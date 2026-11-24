"""The faithful arm's market data: the engine's own ``TickSource``, unmodified.

Two thin, behaviour-preserving layers around it, both local to this repo:

1. **CSV materialisation.** ``plutus.market.adapters.tick.TickSource`` reads
   ``quote_{matched,askprice,bidprice}.csv``. The slice ships as zstd parquet
   (about 10x smaller); :func:`materialise_csv` writes the CSV copies the
   adapter needs into a git-ignored cache, row for row.
2. **Per-day caching and the continuous-session filter.** ``TickSource.state_at``
   rebuilds the whole day's states on every call. :class:`DayCachedTickSource`
   builds each (ticker, day) once through ``TickSource.states`` and answers
   ``state_at`` by bisection over that list, so every state it returns is one
   ``TickSource`` built. It keeps only the states the naive arm also trades on:
   continuous-session prints, never the ``00:00:00`` end-of-day row.
"""
from __future__ import annotations

from bisect import bisect_right
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import duckdb

from plutus.market.adapters.datahub import DataHubSource
from plutus.market.adapters.tick import TickSource
from plutus.market.protocol import MarketState

from proto_grid import data as D

TICK_STEMS = ("quote_matched", "quote_askprice", "quote_bidprice")
CACHE_ROOT = D.DATA_ROOT / ".cache"


def materialise_csv(window: str) -> Path:
    """Write the CSV copies of the tick parquet that ``TickSource`` reads."""
    out = CACHE_ROOT / window
    out.mkdir(parents=True, exist_ok=True)
    for stem in TICK_STEMS:
        src = D.tick_dir(window) / f"{stem}.parquet"
        dst = out / f"{stem}.csv"
        if dst.exists() and dst.stat().st_mtime >= src.stat().st_mtime:
            continue
        tmp = dst.with_suffix(".csv.tmp")
        duckdb.connect().execute(
            f"COPY (SELECT * FROM read_parquet('{src}') "
            f"ORDER BY tickersymbol, datetime{', depth' if stem != 'quote_matched' else ''}) "
            f"TO '{tmp}' (HEADER, DELIMITER ',')")
        tmp.replace(dst)
    return out


class DayCachedTickSource:
    """``TickSource`` states, built once per (ticker, day), continuous only."""

    def __init__(self, tick: TickSource, params: dict) -> None:
        self.tick = tick
        self._windows = D._windows(params)
        self._days: Dict[Tuple[str, date], Tuple[List[datetime],
                                                  List[MarketState]]] = {}

    @classmethod
    def for_window(cls, window: str, params: dict) -> "DayCachedTickSource":
        band = DataHubSource.for_root(str(D.band_dir(window)))
        return cls(TickSource(str(materialise_csv(window)), band_source=band),
                   params)

    # -- the MarketDataSource surface the session reads -------------------
    def instrument(self, ticker: str):
        return self.tick.instrument(ticker)

    def states(self, ticker, start, end, **kw):
        return self.tick.states(ticker, start, end, **kw)

    def _day(self, ticker: str, day: date):
        key = (ticker, day)
        if key not in self._days:
            kept = [s for s in self.tick.states(ticker, day,
                                                day + timedelta(days=1))
                    if D.in_continuous(s.ts, self._windows)]
            self._days[key] = ([s.ts for s in kept], kept)
        return self._days[key]

    def state_at(self, ticker: str, ts: datetime) -> Optional[MarketState]:
        stamps, states = self._day(ticker, ts.date())
        i = bisect_right(stamps, ts)
        return states[i - 1] if i else None
