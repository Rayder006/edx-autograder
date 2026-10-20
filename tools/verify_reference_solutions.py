"""Confere as soluções originais dos exercícios em containers Pytest reais."""
import argparse
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from grader.pytest_runner import avaliar_com_pytest


ALIASES = {
    'week_7_retangulo_cheio': 'week_7/respostas/imprime_retangulo_cheio.py',
    'week_7_retangulo_vazado': 'week_7/respostas/imprime_retangulo_vazado.py',
    'week_6_jogo_nim': 'jogo_nim/respostas/jogo_nim.py',
    'week_9_coh_piah': 'coh_piah/respostas/coh_piah.py',
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference-root', type=Path, default=ROOT / '.exercicios-coursera/programming_assignments/part_1')
    parser.add_argument('--exercise', help='Verifica apenas o identificador informado.')
    args = parser.parse_args()
    if not args.reference_root.is_dir():
        parser.error('Informe --reference-root com a pasta part_1 do material original do curso.')
    specs = sorted((ROOT / 'exercises').glob('test_*.py'))
    if args.exercise:
        specs = [spec for spec in specs if spec.stem == f'test_{args.exercise}']
    if not specs:
        parser.error('Não foram encontrados exercícios para verificar.')
    os.environ['AUTOGRADER_ALLOW_LOCAL_FALLBACK'] = '0'
    passed = 0
    # As referências rodam em série para aferir os limites por aluno.
    for spec in specs:
        exercise = spec.stem.removeprefix('test_')
        _, week, name = exercise.split('_', 2)
        reference = args.reference_root / ALIASES.get(exercise, f'week_{week}/respostas/{name}.py')
        if not reference.is_file():
            print(f'{exercise}: referência ausente ({reference})')
            continue
        report = avaliar_com_pytest(reference.read_text(encoding='utf-8'), exercise)
        success = report.get('sucesso') and report.get('nota') == 1
        passed += bool(success)
        print(f'{exercise}: nota {report.get("nota")} — {"OK" if success else "FALHOU"}', flush=True)
        if not success:
            failures = [case.get('erro', '') for case in report.get('detalhes', []) if not case.get('passou')]
            print((report.get('erro') or '\n'.join(failures))[:4000])
    print(f'{passed}/{len(specs)} exercícios com nota máxima.')
    return 0 if passed == len(specs) else 1


if __name__ == '__main__':
    sys.exit(main())
