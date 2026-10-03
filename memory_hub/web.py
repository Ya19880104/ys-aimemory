"""Role-scoped human dashboard and management. Browser sessions never become MCP credentials.

Opaque sessions, login throttles, human accounts and one-use forms are persisted
in the database. Account edits and runtime security-policy changes revoke sessions.
"""
from .i18n import tr, locale, language_switch
from dataclasses import dataclass
from datetime import datetime, timezone
from html import escape
import hmac
import os
import re
import secrets
import time
from uuid import UUID
from urllib.parse import parse_qs, urlencode, urlsplit

from fastapi import Request
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.concurrency import run_in_threadpool
from sqlalchemy import select
from .store import projects, events
from .web_password import valid_hash

COOKIE = 'hub_web_session'
LOGIN_COOKIE = 'hub_web_login'


def safe_chat_return(value):
    """Canonical room navigation only; never retain arbitrary URLs or queries."""
    fallback = '/ui/chat'
    if not isinstance(value, str) or len(value) > 2048 or any(ord(c) < 32 for c in value):
        return fallback
    try:
        target = urlsplit(value)
        if target.scheme or target.netloc or target.path != fallback or target.fragment:
            return fallback
        values = parse_qs(target.query, keep_blank_values=True, max_num_fields=20)
    except ValueError:
        return fallback
    query = {}
    patterns = {'project': r'[a-zA-Z0-9_.-]{1,128}', 'session': r'[0-9a-f]{32}',
                'lang': r'en|zh-TW'}
    for key, pattern in patterns.items():
        entries = values.get(key)
        if entries is not None:
            if len(entries) != 1 or re.fullmatch(pattern, entries[0]) is None:
                return fallback
            query[key] = entries[0]
    return fallback + ('?' + urlencode(query) if query else '')


def chat_login_redirect(request):
    target = safe_chat_return(request.url.path + '?' + request.url.query)
    path = '/login' + ('?' + urlencode({'return_to': target}) if target != '/ui/chat' else '')
    return RedirectResponse(path, status_code=303,
                            headers={'Cache-Control': 'no-store', 'Referrer-Policy': 'no-referrer'})


@dataclass
class WebConfig:
    username: str
    password_hash: str
    projects: tuple[str, ...]
    secure: bool = True
    ttl: int = 3600
    role: str = "read_only"
    mcp_enabled: bool = False
    owner_id: str = ''

    def __post_init__(self):
        if self.role not in {"read_only", "admin"}:
            raise ValueError("HUB_WEB_ROLE must be read_only or admin")
        if self.mcp_enabled:
            try:
                self.owner_id = str(UUID(self.owner_id))
            except (ValueError, TypeError, AttributeError):
                raise ValueError('HUB_WEB_OWNER_ID must be a stable UUID when MCP management is enabled') from None

    @classmethod
    def from_env(cls):
        fields = [os.getenv('HUB_WEB_USERNAME', ''), os.getenv('HUB_WEB_PASSWORD_HASH', ''), os.getenv('HUB_WEB_PROJECTS', '')]
        if not any(fields):
            return None
        if not all(fields) or not valid_hash(fields[1]):
            raise RuntimeError('Dashboard requires HUB_WEB_USERNAME, valid HUB_WEB_PASSWORD_HASH and HUB_WEB_PROJECTS; no default credentials exist')
        scope = tuple(x.strip() for x in fields[2].split(',') if x.strip())
        if not scope or '*' in scope:
            raise RuntimeError('HUB_WEB_PROJECTS must explicitly list readable project IDs')
        ttl = int(os.getenv('HUB_WEB_SESSION_TTL', '3600'))
        if not 300 <= ttl <= 28800:
            raise RuntimeError('HUB_WEB_SESSION_TTL must be between 300 and 28800 seconds')
        secure = os.getenv('HUB_WEB_COOKIE_SECURE', 'true').lower()
        if secure not in ('true', 'false'):
            raise RuntimeError('HUB_WEB_COOKIE_SECURE must be true or false')
        enabled = os.getenv('HUB_WEB_MCP_ENABLED', 'false').lower()
        if enabled not in ('true', 'false'):
            raise RuntimeError('HUB_WEB_MCP_ENABLED must be true or false')
        return cls(*fields[:2], scope, secure == 'true', ttl, os.getenv('HUB_WEB_ROLE', 'read_only'),
                   enabled == 'true', os.getenv('HUB_WEB_OWNER_ID', ''))

    @classmethod
    def policy_from_env(cls):
        """Runtime settings after bootstrap; no environment identity is needed."""
        secure = os.getenv('HUB_WEB_COOKIE_SECURE', 'true').lower()
        enabled = os.getenv('HUB_WEB_MCP_ENABLED', 'false').lower()
        ttl = int(os.getenv('HUB_WEB_SESSION_TTL', '3600'))
        if secure not in ('true', 'false') or enabled not in ('true', 'false') or not 300 <= ttl <= 28800:
            raise RuntimeError('Invalid browser cookie, session lifetime or MCP feature setting')
        # owner_id validation belongs to the credential-bearing bootstrap only.
        policy = cls('', '', (), secure == 'true', ttl)
        policy.mcp_enabled = enabled == 'true'
        return policy


def e(value):
    return escape(str(value), quote=True)


def stamp(value):
    return datetime.fromtimestamp(value, timezone.utc).strftime('%m/%d %H:%M UTC') if value else (tr('ui_3e1b52c88f58'))

CSS = '''
.manual nav{display:flex;flex-wrap:wrap;gap:6px 14px;margin:24px 0}.manual section.panel{margin:20px 0;scroll-margin-top:20px}.manual pre{white-space:pre-wrap;overflow-wrap:anywhere}.manual header>.button{flex-shrink:0;display:inline-block}.manual li+li{margin-top:8px}
.manual h3{margin:20px 0 8px}.manual h4{margin:14px 0 4px}.manual table{width:100%;border-collapse:collapse;table-layout:fixed;font-size:13px}.manual th,.manual td{text-align:left;vertical-align:top;padding:9px;border-bottom:1px solid var(--line);overflow-wrap:anywhere}.manual th{color:var(--accent)}
.management{max-width:1100px;margin:auto}:root{color-scheme:dark;--bg:#0b1019;--panel:#141c29;--line:#283346;--muted:#91a1ba;--text:#e9eff8;--accent:#a4e6cf}*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:15px/1.7 system-ui,-apple-system,"Noto Sans TC",sans-serif}a{color:var(--accent);text-decoration:none}a:hover{text-decoration:underline}button,input,select,textarea{font:inherit}textarea{min-height:130px;resize:vertical}button,.button{border:0;background:var(--accent);color:#10231e;padding:10px 18px;border-radius:9px;cursor:pointer;font-weight:650}button:hover{filter:brightness(1.1)}button:focus-visible,a:focus-visible,summary:focus-visible{outline:3px solid #8bc4ff;outline-offset:3px}input,select,textarea{background:#0e1521;color:var(--text);border:1px solid #42506a;padding:11px 13px;border-radius:8px;width:100%}label{display:block;margin:16px 0 6px}.shell{max-width:1440px;margin:auto;display:grid;grid-template-columns:230px 1fr;min-height:100vh}aside{padding:30px 23px;border-right:1px solid var(--line)}.brand{font-size:21px;font-weight:750;letter-spacing:-.5px}.brand small{display:block;font-size:11px;letter-spacing:2px;color:var(--muted);margin-top:3px}nav{display:grid;gap:9px;margin:35px 0}nav a{padding:9px 12px;border-radius:8px;color:#c1cee1}nav a:hover{background:var(--panel)}.aside-note{font-size:12px;color:var(--muted);margin-top:30px}main{padding:34px 38px;min-width:0}header{display:flex;justify-content:space-between;align-items:center;gap:20px;margin-bottom:30px}h1{font-size:30px;line-height:1.3;margin:4px 0 9px;letter-spacing:-1px}h2{font-size:19px;margin:0}h3{font-size:16px;margin:0}.muted,small{color:var(--muted)}.eyebrow{color:var(--accent);font-size:11px;font-weight:750;letter-spacing:2px}.project-select{display:flex;gap:10px;max-width:350px}.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:15px;margin:24px 0}.stat,.panel{background:var(--panel);border:1px solid var(--line);border-radius:13px;padding:21px}.stat strong{display:block;font-size:30px;color:var(--text);line-height:1.4}.stat span{font-size:12px;color:var(--muted)}.section-head{display:flex;align-items:center;justify-content:space-between;gap:12px;margin:29px 0 13px}.badge{display:inline-block;background:#25354b;color:#c8d9f2;border:1px solid #394b66;border-radius:20px;font-size:11px;padding:2px 9px;white-space:nowrap}.badge.good{background:#183a31;border-color:#2d5749;color:#ade6cd}.badge.warn{background:#44381f;border-color:#68552d;color:#f2d79e}.grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}.task{margin-bottom:12px}.task-head{display:flex;justify-content:space-between;gap:12px}.task p{margin:12px 0}.meta{display:flex;flex-wrap:wrap;gap:8px 18px;font-size:12px;color:var(--muted)}.path,code{font:12px/1.6 ui-monospace,SFMono-Regular,monospace;overflow-wrap:anywhere;color:#b5cce8}.empty{padding:25px;text-align:center;color:var(--muted);border:1px dashed #39465b;border-radius:12px}.empty strong{display:block;color:var(--text);font-size:15px}.row{padding:15px 0;border-bottom:1px solid var(--line)}.row:last-child{border:0}.row-title{display:flex;gap:12px;justify-content:space-between;align-items:center}.body-text{white-space:pre-wrap;overflow-wrap:anywhere;font-size:13px;color:#c1cee1}summary{cursor:pointer;color:var(--accent);font-size:12px;margin-top:12px}.connection{display:flex;align-items:center;justify-content:space-between;gap:15px}.dot{display:inline-block;width:8px;height:8px;border-radius:50%;background:#8badbd;margin-right:8px}.alert{background:#392b20;border:1px solid #675039;color:#ecccaa;padding:12px 16px;border-radius:9px;margin:15px 0;font-size:13px}.login{max-width:440px;margin:10vh auto;padding:0 22px}.login .panel{margin-top:26px;padding:30px}.login button{width:100%;margin-top:23px}.login h1{font-size:27px}.topline{display:flex;justify-content:space-between;gap:12px}.logout button{background:transparent;border:1px solid var(--line);color:var(--muted);font-size:12px;padding:6px 12px}.timeline{border-left:2px solid #33455d;padding-left:17px;margin:16px 0 0 7px}.timeline p{font-size:12px;margin:7px 0}.foot{margin:35px 0;font-size:12px;color:var(--muted)}@media(max-width:1000px){.shell{grid-template-columns:190px 1fr}main{padding:26px 22px}.grid{grid-template-columns:1fr}.stats{grid-template-columns:1fr 1fr}}@media(max-width:640px){.shell{display:block}aside{padding:18px 20px;border-right:0;border-bottom:1px solid var(--line)}aside nav{display:flex;overflow:auto;margin:14px 0 0;gap:3px}nav a{white-space:nowrap;padding:6px 10px}.aside-note{display:none}main{padding:23px 16px}header{display:block}h1{font-size:25px}.project-select{margin-top:18px;max-width:none}.panel{padding:17px}.stats{gap:9px}.stat{padding:15px}.task-head{display:block}.task-head .badge{margin-top:8px}}
.shell aside nav{gap:2px;margin:24px 0}.shell aside nav a{padding:7px 11px}.shell aside nav a[aria-current="page"]{background:var(--panel);color:var(--accent)}.nav-label{font-size:11px;color:var(--muted);padding:13px 11px 4px}.project-select{min-width:0;width:350px;flex-shrink:0}.project-select select{min-width:0;flex:1}.project-select button{flex:0 0 auto;white-space:nowrap}.project-context{border-left:3px solid var(--accent);padding:8px 14px;color:var(--muted);font-size:13px;overflow-wrap:anywhere}.project-context strong{color:var(--text);margin-left:8px}.project-context span{display:block;margin-top:3px}.task h3{overflow-wrap:anywhere}.management .project-context{margin:16px 0}
@media(max-width:1000px){.shell header{align-items:flex-start;flex-direction:column}.project-select{width:100%;max-width:420px}}@media(max-width:640px){.shell aside nav{display:flex;flex-wrap:wrap;overflow:visible;gap:3px;margin:12px 0 0}.shell aside nav a{white-space:normal}.shell aside .nav-label{flex-basis:100%;padding-left:10px}.project-select{max-width:none}.project-context strong{display:block;margin:2px 0}.shell .topline{align-items:center}}
/* Hallmark · existing dark/mint workbench · hierarchy: one project navigation, contextual tabs. */
.workspace-shell{grid-template-columns:230px minmax(0,1fr)}.workspace-shell aside{display:flex;flex-direction:column;gap:24px;padding:28px 22px}.workspace-shell .brand small{letter-spacing:1px}.workspace-project label{margin:0 0 7px;color:var(--muted);font-size:12px}.workspace-project>div{display:flex;gap:6px;min-width:0}.workspace-project select{min-width:0;flex:1;padding:9px 8px;font-size:12px}.workspace-project button{flex:0 0 auto;padding:8px 10px;font-size:12px;white-space:nowrap}.workspace-shell aside nav{margin:0;gap:5px;display:grid}.workspace-shell aside nav a{padding:10px 12px;white-space:nowrap}.workspace-shell .workspace-utilities{margin-top:28px;padding-top:18px;border-top:1px solid var(--line)}.workspace-user{font-size:12px;color:var(--muted);overflow-wrap:anywhere;margin-top:auto}.workspace-heading{display:flex;justify-content:space-between;align-items:flex-start;gap:18px;margin-bottom:26px}.workspace-context{color:var(--muted);font-size:13px;margin:0 0 6px;overflow-wrap:anywhere}.workspace-heading h1{font-size:27px;margin:0}.section-tabs{display:flex;flex-wrap:wrap;gap:5px;margin:0 0 24px;padding-bottom:12px;border-bottom:1px solid var(--line)}.section-tabs a{white-space:nowrap;padding:8px 12px}.section-tabs a[aria-current="page"]{background:var(--panel);color:var(--accent)}.workspace-shell .section-head{margin-top:18px}.workspace-shell .stats{margin-top:24px}.workspace-shell .management{padding:0}.workspace-shell .panel+.panel{margin-top:16px}
@media(max-width:768px){.workspace-shell{grid-template-columns:190px minmax(0,1fr)}.workspace-shell aside{padding:24px 14px}.workspace-heading h1{font-size:24px}}
@media(max-width:640px){.workspace-shell{display:block}.workspace-shell aside{gap:14px;padding:18px 16px}.workspace-shell .brand small,.workspace-user{display:none}.workspace-shell aside nav{display:flex;flex-wrap:wrap;gap:3px}.workspace-shell aside nav a{padding:6px 10px;white-space:nowrap}.workspace-shell .workspace-utilities{margin-top:0;padding-top:8px}.workspace-project{max-width:none}.workspace-heading{margin-bottom:20px}.workspace-context{max-width:220px}.section-tabs{gap:2px}.section-tabs a{font-size:13px;padding:7px 9px}.workspace-shell .section-head{align-items:flex-start;flex-direction:column}}
'''


LANGUAGE_CSS = '.language-switch{display:flex;align-items:center;justify-content:flex-end;gap:8px;padding:8px 16px;font-size:12px}.language-switch label{margin:0}.language-switch select{width:auto;padding:3px 6px}.language-switch button{padding:4px 9px;font-size:12px}.chat-app{height:calc(100dvh - 49px)}'

def page(body, status=200, script='', *, css='', connect=False):
    nonce = secrets.token_urlsafe(18)
    extra = '<script nonce="'+nonce+'">'+script+'</script>' if script else ''
    script_policy = f"; script-src 'nonce-{nonce}'" if script else ''
    connect_policy = "; connect-src 'self'" if connect else ''
    return HTMLResponse(('<!doctype html><html lang="'+locale()+'"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>' + tr('ui_7e79db7926ba') + '</title><style nonce="')+nonce+'">'+CSS+LANGUAGE_CSS+css+'</style></head><body>'+language_switch()+body+extra+'</body></html>', status_code=status, headers={'Cache-Control':'no-store', 'Pragma':'no-cache', 'X-Content-Type-Options':'nosniff', 'X-Frame-Options':'DENY', 'Referrer-Policy':'no-referrer', 'Content-Security-Policy':f"default-src 'none'; style-src 'nonce-{nonce}'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'"+script_policy+connect_policy})


def badge(text, kind=''):
    return '<span class="badge '+kind+'">'+e(text)+'</span>'


def empty(title, detail):
    return '<div class="empty"><strong>'+e(title)+'</strong>'+e(detail)+'</div>'


def render_handoff(record):
    """Render preserved handoff evidence without treating it as trusted HTML."""
    result = ('<div class="panel"><h3>' + tr('ui_54752d67e87d'))+e(record.get('to_worker', '—'))+'</h3>'
    result += '<p class="body-text">'+e(record.get('summary', ''))+'</p>'
    result += ('<div class="path">' + tr('ui_7fcc0205ab8c'))+e(record.get('result_commit', (tr('ui_756762e293f2'))))+'</div>'
    for title, key in [((tr('ui_fc2a75673f77')), 'changed_artifacts'), ((tr('ui_b8264ae4130f')), 'blockers'), ((tr('ui_2c763637cbaa')), 'next_steps')]:
        values = record.get(key, [])
        result += '<h4>'+title+'</h4>'
        result += '<ul>'+''.join('<li class="body-text">'+e(item)+'</li>' for item in values)+'</ul>' if values else ('<p class="muted">' + tr('ui_fe8e76c5e348') + '</p>')
    result += ('<h4>' + tr('ui_713cf1a97ccf') + '</h4>')
    for test in record.get('test_results', []):
        status = test.get('status', 'not_run')
        label = {'passed':(tr('ui_dd55c6c25912')), 'failed':(tr('ui_37d266e0ab12')), 'not_run':(tr('ui_d2297ba2384d'))}.get(status, (tr('ui_4d8c1c5b4283')))
        result += '<div class="row">'+badge(label, 'good' if status == 'passed' else 'warn')+'<div class="path">'+e(test.get('command', ''))+'</div><div class="body-text">'+e(test.get('details', ''))+'</div></div>'
    result += ('<p class="muted">' + tr('ui_b48f2019ad05') + '</p></div>')
    return result


def render_recovery(record):
    target = record.get('to_worker') or (tr('ui_090aaa435c53'))
    return (('<div class="row"><h4>' + tr('ui_198a9c0b5bf9') + '</h4><div class="meta">')
            +e(record.get('recovered_by', ''))+' · '+e(stamp(record.get('at')))
            +' · Fence '+e(record.get('fence', ''))+'</div><div class="body-text">'
            +e(record.get('reason', ''))+('</div><div class="meta">' + tr('ui_e64d0deff642'))
            +e(target)+('</div><p class="muted">' + tr('ui_d02ef54a78cb') + '</p></div>'))


def section_name(section):
    return {'overview':(tr('ui_09bb87a333bc')), 'chat':(tr('ui_932be7091ff4')), 'tasks':(tr('ui_f041aecabf60')), 'memory':(tr('ui_2892879e37b9')), 'connections':(tr('ui_e6d6f89902cb')), 'settings':(tr('ui_0d8619aae051'))}[section]


def workspace_url(section, project):
    path = '/ui/chat' if section == 'chat' else '/ui/account/password' if section == 'settings' else '/ui'
    query = {'project': project}
    if section not in ('overview', 'chat', 'settings'): query['view'] = section
    return path+'?'+urlencode(query)


def project_navigation(config, selected, identity=None, active='overview'):
    def item(section):
        return '<a href="'+e(workspace_url(section,selected))+'"'+(' aria-current="page"' if section==active else '')+'>'+section_name(section)+'</a>'
    return ('<nav class="workspace-nav" aria-label="' + tr('ui_8f347997bc92') + '">')+''.join(item(k) for k in ('overview','chat','tasks','memory','connections'))+('</nav><nav class="workspace-utilities" aria-label="' + tr('ui_7e77dcbfd35d') + '">')+item('settings')+('<a href="/help">' + tr('ui_b75700a270c5') + '</a></nav>')


def section_tabs(section, active, project, config, identity):
    def url(path, **query): return path+'?'+urlencode({'project':project,**query})
    admin = (identity.role if identity else config.role) == 'admin'
    rows = []
    if section == 'tasks':
        rows = [('list',(tr('ui_f3874509edba')),workspace_url('tasks',project)),('inbox',(tr('ui_2899af743145')),url('/ui/inbox'))]
        if admin: rows.append(('edit',(tr('ui_e14e0d0691bd')),url('/ui/manage',area='tasks')))
    elif section == 'memory':
        rows = [('list',(tr('ui_ecefa6cc85b3')),workspace_url('memory',project)),('search',(tr('ui_03c481a6ab85')),url('/ui/search'))]
        if admin: rows.append(('edit',(tr('ui_eb29d2c20f3d')),url('/ui/manage',area='memory')))
    elif section == 'connections':
        rows = [('list',(tr('ui_1c2b2d825ce3')),workspace_url('connections',project))]
        if admin and config.mcp_enabled: rows.append(('edit',(tr('ui_f3c3f05c32de')),url('/ui/mcp')))
    elif section == 'settings':
        rows = [('password',(tr('ui_475fe4d4bf58')),url('/ui/account/password'))]
        if identity and identity.can_manage_users: rows.append(('users',(tr('ui_e4d7d9dd6324')),url('/ui/users')))
        if admin:
            rows.append(('project',(tr('ui_181ad3312ed1')),url('/ui/mcp',setup='project') if config.mcp_enabled else url('/ui/manage',area='project')))
    if not rows: return ''
    return '<nav class="section-tabs" aria-label="'+section_name(section)+(tr('ui_3df5273225ef'))+''.join('<a href="'+e(href)+'"'+(' aria-current="page"' if key==active else '')+'>'+label+'</a>' for key,label,href in rows)+'</nav>'


def workspace_shell(title, body, project, config, identity, csrf, section='overview', tab='list', choices=None):
    choices = choices if choices is not None else (identity.projects if identity else config.projects)
    options = ''.join('<option value="'+e(p)+'"'+(' selected' if p==project else '')+'>'+e(p)+'</option>' for p in sorted(choices))
    switch = ''
    if options:
        target = workspace_url(section, project).split('?')[0]
        switch = '<form class="workspace-project" action="'+target+('" method="get"><label for="workspace-project">' + tr('ui_e564b916b12e') + '</label><div><select id="workspace-project" name="project" aria-label="' + tr('ui_f7e540512d3c') + '">')+options+('</select><button>' + tr('ui_873b0afae9ba') + '</button></div>')
        if section not in ('overview','chat','settings'): switch += '<input type="hidden" name="view" value="'+e(section)+'">'
        switch += '</form>'
    who = identity.display_name if identity else config.username
    header = '<div class="workspace-heading"><div><p class="workspace-context">'+e(project or (tr('ui_14bee9923d27')))+'</p><h1>'+e(title)+'</h1></div><form class="logout" action="/logout" method="post"><input type="hidden" name="csrf" value="'+e(csrf)+('"><button>' + tr('ui_057f31bc16c8') + '</button></form></div>')
    alert = '' if config.secure else ('<div class="alert">' + tr('ui_5cbf7e80cc31') + '</div>')
    return ('<div class="shell workspace-shell"><aside><div class="brand">ys-aimemory<small>' + tr('ui_8c38475ee858') + '</small></div>')+switch+project_navigation(config,project,identity,section)+'<p class="workspace-user">'+e(who)+'</p></aside><main>'+header+section_tabs(section,tab,project,config,identity)+alert+body+'</main></div>'


def render_dashboard(config, selected, states, audit, principals, csrf, now, *, identity=None, view='overview', task_after=''):
    state = states.get(selected, {})
    tasks = state.get('tasks', {})
    sources = state.get('sources', {})
    decisions = state.get('decisions', {})
    active = sum(bool(t.get('owner') and t.get('lease_until', 0) > now) for t in tasks.values())
    pending = sum(bool(t.get('pending_recipient')) for t in tasks.values())
    overview = ('<p class="muted">' + tr('ui_d5c151b2adde') + '</p>')
    overview += '<div class="stats">'+''.join('<div class="stat"><span>'+label+'</span><strong>'+e(value)+'</strong></div>' for label,value in [((tr('ui_b2b0a879e55c')),len(tasks)),((tr('ui_94cc635c1e5f')),active),((tr('ui_0a927d059929')),pending),((tr('ui_5a26cfc1ab9f')),len(sources))])+'</div>'
    if not states: overview += empty((tr('ui_65a953f1277a')), (tr('ui_94bf422b2d40')))
    body = ('<section id="tasks"><div class="section-head"><h2>' + tr('ui_f3874509edba') + '</h2>')+badge(str(len(tasks))+(tr('ui_3538219b48aa')))+'</div>'
    task_ids = sorted(tid for tid in tasks if not task_after or tid > task_after)
    for task_id in task_ids[:20]:
        t = tasks[task_id]
        live = bool(t.get('owner') and t.get('lease_until',0) > now)
        accepted_packet = state.get('packets', {}).get((t.get('accepted') or {}).get('packet_id'), {})
        accepted_current = bool(live and accepted_packet and accepted_packet.get('context_revision') == state.get('revision') and accepted_packet.get('task_generation') == t.get('generation') and (t.get('accepted') or {}).get('fence') == t.get('fence'))
        status = (tr('ui_f28461bb49c8')) if t['status'] == 'completed' else ((tr('ui_eed5d32d162e'))+str(t['pending_recipient'])+(tr('ui_818afede9783')) if t.get('pending_recipient') else ((tr('ui_039833e5697d')) if live else (tr('ui_3adc54e36397'))))
        body += '<article class="panel task"><div class="task-head"><h3><a href="'+e('/ui/task?'+urlencode({'project':selected,'task':task_id}))+'">'+e(task_id)+'</a></h3>'+badge(status, 'good' if live or t['status']=='completed' else 'warn')+'</div><p>'+e(t['goal'])+('</p><div class="meta"><span>' + tr('ui_d37f774c768b'))+e(t.get('owner') or '—')+'</span><span>Fence '+e(t.get('fence',0))+('</span><span>' + tr('ui_8854dfaa36b6'))+e(stamp(t.get('lease_until')))+('</span><span>' + tr('ui_08b698ba5bcb'))+((tr('ui_ed404ac4c8fe')) if accepted_current else (tr('ui_3b865471662f')))+('</span></div><details><summary>' + tr('ui_44446b068adf') + '</summary><p class="path">')+e(' · '.join(t.get('allowed_paths',[])))+'</p><ul>'+''.join('<li>'+e(x)+'</li>' for x in t.get('acceptance_criteria',[]))+'</ul>'
        packets = [v for v in state.get('packets', {}).values() if v.get('task_id') == task_id]
        for packet in sorted(packets, key=lambda x:x.get('prepared_at',0), reverse=True)[:8]:
            fresh = packet.get('context_revision') == state.get('revision') and packet.get('task_generation') == t.get('generation')
            body += ('<div class="row"><div class="meta">' + tr('ui_51c0fec7d38a'))+e(packet['worker_id'])+' · r'+e(packet['context_revision'])+' · '+((tr('ui_c2f0001e7e2e')) if fresh else (tr('ui_9b42a6cda2e5')))+' · '+((tr('ui_2aff58e58e12')) if packet.get('acknowledged') else (tr('ui_a1404211a481')))+'</div><div class="path">'+e(packet['workspace'])+'<br>'+e(packet['branch'])+' @ '+e(packet['commit'])+'</div></div>'
        for cp in t.get('checkpoints',[]):
            body += '<div class="row"><div class="meta">'+e(cp['binding']['worker_id'])+' · '+e(cp['kind'])+' · '+e(stamp(cp['at']))+'</div><div class="body-text">'+e(cp['summary'])+'</div><div class="path">'+e(cp['binding']['branch'])+' @ '+e(cp['binding']['commit'])+'</div></div>'
        if not t.get('checkpoints'):
            body += ('<p class="muted">' + tr('ui_14fa3a491d53') + '</p>')
        for handoff in t.get('handoffs', []):
            body += render_handoff(handoff)
        for recovery in t.get('recoveries', []):
            body += render_recovery(recovery)
        body += '</details></article>'
    if not tasks:
        body += empty((tr('ui_19dcc4d081c0')), (tr('ui_0eb8faf6261f')))
    if task_after or len(task_ids)>20:
        body += '<p class="pagination">'
        if task_after: body += '<a href="'+e(workspace_url('tasks',selected))+(tr('ui_57ed178a33c7') + '</a> ')
        if len(task_ids)>20: body += '<a href="'+e(workspace_url('tasks',selected)+'&'+urlencode({'after':task_ids[19]}))+(tr('ui_774069bf8efc') + '</a>')
        body += '</p>'
    tasks_html = body+'</section>'
    body = ('<section id="memory"><div class="section-head"><h2>' + tr('ui_11ea94060a08') + '</h2>')+badge((tr('ui_d37ff8d5c69e')))+('</div><div class="grid"><div class="panel"><h3>' + tr('ui_141ce3c9baf5') + '</h3>')
    for sid,source in sources.items():
        current = source['current']
        body += '<div class="row"><div class="row-title"><strong>'+e(sid)+'</strong>'+badge(str(len(source['versions']))+(tr('ui_f594f171672d')))+'</div><div class="path">'+e(current['uri'])+'<br>commit '+e(current['commit'])+'<br>SHA-256 '+e(current['sha256'])+('</div><details><summary>' + tr('ui_21aab6283ec4') + '</summary><div class="body-text">')+e(current['content'])+'</div></details></div>'
    if not sources: body += ('<p class="muted">' + tr('ui_5ccaf337c1ee') + '</p>')
    body += ('</div><div class="panel"><h3>' + tr('ui_c0a28e5e3808') + '</h3>')
    for did,d in decisions.items():
        body += '<div class="row">'+badge((tr('ui_1625f6ba5f2c')) if d['status']=='approved' else (tr('ui_8970039135ad')),'good' if d['status']=='approved' else 'warn')+'<p class="body-text">'+e(d['text'])+'</p><div class="meta">'+e(d['binding']['worker_id'])+' · r'+e(d['binding']['context_revision'])+'</div><div class="path">'+e(did)+'</div></div>'
    if not decisions: body += ('<p class="muted">' + tr('ui_c32e0df042d2') + '</p>')
    memory_html = body+'</div></div></section>'
    body = ('<section id="connections"><div class="section-head"><h2>' + tr('ui_2f7028ef99b4') + '</h2>')+badge('Streamable HTTP')+('</div><div class="panel"><div class="connection"><div><h3>' + tr('ui_d4dd2e2eb27e') + '</h3><code>/mcp</code><div class="muted">' + tr('ui_591c000dcf5f') + '</div></div>')+badge((tr('ui_2cac3c472320')),'good')+('</div><div class="alert">' + tr('ui_d1bcde2190d4') + '</div>')
    seen = {row['worker_id']: row['at'] for row in audit}
    displayed = set()
    for principal in principals:
        if selected not in principal.projects or principal.worker_id in displayed: continue
        displayed.add(principal.worker_id)
        body += '<div class="row connection"><div><span class="dot"></span><strong>'+e(principal.worker_id)+('</strong><div class="meta">' + tr('ui_5db2971a333c'))+e(principal.role)+(tr('ui_09b8215cdaf3') + '</div></div><div class="meta">')+((tr('ui_7ba95c431b47'))+e(stamp(seen[principal.worker_id])) if principal.worker_id in seen else (tr('ui_b99c99f4a453')))+'</div></div>'
    if not displayed: body += ('<p class="muted">' + tr('ui_3340cee124e7') + '</p>')
    body += ('<details><summary>' + tr('ui_718d16928861') + '</summary><ol><li>' + tr('ui_ad2d5508c1da') + '</li><li>' + tr('ui_236c21f688ed') + '</li><li>' + tr('ui_3d7c5c7443f9') + '</li><li>' + tr('ui_e38eb8083547') + '</li></ol><p><a href="/help#clients">' + tr('ui_89c83731a4e8') + '</a></p></details></div></section>')
    connections_html = body
    body = ('<section id="audit"><div class="section-head"><h2>' + tr('ui_69d2456eb923') + '</h2>')+badge((tr('ui_bb03c0b803aa')))+'</div><div class="panel">'
    for row in reversed(audit[-30:]):
        body += '<div class="row"><div class="row-title"><strong>'+e(row['operation'])+'</strong><small>'+e(stamp(row['at']))+'</small></div><div class="meta">#'+e(row['sequence'])+' · '+e(row['worker_id'])+' · '+e(row.get('task_id') or (tr('ui_d5f8860a9c4f')))+' · r'+e(row['context_revision'])+'</div></div>'
    if not audit: body += ('<p class="muted">' + tr('ui_fa39cd080774') + '</p>')
    audit_html = body+'</div></section>'
    content = {'overview':overview+('<details class="overview-activity"><summary>' + tr('ui_d4c5a340b27b') + '</summary>')+audit_html+'</details>', 'tasks':tasks_html, 'memory':memory_html, 'connections':connections_html}[view]
    return workspace_shell(section_name(view),content,selected,config,identity,csrf,view,choices=states)



def install_web(app, hub, config=None, clock=time.time):
    from .i18n import install_language
    install_language(app)
    config = config or WebConfig.from_env() or WebConfig.policy_from_env()
    from .web_auth import WebAuthStore
    auth=WebAuthStore(hub.store, config, clock)
    def session(request):
        return auth.session(request.cookies.get(COOKIE,'')) if auth.enabled else None
    app.state.web_auth = auth
    app.state.web_session = session
    def redirect(path):
        return RedirectResponse(path, status_code=303, headers={'Cache-Control':'no-store'})
    def login_form(message='', status=200, return_to='/ui/chat'):
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        if not auth.start_login(token,csrf,safe_chat_return(return_to)):
            return page(('<main><h1>' + tr('ui_b9131bbe4b2a') + '</h1><p>' + tr('ui_da04f5a9c47c') + '</p></main>'),503)
        response = page(('<div class="login"><div class="brand">ys-aimemory<small>PROJECT MEMORY / MCP</small></div><div class="panel"><span class="eyebrow">WELCOME BACK</span><h1>' + tr('ui_edddb8024b8e') + '</h1><p class="muted">' + tr('ui_3748eca7a2c5') + '</p>')+('<div class="alert" role="alert">'+e(message)+'</div>' if message else '')+'<form method="post" action="/login"><input type="hidden" name="csrf" value="'+e(csrf)+('"><label for="username">' + tr('ui_107ab4b575a7') + '</label><input id="username" name="username" autocomplete="username" maxlength="128" required><label for="password">' + tr('ui_ef8b49458c14') + '</label><input id="password" name="password" type="password" autocomplete="current-password" maxlength="1024" required><button type="submit">' + tr('ui_c52651f85eb3') + '</button></form></div><p class="foot">' + tr('ui_9f24df40e911') + '<br>' + tr('ui_8e10a90fe1bc') + '</p></div>'),status)
        response.set_cookie(LOGIN_COOKIE,token,httponly=True,secure=config.secure,samesite='strict',max_age=600,path='/')
        return response
    async def form(request, max_bytes=8192, max_fields=5):
        if request.headers.get('content-type','').split(';')[0] != 'application/x-www-form-urlencoded': return {}
        data = bytearray()
        async for chunk in request.stream():
            data.extend(chunk)
            if len(data)>max_bytes: return {}
        try:
            values=parse_qs(data.decode('utf-8'),max_num_fields=max_fields)
            return {k:v[0] for k,v in values.items() if len(v)==1}
        except (ValueError,UnicodeDecodeError): return {}

    @app.get('/')
    def root(): return redirect('/ui/chat')

    @app.get('/login')
    def login_get(request: Request):
        if not auth.enabled: return page(('<main><h1>' + tr('ui_bdc16457fa28') + '</h1><p>' + tr('ui_737f338f13f8') + '</p></main>'),503)
        return_to = safe_chat_return(request.query_params.get('return_to', '/ui/chat'))
        if session(request): return redirect(return_to)
        return login_form(return_to=return_to)

    @app.post('/login')
    async def login_post(request: Request):
        if not auth.enabled: return page(('<main>' + tr('ui_bdc16457fa28') + '</main>'),503)
        values=await form(request,max_bytes=16384)
        pre=auth.consume_login(request.cookies.get(LOGIN_COOKIE,''))
        if not pre or not hmac.compare_digest(values.get('csrf','').encode(),pre['csrf'].encode()):
            return login_form((tr('ui_0e2f411d7412')),403)
        return_to = safe_chat_return(pre.get('return_to', '/ui/chat'))
        ip=request.client.host if request.client else 'unknown'
        if not auth.allow_attempt(ip):
            response=login_form((tr('ui_deb482bd764c')),429,return_to)
            response.headers['Retry-After']='300'
            return response
        identity = await run_in_threadpool(auth.users.authenticate, values.get('username',''), values.get('password',''))
        if identity is None: return login_form((tr('ui_35ddab0fb11b')),401,return_to)
        token,csrf=secrets.token_urlsafe(32),secrets.token_urlsafe(32)
        if not auth.start_session(token,csrf,request.cookies.get(COOKIE,''),identity):
            return page(('<main>' + tr('ui_1cff9523a11f') + '</main>'),503)
        response=redirect(return_to)
        response.set_cookie(COOKIE,token,httponly=True,secure=config.secure,samesite='strict',max_age=config.ttl,path='/')
        response.delete_cookie(LOGIN_COOKIE,path='/',secure=config.secure,httponly=True,samesite='strict')
        return response

    @app.post('/logout')
    async def logout(request: Request):
        current=session(request)
        values=await form(request)
        if not current or not hmac.compare_digest(values.get('csrf','').encode(),current['csrf'].encode()): return page(('<main>' + tr('ui_9c51b5da6d43') + '</main>'),403)
        auth.logout(request.cookies.get(COOKIE,''))
        response=redirect('/login')
        response.delete_cookie(COOKIE,path='/',secure=config.secure,httponly=True,samesite='strict')
        return response

    @app.get('/ui')
    def dashboard(request: Request):
        current=session(request)
        if not current: return redirect('/login')
        identity=auth.principal(current)
        if identity is None: return redirect('/login')
        scope=identity.projects
        view=request.query_params.get('view','overview')
        if view not in ('overview','tasks','memory','connections'): return page(('<main>' + tr('ui_ff87476d2ead') + '</main>'),404)
        with hub.store.engine.connect() as conn:
            states={row.id:row.state for row in conn.execute(select(projects).where(projects.c.id.in_(scope))).all()}
            selected=request.query_params.get('project') or next(iter(sorted(states)), '')
            if selected and selected not in states: return page(('<main><h1>' + tr('ui_a921ca11e333') + '</h1><a href="/ui">' + tr('ui_34c6fb9e6b18') + '</a></main>'),404)
            records=conn.execute(select(events.c.sequence,events.c.event).where(events.c.project_id==selected).order_by(events.c.sequence.desc()).limit(200)).all()
            audit=[{'sequence':row.sequence,**row.event} for row in reversed(records)]
        task_after=request.query_params.get('after','')
        if len(task_after)>128: return page(('<main>' + tr('ui_0896e2f444ee') + '</main>'),400)
        output=render_dashboard(config,selected,states,audit,hub.principals,current['csrf'],clock(),identity=identity,view=view,task_after=task_after)
        return page(output)

    from .web_management import install_management
    install_management(app, hub, config, session, form, redirect, auth, clock)
    from .web_mcp import install_mcp_management
    install_mcp_management(app, hub, config, session, form, redirect, auth, clock)
    from .web_accounts import install_accounts
    install_accounts(app, auth, session, form, redirect)
    return auth
