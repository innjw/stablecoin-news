"""블로그용 Markdown 생성기.

main.py가 이미 카테고리별로 그룹핑·정렬해놓은 articles dict를 받아서
site/src/content/blog/YYYY-MM-DD.md 파일로 떨군다.
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from pathlib import Path

KST = timezone(timedelta(hours=9))
ROOT = Path(__file__).resolve().parent.parent
POSTS_DIR = ROOT / "site" / "src" / "content" / "blog"


def _escape_yaml(s: str) -> str:
    """front matter 값에 들어갈 문자열의 큰따옴표 이스케이프."""
    return s.replace('"', '\\"')


def render_markdown(categories: dict, total_count: int) -> str:
    """categories는 main.py의 render_html이 만든 ordered dict.
    구조: {"규제": [Article, ...], "발행사": [...], ...}
    """
    today = datetime.now(KST)
    date_iso = today.strftime("%Y-%m-%d")
    date_label = today.strftime("%Y년 %m월 %d일")

    # 헤드라인: 가장 중요한 기사의 제목
    top_article = None
    for items in categories.values():
        if items:
            top_article = items[0]
            break
    headline = _escape_yaml(top_article.title) if top_article else "오늘의 스테이블코인 소식"

    # front matter
    lines = [
        "---",
        f'title: "{date_label} 국내 스테이블코인 브리핑"',
        f'description: "{headline}"',
        f"pubDate: {date_iso}",
        f"tags: [\"스테이블코인\", \"국내\", \"데일리\"]",
        "---",
        "",
        f"오늘 정리된 소식은 총 **{total_count}건**입니다.",
        "",
    ]

    # 카테고리별 본문
    for cat, items in categories.items():
        if not items:
            continue
        lines.append(f"## {cat}")
        lines.append("")
        for a in items:
            time_str = (
                a.published_at.astimezone(KST).strftime("%H:%M")
                if a.published_at else ""
            )
            time_prefix = f"`{time_str}` " if time_str else ""

            # 기사 제목 + 출처 + 시각
            lines.append(f"### {time_prefix}[{a.title}]({a.url})")
            lines.append("")
            lines.append(f"*출처: {a.source}*")
            lines.append("")

            # LLM 요약 (있으면)
            if getattr(a, "summary", None):
                lines.append(a.summary)
                lines.append("")

        lines.append("")

    return "\n".join(lines)


def publish_to_blog(categories: dict, total_count: int) -> Path:
    """블로그 글 .md 파일을 site/src/content/blog/에 생성."""
    POSTS_DIR.mkdir(parents=True, exist_ok=True)
    date_iso = datetime.now(KST).strftime("%Y-%m-%d")
    file_path = POSTS_DIR / f"{date_iso}.md"
    file_path.write_text(
        render_markdown(categories, total_count),
        encoding="utf-8",
    )
    return file_path
