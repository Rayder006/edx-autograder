# -*- coding: utf-8 -*-
import pytest

@pytest.mark.bateria(nome='verdadeiro', peso=0.4, descricao='Checando casos verdadeiros')
@pytest.mark.parametrize("entrada, esperado", [('5\n', 'Buzz'), ('10\n', 'Buzz'), ('20\n', 'Buzz')])
def test_verdadeiro(script_runner, entrada, esperado):
    saida = script_runner.run("solution.py", stdin=entrada)
    assert script_runner.validar_saida(saida, esperado)

@pytest.mark.bateria(nome='falso', peso=0.4, descricao='Checando casos falsos')
@pytest.mark.parametrize("entrada, esperado", [('3\n', '3'), ('4\n', '4')])
def test_falso(script_runner, entrada, esperado):
    saida = script_runner.run("solution.py", stdin=entrada)
    assert script_runner.validar_saida(saida, esperado)
