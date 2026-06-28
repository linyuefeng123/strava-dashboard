#!/usr/bin/env python3
"""
Render the e-ink sports dashboard as a single HTML page.

Reads processed data from JSON, applies formatting helpers, and renders
a Kindle Paperwhite-optimized (758x1024, 16-gray) dashboard via Jinja2.
"""

from __future__ import annotations

import json
import math
import os
import sys
import time
from datetime import datetime, date, timedelta

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

def _fmt_trend_value(km: float) -> str:
    """Format a distance for bar chart labels, compact: '320k' or '40.5k'."""
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


def svg_line_chart(values: list, labels: list, width: int = 350, height: int = 110) -> str:
    """Generate an SVG line chart for e-ink display.

    Args:
        values: List of numeric values (e.g. weekly distances in km).
        labels: List of x-axis labels (e.g. week names).
        width: SVG canvas width.
        height: SVG canvas height.

    Returns:
        SVG string with line chart.
    """
    if not values or max(values) <= 0:
        return ""

    padding_top = 12
    padding_left = 8
    padding_bottom = 16
    padding_right = 8

    chart_w = width - padding_left - padding_right
    chart_h = height - padding_top - padding_bottom

    max_val = max(values)
    min_val = min(values)
    val_range = max_val - min_val if max_val > min_val else 1

    n = len(values)
    points = []
    for i, v in enumerate(values):
        x = padding_left + int((i / (n - 1)) * chart_w) if n > 1 else padding_left + chart_w // 2
        y = padding_top + int(chart_h - ((v - min_val) / val_range) * chart_h)
        points.append((x, y))

    # Build SVG
    lines = [f'<svg width="{width}" height="{height}" xmlns="http://www.w3.org/2000/svg" style="background:#FFFFFF;">']

    # Grid lines (3 horizontal lines)
    for gi in range(4):
        gy = padding_top + int(chart_h * gi / 3)
        lines.append(f'<line x1="{padding_left}" y1="{gy}" x2="{width - padding_right}" y2="{gy}" stroke="#DDDDDD" stroke-width="1"/>')

    # Y-axis value labels
    for gi in range(4):
        gy = padding_top + int(chart_h * gi / 3)
        val = max_val - (val_range * gi / 3)
        lines.append(f'<text x="{padding_left - 2}" y="{gy + 3}" fill="#888888" font-size="7" text-anchor="end">{val:.0f}</text>')

    # Line
    polyline_pts = " ".join(f"{px},{py}" for px, py in points)
    lines.append(f'<polyline points="{polyline_pts}" fill="none" stroke="#444444" stroke-width="2" stroke-linejoin="round"/>')

    # Data points
    for px, py in points:
        lines.append(f'<circle cx="{px}" cy="{py}" r="3" fill="#444444" stroke="#FFFFFF" stroke-width="1"/>')

    # X-axis labels - show all, use compact format
    for i, (px, py) in enumerate(points):
        if i < len(labels):
            label = labels[i].replace("W", "")  # "W1" -> "1"
            lines.append(f'<text x="{px}" y="{height - 2}" fill="#888888" font-size="6" text-anchor="middle">{label}</text>')

    lines.append('</svg>')
    return "\n".join(lines)


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
            "current_km": annual.get("ride", {}).get("distance_km", 0),
            "target_km": goals_config.get("ride_km", 5000),
            "unit": "km",
        },
        {
            "sport": "Run",
            "icon": "[R]",
            "current_km": annual.get("run", {}).get("distance_km", 0),
            "target_km": goals_config.get("run_km", 800),
            "unit": "km",
        },
        {
            "sport": "Swim",
            "icon": "[S]",
            "current_km": annual.get("swim", {}).get("distance_km", 0),
            "target_km": goals_config.get("swim_km", 20),
            "unit": "km",
        },
        {
            "sport": "Lift",
            "icon": "[W]",
            "current": annual.get("workout", {}).get("count", 0),
            "target": goals_config.get("workout_count", 100),
            "unit": "x",
        },
    ]

    result = []
    for g in goal_defs:
        if "current_km" in g:
            current_disp = f"{g['current_km']:.1f}"
            target_disp = str(g["target_km"])
            pct = fmt_pct(g["current_km"], g["target_km"])
            current_raw = g["current_km"]
            target_raw = g["target_km"]
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
    key_data = data.get("key_metrics", {})
    key_config = config.get("goals", {}).get("key_metrics", {})

    # FTP
    current_ftp = key_data.get("ftp", 0)
    target_ftp = key_config.get("ftp", 250)
    metrics.append({
        "label": "FTP",
        "current": f"{current_ftp}W" if current_ftp else "--W",
        "target": f"{target_ftp}W",
    })

    # 5K best time
    best_5k = key_data.get("best_5k_time")
    if best_5k:
        metrics.append({
            "label": "5K",
            "current": fmt_time_hm(best_5k),
            "target": key_config.get("run_5k_pace", "--:--") + "/km",
        })
    else:
        metrics.append({
            "label": "5K",
            "current": "--:--",
            "target": key_config.get("run_5k_pace", "--:--") + "/km",
        })

    # Total PRs
    total_prs = key_data.get("total_prs", 0)
    metrics.append({
        "label": "PRs",
        "current": str(total_prs),
        "target": "",
    })

    # Streak
    streak = data.get("streak", 0)
    metrics.append({
        "label": "Streak",
        "current": f"{streak}d",
        "target": "",
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
            "current_km": weekly.get("ride", {}).get("distance_km", 0),
            "target_km": goals_config.get("ride_km", 100),
        },
        {
            "sport": "Run",
            "icon": "[R]",
            "current_km": weekly.get("run", {}).get("distance_km", 0),
            "target_km": goals_config.get("run_km", 20),
        },
        {
            "sport": "Lift",
            "icon": "[W]",
            "current": weekly.get("workout", {}).get("count", 0),
            "target": goals_config.get("workout_count", 2),
        },
    ]

    result = []
    done_count = 0
    total_count = 0
    for g in goal_defs:
        if "current_km" in g:
            current_disp = f"{g['current_km']:.1f}"
            target_disp = str(g["target_km"])
            pct = fmt_pct(g["current_km"], g["target_km"])
            is_done = g["current_km"] >= g["target_km"]
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
    """Build monthly trend ASCII bar charts from processed data."""
    monthly_trend = data.get("monthly_trend", {})
    result = []

    for sport_key, display_name, icon in [
        ("ride", "Ride", "[B]"),
        ("run", "Run", "[R]"),
    ]:
        months = []
        distances = []
        # monthly_trend is {month_num: {sport: {distance_km, ...}}}
        for month_num in sorted(monthly_trend.keys(), key=lambda x: int(x)):
            month_data = monthly_trend[month_num]
            sport_data = month_data.get(sport_key, {})
            dist_km = sport_data.get("distance_km", 0)
            months.append(f"{int(month_num)}月")
            distances.append(dist_km)

        if months and any(d > 0 for d in distances):
            chart = ascii_bar_chart(distances, months, max_width=22)
            result.append({
                "sport": display_name,
                "icon": icon,
                "chart": chart,
            })

    return result


def prepare_weekly_trends(data: dict) -> list:
    """Build weekly trend ASCII bar charts and SVG line charts from processed data."""
    weekly_trend = data.get("weekly_trend", [])
    result = []

    for sport_key, display_name, icon in [
        ("ride", "Ride", "[B]"),
        ("run", "Run", "[R]"),
    ]:
        labels = []
        distances = []
        for week in reversed(weekly_trend):
            week_num = week.get("week_num", 0)
            sport_data = week.get("sports", {}).get(sport_key, {})
            dist_km = sport_data.get("distance_km", 0)
            labels.append(f"W{week_num}")
            distances.append(dist_km)

        if labels and any(d > 0 for d in distances):
            chart = ascii_bar_chart(distances, labels, max_width=22)
            svg = svg_line_chart(distances, labels, width=350, height=110)
            result.append({
                "sport": display_name,
                "icon": icon,
                "chart": chart,
                "svg": svg,
            })

    return result


def prepare_recent_activities(data: dict) -> list:
    """Build recent activities list from processed data."""
    return data.get("recent_activities", [])


def prepare_upcoming_races(data: dict) -> list:
    """Build upcoming races list with countdown days."""
    races = data.get("races", {})
    upcoming = races.get("upcoming", [])
    today = date.today()

    result = []
    for race in upcoming:
        race_date_str = race.get("date", "")
        try:
            race_date = datetime.strptime(race_date_str, "%Y-%m-%d").date()
            days_away = (race_date - today).days
        except (ValueError, TypeError):
            days_away = -1

        if days_away > 0:
            short_date = race_date.strftime("%m/%d")
            result.append({
                "name": race.get("name", ""),
                "days": days_away,
                "date": short_date,
                "sport": race.get("sport", ""),
            })

    return result


def prepare_year_progress(data: dict, config: dict) -> dict:
    """Build year progress info: days elapsed vs goal completion."""
    today = date.today()
    year_start = date(today.year, 1, 1)
    year_end = date(today.year, 12, 31)
    total_days = (year_end - year_start).days + 1
    elapsed_days = (today - year_start).days + 1
    elapsed_pct = round(elapsed_days / total_days * 100, 1)

    # Compute overall goal completion from annual goals
    annual = data.get("annual_summary", {})
    goals_config = config.get("goals", {}).get("annual", {})

    goal_pcts = []
    goal_items = [
        ("ride", "ride_km", "distance_km"),
        ("run", "run_km", "distance_km"),
        ("swim", "swim_km", "distance_km"),
        ("workout", "workout_count", "count"),
    ]
    for sport_key, config_key, metric in goal_items:
        target = goals_config.get(config_key, 0)
        if target > 0:
            current = annual.get(sport_key, {}).get(metric, 0)
            goal_pcts.append(min(100, round(current / target * 100, 1)))

    avg_goal_pct = round(sum(goal_pcts) / len(goal_pcts), 1) if goal_pcts else 0

    return {
        "elapsed_days": elapsed_days,
        "total_days": total_days,
        "elapsed_pct": elapsed_pct,
        "goal_pct": avg_goal_pct,
    }


def prepare_training_plan(data: dict) -> list:
    """Build weekly training plan from training_plan.json format.

    The training plan is stored as:
    {plan: {周一: "...", 周二: "...", ...}, source: "rule-based"}

    Convert to template format: [{day, description, rest, icon}, ...]
    """
    raw_plan = data.get("training_plan", {})

    # If already in list format, return as-is
    if isinstance(raw_plan, list):
        return raw_plan

    # Convert dict format to list
    plan_dict = raw_plan.get("plan", {}) if isinstance(raw_plan, dict) else {}
    if not plan_dict:
        return []

    # Map Chinese day names to short forms and detect sport icons
    day_map = {
        "周一": "Mon", "周二": "Tue", "周三": "Wed",
        "周四": "Thu", "周五": "Fri", "周六": "Sat", "周日": "Sun",
    }

    sport_keywords = {
        "[R]": ["跑", "run", "Run"],
        "[B]": ["骑", "MyWhoosh", "Ride", "ride", "骑行"],
        "[W]": ["力量", "workout", "Workout", "举重", "锻炼"],
        "[S]": ["游", "swim", "Swim"],
    }

    result = []
    for cn_day, desc in plan_dict.items():
        short_day = day_map.get(cn_day, cn_day)
        is_rest = any(kw in desc for kw in ["休息", "rest", "Rest"])

        # Detect sport icon
        icon = ""
        if not is_rest:
            for sport_icon, keywords in sport_keywords.items():
                if any(kw in desc for kw in keywords):
                    icon = sport_icon
                    break

        result.append({
            "day": short_day,
            "description": desc,
            "rest": is_rest,
            "icon": icon,
        })

    return result


def prepare_ai_tip(data: dict) -> str:
    """Extract a key AI tip from the training plan.

    Returns the first non-rest day's description as a highlighted tip.
    """
    plan = data.get("training_plan", {})

    # Handle dict format {plan: {周一: ..., ...}}
    if isinstance(plan, dict) and "plan" in plan:
        plan_dict = plan["plan"]
        for day, desc in plan_dict.items():
            if not any(kw in desc for kw in ["休息", "rest", "Rest"]) and desc.strip():
                return desc
        return ""

    # Handle list format
    if isinstance(plan, list):
        for day in plan:
            if not day.get("rest", False) and day.get("description", "").strip():
                return day["description"]

    return ""


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

    # Try to load athlete name from profile.json
    athlete_name = data.get("athlete_name", "Athlete")
    if athlete_name == "Athlete":
        profile_path = os.path.join(os.path.dirname(data_path), "profile.json")
        if os.path.exists(profile_path):
            try:
                with open(profile_path, "r", encoding="utf-8") as f:
                    profile = json.load(f)
                    athlete_name = profile.get("firstname", "Athlete")
                    lastname = profile.get("lastname", "")
                    if lastname:
                        athlete_name = f"{athlete_name} {lastname}"
            except (json.JSONDecodeError, FileNotFoundError):
                pass

    # Load training plan from separate file
    training_plan_path = os.path.join(os.path.dirname(data_path), "training_plan.json")
    training_plan_data = {}
    if os.path.exists(training_plan_path):
        try:
            with open(training_plan_path, "r", encoding="utf-8") as f:
                training_plan_data = json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            pass

    # Prepare template data
    template_data = {
        "athlete_name": athlete_name,
        "date": datetime.now().strftime("%Y.%m.%d"),
        "timestamp": str(int(time.time())),
        "streak": data.get("streak", 0),
        "annual_goals": prepare_annual_goals(data, config),
        "key_metrics": prepare_key_metrics(data, config),
        "monthly_trends": prepare_monthly_trends(data),
        "weekly_trends": prepare_weekly_trends(data),
        "recent_activities": prepare_recent_activities(data),
        "upcoming_races": prepare_upcoming_races(data),
        "year_progress": prepare_year_progress(data, config),
        "training_plan": prepare_training_plan({"training_plan": training_plan_data}),
        "ai_tip": prepare_ai_tip({"training_plan": training_plan_data}),
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
# Multi-page rendering helpers
# ---------------------------------------------------------------------------

def _load_json_safe(path: str) -> dict:
    """Load a JSON file, returning empty dict on failure."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _load_yaml_safe(path: str) -> dict:
    """Load a YAML file, returning empty dict on failure."""
    try:
        import yaml
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
            return data if isinstance(data, dict) else {}
    except (FileNotFoundError, yaml.YAMLError):
        return {}


def _get_jinja_env(template_dir: str = "templates") -> Environment:
    """Create a Jinja2 Environment with custom filters registered."""
    env = Environment(
        loader=FileSystemLoader(template_dir),
        autoescape=False,
    )
    env.filters["km"] = fmt_km
    env.filters["hours"] = fmt_hours
    env.filters["mmss"] = fmt_mmss
    env.filters["pace"] = fmt_pace
    env.filters["pct"] = fmt_pct
    return env


def _render_single_page(
    env: Environment,
    template_name: str,
    output_path: str,
    context: dict,
) -> str:
    """Render a single Jinja2 template and write to file."""
    template = env.get_template(template_name)
    html = template.render(**context)

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"  Rendered: {output_path}")
    return html


# ---------------------------------------------------------------------------
# Data preparation for new pages
# ---------------------------------------------------------------------------

def _prepare_weather_context(data: dict, config: dict, weather: dict) -> dict:
    """Build template context for the weather/calendar page."""
    from lunar import solar_to_lunar, format_solar_date

    today = date.today()
    lunar = solar_to_lunar(today)

    # Solar date in Chinese
    solar_date = format_solar_date(today)

    # Lunar date string
    lunar_date = lunar["date_cn"]

    # Weather data
    weather_data = weather if weather else None

    # Races from processed data (both upcoming and past)
    races_raw = data.get("races", {})
    races = []

    # Add upcoming races with countdown
    for race in races_raw.get("upcoming", []):
        race_date_str = race.get("date", "")
        try:
            race_date = datetime.strptime(race_date_str, "%Y-%m-%d").date()
            countdown = (race_date - today).days
        except (ValueError, TypeError):
            countdown = -1

        races.append({
            "name": race.get("name", ""),
            "date": race_date_str,
            "countdown": countdown,
            "status": "upcoming" if countdown > 0 else "past",
        })

    # Add past races
    for race in races_raw.get("past", []):
        races.append({
            "name": race.get("name", ""),
            "date": race.get("date", ""),
            "countdown": 0,
            "status": "done",
        })

    # Quote
    quote_data = config.get("_quotes", {})
    quote = quote_data.get("quote") if quote_data else None

    return {
        "page": "weather",
        "date": today.strftime("%Y.%m.%d"),
        "solar_date": solar_date,
        "lunar_date": lunar_date,
        "weather": weather_data,
        "races": races,
        "quote": quote,
    }


def _prepare_todo_context(data: dict, config: dict) -> dict:
    """Build template context for the todo/focus page."""
    today = date.today()

    # Todos: try multiple sources in priority order
    # 1. Apple Reminders (reminders.json) - iCloud synced
    # 2. Feishu tasks (feishu_tasks.json)
    # 3. config.yaml todos (manual fallback)
    todos = []
    done_count = 0

    reminders_data = _load_json_safe(os.path.join("data", "reminders.json"))
    reminders_todos = reminders_data.get("todos", [])

    feishu_data = _load_json_safe(os.path.join("data", "feishu_tasks.json"))
    feishu_todos = feishu_data.get("todos", [])

    if reminders_todos or feishu_todos:
        # Merge from Apple Reminders and Feishu
        for t in reminders_todos:
            if not t["done"]:
                todos.append({"text": t["text"], "done": False, "source": "reminders"})
            elif t.get("completed_date"):
                try:
                    comp_date = datetime.strptime(t["completed_date"], "%Y-%m-%d").date()
                    if (today - comp_date).days <= 7:
                        todos.append({"text": t["text"], "done": True, "source": "reminders"})
                        done_count += 1
                except (ValueError, TypeError):
                    pass

        for t in feishu_todos:
            if not t["done"]:
                todos.append({"text": t["text"], "done": False, "source": "feishu"})
            else:
                done_count += 1

        # Put completed items at the bottom
        todos.sort(key=lambda x: x["done"])
    else:
        # Fallback to config.yaml todos
        todos_raw = config.get("todos", [])
        for todo in todos_raw:
            text = todo.get("text", "") if isinstance(todo, dict) else str(todo)
            is_done = todo.get("done", False) if isinstance(todo, dict) else False
            if is_done:
                done_count += 1
            todos.append({"text": text, "done": is_done})

    # Training plan
    training_plan_path = os.path.join("data", "training_plan.json")
    training_plan_data = _load_json_safe(training_plan_path)
    training_plan = prepare_training_plan({"training_plan": training_plan_data})

    # Mark today in the training plan
    weekday_map = {
        0: "Mon", 1: "Tue", 2: "Wed", 3: "Thu",
        4: "Fri", 5: "Sat", 6: "Sun",
    }
    today_short = weekday_map[today.weekday()]
    for day in training_plan:
        day["is_today"] = (day.get("day") == today_short)

    # Streak
    streak = data.get("streak", 0)

    return {
        "page": "todo",
        "date": today.strftime("%Y.%m.%d"),
        "todos": todos,
        "todo_done_count": done_count,
        "todo_total_count": len(todos),
        "training_plan": training_plan,
        "streak": streak,
    }


def _prepare_guide_context(data: dict, config: dict) -> dict:
    """Build template context for the daily guidance page."""
    today = date.today()

    # Today's training
    training_plan_path = os.path.join("data", "training_plan.json")
    training_plan_data = _load_json_safe(training_plan_path)
    training_plan = prepare_training_plan({"training_plan": training_plan_data})

    weekday_map = {
        0: "Mon", 1: "Tue", 2: "Wed", 3: "Thu",
        4: "Fri", 5: "Sat", 6: "Sun",
    }
    today_short = weekday_map[today.weekday()]

    today_training = None
    for day in training_plan:
        if day.get("day") == today_short:
            today_training = day.get("description", "")
            break

    # Weekly goals progress
    weekly_goals, _, _ = prepare_weekly_goals(data, config)

    # Next upcoming race
    races_raw = data.get("races", {})
    next_race = None
    for race in races_raw.get("upcoming", []):
        race_date_str = race.get("date", "")
        try:
            race_date = datetime.strptime(race_date_str, "%Y-%m-%d").date()
            countdown = (race_date - today).days
        except (ValueError, TypeError):
            countdown = -1

        if countdown > 0:
            next_race = {
                "name": race.get("name", ""),
                "countdown": countdown,
            }
            break

    # Training zones from zones.json
    zones_path = os.path.join("data", "zones.json")
    zones_data = _load_json_safe(zones_path)
    zones = {}

    # HR zones
    hr_zones = zones_data.get("heart_rate_zones", [])
    if hr_zones and isinstance(hr_zones, list):
        zone_parts = []
        for i, z in enumerate(hr_zones):
            if isinstance(z, dict):
                low = z.get("min", z.get("from", 0))
                high = z.get("max", z.get("to", 0))
                if i < len(hr_zones) - 1:
                    zone_parts.append(f"Z{i+1}<{int(high)}")
                else:
                    zone_parts.append(f"Z{i+1}≥{int(low)}")
            elif isinstance(z, (int, float)):
                zone_parts.append(f"Z{i+1}={int(z)}")
        zones["hr_zones"] = "  ".join(zone_parts) if zone_parts else ""

    # Power zones
    power_zones = zones_data.get("power_zones", [])
    ftp = zones_data.get("ftp", 0)
    if power_zones and isinstance(power_zones, list):
        zone_parts = []
        for i, z in enumerate(power_zones):
            if isinstance(z, dict):
                low = z.get("min", z.get("from", 0))
                high = z.get("max", z.get("to", 0))
                if i < len(power_zones) - 1:
                    zone_parts.append(f"Z{i+1}<{int(high)}")
                else:
                    zone_parts.append(f"Z{i+1}≥{int(low)}")
            elif isinstance(z, (int, float)):
                zone_parts.append(f"Z{i+1}={int(z)}")
        label = f"功率 (FTP {ftp}W)" if ftp else "功率"
        zones["power_zones"] = f"{label}: " + "  ".join(zone_parts) if zone_parts else ""

    # Quote
    quote_data = config.get("_quotes", {})
    quote = quote_data.get("quote") if quote_data else None

    return {
        "page": "guide",
        "date": today.strftime("%Y.%m.%d"),
        "today_training": today_training,
        "weekly_goals": weekly_goals,
        "next_race": next_race,
        "zones": zones if zones.get("hr_zones") or zones.get("power_zones") else None,
        "quote": quote,
    }


# ---------------------------------------------------------------------------
# Work page
# ---------------------------------------------------------------------------

def _prepare_work_context(data: dict, config: dict, reminders: dict) -> dict:
    """Build template context for the work page."""
    today = date.today()
    todos_raw = reminders.get("todos", [])

    today_todos = []
    week_todos = []

    work_kw = ["周报", "汇报", "会议", "评审", "项目", "面谈", "复盘",
               "代码", "技术", "方案", "需求", "bug", "Bug", "提测"]

    for t in todos_raw:
        text = t.get("text", "")
        if not text.strip():
            continue
        if not any(kw in text for kw in work_kw):
            continue
        is_done = t.get("done", False)

        due = t.get("due_date", "")
        if due:
            try:
                due_date = datetime.strptime(due, "%Y-%m-%d").date()
                week_start = today - timedelta(days=today.weekday())
                week_end = week_start + timedelta(days=6)
                if week_start <= due_date <= week_end:
                    week_todos.append({"text": text, "done": is_done})
                elif due_date < week_start:
                    today_todos.append({"text": text, "done": is_done})
            except (ValueError, TypeError):
                today_todos.append({"text": text, "done": is_done})
        else:
            today_todos.append({"text": text, "done": is_done})

    today_todos.sort(key=lambda x: x["done"])
    week_todos.sort(key=lambda x: x["done"])
    today_done = sum(1 for t in today_todos if t["done"])

    # Meetings from config (will be fed by Feishu CLI later)
    week_meetings = config.get("meetings", {}).get("week", [])

    return {
        "page": "work",
        "date": today.strftime("%Y.%m.%d"),
        "today_todos": today_todos,
        "today_done_count": today_done,
        "today_total_count": len(today_todos),
        "week_todos": week_todos,
        "week_meetings": week_meetings,
    }


# ---------------------------------------------------------------------------
# Life page
# ---------------------------------------------------------------------------

def _prepare_life_context(data: dict, config: dict, weather: dict, reminders: dict) -> dict:
    """Build template context for the life page."""
    today = date.today()

    # Lunar
    try:
        from lunar import solar_to_lunar, format_solar_date
        lunar = solar_to_lunar(today)
        solar_date = format_solar_date(today)
        lunar_date = lunar["date_cn"]
    except Exception:
        wd = ["星期一","星期二","星期三","星期四","星期五","星期六","星期日"]
        solar_date = f"{today.year}年{today.month}月{today.day}日 {wd[today.weekday()]}"
        lunar_date = ""

    # Life todos (non-work items)
    work_kw = ["周报", "汇报", "会议", "评审", "项目", "面谈", "复盘",
               "代码", "技术", "方案", "需求", "bug", "Bug", "提测"]
    todos_raw = reminders.get("todos", [])
    life_todos = []
    birthdays = []
    streak = data.get("streak", 0)

    for t in todos_raw:
        text = t.get("text", "")
        if not text.strip():
            continue
        is_done = t.get("done", False)

        if any(kw in text for kw in ["生日", "纪念日", "结婚"]):
            due = t.get("due_date", "")
            bday_display = due[:5] if len(due) >= 5 else ""
            bday_countdown = ""
            if due:
                try:
                    parts = due.split("-")
                    if len(parts) == 3:
                        ed = date(today.year, int(parts[1]), int(parts[2]))
                        if ed < today:
                            ed = date(today.year + 1, int(parts[1]), int(parts[2]))
                        days = (ed - today).days
                        if 0 < days <= 365:
                            bday_countdown = f"{days}天后"
                except (ValueError, TypeError):
                    pass
            birthdays.append({
                "name": text,
                "date": bday_display,
                "countdown": bday_countdown,
            })
            continue

        if any(kw in text for kw in work_kw):
            continue
        life_todos.append({"text": text, "done": is_done})

    life_todos.sort(key=lambda x: x["done"])
    quote_data = config.get("_quotes", {}).get("quote")
    rain_alert = weather.get("rain_alert", "") if weather else ""

    return {
        "page": "life",
        "date": today.strftime("%Y.%m.%d"),
        "solar_date": solar_date,
        "lunar_date": lunar_date,
        "weather": weather,
        "life_todos": life_todos,
        "streak": streak,
        "birthdays": birthdays,
        "quote": quote_data,
        "rain_alert": rain_alert,
    }


# ---------------------------------------------------------------------------
# Multi-page renderer
# ---------------------------------------------------------------------------

def render_all_pages(
    data_dir: str = "data",
    config_path: str = "config.yaml",
    template_dir: str = "templates",
    output_dir: str = "output",
) -> list[str]:
    """Render all 4 dashboard pages.

    Args:
        data_dir: Directory containing processed.json, weather.json, quotes.json.
        config_path: Path to config.yaml.
        template_dir: Directory containing Jinja2 templates.
        output_dir: Directory to write rendered HTML files.

    Returns:
        List of output file paths.
    """
    # Load all data sources
    data = _load_json_safe(os.path.join(data_dir, "processed.json"))
    config = _load_yaml_safe(config_path)
    weather = _load_json_safe(os.path.join(data_dir, "weather.json"))
    quotes = _load_json_safe(os.path.join(data_dir, "quotes.json"))

    # Inject quotes data into config for template access
    config["_quotes"] = quotes

    # Load athlete name from profile
    athlete_name = data.get("athlete_name", "Athlete")
    profile_path = os.path.join(data_dir, "profile.json")
    if athlete_name == "Athlete":
        profile = _load_json_safe(profile_path)
        firstname = profile.get("firstname", "Athlete")
        lastname = profile.get("lastname", "")
        athlete_name = f"{firstname} {lastname}" if lastname else firstname

    # Load training plan
    training_plan_path = os.path.join(data_dir, "training_plan.json")
    training_plan_data = _load_json_safe(training_plan_path)

    # Set up Jinja2
    env = _get_jinja_env(template_dir)

    # Load reminders for todos
    reminders = _load_json_safe(os.path.join(data_dir, "reminders.json"))

    # Define pages to render
    pages = [
        {
            "name": "sports",
            "template": "dashboard.html",
            "output": os.path.join(output_dir, "index.html"),
            "context_fn": lambda: _prepare_sports_context(data, config, athlete_name, training_plan_data),
        },
        {
            "name": "work",
            "template": "work.html",
            "output": os.path.join(output_dir, "work.html"),
            "context_fn": lambda: _prepare_work_context(data, config, reminders),
        },
        {
            "name": "life",
            "template": "life.html",
            "output": os.path.join(output_dir, "life.html"),
            "context_fn": lambda: _prepare_life_context(data, config, weather, reminders),
        },
    ]

    output_paths = []
    for page in pages:
        try:
            context = page["context_fn"]()
            _render_single_page(env, page["template"], page["output"], context)
            output_paths.append(page["output"])
        except Exception as e:
            print(f"  Error rendering {page['name']}: {e}", file=sys.stderr)

    print(f"\nAll pages rendered: {len(output_paths)}/{len(pages)}")
    return output_paths


def _prepare_sports_context(
    data: dict, config: dict, athlete_name: str, training_plan_data: dict
) -> dict:
    """Build template context for the sports dashboard page (simplified layout)."""
    today = date.today()

    # --- Key metrics: hardcoded for now ---
    ftp = 220
    run_10k = "45:00"
    swim_1500 = "待测量"

    # --- AI Training Plan ---
    ai_plan = _generate_ai_training_plan(data, config, ftp)

    # --- Weekly progress ---
    weekly = data.get("weekly_summary", {})
    goals_config = config.get("goals", {}).get("weekly", {})

    goal_defs = [
        {
            "sport": "Ride", "icon": "[B]",
            "current_km": weekly.get("ride", {}).get("distance_km", 0),
            "target_km": goals_config.get("ride_km", 100),
        },
        {
            "sport": "Run", "icon": "[R]",
            "current_km": weekly.get("run", {}).get("distance_km", 0),
            "target_km": goals_config.get("run_km", 20),
        },
        {
            "sport": "Lift", "icon": "[W]",
            "current": weekly.get("workout", {}).get("count", 0),
            "target": goals_config.get("workout_count", 2),
        },
    ]

    weekly_goals = []
    for g in goal_defs:
        if "current_km" in g:
            cd = f"{g['current_km']:.1f}"
            td = f"{g['target_km']:.0f}"
            pct = int(min(100, g["current_km"] / g["target_km"] * 100)) if g["target_km"] > 0 else 0
        else:
            cd = str(g["current"])
            td = str(g["target"])
            pct = int(min(100, g["current"] / g["target"] * 100)) if g["target"] > 0 else 0
        weekly_goals.append({
            "sport": g["sport"], "icon": g["icon"],
            "current_disp": cd, "target_disp": td, "pct": pct,
        })

    template_data = {
        "page": "sports",
        "athlete_name": athlete_name,
        "date": today.strftime("%Y.%m.%d"),
        "streak": data.get("streak", 0),
        "ftp": ftp,
        "run_10k": run_10k,
        "swim_1500": swim_1500,
        "weekly_goals": weekly_goals,
        "weekly_trends": prepare_weekly_trends(data),
        "upcoming_races": prepare_upcoming_races(data),
        "ai_plan": ai_plan,
    }

    return template_data


def _generate_ai_training_plan(data: dict, config: dict, ftp: int = None) -> dict:
    """Generate AI training suggestions based on goals and recent activity.

    Calls the Anthropic API (via Baidu Qianfan proxy) to produce personalized advice.
    Falls back to rule-based plan on API failure.
    """
    import requests as reqs
    import json as j

    today = date.today()
    weekday_cn = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]

    # Build context from recent data
    weekly = data.get("weekly_summary", {})
    annual = data.get("annual_summary", {})

    context_lines = [
        f"今天是{today.year}年{today.month}月{today.day}日 星期{['一','二','三','四','五','六','日'][today.weekday()]}",
        "",
        "=== 运动目标 ===",
        f"FTP: {ftp if ftp else 220}W → 目标 250W",
        "10公里跑步: 当前待测 → 目标 40分钟",
        "1.5公里游泳: 当前待测 → 目标 待定",
        "",
        "=== 本周运动量 ===",
        f"骑行: {weekly.get('ride', {}).get('distance_km', 0):.1f}km / {weekly.get('ride', {}).get('time_hours', 0):.1f}h",
        f"跑步: {weekly.get('run', {}).get('distance_km', 0):.1f}km / {weekly.get('run', {}).get('time_hours', 0):.1f}h",
        f"力量: {weekly.get('workout', {}).get('count', 0)}次",
        "",
        "=== 年度累计 ===",
        f"骑行: {annual.get('ride', {}).get('distance_km', 0):.0f}km / {annual.get('ride', {}).get('time_hours', 0):.0f}h",
        f"跑步: {annual.get('run', {}).get('distance_km', 0):.0f}km / {annual.get('run', {}).get('time_hours', 0):.0f}h",
        f"游泳: {annual.get('swim', {}).get('distance_km', 0):.1f}km",
        f"力量: {annual.get('workout', {}).get('count', 0)}次",
    ]

    prompt = (
        "你是一个铁人三项训练教练。请根据以下运动员数据，制定今日训练建议和本周训练计划。\n"
        + "\n".join(context_lines)
        + "\n\n"
        "请严格按照以下 JSON 格式回复，不要加任何其他文字：\n"
        "{\n"
        '  "today": "今日具体训练内容和强度",\n'
        '  "weekly": [\n'
        '    {"day": "周一", "description": "训练内容", "rest": false},\n'
        '    {"day": "周二", "description": "训练内容", "rest": false},\n'
        '    ...\n'
        '  ],\n'
        '  "note": "训练说明或注意事项"\n'
        "}\n\n"
        "要求：\n"
        "1. today 是今日的具体训练安排，包含运动类型、距离/时间、强度（心率区间/功率区间）\n"
        "2. weekly 是从今天开始的7天计划，包含骑行/跑步/力量/休息的合理安排\n"
        "3. 有氧、阈值、间歇训练要合理搭配\n"
        "4. 如果当天是休息日，rest 设为 true\n"
        "5. 用中文回复"
    )

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    base_url = os.environ.get("ANTHROPIC_BASE_URL", "https://qianfan.baidubce.com/anthropic/coding")
    model = os.environ.get("ANTHROPIC_DEFAULT_HAIKU_MODEL", "qianfan-code-latest")

    if not api_key:
        # Fallback rule-based plan
        return _rule_based_training_plan(weekly, weekday_cn[today.weekday()])

    try:
        resp = reqs.post(
            f"{base_url}/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": model,
                "max_tokens": 1024,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=30,
        )
        resp.raise_for_status()
        raw = resp.json()
        content = raw.get("content", [])
        if content and isinstance(content, list):
            text = content[0].get("text", "")
            # Parse JSON from response
            start = text.find("{")
            end = text.rfind("}") + 1
            if start >= 0 and end > start:
                plan = j.loads(text[start:end])
                # Ensure weekly has today's index
                today_idx = today.weekday()
                ordered_weekdays = weekday_cn[today_idx:] + weekday_cn[:today_idx]
                plan_weekly = []
                for day_name in ordered_weekdays:
                    found = False
                    for item in plan.get("weekly", []):
                        if item.get("day") == day_name:
                            plan_weekly.append(item)
                            found = True
                            break
                    if not found:
                        plan_weekly.append({"day": day_name, "description": "休息/轻度活动", "rest": True})
                plan["weekly"] = plan_weekly
                return plan

    except Exception as e:
        print(f"AI training plan failed: {e}", file=sys.stderr)

    return _rule_based_training_plan(weekly, weekday_cn[today.weekday()])


def _rule_based_training_plan(weekly: dict, today_cn: str) -> dict:
    """Rule-based fallback training plan."""
    ride_km = weekly.get("ride", {}).get("distance_km", 0)
    run_km = weekly.get("run", {}).get("distance_km", 0)

    # Simple weekly plan based on remaining goals
    if run_km < 10:
        # Run deficit - focus on running
        plan = [
            ("周一", "休息/拉伸", True),
            ("周二", "轻松跑 5km @5:40/km", False),
            ("周三", "MyWhoosh 有氧 45min Z2", False),
            ("周四", "间歇跑 6×800m @4:30/km", False),
            ("周五", "力量训练（上肢+核心）", False),
            ("周六", "长距离跑 10km @5:20/km", False),
            ("周日", "放松跑 5km", False),
        ]
    elif ride_km < 50:
        # Ride deficit
        plan = [
            ("周一", "休息", True),
            ("周二", "阈值训练 3×8min @260W", False),
            ("周三", "轻松跑 5km", False),
            ("周四", "MyWhoosh 间歇 6×3min 高功率", False),
            ("周五", "力量训练（全身）", False),
            ("周六", "户外骑行 60km Z2-Z3", False),
            ("周日", "长跑 8km @5:20/km", False),
        ]
    else:
        plan = [
            ("周一", "休息", True),
            ("周二", "阈值间歇 5×1000m @4:00/km", False),
            ("周三", "有氧骑行 60min Z2", False),
            ("周四", "游泳技术练习 1km", False),
            ("周五", "力量训练", False),
            ("周六", "长距离骑行 80km Z2", False),
            ("周日", "长跑 10km @5:00/km", False),
        ]

    # Rotate so today comes first
    day_names = [p[0] for p in plan]
    if today_cn in day_names:
        idx = day_names.index(today_cn)
        plan = plan[idx:] + plan[:idx]

    today_desc = ""
    for day, desc, _ in plan[:1]:
        today_desc = desc

    weekly_list = [
        {"day": d, "description": desc, "rest": rest}
        for d, desc, rest in plan
    ]

    return {
        "today": f"今日: {today_desc}",
        "weekly": weekly_list,
        "note": "规则引擎生成 · 暂用基础训练模板",
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Render Strava e-ink dashboard")
    parser.add_argument("--all", action="store_true", help="Render all 4 pages")
    parser.add_argument("--data", default="data/processed.json", help="Processed data JSON path")
    parser.add_argument("--template", default="templates/dashboard.html", help="Template path")
    parser.add_argument("--output", default="output/index.html", help="Output HTML path")
    args = parser.parse_args()

    if args.all:
        render_all_pages()
    else:
        render_html(
            data_path=args.data,
            template_path=args.template,
            output_path=args.output,
        )
