#!/usr/bin/env python3
"""
Render an e-ink friendly "screensaver" lock-screen page for the Strava dashboard.

This is the missing step referenced by .github/workflows/daily-build.yml and
.gitignore (output/screensaver.png/.html are force-tracked). It produces:

  output/screensaver.html  — a 758x1024 Kindle-Paperwhite-friendly lock screen
  output/screensaver.png   — the same page rasterised to PNG (via Playwright)

The page shows the key "at a glance" info for a wall/e-ink display:
date + lunar, streak, today's training, weekly goal progress, next race.
Falls back to existing data files; renders even if some are missing.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import date

# Make `src` importable when run from repo root (workflow does `python src/...`)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


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


def _lunar_for_today() -> str:
    """Return a lunar date string for today, or empty string on failure."""
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
        from src.lunar import solar_to_lunar

        return solar_to_lunar(date.today()).get("date_cn", "")
    except Exception:
        return ""


def _fmt_km(meters: float) -> str:
    if meters is None:
        return "0.0"
    return f"{meters / 1000:.1f}"


def _fmt_pct(value: float, total: float) -> int:
    if total is None or total <= 0:
        return 0
    return min(100, max(0, int(round(value / total * 100))))


def render_screensaver(
    data_dir: str = "data",
    config_path: str = "config.yaml",
    output_dir: str = "output",
) -> str:
    """Render the screensaver HTML page, return the HTML string."""
    data = _load_json_safe(os.path.join(data_dir, "processed.json"))
    config = _load_yaml_safe(config_path)

    today = date.today()
    weekday_cn = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]

    # --- Lunar date ---
    lunar = _lunar_for_today()

    # --- Streak ---
    streak = data.get("streak", 0)

    # --- Today's training from training_plan.json ---
    training_plan_data = _load_json_safe(os.path.join(data_dir, "training_plan.json"))
    today_desc = "今日休息 / 轻度活动"
    if isinstance(training_plan_data, dict) and "plan" in training_plan_data:
        plan_dict = training_plan_data["plan"]
        today_cn = weekday_cn[today.weekday()]
        if today_cn in plan_dict:
            today_desc = plan_dict[today_cn]
    elif isinstance(training_plan_data, list):
        today_short = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][today.weekday()]
        for item in training_plan_data:
            if isinstance(item, dict) and item.get("day") == today_short:
                today_desc = item.get("description", today_desc)
                break

    # --- Weekly goal progress ---
    weekly = data.get("weekly_summary", {})
    goals_config = config.get("goals", {}).get("weekly", {})
    weekly_items = [
        ("骑行", "[B]", _fmt_km(weekly.get("ride", {}).get("distance_km", 0)),
         float(goals_config.get("ride_km", 100))),
        ("跑步", "[R]", _fmt_km(weekly.get("run", {}).get("distance_km", 0)),
         float(goals_config.get("run_km", 20))),
        ("力量", "[W]", f"{weekly.get('workout', {}).get('count', 0)} 次",
         float(goals_config.get("workout_count", 2))),
    ]
    weekly_goals = []
    for label, icon, current_disp, target in weekly_items:
        # Parse current numeric value from display string
        try:
            current_num = float(current_disp.split()[0])
        except ValueError:
            current_num = 0.0
        weekly_goals.append({
            "label": label,
            "icon": icon,
            "current": current_disp,
            "target": f"{target:.0f}" if target >= 10 or target == int(target) else f"{target:g}",
            "pct": _fmt_pct(current_num, target),
        })

    # --- Next race ---
    next_race_html = ""
    upcoming = data.get("races", {}).get("upcoming", [])
    for race in upcoming:
        race_date_str = race.get("date", "")
        try:
            from datetime import datetime

            race_date = datetime.strptime(race_date_str, "%Y-%m-%d").date()
            days = (race_date - today).days
        except (ValueError, TypeError):
            days = -1
        if days > 0:
            next_race_html = (
                f'<div class="race"><span class="race-name">{race.get("name", "")}</span>'
                f'<span class="race-days">{days} 天后</span></div>'
            )
            break

    # Build the lock-screen HTML (e-ink first: table layout, no flexbox, 16-gray safe)
    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>训练屏保 · {today:%m.%d}</title>
<style>
  body {{
    margin: 0; padding: 32px 28px;
    background: #FFFFFF; color: #111111;
    font-family: "Noto Sans CJK SC", "PingFang SC", "Microsoft YaHei", sans-serif;
    font-size: 20px;
  }}
  .header {{
    border-bottom: 3px solid #111;
    padding-bottom: 14px;
    margin-bottom: 22px;
  }}
  .header .date {{ font-size: 40px; font-weight: bold; letter-spacing: 1px; }}
  .header .sub {{ font-size: 18px; color: #555; margin-top: 6px; }}
  .header .streak {{ float: right; text-align: right; font-size: 22px; font-weight: bold; }}
  .block {{ margin-bottom: 24px; }}
  .block-title {{
    font-size: 17px; color: #666; letter-spacing: 2px;
    border-bottom: 1px solid #ddd; padding-bottom: 6px; margin-bottom: 12px;
  }}
  .today {{ font-size: 26px; font-weight: bold; line-height: 1.5; }}
  .goal-row {{
    display: table-row;
    font-size: 22px; line-height: 1.9;
  }}
  .goal-row span {{ display: table-cell; }}
  .goal-row .g-icon {{ width: 48px; }}
  .goal-row .g-val {{ padding-right: 12px; }}
  .goal-row .g-bar {{ display: inline-block; height: 16px; background: #ddd; vertical-align: middle; margin-right: 8px; }}
  .goal-row .g-bar i {{ display: block; height: 100%; background: #444; }}
  .goal-row .g-pct {{ font-size: 18px; color: #555; }}
  .race {{ margin-top: 8px; font-size: 24px; font-weight: bold; }}
  .race .race-days {{ float: right; color: #111; }}
  .footer {{
    margin-top: 30px; padding-top: 12px;
    border-top: 1px solid #ddd;
    font-size: 16px; color: #888; text-align: center;
  }}
</style>
</head>
<body>
  <div class="header">
    <div class="date">{today:%m月%d日} · {weekday_cn[today.weekday()]}</div>
    <div class="sub">{today:%Y年%m月%d日}{' · ' + lunar if lunar else ''}</div>
    <div class="streak">连训 {streak} 天</div>
  </div>

  <div class="block">
    <div class="block-title">今日训练</div>
    <div class="today">{today_desc}</div>
  </div>

  <div class="block">
    <div class="block-title">本周目标</div>
    {''.join(
        f'<div class="goal-row">'
        f'<span class="g-icon">{g["icon"]}</span>'
        f'<span class="g-val">{g["label"]} {g["current"]} / {g["target"]}</span>'
        f'<span class="g-bar"><i style="width:{g["pct"]}%"></i></span>'
        f'<span class="g-pct">{g["pct"]}%</span>'
        f'</div>'
        for g in weekly_goals
    ) if weekly_goals else '<div class="today">暂无目标</div>'}
  </div>

  <div class="block">
    <div class="block-title">下一场比赛</div>
    {next_race_html or '<div class="today">暂无安排</div>'}
  </div>

  <div class="footer">Strava Dashboard · 锁定屏 · 每日自动更新</div>
</body>
</html>
"""
    os.makedirs(output_dir, exist_ok=True)
    html_path = os.path.join(output_dir, "screensaver.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Screensaver rendered: {html_path}")
    return html


def _render_png(html_path: str, png_path: str, width: int = 758, height: int = 1024) -> bool:
    """Rasterise the screensaver HTML to a grayscale PNG via Playwright.

    E-ink displays are 16-gray; PNG is kept grayscale for smaller size.
    Returns True on success, False if Playwright is unavailable (non-fatal).
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("Playwright not installed; skipping PNG render.", file=sys.stderr)
        return False

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(args=["--no-sandbox"])
            page = browser.new_page(
                viewport={"width": width, "height": height},
                device_scale_factor=1,
            )
            page.goto(f"file://{os.path.abspath(html_path)}")
            page.wait_for_timeout(500)
            page.screenshot(path=png_path, type="png")
            browser.close()
        print(f"Screensaver PNG: {png_path}")
        return True
    except Exception as e:
        print(f"PNG render failed (non-fatal): {e}", file=sys.stderr)
        return False


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Render e-ink screensaver page")
    parser.add_argument("--data", default="data", help="Data directory")
    parser.add_argument("--config", default="config.yaml", help="Config YAML path")
    parser.add_argument("--output", default="output", help="Output directory")
    args = parser.parse_args()

    html_str = render_screensaver(
        data_dir=args.data, config_path=args.config, output_dir=args.output
    )

    # PNG is best-effort (workflow installs Playwright; local may not)
    _render_png(
        os.path.join(args.output, "screensaver.html"),
        os.path.join(args.output, "screensaver.png"),
    )