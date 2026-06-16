import os
import logging
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
        self.groq_model = os.getenv("GROQ_MODEL", "llama3-8b-8192")

        self.grok_key = os.getenv("GROK_API_KEY")
        self.grok_model = os.getenv("GROK_MODEL", "grok-beta")

        self.openrouter_key = os.getenv("OPENROUTER_API_KEY")
        self.openrouter_model = os.getenv("OPENROUTER_MODEL", "meta-llama/llama-3-8b-instruct:free")

        self.gemini_key = os.getenv("GEMINI_API_KEY")
        self.gemini_model = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")

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

    async def answer_query(self, query: str, history: list = None) -> Dict[str, Any]:
        """
        Processes user query: finds similar products and builds a conversational response.
        Returns a dict: {"text": "Formatted text response", "products": list_of_matching_products}
        """
        logger.info(f"Processing query: '{query}'")
        
        # 1. Embed query
        query_embedding = self._generate_query_embedding(query)
        
        # 2. Vector search matching products
        matching_products = []
        if query_embedding:
            matching_products = await self.db_client.match_products(query_embedding, threshold=0.4, limit=4)
            
        logger.info(f"Found {len(matching_products)} matching products.")

        # 3. Construct System Prompt
        system_prompt = (
            "You are an expert sales assistant for our online store. "
            "Your job is to answer user queries politely and helpfully. "
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

        # 4. Construct Context
        context_str = "Available Products in Store:\n"
        if matching_products:
            for p in matching_products:
                desc = p.get("description", "")[:120] + "..." if len(p.get("description", "")) > 120 else p.get("description", "")
                context_str += f"- ID: {p.get('id')}\n  Name: {p.get('name')}\n  Price: ${p.get('price')}\n  Description: {desc}\n  Link: {p.get('permalink')}\n\n"
        else:
            context_str += "No products matched this specific search directly. Recommend browsing categories or searching general terms."

        user_prompt = f"Context:\n{context_str}\n\nUser Query: {query}\n\nProvide your sales assistant response:"

        # 5. Call LLM
        response_text = await self._call_llm(system_prompt, user_prompt, history)
        
        return {
            "text": response_text,
            "products": matching_products
        }
