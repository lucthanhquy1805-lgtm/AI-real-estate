"""Compliance test cho schema (metadata ORM, không cần DB).

(1) Không bảng nào có cột thuộc nhóm CONTENT / MEDIA / PERSONAL.
(2) Mọi cột dữ liệu nguồn của các bảng tin đăng phải khai báo trong field_policy.yaml với store=true.
(3) Cột provenance của listings phải NOT NULL.
"""

import re

from app.db.models import Base
from ingestion.core.policy import FieldPolicy, UnknownFieldError

# Bắt cả tên cột "gần giống" mà chưa khai báo trong field_policy
SUSPICIOUS = re.compile(r"(description|^title$|phone|email|avatar|image_url|image_bytes|photo|house_number)")

# Cột kỹ thuật theo từng bảng (id, khóa ngoại, thời điểm/phiên bản hệ thống, trạng thái nội bộ): không cần khai báo.
# Miễn trừ theo cặp (bảng, cột) để một cột trùng tên ở bảng khác vẫn bị kiểm tra.
# Mọi cột còn lại của các bảng này phải có trong field_policy.yaml với store=true.
TECHNICAL_COLUMNS: dict[str, set[str]] = {
    "ingestion_jobs": {
        "job_id",
        "source_id",
        "kind",
        "status",
        "started_at",
        "finished_at",
        "fetched_count",
        "parsed_count",
        "error_count",
        "blocked_count",
        "parser_version",
        "checkpoint",  # jsonb nhỏ, có CHECK kích thước và chặn SĐT
        "error_summary",  # có CHECK độ dài và chặn SĐT
        "created_at",
    },
    "fetch_log": {"id", "job_id", "source_id", "http_status", "latency_ms", "fetched_at", "outcome"},
    "listings": {
        "listing_id",
        "source_id",
        "first_seen_at",
        "last_seen_at",
        "listing_status",
        "out_of_scope",
        "parser_version",
        "collected_at",
    },
    # Tên trường nằm trong feature_name, được kiểm tra ở tầng persist; value có CHECK giá trị ngắn
    "listing_features": {
        "listing_id",
        "feature_name",
        "value",
        "provenance",
        "confidence",
        "extractor_version",
        "extracted_at",
    },
    "listing_observations": {"listing_id", "observed_at", "listing_status", "parser_version"},
    "data_quality_issues": {
        "id",
        "entity_type",
        "entity_id",
        "issue_code",
        "severity",
        "details",  # jsonb nhỏ, có CHECK kích thước và chặn SĐT
        "detected_at",
        "resolution_status",
    },
}

PROVENANCE_COLUMNS = ("source_id", "parser_version", "collected_at")


def test_no_forbidden_columns_in_schema():
    forbidden = FieldPolicy.load().forbidden_fields()
    offenders = []
    for table in Base.metadata.sorted_tables:
        for col in table.columns:
            if col.name in forbidden or SUSPICIOUS.search(col.name):
                offenders.append(f"{table.name}.{col.name}")
    assert not offenders, f"Cột vi phạm field policy: {offenders}"


def test_source_data_columns_are_declared_and_storable():
    policy = FieldPolicy.load()
    tables = {t.name: t for t in Base.metadata.sorted_tables}
    assert TECHNICAL_COLUMNS.keys() <= tables.keys()
    problems = []
    for name, technical in sorted(TECHNICAL_COLUMNS.items()):
        for col in tables[name].columns:
            if col.name in technical:
                continue
            try:
                if not policy.can_store(col.name):
                    problems.append(f"{name}.{col.name}: store=false")
            except UnknownFieldError:
                problems.append(f"{name}.{col.name}: chưa khai báo trong field_policy.yaml")
    assert not problems, f"Cột dữ liệu nguồn không hợp lệ: {problems}"


def test_listings_provenance_not_null():
    listings = Base.metadata.tables["listings"]
    nullable = [c for c in PROVENANCE_COLUMNS if listings.c[c].nullable]
    assert not nullable, f"Cột provenance phải NOT NULL: {nullable}"
