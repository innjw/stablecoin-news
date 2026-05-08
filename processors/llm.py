"""LLM 기반 기사 처리.

배치 처리로 한 번에 여러 기사를 분류·요약·점수화. JSON 모드 사용.
Claude Haiku로 비용 최소화.
"""
from __future__ import annotations

import json
import logging
import os
import re
from typing import Iterable

from anthropic import Anthropic

from models import Article

logger = logging.getLogger(__name__)

MODEL = "claude-haiku-4-5-20251001"
BATCH_SIZE = 15  # 한 번에 처리할 기사 수


SYSTEM_PROMPT = """당신은 한국 금융·블록체인 뉴스 큐레이터입니다.
입력으로 들어온 기사 목록 각각에 대해 다음을 판단해 JSON으로만 출력하세요.

각 기사에 대해:
- is_relevant: 한국 스테이블코인 시장·정책·기술과 직접 관련 있는가? (true/false)
  · 단순 비트코인 가격 기사는 false. 스테이블코인이 핵심 주제일 때만 true.
  · 한국은행 CBDC, 원화 스테이블, 발행사 동향, 규제는 true.
- category: "규제" | "발행사" | "시장동향" | "기술" | "기타"
- importance: 1~5 정수 (5: 한국 시장에 직접 영향, 1: 가십)
- llm_summary: 한국어 한 줄 요약 (50자 이내). 핵심만.

출력 형식 (반드시 이 형식 그대로):
{
  "results": [
    {"id": 0, "is_relevant": true, "category": "규제", "importance": 4, "llm_summary": "..."},
    ...
  ]
}

JSON 외의 텍스트는 절대 출력하지 마세요."""


def enrich_with_llm(articles: list[Article]) -> list[Article]:
    """LLM으로 기사를 분류·요약·점수화. 원본 리스트를 in-place 갱신."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        logger.warning("ANTHROPIC_API_KEY 미설정 — LLM 단계 건너뜀")
        return articles

    client = Anthropic(api_key=api_key)

    for i in range(0, len(articles), BATCH_SIZE):
        batch = articles[i:i + BATCH_SIZE]
        try:
            results = _call_llm(client, batch)
        except Exception as e:
            logger.warning("LLM 호출 실패 (batch %d): %s", i, e)
            continue

        for r in results:
            idx = r.get("id")
            if not isinstance(idx, int) or not (0 <= idx < len(batch)):
                continue
            a = batch[idx]
            a.is_relevant = bool(r.get("is_relevant", True))
            a.category = str(r.get("category", "기타"))
            a.importance = int(r.get("importance", 1))
            a.llm_summary = str(r.get("llm_summary", "")).strip()

    relevant_count = sum(1 for a in articles if a.is_relevant)
    logger.info("LLM 처리 완료: %d/%d 관련성 있음", relevant_count, len(articles))
    return articles


def _call_llm(client: Anthropic, batch: list[Article]) -> list[dict]:
    """단일 배치 LLM 호출."""
    items = []
    for i, a in enumerate(batch):
        items.append({
            "id": i,
            "title": a.title,
            "summary": a.summary[:300],  # 너무 길면 자름
            "source": a.source,
        })

    user_message = f"기사 목록:\n{json.dumps(items, ensure_ascii=False, indent=2)}"

    response = client.messages.create(
        model=MODEL,
        max_tokens=2000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    )

    text = response.content[0].text.strip()
    # 혹시 코드 펜스가 있으면 제거
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)

    parsed = json.loads(text)
    return parsed.get("results", [])
