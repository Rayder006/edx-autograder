from .runner import avaliar_no_docker_com_json
from django.conf import settings
import os
import json
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
import urllib.parse
import hmac
import hashlib
import base64

LTI_KEY = 'minha_chave_edx_usp'
LTI_SECRET = 'meu_segredo_super_seguro'

def escape(text):
    """Codificação RFC 3986 (O padrão exigido pela matemática do OAuth 1.0)"""
    return urllib.parse.quote(str(text), safe='~')


# View que recebe a Request LTI, decriptografa o HMAC (Usando a LTI_KEY e LTI_SECRET que precisamos definir) e envia para o runner.py rodar
@csrf_exempt
@require_POST
def lti_grade_endpoint(request):
    uri = request.build_absolute_uri()
    
    received_signature = request.POST.get('oauth_signature')
    client_key = request.POST.get('oauth_consumer_key')
    
    if client_key != LTI_KEY:
        return HttpResponse("Chave LTI não reconhecida.", status=403)
        
    if not received_signature:
        return HttpResponse("Assinatura ausente.", status=403)

    # Coleta os parâmetros do Request
    params = [(k, v) for k, v in request.POST.items() if k != 'oauth_signature']
    
    # Codifica e Ordena os parâmetros
    encoded_params = [(escape(k), escape(v)) for k, v in params]
    encoded_params.sort()  # Ordena alfabeticamente pela chave
    param_string = "&".join([f"{k}={v}" for k, v in encoded_params])
    
    # Monta a Base String
    base_string = "&".join([
        request.method.upper(),
        escape(uri.split('?')[0].lower()), # Garante que a URL base esteja limpa
        escape(param_string)
    ])
    
    # A Chave de Assinatura (Consumer Secret + "&" + Token Secret que no LTI é vazio)
    signing_key = escape(LTI_SECRET) + "&"
    
    # Hash HMAC-SHA1
    hashed = hmac.new(
        signing_key.encode('utf-8'),
        base_string.encode('utf-8'),
        hashlib.sha1
    )
    
    # Transforma os bytes do hash em uma string legível em Base64
    expected_signature = base64.b64encode(hashed.digest()).decode('utf-8')

    print("\n=== MOTOR CRIPTOGRÁFICO RAIZ ===")
    print(f"Assinatura do Request (EdX) : {received_signature}")
    print(f"Assinatura Calculada AQUI  : {expected_signature}")
    print("================================\n")

    # compare_digest evita ataques de temporização do lado do servidor
    if not hmac.compare_digest(expected_signature.encode(), received_signature.encode()):
        return HttpResponse("Acesso Negado: As assinaturas HMAC não batem.", status=403)
    
    student_code = request.POST.get('custom_student_code', '')
    sourcedid = request.POST.get('lis_result_sourcedid')
    
    print("--- NOVA SUBMISSÃO AUTENTICADA ---")
    print(f"ID: {sourcedid}")
    print("Iniciando container Docker...\n")
    
    # Determina qual exercício avaliar
    exercise_id = request.POST.get('custom_exercise_id') or request.POST.get('resource_link_id')
    if not exercise_id:
        # fallback para testes locais rápidos se não enviado via LTI
        exercise_id = "week_4_fatorial"
    
    caminho_tests_json = os.path.join(settings.BASE_DIR, 'tests.json')
    if not os.path.exists(caminho_tests_json):
        return HttpResponse("Arquivo tests.json de configuração não encontrado.", status=500)
        
    with open(caminho_tests_json, 'r', encoding='utf-8') as f:
        todos_os_testes = json.load(f)
        
    if exercise_id not in todos_os_testes:
        return HttpResponse(f"Exercício '{exercise_id}' não configurado no autograder.", status=400)
        
    config_exercicio = todos_os_testes[exercise_id]
    
    # Chama o motor Docker
    resultado_avaliacao = avaliar_no_docker_com_json(student_code, config_exercicio)
    
    # Constrói o relatório detalhado no formato solicitado
    feedback_lines = ["O resultado dos testes com seu programa foi:\n"]
    
    for r in resultado_avaliacao['detalhes']:
        peso = r.get("peso", 0.0)
        descricao = r.get("descricao", "teste")
        passou = r.get("passou", False)
        
        status_str = "Passou" if passou else "Falhou"
        feedback_lines.append(f"***** [{peso * 10:.1f} pontos]: {descricao} - {status_str} *****")
        
        if not passou:
            if 'erro' in r:
                feedback_lines.append(f"Erro de execução:\n{r['erro']}\n")
            else:
                saida_aluno = r.get("saida_aluno")
                esperado = r.get("esperado")
                feedback_lines.append(
                    f"AssertionError: Esperado:\n{esperado}\n"
                    f"Recebido:\n{saida_aluno}\n"
                )
    
    nota_final_10 = round(resultado_avaliacao['nota'] * 10, 1)
    feedback_lines.append(f"\nNota Final: {nota_final_10}/10.0")
    
    feedback_text = "\n".join(feedback_lines)
    
    # Imprime no log para depuração local do servidor
    print("\n=== FEEDBACK GERADO ===")
    print(feedback_text)
    print("=======================\n")
    
    return HttpResponse(feedback_text, content_type="text/plain; charset=utf-8", status=200)