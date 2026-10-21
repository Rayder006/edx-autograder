import os
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

from django.test import TestCase, override_settings
from unittest.mock import patch
import requests
import pytest
import threading
import time
import base64
import hashlib
import hmac
from grader.views import LTI_KEY, LTI_SECRET, enviar_nota_ao_edx, escape
from grader.mock_lti_server import ReusableTCPServer, MockLTIServerHandler, MOCK_CONSUMER_KEY, MOCK_SHARED_SECRET
from grader.lti_debug import obter_lti_passports

class LTIOutcomesTestCase(TestCase):
    @patch('grader.views.requests.Session.send')
    def test_enviar_nota_ao_edx_includes_body_hash(self, mock_send):
        # Set up mock response
        mock_response = requests.Response()
        mock_response.status_code = 200
        mock_response._content = b'<imsx_POXEnvelopeResponse><imsx_POXHeader><imsx_statusInfo><imsx_codeMajor>success</imsx_codeMajor></imsx_statusInfo></imsx_POXHeader></imsx_POXEnvelopeResponse>'
        mock_send.return_value = mock_response

        # Call function
        success = enviar_nota_ao_edx(
            lis_outcome_service_url='https://dummy.edx.org/grades',
            lis_result_sourcedid='aluno_test',
            nota_decimal=0.85,
            client_key='key_test',
            client_secret='secret_test'
        )

        # Check call arguments
        self.assertTrue(success)
        mock_send.assert_called_once()
        
        args, kwargs = mock_send.call_args
        prepared_request = args[0]
        
        self.assertEqual(prepared_request.url, 'https://dummy.edx.org/grades')
        
        # Verify headers and auth
        headers = prepared_request.headers
        self.assertEqual(headers.get('Content-Type'), 'application/xml')
        
        auth_header = headers.get('Authorization')
        self.assertIsNotNone(auth_header)
        self.assertIn('oauth_body_hash=', auth_header)

    @patch('grader.views.requests.Session.send')
    def test_enviar_nota_ao_edx_preserves_sourcedid_raw(self, mock_send):
        # Set up mock response
        mock_response = requests.Response()
        mock_response.status_code = 200
        mock_response._content = b'<imsx_POXEnvelopeResponse><imsx_POXHeader><imsx_statusInfo><imsx_codeMajor>success</imsx_codeMajor></imsx_statusInfo></imsx_POXHeader></imsx_POXEnvelopeResponse>'
        mock_send.return_value = mock_response

        # Call function with percent-encoded sourcedid
        success = enviar_nota_ao_edx(
            lis_outcome_service_url='https://dummy.edx.org/grades',
            lis_result_sourcedid='course-v1%3AUSP%2BICCP1%2B2T2024:courses.edx.org-lti_consumer3:aluno_test',
            nota_decimal=0.85,
            client_key='key_test',
            client_secret='secret_test'
        )

        self.assertTrue(success)
        mock_send.assert_called_once()
        
        args, kwargs = mock_send.call_args
        prepared_request = args[0]
        data = prepared_request.body
        if isinstance(data, bytes):
            data = data.decode('utf-8')
            
        # Verify the sourcedId in the XML body is preserved raw (opaque)
        self.assertIn('<sourcedId>course-v1%3AUSP%2BICCP1%2B2T2024:courses.edx.org-lti_consumer3:aluno_test</sourcedId>', data)

    @patch('grader.views.requests.Session.send')
    def test_enviar_nota_ao_edx_escapes_xml_sourcedid(self, mock_send):
        mock_response = requests.Response()
        mock_response.status_code = 200
        mock_response._content = b'<imsx_POXEnvelopeResponse><imsx_POXHeader><imsx_statusInfo><imsx_codeMajor>success</imsx_codeMajor></imsx_statusInfo></imsx_POXHeader></imsx_POXEnvelopeResponse>'
        mock_send.return_value = mock_response

        self.assertTrue(enviar_nota_ao_edx(
            'https://dummy.edx.org/grades', 'aluno&teste', 0.5,
            'key_test', 'secret_test'
        ))
        body = mock_send.call_args.args[0].body
        if isinstance(body, bytes):
            body = body.decode('utf-8')
        self.assertIn('<sourcedId>aluno&amp;teste</sourcedId>', body)


class LTILaunchSignatureTestCase(TestCase):
    key = 'launch_key'
    secret = 'launch_secret'

    def _assinar(self, url, params):
        encoded_params = [(escape(k), escape(v)) for k, v in params.items()]
        encoded_params.sort()
        parameter_string = '&'.join(f'{key}={value}' for key, value in encoded_params)
        base_string = '&'.join(['POST', escape(url.split('?')[0]), escape(parameter_string)])
        signing_key = escape(self.secret) + '&'
        digest = hmac.new(
            signing_key.encode('utf-8'), base_string.encode('utf-8'), hashlib.sha1
        ).digest()
        return base64.b64encode(digest).decode('utf-8')

    def test_launch_with_exercise_query_parameter_has_valid_signature(self):
        url = 'http://testserver/lti/avaliacao/?exercise=week_4_fatorial'
        payload = {
            'oauth_consumer_key': self.key,
            'oauth_nonce': 'query-param-test-nonce',
            'oauth_signature_method': 'HMAC-SHA1',
            'oauth_timestamp': str(int(time.time())),
            'oauth_version': '1.0',
            'lti_message_type': 'basic-lti-launch-request',
            'lti_version': 'LTI-1p0',
            'resource_link_id': 'week_4_fatorial',
            'user_id': 'query-param-test-user',
        }
        payload['oauth_signature'] = self._assinar(
            url, {**payload, 'exercise': 'week_4_fatorial'}
        )

        with patch.dict(os.environ, {'LTI_PASSPORTS': f'{self.key}:{self.secret}'}):
            response = self.client.post('/lti/avaliacao/?exercise=week_4_fatorial', payload)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="lti_token"')

class LTIOutcomesIntegrationTestCase(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.mock_server = ReusableTCPServer(("127.0.0.1", 0), MockLTIServerHandler)
        cls.server_port = cls.mock_server.server_address[1]
        cls.server_thread = threading.Thread(target=cls.mock_server.serve_forever)
        cls.server_thread.daemon = True
        cls.server_thread.start()
        # Wait a moment for server to start
        time.sleep(0.5)

    @classmethod
    def tearDownClass(cls):
        cls.mock_server.shutdown()
        cls.mock_server.server_close()
        cls.server_thread.join()
        super().tearDownClass()

    def setUp(self):
        self.env_patch = patch.dict(os.environ, {'LTI_PASSPORTS': '', 'LTI_PASSBACK_DRY_RUN': '0'})
        self.env_patch.start()
        self.addCleanup(self.env_patch.stop)
        # Clear LTI_PASSPORTS env before each test
        if 'LTI_PASSPORTS' in os.environ:
            del os.environ['LTI_PASSPORTS']
        if 'LTI_PASSBACK_DRY_RUN' in os.environ:
            del os.environ['LTI_PASSBACK_DRY_RUN']
        self.url = f"http://127.0.0.1:{self.server_port}/grade"
        self.client_key = MOCK_CONSUMER_KEY
        self.client_secret = MOCK_SHARED_SECRET

    # Scenarios 1-3: score ranges [0.0, 1.0]
    def test_score_valid_0_0(self):
        res = enviar_nota_ao_edx(self.url, 'aluno_test', 0.0, self.client_key, self.client_secret)
        self.assertTrue(res)

    def test_score_valid_0_5(self):
        res = enviar_nota_ao_edx(self.url, 'aluno_test', 0.5, self.client_key, self.client_secret)
        self.assertTrue(res)

    def test_score_valid_1_0(self):
        res = enviar_nota_ao_edx(self.url, 'aluno_test', 1.0, self.client_key, self.client_secret)
        self.assertTrue(res)

    # Scenarios 4-5: invalid score limits
    def test_score_invalid_under_zero(self):
        res = enviar_nota_ao_edx(self.url, 'aluno_test', -0.1, self.client_key, self.client_secret)
        self.assertFalse(res)

    def test_score_invalid_over_one(self):
        res = enviar_nota_ao_edx(self.url, 'aluno_test', 1.1, self.client_key, self.client_secret)
        self.assertFalse(res)

    # Scenarios 6-7: sourcedid encoding variations
    def test_sourcedid_with_percent_encoding(self):
        sourcedid = "course-v1%3AUSP%2BICCP1%2B2T2024:courses.edx.org-lti_consumer3:aluno_test"
        res = enviar_nota_ao_edx(self.url, sourcedid, 0.8, self.client_key, self.client_secret)
        self.assertTrue(res)

    def test_sourcedid_without_percent_encoding(self):
        sourcedid = "course-v1:USP+ICCP1+2T2024:courses.edx.org-lti_consumer3:aluno_test"
        res = enviar_nota_ao_edx(self.url, sourcedid, 0.8, self.client_key, self.client_secret)
        self.assertTrue(res)

    # Scenarios 8-11: consumer key and secret validations
    def test_consumer_key_incorrect(self):
        # Scenario F is triggered by sending an incorrect client key
        res = enviar_nota_ao_edx(self.url, 'aluno_test', 0.8, 'wrong_key', self.client_secret)
        self.assertFalse(res)

    def test_consumer_key_correct(self):
        res = enviar_nota_ao_edx(self.url, 'aluno_test', 0.8, self.client_key, self.client_secret)
        self.assertTrue(res)

    def test_secret_incorrect(self):
        # Scenario E is explicitly selected via URL query parameter for wrong secret validation
        url_with_scen = f"{self.url}?scenario=E"
        res = enviar_nota_ao_edx(url_with_scen, 'aluno_test', 0.8, self.client_key, 'wrong_secret')
        self.assertFalse(res)

    def test_secret_correct(self):
        res = enviar_nota_ao_edx(self.url, 'aluno_test', 0.8, self.client_key, self.client_secret)
        self.assertTrue(res)

    # Scenarios 12-13: body hash checks
    def test_body_hash_correct(self):
        res = enviar_nota_ao_edx(self.url, 'aluno_test', 0.85, self.client_key, self.client_secret)
        self.assertTrue(res)

    def test_body_hash_adulterated(self):
        # Scenario D (body hash incorrect)
        url_with_scen = f"{self.url}?scenario=D"
        res = enviar_nota_ao_edx(url_with_scen, 'aluno_test', 0.85, self.client_key, self.client_secret)
        self.assertFalse(res)

    # Scenarios 14-15: XML payload format
    def test_xml_valid(self):
        res = enviar_nota_ao_edx(self.url, 'aluno_test', 0.85, self.client_key, self.client_secret)
        self.assertTrue(res)

    def test_xml_invalid(self):
        # Scenario G (XML invalid)
        url_with_scen = f"{self.url}?scenario=G"
        res = enviar_nota_ao_edx(url_with_scen, 'aluno_test', 0.85, self.client_key, self.client_secret)
        self.assertFalse(res)

    # Scenarios 16-17: Signature URL checks
    def test_signature_url_correct(self):
        res = enviar_nota_ao_edx(self.url, 'aluno_test', 0.85, self.client_key, self.client_secret)
        self.assertTrue(res)

    def test_signature_url_altered(self):
        # Scenario H (different signature url)
        url_with_scen = f"{self.url}?scenario=H"
        res = enviar_nota_ao_edx(url_with_scen, 'aluno_test', 0.85, self.client_key, self.client_secret)
        self.assertFalse(res)

    # Scenarios 18-19: launch to passback comparison logic
    def test_launch_passback_no_change(self):
        from grader.lti_debug import comparar_launch_passback
        launch = {'user_id': 'aluno1', 'custom_exercise_id': 'ex1', 'lis_result_sourcedid': 'src1'}
        passback = {'user_id': 'aluno1', 'custom_exercise_id': 'ex1', 'lis_result_sourcedid': 'src1'}
        # Should not raise exception
        comparar_launch_passback(launch, passback)

    def test_launch_passback_with_change(self):
        from grader.lti_debug import comparar_launch_passback
        launch = {'user_id': 'aluno1', 'custom_exercise_id': 'ex1', 'lis_result_sourcedid': 'src1'}
        passback = {'user_id': 'aluno2', 'custom_exercise_id': 'ex1', 'lis_result_sourcedid': 'src2'}
        # Warning log will be printed, but should not raise exception
        comparar_launch_passback(launch, passback)

    # Scenario 20: Dry-run
    @override_settings(DEBUG=True)
    def test_dry_run_mode(self):
        os.environ['LTI_PASSBACK_DRY_RUN'] = '1'
        # Calling with invalid URL to verify it's not even hitting the network
        res = enviar_nota_ao_edx("http://invalid-dns-name/grades", 'aluno_test', 0.85, self.client_key, self.client_secret)
        self.assertTrue(res)

    # Scenarios 21-25: server HTTP responses
    def test_mock_server_returning_200(self):
        url_with_scen = f"{self.url}?scenario=A"
        res = enviar_nota_ao_edx(url_with_scen, 'aluno_test', 0.85, self.client_key, self.client_secret)
        self.assertTrue(res)

    def test_mock_server_returning_400(self):
        url_with_scen = f"{self.url}?scenario=B"  # returns 400
        res = enviar_nota_ao_edx(url_with_scen, 'aluno_test', 1.5, self.client_key, self.client_secret) # invalid score
        self.assertFalse(res)

    def test_mock_server_returning_401_403(self):
        url_with_scen = f"{self.url}?scenario=F"  # returns 401
        res = enviar_nota_ao_edx(url_with_scen, 'aluno_test', 0.85, 'wrong_key', self.client_secret)
        self.assertFalse(res)

    def test_mock_server_returning_500(self):
        url_with_scen = f"{self.url}?scenario=I"  # returns 500 html
        res = enviar_nota_ao_edx(url_with_scen, 'aluno_test', 0.85, self.client_key, self.client_secret)
        self.assertFalse(res)

    def test_mock_server_returning_html(self):
        url_with_scen = f"{self.url}?scenario=I"  # returns 500 HTML page
        res = enviar_nota_ao_edx(url_with_scen, 'aluno_test', 0.85, self.client_key, self.client_secret)
        self.assertFalse(res)

    # Scenarios 26-28: timeout and other edge cases
    @patch('grader.views.requests.Session.send', side_effect=requests.Timeout('Simulated timeout'))
    def test_request_timeout(self, mock_send):
        res = enviar_nota_ao_edx("http://10.255.255.1:9999/grades", 'aluno_test', 0.85, self.client_key, self.client_secret)
        self.assertFalse(res)

    @override_settings(DEBUG=True)
    @patch('grader.views.executar_avaliacao')
    def test_replay_mechanism(self, mock_eval):
        mock_eval.return_value = {
            'nota': 0.9,
            'detalhes': [
                {'peso': 0.5, 'descricao': 'Teste 1', 'passou': True},
                {'peso': 0.5, 'descricao': 'Teste 2', 'passou': True}
            ]
        }
        from grader.lti_debug import executar_replay
        # O replay de teste nunca sobrescreve um arquivo do diretório de trabalho.
        replay_data = {
            'oauth_consumer_key': self.client_key,
            'lis_result_sourcedid': 'course-v1%3AUSP%2BICCP1%2B2T2024:courses.edx.org-lti_consumer3:aluno_test',
            'lis_outcome_service_url': self.url,
            'user_id': 'aluno_test',
            'context_id': 'course-v1:USP+ICCP1+2T2024',
            'resource_link_id': 'week_4_fatorial',
            'custom_exercise_id': 'week_4_fatorial'
        }
        
        import tempfile
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        temp_path = os.path.join(temporary.name, 'replay_test.json')
        import json
        with open(temp_path, 'w', encoding='utf-8') as f:
            json.dump(replay_data, f)
            
        try:
            # Set passports to allow mock validation
            os.environ['LTI_PASSPORTS'] = f"test:{self.client_key}:{self.client_secret}"
            res = executar_replay(temp_path, code='print("Replay code")', score=0.9)
            self.assertTrue(res)
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)
            if 'LTI_PASSPORTS' in os.environ:
                del os.environ['LTI_PASSPORTS']

    def test_passport_parser_json(self):
        os.environ['LTI_PASSPORTS'] = '{"key1": "secret1", "key2": "secret2"}'
        passports = obter_lti_passports()
        self.assertEqual(passports.get('key1'), 'secret1')
        self.assertEqual(passports.get('key2'), 'secret2')

    def test_passport_parser_edx(self):
        os.environ['LTI_PASSPORTS'] = 'passport1:key1:secret1, passport2:key2:secret2'
        passports = obter_lti_passports()
        self.assertEqual(passports.get('key1'), 'secret1')
        self.assertEqual(passports.get('key2'), 'secret2')

class EvaluatorTestCase(TestCase):
    def test_bateria_all_passed(self):
        from grader.evaluator import calcular_nota_baterias
        config = {
            "tipo": "script",
            "baterias": [
                {
                    "nome": "bateria_1",
                    "descricao": "Bateria 1",
                    "peso": 0.8,
                    "testes": [{"input": "1"}, {"input": "2"}]
                }
            ]
        }
        resultados = [
            {"bateria_idx": 0, "passou": True},
            {"bateria_idx": 0, "passou": True}
        ]
        res = calcular_nota_baterias(config, resultados)
        self.assertEqual(res["nota"], 0.8)
        self.assertTrue(res["baterias"][0]["passou"])

    def test_bateria_one_failed_gets_zero(self):
        from grader.evaluator import calcular_nota_baterias
        config = {
            "tipo": "script",
            "baterias": [
                {
                    "nome": "bateria_digitos",
                    "descricao": "Checando dígitos",
                    "peso": 0.8,
                    "testes": [{"input": str(i)} for i in range(7)]
                }
            ]
        }
        # 6 pass, 1 fails -> battery gets 0.0!
        resultados = [{"bateria_idx": 0, "passou": True} for _ in range(6)]
        resultados.append({"bateria_idx": 0, "passou": False})
        
        res = calcular_nota_baterias(config, resultados)
        self.assertEqual(res["nota"], 0.0)
        self.assertFalse(res["baterias"][0]["passou"])
        self.assertEqual(res["baterias"][0]["nota_obtida"], 0.0)

    def test_multiple_baterias_partial_success(self):
        from grader.evaluator import calcular_nota_baterias
        config = {
            "tipo": "script",
            "baterias": [
                {
                    "nome": "bateria_1",
                    "descricao": "Dígito dezenas",
                    "peso": 0.8,
                    "testes": [{"input": "12"}, {"input": "23"}]
                },
                {
                    "nome": "bateria_2",
                    "descricao": "Mensagem formato",
                    "peso": 0.2,
                    "testes": [{"input": "1"}]
                }
            ]
        }
        # Battery 1 passes, Battery 2 fails
        resultados = [
            {"bateria_idx": 0, "passou": True},
            {"bateria_idx": 0, "passou": True},
            {"bateria_idx": 1, "passou": False}
        ]
        res = calcular_nota_baterias(config, resultados)
        self.assertEqual(res["nota"], 0.8)
        self.assertTrue(res["baterias"][0]["passou"])
        self.assertFalse(res["baterias"][1]["passou"])

    def test_extrair_lista_testes(self):
        from grader.evaluator import extrair_lista_testes
        config = {
            "tipo": "script",
            "baterias": [
                {
                    "nome": "bat1",
                    "peso": 0.8,
                    "testes": [{"input": "10"}, {"input": "20"}]
                }
            ]
        }
        planos = extrair_lista_testes(config)
        self.assertEqual(len(planos), 2)
        self.assertEqual(planos[0]["_bateria_nome"], "bat1")
        self.assertEqual(planos[0]["_bateria_peso"], 0.8)

@pytest.mark.docker
class PytestRunnerTestCase(TestCase):
    def test_avaliar_com_pytest_script(self):
        from grader.pytest_runner import avaliar_com_pytest
        codigo_aluno = (
            "n = int(input())\n"
            "d = (n // 10) % 10\n"
            "print(f'O dígito das dezenas é {d}')\n"
        )
        res = avaliar_com_pytest(codigo_aluno, "week_2_dezenas")
        self.assertTrue(res["sucesso"])
        self.assertEqual(res["nota"], 1.0)
        self.assertTrue(len(res["baterias"]) >= 1)

    def test_avaliar_com_pytest_funcao(self):
        from grader.pytest_runner import avaliar_com_pytest
        codigo_aluno = (
            "def fizzbuzz(n):\n"
            "    if n % 3 == 0 and n % 5 == 0:\n"
            "        return 'FizzBuzz'\n"
            "    elif n % 3 == 0:\n"
            "        return 'Fizz'\n"
            "    elif n % 5 == 0:\n"
            "        return 'Buzz'\n"
            "    else:\n"
            "        return n\n"
        )
        res = avaliar_com_pytest(codigo_aluno, "week_5_fizzbuzz_funcao")
        self.assertTrue(res["sucesso"])
        self.assertEqual(res["nota"], 1.0)
        self.assertEqual(len(res["baterias"]), 4)


