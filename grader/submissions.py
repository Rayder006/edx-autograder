"""Persistência compartilhada por formulário e submissão LTI direta."""
from django.db import transaction

from .models import Aluno, Submissao


def save_submission(aluno, exercise_id, code, result):
    score = round(result['nota'] * 10, 4)
    with transaction.atomic():
        # A linha do aluno existe antes da primeira tentativa. O lock também
        # serializa submissões concorrentes que ainda não têm Submissao.
        Aluno.objects.select_for_update().get(pk=aluno.pk)
        submission, created = Submissao.objects.get_or_create(
            aluno=aluno, exercise_id=exercise_id,
            defaults={
                'nota': score, 'maior_nota': score, 'student_code': code,
                'resultado_json': result, 'tentativas': 1,
            },
        )
        if not created:
            submission.nota = score
            submission.maior_nota = max(score, submission.maior_nota)
            submission.tentativas += 1
            submission.student_code = code
            submission.resultado_json = result
            submission.save()
    return submission


def saved_result(submission):
    import json
    result = submission.resultado_json
    if isinstance(result, str):
        result = json.loads(result)
    return result if isinstance(result, dict) else {}


def display_result(result):
    """O valor por bateria é exibido uma vez; casos não têm peso individual."""
    for battery in result.get('baterias', []):
        battery['peso_exibicao'] = f"{battery.get('peso', 0) * 10:.1f}"
    for case in result.get('detalhes', []):
        if 'peso' in case and not result.get('baterias'):
            case['peso_exibicao'] = f"{case['peso'] * 10:.1f}"
        else:
            case.pop('peso_exibicao', None)
    return result
