"""Submissão LTI direta para um servidor local já iniciado."""
import os
import sys
import uuid
from pathlib import Path

import requests
from dotenv import load_dotenv
from requests_oauthlib import OAuth1

from grader.lti_debug import obter_lti_passports


def main():
    load_dotenv(Path(__file__).resolve().parent / '.env', override=False)
    passports = obter_lti_passports()
    if passports:
        key, secret = next(iter(passports.items()))
    else:
        key = os.environ.get('LTI_CONSUMER_KEY', 'minha_chave_edx_usp')
        secret = os.environ.get('LTI_SHARED_SECRET', 'meu_segredo_super_seguro')
    port = os.environ.get('AUTOGRADER_WEB_PORT', '8000')
    url = os.environ.get('AUTOGRADER_TEST_URL', f'http://127.0.0.1:{port}/lti/avaliacao/')
    payload = {
        'lti_message_type': 'basic-lti-launch-request', 'lti_version': 'LTI-1p0',
        'resource_link_id': 'week_4_fatorial', 'custom_exercise_id': 'week_4_fatorial',
        'user_id': 'teste-cli-' + uuid.uuid4().hex,
        'custom_student_code': 'import math\nn = int(input())\nprint(math.factorial(n))\n',
    }
    if os.environ.get('AUTOGRADER_TEST_OUTCOME_URL'):
        payload['lis_outcome_service_url'] = os.environ['AUTOGRADER_TEST_OUTCOME_URL']
        payload['lis_result_sourcedid'] = os.environ.get('AUTOGRADER_TEST_SOURCEDID', payload['user_id'])
    auth = OAuth1(key, client_secret=secret, signature_type='body')
    print(f'Enviando exercício de teste para {url}...')
    try:
        response = requests.post(url, data=payload, auth=auth, timeout=60)
    except requests.RequestException as error:
        print(f'Falha ao acessar o servidor: {error}', file=sys.stderr)
        return 1
    print(f'HTTP {response.status_code}\n{response.text}')
    return 0 if response.status_code == 200 and 'Nota Final: 10.0/10.0' in response.text else 1


if __name__ == '__main__':
    sys.exit(main())
