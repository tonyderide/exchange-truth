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


def test_exchange_id_is_whitelisted():
    from exchange_truth import mcp_server
    for bad in ["__class__", "Exchange", "base", "../../etc/passwd", "os"]:
        r = mcp_server.check_exchange(bad)
        assert r["critical"] and "unknown exchange id" in r["findings"][0]["message"]
