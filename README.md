# Telegram <-> Google Chat Support Gateway

Отказоустойчивый микросервис-шлюз для прямой двусторонней маршрутизации сообщений между **Telegram** и **Google Chat** в формате сквозного моста **1 чат Telegram <-> 1 пространство Google Chat** (без тредов, промежуточных low-code платформ вроде n8n и внешних LLM).

## Архитектурные особенности (Outbound-only & Zero Ingress)

    [Telegram Bot API] <----(getUpdates Polling)----+
                                                    |---> [support-gateway (Docker, 256MB)]
    [Google Chat / PubSub] <---(Service Account)----+
                                    |
                       (SQLite: Space Map + Anti-Echo)

### Ключевые инженерные решения
- **Zero Ingress Surface (без открытых портов):** Шлюз забирает сообщения из Telegram через `getUpdates` (Long Polling), а события из Google Chat — через Pull-подписку GCP Pub/Sub. Серверу не нужен белый IP, Nginx, SSL-сертификаты или Cloudflare Tunnel.
- **Сквозной роутинг 1-на-1:** Сообщения из Telegram публикуются напрямую в общий поток пространства Google Chat в формате `@username: текст`, а ответы из Google Chat возвращаются в привязанный Telegram-чат (фиксируется через `TG_CHAT_ID` или автоматически в SQLite `space_bindings`).
- **Google Service Account (Chat App):** Интеграция работает от имени сервисного аккаунта и Chat-приложения, а не личной учётной записи сотрудника. Это устраняет привязку к конкретному человеку и решает проблему уведомлений.
- **Совместимость с форматами Google Chat:** Поддерживаются как классические события Chat API (`message`), так и события Workspace Add-on (`chat.messagePayload.message`) с автоматической очисткой `@упоминания` через `argumentText`.
- **Anti-Echo и Дедупликация:** Игнорируются сообщения с типом отправителя `BOT` (и боты Telegram `is_bot`), а все обработанные ID сообщений фиксируются в SQLite (`processed_messages`), исключая зацикливание и повторную доставку при ретраях.
- **Внутренние заметки:** Сообщения в Google Chat, текст которых начинается с `!` (после `@упоминания`), считаются внутренними комментариями и **не отправляются** в Telegram.
- **Hardened Container:** Запуск от непривилегированного пользователя (`appuser`), запрет повышения привилегий (`no-new-privileges`), жёсткий лимит памяти `256M`, ключ сервисного аккаунта монтируется только на чтение (`:ro`), встроенный `healthcheck` по heartbeat-файлу.

> **Примечание по работе в Google Chat:** В групповых пространствах на обычных аккаунтах Google бот получает события только при явном `@упоминании` (в корпоративном Google Workspace чтение всех сообщений пространства без `@упоминания` включается через одобрение скоупа `chat.app.messages.readonly` и Workspace Events API).

---

## Переменные окружения

| Переменная | Обязательна | Описание |
|---|---|---|
| `TG_BOT_TOKEN` | Да | Токен Telegram-бота от `@BotFather` |
| `GCHAT_SPACE_ID` | Да | ID пространства Google Chat (`spaces/AAAAxxxxxxx`) |
| `PUBSUB_SUBSCRIPTION` | Нет* | Полное имя Pull-подписки GCP Pub/Sub (`projects/.../subscriptions/...`). *Без неё работает только направление TG -> GChat |
| `TG_CHAT_ID` | Нет | ID целевого Telegram-чата/группы (например, `-100xxxxxxxxxx`). Если не задан, привязывается первый написавший чат |
| `GOOGLE_APPLICATION_CREDENTIALS` | В Docker задано | Путь к JSON-ключу сервисного аккаунта (в контейнере `/app/secrets/google-sa.json`) |
| `DB_PATH` | В Docker задано | Путь к локальной базе SQLite (в контейнере `/app/data/gateway.db`) |

---

## Быстрый старт (Локально)

1. Скопируйте `.env.example` в `.env` и заполните переменные.
2. Положите JSON-ключ сервисного аккаунта Google в `secrets/google-sa.json` (файл должен существовать до старта Docker).
3. Убедитесь, что в GCP Pub/Sub выданы права:
   - Сервисному аккаунту бота — роль **Pub/Sub Subscriber** на подписку.
   - Системному агенту Google Chat (`chat-api-push@system.gserviceaccount.com` и/или `service-<PROJECT_NUMBER>@gcp-sa-gsuiteaddons.iam.gserviceaccount.com`) — роль **Pub/Sub Publisher** на топик.
4. Запустите юнит-тесты (не требуют реальных токенов, внешние API замоканы):

    pip install -r requirements.txt pytest
    pytest tests/ -v

5. Поднимите сервис в Docker и проверьте логи:

    docker compose up -d --build
    docker compose logs -f

---

## CI/CD (GitHub Actions)

- **CI (`.github/workflows/ci.yml`):** запускается автоматически на `push` и `pull_request` в `main` — прогоняет `flake8`, `pytest`, валидирует `docker compose config -q` и собирает тестовый Docker-образ.
- **CD (`.github/workflows/deploy.yml`):** ручной деплой на сервер через `workflow_dispatch` (копирует проект по SCP/SSH в `/opt/support-gateway`, разворачивает секреты в `.env` и `secrets/google-sa.json`, перезапускает контейнер).
  - Необходимые **GitHub Actions Secrets**: `SERVER_HOST`, `SERVER_USER`, `SERVER_SSH_KEY`, `TG_BOT_TOKEN`, `TG_CHAT_ID`, `GCHAT_SPACE_ID`, `PUBSUB_SUBSCRIPTION`, `GOOGLE_SA_KEY_JSON`.