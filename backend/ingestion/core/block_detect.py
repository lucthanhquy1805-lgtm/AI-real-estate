"""Phát hiện bị chặn (nguyên tắc 1). Khi bị chặn, nguồn phải dừng (status -> paused), không thử vượt.

- Trang challenge/CAPTCHA (Cloudflare, reCAPTCHA, hCaptcha, Turnstile...): chặn ngay từ lần đầu.
- 403/429: chặn khi gặp `threshold` lần liên tiếp (mặc định 3). Một phản hồi 2xx đặt lại bộ đếm.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass

BLOCK_STATUSES = frozenset({403, 429})
SNIFF_BYTES = 64 * 1024

# Dấu hiệu trang thử thách / CAPTCHA. Chỉ cần khớp một dấu hiệu là coi như bị chặn (thà dừng nhầm còn hơn vượt).
CHALLENGE_MARKERS = re.compile(
    r"cf-chl-|challenge-platform|cf_chl_opt|<title>\s*just a moment|attention required!\s*\|\s*cloudflare"
    r"|g-recaptcha|recaptcha/api|hcaptcha\.com|h-captcha|challenges\.cloudflare\.com/turnstile|cf-turnstile"
    r"|captcha-delivery\.com|px-captcha|/_incapsula_resource|verify you are (a )?human",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class BlockVerdict:
    blocked: bool
    reason: str = ""


NOT_BLOCKED = BlockVerdict(False)


def is_challenge(headers: Mapping[str, str], body: bytes) -> str | None:
    """Trả về lý do nếu phản hồi là trang challenge/CAPTCHA, ngược lại None."""
    lower = {k.lower(): v for k, v in headers.items()}
    if lower.get("cf-mitigated", "").lower() == "challenge":
        return "challenge (header cf-mitigated)"
    m = CHALLENGE_MARKERS.search(body[:SNIFF_BYTES].decode("utf-8", errors="ignore"))
    if m:
        return f"challenge/CAPTCHA ({m.group(0).strip().lower()[:40]})"
    return None


class BlockDetector:
    def __init__(self, threshold: int = 3):
        if threshold < 1:
            raise ValueError("threshold phải >= 1")
        self.threshold = threshold
        self.consecutive = 0

    def observe(self, status: int, headers: Mapping[str, str], body: bytes) -> BlockVerdict:
        reason = is_challenge(headers, body)
        if reason:
            return BlockVerdict(True, reason)
        if status in BLOCK_STATUSES:
            self.consecutive += 1
            if self.consecutive >= self.threshold:
                return BlockVerdict(True, f"{self.consecutive} lần liên tiếp HTTP 403/429 (lần cuối {status})")
            return NOT_BLOCKED
        if 200 <= status < 300:
            self.consecutive = 0
        return NOT_BLOCKED
