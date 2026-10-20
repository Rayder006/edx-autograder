"""Comparação tolerante à apresentação, preservando números e desenhos."""
import re
import unicodedata
from decimal import Decimal, InvalidOperation


def normalizar(texto):
    return ''.join(
        char for char in unicodedata.normalize('NFD', str(texto or ''))
        if unicodedata.category(char) != 'Mn'
    ).lower()


def _tokens(text):
    return re.findall(r'[-+]?\d+(?:[.,]\d+)*|[^\W\d_]+|#+|\$', normalizar(text))


def _number(token):
    if ',' in token and '.' in token:
        token = token.replace('.', '').replace(',', '.')
    else:
        token = token.replace(',', '.')
    return Decimal(token)


def _same(actual, expected):
    if actual == expected:
        return True
    try:
        left, right = _number(actual), _number(expected)
    except InvalidOperation:
        return False
    # Os enunciados históricos incluem decimais truncados a seis casas.
    # Inteiros e sinais continuam exatos; 1 não corresponde a 10, nem -2 a 2.
    places = max(0, -right.as_tuple().exponent)
    tolerance = Decimal(10) ** -places if places >= 6 else Decimal('0.000000001')
    return abs(left - right) <= tolerance


def validar_saida_script(saida_aluno, esperado):
    actual_tokens = _tokens(saida_aluno)
    expected_tokens = _tokens(esperado)
    if expected_tokens == ['primo'] and 'nao' in actual_tokens:
        return False
    actual = iter(actual_tokens)
    for expected in expected_tokens:
        if not any(_same(token, expected) for token in actual):
            return False
    return True
