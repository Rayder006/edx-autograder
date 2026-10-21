"""Persistência compartilhada por formulário e submissão LTI direta."""
import hashlib
import json
import math

from django.db import transaction

from .models import Aluno, Submissao


LTI_CONTEXT_FIELDS = (
    'oauth_consumer_key', 'context_id', 'resource_link_id',
    'lis_result_sourcedid', 'lis_outcome_service_url',
)


def lti_context(params):
    # Nunca guardar segredo, assinatura OAuth, token do formulário ou código aqui.
    return {key: params.get(key) for key in LTI_CONTEXT_FIELDS}


def lti_scope(params):
    identity = [params.get(key) or '' for key in (
        'oauth_consumer_key', 'context_id', 'resource_link_id',
    )]
    return hashlib.sha256(json.dumps(identity, ensure_ascii=False).encode()).hexdigest()


def get_submission(aluno, exercise_id, scope):
    with transaction.atomic():
        Aluno.objects.select_for_update().get(pk=aluno.pk)
        submission = Submissao.objects.filter(
            aluno=aluno, exercise_id=exercise_id, lti_scope=scope,
        ).first()
        if submission is None:
            # O banco antigo não tinha contexto LTI. A primeira reabertura
            # autenticada assume o registro legado uma única vez.
            submission = Submissao.objects.filter(
                aluno=aluno, exercise_id=exercise_id, lti_scope='',
            ).first()
            if submission:
                submission.lti_scope = scope
                submission.save(update_fields=['lti_scope'])
        return submission


def remember_lti_context(submission, params):
    with transaction.atomic():
        current = Submissao.objects.select_for_update().get(pk=submission.pk)
        context = lti_context(params)
        if current.lti_context != context:
            current.lti_context = context
            current.passback_success = None
            current.passback_score = None
            current.passback_attempted_at = None
            current.save(update_fields=[
                'lti_context', 'passback_success', 'passback_score', 'passback_attempted_at',
            ])
        return current


def save_submission(aluno, exercise_id, code, result, *, scope='', params=None):
    raw_score = result['nota']
    if (isinstance(raw_score, bool) or not isinstance(raw_score, (int, float))
            or not math.isfinite(raw_score) or not 0 <= raw_score <= 1):
        raise ValueError('A nota do corretor deve ser um número finito entre 0 e 1.')
    score = round(raw_score * 10, 4)
    with transaction.atomic():
        # A linha do aluno existe antes da primeira tentativa. O lock também
        # serializa submissões concorrentes que ainda não têm Submissao.
        Aluno.objects.select_for_update().get(pk=aluno.pk)
        submission, created = Submissao.objects.get_or_create(
            aluno=aluno, exercise_id=exercise_id, lti_scope=scope,
            defaults={
                'nota': score, 'maior_nota': score, 'student_code': code,
                'resultado_json': result, 'tentativas': 1,
                'lti_context': lti_context(params) if params else {},
            },
        )
        if not created:
            submission.nota = score
            submission.maior_nota = max(score, submission.maior_nota)
            submission.tentativas += 1
            submission.student_code = code
            submission.resultado_json = result
            if params:
                submission.lti_context = lti_context(params)
            submission.passback_success = None
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
