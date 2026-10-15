"""MCP server: lets an AI agent ask "is my bot's exchange account really protected?".

Read-only, like the CLI. Keys come from the environment of the MCP server process
(ET_API_KEY / ET_API_SECRET), never from the agent's arguments.

Run:  python -m exchange_truth.mcp_server        (stdio transport)
Requires: pip install "mcp>=2" ccxt
"""
import dataclasses
import os

from mcp.server.mcpserver import MCPServer

from .adapters import from_ccxt, from_freqtrade
from .cli import attestation
from .core import Finding, check

server = MCPServer("exchange-truth", instructions=(
    "Read-only watchdog for trading-bot accounts. Call check_exchange to verify that every open "
    "position has a real stop loss on the exchange and that the bot's beliefs match the exchange. "
    "It never places or cancels orders."))


def _exchange(exchange_id: str):
    import ccxt
    return getattr(ccxt, exchange_id)({"apiKey": os.environ.get("ET_API_KEY", ""),
                                       "secret": os.environ.get("ET_API_SECRET", ""), "enableRateLimit": True})


@server.tool(description="Check an exchange account (any ccxt id, e.g. krakenfutures, binanceusdm, bybit, "
                         "hyperliquid). Returns findings such as NAKED_POSITION, STOP_UNDERSIZED, DUPLICATE_STOPS, "
                         "ORPHAN_ORDER. Set compare_freqtrade=true to also diff against FT_URL/FT_USER/FT_PASS.")
def check_exchange(exchange_id: str, compare_freqtrade: bool = False) -> dict:
    try:
        positions, orders = from_ccxt(_exchange(exchange_id))
        bot = None
        if compare_freqtrade:
            bot = from_freqtrade(os.environ["FT_URL"], os.environ.get("FT_USER", ""), os.environ.get("FT_PASS", ""))
        findings = check(positions, orders, bot)
    except Exception as e:  # never answer "clean" when blind
        positions, orders = [], []
        findings = [Finding("CRITICAL", "CHECK_FAILED", "*", f"could not read the exchange: {type(e).__name__}: {e}")]
    return {"clean": not findings, "critical": any(f.severity == "CRITICAL" for f in findings),
            "findings": [dataclasses.asdict(f) for f in findings],
            "positions": len(positions), "open_orders": len(orders)}


@server.tool(description="Same check, returned as a sha256-sealed attestation (UTC time, raw snapshot, findings), "
                         "useful as evidence in a post-mortem.")
def attest_exchange(exchange_id: str) -> dict:
    try:
        positions, orders = from_ccxt(_exchange(exchange_id))
        findings = check(positions, orders)
    except Exception as e:
        positions, orders = [], []
        findings = [Finding("CRITICAL", "CHECK_FAILED", "*", f"could not read the exchange: {type(e).__name__}: {e}")]
    return attestation(exchange_id, positions, orders, findings)


def main():
    server.run("stdio")


if __name__ == "__main__":
    main()
