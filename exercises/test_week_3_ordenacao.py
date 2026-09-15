# -*- coding: utf-8 -*-
import pytest

@pytest.mark.bateria(nome='ordenacao', peso=1.0, descricao='Checando ordenação')
@pytest.mark.parametrize("entrada, esperado", [('1\n2\n3\n', 'crescente'), ('3\n4\n2\n', 'não está em ordem crescente'), ('4\n3\n2\n', 'não está em ordem crescente'), ('10\n21\n43\n', 'crescente'), ('3\n-1\n7\n', 'não está em ordem crescente'), ('-8\n-1\n0\n', 'crescente'), ('-8\n-3\n-1\n', 'crescente'), ('-3\n2\n5\n', 'crescente')])
def test_ordenacao(script_runner, entrada, esperado):
    saida = script_runner.run("solution.py", stdin=entrada)
    assert script_runner.validar_saida(saida, esperado)
