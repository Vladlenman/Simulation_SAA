#!/bin/bash
# SAA-Simulation starten (macOS / Linux). Diese Datei doppelklicken.
cd "$(dirname "$0")" || exit 1

echo
echo "  SAA-Simulation wird gestartet ..."
echo

PY=""
for candidate in python3 python; do
  if command -v "$candidate" >/dev/null 2>&1; then PY="$candidate"; break; fi
done

if [ -z "$PY" ]; then
  echo "  [!] Python 3 wurde nicht gefunden."
  echo "      Installieren: https://www.python.org/downloads/"
  echo
  read -r -p "  Enter zum Schliessen " _
  exit 1
fi

if ! "$PY" -c "import numpy" >/dev/null 2>&1; then
  echo "  numpy fehlt, wird installiert ..."
  "$PY" -m pip install --user numpy
  if ! "$PY" -c "import numpy" >/dev/null 2>&1; then
    echo
    echo "  [!] numpy konnte nicht installiert werden."
    echo "      Ohne Internetzugang bitte die IT um 'pip install numpy' bitten."
    echo
    read -r -p "  Enter zum Schliessen " _
    exit 1
  fi
fi

"$PY" run.py

echo
read -r -p "  Beendet. Enter zum Schliessen " _
