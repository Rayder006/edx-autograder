# -*- coding: utf-8 -*-
import pytest

@pytest.mark.bateria(nome='perimetro', peso=0.4, descricao='Checando cálculo do perímetro')
@pytest.mark.parametrize("entrada, esperado", [('1\n', 'perímetro: 4 - área: 1'), ('2\n', 'perímetro: 8 - área: 4')])
def test_perimetro(script_runner, entrada, esperado):
    saida = script_runner.run("solution.py", stdin=entrada)
    assert script_runner.validar_saida(saida, esperado)

@pytest.mark.bateria(nome='area', peso=0.4, descricao='Checando cálculo da área')
@pytest.mark.parametrize("entrada, esperado", [('3\n', 'perímetro: 12 - área: 9'), ('4\n', 'perímetro: 16 - área: 16'), ('5\n', 'perímetro: 20 - área: 25')])
def test_area(script_runner, entrada, esperado):
    saida = script_runner.run("solution.py", stdin=entrada)
    assert script_runner.validar_saida(saida, esperado)

@pytest.mark.bateria(nome='apresentacao', peso=0.2, descricao='Checando apresentação da resposta de acordo com o enunciado')
@pytest.mark.parametrize("entrada, esperado", [('100\n', 'perímetro: 400 - área: 10000')])
def test_apresentacao(script_runner, entrada, esperado):
    saida = script_runner.run("solution.py", stdin=entrada)
    assert script_runner.validar_saida(saida, esperado)
