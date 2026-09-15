# -*- coding: utf-8 -*-
import pytest
from solution import vogal

@pytest.mark.bateria(nome='vogais_minusculas', peso=0.3, descricao='Checando vogais minúsculas')
@pytest.mark.parametrize("args, esperado", [(['a'], True), (['e'], True), (['i'], True), (['o'], True), (['u'], True)])
def test_vogais_minusculas(args, esperado):
    assert vogal(*args) == esperado

@pytest.mark.bateria(nome='vogais_maiusculas', peso=0.3, descricao='Checando vogais maiúsculas')
@pytest.mark.parametrize("args, esperado", [(['A'], True), (['E'], True), (['I'], True), (['O'], True), (['U'], True)])
def test_vogais_maiusculas(args, esperado):
    assert vogal(*args) == esperado

@pytest.mark.bateria(nome='consoantes', peso=0.4, descricao='Checando consoantes')
@pytest.mark.parametrize("args, esperado", [(['b'], False), (['x'], False), (['Q'], False), (['F'], False), (['t'], False)])
def test_consoantes(args, esperado):
    assert vogal(*args) == esperado
