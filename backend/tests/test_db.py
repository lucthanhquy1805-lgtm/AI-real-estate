"""Test cần PostgreSQL + PostGIS + pgvector. Bỏ qua nếu không có TEST_DATABASE_URL."""

import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

DB_URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = [pytest.mark.db, pytest.mark.skipif(not DB_URL, reason="TEST_DATABASE_URL chưa đặt")]
BACKEND = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def migrated():
    env = {**os.environ, "DATABASE_URL": DB_URL}

    def run(*args: str) -> None:
        p = subprocess.run(
            [sys.executable, "-m", "alembic", *args],
            cwd=BACKEND,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        assert p.returncode == 0, f"alembic {' '.join(args)} lỗi:\n{p.stdout}\n{p.stderr}"

    run("downgrade", "base")
    run("upgrade", "head")
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
