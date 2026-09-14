@echo off
REM One-time git setup for this project. Double-click to run.
cd /d "%~dp0"

git rev-parse --git-dir >nul 2>&1
if %errorlevel%==0 (
  echo A git repo already exists here. Nothing to do.
  pause
  exit /b 0
)

git init -b main
git add -A
git commit -m "Scaffold project: repo structure, pinned deps, module stubs"

echo.
echo Local repo created on branch main.
echo.
echo To publish it, either:
echo   gh repo create sec-edgar-analyzer --public --source=. --remote=origin --push
echo or create sec-edgar-analyzer on github.com and then:
echo   git remote add origin https://github.com/austi20/sec-edgar-analyzer.git
echo   git push -u origin main
echo.
pause
