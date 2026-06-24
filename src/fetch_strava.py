#!/usr/bin/env python3
"""
Dump Strava data to JSON files using the REST API.
For development, you can also manually paste MCP data here.

Usage:
  # Production: use Strava OAuth tokens
  python dump_strava.py --client-id ID --client-secret SECRET --refresh-token TOKEN

  # Development: use pre-existing access token (expires in 6h)
  python dump_strava.py --access-token TOKEN
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


def fetch_activities(access_token, year=2026):
    """Fetch all activities for a given year."""
    headers = {"Authorization": f"Bearer {access_token}"}
    all_activities = []
    page = 1

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


def main():
    parser = argparse.ArgumentParser(description="Dump Strava data to JSON")
    parser.add_argument("--access-token", help="Strava access token")
    parser.add_argument("--client-id", help="Strava API client ID")
    parser.add_argument("--client-secret", help="Strava API client secret")
    parser.add_argument("--refresh-token", help="Strava refresh token")
    parser.add_argument("--year", type=int, default=2026, help="Year to fetch")
    parser.add_argument("--output-dir", default="data", help="Output directory")
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

    # Fetch data
    print(f"Fetching activities for {args.year}...")
    raw_activities = fetch_activities(access_token, args.year)
    activities = [normalize_activity(a) for a in raw_activities]
    print(f"  Total: {len(activities)} activities")

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
    activities_path = os.path.join(args.output_dir, f"activities_{args.year}.json")
    with open(activities_path, "w", encoding="utf-8") as f:
        json.dump(activities, f, indent=2, ensure_ascii=False)
    print(f"Saved: {activities_path}")

    with open(os.path.join(args.output_dir, "zones.json"), "w", encoding="utf-8") as f:
        json.dump(zones, f, indent=2, ensure_ascii=False)
    print("Saved: zones.json")

    with open(os.path.join(args.output_dir, "profile.json"), "w", encoding="utf-8") as f:
        json.dump(profile, f, indent=2, ensure_ascii=False)
    print("Saved: profile.json")

    if new_refresh_token:
        with open(os.path.join(args.output_dir, "new_refresh_token.txt"), "w") as f:
            f.write(new_refresh_token)
        print(f"Saved: new_refresh_token.txt (update your secrets!)")


if __name__ == "__main__":
    main()
