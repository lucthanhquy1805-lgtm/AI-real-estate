"""Giới hạn tốc độ theo domain (nguyên tắc 2: mỗi domain tối thiểu `min_delay_seconds`, 1 kết nối).

Khoảng cách được tính giữa hai lần *bắt đầu gửi* request tới cùng domain, kể cả request robots.txt,
request lỗi mạng hay request bị chặn. Đồng hồ và hàm ngủ được tiêm vào để test không phải chờ thật.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from urllib.parse import urlsplit


def domain_of(url: str) -> str:
    """Domain dùng làm khóa rate limit (hostname chữ thường, không cổng)."""
    host = urlsplit(url).hostname
    if not host:
        raise ValueError(f"URL không có hostname: {url!r}")
    return host.lower()


class RateLimiter:
    def __init__(
        self,
        min_delay_seconds: float,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ):
        if min_delay_seconds < 1:
            raise ValueError("min_delay_seconds phải >= 1")
        self.min_delay = float(min_delay_seconds)
        self._clock = clock
        self._sleep = sleep
        self._last_start: dict[str, float] = {}
        self._not_before: dict[str, float] = {}
        # Một khóa cho mỗi domain: đảm bảo 1 kết nối/domain kể cả khi gọi từ nhiều thread.
        self._locks: dict[str, threading.Lock] = {}
        self._guard = threading.Lock()

    def _lock_for(self, domain: str) -> threading.Lock:
        with self._guard:
            return self._locks.setdefault(domain, threading.Lock())

    def acquire(self, domain: str, extra_delay: float = 0.0) -> threading.Lock:
        """Chờ tới lượt rồi giữ khóa domain. Người gọi PHẢI `release()` sau khi request kết thúc.

        `extra_delay` (vd Crawl-delay trong robots.txt) chỉ được làm chậm hơn, không bao giờ nhanh hơn min_delay.
        """
        lock = self._lock_for(domain)
        lock.acquire()
        try:
            delay = max(self.min_delay, extra_delay)
            last = self._last_start.get(domain)
            earliest = max(last + delay if last is not None else 0.0, self._not_before.get(domain, 0.0))
            while (now := self._clock()) < earliest:
                self._sleep(earliest - now)
            self._last_start[domain] = self._clock()
        except BaseException:
            lock.release()
            raise
        return lock

    def defer(self, domain: str, seconds: float) -> None:
        """Lùi lượt kế tiếp của domain (vd theo Retry-After). Chỉ kéo dài, không rút ngắn."""
        until = self._clock() + max(0.0, seconds)
        self._not_before[domain] = max(self._not_before.get(domain, 0.0), until)
