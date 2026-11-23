# Telegram <-> Google Chat Support Gateway

Отказоустойчивый микросервис-шлюз для маршрутизации обращений технической поддержки между **Telegram** и **Google Chat** (треды в едином пространстве операторов), спроектированный по принципу **Outbound-only / Zero Ingress** без low-code платформ и внешних LLM.

## Архитектура

```text
[Telegram Bot API] <----(getUpdates Polling)----+
                                                |---> [support-gateway (Hardened Docker, 256MB)]
[Google Chat / PubSub] <---(Service Account)----+        |-- SQLite WAL (Thread Map + Anti-Echo + Offset)
                                                         |-- 127.0.0.1:9090 (/healthz & /metrics)
```

### Инженерные решения
* **Zero Ingress Surface:** исходящие соединения для обоих направлений (`getUpdates` long-polling в Telegram и `Pull`-подписка GCP Pub/Sub). Серверу не требуются открытые входящие порты, публичный IP, Nginx и TLS-сертификаты.
* **Infrastructure as Code (Terraform):** вся облачная обвязка GCP (`Pub/Sub` топик/подписка, IAM для `chat-api-push@system.gserviceaccount.com` и сервисный аккаунт) описана в [`terraform/`](terraform/).
* **Thread-safe & Idempotent:** потокобезопасное обновление OAuth-токенов, изолированные `requests.Session` на поток, хранение Telegram `offset` и дедупликация сообщений в SQLite (WAL mode) с автоочисткой TTL.
* **Observability:** структурированные JSON-логи в `stdout` (с ротацией в Compose), Prometheus-метрики на `/metrics` и реальный `/healthz`, проверяющий активность обоих воркеров.
* **Hardened Container & Supply Chain Security:** `read_only: true`, `cap_drop: [ALL]`, `no-new-privileges`, `appuser`, зафиксированные версии зависимостей, Hadolint, Trivy (`fs` + `image`), доставка неизменяемого образа через **GHCR**.
* **Функции для операторов Google Chat:**
  * Сообщения в треде, начинающиеся с `!`, считаются внутренними заметками и не отправляются клиенту.
  * Команда `/close` закрывает тред и уведомляет клиента в Telegram.

## Развёртывание инфраструктуры (Terraform)

1. Инициализируйте и примените инфраструктуру в GCP:
   ```bash
   cd terraform
   cp terraform.tfvars.example terraform.tfvars
   # Укажите project_id в terraform.tfvars
   terraform init
   terraform apply
   ```
2. Создайте JSON-ключ для сервисного аккаунта из вывода `service_account_email` и положите его в `secrets/google-sa.json`.
3. В GCP Console → **Google Chat API → Configuration** подключите приложение к созданному топику (`pubsub_topic_id` из вывода Terraform) через **Cloud Pub/Sub** *(настройка самого Chat App на стороне Google пока не имеет официального ресурса в Terraform Google Provider)*.

## Локальный запуск и тесты

1. Скопируйте `.env.example` в `.env` и заполните переменные (`TG_BOT_TOKEN`, `GCHAT_SPACE_ID`, `PUBSUB_SUBSCRIPTION`).
2. Запустите линтер и тесты (API замоканы):
   ```bash
   pip install -r requirements.txt -r requirements-dev.txt
   flake8 src/ tests/
   pytest tests/ -v
   ```
3. Запустите контейнер:
   ```bash
   docker compose up -d --build
   ```

## CI/CD Pipeline

* **CI (`.github/workflows/ci.yml`):** `flake8` → `pytest` → `docker compose config` → `terraform fmt/validate` → `Hadolint` → `Trivy` (репозиторий + собранный образ) → публикация образа в **GHCR** (`sha-<commit>` и `latest`).
* **CD (`.github/workflows/deploy.yml`):** ручной запуск (`workflow_dispatch`) с выбором тега образа (удобно для rollback), доставка `docker-compose.yml` через SCP, безопасная запись секретов и `docker compose pull && docker compose up -d --no-build`.