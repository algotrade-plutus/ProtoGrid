"""Equity-curve metrics, shared by both arms."""
from __future__ import annotations

import math
from typing import Dict, List, Sequence


def hpr(equity: Sequence[float]) -> float:
    return equity[-1] / equity[0] - 1.0 if equity and equity[0] else 0.0


def max_drawdown(equity: Sequence[float]) -> float:
    peak, mdd = -math.inf, 0.0
    for v in equity:
        peak = max(peak, v)
        if peak > 0:
            mdd = min(mdd, v / peak - 1.0)
    return mdd


def sharpe(equity: Sequence[float], periods: int = 252) -> float:
    rets: List[float] = [b / a - 1.0 for a, b in zip(equity, equity[1:]) if a]
    if len(rets) < 2:
        return 0.0
    mu = sum(rets) / len(rets)
    var = sum((r - mu) ** 2 for r in rets) / (len(rets) - 1)
    return mu / math.sqrt(var) * math.sqrt(periods) if var > 0 else 0.0


def summary(equity: Sequence[float]) -> Dict[str, float]:
    return {"hpr": round(hpr(equity), 6),
            "max_drawdown": round(max_drawdown(equity), 6),
            "sharpe": round(sharpe(equity), 4)}
