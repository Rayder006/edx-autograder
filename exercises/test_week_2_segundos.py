# -*- coding: utf-8 -*-
import pytest

@pytest.mark.bateria(nome='conversao_segundos', peso=1.0, descricao='Checando conversão de segundos')
@pytest.mark.parametrize("entrada, esperado", [('123456323456\n', '1428892 dias, 16 horas, 4 minutos e 16 segundos.'), ('1\n', '0 dias, 0 horas, 0 minutos e 1 segundos.'), ('3600\n', '0 dias, 1 horas, 0 minutos e 0 segundos.')])
def test_conversao_segundos(script_runner, entrada, esperado):
    saida = script_runner.run("solution.py", stdin=entrada)
    assert script_runner.validar_saida(saida, esperado)
