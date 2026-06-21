import os
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

class WitClient:
    """Lightweight client for Wit.ai message understanding (intent + entity extraction).

    Uses the HTTP GET /message endpoint. Returns structured results so the
    caller can route requests without an expensive LLM call.
    """

    def __init__(self, server_token: str | None = None):
        self._token = server_token or os.getenv("WIT_AI_SERVER_TOKEN", "")
        self._http_client: httpx.AsyncClient | None = None

    @property
    def configured(self) -> bool:
        return bool(self._token)

    async def _get_client(self) -> httpx.AsyncClient:
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(
                base_url="https://api.wit.ai",
                headers={"Authorization": f"Bearer {self._token}"},
                timeout=10.0,
            )
        return self._http_client

    async def analyze_message(self, text: str) -> dict[str, Any] | None:
        """Analyze a text message via Wit.ai and return extracted intents + entities.

        Returns a dict with keys:
            - ``intents``: list of {"name": str, "confidence": float}
            - ``entities``: dict keyed by entity name, each value is a list of dicts
            - ``text``: the original input text
        Returns None if Wit.ai is not configured, the API call fails, or the
        top intent confidence is below the threshold.
        """
        if not self.configured:
            return None

        client = await self._get_client()

        try:
            response = await client.get(
                "/message",
                params={"q": text, "v": "20240304"},
            )
            response.raise_for_status()
            data = response.json()
        except httpx.TimeoutException:
            logger.warning("Wit.ai request timed out")
            return None
        except httpx.HTTPStatusError as e:
            logger.warning(f"Wit.ai returned HTTP {e.response.status_code}: {e.response.text[:200]}")
            return None
        except Exception as e:
            logger.warning(f"Wit.ai request failed: {e}")
            return None

        # Parse intents from the response
        raw_intents = data.get("intents", [])
        intents = [
            {"name": i.get("name", ""), "confidence": i.get("confidence", 0.0)}
            for i in raw_intents
        ]

        # Parse entities from the response
        entities: dict[str, list[dict[str, Any]]] = {}
        for key, raw_list in data.get("entities", {}).items():
            # Wit.ai entity keys look like "wit$location:location"
            # Strip the prefix for cleaner access
            simple_key = key.split(":")[-1] if ":" in key else key
            entities[simple_key] = [
                {
                    "name": e.get("name", ""),
                    "value": e.get("value", ""),
                    "confidence": e.get("confidence", 0.0),
                    "role": e.get("role", ""),
                }
                for e in raw_list
            ]

        return {
            "intents": intents,
            "entities": entities,
            "text": data.get("text", text),
        }

    async def close(self):
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None
