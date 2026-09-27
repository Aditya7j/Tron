#!/usr/bin/env python3
"""send_email.py - the hand that reaches outside the house, now through Gmail's own API.

It prints exactly one of two things: "Email sent to <address>.", or "Email failed:
<reason>". That is the whole contract, unchanged. The assistant speaks the line rather than
deciding for itself whether the thing worked, because a hand that claims a success it did
not observe is a liar - and this is the one hand whose work cannot be taken back.

WHAT CHANGED. This used to log in to smtp.gmail.com with a sixteen-character app password
out of config.json. It now builds the same RFC 2822 message and hands it to Gmail v1
users.messages.send over an OAuth token, as the connected account. Three things improve and
one gets harder, and it is worth knowing which is which:

  + There is no long-lived password on this disk any more. The grant is scoped to
    gmail.send and gmail.compose - it cannot READ a single message in the mailbox - and the
    employer can revoke it from his Google account page in one click, without touching this
    machine, and the very next attempt says so out loud.
  + Gmail stamps the sent copy into Sent properly, because it is Gmail doing the sending
    rather than a stranger authenticating as him.
  + A send now returns Google's own message id, so the ledger records a thing that exists
    on Google's side rather than a local claim of success.
  - The failure surface moved. "the app password was deleted" used to be the interesting
    error; now it is "the token was revoked" and "the refresh failed", which are different
    sentences and are written out below rather than collapsed into one.

THE CREDENTIAL NEVER TRAVELS. The registry holds none of it and the server passes none of
it: this script asks google_api for a token itself, in the process already trusted with
secrets/. Nothing about it goes back up the pipe, because stdout is spoken aloud in a room.

  in    {"to": "...", "subject": "...", "body": "..."} on stdin, UTF-8, one recipient
  out   one plain-ASCII line
  exit  0 sent, 1 not sent - and every failure path ends here, named

NO ATTACHMENTS, AND IT SAYS SO. Nothing in this version can attach a file. That is a
refusal with a sentence, not a crash and not a silent drop: an employer who asked for the
quarterly PDF to go with it must hear that it did not, before he assumes it did.
"""
import json
import pathlib
import re
import sys
from email.message import EmailMessage
from email.utils import formatdate, make_msgid

ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import google_api  # noqa: E402

# Deliberately strict, and deliberately excluding the comma, the semicolon and every
# bracket: an address that cannot exist is a typo, and a typo is better caught here than
# by a stranger's mail server. Anything that looks like a list is refused outright below.
ADDRESS_RE = re.compile(r"^[^@\s,;:<>\"'()\[\]]{1,64}@[A-Za-z0-9.-]{1,255}\.[A-Za-z]{2,24}$")
ATTACHMENT_KEYS = ("attachment", "attachments", "attach", "file", "files", "path")

NO_ROAD = "I have no road to your mail yet, Addi - Connect Google, and I shall."
RECONNECT = ("The road to your mail has closed, Addi - Google will not renew the "
             "connection, so it wants reconnecting in the Command Panel.")


def say(line):
    sys.stdout.buffer.write(str(line).encode("ascii", "replace") + b"\n")
    sys.stdout.buffer.flush()


def fail(reason):
    say("Email failed: %s" % reason)
    return 1


def build(to, subject, body, sender):
    """The RFC 2822 bytes, and nothing Gmail has to guess at.

    Date and Message-ID are set here rather than left to Google so that the message this
    process serialized is the message that was sent - which is what makes the draft probe
    in google_hands_proof a real test of serialization and not just of transport.
    """
    note = EmailMessage()
    note["To"] = to
    if sender:
        note["From"] = sender
    note["Subject"] = subject
    note["Date"] = formatdate(localtime=True)
    note["Message-ID"] = make_msgid()
    note.set_content(body)
    return note.as_bytes()


def main():
    raw = sys.stdin.buffer.read().decode("utf-8", "replace")
    try:
        params = json.loads(raw) if raw.strip() else {}
    except ValueError as exc:
        return fail("the parameters were not JSON (%s)" % exc)
    if not isinstance(params, dict):
        return fail("the parameters were not an object")

    for key in ATTACHMENT_KEYS:
        if params.get(key):
            # Said, not swallowed. The registry has no attachment parameter, so this is
            # reachable only by hand or by a future schema - and on that day the employer
            # gets a sentence instead of a message that quietly went without its file.
            return fail("I cannot attach a file to an email yet - the message itself can "
                        "go, but nothing can travel with it, so I have sent nothing")

    to = str(params.get("to") or "").strip()
    subject = " ".join(str(params.get("subject") or "").split())[:300]
    body = str(params.get("body") or "")
    if not to:
        return fail("no recipient was given")
    if re.search(r"[,;]", to):
        # One recipient per send. Not a limitation - a confirmation dialogue that showed
        # one address and sent to four would make the gate a decoration.
        return fail("one recipient per send, and that is a list")
    if not ADDRESS_RE.match(to):
        return fail("that is not an address I can send to")
    if not subject or not body.strip():
        return fail("an email needs a subject and something to say")

    _bearer, state, why = google_api.access()
    if state in ("absent", "no-client"):
        say(NO_ROAD)
        return 1
    if state == "reconnect":
        say(RECONNECT)
        return 1
    if why:
        return fail(why)

    # The From is the account that authenticated and is not a field the model may set:
    # Gmail will not send as an identity it has not verified, so a supplied sender could
    # only ever be a bounce or a forgery. An empty one lets Gmail fill it in itself.
    sender = str((google_api.token() or {}).get("email") or "")
    sent, err = google_api.send_message(build(to, subject, body, sender))
    if err:
        return fail(err)
    message_id = str((sent or {}).get("id") or "")
    if not message_id:
        return fail("Gmail accepted it but named no message, so I cannot prove it went")
    say("Email sent to %s. Google's id for it is %s." % (to, message_id))
    return 0


if __name__ == "__main__":
    sys.exit(main())
