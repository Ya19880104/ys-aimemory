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


def configure(project, project_id, session_id, native_session_id=None, *, display_name='Claude',
              hours=8, max_turns=20, after_sequence=0, language='en'):
    project = Path(project).resolve(strict=True)
    if not 1 <= hours <= 8 or not 1 <= max_turns <= 100 or after_sequence < 0:
        raise ValueError('invalid_budget')
    if language not in {'en', 'zh-TW'}:
        raise ValueError('invalid_language')
    for identifier in (project_id, session_id, native_session_id or 'unbound', display_name):
        if not identifier or len(identifier) > 160 or any(ord(c) < 32 for c in identifier):
            raise ValueError('invalid_identifier')
    entry = json.loads((project / '.mcp.json').read_text(encoding='utf-8-sig'))['mcpServers']['ys_memory']
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
        raise ValueError('existing_binding_review_before_rebinding')
    spec = importlib.util.spec_from_file_location('ys_chat_secret', launcher)
    secret = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(secret)
    if original:
        (directory / 'previous-claude-settings.dpapi').write_bytes(secret.transform(original))
    shutil.copyfile(Path(__file__).resolve().parents[1] / 'memory_hub/client_watch.py', watcher)
    binding = {'version': 1, 'client': 'claude', 'display_name': display_name,
        'project_id': project_id, 'session_id': session_id, 'native_session_id': native_session_id,
        'project_path': str(project), 'language': language,
        'after_sequence': after_sequence, 'max_turns': max_turns,
        'expires_at': time.time() + hours * 3600, 'ttl_seconds': hours * 3600,
        'idempotency_key': 'chat-' + uuid.uuid4().hex}
    if not native_session_id:
        binding['activation_phrase'] = 'YS_MEMORY_JOIN_' + uuid.uuid4().hex
    binding_path.write_text(json.dumps(binding, ensure_ascii=True, indent=2), encoding='utf-8')
    hooks.append({'hooks': [{'type': 'command', 'command': entry['command'],
        'args': [str(watcher)], 'async': True, 'asyncRewake': True, 'timeout': hours * 3600 + 30}]})
    candidate = (json.dumps(config, ensure_ascii=True, indent=2) + '\n').encode()
    if (target.read_bytes() if target.exists() else None) != original:
        raise ValueError('settings_changed_preserved')
    target.parent.mkdir(parents=True, exist_ok=True)
    pending = target.with_name('.chat-' + uuid.uuid4().hex + '.tmp')
    try:
        with pending.open('xb') as out:
            out.write(candidate)
        os.replace(pending, target)
    finally:
        pending.unlink(missing_ok=True)
    return {'status': 'configured_waiting_for_native_hook', 'project': str(project),
        'native_session_id': native_session_id, 'session_id': session_id,
        'expires_at': binding['expires_at'], 'max_turns': max_turns,
        'settings_sha256': hashlib.sha256(candidate).hexdigest(),
        'stop_file': str(directory / 'STOP'), 'global_settings_changed': False,
        'activation_prompt': ('I authorize automatic chat only in the configured YS Memory room, '
            'within the displayed time and turn budget. Reply with exactly this single line and no tools: '
            + binding['activation_phrase']) if not native_session_id else None,
        'notice': 'Resume this exact Claude conversation after reloading hooks; verify online state in Hub.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, default=Path.cwd())
    parser.add_argument('--project-id', required=True)
    parser.add_argument('--session-id', required=True)
    parser.add_argument('--native-session-id')
    parser.add_argument('--display-name', default='Claude')
    parser.add_argument('--hours', type=int, default=8)
    parser.add_argument('--max-turns', type=int, default=20)
    parser.add_argument('--after-sequence', type=int, default=0)
    parser.add_argument('--language', choices=('en', 'zh-TW'), default='en')
    args = parser.parse_args()
    try:
        print(json.dumps(configure(**vars(args)), ensure_ascii=True, indent=2))
        return 0
    except Exception as exc:
        print('chat_setup_failed: ' + type(exc).__name__, file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
