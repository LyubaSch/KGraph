import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from kg.yandexgpt_client import YandexGPTClient, YandexGPTConfigError


def generate_llm_answer(query: str, context: dict[str, Any]) -> str | None:
    """Optional YandexGPT integration point.

    The product demo must keep working without YandexGPT credentials, so missing
    config returns None and lets callers use deterministic fallback text.
    """
    try:
        client = YandexGPTClient()
    except YandexGPTConfigError:
        return None

    prompt = (
        "Ответь кратко на русском языке по данным контекста. "
        "Не добавляй факты, которых нет в контексте.\n\n"
        f"Вопрос: {query}\n\n"
        f"Контекст JSON:\n{context}"
    )
    return client.complete(
        [
            {
                "role": "system",
                "text": "You are a scientific assistant for a materials knowledge graph.",
            },
            {"role": "user", "text": prompt},
        ],
        temperature=0.2,
        max_tokens=1200,
    )
