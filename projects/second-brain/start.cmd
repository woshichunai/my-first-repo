@echo off
cd /d "%~dp0"
py -3 --version >nul 2>&1
if errorlevel 1 (
  echo Python 3 was not found. Install Python 3.10+ from python.org with Tcl/Tk.
  pause
  exit /b 1
)
py -3 brain.py
if errorlevel 1 pause
