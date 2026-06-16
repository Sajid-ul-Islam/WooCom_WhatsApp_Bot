import os
import logging
import json
from typing import List, Dict, Any, Optional
from fastembed import TextEmbedding

from db import DatabaseClient

logger = logging.getLogger(__name__)

class RAGAgent:
    def __init__(self):
        self.db_client = DatabaseClient()
        
        # Load embedding model
        model_name = os.getenv("EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5")
        try:
            self.embedding_model = TextEmbedding(model_name=model_name)
        except Exception as e:
            logger.error(f"Error loading embedding model: {e}")
            self.embedding_model = None

        # Load LLM configs
        self.provider = os.getenv("LLM_PROVIDER", "").lower()
        self.openai_key = os.getenv("OPENAI_API_KEY")
        self.openai_model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        
        self.anthropic_key = os.getenv("ANTHROPIC_API_KEY")
        self.anthropic_model = os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-20241022")

        self.groq_key = os.getenv("GROQ_API_KEY")
        self.groq_model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

        self.grok_key = os.getenv("GROK_API_KEY")
        self.grok_model = os.getenv("GROK_MODEL", "grok-2-latest")

        self.openrouter_key = os.getenv("OPENROUTER_API_KEY")
        self.openrouter_model = os.getenv("OPENROUTER_MODEL", "meta-llama/llama-3-8b-instruct")

        self.gemini_key = os.getenv("GEMINI_API_KEY")
        self.gemini_model = os.getenv("GEMINI_MODEL", "gemini-1.5-flash-latest")

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
        providers_to_try = []
        if self.provider:
            providers_to_try.append(self.provider)
            
        # Add available fallbacks in priority order
        if "openrouter" not in providers_to_try and self.openrouter_key: providers_to_try.append("openrouter")
        if "groq" not in providers_to_try and self.groq_key: providers_to_try.append("groq")
        if "grok" not in providers_to_try and self.grok_key: providers_to_try.append("grok")
        if "gemini" not in providers_to_try and self.gemini_key: providers_to_try.append("gemini")
        if "openai" not in providers_to_try and self.openai_key: providers_to_try.append("openai")
        if "anthropic" not in providers_to_try and self.anthropic_key: providers_to_try.append("anthropic")
            
        if not providers_to_try:
            return "Error: No LLM API keys configured. Please add an API key to your Supabase config table."
            
        errors = []
        
        for provider in providers_to_try:
            if provider == "anthropic":
                if not self.anthropic_key:
                    errors.append("Anthropic key missing.")
                    continue
                try:
                    from anthropic import AsyncAnthropic
                    client = AsyncAnthropic(api_key=self.anthropic_key)
                    messages_list = []
                    if history:
                        messages_list.extend(history)
                    messages_list.append({"role": "user", "content": user_prompt})

                    response = await client.messages.create(
                        model=self.anthropic_model,
                        max_tokens=600,
                        temperature=0.3,
                        system=system_prompt,
                        messages=messages_list
                    )
                    return response.content[0].text
                except Exception as e:
                    errors.append(f"Anthropic: {str(e)}")
                    logger.warning(f"Anthropic API failed, falling back: {e}")
                    continue
            else:
                # All other providers are OpenAI compatible!
                base_url = None
                api_key = None
                model = None
                
                if provider == "openai":
                    api_key = self.openai_key
                    model = self.openai_model
                elif provider == "groq":
                    api_key = self.groq_key
                    model = self.groq_model
                    base_url = "https://api.groq.com/openai/v1"
                elif provider == "grok":
                    api_key = self.grok_key
                    model = self.grok_model
                    base_url = "https://api.x.ai/v1"
                elif provider == "openrouter":
                    api_key = self.openrouter_key
                    model = self.openrouter_model
                    base_url = "https://openrouter.ai/api/v1"
                elif provider == "gemini":
                    api_key = self.gemini_key
                    model = self.gemini_model
                    base_url = "https://generativelanguage.googleapis.com/v1beta/openai/"
                
                if not api_key:
                    errors.append(f"{provider.capitalize()} key missing.")
                    continue
                    
                try:
                    from openai import AsyncOpenAI
                    client_kwargs = {"api_key": api_key}
                    if base_url:
                        client_kwargs["base_url"] = base_url
                    
                    client = AsyncOpenAI(**client_kwargs)
                    
                    messages = [{"role": "system", "content": system_prompt}]
                    if history:
                        messages.extend(history)
                    messages.append({"role": "user", "content": user_prompt})
                    
                    response = await client.chat.completions.create(
                        model=model,
                        messages=messages,
                        max_tokens=600,
                        temperature=0.3
                    )
                    return response.choices[0].message.content or ""
                except Exception as e:
                    errors.append(f"{provider.capitalize()}: {str(e)}")
                    logger.warning(f"{provider.capitalize()} API failed, falling back: {e}")
                    continue

        error_msg = " | ".join(errors)
        return f"Sorry, all AI providers failed. Errors: {error_msg}"

    async def _analyze_query(self, query: str) -> dict:
        """
        Uses the LLM to classify intent and extract search parameters.
        Returns a dict: { "intent": str, "search_terms": str, "max_price": float|None, "min_price": float|None }
        """
        system_prompt = (
            "You are a strict JSON query analyzer for an e-commerce store. "
            "Analyze the user's message and output a RAW JSON object. DO NOT wrap the JSON in Markdown formatting (no ```json). Just output raw JSON.\n\n"
            "Format:\n"
            "{\n"
            '  "intent": "product_search" | "small_talk" | "support" | "order_status",\n'
            '  "search_terms": "Cleaned string focusing only on product features/names (e.g. \'red running shoes\'). Leave empty if not product_search",\n'
            '  "max_price": numeric or null,\n'
            '  "min_price": numeric or null\n'
            "}\n\n"
            "Rules:\n"
            "- If the user says 'hi', 'hello', 'thanks', intent = 'small_talk'.\n"
            "- If the user says 'where is my order', intent = 'order_status'.\n"
            "- If the user says 'i need help with a return', intent = 'support'.\n"
            "- If the user is asking to buy, browse, or find items, intent = 'product_search'.\n"
            "- Extract max_price/min_price ONLY if explicitly mentioned (e.g. 'under 50' -> max_price: 50.0)."
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
                "min_price": data.get("min_price")
            }
        except Exception as e:
            logger.error(f"Error analyzing query: {e}. Falling back to default product search.")
            return {
                "intent": "product_search",
                "search_terms": query,
                "max_price": None,
                "min_price": None
            }

    async def answer_query(self, query: str, history: list = None) -> Dict[str, Any]:
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
                "products": []
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
            "Guidelines:\n"
            "1. ONLY discuss and recommend products from the provided Context if it is relevant. "
            "2. If the user asks about products not in the store, reply politely that we don't have them but suggest the closest alternative from our store if possible.\n"
            "3. Always mention product prices clearly.\n"
            "4. Keep responses under 3 short paragraphs. WhatsApp users prefer quick answers.\n"
            "5. To add a product to the cart, the user will reply with: *Add [ID]* (e.g. *Add 123*)."
        )
        
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
            "products": matching_products
        }
