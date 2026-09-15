# -*- coding: utf-8 -*-
import pytest

@pytest.mark.bateria(nome='paridade_positivos', peso=0.5, descricao='Checando paridade dos números positivos')
@pytest.mark.parametrize("entrada, esperado", [('1\n', 'ímpar'), ('2\n', 'par'), ('3\n', 'ímpar'), ('4\n', 'par'), ('100\n', 'par'), ('123123123\n', 'ímpar'), ('33\n', 'ímpar'), ('44\n', 'par')])
def test_paridade_positivos(script_runner, entrada, esperado):
    saida = script_runner.run("solution.py", stdin=entrada)
    assert script_runner.validar_saida(saida, esperado)

@pytest.mark.bateria(nome='paridade_negativos', peso=0.5, descricao='Checando paridade dos números negativos')
@pytest.mark.parametrize("entrada, esperado", [('-1\n', 'ímpar'), ('-10\n', 'par'), ('-11\n', 'ímpar'), ('-2\n', 'par')])
def test_paridade_negativos(script_runner, entrada, esperado):
    saida = script_runner.run("solution.py", stdin=entrada)
    assert script_runner.validar_saida(saida, esperado)
