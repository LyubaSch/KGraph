# Хакатон НОРНИКЕЛЬ AI SCIENCE HACK

Состав команды: Лакпажап Дан-Хаяа, Щетинникова Любовь, Самохвалов Кирилл, Хадралинова Полина

*г.Иннополис*

*July 2026*

## Постановка задачи

Трек 02 "Научный клубок"

> Ваша задача: создать knowledge graph или поисково-аналитическую систему, которая связывает статьи, эксперименты, материалы, свойства, режимы, установки, исследовательские команды и выводы. Вам не нужно вписываться в жесткие рамки — вы сами решаете, какую архитектуру и интерфейс предложить: графовую БД, семантический поиск, гибридное решение. Главное — чтобы система отвечала на вопросы вида: «что уже делали по сплавам X при режиме Y и какой был эффект на свойство Z», показывала связанные сущности, историю решений и пробелы в данных. Для работы вы получите доступ к корпусу внутренних документов, каталогу экспериментов, справочникам материалов и оборудования, перечню сотрудников/лабораторий и тегам тематик.

## Knowledge Graph module

Зона ответственности участника 3 — Neo4j Knowledge Graph:

- импорт структурированного `JSON -> Neo4j`;
- graph schema, constraints и indexes;
- импорт сущностей и связей через `MERGE`;
- entity resolution и дедупликация;
- `get_subgraph()` для выдачи JSON-compatible подграфа;
- demo JSON и demo Cypher-запросы.

Модуль не делает semantic search, embeddings, frontend, chat, auth, upload UI, OpenAI agent или RAG.

### Запуск Knowledge Graph

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

В `.env` нужен доступ к Neo4j:

```env
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your_password
```

Локально Neo4j можно поднять через Docker:

```bash
docker compose -f docker-compose.neo4j.yml up -d
```

Создать schema и импортировать demo-граф:

```bash
python scripts/build_graph.py
python scripts/import_json.py data/examples/example_materials.json
python scripts/demo_get_subgraph.py "вещество Б"
python scripts/demo_get_subgraph.py "Б"
python scripts/demo_get_subgraph.py "вещество ББ"
python scripts/demo_get_subgraph.py "Ti-6Al-4V"
```

Или выполнить полный bootstrap + smoke-test одной командой:

```bash
python scripts/bootstrap_neo4j.py
```

Факты хранятся как обычные ребра с `evidence_type="fact"` и `visual_style="solid"`.

Гипотеза не является узлом. Она хранится как ребро:

```cypher
(Material)-[:HYPOTHESIZED_RELATED_TO {
  evidence_type: "hypothesis",
  visual_style: "dashed"
}]->(Material)
```

Готовые проверки для Neo4j Browser лежат в `cypher/demo_queries.cypher`.

Готовый query для backend/frontend demo:

```text
Ti-6Al-4V
```

Проверка backend endpoint:

```bash
curl -X POST http://127.0.0.1:18080/graph \
  -H "Content-Type: application/json" \
  -d '{"query":"Ti-6Al-4V"}'
```

Если Neo4j доступен и demo JSON импортирован, backend вернет `nodes` и `edges` из Neo4j. Если Neo4j недоступен или сущность не найдена, backend автоматически вернет mock graph из `data/graph.json`.

Подробный локальный runbook: `docs/neo4j_runbook.md`.
