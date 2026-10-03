"""Administrator onboarding: scoped libraries and one-time worker credentials."""
from .i18n import tr
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
COPY_SCRIPT = r'''document.addEventListener('click', async event => {
  const button = event.target.closest('button[data-copy],button[data-download]');
  if (!button) return;
  const source = document.getElementById(button.dataset.copy || button.dataset.download);
  const status = document.getElementById('copy-status');
  if (button.dataset.copy) {
    try { await navigator.clipboard.writeText(source.value); status.textContent = uiText('ui_5f1fc265c7ec'); }
    catch { source.focus(); source.select(); status.textContent = uiText('ui_08113a3e4640'); }
  } else {
    const url = URL.createObjectURL(new Blob([source.value], {type:'text/plain;charset=utf-8'}));
    const a = document.createElement('a'); a.href = url; a.download = button.dataset.filename;
    a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
    status.textContent = uiText('ui_28bb9a5c926f');
  }
});'''


def copy_script():
    from .i18n import script_catalog
    return script_catalog(COPY_SCRIPT) + COPY_SCRIPT


def templates(base_url):
    endpoint = base_url + '/mcp'
    return [
        ('codex', (tr('ui_66486bf64fda')), 'ys-memory-codex.toml',
         '[mcp_servers.ys_memory]\nurl = ' + json.dumps(endpoint) + '\nbearer_token_env_var = "YS_AIMEMORY_TOKEN"\nenabled = true\n'),
        ('claude', (tr('ui_791bc633bc6d')), 'ys-memory-claude-code.json',
         json.dumps({'mcpServers': {'ys_memory': {'type': 'http', 'url': endpoint,
                    'headers': {'Authorization': 'Bearer ${YS_AIMEMORY_TOKEN}'}}}}, ensure_ascii=False, indent=2) + '\n'),
    ]


def config_cards(base_url):
    body = ('<h2>' + tr('ui_aae18e62a930') + '</h2><p>' + tr('ui_9728fe9507a2') + '</p>')
    for name, title, filename, content in templates(base_url):
        field = 'config-' + name
        body += '<section class="panel task"><label for="'+field+'">'+e(title)+'</label><textarea id="'+field+'" readonly rows="8" spellcheck="false">'+e(content)+'</textarea><p><button type="button" data-copy="'+field+(tr('ui_df8f59344aa3') + '</button> <button type="button" data-download="')+field+'" data-filename="'+filename+(tr('ui_4b881c0e896b') + '</button></p></section>')
    from .client_bundle import BUNDLE_ROUTE
    setup = 'py -3.12 -m venv .venv\n.\\.venv\\Scripts\\python.exe -m pip install -r requirements.lock\n.\\.venv\\Scripts\\python.exe .\\bridge.py --compact --print-claude-config'
    body += ('<section class="panel task"><h3>Claude Code：stdio HTTPS adapter</h3><p>' + tr('ui_15e4d4e682b1') + '<code>UNSUPPORTED_CONSTRAINT_TYPE</code>' + tr('ui_e4432cd58aa6') + '</p><p><a class="button" href="')+e(base_url+BUNDLE_ROUTE)+(tr('ui_3e8540692c58') + '</a></p><p>' + tr('ui_77b9d1e0d187') + '</p><pre class="path"><code>')+e(setup)+('</code></pre><p>' + tr('ui_91b8cc3ee5a5') + '</p></section>')
    body += ('<p>' + tr('ui_556dfda6e500') + '<code>YS_AIMEMORY_TOKEN</code>' + tr('ui_4987a04fba44') + '<code>CODEX_CA_CERTIFICATE</code>' + tr('ui_9b7c14f122c4') + '<code>NODE_EXTRA_CA_CERTS</code>' + tr('ui_9d16fda5b79e') + '</p><p><a href="/help#clients">' + tr('ui_ba5fcb41ac08') + '</a></p><p id="copy-status" role="status" aria-live="polite"></p>')
    return body


def install_mcp_management(app, hub, config, session, parse_form, redirect, auth, clock):
    def guard(request):
        current = session(request)
        if not current:
            return None
        identity = auth.principal(current)
        if identity is None: return None
        if identity.role != 'admin' or not config.mcp_enabled:
            raise HubError('forbidden', (tr('ui_f8cb9cf0c84c')), 403)
        return current

    def scoped(project, current):
        identity = auth.principal(current)
        if identity is None or project not in identity.projects:
            raise HubError('forbidden', (tr('ui_ec19e71fbd4b')), 403)

    def start(action, current, project='', extra=None):
        nonce = secrets.token_urlsafe(24)
        auth.start_nonce(nonce, current, 'mcp-' + action, project)
        return '<form method="post" action="/ui/mcp/'+action+'">'+hidden('csrf',current['csrf'])+hidden('nonce',nonce)+hidden('project_id',project)+''.join(hidden(k,v) for k,v in (extra or {}).items())

    def error(exc):
        return page(shell((tr('ui_ede8e0f84896')), '<p class="alert">'+e(exc.message)+('</p><a href="/ui/mcp">' + tr('ui_05c88c6b6a34') + '</a>')), exc.status)

    def unavailable():
        return error(HubError('unavailable', (tr('ui_c4f6e043ced8')), 503))

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
            if request.query_params.get('setup') == 'project':
                body=('<section class="panel"><p>' + tr('ui_5fdeb11deea8') + '</p>')+start('project',current)+input_field('new_project_id',(tr('ui_39174667a521')))+('<p><button>' + tr('ui_181ad3312ed1') + '</button></p></form></section>')
                return page(shell((tr('ui_181ad3312ed1')),body,project,'admin',config=config,identity=identity,csrf=current['csrf'],section='settings',tab='project'))
            body=('<p>' + tr('ui_994464209747') + '</p>')
            if project:
                body+=('<section class="panel task"><h2>' + tr('ui_d959ea09b2d3') + '</h2>')+start('issue',current,project)+input_field('worker_id',(tr('ui_223e32e0caf2')))+('<p><button>' + tr('ui_776f2084bb8f') + '</button></p></form></section><h2>' + tr('ui_624be01635ec') + '</h2>')
            else:
                body+=('<p>' + tr('ui_b3736cb154b0') + '</p>')
            records = hub.credentials.list_credentials([project]) if project else []
            for row in records:
                body += '<section class="panel task"><h3>'+e(row['worker_id'])+('</h3><p>' + tr('ui_4d04986f010a'))+e(row['project_id'])+' · worker · '+((tr('ui_3c22dce74d92')) if row['revoked_at'] is not None else (tr('ui_11afd2a53439')))+('</p><p class="muted">' + tr('ui_bf8cc4574c59'))+e(stamp(row['created_at']))+(tr('ui_033a7d706fce'))+e(row['version'])+'</p>'
                if row['revoked_at'] is None:
                    extra = {'token_id':row['token_id'],'expected_version':row['version']}
                    body += ('<p>' + tr('ui_140beadc980d') + '</p>')+start('rotate',current,project,extra)+('<p><button>' + tr('ui_ce470c68ad74') + '</button></p></form>')+start('revoke',current,project,extra)+('<p><button>' + tr('ui_8871c2701c22') + '</button></p></form>')
                body += '</section>'
            if project and not records:
                body += ('<p class="muted">' + tr('ui_2ea3f51377d3') + '</p>')
            body += ('<p class="muted">' + tr('ui_eb8cffc8fa20') + '</p>')+config_cards(public_base_url())
            return page(shell((tr('ui_e6d6f89902cb')),body,project,'admin',config=config,identity=identity,csrf=current['csrf'],section='connections',tab='edit'), script=copy_script())
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
                raise HubError('not_found',(tr('ui_73c12c28d6e2')),404)
            values = await parse_form(request, max_bytes=8192, max_fields=8)
            project = values.get('project_id','')
            if action != 'project':
                scoped(project, current)
            elif project:
                raise HubError('invalid_project',(tr('ui_927350154e87')),400)
            if not hmac.compare_digest(values.get('csrf','').encode(),current['csrf'].encode()):
                raise HubError('csrf',(tr('ui_9d00f2d7beca')),403)
            if not auth.consume_nonce(values.get('nonce',''),current,'mcp-'+action,project):
                raise HubError('duplicate_or_expired',(tr('ui_e2cb1bed22cb')),409)
            from .web_help import public_base_url
            # Resolve configuration before mutation so malformed deployment config
            # cannot mint a token and then fail while rendering its only response.
            base = public_base_url()
            registry = hub.credentials
            identity = auth.principal(current)
            if identity is None: return redirect('/login')
            if identity.role != 'admin': raise HubError('forbidden', (tr('ui_f8b8e59ef830')), 403)
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
            body = ('<div class="alert">' + tr('ui_f469d523f4d0') + '</div><p>' + tr('ui_4d04986f010a') + '<strong>')+e(issued['project_id'])+('</strong>' + tr('ui_c9d3fd7a9d47') + '<strong>')+e(issued['worker_id'])+('</strong> · worker</p><label for="issued-token">' + tr('ui_00cad93c9c4e') + '</label><textarea id="issued-token" readonly rows="3" spellcheck="false" autocomplete="off">')+e(issued['token'])+('</textarea><p><button type="button" data-copy="issued-token">' + tr('ui_669d1acc199f') + '</button></p>')+config_cards(base)+'<p><a href="/ui/mcp?'+e(urlencode({'project':project}))+(tr('ui_431369438bf8') + '</a></p>')
            return page(shell((tr('ui_13ec43b7c74f')),body,project,'admin',config=config,identity=identity,csrf=current['csrf'],section='connections',tab='edit'), script=copy_script())
        except HubError as exc:
            return error(exc)
        except (ValueError, TypeError):
            return error(HubError('invalid_form',(tr('ui_f03bb2a5cb23')),400))
        except SQLAlchemyError:
            return unavailable()
