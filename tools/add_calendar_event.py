#!/usr/bin/env python3
"""add_calendar_event.py - one event into the employer's real Google calendar.

WHAT CHANGED, AND WHY IT IS WORTH SAYING OUT LOUD. This hand used to append a line to
calendar.json in the project root: honest, contained, and not a calendar. Nobody's phone
ever rang because of it. It now calls Calendar API v3 events.insert on the primary
calendar, which means the blast radius of "remind me to call the client at four" is no
longer one file on one disk - it is an entry that appears on every device the employer
owns. The gate in front of it is unchanged and is now the only thing standing between a
model's guess and a real diary, which is why the confirmation card shows the human reading
AND the exact stamps that will be sent.

calendar.json IS RETIRED. This file neither reads nor writes it. It is not consulted as a
cache, not written as a mirror, and not read as a fallback: a fallback would mean a
failed send could look like a success, which is the one outcome that must be impossible.
The old file may be deleted whenever the boss likes.

  in    {"title": "...", "start": "...", "end": "...", "description": "..."} on stdin
        start/end are ISO-8601 - "2026-09-28T16:00" or "2026-09-28" for a whole day.
        end is optional and defaults to half an hour, which is SHOWN on the card.
  out   one plain-ASCII line, which is the only thing the assistant may claim
  exit  0 written, 1 not written - and every failure path ends here, named

THE CREDENTIAL NEVER TRAVELS, exactly as with the old app password: the server passes no
token and the registry holds none. This script asks google_api for one, in the process
that is already trusted with secrets/, and nothing about it - not the token, not its
length, not its shape - goes back up the pipe, because stdout is spoken aloud in a room.
"""
import json
import pathlib
import sys

# The project root, from THIS file rather than from the working directory: the server runs
# tools with cwd set to tools/ and a human runs them from the root.
ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import google_api  # noqa: E402  (after the path is right, and deliberately)

# THE THREE REFUSALS, WRITTEN DOWN RATHER THAN IMPROVISED. Each one says what is wrong and
# what would fix it, in that order, because a refusal that does not name its remedy just
# sounds like a machine saying no. ASCII only: this line is handed to a speech synthesiser
# and printed on a cp1252 console, so the dash is a hyphen and not an em dash.
NO_ROAD = ("I have no road to your calendar yet, Addi - Connect Google, and I shall.")
RECONNECT = ("The road to your calendar has closed, Addi - Google will not renew the "
             "connection, so it wants reconnecting in the Command Panel.")


def say(line):
    sys.stdout.buffer.write(str(line).encode("ascii", "replace") + b"\n")
    sys.stdout.buffer.flush()


def fail(reason):
    say("Calendar failed: %s" % reason)
    return 1


def main():
    raw = sys.stdin.buffer.read().decode("utf-8", "replace")
    try:
        params = json.loads(raw) if raw.strip() else {}
    except ValueError as exc:
        return fail("the parameters were not JSON (%s)" % exc)
    if not isinstance(params, dict):
        return fail("the parameters were not an object")

    title = str(params.get("title") or "").strip()[:200]
    start = str(params.get("start") or "").strip()[:64]
    end = str(params.get("end") or "").strip()[:64]
    description = str(params.get("description") or "").strip()[:2000]
    if not title:
        return fail("an event needs something to be called")
    if not start:
        return fail("an event needs a time to start")

    # THE STAMPS ARE CHECKED BEFORE THE CONNECTION IS. A malformed time is the employer's
    # sentence to hear about immediately; making them wait for a network round trip to be
    # told "that is not a date" would be slower and no more informative.
    start_obj, end_obj, when, duration, err = google_api.event_times(start, end)
    if err:
        return fail(err)

    # AND THE STATE OF THE CONNECTION BEFORE ANYTHING IS SENT, so that "not connected" is
    # its own sentence rather than an HTTP error dressed up as one.
    _bearer, state, why = google_api.access()
    if state == "absent" or state == "no-client":
        say(NO_ROAD)
        return 1
    if state == "reconnect":
        say(RECONNECT)
        return 1
    if why:
        # Connected, but the refresh itself could not be completed - the network, usually.
        # Named plainly, and nothing is retried silently.
        return fail(why)

    event, err = google_api.insert_event(title, start_obj, end_obj, description)
    if err:
        return fail(err)
    event_id = str((event or {}).get("id") or "")
    if not event_id:
        return fail("Google accepted it but named no event, so I cannot prove it is there")
    # THE RECEIPT CARRIES GOOGLE'S OWN ID. The server did not make this number up and could
    # not have: it is the proof that the event exists somewhere other than this machine,
    # and it is what a harness reads back with events.get.
    say("Written into your Google calendar: %s, %s, %s. Google's id for it is %s."
        % (title, when, duration, event_id))
    return 0


if __name__ == "__main__":
    sys.exit(main())
