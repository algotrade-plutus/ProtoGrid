"""Naive vs faithful: the same grid signals through two execution backends.

``python -m proto_grid.experiments.grid_anchor [--window W ...]`` writes
``result/grid_anchor/<window>.json`` with ``naive``, ``faithful`` and ``tier1``
blocks.

The faithful arm drives ``plutus.execution.PlutusBackend`` over an
``ExchangeSession`` at ``resolution: tick``, fed by the engine's ``TickSource``
(see ``tick_source.py``):

* ``soft`` fill policy (uncapped): a resting LIMIT fills, at its limit, when a
  continuous-session print reaches it -- the naive arm's own fill rule, so the
  gap is the market's rules, not a stricter fill model;
* every submission passes the session's admission gauntlet, including the
  **dated tick grid** (``TICK_GRID``), the 100-share lot and the **price band**
  (``BAND_LIMIT``, judged on the day's published ceiling/floor);
* the **tick book-tier band lock** (``band_lock_decision`` reading the resting
  ask/bid ladder, ``TICK_BOOK`` evidence) decides any order marketable into a
  band edge;
* **T+2** settlement of cash and shares, sale advance **off**; real dated
  statutory charges (0.1% sell PIT, ...) plus a 0.15% broker commission.

Orders are day orders. The driver submits a ticker's resting grid at its first
continuous print of the day and then advances the session clock to **every**
continuous-session print of the three names, in time order; the session
evaluates every live order at each one. A refused order is retried at the next
session's open; a fill's follow-up order (the paired sell, or the re-buy) is
submitted at the fill's instant and evaluated from that print on.
"""
from __future__ import annotations

import argparse
import json
import subprocess
from collections import Counter, defaultdict
from datetime import date, datetime, time
from decimal import Decimal
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from plutus.core.order import OrderType, Side
from plutus.execution import PlutusBackend
from plutus.market.protocol import Order
from plutus.market.session import Accepted, Rejected
from plutus.market.session.types import FillOutcome

from proto_grid import data as D
from proto_grid.backtest import ArmResult, build_grids, run_naive
from proto_grid.experiments.tick_source import DayCachedTickSource
from proto_grid.strategy import PRICE_SCALE, Intent

RESULT_DIR = D.REPO_ROOT / "result" / "grid_anchor"
ENGINE_ROOT = Path(__import__("plutus").__file__).resolve().parents[2]
COMMISSION = 0.0015
DAY_END = time(15, 0)
#: The headline is ``soft``. ``hard`` and ``probabilistic`` are the Tier-1
#: spread; both at the engine's 10% participation cap (hard's own default),
#: probabilistic with a fixed seed so the run reproduces.
POLICIES = {
    "soft": {"kind": "soft"},
    "hard": {"kind": "hard"},
    "probabilistic": {"kind": "probabilistic", "seed": 20261124,
                      "max_participation": 0.10},
}


class ObservedPolicy:
    """Delegates to the session's fill policy and tallies what it decided.

    Observation only: the decision is returned unchanged. It is how a
    fill-time ``BAND_LOCK`` no-fill, which emits no event, becomes countable.
    """

    def __init__(self, inner) -> None:
        self._inner = inner
        self.outcomes: Counter = Counter()
        self.band_lock_no_fills = 0
        self.band_edge_evaluations = 0
        self.evidence: Counter = Counter()

    def __getattr__(self, name):
        return getattr(self._inner, name)

    def evaluate(self, record, interval, rules, **kw):
        d = self._inner.evaluate(record, interval, rules, **kw)
        self.outcomes[d.outcome.value] += 1
        o = record.order
        st = interval.state
        if o.limit_price is not None and (
                (o.side is Side.BUY and st.ceiling is not None
                 and o.limit_price >= st.ceiling)
                or (o.side is Side.SELL and st.floor is not None
                    and o.limit_price <= st.floor)):
            self.band_edge_evaluations += 1
        if d.outcome is FillOutcome.NO_FILL and "BAND_LOCK" in (d.reason or ""):
            self.band_lock_no_fills += 1
        if d.outcome is FillOutcome.FILL and d.evidence is not None:
            self.evidence[d.evidence.value] += 1
        return d


def session_config(window: str, params: dict, policy: str,
                   advance_sale: bool) -> dict:
    spec = params["windows"][window]
    return {
        "period": {"start": spec["start"], "end": spec["end"]},
        "resolution": "tick",
        "exchange_rules": {"venues": ["HSX"]},
        "accounts": {"securities": {"initial_cash": params["capital_vnd"],
                                    "account_no": "SEC-GRID"}},
        "broker_profile": {
            "commission": [{"venue": "HSX", "base": "trade_value",
                            "rate": COMMISSION}],
            "advance_sale_proceeds": {"enabled": advance_sale},
        },
        "fill_policy": POLICIES[policy],
    }


def _order(it: Intent) -> Order:
    return Order(ticker=it.ticker,
                 side=Side.BUY if it.side == "buy" else Side.SELL,
                 quantity=it.quantity, order_type=OrderType.LIMIT,
                 limit_price=it.price)


def run_faithful(window: str, params: Optional[dict] = None, *,
                 policy: str = "soft", advance_sale: bool = False,
                 tape: Optional[List[D.Tick]] = None) -> Tuple[ArmResult, dict]:
    params = params or D.load_params()
    tape = tape if tape is not None else D.load_tape(window, params)
    days = D.trading_days(tape)
    anchors = D.month_anchors(window, params, days)
    grids = build_grids(params)
    source = DayCachedTickSource.for_window(window, params)
    backend = PlutusBackend.from_config(
        session_config(window, params, policy, advance_sale), source=source)
    observed = ObservedPolicy(backend.session._policy)
    backend.session._policy = observed

    res = ArmResult(equity=[float(params["capital_vnd"])], days=["start"])
    refusals: Counter = Counter()           # rule -> count
    refusals_by_side: Counter = Counter()   # (rule, side) -> count
    indeterminate_submits: Counter = Counter()
    t2_locked_rebuys = 0
    t2_unsettled_sells = 0
    cash_short_other = 0
    events: Counter = Counter()
    live: Dict[str, Intent] = {}             # order_id -> intent
    last: Dict[str, Decimal] = {}

    by_day: Dict[date, List[D.Tick]] = defaultdict(list)
    for k in tape:
        by_day[k.ts.date()].append(k)

    def submit(it: Intent) -> None:
        nonlocal t2_locked_rebuys, t2_unsettled_sells, cash_short_other
        ack = backend.submit(_order(it))
        if isinstance(ack, Accepted):
            live[ack.order_id] = it
            return
        rule = getattr(ack.rule, "value", str(ack.rule))
        if getattr(ack.verdict, "value", "") == "indeterminate":
            indeterminate_submits[rule] += 1
            return
        refusals[rule] += 1
        refusals_by_side[f"{rule}:{it.side}"] += 1
        if rule == "insufficient_cash":
            cash = backend.cash()
            need = it.price * PRICE_SCALE * it.quantity
            if cash.available < need <= cash.available + cash.pending_total:
                t2_locked_rebuys += 1
            else:
                cash_short_other += 1
        elif rule == "unsettled_holding":
            t2_unsettled_sells += 1

    def crosses(k: D.Tick) -> bool:
        return any(it.ticker == k.ticker and (
            (it.side == "buy" and k.price <= it.price)
            or (it.side == "sell" and k.price >= it.price))
            for it in live.values())

    def advance(ts: datetime) -> int:
        n = 0
        for ev in backend.advance_to(ts):
            kind = getattr(ev.kind, "value", str(ev.kind))
            events[kind] += 1
            if kind not in ("filled", "partially_filled"):
                continue
            it = live.get(ev.order_id)
            if it is None:
                continue
            n += 1
            value = ev.price * PRICE_SCALE * ev.quantity
            res.fills += 1
            res.buy_fills += it.side == "buy"
            res.sell_fills += it.side == "sell"
            res.fills_by_ticker[it.ticker] = res.fills_by_ticker.get(
                it.ticker, 0) + 1
            res.traded_value_vnd += float(value)
            g = grids[it.ticker]
            g.on_fill(it.slot, it.side, ev.price, ev.quantity)
            if kind == "filled":
                del live[ev.order_id]
                nxt = g.intent_for(it.slot)
                if nxt is not None:
                    submit(nxt)
            else:
                live[ev.order_id] = Intent(it.ticker, it.slot, it.side,
                                           it.price, it.quantity - ev.quantity)
        return n

    month = None
    for day in days:
        if (day.year, day.month) != month:
            month = (day.year, day.month)
            for t, g in grids.items():
                a = anchors.get((t, month))
                if a is not None:
                    g.reanchor(a)
        opened: set = set()
        for k in by_day[day]:
            last[k.ticker] = k.price
            if k.ticker not in opened:
                opened.add(k.ticker)
                advance(k.ts)
                for it in grids[k.ticker].intents():
                    submit(it)
            # every print; re-advance at the same instant while a fill's
            # follow-up order is itself reachable by this print
            while advance(k.ts) and crosses(k):
                pass
        advance(datetime.combine(day, DAY_END))
        live.clear()   # day orders: every one expired at the close
        cash = backend.cash()
        mark = sum((Decimal(backend.holdings(t).total) * last.get(t, Decimal(0))
                    * PRICE_SCALE for t in params["tickers"]), Decimal(0))
        res.equity.append(float(cash.settled_balance + cash.pending_total
                                + mark))
        res.days.append(day.isoformat())

    res.round_trips = sum(g.round_trips for g in grids.values())
    res.final_holdings = {t: backend.holdings(t).total
                          for t in params["tickers"]}
    res.costs_vnd = float(sum(c.amount for c in backend.charges()))
    ign = backend.indeterminate_report()
    tier1 = {
        "refusals_by_rule": dict(sorted(refusals.items())),
        "refusals_by_rule_and_side": dict(sorted(refusals_by_side.items())),
        "band_limit_refusals": refusals.get("band_limit", 0),
        "tick_grid_refusals": refusals.get("tick_grid", 0),
        "round_lot_refusals": refusals.get("round_lot", 0),
        "insufficient_cash_refusals": refusals.get("insufficient_cash", 0),
        "unsettled_holding_refusals": refusals.get("unsettled_holding", 0),
        "indeterminate_at_submit": dict(sorted(indeterminate_submits.items())),
        "t2_locked_rebuys": t2_locked_rebuys,
        "t2_unsettled_sells": t2_unsettled_sells,
        "insufficient_cash_not_t2": cash_short_other,
        "band_edge_evaluations": observed.band_edge_evaluations,
        "band_lock_no_fills": observed.band_lock_no_fills,
        "fill_evaluations": dict(sorted(observed.outcomes.items())),
        "fill_evidence": dict(sorted(observed.evidence.items())),
        "session_events": dict(sorted(events.items())),
        "indeterminate_report": _plain(ign),
    }
    return res, tier1


def _plain(obj):
    """Best-effort JSON-safe view of an engine report."""
    for attr in ("to_dict", "as_dict"):
        if hasattr(obj, attr):
            try:
                return json.loads(json.dumps(getattr(obj, attr)(), default=str))
            except Exception:   # noqa: BLE001 - reporting only
                pass
    if hasattr(obj, "__dataclass_fields__"):
        return {f: _plain(getattr(obj, f)) for f in obj.__dataclass_fields__}
    if isinstance(obj, dict):
        return {str(getattr(k, "value", k)): _plain(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_plain(v) for v in obj]
    if isinstance(obj, (int, float, str, bool)) or obj is None:
        return obj
    return str(getattr(obj, "value", obj))


def engine_commit() -> str:
    try:
        sha = subprocess.run(["git", "-C", str(ENGINE_ROOT), "rev-parse", "HEAD"],
                             capture_output=True, text=True, check=True).stdout.strip()
        dirty = subprocess.run(["git", "-C", str(ENGINE_ROOT), "status",
                                "--porcelain", "--untracked-files=no"],
                               capture_output=True, text=True).stdout.strip()
        return sha + ("-dirty" if dirty else "")
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def run_window(window: str, params: Optional[dict] = None, *,
               spread: bool = True, advance_variant: bool = True) -> dict:
    params = params or D.load_params()
    tape = D.load_tape(window, params)
    naive = run_naive(window, params, tape=tape)
    faithful, tier1 = run_faithful(window, params, tape=tape)
    n, f = naive.as_dict(), faithful.as_dict()
    out = {
        "window": window,
        "period": params["windows"][window],
        "tickers": params["tickers"],
        "plutus_simulator_commit": engine_commit(),
        "naive": n,
        "faithful": f,
        "tier1": tier1,
        "gap": {
            "fill_ratio_f_over_n": round(f["fills"] / n["fills"], 4)
            if n["fills"] else None,
            "hpr_naive": n["hpr"], "hpr_faithful": f["hpr"],
            "hpr_delta": round(f["hpr"] - n["hpr"], 6),
        },
    }
    if advance_variant:
        adv, adv_t1 = run_faithful(window, params, tape=tape, advance_sale=True)
        out["sale_advance_on"] = {
            "fills": adv.fills,
            "insufficient_cash_refusals": adv_t1["insufficient_cash_refusals"],
            "unsettled_holding_refusals": adv_t1["unsettled_holding_refusals"],
        }
    if spread:
        out["policy_spread"] = {}
        for pol in ("hard", "probabilistic"):
            r, t1 = run_faithful(window, params, tape=tape, policy=pol)
            ev = t1["fill_evaluations"]
            tot = sum(ev.values())
            out["policy_spread"][pol] = {
                "fills": r.fills, "evaluations": ev,
                "indeterminate_rate": round(ev.get("indeterminate", 0) / tot, 4)
                if tot else None}
        ev = tier1["fill_evaluations"]
        tot = sum(ev.values())
        out["policy_spread"]["soft"] = {
            "fills": faithful.fills, "evaluations": ev,
            "indeterminate_rate": round(ev.get("indeterminate", 0) / tot, 4)
            if tot else None}
    return out


def main(argv: Optional[List[str]] = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--window", action="append",
                    help="window id from parameter/backtesting_parameter.json "
                         "(default: all)")
    ap.add_argument("--no-spread", action="store_true",
                    help="skip the hard/probabilistic fill-policy runs")
    args = ap.parse_args(argv)
    params = D.load_params()
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    for w in args.window or list(params["windows"]):
        out = run_window(w, params, spread=not args.no_spread)
        path = RESULT_DIR / f"{w}.json"
        path.write_text(json.dumps(out, indent=2, sort_keys=False) + "\n",
                        encoding="utf-8")
        g = out["gap"]
        print(f"{w}: fills naive {out['naive']['fills']} -> faithful "
              f"{out['faithful']['fills']} (f/n {g['fill_ratio_f_over_n']}); "
              f"HPR {g['hpr_naive']:.4%} -> {g['hpr_faithful']:.4%}  -> {path}")


if __name__ == "__main__":
    main()
