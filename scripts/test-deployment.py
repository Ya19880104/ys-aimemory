#!/usr/bin/env python3
"""Deterministic, noncredential fixtures for the offline preflight validator."""
import base64
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import unittest

PATH = Path(__file__).with_name('validate-compose.py')
spec = importlib.util.spec_from_file_location('validator', PATH)
validator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validator)

class DeploymentTests(unittest.TestCase):
    def setUp(self):
        self.config = {'services': {
            'db': {'environment': {'POSTGRES_PASSWORD': 'fixture-admin-value-000000000000', 'HUB_DB_PASSWORD': 'fixture-app-value-00000000000000'}},
            'app': {'environment': {
                'HUB_DATABASE_URL': 'postgresql+psycopg://memory_hub:fixture-app-value-00000000000000@db:5432/memory_hub',
                'HUB_AUTH_TOKENS': json.dumps({'fixture-token-value-000000000000': {'worker_id': 'worker1', 'projects': ['p'], 'role': 'worker'}}),
                'HUB_ALLOWED_HOSTS': 'localhost,127.0.0.1', 'HUB_ALLOW_SQLITE': 'false'},
                'ports': [{'host_ip': '127.0.0.1'}]},
            'nginx': {'ports': [{'host_ip': '192.168.10.5'}]}}}
        self.env = self.config['services']['app']['environment']

    def reject(self):
        with self.assertRaises(validator.ConfigurationError):
            validator.validate(self.config)

    def test_valid_configuration(self):
        validator.validate(self.config)

    def test_reject_unsafe_network_and_auth(self):
        original = copy.deepcopy(self.config)
        changes = [
            lambda x: x['app']['ports'][0].update(host_ip='0.0.0.0'),
            lambda x: x['nginx']['ports'][0].update(host_ip='0.0.0.0'),
            lambda x: x['db'].update(ports=[{'published': 5432}]),
            lambda x: x['app']['environment'].update(HUB_AUTH_TOKENS='{}'),
            lambda x: x['app']['environment'].update(HUB_ALLOWED_HOSTS='*'),
            lambda x: x['app']['environment'].update(HUB_ALLOW_SQLITE='true'),
            lambda x: x['app']['environment'].update(HUB_DATABASE_URL='sqlite:///test.db')]
        for index, change in enumerate(changes):
            with self.subTest(case=index):
                self.config = copy.deepcopy(original)
                change(self.config['services'])
                self.reject()

    def enable_web(self):
        # Format-only validation fixture. Not derived from a password, not usable for login.
        encoded = 'scrypt$32768$8$1$' + base64.urlsafe_b64encode(bytes(16)).decode() + '$' + base64.urlsafe_b64encode(bytes(64)).decode()
        self.env.update(HUB_WEB_USERNAME='fixture-user', HUB_WEB_PASSWORD_HASH=encoded,
                        HUB_WEB_PROJECTS='p', HUB_WEB_COOKIE_SECURE='true', HUB_WEB_SESSION_TTL='3600')

    def test_valid_web_configuration(self):
        self.enable_web()
        validator.validate(self.config)

    def test_valid_admin_web_configuration(self):
        self.enable_web()
        self.env['HUB_WEB_ROLE'] = 'admin'
        validator.validate(self.config)

    def test_reject_unknown_web_role(self):
        self.enable_web()
        self.env['HUB_WEB_ROLE'] = 'superuser'
        self.reject()

    def test_reject_partial_web_configuration(self):
        self.env['HUB_WEB_USERNAME'] = 'fixture-user'
        self.reject()

    def test_reject_plaintext_web_password(self):
        self.enable_web()
        self.env['HUB_WEB_PASSWORD_HASH'] = 'not-a-hash'
        self.reject()

    def test_reject_insecure_web_cookies(self):
        self.enable_web()
        self.env['HUB_WEB_COOKIE_SECURE'] = 'false'
        self.reject()

    def test_reject_web_wildcard_scope(self):
        self.enable_web()
        self.env['HUB_WEB_PROJECTS'] = '*'
        self.reject()

    def test_reject_web_long_session(self):
        self.enable_web()
        self.env['HUB_WEB_SESSION_TTL'] = '86400'
        self.reject()

    def compose_config_result(self):
        # Compose's interpolated config JSON doubles every dollar on output.
        data = json.dumps(self.config).replace('$', '$$')
        return subprocess.run([sys.executable, str(PATH)], input=data, text=True, capture_output=True)

    def test_compose_config_json_accepts_valid_scrypt_hash(self):
        self.enable_web()
        result = self.compose_config_result()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, '')
        self.assertEqual(result.stderr, '')

    def test_compose_config_json_preserves_literal_double_dollars(self):
        self.enable_web()
        self.config['services']['db']['environment']['HUB_DB_PASSWORD'] = 'fixture-app-value-$$-00000000000000'
        self.env['HUB_DATABASE_URL'] = 'postgresql+psycopg://memory_hub:fixture-app-value-%24%24-00000000000000@db:5432/memory_hub'
        validator.validate(self.config)
        result = self.compose_config_result()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, '')
        self.assertEqual(result.stderr, '')

    def test_compose_config_json_rejects_invalid_runtime_hash(self):
        self.enable_web()
        invalid_hashes = ['not-a-hash', self.env['HUB_WEB_PASSWORD_HASH'].replace('$', '$$', 1)]
        for invalid_hash in invalid_hashes:
            with self.subTest(case='invalid runtime hash'):
                self.env['HUB_WEB_PASSWORD_HASH'] = invalid_hash
                self.reject()
                result = self.compose_config_result()
                self.assertEqual(result.returncode, 1)
                self.assertEqual(result.stdout, '')
                self.assertIn('Dashboard needs a valid operator-supplied scrypt password hash', result.stderr)
                self.assertNotIn(invalid_hash, result.stderr)
                self.assertNotIn('Traceback', result.stderr)

    def test_invalid_inputs_do_not_echo_data_or_tracebacks(self):
        for data in ['', '{', json.dumps({'services': {}})]:
            with self.subTest(data=data):
                result = subprocess.run([sys.executable, str(PATH)], input=data, text=True, capture_output=True)
                self.assertEqual(result.returncode, 1)
                self.assertNotIn('Traceback', result.stderr)
                self.assertEqual(result.stdout, '')

if __name__ == '__main__':
    unittest.main()
