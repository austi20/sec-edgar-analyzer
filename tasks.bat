@echo off
REM Windows stand-in for the Makefile targets in the README.
cd /d "%~dp0"
if "%1"=="data"   ( python -m src.edgar_client && python -m src.parse & goto :eof )
if "%1"=="ratios" ( python -m src.ratios & goto :eof )
if "%1"=="test"   ( pytest -q & goto :eof )
if "%1"=="app"    ( streamlit run app/streamlit_app.py & goto :eof )
echo Usage: tasks [data^|ratios^|test^|app]
