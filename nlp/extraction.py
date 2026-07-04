"""
NLP extraction for entities, claims, and relations.

Flow:
1. Try YandexGPT if credentials are configured.
2. Fall back to deterministic rule-based extraction for the demo.
"""

from __future__ import annotations

import re
from typing import Any

from kg.resolver import normalize_name
from kg.yandexgpt_client import YandexGPTClient, YandexGPTConfigError, parse_json_response
from nlp.prompts import EXTRACTION_PROMPT


MATERIAL_TERMS = [
    ("ВТ47", ["ВТ47"]),
    ("ВТ16", ["ВТ16"]),
    ("Ti-6Al-4V", ["Ti-6Al-4V", "Ti64"]),
    ("ВТ5", ["ВТ5"]),
    ("ВТ20", ["ВТ20"]),
    ("ВТ22", ["ВТ22"]),
    ("Timetal 21S", ["Timetal 21S"]),
]
PROCESS_TERMS = [
    ("закалка", ["закалка", "закалки", "закалке", "закалкой"]),
    ("отжиг", ["отжиг", "отжига", "отжиге", "отжигом"]),
    ("старение", ["старение", "старения", "старением"]),
    ("деформация", ["деформация", "деформации", "деформацией"]),
    ("прокатка", ["прокатка", "прокатки", "прокатке", "прокаткой"]),
    ("высадка", ["высадка", "высадки", "высадке", "высадкой"]),
]
PROPERTY_TERMS = [
    ("предел прочности", ["предел прочности", "предела прочности"]),
    ("прочность", ["прочность", "прочности", "рост прочности"]),
    ("твердость", ["твердость", "твёрдость", "твердости", "твёрдости"]),
    ("сопротивление срезу", ["сопротивление срезу", "сопротивления срезу"]),
    ("пластичность", ["пластичность", "пластичности"]),
]
EQUIPMENT_TERMS = [
    ("Вега-2М", ["Вега-2М"]),
    ("Nabertherm", ["Nabertherm"]),
    ("Olympus", ["Olympus"]),
    ("Bruker", ["Bruker"]),
    ("MTS-5т", ["MTS-5т"]),
    ("Zwick", ["Zwick"]),
]

MATERIALS = [name for name, _ in MATERIAL_TERMS]

ALLOWED_ENTITY_TYPES = {
    "Material",
    "Process",
    "Property",
    "Equipment",
    "Parameter",
    "Experiment",
    "Publication",
    "Expert",
}


def extract_knowledge(text: str) -> dict[str, list[dict[str, Any]]]:
    """Extract KG-ready entities, claims, and relations from text."""
    ai_result = _extract_with_yandexgpt(text)
    if ai_result:
        entities = _dedupe_entities(
            _normalize_entity(entity) for entity in ai_result.get("entities", [])
        )
        claims = [
            claim
            for claim in (_normalize_claim(claim, index) for index, claim in enumerate(ai_result.get("claims", []), 1))
            if claim
        ]
        relations = extract_relations(text, entities)
        return {"entities": entities, "claims": claims, "relations": relations}

    entities = extract_entities(text)
    return {
        "entities": entities,
        "claims": extract_claims(text, entities),
        "relations": extract_relations(text, entities),
    }


def extract_entities(text: str) -> list[dict[str, Any]]:
    """Extract Material, Process, Property, and Equipment entities."""
    ai_result = _extract_with_yandexgpt(text)
    if ai_result:
        entities = _dedupe_entities(
            _normalize_entity(entity) for entity in ai_result.get("entities", [])
        )
        if entities:
            return entities

    entities: list[dict[str, Any]] = []
    for name, aliases in MATERIAL_TERMS:
        if _contains_any(text, aliases):
            entities.append(_make_entity(name, "Material", confidence=0.9))

    for name, aliases in PROCESS_TERMS:
        if _contains_any(text, aliases):
            entities.append(_make_entity(name, "Process", confidence=0.9))

    for name, aliases in PROPERTY_TERMS:
        if _contains_any(text, aliases):
            entities.append(_make_entity(name, "Property", confidence=0.9))

    for name, aliases in EQUIPMENT_TERMS:
        if _contains_any(text, aliases):
            entities.append(_make_entity(name, "Equipment", confidence=0.9))

    return _dedupe_entities(entities)


def extract_relations(text: str, entities: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """Build simple explicit co-mention relations for the demo pipeline."""
    entities = entities or extract_entities(text)
    relations = []
    materials = [entity for entity in entities if entity["type"] == "Material"]
    processes = [entity for entity in entities if entity["type"] == "Process"]
    properties = [entity for entity in entities if entity["type"] == "Property"]

    for process in processes:
        for material in materials:
            relations.append(
                {
                    "source": process["id"],
                    "target": material["id"],
                    "type": "USES_MATERIAL",
                    "evidence": f"Совместное упоминание: {process['name']} и {material['name']}",
                    "confidence": 0.8,
                }
            )

    for process in processes:
        for prop in properties:
            relations.append(
                {
                    "source": process["id"],
                    "target": prop["id"],
                    "type": "PRODUCES_OUTPUT",
                    "evidence": f"Совместное упоминание процесса {process['name']} и свойства {prop['name']}",
                    "confidence": 0.75,
                }
            )

    return relations


def extract_claims(text: str, entities: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """Extract short claims from sentences mentioning known materials."""
    entities = entities or extract_entities(text)
    material_names = {entity["name"] for entity in entities if entity["type"] == "Material"}
    claims = []

    for index, sentence in enumerate(_sentences(text), 1):
        matched_materials = [name for name in material_names if _contains(sentence, name)]
        if not matched_materials:
            continue

        claim_entities = [
            entity["id"]
            for entity in entities
            if _contains(sentence, entity["name"])
        ]
        claims.append(
            {
                "id": f"claim:{index:03d}",
                "name": sentence[:80],
                "text": sentence,
                "quote": sentence,
                "entities": claim_entities,
                "confidence": 0.8,
            }
        )

    return claims[:5]


def _extract_with_yandexgpt(text: str) -> dict[str, Any] | None:
    try:
        client = YandexGPTClient()
    except YandexGPTConfigError:
        return None

    response_text = client.complete(
        [
            {"role": "system", "text": EXTRACTION_PROMPT},
            {"role": "user", "text": text},
        ],
        temperature=0.1,
        max_tokens=3000,
    )
    try:
        parsed = parse_json_response(response_text)
    except (ValueError, TypeError):
        return None

    if isinstance(parsed, dict):
        return parsed
    if isinstance(parsed, list):
        return {"entities": parsed, "claims": []}
    return None


def _normalize_entity(entity: dict[str, Any]) -> dict[str, Any] | None:
    entity_type = str(entity.get("type", "")).strip()
    name = str(entity.get("name", "")).strip()
    if entity_type not in ALLOWED_ENTITY_TYPES or not name:
        return None

    normalized = _make_entity(
        name,
        entity_type,
        entity_id=entity.get("id"),
        confidence=float(entity.get("confidence", 0.7) or 0.7),
    )
    attributes = entity.get("attributes") or entity.get("properties") or {}
    if isinstance(attributes, dict):
        for key, value in attributes.items():
            if isinstance(value, str | int | float | bool) or value is None:
                normalized[str(key)] = value
    return normalized


def _normalize_claim(claim: dict[str, Any], index: int) -> dict[str, Any] | None:
    text = str(claim.get("text") or claim.get("quote") or "").strip()
    if not text:
        return None
    return {
        "id": str(claim.get("id") or f"claim:{index:03d}"),
        "name": text[:80],
        "text": text,
        "quote": str(claim.get("quote") or text),
        "entities": claim.get("entities") or [],
        "confidence": float(claim.get("confidence", 0.7) or 0.7),
    }


def _make_entity(
    name: str,
    entity_type: str,
    *,
    entity_id: Any | None = None,
    confidence: float = 0.8,
) -> dict[str, Any]:
    entity_id = str(entity_id or f"{entity_type.lower()}:{normalize_name(name)}")
    return {
        "id": entity_id,
        "name": name,
        "type": entity_type,
        "confidence": confidence,
    }


def _dedupe_entities(entities: Any) -> list[dict[str, Any]]:
    unique = {}
    for entity in entities:
        if not entity:
            continue
        key = (entity["type"], normalize_name(entity["name"]))
        unique[key] = entity
    return list(unique.values())


def _contains(text: str, value: str) -> bool:
    return re.search(re.escape(value), text, re.IGNORECASE) is not None


def _contains_any(text: str, values: list[str]) -> bool:
    return any(_contains(text, value) for value in values)


def _sentences(text: str) -> list[str]:
    return [sentence.strip() for sentence in re.split(r"[.!?]\s+", text) if sentence.strip()]
