@echo off
setlocal EnableDelayedExpansion

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..\..") do set "PROJECT_ROOT=%%~fI"
set "APP_DIR=%PROJECT_ROOT%\app"
set "SERVER_DIR=%APP_DIR%\server"
set "CLIENT_DIR=%APP_DIR%\client"
set "TESTS_DIR=%APP_DIR%\tests"
set "CACHE_DIR=%PROJECT_ROOT%\assets\cache"
set "PYTHON_BYTECODE_CACHE_DIR=%CACHE_DIR%\python"
set "PYTEST_CACHE_DIR=%CACHE_DIR%\pytest"
set "PYTEST_TEMP_DIR=%CACHE_DIR%\pytest-tmp"
set "RUFF_CACHE_DIR=%CACHE_DIR%\ruff"
set "UV_CACHE_DIR=%CACHE_DIR%\uv"
set "NPM_CACHE_DIR=%CACHE_DIR%\npm"
set "PIP_CACHE_DIR=%CACHE_DIR%\pip"
set "COVERAGE_DIR=%CACHE_DIR%\coverage"
set "PLAYWRIGHT_BROWSERS_DIR=%CACHE_DIR%\playwright-browsers"
set "SETTINGS_ENV=%PROJECT_ROOT%\settings\.env"
set "VENV_PYTHON=%SERVER_DIR%\.venv\Scripts\python.exe"
set "RUNTIME_NPM=%PROJECT_ROOT%\runtimes\nodejs\npm.cmd"

set "FASTAPI_HOST=127.0.0.1"
set "FASTAPI_PORT=8000"
set "UI_HOST=127.0.0.1"
set "UI_PORT=8001"
set "TEST_RESULT=0"
set "LIVE_SERVER_PHASE=SKIPPED"
set "PYTEST_PHASE=SKIPPED"
set "FRONTEND_BOOTSTRAP_PHASE=SKIPPED"
set "FRONTEND_UNIT_PHASE=SKIPPED"
set "FRONTEND_E2E_PHASE=SKIPPED"
set "STARTED_BACKEND=0"
set "STARTED_FRONTEND=0"
set "SKIP_LIVE_SERVERS=0"
set "SKIP_FRONTEND=0"
if not exist "%CACHE_DIR%" mkdir "%CACHE_DIR%"
if not exist "%PYTHON_BYTECODE_CACHE_DIR%" mkdir "%PYTHON_BYTECODE_CACHE_DIR%"
if not exist "%PYTEST_CACHE_DIR%" mkdir "%PYTEST_CACHE_DIR%"
if not exist "%PYTEST_TEMP_DIR%" mkdir "%PYTEST_TEMP_DIR%"
if not exist "%RUFF_CACHE_DIR%" mkdir "%RUFF_CACHE_DIR%"
if not exist "%UV_CACHE_DIR%" mkdir "%UV_CACHE_DIR%"
if not exist "%NPM_CACHE_DIR%" mkdir "%NPM_CACHE_DIR%"
if not exist "%PIP_CACHE_DIR%" mkdir "%PIP_CACHE_DIR%"
if not exist "%COVERAGE_DIR%" mkdir "%COVERAGE_DIR%"
if not exist "%PLAYWRIGHT_BROWSERS_DIR%" mkdir "%PLAYWRIGHT_BROWSERS_DIR%"
set "PYTHONPYCACHEPREFIX=%PYTHON_BYTECODE_CACHE_DIR%"
set "UV_CACHE_DIR=%UV_CACHE_DIR%"
set "RUFF_CACHE_DIR=%RUFF_CACHE_DIR%"
set "NPM_CONFIG_CACHE=%NPM_CACHE_DIR%"
set "PIP_CACHE_DIR=%PIP_CACHE_DIR%"
set "PLAYWRIGHT_BROWSERS_PATH=%PLAYWRIGHT_BROWSERS_DIR%"
set "COVERAGE_FILE=%COVERAGE_DIR%\.coverage"
if /i "%STANDARD_TEST_SKIP_LIVE_SERVERS%"=="true" set "SKIP_LIVE_SERVERS=1"
if "%STANDARD_TEST_SKIP_LIVE_SERVERS%"=="1" set "SKIP_LIVE_SERVERS=1"
if /i "%STANDARD_TEST_SKIP_FRONTEND%"=="true" set "SKIP_FRONTEND=1"
if "%STANDARD_TEST_SKIP_FRONTEND%"=="1" set "SKIP_FRONTEND=1"

if exist "%SETTINGS_ENV%" (
  for /f "usebackq tokens=* delims=" %%L in ("%SETTINGS_ENV%") do (
    set "line=%%L"
    if not "!line!"=="" if "!line:~0,1!" NEQ "#" if "!line:~0,1!" NEQ ";" (
      for /f "tokens=1,* delims==" %%A in ("!line!") do (
        if /i "%%A"=="FASTAPI_HOST" set "FASTAPI_HOST=%%B"
        if /i "%%A"=="FASTAPI_PORT" set "FASTAPI_PORT=%%B"
        if /i "%%A"=="UI_HOST" set "UI_HOST=%%B"
        if /i "%%A"=="UI_PORT" set "UI_PORT=%%B"
      )
    )
  )
)

set "TEST_FASTAPI_HOST=%FASTAPI_HOST%"
set "TEST_UI_HOST=%UI_HOST%"
if /i "%TEST_FASTAPI_HOST%"=="0.0.0.0" set "TEST_FASTAPI_HOST=127.0.0.1"
if /i "%TEST_FASTAPI_HOST%"=="::" set "TEST_FASTAPI_HOST=127.0.0.1"
if /i "%TEST_UI_HOST%"=="0.0.0.0" set "TEST_UI_HOST=127.0.0.1"
if /i "%TEST_UI_HOST%"=="::" set "TEST_UI_HOST=127.0.0.1"

set "APP_TEST_BACKEND_URL=http://%TEST_FASTAPI_HOST%:%FASTAPI_PORT%"
set "APP_TEST_FRONTEND_URL=http://%TEST_UI_HOST%:%UI_PORT%"
set "API_BASE_URL=%APP_TEST_BACKEND_URL%"
set "UI_BASE_URL=%APP_TEST_FRONTEND_URL%"

if exist "%VENV_PYTHON%" (
  set "PYTHON_CMD=%VENV_PYTHON%"
) else (
  echo [ERROR] Missing backend venv: "%VENV_PYTHON%"
  exit /b 1
)

if exist "%RUNTIME_NPM%" (
  set "NPM_CMD=%RUNTIME_NPM%"
) else (
  set "NPM_CMD=npm"
)

set "UVICORN_APP=server.app:app"
set "BACKEND_WORKDIR=%APP_DIR%"
set "PYTHONPATH=%APP_DIR%"

set "PYTEST_TARGET=%TESTS_DIR%"
if not "%STANDARD_TEST_PYTEST_TARGET%"=="" set "PYTEST_TARGET=%STANDARD_TEST_PYTEST_TARGET%"

set "NEED_FRONTEND=0"
echo %PYTEST_TARGET% | findstr /I "\\e2e" >nul 2>&1
if not errorlevel 1 set "NEED_FRONTEND=1"
if /i "%PYTEST_TARGET%"=="%TESTS_DIR%" set "NEED_FRONTEND=1"
if "%SKIP_FRONTEND%"=="1" set "NEED_FRONTEND=0"


echo.
echo ============================================================
echo  Standard Test Runner
echo ============================================================
echo [INFO] Project root: %PROJECT_ROOT%
echo [INFO] Backend URL : %APP_TEST_BACKEND_URL%
echo [INFO] Frontend URL: %APP_TEST_FRONTEND_URL%
echo [INFO] Target      : %PYTEST_TARGET%
echo.

if "%SKIP_LIVE_SERVERS%"=="1" goto run_pytests

set "LIVE_SERVER_PHASE=PASS"
curl -s --max-time 2 "%APP_TEST_BACKEND_URL%/docs" >nul 2>&1
if errorlevel 1 (
  echo [INFO] Starting backend server...
  start "" /B /D "%BACKEND_WORKDIR%" "%PYTHON_CMD%" -m uvicorn %UVICORN_APP% --host %FASTAPI_HOST% --port %FASTAPI_PORT% --log-level warning --ws-max-size 65536 --ws-ping-interval 15 --ws-ping-timeout 10
  set "STARTED_BACKEND=1"
)

if "%NEED_FRONTEND%"=="1" (
  if not exist "%CLIENT_DIR%\node_modules" (
    echo [INFO] Installing frontend dependencies...
    call "%NPM_CMD%" --prefix "%CLIENT_DIR%" install
    if errorlevel 1 set "TEST_RESULT=1" & goto cleanup
  )
  echo [INFO] Starting frontend preview server...
  start "" /B /D "%CLIENT_DIR%" "%NPM_CMD%" run preview -- --host %UI_HOST% --port %UI_PORT%
  set "STARTED_FRONTEND=1"
)

set "ATTEMPTS=0"
:wait_loop
if %ATTEMPTS% geq 90 (
  set "LIVE_SERVER_PHASE=FAIL"
  set "TEST_RESULT=1"
  goto cleanup
)
curl -s --max-time 2 "%APP_TEST_BACKEND_URL%/docs" >nul 2>&1
if errorlevel 1 (
  set /a ATTEMPTS+=1
  timeout /t 1 /nobreak >nul
  goto wait_loop
)
if "%NEED_FRONTEND%"=="1" (
  curl -s --max-time 2 "%APP_TEST_FRONTEND_URL%" >nul 2>&1
  if errorlevel 1 (
    set /a ATTEMPTS+=1
    timeout /t 1 /nobreak >nul
    goto wait_loop
  )
)

:run_pytests
echo [STEP] Running Python tests...
"%PYTHON_CMD%" -m pytest -c "%SERVER_DIR%\pyproject.toml" -o "cache_dir=%PYTEST_CACHE_DIR%" --basetemp "%PYTEST_TEMP_DIR%" "%PYTEST_TARGET%" -v --tb=short %*
if errorlevel 1 (
  set "PYTEST_PHASE=FAIL"
  set "TEST_RESULT=1"
) else (
  set "PYTEST_PHASE=PASS"
)

:cleanup
if "%STARTED_BACKEND%"=="1" (
  for /f "tokens=5" %%P in ('netstat -ano ^| findstr LISTENING ^| findstr ":%FASTAPI_PORT%"') do taskkill /PID %%P /F >nul 2>&1
)
if "%STARTED_FRONTEND%"=="1" (
  for /f "tokens=5" %%P in ('netstat -ano ^| findstr LISTENING ^| findstr ":%UI_PORT%"') do taskkill /PID %%P /F >nul 2>&1
)

echo.
echo ============================================================
echo  Test Summary
echo ============================================================
echo  Live server phase   : %LIVE_SERVER_PHASE%
echo  Python tests        : %PYTEST_PHASE%
echo  Frontend bootstrap  : %FRONTEND_BOOTSTRAP_PHASE%
echo  Frontend unit tests : %FRONTEND_UNIT_PHASE%
echo  Frontend E2E tests  : %FRONTEND_E2E_PHASE%
echo ============================================================
echo.

exit /b %TEST_RESULT%

