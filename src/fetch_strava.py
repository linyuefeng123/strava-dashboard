#!/usr/bin/env python3
"""
Dump Strava data to JSON files using the REST API.
Supports incremental updates via --since or auto-detect from last_fetch.json.

Usage:
  # Production: use Strava OAuth tokens
  python fetch_strava.py --client-id ID --client-secret SECRET --refresh-token TOKEN

  # Development: use pre-existing access token (expires in 6h)
  python fetch_strava.py --access-token TOKEN

  # Incremental: fetch only activities after a given date
  python fetch_strava.py --access-token TOKEN --since 2026-06-20

  # Full: force full year fetch (ignore last_fetch.json)
  python fetch_strava.py --access-token TOKEN --full
"""

import argparse
import json
import os
import sys
import requests
from datetime import datetime

STRAVA_API_BASE = "https://www.strava.com/api/v3"


def refresh_token(client_id, client_secret, refresh_token_val):
    """Refresh Strava access token using refresh_token."""
    resp = requests.post(f"{STRAVA_API_BASE}/oauth/token", data={
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token_val,
        "grant_type": "refresh_token",
    })
    resp.raise_for_status()
    data = resp.json()
    return data["access_token"], data["refresh_token"]


def fetch_activities(access_token, year=2026, since=None):
    """Fetch activities for a given year, optionally only after a given date.

    Args:
        access_token: Strava API access token.
        year: Year to fetch activities for.
        since: Optional ISO date string (e.g. '2026-06-20') to fetch only
               activities after this date. If None, fetches full year.

    Returns:
        List of raw activity dicts from Strava API.
    """
    headers = {"Authorization": f"Bearer {access_token}"}
    all_activities = []
    page = 1

    if since:
        after_ts = int(datetime.fromisoformat(since).timestamp())
        print(f"  Incremental fetch: activities after {since}")
    else:
        after_ts = int(datetime(year, 1, 1).timestamp())

    before_ts = int(datetime(year + 1, 1, 1).timestamp())

    while True:
        resp = requests.get(f"{STRAVA_API_BASE}/athlete/activities", headers=headers, params={
            "after": after_ts,
            "before": before_ts,
            "per_page": 200,
            "page": page,
        })
        resp.raise_for_status()
        activities = resp.json()
        if not activities:
            break
        all_activities.extend(activities)
        print(f"  Page {page}: {len(activities)} activities (total: {len(all_activities)})")
        if len(activities) < 200:
            break
        page += 1

    return all_activities


def fetch_zones(access_token):
    """Fetch athlete zones (FTP, HR zones, power zones, run zones)."""
    headers = {"Authorization": f"Bearer {access_token}"}
    resp = requests.get(f"{STRAVA_API_BASE}/athlete/zones", headers=headers)
    resp.raise_for_status()
    return resp.json()


def fetch_profile(access_token):
    """Fetch athlete profile."""
    headers = {"Authorization": f"Bearer {access_token}"}
    resp = requests.get(f"{STRAVA_API_BASE}/athlete", headers=headers)
    resp.raise_for_status()
    return resp.json()


def normalize_activity(act):
    """Normalize Strava activity to our internal format (strip verbose descriptions)."""
    # Truncate weather descriptions - they're huge and not needed for dashboard
    desc = act.get("description", "") or ""
    if len(desc) > 100:
        desc = desc[:100] + "..."

    return {
        "id": act["id"],
        "name": act.get("name", ""),
        "description": desc,
        "sport_type": act.get("sport_type", act.get("type", "")),
        "start_date_local": act.get("start_date_local", ""),
        "distance": act.get("distance", 0),  # meters
        "moving_time": act.get("moving_time", 0),  # seconds
        "elapsed_time": act.get("elapsed_time", 0),
        "total_elevation_gain": act.get("total_elevation_gain", 0),
        "average_speed": act.get("average_speed", 0),  # m/s
        "max_speed": act.get("max_speed", 0),
        "average_heartrate": act.get("average_heartrate"),
        "max_heartrate": act.get("max_heartrate"),
        "average_watts": act.get("average_watts"),
        "average_cadence": act.get("average_cadence"),
        "kilojoules": act.get("kilojoules"),
        "suffer_score": act.get("suffer_score"),
        "relative_effort": act.get("relative_effort"),
        "calories": act.get("calories", 0),
        "achievement_count": act.get("achievement_count", 0),
        "pr_count": act.get("pr_count", 0),
        "kudos_count": act.get("kudos_count", 0),
        "gear_id": act.get("gear_id"),
    }


def merge_activities(existing: list, new: list) -> list:
    """Merge new activities into existing list by activity ID.

    - New activities with existing IDs replace the old ones (updated data).
    - New activities with new IDs are appended.
    - Existing activities not in the new fetch are kept.
    - Result is sorted by start_date_local descending.
    """
    existing_by_id = {act["id"]: act for act in existing}
    new_by_id = {act["id"]: act for act in new}

    # Merge: new data overwrites existing for same ID
    merged = {}
    for act_id, act in existing_by_id.items():
        merged[act_id] = act
    for act_id, act in new_by_id.items():
        merged[act_id] = act

    # Sort by start_date_local descending
    result = sorted(
        merged.values(),
        key=lambda a: a.get("start_date_local", ""),
        reverse=True,
    )
    return result


def load_last_fetch(data_dir: str) -> str | None:
    """Load the last fetch timestamp from data/last_fetch.json.

    Returns the ISO date string of the last fetch, or None if not found.
    """
    path = os.path.join(data_dir, "last_fetch.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("last_fetch")
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def save_last_fetch(data_dir: str, timestamp: str, count: int, year: int):
    """Save the last fetch timestamp to data/last_fetch.json."""
    path = os.path.join(data_dir, "last_fetch.json")
    data = {
        "last_fetch": timestamp,
        "activity_count": count,
        "year": year,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    print(f"Saved: last_fetch.json (last_fetch={timestamp}, count={count})")


def main():
    parser = argparse.ArgumentParser(description="Dump Strava data to JSON")
    parser.add_argument("--access-token", help="Strava access token")
    parser.add_argument("--client-id", help="Strava API client ID")
    parser.add_argument("--client-secret", help="Strava API client secret")
    parser.add_argument("--refresh-token", help="Strava refresh token")
    parser.add_argument("--year", type=int, default=2026, help="Year to fetch")
    parser.add_argument("--output-dir", default="data", help="Output directory")
    parser.add_argument("--since", help="Fetch only activities after this date (ISO format, e.g. 2026-06-20)")
    parser.add_argument("--full", action="store_true", help="Force full year fetch (ignore last_fetch.json)")
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)

    # Get access token
    if args.access_token:
        access_token = args.access_token
        new_refresh_token = None
    elif args.client_id and args.client_secret and args.refresh_token:
        print("Refreshing Strava token...")
        access_token, new_refresh_token = refresh_token(
            args.client_id, args.client_secret, args.refresh_token
        )
        print(f"  New refresh_token: {new_refresh_token[:20]}...")
    else:
        print("Error: Provide --access-token or --client-id + --client-secret + --refresh-token")
        sys.exit(1)

    # Determine incremental vs full fetch
    since = args.since
    if not since and not args.full:
        # Auto-detect: use last_fetch timestamp if available
        last_fetch = load_last_fetch(args.output_dir)
        if last_fetch:
            since = last_fetch
            print(f"Auto-detected incremental mode: fetching after {since}")

    # Load existing activities for merge
    activities_path = os.path.join(args.output_dir, f"activities_{args.year}.json")
    existing_activities = []
    if os.path.exists(activities_path):
        try:
            with open(activities_path, "r", encoding="utf-8") as f:
                existing_activities = json.load(f)
            if not isinstance(existing_activities, list):
                existing_activities = []
            print(f"Loaded {len(existing_activities)} existing activities")
        except json.JSONDecodeError:
            existing_activities = []

    # Fetch data
    if since:
        print(f"Fetching activities for {args.year} after {since}...")
    else:
        print(f"Fetching all activities for {args.year}...")

    raw_activities = fetch_activities(access_token, args.year, since=since)
    new_activities = [normalize_activity(a) for a in raw_activities]
    print(f"  Fetched: {len(new_activities)} activities")

    # Merge with existing
    if existing_activities and new_activities:
        merged = merge_activities(existing_activities, new_activities)
        print(f"  Merged: {len(merged)} total activities ({len(new_activities)} new/updated)")
    elif existing_activities:
        merged = existing_activities
    else:
        merged = new_activities

    print(f"  Total activities: {len(merged)}")

    # Fetch zones and profile (always full)
    print("Fetching zones...")
    try:
        zones = fetch_zones(access_token)
    except Exception as e:
        print(f"  Warning: Could not fetch zones: {e}")
        zones = {}

    print("Fetching profile...")
    try:
        profile = fetch_profile(access_token)
    except Exception as e:
        print(f"  Warning: Could not fetch profile: {e}")
        profile = {}

    # Save
    with open(activities_path, "w", encoding="utf-8") as f:
        json.dump(merged, f, indent=2, ensure_ascii=False)
    print(f"Saved: {activities_path}")

    with open(os.path.join(args.output_dir, "zones.json"), "w", encoding="utf-8") as f:
        json.dump(zones, f, indent=2, ensure_ascii=False)
    print("Saved: zones.json")

    with open(os.path.join(args.output_dir, "profile.json"), "w", encoding="utf-8") as f:
        json.dump(profile, f, indent=2, ensure_ascii=False)
    print("Saved: profile.json")

    # Save last_fetch timestamp
    now_str = datetime.now().isoformat()
    save_last_fetch(args.output_dir, now_str, len(merged), args.year)

    if new_refresh_token:
        with open(os.path.join(args.output_dir, "new_refresh_token.txt"), "w") as f:
            f.write(new_refresh_token)
        print(f"Saved: new_refresh_token.txt (update your secrets!)")


if __name__ == "__main__":
    main()
