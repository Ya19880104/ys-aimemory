<#
Windows / Python 3.12: reviewed project-local Claude MCP + bounded chat setup.
Token is requested privately, never supplied in the URL or command line.
Download and review this script before execution. Five immutable source files
are SHA-256 checked before execution, with their original directory layout.
No global configuration, CA trust, login or permission mode is changed.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$Url,
    [Parameter(Mandatory=$true)][string]$ExpectedCa,
    [Parameter(Mandatory=$true)][string]$Project,
    [Parameter(Mandatory=$true)][string]$ProjectId,
    [Parameter(Mandatory=$true)][string]$SessionId,
    [string]$Language = 'en',
    [int]$Hours = 8,
    [int]$MaxTurns = 20,
    [string]$PythonPath
)
$ErrorActionPreference = 'Stop'

# Publish this immutable revision and these LF source digests as one unit.
$SourceRevision = '0f6e56f0e91275820489c1c6effedf879051a905'
$SourceRoot = 'https://raw.githubusercontent.com/Ya19880104/ys-aimemory/' + $SourceRevision + '/'
$SourceFiles = @(
    @{ Source = 'scripts/setup-chat.py'; Sha256 = 'ef66fb942750abd084df82e0415611860a5f658a908d1aeae2718df06110c108' },
    @{ Source = 'scripts/setup-claude.py'; Sha256 = 'd3c7e1108e624e24d749cb59e0ca06fe0de14d4eab48ef7b74233098a0d24098' },
    @{ Source = 'memory_hub/client_watch.py'; Sha256 = '24fe1bae6b26125d8badc0dde45014d349336bb746010408dbd31e65ad8ba9f4' },
    @{ Source = 'memory_hub/client_chat_bridge.py'; Sha256 = '94703eb72cb587e42a70a996148cc01067afac9a5cc43bf8fee3add77435df2b' },
    @{ Source = 'memory_hub/client_secret.py'; Sha256 = '11f2312b254a1c17761d2adb402f4ed6fc73eaa344a98994c695a6175ea1d469' }
)

# Kept inline so the public entry script contains all orchestration to review.
# No downloaded or existing launcher is executed before ownership checks.
$Bootstrap = @'
import getpass
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import warnings


class BootstrapError(ValueError):
    pass


def checked_file(path, maximum=1048576):
    path = Path(path)
    if any(p.is_symlink() or (hasattr(p, 'is_junction') and p.is_junction())
           for p in (path, *path.parents)):
        raise BootstrapError('linked_path_refused')
    if not path.is_file() or path.stat().st_size > maximum:
        raise BootstrapError('invalid_owned_file')
    return path.read_bytes()


def existing_install(project, source, origin, pin):
    """Read public ownership evidence only; never decrypt or read worker.dpapi."""
    target = project / '.mcp.json'
    if not target.exists() and not target.is_symlink():
        return None
    raw = checked_file(target)
    config = json.loads(raw.decode('utf-8-sig'))
    if not isinstance(config, dict) or not isinstance(config.get('mcpServers', {}), dict):
        raise BootstrapError('invalid_mcp_config_preserved')
    entry = config.get('mcpServers', {}).get('ys_memory')
    if entry is None and 'ys_memory' not in config.get('mcpServers', {}):
        return None
    if not isinstance(entry, dict) or not isinstance(entry.get('args'), list) or len(entry['args']) != 5:
        raise BootstrapError('existing_mcp_not_owned_or_chat_already_bound')
    launcher = Path(entry['args'][1])
    if not launcher.is_absolute() or launcher.name != 'launcher.py':
        raise BootstrapError('existing_mcp_not_owned_or_chat_already_bound')
    launcher_bytes = checked_file(launcher)
    directory = launcher.parent.resolve(strict=True)
    receipt = json.loads(checked_file(directory / 'install-receipt.json'))
    expected_entry = {'command': str(directory / '.venv' / 'Scripts' / 'python.exe'),
                      'args': ['-B', str(directory / 'launcher.py'), '--config',
                               str(directory / 'connection.json'), '--compact']}
    # Current adapter emits type=stdio; older owned receipts omit it. Both
    # exact shapes still require the original complete configuration digest.
    if 'type' in entry:
        expected_entry['type'] = 'stdio'
    if (entry != expected_entry
            or receipt.get('status') != 'installed_not_native_verified'
            or Path(receipt.get('project', '')).resolve() != project
            or Path(receipt.get('client_directory', '')).resolve() != directory
            or receipt.get('config_sha256') != hashlib.sha256(raw).hexdigest()
            or receipt.get('ca_sha256') != pin
            or receipt.get('global_config_changed') is not False
            or launcher_bytes != checked_file(source / 'memory_hub' / 'client_secret.py')):
        raise BootstrapError('existing_mcp_ownership_verification_failed')
    connection = json.loads(checked_file(directory / 'connection.json'))
    if connection != {'version': 1, 'endpoint': origin + '/mcp',
                      'ca_file': 'ys-ai-memory-ca.crt', 'ca_sha256': pin}:
        raise BootstrapError('existing_mcp_hub_or_ca_mismatch')
    # Metadata only: bootstrap does not consume the existing encrypted Token.
    credential = directory / 'worker.dpapi'
    if (not credential.is_file() or credential.is_symlink()
            or not 0 < credential.stat().st_size <= 16384):
        raise BootstrapError('existing_encrypted_worker_missing')
    checked_file(directory / '.venv' / 'Scripts' / 'python.exe', 20 * 1048576)
    binding = directory / 'chat-binding.json'
    if binding.exists() and not json.loads(checked_file(binding)).get('disconnected_at'):
        raise BootstrapError('chat_already_bound_disconnect_first')
    return directory


def verify_bundle(directory, bundle):
    if directory is not None:
        # Authenticate executable bridge/dependencies with the pinned-CA HTTPS
        # bundle before the existing installer imports or invokes anything.
        for name in ('bridge.py', 'connection.json', 'ys-ai-memory-ca.crt', 'requirements.lock'):
            if checked_file(directory / name) != checked_file(bundle / name):
                raise BootstrapError('owned_install_differs_from_verified_hub_bundle')


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run(source, url, expected_ca, project, project_id, session_id, language, hours, max_turns):
    source, project = Path(source).resolve(strict=True), Path(project).resolve(strict=True)
    if os.name != 'nt' or sys.version_info[:2] != (3, 12) or not project.is_dir():
        raise BootstrapError('windows_python312_and_existing_project_required')
    if language not in ('en', 'zh-TW') or not 1 <= hours <= 8 or not 1 <= max_turns <= 100:
        raise BootstrapError('invalid_language_or_budget')
    if any(not value or len(value) > 160 or any(ord(c) < 32 for c in value)
           for value in (project_id, session_id)):
        raise BootstrapError('invalid_project_or_room')
    setup = load('ys_verified_setup', source / 'scripts' / 'setup-claude.py')
    chat = load('ys_verified_chat_setup', source / 'scripts' / 'setup-chat.py')
    origin, pin = setup.hub_origin(url), setup.ca_pin(expected_ca)
    directory = existing_install(project, source, origin, pin)
    bundle = setup.download_bundle(origin, pin, source / 'verified-bundle')
    verify_bundle(directory, bundle)
    # Recheck after network I/O; another tool may have changed configuration.
    if existing_install(project, source, origin, pin) != directory:
        raise BootstrapError('configuration_changed_preserved')
    if directory is None:
        if not sys.stdin.isatty():
            raise BootstrapError('interactive_terminal_required_for_private_token_prompt')
        with warnings.catch_warnings():
            warnings.simplefilter('error', getpass.GetPassWarning)
            token = getpass.getpass('Your Claude worker Token (hidden): ')
        try:
            setup.install(bundle, project, pin, token)
        finally:
            token = None
        directory = existing_install(project, source, origin, pin)
        if directory is None:
            raise BootstrapError('installation_receipt_missing')
    verify_bundle(directory, bundle)
    receipt = chat.configure(project, project_id, session_id, language=language,
                             hours=hours, max_turns=max_turns)
    receipt['bootstrap_sources'] = str(source)
    receipt['lifecycle_script'] = str(source / 'scripts' / 'setup-chat.py')
    # Disconnect imports httpx: use the owned environment, not a bare system Python.
    receipt['lifecycle_python'] = str(directory / '.venv' / 'Scripts' / 'python.exe')
    receipt['native_acceptance'] = 'not_run'
    (source / 'chat-bootstrap-receipt.json').write_text(
        json.dumps(receipt, ensure_ascii=True, indent=2), encoding='utf-8')
    return receipt


if __name__ == '__main__':
    try:
        result = run(*sys.argv[1:8], int(sys.argv[8]), int(sys.argv[9]))
        print(json.dumps(result, ensure_ascii=True, indent=2))
    except Exception as exc:
        # Only fixed local codes may be printed; remote/JSON/OS errors can echo input.
        code = str(exc) if isinstance(exc, BootstrapError) else type(exc).__name__
        print('chat_bootstrap_failed: ' + code, file=sys.stderr)
        raise SystemExit(1)
'@

try {
    if ($env:OS -ne 'Windows_NT') { throw 'Unsupported platform' }
    $Pin = $ExpectedCa.Replace(':', '').ToLowerInvariant()
    if ($Pin -notmatch '^[0-9a-f]{64}$') { throw 'Invalid public CA fingerprint' }
    $HubUri = $null
    if (-not [Uri]::TryCreate($Url, [UriKind]::Absolute, [ref]$HubUri) -or
        $HubUri.Scheme -ne 'https' -or $HubUri.UserInfo -or $HubUri.Query -or $HubUri.Fragment -or
        $HubUri.AbsolutePath -ne '/' -or $Url -match '[\s\\]') { throw 'Invalid Hub URL' }
    if ($Language -cnotin @('en', 'zh-TW') -or $Hours -lt 1 -or $Hours -gt 8 -or
        $MaxTurns -lt 1 -or $MaxTurns -gt 100) { throw 'Invalid language or budget' }
    foreach ($Value in @($ProjectId, $SessionId)) {
        if (-not $Value -or $Value.Length -gt 160 -or $Value -match '[\x00-\x1f]') { throw 'Invalid project or room' }
    }
    $ProjectPath = (Resolve-Path -LiteralPath $Project).Path
    if (-not (Test-Path -LiteralPath $ProjectPath -PathType Container)) { throw 'Invalid project directory' }
    $PythonCommand = $null
    $PythonArguments = @()
    if ($PythonPath) {
        $PythonCommand = (Resolve-Path -LiteralPath $PythonPath).Path
    } else {
        $PythonLauncher = Get-Command py.exe -ErrorAction SilentlyContinue
        if ($PythonLauncher) {
            & $PythonLauncher.Source -3.12 -c 'import sys; sys.exit(sys.version_info[:2] != (3,12))' 2>$null
            if ($LASTEXITCODE -eq 0) {
                $PythonCommand = $PythonLauncher.Source
                $PythonArguments = @('-3.12')
            }
        }
        if (-not $PythonCommand) {
            $PythonExecutable = Get-Command python.exe -ErrorAction SilentlyContinue
            if ($PythonExecutable) { $PythonCommand = $PythonExecutable.Source }
        }
    }
    if (-not $PythonCommand) { throw 'Python unavailable' }
    & $PythonCommand @PythonArguments -c 'import sys; sys.exit(sys.version_info[:2] != (3,12))' 2>$null
    if ($LASTEXITCODE -ne 0) { throw 'Python 3.12 required' }
    $SetupDirectory = Join-Path $env:LOCALAPPDATA ('YS-AIMemory\setup\' + [Guid]::NewGuid().ToString('N'))
    [void][IO.Directory]::CreateDirectory($SetupDirectory)
    Add-Type -AssemblyName System.Net.Http
    $Handler = [System.Net.Http.HttpClientHandler]::new()
    $Handler.AllowAutoRedirect = $false
    $Handler.UseProxy = $false
    $Client = [System.Net.Http.HttpClient]::new($Handler)
    $Client.Timeout = [TimeSpan]::FromSeconds(30)
    $Client.MaxResponseContentBufferSize = 1048576
    try {
        foreach ($File in $SourceFiles) {
            $Response = $Client.GetAsync($SourceRoot + $File.Source).GetAwaiter().GetResult()
            try {
                if ([int]$Response.StatusCode -ne 200) { throw 'Installer download unavailable' }
                $Bytes = $Response.Content.ReadAsByteArrayAsync().GetAwaiter().GetResult()
                $Hasher = [Security.Cryptography.SHA256]::Create()
                try { $Digest = [BitConverter]::ToString($Hasher.ComputeHash($Bytes)).Replace('-', '').ToLowerInvariant() }
                finally { $Hasher.Dispose() }
                if ($Digest -ne $File.Sha256) { throw 'Installer source verification failed' }
                $Target = Join-Path $SetupDirectory $File.Source
                [void][IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($Target))
                $Stream = [IO.File]::Open($Target, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write)
                try { $Stream.Write($Bytes, 0, $Bytes.Length) } finally { $Stream.Dispose() }
            } finally { $Response.Dispose() }
        }
    } finally {
        $Client.Dispose()
        $Handler.Dispose()
    }
    # Execute a local file, avoiding native multiline argument quoting differences
    # between Windows PowerShell 5.1 and PowerShell 7. Token input keeps the console.
    $BootstrapPath = Join-Path $SetupDirectory 'bootstrap-chat.py'
    [IO.File]::WriteAllText($BootstrapPath, $Bootstrap, [Text.UTF8Encoding]::new($false))
    & $PythonCommand @PythonArguments $BootstrapPath $SetupDirectory $Url $Pin $ProjectPath $ProjectId $SessionId $Language $Hours $MaxTurns
    if ($LASTEXITCODE -ne 0) { throw 'Project chat setup failed' }
    Write-Host 'Configuration only; native acceptance is NOT RUN. Reload project hooks/MCP, then paste activation_prompt into the intended Claude conversation.'
} catch {
    # Never echo supplied URLs, credentials or remote exception text.
    Write-Error 'Chat setup failed. Check Windows/Python 3.12, the project, Hub URL/CA fingerprint, room IDs and network. Existing unverified settings are preserved. For an active chat use its reviewed setup-chat.py --disconnect first; do not delete config. A completed MCP install may remain if chat setup failed.'
    exit 1
}
