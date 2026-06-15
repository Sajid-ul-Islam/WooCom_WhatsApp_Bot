"""
Standalone script to sync WooCommerce products to Supabase with vector embeddings.
Processes products in small batches to avoid memory issues on low-RAM machines.
"""
import os
import re
import gc
import asyncio
import logging
from dotenv import load_dotenv
from typing import List, Dict, Any
from fastembed import TextEmbedding

from woocommerce_client import WooCommerceClient
from db import DatabaseClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("product_embeddings")

# Load environment variables in case this is run as a standalone script
load_dotenv()

def clean_html(raw_html: str) -> str:
    """Strip HTML tags from WooCommerce descriptions."""
    if not raw_html:
        return ""
    clean_r = re.compile('<[^<]+?>')
    return re.sub(clean_r, '', raw_html).strip()

def prepare_product_search_text(product: Dict[str, Any]) -> str:
    """Create a descriptive text representation of a product for semantic search."""
    name = product.get("name", "")
    price = product.get("price", "0.0")
    description = clean_html(product.get("description", "")) or clean_html(product.get("short_description", ""))
    
    categories = [cat.get("name", "") for cat in product.get("categories", [])]
    categories_str = ", ".join(categories)
    
    tags = [tag.get("name", "") for tag in product.get("tags", [])]
    tags_str = ", ".join(tags)

    return f"Product Name: {name}. Price: ${price}. Categories: {categories_str}. Tags: {tags_str}. Description: {description}"

def prepare_product_doc(p: Dict[str, Any]) -> Dict[str, Any]:
    """Map a WooCommerce product to a Supabase row (without embedding)."""
    images = [{"src": img.get("src")} for img in p.get("images", [])]
    categories = [{"id": cat.get("id"), "name": cat.get("name")} for cat in p.get("categories", [])]
    return {
        "id": p.get("id"),
        "name": p.get("name"),
        "description": clean_html(p.get("description", "")),
        "price": float(p.get("price")) if p.get("price") else 0.0,
        "permalink": p.get("permalink"),
        "images": images,
        "categories": categories,
    }


class ProductEmbeddingManager:
    BATCH_SIZE = 8  # Small batches to fit in low RAM

    def __init__(self):
        self.wc_client = WooCommerceClient()
        self.db_client = DatabaseClient()
        
        # Initialize FastEmbed locally
        model_name = os.getenv("EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5")
        logger.info(f"Initializing FastEmbed with model: {model_name}")
        self.embedding_model = TextEmbedding(model_name=model_name)

    def _embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Embed a small batch of texts and return list of float vectors."""
        return [arr.tolist() for arr in self.embedding_model.embed(texts)]

    async def sync_products(self) -> bool:
        """Fetch all WooCommerce products, generate embeddings, and upsert to Supabase."""
        if not self.db_client.client:
            logger.error("Supabase client is not initialized. Cannot sync.")
            return False
            
        logger.info("Starting WooCommerce products sync...")
        products = await self.wc_client.get_all_products()
        if not products:
            logger.warning("No products fetched from WooCommerce.")
            return False
            
        total = len(products)
        logger.info(f"Fetched {total} products from WooCommerce. Processing in batches of {self.BATCH_SIZE}...")
        
        success_count = 0
        
        for i in range(0, total, self.BATCH_SIZE):
            batch_products = products[i:i + self.BATCH_SIZE]
            batch_num = i // self.BATCH_SIZE + 1
            total_batches = (total + self.BATCH_SIZE - 1) // self.BATCH_SIZE
            logger.info(f"Batch {batch_num}/{total_batches} — embedding {len(batch_products)} products...")
            
            # Prepare texts and docs for this batch only
            texts = [prepare_product_search_text(p) for p in batch_products]
            docs = [prepare_product_doc(p) for p in batch_products]
            
            try:
                embeddings = self._embed_batch(texts)
                for j, doc in enumerate(docs):
                    doc["embedding"] = embeddings[j]
            except Exception as e:
                logger.error(f"Error generating embeddings for batch {batch_num}: {e}")
                # Skip this batch but continue with the rest
                gc.collect()
                continue
            
            # Upsert this batch to Supabase immediately
            for doc in docs:
                success = await self.db_client.upsert_product(doc)
                if success:
                    success_count += 1
            
            # Free memory
            del texts, docs, embeddings, batch_products
            gc.collect()
                
        logger.info(f"✅ Successfully synced {success_count}/{total} products.")
        return success_count == total

# For running as a standalone script
if __name__ == "__main__":
    manager = ProductEmbeddingManager()
    asyncio.run(manager.sync_products())
