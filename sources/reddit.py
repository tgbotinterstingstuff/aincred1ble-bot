"""Сбор топовых постов из сабреддитов через публичный JSON API (без авторизации)."""
import logging
from datetime import datetime, timezone, timedelta

import requests

log = logging.getLogger(__name__)


def collect(config: dict, freshness_days: int = 3) -> list:
    if not config.get("enabled"):
        return []

    headers = {"User-Agent": config.get("user_agent", "ai-cases-bot/1.0")}
    cutoff_ts = (datetime.now(timezone.utc) - timedelta(days=freshness_days)).timestamp()
    min_score = config.get("min_score", 100)
    top_n = config.get("top_n", 10)
    items = []

    for sub in config.get("subreddits", []):
        try:
            url = f"https://www.reddit.com/r/{sub}/top.json?t=week&limit={top_n}"
            log.info(f"Reddit: r/{sub}")
            resp = requests.get(url, headers=headers, timeout=15)
            resp.raise_for_status()
            data = resp.json()

            for child in data.get("data", {}).get("children", []):
                p = child.get("data", {})
                if p.get("created_utc", 0) < cutoff_ts:
                    continue
                if p.get("score", 0) < min_score:
                    continue
                if p.get("over_18"):
                    continue
                if p.get("stickied"):
                    continue

                title = p.get("title", "")
                selftext = p.get("selftext", "")
                external_url = p.get("url_overridden_by_dest") or p.get("url", "")
                permalink = "https://reddit.com" + p.get("permalink", "")

                # Если у поста есть внешняя ссылка (не на reddit) — это часто кейс/инструмент
                final_url = external_url if (external_url and "reddit.com" not in external_url) else permalink

                items.append({
                    "title": title,
                    "url": final_url,
                    "source": f"Reddit / r/{sub}",
                    "summary": (selftext or title)[:500],
                    "raw_text": f"{title}\n\n{selftext}"[:3000],
                    "published_at": datetime.fromtimestamp(p.get("created_utc", 0), timezone.utc).isoformat(),
                    "_meta": {"score": p.get("score", 0), "comments": p.get("num_comments", 0)},
                })
        except Exception as e:
            log.warning(f"Reddit r/{sub} ошибка: {e}")

    log.info(f"Reddit: собрано {len(items)} материалов")
    return items
