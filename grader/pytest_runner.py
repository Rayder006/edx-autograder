import docker
import tempfile
import os
import sys
import json
import time
import subprocess
import logging
import re
import shutil
import signal

from .docker_runtime import host_path, runner_user

logger = logging.getLogger(__name__)

CONFTEST_CONTENT = r"""# -*- coding: utf-8 -*-
import pytest
import json
import os
import sys
import subprocess

from output_validation import validar_saida_script

class ScriptRunner:
    def run(self, script_path="solution.py", stdin=""):
        # Cada caso recebe um processo novo: sys.exit(1), exceções e alterações
        # em globais do aluno não contaminam o Pytest nem os casos seguintes.
        wrapper = (
            'import builtins, runpy, sys\n'
            'original_input = builtins.input\n'
            'builtins.input = lambda prompt="": original_input()\n'
            'runpy.run_path(sys.argv[1], run_name="__main__")\n'
        )
        try:
            result = subprocess.run(
                [sys.executable, '-c', wrapper, script_path], input=stdin,
                capture_output=True, text=True, timeout=30,
            )
        except subprocess.TimeoutExpired:
            raise AssertionError('Tempo limite excedido neste caso de teste (30 segundos).') from None
        if result.returncode:
            raise AssertionError(result.stderr[-4000:] or f'Programa terminou com código {result.returncode}.')
        return result.stdout

    def validar_saida(self, saida_aluno, esperado):
        return validar_saida_script(saida_aluno, esperado)

@pytest.fixture
def script_runner():
    return ScriptRunner()

_test_outcomes = []
_collection_errors = []


def pytest_configure(config):
    config.addinivalue_line('markers', 'bateria(nome, peso, descricao): grupo de testes com pontuação tudo-ou-nada')


def pytest_collectreport(report):
    if report.failed:
        _collection_errors.append(str(report.longrepr))

@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()

    if report.when == "call" or (report.when == "setup" and report.failed):
        bateria_marker = item.get_closest_marker("bateria")
        if bateria_marker:
            bat_nome = bateria_marker.kwargs.get("nome", item.name)
            bat_peso = bateria_marker.kwargs.get("peso", 1.0)
            bat_desc = bateria_marker.kwargs.get("descricao", bat_nome)
        else:
            bat_nome = "default"
            bat_peso = 1.0
            bat_desc = "Default Battery"

        err_msg = ""
        if report.failed:
            err_msg = str(report.longrepr) if report.longrepr else "Falha no teste"

        test_desc = item.name
        if hasattr(item, "callspec"):
            params_str = ", ".join(f"{k}={v}" for k, v in item.callspec.params.items())
            test_desc = f"{item.name} [{params_str}]"

        _test_outcomes.append({
            "nome_teste": item.name,
            "descricao": test_desc,
            "bateria_nome": bat_nome,
            "bateria_peso": bat_peso,
            "bateria_desc": bat_desc,
            "passou": report.passed,
            "erro": err_msg
        })

def pytest_sessionfinish(session, exitstatus):
    baterias_map = {}
    for res in _test_outcomes:
        bat_nome = res["bateria_nome"]
        if bat_nome not in baterias_map:
            baterias_map[bat_nome] = {
                "nome": bat_nome,
                "descricao": res["bateria_desc"],
                "peso": res["bateria_peso"],
                "testes": []
            }
        baterias_map[bat_nome]["testes"].append(res)

    soma_pesos = 0.0
    nota_acumulada = 0.0
    baterias_final = []

    for bat_nome, bat_info in baterias_map.items():
        peso = bat_info["peso"]
        soma_pesos += peso
        todos_passaram = all(t["passou"] for t in bat_info["testes"]) and exitstatus in (0, 1)
        nota_obtida = peso if todos_passaram else 0.0
        nota_acumulada += nota_obtida

        baterias_final.append({
            "nome": bat_nome,
            "descricao": bat_info["descricao"],
            "peso": peso,
            "passou": todos_passaram,
            "nota_obtida": round(nota_obtida, 4),
            "testes": bat_info["testes"]
        })

    if soma_pesos > 1.0:
        nota_final = round(nota_acumulada / soma_pesos, 4)
    else:
        nota_final = round(nota_acumulada, 4)

    nota_final = max(0.0, min(1.0, nota_final))

    if _collection_errors:
        _test_outcomes.append({
            'nome_teste': 'importacao', 'descricao': 'Carregamento da solução',
            'passou': False, 'erro': '\n'.join(_collection_errors)[-8000:],
        })

    report_data = {
        "sucesso": bool(_test_outcomes) and exitstatus in (0, 1, 2),
        "nota": nota_final,
        "baterias": baterias_final,
        "detalhes": _test_outcomes
    }
    if not report_data['sucesso']:
        report_data['erro'] = 'O Pytest não conseguiu executar os testes configurados.'

    results_path = os.environ.get("AUTOGRADER_RESULTS_PATH", "results.json")
    with open(results_path, "w", encoding="utf-8") as f:
        json.dump(report_data, f, indent=2, ensure_ascii=False)
"""

def avaliar_com_pytest(codigo_aluno, exercise_id):
    """
    Executa o código do aluno utilizando o motor Pytest e o arquivo de especificação
    em Python nativo localizado em exercises/test_{exercise_id}.py.
    Executa dentro do Docker. O fallback local só é permitido explicitamente para
    desenvolvimento, pois executar código submetido diretamente no host é inseguro.
    """
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if not isinstance(exercise_id, str) or not re.fullmatch(r'[A-Za-z0-9_]+', exercise_id):
        return _error('Identificador de exercício inválido.')
    test_spec_path = os.path.join(base_dir, "exercises", f"test_{exercise_id}.py")
    
    if not os.path.exists(test_spec_path):
        return _error('Arquivo de testes Pytest não encontrado para este exercício.')

    with open(test_spec_path, "r", encoding="utf-8") as f:
        test_spec_code = f.read()
    try:
        compile(test_spec_code, test_spec_path, 'exec')
    except SyntaxError:
        logger.exception('Sintaxe inválida na especificação de %s.', exercise_id)
        return _error('A configuração de testes deste exercício está inválida. Avise o professor.')

    try:
        compile(codigo_aluno, 'solution.py', 'exec')
    except (SyntaxError, ValueError) as exc:
        return _student_error(f'Erro de sintaxe: {exc}')

    base_tmp_dir = os.environ.get('AUTOGRADER_TMP_DIR') or None
    if base_tmp_dir:
        os.makedirs(base_tmp_dir, mode=0o700, exist_ok=True)

    with tempfile.TemporaryDirectory(dir=base_tmp_dir) as tmpdir:
        # Salva solution.py, test_spec.py e conftest.py
        with open(os.path.join(tmpdir, "solution.py"), "w", encoding="utf-8") as f:
            f.write(codigo_aluno)

        with open(os.path.join(tmpdir, "test_spec.py"), "w", encoding="utf-8") as f:
            f.write(test_spec_code)

        with open(os.path.join(tmpdir, "conftest.py"), "w", encoding="utf-8") as f:
            f.write(CONFTEST_CONTENT)
        shutil.copyfile(
            os.path.join(base_dir, 'grader', 'output_validation.py'),
            os.path.join(tmpdir, 'output_validation.py'),
        )

        results_dir = os.path.join(tmpdir, "results")
        os.mkdir(results_dir)
        results_json_path = os.path.join(results_dir, "results.json")

        # 1. Executa no Docker. A imagem deve conter pytest previamente instalado;
        # instalar dependências durante uma submissão deixa a avaliação lenta e
        # exige rede no container.
        docker_sucesso = False
        docker_erro = None
        container = None
        client = None
        docker_started = False
        try:
            client = docker.from_env(timeout=5)
            client.ping()
            runner_image = os.environ.get(
                "AUTOGRADER_RUNNER_IMAGE", "edx-autograder-web:latest"
            )
            # O diretório temporário é criado pelo processo Django. Executar o
            # container com o mesmo UID evita arquivos root-owned, incluindo o
            # antigo .pytest_cache relatado na infraestrutura da USP.
            container_user = runner_user(tmpdir, (results_dir,))
            container = client.containers.run(
                image=runner_image,
                # O watchdog continua válido se o worker web for interrompido.
                command=['timeout', '--signal=KILL', '35s', 'python', '-m', 'pytest', '/app/test_spec.py', '--tb=short', '-p', 'no:cacheprovider'],
                volumes={
                    host_path(tmpdir): {'bind': '/app', 'mode': 'ro'},
                    host_path(results_dir): {'bind': '/result', 'mode': 'rw'},
                },
                working_dir="/app",
                user=container_user,
                network_disabled=True,
                mem_limit="128m",
                pids_limit=64,
                nano_cpus=1_000_000_000,
                read_only=True,
                tmpfs={'/tmp': 'rw,nosuid,size=32m'},
                cap_drop=['ALL'],
                security_opt=['no-new-privileges:true'],
                labels={'edx-autograder.role': 'evaluation'},
                environment={
                    "AUTOGRADER_RESULTS_PATH": "/result/results.json",
                    "PYTHONDONTWRITEBYTECODE": "1", "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
                },
                detach=True,
                stdout=True,
                stderr=True
            )
            docker_started = True

            timeout = 30
            intervalo = 0.2
            deadline = time.monotonic() + timeout
            passou_limite = False

            while True:
                container.reload()
                if container.status != "running":
                    break
                if time.monotonic() >= deadline:
                    passou_limite = True
                    break
                time.sleep(intervalo)

            if passou_limite:
                return _student_error('Tempo limite de execução excedido (30 segundos). Verifique se há um loop infinito.')

            state = container.attrs.get('State', {})
            if state.get('OOMKilled'):
                return _student_error('Limite de memória excedido (128 MB).')
            if state.get('ExitCode') in (124, 137):
                return _student_error('Tempo limite de execução excedido.')
            if state.get('ExitCode') not in (0, 1, 2):
                docker_erro = container.logs(tail=30).decode('utf-8', errors='replace')[-4000:]

            docker_sucesso = True
        except Exception as docker_err:
            docker_erro = docker_err
            logger.warning('Falha ao executar avaliador Docker: %s', docker_err)
        finally:
            if container is not None:
                try:
                    container.remove(force=True)
                except docker.errors.DockerException:
                    logger.exception('Não foi possível remover o container de avaliação.')
            if client is not None:
                client.close()

        # 2. Execução local via Subprocesso (fallback) se Docker não rodou.
        if not docker_sucesso:
            allow_local_fallback = os.environ.get('AUTOGRADER_ALLOW_LOCAL_FALLBACK') == '1'

            if not allow_local_fallback or docker_started:
                return _error('O ambiente Docker do corretor não está disponível. Avise o professor e tente novamente mais tarde.')

            cmd = [sys.executable, '-m', 'pytest', 'test_spec.py', '--tb=short', '-p', 'no:cacheprovider']
            with subprocess.Popen(
                cmd, cwd=tmpdir, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                start_new_session=True,
                env={**os.environ, 'AUTOGRADER_RESULTS_PATH': results_json_path,
                     'PYTHONDONTWRITEBYTECODE': '1', 'PYTEST_DISABLE_PLUGIN_AUTOLOAD': '1'},
            ) as process:
                try:
                    stdout, stderr = process.communicate(timeout=30)
                except subprocess.TimeoutExpired:
                    # Encerra também os subprocessos do código avaliado.
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    process.communicate()
                    return _student_error('Tempo limite de execução excedido (30 segundos).')
                if process.returncode and not os.path.exists(results_json_path):
                    docker_erro = stderr.strip() or stdout.strip()

        # 3. Lê o resultado produzido pelo conftest.py
        if os.path.exists(results_json_path):
            try:
                with open(results_json_path, "r", encoding="utf-8") as f:
                    result = json.load(f)
                if (not isinstance(result, dict) or not isinstance(result.get('nota'), (int, float))
                        or not 0 <= result['nota'] <= 1
                        or not isinstance(result.get('detalhes'), list)):
                    raise ValueError('Relatório inválido.')
                return result
            except (OSError, ValueError):
                logger.exception('Falha ao ler o relatório Pytest.')
                return _error('O corretor não conseguiu ler o resultado. Tente novamente.')
        else:
            logger.error('Pytest não gerou relatório: %s', docker_erro)
            return _error('Falha na geração do relatório de resultados pelo Pytest. Avise o professor.')


def _error(message):
    return {'sucesso': False, 'nota': 0.0, 'erro': message, 'baterias': [], 'detalhes': []}


def _student_error(message):
    return {
        'sucesso': True, 'nota': 0.0, 'erro': message, 'baterias': [],
        'detalhes': [{'nome_teste': 'execucao', 'descricao': 'Execução da solução',
                      'passou': False, 'erro': message}],
    }
