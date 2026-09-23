#!/usr/bin/env python3
"""add_calendar_event.py - one line into calendar.json, and nothing else.

A real hand, doing a real thing, in about forty lines. The reason it is worth reading
is not the JSON: it is that this file is the entire blast radius of "remind me to call
the client at four". It appends one entry to one file in the project root. It cannot
send anything, cannot delete anything, and has no idea what the internet is.

  in    {"title": "...", "when": "...", "notes": "..."} on stdin, UTF-8
  out   one ASCII line, which is the only thing the assistant is allowed to claim
  exit  0 appended, 1 did not

Run it by hand:  echo {"title":"call the client","when":"four"} | python tools/add_calendar_event.py
"""
import json
import pathlib
import sys
import time

# pathlib, and relative to THIS file rather than to the working directory: the server
# runs scripts with cwd set to tools/, a human runs them from the project root, and
# both must write to the same calendar.
CALENDAR = pathlib.Path(__file__).resolve().parent.parent / "calendar.json"
MAX_ENTRIES = 2000


def say(line):
    sys.stdout.buffer.write(str(line).encode("ascii", "replace") + b"\n")
    sys.stdout.buffer.flush()


def load():
    """Whatever is there, or an empty diary. A corrupt file is not a reason to lose one."""
    try:
        data = json.loads(CALENDAR.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return data if isinstance(data, list) else []


def main():
    raw = sys.stdin.buffer.read().decode("utf-8", "replace")
    try:
        params = json.loads(raw) if raw.strip() else {}
    except ValueError as exc:
        say("Calendar failed: the parameters were not JSON (%s)" % exc)
        return 1
    if not isinstance(params, dict):
        say("Calendar failed: the parameters were not an object")
        return 1
    title = str(params.get("title") or "").strip()[:200]
    when = str(params.get("when") or "").strip()[:120]
    notes = str(params.get("notes") or "").strip()[:2000]
    if not title or not when:
        say("Calendar failed: an entry needs a title and a time")
        return 1

    entries = load()
    entries.append({"title": title, "when": when, "notes": notes,
                    "added": time.strftime("%Y-%m-%dT%H:%M:%S")})
    del entries[:max(0, len(entries) - MAX_ENTRIES)]
    try:
        CALENDAR.write_text(json.dumps(entries, ensure_ascii=False, indent=2) + "\n",
                            encoding="utf-8")
    except OSError as exc:
        say("Calendar failed: could not write the file (%s)" % exc)
        return 1
    # It is in, and the line says WHICH entry and how many the diary now holds - the
    # employer hears this instead of watching a file, so it has to be worth hearing.
    say("Written into your calendar: %s at %s. That makes %d entr%s in all."
        % (title, when, len(entries), "y" if len(entries) == 1 else "ies"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
