"""Request-scoped UI language; never translate project or user supplied content."""
from contextvars import ContextVar
import json
import os
from pathlib import Path
from urllib.parse import parse_qsl, urlencode

LANGUAGES = ('en', 'zh-TW')
COOKIE = 'hub_ui_language'
_locale = ContextVar('hub_ui_language', default=None)
# Published guide siblings shipped with the international release. Production
# wheels do not include the repository's docs directory.
ENGLISH_GUIDES = frozenset({
    'ACCEPTANCE_TESTS', 'API_EXAMPLES', 'ARCHITECTURE', 'AUTOMATIC_CHAT',
    'CLAUDE_WINDOWS_SETUP', 'CLIENT_SETUP', 'DELIVERY_API', 'DEPLOYMENT',
    'EFFICIENT_MCP', 'FOUR_AGENT_RUNBOOK', 'IMPORTING_MEMORY', 'KNOWLEDGE_INDEX',
    'MCP_GENERATOR', 'MCP_MESSAGES', 'MULTI_CLIENT_SETUP', 'NATIVE_CLIENT_CHECK',
    'OPERATION_MANUAL', 'QUICKSTART', 'SHARED_SESSIONS', 'V02_ACCEPTANCE', 'WEB_DASHBOARD',
})


def default_language():
    value = os.getenv('HUB_WEB_LANGUAGE', 'en')
    if value not in LANGUAGES:
        raise ValueError('HUB_WEB_LANGUAGE must be en or zh-TW')
    return value


def locale():
    return _locale.get() or default_language()


def documentation_url(name):
    """Select a published sibling without requiring repository files at runtime."""
    selected = name
    if locale() == 'en' and name.endswith('.zh-TW.md'):
        basename = name[:-len('.zh-TW.md')]
        if basename in ENGLISH_GUIDES:
            selected = basename+'.md'
    return 'https://github.com/Ya19880104/ys-aimemory/blob/main/docs/'+selected


def tr(key):
    """Translate one explicitly marked, trusted interface phrase."""
    return CATALOG[key][locale()]


def js_text(key):
    """A JavaScript string literal, safely embedded under the page's CSP nonce."""
    return json.dumps(tr(key), ensure_ascii=False).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')


def script_catalog(script):
    import re
    keys = set(re.findall(r"uiText\(['\"](ui_[a-f0-9]+)['\"]\)", script))
    values = {key: CATALOG[key][locale()] for key in keys}
    encoded = json.dumps(values, ensure_ascii=False).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
    return 'const UI_LANGUAGE='+json.dumps(locale())+'; const UI_MESSAGES='+encoded+'; const uiText=key=>UI_MESSAGES[key];\n'


CATALOG = json.loads(Path(__file__).with_name('ui_catalog.json').read_text(encoding='utf-8'))


def language_switch():
    label, apply = ('Language', 'Apply') if locale() == 'en' else ('語言', '套用')
    return ('<form class="language-switch" method="get" action="/ui/language">'
            '<label for="ui-language">'+label+'</label>'
            '<select id="ui-language" name="lang" aria-label="'+label+'">'
            + ''.join('<option value="'+value+'"'+(' selected' if value == locale() else '')+'>'+name+'</option>'
                      for value, name in [('en','English'),('zh-TW','繁體中文')])
            + '</select><button type="submit">'+apply+'</button></form>')


class LanguageMiddleware:
    """Strict enum selection, isolated across concurrent requests and threadpool calls."""
    def __init__(self, app):
        self.app = app
        default_language()

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        from starlette.requests import Request
        request = Request(scope)
        selected = request.query_params.get('lang')
        chosen = selected if selected in LANGUAGES else request.cookies.get(COOKIE)
        if chosen not in LANGUAGES:
            chosen = default_language()
        token = _locale.set(chosen)
        async def localized_send(message):
            if message['type'] == 'http.response.start':
                headers = list(message.get('headers', []))
                headers.append((b'content-language', chosen.encode('ascii')))
                if selected in LANGUAGES:
                    secure = os.getenv('HUB_WEB_COOKIE_SECURE', 'true').lower() != 'false'
                    cookie = COOKIE+'='+chosen+'; Path=/; Max-Age=31536000; HttpOnly; SameSite=Lax'
                    if secure:
                        cookie += '; Secure'
                    headers.append((b'set-cookie', cookie.encode('ascii')))
                message = {**message, 'headers': headers}
            await send(message)
        try:
            await self.app(scope, receive, localized_send)
        finally:
            _locale.reset(token)


def install_language(app):
    if getattr(app.state, 'ui_language_installed', False):
        return
    app.state.ui_language_installed = True
    from fastapi import Request
    from fastapi.responses import RedirectResponse
    app.add_middleware(LanguageMiddleware)

    @app.get('/ui/language', include_in_schema=False)
    def change_language(request: Request):
        # Return only to the same origin. No request-controlled open redirect.
        from urllib.parse import urlsplit
        referer = urlsplit(request.headers.get('referer', ''))
        destination = '/login'
        if referer.netloc == request.url.netloc and referer.scheme == request.url.scheme:
            if referer.path == '/help' or referer.path == '/login' or referer.path.startswith('/ui'):
                query = [(k,v) for k,v in parse_qsl(referer.query) if k != 'lang']
                destination = referer.path + ('?'+urlencode(query) if query else '')
        return RedirectResponse(destination, status_code=303)
