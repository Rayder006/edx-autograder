import os
import json
import time
import urllib.parse
import hashlib
import base64
from django.conf import settings

def mascarar_id(val):
    if not val:
        return ""
    if len(val) <= 8:
        return "****"
    return f"{val[:6]}...{val[-6:]}"

def mascarar_sourcedid(sourcedid):
    if not sourcedid:
        return ""
    parts = sourcedid.split(':')
    if len(parts) >= 3:
        parts[-1] = mascarar_id(parts[-1])
        return ':'.join(parts)
    return mascarar_id(sourcedid)

def obter_lti_passports():
    passports_env = os.environ.get('LTI_PASSPORTS', '')
    if not passports_env:
        return {}
    
    # Try parsing as JSON first
    try:
        parsed = json.loads(passports_env)
        if isinstance(parsed, dict):
            return {k.strip(): v.strip() for k, v in parsed.items()}
    except json.JSONDecodeError:
        pass
        
    # Try parsing as edX passport format: "id:key:secret, id2:key2:secret2"
    passports = {}
    parts = passports_env.split(',')
    for part in parts:
        part = part.strip()
        if not part:
            continue
        subparts = part.split(':')
        if len(subparts) >= 3:
            k = subparts[1].strip()
            v = ':'.join(subparts[2:]).strip()
            passports[k] = v
    return passports

def log_lti_launch(request, params, signature_ok):
    print("\n" + "="*60, flush=True)
    print("=== LTI LAUNCH DEBUG ===", flush=True)
    print(f"Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}", flush=True)
    print(f"Request Method: {request.method}", flush=True)
    print(f"Request Path: {request.path}", flush=True)
    print(f"Request Full URL: {request.build_absolute_uri()}", flush=True)
    
    # Masked values
    user_id = params.get('user_id', '')
    sourcedid = params.get('lis_result_sourcedid', '')
    
    print(f"Signature Verification: {'SUCCESS' if signature_ok else 'FAILED'}", flush=True)
    print(f"oauth_consumer_key: {params.get('oauth_consumer_key')}", flush=True)
    print(f"oauth_signature_method: {params.get('oauth_signature_method')}", flush=True)
    print(f"oauth_timestamp: {params.get('oauth_timestamp')}", flush=True)
    print(f"oauth_nonce: {params.get('oauth_nonce')}", flush=True)
    print(f"oauth_version: {params.get('oauth_version')}", flush=True)
    print(f"lti_message_type: {params.get('lti_message_type')}", flush=True)
    print(f"lti_version: {params.get('lti_version')}", flush=True)
    print(f"resource_link_id: {params.get('resource_link_id')}", flush=True)
    print(f"context_id: {params.get('context_id')}", flush=True)
    print(f"context_title: {params.get('context_title')}", flush=True)
    print(f"user_id: {mascarar_id(user_id)}", flush=True)
    print(f"lis_result_sourcedid: {mascarar_sourcedid(sourcedid)}", flush=True)
    print(f"lis_outcome_service_url: {params.get('lis_outcome_service_url')}", flush=True)
    print("="*60 + "\n", flush=True)

def log_lti_passback(
    lis_outcome_service_url,
    lis_result_sourcedid,
    nota_decimal,
    client_key,
    xml_data,
    response,
    oauth_params=None,
    dry_run=False
):
    print("\n" + "="*60, flush=True)
    print("=== LTI OUTCOMES PASSBACK DEBUG ===", flush=True)
    print(f"TIMESTAMP: {time.strftime('%Y-%m-%d %H:%M:%S')}", flush=True)
    print(f"DRY RUN: {dry_run}", flush=True)
    
    # Try parsing context information from sourcedid
    course_context = ""
    user_id_masked = ""
    if lis_result_sourcedid:
        parts = lis_result_sourcedid.split(':')
        if len(parts) >= 1:
            course_context = parts[0]
        if len(parts) >= 3:
            user_id_masked = mascarar_id(parts[-1])
            
    print(f"COURSE/CONTEXT: {course_context}", flush=True)
    print(f"LTI CONSUMER KEY: {client_key}", flush=True)
    print(f"OUTCOME SERVICE URL: {lis_outcome_service_url}", flush=True)
    print(f"LIS RESULT SOURCEDID: {mascarar_sourcedid(lis_result_sourcedid)}", flush=True)
    print(f"USER ID (derived): {user_id_masked}", flush=True)
    print(f"SCORE RAW: {nota_decimal}", flush=True)
    print(f"SCORE NORMALIZED: {float(nota_decimal):.4f}", flush=True)
    
    encoded_xml = xml_data.encode('utf-8')
    print(f"XML BYTE LENGTH: {len(encoded_xml)}", flush=True)
    print(f"XML SHA1: {hashlib.sha1(encoded_xml).hexdigest()}", flush=True)
    print("CONTENT-TYPE: application/xml", flush=True)
    
    # OAuth headers detail
    if oauth_params:
        print("OAUTH:", flush=True)
        for k, v in sorted(oauth_params.items()):
            # Mask signature in logs just in case
            if k == 'oauth_signature':
                print(f"  {k}: {mascarar_id(v)}", flush=True)
            else:
                print(f"  {k}: {v}", flush=True)
                
    print(f"REQUEST URL: {lis_outcome_service_url}", flush=True)
    print(f"REQUEST BODY:\n{xml_data}", flush=True)
    
    if dry_run:
        print("HTTP RESPONSE: [NOT SENT - DRY RUN]", flush=True)
    elif response is not None:
        print(f"HTTP RESPONSE:", flush=True)
        print(f"  status={response.status_code}", flush=True)
        print(f"  reason={response.reason}", flush=True)
        print(f"  content-type={response.headers.get('Content-Type')}", flush=True)
        print(f"  content-length={response.headers.get('Content-Length')}", flush=True)
        
        # Check redirect history
        if response.history:
            print("  REDIRECT HISTORY:", flush=True)
            for idx, resp in enumerate(response.history):
                print(f"    [{idx}] {resp.status_code} to {resp.url}", flush=True)
        
        # Truncate and clean HTML body if returned
        body = response.text
        print(f"RESPONSE BODY:\n{body[:500]}...", flush=True)
        
        if response.headers.get('Content-Type', '').startswith('text/html'):
            # Simple extractor of title or main header from HTML
            import re
            title_match = re.search(r'<title>(.*?)</title>', body, re.IGNORECASE)
            h1_match = re.search(r'<h1>(.*?)</h1>', body, re.IGNORECASE)
            body_text_match = re.search(r'<body[^>]*>(.*?)</body>', body, re.IGNORECASE | re.DOTALL)
            
            extracted_text = []
            if title_match:
                extracted_text.append(f"Title: {title_match.group(1).strip()}")
            if h1_match:
                extracted_text.append(f"Header: {h1_match.group(1).strip()}")
            if len(extracted_text) == 0 and body_text_match:
                # Get plain text from body match, stripping tags
                clean_text = re.sub(r'<[^>]+>', ' ', body_text_match.group(1))
                clean_lines = [line.strip() for line in clean_text.split('\n') if line.strip()]
                extracted_text.append("Snippet: " + " ".join(clean_lines)[:200])
                
            print(f"RESPONSE BODY EXTRACTED TEXT:\n" + "\n".join(extracted_text), flush=True)
    else:
        print("HTTP RESPONSE: None (Connection failed)", flush=True)
        
    print("="*60 + "\n", flush=True)

def comparar_launch_passback(launch_params, passback_params):
    print("\n" + "="*60, flush=True)
    print("=== LAUNCH vs PASSBACK COMPARISON ===", flush=True)
    
    comparisons = [
        ('oauth_consumer_key', launch_params.get('oauth_consumer_key'), passback_params.get('oauth_consumer_key')),
        ('lis_result_sourcedid', launch_params.get('lis_result_sourcedid'), passback_params.get('lis_result_sourcedid')),
        ('lis_outcome_service_url', launch_params.get('lis_outcome_service_url'), passback_params.get('lis_outcome_service_url')),
        ('user_id', launch_params.get('user_id'), passback_params.get('user_id')),
        ('context_id', launch_params.get('context_id'), passback_params.get('context_id')),
        ('custom_exercise_id', launch_params.get('custom_exercise_id'), passback_params.get('custom_exercise_id')),
    ]
    
    has_warning = False
    print(f"{'FIELD':<30} | {'LAUNCH':<35} | {'PASSBACK':<35}", flush=True)
    print("-"*110, flush=True)
    
    for field, l_val, p_val in comparisons:
        # Mask sensitive outputs
        l_display = mascarar_sourcedid(l_val) if field == 'lis_result_sourcedid' else (mascarar_id(l_val) if field == 'user_id' else str(l_val))
        p_display = mascarar_sourcedid(p_val) if field == 'lis_result_sourcedid' else (mascarar_id(p_val) if field == 'user_id' else str(p_val))
        
        status = "OK"
        if l_val != p_val:
            status = "!!! WARNING !!! Differs"
            has_warning = True
            
        print(f"{field:<30} | {l_display:<35} | {p_display:<35} | {status}", flush=True)
        
    if has_warning:
        print("\n!!! WARNING !!! Discrepancies detected between Launch and Passback parameters.", flush=True)
    else:
        print("\nOK: Outcome parameters match Launch parameters.", flush=True)
    print("="*60 + "\n", flush=True)

def executar_replay(replay_file_path, code=None, score=1.0):
    """
    Carrega os dados de launch salvos, simula o launch e o passback localmente.
    """
    if not os.path.exists(replay_file_path):
        print(f"Erro: Arquivo de replay {replay_file_path} não encontrado.", flush=True)
        return False
        
    try:
        with open(replay_file_path, 'r', encoding='utf-8') as f:
            launch_data = json.load(f)
    except Exception as e:
        print(f"Erro ao carregar JSON de replay: {e}", flush=True)
        return False
        
    print(f"Iniciando REPLAY a partir de {replay_file_path}...", flush=True)
    
    from django.test import Client
    client = Client()
    
    # 1. Simula Launch
    launch_url = '/lti/avaliacao/'
    # Preserva parâmetros LTI
    post_data = {
        'oauth_consumer_key': launch_data.get('oauth_consumer_key', 'chave_test'),
        'oauth_signature_method': 'HMAC-SHA1',
        'oauth_timestamp': str(int(time.time())),
        'oauth_nonce': 'replaynonce12345',
        'oauth_version': '1.0',
        'oauth_signature': 'replaysignaturedummy',  # Não valida assinatura em modo replay/test se mockado
        'lti_message_type': 'basic-lti-launch-request',
        'lti_version': 'LTI-1p0',
        'resource_link_id': launch_data.get('resource_link_id', 'week_4_fatorial'),
        'lis_result_sourcedid': launch_data.get('lis_result_sourcedid', 'aluno_test'),
        'lis_outcome_service_url': launch_data.get('lis_outcome_service_url', 'http://127.0.0.1:9997/grade'),
        'custom_exercise_id': launch_data.get('custom_exercise_id', 'week_4_fatorial'),
        'user_id': launch_data.get('user_id', 'aluno_test'),
    }
    
    # Adiciona outros campos customizados se houver
    for k, v in launch_data.items():
        if k not in post_data:
            post_data[k] = v
            
    # Mock signature verification bypass na view se for execução do script
    os.environ['LTI_BYPASS_SIGNATURE_VERIFICATION'] = '1'
    
    try:
        response = client.post(launch_url, post_data)
        if response.status_code != 200:
            print(f"Launch Replay falhou com status {response.status_code}: {response.content}", flush=True)
            return False
            
        # Extrai o lti_token do HTML renderizado
        html = response.content.decode('utf-8')
        import re
        token_match = re.search(r'name="lti_token" value="(.*?)"', html)
        if not token_match:
            print("Não foi possível extrair o lti_token do formulário de submissão do HTML.", flush=True)
            return False
            
        lti_token = token_match.group(1)
        print("Launch simulado com sucesso. Token obtido.", flush=True)
        
        # 2. Simula Submissão e Passback
        submission_data = {
            'lti_token': lti_token,
            'custom_student_code': code or 'print("hello world")'
        }
        
        # Define a nota simulada para avaliação
        os.environ['LTI_FORCE_EVALUATION_SCORE'] = str(score)
        
        print("Enviando submissão simulada...", flush=True)
        sub_response = client.post(launch_url, submission_data)
        print(f"Submissão concluída com status {sub_response.status_code}.", flush=True)
        
        return sub_response.status_code == 200
        
    finally:
        if 'LTI_BYPASS_SIGNATURE_VERIFICATION' in os.environ:
            del os.environ['LTI_BYPASS_SIGNATURE_VERIFICATION']
        if 'LTI_FORCE_EVALUATION_SCORE' in os.environ:
            del os.environ['LTI_FORCE_EVALUATION_SCORE']
