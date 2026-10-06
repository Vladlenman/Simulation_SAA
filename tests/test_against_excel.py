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

from saa.data import AssetClass, load_asset_classes, load_panel
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
    classes, risk_free = load_asset_classes()
    panel = load_panel()
    missing = [c.name for c in classes if not panel.has(c.benchmark)]
    assert not missing, f"configured benchmarks not in the data: {missing}"
    assert panel.has(risk_free), risk_free
    for cls in classes:
        unknown = [t for t in cls.benchmark_choices() if not panel.has(t)]
        assert not unknown, f"{cls.name}: unknown alternatives {unknown}"


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"PASS {name}")
