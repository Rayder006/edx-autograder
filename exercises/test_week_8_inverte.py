# -*- coding: utf-8 -*-
import pytest

@pytest.mark.bateria(nome='week_8_inverte', peso=1.0, descricao='Testes para week_8_inverte')
@pytest.mark.parametrize("entrada, esperado", [('3\n7\n4\n0\n', '4\n7\n3'), ('3\n3\n5\n3\n10\n12\n0\n', '12\n10\n3\n5\n3\n3'), ('10\n0\n', '10')])
def test_week_8_inverte(script_runner, entrada, esperado):
    saida = script_runner.run("solution.py", stdin=entrada)
    assert script_runner.validar_saida(saida, esperado)
