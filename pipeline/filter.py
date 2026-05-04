"""Filter and scoring."""
import logging
import re

from storage import filter_unpublished
from prompts import build_scoring_prompt

log = logging.getLogger(__name__)


def deduplicate_by_url(items):
    seen = set()
    out = []
    for item in items:
        url = item.get("url", "").strip().lower()
        if not url or url in seen:
            continue
        seen.add(url)
        out.append(item)
    return out


def score_with_llm(items, llm_client, max_to_score=25):
    items = [i for i in items if i.get("title") or i.get("raw_text")]
    AI_KEYS = ["ai", "llm", "gpt", "claude", "gemini", "agent", "промпт", "нейросет", "ии"]
    def relevance(item):
        text = (item.get("title", "") + " " + item.get("summary", "")).lower()
        return sum(1 for k in AI_KEYS if k in text)
    items = sorted(items, key=relevance, reverse=True)[:max_to_score]
    scored = []
    for item in items:
        try:
            prompt = build_scoring_prompt(item)
            response = llm_client.generate(prompt, max_tokens=50)
            m = re.search(r"\b(10(?:\.0+)?|[0-9](?:\.\d+)?)\b", response)
            score = float(m.group(1)) if m else 0.0
            item["_score"] = score
            scored.append(item)
            title_short = (item.get("title") or "")[:80]
            log.info(f"Скор {score}/10: {title_short}")
        except Exception as e:
            log.warning(f"Скоринг упал: {e}")
            item["_score"] = 0.0
            scored.append(item)
    return scored


def filter_pipeline(items, llm_client, config):
    log.info(f"Фильтр: вход {len(items)} материалов")
    items = deduplicate_by_url(items)
    log.info(f"После дедупа: {len(items)}")
    items = filter_unpublished(items)
    log.info(f"После исключения опубликованного: {len(items)}")
    if not items:
        return []
    max_to_score = config.get("max_candidates_to_score", 25)
    items = score_with_llm(items, llm_client, max_to_score=max_to_score)
    min_score = config.get("min_score", 5)
    items = [i for i in items if i.get("_score", 0) >= min_score]
    items.sort(key=lambda x: x.get("_score", 0), reverse=True)
    log.info(f"После скоринга (min_score={min_score}): {len(items)} прошли")
    return items
"""Фильтрация и скоринг кандидатов."""
import logging
import re

from storage import filter_unpublished
from prompts import build_scoring_prompt

log = logging.getLogger(__name__)


def deduplicate_by_url(items: list) -> list:
    """Убирает дубли по URL внутри одного запуска."""
    seen = set()
    out = []
    for item in items:
        url = item.get("url", "").strip().lower()
        if not url or url in seen:
            continue
        seen.add(url)
        out.append(item)
    return out


def score_with_llm(items: list, llm_client, max_to_score: int = 25) -> list:
    """Пропускает кандидатов через LLM-скоринг. Возвращает с полем _score."""
    # Сначала отбросим те, у кого нет ни заголовка, ни текста
    items = [i for i in items if i.get("title") or i.get("raw_text")]

    # Сортируем по упоминаниям AI-ключевых слов, чтобы скорить самые релевантные
    AI_KEYS = ["ai", "llm", "gpt", "claude", "gemini", "agent", "промпт", "нейросет", "ии"]
    def relevance(item):
        text = (item.get("title", "") + " " + item.get("summary", "")).lower()
        return sum(1 for k in AI_KEYS if k in text)

    items = sorted(items, key=relevance, reverse=True)[:max_to_score]

    scored = []
    for item in items:
        try:
            prompt = build_scoring_prompt(item)
            response = llm_client.generate(prompt, max_tokens=10)
            # Достаём первое число из ответа (включая дробные части)
            m = re.search(r"\b(10(?:\.0+)?|[0-9](?:\.\d+)?)\b", response)
            score = float(m.group(1)) if m else 0.0
            item["_score"] = score
            scored.append(item)
            log.info(f"Скор {score}/10: {item['title'][:80]}")
        except Exception as e:
            log.warning(f"Скоринг упал для {item.get('title', '?')[:50]}: {e}")
            item["_score"] = 0.0
            scored.append(item)

    return scored


def filter_pipeline(items: list, llm_client, config: dict) -> list:
    """Полный фильтр: дедуп → выкинуть опубликованное → LLM-скоринг → фильтр по min_score."""
    log.info(f"Фильтр: вход {len(items)} материалов")

    items = deduplicate_by_url(items)
    log.info(f"После дедупа по URL: {len(items)}")

    items = filter_unpublished(items)
    log.info(f"После исключения опубликованного: {len(items)}")

    if not items:
        return []

    max_to_score = config.get("max_candidates_to_score", 25)
    items = score_with_llm(items, llm_client, max_to_score=max_to_score)

    min_score = config.get("min_score", 7)
    items = [i for i in items if i.get("_score", 0) >= min_score]
    items.sort(key=lambda x: x.get("_score", 0), reverse=True)

    log.info(f"После скоринга (min_score={min_score}): {len(items)} прошли")
    return items
