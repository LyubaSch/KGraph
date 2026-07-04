# Научный клубок

MVP веб-приложения для анализа материаловедческих данных через поиск, NLP-заготовку и Neo4j knowledge graph.

Пользователь открывает сайт, вводит исследовательский вопрос или загружает источник. Backend ищет релевантные документы, получает связанный подграф из Neo4j и возвращает на frontend ответ, документы, гипотезы и граф связей.

## Что Уже Работает

- web-интерфейс без сборки в `frontend-web/`;
- FastAPI backend в `backend/`;
- загрузка файлов через `/upload`;
- поиск по demo-документам;
- Neo4j knowledge graph;
- импорт структурированного JSON в Neo4j;
- получение подграфа через `/graph`;
- единый endpoint `/chat` для frontend;
- fallback на mock graph, если Neo4j недоступен;
- NLP scaffold под YandexGPT в `nlp/`;
- rule-based NLP fallback без ключа YandexGPT.

Основной demo query:

```text
Что известно про Ti-6Al-4V после закалки?
```

## Архитектура

```text
frontend-web
  |
  | POST /chat
  v
backend FastAPI
  |
  +-- search_service  -> data/documents.json
  +-- graph_service   -> Neo4j через kg/queries.py
  +-- agent_service   -> собирает ответ для frontend
  +-- upload          -> data/uploads/
  |
  v
Neo4j
  ^
  |
kg/importer.py <- structured JSON <- nlp/extraction.py
```

Планируемый production flow:

```text
PDF/text -> chunks -> NLP extraction -> structured JSON -> Neo4j -> /chat -> web graph
```

В текущем MVP PDF-to-graph pipeline ещё не подключён полностью. Для демо используются подготовленные JSON-данные и NLP fallback.

## Структура Директорий

```text
backend/                 FastAPI backend и API endpoints
frontend-web/            основной web-интерфейс для демо
kg/                      Neo4j client, schema, importer, queries, YandexGPT client
nlp/                     извлечение сущностей/claims/relations из текста
scripts/                 команды импорта и проверки Neo4j
data/                    demo documents, graph, hypotheses, structured KG JSON
cypher/                  полезные Cypher-запросы для Neo4j Browser
docker-compose.neo4j.yml локальный Neo4j
README.md                единственная документация по запуску
```

## Быстрый Запуск

### 1. Подготовить Python

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -r backend/requirements.txt
```

### 2. Создать `.env`

```bash
cp .env.example .env
```

Минимально нужны настройки Neo4j:

```env
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your_password
```

Опционально для YandexGPT:

```env
YANDEXGPT_FOLDER_ID=your_folder_id
YANDEXGPT_API_KEY=your_api_key
YANDEXGPT_MODEL=yandexgpt-lite/latest
```

Без YandexGPT-ключа приложение продолжает работать через fallback.

### 3. Запустить Neo4j

```bash
docker compose -f docker-compose.neo4j.yml up -d
```

Neo4j Browser:

```text
http://localhost:7474
```

### 4. Импортировать Demo Graph

```bash
python scripts/bootstrap_neo4j.py
```

Скрипт создаёт constraints/indexes, импортирует `data/examples/example_materials.json` и проверяет:

- у Entity есть `uid`, `name`, `canonical_name`, `type`;
- relationships созданы;
- `get_subgraph("Ti-6Al-4V")` возвращает непустой граф.

### 5. Запустить Backend

```bash
cd backend
../.venv/bin/uvicorn app.main:app --reload --port 18080
```

Проверка:

```text
http://127.0.0.1:18080/health
```

### 6. Запустить Сайт

Из корня проекта во втором терминале:

```bash
python3 -m http.server 5501 -d frontend-web
```

Открыть:

```text
http://127.0.0.1:5501
```

## Проверка API

Проверить Neo4j-граф:

```bash
curl -X POST http://127.0.0.1:18080/graph \
  -H "Content-Type: application/json" \
  -d '{"query":"Ti-6Al-4V"}'
```

Ожидаемый формат:

```json
{
  "nodes": [
    {"id": "material:ti-6al-4v", "label": "Ti-6Al-4V", "type": "Material"}
  ],
  "edges": [
    {"source": "...", "target": "...", "label": "..."}
  ]
}
```

Проверить основной frontend endpoint:

```bash
curl -X POST http://127.0.0.1:18080/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"Что известно про Ti-6Al-4V после закалки?","session_id":"demo"}'
```

## NLP Scaffold

NLP-часть лежит в `nlp/`.

Пример локальной проверки без YandexGPT:

```bash
python -c "from nlp.extraction import extract_knowledge; import json; print(json.dumps(extract_knowledge('Сплав Ti-6Al-4V после закалки показал рост прочности.'), ensure_ascii=False, indent=2))"
```

Если YandexGPT настроен, extractor пробует LLM. Если ключа нет или API недоступен, используется rule-based fallback.

## Что Важно Для Demo

- Сайт открывается на `http://127.0.0.1:5501`.
- Backend должен быть запущен на `http://127.0.0.1:18080`.
- Neo4j должен слушать `bolt://localhost:7687`.
- Основной запрос для записи экрана: `Что известно про Ti-6Al-4V после закалки?`
- Если Neo4j выключен, backend вернёт mock graph, чтобы интерфейс не падал.
