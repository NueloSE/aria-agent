"""Paper-trading engine — forward simulation with no funds and no chain.

Fidelity choice: the competition scores at MARKET PRICE with SIMULATED costs
(organizers said don't calibrate to live TWAK quotes), so paper fills mirror
that exactly — fill at the latest accumulated price, apply SIM_COST_PCT_PER_LEG.
That makes the paper PnL the most faithful possible preview of the real score.

The paper portfolio has the same PortfolioState shape as the on-chain one, so
the identical safety layer + circuit breaker run on simulated PnL — a 20% paper
drawdown trips the real breaker. State persists in the DB (survives restarts).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from aria import config
from aria.models import Decision, PortfolioState, Position
from aria.state.db import Store

log = logging.getLogger("aria.execution.paper")

STABLE = "USDT"


def _cost(usd: float) -> float:
    return usd * config.SIM_COST_PCT_PER_LEG / 100.0


def ensure_init(store: Store) -> None:
    store.paper_book_init(config.PAPER_START_USD)


def load_state(store: Store) -> PortfolioState:
    """Mark the paper book to market using the latest accumulated prices."""
    ensure_init(store)
    book = store.paper_book()
    assert book is not None
    prices = store.latest_prices()
    prices[STABLE] = 1.0
    for s in config.STABLES:
        prices.setdefault(s, 1.0)

    positions: list[Position] = []
    positions_value = 0.0
    for p in store.paper_positions():
        sym = p["symbol"]
        price = prices.get(sym)
        if price is None:
            # no fresh mark — value at entry (conservative; logged)
            price = p["entry_price_usd"]
            log.warning("paper: no mark for %s, valuing at entry", sym)
        positions_value += p["amount"] * price
        positions.append(Position(
            token_symbol=sym, amount=p["amount"], entry_price_usd=p["entry_price_usd"],
            stop_loss_pct=p["stop_loss_pct"], target_pct=p.get("target_pct"),
            peak_gain_pct=p.get("peak_gain_pct") or 0.0,
            opened_at=datetime.fromisoformat(p["opened_at"]),
        ))

    total = book["stable_usd"] + positions_value
    peak = max(book["peak_value_usd"], total)
    if peak > book["peak_value_usd"]:
        store.paper_book_update(book["stable_usd"], peak)

    return PortfolioState(
        timestamp=datetime.now(timezone.utc),
        total_value_usd=total,
        peak_value_usd=peak,
        positions=positions,
        stable_balance_usd=book["stable_usd"],
        trades_today=store.trades_today_utc(),
    )


def _price_of(store: Store, symbol: str) -> float | None:
    if symbol in config.STABLES or symbol == STABLE:
        return 1.0
    return store.latest_prices().get(symbol)


def simulate(store: Store, decision: Decision, total_value_usd: float):
    """Apply a decision to the paper book. Returns an ExecutionResult-like object.
    Buys spend size_pct of total value from stables; sells/close_all liquidate."""
    from aria.execution import ExecutionResult  # avoid import cycle

    book = store.paper_book()
    assert book is not None
    stable = book["stable_usd"]
    now = datetime.now(timezone.utc).isoformat()

    if decision.action == "buy":
        sym = decision.token_symbol
        price = _price_of(store, sym) if sym else None
        if not sym or not price:
            return ExecutionResult("skipped", f"paper: no price for {sym}")
        usd_in = min(total_value_usd * decision.size_pct / 100.0, stable)
        if usd_in <= 0:
            return ExecutionResult("skipped", "paper: no stable balance for buy")
        net = usd_in - _cost(usd_in)
        amount = net / price
        store.paper_book_update(stable - usd_in, book["peak_value_usd"])
        store.paper_position_set(sym, amount, price, decision.stop_loss_pct, now,
                                 target_pct=decision.target_pct, peak_gain_pct=0.0)
        store.log_trade(decision.cycle_id, "strategy", STABLE, sym, status="confirmed",
                        from_amount=f"{usd_in:.2f}", to_amount=f"{amount:.6f}")
        log.info("PAPER buy %s: $%.2f -> %.6f @ $%.4f (cost $%.3f)",
                 sym, usd_in, amount, price, _cost(usd_in))
        return ExecutionResult("executed", f"${usd_in:.2f} USDT -> {amount:.6f} {sym}")

    if decision.action in ("sell", "close_all"):
        targets = [decision.token_symbol] if decision.action == "sell" else \
            [p["symbol"] for p in store.paper_positions()]
        targets = [t for t in targets if t]
        if not targets:
            return ExecutionResult("skipped", "paper: no positions to close")
        proceeds_detail = []
        for sym in targets:
            pos = next((p for p in store.paper_positions() if p["symbol"] == sym), None)
            if not pos:
                continue
            price = _price_of(store, sym) or pos["entry_price_usd"]
            gross = pos["amount"] * price
            net = gross - _cost(gross)
            book = store.paper_book()
            store.paper_book_update(book["stable_usd"] + net, book["peak_value_usd"])
            store.paper_position_delete(sym)
            store.log_trade(decision.cycle_id, "strategy", sym, STABLE, status="confirmed",
                            from_amount=f"{pos['amount']:.6f}", to_amount=f"{net:.2f}")
            proceeds_detail.append(f"{sym}->${net:.2f}")
            log.info("PAPER close %s: %.6f -> $%.2f @ $%.4f", sym, pos["amount"], net, price)
        return ExecutionResult("executed", ", ".join(proceeds_detail) or "nothing to close")

    return ExecutionResult("skipped", f"paper: action {decision.action}")


def compliance_roundtrip(store: Store, cycle_id: str, amount_usd: float):
    """Paper USDT->ETH->USDT heartbeat. Two simulated legs, both costed."""
    from aria.execution import ExecutionResult

    book = store.paper_book()
    assert book is not None
    eth_price = _price_of(store, "ETH")
    if not eth_price:
        return ExecutionResult("skipped", "paper heartbeat: no ETH price yet")
    spend = min(amount_usd, book["stable_usd"])
    if spend <= 0:
        return ExecutionResult("skipped", "paper heartbeat: no stable balance")
    # round trip: USDT->ETH->USDT, cost on each leg, no position left
    after_leg1 = (spend - _cost(spend)) / eth_price * eth_price  # eth then back to usd basis
    proceeds = after_leg1 - _cost(after_leg1)
    net_cost = spend - proceeds
    store.paper_book_update(book["stable_usd"] - net_cost, book["peak_value_usd"])
    store.log_trade(cycle_id, "compliance", "USDT", "ETH", status="confirmed",
                    from_amount=f"{spend:.2f}")
    store.log_trade(cycle_id, "compliance", "ETH", "USDT", status="confirmed",
                    to_amount=f"{proceeds:.2f}")
    log.info("PAPER heartbeat round trip: $%.2f, cost $%.3f", spend, net_cost)
    return ExecutionResult("executed", f"roundtrip ${spend:.2f}, cost ${net_cost:.3f}")
