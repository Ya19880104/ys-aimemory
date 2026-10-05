"""Bind one local Claude Code conversation to durable shared-room notifications."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import time
import uuid


class ChatSetupError(ValueError):
    """Fixed, non-secret code; an unproven Hub state is never reported as disconnected."""


def write_checked(path, original, candidate):
    if (path.read_bytes() if path.exists() else None) != original:
        raise ValueError('configuration_changed_preserved')
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_name('.chat-' + uuid.uuid4().hex + '.tmp')
    try:
        with pending.open('xb') as out:
            out.write(candidate)
        os.replace(pending, path)
    finally:
        pending.unlink(missing_ok=True)


def listener_stopped(watcher, path):
    """After STOP, hold the listener lock so no watcher join can race the Hub fence."""
    deadline = time.monotonic() + 40
    while True:
        lock = watcher.exclusive(path)
        if lock.__enter__():
            return lock
        lock.__exit__(None, None, None)
        if time.monotonic() >= deadline:
            raise ChatSetupError('listener_still_stopping_retry_disconnect')
        time.sleep(0.2)


def release_binding(client, binding, state):
    """Locate this worker's own binding in the bound room; prove its generation fence.

    The identity comes from a non-mutating Hub check, never local files. A
    recorded binding_id/generation is only a cross-check and must agree."""
    import httpx
    scope = {k: binding[k] for k in ('project_id', 'session_id')}
    try:
        identity = client.post('/v1/tools/get_worker_inbox', json={'arguments': {'project_id': scope['project_id']}})
        identity.raise_for_status()
        worker = identity.json().get('worker_id')
    except (httpx.HTTPError, ValueError, AttributeError):
        worker = None
    if not isinstance(worker, str) or not worker:
        raise ChatSetupError('chat_identity_unverified')
    known = state.get('binding_id') if isinstance(state.get('binding_id'), str) else None
    generation = state.get('generation') if type(state.get('generation')) is int else None

    def own():
        response = client.get('/v1/chat/status', params=scope)
        response.raise_for_status()
        room = response.json()
        mine = [p for p in room['participants'] if p.get('worker_id') == worker
                and all(p.get(k) == v for k, v in scope.items())]
        if not mine and room.get('has_more') is not False:
            raise ChatSetupError('disconnect_not_confirmed')
        if len(mine) > 1 or known is not None and [p.get('binding_id') for p in mine] != [known]:
            raise ChatSetupError('binding_ownership_mismatch')
        return mine[0] if mine else None

    def released(participant):
        return participant.get('released_at') is not None and participant.get('enabled') is False

    current = own()
    if current is None:
        return 'absent'  # Never joined: no Hub binding of this worker exists in the room.
    if released(current):
        return 'released'
    if generation is not None and current.get('generation') != generation:
        raise ChatSetupError('binding_generation_changed')
    try:
        client.post('/v1/chat/disconnect', json={'project_id': scope['project_id'],
            'binding_id': current['binding_id'], 'expected_version': current['version']}).raise_for_status()
    except httpx.HTTPError:
        pass  # A lost response can follow a committed fence: read back, never replay stale CAS.
    after = own()
    if after is None or not released(after) or after.get('generation') != current['generation'] + 1:
        raise ChatSetupError('disconnect_not_confirmed')
    return 'released'


def disconnect(project):
    """Fence this worker's own Hub binding with readback, then restore only our project configuration."""
    import httpx
    project = Path(project).resolve(strict=True)
    mcp_path = project / '.mcp.json'
    original_mcp = mcp_path.read_bytes()
    mcp = json.loads(original_mcp.decode('utf-8-sig'))
    entry = mcp['mcpServers']['ys_memory']
    candidates = [Path(value) for value in entry['args'] if str(value).endswith(('chat-bridge.py','launcher.py'))]
    if len(candidates) != 1:
        raise ValueError('unknown_chat_installation')
    directory = candidates[0].resolve(strict=True).parent
    receipt = json.loads((directory/'install-receipt.json').read_text(encoding='utf-8'))
    if Path(receipt['project']).resolve() != project or Path(receipt['client_directory']).resolve() != directory:
        raise ValueError('installation_project_mismatch')
    binding_path = directory/'chat-binding.json'
    binding = json.loads(binding_path.read_text(encoding='utf-8'))
    if binding.get('disconnected_at'):
        return {'status':'already_disconnected','directory':str(directory)}
    (directory/'STOP').touch()
    spec = importlib.util.spec_from_file_location('stop_chat_secret', directory/'launcher.py')
    secret = importlib.util.module_from_spec(spec);spec.loader.exec_module(secret)
    spec = importlib.util.spec_from_file_location('stop_chat_bridge', directory/'bridge.py')
    bridge = importlib.util.module_from_spec(spec);spec.loader.exec_module(bridge)
    spec = importlib.util.spec_from_file_location('stop_chat_watch', directory/'watch.py')
    watcher = importlib.util.module_from_spec(spec);spec.loader.exec_module(watcher)
    lock = listener_stopped(watcher, directory/'chat-listener.lock')
    try:
        # Read after the listener exited: its final status write is visible.
        try:
            state = json.loads((directory/'chat-status.json').read_text(encoding='utf-8'))
        except (OSError, ValueError):
            state = {}  # Absent or unreadable; the Hub lookup stays authoritative.
        try:
            connection = bridge.load_connection(directory/'connection.json')
            token = secret.transform((directory/'worker.dpapi').read_bytes(),decrypt=True).decode('ascii')
            with httpx.Client(base_url=connection['endpoint'].removesuffix('/mcp'),
                    verify=bridge.verified_context(connection),trust_env=False,follow_redirects=False,timeout=10,
                    headers={'Authorization':'Bearer '+token}) as client:
                hub_binding = release_binding(client, binding, state if isinstance(state, dict) else {})
        except ChatSetupError:
            raise
        except Exception as exc:
            raise ChatSetupError('disconnect_not_confirmed') from exc
        old_mcp = json.loads(secret.transform((directory/'previous-chat-mcp.dpapi').read_bytes(),decrypt=True).decode('utf-8-sig'))
        # Do not overwrite another installation that replaced this specific entry.
        if entry != {'command':old_mcp['mcpServers']['ys_memory']['command'],'args':[str(directory/'chat-bridge.py')]}:
            raise ValueError('mcp_entry_changed_preserved')
        mcp['mcpServers']['ys_memory'] = old_mcp['mcpServers']['ys_memory']
        settings_path = project/'.claude/settings.local.json'
        original_settings = settings_path.read_bytes()
        settings = json.loads(original_settings.decode('utf-8-sig'))
        stops = settings.get('hooks',{}).get('Stop',[])
        for group in stops:
            group['hooks'] = [h for h in group.get('hooks',[]) if h.get('args') != [str(directory/'watch.py')]]
        settings.setdefault('hooks',{})['Stop'] = [g for g in stops if g.get('hooks')]
        old_settings_path = directory/'previous-claude-settings.dpapi'
        old_settings = json.loads(secret.transform(old_settings_path.read_bytes(),decrypt=True).decode('utf-8-sig')) if old_settings_path.exists() else {}
        old_rules = old_settings.get('permissions',{}).get('allow',[])
        owned = {'mcp__ys_memory__'+n for n in ('chat_status','chat_read','chat_reply','chat_no_reply')}
        allow = settings.get('permissions',{}).get('allow',[])
        if 'permissions' in settings:
            settings['permissions']['allow'] = [r for r in allow if r not in owned or r in old_rules]
        write_checked(mcp_path,original_mcp,(json.dumps(mcp,ensure_ascii=True,indent=2)+'\n').encode())
        write_checked(settings_path,original_settings,(json.dumps(settings,ensure_ascii=True,indent=2)+'\n').encode())
        binding['disconnected_at'] = time.time()
        binding_path.write_text(json.dumps(binding,indent=2),encoding='utf-8')
    finally:
        lock.__exit__(None, None, None)
    return {'status':'disconnected','directory':str(directory),'hub_binding':hub_binding,'global_settings_changed':False}


def configure(project, project_id, session_id, native_session_id=None, *, display_name='Claude',
              hours=8, max_turns=20, after_sequence=None, language='en'):
    project = Path(project).resolve(strict=True)
    if not 1 <= hours <= 8 or not 1 <= max_turns <= 100 or (after_sequence is not None and after_sequence < 0):
        raise ValueError('invalid_budget')
    if language not in {'en', 'zh-TW'}:
        raise ValueError('invalid_language')
    for identifier in (project_id, session_id, native_session_id or 'unbound', display_name):
        if not identifier or len(identifier) > 160 or any(ord(c) < 32 for c in identifier):
            raise ValueError('invalid_identifier')
    mcp_path = project / '.mcp.json'
    if mcp_path.is_symlink():
        raise ValueError('mcp_symlink_not_supported')
    original_mcp = mcp_path.read_bytes()
    mcp_config = json.loads(original_mcp.decode('utf-8-sig'))
    entry = mcp_config['mcpServers']['ys_memory']
    launcher = Path(entry['args'][1]).resolve(strict=True)
    directory = launcher.parent
    if launcher.name != 'launcher.py' or not (directory / 'worker.dpapi').is_file():
        raise ValueError('use_verified_claude_setup_first')
    receipt = json.loads((directory / 'install-receipt.json').read_text(encoding='utf-8'))
    if Path(receipt['project']).resolve() != project or Path(receipt['client_directory']).resolve() != directory:
        raise ValueError('installation_does_not_belong_to_this_project')
    target = project / '.claude' / 'settings.local.json'
    if target.is_symlink() or target.parent.is_symlink():
        raise ValueError('settings_symlink_not_supported')
    original = target.read_bytes() if target.exists() else None
    config = json.loads(original.decode('utf-8-sig')) if original else {}
    hooks = config.setdefault('hooks', {}).setdefault('Stop', [])
    if not isinstance(hooks, list):
        raise ValueError('invalid_stop_hooks')
    watcher = directory / 'watch.py'
    if any(str(watcher).replace('\\', '/') in json.dumps(item).replace('\\\\', '/') for item in hooks):
        raise ValueError('already_bound_stop_before_rebinding')
    binding_path = directory / 'chat-binding.json'
    if binding_path.exists():
        retired = json.loads(binding_path.read_text(encoding='utf-8'))
        if not retired.get('disconnected_at'):
            raise ValueError('existing_binding_review_before_rebinding')
        # Preserve retired evidence inside this verified client directory.
        suffix = '.retired-' + uuid.uuid4().hex + '.json'
        for name in ('chat-binding.json','chat-status.json','chat-delivery.json','chat-install.json'):
            path = directory/name
            if path.exists():
                path.rename(directory/(path.stem+suffix))
    spec = importlib.util.spec_from_file_location('ys_chat_secret', launcher)
    secret = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(secret)
    if original:
        (directory / 'previous-claude-settings.dpapi').write_bytes(secret.transform(original))
    (directory / 'previous-chat-mcp.dpapi').write_bytes(secret.transform(original_mcp))
    shutil.copyfile(Path(__file__).resolve().parents[1] / 'memory_hub/client_watch.py', watcher)
    chat_bridge = directory / 'chat-bridge.py'
    shutil.copyfile(Path(__file__).resolve().parents[1] / 'memory_hub/client_chat_bridge.py', chat_bridge)
    binding = {'version': 1, 'client': 'claude', 'display_name': display_name,
        'project_id': project_id, 'session_id': session_id, 'native_session_id': native_session_id,
        'project_path': str(project), 'language': language,
        'after_sequence': after_sequence, 'max_turns': max_turns,
        'expires_at': time.time() + hours * 3600, 'ttl_seconds': hours * 3600,
        'idempotency_key': 'chat-' + uuid.uuid4().hex}
    if not native_session_id:
        binding['activation_phrase'] = 'YS_MEMORY_JOIN_' + uuid.uuid4().hex
    hooks.append({'hooks': [{'type': 'command', 'command': entry['command'],
        'args': [str(watcher)], 'async': True, 'asyncRewake': True, 'timeout': hours * 3600 + 30}]})
    allows = config.setdefault('permissions', {}).setdefault('allow', [])
    if not isinstance(allows, list):
        raise ValueError('invalid_project_tool_permissions')
    for tool in ('chat_status','chat_read','chat_reply','chat_no_reply'):
        rule = 'mcp__ys_memory__' + tool
        if rule not in allows:
            allows.append(rule)
    mcp_config['mcpServers']['ys_memory'] = {'command':entry['command'], 'args':[str(chat_bridge)]}
    candidate_mcp = (json.dumps(mcp_config, ensure_ascii=True, indent=2) + '\n').encode()
    candidate = (json.dumps(config, ensure_ascii=True, indent=2) + '\n').encode()
    try:
        write_checked(mcp_path, original_mcp, candidate_mcp)
        binding_path.write_text(json.dumps(binding, ensure_ascii=True, indent=2), encoding='utf-8')
        write_checked(target, original, candidate)
    except Exception:
        if mcp_path.read_bytes() == candidate_mcp:
            write_checked(mcp_path, candidate_mcp, original_mcp)
        (directory/'STOP').touch()
        if binding_path.exists():
            binding['disconnected_at'] = time.time()
            binding_path.write_text(json.dumps(binding,indent=2),encoding='utf-8')
        raise
    (directory / 'chat-install.json').write_text(json.dumps({
        'mcp_sha256':hashlib.sha256(candidate_mcp).hexdigest(),
        'settings_sha256':hashlib.sha256(candidate).hexdigest(),
        'settings_existed':original is not None}),encoding='utf-8')
    (directory/'STOP').unlink(missing_ok=True)
    return {'status': 'configured_waiting_for_native_hook', 'project': str(project),
        'native_session_id': native_session_id, 'session_id': session_id,
        'expires_at': binding['expires_at'], 'max_turns': max_turns,
        'settings_sha256': hashlib.sha256(candidate).hexdigest(),
        'stop_file': str(directory / 'STOP'), 'global_settings_changed': False,
        'mcp_scope':'Only chat_status/chat_read/chat_reply/chat_no_reply in the configured room; normal memory tools restored on disconnect.',
        'activation_prompt': ('I authorize automatic chat only in the configured YS Memory room, '
            'within the displayed time and turn budget. Reply with exactly this single line and no tools: '
            + binding['activation_phrase']) if not native_session_id else None,
        'notice': 'Resume this exact Claude conversation after reloading hooks; verify online state in Hub.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, default=Path.cwd())
    parser.add_argument('--project-id')
    parser.add_argument('--session-id')
    lifecycle = parser.add_mutually_exclusive_group()
    lifecycle.add_argument('--disconnect', action='store_true')
    lifecycle.add_argument('--renew', action='store_true')
    parser.add_argument('--native-session-id')
    parser.add_argument('--display-name', default='Claude')
    parser.add_argument('--hours', type=int, default=8)
    parser.add_argument('--max-turns', type=int, default=20)
    parser.add_argument('--after-sequence', type=int)
    parser.add_argument('--language', choices=('en', 'zh-TW'), default='en')
    args = parser.parse_args()
    try:
        if not args.disconnect and (not args.project_id or not args.session_id):
            raise ValueError('project_and_session_required')
        if args.disconnect or args.renew:
            disconnected = disconnect(args.project)
            if args.disconnect:
                print(json.dumps(disconnected,ensure_ascii=True,indent=2))
                return 0
        values = vars(args).copy()
        values.pop('disconnect');values.pop('renew')
        print(json.dumps(configure(**values), ensure_ascii=True, indent=2))
        return 0
    except Exception as exc:
        print('chat_setup_failed: ' + (str(exc) if isinstance(exc, ChatSetupError) else type(exc).__name__), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
