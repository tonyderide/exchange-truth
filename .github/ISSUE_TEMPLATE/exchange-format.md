---
name: My exchange's stops are not detected / wrongly detected
about: Help exchange-truth understand how your exchange reports stop orders
title: "[exchange] <ccxt id>: "
labels: exchange-format
---

**Exchange (ccxt id) and ccxt version:**

**What exchange-truth reported** (paste the output, e.g. `NAKED_POSITION` while you do have a stop):

**Raw data**: please paste one position and its stop order as ccxt returns them. **Remove ids and any account info.**
```python
import ccxt, json
ex = ccxt.<id>({"apiKey": "...", "secret": "..."})          # read-only key
print(json.dumps(ex.fetch_positions()[:1], indent=1, default=str))
print(json.dumps(ex.fetch_open_orders(params={"trigger": True})[:2], indent=1, default=str))
```

A test reproducing your exact shape will be added in `tests/test_adapters.py`.
