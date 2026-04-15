from oauthlib.oauth1 import RequestValidator

LTI_CONSUMER_KEY = 'minha_chave_edx_usp'
LTI_SHARED_SECRET = 'meu_segredo_super_seguro'

class EdXValidator(RequestValidator):
    @property
    def client_key_length(self):
        return 1, 100
        
    @property
    def dummy_client(self):
        # Exigido pelo oauthlib para evitar ataques de tempo (timing attacks)
        return "cliente_falso"

    def validate_client_key(self, client_key, request):
        return client_key == LTI_CONSUMER_KEY

    def get_client_secret(self, client_key, request):
        return LTI_SHARED_SECRET

    def validate_timestamp_and_nonce(self, client_key, timestamp, nonce, request, request_token=None, access_token=None):
        return True