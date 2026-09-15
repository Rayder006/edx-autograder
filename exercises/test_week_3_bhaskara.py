# -*- coding: utf-8 -*-
import pytest

@pytest.mark.bateria(nome='sem_raizes', peso=0.3, descricao='Testando Bhaskara sem raízes reais')
@pytest.mark.parametrize("entrada, esperado", [('5\n3\n5\n', 'esta equação não possui raízes reais')])
def test_sem_raizes(script_runner, entrada, esperado):
    saida = script_runner.run("solution.py", stdin=entrada)
    assert script_runner.validar_saida(saida, esperado)

@pytest.mark.bateria(nome='raiz_dupla', peso=0.3, descricao='Testando Bhaskara com uma raiz dupla')
@pytest.mark.parametrize("entrada, esperado", [('9\n-12\n4\n', 'a raiz dupla desta equação é 0.666666')])
def test_raiz_dupla(script_runner, entrada, esperado):
    saida = script_runner.run("solution.py", stdin=entrada)
    assert script_runner.validar_saida(saida, esperado)

@pytest.mark.bateria(nome='duas_raizes', peso=0.4, descricao='Testando Bhaskara com 2 raízes reais')
@pytest.mark.parametrize("entrada, esperado", [('1\n-3\n-10\n', 'as raízes da equação são -2.0 e 5.0')])
def test_duas_raizes(script_runner, entrada, esperado):
    saida = script_runner.run("solution.py", stdin=entrada)
    assert script_runner.validar_saida(saida, esperado)
