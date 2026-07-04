import json

from kg.yandexgpt_client import YandexGPTClient, parse_json_response
from prompts import (
    SYSTEM_PROMPT,
    EXTRACTION_AGENT,
    HYPOTHESIS_AGENT,
    DISCOVERY_AGENT,
    EXPLAIN_EDGE_PROMPT,
)


_client = None


def get_yandexgpt_client():
    global _client

    if _client is not None:
        return _client

    _client = YandexGPTClient()
    return _client


# ─────────────────────────────
# LLM WRAPPER
# ─────────────────────────────

def ask_llm(prompt, temperature=0.0):
    client = get_yandexgpt_client()
    response_text = client.complete(
        [
            {"role": "system", "text": SYSTEM_PROMPT},
            {"role": "user", "text": prompt},
        ],
        temperature=temperature,
        max_tokens=3000,
    )
    return parse_json_response(response_text)


# ─────────────────────────────
# MATERIAL NAME EXTRACTION (NON-CRITICAL LLM)
# ─────────────────────────────

def extract_material_name(query):
    client = get_yandexgpt_client()
    response_text = client.complete(
        [
            {
                "role": "user",
                "text": (
                    "Extract material name from query. If none, return null. "
                    "Return only the material name or null.\n\n"
                    f"{query}"
                ),
            }
        ],
        temperature=0.0,
        max_tokens=64,
    )
    out = response_text.strip().strip('"')
    return None if out.lower() == "null" else out


# ─────────────────────────────
# CYpher generator (NO LLM)
# ─────────────────────────────

def json_to_cypher(entities, relations):
    cypher = []

    for e in entities:
        label = e["type"].replace(" ", "_")
        props = json.dumps(e)

        cypher.append(
            f"MERGE (n:{label} {{id: '{e['id']}'}}) "
            f"SET n += {props}"
        )

    for r in relations:
        cypher.append(
            f"MATCH (a {{id: '{r['source']}'}}), (b {{id: '{r['target']}'}}) "
            f"MERGE (a)-[x:{r['relation'].upper().replace(' ', '_')}]->(b) "
            f"SET x.confidence = {r['confidence']}"
        )

    return cypher


# ─────────────────────────────
# SUBGRAPH FILTER
# ─────────────────────────────

def filter_subgraph(subgraph, max_nodes=20):
    nodes = subgraph.get("nodes", [])[:max_nodes]
    node_ids = {n["id"] for n in nodes}

    edges = [
        e for e in subgraph.get("edges", [])
        if e.get("source") in node_ids and e.get("target") in node_ids
    ]

    return {
        "nodes": nodes,
        "edges": edges,
        "claims": subgraph.get("claims", [])[:10]
    }


# ─────────────────────────────
# PROCESS DOCUMENT PIPELINE
# ─────────────────────────────

def process_document(pdf_path, chunker, graph, retriever):
    result = {
        "chunks": 0,
        "entities": 0,
        "claims": 0,
        "relations": 0,
        "discoveries": 0
    }

    for chunk in chunker.parse(pdf_path):

        extracted = ask_llm(
            EXTRACTION_AGENT.format(text=chunk)
        )

        # entity resolution (simple deterministic)
        for e in extracted.get("entities", []):
            known = graph.resolve_entity(e["name"], e["type"])
            if known:
                e["id"] = known["id"]

        graph.execute_many(
            json_to_cypher(
                extracted.get("entities", []),
                extracted.get("relations", [])
            )
        )

        retriever.index(chunk, extracted)

        result["chunks"] += 1
        result["entities"] += len(extracted.get("entities", []))
        result["claims"] += len(extracted.get("claims", []))
        result["relations"] += len(extracted.get("relations", []))

    # ─── DISCOVERY ONCE ───
    for material in graph.get_all_materials():

        subgraph = graph.get_subgraph(material)
        if not subgraph.get("nodes"):
            continue

        subgraph = filter_subgraph(subgraph)

        discovery = ask_llm(
            DISCOVERY_AGENT.format(
                subgraph=json.dumps(subgraph, ensure_ascii=False)
            )
        )

        graph.set_discoveries(material, discovery)
        result["discoveries"] += 1

    return result


# ─────────────────────────────
# CHAT (GRAPH-CENTRIC OUTPUT)
# ─────────────────────────────

def chat(user_query, retriever, graph):

    docs = retriever.search(user_query)
    material = extract_material_name(user_query)

    subgraph = graph.get_subgraph(material) if material else {
        "nodes": [], "edges": [], "claims": []
    }

    subgraph = filter_subgraph(subgraph)

    # ─── HYPOTHESES ───
    doc_claims = []
    for d in docs:
        doc_claims.extend(d.get("claims", []))

    graph_claims = subgraph.get("claims", [])

    hypotheses = []

    for dc in doc_claims[:5]:
        for gc in graph_claims[:5]:

            common = set(dc.get("entities", [])) & set(gc.get("entities", []))

            if common:
                h = ask_llm(
                    HYPOTHESIS_AGENT.format(
                        claim_a=json.dumps(dc),
                        claim_b=json.dumps(gc),
                        graph_nodes=json.dumps(subgraph.get("nodes", [])),
                        common_entities=list(common),
                        similarity_score=0.85
                    )
                )

                if h.get("status") != "no_relation":
                    hypotheses.append(h)

    # ─── DISCOVERY (precomputed) ───
    discovery = graph.get_discoveries(material) if material else {}

    # ─── FINAL GRAPH OUTPUT ───
    return {
        "graph": {
            "nodes": subgraph["nodes"],
            "edges": subgraph["edges"],
        },
        "hypotheses": hypotheses,
        "discoveries": discovery,
        "highlighted_nodes": list({n["id"] for n in subgraph["nodes"]})
    }
