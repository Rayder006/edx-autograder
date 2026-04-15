from .runner import avaliar_no_docker
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
    
    # simulação de teste com json temporário (aqui colocamos o nosso json depois de criá-lo)
    casos_de_teste = [
        "2\n3\n",    # Teste 1: deve dar 5
        "10\n5\n"   # Teste 2: deve dar 15
    ]
    
    # Chama o motor (Isso vai bloquear o Django até o Docker terminar, podemos usar Celery + Redis)
    resultados_docker = avaliar_no_docker(student_code, casos_de_teste)
    
    print("=== RESULTADOS DA EXECUÇÃO ===")
    for i, res in enumerate(resultados_docker):
        print(f"Caso de Teste {i+1}:")
        print(f"Saída do Aluno: {res}")
        print("-" * 30)
    
    return HttpResponse("Submissão LTI recebida e executada com sucesso.", status=200)