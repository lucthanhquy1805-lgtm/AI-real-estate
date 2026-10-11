"""Field-level data policy (FR-17). Đọc packages/contracts/field_policy.yaml.

Mọi bản ghi trước khi ghi vào DB phải đi qua `FieldPolicy.filter_for_storage`.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from app.config import get_settings


class UnknownFieldError(KeyError):
    """Trường chưa được khai báo trong field_policy.yaml — bắt buộc khai báo trước khi dùng."""


@dataclass(frozen=True)
class ClassRule:
    store: bool
    display: bool


class FieldPolicy:
    def __init__(self, classes: dict[str, ClassRule], fields: dict[str, str]):
        unknown = {c for c in fields.values() if c not in classes}
        if unknown:
            raise ValueError(f"field_policy: lớp không tồn tại {unknown}")
        self.classes = classes
        self.fields = fields

    @classmethod
    def load(cls, path: Path | None = None) -> FieldPolicy:
        path = path or get_settings().contracts_dir / "field_policy.yaml"
        with open(path, encoding="utf-8") as f:
            raw = yaml.safe_load(f)
        classes = {k: ClassRule(**v) for k, v in raw["classes"].items()}
        return cls(classes, raw["fields"])

    def class_of(self, field: str) -> str:
        try:
            return self.fields[field]
        except KeyError:
            raise UnknownFieldError(f"Trường '{field}' chưa khai báo trong field_policy.yaml") from None

    def can_store(self, field: str) -> bool:
        return self.classes[self.class_of(field)].store

    def can_display(self, field: str) -> bool:
        return self.classes[self.class_of(field)].display

    def forbidden_fields(self) -> set[str]:
        return {f for f, c in self.fields.items() if not self.classes[c].store}

    def filter_for_storage(self, record: dict) -> tuple[dict, list[str]]:
        """Trả về (bản ghi chỉ gồm trường được lưu, danh sách trường bị loại).

        Trường chưa khai báo -> UnknownFieldError (fail closed, không âm thầm lưu)."""
        kept, dropped = {}, []
        for k, v in record.items():
            if self.can_store(k):
                kept[k] = v
            else:
                dropped.append(k)
        return kept, dropped
