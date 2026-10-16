"""from_freqtrade against a local fake of freqtrade's /api/v1/status (TradeSchema: pair, is_short, amount)."""
import base64
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from exchange_truth.adapters import from_freqtrade
from exchange_truth.core import Order, Position, check

TRADES = [{"pair": "BTC/USDT:USDT", "is_short": False, "amount": 0.01, "trade_id": 1},
          {"pair": "ETH/USDT:USDT", "is_short": True, "amount": 0.5, "trade_id": 2}]


class Fake(BaseHTTPRequestHandler):
    def do_GET(self):
        ok = self.headers.get("Authorization") == "Basic " + base64.b64encode(b"u:p").decode()
        if self.path != "/api/v1/status" or not ok:
            self.send_response(401); self.end_headers(); return
        body = json.dumps(TRADES).encode()
        self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


def test_freqtrade_status_parsed_and_compared():
    srv = HTTPServer(("127.0.0.1", 0), Fake)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        bot = from_freqtrade(f"http://127.0.0.1:{srv.server_port}", "u", "p")
    finally:
        srv.shutdown()
    assert [(t.symbol, t.side, t.amount) for t in bot] == [("BTC/USDT:USDT", "long", 0.01), ("ETH/USDT:USDT", "short", 0.5)]
    # exchange only holds the BTC long (with its stop): the ETH short is a ghost in the bot's mind
    pos = [Position("BTC/USDT:USDT", "long", 0.01, mark=60000)]
    orders = [Order("s", "BTC/USDT:USDT", "sell", "stop_market", 0.01, stop_price=58000, reduce_only=True)]
    assert sorted(f.code for f in check(pos, orders, bot)) == ["BOT_GHOST_TRADE"]
