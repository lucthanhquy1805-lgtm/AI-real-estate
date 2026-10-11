"""Bảng của Sprint 0: nguồn dữ liệu và địa giới hành chính.
Bảng tin đăng (listings, observations, ...) được thêm ở migration W3."""

from datetime import date, datetime

from geoalchemy2 import Geometry
from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class DataSource(Base):
    __tablename__ = "data_sources"

    source_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    base_url: Mapped[str | None] = mapped_column(String(500))
    tier: Mapped[int] = mapped_column(Integer)
    permission_level: Mapped[str] = mapped_column(String(32))
    allow_training: Mapped[bool] = mapped_column(Boolean)
    status: Mapped[str] = mapped_column(String(16))
    min_delay_seconds: Mapped[float | None] = mapped_column(Float)
    license: Mapped[str | None] = mapped_column(String(200))
    reviewed_at: Mapped[date | None] = mapped_column(Date)
    next_review_at: Mapped[date | None] = mapped_column(Date)
    robots_snapshot_ref: Mapped[str | None] = mapped_column(String(500))
    tos_snapshot_ref: Mapped[str | None] = mapped_column(String(500))
    notes: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class AdminUnit(Base):
    """Đơn vị hành chính hiện hành (cấp xã/phường sau 01/07/2025)."""

    __tablename__ = "admin_units"

    slug: Mapped[str] = mapped_column(String(64), primary_key=True)  # "hcm.long_binh"
    name: Mapped[str] = mapped_column(String(120))
    level: Mapped[str] = mapped_column(String(16))  # "ward"
    province_slug: Mapped[str] = mapped_column(String(32))  # "hcm"
    official_code: Mapped[str | None] = mapped_column(String(16))  # TODO: mã chính thức
    effective_from: Mapped[date] = mapped_column(Date)
    legal_basis: Mapped[str] = mapped_column(String(200))
    in_research_scope: Mapped[bool] = mapped_column(Boolean, default=True)


class AdminUnitMapping(Base):
    """Ánh xạ phường cũ -> phường mới."""

    __tablename__ = "admin_unit_mapping"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    old_ward_name: Mapped[str] = mapped_column(String(120), index=True)
    old_district_pre2021: Mapped[str] = mapped_column(String(120))
    old_city_2021_2025: Mapped[str] = mapped_column(String(120))
    new_ward_slug: Mapped[str] = mapped_column(ForeignKey("admin_units.slug"))
    mapping_type: Mapped[str] = mapped_column(String(16))  # full | partial
    note: Mapped[str | None] = mapped_column(Text)


class WardBoundary(Base):
    __tablename__ = "ward_boundaries"

    slug: Mapped[str] = mapped_column(ForeignKey("admin_units.slug"), primary_key=True)
    geom = mapped_column(Geometry("MULTIPOLYGON", srid=4326, spatial_index=True), nullable=False)
    source: Mapped[str] = mapped_column(String(300))
    license: Mapped[str | None] = mapped_column(String(200))
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
