"""구글 뉴스 RSS 수집기.

쿼리 기반으로 구글 뉴스 RSS를 호출. 인증 불필요.
URL이 구글 리다이렉트 형태(news.google.com/rss/articles/...)로 오므로
나중에 dedupe 단계에서 정규화한다.
"""
from __future__ import annotations

import logging
from urllib.parse import urlencode

from collectors.rss import collect_rss
from models import Article

logger = logging.getLogger(__name__)


def collect_google_news(
    queries: list[str],
    base_url: str = "https://news.google.com/rss/search",
    params: dict | None = None,
) -> list[Article]:
    """여러 쿼리로 구글 뉴스 RSS를 호출."""
    params = params or {"hl": "ko", "gl": "KR", "ceid": "KR:ko"}
    articles: list[Article] = []
    for q in queries:
        url = f"{base_url}?{urlencode({'q': q, **params})}"
        results = collect_rss(
            name=f"Google News: {q}",
            url=url,
            weight=1.0,
        )
        # source를 매체명으로 정상화 (구글 뉴스는 entry에서 매체명 추출 가능하지만
        # feedparser 기본 처리만으로는 어려워 일단 'Google News'로 통일)
        for a in results:
            a.source = "Google News"
        articles.extend(results)
    logger.info("Google News 총 %d건", len(articles))
    return articles
