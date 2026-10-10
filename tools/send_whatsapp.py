#!/usr/bin/env python3
"""send_whatsapp.py - the hand that reaches the employer's own pocket, through Meta's
WhatsApp Cloud API.

It prints exactly one of two things: "WhatsApp accepted it, sir - Meta's id for it is <id>,
but I cannot yet confirm it arrived.", or "WhatsApp failed: <reason>." That is the whole
contract, and it is send_email's contract on purpose. The assistant speaks the line rather
than deciding for itself whether the thing worked, because a hand that claims a success it
did not observe is a liar - and a message that has landed on a phone cannot be called back
off it. Which is exactly why the good line says "accepted" and not "sent": acceptance is
all this script ever observes (see THE 24-HOUR WINDOW below).

WHY IT EXISTS. Email is the road to other people; this is the road to one person. The
recipient is not a parameter - it is meta_whatsapp_to in config.json, the employer's own
number, and nothing the brain says can change it. That is what makes it safe to give this
hand a reporter's job later: the worst a confused model can do here is tell the employer
something that did not need saying, never tell a stranger something they should not.

WHY NOT TWILIO. The first version of this hand went through Twilio's sandbox, and the
sandbox sender refused every free-form Body with 21654 "ContentSid Required" - even eleven
seconds after the phone had written to it, inside an open session - while the Content API
that would have listed a template answered "not available on a Trial account". A hand
that could only ever send an appointment reminder was not a hand, so it moved here.

THE TOKEN DIES IN A DAY, AND THAT IS EXPECTED. meta_whatsapp_token is the temporary access
token from the app's API Setup page, and Meta expires it 24 hours after it was generated.
When this hand starts saying the token has expired, nothing here broke: paste a fresh one
into config.json. A permanent System User token ends that, and is a setup step, not code.

THE 24-HOUR WINDOW, WHICH A REPORTER WILL MEET FIRST. Free-form text may only go to someone
who has written to the business number in the last 24 hours; outside that window WhatsApp
wants an approved template, and Meta's code for the refusal is 131047. This script names
131047 in plain words when Meta says it in the reply. But Meta can also accept the message
- a 200 and an id - and only report 131047 afterwards, to a status webhook this house does
not run. In that case the line says "accepted" with Meta's id and nothing arrives. The id
is proof that Meta took the message, not that the phone buzzed - and on 10 October 2026
three accepted sends in a row, one of them a template, never reached the phone at all. A
temporary webhook, pointed at a tunnel for ten minutes and then taken down, caught the
reason on a fourth: status "failed", code 131031, "Business account has been locked". That
is Meta's lock on the WhatsApp Business Account, not anything this script sends, and it is
cleared in Meta's Business Support Home, not here.

THE CREDENTIAL NEVER TRAVELS. The registry holds none of it and the server passes none of
it: this script reads config.json itself, fresh on every run, in the process already trusted
with it - the same discipline as ingest.settings(). Nothing about it goes back up the pipe,
because stdout is spoken aloud in a room, and that includes Meta's own error text; scrub()
takes the token out of anything Meta says before anything is said.

  in    {"body": "..."} on stdin, UTF-8
  out   one plain-ASCII line
  exit  0 sent, 1 not sent - and every failure path ends here, named

Standard library only, like google_api.py: one JSON POST does not earn a dependency.
"""
import json
import os
import re
import socket
import sys
import urllib.error
import urllib.request

# This script is run with cwd=tools/ by hands.py, so every path here is derived from
# __file__ and never from the working directory.
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CONFIG_PATH = os.path.join(ROOT, "config.json")

API = "https://graph.facebook.com/v23.0/%s/messages"
# meta_waba_id is not used by the send itself. It is required anyway, because a config.json
# with the account id missing is a half-finished setup, and that is better said now than
# on the day something else needs it.
KEYS = ("meta_whatsapp_token", "meta_phone_number_id", "meta_waba_id", "meta_whatsapp_to")
# Under the registry's timeout_s of 20, so a hung connection is reported by this script in
# its own words rather than killed by hands.py and reported as a timeout with no reason.
TIMEOUT_S = 15

NO_ROAD = "I have no road to WhatsApp yet - add Meta credentials to config.json"
WINDOW_SHUT = ("WhatsApp will not take free text - the employer has not written to the "
               "business number in the last 24 hours, so this needs an approved template "
               "(Meta code 131047)")
# Meta's own words go in the blank, because code 190 covers more than expiry: "Session has
# expired" is the 24-hour clock, "could not be decrypted" is a token damaged in the paste,
# and the employer fixes both the same way but should not be told the wrong story.
TOKEN_DEAD = ("Meta would not accept the access token (code 190: %s) - the temporary one "
              "lasts 24 hours, so paste a fresh one into config.json")


def say(line):
    sys.stdout.buffer.write(str(line).encode("ascii", "replace") + b"\n")
    sys.stdout.buffer.flush()


def fail(reason):
    # One full stop, whoever wrote the reason: Meta's messages sometimes end with one.
    say("WhatsApp failed: %s." % str(reason).strip().rstrip("."))
    return 1


def road():
    """The four Meta keys from config.json, read fresh, or None if any is missing.

    All four or nothing. A sender without a recipient is not three quarters of a road, and
    reporting "no road" once is kinder than reporting the first missing key and then, after
    the employer fixes it, the second.
    """
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as fh:
            cfg = json.load(fh)
        if not isinstance(cfg, dict):
            return None
    except Exception:                                          # noqa: BLE001
        return None
    found = {key: str(cfg.get(key) or "").strip() for key in KEYS}
    return found if all(found.values()) else None


def scrub(text, keys):
    """Meta's words, with the token not left in them, flattened to one line."""
    said = " ".join(str(text or "").split())
    if keys.get("meta_whatsapp_token"):
        said = said.replace(keys["meta_whatsapp_token"], "[access token]")
    return said[:300]


def refused(exc, keys):
    """The real reason out of a Graph API error, not the status line.

    Meta answers every refusal with {"error": {"code", "message", "error_data":
    {"details"}}}, and the code is what decides the sentence: 131047 and 190 are the two
    this hand WILL meet in ordinary life, so they get plain words of their own; anything
    else is Meta's message verbatim (token scrubbed), with the code beside it.
    """
    try:
        data = json.loads(exc.read().decode("utf-8", "replace"))
    except Exception:                                          # noqa: BLE001
        data = None
    error = data.get("error") if isinstance(data, dict) else None
    if not isinstance(error, dict):
        return "Meta refused it with HTTP %s and gave no reason" % exc.code
    code = error.get("code")
    if code == 131047:
        return WINDOW_SHUT
    details = (error.get("error_data") or {}).get("details") if isinstance(
        error.get("error_data"), dict) else ""
    message = str(error.get("message") or "no message")
    if details and details not in message:
        message = "%s - %s" % (message.rstrip("."), details)
    if code == 190:
        return TOKEN_DEAD % scrub(message, keys).rstrip(".")
    return "Meta refused it (HTTP %s, code %s): %s" % (exc.code, code if code else "none",
                                                     scrub(message, keys))


def main():
    raw = sys.stdin.buffer.read().decode("utf-8", "replace")
    try:
        params = json.loads(raw) if raw.strip() else {}
    except ValueError as exc:
        return fail("the parameters were not JSON (%s)" % exc)
    if not isinstance(params, dict):
        return fail("the parameters were not an object")

    body = str(params.get("body") or "")
    if not body.strip():
        return fail("there was nothing to say - the message body was empty")

    keys = road()
    if keys is None:
        return fail(NO_ROAD)
    # Both ids go into a URL or are read as one, so a stray character is a setup error to
    # be named, not something to be quoted into a path.
    for key in ("meta_phone_number_id", "meta_waba_id"):
        if not keys[key].isdigit():
            return fail("%s in config.json should be digits only, and is not" % key)
    # Meta wants the number as digits with the country code and no plus; config.json may
    # reasonably hold "+91 62901 12457", so it is read the way a human wrote it.
    to = re.sub(r"\D", "", keys["meta_whatsapp_to"])
    if not 8 <= len(to) <= 15:
        return fail("meta_whatsapp_to in config.json is not a phone number with its country "
                    "code")

    payload = json.dumps({"messaging_product": "whatsapp", "to": to, "type": "text",
                          "text": {"body": body}}).encode("utf-8")
    request = urllib.request.Request(
        API % keys["meta_phone_number_id"], data=payload, method="POST",
        headers={"Authorization": "Bearer " + keys["meta_whatsapp_token"],
                 "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_S) as reply:
            answer = reply.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return fail(refused(exc, keys))
    except urllib.error.URLError as exc:
        # A timeout while CONNECTING arrives wrapped in a URLError, one while READING
        # arrives bare (below); both are the same sentence to the employer.
        if not isinstance(exc.reason, (socket.timeout, TimeoutError)):
            return fail("I could not reach Meta (%s)" % scrub(exc.reason, keys))
        return fail("Meta did not answer within %d seconds, so I cannot say it went"
                    % TIMEOUT_S)
    except (socket.timeout, TimeoutError):
        return fail("Meta did not answer within %d seconds, so I cannot say it went"
                    % TIMEOUT_S)
    except OSError as exc:
        return fail("the connection to Meta broke (%s)" % scrub(exc, keys))

    try:
        messages = (json.loads(answer) or {}).get("messages") or []
        message_id = str((messages[0] or {}).get("id") or "")
    except (ValueError, AttributeError, IndexError, TypeError):
        message_id = ""
    if not message_id:
        return fail("Meta accepted it but named no message, so I cannot prove it went")
    # "Accepted", never "sent": on 10 October 2026 three sends in a row came back 200 with an
    # id and not one reached the phone. The id stays in the line because it is the only
    # thing that can be matched against Meta's delivery status later.
    say("WhatsApp accepted it, sir - Meta's id for it is %s, but I cannot yet confirm it "
        "arrived." % message_id)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:                                   # noqa: BLE001
        # The last net. Every path above is meant to end in a named sentence; this one
        # exists so that a path nobody foresaw still ends in one line and exit 1, not a
        # traceback read aloud.
        sys.exit(fail("something unforeseen went wrong (%s)" % type(exc).__name__))
