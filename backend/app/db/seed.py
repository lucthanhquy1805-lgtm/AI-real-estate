"""Nạp dữ liệu tham chiếu vào DB: nguồn (sources.yaml) và địa giới (hcm_q9_ward_mapping.csv).

Chạy:  python -m app.db.seed
Idempotent: chạy lại nhiều lần không tạo bản ghi trùng.
"""

from datetime import date

from sqlalchemy import case, delete
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.contracts import SourceStatus, load_sources, load_ward_mapping
from app.db.models import AdminUnit, AdminUnitMapping, DataSource
from app.db.session import get_engine

NQ_1685 = "Nghị quyết 1685/NQ-UBTVQH15 (16/6/2025)"


def seed(session: Session) -> dict[str, int]:
    reg = load_sources()
    for s in reg.sources:
        values = dict(
            source_id=s.id,
            name=s.name,
            base_url=s.base_url,
            tier=s.tier,
            permission_level=s.permission_level.value,
            allow_training=s.allow_training,
            status=s.status.value,
            min_delay_seconds=s.min_delay_seconds,
            license=s.license,
            reviewed_at=s.reviewed_at,
            next_review_at=s.next_review_at,
            notes=s.notes,
        )
        stmt = insert(DataSource).values(**values)
        # Seed chỉ được hạ trạng thái, không bao giờ mở lại nguồn đang paused/blocked trong DB
        # (có thể do crawler tự pause khi bị chặn). Mở lại phải là thao tác có chủ đích (T0.6).
        # Thứ tự nghiêm: active < paused < blocked. Giữ blocked; paused không bị nâng lên active.
        status = case(
            (DataSource.status == SourceStatus.BLOCKED.value, DataSource.status),
            (
                (DataSource.status == SourceStatus.PAUSED.value) & (stmt.excluded.status == SourceStatus.ACTIVE.value),
                DataSource.status,
            ),
            else_=stmt.excluded.status,
        )
        session.execute(stmt.on_conflict_do_update(index_elements=["source_id"], set_={**values, "status": status}))

    rows = load_ward_mapping()
    for slug, name in sorted({(r.new_ward_slug, r.new_ward_name) for r in rows}):
        values = dict(
            slug=f"hcm.{slug}",
            name=name,
            level="ward",
            province_slug="hcm",
            effective_from=date(2025, 7, 1),
            legal_basis=NQ_1685,
            in_research_scope=True,
        )
        stmt = insert(AdminUnit).values(**values)
        session.execute(stmt.on_conflict_do_update(index_elements=["slug"], set_=values))

    session.execute(delete(AdminUnitMapping))
    for r in rows:
        session.add(
            AdminUnitMapping(
                old_ward_name=r.old_ward_name,
                old_district_pre2021=r.old_district_pre2021,
                old_city_2021_2025=r.old_city_2021_2025,
                new_ward_slug=f"hcm.{r.new_ward_slug}",
                mapping_type=r.mapping_type,
                note=r.note or None,
            )
        )
    session.commit()
    return {"sources": len(reg.sources), "wards": len({r.new_ward_slug for r in rows}), "mappings": len(rows)}


if __name__ == "__main__":
    with Session(get_engine()) as s:
        print(seed(s))
