#!/usr/bin/env python3
"""Main entry point for the Composio app research pipeline."""

import asyncio
import argparse
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel

load_dotenv()
console = Console()

def main():
    parser = argparse.ArgumentParser(description="Composio App Research Pipeline")
    parser.add_argument("stage", choices=["research", "verify", "analyze", "generate", "all"],
                        help="Pipeline stage to run")
    parser.add_argument("--test", action="store_true", help="Test mode (5 apps only)")
    parser.add_argument("--batch-size", type=int, help="Process N apps")
    args = parser.parse_args()
    
    console.print(Panel.fit(
        "[bold cyan]Composio App Research Pipeline[/bold cyan]\n"
        "Researching 100 apps for API surface, auth, and buildability",
        border_style="cyan"
    ))
    
    if args.stage in ("research", "all"):
        from agent.researcher import run_pipeline
        asyncio.run(run_pipeline(test_mode=args.test, batch_size=args.batch_size))
    
    if args.stage in ("verify", "all"):
        from agent.verifier import run_verification
        asyncio.run(run_verification())
    
    if args.stage in ("analyze", "all"):
        from agent.analyzer import run_analysis
        asyncio.run(run_analysis())
    
    if args.stage in ("generate", "all"):
        from agent.html_generator import generate_html
        generate_html()
    
    console.print("\n[bold green]Done![/bold green]")

if __name__ == "__main__":
    main()
