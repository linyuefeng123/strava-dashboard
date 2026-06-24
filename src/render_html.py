#!/usr/bin/env python3
"""
Render the e-ink sports dashboard as a single HTML page.

Reads processed data from JSON, applies formatting helpers, and renders
a Kindle Paperwhite-optimized (758x1024, 16-gray) dashboard via Jinja2.
"""

import json
import math
import os
import time
from datetime import datetime

from jinja2 import Environment, FileSystemLoader


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def fmt_km(meters: float) -> str:
    """Format meters as kilometers with 1 decimal, e.g. 850.0."""
    if meters is None:
        return "0.0"
    return f"{meters / 1000:.1f}"


def fmt_hours(seconds: float) -> str:
    """Format seconds as hours with 1 decimal, e.g. 12.5."""
    if seconds is None or seconds == 0:
        return "0.0"
    return f"{seconds / 3600:.1f}"


def fmt_mmss(seconds: float) -> str:
    """Format seconds as MM:SS, e.g. 130 -> '2:10'."""
    if seconds is None or seconds == 0:
        return "0:00"
    s = int(round(seconds))
    m, sec = divmod(abs(s), 60)
    sign = "-" if s < 0 else ""
    return f"{sign}{m}:{sec:02d}"


def fmt_pace(speed_ms: float) -> str:
    """Format speed (m/s) as min:sec/km pace, e.g. 4.5 -> '3:42'."""
    if speed_ms is None or speed_ms <= 0:
        return "--:--"
    pace_min_per_km = 1000 / (speed_ms * 60)  # total minutes per km
    mins = int(pace_min_per_km)
    secs = int(round((pace_min_per_km - mins) * 60))
    if secs == 60:
        mins += 1
        secs = 0
    return f"{mins}:{secs:02d}"


def fmt_pct(value: float, total: float) -> int:
    """Return percentage as integer (clamped 0-100)."""
    if total is None or total == 0:
        return 0
    return min(100, max(0, int(round(value / total * 100))))


def fmt_time_hm(seconds: float) -> str:
    """Format seconds as H:MM:SS or M:SS for race times."""
    if seconds is None or seconds == 0:
        return "-"
    s = int(round(seconds))
    if s >= 3600:
        h, remainder = divmod(s, 3600)
        m, sec = divmod(remainder, 60)
        return f"{h}:{m:02d}:{sec:02d}"
    else:
        m, sec = divmod(s, 60)
        return f"{m}:{sec:02d}"


# ---------------------------------------------------------------------------
# ASCII bar chart generator
# ---------------------------------------------------------------------------

def _fmt_trend_value(meters: float) -> str:
    """Format a distance for bar chart labels, compact: '320k' or '40.5k'."""
    km = meters / 1000
    if km == int(km):
        return f"{int(km)}k"
    return f"{km:.1f}k"


def ascii_bar_chart(values: list, labels: list, max_width: int = 20) -> list:
    """
    Generate ASCII bar chart rows.

    Returns list of dicts: {"label": str, "bar": str, "value": str}
    Each bar is made of '#' chars, padded with spaces to max_width.
    """
    if not values:
        return []

    max_val = max(values) if max(values) > 0 else 1
    rows = []
    for label, val in zip(labels, values):
        bar_len = int(round(val / max_val * max_width)) if max_val > 0 else 0
        bar_len = max(0, min(max_width, bar_len))
        bar = "#" * bar_len + " " * (max_width - bar_len)
        rows.append({
            "label": label,
            "bar": bar,
            "value": _fmt_trend_value(val),
        })
    return rows


# ---------------------------------------------------------------------------
# Sport icon mapping
# ---------------------------------------------------------------------------

SPORT_ICONS = {
    "Ride": "[B]",
    "VirtualRide": "[B]",
    "Run": "[R]",
    "TrailRun": "[R]",
    "Swim": "[S]",
    "Workout": "[W]",
    "WeightTraining": "[W]",
    "Crossfit": "[W]",
}

SPORT_ORDER = ["Ride", "Run", "Swim", "Workout"]


def sport_icon(sport_type: str) -> str:
    """Return e-ink-safe sport icon text."""
    return SPORT_ICONS.get(sport_type, "[?]")


def sport_display_name(sport_type: str) -> str:
    """Return short display name for sport type."""
    names = {
        "Ride": "Ride",
        "VirtualRide": "Ride",
        "Run": "Run",
        "TrailRun": "Run",
        "Swim": "Swim",
        "Workout": "Lift",
        "WeightTraining": "Lift",
        "Crossfit": "Lift",
    }
    return names.get(sport_type, sport_type)


# ---------------------------------------------------------------------------
# Data preparation
# ---------------------------------------------------------------------------

def prepare_annual_goals(data: dict, config: dict) -> list:
    """Build annual goals list from processed data and config."""
    annual = data.get("annual_summary", {})
    goals_config = config.get("goals", {}).get("annual", {})

    goal_defs = [
        {
            "sport": "Ride",
            "icon": "[B]",
            "current_m": annual.get("ride_distance_m", 0),
            "target_m": goals_config.get("ride_km", 5000) * 1000,
            "unit": "km",
        },
        {
            "sport": "Run",
            "icon": "[R]",
            "current_m": annual.get("run_distance_m", 0),
            "target_m": goals_config.get("run_km", 800) * 1000,
            "unit": "km",
        },
        {
            "sport": "Swim",
            "icon": "[S]",
            "current_m": annual.get("swim_distance_m", 0),
            "target_m": goals_config.get("swim_km", 20) * 1000,
            "unit": "km",
        },
        {
            "sport": "Lift",
            "icon": "[W]",
            "current": annual.get("workout_count", 0),
            "target": goals_config.get("workout_count", 100),
            "unit": "x",
        },
    ]

    result = []
    for g in goal_defs:
        if "current_m" in g:
            current_disp = fmt_km(g["current_m"])
            target_disp = fmt_km(g["target_m"])
            pct = fmt_pct(g["current_m"], g["target_m"])
            current_raw = g["current_m"]
            target_raw = g["target_m"]
        else:
            current_disp = str(g["current"])
            target_disp = str(g["target"])
            pct = fmt_pct(g["current"], g["target"])
            current_raw = g["current"]
            target_raw = g["target"]

        result.append({
            "sport": g["sport"],
            "icon": g["icon"],
            "current_disp": current_disp,
            "target_disp": target_disp,
            "pct": pct,
            "unit": g["unit"],
            "current_raw": current_raw,
            "target_raw": target_raw,
        })

    return result


def prepare_key_metrics(data: dict, config: dict) -> list:
    """Build key metrics display list."""
    metrics = []
    annual = data.get("annual_summary", {})
    zones = data.get("zones", {})
    key_config = config.get("goals", {}).get("key_metrics", {})

    # FTP
    current_ftp = zones.get("ftp", 0)
    target_ftp = key_config.get("ftp", 250)
    metrics.append({
        "label": "FTP",
        "current": f"{current_ftp}W" if current_ftp else "--W",
        "target": f"{target_ftp}W",
        "trend": "+" if current_ftp and current_ftp >= 220 else "",
    })

    # 5K pace from sample_race_pace
    race_pace = zones.get("sample_race_pace", {})
    time_str = race_pace.get("time", "")
    metrics.append({
        "label": "5K",
        "current": time_str if time_str else "--:--",
        "target": key_config.get("run_5k_pace", "--:--") + "/km",
        "trend": "",
    })

    # PRs
    metrics.append({
        "label": "Ride PRs",
        "current": str(annual.get("ride_prs", 0)),
        "target": "",
        "trend": "",
    })
    metrics.append({
        "label": "Run PRs",
        "current": str(annual.get("run_prs", 0)),
        "target": "",
        "trend": "",
    })

    return metrics


def prepare_weekly_goals(data: dict, config: dict) -> list:
    """Build weekly goals list."""
    weekly = data.get("weekly_summary", {})
    goals_config = config.get("goals", {}).get("weekly", {})

    goal_defs = [
        {
            "sport": "Ride",
            "icon": "[B]",
            "current_m": weekly.get("ride_distance_m", 0),
            "target_m": goals_config.get("ride_km", 100) * 1000,
        },
        {
            "sport": "Run",
            "icon": "[R]",
            "current_m": weekly.get("run_distance_m", 0),
            "target_m": goals_config.get("run_km", 20) * 1000,
        },
        {
            "sport": "Lift",
            "icon": "[W]",
            "current": weekly.get("workout_count", 0),
            "target": goals_config.get("workout_count", 2),
        },
    ]

    result = []
    done_count = 0
    total_count = 0
    for g in goal_defs:
        if "current_m" in g:
            current_disp = fmt_km(g["current_m"])
            target_disp = fmt_km(g["target_m"])
            pct = fmt_pct(g["current_m"], g["target_m"])
            is_done = g["current_m"] >= g["target_m"]
        else:
            current_disp = str(g["current"])
            target_disp = str(g["target"])
            pct = fmt_pct(g["current"], g["target"])
            is_done = g["current"] >= g["target"]

        total_count += 1
        if is_done:
            done_count += 1

        result.append({
            "sport": g["sport"],
            "icon": g["icon"],
            "current_disp": current_disp,
            "target_disp": target_disp,
            "pct": pct,
            "done": is_done,
        })

    return result, done_count, total_count


def prepare_monthly_trends(data: dict) -> list:
    """Build monthly trend ASCII bar charts."""
    trends = data.get("monthly_trends", {})
    result = []

    for sport_key, display_name, icon in [
        ("ride", "Ride", "[B]"),
        ("run", "Run", "[R]"),
    ]:
        sport_data = trends.get(sport_key, {})
        months = sport_data.get("months", [])
        distances = sport_data.get("distances_m", [])

        if months and distances:
            chart = ascii_bar_chart(distances, months, max_width=22)
            result.append({
                "sport": display_name,
                "icon": icon,
                "chart": chart,
            })

    return result


def prepare_upcoming(data: dict) -> list:
    """Build upcoming events list."""
    events = data.get("upcoming_events", [])
    today = datetime.now().date()

    result = []
    for event in events:
        event_date_str = event.get("date", "")
        try:
            event_date = datetime.strptime(event_date_str, "%Y-%m-%d").date()
            days_away = (event_date - today).days
        except (ValueError, TypeError):
            days_away = -1

        if days_away > 0:
            short_date = event_date.strftime("%b %d")
            result.append({
                "name": event.get("name", ""),
                "days": days_away,
                "date": short_date,
            })

    return result


def prepare_training_plan(data: dict) -> list:
    """Build weekly training plan."""
    return data.get("training_plan", [])


# ---------------------------------------------------------------------------
# Main renderer
# ---------------------------------------------------------------------------

def render_html(
    data_path: str = "data/processed.json",
    template_path: str = "templates/dashboard.html",
    output_path: str = "output/index.html",
) -> str:
    """
    Render the e-ink dashboard HTML page.

    Args:
        data_path: Path to processed JSON data file.
        template_path: Path to the Jinja2 template directory (directory containing the template).
        output_path: Path to write the rendered HTML.

    Returns:
        The rendered HTML string.
    """
    # Load processed data
    with open(data_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Load config for goals
    config_path = os.path.join(os.path.dirname(data_path), "..", "config.yaml")
    config = {}
    if os.path.exists(config_path):
        import yaml
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}

    # Prepare template data
    template_data = {
        "athlete_name": data.get("athlete_name", "Athlete"),
        "date": datetime.now().strftime("%Y.%m.%d"),
        "timestamp": str(int(time.time())),
        "annual_goals": prepare_annual_goals(data, config),
        "key_metrics": prepare_key_metrics(data, config),
        "monthly_trends": prepare_monthly_trends(data),
        "upcoming": prepare_upcoming(data),
        "training_plan": prepare_training_plan(data),
    }

    # Weekly goals (with done count)
    weekly_goals, done_count, total_count = prepare_weekly_goals(data, config)
    template_data["weekly_goals"] = weekly_goals
    template_data["weekly_done"] = done_count
    template_data["weekly_total"] = total_count

    # Set up Jinja2
    template_dir = os.path.dirname(template_path) if os.path.isfile(template_path) else template_path
    template_name = os.path.basename(template_path) if os.path.isfile(template_path) else "dashboard.html"

    env = Environment(
        loader=FileSystemLoader(template_dir),
        autoescape=False,
    )

    # Register custom filters
    env.filters["km"] = fmt_km
    env.filters["hours"] = fmt_hours
    env.filters["mmss"] = fmt_mmss
    env.filters["pace"] = fmt_pace
    env.filters["pct"] = fmt_pct

    # Render
    template = env.get_template(template_name)
    html = template.render(**template_data)

    # Write output
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"Dashboard rendered: {output_path}")
    return html


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Render Strava e-ink dashboard")
    parser.add_argument("--data", default="data/processed.json", help="Processed data JSON path")
    parser.add_argument("--template", default="templates/dashboard.html", help="Template path")
    parser.add_argument("--output", default="output/index.html", help="Output HTML path")
    args = parser.parse_args()

    render_html(
        data_path=args.data,
        template_path=args.template,
        output_path=args.output,
    )
