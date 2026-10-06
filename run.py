#!/usr/bin/env python3
"""Start the SAA tool.

    python run.py                 http://127.0.0.1:8000
    python run.py --port 8080
    python run.py --host 0.0.0.0  reachable from the network - only on a
                                  machine where that is acceptable
"""

from __future__ import annotations

import argparse
import sys
import webbrowser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


def main() -> int:
    parser = argparse.ArgumentParser(description="SAA-Simulationstool starten")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--no-browser", action="store_true", help="Browser nicht öffnen")
    args = parser.parse_args()

    try:
        import numpy  # noqa: F401
    except ImportError:
        print("numpy fehlt. Installieren mit:  pip install numpy", file=sys.stderr)
        return 1

    from saa.app import serve
    from saa.data import RETURNS_CSV

    if not RETURNS_CSV.exists():
        print(
            f"{RETURNS_CSV} fehlt.\n"
            "Einmalig aus der Excel-Datei erzeugen:\n"
            "    python tools/import_excel.py pfad/zu/BM-Tool.xlsx",
            file=sys.stderr,
        )
        return 1

    if not args.no_browser:
        webbrowser.open(f"http://{args.host if args.host != '0.0.0.0' else '127.0.0.1'}:{args.port}/")

    serve(args.host, args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
