FROM python:3.13-slim

# Provide image-level defaults; docker-compose runtime env overrides these.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_HOME=/app \
    PORT=8000 \
    APP_NAME=sbn-zaac \
    FLASK_DEBUG=0 \
    LIVE_GUNICORN_INSTANCES=-1

WORKDIR ${APP_HOME}

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

COPY . .

RUN chmod +x /app/_app_entry

EXPOSE 8000

ENTRYPOINT ["/app/_app_entry"]
