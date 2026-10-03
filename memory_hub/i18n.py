"""Request-scoped UI language; never translate project or user supplied content."""
from contextvars import ContextVar
from html import escape
import json
import logging
import os
import re
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit

LANGUAGES = ('en', 'zh-TW')
COOKIE = 'hub_ui_language'
_locale = ContextVar('hub_ui_language', default=None)
_return_path = ContextVar('hub_ui_return_path', default='/login')
# Published guide siblings shipped with the international release. Production
# wheels do not include the repository's docs directory.
ENGLISH_GUIDES = frozenset({
    'ACCEPTANCE_TESTS', 'API_EXAMPLES', 'ARCHITECTURE', 'AUTOMATIC_CHAT',
    'CHATGPT_PRIVATE_TUNNEL', 'CLAUDE_WINDOWS_SETUP', 'CODEX_CHAT_SETUP', 'CLIENT_SETUP', 'DELIVERY_API', 'DEPLOYMENT',
    'EFFICIENT_MCP', 'FOUR_AGENT_RUNBOOK', 'IMPORTING_MEMORY', 'KNOWLEDGE_INDEX',
    'MCP_GENERATOR', 'MCP_MESSAGES', 'MULTI_CLIENT_SETUP', 'NATIVE_CLIENT_CHECK',
    'OPERATION_MANUAL', 'QUICKSTART', 'SHARED_SESSIONS', 'START_CHATTING', 'V02_ACCEPTANCE', 'WEB_DASHBOARD',
})


def default_language():
    value = os.getenv('HUB_WEB_LANGUAGE', 'en')
    if value not in LANGUAGES:
        raise ValueError('HUB_WEB_LANGUAGE must be en or zh-TW')
    return value


def locale():
    return _locale.get() or default_language()


DEFAULT_DOCS_BASE_URL = 'https://github.com/Ya19880104/ys-aimemory/blob/main/docs'


def _validated_documentation_base_url():
    """A trusted directory URL, or the built-in /help landing-page fallback."""
    value = os.getenv('HUB_DOCS_BASE_URL') or DEFAULT_DOCS_BASE_URL
    error = 'HUB_DOCS_BASE_URL must be an HTTPS or root-relative directory without escapes, credentials, query, fragment or traversal'
    if (len(value) > 2048 or any(ord(c) < 33 or ord(c) > 126 for c in value)
            or any(c in value for c in '%\\?#')):
        raise ValueError(error)
    try:
        target = urlsplit(value)
        if target.scheme:
            if (target.scheme != 'https' or not target.hostname or target.username is not None
                    or target.password is not None or not target.netloc
                    or not re.fullmatch(r'[A-Za-z0-9.\-:\[\]]+', target.netloc)):
                raise ValueError(error)
            target.port  # Validate malformed/out-of-range ports, including IPv6.
        elif target.netloc or not value.startswith('/') or value.startswith('//'):
            raise ValueError(error)
        path = target.path
        if ('//' in path or any(part in {'.', '..'} for part in path.split('/'))
                or not re.fullmatch(r'[A-Za-z0-9_./~-]*', path)):
            raise ValueError(error)
    except ValueError:
        raise ValueError(error) from None
    return value.rstrip('/') or '/'


def documentation_base_url(*, warn=False):
    """Misconfigured mirrors fall back locally without breaking UI requests."""
    try:
        return _validated_documentation_base_url()
    except ValueError:
        if warn:
            # Do not log the rejected value: it may contain credentials or query data.
            logging.getLogger(__name__).warning('Invalid HUB_DOCS_BASE_URL; using the local /help fallback')
        return '/help'


def documentation_url(name):
    """Select a guide sibling; /help is a real landing page, not a docs mount."""
    if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9_-]+(?:\.zh-TW)?\.md', name):
        raise ValueError('Documentation name must be a plain Markdown guide filename')
    selected = name
    if locale() == 'en' and name.endswith('.zh-TW.md'):
        basename = name[:-len('.zh-TW.md')]
        if basename in ENGLISH_GUIDES:
            selected = basename+'.md'
    base = documentation_base_url()
    if base == '/help':
        return '/help?'+urlencode({'lang': locale()})
    return base.rstrip('/')+'/'+selected


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


def local_language_destination(value):
    """Return a canonical relative UI URL; reject encoded path/authority tricks."""
    if (not isinstance(value, str) or len(value) > 8192 or
            any(ord(char) < 32 or ord(char) == 127 for char in value) or '\\' in value):
        return '/login'
    try:
        target = urlsplit(value)
        path = target.path
        if (target.scheme or target.netloc or target.fragment or not path.startswith('/') or
                path.startswith('//') or '%' in path or '//' in path or
                any(part in {'.', '..'} for part in path.split('/')) or
                not (path in {'/help', '/login', '/ui'} or path.startswith('/ui/')) or
                path == '/ui/language'):
            return '/login'
        query = [(key, item) for key, item in parse_qsl(target.query, keep_blank_values=True, max_num_fields=64)
                 if key != 'lang']
    except ValueError:
        return '/login'
    return path + ('?' + urlencode(query) if query else '')


def language_switch():
    label, apply = ('Language', 'Apply') if locale() == 'en' else ('語言', '套用')
    return ('<form class="language-switch" method="get" action="/ui/language">'
            '<input type="hidden" name="return_to" value="'+escape(_return_path.get(), quote=True)+'">'
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
        documentation_base_url(warn=True)

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
        return_token = _return_path.set(local_language_destination(request.url.path + '?' + request.url.query))
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
            _return_path.reset(return_token)


def install_language(app):
    if getattr(app.state, 'ui_language_installed', False):
        return
    app.state.ui_language_installed = True
    from fastapi import Request
    from fastapi.responses import RedirectResponse
    from urllib.parse import urlsplit
    # Resolve the explicit operator origin at installation time. Import locally
    # after modules load: web_help consumes i18n while defining its validator.
    public_origin = None
    if os.getenv('HUB_PUBLIC_BASE_URL'):
        from .web_help import public_base_url
        public_origin = urlsplit(public_base_url())
    app.add_middleware(LanguageMiddleware)

    @app.get('/ui/language', include_in_schema=False)
    def change_language(request: Request):
        # Forms carry an explicit local destination because pages deliberately
        # suppress Referer. Never fall back to a header for a rejected target.
        if 'return_to' in request.query_params:
            destination = local_language_destination(request.query_params.get('return_to'))
            return RedirectResponse(destination, status_code=303)
        # Backward-compatible same-origin links without the new form field.
        destination = '/login'
        def origin(value):
            if value.scheme not in ('http', 'https') or value.username is not None or value.password is not None:
                return None
            port = value.port
            if not value.hostname or (port is not None and not 1 <= port <= 65535):
                return None
            return (value.scheme, value.hostname, port if port is not None else (443 if value.scheme == 'https' else 80))
        raw = request.headers.get('referer', '')
        try:
            referer = urlsplit(raw)
            trusted = {origin(urlsplit(str(request.url)))}
            if public_origin is not None:
                trusted.add(origin(public_origin))
            accepted = (not any(ord(char) <= 32 or ord(char) == 127 for char in raw)
                and '\\' not in raw and origin(referer) is not None and origin(referer) in trusted)
        except ValueError:
            accepted = False
        if accepted:
            if referer.path == '/help' or referer.path == '/login' or referer.path.startswith('/ui'):
                destination = local_language_destination(referer.path + ('?' + referer.query if referer.query else ''))
        return RedirectResponse(destination, status_code=303)
