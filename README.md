# Composio App Intelligence Pipeline

An autonomous, multi-agent AI pipeline designed to research and analyze the developer ecosystem of 100 different applications. It investigates their API surfaces, authentication protocols, access levels (e.g. self-serve vs. partner gated), and integration readiness (Buildability) to determine if they are viable candidates for AI agent toolkits or MCP servers.

## 🎯 What Has Been Done

1. **Mass Documentation Research:** Successfully researched the developer documentation of exactly 100 diverse SaaS platforms and APIs.
2. **Pattern Recognition:** Identified overarching architectural trends across the software industry (e.g., OAuth vs. API Key dominance, prevalence of free-tier access, and common development blockers).
3. **Agentic Data Verification:** Developed an autonomous ReAct loop that independently re-verifies claims to eliminate LLM hallucinations, ensuring highly accurate data.
4. **Dashboard Generation:** Synthesized all findings, metrics, and raw data into a clean, zero-dependency, single-file HTML deliverable that runs completely locally.

## 🧠 How It Has Been Done

The system was built using Python and consists of a sequential pipeline of specialized AI agents:

1. **The Researcher Agent:**
   - **Search:** Uses the **Serper API** to simulate a developer searching Google for specific API documentation and developer portals.
   - **Scrape:** Uses the **Jina Reader API** to bypass JavaScript-heavy SPAs and extract clean, LLM-optimized Markdown directly from the source pages.
   - **Extract:** Utilizes the **Sarvam API (`sarvam-105b`)** coupled with the `instructor` Python library to forcefully extract data into strict Pydantic JSON schemas.

2. **The Analyzer Agent:**
   - Takes the final 100-app dataset and performs macro-analysis to generate an Executive Summary, categorize easy wins, identify common blockers, and compute distribution statistics.

3. **The Verifier Agent:**
   - An advanced ReAct (Reasoning and Acting) loop designed to solve the "context starvation" problem that plagues simple web scrapers.
   - Armed with `search_web` and `scrape_url` tools, the Verifier dynamically browses the web up to 5 times per app. If it lands on a marketing page, it thinks, adjusts its search query, and finds the deep API reference link before casting its final verdict on accuracy.

4. **The HTML Generator:**
   - Uses `Jinja2` to securely inject the processed JSON payloads into a beautifully styled HTML template, resulting in the final `output/index.html` dashboard.

## 🚀 How to Run the Agent

### 1. Prerequisites
Ensure you have Python installed and the fast `uv` package manager. If you don't have `uv` installed:
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 2. Environment Variables
Create a `.env` file in the root directory and add the necessary API keys for the LLM and search capabilities:
```env
SARVAM_API_KEY=your_sarvam_key_here
SERPER_API_KEY=your_serper_key_here
```
*(Note: The Sarvam API powers the entire reasoning engine for this pipeline).*

### 3. Run the Pipeline
The project is managed via `uv`, which handles all dependencies seamlessly. To run the full pipeline (Research -> Analyze -> Verify -> Generate HTML):

```bash
uv sync
uv run python main.py all
```

**Alternative Commands:**
- Test mode (only processes the first 5 apps to save time): `uv run python main.py all --test`
- Run specific modules only: `uv run python main.py research` or `uv run python main.py dashboard`

### 4. View the Deliverable
Once the pipeline completes, simply open the resulting file in your favorite web browser:
```bash
open output/index.html
```
