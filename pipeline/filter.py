"""Filter and scoring."""
import logging
import re
import time

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
            response = llm_client.generate(prompt, max_tokens=50, retries=1)
            time.sleep(7)
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
    log.info(f"Фильтр: {len(items)} материалов")
    items = deduplicate_by_url(items)
    items = filter_unpublished(items)
    log.info(f"После фильтра: {len(items)}")
    if not items:
        return []
    max_to_score = config.get("max_candidates_to_score", 25)
    items = score_with_llm(items, llm_client, max_to_score=max_to_score)
    min_score = config.get("min_score", 5)
    items = [i for i in items if i.get("_score", 0) >= min_score]
    items.sort(key=lambda x: x.get("_score", 0), reverse=True)
    log.info(f"Выше min_score={min_score}: {len(items)}")
    return items
