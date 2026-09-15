# -*- coding: utf-8 -*-
import pytest

@pytest.mark.bateria(nome='conversao_numerica', peso=0.4, descricao='Verificando conversão numérica')
@pytest.mark.parametrize("entrada, esperado", [('Foo Bar\n29\nFevereiro\n1.342,52\n', 'Olá, Foo Bar\nA sua fatura com vencimento em 29 de Fevereiro no valor de R$ 1.342,52 está fechada.')])
def test_conversao_numerica(script_runner, entrada, esperado):
    saida = script_runner.run("solution.py", stdin=entrada)
    assert script_runner.validar_saida(saida, esperado)

@pytest.mark.bateria(nome='dados_incluidos', peso=0.4, descricao='Checando se os dados pedidos foram incluídos na resposta')
@pytest.mark.parametrize("entrada, esperado", [('John Doe\n31\nOutubro\n1,00\n', 'Olá, John Doe\nA sua fatura com vencimento em 31 de Outubro no valor de R$ 1,00 está fechada.'), ('Foo Bar\n29\nFevereiro\n1.342,52\n', 'Olá, Foo Bar\nA sua fatura com vencimento em 29 de Fevereiro no valor de R$ 1.342,52 está fechada.'), ('Pedro\n9\nJaneiro\n350,00\n', 'Olá, Pedro\nA sua fatura com vencimento em 9 de Janeiro no valor de R$ 350,00 está fechada.')])
def test_dados_incluidos(script_runner, entrada, esperado):
    saida = script_runner.run("solution.py", stdin=entrada)
    assert script_runner.validar_saida(saida, esperado)

@pytest.mark.bateria(nome='formato_resposta', peso=0.2, descricao='Verificando se a resposta segue o formato pedido no enunciado')
@pytest.mark.parametrize("entrada, esperado", [('Foo Bar\n29\nFevereiro\n1.342,52\n', 'Olá, Foo Bar\nA sua fatura com vencimento em 29 de Fevereiro no valor de R$ 1.342,52 está fechada.')])
def test_formato_resposta(script_runner, entrada, esperado):
    saida = script_runner.run("solution.py", stdin=entrada)
    assert script_runner.validar_saida(saida, esperado)
