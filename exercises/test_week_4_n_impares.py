# -*- coding: utf-8 -*-
import pytest

@pytest.mark.bateria(nome='primeiro_impar', peso=0.3, descricao='Checando o primeiro ímpar (n=1)')
@pytest.mark.parametrize("entrada, esperado", [('1\n', '1\n')])
def test_primeiro_impar(script_runner, entrada, esperado):
    saida = script_runner.run("solution.py", stdin=entrada)
    assert script_runner.validar_saida(saida, esperado)

@pytest.mark.bateria(nome='tres_impares', peso=0.3, descricao='Checando os 3 primeiros ímpares (n=3)')
@pytest.mark.parametrize("entrada, esperado", [('3\n', '1\n3\n5\n')])
def test_tres_impares(script_runner, entrada, esperado):
    saida = script_runner.run("solution.py", stdin=entrada)
    assert script_runner.validar_saida(saida, esperado)

@pytest.mark.bateria(nome='dez_impares', peso=0.4, descricao='Checando os 10 primeiros ímpares (n=10)')
@pytest.mark.parametrize("entrada, esperado", [('10\n', '1\n3\n5\n7\n9\n11\n13\n15\n17\n19\n')])
def test_dez_impares(script_runner, entrada, esperado):
    saida = script_runner.run("solution.py", stdin=entrada)
    assert script_runner.validar_saida(saida, esperado)
