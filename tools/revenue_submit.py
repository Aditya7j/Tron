#!/usr/bin/env python3
"""revenue_submit.py - the one checkpoint: reviewed work goes to the client, after a yes.

    echo {"job": "R-0003"} | python tools/revenue_submit.py
    Submitted Landing page fix to the client on Freelancer.com, sir - 2 files. ...

THE CONTRACT, as tools/selftest.py states it:

  in    {"job": "R-0003"} on stdin, UTF-8 - the job server.revenue_asked() found READY. Door-bound
        to "revenue": no model names it.
  out   ONE line on stdout: what was delivered and where - or why nothing was.
  exit  0 the delivery was pressed (the line says whether the platform confirmed it). 1 nothing
        was sent, or the run was stopped.

WHAT GOES: every file in revenue-work/R-xxxx/ as the employer left it - his fixes included -
except REVIEW.txt and the -preview.png images, with DELIVERY-NOTE.txt as the message. Each file's
sha256 is logged before the press. A delivery is never retried on its own: a press whose outcome
is unknown may have landed. Ctrl+M is armed for the whole run, as in every Operator hand.
"""
import json
import pathlib
import re
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
        say("The submit card would not parse, so nothing was sent.")
        return 1
    job = str((p if isinstance(p, dict) else {}).get("job") or "")
    if not re.fullmatch(r"R-\d{4,5}", job):
        say("%r is not a job number, so nothing was sent." % job[:20])
        return 1
    line, ok = revenue.submit(job)
    say(line)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
