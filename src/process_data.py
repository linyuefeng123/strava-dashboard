"""
Data processing module for the Strava sports dashboard.

Reads activity data from JSON files and config.yaml, then computes
all dashboard metrics including summaries, goals, trends, and key metrics.
"""

from __future__ import annotations

import json
import yaml
from datetime import datetime, timedelta, date
from collections import defaultdict


# ---------------------------------------------------------------------------
# Sport-type normalisation
# ---------------------------------------------------------------------------
# Strava sport types -> dashboard canonical names
SPORT_MAP = {
    "Run": "run",
    "Ride": "ride",
    "VirtualRide": "ride",
    "WeightTraining": "workout",
    "Workout": "workout",
    "Swim": "swim",
    "Walk": "walk",
}

# Human-readable labels for each dashboard sport
SPORT_LABELS = {
    "run": "Run",
    "ride": "Ride",
    "workout": "Workout",
    "swim": "Swim",
    "walk": "Walk",
}

# Only sports that carry meaningful distance / time summaries
DISTANCE_SPORTS = {"run", "ride", "swim", "walk"}

# Reference year for annual metrics
REFERENCE_YEAR = 2026


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _normalise_sport(sport_type: str) -> str | None:
    """Map a raw Strava sport_type string to a canonical dashboard sport.

    Returns None for sport types we don't track (e.g. AlpineSki).
    """
    return SPORT_MAP.get(sport_type)


def _parse_date(dt_str: str) -> date:
    """Parse an ISO-8601 datetime string to a date object.

    Handles both '2026-06-15T08:30:00' and '2026-06-15' formats.
    """
    if dt_str is None:
        raise ValueError("date string is None")
    # Strip trailing Z / timezone offset for simplicity (use local time)
    dt_str = dt_str.rstrip("Z")
    if "+" in dt_str:
        dt_str = dt_str.split("+")[0]
    if "T" in dt_str:
        return datetime.fromisoformat(dt_str).date()
    return date.fromisoformat(dt_str)


def _week_range(reference_date: date | None = None) -> tuple[date, date]:
    """Return (monday, sunday) for the week containing *reference_date*.

    Defaults to today if no reference date is given.
    """
    if reference_date is None:
        reference_date = date.today()
    monday = reference_date - timedelta(days=reference_date.weekday())
    sunday = monday + timedelta(days=6)
    return monday, sunday


def _load_json(path: str) -> list | dict:
    """Load a JSON file, returning an empty list on missing / invalid data."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return []
    except json.JSONDecodeError:
        return []


def _load_yaml(path: str) -> dict:
    """Load a YAML file, returning an empty dict on missing / invalid data."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
            return data if isinstance(data, dict) else {}
    except FileNotFoundError:
        return {}
    except yaml.YAMLError:
        return {}


# ---------------------------------------------------------------------------
# Metric computation helpers
# ---------------------------------------------------------------------------

def _compute_annual_summary(activities: list[dict]) -> dict:
    """Per-sport annual totals: distance (km), time (h), count, calories, PRs."""
    summary: dict[str, dict] = {}

    for act in activities:
        sport = _normalise_sport(act.get("sport_type", ""))
        if sport is None:
            continue

        if sport not in summary:
            summary[sport] = {
                "distance_km": 0.0,
                "time_hours": 0.0,
                "count": 0,
                "calories": 0,
                "pr_count": 0,
            }

        # Strava returns distance in metres
        dist_m = act.get("distance", 0) or 0
        summary[sport]["distance_km"] += dist_m / 1000.0

        # Strava returns moving_time in seconds
        moving_s = act.get("moving_time", 0) or 0
        summary[sport]["time_hours"] += moving_s / 3600.0

        summary[sport]["count"] += 1
        summary[sport]["calories"] += act.get("calories", 0) or 0
        summary[sport]["pr_count"] += act.get("pr_count", 0) or 0

    # Round floats for display
    for sport_data in summary.values():
        sport_data["distance_km"] = round(sport_data["distance_km"], 1)
        sport_data["time_hours"] = round(sport_data["time_hours"], 1)
        sport_data["calories"] = round(sport_data["calories"], 0)

    return summary


def _compute_weekly_summary(activities: list[dict]) -> dict:
    """Per-sport totals for the current Mon-Sun week."""
    monday, sunday = _week_range()
    summary: dict[str, dict] = {}

    for act in activities:
        sport = _normalise_sport(act.get("sport_type", ""))
        if sport is None:
            continue

        try:
            act_date = _parse_date(act.get("start_date_local", ""))
        except (ValueError, TypeError):
            continue

        if not (monday <= act_date <= sunday):
            continue

        if sport not in summary:
            summary[sport] = {"distance_km": 0.0, "time_hours": 0.0, "count": 0}

        dist_m = act.get("distance", 0) or 0
        summary[sport]["distance_km"] += dist_m / 1000.0

        moving_s = act.get("moving_time", 0) or 0
        summary[sport]["time_hours"] += moving_s / 3600.0

        summary[sport]["count"] += 1

    for sport_data in summary.values():
        sport_data["distance_km"] = round(sport_data["distance_km"], 1)
        sport_data["time_hours"] = round(sport_data["time_hours"], 1)

    return summary


def _compute_weekly_goals(
    weekly_summary: dict, weekly_goals_config: dict
) -> list[dict]:
    """Compute completion % for each weekly goal defined in config."""
    results = []

    for goal in weekly_goals_config:
        sport = goal.get("sport", "")
        metric = goal.get("metric", "")
        target = goal.get("target", 0)
        label = goal.get("label", f"{sport} {metric}")

        if target <= 0:
            results.append({"label": label, "target": target, "current": 0, "pct": 0})
            continue

        current = 0.0
        sport_data = weekly_summary.get(sport, {})

        if metric == "distance_km":
            current = sport_data.get("distance_km", 0)
        elif metric == "time_hours":
            current = sport_data.get("time_hours", 0)
        elif metric == "count":
            current = sport_data.get("count", 0)

        pct = min(round(current / target * 100, 1), 100.0) if target else 0
        results.append({
            "label": label,
            "target": target,
            "current": round(current, 1),
            "pct": pct,
        })

    return results


def _compute_annual_goals(
    annual_summary: dict, annual_goals_config: dict
) -> list[dict]:
    """Compute completion % for each annual goal defined in config."""
    results = []

    for goal in annual_goals_config:
        sport = goal.get("sport", "")
        metric = goal.get("metric", "")
        target = goal.get("target", 0)
        label = goal.get("label", f"{sport} {metric}")

        if target <= 0:
            results.append({"label": label, "target": target, "current": 0, "pct": 0})
            continue

        current = 0.0
        sport_data = annual_summary.get(sport, {})

        if metric == "distance_km":
            current = sport_data.get("distance_km", 0)
        elif metric == "time_hours":
            current = sport_data.get("time_hours", 0)
        elif metric == "count":
            current = sport_data.get("count", 0)
        elif metric == "calories":
            current = sport_data.get("calories", 0)
        elif metric == "pr_count":
            current = sport_data.get("pr_count", 0)

        pct = min(round(current / target * 100, 1), 100.0) if target else 0
        results.append({
            "label": label,
            "target": target,
            "current": round(current, 1),
            "pct": pct,
        })

    return results


def _expand_goals_config(goals_dict: dict, period: str = "annual") -> list[dict]:
    """Convert flat goal config (e.g. {run_km: 800}) to list-of-dicts format.

    The config.yaml uses a flat dict: goals.annual.run_km: 800
    The computation functions expect a list of dicts:
        [{sport: "run", metric: "distance_km", target: 800, label: "Run Distance"}]
    """
    mapping = [
        ("ride_km", "ride", "distance_km", "Ride Distance"),
        ("run_km", "run", "distance_km", "Run Distance"),
        ("swim_km", "swim", "distance_km", "Swim Distance"),
        ("workout_count", "workout", "count", "Workouts"),
    ]
    results = []
    for key, sport, metric, label in mapping:
        if key in goals_dict:
            results.append({
                "sport": sport,
                "metric": metric,
                "target": goals_dict[key],
                "label": label,
            })
    return results


def _compute_monthly_trend(activities: list[dict]) -> dict:
    """Per-month (1 to current month), per-sport breakdown: distance, time, count."""
    trend: dict[int, dict[str, dict]] = {}

    # Dynamically compute months up to current month of reference year
    today = date.today()
    if today.year == REFERENCE_YEAR:
        max_month = today.month
    else:
        max_month = 12
    for m in range(1, max_month + 1):
        trend[m] = {}

    for act in activities:
        sport = _normalise_sport(act.get("sport_type", ""))
        if sport is None:
            continue

        try:
            act_date = _parse_date(act.get("start_date_local", ""))
        except (ValueError, TypeError):
            continue

        if act_date.year != REFERENCE_YEAR:
            continue

        month = act_date.month
        if month not in trend:
            continue

        if sport not in trend[month]:
            trend[month][sport] = {"distance_km": 0.0, "time_hours": 0.0, "count": 0}

        dist_m = act.get("distance", 0) or 0
        trend[month][sport]["distance_km"] += dist_m / 1000.0

        moving_s = act.get("moving_time", 0) or 0
        trend[month][sport]["time_hours"] += moving_s / 3600.0

        trend[month][sport]["count"] += 1

    # Round values
    for month_data in trend.values():
        for sport_data in month_data.values():
            sport_data["distance_km"] = round(sport_data["distance_km"], 1)
            sport_data["time_hours"] = round(sport_data["time_hours"], 1)

    return trend


def _compute_key_metrics(activities: list[dict], zones: dict) -> dict:
    """Current FTP, 5K best, half-marathon best, total PRs (ride + run)."""
    metrics: dict = {
        "ftp": None,
        "best_5k_time": None,
        "best_half_marathon_time": None,
        "total_prs": 0,
    }

    # --- FTP from zones ---
    # zones.json may store FTP under various keys; handle common shapes
    ftp_val = zones.get("ftp") or zones.get("FTP")
    if ftp_val is not None:
        try:
            metrics["ftp"] = int(ftp_val)
        except (ValueError, TypeError):
            pass

    # If FTP is nested inside a cycling zone block
    if metrics["ftp"] is None:
        cycling_zones = zones.get("power_zones") or zones.get("cycling") or {}
        ftp_val = cycling_zones.get("ftp") or cycling_zones.get("FTP")
        if ftp_val is not None:
            try:
                metrics["ftp"] = int(ftp_val)
            except (ValueError, TypeError):
                pass

    # --- Best times & total PRs from activities ---
    for act in activities:
        sport = _normalise_sport(act.get("sport_type", ""))

        # Accumulate PRs for ride and run only
        if sport in ("ride", "run"):
            metrics["total_prs"] += act.get("pr_count", 0) or 0

        # 5K best: look for activities around 5 km distance
        if sport == "run":
            dist_m = act.get("distance", 0) or 0
            dist_km = dist_m / 1000.0

            # 5K: accept 4.8-5.2 km as a valid 5K effort
            if 4.8 <= dist_km <= 5.2:
                elapsed = act.get("moving_time", 0) or 0
                if elapsed > 0:
                    if metrics["best_5k_time"] is None or elapsed < metrics["best_5k_time"]:
                        metrics["best_5k_time"] = elapsed

            # Half marathon: accept 21.0-21.3 km
            if 21.0 <= dist_km <= 21.3:
                elapsed = act.get("moving_time", 0) or 0
                if elapsed > 0:
                    if metrics["best_half_marathon_time"] is None or elapsed < metrics["best_half_marathon_time"]:
                        metrics["best_half_marathon_time"] = elapsed

    return metrics


def _compute_weekly_trend(activities: list[dict], num_weeks: int = 8) -> list[dict]:
    """Per-week, per-sport distance for the last N weeks.

    Returns a list of dicts, each with:
        week_num, start_date (str), per-sport {distance_km, time_hours, count}
    Sorted most recent week first.
    """
    today = date.today()
    # Find the Monday of the current week
    current_monday = today - timedelta(days=today.weekday())

    # Build week boundaries (most recent first)
    weeks = []
    for i in range(num_weeks):
        monday = current_monday - timedelta(weeks=i)
        sunday = monday + timedelta(days=6)
        iso_week = monday.isocalendar()[1]
        weeks.append({
            "week_num": iso_week,
            "start_date": monday.isoformat(),
            "end_date": sunday.isoformat(),
            "monday": monday,
            "sunday": sunday,
            "sports": {},
        })

    # Aggregate activities into weeks
    for act in activities:
        sport = _normalise_sport(act.get("sport_type", ""))
        if sport is None or sport not in DISTANCE_SPORTS:
            continue

        try:
            act_date = _parse_date(act.get("start_date_local", ""))
        except (ValueError, TypeError):
            continue

        for week in weeks:
            if week["monday"] <= act_date <= week["sunday"]:
                if sport not in week["sports"]:
                    week["sports"][sport] = {"distance_km": 0.0, "time_hours": 0.0, "count": 0}

                dist_m = act.get("distance", 0) or 0
                week["sports"][sport]["distance_km"] += dist_m / 1000.0

                moving_s = act.get("moving_time", 0) or 0
                week["sports"][sport]["time_hours"] += moving_s / 3600.0

                week["sports"][sport]["count"] += 1
                break

    # Round and format output
    result = []
    for week in weeks:
        sports_data = {}
        for sport_key, sport_val in week["sports"].items():
            sports_data[sport_key] = {
                "distance_km": round(sport_val["distance_km"], 1),
                "time_hours": round(sport_val["time_hours"], 1),
                "count": sport_val["count"],
            }
        result.append({
            "week_num": week["week_num"],
            "start_date": week["start_date"],
            "sports": sports_data,
        })

    return result


def _compute_recent_activities(activities: list[dict], limit: int = 7) -> list[dict]:
    """Return the N most recent activities with formatted fields.

    Each entry has: id, name, sport_type, sport_icon, distance_km,
    date_short, moving_time_min.
    """
    # Sort by start_date_local descending
    sorted_acts = sorted(
        activities,
        key=lambda a: a.get("start_date_local", ""),
        reverse=True,
    )

    sport_icons = {
        "Run": "[R]", "TrailRun": "[R]",
        "Ride": "[B]", "VirtualRide": "[B]",
        "Swim": "[S]",
        "WeightTraining": "[W]", "Workout": "[W]",
    }

    result = []
    for act in sorted_acts[:limit]:
        sport_type = act.get("sport_type", "")
        dist_m = act.get("distance", 0) or 0
        moving_s = act.get("moving_time", 0) or 0

        # Format date as "M/D"
        try:
            act_date = _parse_date(act.get("start_date_local", ""))
            date_short = f"{act_date.month}/{act_date.day}"
        except (ValueError, TypeError):
            date_short = ""

        result.append({
            "id": act.get("id"),
            "name": act.get("name", ""),
            "sport_type": sport_type,
            "sport_icon": sport_icons.get(sport_type, "[?]"),
            "distance_km": round(dist_m / 1000.0, 1),
            "date_short": date_short,
            "moving_time_min": round(moving_s / 60.0, 0),
        })

    return result


def _compute_races(races_config: list[dict]) -> dict:
    """Split races into upcoming (with countdown days) and past (with results)."""
    today = date.today()
    upcoming = []
    past = []

    for race in races_config:
        race_date_str = race.get("date", "")
        try:
            race_date = _parse_date(race_date_str)
        except (ValueError, TypeError):
            continue

        entry = {
            "name": race.get("name", ""),
            "date": race_date.isoformat(),
            "distance_km": race.get("distance_km"),
            "sport": race.get("sport", ""),
        }

        if race_date >= today:
            entry["countdown_days"] = (race_date - today).days
            upcoming.append(entry)
        else:
            entry["result"] = race.get("result")
            entry["time"] = race.get("time")
            past.append(entry)

    # Sort upcoming by soonest first, past by most recent first
    upcoming.sort(key=lambda r: r["date"])
    past.sort(key=lambda r: r["date"], reverse=True)

    return {"upcoming": upcoming, "past": past}


def _compute_streak(activities: list[dict]) -> int:
    """Current consecutive-day activity streak ending on today.

    A streak counts backwards from today (or the most recent activity day
    if today has no activity yet). Each day with at least one activity
    extends the streak.
    """
    if not activities:
        return 0

    # Collect all dates that had an activity
    active_dates: set[date] = set()
    for act in activities:
        try:
            act_date = _parse_date(act.get("start_date_local", ""))
            active_dates.add(act_date)
        except (ValueError, TypeError):
            continue

    if not active_dates:
        return 0

    # Start from today; if today has no activity, start from the most
    # recent active day (grace window: allow the streak to include
    # yesterday if today is still early).
    today = date.today()
    check_date = today

    if today not in active_dates:
        # Allow the streak to continue if the most recent activity was
        # yesterday (the day may not be over yet)
        yesterday = today - timedelta(days=1)
        if yesterday in active_dates:
            check_date = yesterday
        else:
            return 0

    # Count backwards
    streak = 0
    while check_date in active_dates:
        streak += 1
        check_date -= timedelta(days=1)

    return streak


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def process_data(data_dir: str = "data", config_path: str = "config.yaml") -> dict:
    """Load raw data, compute all dashboard metrics, and return a result dict.

    Parameters
    ----------
    data_dir : str
        Directory containing activities_2026.json and zones.json.
    config_path : str
        Path to the config.yaml file with goals, races, and manual data.

    Returns
    -------
    dict
        A dictionary with keys: annual_summary, weekly_summary,
        weekly_goals, annual_goals, monthly_trend, key_metrics,
        races, streak, last_updated.
    """
    # ---- Load raw data ----
    activities_path = f"{data_dir}/activities_2026.json"
    zones_path = f"{data_dir}/zones.json"

    raw_activities: list = _load_json(activities_path)
    if not isinstance(raw_activities, list):
        raw_activities = []

    raw_zones: dict = _load_json(zones_path)
    if not isinstance(raw_zones, dict):
        raw_zones = {}

    config: dict = _load_yaml(config_path)

    # ---- Filter activities to the reference year only ----
    filtered_activities: list[dict] = []
    for act in raw_activities:
        try:
            act_date = _parse_date(act.get("start_date_local", ""))
            if act_date.year == REFERENCE_YEAR:
                filtered_activities.append(act)
        except (ValueError, TypeError):
            # If we cannot parse the date, include the activity anyway
            # so we do not silently drop data with malformed timestamps.
            filtered_activities.append(act)

    # ---- Extract config sections ----
    # Expand flat goal config into list format if not already provided
    annual_goals_cfg = config.get("annual_goals", [])
    if not annual_goals_cfg:
        annual_goals_cfg = _expand_goals_config(
            config.get("goals", {}).get("annual", {}), period="annual"
        )

    weekly_goals_cfg = config.get("weekly_goals", [])
    if not weekly_goals_cfg:
        weekly_goals_cfg = _expand_goals_config(
            config.get("goals", {}).get("weekly", {}), period="weekly"
        )

    races_cfg = config.get("races", [])
    manual_data = config.get("manual_data", {})

    # Merge manual data into zones (e.g. hand-entered FTP)
    if isinstance(manual_data, dict):
        for key, value in manual_data.items():
            if key not in raw_zones:
                raw_zones[key] = value

    # ---- Compute all metrics ----
    annual_summary = _compute_annual_summary(filtered_activities)
    weekly_summary = _compute_weekly_summary(filtered_activities)
    weekly_goals = _compute_weekly_goals(weekly_summary, weekly_goals_cfg)
    annual_goals = _compute_annual_goals(annual_summary, annual_goals_cfg)
    monthly_trend = _compute_monthly_trend(filtered_activities)
    key_metrics = _compute_key_metrics(filtered_activities, raw_zones)
    races = _compute_races(races_cfg)
    streak = _compute_streak(filtered_activities)
    weekly_trend = _compute_weekly_trend(filtered_activities, num_weeks=8)
    recent_activities = _compute_recent_activities(filtered_activities, limit=7)

    return {
        "annual_summary": annual_summary,
        "weekly_summary": weekly_summary,
        "weekly_goals": weekly_goals,
        "annual_goals": annual_goals,
        "monthly_trend": monthly_trend,
        "key_metrics": key_metrics,
        "races": races,
        "streak": streak,
        "weekly_trend": weekly_trend,
        "recent_activities": recent_activities,
        "last_updated": datetime.now().isoformat(),
    }
