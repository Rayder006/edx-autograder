from django.db import models

class Aluno(models.Model):
    user_id = models.CharField(max_length=255, unique=True, primary_key=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        return self.user_id

class Submissao(models.Model):
    aluno = models.ForeignKey(Aluno, on_delete=models.CASCADE, related_name='submissoes')
    exercise_id = models.CharField(max_length=255, db_index=True)
    # Uma atividade em outro curso/componente não pode herdar a nota daqui.
    lti_scope = models.CharField(max_length=64, default='', blank=True)
    nota = models.FloatField(default=0.0)         # Nota da tentativa atual (0.0 a 10.0)
    maior_nota = models.FloatField(default=0.0)   # Maior nota obtida (0.0 a 10.0)
    tentativas = models.IntegerField(default=1)   # Quantidade de tentativas realizadas pelo aluno
    student_code = models.TextField()
    resultado_json = models.JSONField(default=dict) # Detalhes da avaliação em JSON nativo
    lti_context = models.JSONField(default=dict, blank=True)
    passback_success = models.BooleanField(null=True, default=None)
    passback_score = models.FloatField(null=True, blank=True)
    passback_attempted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True, db_index=True)

    class Meta:
        unique_together = ('aluno', 'exercise_id', 'lti_scope')
        indexes = [
            models.Index(fields=['aluno', 'exercise_id']),
            models.Index(fields=['exercise_id', 'maior_nota']),
            models.Index(fields=['updated_at']),
        ]

    def __str__(self):
        return f"{self.aluno.user_id} - {self.exercise_id} (atual: {self.nota}, maior: {self.maior_nota}/10.0)"


class LTILaunchNonce(models.Model):
    """Proteção contra replay, compartilhada pelos workers via banco."""
    digest = models.CharField(max_length=64, primary_key=True)
    expires_at = models.DateTimeField(db_index=True)
