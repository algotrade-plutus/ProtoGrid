"""The faithful arm runs through PlutusBackend on the shipped slice.

A short sub-window (the first two weeks of the 2022 window) keeps this fast. It
checks the arm runs end to end and that the grid's own mechanisms reach the
Tier-1 counters, not any particular number.
"""
import copy

from proto_grid import data as D
from proto_grid.backtest import run_naive
from proto_grid.experiments.grid_anchor import run_faithful


def _params():
    p = copy.deepcopy(D.load_params())
    p["windows"]["w2022_10"] = {"start": "2022-10-03", "end": "2022-10-14"}
    return p


def test_faithful_arm_runs_and_is_bounded_by_naive():
    p = _params()
    tape = D.load_tape("w2022_10", p)
    naive = run_naive("w2022_10", p, tape=tape)
    faithful, tier1 = run_faithful("w2022_10", p, tape=tape)

    assert faithful.equity and len(faithful.equity) == len(naive.equity)
    assert 0 < faithful.fills <= naive.fills
    # admission (band) and settlement (T+2) both fire inside two weeks
    assert tier1["band_limit_refusals"] > 0
    assert tier1["t2_unsettled_sells"] + tier1["t2_locked_rebuys"] > 0
    # soft decides every evaluation: no INDETERMINATE at tick resolution
    assert tier1["fill_evaluations"].get("indeterminate", 0) == 0
