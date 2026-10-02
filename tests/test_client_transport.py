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
            response = client.get(url + '/downloads/ys-memory-stdio-1.0.0.zip')
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
                    assert len(listed.tools) == 28
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
