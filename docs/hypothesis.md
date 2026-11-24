# Hypothesis and pre-registered assumptions

## Thesis

Liquid VN30 equities oscillate enough, day to day, that a cost-aware
buy-low/sell-high limit grid can harvest the chop after fees and sell tax.

## Role in the paper

ProtoGrid is an **execution-fidelity demonstrator**. The finding is the gap
between the naive backtest and the faithful Plutus market on the same signals,
and which market rules produce it. P&L is secondary.

The original design (2026-09-14) set a kill criterion on a 2.5-year in-sample
run: net Sharpe > 0, net HPR > 0 and at least 300 completed round trips. The
camera-ready rebuild runs two short windows chosen to contain the execution
effects (see the README). They are far too short to test an alpha claim, so the
kill criterion is **not assessed** here. That is stated, not waived: nothing in
this repo claims the grid is profitable.

## Assumed costs (fixed before any run)

The naive developer's static estimate, which sets the grid spacing and is what
the naive arm charges:

| Item | Rate |
|---|---|
| Broker commission, per side | 0.15% |
| Sell tax (PIT on securities transfer) | 0.10% |
| **Round trip** | **0.40%** |

Spacing `delta` = the smallest whole number of tick steps at the month's anchor
that is at least 3 x the round-trip cost (so 1.2% of the anchor, rounded up to
the tick). The faithful arm trades the same `delta` and pays the engine's dated
statutory charges plus a 0.15% commission.
