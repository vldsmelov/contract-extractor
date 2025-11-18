### Работа с assets

**GET `/assets/fields`**

- Параметр `q` обязателен: `get` читает базовые файлы, `check` — файлы пользователя.
- Параметр `f` выбирает нужный файл: `extractors`, `schema` или `contexts`. Пример: `/assets/fields?q=get&f=extractors` вернёт содержимое `api/app/assets/field_extractors.json`.
- При неверном `q` или `f` вернётся `400 Bad Request`.

**POST `/assets/change`**

- Обязательный параметр `f`: один из `extractors`, `schema` или `contexts`.
- Тело запроса — JSON, который будет сохранён в `api/app/assets/users_assets/<f>.json` (директория создаётся автоматически).
- В случае отсутствия `f` или несериализуемого JSON вернётся `400 Bad Request`.

### Работа с prompts

**GET `/prompts/system`**

- Параметр `q` обязателен: `get` читает дефолтные файлы (`api/app/prompts/...`), `check` — пользовательские (`api/app/prompts/user_prompts/...`).
- Параметр `f` можно передавать несколько раз для выборки конкретных файлов (`field_guidelines`, `summary_system`, `summary_user_template`, `system`, `user_template`). Без `f` вернутся все файлы.
- Неверные значения `q` или `f` приводят к `400 Bad Request`.

**POST `/prompts/system_change`**

- Тело запроса — JSON-объект, где ключи соответствуют названиям файлов (`field_guidelines`, `summary_system`, `summary_user_template`, `system`, `user_template`).
- Значения должны быть строками; для каждого переданного ключа создаётся или перезаписывается файл в `api/app/prompts/user_prompts/`.
- Пустой payload или неожиданные ключи вызывают `400 Bad Request`.