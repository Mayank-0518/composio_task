"""Tools for web search and page scraping."""

import httpx
import asyncio
import json
import os
from typing import Optional
from tenacity import retry, stop_after_attempt, wait_random_exponential, retry_if_exception_type
from rich.console import Console

console = Console()

# ============= SERPER SEARCH (PRIMARY) =============

async def search_serper(query: str, num_results: int = 5) -> list[dict]:
    """Search Google via Serper API. Returns list of {title, link, snippet}."""
    api_key = os.getenv("SERPER_API_KEY")
    if not api_key:
        raise ValueError("SERPER_API_KEY not set")
    
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            "https://google.serper.dev/search",
            json={"q": query, "num": num_results},
            headers={"X-API-KEY": api_key, "Content-Type": "application/json"}
        )
        resp.raise_for_status()
        data = resp.json()
        
        results = []
        for item in data.get("organic", [])[:num_results]:
            results.append({
                "title": item.get("title", ""),
                "link": item.get("link", ""),
                "snippet": item.get("snippet", "")
            })
        return results


# ============= TAVILY SEARCH (FALLBACK) =============

async def search_tavily(query: str, num_results: int = 5) -> list[dict]:
    """Search via Tavily API (fallback). Returns list of {title, link, snippet}."""
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        return []  # Silently skip if no key
    
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            "https://api.tavily.com/search",
            json={"api_key": api_key, "query": query, "max_results": num_results, "include_raw_content": False},
        )
        resp.raise_for_status()
        data = resp.json()
        
        results = []
        for item in data.get("results", [])[:num_results]:
            results.append({
                "title": item.get("title", ""),
                "link": item.get("url", ""),
                "snippet": item.get("content", "")
            })
        return results


# ============= JINA READER (PAGE SCRAPING) =============

@retry(stop=stop_after_attempt(2), wait=wait_random_exponential(min=1, max=5))
async def scrape_jina(url: str) -> str:
    """Scrape a URL to clean markdown via Jina Reader API."""
    jina_url = f"https://r.jina.ai/{url}"
    headers = {"Accept": "text/markdown"}
    
    api_key = os.getenv("JINA_API_KEY")
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        resp = await client.get(jina_url, headers=headers)
        resp.raise_for_status()
        text = resp.text
        # Truncate to ~12000 chars (~3000 tokens) to stay within LLM budget
        return text[:12000]


# ============= HTTPX FALLBACK SCRAPING =============

async def scrape_httpx(url: str) -> str:
    """Direct HTTP fetch as fallback. Returns raw text, truncated."""
    async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
        resp = await client.get(url, headers={"User-Agent": "Mozilla/5.0 (research bot)"})
        resp.raise_for_status()
        return resp.text[:12000]


# ============= COMBINED SEARCH FUNCTION =============

async def search_app_docs(app_name: str, website_hint: str = "") -> list[dict]:
    """Search for an app's API documentation. Returns list of search results.
    
    Runs up to 3 search queries:
    1. "{app} API documentation developer"
    2. "{app} API authentication OAuth2 API key"
    3. "{app} MCP server" (for existing MCP check)
    """
    queries = [
        f"{app_name} API documentation developer",
        f"{app_name} API authentication OAuth2 API key",
    ]
    
    all_results = []
    seen_urls = set()
    
    for query in queries:
        try:
            results = await search_serper(query, num_results=3)
        except Exception as e:
            console.print(f"  [yellow]Serper failed for '{query}': {e}. Trying Tavily...[/yellow]")
            try:
                results = await search_tavily(query, num_results=3)
            except Exception as e2:
                console.print(f"  [red]Tavily also failed: {e2}[/red]")
                results = []
        
        for r in results:
            if r["link"] not in seen_urls:
                seen_urls.add(r["link"])
                all_results.append(r)
    
    # If no results found, try the website hint
    if not all_results and website_hint:
        all_results.append({"title": f"{app_name} website", "link": f"https://{website_hint}", "snippet": ""})
    
    return all_results


# ============= COMBINED SCRAPE FUNCTION =============

async def scrape_pages(urls: list[str], max_pages: int = 3) -> str:
    """Scrape multiple pages and combine their content.
    
    Uses Jina Reader as primary, httpx as fallback.
    Returns combined markdown text, truncated to ~30000 chars.
    """
    combined = []
    
    for url in urls[:max_pages]:
        try:
            content = await scrape_jina(url)
            combined.append(f"\n\n--- SOURCE: {url} ---\n\n{content}")
        except Exception as e:
            console.print(f"  [yellow]Jina failed for {url}: {e}. Trying httpx...[/yellow]")
            try:
                content = await scrape_httpx(url)
                combined.append(f"\n\n--- SOURCE: {url} ---\n\n{content}")
            except Exception as e2:
                console.print(f"  [red]httpx also failed for {url}: {e2}[/red]")
        
        # Small delay to avoid rate limiting
        await asyncio.sleep(0.5)
    
    full_text = "\n".join(combined)
    return full_text[:30000]  # Truncate total to ~7500 tokens


async def check_mcp_exists(app_name: str) -> tuple[bool, Optional[str]]:
    """Check if an MCP server exists for the app via search."""
    try:
        results = await search_serper(f"{app_name} MCP server", num_results=3)
        for r in results:
            if "mcp" in r.get("title", "").lower() or "mcp" in r.get("snippet", "").lower():
                return True, r.get("link", "")
    except Exception:
        pass
    return False, None


async def check_composio_integration(app_name: str) -> bool:
    """Check if Composio already has a toolkit for this app via search."""
    try:
        results = await search_serper(f"site:composio.dev {app_name}", num_results=3)
        for r in results:
            if "composio" in r.get("link", "").lower():
                return True
    except Exception:
        pass
    return False
