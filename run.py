#!/usr/bin/env python3
"""Start the SAA tool.

    python run.py                 http://127.0.0.1:8000
    python run.py --port 8080
    python run.py --host 0.0.0.0  reachable from the network - only on a
                                  machine where that is acceptable

Ordner verschieben (sonst liegen sie neben dieser Datei):

    python run.py --portfolios "S:/Team/SAA-Szenarien"
    python run.py --data-dir "S:/Team/SAA-Daten"
    python run.py --config-dir "S:/Team/SAA-Konfiguration"

Dieselben drei Pfade lassen sich auch als Umgebungsvariablen setzen:
SAA_PORTFOLIOS_DIR, SAA_DATA_DIR, SAA_CONFIG_DIR.
"""

from __future__ import annotations

import argparse
import os
import sys
import webbrowser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="SAA-Simulationstool starten",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--no-browser", action="store_true", help="Browser nicht öffnen")
    parser.add_argument(
        "--portfolios",
        metavar="ORDNER",
        help="Ordner für die gespeicherten Szenarien (Standard: ./portfolios)",
    )
    parser.add_argument(
        "--data-dir",
        metavar="ORDNER",
        help="Ordner mit monthly_returns.csv und benchmarks.json (Standard: ./data)",
    )
    parser.add_argument(
        "--config-dir",
        metavar="ORDNER",
        help="Ordner mit asset_classes.json (Standard: ./config)",
    )
    args = parser.parse_args()

    # Set these before importing the package: the modules resolve their folders
    # at import time, so the overrides have to be in place first.
    for value, variable in (
        (args.portfolios, "SAA_PORTFOLIOS_DIR"),
        (args.data_dir, "SAA_DATA_DIR"),
        (args.config_dir, "SAA_CONFIG_DIR"),
    ):
        if value:
            os.environ[variable] = value

    missing = [
        name
        for name in ("numpy", "openpyxl")
        if __import__("importlib.util", fromlist=["util"]).find_spec(name) is None
    ]
    if missing:
        print(
            f"Fehlende Pakete: {', '.join(missing)}\n"
            f"Installieren mit:  pip install {' '.join(missing)}",
            file=sys.stderr,
        )
        return 1

    from saa.app import serve
    from saa.data import ASSET_CLASSES_JSON, RETURNS_CSV, RETURNS_XLSX
    from saa.store import PORTFOLIO_DIR

    returns = RETURNS_XLSX if RETURNS_XLSX.exists() else RETURNS_CSV
    for label, path in (
        ("Renditen", returns),
        ("Konfiguration", ASSET_CLASSES_JSON),
    ):
        if not path.exists():
            print(
                f"{label} nicht gefunden: {path}\n\n"
                "Liegt der Ordner woanders? Dann mit --data-dir bzw. --config-dir\n"
                "darauf zeigen. Fehlt die Renditedatei ganz, einmal aus der\n"
                "BM-Tool-Datei erzeugen:\n"
                "    python tools/import_excel.py pfad/zu/BM-Tool.xlsx",
                file=sys.stderr,
            )
            return 1

    print(f"  Renditen     {returns}")
    print(f"  Konfiguration {ASSET_CLASSES_JSON}")
    print(f"  Szenarien    {PORTFOLIO_DIR}")
    print()

    if not args.no_browser:
        host = "127.0.0.1" if args.host == "0.0.0.0" else args.host
        webbrowser.open(f"http://{host}:{args.port}/")

    serve(args.host, args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
