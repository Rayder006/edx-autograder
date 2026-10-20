"""Motor legado JSON, mantido para seleção explícita pela infraestrutura."""
import json
import logging
import os
import tempfile
import time

import docker

from .docker_runtime import host_path, runner_user
from .evaluator import extrair_lista_testes, calcular_nota_baterias
from .output_validation import normalizar, validar_saida_script

logger = logging.getLogger(__name__)


def avaliar_no_docker_com_json(codigo_aluno, config_exercicio):
    client = None
    try:
        client = docker.from_env(timeout=5)
        client.ping()
        return _evaluate(client, codigo_aluno, config_exercicio)
    except (docker.errors.DockerException, OSError, ValueError):
        logger.exception('Falha operacional no avaliador legado.')
        return {
            'sucesso': False, 'nota': 0, 'detalhes': [], 'baterias': [],
            'erro': 'O Docker do corretor está indisponível. Avise o professor.',
        }
    finally:
        if client is not None:
            client.close()


def _evaluate(client, code, config):
    results = []
    tipo = config.get('tipo', 'script')
    image = os.environ.get('AUTOGRADER_RUNNER_IMAGE', 'edx-autograder-web:latest')
    base = os.environ.get('AUTOGRADER_TMP_DIR') or None
    if base:
        os.makedirs(base, mode=0o700, exist_ok=True)
    total_deadline = time.monotonic() + 30
    for index, test in enumerate(extrair_lista_testes(config)):
        if time.monotonic() >= total_deadline:
            report = calcular_nota_baterias(config, results)
            report['erro'] = 'Tempo limite total de execução excedido (30 segundos).'
            return report
        result = {
            'caso': index + 1, 'passou': False,
            'peso': test.get('peso', 0), 'descricao': test.get('descricao', f'Caso {index + 1}'),
            'bateria_idx': test.get('_bateria_idx'), 'bateria_nome': test.get('_bateria_nome'),
            'bateria_peso': test.get('_bateria_peso'), 'bateria_desc': test.get('_bateria_desc'),
            'esperado': test.get('expected'),
        }
        with tempfile.TemporaryDirectory(dir=base) as directory:
            with open(os.path.join(directory, 'solution.py'), 'w', encoding='utf-8') as file:
                file.write(code)
            if tipo == 'script':
                with open(os.path.join(directory, 'input.txt'), 'w', encoding='utf-8') as file:
                    file.write(test.get('input', ''))
                with open(os.path.join(directory, 'wrapper.py'), 'w', encoding='utf-8') as file:
                    file.write(
                        'import builtins, runpy\n'
                        'original_input = builtins.input\n'
                        'builtins.input = lambda prompt="": original_input()\n'
                        'runpy.run_path("/app/solution.py", run_name="__main__")\n'
                    )
                command = ['sh', '-c', 'python /app/wrapper.py < /app/input.txt']
            elif tipo == 'funcao':
                name = config['nome_funcao']
                if not name.isidentifier():
                    raise ValueError('Nome de função inválido na configuração.')
                wrapper = (
                    'import json\n'
                    f'from solution import {name}\n'
                    f'print(json.dumps({name}(*{test.get("args", [])!r})))\n'
                )
                with open(os.path.join(directory, 'wrapper.py'), 'w', encoding='utf-8') as file:
                    file.write(wrapper)
                command = ['python', '/app/wrapper.py']
            else:
                raise ValueError('Tipo de exercício não suportado.')
            container = None
            try:
                container = client.containers.run(
                    image=image, command=['timeout', '--signal=KILL', '7s', *command],
                    volumes={host_path(directory): {'bind': '/app', 'mode': 'ro'}},
                    working_dir='/app', user=runner_user(directory),
                    network_disabled=True, mem_limit='128m', pids_limit=64,
                    nano_cpus=1_000_000_000, read_only=True,
                    tmpfs={'/tmp': 'rw,nosuid,size=32m'},
                    cap_drop=['ALL'], security_opt=['no-new-privileges:true'],
                    labels={'edx-autograder.role': 'evaluation'},
                    environment={'PYTHONDONTWRITEBYTECODE': '1'}, detach=True,
                )
                deadline = min(time.monotonic() + 5, total_deadline)
                while True:
                    container.reload()
                    if container.status != 'running':
                        break
                    if time.monotonic() >= deadline:
                        raise TimeoutError('Tempo limite excedido (5 segundos). Verifique loops infinitos.')
                    time.sleep(0.1)
                state = container.attrs['State']
                output = container.logs(stdout=True, stderr=False, tail=100).decode('utf-8', errors='replace').strip()
                error = container.logs(stdout=False, stderr=True, tail=100).decode('utf-8', errors='replace').strip()
                if state.get('OOMKilled'):
                    result['erro'] = 'Limite de memória excedido (128 MB).'
                elif state['ExitCode']:
                    result['erro'] = error or f"Programa terminou com código {state['ExitCode']}."
                else:
                    try:
                        result['saida_aluno'] = json.loads(output) if tipo == 'funcao' else output
                        result['passou'] = (
                            result['saida_aluno'] == test.get('expected') if tipo == 'funcao'
                            else validar_saida_script(output, test.get('expected'))
                        )
                    except ValueError:
                        result['erro'] = 'A função não retornou um resultado JSON válido.'
            except TimeoutError as exc:
                result['erro'] = str(exc)
            finally:
                if container is not None:
                    container.remove(force=True)
        results.append(result)
    return calcular_nota_baterias(config, results)
