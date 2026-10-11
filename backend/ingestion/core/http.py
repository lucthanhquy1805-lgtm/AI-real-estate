"""HttpClient: điểm duy nhất crawler được phép gửi request ra ngoài.

Mỗi request đi qua theo thứ tự:
1. Policy gate: nguồn phải `can_crawl()` và chưa bị pause trong DB (kiểm tra khi khởi tạo).
2. Phạm vi: chỉ host thuộc `base_url` của nguồn, không tải URL ảnh/video   -> skipped_policy.
3. robots.txt (RFC 9309, có wildcard)                                      -> skipped_robots.
4. Rate limit theo site (base host, gộp mọi subdomain): max(min_delay, Crawl-delay, Retry-After), 1 kết nối.
5. Gửi request (không tự theo redirect; mỗi bước redirect lặp lại 2–4).
6. BlockDetector: challenge/CAPTCHA hoặc 3 lần 403/429 liên tiếp -> pause nguồn, ghi log, ném SourceBlocked.

Mọi request (kể cả robots.txt và request bị bỏ qua) đều ghi một dòng fetch_log.
Không có retry, không đổi User-Agent, không proxy (nguyên tắc 1).
"""

from __future__ import annotations

import hashlib
import logging
import re
import time
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from email.utils import parsedate_to_datetime
from http.cookiejar import CookieJar, DefaultCookiePolicy
from typing import NoReturn, Protocol
from urllib.parse import urljoin, urlsplit

import httpx

from app.contracts import Source, SourceRegistry, load_sources
from ingestion.core.block_detect import BlockDetector
from ingestion.core.rate_limit import RateLimiter
from ingestion.core.robots import RobotsChecker

log = logging.getLogger(__name__)

MEDIA_URL = re.compile(r"\.(jpe?g|png|webp|gif|avif|bmp|svg|mp4|webm)(\?|#|$)", re.IGNORECASE)
# Server bảo chờ lâu hơn mức này (429/503 + Retry-After) thì coi như bị chặn: pause nguồn thay vì quay lại sớm.
MAX_RETRY_AFTER_SECONDS = 3600.0
REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})
PLACEHOLDER_CONTACT = "CHANGE_ME"
# Limiter dùng chung trong process; delay thật của từng nguồn truyền qua extra_delay.
_PROCESS_LIMITER = RateLimiter(1)


# ---------------------------------------------------------------- giao diện ghi log / trạng thái nguồn


@dataclass(frozen=True)
class FetchLogEntry:
    source_id: str
    url_hash: str
    request_url: str | None  # None khi URL ngoài phạm vi base_url (chỉ giữ hash)
    http_status: int | None
    latency_ms: int | None
    outcome: str  # ok | blocked | error | skipped_robots | skipped_policy


class FetchLogSink(Protocol):
    def record(self, entry: FetchLogEntry) -> None: ...


class SourceStatusStore(Protocol):
    def is_paused(self, source_id: str) -> bool: ...

    def pause(self, source_id: str, reason: str) -> None: ...


class MemoryFetchLog:
    """Sink trong bộ nhớ, dùng cho test và chế độ --dry-run."""

    def __init__(self) -> None:
        self.entries: list[FetchLogEntry] = []

    def record(self, entry: FetchLogEntry) -> None:
        self.entries.append(entry)


class MemorySourceStatus:
    def __init__(self) -> None:
        self.paused: dict[str, str] = {}

    def is_paused(self, source_id: str) -> bool:
        return source_id in self.paused

    def pause(self, source_id: str, reason: str) -> None:
        self.paused[source_id] = reason


# ---------------------------------------------------------------- kết quả và lỗi


class SourceBlocked(RuntimeError):
    """Nguồn đã bị pause (bị chặn hoặc đang paused). Job phải dừng, không thử lại."""


class SourceNotCrawlable(PermissionError):
    """Policy gate từ chối: nguồn không ở trạng thái được crawl."""


@dataclass
class FetchResult:
    url: str
    outcome: str
    status: int | None = None
    final_url: str | None = None
    headers: dict[str, str] = field(default_factory=dict)
    content: bytes = b""
    latency_ms: int | None = None
    error: str | None = None  # chỉ tên lớp lỗi/mã lỗi, không chép nội dung trang

    @property
    def ok(self) -> bool:
        return self.outcome == "ok"


def url_hash(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


def _base_host(base_url: str) -> str:
    host = (urlsplit(base_url).hostname or "").lower()
    return host.removeprefix("www.")


# ---------------------------------------------------------------- client


class HttpClient:
    def __init__(
        self,
        source: Source,
        *,
        user_agent: str,
        min_delay_seconds: float,
        fetch_log: FetchLogSink,
        status_store: SourceStatusStore,
        transport: httpx.BaseTransport | None = None,
        limiter: RateLimiter | None = None,
        block_threshold: int = 3,
        max_redirects: int = 3,
        max_bytes: int = 5 * 1024 * 1024,
        timeout_seconds: float = 30.0,
        today: date | None = None,
    ):
        ok, reason = source.can_crawl(today)
        if not ok:
            raise SourceNotCrawlable(f"{source.id}: {reason}")
        if status_store.is_paused(source.id):
            raise SourceBlocked(f"{source.id}: nguồn đang paused trong DB")
        if not source.base_url:
            raise SourceNotCrawlable(f"{source.id}: thiếu base_url")
        if PLACEHOLDER_CONTACT in user_agent:
            raise SourceNotCrawlable("User-Agent còn email liên hệ mẫu CHANGE_ME (xem ROADMAP X.1)")
        self.source = source
        self.user_agent = user_agent
        self.fetch_log = fetch_log
        self.status_store = status_store
        # Không bao giờ nhanh hơn min_delay mặc định và của riêng nguồn trong sources.yaml,
        # dù người gọi truyền số nhỏ hơn.
        floor = load_sources().defaults.min_delay_seconds
        self.min_delay = max(float(min_delay_seconds), floor, source.min_delay_seconds or 0.0)
        # Mặc định dùng chung một limiter trong process: hai client cùng site vẫn chỉ 1 kết nối.
        # Test truyền limiter riêng có đồng hồ giả.
        self.limiter = limiter or _PROCESS_LIMITER
        self.robots = RobotsChecker(user_agent, self._fetch_robots)
        self.detector = BlockDetector(block_threshold)
        self.max_redirects = max_redirects
        self.max_bytes = max_bytes
        self.blocked_reason: str | None = None
        self._base_host = _base_host(source.base_url)
        self._client = httpx.Client(
            transport=transport,
            headers={"User-Agent": user_agent},
            # Không giữ cookie: không mang cookie phiên hay cookie "đã qua challenge" (cf_clearance...).
            cookies=httpx.Cookies(CookieJar(policy=DefaultCookiePolicy(allowed_domains=[]))),
            follow_redirects=False,
            timeout=timeout_seconds,
        )

    @classmethod
    def for_source(
        cls,
        registry: SourceRegistry,
        source_id: str,
        *,
        fetch_log: FetchLogSink,
        status_store: SourceStatusStore,
        **kwargs: object,
    ) -> HttpClient:
        return cls(
            registry.get(source_id),
            user_agent=registry.defaults.user_agent,
            min_delay_seconds=registry.delay_for(source_id),
            fetch_log=fetch_log,
            status_store=status_store,
            **kwargs,  # type: ignore[arg-type]
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> HttpClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # ------------------------------------------------------------ API công khai

    def in_scope(self, url: str) -> bool:
        """URL thuộc base_url của nguồn (http/https, cùng domain hoặc subdomain) và không phải ảnh/video."""
        parts = urlsplit(url)
        host = (parts.hostname or "").lower()
        if parts.scheme not in ("http", "https") or MEDIA_URL.search(parts.path):
            return False
        return host == self._base_host or host.endswith("." + self._base_host)

    def fetch(self, url: str) -> FetchResult:
        """Tải một URL. Ném SourceBlocked nếu nguồn bị chặn; các trường hợp khác trả FetchResult."""
        for _ in range(self.max_redirects + 1):
            result = self._fetch_checked(url)
            if result.outcome != "redirect":
                return result
            url = result.final_url or url
        self._log(url, None, None, "error")
        return FetchResult(url, "error", error="TooManyRedirects")

    # ------------------------------------------------------------ nội bộ

    def _fetch_checked(self, url: str) -> FetchResult:
        self._ensure_not_blocked()
        if not self.in_scope(url):
            self._log(url, None, None, "skipped_policy")
            return FetchResult(url, "skipped_policy")
        if not self.robots.is_allowed(url):
            self._log(url, None, None, "skipped_robots")
            return FetchResult(url, "skipped_robots")
        return self._request(url, extra_delay=self.robots.crawl_delay(url))

    def _fetch_robots(self, robots_url: str) -> tuple[int | None, str]:
        self._ensure_not_blocked()
        if not self.in_scope(robots_url):
            self._log(robots_url, None, None, "skipped_policy")
            return None, ""
        r = self._request(robots_url, extra_delay=0.0)
        if r.outcome == "redirect":  # robots.txt bị chuyển hướng: coi như không đọc được -> chặn hết
            return None, ""
        return r.status, r.content.decode("utf-8", errors="replace")

    def _request(self, url: str, *, extra_delay: float) -> FetchResult:
        # Khóa rate limit theo cả site (base host), không theo từng subdomain: www. và m. dùng chung lượt.
        domain = self._base_host
        lock = self.limiter.acquire(domain, max(self.min_delay, extra_delay))
        start = time.perf_counter()
        status: int | None = None
        retry_after: float | None = None
        try:
            self._client.cookies.clear()
            with self._client.stream("GET", url) as resp:
                status, headers = resp.status_code, {k.lower(): v for k, v in resp.headers.items()}
                if status in (429, 503):
                    # Lùi lượt khi vẫn giữ khóa: request kế tiếp tới site không thể chen vào trước Retry-After.
                    retry_after = _retry_after_seconds(headers.get("retry-after"))
                    if retry_after:
                        self.limiter.defer(domain, retry_after)
                is_media = headers.get("content-type", "").lower().startswith(("image/", "video/"))
                content = bytearray()
                if not is_media:  # ảnh/video: không đọc body
                    for chunk in resp.iter_bytes():
                        content.extend(chunk)
                        if len(content) > self.max_bytes:
                            break
        except httpx.HTTPError as exc:
            latency = _ms(start)
            self._log(url, status, latency, "error")
            return FetchResult(url, "error", status, latency_ms=latency, error=type(exc).__name__)
        finally:
            lock.release()

        latency = _ms(start)
        if len(content) > self.max_bytes:
            self._log(url, status, latency, "error")
            return FetchResult(url, "error", status, latency_ms=latency, error="ResponseTooLarge")
        body = bytes(content)
        verdict = self.detector.observe(status, headers, body)
        if verdict.blocked:
            self._block(verdict.reason, url, status, latency)
        if retry_after is not None and retry_after > MAX_RETRY_AFTER_SECONDS:
            self._block(f"HTTP {status} yêu cầu chờ {int(retry_after)} giây", url, status, latency)

        if is_media:  # ảnh/video không có đuôi file: không lưu URL
            self._log(url, status, latency, "skipped_policy", store_url=False)
            return FetchResult(url, "skipped_policy", status, latency_ms=latency)

        if status in REDIRECT_STATUSES and headers.get("location"):
            self._log(url, status, latency, "ok")
            return FetchResult(url, "redirect", status, urljoin(url, headers["location"]), headers, b"", latency)
        outcome = "ok" if 200 <= status < 300 else "error"
        self._log(url, status, latency, outcome)
        return FetchResult(
            url,
            outcome,
            status,
            url,
            headers,
            body if outcome == "ok" else b"",
            latency,
            None if outcome == "ok" else f"HTTP {status}",
        )

    def _ensure_not_blocked(self) -> None:
        if self.blocked_reason is not None:
            raise SourceBlocked(f"{self.source.id}: {self.blocked_reason}")

    def _block(self, reason: str, url: str, status: int | None, latency_ms: int | None) -> NoReturn:
        # Đặt cờ trước tiên: dù ghi log hay pause trong DB lỗi, client này không gửi thêm request nào.
        self.blocked_reason = reason
        log.warning("Nguồn %s bị chặn: %s -> chuyển paused, dừng job", self.source.id, reason)
        try:
            self._log(url, status, latency_ms, "blocked")
        except Exception:
            log.exception("Không ghi được fetch_log 'blocked' cho nguồn %s", self.source.id)
        try:
            self.status_store.pause(self.source.id, reason)
        except Exception:
            log.exception("KHÔNG pause được nguồn %s trong DB — cần pause tay trước lần chạy sau", self.source.id)
        raise SourceBlocked(f"{self.source.id}: {reason}")

    def _log(
        self, url: str, status: int | None, latency_ms: int | None, outcome: str, *, store_url: bool = True
    ) -> None:
        self.fetch_log.record(
            FetchLogEntry(
                source_id=self.source.id,
                url_hash=url_hash(url),
                request_url=url if store_url and self.in_scope(url) else None,
                http_status=status,
                latency_ms=latency_ms,
                outcome=outcome,
            )
        )


def _ms(start: float) -> int:
    return max(0, int((time.perf_counter() - start) * 1000))


def _retry_after_seconds(value: str | None, now: datetime | None = None) -> float | None:
    """Retry-After dạng số giây hoặc HTTP-date. Không đọc được thì None (min_delay vẫn áp dụng)."""
    if not value:
        return None
    value = value.strip()
    try:
        return max(0.0, float(value))
    except ValueError:
        pass
    try:
        when = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=UTC)
    return max(0.0, (when - (now or datetime.now(UTC))).total_seconds())
