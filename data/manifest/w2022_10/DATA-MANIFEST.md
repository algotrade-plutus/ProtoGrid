# DATA-MANIFEST: grid-2022-10

- **Reproduces:** ProtoGrid result/grid_anchor/w2022_10.json (2022-10-03..2022-11-30): naive vs faithful fills, HPR and Tier-1 counters
- **Extraction mode:** `declared`
- **Command:** `rivf26_extract.py declared --force --source db --experiment grid-2022-10 --reproduces ProtoGrid result/grid_anchor/w2022_10.json (2022-10-03..2022-11-30): naive vs faithful fills, HPR and Tier-1 counters --files quote_matched,quote_askprice,quote_bidprice,quote_close,quote_ceil,quote_floor,quote_reference --tickers SSI,TCH,POW --start 2022-10-01 --end 2022-12-01 --max-depth 3`
- **Source:** Algotrade PostgreSQL DB, schema `quote` (read-only transaction). File `<prefix>_<x>.<ext>` holds rows of DB table `quote.<x>`.
- **Extracted on:** 2026-11-24 with `scripts/rivf26_extract.py` (pyarrow 26.0.1; writer settings fixed in `WRITER`).
- **Total size:** 1,223,413 bytes (1.17 MiB) in 8 files.

## Why this window is minimal

Tickers: the three grid names only (SSI, TCH, POW, the old run's names). Fields: the trade tape (`matched`) and book prices depth 1-3 (`askprice`/`bidprice`), which the engine's `TickSource` reads; the daily `ceil`/`floor`/`reference` (band and monthly anchor), `close` (the table `DataHubSource` drives its band query from; its values are not used) and the ticker master (venue and lot). No sizes, no daily volume: neither arm reads them. Dates: two calendar months, the shortest span that holds one monthly re-anchor (the grid's own clock), so inventory carried across a re-anchor is exercised; no warm-up is needed because the anchor is the month's first reference price. This window (2022-10-03 to 2022-11-30, 43 sessions) is the 2022 sell-off and rebound: close-at-floor days SSI 7, TCH 9, POW 4 and close-at-ceiling days SSI 4, TCH 7, POW 1, so every name has band-lock days and the sliding band crosses the fixed ladder (BAND_LIMIT) in both directions; enough chop for T+2 recycling (58 sells blocked as unsettled, 28 re-buys blocked on unsettled cash in the faithful run). TCH and POW cross the 10,000d tick tier. No holiday falls inside, so the default weekday settlement calendar is exact.

## Files

| File | Rows | Bytes | sha256 |
|---|---:|---:|---|
| `quote_askprice.parquet` | 95,432 | 318,594 | `896a68a9d6d05b955ff81ddb5eda23084f1fbc0840afb3ceca129702eb155ebd` |
| `quote_bidprice.parquet` | 102,882 | 335,409 | `8ee06528adc6103882bdca6aed410c8ef9f28f4e4b8b790cf265ed6aa90087b3` |
| `quote_ceil.parquet` | 129 | 1,731 | `a24c4c35918f7f0f8de55378a4c7f7d780cadae4ad4cd771a642004f66e36c36` |
| `quote_close.parquet` | 129 | 1,746 | `60fa58de81712f755563f9ce782f248bb13c23ade6c9ca81f65bbcc9d6f2abff` |
| `quote_floor.parquet` | 129 | 1,752 | `f395e01126969f55afa35f51171ad3693bacb107ca065ff8e5c989dc7036e943` |
| `quote_matched.parquet` | 90,875 | 560,691 | `7fc3c5954d31125eba71b19c1f66a721d1924447805c6be7def8e42dee886c5d` |
| `quote_reference.parquet` | 129 | 1,746 | `60dd1b3de79ec4946c54312948c2c9364767525bd056f4214922f7cbd829db9d` |
| `quote_ticker.parquet` | 3 | 1,744 | `91988e24bb471d82b44eb97db3a15c6774662ee1458f2dd1fc9ec8996a941e45` |

## Contents (tickers, ranges, fields, query)

### `quote_askprice.parquet`
- Fields: `datetime, tickersymbol, price, depth`
- Query: `quote.askprice WHERE tickersymbol = <t> AND datetime >= <lo> AND datetime < <hi> AND depth BETWEEN 1 AND 3`, once per (ticker, interval) below
- `POW`: [2022-10-01, 2022-12-01)
- `SSI`: [2022-10-01, 2022-12-01)
- `TCH`: [2022-10-01, 2022-12-01)

### `quote_bidprice.parquet`
- Fields: `datetime, tickersymbol, price, depth`
- Query: `quote.bidprice WHERE tickersymbol = <t> AND datetime >= <lo> AND datetime < <hi> AND depth BETWEEN 1 AND 3`, once per (ticker, interval) below
- `POW`: [2022-10-01, 2022-12-01)
- `SSI`: [2022-10-01, 2022-12-01)
- `TCH`: [2022-10-01, 2022-12-01)

### `quote_ceil.parquet`
- Fields: `datetime, tickersymbol, price`
- Query: `quote.ceil WHERE tickersymbol = <t> AND datetime >= <lo> AND datetime < <hi>`, once per (ticker, interval) below
- `POW`: [2022-10-01, 2022-12-01)
- `SSI`: [2022-10-01, 2022-12-01)
- `TCH`: [2022-10-01, 2022-12-01)

### `quote_close.parquet`
- Fields: `datetime, tickersymbol, price`
- Query: `quote.close WHERE tickersymbol = <t> AND datetime >= <lo> AND datetime < <hi>`, once per (ticker, interval) below
- `POW`: [2022-10-01, 2022-12-01)
- `SSI`: [2022-10-01, 2022-12-01)
- `TCH`: [2022-10-01, 2022-12-01)

### `quote_floor.parquet`
- Fields: `datetime, tickersymbol, price`
- Query: `quote.floor WHERE tickersymbol = <t> AND datetime >= <lo> AND datetime < <hi>`, once per (ticker, interval) below
- `POW`: [2022-10-01, 2022-12-01)
- `SSI`: [2022-10-01, 2022-12-01)
- `TCH`: [2022-10-01, 2022-12-01)

### `quote_matched.parquet`
- Fields: `datetime, tickersymbol, price`
- Query: `quote.matched WHERE tickersymbol = <t> AND datetime >= <lo> AND datetime < <hi>`, once per (ticker, interval) below
- `POW`: [2022-10-01, 2022-12-01)
- `SSI`: [2022-10-01, 2022-12-01)
- `TCH`: [2022-10-01, 2022-12-01)

### `quote_reference.parquet`
- Fields: `datetime, tickersymbol, price`
- Query: `quote.reference WHERE tickersymbol = <t> AND datetime >= <lo> AND datetime < <hi>`, once per (ticker, interval) below
- `POW`: [2022-10-01, 2022-12-01)
- `SSI`: [2022-10-01, 2022-12-01)
- `TCH`: [2022-10-01, 2022-12-01)

### `quote_ticker.parquet`
- Fields: `tickersymbol, exchangeid, lastupdated, instrumenttype, startdate, expdate`
- Query: `quote.ticker WHERE tickersymbol = ANY(<tickers>)`
- `POW`: ticker-master row
- `SSI`: ticker-master row
- `TCH`: ticker-master row
