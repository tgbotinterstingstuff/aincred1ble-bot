"""Сборщики материалов из разных источников.

Каждый сборщик возвращает список словарей единого формата:
{
    "title": str,
    "url": str,
    "source": str,
    "summary": str,        # короткое описание
    "raw_text": str,       # полный доступный текст
    "published_at": str,   # ISO-дата
}
"""
from .rss import collect as collect_rss
from .reddit import collect as collect_reddit
from .hackernews import collect as collect_hackernews
from .youtube import collect as collect_youtube
from .arxiv import collect as collect_arxiv
from .habr import collect as collect_habr
from .github_trending import collect as collect_github_trending

__all__ = [
    "collect_rss",
    "collect_reddit",
    "collect_hackernews",
    "collect_youtube",
    "collect_arxiv",
    "collect_habr",
    "collect_github_trending",
]
