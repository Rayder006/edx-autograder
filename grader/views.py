from django.conf import settings
import os
import json
import re
import urllib.parse
import hmac
import hashlib
import base64
import logging
import time
from datetime import datetime, timezone as datetime_timezone
import xml.etree.ElementTree as ET
import requests
from requests_oauthlib import OAuth1
from xml.sax.saxutils import escape as xml_escape
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.views.decorators.clickjacking import xframe_options_exempt
from django.core import signing
from django.shortcuts import render
from django.db import transaction
from django.utils import timezone
from .models import Aluno, Submissao, LTILaunchNonce
from .runner import avaliar_no_docker_com_json
from .pytest_runner import avaliar_com_pytest
from .catalog import exercises
from .submissions import (
    save_submission, saved_result, display_result, get_submission, lti_scope, lti_context,
    remember_lti_context,
)
from .lti_debug import (
    obter_lti_passports,
    log_lti_launch,
    log_lti_passback,
    comparar_launch_passback
)

logger = logging.getLogger(__name__)
LTI_KEY = os.environ.get('LTI_CONSUMER_KEY', 'minha_chave_edx_usp' if settings.DEBUG else '')
LTI_SECRET = os.environ.get('LTI_SHARED_SECRET', 'meu_segredo_super_seguro' if settings.DEBUG else '')


def escape(text):
    """Codificação RFC 3986 (O padrão exigido pela matemática do OAuth 1.0)"""
    return urllib.parse.quote(str(text), safe='~')


def executar_avaliacao(student_code, exercise_id, config_exercicio):
    """
    Ponto central de despacho do motor de correção.

    Por padrão usa o motor Pytest (exercises/test_<exercise_id>.py).
    O motor legado só é selecionado explicitamente com AUTOGRADER_ENGINE=docker.
    """
    engine = os.environ.get("AUTOGRADER_ENGINE", "pytest")
    if engine == "pytest":
        return avaliar_com_pytest(student_code, exercise_id)
    if engine == 'docker' and config_exercicio:
        return avaliar_no_docker_com_json(student_code, config_exercicio)
    return {'sucesso': False, 'nota': 0, 'detalhes': [], 'baterias': [],
            'erro': 'Motor de correção ou exercício não configurado.'}

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
            return False

    import uuid
    message_id = uuid.uuid4().hex
    sourced_id = xml_escape(str(lis_result_sourcedid))

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
    dry_run = settings.DEBUG and os.environ.get('LTI_PASSBACK_DRY_RUN', '0') == '1'

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
    try:
        prepared = req.prepare()
    except (ValueError, requests.RequestException):
        logger.exception('Não foi possível preparar o retorno de nota LTI.')
        return False

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
            with requests.Session() as session:
                # PreparedRequest não incorpora sozinho REQUESTS_CA_BUNDLE nem
                # as configurações de proxy da infraestrutura.
                environment = session.merge_environment_settings(
                    prepared.url, {}, None, None, None,
                )
                response = session.send(
                    prepared, timeout=15, allow_redirects=False, **environment,
                )
            
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
                
            try:
                root = ET.fromstring(response.content)
            except ET.ParseError:
                return False
            if root.tag.rsplit('}', 1)[-1] != 'imsx_POXEnvelopeResponse':
                return False
            statuses = root.findall('.//{*}imsx_statusInfo/{*}imsx_codeMajor')
            return len(statuses) == 1 and (statuses[0].text or '').strip() == 'success'
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


def _passback(params, submission):
    url = params.get('lis_outcome_service_url')
    sourcedid = params.get('lis_result_sourcedid')
    if not url or not sourcedid:
        return None
    # Serializa passbacks do mesmo aluno/exercício. Uma resposta lenta de uma
    # tentativa anterior não pode sobrescrever uma nota melhor no EdX.
    with transaction.atomic():
        current = Submissao.objects.select_for_update().get(pk=submission.pk)
        score = current.maior_nota / 10.0
        if settings.DEBUG and os.environ.get('LTI_FORCE_EVALUATION_SCORE'):
            score = float(os.environ['LTI_FORCE_EVALUATION_SCORE'])
        current.lti_context = lti_context(params)
        current.passback_attempted_at = timezone.now()
        try:
            success = enviar_nota_ao_edx(url, sourcedid, score, params.get('oauth_consumer_key'))
        except Exception:
            logger.exception('Falha inesperada no retorno de nota LTI.')
            success = False
        current.passback_success = success
        if success:
            current.passback_score = score
        current.save(update_fields=[
            'lti_context', 'passback_attempted_at', 'passback_success', 'passback_score',
        ])
    if not success:
        logger.warning('O EdX não confirmou o recebimento da nota.')
    return success


def _render_submission(request, params, token, code='', result=None, submission=None,
                       passback_status=None, status=200):
    if passback_status is None and submission and submission.lti_context == lti_context(params):
        passback_status = submission.passback_success
        if submission.passback_score != submission.maior_nota / 10.0 and passback_status:
            passback_status = None
    result = display_result(result) if result is not None else None
    details = result.get('detalhes', []) if result else []
    return render(request, 'grader/index.html', {
        'exercise_id': params['custom_exercise_id'],
        'exercise_name': obter_nome_exibicao(params['custom_exercise_id']),
        'lti_token': token,
        'student_code': code,
        'resultado': result,
        'nota_10': round(result.get('nota', 0) * 10, 1) if result else 0,
        'maior_nota': round(submission.maior_nota, 1) if submission else 0,
        'nota_maxima': bool(submission and submission.maior_nota >= 10),
        'passou_count': sum(1 for case in details if case.get('passou')),
        'total_count': len(details),
        'passback_failed': passback_status is False,
        'can_retry_passback': bool(
            submission and params.get('lis_outcome_service_url')
            and params.get('lis_result_sourcedid') and passback_status is not True
        ),
    }, status=status)


def _valid_launch(request):
    from oauthlib.oauth1.rfc5849.signature import base_string_uri

    key = request.POST.get('oauth_consumer_key')
    secret = obter_lti_passports().get(key) or (LTI_SECRET if key and key == LTI_KEY else None)
    bypass = settings.DEBUG and os.environ.get('LTI_BYPASS_SIGNATURE_VERIFICATION') == '1'
    if not secret and not bypass:
        return False
    if bypass:
        return True
    if request.POST.get('oauth_signature_method') != 'HMAC-SHA1':
        return False
    received = request.POST.get('oauth_signature', '')
    params = [
        (escape(key), escape(value))
        for query in (request.GET, request.POST)
        for key, values in query.lists() if key != 'oauth_signature'
        for value in values
    ]
    params.sort()
    normalized = '&'.join(f'{key}={value}' for key, value in params)
    base = '&'.join([
        request.method.upper(), escape(base_string_uri(request.build_absolute_uri())),
        escape(normalized),
    ])
    expected = base64.b64encode(hmac.new(
        (escape(secret) + '&').encode(), base.encode(), hashlib.sha1
    ).digest()).decode()
    valid = hmac.compare_digest(expected.encode(), received.encode())
    log_lti_launch(request, dict(request.POST.items()), valid)
    if not valid:
        return False
    # Uma assinatura correta sem timestamp/nonce verificados pode ser repetida
    # indefinidamente. O banco faz a deduplicação entre todos os workers.
    nonce = request.POST.get('oauth_nonce', '')
    try:
        timestamp = int(request.POST.get('oauth_timestamp', ''))
    except (TypeError, ValueError):
        return False
    tolerance = 90 * 60  # Janela recomendada pelo guia LTI 1.1.
    now = time.time()
    if not nonce or len(nonce) > 1024 or abs(now - timestamp) > tolerance:
        logger.warning('Launch LTI com nonce ausente ou timestamp inválido/expirado. Confira o relógio do servidor.')
        return False
    digest = hashlib.sha256(json.dumps([key, nonce]).encode()).hexdigest()
    LTILaunchNonce.objects.filter(expires_at__lte=timezone.now()).delete()
    _, created = LTILaunchNonce.objects.get_or_create(
        digest=digest,
        defaults={'expires_at': datetime.fromtimestamp(timestamp + tolerance, datetime_timezone.utc)},
    )
    return created


@csrf_exempt
@xframe_options_exempt
@require_POST
def lti_grade_endpoint(request, course_id=None, exercise_id=None):
    token = request.POST.get('lti_token')
    is_form = bool(token)
    if is_form:
        try:
            params = signing.loads(token, max_age=3600)
        except signing.SignatureExpired:
            return HttpResponse('A sessão expirou. Recarregue a página no EdX.', status=403)
        except signing.BadSignature:
            return HttpResponse('Assinatura de sessão inválida.', status=403)
        if not isinstance(params, dict):
            return HttpResponse('Sessão LTI inválida.', status=403)
        exercise_id = params.get('custom_exercise_id')
        user_id = params.get('user_id')
    else:
        if not _valid_launch(request):
            return HttpResponse('Acesso negado: chave ou assinatura LTI inválida.', status=403)
        exercise_id = (
            exercise_id or request.GET.get('exercise')
            or request.POST.get('custom_exercise_id') or request.POST.get('resource_link_id')
        )
        user_id = request.POST.get('user_id') or request.POST.get('lis_result_sourcedid')
        params = {
            key: request.POST.get(key) for key in (
                'lis_result_sourcedid', 'lis_outcome_service_url', 'oauth_consumer_key',
                'context_id', 'resource_link_id',
            )
        }
        params.update(custom_exercise_id=exercise_id, user_id=user_id)
        token = signing.dumps(params)

    if not user_id or len(user_id) > 255:
        return HttpResponse('O launch LTI precisa identificar o aluno (user_id).', status=400)
    if not isinstance(exercise_id, str) or not re.fullmatch(r'[A-Za-z0-9_]+', exercise_id):
        return HttpResponse('Identificador de exercício inválido.', status=400)
    try:
        catalog = exercises()
    except (OSError, ValueError):
        logger.exception('Falha ao carregar o catálogo de exercícios.')
        return HttpResponse('O catálogo de exercícios está indisponível. Avise o professor.', status=503)
    if exercise_id not in catalog:
        return HttpResponse('Exercício não configurado no autograder.', status=400)

    aluno, _ = Aluno.objects.get_or_create(user_id=user_id)
    scope = lti_scope(params)
    submission = get_submission(aluno, exercise_id, scope)
    if submission and not is_form:
        submission = remember_lti_context(submission, params)
    is_submission = is_form or 'custom_student_code' in request.POST
    if not is_submission:
        return _render_submission(
            request, params, token,
            code=submission.student_code if submission else '',
            result=saved_result(submission) if submission else None,
            submission=submission,
        )

    # Uma nota máxima não deve impedir a retransmissão de um passback que falhou.
    reuse = submission and (
        submission.maior_nota >= 10 or request.POST.get('retry_passback') == '1'
    )
    if reuse:
        result = saved_result(submission)
        code = submission.student_code
    else:
        code = request.POST.get('custom_student_code', '')
        if 'code_file' in request.FILES:
            if request.FILES['code_file'].size > 256 * 1024:
                return HttpResponse('O arquivo Python deve ter no máximo 256 KiB.', status=413)
            try:
                code = request.FILES['code_file'].read().decode('utf-8-sig')
            except UnicodeDecodeError:
                return HttpResponse('O arquivo Python deve usar codificação UTF-8.', status=400)
        if len(code.encode('utf-8')) > 256 * 1024:
            return HttpResponse('O código Python deve ter no máximo 256 KiB.', status=413)
        if not code.strip():
            return HttpResponse('Envie um código Python para correção.', status=400)
        try:
            result = executar_avaliacao(code, exercise_id, catalog[exercise_id])
            if not isinstance(result, dict):
                raise ValueError('O avaliador não retornou um relatório.')
        except Exception:
            logger.exception('Falha no motor de avaliação para %s.', exercise_id)
            result = {
                'sucesso': False, 'nota': 0, 'detalhes': [], 'baterias': [],
                'erro': 'O corretor está indisponível. Avise o professor e tente novamente.',
            }
        if not result.get('sucesso', True):
            # Uma falha operacional não é uma tentativa errada do aluno.
            if is_form:
                return _render_submission(
                    request, params, token, code, result, submission, status=503,
                )
            return HttpResponse(result.get('erro', 'Falha no corretor.'), status=503)
        try:
            submission = save_submission(aluno, exercise_id, code, result, scope=scope, params=params)
        except (ValueError, TypeError, KeyError):
            logger.exception('O avaliador retornou uma nota inválida para %s.', exercise_id)
            return HttpResponse('O corretor retornou um resultado inválido. Avise o professor.', status=503)

    passback_status = _passback(params, submission)
    if is_form:
        return _render_submission(
            request, params, token, code, result, submission, passback_status,
        )
    lines = ['O resultado dos testes com seu programa foi:']
    for battery in result.get('baterias', []):
        state = 'Passou' if battery['passou'] else 'Falhou'
        lines.append(f"Bateria {battery['descricao']} [{battery['peso'] * 10:.1f} pontos]: {state}")
    for case in result.get('detalhes', []):
        state = 'Passou' if case.get('passou') else 'Falhou'
        lines.append(f"{case.get('descricao', 'Teste')}: {state}")
        if case.get('erro'):
            lines.append(case['erro'])
    if result.get('erro'):
        lines.append(result['erro'])
    lines.append(f"Nota Final: {round(result['nota'] * 10, 1)}/10.0")
    lines.append(f'Maior nota: {submission.maior_nota}/10.0')
    if passback_status is False:
        lines.append('A nota foi salva, mas o EdX não confirmou o recebimento. Envie novamente para retransmitir.')
    return HttpResponse('\n'.join(lines), content_type='text/plain; charset=utf-8')

@csrf_exempt
def test_launcher_view(request):
    if not settings.DEBUG:
        return HttpResponse('Não encontrado.', status=404)
    import time
    import uuid
    
    # O simulador usa o mesmo catálogo da aplicação.
    todos_exercicios = list(exercises())
            
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
    encoded_params.append((escape('exercise'), escape(exercise_id)))
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
    from django.utils.html import escape as html_escape
    for k, v in params.items():
        html_content += f'            <input type="hidden" name="{html_escape(k)}" value="{html_escape(v)}">\n'
        
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
