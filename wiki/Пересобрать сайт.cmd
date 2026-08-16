@echo off
rem Rebuilds the net67 wiki after you edit content\*.md
rem
rem ASCII only on purpose: cmd.exe reads .cmd files in the OEM codepage,
rem and Cyrillic here turns into garbage and breaks parsing.
rem
rem Needs Node.js 22+ (https://nodejs.org). Everything else is bundled
rem in the engine folder.
setlocal
cd /d "%~dp0"

where node >nul 2>nul || (
  echo Node.js not found. Install it from https://nodejs.org and run this again.
  pause
  exit /b 1
)

echo [1/4] Copying content into the engine
if exist "engine\content" rmdir /s /q "engine\content"
xcopy /e /i /q "content" "engine\content" >nul
copy /y "quartz.config.yaml" "engine\quartz.config.yaml" >nul
copy /y "content\img\net67.png" "engine\quartz\static\icon.png" >nul
copy /y "custom.scss" "engine\quartz\styles\custom.scss" >nul

echo [2/4] Installing engine dependencies (first run only)
cd engine
if not exist "node_modules" (
  call npm ci --no-audit --no-fund || exit /b 1
)

echo [3/4] Building
call npx quartz build || exit /b 1
cd ..

echo [4/4] Publishing into site
if exist "site" rmdir /s /q "site"
xcopy /e /i /q "engine\public" "site" >nul

echo.
echo Done. Open the wiki with "Otkryt sayt.cmd"
pause
