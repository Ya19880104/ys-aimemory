"""Read-only recovery report for a dedicated Codex chat receiver.

Compares the receiver's local journal with the Hub's own status route and names
what each record shows and what is still missing. It never joins, claims, posts,
disconnects, starts a model, inspects or stops a process, or changes receiver or product state.
The report supports an operator's decision; it performs no recovery, grants no
retry and does not establish that a native process has exited.
"""
import argparse
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import re
import sys
import time

import httpx

STATUS_ROUTE = '/v1/chat/status'
RESPONSE_LIMIT = 1048576
FILE_LIMIT = 65536
HEX = re.compile('[0-9a-f]{32}')
CODE = re.compile('[a-z0-9_]{1,80}')
BINDING_STATES = {'revoked', 'disconnected', 'archived', 'paused', 'disabled', 'expired', 'failed',
                  'processing', 'budget_exhausted', 'waiting', 'offline'}
DELIVERY_STATES = {'leased', 'dispatched', 'tool_read', 'failed', 'retry_ready', 'replied',
                   'released', 'superseded'}
FIXED = {'read_only': True, 'automatic_recovery': 'not_performed',
         'retry_permission': 'not_granted_by_this_report',
         'native_exit': 'not_established_by_this_report'}


class InspectorError(RuntimeError):
    """Fixed codes only; never interpolate remote output, paths or credentials."""


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise InspectorError('invalid_arguments_use_help')


class StatusOnlyTransport(httpx.BaseTransport):
    """Refuse everything except the exact status GET before it reaches a socket."""
    def __init__(self, inner):
        self.inner = inner

    def handle_request(self, request):
        if (request.method != 'GET' or request.url.path != STATUS_ROUTE
                or sorted(key for key, _ in request.url.params.multi_items()) != ['project_id', 'session_id']):
            raise InspectorError('only_status_get_permitted')
        return self.inner.handle_request(request)

    def close(self):
        self.inner.close()


def iso(value):
    if type(value) not in (int, float) or not 0 <= value < 32503680000:
        return None
    return datetime.fromtimestamp(value, timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z')


def linked(path):
    return path.is_symlink() or bool(getattr(path, 'is_junction', lambda: False)())


def read_json(path):
    """Bounded read of one known file; (value, problem). Links are never followed."""
    if linked(path):
        return None, 'linked'
    if not path.exists():
        return None, 'absent'
    if not path.is_file():
        return None, 'not_a_file'
    with path.open('rb') as stream:
        data = stream.read(FILE_LIMIT + 1)
    if len(data) > FILE_LIMIT:
        return None, 'too_large'
    try:
        return json.loads(data.decode('utf-8')), None
    except (ValueError, RecursionError):
        return None, 'malformed'


def is_id(value):
    return isinstance(value, str) and HEX.fullmatch(value) is not None


def is_int(value, minimum=0):
    return type(value) is int and value >= minimum


def read_state(directory, scope):
    """Allowlisted facts from the receiver's own journal. Opens files for reading only."""
    directory = Path(directory)
    if any(linked(p) for p in (directory, *directory.parents)):
        raise InspectorError('linked_state_refused')
    local = {'journal': 'present' if directory.is_dir() else 'absent', 'problems': [],
             'config': {'status': 'absent'}, 'binding': {'status': 'absent'},
             'claim': {'status': 'absent'}, 'delivery': {'status': 'absent'},
             'completion': {'status': 'absent'}, 'native_marker': {'status': 'absent'},
             'stop': 'absent', 'last_status': {'status': 'absent'}, 'receipts': 0}
    if local['journal'] == 'absent':
        return local

    def take(name, check):
        path = directory / name
        value, problem = read_json(path)
        if problem == 'absent':
            return None
        entry = {'status': problem or 'valid', 'modified_at': None if problem == 'linked' else iso(path.stat().st_mtime)}
        if problem is None:
            fields = check(value) if isinstance(value, dict) else 'malformed'
            if isinstance(fields, str):
                entry['status'] = fields
            else:
                entry.update(fields)
        if entry['status'] != 'valid':
            local['problems'].append(entry['status'])
            entry = {'status': entry['status'], 'modified_at': entry['modified_at']}
        return entry

    def scoped(value, keys=('project_id', 'session_id', 'worker_id')):
        return all(value.get(k) == scope[k] for k in keys if k in scope)

    def config(value):
        if not scoped(value):
            return 'scope_mismatch'
        return {'expires_at': iso(value.get('expires_at')), 'max_turns': value.get('max_turns')
                if is_int(value.get('max_turns'), 1) else None}

    def binding(value):
        if set(value) != {'project_id', 'session_id', 'worker_id', 'binding_id', 'generation'}:
            return 'malformed'
        if not scoped(value):
            return 'scope_mismatch'
        if not is_id(value['binding_id']) or not is_int(value['generation'], 1):
            return 'malformed'
        return {'binding_id': value['binding_id'], 'generation': value['generation']}

    def claim(value):
        if (set(value) != {'project_id', 'binding_id', 'generation', 'request_id', 'lease_seconds'}
                or not is_id(value['binding_id']) or not is_int(value['generation'], 1)):
            return 'malformed'
        if value['project_id'] != scope['project_id']:
            return 'scope_mismatch'
        # The request ID replays a claim; it is deliberately left out of the report.
        return {'binding_id': value['binding_id'], 'generation': value['generation']}

    def delivery(value):
        ids = value.get('message_ids')
        if (set(value) != {'delivery_id', 'lease_id', 'after_sequence', 'through_sequence',
                           'message_ids', 'reply_idempotency_key'}
                or not is_id(value['delivery_id']) or not is_int(value['after_sequence'])
                or not is_int(value['through_sequence']) or value['through_sequence'] <= value['after_sequence']
                or not isinstance(ids, list) or not ids or not all(is_id(item) for item in ids)):
            return 'malformed'
        # The lease and reply key authorize writes; they never enter the report.
        return {'delivery_id': value['delivery_id'], 'after_sequence': value['after_sequence'],
                'through_sequence': value['through_sequence'], 'messages': len(ids)}

    def marker(value):
        return {'recorded_state': value['state'] if value.get('state') == 'starting' else 'unrecognized'}

    def status(value):
        def code(item):
            return item if isinstance(item, str) and CODE.fullmatch(item) else None if item is None else 'unrecognized'
        return {'state': code(value.get('state')), 'error_code': code(value.get('error_code')),
                'at': iso(value.get('at')), 'native_turns': value.get('native_turns')
                if is_int(value.get('native_turns')) else None}

    for name, key, check in (('receiver-config.json', 'config', config),
                             ('receiver-binding.json', 'binding', binding),
                             ('receiver-claim.json', 'claim', claim),
                             ('receiver-delivery.json', 'delivery', delivery),
                             ('receiver-status.json', 'last_status', status)):
        entry = take(name, check)
        if entry is not None:
            local[key] = entry
    # The marker carries no process identity. Its presence is the only fact used.
    path = directory / 'native-active.json'
    if linked(path) or path.exists():
        value, problem = read_json(path)
        local['native_marker'] = {'status': 'present', 'modified_at': None if problem == 'linked' else iso(path.stat().st_mtime),
            'recorded_state': marker(value)['recorded_state'] if isinstance(value, dict) else problem or 'unrecognized'}
    stop = directory / 'STOP'
    local['stop'] = 'linked' if linked(stop) else 'present' if stop.exists() else 'absent'
    local['receipts'] = sum(1 for item in directory.glob('receipt-*.json') if not linked(item) and item.is_file())
    if local['delivery']['status'] == 'valid':
        def completion(value):
            post = value.get('post_receipt')
            if (value.get('status') != 'passed' or value.get('delivery_id') != local['delivery']['delivery_id']
                    or value.get('worker_id') != scope['worker_id'] or not isinstance(post, dict)
                    or not is_id(post.get('message_id')) or not is_int(post.get('sequence'))
                    or not scoped(post, ('project_id', 'session_id'))):
                return 'malformed'
            return {'message_id': post['message_id'], 'sequence': post['sequence']}
        entry = take('receipt-' + local['delivery']['delivery_id'] + '.json', completion)
        if entry is not None:
            local['completion'] = {**entry, 'status': 'recorded' if entry['status'] == 'valid' else entry['status']}
    return local


def fetch_status(client, scope):
    """One bounded GET of the exact status route; (payload, fixed_reason)."""
    body = bytearray()
    try:
        with client.stream('GET', STATUS_ROUTE, params={k: scope[k] for k in ('project_id', 'session_id')}) as response:
            if response.status_code != 200:
                return None, 'http_' + str(response.status_code)
            for chunk in response.iter_bytes():
                body.extend(chunk)
                if len(body) > RESPONSE_LIMIT:
                    return None, 'response_too_large'
    except httpx.TimeoutException:
        return None, 'timeout'
    except httpx.HTTPError:
        return None, 'transport_error'
    try:
        return json.loads(body), None
    except (ValueError, RecursionError):
        return None, 'invalid_response'


def hub_view(payload, scope, binding_id):
    """Allowlisted fields of the one binding this journal names; (view, fixed_reason)."""
    if (not isinstance(payload, dict) or payload.get('project_id') != scope['project_id']
            or payload.get('session_id') != scope['session_id']
            or not isinstance(payload.get('participants'), list)):
        return None, 'invalid_response'
    rows = [item for item in payload['participants'] if isinstance(item, dict)]
    found = [item for item in rows if (item.get('binding_id') == binding_id if binding_id
                                       else item.get('worker_id') == scope['worker_id'])]
    if not found:
        return None, 'binding_not_in_first_page' if payload.get('has_more') is True else 'binding_not_listed'
    row = found[0]
    latest = row.get('latest_delivery')
    if (len(found) != 1 or not is_id(row.get('binding_id')) or not is_int(row.get('generation'), 1)
            or not is_int(row.get('processed_sequence')) or not isinstance(row.get('status'), str)
            or latest is not None and (not isinstance(latest, dict) or not is_id(latest.get('delivery_id'))
                                       or not isinstance(latest.get('status'), str))):
        return None, 'invalid_response'
    view = {'binding_id': row['binding_id'], 'generation': row['generation'],
            'status': row['status'] if row['status'] in BINDING_STATES else 'unrecognized',
            'scope_matches': all(row.get(k) == scope[k] for k in ('project_id', 'session_id', 'worker_id')),
            'lease_live': row['status'] == 'processing', 'processed_sequence': row['processed_sequence'],
            'turns_used': row.get('turns_used') if is_int(row.get('turns_used')) else None,
            'max_turns': row.get('max_turns') if is_int(row.get('max_turns')) else None,
            'released_at': iso(row.get('released_at')), 'expires_at': iso(row.get('expires_at')),
            'room_paused': isinstance(payload.get('control'), dict) and payload['control'].get('paused') is True,
            'latest_delivery': None}
    if latest is not None:
        reply = latest.get('reply_message_id')
        view['latest_delivery'] = {'delivery_id': latest['delivery_id'],
            'status': latest['status'] if latest['status'] in DELIVERY_STATES else 'unrecognized',
            'through_sequence': latest.get('through_sequence') if is_int(latest.get('through_sequence')) else None,
            'attempts': latest.get('attempts') if is_int(latest.get('attempts')) else None,
            'dispatched_at': iso(latest.get('dispatched_at')), 'read_at': iso(latest.get('read_at')),
            'replied_at': iso(latest.get('replied_at')), 'reply_message_id': reply if is_id(reply) else None,
            'reply_sequence': latest.get('reply_sequence') if is_int(latest.get('reply_sequence')) else None}
    return view, None


def classify(local, hub, reason):
    """Name what the two records show. Never infers a reply from a cursor, nor a retry or native exit."""
    missing, actions = [], ['keep_state_directory']
    if local['native_marker']['status'] == 'present':
        missing.append('native_exit_unconfirmed')
        actions.append('marker_blocks_restart_and_disconnect')

    def verdict(state, detail=None, *more):
        actions.extend(more)
        return {'state': state, 'detail': detail, 'evidence_missing': missing, 'next_safe_action': actions}

    if local['problems']:
        scope = 'scope_mismatch' in local['problems']
        return verdict('scope-mismatch' if scope else 'invalid-local-state',
                       'journal_scope' if scope else local['problems'][0], 'ask_administrator')
    binding, delivery, completion = local['binding'], local['delivery'], local['completion']
    if hub is None:
        missing.append('hub_status_not_read')
        return verdict('unavailable', reason, 'rerun_when_hub_reachable')
    if not hub['scope_matches']:
        return verdict('scope-mismatch', 'hub_binding_scope', 'ask_administrator')
    owned = binding['status'] == 'valid'
    if not owned:
        missing.append('local_binding_ownership')
    journaled = delivery['status'] == 'valid'
    if hub['status'] == 'disconnected':
        if journaled:
            missing.append('journaled_delivery_not_exposed_for_this_generation')
        return verdict('disconnected', 'owned_release_generation' if owned and
                       hub['generation'] == binding['generation'] + 1 else 'other_generation',
                       'provision_new_installation_if_wanted')
    if owned and hub['generation'] != binding['generation']:
        if journaled:
            missing.append('journaled_delivery_not_exposed_for_this_generation')
        return verdict('stale-generation', None, 'do_not_start_this_receipt', 'provision_new_installation_if_wanted')
    if not journaled:
        return verdict('no-delivery', 'marker_without_delivery' if local['native_marker']['status'] == 'present' else None)
    latest = hub['latest_delivery']
    recorded = completion['status'] == 'recorded'
    if latest is None or latest['delivery_id'] != delivery['delivery_id']:
        missing.append('journaled_delivery_is_not_hub_latest')
        if latest is not None:
            missing.append('hub_latest_delivery_not_in_journal')
        if hub['processed_sequence'] >= delivery['through_sequence']:
            missing.append('cursor_alone_is_not_reply_evidence')
        return verdict('unresolved', 'delivery_not_latest' if latest else 'no_hub_delivery', 'check_room_before_any_action')
    if (latest['status'] == 'replied' and latest['replied_at'] and latest['reply_message_id']
            and latest['reply_sequence'] is not None):
        if not recorded:
            return verdict('server-replied', 'local-completion-missing', 'do_not_resend_reply_exists')
        same = (completion['message_id'], completion['sequence']) == (latest['reply_message_id'], latest['reply_sequence'])
        return verdict('server-replied', 'local-completion-recorded' if same else 'local-completion-mismatch',
                       *(() if same else ('ask_administrator',)))
    if recorded:
        missing.append('local_completion_not_confirmed_by_hub')
    missing.append('hub_reply_record')
    if latest['status'] == 'tool_read' or latest['read_at'] and not latest['replied_at']:
        return verdict('server-read', None, 'check_room_before_any_action', 'do_not_post_substitute_reply')
    missing.insert(-1, 'hub_full_read_record')
    return verdict('unresolved', 'server_' + latest['status'], 'check_room_before_any_action', 'do_not_post_substitute_reply')


def inspect(scope, state_directory, client=None, *, reason='not_queried', now=time.time):
    """Build the report. `client` must already be restricted to this worker's own credential."""
    local = read_state(state_directory, scope)
    hub = None
    if client is not None and not local['problems']:
        payload, reason = fetch_status(client, scope)
        if payload is not None:
            hub, reason = hub_view(payload, scope, local['binding'].get('binding_id'))
    elif client is not None:
        reason = 'not_queried_after_local_problem'
    return {'kind': 'ys-memory-codex-recovery-report', 'version': 1, 'generated_at': iso(now()), **FIXED,
            'scope': {k: scope[k] for k in ('project_id', 'session_id', 'worker_id')},
            **classify(local, hub, reason), 'local': local,
            'hub': {'route': 'GET ' + STATUS_ROUTE, 'status_read': hub is not None,
                    'reason': None if hub else reason, 'binding': hub}}


def present(value, full_ids=False):
    """Copy for output. 32-hex identifiers are shortened unless explicitly requested."""
    if isinstance(value, dict):
        return {key: present(item, full_ids) for key, item in value.items()}
    if isinstance(value, list):
        return [present(item, full_ids) for item in value]
    return value[:8] + '...' if is_id(value) and not full_ids else value


TEXT = {
    'title': ('Codex chat recovery report (read-only; receiver and product state unchanged)', 'Codex 對話恢復報告（唯讀，接收器與產品狀態未變更）'),
    'scope': ('Scope: project {project_id}, room {session_id}, worker {worker_id}', '範圍：專案 {project_id}、聊天室 {session_id}、worker {worker_id}'),
    'state': ('State: {state}', '狀態：{state}'),
    'local': ('Local journal', '本機 journal'),
    'hub': ('Hub status ({route})', 'Hub 狀態（{route}）'),
    'meaning': ('What this shows', '這代表什麼'),
    'missing': ('Evidence still missing', '仍缺少的證據'),
    'action': ('Next safe action', '下一步安全作法'),
    'none': ('none', '無'),
    'sep': (', ', '、'),
    'f_sequences': ('sequences {0}-{1}', '序號 {0}-{1}'),
    'f_message_at': ('message {0} at sequence {1}', '訊息 {0}，序號 {1}'),
    'f_written': ('written {0}', '寫入於 {0}'),
    'f_lease_live': ('lease live', '租約仍有效'),
    'f_room_paused': ('room paused', '聊天室已暫停'),
    'f_read': ('read {0}', '讀取於 {0}'),
    'f_reply_at': ('reply {0} at sequence {1}', '回覆 {0}，序號 {1}'),
    'footer': ('This report grants no retry, does not establish that the native process exited, and performs no recovery.',
               '本報告不授權重試、不能證明 native 程序已退出，也不執行任何恢復。'),
    'l_journal_absent': ('state directory absent: this receipt has not started a receiver', '狀態目錄不存在：這份安裝回條尚未啟動過接收器'),
    'l_binding': ('binding       {status}{extra}', 'binding       {status}{extra}'),
    'l_delivery': ('delivery      {status}{extra}', 'delivery      {status}{extra}'),
    'l_completion': ('local receipt {status}{extra}', '執行回條      {status}{extra}'),
    'l_marker': ('native marker {status}{extra}', 'native 標記   {status}{extra}'),
    'l_stop': ('stop file     {status}', 'STOP 檔       {status}'),
    'l_status': ('last status   {status}{extra}', '最後狀態      {status}{extra}'),
    'h_none': ('not read: {reason}', '未讀取：{reason}'),
    'h_binding': ('binding       generation {generation}, status {status}, turns {turns_used}/{max_turns}, cursor {processed_sequence}{extra}',
                  'binding       generation {generation}、狀態 {status}、回合 {turns_used}/{max_turns}、游標 {processed_sequence}{extra}'),
    'h_delivery': ('latest        {delivery_id}, status {status}{extra}', '最新交付      {delivery_id}、狀態 {status}{extra}'),
    'h_no_delivery': ('latest        none for this generation', '最新交付      此 generation 沒有交付'),
    's_server-replied/local-completion-missing': (
        'The Hub recorded a reply for the journaled delivery, but this receiver never saved its receipt. The reply exists in the room; only the local record is missing.',
        'Hub 已記錄此交付的回覆，但接收器沒有存下執行回條。回覆已在聊天室內，缺的只是本機紀錄。'),
    's_server-replied/local-completion-recorded': (
        'The Hub reply and the local receipt name the same message. Nothing is pending for this delivery.',
        'Hub 的回覆與本機的執行回條指向同一則訊息，此交付沒有待處理事項。'),
    's_server-replied/local-completion-mismatch': (
        'The Hub recorded a reply, but the local receipt names a different message. The two records disagree.',
        'Hub 已記錄回覆，但本機的執行回條指向不同的訊息，兩份紀錄不一致。'),
    's_server-read': (
        'The Hub returned the complete messages to a tool call, but recorded no reply. This is a read without a reply, not a completed turn.',
        'Hub 已透過工具回傳完整訊息，但沒有記錄回覆。這是已讀未回，不是完成的回合。'),
    's_unresolved': (
        'The Hub holds the journaled delivery with neither a complete read nor a reply recorded. The outcome is unknown.',
        'Hub 上此交付既沒有完整讀取紀錄，也沒有回覆紀錄，結果未知。'),
    's_unresolved/delivery_not_latest': (
        'The Hub\'s latest delivery for this binding is a different one, so the status route cannot show what happened to the journaled delivery.',
        'Hub 上此 binding 的最新交付是另一筆，狀態路由無法顯示 journal 內這筆交付的結果。'),
    's_unresolved/no_hub_delivery': (
        'The Hub lists no delivery for this binding generation, so the journaled delivery cannot be reconciled through the status route.',
        'Hub 上此 binding generation 沒有任何交付，無法透過狀態路由核對 journal 內的交付。'),
    's_stale-generation': (
        'The Hub binding has moved to another generation. This journal no longer owns it.',
        'Hub 的 binding 已換到另一個 generation，此 journal 已不再擁有它。'),
    's_disconnected': ('The Hub binding is released. Nothing can be delivered under this journal.', 'Hub 的 binding 已釋放，此 journal 之下不會再有交付。'),
    's_unavailable': ('No Hub evidence was read. The local journal alone cannot show whether the delivery was read or replied.',
                      '未取得 Hub 證據。單靠本機 journal 無法判斷交付是否已讀或已回覆。'),
    's_no-delivery': ('The journal holds no dispatched delivery to reconcile.', 'journal 內沒有需要核對的已派送交付。'),
    's_scope-mismatch': ('The journal or the Hub binding belongs to a different project, room or worker than the receipt.',
                         'journal 或 Hub binding 所屬的專案、聊天室或 worker 與安裝回條不同。'),
    's_invalid-local-state': ('A journal file is linked, malformed or oversized, so the journal cannot be trusted as evidence.',
                              'journal 檔案是連結、格式錯誤或過大，無法當作證據。'),
    'm_native_exit_unconfirmed': (
        'Whether the native child exited. The marker names no process, and this report inspects none; a missing, live or dead PID would not settle it.',
        'native 子程序是否已退出。標記不含程序身分，本報告也不檢查程序；PID 不存在、存活或已結束都不足以判定。'),
    'm_hub_status_not_read': ('The Hub status for this binding.', '此 binding 的 Hub 狀態。'),
    'm_local_binding_ownership': ('receiver-binding.json: without it this journal cannot show which binding generation it owned.',
                                  'receiver-binding.json：缺少它，journal 無法顯示自己擁有哪個 binding generation。'),
    'm_journaled_delivery_not_exposed_for_this_generation': (
        'The outcome of the journaled delivery: the status route lists only the latest delivery of the current generation.',
        '此交付的結果：狀態路由只列出目前 generation 的最新交付。'),
    'm_journaled_delivery_is_not_hub_latest': (
        'A Hub record for the journaled delivery: the status route lists a different latest delivery, or none.',
        '此交付在 Hub 的紀錄：狀態路由列出的最新交付是另一筆，或沒有。'),
    'm_hub_latest_delivery_not_in_journal': (
        'A journal entry for the Hub\'s latest delivery: the receiver may have claimed it without recording it.',
        'Hub 最新交付在 journal 內的紀錄：接收器可能已認領卻沒有寫入。'),
    'm_cursor_alone_is_not_reply_evidence': (
        'A reply record. The Hub cursor has passed this delivery, but a cursor alone does not show that a reply was posted.',
        '回覆紀錄。Hub 游標已越過此交付，但單憑游標不能證明已發出回覆。'),
    'm_hub_reply_record': ('A Hub reply record for this delivery.', '此交付在 Hub 的回覆紀錄。'),
    'm_hub_full_read_record': ('A Hub record that the complete messages were read through a tool.', 'Hub 上透過工具完整讀取訊息的紀錄。'),
    'm_local_completion_not_confirmed_by_hub': ('Hub confirmation of the reply that the local receipt claims.', '本機執行回條所稱的回覆在 Hub 上的確認。'),
    'a_keep_state_directory': ('Keep the state directory exactly as it is; it is the evidence.', '原樣保留狀態目錄，它就是證據。'),
    'a_marker_blocks_restart_and_disconnect': (
        'Leave native-active.json in place. It blocks restart and disconnect by design, and removing it needs an administrator decision based on evidence outside this report.',
        '保留 native-active.json。它依設計會擋住重啟與 disconnect；是否移除須由管理員依本報告以外的證據決定。'),
    'a_ask_administrator': ('Stop and ask the Hub administrator before any further step.', '停止操作，先請 Hub 管理員判斷。'),
    'a_rerun_when_hub_reachable': ('Restore access to the Hub with this worker\'s own credential, then run this report again.',
                                   '恢復以此 worker 自己的憑證連到 Hub 後，再執行一次本報告。'),
    'a_provision_new_installation_if_wanted': (
        'If automatic replies are still wanted, provision a new bounded installation; do not reuse or edit this one.',
        '若仍需要自動回覆，請另建新的有限額度安裝；不要重用或修改這一份。'),
    'a_do_not_start_this_receipt': ('Do not start this receipt again.', '不要再用這份安裝回條啟動接收器。'),
    'a_check_room_before_any_action': (
        'Look in the Hub room for a reply from this worker after the delivery\'s last sequence before doing anything else.',
        '採取任何動作前，先到 Hub 聊天室確認此 worker 在該交付最後序號之後是否已有回覆。'),
    'a_do_not_resend_reply_exists': ('Do not resend or post a substitute: the reply is already in the room.', '不要重送或補發：回覆已在聊天室內。'),
    'a_do_not_post_substitute_reply': (
        'Do not post a substitute reply with this delivery\'s fields, and do not strip them to post manually.',
        '不要用此交付的欄位補發回覆，也不要拿掉欄位改成手動發文。'),
}


def render(report, language='en', full_ids=False):
    """Concise text that is safe to share: allowlisted facts and fixed sentences only."""
    column = 1 if language == 'zh-TW' else 0
    shown = present(report, full_ids)
    local, hub = shown['local'], shown['hub']['binding']

    def say(key, *positional, **values):
        return TEXT[key][column].format(*positional, **values)

    def extra(*parts):
        return ''.join(say('sep') + part for part in parts if part)
    label = shown['state'] + (' (' + shown['detail'] + ')' if shown['detail'] else '')
    lines = [say('title'), say('scope', **shown['scope']), say('state', state=label), '', say('local')]
    if local['journal'] == 'absent':
        lines.append('  ' + say('l_journal_absent'))
    else:
        b, d, c, m, s = (local[k] for k in ('binding', 'delivery', 'completion', 'native_marker', 'last_status'))
        lines += ['  ' + say('l_binding', status=b['status'], extra=extra(
                      'generation ' + str(b['generation']) if 'generation' in b else '', b.get('binding_id'))),
                  '  ' + say('l_delivery', status=d['status'], extra=extra(
                      d.get('delivery_id'), say('f_sequences', d['after_sequence'], d['through_sequence'])
                      if 'through_sequence' in d else '')),
                  '  ' + say('l_completion', status=c['status'], extra=extra(
                      say('f_message_at', c['message_id'], c['sequence']) if 'sequence' in c else '')),
                  '  ' + say('l_marker', status=m['status'].upper() if m['status'] == 'present' else m['status'],
                             extra=extra(say('f_written', m['modified_at']) if m.get('modified_at') else '')),
                  '  ' + say('l_stop', status=local['stop']),
                  '  ' + say('l_status', status=s.get('state') or s['status'], extra=extra(s.get('error_code'), s.get('at')))]
    lines += ['', say('hub', route=shown['hub']['route'])]
    if hub is None:
        lines.append('  ' + say('h_none', reason=shown['hub']['reason']))
    else:
        lines.append('  ' + say('h_binding', **{k: '?' if hub[k] is None else hub[k] for k in
            ('generation', 'status', 'turns_used', 'max_turns', 'processed_sequence')},
            extra=extra(say('f_lease_live') if hub['lease_live'] else '', say('f_room_paused') if hub['room_paused'] else '')))
        latest = hub['latest_delivery']
        lines.append('  ' + (say('h_delivery', **latest, extra=extra(
            say('f_read', latest['read_at']) if latest['read_at'] else '',
            say('f_reply_at', latest['reply_message_id'], latest['reply_sequence'])
            if latest['reply_message_id'] else '')) if latest else say('h_no_delivery')))
    key = 's_' + shown['state'] + '/' + str(shown['detail'])
    lines += ['', say('meaning'), '  ' + say(key if key in TEXT else 's_' + shown['state']), '', say('missing')]
    lines += ['  - ' + say('m_' + code) for code in shown['evidence_missing']] or ['  ' + say('none')]
    lines += ['', say('action')] + ['  - ' + say('a_' + code) for code in shown['next_safe_action']]
    return '\n'.join(lines + ['', say('footer')])


def load_sources():
    """The installer and receiver beside this file hold the documented receipt and credential handling."""
    modules = []
    for name, file in (('recovery_inspector_setup', 'setup-codex-chat.py'),
                       ('recovery_inspector_receiver', 'run-codex-chat.py')):
        path = Path(__file__).resolve().with_name(file)
        if linked(path) or not path.is_file():
            raise InspectorError('sibling_installer_sources_required')
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        modules.append(module)
    return modules


def own_client(receipt, runner, timeout):
    """This worker's own protected Token over the pinned CA, behind the status-only transport."""
    directory = Path(receipt['client_directory'])
    _, connection, context, token = runner.credentials({'client_dir': str(directory),
        'expected_ca': receipt['ca_sha256'], 'credential': str(directory / 'worker.dpapi')})
    client = httpx.Client(base_url=connection['endpoint'].removesuffix('/mcp'),
        transport=StatusOnlyTransport(httpx.HTTPTransport(verify=context, trust_env=False)),
        trust_env=False, follow_redirects=False, timeout=timeout, headers={'Authorization': 'Bearer ' + token})
    return client, token


def main(argv=None):
    parser = Parser(description=__doc__)
    parser.add_argument('--receipt', type=Path, required=True, help="The installation's codex-install.json")
    parser.add_argument('--offline', action='store_true', help='Local journal only: no Token read, no Hub request')
    parser.add_argument('--json', action='store_true', dest='as_json', help='Machine-readable report')
    parser.add_argument('--full-ids', action='store_true', help='Complete identifiers, for private reconciliation only')
    parser.add_argument('--language', choices=('en', 'zh-TW'), default='en')
    parser.add_argument('--timeout', type=int, default=10, help='Hub request timeout, 1-30 seconds')
    fixed = (InspectorError,)
    try:
        args = parser.parse_args(argv)
        if not 1 <= args.timeout <= 30:
            raise InspectorError('invalid_arguments_use_help')
        setup, runner = load_sources()
        fixed += (setup.SetupError,)
        receipt = setup.read_receipt(args.receipt)
        scope = {k: receipt[k] for k in ('project_id', 'session_id', 'worker_id')}
        client, token, reason = None, None, 'not_queried'
        if not args.offline:
            try:
                client, token = own_client(receipt, runner, args.timeout)
            except Exception:
                reason = 'own_credential_or_tls_unavailable'
        try:
            report = inspect(scope, Path(receipt['state_directory']), client, reason=reason)
        finally:
            if client is not None:
                client.close()
        text = (json.dumps(present(report, args.full_ids), ensure_ascii=True, indent=2) if args.as_json
                else render(report, args.language, args.full_ids))
        if token and token in text:
            raise InspectorError('redaction_guard_stopped_output')
        if hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(errors='replace')
        print(text)
        return 0
    except Exception as exc:
        print('codex_recovery_inspection_failed: ' + (str(exc) if isinstance(exc, fixed) else type(exc).__name__),
              file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
