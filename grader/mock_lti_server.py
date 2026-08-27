import http.server
import socketserver
import urllib.parse
import hashlib
import base64
import re
import sys
import os
import xml.etree.ElementTree as ET

os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'
from oauthlib.oauth1 import RequestValidator
from oauthlib.oauth1.rfc5849.endpoints import SignatureOnlyEndpoint

# Credentials for the mock server
MOCK_CONSUMER_KEY = 'key_test'
MOCK_SHARED_SECRET = 'secret_test'

class MockLTIValidator(RequestValidator):
    @property
    def enforce_ssl(self):
        return False

    def validate_client_key(self, client_key, request):
        return client_key == MOCK_CONSUMER_KEY

    def get_client_secret(self, client_key, request):
        return MOCK_SHARED_SECRET

    def validate_timestamp_and_nonce(self, client_key, timestamp, nonce, request, request_token=None, access_token=None):
        return True

    def validate_body_hash(self, client_key, request):
        # We manually validate body hash in our request handler to return custom scenario errors
        return True

    def check_client_key(self, client_key):
        return True

    def check_nonce(self, nonce):
        return True

class MockLTIServerHandler(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        # Parse query parameters to determine scenario if explicitly set
        parsed_url = urllib.parse.urlparse(self.path)
        query_params = urllib.parse.parse_qs(parsed_url.query)
        scenario = query_params.get('scenario', [None])[0]
        
        # Read body
        content_length = int(self.headers.get('Content-Length', 0))
        raw_body = self.rfile.read(content_length)
        
        # Calculate SHA1 body hash
        calculated_body_hash = base64.b64encode(hashlib.sha1(raw_body).digest()).decode('utf-8')
        
        # Extract Authorization header
        auth_header = self.headers.get('Authorization', '')
        
        # Extract oauth_body_hash from Authorization header
        body_hash_match = re.search(r'oauth_body_hash="([^"]+)"', auth_header)
        received_body_hash = urllib.parse.unquote(body_hash_match.group(1)) if body_hash_match else None
        
        # Extract consumer key
        key_match = re.search(r'oauth_consumer_key="([^"]+)"', auth_header)
        received_consumer_key = urllib.parse.unquote(key_match.group(1)) if key_match else None
        
        # Determine scenario automatically if not explicitly given in URL path/query
        if not scenario:
            # Check path for /scenario/X/
            path_match = re.search(r'/scenario/([A-I])/', parsed_url.path)
            if path_match:
                scenario = path_match.group(1)
                
        # Parse XML (Scenario G: XML invalid / not well-formed)
        xml_valid = True
        xml_root = None
        score_val = None
        sourced_id_val = None
        message_id = "mock_message_id_12345"
        
        if scenario != 'G':
            try:
                xml_root = ET.fromstring(raw_body)
                # Find namespace
                ns_match = re.search(r'{(.*?)}', xml_root.tag)
                ns = ns_match.group(1) if ns_match else "http://www.imsglobal.org/services/ltiv1p1/xsd/imsoms_v1p0"
                
                # Extract messageIdentifier
                msg_id_elem = xml_root.find(f".//{{{ns}}}imsx_messageIdentifier")
                if msg_id_elem is not None:
                    message_id = msg_id_elem.text
                    
                # Extract sourcedId
                sourced_elem = xml_root.find(f".//{{{ns}}}sourcedId")
                if sourced_elem is not None:
                    sourced_id_val = sourced_elem.text
                    
                # Extract score textString
                score_elem = xml_root.find(f".//{{{ns}}}textString")
                if score_elem is not None:
                    score_val = float(score_elem.text)
            except Exception:
                xml_valid = False
                
        # If scenario is not explicitly selected, try to infer it from request content
        if not scenario:
            if not xml_valid:
                scenario = 'G'
            elif score_val is not None and not (0.0 <= score_val <= 1.0):
                scenario = 'B'
            elif received_body_hash != calculated_body_hash:
                scenario = 'D'
            elif received_consumer_key != MOCK_CONSUMER_KEY:
                scenario = 'F'
            else:
                scenario = 'A'  # Default success
                
        # Handle scenarios
        if scenario == 'I':
            # Scenario I — HTTP 500 genérico com HTML
            self.send_response(500)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<html><head><title>Internal Server Error</title></head><body><h1>Erro 500</h1><p>Erro generico do LMS</p></body></html>")
            return
            
        if scenario == 'G' or not xml_valid:
            # Scenario G — XML inválido
            self.send_pox_response(message_id, "failure", "XML format is invalid", 400)
            return
            
        if scenario == 'F' or received_consumer_key != MOCK_CONSUMER_KEY:
            # Scenario F — consumer key incorreto
            self.send_pox_response(message_id, "failure", "Invalid consumer key", 401)
            return

        # Verify OAuth Signature (Scenario E: Secret incorreto, Scenario H: URL de assinatura diferente)
        # Note: We construct oauthlib Request object
        # Since we are http.server, we reconstruct the request URL.
        # We can simulate host from headers.
        host = self.headers.get('Host', '127.0.0.1')
        full_request_url = f"http://{host}{self.path}"
        
        # If scenario H is selected, we change the verification URL to verify failure
        if scenario == 'H':
            full_request_url = f"http://{host}/different_signature_path"
            
        # Standard validation
        validator = MockLTIValidator()
        endpoint = SignatureOnlyEndpoint(validator)
        
        # If scenario E is selected, we use a validator with wrong secret
        if scenario == 'E':
            class WrongSecretValidator(MockLTIValidator):
                def get_client_secret(self, client_key, request):
                    return "wrong_secret_123"
            endpoint = SignatureOnlyEndpoint(WrongSecretValidator())
            
        # Reconstruct signature verification headers
        headers_dict = dict(self.headers)
        # oauthlib verification
        valid_signature, req_obj = endpoint.validate_request(
            uri=full_request_url,
            http_method='POST',
            body=raw_body.decode('utf-8', errors='ignore'),
            headers=headers_dict
        )
        
        if not valid_signature or scenario == 'E' or scenario == 'H':
            self.send_pox_response(message_id, "failure", "Invalid signature", 401)
            return
            
        if scenario == 'D' or received_body_hash != calculated_body_hash:
            # Scenario D — OAuth body hash incorreto
            self.send_pox_response(message_id, "failure", "OAuth body hash mismatch", 401)
            return
            
        if scenario == 'B' or (score_val is not None and not (0.0 <= score_val <= 1.0)):
            # Scenario B — score inválido
            self.send_pox_response(message_id, "failure", "Score must be between 0.0 and 1.0", 400)
            return
            
        if scenario == 'C' or (sourced_id_val and "altered" in sourced_id_val):
            # Scenario C — sourcedid alterado / inválido
            self.send_pox_response(message_id, "failure", "SourcedGUID/SourcedId not recognized", 404)
            return
            
        # Scenario A — sucesso
        self.send_pox_response(message_id, "success", "Score replaced successfully", 200)

    def send_pox_response(self, message_id, code_major, severity_msg, http_status):
        self.send_response(http_status)
        self.send_header("Content-Type", "application/xml")
        self.end_headers()
        
        xml_resp = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<imsx_POXEnvelopeResponse xmlns="http://www.imsglobal.org/services/ltiv1p1/xsd/imsoms_v1p0">'
            '<imsx_POXHeader>'
            '<imsx_POXResponseHeaderInfo>'
            '<imsx_version>V1.0</imsx_version>'
            f'<imsx_messageIdentifier>{message_id}</imsx_messageIdentifier>'
            '<imsx_statusInfo>'
            f'<imsx_codeMajor>{code_major}</imsx_codeMajor>'
            f'<imsx_severity>status</imsx_severity>'
            f'<imsx_description>{severity_msg}</imsx_description>'
            f'<imsx_messageIdentifier>{message_id}</imsx_messageIdentifier>'
            '</imsx_statusInfo>'
            '</imsx_POXResponseHeaderInfo>'
            '</imsx_POXHeader>'
            '<imsx_POXBody>'
            '<replaceResultResponse/>'
            '</imsx_POXBody>'
            '</imsx_POXEnvelopeResponse>'
        )
        self.wfile.write(xml_resp.encode('utf-8'))

    def log_message(self, format, *args):
        # Prevent default logging to stdout to keep debug logs clean unless run directly
        if len(sys.argv) > 1 and sys.argv[1] == '--verbose':
            super().log_message(format, *args)

class ReusableTCPServer(socketserver.TCPServer):
    allow_reuse_address = True

def run_mock_server(port=9997):
    print(f"Mock LTI Server starting on port {port}...", flush=True)
    with ReusableTCPServer(("127.0.0.1", port), MockLTIServerHandler) as httpd:
        httpd.serve_forever()

if __name__ == '__main__':
    port = 9997
    if len(sys.argv) > 1 and sys.argv[1].isdigit():
        port = int(sys.argv[1])
    try:
        run_mock_server(port)
    except KeyboardInterrupt:
        print("\nStopping Mock LTI Server.", flush=True)
