"""Точка входа. Запускается из CI или локально."""
import logging
import os
import re
import sys
import tempfile
from pathlib import Path

import yaml

from pipeline.collector import collect_all
from pipeline.filter import filter_pipeline
from pipeline.writer import GroqClient, write_short_post, write_summary
from pipeline.publisher import TelegramPublisher
from storage import mark_published, stats


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("main")


def load_config() -> dict:
    cfg_path = Path(__file__).parent / "config.yaml"
    with open(cfg_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def safe_filename(title: str, max_len: int = 60) -> str:
    """Преобразует заголовок в имя файла, безопасное для Telegram."""
    cleaned = re.sub(r"[^\w\s\-а-яА-ЯёЁ]", "", title, flags=re.UNICODE).strip()
    cleaned = re.sub(r"\s+", "_", cleaned)
    return (cleaned[:max_len] or "summary").strip("_") or "summary"


def build_summary_file(item: dict, summary_text: str, tmpdir: str) -> str:
    """Сохраняет выжимку в .txt и возвращает путь."""
    title = item.get("title", "Без названия")
    fname = safe_filename(title) + ".txt"
    fpath = os.path.join(tmpdir, fname)

    with open(fpath, "w", encoding="utf-8") as f:
        f.write(f"{title}\n\n")
        f.write(f"Источник: {item.get('source', '')}\n")
        f.write(f"Ссылка: {item.get('url', '')}\n")
        # Если объединённая серия — перечислим все части
        part_urls = item.get("_part_urls")
        if part_urls and len(part_urls) > 1:
            f.write(f"\nЧасти серии:\n")
            for i, url in enumerate(part_urls, 1):
                f.write(f"  {i}. {url}\n")
        f.write("\n" + "=" * 60 + "\n\n")
        f.write(summary_text)
        f.write("\n")

    return fpath


def main() -> int:
    log.info("=" * 60)
    log.info("Запуск AI Cases Bot")
    log.info(f"Статистика: {stats()}")

    config = load_config()

    # 1. Сбор
    items = collect_all(config)
    if not items:
        log.warning("Ничего не собрано из источников. Завершаю.")
        return 0

    # 2. Скоринг и фильтрация
    llm = GroqClient()
    candidates = filter_pipeline(items, llm, config)
    if not candidates:
        log.info("Нет кандидатов выше min_score. Завершаю.")
        return 0

    # 3. Берём топ-N
    posts_per_run = config.get("posts_per_run", 1)
    top = candidates[:posts_per_run]

    # 4. Пишем и публикуем
    tg_cfg = config.get("telegram", {})
    publisher = TelegramPublisher(
        parse_mode=tg_cfg.get("parse_mode", "HTML"),
        link_preview=tg_cfg.get("link_preview", True),
    )

    published = 0
    for item in top:
        try:
            log.info(f"Пишу для: {item['title'][:80]} (score={item['_score']})")

            # 4a. Короткий пост (тизер)
            short_text = write_short_post(item, llm)
            log.info(f"Короткий пост ({len(short_text)} симв.):\n{short_text}")

            # 4b. Подробная выжимка
            summary_text = write_summary(item, llm)
            log.info(f"Выжимка ({len(summary_text)} симв.) сгенерирована")

            # 4c. Caption = короткий пост + ссылка на источник
            url = item.get("url", "")
            full_caption = short_text
            if url:
                full_caption += f'\n\n<a href="{url}">Источник</a>'

            # 4d. Сохраняем выжимку в .txt и отправляем как документ
            with tempfile.TemporaryDirectory() as tmpdir:
                summary_path = build_summary_file(item, summary_text, tmpdir)
                publisher.send_document(summary_path, caption=full_caption)

            mark_published(item["url"], item.get("title", ""), item.get("source", ""))
            published += 1
            log.info(f"✓ Опубликовано: {item['url']}")
        except Exception as e:
            log.exception(f"✗ Ошибка публикации: {e}")
            mark_published(item["url"], item.get("title", ""),
                          item.get("source", "") + " [FAILED]")

    log.info(f"Готово. Опубликовано: {published}/{len(top)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
