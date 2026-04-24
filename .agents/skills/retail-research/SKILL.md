---
name: retail-research
description: Use when gathering lightweight retail competitor data, normalizing place results, and producing a raw handoff bundle for another intelligence agent
---

# Retail Research

Run location-based retail research and write a structured handoff bundle. By default, use the Signal Scout orchestrator to gather insights across all APIs (Google Places, YouTube, and Google Trends).

## Security Rules

- Never read `.env`, `.env.*`, or any secret file directly.
- Access credentials only through `scripts/config.py` or existing environment variables.
- Do not echo API keys into logs, prompts, or checked-in files.

## Primary Workflow

Do not run retrieval immediately.

First collect the required context, then restate the planned query, and wait for explicit user confirmation before running any script.

### Intake Sequence

Ask for these inputs before retrieval:

1. Preferred input format
- Google Maps URL
- latitude/longitude
- local CSV or JSON file

2. Target keywords or topics
- What brands, topics, or product types should we track on Google Trends and YouTube? (e.g., "Aēsop", "luxury skincare")

3. Target retail category or categories
- Require explicit Google Places category choices for live mode.
- Do not guess broad categories like `store`.

4. Search scope and results cap
- radius in km
- max results to fetch per category (Note: Google Places API has a hard cap of 60 results/3 pages)
- price tier if relevant
- surrounding information that matters for interpretation, such as:
  - nearby landmarks
  - trade area or neighborhood expectations
  - competitor types to include or exclude
  - whether the user wants broad coverage or a narrow competitive set

5. Optional session name

### Confirmation Gate

Before running retrieval, summarize the planned run in plain language:

- mode: live or offline
- input format and location/file
- keywords for trend analysis
- categories
- radius
- max results (inform if it approaches the 60 cap)
- price tier if any
- any surrounding context or exclusions
- proposed session name

Then stop and wait for a clear confirmation such as `run`, `confirm`, or equivalent.

Do not call any retrieval scripts until the user confirms.

Use the Signal Scout orchestrated script by default to gather all API signals (Google Places, YouTube, Google Trends):

```bash
python scripts/signal_scout.py --input "<coordinates or Google Maps URL>" --keyword "<topic>" [--keyword "<topic>"] --category "<google_places_type>" [--category "<google_places_type>"] --radius <km> [--max-results <int>] --session-name "<name>"
```

If the user specifically only wants local Google Places data (no social or trend signals), use the basic retail research script:

```bash
python scripts/retail_research.py --input "<coordinates or Google Maps URL>" --radius <km> --category "<google_places_type>" [--category "<google_places_type>"] [--max-results <int>] [--price-tier "<tier>"] [--session-name "<name>"]
```

Examples:

```bash
python scripts/signal_scout.py --input "https://maps.app.goo.gl/..." --keyword "matcha" --category "cafe" --radius 3.0 --max-results 40 --session-name matcha-trends-silom

python scripts/retail_research.py --input "40.7412,-73.9896" --radius 1.5 --category clothing_store --category shoe_store --max-results 40 --session-name flatiron-apparel
```

```bash
python scripts/retail_research.py --input-file data/sample_places.json --source json --session-name sample-offline
```

## Inputs

Live mode (Signal Scout):

- location input or explicit coordinates
- one or more keywords for trend and social analysis
- one or more Google Places `includedType` values
- radius in km
- surrounding context or scope notes from the user
- optional session name

Offline mode:

- input file path
- optional source type
- optional surrounding context about the dataset
- optional session name

## Output Bundle

Signal Scout writes to `output/raw/{session_name}/`:

- `signal_dump.json` (Combined results from Places, YouTube, Trends)
- `manifest.json`

Basic Retail Research writes to `output/raw/{session_name}/`:

- `raw_search.json`
- `normalized_places.json`
- `market_summary.json`
- `research_brief.md`
- `manifest.json`

## Use the Underlying Scripts Only When Needed

- `scripts/coordinate_parser.py` for location parsing checks
- `scripts/places_search.py` for a single live category query
- `scripts/places_normalize.py` for standalone normalization
- `scripts/places_details.py` for optional follow-up detail fetches

Default to `scripts/signal_scout.py` unless you need a narrower step.