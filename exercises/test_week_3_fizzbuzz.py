# -*- coding: utf-8 -*-
import pytest

@pytest.mark.bateria(nome='verdadeiro', peso=0.4, descricao='Checando casos verdadeiros')
@pytest.mark.parametrize("entrada, esperado", [('15\n', 'FizzBuzz'), ('30\n', 'FizzBuzz'), ('75\n', 'FizzBuzz')])
def test_verdadeiro(script_runner, entrada, esperado):
    saida = script_runner.run("solution.py", stdin=entrada)
    assert script_runner.validar_saida(saida, esperado)

@pytest.mark.bateria(nome='falso', peso=0.4, descricao='Checando casos falsos')
@pytest.mark.parametrize("entrada, esperado", [('3\n', '3'), ('5\n', '5'), ('8\n', '8')])
def test_falso(script_runner, entrada, esperado):
    saida = script_runner.run("solution.py", stdin=entrada)
    assert script_runner.validar_saida(saida, esperado)
