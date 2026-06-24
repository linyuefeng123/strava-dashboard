#!/usr/bin/env python3
"""
Convert Strava MCP activity format to our internal format.
Run this when you have fresh MCP data to save as the activities JSON.

Usage:
  1. Use Claude Code MCP tools to fetch activities
  2. Save the raw JSON response to data/raw_mcp_activities.json
  3. Run: python src/convert_mcp_data.py

The MCP format uses:
  - "start_local" instead of "start_date_local"
  - "summary.distance" instead of top-level "distance"
  - "summary.moving_time" instead of top-level "moving_time"
  - etc.
"""

import json
import os
import sys


def convert_mcp_activity(act):
    """Convert a single MCP-format activity to our internal format."""
    s = act.get("summary", {})
    return {
        "id": act.get("id", ""),
        "name": act.get("name", ""),
        "sport_type": act.get("sport_type", ""),
        "start_date_local": act.get("start_local", ""),
        "distance": s.get("distance", 0),
        "moving_time": s.get("moving_time", 0),
        "elapsed_time": s.get("elapsed_time", 0),
        "total_elevation_gain": s.get("elevation_gain", 0),
        "average_speed": s.get("avg_speed", 0),
        "max_speed": s.get("max_speed", 0),
        "average_heartrate": None,
        "max_heartrate": None,
        "average_watts": None,
        "average_cadence": s.get("avg_cadence"),
        "calories": s.get("total_calories", 0),
        "relative_effort": s.get("relative_effort"),
        "achievement_count": s.get("achievement_count", 0),
        "pr_count": s.get("pr_count", 0),
        "kudos_count": s.get("kudos_count", 0),
    }


def main():
    data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
    raw_path = os.path.join(data_dir, "raw_mcp_activities.json")
    out_path = os.path.join(data_dir, "activities_2026.json")

    if not os.path.exists(raw_path):
        print(f"Error: {raw_path} not found")
        print("Save your MCP activity data to data/raw_mcp_activities.json first")
        sys.exit(1)

    with open(raw_path, "r", encoding="utf-8") as f:
        raw_data = json.load(f)

    # Handle both formats:
    # 1. Direct list of activities
    # 2. Dict with "activities" key (MCP list_activities response)
    if isinstance(raw_data, dict) and "activities" in raw_data:
        activities = raw_data["activities"]
    elif isinstance(raw_data, list):
        activities = raw_data
    else:
        print(f"Error: unexpected format in {raw_path}")
        sys.exit(1)

    converted = [convert_mcp_activity(a) for a in activities]
    print(f"Converted {len(converted)} activities")

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(converted, f, indent=2, ensure_ascii=False)
    print(f"Saved to {out_path}")


if __name__ == "__main__":
    main()
