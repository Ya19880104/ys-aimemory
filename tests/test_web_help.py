"""Public help must never turn a configured file into a secret download."""
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
import json

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID
from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest


@pytest.fixture
def certificate():
    key = ec.generate_private_key(ec.SECP256R1())

    def build(ca=True, extension=True):
        subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Synthetic help test CA")])
        now = datetime.now(timezone.utc)
        builder = (x509.CertificateBuilder().subject_name(subject).issuer_name(subject)
                   .public_key(key.public_key()).serial_number(x509.random_serial_number())
                   .not_valid_before(now - timedelta(minutes=1)).not_valid_after(now + timedelta(days=1)))
        if extension:
            builder = builder.add_extension(x509.BasicConstraints(ca=ca, path_length=None), critical=True)
        cert = builder.sign(key, hashes.SHA256())
        return cert, cert.public_bytes(serialization.Encoding.PEM)

    return key, build


def client(monkeypatch, path, base="https://192.0.2.10"):
    from memory_hub.web_help import install_help
    monkeypatch.setenv("HUB_PUBLIC_BASE_URL", base)
    monkeypatch.setenv("HUB_PUBLIC_CA_FILE", str(path))
    app = FastAPI()
    install_help(app)
    return TestClient(app)


def test_help_without_ca_is_public_and_never_uses_request_host(tmp_path, monkeypatch):
    with client(monkeypatch, tmp_path / "missing.crt") as browser:
        response = browser.get("/help", headers={"Host": "attacker.invalid", "X-Forwarded-Host": "attacker.invalid"})
        assert response.status_code == 200
        assert 'lang="zh-Hant"' in response.text
        assert "https://192.0.2.10/ui/mcp" in response.text
        assert "https://192.0.2.10/mcp" in response.text
        assert "attacker.invalid" not in response.text
        assert "CA 尚未提供" in response.text
        assert "線上帳號管理" in response.text
        assert 'id="sessions"' in response.text
        assert 'id="efficient"' in response.text
        assert 'id="accounts"' in response.text
        assert "私有 CA" in response.text
        assert "可信通道" in response.text
        assert "只顯示一次" in response.text
        assert "bearer_token_env_var" in response.text
        assert "${YS_AIMEMORY_TOKEN}" in response.text
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["x-content-type-options"] == "nosniff"
        assert "set-cookie" not in response.headers
        assert browser.head("/help").status_code == 200
        assert browser.head("/help").content == b""
        missing = browser.get("/downloads/ys-ai-memory-ca.crt")
        assert missing.status_code == 404
        assert str(tmp_path) not in missing.text


def test_help_message_examples_can_be_copied_as_tool_arguments(tmp_path, monkeypatch):
    class Examples(HTMLParser):
        def __init__(self):
            super().__init__()
            self.current = None
            self.code = {}

        def handle_starttag(self, tag, attrs):
            if tag == "code":
                self.current = dict(attrs).get("id")
                if self.current:
                    self.code[self.current] = ""

        def handle_data(self, data):
            if self.current:
                self.code[self.current] += data

        def handle_endtag(self, tag):
            if tag == "code":
                self.current = None

    with client(monkeypatch, tmp_path / "missing.crt") as browser:
        parsed = Examples()
        parsed.feed(browser.get("/help").text)
    assert {"message-send-example", "message-list-example", "session-read-example"} <= parsed.code.keys()
    send = json.loads(parsed.code["message-send-example"])
    receive = json.loads(parsed.code["message-list-example"])
    assert send == {
        "project_id": "conversation-sandbox", "recipient_worker_id": "agent-b",
        "thread_id": "hello-20261002", "body": "你好，請回覆你收到的驗收碼 A-123。",
        "idempotency_key": "a-hello-001", "reply_to_message_id": None,
    }
    assert receive == {
        "project_id": "conversation-sandbox", "thread_id": "hello-20261002",
        "after_sequence": 0, "limit": 20,
    }
    # The published compact example must survive HTML rendering and validate
    # against the actual Hub contract, including its nested envelope.
    from memory_hub.models import MODELS
    compact = json.loads(parsed.code["session-read-example"])
    assert compact["name"] == "read_session"
    request = MODELS[compact["name"]].model_validate(compact["arguments"]["arguments"])
    assert request.limit == 5 and request.max_bytes == 4096 and not request.full_text


@pytest.mark.parametrize("base", ["https://192.0.2.10", "https://hub.example.test:9443"])
def test_help_bundle_download_uses_configured_https_origin(tmp_path, monkeypatch, certificate, base):
    class Downloads(HTMLParser):
        def __init__(self):
            super().__init__()
            self.links = {}

        def handle_starttag(self, tag, attrs):
            attrs = dict(attrs)
            if tag == "a" and attrs.get("id"):
                self.links[attrs["id"]] = attrs.get("href")

    _, build = certificate
    path = tmp_path / "public.crt"
    path.write_bytes(build()[1])
    with client(monkeypatch, path, base) as browser:
        response = browser.get("/help", headers={"Host": "attacker.invalid", "X-Forwarded-Proto": "http"})
        parsed = Downloads()
        parsed.feed(response.text)
        assert parsed.links.get("stdio-bundle-download") == base + "/downloads/ys-memory-stdio-1.1.0.zip"
        path.write_bytes(b"not a public CA")
        unavailable = Downloads()
        response = browser.get("/help")
        unavailable.feed(response.text)
        assert response.status_code == 200
        assert "stdio-bundle-download" not in unavailable.links


def test_public_ca_download_and_der_fingerprint(tmp_path, monkeypatch, certificate):
    _, build = certificate
    cert, pem = build()
    path = tmp_path / "public.crt"
    path.write_bytes(pem)
    fingerprint = ":".join(f"{b:02X}" for b in cert.fingerprint(hashes.SHA256()))
    with client(monkeypatch, path) as browser:
        help_page = browser.get("/help")
        assert fingerprint in help_page.text
        assert 'href="/downloads/ys-ai-memory-ca.crt"' in help_page.text
        response = browser.get("/downloads/ys-ai-memory-ca.crt")
        assert response.status_code == 200
        assert response.content == pem
        assert response.headers["content-type"] == "application/x-x509-ca-cert"
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["content-disposition"] == 'attachment; filename="ys-ai-memory-ca.crt"'
        assert response.headers["cache-control"] == "no-store"
        head = browser.head("/downloads/ys-ai-memory-ca.crt")
        assert head.status_code == 200 and head.content == b""
        assert head.headers["content-length"] == str(len(pem))
        assert browser.post("/downloads/ys-ai-memory-ca.crt").status_code == 405


@pytest.mark.parametrize("kind", ["private_key", "cert_and_key", "two_certs", "leaf", "no_constraints", "prefix", "suffix", "malformed", "too_large"])
def test_invalid_or_sensitive_file_is_never_served(tmp_path, monkeypatch, certificate, kind):
    key, build = certificate
    _, pem = build()
    private = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    bodies = {
        "private_key": private, "cert_and_key": pem + private, "two_certs": pem + pem,
        "leaf": build(ca=False)[1], "no_constraints": build(extension=False)[1],
        "prefix": b"sensitive-prefix\n" + pem, "suffix": pem + b"sensitive-suffix\n",
        "malformed": b"-----BEGIN CERTIFICATE-----\ninvalid\n-----END CERTIFICATE-----\n",
        "too_large": b" " * 65537 + pem,
    }
    path = tmp_path / "misconfigured.crt"
    path.write_bytes(bodies[kind])
    with client(monkeypatch, path) as browser:
        for method in ("get", "head"):
            response = getattr(browser, method)("/downloads/ys-ai-memory-ca.crt")
            assert response.status_code == 404
            assert b"PRIVATE KEY" not in response.content
            assert b"sensitive-" not in response.content
        response = browser.get("/help")
        assert response.status_code == 200
        assert "CA 尚未提供" in response.text
        assert "PRIVATE KEY" not in response.text
        assert str(path) not in response.text


def test_ca_is_revalidated_after_file_changes(tmp_path, monkeypatch, certificate):
    _, build = certificate
    path = tmp_path / "rotating.crt"
    path.write_bytes(build()[1])
    with client(monkeypatch, path) as browser:
        assert browser.get("/downloads/ys-ai-memory-ca.crt").status_code == 200
        path.write_bytes(b"not a certificate")
        assert browser.get("/downloads/ys-ai-memory-ca.crt").status_code == 404


@pytest.mark.parametrize("value", ["http://192.0.2.10", "//example.com", "https://user:pass@example.com",
    "https://example.com/help", "https://example.com?x=1", "https://example.com#section", "https://",
    "https://example.com:0", "https://example.com:65536", "https://example.com:bad", "https://example.com\\evil",
    "https://example.com\n", " https://example.com", "https://<script>.invalid", "https://example.com/%2f"])
def test_public_base_rejects_unsafe_urls(value):
    from memory_hub.web_help import public_base_url
    with pytest.raises(ValueError):
        public_base_url(value)


@pytest.mark.parametrize(("value", "expected"), [("", "https://localhost"),
    ("https://192.0.2.10/", "https://192.0.2.10"),
    ("https://hub.example.com:8443", "https://hub.example.com:8443"),
    ("https://[::1]:8443/", "https://[::1]:8443")])
def test_public_base_accepts_https_authority(value, expected):
    from memory_hub.web_help import public_base_url
    assert public_base_url(value) == expected


def test_public_base_default_uses_environment(monkeypatch):
    from memory_hub.web_help import public_base_url
    monkeypatch.setenv("HUB_PUBLIC_BASE_URL", "https://example.test")
    assert public_base_url() == "https://example.test"
