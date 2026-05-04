"""Публикация постов в Telegram канал через Bot API."""
import logging
import os
import time

import requests

log = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org"


class TelegramPublisher:
    # Лимиты Telegram
    MAX_MESSAGE_LEN = 4096
    MAX_CAPTION_LEN = 1024

    def __init__(self, bot_token: str | None = None, channel_id: str | None = None,
                 parse_mode: str = "HTML", link_preview: bool = True):
        self.token = bot_token or os.environ.get("TELEGRAM_BOT_TOKEN")
        self.channel = channel_id or os.environ.get("TELEGRAM_CHANNEL_ID")
        if not self.token or not self.channel:
            raise RuntimeError("TELEGRAM_BOT_TOKEN или TELEGRAM_CHANNEL_ID не заданы")
        self.parse_mode = parse_mode
        self.link_preview = link_preview

    def _truncate(self, text: str, max_len: int) -> str:
        if len(text) <= max_len:
            return text
        log.warning(f"Текст длиной {len(text)} обрезан до {max_len}")
        return text[: max_len - 5] + "…"

    def send_message(self, text: str, retries: int = 3) -> dict:
        text = self._truncate(text, self.MAX_MESSAGE_LEN)
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
                if r.status_code == 400:
                    body = r.text or ""
                    if "can't parse" in body.lower() or "parse" in body.lower():
                        log.warning(f"Ошибка парсинга HTML: {body[:200]}. Без parse_mode")
                        payload.pop("parse_mode", None)
                        r = requests.post(url, json=payload, timeout=20)
                r.raise_for_status()
                return r.json()
            except Exception as e:
                last_err = e
                log.warning(f"Telegram ошибка (попытка {attempt + 1}): {e}")
                time.sleep(5)
        raise RuntimeError(f"Не удалось отправить сообщение: {last_err}")

    def send_document(self, file_path: str, caption: str | None = None,
                      retries: int = 3) -> dict:
        """Отправляет файл (.txt и т.д.) с опциональной подписью.

        Caption ограничен 1024 символами в Telegram.
        """
        url = f"{TELEGRAM_API}/bot{self.token}/sendDocument"
        if caption:
            caption = self._truncate(caption, self.MAX_CAPTION_LEN)

        last_err = None
        for attempt in range(retries):
            try:
                with open(file_path, "rb") as f:
                    files = {"document": f}
                    data = {"chat_id": self.channel}
                    if caption:
                        data["caption"] = caption
                        data["parse_mode"] = self.parse_mode
                    r = requests.post(url, data=data, files=files, timeout=60)

                if r.status_code == 429:
                    retry_after = r.json().get("parameters", {}).get("retry_after", 10)
                    log.warning(f"Telegram rate limit, жду {retry_after}с")
                    time.sleep(retry_after + 1)
                    continue

                if r.status_code == 400:
                    body = r.text or ""
                    if "parse" in body.lower():
                        log.warning(f"HTML parse error в caption, отправляю без parse_mode")
                        with open(file_path, "rb") as f2:
                            files = {"document": f2}
                            data.pop("parse_mode", None)
                            r = requests.post(url, data=data, files=files, timeout=60)

                r.raise_for_status()
                return r.json()
            except Exception as e:
                last_err = e
                log.warning(f"sendDocument ошибка (попытка {attempt + 1}): {e}")
                time.sleep(5)
        raise RuntimeError(f"Не удалось отправить документ: {last_err}")
