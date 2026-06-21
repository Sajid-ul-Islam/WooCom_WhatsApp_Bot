import os
import time
import logging
from dataclasses import dataclass, field
from typing import Any

import httpx

logger = logging.getLogger(__name__)


@dataclass
class WitStats:
    """In-memory statistics tracker for Wit.ai classification calls."""
    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    # Per-intent tracking: intent_name -> {count, confidence_sum, min_confidence, max_confidence}
    intents: dict[str, dict[str, float]] = field(default_factory=dict)
    # Recent call timestamps for throughput calculation (last 100)
    recent_timestamps: list[float] = field(default_factory=list)
    max_recent: int = 100
    last_classification: dict[str, Any] | None = None

    def record(self, text: str, result: dict | None, success: bool):
        """Record a Wit.ai classification result."""
        self.total_calls += 1
        now = time.time()
        self.recent_timestamps.append(now)
        if len(self.recent_timestamps) > self.max_recent:
            self.recent_timestamps = self.recent_timestamps[-self.max_recent:]

        if not success or result is None:
            self.failed_calls += 1
            return

        self.successful_calls += 1
        self.last_classification = {
            "text": text[:100],
            "intents": result.get("intents", []),
            "timestamp": now,
        }

        for intent in result.get("intents", []):
            name = intent.get("name", "unknown")
            confidence = intent.get("confidence", 0.0)
            if name not in self.intents:
                self.intents[name] = {
                    "count": 0.0,
                    "confidence_sum": 0.0,
                    "min_confidence": confidence,
                    "max_confidence": confidence,
                }
            entry = self.intents[name]
            entry["count"] += 1.0
            entry["confidence_sum"] += confidence
            entry["min_confidence"] = min(entry["min_confidence"], confidence)
            entry["max_confidence"] = max(entry["max_confidence"], confidence)

    def snapshot(self) -> dict[str, Any]:
        """Return a JSON-serialisable snapshot of current stats."""
        now = time.time()
        # Calculate throughput (calls per minute over the recent window)
        window = 60.0
        recent_cutoff = now - window
        rpm = sum(1 for t in self.recent_timestamps if t >= recent_cutoff)

        intent_breakdown = {}
        for name, entry in sorted(self.intents.items(), key=lambda x: -x[1]["count"]):
            count = int(entry["count"])
            avg_confidence = round(entry["confidence_sum"] / entry["count"], 3) if entry["count"] > 0 else 0.0
            intent_breakdown[name] = {
                "count": count,
                "avg_confidence": avg_confidence,
                "min_confidence": round(entry["min_confidence"], 3),
                "max_confidence": round(entry["max_confidence"], 3),
            }

        return {
            "total_calls": self.total_calls,
            "successful_calls": self.successful_calls,
            "failed_calls": self.failed_calls,
            "success_rate": round(self.successful_calls / max(self.total_calls, 1), 3),
            "calls_per_minute": rpm,
            "intents": intent_breakdown,
            "last_classification": self.last_classification,
        }


class WitClient:
    """Lightweight client for Wit.ai message understanding (intent + entity extraction).

    Uses the HTTP GET /message endpoint. Returns structured results so the
    caller can route requests without an expensive LLM call.
    """

    def __init__(self, server_token: str | None = None):
        self._token = server_token or os.getenv("WIT_AI_SERVER_TOKEN", "")
        self._http_client: httpx.AsyncClient | None = None
        self.stats = WitStats()

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
            self.stats.record(text, None, success=False)
            return None
        except httpx.HTTPStatusError as e:
            logger.warning(f"Wit.ai returned HTTP {e.response.status_code}: {e.response.text[:200]}")
            self.stats.record(text, None, success=False)
            return None
        except Exception as e:
            logger.warning(f"Wit.ai request failed: {e}")
            self.stats.record(text, None, success=False)
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

        result = {
            "intents": intents,
            "entities": entities,
            "text": data.get("text", text),
        }
        self.stats.record(text, result, success=True)
        return result

    async def close(self):
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None
