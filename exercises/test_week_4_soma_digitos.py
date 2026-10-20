# -*- coding: utf-8 -*-
import pytest

@pytest.mark.bateria(nome='soma_digitos', peso=1.0, descricao='Checando soma dos dígitos')
@pytest.mark.parametrize("entrada, esperado", [('0\n', '0'), ('111\n', '3'), ('4\n', '4'), ('54\n', '9'), ('200000\n', '2'), ('733432134\n', '30')])
def test_soma_digitos(script_runner, entrada, esperado):
    saida = script_runner.run("solution.py", stdin=entrada)
    assert script_runner.validar_saida(saida, esperado)
