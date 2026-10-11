"""Sprint 0: extensions, data_sources, admin_units, admin_unit_mapping, ward_boundaries

Revision ID: 0001
Revises:
Create Date: 2026-10-10
"""

import geoalchemy2
import sqlalchemy as sa

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    op.create_table(
        "data_sources",
        sa.Column("source_id", sa.String(64), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("base_url", sa.String(500)),
        sa.Column("tier", sa.Integer, nullable=False),
        sa.Column("permission_level", sa.String(32), nullable=False),
        sa.Column("allow_training", sa.Boolean, nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("min_delay_seconds", sa.Float),
        sa.Column("license", sa.String(200)),
        sa.Column("reviewed_at", sa.Date),
        sa.Column("next_review_at", sa.Date),
        sa.Column("robots_snapshot_ref", sa.String(500)),
        sa.Column("tos_snapshot_ref", sa.String(500)),
        sa.Column("notes", sa.Text),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("tier between 1 and 3", name="ck_sources_tier"),
        sa.CheckConstraint(
            "permission_level in ('blocked','pending','manual_only','approved_facts_only','approved_licensed')",
            name="ck_sources_permission",
        ),
        sa.CheckConstraint("status in ('active','paused','blocked')", name="ck_sources_status"),
    )

    op.create_table(
        "admin_units",
        sa.Column("slug", sa.String(64), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("level", sa.String(16), nullable=False),
        sa.Column("province_slug", sa.String(32), nullable=False),
        sa.Column("official_code", sa.String(16)),
        sa.Column("effective_from", sa.Date, nullable=False),
        sa.Column("legal_basis", sa.String(200), nullable=False),
        sa.Column("in_research_scope", sa.Boolean, nullable=False, server_default=sa.true()),
    )

    op.create_table(
        "admin_unit_mapping",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("old_ward_name", sa.String(120), nullable=False),
        sa.Column("old_district_pre2021", sa.String(120), nullable=False),
        sa.Column("old_city_2021_2025", sa.String(120), nullable=False),
        sa.Column("new_ward_slug", sa.String(64), sa.ForeignKey("admin_units.slug"), nullable=False),
        sa.Column("mapping_type", sa.String(16), nullable=False),
        sa.Column("note", sa.Text),
        sa.CheckConstraint("mapping_type in ('full','partial')", name="ck_mapping_type"),
    )
    op.create_index("ix_admin_unit_mapping_old_ward_name", "admin_unit_mapping", ["old_ward_name"])

    op.create_table(
        "ward_boundaries",
        sa.Column("slug", sa.String(64), sa.ForeignKey("admin_units.slug"), primary_key=True),
        sa.Column("geom", geoalchemy2.Geometry("MULTIPOLYGON", srid=4326, spatial_index=False), nullable=False),
        sa.Column("source", sa.String(300), nullable=False),
        sa.Column("license", sa.String(200)),
        sa.Column("fetched_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_ward_boundaries_geom", "ward_boundaries", ["geom"], postgresql_using="gist")


def downgrade() -> None:
    op.drop_table("ward_boundaries")
    op.drop_table("admin_unit_mapping")
    op.drop_table("admin_units")
    op.drop_table("data_sources")
