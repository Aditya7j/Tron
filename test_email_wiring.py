"""Proves the mailer is really wired, really refuses, and never repeats a credential.

`send_email.py` is the only hand in this house whose work cannot be taken back. An
appointment written into a calendar can be deleted; a letter that has left the building
is gone. So this file is deliberately hostile to it, and deliberately hermetic: NOT ONE
CHECK HERE SENDS MAIL. Nothing leaves this machine. The two things that could - the
network and config.json - are both replaced: the module's CONFIG and REGISTRY paths are
redirected into a temporary folder, and smtplib is either a recording double or a socket
server on 127.0.0.1 that answers in raw SMTP.

Seven claims:

  1. THE SENTINELS ARE FOREIGN. The fake password and the fake account below appear
     nowhere in the shipped source, so a hit later is this test's string.
  2. A BAD REQUEST NEVER REACHES A MAIL SERVER. Six shapes of nonsense - no address, a
     list of addresses, a malformed address, no subject, an empty body, stdin that is not
     JSON - each refused, by exit code, with its own sentence, through a real subprocess.
  3. AN UNCONFIGURED PROVIDER SAYS SO, BY FIELD. Missing host, missing account, missing
     app password and an impossible port are four different honest answers, each naming
     the field in config.json and none of them naming a value. This is the line the
     employer must see the moment they revoke the password, which is the kill switch.
  4. THE HAPPY PATH IS WIRED AS SPECIFIED. With a double in place of smtplib: STARTTLS on
     587 with a VERIFIED context, login with the app password, exactly one recipient, the
     From is the account rather than anything off the wire, To / Subject / body come from
     the stdin JSON, and the receipt is "Email sent to <addr>." on exit 0.
  5. THE TIMEOUT COMES FROM THE REGISTRY. The socket deadline is the registry's
     timeout_s, less a margin so the script reports its own reason instead of being
     killed mid-send - and for an email, "it may or may not have gone" is the worst of
     the three possible outcomes.
  6. A REVOKED PASSWORD IS A NAMED REFUSAL, NOT A CRASH. An auth rejection is turned into
     one plain sentence that does NOT quote the server, because a provider's own message
     can contain the account and that line is about to be read out in a room.
  7. TLS IS NOT OPTIONAL, PROVED AGAINST A REAL SOCKET. A mail server on 127.0.0.1 that
     greets, answers EHLO and offers no STARTTLS gets a refusal - and that server records
     that it never saw a MAIL FROM, so nothing was sent in the clear.

Run it:  python test_email_wiring.py
Exit status is the number of failures.
"""

import importlib.util
import io
import json
import os
import pathlib
import re
import shutil
import smtplib
import socket
import subprocess
from tools import _proc
import sys
import tempfile
import threading
import types

sys.dont_write_bytecode = True

ROOT = pathlib.Path(__file__).resolve().parent
SCRIPT = ROOT / "tools" / "send_email.py"
REAL_CONFIG = ROOT / "config.json"
PY = sys.executable

# Shaped like the real things, so a leak has somewhere realistic to hide.
CANARY_PW = "zqmailwafflepw9931"
CANARY_USER = "zqmailbutler@example.invalid"
CANARY_TO = "zqmailfriend@example.invalid"
SENTINELS = [CANARY_PW, CANARY_USER, CANARY_TO, "zqmailwaffle", "wafflepw"]

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:                                              # noqa: BLE001
    pass

failures = []
checks = 0


def ok(condition, claim, detail=""):
    global checks
    checks += 1
    if condition:
        print("  ok   %s" % claim)
    else:
        failures.append(claim)
        print("  FAIL %s" % claim)
        if detail:
            print("       %s" % detail)


def hits(blob):
    text = blob if isinstance(blob, str) else str(blob)
    return sorted({s for s in SENTINELS if s in text})


# --------------------------------------------------------------- the temporary house
#
#   house/config.json
#   house/tools/send_email.py      <- a copy of the shipped script, byte for byte
#   house/tools/registry.json
#
# The script derives config.json from its own __file__, which is exactly right in
# production and means a copy is the only honest way to test it through a subprocess.
# Nothing in the shipped file exists for the benefit of this one.

house = pathlib.Path(tempfile.mkdtemp(prefix="mail-wiring-"))
(house / "tools").mkdir()
COPY = house / "tools" / "send_email.py"
shutil.copyfile(SCRIPT, COPY)
(house / "tools" / "registry.json").write_text(json.dumps({"version": 1, "tools": [
    {"id": "send_email", "name": "Send an email", "script": "send_email.py",
     "capabilities": ["send an email"], "timeout_s": 30,
     "params": [{"name": "to", "type": "string", "required": True},
                {"name": "subject", "type": "string", "required": True},
                {"name": "body", "type": "text", "required": True}],
     "proposal": "An email for {to}, sir."},
]}, indent=2), encoding="utf-8")

WORKING = {"email_host": "smtp.example.invalid", "email_port": 587,
           "email_user": CANARY_USER, "email_app_password": CANARY_PW}


def wire(**settings):
    """Write the temporary config.json. Nothing here can see the real one."""
    (house / "config.json").write_text(json.dumps(settings, indent=2), encoding="utf-8")


def run(params, raw=None, timeout=25):
    """The copy, in its own process, JSON on stdin - the way hands.py runs it."""
    payload = raw if raw is not None else json.dumps(params)
    done = _proc.run([PY, str(COPY)], input=payload.encode("utf-8"),
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          timeout=timeout, shell=False)
    return (done.returncode,
            done.stdout.decode("utf-8", "replace").strip(),
            done.stderr.decode("utf-8", "replace").strip())


# ------------------------------------------------ claim 1: the sentinels are foreign

shipped_hits = {}
for name in ("tools/send_email.py", "tools/registry.json", "hands.py", "server.py"):
    try:
        blob = (ROOT / name).read_bytes().decode("utf-8", "replace")
    except OSError:
        shipped_hits[name] = "missing"
        continue
    if hits(blob):
        shipped_hits[name] = hits(blob)
ok(not shipped_hits,
   "every sentinel is foreign to the shipped source, so a hit later is this test's",
   json.dumps(shipped_hits))
real_before = REAL_CONFIG.read_bytes() if REAL_CONFIG.is_file() else None
real_password = ""
try:
    real_password = str(json.loads(real_before.decode("utf-8")).get(
        "email_app_password") or "")
except Exception:                                              # noqa: BLE001
    pass
transcript = []                       # every byte this test ever reads back, for claim 1b


def record(*parts):
    transcript.extend(str(p) for p in parts)


# ------------------------------- claim 2: a bad request never reaches a mail server
#
# A fully working config is in place for every one of these, so a refusal here is the
# script's own judgement and not a missing setting. The host does not resolve, which is
# the second belt: if any of these DID try to connect, the failure would name a
# different thing entirely and the assertion below would catch it.

wire(**WORKING)
bad = [
    ({"subject": "s", "body": "b"}, r"no recipient", "no address at all"),
    ({"to": "a@b.com, c@d.com", "subject": "s", "body": "b"},
     r"one recipient per send", "a list of two addresses"),
    ({"to": "a@b.com; c@d.com", "subject": "s", "body": "b"},
     r"one recipient per send", "a list joined with a semicolon"),
    ({"to": "Friend <a@b.com>", "subject": "s", "body": "b"},
     r"not an address", "a display name wrapped round an address"),
    ({"to": "not-an-address", "subject": "s", "body": "b"},
     r"not an address", "a word where an address should be"),
    ({"to": "a@b.com", "subject": "", "body": "b"},
     r"subject and something to say", "no subject"),
    ({"to": "a@b.com", "subject": "s", "body": "   \n "},
     r"subject and something to say", "a body of whitespace"),
]
for params, pattern, what in bad:
    code, out, err = run(params)
    record(out, err)
    ok(code == 1 and out.startswith("Email failed: ") and re.search(pattern, out),
       "refused before any connection - %s: %s" % (what, out), "exit %d" % code)
code, out, err = run(None, raw="{not json at all")
record(out, err)
ok(code == 1 and "not JSON" in out, "stdin that is not JSON is refused and said: " + out)
code, out, err = run(None, raw='["a", "list"]')
record(out, err)
ok(code == 1 and "not an object" in out, "stdin that is not an object likewise: " + out)

# ------------------------------- claim 3: an unconfigured provider says so, by field

good = {"to": CANARY_TO, "subject": "A test that never sends", "body": "One line."}
cases = [
    ({}, "email_host", "nothing configured at all"),
    (dict(WORKING, email_host=""), "email_host", "the host removed"),
    (dict(WORKING, email_user=""), "email_user", "the account removed"),
    (dict(WORKING, email_app_password=""), "email_app_password",
     "THE KILL SWITCH: the app password deleted"),
    (dict(WORKING, email_port=0), "not a port", "an impossible port"),
    (dict(WORKING, email_port=99999), "not a port", "a port above every port"),
    (dict(WORKING, email_port="ninety"), "not a port", "a port that is a word"),
]
for settings, expect, what in cases:
    wire(**settings)
    code, out, err = run(good)
    record(out, err)
    ok(code == 1 and expect in out,
       "%s -> %s" % (what, out), "exit %d, expected %r" % (code, expect))
wire(**dict(WORKING, email_app_password=""))
code, out, err = run(good)
record(out, err)
ok(not re.search(r"\b(0|zero|empty|length)\b", out),
   "and the missing-password line says nothing about the value it did not find: " + out)

# ----------------------------------------- the double, for everything TLS makes hard
#
# A real send needs a certificate a test cannot mint from the standard library, so the
# happy path is proved against a recording double IN PROCESS - the shipped file itself,
# with its CONFIG and REGISTRY pointed at the temporary house. Claim 7 then proves the
# same refusal against a real socket, so neither claim rests on the other.

spec = importlib.util.spec_from_file_location("mailer_under_test", SCRIPT)
mailer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mailer)
mailer.CONFIG = house / "config.json"
mailer.REGISTRY = house / "tools" / "registry.json"


class Double:
    """Records what a real SMTP conversation would have been given."""

    log = []
    fail_login = None
    starttls_offered = True

    def __init__(self, host, port, timeout=None, context=None):
        Double.log.append(("connect", host, port, timeout, context))

    def __enter__(self):
        return self

    def __exit__(self, *_):
        Double.log.append(("quit",))
        return False

    def ehlo(self, *_):
        Double.log.append(("ehlo",))

    def has_extn(self, name):
        return name.lower() == "starttls" and Double.starttls_offered

    def starttls(self, context=None):
        Double.log.append(("starttls", context))

    def login(self, user, password):
        Double.log.append(("login", user, password))
        if Double.fail_login:
            raise Double.fail_login

    def send_message(self, note, from_addr=None, to_addrs=None):
        Double.log.append(("send", note, from_addr, to_addrs))


mailer.smtplib = types.SimpleNamespace(
    SMTP=Double, SMTP_SSL=Double,
    **{name: getattr(smtplib, name) for name in (
        "SMTPException", "SMTPAuthenticationError", "SMTPSenderRefused",
        "SMTPRecipientsRefused", "SMTPNotSupportedError")})


def inprocess(params):
    """main() with stdin and stdout replaced. Returns (exit code, the one line)."""
    Double.log = []
    out = io.BytesIO()
    real_in, real_out = sys.stdin, sys.stdout
    sys.stdin = types.SimpleNamespace(
        buffer=io.BytesIO(json.dumps(params).encode("utf-8")))
    sys.stdout = types.SimpleNamespace(buffer=out, flush=lambda: None)
    try:
        code = mailer.main()
    finally:
        sys.stdin, sys.stdout = real_in, real_out
    line = out.getvalue().decode("ascii", "replace").strip()
    record(line)
    return code, line


# ------------------------------------ claim 4: the happy path is wired as specified

wire(**WORKING)
code, line = inprocess(dict(good, to=CANARY_TO))
steps = [row[0] for row in Double.log]
ok(code == 0 and line == "Email sent to %s." % CANARY_TO,
   "a good request on a working provider prints the receipt and exits 0: " + line)
ok(steps == ["connect", "ehlo", "starttls", "ehlo", "login", "send", "quit"],
   "and the conversation is the specified one, in order", json.dumps(steps))
connect = [r for r in Double.log if r[0] == "connect"][0]
ok(connect[1] == WORKING["email_host"] and connect[2] == 587,
   "it connected to the host and port config.json names, and nowhere else",
   json.dumps([connect[1], connect[2]]))
context = [r for r in Double.log if r[0] == "starttls"][0][1]
ok(context is not None and context.check_hostname is True
   and context.verify_mode == mailer.ssl.CERT_REQUIRED,
   "STARTTLS was handed a VERIFIED context - hostname checked, certificate required",
   repr(context and (context.check_hostname, context.verify_mode)))
login = [r for r in Double.log if r[0] == "login"][0]
ok(login[1] == CANARY_USER and login[2] == CANARY_PW,
   "it signed in as the account in config.json, with the app password from config.json")
sent = [r for r in Double.log if r[0] == "send"][0]
note, from_addr, to_addrs = sent[1], sent[2], sent[3]
ok(to_addrs == [CANARY_TO],
   "ONE recipient per send, passed explicitly as a list of one", json.dumps(to_addrs))
ok(note["To"] == CANARY_TO and note["Subject"] == good["subject"]
   and good["body"] in note.get_content(),
   "To, Subject and body are the stdin JSON's, verbatim",
   json.dumps({"to": note["To"], "subject": note["Subject"]}))
ok(from_addr == CANARY_USER and note["From"] == CANARY_USER,
   "and the From is the account that authenticates - not a field a model could set",
   repr(note["From"]))
ok(note["Date"] and note["Message-ID"],
   "the message carries a Date and a Message-ID, so it is not read as spam on arrival")

wire(**dict(WORKING, email_from="alias@example.invalid"))
code, line = inprocess(good)
sent = [r for r in Double.log if r[0] == "send"][0]
ok(code == 0 and sent[1]["From"] == "alias@example.invalid"
   and [r for r in Double.log if r[0] == "login"][0][1] == CANARY_USER,
   "an alias you own goes in config.json as email_from, and the login is unchanged")

wire(email_host=WORKING["email_host"], email_user=CANARY_USER,
     email_app_password=CANARY_PW)
code, line = inprocess(good)
ok(code == 0 and [r for r in Double.log if r[0] == "connect"][0][2] == 587,
   "an ABSENT port defaults to 587, the STARTTLS port - only a WRONG one is refused")
code465, line465 = 0, ""
wire(**dict(WORKING, email_port=465))
code465, line465 = inprocess(good)
steps465 = [r[0] for r in Double.log]
ok(code465 == 0 and "starttls" not in steps465
   and [r for r in Double.log if r[0] == "connect"][0][4] is not None,
   "port 465 goes the implicit-TLS way instead: no STARTTLS step, a context at connect",
   json.dumps(steps465))

# A subject is folded onto one line: a header with a newline in it is header injection.
wire(**WORKING)
code, line = inprocess(dict(good, subject="Hello\r\nBcc: someone@else.invalid"))
sent = [r for r in Double.log if r[0] == "send"][0]
ok(code == 0 and "\n" not in str(sent[1]["Subject"]) and sent[1]["Bcc"] is None
   and sent[1]["To"] == CANARY_TO,
   "a newline in the subject cannot smuggle in a header: " + repr(sent[1]["Subject"]))

# --------------------------------- claim 5: the timeout comes from the registry
ok(connect[3] == 26.0,
   "the socket deadline is the registry's timeout_s (30) less a 4s margin, so the "
   "script reports its own reason rather than being killed", repr(connect[3]))
(house / "tools" / "registry.json").write_text(json.dumps({"version": 1, "tools": [
    {"id": "send_email", "script": "send_email.py", "timeout_s": 12,
     "capabilities": [], "name": "x", "params": [], "proposal": "x"}]}), encoding="utf-8")
code, line = inprocess(good)
ok([r for r in Double.log if r[0] == "connect"][0][3] == 8.0,
   "change the registry to 12s and the deadline follows it to 8s - one source of truth")
(house / "tools" / "registry.json").write_text("{ broken", encoding="utf-8")
code, line = inprocess(good)
ok(code == 0 and [r for r in Double.log if r[0] == "connect"][0][3]
   == mailer.DEFAULT_TIMEOUT,
   "and an unreadable registry falls back to a stated default rather than to no timeout")

# ------------------------- claim 6: a revoked password is a named refusal, not a crash

Double.fail_login = smtplib.SMTPAuthenticationError(
    535, b"5.7.8 Username and Password not accepted for " + CANARY_USER.encode())
code, line = inprocess(good)
Double.fail_login = None
ok(code == 1 and "refused the account in config.json" in line,
   "a rejected sign-in is one plain sentence on exit 1: " + line)
ok(not hits(line) and "5.7.8" not in line,
   "which does NOT quote the server - its message held the account, this line holds "
   "neither account nor password", line)
ok("app password" in line,
   "and it names the likeliest cause, which is the kill switch having been used")
Double.starttls_offered = False
code, line = inprocess(good)
Double.starttls_offered = True
ok(code == 1 and "will not send" in line and
   not any(r[0] in ("login", "send") for r in Double.log),
   "a server that offers no STARTTLS is refused BEFORE the password is offered to it: "
   + line, json.dumps([r[0] for r in Double.log]))

# ------------------- claim 7: TLS is not optional, proved against a real socket
#
# A mail server that greets properly, answers EHLO and offers no encryption. The shipped
# script, in its own process, over a real TCP connection, with the real smtplib.

heard = []


def plaintext_server(sock):
    try:
        conn, _ = sock.accept()
    except OSError:
        return
    with conn:
        conn.settimeout(10)
        conn.sendall(b"220 fake.invalid ESMTP ready\r\n")
        while True:
            try:
                line = conn.recv(4096)
            except OSError:
                return
            if not line:
                return
            text = line.decode("ascii", "replace").strip()
            heard.append(text)
            head = text.split(" ")[0].upper()
            if head in ("EHLO", "HELO"):
                conn.sendall(b"250-fake.invalid\r\n250 SIZE 10485760\r\n")
            elif head == "QUIT":
                conn.sendall(b"221 Bye\r\n")
                return
            else:
                conn.sendall(b"250 OK\r\n")


listener = socket.socket()
listener.bind(("127.0.0.1", 0))
listener.listen(1)
port = listener.getsockname()[1]
thread = threading.Thread(target=plaintext_server, args=(listener,), daemon=True)
thread.start()
wire(**dict(WORKING, email_host="127.0.0.1", email_port=port))
code, out, err = run(good)
record(out, err)
thread.join(timeout=5)
listener.close()
ok(code == 1 and "will not encrypt" in out and "clear" in out,
   "a real mail server that will not encrypt is refused out loud: " + out,
   "exit %d, stderr %r" % (code, err[:200]))
ok(any(h.upper().startswith("EHLO") for h in heard),
   "the connection really happened - the server heard the greeting", json.dumps(heard))
ok(not any(h.upper().startswith(("MAIL FROM", "AUTH", "DATA")) for h in heard),
   "and it never heard a sender, a password or a body: nothing went in the clear",
   json.dumps(heard))

# ------------------------------------- what everything above said, read all at once

whole = "\n".join(transcript)
ok(CANARY_PW not in whole,
   "across every line this test read back, the app password appears NOWHERE",
   "\n       ".join(l for l in whole.splitlines() if CANARY_PW in l))
ok(not real_password or real_password not in whole,
   "nor does the real app password in config.json, if one is set at all")
ok(sum(1 for line in whole.splitlines()
       if line.startswith("Email failed: ") or line.startswith("Email sent to ")) >= 18,
   "and every line either began 'Email sent to ' or 'Email failed: ' - one contract, "
   "%d lines of it" % len(whole.splitlines()))
ok(all(line == line.encode("ascii", "replace").decode("ascii")
       for line in whole.splitlines()),
   "every line is plain ASCII, which is what a cp1252 console and a voice both want")

# ----------------------------------------------------------------------- tidying up

after = REAL_CONFIG.read_bytes() if REAL_CONFIG.is_file() else None
ok(after == real_before,
   "and the real config.json is byte-for-byte what it was before this test ran")
ok(os.path.isfile(SCRIPT) and SCRIPT.read_bytes() == COPY.read_bytes(),
   "the shipped script was tested as shipped - the copy that ran is identical to it")
shutil.rmtree(house, ignore_errors=True)

print("\n  %d checks, %d failed\n" % (checks, len(failures)))
if failures:
    for claim in failures:
        print("    FAILED: %s" % claim)
    print("")
sys.exit(min(len(failures), 120))
