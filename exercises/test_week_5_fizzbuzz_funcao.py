# -*- coding: utf-8 -*-
import pytest
from solution import fizzbuzz

@pytest.mark.bateria(nome='fizz', peso=0.25, descricao='Checando se Fizz é identificado')
@pytest.mark.parametrize("args, esperado", [([3], 'Fizz'), ([6], 'Fizz'), ([93], 'Fizz')])
def test_fizz(args, esperado):
    assert fizzbuzz(*args) == esperado

@pytest.mark.bateria(nome='buzz', peso=0.25, descricao='Checando se Buzz é identificado')
@pytest.mark.parametrize("args, esperado", [([5], 'Buzz'), ([10], 'Buzz'), ([230], 'Buzz')])
def test_buzz(args, esperado):
    assert fizzbuzz(*args) == esperado

@pytest.mark.bateria(nome='fizzbuzz', peso=0.25, descricao='Checando se FizzBuzz é identificado')
@pytest.mark.parametrize("args, esperado", [([15], 'FizzBuzz'), ([225], 'FizzBuzz'), ([12345], 'FizzBuzz')])
def test_fizzbuzz(args, esperado):
    assert fizzbuzz(*args) == esperado

@pytest.mark.bateria(nome='numerico', peso=0.25, descricao='Checando retorno numérico')
@pytest.mark.parametrize("args, esperado", [([23], 23), ([101], 101), ([7], 7)])
def test_numerico(args, esperado):
    assert fizzbuzz(*args) == esperado
