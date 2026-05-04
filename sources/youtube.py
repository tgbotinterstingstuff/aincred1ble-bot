"""Сбор свежих видео с YouTube-каналов + извлечение транскриптов.

Использует RSS-фид YouTube для метаданных (без API-ключа) и youtube-transcript-api
для текста видео.
"""
import logging
import re
from datetime import datetime, timezone, timedelta

import feedparser
import requests
from dateutil import parser as date_parser

log = logging.getLogger(__name__)


def _resolve_channel_id(handle: str) -> str | None:
    """Получает channel_id по handle (@name) через парсинг страницы канала."""
    try:
        url = f"https://www.youtube.com/{handle}"
        r = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        # channel_id запрятан в исходнике страницы
        m = re.search(r'"channelId":"(UC[a-zA-Z0-9_-]{22})"', r.text)
        if m:
            return m.group(1)
    except Exception as e:
        log.warning(f"YouTube: не смог найти channelId для {handle}: {e}")
    return None


def _get_transcript(video_id: str) -> str:
    """Достаёт текстовый транскрипт видео. Сначала пробует русский, потом английский."""
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        api = YouTubeTranscriptApi()
        # Пробуем разные языки
        for langs in (["ru"], ["en"], ["en-US", "en-GB"]):
            try:
                fetched = api.fetch(video_id, languages=langs)
                # fetched это итерируемый объект с .text у каждого сегмента
                text = " ".join(snippet.text for snippet in fetched)
                return text[:8000]  # ограничим, чтобы не раздувать промпт
            except Exception:
                continue
    except ImportError:
        log.error("youtube-transcript-api не установлен")
    except Exception as e:
        log.debug(f"Транскрипт {video_id} недоступен: {e}")
    return ""


def collect(config: dict, freshness_days: int = 3) -> list:
    if not config.get("enabled"):
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(days=freshness_days)
    max_per = config.get("max_videos_per_channel", 3)
    items = []

    for ch in config.get("channels", []):
        name = ch["name"]
        handle = ch.get("handle")
        ch_id = ch.get("channel_id")

        if not ch_id and handle:
            ch_id = _resolve_channel_id(handle)
            if not ch_id:
                continue

        try:
            feed_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={ch_id}"
            log.info(f"YouTube: {name}")
            feed = feedparser.parse(feed_url)
            count = 0
            for entry in feed.entries:
                if count >= max_per:
                    break
                try:
                    published = date_parser.parse(entry.published)
                    if published.tzinfo is None:
                        published = published.replace(tzinfo=timezone.utc)
                except Exception:
                    continue
                if published < cutoff:
                    continue

                video_id = entry.get("yt_videoid") or entry.get("id", "").split(":")[-1]
                title = entry.get("title", "")
                description = ""
                if hasattr(entry, "media_description"):
                    description = entry.media_description
                elif hasattr(entry, "summary"):
                    description = entry.summary

                # Достаём транскрипт — это даёт реальное содержание видео
                transcript = _get_transcript(video_id)
                raw = f"{description}\n\n{transcript}".strip()

                items.append({
                    "title": title,
                    "url": entry.link,
                    "source": f"YouTube / {name}",
                    "summary": (description or title)[:500],
                    "raw_text": raw[:6000],
                    "published_at": published.isoformat(),
                })
                count += 1
        except Exception as e:
            log.warning(f"YouTube {name} ошибка: {e}")

    log.info(f"YouTube: собрано {len(items)} видео")
    return items
