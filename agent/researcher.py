#!/usr/bin/env python3
"""Main research pipeline for analyzing 100 apps."""

import asyncio
import json
import os
import sys
import time
from pathlib import Path
from typing import Optional

import instructor
from groq import Groq
from dotenv import load_dotenv
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.table import Table
from tenacity import retry, stop_after_attempt, wait_random_exponential, retry_if_exception_type

from agent.models import AppInput, AppResearchResult, parse_apps_md
from agent.tools import search_app_docs, scrape_pages, check_mcp_exists
from agent.prompts import RESEARCH_SYSTEM_PROMPT

load_dotenv()
console = Console()

# ============= LLM CLIENT SETUP =============

def get_llm_client():
    """Create an instructor-patched client for structured extraction using Sarvam API."""
    api_key = os.getenv("SARVAM_API_KEY")
    if not api_key:
        console.print("[red]Error: SARVAM_API_KEY not set.[/red]")
        sys.exit(1)
    
    from openai import OpenAI
    client = OpenAI(
        api_key=api_key,
        base_url="https://api.sarvam.ai/v1",
        max_retries=5
    )
    return instructor.from_openai(client, mode=instructor.Mode.JSON)


# ============= SINGLE APP RESEARCH =============

async def research_single_app(
    app: AppInput,
    client,
) -> tuple[Optional[AppResearchResult], Optional[str]]:
    """Research a single app. Returns (result, error_message)."""
    try:
        # Step 1: Search for API docs
        console.print(f"  [dim]Searching for {app.app_name} docs...[/dim]")
        search_results = await search_app_docs(app.app_name, app.website_hint)
        
        if not search_results:
            return None, f"No search results found for {app.app_name}"
        
        # Step 2: Scrape top documentation pages
        urls = [r["link"] for r in search_results[:3]]
        console.print(f"  [dim]Scraping {len(urls)} pages...[/dim]")
        docs_text = await scrape_pages(urls)
        
        if not docs_text or len(docs_text.strip()) < 100:
            return None, f"Could not scrape meaningful content for {app.app_name}"
        
        # Step 3: Check for existing MCP server
        mcp_exists, mcp_url = await check_mcp_exists(app.app_name)
        
        # Step 4: Extract structured data via LLM
        console.print(f"  [dim]Extracting data via LLM...[/dim]")
        
        # Add context about MCP status
        extra_context = ""
        if mcp_exists:
            extra_context += f"\nNote: An MCP server appears to exist for this app (found at: {mcp_url})"
        
        user_message = f"""Research the app: {app.app_name}
Category: {app.category}
Website hint: {app.website_hint}
{extra_context}

Here is the developer documentation content scraped from their website:

{docs_text}

Extract the structured research data. Evidence URLs should be the actual documentation pages listed above."""
        
        # Call LLM with instructor for structured output
        result = client.chat.completions.create(
            model="sarvam-105b",
            response_model=AppResearchResult,
            max_retries=3,
            messages=[
                {"role": "system", "content": RESEARCH_SYSTEM_PROMPT},
                {"role": "user", "content": user_message}
            ],
        )
        
        # Override MCP fields with our direct checks
        if mcp_exists and not result.existing_mcp:
            result.existing_mcp = True
            result.mcp_detail = f"Found via search: {mcp_url}"
        
        # Ensure evidence URLs are populated
        if not result.evidence_urls:
            result.evidence_urls = urls
        
        return result, None
    
    except Exception as e:
        return None, f"Error researching {app.app_name}: {str(e)}"


# ============= CHECKPOINT MANAGEMENT =============

def load_checkpoint(filepath: str) -> dict[str, dict]:
    """Load existing results from checkpoint file."""
    if os.path.exists(filepath):
        with open(filepath, 'r') as f:
            data = json.load(f)
        return {item["app_name"]: item for item in data}
    return {}


def save_checkpoint(results: list[dict], filepath: str):
    """Save results to checkpoint file."""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, 'w') as f:
        json.dump(results, f, indent=2, default=str)


# ============= MAIN PIPELINE =============

async def run_pipeline(
    apps_file: str = "apps.md",
    output_file: str = "data/results.json",
    failures_file: str = "data/failures.json",
    batch_size: Optional[int] = None,
    test_mode: bool = False,
):
    """Run the full research pipeline."""
    
    # Parse apps
    apps = parse_apps_md(apps_file)
    if test_mode:
        apps = apps[:5]  # Only process 5 apps in test mode
        console.print("[yellow]TEST MODE: Processing only 5 apps[/yellow]")
    elif batch_size:
        apps = apps[:batch_size]
        console.print(f"[yellow]Batch mode: Processing {batch_size} apps[/yellow]")
    
    console.print(f"\n[bold green]Starting research pipeline for {len(apps)} apps[/bold green]\n")
    
    # Load checkpoint
    existing = load_checkpoint(output_file)
    console.print(f"[dim]Checkpoint: {len(existing)} apps already processed[/dim]")
    
    # Initialize LLM client
    client = get_llm_client()
    
    # Process each app
    results = list(existing.values())
    failures = []
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Researching apps...", total=len(apps))
        
        for i, app in enumerate(apps):
            # Skip already processed
            if app.app_name in existing:
                progress.update(task, advance=1, description=f"[dim]Skipping {app.app_name} (cached)[/dim]")
                continue
            
            progress.update(task, description=f"[cyan]({i+1}/{len(apps)}) {app.app_name}[/cyan]")
            
            result, error = await research_single_app(app, client)
            
            if result:
                result_dict = result.model_dump()
                results.append(result_dict)
                existing[app.app_name] = result_dict
                console.print(f"  [green]✓ {app.app_name} — {result.buildability.value}[/green]")
            else:
                failures.append({"app_name": app.app_name, "error": error})
                console.print(f"  [red]✗ {app.app_name} — {error}[/red]")
            
            # Save checkpoint after each app
            save_checkpoint(results, output_file)
            # Rate limiting: wait between apps (Gemini free tier = 15 RPM)
            if i < len(apps) - 1:
                await asyncio.sleep(5.0)
            
            progress.update(task, advance=1)
    
    # Save failures
    if failures:
        save_checkpoint(failures, failures_file)
    
    # Print summary
    console.print(f"\n[bold]Pipeline Complete![/bold]")
    
    table = Table(title="Research Summary")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")
    table.add_row("Total Apps", str(len(apps)))
    table.add_row("Successful", str(len(results)))
    table.add_row("Failed", str(len(failures)))
    table.add_row("Results File", output_file)
    console.print(table)
    
    return results


def main():
    """Entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Research 100 apps for Composio")
    parser.add_argument("--test", action="store_true", help="Test mode: process only 5 apps")
    parser.add_argument("--batch-size", type=int, help="Process only N apps")
    parser.add_argument("--apps-file", default="apps.md", help="Path to apps.md")
    parser.add_argument("--output", default="data/results.json", help="Output file")
    args = parser.parse_args()
    
    asyncio.run(run_pipeline(
        apps_file=args.apps_file,
        output_file=args.output,
        batch_size=args.batch_size,
        test_mode=args.test,
    ))


if __name__ == "__main__":
    main()
