#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import sys

# Polyfill para o módulo 'cgi' removido no Python 3.13+ (PEP 594)
try:
    import cgi
except ImportError:
    import types
    
    # Cria um módulo cgi falso na memória
    cgi_mock = types.ModuleType('cgi')
    
    # Implementa parse_header necessário para processamento de cabeçalhos multipart no Django
    def parse_header(line):
        parts = [p.strip() for p in line.split(';')]
        key = parts[0].lower()
        pdict = {}
        for p in parts[1:]:
            if '=' in p:
                name, value = p.split('=', 1)
                name = name.strip().lower()
                value = value.strip()
                if value.startswith('"') and value.endswith('"'):
                    value = value[1:-1].replace('\\\\', '\\').replace('\\"', '"')
                pdict[name] = value
        return key, pdict
        
    cgi_mock.parse_header = parse_header
    sys.modules['cgi'] = cgi_mock

# INJEÇÃO DIRETA NO PONTO ZERO (Bypassa o cache de módulos do Python) para aceitar HTTP
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

def main():
    """Run administrative tasks."""
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == '__main__':
    main()
