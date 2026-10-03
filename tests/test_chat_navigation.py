"""Exercise the shipped chat JavaScript without browser or npm dependencies."""
import json
from pathlib import Path
import re
import shutil
import subprocess

from fastapi.testclient import TestClient
import pytest

from memory_hub.app import create_app
from memory_hub.models import Principal
from memory_hub.web_chat_assets import CHAT_JS
from memory_hub.web_password import hash_password


NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="Node.js is required for chat JavaScript regression tests")


@pytest.mark.parametrize("scenario", [
    "deep_link_outside_first_page",
    "project_change_during_deep_link",
    "project_change_clears_old_rooms",
    "close_pending_artifact",
    "composer_enter_and_ime",
    "restore_last_room",
    "restore_authorization_and_explicit_url",
    "latest_artifacts_outside_message_window",
])
def test_chat_navigation(tmp_path, monkeypatch, scenario):
    # Render the actual page so IDs, focusability and form controls are not
    # maintained as an independent copy of the production markup.
    monkeypatch.setenv("HUB_WEB_USERNAME", "navigation-reader")
    monkeypatch.setenv("HUB_WEB_PASSWORD_HASH", hash_password("synthetic-navigation-password"))
    monkeypatch.setenv("HUB_WEB_PROJECTS", "alpha,beta")
    monkeypatch.setenv("HUB_WEB_ROLE", "read_only" if scenario == "close_pending_artifact" else "admin")
    monkeypatch.setenv("HUB_WEB_COOKIE_SECURE", "false")
    monkeypatch.setenv("HUB_WEB_MCP_ENABLED", "false")
    app = create_app(database_url="sqlite:///" + str(tmp_path / "navigation.db"), allow_sqlite=True,
        auth_tokens=json.dumps({"synthetic-navigation-worker-token": {
            "worker_id": "navigation-worker", "projects": ["alpha", "beta"], "role": "worker"}}))
    admin = Principal(worker_id="setup", projects=["alpha", "beta"], role="admin")
    for project in admin.projects:
        app.state.hub.call("create_project", {"project_id": project}, admin)
    with TestClient(app) as client:
        csrf = re.search('name="csrf" value="([^"]+)"', client.get("/login").text)[1]
        assert client.post("/login", data={"csrf": csrf, "username": "navigation-reader",
            "password": "synthetic-navigation-password"}, follow_redirects=False).status_code == 303
        page = client.get("/ui/chat?project=alpha")
        assert page.status_code == 200
    result = subprocess.run([NODE, str(Path(__file__).with_name("chat_navigation.cjs"))],
        input=json.dumps({"scenario": scenario, "script": CHAT_JS, "html": page.text}),
        capture_output=True, text=True, encoding="utf-8", timeout=15, check=False)
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout) == {"scenario": scenario, "status": "passed"}
