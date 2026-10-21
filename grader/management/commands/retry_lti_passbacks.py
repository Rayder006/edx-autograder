"""Recuperação explícita de notas pendentes sem executar código de alunos."""
from django.core.management.base import BaseCommand, CommandError
from django.db.models import F, Q

from grader.models import Submissao
from grader.views import _passback


class Command(BaseCommand):
    help = 'Retransmite notas LTI pendentes/falhas a partir dos destinos salvos no banco.'

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=100)
        parser.add_argument('--dry-run', action='store_true')

    def handle(self, *args, **options):
        if options['limit'] < 1:
            raise CommandError('--limit deve ser positivo.')
        pending = Submissao.objects.filter(
            Q(passback_success__isnull=True) | Q(passback_success=False)
            | Q(passback_score__lt=F('maior_nota') / 10.0),
        ).exclude(lti_context={}).order_by('pk')
        sent = failed = processed = 0
        for submission in pending.iterator():
            context = submission.lti_context
            if not context.get('lis_outcome_service_url') or not context.get('lis_result_sourcedid'):
                continue
            if processed >= options['limit']:
                break
            processed += 1
            if options['dry_run']:
                self.stdout.write(f'Submissão {submission.pk}: retorno de nota pendente.')
                continue
            if _passback(context, submission):
                sent += 1
            else:
                failed += 1
        if failed:
            raise CommandError(f'{sent} notas confirmadas; {failed} retornos falharam e continuam pendentes.')
        self.stdout.write(self.style.SUCCESS(
            'Validação sem envio concluída.' if options['dry_run'] else f'{sent} notas confirmadas.',
        ))
