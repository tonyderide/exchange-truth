"""Adapter tests on ccxt-unified shapes, without API keys.

Shapes follow ccxt's unified order/position structures; exchange-specific bits live in `info`.
"""
from exchange_truth.adapters import from_ccxt
from exchange_truth.core import check


class FakeExchange:
    def __init__(self, positions, orders, trigger_orders=(), ticker=None):
        self._p, self._o, self._t, self._tick = positions, orders, list(trigger_orders), ticker or {}

    def fetch_positions(self):
        return self._p

    def fetch_open_orders(self, params=None):
        if params and params.get("trigger"):
            return self._t
        if params and params.get("stop"):
            raise ValueError("unsupported param")  # some exchanges reject it: must not crash
        return self._o

    def fetch_ticker(self, symbol):
        return self._tick


def codes(f):
    return sorted(x.code for x in f)


def test_binance_like_stop_market_close_position():
    # Binance USDM: STOP_MARKET with closePosition=true has amount 0 and reduceOnly false in unified fields
    ex = FakeExchange(
        [{"symbol": "BTC/USDT:USDT", "contracts": 0.01, "side": "long", "markPrice": 60000, "entryPrice": 59000}],
        [{"id": "1", "symbol": "BTC/USDT:USDT", "side": "sell", "type": "stop_market", "amount": 0.01,
          "remaining": 0.01, "triggerPrice": 58000, "reduceOnly": False, "info": {"closePosition": True}}])
    p, o = from_ccxt(ex)
    assert o[0].reduce_only is True
    assert check(p, o) == []


def test_trigger_book_is_merged_and_missing_mark_uses_ticker():
    # Kraken-Futures-like: no markPrice on the position, stop lives in the trigger book
    ex = FakeExchange(
        [{"symbol": "SOL/USD:USD", "contracts": 0.24, "side": "short", "entryPrice": 104.0}],
        [], trigger_orders=[{"id": "s", "symbol": "SOL/USD:USD", "side": "buy", "type": "stop", "amount": 0.24,
                             "remaining": 0.24, "stopPrice": 103.0, "reduceOnly": True}],
        ticker={"last": 101.0, "info": {"markPrice": "101.2"}})
    p, o = from_ccxt(ex)
    assert p[0].mark == 101.2  # NOT the entry price
    # stop at 103 is above mark 101.2 -> a real stop loss (it would look like a TP if we used entry=104)
    assert check(p, o) == []


def test_zero_size_positions_are_ignored():
    ex = FakeExchange([{"symbol": "ETH/USDT:USDT", "contracts": 0, "side": "long", "markPrice": 3000}], [])
    p, o = from_ccxt(ex)
    assert p == [] and o == []


def test_hyperliquid_like_trigger_with_reduce_only_in_info():
    ex = FakeExchange(
        [{"symbol": "ETH/USDC:USDC", "contracts": 1.0, "side": "short", "markPrice": 3000}],
        [{"id": "h", "symbol": "ETH/USDC:USDC", "side": "buy", "type": "market", "amount": 1.0, "remaining": 1.0,
          "triggerPrice": 3100, "info": {"reduceOnly": True, "orderType": "Stop Market"}}])
    p, o = from_ccxt(ex)
    assert o[0].reduce_only
    # type "market" + triggerPrice: still a stop
    assert codes(check(p, o)) == []
