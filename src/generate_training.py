#!/usr/bin/env python3
"""
Generate weekly training plan using Claude API.
Can be called from GitHub Action or locally.

Usage:
  # With Claude API key
  ANTHROPIC_API_KEY=xxx python src/generate_training.py

  # Without API key (generates a basic plan from rules)
  python src/generate_training.py
"""

import json
import os
import sys
from datetime import datetime, timedelta


def generate_basic_plan(processed_data, config):
    """Generate a basic training plan without AI (rule-based fallback)."""
    weekly = processed_data.get("weekly_summary", {})
    weekly_goals = processed_data.get("weekly_goals", [])
    key_metrics = processed_data.get("key_metrics", {})
    races = processed_data.get("races", [])

    # Current week's remaining goals
    ride_remaining = 0
    run_remaining = 0
    workout_remaining = 0

    for g in weekly_goals:
        if g.get("sport") == "ride":
            ride_remaining = max(0, g.get("target", 0) - g.get("current", 0))
        elif g.get("sport") == "run":
            run_remaining = max(0, g.get("target", 0) - g.get("current", 0))
        elif g.get("sport") == "workout":
            workout_remaining = max(0, g.get("target", 0) - g.get("current", 0))

    # Days of week in Chinese
    days = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]

    # Base plan template - adjusts based on remaining goals
    plan = []

    # Check if there's an upcoming race
    # races may be a dict with 'upcoming'/'past' keys or a list
    if isinstance(races, dict):
        upcoming = races.get("upcoming", [])
    else:
        upcoming = [r for r in races if r.get("status") == "upcoming"]
    race_note = ""
    if upcoming:
        days_to_race = upcoming[0].get("countdown_days", 0)
        if days_to_race <= 7:
            race_note = f" (周赛:{upcoming[0]['name']})"

    if ride_remaining > 60:
        # Need big ride week
        plan = [
            f"休息/核心训练{race_note}",
            "5km轻松跑 @5:40/km",
            f"MyWhoosh 60-90min Z2耐力骑行",
            "力量训练（上肢+核心）",
            "5km节奏跑 @5:10/km",
            f"户外骑行 {min(int(ride_remaining*0.6),80)}km Z2-Z3",
            "8-10km长跑 @5:20/km",
        ]
    elif run_remaining > 10:
        # Need more running
        plan = [
            f"休息/拉伸{race_note}",
            f"5km节奏跑 @5:10/km",
            "MyWhoosh 60min Z2耐力",
            "力量训练（下肢+核心）",
            f"5-8km轻松跑 @5:40/km",
            f"户外骑行 40-60km Z2",
            f"8-10km长跑 @5:20/km",
        ]
    else:
        # Balanced week
        plan = [
            f"休息/轻度拉伸{race_note}",
            "5km轻松跑 @5:40/km",
            "MyWhoosh 60min Z2耐力",
            "力量训练（全身）",
            "休息或5km慢跑",
            "户外骑行 50-70km Z2-Z3",
            "8km长跑 @5:20/km",
        ]

    # Insert workout if needed
    if workout_remaining > 0:
        # Already included in plan, good
        pass

    return dict(zip(days, plan))


def generate_ai_plan(processed_data, config):
    """Generate training plan using Claude API."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return None

    try:
        import requests
    except ImportError:
        return None

    key_metrics = processed_data.get("key_metrics", {})
    weekly_goals = processed_data.get("weekly_goals", [])
    races = processed_data.get("races", [])

    # Build context
    ftp = key_metrics.get("ftp", "unknown")
    best_5k = key_metrics.get("best_5k_time")
    if best_5k:
        mins = best_5k // 60
        secs = best_5k % 60
        best_5k_str = f"{mins}:{secs:02d}"
    else:
        best_5k_str = "unknown"

    goals_str = "\n".join([
        f"  - {g['sport']}: {g.get('current',0):.1f}/{g.get('target',0):.1f} ({g.get('pct',0):.0f}%)"
        for g in weekly_goals
    ])

    # races may be a dict with 'upcoming'/'past' keys or a list
    if isinstance(races, dict):
        upcoming = races.get("upcoming", [])
    else:
        upcoming = [r for r in races if r.get("status") == "upcoming"]
    race_str = ""
    if upcoming:
        race_str = f"\n即将到来的比赛: {upcoming[0]['name']} ({upcoming[0].get('countdown_days','?')}天后)"

    prompt = f"""你是Eric的运动教练。基于以下数据生成本周训练建议：

当前指标：
- FTP: {ftp}W（目标 250W）
- 5K最佳: {best_5k_str}
- 年度PR总数: {key_metrics.get('total_prs', 0)}

本周目标完成情况：
{goals_str}
{race_str}

规则：
- 每天一条建议，周一到周日共7行
- 格式：活动类型 + 时长/距离 + 强度区间
- 工作日偏短平快(30-60min)，周末偏长距离
- 必须包含1-2次力量训练
- 至少1天完全休息
- 输出格式严格为7行，每行格式"周X: 内容"，不要额外说明"""

    # Support custom base URL (e.g. Baidu Qianfan proxy)
    base_url = os.environ.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com")
    model = os.environ.get("ANTHROPIC_DEFAULT_HAIKU_MODEL", "claude-haiku-4-5-20251001")

    try:
        resp = requests.post(
            f"{base_url}/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": model,
                "max_tokens": 500,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=30,
        )
        resp.raise_for_status()
        # Handle both standard Anthropic and Qianfan (which may include thinking blocks)
        content_blocks = resp.json()["content"]
        text = ""
        for block in content_blocks:
            if block.get("type") == "text":
                text += block.get("text", "")
        if not text:
            # Fallback: try first block regardless of type
            text = content_blocks[0].get("text", "") if content_blocks else ""

        # Parse the response into a dict
        plan = {}
        days_cn = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
        for line in text.strip().split("\n"):
            line = line.strip()
            if not line:
                continue
            for day in days_cn:
                if day in line:
                    # Remove "周X:" prefix
                    content = line.split(":", 1)[-1].strip() if ":" in line else line
                    plan[day] = content
                    break

        # Fill missing days
        for i, day in enumerate(days_cn):
            if day not in plan:
                plan[day] = "休息"

        return plan

    except Exception as e:
        print(f"Warning: AI plan generation failed: {e}", file=sys.stderr)
        return None


def main():
    data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
    config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.yaml")

    # Load processed data
    processed_path = os.path.join(data_dir, "processed.json")
    if not os.path.exists(processed_path):
        print(f"Error: {processed_path} not found. Run process_data.py first.")
        sys.exit(1)

    with open(processed_path, "r", encoding="utf-8") as f:
        processed_data = json.load(f)

    # Load config
    import yaml
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    # Try AI first, fall back to rule-based
    plan = generate_ai_plan(processed_data, config)
    if not plan:
        print("Using rule-based plan (no API key or API error)")
        plan = generate_basic_plan(processed_data, config)
    else:
        print("Using AI-generated plan")

    # Save
    output = {
        "plan": plan,
        "generated_at": datetime.now().isoformat(),
        "source": "ai" if os.environ.get("ANTHROPIC_API_KEY") else "rule-based",
    }

    out_path = os.path.join(data_dir, "training_plan.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"Saved training plan to {out_path}")
    for day, activity in plan.items():
        print(f"  {day}: {activity}")


if __name__ == "__main__":
    main()
