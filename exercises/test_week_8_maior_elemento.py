# -*- coding: utf-8 -*-
import pytest
from solution import maior_elemento

@pytest.mark.bateria(nome='week_8_maior_elemento', peso=1.0, descricao='Testes para week_8_maior_elemento')
@pytest.mark.parametrize("args, esperado", [([[6, 2, 3]], 6), ([[7, -7, 1, 5, 5, 7]], 7), ([[-90, -27, -12]], -12), ([[1]], 1)])
def test_week_8_maior_elemento(args, esperado):
    assert maior_elemento(*args) == esperado
