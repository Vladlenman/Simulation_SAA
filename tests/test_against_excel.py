"""Regression test: the engine must reproduce BM-Tool's own reported figures.

BM-Tool!D34:I34 for "SAA neu" (TER 1.09 % p.a., 2003-02 .. 2025-12) is the
reference. Sharpe is excluded on purpose - the workbook's own figure is wrong,
see docs/excel-workbook-notes.md.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from saa.data import (
    INDEX_MODE,
    KEY_RATE_MODE,
    AssetClass,
    ReturnPanel,
    YieldCurve,
    benchmark_config,
    build_yield_series,
    load_panel,
    panel,
)
from saa.portfolio import Scenario, simulate

ROOT = Path(__file__).resolve().parent.parent
REFERENCE = json.loads((ROOT / "data" / "reference_figures.json").read_text("utf-8"))

TOLERANCE = 1e-12


def build_excel_scenario() -> tuple[Scenario, list[AssetClass]]:
    """The 15 BM-Tool rows exactly as the workbook had them."""
    rows = REFERENCE["excel_saa_rows"]
    classes = [
        AssetClass(name=name, group="", benchmark=ticker)
        for name, ticker, _ in rows
    ]
    scenario = Scenario(
        name=REFERENCE["figures"]["scenario"],
        weights={name: weight for name, _, weight in rows},
        benchmarks={name: ticker for name, ticker, _ in rows},
        ter=REFERENCE["figures"]["ter"],
    )
    return scenario, classes


def test_reproduces_excel_figures() -> None:
    scenario, classes = build_excel_scenario()
    panel = load_panel()
    expected = REFERENCE["figures"]

    sim = simulate(
        scenario,
        panel,
        classes,
        risk_free_ticker="",
        start=expected["start"],
        end=expected["end"],
    )
    stats = sim.stats()

    assert sim.months[0] == expected["start"], sim.months[0]
    assert sim.months[-1] == expected["end"], sim.months[-1]
    assert stats.months == expected["months"], stats.months

    checks = {
        "total_return": stats.total_return,
        "cagr": stats.cagr,
        "volatility": stats.volatility,
        "max_drawdown": stats.max_drawdown,
        "calmar": stats.calmar,
    }
    for key, actual in checks.items():
        assert abs(actual - expected[key]) < TOLERANCE, (
            f"{key}: engine {actual!r} vs Excel {expected[key]!r}"
        )


def test_weights_sum_to_one_and_cost_reduces_return() -> None:
    scenario, classes = build_excel_scenario()
    panel = load_panel()
    sim = simulate(scenario, panel, classes, start="2003-02", end="2025-12")
    assert abs(sim.weights.sum() - 1.0) < 1e-12
    assert sim.stats().total_return < sim.gross_stats().total_return


def test_risk_contributions_sum_to_portfolio_volatility() -> None:
    scenario, classes = build_excel_scenario()
    panel = load_panel()
    sim = simulate(scenario, panel, classes, start="2003-02", end="2025-12")
    components = sum(row["component_risk"] for row in sim.risk_contribution())
    realised = float(np.std(sim.returns, ddof=1) * np.sqrt(12))
    assert abs(components - realised) < 1e-9, (components, realised)


def test_configured_classes_all_have_available_benchmarks() -> None:
    config = benchmark_config()
    data = panel()
    assert data.has(config.risk_free), config.risk_free
    for mode in (INDEX_MODE, KEY_RATE_MODE):
        for cls in config.classes:
            ticker = cls.benchmark_for(mode)
            assert data.has(ticker), f"{cls.name} [{mode}]: {ticker} not in the data"
            unknown = [t for t in cls.benchmark_choices(mode) if not data.has(t)]
            assert not unknown, f"{cls.name} [{mode}]: unknown alternatives {unknown}"


def test_synthetic_key_rate_series_match_the_excel_spread_series() -> None:
    """``Geldmarkt + n bp`` must equal the workbook's own ESTR3MA + n bp series.

    This is what keeps the key-rate mode a faithful reproduction rather than an
    approximation of the original calculation.
    """
    data = panel()
    for spread, original in ((100, "ESTR3MA Index (+ 100BP)"), (200, "ESTR3MA Index (+ 200BP)")):
        synthetic = data.column(f"Geldmarkt + {spread} bp")
        reference = data.column(original)
        known = ~np.isnan(reference)
        assert np.array_equal(np.isnan(synthetic), np.isnan(reference))
        assert np.max(np.abs(synthetic[known] - reference[known])) < 1e-15


def test_key_rate_mode_reproduces_the_excel_portfolio() -> None:
    """The configured classes in key-rate mode must match the Excel figures.

    The regression test above pins the raw tickers; this one pins the
    *configuration*, so a careless edit to ``asset_classes.json`` is caught.
    """
    expected = REFERENCE["figures"]
    config = benchmark_config()
    weights = {
        "Anleihen EURO": 0.29,
        "Anleihen HTM": 0.35,
        "Anleihen Welt": 0.03,
        "Wandelanleihen (EUR hedged)": 0.04,
        "Aktien Welt": 0.08,
        "Aktien Europa (EUR hedged)": 0.05,
        "Aktien EM": 0.02,
        "Alternative Investments": 0.03,
        "Mikrofinanz": 0.02,
        "Immobilien": 0.09,
    }
    sim = simulate(
        Scenario(name="SAA", weights=weights, ter=expected["ter"], mode=KEY_RATE_MODE),
        panel(),
        list(config.classes),
        risk_free_ticker="",
        start=expected["start"],
        end=expected["end"],
    )
    stats = sim.stats()
    for key in ("total_return", "cagr", "volatility", "max_drawdown"):
        actual = getattr(stats, key)
        assert abs(actual - expected[key]) < TOLERANCE, (
            f"{key}: {actual!r} vs Excel {expected[key]!r}"
        )


def test_modes_select_different_benchmarks_and_both_simulate() -> None:
    config = benchmark_config()
    data = panel()
    weights = {c.name: 1.0 / len(config.classes) for c in config.classes}

    switched = [c.name for c in config.classes if c.key_rate_spread_bp is not None]
    assert switched, "no asset class is configured to react to the mode switch"

    results = {}
    for mode in (INDEX_MODE, KEY_RATE_MODE):
        sim = simulate(
            Scenario(name=mode, weights=weights, mode=mode),
            data,
            list(config.classes),
            risk_free_ticker=config.risk_free,
        )
        assert sim.months, f"{mode} produced no months"
        results[mode] = sim

    assert results[INDEX_MODE].benchmarks != results[KEY_RATE_MODE].benchmarks
    # The stand-ins have almost no variance, so the key-rate run must look calmer.
    assert results[KEY_RATE_MODE].stats().volatility < results[INDEX_MODE].stats().volatility


def test_per_class_override_beats_the_mode() -> None:
    config = benchmark_config()
    sim = simulate(
        Scenario(
            name="override",
            weights={"Immobilien": 1.0},
            benchmarks={"Immobilien": "LBEATREU Index"},
            mode=KEY_RATE_MODE,
        ),
        panel(),
        list(config.classes),
    )
    assert sim.benchmarks == ["LBEATREU Index"]
    assert sim.proxy_members == []


def test_scenario_without_mode_defaults_to_the_excel_behaviour() -> None:
    assert Scenario.from_dict({"name": "alt", "weights": {}}).mode == KEY_RATE_MODE
    assert Scenario.from_dict({"name": "x", "mode": "bogus"}).mode == KEY_RATE_MODE
    assert Scenario.from_dict({"name": "x", "mode": INDEX_MODE}).mode == INDEX_MODE




# --------------------------------------------------------------------------- #
# book-yield curves (held-to-maturity)
# --------------------------------------------------------------------------- #
def _empty_panel(months: list[str]) -> ReturnPanel:
    return ReturnPanel(months=months, tickers=[], values=np.empty((len(months), 0)))


MONTHS = [f"{y:04d}-{m:02d}" for y in range(2000, 2006) for m in range(1, 13)]


def test_yield_curve_steps_hold_until_the_next_anchor() -> None:
    curve = YieldCurve(
        name="book",
        label="book",
        schedule=(("2001-01", 0.04), ("2003-01", 0.02)),
        interpolate=False,
    )
    column = build_yield_series(_empty_panel(MONTHS), [curve]).column("book")
    index = {m: i for i, m in enumerate(MONTHS)}

    # Nothing before the first anchor.
    assert np.isnan(column[index["2000-12"]])
    # 4 % holds right up to the month before the next anchor, then steps.
    for month in ("2001-01", "2002-06", "2002-12"):
        assert abs((1 + column[index[month]]) ** 12 - 1 - 0.04) < 1e-12, month
    for month in ("2003-01", "2005-12"):
        assert abs((1 + column[index[month]]) ** 12 - 1 - 0.02) < 1e-12, month


def test_yield_curve_interpolates_between_anchors() -> None:
    curve = YieldCurve(
        name="book",
        label="book",
        schedule=(("2001-01", 0.04), ("2003-01", 0.02)),
        interpolate=True,
    )
    column = build_yield_series(_empty_panel(MONTHS), [curve]).column("book")
    index = {m: i for i, m in enumerate(MONTHS)}

    # Endpoints are exact, the midpoint is halfway, and it only ever falls.
    assert abs((1 + column[index["2001-01"]]) ** 12 - 1 - 0.04) < 1e-12
    assert abs((1 + column[index["2002-01"]]) ** 12 - 1 - 0.03) < 1e-12
    assert abs((1 + column[index["2003-01"]]) ** 12 - 1 - 0.02) < 1e-12
    window = column[index["2001-01"] : index["2003-01"] + 1]
    assert np.all(np.diff(window) < 0)


def test_yield_curve_compounding_conventions() -> None:
    schedule = (("2001-01", 0.06),)
    geometric = build_yield_series(
        _empty_panel(MONTHS), [YieldCurve("g", "g", schedule)]
    ).column("g")
    simple = build_yield_series(
        _empty_panel(MONTHS), [YieldCurve("s", "s", schedule, compounding="simple")]
    ).column("s")
    index = MONTHS.index("2001-06")

    # Geometric compounds to exactly the stated yield; simple is rate/12.
    assert abs((1 + geometric[index]) ** 12 - 1 - 0.06) < 1e-12
    assert abs(simple[index] - 0.06 / 12) < 1e-15
    assert simple[index] > geometric[index]


def test_configured_yield_curves_land_in_the_panel() -> None:
    config = benchmark_config()
    data = panel()
    for curve in config.yield_curves:
        assert data.has(curve.name), curve.name
        column = data.column(curve.name)
        assert np.isfinite(column).any(), f"{curve.name} is empty"
        # An accrual series never goes backwards.
        assert np.nanmin(column) >= 0.0, curve.name


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"PASS {name}")
