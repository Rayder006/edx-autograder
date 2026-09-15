# -*- coding: utf-8 -*-
import pytest

@pytest.mark.bateria(nome='digito_dezenas', peso=0.8, descricao='Checando dígito das dezenas encontrado')
@pytest.mark.parametrize("entrada, esperado", [('12\n', 'O dígito das dezenas é 1'), ('2342342\n', 'O dígito das dezenas é 4'), ('3876482\n', 'O dígito das dezenas é 8'), ('444\n', 'O dígito das dezenas é 4'), ('577\n', 'O dígito das dezenas é 7'), ('100\n', 'O dígito das dezenas é 0'), ('1\n', 'O dígito das dezenas é 0')])
def test_digito_dezenas(script_runner, entrada, esperado):
    saida = script_runner.run("solution.py", stdin=entrada)
    assert script_runner.validar_saida(saida, esperado)

@pytest.mark.bateria(nome='mensagem_formato', peso=0.2, descricao='Checando se a mensagem completa está correta')
@pytest.mark.parametrize("entrada, esperado", [('1\n', 'O dígito das dezenas é 0')])
def test_mensagem_formato(script_runner, entrada, esperado):
    saida = script_runner.run("solution.py", stdin=entrada)
    assert script_runner.validar_saida(saida, esperado)
