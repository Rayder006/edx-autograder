# -*- coding: utf-8 -*-
import pytest
from solution import soma_elementos

@pytest.mark.bateria(nome='week_8_soma_elementos', peso=1.0, descricao='Testes para week_8_soma_elementos')
@pytest.mark.parametrize("args, esperado", [([[1, 2, 3]], 6), ([[7]], 7), ([[-9, -2, -1]], -12), ([[5, 5, 5, 5, 0, 5]], 25)])
def test_week_8_soma_elementos(args, esperado):
    assert soma_elementos(*args) == esperado
