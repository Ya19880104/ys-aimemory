<#
Windows / Python 3.12: install a dedicated Codex CLI chat receiver without a clone.
Default/-Print provisions only. -Run explicitly starts bounded model turns.
Your own worker Token is requested privately; no Token URL/argument is accepted.
Existing Claude, Codex Desktop conversations and global configuration stay unchanged.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$Url,
    [Parameter(Mandatory=$true)][string]$ExpectedCa,
    [Parameter(Mandatory=$true)][string]$ProjectId,
    [Parameter(Mandatory=$true)][string]$SessionId,
    [Parameter(Mandatory=$true)][string]$WorkerId,
    [string]$Language = 'en',
    [int]$Hours = 1,
    [int]$MaxTurns = 20,
    [int]$TurnTimeout = 90,
    [string]$CodexPath,
    [string]$PythonPath,
    [switch]$Print,
    [switch]$Run
)
$ErrorActionPreference = 'Stop'

$SourceRevision = '5b54867a4204e8218a541b7d87039a2700bf22ac'
$SourceRoot = 'https://raw.githubusercontent.com/Ya19880104/ys-aimemory/' + $SourceRevision + '/'
$SourceFiles = @(
    @{ Source = 'scripts/setup-codex-chat.py'; Sha256 = '1eddd494f78bebcd9d85d6e998fd1f9b12868c633e2113f4ff71d7b92068f0e3' },
    @{ Source = 'scripts/setup-claude.py'; Sha256 = '19c46cdf351f7427124743a208f3517975a540325f912ff7d79bd4d86cc8fd24' },
    @{ Source = 'scripts/run-codex-chat.py'; Sha256 = 'ac04790388cc0a53415dee21f3258227cfeb14e7bd8118f270fe8d8af89dbaff' },
    @{ Source = 'memory_hub/client_secret.py'; Sha256 = '11f2312b254a1c17761d2adb402f4ed6fc73eaa344a98994c695a6175ea1d469' }
)

try {
    if ($env:OS -ne 'Windows_NT') { throw 'Unsupported platform' }
    $Pin = $ExpectedCa.Replace(':', '').ToLowerInvariant()
    if ($Pin -notmatch '^[0-9a-f]{64}$') { throw 'Invalid public CA fingerprint' }
    $HubUri = $null
    if (-not [Uri]::TryCreate($Url, [UriKind]::Absolute, [ref]$HubUri) -or
        $HubUri.Scheme -ne 'https' -or $HubUri.UserInfo -or $HubUri.Query -or $HubUri.Fragment -or
        $HubUri.AbsolutePath -ne '/' -or $Url -match '[\s\\]') { throw 'Invalid Hub URL' }
    if ($ProjectId -notmatch '^[a-zA-Z0-9_.-]{1,128}$' -or $SessionId -cnotmatch '^[0-9a-f]{32}$' -or
        -not $WorkerId.Trim() -or $WorkerId.Length -gt 128 -or $WorkerId -match '[\x00-\x1f]') { throw 'Invalid scope' }
    if ($Language -cnotin @('en', 'zh-TW') -or $Hours -lt 1 -or $Hours -gt 8 -or
        $MaxTurns -lt 1 -or $MaxTurns -gt 100 -or $TurnTimeout -lt 30 -or $TurnTimeout -gt 240 -or
        ($Run -and $Print)) { throw 'Invalid budget or action' }
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
                if ([int]$Response.StatusCode -ne 200) { throw 'Source download unavailable' }
                $Bytes = $Response.Content.ReadAsByteArrayAsync().GetAwaiter().GetResult()
                $Hasher = [Security.Cryptography.SHA256]::Create()
                try { $Digest = [BitConverter]::ToString($Hasher.ComputeHash($Bytes)).Replace('-', '').ToLowerInvariant() }
                finally { $Hasher.Dispose() }
                if ($Digest -ne $File.Sha256) { throw 'Source verification failed' }
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
    $InstallerArguments = @('--url', $Url, '--expected-ca', $Pin, '--project-id', $ProjectId,
        '--session-id', $SessionId, '--worker-id', $WorkerId, '--language', $Language,
        '--hours', $Hours, '--max-turns', $MaxTurns, '--turn-timeout', $TurnTimeout)
    if ($CodexPath) { $InstallerArguments += @('--codex', (Resolve-Path -LiteralPath $CodexPath).Path) }
    if ($Run) { $InstallerArguments += '--run' } else { $InstallerArguments += '--print' }
    & $PythonCommand @PythonArguments (Join-Path $SetupDirectory 'scripts/setup-codex-chat.py') @InstallerArguments
    if ($LASTEXITCODE -ne 0) { throw 'Dedicated Codex installation or receiver stopped' }
} catch {
    # Do not print supplied arguments, errors from remote services or credentials.
    Write-Error 'Codex chat setup stopped. Check Windows/Python 3.12, official Codex CLI on PATH, trusted Hub URL/CA, dedicated worker and room IDs, budgets and network. Use -CodexPath/-PythonPath for verified executables. Existing client settings are not overwritten. Inspect the fixed codex_setup_failed code if present.'
    exit 1
}
