from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.conf import settings
from django.db.migrations.executor import MigrationExecutor
import os

from grader.views import executar_avaliacao
from grader.catalog import exercises
from grader.lti_debug import obter_lti_passports


class Command(BaseCommand):
    help = 'Verifica banco e avaliação real em Docker sem criar alunos ou notas.'

    def handle(self, *args, **options):
        if not settings.DEBUG and not (
            obter_lti_passports()
            or (os.environ.get('LTI_CONSUMER_KEY') and os.environ.get('LTI_SHARED_SECRET'))
        ):
            raise CommandError('Configure LTI_PASSPORTS ou LTI_CONSUMER_KEY e LTI_SHARED_SECRET.')
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
        executor = MigrationExecutor(connection)
        if executor.migration_plan(executor.loader.graph.leaf_nodes()):
            raise CommandError('Há migrações pendentes. Execute migrate antes de liberar os alunos.')
        self.stdout.write(f'Banco acessível: {connection.vendor}')
        result = executar_avaliacao(
            'n = int(input())\nprint(f"O dígito das dezenas é {(n // 10) % 10}")\n',
            'week_2_dezenas',
            exercises()['week_2_dezenas'],
        )
        if not result.get('sucesso') or result.get('nota') != 1:
            raise CommandError(f'Correção de diagnóstico falhou: {result}')
        engine = os.environ.get('AUTOGRADER_ENGINE', 'pytest')
        self.stdout.write(self.style.SUCCESS(f'Docker e motor {engine} operacionais: nota 1.0.'))
