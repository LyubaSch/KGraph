# Neo4j Runbook

This project keeps NLP/search, PDF parsing, and Neo4j import as separate steps.
The Knowledge Graph module expects already structured JSON and imports it into Neo4j.

## 1. Start Neo4j

Create `.env` if it does not exist:

```bash
cp .env.example .env
```

Start Neo4j with Docker:

```bash
docker compose -f docker-compose.neo4j.yml up -d
```

Neo4j Browser:

```text
http://localhost:7474
```

Use the credentials from `.env`.

If port `7474` or `7687` is already allocated, another Neo4j container is already running.
Use that container or stop it before starting this compose file.

## 2. Bootstrap and Verify the Graph

```bash
source .venv/bin/activate
python scripts/bootstrap_neo4j.py
```

The script runs:

- schema creation;
- demo JSON import;
- Entity field checks for `uid`, `name`, `canonical_name`, `type`;
- relationship checks;
- `get_subgraph("Ti-6Al-4V")` smoke test.

## 3. Verify Backend Uses Neo4j

Start backend:

```bash
cd backend
../.venv/bin/uvicorn app.main:app --reload --port 18080
```

Call `/graph`:

```bash
curl -X POST http://127.0.0.1:18080/graph \
  -H "Content-Type: application/json" \
  -d '{"query":"Ti-6Al-4V"}'
```

If Neo4j is available and the demo data is imported, the response contains nodes such as:

```json
{"id": "material:ti-6al-4v", "label": "Ti-6Al-4V", "type": "Material"}
```

If Neo4j is unavailable or the entity is missing, backend falls back to `data/graph.json`.

## 4. What Is Not Connected

`agent.py` and `prompts.py` are experimental extraction scaffolding. They are not connected to `/chat`,
do not write to Neo4j, and should not be used in the demo path without a separate integration pass.

