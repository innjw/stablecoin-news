"""sources.yaml의 RSS URL을 직접 호출해서 살아있는 것만 verified=true 로 갱신.

사용법:
    python verify_sources.py

조건 (모두 통과해야 verified=true):
1. HTTP 200
2. RSS/Atom XML 파싱 가능
3. 최근 30일 내 기사 1건 이상 (정부기관은 90일 허용)
"""
from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from time import mktime

import feedparser
import yaml

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("verify")

ROOT = Path(__file__).parent
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)


def verify_feed(url: str, max_age_days: int = 30) -> tuple[bool, str]:
    """단일 피드 검증. (verified, reason) 반환."""
    try:
        feed = feedparser.parse(
            url,
            agent=USER_AGENT,
            request_headers={"User-Agent": USER_AGENT},
        )
    except Exception as e:
        return False, f"파싱 예외: {e}"

    status = feed.get("status")
    if status and status >= 400:
        return False, f"HTTP {status}"

    if not feed.entries:
        return False, "기사 없음"

    # 최신 기사 발행일 확인
    cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
    has_recent = False
    for entry in feed.entries[:5]:
        for key in ("published_parsed", "updated_parsed"):
            t = entry.get(key)
            if t:
                try:
                    pub = datetime.fromtimestamp(mktime(t), tz=timezone.utc)
                    if pub >= cutoff:
                        has_recent = True
                        break
                except Exception:
                    pass
        if has_recent:
            break

    if not has_recent:
        # 발행일이 없는 피드도 있으니, entry는 있는데 날짜만 없는 경우는 통과시킴
        no_date = all(
            not e.get("published_parsed") and not e.get("updated_parsed")
            for e in feed.entries[:5]
        )
        if not no_date:
            return False, f"최근 {max_age_days}일 내 기사 없음"

    return True, f"OK ({len(feed.entries)}건)"


def main() -> int:
    sources_path = ROOT / "sources.yaml"
    sources = yaml.safe_load(sources_path.read_text(encoding="utf-8"))

    changed = False

    # direct_rss
    for src in sources.get("direct_rss", []):
        ok, reason = verify_feed(src["url"], max_age_days=30)
        old = src.get("verified")
        src["verified"] = ok
        marker = "✅" if ok else "❌"
        logger.info("%s %s — %s", marker, src["name"], reason)
        if old != ok:
            changed = True

    # regulators (정부 보도자료는 업데이트 빈도가 낮을 수 있어 90일)
    for src in sources.get("regulators", []):
        ok, reason = verify_feed(src["url"], max_age_days=90)
        old = src.get("verified")
        src["verified"] = ok
        marker = "✅" if ok else "❌"
        logger.info("%s %s — %s", marker, src["name"], reason)
        if old != ok:
            changed = True

    if changed:
        # YAML 보존을 위해 직접 쓰는 대신, ruamel 없이 처리하려면 단순 dump
        sources_path.write_text(
            yaml.dump(sources, allow_unicode=True, sort_keys=False, default_flow_style=False),
            encoding="utf-8",
        )
        logger.info("sources.yaml 업데이트 완료")
    else:
        logger.info("변경사항 없음")

    return 0


if __name__ == "__main__":
    sys.exit(main())
