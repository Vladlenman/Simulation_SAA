"""Loading the benchmark return history and the asset-class configuration."""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
CONFIG_DIR = ROOT / "config"

RETURNS_CSV = DATA_DIR / "monthly_returns.csv"
BENCHMARKS_JSON = DATA_DIR / "benchmarks.json"
ASSET_CLASSES_JSON = CONFIG_DIR / "asset_classes.json"


@dataclass(frozen=True)
class AssetClass:
    name: str
    group: str
    benchmark: str
    alternatives: tuple[str, ...] = ()
    proxy: bool = False

    def benchmark_choices(self) -> tuple[str, ...]:
        seen = [self.benchmark, *self.alternatives]
        return tuple(dict.fromkeys(seen))


@dataclass
class ReturnPanel:
    """Monthly total returns, as decimals, one column per benchmark series.

    ``values`` is months x series with ``nan`` where a series has no history.
    """

    months: list[str]
    tickers: list[str]
    values: np.ndarray
    catalogue: dict[str, dict] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self._index = {t: i for i, t in enumerate(self.tickers)}

    def column(self, ticker: str) -> np.ndarray:
        try:
            return self.values[:, self._index[ticker]]
        except KeyError:
            raise KeyError(f"unknown benchmark series: {ticker!r}") from None

    def has(self, ticker: str) -> bool:
        return ticker in self._index

    def matrix(self, tickers: list[str]) -> np.ndarray:
        missing = [t for t in tickers if t not in self._index]
        if missing:
            raise KeyError(f"unknown benchmark series: {missing}")
        return self.values[:, [self._index[t] for t in tickers]]

    def describe(self, ticker: str) -> dict:
        info = dict(self.catalogue.get(ticker, {}))
        info.setdefault("name", ticker)
        return info


def load_panel(path: Path | None = None) -> ReturnPanel:
    """Read ``data/monthly_returns.csv`` into a ReturnPanel."""
    path = path or RETURNS_CSV
    if not path.exists():
        raise FileNotFoundError(
            f"{path} is missing - run: python tools/import_excel.py <BM-Tool.xlsx>"
        )

    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle)
        header = next(reader)
        tickers = header[1:]
        months: list[str] = []
        rows: list[list[float]] = []
        for record in reader:
            if not record or not record[0]:
                continue
            months.append(record[0])
            rows.append(
                [float(cell) if cell not in ("", "nan") else np.nan for cell in record[1:]]
            )

    catalogue: dict[str, dict] = {}
    if BENCHMARKS_JSON.exists():
        catalogue = json.loads(BENCHMARKS_JSON.read_text(encoding="utf-8"))

    return ReturnPanel(
        months=months,
        tickers=tickers,
        values=np.asarray(rows, dtype=float),
        catalogue=catalogue,
    )


def load_asset_classes(path: Path | None = None) -> tuple[list[AssetClass], str]:
    """Read ``config/asset_classes.json``. Returns (classes, risk_free_ticker)."""
    path = path or ASSET_CLASSES_JSON
    raw = json.loads(path.read_text(encoding="utf-8"))
    classes = [
        AssetClass(
            name=entry["name"],
            group=entry.get("group", ""),
            benchmark=entry["benchmark"],
            alternatives=tuple(entry.get("alternatives", ())),
            proxy=bool(entry.get("proxy", False)),
        )
        for entry in raw["classes"]
    ]
    names = [c.name for c in classes]
    if len(set(names)) != len(names):
        duplicates = sorted({n for n in names if names.count(n) > 1})
        raise ValueError(f"duplicate asset class names in {path}: {duplicates}")
    return classes, raw.get("risk_free", "")


@lru_cache(maxsize=1)
def panel() -> ReturnPanel:
    return load_panel()


@lru_cache(maxsize=1)
def asset_classes() -> tuple[tuple[AssetClass, ...], str]:
    classes, risk_free = load_asset_classes()
    return tuple(classes), risk_free


def reset_caches() -> None:
    """Drop the cached panel/config so edited files are picked up."""
    panel.cache_clear()
    asset_classes.cache_clear()
