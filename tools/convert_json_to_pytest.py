"""Conversor portátil do catálogo legado para especificações Pytest."""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def render(exercise):
    kind = exercise.get('tipo', 'script')
    function = exercise.get('nome_funcao')
    lines = ['# -*- coding: utf-8 -*-', 'import pytest']
    if kind == 'funcao':
        if not function or not function.isidentifier():
            raise ValueError('Nome de função inválido.')
        lines.append(f'from solution import {function}')
    lines.append('')
    for index, battery in enumerate(exercise.get('baterias', [])):
        name = battery.get('nome', f'bateria_{index + 1}')
        if not name.isidentifier():
            raise ValueError(f'Nome de bateria inválido: {name}')
        weight = battery.get('peso', 1.0)
        description = battery.get('descricao', name)
        tests = battery.get('testes', [])
        lines.append(f'@pytest.mark.bateria(nome={name!r}, peso={weight}, descricao={description!r})')
        if kind == 'script':
            cases = [(test.get('input', ''), test.get('expected', '')) for test in tests]
            lines.extend([
                f'@pytest.mark.parametrize("entrada, esperado", {cases!r})',
                f'def test_{name}(script_runner, entrada, esperado):',
                '    saida = script_runner.run("solution.py", stdin=entrada)',
                '    assert script_runner.validar_saida(saida, esperado)',
            ])
        elif kind == 'funcao':
            cases = [(test.get('args', []), test.get('expected')) for test in tests]
            lines.extend([
                f'@pytest.mark.parametrize("args, esperado", {cases!r})',
                f'def test_{name}(args, esperado):',
                f'    assert {function}(*args) == esperado',
            ])
        else:
            raise ValueError(f'Tipo inválido: {kind}')
        lines.append('')
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=ROOT / 'tests.json')
    parser.add_argument('--output', type=Path, default=ROOT / 'exercises')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--write', action='store_true', help='Regenera os arquivos de teste.')
    mode.add_argument('--check', action='store_true', help='Verifica sincronização sem alterar arquivos (padrão).')
    args = parser.parse_args()
    catalog = json.loads(args.source.read_text(encoding='utf-8'))
    different = []
    for identifier, config in catalog.items():
        if not identifier.isidentifier():
            raise ValueError(f'Identificador inválido: {identifier}')
        target = args.output / f'test_{identifier}.py'
        content = render(config)
        if args.write:
            args.output.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding='utf-8')
        elif not target.is_file() or target.read_text(encoding='utf-8') != content:
            different.append(identifier)
    if different:
        parser.exit(1, 'Especificações diferentes do JSON: ' + ', '.join(different) + '\n')
    print(f'{len(catalog)} especificações verificadas' + (' e regeneradas.' if args.write else '.'))


if __name__ == '__main__':
    main()
