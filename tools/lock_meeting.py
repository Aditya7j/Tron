#!/usr/bin/env python3
"""lock_meeting.py - the employer's "lock a meeting with <business>". After a yes, and nothing
else. The one Closer send that is never autonomous: which lead deserves a meeting is the
employer's judgment, and this hand exists so that the judgment is his and visibly so.

    echo {"lead": "H-0007", "when": "Friday at 4pm"} | python tools/lock_meeting.py
    Written to Dr Hinge's Dental Clinic asking for a meeting (Friday at 4pm), sir - ...

THE CONTRACT, as tools/selftest.py states it:

  in    {"lead": "H-0007", "when": "..."} on stdin, UTF-8. lead is resolved from the employer's
        own sentence by closer.find_lead() in server.closer_asked(); when is his own words or
        empty, in which case the business is asked which times suit them. Door-bound to
        "closer": no model fills either in, and no time is ever made up.
  out   ONE line on stdout: written, with Gmail's id - or why not.
  exit  0 the email went. 1 it did not, and it is not retried.

WHAT IT SENDS: one email to that business, in the thread the Closer started with it, signed with
the offer sheet's signature. The lead becomes "meeting-proposed"; the Closer marks it
"meeting-confirmed" when the business answers with a time. No calendar is touched this phase.
"""
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import closer                                                  # noqa: E402


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
        say("The meeting card would not parse, so nothing was sent.")
        return 1
    lead = str((p or {}).get("lead") or "").strip() if isinstance(p, dict) else ""
    if not re.fullmatch(r"H-\d{4,6}", lead):
        say("The card names no lead, so nothing was sent.")
        return 1
    try:
        line, ok = closer.propose_meeting(lead, str(p.get("when") or ""))
    except OSError as exc:
        line, ok = "Nothing was sent: %s." % exc, False
    say(line)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
