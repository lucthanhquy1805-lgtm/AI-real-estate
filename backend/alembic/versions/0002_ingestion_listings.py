"""Ingestion và tin đăng: ingestion_jobs, fetch_log, listings, listing_features, listing_observations,
data_quality_issues

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-11
"""

import geoalchemy2
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

# Viết cố định ở đây (không import từ models) để migration không đổi khi models đổi.
HEX64 = "'^[0-9a-f]{64}$'"
LISTING_STATUSES = "('active','not_seen','removed')"
MEDIA_URL_PATTERN = r"'\.(jpe?g|png|webp|gif|avif|bmp|svg|mp4|webm)(\?|#|$)'"
# Dãy số dạng SĐT Việt Nam (+84 hoặc 0, theo sau 9 chữ số), không dính chữ số hai bên để tránh khớp nhầm giá tiền
PHONE_PATTERN = r"'(^|\D)(\+84|0)\d{9}(\D|$)'"
# Cột jsonb tự do: chỉ là object nhỏ, không chứa SĐT
MAX_JSON_BYTES = 2048


def _tstz(name: str, nullable: bool = True, now: bool = False) -> sa.Column:
    return sa.Column(
        name,
        sa.DateTime(timezone=True),
        nullable=nullable,
        server_default=sa.func.now() if now else None,
    )


def upgrade() -> None:
    op.create_table(
        "ingestion_jobs",
        sa.Column("job_id", pg.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("source_id", sa.String(64), sa.ForeignKey("data_sources.source_id"), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="queued"),
        _tstz("started_at"),
        _tstz("finished_at"),
        sa.Column("fetched_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("parsed_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("error_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("blocked_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("parser_version", sa.String(32), nullable=False),
        sa.Column("checkpoint", pg.JSONB),
        sa.Column("error_summary", sa.Text),
        _tstz("created_at", nullable=False, now=True),
        sa.CheckConstraint("kind in ('discover','fetch','full')", name="ck_ingestion_jobs_kind"),
        sa.CheckConstraint(
            "status in ('queued','running','succeeded','failed','aborted_blocked')", name="ck_ingestion_jobs_status"
        ),
        sa.CheckConstraint("finished_at >= started_at", name="ck_ingestion_jobs_time"),
        sa.CheckConstraint(
            "fetched_count >= 0 and parsed_count >= 0 and error_count >= 0 and blocked_count >= 0",
            name="ck_ingestion_jobs_counts",
        ),
        sa.CheckConstraint(
            f"length(error_summary) <= 1000 and error_summary !~ {PHONE_PATTERN}",
            name="ck_ingestion_jobs_error_summary",
        ),
        sa.CheckConstraint(
            f"jsonb_typeof(checkpoint) = 'object' and pg_column_size(checkpoint) <= {MAX_JSON_BYTES}"
            f" and checkpoint::text !~ {PHONE_PATTERN}",
            name="ck_ingestion_jobs_checkpoint",
        ),
    )
    op.create_index("ix_ingestion_jobs_source_created", "ingestion_jobs", ["source_id", "created_at"])
    op.create_index("ix_ingestion_jobs_status", "ingestion_jobs", ["status"])

    op.create_table(
        "fetch_log",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column(
            "job_id", pg.UUID(as_uuid=True), sa.ForeignKey("ingestion_jobs.job_id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("source_id", sa.String(64), sa.ForeignKey("data_sources.source_id"), nullable=False),
        sa.Column("url_hash", sa.String(64), nullable=False),
        sa.Column("request_url", sa.String(2000)),
        sa.Column("http_status", sa.SmallInteger),
        sa.Column("latency_ms", sa.Integer),
        _tstz("fetched_at", nullable=False, now=True),
        sa.Column("outcome", sa.String(20), nullable=False),
        sa.CheckConstraint(f"url_hash ~ {HEX64}", name="ck_fetch_log_url_hash"),
        sa.CheckConstraint(f"request_url !~* {MEDIA_URL_PATTERN}", name="ck_fetch_log_request_url"),
        sa.CheckConstraint("latency_ms >= 0", name="ck_fetch_log_latency"),
        sa.CheckConstraint(
            "outcome in ('ok','blocked','error','skipped_robots','skipped_policy')", name="ck_fetch_log_outcome"
        ),
    )
    op.create_index("ix_fetch_log_source_fetched", "fetch_log", ["source_id", "fetched_at"])
    op.create_index("ix_fetch_log_url_hash", "fetch_log", ["url_hash"])
    op.create_index("ix_fetch_log_job_id", "fetch_log", ["job_id"])

    op.create_table(
        "listings",
        sa.Column("listing_id", pg.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("source_id", sa.String(64), sa.ForeignKey("data_sources.source_id"), nullable=False),
        sa.Column("source_listing_id", sa.String(128), nullable=False),
        sa.Column("source_url", sa.String(2000), nullable=False),
        sa.Column("transaction_type", sa.String(8), nullable=False),
        sa.Column("property_type", sa.String(20), nullable=False),
        sa.Column("asking_price_vnd", sa.BigInteger),
        sa.Column("price_raw", sa.String(64)),
        sa.Column("land_area_sqm", sa.Numeric(10, 2)),
        sa.Column("floor_area_sqm", sa.Numeric(10, 2)),
        sa.Column("floors", sa.SmallInteger),
        sa.Column("bedrooms", sa.SmallInteger),
        sa.Column("bathrooms", sa.SmallInteger),
        sa.Column("direction", sa.String(4)),
        sa.Column("ward_name_old", sa.String(120)),
        sa.Column("district_alias", sa.String(64)),
        sa.Column("ward_slug_new", sa.String(64), sa.ForeignKey("admin_units.slug")),
        sa.Column("ward_method", sa.String(8)),
        sa.Column("ward_confidence", sa.REAL),
        sa.Column("ward_flags", pg.ARRAY(sa.Text), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("geo_point", geoalchemy2.Geometry("POINT", srid=4326, spatial_index=False)),
        sa.Column("price_per_sqm_vnd", sa.BigInteger),
        sa.Column("poster_pseudonym", sa.String(64)),
        _tstz("posted_at"),
        _tstz("first_seen_at", nullable=False),
        _tstz("last_seen_at", nullable=False),
        sa.Column("listing_status", sa.String(12), nullable=False, server_default="active"),
        sa.Column("out_of_scope", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("parser_version", sa.String(32), nullable=False),
        _tstz("collected_at", nullable=False),
        sa.UniqueConstraint("source_id", "source_listing_id", name="uq_listings_source_listing"),
        sa.CheckConstraint("transaction_type in ('sale','rent')", name="ck_listings_transaction_type"),
        sa.CheckConstraint(f"source_url !~* {MEDIA_URL_PATTERN}", name="ck_listings_source_url"),
        # price_raw chỉ là chuỗi giá ngắn (vd "5,2 tỷ"), không được lẫn SĐT hay lời liên hệ
        sa.CheckConstraint(
            r"price_raw !~ '\d{9,}' and price_raw !~* '(@|\mlh\M|zalo|liên hệ)'",
            name="ck_listings_price_raw",
        ),
        sa.CheckConstraint(
            "property_type in ('townhouse','apartment','land','villa','shophouse','other')",
            name="ck_listings_property_type",
        ),
        sa.CheckConstraint("asking_price_vnd > 0", name="ck_listings_asking_price"),
        sa.CheckConstraint("land_area_sqm > 0 and floor_area_sqm > 0", name="ck_listings_area"),
        sa.CheckConstraint("floors >= 0 and bedrooms >= 0 and bathrooms >= 0", name="ck_listings_counts"),
        sa.CheckConstraint("direction in ('n','ne','e','se','s','sw','w','nw')", name="ck_listings_direction"),
        sa.CheckConstraint("ward_method in ('text','geo')", name="ck_listings_ward_method"),
        sa.CheckConstraint("ward_confidence between 0 and 1", name="ck_listings_ward_confidence"),
        sa.CheckConstraint("price_per_sqm_vnd > 0", name="ck_listings_price_per_sqm"),
        sa.CheckConstraint(f"poster_pseudonym ~ {HEX64}", name="ck_listings_poster_pseudonym"),
        sa.CheckConstraint("last_seen_at >= first_seen_at", name="ck_listings_seen"),
        sa.CheckConstraint(f"listing_status in {LISTING_STATUSES}", name="ck_listings_listing_status"),
    )
    op.create_index("ix_listings_ward_slug_new", "listings", ["ward_slug_new"])
    op.create_index("ix_listings_last_seen_at", "listings", ["last_seen_at"])
    op.create_index("ix_listings_poster_pseudonym", "listings", ["poster_pseudonym"])
    op.create_index("idx_listings_geo_point", "listings", ["geo_point"], postgresql_using="gist")

    op.create_table(
        "listing_features",
        sa.Column(
            "listing_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("listings.listing_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("feature_name", sa.String(64), primary_key=True),
        sa.Column("value", pg.JSONB, nullable=False),
        sa.Column("provenance", sa.String(16), nullable=False),
        sa.Column("confidence", sa.REAL),
        sa.Column("extractor_version", sa.String(32), nullable=False),
        _tstz("extracted_at", nullable=False, now=True),
        sa.CheckConstraint("provenance in ('SOURCE_REPORTED','INFERRED')", name="ck_listing_features_provenance"),
        sa.CheckConstraint("confidence between 0 and 1", name="ck_listing_features_confidence"),
        # value chỉ là giá trị nguyên tử ngắn, không phải đoạn văn
        sa.CheckConstraint(
            "jsonb_typeof(value) in ('number','boolean','string')"
            " and (jsonb_typeof(value) <> 'string' or length(value #>> '{}') <= 64)",
            name="ck_listing_features_value",
        ),
    )

    op.create_table(
        "listing_observations",
        sa.Column(
            "listing_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("listings.listing_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("observed_at", sa.DateTime(timezone=True), primary_key=True),
        sa.Column("asking_price_vnd", sa.BigInteger),
        sa.Column("listing_status", sa.String(12), nullable=False),
        sa.Column("changed_fields", pg.ARRAY(sa.Text), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("content_checksum", sa.String(64), nullable=False),
        sa.Column("parser_version", sa.String(32), nullable=False),
        sa.CheckConstraint("asking_price_vnd > 0", name="ck_listing_observations_price"),
        sa.CheckConstraint(f"listing_status in {LISTING_STATUSES}", name="ck_listing_observations_listing_status"),
        sa.CheckConstraint(f"content_checksum ~ {HEX64}", name="ck_listing_observations_checksum"),
    )

    op.create_table(
        "data_quality_issues",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("entity_type", sa.String(32), nullable=False),
        sa.Column("entity_id", sa.String(64), nullable=False),
        sa.Column("issue_code", sa.String(64), nullable=False),
        sa.Column("severity", sa.String(8), nullable=False),
        sa.Column("details", pg.JSONB),
        _tstz("detected_at", nullable=False, now=True),
        sa.Column("resolution_status", sa.String(12), nullable=False, server_default="open"),
        sa.CheckConstraint(
            "entity_type in ('listing','source','job','fetch')", name="ck_data_quality_issues_entity_type"
        ),
        sa.CheckConstraint("severity in ('info','warning','error')", name="ck_data_quality_issues_severity"),
        sa.CheckConstraint(
            "resolution_status in ('open','resolved','ignored')", name="ck_data_quality_issues_resolution_status"
        ),
        sa.CheckConstraint(
            f"jsonb_typeof(details) = 'object' and pg_column_size(details) <= {MAX_JSON_BYTES}"
            f" and details::text !~ {PHONE_PATTERN}",
            name="ck_data_quality_issues_details",
        ),
    )
    op.create_index("ix_data_quality_issues_entity", "data_quality_issues", ["entity_type", "entity_id"])
    op.create_index("ix_data_quality_issues_status_severity", "data_quality_issues", ["resolution_status", "severity"])


def downgrade() -> None:
    op.drop_table("listing_observations")
    op.drop_table("listing_features")
    op.drop_table("data_quality_issues")
    op.drop_table("listings")
    op.drop_table("fetch_log")
    op.drop_table("ingestion_jobs")
