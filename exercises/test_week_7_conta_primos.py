# -*- coding: utf-8 -*-
import pytest
from solution import n_primos

@pytest.mark.bateria(nome='week_7_conta_primos', peso=1.0, descricao='Testes para week_7_conta_primos')
@pytest.mark.parametrize("args, esperado", [([6], 3), ([15], 6), ([20], 8), ([24], 9)])
def test_week_7_conta_primos(args, esperado):
    assert n_primos(*args) == esperado
