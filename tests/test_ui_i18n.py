"""English release default and scoped Traditional Chinese interface regression."""
from concurrent.futures import ThreadPoolExecutor
from html import unescape
from html.parser import HTMLParser
import json
from pathlib import Path
import re

import pytest
from fastapi.testclient import TestClient

from memory_hub.app import create_app
from memory_hub.i18n import CATALOG, COOKIE, LANGUAGES, default_language, locale, _locale
from memory_hub.models import Principal
from memory_hub.web_chat_assets import chat_script
from memory_hub.web_password import hash_password


@pytest.fixture
def localized(tmp_path, monkeypatch):
    monkeypatch.setenv('HUB_WEB_LANGUAGE', 'en')
    monkeypatch.setenv('HUB_WEB_USERNAME', 'localization-admin')
    monkeypatch.setenv('HUB_WEB_PASSWORD_HASH', hash_password('synthetic-language-password'))
    monkeypatch.setenv('HUB_WEB_PROJECTS', 'visible')
    monkeypatch.setenv('HUB_WEB_ROLE', 'admin')
    monkeypatch.setenv('HUB_WEB_COOKIE_SECURE', 'false')
    monkeypatch.setenv('HUB_WEB_MCP_ENABLED', 'false')
    app = create_app(database_url='sqlite:///'+str(tmp_path/'i18n.db'), allow_sqlite=True,
        auth_tokens=json.dumps({'synthetic-language-token': {'worker_id':'language-worker','projects':['visible'],'role':'worker'}}))
    admin = Principal(worker_id='setup', projects=['visible'], role='admin')
    app.state.hub.call('create_project', {'project_id':'visible'}, admin)
    with TestClient(app) as client:
        csrf = re.search('name="csrf" value="([^"]+)"', client.get('/login').text)[1]
        response = client.post('/login', data={'csrf':csrf,'username':'localization-admin','password':'synthetic-language-password'}, follow_redirects=False)
        assert response.status_code == 303
        yield client, app.state.hub, admin
    app.state.hub.store.engine.dispose()


class Visible(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hidden = 0
        self.values = []
    def handle_starttag(self, tag, attrs):
        if tag in ('script','style'): self.hidden += 1
        if not self.hidden:
            self.values.extend(v for k,v in attrs if k in ('aria-label','placeholder','alt','title') and v)
    def handle_endtag(self, tag):
        if tag in ('script','style'): self.hidden -= 1
    def handle_data(self, data):
        if not self.hidden: self.values.append(data)


@pytest.mark.parametrize('path', ['/login','/help','/ui?project=visible', '/ui?project=visible&view=tasks',
    '/ui?project=visible&view=memory','/ui?project=visible&view=connections','/ui/chat?project=visible',
    '/ui/manage?project=visible&area=memory','/ui/manage?project=visible&area=tasks',
    '/ui/search?project=visible','/ui/inbox?project=visible','/ui/account/password?project=visible','/ui/users?project=visible'])
def test_all_pages_english_default_and_chinese_selection(localized, path):
    client, _, _ = localized
    client.cookies.delete(COOKIE)
    if path == '/login':
        client.cookies.delete('hub_web_session')
    english = client.get(path)
    assert english.status_code == 200
    assert '<html lang="en">' in english.text
    assert english.headers['content-language'] == 'en'
    parser = Visible(); parser.feed(english.text)
    # The language selector deliberately names the alternate language in its own script.
    text = '\n'.join(parser.values).replace('Language / 語言','').replace('繁體中文','').replace('Apply / 套用','')
    assert not re.search(r'[\u3400-\u9fff]', text), text
    chinese = client.get(path+('&' if '?' in path else '?')+'lang=zh-TW')
    assert chinese.status_code == 200
    assert '<html lang="zh-TW">' in chinese.text
    assert chinese.headers['content-language'] == 'zh-TW'
    assert client.cookies.get(COOKIE) == 'zh-TW'
    assert chinese.text != english.text


def test_locale_precedence_invalid_input_and_cookie_security(localized, monkeypatch):
    client, _, _ = localized
    monkeypatch.setenv('HUB_WEB_LANGUAGE','zh-TW')
    client.cookies.delete(COOKIE)
    assert client.get('/help').headers['content-language'] == 'zh-TW'
    client.cookies.set(COOKIE,'en',domain='testserver.local',path='/')
    assert client.get('/help').headers['content-language'] == 'en'
    assert client.get('/help?lang=zh-TW').headers['content-language'] == 'zh-TW'
    bad = client.get('/help?lang=%22%3E%3Cscript%3E')
    assert bad.headers['content-language'] == 'zh-TW'
    assert COOKIE+'=' not in bad.headers.get('set-cookie','')
    monkeypatch.setenv('HUB_WEB_COOKIE_SECURE','true')
    result = client.get('/help?lang=en')
    cookie = result.headers['set-cookie']
    assert 'Secure' in cookie and 'HttpOnly' in cookie and 'SameSite=Lax' in cookie
    monkeypatch.setenv('HUB_WEB_LANGUAGE','unexpected')
    with pytest.raises(ValueError,match='en or zh-TW'): default_language()


def test_switch_preserves_local_page_and_rejects_external_redirect(localized):
    client, _, _ = localized
    result = client.get('/ui/language?lang=zh-TW',headers={'referer':'http://testserver/ui/chat?project=visible&session=abc&lang=en'},follow_redirects=False)
    assert result.headers['location'] == '/ui/chat?project=visible&session=abc'
    assert client.get('/ui/language?lang=en',headers={'referer':'https://evil.invalid/ui'},follow_redirects=False).headers['location'] == '/login'


def test_language_switch_uses_configured_public_origin_behind_http_proxy(monkeypatch, request):
    monkeypatch.setenv('HUB_PUBLIC_BASE_URL','https://public.example:443')
    client, _, _ = request.getfixturevalue('localized')
    referer='https://public.example/ui/chat?project=visible&session=abc&filter=a%26b&filter=c&lang=en#ignored'
    result=client.get('/ui/language?lang=zh-TW',headers={'referer':referer},follow_redirects=False)
    assert result.status_code == 303
    assert result.headers['location']=='/ui/chat?project=visible&session=abc&filter=a%26b&filter=c'
    assert client.cookies.get(COOKIE)=='zh-TW'
    assert client.get('/ui/chat?project=visible&session=abc').headers['content-language']=='zh-TW'
    # Existing direct backend origin remains valid, independently of the public origin.
    direct=client.get('/ui/language?lang=en',headers={'referer':'http://testserver/help'},follow_redirects=False)
    assert direct.headers['location']=='/help'
    for referer in ('https://evil.invalid/ui/chat?project=visible',
                    'http://public.example/ui/chat', 'https://public.example:444/ui/chat',
                    'https://public.example.evil.invalid/ui/chat',
                    'https://user@public.example/ui/chat',
                    'https://public.example:invalid/ui/chat',
                    'https://public.example:0/ui/chat',
                    '//public.example/ui/chat', 'https://public.example//evil.invalid'):
        rejected=client.get('/ui/language?lang=en',headers={'referer':referer,
            'x-forwarded-host':'evil.invalid','x-forwarded-proto':'https',
            'forwarded':'proto=https;host=evil.invalid'},follow_redirects=False)
        assert rejected.headers['location']=='/login',referer
    injected=client.get('/ui/language?lang=en',headers={'referer':'https://injected.invalid/help',
        'x-forwarded-host':'injected.invalid','x-forwarded-proto':'https',
        'forwarded':'proto=https;host=injected.invalid'},follow_redirects=False)
    assert injected.headers['location']=='/login'


def test_language_switch_does_not_trust_unconfigured_https_origin_or_headers(localized, monkeypatch):
    client, _, _ = localized
    # Runtime env edits cannot change the origin captured during app installation.
    monkeypatch.setenv('HUB_PUBLIC_BASE_URL','https://injected.invalid')
    result=client.get('/ui/language?lang=en',headers={'referer':'https://injected.invalid/ui',
        'x-forwarded-host':'injected.invalid','x-forwarded-proto':'https'},follow_redirects=False)
    assert result.headers['location']=='/login'


def test_concurrent_request_locales_are_isolated(localized):
    client, _, _ = localized
    def fetch(lang):
        response=client.get('/help?lang='+lang)
        assert '<html lang="'+lang+'">' in response.text
        assert response.headers['content-language'] == lang
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(fetch, LANGUAGES*6))
    assert locale() == 'en'


def test_user_content_remains_verbatim_and_escaped(localized):
    client, hub, admin = localized
    content='使用者原文 <script>alert("x")</script> English & 中文'
    hub.call('register_source',{'project_id':'visible','source_id':'user-source','uri':'repo://中文','commit':'language-fixture','content':content,'expected_revision':1},admin)
    for lang in LANGUAGES:
        html=client.get('/ui?project=visible&view=memory&lang='+lang).text
        assert '使用者原文' in unescape(html)
        assert '<script>alert("x")</script>' not in html
        assert 'repo://中文' in html


def test_catalog_keys_have_both_languages_and_scripts_are_scoped():
    assert CATALOG
    for key, row in CATALOG.items():
        assert set(row) == set(LANGUAGES), key
        assert all(isinstance(value,str) and value.strip() for value in row.values()), key
    for lang in LANGUAGES:
        token = _locale.set(lang)
        try:
            script = chat_script()
            assert 'const UI_LANGUAGE="'+lang+'"' in script
            assert 'toLocaleString(UI_LANGUAGE)' in script
            assert 'toLocaleTimeString(UI_LANGUAGE)' in script
            used = set(re.findall(r"uiText\(['\"](ui_[a-f0-9]+)['\"]\)",script))
            data = json.loads(re.search(r'const UI_MESSAGES=(.*?); const uiText=',script)[1])
            assert set(data) == used
            assert all(data[key] == CATALOG[key][lang] for key in used)
        finally:
            _locale.reset(token)


def test_translation_resource_is_declared_for_distribution():
    root=Path(__file__).resolve().parents[1]
    assert '"ui_catalog.json"' in (root/'pyproject.toml').read_text(encoding='utf-8')


def test_document_links_work_without_repository_docs(monkeypatch, tmp_path):
    from memory_hub.i18n import documentation_url
    token = _locale.set('en')
    try:
        monkeypatch.setattr(Path, 'is_file', lambda path: False)
        monkeypatch.chdir(tmp_path)
        assert documentation_url('GUIDE.zh-TW.md').endswith('/GUIDE.zh-TW.md')
        assert documentation_url('CLIENT_SETUP.zh-TW.md').endswith('/CLIENT_SETUP.md')
        _locale.set('zh-TW')
        assert documentation_url('CLIENT_SETUP.zh-TW.md').endswith('/CLIENT_SETUP.zh-TW.md')
    finally:
        _locale.reset(token)


@pytest.mark.parametrize('lang, role, expected', [('en', 'admin', 'Posting as Administrator '), ('zh-TW', 'admin', '以 管理員 '), ('en', 'member', 'Posting as Member '), ('zh-TW', 'member', '以 成員 ')])
def test_composer_identity_is_a_complete_sentence_and_escapes_names(localized, monkeypatch, lang, role, expected):
    from dataclasses import replace
    from memory_hub.web_auth import WebAuthStore
    from html import escape

    client, _, _ = localized
    original = WebAuthStore.principal
    name = '教學測試管理員 <img src=x onerror=alert(1)> & {role}'
    def principal(self, current):
        person = original(self, current)
        return replace(person, display_name=name, role=role) if person else person
    monkeypatch.setattr(WebAuthStore, 'principal', principal)
    response = client.get('/ui/chat?project=visible&lang='+lang)
    assert response.status_code == 200
    identity = re.search(r'<div class="composer-by">(.*?)</div>', response.text)[1]
    assert identity == expected + '<strong>' + escape(name, quote=True) + '</strong>' + (' 發言' if lang == 'zh-TW' else '')
    assert '<img' not in identity
    assert 'Use Administrator' not in identity
    assert set(re.findall(r'{([^}]+)}', CATALOG['composer_posting_as'][lang])) == {'role', 'name'}
