from django.db import models

class Aluno(models.Model):
    user_id = models.CharField(max_length=255, unique=True, primary_key=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.user_id

class Submissao(models.Model):
    aluno = models.ForeignKey(Aluno, on_delete=models.CASCADE, related_name='submissoes')
    exercise_id = models.CharField(max_length=255)
    nota = models.FloatField(default=0.0)  # nota na escala de 0.0 a 10.0
    student_code = models.TextField()
    resultado_json = models.TextField()   # Detalhes serializados em JSON da avaliação
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('aluno', 'exercise_id')

    def __str__(self):
        return f"{self.aluno.user_id} - {self.exercise_id} ({self.nota}/10.0)"
