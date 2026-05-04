"""Фильтрация и скоринг кандидатов."""
import logging
import re
import time

from storage import filter_unpublished
from prompts import build_scoring_prompt

log = logging.getLogger(__name__)


# Паттерны определения «Часть N» в заголовке
# Для каждого паттерна group(1) должна давать номер части
PART_PATTERNS = [
    re.compile(r"\bчасть\s+(\d+)(?:\s*\(\s*из\s*(\d+)\s*\))?", re.IGNORECASE),
    re.compile(r"\bчасть\s+(\d+)\s+из\s+(\d+)", re.IGNORECASE),
    re.compile(r"\bч\.\s*(\d+)\b", re.IGNORECASE),
    re.compile(r"\bpart\s+(\d+)(?:\s+of\s+(\d+))?", re.IGNORECASE),
    re.compile(r"\((\d+)\s*[/\\]\s*(\d+)\)"),
]


def detect_part(title: str):
    """Возвращает (base_title, part_num) или (title, None) если не серия."""
    if not title:
        return title, None
    for pat in PART_PATTERNS:
        m = pat.search(title)
        if m:
            try:
                part_num = int(m.group(1))
            except (ValueError, IndexError):
                continue
            base = pat.sub("", title).strip()
            base = re.sub(r"\s+", " ", base).strip(" .,:;-—")
            return base.lower(), part_num
    return title.lower(), None


def merge_series(items: list) -> list:
    """Группирует серии по нормализованному заголовку.

    Если в одной серии 2+ частей — объединяет их в один item.
    Если только 1 часть с маркером серии — пропускает её (ждём остальные части).
    """
    series = {}     # base_title -> [(part_num, item), ...]
    standalone = []
    skipped_singletons = 0

    for item in items:
        title = item.get("title", "")
        base, part_num = detect_part(title)
        if part_num is None:
            standalone.append(item)
        else:
            series.setdefault(base, []).append((part_num, item))

    merged = []
    for base, parts in series.items():
        if len(parts) < 2:
            skipped_singletons += 1
            log.info(f"Пропускаю единичную часть серии: {parts[0][1].get('title', '')[:80]}")
            continue
        parts.sort(key=lambda x: x[0])
        first_item = parts[0][1]
        last_item = parts[-1][1]
        # Объединяем тексты с разделителями
        merged_text_blocks = []
        for part_num, item in parts:
            block = f"\n\n────── ЧАСТЬ {part_num} ──────\n\n"
            block += (item.get("raw_text") or item.get("summary") or "").strip()
            merged_text_blocks.append(block)
        merged_raw = "".join(merged_text_blocks)
        # Берём название базы (без маркера часть N) с заглавной буквы
        nice_title = base.capitalize() + f" (объединено из {len(parts)} частей)"
        merged_item = {
            "title": nice_title,
            "url": last_item.get("url", ""),  # ссылка на последнюю часть
            "source": last_item.get("source", "") + " [merged]",
            "summary": (first_item.get("summary") or "")[:500],
            "raw_text": merged_raw[:20000],
            "published_at": last_item.get("published_at", ""),
            "_part_count": len(parts),
            "_part_urls": [p[1].get("url", "") for p in parts],
        }
        merged.append(merged_item)
        log.info(f"Объединил серию ({len(parts)} частей): {nice_title[:80]}")

    if skipped_singletons:
        log.info(f"Пропущено единичных частей серий: {skipped_singletons}")

    return standalone + merged


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


# Стоп-слова для дедупликации тем — не учитываются при сравнении
_STOPWORDS = {
    "и", "в", "на", "с", "по", "для", "из", "не", "к", "о", "об", "от", "до",
    "при", "за", "над", "под", "у", "что", "как", "это", "его", "её", "их",
    "или", "но", "а", "же", "ли", "бы", "ещё",
    "the", "a", "an", "of", "to", "in", "for", "on", "is", "are", "with",
    "how", "why", "what", "this", "that", "as", "by", "be", "was", "were",
    "and", "or", "but", "not", "if", "then", "than", "from", "into",
}


def _title_words(title: str) -> set:
    """Возвращает множество значимых слов из заголовка (lower, без стоп-слов и коротких)."""
    if not title:
        return set()
    cleaned = re.sub(r"[^\w\sа-яА-ЯёЁ]", " ", title.lower())
    words = cleaned.split()
    return {w for w in words if len(w) > 2 and w not in _STOPWORDS}


def topic_deduplicate(items: list, similarity_threshold: float = 0.45) -> list:
    """Убирает почти-дубликаты по теме (похожие заголовки от разных источников).

    Считаем долю общих значимых слов от меньшего набора. Если ≥ threshold —
    дубликаты. Оставляем item с большим _score; в оставшийся пишем _alt_sources
    и _alt_urls для возможного использования в выжимке.
    """
    if len(items) < 2:
        return items

    # Сортируем по убыванию скора, чтобы сначала шли «лучшие»
    items = sorted(items, key=lambda x: x.get("_score", 0), reverse=True)
    keep = []
    duplicates_count = 0

    for item in items:
        words = _title_words(item.get("title", ""))
        is_dup = False
        for kept in keep:
            kept_words = _title_words(kept.get("title", ""))
            if not words or not kept_words:
                continue
            common = len(words & kept_words)
            if common == 0:
                continue
            overlap = common / min(len(words), len(kept_words))
            if overlap >= similarity_threshold:
                # Это та же тема — оставляем «kept» (он с большим скором)
                kept.setdefault("_alt_sources", []).append(item.get("source", ""))
                kept.setdefault("_alt_urls", []).append(item.get("url", ""))
                is_dup = True
                duplicates_count += 1
                log.info(
                    f"Тема-дубликат: «{item.get('title','')[:60]}» "
                    f"≈ «{kept.get('title','')[:60]}» (overlap {overlap:.0%})"
                )
                break
        if not is_dup:
            keep.append(item)

    if duplicates_count:
        log.info(f"Дедуплицировано тем: {duplicates_count}")
    return keep


def score_with_llm(items: list, llm_client, max_to_score: int = 25) -> list:
    """Пропускает кандидатов через LLM-скоринг. Возвращает с полем _score."""
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
            time.sleep(2)  # лёгкий дроссель чтобы не упереться в RPM
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


def filter_pipeline(items: list, llm_client, config: dict) -> list:
    """Полный фильтр: дедуп → объединение серий → выкинуть опубликованное → LLM-скоринг."""
    log.info(f"Фильтр: вход {len(items)} материалов")

    items = deduplicate_by_url(items)
    log.info(f"После дедупа: {len(items)}")

    items = merge_series(items)
    log.info(f"После объединения серий: {len(items)}")

    items = filter_unpublished(items)
    log.info(f"После исключения опубликованного: {len(items)}")

    if not items:
        return []

    max_to_score = config.get("max_candidates_to_score", 25)
    items = score_with_llm(items, llm_client, max_to_score=max_to_score)

    min_score = config.get("min_score", 5)
    items = [i for i in items if i.get("_score", 0) >= min_score]
    items.sort(key=lambda x: x.get("_score", 0), reverse=True)
    log.info(f"Выше min_score={min_score}: {len(items)}")

    # Тематическая дедупликация — после скоринга, чтобы оставить лучший по скору
    items = topic_deduplicate(items)
    log.info(f"После тематической дедупликации: {len(items)}")

    return items
