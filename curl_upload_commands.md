# Памятка по отправке файлов через `curl`

Ниже описаны примеры команд `curl` для локального запуска FastAPI-сервиса из этого репозитория. В примерах предполагается, что сервис поднят через `docker compose up --build` и доступен по адресу `http://localhost:8080`, а тестовые файлы находятся в каталоге проекта в папках `sample/` (документы) и `test/` (эталонные JSON).

## `POST /check`

Эндпоинт принимает либо текстовый файл, либо JSON с полем `text`. Для передачи файла:

```bash
curl -fS -X POST \
  "http://localhost:8080/check" \
  -H "Accept: application/json" \
  -F "file=@sample/sample_document.txt" \
  | jq
```

Замените `sample/sample_document.txt` на нужный файл. Параметр `-fS` заставит `curl` завершиться с ошибкой при статусе HTTP ≥ 400 (и не передавать в `jq` текст ошибки вроде `Internal Server Error`). Если необходимо отправить текст прямо в теле запроса, можно использовать JSON:

```bash
curl -fS -X POST \
  "http://localhost:8080/check" \
  -H "Content-Type: application/json" \
  -d '{"text": "Произвольный текст"}' \
  | jq
```

## `POST /test`

Эндпоинт сравнивает результат работы пайплайна с эталонными данными. Он ожидает два файла в одном multipart-запросе: документ и JSON с ответом.

```bash
curl -fS -X POST \
  "http://localhost:8080/test" \
  -H "Accept: application/json" \
  -F "text_file=@sample/sample_document.txt" \
  -F "gold_json=@test/sample_gold.json" \
  | jq
```

При необходимости замените пути на актуальные файлы в каталогах `sample/` и `test/`. Если необходимо посмотреть текст ошибки сервиса, временно уберите конвейер `| jq` или флаг `-fS`.
