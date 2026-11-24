# DATA-MANIFEST: grid-2021-11

- **Reproduces:** ProtoGrid result/grid_anchor/w2021_11.json (2021-11-01..2021-12-31): naive vs faithful fills, HPR and Tier-1 counters
- **Extraction mode:** `declared`
- **Command:** `rivf26_extract.py declared --force --source db --experiment grid-2021-11 --reproduces ProtoGrid result/grid_anchor/w2021_11.json (2021-11-01..2021-12-31): naive vs faithful fills, HPR and Tier-1 counters --files quote_matched,quote_askprice,quote_bidprice,quote_close,quote_ceil,quote_floor,quote_reference --tickers SSI,TCH,POW --start 2021-11-01 --end 2022-01-01 --max-depth 3`
- **Source:** Algotrade PostgreSQL DB, schema `quote` (read-only transaction). File `<prefix>_<x>.<ext>` holds rows of DB table `quote.<x>`.
- **Extracted on:** 2026-11-24 with `scripts/rivf26_extract.py` (pyarrow 26.0.1; writer settings fixed in `WRITER`).
- **Total size:** 1,693,844 bytes (1.62 MiB) in 8 files.

## Why this window is minimal

Tickers: the three grid names only (SSI, TCH, POW, the old run's names). Fields: the trade tape (`matched`) and book prices depth 1-3 (`askprice`/`bidprice`), which the engine's `TickSource` reads; the daily `ceil`/`floor`/`reference` (band and monthly anchor), `close` (the table `DataHubSource` drives its band query from; its values are not used) and the ticker master (venue and lot). No sizes, no daily volume: neither arm reads them. Dates: two calendar months, the shortest span that holds one monthly re-anchor (the grid's own clock), so inventory carried across a re-anchor is exercised; no warm-up is needed because the anchor is the month's first reference price. This window (2021-11-01 to 2021-12-31, 45 sessions) is the late-2021 rally, the complementary regime: close-at-ceiling days SSI 2, TCH 10, POW 5 and close-at-floor days TCH 3, POW 1; SSI crosses the 50,000d tick tier. T+2 recycling: 68 sells blocked as unsettled, 3 re-buys on unsettled cash. It ends before the 2022-01-03 holiday and Tet 2022, so the weekday settlement calendar is exact for every fill inside it.

## Files

| File | Rows | Bytes | sha256 |
|---|---:|---:|---|
| `quote_askprice.parquet` | 117,785 | 346,332 | `03950ae64d38e1a3c611af393e1f68bca7ac71d9c8698601aedb0a77731df414` |
| `quote_bidprice.parquet` | 125,145 | 360,926 | `717c66f7c3a989a55ae9bcbbadcdede234ab9da705d1ff5d51fec824fa1bb01f` |
| `quote_ceil.parquet` | 135 | 1,724 | `93049dc453eeef4604583f812c66b7b2258a2e36bf63a84f3fee143efd96b2f5` |
| `quote_close.parquet` | 135 | 1,733 | `6484d825a78ee030a84761e53a8a43cafeda9f6eb5af5be1e16bb9468f8fc4f3` |
| `quote_floor.parquet` | 135 | 1,719 | `7f3a0ae4d010ea56a75cabed0f8a6cd6b4a41e8b3e6a348373045e4e8186e63a` |
| `quote_matched.parquet` | 180,434 | 977,935 | `94a114ed37ebfe48cd06151485d0987ec0442842f6decbef43863748f308d9f5` |
| `quote_reference.parquet` | 135 | 1,731 | `315f29dca2cccb5d8aecdd8aef8d18be284a2630d7630502ca68c008dc0eb171` |
| `quote_ticker.parquet` | 3 | 1,744 | `91988e24bb471d82b44eb97db3a15c6774662ee1458f2dd1fc9ec8996a941e45` |

## Contents (tickers, ranges, fields, query)

### `quote_askprice.parquet`
- Fields: `datetime, tickersymbol, price, depth`
- Query: `quote.askprice WHERE tickersymbol = <t> AND datetime >= <lo> AND datetime < <hi> AND depth BETWEEN 1 AND 3`, once per (ticker, interval) below
- `POW`: [2021-11-01, 2022-01-01)
- `SSI`: [2021-11-01, 2022-01-01)
- `TCH`: [2021-11-01, 2022-01-01)

### `quote_bidprice.parquet`
- Fields: `datetime, tickersymbol, price, depth`
- Query: `quote.bidprice WHERE tickersymbol = <t> AND datetime >= <lo> AND datetime < <hi> AND depth BETWEEN 1 AND 3`, once per (ticker, interval) below
- `POW`: [2021-11-01, 2022-01-01)
- `SSI`: [2021-11-01, 2022-01-01)
- `TCH`: [2021-11-01, 2022-01-01)

### `quote_ceil.parquet`
- Fields: `datetime, tickersymbol, price`
- Query: `quote.ceil WHERE tickersymbol = <t> AND datetime >= <lo> AND datetime < <hi>`, once per (ticker, interval) below
- `POW`: [2021-11-01, 2022-01-01)
- `SSI`: [2021-11-01, 2022-01-01)
- `TCH`: [2021-11-01, 2022-01-01)

### `quote_close.parquet`
- Fields: `datetime, tickersymbol, price`
- Query: `quote.close WHERE tickersymbol = <t> AND datetime >= <lo> AND datetime < <hi>`, once per (ticker, interval) below
- `POW`: [2021-11-01, 2022-01-01)
- `SSI`: [2021-11-01, 2022-01-01)
- `TCH`: [2021-11-01, 2022-01-01)

### `quote_floor.parquet`
- Fields: `datetime, tickersymbol, price`
- Query: `quote.floor WHERE tickersymbol = <t> AND datetime >= <lo> AND datetime < <hi>`, once per (ticker, interval) below
- `POW`: [2021-11-01, 2022-01-01)
- `SSI`: [2021-11-01, 2022-01-01)
- `TCH`: [2021-11-01, 2022-01-01)

### `quote_matched.parquet`
- Fields: `datetime, tickersymbol, price`
- Query: `quote.matched WHERE tickersymbol = <t> AND datetime >= <lo> AND datetime < <hi>`, once per (ticker, interval) below
- `POW`: [2021-11-01, 2022-01-01)
- `SSI`: [2021-11-01, 2022-01-01)
- `TCH`: [2021-11-01, 2022-01-01)

### `quote_reference.parquet`
- Fields: `datetime, tickersymbol, price`
- Query: `quote.reference WHERE tickersymbol = <t> AND datetime >= <lo> AND datetime < <hi>`, once per (ticker, interval) below
- `POW`: [2021-11-01, 2022-01-01)
- `SSI`: [2021-11-01, 2022-01-01)
- `TCH`: [2021-11-01, 2022-01-01)

### `quote_ticker.parquet`
- Fields: `tickersymbol, exchangeid, lastupdated, instrumenttype, startdate, expdate`
- Query: `quote.ticker WHERE tickersymbol = ANY(<tickers>)`
- `POW`: ticker-master row
- `SSI`: ticker-master row
- `TCH`: ticker-master row
