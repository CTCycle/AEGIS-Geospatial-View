[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$RootDir = $PSScriptRoot
$AppDir = Join-Path $RootDir 'app'
$ServerDir = Join-Path $AppDir 'server'
$ClientDir = Join-Path $AppDir 'client'
$TestsDir = Join-Path $AppDir 'tests'
$SettingsDir = Join-Path $RootDir 'settings'
$RuntimesDir = Join-Path $RootDir 'runtimes'
$ResourcesDir = Join-Path $AppDir 'resources'
$DefaultRuntimeDataDir = Join-Path $ResourcesDir 'runtime'
$IngestionDataDir = Join-Path $RootDir 'data'
$VectorsDir = Join-Path $ResourcesDir 'vectors'
$RuntimeCacheDir = Join-Path $RuntimesDir 'cache'
$ToolCacheDir = Join-Path $TestsDir 'cache'
$LegacyCacheDir = Join-Path $RootDir 'assets\cache'
$PythonDir = Join-Path $RuntimesDir 'python'
$PythonExe = Join-Path $PythonDir 'python.exe'
$PythonPth = Join-Path $PythonDir 'python314._pth'
$UvDir = Join-Path $RuntimesDir 'uv'
$UvExe = Join-Path $UvDir 'uv.exe'
$NodeDir = Join-Path $RuntimesDir 'nodejs'
$NodeExe = Join-Path $NodeDir 'node.exe'
$NpmCmd = Join-Path $NodeDir 'npm.cmd'
$UvCacheDir = Join-Path $RuntimeCacheDir 'uv'
$NpmCacheDir = Join-Path $RuntimeCacheDir 'npm'
$PipCacheDir = Join-Path $RuntimeCacheDir 'pip'
$PythonBytecodeCacheDir = Join-Path $RuntimeCacheDir 'python'
$PlaywrightBrowsersDir = Join-Path $RuntimeCacheDir 'playwright-browsers'
$PytestCacheDir = Join-Path $ToolCacheDir 'pytest'
$PytestTempDir = Join-Path $ToolCacheDir 'pytest-tmp'
$RuffCacheDir = Join-Path $ToolCacheDir 'ruff'
$CoverageDir = Join-Path $ToolCacheDir 'coverage'
$AngularCacheDir = Join-Path $ToolCacheDir 'angular'
$VenvDir = Join-Path $ServerDir '.venv'
$DotEnvPath = Join-Path $SettingsDir '.env'
$DotEnvExamplePath = Join-Path $SettingsDir '.env.example'
$LogsDir = Join-Path $AppDir 'resources\logs'
$TestScript = Join-Path $AppDir 'tests\run_tests.bat'
$LegacyCachePaths = @(
    $LegacyCacheDir,
    (Join-Path $RootDir '.pytest_cache'),
    (Join-Path $RootDir '.ruff_cache'),
    (Join-Path $RootDir '.tmp_pytest'),
    (Join-Path $ClientDir '.angular')
)
$InitializeDatabaseScript = Join-Path $AppDir 'scripts\initialize_database.py'
$PythonVersion = '3.14.2'
$PythonArchiveName = "python-$PythonVersion-embed-amd64.zip"
$PythonArchiveUri = "https://www.python.org/ftp/python/$PythonVersion/$PythonArchiveName"
$UvAmd64Uri = 'https://github.com/astral-sh/uv/releases/latest/download/uv-x86_64-pc-windows-msvc.zip'
$UvArm64Uri = 'https://github.com/astral-sh/uv/releases/latest/download/uv-aarch64-pc-windows-msvc.zip'
$NodeVersion = '22.23.1'
$NodeArchiveName = "node-v$NodeVersion-win-x64.zip"
$NodeArchiveUri = "https://nodejs.org/dist/v$NodeVersion/$NodeArchiveName"
$script:NextProgressId = 1
$script:ActiveProgressIds = [Collections.Generic.HashSet[int]]::new()

# -----------------------------------------------------------------------------
# RUNTIME AND DOWNLOAD HELPERS
# -----------------------------------------------------------------------------
function Invoke-DownloadAndExtract {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$Uri,
        [Parameter(Mandatory)]
        [string]$ArchivePath,
        [Parameter(Mandatory)]
        [string]$DestinationPath
    )
    $ErrorActionPreference = 'Stop'
    $previousProgressPreference = $ProgressPreference
    $activity = "AEGIS: download and extract $([IO.Path]::GetFileName($ArchivePath))"
    $progressId = Start-LauncherProgress -Activity $activity -Status "Downloading $Uri"
    try {
        $ProgressPreference = 'SilentlyContinue'
        New-Item -ItemType Directory -Path (Split-Path -Parent $ArchivePath) -Force | Out-Null
        New-Item -ItemType Directory -Path $DestinationPath -Force | Out-Null
        Invoke-WebRequest -Uri $Uri -OutFile $ArchivePath
        $ProgressPreference = $previousProgressPreference
        Update-LauncherProgress -Id $progressId -Activity $activity -Status 'Extracting archive'
        Expand-Archive -LiteralPath $ArchivePath -DestinationPath $DestinationPath -Force
    }
    finally {
        $ProgressPreference = $previousProgressPreference
        Remove-Item -LiteralPath $ArchivePath -Force -ErrorAction SilentlyContinue
        Complete-LauncherProgress $progressId
    }
}

function Enable-EmbeddedPythonSitePackages {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$Path
    )
    if (-not (Test-Path -LiteralPath $Path)) {
        return
    }
    $content = Get-Content -LiteralPath $Path -Raw
    $patched = $content -replace '(?m)^#import site\s*$', 'import site'
    if ($patched -ne $content) {
        Set-Content -LiteralPath $Path -Value $patched -NoNewline
    }
}

function Find-UvExecutable {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$SearchPath
    )
    Get-ChildItem -LiteralPath $SearchPath -Recurse -Filter 'uv.exe' -File -ErrorAction SilentlyContinue |
        Select-Object -First 1 -ExpandProperty FullName
}

function Get-PythonRuntimeVersion {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$PythonExecutable
    )
    & $PythonExecutable -c 'import platform; print(platform.python_version())'
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to execute Python at $PythonExecutable."
    }
}

function Wait-HttpHealth {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$Uri,
        [ValidateRange(1, 600)]
        [int]$TimeoutSeconds = 60,
        [ValidateRange(1, 60)]
        [int]$IntervalSeconds = 1
    )
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    $activity = "AEGIS: wait for health $Uri"
    $progressId = Start-LauncherProgress -Activity $activity -Status "Waiting up to $TimeoutSeconds seconds"
    try {
        do {
            $elapsed = [int](([DateTime]::UtcNow - $deadline.AddSeconds(-$TimeoutSeconds)).TotalSeconds)
            Update-LauncherProgress -Id $progressId -Activity $activity -Status "Waiting for healthy response; ${elapsed}s elapsed"
            try {
                $response = Invoke-WebRequest -UseBasicParsing -Uri $Uri -TimeoutSec 2
                if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 300) {
                    return $true
                }
            }
            catch {
            }
            Start-Sleep -Seconds $IntervalSeconds
        } while ([DateTime]::UtcNow -lt $deadline)
        return $false
    }
    finally {
        Complete-LauncherProgress $progressId
    }
}

function Write-Status {
    param(
        [Parameter(Mandatory)]
        [ValidateSet('STEP', 'OK', 'INFO', 'WARN', 'FATAL', 'SUCCESS', 'RUN', 'WAIT')]
        [string]$Level,

        [Parameter(Mandatory)]
        [string]$Message
    )

    $color = switch ($Level) {
        'STEP' { 'Cyan' }
        'OK' { 'Green' }
        'INFO' { 'Gray' }
        'WARN' { 'Yellow' }
        'FATAL' { 'Red' }
        'SUCCESS' { 'Green' }
        'RUN' { 'Cyan' }
        'WAIT' { 'Yellow' }
    }
    Write-Host "[$Level] $Message" -ForegroundColor $color
}

function Start-LauncherProgress {
    param([Parameter(Mandatory)][string]$Activity, [string]$Status = 'Starting')
    $id = $script:NextProgressId++
    [void]$script:ActiveProgressIds.Add($id)
    Write-Progress -Id $id -Activity $Activity -Status $Status
    return $id
}

function Update-LauncherProgress {
    param(
        [Parameter(Mandatory)][int]$Id,
        [Parameter(Mandatory)][string]$Activity,
        [Parameter(Mandatory)][string]$Status,
        [Nullable[int]]$PercentComplete
    )
    if (-not $script:ActiveProgressIds.Contains($Id)) { return }
    $progress = @{ Id = $Id; Activity = $Activity; Status = $Status }
    if ($null -ne $PercentComplete) { $progress.PercentComplete = $PercentComplete }
    Write-Progress @progress
}

function Complete-LauncherProgress([int]$Id) {
    if ($script:ActiveProgressIds.Contains($Id)) {
        Write-Progress -Id $Id -Activity 'AEGIS launcher' -Completed
        [void]$script:ActiveProgressIds.Remove($Id)
    }
}

function Clear-LauncherProgress {
    foreach ($id in @($script:ActiveProgressIds)) {
        Write-Progress -Id $id -Activity 'AEGIS launcher' -Completed
        [void]$script:ActiveProgressIds.Remove($id)
    }
}

function Invoke-TrackedLauncherAction {
    param(
        [Parameter(Mandatory)][string]$Name,
        [Parameter(Mandatory)][scriptblock]$Action
    )
    $activity = "AEGIS: $Name"
    $progressId = Start-LauncherProgress -Activity $activity -Status 'Starting'
    Write-Status RUN "Starting $Name"
    try {
        Update-LauncherProgress -Id $progressId -Activity $activity -Status 'Running'
        & $Action
        Write-Status SUCCESS "$Name completed"
    }
    catch {
        Write-Status FATAL "$Name failed: $($_.Exception.Message)"
        throw
    }
    finally {
        Complete-LauncherProgress $progressId
    }
}

# -----------------------------------------------------------------------------
# ENVIRONMENT AND CACHE CONFIGURATION
# -----------------------------------------------------------------------------
function Import-EnvironmentFile {
    $environmentSourcePath = $DotEnvPath
    if (-not (Test-Path -LiteralPath $environmentSourcePath)) {
        $environmentSourcePath = $DotEnvExamplePath
    }
    if (-not (Test-Path -LiteralPath $environmentSourcePath)) {
        throw "Missing environment file and template: $DotEnvPath"
    }

    $defaults = [ordered]@{
        FASTAPI_HOST = '127.0.0.1'
        FASTAPI_PORT = '8000'
        UI_HOST = '127.0.0.1'
        UI_PORT = '8001'
        RELOAD = 'false'
        BACKEND_LOGS_VISIBLE = 'true'
    }
    foreach ($entry in $defaults.GetEnumerator()) {
        [Environment]::SetEnvironmentVariable($entry.Key, $entry.Value, 'Process')
    }

    foreach ($rawLine in Get-Content -LiteralPath $environmentSourcePath) {
        $line = $rawLine.Trim()
        if (-not $line -or $line.StartsWith('#') -or $line.StartsWith(';') -or -not $line.Contains('=')) {
            continue
        }

        $parts = $line.Split('=', 2)
        $key = $parts[0].Trim()
        $value = $parts[1].Trim()
        if (-not $key) {
            continue
        }
        if (($value.StartsWith('"') -and $value.EndsWith('"')) -or
            ($value.StartsWith("'") -and $value.EndsWith("'"))) {
            $value = $value.Substring(1, $value.Length - 2)
        }
        [Environment]::SetEnvironmentVariable($key, $value, 'Process')
    }
}

function Set-LauncherEnvironment {
    New-Item -ItemType Directory -Path $RuntimeCacheDir, $ToolCacheDir, $UvCacheDir, $NpmCacheDir, $PipCacheDir, $PythonBytecodeCacheDir, $PytestCacheDir, $PytestTempDir, $RuffCacheDir, $CoverageDir, $AngularCacheDir, $PlaywrightBrowsersDir -Force | Out-Null
    $env:UV_CACHE_DIR = $UvCacheDir
    $env:UV_PROJECT_ENVIRONMENT = $VenvDir
    $env:UV_LINK_MODE = 'copy'
    $env:NPM_CONFIG_CACHE = $NpmCacheDir
    $env:PIP_CACHE_DIR = $PipCacheDir
    $env:PLAYWRIGHT_BROWSERS_PATH = $PlaywrightBrowsersDir
    $env:PYTHONPYCACHEPREFIX = $PythonBytecodeCacheDir
    $env:RUFF_CACHE_DIR = $RuffCacheDir
    $env:COVERAGE_FILE = Join-Path $CoverageDir '.coverage'
    $env:PYTEST_ADDOPTS = '--basetemp="' + $PytestTempDir + '"'
    Remove-Item Env:\PYTHONHOME -ErrorAction SilentlyContinue
    Remove-Item Env:\PYTHONPATH -ErrorAction SilentlyContinue
    Remove-Item Env:\PYTHONNOUSERSITE -ErrorAction SilentlyContinue
    $env:PATH = "$NodeDir;$($env:PATH)"
}

# -----------------------------------------------------------------------------
# PORTABLE RUNTIMES AND DEPENDENCIES
# -----------------------------------------------------------------------------
function Ensure-NodeRuntime {
    New-Item -ItemType Directory -Path $RuntimesDir, $NodeDir -Force | Out-Null

    Write-Status STEP 'Installing Node.js (portable)'
    if (-not (Test-Path -LiteralPath $NodeExe)) {
        Write-Status INFO "Downloading $NodeArchiveUri"
        Invoke-DownloadAndExtract -Uri $NodeArchiveUri -ArchivePath (Join-Path $NodeDir $NodeArchiveName) -DestinationPath $NodeDir
    }
    $nestedNodeDir = Join-Path $NodeDir "node-v$NodeVersion-win-x64"
    if (Test-Path -LiteralPath (Join-Path $nestedNodeDir 'node.exe')) {
        Get-ChildItem -LiteralPath $nestedNodeDir -Force | Move-Item -Destination $NodeDir -Force
        Remove-Item -LiteralPath $nestedNodeDir -Recurse -Force
    }
    if (-not (Test-Path -LiteralPath $NodeExe) -or -not (Test-Path -LiteralPath $NpmCmd)) {
        throw "The portable Node.js runtime is incomplete at $NodeDir."
    }
    $nodeVersionOutput = & $NodeExe --version
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to execute Node.js at $NodeExe."
    }
    Write-Status OK "Node.js ready: $nodeVersionOutput"
}

function Ensure-PortableRuntimes {
    New-Item -ItemType Directory -Path $RuntimesDir, $PythonDir, $UvDir -Force | Out-Null

    Write-Status STEP 'Setting up Python (embeddable) locally'
    if (-not (Test-Path -LiteralPath $PythonExe)) {
        Write-Status INFO "Downloading $PythonArchiveUri"
        Invoke-DownloadAndExtract -Uri $PythonArchiveUri -ArchivePath (Join-Path $PythonDir $PythonArchiveName) -DestinationPath $PythonDir
    }
    Enable-EmbeddedPythonSitePackages -Path $PythonPth
    Write-Status OK "Python ready: $(Get-PythonRuntimeVersion -PythonExecutable $PythonExe)"

    Write-Status STEP 'Installing uv (portable)'
    if (-not (Test-Path -LiteralPath $UvExe)) {
        $uvUri = if ($env:PROCESSOR_ARCHITECTURE -eq 'ARM64') { $UvArm64Uri } else { $UvAmd64Uri }
        Write-Status INFO "Downloading $uvUri"
        Invoke-DownloadAndExtract -Uri $uvUri -ArchivePath (Join-Path $UvDir 'uv.zip') -DestinationPath $UvDir
        $foundUv = Find-UvExecutable -SearchPath $UvDir
        if (-not $foundUv) {
            throw 'uv.exe was not found after extraction.'
        }
        if ([IO.Path]::GetFullPath($foundUv) -ne [IO.Path]::GetFullPath($UvExe)) {
            Copy-Item -LiteralPath $foundUv -Destination $UvExe -Force
        }
    }
    $uvVersion = & $UvExe --version
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to execute uv at $UvExe."
    }
    Write-Status OK ($uvVersion -join ' ')

    Ensure-NodeRuntime
}

function Build-Frontend {
    if (-not (Test-Path -LiteralPath (Join-Path $ClientDir 'package.json'))) {
        throw "Frontend package manifest was not found at $ClientDir."
    }

    Write-Status STEP 'Building frontend'
    Push-Location $ClientDir
    try {
        & $NpmCmd run build
        if ($LASTEXITCODE -ne 0) {
            throw "Frontend build failed with exit code $LASTEXITCODE."
        }
    }
    finally {
        Pop-Location
    }
}

function Sync-Dependencies {
    param(
        [bool]$BuildFrontend = $false,
        [ValidateSet('Standard', 'Development')]
        [string]$InstallationType = 'Standard'
    )

    Write-Status STEP 'Installing Python dependencies with uv'
    $uvArguments = @('sync', '--python', $PythonExe, '--no-install-project')
    if ($InstallationType -eq 'Development') {
        $uvArguments += '--all-extras'
    }
    Push-Location $ServerDir
    try {
        & $UvExe @uvArguments
        if ($LASTEXITCODE -ne 0) {
            throw "uv sync failed with exit code $LASTEXITCODE."
        }
    }
    finally {
        Pop-Location
    }

    Write-Status STEP 'Installing frontend dependencies'
    Push-Location $ClientDir
    try {
        if (Test-Path -LiteralPath (Join-Path $ClientDir 'package-lock.json')) {
            & $NpmCmd ci
        }
        else {
            & $NpmCmd install
        }
        if ($LASTEXITCODE -ne 0) {
            throw "npm dependency installation failed with exit code $LASTEXITCODE."
        }
    }
    finally {
        Pop-Location
    }

    if ($BuildFrontend) {
        Build-Frontend
    }
}

# -----------------------------------------------------------------------------
# APPLICATION ACTIONS
# -----------------------------------------------------------------------------
function Invoke-RebuildFrontend {
    Import-EnvironmentFile
    Set-LauncherEnvironment
    Ensure-NodeRuntime
    Build-Frontend
    Write-Status SUCCESS 'Frontend rebuilt successfully.'
}

function Test-DependenciesReady {
    $frontendPackage = Join-Path $ClientDir 'package.json'
    $frontendLock = Join-Path $ClientDir 'package-lock.json'
    $frontendModules = Join-Path $ClientDir 'node_modules'
    $frontendInstallState = Join-Path $frontendModules '.package-lock.json'
    $frontendRunner = Join-Path $frontendModules '@angular/cli/bin/ng.js'
    $backendEntrypoint = Join-Path $ServerDir 'app.py'
    $venvPython = Join-Path $VenvDir 'Scripts\python.exe'

    if (-not (Test-Path -LiteralPath $PythonExe) -or
        -not (Test-Path -LiteralPath $UvExe) -or
        -not (Test-Path -LiteralPath $NodeExe) -or
        -not (Test-Path -LiteralPath $NpmCmd) -or
        -not (Test-Path -LiteralPath $venvPython) -or
        -not (Test-Path -LiteralPath $backendEntrypoint) -or
        -not (Test-Path -LiteralPath $frontendPackage) -or
        -not (Test-Path -LiteralPath $frontendLock) -or
        -not (Test-Path -LiteralPath $frontendInstallState) -or
        -not (Test-Path -LiteralPath $frontendRunner)) {
        return $false
    }

    & $PythonExe --version *> $null
    if ($LASTEXITCODE -ne 0) { return $false }
    & $UvExe --version *> $null
    if ($LASTEXITCODE -ne 0) { return $false }
    & $NodeExe --version *> $null
    if ($LASTEXITCODE -ne 0) { return $false }
    & $venvPython -c 'import alembic, fastapi, filelock, uvicorn' *> $null
    if ($LASTEXITCODE -ne 0) { return $false }

    return $true
}

function Get-PortListenerPids {
    param([Parameter(Mandatory)][int]$Port)

    $pattern = "^\s*TCP\s+\S+:$Port\s+\S+\s+LISTENING\s+(\d+)\s*$"
    @(netstat.exe -ano -p TCP 2>$null) | ForEach-Object {
        if ($_ -match $pattern) {
            [int]$Matches[1]
        }
    } | Sort-Object -Unique
}

function Stop-PortListeners {
    param([Parameter(Mandatory)][int]$Port)

    foreach ($processId in @(Get-PortListenerPids -Port $Port)) {
        Write-Status INFO "Releasing port $Port from PID $processId."
        & taskkill.exe /PID $processId /T /F | Out-Null
    }

    $deadline = [DateTime]::UtcNow.AddSeconds(20)
    while (@(Get-PortListenerPids -Port $Port).Count -gt 0 -and [DateTime]::UtcNow -lt $deadline) {
        Start-Sleep -Seconds 1
    }
    if (@(Get-PortListenerPids -Port $Port).Count -gt 0) {
        throw "Port $Port is still occupied after 20 seconds."
    }
}

function Get-BrowserHost {
    param([Parameter(Mandatory)][string]$HostName)
    if ($HostName -in @('0.0.0.0', '::')) {
        return '127.0.0.1'
    }
    return $HostName
}

function Invoke-LaunchApplication {
    Import-EnvironmentFile
    Set-LauncherEnvironment
    if (-not (Test-DependenciesReady)) {
        Write-Status STEP 'Required application environments are missing or unusable; installing dependencies and rebuilding the frontend.'
        Ensure-PortableRuntimes
        Sync-Dependencies -BuildFrontend $true -InstallationType 'Standard'
    }
    else {
        Write-Status OK 'Application environments are ready; skipped dependency installation.'
    }

    $fastApiPort = [int]$env:FASTAPI_PORT
    $uiPort = [int]$env:UI_PORT
    $browserBackendHost = Get-BrowserHost -HostName $env:FASTAPI_HOST
    $browserUiHost = Get-BrowserHost -HostName $env:UI_HOST
    $backendHealthUri = "http://${browserBackendHost}:$fastApiPort/api/health"
    $uiUri = "http://${browserUiHost}:$uiPort"

    Stop-PortListeners -Port $fastApiPort
    Stop-PortListeners -Port $uiPort

    $venvPython = Join-Path $VenvDir 'Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $venvPython)) {
        throw "Virtual-environment Python was not found at $venvPython."
    }

    $backendModule = 'app.server.app:app'
    $backendWorkingDirectory = $RootDir
    $env:PYTHONPATH = "$RootDir;$AppDir"
    & $venvPython -c "import importlib; importlib.import_module('app.server.app')" 2>$null
    if ($LASTEXITCODE -ne 0) {
        $backendModule = 'server.app:app'
        $backendWorkingDirectory = $ServerDir
        $env:PYTHONPATH = $AppDir
    }

    $backendArguments = @('-m', 'uvicorn', $backendModule, '--host', $env:FASTAPI_HOST, '--port', "$fastApiPort", '--log-level', 'info', '--ws-max-size', '65536', '--ws-ping-interval', '15', '--ws-ping-timeout', '10')
    if ($env:RELOAD -ieq 'true') {
        $backendArguments += '--reload'
    }

    Write-Status RUN "Launching backend ($backendModule)"
    $backendProcess = $null
    if ($env:BACKEND_LOGS_VISIBLE -ieq 'true') {
        $quotedArguments = $backendArguments | ForEach-Object {
            if ($_ -match '\s') { '"{0}"' -f ($_ -replace '"', '""') } else { $_ }
        }
        $backendCommand = 'cd /d "{0}" && "{1}" {2}' -f $backendWorkingDirectory, $venvPython, ($quotedArguments -join ' ')
        $backendProcess = Start-Process -FilePath 'cmd.exe' -ArgumentList @('/d', '/k', $backendCommand) -WorkingDirectory $backendWorkingDirectory -WindowStyle Normal -PassThru
    }
    else {
        $backendProcess = Start-Process -FilePath $venvPython -ArgumentList $backendArguments -WorkingDirectory $backendWorkingDirectory -WindowStyle Hidden -PassThru
    }

    Write-Status WAIT "Waiting for backend readiness at $backendHealthUri"
    if (-not (Wait-HttpHealth -Uri $backendHealthUri -TimeoutSeconds 60 -IntervalSeconds 1)) {
        throw "Backend did not become ready within 60 seconds at $backendHealthUri."
    }
    Write-Status OK 'Backend health check passed.'

    Write-Status RUN 'Launching frontend preview'
    $frontendProcess = Start-Process -FilePath $NpmCmd -ArgumentList @('run', 'preview', '--', '--host', $env:UI_HOST, '--port', "$uiPort") -WorkingDirectory $ClientDir -WindowStyle Hidden -PassThru
    if (-not (Wait-HttpHealth -Uri $uiUri -TimeoutSeconds 60 -IntervalSeconds 1)) {
        throw "Frontend preview did not become ready within 60 seconds at $uiUri."
    }

    Start-Process $uiUri
    $backendPid = @(Get-PortListenerPids -Port $fastApiPort) | Select-Object -First 1
    $frontendPid = @(Get-PortListenerPids -Port $uiPort) | Select-Object -First 1
    if (-not $backendPid -and $backendProcess) { $backendPid = $backendProcess.Id }
    if (-not $frontendPid) { $frontendPid = $frontendProcess.Id }

    Write-Host ''
    Write-Status SUCCESS 'AEGIS started successfully.'
    Write-Host "  Backend: $backendHealthUri (PID $backendPid)"
    Write-Host "  Frontend: $uiUri (PID $frontendPid)"
}

function Invoke-InstallOrUpdate {
    Import-EnvironmentFile
    Set-LauncherEnvironment
    Ensure-PortableRuntimes
    Write-Status OK 'Portable runtimes ready.'
    $installationType = Read-InstallationType
    Sync-Dependencies -BuildFrontend $true -InstallationType $installationType
    if (Test-Path -LiteralPath $UvCacheDir) {
        [void](Remove-PathBestEffort -Path $UvCacheDir -Recurse)
    }
    Write-Status SUCCESS 'Dependencies installed, frontend built, and uv cache pruning attempted.'
}

function Read-InstallationType {
    Write-Host '  [1] Development - include Ruff, Pyright, and pytest'
    Write-Host '  [2] Standard    - install runtime dependencies only'
    $selection = (Read-Host '  Select installation profile [1-2]').Trim()
    switch ($selection) {
        '1' { return 'Development' }
        '2' { return 'Standard' }
        default { throw 'Invalid installation profile. Enter 1 for Development or 2 for Standard.' }
    }
}

function Invoke-InitializeDatabase {
    Import-EnvironmentFile
    Set-LauncherEnvironment
    Ensure-PortableRuntimes
    if (-not (Test-Path -LiteralPath $InitializeDatabaseScript)) {
        throw "Missing database initialization script: $InitializeDatabaseScript"
    }

    Push-Location $AppDir
    try {
        & $UvExe run --project server --python $PythonExe python -m scripts.initialize_database
        if ($LASTEXITCODE -ne 0) {
            throw "Database initialization failed with exit code $LASTEXITCODE."
        }
    }
    finally {
        Pop-Location
    }
    Write-Status SUCCESS 'Database initialization completed.'
}

# -----------------------------------------------------------------------------
# SOURCE CONTROL ACTIONS
# -----------------------------------------------------------------------------
function Get-GitExecutable {
    $gitCommand = Get-Command git.exe -CommandType Application -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if (-not $gitCommand) {
        throw 'Git was not found on PATH. Install Git before using source-control options.'
    }
    return $gitCommand.Path
}

function Invoke-GitCommand {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string[]]$Arguments
    )

    $gitExecutable = Get-GitExecutable
    $display = "git $($Arguments -join ' ')"
    $activity = "AEGIS: $display"
    $progressId = Start-LauncherProgress -Activity $activity -Status 'Running Git command'
    Write-Status RUN $display
    try {
        $output = @(& $gitExecutable -C $RootDir @Arguments)
        $exitCode = if ($null -eq $LASTEXITCODE) { 0 } else { [int]$LASTEXITCODE }
    }
    finally {
        Complete-LauncherProgress $progressId
    }
    if ($exitCode -ne 0) {
        throw "Git command failed: $display (exit code $exitCode)."
    }
    Write-Status OK "Completed $display"
    return $output
}

function Invoke-ApplicationUpdate {
    $statusLines = @(Invoke-GitCommand -Arguments @('status', '--porcelain'))
    if ($statusLines.Count -gt 0) {
        throw 'The working tree contains local changes. Commit or stash them before updating from main.'
    }

    $currentBranch = (@(Invoke-GitCommand -Arguments @('branch', '--show-current')) -join [Environment]::NewLine).Trim()
    if (-not $currentBranch) {
        throw 'The repository is in a detached HEAD state. Switch to a local branch before updating.'
    }

    if ($currentBranch -ne 'main') {
        throw "Update requires the main branch to be checked out; current branch is '$currentBranch'. No files were changed."
    }

    Write-Status RUN 'Updating the application from origin/main with git pull.'
    Invoke-GitCommand -Arguments @('pull', '--ff-only', 'origin', 'main') |
        ForEach-Object { Write-Host "  $_" }
    Write-Status SUCCESS 'Application update from origin/main completed.'
}

function Invoke-CheckForUpdates {
    $localMainCommit = ((Invoke-GitCommand -Arguments @('rev-parse', 'main')) | Select-Object -First 1).Trim()
    if (-not $localMainCommit) {
        throw 'The local main branch could not be resolved.'
    }

    Write-Status RUN 'Checking origin/main for a newer application version (read-only).'
    $gitExecutable = Get-GitExecutable
    $remoteLines = @(& $gitExecutable -C $RootDir ls-remote origin refs/heads/main)
    if ($LASTEXITCODE -ne 0) {
        throw 'Unable to check origin/main. Verify the Git remote and network connection.'
    }
    $remoteLine = $remoteLines | Select-Object -First 1
    $remoteCommit = if ($remoteLine) { ($remoteLine -split "`t", 2)[0].Trim() } else { '' }
    if (-not $remoteCommit) {
        throw 'The origin/main branch could not be resolved.'
    }

    if ($remoteCommit -eq $localMainCommit) {
        Write-Status SUCCESS 'The local main branch is up to date with origin/main.'
        return
    }

    Write-Status WARN 'A newer or different main branch revision is available on origin.'
    Write-Host "  Local main:  $localMainCommit" -ForegroundColor DarkGray
    Write-Host "  Origin main: $remoteCommit" -ForegroundColor DarkGray
    Write-Status INFO 'No files were downloaded or changed. Use Update application to apply the revision.'
}

# -----------------------------------------------------------------------------
# DATABASE, DATA, AND MAINTENANCE ACTIONS
# -----------------------------------------------------------------------------
function Get-ConfiguredDataDirectory {
    $configuredDataDir = if ($null -eq $env:AEGIS_DATA_DIR) { '' } else { $env:AEGIS_DATA_DIR.Trim() }
    if (-not $configuredDataDir) {
        return $DefaultRuntimeDataDir
    }

    if ($configuredDataDir.StartsWith('~')) {
        $userProfileDir = [Environment]::GetFolderPath('UserProfile')
        $configuredDataDir = Join-Path $userProfileDir $configuredDataDir.TrimStart([char]'~', [char]'\', [char]'/')
    }
    if ([IO.Path]::IsPathRooted($configuredDataDir)) {
        return [IO.Path]::GetFullPath($configuredDataDir)
    }
    return [IO.Path]::GetFullPath((Join-Path $RootDir $configuredDataDir))
}

function Get-NormalizedPath {
    param([Parameter(Mandatory)][string]$Path)

    return ([IO.Path]::GetFullPath($Path)).TrimEnd([char]'\', [char]'/')
}

function Test-SafeDataDirectory {
    param([Parameter(Mandatory)][string]$Path)

    $candidate = Get-NormalizedPath -Path $Path
    $root = Get-NormalizedPath -Path $RootDir
    $protectedPaths = @(
        $root,
        (Get-NormalizedPath -Path $AppDir),
        (Get-NormalizedPath -Path $ResourcesDir),
        (Get-NormalizedPath -Path $ServerDir),
        (Get-NormalizedPath -Path $ClientDir),
        (Get-NormalizedPath -Path $SettingsDir),
        (Get-NormalizedPath -Path $RuntimesDir)
    )

    if ($candidate -eq (Get-NormalizedPath -Path $DefaultRuntimeDataDir)) {
        return
    }
    if ($candidate -in $protectedPaths) {
        throw "Refusing to remove application files from the configured data path: $Path"
    }
    if ($root.StartsWith("$candidate\", [StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to remove a data path that contains the application checkout: $Path"
    }
}

function Remove-DirectoryContents {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$Path,
        [string[]]$PreserveNames = @('.gitkeep')
    )

    $result = [ordered]@{
        Path = $Path
        Removed = 0
        Skipped = 0
    }
    if (-not (Test-Path -LiteralPath $Path)) {
        return [pscustomobject]$result
    }

    try {
        $children = @(Get-ChildItem -LiteralPath $Path -Force -ErrorAction Stop)
    }
    catch {
        Write-Status WARN "Skipped inaccessible data directory: $Path ($($_.Exception.Message))"
        $result.Skipped++
        return [pscustomobject]$result
    }

    $progressId = Start-LauncherProgress -Activity "AEGIS: remove data from $Path" -Status "0 of $($children.Count) items"
    try {
        for ($index = 0; $index -lt $children.Count; $index++) {
            $child = $children[$index]
            if ($child.Name -in $PreserveNames) {
                continue
            }
            Update-LauncherProgress -Id $progressId -Activity "AEGIS: remove data from $Path" -Status "$($index + 1) of $($children.Count): $($child.Name)" -PercentComplete ([int](($index + 1) * 100 / [Math]::Max(1, $children.Count)))
            if (Remove-PathBestEffort -Path $child.FullName -Recurse) {
                $result.Removed++
            }
            else {
                $result.Skipped++
            }
        }
    }
    finally {
        Complete-LauncherProgress $progressId
    }
    return [pscustomobject]$result
}

function Invoke-RemoveAllData {
    Import-EnvironmentFile
    $configuredDataDir = Get-ConfiguredDataDirectory
    Test-SafeDataDirectory -Path $configuredDataDir

    $targets = @(
        $configuredDataDir,
        $IngestionDataDir,
        $VectorsDir,
        $LogsDir
    ) | ForEach-Object { Get-NormalizedPath -Path $_ } | Select-Object -Unique

    Write-Host ''
    Write-Host '  Remove all user-generated application data?' -ForegroundColor Yellow
    Write-Host '  This permanently deletes the SQLite database, runtime data, ingested files, generated vectors, and logs.' -ForegroundColor Yellow
    Write-Host '  Application source files, catalogs, settings templates, dependencies, and lockfiles are preserved.' -ForegroundColor DarkGray
    Write-Host "  Runtime data path: $configuredDataDir" -ForegroundColor DarkGray
    $confirmation = (Read-Host '  Type REMOVE ALL DATA to continue').Trim()
    if ($confirmation -cne 'REMOVE ALL DATA') {
        Write-Status INFO 'Remove all data cancelled.'
        return
    }

    Write-Status INFO 'Stopping configured local application services before removing data.'
    $applicationPorts = @([int]$env:FASTAPI_PORT, [int]$env:UI_PORT) | Select-Object -Unique
    foreach ($port in $applicationPorts) {
        Stop-PortListeners -Port $port
    }

    $removed = 0
    $skipped = 0
    foreach ($target in $targets) {
        $result = Remove-DirectoryContents -Path $target
        $removed += $result.Removed
        $skipped += $result.Skipped
    }
    $statusLevel = if ($skipped -gt 0) { 'WARN' } else { 'SUCCESS' }
    Write-Status $statusLevel "User-generated data removal completed where permitted; removed $removed item(s), skipped $skipped locked or inaccessible item(s)."
}

function Invoke-TestSuite {
    if (-not (Test-Path -LiteralPath $TestScript)) {
        throw "Missing test runner: $TestScript"
    }
    & cmd.exe /d /c $TestScript
    $exitCode = $LASTEXITCODE
    if ($exitCode -ne 0) {
        throw "Test suite failed with exit code $exitCode."
    }
    Write-Status SUCCESS 'Test suite completed successfully.'
}

function Remove-ApplicationLogs {
    if (-not (Test-Path -LiteralPath $LogsDir)) {
        Write-Status INFO "Log directory does not exist: $LogsDir"
        return
    }
    $logs = @(Get-ChildItem -LiteralPath $LogsDir -Filter '*.log' -File -ErrorAction SilentlyContinue)
    if ($logs.Count -eq 0) {
        Write-Status INFO 'No log files found.'
        return
    }
    $removed = 0
    $skipped = 0
    $progressId = Start-LauncherProgress -Activity 'AEGIS: remove application logs' -Status "0 of $($logs.Count) files"
    try {
        for ($index = 0; $index -lt $logs.Count; $index++) {
            $log = $logs[$index]
            $percent = [int](($index + 1) * 100 / $logs.Count)
            Update-LauncherProgress -Id $progressId -Activity 'AEGIS: remove application logs' -Status "$($index + 1) of $($logs.Count): $($log.Name)" -PercentComplete $percent
            if (Remove-PathBestEffort -Path $log.FullName) {
                $removed++
            }
            else {
                $skipped++
            }
        }
    }
    finally {
        Complete-LauncherProgress $progressId
    }
    Write-Status SUCCESS "Removed $removed log file(s); skipped $skipped locked or inaccessible file(s)."
}

function Remove-PathBestEffort {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$Path,
        [switch]$Recurse
    )

    try {
        $item = Get-Item -LiteralPath $Path -Force -ErrorAction Stop
    }
    catch {
        Write-Status WARN "Skipped inaccessible path: $Path ($($_.Exception.Message))"
        return $false
    }

    if ($Recurse -and $item.PSIsContainer) {
        try {
            $children = @(Get-ChildItem -LiteralPath $item.FullName -Force -ErrorAction Stop)
        }
        catch {
            Write-Status WARN "Skipped inaccessible directory: $Path ($($_.Exception.Message))"
            return $false
        }

        $childFailure = $false
        $progressId = Start-LauncherProgress -Activity "AEGIS: remove $($item.Name)" -Status "0 of $($children.Count) items"
        try {
            for ($index = 0; $index -lt $children.Count; $index++) {
                $child = $children[$index]
                $percent = if ($children.Count -eq 0) { 100 } else { [int](($index + 1) * 100 / $children.Count) }
                Update-LauncherProgress -Id $progressId -Activity "AEGIS: remove $($item.Name)" -Status "$($index + 1) of $($children.Count): $($child.Name)" -PercentComplete $percent
                if (-not (Remove-PathBestEffort -Path $child.FullName -Recurse)) {
                    $childFailure = $true
                }
            }
        }
        finally {
            Complete-LauncherProgress $progressId
        }
        if ($childFailure) {
            return $false
        }
    }

    try {
        $removeParameters = @{
            LiteralPath = $item.FullName
            Force = $true
            ErrorAction = 'Stop'
        }
        if ($Recurse) {
            $removeParameters.Recurse = $true
        }
        Remove-Item @removeParameters
        return $true
    }
    catch {
        Write-Status WARN "Skipped locked or protected path: $($item.FullName) ($($_.Exception.Message))"
        return $false
    }
}

function Remove-PythonCaches {
    $scriptsDir = Join-Path $AppDir 'scripts'
    $searchRoots = @(
        Get-ChildItem -LiteralPath $ServerDir -Directory -Force -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -ne '.venv' } |
            Select-Object -ExpandProperty FullName
        $TestsDir
        $scriptsDir
    )
    $cacheDirectories = @(
        Get-ChildItem -LiteralPath $ServerDir -Directory -Filter '__pycache__' -Force -ErrorAction SilentlyContinue
        foreach ($searchRoot in $searchRoots) {
            if (Test-Path -LiteralPath $searchRoot) {
                Get-ChildItem -LiteralPath $searchRoot -Directory -Filter '__pycache__' -Recurse -Force -ErrorAction SilentlyContinue
            }
        }
    ) | Sort-Object FullName -Descending
    foreach ($cacheDirectory in $cacheDirectories) {
        [void](Remove-PathBestEffort -Path $cacheDirectory.FullName -Recurse)
    }
}

function Clear-ApplicationCache {
    Remove-PythonCaches
    $cacheRoots = @($RuntimeCacheDir, $ToolCacheDir) + $LegacyCachePaths
    $skipped = 0
    $uniqueCacheRoots = @($cacheRoots | Select-Object -Unique)
    $progressId = Start-LauncherProgress -Activity 'AEGIS: clear caches' -Status "0 of $($uniqueCacheRoots.Count) roots"
    try {
        for ($rootIndex = 0; $rootIndex -lt $uniqueCacheRoots.Count; $rootIndex++) {
            $cacheRoot = $uniqueCacheRoots[$rootIndex]
            Update-LauncherProgress -Id $progressId -Activity 'AEGIS: clear caches' -Status "Root $($rootIndex + 1) of $($uniqueCacheRoots.Count): $cacheRoot" -PercentComplete ([int](($rootIndex + 1) * 100 / [Math]::Max(1, $uniqueCacheRoots.Count)))
        try {
            $cacheRootExists = Test-Path -LiteralPath $cacheRoot -ErrorAction Stop
        }
        catch {
            Write-Status WARN "Skipped inaccessible cache directory: $cacheRoot ($($_.Exception.Message))"
            $skipped++
            continue
        }
        if (-not $cacheRootExists) {
            continue
        }
        try {
            $children = @(Get-ChildItem -LiteralPath $cacheRoot -Force -ErrorAction Stop)
        }
        catch {
            Write-Status WARN "Skipped inaccessible cache directory: $cacheRoot ($($_.Exception.Message))"
            $skipped++
            continue
        }
        foreach ($child in $children) {
            if ($child.Name -eq '.gitkeep') {
                continue
            }
            if (-not (Remove-PathBestEffort -Path $child.FullName -Recurse)) {
                $skipped++
            }
        }
        }
    }
    finally {
        Complete-LauncherProgress $progressId
    }
    New-Item -ItemType Directory -Path $RuntimeCacheDir, $ToolCacheDir -Force | Out-Null
    Write-Status SUCCESS "Development caches cleared where permitted; skipped $skipped locked or inaccessible item(s)."
}

function Uninstall-Application {
    $targets = @(
        $RuntimesDir,
        $LegacyCacheDir,
        $VenvDir,
        (Join-Path $RootDir '.venv'),
        (Join-Path $ClientDir 'node_modules'),
        (Join-Path $ClientDir '.angular'),
        (Join-Path $ClientDir 'dist')
    )
    $skipped = 0
    $progressId = Start-LauncherProgress -Activity 'AEGIS: uninstall application' -Status "0 of $($targets.Count) paths"
    try {
        for ($index = 0; $index -lt $targets.Count; $index++) {
            $target = $targets[$index]
            Update-LauncherProgress -Id $progressId -Activity 'AEGIS: uninstall application' -Status "$($index + 1) of $($targets.Count): $target" -PercentComplete ([int](($index + 1) * 100 / [Math]::Max(1, $targets.Count)))
        try {
            $targetExists = Test-Path -LiteralPath $target -ErrorAction Stop
        }
        catch {
            Write-Status WARN "Skipped inaccessible uninstall target: $target ($($_.Exception.Message))"
            $skipped++
            continue
        }
        if ($targetExists -and -not (Remove-PathBestEffort -Path $target -Recurse)) {
            $skipped++
        }
    }
    }
    finally {
        Complete-LauncherProgress $progressId
    }

    # Keep dependency lockfiles: install/update uses them for reproducible restores.
    New-Item -ItemType Directory -Path $RuntimesDir -Force | Out-Null
    $runtimeKeepFile = Join-Path $RuntimesDir '.gitkeep'
    if (-not (Test-Path -LiteralPath $runtimeKeepFile)) {
        New-Item -ItemType File -Path $runtimeKeepFile -Force | Out-Null
    }
    Remove-PythonCaches
    Write-Status SUCCESS "Application runtimes, dependencies, caches, and build outputs uninstalled where permitted; skipped $skipped locked or inaccessible item(s). Dependency lockfiles and user data were preserved."
}

function Wait-ForMenuReturn {
    Write-Host ''
    Write-Host '  Press any key to return to the menu...' -ForegroundColor DarkGray
    if ([Console]::IsInputRedirected) {
        return
    }
    [Console]::ReadKey($true) | Out-Null
}

function Write-MenuRule {
    param([string]$Character = '-')

    Write-Host "  $($Character * 57)" -ForegroundColor DarkCyan
}

function Write-MenuSection {
    param([Parameter(Mandatory)][string]$Title)

    Write-Host "  $Title" -ForegroundColor DarkCyan
}

function Write-MenuOption {
    param(
        [Parameter(Mandatory)][string]$Number,
        [Parameter(Mandatory)][string]$Label,
        [Parameter(Mandatory)][string]$Description,
        [switch]$Destructive,
        [switch]$Exit
    )

    $numberColor = if ($Destructive) { 'Yellow' } elseif ($Exit) { 'DarkGray' } else { 'Cyan' }
    $labelColor = if ($Destructive) { 'Yellow' } elseif ($Exit) { 'Gray' } else { 'White' }
    Write-Host "  [$Number] " -ForegroundColor $numberColor -NoNewline
    Write-Host $Label.PadRight(31) -ForegroundColor $labelColor -NoNewline
    Write-Host $Description -ForegroundColor DarkGray
}

function Show-LauncherMenu {
    if (-not [Console]::IsInputRedirected -and -not [Console]::IsOutputRedirected) {
        Clear-Host
    }
    Write-Host ''
    Write-MenuRule
    Write-Host '  AEGIS' -ForegroundColor Cyan -NoNewline
    Write-Host '  /  GEOSPATIAL VIEW' -ForegroundColor White
    Write-Host '  Local application control center' -ForegroundColor DarkGray
    Write-MenuRule
    Write-Host ''
    Write-MenuSection -Title 'APPLICATION'
    Write-MenuOption -Number '1' -Label 'Launch application' -Description 'Start local services'
    Write-MenuOption -Number '2' -Label 'Install / update dependencies' -Description 'Sync and build'
    Write-MenuOption -Number '3' -Label 'Rebuild frontend' -Description 'Run frontend production build'
    Write-MenuOption -Number '4' -Label 'Initialize database' -Description 'Create, upgrade, and seed SQLite schema'
    Write-Host ''
    Write-MenuSection -Title 'MAINTENANCE'
    Write-MenuOption -Number '5' -Label 'Run test suite' -Description 'Validate installation'
    Write-MenuOption -Number '6' -Label 'Remove logs' -Description 'Clear application logs'
    Write-MenuOption -Number '7' -Label 'Clear cache' -Description 'Remove runtime and test caches'
    Write-MenuOption -Number '8' -Label 'Uninstall application' -Description 'Remove local dependencies' -Destructive
    Write-Host ''
    Write-MenuSection -Title 'UPDATES'
    Write-MenuOption -Number '9' -Label 'Update application' -Description 'Pull the latest main branch'
    Write-MenuOption -Number '10' -Label 'Check for updates' -Description 'Report main branch status only'
    Write-Host ''
    Write-MenuSection -Title 'DATA MANAGEMENT'
    Write-MenuOption -Number '11' -Label 'Remove all data' -Description 'Delete user-generated data' -Destructive
    Write-Host ''
    Write-MenuRule
    Write-MenuSection -Title 'EXIT'
    Write-MenuOption -Number '12' -Label 'Exit' -Description 'Close launcher' -Exit
    Write-MenuRule
    Write-Host ''
}

while ($true) {
    Show-LauncherMenu
    $selection = (Read-Host '  Select an option (1-12)').Trim()

    if ($selection -notmatch '^(?:[1-9]|1[0-2])$') {
        Write-Status WARN 'Invalid option. Enter a number from 1 to 12.'
        Wait-ForMenuReturn
        continue
    }

    if ($selection -eq '12') {
        break
    }

    try {
        Invoke-TrackedLauncherAction -Name "menu option $selection" -Action {
            switch ($selection) {
                '1' {
                    Invoke-LaunchApplication
                    exit 0
                }
                '2' { Invoke-InstallOrUpdate }
                '3' { Invoke-RebuildFrontend }
                '4' { Invoke-InitializeDatabase }
                '5' { Invoke-TestSuite }
                '6' { Remove-ApplicationLogs }
                '7' { Clear-ApplicationCache }
                '8' { Uninstall-Application }
                '9' { Invoke-ApplicationUpdate }
                '10' { Invoke-CheckForUpdates }
                '11' { Invoke-RemoveAllData }
            }
        }
    }
    catch {
        Write-Status FATAL $_.Exception.Message
        if ([Console]::IsInputRedirected) {
            exit 1
        }
    }

    Wait-ForMenuReturn
}
Clear-LauncherProgress
