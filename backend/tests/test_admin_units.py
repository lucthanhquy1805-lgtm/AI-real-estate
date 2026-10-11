import pytest

from ingestion.normalize.admin_units import (
    AMBIGUOUS_WARD,
    MULTIPLE_WARDS,
    NO_CONTEXT,
    NO_WARD,
    normalize_text,
    resolve_ward,
)


def test_normalize_text():
    assert normalize_text("P. Tăng Nhơn Phú A, Q.9, TP.HCM") == "p tang nhon phu a q 9 tp hcm"
    assert normalize_text("Đường Đỗ Xuân Hợp") == "duong do xuan hop"


@pytest.mark.parametrize(
    "address,slug,old,alias",
    [
        # kiểu trước 2021
        ("Đường Lê Văn Việt, Phường Hiệp Phú, Quận 9, TP.HCM", "hcm.tang_nhon_phu", "Hiệp Phú", "Quận 9"),
        ("P. Tăng Nhơn Phú A, Q.9", "hcm.tang_nhon_phu", "Tăng Nhơn Phú A", "Quận 9"),
        ("TNP B, Q9", "hcm.tang_nhon_phu", "Tăng Nhơn Phú B", "Quận 9"),
        ("Phước Long B, Quận 9", "hcm.phuoc_long", "Phước Long B", "Quận 9"),
        ("Phước Bình, Quận 9", "hcm.phuoc_long", "Phước Bình", "Quận 9"),
        ("Trường Thạnh, Quận 9", "hcm.long_phuoc", "Trường Thạnh", "Quận 9"),
        ("Phú Hữu, Quận 9", "hcm.long_truong", "Phú Hữu", "Quận 9"),
        ("Tân Phú, Quận 9", "hcm.tang_nhon_phu", "Tân Phú", "Quận 9"),
        # kiểu 2021–2025
        ("Phường Long Trường, TP Thủ Đức, TP.HCM", "hcm.long_truong", "Long Trường", "TP Thủ Đức"),
        ("Long Bình, Thành phố Thủ Đức", "hcm.long_binh", "Long Bình", "TP Thủ Đức"),
    ],
)
def test_old_style_addresses(address, slug, old, alias):
    r = resolve_ward(address)
    assert r.resolved, r.flags
    assert r.ward_slug_new == slug
    assert r.ward_name_old == old
    assert r.district_alias == alias
    assert r.confidence >= 0.9


@pytest.mark.parametrize(
    "address,slug",
    [
        ("Phường Tăng Nhơn Phú, TP.HCM", "hcm.tang_nhon_phu"),
        ("Phường Long Bình, Thành phố Hồ Chí Minh", "hcm.long_binh"),
        ("Phường Phước Long, TP Hồ Chí Minh", "hcm.phuoc_long"),
    ],
)
def test_new_style_addresses(address, slug):
    r = resolve_ward(address)
    assert r.ward_slug_new == slug
    assert r.ward_name_old is None
    assert r.confidence == 0.9


def test_long_thanh_my_is_ambiguous_without_coordinates():
    r = resolve_ward("Phường Long Thạnh Mỹ, Quận 9")
    assert not r.resolved
    assert r.flags == [AMBIGUOUS_WARD]
    assert r.ward_name_old == "Long Thạnh Mỹ"


def test_long_thanh_my_with_new_ward_hint():
    r = resolve_ward("Long Thạnh Mỹ (nay là phường Long Bình), TP.HCM", context_text="Quận 9")
    assert r.ward_slug_new == "hcm.long_binh"


def test_long_thanh_my_resolved_by_geo():
    r = resolve_ward("Long Thạnh Mỹ, Quận 9", lat=10.84, lon=106.83, point_in_ward=lambda la, lo: "long_binh")
    assert r.ward_slug_new == "hcm.long_binh"
    assert r.method == "geo"
    assert r.ward_name_old == "Long Thạnh Mỹ"


@pytest.mark.parametrize(
    "address",
    [
        "Phường Long Bình, TP Biên Hòa, Đồng Nai",  # trùng tên ở tỉnh khác
        "Xã Phú Hữu, huyện Nhơn Trạch, Đồng Nai",
        "Long Phước, Bà Rịa",
    ],
)
def test_same_name_other_province_not_matched(address):
    r = resolve_ward(address)
    assert not r.resolved
    assert NO_CONTEXT in r.flags


def test_district_named_tan_phu_is_not_ward():
    # "Quận Tân Phú" là quận khác, không phải phường Tân Phú (Quận 9)
    r = resolve_ward("Đường Lũy Bán Bích, Quận Tân Phú, TP.HCM")
    assert not r.resolved
    assert NO_WARD in r.flags


def test_context_from_structured_field():
    r = resolve_ward("Đường số 6, Hiệp Phú", context_text="Hồ Chí Minh > Quận 9")
    assert r.ward_slug_new == "hcm.tang_nhon_phu"


def test_conflicting_wards():
    r = resolve_ward("Phước Bình hoặc Long Trường, Quận 9")
    assert not r.resolved
    assert MULTIPLE_WARDS in r.flags


def test_old_name_with_only_hcm_context_has_lower_confidence():
    r = resolve_ward("Hiệp Phú, TP.HCM")
    assert r.ward_slug_new == "hcm.tang_nhon_phu"
    assert r.confidence == 0.7
