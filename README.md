# Gemini Retail Researcher

A lightweight, script-first toolkit for retail research and market intelligence, optimized for Gemini CLI. This repository provides a streamlined pipeline for aggregating local business data, social proof, and search trends into standardized, actionable handoff bundles.

## Purpose

The toolkit is designed for rapid competitive analysis and market depth scanning. It avoids complex infrastructure in favor of a clean, file-based workflow that produces portable JSON and Markdown artifacts for downstream analysis.

## Core Capabilities

- **Signal Scout**: A unified orchestration pipeline that aggregates Google Places data, YouTube social proof (video mentions), and Google Trends interest into a single "signal dump."
- **Retail Research**: Focused location-based scanning for direct competitor identification and market summary reporting.
- **AI-Native Integration**: Includes a pre-configured Gemini CLI `retail-research` skill to guide the intake and confirmation process.

## Example Use Case

**Scenario**: You are researching the Shabu-Shabu market in the Thonglor neighborhood of Bangkok.

**Prompt**:
> "Use retail-research on https://maps.app.goo.gl/eWwusREk47A1Mg9M8 for Shabu restaurants within 2km. Use keywords 'Shabu Thonglor' and 'ชาบู ทองหล่อ'."

**Command Line Execution**:
```bash
# 1. Standard Retail Research
python scripts/retail_research.py --input "https://maps.app.goo.gl/..." --radius 2 --category "japanese_restaurant" --max-results 60 --session-name "shabu-thonglor-scan"

# 2. Advanced Signal Scout (Trends + YouTube)
python scripts/signal_scout.py --input "https://maps.app.goo.gl/..." --keyword "Shabu Thonglor" --keyword "ชาบู ทองหล่อ" --category "japanese_restaurant" --radius 2 --max-results 60 --session-name "shabu-thonglor-scan"
```

## Outputs

Each session generates a comprehensive handoff bundle in `output/raw/{session_name}/`:

- **`research_brief.md`**: The executive summary. A human-readable Markdown report summarizing market density, top competitors, quality benchmarks (average ratings), and recommended next steps.
- **`signal_dump.json`**: The multi-channel intelligence report (Signal Scout only). A unified JSON combining Google Places records with YouTube social proof (video themes, engagement) and Google Trends growth directions.
- **`normalized_places.json`**: Standardized data. A clean, flattened JSON format for all identified competitors, optimized for spreadsheet imports or downstream data processing.
- **`market_summary.json`**: Aggregated market metrics. Contains calculated statistics including average ratings, median review counts, category distributions, and price tier patterns.
- **`raw_search.json`**: The "source of truth." The raw, unmodified response payload from the Google Places API, including all available technical fields and metadata.
- **`manifest.json`**: The session inventory. Metadata regarding the research run, including query parameters, timestamps, and a checklist of all generated files.

## API Usage & Costs

This toolkit uses standard Google Cloud APIs. Approximate costs per run include:

- **Google Places API (New)**: ~$0.04 per search request (Atmosphere tier). A single search with pagination (60 results) costs approximately **$0.12**.
- **YouTube Data API**: Uses the standard quota (10,000 units/day). A search + details fetch costs ~102 units per keyword.
- **Google Trends**: Free of charge (but subject to rate limiting).

**Note**: Always monitor your usage in the [Google Cloud Console](https://console.cloud.google.com/) and set billing alerts to avoid unexpected charges.

## Data Handoff & Visualization

To hand off these results to another AI (e.g., Gemini, ChatGPT) for visualization or strategic discussion, use the following "Power Combo" of files:

- **`research_brief.md`**: Provides the executive context and high-level benchmarks.
- **`market_summary.json`**: Best for generating charts (category distribution, rating histograms).
- **`normalized_places.json`**: Required for mapping (contains lat/lng coordinates) and comparison tables.
- **`signal_dump.json`** (Optional): Include this if you want the agent to analyze YouTube "buzz" and search trends.

**Example Prompt for Visualization Agent:**
> "I've attached the research data for [Location]. Please plot these competitors on a map, identify the 'Power Players' (high rating + high review count), and summarize the market gap based on the research brief."

## Installation

```bash
# Set up environment
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
pip install -r requirements.txt

# Configure API Keys
# Create a secrets.env file with GOOGLE_PLACES_API_KEY (and optionally YOUTUBE_API_KEY)
```

## Security & Configuration

- **Credentials**: Managed via `scripts/config.py`.
- **API Key Fallback**: `YOUTUBE_API_KEY` is optional. If not provided in `secrets.env`, the system defaults to using the `GOOGLE_PLACES_API_KEY` for YouTube requests.
- **Privacy**: API keys are never logged, printed, or committed to the repository.
- **Gemini CLI**: `.geminiignore` blocks the CLI from reading `secrets.env` or `.env.*` to maintain security and prevent your API keys from being processed or logged by the AI.
- **Best Practice**: Always use a `secrets.env.example` template for documentation, and ensure `secrets.env` is explicitly listed in both `.gitignore` and `.geminiignore`. For production environments, consider using a secret manager (like Doppler or Infisical) for runtime injection.
