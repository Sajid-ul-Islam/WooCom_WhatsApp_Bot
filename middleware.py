import time
import logging
from collections import defaultdict
from typing import Optional, Set

logger = logging.getLogger(__name__)

RATE_LIMIT_WINDOW = 10  # seconds
RATE_LIMIT_MAX = 5      # max messages per window

# In-memory fast cache for rate limiting (reset on restart, Supabase is the source of truth)
_rate_buckets: dict[str, list[float]] = defaultdict(list)

# In-memory dedup set — preloaded from Supabase on startup
_processed_message_ids: Set[str] = set()
_dedup_lock = False  # simple flag to track if we've loaded from DB

DEDUPLICATION_WINDOW = 300  # 5 minutes in seconds

MAX_INCOMING_TEXT_LEN = 1000


def load_dedup_ids_from_db(ids: set):
    """Load known processed message IDs from Supabase into memory (called at startup)."""
    global _processed_message_ids, _dedup_lock  # noqa: PLW0603
    _processed_message_ids = ids
    _dedup_lock = True
    logger.info(f"Loaded {len(ids)} processed message IDs into dedup cache.")


def is_rate_limited(phone: str) -> bool:
    """Return True if the phone number has exceeded the rate limit (in-memory, fast path)."""
    now = time.monotonic()
    bucket = _rate_buckets[phone]
    # Prune old timestamps
    _rate_buckets[phone] = [t for t in bucket if now - t < RATE_LIMIT_WINDOW]
    bucket = _rate_buckets[phone]
    if len(bucket) >= RATE_LIMIT_MAX:
        return True
    bucket.append(now)
    return False


def is_duplicate_message(msg_id: str) -> bool:
    """Check if the message has already been processed (in-memory fast path)."""
    if not msg_id:
        return False
    if msg_id in _processed_message_ids:
        return True
    _processed_message_ids.add(msg_id)
    return False
