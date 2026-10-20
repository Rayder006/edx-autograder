from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.conf import settings
import os

from grader.pytest_runner import avaliar_com_pytest
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
        self.stdout.write(f'Banco acessível: {connection.vendor}')
        result = avaliar_com_pytest(
            'n = int(input())\nprint(f"O dígito das dezenas é {(n // 10) % 10}")\n',
            'week_2_dezenas',
        )
        if not result.get('sucesso') or result.get('nota') != 1:
            raise CommandError(f'Correção de diagnóstico falhou: {result}')
        self.stdout.write(self.style.SUCCESS('Docker e Pytest operacionais: nota 1.0.'))
