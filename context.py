from dataclasses import dataclass

from db import DatabaseClient
from whatsapp_client import WhatsAppClient
from woocommerce_client import WooCommerceClient
from rag_agent import RAGAgent


@dataclass
class BotContext:
    db: DatabaseClient
    wa: WhatsAppClient
    wc: WooCommerceClient
    agent: RAGAgent
