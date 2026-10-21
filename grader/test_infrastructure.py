"""Regressões de instalação, isolamento dos dados e recuperação LTI."""
import io
import json
import os
import subprocess
import tempfile
import time
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

import requests
from requests_oauthlib import OAuth1
from django.core import signing
from django.core.management import call_command, CommandError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from grader.models import Aluno, Submissao, LTILaunchNonce
from grader.submissions import lti_scope, save_submission
from grader.views import enviar_nota_ao_edx


KEY, SECRET = 'infrastructure-key', 'infrastructure-secret'
ROOT = Path(__file__).resolve().parent.parent


def report(score):
    return {'sucesso': True, 'nota': score, 'detalhes': [], 'baterias': []}


class LTIInfrastructureTests(TestCase):
    def setUp(self):
        env = patch.dict(os.environ, {
            'LTI_PASSPORTS': json.dumps({KEY: SECRET, 'other-key': SECRET}),
            'LTI_BYPASS_SIGNATURE_VERIFICATION': '0', 'LTI_FORCE_EVALUATION_SCORE': '',
        })
        env.start()
        self.addCleanup(env.stop)
        self.params = {
            'oauth_consumer_key': KEY, 'user_id': 'infrastructure-user',
            'context_id': 'course-one', 'resource_link_id': 'component-one',
            'custom_exercise_id': 'week_2_dezenas',
            'lis_outcome_service_url': 'https://edx.example/outcomes',
            'lis_result_sourcedid': 'opaque:%/&resultado',
        }

    def prepare(self, *, timestamp=None, nonce=None, key=KEY, **params):
        payload = {**self.params, **params}
        payload.pop('oauth_consumer_key')
        return requests.Request(
            'POST', 'http://testserver/lti/avaliacao/', data=payload,
            auth=OAuth1(key, SECRET, signature_type='body', timestamp=timestamp, nonce=nonce),
        ).prepare()

    def launch(self, **params):
        return self.send(self.prepare(**params))

    def send(self, prepared):
        return self.client.post('/lti/avaliacao/', prepared.body,
                                content_type='application/x-www-form-urlencoded')

    def submit(self, params=None, code='print(1)'):
        return self.client.post('/lti/avaliacao/', {
            'lti_token': signing.dumps(params or self.params), 'custom_student_code': code,
        })

    def test_launch_replay_is_rejected(self):
        prepared = self.prepare()
        self.assertEqual(self.send(prepared).status_code, 200)
        self.assertEqual(self.send(prepared).status_code, 403)
        self.assertEqual(LTILaunchNonce.objects.count(), 1)

    def test_old_or_future_timestamp_is_rejected(self):
        for delta in (-6000, 6000):
            self.assertEqual(self.launch(timestamp=str(int(time.time()) + delta)).status_code, 403)
        self.assertFalse(Aluno.objects.exists())

    def test_nonce_is_scoped_by_consumer(self):
        self.assertEqual(self.launch(nonce='same-nonce').status_code, 200)
        self.assertEqual(self.launch(nonce='same-nonce', key='other-key').status_code, 200)
        self.assertEqual(LTILaunchNonce.objects.count(), 2)

    def test_expired_nonces_are_cleaned(self):
        LTILaunchNonce.objects.create(digest='expired', expires_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(self.launch().status_code, 200)
        self.assertFalse(LTILaunchNonce.objects.filter(pk='expired').exists())

    def test_external_https_proxy_url_is_used_for_launch_signature(self):
        prepared = requests.Request(
            'POST', 'https://localhost/lti/avaliacao/', data=self.params,
            auth=OAuth1(KEY, SECRET, signature_type='body'),
        ).prepare()
        response = self.client.post('/lti/avaliacao/', prepared.body,
                                    content_type='application/x-www-form-urlencoded',
                                    HTTP_X_FORWARDED_HOST='localhost', HTTP_X_FORWARDED_PROTO='https')
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('X-Frame-Options', response.headers)

    @patch('grader.views.executar_avaliacao', return_value=report(.8))
    @patch('grader.views.enviar_nota_ao_edx', return_value=True)
    def test_courses_components_and_consumers_have_independent_grades(self, send, evaluate):
        contexts = [self.params, {**self.params, 'context_id': 'course-two'},
                    {**self.params, 'resource_link_id': 'component-two'},
                    {**self.params, 'oauth_consumer_key': 'other-key'}]
        for context in contexts:
            self.assertEqual(self.submit(context).status_code, 200)
        self.assertEqual(Submissao.objects.count(), 4)
        self.assertEqual(list(Submissao.objects.values_list('tentativas', flat=True)), [1] * 4)

    @patch('grader.views.executar_avaliacao', return_value=report(1))
    @patch('grader.views.enviar_nota_ao_edx', return_value=True)
    def test_maximum_in_other_course_does_not_block_correction(self, send, evaluate):
        self.assertEqual(self.submit().status_code, 200)
        self.assertEqual(self.submit({**self.params, 'context_id': 'other-course'}).status_code, 200)
        self.assertEqual(evaluate.call_count, 2)

    def test_legacy_record_is_adopted_only_once(self):
        aluno = Aluno.objects.create(user_id=self.params['user_id'])
        original = save_submission(aluno, 'week_2_dezenas', 'old code', report(.85))
        self.assertEqual(self.launch().context['maior_nota'], 8.5)
        self.assertEqual(self.launch(context_id='other-course').context['maior_nota'], 0)
        original.refresh_from_db()
        self.assertEqual(original.lti_scope, lti_scope(self.params))
        self.assertEqual(original.tentativas, 1)
        self.assertEqual(original.student_code, 'old code')

    @patch('grader.views.executar_avaliacao', return_value=report(.8))
    @patch('grader.views.enviar_nota_ao_edx', return_value=False)
    def test_failed_callback_is_persisted_and_survives_reopen(self, send, evaluate):
        self.assertEqual(self.submit().status_code, 200)
        submission = Submissao.objects.get()
        self.assertIs(submission.passback_success, False)
        self.assertIsNotNone(submission.passback_attempted_at)
        self.assertEqual(submission.lti_context['lis_result_sourcedid'], self.params['lis_result_sourcedid'])
        self.assertNotIn('oauth_signature', submission.lti_context)
        self.assertContains(self.launch(), 'Reenviar nota ao EdX')

    @patch('grader.views.executar_avaliacao', return_value=report(.8))
    @patch('grader.views.enviar_nota_ao_edx', return_value=True)
    def test_successful_callback_persisted_and_not_offered_again_on_reopen(self, send, evaluate):
        self.submit()
        submission = Submissao.objects.get()
        self.assertIs(submission.passback_success, True)
        self.assertEqual(submission.passback_score, .8)
        self.assertNotContains(self.launch(), 'Reenviar nota ao EdX')

    @patch('grader.views.executar_avaliacao', return_value=report(.8))
    @patch('grader.views.enviar_nota_ao_edx', return_value=True)
    def test_new_outcome_identifier_is_remembered_without_grading_again(self, send, evaluate):
        self.submit()
        self.assertContains(self.launch(lis_result_sourcedid='new-result'), 'Reenviar nota ao EdX')
        submission = Submissao.objects.get()
        self.assertEqual(submission.lti_context['lis_result_sourcedid'], 'new-result')
        self.assertIsNone(submission.passback_success)
        self.assertEqual(submission.tentativas, 1)

    @patch('grader.views.executar_avaliacao', return_value=report(.8))
    @patch('grader.views.enviar_nota_ao_edx', side_effect=[False, True])
    def test_management_retry_uses_saved_target_and_does_not_regrade(self, send, evaluate):
        self.submit()
        call_command('retry_lti_passbacks', stdout=io.StringIO())
        submission = Submissao.objects.get()
        self.assertIs(submission.passback_success, True)
        self.assertEqual(submission.tentativas, 1)
        self.assertEqual(evaluate.call_count, 1)
        self.assertEqual(send.call_args.args[:3], (
            self.params['lis_outcome_service_url'], self.params['lis_result_sourcedid'], .8,
        ))
        call_command('retry_lti_passbacks', stdout=io.StringIO())
        self.assertEqual(send.call_count, 2)

    @patch('grader.views.executar_avaliacao', return_value=report(.8))
    @patch('grader.views.enviar_nota_ao_edx', return_value=False)
    def test_management_dry_run_never_sends_and_failed_retry_is_reported(self, send, evaluate):
        self.submit()
        call_command('retry_lti_passbacks', dry_run=True, stdout=io.StringIO())
        self.assertEqual(send.call_count, 1)
        with self.assertRaises(CommandError):
            call_command('retry_lti_passbacks', stdout=io.StringIO())

    @patch('grader.views.executar_avaliacao', return_value=report(.8))
    @patch('grader.views.enviar_nota_ao_edx', side_effect=ValueError('bad configuration'))
    def test_unexpected_callback_error_keeps_grade_and_marks_retry(self, send, evaluate):
        self.assertEqual(self.submit().status_code, 200)
        submission = Submissao.objects.get()
        self.assertEqual(submission.maior_nota, 8)
        self.assertIs(submission.passback_success, False)

    @patch('grader.views.enviar_nota_ao_edx')
    @patch('grader.views.executar_avaliacao', return_value=report(float('nan')))
    def test_invalid_grade_is_not_persisted_or_sent(self, evaluate, send):
        self.assertEqual(self.submit().status_code, 503)
        self.assertFalse(Submissao.objects.exists())
        send.assert_not_called()

    def test_database_prevents_duplicate_scoped_submissions(self):
        aluno = Aluno.objects.create(user_id='unique-test')
        save_submission(aluno, 'week_2_dezenas', 'pass', report(.5), scope='one')
        with self.assertRaises(IntegrityError), transaction.atomic():
            Submissao.objects.create(aluno=aluno, exercise_id='week_2_dezenas', lti_scope='one')

    @patch('grader.views.executar_avaliacao')
    def test_oversized_code_and_file_rejected_before_evaluation(self, evaluate):
        self.assertEqual(self.submit(code='a' * (256 * 1024 + 1)).status_code, 413)
        response = self.client.post('/lti/avaliacao/', {
            'lti_token': signing.dumps(self.params),
            'code_file': SimpleUploadedFile('large.py', b'a' * (256 * 1024 + 1)),
        })
        self.assertEqual(response.status_code, 413)
        evaluate.assert_not_called()

    @patch('grader.views.executar_avaliacao', return_value=report(.8))
    @patch('grader.views.enviar_nota_ao_edx', side_effect=[False, True])
    def test_retry_limit_does_not_get_stuck_on_non_graded_launches(self, send, evaluate):
        # Contextos sem callback não podem consumir o limite antes dos pendentes.
        aluno = Aluno.objects.create(user_id='no-outcomes')
        save_submission(aluno, 'week_2_dezenas', 'pass', report(.5), params={
            'oauth_consumer_key': KEY, 'context_id': 'ungraded',
        })
        self.submit()
        call_command('retry_lti_passbacks', limit=1, stdout=io.StringIO())
        self.assertEqual(send.call_count, 2)


class PassbackEnvironmentTests(SimpleTestCase):
    @patch('grader.views.requests.Session.send')
    def test_infrastructure_ca_and_proxy_are_used_without_disabling_tls(self, send):
        response = requests.Response()
        response.status_code = 200
        response._content = b'<imsx_POXEnvelopeResponse><imsx_statusInfo><imsx_codeMajor>success</imsx_codeMajor></imsx_statusInfo></imsx_POXEnvelopeResponse>'
        send.return_value = response
        with patch.dict(os.environ, {
            'REQUESTS_CA_BUNDLE': '/srv/certificates/usp.pem',
            'HTTPS_PROXY': 'http://proxy.example:3128', 'NO_PROXY': '',
        }):
            self.assertTrue(enviar_nota_ao_edx('https://edx.example/grades', 'opaque', .5, KEY, SECRET))
        self.assertEqual(send.call_args.kwargs['verify'], '/srv/certificates/usp.pem')
        self.assertEqual(send.call_args.kwargs['proxies']['https'], 'http://proxy.example:3128')
        self.assertIs(send.call_args.kwargs['allow_redirects'], False)

    @patch('grader.views.requests.Session.send')
    def test_non_outcomes_xml_cannot_confirm_a_grade(self, send):
        response = requests.Response()
        response.status_code = 200
        response._content = b'<html><imsx_codeMajor>success</imsx_codeMajor></html>'
        send.return_value = response
        self.assertFalse(enviar_nota_ao_edx('https://edx.example/grades', 'opaque', .5, KEY, SECRET))


class InstallationTests(SimpleTestCase):
    def wrapper(self, *args, configured_uid='', old_compose=False, old_environment=False, tmp_override=None):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        directory = Path(temporary.name)
        env_file = directory / 'test.env'
        env_file.write_text('UNTRUSTED=$(touch should-never-exist)\n')
        docker = directory / 'docker'
        docker.write_text('''#!/bin/sh
case "$*" in
    'compose version') exit 0 ;;
    'compose config --help')
        if [ "$TEST_OLD_ENVIRONMENT" = 1 ]; then echo old; else echo --environment; fi
        exit 0 ;;
    *'config --environment')
        printf '%s\\n' "AUTOGRADER_WEB_UID=$TEST_CONFIGURED_UID" "AUTOGRADER_DOCKER_GID=987" "AUTOGRADER_TMP_DIR_HOST=$TEST_TMP_DIR"
        exit 0 ;;
    'compose up --help')
        if [ "$TEST_OLD_COMPOSE" = 1 ]; then echo old; else echo --wait-timeout; fi
        exit 0 ;;
    *) printf '%s\\n' "runtime=$AUTOGRADER_WEB_UID:$AUTOGRADER_WEB_GID socket_group=$AUTOGRADER_DOCKER_GID" ;;
esac
''')
        docker.chmod(0o755)
        fake_id = directory / 'id'
        fake_id.write_text('#!/bin/sh\nif [ "$1" = -u ]; then echo 1005; else echo 1006; fi\n')
        fake_id.chmod(0o755)
        completed = subprocess.run(
            ['sh', str(ROOT / 'tools/compose.sh'), *args], cwd=directory,
            capture_output=True, text=True,
            env={**os.environ, 'PATH': str(directory) + os.pathsep + os.environ['PATH'],
                 'ENV_FILE': str(env_file), 'TEST_CONFIGURED_UID': configured_uid,
                 'TEST_TMP_DIR': str(tmp_override or directory / 'grading'),
                 'TEST_OLD_COMPOSE': '1' if old_compose else '0',
                 'TEST_OLD_ENVIRONMENT': '1' if old_environment else '0'},
        )
        self.assertFalse((directory / 'should-never-exist').exists())
        return completed, directory

    def test_compose_uses_service_uid_and_socket_group_without_sourcing_env(self):
        completed, directory = self.wrapper('up', '-d', 'web')
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn('runtime=1005:1006 socket_group=987', completed.stdout)
        self.assertTrue((directory / 'grading').is_dir())

    def test_compose_rejects_root_instead_of_creating_root_owned_files(self):
        completed, directory = self.wrapper('up', configured_uid='0')
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn('Não execute a instalação como root', completed.stderr)
        self.assertFalse((directory / 'grading').exists())

    def test_compose_rejects_another_users_uid(self):
        completed, directory = self.wrapper('up', configured_uid='1007')
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn('mesmo UID/GID', completed.stderr)

    def test_old_compose_has_actionable_error(self):
        completed, directory = self.wrapper('up', old_compose=True)
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn('v2.28+', completed.stderr)

    def test_missing_environment_flag_has_actionable_error(self):
        completed, directory = self.wrapper('up', old_environment=True)
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn('v2.28+', completed.stderr)
        self.assertFalse((directory / 'grading').exists())

    def test_compose_refuses_broad_or_relative_temp_directory(self):
        for path in ['/tmp', 'relative-folder']:
            completed, directory = self.wrapper('up', tmp_override=path)
            self.assertNotEqual(completed.returncode, 0)

    def test_venv_failure_is_not_reported_as_success(self):
        with tempfile.TemporaryDirectory() as directory:
            completed = subprocess.run(
                ['make', '-f', str(ROOT / 'Makefile'), 'venv', 'HOST_PYTHON=false'],
                cwd=directory, capture_output=True, text=True,
            )
        self.assertNotEqual(completed.returncode, 0)
        self.assertNotIn('Ambiente virtual criado!', completed.stdout)

    def test_missing_env_is_not_created(self):
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / 'missing.env'
            completed = subprocess.run(
                ['make', 'setup-env', f'ENV_FILE={missing}'],
                cwd=ROOT, capture_output=True, text=True,
            )
            self.assertNotEqual(completed.returncode, 0)
            self.assertFalse(missing.exists())

    def test_compose_wrapper_shell_syntax(self):
        subprocess.run(['sh', '-n', str(ROOT / 'tools/compose.sh')], check=True)


class DoctorTests(TestCase):
    @patch('grader.management.commands.check_autograder.executar_avaliacao', return_value=report(1))
    def test_doctor_dispatches_configured_engine_without_creating_records(self, evaluate):
        with patch.dict(os.environ, {'AUTOGRADER_ENGINE': 'docker', 'LTI_PASSPORTS': f'{KEY}:{SECRET}'}):
            output = io.StringIO()
            call_command('check_autograder', stdout=output)
        self.assertIn('motor docker operacionais', output.getvalue())
        evaluate.assert_called_once()
        self.assertFalse(Aluno.objects.exists())

    @patch('grader.management.commands.check_autograder.MigrationExecutor')
    @patch('grader.management.commands.check_autograder.executar_avaliacao')
    def test_pending_migrations_fail_before_grading(self, evaluate, executor):
        executor.return_value.migration_plan.return_value = ['pending']
        with patch.dict(os.environ, {'LTI_PASSPORTS': f'{KEY}:{SECRET}'}), self.assertRaisesMessage(CommandError, 'migrações pendentes'):
            call_command('check_autograder', stdout=io.StringIO())
        evaluate.assert_not_called()
