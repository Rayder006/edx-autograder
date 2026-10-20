"""Conserva notas e converte JSON legado ao atualizar instalações existentes."""
import json

from django.db import migrations, models


def preserve_submissions(apps, schema_editor):
    Submission = apps.get_model('grader', 'Submissao')
    for submission in Submission.objects.using(schema_editor.connection.alias).iterator():
        result = submission.resultado_json
        # Instalações intermediárias gravavam JSON serializado dentro do JSONField.
        for _ in range(3):
            if not isinstance(result, str):
                break
            try:
                result = json.loads(result)
            except (TypeError, ValueError):
                break
        if not isinstance(result, dict):
            result = {
                'sucesso': False, 'nota': submission.nota / 10.0,
                'erro': 'Relatório legado indisponível.', 'detalhes': [], 'baterias': [],
            }
        Submission.objects.using(schema_editor.connection.alias).filter(pk=submission.pk).update(
            maior_nota=max(submission.maior_nota, submission.nota),
            resultado_json=result,
        )


class Migration(migrations.Migration):
    dependencies = [('grader', '0002_submissao_created_at_submissao_maior_nota_and_more')]
    operations = [
        migrations.RunPython(preserve_submissions, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='submissao', name='created_at',
            field=models.DateTimeField(auto_now_add=True, blank=True, null=True),
        ),
    ]
