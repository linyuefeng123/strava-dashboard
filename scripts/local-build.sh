#!/bin/bash
# strava-dashboard daily local build
# Runs fetch_reminders (macOS only) + render + optional git push
# Designed to be called by launchd or cron on Mac

set -e
cd /Users/linyf/strava-dashboard

echo "[$(date)] Starting local build..."

# 1. Fetch Apple Reminders (macOS EventKit)
python3 src/fetch_reminders.py 2>&1 || echo "WARN: fetch_reminders failed"

# 2. Fetch weather and quotes
python3 src/fetch_weather.py 2>&1 || echo "WARN: fetch_weather failed"
python3 src/fetch_quotes.py 2>&1 || echo "WARN: fetch_quotes failed"

# 3. Fetch Feishu tasks (if credentials configured)
python3 src/fetch_feishu.py 2>&1 || echo "WARN: fetch_feishu failed"

# 4. Render all 4 pages
python3 src/render_html.py --all 2>&1

# 5. Commit and push data + output changes
git add data/reminders.json data/weather.json data/quotes.json data/feishu_tasks.json output/ 2>/dev/null || true
if ! git diff --staged --quiet 2>/dev/null; then
    git commit -m "chore: local build update $(date +%Y-%m-%d-%H:%M)" 2>&1
    git push origin main 2>&1
    echo "[$(date)] Pushed updates to GitHub"
else
    echo "[$(date)] No changes to push"
fi

echo "[$(date)] Local build complete"
