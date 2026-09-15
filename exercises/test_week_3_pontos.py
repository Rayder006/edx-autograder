# -*- coding: utf-8 -*-
import pytest

@pytest.mark.bateria(nome='distancia_pontos', peso=1.0, descricao='Checando distância entre pontos')
@pytest.mark.parametrize("entrada, esperado", [('0\n0\n11\n0\n', 'longe'), ('1\n1\n1\n1\n', 'perto'), ('1\n2\n3\n4\n', 'perto'), ('-1\n-1\n-1\n-1\n', 'perto'), ('-1\n-2\n-3\n-4\n', 'perto'), ('-1\n2\n3\n-4\n', 'perto')])
def test_distancia_pontos(script_runner, entrada, esperado):
    saida = script_runner.run("solution.py", stdin=entrada)
    assert script_runner.validar_saida(saida, esperado)
