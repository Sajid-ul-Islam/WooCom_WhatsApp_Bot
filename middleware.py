import time
import logging
from collections import defaultdict
from typing import Optional, Set

logger = logging.getLogger(__name__)



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




def is_duplicate_message(msg_id: str) -> bool:
    """Check if the message has already been processed (in-memory fast path)."""
    if not msg_id:
        return False
    if msg_id in _processed_message_ids:
        return True
    _processed_message_ids.add(msg_id)
    return False
