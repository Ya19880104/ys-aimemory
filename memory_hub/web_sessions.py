"""Cookie-authenticated shared rooms. Bearer tools use the same Session service."""
from .i18n import tr
import base64
import hashlib
import hmac
import json
import os
import secrets
from urllib.parse import quote

from fastapi import Request
from fastapi.responses import JSONResponse, Response
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from .store import HubError
from .web import e, page
from .web_chat_assets import CHAT_CSS, chat_script
from .web_help import public_base_url, _public_ca

CHAT_ROUTES = {'/ui/chat', '/ui/chat/data', '/ui/chat/action', '/ui/chat/file'}
CHAT_ACTIONS = {'create_session', 'post_session_message', 'create_session_artifact',
                'upload_session_attachment', 'archive_session', 'set_session_delivery_paused'}
HEADERS = {'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff', 'Referrer-Policy': 'no-referrer'}


def install_sessions(app, hub, auth, session, redirect):
    # Labels are an explicit operator assertion, never guessed from worker IDs.
    # They affect presentation only; author IDs and authorization are unchanged.
    try:
        worker_names = json.loads(os.environ.get('HUB_WORKER_DISPLAY_NAMES') or '{}')
        if (not isinstance(worker_names, dict) or len(worker_names) > 200 or
            any(not isinstance(k, str) or not 1 <= len(k) <= 128 or
                not isinstance(v, str) or not v.strip() or len(v) > 100 or
                any(ord(c) < 32 for c in k + v) for k, v in worker_names.items())):
            raise ValueError()
    except (ValueError, TypeError):
        raise ValueError('HUB_WORKER_DISPLAY_NAMES must map worker IDs to display names') from None

    def present(value):
        if isinstance(value, list):
            return [present(item) for item in value]
        if not isinstance(value, dict):
            return value
        value = {key: present(item) for key, item in value.items()}
        if value.get('kind') == 'worker' and value.get('id') in worker_names:
            value['display_name'] = worker_names[value['id']]
        elif value.get('worker_id') in worker_names:
            value['display_name'] = worker_names[value['worker_id']]
        return value

    def delivery_call(name, arguments, actor):
        delivery = getattr(hub, 'delivery', None)
        if delivery is None:
            raise HubError('unavailable', (tr('ui_a2c1a96deda2')), 503)
        return delivery.call(name, arguments, actor)

    def identity(request):
        current = session(request)
        principal = auth.principal(current) if current else None
        if principal is None:
            raise HubError('unauthorized', (tr('ui_13c3485fbe25')), 401)
        from .session_service import SessionActor
        actor = SessionActor(kind='human', id=principal.user_id, display_name=principal.display_name,
                             projects=principal.projects, role=principal.role)
        return current, principal, actor

    def scope(actor, project):
        if project not in actor.projects:
            raise HubError('not_found', (tr('ui_1d8812ac41ce')), 404)

    def result(value, status=200):
        return JSONResponse(present(value), status_code=status, headers=HEADERS)

    def failure(exc):
        if isinstance(exc, HubError):
            return result({'error': exc.code, 'message': exc.message}, exc.status)
        if isinstance(exc, SQLAlchemyError):
            return result({'error': 'unavailable', 'message': (tr('ui_48f0dcd631f7'))}, 503)
        return result({'error': 'invalid_arguments', 'message': (tr('ui_87f810597b05'))}, 422)

    def nonce_scope(project, room):
        return json.dumps([project, room], separators=(',', ':'))

    @app.get('/ui/chat')
    def chat(request: Request):
        try:
            current, person, actor = identity(request)
            project = request.query_params.get('project') or next(iter(actor.projects), '')
            if project:
                scope(actor, project)
            label = (tr('ui_3c998927bece')) if person.role == 'admin' else (tr('composer_member'))
            options = ''.join('<option value="' + e(p) + '"' + (' selected' if p == project else '') + '>' + e(p) + '</option>' for p in actor.projects)
            navigation = '<a id="project-tasks-link" href="/ui?project=' + quote(project,safe='') + (tr('ui_249328c8a8c6') + '</a><a id="project-memory-link" href="/ui?project=') + quote(project,safe='') + (tr('ui_f6369853dc0a') + '</a><a id="project-mcp-link" href="/ui?project=') + quote(project,safe='') + (tr('ui_7c0c138323dc') + '</a>')
            navigation += '<a id="project-settings-link" href="/ui/account/password?project=' + quote(project,safe='') + (tr('ui_851abff529f6') + '</a>')
            body = (('<div class="chat-app"><header class="chat-top"><div><a id="project-home-link" class="brand" aria-label="' + tr('ui_517a66c12bf9') + '" href="/ui?project=')) + quote(project, safe='') + ('">ys-aimemory</a><span class="chat-title">' + tr('ui_68236f7b4acd') + '</span></div><nav aria-label="' + tr('ui_8f347997bc92') + '">') + navigation + '</nav></header>'
            ca = _public_ca(os.getenv('HUB_PUBLIC_CA_FILE') or '/app/public/ys-ai-memory-ca.crt')
            setup_base = public_base_url() if os.getenv('HUB_PUBLIC_BASE_URL') and ca else ''
            body += '<div id="room-config" data-csrf="' + e(current['csrf']) + '" data-setup-base="' + e(setup_base) + '" data-setup-ca="' + e(ca.fingerprint if ca else '') + '" data-role="' + e(person.role) + '" data-user="' + e(person.user_id) + '"></div>'
            body += ('<div class="chat-workspace"><section class="room-nav" aria-label="' + tr('ui_451328ed37e9') + '"><h1>' + tr('ui_02bf8e3c6fa6') + '</h1><div class="room-filters"><div><label for="chat-project">' + tr('ui_e564b916b12e') + '</label><select id="chat-project">') + options + ('</select></div><div><label for="room-status">' + tr('ui_c30670cbfc51') + '</label><select id="room-status"><option value="open">' + tr('ui_e7e5869de581') + '</option><option value="archived">' + tr('ui_1499cf5a6a80') + '</option></select></div></div><form id="create-room"><label for="room-title">' + tr('ui_9c567ca5168e') + '</label><input id="room-title" placeholder="' + tr('ui_5869546c81da') + '" maxlength="160" required><button type="submit">' + tr('ui_1685575e61b5') + '</button></form><div id="room-list" aria-live="polite"></div><button id="more-rooms" type="button" hidden>' + tr('ui_e06a5e9d9ab5') + '</button><p class="room-note">' + tr('ui_af8ee2df82e2') + '</p></section>')
            body += ('<main class="room-main"><header class="room-heading"><div><span class="eyebrow">' + tr('ui_7f12174f454c') + '</span><h2 id="active-room">' + tr('ui_67babec0d58d') + '</h2><p id="room-visibility">' + tr('ui_637450baeab8') + '</p></div><button id="archive-room" type="button" hidden>' + tr('ui_d594d0ff9a4b') + '</button></header><div class="sync-bar"><span id="sync-status" role="status">' + tr('ui_38bb242511a3') + '</span><button id="sync-now" type="button">' + tr('ui_74d58e282750') + '</button></div><section class="delivery-notice" aria-label="' + tr('ui_b0ac339b4569') + '"><div class="delivery-heading"><strong id="delivery-title">' + tr('ui_7cd33c58c2e3') + '</strong><button id="pause-delivery" type="button" hidden disabled>' + tr('ui_e7efcf8dd0ba') + '</button></div><p id="delivery-explanation">' + tr('ui_d21cf4bd524b') + '</p><div id="delivery-participants" aria-live="polite"></div><details><summary>' + tr('ui_24ad9291bd59') + '</summary><p>' + tr('ui_15f6645420bf') + '</p><p>' + tr('ui_2f741293fe55') + '</p><a href="/help#automatic-chat">' + tr('ui_daa827b9862c') + '</a></details></section><div id="chat-error" role="alert" hidden></div><button id="older-messages" type="button" hidden>' + tr('ui_8c685baf48dd') + '</button><div id="chat-stream" tabindex="-1" role="log" aria-label="' + tr('ui_4841fc02113e') + '" aria-live="polite"><div class="chat-empty"><strong>' + tr('ui_b625ad120af4') + '</strong>' + tr('ui_ebbcd99950d6') + '<p>' + tr('ui_cc46aa5c1463') + '</p></div></div><form id="message-form" class="composer"><div class="composer-by">' + tr('composer_posting_as').format(role=e(label), name=e(person.display_name)) + '</div><div id="reply-preview" hidden></div><label class="sr-only" for="message-body">' + tr('ui_87d1f8b4dd79') + '</label><textarea id="message-body" placeholder="' + tr('ui_6c9e5980fb10') + '" rows="3" maxlength="8000" required></textarea><div class="composer-tools"><div><label class="file-control" for="message-file">' + tr('ui_e6e3dc07d52a') + '</label><input id="message-file" type="file"><span id="file-status"></span></div><button id="send-message" type="submit">' + tr('ui_1a5f00488854') + '</button></div><p class="room-note">' + tr('ui_b4de5e37f879') + '</p><p class="room-note">' + tr('ui_e3cb77785fe2') + '</p></form></main>')
            body += ('<section class="room-context" aria-label="' + tr('ui_766e98213e5d') + '"><section id="artifact-detail" tabindex="-1" aria-label="' + tr('ui_1c528b52a950') + '" hidden><h3 id="detail-title"></h3><p id="detail-meta" class="room-note"></p><pre id="detail-content"></pre><details id="version-info"><summary>' + tr('ui_fb1b52af7f9d') + '</summary><p id="detail-version"></p></details><button id="more-artifact" type="button" hidden>' + tr('ui_3ad140781663') + '</button><button id="close-detail" type="button">' + tr('ui_8c15d82cac91') + '</button></section><section class="context-section"><h2>' + tr('ui_78fc0ea402e9') + '</h2><p class="room-note">' + tr('ui_f62b4d7f336f') + '</p><details id="artifact-editor"><summary>' + tr('ui_c8d00d5ce574') + '</summary><form id="artifact-form"><label for="artifact-kind">' + tr('ui_1588dd8c9e73') + '</label><select id="artifact-kind"><option value="document">' + tr('ui_39932f24fe11') + '</option><option value="plan">' + tr('ui_6f949ac3522d') + '</option><option value="summary">' + tr('ui_e58e86d5dd64') + '</option><option value="task_proposal">' + tr('ui_33170e67f6ba') + '</option><option value="handoff_proposal">' + tr('ui_37f02eade9df') + '</option></select><label for="artifact-title">' + tr('ui_6fe38ed1ee10') + '</label><input id="artifact-title" maxlength="160" required><label for="artifact-content">' + tr('ui_21e5bce6a622') + '</label><textarea id="artifact-content" required placeholder="' + tr('ui_5f8676b52d13') + '"></textarea><p class="room-note">' + tr('ui_a78e64c99333') + '</p><button type="submit">' + tr('ui_38d595530e08') + '</button></form></details><div id="artifact-list"></div><a id="task-link" href="/ui?view=tasks&amp;project=') + quote(project, safe='') + (tr('ui_becded990123') + '</a></section><section class="context-section"><h3>' + tr('ui_73b3a17d4355') + '</h3><div id="attachment-list"><p class="room-note">' + tr('ui_9882c99f3fac') + '</p></div></section><section class="context-section connect-tip"><h3>' + tr('ui_64aa45b90156') + '</h3><p>' + tr('ui_11037d82b7bc') + '</p><button id="copy-invite" type="button" disabled>' + tr('ui_8fbd48234a05') + '</button><p>' + tr('ui_2f463aa076a2') + '</p><details id="auto-setup"><summary>' + tr('ui_aa001001') + '</summary><p>' + tr('ui_aa001002') + '</p><label for="auto-client">' + tr('ui_aa001003') + '</label><select id="auto-client"><option value="claude">Claude Code</option><option value="codex">Codex CLI</option></select><label for="auto-worker">' + tr('ui_aa001004') + '</label><input id="auto-worker" maxlength="128" autocomplete="off"><a id="auto-worker-link" href="/ui/mcp?">' + tr('ui_aa001005') + '</a><label for="auto-hours">' + tr('ui_aa001006') + '</label><input id="auto-hours" type="number" min="1" max="8" value="1"><label for="auto-turns">' + tr('ui_aa001007') + '</label><input id="auto-turns" type="number" min="1" max="100" value="20"><button id="copy-auto-setup" type="button" disabled>' + tr('ui_aa001008') + '</button><textarea id="auto-instructions" rows="10" readonly hidden aria-label="' + tr('ui_aa001008') + '"></textarea><p id="auto-setup-status" role="status"></p></details></section><details class="search-disclosure"><summary>' + tr('ui_5cca3eaf6ca3') + '</summary><form id="search-form"><label for="search-query">' + tr('ui_961aef0488e9') + '</label><div class="search-controls"><input id="search-query" maxlength="200" placeholder="' + tr('ui_61ec976adade') + '" required><button type="submit">' + tr('ui_7f709fe1022a') + '</button></div></form><div id="search-results" aria-live="polite"></div><button id="more-search" type="button" hidden>' + tr('ui_0ab09d3ca347') + '</button></details></section></div></div>')
            return page(body, script=chat_script(), css=CHAT_CSS, connect=True)
        except HubError as exc:
            if exc.status == 401:
                return redirect('/login')
            return page('<main><h1>' + e(exc.message) + ('</h1><a href="/ui">' + tr('ui_34c6fb9e6b18') + '</a></main>'), exc.status)
        except SQLAlchemyError as exc:
            return failure(exc)

    @app.get('/ui/chat/data')
    def data(request: Request):
        try:
            current, person, actor = identity(request)
            q = request.query_params
            op, project, room = q.get('op', 'list'), q.get('project', ''), q.get('session', '')
            if project:
                scope(actor, project)
            if op == 'nonce':
                action = q.get('action', '')
                if action not in CHAT_ACTIONS or person.role == 'read_only':
                    raise HubError('forbidden', (tr('ui_6caf7bb303a9')), 403)
                if action == 'set_session_delivery_paused' and person.role != 'admin':
                    raise HubError('forbidden', (tr('ui_5420c15ad8c4')), 403)
                token = secrets.token_urlsafe(24)
                if not auth.start_nonce(token, current, 'chat-' + action, nonce_scope(project, room)):
                    raise HubError('unauthorized', (tr('ui_8a9d88231742')), 401)
                return result({'nonce': token})
            if op == 'list':
                args = {'status': q.get('status', 'open'), 'limit': 20}
                if project:
                    args['project_id'] = project
                if q.get('after_id'):
                    args['after_id'] = q['after_id']
                name = 'list_sessions'
            elif op == 'read':
                name, args = 'read_session', {'project_id': project, 'session_id': room,
                    'after_sequence': int(q.get('after', '0')), 'limit': 20, 'max_bytes': 65536, 'full_text': True}
            elif op == 'search':
                name, args = 'search_sessions', {'project_id': project, 'query': q.get('query', ''), 'limit': 20, 'after_sequence': int(q.get('after', '0'))}
                if room:
                    args['session_id'] = room
            elif op == 'artifact':
                name, args = 'get_session_artifact', {'project_id': project, 'session_id': room,
                    'artifact_id': q.get('artifact', ''), 'offset': int(q.get('offset', '0')), 'limit_chars': 8000}
            elif op == 'artifacts':
                return result(hub.sessions.latest_artifacts(project, room, actor))
            elif op == 'delivery':
                return result(delivery_call('status', {'project_id': project, 'session_id': room}, actor))
            else:
                raise HubError('not_found', (tr('ui_c4a2b35b7145')), 404)
            return result(hub.sessions.call(name, args, actor))
        except (HubError, ValidationError, ValueError, SQLAlchemyError) as exc:
            return failure(exc)

    @app.post('/ui/chat/action')
    async def mutate(request: Request):
        try:
            current, person, actor = identity(request)
            if person.role == 'read_only':
                raise HubError('forbidden', (tr('ui_5e3f014ed690')), 403)
            if not hmac.compare_digest(request.headers.get('X-CSRF-Token', '').encode(), current['csrf'].encode()):
                raise HubError('csrf', (tr('ui_9d00f2d7beca')), 403)
            if request.headers.get('content-type', '').split(';')[0] != 'application/json':
                raise ValueError('JSON required')
            payload = await request.json()
            if not isinstance(payload, dict) or set(payload) - {'action', 'arguments', 'nonce'}:
                raise ValueError('Invalid envelope')
            action, args = payload.get('action'), payload.get('arguments')
            if action not in CHAT_ACTIONS or not isinstance(args, dict):
                raise ValueError('Invalid action')
            project, room = args.get('project_id', ''), args.get('session_id', '')
            scope(actor, project)
            nonce = payload.get('nonce', '')
            if not isinstance(nonce, str) or not auth.consume_nonce(nonce, current, 'chat-' + action, nonce_scope(project, room)):
                raise HubError('duplicate_or_expired', (tr('ui_be32f4d54111')), 409)
            # Re-read live account after body/nonce work; never use caller actor fields.
            _, _, actor = identity(request)
            from starlette.concurrency import run_in_threadpool
            if action == 'set_session_delivery_paused':
                if actor.role != 'admin':
                    raise HubError('forbidden', (tr('ui_5420c15ad8c4')), 403)
                value = await run_in_threadpool(delivery_call, 'pause', args, actor)
            else:
                value = await run_in_threadpool(hub.sessions.call, action, args, actor)
            return result(value)
        except (HubError, ValidationError, ValueError, TypeError, SQLAlchemyError) as exc:
            return failure(exc)

    @app.get('/ui/chat/file')
    def download(request: Request):
        try:
            _, _, actor = identity(request)
            q = request.query_params
            project, room, aid = q.get('project', ''), q.get('session', ''), q.get('attachment', '')
            scope(actor, project)
            content, offset, metadata = bytearray(), 0, None
            while True:
                part = hub.sessions.call('read_session_attachment', {'project_id': project, 'session_id': room,
                    'attachment_id': aid, 'offset': offset, 'limit_bytes': 65536}, actor)
                metadata = metadata or part
                content.extend(base64.b64decode(part['content_base64'], validate=True))
                if len(content) > 524288:
                    raise ValueError('File exceeds limit')
                if not part['has_more']:
                    break
                if part['next_offset'] <= offset:
                    raise ValueError('Invalid file cursor')
                offset = part['next_offset']
            if hashlib.sha256(content).hexdigest() != metadata['sha256']:
                raise HubError('unavailable', (tr('ui_d2ed3971be0c')), 503)
            filename = metadata['filename']
            return Response(bytes(content), media_type='application/octet-stream', headers={**HEADERS,
                'Content-Security-Policy': "default-src 'none'; sandbox",
                'Content-Disposition': "attachment; filename=\"download\"; filename*=UTF-8''" + quote(filename, safe='')})
        except (HubError, ValidationError, ValueError, SQLAlchemyError) as exc:
            return failure(exc)
