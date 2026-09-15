# -*- coding: utf-8 -*-
import pytest

@pytest.mark.bateria(nome='week_6_jogo_nim', peso=1.0, descricao='Testes para week_6_jogo_nim')
@pytest.mark.parametrize("entrada, esperado", [('1\n5\n3\n1\n', 'Fim do jogo! O computador ganhou!'), ('1\n9\n2\n1\n2\n2\n', 'Fim do jogo! O computador ganhou!'), ('2\n5\n3\n1\n6\n4\n1\n5\n3\n1\n', 'Placar: Você 0 X 3 Computador')])
def test_week_6_jogo_nim(script_runner, entrada, esperado):
    saida = script_runner.run("solution.py", stdin=entrada)
    assert script_runner.validar_saida(saida, esperado)
