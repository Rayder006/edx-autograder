from .runner import avaliar_no_docker_com_json
from django.conf import settings
import os
import json
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.views.decorators.clickjacking import xframe_options_exempt
from django.core import signing
from django.shortcuts import render
import urllib.parse
import hmac
import hashlib
import base64
import requests
from requests_oauthlib import OAuth1
from .models import Aluno, Submissao

LTI_KEY = os.environ.get('LTI_CONSUMER_KEY', 'minha_chave_edx_usp')
LTI_SECRET = os.environ.get('LTI_SHARED_SECRET', 'meu_segredo_super_seguro')


def escape(text):
    """Codificação RFC 3986 (O padrão exigido pela matemática do OAuth 1.0)"""
    return urllib.parse.quote(str(text), safe='~')


def enviar_nota_ao_edx(lis_outcome_service_url, lis_result_sourcedid, nota_decimal, client_key, client_secret):
    """
    Envia a nota do aluno de volta para o LMS (EdX/Moodle) via LTI Outcomes 1.1 (XML SOAP).
    nota_decimal deve ser um valor de 0.0 a 1.0.
    """
    if not lis_outcome_service_url or not lis_result_sourcedid:
        print("LTI Outcomes: lis_outcome_service_url ou lis_result_sourcedid não informados. Ignorando envio de nota.")
        return False

    import uuid
    message_id = uuid.uuid4().hex

    xml_data = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<imsx_POXEnvelopeRequest xmlns="http://www.imsglobal.org/services/ltiv1p1/xsd/imsoms_v1p0">\n'
        '  <imsx_POXHeader>\n'
        '    <imsx_POXRequestHeaderInfo>\n'
        '      <imsx_version>V1.0</imsx_version>\n'
        f'      <imsx_messageIdentifier>{message_id}</imsx_messageIdentifier>\n'
        '    </imsx_POXRequestHeaderInfo>\n'
        '  </imsx_POXHeader>\n'
        '  <imsx_POXBody>\n'
        '    <replaceResultRequest>\n'
        '      <resultRecord>\n'
        '        <sourcedGUID>\n'
        f'          <sourcedId>{lis_result_sourcedid}</sourcedId>\n'
        '        </sourcedGUID>\n'
        '        <result>\n'
        '          <resultScore>\n'
        '            <language>en</language>\n'
        f'            <textString>{nota_decimal:.4f}</textString>\n'
        '          </resultScore>\n'
        '        </result>\n'
        '      </resultRecord>\n'
        '    </replaceResultRequest>\n'
        '  </imsx_POXBody>\n'
        '</imsx_POXEnvelopeRequest>'
    )

    encoded_xml = xml_data.encode('utf-8')
    body_hash = base64.b64encode(hashlib.sha1(encoded_xml).digest()).decode('utf-8')

    auth = OAuth1(
        client_key,
        client_secret,
        signature_method='HMAC-SHA1'
    )

    headers = {'Content-Type': 'application/xml'}

    try:
        print(f"LTI Outcomes: Iniciando envio de nota para {lis_outcome_service_url}...", flush=True)
        response = requests.post(lis_outcome_service_url, data=encoded_xml, auth=auth, headers=headers, timeout=10)
        print(f"\n=== LTI OUTCOMES GRADE PASSBACK ===", flush=True)
        print(f"URL: {lis_outcome_service_url}", flush=True)
        print(f"Status da Resposta: {response.status_code}", flush=True)
        print(f"Resposta:\n{response.text}", flush=True)
        print("===================================\n", flush=True)
        return response.status_code == 200
    except Exception as e:
        print(f"Erro ao enviar nota via LTI Outcomes: {str(e)}", flush=True)
        return False


@csrf_exempt
@xframe_options_exempt
@require_POST
def lti_grade_endpoint(request, course_id=None, exercise_id=None):
    # 1. Verifica se é uma submissão via formulário HTML (possui lti_token)
    lti_token = request.POST.get('lti_token')
    
    if lti_token:
        try:
            # Descriptografa e valida os dados de sessão LTI
            lti_params = signing.loads(lti_token, max_age=3600)  # Válido por 1 hora
        except signing.SignatureExpired:
            return HttpResponse("A sessão expirou. Por favor, recarregue a página no EdX.", status=403)
        except signing.BadSignature:
            return HttpResponse("Assinatura de sessão inválida.", status=403)
            
        exercise_id = lti_params.get('custom_exercise_id')
        user_id = lti_params.get('user_id', 'aluno_test')
        
        try:
            aluno = Aluno.objects.get(user_id=user_id)
        except Aluno.DoesNotExist:
            return HttpResponse("Aluno não encontrado no banco de dados local.", status=400)

        # Lê o código enviado pelo formulário ou via upload de arquivo
        student_code = request.POST.get('custom_student_code', '')
        if 'code_file' in request.FILES:
            try:
                student_code = request.FILES['code_file'].read().decode('utf-8', errors='replace')
            except Exception:
                pass
                
        caminho_tests_json = os.path.join(settings.BASE_DIR, 'tests.json')
        if not os.path.exists(caminho_tests_json):
            return HttpResponse("Arquivo tests.json de configuração não encontrado.", status=500)
            
        with open(caminho_tests_json, 'r', encoding='utf-8') as f:
            todos_os_testes = json.load(f)
            
        if exercise_id not in todos_os_testes:
            return HttpResponse(f"Exercício '{exercise_id}' não configurado no autograder.", status=400)
            
        config_exercicio = todos_os_testes[exercise_id]
        
        # Bloqueia re-submissão caso o aluno já tenha nota máxima (10.0) salva
        try:
            submissao_existente = Submissao.objects.get(aluno=aluno, exercise_id=exercise_id)
            if submissao_existente.nota >= 10.0:
                resultado_avaliacao = json.loads(submissao_existente.resultado_json)
                
                # Adiciona peso formatado para exibição se necessário
                for r in resultado_avaliacao.get('detalhes', []):
                    r['peso_exibicao'] = f"{r.get('peso', 0.0) * 10:.1f}"
                    
                context = {
                    'exercise_id': exercise_id,
                    'lti_token': lti_token,
                    'student_code': submissao_existente.student_code,
                    'resultado': resultado_avaliacao,
                    'nota_10': 10.0,
                    'passou_count': len(resultado_avaliacao.get('detalhes', [])),
                    'total_count': len(resultado_avaliacao.get('detalhes', [])),
                }
                return render(request, 'grader/index.html', context)
        except Submissao.DoesNotExist:
            pass

        # Executa no Docker
        resultado_avaliacao = avaliar_no_docker_com_json(student_code, config_exercicio)
        
        # Prepara estatísticas de exibição e nota
        nota_10 = round(resultado_avaliacao['nota'] * 10, 1)
        passou_count = sum(1 for r in resultado_avaliacao['detalhes'] if r.get('passou'))
        total_count = len(resultado_avaliacao['detalhes'])
        
        # Salva ou atualiza a submissão no banco de dados local
        submissao, _ = Submissao.objects.update_or_create(
            aluno=aluno,
            exercise_id=exercise_id,
            defaults={
                'nota': nota_10,
                'student_code': student_code,
                'resultado_json': json.dumps(resultado_avaliacao)
            }
        )
        
        # Envia a nota de volta para a plataforma EdX
        lis_outcome_service_url = lti_params.get('lis_outcome_service_url')
        lis_result_sourcedid = lti_params.get('lis_result_sourcedid')
        oauth_consumer_key = lti_params.get('oauth_consumer_key') or LTI_KEY
        
        enviar_nota_ao_edx(
            lis_outcome_service_url=lis_outcome_service_url,
            lis_result_sourcedid=lis_result_sourcedid,
            nota_decimal=resultado_avaliacao.get('nota', 0.0),
            client_key=oauth_consumer_key,
            client_secret=LTI_SECRET
        )
        
        # Adiciona peso na escala 0-10 para facilitar a renderização no template
        for r in resultado_avaliacao['detalhes']:
            r['peso_exibicao'] = f"{r.get('peso', 0.0) * 10:.1f}"
            
        context = {
            'exercise_id': exercise_id,
            'lti_token': lti_token,
            'student_code': student_code,
            'resultado': resultado_avaliacao,
            'nota_10': nota_10,
            'passou_count': passou_count,
            'total_count': total_count,
        }
        return render(request, 'grader/index.html', context)

    # 2. Caso contrário, é um LTI Launch inicial vindo do EdX.
    # Valida as chaves e assinatura LTI / OAuth 1.0.
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
    
    sourcedid = request.POST.get('lis_result_sourcedid')
    user_id = request.POST.get('user_id', 'aluno_test')
    
    # Registra ou recupera o aluno no banco de dados local
    aluno, _ = Aluno.objects.get_or_create(user_id=user_id)
    
    # Determina qual exercício avaliar
    exercise_id_resolved = exercise_id
    if not exercise_id_resolved:
        exercise_id_resolved = request.GET.get('exercise') or request.POST.get('custom_exercise_id') or request.POST.get('resource_link_id')
    if not exercise_id_resolved:
        # fallback para testes locais rápidos se não enviado via LTI
        exercise_id_resolved = "week_4_fatorial"
        
    exercise_id = exercise_id_resolved
    
    # Verifica se já foi passado o código no request (chamada automatizada ou via script)
    student_code = request.POST.get('custom_student_code')
    if student_code is not None:
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
        
        # Constrói o relatório detalhado no formato original (devolve texto puro)
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
        
        # Salva/atualiza submissão no banco de dados mesmo no modo direto
        submissao, _ = Submissao.objects.update_or_create(
            aluno=aluno,
            exercise_id=exercise_id,
            defaults={
                'nota': nota_final_10,
                'student_code': student_code,
                'resultado_json': json.dumps(resultado_avaliacao)
            }
        )
        
        # Envia a nota de volta para a plataforma EdX caso os parâmetros tenham sido enviados
        lis_outcome_service_url = request.POST.get('lis_outcome_service_url')
        lis_result_sourcedid = request.POST.get('lis_result_sourcedid')
        if lis_outcome_service_url and lis_result_sourcedid:
            enviar_nota_ao_edx(
                lis_outcome_service_url=lis_outcome_service_url,
                lis_result_sourcedid=lis_result_sourcedid,
                nota_decimal=resultado_avaliacao.get('nota', 0.0),
                client_key=client_key or LTI_KEY,
                client_secret=LTI_SECRET
            )
        
        # Imprime no log para depuração local do servidor
        print("\n=== FEEDBACK GERADO ===")
        print(feedback_text)
        print("=======================\n")
        
        return HttpResponse(feedback_text, content_type="text/plain; charset=utf-8", status=200)

    # 3. Caso contrário, renderiza a página HTML. 
    # Verifica se já existe uma submissão para este aluno e exercício
    try:
        submissao_salva = Submissao.objects.get(aluno=aluno, exercise_id=exercise_id)
        resultado_json = json.loads(submissao_salva.resultado_json)
        nota_10 = submissao_salva.nota
        student_code = submissao_salva.student_code
        passou_count = sum(1 for r in resultado_json.get('detalhes', []) if r.get('passou'))
        total_count = len(resultado_json.get('detalhes', []))
        
        # Adiciona peso formatado para exibição se necessário
        for r in resultado_json.get('detalhes', []):
            r['peso_exibicao'] = f"{r.get('peso', 0.0) * 10:.1f}"
    except Submissao.DoesNotExist:
        resultado_json = None
        nota_10 = 0.0
        student_code = ''
        passou_count = 0
        total_count = 0

    # Gera lti_token preservando a sessão de LTI
    lti_params = {
        'lis_result_sourcedid': sourcedid,
        'lis_outcome_service_url': request.POST.get('lis_outcome_service_url'),
        'custom_exercise_id': exercise_id,
        'oauth_consumer_key': client_key,
        'user_id': user_id,
    }
    lti_token = signing.dumps(lti_params)
    
    context = {
        'exercise_id': exercise_id,
        'lti_token': lti_token,
        'student_code': student_code,
        'resultado': resultado_json,
        'nota_10': nota_10,
        'passou_count': passou_count,
        'total_count': total_count,
    }
    return render(request, 'grader/index.html', context)


@csrf_exempt
def test_launcher_view(request):
    import time
    import uuid
    
    # 1. Carrega os exercícios disponíveis do tests.json
    caminho_tests_json = os.path.join(settings.BASE_DIR, 'tests.json')
    todos_exercicios = []
    if os.path.exists(caminho_tests_json):
        try:
            with open(caminho_tests_json, 'r', encoding='utf-8') as f:
                todos_exercicios = list(json.load(f).keys())
        except Exception:
            pass
            
    if not todos_exercicios:
        todos_exercicios = ["week_4_fatorial"]
        
    # 2. Determina o exercício ativo com base na query string (?exercise=...)
    exercise_id = request.GET.get('exercise', '')
    if exercise_id not in todos_exercicios:
        # Se não especificado ou inválido, usa o fatorial ou o primeiro da lista
        exercise_id = "week_4_fatorial" if "week_4_fatorial" in todos_exercicios else todos_exercicios[0]

    # Target URL
    target_url = request.build_absolute_uri('/lti/avaliacao/')
    
    # LTI parameters
    params = {
        'oauth_consumer_key': LTI_KEY,
        'oauth_signature_method': 'HMAC-SHA1',
        'oauth_timestamp': str(int(time.time())),
        'oauth_nonce': uuid.uuid4().hex,
        'oauth_version': '1.0',
        'lti_message_type': 'basic-lti-launch-request',
        'lti_version': 'LTI-1p0',
        'resource_link_id': exercise_id,
        'lis_result_sourcedid': 'aluno_test',
        'lis_outcome_service_url': 'https://dummy.edx.org/grades',
        'custom_exercise_id': exercise_id,
        'user_id': 'aluno_test', # Simula ID de usuário
    }
    
    # Calculate signature
    # 1. Escape and sort parameters
    encoded_params = [(escape(k), escape(v)) for k, v in params.items()]
    encoded_params.sort()
    param_string = "&".join([f"{k}={v}" for k, v in encoded_params])
    
    # 2. Base string
    base_string = "&".join([
        'POST',
        escape(target_url),
        escape(param_string)
    ])
    
    # 3. Signing key
    signing_key = escape(LTI_SECRET) + "&"
    
    # 4. Hash HMAC-SHA1
    hashed = hmac.new(
        signing_key.encode('utf-8'),
        base_string.encode('utf-8'),
        hashlib.sha1
    )
    
    signature = base64.b64encode(hashed.digest()).decode('utf-8')
    params['oauth_signature'] = signature
    
    # Opções do dropdown
    options_html = ""
    for ex in todos_exercicios:
        selected_attr = "selected" if ex == exercise_id else ""
        options_html += f'                    <option value="{ex}" {selected_attr}>{ex}</option>\n'
    
    # Render HTML page with a form that autosubmits to the target_url
    html_content = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Simulador de Lançamento LTI</title>
    <style>
        body {{ font-family: sans-serif; background-color: #0b0f19; color: white; display: flex; flex-direction: column; align-items: center; padding: 20px; margin: 0; min-height: 100vh; box-sizing: border-box; }}
        iframe {{ width: 100%; height: 80vh; border: 1px solid #374151; border-radius: 12px; background-color: #0b0f19; box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.3); }}
        .container {{ width: 100%; max-width: 1200px; display: flex; flex-direction: column; gap: 15px; }}
        .header {{ display: flex; justify-content: space-between; align-items: center; padding: 10px 0; border-bottom: 1px solid #374151; }}
        .controls {{ display: flex; align-items: center; gap: 15px; }}
        select {{ padding: 10px; background-color: #1f2937; border: 1px solid #374151; border-radius: 8px; color: white; cursor: pointer; font-weight: 500; }}
        button {{ padding: 10px 20px; background-color: #3b82f6; border: none; border-radius: 8px; color: white; font-weight: 600; cursor: pointer; transition: background-color 0.2s; }}
        button:hover {{ background-color: #2563eb; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div>
                <h1 style="margin: 0; font-size: 1.5rem; background: linear-gradient(to right, #60a5fa, #3b82f6); -webkit-background-clip: text; -webkit-text-fill-color: transparent;">LTI Simulator</h1>
                <p style="margin: 5px 0 0 0; font-size: 0.85rem; color: #9ca3af;">Simula o comportamento do iframe dentro da plataforma EdX</p>
            </div>
            <div class="controls">
                <select id="exerciseSelect" onchange="changeExercise(this.value)">
{options_html}                </select>
                <button onclick="document.getElementById('ltiForm').submit()">Reiniciar Iframe</button>
            </div>
        </div>
        
        <form id="ltiForm" action="{target_url}?exercise={exercise_id}" method="POST" target="ltiFrame">
"""
    for k, v in params.items():
        html_content += f'            <input type="hidden" name="{k}" value="{v}">\n'
        
    html_content += """        </form>
        <iframe name="ltiFrame" id="ltiFrame"></iframe>
    </div>
    <script>
        window.onload = function() {
            document.getElementById('ltiForm').submit();
        };
        function changeExercise(val) {
            window.location.href = '?exercise=' + val;
        }
    </script>
</body>
</html>
"""
    return HttpResponse(html_content, content_type="text/html; charset=utf-8")