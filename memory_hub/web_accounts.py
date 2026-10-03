"""Human account pages. Only explicit account managers can administer users."""
from .i18n import tr
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
            raise HubError('forbidden', (tr('ui_15a7e789ea75')), 403)
        return current, identity

    def selected_project(request, identity):
        value=request.query_params.get('project') or next(iter(identity.projects), '')
        if value and value not in identity.projects: raise HubError('not_found',(tr('ui_1d8812ac41ce')),404)
        return value

    def error(exc):
        if exc.status == 401:
            return redirect('/login')
        return page(shell((tr('ui_12dda12f1106')), '<p class="alert">' + e(exc.message) + ('</p><p><a href="/ui">' + tr('ui_34c6fb9e6b18') + '</a></p>')), exc.status)

    def start(action, current, target='', version=0, project=''):
        nonce = secrets.token_urlsafe(24)
        resource = target + ':' + str(version)
        if not auth.start_nonce(nonce, current, 'users-' + action, resource):
            raise HubError('unauthorized', (tr('ui_446e2f1aa692')), 401)
        route = '/ui/account/password' if action == 'self-password' else '/ui/users/' + action
        return '<form method="post" action="' + route + '">' + hidden('csrf', current['csrf']) + hidden('nonce', nonce) + hidden('target_id', target) + hidden('expected_version', version) + hidden('return_project', project)

    def password_field(name='password', label=(tr('ui_e9f040cf3eb5'))):
        return '<label>' + e(label) + '<input type="password" name="' + e(name) + '" minlength="10" maxlength="1024" autocomplete="' + ('current-password' if name == 'current_password' else 'new-password') + '" required></label>'

    def permissions(row=None):
        row = row or {'role': 'read_only', 'projects': (), 'can_manage_users': False}
        roles = [('read_only', (tr('ui_258b221f71b4'))), ('member', (tr('ui_91b549195826'))), ('admin', (tr('ui_17bfcee53538')))]
        body = ('<label>' + tr('ui_c47b54e84e79') + '<select name="role">') + ''.join('<option value="' + key + '"' + (' selected' if row['role'] == key else '') + '>' + label + '</option>' for key, label in roles) + '</select></label>'
        body += input_field('projects', (tr('ui_e15dca20d337')), ','.join(row['projects']), required=False)
        body += ('<label>' + tr('ui_7272c81bb7da') + '<select name="can_manage_users">') + ''.join('<option value="' + value + '"' + (' selected' if row['can_manage_users'] == (value == 'true') else '') + '>' + label + '</option>' for value, label in [('false', (tr('ui_b427aa9ffc80'))), ('true', (tr('ui_65094ce16616')))]) + '</select></label>'
        return body

    @app.get('/ui/users')
    def users_page(request: Request):
        try:
            current, identity = guard(request)
            if identity is None:
                return redirect('/login')
            project = selected_project(request, identity)
            result = auth.users.list(current, request.query_params.get('after', ''))
            body = ('<p class="alert">' + tr('ui_dea11622e845') + '</p>')
            body += ('<section class="panel"><h2>' + tr('ui_fac920aaecbc') + '</h2>') + start('create', current, project=project) + input_field('username', (tr('ui_aa023fe47b51'))) + input_field('display_name', (tr('ui_bda532c613dd'))) + password_field() + permissions() + ('<p><button>' + tr('ui_fac920aaecbc') + '</button></p></form></section><h2>' + tr('ui_8e517b1f924b') + '</h2>')
            for row in result['items']:
                body += '<p><a href="' + e('/ui/users?' + urlencode({'user_id': row['user_id'], 'project': selected_project(request,identity)})) + '">' + e(row['display_name']) + '（' + e(row['username']) + '）</a> · ' + ((tr('ui_af5eb2248daf')) if row['enabled'] else (tr('ui_a8c3698b5b8c'))) + ' · ' + e(row['role']) + '</p>'
            if result['next_after']:
                body += '<a href="' + e('/ui/users?' + urlencode({'after': result['next_after'], 'project': selected_project(request,identity)})) + (tr('ui_631484f1c5e0') + '</a>')
            selected = request.query_params.get('user_id', '')
            if selected:
                row = auth.users.get(current, selected)
                body += '<section class="panel"><h2>' + e(row['display_name']) + ('</h2><p>' + tr('ui_023f4406a90b')) + e(row['username']) + (tr('ui_2d67bf48688c')) + e(row['user_id']) + ('</p><p>' + tr('ui_4ecbe9e6ab24') + '</p>')
                body += start('update', current, selected, row['version'], project) + input_field('display_name', (tr('ui_bda532c613dd')), row['display_name']) + permissions(row) + ('<p><button>' + tr('ui_c23b16b0bbce') + '</button></p></form>')
                action = 'disable' if row['enabled'] else 'enable'
                body += start(action, current, selected, row['version'], project) + '<p><button>' + ((tr('ui_b2ee01f4354e')) if row['enabled'] else (tr('ui_6519a9b02c71'))) + '</button></p></form>'
                body += start('password', current, selected, row['version'], project) + password_field() + ('<p><button>' + tr('ui_e189e5018ab4') + '</button></p></form></section>')
            return page(shell((tr('ui_e4d7d9dd6324')),body,selected_project(request,identity),identity.role,config=auth.config,identity=identity,csrf=current['csrf'],section='settings',tab='users'))
        except HubError as exc:
            return error(exc)
        except SQLAlchemyError:
            return error(HubError('unavailable', (tr('ui_31d0a840a167')), 503))

    def verify(current, action, values):
        if not hmac.compare_digest(values.get('csrf', '').encode(), current['csrf'].encode()):
            raise HubError('csrf', (tr('ui_9d00f2d7beca')), 403)
        try:
            version = int(values.get('expected_version', ''))
        except ValueError:
            raise HubError('invalid_account', (tr('ui_1455f71494aa')), 400) from None
        target = values.get('target_id', '')
        if len(target) > 36 or version < 0:
            raise HubError('invalid_account', (tr('ui_c44c21649fca')), 400)
        if not auth.consume_nonce(values.get('nonce', ''), current, 'users-' + action, target + ':' + str(version)):
            raise HubError('duplicate_or_expired', (tr('ui_16d25075b6fd')), 409)
        return target, version

    def parsed_permissions(values):
        manager = values.get('can_manage_users', 'false')
        if manager not in ('true', 'false'):
            raise HubError('invalid_account', (tr('ui_e5f72bfcc873')), 400)
        return values.get('display_name', ''), values.get('role', ''), tuple(p.strip() for p in values.get('projects', '').split(',') if p.strip()), manager == 'true'

    @app.post('/ui/users/{action}')
    async def mutate(action: str, request: Request):
        try:
            current, identity = guard(request)
            if identity is None:
                return redirect('/login')
            if action not in {'create', 'update', 'password', 'enable', 'disable'}:
                raise HubError('not_found', (tr('ui_85cfcbccc2ec')), 404)
            values = await parse_form(request, max_bytes=24576, max_fields=12)
            project = values.get('return_project', '')
            if project and project not in identity.projects:
                raise HubError('not_found', (tr('ui_1d8812ac41ce')), 404)
            target, version = verify(current, action, values)
            if action == 'create':
                if target or version:
                    raise HubError('invalid_account', (tr('ui_5d16e7cdc549')), 400)
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
            return error(HubError('unavailable', (tr('ui_31d0a840a167')), 503))

    @app.get('/ui/account/password')
    def self_password_page(request: Request):
        try:
            current, identity = guard(request, manager=False)
            if identity is None:
                return redirect('/login')
            body = ('<h2>' + tr('ui_475fe4d4bf58') + '</h2><p>' + tr('ui_38116e2b8341') + '</p>') + start('self-password', current, identity.user_id, identity.version)
            body += password_field('current_password', (tr('ui_cfd5861bdd7d'))) + password_field() + ('<p><button>' + tr('ui_cc589ba6f167') + '</button></p></form>')
            return page(shell((tr('ui_0d8619aae051')),body,selected_project(request,identity),identity.role,config=auth.config,identity=identity,csrf=current['csrf'],section='settings',tab='password'))
        except HubError as exc:
            return error(exc)
        except SQLAlchemyError:
            return error(HubError('unavailable', (tr('ui_31d0a840a167')), 503))

    @app.post('/ui/account/password')
    async def self_password_post(request: Request):
        try:
            current, identity = guard(request, manager=False)
            if identity is None:
                return redirect('/login')
            values = await parse_form(request, max_bytes=32768, max_fields=8)
            target, version = verify(current, 'self-password', values)
            if target != identity.user_id:
                raise HubError('forbidden', (tr('ui_753062cd23c6')), 403)
            await run_in_threadpool(auth.users.password, current, target, version, values.get('password', ''), current_password=values.get('current_password', ''))
            return redirect('/login')
        except HubError as exc:
            return error(exc)
        except SQLAlchemyError:
            return error(HubError('unavailable', (tr('ui_31d0a840a167')), 503))
