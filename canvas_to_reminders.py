#!/usr/bin/env python3
"""Turn upcoming Canvas iCal events into Apple Reminders using remctl.

Dry run by default. Pass --apply to actually create reminders.
Already-added events are tracked in a small JSON file so reruns
never create duplicates.
"""

import argparse
import json
import os
import shlex
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from dotenv import load_dotenv
from icalendar import Calendar

load_dotenv(Path(__file__).resolve().with_name(".env"))

LOCAL_TZ = ZoneInfo("America/Los_Angeles")
DEFAULT_STATE = Path.home() / ".canvas_reminders_state.json"


# ---------- Step 1-3: load events and normalize dates ----------

def fetch_ics(url):
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    return response.content


def load_events(ics_bytes):
    cal = Calendar.from_ical(ics_bytes)
    for event in cal.walk("VEVENT"):
        yield {
            "uid": str(event.get("UID")),
            "title": str(event.get("SUMMARY")),
            "due": event.decoded("DTSTART"),
            "url": str(event.get("URL", "")),
        }


def to_local(due):
    if isinstance(due, datetime):
        return due.astimezone(LOCAL_TZ)
    return due


def due_day(due):
    local = to_local(due)
    if isinstance(local, datetime):
        return local.date()
    return local


def upcoming(events, today=None):
    today = today or datetime.now(LOCAL_TZ).date()
    return [e for e in events if due_day(e["due"]) >= today]


# ---------- Step 4: build and run the remctl command ----------

def due_arg(due):
    local = to_local(due)
    if isinstance(local, datetime):
        return local.strftime("%Y-%m-%d %H:%M")
    return local.isoformat()


def find_remctl():
    override = os.environ.get("REMCTL_PATH")
    if override and Path(override).expanduser().exists():
        return str(Path(override).expanduser())
    found = shutil.which("remctl")
    if found:
        return found
    fallback = Path.home() / "bin" / "remctl"
    if fallback.exists():
        return str(fallback)
    return None


def build_command(event, list_name=None, remctl="remctl"):
    cmd = [remctl, "add", "--json", "-d", due_arg(event["due"])]
    if list_name:
        cmd += ["-l", list_name]
    if event["url"]:
        cmd += ["--url", event["url"]]
    cmd += ["--", event["title"]]
    return cmd


def build_edit_command(event, remctl, reminder_id):
    return [
        remctl, "edit", str(reminder_id),
        "--title", event["title"],
        "-d", due_arg(event["due"]),
    ]


# ---------- Step 5: remember what was already added ----------

def load_state(path):
    if path.exists():
        return json.loads(path.read_text())
    return {}


def save_state(path, state):
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2))
    tmp.replace(path)


def has_changed(entry, event):
    return entry["title"] != event["title"] or entry["due"] != str(event["due"])


def run_add(cmd):
    result = subprocess.run(cmd, check=True, capture_output=True, text=True)
    try:
        return json.loads(result.stdout).get("numericId")
    except (json.JSONDecodeError, AttributeError):
        return None


def sync(events, list_name, state_path, apply, remctl):
    state = load_state(state_path)
    added = updated = skipped = failed = 0

    for event in sorted(events, key=lambda e: due_day(e["due"])):
        entry = state.get(event["uid"])

        if entry is not None and not has_changed(entry, event):
            skipped += 1
            continue

        if entry is None:
            cmd = build_command(event, list_name, remctl)
        elif entry.get("id"):
            cmd = build_edit_command(event, remctl, entry["id"])
        else:
            print(
                f"CAN'T UPDATE: {event['title']} changed in Canvas, but no "
                "reminder ID was saved for it (added by an older version).",
                file=sys.stderr,
            )
            failed += 1
            continue

        label = "add" if entry is None else "update"
        if not apply:
            print(f"[dry run] {label}:", shlex.join(cmd))
            if entry is None:
                added += 1
            else:
                updated += 1
            continue

        try:
            if entry is None:
                reminder_id = run_add(cmd)
                if reminder_id is None:
                    print(f"Note: no reminder ID returned for {event['title']}; "
                          "future changes to it can't be applied automatically.",
                          file=sys.stderr)
            else:
                subprocess.run(cmd, check=True, capture_output=True, text=True)
                reminder_id = entry["id"]
        except subprocess.CalledProcessError as err:
            print(f"FAILED to {label}: {event['title']} ({err.stderr.strip() or err})",
                  file=sys.stderr)
            failed += 1
            continue
        except FileNotFoundError as err:
            print(f"FAILED to {label}: {event['title']} ({err})", file=sys.stderr)
            failed += 1
            continue

        state[event["uid"]] = {
            "title": event["title"],
            "due": str(event["due"]),
            "id": reminder_id,
            "added": (entry or {}).get("added")
            or datetime.now(LOCAL_TZ).isoformat(timespec="seconds"),
        }
        save_state(state_path, state)
        if entry is None:
            added += 1
        else:
            updated += 1

    verb = "created" if apply else "would create"
    verb2 = "updated" if apply else "would update"
    print(f"\n{verb}: {added} | {verb2}: {updated} | unchanged: {skipped} | failed: {failed}")


# ---------- Command line ----------

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list", default="Canvas", help="Reminders list name")
    parser.add_argument("--file", help="read a local .ics file instead of the feed URL")
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE)
    parser.add_argument("--apply", action="store_true", help="actually create reminders")
    args = parser.parse_args()

    if args.file:
        ics_bytes = Path(args.file).read_bytes()
    else:
        url = os.environ.get("CANVAS_ICAL_URL")
        if not url:
            sys.exit("Add CANVAS_ICAL_URL=<your feed URL> to the .env file next to this script.")
        ics_bytes = fetch_ics(url)

    remctl = find_remctl()
    if args.apply and not remctl:
        sys.exit(
            "Could not find remctl. Run `which remctl` in Terminal, then add "
            "REMCTL_PATH=<that path> to the .env file next to this script."
        )

    events = upcoming(list(load_events(ics_bytes)))
    sync(events, args.list, args.state, args.apply, remctl or "remctl")


if __name__ == "__main__":
    main()
