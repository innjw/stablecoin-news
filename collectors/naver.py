"""네이버 뉴스 검색 API 수집기.

https://developers.naver.com/docs/serviceapi/search/news/news.md
- 일 25,000회 무료
- 1회 최대 100건
- HTML 태그 (<b>, </b>) 제거 필요
"""
from __future__ import annotations

import html
import logging
import os
import re
from datetime import datetime
from email.utils import parsedate_to_datetime

import requests

from models import Article

logger = logging.getLogger(__name__)

ENDPOINT = "https://openapi.naver.com/v1/search/news.json"


def collect_naver(
    queries: list[str],
    display: int = 50,
    sort: str = "date",
) -> list[Article]:
    """여러 쿼리로 네이버 뉴스 API 호출.

    Returns:
        Article 리스트. 환경변수 NAVER_CLIENT_ID/SECRET 없으면 빈 리스트.
    """
    client_id = os.environ.get("NAVER_CLIENT_ID")
    client_secret = os.environ.get("NAVER_CLIENT_SECRET")
    if not (client_id and client_secret):
        logger.warning("NAVER_CLIENT_ID/SECRET 미설정 — 네이버 수집 건너뜀")
        return []

    headers = {
        "X-Naver-Client-Id": client_id,
        "X-Naver-Client-Secret": client_secret,
    }

    articles: list[Article] = []
    for q in queries:
        try:
            r = requests.get(
                ENDPOINT,
                headers=headers,
                params={"query": q, "display": display, "sort": sort},
                timeout=10,
            )
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            logger.warning("네이버 API 호출 실패 [%s]: %s", q, e)
            continue

        for item in data.get("items", []):
            title = _clean(item.get("title", ""))
            description = _clean(item.get("description", ""))
            link = item.get("originallink") or item.get("link", "")
            pub_date = _parse_pub_date(item.get("pubDate", ""))

            if not title or not link:
                continue

            articles.append(
                Article(
                    title=title,
                    url=link,
                    source="네이버 뉴스",
                    published_at=pub_date,
                    summary=description,
                    raw_url=link,
                    weight=1.0,
                )
            )

    logger.info("네이버 뉴스 총 %d건", len(articles))
    return articles


def _clean(text: str) -> str:
    """네이버 응답의 HTML 엔티티·하이라이트 태그 제거."""
    text = re.sub(r"</?b>", "", text)
    text = html.unescape(text)
    return text.strip()


def _parse_pub_date(s: str) -> datetime | None:
    """RFC 2822 형식 파싱 (예: 'Mon, 06 May 2026 12:34:56 +0900')."""
    if not s:
        return None
    try:
        return parsedate_to_datetime(s)
    except Exception:
        return None
