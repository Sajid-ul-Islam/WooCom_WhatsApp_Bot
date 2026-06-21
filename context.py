from dataclasses import dataclass
import logging

from db import DatabaseClient
from whatsapp_client import WhatsAppClient
from woocommerce_client import WooCommerceClient
from rag_agent import RAGAgent
from wit_client import WitClient

logger = logging.getLogger(__name__)


@dataclass
class BotContext:
    db: DatabaseClient
    wa: WhatsAppClient
    wc: WooCommerceClient
    agent: RAGAgent
    wit: WitClient | None = None

    def __post_init__(self):
        """Validate that all clients are properly initialized."""
        if not self.db.client:
            logger.warning("BotContext: DatabaseClient is not connected to Supabase. Cart, order, and user features will not work.")

        if not self.wa._client:
            logger.warning("BotContext: WhatsAppClient HTTP client is not initialized. Messages cannot be sent.")

        if not self.wc._client:
            logger.warning("BotContext: WooCommerceClient HTTP client is not initialized. Store features will not work.")

        if not self.agent.embedding_model:
            logger.warning("BotContext: RAGAgent embedding model failed to load. AI search quality may be degraded.")

        if self.wit is None or not self.wit.configured:
            logger.info("BotContext: Wit.ai client not configured — all queries will use LLM fallback.")
        else:
            logger.info("BotContext: Wit.ai client configured — known intents will skip LLM for faster responses.")
