"""Unit tests for the pure grid signal (no data, no plutus)."""
from decimal import Decimal

from proto_grid.strategy import (PairedGrid, buy_rungs, grid_step, hose_tick,
                                 lot_quantity)


def test_hose_tick_tiers_are_inclusive_below():
    assert hose_tick(Decimal("9.99")) == Decimal("0.01")
    assert hose_tick(Decimal("10.00")) == Decimal("0.05")
    assert hose_tick(Decimal("49.95")) == Decimal("0.05")
    assert hose_tick(Decimal("50.00")) == Decimal("0.1")


def test_grid_step_clears_three_times_assumed_cost_on_whole_ticks():
    # 24.2 * 0.004 * 3 = 0.2904 -> ceil to 0.05 ticks -> 0.30
    d = grid_step(Decimal("24.2"), Decimal("0.004"))
    assert d == Decimal("0.30")
    # 55.9 * 0.012 = 0.6708 -> ceil to 0.1 ticks -> 0.7
    assert grid_step(Decimal("55.9"), Decimal("0.004")) == Decimal("0.7")
    # 8.0 * 0.012 = 0.096 -> ceil to 0.01 ticks -> 0.10
    assert grid_step(Decimal("8.00"), Decimal("0.004")) == Decimal("0.10")


def test_buy_rungs_below_anchor_evenly_spaced():
    assert buy_rungs(Decimal("24.2"), Decimal("0.30"), 3) == [
        Decimal("23.90"), Decimal("23.60"), Decimal("23.30")]


def test_lot_quantity_floors_to_100_shares():
    # 83,333,333d at 23.90 (23,900d) -> 3,486.7 shares -> 3,400
    assert lot_quantity(Decimal("83333333"), Decimal("23.90")) == 3400


def _grid():
    g = PairedGrid("XYZ", Decimal("800000000"), n_rungs=8)
    g.reanchor(Decimal("20.00"))      # delta = ceil(0.24/0.05)*0.05 = 0.25
    return g


def test_flat_start_wants_eight_buys():
    g = _grid()
    its = g.intents()
    assert [i.side for i in its] == ["buy"] * 8
    assert its[0].price == Decimal("19.75") and its[-1].price == Decimal("18.00")


def test_buy_fill_arms_paired_sell_one_step_up_and_sell_frees_slot():
    g = _grid()
    q = g.intent_for(2).quantity
    g.on_fill(2, "buy", Decimal("19.50"), q)
    sell = g.intent_for(2)
    assert sell.side == "sell" and sell.price == Decimal("19.75")
    assert sell.quantity == q
    g.on_fill(2, "sell", Decimal("19.75"), q)
    assert g.round_trips == 1
    rebuy = g.intent_for(2)
    assert rebuy.side == "buy" and rebuy.price == Decimal("19.50")


def test_reanchor_reprices_free_slots_only():
    g = _grid()
    q = g.intent_for(1).quantity
    g.on_fill(1, "buy", Decimal("19.75"), q)
    g.reanchor(Decimal("15.00"))      # delta = ceil(0.18/0.05)*0.05 = 0.20
    held = g.intent_for(1)
    assert held.side == "sell" and held.price == Decimal("20.00")
    assert g.intent_for(2).price == Decimal("14.60")
