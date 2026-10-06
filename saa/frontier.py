"""Markowitz efficient frontier for the configured asset classes.

Long-only, fully invested, with optional per-class bounds.  Deliberately has no
SciPy dependency: the mean-variance problem

    minimise  1/2 w' S w  -  lambda mu' w
    s.t.      sum(w) = 1,  lo <= w <= hi

is solved by projected gradient descent, because projecting onto
``{sum(w) = 1, lo <= w <= hi}`` has a closed form (a clipped simplex
projection, found by bisection on a single scalar shift).  Sweeping ``lambda``
from 0 upwards traces the frontier from the minimum-variance portfolio to the
highest-return portfolio the bounds allow.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

MONTHS_PER_YEAR = 12


@dataclass
class FrontierPoint:
    volatility: float
    cagr: float
    arithmetic_return: float
    sharpe: float
    weights: dict[str, float]


def project_to_simplex(
    v: np.ndarray, lo: np.ndarray, hi: np.ndarray, total: float = 1.0
) -> np.ndarray:
    """Euclidean projection of ``v`` onto {sum(w)=total, lo<=w<=hi}.

    ``w(theta) = clip(v - theta, lo, hi)`` and ``g(theta) = sum(w(theta))`` is
    piecewise linear and non-increasing, with breakpoints at ``v - hi`` (where a
    weight leaves its upper bound) and ``v - lo`` (where it reaches its lower
    bound).  Sorting those 2n breakpoints locates the segment holding the root,
    and on that segment the root is one division away - no iteration needed.
    """
    v = np.asarray(v, dtype=float)
    lo = np.asarray(lo, dtype=float)
    hi = np.asarray(hi, dtype=float)
    if lo.sum() > total + 1e-12 or hi.sum() < total - 1e-12:
        raise ValueError(
            f"bounds cannot sum to {total}: min {lo.sum():.4f}, max {hi.sum():.4f}"
        )

    breaks = np.sort(np.concatenate((v - hi, v - lo)))
    sums = np.clip(v[None, :] - breaks[:, None], lo, hi).sum(axis=1)

    # g is non-increasing, g(breaks[0]) = sum(hi) >= total >= sum(lo) = g(breaks[-1]),
    # so the first breakpoint at or below the target closes the bracket.
    reached = np.flatnonzero(sums <= total)
    if reached.size == 0 or reached[0] == 0:
        edge = breaks[0] if reached.size else breaks[-1]
        return np.clip(v - edge, lo, hi)

    index = int(reached[0])
    probe = 0.5 * (breaks[index - 1] + breaks[index])
    shifted = v - probe
    at_hi = shifted >= hi
    at_lo = shifted <= lo
    free = ~(at_hi | at_lo)

    if not np.any(free):
        return np.clip(v - breaks[index], lo, hi)

    pinned = float(hi[at_hi].sum() + lo[at_lo].sum())
    theta = (float(v[free].sum()) + pinned - total) / float(free.sum())
    return np.clip(v - theta, lo, hi)


def step_size(cov: np.ndarray) -> float:
    """1/L for projected gradient, L = largest eigenvalue of the covariance."""
    return 1.0 / float(max(np.linalg.eigvalsh(cov)[-1], 1e-14))


def _solve(
    cov: np.ndarray,
    mu: np.ndarray,
    lam: float,
    lo: np.ndarray,
    hi: np.ndarray,
    step: float,
    start: np.ndarray | None = None,
    iterations: int = 250,
) -> np.ndarray:
    """Projected-gradient solve of min 1/2 w'Sw - lam mu'w over the feasible set."""
    n = cov.shape[0]
    seed = np.full(n, 1.0 / n) if start is None else start
    previous = project_to_simplex(seed, lo, hi)
    momentum = previous.copy()
    for k in range(iterations):
        gradient = cov @ momentum - lam * mu
        candidate = project_to_simplex(momentum - step * gradient, lo, hi)
        beta = k / (k + 3.0)  # FISTA-style acceleration
        momentum = project_to_simplex(candidate + beta * (candidate - previous), lo, hi)
        converged = np.max(np.abs(candidate - previous)) < 1e-12
        previous = candidate
        if converged:
            break
    return previous


def max_return_weights(mu: np.ndarray, lo: np.ndarray, hi: np.ndarray) -> np.ndarray:
    """Greedy LP solution: the feasible portfolio with the highest mean return."""
    weights = lo.astype(float).copy()
    budget = 1.0 - weights.sum()
    for idx in np.argsort(-mu):
        if budget <= 1e-15:
            break
        room = min(hi[idx] - weights[idx], budget)
        if room > 0:
            weights[idx] += room
            budget -= room
    return weights


def _point(
    weights: np.ndarray,
    names: list[str],
    cov: np.ndarray,
    mu: np.ndarray,
    returns: np.ndarray,
    risk_free_monthly: float,
) -> FrontierPoint:
    variance = float(weights @ cov @ weights)
    vol = math.sqrt(max(variance, 0.0)) * math.sqrt(MONTHS_PER_YEAR)
    series = returns @ weights
    growth = float(np.prod(1.0 + series))
    compounded = growth ** (MONTHS_PER_YEAR / series.size) - 1.0 if series.size else 0.0
    arithmetic = float(np.mean(series)) * MONTHS_PER_YEAR
    excess = float(np.mean(series) - risk_free_monthly) * MONTHS_PER_YEAR
    return FrontierPoint(
        volatility=vol,
        cagr=compounded,
        arithmetic_return=arithmetic,
        sharpe=excess / vol if vol else 0.0,
        weights={name: float(w) for name, w in zip(names, weights)},
    )


def efficient_frontier(
    returns: np.ndarray,
    names: list[str],
    points: int = 40,
    bounds: dict[str, tuple[float, float]] | None = None,
    risk_free: np.ndarray | None = None,
) -> dict:
    """Trace the long-only frontier for the asset classes in ``returns``.

    ``returns`` is months x classes of monthly decimal returns.  Returns the
    frontier points, the single-asset points, and the min-variance and
    max-Sharpe portfolios.
    """
    if returns.ndim != 2 or returns.shape[1] != len(names):
        raise ValueError("returns must be months x len(names)")
    if returns.shape[0] < 3:
        return {
            "points": [],
            "assets": [],
            "min_variance": None,
            "max_sharpe": None,
            "error": "Zu wenige gemeinsame Monate für eine Effizienzlinie.",
        }

    n = len(names)
    cov = np.cov(returns, rowvar=False, ddof=1).reshape(n, n)
    mu = returns.mean(axis=0)
    rf_monthly = float(np.mean(risk_free)) if risk_free is not None and len(risk_free) else 0.0

    bounds = bounds or {}
    lo = np.asarray([float(bounds.get(name, (0.0, 1.0))[0]) for name in names])
    hi = np.asarray([float(bounds.get(name, (0.0, 1.0))[1]) for name in names])
    if lo.sum() > 1.0 + 1e-9:
        return {
            "points": [], "assets": [], "min_variance": None, "max_sharpe": None,
            "error": f"Die Mindestgewichte summieren auf {lo.sum():.0%} - über 100 %.",
        }
    if hi.sum() < 1.0 - 1e-9:
        return {
            "points": [], "assets": [], "min_variance": None, "max_sharpe": None,
            "error": f"Die Maximalgewichte summieren auf {hi.sum():.0%} - unter 100 %.",
        }

    # lambda = 0 is the minimum-variance portfolio; raising lambda walks up the
    # frontier until the bounds stop the return from growing.
    scale = float(np.max(np.abs(cov))) if np.any(cov) else 1.0
    spread = float(np.max(mu) - np.min(mu))
    ceiling = float(mu @ max_return_weights(mu, lo, hi))

    step = step_size(cov)
    minimum_variance = _solve(cov, mu, 0.0, lo, hi, step)
    floor = float(mu @ minimum_variance)

    raw: list[FrontierPoint] = [
        _point(minimum_variance, names, cov, mu, returns, rf_monthly)
    ]

    if spread > 0 and ceiling - floor > 1e-12:
        # Find a lambda large enough to reach the maximum-return corner.
        lam_cap = max(scale / max(spread, 1e-12), 1e-9)
        for _ in range(80):
            probe = _solve(cov, mu, lam_cap, lo, hi, step, iterations=60)
            if float(mu @ probe) >= ceiling - 1e-8:
                break
            lam_cap *= 2.0

        # Log spacing concentrates points where the frontier actually bends.
        grid = np.logspace(
            math.log10(lam_cap) - 5.0, math.log10(lam_cap), max(points, 2) * 4
        )
        warm = minimum_variance
        for lam in grid:
            warm = _solve(cov, mu, float(lam), lo, hi, step, start=warm)
            raw.append(_point(warm, names, cov, mu, returns, rf_monthly))

    # Keep the upper envelope: sort by risk, drop points no better in return.
    raw.sort(key=lambda p: (p.volatility, -p.arithmetic_return))
    envelope: list[FrontierPoint] = []
    best = -math.inf
    for candidate in raw:
        if candidate.arithmetic_return > best + 1e-9:
            envelope.append(candidate)
            best = candidate.arithmetic_return

    # Thin the envelope down to roughly ``points`` evenly spaced in risk.
    if len(envelope) > points:
        lowest, highest = envelope[0].volatility, envelope[-1].volatility
        wanted = np.linspace(lowest, highest, points)
        thinned: list[FrontierPoint] = []
        cursor = 0
        for target in wanted:
            while (
                cursor + 1 < len(envelope)
                and abs(envelope[cursor + 1].volatility - target)
                <= abs(envelope[cursor].volatility - target)
            ):
                cursor += 1
            if not thinned or envelope[cursor] is not thinned[-1]:
                thinned.append(envelope[cursor])
        envelope = thinned

    assets = []
    for idx, name in enumerate(names):
        unit = np.zeros(n)
        unit[idx] = 1.0
        single = _point(unit, names, cov, mu, returns, rf_monthly)
        assets.append(
            {
                "asset_class": name,
                "volatility": single.volatility,
                "cagr": single.cagr,
                "sharpe": single.sharpe,
                "feasible": bool(lo[idx] <= 1.0 <= hi[idx] + 1e-12),
            }
        )

    min_variance = min(raw, key=lambda p: p.volatility) if raw else None
    max_sharpe = max(envelope or raw, key=lambda p: p.sharpe) if raw else None

    return {
        "points": [_as_dict(p) for p in envelope],
        "assets": assets,
        "min_variance": _as_dict(min_variance) if min_variance else None,
        "max_sharpe": _as_dict(max_sharpe) if max_sharpe else None,
        "error": None,
    }


def _as_dict(point: FrontierPoint) -> dict:
    return {
        "volatility": point.volatility,
        "cagr": point.cagr,
        "arithmetic_return": point.arithmetic_return,
        "sharpe": point.sharpe,
        "weights": point.weights,
    }
