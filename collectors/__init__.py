"""뉴스 수집기 패키지."""
from .rss import collect_rss
from .google_news import collect_google_news
from .naver import collect_naver

__all__ = ["collect_rss", "collect_google_news", "collect_naver"]
