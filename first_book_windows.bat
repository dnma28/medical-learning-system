@echo off
setlocal
cd /d %~dp0

if "%~1"=="" (
  echo Usage:
  echo   first_book_windows.bat "C:\path\to\Costanzo Physiology 6e.pdf"
  echo.
  echo You can also drag the PDF file onto this .bat file.
  pause
  exit /b 1
)

if not exist .venv\Scripts\activate.bat (
  echo [ERROR] Run setup_windows.bat first.
  pause
  exit /b 1
)

call .venv\Scripts\activate.bat

if not exist "%~1" (
  echo [ERROR] File not found: %~1
  pause
  exit /b 1
)

echo ================================================
echo Ingesting first medical book
echo ================================================
echo File: %~1

mls-ingest --manifest data\sources\costanzo-physiology-6e.example.yaml --file "%~1"
if errorlevel 1 goto :fail

echo.
echo ================================================
echo Running first query
echo ================================================
mls-query "Explain the determinants of resting membrane potential."
if errorlevel 1 goto :fail

echo.
echo SUCCESS: first-book pipeline completed.
pause
exit /b 0

:fail
echo.
echo [ERROR] The first-book run stopped.
echo Copy the error above and send it to ChatGPT.
pause
exit /b 1