"""Real local HTTPS + official SDK stdio, using synthetic CA/identity only."""
import asyncio
from datetime import datetime, timedelta, timezone
from io import BytesIO
import ipaddress
import json
import socket
import ssl
import sys
from threading import Thread
import time
from zipfile import ZipFile

import anyio
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
import httpx
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import pytest
from starlette.responses import Response
import uvicorn


@pytest.fixture
def local_https(tmp_path, monkeypatch):
    from memory_hub.app import create_app
    from memory_hub.models import Principal
    ca_key = ec.generate_private_key(ec.SECP256R1())
    leaf_key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'Synthetic transport CA')])
    leaf_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'Synthetic loopback server')])
    now = datetime.now(timezone.utc)

    def builder(subject, key):
        return (x509.CertificateBuilder().subject_name(subject).issuer_name(name)
                .public_key(key.public_key()).serial_number(x509.random_serial_number())
                .not_valid_before(now - timedelta(minutes=1)).not_valid_after(now + timedelta(days=1))
                .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
                .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), critical=False))

    ca = (builder(name, ca_key).add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
          .add_extension(x509.KeyUsage(False, False, False, False, False, True, True, False, False), critical=True)
          .add_extension(x509.NameConstraints([x509.IPAddress(ipaddress.ip_network('127.0.0.0/8'))], None), critical=True)
          .sign(ca_key, hashes.SHA256()))
    leaf = (builder(leaf_name, leaf_key).add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .add_extension(x509.KeyUsage(True, False, False, False, False, False, False, False, False), critical=True)
            .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
            .add_extension(x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address('127.0.0.1'))]), critical=False)
            .sign(ca_key, hashes.SHA256()))
    ca_file, cert_file, key_file = (tmp_path / name for name in ('ca.pem', 'server.pem', 'key.pem'))
    ca_file.write_bytes(ca.public_bytes(serialization.Encoding.PEM))
    cert_file.write_bytes(leaf.public_bytes(serialization.Encoding.PEM))
    key_file.write_bytes(leaf_key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    sock = socket.socket()
    sock.bind(('127.0.0.1', 0))
    url = 'https://127.0.0.1:' + str(sock.getsockname()[1])
    monkeypatch.setenv('HUB_PUBLIC_BASE_URL', url)
    monkeypatch.setenv('HUB_PUBLIC_CA_FILE', str(ca_file))
    monkeypatch.setenv('HUB_ALLOWED_HOSTS', 'localhost,127.0.0.1,testserver')
    bearer = 'synthetic-transport-token-123456789'
    app = create_app(database_url='sqlite:///' + str(tmp_path / 'transport.db'), allow_sqlite=True,
        auth_tokens=json.dumps({bearer: {'worker_id': 'real-bearer', 'projects': ['only'], 'role': 'worker'}}))
    app.state.hub.call('create_project', {'project_id': 'only'}, Principal(worker_id='setup', projects=['only'], role='admin'))
    app.state.transport_requests = []

    @app.middleware('http')
    async def record_mcp_transport(request, call_next):
        if request.url.path == '/mcp':
            body = await request.body()
            data = json.loads(body) if body else {}
            # Count actual loopback traffic without retaining headers or bodies.
            app.state.transport_requests.append((request.method, data.get('method'),
                                                  data.get('params', {}).get('name')))
            if data.get('method') == 'tools/call' and getattr(app.state, 'fail_tool_transport', False):
                return Response('synthetic-private-upstream-error-' + bearer, status_code=503)
        return await call_next(request)
    server = uvicorn.Server(uvicorn.Config(app, log_level='critical', access_log=False,
        ssl_certfile=str(cert_file), ssl_keyfile=str(key_file), lifespan='on'))
    thread = Thread(target=server.run, kwargs={'sockets': [sock]}, daemon=True)
    try:
        thread.start()
        deadline = time.monotonic() + 5
        while not server.started and thread.is_alive() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert server.started, 'Owned loopback fixture did not start'
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.load_verify_locations(cafile=str(ca_file))
        context.verify_flags |= ssl.VERIFY_X509_STRICT
        with httpx.Client(verify=context, trust_env=False) as client:
            response = client.get(url + '/downloads/ys-memory-stdio-1.1.0.zip')
            assert response.status_code == 200
        bundle = tmp_path / 'fresh client directory'
        bundle.mkdir()
        with ZipFile(BytesIO(response.content)) as archive:
            for name in ('bridge.py', 'connection.json', 'ys-ai-memory-ca.crt', 'requirements.lock', 'README.txt'):
                (bundle / name).write_bytes(archive.read(name))
        yield bundle, bearer, app, url
    finally:
        server.should_exit = True
        thread.join(timeout=5)
        sock.close()
        assert not thread.is_alive(), 'Owned loopback fixture did not stop'


def test_downloaded_stdio_adapter_relays_live_tools_identity_and_error_without_proxy_or_keylog(local_https, tmp_path):
    bundle, token, app, _ = local_https
    keylog = tmp_path / 'forbidden-keylog.txt'
    env = {'YS_AIMEMORY_TOKEN': token, 'HTTPS_PROXY': 'http://127.0.0.1:1',
           'ALL_PROXY': 'http://127.0.0.1:1', 'SSLKEYLOGFILE': str(keylog), 'PYTHONDONTWRITEBYTECODE': '1'}

    async def run():
        params = StdioServerParameters(command=sys.executable, args=['-B', str(bundle / 'bridge.py')], env=env)
        with anyio.fail_after(20):
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    listed = await session.list_tools()
                    expected = await app.state.mcp.list_tools()
                    assert [tool.model_dump() for tool in listed.tools] == [tool.model_dump() for tool in expected]
                    assert {'send_message', 'list_messages', 'read_session'} <= {tool.name for tool in listed.tools}
                    assert len(listed.tools) == 38
                    inbox = await session.call_tool('get_worker_inbox', {'arguments': {'project_id': 'only'}})
                    assert not inbox.isError
                    payload = inbox.structuredContent or json.loads(inbox.content[0].text)
                    assert payload['worker_id'] == 'real-bearer'
                    denied = await session.call_tool('get_worker_inbox', {'arguments': {'project_id': 'private'}})
                    assert denied.isError and denied.content
                    assert token not in denied.model_dump_json()
    asyncio.run(run())
    assert not keylog.exists()


def test_downloaded_adapter_rejects_hostname_mismatch_before_any_tool_call(local_https):
    bundle, token, _, url = local_https
    config_path = bundle / 'connection.json'
    config = json.loads(config_path.read_text())
    config['endpoint'] = url.replace('127.0.0.1', 'localhost') + '/mcp'
    config_path.write_text(json.dumps(config), encoding='utf-8')

    async def run():
        params = StdioServerParameters(command=sys.executable, args=['-B', str(bundle / 'bridge.py')],
                                       env={'YS_AIMEMORY_TOKEN': token})
        with anyio.fail_after(20):
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
    with pytest.raises(Exception):
        asyncio.run(run())


def test_compact_stdio_is_locally_ready_without_token_or_upstream_requests(local_https, monkeypatch):
    bundle, _, app, _ = local_https
    monkeypatch.delenv('YS_AIMEMORY_TOKEN', raising=False)

    async def run():
        params = StdioServerParameters(command=sys.executable, args=['-B', str(bundle / 'bridge.py'), '--compact'],
                                       env={'YS_AIMEMORY_TOKEN': ''})
        with anyio.fail_after(20):
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    ready = await session.initialize()
                    assert 'local' in ready.instructions.lower()
                    listed = await session.list_tools()
                    assert [tool.name for tool in listed.tools] == ['memory_tools', 'memory_call']
                    assert all(not tool.annotations or tool.annotations.readOnlyHint is not True for tool in listed.tools)
                    assert app.state.transport_requests == []
                    missing = await session.call_tool('memory_tools', {'query': 'inbox'})
                    assert missing.isError
                    assert app.state.transport_requests == []
    asyncio.run(run())


def test_compact_stdio_discovers_one_schema_and_relays_identity_scope_and_validation(local_https):
    bundle, token, app, _ = local_https

    def payload(result):
        assert not result.isError, result
        return result.structuredContent or json.loads(result.content[0].text)

    async def run():
        params = StdioServerParameters(command=sys.executable, args=['-B', str(bundle / 'bridge.py'), '--compact'],
                                       env={'YS_AIMEMORY_TOKEN': token})
        with anyio.fail_after(30):
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    await session.list_tools()
                    assert app.state.transport_requests == []
                    found = payload(await session.call_tool('memory_tools', {'query': 'inbox', 'limit': 1}))
                    assert found['items'][0]['name'] == 'get_worker_inbox'
                    assert set(found['items'][0]) == {'name', 'description'}
                    assert 'inputSchema' not in json.dumps(found)
                    bounded = payload(await session.call_tool('memory_tools', {'limit': 8}))
                    assert len(bounded['items']) == 8 and bounded['has_more']
                    one = payload(await session.call_tool('memory_tools', {'name': 'get_worker_inbox'}))
                    expected = next(tool for tool in (await app.state.mcp.list_tools()) if tool.name == 'get_worker_inbox')
                    assert one['tool'] == expected.model_dump(mode='json', by_alias=True, exclude_none=True)
                    inbox = payload(await session.call_tool('memory_call', {
                        'name': 'get_worker_inbox', 'arguments': {'arguments': {'project_id': 'only'}}}))
                    assert inbox['worker_id'] == 'real-bearer'
                    for name, arguments in (
                        ('get_worker_inbox', {'arguments': {'project_id': 'private'}}),
                        ('create_project', {'arguments': {'project_id': 'only'}}),
                        ('get_worker_inbox', {'arguments': {}}),
                    ):
                        result = await session.call_tool('memory_call', {'name': name, 'arguments': arguments})
                        assert result.isError and token not in result.model_dump_json()
                    calls = [r for r in app.state.transport_requests if r[1] == 'tools/call']
                    assert [r[2] for r in calls] == ['get_worker_inbox', 'get_worker_inbox', 'create_project', 'get_worker_inbox']
                    before = list(app.state.transport_requests)
                    for name, arguments in (
                        ('memory_tools', {'limit': 9}), ('memory_tools', {'limit': True}),
                        ('memory_tools', {'query': token, 'unexpected': token}),
                        ('memory_call', {'name': 'get_worker_inbox', 'arguments': token}),
                        ('unknown_compact_tool', {'secret': token}),
                    ):
                        rejected = await session.call_tool(name, arguments)
                        assert rejected.isError and token not in rejected.model_dump_json()
                    assert app.state.transport_requests == before
                    app.state.fail_tool_transport = True
                    failed = await session.call_tool('memory_call', {
                        'name': 'create_project', 'arguments': {'arguments': {'project_id': 'only'}}})
                    assert failed.isError and 'outcome unconfirmed' in failed.content[0].text
                    assert token not in failed.model_dump_json()
                    assert 'synthetic-private-upstream-error' not in failed.model_dump_json()
                    attempted = [r for r in app.state.transport_requests[len(before):] if r[1] == 'tools/call']
                    assert len(attempted) == 1
    asyncio.run(run())


def test_compact_tls_failure_occurs_only_on_call_and_is_sanitized(local_https):
    bundle, token, app, url = local_https
    config_path = bundle / 'connection.json'
    config = json.loads(config_path.read_text())
    config['endpoint'] = url.replace('127.0.0.1', 'localhost') + '/mcp'
    config_path.write_text(json.dumps(config), encoding='utf-8')

    async def run():
        params = StdioServerParameters(command=sys.executable, args=['-B', str(bundle / 'bridge.py'), '--compact'],
                                       env={'YS_AIMEMORY_TOKEN': token})
        with anyio.fail_after(20):
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    await session.list_tools()
                    assert app.state.transport_requests == []
                    result = await session.call_tool('memory_call', {'name': 'get_worker_inbox', 'arguments': {}})
                    assert result.isError
                    text = result.model_dump_json()
                    assert 'outcome unconfirmed' in text
                    assert token not in text and url not in text and 'localhost' not in text
                    assert app.state.transport_requests == []
    asyncio.run(run())
