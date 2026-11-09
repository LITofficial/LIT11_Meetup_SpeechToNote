@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Please follow the setup instructions in README.md first.
  pause
  exit /b 1
)
set "PYTHONPATH=%~dp0src"
".venv\Scripts\python.exe" -m lecture_transcriber
if errorlevel 1 pause
