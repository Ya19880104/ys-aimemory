"""Cookie-authenticated shared rooms. Bearer tools use the same Session service."""
import base64
import hashlib
import hmac
import json
import secrets
from urllib.parse import quote

from fastapi import Request
from fastapi.responses import JSONResponse, Response
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from .store import HubError
from .web import e, page
from .web_chat_assets import CHAT_CSS, CHAT_JS

CHAT_ROUTES = {'/ui/chat', '/ui/chat/data', '/ui/chat/action', '/ui/chat/file'}
CHAT_ACTIONS = {'create_session', 'post_session_message', 'create_session_artifact',
                'upload_session_attachment', 'archive_session'}
HEADERS = {'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff', 'Referrer-Policy': 'no-referrer'}


def install_sessions(app, hub, auth, session, redirect):
    def identity(request):
        current = session(request)
        principal = auth.principal(current) if current else None
        if principal is None:
            raise HubError('unauthorized', '登入已過期，請重新登入。', 401)
        from .session_service import SessionActor
        actor = SessionActor(kind='human', id=principal.user_id, display_name=principal.display_name,
                             projects=principal.projects, role=principal.role)
        return current, principal, actor

    def scope(actor, project):
        if project not in actor.projects:
            raise HubError('not_found', '找不到可讀取的專案。', 404)

    def result(value, status=200):
        return JSONResponse(value, status_code=status, headers=HEADERS)

    def failure(exc):
        if isinstance(exc, HubError):
            return result({'error': exc.code, 'message': exc.message}, exc.status)
        if isinstance(exc, SQLAlchemyError):
            return result({'error': 'unavailable', 'message': '服務暫時無法使用，請稍後再試。'}, 503)
        return result({'error': 'invalid_arguments', 'message': '資料格式不正確。'}, 422)

    def nonce_scope(project, room):
        return json.dumps([project, room], separators=(',', ':'))

    @app.get('/ui/chat')
    def chat(request: Request):
        try:
            current, person, actor = identity(request)
            project = request.query_params.get('project') or next(iter(actor.projects), '')
            if project:
                scope(actor, project)
            label = '人類管理員' if person.role == 'admin' else '人類成員'
            options = ''.join('<option value="' + e(p) + '"' + (' selected' if p == project else '') + '>' + e(p) + '</option>' for p in actor.projects)
            body = '''<div class="chat-app"><header class="chat-top"><div><a class="brand" href="/ui">ys-aimemory</a><span class="chat-title">共享對話</span></div><nav aria-label="主要導覽"><a href="/ui/manage">任務</a><a href="/ui/mcp">MCP 接入</a><a href="/ui/account/password">我的帳號</a><a href="/help#sessions">操作教學</a></nav></header>'''
            body += '<div id="room-config" data-csrf="' + e(current['csrf']) + '" data-role="' + e(person.role) + '" data-user="' + e(person.user_id) + '"></div>'
            body += '<div class="chat-workspace"><section class="room-nav" aria-label="選擇對話"><h1>Sessions</h1><label for="chat-project">記憶庫</label><select id="chat-project">' + options + '</select><label for="room-status">顯示狀態</label><select id="room-status"><option value="open">進行中</option><option value="archived">已封存</option></select><form id="create-room"><label for="room-title">新增對話</label><input id="room-title" placeholder="例如：首頁改版討論" maxlength="160" required><button type="submit">建立 Session</button></form><div id="room-list" aria-live="polite"></div><button id="more-rooms" type="button" hidden>更多 Session</button><p class="room-note">同一個 MCP 連線可選擇授權範圍內的 Session。切換 Session 不會增加專案權限。</p></section>'
            body += '<main class="room-main"><header class="room-heading"><div><span class="eyebrow">SHARED WORKSPACE</span><h2 id="active-room">選擇一個 Session</h2><p id="room-visibility">此對話與附件對該專案授權成員及管理員可見。</p></div><button id="archive-room" type="button" hidden>封存</button></header><div class="sync-bar"><span id="sync-status" role="status">尚未選擇對話</span><button id="sync-now" type="button">立即同步</button></div><div id="chat-error" role="alert" hidden></div><button id="older-messages" type="button" hidden>載入較早訊息</button><div id="chat-stream" role="log" aria-label="共享對話紀錄" aria-live="polite"><div class="chat-empty">選擇或建立 Session，讓人與 AI 在同一處討論。<p>AI 必須主動讀取或同步訊息，這裡不會自動喚醒模型。</p></div></div><form id="message-form" class="composer"><div class="composer-by">以 ' + e(label) + ' <strong>' + e(person.display_name) + '</strong> 發言</div><div id="reply-preview" hidden></div><label class="sr-only" for="message-body">訊息內容</label><textarea id="message-body" placeholder="提供想法、回覆 AI，或補充需求…" rows="3" maxlength="8000" required></textarea><div class="composer-tools"><div><label class="file-control" for="message-file">附加檔案</label><input id="message-file" type="file"><span id="file-status"></span></div><button id="send-message" type="submit">傳送訊息</button></div><p class="room-note">每檔最多 512 KiB；每個 Session 最多 25 MiB。上傳完成即與專案成員共享。訊息以 8,000 UTF-8 bytes 為限。</p></form></main>'
            body += '<section class="room-context" aria-label="共同成果"><form id="search-form"><label for="search-query">搜尋本記憶庫的對話與成果</label><input id="search-query" maxlength="200" placeholder="輸入關鍵字" required><button type="submit">搜尋紀錄</button></form><div id="search-results" aria-live="polite"></div><button id="more-search" type="button" hidden>更多搜尋結果</button><h2 class="files-heading">最近共同成果</h2><p class="room-note">把討論整理成方案、交接或任務提案。正式任務仍需另外建立或交接。</p><a id="task-link" href="/ui/manage">查看正式任務與交接 →</a><details id="artifact-editor"><summary>建立文件／提案</summary><form id="artifact-form"><label for="artifact-kind">類型</label><select id="artifact-kind"><option value="document">文件</option><option value="plan">方案</option><option value="summary">對話摘要</option><option value="task_proposal">任務提案</option><option value="handoff_proposal">交接提案</option></select><label for="artifact-title">標題</label><input id="artifact-title" maxlength="160" required><label for="artifact-content">內容</label><textarea id="artifact-content" required placeholder="目標、決定、來源、未完成事項…"></textarea><p class="room-note">保存時會標記當前讀到的訊息序號；新訊息不會被誤算進摘要。</p><button type="submit">保存成果</button></form></details><div id="artifact-list"></div><h3 class="files-heading">共享檔案</h3><div id="attachment-list"></div><section id="artifact-detail" hidden><h3 id="detail-title"></h3><p id="detail-meta" class="room-note"></p><pre id="detail-content"></pre><button id="more-artifact" type="button" hidden>讀取下一段</button></section><div class="connect-tip"><h3>讓 AI 加入</h3><p>先在 MCP 產生器取得各自的 Token，再請 AI 搜尋 Session 並選擇本對話。</p><button id="copy-invite" type="button">複製加入指引</button><p>省 Token：先讀新訊息，再按需要取全文或檔案。</p></div></section></div></div>'
            return page(body, script=CHAT_JS, css=CHAT_CSS, connect=True)
        except HubError as exc:
            if exc.status == 401:
                return redirect('/login')
            return page('<main><h1>' + e(exc.message) + '</h1><a href="/ui">返回總覽</a></main>', exc.status)
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
                    raise HubError('forbidden', '此帳號無法執行此動作。', 403)
                token = secrets.token_urlsafe(24)
                if not auth.start_nonce(token, current, 'chat-' + action, nonce_scope(project, room)):
                    raise HubError('unauthorized', '登入已過期。', 401)
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
            else:
                raise HubError('not_found', '未知的讀取方式。', 404)
            return result(hub.sessions.call(name, args, actor))
        except (HubError, ValidationError, ValueError, SQLAlchemyError) as exc:
            return failure(exc)

    @app.post('/ui/chat/action')
    async def mutate(request: Request):
        try:
            current, person, actor = identity(request)
            if person.role == 'read_only':
                raise HubError('forbidden', '唯讀帳號無法發言或建立成果。', 403)
            if not hmac.compare_digest(request.headers.get('X-CSRF-Token', '').encode(), current['csrf'].encode()):
                raise HubError('csrf', '表單驗證失敗，請重新載入。', 403)
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
                raise HubError('duplicate_or_expired', '操作已送出或過期，請重新讀取最新狀態。', 409)
            # Re-read live account after body/nonce work; never use caller actor fields.
            _, _, actor = identity(request)
            from starlette.concurrency import run_in_threadpool
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
                raise HubError('unavailable', '檔案完整性檢查未通過。', 503)
            filename = metadata['filename']
            return Response(bytes(content), media_type='application/octet-stream', headers={**HEADERS,
                'Content-Security-Policy': "default-src 'none'; sandbox",
                'Content-Disposition': "attachment; filename=\"download\"; filename*=UTF-8''" + quote(filename, safe='')})
        except (HubError, ValidationError, ValueError, SQLAlchemyError) as exc:
            return failure(exc)
