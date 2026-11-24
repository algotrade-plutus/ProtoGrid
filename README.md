# ProtoGrid

A cost-aware, paired buy-low/sell-high limit grid on three liquid HOSE names. It
runs the same signals through two backends: a naive backtester and the faithful
Plutus market (`plutus.execution.PlutusBackend`), and measures the gap.

This is the RIVF'26 camera-ready rebuild (branch `rivf26`). It was rebuilt from
the design spec (`plutus-simulator/docs/superpowers/specs/2026-09-14-protogrid-design.md`)
and supersedes the public `algotrade-plutus/ProtoGrid`. No code was carried over
from that repo.

## Hypothesis

Liquid VN30 equities oscillate enough that a grid harvests the chop after costs.
In the paper, ProtoGrid demonstrates **execution fidelity**: the finding is the
naive-to-faithful gap and the rules that cause it, not alpha. See
[`docs/hypothesis.md`](docs/hypothesis.md). It also records the pre-registered
assumed costs, and it explains why the old kill criterion is not assessed on
these short windows.

## The strategy (`src/proto_grid/strategy.py`, pure, no plutus import)

- **Names and capital:** SSI, TCH, POW, with 2,000,000,000đ split evenly across
  3 grids. Each grid has 8 buy slots.
- **Anchor:** each calendar month, the grid re-anchors to that month's open
  reference price (the reference on the month's first session).
- **Spacing Δ:** the smallest whole number of HOSE tick steps at the anchor
  that is at least 3 × the assumed round-trip cost (0.4%). Δ is fixed for the
  month and shared by both arms.
- **Ladder:** slot *k* buys at `anchor − kΔ`. A filled buy arms a paired sell
  at `fill + Δ`. A filled sell frees the slot, which then re-buys at the
  current month's price for that slot. The grid starts flat once. A re-anchor
  re-prices only the free slots: held inventory and its sell persist.
- **Sizing:** each slot buys `capital_per_grid / 8` of notional, floored to a
  100-share lot at the slot's price.

## The two arms

| | naive (`backtest.py`) | faithful (`experiments/grid_anchor.py`) |
|---|---|---|
| Tape | continuous-session prints, 09:15–11:30 and 13:00–14:30 | the same prints, through the engine's `TickSource` |
| Fill rule | a rung fills in full at its price on the first print at or through it | `soft` policy (uncapped): the same rule, decided by the session |
| Price band | none | `BAND_LIMIT` at admission, on the day's published ceiling/floor |
| Tick grid / lot | none | dated `TICK_GRID` and `ROUND_LOT` at admission |
| Band lock | none | tick book-tier `band_lock_decision` (resting ask/bid ladder, `TICK_BOOK`) |
| Settlement | instant cash and shares | T+2 for cash and shares, sale advance **off** |
| Costs | static 0.15% buy, 0.25% sell | dated statutory charges (0.1% sell PIT, …) + 0.15% commission |

Orders are day orders. Each morning the faithful driver submits a ticker's
resting grid at that ticker's first continuous print. It then advances the
session clock to **every** continuous print of the three names, in time order.
A refused order is retried at the next session's open. A fill's follow-up
order is submitted at the fill's instant. The faithful equity is settled cash
plus pending sale proceeds plus holdings marked at the last print.

## Units

The data quotes prices in **thousands of đồng**, and so do the engine and
`strategy.py` (`24.30` is 24,300đ). All cash, capital, notional, costs and
equity are in **real đồng**: notional is `price × 1000 × shares`
(`strategy.PRICE_SCALE`). The engine applies the same ×1000 to cash-venue
prices internally.

## Data and windows (why each one is the minimum)

Both windows come from the Algotrade DB (`--source db`). Book sizes are not
needed (`TickSource` reads book prices only), so the archive is not used.

| Window | Dates | Sessions | Why |
|---|---|---:|---|
| `w2022_10` | 2022-10-03 → 2022-11-30 | 43 | 2022 sell-off and rebound. Every name has lock days: close at floor SSI 7 / TCH 9 / POW 4, close at ceiling 4 / 7 / 1. TCH and POW cross the 10,000đ tick tier. |
| `w2021_11` | 2021-11-01 → 2021-12-31 | 45 | Late-2021 rally, the other regime. Close at ceiling SSI 2 / TCH 10 / POW 5, close at floor 0 / 3 / 1. SSI crosses the 50,000đ tier. |

Each window is two calendar months. That is the shortest span with one monthly
re-anchor, which is the grid's own clock, so carried inventory crosses a
re-anchor. No warm-up is needed: the anchor is the month's first reference
price. Both windows contain band-lock days for all three names and T+2
recycling (see Tier-1). Neither contains an exchange holiday, so the engine's
default weekday settlement calendar is exact for every fill. (Tet 2022 and
2022-01-03 are deliberately outside.) The old in-sample window,
2021-02-17 → 2023-08-31, was 637 sessions.

Layout: `data/tick/<window>/quote_{matched,askprice,bidprice}.parquet` and
`data/band/<window>/quote_{close,ceil,floor,reference,ticker}.parquet`.
Manifests are in **[`data/manifest/<window>/DATA-MANIFEST.md`](data/manifest/)**,
with the source table, query, tickers, dates, fields, rows, bytes, sha256 and
the minimality note. The `request.json` beside each manifest replays the
extraction byte for byte. The `.parquet` tick files are converted to the CSV
that `TickSource` reads, in the git-ignored `data/.cache/`. Total size is
1.17 MiB + 1.62 MiB.

## Results

`result/grid_anchor/<window>.json` holds the `naive`, `faithful` and `tier1`
blocks, a `gap` summary, a sale-advance-on variant, the soft/hard/probabilistic
policy spread and the `plutus-simulator` commit the run used.

| Window | fills n → f | f/n | HPR n → f |
|---|---|---:|---|
| `w2022_10` | 136 → 62 | 45.6% | −2.40% → −2.65% |
| `w2021_11` | 124 → 57 | 46.0% | +1.47% → +1.18% |

Tier-1 (faithful, `soft`):

| Window | BAND_LIMIT (buy/sell) | TICK_GRID | INSUFFICIENT_CASH (T+2-locked) | UNSETTLED_HOLDING | band-lock no-fills |
|---|---|---:|---|---:|---:|
| `w2022_10` | 828 (71 / 757) | 0 | 28 (28) | 58 | 0 (1 band-edge evaluation) |
| `w2021_11` | 784 (706 / 78) | 0 | 3 (3) | 68 | 0 (0) |

Notes on these numbers:

- **The gap is T+2.** A band refusal only refuses a price that the day's
  trading cannot reach anyway, so it costs no fills by itself. What costs
  fills is settlement. The naive arm sells a lot the same day it buys it, and
  re-buys on proceeds that the faithful arm will not hold for two days.
- **TICK_GRID is 0 by construction.** Δ is a whole number of ticks at the
  anchor, and every rung and paired sell sits at or below the anchor. A
  coarser tier's multiples always lie on every finer tier's grid, so the
  ladder never leaves the dated grid. The old run's 2,409 tick refusals cannot
  come from this construction (its code is lost).
- **Band-lock no-fills are 0.** A limit is a band-lock question only when it
  sits at or past the edge (a buy at the ceiling, a sell at the floor). A
  buy-low ladder almost never places one.
- **The policy spread** at tick resolution: `hard` and `probabilistic` fill
  nothing and are 99–100% INDETERMINATE. A synthesised tick interval carries no
  volume or OHLC, so they cannot size a fill. That is the honest outcome, not
  a bug.
- **Sale advance on:** INSUFFICIENT_CASH drops to 0. Fills move 62 → 58 and
  57 → 61, a path effect.

## Regenerate

```bash
# plutus-simulator checkout on branch rivf26 at ../../plutus-simulator
python3 -m venv .venv
.venv/bin/pip install -e ../../plutus-simulator pytest
.venv/bin/pip install -e . --no-deps
.venv/bin/python -m pytest -q          # strategy unit tests, naive regression pin, faithful smoke
.venv/bin/pg-backtest                  # naive arm only, both windows
.venv/bin/pg-anchor                    # naive vs faithful -> result/grid_anchor/<window>.json (~6 min)
```

To re-extract a slice (needs DB access, run from plutus-simulator), replay its
`request.json` with
`scripts/rivf26_extract.py declared --source db --experiment <name> --request data/manifest/<window>/request.json`.
The `.plutus/manifest.yaml` lists the steps and artifacts.
