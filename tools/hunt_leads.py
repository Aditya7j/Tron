#!/usr/bin/env python3
"""hunt_leads.py - the Hunter: find businesses in open listings, read their own sites for a public
way to reach them, and write the ones that have one into the leads book. After a yes, and
nothing else.

    echo {"what": "dentists", "where": "Pune", "count": 5} | python tools/hunt_leads.py
    Found all 5 dentists in Pune, sir - written to the leads book as H-0001 to H-0005, ...

THE CONTRACT, as tools/selftest.py states it:

  in    {"what": "...", "where": "...", "count": N, "asked": N} on stdin, UTF-8 - the
        employer's own sentence, parsed by hunter.parse_request() in server.hunt_asked().
        Door-bound to "hunt": no model fills these in and no tag can raise this hand.
  out   ONE line on stdout - what was written, what was skipped and why, and from where.
        The progress of the hunt goes to stderr, which nobody reads aloud.
  exit  0 the hunt ran and the line says what it found, nothing included. 1 it could not
        run - the card was malformed, or every source refused - and the line says which.

WHAT IT SENDS: nothing to anyone. It reads OpenStreetMap, Wikidata and the businesses' own
pages under an honest User-Agent, paced, and it writes leads.json. Every row it writes has
status "new"; see hunter.py for the rest of the rules, all of which apply here because all
of the work is done there.
"""
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import hunter                                                  # noqa: E402


def main():
    # BOTH STREAMS, as in every hand since ₹ arrived mis-decoded from a stdin in the ANSI
    # codepage: a town or a niche may carry a character cp1252 does not have.
    try:
        sys.stdin.reconfigure(encoding="utf-8")
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:                                          # noqa: BLE001
        pass
    try:
        p = json.loads(sys.stdin.read() or "{}")
    except ValueError:
        print("The hunt's card would not parse, so nothing was looked for.")
        return 1
    if not isinstance(p, dict):
        print("The hunt's card would not parse, so nothing was looked for.")
        return 1
    what = " ".join(str(p.get("what") or "").split())[:80]
    where = " ".join(str(p.get("where") or "").split())[:80]
    count = p.get("count")
    if not what or not where:
        print("The card names no kind of business or no place, so nothing was looked for.")
        return 1
    if type(count) is not int or not 1 <= count <= hunter.MAX_COUNT:
        print("A hunt is for between 1 and %d leads, sir, not %r, so nothing was looked for."
              % (hunter.MAX_COUNT, count))
        return 1
    wire = hunter.Wire()
    try:
        r = hunter.hunt(what, where, count, wire=wire,
                        log=lambda line: sys.stderr.write("  hunt: %s\n" % line))
    except (OSError, ValueError) as exc:
        print("The leads book could not be written (%s), sir, so the hunt stopped."
              % type(exc).__name__)
        return 1
    print(hunter.report(r))
    sys.stderr.write("  hunt: %d request(s), %d written, refused by: %s\n"
                     % (r["requests"], len(r["added"]), ", ".join(wire.refused) or "nobody"))
    # Every source refusing is a failure to hunt, not a hunt that found nothing.
    if not r["added"] and not r["candidates"] and {"openstreetmap", "wikidata"} <= set(
            wire.refused):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
