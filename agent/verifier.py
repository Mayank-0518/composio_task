"""Verification pipeline using an iterative ReAct Agent Loop."""

import asyncio
import json
import os
import random
from typing import Optional, Literal
from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table
import httpx
from pydantic import BaseModel, Field

import instructor
from groq import Groq

from agent.models import VerificationResult
from agent.tools import scrape_jina, search_serper

load_dotenv()
console = Console()

class VerificationResponse(BaseModel):
    is_correct: bool = Field(description="Is the claim correct based on the documentation?")
    actual_value: str = Field(description="The actual value found in the documentation")
    explanation: str = Field(description="Brief explanation of findings")

class AgentStep(BaseModel):
    thought: str = Field(description="What you are thinking about doing next")
    action: Literal["SEARCH", "SCRAPE", "FINISH"] = Field(description="The action to take (must be SEARCH, SCRAPE, or FINISH)")
    action_input: str = Field(description="The input for the action (search query, URL, or final JSON string)")

def get_llm_client():
    """Create an instructor-patched Sarvam client."""
    api_key = os.getenv("SARVAM_API_KEY")
    if not api_key:
        console.print("[red]SARVAM_API_KEY not set.[/red]")
        return None
    from openai import OpenAI
    client = OpenAI(
        api_key=api_key,
        base_url="https://api.sarvam.ai/v1",
        max_retries=5
    )
    return instructor.from_openai(client, mode=instructor.Mode.JSON)

VERIFICATION_SYSTEM_PROMPT = """You are an elite autonomous Verification Agent.
Your job is to verify a specific claim about a software application's API.
You must use a ReAct loop to interact with the web.

You will output a JSON object at each step with exactly these fields:
- "thought": Describe your reasoning.
- "action": Must be exactly one of "SEARCH", "SCRAPE", or "FINISH".
- "action_input": The argument for the action.

Actions:
1. SEARCH: Search the web. action_input should be a highly targeted search query (e.g. "Stripe API authentication method developer docs").
2. SCRAPE: Read the contents of a specific URL. action_input should be the exact URL you want to read.
3. FINISH: You have found the answer or exhausted your options. action_input must be a valid JSON string containing exactly:
   {"is_correct": bool, "actual_value": "string", "explanation": "string"}

Rules:
- NEVER guess. If you are unsure, SEARCH or SCRAPE.
- Read search snippets carefully to pick the best developer docs URL.
- If you FINISH, ensure your action_input is perfectly valid JSON parsable into VerificationResponse.
"""

async def verify_claim_agentic(client, app_name: str, field_name: str, claim: str) -> tuple[Optional[VerificationResponse], list[str]]:
    """Verify a claim using an iterative ReAct loop."""
    
    messages = [
        {"role": "system", "content": VERIFICATION_SYSTEM_PROMPT},
        {"role": "user", "content": f"Verify this claim.\nApp: {app_name}\nField: {field_name}\nClaimed Value: {claim}\n\nStart your investigation!"}
    ]
    
    trajectory = []
    
    for step in range(5): # Max 5 steps to prevent infinite loops
        try:
            result = client.chat.completions.create(
                model="sarvam-105b",
                response_model=AgentStep,
                max_retries=3,
                messages=messages,
            )
            
            action = result.action
            action_input = result.action_input
            thought = result.thought
            
            console.print(f"  [dim]Step {step+1}: {action} -> {action_input[:50]}...[/dim]")
            trajectory.append(f"{action}: {action_input}")
            
            messages.append({"role": "assistant", "content": result.model_dump_json()})
            
            if action == "FINISH":
                # Parse the final JSON
                try:
                    # Fix escaped quotes if LLM messed up stringifying the JSON
                    if action_input.startswith("'") and action_input.endswith("'"):
                        action_input = action_input[1:-1]
                    final_data = json.loads(action_input)
                    return VerificationResponse(**final_data), trajectory
                except Exception as e:
                    console.print(f"  [red]Failed to parse FINISH JSON: {e}[/red]")
                    return None, trajectory
                    
            elif action == "SEARCH":
                try:
                    search_results = await search_serper(action_input, num_results=3)
                    observation = "Search Results:\\n"
                    for r in search_results:
                        observation += f"- Title: {r.get('title')}\\n  URL: {r.get('link')}\\n  Snippet: {r.get('snippet')}\\n"
                    messages.append({"role": "user", "content": observation})
                except Exception as e:
                    messages.append({"role": "user", "content": f"Search failed: {e}"})
                    
            elif action == "SCRAPE":
                try:
                    content = await scrape_jina(action_input)
                    if len(content) > 15000:
                        content = content[:15000] + "... (truncated)"
                    messages.append({"role": "user", "content": f"Page Content for {action_input}:\\n\\n{content}"})
                except Exception as e:
                    messages.append({"role": "user", "content": f"Scrape failed for {action_input}: {e}"})
            
            else:
                messages.append({"role": "user", "content": f"Invalid action: {action}"})
                
            await asyncio.sleep(1)
            
        except Exception as e:
            console.print(f"  [yellow]Agent loop error: {e}[/yellow]")
            break
            
    return None, trajectory

async def run_verification(
    results_file: str = "data/results.json",
    output_file: str = "data/verification_report.json",
    sample_size: int = 20
):
    """Run verification on a sample of research results."""
    console.print("\\n[bold cyan]Starting Agentic Verification Pipeline[/bold cyan]\\n")
    
    if not os.path.exists(results_file):
        console.print(f"[red]Results file {results_file} not found. Run research first.[/red]")
        return
        
    with open(results_file, 'r') as f:
        results = json.load(f)
        
    if not results:
        console.print("[yellow]No results to verify.[/yellow]")
        return

    client = get_llm_client()
    if not client:
        return
        
    # Group by category for stratified sampling
    by_category = {}
    for r in results:
        cat = r.get("category", "Unknown")
        if cat not in by_category:
            by_category[cat] = []
        by_category[cat].append(r)
        
    # Sample 2 per category or up to sample_size
    sample = []
    for cat, apps in by_category.items():
        sample.extend(random.sample(apps, min(2, len(apps))))
        
    if len(sample) > sample_size:
        sample = random.sample(sample, sample_size)
    elif len(sample) < sample_size and len(results) > len(sample):
        # fill remaining with random
        remaining = [r for r in results if r not in sample]
        sample.extend(random.sample(remaining, min(sample_size - len(sample), len(remaining))))

    console.print(f"[dim]Selected {len(sample)} apps for deep verification[/dim]")
    
    verification_results = []
    field_stats = {"primary_auth": {"correct": 0, "total": 0}, "buildability": {"correct": 0, "total": 0}}
    
    for i, app in enumerate(sample):
        console.print(f"[{i+1}/{len(sample)}] Verifying {app['app_name']}...")
        
        # 1. Agentic verification of primary_auth
        auth_claim = app.get('primary_auth')
        if auth_claim:
            v_res, trajectory = await verify_claim_agentic(client, app['app_name'], "primary_auth", auth_claim)
            if v_res:
                field_stats["primary_auth"]["total"] += 1
                if v_res.is_correct:
                    field_stats["primary_auth"]["correct"] += 1
                
                verification_results.append(VerificationResult(
                    app_name=app['app_name'],
                    field_name="primary_auth",
                    agent_value=auth_claim,
                    actual_value=v_res.actual_value,
                    is_correct=v_res.is_correct,
                    evidence_url="See Trajectory",
                    notes=v_res.explanation,
                    agent_trajectory=trajectory
                ).model_dump())
        
        # 2. Agentic verification of buildability
        build_claim = app.get('buildability')
        if build_claim:
            v_res, trajectory = await verify_claim_agentic(client, app['app_name'], "buildability", build_claim)
            if v_res:
                field_stats["buildability"]["total"] += 1
                if v_res.is_correct:
                    field_stats["buildability"]["correct"] += 1
                
                verification_results.append(VerificationResult(
                    app_name=app['app_name'],
                    field_name="buildability",
                    agent_value=build_claim,
                    actual_value=v_res.actual_value,
                    is_correct=v_res.is_correct,
                    evidence_url="See Trajectory",
                    notes=v_res.explanation,
                    agent_trajectory=trajectory
                ).model_dump())
                
        await asyncio.sleep(2) 
        
    # Calculate accuracy
    auth_acc = (field_stats["primary_auth"]["correct"] / max(1, field_stats["primary_auth"]["total"])) * 100
    build_acc = (field_stats["buildability"]["correct"] / max(1, field_stats["buildability"]["total"])) * 100
    
    report = {
        "first_pass_accuracy": {
            "primary_auth": f"{auth_acc:.1f}%",
            "buildability": f"{build_acc:.1f}%"
        },
        "sample_details": verification_results,
        "common_errors": ["To be populated by analyzer if needed"],
        "unreachable_urls": 0
    }
    
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    with open(output_file, 'w') as f:
        json.dump(report, f, indent=2)
        
    # Print table
    table = Table(title="Agentic Verification Accuracy")
    table.add_column("Field", style="cyan")
    table.add_column("Accuracy", style="green")
    table.add_row("Primary Auth", f"{auth_acc:.1f}%")
    table.add_row("Buildability", f"{build_acc:.1f}%")
    console.print(table)
    console.print(f"[green]Agentic Verification report saved to {output_file}[/green]")
    
    return report

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample-size", type=int, default=20)
    args = parser.parse_args()
    asyncio.run(run_verification(sample_size=args.sample_size))

if __name__ == "__main__":
    main()
