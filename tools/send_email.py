#!/usr/bin/env python3
"""send_email.py - the hand that reaches outside the house, and now it really does.

It prints exactly one of two things: "Email sent to <address>.", or "Email failed:
<reason>". That is the whole contract. The assistant speaks the line rather than deciding
for itself whether the thing worked, because a hand that claims a success it did not
observe is a liar - and this is the one hand whose work cannot be taken back.

THE CREDENTIAL NEVER TRAVELS. The registry holds none of it and the server passes none of
it: this script reads config.json itself, from the project root, in the process that is
already trusted with it. Nothing about the account - not the password, not its length,
not its shape - goes back up the pipe, because stdout is spoken aloud in a room. The four
settings, in config.json and nowhere else:

  "email_host": "smtp.gmail.com",
  "email_port": 587,
  "email_user": "you@gmail.com",
  "email_app_password": "abcdefghijklmnop"      <- a Gmail APP PASSWORD, 16 characters

An app password is not your account password and must never be. Google Account ->
Security -> 2-Step Verification -> App passwords. Deleting it there is the kill switch:
this hand goes dead within a second, from Google's side, without touching this machine -
and the next attempt says so out loud instead of pretending.

  in    {"to": "...", "subject": "...", "body": "..."} on stdin, UTF-8, one recipient
  out   one plain-ASCII line
  exit  0 sent, 1 not sent - and every failure path ends here, named

TLS IS NOT OPTIONAL. Port 587 is STARTTLS and port 465 is implicit TLS; both use a
verified default context, and a server that will not encrypt gets a refusal rather than a
plaintext send. There is no flag in this file to turn that off, which is the point.
"""
import json
import pathlib
import re
import smtplib
import socket
import ssl
import sys
from email.message import EmailMessage
from email.utils import formatdate, make_msgid

HERE = pathlib.Path(__file__).resolve()
CONFIG = HERE.parent.parent / "config.json"
REGISTRY = HERE.parent / "registry.json"
# Deliberately strict, and deliberately excluding the comma, the semicolon and every
# bracket: an address that cannot exist is a typo, and a typo is better caught here than
# by a stranger's mail server. Anything that looks like a list is refused outright below.
ADDRESS_RE = re.compile(r"^[^@\s,;:<>\"'()\[\]]{1,64}@[A-Za-z0-9.-]{1,255}\.[A-Za-z]{2,24}$")
DEFAULT_TIMEOUT = 20.0


def say(line):
    """One line, ASCII only. cp1252 consoles and speech synthesis both prefer it."""
    sys.stdout.buffer.write(str(line).encode("ascii", "replace") + b"\n")
    sys.stdout.buffer.flush()


def fail(reason):
    say("Email failed: %s" % reason)
    return 1


def config():
    try:
        data = json.loads(CONFIG.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def budget():
    """This tool's own timeout_s, read from the registry that declares it.

    The registry is the single source of truth about how long this hand may take, so the
    socket takes its deadline from there rather than from a number invented in this file.
    A few seconds are held back: if the network is going to hang, the script wants to
    report WHY with its own sentence, rather than be killed by the executor and reported
    as "it may or may not have finished" - which, for an email, is the worst of the three
    possible outcomes.
    """
    try:
        data = json.loads(REGISTRY.read_text(encoding="utf-8"))
        for tool in data.get("tools") or []:
            if isinstance(tool, dict) and str(tool.get("script") or "") == HERE.name:
                return max(5.0, min(120.0, float(tool["timeout_s"]) - 4.0))
    except (OSError, ValueError, TypeError, KeyError):
        pass
    return DEFAULT_TIMEOUT


def secure():
    """A verified context, asserted rather than assumed."""
    context = ssl.create_default_context()
    context.check_hostname = True
    context.verify_mode = ssl.CERT_REQUIRED
    return context


def main():
    raw = sys.stdin.buffer.read().decode("utf-8", "replace")
    try:
        params = json.loads(raw) if raw.strip() else {}
    except ValueError as exc:
        return fail("the parameters were not JSON (%s)" % exc)
    if not isinstance(params, dict):
        return fail("the parameters were not an object")

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

    cfg = config()
    host = str(cfg.get("email_host") or "").strip()
    user = str(cfg.get("email_user") or "").strip()
    password = str(cfg.get("email_app_password") or "")
    # An ABSENT port is a kindness and defaults to 587. A port that is present and is not
    # a port is a mistake, and gets said out loud rather than quietly replaced: choosing a
    # different port than the one written down is exactly the sort of helpfulness that
    # ends with a message going somewhere nobody chose.
    raw_port = cfg.get("email_port", 587)
    if raw_port is None or (isinstance(raw_port, str) and not raw_port.strip()):
        raw_port = 587
    try:
        port = int(str(raw_port).strip())
    except (TypeError, ValueError):
        port = -1
    # The From is the account that authenticates, and not a field on the wire: Gmail
    # rejects a From it has not verified, so a model-supplied sender could only ever be a
    # bounce or a forgery. An alias you own goes in config.json as "email_from".
    sender = str(cfg.get("email_from") or user).strip()

    # Three separate honest answers, because "it didn't work" is not an answer. Each names
    # the field and not one of them names a value.
    if not host:
        return fail("no email provider is configured in config.json (email_host)")
    if not user or not sender:
        return fail("no email account is configured in config.json (email_user)")
    if not password:
        return fail("no app password is set in config.json (email_app_password)")
    if not 1 <= port <= 65535:
        return fail("the email_port in config.json is not a port")

    note = EmailMessage()
    note["To"] = to
    note["From"] = sender
    note["Subject"] = subject
    note["Date"] = formatdate(localtime=True)
    note["Message-ID"] = make_msgid()
    note.set_content(body)

    seconds = budget()
    try:
        if port == 465:
            with smtplib.SMTP_SSL(host, port, timeout=seconds, context=secure()) as smtp:
                smtp.login(user, password)
                smtp.send_message(note, from_addr=sender, to_addrs=[to])
        else:
            with smtplib.SMTP(host, port, timeout=seconds) as smtp:
                smtp.ehlo()
                if not smtp.has_extn("starttls"):
                    return fail("that mail server will not encrypt, and I will not send "
                                "in the clear")
                smtp.starttls(context=secure())
                smtp.ehlo()
                smtp.login(user, password)
                smtp.send_message(note, from_addr=sender, to_addrs=[to])
    except smtplib.SMTPAuthenticationError:
        # Named without being quoted: the provider's own message can contain the account,
        # and this line is about to be read out in a room.
        return fail("the mail server refused the account in config.json - if the app "
                    "password was deleted, that is exactly what this looks like")
    except smtplib.SMTPSenderRefused:
        return fail("the mail server refused the sender in config.json")
    except smtplib.SMTPRecipientsRefused:
        return fail("the mail server refused that recipient")
    except smtplib.SMTPNotSupportedError as exc:
        return fail("the mail server would not do what was asked (%s)" % str(exc)[:100])
    except ssl.SSLCertVerificationError:
        return fail("that mail server's certificate did not verify, so I stopped")
    except (socket.timeout, TimeoutError):
        return fail("the mail server did not answer within %ds" % seconds)
    except socket.gaierror:
        return fail("the email_host in config.json does not resolve")
    except (smtplib.SMTPException, ssl.SSLError, OSError) as exc:
        return fail("%s (%s)" % (type(exc).__name__, str(exc)[:120]))
    say("Email sent to %s." % to)
    return 0


if __name__ == "__main__":
    sys.exit(main())
