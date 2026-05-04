"""Wrapper around Groq API."""
import logging
import os
import time

from prompts import build_writer_prompt

log = logging.getLogger(__name__)


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
                msg = str(e).lower()
                if "rate" in msg or "quota" in msg or "429" in msg:
                    log.warning("Rate limit, жду 10с...")
                    time.sleep(10)
                else:
                    log.warning(f"LLM ошибка: {e}")
                    time.sleep(3)
        raise RuntimeError(f"LLM не ответил: {last_err}")


# Backwards-compat alias — main.py импортирует GeminiClient
GeminiClient = GroqClient


def write_post(item, llm_client):
    prompt = build_writer_prompt(item)
    text = llm_client.generate(prompt, max_tokens=2000)
    bt = chr(96) * 3
    text = text.replace(bt + "html", "").replace(bt, "").strip()
    return text
