import json
import os
import sqlite3
import tempfile
import threading
from html.parser import HTMLParser
from pathlib import Path
from unittest import skipUnless
from unittest.mock import patch

import docker
import pytest
import requests
from requests_oauthlib import OAuth1
from django.conf import settings
from django.core import signing
from django.core.management import call_command, CommandError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import close_old_connections, connection, connections
from django.db.migrations.executor import MigrationExecutor
from django.test import SimpleTestCase, TestCase, TransactionTestCase, override_settings

from grader.lti_debug import obter_lti_passports
from grader.models import Aluno, Submissao
from grader.output_validation import validar_saida_script
from grader.pytest_runner import avaliar_com_pytest
from grader.submissions import save_submission
from grader.views import enviar_nota_ao_edx, _passback


KEY = 'regression-key'
SECRET = 'regression-secret'
SOLUTION = 'n = int(input())\nprint(f"O dígito das dezenas é {(n // 10) % 10}")\n'


def result(score):
    return {'sucesso': True, 'nota': score, 'baterias': [], 'detalhes': [
        {'descricao': 'Caso de teste', 'passou': score == 1},
    ]}


class FormParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.fields = {}
        self.action = ''

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'form':
            self.action = attrs.get('action', '')
        if tag == 'input' and 'name' in attrs:
            self.fields[attrs['name']] = attrs.get('value', '')


class OutputValidationTests(SimpleTestCase):
    def test_accents_case_prompts_and_spaces(self):
        self.assertTrue(validar_saida_script('Digite: O DIGITO  das dezenas é 4!', 'O dígito das dezenas é 4'))

    def test_multiline_currency(self):
        self.assertTrue(validar_saida_script('Olá, Ana\nFatura: R$ 1.342,52.', 'Olá, Ana\nFatura: R$ 1.342,52'))

    def test_hash_rectangles(self):
        self.assertTrue(validar_saida_script('###\n# #\n###\n', '###\n# #\n###'))
        self.assertFalse(validar_saida_script('####\n####\n', '###\n###'))

    def test_negative_sign_is_significant(self):
        self.assertFalse(validar_saida_script('2.0', '-2.0'))

    def test_whole_numbers_and_words(self):
        self.assertFalse(validar_saida_script('10', '1'))
        self.assertFalse(validar_saida_script('FizzBuzz', 'Fizz'))

    def test_historical_truncated_decimal(self):
        self.assertTrue(validar_saida_script('a raiz é 0.6666666666666666', 'a raiz é 0.666666'))

    def test_non_prime_is_not_prime(self):
        self.assertFalse(validar_saida_script('não primo', 'primo'))
        self.assertTrue(validar_saida_script('O número é primo!', 'primo'))


class DockerConfigurationTests(SimpleTestCase):
    def test_sibling_volume_path_translation(self):
        from grader.docker_runtime import host_path
        with patch.dict(os.environ, {'AUTOGRADER_TMP_DIR': '/tmp/autograder', 'AUTOGRADER_TMP_DIR_HOST': '/srv/autograder'}):
            self.assertEqual(host_path('/tmp/autograder/job/result'), '/srv/autograder/job/result')
            with self.assertRaises(ValueError):
                host_path('/another/path')

    @patch('grader.pytest_runner.docker.from_env')
    @patch('grader.pytest_runner.time.monotonic', side_effect=[0, 31])
    @patch('grader.pytest_runner.subprocess.Popen')
    def test_timeout_removes_container_without_local_reexecution(self, run, clock, from_env):
        container = from_env.return_value.containers.run.return_value
        container.status = 'running'
        with patch.dict(os.environ, {'AUTOGRADER_ALLOW_LOCAL_FALLBACK': '1'}):
            report = avaliar_com_pytest(SOLUTION, 'week_2_dezenas')
        self.assertEqual(report['nota'], 0)
        self.assertIn('Tempo limite', report['erro'])
        container.remove.assert_called_once_with(force=True)
        run.assert_not_called()


class CatalogTests(SimpleTestCase):
    def test_legacy_and_pytest_specs_are_synchronized(self):
        from tools.convert_json_to_pytest import render
        catalog = json.loads((settings.BASE_DIR / 'tests.json').read_text())
        for exercise, config in catalog.items():
            with self.subTest(exercise=exercise):
                self.assertAlmostEqual(sum(b['peso'] for b in config['baterias']), 1)
                actual = (settings.BASE_DIR / 'exercises' / f'test_{exercise}.py').read_text()
                self.assertEqual(actual, render(config))

    def test_seconds_and_digit_sum_expected_results(self):
        catalog = json.loads((settings.BASE_DIR / 'tests.json').read_text())
        for battery in catalog['week_4_soma_digitos']['baterias']:
            for case in battery['testes']:
                self.assertEqual(int(case['expected']), sum(map(int, case['input'].strip())))
        for battery in catalog['week_2_segundos']['baterias']:
            for case in battery['testes']:
                days, remainder = divmod(int(case['input']), 86400)
                hours, remainder = divmod(remainder, 3600)
                minutes, seconds = divmod(remainder, 60)
                self.assertEqual(case['expected'], f'{days} dias, {hours} horas, {minutes} minutos e {seconds} segundos.')


class PassportTests(SimpleTestCase):
    def test_example_key_secret_format(self):
        with patch.dict(os.environ, {'LTI_PASSPORTS': 'key_prod:secret_prod_compartilhada'}):
            self.assertEqual(obter_lti_passports(), {'key_prod': 'secret_prod_compartilhada'})

    def test_edx_format_preserves_colons_in_secret(self):
        with patch.dict(os.environ, {'LTI_PASSPORTS': 'usp:key:a:b:c'}):
            self.assertEqual(obter_lti_passports(), {'key': 'a:b:c'})

    def test_invalid_json_values_are_ignored(self):
        with patch.dict(os.environ, {'LTI_PASSPORTS': '{"key": null, "valid": "secret"}'}):
            self.assertEqual(obter_lti_passports(), {'valid': 'secret'})


class SubmissionFlowTests(TestCase):
    def setUp(self):
        env = patch.dict(os.environ, {
            'LTI_PASSPORTS': json.dumps({KEY: SECRET}),
            'LTI_BYPASS_SIGNATURE_VERIFICATION': '0', 'LTI_FORCE_EVALUATION_SCORE': '',
        })
        env.start()
        self.addCleanup(env.stop)
        self.params = {
            'oauth_consumer_key': KEY, 'user_id': 'student-regression',
            'custom_exercise_id': 'week_2_dezenas',
            'lis_result_sourcedid': 'course:resource:user&1',
            'lis_outcome_service_url': 'https://edx.example/outcomes',
        }
        self.token = signing.dumps(self.params)
        self.aluno = Aluno.objects.create(user_id=self.params['user_id'])

    def signed_post(self, path='/lti/avaliacao/?exercise=week_2_dezenas', **extra):
        payload = {**self.params, 'oauth_signature_method': 'HMAC-SHA1', **extra}
        payload.pop('oauth_consumer_key')
        prepared = requests.Request(
            'POST', 'http://testserver' + path, data=payload,
            auth=OAuth1(KEY, client_secret=SECRET, signature_type='body'),
        ).prepare()
        return self.client.post(path, data=prepared.body, content_type='application/x-www-form-urlencoded')

    @patch('grader.views.executar_avaliacao')
    @patch('grader.views.enviar_nota_ao_edx', return_value=True)
    def test_form_saves_json_attempt_count_and_best_score(self, send, evaluate):
        evaluate.side_effect = [result(.8), result(.4)]
        for code in ['print(8)', 'print(4)']:
            response = self.client.post('/lti/avaliacao/', {'lti_token': self.token, 'custom_student_code': code})
            self.assertEqual(response.status_code, 200)
        submission = Submissao.objects.get()
        self.assertEqual((submission.nota, submission.maior_nota, submission.tentativas), (4, 8, 2))
        self.assertIsInstance(submission.resultado_json, dict)
        self.assertEqual(send.call_args.args[2], .8)
        self.assertEqual(response.context['nota_10'], 4)
        self.assertEqual(response.context['maior_nota'], 8)

    @patch('grader.views.executar_avaliacao')
    @patch('grader.views.enviar_nota_ao_edx', return_value=True)
    def test_direct_submission_sends_best_score(self, send, evaluate):
        evaluate.side_effect = [result(.85), result(.2)]
        self.assertEqual(self.signed_post(custom_student_code='print(1)').status_code, 200)
        self.assertEqual(self.signed_post(custom_student_code='print(2)').status_code, 200)
        self.assertEqual(send.call_args.args[2], .85)
        self.assertEqual(Submissao.objects.get().tentativas, 2)

    @patch('grader.views.executar_avaliacao', return_value=result(1))
    @patch('grader.views.enviar_nota_ao_edx', side_effect=[False, True])
    def test_maximum_score_can_retry_failed_passback(self, send, evaluate):
        response = self.client.post('/lti/avaliacao/', {'lti_token': self.token, 'custom_student_code': SOLUTION})
        self.assertContains(response, 'Reenviar nota ao EdX')
        reopened = self.signed_post()
        self.assertContains(reopened, 'Reenviar nota ao EdX')
        response = self.client.post('/lti/avaliacao/', {
            'lti_token': reopened.context['lti_token'], 'retry_passback': '1',
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(send.call_count, 2)
        self.assertEqual(evaluate.call_count, 1)
        self.assertEqual(Submissao.objects.get().tentativas, 1)

    @patch('grader.views.executar_avaliacao')
    @patch('grader.views.enviar_nota_ao_edx')
    def test_infrastructure_failure_does_not_record_zero_or_send_grade(self, send, evaluate):
        evaluate.return_value = {'sucesso': False, 'nota': 0, 'detalhes': [], 'erro': 'Docker indisponível'}
        response = self.client.post('/lti/avaliacao/', {'lti_token': self.token, 'custom_student_code': SOLUTION})
        self.assertContains(response, 'Docker indisponível', status_code=503)
        self.assertFalse(Submissao.objects.exists())
        send.assert_not_called()

    @patch('grader.views.executar_avaliacao', side_effect=OSError('temporary failure'))
    def test_unexpected_engine_failure_has_useful_response(self, evaluate):
        response = self.client.post('/lti/avaliacao/', {'lti_token': self.token, 'custom_student_code': SOLUTION})
        self.assertEqual(response.status_code, 503)
        self.assertFalse(Submissao.objects.exists())

    @patch('grader.views.executar_avaliacao', return_value=result(.7))
    @patch('grader.views.enviar_nota_ao_edx', return_value=True)
    def test_utf8_file_upload(self, send, evaluate):
        upload = SimpleUploadedFile('solucao.py', ('\ufeff' + SOLUTION).encode('utf-8'))
        response = self.client.post('/lti/avaliacao/', {'lti_token': self.token, 'code_file': upload})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(evaluate.call_args.args[0], SOLUTION)

    def test_invalid_utf8_file_rejected(self):
        response = self.client.post('/lti/avaliacao/', {
            'lti_token': self.token, 'code_file': SimpleUploadedFile('bad.py', b'\xff'),
        })
        self.assertEqual(response.status_code, 400)

    def test_invalid_signature_rejected(self):
        self.assertEqual(self.client.post('/lti/avaliacao/', {
            **self.params, 'oauth_signature_method': 'HMAC-SHA1', 'oauth_signature': 'invalid',
        }).status_code, 403)

    def test_tampered_token_rejected(self):
        self.assertEqual(self.client.post('/lti/avaliacao/', {
            'lti_token': self.token + 'x', 'custom_student_code': SOLUTION,
        }).status_code, 403)

    @patch('django.core.signing.time.time', return_value=1)
    def test_expired_token_rejected(self, clock):
        token = signing.dumps(self.params)
        clock.return_value = 7200
        self.assertEqual(self.client.post('/lti/avaliacao/', {'lti_token': token}).status_code, 403)

    def test_query_parameters_signed_by_oauthlib(self):
        self.assertEqual(self.signed_post().status_code, 200)

    def test_default_https_port_is_normalized(self):
        url = 'https://testserver:443/lti/avaliacao/?exercise=week_2_dezenas'
        prepared = requests.Request('POST', url, data=self.params, auth=OAuth1(
            KEY, client_secret=SECRET, signature_type='body',
        )).prepare()
        response = self.client.post(
            '/lti/avaliacao/?exercise=week_2_dezenas', data=prepared.body,
            content_type='application/x-www-form-urlencoded', secure=True, HTTP_HOST='testserver:443',
        )
        self.assertEqual(response.status_code, 200)

    @override_settings(DEBUG=False)
    def test_signature_bypass_is_disabled_in_production(self):
        with patch.dict(os.environ, {'LTI_BYPASS_SIGNATURE_VERIFICATION': '1'}):
            self.assertEqual(self.client.post('/lti/avaliacao/', self.params).status_code, 403)

    def test_legacy_path_with_and_without_slash(self):
        for path in ['/lti/introcomp2024/paridade', '/lti/introcomp2024/paridade/']:
            response = self.signed_post(path)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.context['exercise_id'], 'week_3_paridade')
            self.assertNotIn('X-Frame-Options', response.headers)

    def test_unknown_exercise_and_traversal_rejected(self):
        for exercise in ['not_configured', '../../settings']:
            response = self.signed_post('/lti/avaliacao/', custom_exercise_id=exercise)
            self.assertEqual(response.status_code, 400)

    def test_launch_shows_latest_score_consistently(self):
        save_submission(self.aluno, 'week_2_dezenas', SOLUTION, result(.9))
        save_submission(self.aluno, 'week_2_dezenas', 'print(0)', result(.2))
        response = self.signed_post()
        self.assertEqual(response.context['nota_10'], 2)
        self.assertEqual(response.context['maior_nota'], 9)

    @patch('grader.views.enviar_nota_ao_edx', return_value=True)
    def test_passback_refreshes_best_score_from_database(self, send):
        earlier = save_submission(self.aluno, 'week_2_dezenas', 'pass', result(.2))
        save_submission(self.aluno, 'week_2_dezenas', SOLUTION, result(.9))
        self.assertTrue(_passback(self.params, earlier))
        self.assertEqual(send.call_args.args[2], .9)

    def test_missing_battery_case_cannot_receive_full_points(self):
        from grader.evaluator import calcular_nota_baterias
        config = {'baterias': [{'nome': 'bat', 'peso': 1, 'testes': [{}, {}]}]}
        report = calcular_nota_baterias(config, [{'bateria_idx': 0, 'passou': True}])
        self.assertEqual(report['nota'], 0)

    @override_settings(DEBUG=True)
    def test_simulator_form_has_valid_signature(self):
        with patch('grader.views.LTI_KEY', KEY), patch('grader.views.LTI_SECRET', SECRET):
            response = self.client.get('/lti/test-launcher/?exercise=week_3_paridade')
        self.assertEqual(response.status_code, 200)
        parser = FormParser()
        parser.feed(response.content.decode())
        path = parser.action.removeprefix('http://testserver')
        self.assertEqual(self.client.post(path, parser.fields).status_code, 200)

    @override_settings(DEBUG=False)
    def test_simulator_not_available_in_production(self):
        self.assertEqual(self.client.get('/lti/test-launcher/').status_code, 404)


class PassbackResponseTests(SimpleTestCase):
    @patch('grader.views.requests.Session.send')
    def test_namespace_and_whitespace_are_accepted(self, send):
        response = requests.Response()
        response.status_code = 200
        response._content = b'<r xmlns:ns="urn:test"><ns:imsx_codeMajor>\n  success \n</ns:imsx_codeMajor></r>'
        send.return_value = response
        self.assertTrue(enviar_nota_ao_edx('https://edx.example/grades', 'user', 1, KEY, SECRET))

    @patch('grader.views.requests.Session.send')
    def test_html_success_string_is_not_a_valid_passback(self, send):
        response = requests.Response()
        response.status_code = 200
        response._content = b'<html><!-- <imsx_codeMajor>success</imsx_codeMajor> --></html>'
        send.return_value = response
        self.assertFalse(enviar_nota_ao_edx('https://edx.example/grades', 'user', 1, KEY, SECRET))


@pytest.mark.docker
class RunnerRegressionTests(SimpleTestCase):
    @patch('grader.pytest_runner.docker.from_env', side_effect=docker.errors.DockerException('offline'))
    def test_no_implicit_host_execution(self, from_env):
        with patch.dict(os.environ, {'AUTOGRADER_ALLOW_LOCAL_FALLBACK': '0'}), patch('subprocess.Popen') as run:
            self.assertFalse(avaliar_com_pytest(SOLUTION, 'week_2_dezenas')['sucesso'])
        run.assert_not_called()

    def test_syntax_error_is_student_feedback(self):
        report = avaliar_com_pytest('def invalid(', 'week_5_fizzbuzz_funcao')
        self.assertTrue(report['sucesso'])
        self.assertEqual(report['nota'], 0)
        self.assertIn('sintaxe', report['erro'])

    def test_invalid_exercise_id(self):
        self.assertFalse(avaliar_com_pytest('pass', '../settings')['sucesso'])

    @patch('grader.pytest_runner.docker.from_env', side_effect=docker.errors.DockerException('offline'))
    def test_explicit_development_fallback(self, from_env):
        with patch.dict(os.environ, {'AUTOGRADER_ALLOW_LOCAL_FALLBACK': '1'}):
            report = avaliar_com_pytest(SOLUTION, 'week_2_dezenas')
        self.assertTrue(report['sucesso'])
        self.assertEqual(report['nota'], 1)

    def test_missing_function_has_collection_feedback(self):
        report = avaliar_com_pytest('def another_function(): return 1', 'week_5_fizzbuzz_funcao')
        self.assertTrue(report['sucesso'])
        self.assertEqual(report['nota'], 0)
        self.assertTrue(report['detalhes'])
        self.assertIn('ImportError', report['detalhes'][0]['erro'])

    def test_system_exit_failure_cannot_pass_script(self):
        report = avaliar_com_pytest('import sys\nprint("O dígito das dezenas é 0")\nsys.exit(1)', 'week_2_dezenas')
        self.assertTrue(report['sucesso'])
        self.assertEqual(report['nota'], 0)

    def test_rectangle_solution_is_accepted(self):
        code = 'w=int(input())\nh=int(input())\nfor _ in range(h): print("#" * w)\n'
        self.assertEqual(avaliar_com_pytest(code, 'week_7_retangulo_cheio')['nota'], 1)

    def test_fizz_partial_battery_score(self):
        code = 'n=int(input())\nprint("Fizz" if n > 0 and n % 3 == 0 else n)\n'
        report = avaliar_com_pytest(code, 'week_3_fizz')
        self.assertEqual(report['nota'], .8)

    def test_constant_non_prime_does_not_receive_full_score(self):
        report = avaliar_com_pytest('input()\nprint("não primo")\n', 'week_4_primalidade')
        self.assertEqual(report['nota'], .5)


class LegacyMigrationTests(TransactionTestCase):
    def test_upgrade_preserves_old_grade_and_json(self):
        executor = MigrationExecutor(connection)
        executor.migrate([('grader', '0001_initial')])
        old = executor.loader.project_state([('grader', '0001_initial')]).apps
        aluno = old.get_model('grader', 'Aluno').objects.create(user_id='legacy-user')
        old.get_model('grader', 'Submissao').objects.create(
            aluno=aluno, exercise_id='week_2_dezenas', nota=8.5,
            student_code=SOLUTION, resultado_json=json.dumps(result(.85)),
        )
        try:
            executor = MigrationExecutor(connection)
            executor.migrate(executor.loader.graph.leaf_nodes())
            submission = Submissao.objects.get(aluno_id='legacy-user')
            self.assertEqual(submission.maior_nota, 8.5)
            self.assertIsInstance(submission.resultado_json, dict)
            self.assertEqual(submission.resultado_json['nota'], .85)
        finally:
            executor = MigrationExecutor(connection)
            executor.migrate(executor.loader.graph.leaf_nodes())


class SqliteImportTests(TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.source = Path(temporary.name) / 'legacy.sqlite3'
        with sqlite3.connect(self.source) as legacy:
            legacy.executescript('''
                CREATE TABLE grader_aluno (user_id TEXT PRIMARY KEY, created_at TEXT);
                CREATE TABLE grader_submissao (
                    id INTEGER PRIMARY KEY, aluno_id TEXT, exercise_id TEXT,
                    nota REAL, student_code TEXT, resultado_json TEXT, updated_at TEXT
                );
            ''')
            legacy.execute('INSERT INTO grader_aluno VALUES (?, ?)', ('import-user', '2026-01-01 12:00:00'))
            legacy.execute('INSERT INTO grader_submissao VALUES (1, ?, ?, ?, ?, ?, ?)', (
                'import-user', 'week_2_dezenas', 8.5, SOLUTION,
                json.dumps(result(.85)), '2026-01-02 12:00:00',
            ))

    def test_import_preserves_score_json_dates_and_source(self):
        original = self.source.read_bytes()
        call_command('import_legacy_sqlite', source=str(self.source))
        submission = Submissao.objects.get()
        self.assertEqual(submission.maior_nota, 8.5)
        self.assertEqual(submission.tentativas, 1)
        self.assertEqual(submission.resultado_json['nota'], .85)
        self.assertEqual(submission.updated_at.day, 2)
        self.assertEqual(self.source.read_bytes(), original)

    def test_dry_run_rolls_back_all_records(self):
        call_command('import_legacy_sqlite', source=str(self.source), dry_run=True)
        self.assertFalse(Aluno.objects.exists())
        self.assertFalse(Submissao.objects.exists())

    def test_nonempty_destination_is_preserved(self):
        Aluno.objects.create(user_id='existing')
        with self.assertRaises(CommandError):
            call_command('import_legacy_sqlite', source=str(self.source))
        self.assertEqual(list(Aluno.objects.values_list('user_id', flat=True)), ['existing'])

    def test_bad_source_rolls_back_import(self):
        with sqlite3.connect(self.source) as legacy:
            legacy.execute('UPDATE grader_submissao SET resultado_json = ?', ('not json',))
        with self.assertRaises(CommandError):
            call_command('import_legacy_sqlite', source=str(self.source))
        self.assertFalse(Aluno.objects.exists())


@skipUnless(connection.vendor == 'postgresql', 'Valida locks reais do PostgreSQL.')
class ConcurrentSubmissionTests(TransactionTestCase):
    def test_parallel_attempts_keep_highest_score_and_count(self):
        aluno = Aluno.objects.create(user_id='parallel-user')
        gate = threading.Barrier(3)
        errors = []

        def submit(score):
            close_old_connections()
            try:
                gate.wait(timeout=10)
                save_submission(aluno, 'week_2_dezenas', 'pass', result(score))
            except Exception as error:
                errors.append(error)
            finally:
                connections.close_all()

        threads = [threading.Thread(target=submit, args=(score,)) for score in [.9, .3, .6]]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=15)
        self.assertFalse(errors, errors)
        submission = Submissao.objects.get()
        self.assertEqual(submission.maior_nota, 9)
        self.assertEqual(submission.tentativas, 3)
