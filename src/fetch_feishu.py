#!/usr/bin/env python3
"""
Fetch tasks from Feishu (Lark) via the official lark-oapi SDK.

Reads incomplete tasks from Feishu Task API and outputs
data/feishu_tasks.json for the dashboard renderer.

Setup:
1. Create a Feishu app at https://open.feishu.cn/app
2. Enable "Task" permissions (task:task:read)
3. Set FEISHU_APP_ID and FEISHU_APP_SECRET environment variables
4. Or add them to .env.secrets

If credentials are not configured, the script exits gracefully
and the dashboard will use Apple Reminders or config.yaml as fallback.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime


def fetch_feishu_tasks(output_path: str = "data/feishu_tasks.json") -> dict:
    """Fetch incomplete tasks from Feishu Task API.

    Args:
        output_path: Path to write the output JSON.

    Returns:
        The tasks data dict.
    """
    app_id = os.environ.get("FEISHU_APP_ID", "")
    app_secret = os.environ.get("FEISHU_APP_SECRET", "")

    if not app_id or not app_secret:
        msg = "FEISHU_APP_ID / FEISHU_APP_SECRET not set. Skipping Feishu task fetch."
        print(msg, file=sys.stderr)
        result = {
            "todos": [],
            "fetched_at": datetime.now().isoformat(),
            "error": "Credentials not configured",
        }
        _write_output(result, output_path)
        return result

    try:
        import lark_oapi as lark
        from lark_oapi.api.task.v2 import ListTaskRequest, ListTaskRequestFilter, ListTaskRequestSource
    except ImportError:
        print("Error: lark-oapi not installed. Run: pip install lark-oapi", file=sys.stderr)
        result = {"todos": [], "fetched_at": datetime.now().isoformat(), "error": "lark-oapi not installed"}
        _write_output(result, output_path)
        return result

    # Create client
    client = lark.Client.builder() \
        .app_id(app_id) \
        .app_secret(app_secret) \
        .build()

    # Fetch tasks (incomplete only)
    try:
        request = ListTaskRequest.builder() \
            .user_id_type("open_id") \
            .page_size(50) \
            .build()

        response = client.task.v2.task.list(request)

        if not response.success():
            print(f"Feishu API error: {response.code} - {response.msg}", file=sys.stderr)
            result = {
                "todos": [],
                "fetched_at": datetime.now().isoformat(),
                "error": f"API error: {response.code} - {response.msg}",
            }
            _write_output(result, output_path)
            return result

        # Parse response
        todos = []
        if response.data and response.data.items:
            for task in response.data.items:
                title = task.summary or ""
                if not title.strip():
                    continue

                is_completed = task.status == 3 if hasattr(task, "status") else False
                due_str = ""
                if hasattr(task, "due") and task.due:
                    due_str = task.due.get("date", "") if isinstance(task.due, dict) else ""

                todos.append({
                    "text": title.strip(),
                    "done": is_completed,
                    "due_date": due_str,
                    "source": "feishu",
                })

        result = {
            "todos": todos,
            "incomplete_count": sum(1 for t in todos if not t["done"]),
            "completed_count": sum(1 for t in todos if t["done"]),
            "fetched_at": datetime.now().isoformat(),
        }

    except Exception as e:
        print(f"Feishu fetch error: {e}", file=sys.stderr)
        result = {
            "todos": [],
            "fetched_at": datetime.now().isoformat(),
            "error": str(e),
        }

    _write_output(result, output_path)
    return result


def _write_output(data: dict, path: str) -> None:
    """Write data to JSON file."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"Feishu tasks saved: {path}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    fetch_feishu_tasks()
