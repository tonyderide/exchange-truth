"""Pure checks: compare what the exchange really holds with what should protect it.

No network here. Adapters (ccxt, freqtrade) normalise data into these dataclasses,
so every rule is unit-testable on plain values.
"""
from dataclasses import dataclass, field
from typing import List, Optional



@dataclass
class Position:
    symbol: str
    side: str            # "long" | "short"
    amount: float        # contracts, > 0
    mark: float          # current mark/last price
    entry: Optional[float] = None


@dataclass
class Order:
    id: str
    symbol: str
    side: str            # "buy" | "sell"
    type: str            # normalised lower-case order type
    amount: Optional[float]
    stop_price: Optional[float] = None
    limit_price: Optional[float] = None
    reduce_only: bool = False


@dataclass
class BotTrade:
    symbol: str
    side: str            # "long" | "short"
    amount: float


@dataclass
class Finding:
    severity: str        # "CRITICAL" | "WARN" | "INFO"
    code: str
    symbol: str
    message: str
    details: dict = field(default_factory=dict)


def _is_stop(o: Order) -> bool:
    # Any order carrying a trigger price is conditional, whatever its type label:
    # ccxt reports Hyperliquid stops as type "market" + triggerPrice.
    return o.stop_price is not None


def _closing_side(p: Position) -> str:
    return "buy" if p.side == "short" else "sell"


def _is_stop_loss_for(o: Order, p: Position) -> bool:
    """A protective stop: closing side, reduce-only, trigger on the ADVERSE side of the mark.

    A buy-stop *below* the mark of a short is a take-profit trigger, not a stop loss
    (a mistake we made ourselves once: side-awareness matters).
    """
    if o.symbol != p.symbol or not _is_stop(o) or o.side != _closing_side(p):
        return False
    if p.side == "short":
        return o.stop_price > p.mark
    return o.stop_price < p.mark


def check(positions: List[Position], orders: List[Order], bot_trades: Optional[List[BotTrade]] = None,
          size_tolerance: float = 0.01) -> List[Finding]:
    out: List[Finding] = []
    pos_symbols = {p.symbol for p in positions}

    for p in positions:
        sls = [o for o in orders if _is_stop_loss_for(o, p)]
        if not sls:
            out.append(Finding("CRITICAL", "NAKED_POSITION", p.symbol,
                               f"{p.side} {p.amount} {p.symbol} has NO stop loss on the exchange",
                               {"mark": p.mark}))
            continue
        not_reduce = [o.id for o in sls if not o.reduce_only]
        if not_reduce:
            out.append(Finding("WARN", "STOP_NOT_REDUCE_ONLY", p.symbol,
                               "stop order is not reduce-only: if the position closes first it can OPEN a new one",
                               {"orders": not_reduce}))
        known = [o.amount for o in sls if o.amount is not None]
        if known:
            covered = sum(known)
            if covered < p.amount * (1 - size_tolerance):
                out.append(Finding("CRITICAL", "STOP_UNDERSIZED", p.symbol,
                                   f"stops cover {covered} of {p.amount}", {"covered": covered, "position": p.amount}))
            elif len(sls) > 1 and covered > p.amount * (1 + size_tolerance):
                out.append(Finding("WARN", "DUPLICATE_STOPS", p.symbol,
                                   f"{len(sls)} stop orders cover {covered} for a {p.amount} position",
                                   {"orders": [o.id for o in sls]}))
            elif covered > p.amount * (1 + size_tolerance):
                # A single reduce-only stop larger than the position: the stop was not resized after a partial
                # exit. The exchange will cap it, but some bots then book the ORIGINAL size as filled
                # (e.g. freqtrade#13671 on Hyperliquid), overstating profit/loss.
                out.append(Finding("INFO", "STOP_OVERSIZED", p.symbol,
                                   f"stop covers {covered} but position is {p.amount} (not resized after a partial exit?)",
                                   {"covered": covered, "position": p.amount}))

    for o in orders:
        if o.reduce_only and o.symbol not in pos_symbols:
            out.append(Finding("WARN", "ORPHAN_ORDER", o.symbol,
                               f"reduce-only {o.side} {o.type} order with no position (left behind?)",
                               {"order": o.id, "stop": o.stop_price, "limit": o.limit_price}))

    if bot_trades is not None:
        bot = {}
        for t in bot_trades:
            k = (t.symbol, t.side)
            bot[k] = bot.get(k, 0) + t.amount
        ex = {(p.symbol, p.side): p.amount for p in positions}
        for k, amt in bot.items():
            if k not in ex:
                out.append(Finding("CRITICAL", "BOT_GHOST_TRADE", k[0],
                                   f"bot believes it holds {k[1]} {amt} but the exchange has no such position"))
            elif abs(ex[k] - amt) > max(ex[k], amt) * size_tolerance:
                out.append(Finding("WARN", "SIZE_MISMATCH", k[0],
                                   f"bot thinks {amt}, exchange holds {ex[k]}", {"bot": amt, "exchange": ex[k]}))
        for k, amt in ex.items():
            if k not in bot:
                out.append(Finding("WARN", "UNTRACKED_POSITION", k[0],
                                   f"exchange holds {k[1]} {amt} that the bot does not know about"))
    return out


def worst_case(positions: List[Position], orders: List[Order], bot_entry: bool = True) -> dict:
    """Loss if every position hits its (tightest) stop loss now, measured from the entry price when known
    (otherwise from the mark). Positions without a stop are reported as unbounded."""
    total, unbounded = 0.0, []
    for p in positions:
        sls = [o for o in orders if _is_stop_loss_for(o, p)]
        if not sls:
            unbounded.append(p.symbol); continue
        ref = p.entry if (bot_entry and p.entry) else p.mark
        stop = min(o.stop_price for o in sls) if p.side == "short" else max(o.stop_price for o in sls)
        total += (stop - ref) * p.amount if p.side == "short" else (ref - stop) * p.amount
    return {"loss_at_stops": round(total, 4), "unbounded": unbounded}
