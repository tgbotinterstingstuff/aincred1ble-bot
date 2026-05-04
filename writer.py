"""Обёртка над Gemini API — скоринг и написание постов."""
import logging
import os
import time

from prompts import build_writer_prompt

log = logging.getLogger(__name__)


class GeminiClient:
    """Минимальная обёртка над google-genai SDK с ретраями и обработкой лимитов."""

    def __init__(self, api_key: str | None = None, model: str = "gemini-2.5-flash"):
        from google import genai

        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")
        if not self.api_key:
            raise RuntimeError("GEMINI_API_KEY не задан")
        self.client = genai.Client(api_key=self.api_key)
        self.model = model

    def generate(self, prompt: str, max_tokens: int = 2000, retries: int = 3) -> str:
        from google.genai import types

        last_err = None
        for attempt in range(retries):
            try:
                response = self.client.models.generate_content(
                    model=self.model,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        max_output_tokens=max_tokens,
                        temperature=0.7,
                    ),
                )
                text = response.text or ""
                return text.strip()
            except Exception as e:
                last_err = e
                msg = str(e).lower()
                if "rate" in msg or "quota" in msg or "429" in msg:
                    wait = 30 * (attempt + 1)
                    log.warning(f"Rate limit, жду {wait}с...")
                    time.sleep(wait)
                else:
                    log.warning(f"LLM ошибка (попытка {attempt + 1}): {e}")
                    time.sleep(5)
        raise RuntimeError(f"LLM не ответил после {retries} попыток: {last_err}")


def write_post(item: dict, llm_client: GeminiClient) -> str:
    """Пишет готовый пост по материалу."""
    prompt = build_writer_prompt(item)
    text = llm_client.generate(prompt, max_tokens=2000)
    # Срезаем возможные markdown-блоки от модели
    text = text.replace("```html", "").replace("```", "").strip()
    return text
