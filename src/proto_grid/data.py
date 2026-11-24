"""Read the shipped frozen slices. No plutus import: both arms use this.

Layout (prices in thousands of dong, as extracted):

* ``data/tick/<window>/quote_matched.parquet`` -- the trade tape
  (``datetime, tickersymbol, price``);
* ``data/tick/<window>/quote_{ask,bid}price.parquet`` -- book prices, depth 1-3
  (read only by the faithful arm, through the engine's ``TickSource``);
* ``data/band/<window>/quote_{close,ceil,floor,reference,ticker}.parquet`` --
  the daily band source.

Both arms trade the **continuous-session tape only**: prints in
``[09:15, 11:30)`` and ``[13:00, 14:30)``. Auction prints and the end-of-day
row the tick tables carry stamped ``00:00:00`` are excluded.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Dict, List, Tuple

import duckdb

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_ROOT = REPO_ROOT / "data"
PARAMS_PATH = REPO_ROOT / "parameter" / "backtesting_parameter.json"


def load_params() -> dict:
    return json.loads(PARAMS_PATH.read_text(encoding="utf-8"))


def tick_dir(window: str) -> Path:
    return DATA_ROOT / "tick" / window


def band_dir(window: str) -> Path:
    return DATA_ROOT / "band" / window


def price(text) -> Decimal:
    """A quoted price as an exact Decimal on the 10-dong (0.01) lattice."""
    return Decimal(str(text)).quantize(Decimal("0.01"))


@dataclass(frozen=True)
class Tick:
    ts: datetime
    ticker: str
    price: Decimal


def _windows(params: dict) -> List[Tuple[time, time]]:
    return [(time.fromisoformat(a), time.fromisoformat(b))
            for a, b in params["continuous_windows"]]


def in_continuous(ts: datetime, windows: List[Tuple[time, time]]) -> bool:
    t = ts.time()
    return any(a <= t < b for a, b in windows)


def load_tape(window: str, params: dict) -> List[Tick]:
    """The merged continuous-session tape of every ticker, in time order.

    Ties on timestamp are broken by ticker then by the file's row order, so the
    stream is deterministic.
    """
    spec = params["windows"][window]
    path = tick_dir(window) / "quote_matched.parquet"
    end_excl = date.fromisoformat(spec["end"]) + timedelta(days=1)
    rows = duckdb.connect().execute(
        "SELECT datetime, tickersymbol, CAST(price AS VARCHAR) "
        f"FROM read_parquet('{path}') "
        "WHERE list_contains(?, tickersymbol) "
        "AND datetime >= ? AND datetime < ? "
        "AND CAST(datetime AS TIME) <> TIME '00:00:00' "
        "ORDER BY datetime, tickersymbol",
        [params["tickers"], spec["start"], end_excl.isoformat()]).fetchall()
    wins = _windows(params)
    return [Tick(ts, t, price(p)) for ts, t, p in rows
            if in_continuous(ts, wins)]


def load_reference(window: str) -> Dict[Tuple[str, date], Decimal]:
    """The published reference price per (ticker, day)."""
    path = band_dir(window) / "quote_reference.parquet"
    rows = duckdb.connect().execute(
        "SELECT tickersymbol, datetime, CAST(price AS VARCHAR) "
        f"FROM read_parquet('{path}')").fetchall()
    return {(t, d): price(p) for t, d, p in rows}


def month_anchors(window: str, params: dict, days: List[date]
                  ) -> Dict[Tuple[str, Tuple[int, int]], Decimal]:
    """Each (ticker, month) -> the reference price of the month's first session.

    The first session is the first day of the month on which that ticker has a
    published reference inside the window.
    """
    ref = load_reference(window)
    out: Dict[Tuple[str, Tuple[int, int]], Decimal] = {}
    for t in params["tickers"]:
        for d in sorted(days):
            key = (t, (d.year, d.month))
            if key not in out and (t, d) in ref:
                out[key] = ref[(t, d)]
    return out


def trading_days(tape: List[Tick]) -> List[date]:
    return sorted({k.ts.date() for k in tape})
