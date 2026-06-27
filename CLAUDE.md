# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Strava sports dashboard that generates a static HTML page optimized for e-ink displays (Kindle Paperwhite, 758×1024, 16-gray). Fetches Strava activity data, computes dashboard metrics, generates a weekly training plan (AI or rule-based fallback), and renders a Jinja2 template. Deployed to GitHub Pages via daily GitHub Actions workflow.

## Pipeline

The four scripts run in sequence (orchestrated by GitHub Action or manually):

```
src/fetch_strava.py → src/process_data.py → src/generate_training.py → src/render_html.py
```

1. **fetch_strava.py** — OAuth auth, paginated activity fetch, zones/profile fetch → `data/activities_2026.json`, `data/zones.json`, `data/profile.json`
2. **process_data.py** — Computes annual/weekly summaries, goals, monthly trends, key metrics, races, streaks → `data/processed.json`
3. **generate_training.py** — AI plan via Anthropic API (Haiku, Chinese prompts, supports Qianfan proxy) with rule-based fallback → `data/training_plan.json`
4. **render_html.py** — Jinja2 template with custom filters (`km`, `hours`, `mmss`, `pace`, `pct`) → `output/index.html`

**Auxiliary**: `src/convert_mcp_data.py` — converts Strava MCP tool output to internal format for local dev without API tokens.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run full pipeline locally (requires .env.secrets with Strava + Anthropic credentials)
python src/fetch_strava.py
python src/process_data.py
python src/generate_training.py
python src/render_html.py

# Local dev without Strava API (use MCP tools to fetch data, then convert)
python src/convert_mcp_data.py
python src/process_data.py
python src/generate_training.py   # works without ANTHROPIC_API_KEY (rule-based fallback)
python src/render_html.py

# Push secrets to GitHub Actions (requires GITHUB_TOKEN + pynacl)
bash push_secrets.sh
```

No test suite, linter, or formatter is configured.

## Architecture Notes

- **Data format**: All intermediate data is JSON; config is YAML (`config.yaml`); output is HTML
- **Reference year**: Hardcoded as 2026 in `process_data.py`
- **Units**: Strava API returns meters and m/s; dashboard displays km, min/km (run pace), km/h (ride speed)
- **Template**: Table-based layout (no flexbox/grid) for e-ink compatibility; ASCII icons (`[B]` bike, `[R]` run, `[S]` swim, `[W]` workout)
- **Strava API**: Uses `requests` directly, not `stravalib`
- **AI proxy**: Supports `ANTHROPIC_BASE_URL` env var for Baidu Qianfan proxy
- **Error handling**: Graceful fallbacks — AI plan failure → rule-based plan; zones fetch failure → empty dict
- **Chinese language**: Config comments, training plan prompts, and some activity names are in Chinese

## Key Files

- `config.yaml` — User goals (annual/weekly), race calendar, manual data overrides
- `templates/dashboard.html` — E-ink Jinja2 template (auto-refresh 3600s)
- `.github/workflows/daily-build.yml` — Daily 06:00 CST build + deploy to `gh-pages`
- `.env.secrets` — API credentials (gitignored)

## Deployment

GitHub Actions deploys `output/` to the `gh-pages` branch via `peaceiris/actions-gh-pages@v4`. The workflow triggers daily at 06:00 Beijing time, on `workflow_dispatch`, and on pushes to `config.yaml`.
