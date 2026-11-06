@echo off
REM =====================================================================
REM  LM Studio Auto Optimizer - unified launcher (Windows)
REM  One entry point for everything: Web UI, optimize, tests, cleanup.
REM =====================================================================
@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"

set LOGFILE=data\logs\startup.log
if not exist "data\logs" mkdir "data\logs" 2>nul

call :log "=== LM Studio Auto Optimizer launcher ==="
call :log "WorkDir: %CD%"

REM --- Python / venv check ------------------------------------------------
echo [1/3] Checking Python...
python --version >nul 2>&1
if errorlevel 1 goto fail_python
for /f "tokens=*" %%v in ('python --version 2^>^&1') do set PYVER=%%v
echo       Python OK - %PYVER%

echo [2/3] Checking virtual environment and dependencies...
if exist ".venv\Scripts\python.exe" goto deps_check
echo       Creating .venv - one-time step, may take a few minutes...
call :log "creating .venv"
python -m venv .venv >> "%LOGFILE%" 2>&1
if errorlevel 1 goto fail_venv
echo       Installing dependencies - one-time step, may take a few minutes...
call :log "command: pip install -e .[dev]"
".venv\Scripts\python.exe" -m pip install -e ".[dev]" >> "%LOGFILE%" 2>&1
if errorlevel 1 goto fail_deps
goto deps_done

:deps_check
".venv\Scripts\python.exe" -c "import lm_optimizer" >> "%LOGFILE%" 2>&1
if errorlevel 1 goto deps_repair
goto deps_done

:deps_repair
echo       Dependencies missing, installing - may take a few minutes...
call :log "command: pip install -e .[dev] - repair"
".venv\Scripts\python.exe" -m pip install -e ".[dev]" >> "%LOGFILE%" 2>&1
if errorlevel 1 goto fail_deps

:deps_done
set PYBIN=.venv\Scripts\python.exe
echo       Dependencies OK

echo [3/3] Ready - launcher menu
call :log "launcher ready"

REM --- Menu ---------------------------------------------------------------
:menu
echo.
echo ========================================
echo  LM Studio Auto Optimizer
echo ========================================
echo  [1] Start Web UI - server plus browser
echo  [2] Optimize one model
echo  [3] Optimize all models one by one
echo  [4] Run tests (one file or all)
echo  [5] Check LM Studio connection
echo  [6] List available models
echo  [7] Install / repair environment
echo  [8] Cleanup logs and caches
echo  [9] Delete failed sandbox runs
echo  [10] Exit
echo.
choice /C 1234567890 /N /M "Select 1-10: "
set choice=%errorlevel%
if "%choice%"=="1" goto webui
if "%choice%"=="2" goto optimize_one
if "%choice%"=="3" goto optimize_all
if "%choice%"=="4" goto tests_menu
if "%choice%"=="5" goto check
if "%choice%"=="6" goto models
if "%choice%"=="7" goto install
if "%choice%"=="8" goto cleanup
if "%choice%"=="9" goto cleanup_failed_sandbox
if "%choice%"=="0" goto end
echo Invalid choice.
goto menu

REM --- Web UI -------------------------------------------------------------
:webui
echo.
echo Starting LM Studio Auto Optimizer Web UI...
call :log "starting web server"
start "LM Studio Auto Optimizer - server" "%PYBIN%" -m lm_optimizer.web_main
if errorlevel 1 goto fail_start
echo [INFO] Waiting for http://127.0.0.1:8080 ...
set READY=0
for /L %%i in (1,1,30) do call :poll_once
if "%READY%"=="1" goto ready
goto fail_timeout

:poll_once
curl.exe -sf http://127.0.0.1:8080/api/status >nul 2>&1
if errorlevel 1 goto poll_wait
set READY=1
goto :eof
:poll_wait
timeout /t 1 >nul
goto :eof

:ready
echo.
echo LM Studio Auto Optimizer is running:
echo   http://127.0.0.1:8080
echo.
echo Opening browser...
call :log "ready - opening browser"
start http://127.0.0.1:8080/
echo.
echo Server log streams live in the server window.
echo Launcher stages: %CD%\%LOGFILE%
echo.
echo Press any key to STOP the server and return to the menu.
pause >nul
call :log "stopping server"
taskkill /FI "WINDOWTITLE eq LM Studio Auto Optimizer - server*" >nul 2>&1
goto menu

REM --- Optimize one model -------------------------------------------------
:optimize_one
call :preflight
if errorlevel 1 goto menu
"%PYBIN%" -m lm_optimizer models --full-ids > "%TEMP%\lmo_models.txt" 2>nul
type "%TEMP%\lmo_models.txt"
echo.
set /p osel="Model number or full ID - empty returns to menu: "
if "%osel%"=="" goto menu
set omodel=%osel%
for /f "tokens=1,2 delims=|" %%a in ('type "%TEMP%\lmo_models.txt"') do if "%%a"=="%osel%" set omodel=%%b
set /p oprofile="Profile speed/balanced/context/quality - default balanced: "
if "%oprofile%"=="" set oprofile=balanced
echo Selected model: %omodel%
echo Profile: %oprofile%
call :log "optimize %omodel% profile %oprofile%"
"%PYBIN%" -m lm_optimizer optimize "%omodel%" --profile "%oprofile%"
echo.
echo Finished with exit code %errorlevel%. Press any key for menu.
pause >nul
goto menu

REM --- Optimize all models ------------------------------------------------
:optimize_all
call :preflight
if errorlevel 1 goto menu
"%PYBIN%" -m lm_optimizer models --full-ids > "%TEMP%\lmo_models.txt" 2>nul
type "%TEMP%\lmo_models.txt"
echo.
echo Runs the full pipeline per selected model, small first. This takes hours.
echo You will pick quick/standard/full/benchmark for each model after connecting.
set /p oprofile="Profile speed/balanced/context/quality - default balanced: "
if "%oprofile%"=="" set oprofile=balanced
set /p oselect="Run ONLY these numbers from the list (e.g. 6,9), empty = all models: "
if "%oselect%"=="" goto all_all
call :log "optimize-all profile %oprofile% only %oselect%"
set "oselect_ids="
for %%n in (%oselect%) do call :resolve_one %%n
"%PYBIN%" -m lm_optimizer auto %oselect_ids% --profile "%oprofile%"
goto all_done
:all_all
call :log "optimize-all profile %oprofile%"
"%PYBIN%" -m lm_optimizer auto --profile "%oprofile%"
:all_done
echo.
echo Finished with exit code %errorlevel%. Press any key for menu.
pause >nul
goto menu

:resolve_one
set "one=%~1"
set "found="
for /f "tokens=1,2 delims=|" %%a in ('type "%TEMP%\lmo_models.txt"') do if "%%a"=="%one%" set "found=%%b"
if defined found (
  set "oselect_ids=%oselect_ids% "%found%""
) else (
  set "oselect_ids=%oselect_ids% "%one%""
)
goto :eof

REM --- Tests menu ---------------------------------------------------------
:tests_menu
echo.
echo --- Tests ---
echo  [1] Run ALL tests (pytest -q)
echo  [2] Run ONE test file
echo  [3] Back to main menu
echo.
set /p tchoice="Select 1-3: "
if "%tchoice%"=="1" goto tests_all
if "%tchoice%"=="2" goto tests_one
if "%tchoice%"=="3" goto menu
echo Invalid choice.
goto tests_menu

:tests_all
call :preflight
if errorlevel 1 goto menu
echo Running ALL tests...
"%PYBIN%" -m pytest -q
echo.
echo Finished with exit code %errorlevel%. Press any key for menu.
pause >nul
goto menu

:tests_one
echo.
echo Available test files:
dir /b tests\*.py lm_optimizer\tests\*.py 2>nul
echo.
set /p tfile="Enter test file path (e.g. tests/test_sandbox_lab.py): "
if "%tfile%"=="" goto tests_menu
call :preflight
if errorlevel 1 goto menu
echo Running: %tfile%
"%PYBIN%" -m pytest "%tfile%" -q
echo.
echo Finished with exit code %errorlevel%. Press any key for menu.
pause >nul
goto tests_menu

REM --- Check connection ---------------------------------------------------
:check
"%PYBIN%" -m lm_optimizer status --quick
echo.
echo Press any key for menu.
pause >nul
goto menu

REM --- List models --------------------------------------------------------
:models
"%PYBIN%" -m lm_optimizer models
echo.
"%PYBIN%" -m lm_optimizer models --full-ids
echo.
echo Copy a full ID from the numbered list above.
echo Press any key for menu.
pause >nul
goto menu

REM --- Install / repair ---------------------------------------------------
:install
echo.
echo [1] Create .venv and install dependencies
echo [2] Back to main menu
echo.
set /p ichoice="Select 1-2: "
if "%ichoice%"=="1" goto do_install
if "%ichoice%"=="2" goto menu
echo Invalid choice.
goto install

:do_install
if not exist ".venv" (
  echo Creating .venv...
  python -m venv .venv
)
call ".venv\Scripts\activate.bat"
python -m pip install --upgrade pip
pip install -e ".[dev]"
if not exist ".env" (
  copy ".env.example" ".env" >nul
  echo Created .env from example.
) else (
  echo .env already exists - kept.
)
echo.
echo Install complete. Press any key for menu.
pause >nul
goto menu

REM --- Cleanup ------------------------------------------------------------
:cleanup
echo.
echo This will delete data\logs contents and Python/test caches only.
echo Kept: optimizer.db, data\reports, data\checkpoints, results\, models.
echo.
set /p cconfirm="Type YES to continue: "
if /i not "%cconfirm%"=="YES" goto menu
"%PYBIN%" tools\cleanup.py --yes --logs-only
echo.
echo Done. Press any key for menu.
pause >nul
goto menu

REM --- Cleanup failed sandbox runs -------------------------------------------
:cleanup_failed_sandbox
echo.
echo This will delete ALL failed sandbox runs (history + artifact directories).
echo This cannot be undone.
echo.
set /p cconfirm="Type YES to continue: "
if /i not "%cconfirm%"=="YES" goto menu
"%PYBIN%" -c "from lm_optimizer.services.sandbox_history import clear_failed_sandbox_runs; print('Deleted:', clear_failed_sandbox_runs())"
echo.
echo Done. Press any key for menu.
pause >nul
goto menu

REM --- Preflight (LM Studio check) ----------------------------------------
:preflight
"%PYBIN%" -m lm_optimizer status --quick >nul 2>&1
if not errorlevel 1 goto preflight_ready
echo.
echo ====================================
echo LM Studio is not reachable.
echo ====================================
echo The optimizer cannot start without the server.
echo Check that LM Studio is running with the Developer API enabled.
echo.
set /p osrv="LM Studio URL, empty returns to the menu: "
if "%osrv%"=="" goto preflight_abort
"%PYBIN%" -m lm_optimizer status --quick --url "%osrv%"
if errorlevel 1 goto preflight_bad
set LM_STUDIO_BASE_URL=%osrv%
echo Using %LM_STUDIO_BASE_URL% for this session.
goto preflight_ready
:preflight_bad
echo.
echo Still unreachable at %osrv% - nothing was started.
goto preflight_abort
:preflight_ready
exit /b 0
:preflight_abort
echo Returning to the menu.
exit /b 1

REM --- Errors -------------------------------------------------------------
:fail_python
call :fail "Python not found on PATH. Install Python 3.11 or newer." "python --version"
goto end
:fail_venv
call :fail "Could not create .venv. See log for the python error." "python -m venv .venv"
goto end
:fail_deps
call :fail "Dependency install failed. See log for the pip error." "pip install -e .[dev]"
goto end
:fail_start
call :fail "Could not start the server process." "web_main"
goto end
:fail_timeout
echo.
echo ====================================
echo LM Studio Auto Optimizer FAILED
echo ====================================
echo Reason: server did not answer /api/status within 30 seconds.
echo.
echo Last log lines:
powershell -NoProfile -Command "Get-Content '%LOGFILE%' -Tail 20"
echo.
echo Log:
echo %CD%\%LOGFILE%
echo.
echo Look at the server window for live output. Press any key to close.
pause >nul
call :log "FAILED: readiness timeout"
goto end

:fail
echo.
echo ====================================
echo LM Studio Auto Optimizer FAILED
echo ====================================
echo Reason: %~1
echo Command: %~2
echo.
echo Log:
echo %CD%\%LOGFILE%
echo.
echo Press any key to close.
call :log "FAILED: %~1 [%~2]"
pause >nul
goto :eof

:log
echo %date% %time% %~1>> "%LOGFILE%"
goto :eof

:end
endlocal
