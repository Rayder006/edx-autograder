# -*- coding: utf-8 -*-
import pytest

@pytest.mark.bateria(nome='week_7_retangulo_cheio', peso=1.0, descricao='Testes para week_7_retangulo_cheio')
@pytest.mark.parametrize("entrada, esperado", [('10\n3\n', '##########\n##########\n##########'), ('2\n2\n', '##\n##')])
def test_week_7_retangulo_cheio(script_runner, entrada, esperado):
    saida = script_runner.run("solution.py", stdin=entrada)
    assert script_runner.validar_saida(saida, esperado)
