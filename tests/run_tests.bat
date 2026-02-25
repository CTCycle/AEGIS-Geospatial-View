@echo off
setlocal enabledelayedexpansion

REM ============================================================================
REM == AEGIS E2E Test Runner
REM == Automatically starts the application, runs tests, and cleans up.
REM ============================================================================

set "tests_folder=%~dp0"
set "project_folder=%tests_folder%..\AEGIS\"
set "root_folder=%tests_folder%..\"
set "runtimes_dir=%project_folder%resources\runtimes"
set "settings_dir=%project_folder%settings"

set "python_dir=%runtimes_dir%\python"
set "python_exe=%python_dir%\python.exe"
set "uv_dir=%runtimes_dir%\uv"
set "uv_exe=%uv_dir%\uv.exe"
set "nodejs_dir=%runtimes_dir%\nodejs"
set "node_exe=%nodejs_dir%\node.exe"
set "npm_cmd=%nodejs_dir%\npm.cmd"

set "DOTENV=%settings_dir%\.env"
set "FRONTEND_DIR=%project_folder%client"
set "FRONTEND_DIST=%FRONTEND_DIR%\dist"
set "UVICORN_MODULE=AEGIS.server.app:app"

title AEGIS Test Runner
echo.
echo ============================================================================
echo    AEGIS E2E Test Runner
echo ============================================================================
echo.

REM ============================================================================
REM == Check prerequisites
REM ============================================================================
if not exist "%python_exe%" (
    echo [ERROR] Python not found. Please run AEGIS\start_on_windows.bat first.
    goto error
)
if not exist "%uv_exe%" (
    echo [ERROR] uv not found. Please run AEGIS\start_on_windows.bat first.
    goto error
)
if not exist "%node_exe%" (
    echo [ERROR] Node.js not found. Please run AEGIS\start_on_windows.bat first.
    goto error
)

echo [OK] All prerequisites found.

REM ============================================================================
REM == Load environment variables
REM ============================================================================
set "FASTAPI_HOST=127.0.0.1"
set "FASTAPI_PORT=8000"
set "UI_HOST=127.0.0.1"
set "UI_PORT=7861"

if exist "%DOTENV%" (
    for /f "usebackq tokens=* delims=" %%L in ("%DOTENV%") do (
        set "line=%%L"
        if not "!line!"=="" if "!line:~0,1!" NEQ "#" if "!line:~0,1!" NEQ ";" (
            for /f "tokens=1* delims==" %%K in ("!line!") do (
                set "k=%%K"
                set "v=%%L"
                if defined v (
                    if "!v:~0,1!"=="\"" set "v=!v:~1,-1!"
                    if "!v:~0,1!"=="'" set "v=!v:~1,-1!"
                )
                set "!k!=!v!"
            )
        )
    )
)

set "FASTAPI_TEST_HOST=%FASTAPI_HOST%"
if /i "%FASTAPI_TEST_HOST%"=="0.0.0.0" set "FASTAPI_TEST_HOST=127.0.0.1"
set "UI_TEST_HOST=%UI_HOST%"
if /i "%UI_TEST_HOST%"=="0.0.0.0" set "UI_TEST_HOST=127.0.0.1"

if not defined APP_TEST_BACKEND_URL set "APP_TEST_BACKEND_URL=http://%FASTAPI_TEST_HOST%:%FASTAPI_PORT%"
if not defined APP_TEST_FRONTEND_URL set "APP_TEST_FRONTEND_URL=http://%UI_TEST_HOST%:%UI_PORT%"
set "API_BASE_URL=%APP_TEST_BACKEND_URL%"
set "UI_BASE_URL=%APP_TEST_FRONTEND_URL%"

echo [INFO] APP_TEST_BACKEND_URL=%APP_TEST_BACKEND_URL%
echo [INFO] APP_TEST_FRONTEND_URL=%APP_TEST_FRONTEND_URL%

REM ============================================================================
REM == Force portable runtimes (avoid global Python/npm)
REM ============================================================================
set "PATH=%python_dir%;%nodejs_dir%;%PATH%"
set "PYTHONHOME=%python_dir%"
set "PYTHONPATH="
set "PYTHONNOUSERSITE=1"
set "VIRTUAL_ENV="
set "__PYVENV_LAUNCHER__="
set "PYTHON=%python_exe%"
set "npm_config_python=%python_exe%"

REM ============================================================================
REM == Configure pytest / Playwright options
REM ============================================================================
if not defined E2E_HEADLESS set "E2E_HEADLESS=true"
if not defined E2E_BROWSER set "E2E_BROWSER=chromium"
if not defined E2E_SLOWMO set "E2E_SLOWMO=0"
if not defined E2E_PWDEBUG set "E2E_PWDEBUG=0"

set "PYTEST_ARGS=tests -v --tb=short"
if defined E2E_BROWSER set "PYTEST_ARGS=!PYTEST_ARGS! --browser !E2E_BROWSER!"
if /i "!E2E_HEADLESS!"=="false" set "PYTEST_ARGS=!PYTEST_ARGS! --headed"
if /i "!E2E_HEADLESS!"=="0" set "PYTEST_ARGS=!PYTEST_ARGS! --headed"
if not "!E2E_SLOWMO!"=="0" set "PYTEST_ARGS=!PYTEST_ARGS! --slowmo !E2E_SLOWMO!"
if /i "!E2E_PWDEBUG!"=="1" set "PWDEBUG=1" & set "PYTEST_ARGS=!PYTEST_ARGS! --headed"
if /i "!E2E_PWDEBUG!"=="true" set "PWDEBUG=1" & set "PYTEST_ARGS=!PYTEST_ARGS! --headed"

REM ============================================================================
REM == Install Playwright browsers if needed
REM ============================================================================
echo [STEP 1/4] Checking Playwright browsers...
"%uv_exe%" run --python "%python_exe%" python -m playwright install chromium >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [INFO] Installing Playwright browsers...
    "%uv_exe%" run --python "%python_exe%" python -m playwright install
)
echo [OK] Playwright browsers ready.

REM ============================================================================
REM == Start backend
REM ============================================================================
echo [STEP 2/4] Starting backend server...
call :kill_port %FASTAPI_PORT%
start "" /b "%uv_exe%" run --python "%python_exe%" python -m uvicorn %UVICORN_MODULE% --host %FASTAPI_HOST% --port %FASTAPI_PORT% --log-level warning

REM Wait for backend to be ready
echo [INFO] Waiting for backend to start...
for /L %%i in (1,1,120) do (
  powershell -NoLogo -NoProfile -ExecutionPolicy Bypass -Command "try { $response = Invoke-WebRequest -Uri '%APP_TEST_BACKEND_URL%/docs' -UseBasicParsing -TimeoutSec 2; if ($response.StatusCode -ge 200) { exit 0 } ; exit 1 } catch { exit 1 }" >nul 2>&1
  if !errorlevel! equ 0 goto :backend_ready_check
  timeout /t 1 /nobreak >nul
)
echo [WARN] Timed out waiting for backend.
:backend_ready_check

REM ============================================================================
REM == Start frontend
REM ============================================================================
echo [STEP 3/4] Starting frontend server...

if not exist "%FRONTEND_DIR%\node_modules" (
    echo [INFO] Installing frontend dependencies...
    pushd "%FRONTEND_DIR%" >nul
    if exist "%FRONTEND_DIR%\package-lock.json" (
        echo [INFO] Detected package-lock.json. Using npm ci...
        call "%npm_cmd%" ci
        set "npm_ec=!ERRORLEVEL!"
        if not "!npm_ec!"=="0" (
            echo [WARN] npm ci failed with code !npm_ec!. Falling back to npm install.
            call "%npm_cmd%" install
            set "npm_ec=!ERRORLEVEL!"
        )
    ) else (
        call "%npm_cmd%" install
        set "npm_ec=!ERRORLEVEL!"
    )
    popd >nul
    if not "!npm_ec!"=="0" (
        echo [FATAL] Frontend dependency installation failed with code !npm_ec!.
        goto error
    )
)

if not exist "%FRONTEND_DIST%" (
    echo [INFO] Building frontend...
    pushd "%FRONTEND_DIR%" >nul
    call "%npm_cmd%" run build
    popd >nul
)

call :kill_port %UI_PORT%
pushd "%FRONTEND_DIR%" >nul
start "" /b "%npm_cmd%" run preview -- --host %UI_HOST% --port %UI_PORT% --strictPort
popd >nul

REM Wait for frontend to be ready
echo [INFO] Waiting for frontend to start...
for /L %%i in (1,1,120) do (
  powershell -NoLogo -NoProfile -ExecutionPolicy Bypass -Command "try { $response = Invoke-WebRequest -Uri '%APP_TEST_FRONTEND_URL%' -UseBasicParsing -TimeoutSec 2; if ($response.StatusCode -ge 200) { exit 0 } ; exit 1 } catch { exit 1 }" >nul 2>&1
  if !errorlevel! equ 0 goto :frontend_ready_check
  timeout /t 1 /nobreak >nul
)
echo [WARN] Timed out waiting for frontend.
:frontend_ready_check

REM ============================================================================
REM == Run tests
REM ============================================================================
echo [STEP 4/4] Running E2E tests...
echo.
echo ============================================================================

pushd "%root_folder%" >nul
"%uv_exe%" run --python "%python_exe%" python -m pytest %PYTEST_ARGS%
set "test_result=%ERRORLEVEL%"
popd >nul

echo.
echo ============================================================================

REM ============================================================================
REM == Cleanup: Stop servers
REM ============================================================================
echo [CLEANUP] Stopping servers...
call :kill_port %FASTAPI_PORT%
call :kill_port %UI_PORT%

if %test_result% EQU 0 (
    echo [SUCCESS] All tests passed!
    endlocal & exit /b 0
) else (
    echo [FAILED] Some tests failed. Exit code: %test_result%
    pause
    endlocal & exit /b %test_result%
)

REM ============================================================================
REM == Error
REM ============================================================================
:error
echo.
echo !!! An error occurred. !!!
pause
endlocal & exit /b 1

REM ============================================================================
REM == Kill process on port
REM ============================================================================
:kill_port
set "target_port=%~1"
if not defined target_port goto :eof
for /f "tokens=5" %%P in ('netstat -ano ^| findstr /R ":%target_port%"') do (
    taskkill /PID %%P /F >nul 2>&1
)
goto :eof
