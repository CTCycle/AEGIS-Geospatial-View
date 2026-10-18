[CmdletBinding()]
param(
    [string]$RepositoryRoot,
    [string]$DataRoot,
    [string]$OutputDirectory,
    [int]$BackendPort = 5079,
    [string]$SecretEnvironmentVariable = 'AEGIS_T3_OPENCODE_GO_API_KEY',
    [int]$ReadinessTimeoutSeconds = 30,
    [int]$ProbeTimeoutSeconds = 180,
    [switch]$KeepRuntime
)

$ErrorActionPreference = 'Stop'

$scriptRoot = $PSScriptRoot
if ([string]::IsNullOrWhiteSpace($scriptRoot)) {
    $scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
}
if ([string]::IsNullOrWhiteSpace($RepositoryRoot)) {
    $RepositoryRoot = Split-Path -Parent (Split-Path -Parent $scriptRoot)
}

function Get-FullPath {
    param([Parameter(Mandatory = $true)][string]$Path)

    return [System.IO.Path]::GetFullPath($Path)
}

function Test-PathWithin {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Root
    )

    $normalizedPath = (Get-FullPath $Path).TrimEnd('\')
    $normalizedRoot = (Get-FullPath $Root).TrimEnd('\')
    return $normalizedPath.Equals($normalizedRoot, [System.StringComparison]::OrdinalIgnoreCase) -or
        $normalizedPath.StartsWith($normalizedRoot + '\', [System.StringComparison]::OrdinalIgnoreCase)
}

function Write-JsonArtifact {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][object]$Value
    )

    $Value | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $Path -Encoding utf8
}

function Restore-ProcessEnvironment {
    param(
        [Parameter(Mandatory = $true)][hashtable]$Snapshot
    )

    foreach ($name in $Snapshot.Keys) {
        [Environment]::SetEnvironmentVariable(
            $name,
            $Snapshot[$name],
            [EnvironmentVariableTarget]::Process
        )
    }
}

function Invoke-ApiJson {
    param(
        [Parameter(Mandatory = $true)][ValidateSet('Get', 'Patch', 'Post')][string]$Method,
        [Parameter(Mandatory = $true)][string]$Uri,
        [object]$Body,
        [int]$TimeoutSeconds = 30
    )

    $request = @{
        Method = $Method
        Uri = $Uri
        TimeoutSec = $TimeoutSeconds
        ErrorAction = 'Stop'
    }
    if ($null -ne $Body) {
        $request.ContentType = 'application/json'
        $request.Body = $Body | ConvertTo-Json -Depth 10 -Compress
    }
    return Invoke-RestMethod @request
}

$resolvedRepositoryRoot = (Resolve-Path -LiteralPath $RepositoryRoot).Path
$appDirectory = Join-Path $resolvedRepositoryRoot 'app'
$pythonPath = Join-Path $resolvedRepositoryRoot 'app\server\.venv\Scripts\python.exe'
$cacheRoot = Join-Path $resolvedRepositoryRoot 'runtimes\cache'
$qaRoot = Join-Path $resolvedRepositoryRoot 'assets\QA'
$protectedDataRoot = Join-Path $resolvedRepositoryRoot 'data'
$protectedResourcesRoot = Join-Path $resolvedRepositoryRoot 'app\resources'
$dateToken = [DateTime]::Now.ToString('yyyyMMdd')

if ([string]::IsNullOrWhiteSpace($DataRoot)) {
    $DataRoot = Join-Path $cacheRoot ("test-runtime\t3-09-opencode-go-exact-lane-$([DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ'))")
}
if ([string]::IsNullOrWhiteSpace($OutputDirectory)) {
    $OutputDirectory = Join-Path $qaRoot "tier3-validation-develop-$dateToken-t3-07-t3-09-final\T3-09"
}

$resolvedDataRoot = Get-FullPath $DataRoot
$resolvedOutputDirectory = Get-FullPath $OutputDirectory
$outputDirectoryAllowed = (Test-PathWithin -Path $resolvedOutputDirectory -Root $qaRoot) -and
    -not $resolvedOutputDirectory.Equals($qaRoot, [System.StringComparison]::OrdinalIgnoreCase)
$apiBaseUrl = "http://127.0.0.1:$BackendPort"
$resultPath = Join-Path $resolvedOutputDirectory 'exact-lane-bootstrap.json'
$stdoutPath = Join-Path $resolvedOutputDirectory 'backend.stdout.log'
$stderrPath = Join-Path $resolvedOutputDirectory 'backend.stderr.log'
$ownershipMarker = Join-Path $resolvedDataRoot '.aegis-t3-09-owned'
$secret = [Environment]::GetEnvironmentVariable($SecretEnvironmentVariable, 'Process')
$ownedProcess = $null
$exitCode = 1
$result = [ordered]@{
    status = 'BLOCKED'
    reason = $null
    tested_at = [DateTime]::UtcNow.ToString('o')
    provider = 'opencode-go'
    model = 'deepseek-v4.1-flash'
    backend = $apiBaseUrl
    data_root_isolated = $false
    secret_environment_variable = $SecretEnvironmentVariable
    secret_recorded = $false
    secret_leaked_to_logs = $false
    credential_present = $false
    credential_health = $null
    selected_provider = $null
    selected_model = $null
    probe = $null
    runtime_cleaned = $false
}

try {
    if (-not $outputDirectoryAllowed) {
        throw 'OutputDirectory must be a child of assets\\QA.'
    }
    New-Item -ItemType Directory -Path $resolvedOutputDirectory -Force | Out-Null

    if (-not (Test-Path -LiteralPath $pythonPath -PathType Leaf)) {
        throw "Project Python environment was not found: $pythonPath"
    }
    if (-not (Test-PathWithin -Path $resolvedDataRoot -Root $cacheRoot) -or
        $resolvedDataRoot.Equals($cacheRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw 'DataRoot must be a disposable child of runtimes\\cache.'
    }
    if (Test-PathWithin -Path $resolvedDataRoot -Root $protectedDataRoot) {
        throw 'DataRoot must not be inside the persistent data directory.'
    }
    if (Test-PathWithin -Path $resolvedDataRoot -Root $protectedResourcesRoot) {
        throw 'DataRoot must not be inside app\\resources.'
    }
    $result.data_root_isolated = $true

    if ([string]::IsNullOrWhiteSpace($secret)) {
        $result.reason = "Required process environment variable '$SecretEnvironmentVariable' was not supplied."
        $exitCode = 2
    } else {
        $listener = [System.Net.Sockets.TcpListener]::new(
            [System.Net.IPAddress]::Loopback,
            $BackendPort
        )
        try {
            $listener.Start()
        } catch {
            throw "Backend port $BackendPort is not available; no existing process was terminated."
        } finally {
            $listener.Stop()
        }

        if (Test-Path -LiteralPath $resolvedDataRoot) {
            $existingEntries = @(Get-ChildItem -LiteralPath $resolvedDataRoot -Force)
            if ($existingEntries.Count -gt 0) {
                throw "DataRoot already exists and is not empty: $resolvedDataRoot"
            }
        } else {
            New-Item -ItemType Directory -Path $resolvedDataRoot -Force | Out-Null
        }
        New-Item -ItemType File -Path $ownershipMarker -Force | Out-Null

        $environmentSnapshot = @{
            AEGIS_DATA_DIR = [Environment]::GetEnvironmentVariable('AEGIS_DATA_DIR', 'Process')
            PYTHONPATH = [Environment]::GetEnvironmentVariable('PYTHONPATH', 'Process')
            FASTAPI_HOST = [Environment]::GetEnvironmentVariable('FASTAPI_HOST', 'Process')
            FASTAPI_PORT = [Environment]::GetEnvironmentVariable('FASTAPI_PORT', 'Process')
        }
        [Environment]::SetEnvironmentVariable('AEGIS_DATA_DIR', $resolvedDataRoot, 'Process')
        [Environment]::SetEnvironmentVariable('PYTHONPATH', $appDirectory, 'Process')
        [Environment]::SetEnvironmentVariable('FASTAPI_HOST', '127.0.0.1', 'Process')
        [Environment]::SetEnvironmentVariable('FASTAPI_PORT', "$BackendPort", 'Process')

        $ownedProcess = Start-Process -FilePath $pythonPath `
            -ArgumentList @('-m', 'uvicorn', 'server.app:app', '--host', '127.0.0.1', '--port', "$BackendPort") `
            -WorkingDirectory (Join-Path $resolvedRepositoryRoot 'app\server') `
            -WindowStyle Hidden `
            -RedirectStandardOutput $stdoutPath `
            -RedirectStandardError $stderrPath `
            -PassThru

        $ready = $false
        $deadline = [DateTime]::UtcNow.AddSeconds($ReadinessTimeoutSeconds)
        while ([DateTime]::UtcNow -lt $deadline) {
            if ($ownedProcess.HasExited) {
                throw "Isolated backend exited during startup with code $($ownedProcess.ExitCode)."
            }
            try {
                $null = Invoke-ApiJson -Method Get -Uri "$apiBaseUrl/api/health" -TimeoutSeconds 3
                $ready = $true
                break
            } catch {
                Start-Sleep -Milliseconds 500
            }
        }
        if (-not $ready) {
            throw "Isolated backend did not become ready within $ReadinessTimeoutSeconds seconds."
        }

        $credentialPayload = @{
            credentials = @{
                'opencode-go' = @{ api_key = $secret }
            }
        }
        $null = Invoke-ApiJson -Method Patch -Uri "$apiBaseUrl/api/chat/settings" -Body $credentialPayload
        $selectionPayload = @{
            active_provider_mode = 'cloud'
            agent_model_provider = 'opencode-go'
            agent_model_name = 'deepseek-v4.1-flash'
        }
        $settings = Invoke-ApiJson -Method Patch -Uri "$apiBaseUrl/api/chat/settings" -Body $selectionPayload
        $settings = Invoke-ApiJson -Method Get -Uri "$apiBaseUrl/api/chat/settings"
        $result.credential_present = [bool]$settings.credentials.'opencode-go'.api_key
        $result.credential_health = $settings.credential_health.'opencode-go'.api_key
        $result.selected_provider = [string]$settings.agent_model_provider
        $result.selected_model = [string]$settings.agent_model_name
        if (-not $result.credential_present -or
            $result.selected_provider -ne 'opencode-go' -or
            $result.selected_model -ne 'deepseek-v4.1-flash') {
            throw 'Settings API did not persist the exact provider/model lane.'
        }

        $probe = Invoke-ApiJson -Method Post -Uri "$apiBaseUrl/api/chat/models/structured-probe" -TimeoutSeconds $ProbeTimeoutSeconds
        $result.probe = [ordered]@{
            http_status = 200
            provider = [string]$probe.provider
            model = [string]$probe.model
            protocol = [string]$probe.protocol
            status = [string]$probe.status
            parse_status = [string]$probe.parse_status
            duration_ms = $probe.duration_ms
        }
        if ($result.probe.status -ne 'passed' -or $result.probe.parse_status -ne 'complete') {
            throw 'The exact provider/model structured probe did not pass.'
        }
        $result.status = 'PASS'
        $result.reason = 'Exact OpenCode Go model lane persisted through Settings API and passed the native structured probe.'
        $result.secret_recorded = $false
        $exitCode = 0
    }
} catch {
    $message = $_.Exception.Message
    if (-not [string]::IsNullOrWhiteSpace($secret)) {
        $message = $message.Replace($secret, '[REDACTED]')
    }
    $result.status = 'FAILED'
    $result.reason = $message
    $exitCode = 1
} finally {
    if ($null -ne $ownedProcess) {
        try {
            if (-not $ownedProcess.HasExited) {
                Stop-Process -Id $ownedProcess.Id -Force -ErrorAction Stop
            }
            $null = $ownedProcess.WaitForExit(15000)
            $ownedProcess.Refresh()
            if (-not $ownedProcess.HasExited) {
                throw 'Owned backend process did not exit before log inspection.'
            }
        } catch {
            $result.status = 'FAILED'
            $result.reason = 'Owned backend process cleanup failed.'
            $exitCode = 1
        }
    }

    if (-not [string]::IsNullOrWhiteSpace($secret)) {
        foreach ($logPath in @($stdoutPath, $stderrPath)) {
            if (Test-Path -LiteralPath $logPath -PathType Leaf) {
                $logText = [System.IO.File]::ReadAllText($logPath)
                if ($logText.IndexOf($secret, [System.StringComparison]::Ordinal) -ge 0) {
                    $result.secret_leaked_to_logs = $true
                    Remove-Item -LiteralPath $logPath -Force
                }
            }
        }
        if ($result.secret_leaked_to_logs) {
            $result.status = 'FAILED'
            $result.reason = 'The supplied secret was detected in an owned backend log and the log was removed.'
            $exitCode = 1
        }
    }

    if ($null -ne $environmentSnapshot) {
        Restore-ProcessEnvironment -Snapshot $environmentSnapshot
    }

    if (-not $KeepRuntime -and (Test-Path -LiteralPath $ownershipMarker -PathType Leaf)) {
        try {
            Remove-Item -LiteralPath $resolvedDataRoot -Recurse -Force -ErrorAction Stop
            $result.runtime_cleaned = $true
        } catch {
            $result.status = 'FAILED'
            $result.reason = 'Owned disposable runtime cleanup failed.'
            $exitCode = 1
        }
    } elseif ($KeepRuntime) {
        $result.runtime_cleaned = $false
    }

    if ($outputDirectoryAllowed -and -not (Test-Path -LiteralPath $resolvedOutputDirectory)) {
        New-Item -ItemType Directory -Path $resolvedOutputDirectory -Force | Out-Null
    }
    Write-JsonArtifact -Path $resultPath -Value $result
}

exit $exitCode
