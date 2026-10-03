import importlib.util
import json
import os
from pathlib import Path
from io import BytesIO
import ssl
import subprocess
from types import SimpleNamespace
from zipfile import ZipFile, ZipInfo
import pytest

spec = importlib.util.spec_from_file_location('claude_setup', Path(__file__).parents[1] / 'scripts/setup-claude.py')
setup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(setup)


def test_setup_preserves_unrelated_servers_and_refuses_existing_memory_server():
    original = {'mcpServers': {'other': {'command':'existing', 'env':{'EXAMPLE':'synthetic'}}}, 'custom':True}
    result = json.loads(setup.merged_config(json.dumps(original).encode(), {'command':'new'}))
    assert result['mcpServers']['other'] == original['mcpServers']['other'] and result['custom'] is True
    with pytest.raises(ValueError, match='already exists'):
        setup.merged_config(json.dumps(result).encode(), {'command':'replacement'})


@pytest.mark.skipif(os.name != 'nt', reason='Windows current-user DPAPI')
def test_dpapi_roundtrip_and_corrupted_ciphertext_rejected():
    from memory_hub.client_secret import transform
    token = b'fixture-worker-value-not-a-real-token'
    encrypted = transform(token)
    assert token not in encrypted and transform(encrypted, decrypt=True) == token
    with pytest.raises(RuntimeError, match='protection failed'):
        transform(b'invalid cipher', decrypt=True)


def test_setup_rejects_malformed_shared_configuration():
    for raw in (b'[]', b'{"mcpServers": []}', b'{invalid'):
        with pytest.raises((ValueError, TypeError)):
            setup.merged_config(raw, {'command':'new'})


@pytest.fixture
def public_ca():
    from datetime import datetime, timedelta, timezone
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'URL installer fixture CA')])
    now = datetime.now(timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(minutes=1)).not_valid_after(now + timedelta(days=1))
            .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
            .sign(key, hashes.SHA256()))
    return cert.public_bytes(serialization.Encoding.PEM), cert.fingerprint(hashes.SHA256()).hex()


@pytest.mark.parametrize('url', [
    'http://host', 'https://user:secret@host', 'https://host?token=secret',
    'https://host/#secret', 'https://host/path', 'https://host:bad',
    'https://host:0', 'https://host:65536', 'https://host\\evil', 'https://host\n',
    'https://host%2eexample', 'https://[::1]@evil',
])
def test_url_setup_rejects_unsafe_urls_without_network(url, tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('Unsafe URL reached network')
    monkeypatch.setattr(setup, 'download', forbidden)
    with pytest.raises(setup.SetupError):
        setup.download_bundle(url, '1' * 64, tmp_path / 'bundle')


@pytest.mark.parametrize(('url', 'origin'), [
    ('https://memory.example.test/', 'https://memory.example.test'),
    ('https://MEMORY.example.test:8443', 'https://memory.example.test:8443'),
    ('https://192.168.100.54', 'https://192.168.100.54'),
    ('https://[::1]:8443/', 'https://[::1]:8443'),
])
def test_canonical_hub_urls(url, origin):
    assert setup.hub_origin(url) == origin


def make_public_bundle(ca, pin, *, endpoint='https://memory.example.test/mcp', extra=None, symlink=False):
    assets = {name: b'fixture' for name in setup.ASSETS}
    assets['connection.json'] = json.dumps({'version': 1, 'endpoint': endpoint,
        'ca_file': 'ys-ai-memory-ca.crt', 'ca_sha256': pin}).encode()
    assets['ys-ai-memory-ca.crt'] = ca
    output = BytesIO()
    with ZipFile(output, 'w') as archive:
        for name, body in assets.items():
            info = ZipInfo(name)
            info.external_attr = (0o120777 if symlink else 0o100644) << 16
            archive.writestr(info, body)
        if extra is not None:
            if extra in assets:
                with pytest.warns(UserWarning, match='Duplicate name'):
                    archive.writestr(extra, b'not allowed')
            else:
                archive.writestr(extra, b'not allowed')
    return output.getvalue()


def test_url_bundle_verifies_independent_pin_before_https_and_no_keylog(public_ca, tmp_path, monkeypatch):
    ca, pin = public_ca
    bundle = make_public_bundle(ca, pin)
    requests = []
    monkeypatch.setenv('SSLKEYLOGFILE', str(tmp_path / 'never-keylog'))
    def fetch(url, *, context=None, maximum):
        requests.append(url)
        if context is None:
            assert url == 'http://memory.example.test' + setup.CA_ROUTE
            return ca
        assert context.verify_mode == ssl.CERT_REQUIRED and context.check_hostname
        assert context.verify_flags & ssl.VERIFY_X509_STRICT
        assert context.keylog_filename is None and len(context.get_ca_certs()) == 1
        return bundle
    monkeypatch.setattr(setup, 'download', fetch)
    result = setup.download_bundle('https://memory.example.test/', pin.upper(), tmp_path / 'bundle')
    assert {f.name for f in result.iterdir()} == setup.ASSETS
    assert requests == ['http://memory.example.test' + setup.CA_ROUTE,
                        'https://memory.example.test' + setup.BUNDLE_ROUTE]
    assert not (tmp_path / 'never-keylog').exists()
    requests.clear()
    with pytest.raises(setup.SetupError, match='fingerprint'):
        setup.download_bundle('https://memory.example.test', '0' * 64, tmp_path / 'wrong')
    assert len(requests) == 1 and not (tmp_path / 'wrong').exists()


@pytest.mark.parametrize('scenario', ['traversal', 'duplicate', 'symlink', 'foreign_endpoint', 'changed_ca', 'invalid_zip'])
def test_url_bundle_rejects_unsafe_or_misdirected_archive(public_ca, tmp_path, monkeypatch, scenario):
    ca, pin = public_ca
    payload = make_public_bundle(ca if scenario != 'changed_ca' else b'bad CA', pin,
        endpoint='https://unrelated.example.test/mcp' if scenario == 'foreign_endpoint' else 'https://memory.example.test/mcp',
        extra='../outside.py' if scenario == 'traversal' else ('bridge.py' if scenario == 'duplicate' else None),
        symlink=scenario == 'symlink') if scenario != 'invalid_zip' else b'invalid zip'
    monkeypatch.setattr(setup, 'download', lambda url, **kwargs: ca if url.startswith('http:') else payload)
    with pytest.raises(setup.SetupError):
        setup.download_bundle('https://memory.example.test', pin, tmp_path / 'bundle')
    assert not (tmp_path / 'bundle').exists()
    assert not (tmp_path / 'outside.py').exists()


@pytest.mark.parametrize(('status', 'headers', 'body'), [
    (302, {'Location': 'https://elsewhere.test'}, b''),
    (200, {'Content-Length': '20'}, b'too long'),
    (200, {'Content-Length': '4'}, b'bad'),
    (200, {'Content-Length': 'invalid'}, b''),
    (200, {'Content-Encoding': 'gzip'}, b'abc'),
    (200, {}, b'123456'),
])
def test_download_bounds_redirects_and_encoding(status, headers, body, monkeypatch):
    class Connection:
        def __init__(self, *args, **kwargs): pass
        def request(self, *args, **kwargs): pass
        def getresponse(self):
            return SimpleNamespace(status=status, getheader=lambda name, default=None: headers.get(name, default),
                                   read=lambda maximum: body[:maximum])
        def close(self): pass
    monkeypatch.setattr(setup.http.client, 'HTTPConnection', Connection)
    with pytest.raises(setup.SetupError):
        setup.download('http://memory.example.test' + setup.CA_ROUTE, maximum=5)


def test_cli_url_defaults_to_current_project_and_keeps_token_out_of_download(monkeypatch, tmp_path, capsys):
    monkeypatch.chdir(tmp_path)
    pin = '2' * 64
    monkeypatch.setattr('sys.argv', ['setup-claude.py', '--url', 'https://memory.example.test', '--expected-ca', pin])
    monkeypatch.setenv('YS_AIMEMORY_SETUP_TOKEN', 'synthetic-worker-never-print')
    calls = []
    def download(url, expected_ca, destination):
        calls.append(('download', url, expected_ca))
        return destination
    def install(bundle, project, expected_ca, token):
        assert project == tmp_path and expected_ca == pin and token == 'synthetic-worker-never-print'
        calls.append(('install',))
        return {'status': 'installed_not_native_verified'}
    monkeypatch.setattr(setup, 'download_bundle', download)
    monkeypatch.setattr(setup, 'install', install)
    assert setup.main() == 0
    assert calls == [('download', 'https://memory.example.test', pin), ('install',)]
    assert 'synthetic-worker-never-print' not in str(capsys.readouterr())


def test_cli_bad_arguments_do_not_echo_secrets(monkeypatch, capsys):
    monkeypatch.setattr('sys.argv', ['setup-claude.py', '--token', 'secret-must-not-print'])
    assert setup.main() == 1
    assert 'secret-must-not-print' not in str(capsys.readouterr())


def test_cli_does_not_echo_secret_exception_or_token(monkeypatch, capsys):
    monkeypatch.setattr('sys.argv', ['setup-claude.py', '--bundle', '.', '--project', '.', '--expected-ca', '0' * 64])
    monkeypatch.setenv('YS_AIMEMORY_SETUP_TOKEN', 'synthetic-input-never-print')

    def fail(*args):
        raise RuntimeError('synthetic-private-package-index-value')

    monkeypatch.setattr(setup, 'install', fail)
    assert setup.main() == 1
    output = capsys.readouterr()
    assert output.out == '' and output.err == 'setup_failed: RuntimeError\n'
    assert 'YS_AIMEMORY_SETUP_TOKEN' not in os.environ


@pytest.mark.skipif(os.name != 'nt', reason='Windows installer and DPAPI')
@pytest.mark.parametrize('scenario', ['success', 'concurrent_edit', 'dependency_failure'])
def test_install_preserves_config_and_keeps_secrets_out_of_shared_files(tmp_path, monkeypatch, scenario):
    from memory_hub.client_secret import transform
    project, bundle, clients = (tmp_path / name for name in ('project', 'bundle', 'clients'))
    project.mkdir()
    bundle.mkdir()
    original = b'{"mcpServers":{"unrelated":{"env":{"EXAMPLE":"synthetic-backup-value"}}}}'
    target = project / '.mcp.json'
    target.write_bytes(original)
    for name in setup.ASSETS:
        (bundle / name).write_text('{}', encoding='utf-8')
    pin = '1' * 64
    (bundle / 'connection.json').write_text(json.dumps({'ca_sha256':pin}), encoding='utf-8')
    changed = b'{"mcpServers":{"changed_by_user":{}}}'

    def subprocess_fixture(args, **kwargs):
        if 'pip' in args and scenario == 'dependency_failure':
            raise subprocess.CalledProcessError(1, args, stderr=b'synthetic-private-index')
        if '--print-claude-config' in args:
            directory = Path(kwargs['cwd'])
            if scenario == 'concurrent_edit':
                target.write_bytes(changed)
            return SimpleNamespace(stdout=json.dumps({'mcpServers':{'ys_memory':{
                'command': str(directory / '.venv/Scripts/python.exe'),
                'args': ['-B', str(directory / 'bridge.py'), '--compact'],
                'env': {'YS_AIMEMORY_TOKEN': '${YS_AIMEMORY_TOKEN:-}'}}}}).encode())
        return SimpleNamespace(stdout=b'')

    monkeypatch.setattr(setup.subprocess, 'run', subprocess_fixture)
    if scenario != 'success':
        with pytest.raises((setup.SetupError, subprocess.CalledProcessError)):
            setup.install(bundle, project, pin, 'synthetic-worker-value', install_parent=clients)
        assert target.read_bytes() == (changed if scenario == 'concurrent_edit' else original)
        return
    receipt = setup.install(bundle, project, pin, 'synthetic-worker-value', install_parent=clients)
    installed = Path(receipt['client_directory'])
    config = json.loads(target.read_bytes())
    assert config['mcpServers']['unrelated'] == json.loads(original)['mcpServers']['unrelated']
    assert 'env' not in config['mcpServers']['ys_memory']
    assert config['mcpServers']['ys_memory']['args'][1] == str(installed / 'launcher.py')
    assert transform((installed / 'worker.dpapi').read_bytes(), decrypt=True) == b'synthetic-worker-value'
    assert transform((installed / 'previous-mcp.dpapi').read_bytes(), decrypt=True) == original
    assert b'synthetic-worker-value' not in target.read_bytes()
    assert b'synthetic-backup-value' not in (installed / 'previous-mcp.dpapi').read_bytes()
