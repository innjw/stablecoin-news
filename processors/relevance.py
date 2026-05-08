"""키워드 기반 관련성 필터.

LLM 호출 전 1차로 거른다. 명백히 무관한 기사를 빼서 LLM 비용을 줄인다.
LLM이 정밀 분류는 다시 한다.
"""
from __future__ import annotations

import logging
from typing import Iterable

from models import Article

logger = logging.getLogger(__name__)


def filter_relevant(
    articles: Iterable[Article],
    primary: list[str],
    secondary: list[str],
    exclude: list[str],
) -> list[Article]:
    """관련성 필터링.

    채택 조건:
    - exclude 키워드 없음 AND
    - primary 키워드 1개 이상 OR (secondary 2개 이상)

    Args:
        primary: 강한 관련성 키워드
        secondary: 약한 관련성 (단독으로는 부족, 2개 이상 일치 필요)
        exclude: 이게 있으면 무조건 제외
    """
    primary_lower = [k.lower() for k in primary]
    secondary_lower = [k.lower() for k in secondary]
    exclude_lower = [k.lower() for k in exclude]

    kept = []
    for a in articles:
        haystack = f"{a.title} {a.summary}".lower()

        if any(k in haystack for k in exclude_lower):
            continue

        primary_hits = sum(1 for k in primary_lower if k in haystack)
        secondary_hits = sum(1 for k in secondary_lower if k in haystack)

        if primary_hits >= 1 or secondary_hits >= 2:
            kept.append(a)

    logger.info("relevance filter: %d 건 채택", len(kept))
    return kept
