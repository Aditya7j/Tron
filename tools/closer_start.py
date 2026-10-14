#!/usr/bin/env python3
"""closer_start.py - the Closer's on-switch, and the only card the Closer's autonomy has. After a
yes, and nothing else.

    echo {"daily": 10} | python tools/closer_start.py
    The Closer is on, sir - it will email up to 10 new leads a day and answer their replies ...

THE CONTRACT, as tools/selftest.py states it:

  in    {"daily": N} on stdin, UTF-8 - the cap the employer saw on the card, from config.json's
        closer block via server.closer_asked(). Door-bound to "closer": no model fills it in.
  out   ONE line on stdout: on, and what that means - or why it stayed off.
  exit  0 the switch is on. 1 it is not, and the line says which thing is missing.

WHAT IT SENDS: nothing itself. It writes closer-state.json; the daemon in the server reads it on
its next look (every few seconds) and starts working. It refuses to turn on without an offer
sheet - with nothing to say about what is offered, any cold email would be invented - and without
a Google grant that can both send and read, because a Closer that cannot read the replies to what
it sent is a mass mailer.
"""
import json
import pathlib
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
        say("The Closer's card would not parse, so it stayed off.")
        return 1
    daily = p.get("daily") if isinstance(p, dict) else None
    if type(daily) is not int or not 1 <= daily <= closer.HARD_DAILY_MAX:
        say("The Closer writes between 1 and %d cold emails a day, not %r, so it stayed off."
            % (closer.HARD_DAILY_MAX, daily))
        return 1
    _s, problems = closer.settings()
    if problems:
        say("The Closer stayed off: %s." % problems[0])
        return 1
    why = closer.google_ready()
    if why:
        say("The Closer stayed off: %s." % why)
        return 1
    try:
        closer.read_log()
        closer.switch(True, "card", daily=daily)
    except OSError as exc:
        say("The Closer stayed off: %s." % exc)
        return 1
    say("The Closer is on, sir - up to %d cold email%s a day to new leads, and it reads and "
        "answers their replies on its own. Every send is in closer-log.json; say \"stop the "
        "closer\" to halt it, or \"today's leads\" for the report."
        % (daily, "" if daily == 1 else "s"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
