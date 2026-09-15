# -*- coding: utf-8 -*-
import pytest
from solution import remove_repetidos

@pytest.mark.bateria(nome='week_8_remove_repetidos', peso=1.0, descricao='Testes para week_8_remove_repetidos')
@pytest.mark.parametrize("args, esperado", [([[1, 2, 3]], [1, 2, 3]), ([[1, 2, 1, 3, 4, 7, 10]], [1, 2, 3, 4, 7, 10]), ([[7, 3, 33, 12, 3, 3, 3, 7, 12, 100]], [3, 7, 12, 33, 100])])
def test_week_8_remove_repetidos(args, esperado):
    assert remove_repetidos(*args) == esperado
