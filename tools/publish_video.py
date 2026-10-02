#!/usr/bin/env python3
"""publish_video.py - the hand that makes an unlisted film public, and the only one that can.

It prints exactly one of two things: "The film is public. <url>", or "Publishing failed:
<reason>". send_email.py's contract, for send_email.py's reason - the assistant speaks what the
hand observed rather than deciding for itself that the thing worked, and this is the second hand
in the house whose work cannot be taken back.

WHY THIS IS A HAND AND THE UPLOAD IS NOT. The upload takes a minute and lands UNLISTED - a URL
nobody has - so it runs on the server's own thread with a progress bus, behind the Doorman's
BOSS-only gate. This takes four hundred milliseconds and is the instant the film becomes visible
to the world, so it is a registry tool: the Hands' gate puts a human between this house and an
act that strangers can see, which is exactly what the gate is for. Being a hand also means it
inherits the Chain Card, the one-pending-at-a-time slot, and the handshake window - so §40's
"public only on the boss's spoken Yes" needed no new gate written for it, and "a guest's yes
leaves the film unlisted" is a property of the window's BOSS seal rather than a rule in this file.

THREE REFUSALS, AND THE FIRST IS THE ONE THAT MATTERS.

  IT WILL ONLY PUBLISH A FILM THIS HOUSE UPLOADED. A registry tool can be proposed by a language
    model, so the `video` parameter can arrive invented - a video id is sixteen characters that a
    model is entirely capable of producing from nothing. An invented id is a request to make
    somebody else's video public. So the id is checked against jobs-ledger.json, which upload()
    wrote at the moment the bytes were accepted, and an id that is not in there is refused by
    name. The ledger, and not the request, is the authority on what this house has published.
  IT WILL NOT PUBLISH WHAT IS ALREADY PUBLIC, because a second flip is a second ledger row
    recording a transition that did not happen, and an audit trail with a fictitious entry in it
    is worse than none.
  AND IT NEVER DELETES. There is no path in broadcast.py that can - see METHODS_ALLOWED - so
    there is nothing in this file that could reach one.

  in    {"video": "<id>", "title": "...", "url": "...", ...} on stdin, UTF-8
  out   one plain-ASCII line
  exit  0 public, 1 not - and every failure path ends here, named

THE CREDENTIAL NEVER TRAVELS. The registry holds none of it and the server passes none of it:
this script asks broadcast.py for a token itself, in the process already trusted with secrets/.
Nothing about it goes back up the pipe, because stdout is spoken aloud in a room.
"""
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import broadcast  # noqa: E402

NO_ROAD = "I have no road to your channel yet, Addi - connect YouTube, and I shall."
RECONNECT = ("The road to your channel has closed, Addi - Google will not renew the "
             "connection, so it wants reconnecting in the Command Panel.")
# A YOUTUBE VIDEO ID, and nothing else gets as far as the network. Eleven characters of
# URL-safe base64 is the format Google has used for every video for fifteen years.
ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")


def say(line):
    sys.stdout.buffer.write(str(line).encode("ascii", "replace") + b"\n")
    sys.stdout.buffer.flush()


def fail(reason):
    say("Publishing failed: %s" % reason)
    return 1


def main():
    raw = sys.stdin.buffer.read().decode("utf-8", "replace")
    try:
        params = json.loads(raw) if raw.strip() else {}
    except ValueError as exc:
        return fail("the parameters were not JSON (%s)" % exc)
    if not isinstance(params, dict):
        return fail("the parameters were not an object")

    video = str(params.get("video") or "").strip()
    if not video:
        return fail("no film was named")
    if not ID_RE.match(video):
        # The id is not echoed. It may have come from a model, and this house's habit is that
        # model text does not reach a log or a spoken line.
        return fail("that is not a video id I can act on")

    # ---- THE GUARD. See the module docstring's first refusal. -------------------------------
    row = broadcast.uploaded(video)
    if not row:
        return fail("I have no record of putting that film up, so I shall not make it public - "
                    "the only films I publish are the ones I uploaded myself")

    _bearer, state, why = broadcast.access()
    if state in ("absent", "no-client"):
        say(NO_ROAD)
        return 1
    if state == "reconnect":
        say(RECONNECT)
        return 1
    if why:
        return fail(why)

    scope = broadcast.scope_report()
    if not scope["canPublish"]:
        # NAMED, NOT A 403 HALFWAY THROUGH. The narrow grant can upload and cannot flip privacy,
        # and a boss who approved the narrow screen should hear that sentence rather than watch a
        # confirmation succeed and nothing change.
        return fail(scope["whyNotPublish"])

    was = broadcast.verify(video)
    if was["ok"] and was["privacy"] == broadcast.PRIVACY_PUBLIC:
        # Not an error worth the word "failed", so it exits 0: the world the boss asked for is
        # the world that exists. It is still said out loud, because he asked for a change.
        say("That film is already public. %s" % broadcast.watch_url(video))
        return 0

    got = broadcast.publish(video)
    if not got["ok"]:
        return fail(got["why"])
    # THE TRANSITION, SPOKEN. "from unlisted to public" is the whole audit fact in six words,
    # and the ledger row that broadcast.publish() just wrote carries the same two states.
    say("The film is public - %s to %s. %s"
        % (got["from"] or "unlisted", got["privacy"], got["url"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
