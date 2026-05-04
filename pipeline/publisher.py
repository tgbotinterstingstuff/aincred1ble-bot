"""Публикация постов в Telegram канал через Bot API."""
import logging
import os
import time

import requests

log = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org"


class TelegramPublisher:
    def __init__(self, bot_token: str | None = None, channel_id: str | None = None,
                 parse_mode: str = "HTML", link_preview: bool = True):
        self.token = bot_token or os.environ.get("TELEGRAM_BOT_TOKEN")
        self.channel = channel_id or os.environ.get("TELEGRAM_CHANNEL_ID")
        if not self.token or not self.channel:
            raise RuntimeError("TELEGRAM_BOT_TOKEN или TELEGRAM_CHANNEL_ID не заданы")
        self.parse_mode = parse_mode
        self.link_preview = link_preview

    # Лимит длины сообщения в Telegram
    MAX_LEN = 4096

    def _truncate(self, text: str) -> str:
        if len(text) <= self.MAX_LEN:
            return text
        log.warning(f"Сообщение длиной {len(text)} обрезано до {self.MAX_LEN}")
        return text[: self.MAX_LEN - 5] + "…"

    def send_message(self, text: str, retries: int = 3) -> dict:
        text = self._truncate(text)
        url = f"{TELEGRAM_API}/bot{self.token}/sendMessage"
        payload = {
            "chat_id": self.channel,
            "text": text,
            "parse_mode": self.parse_mode,
            "disable_web_page_preview": not self.link_preview,
        }

        last_err = None
        for attempt in range(retries):
            try:
                r = requests.post(url, json=payload, timeout=20)
                if r.status_code == 429:
                    retry_after = r.json().get("parameters", {}).get("retry_after", 10)
                    log.warning(f"Telegram rate limit, жду {retry_after}с")
                    time.sleep(retry_after + 1)
                    continue
                # Telegram возвращает 400 при ошибке парсинга HTML
                if r.status_code == 400:
                    body = r.text or ""
                    if "can't parse" in body.lower() or "parse" in body.lower():
                        log.warning(f"Ошибка парсинга HTML: {body[:200]}. Отправляю как plain text")
                        payload.pop("parse_mode", None)
                        r = requests.post(url, json=payload, timeout=20)
                r.raise_for_status()
                return r.json()
            except Exception as e:
                last_err = e
                log.warning(f"Telegram ошибка (попытка {attempt + 1}): {e}")
                time.sleep(5)
        raise RuntimeError(f"Не удалось отправить сообщение: {last_err}")
