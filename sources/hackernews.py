"""Сбор топовых постов с Hacker News через официальный API."""
import logging
from datetime import datetime, timezone, timedelta

import requests

log = logging.getLogger(__name__)

HN_API = "https://hacker-news.firebaseio.com/v0"


def _has_keyword(text: str, keywords: list) -> bool:
    if not keywords:
        return True
    text_lower = (text or "").lower()
    return any(k.lower() in text_lower for k in keywords)


def collect(config: dict, freshness_days: int = 3) -> list:
    if not config.get("enabled"):
        return []

    cutoff_ts = (datetime.now(timezone.utc) - timedelta(days=freshness_days)).timestamp()
    min_score = config.get("min_score", 100)
    keywords = config.get("keywords", [])
    items = []

    try:
        # Берём топ-100 stories
        ids = requests.get(f"{HN_API}/topstories.json", timeout=15).json()[:100]
        for story_id in ids:
            try:
                story = requests.get(f"{HN_API}/item/{story_id}.json", timeout=10).json()
                if not story:
                    continue
                if story.get("time", 0) < cutoff_ts:
                    continue
                if story.get("score", 0) < min_score:
                    continue

                title = story.get("title", "")
                if not _has_keyword(title, keywords):
                    continue

                url = story.get("url") or f"https://news.ycombinator.com/item?id={story_id}"
                items.append({
                    "title": title,
                    "url": url,
                    "source": "Hacker News",
                    "summary": title[:500],
                    "raw_text": title,
                    "published_at": datetime.fromtimestamp(story.get("time", 0), timezone.utc).isoformat(),
                    "_meta": {"score": story.get("score", 0), "comments": story.get("descendants", 0)},
                })
            except Exception as e:
                log.debug(f"HN story {story_id} skip: {e}")
    except Exception as e:
        log.warning(f"Hacker News ошибка: {e}")

    log.info(f"Hacker News: собрано {len(items)} материалов")
    return items
