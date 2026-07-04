import re
import sys
from pathlib import Path
from typing import Any

from app.services.data_service import load_graph


REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _matches_query(node: dict[str, Any], query: str) -> bool:
    searchable = f"{node.get('id', '')} {node.get('label', '')}".casefold()
    normalized_query = query.casefold().strip()
    terms = [term for term in re.findall(r"[\w-]+", normalized_query) if len(term) > 2]
    return normalized_query in searchable or any(
        term in searchable or str(node.get("label", "")).casefold() in normalized_query
        for term in terms
    )


def _get_mock_subgraph(query: str) -> dict[str, list[dict[str, Any]]]:
    graph = load_graph()
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])
    matched_ids = {node.get("id") for node in nodes if _matches_query(node, query)}

    if not matched_ids:
        return {"nodes": nodes[:8], "edges": edges[:10]}

    related_edges = [
        edge
        for edge in edges
        if edge.get("source") in matched_ids or edge.get("target") in matched_ids
    ]
    related_ids = matched_ids | {
        endpoint
        for edge in related_edges
        for endpoint in (edge.get("source"), edge.get("target"))
    }
    related_nodes = [node for node in nodes if node.get("id") in related_ids]
    return {"nodes": related_nodes, "edges": related_edges}


def _node_type(labels: list[str], properties: dict[str, Any]) -> str:
    if properties.get("type"):
        return str(properties["type"])
    for label in labels:
        if label != "Entity":
            return label
    return "Entity"


def _adapt_neo4j_subgraph(subgraph: dict[str, list[dict[str, Any]]]) -> dict[str, list[dict[str, Any]]]:
    nodes = []
    element_to_uid = {}

    for node in subgraph.get("nodes", []):
        properties = node.get("properties", {})
        uid = node.get("uid") or properties.get("uid") or node.get("id") or properties.get("id")
        if not uid:
            continue

        element_id = node.get("element_id")
        if element_id:
            element_to_uid[element_id] = uid

        nodes.append(
            {
                "id": str(uid),
                "label": str(properties.get("name") or properties.get("canonical_name") or uid),
                "type": _node_type(node.get("labels", []), properties),
            }
        )

    edges = []
    known_node_ids = {node["id"] for node in nodes}
    for relationship in subgraph.get("relationships", []):
        source = relationship.get("start_node_uid") or element_to_uid.get(relationship.get("start_node"))
        target = relationship.get("end_node_uid") or element_to_uid.get(relationship.get("end_node"))
        if not source or not target:
            continue

        source = str(source)
        target = str(target)
        if source not in known_node_ids or target not in known_node_ids:
            continue

        properties = relationship.get("properties", {})
        edges.append(
            {
                "source": source,
                "target": target,
                "label": str(properties.get("effect") or relationship.get("type") or "RELATED_TO"),
            }
        )

    return {"nodes": nodes, "edges": edges}


def _candidate_entity_queries(query: str) -> list[str]:
    candidates = [query]

    try:
        from kg.resolver import SYNONYMS, normalize_text
    except Exception:
        return candidates

    normalized_query = normalize_text(query)
    for alias, canonical in SYNONYMS.items():
        normalized_alias = normalize_text(alias)
        if not normalized_alias:
            continue

        if normalized_query == normalized_alias or (
            len(normalized_alias) > 2 and normalized_alias in normalized_query
        ):
            candidates.extend([alias, canonical])

    unique_candidates = []
    seen = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        unique_candidates.append(candidate)
    return unique_candidates


def _get_neo4j_subgraph(query: str) -> dict[str, list[dict[str, Any]]]:
    from kg.neo4j_client import Neo4jClient
    from kg.queries import get_subgraph as get_kg_subgraph

    client = Neo4jClient()
    try:
        for candidate in _candidate_entity_queries(query):
            subgraph = get_kg_subgraph(client, candidate)
            adapted = _adapt_neo4j_subgraph(subgraph)
            if adapted["nodes"]:
                return adapted
    finally:
        client.close()

    raise ValueError(f"Neo4j has no entity for query: {query}")


def get_subgraph(query: str) -> dict[str, list[dict[str, Any]]]:
    """Read from Neo4j first and fall back to local mock graph data."""
    try:
        return _get_neo4j_subgraph(query)
    except Exception:
        return _get_mock_subgraph(query)
