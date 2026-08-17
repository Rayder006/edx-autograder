from django.test import TestCase
from unittest.mock import patch
import requests
from grader.views import enviar_nota_ao_edx

class LTIOutcomesTestCase(TestCase):
    @patch('grader.views.requests.post')
    def test_enviar_nota_ao_edx_includes_body_hash(self, mock_post):
        # Set up mock response
        mock_response = requests.Response()
        mock_response.status_code = 200
        mock_response._content = b'<imsx_POXEnvelopeResponse><imsx_POXHeader><imsx_statusInfo><imsx_codeMajor>success</imsx_codeMajor></imsx_statusInfo></imsx_POXHeader></imsx_POXEnvelopeResponse>'
        mock_post.return_value = mock_response

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
        mock_post.assert_called_once()
        
        args, kwargs = mock_post.call_args
        url = args[0]
        self.assertEqual(url, 'https://dummy.edx.org/grades')
        
        # Verify headers and auth
        headers = kwargs.get('headers')
        self.assertEqual(headers.get('Content-Type'), 'application/xml')
        
        auth = kwargs.get('auth')
        self.assertIsNotNone(auth)
        
        # Test prepared request headers using the auth object
        req = requests.Request('POST', url, data=kwargs.get('data'), auth=auth, headers=headers)
        prepared = req.prepare()
        auth_header = prepared.headers.get('Authorization')
        self.assertIsNotNone(auth_header)
        
        # We decode to string if it is bytes
        if isinstance(auth_header, bytes):
            auth_header = auth_header.decode('utf-8')
            
        self.assertIn('oauth_body_hash=', auth_header)

    @patch('grader.views.requests.post')
    def test_enviar_nota_ao_edx_unquotes_sourcedid(self, mock_post):
        # Set up mock response
        mock_response = requests.Response()
        mock_response.status_code = 200
        mock_response._content = b'<imsx_POXEnvelopeResponse><imsx_POXHeader><imsx_statusInfo><imsx_codeMajor>success</imsx_codeMajor></imsx_statusInfo></imsx_POXHeader></imsx_POXEnvelopeResponse>'
        mock_post.return_value = mock_response

        # Call function with percent-encoded sourcedid
        success = enviar_nota_ao_edx(
            lis_outcome_service_url='https://dummy.edx.org/grades',
            lis_result_sourcedid='course-v1%3AUSP%2BICCP1%2B2T2024:courses.edx.org-lti_consumer3:aluno_test',
            nota_decimal=0.85,
            client_key='key_test',
            client_secret='secret_test'
        )

        self.assertTrue(success)
        mock_post.assert_called_once()
        
        args, kwargs = mock_post.call_args
        data = kwargs.get('data')
        if isinstance(data, bytes):
            data = data.decode('utf-8')
            
        # Verify the sourcedId in the XML body has been decoded (unquoted)
        # %3A -> : and %2B -> +
        self.assertIn('<sourcedId>course-v1:USP+ICCP1+2T2024:courses.edx.org-lti_consumer3:aluno_test</sourcedId>', data)

