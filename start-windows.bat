@echo off
REM SAA-Simulation starten (Windows). Diese Datei doppelklicken.
setlocal
cd /d "%~dp0"

REM ===================================================================
REM  ORDNER VERSCHIEBEN - nur wenn gewuenscht, sonst leer lassen.
REM  Ohne Eintrag liegen die Ordner neben dieser Datei.
REM  Beispiel:  set "SAA_PORTFOLIOS_DIR=S:\Team\SAA-Szenarien"
REM  Pfade mit Leerzeichen genau so in Anfuehrungszeichen setzen.
REM ===================================================================
set "SAA_PORTFOLIOS_DIR="
set "SAA_DATA_DIR="
set "SAA_CONFIG_DIR="
REM ===================================================================

echo.
echo   SAA-Simulation wird gestartet ...
echo.

REM --- Python suchen: erst der Launcher "py", dann "python". ---
REM Flache Struktur mit Sprungmarken: errorlevel in Klammerbloecken
REM braucht sonst delayed expansion und wertet den falschen Stand aus.
set "PY="
py -3 --version >nul 2>&1
if not errorlevel 1 set "PY=py -3"
if defined PY goto have_python
python --version >nul 2>&1
if not errorlevel 1 set "PY=python"
if defined PY goto have_python

echo   [!] Python wurde nicht gefunden.
echo.
echo       Python 3 installieren: https://www.python.org/downloads/
echo       Beim Installieren "Add Python to PATH" ankreuzen.
echo.
pause
exit /b 1

:have_python
REM --- numpy ist die einzige Abhaengigkeit. ---
%PY% -c "import numpy" >nul 2>&1
if not errorlevel 1 goto run

echo   numpy fehlt, wird installiert ...
%PY% -m pip install --user numpy
%PY% -c "import numpy" >nul 2>&1
if not errorlevel 1 goto run

echo.
echo   [!] numpy konnte nicht installiert werden.
echo       Firmenrechner ohne Internetzugang? Dann bitte die IT um
echo       "pip install numpy" bitten.
echo.
pause
exit /b 1

:run
%PY% run.py

echo.
echo   Beendet. Fenster kann geschlossen werden.
pause
