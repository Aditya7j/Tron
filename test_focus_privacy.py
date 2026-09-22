"""Proves that no app identity and no tab identity can appear in focus state.

This is the test the privacy claim rests on, so it is written to be hostile rather
than reassuring. It feeds the reader identities chosen here - unmistakable sentinel
strings that could not occur by accident - drives a whole session through arming,
locking, drifting, nagging, excusing and finishing, and after every single step it
serialises exactly what a browser would receive and hunts for them.

Three separate claims, because "no leak" is really three different promises:

  1. NOTHING RECOGNISABLE GETS OUT. The sentinels appear nowhere in the state, in
     any spelling, at any depth, in keys or in values - nor in the ledger on disk.
  2. NOTHING UNRECOGNISABLE GETS OUT EITHER. Every string that leaves is checked
     against LINE_REGISTRY, so it is not enough for a leak to be unfamiliar - text
     that is not a known template with numbers in it fails. This is what catches a
     hash, a truncation, or a base64 of an app name, none of which would trip (1).
  3. THE SHAPE CANNOT DRIFT. The key set must equal PUBLIC_KEYS exactly, so a new
     field cannot arrive quietly, and the reader is searched for plaintext held in
     an attribute where a later refactor might expose it.

Run it:  python test_focus_privacy.py
Exit status is the number of failures.
"""

import inspect
import json
import os
import re
import socket
import struct
import sys
import tempfile
import threading
import urllib.parse

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import focus                                                   # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:                                              # noqa: BLE001
    pass

# The identities under test. Deliberately shaped like the real thing - an
# executable, a work host, a second app, and one with characters that would break
# a naive serialiser - so a leak has somewhere realistic to hide.
APP_TARGET = "zqxsentinelapp.exe"
HOST_TARGET = "zqxsentinelhost.example.com"
APP_ELSEWHERE = "zqxdistractionapp.exe"
HOST_ELSEWHERE = "zqxdistractionhost.example.net"
APP_WEIRD = 'zqx"quote\\slash<tag>.exe'
HOST_WEIRD = "zqx-unicode-ümläut.example"
# Not in CHROME_FAMILY below, so it exercises the one surface with no site at all:
# "lock the app" is a whole outcome of the re-target and needs its own identity.
APP_NATIVE = "zqxnativeeditor.exe"
# The tab the CARD has to find while the OS insists the card itself is in front.
HOST_BEHIND = "zqxbehindthecard.example.org"

SENTINELS = [APP_TARGET, HOST_TARGET, APP_ELSEWHERE, HOST_ELSEWHERE,
             APP_WEIRD, HOST_WEIRD, APP_NATIVE, HOST_BEHIND,
             # and the distinctive stems, so a truncation is caught too
             "zqxsentinel", "zqxdistraction", "sentinelhost", "zqx"]

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


# --------------------------------------------------------------- a fake clock
#
# The grace window is 800ms and the nag cadence is seconds; waiting for either in
# real time would make this test slow and flaky. focus.py reads the clock through
# the module-level name `time`, so replacing it drives the session by hand.

class Clock:
    def __init__(self):
        self.t = 10000.0

    def monotonic(self):
        return self.t

    def sleep(self, seconds):
        self.t += seconds

    def strftime(self, fmt, *args):
        return "2026-01-01"

    def advance(self, seconds):
        self.t += seconds


clock = Clock()
focus.time = clock

# ------------------------------------------------------- a controllable reader

frontmost = {"app": APP_TARGET, "host": HOST_TARGET}


def backend():
    """Stands in for the platform reader. Returns plaintext identities, which is
    precisely the point: everything downstream has to cope with the real thing."""
    return {"app": frontmost["app"],
            "title": "a window title mentioning " + str(frontmost["host"]),
            "url": "https://%s/some/path?q=1" % frontmost["host"]
                   if frontmost["host"] else None}


focus.READER_BACKEND = backend
# Every fake app must count as a browser, or the tab half is never exercised.
focus.CHROME_FAMILY = frozenset([APP_TARGET, APP_ELSEWHERE, APP_WEIRD])

# A throwaway ledger: the test must not touch the real streak, and it also has to
# read the file back to prove nothing leaked into it.
_ledger_dir = tempfile.mkdtemp(prefix="focus-privacy-")
focus.LEDGER_PATH = os.path.join(_ledger_dir, "focus-ledger.json")


# -------------------------------------------------------------- the scanners

def strings_in(value, path="state"):
    """Every string anywhere in the payload, keys included, with where it was."""
    found = []
    if isinstance(value, dict):
        for key, item in value.items():
            found.append((path + " (key)", str(key)))
            found.extend(strings_in(item, "%s.%s" % (path, key)))
    elif isinstance(value, (list, tuple)):
        for i, item in enumerate(value):
            found.extend(strings_in(item, "%s[%d]" % (path, i)))
    elif isinstance(value, str):
        found.append((path, value))
    return found


# A template's blank may hold a number, a duration, or - in the intent lines - the
# words you spoke. Nothing legitimate is longer than the cap on a spoken intent, so
# that cap plus a little slack is the widest a blank is allowed to be. Leaving it
# open (".*") would let any leak at all pass as a filled-in template.
BLANK = ".{0,%d}" % (focus.INTENT_SPOKEN_MAX_CHARS + 4)
TEMPLATE_PATTERNS = [
    re.compile("^" + re.sub(r"\\\{\w+\\\}", BLANK, re.escape(t)) + "$")
    for t in focus.LINE_REGISTRY
]

# ----------------------------------------------- the one string that IS allowed
#
# The named callouts say where you drifted to, out loud, on purpose - so a blanket
# "no identity in the payload" would now fail on a line the feature exists to speak.
# The audit therefore has to distinguish the one allowed appearance from every other
# kind, and it is made narrow in three ways at once:
#
#   * the line must match a NAMED template exactly, anchored at both ends;
#   * the {label} blank accepts only label-shaped characters and only up to
#     LABEL_MAX_CHARS, so a URL with a path or a quoted app name cannot fill it;
#   * what filled it must be one of LEGIT_LABELS - the names these sentinels are
#     allowed to become, computed here by asking focus for them.
#
# Then ONLY that substring is taken out before the sentinel hunt, not the whole line,
# so a leak hiding elsewhere in the same sentence is still caught. And because a
# legitimate label may itself contain a sentinel stem - zqxnativeeditor.exe is meant
# to be spoken as "Zqxnativeeditor" - the proof that nothing is KEPT cannot rest on
# this at all. It rests on MADEUP, further down, and its own scrub.
LABEL_BLANK = r"[A-Za-z0-9 .+&'-]{1,%d}" % focus.LABEL_MAX_CHARS
NAMED_PATTERNS = [
    re.compile("^" + re.sub(r"\\\{label\\\}", "(?P<label>" + LABEL_BLANK + ")",
                            re.sub(r"\\\{(?!label\\\})\w+\\\}", BLANK,
                                   re.escape(t))) + "$")
    for t in focus.NAMED_LINES
]


def named_label(text):
    """The name inside a named line, or None if this is not one."""
    for pattern in NAMED_PATTERNS:
        hit = pattern.match(text)
        if hit:
            return hit.group("label")
    return None


LEGIT_LABELS = frozenset(name for name in (
    focus.site_label(HOST_TARGET), focus.site_label(HOST_ELSEWHERE),
    focus.site_label(HOST_WEIRD), focus.site_label(HOST_BEHIND),
    focus.app_label(APP_TARGET), focus.app_label(APP_ELSEWHERE),
    focus.app_label(APP_WEIRD), focus.app_label(APP_NATIVE),
) if name)


def is_canned(text):
    """True only if the text is a LINE_REGISTRY template with its blanks filled.

    This is the claim that catches the leaks a sentinel search cannot: a hashed
    app name is not a sentinel, but it is not a canned line either.
    """
    return any(p.match(text) for p in TEMPLATE_PATTERNS)


ENUMS = set(focus.STATES) | {r for r in focus.END_REASONS if r} | set(focus.SAY_KINDS)
ENUMS.add("")


def audit(state, label):
    """The whole audit, run after every step of the session."""
    # Named lines first: identify them, remember their seqs, and take the NAME out of
    # the copy that is about to be searched. Everything else about those lines - and
    # every other line - goes into the hunt untouched.
    named_seqs, scanned = set(), state
    if state.get("say"):
        lines = []
        for line in state["say"]:
            text = str(line.get("text") or "")
            name = named_label(text)
            if name and name in LEGIT_LABELS:
                named_seqs.add(line.get("seq"))
                line = dict(line, text=text.replace(name, "<name>"))
            lines.append(line)
        scanned = dict(state, say=lines)

    blob = json.dumps(scanned, ensure_ascii=False)
    blob_ascii = json.dumps(scanned, ensure_ascii=True)
    lowered = (blob + blob_ascii).lower()

    hits = [s for s in SENTINELS if s.lower() in lowered]
    ok(not hits, "%s: no identity anywhere in the payload" % label,
       "leaked: %s" % hits if hits else "")

    ok(set(state) == set(focus.PUBLIC_KEYS),
       "%s: key set is exactly PUBLIC_KEYS" % label,
       "extra=%s missing=%s" % (sorted(set(state) - set(focus.PUBLIC_KEYS)),
                                sorted(set(focus.PUBLIC_KEYS) - set(state))))

    stray = []
    for where, text in strings_in(state):
        if where.endswith("(key)"):
            if text not in focus.PUBLIC_KEYS and text not in ("seq", "kind", "text"):
                stray.append((where, text))
            continue
        # The intent is the ONE string in the payload that is not a canned line,
        # because it is the one string that came from you rather than from watching
        # you. It is still scanned for sentinels above, and "no reader can write the
        # intent" is proved on its own further down rather than assumed here.
        if where == "state.intent":
            continue
        if not text or text in ENUMS or text in focus.PUBLIC_KEYS:
            continue
        if "<name>" in text:
            # A named line, already proved to be a named template with an allowed
            # name in it - which is a stricter claim than is_canned makes, so
            # re-checking the scrubbed spelling against the templates would only
            # weaken it.
            continue
        if not is_canned(text):
            stray.append((where, text))
    ok(not stray, "%s: every string is a known template or an enum" % label,
       "; ".join("%s -> %r" % pair for pair in stray[:4]))


# ============================================================ drive a session

print("\n  focus privacy  ·  identities are compared and discarded in the reader\n")

session = focus.FocusSession(minutes=2)
audit(focus.public_state(session), "on creation")

# ARMING. Home base first, exactly as it happens when you press FOCUS in the Jarvis
# tab: it must not lock on to the galaxy, which is the one surface you are certain
# to leave.
frontmost.update({"app": APP_TARGET, "host": "127.0.0.1"})
session.note_home_hint()
clock.advance(1.0)
session.tick()
ok(session.state == "arming", "arming: does not lock on to home base")
ok(session.deferred, "the deferred lock is visible as a boolean while it waits")
audit(focus.public_state(session), "while arming at home base")

# Now go to the work site. One tick is NOT a lock - passing through a window on the
# way to the right one must not become the thing you are held to.
frontmost.update({"app": APP_TARGET, "host": HOST_TARGET})
clock.advance(5.0)                      # long enough for the home hint to go stale
session.tick()
ok(session.state == "arming" and session.deferred,
   "one tick on a new surface is not enough to lock on")
audit(focus.public_state(session), "settling, one tick in")

# Still there on the next tick, so that is the target.
clock.advance(1.0)
session.tick()
ok(session.state == "running", "arming: settles on the surface you stayed on")
ok(session.reader.watching_tab, "the tab is locked as well as the app")
ok(not session.deferred, "and the deferred boolean goes false the moment it locks")
ok(any(l["text"] == focus.LINES["settled"] for l in session.say),
   "settling on a target is said out loud, so a wrong lock is audible",
   json.dumps([l["text"] for l in session.say]))
audit(focus.public_state(session), "just locked on")

# ON TARGET. Same host, different path every tick - the single-page app case that
# host-level hashing exists for. None of these may register as a drift.
for path in range(4):
    clock.advance(1.0)
    session.tick()
ok(session.drifts == 0, "a changing path on the locked host is not a drift")
ok(session.on_target_s > 0, "time on target is accumulating")
audit(focus.public_state(session), "on target")

# HOME BASE mid-session: coming back to talk is never a drift.
frontmost.update({"app": APP_TARGET, "host": "127.0.0.1"})
clock.advance(2.0)
session.tick()
ok(session.drifts == 0, "returning to home base is not a drift")
audit(focus.public_state(session), "back at home base")

# GRACE. Off target, but for less than DRIFT_GRACE_MS.
frontmost.update({"app": APP_ELSEWHERE, "host": HOST_ELSEWHERE})
clock.advance(focus.DRIFT_GRACE_MS / 2000.0)
session.tick()
ok(session.drifts == 0, "inside the grace window, still not a drift")
audit(focus.public_state(session), "inside grace")

# DRIFT, and a callout.
clock.advance(1.0)
session.tick()
ok(session.drifts == 1, "past the grace window, it counts as a drift")
spoken = [line for line in session.say if line["kind"] == "callout"]
ok(len(spoken) == 1, "a drift produces exactly one callout")
audit(focus.public_state(session), "drifting, callout spoken")

# A TAB-ONLY drift: right app, wrong site. Come back first.
frontmost.update({"app": APP_TARGET, "host": HOST_TARGET})
clock.advance(2.0)
session.tick()
frontmost["host"] = HOST_ELSEWHERE
# Two ticks, and that is the design rather than an inconvenience: the first notices
# you are elsewhere, the second confirms you are STILL elsewhere once the grace
# window has passed. One tick could not tell a drift from an alt-tab in transit.
clock.advance(2.0)
session.tick()
clock.advance(1.0)
session.tick()
ok(session.drifts == 2, "the right app on the wrong site is still a drift")
audit(focus.public_state(session), "tab drift in the locked app")

# NAG cadence, set by voice.
session.set_nag(6)
before = len([l for l in session.say if l["kind"] == "nag"])
clock.advance(7.0)
session.tick()
after = len([l for l in session.say if l["kind"] == "nag"])
ok(after > before, "a persisting drift nags on the cadence it was given")
audit(focus.public_state(session), "nagging")

# EXCUSE refunds the current excursion and goes quiet.
was = session.drifts
session.excuse()
ok(session.drifts == was - 1, "an excuse refunds the current excursion")
nags = len([l for l in session.say if l["kind"] == "nag"])
charged = session.drift_s
clock.advance(30.0)
session.tick()
ok(len([l for l in session.say if l["kind"] == "nag"]) == nags,
   "an excused excursion stays quiet")
# The whole excursion, not just the part already served: charging for the remainder
# would make an excuse a refund with a subscription attached.
ok(abs(session.drift_s - charged) < 0.001,
   "an excused excursion stops accruing drift while it continues")
ok(0 < session.excused_s <= focus.TICK_S * 5 + 0.001,
   "excused time is kept in its own bucket, and one tick cannot bank more than "
   "the dt clamp allows (a suspended laptop must not dump an hour into a bucket)")
audit(focus.public_state(session), "excused")

# Coming back must clear the excuse, or one "it's fine" buys the whole session.
frontmost.update({"app": APP_TARGET, "host": HOST_TARGET})
clock.advance(1.0)
session.tick()
ok(not session.excused, "coming back on target clears the excuse")
frontmost.update({"app": APP_WEIRD, "host": HOST_WEIRD})
clock.advance(2.0)
session.tick()
clock.advance(1.0)
session.tick()
ok(session.drifts >= 2, "the next excursion is counted again")
audit(focus.public_state(session), "drifting on identities with quotes and unicode")

# SNOOZE and PAUSE.
session.snooze(20)
audit(focus.public_state(session), "snoozed")
session.pause()
audit(focus.public_state(session), "paused")
session.resume()
session.extend(1)
audit(focus.public_state(session), "resumed and extended")

# THE END. The report card is numbers and canned wording.
session.finish("ended-early")
state = focus.public_state(session)
audit(state, "the report card")
ok(state["state"] == "ended" and state["report"], "a finished session has a report")
ok(is_canned(state["report"]), "the report is a filled-in template")
print("\n      report: %s\n" % state["report"])

# ------------------------------------------------- the places state also lives

# 1. The idle state, which reads the ledger rather than a session.
audit(focus.public_state(None), "idle, with no session at all")

# 2. The ledger on disk.
raw = ""
if os.path.isfile(focus.LEDGER_PATH):
    with open(focus.LEDGER_PATH, "r", encoding="utf-8") as fh:
        raw = fh.read()
hits = [s for s in SENTINELS if s.lower() in raw.lower()]
ok(raw and not hits, "the ledger on disk holds no identity", "leaked: %s" % hits)
book = json.loads(raw or "{}")
ok(all(isinstance(v, (int, str)) for v in book.values())
   and not any(isinstance(v, (list, dict)) for v in book.values()),
   "the ledger is aggregates only - no per-session rows")

# 3. The reader's own attributes: hashes, never names.
held = json.dumps({k: repr(v) for k, v in vars(session.reader).items()})
hits = [s for s in SENTINELS if s.lower() in held.lower()]
ok(not hits, "the reader holds no identity in plaintext, only salted hashes",
   "leaked: %s" % hits)

# 4. And the structural guard: free text cannot be spoken at all.
try:
    session._emit("the frontmost app is %s" % APP_TARGET, "note")
    ok(False, "_emit refuses a line that is not in LINE_REGISTRY")
except ValueError:
    ok(True, "_emit refuses a line that is not in LINE_REGISTRY")

# 5. Two readers must not produce comparable hashes, or the salt is decoration.
#    settle() is called SETTLE_TICKS times because there is no other way in: the
#    class has no method that accepts a target from outside, by design.
one, two = focus.TargetReader(), focus.TargetReader()
for _ in range(focus.SETTLE_TICKS):
    one.settle()
    two.settle()
ok(one.locked and two.locked, "settling twice on one surface is what locks it")
ok(one._app != two._app,
   "two readers hash the same app differently, so hashes cannot be correlated")
ok(not hasattr(focus.TargetReader, "lock"),
   "there is no method that locks a target handed in from elsewhere")


# ================================= never leaving home base, and refusing to guess
#
# The FOCUS button is in the Jarvis tab, so "you are still in the Jarvis tab" is the
# normal state for the first few seconds of every session and has to be survivable.

print("")
frontmost.update({"app": APP_TARGET, "host": "127.0.0.1"})
stayer = focus.FocusSession(minutes=2)
ticks = 0
# The hint is refreshed every tick, exactly as the viewer refreshes it while its page
# has keyboard focus. Nothing may settle for as long as that keeps arriving.
while stayer.state == "arming" and ticks < 60:
    stayer.note_home_hint()
    clock.advance(2.0)
    stayer.tick()
    ticks += 1
    if ticks == 5:
        ok(stayer.deferred and not stayer.reader.locked,
           "sitting in the Jarvis tab locks nothing, ten seconds in")
waited = ticks * 2.0
ok(stayer.state == "running",
   "it does not wait forever - it stops deferring on its own", str(waited))
ok(waited >= focus.DEFER_APP_ONLY_S,
   "and it waited the full DEFER_APP_ONLY_S before doing so", str(waited))
ok(not stayer.tab_watched and stayer.reader.locked,
   "the fallback watches the APPLICATION and drops the site - the half that could "
   "have been wrong is the half it throws away")
ok(any(l["text"].startswith(focus.LINES["settled_app_only"].split("{")[0])
       for l in stayer.say),
   "and it says so, out loud, rather than silently watching less than you think",
   json.dumps([l["text"] for l in stayer.say]))
print("      said: %s" % json.dumps([l["text"] for l in stayer.say][-1:]))
audit(focus.public_state(stayer), "settled app-only after never leaving home")

# --- the title join, and what it does with two windows that look the same --------
#
# Chrome's window title IS its active tab's title, which is the only join available
# between the OS's foreground window and the browser's tabs. With several windows
# open that join can be ambiguous, and this is the check that an ambiguous join
# answers "I don't know" rather than picking one.


class _Answer:
    def __init__(self, payload):
        self._payload = payload

    def read(self):
        return json.dumps(self._payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


PAGES = []


class _UrllibShim:                 # only the two attributes focus.py actually uses
    parse = urllib.parse

    class request:
        @staticmethod
        def urlopen(url, timeout=None):
            return _Answer(PAGES)


real_urllib, focus.urllib = focus.urllib, _UrllibShim

PAGES = [{"type": "page", "url": "https://work.example.com/a", "title": "New Tab"},
         {"type": "page", "url": "https://elsewhere.example.net/b", "title": "New Tab"}]
host, alive = focus._cdp_active_host("New Tab")
ok(host is None and alive is True,
   "two windows with the same title resolve to NOTHING, not to the first match",
   repr((host, alive)))

PAGES = [{"type": "page", "url": "https://work.example.com/a", "title": "The Work"},
         {"type": "page", "url": "https://elsewhere.example.net/b", "title": "Other"}]
host, alive = focus._cdp_active_host("The Work")
ok(host == "work.example.com" and alive,
   "one unambiguous match is an answer", repr((host, alive)))

PAGES = [{"type": "page", "url": "https://work.example.com/a", "title": "The Work"},
         {"type": "page", "url": "https://work.example.com/b", "title": "The Work"}]
host, alive = focus._cdp_active_host("The Work")
ok(host == "work.example.com",
   "two tabs on the same HOST are not an ambiguity - host-level is why", repr(host))

PAGES = []
host, alive = focus._cdp_active_host("Something Else Entirely")
ok(host is None and alive is True,
   "an endpoint that answers but matches nothing is alive and unhelpful, not dead",
   repr((host, alive)))

# And the consequence, which is the part that matters: unreadable-but-alive WAITS.
focus.READER_BACKEND = lambda: {"app": APP_TARGET, "title": "New Tab", "url": None}
PAGES = [{"type": "page", "url": "https://a.example.com/", "title": "New Tab"},
         {"type": "page", "url": "https://b.example.net/", "title": "New Tab"}]
stalled = focus.TargetReader()
steps = [stalled.settle() for _ in range(focus.SETTLE_TICKS + 2)]
ok(all(s["waiting"] and not s["settled"] for s in steps),
   "a browser whose site cannot be read, while the endpoint is alive, is waited on "
   "and never becomes a target",
   json.dumps(steps))
ok(not stalled.locked, "so nothing is locked by a stall", str(stalled.locked))

# With NO endpoint at all it is not a stall, it is the machine: settle app-only now
# rather than waiting forty-five seconds to learn a permanent fact.
focus.urllib = real_urllib          # so the lookup genuinely fails: no such port
real_ports, focus.CDP_PORTS = focus.CDP_PORTS, (1,)   # port 1 answers nothing, ever
noport = focus.TargetReader()
steps = [noport.settle() for _ in range(focus.SETTLE_TICKS)]
ok(steps[-1]["settled"] and not steps[-1]["tab"],
   "with no DevTools port anywhere, it settles at application level immediately",
   json.dumps(steps[-1]))
focus.CDP_PORTS = real_ports
focus.READER_BACKEND = backend


# ================================================ the intent, and who may write it
#
# The intent is the only free text in the whole feature, so it gets its own section.
# Two questions matter: can anything OTHER than your own answer put a string there,
# and is a long answer ever read back to you.

print("")
frontmost.update({"app": APP_TARGET, "host": HOST_TARGET})
victim = focus.FocusSession(minutes=2)
ok(victim.awaiting_intent,
   "a new session is waiting for an answer to \"what are we focusing on?\"")
ok(focus.LINES["arming"].count("what are we focusing on") == 1,
   "and the start line actually asks it, so a deferred lock is never silent",
   focus.LINES["arming"])
ok("lock on there" in focus.LINES["arming"],
   "the start line says where to go, since nothing is locked yet")

# Drive a whole session past every path that touches an identity. If any of them
# could reach self.intent, a window title would be sitting in it by the end.
# Two ticks per surface, so this really does settle and then really does drift,
# rather than staying in arming for the whole loop and proving nothing about the
# paths that run once a target exists.
for step in range(12):
    which = (step // focus.SETTLE_TICKS) % 3
    frontmost.update({"app": [APP_TARGET, APP_ELSEWHERE, APP_WEIRD][which],
                      "host": [HOST_TARGET, HOST_ELSEWHERE, HOST_WEIRD][which]})
    clock.advance(2.0)
    victim.tick()
ok(victim.state == "running" and victim.drifts >= 1,
   "the loop above really did settle and really did drift",
   json.dumps({"state": victim.state, "drifts": victim.drifts}))
ok(victim.intent == "",
   "no amount of watching can put a string in the intent - it stays empty",
   repr(victim.intent))

# Structurally: exactly one writer, and it is the one reached from the POST body.
with open(focus.__file__, "r", encoding="utf-8") as fh:
    src_lines = fh.read().splitlines()
writers, enclosing = [], "?"
for line in src_lines:
    found = re.match(r"\s+def (\w+)", line)
    if found:
        enclosing = found.group(1)
    if re.match(r"\s+self\.intent\s*(=|\+=)[^=]", line):
        writers.append(enclosing)
ok(writers == ["__init__", "set_intent"],
   "self.intent is assigned in exactly two places: emptied, and set_intent()",
   "assigned in: %s" % writers)

# A short answer is kept and used.
ok(victim.set_intent("the invoice importer"), "an answer is accepted")
ok(victim.intent == "the invoice importer", "and kept as you said it", victim.intent)
ok(any(l["text"] == focus.LINES["intent_noted"] for l in victim.say),
   "the reply is four words, not your sentence read back at you")
audit(focus.public_state(victim), "with an intent attached")

# Filler is not an intent. "That is not uh, sir." must be impossible.
for junk in ["", "   ", "um", "uh", "er", "well", "okay", "yeah", "nothing",
             "stuff", "things", "work", "it", "this", "that", "um, er"]:
    if focus.clean_intent(junk):
        ok(False, "filler is never accepted as an intent", "%r -> %r"
           % (junk, focus.clean_intent(junk)))
        break
else:
    ok(True, "filler and hesitation are never accepted as an intent")
ok(focus.clean_intent("I need to finish the invoice importer")
   == "the invoice importer",
   "dictation preamble is trimmed off the front",
   repr(focus.clean_intent("I need to finish the invoice importer")))

# A LONG answer is shown but never spoken. This is the "never parrot it back" rule
# with a number behind it.
essay = ("rewriting the invoice importer so that the nightly reconciliation job "
         "stops double counting refunds from the old gateway")
frontmost.update({"app": APP_TARGET, "host": HOST_TARGET})
talker = focus.FocusSession(minutes=2)
talker.set_intent(essay)
ok(len(talker.intent) > focus.INTENT_SPOKEN_MAX_CHARS,
   "a dictated essay is kept in full, up to the cap", str(len(talker.intent)))
ok(focus.spoken_intent(talker.intent) == "",
   "but it is not sayable, so no line will recite it")
for _ in range(3):                    # settle, then drift, then get called out
    clock.advance(2.0)
    talker.tick()
frontmost.update({"app": APP_ELSEWHERE, "host": HOST_ELSEWHERE})
for _ in range(3):
    clock.advance(2.0)
    talker.tick()
talker.finish("ended-early")
said = " ".join(l["text"] for l in talker.say) + " " + (talker.report or "")
ok(essay[:30] not in said,
   "a long intent appears in NO spoken line and in NO report card", said[:200])
ok(talker.drifts >= 1, "and the session still called out the drift",
   str(talker.drifts))
audit(focus.public_state(talker), "a long intent, spoken nowhere")

# The short one, by contrast, is allowed to colour what you hear.
picky = focus.FocusSession(minutes=2)
picky.set_intent("the invoice importer")
frontmost.update({"app": APP_TARGET, "host": HOST_TARGET})
for _ in range(3):
    clock.advance(2.0)
    picky.tick()
frontmost.update({"app": APP_ELSEWHERE, "host": HOST_ELSEWHERE})
for _ in range(3):
    clock.advance(2.0)
    picky.tick()
callouts = [l["text"] for l in picky.say if l["kind"] == "callout"]
ok(callouts and "the invoice importer" in callouts[0],
   "a short intent colours the FIRST callout, which is the one you listen to",
   json.dumps(callouts))
picky.finish("ended-early")
ok("the invoice importer" in (picky.report or ""),
   "and the report card is about what you said you were doing", picky.report)
audit(focus.public_state(picky), "a short intent, on the card and in the callout")
print("\n      callout: %s" % callouts[0])
print("      report:  %s\n" % picky.report)

# ===================================================== moving the lock, on purpose
#
# The deferred lock infers, and this is the override for when it infers wrongly. Three
# surfaces, three outcomes, and the privacy audit runs after each of them because a
# new way to choose a target is a new place for a target to leak out of.

print("")
print("  moving the lock  ·  three surfaces, three outcomes\n")

# --- the phrases. First in the chain, and only while a session is live -----------
for said in ["lock on this tab", "keep me in this tab", "this is the tab",
             "stay on this tab", "lock this tab", "lock onto this window",
             "okay, I'm gonna need you to keep me in this tab.",
             "this is my work tab", "keep me here", "watch this page"]:
    parsed = focus.parse_command(said, True)
    if parsed != ("retarget", {"source": "voice"}):
        ok(False, "every phrasing of it is understood as a re-target",
           "%r -> %r" % (said, parsed))
        break
else:
    ok(True, "every phrasing of it is understood as a re-target, lead-ins included")

# And what it must NOT swallow. "keep me in the loop" is the one that costs you a
# session if the regex is written a word too wide.
for said, expected in [("keep me in the loop", None),
                       ("watch this", None),
                       ("look at this", None),
                       ("what do you think of this", None),
                       ("it's okay, I'm doing research", ("excuse", {})),
                       ("pause", ("pause", {})),
                       ("how much longer", ("status", {}))]:
    parsed = focus.parse_command(said, True)
    if parsed != expected:
        ok(False, "an ordinary sentence is not a re-target",
           "%r -> %r, wanted %r" % (said, parsed, expected))
        break
else:
    ok(True, "an ordinary sentence is not a re-target, and the other commands keep "
             "every phrase they had")
ok(focus.parse_command("lock on this tab", False) is None,
   "with no session running it is not a command at all - which is what leaves "
   "\"lock my screen\" to the screen share")

# --- surface one: the tab you actually want --------------------------------------
frontmost.update({"app": APP_TARGET, "host": HOST_TARGET})
mover = focus.FocusSession(minutes=5)
for _ in range(focus.SETTLE_TICKS + 1):
    clock.advance(1.0)
    mover.tick()
ok(mover.state == "running" and mover.reader.locked, "a session settles as usual")

# Off to the wrong place, long enough to be counted and told off for.
frontmost.update({"app": APP_ELSEWHERE, "host": HOST_ELSEWHERE})
for _ in range(3):
    clock.advance(1.0)
    mover.tick()
ok(mover.drifts == 1 and mover.drift_s > 0,
   "and a drift is counted while you are somewhere else", str(mover.drifts))

before = len(mover.say)
mover.retarget()
said = [l["text"] for l in mover.say[before:]]
ok(mover.reader.locked and mover.state == "running" and mover.tab_watched,
   "saying it from the tab you want locks THAT, in one read - no second tick, "
   "because you have just told me")
ok(said == [focus.LINES["settled"]],
   "and says exactly \"Locked on, sir.\" - nothing else", json.dumps(said))
ok(mover.drifts == 0 and mover.drift_s == 0.0,
   "the drift you were in the middle of is forgiven",
   "%d drifts, %.2fs" % (mover.drifts, mover.drift_s))
ok(focus.LINES["back"] not in said and focus.LINES["back_long"].split("{")[0]
   not in " ".join(said),
   "and forgiven SILENTLY: no \"Back, thank you sir\" for a correction you made "
   "yourself", json.dumps(said))
clock.advance(1.0)
mover.tick()
ok(mover.drifts == 0 and mover._on_target_now,
   "the very next tick counts the new surface as on target", str(mover.drifts))
audit(focus.public_state(mover), "after a spoken re-target onto a work tab")

# --- surface two: this page, which is the one it cannot lock ---------------------
frontmost.update({"app": APP_TARGET, "host": "127.0.0.1"})
before = len(mover.say)
mover.retarget()
said = [l["text"] for l in mover.say[before:]]
ok(not mover.reader.locked and mover.state == "arming" and mover.deferred,
   "said from this page it locks NOTHING and re-arms - this is the tab the button "
   "lives in", "%s / locked=%s" % (mover.state, mover.reader.locked))
ok(said == [focus.LINES["retarget_armed"]],
   "and says where it will be looking instead", json.dumps(said))
ok(not mover.tab_watched, "with nothing watched in the meantime")
audit(focus.public_state(mover), "after a re-target from home base")
print("      said: %s" % json.dumps(said))

# It then settles on the next surface you stay on, exactly as at the start.
frontmost.update({"app": APP_ELSEWHERE, "host": HOST_ELSEWHERE})
for _ in range(focus.SETTLE_TICKS + 1):
    clock.advance(1.0)
    mover.tick()
ok(mover.state == "running" and mover.reader.locked and mover.tab_watched,
   "and the promise holds: it locks on where you land, by settling")

# --- surface three: an application with no site at all --------------------------
frontmost.update({"app": APP_NATIVE, "host": None})
before = len(mover.say)
mover.retarget()
said = [l["text"] for l in mover.say[before:]]
ok(mover.reader.locked and not mover.tab_watched,
   "from a non-browser application it locks the APPLICATION")
ok(said == [focus.LINES["settled"]],
   "and does not add a caveat about a site that was never possible",
   json.dumps(said))
audit(focus.public_state(mover), "after a re-target onto a native application")

# A browser whose site cannot be read does NOT wait here, unlike settle(): you have
# said this is the surface, so the app is locked and the missing half is said out loud.
frontmost.update({"app": APP_TARGET, "host": None})
before = len(mover.say)
mover.retarget()
said = [l["text"] for l in mover.say[before:]]
ok(mover.reader.locked and not mover.tab_watched,
   "a browser with no readable site locks the app rather than waiting - arguing with "
   "an instruction is not a feature")
ok(said == [focus.LINES["settled"], focus.LINES["notab"]],
   "and says the site is the half it could not get", json.dumps(said))

# --- and the one thing it must never do: lose a good lock over a bad read --------
frontmost.update({"app": APP_TARGET, "host": HOST_TARGET})
for _ in range(focus.SETTLE_TICKS + 1):
    clock.advance(1.0)
    mover.tick()
holding = (mover.reader._app, mover.reader._host, mover.state)
blind, focus.READER_BACKEND = focus.READER_BACKEND, lambda: None
before = len(mover.say)
mover.retarget()
focus.READER_BACKEND = blind
ok((mover.reader._app, mover.reader._host, mover.state) == holding,
   "a read that fails changes nothing at all - a working lock is not thrown away "
   "because one look failed")
ok([l["text"] for l in mover.say[before:]] == [focus.LINES["unreadable"]],
   "it says it cannot see, and that is the whole of it",
   json.dumps([l["text"] for l in mover.say[before:]]))

# --- structurally: still no way to hand a target in ------------------------------
params = list(inspect.signature(focus.TargetReader.settle_here).parameters)
ok(params == ["self", "via_browser"],
   "settle_here takes one flag and no surface: which fresh read to take, never what "
   "to lock", json.dumps(params))
ok(not hasattr(focus.TargetReader, "lock"),
   "and there is still no method that locks a target handed in from elsewhere")
held = json.dumps({k: str(v) for k, v in vars(mover.reader).items()})
hits = [s for s in SENTINELS if s.lower() in held.lower()]
ok(not hits, "the re-targeted reader holds no identity in plaintext either",
   "leaked: %s" % hits)


# ============================================ the card trap, and the WebSocket
#
# Pressing a button on the card is what brings the card to the front, so at that
# instant the frontmost window is this page - the one surface a re-target must never
# choose. The answer is to ask the BROWSER which of its tabs is visible instead, and
# that answer only exists over a DevTools socket. So there is a socket here: a real
# one, speaking the real protocol, because a hand-rolled frame encoder tested against
# a mock of my own assumptions would prove nothing at all.

print("")


def _recv_exactly(conn, n):
    buf = b""
    while len(buf) < n:
        chunk = conn.recv(n - len(buf))
        if not chunk:
            raise OSError("short read")
        buf += chunk
    return buf


def _server_frame(payload):
    """One UNMASKED text frame, which is what a server must send."""
    if len(payload) < 126:
        return struct.pack("!BB", 0x81, len(payload)) + payload
    return struct.pack("!BBH", 0x81, 126, len(payload)) + payload


class FakePage(threading.Thread):
    """A DevTools page socket in thirty lines: handshake, one frame in, one out.

    The value it answers with is taken from the last path segment, so one server can
    play several tabs - "vis" is a visible one, "hid" a background one, "foc" the
    focused one - and the client's own masking is recorded, because an unmasked client
    frame is a protocol violation that Chrome would close the socket over.
    """

    ANSWERS = {"vis": 1, "hid": 0, "foc": 3, "mute": None}

    def __init__(self):
        threading.Thread.__init__(self, daemon=True)
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(16)
        self.port = self.sock.getsockname()[1]
        self.asked = []
        self.masked = []

    def run(self):
        while True:
            try:
                conn, _ = self.sock.accept()
            except OSError:
                return
            threading.Thread(target=self._serve, args=(conn,), daemon=True).start()

    def _serve(self, conn):
        try:
            conn.settimeout(3)
            buf = b""
            while b"\r\n\r\n" not in buf:
                chunk = conn.recv(4096)
                if not chunk:
                    return
                buf += chunk
            path = buf.split(b" ")[1].decode("ascii")
            conn.sendall(b"HTTP/1.1 101 Switching Protocols\r\n"
                         b"Upgrade: websocket\r\nConnection: Upgrade\r\n\r\n")
            head = _recv_exactly(conn, 2)
            length = head[1] & 0x7F
            if length == 126:
                length = struct.unpack("!H", _recv_exactly(conn, 2))[0]
            self.masked.append(bool(head[1] & 0x80))
            mask = _recv_exactly(conn, 4) if head[1] & 0x80 else b"\0\0\0\0"
            body = _recv_exactly(conn, length)
            body = bytes(b ^ mask[i % 4] for i, b in enumerate(body))
            self.asked.append((path, json.loads(body.decode("utf-8"))))
            value = self.ANSWERS.get(path.rsplit("/", 1)[-1], 0)
            if value is None:
                return                      # a tab that never answers, on purpose
            conn.sendall(_server_frame(json.dumps(
                {"id": 1, "result": {"result": {"value": value}}}).encode("utf-8")))
        except (OSError, ValueError):
            pass
        finally:
            try:
                conn.close()
            except OSError:
                pass


page = FakePage()
page.start()


def ws(name):
    return "ws://127.0.0.1:%d/devtools/page/%s" % (page.port, name)


ok(focus._ws_eval_int(ws("foc"), focus._FRONT_EXPR) == 3,
   "the hand-rolled WebSocket client completes a real handshake and reads a real "
   "frame back")
ok(page.asked and page.asked[-1][1]["method"] == "Runtime.evaluate"
   and "visibilityState" in page.asked[-1][1]["params"]["expression"],
   "asking the page itself whether it is the visible one",
   json.dumps(page.asked[-1][1]) if page.asked else "nothing was asked")
ok(all(page.masked), "and it masks its frames, as a client must",
   json.dumps(page.masked))
ok(focus._ws_eval_int(ws("mute"), focus._FRONT_EXPR) is None,
   "a tab that does not answer is None - not a claim about it either way")
ok(focus._ws_eval_int("ws://127.0.0.1:1/devtools/page/x", focus._FRONT_EXPR) is None
   and focus._ws_eval_int("http://not-a-socket/", focus._FRONT_EXPR) is None,
   "a dead port and a nonsense URL are None, not an exception")

# Now the join: /json lists the tabs, and the pressed-in tab is home base.
focus.urllib = _UrllibShim
PAGES = [
    {"type": "page", "url": "http://127.0.0.1:4700/", "title": "Knowledge Galaxy",
     "webSocketDebuggerUrl": ws("foc")},
    {"type": "page", "url": "https://%s/ticket/1" % HOST_BEHIND, "title": "Behind",
     "webSocketDebuggerUrl": ws("vis")},
    {"type": "page", "url": "https://%s/x" % HOST_ELSEWHERE, "title": "Hidden",
     "webSocketDebuggerUrl": ws("hid")},
]
asked_before = len(page.asked)
host, alive, ambiguous = focus._cdp_front_host()
ok(host == HOST_BEHIND and alive and not ambiguous,
   "the browser's own visible tab is found while the card is what is in front",
   repr((host, alive, ambiguous)))
ok(all("/foc" not in path for path, _ in page.asked[asked_before:]),
   "and home base is never even asked - the tab you pressed the button in is not a "
   "candidate for the tab you meant",
   json.dumps([p for p, _ in page.asked[asked_before:]]))

PAGES = [
    {"type": "page", "url": "https://%s/a" % HOST_BEHIND, "title": "One",
     "webSocketDebuggerUrl": ws("vis")},
    {"type": "page", "url": "https://%s/b" % HOST_ELSEWHERE, "title": "Two",
     "webSocketDebuggerUrl": ws("vis")},
]
host, alive, ambiguous = focus._cdp_front_host()
ok(host is None and ambiguous,
   "two windows both showing work is a question, not an answer", repr((host, alive)))

# --- and the trap itself, end to end --------------------------------------------
frontmost.update({"app": APP_TARGET, "host": "127.0.0.1"})
PAGES = [
    {"type": "page", "url": "http://127.0.0.1:4700/", "title": "Knowledge Galaxy",
     "webSocketDebuggerUrl": ws("foc")},
    {"type": "page", "url": "https://%s/ticket/1" % HOST_BEHIND, "title": "Behind",
     "webSocketDebuggerUrl": ws("vis")},
]
carder = focus.FocusSession(minutes=5)
for _ in range(focus.SETTLE_TICKS + 1):     # settles on the work tab first
    frontmost.update({"app": APP_TARGET, "host": HOST_TARGET})
    clock.advance(1.0)
    carder.tick()
ok(carder.state == "running" and carder.tab_watched, "a session watching a site")

frontmost.update({"app": APP_TARGET, "host": "127.0.0.1"})
naive = carder.reader.settle_here(via_browser=False)
ok(naive["reason"] == "home",
   "reading the foreground at the moment of a press finds THE CARD - which is the "
   "whole trap, and why the flag exists", json.dumps(naive))

before = len(carder.say)
carder.retarget(from_card=True)
said = [l["text"] for l in carder.say[before:]]
ok(carder.reader.locked and carder.tab_watched and said == [focus.LINES["settled"]],
   "the pill locks the tab BEHIND the card, and says Locked on, sir",
   json.dumps(said))
frontmost.update({"app": APP_TARGET, "host": HOST_BEHIND})
clock.advance(1.0)
carder.tick()
ok(carder.drifts == 0 and carder._on_target_now,
   "and that tab is what it now holds you to", str(carder.drifts))
frontmost.update({"app": APP_TARGET, "host": "127.0.0.1"})
clock.advance(1.0)
carder.tick()
ok(carder.drifts == 0,
   "while this page is still home base and still never a drift", str(carder.drifts))
audit(focus.public_state(carder), "after the card moved the lock")

# With nothing the browser can point at, the pill re-arms rather than guessing.
PAGES = [{"type": "page", "url": "http://127.0.0.1:4700/", "title": "Knowledge Galaxy",
          "webSocketDebuggerUrl": ws("foc")}]
before = len(carder.say)
carder.retarget(from_card=True)
said = [l["text"] for l in carder.say[before:]]
ok(not carder.reader.locked and carder.deferred
   and said == [focus.LINES["retarget_armed"]],
   "a press with no readable tab behind it re-arms - a recovery, not an apology",
   json.dumps(said))
audit(focus.public_state(carder), "after a card press with nothing to point at")

focus.urllib = real_urllib
try:
    page.sock.close()
except OSError:
    pass


# ================================== naming the drift, and keeping no record of it
#
# The feature under test says where you went - "Sir, Instagram can wait" - which is a
# hole in the wall every other check in this file defends. So this section proves the
# narrow thing that is actually promised: the name reaches the speakers and reaches
# nothing else, and the sentence carrying it does not survive the tick.
#
# THE NAME USED HERE IS MADE UP, and that is the whole method. A test that searched
# for "Instagram" would be searching for a word that appears in focus.py's own map, in
# its comments and in this very paragraph, so it could pass while leaking - or fail on
# an example sentence. "fnordwaffle-9182.example" is in no map, no line and no comment:
# a single occurrence anywhere it should not be is a leak and cannot be anything else.

print("")
print("  naming the drift  |  said out loud, kept nowhere\n")

MADEUP_HOST = "www.fnordwaffle-9182.example"
MADEUP_LABEL = focus.site_label(MADEUP_HOST)
MADEUP_STEMS = [s for s in ["fnordwaffle", "9182", MADEUP_LABEL, MADEUP_HOST] if s]


def named_hits(blob):
    """Every trace of the made-up name in whatever was handed in."""
    lowered = str(blob).lower()
    return [s for s in MADEUP_STEMS if s.lower() in lowered]


def state_hits(state, include_say=True):
    payload = dict(state)
    if not include_say:
        payload.pop("say", None)
    return named_hits(json.dumps(payload, ensure_ascii=False)
                      + json.dumps(payload, ensure_ascii=True))


with open(focus.__file__, "r", encoding="utf-8") as fh:
    module_source = fh.read().lower()

ok(MADEUP_LABEL == "fnordwaffle-9182.example",
   "an unmapped host is named by its bare domain and nothing more",
   repr(MADEUP_LABEL))
ok("fnordwaffle" not in module_source,
   "the name under test appears NOWHERE in focus.py - not in a map, not in a comment")
ok("instagram" in module_source,
   "whereas 'instagram' does appear in it, which is exactly why this test does not "
   "search for that")

# --- spoken once, then gone ------------------------------------------------------
namer = focus.FocusSession(minutes=30)
frontmost.update({"app": APP_TARGET, "host": HOST_TARGET})
for _ in range(focus.SETTLE_TICKS + 1):
    clock.advance(2.0)
    namer.tick()
ok(namer.state == "running" and namer.reader.locked,
   "naming: a session locked on to the work, ready to be tempted")

frontmost.update({"app": APP_TARGET, "host": MADEUP_HOST})
clock.advance(2.0)
namer.tick()
clock.advance(1.0)
namer.tick()
spoken = [l["text"] for l in namer.say if l["kind"] == "callout"]
ok(namer.drifts == 1 and len(spoken) == 1,
   "naming: the drift counted and produced exactly one callout", json.dumps(spoken))
ok(spoken and MADEUP_LABEL in spoken[0],
   "the callout SAYS the name, which is the entire point of it", json.dumps(spoken))
ok(spoken and named_label(spoken[0]) == MADEUP_LABEL,
   "and it is a template from the named pools, not free text")

# At this instant the name exists in exactly one place: the sentence about to be
# spoken. Not in a counter, not in the report, not in a second copy of itself.
live = focus.public_state(namer)
ok(not state_hits(live, include_say=False),
   "at the moment of speaking, the name is in the say queue and in NO other key",
   "leaked: %s" % state_hits(live, include_say=False))
ok(sum(1 for l in live["say"] if MADEUP_LABEL in l["text"]) == 1,
   "and in exactly one line of that queue")

# One tick past the TTL and the sentence is not history, because it was never kept.
clock.advance(focus.LABEL_LINE_TTL_S + 1.0)
namer.tick()
after = focus.public_state(namer)
ok(not state_hits(after),
   "one tick later the name is gone from the ENTIRE payload, say queue included",
   "leaked: %s" % state_hits(after))
ok(after["drifts"] == 1 and after["driftS"] >= 1,
   "the drift itself is still counted - what went is the name, not the accounting",
   json.dumps({"drifts": after["drifts"], "driftS": after["driftS"]}))
audit(after, "after a named callout has been scrubbed")

# The report card and the ledger: the two things that outlive the session.
namer.finish("ended-early")
ended = focus.public_state(namer)
ok(not named_hits(namer.report), "the report card never names anywhere",
   namer.report)
ok(not state_hits(ended), "and the ended state holds no trace of it either",
   "leaked: %s" % state_hits(ended))
with open(focus.LEDGER_PATH, "r", encoding="utf-8") as fh:
    ledger_raw = fh.read()
ok(not named_hits(ledger_raw), "the ledger on disk holds no trace of it",
   "leaked: %s" % named_hits(ledger_raw))

# Nothing on the objects themselves, either - the scrub must not be a trick played on
# the serialiser while an attribute quietly keeps the string.
held = json.dumps([{k: repr(v) for k, v in vars(obj).items()}
                   for obj in (namer, namer.reader)])
ok(not named_hits(held),
   "no attribute of the session or the reader holds the name, before or after",
   "leaked: %s" % named_hits(held))

# --- the paths that end a session early, which never tick again ------------------
for reason, kill in (("paused mid-drift", lambda s: s.pause()),
                     ("abandoned mid-drift", lambda s: s.abort()),
                     ("ended mid-drift", lambda s: s.finish("ended-early"))):
    victim2 = focus.FocusSession(minutes=30)
    frontmost.update({"app": APP_TARGET, "host": HOST_TARGET})
    for _ in range(focus.SETTLE_TICKS + 1):
        clock.advance(2.0)
        victim2.tick()
    frontmost.update({"app": APP_TARGET, "host": MADEUP_HOST})
    clock.advance(2.0)
    victim2.tick()
    clock.advance(1.0)
    victim2.tick()
    said_it = any(MADEUP_LABEL in l["text"] for l in victim2.say)
    kill(victim2)
    clock.advance(focus.LABEL_LINE_TTL_S + 1.0)
    victim2.tick()                       # a paused session still ticks; an ended one
    ok(said_it and not state_hits(focus.public_state(victim2)),  # scrubbed on the way out
       "%s: the name goes with the session, not into it" % reason,
       "leaked: %s" % state_hits(focus.public_state(victim2)))

# --- where the name may be derived, and where it may not -------------------------
frontmost.update({"app": APP_TARGET, "host": HOST_TARGET})
reader = focus.TargetReader()
for _ in range(focus.SETTLE_TICKS):
    reader.settle()
ok(reader.look()["label"] is None,
   "where you said you would be is never named: it is not a drift")
frontmost.update({"app": APP_TARGET, "host": "127.0.0.1"})
ok(reader.look()["label"] is None,
   "home base is never named either - this page is not a distraction")
frontmost.update({"app": APP_TARGET, "host": MADEUP_HOST})
ok(reader.look()["label"] == MADEUP_LABEL,
   "a readable drift, and only that, comes back with a name")
blind = focus.TargetReader()
ok(blind.look()["label"] is None,
   "an unlocked reader names nothing, because nothing is a drift yet")

ok((focus.site_label("www.instagram.com"), focus.site_label("m.youtube.com"),
    focus.site_label("youtu.be"), focus.site_label("mail.google.com"),
    focus.site_label("t.co")) == ("Instagram", "YouTube", "YouTube", "Gmail", "t.co"),
   "the big distractions get a proper name; everything else gets its bare domain")
ok(focus.site_label("docs.google.com") == "google.com"
   and focus.site_label("news.bbc.co.uk") == "bbc.co.uk",
   "longest suffix wins, and a two-part suffix is not mistaken for a domain")
ok(focus.app_label("slack.exe") == "Slack"
   and focus.app_label("com.tinyspeck.slackmacgap") == "Slack"
   and focus.app_label(APP_NATIVE) == "Zqxnativeeditor",
   "an app is named from the reader's own string, mapped or title-cased",
   repr(focus.app_label(APP_NATIVE)))
ok(focus._clean_label('zqx"quote\\slash<tag>') == "zqx quote slash tag"
   and focus._clean_label("<<>>") is None,
   "punctuation is dropped, and a name that is nothing but punctuation is no name")
ok(focus.site_label("a" * 90 + ".example") is not None
   and len(focus.site_label("a" * 90 + ".example")) <= focus.LABEL_MAX_CHARS,
   "a name is capped at LABEL_MAX_CHARS, so no sentence can smuggle a URL")
# The path is gone long before the name is made, so no page can ever be named.
ok(focus.site_label(focus._host_of(
    "https://www.fnordwaffle-9182.example/private/thing?x=1")) == MADEUP_LABEL,
   "a URL's path cannot reach a name: only the host is ever looked at")

# --- the nags stay nameless ------------------------------------------------------
nagger = focus.FocusSession(minutes=30)
nagger.set_nag(focus.NAG_MIN_S)
frontmost.update({"app": APP_TARGET, "host": HOST_TARGET})
for _ in range(focus.SETTLE_TICKS + 1):
    clock.advance(2.0)
    nagger.tick()
frontmost.update({"app": APP_TARGET, "host": MADEUP_HOST})
for _ in range(6):                        # drift, callout, then nag after nag
    clock.advance(focus.NAG_MIN_S)
    nagger.tick()
nags = [l["text"] for l in nagger.say if l["kind"] == "nag"]
ok(len(nags) >= 2 and not named_hits(" ".join(nags)),
   "a dragging drift is nagged about, and no nag names the place",
   json.dumps(nags[:3]))

# --- the switch at the top of the file -------------------------------------------
focus.NAME_DRIFTS = False
try:
    quiet = focus.FocusSession(minutes=30)
    frontmost.update({"app": APP_TARGET, "host": HOST_TARGET})
    for _ in range(focus.SETTLE_TICKS + 1):
        clock.advance(2.0)
        quiet.tick()
    frontmost.update({"app": APP_TARGET, "host": MADEUP_HOST})
    ok(quiet.reader.look()["label"] is None,
       "switched off: the reader stops deriving a name at all")
    clock.advance(2.0)
    quiet.tick()
    clock.advance(1.0)
    quiet.tick()
    quiet_said = [l["text"] for l in quiet.say if l["kind"] == "callout"]
    ok(quiet.drifts == 1 and quiet_said
       and quiet_said[0] in focus.CALLOUTS[1] and not named_hits(quiet_said[0]),
       "switched off: the drift is still called out, from the nameless pool",
       json.dumps(quiet_said))
    try:
        quiet._emit(focus.CALLOUTS_NAMED[1][0], "callout", label=MADEUP_LABEL)
        ok(False, "switched off: _emit refuses a template with a name in it")
    except ValueError:
        ok(True, "switched off: _emit refuses a template with a name in it")
finally:
    focus.NAME_DRIFTS = True

try:
    namer._emit(focus.CALLOUTS_NAMED[1][0], "callout", label="")
    ok(False, "a naming line with nothing to name is refused, not spoken half-empty")
except ValueError:
    ok(True, "a naming line with nothing to name is refused, not spoken half-empty")

# --- four lines a tier, so a long drift does not loop three phrases --------------
ok(all(len(pool) >= 4 for pool in focus.CALLOUTS_NAMED.values())
   and len(focus.CALLOUTS_INTENT_NAMED) >= 4 and len(focus.CALLOUTS_DRILL_NAMED) >= 4,
   "every named pool has at least four lines in it",
   json.dumps({t: len(p) for t, p in focus.CALLOUTS_NAMED.items()}))
ok(all("{label}" in t for pool in focus.CALLOUTS_NAMED.values() for t in pool),
   "and every line in them actually uses the name")
ok(focus.NAMED_LINES < focus.LINE_REGISTRY,
   "the named lines are a subset of the registry, so _emit can still gate them")

# --- the first callout names both the work and the distraction -------------------
both = focus.FocusSession(minutes=30)
both.set_intent("the thumbnail sprint")
frontmost.update({"app": APP_TARGET, "host": HOST_TARGET})
for _ in range(focus.SETTLE_TICKS + 1):
    clock.advance(2.0)
    both.tick()
frontmost.update({"app": APP_TARGET, "host": MADEUP_HOST})
clock.advance(2.0)
both.tick()
clock.advance(1.0)
both.tick()
first = [l["text"] for l in both.say if l["kind"] == "callout"][:1]
ok(first and "the thumbnail sprint" in first[0] and MADEUP_LABEL in first[0],
   "the first callout of a session names the work AND the place",
   json.dumps(first))
clock.advance(focus.LABEL_LINE_TTL_S + 1.0)
both.tick()
ok(not state_hits(focus.public_state(both)),
   "and it is scrubbed like any other named line, intent and all")

# --- the register you asked for --------------------------------------------------
sarge = focus.FocusSession(minutes=30)
sarge.set_drill(True)
ok(sarge.drill and focus.public_state(sarge)["drill"] is True
   and any(l["text"] == focus.LINES["drill_on"] for l in sarge.say),
   "drill sergeant is a boolean about HOW you are spoken to, and it says so")
ok(sarge._callout_pool("Instagram") is focus.CALLOUTS_DRILL_NAMED
   and sarge._callout_pool(None) is focus.CALLOUTS_DRILL,
   "in drill mode both pools are the drill pools, named and nameless")
sarge.set_drill(False)
ok(not sarge.drill and sarge._callout_pool(None) is not focus.CALLOUTS_DRILL
   and any(l["text"] == focus.LINES["drill_off"] for l in sarge.say),
   "and it goes back, mid-session, because you asked for it in the first place")
ok(focus.parse_command("be harsh with me", True) == ("drill", {})
   and focus.parse_command("call me out properly", True) == ("drill", {})
   and focus.parse_command("ease up", True) == ("gentle", {}),
   "the phrases for it are heard, and heard before the nag cadence takes them",
   json.dumps([focus.parse_command("call me out properly", True)]))
ok(focus.parse_command("call me out every 30 seconds", True)
   == ("nag", {"seconds": 30}),
   "while an instruction about the cadence is still an instruction about the cadence")

# --- and nothing in this module writes the name anywhere at all ------------------
writes = re.findall(r"open\([^)]*?,\s*[\"']([wa][^\"']*)[\"']", module_source)
ok(writes == ["w"],
   "focus.py opens exactly one file for writing, and it is the ledger",
   json.dumps(writes))
ok("label" not in [k.lower() for k in focus.PUBLIC_KEYS],
   "there is no key in PUBLIC_KEYS that a name could be put into")

try:
    os.remove(focus.LEDGER_PATH)
    os.rmdir(_ledger_dir)
except OSError:
    pass

print("\n  %d checks, %d failed\n" % (checks, len(failures)))
if failures:
    for claim in failures:
        print("    FAILED: %s" % claim)
    print("")
sys.exit(min(len(failures), 120))
