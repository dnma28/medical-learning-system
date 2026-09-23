@echo off
setlocal
cd /d %~dp0

echo ================================================
echo Medical Learning System v0.2 - Windows setup
echo ================================================

where python >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Python was not found.
  echo Install Python 3.10 or newer, then run this file again.
  pause
  exit /b 1
)

python --version

if not exist .venv (
  echo Creating virtual environment...
  python -m venv .venv
  if errorlevel 1 goto :fail
)

call .venv\Scripts\activate.bat
if errorlevel 1 goto :fail

echo Upgrading pip...
python -m pip install --upgrade pip
if errorlevel 1 goto :fail

echo Installing Medical Learning System and RAG-Anything...
pip install -e ".[dev,rag]"
if errorlevel 1 goto :fail

if not exist .env (
  copy .env.example .env >nul
  echo Created .env from .env.example
)

echo.
echo Running health check...
python scripts\doctor.py

echo.
echo ================================================
echo Setup finished.
echo NEXT: open .env and set OPENAI_API_KEY.
echo Then run first_book_windows.bat with your PDF.
echo ================================================
pause
exit /b 0

:fail
echo.
echo [ERROR] Setup stopped. Copy the error above and send it to ChatGPT.
pause
exit /b 1