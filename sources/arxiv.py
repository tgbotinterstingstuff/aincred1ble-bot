"""Сбор свежих статей с ArXiv через официальный API."""
import logging
from datetime import datetime, timezone, timedelta

import feedparser

log = logging.getLogger(__name__)

ARXIV_API = "http://export.arxiv.org/api/query"


def collect(config: dict, freshness_days: int = 3) -> list:
    if not config.get("enabled"):
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(days=freshness_days)
    categories = config.get("categories", ["cs.AI"])
    max_results = config.get("max_results", 10)
    keywords = [k.lower() for k in config.get("keywords", [])]

    cat_query = "+OR+".join(f"cat:{c}" for c in categories)
    url = f"{ARXIV_API}?search_query={cat_query}&sortBy=submittedDate&sortOrder=descending&max_results={max_results * 3}"

    items = []
    try:
        feed = feedparser.parse(url)
        for entry in feed.entries:
            try:
                published = datetime.strptime(entry.published, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
            except Exception:
                continue
            if published < cutoff:
                continue

            summary = entry.get("summary", "").strip()
            title = entry.get("title", "").strip()

            # Фильтр по прикладным ключевым словам
            if keywords:
                full = (title + " " + summary).lower()
                if not any(k in full for k in keywords):
                    continue

            items.append({
                "title": title,
                "url": entry.link,
                "source": "ArXiv",
                "summary": summary[:500],
                "raw_text": summary[:3000],
                "published_at": published.isoformat(),
            })
            if len(items) >= max_results:
                break
    except Exception as e:
        log.warning(f"ArXiv ошибка: {e}")

    log.info(f"ArXiv: собрано {len(items)} статей")
    return items
