"""The grid signal: a cost-aware, paired buy-low/sell-high ladder.

**Pure.** No plutus import, no I/O, no clock. Both arms (the naive engine in
``backtest.py`` and the faithful runner in ``experiments/grid_anchor.py``)
drive the same :class:`PairedGrid`; only the execution backend differs.

Prices here are in **thousands of dong**, as the exchange and the data quote
them (``24.30`` is 24,300 VND). Cash and notional are in **dong**.

The mechanic (design 2026-09-14, section 3):

* **Anchor.** Each calendar month the ladder re-anchors to that month's open
  reference price (the reference price of the month's first session).
* **Spacing.** ``delta`` is the smallest whole number of tick steps, at the
  anchor price, that is at least ``margin`` times the *assumed* round-trip cost
  (0.4% of the anchor). It is fixed for the month and shared by both arms.
* **Ladder.** ``n_rungs`` buy slots below the anchor, slot ``k`` at
  ``anchor - k * delta``. A filled buy in slot ``k`` arms a sell one step up
  (``fill + delta``). A filled sell frees the slot, which then re-buys at the
  current month's slot-``k`` price.
* **Continuous.** Start flat once. A re-anchor re-prices only *free* slots;
  held inventory and its paired sell persist at their original levels.
* **Sizing.** Per-slot buy notional is ``capital_per_grid / n_rungs``, floored
  to a 100-share lot at the slot's buy price, so every slot is fundable.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import ROUND_CEILING, Decimal
from typing import Callable, Dict, List, Optional

#: Thousands of dong per quoted price unit.
PRICE_SCALE = 1000
LOT = 100


def hose_tick(price: Decimal) -> Decimal:
    """The HOSE matched-order tick for a stock at ``price`` (thousand VND).

    Three tiers, unchanged across both windows: below 10,000d -> 10d;
    10,000-49,950d -> 50d; 50,000d and above -> 100d. This is the developer's
    static table; the faithful arm judges every price on the engine's *dated*
    grid instead.
    """
    if price < Decimal("10"):
        return Decimal("0.01")
    if price < Decimal("50"):
        return Decimal("0.05")
    return Decimal("0.1")


def grid_step(anchor: Decimal, assumed_cost_rate: Decimal,
              tick_fn: Callable[[Decimal], Decimal] = hose_tick,
              margin: int = 3) -> Decimal:
    """Smallest whole-tick step at the anchor that is >= margin x the cost.

    ``cost = anchor * assumed_cost_rate`` (price points per round trip), so a
    completed pair nets at least ``(margin - 1) x`` the assumed cost.
    """
    raw = anchor * assumed_cost_rate * Decimal(margin)
    tick = tick_fn(anchor)
    steps = (raw / tick).to_integral_value(rounding=ROUND_CEILING)
    return max(steps, Decimal(1)) * tick


def buy_rungs(anchor: Decimal, delta: Decimal, n: int) -> List[Decimal]:
    """``n`` buy prices below the anchor: ``anchor - delta ... anchor - n*delta``."""
    return [anchor - delta * Decimal(k) for k in range(1, n + 1)]


def lot_quantity(notional_vnd: Decimal, price: Decimal) -> int:
    """Shares buyable for ``notional_vnd`` at ``price``, floored to a lot."""
    if price <= 0:
        return 0
    shares = int(notional_vnd / (price * PRICE_SCALE))
    return (shares // LOT) * LOT


@dataclass(frozen=True)
class Intent:
    """One resting order the grid wants live: a slot's buy or its paired sell."""

    ticker: str
    slot: int
    side: str            # "buy" or "sell"
    price: Decimal       # thousand VND
    quantity: int


@dataclass
class Slot:
    k: int
    buy_price: Optional[Decimal] = None
    quantity: int = 0               # shares held (0 = free)
    sell_price: Optional[Decimal] = None
    bought_at: Optional[Decimal] = None

    @property
    def holding(self) -> bool:
        return self.quantity > 0


@dataclass
class PairedGrid:
    """One ticker's continuous paired grid."""

    ticker: str
    capital: Decimal                     # dong allotted to this grid
    n_rungs: int = 8
    assumed_cost_rate: Decimal = Decimal("0.004")
    margin: int = 3
    tick_fn: Callable[[Decimal], Decimal] = hose_tick
    anchor: Optional[Decimal] = None
    delta: Optional[Decimal] = None
    slots: List[Slot] = field(default_factory=list)
    round_trips: int = 0

    def __post_init__(self) -> None:
        if not self.slots:
            self.slots = [Slot(k) for k in range(1, self.n_rungs + 1)]

    @property
    def per_slot_notional(self) -> Decimal:
        return self.capital / Decimal(self.n_rungs)

    def reanchor(self, anchor: Decimal) -> None:
        """Re-price the free slots around a new month-open anchor."""
        self.anchor = anchor
        self.delta = grid_step(anchor, self.assumed_cost_rate, self.tick_fn,
                               self.margin)
        prices = buy_rungs(anchor, self.delta, self.n_rungs)
        for slot, price in zip(self.slots, prices):
            slot.buy_price = price

    def intents(self) -> List[Intent]:
        """Every order the grid wants resting now, buys then sells."""
        out: List[Intent] = []
        if self.anchor is None:
            return out
        for s in self.slots:
            if s.holding:
                out.append(Intent(self.ticker, s.k, "sell", s.sell_price,
                                  s.quantity))
            else:
                qty = lot_quantity(self.per_slot_notional, s.buy_price)
                if qty > 0 and s.buy_price > 0:
                    out.append(Intent(self.ticker, s.k, "buy", s.buy_price, qty))
        return out

    def intent_for(self, k: int) -> Optional[Intent]:
        """The single order slot ``k`` wants now (after a fill changed it)."""
        for it in self.intents():
            if it.slot == k:
                return it
        return None

    def on_fill(self, k: int, side: str, price: Decimal, quantity: int) -> None:
        """Apply a fill to slot ``k``. Partial fills accumulate."""
        s = self.slots[k - 1]
        if side == "buy":
            s.quantity += quantity
            s.bought_at = price
            # paired sell one step up from the slot's buy price
            s.sell_price = price + self.delta_for(s)
        else:
            s.quantity -= quantity
            if s.quantity <= 0:
                s.quantity = 0
                s.sell_price = None
                s.bought_at = None
                self.round_trips += 1

    def delta_for(self, s: Slot) -> Decimal:
        # The step in force when the slot's buy was priced (this month's).
        return self.delta
