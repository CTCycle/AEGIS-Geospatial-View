[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [string]$RepositoryRoot
)

$ErrorActionPreference = 'Stop'
$launcherPath = Join-Path $RepositoryRoot 'start_on_windows.ps1'
$tokens = $null
$parseErrors = $null
$launcherAst = [System.Management.Automation.Language.Parser]::ParseFile(
    $launcherPath,
    [ref]$tokens,
    [ref]$parseErrors
)
if ($parseErrors.Count -gt 0) {
    throw ($parseErrors | ForEach-Object Message | Out-String)
}

foreach ($statement in $launcherAst.EndBlock.Statements) {
    if ($statement -is [System.Management.Automation.Language.FunctionDefinitionAst]) {
        . ([scriptblock]::Create($statement.Extent.Text))
    }
}

$script:LauncherInteractive = $false
$script:NextProgressId = 1
$script:ActiveProgressActivities = [Collections.Generic.Dictionary[int, string]]::new()
$script:ConflictSequence = [Collections.Queue]::new()
$script:CurrentConflicts = @()
$script:TaskKillCount = 0
$script:TaskKillClearsConflicts = $false
$script:ReadHostCount = 0

function Assert-Scenario {
    param(
        [Parameter(Mandatory)][bool]$Condition,
        [Parameter(Mandatory)][string]$Message
    )
    if (-not $Condition) { throw $Message }
}

function Get-ExpectedFailure {
    param(
        [Parameter(Mandatory)][scriptblock]$Action,
        [Parameter(Mandatory)][string]$MessageFragment
    )
    $failure = $null
    try { & $Action } catch { $failure = $_.Exception }
    if ($null -eq $failure) {
        throw "Expected failure containing '$MessageFragment'."
    }
    if ($failure.Message -notmatch [regex]::Escape($MessageFragment)) {
        throw "Unexpected failure: $($failure.Message)"
    }
    return $failure
}

function Write-PortConflicts {
    param([Parameter(Mandatory)][object[]]$Conflicts)
}

function Read-Host {
    param([string]$Prompt)
    $script:ReadHostCount++
    return 'yes'
}

function Get-PortConflicts {
    param([Parameter(Mandatory)][int[]]$Ports)
    if ($script:ConflictSequence.Count -gt 1) {
        return $script:ConflictSequence.Dequeue()
    }
    if ($script:ConflictSequence.Count -eq 1) {
        return $script:ConflictSequence.Peek()
    }
    return $script:CurrentConflicts
}

function taskkill.exe {
    $script:TaskKillCount++
    if ($script:TaskKillClearsConflicts) { $script:CurrentConflicts = @() }
    $global:LASTEXITCODE = 5
    return 'Synthetic taskkill refusal; no process was targeted.'
}

# Unresolved identities must fail before prompting or issuing a termination command.
$unresolved = [pscustomobject]@{
    ProcessId = 2147483001
    ProcessName = 'unavailable'
    StartTimeUtcTicks = $null
    Ports = @(45871)
}
$script:LauncherInteractive = $true
$script:CurrentConflicts = @($unresolved)
$script:TaskKillCount = 0
$script:TaskKillClearsConflicts = $true
$script:ReadHostCount = 0
$unresolvedFailure = Get-ExpectedFailure -Action {
    Resolve-LaunchPortConflicts -Ports @(45871, 45872)
} -MessageFragment 'Unable to resolve the identity'
Assert-Scenario ($unresolvedFailure.Message -match 'no existing process was terminated') 'Unresolved owner error omitted the fail-closed detail.'
Assert-Scenario ($script:ReadHostCount -eq 0) 'Launcher prompted for an unresolved owner.'
Assert-Scenario ($script:TaskKillCount -eq 0) 'Launcher attempted to terminate an unresolved owner.'

# A resolved owner in non-interactive mode must also fail without termination.
$resolved = [pscustomobject]@{
    ProcessId = 2147483002
    ProcessName = 'controlled-test-owner'
    StartTimeUtcTicks = 638940000000000000
    Ports = @(45871)
}
$script:LauncherInteractive = $false
$script:CurrentConflicts = @($resolved)
$script:TaskKillCount = 0
$script:TaskKillClearsConflicts = $false
$nonInteractiveFailure = Get-ExpectedFailure -Action {
    Resolve-LaunchPortConflicts -Ports @(45871, 45872)
} -MessageFragment 'Launch is non-interactive'
Assert-Scenario ($script:TaskKillCount -eq 0) 'Non-interactive conflict attempted termination.'

# PID reuse/identity change at the final recheck must require fresh consent.
$replacement = [pscustomobject]@{
    ProcessId = $resolved.ProcessId
    ProcessName = 'replacement-test-owner'
    StartTimeUtcTicks = 638940000000000001
    Ports = @(45871)
}
$script:ConflictSequence = [Collections.Queue]::new()
$script:ConflictSequence.Enqueue(@($resolved))
$script:ConflictSequence.Enqueue(@($resolved))
$script:ConflictSequence.Enqueue(@($replacement))
$script:ConflictSequence.Enqueue(@($replacement))
$script:ConfirmCount = 0
$script:TaskKillCount = 0
$script:LauncherInteractive = $true
function Confirm-PortConflictTermination {
    param([Parameter(Mandatory)][object[]]$Conflicts)
    $script:ConfirmCount++
    return $script:ConfirmCount -eq 1
}
$ownershipFailure = Get-ExpectedFailure -Action {
    Resolve-LaunchPortConflicts -Ports @(45871, 45872)
} -MessageFragment 'Launch cancelled'
Assert-Scenario ($script:ConfirmCount -eq 2) 'Replacement owner did not receive a fresh consent prompt.'
Assert-Scenario ($script:TaskKillCount -eq 0) 'Replacement owner was terminated without fresh consent.'

# Model an OS refusal against a synthetic protected owner; never target a real PID.
$protected = [pscustomobject]@{
    ProcessId = 2147483003
    ProcessName = 'synthetic-protected-owner'
    StartTimeUtcTicks = 638940000000000002
    Ports = @(45871)
}
$script:ConflictSequence = [Collections.Queue]::new()
$script:CurrentConflicts = @($protected)
$script:TaskKillCount = 0
$script:LauncherInteractive = $true
function Confirm-PortConflictTermination {
    param([Parameter(Mandatory)][object[]]$Conflicts)
    return $true
}
function Start-Sleep {
    param([int]$Seconds = 1)
    [Threading.Thread]::Sleep(100)
}
$protectedFailure = Get-ExpectedFailure -Action {
    Resolve-LaunchPortConflicts -Ports @(45871, 45872)
} -MessageFragment 'Termination errors'
Assert-Scenario ($protectedFailure.Message -match 'synthetic-protected-owner') 'Termination refusal did not identify the unresolved occupied port.'
Assert-Scenario ($script:TaskKillCount -eq 1) 'Confirmed synthetic owner was not deduplicated to one attempt.'

# Exercise the real cleanup function with controlled child processes and an unrelated control.
Remove-Item Function:\taskkill.exe -ErrorAction SilentlyContinue
$script:RootDir = $RepositoryRoot
$script:AppDir = Join-Path $RepositoryRoot 'app'
$script:ClientDir = Join-Path $RepositoryRoot 'app\client'
$script:VenvDir = Join-Path $RepositoryRoot 'app\server\.venv'
$script:NpmCmd = Join-Path $RepositoryRoot 'app\client\node_modules\.bin\ng.cmd'
$script:PowerShellExe = Join-Path $PSHOME 'pwsh.exe'
$script:StartedProcesses = [Collections.Generic.List[System.Diagnostics.Process]]::new()
$script:FailureStage = ''
$script:HealthCall = 0
$script:BrowserOpenAttempted = $false

function Import-EnvironmentFile {
    $env:FASTAPI_HOST = '127.0.0.1'
    $env:FASTAPI_PORT = '45871'
    $env:UI_HOST = '127.0.0.1'
    $env:UI_PORT = '45872'
    $env:RELOAD = 'false'
    $env:BACKEND_LOGS_VISIBLE = 'false'
}
function Set-LauncherEnvironment {}
function Test-LaunchDependenciesReady { return $true }
function Ensure-FrontendBuildCurrent {}
function Resolve-LaunchPortConflicts {
    param([Parameter(Mandatory)][int[]]$Ports)
}
function Wait-HttpHealth {
    param(
        [Parameter(Mandatory)][string]$Uri,
        [System.Diagnostics.Process]$Process,
        [int]$TimeoutSeconds = 60,
        [int]$IntervalSeconds = 1
    )
    $script:HealthCall++
    if ($script:FailureStage -eq 'backend' -and $script:HealthCall -eq 1) {
        return $false
    }
    if ($script:FailureStage -eq 'frontend' -and $script:HealthCall -eq 2) {
        return $false
    }
    return $true
}
function Start-Process {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$FilePath,
        [string[]]$ArgumentList,
        [string]$WorkingDirectory,
        [string]$WindowStyle,
        [switch]$PassThru
    )
    if ($FilePath -like 'http://*' -or $FilePath -like 'https://*') {
        $script:BrowserOpenAttempted = $true
        return $null
    }
    $process = Microsoft.PowerShell.Management\Start-Process `
        -FilePath $script:PowerShellExe `
        -ArgumentList @('-NoLogo -NoProfile -NonInteractive -Command "Start-Sleep -Seconds 120"') `
        -WorkingDirectory $RepositoryRoot `
        -WindowStyle Hidden `
        -PassThru
    [void]$script:StartedProcesses.Add($process)
    return $process
}
function Write-Status {
    param([string]$Level, [string]$Message)
}

$failureResults = [Collections.Generic.List[object]]::new()
foreach ($stage in @('backend', 'frontend')) {
    $script:FailureStage = $stage
    $script:HealthCall = 0
    $script:StartedProcesses = [Collections.Generic.List[System.Diagnostics.Process]]::new()
    $unrelated = Microsoft.PowerShell.Management\Start-Process `
        -FilePath $script:PowerShellExe `
        -ArgumentList @('-NoLogo -NoProfile -NonInteractive -Command "Start-Sleep -Seconds 120"') `
        -WorkingDirectory $RepositoryRoot `
        -WindowStyle Hidden `
        -PassThru
    try {
        $expectedFailure = if ($stage -eq 'backend') {
            'Backend did not become ready'
        } else {
            'Frontend preview did not become ready'
        }
        $failure = Get-ExpectedFailure -Action { Invoke-LaunchApplication } `
            -MessageFragment $expectedFailure
        foreach ($process in $script:StartedProcesses) {
            $process.Refresh()
            [void]$process.WaitForExit(5000)
            $process.Refresh()
            Assert-Scenario $process.HasExited "$stage readiness failure left launcher-owned PID $($process.Id) running."
        }
        $unrelated.Refresh()
        Assert-Scenario (-not $unrelated.HasExited) "$stage readiness failure terminated unrelated control PID $($unrelated.Id)."
        $failureResults.Add([pscustomobject]@{
            stage = $stage
            launcher_owned_pids = @($script:StartedProcesses | ForEach-Object Id)
            unrelated_pid_survived = $unrelated.Id
            expected_failure = $failure.Message
        })
    }
    finally {
        foreach ($process in $script:StartedProcesses) {
            $process.Refresh()
            if (-not $process.HasExited) {
                Microsoft.PowerShell.Management\Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
            }
        }
        $unrelated.Refresh()
        if (-not $unrelated.HasExited) {
            Microsoft.PowerShell.Management\Stop-Process -Id $unrelated.Id -Force -ErrorAction SilentlyContinue
            [void]$unrelated.WaitForExit(5000)
        }
    }
}

[ordered]@{
    result = 'PASS'
    launcher_parse = 'PASS'
    unresolved_owner_fails_before_prompt_or_termination = 'PASS'
    noninteractive_conflict_fails_without_termination = 'PASS'
    changed_owner_requires_fresh_consent = 'PASS'
    synthetic_termination_refusal_fails_closed = 'PASS'
    readiness_failure_cleanup = @($failureResults)
    simulated_listener_pids = @(2147483001, 2147483002, 2147483003)
    real_services_or_user_processes_targeted = $false
} | ConvertTo-Json -Depth 6
