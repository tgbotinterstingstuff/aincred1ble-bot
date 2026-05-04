"""Точка входа. Запускается из CI или локально."""
import logging
import sys
from pathlib import Path

import yaml

from pipeline.collector import collect_all
from pipeline.filter import filter_pipeline
from pipeline.writer import GeminiClient, write_post
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
    llm = GeminiClient()
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
            log.info(f"Пишу пост для: {item['title'][:80]} (score={item['_score']})")
            post_text = write_post(item, llm)
            log.info(f"Готовый пост ({len(post_text)} символов):\n{post_text}\n")

            publisher.send_message(post_text)
            mark_published(item["url"], item.get("title", ""), item.get("source", ""))
            published += 1
            log.info(f"✓ Опубликовано: {item['url']}")
        except Exception as e:
            log.exception(f"✗ Ошибка публикации: {e}")
            # Помечаем как опубликованное, чтобы не зацикливаться на сломанном материале
            mark_published(item["url"], item.get("title", ""), item.get("source", "") + " [FAILED]")

    log.info(f"Готово. Опубликовано: {published}/{len(top)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
