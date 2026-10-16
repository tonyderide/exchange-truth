"""exchange-truth: does your exchange really hold what your bot thinks it holds?

Read-only. Use an API key WITHOUT trading/withdrawal permission.
"""
import argparse
import dataclasses
import hashlib
import json
import os
import sys
import time
import urllib.parse
import urllib.request

from .adapters import from_ccxt, from_freqtrade
from .core import Finding, check

ICON = {"CRITICAL": "🚨", "WARN": "⚠️", "INFO": "ℹ️"}


def telegram(token, chat, text):
    data = urllib.parse.urlencode({"chat_id": chat, "text": text}).encode()
    urllib.request.urlopen(f"https://api.telegram.org/bot{token}/sendMessage", data=data, timeout=15)


def attestation(exchange, positions, orders, findings):
    """Self-contained, hash-sealed record of what the exchange held at a given time.

    The sha256 covers the canonical JSON of everything else, so any later edit is detectable.
    (Integrity only: a signature proving *who* attested is future work.)
    """
    body = {"tool": "exchange-truth/0.1", "exchange": exchange, "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "positions": [dataclasses.asdict(x) for x in positions], "orders": [dataclasses.asdict(x) for x in orders],
            "findings": [dataclasses.asdict(x) for x in findings]}
    body["sha256"] = hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return body


def run_once(a):
    import ccxt
    if a.exchange not in ccxt.exchanges:
        raise ValueError(f"unknown exchange id {a.exchange!r}")
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
    p.add_argument("--attest", action="store_true",
                   help="print a JSON attestation: UTC time, exchange snapshot, findings and their sha256")
    p.add_argument("--watch", type=int, default=0, help="re-check every N seconds")
    p.add_argument("--telegram", action="store_true", help="alert via TG_TOKEN/TG_CHAT on new findings")
    p.add_argument("--state", help="file remembering the last alerted findings, so one-shot runs from cron don't re-alert")
    p.add_argument("--alert-min", choices=["INFO", "WARN", "CRITICAL"], default="WARN",
                   help="lowest severity that triggers a Telegram alert (default WARN)")
    a = p.parse_args(argv)

    last = None
    if a.state and os.path.exists(a.state):
        last = json.load(open(a.state))
    while True:
        try:
            positions, orders, findings = run_once(a)
        except Exception as e:
            # Never report "clean" when we could not look: silence must not mean safety.
            positions, orders = [], []
            findings = [Finding("CRITICAL", "CHECK_FAILED", "*", f"could not read the exchange: {type(e).__name__}: {e}")]
        if a.attest:
            print(json.dumps(attestation(a.exchange, positions, orders, findings), sort_keys=True))
        elif a.json:
            print(json.dumps([f.__dict__ for f in findings]))
        else:
            print(f"{time.strftime('%F %T')}  {len(positions)} positions, {len(orders)} open orders, "
                  f"{len(findings)} findings")
            for f in findings:
                print(f"  {ICON.get(f.severity, '')} {f.severity:8} {f.code:22} {f.symbol}: {f.message}")
        rank = {"INFO": 0, "WARN": 1, "CRITICAL": 2}
        alerting = [f for f in findings if rank[f.severity] >= rank[a.alert_min]]
        key = sorted([f.code, f.symbol] for f in alerting)
        if a.telegram and alerting and key != last:
            telegram(os.environ["TG_TOKEN"], os.environ["TG_CHAT"],
                     "exchange-truth\n" + "\n".join(f"{ICON.get(f.severity, '')} {f.code} {f.symbol}: {f.message}" for f in alerting))
        last = key
        if a.state:
            json.dump(key, open(a.state, "w"))
        if not a.watch:
            return 2 if any(f.severity == "CRITICAL" for f in findings) else (1 if findings else 0)
        time.sleep(a.watch)


if __name__ == "__main__":
    sys.exit(main())
