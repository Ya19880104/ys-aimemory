<#
Run from the Claude project directory. Requires Windows and Python 3.12.
  .\connect-claude.ps1 -Url https://YOUR-HUB -ExpectedCa TRUSTED_PUBLIC_CA_SHA256
Optional: -Project C:\Projects\Example -PythonPath C:\Python312\python.exe
Token is requested privately by the installer, never passed in a URL/argument.
This downloads exactly two public source files from an immutable Git revision,
checks their SHA-256 values, then invokes the URL installer. No global config,
CA trust, execution policy, Claude login or tool permission is changed.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$Url,
    [Parameter(Mandatory=$true)][string]$ExpectedCa,
    [string]$Project = (Get-Location).Path,
    [string]$PythonPath
)
$ErrorActionPreference = 'Stop'

# Keep this revision and both digests together when publishing a new installer.
$SourceRevision = 'ee21c2dfccba1d7f60b44563880c8b6a864bf971'
$SourceRoot = 'https://raw.githubusercontent.com/Ya19880104/ys-aimemory/' + $SourceRevision + '/'
$SourceFiles = @(
    @{ Source = 'scripts/setup-claude.py'; Name = 'setup-claude.py'; Sha256 = '19c46cdf351f7427124743a208f3517975a540325f912ff7d79bd4d86cc8fd24' },
    @{ Source = 'memory_hub/client_secret.py'; Name = 'client_secret.py'; Sha256 = '11f2312b254a1c17761d2adb402f4ed6fc73eaa344a98994c695a6175ea1d469' }
)

try {
    if ($env:OS -ne 'Windows_NT') { throw 'Unsupported platform' }
    $Pin = $ExpectedCa.Replace(':', '').ToLowerInvariant()
    if ($Pin -notmatch '^[0-9a-f]{64}$') { throw 'Invalid public CA fingerprint' }
    $HubUri = $null
    if (-not [Uri]::TryCreate($Url, [UriKind]::Absolute, [ref]$HubUri) -or
        $HubUri.Scheme -ne 'https' -or $HubUri.UserInfo -or $HubUri.Query -or $HubUri.Fragment -or
        $HubUri.AbsolutePath -ne '/' -or $Url -match '[\s\\]') { throw 'Invalid Hub URL' }
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
                [IO.File]::WriteAllBytes((Join-Path $SetupDirectory $File.Name), $Bytes)
            } finally { $Response.Dispose() }
        }
    } finally {
        $Client.Dispose()
        $Handler.Dispose()
    }
    & $PythonCommand @PythonArguments (Join-Path $SetupDirectory 'setup-claude.py') --url $Url --expected-ca $Pin --project $ProjectPath
    if ($LASTEXITCODE -ne 0) { throw 'Project installer failed' }
} catch {
    # Never print exception text: supplied arguments or remote errors may contain secrets.
    Write-Error 'Claude setup failed. Check Windows/Python 3.12, project path, trusted Hub URL/CA fingerprint and network. Use -PythonPath for an existing Python 3.12. Existing ys_memory settings are never overwritten.'
    exit 1
}
