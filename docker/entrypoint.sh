#!/usr/bin/env bash
set -Eeuo pipefail

APP_OLLAMA_HOST="http://ollama_android:11434"
APP_PORT="${API_PORT:-8085}"

for i in $(seq 1 60); do
  if curl -fsS "${APP_OLLAMA_HOST}/api/tags" >/dev/null 2>&1; then
    break
  fi
  sleep 1
  if [[ "${i}" -eq 60 ]]; then
    echo "Timed out waiting for Ollama to become available at ${APP_OLLAMA_HOST}" >&2
    exit 1
  fi
done

exec uvicorn app.main:app --host 0.0.0.0 --port "${APP_PORT}" --workers "${UVICORN_WORKERS:-1}"
