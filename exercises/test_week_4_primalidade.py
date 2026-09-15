# -*- coding: utf-8 -*-
import pytest

@pytest.mark.bateria(nome='primos_pequenos', peso=0.15, descricao='Testando primos pequenos')
@pytest.mark.parametrize("entrada, esperado", [('2\n', 'primo'), ('3\n', 'primo'), ('5\n', 'primo'), ('7\n', 'primo'), ('11\n', 'primo'), ('13\n', 'primo'), ('4\n', 'não primo'), ('6\n', 'não primo'), ('8\n', 'não primo'), ('9\n', 'não primo'), ('10\n', 'não primo'), ('14\n', 'não primo'), ('15\n', 'não primo')])
def test_primos_pequenos(script_runner, entrada, esperado):
    saida = script_runner.run("solution.py", stdin=entrada)
    assert script_runner.validar_saida(saida, esperado)

@pytest.mark.bateria(nome='nao_primos_pequenos', peso=0.15, descricao='Testando não-primos pequenos')
@pytest.mark.parametrize("entrada, esperado", [('4\n', 'não primo'), ('6\n', 'não primo'), ('8\n', 'não primo'), ('9\n', 'não primo'), ('10\n', 'não primo'), ('14\n', 'não primo'), ('15\n', 'não primo')])
def test_nao_primos_pequenos(script_runner, entrada, esperado):
    saida = script_runner.run("solution.py", stdin=entrada)
    assert script_runner.validar_saida(saida, esperado)

@pytest.mark.bateria(nome='primos_diversos', peso=0.35, descricao='Testando primos diversos')
@pytest.mark.parametrize("entrada, esperado", [('359\n', 'primo'), ('7451\n', 'primo'), ('87874301\n', 'primo'), ('85043527\n', 'não primo'), ('377\n', 'não primo'), ('7447\n', 'não primo'), ('361\n', 'não primo')])
def test_primos_diversos(script_runner, entrada, esperado):
    saida = script_runner.run("solution.py", stdin=entrada)
    assert script_runner.validar_saida(saida, esperado)

@pytest.mark.bateria(nome='nao_primos_diversos', peso=0.35, descricao='Testando não-primos diversos')
@pytest.mark.parametrize("entrada, esperado", [('85043527\n', 'não primo'), ('377\n', 'não primo'), ('7447\n', 'não primo'), ('361\n', 'não primo')])
def test_nao_primos_diversos(script_runner, entrada, esperado):
    saida = script_runner.run("solution.py", stdin=entrada)
    assert script_runner.validar_saida(saida, esperado)
