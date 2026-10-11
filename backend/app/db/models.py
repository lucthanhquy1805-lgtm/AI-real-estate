"""Bảng dữ liệu của dự án.

- Migration 0001: nguồn dữ liệu và địa giới hành chính.
- Migration 0002: job thu thập, fetch log, tin đăng, đặc điểm, lịch sử quan sát, vấn đề chất lượng.

Cột lưu dữ liệu nguồn phải khai báo trong packages/contracts/field_policy.yaml (xem tests/test_compliance_schema.py).
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from geoalchemy2 import Geometry
from sqlalchemy import (
    REAL,
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Identity,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
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


# ---------------------------------------------------------------- migration 0002: ingestion và tin đăng
# Lưu ý: CHECK trong PostgreSQL coi NULL là đạt, nên cột nullable không cần "x is null or ...".

HEX64 = "'^[0-9a-f]{64}$'"
LISTING_STATUSES = "('active','not_seen','removed')"
# URL ảnh/video không bao giờ được lưu (field_policy: MEDIA)
MEDIA_URL_PATTERN = r"'\.(jpe?g|png|webp|gif|avif|bmp|svg|mp4|webm)(\?|#|$)'"
# Dãy số dạng SĐT Việt Nam (+84 hoặc 0, theo sau 9 chữ số), không dính chữ số hai bên để tránh khớp nhầm giá tiền
PHONE_PATTERN = r"'(^|\D)(\+84|0)\d{9}(\D|$)'"
# Cột jsonb tự do: chỉ là object nhỏ, không chứa SĐT
MAX_JSON_BYTES = 2048


class IngestionJob(Base):
    """Một lần chạy thu thập cho một nguồn."""

    __tablename__ = "ingestion_jobs"
    __table_args__ = (
        CheckConstraint("kind in ('discover','fetch','full')", name="ck_ingestion_jobs_kind"),
        CheckConstraint(
            "status in ('queued','running','succeeded','failed','aborted_blocked')", name="ck_ingestion_jobs_status"
        ),
        CheckConstraint("finished_at >= started_at", name="ck_ingestion_jobs_time"),
        CheckConstraint(
            "fetched_count >= 0 and parsed_count >= 0 and error_count >= 0 and blocked_count >= 0",
            name="ck_ingestion_jobs_counts",
        ),
        CheckConstraint(
            f"length(error_summary) <= 1000 and error_summary !~ {PHONE_PATTERN}",
            name="ck_ingestion_jobs_error_summary",
        ),
        CheckConstraint(
            f"jsonb_typeof(checkpoint) = 'object' and pg_column_size(checkpoint) <= {MAX_JSON_BYTES}"
            f" and checkpoint::text !~ {PHONE_PATTERN}",
            name="ck_ingestion_jobs_checkpoint",
        ),
        Index("ix_ingestion_jobs_source_created", "source_id", "created_at"),
        Index("ix_ingestion_jobs_status", "status"),
    )

    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    source_id: Mapped[str] = mapped_column(ForeignKey("data_sources.source_id"))
    kind: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(20), server_default="queued")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fetched_count: Mapped[int] = mapped_column(Integer, server_default="0")
    parsed_count: Mapped[int] = mapped_column(Integer, server_default="0")
    error_count: Mapped[int] = mapped_column(Integer, server_default="0")
    blocked_count: Mapped[int] = mapped_column(Integer, server_default="0")
    parser_version: Mapped[str] = mapped_column(String(32))
    checkpoint: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    error_summary: Mapped[str | None] = mapped_column(Text)  # chỉ lỗi kỹ thuật, không chép nội dung trang
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class FetchLog(Base):
    """Nhật ký từng request. Chỉ lưu URL trang tin/sitemap; URL ảnh/video bị CHECK chặn."""

    __tablename__ = "fetch_log"
    __table_args__ = (
        CheckConstraint(f"url_hash ~ {HEX64}", name="ck_fetch_log_url_hash"),
        CheckConstraint(f"request_url !~* {MEDIA_URL_PATTERN}", name="ck_fetch_log_request_url"),
        CheckConstraint("latency_ms >= 0", name="ck_fetch_log_latency"),
        CheckConstraint(
            "outcome in ('ok','blocked','error','skipped_robots','skipped_policy')", name="ck_fetch_log_outcome"
        ),
        Index("ix_fetch_log_source_fetched", "source_id", "fetched_at"),
        Index("ix_fetch_log_url_hash", "url_hash"),
        Index("ix_fetch_log_job_id", "job_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ingestion_jobs.job_id", ondelete="CASCADE"))
    source_id: Mapped[str] = mapped_column(ForeignKey("data_sources.source_id"))
    url_hash: Mapped[str] = mapped_column(String(64))
    request_url: Mapped[str | None] = mapped_column(String(2000))
    http_status: Mapped[int | None] = mapped_column(SmallInteger)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    outcome: Mapped[str] = mapped_column(String(20))


class Listing(Base):
    """Một dòng cho mỗi (nguồn, mã tin). Giá là giá rao, không phải giá giao dịch."""

    __tablename__ = "listings"
    __table_args__ = (
        UniqueConstraint("source_id", "source_listing_id", name="uq_listings_source_listing"),
        CheckConstraint("transaction_type in ('sale','rent')", name="ck_listings_transaction_type"),
        CheckConstraint(f"source_url !~* {MEDIA_URL_PATTERN}", name="ck_listings_source_url"),
        # price_raw chỉ là chuỗi giá ngắn (vd "5,2 tỷ"), không được lẫn SĐT hay lời liên hệ
        CheckConstraint(
            r"price_raw !~ '\d{9,}' and price_raw !~* '(@|\mlh\M|zalo|liên hệ)'",
            name="ck_listings_price_raw",
        ),
        CheckConstraint(
            "property_type in ('townhouse','apartment','land','villa','shophouse','other')",
            name="ck_listings_property_type",
        ),
        CheckConstraint("asking_price_vnd > 0", name="ck_listings_asking_price"),
        CheckConstraint("land_area_sqm > 0 and floor_area_sqm > 0", name="ck_listings_area"),
        CheckConstraint("floors >= 0 and bedrooms >= 0 and bathrooms >= 0", name="ck_listings_counts"),
        CheckConstraint("direction in ('n','ne','e','se','s','sw','w','nw')", name="ck_listings_direction"),
        CheckConstraint("ward_method in ('text','geo')", name="ck_listings_ward_method"),
        CheckConstraint("ward_confidence between 0 and 1", name="ck_listings_ward_confidence"),
        CheckConstraint("price_per_sqm_vnd > 0", name="ck_listings_price_per_sqm"),
        CheckConstraint(f"poster_pseudonym ~ {HEX64}", name="ck_listings_poster_pseudonym"),
        CheckConstraint("last_seen_at >= first_seen_at", name="ck_listings_seen"),
        CheckConstraint(f"listing_status in {LISTING_STATUSES}", name="ck_listings_listing_status"),
        Index("ix_listings_ward_slug_new", "ward_slug_new"),
        Index("ix_listings_last_seen_at", "last_seen_at"),
        Index("ix_listings_poster_pseudonym", "poster_pseudonym"),
    )

    listing_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    source_id: Mapped[str] = mapped_column(ForeignKey("data_sources.source_id"))
    source_listing_id: Mapped[str] = mapped_column(String(128))
    source_url: Mapped[str] = mapped_column(String(2000))
    transaction_type: Mapped[str] = mapped_column(String(8))
    property_type: Mapped[str] = mapped_column(String(20))
    asking_price_vnd: Mapped[int | None] = mapped_column(BigInteger)  # null nếu "thỏa thuận"
    price_raw: Mapped[str | None] = mapped_column(String(64))
    land_area_sqm: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    floor_area_sqm: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    floors: Mapped[int | None] = mapped_column(SmallInteger)
    bedrooms: Mapped[int | None] = mapped_column(SmallInteger)
    bathrooms: Mapped[int | None] = mapped_column(SmallInteger)
    direction: Mapped[str | None] = mapped_column(String(4))
    ward_name_old: Mapped[str | None] = mapped_column(String(120))
    district_alias: Mapped[str | None] = mapped_column(String(64))
    ward_slug_new: Mapped[str | None] = mapped_column(ForeignKey("admin_units.slug"))
    ward_method: Mapped[str | None] = mapped_column(String(8))
    ward_confidence: Mapped[float | None] = mapped_column(REAL)
    ward_flags: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default=text("'{}'"))
    geo_point = mapped_column(Geometry("POINT", srid=4326, spatial_index=True))  # làm tròn ~50–100 m
    price_per_sqm_vnd: Mapped[int | None] = mapped_column(BigInteger)
    poster_pseudonym: Mapped[str | None] = mapped_column(String(64))  # HMAC-SHA256, không bao giờ là SĐT
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    listing_status: Mapped[str] = mapped_column(String(12), server_default="active")
    out_of_scope: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    parser_version: Mapped[str] = mapped_column(String(32))
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ListingFeature(Base):
    """Đặc điểm trích từ tin. feature_name phải là trường store=true trong field_policy (kiểm tra ở tầng persist)."""

    __tablename__ = "listing_features"
    __table_args__ = (
        CheckConstraint("provenance in ('SOURCE_REPORTED','INFERRED')", name="ck_listing_features_provenance"),
        CheckConstraint("confidence between 0 and 1", name="ck_listing_features_confidence"),
        # value chỉ là giá trị nguyên tử ngắn, không phải đoạn văn
        CheckConstraint(
            "jsonb_typeof(value) in ('number','boolean','string')"
            " and (jsonb_typeof(value) <> 'string' or length(value #>> '{}') <= 64)",
            name="ck_listing_features_value",
        ),
    )

    listing_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("listings.listing_id", ondelete="CASCADE"), primary_key=True
    )
    feature_name: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[Any] = mapped_column(JSONB)
    provenance: Mapped[str] = mapped_column(String(16))
    confidence: Mapped[float | None] = mapped_column(REAL)
    extractor_version: Mapped[str] = mapped_column(String(32))
    extracted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ListingObservation(Base):
    """Lịch sử quan sát một tin: giá rao và trạng thái theo thời gian."""

    __tablename__ = "listing_observations"
    __table_args__ = (
        CheckConstraint("asking_price_vnd > 0", name="ck_listing_observations_price"),
        CheckConstraint(f"listing_status in {LISTING_STATUSES}", name="ck_listing_observations_listing_status"),
        CheckConstraint(f"content_checksum ~ {HEX64}", name="ck_listing_observations_checksum"),
    )

    listing_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("listings.listing_id", ondelete="CASCADE"), primary_key=True
    )
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    asking_price_vnd: Mapped[int | None] = mapped_column(BigInteger)
    listing_status: Mapped[str] = mapped_column(String(12))
    changed_fields: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default=text("'{}'"))
    content_checksum: Mapped[str] = mapped_column(String(64))
    parser_version: Mapped[str] = mapped_column(String(32))


class DataQualityIssue(Base):
    """Vấn đề chất lượng dữ liệu. details chỉ chứa tên trường và giá trị FACT, không chép nội dung trang."""

    __tablename__ = "data_quality_issues"
    __table_args__ = (
        CheckConstraint("entity_type in ('listing','source','job','fetch')", name="ck_data_quality_issues_entity_type"),
        CheckConstraint("severity in ('info','warning','error')", name="ck_data_quality_issues_severity"),
        CheckConstraint(
            "resolution_status in ('open','resolved','ignored')", name="ck_data_quality_issues_resolution_status"
        ),
        CheckConstraint(
            f"jsonb_typeof(details) = 'object' and pg_column_size(details) <= {MAX_JSON_BYTES}"
            f" and details::text !~ {PHONE_PATTERN}",
            name="ck_data_quality_issues_details",
        ),
        Index("ix_data_quality_issues_entity", "entity_type", "entity_id"),
        Index("ix_data_quality_issues_status_severity", "resolution_status", "severity"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(32))
    entity_id: Mapped[str] = mapped_column(String(64))
    issue_code: Mapped[str] = mapped_column(String(64))
    severity: Mapped[str] = mapped_column(String(8))
    details: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    resolution_status: Mapped[str] = mapped_column(String(12), server_default="open")
