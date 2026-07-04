import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from neo4j.exceptions import AuthError, ServiceUnavailable

from kg.importer import import_json_file
from kg.neo4j_client import Neo4jClient
from kg.queries import get_subgraph
from kg.schema import build_graph


REQUIRED_ENTITY_FIELDS_QUERY = """
MATCH (e:Entity)
RETURN
  count(e) AS total,
  sum(
    CASE
      WHEN e.uid IS NOT NULL
       AND e.name IS NOT NULL
       AND e.canonical_name IS NOT NULL
       AND e.type IS NOT NULL
      THEN 1
      ELSE 0
    END
  ) AS valid
"""

RELATIONSHIPS_QUERY = """
MATCH (:Entity)-[r]->(:Entity)
RETURN count(r) AS total
"""


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Prepare local Neo4j for the Knowledge Graph demo and verify it works."
    )
    parser.add_argument(
        "--json-path",
        default="data/examples/example_materials.json",
        help="Structured KG JSON to import.",
    )
    parser.add_argument(
        "--demo-query",
        default="Ti-6Al-4V",
        help="Entity query that must return a non-empty subgraph.",
    )
    parser.add_argument(
        "--skip-import",
        action="store_true",
        help="Only run schema and checks without importing JSON.",
    )
    args = parser.parse_args()

    try:
        client = Neo4jClient()
        try:
            build_graph(client)
            print("OK: Neo4j schema is ready.")

            if not args.skip_import:
                stats = import_json_file(client, args.json_path)
                print(f"OK: imported {args.json_path}")
                for key, value in stats.items():
                    print(f"  {key}: {value}")

            rows = client.read(REQUIRED_ENTITY_FIELDS_QUERY)
            total_entities = rows[0]["total"] if rows else 0
            valid_entities = rows[0]["valid"] if rows else 0
            if total_entities == 0 or total_entities != valid_entities:
                raise RuntimeError(
                    f"Entity field check failed: total={total_entities}, valid={valid_entities}"
                )
            print(f"OK: Entity nodes have uid/name/canonical_name/type ({valid_entities}/{total_entities}).")

            rows = client.read(RELATIONSHIPS_QUERY)
            total_relationships = rows[0]["total"] if rows else 0
            if total_relationships == 0:
                raise RuntimeError("Relationship check failed: no Entity relationships found.")
            print(f"OK: Entity relationships found: {total_relationships}.")

            subgraph = get_subgraph(client, args.demo_query)
            if not subgraph["nodes"] or not subgraph["relationships"]:
                raise RuntimeError(f"Demo query returned an empty subgraph: {args.demo_query}")
            print(
                "OK: demo subgraph "
                f"'{args.demo_query}' -> {len(subgraph['nodes'])} nodes, "
                f"{len(subgraph['relationships'])} relationships."
            )
        finally:
            client.close()
    except AuthError as exc:
        raise SystemExit(
            "Neo4j authentication failed. Check NEO4J_USER/NEO4J_PASSWORD in .env "
            "and the password used by the Neo4j container."
        ) from exc
    except ServiceUnavailable as exc:
        raise SystemExit(
            "Cannot connect to Neo4j. Start it first, for example:\n"
            "  docker compose -f docker-compose.neo4j.yml up -d\n"
            "Then wait 20-40 seconds and rerun this script."
        ) from exc


if __name__ == "__main__":
    main()

