"""Read-only adapters. Nothing here can place, edit or cancel an order."""
import base64
import json
import urllib.request
from typing import List

from .core import BotTrade, Order, Position


def _f(x):
    try:
        return float(x) if x is not None and x != "" else None
    except (TypeError, ValueError):
        return None


def from_ccxt(exchange) -> tuple:
    """Fetch positions + open orders (regular and trigger/stop) from a ccxt exchange instance."""
    positions: List[Position] = []
    for p in exchange.fetch_positions():
        amt = abs(_f(p.get("contracts")) or 0)
        if amt <= 0:
            continue
        side = p.get("side") or ("long" if (_f(p.get("contracts")) or 0) > 0 else "short")
        mark = _f(p.get("markPrice")) or _f(p.get("lastPrice"))
        if mark is None:  # e.g. krakenfutures positions carry no mark: never fall back to entry silently
            t = exchange.fetch_ticker(p["symbol"])
            mark = _f((t.get("info") or {}).get("markPrice")) or _f(t.get("last"))
        positions.append(Position(p["symbol"], side, amt, mark, _f(p.get("entryPrice")),
                                  _f(p.get("unrealizedPnl")) if p.get("unrealizedPnl") is not None else _f((p.get("info") or {}).get("unrealizedPnl"))))

    raw = list(exchange.fetch_open_orders())
    seen = {o.get("id") for o in raw}
    for params in ({"trigger": True}, {"stop": True}):  # many exchanges keep stops in a separate book
        try:
            for o in exchange.fetch_open_orders(params=params):
                if o.get("id") not in seen:
                    raw.append(o); seen.add(o.get("id"))
        except Exception:
            pass

    orders: List[Order] = []
    for o in raw:
        info = o.get("info") or {}
        ro = bool(o.get("reduceOnly") or info.get("reduceOnly") or info.get("reduce_only")
                  or info.get("closePosition") in (True, "true"))
        stop = _f(o.get("triggerPrice")) or _f(o.get("stopPrice")) or _f(o.get("stopLossPrice"))
        remaining = _f(o.get("remaining"))
        orders.append(Order(str(o.get("id")), o["symbol"], o.get("side"), (o.get("type") or "").lower(),
                            remaining if remaining is not None else _f(o.get("amount")),
                            stop_price=stop, limit_price=_f(o.get("price")), reduce_only=ro))
    return positions, orders


def from_freqtrade(url: str, user: str, password: str) -> List[BotTrade]:
    """Open trades as freqtrade believes them to be (REST API /api/v1/status)."""
    req = urllib.request.Request(url.rstrip("/") + "/api/v1/status")
    req.add_header("Authorization", "Basic " + base64.b64encode(f"{user}:{password}".encode()).decode())
    trades = json.load(urllib.request.urlopen(req, timeout=15))
    return [BotTrade(t["pair"], "short" if t.get("is_short") else "long", float(t["amount"])) for t in trades]


def account_margin(exchange):
    """(equity, maintenance margin) when the exchange exposes them; None otherwise.
    Known: krakenfutures multi-collateral ('flex') account. Other exchanges: contributions welcome."""
    try:
        info = exchange.fetch_balance().get("info") or {}
        flex = (info.get("accounts") or {}).get("flex") or {}
        eq, mm = _f(flex.get("marginEquity")), _f(flex.get("maintenanceMargin"))
        return (eq, mm) if eq is not None and mm is not None else None
    except Exception:
        return None
