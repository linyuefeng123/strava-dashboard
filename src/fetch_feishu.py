#!/usr/bin/env python3
"""
Fetch tasks from Feishu (Lark) via direct HTTPS API.

Reads tasks from Feishu Task API v1 and outputs
data/feishu_tasks.json for the dashboard renderer.

Setup:
1. Go to https://open.feishu.cn/app → 找到你的应用
2. 权限管理 → 添加 "任务" 权限 (task:task:read)
3. 发布应用
4. 设置环境变量 FEISHU_APP_ID 和 FEISHU_APP_SECRET
"""

from __future__ import annotations

import json
import os
import sys
import requests
from datetime import datetime


# ---------------------------------------------------------------------------
# Token management
# ---------------------------------------------------------------------------

_TOKEN_CACHE: dict = {}


def _get_tenant_token(app_id: str, app_secret: str) -> str | None:
    """Get tenant access token from Feishu Open API."""
    cached = _TOKEN_CACHE.get("token")
    if cached:
        return cached

    try:
        resp = requests.post(
            "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
            json={"app_id": app_id, "app_secret": app_secret},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        token = data.get("tenant_access_token")
        if token:
            _TOKEN_CACHE["token"] = token
            return token
        print(f"Feishu token error: {data}", file=sys.stderr)
        return None
    except requests.RequestException as e:
        print(f"Feishu token request failed: {e}", file=sys.stderr)
        return None


# ---------------------------------------------------------------------------
# Fetch tasks
# ---------------------------------------------------------------------------

def fetch_feishu_tasks(output_path: str = "data/feishu_tasks.json") -> dict:
    """Fetch tasks from Feishu Task API v1.

    Args:
        output_path: Path to write the output JSON.

    Returns:
        dict with keys: todos, incomplete_count, completed_count, fetched_at, error (optional)
    """
    app_id = os.environ.get("FEISHU_APP_ID", "")
    app_secret = os.environ.get("FEISHU_APP_SECRET", "")

    if not app_id or not app_secret:
        msg = "FEISHU_APP_ID / FEISHU_APP_SECRET not set. Skipping Feishu task fetch."
        print(msg, file=sys.stderr)
        result = {"todos": [], "fetched_at": datetime.now().isoformat(), "error": "Credentials not configured"}
        _write_output(result, output_path)
        return result

    # Get access token
    token = _get_tenant_token(app_id, app_secret)
    if not token:
        result = {"todos": [], "fetched_at": datetime.now().isoformat(), "error": "Failed to get access token"}
        _write_output(result, output_path)
        return result

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json; charset=utf-8",
    }

    try:
        # Fetch task list (v1 API)
        resp = requests.get(
            "https://open.feishu.cn/open-apis/task/v1/tasks",
            params={"page_size": 50, "user_id_type": "open_id"},
            headers=headers,
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()

        if data.get("code") != 0:
            err_msg = data.get("msg", "Unknown error")
            print(f"Feishu API error: {data.get('code')} - {err_msg}", file=sys.stderr)
            print("", file=sys.stderr)
            print("=== 开通权限步骤 ===", file=sys.stderr)
            print(f"1. 打开: https://open.feishu.cn/app/{app_id}/auth?q=task:task:readonly,task:task:read&token_type=tenant", file=sys.stderr)
            print("2. 添加 'task:task:readonly' 和 'task:task:read' 权限", file=sys.stderr)
            print("3. 发布新版本", file=sys.stderr)
            print("", file=sys.stderr)
            result = {"todos": [], "fetched_at": datetime.now().isoformat(), "error": f"API error: {err_msg}"}
            _write_output(result, output_path)
            return result

        # Parse tasks
        todos = []
        task_items = data.get("data", {}).get("items", []) if isinstance(data.get("data"), dict) else []

        if not task_items and isinstance(data.get("data"), list):
            task_items = data["data"]

        for item in task_items:
            title = item.get("summary", "") or item.get("title", "")
            if not title.strip():
                continue

            status = item.get("status", 0)
            is_done = status == 2

            due_str = ""
            due_info = item.get("due", {}) or {}
            if isinstance(due_info, dict):
                due_date = due_info.get("date", "")
                due_str = due_date if due_date else ""

            todos.append({
                "text": title.strip(),
                "done": is_done,
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
        result = {"todos": [], "fetched_at": datetime.now().isoformat(), "error": str(e)}

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