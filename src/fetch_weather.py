#!/usr/bin/env python3
"""
Fetch weather data from Open-Meteo API for Shanghai.

Outputs data/weather.json with current conditions and 3-day forecast.
No API key required.
"""

import json
import os
import sys
from datetime import datetime

import requests


# ---------------------------------------------------------------------------
# WMO Weather Code mapping
# ---------------------------------------------------------------------------

WMO_CODES = {
    0: ("晴", "*"),
    1: ("大部晴", "*"),
    2: ("多云", "~"),
    3: ("阴", "~"),
    45: ("雾", "="),
    48: ("冻雾", "="),
    51: ("小毛雨", "."),
    53: ("毛雨", "."),
    55: ("大毛雨", "."),
    56: ("冻毛雨", "."),
    57: ("冻毛雨", "."),
    61: ("小雨", "."),
    63: ("中雨", "|"),
    65: ("大雨", "|"),
    66: ("冻雨", "|"),
    67: ("大冻雨", "|"),
    71: ("小雪", "+"),
    73: ("中雪", "+"),
    75: ("大雪", "+"),
    77: ("雪粒", "+"),
    80: ("小阵雨", "."),
    81: ("阵雨", "|"),
    82: ("大阵雨", "|"),
    85: ("小阵雪", "+"),
    86: ("大阵雪", "+"),
    95: ("雷暴", "!"),
    96: ("雷暴+冰雹", "!"),
    99: ("强雷暴+冰雹", "!"),
}


def _weather_desc(code: int) -> str:
    """Return Chinese description for a WMO weather code."""
    return WMO_CODES.get(code, ("未知", "?"))[0]


def _weather_icon(code: int) -> str:
    """Return ASCII icon for a WMO weather code."""
    return WMO_CODES.get(code, ("未知", "?"))[1]


# ---------------------------------------------------------------------------
# Fetch weather
# ---------------------------------------------------------------------------

def fetch_weather(
    latitude: float = 31.23,
    longitude: float = 121.47,
    timezone: str = "Asia/Shanghai",
    output_path: str = "data/weather.json",
) -> dict:
    """Fetch current weather and 3-day forecast from Open-Meteo.

    Args:
        latitude: Location latitude (default: Shanghai).
        longitude: Location longitude.
        timezone: Timezone string.
        output_path: Path to write the output JSON.

    Returns:
        The weather data dict.
    """
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "current": "temperature_2m,weather_code",
        "daily": "weather_code,temperature_2m_max,temperature_2m_min",
        "timezone": timezone,
        "forecast_days": 4,  # today + 3 days
    }

    try:
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
        raw = resp.json()
    except (requests.RequestException, json.JSONDecodeError) as e:
        print(f"Weather fetch failed: {e}", file=sys.stderr)
        # Return empty data on failure
        result = {
            "current": None,
            "forecast": [],
            "fetched_at": datetime.now().isoformat(),
            "error": str(e),
        }
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        return result

    # Parse current weather
    current_raw = raw.get("current", {})
    current_code = current_raw.get("weather_code", 0)
    current = {
        "temperature": round(current_raw.get("temperature_2m", 0)),
        "weather_code": current_code,
        "description": _weather_desc(current_code),
        "icon": _weather_icon(current_code),
    }

    # Parse forecast (skip today, take next 3 days)
    daily = raw.get("daily", {})
    forecast = []
    dates = daily.get("time", [])
    codes = daily.get("weather_code", [])
    highs = daily.get("temperature_2m_max", [])
    lows = daily.get("temperature_2m_min", [])

    for i in range(len(dates)):
        # Skip today (index 0), take next 3 days
        if i == 0:
            continue
        if i > 3:
            break

        code = codes[i] if i < len(codes) else 0
        high = round(highs[i]) if i < len(highs) else 0
        low = round(lows[i]) if i < len(lows) else 0

        # Day label: 明天, 后天, 大后天
        day_labels = ["明天", "后天", "大后天"]
        day_label = day_labels[i - 1] if i - 1 < len(day_labels) else dates[i]

        forecast.append({
            "date": dates[i],
            "day_label": day_label,
            "high": high,
            "low": low,
            "weather_code": code,
            "description": _weather_desc(code),
            "icon": _weather_icon(code),
        })

    result = {
        "current": current,
        "forecast": forecast,
        "fetched_at": datetime.now().isoformat(),
    }

    # Write output
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    print(f"Weather data saved: {output_path}")
    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Fetch weather from Open-Meteo")
    parser.add_argument("--lat", type=float, default=31.23, help="Latitude")
    parser.add_argument("--lon", type=float, default=121.47, help="Longitude")
    parser.add_argument("--output", default="data/weather.json", help="Output path")
    args = parser.parse_args()

    fetch_weather(
        latitude=args.lat,
        longitude=args.lon,
        output_path=args.output,
    )
