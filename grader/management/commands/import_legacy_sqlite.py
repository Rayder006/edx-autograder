"""Importa alunos/submissões de um SQLite antigo sem modificar a origem."""
import json
import math
import sqlite3
from pathlib import Path
from urllib.parse import quote

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from grader.models import Aluno, Submissao


def timestamp(value):
    parsed = parse_datetime(value) if value else None
    if parsed and timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed, timezone.get_default_timezone())
    return parsed


class Command(BaseCommand):
    help = 'Importa dados do SQLite antigo em banco vazio. A origem é aberta somente para leitura.'

    def add_arguments(self, parser):
        parser.add_argument('--source', required=True, help='Caminho do backup SQLite.')
        parser.add_argument('--dry-run', action='store_true', help='Valida tudo e desfaz a importação.')

    def handle(self, *args, **options):
        source = Path(options['source']).resolve()
        if not source.is_file():
            raise CommandError('Arquivo SQLite de origem não encontrado.')
        try:
            legacy = sqlite3.connect(f'file:{quote(str(source))}?mode=ro', uri=True)
            legacy.row_factory = sqlite3.Row
            try:
                users = list(legacy.execute('SELECT * FROM grader_aluno'))
                submissions = list(legacy.execute('SELECT * FROM grader_submissao'))
            finally:
                legacy.close()
            with transaction.atomic():
                if Aluno.objects.exists() or Submissao.objects.exists():
                    raise CommandError('O destino já contém alunos ou submissões. Use um banco vazio.')
                for row in users:
                    user = Aluno.objects.create(user_id=row['user_id'])
                    created = timestamp(row['created_at'])
                    if created:
                        Aluno.objects.filter(pk=user.pk).update(created_at=created)
                for raw in submissions:
                    row = dict(raw)
                    score = float(row.get('nota') or 0)
                    best = max(score, float(row.get('maior_nota') or 0))
                    if not math.isfinite(best) or not 0 <= score <= best <= 10:
                        raise CommandError('A origem contém uma nota fora do intervalo 0 a 10.')
                    report = row['resultado_json']
                    for _ in range(3):
                        if not isinstance(report, str):
                            break
                        report = json.loads(report)
                    if not isinstance(report, dict):
                        raise CommandError('A origem contém um relatório JSON inválido.')
                    submission = Submissao.objects.create(
                        aluno_id=row['aluno_id'], exercise_id=row['exercise_id'],
                        nota=score, maior_nota=best, tentativas=max(1, row.get('tentativas') or 1),
                        student_code=row['student_code'], resultado_json=report,
                    )
                    updated = timestamp(row.get('updated_at'))
                    created = timestamp(row.get('created_at')) or updated
                    dates = {}
                    if created:
                        dates['created_at'] = created
                    if updated:
                        dates['updated_at'] = updated
                    if dates:
                        Submissao.objects.filter(pk=submission.pk).update(**dates)
                if options['dry_run']:
                    transaction.set_rollback(True)
        except (sqlite3.Error, ValueError, TypeError) as exc:
            raise CommandError(f'Não foi possível importar o SQLite: {exc}') from exc
        action = 'Validação concluída (nenhum dado importado)' if options['dry_run'] else 'Importação concluída'
        self.stdout.write(self.style.SUCCESS(f'{action}: {len(users)} alunos e {len(submissions)} submissões.'))
