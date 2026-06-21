"""
Fuzzy product search using rapidfuzz for fast multi-field matching.
Indexes WooCommerce products and allows fuzzy search across name, price,
categories, tags, and size/variation attributes.
"""
import re
import logging
import asyncio
from typing import List, Dict, Any, Optional, Tuple
from rapidfuzz import process, fuzz

logger = logging.getLogger(__name__)


class FuzzyProductSearch:
    """In-memory fuzzy search index over WooCommerce products.

    Each indexed product stores a pre-computed searchable text blob that
    combines name, categories, tags, price, and available sizes so that a
    single ``process.extract`` call can rank results across all relevant
    fields at once.
    """

    # Weights used when combining per-field scores into a final score.
    WEIGHTS = {
        "name": 0.40,
        "categories": 0.15,
        "tags": 0.10,
        "description": 0.10,
        "price": 0.10,
        "size": 0.15,
    }

    # Size alias map — keys are canonical, values are accepted variants.
    SIZE_ALIASES: Dict[str, List[str]] = {
        "xs": ["xs", "extra small", "extra-small", "xxs"],
        "s": ["s", "small"],
        "m": ["m", "medium", "med"],
        "l": ["l", "large", "lg"],
        "xl": ["xl", "extra large", "extra-large"],
        "xxl": ["xxl", "2xl", "double xl", "double-extra-large"],
        "xxxl": ["xxxl", "3xl", "triple xl"],
    }

    def __init__(self):
        # product_id -> raw WooCommerce product dict
        self._products: Dict[int, Dict[str, Any]] = {}
        # product_id -> searchable text blob (concatenated fields)
        self._search_text: Dict[int, str] = {}
        # product_id -> list of available size strings (from variations)
        self._sizes: Dict[int, List[str]] = {}
        # product_id -> list of variation dicts (id, price, attributes, stock_status)
        self._variations: Dict[int, List[Dict[str, Any]]] = {}
        # Whether the index has been populated at least once
        self.ready = False

    # ------------------------------------------------------------------
    # Index building
    # ------------------------------------------------------------------

    def index_products(self, products: List[Dict[str, Any]]):
        """Rebuild the product and search-text index.

        NOTE: Does **not** clear ``_sizes`` or ``_variations`` so that
        variation data fetched during ``sync_from_woo`` is preserved.
        Call ``clear()`` first if a full reset is needed.
        """
        self._products.clear()
        self._search_text.clear()

        for p in products:
            pid = p.get("id")
            if not pid:
                continue
            self._products[pid] = p
            self._search_text[pid] = self._build_search_text(p)

        self.ready = True
        logger.info(f"FuzzyProductSearch index built with {len(self._products)} products.")

    def clear(self):
        """Reset the entire index including variations."""
        self._products.clear()
        self._search_text.clear()
        self._sizes.clear()
        self._variations.clear()
        self.ready = False

    async def sync_from_woo(self, wc_client, max_products: int = 500) -> int:
        """Fetch products from WooCommerce and rebuild the index.

        Uses concurrent fetching for variations with a concurrency limit to
        avoid overwhelming the WooCommerce API.

        Returns the number of products indexed.
        """
        self.clear()

        products = await wc_client.get_all_products()
        if not products:
            logger.warning("FuzzyProductSearch: No products returned from WooCommerce.")
            return 0

        products = products[:max_products]

        # Fetch variations concurrently with bounded parallelism
        variable_products = [
            p for p in products
            if p.get("type") == "variable" and p.get("id")
        ]
        if variable_products:
            semaphore = asyncio.Semaphore(5)  # max 5 concurrent WC requests

            async def _fetch_variations(pid: int):
                async with semaphore:
                    try:
                        return pid, await wc_client.get_product_variations(pid)
                    except Exception as e:
                        logger.debug(f"Could not fetch variations for product {pid}: {e}")
                        return pid, []

            tasks = [_fetch_variations(p["id"]) for p in variable_products]
            results = await asyncio.gather(*tasks)
            for pid, variations in results:
                if variations:
                    self._variations[pid] = variations
                    self._sizes[pid] = self._extract_sizes(variations)

        # index_products preserves _sizes / _variations (no clear)
        self.index_products(products)
        return len(self._products)

    # ------------------------------------------------------------------
    # Search text construction
    # ------------------------------------------------------------------

    @staticmethod
    def _clean_html(text: str) -> str:
        """Strip HTML tags from text."""
        if not text:
            return ""
        return re.sub(r"<[^>]+>", " ", text)

    @staticmethod
    def _extract_sizes(variations: List[Dict[str, Any]]) -> List[str]:
        """Extract unique size option values from variation attributes."""
        sizes = []
        for v in variations:
            for attr in v.get("attributes", []):
                if attr.get("name", "").lower() == "size":
                    option = attr.get("option", "")
                    if option and option not in sizes:
                        sizes.append(option)
        return sizes

    def _build_search_text(self, product: Dict[str, Any]) -> str:
        """Build a weighted text blob for a product.

        The name is repeated to give it more weight in the fuzzy score.
        Sizes from variations are appended so queries like "XL" or "large"
        match directly.
        """
        name = product.get("name", "")
        description = self._clean_html(
            product.get("description", "")
        ) or self._clean_html(
            product.get("short_description", "")
        )
        price = str(product.get("price", ""))
        categories = " ".join(
            cat.get("name", "") for cat in product.get("categories", [])
        )
        tags = " ".join(tag.get("name", "") for tag in product.get("tags", []))

        # Repeat name for higher weight
        name_weighted = " ".join([name] * 3)

        # Sizes
        pid = product.get("id")
        sizes_str = " ".join(self._sizes.get(pid, []))

        # Price without currency symbol for numeric-ish matching
        price_clean = re.sub(r"[^\d.]", "", price)

        parts = [
            name_weighted,
            f"Name: {name}",
            f"Price: {price_clean}",
            f"Categories: {categories}",
            f"Tags: {tags}",
            f"Sizes: {sizes_str}",
            f"Description: {description[:300]}",
        ]
        return " ".join(p for p in parts if p)

    # ------------------------------------------------------------------
    # Public search API
    # ------------------------------------------------------------------

    def search(
        self,
        query: str,
        max_results: int = 8,
        min_score: float = 40.0,
        max_price: Optional[float] = None,
        min_price: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """Fuzzy search across all indexed products.

        Returns a list of product dicts augmented with a ``_fuzzy_score``
        float (0-100) representing match quality.
        """
        if not self.ready or not self._products:
            return []

        query_clean = query.strip()
        if not query_clean:
            return []

        # ---- Step 1: Overall fuzzy match against the text blobs ----
        search_texts = {
            pid: text for pid, text in self._search_text.items()
        }
        raw_matches = process.extract(
            query_clean,
            search_texts,
            scorer=fuzz.token_set_ratio,
            limit=max_results * 3,  # over-fetch for post-filtering
        )

        # ---- Step 2: Per-field scoring for nuanced ranking ----
        results: List[Tuple[int, float]] = []
        for pid, text_blob, overall_score in raw_matches:
            product = self._products[pid]

            # Individual field scores
            name_score = fuzz.token_set_ratio(
                query_clean, product.get("name", "")
            )
            cat_names = " ".join(
                c.get("name", "") for c in product.get("categories", [])
            )
            cat_score = fuzz.partial_ratio(query_clean, cat_names)
            tag_names = " ".join(
                t.get("name", "") for t in product.get("tags", [])
            )
            tag_score = fuzz.partial_ratio(query_clean, tag_names)
            desc_short = self._clean_html(product.get("description", ""))[:200]
            desc_score = fuzz.partial_ratio(query_clean, desc_short)

            # Price matching — extract numeric parts from the query
            price_score = self._score_price(query_clean, product)

            # Size matching — "XL", "large", "L" etc.
            size_score = self._score_size(query_clean, pid)

            # Weighted composite
            composite = (
                self.WEIGHTS["name"] * name_score
                + self.WEIGHTS["categories"] * cat_score
                + self.WEIGHTS["tags"] * tag_score
                + self.WEIGHTS["description"] * desc_score
                + self.WEIGHTS["price"] * price_score
                + self.WEIGHTS["size"] * size_score
            )

            results.append((pid, composite))

        # Sort by composite score descending
        results.sort(key=lambda x: x[1], reverse=True)

        # ---- Step 3: Apply price filters and build output ----
        output: List[Dict[str, Any]] = []
        for pid, score in results:
            if score < min_score:
                continue
            product = self._products[pid]
            price_val = self._parse_price(product.get("price", "0"))
            if max_price is not None and price_val > max_price:
                continue
            if min_price is not None and price_val < min_price:
                continue

            enriched = dict(product)
            enriched["_fuzzy_score"] = round(score, 1)
            # Attach variations if available
            if pid in self._variations:
                enriched["_variations"] = self._variations[pid]
            if pid in self._sizes:
                enriched["_available_sizes"] = self._sizes[pid]

            output.append(enriched)
            if len(output) >= max_results:
                break

        return output

    def upsert_product(self, product: Dict[str, Any]):
        """Update or add a single product in the index (called from product webhooks)."""
        pid = product.get("id")
        if not pid:
            return
        self._products[pid] = product
        self._search_text[pid] = self._build_search_text(product)
        self.ready = True

    def remove_product(self, product_id: int):
        """Remove a product from the index (e.g. when deleted in WooCommerce)."""
        self._products.pop(product_id, None)
        self._search_text.pop(product_id, None)
        self._sizes.pop(product_id, None)
        self._variations.pop(product_id, None)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _score_price(self, query: str, product: Dict[str, Any]) -> float:
        """Return 0-100 score for how well the query matches the product price."""
        # Extract numbers from query (e.g. "under 500" -> [500], "shirt 200 bdt" -> [200])
        numbers = re.findall(r"\d+(?:\.\d+)?", query)
        if not numbers:
            return 50.0  # neutral if no price mentioned

        product_price = self._parse_price(product.get("price", "0"))
        if product_price <= 0:
            return 30.0

        best_score = 0.0
        for num_str in numbers:
            try:
                query_num = float(num_str)
            except ValueError:
                continue

            # Exact price match
            if abs(query_num - product_price) < 1:
                best_score = max(best_score, 100.0)
            # Query is "under X" style — product is within range
            elif query_num > product_price and query_num - product_price < query_num * 0.3:
                best_score = max(best_score, 80.0)
            # Close enough (within 20%)
            elif abs(query_num - product_price) / max(query_num, 1) < 0.2:
                best_score = max(best_score, 70.0)
            # Within 50%
            elif abs(query_num - product_price) / max(query_num, 1) < 0.5:
                best_score = max(best_score, 50.0)
            else:
                best_score = max(best_score, 20.0)

        return best_score

    def _score_size(self, query: str, product_id: int) -> float:
        """Return 0-100 score for how well the query matches product sizes.

        Uses word-boundary matching for short aliases (e.g. "s", "m") to
        avoid false positives where "shirt" matches the "s" size alias.
        """
        sizes = self._sizes.get(product_id, [])
        if not sizes:
            # Check if product itself has a size attribute (simple products)
            product = self._products.get(product_id, {})
            for attr in product.get("attributes", []):
                if attr.get("name", "").lower() == "size":
                    options = attr.get("options", [])
                    if options:
                        sizes = options
                    break

        if not sizes:
            return 40.0  # neutral when no size info available

        # Tokenize query into words for word-boundary matching
        query_lower = query.lower()
        query_words = set(re.findall(r"\b\w+\b", query_lower))

        for size in sizes:
            size_lower = size.lower().strip()

            # 1. Direct exact match (e.g. query contains "xl" and product has "xl")
            if size_lower in query_words or size_lower in query_lower:
                return 100.0

            # 2. Multi-word size names match as substrings (safe for "extra small" etc.)
            if len(size_lower) > 2 and size_lower in query_lower:
                return 95.0

            # 3. Check aliases using word-boundary matching
            for canonical, aliases in self.SIZE_ALIASES.items():
                if size_lower == canonical or size_lower in aliases:
                    for alias in aliases:
                        # Short aliases (1-2 chars) must match as whole words
                        if len(alias) <= 2:
                            if alias in query_words:
                                return 95.0
                        else:
                            if alias in query_lower:
                                return 95.0

        # 4. Partial fuzzy match as last resort
        best = 0.0
        for size in sizes:
            score = fuzz.partial_ratio(query_lower, size.lower())
            if score > best:
                best = score

        return best if best > 30 else 40.0

    @staticmethod
    def _parse_price(price_str) -> float:
        """Parse a price string to float."""
        if isinstance(price_str, (int, float)):
            return float(price_str)
        if not price_str:
            return 0.0
        cleaned = re.sub(r"[^\d.]", "", str(price_str))
        try:
            return float(cleaned)
        except (ValueError, TypeError):
            return 0.0
