"""Đọc và áp dụng robots.txt theo RFC 9309 (nguyên tắc 2).

Không dùng `urllib.robotparser` vì nó không hiểu ký tự đại diện `*` và `$`. Ví dụ Nhà Tốt chặn tham số
`page=`, `price=` bằng mẫu dạng `/*page=`; khớp tiền tố đơn thuần sẽ để lọt những URL đó.

Quy tắc:
- Chọn nhóm có user-agent khớp product token của bot (không phân biệt hoa thường); không có thì dùng `*`.
- Khớp trên path + query. Luật dài nhất thắng; bằng nhau thì Allow thắng.
- robots.txt trả 2xx: phân tích. 404/410: cho phép hết. Mã 4xx khác, 5xx, lỗi mạng: **chặn hết** (an toàn).
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from urllib.parse import unquote, urlsplit

# fetch_robots(url) -> (http_status hoặc None nếu lỗi mạng, nội dung)
RobotsFetcher = Callable[[str], tuple[int | None, str]]

MAX_ROBOTS_BYTES = 500 * 1024  # RFC 9309: tối thiểu phải đọc 500 KiB


@dataclass(frozen=True)
class _Rule:
    allow: bool
    pattern: str
    regex: re.Pattern[str]


@dataclass
class _Group:
    agents: list[str] = field(default_factory=list)
    rules: list[_Rule] = field(default_factory=list)
    crawl_delay: float | None = None


def _compile(pattern: str) -> re.Pattern[str]:
    anchored = pattern.endswith("$")
    body = pattern[:-1] if anchored else pattern
    rx = ".*".join(re.escape(part) for part in body.split("*"))
    return re.compile(rx + ("$" if anchored else ""))


def _normalize(path: str) -> str:
    # So sánh trên dạng đã giải mã %xx để "/a%2Fb" và "/a/b" không lách được nhau.
    return unquote(path)


class RobotsRules:
    """Luật đã phân tích cho một user-agent cụ thể."""

    def __init__(self, rules: list[_Rule], crawl_delay: float | None = None, *, deny_all: bool = False):
        self.rules = rules
        self.crawl_delay = crawl_delay
        self.deny_all = deny_all

    @classmethod
    def allow_all(cls) -> RobotsRules:
        return cls([])

    @classmethod
    def disallow_all(cls) -> RobotsRules:
        return cls([], deny_all=True)

    @classmethod
    def parse(cls, text: str, user_agent: str) -> RobotsRules:
        token = product_token(user_agent)
        groups: list[_Group] = []
        current: _Group | None = None
        last_was_agent = False
        for raw in text[:MAX_ROBOTS_BYTES].splitlines():
            line = raw.split("#", 1)[0].strip()
            if ":" not in line:
                continue
            key, value = (s.strip() for s in line.split(":", 1))
            key = key.lower()
            if key == "user-agent":
                if current is None or not last_was_agent:
                    current = _Group()
                    groups.append(current)
                current.agents.append(value.lower())
                last_was_agent = True
                continue
            if key not in ("allow", "disallow", "crawl-delay"):
                continue  # Sitemap, Content-Signal...: không thuộc nhóm, không cắt nhóm (RFC 9309)
            last_was_agent = False
            if current is None:
                continue
            if key in ("allow", "disallow"):
                if not value:  # "Disallow:" rỗng = không có luật
                    continue
                pat = _normalize(value)
                current.rules.append(_Rule(key == "allow", pat, _compile(pat)))
            elif key == "crawl-delay":
                try:
                    current.crawl_delay = max(current.crawl_delay or 0.0, float(value))
                except ValueError:
                    pass

        matched = [g for g in groups if token in g.agents]
        if not matched:
            matched = [g for g in groups if "*" in g.agents]
        rules = [r for g in matched for r in g.rules]
        delays = [g.crawl_delay for g in matched if g.crawl_delay is not None]
        return cls(rules, max(delays) if delays else None)

    def is_allowed(self, url: str) -> bool:
        parts = urlsplit(url)
        path = parts.path or "/"
        if path == "/robots.txt":
            return True
        if self.deny_all:
            return False
        target = _normalize(path + (f"?{parts.query}" if parts.query else ""))
        best: _Rule | None = None
        for r in self.rules:
            if r.regex.match(target):
                if (
                    best is None
                    or len(r.pattern) > len(best.pattern)
                    or (len(r.pattern) == len(best.pattern) and r.allow and not best.allow)
                ):
                    best = r
        return best is None or best.allow


def product_token(user_agent: str) -> str:
    """'AIPropertyResearchBot/0.1 (...)' -> 'aipropertyresearchbot'."""
    return re.split(r"[/\s]", user_agent.strip(), maxsplit=1)[0].lower()


def robots_url(url: str) -> str:
    p = urlsplit(url)
    return f"{p.scheme}://{p.netloc}/robots.txt"


class RobotsChecker:
    """Cache robots.txt theo origin trong một job. Việc tải robots.txt đi qua `fetcher` (HttpClient),
    nên cũng chịu rate limit như mọi request khác."""

    def __init__(self, user_agent: str, fetcher: RobotsFetcher):
        self.user_agent = user_agent
        self._fetch = fetcher
        self._cache: dict[str, RobotsRules] = {}

    def rules_for(self, url: str) -> RobotsRules:
        key = robots_url(url)
        if key not in self._cache:
            status, body = self._fetch(key)
            if status is not None and 200 <= status < 300:
                rules = RobotsRules.parse(body, self.user_agent)
            elif status in (404, 410):
                rules = RobotsRules.allow_all()
            else:
                rules = RobotsRules.disallow_all()
            self._cache[key] = rules
        return self._cache[key]

    def is_allowed(self, url: str) -> bool:
        return self.rules_for(url).is_allowed(url)

    def crawl_delay(self, url: str) -> float:
        return self.rules_for(url).crawl_delay or 0.0
