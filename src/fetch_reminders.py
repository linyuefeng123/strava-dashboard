#!/usr/bin/env python3
"""
Fetch Apple Reminders via EventKit (PyObjC).

Reads reminders from the default Reminders list and outputs
data/reminders.json for the dashboard renderer.

Requires: PyObjC (EventKit framework)
First run may prompt for Reminders access permission.

iCloud sync: Reminders edited on iPhone will automatically
appear on Mac via iCloud, so this script reads the latest data.
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, date


def fetch_reminders(output_path: str = "data/reminders.json") -> dict:
    """Fetch Apple Reminders via EventKit.

    Args:
        output_path: Path to write the output JSON.

    Returns:
        The reminders data dict.
    """
    try:
        import EventKit
    except ImportError:
        print("Error: PyObjC not installed. Run: pip install pyobjc-framework-EventKit", file=sys.stderr)
        result = {"todos": [], "fetched_at": datetime.now().isoformat(), "error": "PyObjC not installed"}
        _write_output(result, output_path)
        return result

    # Check authorization
    status = EventKit.EKEventStore.authorizationStatusForEntityType_(EventKit.EKEntityTypeReminder)
    if status != 3:  # 3 = Authorized
        msg = {0: "Not determined (need to grant permission)", 1: "Restricted",
               2: "Denied (check System Settings > Privacy > Reminders)"}.get(status, f"Unknown ({status})")
        print(f"Error: Reminders access not authorized: {msg}", file=sys.stderr)
        result = {"todos": [], "fetched_at": datetime.now().isoformat(), "error": f"Access not authorized: {msg}"}
        _write_output(result, output_path)
        return result

    store = EventKit.EKEventStore.alloc().init()
    calendars = store.calendarsForEntityType_(EventKit.EKEntityTypeReminder)

    all_todos = []

    for cal in calendars:
        predicates = store.predicateForRemindersInCalendars_([cal])

        reminders = []
        done_flag = []

        def fetch_completion(r):
            reminders.extend(r)
            done_flag.append(True)

        store.fetchRemindersMatchingPredicate_completion_(predicates, fetch_completion)

        # Wait for async completion (up to 10 seconds)
        start = time.time()
        while not done_flag and time.time() - start < 10:
            time.sleep(0.1)

        if not done_flag:
            print(f"Warning: Timeout fetching reminders from '{cal.title()}'", file=sys.stderr)
            continue

        for r in reminders:
            title = r.title() or ""
            if not title.strip():
                continue

            is_completed = r.isCompleted()

            # Due date
            due = r.dueDateComponents()
            due_str = ""
            if due and due.year():
                due_str = f"{due.year()}-{due.month():02d}-{due.day():02d}"

            # Completion date
            comp_date = r.completionDate()
            comp_str = ""
            if comp_date:
                try:
                    from Foundation import NSDateFormatter
                    fmt = NSDateFormatter.alloc().init()
                    fmt.setDateFormat_("yyyy-MM-dd")
                    comp_str = fmt.stringFromDate_(comp_date)
                except Exception:
                    pass

            # Priority (1=high, 5=medium, 9=low, 0=none)
            priority = r.priority()

            # Notes
            notes = r.notes() or ""

            all_todos.append({
                "text": title.strip(),
                "done": is_completed,
                "due_date": due_str,
                "completed_date": comp_str,
                "priority": priority,
                "list": cal.title(),
                "notes": notes.strip(),
            })

    # Sort: incomplete first (by due date), then completed (by completion date desc)
    def sort_key(t):
        if not t["done"]:
            # Incomplete: sort by due date (empty = far future)
            due = t["due_date"] or "9999-99-99"
            return (0, due)
        else:
            # Completed: sort by completion date desc
            comp = t["completed_date"] or ""
            return (1, "" if not comp else comp)

    all_todos.sort(key=sort_key)

    result = {
        "todos": all_todos,
        "incomplete_count": sum(1 for t in all_todos if not t["done"]),
        "completed_count": sum(1 for t in all_todos if t["done"]),
        "fetched_at": datetime.now().isoformat(),
    }

    _write_output(result, output_path)
    return result


def _write_output(data: dict, path: str) -> None:
    """Write data to JSON file."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"Reminders data saved: {path}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    fetch_reminders()
