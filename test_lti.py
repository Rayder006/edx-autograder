import os
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

import requests
from requests_oauthlib import OAuth1

LTI_KEY = 'minha_chave_edx_usp' # chave lti reconhecida
LTI_SECRET = 'meu_segredo_super_seguro' # segredo para assinatura HMAC
URL = 'http://127.0.0.1:8000/lti/avaliacao/'

payload = {
    'lti_message_type': 'basic-lti-launch-request',
    'lti_version': 'LTI-1p0',
    'resource_link_id': 'exercicio_soma',
    'lis_result_sourcedid': 'aluno_test',
    'lis_outcome_service_url': 'https://dummy.edx.org/grades',
    'custom_student_code': 'print(int(input()) + int(input()))'
}

auth_signer = OAuth1(LTI_KEY, client_secret=LTI_SECRET, signature_type='body')

print(f"Disparando POST para {URL}...")

response = requests.post(URL, data=payload, auth=auth_signer)
    
print("\n=== RETORNO DO DJANGO ===")
print(f"Status Code : {response.status_code}")
print(f"Mensagem    : {response.text}")
print("=========================")