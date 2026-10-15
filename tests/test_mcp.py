import asyncio
import pytest

mcp = pytest.importorskip("mcp")


def test_tools_listed_and_blind_check_is_critical(monkeypatch):
    from exchange_truth import mcp_server

    def boom(_):
        raise ConnectionError("503")
    monkeypatch.setattr(mcp_server, "_exchange", boom)
    names = {t.name for t in asyncio.run(mcp_server.server.list_tools())}
    assert {"check_exchange", "attest_exchange"} <= names
    r = mcp_server.check_exchange("krakenfutures")
    assert r["critical"] and r["findings"][0]["code"] == "CHECK_FAILED"
