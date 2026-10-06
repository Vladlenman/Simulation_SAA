"""Performance and risk statistics for a monthly return series.

Everything works on monthly decimal returns and annualises with 12 periods,
matching the conventions the BM-Tool Excel sheet used:

    Total Return  PRODUCT(1 + r) - 1
    Rendite p.a.  (1 + TotalReturn) ^ (12 / n) - 1
    Vola p.a.     STDEV.S(r) * SQRT(12)                (sample, n-1)
    Sharpe        12 * mean(r - rf) / (SQRT(12) * STDEV.S(r - rf))

One deliberate change from the workbook: the Sharpe ratio uses the risk-free
series over the *whole* period.  BM-Tool's excess-return column (AN) was only
populated from row 123 (2011-01) onwards, so its Sharpe mixed gross returns
before 2011 with excess returns after - see docs/excel-workbook-notes.md.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass

import numpy as np

MONTHS_PER_YEAR = 12


@dataclass
class Drawdown:
    depth: float
    peak_month: str | None
    trough_month: str | None
    recovery_month: str | None
    months_peak_to_trough: int
    months_to_recovery: int | None


@dataclass
class Stats:
    start: str | None
    end: str | None
    months: int
    total_return: float
    cagr: float
    volatility: float
    sharpe: float
    sortino: float
    max_drawdown: float
    calmar: float
    best_month: float
    worst_month: float
    positive_share: float
    var_95: float
    cvar_95: float
    risk_free_cagr: float
    drawdown: Drawdown

    def to_dict(self) -> dict:
        out = asdict(self)
        out["drawdown"] = asdict(self.drawdown)
        return out


def _clean(values: np.ndarray) -> np.ndarray:
    return np.asarray(values, dtype=float)


def total_return(returns: np.ndarray) -> float:
    returns = _clean(returns)
    if returns.size == 0:
        return 0.0
    return float(np.prod(1.0 + returns) - 1.0)


def cagr(returns: np.ndarray) -> float:
    returns = _clean(returns)
    if returns.size == 0:
        return 0.0
    growth = 1.0 + total_return(returns)
    if growth <= 0:
        return -1.0
    return float(growth ** (MONTHS_PER_YEAR / returns.size) - 1.0)


def volatility(returns: np.ndarray) -> float:
    returns = _clean(returns)
    if returns.size < 2:
        return 0.0
    return float(np.std(returns, ddof=1) * math.sqrt(MONTHS_PER_YEAR))


def sharpe(returns: np.ndarray, risk_free: np.ndarray | None = None) -> float:
    returns = _clean(returns)
    if returns.size < 2:
        return 0.0
    excess = returns if risk_free is None else returns - _clean(risk_free)
    spread = np.std(excess, ddof=1)
    if spread == 0:
        return 0.0
    return float(
        MONTHS_PER_YEAR * np.mean(excess) / (math.sqrt(MONTHS_PER_YEAR) * spread)
    )


def sortino(returns: np.ndarray, risk_free: np.ndarray | None = None) -> float:
    returns = _clean(returns)
    if returns.size < 2:
        return 0.0
    excess = returns if risk_free is None else returns - _clean(risk_free)
    shortfall = np.minimum(excess, 0.0)
    downside = math.sqrt(float(np.mean(shortfall**2)))
    if downside == 0:
        return 0.0
    return float(
        MONTHS_PER_YEAR * np.mean(excess) / (math.sqrt(MONTHS_PER_YEAR) * downside)
    )


def wealth_curve(returns: np.ndarray, base: float = 100.0) -> np.ndarray:
    """Indexed level series, starting at ``base`` *before* the first return."""
    returns = _clean(returns)
    return base * np.cumprod(1.0 + returns)


def drawdown_series(returns: np.ndarray) -> np.ndarray:
    curve = wealth_curve(returns)
    if curve.size == 0:
        return curve
    peaks = np.maximum.accumulate(np.concatenate(([100.0], curve)))[1:]
    return curve / peaks - 1.0


def max_drawdown(returns: np.ndarray, months: list[str] | None = None) -> Drawdown:
    returns = _clean(returns)
    if returns.size == 0:
        return Drawdown(0.0, None, None, None, 0, None)

    curve = wealth_curve(returns)
    running_peak = np.maximum.accumulate(np.concatenate(([100.0], curve)))[1:]
    underwater = curve / running_peak - 1.0

    trough = int(np.argmin(underwater))
    depth = float(underwater[trough])
    if depth == 0.0:
        return Drawdown(0.0, None, None, None, 0, None)

    peak_level = running_peak[trough]
    # The peak is the last month at or above the running peak before the trough.
    peak = trough
    while peak >= 0 and curve[peak] < peak_level:
        peak -= 1
    # peak == -1 means the drawdown started from the 100 base, before month 0.

    recovery = None
    for i in range(trough + 1, curve.size):
        if curve[i] >= peak_level:
            recovery = i
            break

    def label(i: int | None) -> str | None:
        if i is None or months is None:
            return None
        if i < 0:
            return "Start"
        return months[i] if i < len(months) else None

    return Drawdown(
        depth=depth,
        peak_month=label(peak),
        trough_month=label(trough),
        recovery_month=label(recovery),
        months_peak_to_trough=trough - peak,
        months_to_recovery=None if recovery is None else recovery - trough,
    )


def historic_var(returns: np.ndarray, level: float = 0.95) -> tuple[float, float]:
    """Monthly historical VaR and CVaR at ``level`` (both reported as losses)."""
    returns = _clean(returns)
    if returns.size == 0:
        return 0.0, 0.0
    cutoff = float(np.quantile(returns, 1.0 - level))
    tail = returns[returns <= cutoff]
    expected = float(np.mean(tail)) if tail.size else cutoff
    return cutoff, expected


def summarise(
    returns: np.ndarray,
    months: list[str] | None = None,
    risk_free: np.ndarray | None = None,
) -> Stats:
    returns = _clean(returns)
    draw = max_drawdown(returns, months)
    annual = cagr(returns)
    var_95, cvar_95 = historic_var(returns)
    return Stats(
        start=months[0] if months else None,
        end=months[-1] if months else None,
        months=int(returns.size),
        total_return=total_return(returns),
        cagr=annual,
        volatility=volatility(returns),
        sharpe=sharpe(returns, risk_free),
        sortino=sortino(returns, risk_free),
        max_drawdown=draw.depth,
        calmar=annual / abs(draw.depth) if draw.depth else 0.0,
        best_month=float(np.max(returns)) if returns.size else 0.0,
        worst_month=float(np.min(returns)) if returns.size else 0.0,
        positive_share=float(np.mean(returns > 0)) if returns.size else 0.0,
        var_95=var_95,
        cvar_95=cvar_95,
        risk_free_cagr=cagr(risk_free) if risk_free is not None else 0.0,
        drawdown=draw,
    )


def calendar_years(returns: np.ndarray, months: list[str]) -> list[dict]:
    """Return per calendar year, flagging years that are not fully covered."""
    returns = _clean(returns)
    out: list[dict] = []
    for year in sorted({m[:4] for m in months}):
        picks = [i for i, m in enumerate(months) if m.startswith(year)]
        if not picks:
            continue
        window = returns[picks]
        out.append(
            {
                "year": year,
                "return": total_return(window),
                "months": len(picks),
                "partial": len(picks) < 12,
            }
        )
    return out


def rolling(
    returns: np.ndarray, months: list[str], window: int = 24
) -> dict[str, list]:
    """Rolling annualised return and volatility, as BM-Tool's 24M columns did."""
    returns = _clean(returns)
    labels: list[str] = []
    ann_return: list[float] = []
    ann_vol: list[float] = []
    for end in range(window - 1, returns.size):
        chunk = returns[end - window + 1 : end + 1]
        labels.append(months[end])
        ann_return.append(cagr(chunk))
        ann_vol.append(volatility(chunk))
    return {"months": labels, "window": window, "return": ann_return, "volatility": ann_vol}
