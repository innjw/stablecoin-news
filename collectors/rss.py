"""RSS 피드 수집기.

코인 전문지·정부기관 등 직접 RSS를 제공하는 곳에서 기사를 가져온다.
feedparser로 표준 RSS/Atom 모두 처리.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from time import mktime
from typing import Iterable

import feedparser

from models import Article

logger = logging.getLogger(__name__)

# feedparser User-Agent 기본값이 차단되는 경우가 있어 일반 브라우저로 위장
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)


def collect_rss(
    name: str,
    url: str,
    weight: float = 1.0,
    keyword_filter: Iterable[str] | None = None,
) -> list[Article]:
    """단일 RSS 피드에서 기사를 수집한다.

    Args:
        name: 매체명 (Article.source 에 들어감)
        url: RSS URL
        weight: 매체 가중치
        keyword_filter: 제목·본문에 이 중 하나가 들어있는 기사만 채택.
                        None이면 전부 채택.
    """
    try:
        feed = feedparser.parse(url, agent=USER_AGENT, request_headers={"User-Agent": USER_AGENT})
    except Exception as e:
        logger.warning("RSS 파싱 실패 [%s] %s: %s", name, url, e)
        return []

    if feed.bozo and not feed.entries:
        logger.warning("빈 피드 [%s] %s: %s", name, url, getattr(feed, "bozo_exception", ""))
        return []

    articles: list[Article] = []
    keyword_filter_lower = (
        [k.lower() for k in keyword_filter] if keyword_filter else None
    )

    for entry in feed.entries:
        title = (entry.get("title") or "").strip()
        link = (entry.get("link") or "").strip()
        if not title or not link:
            continue

        summary = (
            entry.get("summary")
            or entry.get("description")
            or ""
        ).strip()

        # 키워드 필터링 (정부기관처럼 전체 보도자료 중 일부만 가져와야 할 때)
        if keyword_filter_lower:
            haystack = f"{title} {summary}".lower()
            if not any(k in haystack for k in keyword_filter_lower):
                continue

        published_at = _parse_published(entry)

        articles.append(
            Article(
                title=title,
                url=link,
                source=name,
                published_at=published_at,
                summary=summary,
                raw_url=link,
                weight=weight,
            )
        )

    logger.info("[%s] %d건 수집 (URL: %s)", name, len(articles), url)
    return articles


def _parse_published(entry) -> datetime | None:
    """feedparser entry에서 발행 시각을 파싱."""
    for key in ("published_parsed", "updated_parsed"):
        t = entry.get(key)
        if t:
            try:
                return datetime.fromtimestamp(mktime(t), tz=timezone.utc)
            except Exception:
                continue
    return None
