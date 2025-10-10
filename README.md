# Contract Extractor API

Локальный сервис извлечения JSON из текста договора (без табличной части).
Спроектировано по принципам **OOP, DRY, KISS**. Настройки, промпты и схема — в отдельных файлах.

## Архитектура
- `ollama` — локальная LLM (по умолчанию `qwen2.5:7b-instruct`).
- `api` — FastAPI-сервис с эндпоинтами `/check`, `/test`, `/healthz`, `/status`, `/config`, `/schema`, `/models`, `/version`.

## Сборка и запуск

1. Соберите базовый образ (тяжёлый слой):
```bash
 docker build -f api/dockerfile.base -t contract-extractor-api-base ./api
```

   *По умолчанию образ собирается на основе `nvidia/cuda:13.0.0-cudnn-devel-ubuntu22.04`,
   оптимизированного под архитектуру `sm_120` и нацелен на nightly-сборки PyTorch для CUDA 13.
   При необходимости можно переопределить базовый образ, индекс колёс PyTorch и список
   поддерживаемых архитектур аргументами сборки `--build-arg CUDA_BASE_IMAGE=...`,
   `--build-arg TORCH_INDEX_URL=...` и `--build-arg TORCH_CUDA_ARCH=...`.*

2. Соберите и поднимите сервисы:
```bash
docker compose up --build
```

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

## Конфигурация
См. переменные окружения в `docker-compose.yml` или используйте:
- `OLLAMA_HOST` — адрес Ollama, по умолчанию `http://ollama:11434`.
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
  dockerfile.base      # тяжёлый слой
  dockerfile           # лёгкий слой (код)
  requirements-base.txt
  requirements.txt
docker-compose.yml
```

## Развитие
- Расширить регексы и нормализацию по всем полям схемы.
- Добавить подбор few-shot из ваших 32 примеров.
- Усилить кросс-проверки (даты, суммы, статусы).
- Логи/метрики/трассировка.
