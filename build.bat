@echo off
title SsakSsak Macro - EXE Builder
cls

echo ====================================================================
echo      SSAKSSAK HIGH-PRECISION MOUSE MACRO - Standalone EXE Builder
echo ====================================================================
echo.
echo [1/3] Checking and installing PyInstaller...
python -m pip install --upgrade pip pyinstaller

echo.
echo [2/3] Compiling application...
echo Resources (Pretendard fonts) will be embedded inside the EXE.
echo.

:: Compile with --windowed for clean headless execution
pyinstaller --noconfirm --onefile --windowed --version-file version_info.txt --name="SsakSsakMacro" --icon "assets/brand/app.ico" --add-data "assets/brand;assets/brand" --add-data "fonts;fonts" app.py

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] Compilation failed.
    goto end
)

echo.
echo [3/3] Compilation completed successfully!
echo ====================================================================
echo  Standalone EXE is located at:
echo  %~dp0dist\SsakSsakMacro.exe
echo.
echo  You can copy this EXE file anywhere and run it independently.
echo ====================================================================

:end
pause
