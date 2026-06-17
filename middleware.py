import time
from collections import defaultdict

RATE_LIMIT_WINDOW = 10  # seconds
RATE_LIMIT_MAX = 5      # max messages per window

_rate_buckets: dict[str, list[float]] = defaultdict(list)

DEDUPLICATION_WINDOW = 300  # 5 minutes in seconds
_processed_message_ids: dict[str, float] = {}

MAX_INCOMING_TEXT_LEN = 1000


def is_rate_limited(phone: str) -> bool:
    """Return True if the phone number has exceeded the rate limit."""
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
    """Check if the message has already been processed or is currently processing."""
    if not msg_id:
        return False
    now = time.monotonic()

    # Prune old message IDs to prevent memory growth
    expired_ids = [k for k, t in _processed_message_ids.items() if now - t > DEDUPLICATION_WINDOW]
    for k in expired_ids:
        _processed_message_ids.pop(k, None)

    if msg_id in _processed_message_ids:
        return True

    _processed_message_ids[msg_id] = now
    return False
