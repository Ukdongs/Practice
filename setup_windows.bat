@echo off
setlocal

cd /d "%~dp0"

echo ===================================================
echo  OCR 3-Engine Comparison - Windows Setup Script
echo ===================================================
echo.

rem --- 1. Check for Tesseract -------------------------------------------
where tesseract >nul 2>nul
if errorlevel 1 goto NO_TESSERACT
echo [1/4] Tesseract is already installed.
goto AFTER_TESSERACT

:NO_TESSERACT
echo [1/4] Tesseract was not found.
where winget >nul 2>nul
if errorlevel 1 goto NO_WINGET
echo       Trying to install Tesseract-OCR via winget...
winget install --id UB-Mannheim.TesseractOCR -e --source winget
echo.
echo       NOTE: the winget install may not include the Korean language pack.
echo       Please check the manual steps below once it finishes.
goto TESSERACT_GUIDE

:NO_WINGET
echo       winget is not available. Manual installation is required.

:TESSERACT_GUIDE
echo.
echo       ------------------------------------------------------------
echo       Manual Tesseract install / Korean language pack check
echo       ------------------------------------------------------------
echo       1. Visit https://github.com/UB-Mannheim/tesseract/wiki
echo       2. Download and run the latest Windows installer
echo       3. During install, check Additional language data, then Korean
echo       4. When finished, come back here and press any key
echo       ------------------------------------------------------------
pause

:AFTER_TESSERACT
echo.

rem --- 2. Pick a Python launcher ------------------------------------------
where py >nul 2>nul
if errorlevel 1 goto CHECK_PYTHON
set PY_LAUNCH=py -3
goto PY_FOUND

:CHECK_PYTHON
where python >nul 2>nul
if errorlevel 1 goto NO_PYTHON
set PY_LAUNCH=python
goto PY_FOUND

:NO_PYTHON
echo Python was not found. Please install it from:
echo https://www.python.org/downloads/
echo Be sure to check the box to add python.exe to PATH during install.
pause
exit /b 1

:PY_FOUND
echo [2/4] Using Python launcher: %PY_LAUNCH%

rem --- 3. Create venv and install packages ----------------------------------
if exist ".venv" goto VENV_EXISTS
echo [3/4] Creating virtual environment .venv ...
%PY_LAUNCH% -m venv .venv
if errorlevel 1 goto VENV_FAIL
goto VENV_READY

:VENV_FAIL
echo Failed to create the virtual environment.
pause
exit /b 1

:VENV_EXISTS
echo [3/4] Virtual environment .venv already exists.

:VENV_READY
call .venv\Scripts\activate.bat

python -m pip install --upgrade pip setuptools wheel
if errorlevel 1 goto PIP_FAIL

python -m pip install -r requirements.txt
if errorlevel 1 goto PIP_FAIL
goto MODELS

:PIP_FAIL
echo Package installation failed. See the messages above.
pause
exit /b 1

:MODELS
rem --- 4. Pre-download EasyOCR and PaddleOCR models --------------------------
echo [4/4] Downloading EasyOCR and PaddleOCR models...
python main.py --prepare-models
if errorlevel 1 goto MODEL_FAIL
goto DONE

:MODEL_FAIL
echo Model preparation failed. Double-check the Tesseract install above.
pause
exit /b 1

:DONE
echo.
echo Setup complete.
echo In VS Code, select .venv\Scripts\python.exe as the Python interpreter.
pause
