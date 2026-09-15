# -*- coding: utf-8 -*-
import pytest

@pytest.mark.bateria(nome='calculo_media', peso=1.0, descricao='Verificando cálculo da média')
@pytest.mark.parametrize("entrada, esperado", [('1\n2\n3\n4\n', 'A média aritmética é 2.5'), ('1\n1\n1\n1\n', 'A média aritmética é 1.0'), ('0\n10\n8\n0\n', 'A média aritmética é 4.5'), ('1000\n2232\n1010\n300\n', 'A média aritmética é 1135.5')])
def test_calculo_media(script_runner, entrada, esperado):
    saida = script_runner.run("solution.py", stdin=entrada)
    assert script_runner.validar_saida(saida, esperado)
