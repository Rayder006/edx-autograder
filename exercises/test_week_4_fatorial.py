# -*- coding: utf-8 -*-
import pytest

@pytest.mark.bateria(nome='fatorial', peso=1.0, descricao='Checando cálculo de fatorial')
@pytest.mark.parametrize("entrada, esperado", [('0\n', '1'), ('1\n', '1'), ('4\n', '24'), ('5\n', '120'), ('20\n', '2432902008176640000'), ('73\n', '4470115461512684340891257138125051110076800700282905015819080092370422104067183317016903680000000000000000')])
def test_fatorial(script_runner, entrada, esperado):
    saida = script_runner.run("solution.py", stdin=entrada)
    assert script_runner.validar_saida(saida, esperado)
