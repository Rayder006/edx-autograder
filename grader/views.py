from django.conf import settings
import os
import json
import re
import urllib.parse
import hmac
import hashlib
import base64
import requests
from requests_oauthlib import OAuth1
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.views.decorators.clickjacking import xframe_options_exempt
from django.core import signing
from django.shortcuts import render
from .models import Aluno, Submissao
from .runner import avaliar_no_docker_com_json
from .pytest_runner import avaliar_com_pytest
from .lti_debug import (
    obter_lti_passports,
    log_lti_launch,
    log_lti_passback,
    comparar_launch_passback
)

LTI_KEY = os.environ.get('LTI_CONSUMER_KEY', 'minha_chave_edx_usp')
LTI_SECRET = os.environ.get('LTI_SHARED_SECRET', 'meu_segredo_super_seguro')


def escape(text):
    """Codificação RFC 3986 (O padrão exigido pela matemática do OAuth 1.0)"""
    return urllib.parse.quote(str(text), safe='~')


def executar_avaliacao(student_code, exercise_id, config_exercicio):
    """
    Ponto central de despacho do motor de correção.

    Por padrão usa o motor Pytest (exercises/test_<exercise_id>.py).
    Faz fallback para o motor Docker legado se:
      - AUTOGRADER_ENGINE=docker (variável de ambiente), ou
      - não existir arquivo de teste Pytest para o exercício.
    """
    engine = os.environ.get("AUTOGRADER_ENGINE", "pytest")
    if engine == "pytest":
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        test_spec_path = os.path.join(base_dir, "exercises", f"test_{exercise_id}.py")
        if os.path.exists(test_spec_path):
            return avaliar_com_pytest(student_code, exercise_id)

    # Fallback: motor Docker com JSON
    return avaliar_no_docker_com_json(student_code, config_exercicio)

def enviar_nota_ao_edx(
    lis_outcome_service_url,
    lis_result_sourcedid,
    nota_decimal,
    client_key,
    client_secret=None
):
    """
    Envia a nota do aluno ao LMS via LTI 1.1 Basic Outcomes Service.
    nota_decimal deve estar no intervalo [0.0, 1.0].
    """

    if not lis_outcome_service_url or not lis_result_sourcedid:
        print(
            "LTI Outcomes: lis_outcome_service_url ou "
            "lis_result_sourcedid não informados."
        )
        return False

    # Valida limites do score
    try:
        score_float = float(nota_decimal)
        if not (0.0 <= score_float <= 1.0):
            print(f"LTI Outcomes ERROR: score out of bounds: raw={nota_decimal}, float={score_float}")
            return False
    except (ValueError, TypeError) as e:
        print(f"LTI Outcomes ERROR: invalid score type: {e}")
        return False

    # Resolve secret
    if not client_secret:
        passports = obter_lti_passports()
        if client_key in passports:
            client_secret = passports[client_key]
        elif client_key == LTI_KEY:
            client_secret = LTI_SECRET
        else:
            client_secret = LTI_SECRET  # fallback

    import uuid
    message_id = uuid.uuid4().hex
    sourced_id = lis_result_sourcedid

    xml_data = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<imsx_POXEnvelopeRequest '
        'xmlns="http://www.imsglobal.org/services/ltiv1p1/xsd/imsoms_v1p0">'
        '<imsx_POXHeader>'
        '<imsx_POXRequestHeaderInfo>'
        '<imsx_version>V1.0</imsx_version>'
        f'<imsx_messageIdentifier>{message_id}</imsx_messageIdentifier>'
        '</imsx_POXRequestHeaderInfo>'
        '</imsx_POXHeader>'
        '<imsx_POXBody>'
        '<replaceResultRequest>'
        '<resultRecord>'
        '<sourcedGUID>'
        f'<sourcedId>{sourced_id}</sourcedId>'
        '</sourcedGUID>'
        '<result>'
        '<resultScore>'
        '<language>en</language>'
        f'<textString>{score_float:.4f}</textString>'
        '</resultScore>'
        '</result>'
        '</resultRecord>'
        '</replaceResultRequest>'
        '</imsx_POXBody>'
        '</imsx_POXEnvelopeRequest>'
    )

    encoded_xml = xml_data.encode("utf-8")
    dry_run = os.environ.get('LTI_PASSBACK_DRY_RUN', '0') == '1'

    # Configura OAuth 1.0a
    auth = OAuth1(
        client_key,
        client_secret,
        signature_method="HMAC-SHA1",
        force_include_body=True,
        decoding=None,
    )

    headers = {
        "Content-Type": "application/xml",
    }

    # Prepara a requisição localmente para obter os headers e oauth_body_hash assinados
    req = requests.Request(
        'POST',
        lis_outcome_service_url,
        data=encoded_xml,
        headers=headers,
        auth=auth
    )
    prepared = req.prepare()

    # Extrai parâmetros OAuth dos headers assinados para depuração
    auth_header = prepared.headers.get('Authorization', '')
    oauth_params = {}
    if auth_header:
        matches = re.findall(r'(oauth_[a-z_]+)="([^"]+)"', auth_header)
        for k, v in matches:
            oauth_params[k] = urllib.parse.unquote(v)

    response = None
    try:
        if not dry_run:
            session = requests.Session()
            response = session.send(prepared, timeout=15)
            
            # Executa log do passback com resposta
            log_lti_passback(
                lis_outcome_service_url,
                lis_result_sourcedid,
                nota_decimal,
                client_key,
                xml_data,
                response,
                oauth_params,
                dry_run=False
            )
            
            if response.status_code != 200:
                return False
                
            return (
                "<imsx_codeMajor>success</imsx_codeMajor>" in response.text
                or "<imsx_codeMajor>\nsuccess\n</imsx_codeMajor>" in response.text
            )
        else:
            # Em modo dry-run apenas registra o log e retorna sucesso
            log_lti_passback(
                lis_outcome_service_url,
                lis_result_sourcedid,
                nota_decimal,
                client_key,
                xml_data,
                None,
                oauth_params,
                dry_run=True
            )
            return True

    except requests.RequestException as e:
        print(f"LTI Outcomes: erro HTTP: {e}", flush=True)
        return False

    except Exception as e:
        print(f"LTI Outcomes: erro inesperado: {e}", flush=True)
        return False

def obter_nome_exibicao(exercise_id):
    """
    Converte chaves internas como 'week_4_fatorial' para nomes legíveis de exibição como 'Fatorial'.
    'week_7_retangulo_cheio' -> 'Retangulo Cheio'.
    """
    if not exercise_id:
        return ""
    parts = exercise_id.split('_')
    if len(parts) > 2 and parts[0] == 'week' and parts[1].isdigit():
        return '_'.join(parts[2:]).replace('_', ' ').title()
    return exercise_id.replace('_', ' ').title()


@csrf_exempt
@xframe_options_exempt
@require_POST
def lti_grade_endpoint(request, course_id=None, exercise_id=None):
    # 1. Verifica se é uma submissão via formulário HTML (possui lti_token)
    lti_token = request.POST.get('lti_token')
    print(request.POST)
    
    if lti_token:
        try:
            # Descriptografa e valida os dados de sessão LTI
            lti_params = signing.loads(lti_token, max_age=3600)  # Válido por 1 hora
        except signing.SignatureExpired:
            return HttpResponse("A sessão expirou. Por favor, recarregue a página no EdX.", status=403)
        except signing.BadSignature:
            return HttpResponse("Assinatura de sessão inválida.", status=403)
            
        print(lti_params.items())
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
            if submissao_existente.maior_nota >= 10.0:
                resultado_avaliacao = submissao_existente.resultado_json if isinstance(submissao_existente.resultado_json, dict) else json.loads(submissao_existente.resultado_json)
                
                # Adiciona peso formatado para exibição se necessário
                for r in resultado_avaliacao.get('detalhes', []):
                    r['peso_exibicao'] = f"{r.get('peso', 0.0) * 10:.1f}"
                    
                context = {
                    'exercise_id': exercise_id,
                    'exercise_name': obter_nome_exibicao(exercise_id),
                    'lti_token': lti_token,
                    'student_code': submissao_existente.student_code,
                    'resultado': resultado_avaliacao,
                    'nota_10': submissao_existente.maior_nota,
                    'passou_count': len(resultado_avaliacao.get('detalhes', [])),
                    'total_count': len(resultado_avaliacao.get('detalhes', [])),
                }
                return render(request, 'grader/index.html', context)
        except Submissao.DoesNotExist:
            pass

        # Executa a avaliação (Pytest Runner por padrão, ou fallback Docker)
        resultado_avaliacao = executar_avaliacao(student_code, exercise_id, config_exercicio)
        
        # Prepara estatísticas de exibição e nota
        nota_10 = round(resultado_avaliacao['nota'] * 10, 1)
        passou_count = sum(1 for r in resultado_avaliacao['detalhes'] if r.get('passou'))
        total_count = len(resultado_avaliacao['detalhes'])
        
        # Salva ou atualiza a submissão no banco de dados local com maior_nota e tentativas
        submissao_existente = Submissao.objects.filter(aluno=aluno, exercise_id=exercise_id).first()
        if submissao_existente:
            maior_nota = max(nota_10, submissao_existente.maior_nota)
            submissao_existente.nota = nota_10
            submissao_existente.maior_nota = maior_nota
            submissao_existente.tentativas = submissao_existente.tentativas + 1
            submissao_existente.student_code = student_code
            submissao_existente.resultado_json = resultado_avaliacao
            submissao_existente.save()
            submissao = submissao_existente
        else:
            submissao = Submissao.objects.create(
                aluno=aluno,
                exercise_id=exercise_id,
                nota=nota_10,
                maior_nota=nota_10,
                tentativas=1,
                student_code=student_code,
                resultado_json=resultado_avaliacao
            )
        
        # Envia a nota de volta para a plataforma EdX
        lis_outcome_service_url = lti_params.get('lis_outcome_service_url')
        lis_result_sourcedid = lti_params.get('lis_result_sourcedid')
        oauth_consumer_key = lti_params.get('oauth_consumer_key') or LTI_KEY
        
        # Resolve secret dynamically
        passports = obter_lti_passports()
        client_secret = None
        if oauth_consumer_key in passports:
            client_secret = passports[oauth_consumer_key]
        elif oauth_consumer_key == LTI_KEY:
            client_secret = LTI_SECRET
        else:
            client_secret = LTI_SECRET
            
        nota_enviar = submissao.maior_nota / 10.0
        if os.environ.get('LTI_FORCE_EVALUATION_SCORE'):
            nota_enviar = float(os.environ.get('LTI_FORCE_EVALUATION_SCORE'))

        # Comparador Launch vs Passback
        passback_params = {
            'oauth_consumer_key': oauth_consumer_key,
            'lis_result_sourcedid': lis_result_sourcedid,
            'lis_outcome_service_url': lis_outcome_service_url,
            'user_id': user_id,
            'context_id': lti_params.get('context_id'),
            'custom_exercise_id': exercise_id,
        }
        comparar_launch_passback(lti_params, passback_params)

        enviar_nota_ao_edx(
            lis_outcome_service_url=lis_outcome_service_url,
            lis_result_sourcedid=lis_result_sourcedid,
            nota_decimal=nota_enviar,
            client_key=oauth_consumer_key,
            client_secret=client_secret
        )
        
        # Adiciona peso na escala 0-10 para facilitar a renderização no template
        for r in resultado_avaliacao['detalhes']:
            r['peso_exibicao'] = f"{r.get('peso', 0.0) * 10:.1f}"
            
        context = {
            'exercise_id': exercise_id,
            'exercise_name': obter_nome_exibicao(exercise_id),
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
    
    # Resolve secret dynamically
    passports = obter_lti_passports()
    client_secret = None
    if client_key in passports:
        client_secret = passports[client_key]
    elif client_key == LTI_KEY:
        client_secret = LTI_SECRET
        
    if not client_secret:
        if os.environ.get('LTI_BYPASS_SIGNATURE_VERIFICATION') == '1':
            client_secret = LTI_SECRET
        else:
            return HttpResponse("Chave LTI não reconhecida.", status=403)
        
    if not received_signature and os.environ.get('LTI_BYPASS_SIGNATURE_VERIFICATION') != '1':
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
        escape(uri.split('?')[0]), # RFC 5849: path is case-sensitive, do not lowercase
        escape(param_string)
    ])
    
    # A Chave de Assinatura (Consumer Secret + "&" + Token Secret que no LTI é vazio)
    signing_key = escape(client_secret) + "&"
    
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

    signature_ok = False
    if os.environ.get('LTI_BYPASS_SIGNATURE_VERIFICATION') == '1':
        signature_ok = True
    elif received_signature:
        signature_ok = hmac.compare_digest(expected_signature.encode(), received_signature.encode())
        
    # Log the launch debug details
    params_dict = dict(request.POST.items())
    log_lti_launch(request, params_dict, signature_ok)

    if not signature_ok:
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
        
        # Chama o motor de avaliação (Pytest ou Docker)
        resultado_avaliacao = executar_avaliacao(student_code, exercise_id, config_exercicio)
        
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
            # Resolve secret dynamically
            passports = obter_lti_passports()
            client_secret = None
            if client_key in passports:
                client_secret = passports[client_key]
            elif client_key == LTI_KEY:
                client_secret = LTI_SECRET
            else:
                client_secret = LTI_SECRET
                
            nota_enviar = resultado_avaliacao.get('nota', 0.0)
            if os.environ.get('LTI_FORCE_EVALUATION_SCORE'):
                nota_enviar = float(os.environ.get('LTI_FORCE_EVALUATION_SCORE'))

            # Direct compare logs
            launch_params_direct = {
                'oauth_consumer_key': client_key or LTI_KEY,
                'lis_result_sourcedid': lis_result_sourcedid,
                'lis_outcome_service_url': lis_outcome_service_url,
                'user_id': user_id,
                'context_id': request.POST.get('context_id'),
                'custom_exercise_id': exercise_id,
            }
            comparar_launch_passback(launch_params_direct, launch_params_direct)

            enviar_nota_ao_edx(
                lis_outcome_service_url=lis_outcome_service_url,
                lis_result_sourcedid=lis_result_sourcedid,
                nota_decimal=nota_enviar,
                client_key=client_key or LTI_KEY,
                client_secret=client_secret
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
        resultado_json = submissao_salva.resultado_json if isinstance(submissao_salva.resultado_json, dict) else json.loads(submissao_salva.resultado_json)
        nota_10 = submissao_salva.maior_nota
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
        'context_id': request.POST.get('context_id'),
        'resource_link_id': request.POST.get('resource_link_id'),
    }
    lti_token = signing.dumps(lti_params)
    
    context = {
        'exercise_id': exercise_id,
        'exercise_name': obter_nome_exibicao(exercise_id),
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
    return HttpResponse(html_content, content_type="text/html; charset=utf-8", status=200)
