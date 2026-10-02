"""A public bundle contains only audited client assets and deployment metadata."""
from datetime import datetime, timedelta, timezone
from html import unescape
from io import BytesIO
import json
import re
from zipfile import ZipFile

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID
from fastapi.testclient import TestClient
import pytest


DOWNLOAD = '/downloads/ys-memory-stdio-1.0.0.zip'
TOKEN = 'synthetic-bundle-worker-token-123456'


@pytest.fixture
def bundle_app(tmp_path, monkeypatch):
    from memory_hub.app import create_app
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'Bundle test CA')])
    now = datetime.now(timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(minutes=1)).not_valid_after(now + timedelta(days=1))
            .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
            .sign(key, hashes.SHA256()))
    pem = cert.public_bytes(serialization.Encoding.PEM)
    ca = tmp_path / 'ca.crt'
    ca.write_bytes(pem)
    monkeypatch.setenv('HUB_PUBLIC_CA_FILE', str(ca))
    monkeypatch.setenv('HUB_PUBLIC_BASE_URL', 'https://memory.example.test:8443')
    monkeypatch.setenv('HUB_ALLOWED_HOSTS', 'localhost,127.0.0.1,testserver')
    app = create_app(database_url='sqlite:///' + str(tmp_path / 'bundle.db'), allow_sqlite=True,
                     auth_tokens=json.dumps({TOKEN: {'worker_id': 'client', 'projects': ['only'], 'role': 'worker'}}))
    with TestClient(app) as client:
        yield client, ca, cert, pem


def test_download_is_public_deterministic_and_contains_only_client_assets(bundle_app):
    client, _, cert, pem = bundle_app
    response = client.get(DOWNLOAD, headers={'X-Forwarded-Host': 'attacker.invalid'})
    assert response.status_code == 200
    assert response.headers['content-type'] == 'application/zip'
    assert response.headers['cache-control'] == 'no-store'
    assert response.headers['x-content-type-options'] == 'nosniff'
    assert response.headers['content-disposition'] == 'attachment; filename="ys-memory-stdio-1.0.0.zip"'
    assert response.content == client.get(DOWNLOAD).content
    head = client.head(DOWNLOAD)
    assert head.status_code == 200 and head.content == b''
    assert int(head.headers['content-length']) == len(response.content)
    with ZipFile(BytesIO(response.content)) as archive:
        assert set(archive.namelist()) == {'bridge.py', 'connection.json', 'ys-ai-memory-ca.crt', 'requirements.lock', 'README.txt'}
        assert archive.read('ys-ai-memory-ca.crt') == pem
        config = json.loads(archive.read('connection.json'))
        assert config == {'version': 1, 'endpoint': 'https://memory.example.test:8443/mcp',
                          'ca_file': 'ys-ai-memory-ca.crt', 'ca_sha256': cert.fingerprint(hashes.SHA256()).hex()}
        for name in archive.namelist():
            content = archive.read(name)
            assert TOKEN.encode() not in content
            if name != 'bridge.py':
                assert b'PRIVATE KEY' not in content
            assert b'attacker.invalid' not in content
            assert b'C:\\Users\\example\\workspace' not in content


@pytest.mark.parametrize('body', [b'not a certificate', b'-----BEGIN PRIVATE KEY-----\nsecret\n-----END PRIVATE KEY-----'])
def test_bundle_fails_closed_if_public_ca_becomes_invalid(bundle_app, body):
    client, ca, _, _ = bundle_app
    ca.write_bytes(body)
    response = client.get(DOWNLOAD)
    assert response.status_code == 404
    assert body not in response.content and str(ca) not in response.text


def test_download_route_does_not_expand_public_authentication_allowlist(bundle_app):
    client, _, _, _ = bundle_app
    for path in (DOWNLOAD + '/extra', '/downloads/other.zip', '/v1/tools/get_worker_inbox'):
        assert client.get(path).status_code == 401
    assert client.post(DOWNLOAD).status_code == 401
    # Root SDK mount handles unknown methods as 404 after bearer validation.
    assert client.post(DOWNLOAD, headers={'Authorization': 'Bearer ' + TOKEN}).status_code == 404


def test_generator_keeps_http_configs_and_provides_offline_stdio_setup():
    from memory_hub.web_mcp import config_cards
    html = config_cards('https://memory.example.test:8443')
    configs = {name: unescape(value) for name, value in re.findall(
        r'<textarea id="config-([^"]+)"[^>]*>(.*?)</textarea>', html, re.S)}
    assert json.loads(configs['claude'])['mcpServers']['ys_memory']['type'] == 'http'
    assert 'bearer_token_env_var = "YS_AIMEMORY_TOKEN"' in configs['codex']
    assert 'https://memory.example.test:8443' + DOWNLOAD in html
    assert '--print-claude-config' in html and 'requirements.lock' in html
    assert 'UNSUPPORTED_CONSTRAINT_TYPE' in html


def test_only_configured_https_port_is_added_to_origin_allowlist(bundle_app):
    client, _, _, _ = bundle_app
    headers = {'Authorization': 'Bearer ' + TOKEN, 'Accept': 'application/json, text/event-stream'}
    initialize = {'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {
        'protocolVersion': '2025-03-26', 'capabilities': {}, 'clientInfo': {'name': 'bundle-test', 'version': '1'}}}
    assert client.post('/mcp', json=initialize, headers={**headers, 'Origin': 'https://memory.example.test:8443'}).status_code == 200
    for origin in ('https://memory.example.test:8444', 'http://memory.example.test:8443', 'https://attacker.invalid'):
        assert client.post('/mcp', json=initialize, headers={**headers, 'Origin': origin}).status_code == 403
    assert client.post('/mcp', json=initialize, headers={**headers, 'Host': 'attacker.invalid',
                       'Origin': 'https://memory.example.test:8443'}).status_code == 400


def test_ca_default_location_matches_public_help(bundle_app, monkeypatch):
    client, _, cert, pem = bundle_app
    from memory_hub import web_help
    monkeypatch.delenv('HUB_PUBLIC_CA_FILE')
    seen = []

    def synthetic_ca(path):
        seen.append(path)
        return web_help.PublicCA(pem, cert.fingerprint(hashes.SHA256()).hex())

    monkeypatch.setattr(web_help, '_public_ca', synthetic_ca)
    assert client.get(DOWNLOAD).status_code == 200
    assert seen == ['/app/public/ys-ai-memory-ca.crt']


def test_missing_public_base_does_not_grant_localhost_origin(tmp_path, monkeypatch):
    from memory_hub.app import create_app
    monkeypatch.delenv('HUB_PUBLIC_BASE_URL', raising=False)
    monkeypatch.setenv('HUB_ALLOWED_HOSTS', 'memory.example.test')
    app = create_app(database_url='sqlite:///' + str(tmp_path / 'origin.db'), allow_sqlite=True,
        auth_tokens=json.dumps({TOKEN: {'worker_id': 'client', 'projects': ['only'], 'role': 'worker'}}))
    initialize = {'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {
        'protocolVersion': '2025-03-26', 'capabilities': {}, 'clientInfo': {'name': 'bundle-test', 'version': '1'}}}
    headers = {'Authorization': 'Bearer ' + TOKEN, 'Accept': 'application/json, text/event-stream'}
    with TestClient(app, base_url='http://memory.example.test') as client:
        assert client.post('/mcp', json=initialize, headers={**headers, 'Origin': 'https://localhost'}).status_code == 403
        assert client.post('/mcp', json=initialize, headers={**headers, 'Origin': 'https://memory.example.test'}).status_code == 200
