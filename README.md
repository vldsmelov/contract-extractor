# Contract Extractor API

Локальный сервис извлечения JSON из текста договора (без табличной части).
Спроектировано по принципам **OOP, DRY, KISS**. Настройки, промпты и схема — в отдельных файлах.

## Архитектура
- `ollama` — локальная LLM (по умолчанию `qwen2.5:7b-instruct`).
- `api` — FastAPI-сервис с эндпоинтами `/check`, `/test`, `/healthz`, `/status`, `/config`, `/schema`, `/models`, `/version`.

## Сборка и запуск

1. (Опционально, но ускоряет дальнейшую сборку) один раз создайте тяжёлый базовый образ, куда входят CUDA, PyTorch, Ollama и все «большие» зависимости API:
```bash
docker build \
  --target python-base \
  --build-arg CUDA_BASE_IMAGE=nvidia/cuda:13.0.0-cudnn-devel-ubuntu22.04 \
  --build-arg TORCH_INDEX_URL=https://download.pytorch.org/whl/nightly/cu130 \
  --build-arg TORCH_CUDA_ARCH=12.0 \
  -t contract-extractor-base:latest .
```

   После этого можно указать `RUNTIME_BASE_IMAGE=contract-extractor-base:latest`, чтобы итоговая сборка переиспользовала готовый слой и при изменениях `requirements.txt` пересобирала только лёгкие части.

2. Соберите и поднимите сервис (API + Ollama в одном контейнере с поддержкой GPU):
```bash
RUNTIME_BASE_IMAGE=contract-extractor-base:latest docker compose up --build
```

   *Если переменная `RUNTIME_BASE_IMAGE` не задана, Docker соберёт полноценный образ с нуля, опираясь на `nvidia/cuda:13.0.0-cudnn-devel-ubuntu22.04`. При необходимости можно переопределить базовый CUDA-образ, индекс колёс PyTorch и список поддерживаемых архитектур аргументами `CUDA_BASE_IMAGE`, `TORCH_INDEX_URL` и `TORCH_CUDA_ARCH` в `docker-compose.yml`.*

3. Загрузите модель в Ollama (если не загружена):
```bash
ollama pull qwen2.5:7b-instruct
```

API будет доступен на `http://localhost:8080`.

## Эндпоинты

- `GET /healthz` — проверка живости.
- `GET /status` — базовая информация (модель, хост).
- `GET /config` — активные настройки.
- `GET /schema` — JSON Schema целевого ответа.
- `GET /models` — список моделей в Ollama.
- `GET /version` — версия приложения.

- `POST /check` — извлечь JSON.
  - **multipart/form-data**: `file=<.txt>`
  - **application/json**: `{ "text": "..." }`

- `POST /test` — сравнить с эталоном.
  - **multipart/form-data**: `text_file=<.txt>, gold_json=<.json>`

## Примечания
- Строгая валидация по `assets/schema.json`. Схема сгенерирована из вашего эталонного JSON.
- Гибридный пайплайн: правила → (опционально) LLM → валидация → предупреждения.
- Числовая толерантность сравнения в `/test` — `NUMERIC_TOLERANCE` (env).
- Дополнительные лёгкие зависимости следует добавлять в `api/requirements.txt`. Благодаря разнесению слоёв, изменение этого файла приводит только к быстрому пересбору верхнего слоя.

## Добавление новых зависимостей

1. **Выберите слой:**
   - Лёгкие утилиты (pandas, rapidfuzz, httpx и т. п.) добавляйте в `api/requirements.txt`.
   - Тяжёлые GPU-библиотеки (CUDA, PyTorch, TensorRT и т. п.) добавляйте в `api/requirements-base.txt`, чтобы они попадали в базовый образ и переиспользовались между сборками.

2. **Обновите файлы зависимостей:**
   ```bash
   # пример добавления новой библиотеки в верхний слой
   echo "pydantic-settings==2.4.0" >> api/requirements.txt
   ```

3. **Пересоберите только лёгкий слой (быстро):**
   ```bash
   RUNTIME_BASE_IMAGE=contract-extractor-base:latest docker compose build contract-extractor
   ```
   Docker скачает только новые пакеты из `api/requirements.txt`, поскольку тяжёлый слой уже собран.

4. **Если меняли `requirements-base.txt`:**
   ```bash
   docker build \
     --target python-base \
     --build-arg CUDA_BASE_IMAGE=${CUDA_BASE_IMAGE:-nvidia/cuda:13.0.0-cudnn-devel-ubuntu22.04} \
     --build-arg TORCH_INDEX_URL=${TORCH_INDEX_URL:-https://download.pytorch.org/whl/nightly/cu130} \
     --build-arg TORCH_CUDA_ARCH=${TORCH_CUDA_ARCH:-12.0} \
     -t contract-extractor-base:latest .
   ```
   Затем повторно выполните шаг 3, чтобы обновить основной образ приложения.

5. **Запустите сервис после пересборки:**
   ```bash
   docker compose up -d contract-extractor
   ```
   Или `docker compose up --build`, если хотите собрать и запустить одной командой.

## Чистый старт Docker-среды
Чтобы пересобрать всё с нуля (например, при смене базового CUDA-образа), выполните:

```bash
# Остановить и удалить сервисы вместе с томами Ollama
docker compose down --volumes --remove-orphans

# Очистить кэш сборки и удалить связанные образы
docker builder prune --all --force
docker image rm contract-extractor:latest contract-extractor-base:latest || true

# Удалить сохранённые модели Ollama
docker volume rm contract-extractor_ollama_models || true
```

После очистки повторите сборку базового слоя (при необходимости) и основной службы по инструкциям выше.

## Конфигурация
См. переменные окружения в `docker-compose.yml` или используйте:
- `OLLAMA_HOST` — адрес Ollama, по умолчанию `http://127.0.0.1:11434` внутри контейнера.
- `MODEL` — имя модели Ollama (например, `qwen2.5:7b-instruct`).
- `TEMPERATURE`, `MAX_TOKENS`, `USE_LLM` — параметры генерации.

## Структура
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
docker/
  entrypoint.sh
docker-compose.yml
```

## Развитие
- Расширить регексы и нормализацию по всем полям схемы.
- Добавить подбор few-shot из ваших 32 примеров.
- Усилить кросс-проверки (даты, суммы, статусы).
- Логи/метрики/трассировка.
