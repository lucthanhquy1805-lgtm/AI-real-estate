"""T0.5 — lõi crawler: RateLimiter, RobotsChecker, BlockDetector, TransientStore, HttpClient.

Không gọi mạng thật: mọi request đi qua httpx.MockTransport, đồng hồ là đồng hồ giả.
"""

from __future__ import annotations

from datetime import date

import httpx
import pytest

from app.contracts import Source
from ingestion.core.block_detect import BlockDetector, is_challenge
from ingestion.core.http import (
    HttpClient,
    MemoryFetchLog,
    MemorySourceStatus,
    SourceBlocked,
    SourceNotCrawlable,
    url_hash,
)
from ingestion.core.rate_limit import RateLimiter, domain_of
from ingestion.core.robots import RobotsChecker, RobotsRules, product_token
from ingestion.core.transient import TransientStore

UA = "AIPropertyResearchBot/0.1 (personal non-commercial research; contact: test@example.test)"
BASE = "https://www.example.test"
DELAY = 8.0


class FakeClock:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t

    def sleep(self, seconds: float) -> None:
        assert seconds > 0
        self.t += seconds


def make_source(**overrides: object) -> Source:
    data: dict[str, object] = dict(
        id="testsrc",
        name="Nguồn thử",
        base_url=BASE,
        tier=1,
        permission_level="approved_facts_only",
        allow_training=True,
        status="active",
        reviewed_at=date(2026, 10, 1),
        next_review_at=date(2026, 11, 1),
    )
    data.update(overrides)
    return Source.model_validate(data)


class FakeSite:
    """Máy chủ giả: map path(+query) -> (status, body, headers). Ghi lại thời điểm và URL mỗi request."""

    def __init__(self, clock: FakeClock, robots: str | None = "User-agent: *\nAllow: /\n", robots_status: int = 200):
        self.clock = clock
        self.routes: dict[str, list[tuple[int, str, dict[str, str]]]] = {}
        self.calls: list[tuple[float, str, str]] = []
        if robots is not None:
            self.add("/robots.txt", robots_status, robots)

    def add(self, path: str, status: int = 200, body: str = "<html>ok</html>", headers: dict[str, str] | None = None):
        self.routes.setdefault(path, []).append((status, body, headers or {}))
        return self

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.calls.append((self.clock(), str(request.url), request.headers.get("user-agent", "")))
        key = request.url.raw_path.decode()
        responses = self.routes.get(key)
        if not responses:
            return httpx.Response(404, text="not found")
        status, body, headers = responses.pop(0) if len(responses) > 1 else responses[0]
        return httpx.Response(status, text=body, headers=headers)

    def page_calls(self) -> list[tuple[float, str, str]]:
        return [c for c in self.calls if not c[1].endswith("/robots.txt")]


def make_client(
    site: FakeSite, clock: FakeClock, **kwargs: object
) -> tuple[HttpClient, MemoryFetchLog, MemorySourceStatus]:
    fetch_log = MemoryFetchLog()
    status = kwargs.pop("status_store", None) or MemorySourceStatus()
    client = HttpClient(
        kwargs.pop("source", None) or make_source(),
        user_agent=UA,
        min_delay_seconds=DELAY,
        fetch_log=fetch_log,
        status_store=status,
        transport=httpx.MockTransport(site.handler),
        limiter=RateLimiter(1, clock=clock, sleep=clock.sleep),
        today=date(2026, 10, 11),
        **kwargs,
    )
    return client, fetch_log, status


# ---------------------------------------------------------------- RateLimiter


def test_rate_limiter_enforces_min_delay_per_domain():
    clock = FakeClock()
    rl = RateLimiter(6, clock=clock, sleep=clock.sleep)
    starts = []
    for _ in range(5):
        lock = rl.acquire("a.test")
        starts.append(clock())
        clock.t += 0.5  # thời gian request
        lock.release()
    gaps = [b - a for a, b in zip(starts, starts[1:], strict=False)]
    assert all(g >= 6 for g in gaps), gaps


def test_rate_limiter_domains_are_independent_and_extra_delay_only_slows_down():
    clock = FakeClock()
    rl = RateLimiter(6, clock=clock, sleep=clock.sleep)
    rl.acquire("a.test").release()
    t0 = clock()
    rl.acquire("b.test").release()
    assert clock() == t0  # domain khác không phải chờ
    rl.acquire("a.test", extra_delay=20).release()
    assert clock() - t0 >= 20
    t1 = clock()
    rl.acquire("a.test", extra_delay=1).release()  # Crawl-delay nhỏ hơn không rút ngắn min_delay
    assert clock() - t1 >= 6


def test_rate_limiter_defer_and_validation():
    clock = FakeClock()
    rl = RateLimiter(6, clock=clock, sleep=clock.sleep)
    rl.acquire("a.test").release()
    rl.defer("a.test", 60)
    t0 = clock()
    rl.acquire("a.test").release()
    assert clock() - t0 >= 60
    with pytest.raises(ValueError):
        RateLimiter(0.5)
    assert domain_of("https://WWW.Example.test:443/x") == "www.example.test"


# ---------------------------------------------------------------- robots.txt

NHATOT_LIKE = """
# ví dụ kiểu Nhà Tốt: chặn tham số tìm kiếm bằng wildcard
User-agent: *
Allow: /
Disallow: /*page=
Disallow: /*price=
Disallow: /*.json$
Disallow: /tai-khoan
Crawl-delay: 10
"""


def test_robots_wildcards_and_anchor():
    r = RobotsRules.parse(NHATOT_LIKE, UA)
    assert r.is_allowed(f"{BASE}/mua-ban-nha-dat")
    assert not r.is_allowed(f"{BASE}/mua-ban-nha-dat?page=2")
    assert not r.is_allowed(f"{BASE}/mua-ban?sort=1&price=1-2-ty")
    assert not r.is_allowed(f"{BASE}/api/data.json")
    assert r.is_allowed(f"{BASE}/api/data.json?v=1")  # "$" neo ở cuối
    assert not r.is_allowed(f"{BASE}/tai-khoan/123")
    assert r.crawl_delay == 10


def test_robots_longest_match_and_tie_goes_to_allow():
    r = RobotsRules.parse("User-agent: *\nDisallow: /a\nAllow: /a/b\nDisallow: /x\nAllow: /x\n", UA)
    assert r.is_allowed(f"{BASE}/a/b/c")
    assert not r.is_allowed(f"{BASE}/a/c")
    assert r.is_allowed(f"{BASE}/x/1")


def test_robots_specific_group_overrides_star_and_groups_merge():
    text = (
        "User-agent: *\nDisallow: /\n\n"
        "User-agent: Googlebot\nUser-agent: AIPropertyResearchBot\nDisallow: /private\n\n"
        "User-agent: aipropertyresearchbot\nDisallow: /secret # chú thích\nDisallow:\n"
    )
    r = RobotsRules.parse(text, UA)
    assert product_token(UA) == "aipropertyresearchbot"
    assert r.is_allowed(f"{BASE}/ban-nha")
    assert not r.is_allowed(f"{BASE}/private/1")
    assert not r.is_allowed(f"{BASE}/secret")
    other = RobotsRules.parse(text, "OtherBot/1.0")
    assert not other.is_allowed(f"{BASE}/ban-nha")


def test_robots_percent_encoding_cannot_bypass():
    r = RobotsRules.parse("User-agent: *\nDisallow: /tài-khoản\n", UA)
    assert not r.is_allowed(f"{BASE}/t%C3%A0i-kho%E1%BA%A3n/1")


@pytest.mark.parametrize(
    ("status", "allowed"),
    [(200, True), (404, True), (410, True), (401, False), (403, False), (500, False), (503, False), (None, False)],
)
def test_robots_fetch_status_policy(status, allowed):
    body = "User-agent: *\nAllow: /\n" if status == 200 else ""
    checker = RobotsChecker(UA, lambda url: (status, body))
    assert checker.is_allowed(f"{BASE}/ban-nha") is allowed
    assert checker.is_allowed(f"{BASE}/robots.txt")  # robots.txt luôn được đọc


def test_robots_checker_caches_per_origin():
    seen = []
    checker = RobotsChecker(UA, lambda url: (seen.append(url), (200, "User-agent: *\nDisallow: /x\n"))[1])
    for p in ("/a", "/b", "/x"):
        checker.is_allowed(f"{BASE}{p}")
    checker.is_allowed("https://other.test/a")
    assert seen == [f"{BASE}/robots.txt", "https://other.test/robots.txt"]


# ---------------------------------------------------------------- BlockDetector


def test_block_detector_three_consecutive_403_429():
    d = BlockDetector()
    assert not d.observe(403, {}, b"").blocked
    assert not d.observe(429, {}, b"").blocked
    v = d.observe(403, {}, b"")
    assert v.blocked and "3 lần" in v.reason


def test_block_detector_resets_on_success():
    d = BlockDetector()
    d.observe(403, {}, b"")
    d.observe(403, {}, b"")
    d.observe(200, {}, b"<html>ok</html>")
    assert not d.observe(403, {}, b"").blocked
    assert not d.observe(404, {}, b"").blocked  # 404 không reset nhưng cũng không tính
    assert not d.observe(429, {}, b"").blocked
    assert d.observe(403, {}, b"").blocked


@pytest.mark.parametrize(
    "body",
    [
        "<html><head><title>Just a moment...</title></head></html>",
        '<script src="/cdn-cgi/challenge-platform/h/b/orchestrate/jsch/v1"></script>',
        '<div class="g-recaptcha" data-sitekey="x"></div>',
        '<script src="https://hcaptcha.com/1/api.js"></script>',
        '<div class="cf-turnstile"></div>',
        "<title>Attention Required! | Cloudflare</title>",
        "<p>Please verify you are a human</p>",
    ],
)
def test_challenge_pages_block_immediately(body):
    assert is_challenge({}, body.encode())
    assert BlockDetector().observe(200, {}, body.encode()).blocked


def test_challenge_header_and_normal_page():
    assert is_challenge({"CF-Mitigated": "challenge"}, b"")
    assert is_challenge({}, "<html><body>Nhà phố Long Bình 5,2 tỷ</body></html>".encode()) is None


# ---------------------------------------------------------------- TransientStore


def test_transient_store_is_removed_after_job(tmp_path):
    with TransientStore("job-1", root=tmp_path) as store:
        store.write_text("mo_ta.txt", "mô tả tạm")
        store.write_bytes("anh/1.bin", b"\x00\x01")
        assert not store.is_empty()
    assert not store.path.exists()
    assert list(tmp_path.iterdir()) == []


def test_transient_store_is_removed_on_error(tmp_path):
    with pytest.raises(RuntimeError), TransientStore("job-2", root=tmp_path) as store:
        store.write_text("x.txt", "tạm")
        raise RuntimeError("parser lỗi")
    assert list(tmp_path.iterdir()) == []


def test_transient_store_rejects_path_escape_and_closed_use(tmp_path):
    with TransientStore("job-3", root=tmp_path) as store:
        with pytest.raises(ValueError):
            store.write_text("../thoat.txt", "x")
    with pytest.raises(RuntimeError):
        store.write_text("sau-khi-dong.txt", "x")
    assert list(tmp_path.iterdir()) == []


def test_transient_sweep_removes_leftovers(tmp_path):
    (tmp_path / "job-cu" / "sub").mkdir(parents=True)
    (tmp_path / "job-cu" / "sub" / "f.txt").write_text("x", encoding="utf-8")
    (tmp_path / "le.txt").write_text("x", encoding="utf-8")
    assert TransientStore.sweep(tmp_path) == 2
    assert list(tmp_path.iterdir()) == []
    assert TransientStore.sweep(tmp_path / "khong-ton-tai") == 0


# ---------------------------------------------------------------- HttpClient


def test_dod_a_never_two_requests_same_domain_within_min_delay():
    clock = FakeClock()
    site = FakeSite(clock)
    for i in range(6):
        site.add(f"/tin-{i}", 200 if i % 2 else 500)
    client, _, _ = make_client(site, clock)
    for i in range(6):
        client.fetch(f"{BASE}/tin-{i}")
        clock.t += 0.3  # xử lý giữa hai lần fetch
    times = [t for t, _, _ in site.calls]
    assert len(times) == 7  # robots.txt + 6 trang
    assert all(b - a >= DELAY for a, b in zip(times, times[1:], strict=False))


def test_dod_a_crawl_delay_from_robots_slows_down():
    clock = FakeClock()
    site = FakeSite(clock, robots="User-agent: *\nCrawl-delay: 30\n").add("/a").add("/b")
    client, _, _ = make_client(site, clock)
    client.fetch(f"{BASE}/a")
    client.fetch(f"{BASE}/b")
    pages = [t for t, _, _ in site.page_calls()]
    assert pages[1] - pages[0] >= 30


def test_dod_b_robots_disallowed_url_is_not_fetched_and_logged():
    clock = FakeClock()
    site = FakeSite(clock, robots="User-agent: *\nDisallow: /*page=\n").add("/ban-nha")
    client, flog, _ = make_client(site, clock)
    r = client.fetch(f"{BASE}/ban-nha?page=2")
    assert r.outcome == "skipped_robots" and not r.ok
    assert site.page_calls() == []
    entry = flog.entries[-1]
    assert entry.outcome == "skipped_robots"
    assert entry.request_url == f"{BASE}/ban-nha?page=2"
    assert entry.url_hash == url_hash(f"{BASE}/ban-nha?page=2") and entry.http_status is None
    assert client.fetch(f"{BASE}/ban-nha").ok


def test_robots_unreachable_means_skip_everything():
    clock = FakeClock()
    site = FakeSite(clock, robots="", robots_status=503).add("/ban-nha")
    client, flog, _ = make_client(site, clock)
    assert client.fetch(f"{BASE}/ban-nha").outcome == "skipped_robots"
    assert site.page_calls() == []
    assert [e.outcome for e in flog.entries] == ["error", "skipped_robots"]


def test_dod_c_three_consecutive_403_pauses_source():
    clock = FakeClock()
    site = FakeSite(clock).add("/x", 403)
    client, flog, status = make_client(site, clock)
    client.fetch(f"{BASE}/x")
    client.fetch(f"{BASE}/x")
    with pytest.raises(SourceBlocked):
        client.fetch(f"{BASE}/x")
    assert status.is_paused("testsrc") and "403/429" in status.paused["testsrc"]
    assert flog.entries[-1].outcome == "blocked" and flog.entries[-1].http_status == 403
    n = len(site.calls)
    with pytest.raises(SourceBlocked):  # sau khi bị chặn: không gửi thêm request nào
        client.fetch(f"{BASE}/khac")
    assert len(site.calls) == n


def test_dod_c_challenge_page_pauses_immediately():
    clock = FakeClock()
    site = FakeSite(clock).add("/x", 503, "<title>Just a moment...</title>")
    client, flog, status = make_client(site, clock)
    with pytest.raises(SourceBlocked, match="challenge"):
        client.fetch(f"{BASE}/x")
    assert status.is_paused("testsrc")
    assert [e.outcome for e in flog.entries] == ["ok", "blocked"]  # robots.txt rồi trang challenge


def test_dod_c_challenge_on_robots_txt_also_blocks():
    clock = FakeClock()
    site = FakeSite(clock, robots='<div class="g-recaptcha"></div>')
    client, _, status = make_client(site, clock)
    with pytest.raises(SourceBlocked):
        client.fetch(f"{BASE}/ban-nha")
    assert status.is_paused("testsrc")


def test_429_retry_after_defers_next_request():
    clock = FakeClock()
    site = FakeSite(clock).add("/x", 429, "", {"Retry-After": "120"}).add("/x", 200)
    client, _, _ = make_client(site, clock)
    assert client.fetch(f"{BASE}/x").outcome == "error"
    assert client.fetch(f"{BASE}/x").ok
    pages = [t for t, _, _ in site.page_calls()]
    assert pages[1] - pages[0] >= 120


def test_policy_gate_refuses_non_crawlable_or_db_paused_source():
    clock = FakeClock()
    site = FakeSite(clock)
    with pytest.raises(SourceNotCrawlable):
        make_client(site, clock, source=make_source(status="paused"))
    with pytest.raises(SourceNotCrawlable):
        make_client(site, clock, source=make_source(next_review_at=date(2026, 10, 1)))
    db_paused = MemorySourceStatus()
    db_paused.pause("testsrc", "bị chặn hôm qua")
    with pytest.raises(SourceBlocked):
        make_client(site, clock, status_store=db_paused)
    assert site.calls == []


def test_out_of_scope_and_media_urls_are_skipped_without_storing_url():
    clock = FakeClock()
    site = FakeSite(clock)
    client, flog, _ = make_client(site, clock)
    for url in ("https://khac.test/tin-1", f"{BASE}/anh/1.JPG", f"{BASE}/v.mp4?x=1", "ftp://www.example.test/a"):
        assert client.fetch(url).outcome == "skipped_policy"
    assert site.calls == []
    assert all(e.request_url is None and e.outcome == "skipped_policy" for e in flog.entries)
    assert client.in_scope("https://example.test/a") and client.in_scope("https://m.example.test/a")


def test_redirects_are_rechecked():
    clock = FakeClock()
    site = FakeSite(clock, robots="User-agent: *\nDisallow: /cam\n")
    site.add("/cu", 301, "", {"Location": "/moi"}).add("/moi", 200, "<html>moi</html>")
    site.add("/ra-ngoai", 302, "", {"Location": "https://khac.test/x"})
    site.add("/vao-cam", 302, "", {"Location": "/cam/1"})
    client, _, _ = make_client(site, clock)
    r = client.fetch(f"{BASE}/cu")
    assert r.ok and r.final_url == f"{BASE}/moi" and r.content == b"<html>moi</html>"
    assert client.fetch(f"{BASE}/ra-ngoai").outcome == "skipped_policy"
    assert client.fetch(f"{BASE}/vao-cam").outcome == "skipped_robots"
    assert not any("khac.test" in u or "/cam/" in u for _, u, _ in site.calls)


def test_redirect_loop_stops():
    clock = FakeClock()
    site = FakeSite(clock).add("/vong", 302, "", {"Location": "/vong"})
    client, _, _ = make_client(site, clock)
    r = client.fetch(f"{BASE}/vong")
    assert r.outcome == "error" and r.error == "TooManyRedirects"
    assert len(site.page_calls()) == 4  # lần đầu + 3 redirect


def test_network_error_records_only_exception_name():
    clock = FakeClock()

    def boom(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        raise httpx.ConnectError("lỗi kèm chi tiết NOI-DUNG-TRANG không được chép", request=request)

    client = HttpClient(
        make_source(),
        user_agent=UA,
        min_delay_seconds=DELAY,
        fetch_log=(flog := MemoryFetchLog()),
        status_store=MemorySourceStatus(),
        transport=httpx.MockTransport(boom),
        limiter=RateLimiter(1, clock=clock, sleep=clock.sleep),
        today=date(2026, 10, 11),
    )
    r = client.fetch(f"{BASE}/a")
    assert r.outcome == "error" and r.error == "ConnectError"
    assert flog.entries[-1].outcome == "error" and flog.entries[-1].http_status is None
    assert "NOI-DUNG-TRANG" not in repr(r) and "NOI-DUNG-TRANG" not in repr(flog.entries)


def test_user_agent_and_size_limit():
    clock = FakeClock()
    site = FakeSite(clock).add("/to", 200, "x" * 2000)
    client, _, _ = make_client(site, clock, max_bytes=1000)
    r = client.fetch(f"{BASE}/to")
    assert r.outcome == "error" and r.error == "ResponseTooLarge" and r.content == b""
    assert all(ua == UA for _, _, ua in site.calls)


def test_non_ok_responses_do_not_carry_content():
    clock = FakeClock()
    site = FakeSite(clock).add("/loi", 500, "<html>trang lỗi</html>")
    client, _, _ = make_client(site, clock)
    r = client.fetch(f"{BASE}/loi")
    assert r.outcome == "error" and r.error == "HTTP 500" and r.content == b""


def test_tests_cannot_reach_real_network():
    import socket

    with socket.socket() as s, pytest.raises(RuntimeError, match="mạng thật"):
        s.connect(("192.0.2.1", 80))  # IP tài liệu (TEST-NET-1), không cần DNS


# ---------------------------------------------------------------- sau rà soát compliance T0.5


def test_cookies_are_never_sent_back():
    clock = FakeClock()
    site = FakeSite(clock).add("/a", 200, "ok", {"Set-Cookie": "cf_clearance=abc; Path=/"}).add("/b")
    sent: list[str | None] = []
    original = site.handler

    def spy(request: httpx.Request) -> httpx.Response:
        sent.append(request.headers.get("cookie"))
        return original(request)

    site.handler = spy  # type: ignore[method-assign]
    client, _, _ = make_client(site, clock)
    client.fetch(f"{BASE}/a")
    client.fetch(f"{BASE}/b")
    assert sent and all(c is None for c in sent)


def test_rate_limit_is_shared_across_subdomains():
    clock = FakeClock()
    site = FakeSite(clock).add("/a").add("/b")
    client, _, _ = make_client(site, clock)
    client.fetch(f"{BASE}/a")
    client.fetch("https://m.example.test/b")
    times = [t for t, _, _ in site.calls]
    assert len(times) == 4  # 2 robots.txt (2 origin) + 2 trang
    assert all(b - a >= DELAY for a, b in zip(times, times[1:], strict=False))


def test_min_delay_never_below_source_setting():
    clock = FakeClock()
    site = FakeSite(clock).add("/a").add("/b")
    client, _, _ = make_client(site, clock, source=make_source(min_delay_seconds=20))
    client.fetch(f"{BASE}/a")
    client.fetch(f"{BASE}/b")
    pages = [t for t, _, _ in site.page_calls()]
    assert pages[1] - pages[0] >= 20


def test_clients_without_fake_clock_share_process_limiter():
    from ingestion.core import http as http_mod

    kwargs = dict(user_agent=UA, min_delay_seconds=DELAY, today=date(2026, 10, 11))
    a = HttpClient(make_source(), fetch_log=MemoryFetchLog(), status_store=MemorySourceStatus(), **kwargs)
    b = HttpClient(make_source(), fetch_log=MemoryFetchLog(), status_store=MemorySourceStatus(), **kwargs)
    assert a.limiter is b.limiter is http_mod._PROCESS_LIMITER


def test_placeholder_contact_in_user_agent_is_refused():
    with pytest.raises(SourceNotCrawlable, match="CHANGE_ME"):
        HttpClient(
            make_source(),
            user_agent="AIPropertyResearchBot/0.1 (contact: CHANGE_ME@example.com)",
            min_delay_seconds=DELAY,
            fetch_log=MemoryFetchLog(),
            status_store=MemorySourceStatus(),
            today=date(2026, 10, 11),
        )


class BrokenSink:
    def record(self, entry: object) -> None:
        raise RuntimeError("DB rớt")


class BrokenStatus(MemorySourceStatus):
    def pause(self, source_id: str, reason: str) -> None:
        raise RuntimeError("DB rớt")


def test_block_still_stops_client_when_log_and_pause_fail():
    clock = FakeClock()
    site = FakeSite(clock, robots=None).add("/robots.txt", 404).add("/x", 200, "<title>Just a moment...</title>")
    client = HttpClient(
        make_source(),
        user_agent=UA,
        min_delay_seconds=DELAY,
        fetch_log=MemoryFetchLog(),
        status_store=BrokenStatus(),
        transport=httpx.MockTransport(site.handler),
        limiter=RateLimiter(1, clock=clock, sleep=clock.sleep),
        today=date(2026, 10, 11),
    )
    client.robots.rules_for(f"{BASE}/x")  # đọc robots.txt trước
    client.fetch_log = BrokenSink()  # từ giờ mọi lần ghi log đều lỗi
    with pytest.raises(SourceBlocked):
        client.fetch(f"{BASE}/x")
    n = len(site.calls)
    with pytest.raises(SourceBlocked):
        client.fetch(f"{BASE}/y")
    assert len(site.calls) == n


def test_long_retry_after_pauses_source_and_http_date_is_parsed():
    from datetime import UTC, datetime

    from ingestion.core.http import _retry_after_seconds

    clock = FakeClock()
    site = FakeSite(clock).add("/x", 429, "", {"Retry-After": "7200"})
    client, flog, status = make_client(site, clock)
    with pytest.raises(SourceBlocked, match="7200"):
        client.fetch(f"{BASE}/x")
    assert status.is_paused("testsrc") and flog.entries[-1].outcome == "blocked"

    now = datetime(2026, 10, 11, 0, 0, 0, tzinfo=UTC)
    assert _retry_after_seconds("Sun, 11 Oct 2026 00:02:00 GMT", now) == 120
    assert _retry_after_seconds("ngày mai", now) is None
    assert _retry_after_seconds("30", now) == 30


def test_503_retry_after_also_defers():
    clock = FakeClock()
    site = FakeSite(clock).add("/x", 503, "", {"Retry-After": "90"}).add("/x", 200)
    client, _, _ = make_client(site, clock)
    client.fetch(f"{BASE}/x")
    client.fetch(f"{BASE}/x")
    pages = [t for t, _, _ in site.page_calls()]
    assert pages[1] - pages[0] >= 90


def test_media_content_type_without_extension_is_dropped():
    clock = FakeClock()
    site = FakeSite(clock).add("/resize/abc", 200, "fake", {"Content-Type": "image/webp"})
    client, flog, _ = make_client(site, clock)
    r = client.fetch(f"{BASE}/resize/abc")
    assert r.outcome == "skipped_policy" and r.content == b""
    assert flog.entries[-1].request_url is None and flog.entries[-1].outcome == "skipped_policy"


def test_robots_non_group_lines_do_not_split_groups():
    text = "User-agent: Googlebot\nSitemap: https://x.test/s.xml\nUser-agent: AIPropertyResearchBot\nDisallow: /cam\n"
    r = RobotsRules.parse(text, UA)
    assert not r.is_allowed(f"{BASE}/cam/1")


def test_dns_is_blocked_in_tests():
    import socket

    with pytest.raises(RuntimeError, match="DNS"):
        socket.getaddrinfo("example.com", 80)


def test_delay_never_below_registry_default_even_if_caller_passes_less():
    clock = FakeClock()
    site = FakeSite(clock).add("/a").add("/b")
    client = HttpClient(
        make_source(),  # nguồn không khai min_delay_seconds riêng
        user_agent=UA,
        min_delay_seconds=1,
        fetch_log=MemoryFetchLog(),
        status_store=MemorySourceStatus(),
        transport=httpx.MockTransport(site.handler),
        limiter=RateLimiter(1, clock=clock, sleep=clock.sleep),
        today=date(2026, 10, 11),
    )
    assert client.min_delay == 6
    client.fetch(f"{BASE}/a")
    client.fetch(f"{BASE}/b")
    times = [t for t, _, _ in site.calls]
    assert all(b - a >= 6 for a, b in zip(times, times[1:], strict=False))


def test_media_body_is_not_read():
    clock = FakeClock()
    reads: list[int] = []

    class CountingStream(httpx.SyncByteStream):
        def __iter__(self):
            reads.append(1)
            yield b"fake-image-bytes"

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(200, headers={"Content-Type": "image/jpeg"}, stream=CountingStream())

    client = HttpClient(
        make_source(),
        user_agent=UA,
        min_delay_seconds=DELAY,
        fetch_log=MemoryFetchLog(),
        status_store=MemorySourceStatus(),
        transport=httpx.MockTransport(handler),
        limiter=RateLimiter(1, clock=clock, sleep=clock.sleep),
        today=date(2026, 10, 11),
    )
    assert client.fetch(f"{BASE}/resize/1").outcome == "skipped_policy"
    assert reads == []
