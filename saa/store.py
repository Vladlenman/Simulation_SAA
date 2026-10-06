"""Saved weight scenarios, one JSON file each under ``portfolios/``.

Plain files on purpose: they diff in git, they can be mailed to a colleague,
and they are readable without the tool.
"""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

from .portfolio import Scenario

ROOT = Path(__file__).resolve().parent.parent
PORTFOLIO_DIR = ROOT / "portfolios"

_SAFE = re.compile(r"[^a-z0-9]+")


UMLAUTS = str.maketrans(
    {"ä": "ae", "ö": "oe", "ü": "ue", "Ä": "ae", "Ö": "oe", "Ü": "ue", "ß": "ss"}
)


def slug(name: str) -> str:
    # Transliterate before NFKD, which would otherwise split "Ä" into a bare "A".
    folded = unicodedata.normalize("NFC", name).translate(UMLAUTS)
    ascii_only = (
        unicodedata.normalize("NFKD", folded).encode("ascii", "ignore").decode().lower()
    )
    cleaned = _SAFE.sub("-", ascii_only).strip("-")
    return cleaned or "szenario"


class ScenarioStore:
    def __init__(self, directory: Path | None = None) -> None:
        self.directory = directory or PORTFOLIO_DIR
        self.directory.mkdir(parents=True, exist_ok=True)

    def path_for(self, name: str) -> Path:
        return self.directory / f"{slug(name)}.json"

    def list(self) -> list[Scenario]:
        out: list[Scenario] = []
        for path in sorted(self.directory.glob("*.json")):
            try:
                out.append(Scenario.from_dict(json.loads(path.read_text("utf-8"))))
            except (json.JSONDecodeError, OSError, TypeError, ValueError):
                continue
        return out

    def get(self, name: str) -> Scenario | None:
        path = self.path_for(name)
        if not path.exists():
            return None
        return Scenario.from_dict(json.loads(path.read_text("utf-8")))

    def save(self, scenario: Scenario) -> Path:
        if not scenario.name.strip():
            raise ValueError("Ein Szenario braucht einen Namen.")
        path = self.path_for(scenario.name)
        payload = json.dumps(scenario.to_dict(), indent=2, ensure_ascii=False)
        path.write_text(payload + "\n", encoding="utf-8")
        return path

    def delete(self, name: str) -> bool:
        path = self.path_for(name)
        if path.exists():
            path.unlink()
            return True
        return False
