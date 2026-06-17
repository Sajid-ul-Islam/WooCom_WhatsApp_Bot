import os
import asyncio
import logging
import json
from typing import List, Dict, Any
from fastembed import TextEmbedding

from db import DatabaseClient

logger = logging.getLogger(__name__)


# --- Provider Registry ---
# Each entry maps a provider name to its env-var keys, default model, and base URL.
# Providers using the "anthropic" api_type get special handling; all others are
# assumed to be OpenAI-compatible and can share a single code path.

PROVIDER_REGISTRY: Dict[str, Dict[str, Any]] = {
    "openai": {
        "key_env": "OPENAI_API_KEY",
        "model_env": "OPENAI_MODEL",
        "default_model": "gpt-4o-mini",
        "base_url": None,
    },
    "anthropic": {
        "key_env": "ANTHROPIC_API_KEY",
        "model_env": "ANTHROPIC_MODEL",
        "default_model": "claude-3-5-sonnet-20241022",
        "base_url": None,
        "api_type": "anthropic",
    },
    "groq": {
        "key_env": "GROQ_API_KEY",
        "model_env": "GROQ_MODEL",
        "default_model": "llama-3.3-70b-versatile",
        "base_url": "https://api.groq.com/openai/v1",
    },
    "grok": {
        "key_env": "GROK_API_KEY",
        "model_env": "GROK_MODEL",
        "default_model": "grok-2-latest",
        "base_url": "https://api.x.ai/v1",
    },
    "openrouter": {
        "key_env": "OPENROUTER_API_KEY",
        "model_env": "OPENROUTER_MODEL",
        "default_model": "meta-llama/llama-3-8b-instruct",
        "base_url": "https://openrouter.ai/api/v1",
    },
    "gemini": {
        "key_env": "GEMINI_API_KEY",
        "model_env": "GEMINI_MODEL",
        "default_model": "gemini-1.5-flash-latest",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
    },
}

# Fallback order when the primary provider fails or isn't set.
FALLBACK_PRIORITY = ["openrouter", "groq", "grok", "gemini", "openai", "anthropic"]


class RAGAgent:
    def __init__(self, db_client=None):
        self.db_client = db_client or DatabaseClient()

        # Load embedding model
        model_name = os.getenv("EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5")
        try:
            self.embedding_model = TextEmbedding(model_name=model_name)
        except Exception as e:
            logger.error(f"Error loading embedding model: {e}")
            self.embedding_model = None

        # Load LLM provider configs from the registry
        self.provider = os.getenv("LLM_PROVIDER", "").lower()
        self.providers: Dict[str, Dict[str, Any]] = {}
        for name, reg in PROVIDER_REGISTRY.items():
            key = os.getenv(reg["key_env"])
            if key:
                self.providers[name] = {
                    "key": key,
                    "model": os.getenv(reg["model_env"], reg["default_model"]),
                    "base_url": reg.get("base_url"),
                    "api_type": reg.get("api_type", "openai"),
                }

    def _generate_query_embedding(self, query: str) -> List[float]:
        """Generate vector embedding for user query."""
        if not self.embedding_model:
            return []
        try:
            generator = self.embedding_model.embed([query])
            embeddings = [arr.tolist() for arr in generator]
            return embeddings[0] if embeddings else []
        except Exception as e:
            logger.error(f"Failed to generate query embedding: {e}")
            return []

    async def _call_llm(self, system_prompt: str, user_prompt: str, history: list = None) -> str:
        """Call the configured LLM APIs with dynamic fallback."""
        # Build ordered list of providers to try: primary first, then fallbacks.
        providers_to_try: list[str] = []
        if self.provider and self.provider in self.providers:
            providers_to_try.append(self.provider)

        for name in FALLBACK_PRIORITY:
            if name not in providers_to_try and name in self.providers:
                providers_to_try.append(name)

        if not providers_to_try:
            return "Error: No LLM API keys configured. Please add an API key to your Supabase config table."

        MAX_RETRIES = 3
        BASE_DELAY = 1.0  # seconds

        errors: list[str] = []

        for provider_name in providers_to_try:
            config = self.providers[provider_name]
            api_key = config["key"]
            model = config["model"]
            base_url = config.get("base_url")

            for attempt in range(MAX_RETRIES):
                try:
                    if config.get("api_type") == "anthropic":
                        return await self._call_anthropic(api_key, model, system_prompt, user_prompt, history)
                    else:
                        return await self._call_openai_compatible(api_key, model, base_url, system_prompt, user_prompt, history)
                except Exception as e:
                    delay = BASE_DELAY * (2 ** attempt)
                    logger.warning(
                        f"{provider_name} attempt {attempt + 1}/{MAX_RETRIES} failed: {e}"
                        + (f" — retrying in {delay:.1f}s" if attempt < MAX_RETRIES - 1 else "")
                    )
                    if attempt < MAX_RETRIES - 1:
                        await asyncio.sleep(delay)
                    else:
                        errors.append(f"{provider_name}: {e}")

        error_msg = " | ".join(errors)
        return f"Sorry, all AI providers failed. Errors: {error_msg}"

    async def _call_anthropic(self, api_key: str, model: str, system_prompt: str, user_prompt: str, history: list = None) -> str:
        """Call the Anthropic Messages API."""
        from anthropic import AsyncAnthropic

        client = AsyncAnthropic(api_key=api_key)
        messages_list = list(history) if history else []
        messages_list.append({"role": "user", "content": user_prompt})

        response = await client.messages.create(
            model=model,
            max_tokens=600,
            temperature=0.3,
            system=system_prompt,
            messages=messages_list,
        )
        return response.content[0].text

    async def _call_openai_compatible(self, api_key: str, model: str, base_url: str | None, system_prompt: str, user_prompt: str, history: list = None) -> str:
        """Call any OpenAI-compatible chat completions endpoint."""
        from openai import AsyncOpenAI

        client_kwargs: dict[str, Any] = {"api_key": api_key}
        if base_url:
            client_kwargs["base_url"] = base_url

        client = AsyncOpenAI(**client_kwargs)

        messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": user_prompt})

        response = await client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=600,
            temperature=0.3,
        )
        return response.choices[0].message.content or ""

    async def _analyze_query(self, query: str) -> dict:
        """
        Uses the LLM to classify intent and extract search parameters.
        Returns a dict: { "intent": str, "search_terms": str, "max_price": float|None, "min_price": float|None, "sentiment": str }
        """
        system_prompt = (
            "You are a strict JSON query analyzer for an e-commerce store. "
            "Analyze the user's message and output a RAW JSON object. DO NOT wrap the JSON in Markdown formatting (no ```json). Just output raw JSON.\n\n"
            "Format:\n"
            "{\n"
            '  "intent": "product_search" | "small_talk" | "support" | "order_status",\n'
            '  "search_terms": "Cleaned string focusing only on product features/names (e.g. \'red running shoes\'). Leave empty if not product_search",\n'
            '  "max_price": numeric or null,\n'
            '  "min_price": numeric or null,\n'
            '  "sentiment": "positive" | "neutral" | "frustrated" | "angry"\n'
            "}\n\n"
            "Rules:\n"
            "- If the user says 'hi', 'hello', 'thanks', intent = 'small_talk'.\n"
            "- If the user says 'where is my order', intent = 'order_status'.\n"
            "- If the user says 'i need help with a return', intent = 'support'.\n"
            "- If the user is asking to buy, browse, or find items, intent = 'product_search'.\n"
            "- Extract max_price/min_price ONLY if explicitly mentioned (e.g. 'under 50' -> max_price: 50.0).\n"
            "- Detect the customer's sentiment. If they are showing annoyance, impatience, complaining, or using aggressive words, mark as 'frustrated' or 'angry'. Otherwise, default to 'neutral' or 'positive' if expressing satisfaction."
        )
        try:
            response_text = await self._call_llm(system_prompt, f"User Query: {query}")

            clean_text = response_text.strip()
            if clean_text.startswith("```json"):
                clean_text = clean_text[7:]
            if clean_text.startswith("```"):
                clean_text = clean_text[3:]
            if clean_text.endswith("```"):
                clean_text = clean_text[:-3]

            data = json.loads(clean_text.strip())

            return {
                "intent": data.get("intent", "product_search"),
                "search_terms": data.get("search_terms", query),
                "max_price": data.get("max_price"),
                "min_price": data.get("min_price"),
                "sentiment": data.get("sentiment", "neutral")
            }
        except Exception as e:
            logger.error(f"Error analyzing query: {e}. Falling back to default product search.")
            return {
                "intent": "product_search",
                "search_terms": query,
                "max_price": None,
                "min_price": None,
                "sentiment": "neutral"
            }

    async def answer_query(self, query: str, history: list = None, orders: list = None) -> Dict[str, Any]:
        """
        Processes user query dynamically.
        """
        logger.info(f"Processing query dynamically: '{query}'")

        # 1. Analyze query
        analysis = await self._analyze_query(query)
        intent = analysis["intent"]
        search_terms = analysis["search_terms"] or query
        max_price = analysis["max_price"]
        min_price = analysis["min_price"]
        sentiment = analysis["sentiment"]

        logger.info(f"Query Analysis: {analysis}")

        matching_products = []

        # 2. Route based on intent
        if intent in ["small_talk", "support", "order_status"]:
            system_prompt = (
                "You are an expert, friendly sales assistant for our online store.\n"
                "CRITICAL: Automatically detect the language the user is speaking and reply fluently in that EXACT same language!\n"
                "You MUST format your replies for WhatsApp. Keep them concise and clear.\n\n"
            )
            if intent == "order_status":
                system_prompt += "The user is asking about an order. Tell them they can check their order status by clicking the 'My Orders' button in the main menu."
            elif intent == "support":
                system_prompt += "The user needs support. Tell them they can talk to a human by clicking the 'Talk to Human' button in the main menu."
            elif intent == "small_talk":
                system_prompt += "The user is making small talk. Be polite, friendly, and ask how you can help them find the perfect product today."

            response_text = await self._call_llm(system_prompt, query, history)
            return {
                "text": response_text,
                "products": [],
                "sentiment": sentiment
            }

        # 3. Product Search Intent
        query_embedding = self._generate_query_embedding(search_terms)
        context_warning = ""

        if query_embedding:
            # Fetch up to 20 for Python-side filtering
            raw_matches = await self.db_client.match_products(query_embedding, threshold=0.3, limit=20)

            # 4. Hybrid Filtering
            filtered_matches = []
            for p in raw_matches:
                price = float(p.get("price") or 0)
                if max_price is not None and price > max_price:
                    continue
                if min_price is not None and price < min_price:
                    continue
                filtered_matches.append(p)

            # If our filters killed all results, fall back to raw matches to at least show something
            if not filtered_matches and raw_matches:
                matching_products = raw_matches[:4]
                context_warning = f"Note: I could not find exact matches within the budget constraint ({min_price}-{max_price}), but here are the closest alternatives."
            else:
                matching_products = filtered_matches[:4]

        # 5. Construct Product Prompt
        system_prompt = (
            "You are an expert sales assistant for our online store. "
            "Your job is to answer user queries politely and helpfully. "
            "CRITICAL: Automatically detect the language the user is speaking and reply fluently in that EXACT same language! "
            "You MUST format your replies for WhatsApp. Keep them concise and clear.\n"
            "Use WhatsApp formatting:\n"
            "- Bold text with asterisks, e.g. *bold text*\n"
            "- Italics with underscores, e.g. _italic text_\n"
            "- Strikethrough with tildes, e.g. ~strikethrough~\n"
            "- Use bullet points or emojis for lists.\n\n"
            "Sizing Guidelines (for Panjabis and Shirts):\n"
            "- Height 5'2\"-5'5\", Weight 50-60 kg: S (Small, Chest: 38\")\n"
            "- Height 5'5\"-5'7\", Weight 60-70 kg: M (Medium, Chest: 40\")\n"
            "- Height 5'7\"-5'10\", Weight 70-80 kg: L (Large, Chest: 42\")\n"
            "- Height 5'10\"-6'0\", Weight 80-90 kg: XL (Extra Large, Chest: 44\")\n"
            "- Height 6'0\"+, Weight 90+ kg: XXL (Double Extra Large, Chest: 46\")\n\n"
            "Delivery Policy:\n"
            "- Inside Dhaka: 80 BDT, 2-3 days\n"
            "- Outside Dhaka: 150 BDT, 3-5 days\n"
            "- Cash on Delivery (COD) is available nationwide.\n\n"
            "Guidelines:\n"
            "1. ONLY discuss and recommend products from the provided Context if it is relevant. "
            "2. If the user asks about products not in the store, reply politely that we don't have them but suggest the closest alternative from our store if possible.\n"
            "3. Always mention product prices clearly.\n"
            "4. Keep responses under 3 short paragraphs. WhatsApp users prefer quick answers.\n"
            "5. To add a product to the cart, the user will reply with: *Add [ID]* (e.g. *Add 123*).\n"
        )

        if orders:
            history_desc = []
            for o in orders[:3]:
                for item in o.get("items", []):
                    history_desc.append(f"{item.get('name')}")
            if history_desc:
                system_prompt += f"6. Customer previously purchased: {', '.join(history_desc)}. Suggest similar or complementary items from the catalog if relevant.\n"

        context_str = "Available Products in Store:\n"
        if context_warning:
            context_str += f"[{context_warning}]\n\n"

        if matching_products:
            for p in matching_products:
                desc = p.get("description", "")[:120] + "..." if len(p.get("description", "")) > 120 else p.get("description", "")
                context_str += f"- ID: {p.get('id')}\n  Name: {p.get('name')}\n  Price: ${p.get('price')}\n  Description: {desc}\n  Link: {p.get('permalink')}\n\n"
        else:
            context_str += "No products matched this specific search directly. Recommend browsing categories or searching general terms."

        user_prompt = f"Context:\n{context_str}\n\nUser Query: {query}\n\nProvide your sales assistant response:"

        response_text = await self._call_llm(system_prompt, user_prompt, history)

        return {
            "text": response_text,
            "products": matching_products,
            "sentiment": sentiment
        }
