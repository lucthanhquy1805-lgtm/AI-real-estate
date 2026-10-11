"""Đọc và kiểm tra các file hợp đồng dữ liệu: sources.yaml, field_policy.yaml, bảng ánh xạ phường."""

from __future__ import annotations

import csv
from datetime import date
from enum import StrEnum
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, model_validator

from app.config import get_settings


class PermissionLevel(StrEnum):
    BLOCKED = "blocked"
    PENDING = "pending"
    MANUAL_ONLY = "manual_only"
    APPROVED_FACTS_ONLY = "approved_facts_only"
    APPROVED_LICENSED = "approved_licensed"


class SourceStatus(StrEnum):
    ACTIVE = "active"
    PAUSED = "paused"
    BLOCKED = "blocked"


CRAWLABLE_LEVELS = {PermissionLevel.APPROVED_FACTS_ONLY, PermissionLevel.APPROVED_LICENSED}


class SourceDefaults(BaseModel):
    user_agent: str
    min_delay_seconds: float = Field(ge=1)
    max_concurrency_per_domain: int = Field(ge=1, le=2)
    max_pages_per_day: int = Field(ge=1)
    crawl_window_local: str


class Source(BaseModel):
    id: str = Field(pattern=r"^[a-z0-9_]+$")
    name: str
    base_url: str | None = None
    tier: int = Field(ge=1, le=3)
    permission_level: PermissionLevel
    allow_training: bool
    status: SourceStatus
    discovery: str | None = None
    sitemaps: list[str] = []
    min_delay_seconds: float | None = Field(default=None, ge=1)
    license: str | None = None
    reviewed_at: date | None = None
    next_review_at: date | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def _check(self) -> Source:
        if self.permission_level in CRAWLABLE_LEVELS and self.tier in (1, 2):
            if not self.base_url:
                raise ValueError(f"{self.id}: nguồn được crawl phải có base_url")
            if not self.reviewed_at:
                raise ValueError(f"{self.id}: nguồn được crawl phải có reviewed_at (ngày rà soát điều khoản)")
        if self.permission_level == PermissionLevel.BLOCKED and self.status != SourceStatus.BLOCKED:
            raise ValueError(f"{self.id}: permission blocked thì status phải là blocked")
        return self

    def can_crawl(self, today: date | None = None) -> tuple[bool, str]:
        """Policy gate (ING-02). Trả về (được phép?, lý do)."""
        if self.permission_level not in CRAWLABLE_LEVELS:
            return False, f"permission_level={self.permission_level}"
        if self.status != SourceStatus.ACTIVE:
            return False, f"status={self.status}"
        today = today or date.today()
        if self.next_review_at and today > self.next_review_at:
            return False, f"quá hạn rà soát điều khoản ({self.next_review_at})"
        return True, "ok"


class SourceRegistry(BaseModel):
    version: int
    defaults: SourceDefaults
    sources: list[Source]

    @model_validator(mode="after")
    def _unique(self) -> SourceRegistry:
        ids = [s.id for s in self.sources]
        dup = {i for i in ids if ids.count(i) > 1}
        if dup:
            raise ValueError(f"source id trùng: {dup}")
        return self

    def get(self, source_id: str) -> Source:
        for s in self.sources:
            if s.id == source_id:
                return s
        raise KeyError(source_id)

    def delay_for(self, source_id: str) -> float:
        s = self.get(source_id)
        return max(s.min_delay_seconds or 0, self.defaults.min_delay_seconds)

    def training_source_ids(self) -> set[str]:
        return {s.id for s in self.sources if s.allow_training}


def load_sources(path: Path | None = None) -> SourceRegistry:
    path = path or get_settings().contracts_dir / "sources.yaml"
    with open(path, encoding="utf-8") as f:
        return SourceRegistry.model_validate(yaml.safe_load(f))


class WardMappingRow(BaseModel):
    old_ward_name: str
    old_district_pre2021: str
    old_city_2021_2025: str
    new_ward_slug: str
    new_ward_name: str
    mapping_type: str = Field(pattern=r"^(full|partial)$")
    note: str = ""


def load_ward_mapping(path: Path | None = None) -> list[WardMappingRow]:
    path = path or get_settings().reference_dir / "hcm_q9_ward_mapping.csv"
    with open(path, encoding="utf-8", newline="") as f:
        return [WardMappingRow.model_validate(r) for r in csv.DictReader(f)]
