#!/usr/bin/env bash
set -Eeuo pipefail

APP_OLLAMA_HOST="${OLLAMA_HOST:-http://127.0.0.1:11434}"
APP_PORT="${API_PORT:-8080}"

export OLLAMA_HOST="0.0.0.0"
ollama serve >/var/log/ollama.log 2>&1 &
OLLAMA_PID=$!

cleanup() {
  if kill -0 "${OLLAMA_PID}" >/dev/null 2>&1; then
    kill "${OLLAMA_PID}" || true
    wait "${OLLAMA_PID}" || true
  fi
}
trap cleanup EXIT

export OLLAMA_HOST="${APP_OLLAMA_HOST}"

for i in $(seq 1 60); do
  if curl -fsS "${APP_OLLAMA_HOST}/api/tags" >/dev/null 2>&1; then
    break
  fi
  sleep 1
  if ! kill -0 "${OLLAMA_PID}" >/dev/null 2>&1; then
    echo "Ollama process exited unexpectedly" >&2
    exit 1
  fi
  if [[ "${i}" -eq 60 ]]; then
    echo "Timed out waiting for Ollama to start" >&2
    exit 1
  fi
done

exec uvicorn app.main:app --host 0.0.0.0 --port "${APP_PORT}" --workers "${UVICORN_WORKERS:-1}"
