# Contract Extractor API

Локальный сервис извлечения JSON из текста договора (без табличной части). Сервис использует FastAPI, валидирует ответы по JSON Schema и при необходимости обращается к Ollama для LLM-поддержки.

## Контейнеры и образа
- **`ollama`** — официальный образ `ollama/ollama` с GPU-поддержкой. Отвечает за запуск локальной LLM и хранение скачанных моделей в отдельном Docker-томе. Клиент API поддерживает как новый эндпоинт `/api/chat`, так и старый `/api/generate`, поэтому совместим с разными версиями демона. Чтобы контейнер действительно получил доступ к GPU, Compose-файл запрашивает устройства `nvidia` и прокидывает переменные `NVIDIA_VISIBLE_DEVICES=all` и `NVIDIA_DRIVER_CAPABILITIES=compute,utility`; убедитесь, что на хосте установлен NVIDIA Container Toolkit и команда `docker info | grep -i nvidia` показывает поддержку GPU. В противном случае Ollama автоматически перейдёт в CPU-режим, что заметно снижает скорость генерации.
- **`ollama-pull`** — вспомогательный контейнер на базе `curlimages/curl`, который дожидается старта Ollama и инициирует загрузку выбранной модели.
- **`api`** — образ FastAPI-сервиса. Собирается в два этапа:
  1. `api/dockerfile.base` формирует тяжёлый базовый слой на основе `python:3.11-slim` и устанавливает фреймворк, валидацию и вспомогательные утилиты.
  2. `api/dockerfile` добавляет лёгкие зависимости и исходный код приложения.

Такое разделение позволяет кэшировать тяжёлые зависимости и пересобирать только верхний слой при изменениях кода.

## Зависимости
- `api/requirements-base.txt` — базовые и относительно «тяжёлые» пакеты (FastAPI, Uvicorn, Pydantic, JSON Schema, поддержка multipart). Их стоит менять редко.
- `api/requirements.txt` — лёгкие или часто меняющиеся зависимости приложения (в данный момент — `httpx` для общения с Ollama).

Если библиотека не используется в проекте, добавлять её не нужно — лишние пакеты только увеличивают образ.

## Сборка и запуск
1. **(Опционально) Соберите базовый образ**. Делается редко — только при обновлении системных или тяжёлых Python-зависимостей.
   ```bash
   docker build -f api/dockerfile.base -t contract-extractor/api-base:cu130 ./api
   ```

2. **Запустите сервисы через Docker Compose**. Укажите уже собранный базовый образ через переменную `API_BASE_IMAGE`, чтобы переиспользовать кэш.
   ```bash
   API_BASE_IMAGE=contract-extractor/api-base:cu130 \
   MODEL=qwen2.5:7b-instruct \
   docker compose up --build
   ```
   После старта API будет доступно на `http://localhost:8080`, а Ollama — на `http://localhost:11434`.

3. **Изменение модели**. Передайте другое имя модели через `MODEL=...` (например, `MODEL=llama3.1`). Контейнер `ollama-pull` автоматически скачает её при запуске.

## Чистый старт Docker-среды
Если нужно пересобрать всё с нуля или избавиться от возможных конфликтов кэша/контейнеров:
```bash
# Остановить и удалить сервисы вместе с томами моделей
API_BASE_IMAGE=contract-extractor/api-base:cu130 docker compose down --volumes --remove-orphans

# Очистить кеш сборки Docker
docker builder prune --all --force

# Удалить собранные образы (если они есть)
docker image rm contract-extractor/api:dev contract-extractor/api-base:cu130 || true

# Удалить сохранённые модели Ollama
docker volume rm contract_extractor_ollama_models || true
```
После этого повторите шаги из раздела «Сборка и запуск».

## Добавление зависимостей
1. Определите слой:
   - Фреймворк и тяжёлые пакеты — в `api/requirements-base.txt` (потребуется пересборка базового образа).
   - Прикладные или часто меняющиеся утилиты — в `api/requirements.txt`.
2. Пересоберите нужный слой:
   - Только верхний: `API_BASE_IMAGE=contract-extractor/api-base:cu130 docker compose build api`
   - С обновлением базового слоя: `docker build -f api/dockerfile.base -t contract-extractor/api-base:cu130 ./api`
3. Перезапустите сервис: `docker compose up -d api`

## Как обновить Docker без полной пересборки
Часто достаточно обновить только прикладной слой, не трогая тяжёлый базовый образ:

1. Убедитесь, что локально собран и доступен базовый образ (см. переменную `API_BASE_IMAGE`).
2. Обновите исходники или зависимости в верхнем слое.
3. Пересоберите только сервис API, не трогая остальные контейнеры:
   ```bash
   API_BASE_IMAGE=contract-extractor/api-base:cu130 docker compose build api
   ```
   Команда переиспользует слои базового образа, поэтому пересобирается только лёгкая часть.
4. Примените обновление без перезапуска Ollama и других сервисов:
   ```bash
   docker compose up -d --no-deps api
   ```
   Флаг `--no-deps` пропускает зависимые контейнеры и ускоряет раскатку изменений.

Если нужно только обновить зависимости Python в верхнем слое, отредактируйте `api/requirements.txt`, запустите шаги 3–4 и убедитесь, что новое окружение собрано на основе кэша базового образа.

## Эндпоинты API
- `GET /healthz` — проверка живости.
- `GET /status` — информация о текущей модели и режиме работы.
- `GET /config` — активная конфигурация.
- `GET /schema` — JSON Schema результата.
- `GET /models` — список моделей Ollama.
- `GET /version` — версия приложения.
- `POST /check` — извлечение данных (принимает текст в `multipart/form-data` или JSON).
- `POST /test` — сравнение результата с эталоном.

## Структура проекта
```
api/
  app/
    assets/
      schema.json
    core/
      config.py
      logger.py
      schema.py
      validator.py
    prompts/
      system.txt
      user_template.txt
    services/
      normalize.py
      warnings.py
      utils.py
      compare.py
      ollama_client.py
      extractor/
        base.py
        rules.py
        llm.py
        pipeline.py
  requirements-base.txt
  requirements.txt
Dockerfile
docker-compose.yml
```

## План развития
- Расширить регексы и нормализацию по всем полям схемы.
- Добавить few-shot примеры из корпуса эталонов.
- Внедрить дополнительные проверки (даты, суммы, статусы).
- Подключить логи, метрики и трассировку.
