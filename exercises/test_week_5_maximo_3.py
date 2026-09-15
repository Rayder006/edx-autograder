# -*- coding: utf-8 -*-
import pytest
from solution import maximo

@pytest.mark.bateria(nome='funcao_base', peso=1.0, descricao='Testando função maximo')
@pytest.mark.parametrize("args, esperado", [([0, 2, 4], 4), ([2, 6, -4], 6), ([4, 2, 1], 4), ([7, 7, 7], 7), ([100, 350, 1001], 1001)])
def test_funcao_base(args, esperado):
    assert maximo(*args) == esperado
