import docker
import tempfile
import os
import json
import re
import unicodedata

def normalizar(texto):
    if not texto:
        return ""
    # Remove acentos e caracteres diacríticos
    texto = "".join(c for c in unicodedata.normalize('NFD', texto) if unicodedata.category(c) != 'Mn')
    # Converte para minúsculas
    texto = texto.lower()
    # Substitui pontuações por espaços simples para isolar palavras
    texto = re.sub(r'[.,;:!?\-()\[\]{}"\']', ' ', texto)
    return texto

def validar_saida_script(saida_aluno, esperado):
    saida_norm = normalizar(saida_aluno)
    esp_norm = normalizar(esperado)
    
    # Tratamento para saídas com múltiplas linhas significativas (ex: n_impares, retângulos)
    if "\n" in esperado.strip():
        linhas_esperadas = [normalizar(l) for l in esperado.strip().split("\n") if l.strip()]
        idx_atual = 0
        for linha in linhas_esperadas:
            # Busca a linha inteira a partir do índice atual na saída do aluno
            match = re.search(r'\b' + re.escape(linha) + r'\b', saida_norm[idx_atual:])
            if not match:
                return False
            idx_atual += match.end()
        return True
    
    # Caso geral de única linha ou resposta única
    palavras_esperadas = esp_norm.split()
    if not palavras_esperadas:
        return True
    
    # Monta uma regex para buscar as palavras esperadas na ordem em que aparecem
    regex_busca = r'\b' + r'\b.*\b'.join(re.escape(w) for w in palavras_esperadas) + r'\b'
    return re.search(regex_busca, saida_norm) is not None

def avaliar_no_docker_com_json(codigo_aluno, config_exercicio):
    """
    Roda o código do aluno se adaptando ao tipo (script de I/O ou Função Pura).
    """
    client = docker.from_env()
    resultados = []
    
    tipo = config_exercicio.get("tipo", "script")
    testes = config_exercicio.get("testes", [])
    
    for i, teste in enumerate(testes):
        peso = teste.get("peso", 0.0)
        descricao = teste.get("descricao", f"Caso de teste {i+1}")
        
        with tempfile.TemporaryDirectory() as tmpdir:
            # 1. Salva o código do aluno
            caminho_codigo = os.path.join(tmpdir, "solution.py")
            with open(caminho_codigo, "w", encoding='utf-8') as f:
                f.write(codigo_aluno)

            comando_bash = ""
            
            # 2. Prepara a execução baseado no tipo de exercício
            if tipo == "script":
                caminho_input = os.path.join(tmpdir, "input.txt")
                with open(caminho_input, "w", encoding='utf-8') as f:
                    f.write(teste["input"])
                
                comando_bash = "python /app/solution.py < /app/input.txt"
                
            elif tipo == "funcao":
                nome_funcao = config_exercicio["nome_funcao"]
                args = teste["args"]
                
                caminho_wrapper = os.path.join(tmpdir, "wrapper.py")
                # O wrapper importa a solução, roda a função e imprime o retorno serializado em JSON
                wrapper_code = (
                    "import json\n"
                    "import sys\n"
                    "import traceback\n"
                    "try:\n"
                    f"    from solution import {nome_funcao}\n"
                    f"    args = {repr(args)}\n"
                    f"    resultado = {nome_funcao}(*args)\n"
                    "    print(json.dumps(resultado))\n"
                    "except Exception as e:\n"
                    "    sys.stderr.write(traceback.format_exc())\n"
                    "    sys.exit(1)\n"
                )
                
                with open(caminho_wrapper, "w", encoding='utf-8') as f:
                    f.write(wrapper_code)
                
                comando_bash = "python /app/wrapper.py"

            # 3. Dispara o Container do Docker
            try:
                resultado = client.containers.run(
                    image="python:3.13-alpine",
                    command=f"sh -c '{comando_bash}'",
                    volumes={tmpdir: {'bind': '/app', 'mode': 'ro'}},
                    working_dir="/app",
                    network_disabled=True,
                    mem_limit="128m",
                    remove=True,
                    stdout=True,
                    stderr=True
                )
                
                saida = resultado.decode('utf-8').strip()
                esperado = teste.get("expected")
                passou = False
                
                if tipo == "script":
                    passou = validar_saida_script(saida, esperado)
                    resultados.append({
                        "caso": i + 1,
                        "passou": passou,
                        "saida_aluno": saida,
                        "esperado": esperado,
                        "peso": peso,
                        "descricao": descricao
                    })
                elif tipo == "funcao":
                    try:
                        # Desserializa o resultado retornado pelo wrapper
                        objeto_retornado = json.loads(saida)
                        passou = (objeto_retornado == esperado)
                        resultados.append({
                            "caso": i + 1,
                            "passou": passou,
                            "saida_aluno": objeto_retornado,
                            "esperado": esperado,
                            "peso": peso,
                            "descricao": descricao
                        })
                    except Exception as json_err:
                        resultados.append({
                            "caso": i + 1,
                            "passou": False,
                            "saida_aluno": saida,
                            "esperado": esperado,
                            "peso": peso,
                            "descricao": descricao,
                            "erro": f"Erro ao decodificar a saída da função (esperado JSON): {str(json_err)}"
                        })
                
            except docker.errors.ContainerError as e:
                # Trata erros de execução (syntax error ou exceções não capturadas no script)
                stderr_output = e.stderr.decode('utf-8').strip()
                resultados.append({
                    "caso": i + 1,
                    "passou": False,
                    "peso": peso,
                    "descricao": descricao,
                    "erro": stderr_output if stderr_output else str(e)
                })
            except Exception as ex:
                resultados.append({
                    "caso": i + 1,
                    "passou": False,
                    "peso": peso,
                    "descricao": descricao,
                    "erro": f"Erro inesperado durante a execução do container: {str(ex)}"
                })
                
    # 4. Calcula a nota final do exercício (soma ponderada dos pesos dos testes que passaram)
    acertos_ponderados = sum(r.get("peso", 0.0) for r in resultados if r.get("passou", False))
    nota = round(acertos_ponderados, 2)
    
    return {"sucesso": True, "nota": nota, "detalhes": resultados}