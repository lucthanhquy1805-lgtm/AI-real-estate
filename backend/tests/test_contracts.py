from datetime import date

import pytest
from pydantic import ValidationError

from app.contracts import Source, load_sources, load_ward_mapping
from ingestion.core.policy import FieldPolicy, UnknownFieldError


def test_sources_yaml_is_valid():
    reg = load_sources()
    ids = {s.id for s in reg.sources}
    assert {"batdongsan", "nhatot", "osm", "manual_import"} <= ids


def test_nhatot_never_used_for_training():
    # robots.txt của Nhà Tốt: ai-train=no
    reg = load_sources()
    assert reg.get("nhatot").allow_training is False
    assert "nhatot" not in reg.training_source_ids()


def test_crawl_delay_never_below_default():
    reg = load_sources()
    for s in reg.sources:
        assert reg.delay_for(s.id) >= reg.defaults.min_delay_seconds >= 5


def test_policy_gate():
    reg = load_sources()
    # Mặc định tất cả nguồn crawl đều paused cho tới khi connector sẵn sàng
    ok, reason = reg.get("batdongsan").can_crawl(today=date(2026, 10, 15))
    assert not ok and "paused" in reason
    active = reg.get("batdongsan").model_copy(update={"status": "active"})
    assert active.can_crawl(today=date(2026, 10, 15))[0]
    # quá hạn rà soát điều khoản -> chặn
    assert not active.can_crawl(today=date(2027, 1, 1))[0]
    # nguồn pending không bao giờ crawl
    assert not reg.get("tier2_candidates").can_crawl()[0]


def test_crawlable_source_requires_review_date():
    with pytest.raises(ValidationError):
        Source(
            id="x",
            name="x",
            base_url="https://x.vn",
            tier=1,
            permission_level="approved_facts_only",
            allow_training=True,
            status="active",
        )


def test_ward_mapping_covers_13_old_wards_to_5_new():
    rows = load_ward_mapping()
    assert len({r.old_ward_name for r in rows}) == 13
    assert {r.new_ward_slug for r in rows} == {"tang_nhon_phu", "long_binh", "long_phuoc", "long_truong", "phuoc_long"}
    partial = {r.old_ward_name for r in rows if r.mapping_type == "partial"}
    assert partial == {"Long Thạnh Mỹ"}


# ---- Field policy (FR-17) ----


def test_field_policy_blocks_content_media_personal():
    pol = FieldPolicy.load()
    forbidden = pol.forbidden_fields()
    for f in ["description", "title", "image_url", "image_bytes", "poster_phone", "poster_name"]:
        assert f in forbidden


def test_filter_for_storage_drops_forbidden():
    pol = FieldPolicy.load()
    rec = {
        "asking_price_vnd": 5_200_000_000,
        "description": "Nhà đẹp...",
        "poster_phone": "0909...",
        "poster_pseudonym": "ab12",
        "image_phash": "f0f0",
    }
    kept, dropped = pol.filter_for_storage(rec)
    assert set(kept) == {"asking_price_vnd", "poster_pseudonym", "image_phash"}
    assert set(dropped) == {"description", "poster_phone"}


def test_unknown_field_fails_closed():
    pol = FieldPolicy.load()
    with pytest.raises(UnknownFieldError):
        pol.filter_for_storage({"mystery_field": 1})
