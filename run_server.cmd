@echo off
REM Windows entry point for the Data Commons MCP Claude Desktop extension.
REM
REM Mirrors run_server.sh: dependencies are NOT bundled. uv resolves them from
REM the bundled pyproject.toml + uv.lock and builds wheels for the user's Python
REM (subject to requires-python). The locked versions make every install
REM reproducible. First launch downloads + builds the environment (then cached),
REM so it requires network access. uv is expected to be installed.

setlocal enableextensions

set "SCRIPT_DIR=%~dp0"
if "%SCRIPT_DIR:~-1%"=="\" set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"

REM Locate uv. The standalone installer puts it in %USERPROFILE%\.local\bin;
REM winget links it under %LOCALAPPDATA%\Microsoft\WinGet\Links. Fall back to
REM a PATH lookup (works for terminal/dev launches).
set "UV="
if exist "%USERPROFILE%\.local\bin\uv.exe" set "UV=%USERPROFILE%\.local\bin\uv.exe"
if not defined UV if exist "%LOCALAPPDATA%\Microsoft\WinGet\Links\uv.exe" set "UV=%LOCALAPPDATA%\Microsoft\WinGet\Links\uv.exe"
if not defined UV for %%U in (uv.exe) do if not "%%~$PATH:U"=="" set "UV=%%~$PATH:U"

if not defined UV (
    echo Error: 'uv' was not found. The Data Commons MCP extension uses uv to resolve its Python dependencies at runtime. Install it from https://docs.astral.sh/uv/ ^(or have it deployed via your organization's tooling^) and try again.>&2
    exit /b 1
)

REM --frozen: install exactly what's pinned in uv.lock; never re-resolve.
"%UV%" run --frozen --project "%SCRIPT_DIR%" python "%SCRIPT_DIR%\datacommons_mcp\run_server.py" %*
