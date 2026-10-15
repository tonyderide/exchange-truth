"""exchange-truth: does your exchange really hold what your bot thinks it holds?

Read-only. Use an API key WITHOUT trading/withdrawal permission.
"""
import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request

from .adapters import from_ccxt, from_freqtrade
from .core import check

ICON = {"CRITICAL": "🚨", "WARN": "⚠️", "INFO": "ℹ️"}


def telegram(token, chat, text):
    data = urllib.parse.urlencode({"chat_id": chat, "text": text}).encode()
    urllib.request.urlopen(f"https://api.telegram.org/bot{token}/sendMessage", data=data, timeout=15)


def run_once(a):
    import ccxt
    ex = getattr(ccxt, a.exchange)({"apiKey": os.environ.get(a.key_env, ""), "secret": os.environ.get(a.secret_env, ""),
                                    "enableRateLimit": True})
    positions, orders = from_ccxt(ex)
    bot = None
    if a.freqtrade_url:
        bot = from_freqtrade(a.freqtrade_url, os.environ.get("FT_USER", ""), os.environ.get("FT_PASS", ""))
    return positions, orders, check(positions, orders, bot)


def main(argv=None):
    p = argparse.ArgumentParser(prog="exchange-truth", description=__doc__)
    p.add_argument("--exchange", required=True, help="ccxt id, e.g. krakenfutures, binanceusdm, hyperliquid, bybit")
    p.add_argument("--key-env", default="ET_API_KEY"); p.add_argument("--secret-env", default="ET_API_SECRET")
    p.add_argument("--freqtrade-url", help="compare with a freqtrade bot (REST API); creds in FT_USER/FT_PASS")
    p.add_argument("--json", action="store_true")
    p.add_argument("--watch", type=int, default=0, help="re-check every N seconds")
    p.add_argument("--telegram", action="store_true", help="alert via TG_TOKEN/TG_CHAT on new findings")
    a = p.parse_args(argv)

    last = None
    while True:
        try:
            positions, orders, findings = run_once(a)
        except Exception as e:  # an unreachable exchange is itself worth knowing
            positions, orders, findings = [], [], []
            print(f"error: {e}", file=sys.stderr)
        if a.json:
            print(json.dumps([f.__dict__ for f in findings]))
        else:
            print(f"{time.strftime('%F %T')}  {len(positions)} positions, {len(orders)} open orders, "
                  f"{len(findings)} findings")
            for f in findings:
                print(f"  {ICON.get(f.severity, '')} {f.severity:8} {f.code:22} {f.symbol}: {f.message}")
        key = sorted((f.code, f.symbol) for f in findings)
        if a.telegram and findings and key != last:
            telegram(os.environ["TG_TOKEN"], os.environ["TG_CHAT"],
                     "exchange-truth\n" + "\n".join(f"{ICON.get(f.severity, '')} {f.code} {f.symbol}: {f.message}" for f in findings))
        last = key
        if not a.watch:
            return 2 if any(f.severity == "CRITICAL" for f in findings) else (1 if findings else 0)
        time.sleep(a.watch)


if __name__ == "__main__":
    sys.exit(main())
