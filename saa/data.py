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


INDEX_MODE = "index"
KEY_RATE_MODE = "key_rate"
MODES = (INDEX_MODE, KEY_RATE_MODE)


def key_rate_name(spread_bp: float) -> str:
    """Display name of a synthesised cash series, e.g. ``Geldmarkt + 200 bp``."""
    rounded = int(round(spread_bp))
    if rounded == 0:
        return "Geldmarkt"
    sign = "+" if rounded > 0 else "-"
    return f"Geldmarkt {sign} {abs(rounded)} bp"


@dataclass(frozen=True)
class AssetClass:
    """One asset class and the benchmark it uses in each of the two modes.

    ``benchmark`` is the market index. ``key_rate_spread_bp``, when set, makes
    the class run on the money-market rate plus that spread in ``key_rate``
    mode - the way the Excel workbook computed it.
    """

    name: str
    group: str
    benchmark: str
    alternatives: tuple[str, ...] = ()
    key_rate_spread_bp: float | None = None
    index_proxy: bool = False
    index_note: str = ""

    def benchmark_for(self, mode: str) -> str:
        if mode == KEY_RATE_MODE and self.key_rate_spread_bp is not None:
            return key_rate_name(self.key_rate_spread_bp)
        return self.benchmark

    def is_proxy(self, mode: str) -> bool:
        """A proxy is a stand-in, not a real benchmark for this asset class."""
        if mode == KEY_RATE_MODE and self.key_rate_spread_bp is not None:
            return True
        return self.index_proxy

    def proxy_note(self, mode: str) -> str:
        if mode == KEY_RATE_MODE and self.key_rate_spread_bp is not None:
            return (
                "Geldmarktsatz plus konstantem Aufschlag - eine nahezu gerade "
                "Linie ohne eigenes Risiko. Volatilität, Sharpe Ratio und die "
                "Effizienzlinie fallen dadurch zu gut aus."
            )
        return self.index_note if self.index_proxy else ""

    def benchmark_choices(self, mode: str = INDEX_MODE) -> tuple[str, ...]:
        seen = [self.benchmark_for(mode), self.benchmark, *self.alternatives]
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


@dataclass(frozen=True)
class YieldCurve:
    """A series built from a book yield that changes over time.

    Held-to-maturity books are carried at amortised cost, so their return is an
    accrual, not a market price. What moves over the years is the book's
    average yield, as high-coupon bonds mature and are replaced at current
    rates. ``schedule`` is that path: each anchor is the yield from that month
    onwards, and ``interpolate`` makes the yield drift linearly between
    anchors instead of jumping, which is closer to how a rolling book behaves.
    """

    name: str
    label: str
    schedule: tuple[tuple[str, float], ...]  # (YYYY-MM, yield p.a.)
    interpolate: bool = False
    compounding: str = "geometric"
    until: str | None = None

    def monthly_rate(self, annual: float) -> float:
        if self.compounding == "simple":
            return annual / 12.0
        # Geometric: twelve of these compound to exactly the stated yield.
        return (1.0 + annual) ** (1.0 / 12.0) - 1.0


@dataclass(frozen=True)
class KeyRateSettings:
    """How to rebuild the pure money-market rate from a spread series.

    ``base`` is a series that already contains ``base_spread_bp`` of spread, so
    subtracting it month by month leaves the bare rate.
    """

    base: str
    base_spread_bp: float
    label: str


@dataclass(frozen=True)
class BenchmarkConfig:
    classes: tuple[AssetClass, ...]
    risk_free: str
    key_rate: KeyRateSettings | None
    modes: tuple[dict, ...]
    yield_curves: tuple[YieldCurve, ...] = ()


def load_asset_classes(path: Path | None = None) -> BenchmarkConfig:
    """Read ``config/asset_classes.json``."""
    path = path or ASSET_CLASSES_JSON
    raw = json.loads(path.read_text(encoding="utf-8"))

    classes = []
    for entry in raw["classes"]:
        spread = entry.get("key_rate_spread_bp")
        classes.append(
            AssetClass(
                name=entry["name"],
                group=entry.get("group", ""),
                benchmark=entry["benchmark"],
                alternatives=tuple(entry.get("alternatives", ())),
                key_rate_spread_bp=None if spread is None else float(spread),
                index_proxy=bool(entry.get("index_proxy", False)),
                index_note=str(entry.get("index_note", "")),
            )
        )

    names = [c.name for c in classes]
    if len(set(names)) != len(names):
        duplicates = sorted({n for n in names if names.count(n) > 1})
        raise ValueError(f"duplicate asset class names in {path}: {duplicates}")

    settings = raw.get("key_rate") or {}
    key_rate = (
        KeyRateSettings(
            base=settings["base"],
            base_spread_bp=float(settings.get("base_spread_bp", 0.0)),
            label=settings.get("label", "Geldmarkt"),
        )
        if settings.get("base")
        else None
    )

    curves = []
    for name, entry in (raw.get("yield_curves") or {}).items():
        anchors = tuple(
            (str(a["from"]), float(a["rate_pa"]))
            for a in sorted(entry.get("schedule", []), key=lambda a: str(a["from"]))
        )
        if not anchors:
            continue
        curves.append(
            YieldCurve(
                name=name,
                label=entry.get("label", name),
                schedule=anchors,
                interpolate=bool(entry.get("interpolate", False)),
                compounding=str(entry.get("compounding", "geometric")),
                until=entry.get("until"),
            )
        )

    modes = tuple(raw.get("modes") or [{"id": INDEX_MODE, "label": "Marktindizes"}])
    return BenchmarkConfig(
        classes=tuple(classes),
        risk_free=raw.get("risk_free", ""),
        key_rate=key_rate,
        modes=modes,
        yield_curves=tuple(curves),
    )


def build_yield_series(data: ReturnPanel, curves: list[YieldCurve]) -> ReturnPanel:
    """Append one column per yield curve: the accrual implied by the schedule."""
    curves = [c for c in curves if not data.has(c.name)]
    if not curves:
        return data

    months = list(data.months)
    position = {m: i for i, m in enumerate(months)}
    columns = []
    catalogue = dict(data.catalogue)

    for curve in curves:
        series = np.full(len(months), np.nan)
        anchors = [(m, r) for m, r in curve.schedule if m in position]
        if not anchors:
            columns.append(series)
            continue

        start = position[anchors[0][0]]
        stop = position.get(curve.until, len(months) - 1) if curve.until else len(months) - 1

        for i in range(start, min(stop, len(months) - 1) + 1):
            month = months[i]
            # The last anchor at or before this month, and the next one after.
            previous = anchors[0]
            following = None
            for anchor in anchors:
                if anchor[0] <= month:
                    previous = anchor
                else:
                    following = anchor
                    break

            annual = previous[1]
            if curve.interpolate and following is not None:
                span = position[following[0]] - position[previous[0]]
                if span > 0:
                    step = (i - position[previous[0]]) / span
                    annual = previous[1] + step * (following[1] - previous[1])
            series[i] = curve.monthly_rate(annual)

        columns.append(series)
        known = ~np.isnan(series)
        catalogue[curve.name] = {
            "name": curve.name,
            "description": curve.label,
            "currency": "EUR",
            "synthetic": True,
            "first_month": months[int(np.argmax(known))] if known.any() else None,
            "last_month": months[len(known) - 1 - int(np.argmax(known[::-1]))]
            if known.any()
            else None,
            "months": int(known.sum()),
        }

    return ReturnPanel(
        months=months,
        tickers=[*data.tickers, *(c.name for c in curves)],
        values=np.column_stack([data.values, *columns]),
        catalogue=catalogue,
    )


def build_key_rate_series(
    data: ReturnPanel, settings: KeyRateSettings, spreads: list[float]
) -> ReturnPanel:
    """Append a synthesised ``Geldmarkt + n bp`` column for each spread.

    The published spread series differ by exactly ``spread / 12`` per month, so
    the bare rate comes back by subtracting the base series' own spread, and any
    other spread is an exact addition rather than an approximation.
    """
    if not data.has(settings.base):
        return data

    base = data.column(settings.base) - settings.base_spread_bp / 10_000.0 / 12.0

    wanted = {key_rate_name(s): s for s in spreads}
    wanted.setdefault(key_rate_name(0), 0.0)
    missing = {n: s for n, s in wanted.items() if not data.has(n)}
    if not missing:
        return data

    columns = [base + s / 10_000.0 / 12.0 for s in missing.values()]
    catalogue = dict(data.catalogue)
    months = np.asarray(data.months)
    for name, spread in missing.items():
        known = ~np.isnan(base)
        catalogue[name] = {
            "name": name,
            "description": (
                f"{settings.label} + {int(round(spread))} bp"
                if spread
                else settings.label
            ),
            "currency": "EUR",
            "synthetic": True,
            "first_month": str(months[known][0]) if known.any() else None,
            "last_month": str(months[known][-1]) if known.any() else None,
            "months": int(known.sum()),
        }

    return ReturnPanel(
        months=list(data.months),
        tickers=[*data.tickers, *missing],
        values=np.column_stack([data.values, *columns]),
        catalogue=catalogue,
    )


@lru_cache(maxsize=1)
def benchmark_config() -> BenchmarkConfig:
    return load_asset_classes()


@lru_cache(maxsize=1)
def panel() -> ReturnPanel:
    """The return history, with the synthesised key-rate series included."""
    data = load_panel()
    config = benchmark_config()
    if config.key_rate is not None:
        spreads = [
            c.key_rate_spread_bp
            for c in config.classes
            if c.key_rate_spread_bp is not None
        ]
        data = build_key_rate_series(data, config.key_rate, spreads)
    return build_yield_series(data, list(config.yield_curves))


def asset_classes() -> tuple[tuple[AssetClass, ...], str]:
    config = benchmark_config()
    return config.classes, config.risk_free


def reset_caches() -> None:
    """Drop the cached panel/config so edited files are picked up."""
    panel.cache_clear()
    benchmark_config.cache_clear()
