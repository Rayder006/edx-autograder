import docker
import tempfile
import os

def avaliar_no_docker(codigo_aluno, lista_inputs):
    """
    Roda o código do aluno no Docker para cada input da lista.
    Retorna uma lista com as saídas geradas.
    """
    client = docker.from_env()
    saidas = []
    
    # cria uma pasta temporária (ex: /var/folders/.../tmp_xyz)
    with tempfile.TemporaryDirectory() as tmpdir:
        
        # salva a string do aluno como um arquivo .py real
        caminho_arquivo = os.path.join(tmpdir, "solution.py")
        with open(caminho_arquivo, "w") as f:
            f.write(codigo_aluno)

        # roda o container (uma vez para cada caso de teste)
        for input_str in lista_inputs:
            try:
                # o comando echo injeta o input direto no stdin do python
                comando = f"sh -c 'echo \"{input_str}\" | python /app/solution.py'"
                
                resultado = client.containers.run(
                    image="python:3.13-alpine", # Imagem rápida
                    command=comando,
                    volumes={tmpdir: {'bind': '/app', 'mode': 'ro'}}, # Read Only
                    working_dir="/app",
                    network_disabled=True,      # Sem acesso à internet
                    mem_limit="128m",           # Limite de RAM para não travar o servidor
                    remove=True,                # Destrói o container assim que terminar
                    stdout=True,
                    stderr=True
                )
                
                # Decodifica os bytes que o Docker devolveu
                saidas.append(resultado.decode('utf-8').strip())
                
            except docker.errors.ContainerError as e:
                # Se o código do aluno der erro (ex: SyntaxError), o Docker devolve o erro
                saidas.append(f"Erro de Execução:\n{e.stderr.decode('utf-8')}")
            except Exception as e:
                saidas.append(f"Erro do Sistema: {str(e)}")
                
    return saidas