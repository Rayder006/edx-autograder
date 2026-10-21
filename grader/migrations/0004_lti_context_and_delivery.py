from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('grader', '0003_preserve_existing_submissions')]

    operations = [
        migrations.CreateModel(
            name='LTILaunchNonce',
            fields=[
                ('digest', models.CharField(max_length=64, primary_key=True, serialize=False)),
                ('expires_at', models.DateTimeField(db_index=True)),
            ],
        ),
        migrations.AlterUniqueTogether(name='submissao', unique_together=set()),
        migrations.AddField(
            model_name='submissao', name='lti_scope',
            field=models.CharField(blank=True, default='', max_length=64),
        ),
        migrations.AddField(
            model_name='submissao', name='lti_context',
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name='submissao', name='passback_attempted_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='submissao', name='passback_score',
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='submissao', name='passback_success',
            field=models.BooleanField(default=None, null=True),
        ),
        migrations.AlterUniqueTogether(
            name='submissao', unique_together={('aluno', 'exercise_id', 'lti_scope')},
        ),
    ]
