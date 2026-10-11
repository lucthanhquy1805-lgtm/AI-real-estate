"""Chuẩn hóa địa chỉ hành chính cho khu vực Quận 9 cũ (FR-19).

Tin đăng dùng lẫn 3 cách gọi:
  - trước 2021:  "Phường Hiệp Phú, Quận 9"
  - 2021–2025:   "Phường Hiệp Phú, TP Thủ Đức"
  - từ 07/2025:  "Phường Tăng Nhơn Phú, TP.HCM"

Nguyên tắc:
  - Chỉ kết luận khi có ngữ cảnh khu vực (Quận 9 / Thủ Đức / TP.HCM) — nhiều tên phường trùng ở tỉnh khác
    (Long Bình — Biên Hòa, Phú Hữu — Nhơn Trạch, Tân Phú — Quận 7...).
  - Long Thạnh Mỹ bị chia cho 2 phường mới: không đoán khi không có toạ độ -> cờ AMBIGUOUS_WARD.
  - Không tìm thấy hoặc mâu thuẫn -> trả về kết quả rỗng kèm cờ, không đoán.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import lru_cache

from app.contracts import WardMappingRow, load_ward_mapping

PROVINCE_SLUG = "hcm"

AMBIGUOUS_WARD = "AMBIGUOUS_WARD"
NO_CONTEXT = "NO_CONTEXT"
NO_WARD = "NO_WARD"
MULTIPLE_WARDS = "MULTIPLE_WARDS"


def normalize_text(s: str) -> str:
    """Bỏ dấu, chữ thường, thay dấu câu bằng khoảng trắng: 'P. Tăng Nhơn Phú A, Q.9' -> 'p tang nhon phu a q 9'."""
    s = s.replace("đ", "d").replace("Đ", "D")
    s = unicodedata.normalize("NFD", s)
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    s = s.lower()
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


_Q9_CONTEXT = re.compile(r"\b(quan 9|q 9|q9|district 9)\b")
_THU_DUC_CONTEXT = re.compile(r"\b(tp thu duc|thanh pho thu duc|thu duc city|thu duc)\b")
_HCM_CONTEXT = re.compile(r"\b(ho chi minh|tp hcm|tphcm|hcm|hcmc|sai gon|saigon)\b")
# Một tên phường đứng ngay sau "quan"/"q"/"huyen" là tên quận/huyện, không phải phường (vd "quận Tân Phú").
_DISTRICT_PREFIX = re.compile(r"\b(quan|q|huyen|tp|thanh pho|tinh)\s*$")

# Viết tắt hay gặp trong tin đăng
_ALIASES: dict[str, str] = {
    "tnp a": "tang nhon phu a",
    "tnpa": "tang nhon phu a",
    "tnp b": "tang nhon phu b",
    "tnpb": "tang nhon phu b",
}


@dataclass
class WardResolution:
    ward_slug_new: str | None = None  # vd "hcm.long_binh"
    ward_name_new: str | None = None
    ward_name_old: str | None = None
    district_alias: str | None = None  # "Quận 9" | "TP Thủ Đức" | None
    method: str = "text"  # text | geo
    confidence: float = 0.0
    flags: list[str] = field(default_factory=list)

    @property
    def resolved(self) -> bool:
        return self.ward_slug_new is not None


@dataclass(frozen=True)
class _Index:
    old_to_new: dict[str, set[str]]  # tên cũ đã normalize -> {slug mới}
    old_display: dict[str, str]  # tên cũ normalize -> tên hiển thị
    new_names: dict[str, str]  # tên mới normalize -> slug
    new_display: dict[str, str]  # slug -> tên hiển thị
    patterns: list[tuple[str, str]]  # (tên normalize, "old"|"new"), dài trước


def _build_index(rows: list[WardMappingRow]) -> _Index:
    old_to_new: dict[str, set[str]] = {}
    old_display: dict[str, str] = {}
    new_names: dict[str, str] = {}
    new_display: dict[str, str] = {}
    for r in rows:
        on = normalize_text(r.old_ward_name)
        old_to_new.setdefault(on, set()).add(r.new_ward_slug)
        old_display[on] = r.old_ward_name
        new_names[normalize_text(r.new_ward_name)] = r.new_ward_slug
        new_display[r.new_ward_slug] = r.new_ward_name
    pats = [(n, "old") for n in old_to_new] + [(n, "new") for n in new_names if n not in old_to_new]
    pats.sort(key=lambda p: len(p[0]), reverse=True)
    return _Index(old_to_new, old_display, new_names, new_display, pats)


@lru_cache
def _default_index() -> _Index:
    return _build_index(load_ward_mapping())


def _find_wards(text: str, idx: _Index) -> list[tuple[str, str]]:
    """Tìm các tên phường trong text đã normalize. Trả về [(tên, loại)], không chồng lấn."""
    found: list[tuple[str, str]] = []
    taken: list[tuple[int, int]] = []
    for name, kind in idx.patterns:
        for m in re.finditer(rf"\b{re.escape(name)}\b", text):
            s, e = m.span()
            if any(s < te and e > ts for ts, te in taken):
                continue
            if _DISTRICT_PREFIX.search(text[:s]):
                continue  # "quan tan phu" -> là quận, bỏ qua
            taken.append((s, e))
            found.append((name, kind))
    return found


def resolve_ward(
    address_text: str,
    *,
    context_text: str = "",
    lat: float | None = None,
    lon: float | None = None,
    point_in_ward: Callable[[float, float], str | None] | None = None,
    index: _Index | None = None,
) -> WardResolution:
    """Xác định phường mới từ chuỗi địa chỉ.

    address_text: địa chỉ trong tin, vd "Đường 22, P. Phước Long B, Quận 9, TP.HCM".
    context_text: thông tin khu vực có cấu trúc từ nguồn (breadcrumb, ô "Quận/Huyện"), nếu có.
    point_in_ward: hàm (lat, lon) -> slug phường mới; dùng khi có ranh giới phường (W9).
    """
    idx = index or _default_index()
    text = normalize_text(address_text)
    for a, full in _ALIASES.items():
        text = re.sub(rf"\b{a}\b", full, text)
    ctx = f"{text} {normalize_text(context_text)}"

    res = WardResolution()
    if _Q9_CONTEXT.search(ctx):
        res.district_alias = "Quận 9"
    elif _THU_DUC_CONTEXT.search(ctx):
        res.district_alias = "TP Thủ Đức"
    has_hcm = bool(_HCM_CONTEXT.search(ctx))

    # 1) Có toạ độ + ranh giới -> ưu tiên geo
    if lat is not None and lon is not None and point_in_ward is not None:
        slug = point_in_ward(lat, lon)
        if slug:
            res.ward_slug_new = f"{PROVINCE_SLUG}.{slug}"
            res.ward_name_new = idx.new_display.get(slug)
            res.method, res.confidence = "geo", 0.97
            # vẫn ghi lại tên cũ nếu có
            for name, kind in _find_wards(text, idx):
                if kind == "old":
                    res.ward_name_old = idx.old_display[name]
                    break
            return res

    if res.district_alias is None and not has_hcm:
        res.flags.append(NO_CONTEXT)
        return res

    matches = _find_wards(text, idx)
    if not matches:
        res.flags.append(NO_WARD)
        return res

    # Tên vừa là phường cũ vừa là phường mới (Long Bình, Long Phước, Long Trường):
    #  - có ngữ cảnh Quận 9/Thủ Đức -> hiểu là tên cũ
    #  - chỉ có ngữ cảnh TP.HCM    -> hiểu là tên mới
    old_only: list[str] = []  # tên chỉ tồn tại ở danh sách cũ, hoặc tên chung + ngữ cảnh cũ
    per_match: list[set[str]] = []  # tập phường mới khả dĩ của từng tên tìm thấy
    for name, kind in matches:
        is_new_name = name in idx.new_names
        if kind == "old" and (not is_new_name or res.district_alias):
            old_only.append(idx.old_display[name])
            per_match.append(set(idx.old_to_new[name]))
        else:
            per_match.append({idx.new_names[name]})

    if old_only:
        res.ward_name_old = old_only[0]

    # Mọi tên tìm thấy phải cùng chỉ về một phường mới.
    # vd "Long Thạnh Mỹ (nay là phường Long Bình)" -> {long_binh, tang_nhon_phu} ∩ {long_binh} = {long_binh}
    candidates = set.intersection(*per_match)
    if not candidates:
        res.flags.append(MULTIPLE_WARDS)
        return res
    if len(candidates) > 1:
        res.flags.append(AMBIGUOUS_WARD)  # chỉ xảy ra với phường bị chia (Long Thạnh Mỹ)
        return res

    slug = candidates.pop()
    res.ward_slug_new = f"{PROVINCE_SLUG}.{slug}"
    res.ward_name_new = idx.new_display[slug]
    if res.district_alias:
        res.confidence = 0.95
    elif not old_only:
        res.confidence = 0.9  # địa chỉ kiểu mới: "Phường X, TP.HCM"
    else:
        res.confidence = 0.7  # tên phường cũ nhưng thiếu "Quận 9/Thủ Đức"
    return res
