# -*- coding: utf-8 -*-
import pytest
from solution import maior_primo

@pytest.mark.bateria(nome='funcao_base', peso=1.0, descricao='Testando função maior_primo')
@pytest.mark.parametrize("args, esperado", [([100], 97), ([101], 101), ([102], 101), ([35], 31), ([961], 953)])
def test_funcao_base(args, esperado):
    assert maior_primo(*args) == esperado
