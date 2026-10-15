#!/usr/bin/env python3
"""revenue_start.py - Revenue Mode's on-switch, and the card its autonomy hangs from. After a yes,
and nothing else.

    echo {"bids": 2} | python tools/revenue_start.py
    Revenue Mode is on, sir - up to 2 bids a day on Upwork, Fiverr and Freelancer.com ...

THE CONTRACT, as tools/selftest.py states it:

  in    {"bids": N} on stdin, UTF-8 - the daily cap the employer saw on the card, from config.json's
        revenue block via server.revenue_asked(). Door-bound to "revenue": no model fills it in.
  out   ONE line on stdout: on, and what that means - or why it stayed off.
  exit  0 the switch is on. 1 it is not, and the line says why.

WHAT IT DOES: nothing on any platform itself. It writes revenue-state.json; the daemon in the
server reads it within seconds and makes its first pass, which is where "I'm not signed into
Upwork, sir" is found out - per platform, live, rather than guessed here.
"""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import revenue                                                 # noqa: E402


def say(line):
    sys.stdout.buffer.write(str(line).encode("ascii", "replace") + b"\n")
    sys.stdout.buffer.flush()


def main():
    try:
        sys.stdin.reconfigure(encoding="utf-8")
    except Exception:                                          # noqa: BLE001
        pass
    try:
        p = json.loads(sys.stdin.read() or "{}")
    except ValueError:
        say("Revenue Mode's card would not parse, so it stayed off.")
        return 1
    bids = p.get("bids") if isinstance(p, dict) else None
    if type(bids) is not int or not 1 <= bids <= revenue.HARD_DAILY_MAX:
        say("Revenue Mode places between 1 and %d bids a day, not %r, so it stayed off."
            % (revenue.HARD_DAILY_MAX, bids))
        return 1
    s, problems = revenue.settings()
    if problems:
        say("Revenue Mode stayed off: %s." % problems[0])
        return 1
    try:
        revenue.read_log()
        revenue.read_book()
        revenue.switch(True, "card", daily=bids)
    except OSError as exc:
        say("Revenue Mode stayed off: %s." % exc)
        return 1
    names = [revenue.PLATFORMS[k]["name"] for k in s["platforms"]]
    say("Revenue Mode is on, sir - up to %d bid%s a day on %s, only on work your own profile "
        "says you can do. Finished work waits for your review; say \"revenue update\" for the "
        "report and \"stop revenue mode\" (or Ctrl+M while it is in the browser) to halt it."
        % (bids, "" if bids == 1 else "s", revenue.and_list(names)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
