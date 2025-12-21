@echo off
setlocal EnableDelayedExpansion

for /F "tokens=1,2 delims=#" %%a in ('"prompt #$H#$E# & echo on & for %%b in (1) do rem"') do (
  set "ESC=%%b"
)
set "RESET=%ESC%[0m"
set "RED=%ESC%[31m"
set "GREEN=%ESC%[32m"
set "YELLOW=%ESC%[33m"
set "CYAN=%ESC%[36m"
set "GRAY=%ESC%[90m"

echo %RESET%[INFO] Checking python installation...
set "CURRENT_PY="
python --version >nul 2>&1
if %errorlevel% equ 0 (
    for /f "tokens=2" %%v in ('python --version 2^>^&1') do set "CURRENT_PY=%%v"
)

set "REQUIRED_VER_MAJOR=3"
set "REQUIRED_VER_MINOR=12"
if defined CURRENT_PY (
    for /f "tokens=1,2 delims=." %%a in ("!CURRENT_PY!") do (
        if "%%a"=="%REQUIRED_VER_MAJOR%" (
            if "%%b"=="%REQUIRED_VER_MINOR%" (
                echo %GREEN%[OK] Found Python !CURRENT_PY!
                set "CMD_PYTHON=python"
                goto :PythonFound
            )
        )
    )
    echo %YELLOW%[WARN] Found Python !CURRENT_PY!, but %REQUIRED_VER_MAJOR%.%REQUIRED_VER_MINOR% is required.
) else (
    echo %YELLOW%[WARN] Python not found.
)

echo %RESET%[INFO] Installing via Winget...
winget install -e --id Python.Python.3.12 --source winget --scope user --silent --accept-package-agreements --accept-source-agreements
if %errorlevel% neq 0 (
    echo %RED%[ERROR] Winget installation failed%RESET%
    pause
    exit /b 1
)

echo %RESET%[INFO] Searching for installed Python executable...
set "FOUND_PY="
for /d %%D in ("%LocalAppData%\Programs\Python\Python3*") do (
    if exist "%%D\python.exe" set "FOUND_PY=%%D\python.exe"
)
if not defined FOUND_PY (
    echo %RED%[ERROR] Could not locate the new Python executable
    echo You may need to restart the script/terminal%RESET%
    pause
    exit /b 1
)
set "CMD_PYTHON=!FOUND_PY!"
echo %GREEN%[OK] Found Python at: "!CMD_PYTHON!"

:PythonFound
echo %RESET%[INFO] Creating venv...
if not exist venv (
    "!CMD_PYTHON!" -m venv venv >nul 2>&1
)
call .\venv\Scripts\activate.bat

echo %RESET%[INFO] Updating dependencies...
python -m pip install --upgrade pip >nul 2>&1
if exist requirements.txt (
    python -m pip install -r requirements.txt >nul 2>&1
)
echo %GREEN%[OK] Python ready 

echo %RESET%[INFO] Handing over to installation script...
echo.
echo %CYAN%========================================================%RESET%
echo.

python lib/main.py %*

echo.
echo %CYAN%========================================================
echo.
if %errorlevel% neq 0 (
    echo %RED%[ERROR] Python script exited with error%RESET%
    pause
    exit /b 1
)

echo %GREEN%[OK] Script finished succesfully%RESET%
pause