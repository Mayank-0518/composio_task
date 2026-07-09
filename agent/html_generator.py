"""HTML generator for final deliverable."""

import json
import os
from datetime import datetime
from jinja2 import Environment, FileSystemLoader
from rich.console import Console

console = Console()

def generate_html(
    results_file: str = "data/results.json",
    analysis_file: str = "data/analysis.json",
    verification_file: str = "data/verification_report.json",
    template_dir: str = "agent/templates",
    output_file: str = "output/index.html"
):
    """Generate the HTML dashboard from JSON data."""
    console.print("\n[bold yellow]Generating HTML Deliverable...[/bold yellow]")
    
    # Load data
    try:
        with open(results_file, 'r') as f:
            results_data = f.read()
    except FileNotFoundError:
        results_data = "[]"
        console.print("[red]results.json not found, using empty data[/red]")
        
    try:
        with open(analysis_file, 'r') as f:
            analysis_data = f.read()
    except FileNotFoundError:
        analysis_data = "{}"
        
    try:
        with open(verification_file, 'r') as f:
            verification_data = f.read()
    except FileNotFoundError:
        verification_data = "{}"
        
    # Setup Jinja environment
    env = Environment(loader=FileSystemLoader(template_dir))
    
    try:
        template = env.get_template('index.html')
    except Exception as e:
        console.print(f"[red]Error loading template: {e}[/red]")
        return
        
    # Render template with embedded JSON strings
    html_content = template.render(
        results_json=results_data,
        analysis_json=analysis_data,
        verification_json=verification_data,
        timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")
    )
    
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(html_content)
        
    console.print(f"[bold green]HTML generated successfully at {output_file}![/bold green]")

def main():
    generate_html()

if __name__ == "__main__":
    main()
