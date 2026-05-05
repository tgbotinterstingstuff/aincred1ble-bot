"""LLM-клиенты + написание постов и выжимок.

Двухконтурная схема:
- GroqClient — основной (быстрый, но дневной лимит 100K токенов на free tier)
- GeminiClient — fallback (свободный лимит 1500 запросов/день у gemini-flash)
- FallbackLLMClient — оборачивает обоих: пробует Groq, при 429 переключается на Gemini.
"""
import logging
import os
import time

from prompts import build_short_post_prompt, build_summary_prompt, build_writer_prompt

log = logging.getLogger(__name__)


def _is_rate_limit(err: Exception) -> bool:
    msg = str(err).lower()
    return "rate" in msg or "quota" in msg or "429" in msg or "resource_exhausted" in msg


class GroqClient:
    def __init__(self, api_key=None, model="llama-3.3-70b-versatile"):
        from groq import Groq
        self.api_key = api_key or os.environ.get("GROQ_API_KEY")
        if not self.api_key:
            raise RuntimeError("GROQ_API_KEY не задан")
        self.client = Groq(api_key=self.api_key)
        self.model = model

    def generate(self, prompt, max_tokens=2000, retries=2, thinking=False):
        last_err = None
        for attempt in range(retries):
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.7,
                    max_completion_tokens=max_tokens,
                )
                text = response.choices[0].message.content or ""
                return text.strip()
            except Exception as e:
                last_err = e
                if _is_rate_limit(e):
                    log.warning("Groq rate limit, жду 10с...")
                    time.sleep(10)
                else:
                    log.warning(f"Groq ошибка: {e}")
                    time.sleep(3)
        raise RuntimeError(f"Groq не ответил: {last_err}")


class GeminiClient:
    def __init__(self, api_key=None, model="gemini-2.0-flash-001"):
        from google import genai
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")
        if not self.api_key:
            raise RuntimeError("GEMINI_API_KEY не задан")
        self.client = genai.Client(api_key=self.api_key)
        self.model = model

    @staticmethod
    def _parse_retry_delay(msg: str, default: int = 65) -> int:
        """Извлекает задержку из 'retry in 41.05s' или 'retryDelay': '41s'."""
        import re as _re
        m = _re.search(r"retryDelay['\"]:\s*['\"](\d+)s", msg)
        if m:
            return int(m.group(1)) + 5
        m = _re.search(r"retry in (\d+(?:\.\d+)?)\s*s", msg)
        if m:
            return int(float(m.group(1))) + 5
        return default

    def generate(self, prompt, max_tokens=2000, retries=3, thinking=False):
        from google.genai import types
        last_err = None
        for attempt in range(retries):
            try:
                response = self.client.models.generate_content(
                    model=self.model,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        temperature=0.7,
                        max_output_tokens=max_tokens,
                    ),
                )
                text = (response.text or "").strip()
                if not text:
                    raise RuntimeError("Gemini вернул пустой ответ")
                return text
            except Exception as e:
                last_err = e
                if _is_rate_limit(e):
                    wait = self._parse_retry_delay(str(e), default=65)
                    log.warning(f"Gemini rate limit, жду {wait}с (попытка {attempt+1}/{retries})...")
                    time.sleep(wait)
                else:
                    log.warning(f"Gemini ошибка: {e}")
                    time.sleep(3)
        raise RuntimeError(f"Gemini не ответил: {last_err}")


class FallbackLLMClient:
    """Сначала Groq, при 429 → Gemini. После первого 429 от Groq не тратит на него ретраи в текущем прогоне."""

    def __init__(self):
        self.groq = None
        self.gemini = None
        try:
            self.groq = GroqClient()
            log.info("Groq подключён (основной)")
        except Exception as e:
            log.warning(f"Groq недоступен: {e}")
        try:
            self.gemini = GeminiClient()
            log.info("Gemini подключён (fallback)")
        except Exception as e:
            log.warning(f"Gemini недоступен: {e}")
        if not self.groq and not self.gemini:
            raise RuntimeError("Ни Groq, ни Gemini не настроены — нечем писать")
        self._groq_exhausted = False

    def generate(self, prompt, max_tokens=2000, retries=2, thinking=False):
        # 1) Groq, если жив
        if self.groq and not self._groq_exhausted:
            try:
                return self.groq.generate(prompt, max_tokens=max_tokens, retries=retries)
            except RuntimeError as e:
                if _is_rate_limit(e):
                    log.warning("Groq лимит исчерпан → дальше через Gemini")
                    self._groq_exhausted = True
                else:
                    log.warning(f"Groq отказ: {e} → пробую Gemini")
        # 2) Gemini fallback
        if self.gemini:
            return self.gemini.generate(prompt, max_tokens=max_tokens, retries=retries)
        raise RuntimeError("Оба LLM-канала отвалились (Groq+Gemini)")


def _strip_markdown_code_blocks(text: str) -> str:
    """Убирает оборачивающие тройные бэктики если LLM их добавил."""
    bt = chr(96) * 3
    return text.replace(bt + "html", "").replace(bt + "txt", "").replace(bt, "").strip()


def write_short_post(item: dict, llm_client) -> str:
    """Пишет пост-разбор (600-900 символов) для Telegram caption. Без ссылки и хэштегов."""
    prompt = build_short_post_prompt(item)
    text = llm_client.generate(prompt, max_tokens=700)
    return _strip_markdown_code_blocks(text)


def write_summary(item: dict, llm_client) -> str:
    """Пишет подробную выжимку для .txt файла."""
    prompt = build_summary_prompt(item)
    text = llm_client.generate(prompt, max_tokens=3000)
    return _strip_markdown_code_blocks(text)


def write_post(item: dict, llm_client) -> str:
    """DEPRECATED: используй write_short_post + write_summary."""
    return write_short_post(item, llm_client)
