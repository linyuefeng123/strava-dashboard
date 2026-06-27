#!/usr/bin/env python3
"""
Fetch inspirational quotes from hitokoto.cn API.

Outputs data/quotes.json with quote text and source.
Falls back to hardcoded Chinese quotes on API failure.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime

import requests


# ---------------------------------------------------------------------------
# Hardcoded fallback quotes (from KindleNoodle + additions)
# ---------------------------------------------------------------------------

FALLBACK_QUOTES = [
    {"text": "千里之行，始于足下。", "from": "老子"},
    {"text": "不积跬步，无以至千里；不积小流，无以成江海。", "from": "荀子"},
    {"text": "天行健，君子以自强不息。", "from": "《周易》"},
    {"text": "学而不思则罔，思而不学则殆。", "from": "孔子"},
    {"text": "知之者不如好之者，好之者不如乐之者。", "from": "孔子"},
    {"text": "路漫漫其修远兮，吾将上下而求索。", "from": "屈原"},
    {"text": "长风破浪会有时，直挂云帆济沧海。", "from": "李白"},
    {"text": "宝剑锋从磨砺出，梅花香自苦寒来。", "from": "古训"},
    {"text": "业精于勤，荒于嬉；行成于思，毁于随。", "from": "韩愈"},
    {"text": "生当作人杰，死亦为鬼雄。", "from": "李清照"},
    {"text": "人生自古谁无死，留取丹心照汗青。", "from": "文天祥"},
    {"text": "纸上得来终觉浅，绝知此事要躬行。", "from": "陆游"},
    {"text": "世上无难事，只要肯登攀。", "from": "毛泽东"},
    {"text": "苟利国家生死以，岂因祸福避趋之。", "from": "林则徐"},
    {"text": "博观而约取，厚积而薄发。", "from": "苏轼"},
]


# ---------------------------------------------------------------------------
# Fetch quotes
# ---------------------------------------------------------------------------

def fetch_quotes(
    categories: list[str] | None = None,
    output_path: str = "data/quotes.json",
) -> dict:
    """Fetch quotes from hitokoto.cn API.

    Args:
        categories: Hitokoto category codes (d=poetry, i=quotes, k=philosophy).
        output_path: Path to write the output JSON.

    Returns:
        The quotes data dict with 'quote' (primary) and 'fallback' keys.
    """
    if categories is None:
        categories = ["d", "i", "k"]

    quote = None

    try:
        # Build URL with category params
        url = "https://v1.hitokoto.cn/"
        params = {f"c": cat for cat in categories}
        # hitokoto expects multiple c params: ?c=d&c=i&c=k
        # requests doesn't support duplicate keys in dict, build URL manually
        param_str = "&".join(f"c={cat}" for cat in categories)
        full_url = f"{url}?{param_str}&encode=json"

        resp = requests.get(full_url, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        text = data.get("hitokoto", "").strip()
        source = data.get("from", "").strip()
        if text:
            quote = {"text": text, "from": source}

    except (requests.RequestException, json.JSONDecodeError, ValueError) as e:
        print(f"Quote fetch failed: {e}", file=sys.stderr)

    # Fallback if API failed
    if quote is None:
        import random
        quote = random.choice(FALLBACK_QUOTES)

    result = {
        "quote": quote,
        "fetched_at": datetime.now().isoformat(),
    }

    # Write output
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    print(f"Quote data saved: {output_path}")
    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    fetch_quotes()
