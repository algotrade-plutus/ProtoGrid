"""The naive grid engine: the developer's default backtester.

What it assumes, deliberately (design 2026-09-14, section 4a):

* every resting rung fills **in full, at its own price**, on the first
  continuous-session print at or through it (unlimited size, no queue);
* **no** price band (a rung below the floor or a sell above the ceiling is
  placed and can fill), **no** band lock, **no** tick-grid or lot check;
* **instant cash**: a sale's proceeds fund the next buy on the same tick (no
  T+2), and shares bought can be sold at once;
* the **static assumed cost**: 0.15% on a buy and 0.25% on a sell (0.15%
  commission + 0.1% tax), i.e. 0.4% per round trip.

It drives the same :class:`~proto_grid.strategy.PairedGrid` as the faithful
arm, over the same tape (``proto_grid.data``).
"""
from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

from proto_grid import data as D
from proto_grid.metrics import summary
from proto_grid.strategy import PRICE_SCALE, Intent, PairedGrid


@dataclass
class ArmResult:
    """What either arm reports. Money in dong, prices in thousand VND."""

    fills: int = 0
    buy_fills: int = 0
    sell_fills: int = 0
    round_trips: int = 0
    traded_value_vnd: float = 0.0
    costs_vnd: float = 0.0
    equity: List[float] = field(default_factory=list)
    days: List[str] = field(default_factory=list)
    fills_by_ticker: Dict[str, int] = field(default_factory=dict)
    final_holdings: Dict[str, int] = field(default_factory=dict)

    def as_dict(self) -> dict:
        out = {
            "fills": self.fills, "buy_fills": self.buy_fills,
            "sell_fills": self.sell_fills, "round_trips": self.round_trips,
            "traded_value_vnd": round(self.traded_value_vnd),
            "costs_vnd": round(self.costs_vnd),
            "initial_equity_vnd": round(self.equity[0]) if self.equity else None,
            "final_equity_vnd": round(self.equity[-1]) if self.equity else None,
            "fills_by_ticker": dict(sorted(self.fills_by_ticker.items())),
            "final_holdings": dict(sorted(self.final_holdings.items())),
            "sessions": len(self.days) - 1 if self.days else 0,
        }
        out.update(summary(self.equity))
        return out


def build_grids(params: dict) -> Dict[str, PairedGrid]:
    per_grid = Decimal(params["capital_vnd"]) / Decimal(len(params["tickers"]))
    return {t: PairedGrid(t, per_grid, n_rungs=params["n_rungs"],
                          assumed_cost_rate=Decimal(
                              str(params["assumed_round_trip_cost"])),
                          margin=params["delta_margin"])
            for t in params["tickers"]}


def run_naive(window: str, params: Optional[dict] = None,
              tape: Optional[List[D.Tick]] = None) -> ArmResult:
    params = params or D.load_params()
    tape = tape if tape is not None else D.load_tape(window, params)
    days = D.trading_days(tape)
    anchors = D.month_anchors(window, params, days)
    grids = build_grids(params)
    buy_cost = Decimal(str(params["assumed_buy_cost"]))
    sell_cost = Decimal(str(params["assumed_sell_cost"]))

    cash = Decimal(params["capital_vnd"])
    held: Counter = Counter()
    last: Dict[str, Decimal] = {}
    res = ArmResult(equity=[float(cash)], days=["start"])
    by_day: Dict[date, List[D.Tick]] = {}
    for k in tape:
        by_day.setdefault(k.ts.date(), []).append(k)

    month: Optional[Tuple[int, int]] = None
    for day in days:
        if (day.year, day.month) != month:
            month = (day.year, day.month)
            for t, g in grids.items():
                a = anchors.get((t, month))
                if a is not None:
                    g.reanchor(a)
        # the resting book: (ticker, slot) -> intent, rebuilt each morning
        book: Dict[Tuple[str, int], Intent] = {
            (it.ticker, it.slot): it for g in grids.values() for it in g.intents()}
        for k in by_day[day]:
            last[k.ticker] = k.price
            hit = [it for (t, _), it in book.items() if t == k.ticker and (
                (it.side == "buy" and k.price <= it.price)
                or (it.side == "sell" and k.price >= it.price))]
            for it in sorted(hit, key=lambda i: (i.side, i.slot)):
                value = it.price * PRICE_SCALE * it.quantity
                if it.side == "buy":
                    cost = value * buy_cost
                    cash -= value + cost
                    held[it.ticker] += it.quantity
                    res.buy_fills += 1
                else:
                    cost = value * sell_cost
                    cash += value - cost
                    held[it.ticker] -= it.quantity
                    res.sell_fills += 1
                res.fills += 1
                res.fills_by_ticker[it.ticker] = res.fills_by_ticker.get(
                    it.ticker, 0) + 1
                res.traded_value_vnd += float(value)
                res.costs_vnd += float(cost)
                g = grids[it.ticker]
                g.on_fill(it.slot, it.side, it.price, it.quantity)
                nxt = g.intent_for(it.slot)
                if nxt is None:
                    book.pop((it.ticker, it.slot), None)
                else:
                    book[(it.ticker, it.slot)] = nxt
        mark = sum((held[t] * last.get(t, Decimal(0)) * PRICE_SCALE
                    for t in held), Decimal(0))
        res.equity.append(float(cash + mark))
        res.days.append(day.isoformat())
    res.round_trips = sum(g.round_trips for g in grids.values())
    res.final_holdings = {t: int(q) for t, q in held.items()}
    return res


def main() -> None:
    params = D.load_params()
    out = {w: run_naive(w, params).as_dict() for w in params["windows"]}
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
