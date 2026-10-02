"""Human account pages. Only explicit account managers can administer users."""
import hmac
import secrets
from urllib.parse import urlencode

from fastapi import Request
from sqlalchemy.exc import SQLAlchemyError
from starlette.concurrency import run_in_threadpool

from .store import HubError
from .web import e, page
from .web_management import hidden, input_field, shell


def install_accounts(app, auth, session, parse_form, redirect):
    def guard(request, manager=True):
        current = session(request)
        identity = auth.principal(current)
        if identity is None:
            return None, None
        if manager and not identity.can_manage_users:
            raise HubError('forbidden', '此帳號沒有使用者管理權限。', 403)
        return current, identity

    def selected_project(request, identity):
        value=request.query_params.get('project') or next(iter(identity.projects), '')
        if value and value not in identity.projects: raise HubError('not_found','找不到可讀取的專案。',404)
        return value

    def error(exc):
        if exc.status == 401:
            return redirect('/login')
        return page(shell('帳號請求未完成', '<p class="alert">' + e(exc.message) + '</p><p><a href="/ui">返回總覽</a></p>'), exc.status)

    def start(action, current, target='', version=0, project=''):
        nonce = secrets.token_urlsafe(24)
        resource = target + ':' + str(version)
        if not auth.start_nonce(nonce, current, 'users-' + action, resource):
            raise HubError('unauthorized', '登入已失效。', 401)
        route = '/ui/account/password' if action == 'self-password' else '/ui/users/' + action
        return '<form method="post" action="' + route + '">' + hidden('csrf', current['csrf']) + hidden('nonce', nonce) + hidden('target_id', target) + hidden('expected_version', version) + hidden('return_project', project)

    def password_field(name='password', label='新密碼（10–1024 字元）'):
        return '<label>' + e(label) + '<input type="password" name="' + e(name) + '" minlength="10" maxlength="1024" autocomplete="' + ('current-password' if name == 'current_password' else 'new-password') + '" required></label>'

    def permissions(row=None):
        row = row or {'role': 'read_only', 'projects': (), 'can_manage_users': False}
        roles = [('read_only', '唯讀'), ('member', '共享 Chat 成員'), ('admin', '專案管理員')]
        body = '<label>角色<select name="role">' + ''.join('<option value="' + key + '"' + (' selected' if row['role'] == key else '') + '>' + label + '</option>' for key, label in roles) + '</select></label>'
        body += input_field('projects', '專案範圍（逗號分隔；最多 100 項；可留空；不支援 *）', ','.join(row['projects']), required=False)
        body += '<label>管理使用者<select name="can_manage_users">' + ''.join('<option value="' + value + '"' + (' selected' if row['can_manage_users'] == (value == 'true') else '') + '>' + label + '</option>' for value, label in [('false', '不允許'), ('true', '允許管理所有帳號及其權限')]) + '</select></label>'
        return body

    @app.get('/ui/users')
    def users_page(request: Request):
        try:
            current, identity = guard(request)
            if identity is None:
                return redirect('/login')
            project = selected_project(request, identity)
            result = auth.users.list(current, request.query_params.get('after', ''))
            body = '<p class="alert">管理使用者可重設所有帳號密碼與授權專案。這項能力本身不授予專案資料可見性。帳號停用不會撤銷獨立的 AI Token；既有 private 訊息仍限參與者。</p>'
            body += '<section class="panel"><h2>新增帳號</h2>' + start('create', current, project=project) + input_field('username', '登入名稱') + input_field('display_name', '顯示名稱') + password_field() + permissions() + '<p><button>新增帳號</button></p></form></section><h2>帳號清單</h2>'
            for row in result['items']:
                body += '<p><a href="' + e('/ui/users?' + urlencode({'user_id': row['user_id'], 'project': selected_project(request,identity)})) + '">' + e(row['display_name']) + '（' + e(row['username']) + '）</a> · ' + ('已啟用' if row['enabled'] else '已停用') + ' · ' + e(row['role']) + '</p>'
            if result['next_after']:
                body += '<a href="' + e('/ui/users?' + urlencode({'after': result['next_after'], 'project': selected_project(request,identity)})) + '">下一頁 →</a>'
            selected = request.query_params.get('user_id', '')
            if selected:
                row = auth.users.get(current, selected)
                body += '<section class="panel"><h2>' + e(row['display_name']) + '</h2><p>登入名稱 ' + e(row['username']) + ' · 身份 ' + e(row['user_id']) + '</p><p>變更設定或密碼會使該帳號既有登入失效。身份不會刪除或重用。</p>'
                body += start('update', current, selected, row['version'], project) + input_field('display_name', '顯示名稱', row['display_name']) + permissions(row) + '<p><button>更新角色與範圍</button></p></form>'
                action = 'disable' if row['enabled'] else 'enable'
                body += start(action, current, selected, row['version'], project) + '<p><button>' + ('停用帳號' if row['enabled'] else '啟用帳號') + '</button></p></form>'
                body += start('password', current, selected, row['version'], project) + password_field() + '<p><button>重設密碼</button></p></form></section>'
            return page(shell('使用者管理',body,selected_project(request,identity),identity.role,config=auth.config,identity=identity,csrf=current['csrf'],section='settings',tab='users'))
        except HubError as exc:
            return error(exc)
        except SQLAlchemyError:
            return error(HubError('unavailable', '資料庫暫時無法使用。', 503))

    def verify(current, action, values):
        if not hmac.compare_digest(values.get('csrf', '').encode(), current['csrf'].encode()):
            raise HubError('csrf', '表單驗證失敗，請重新載入。', 403)
        try:
            version = int(values.get('expected_version', ''))
        except ValueError:
            raise HubError('invalid_account', '帳號版本格式不正確。', 400) from None
        target = values.get('target_id', '')
        if len(target) > 36 or version < 0:
            raise HubError('invalid_account', '帳號識別格式不正確。', 400)
        if not auth.consume_nonce(values.get('nonce', ''), current, 'users-' + action, target + ':' + str(version)):
            raise HubError('duplicate_or_expired', '表單已使用或過期，請重新載入。', 409)
        return target, version

    def parsed_permissions(values):
        manager = values.get('can_manage_users', 'false')
        if manager not in ('true', 'false'):
            raise HubError('invalid_account', '帳號權限格式不正確。', 400)
        return values.get('display_name', ''), values.get('role', ''), tuple(p.strip() for p in values.get('projects', '').split(',') if p.strip()), manager == 'true'

    @app.post('/ui/users/{action}')
    async def mutate(action: str, request: Request):
        try:
            current, identity = guard(request)
            if identity is None:
                return redirect('/login')
            if action not in {'create', 'update', 'password', 'enable', 'disable'}:
                raise HubError('not_found', '未知的帳號動作。', 404)
            values = await parse_form(request, max_bytes=24576, max_fields=12)
            project = values.get('return_project', '')
            if project and project not in identity.projects:
                raise HubError('not_found', '找不到可讀取的專案。', 404)
            target, version = verify(current, action, values)
            if action == 'create':
                if target or version:
                    raise HubError('invalid_account', '新增帳號不接受既有身份。', 400)
                display, role, scopes, manager = parsed_permissions(values)
                target = await run_in_threadpool(auth.users.create, current, values.get('username', ''), display,
                    values.get('password', ''), role, scopes, manager)
            elif action == 'update':
                await run_in_threadpool(auth.users.update, current, target, version, *parsed_permissions(values))
            elif action == 'password':
                await run_in_threadpool(auth.users.password, current, target, version, values.get('password', ''))
            else:
                await run_in_threadpool(auth.users.set_enabled, current, target, version, action == 'enable')
            return redirect('/ui/users?' + urlencode({'user_id': target, 'project': project}))
        except HubError as exc:
            return error(exc)
        except SQLAlchemyError:
            return error(HubError('unavailable', '資料庫暫時無法使用。', 503))

    @app.get('/ui/account/password')
    def self_password_page(request: Request):
        try:
            current, identity = guard(request, manager=False)
            if identity is None:
                return redirect('/login')
            body = '<h2>我的密碼</h2><p>變更成功後所有既有登入失效，請用新密碼重新登入。</p>' + start('self-password', current, identity.user_id, identity.version)
            body += password_field('current_password', '目前密碼') + password_field() + '<p><button>變更自己的密碼</button></p></form>'
            return page(shell('設定',body,selected_project(request,identity),identity.role,config=auth.config,identity=identity,csrf=current['csrf'],section='settings',tab='password'))
        except HubError as exc:
            return error(exc)
        except SQLAlchemyError:
            return error(HubError('unavailable', '資料庫暫時無法使用。', 503))

    @app.post('/ui/account/password')
    async def self_password_post(request: Request):
        try:
            current, identity = guard(request, manager=False)
            if identity is None:
                return redirect('/login')
            values = await parse_form(request, max_bytes=32768, max_fields=8)
            target, version = verify(current, 'self-password', values)
            if target != identity.user_id:
                raise HubError('forbidden', '只能變更自己的密碼。', 403)
            await run_in_threadpool(auth.users.password, current, target, version, values.get('password', ''), current_password=values.get('current_password', ''))
            return redirect('/login')
        except HubError as exc:
            return error(exc)
        except SQLAlchemyError:
            return error(HubError('unavailable', '資料庫暫時無法使用。', 503))
