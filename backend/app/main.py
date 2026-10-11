from fastapi import Depends, FastAPI, Query
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.contracts import load_sources
from app.db.models import AdminUnit, AdminUnitMapping
from app.db.session import get_session
from ingestion.normalize.admin_units import resolve_ward

app = FastAPI(
    title="AI Property Intelligence Vietnam",
    version="0.1.0",
    description="API nội bộ cho dự án nghiên cứu định giá và độ uy tín tin đăng nhà phố (Quận 9 cũ, TP.HCM).",
)


@app.get("/health")
def health(session: Session = Depends(get_session)) -> dict:
    db_ok = session.execute(text("select 1")).scalar() == 1
    exts = (
        session.execute(text("select extname from pg_extension where extname in ('postgis','vector','pg_trgm')"))
        .scalars()
        .all()
    )
    return {"status": "ok" if db_ok else "degraded", "db": db_ok, "extensions": sorted(exts)}


@app.get("/reference/wards")
def wards(session: Session = Depends(get_session)) -> list[dict]:
    units = session.execute(select(AdminUnit).order_by(AdminUnit.name)).scalars().all()
    maps = session.execute(select(AdminUnitMapping)).scalars().all()
    return [
        {
            "slug": u.slug,
            "name": u.name,
            "legal_basis": u.legal_basis,
            "old_wards": sorted(
                {
                    m.old_ward_name + (" (một phần)" if m.mapping_type == "partial" else "")
                    for m in maps
                    if m.new_ward_slug == u.slug
                }
            ),
        }
        for u in units
    ]


@app.get("/reference/resolve-ward")
def resolve(address: str = Query(..., min_length=3), context: str = "") -> dict:
    r = resolve_ward(address, context_text=context)
    return r.__dict__ | {"resolved": r.resolved}


@app.get("/admin/sources")
def sources() -> list[dict]:
    reg = load_sources()
    out = []
    for s in reg.sources:
        ok, reason = s.can_crawl()
        out.append(
            {
                "id": s.id,
                "name": s.name,
                "tier": s.tier,
                "permission_level": s.permission_level,
                "allow_training": s.allow_training,
                "status": s.status,
                "can_crawl": ok,
                "gate_reason": reason,
            }
        )
    return out
