"""Web researcher — real web browsing for competitor intelligence.

Inspired by OpenClaw's browser tool. Uses httpx to search the web,
scrape competitor data, and gather market intelligence.
"""

import json
import logging
import re
import uuid
from datetime import datetime, timedelta
from urllib.parse import quote_plus

import httpx
from sqlalchemy.orm import Session

from app.models import WebResearchResult, Competitor

log = logging.getLogger(__name__)

# User-Agent to avoid blocks
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"


class WebResearcher:
    """Performs real web searches and scraping for agent intelligence."""

    def __init__(self, db: Session, shop_id: str):
        self.db = db
        self.shop_id = shop_id

    # ── Public API ────────────────────────────────────────────────────────

    async def search_competitor(self, competitor_name: str, location: str = "") -> dict:
        """Search the web for competitor information."""
        cache = self._check_cache("competitor_search", competitor_name)
        if cache:
            return cache

        results = {"competitor": competitor_name, "findings": [], "sources": []}

        # Search for reviews and reputation
        query = f'"{competitor_name}" reviews {location}'.strip()
        search_results = await self._web_search(query)
        if search_results:
            results["findings"].append({
                "type": "web_presence",
                "data": search_results[:5],
            })
            results["sources"].extend([r.get("url", "") for r in search_results[:5]])

        # Search for pricing and promotions
        promo_query = f'"{competitor_name}" promotions deals discounts {location}'.strip()
        promo_results = await self._web_search(promo_query)
        if promo_results:
            results["findings"].append({
                "type": "promotions",
                "data": promo_results[:3],
            })

        # Search for social media presence
        social_query = f'"{competitor_name}" instagram facebook social media retail'
        social_results = await self._web_search(social_query)
        if social_results:
            results["findings"].append({
                "type": "social_presence",
                "data": social_results[:3],
            })

        self._save_cache("competitor_search", competitor_name, results)
        return results

    async def search_market_trends(self, category: str, location: str = "") -> dict:
        """Search for market trends in the shop's category."""
        cache = self._check_cache("trend_search", f"{category} {location}")
        if cache:
            return cache

        results = {"category": category, "trends": [], "sources": []}

        # Current retail trends
        query = f"{category} retail trends 2026 {location}".strip()
        trend_results = await self._web_search(query)
        if trend_results:
            results["trends"].append({
                "type": "industry_trends",
                "data": trend_results[:5],
            })
            results["sources"].extend([r.get("url", "") for r in trend_results[:5]])

        # Consumer behavior trends
        consumer_query = f"{category} consumer spending trends retail"
        consumer_results = await self._web_search(consumer_query)
        if consumer_results:
            results["trends"].append({
                "type": "consumer_behavior",
                "data": consumer_results[:3],
            })

        self._save_cache("trend_search", f"{category} {location}", results)
        return results

    async def search_all_competitors(self, competitors: list, location: str = "") -> list:
        """Search for all competitors in parallel-ish (sequential for rate limiting)."""
        all_results = []
        for comp in competitors[:5]:  # cap at 5 to avoid rate limiting
            name = comp.get("name", "") if isinstance(comp, dict) else str(comp)
            if not name:
                continue
            try:
                result = await self.search_competitor(name, location)
                all_results.append(result)
            except Exception as e:
                log.warning("Failed to research competitor %s: %s", name, e)
                all_results.append({"competitor": name, "findings": [], "error": str(e)})
        return all_results

    async def search_product_trends(self, product_names: list) -> list:
        """Search for trending info about specific products."""
        results = []
        for name in product_names[:5]:
            cache = self._check_cache("trend_search", f"product:{name}")
            if cache:
                results.append(cache)
                continue
            try:
                query = f'"{name}" trending popular retail 2026'
                search = await self._web_search(query)
                result = {"product": name, "trends": search[:3] if search else []}
                self._save_cache("trend_search", f"product:{name}", result)
                results.append(result)
            except Exception as e:
                log.warning("Failed to research product %s: %s", name, e)
                results.append({"product": name, "trends": [], "error": str(e)})
        return results

    # ── Web Search Implementation ─────────────────────────────────────────

    async def _web_search(self, query: str) -> list:
        """Perform a web search using DuckDuckGo HTML (no API key needed)."""
        try:
            url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
            async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
                resp = await client.get(url, headers={
                    "User-Agent": _UA,
                    "Accept": "text/html",
                    "Accept-Language": "en-US,en;q=0.9",
                })
                if resp.status_code != 200:
                    log.warning("DuckDuckGo search returned %d for: %s", resp.status_code, query)
                    return []
                return self._parse_ddg_results(resp.text)
        except Exception as e:
            log.warning("Web search failed for '%s': %s", query, e)
            return []

    def _parse_ddg_results(self, html: str) -> list:
        """Parse DuckDuckGo HTML search results."""
        results = []
        # Extract result blocks — each result is in a div with class "result"
        # Title is in <a class="result__a"> and snippet in <a class="result__snippet">
        title_pattern = re.compile(
            r'<a[^>]*class="result__a"[^>]*href="([^"]*)"[^>]*>(.*?)</a>',
            re.DOTALL,
        )
        snippet_pattern = re.compile(
            r'<a[^>]*class="result__snippet"[^>]*>(.*?)</a>',
            re.DOTALL,
        )

        titles = title_pattern.findall(html)
        snippets = snippet_pattern.findall(html)

        for i, (url, title) in enumerate(titles[:10]):
            # Clean HTML tags from title and snippet
            clean_title = re.sub(r'<[^>]+>', '', title).strip()
            clean_snippet = ""
            if i < len(snippets):
                clean_snippet = re.sub(r'<[^>]+>', '', snippets[i]).strip()

            # Decode DuckDuckGo redirect URL
            real_url = url
            uddg_match = re.search(r'uddg=([^&]+)', url)
            if uddg_match:
                from urllib.parse import unquote
                real_url = unquote(uddg_match.group(1))

            if clean_title:
                results.append({
                    "title": clean_title,
                    "snippet": clean_snippet,
                    "url": real_url,
                })

        return results

    # ── Caching ───────────────────────────────────────────────────────────

    def _check_cache(self, research_type: str, query: str) -> dict | None:
        """Check if we have a cached result that hasn't expired."""
        cached = (
            self.db.query(WebResearchResult)
            .filter(
                WebResearchResult.shop_id == self.shop_id,
                WebResearchResult.research_type == research_type,
                WebResearchResult.query == query,
            )
            .order_by(WebResearchResult.created_at.desc())
            .first()
        )
        if cached:
            ttl = timedelta(hours=cached.ttl_hours or 24)
            if datetime.utcnow() - cached.created_at < ttl:
                return cached.results_json
        return None

    def _save_cache(self, research_type: str, query: str, results: dict):
        """Save research results to cache."""
        self.db.add(WebResearchResult(
            id=str(uuid.uuid4()),
            shop_id=self.shop_id,
            research_type=research_type,
            query=query,
            results_json=results,
            source_urls=results.get("sources", []),
            ttl_hours=24,
        ))
        try:
            self.db.commit()
        except Exception:
            self.db.rollback()
