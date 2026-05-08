"""기사 데이터 모델. 모든 수집기는 이 형식으로 반환한다."""
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional


@dataclass
class Article:
    """단일 뉴스 기사."""
    title: str                         # 기사 제목
    url: str                           # 원문 URL (정규화 후)
    source: str                        # 매체명 또는 수집기 이름
    published_at: Optional[datetime]   # 발행 시각 (없으면 None)
    summary: str = ""                  # 원문 요약/디스크립션
    raw_url: str = ""                  # 정규화 전 원본 URL (디버깅용)
    weight: float = 1.0                # 매체 가중치

    # LLM 처리 후 채워지는 필드
    llm_summary: str = ""              # LLM 한 줄 요약
    category: str = ""                 # 규제/시장/기술/발행사/기타
    importance: int = 0                # 1~5 (5가 가장 중요)
    is_relevant: bool = True           # 스테이블코인 관련성

    def to_dict(self) -> dict:
        d = asdict(self)
        if self.published_at:
            d["published_at"] = self.published_at.isoformat()
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Article":
        if d.get("published_at") and isinstance(d["published_at"], str):
            d["published_at"] = datetime.fromisoformat(d["published_at"])
        return cls(**d)
