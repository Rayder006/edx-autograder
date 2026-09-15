# -*- coding: utf-8 -*-
import pytest

@pytest.mark.bateria(nome='verdadeiro', peso=0.4, descricao='Checando casos verdadeiros')
@pytest.mark.parametrize("entrada, esperado", [('3\n', 'Fizz'), ('6\n', 'Fizz'), ('99\n', 'Fizz'), ('324\n', 'Fizz')])
def test_verdadeiro(script_runner, entrada, esperado):
    saida = script_runner.run("solution.py", stdin=entrada)
    assert script_runner.validar_saida(saida, esperado)

@pytest.mark.bateria(nome='falso', peso=0.4, descricao='Checando casos falsos')
@pytest.mark.parametrize("entrada, esperado", [('1\n', '1'), ('2\n', '2'), ('7\n', '7'), ('98\n', '98'), ('101\n', '101'), ('332\n', '332')])
def test_falso(script_runner, entrada, esperado):
    saida = script_runner.run("solution.py", stdin=entrada)
    assert script_runner.validar_saida(saida, esperado)

@pytest.mark.bateria(nome='zero_negativos', peso=0.2, descricao='Checando zero e negativos')
@pytest.mark.parametrize("entrada, esperado", [('0\n', 'Fizz'), ('-3\n', 'Fizz'), ('-1\n', '-1')])
def test_zero_negativos(script_runner, entrada, esperado):
    saida = script_runner.run("solution.py", stdin=entrada)
    assert script_runner.validar_saida(saida, esperado)
