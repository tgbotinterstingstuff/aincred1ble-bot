# AI Cases Bot — автономный Telegram-канал про крутые кейсы ИИ

Бот сам собирает свежие материалы из десятка источников, оценивает их через LLM, пишет посты в повествовательном стиле на русском и публикует в твой Telegram-канал. Полностью бесплатно, работает на GitHub Actions.

## Как это работает

```
[RSS, Reddit, HackerNews,    →  [Сбор]  →  [Дедуп +    →  [LLM пишет   →  [Telegram
 YouTube, ArXiv, Habr,                      LLM-скоринг   пост]            канал]
 GitHub Trending]                           крутости]
                                                  ↑
                                            [SQLite база
                                             опубликованного]
```

Каждые 8 часов GitHub Actions запускает `main.py`. Скрипт обходит все источники, отсеивает уже опубликованное, скорит оставшееся через Gemini (0–10 «крутости»), берёт топ-N, пишет пост и публикует. База хранится прямо в репозитории как SQLite-файл и коммитится после каждого запуска.

## Что нужно для запуска (один раз, ~15 минут)

### Шаг 1. Создать Telegram-канал и бота

1. Открой Telegram. Найди в поиске **@BotFather**.
2. Отправь ему `/newbot`. Введи имя бота (любое, например `AI Cases Bot`) и username (должен заканчиваться на `bot`, например `my_ai_cases_bot`).
3. BotFather пришлёт **HTTP API token** вида `1234567890:ABCdef...`. **Сохрани его** — это `TELEGRAM_BOT_TOKEN`.
4. Создай новый канал в Telegram (любое имя, можно публичный или приватный). В настройках канала → Администраторы → Добавить администратора → найди своего бота по username → дай ему права **«Публиковать сообщения»**. Остальное не нужно.
5. Узнай ID канала:
   - **Если канал публичный** — `TELEGRAM_CHANNEL_ID` = `@username_канала` (со собачкой).
   - **Если приватный** — отправь любое сообщение в канал, потом открой `https://api.telegram.org/bot<ТОКЕН>/getUpdates` в браузере, найди там `"chat":{"id":-100xxxxxxxxxx`. Это число (с минусом) и есть ID.

### Шаг 2. Получить ключ Gemini API

1. Зайди на https://aistudio.google.com/ под Google-аккаунтом.
2. Слева → **Get API key** → **Create API key** → выбери проект (или создай новый).
3. Скопируй ключ. Это `GEMINI_API_KEY`. Карта не нужна, бесплатный тариф включается автоматически.

### Шаг 3. Залить код на GitHub

1. Создай аккаунт на github.com (если ещё нет).
2. Нажми **New repository** → имя любое (например `ai-cases-bot`) → **Public** (для бесплатных Actions без лимита) → Create.
3. На странице репо нажми **uploading an existing file** и перетащи туда **всё содержимое папки `ai_cases_bot/`** (включая папки `sources/`, `pipeline/`, `.github/`). Commit.

   Если умеешь работать с git из терминала:
   ```bash
   cd ai_cases_bot
   git init
   git add .
   git commit -m "init"
   git branch -M main
   git remote add origin https://github.com/ТВОЙ_USERNAME/ai-cases-bot.git
   git push -u origin main
   ```

### Шаг 4. Положить ключи в GitHub Secrets

В репозитории: **Settings** → слева **Secrets and variables** → **Actions** → **New repository secret**. Создай три штуки:

| Имя секрета | Значение |
|---|---|
| `GEMINI_API_KEY` | ключ из Google AI Studio |
| `TELEGRAM_BOT_TOKEN` | токен от BotFather |
| `TELEGRAM_CHANNEL_ID` | `@username_канала` или `-100xxxxxxxxxx` |

### Шаг 5. Запустить вручную и проверить

1. В репозитории: вкладка **Actions** → слева выбери **Publish AI Cases** → справа кнопка **Run workflow** → **Run workflow**.
2. Подожди 1–3 минуты, открой запуск, посмотри логи. Если всё ок — в канале появится первый пост.
3. Дальше бот будет запускаться автоматически по расписанию (по умолчанию 3 раза в сутки).

### Шаг 6 (опционально). Подкрутить под себя

Открой `config.yaml` в репозитории прямо в браузере (карандашик «Edit»). Там можно:
- **Включить/выключить источники** (`enabled: true/false`).
- **Сменить частоту** в `.github/workflows/post.yml` — поменяй cron-выражение (`0 */6 * * *` = каждые 6 часов).
- **Поменять `posts_per_run`** — сколько постов за один запуск.
- **Поднять/опустить `min_score`** — насколько строгая фильтрация.
- **Добавить YouTube-каналы** в секции `youtube.channels`.

После сохранения изменений в браузере — следующий запуск сразу подхватит.

Стиль постов меняется в `prompts.py` — в строке `WRITER_PROMPT`.

## Локальный запуск (для тестов)

Если хочешь сначала прогнать локально, не публикуя:

```bash
cd ai_cases_bot
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt

# Положи ключи в переменные окружения
# Windows PowerShell:
$env:GEMINI_API_KEY="..."
$env:TELEGRAM_BOT_TOKEN="..."
$env:TELEGRAM_CHANNEL_ID="@..."

python main.py
```

Чтобы только посмотреть, что бы он опубликовал, без отправки в канал — закомментируй строку `publisher.send_message(post_text)` в `main.py`.

## Структура проекта

```
ai_cases_bot/
├── main.py                      # точка входа
├── config.yaml                  # настройки источников и фильтров
├── prompts.py                   # промпты для LLM (стиль постов)
├── storage.py                   # SQLite — что уже публиковали
├── requirements.txt             # зависимости Python
├── sources/                     # сборщики материалов
│   ├── rss.py                   #   RSS-фиды (Anthropic, OpenAI, ...)
│   ├── reddit.py                #   Reddit JSON API
│   ├── hackernews.py            #   Hacker News API
│   ├── youtube.py               #   YouTube + транскрипты видео
│   ├── arxiv.py                 #   ArXiv научные статьи
│   ├── habr.py                  #   Habr хаб AI
│   └── github_trending.py       #   GitHub Trending
├── pipeline/
│   ├── collector.py             # запускает все сборщики
│   ├── filter.py                # дедуп + LLM-скоринг
│   ├── writer.py                # обёртка Gemini + написание поста
│   └── publisher.py             # отправка в Telegram
└── .github/workflows/post.yml   # cron на GitHub Actions
```

## Лимиты бесплатного тарифа

| Сервис | Лимит | Сколько использует бот |
|---|---|---|
| Telegram Bot API | безлимит | ~3 запроса/день |
| Google Gemini 2.5 Flash | 1500 запросов/день | ~30 (скоринг 25 + написание 3) |
| GitHub Actions (public repo) | безлимит минут | ~3 минуты × 3 запуска = 9 мин/день |
| YouTube transcripts | без ключа, без лимита | свободно |

С большим запасом, всё бесплатно.

## Если что-то сломалось

- **Ничего не публикуется и в логах `Нет кандидатов выше min_score`** — опусти `min_score` в `config.yaml` до 5–6.
- **Telegram ошибка `chat not found`** — проверь, что бот добавлен админом в канал, и что `TELEGRAM_CHANNEL_ID` корректный.
- **Gemini ошибка `quota exceeded`** — подожди день или включи фоллбэк на Groq (см. `pipeline/writer.py`).
- **GitHub Actions перестал запускаться** — если репо неактивно 60 дней, GitHub отключает cron. Сделай любой коммит.
- **Качество постов не нравится** — отредактируй `WRITER_PROMPT` в `prompts.py`, добавь примеры хороших постов.

## Безопасность

- Ключи лежат в GitHub Secrets, не в коде. В логах workflow они автоматически маскируются.
- Никогда не коммить `.env` файл — он в `.gitignore`.
- Если случайно зальёшь ключ в публичный репо — отзови его в AI Studio / BotFather и сгенерируй новый.

## Расширения на будущее

- Добавить картинки к постам (Gemini Flash умеет генерить промпты для DALL-E / Stable Diffusion API)
- Парсить публичные Telegram-каналы через `t.me/s/имя_канала`
- Добавить еженедельный дайджест («лучшие 5 кейсов недели»)
- Сделать веб-дашборд со статистикой
- Добавить фоллбэк на Groq при упоре в лимит Gemini
