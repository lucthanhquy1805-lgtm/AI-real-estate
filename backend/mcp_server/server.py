"""MCP server của dự án — cung cấp cho Claude Code các công cụ hiểu và kiểm tra dữ liệu dự án.

Chạy (stdio):  python -m mcp_server.server     (từ thư mục backend, có venv)
Khai báo cho Claude Code: file .mcp.json ở gốc repo.

Mọi tool ở đây chỉ ĐỌC. Không có tool nào ghi DB, sửa file hay crawl dữ liệu.
"""

from __future__ import annotations

import re
import urllib.robotparser
from pathlib import Path
from typing import Any

import httpx
from mcp.server.mcpserver import MCPServer
from sqlalchemy import create_engine, text

from app.config import get_settings
from app.contracts import load_sources
from ingestion.core.policy import FieldPolicy, UnknownFieldError
from ingestion.normalize.admin_units import resolve_ward as _resolve_ward

server = MCPServer(
    name="aipi",
    title="AI Property Intelligence — project tools",
    instructions=(
        "Công cụ chỉ-đọc cho dự án nghiên cứu BĐS Quận 9 cũ. Dùng roadmap_next để biết việc tiếp theo, "
        "check_fields trước khi thêm cột/trường mới, check_robots trước khi thêm nguồn, db_query để xem dữ liệu."
    ),
)

MAX_ROWS = 500
_READ_ONLY_SQL = re.compile(r"^\s*(select|with|explain(?!\s+analyze)|show|table)\b", re.IGNORECASE)
_ROADMAP_ITEM = re.compile(r"^- \[( |x)\] (T\d+\.\d+\w?|X\.\d+) — (.+)$")


def _repo_root() -> Path:
    return get_settings().repo_root


# ---------------------------------------------------------------- dữ liệu tham chiếu & hợp đồng


@server.tool()
def resolve_ward(address: str, context: str = "") -> dict[str, Any]:
    """Chuẩn hóa địa chỉ khu vực Quận 9 cũ sang phường mới (sau 01/07/2025).

    address: chuỗi địa chỉ trong tin đăng. context: breadcrumb / ô quận-huyện có cấu trúc nếu có.
    Trả về slug phường mới, tên cũ, độ tin cậy và cờ (AMBIGUOUS_WARD, NO_CONTEXT, ...)."""
    r = _resolve_ward(address, context_text=context)
    return r.__dict__ | {"resolved": r.resolved}


@server.tool()
def list_sources() -> list[dict[str, Any]]:
    """Danh mục nguồn dữ liệu (sources.yaml) kèm kết quả policy gate: nguồn nào đang được phép crawl và vì sao."""
    reg = load_sources()
    out = []
    for s in reg.sources:
        ok, reason = s.can_crawl()
        out.append(
            {
                "id": s.id,
                "name": s.name,
                "tier": s.tier,
                "base_url": s.base_url,
                "permission_level": s.permission_level.value,
                "allow_training": s.allow_training,
                "status": s.status.value,
                "delay_seconds": reg.delay_for(s.id),
                "next_review_at": str(s.next_review_at) if s.next_review_at else None,
                "can_crawl": ok,
                "gate_reason": reason,
            }
        )
    return out


@server.tool()
def check_fields(fields: list[str]) -> dict[str, Any]:
    """Kiểm tra danh sách tên trường/cột theo field_policy.yaml.

    Dùng TRƯỚC khi thêm cột DB hoặc trường parser. Trường 'unknown' phải được khai báo trong
    field_policy.yaml; trường có store=false tuyệt đối không được thành cột DB."""
    pol = FieldPolicy.load()
    result: dict[str, Any] = {"allowed": {}, "forbidden": {}, "unknown": []}
    for f in fields:
        try:
            cls = pol.class_of(f)
        except UnknownFieldError:
            result["unknown"].append(f)
            continue
        bucket = "allowed" if pol.can_store(f) else "forbidden"
        result[bucket][f] = {"class": cls, "display": pol.can_display(f)}
    return result


# ---------------------------------------------------------------- nguồn web


@server.tool()
def check_robots(url: str, user_agent: str = "") -> dict[str, Any]:
    """Đọc robots.txt của domain chứa `url` và cho biết URL đó có được phép fetch hay không.

    Chỉ tải đúng một file robots.txt. Trả về: allowed, crawl_delay, sitemaps, content_signals (vd ai-train=no).
    Đây là tín hiệu kỹ thuật, KHÔNG phải giấy phép pháp lý — vẫn phải đọc điều khoản (skill add-source)."""
    reg = load_sources()
    ua = user_agent or reg.defaults.user_agent
    parsed = httpx.URL(url)
    robots_url = f"{parsed.scheme}://{parsed.host}/robots.txt"
    resp = httpx.get(robots_url, headers={"User-Agent": ua}, timeout=15, follow_redirects=True)
    body = resp.text if resp.status_code == 200 else ""
    rp = urllib.robotparser.RobotFileParser()
    rp.parse(body.splitlines())
    signals = [ln.split(":", 1)[1].strip() for ln in body.splitlines() if ln.lower().startswith("content-signal:")]
    return {
        "robots_url": robots_url,
        "http_status": resp.status_code,
        "allowed": rp.can_fetch(ua, url) if body else resp.status_code in (404, 410),
        "crawl_delay": rp.crawl_delay(ua),
        "sitemaps": rp.site_maps() or [],
        "content_signals": signals,
        "ai_train_disallowed": any("ai-train=no" in s.replace(" ", "") for s in signals),
        "user_agent_checked": ua,
    }


# ---------------------------------------------------------------- database (chỉ đọc)


def _engine():
    return create_engine(get_settings().database_url, pool_pre_ping=True)


@server.tool()
def db_schema(table: str = "") -> list[dict[str, Any]]:
    """Liệt kê bảng và cột trong schema public. Truyền `table` để xem một bảng."""
    sql = (
        "select table_name, column_name, data_type, is_nullable from information_schema.columns "
        "where table_schema='public' and (:t = '' or table_name = :t) "
        "and table_name not in ('spatial_ref_sys') order by table_name, ordinal_position"
    )
    with _engine().connect() as c:
        return [dict(r._mapping) for r in c.execute(text(sql), {"t": table})]


def _jsonable(v: Any) -> Any:
    return v if v is None or isinstance(v, (int, float, bool, str)) else str(v)


@server.tool()
def db_query(sql: str, limit: int = 100) -> dict[str, Any]:
    """Chạy MỘT câu SQL chỉ-đọc (SELECT/WITH/EXPLAIN) trong transaction READ ONLY, timeout 10 giây.

    Trả tối đa `limit` dòng (≤ 500). Dùng để kiểm tra dữ liệu, độ phủ, chất lượng."""
    stmt = sql.strip().rstrip(";")
    if ";" in stmt:
        raise ValueError("Chỉ cho phép một câu lệnh.")
    if not _READ_ONLY_SQL.match(stmt):
        raise ValueError("Chỉ cho phép SELECT / WITH / EXPLAIN (không ANALYZE) / SHOW.")
    limit = max(1, min(limit, MAX_ROWS))
    with _engine().connect() as c:
        c.execute(text("SET TRANSACTION READ ONLY"))
        c.execute(text("SET LOCAL statement_timeout = '10s'"))
        res = c.execute(text(stmt))
        cols = list(res.keys())
        rows = [list(r) for r in res.fetchmany(limit + 1)]
        c.rollback()
    return {
        "columns": cols,
        "rows": [
            [str(v) if v is not None and not isinstance(v, (int, float, bool)) else v for v in r] for r in rows[:limit]
        ],
        "truncated": len(rows) > limit,
    }


@server.tool()
def data_summary() -> dict[str, Any]:
    """Tổng quan nhanh: số dòng của các bảng chính và số tin theo phường (nếu bảng listings đã tồn tại)."""
    out: dict[str, Any] = {}
    with _engine().connect() as c:
        tables = [
            r[0]
            for r in c.execute(
                text(
                    "select table_name from information_schema.tables where table_schema='public' "
                    "and table_type='BASE TABLE' and table_name <> 'spatial_ref_sys' order by 1"
                )
            )
        ]
        out["row_counts"] = {
            t: c.execute(text(f'select count(*) from "{t}"')).scalar() for t in tables if t != "alembic_version"
        }
        if "listings" in tables:
            out["listings_by_ward"] = {
                str(k): v
                for k, v in c.execute(
                    text(
                        "select coalesce(ward_slug_new, '(chưa xác định)'), count(*) "
                        "from listings group by 1 order by 2 desc"
                    )
                )
            }
    return out


# ---------------------------------------------------------------- kế hoạch


@server.tool()
def roadmap_next(n: int = 5) -> dict[str, Any]:
    """Đọc docs/ROADMAP.md: trả về n việc chưa xong tiếp theo (kèm DoD và Files) và tiến độ tổng."""
    lines = (_repo_root() / "docs" / "ROADMAP.md").read_text(encoding="utf-8").splitlines()
    items: list[dict[str, Any]] = []
    cur: dict[str, Any] | None = None
    for ln in lines:
        m = _ROADMAP_ITEM.match(ln)
        if m:
            cur = {"id": m.group(2), "title": m.group(3), "done": m.group(1) == "x", "details": []}
            items.append(cur)
        elif cur and ln.startswith("  - "):
            cur["details"].append(ln[4:])
        elif not ln.strip():
            continue
        else:
            cur = None
    todo = [i for i in items if not i["done"]]
    return {"done": len(items) - len(todo), "total": len(items), "next": todo[: max(1, n)]}


def main() -> None:
    server.run("stdio")


if __name__ == "__main__":
    main()
