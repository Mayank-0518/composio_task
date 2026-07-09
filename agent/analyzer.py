"""Pattern analysis of research results."""

import json
import os
from collections import Counter
from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table

import instructor
from groq import Groq
from pydantic import BaseModel, Field

from agent.prompts import ANALYSIS_SYSTEM_PROMPT
from agent.models import AnalysisResult

load_dotenv()
console = Console()

class QualitativeAnalysis(BaseModel):
    top_patterns: list[str] = Field(description="Top 3-5 insights or patterns")
    easy_wins: list[str] = Field(description="List of 3-5 apps that are very easy to integrate")
    hard_nuts: list[str] = Field(description="List of 3-5 apps that are difficult/blocked")
    executive_summary: str = Field(description="One paragraph executive summary of findings")

def get_llm_client():
    api_key = os.getenv("SARVAM_API_KEY")
    if not api_key:
        return None
    from openai import OpenAI
    client = OpenAI(
        api_key=api_key,
        base_url="https://api.sarvam.ai/v1",
        max_retries=5
    )
    return instructor.from_openai(client, mode=instructor.Mode.JSON)

async def run_analysis(
    results_file: str = "data/results.json",
    output_file: str = "data/analysis.json"
):
    """Run quantitative and qualitative analysis on results."""
    console.print("\n[bold magenta]Starting Pattern Analysis[/bold magenta]\n")
    
    if not os.path.exists(results_file):
        console.print(f"[red]Results file {results_file} not found.[/red]")
        return
        
    with open(results_file, 'r') as f:
        results = json.load(f)
        
    if not results:
        console.print("[yellow]No results to analyze.[/yellow]")
        return
        
    # Quantitative Analysis
    auth_counter = Counter([r.get("primary_auth") for r in results])
    buildability_counter = Counter([r.get("buildability") for r in results])
    api_type_counter = Counter([r.get("api_type") for r in results])
    
    access_by_cat = {}
    for r in results:
        cat = r.get("category", "Unknown")
        access = r.get("access_level", "")
        if cat not in access_by_cat:
            access_by_cat[cat] = {"self_serve": 0, "gated": 0}
        if "Self-serve" in access:
            access_by_cat[cat]["self_serve"] += 1
        else:
            access_by_cat[cat]["gated"] += 1
            
    mcp_count = sum(1 for r in results if r.get("existing_mcp"))
    composio_count = sum(1 for r in results if r.get("existing_composio_integration"))
    
    # Qualitative Analysis (via LLM)
    client = get_llm_client()
    qualitative = QualitativeAnalysis(
        top_patterns=["No LLM key available for qualitative analysis"],
        easy_wins=[],
        hard_nuts=[],
        executive_summary="Analysis completed quantitatively."
    )
    
    if client:
        console.print("[dim]Generating qualitative insights with LLM...[/dim]")
        # Send a summary of the data to LLM to save tokens
        summary_data = json.dumps([{
            "app": r.get("app_name"),
            "category": r.get("category"),
            "auth": r.get("primary_auth"),
            "buildability": r.get("buildability"),
            "access": r.get("access_level")
        } for r in results])
        
        try:
            qualitative = client.chat.completions.create(
                model="sarvam-105b",
                response_model=QualitativeAnalysis,
                messages=[
                    {"role": "system", "content": ANALYSIS_SYSTEM_PROMPT},
                    {"role": "user", "content": summary_data}
                ]
            )
        except Exception as e:
            console.print(f"[red]Failed to generate qualitative analysis: {e}[/red]")
            
    # Combine results
    analysis = AnalysisResult(
        auth_distribution=dict(auth_counter),
        access_by_category=access_by_cat,
        buildability_breakdown=dict(buildability_counter),
        top_patterns=qualitative.top_patterns,
        easy_wins=qualitative.easy_wins,
        hard_nuts=qualitative.hard_nuts,
        executive_summary=qualitative.executive_summary
    )
    
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    with open(output_file, 'w') as f:
        json.dump(analysis.model_dump(), f, indent=2)
        
    # Print Summary Tables
    b_table = Table(title="Buildability Breakdown")
    b_table.add_column("Status", style="cyan")
    b_table.add_column("Count", style="green")
    for status, count in buildability_counter.most_common():
        b_table.add_row(str(status), str(count))
    console.print(b_table)
    
    console.print(f"\n[bold]Executive Summary:[/bold] {analysis.executive_summary}")
    console.print(f"[green]Analysis saved to {output_file}[/green]")
    
    return analysis

def main():
    import asyncio
    asyncio.run(run_analysis())

if __name__ == "__main__":
    main()
