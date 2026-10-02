"""Exercise the shipped standalone adapter without real credentials or services."""
from datetime import datetime, timedelta, timezone
import asyncio
import importlib.util
import json
from pathlib import Path
import ssl
import subprocess
import sys

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID
import pytest


@pytest.fixture
def adapter():
    if importlib.util.find_spec('memory_hub.client_adapter') is None:
        pytest.skip('Adapter contract awaits implementation; distribution test is RED')
    from memory_hub import client_adapter
    return client_adapter


def test_standalone_adapter_is_distributed():
    assert importlib.util.find_spec('memory_hub.client_adapter') is not None


@pytest.fixture
def connection(tmp_path):
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'Adapter test CA')])
    now = datetime.now(timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(minutes=1)).not_valid_after(now + timedelta(days=1))
            .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
            .sign(key, hashes.SHA256()))
    (tmp_path / 'ys-ai-memory-ca.crt').write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    config = {'version': 1, 'endpoint': 'https://memory.example.test/mcp',
              'ca_file': 'ys-ai-memory-ca.crt', 'ca_sha256': cert.fingerprint(hashes.SHA256()).hex()}
    path = tmp_path / 'connection.json'
    path.write_text(json.dumps(config), encoding='utf-8')
    return path, config


def test_strict_tls_ignores_keylog_environment_and_only_loads_pinned_ca(adapter, connection, monkeypatch, tmp_path):
    path, _ = connection
    keylog = tmp_path / 'must-not-exist.log'
    monkeypatch.setenv('SSLKEYLOGFILE', str(keylog))
    settings = adapter.load_connection(path)
    context = adapter.verified_context(settings)
    assert context.verify_mode == ssl.CERT_REQUIRED and context.check_hostname
    assert context.verify_flags & ssl.VERIFY_X509_STRICT
    assert context.keylog_filename is None and not keylog.exists()
    assert len(context.get_ca_certs()) == 1


@pytest.mark.parametrize('endpoint', [
    'http://memory.example.test/mcp', 'https://user:pass@memory.example.test/mcp',
    'https://memory.example.test/mcp?token=secret', 'https://memory.example.test/mcp#other',
    'https://memory.example.test/not-mcp', 'https://memory.example.test:bad/mcp',
    'https://memory.example.test\\evil/mcp', 'https://memory.example.test\n/mcp',
])
def test_unsafe_endpoints_are_rejected_before_sending_a_token(adapter, connection, endpoint):
    path, config = connection
    config['endpoint'] = endpoint
    path.write_text(json.dumps(config), encoding='utf-8')
    with pytest.raises(ValueError):
        adapter.load_connection(path)


@pytest.mark.parametrize(('field', 'value'), [
    ('version', 2), ('ca_sha256', '0' * 64), ('ca_file', '../outside.crt'),
    ('token', 'must-not-be-loaded'), ('ca_file', 'other.pem'),
])
def test_malformed_config_or_changed_ca_fails_closed(adapter, connection, field, value):
    path, config = connection
    config[field] = value
    path.write_text(json.dumps(config), encoding='utf-8')
    with pytest.raises(ValueError):
        adapter.verified_context(adapter.load_connection(path))


def test_print_claude_config_is_offline_needs_no_token_and_changes_no_files(adapter, connection, monkeypatch):
    path, _ = connection
    monkeypatch.delenv('YS_AIMEMORY_TOKEN', raising=False)
    before = {f.name: f.read_bytes() for f in path.parent.iterdir()}
    result = subprocess.run([sys.executable, '-B', adapter.__file__, '--config', str(path), '--print-claude-config'],
                            capture_output=True, text=True, timeout=15)
    assert result.returncode == 0 and result.stderr == ''
    server = json.loads(result.stdout)['mcpServers']['ys_memory']
    assert server == {'type': 'stdio', 'command': str(Path(sys.executable).resolve()),
                      'args': ['-B', str(Path(adapter.__file__).resolve()), '--config', str(path.resolve())],
                      'env': {'YS_AIMEMORY_TOKEN': '${YS_AIMEMORY_TOKEN}'}}
    assert before == {f.name: f.read_bytes() for f in path.parent.iterdir()}


def test_missing_token_exits_without_leaking_config_or_exceptions(adapter, connection, monkeypatch):
    path, _ = connection
    monkeypatch.delenv('YS_AIMEMORY_TOKEN', raising=False)
    result = subprocess.run([sys.executable, '-B', adapter.__file__, '--config', str(path)],
                            capture_output=True, text=True, timeout=15)
    assert result.returncode == 1 and result.stdout == ''
    assert result.stderr == 'bridge_stopped: ValueError\n'


def test_accidental_secret_command_argument_is_not_echoed(adapter):
    value = 'synthetic-do-not-echo-secret'
    result = subprocess.run([sys.executable, '-B', adapter.__file__, '--token', value],
                            capture_output=True, text=True, timeout=15)
    assert result.returncode != 0 and result.stdout == ''
    assert value not in result.stderr


def test_print_config_handles_unicode_install_path_with_ascii_console(adapter, connection, monkeypatch):
    path, _ = connection
    directory = path.parent / 'client-\U0001f4be'
    directory.mkdir()
    config = directory / path.name
    config.write_bytes(path.read_bytes())
    (directory / 'ys-ai-memory-ca.crt').write_bytes((path.parent / 'ys-ai-memory-ca.crt').read_bytes())
    monkeypatch.setenv('PYTHONIOENCODING', 'ascii')
    result = subprocess.run([sys.executable, '-B', adapter.__file__, '--config', str(config), '--print-claude-config'],
                            capture_output=True, text=True, timeout=15)
    assert result.returncode == 0 and result.stderr == ''
    assert json.loads(result.stdout)['mcpServers']['ys_memory']['args'][-1] == str(config.resolve())


def test_compact_print_config_is_opt_in_and_offline(adapter, connection, monkeypatch):
    path, _ = connection
    monkeypatch.delenv('YS_AIMEMORY_TOKEN', raising=False)
    result = subprocess.run([sys.executable, '-B', adapter.__file__, '--config', str(path),
                             '--compact', '--print-claude-config'], capture_output=True, text=True, timeout=15)
    assert result.returncode == 0 and result.stderr == ''
    server = json.loads(result.stdout)['mcpServers']['ys_memory']
    assert server['args'] == ['-B', str(Path(adapter.__file__).resolve()), '--config', str(path.resolve()), '--compact']
    assert server['env'] == {'YS_AIMEMORY_TOKEN': '${YS_AIMEMORY_TOKEN}'}


def test_compact_discovery_follows_pages_but_returns_only_one_schema(adapter):
    from mcp import types
    calls = []
    target = types.Tool(name='target', description='Target only', inputSchema={'type': 'object'})

    class Upstream:
        async def list_tools(self, cursor=None):
            calls.append(cursor)
            if cursor is None:
                return types.ListToolsResult(tools=[types.Tool(name='other', inputSchema={'type': 'object'})], nextCursor='second')
            return types.ListToolsResult(tools=[target])

    result = asyncio.run(adapter.compact_discover(Upstream(), {'name': 'target'}))
    assert not result.isError and calls == [None, 'second']
    assert result.structuredContent == {'tool': target.model_dump(mode='json', by_alias=True, exclude_none=True)}
    assert 'other' not in result.model_dump_json()


def test_compact_discovery_bounds_descriptions_and_detects_cursor_loop(adapter):
    from mcp import types

    class Upstream:
        async def list_tools(self, cursor=None):
            return types.ListToolsResult(tools=[types.Tool(name='read', description='long ' * 200, inputSchema={'type': 'object'})])

    result = asyncio.run(adapter.compact_discover(Upstream(), {'query': 'READ'}))
    assert len(result.structuredContent['items'][0]['description']) == 240
    assert result.structuredContent['has_more'] is False

    class Loop:
        calls = 0

        async def list_tools(self, cursor=None):
            self.calls += 1
            return types.ListToolsResult(tools=[], nextCursor='again')

    upstream = Loop()
    result = asyncio.run(adapter.compact_discover(upstream, {'name': 'absent'}))
    assert result.isError and upstream.calls == 2


def test_compact_discovery_refuses_unbounded_single_schema(adapter):
    from mcp import types

    class Upstream:
        async def list_tools(self, cursor=None):
            return types.ListToolsResult(tools=[types.Tool(name='oversized', description='x' * 65536, inputSchema={'type': 'object'})])

    result = asyncio.run(adapter.compact_discover(Upstream(), {'name': 'oversized'}))
    assert result.isError and len(result.model_dump_json()) < 300
