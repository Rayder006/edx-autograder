# -*- coding: utf-8 -*-
import pytest
from solution import soma_hipotenusas

@pytest.mark.bateria(nome='week_7_soma_hipotenusas', peso=1.0, descricao='Testes para week_7_soma_hipotenusas')
@pytest.mark.parametrize("args, esperado", [([6], 5), ([15], 43), ([20], 80), ([27], 131)])
def test_week_7_soma_hipotenusas(args, esperado):
    assert soma_hipotenusas(*args) == esperado
