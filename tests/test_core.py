from exchange_truth.core import Position, Order, BotTrade, check


def codes(f):
    return sorted(x.code for x in f)


def sl(symbol="X", side="buy", stop=110.0, amount=1.0, ro=True, oid="sl"):
    return Order(oid, symbol, side, "stop", amount, stop_price=stop, reduce_only=ro)


SHORT = Position("X", "short", 1.0, mark=100.0)
LONG = Position("X", "long", 1.0, mark=100.0)


def test_protected_short_is_clean():
    assert check([SHORT], [sl()]) == []


def test_naked_position():
    assert codes(check([SHORT], [])) == ["NAKED_POSITION"]


def test_buy_stop_below_mark_is_take_profit_not_stop_loss():
    # side-awareness: for a short, a buy-stop under the price is a TP trigger
    assert codes(check([SHORT], [sl(stop=90.0)])) == ["NAKED_POSITION"]


def test_long_needs_sell_stop_below():
    assert check([LONG], [sl(side="sell", stop=95.0)]) == []
    assert codes(check([LONG], [sl(side="buy", stop=95.0)])) == ["NAKED_POSITION"]


def test_undersized_stop():
    assert codes(check([SHORT], [sl(amount=0.4)])) == ["STOP_UNDERSIZED"]


def test_duplicate_stops_like_bug_001():
    f = check([SHORT], [sl(oid="a"), sl(oid="b"), sl(oid="c")])
    assert codes(f) == ["DUPLICATE_STOPS"]


def test_stop_not_reduce_only():
    assert codes(check([SHORT], [sl(ro=False)])) == ["STOP_NOT_REDUCE_ONLY"]


def test_orphan_order_after_position_closed():
    assert codes(check([], [sl()])) == ["ORPHAN_ORDER"]


def test_unknown_amount_does_not_crash():
    assert check([SHORT], [sl(amount=None)]) == []


def test_bot_mismatches():
    f = check([SHORT], [sl()], [BotTrade("X", "short", 0.5), BotTrade("Y", "long", 2)])
    assert codes(f) == ["BOT_GHOST_TRADE", "SIZE_MISMATCH"]
    f = check([SHORT], [sl()], [])
    assert codes(f) == ["UNTRACKED_POSITION"]


def test_attestation_hash_detects_tampering():
    import hashlib, json
    from exchange_truth.cli import attestation
    att = attestation("x", [SHORT], [sl()], [])
    h = att.pop("sha256")
    assert hashlib.sha256(json.dumps(att, sort_keys=True, separators=(",", ":")).encode()).hexdigest() == h
    att["positions"][0]["amount"] = 2.0
    assert hashlib.sha256(json.dumps(att, sort_keys=True, separators=(",", ":")).encode()).hexdigest() != h


def test_unreachable_exchange_is_critical_not_clean(monkeypatch):
    from exchange_truth import cli

    def boom(a):
        raise ConnectionError("503 Service Unavailable")
    monkeypatch.setattr(cli, "run_once", boom)
    assert cli.main(["--exchange", "krakenfutures"]) == 2


def test_single_oversized_stop_is_info():
    f = check([SHORT], [sl(amount=2.0)])
    assert [(x.code, x.severity) for x in f] == [("STOP_OVERSIZED", "INFO")]


def test_worst_case():
    from exchange_truth.core import worst_case
    short = Position("X", "short", 2.0, mark=100.0, entry=100.0)
    long_ = Position("Y", "long", 1.0, mark=50.0, entry=50.0)
    orders = [sl(stop=110.0, amount=2.0), Order("y", "Y", "sell", "stop", 1.0, stop_price=45.0, reduce_only=True)]
    assert worst_case([short, long_], orders) == {"loss_at_stops": 25.0, "unbounded": []}
    assert worst_case([short], [])["unbounded"] == ["X"]


def test_margin_check_like_kraken_1016():
    from exchange_truth.core import margin_check
    # numbers seen live on 2026-10-16: equity 3.467, maintenance 1.998, loss to stops 1.498 from entry, uPnL -0.324
    sol = Position("S", "short", 0.18, mark=104.0, entry=104.02, upnl=-0.03)
    dot = Position("D", "short", 18.3, mark=1.175, entry=1.16062, upnl=-0.294)
    orders = [Order("a", "S", "buy", "stop", 0.18, stop_price=107.1, reduce_only=True),
              Order("b", "D", "buy", "stop", 18.3, stop_price=1.2122, reduce_only=True)]
    f = margin_check([sol, dot], orders, equity=3.467, maintenance=1.998)
    assert [x.code for x in f] == ["THIN_MARGIN_AT_STOPS"]
    f = margin_check([sol, dot], orders, equity=2.9, maintenance=1.998)
    assert [x.code for x in f] == ["LIQUIDATION_BEFORE_STOP"]
