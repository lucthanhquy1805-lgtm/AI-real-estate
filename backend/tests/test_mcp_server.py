import os

import httpx
import pytest

from mcp_server import server as srv

EXPECTED_TOOLS = {
    "resolve_ward",
    "list_sources",
    "check_fields",
    "check_robots",
    "db_schema",
    "db_query",
    "data_summary",
    "roadmap_next",
}


@pytest.mark.anyio
async def test_tools_registered():
    tools = await srv.server.list_tools()
    assert EXPECTED_TOOLS <= {t.name for t in tools}


def test_resolve_ward_tool():
    r = srv.resolve_ward("P. Phước Long B, Q.9")
    assert r["ward_slug_new"] == "hcm.phuoc_long" and r["resolved"]


def test_check_fields_tool():
    r = srv.check_fields(["asking_price_vnd", "description", "poster_phone", "new_thing"])
    assert "asking_price_vnd" in r["allowed"]
    assert set(r["forbidden"]) == {"description", "poster_phone"}
    assert r["unknown"] == ["new_thing"]


def test_list_sources_tool():
    by_id = {s["id"]: s for s in srv.list_sources()}
    assert by_id["nhatot"]["allow_training"] is False
    assert by_id["batdongsan"]["can_crawl"] is False  # đang paused


def test_roadmap_next_tool():
    r = srv.roadmap_next(3)
    assert r["total"] > 10 and r["done"] >= 4
    assert r["next"][0]["id"].startswith("T")
    assert any(d.startswith("DoD:") for d in r["next"][0]["details"])


def test_check_robots_tool(monkeypatch):
    body = "User-agent: *\nDisallow: /user/\nContent-Signal: search=yes, ai-train=no\nSitemap: https://x.vn/s.xml\n"

    def fake_get(url, **kw):
        assert url == "https://x.vn/robots.txt"
        return httpx.Response(200, text=body, request=httpx.Request("GET", url))

    monkeypatch.setattr(srv.httpx, "get", fake_get)
    ok = srv.check_robots("https://x.vn/ban-nha/123")
    assert ok["allowed"] is True and ok["ai_train_disallowed"] is True and ok["sitemaps"] == ["https://x.vn/s.xml"]
    assert srv.check_robots("https://x.vn/user/abc")["allowed"] is False


@pytest.mark.parametrize(
    "sql",
    [
        "delete from data_sources",
        "update x set a=1",
        "select 1; drop table x",
        "explain analyze select 1",
        "insert into t values (1)",
    ],
)
def test_db_query_rejects_writes(sql):
    with pytest.raises(ValueError):
        srv.db_query(sql)


@pytest.mark.db
@pytest.mark.skipif(not os.environ.get("TEST_DATABASE_URL"), reason="TEST_DATABASE_URL chưa đặt")
def test_db_tools(monkeypatch):
    from app.config import get_settings

    monkeypatch.setenv("DATABASE_URL", os.environ["TEST_DATABASE_URL"])
    get_settings.cache_clear()
    cols = srv.db_schema("admin_units")
    assert {c["column_name"] for c in cols} >= {"slug", "name"}
    r = srv.db_query("select slug from admin_units order by slug", limit=2)
    assert r["columns"] == ["slug"] and len(r["rows"]) == 2 and r["truncated"] is True
    # CTE ghi dữ liệu bị transaction READ ONLY chặn
    with pytest.raises(Exception, match="read-only"):
        srv.db_query("with d as (delete from admin_unit_mapping returning 1) select count(*) from d")
    assert srv.data_summary()["row_counts"]["admin_units"] == 5
    get_settings.cache_clear()
