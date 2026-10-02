"""Role-scoped human dashboard and management. Browser sessions never become MCP credentials.

Opaque sessions, login throttles and one-use forms are persisted in the database
and shared by application workers. Configuration changes invalidate sessions.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
from html import escape
import hmac
import os
import secrets
import time
from uuid import UUID
from urllib.parse import parse_qs

from fastapi import Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from .store import projects, events
from .web_password import valid_hash, verify_password

COOKIE = 'hub_web_session'
LOGIN_COOKIE = 'hub_web_login'

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

    def project_scope(self, hub):
        owned = hub.credentials.owned_projects(self.owner_id) if self.mcp_enabled and self.role == 'admin' else ()
        return tuple(dict.fromkeys((*self.projects, *owned)))

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


def e(value):
    return escape(str(value), quote=True)


def stamp(value):
    return datetime.fromtimestamp(value, timezone.utc).strftime('%m/%d %H:%M UTC') if value else '尚無紀錄'

CSS = '''
.manual nav{display:flex;flex-wrap:wrap;gap:6px 14px;margin:24px 0}.manual section.panel{margin:20px 0;scroll-margin-top:20px}.manual pre{white-space:pre-wrap;overflow-wrap:anywhere}.manual header>.button{flex-shrink:0;display:inline-block}.manual li+li{margin-top:8px}
.management{max-width:1100px;margin:auto}:root{color-scheme:dark;--bg:#0b1019;--panel:#141c29;--line:#283346;--muted:#91a1ba;--text:#e9eff8;--accent:#a4e6cf}*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:15px/1.7 system-ui,-apple-system,"Noto Sans TC",sans-serif}a{color:var(--accent);text-decoration:none}a:hover{text-decoration:underline}button,input,select,textarea{font:inherit}textarea{min-height:130px;resize:vertical}button,.button{border:0;background:var(--accent);color:#10231e;padding:10px 18px;border-radius:9px;cursor:pointer;font-weight:650}button:hover{filter:brightness(1.1)}button:focus-visible,a:focus-visible,summary:focus-visible{outline:3px solid #8bc4ff;outline-offset:3px}input,select,textarea{background:#0e1521;color:var(--text);border:1px solid #42506a;padding:11px 13px;border-radius:8px;width:100%}label{display:block;margin:16px 0 6px}.shell{max-width:1440px;margin:auto;display:grid;grid-template-columns:230px 1fr;min-height:100vh}aside{padding:30px 23px;border-right:1px solid var(--line)}.brand{font-size:21px;font-weight:750;letter-spacing:-.5px}.brand small{display:block;font-size:11px;letter-spacing:2px;color:var(--muted);margin-top:3px}nav{display:grid;gap:9px;margin:35px 0}nav a{padding:9px 12px;border-radius:8px;color:#c1cee1}nav a:hover{background:var(--panel)}.aside-note{font-size:12px;color:var(--muted);margin-top:30px}main{padding:34px 38px;min-width:0}header{display:flex;justify-content:space-between;align-items:center;gap:20px;margin-bottom:30px}h1{font-size:30px;line-height:1.3;margin:4px 0 9px;letter-spacing:-1px}h2{font-size:19px;margin:0}h3{font-size:16px;margin:0}.muted,small{color:var(--muted)}.eyebrow{color:var(--accent);font-size:11px;font-weight:750;letter-spacing:2px}.project-select{display:flex;gap:10px;max-width:350px}.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:15px;margin:24px 0}.stat,.panel{background:var(--panel);border:1px solid var(--line);border-radius:13px;padding:21px}.stat strong{display:block;font-size:30px;color:var(--text);line-height:1.4}.stat span{font-size:12px;color:var(--muted)}.section-head{display:flex;align-items:center;justify-content:space-between;gap:12px;margin:29px 0 13px}.badge{display:inline-block;background:#25354b;color:#c8d9f2;border:1px solid #394b66;border-radius:20px;font-size:11px;padding:2px 9px;white-space:nowrap}.badge.good{background:#183a31;border-color:#2d5749;color:#ade6cd}.badge.warn{background:#44381f;border-color:#68552d;color:#f2d79e}.grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}.task{margin-bottom:12px}.task-head{display:flex;justify-content:space-between;gap:12px}.task p{margin:12px 0}.meta{display:flex;flex-wrap:wrap;gap:8px 18px;font-size:12px;color:var(--muted)}.path,code{font:12px/1.6 ui-monospace,SFMono-Regular,monospace;overflow-wrap:anywhere;color:#b5cce8}.empty{padding:25px;text-align:center;color:var(--muted);border:1px dashed #39465b;border-radius:12px}.empty strong{display:block;color:var(--text);font-size:15px}.row{padding:15px 0;border-bottom:1px solid var(--line)}.row:last-child{border:0}.row-title{display:flex;gap:12px;justify-content:space-between;align-items:center}.body-text{white-space:pre-wrap;overflow-wrap:anywhere;font-size:13px;color:#c1cee1}summary{cursor:pointer;color:var(--accent);font-size:12px;margin-top:12px}.connection{display:flex;align-items:center;justify-content:space-between;gap:15px}.dot{display:inline-block;width:8px;height:8px;border-radius:50%;background:#8badbd;margin-right:8px}.alert{background:#392b20;border:1px solid #675039;color:#ecccaa;padding:12px 16px;border-radius:9px;margin:15px 0;font-size:13px}.login{max-width:440px;margin:10vh auto;padding:0 22px}.login .panel{margin-top:26px;padding:30px}.login button{width:100%;margin-top:23px}.login h1{font-size:27px}.topline{display:flex;justify-content:space-between;gap:12px}.logout button{background:transparent;border:1px solid var(--line);color:var(--muted);font-size:12px;padding:6px 12px}.timeline{border-left:2px solid #33455d;padding-left:17px;margin:16px 0 0 7px}.timeline p{font-size:12px;margin:7px 0}.foot{margin:35px 0;font-size:12px;color:var(--muted)}@media(max-width:1000px){.shell{grid-template-columns:190px 1fr}main{padding:26px 22px}.grid{grid-template-columns:1fr}.stats{grid-template-columns:1fr 1fr}}@media(max-width:640px){.shell{display:block}aside{padding:18px 20px;border-right:0;border-bottom:1px solid var(--line)}aside nav{display:flex;overflow:auto;margin:14px 0 0;gap:3px}nav a{white-space:nowrap;padding:6px 10px}.aside-note{display:none}main{padding:23px 16px}header{display:block}h1{font-size:25px}.project-select{margin-top:18px;max-width:none}.panel{padding:17px}.stats{gap:9px}.stat{padding:15px}.task-head{display:block}.task-head .badge{margin-top:8px}}
'''


def page(body, status=200, script=''):
    nonce = secrets.token_urlsafe(18)
    extra = '<script nonce="'+nonce+'">'+script+'</script>' if script else ''
    script_policy = f"; script-src 'nonce-{nonce}'" if script else ''
    return HTMLResponse('<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>ys · 專案記憶中樞</title><style nonce="'+nonce+'">'+CSS+'</style></head><body>'+body+extra+'</body></html>', status_code=status, headers={'Cache-Control':'no-store', 'Pragma':'no-cache', 'X-Content-Type-Options':'nosniff', 'X-Frame-Options':'DENY', 'Referrer-Policy':'no-referrer', 'Content-Security-Policy':f"default-src 'none'; style-src 'nonce-{nonce}'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'"+script_policy})


def badge(text, kind=''):
    return '<span class="badge '+kind+'">'+e(text)+'</span>'


def empty(title, detail):
    return '<div class="empty"><strong>'+e(title)+'</strong>'+e(detail)+'</div>'


def render_handoff(record):
    """Render preserved handoff evidence without treating it as trusted HTML."""
    result = '<div class="panel"><h3>交接給 '+e(record.get('to_worker', '—'))+'</h3>'
    result += '<p class="body-text">'+e(record.get('summary', ''))+'</p>'
    result += '<div class="path">成果 commit：'+e(record.get('result_commit', '未提供'))+'</div>'
    for title, key in [('變更檔案／成果', 'changed_artifacts'), ('阻礙', 'blockers'), ('接手後下一步', 'next_steps')]:
        values = record.get(key, [])
        result += '<h4>'+title+'</h4>'
        result += '<ul>'+''.join('<li class="body-text">'+e(item)+'</li>' for item in values)+'</ul>' if values else '<p class="muted">未列項目</p>'
    result += '<h4>測試證據（由交接者回報）</h4>'
    for test in record.get('test_results', []):
        status = test.get('status', 'not_run')
        label = {'passed':'通過', 'failed':'失敗', 'not_run':'未執行'}.get(status, '未知')
        result += '<div class="row">'+badge(label, 'good' if status == 'passed' else 'warn')+'<div class="path">'+e(test.get('command', ''))+'</div><div class="body-text">'+e(test.get('details', ''))+'</div></div>'
    result += '<p class="muted">Hub 保存交接者提供的證據；接手者仍需自行驗證。</p></div>'
    return result


def render_recovery(record):
    target = record.get('to_worker') or '解除指定，可重新認領'
    return ('<div class="row"><h4>管理員重新分派</h4><div class="meta">'
            +e(record.get('recovered_by', ''))+' · '+e(stamp(record.get('at')))
            +' · Fence '+e(record.get('fence', ''))+'</div><div class="body-text">'
            +e(record.get('reason', ''))+'</div><div class="meta">接手者：'
            +e(target)+'</div><p class="muted">先前租約與脈絡包已失效，接手需重新取得脈絡並確認。</p></div>')


def render_dashboard(config, selected, states, audit, principals, csrf, now):
    state = states.get(selected, {})
    tasks = state.get('tasks', {})
    sources = state.get('sources', {})
    decisions = state.get('decisions', {})
    active = sum(bool(t.get('owner') and t.get('lease_until', 0) > now) for t in tasks.values())
    pending = sum(bool(t.get('pending_recipient')) for t in tasks.values())
    options = ''.join('<option value="'+e(p)+'"'+(' selected' if p == selected else '')+'>'+e(p)+'</option>' for p in sorted(states))
    body = '''<div class="shell"><aside><div class="brand">ys-aimemory<small>PROJECT MEMORY / MCP</small></div><nav><a href="#overview">◈ 專案總覽</a><a href="#tasks">▦ 任務與交接</a><a href="#memory">▤ 來源與記憶</a><a href="#connections">↗ MCP 連線</a><a href="#audit">◷ 活動紀錄</a></nav><div class="aside-note">共同記憶，明確交接<br>每次認領、閱讀與驗證都有依據<br><br>此介面僅供檢視<br>寫入需經授權 API / MCP</div></aside><main id="overview"><div class="topline"><span class="eyebrow">YOUR PROJECT, IN CONTEXT</span><form class="logout" action="/logout" method="post"><input type="hidden" name="csrf" value="'''+e(csrf)+'''"><button type="submit">登出</button></form></div><header><div><h1>專案記憶中樞</h1><div class="muted">一眼掌握進度、脈絡與下一位接手者</div></div>'''
    if options:
        body += '<form class="project-select" method="get" action="/ui"><select name="project" aria-label="選擇專案">'+options+'</select><button>切換</button></form>'
    body += '</header>'
    if not config.secure:
        body += '<div class="alert">目前停用 Secure Cookie，僅限隔離本機 HTTP 測試。LAN 與公開環境請使用 HTTPS。</div>'
    body += '<div class="stats">'+''.join('<div class="stat"><span>'+label+'</span><strong>'+e(value)+'</strong></div>' for label,value in [('脈絡版本', 'r'+str(state.get('revision',0))),('進行中認領',active),('等待接手',pending),('已登錄來源',len(sources))])+'</div>'
    if not states:
        body += empty('尚未建立可讀取的專案', '管理員透過 API / MCP 建立專案後，重新整理即可查看。')
    body += '<section id="tasks"><div class="section-head"><h2>任務與交接</h2>'+badge(str(len(tasks))+' 個任務')+'</div>'
    for task_id,t in tasks.items():
        live = bool(t.get('owner') and t.get('lease_until',0) > now)
        accepted_packet = state.get('packets', {}).get((t.get('accepted') or {}).get('packet_id'), {})
        accepted_current = bool(live and accepted_packet and accepted_packet.get('context_revision') == state.get('revision') and accepted_packet.get('task_generation') == t.get('generation') and (t.get('accepted') or {}).get('fence') == t.get('fence'))
        status = '已完成' if t['status'] == 'completed' else ('等待 '+str(t['pending_recipient'])+' 接手' if t.get('pending_recipient') else ('認領有效' if live else '等待認領'))
        body += '<article class="panel task"><div class="task-head"><h3>'+e(task_id)+'</h3>'+badge(status, 'good' if live or t['status']=='completed' else 'warn')+'</div><p>'+e(t['goal'])+'</p><div class="meta"><span>持有者 '+e(t.get('owner') or '—')+'</span><span>Fence '+e(t.get('fence',0))+'</span><span>租約 '+e(stamp(t.get('lease_until')))+'</span><span>接手確認 '+('已接受目前脈絡' if accepted_current else '尚未接受／需重新驗證')+'</span></div><details><summary>範圍、驗收與檢查點</summary><p class="path">'+e(' · '.join(t.get('allowed_paths',[])))+'</p><ul>'+''.join('<li>'+e(x)+'</li>' for x in t.get('acceptance_criteria',[]))+'</ul>'
        packets = [v for v in state.get('packets', {}).values() if v.get('task_id') == task_id]
        for packet in sorted(packets, key=lambda x:x.get('prepared_at',0), reverse=True)[:8]:
            fresh = packet.get('context_revision') == state.get('revision') and packet.get('task_generation') == t.get('generation')
            body += '<div class="row"><div class="meta">脈絡包 · '+e(packet['worker_id'])+' · r'+e(packet['context_revision'])+' · '+('目前版本' if fresh else '已過期')+' · '+('已確認閱讀' if packet.get('acknowledged') else '待閱讀確認')+'</div><div class="path">'+e(packet['workspace'])+'<br>'+e(packet['branch'])+' @ '+e(packet['commit'])+'</div></div>'
        for cp in t.get('checkpoints',[]):
            body += '<div class="row"><div class="meta">'+e(cp['binding']['worker_id'])+' · '+e(cp['kind'])+' · '+e(stamp(cp['at']))+'</div><div class="body-text">'+e(cp['summary'])+'</div><div class="path">'+e(cp['binding']['branch'])+' @ '+e(cp['binding']['commit'])+'</div></div>'
        if not t.get('checkpoints'):
            body += '<p class="muted">尚無檢查點或交接紀錄</p>'
        for handoff in t.get('handoffs', []):
            body += render_handoff(handoff)
        for recovery in t.get('recoveries', []):
            body += render_recovery(recovery)
        body += '</details></article>'
    if not tasks:
        body += empty('目前沒有任務', '透過授權的管理員 API 建立任務與必要來源。')
    body += '</section><section id="memory"><div class="section-head"><h2>來源與記憶</h2>'+badge('保留來源版本')+'</div><div class="grid"><div class="panel"><h3>可追溯來源</h3>'
    for sid,source in sources.items():
        current = source['current']
        body += '<div class="row"><div class="row-title"><strong>'+e(sid)+'</strong>'+badge(str(len(source['versions']))+' 版')+'</div><div class="path">'+e(current['uri'])+'<br>commit '+e(current['commit'])+'<br>SHA-256 '+e(current['sha256'])+'</div><details><summary>查看來源內容（未信任參考資料）</summary><div class="body-text">'+e(current['content'])+'</div></details></div>'
    if not sources: body += '<p class="muted">尚無來源。登錄後將顯示內容、commit 與雜湊。</p>'
    body += '</div><div class="panel"><h3>決策與待審提案</h3>'
    for did,d in decisions.items():
        body += '<div class="row">'+badge('已核准' if d['status']=='approved' else '待審・非權威記憶','good' if d['status']=='approved' else 'warn')+'<p class="body-text">'+e(d['text'])+'</p><div class="meta">'+e(d['binding']['worker_id'])+' · r'+e(d['binding']['context_revision'])+'</div><div class="path">'+e(did)+'</div></div>'
    if not decisions: body += '<p class="muted">尚無決策或提案。待審提案不會自動成為核准記憶。</p>'
    body += '</div></div></section><section id="connections"><div class="section-head"><h2>MCP 連線</h2>'+badge('Streamable HTTP')+'</div><div class="panel"><div class="connection"><div><h3>共用服務端點</h3><code>/mcp</code><div class="muted">使用此網站的 HTTPS 網址 + /mcp；每個 AI 使用獨立 bearer 身分</div></div>'+badge('已掛載','good')+'</div><div class="alert">設定身分 ≠ 已連線。以下活動由 Hub 審計紀錄推導，不代表客戶端目前在線。登入 cookie 不能用於 MCP。</div>'
    seen = {row['worker_id']: row['at'] for row in audit}
    displayed = set()
    for principal in principals:
        if selected not in principal.projects or principal.worker_id in displayed: continue
        displayed.add(principal.worker_id)
        body += '<div class="row connection"><div><span class="dot"></span><strong>'+e(principal.worker_id)+'</strong><div class="meta">角色 '+e(principal.role)+' · 已設定目前專案權限</div></div><div class="meta">'+('最近活動 '+e(stamp(seen[principal.worker_id])) if principal.worker_id in seen else '尚未觀察到活動')+'</div></div>'
    if not displayed: body += '<p class="muted">此專案尚無可顯示的 AI 身分</p>'
    body += '<details><summary>連線與交接步驟</summary><ol><li>管理員在伺服器設定獨立、專案限定的 AI 身分</li><li>在客戶端加入 HTTPS MCP 端點，透過客戶端秘密設定傳入 Bearer token</li><li>先 get_worker_inbox 找到待接手任務，再 prepare → claim → read → acknowledge → accept → validate</li><li>工作完成記錄證據、檢查點與明確接手者</li></ol><p class="muted">不在此頁顯示或輸入 token；實際客戶端設定請見專案 docs/CLIENT_SETUP.zh-TW.md。</p></details></div></section>'
    body += '<section id="audit"><div class="section-head"><h2>最近活動</h2>'+badge('最多 200 筆')+'</div><div class="panel">'
    for row in reversed(audit[-30:]):
        body += '<div class="row"><div class="row-title"><strong>'+e(row['operation'])+'</strong><small>'+e(stamp(row['at']))+'</small></div><div class="meta">#'+e(row['sequence'])+' · '+e(row['worker_id'])+' · '+e(row.get('task_id') or '專案層級')+' · r'+e(row['context_revision'])+'</div></div>'
    if not audit: body += '<p class="muted">尚無活動紀錄</p>'
    body += '</div></section><p class="foot">唯讀檢視 · '+e(config.username)+' · '+e(stamp(now))+'<br>重新整理取得最新狀態；此頁不取代工作前的 validate_task_context。</p></main></div>'
    if config.role == 'admin':
        body=body.replace('此介面僅供檢視<br>寫入需經授權 API / MCP','管理員檢視<br>管理操作另有確認表單').replace('唯讀檢視 · ','管理員檢視 · ')
    return body


def install_web(app, hub, config=None, clock=time.time):
    config = config or WebConfig.from_env()
    from .web_auth import WebAuthStore
    auth=WebAuthStore(hub.store, config, clock)
    def session(request):
        return auth.session(request.cookies.get(COOKIE,'')) if config else None
    def redirect(path):
        return RedirectResponse(path, status_code=303, headers={'Cache-Control':'no-store'})
    def login_form(message='', status=200):
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        if not auth.start_login(token,csrf):
            return page('<main><h1>登入設定已更新</h1><p>此伺服器設定尚未同步，請管理員更新所有執行中的服務。</p></main>',503)
        response = page('<div class="login"><div class="brand">ys-aimemory<small>PROJECT MEMORY / MCP</small></div><div class="panel"><span class="eyebrow">WELCOME BACK</span><h1>登入專案記憶中樞</h1><p class="muted">檢視任務、來源與 AI 交接進度</p>'+('<div class="alert" role="alert">'+e(message)+'</div>' if message else '')+'<form method="post" action="/login"><input type="hidden" name="csrf" value="'+e(csrf)+'"><label for="username">使用者名稱</label><input id="username" name="username" autocomplete="username" maxlength="128" required><label for="password">密碼</label><input id="password" name="password" type="password" autocomplete="current-password" maxlength="1024" required><button type="submit">登入 →</button></form></div><p class="foot">僅接受管理員設定的帳號 · 不提供預設密碼<br>網頁權限由管理員設定，不會取得 AI 的 bearer token</p></div>',status)
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
    def root(): return redirect('/ui')

    @app.get('/login')
    def login_get(request: Request):
        if config is None: return page('<main><h1>網頁登入尚未啟用</h1><p>請管理員設定使用者名稱、密碼雜湊與專案範圍。</p></main>',503)
        if session(request): return redirect('/ui')
        return login_form()

    @app.post('/login')
    async def login_post(request: Request):
        if config is None: return page('<main>網頁登入尚未啟用</main>',503)
        values=await form(request)
        pre=auth.consume_login(request.cookies.get(LOGIN_COOKIE,''))
        if not pre or not hmac.compare_digest(values.get('csrf','').encode(),pre['csrf'].encode()):
            return login_form('登入頁已過期，請重新輸入。',403)
        ip=request.client.host if request.client else 'unknown'
        if not auth.allow_attempt(ip):
            response=login_form('登入嘗試過於頻繁，請五分鐘後再試。',429)
            response.headers['Retry-After']='300'
            return response
        # Always calculate the expensive hash, including for an unknown username.
        verified=verify_password(values.get('password',''),config.password_hash)
        correct_user=hmac.compare_digest(values.get('username','').encode(),config.username.encode())
        if not verified or not correct_user: return login_form('使用者名稱或密碼不正確。',401)
        token,csrf=secrets.token_urlsafe(32),secrets.token_urlsafe(32)
        if not auth.start_session(token,csrf,request.cookies.get(COOKIE,'')):
            return page('<main>登入設定已更新，請重新載入。</main>',503)
        response=redirect('/ui')
        response.set_cookie(COOKIE,token,httponly=True,secure=config.secure,samesite='strict',max_age=config.ttl,path='/')
        response.delete_cookie(LOGIN_COOKIE,path='/',secure=config.secure,httponly=True,samesite='strict')
        return response

    @app.post('/logout')
    async def logout(request: Request):
        current=session(request)
        values=await form(request)
        if not current or not hmac.compare_digest(values.get('csrf','').encode(),current['csrf'].encode()): return page('<main>無效的登出請求，請重新整理頁面。</main>',403)
        auth.logout(request.cookies.get(COOKIE,''))
        response=redirect('/login')
        response.delete_cookie(COOKIE,path='/',secure=config.secure,httponly=True,samesite='strict')
        return response

    @app.get('/ui')
    def dashboard(request: Request):
        current=session(request)
        if not current: return redirect('/login')
        scope=config.project_scope(hub)
        with hub.store.engine.connect() as conn:
            states={row.id:row.state for row in conn.execute(select(projects).where(projects.c.id.in_(scope))).all()}
            selected=request.query_params.get('project') or next(iter(sorted(states)), '')
            if selected and selected not in states: return page('<main><h1>找不到可讀取的專案</h1><a href="/ui">返回總覽</a></main>',404)
            records=conn.execute(select(events.c.sequence,events.c.event).where(events.c.project_id==selected).order_by(events.c.sequence.desc()).limit(200)).all()
            audit=[{'sequence':row.sequence,**row.event} for row in reversed(records)]
        output=render_dashboard(config,selected,states,audit,hub.principals,current['csrf'],clock())
        from urllib.parse import urlencode
        links='<div class="panel"><a href="/ui/manage?'+urlencode({'project':selected})+'">專案管理</a> · <a href="/ui/search?'+urlencode({'project':selected})+'">搜尋記憶</a> · <a href="/ui/inbox?'+urlencode({'project':selected})+'">任務收件匣</a></div>'
        links=links.replace('</div>', ' · <a href="/help">操作教學與 CA 下載</a>'+(' · <a href="/ui/mcp">MCP 產生器</a>' if config.mcp_enabled and config.role=='admin' else '')+'</div>')
        output=output.replace('<div class="stats">', links+'<div class="stats">',1)
        return page(output)

    from .web_management import install_management
    install_management(app, hub, config, session, form, redirect, auth, clock)
    from .web_mcp import install_mcp_management
    install_mcp_management(app, hub, config, session, form, redirect, auth, clock)
