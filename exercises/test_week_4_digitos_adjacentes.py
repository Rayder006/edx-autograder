# -*- coding: utf-8 -*-
import pytest

@pytest.mark.bateria(nome='multiplos_digitos', peso=0.6, descricao='Checando dígitos adjacentes - múltiplos dígitos')
@pytest.mark.parametrize("entrada, esperado", [('11\n', 'sim'), ('111\n', 'sim'), ('54\n', 'não'), ('200\n', 'sim'), ('2000\n', 'sim'), ('20000\n', 'sim'), ('783345216\n', 'sim'), ('123456789\n', 'não'), ('123123123\n', 'não'), ('121212\n', 'não')])
def test_multiplos_digitos(script_runner, entrada, esperado):
    saida = script_runner.run("solution.py", stdin=entrada)
    assert script_runner.validar_saida(saida, esperado)

@pytest.mark.bateria(nome='um_digito', peso=0.4, descricao='Checando dígitos adjacentes - só um dígito')
@pytest.mark.parametrize("entrada, esperado", [('0\n', 'não'), ('4\n', 'não'), ('9\n', 'não')])
def test_um_digito(script_runner, entrada, esperado):
    saida = script_runner.run("solution.py", stdin=entrada)
    assert script_runner.validar_saida(saida, esperado)
