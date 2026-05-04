"""Сбор трендовых GitHub-репозиториев через парсинг страницы trending."""
import logging
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

log = logging.getLogger(__name__)


def collect(config: dict, freshness_days: int = 3) -> list:
    if not config.get("enabled"):
        return []

    language = config.get("language", "python")
    since = config.get("since", "daily")
    topics = [t.lower() for t in config.get("topics", [])]

    url = f"https://github.com/trending/{language}?since={since}"
    items = []

    try:
        r = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        for article in soup.select("article.Box-row")[:25]:
            link_el = article.select_one("h2 a")
            if not link_el:
                continue
            repo_path = link_el.get("href", "").strip("/")
            if not repo_path:
                continue
            repo_url = f"https://github.com/{repo_path}"
            title = repo_path.replace("/", " / ")

            desc_el = article.select_one("p")
            description = desc_el.get_text(strip=True) if desc_el else ""

            # Фильтр по AI-теме
            full_text = (title + " " + description).lower()
            if topics and not any(t in full_text for t in topics):
                continue

            items.append({
                "title": title,
                "url": repo_url,
                "source": f"GitHub Trending ({since})",
                "summary": description[:500],
                "raw_text": f"{title}\n\n{description}"[:2000],
                "published_at": datetime.now(timezone.utc).isoformat(),
            })
    except Exception as e:
        log.warning(f"GitHub Trending ошибка: {e}")

    log.info(f"GitHub Trending: собрано {len(items)} репозиториев")
    return items
