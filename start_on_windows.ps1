[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$RootDir = $PSScriptRoot
$AppDir = Join-Path $RootDir 'app'
$ServerDir = Join-Path $AppDir 'server'
$ClientDir = Join-Path $AppDir 'client'
$SettingsDir = Join-Path $RootDir 'settings'
$RuntimesDir = Join-Path $RootDir 'runtimes'
$PythonDir = Join-Path $RuntimesDir 'python'
$PythonExe = Join-Path $PythonDir 'python.exe'
$PythonPth = Join-Path $PythonDir 'python314._pth'
$UvDir = Join-Path $RuntimesDir 'uv'
$UvExe = Join-Path $UvDir 'uv.exe'
$NodeDir = Join-Path $RuntimesDir 'nodejs'
$NodeExe = Join-Path $NodeDir 'node.exe'
$NpmCmd = Join-Path $NodeDir 'npm.cmd'
$UvCacheDir = Join-Path $RuntimesDir '.uv-cache'
$VenvDir = Join-Path $ServerDir '.venv'
$DotEnvPath = Join-Path $SettingsDir '.env'
$DotEnvExamplePath = Join-Path $SettingsDir '.env.example'
$LogsDir = Join-Path $AppDir 'resources\logs'
$TestScript = Join-Path $AppDir 'tests\run_tests.bat'
$InitializeDatabaseScript = Join-Path $AppDir 'scripts\initialize_database.py'
$PythonVersion = '3.14.2'
$PythonArchiveName = "python-$PythonVersion-embed-amd64.zip"
$PythonArchiveUri = "https://www.python.org/ftp/python/$PythonVersion/$PythonArchiveName"
$UvAmd64Uri = 'https://github.com/astral-sh/uv/releases/latest/download/uv-x86_64-pc-windows-msvc.zip'
$UvArm64Uri = 'https://github.com/astral-sh/uv/releases/latest/download/uv-aarch64-pc-windows-msvc.zip'
$NodeVersion = '22.12.0'
$NodeArchiveName = "node-v$NodeVersion-win-x64.zip"
$NodeArchiveUri = "https://nodejs.org/dist/v$NodeVersion/$NodeArchiveName"

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
    $ProgressPreference = 'SilentlyContinue'
    New-Item -ItemType Directory -Path (Split-Path -Parent $ArchivePath) -Force | Out-Null
    New-Item -ItemType Directory -Path $DestinationPath -Force | Out-Null
    Invoke-WebRequest -Uri $Uri -OutFile $ArchivePath
    try {
        Expand-Archive -LiteralPath $ArchivePath -DestinationPath $DestinationPath -Force
    }
    finally {
        Remove-Item -LiteralPath $ArchivePath -Force -ErrorAction SilentlyContinue
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
    do {
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

function Initialize-EnvironmentFile {
    if (Test-Path -LiteralPath $DotEnvPath) {
        return
    }
    if (-not (Test-Path -LiteralPath $DotEnvExamplePath)) {
        throw "Missing environment template: $DotEnvExamplePath"
    }

    Copy-Item -LiteralPath $DotEnvExamplePath -Destination $DotEnvPath
    Write-Status INFO "Created settings/.env from settings/.env.example."
}

function Import-EnvironmentFile {
    Initialize-EnvironmentFile

    $defaults = [ordered]@{
        FASTAPI_HOST = '127.0.0.1'
        FASTAPI_PORT = '8000'
        UI_HOST = '127.0.0.1'
        UI_PORT = '8001'
        RELOAD = 'false'
        OPTIONAL_DEPENDENCIES = 'false'
        BACKEND_LOGS_VISIBLE = 'true'
        ALWAYS_REBUILD = 'true'
    }
    foreach ($entry in $defaults.GetEnumerator()) {
        [Environment]::SetEnvironmentVariable($entry.Key, $entry.Value, 'Process')
    }

    foreach ($rawLine in Get-Content -LiteralPath $DotEnvPath) {
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
    $env:UV_CACHE_DIR = $UvCacheDir
    $env:UV_PROJECT_ENVIRONMENT = $VenvDir
    $env:UV_LINK_MODE = 'copy'
    Remove-Item Env:\PYTHONHOME -ErrorAction SilentlyContinue
    Remove-Item Env:\PYTHONPATH -ErrorAction SilentlyContinue
    Remove-Item Env:\PYTHONNOUSERSITE -ErrorAction SilentlyContinue
    $env:PATH = "$NodeDir;$($env:PATH)"
}

function Ensure-PortableRuntimes {
    New-Item -ItemType Directory -Path $RuntimesDir, $PythonDir, $UvDir, $NodeDir -Force | Out-Null

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

function Sync-Dependencies {
    param(
        [bool]$BuildFrontend = $true
    )

    Write-Status STEP 'Installing Python dependencies with uv'
    $uvArguments = @('sync', '--python', $PythonExe, '--locked', '--no-install-project')
    if ($env:OPTIONAL_DEPENDENCIES -ieq 'true') {
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

        if ($BuildFrontend) {
            Write-Status STEP 'Building frontend'
            & $NpmCmd run build
            if ($LASTEXITCODE -ne 0) {
                throw "Frontend build failed with exit code $LASTEXITCODE."
            }
        }
    }
    finally {
        Pop-Location
    }
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
    Ensure-PortableRuntimes
    Sync-Dependencies -BuildFrontend ($env:ALWAYS_REBUILD -ieq 'true')

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

    $backendArguments = @('-m', 'uvicorn', $backendModule, '--host', $env:FASTAPI_HOST, '--port', "$fastApiPort", '--log-level', 'info')
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
    Sync-Dependencies
    if (Test-Path -LiteralPath $UvCacheDir) {
        Remove-Item -LiteralPath $UvCacheDir -Recurse -Force
    }
    Write-Status SUCCESS 'Dependencies installed, frontend built, and uv cache pruned.'
}

function Invoke-InitializeDatabase {
    Import-EnvironmentFile
    Set-LauncherEnvironment
    Ensure-PortableRuntimes
    if (-not (Test-Path -LiteralPath $InitializeDatabaseScript)) {
        throw "Missing database initialization script: $InitializeDatabaseScript"
    }

    Push-Location $RootDir
    try {
        & $UvExe run --project app/server --python $PythonExe python app/scripts/initialize_database.py --drop-existing --seed-catalogs --force-reseed-catalogs
        if ($LASTEXITCODE -ne 0) {
            throw "Database initialization failed with exit code $LASTEXITCODE."
        }
    }
    finally {
        Pop-Location
    }
    Write-Status SUCCESS 'Database initialized and catalogs reseeded.'
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
    $logs | Remove-Item -Force
    Write-Status SUCCESS "Removed $($logs.Count) log file(s)."
}

function Remove-PythonCaches {
    Get-ChildItem -LiteralPath $RootDir -Directory -Filter '__pycache__' -Recurse -Force -ErrorAction SilentlyContinue |
        Sort-Object FullName -Descending |
        Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
}

function Clear-ApplicationCache {
    Remove-PythonCaches
    if (Test-Path -LiteralPath $UvCacheDir) {
        Remove-Item -LiteralPath $UvCacheDir -Recurse -Force
    }
    Write-Status SUCCESS 'Python and uv caches cleared.'
}

function Uninstall-Application {
    $targets = @(
        $RuntimesDir,
        $VenvDir,
        (Join-Path $RootDir '.venv'),
        (Join-Path $ClientDir 'node_modules'),
        (Join-Path $ClientDir '.angular'),
        (Join-Path $ClientDir 'dist')
    )
    foreach ($target in $targets) {
        if (Test-Path -LiteralPath $target) {
            Remove-Item -LiteralPath $target -Recurse -Force
        }
    }

    @(
        (Join-Path $ClientDir 'package-lock.json'),
        (Join-Path $ServerDir 'uv.lock'),
        (Join-Path $RootDir 'uv.lock')
    ) | ForEach-Object {
        if (Test-Path -LiteralPath $_) {
            Remove-Item -LiteralPath $_ -Force
        }
    }
    Remove-PythonCaches
    Write-Status SUCCESS 'Application dependencies and generated caches uninstalled. Settings and user data were preserved.'
}

function Wait-ForMenuReturn {
    Write-Host ''
    Write-Host '  Press any key to return to the menu...' -ForegroundColor DarkGray
    [Console]::ReadKey($true) | Out-Null
}

function Write-MenuRule {
    param([string]$Character = '-')

    Write-Host "  $($Character * 57)" -ForegroundColor DarkCyan
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
    Clear-Host
    Write-Host ''
    Write-MenuRule
    Write-Host '  AEGIS' -ForegroundColor Cyan -NoNewline
    Write-Host '  /  GEOSPATIAL VIEW' -ForegroundColor White
    Write-Host '  Local application control center' -ForegroundColor DarkGray
    Write-MenuRule
    Write-Host ''
    Write-Host '  APPLICATION' -ForegroundColor DarkCyan
    Write-MenuOption -Number '1' -Label 'Launch application' -Description 'Start local services'
    Write-MenuOption -Number '2' -Label 'Install / update dependencies' -Description 'Sync and build'
    Write-MenuOption -Number '3' -Label 'Initialize database' -Description 'Reseed catalogs'
    Write-Host ''
    Write-Host '  MAINTENANCE' -ForegroundColor DarkCyan
    Write-MenuOption -Number '4' -Label 'Run test suite' -Description 'Validate installation'
    Write-MenuOption -Number '5' -Label 'Remove logs' -Description 'Clear application logs'
    Write-MenuOption -Number '6' -Label 'Clear cache' -Description 'Remove Python and uv caches'
    Write-MenuOption -Number '7' -Label 'Uninstall application' -Description 'Remove local dependencies' -Destructive
    Write-Host ''
    Write-MenuRule
    Write-MenuOption -Number '8' -Label 'Exit' -Description 'Close launcher' -Exit
    Write-MenuRule
    Write-Host ''
}

while ($true) {
    Show-LauncherMenu
    $selection = (Read-Host '  Select an option (1-8)').Trim()

    if ($selection -notmatch '^[1-8]$') {
        Write-Status WARN 'Invalid option. Enter a number from 1 to 8.'
        Wait-ForMenuReturn
        continue
    }

    if ($selection -eq '8') {
        break
    }

    try {
        switch ($selection) {
            '1' {
                Invoke-LaunchApplication
                exit 0
            }
            '2' { Invoke-InstallOrUpdate }
            '3' { Invoke-InitializeDatabase }
            '4' { Invoke-TestSuite }
            '5' { Remove-ApplicationLogs }
            '6' { Clear-ApplicationCache }
            '7' { Uninstall-Application }
        }
    }
    catch {
        Write-Status FATAL $_.Exception.Message
    }

    Wait-ForMenuReturn
}
