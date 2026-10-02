"""Administrator onboarding: scoped libraries and one-time worker credentials."""
import hmac
import json
import secrets
from urllib.parse import urlencode

from fastapi import Request
from sqlalchemy.exc import SQLAlchemyError

from .store import HubError
from .web import e, page, stamp
from .web_management import hidden, input_field, shell


# Static, trusted script only. Secrets stay in the current document; there is no
# storage, network request, URL parameter or server-side download/session cache.
COPY_SCRIPT = '''document.addEventListener('click', async event => {
  const button = event.target.closest('button[data-copy],button[data-download]');
  if (!button) return;
  const source = document.getElementById(button.dataset.copy || button.dataset.download);
  const status = document.getElementById('copy-status');
  if (button.dataset.copy) {
    try { await navigator.clipboard.writeText(source.value); status.textContent = '已複製，請妥善保管。'; }
    catch { source.focus(); source.select(); status.textContent = '請按 Ctrl+C 複製選取內容。'; }
  } else {
    const url = URL.createObjectURL(new Blob([source.value], {type:'text/plain;charset=utf-8'}));
    const a = document.createElement('a'); a.href = url; a.download = button.dataset.filename;
    a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
    status.textContent = '設定檔已下載，內容不包含 Token。';
  }
});'''


def templates(base_url):
    endpoint = base_url + '/mcp'
    return [
        ('codex', 'Codex：合併至 .codex/config.toml', 'ys-memory-codex.toml',
         '[mcp_servers.ys_memory]\nurl = ' + json.dumps(endpoint) + '\nbearer_token_env_var = "YS_AIMEMORY_TOKEN"\nenabled = true\n'),
        ('claude', 'Claude Code：合併至專案 .mcp.json', 'ys-memory-claude-code.json',
         json.dumps({'mcpServers': {'ys_memory': {'type': 'http', 'url': endpoint,
                    'headers': {'Authorization': 'Bearer ${YS_AIMEMORY_TOKEN}'}}}}, ensure_ascii=False, indent=2) + '\n'),
    ]


def config_cards(base_url):
    body = '<h2>客戶端設定</h2><p>下載的是設定範本，不含 Token。合併既有設定，勿直接覆蓋其他 MCP。每個 AI 請使用自己的 Token。</p>'
    for name, title, filename, content in templates(base_url):
        field = 'config-' + name
        body += '<section class="panel task"><label for="'+field+'">'+e(title)+'</label><textarea id="'+field+'" readonly rows="8" spellcheck="false">'+e(content)+'</textarea><p><button type="button" data-copy="'+field+'">複製設定</button> <button type="button" data-download="'+field+'" data-filename="'+filename+'">下載設定</button></p></section>'
    from .client_bundle import BUNDLE_ROUTE
    setup = 'py -3.12 -m venv .venv\n.\\.venv\\Scripts\\python.exe -m pip install -r requirements.lock\n.\\.venv\\Scripts\\python.exe .\\bridge.py --compact --print-claude-config'
    body += '<section class="panel task"><h3>Claude Code：stdio HTTPS adapter</h3><p>若直接 HTTP 出現 <code>UNSUPPORTED_CONSTRAINT_TYPE</code>，可使用 Python 嚴格 TLS adapter。它不處理模型登入、OAuth 過期或客戶端工具核准。</p><p><a class="button" href="'+e(base_url+BUNDLE_ROUTE)+'">下載 stdio 套件 1.1.0（不含 Token）</a></p><p>先核對公開 CA 指紋，將套件解壓至自選的新目錄，在該目錄的 PowerShell 執行：</p><pre class="path"><code>'+e(setup)+'</code></pre><p>最後一行不需 Token、不連線、不寫檔；它輸出這個目錄的完整路徑。將輸出的 ys_memory 設定合併至專案 .mcp.json，保留其他 MCP。套件移動後須重新產生路徑。接著切換到該專案目錄，將自己的 Token 提供給同一程序的 YS_AIMEMORY_TOKEN，再啟動 Claude；compact 初始只提供兩個工具，實際呼叫才連 Hub；Connected 僅代表本機就緒，不代表模型對話已通過。</p></section>'
    body += '<p>將 Token 安全提供至啟動客戶端的 <code>YS_AIMEMORY_TOKEN</code> 環境變數。直接 HTTP 設定的私有 CA 另以 <code>CODEX_CA_CERTIFICATE</code>（Codex）或 <code>NODE_EXTRA_CA_CERTS</code>（Claude Code）指向下載的 PEM 憑證；重新啟動客戶端才會套用。stdio adapter 使用套件內經指紋核對的 CA，不需要 Node CA 環境變數。</p><p><a href="/help#clients">完整設定與測試步驟 →</a></p><p id="copy-status" role="status" aria-live="polite"></p>'
    return body


def install_mcp_management(app, hub, config, session, parse_form, redirect, auth, clock):
    def guard(request):
        current = session(request)
        if not current:
            return None
        identity = auth.principal(current)
        if identity is None: return None
        if identity.role != 'admin' or not config.mcp_enabled:
            raise HubError('forbidden', 'MCP 產生器僅供已啟用此功能的管理員使用。', 403)
        return current

    def scoped(project, current):
        identity = auth.principal(current)
        if identity is None or project not in identity.projects:
            raise HubError('forbidden', '此記憶庫不在網頁帳號授權範圍。', 403)

    def start(action, current, project='', extra=None):
        nonce = secrets.token_urlsafe(24)
        auth.start_nonce(nonce, current, 'mcp-' + action, project)
        return '<form method="post" action="/ui/mcp/'+action+'">'+hidden('csrf',current['csrf'])+hidden('nonce',nonce)+hidden('project_id',project)+''.join(hidden(k,v) for k,v in (extra or {}).items())

    def error(exc):
        return page(shell('MCP 請求未完成', '<p class="alert">'+e(exc.message)+'</p><a href="/ui/mcp">返回產生器</a>'), exc.status)

    def unavailable():
        return error(HubError('unavailable', '資料庫暫時無法使用，請稍後重新載入。', 503))

    @app.get('/ui/mcp')
    def overview(request: Request):
        try:
            current = guard(request)
            if current is None:
                return redirect('/login')
            from .web_help import public_base_url
            identity = auth.principal(current)
            if identity is None: return redirect('/login')
            scope = identity.projects
            project = request.query_params.get('project') or next(iter(scope), '')
            if project: scoped(project, current)
            body = '<p>一個記憶庫對應一個專案 ID；每個 AI 使用獨立 worker 與 Token。新增 Token 的角色固定為 worker，不會取得管理員權限。</p><p><a href="/help">操作教學</a> · <a href="/downloads/ys-ai-memory-ca.crt">下載公開 CA 憑證</a></p>'
            body += '<section class="panel task"><h2>1. 建立記憶庫</h2><p>使用英文字母、數字、點、底線或連字號。已存在的記憶庫不能被重新認領。</p>'+start('project', current)+input_field('new_project_id','新記憶庫 ID')+'<p><button>建立記憶庫</button></p></form></section>'
            if project:
                body += '<form method="get"><label for="project">目前記憶庫</label><select id="project" name="project">'+''.join('<option'+(' selected' if p == project else '')+'>'+e(p)+'</option>' for p in scope)+'</select><p><button>切換記憶庫</button></p></form>'
                body += '<section class="panel task"><h2>2. 產生 MCP Token</h2>'+start('issue',current,project)+input_field('worker_id','AI 身分 ID（例如 claude-design 或 codex-api）')+'<p>身分 ID 不可重用。Token 只顯示一次；遺失時請重新產生。</p><p><button>產生專屬 Token</button></p></form></section><h2>已建立的連線身分</h2>'
            else:
                body += '<p>目前沒有授權專案。可先建立新的記憶庫，或請使用者管理員授予專案範圍。</p>'
            records = hub.credentials.list_credentials([project]) if project else []
            for row in records:
                body += '<section class="panel task"><h3>'+e(row['worker_id'])+'</h3><p>記憶庫 '+e(row['project_id'])+' · worker · '+('已撤銷' if row['revoked_at'] is not None else '有效')+'</p><p class="muted">建立於 '+e(stamp(row['created_at']))+' · 版本 '+e(row['version'])+'</p>'
                if row['revoked_at'] is None:
                    extra = {'token_id':row['token_id'],'expected_version':row['version']}
                    body += '<p>重新產生會立即使舊 Token 失效。撤銷後無法恢復；尚未完成的任務需由管理頁另行復原。</p>'+start('rotate',current,project,extra)+'<p><button>重新產生 Token</button></p></form>'+start('revoke',current,project,extra)+'<p><button>撤銷此 Token</button></p></form>'
                body += '</section>'
            if project and not records:
                body += '<p class="muted">此記憶庫尚未從產生器建立 Token。</p>'
            body += '<p class="muted">環境配置中的既有身分由伺服器管理員維護，不會在此顯示 Token。關閉產生器不會撤銷已簽發的 Token。</p>'+config_cards(public_base_url())
            return page(shell('MCP 產生器',body,project,'admin'), script=COPY_SCRIPT)
        except HubError as exc:
            return error(exc)
        except SQLAlchemyError:
            return unavailable()

    @app.post('/ui/mcp/{action}')
    async def mutate(action: str, request: Request):
        try:
            current = guard(request)
            if current is None:
                return redirect('/login')
            if action not in ('project','issue','rotate','revoke'):
                raise HubError('not_found','未知的 MCP 管理動作。',404)
            values = await parse_form(request, max_bytes=8192, max_fields=8)
            project = values.get('project_id','')
            if action != 'project':
                scoped(project, current)
            elif project:
                raise HubError('invalid_project','建立表單不接受既有記憶庫範圍。',400)
            if not hmac.compare_digest(values.get('csrf','').encode(),current['csrf'].encode()):
                raise HubError('csrf','表單驗證失敗，請重新載入。',403)
            if not auth.consume_nonce(values.get('nonce',''),current,'mcp-'+action,project):
                raise HubError('duplicate_or_expired','此表單已使用或過期；Token 不會再次顯示。請重新載入。',409)
            from .web_help import public_base_url
            # Resolve configuration before mutation so malformed deployment config
            # cannot mint a token and then fail while rendering its only response.
            base = public_base_url()
            registry = hub.credentials
            identity = auth.principal(current)
            if identity is None: return redirect('/login')
            if identity.role != 'admin': raise HubError('forbidden', '此帳號沒有專案管理權限。', 403)
            if action == 'project':
                project = values.get('new_project_id','')
                auth.users.create_project(current,project,registry)
                return redirect('/ui/mcp?'+urlencode({'project':project}))
            if action == 'issue':
                issued = registry.issue(project,values.get('worker_id',''),'human:' + identity.user_id,clock())
            else:
                version = int(values.get('expected_version',''))
                args = (project,values.get('token_id',''),version,'human:' + identity.user_id,clock())
                if action == 'revoke':
                    registry.revoke(*args)
                    return redirect('/ui/mcp?'+urlencode({'project':project}))
                issued = registry.rotate(*args)
            body = '<div class="alert">Token 僅在本次回應顯示。請立即複製到安全的秘密儲存位置；勿貼入聊天、Git、網址或截圖。遺失時請重新產生。</div><p>記憶庫 <strong>'+e(issued['project_id'])+'</strong> · AI 身分 <strong>'+e(issued['worker_id'])+'</strong> · worker</p><label for="issued-token">專屬 Token</label><textarea id="issued-token" readonly rows="3" spellcheck="false" autocomplete="off">'+e(issued['token'])+'</textarea><p><button type="button" data-copy="issued-token">複製 Token</button></p>'+config_cards(base)+'<p><a href="/ui/mcp?'+e(urlencode({'project':project}))+'">已保存 Token，返回連線身分清單</a></p>'
            return page(shell('已產生 MCP Token',body,project,'admin'), script=COPY_SCRIPT)
        except HubError as exc:
            return error(exc)
        except (ValueError, TypeError):
            return error(HubError('invalid_form','表單格式或服務網址設定不正確，請重新確認。',400))
        except SQLAlchemyError:
            return unavailable()
