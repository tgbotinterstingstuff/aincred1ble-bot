"""Запускает все включённые сборщики и возвращает общий список материалов."""
import logging
from sources import (
    collect_rss,
    collect_reddit,
    collect_hackernews,
    collect_youtube,
    collect_arxiv,
    collect_habr,
    collect_github_trending,
)

log = logging.getLogger(__name__)


def collect_all(config: dict) -> list:
    freshness = config.get("freshness_days", 3)
    all_items = []

    collectors = [
        ("rss_feeds", collect_rss),
        ("reddit", collect_reddit),
        ("hackernews", collect_hackernews),
        ("youtube", collect_youtube),
        ("arxiv", collect_arxiv),
        ("habr", collect_habr),
        ("github_trending", collect_github_trending),
    ]

    for key, fn in collectors:
        cfg = config.get(key, {})
        try:
            items = fn(cfg, freshness_days=freshness)
            all_items.extend(items)
        except Exception as e:
            log.exception(f"Сборщик {key} упал: {e}")

    log.info(f"Всего собрано: {len(all_items)} материалов из всех источников")
    return all_items
