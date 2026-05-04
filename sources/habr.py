"""Сбор статей из хаба Habr через RSS."""
import logging
from datetime import datetime, timezone, timedelta

import feedparser
import re
from dateutil import parser as date_parser

log = logging.getLogger(__name__)


def collect(config: dict, freshness_days: int = 3) -> list:
    if not config.get("enabled"):
        return []

    hub = config.get("hub", "artificial_intelligence")
    cutoff = datetime.now(timezone.utc) - timedelta(days=freshness_days)
    items = []

    url = f"https://habr.com/ru/rss/hub/{hub}/all/?fl=ru"
    try:
        feed = feedparser.parse(url)
        for entry in feed.entries[:30]:
            try:
                published = date_parser.parse(entry.published)
                if published.tzinfo is None:
                    published = published.replace(tzinfo=timezone.utc)
            except Exception:
                continue
            if published < cutoff:
                continue

            summary = entry.get("summary", "")
            if "<" in summary:
                summary = re.sub(r"<[^>]+>", " ", summary)
                summary = re.sub(r"\s+", " ", summary).strip()

            items.append({
                "title": entry.get("title", "").strip(),
                "url": entry.get("link", "").strip(),
                "source": "Habr",
                "summary": summary[:500],
                "raw_text": summary[:3000],
                "published_at": published.isoformat(),
            })
    except Exception as e:
        log.warning(f"Habr ошибка: {e}")

    log.info(f"Habr: собрано {len(items)} статей")
    return items
