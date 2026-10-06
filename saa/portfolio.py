"""Turning a set of SAA weights into a simulated portfolio and its diagnostics.

The model is the one BM-Tool used: a monthly-rebalanced portfolio of benchmark
indices, less a flat TER accrued monthly.

    r_portfolio(t) = sum_i w_i * r_benchmark(i, t) - ((1 + TER) ^ (1/12) - 1)

The simulation window is the overlap of every benchmark that carries weight, so
adding a short-history asset class shortens the comparable period rather than
silently dropping months.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from . import metrics
from .data import AssetClass, ReturnPanel


@dataclass
class Scenario:
    """A named set of weights - what the user saves and compares."""

    name: str
    weights: dict[str, float] = field(default_factory=dict)
    benchmarks: dict[str, str] = field(default_factory=dict)
    ter: float = 0.0
    notes: str = ""

    def normalised(self) -> dict[str, float]:
        total = sum(self.weights.values())
        if total == 0:
            return dict(self.weights)
        return {k: v / total for k, v in self.weights.items()}

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "weights": self.weights,
            "benchmarks": self.benchmarks,
            "ter": self.ter,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, raw: dict) -> "Scenario":
        return cls(
            name=str(raw.get("name", "Unbenannt")),
            weights={str(k): float(v) for k, v in (raw.get("weights") or {}).items()},
            benchmarks={str(k): str(v) for k, v in (raw.get("benchmarks") or {}).items()},
            ter=float(raw.get("ter", 0.0) or 0.0),
            notes=str(raw.get("notes", "")),
        )


@dataclass
class Simulation:
    scenario: Scenario
    months: list[str]
    returns: np.ndarray
    gross_returns: np.ndarray
    risk_free: np.ndarray
    members: list[str]
    weights: np.ndarray
    benchmarks: list[str]
    asset_returns: np.ndarray
    window_limited_by: list[str]
    warnings: list[str] = field(default_factory=list)

    # -- headline figures -------------------------------------------------
    def stats(self) -> metrics.Stats:
        return metrics.summarise(self.returns, self.months, self.risk_free)

    def gross_stats(self) -> metrics.Stats:
        return metrics.summarise(self.gross_returns, self.months, self.risk_free)

    def wealth_curve(self, base: float = 100.0) -> np.ndarray:
        return metrics.wealth_curve(self.returns, base)

    def drawdown_series(self) -> np.ndarray:
        return metrics.drawdown_series(self.returns)

    # -- attribution ------------------------------------------------------
    def performance_contribution(self) -> list[dict]:
        """Geometric contribution per asset class, as BM-Tool rows 58-62 did.

        For each class, compound its own weighted return stream
        ``PRODUCT(1 + w_i * r_i) - 1`` and report both the absolute figure and
        its share of the summed contributions.
        """
        rows: list[dict] = []
        for idx, member in enumerate(self.members):
            weighted = self.weights[idx] * self.asset_returns[:, idx]
            rows.append(
                {
                    "asset_class": member,
                    "benchmark": self.benchmarks[idx],
                    "weight": float(self.weights[idx]),
                    "contribution": float(np.prod(1.0 + weighted) - 1.0),
                }
            )
        total = sum(r["contribution"] for r in rows)
        for row in rows:
            row["share"] = row["contribution"] / total if total else 0.0
        return rows

    def covariance(self) -> np.ndarray:
        if self.asset_returns.shape[0] < 2:
            return np.zeros((len(self.members), len(self.members)))
        return np.cov(self.asset_returns, rowvar=False, ddof=1)

    def correlation(self) -> np.ndarray:
        cov = self.covariance()
        sd = np.sqrt(np.diag(cov))
        safe = np.where(sd == 0, 1.0, sd)
        corr = cov / np.outer(safe, safe)
        corr[sd == 0, :] = np.nan
        corr[:, sd == 0] = np.nan
        np.fill_diagonal(corr, 1.0)
        return corr

    def risk_contribution(self) -> list[dict]:
        """Marginal and component risk per asset class.

        ``marginal_i = (Sigma w)_i / sigma_p`` and
        ``component_i = w_i * marginal_i``; the components sum to ``sigma_p``,
        which is the identity BM-Tool checked in its L87 cell.
        """
        cov = self.covariance()
        w = self.weights
        variance = float(w @ cov @ w)
        sigma = math.sqrt(variance) if variance > 0 else 0.0
        marginal = (cov @ w) / sigma if sigma else np.zeros_like(w)
        component = w * marginal
        rows = []
        for idx, member in enumerate(self.members):
            rows.append(
                {
                    "asset_class": member,
                    "benchmark": self.benchmarks[idx],
                    "weight": float(w[idx]),
                    "volatility": float(
                        math.sqrt(max(cov[idx, idx], 0.0)) * math.sqrt(12)
                    ),
                    "marginal_risk": float(marginal[idx] * math.sqrt(12)),
                    "component_risk": float(component[idx] * math.sqrt(12)),
                    "share": float(component[idx] / sigma) if sigma else 0.0,
                }
            )
        return rows

    def to_dict(self) -> dict:
        stats = self.stats()
        return {
            "scenario": self.scenario.to_dict(),
            "members": self.members,
            "benchmarks": self.benchmarks,
            "weights": [float(w) for w in self.weights],
            "months": self.months,
            "returns": [float(x) for x in self.returns],
            "wealth": [float(x) for x in self.wealth_curve()],
            "drawdown": [float(x) for x in self.drawdown_series()],
            "stats": stats.to_dict(),
            "gross_stats": self.gross_stats().to_dict(),
            "calendar_years": metrics.calendar_years(self.returns, self.months),
            "rolling": metrics.rolling(self.returns, self.months),
            "performance_contribution": self.performance_contribution(),
            "risk_contribution": self.risk_contribution(),
            "window_limited_by": self.window_limited_by,
            "warnings": self.warnings,
        }


def resolve_benchmarks(
    scenario: Scenario, classes: list[AssetClass]
) -> dict[str, str]:
    """Per class: the scenario's override if set, else the configured default."""
    by_name = {c.name: c for c in classes}
    out: dict[str, str] = {}
    for name in scenario.weights:
        chosen = scenario.benchmarks.get(name)
        if chosen:
            out[name] = chosen
        elif name in by_name:
            out[name] = by_name[name].benchmark
    return out


def simulate(
    scenario: Scenario,
    panel: ReturnPanel,
    classes: list[AssetClass],
    risk_free_ticker: str = "",
    start: str | None = None,
    end: str | None = None,
    normalise: bool = True,
) -> Simulation:
    """Build the portfolio return series for ``scenario``."""
    warnings: list[str] = []
    weights_map = scenario.normalised() if normalise else dict(scenario.weights)

    total = sum(scenario.weights.values())
    if normalise and total and abs(total - 1.0) > 1e-9:
        warnings.append(
            f"Gewichte summieren auf {total:.4f} und wurden auf 100 % normiert."
        )

    chosen = resolve_benchmarks(scenario, classes)
    members: list[str] = []
    benchmarks: list[str] = []
    weight_values: list[float] = []
    for name, weight in weights_map.items():
        if weight == 0:
            continue
        ticker = chosen.get(name)
        if not ticker:
            warnings.append(f"{name}: kein Benchmark konfiguriert - übersprungen.")
            continue
        if not panel.has(ticker):
            warnings.append(f"{name}: Zeitreihe {ticker!r} fehlt - übersprungen.")
            continue
        members.append(name)
        benchmarks.append(ticker)
        weight_values.append(float(weight))

    if not members:
        return Simulation(
            scenario=scenario,
            months=[],
            returns=np.zeros(0),
            gross_returns=np.zeros(0),
            risk_free=np.zeros(0),
            members=[],
            weights=np.zeros(0),
            benchmarks=[],
            asset_returns=np.zeros((0, 0)),
            window_limited_by=[],
            warnings=warnings + ["Keine Assetklasse mit Gewicht > 0."],
        )

    matrix = panel.matrix(benchmarks)
    complete = ~np.isnan(matrix).any(axis=1)

    all_months = np.asarray(panel.months)
    if start:
        complete &= all_months >= start
    if end:
        complete &= all_months <= end

    rows = np.flatnonzero(complete)
    if rows.size == 0:
        return Simulation(
            scenario=scenario,
            months=[],
            returns=np.zeros(0),
            gross_returns=np.zeros(0),
            risk_free=np.zeros(0),
            members=members,
            weights=np.asarray(weight_values),
            benchmarks=benchmarks,
            asset_returns=np.zeros((0, len(members))),
            window_limited_by=[],
            warnings=warnings
            + ["Kein Monat, in dem alle gewählten Benchmarks Daten haben."],
        )

    # Keep one contiguous block: the overlap of all series, no interior gaps.
    first, last = int(rows[0]), int(rows[-1])
    gaps = [
        panel.months[i] for i in range(first, last + 1) if not complete[i]
    ]
    if gaps:
        warnings.append(
            f"{len(gaps)} Monate im Zeitraum ohne vollständige Daten übersprungen "
            f"(z. B. {', '.join(gaps[:3])})."
        )

    months = [panel.months[i] for i in rows]
    asset_returns = matrix[rows, :]
    weights = np.asarray(weight_values, dtype=float)

    gross = asset_returns @ weights
    monthly_cost = (1.0 + scenario.ter) ** (1.0 / 12.0) - 1.0 if scenario.ter else 0.0
    net = gross - monthly_cost

    if risk_free_ticker and panel.has(risk_free_ticker):
        rf_column = panel.column(risk_free_ticker)[rows]
        rf = np.nan_to_num(rf_column, nan=0.0)
        if np.isnan(rf_column).any():
            warnings.append(
                f"Risikoloser Zins ({risk_free_ticker}) fehlt in "
                f"{int(np.isnan(rf_column).sum())} Monaten, dort mit 0 % gerechnet."
            )
    else:
        rf = np.zeros(rows.size)
        if risk_free_ticker:
            warnings.append(
                f"Risikolose Zeitreihe {risk_free_ticker!r} nicht gefunden - "
                "Sharpe/Sortino gegen 0 % gerechnet."
            )

    # Which benchmarks actually set the start of the window?
    limiters = []
    for idx, ticker in enumerate(benchmarks):
        column = panel.column(ticker)
        valid = np.flatnonzero(~np.isnan(column))
        if valid.size and int(valid[0]) >= first:
            limiters.append(f"{members[idx]} ({ticker}, ab {panel.months[int(valid[0])]})")

    return Simulation(
        scenario=scenario,
        months=months,
        returns=net,
        gross_returns=gross,
        risk_free=rf,
        members=members,
        weights=weights,
        benchmarks=benchmarks,
        asset_returns=asset_returns,
        window_limited_by=limiters,
        warnings=warnings,
    )


def align(simulations: list[Simulation]) -> tuple[list[str], dict[str, np.ndarray]]:
    """Restrict several simulations to their common months, for fair comparison."""
    if not simulations:
        return [], {}
    shared = set(simulations[0].months)
    for sim in simulations[1:]:
        shared &= set(sim.months)
    months = sorted(shared)
    out: dict[str, np.ndarray] = {}
    for sim in simulations:
        index = {m: i for i, m in enumerate(sim.months)}
        out[sim.scenario.name] = np.asarray(
            [sim.returns[index[m]] for m in months], dtype=float
        )
    return months, out
