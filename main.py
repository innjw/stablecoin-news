"""스테이블코인 뉴스 데일리 메인 파이프라인.

흐름:
1. sources.yaml 로드
2. 각 채널에서 기사 수집 (Google News + Naver + 직접 RSS + 정부기관)
3. 관련성 필터 (키워드)
4. URL 정규화 + 중복 제거
5. 어제 이미 보낸 URL 제외
6. LLM 처리 (분류·요약·중요도)
7. 중요도 기준 정렬 + 카테고리 그룹핑
8. HTML 렌더링
9. 이메일 발송
10. 발송 이력 저장
"""
from __future__ import annotations

import json
import logging
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader, select_autoescape

from collectors import collect_google_news, collect_naver, collect_rss
from models import Article
from processors import dedupe, enrich_with_llm, filter_relevant, normalize_url
from senders import send_email
from senders.blog import publish_to_blog

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("main")

ROOT = Path(__file__).parent
KST = timezone(timedelta(hours=9))


def load_yaml(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_subscribers() -> dict:
    """구독자 정보 로드.

    우선순위:
    1. SUBSCRIBERS_YAML 환경변수 (퍼블릭 레포 운영 시)
    2. 로컬 subscribers.yaml 파일 (개발용)
    """
    env_yaml = os.environ.get("SUBSCRIBERS_YAML")
    if env_yaml:
        logger.info("구독자: 환경변수 SUBSCRIBERS_YAML 사용")
        return yaml.safe_load(env_yaml)

    path = ROOT / "subscribers.yaml"
    if path.exists():
        logger.info("구독자: subscribers.yaml 파일 사용")
        return load_yaml(path)

    raise RuntimeError(
        "구독자 정보를 찾을 수 없음. SUBSCRIBERS_YAML 환경변수 또는 "
        "subscribers.yaml 파일 중 하나가 필요합니다."
    )


def collect_all(sources: dict) -> list[Article]:
    """모든 채널에서 기사 수집."""
    all_articles: list[Article] = []

    # 1. 구글 뉴스
    gn = sources.get("meta_search", {}).get("google_news", {})
    if gn.get("enabled"):
        all_articles.extend(collect_google_news(
            queries=gn.get("queries", []),
            base_url=gn.get("base_url", "https://news.google.com/rss/search"),
            params=gn.get("params"),
        ))

    # 2. 네이버 뉴스
    nv = sources.get("meta_search", {}).get("naver_news", {})
    if nv.get("enabled"):
        all_articles.extend(collect_naver(
            queries=nv.get("queries", []),
            display=nv.get("display", 50),
            sort=nv.get("sort", "date"),
        ))

    # 3. 직접 RSS (verified=true 인 것만)
    for src in sources.get("direct_rss", []):
        if src.get("verified") is False:
            logger.info("스킵 (verified=false): %s", src["name"])
            continue
        all_articles.extend(collect_rss(
            name=src["name"],
            url=src["url"],
            weight=src.get("weight", 1.0),
        ))

    # 4. 정부기관 (verified=true 인 것만, 키워드 필터 적용)
    for src in sources.get("regulators", []):
        if src.get("verified") is False:
            continue
        all_articles.extend(collect_rss(
            name=src["name"],
            url=src["url"],
            weight=src.get("weight", 1.0),
            keyword_filter=src.get("keyword_filter"),
        ))

    logger.info("전체 수집: %d건", len(all_articles))
    return all_articles


def filter_by_date(articles: list[Article], hours: int = 24) -> list[Article]:
    """최근 N시간 이내 기사만 남김. 발행일 없는 건 통과."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    kept = []
    for a in articles:
        if a.published_at is None:
            kept.append(a)
        elif a.published_at >= cutoff:
            kept.append(a)
    logger.info("최근 %d시간 필터: %d건", hours, len(kept))
    return kept


def load_sent_urls(path: Path) -> set[str]:
    """발송 이력 (최근 30일치만) 로드."""
    if not path.exists():
        return set()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        cutoff = datetime.now(timezone.utc) - timedelta(days=30)
        return {
            url for url, ts in data.items()
            if datetime.fromisoformat(ts) >= cutoff
        }
    except Exception as e:
        logger.warning("발송 이력 로드 실패: %s", e)
        return set()


def save_sent_urls(path: Path, sent: set[str]) -> None:
    """발송 이력 저장 (URL → 발송 시각)."""
    existing = {}
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            existing = {}
    now_iso = datetime.now(timezone.utc).isoformat()
    for url in sent:
        existing[url] = now_iso
    # 30일 넘은 것 정리
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    cleaned = {
        url: ts for url, ts in existing.items()
        if datetime.fromisoformat(ts) >= cutoff
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(cleaned, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def render_html(articles: list[Article], reply_to: str) -> tuple[str, str]:
    """HTML 본문 + 제목 생성."""
    env = Environment(
        loader=FileSystemLoader(str(ROOT / "templates")),
        autoescape=select_autoescape(["html"]),
    )
    template = env.get_template("daily.html")

    # 카테고리별 그룹핑
    categories = defaultdict(list)
    category_order = ["규제", "발행사", "시장동향", "기술", "기타"]

    for a in articles:
        # 표시용 발행 시각
        a.published_at_str = (
            a.published_at.astimezone(KST).strftime("%H:%M")
            if a.published_at else ""
        )
        cat = a.category or "기타"
        categories[cat].append(a)

    # 카테고리 내에서 importance 내림차순
    for cat in categories:
        categories[cat].sort(key=lambda x: -x.importance)

    # 정해진 순서대로 정렬
    ordered = {
        c: categories[c] for c in category_order if c in categories
    }

    today = datetime.now(KST)
    date_label = today.strftime("%Y년 %m월 %d일 (%A)")

    subject = f"[스테이블코인 데일리] {today.strftime('%m/%d')} — {len(articles)}건"

    html = template.render(
        subject=subject,
        date_label=date_label,
        categories=ordered,
        total_count=len(articles),
        reply_to=reply_to,
    )
    return subject, html, ordered


def main() -> int:
    sources = load_yaml(ROOT / "sources.yaml")
    subs_config = load_subscribers()

    # 1. 수집
    articles = collect_all(sources)
    if not articles:
        logger.warning("수집된 기사 없음 — 중단")
        return 1

    # 2. 최근 24시간 필터
    articles = filter_by_date(articles, hours=24)

    # 3. 키워드 관련성 필터
    rel = sources.get("relevance_keywords", {})
    articles = filter_relevant(
        articles,
        primary=rel.get("primary", []),
        secondary=rel.get("secondary", []),
        exclude=sources.get("exclude_keywords", []),
    )

    # 4. URL 정규화 + 중복 제거
    articles = dedupe(articles)

    # 5. 발송 이력 제외
    sent_path = ROOT / "data" / "sent_urls.json"
    already_sent = load_sent_urls(sent_path)
    articles = [a for a in articles if a.url not in already_sent]
    logger.info("이력 제외 후: %d건", len(articles))

    if not articles:
        logger.info("새 기사 없음 — 발송 생략")
        return 0

    # 6. LLM 처리
    articles = enrich_with_llm(articles)

    # LLM이 단 한 건도 처리 못 한 경우 (크레딧 부족, API 다운 등) 감지
    llm_processed = sum(1 for a in articles if a.category)  # category 채워졌으면 처리됨
    llm_failure = llm_processed == 0
    if llm_failure:
        logger.warning(
            "LLM 처리 0건 — API 실패로 추정. fallback 모드로 발송 강행."
        )
        # fallback: 모든 기사 importance=2, category=기타로 강제
        for a in articles:
            a.importance = 2
            a.category = "기타"
            a.llm_summary = a.summary[:80] if a.summary else ""

    # 관련성 없다고 판단된 건 제거
    articles = [a for a in articles if a.is_relevant]
    logger.info("LLM 관련성 필터 후: %d건", len(articles))

    if not articles:
        logger.info("LLM 처리 후 남은 기사 없음 — 발송 생략")
        return 0

    # 진단용: importance 분포 출력
    from collections import Counter
    dist = Counter(a.importance for a in articles)
    logger.info("importance 분포: %s", dict(sorted(dist.items())))

    # 가십 컷 - importance 1만 제외 (단, 전체가 1뿐이면 전부 채택해서 발송은 함)
    high_quality = [a for a in articles if a.importance >= 2]
    if high_quality:
        articles = high_quality
        logger.info("importance >= 2 컷 적용: %d건", len(articles))
    else:
        logger.warning(
            "전체 기사가 importance 1 — LLM 채점 비정상 가능성. "
            "컷 미적용, 전체 발송"
        )

    # 너무 많으면 상위 30개로 컷
    articles.sort(key=lambda x: -x.importance)
    articles = articles[:30]
    logger.info("최종 발송 대상: %d건", len(articles))

    # 0건이면 발송 생략 (빈 메일 방지)
    if not articles:
        logger.warning("최종 발송 대상 0건 — 발송 생략")
        return 0

    # 7. 렌더링
    sender = subs_config["sender"]
    subject, html = render_html(articles, reply_to=sender["reply_to"])

    # 7-1. 블로그용 Markdown 생성
    try:
        blog_path = publish_to_blog(ordered_categories, len(articles))
        logger.info("블로그 글 생성: %s", blog_path)
    except Exception as e:
        logger.warning("블로그 글 생성 실패 (이메일 발송은 계속 진행): %s", e)

    # 8. 발송
    recipients = [
        s["email"] for s in subs_config["subscribers"]
        if s.get("active", True)
    ]
    if not recipients:
        logger.warning("활성 구독자 없음")
        return 1

    ok = send_email(
        to=recipients,
        subject=subject,
        html=html,
        from_name=sender["from_name"],
        from_email=sender["from_email"],
        reply_to=sender.get("reply_to"),
    )

    # 9. 발송 이력 저장 (성공 시에만)
    if ok:
        save_sent_urls(sent_path, {a.url for a in articles})

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
