import os
import re
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

class ProductEmbeddingManager:
    def __init__(self):
        self.wc_client = WooCommerceClient()
        self.db_client = DatabaseClient()
        
        # Initialize FastEmbed locally
        model_name = os.getenv("EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5")
        logger.info(f"Initializing FastEmbed with model: {model_name}")
        self.embedding_model = TextEmbedding(model_name=model_name)

    def generate_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Generate vector embeddings for a list of texts using FastEmbed."""
        logger.info(f"Generating embeddings for {len(texts)} texts...")
        # text_embeddings is a generator of numpy arrays
        embeddings_generator = self.embedding_model.embed(texts)
        # Convert to list of lists (float)
        embeddings = [arr.tolist() for arr in embeddings_generator]
        return embeddings

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
            
        logger.info(f"Fetched {len(products)} products from WooCommerce. Generating embeddings...")
        
        # Prepare texts for embeddings
        texts = []
        product_docs = []
        
        for p in products:
            search_text = prepare_product_search_text(p)
            texts.append(search_text)
            
            # Map WooCommerce properties to Supabase columns
            images = [{"src": img.get("src")} for img in p.get("images", [])]
            categories = [{"id": cat.get("id"), "name": cat.get("name")} for cat in p.get("categories", [])]
            
            doc = {
                "id": p.get("id"),
                "name": p.get("name"),
                "description": clean_html(p.get("description", "")),
                "price": float(p.get("price")) if p.get("price") else 0.0,
                "permalink": p.get("permalink"),
                "images": images,
                "categories": categories,
            }
            product_docs.append(doc)
            
        # Bulk generate embeddings
        try:
            embeddings = self.generate_embeddings(texts)
            for i, doc in enumerate(product_docs):
                doc["embedding"] = embeddings[i]
        except Exception as e:
            logger.error(f"Error generating embeddings: {e}")
            return False
            
        logger.info("Upserting products to Supabase...")
        success_count = 0
        for doc in product_docs:
            success = await self.db_client.upsert_product(doc)
            if success:
                success_count += 1
                
        logger.info(f"Successfully synced {success_count}/{len(product_docs)} products.")
        return success_count == len(product_docs)

# For running as a standalone script
if __name__ == "__main__":
    manager = ProductEmbeddingManager()
    asyncio.run(manager.sync_products())
