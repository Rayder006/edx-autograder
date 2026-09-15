import docker
import tempfile
import os
import sys
import json
import time
import subprocess

CONFTEST_CONTENT = r"""# -*- coding: utf-8 -*-
import pytest
import runpy
import io
import re
import unicodedata
import json
import os

def normalizar(texto):
    if not texto:
        return ""
    texto = "".join(c for c in unicodedata.normalize('NFD', texto) if unicodedata.category(c) != 'Mn')
    texto = texto.lower()
    texto = re.sub(r'[.,;:!?\-()\[\]{}"\']', ' ', texto)
    return texto

def validar_saida_script(saida_aluno, esperado):
    saida_norm = normalizar(saida_aluno)
    esp_norm = normalizar(esperado)
    if "\n" in esperado.strip():
        linhas_esperadas = [normalizar(l) for l in esperado.strip().split("\n") if l.strip()]
        idx_atual = 0
        for linha in linhas_esperadas:
            match = re.search(r'\b' + re.escape(linha) + r'\b', saida_norm[idx_atual:])
            if not match:
                return False
            idx_atual += match.end()
        return True
    palavras_esperadas = esp_norm.split()
    if not palavras_esperadas:
        return True
    regex_busca = r'\b' + r'\b.*\b'.join(re.escape(w) for w in palavras_esperadas) + r'\b'
    return re.search(regex_busca, saida_norm) is not None

class ScriptRunner:
    def __init__(self, monkeypatch, capsys):
        self.monkeypatch = monkeypatch
        self.capsys = capsys

    def run(self, script_path="solution.py", stdin=""):
        self.monkeypatch.setattr("sys.stdin", io.StringIO(stdin))
        try:
            runpy.run_path(script_path, run_name="__main__")
        except SystemExit:
            pass
        captured = self.capsys.readouterr()
        return captured.out

    def validar_saida(self, saida_aluno, esperado):
        return validar_saida_script(saida_aluno, esperado)

@pytest.fixture
def script_runner(monkeypatch, capsys):
    return ScriptRunner(monkeypatch, capsys)

_test_outcomes = []

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
        todos_passaram = all(t["passou"] for t in bat_info["testes"])
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

    report_data = {
        "sucesso": True,
        "nota": nota_final,
        "baterias": baterias_final,
        "detalhes": _test_outcomes
    }

    with open("results.json", "w", encoding="utf-8") as f:
        json.dump(report_data, f, indent=2, ensure_ascii=False)
"""

def avaliar_com_pytest(codigo_aluno, exercise_id):
    """
    Executa o código do aluno utilizando o motor Pytest e o arquivo de especificação
    em Python nativo localizado em exercises/test_{exercise_id}.py.
    Tenta executar dentro do Docker e faz fallback gracioso para subprocesso local se o Docker não estiver ativo.
    """
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    test_spec_path = os.path.join(base_dir, "exercises", f"test_{exercise_id}.py")
    
    if not os.path.exists(test_spec_path):
        raise FileNotFoundError(f"Arquivo de testes Pytest não encontrado: {test_spec_path}")

    with open(test_spec_path, "r", encoding="utf-8") as f:
        test_spec_code = f.read()

    base_tmp_dir = os.environ.get('AUTOGRADER_TMP_DIR', None)
    with tempfile.TemporaryDirectory(dir=base_tmp_dir) as tmpdir:
        # Salva solution.py, test_spec.py e conftest.py
        with open(os.path.join(tmpdir, "solution.py"), "w", encoding="utf-8") as f:
            f.write(codigo_aluno)

        with open(os.path.join(tmpdir, "test_spec.py"), "w", encoding="utf-8") as f:
            f.write(test_spec_code)

        with open(os.path.join(tmpdir, "conftest.py"), "w", encoding="utf-8") as f:
            f.write(CONFTEST_CONTENT)

        # 1. Tenta executar no Docker se disponível
        docker_sucesso = False
        try:
            client = docker.from_env()
            client.ping()
            comando_bash = "pip install --quiet pytest && pytest /app/test_spec.py --tb=short"
            container = client.containers.run(
                image="python:3.13-alpine",
                command=f"sh -c '{comando_bash}'",
                volumes={tmpdir: {'bind': '/app', 'mode': 'rw'}},
                working_dir="/app",
                network_disabled=False,
                mem_limit="128m",
                detach=True,
                stdout=True,
                stderr=True
            )

            timeout = 15
            intervalo = 0.2
            tempo_decorrido = 0.0
            passou_limite = False

            while True:
                container.reload()
                if container.status != "running":
                    break
                if tempo_decorrido >= timeout:
                    passou_limite = True
                    break
                time.sleep(intervalo)
                tempo_decorrido += intervalo

            if passou_limite:
                try:
                    container.kill()
                except Exception:
                    pass
                try:
                    container.remove(force=True)
                except Exception:
                    pass
                raise TimeoutError("Tempo limite de execução excedido (15 segundos).")

            try:
                container.remove(force=True)
            except Exception:
                pass

            docker_sucesso = True
        except Exception as docker_err:
            # Docker não disponível ou falha no daemon: usa fallback para subprocesso local
            pass

        # 2. Execução local via Subprocesso (fallback) se Docker não rodou
        if not docker_sucesso:
            import shutil
            pytest_bin = shutil.which("pytest")
            if pytest_bin:
                cmd = [pytest_bin, "test_spec.py", "-v", "--tb=short"]
            else:
                cmd = [sys.executable, "-m", "pytest", "test_spec.py", "-v", "--tb=short"]
                
            subprocess.run(cmd, cwd=tmpdir, capture_output=True, text=True, timeout=15)

        # 3. Lê o resultado produzido pelo conftest.py
        results_json_path = os.path.join(tmpdir, "results.json")
        if os.path.exists(results_json_path):
            with open(results_json_path, "r", encoding="utf-8") as f:
                return json.load(f)
        else:
            return {
                "sucesso": False,
                "nota": 0.0,
                "erro": "Falha na geração do relatório de resultados pelo Pytest.",
                "baterias": [],
                "detalhes": []
            }
