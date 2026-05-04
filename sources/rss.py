"""Сбор материалов из RSS-фидов."""
import logging
from datetime import datetime, timezone, timedelta

import feedparser
from dateutil import parser as date_parser

log = logging.getLogger(__name__)


def _parse_date(entry) -> datetime:
    for key in ("published", "updated", "created"):
        val = entry.get(key)
        if val:
            try:
                d = date_parser.parse(val)
                if d.tzinfo is None:
                    d = d.replace(tzinfo=timezone.utc)
                return d
            except Exception:
                pass
    return datetime.now(timezone.utc)


def collect(config: dict, freshness_days: int = 3) -> list:
    if not config.get("enabled"):
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(days=freshness_days)
    items = []

    for feed_cfg in config.get("feeds", []):
        name = feed_cfg["name"]
        url = feed_cfg["url"]
        try:
            log.info(f"RSS: парсю {name}")
            feed = feedparser.parse(url)
            for entry in feed.entries[:30]:
                published = _parse_date(entry)
                if published < cutoff:
                    continue

                summary = entry.get("summary", "") or entry.get("description", "")
                # Срезаем HTML-теги по-простому
                if "<" in summary:
                    import re
                    summary = re.sub(r"<[^>]+>", " ", summary)
                    summary = re.sub(r"\s+", " ", summary).strip()

                items.append({
                    "title": entry.get("title", "").strip(),
                    "url": entry.get("link", "").strip(),
                    "source": f"RSS / {name}",
                    "summary": summary[:500],
                    "raw_text": summary[:3000],
                    "published_at": published.isoformat(),
                })
        except Exception as e:
            log.warning(f"RSS {name} ошибка: {e}")

    log.info(f"RSS: собрано {len(items)} свежих материалов")
    return items
