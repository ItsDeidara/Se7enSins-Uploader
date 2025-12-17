@echo off
echo Installing PyInstaller...
python -m pip install pyinstaller

echo Checking for icon file...
set ICON_FLAG=
if exist icon.ico goto use_default_icon
echo Icon file not found. Please enter the path to an icon file (or press Enter to skip):
set /p ICON_PATH=
if defined ICON_PATH (
    set ICON_FLAG=--icon "%ICON_PATH%"
    echo Using icon: %ICON_PATH%
) else (
    echo No icon selected.
)
goto end_icon_check
:use_default_icon
for %%i in (icon.ico) do set ICON_FLAG=--icon "%%~fi"
echo Using icon: %%~fi
:end_icon_check

echo Building standalone exe...
echo Using icon flag: %ICON_FLAG%
python -m PyInstaller --onefile --windowed %ICON_FLAG% gui.py

echo Copying config and categories files...
copy config.json dist\
copy categories.json dist\

echo Build complete. Check the dist folder for the exe and config files.