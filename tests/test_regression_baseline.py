"""Pins the naive arm on the shipped slices (the behaviour-preserving anchor).

If one of these moves, either the naive engine, the strategy or the slice
changed. Re-pin only on purpose, and say why in the commit.
"""
import pytest

from proto_grid import data as D
from proto_grid.backtest import run_naive

EXPECTED = {
    "w2022_10": dict(fills=136, buy_fills=75, sell_fills=61, round_trips=61,
                     final_equity_vnd=1952005245, hpr=-0.023997,
                     fills_by_ticker={"POW": 36, "SSI": 46, "TCH": 54}),
    "w2021_11": dict(fills=124, buy_fills=65, sell_fills=59, round_trips=59,
                     final_equity_vnd=2029449610, hpr=0.014725,
                     fills_by_ticker={"SSI": 70, "TCH": 54}),
}


@pytest.mark.parametrize("window", sorted(EXPECTED))
def test_naive_arm_reproduces_baseline(window):
    got = run_naive(window, D.load_params()).as_dict()
    for key, want in EXPECTED[window].items():
        assert got[key] == want, (window, key, got[key], want)
