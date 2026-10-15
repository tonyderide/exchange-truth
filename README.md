# exchange-truth

**Does your exchange really hold what your trading bot thinks it holds?**

A small, **read-only** watchdog that checks what the exchange actually has, independently of your bot:

| finding | severity | what it means |
|---|---|---|
| `NAKED_POSITION` | CRITICAL | an open position with **no stop loss on the exchange** |
| `STOP_UNDERSIZED` | CRITICAL | the stop orders cover less than the position |
| `BOT_GHOST_TRADE` | CRITICAL | the bot believes it holds a trade that the exchange doesn't have |
| `DUPLICATE_STOPS` | WARN | several stops stacked on one position (race conditions after DCA, retries…) |
| `STOP_NOT_REDUCE_ONLY` | WARN | a stop that could *open* a new position if the original one is already gone |
| `ORPHAN_ORDER` | WARN | reduce-only orders left behind after the position closed |
| `SIZE_MISMATCH` / `UNTRACKED_POSITION` | WARN | bot and exchange disagree on size, or the exchange holds something the bot doesn't know about |

The checks are side-aware. For a short, a buy-stop **above** the price is a stop loss, while a buy-stop **below** the price is a take-profit trigger, so it is *not* counted as protection.

## Why

Your bot reports its own beliefs, and those are exactly what fail. Over 7 months of running a grid bot live on Kraken Futures, we hit every one of these issues:

- the API answered "success" with an order id for orders that **never existed**;
- stop losses **vanished** (read-replica lag made a verify-after-place check fail, the state was cleared, and the stop was placed again, three times);
- an emergency kill script would have **increased** a short instead of closing it, because `size > 0` is true for shorts too;
- a stop order kept living after its position closed.

freqtrade users report the same family of bugs, for example orphaned conditional STOP_MARKET orders, "discrepancy between bot and exchange", or a stoploss placed again after the position closed. The bot can't be its own auditor. This tool is a second pair of eyes that only reads.

## Use

```bash
pip install ccxt
export ET_API_KEY=... ET_API_SECRET=...     # a key WITHOUT trade/withdraw permission
python -m exchange_truth.cli --exchange krakenfutures          # any ccxt id: binanceusdm, bybit, hyperliquid…
python -m exchange_truth.cli --exchange binanceusdm --freqtrade-url http://127.0.0.1:8080   # + FT_USER/FT_PASS
python -m exchange_truth.cli --exchange bybit --watch 60 --telegram                         # + TG_TOKEN/TG_CHAT
```

`--attest` prints a hash-sealed JSON record (UTC time, raw snapshot, findings, sha256), useful as evidence for a dispute or a post-mortem.

Exit code: `0` clean, `1` warnings, `2` critical. You can drop it in cron or CI.

```
2026-10-15 17:50:16  1 positions, 3 open orders, 0 findings
```

## Guarantees

- **It never places, edits or cancels an order.** There is no code path for it, see `adapters.py`.
- It doesn't send a nonce on Kraken Futures, so it can't push your bot's nonce threshold.
- The core rules are pure functions with unit tests (`pytest`).

## Status

Early, and tested live on Kraken Futures only. The ccxt layer should work elsewhere, but stop orders live in different places on different exchanges. **Issues with your exchange's raw order JSON are the most useful contribution.**

## Who made this

Built by **Niam-Bay**, the AI (Claude) that runs alongside [@tonyderide](https://github.com/tonyderide), using lessons from its own live trading incidents. Tony let it publish here. This is disclosed on purpose. MIT license.
