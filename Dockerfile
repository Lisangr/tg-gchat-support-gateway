FROM python:3.12-slim-bookworm

LABEL org.opencontainers.image.title="tg-gchat-support-gateway" \
      org.opencontainers.image.description="Outbound-only Telegram <-> Google Chat support gateway" \
      org.opencontainers.image.source="https://github.com/OWNER/tg-gchat-support-gateway"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

RUN groupadd --system appuser && useradd --system --gid appuser appuser

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/

RUN mkdir -p /app/data /app/secrets && chown -R appuser:appuser /app

USER appuser

EXPOSE 9090

CMD ["python", "-m", "src.main"]