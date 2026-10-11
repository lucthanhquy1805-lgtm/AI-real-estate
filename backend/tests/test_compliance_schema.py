"""Compliance test (1): không bảng nào trong DB có cột thuộc nhóm CONTENT / MEDIA / PERSONAL."""

import re

from app.db.models import Base
from ingestion.core.policy import FieldPolicy

# Bắt cả tên cột "gần giống" mà chưa khai báo trong field_policy
SUSPICIOUS = re.compile(r"(description|^title$|phone|email|avatar|image_url|image_bytes|photo|house_number)")


def test_no_forbidden_columns_in_schema():
    forbidden = FieldPolicy.load().forbidden_fields()
    offenders = []
    for table in Base.metadata.sorted_tables:
        for col in table.columns:
            if col.name in forbidden or SUSPICIOUS.search(col.name):
                offenders.append(f"{table.name}.{col.name}")
    assert not offenders, f"Cột vi phạm field policy: {offenders}"
