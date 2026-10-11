"""Test cần PostgreSQL + PostGIS + pgvector. Bỏ qua nếu không có TEST_DATABASE_URL."""

import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

DB_URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = [pytest.mark.db, pytest.mark.skipif(not DB_URL, reason="TEST_DATABASE_URL chưa đặt")]
BACKEND = Path(__file__).resolve().parents[1]


def _alembic(*args: str) -> None:
    p = subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=BACKEND,
        env={**os.environ, "DATABASE_URL": DB_URL},
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert p.returncode == 0, f"alembic {' '.join(args)} lỗi:\n{p.stdout}\n{p.stderr}"


@pytest.fixture(scope="module")
def migrated():
    _alembic("downgrade", "base")
    _alembic("upgrade", "head")
    os.environ["DATABASE_URL"] = DB_URL
    from app.config import get_settings
    from app.db.session import get_engine

    get_settings.cache_clear()
    get_engine.cache_clear()
    yield create_engine(DB_URL)


def test_seed_is_idempotent(migrated):
    from app.db.seed import seed

    with Session(migrated) as s:
        first = seed(s)
        second = seed(s)
    assert first == second == {"sources": 7, "wards": 5, "mappings": 14}
    with migrated.connect() as c:
        assert c.execute(text("select count(*) from admin_units")).scalar() == 5
        assert c.execute(text("select count(*) from data_sources")).scalar() == 7


def test_api_health_and_wards(migrated):
    from app.main import app

    client = TestClient(app)
    h = client.get("/health").json()
    assert h["db"] is True and h["extensions"] == ["pg_trgm", "postgis", "vector"]
    wards = {w["slug"]: w for w in client.get("/reference/wards").json()}
    assert "Long Thạnh Mỹ (một phần)" in wards["hcm.long_binh"]["old_wards"]
    r = client.get("/reference/resolve-ward", params={"address": "Hiệp Phú, Quận 9"}).json()
    assert r["ward_slug_new"] == "hcm.tang_nhon_phu"
    srcs = {s["id"]: s for s in client.get("/admin/sources").json()}
    assert srcs["nhatot"]["allow_training"] is False


# ---------------------------------------------------------------- migration 0002

NOW = "2026-10-11T00:00:00+07:00"
LISTING_SQL = text(
    "insert into listings (source_id, source_listing_id, source_url, transaction_type, property_type,"
    " first_seen_at, last_seen_at, parser_version, collected_at)"
    " values (:src, :sid, 'https://example.test/tin-1', :tt, 'townhouse', :now, :now, :pv, :now)"
)


def _source_id(conn) -> str:
    from app.db.seed import seed

    with Session(bind=conn) as s:
        seed(s)
    return conn.execute(text("select source_id from data_sources order by source_id limit 1")).scalar_one()


def _new_job(conn, source_id: str):
    return conn.execute(
        text("insert into ingestion_jobs (source_id, kind, parser_version) values (:s, 'fetch', 't') returning job_id"),
        {"s": source_id},
    ).scalar_one()


def test_real_schema_has_no_forbidden_columns(migrated):
    """Đối chiếu field policy trên DB thật sau migration, không chỉ trên metadata ORM."""
    from test_compliance_schema import SUSPICIOUS

    from ingestion.core.policy import FieldPolicy

    forbidden = FieldPolicy.load().forbidden_fields()
    insp = inspect(migrated)
    tables = set(insp.get_table_names())
    assert {"ingestion_jobs", "fetch_log", "listings", "listing_features", "listing_observations"} <= tables
    assert "data_quality_issues" in tables
    offenders = [
        f"{t}.{c['name']}"
        for t in tables
        for c in insp.get_columns(t)
        if c["name"] in forbidden or SUSPICIOUS.search(c["name"])
    ]
    assert not offenders, f"Cột vi phạm field policy trong DB: {offenders}"


@pytest.mark.parametrize(
    ("params", "case"),
    [
        ({"tt": "sale", "pv": None}, "thiếu parser_version"),
        ({"tt": "lease", "pv": "t"}, "transaction_type ngoài enum"),
    ],
)
def test_listing_constraints_reject_bad_rows(migrated, params, case):
    with migrated.connect() as conn:
        src = _source_id(conn)
        with pytest.raises(IntegrityError):
            conn.execute(LISTING_SQL, {"src": src, "sid": f"bad-{case}", "now": NOW, **params})
        conn.rollback()


def test_listing_unique_per_source(migrated):
    with migrated.connect() as conn:
        src = _source_id(conn)
        row = {"src": src, "sid": "dup-1", "tt": "sale", "pv": "t", "now": NOW}
        conn.execute(LISTING_SQL, row)
        with pytest.raises(IntegrityError):
            conn.execute(LISTING_SQL, row)
        conn.rollback()


@pytest.mark.parametrize(
    ("url", "ok"),
    [
        ("https://example.test/ban-nha-pho-pr123", True),
        ("https://example.test/sitemap-1.xml", True),
        ("https://cdn.example.test/anh/abc.JPG", False),
        ("https://cdn.example.test/anh/abc.webp?w=600", False),
        ("https://cdn.example.test/v/clip.mp4", False),
    ],
)
def test_fetch_log_rejects_media_urls(migrated, url, ok):
    with migrated.connect() as conn:
        src = _source_id(conn)
        job = _new_job(conn, src)
        stmt = text(
            "insert into fetch_log (job_id, source_id, url_hash, request_url, outcome) values (:j, :s, :h, :u, 'ok')"
        )
        params = {"j": job, "s": src, "h": "0" * 64, "u": url}
        if ok:
            conn.execute(stmt, params)
        else:
            with pytest.raises(IntegrityError):
                conn.execute(stmt, params)
        conn.rollback()


_SET_LISTING = "update listings set {col} = :v where listing_id = :lid"
_SET_JOB = "update ingestion_jobs set {col} = cast(:v as {typ}) where job_id = :jid"
_ADD_FEATURE = (
    "insert into listing_features (listing_id, feature_name, value, provenance, extractor_version)"
    " values (:lid, 'legal_status', cast(:v as jsonb), 'INFERRED', 't')"
)
_ADD_ISSUE = (
    "insert into data_quality_issues (entity_type, entity_id, issue_code, severity, details)"
    " values ('listing', 'x', 'test', 'info', cast(:v as jsonb))"
)


@pytest.mark.parametrize(
    ("sql", "value", "ok"),
    [
        # price_raw: chuỗi giá ngắn, không lẫn SĐT hay lời liên hệ
        (_SET_LISTING.format(col="price_raw"), "5,2 tỷ", True),
        (_SET_LISTING.format(col="price_raw"), "5.200.000.000", True),
        (_SET_LISTING.format(col="price_raw"), "5,2 tỷ LH 0901234567", False),
        (_SET_LISTING.format(col="price_raw"), "thỏa thuận zalo", False),
        # source_url: không phải URL ảnh
        (_SET_LISTING.format(col="source_url"), "https://cdn.example.test/a.png", False),
        # error_summary: ngắn, không chứa SĐT
        (_SET_JOB.format(col="error_summary", typ="text"), "ValueError: thiếu giá", True),
        (_SET_JOB.format(col="error_summary", typ="text"), "x" * 1001, False),
        (_SET_JOB.format(col="error_summary", typ="text"), "input_value='gọi 0901234567'", False),
        # checkpoint: object nhỏ; giá tiền 11 chữ số không bị nhầm là SĐT
        (_SET_JOB.format(col="checkpoint", typ="jsonb"), '{"cursor": 12, "last_price": 10000000000}', True),
        (_SET_JOB.format(col="checkpoint", typ="jsonb"), "[1, 2]", False),
        (_SET_JOB.format(col="checkpoint", typ="jsonb"), '{"urls": "' + "a" * 3000 + '"}', False),
        # listing_features.value: giá trị nguyên tử ngắn
        (_ADD_FEATURE, "3.5", True),
        (_ADD_FEATURE, '"sổ riêng"', True),
        (_ADD_FEATURE, '"' + "mô tả dài " * 10 + '"', False),
        (_ADD_FEATURE, '{"a": 1}', False),
        # data_quality_issues.details: object nhỏ, không chứa SĐT
        (_ADD_ISSUE, '{"asking_price_vnd": 10000000000}', True),
        (_ADD_ISSUE, '{"note": "+84901234567"}', False),
    ],
)
def test_free_text_columns_reject_leaks(migrated, sql, value, ok):
    """CHECK chống rò nội dung trang / SĐT qua cột chữ tự do và jsonb."""
    with migrated.connect() as conn:
        src = _source_id(conn)
        conn.execute(LISTING_SQL, {"src": src, "sid": "leak-1", "tt": "sale", "pv": "t", "now": NOW})
        lid = conn.execute(text("select listing_id from listings where source_listing_id = 'leak-1'")).scalar_one()
        jid = _new_job(conn, src)
        params = {"v": value, "lid": lid, "jid": jid}
        if ok:
            conn.execute(text(sql), params)
        else:
            with pytest.raises(IntegrityError):
                conn.execute(text(sql), params)
        conn.rollback()


def test_downgrade_0002_then_upgrade(migrated):
    """Chạy cuối file: downgrade -1 xóa bảng tin đăng, upgrade head tạo lại."""
    _alembic("downgrade", "-1")
    assert "listings" not in inspect(create_engine(DB_URL)).get_table_names()
    _alembic("upgrade", "head")
    assert "listings" in inspect(create_engine(DB_URL)).get_table_names()
