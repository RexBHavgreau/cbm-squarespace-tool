@echo off
setlocal enabledelayedexpansion

rem ---------------------------------------------------------------
rem  build-windows.bat
rem  Builds the CBM Article Converter into a single .exe.
rem
rem  Put this beside app.py and core.py and double-click it. It works
rem  from any folder or drive, including a USB stick, and leaves the
rem  finished app in a "dist" folder right here.
rem ---------------------------------------------------------------

rem Stand in this script's own folder. The /d copes with a different
rem drive letter, which a plain cd will not.
cd /d "%~dp0"

echo.
echo   Building the CBM Article Converter
echo   Folder: %~dp0
echo.

if not exist "app.py"  goto nosource
if not exist "core.py" goto nosource

rem --- Python present? ---
where python >nul 2>&1
if errorlevel 1 goto nopython

rem --- Read the build number out of core.py so the name matches ---
set "BUILD="
for /f "tokens=3 delims= " %%i in ('findstr /b /c:"VERSION = " core.py') do set "RAW=%%i"
if defined RAW set "BUILD=!RAW:"=!"
if not defined BUILD set "BUILD=unknown"
set "APPNAME=CBM Article Converter !BUILD!"

echo   Version found: !BUILD!
echo   Will produce: !APPNAME!.exe
echo.

rem --- Make sure the three packages are there ---
set "LOG=%~dp0build-log.txt"
echo Build log, %DATE% %TIME%> "!LOG!"
echo Folder: %~dp0>> "!LOG!"

echo   Checking packages. This may take a minute the first time.
echo   Everything is written to build-log.txt as it goes.
python -m pip install --upgrade pyinstaller mammoth beautifulsoup4 >> "!LOG!" 2>&1
if errorlevel 1 goto nopackages

rem --- Build, keeping every working file inside this folder ---
echo.
echo   Building. This takes a minute or two.
echo.
rem Relative paths on purpose. %~dp0 ends with a backslash, and a
rem backslash just before a closing quote escapes the quote, which
rem breaks the whole command line. We are already standing in this
rem folder, so plain names are safer and clearer.
python -m PyInstaller --onefile --windowed --clean --noconfirm --name "!APPNAME!" --distpath "dist" --workpath "build" --specpath "." --collect-all mammoth --add-data "USER-GUIDE.txt;." --add-data "HTML-REFERENCE.txt;." --add-data "BUILD-NOTES.txt;." "app.py" >> "!LOG!" 2>&1
if errorlevel 1 goto buildfailed

if not exist "dist\!APPNAME!.exe" goto buildfailed

rem --- Tidy up the working files, keep the app ---
if exist "build" rmdir /s /q "build"
if exist "!APPNAME!.spec" del /q "!APPNAME!.spec"

echo.
echo   ---------------------------------------------------------------
echo    Done.
echo.
echo    Your app:  dist\!APPNAME!.exe
echo.
echo    A full log of the build is in build-log.txt.
echo.
echo    That single file is the whole program. Copy it anywhere; it
echo    needs nothing installed. Windows will warn the first time it
echo    runs on a machine: click More info, then Run anyway.
echo   ---------------------------------------------------------------
echo.
start "" "dist"
pause
exit /b 0

:nosource
echo   app.py and core.py must sit beside this file.
echo   Found in %~dp0:
dir /b *.py 2>nul
echo.
echo   Extract the whole folder, then run this again from inside it.
echo.
pause
exit /b 1

:nopython
echo   Python was not found.
echo.
echo   Install it from python.org, or at a command prompt run:
echo       winget install Python.Python.3.12
echo.
echo   Tick "Add python.exe to PATH" during installation, then open a
echo   new window and run this again.
echo.
pause
exit /b 1

:nopackages
echo.
echo   Could not install the packages needed to build.
echo   Check that this machine can reach the internet, then try again.
goto showlog

:buildfailed
echo.
echo   The build did not finish.
goto showlog

:showlog
echo.
echo   ---------------------------------------------------------------
echo    The last 25 lines of the log:
echo   ---------------------------------------------------------------
powershell -NoProfile -Command "Get-Content -Tail 25 '%~dp0build-log.txt'" 2>nul
echo   ---------------------------------------------------------------
echo.
echo    The whole log is saved here, ready to copy or send on:
echo       %~dp0build-log.txt
echo.
echo    It opens in Notepad when you close this window.
echo.
pause
start "" notepad "%~dp0build-log.txt"
exit /b 1
