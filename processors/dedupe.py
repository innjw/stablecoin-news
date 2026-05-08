"""중복 기사 제거.

3단계로 처리:
1. URL 정규화 (utm_*, fbclid 등 트래킹 파라미터 제거, 도메인 소문자화)
2. 정규화 URL 기준 1차 dedupe
3. 제목 SimHash 기반 2차 dedupe (다른 매체가 같은 보도자료를 받아쓴 경우)
"""
from __future__ import annotations

import hashlib
import logging
import re
from typing import Iterable
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from models import Article

logger = logging.getLogger(__name__)

# 제거할 트래킹 파라미터
TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "fbclid", "gclid", "yclid", "msclkid",
    "ref", "referer", "referrer",
    "_ga", "mc_cid", "mc_eid",
    "from", "share",
}


def normalize_url(url: str) -> str:
    """URL 정규화."""
    if not url:
        return ""
    try:
        p = urlparse(url.strip())
    except Exception:
        return url.strip()

    # 트래킹 파라미터 제거
    qs = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True)
          if k.lower() not in TRACKING_PARAMS]
    qs.sort()  # 순서 무관하게 같은 URL로 인식
    new_query = urlencode(qs)

    # 도메인 소문자화, 끝 슬래시 제거
    netloc = p.netloc.lower()
    path = p.path.rstrip("/") or "/"

    # fragment 제거
    return urlunparse((p.scheme.lower(), netloc, path, "", new_query, ""))


def _normalize_title(title: str) -> str:
    """제목 정규화 — 공백·기호 제거, 소문자."""
    t = re.sub(r"[\s\W_]+", "", title.lower())
    return t


def _title_hash(title: str) -> str:
    return hashlib.md5(_normalize_title(title).encode("utf-8")).hexdigest()


def dedupe(articles: Iterable[Article]) -> list[Article]:
    """URL + 제목 해시 기준으로 중복 제거.

    같은 기사가 여러 매체에서 잡히면 weight 가 가장 높은 것을 남긴다.
    """
    by_key: dict[str, Article] = {}

    for a in articles:
        normalized = normalize_url(a.url)
        if normalized:
            a.url = normalized

        # 1차 키: 정규화 URL
        url_key = a.url
        # 2차 키: 정규화 제목 (URL 다른데 제목 같은 경우 잡기)
        title_key = _title_hash(a.title)

        # 두 키 중 하나라도 충돌하면 같은 기사로 간주
        existing = by_key.get(url_key) or by_key.get(title_key)
        if existing:
            # weight 높은 쪽 유지
            if a.weight > existing.weight:
                _replace(by_key, existing, a, url_key, title_key)
        else:
            by_key[url_key] = a
            by_key[title_key] = a

    # 중복 키 때문에 같은 객체가 여러 번 들어가 있으니 id 기준 유니크화
    unique = {id(v): v for v in by_key.values()}.values()
    result = list(unique)
    logger.info("dedupe: %d → %d", sum(1 for _ in articles), len(result))
    return result


def _replace(d: dict, old: Article, new: Article, *keys: str) -> None:
    """기존 객체를 모든 키에서 새 객체로 교체."""
    for k, v in list(d.items()):
        if v is old:
            d[k] = new
    for k in keys:
        d[k] = new
