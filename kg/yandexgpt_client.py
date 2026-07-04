import json
import os
import re
import urllib.error
import urllib.request
from typing import Any


DEFAULT_ENDPOINT = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"
DEFAULT_MODEL = "yandexgpt-lite/latest"


class YandexGPTConfigError(RuntimeError):
    pass


class YandexGPTClient:
    def __init__(
        self,
        *,
        endpoint: str | None = None,
        model_uri: str | None = None,
        folder_id: str | None = None,
        model: str | None = None,
        api_key: str | None = None,
        iam_token: str | None = None,
        timeout: int | None = None,
    ) -> None:
        self.endpoint = endpoint or os.getenv("YANDEXGPT_ENDPOINT", DEFAULT_ENDPOINT)
        self.folder_id = folder_id or os.getenv("YANDEXGPT_FOLDER_ID")
        self.api_key = api_key or os.getenv("YANDEXGPT_API_KEY")
        self.iam_token = iam_token or os.getenv("YANDEXGPT_IAM_TOKEN")
        self.timeout = timeout or int(os.getenv("YANDEXGPT_TIMEOUT", "60"))

        self.model_uri = model_uri or os.getenv("YANDEXGPT_MODEL_URI")
        if not self.model_uri:
            selected_model = model or os.getenv("YANDEXGPT_MODEL", DEFAULT_MODEL)
            if not self.folder_id:
                raise YandexGPTConfigError(
                    "YANDEXGPT_FOLDER_ID or YANDEXGPT_MODEL_URI is required."
                )
            self.model_uri = f"gpt://{self.folder_id}/{selected_model}"

        if not self.api_key and not self.iam_token:
            raise YandexGPTConfigError(
                "YANDEXGPT_API_KEY or YANDEXGPT_IAM_TOKEN is required."
            )

    def complete(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.0,
        max_tokens: int = 2000,
    ) -> str:
        payload = {
            "modelUri": self.model_uri,
            "completionOptions": {
                "stream": False,
                "temperature": temperature,
                "maxTokens": str(max_tokens),
            },
            "messages": [
                {"role": message["role"], "text": message["text"]}
                for message in messages
            ],
        }
        request = urllib.request.Request(
            self.endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers=self._headers(),
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw_body = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"YandexGPT request failed: HTTP {exc.code}: {body}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"YandexGPT request failed: {exc.reason}") from exc

        data = json.loads(raw_body)
        alternatives = data.get("result", {}).get("alternatives", [])
        if not alternatives:
            raise RuntimeError(f"YandexGPT response has no alternatives: {raw_body}")

        return str(alternatives[0].get("message", {}).get("text", "")).strip()

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Api-Key {self.api_key}"
        else:
            headers["Authorization"] = f"Bearer {self.iam_token}"

        if self.folder_id:
            headers["x-folder-id"] = self.folder_id
        return headers


def parse_json_response(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    fenced_match = re.search(r"```(?:json)?\s*(.*?)```", cleaned, re.DOTALL | re.IGNORECASE)
    if fenced_match:
        return json.loads(fenced_match.group(1).strip())

    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end != -1 and end > start:
        return json.loads(cleaned[start : end + 1])

    raise ValueError(f"YandexGPT response is not valid JSON: {text}")
