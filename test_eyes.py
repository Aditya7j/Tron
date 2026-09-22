"""Proves what the webcam organ sends, when it speaks, and when it shuts up.

The eyes are the one organ pointed at your body, so the claims worth testing are not
about accuracy at all - they are about what leaves the machine and who is allowed a
word. Five of them, and each one is checked against the code rather than against a
comment:

  1. BOOLEANS, AND NOTHING ELSE. POST /eyes reads exactly four names. A payload that
     also carries an image, a landmark, a coordinate or a measurement of a face changes
     nothing and appears nowhere, and no reply this module can produce contains one -
     which is proved by sending all of them and hunting for them in what comes back.
  2. THE TIMINGS ARE THE STATED ONES. 700 ms of sustained posture, twelve seconds of
     grace for an empty chair, one nudge then thirty seconds of quiet, and three
     minutes of silence from the relief valve. The numbers are read out of focus.py
     and out of the tuning the page is handed, so the two cannot drift apart.
  3. ONE NUDGER PER MOMENT. With a session running a head-down posture becomes a
     counted drift with its own line pool, spoken through the say queue. With no
     session the line comes back in the reply for the posting tab to say. Never both,
     and never neither.
  4. THE EYES NEVER NAME ANYTHING. Every line the organ can say is in LINE_REGISTRY,
     none of them is a naming template, and spoken_line() - the second speaking path -
     refuses both an unregistered line and a named one.
  5. THE EAR LAW. No organ turns the microphone on. The eyes coming on with the mic
     off is SAID, in the server's words; the page's copy of that sentence is compared
     character for character; and the page is searched for a second caller of
     startListening(), because the law is only as good as the grep.

A fake clock drives the cooldown and the valve, so nothing here waits in real time.

Run it:  python test_eyes.py
Exit status is the number of failures.
"""

import io
import json
import os
import re
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import focus                                                   # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:                                              # noqa: BLE001
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
PAGE = os.path.join(HERE, "viewer", "index.html")

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


def head(title):
    print("\n  -- %s" % title)


# --------------------------------------------------------------- a fake clock

class Clock:
    def __init__(self):
        self.t = 50000.0

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

# No reader and no ledger: this file is about the camera, and a posture nudge must
# work on a machine where nothing else can be seen at all.
focus.READER_BACKEND = lambda: {"app": None, "title": None, "url": None}
import tempfile                                                # noqa: E402

_ledger_dir = tempfile.mkdtemp(prefix="focus-eyes-")
focus.LEDGER_PATH = os.path.join(_ledger_dir, "focus-ledger.json")

page_source = io.open(PAGE, encoding="utf-8").read()
focus_source = io.open(os.path.join(HERE, "focus.py"), encoding="utf-8").read()


def fresh_eyes():
    """A clean organ, so one test's cooldown is never another test's mystery."""
    focus.EYES = focus.Eyes()
    return focus.EYES


def end_session():
    with focus.MANAGER._lock:                                  # noqa: SLF001
        focus.MANAGER._session = None                          # noqa: SLF001


def install_session(minutes=25, state="running"):
    """A session, WITHOUT the manager's tick thread.

    MANAGER.command("start") would start that thread, and the thread sleeps on the
    clock this file replaced - so it would spin, advancing time by a second per
    iteration as fast as the CPU allows, and every window below would be long expired
    before it was measured. The eyes are driven by hand here for the same reason the
    clock is.
    """
    session = focus.FocusSession(minutes)
    session.state = state
    with focus.MANAGER._lock:                                  # noqa: SLF001
        focus.MANAGER._session = session                       # noqa: SLF001
    return session


print("\n  the eyes  ·  three booleans out, one sentence back, and no picture\n")

# =========================================================== 1. the payload

head("what the camera is allowed to send")

# Every name a well-meaning refactor might add, sent all at once. If any of them
# mattered, something below would change or something would come back.
SMUGGLE = {
    "frame": "data:image/jpeg;base64,ZZZSMUGGLEDPIXELSZZZ",
    "image": "ZZZSMUGGLEDPIXELSZZZ",
    "landmarks": [{"x": 0.1234, "y": 0.5678, "z": 0.9}],
    "faceLandmarks": [[0.1, 0.2]],
    "pitch": 1.4142, "drop": 0.7071, "confidence": 0.99,
    "eyeSpan": 0.1337, "faceId": "ZZZSMUGGLEDIDENTITYZZZ",
    "name": "ZZZSMUGGLEDIDENTITYZZZ", "app": "ZZZSMUGGLEDIDENTITYZZZ",
}
SMUGGLE_MARKS = ["ZZZSMUGGLEDPIXELS", "ZZZSMUGGLEDIDENTITY", "0.1234", "1.4142",
                 "0.1337", "landmark", "confidence", "pitch"]

fresh_eyes()
end_session()
status, body = focus.handle_eyes(dict(SMUGGLE, cmd="on", present=True, ears=True))
blob = json.dumps(body, ensure_ascii=False)
ok(status == 200, "POST /eyes accepts a report", str(status))
ok(not any(m.lower() in blob.lower() for m in SMUGGLE_MARKS),
   "a payload full of pixels, landmarks and identities comes back with none of them",
   "; ".join(m for m in SMUGGLE_MARKS if m.lower() in blob.lower()))
ok(set(body) == {"ok", "kind", "nodes", "answer", "viaSession", "cmd", "tuning",
                 "focus"},
   "the reply has exactly the documented keys", sorted(body))
ok(not any(k in json.dumps(body["focus"]) for k in ("pitch", "drop", "landmark")),
   "and the focus state it carries holds no measurement of a face")

# The object the booleans land in has room for nothing else. Four booleans, two
# clocks, a count - and no attribute a frame or a landmark could be parked in.
fields = sorted(vars(fresh_eyes()))
ok(fields == ["at", "head_down", "hush_until", "last_nudge", "nudges", "on",
              "present", "slouched"],
   "the Eyes object has no field a picture or a measurement could live in",
   str(fields))

# The one frame that IS sent is asked for out loud, and it goes somewhere else
# entirely: /look, in server.py, with a question attached.
ok("def handle_eyes" in focus_source and "frame" not in
   focus_source.split("def handle_eyes")[1].split("\ndef ")[0].replace(
       "no image, no landmark", ""),
   "handle_eyes() has no frame handling in it at all")
ok(re.search(r"/eyes", page_source) and
   page_source.count("JSON.stringify(body)") >= 1,
   "the page posts the eyes as JSON, not as bytes")

payload_block = page_source.split("const body = {", 1)[1].split("};", 1)[0]
sent_keys = sorted(re.findall(r"^\s*(\w+):", payload_block, re.M))
ok(sent_keys == ["cmd", "ears", "headDown", "present", "slouched"],
   "and the whole body it builds is cmd, present, headDown, slouched, ears",
   str(sent_keys))
ok("audio: false" in page_source and "getUserMedia" in page_source,
   "the camera is asked for with audio:false - the ear law, in the request itself")

# =========================================================== 2. the timings

head("the numbers, in one place")

ok(focus.EYE_SUSTAIN_MS == 700,
   "a posture must hold for 700 ms before a word is said", str(focus.EYE_SUSTAIN_MS))
ok(focus.EYE_ABSENCE_MS == 12000,
   "an empty chair gets twelve seconds, because a glance is not leaving",
   str(focus.EYE_ABSENCE_MS))
ok(focus.EYE_COOLDOWN_S == 30.0,
   "one nudge, then thirty seconds of quiet", str(focus.EYE_COOLDOWN_S))
ok(focus.RELIEF_S == 180.0,
   "the relief valve is three minutes", str(focus.RELIEF_S))
ok(focus.EYE_PHONE_DRIFTS is True,
   "a phone posture counts as a drift, like a tab drift")

tuning = fresh_eyes().tuning()
ok(tuning == {"sustainMs": 700, "absenceMs": 12000, "cooldownS": 30, "staleS": 6,
              "reliefS": 180, "countsAsDrift": True},
   "and the page is handed those same numbers with every report", json.dumps(tuning))
ok(all(isinstance(v, (int, bool)) for v in tuning.values()),
   "the tuning is plain numbers and booleans, so no page has to parse anything")

_, body = focus.handle_eyes({"cmd": "posture", "present": True})
ok(body["tuning"] == tuning, "the tuning rides back on every reply, not just the first")

# The page's own defaults, for the one moment before the first reply lands. They are
# allowed to exist; they are not allowed to disagree.
page_tune = page_source.split("let EYE_TUNE = {", 1)[1].split("};", 1)[0]
page_nums = dict(re.findall(r"(\w+):\s*([\d.]+|true|false)", page_tune))
ok(int(page_nums.get("sustainMs", -1)) == focus.EYE_SUSTAIN_MS and
   int(page_nums.get("absenceMs", -1)) == focus.EYE_ABSENCE_MS and
   int(page_nums.get("cooldownS", -1)) == int(focus.EYE_COOLDOWN_S) and
   int(page_nums.get("reliefS", -1)) == int(focus.RELIEF_S),
   "the page's fallback windows are the server's windows", json.dumps(page_nums))

# ==================================================== 3. freshness and belief

head("what the organ refuses to believe")

eyes = fresh_eyes()
eyes.report(True, True, True, False, clock.monotonic())
ok(eyes.posture()["head_down"] is True, "a fresh head-down report is believed")
clock.advance(focus.EYE_STALE_S + 0.1)
stale = eyes.posture()
ok(stale == {"fresh": False, "present": False, "head_down": False, "slouched": False},
   "a page that went quiet stops holding a posture at all", json.dumps(stale))
ok(focus.public_state(None)["eyesOn"] is False,
   "and the state says the eyes are shut rather than stale")

eyes = fresh_eyes()
eyes.report(True, False, True, True, clock.monotonic())
ok(eyes.posture() == {"fresh": True, "present": False, "head_down": False,
                      "slouched": False},
   "a posture read off an empty chair is the detector guessing, and is dropped")

eyes = fresh_eyes()
eyes.report(True, True, False, True, clock.monotonic())
posture = eyes.posture()
ok(posture["slouched"] is True and posture["head_down"] is False,
   "a slouch is a slouch and not a phone")

# ========================================================= 4. the line pools

head("every line the eyes can say")

# The counted tiers say how many times you have done it, so they DO have fields -
# all of them numbers. This is the whitelist, and a field outside it is the way a
# name would arrive in a spoken line.
NUMERIC_FIELDS = {"drifts", "nth", "nth_cap", "times", "times_cap", "span",
                  "minutes", "seconds", "count"}

pools = {"phone tier 1": focus.CALLOUTS_PHONE[1],
         "phone tier 2": focus.CALLOUTS_PHONE[2],
         "phone tier 3": focus.CALLOUTS_PHONE[3],
         "phone drill": focus.CALLOUTS_PHONE_DRILL,
         "slouch": focus.NUDGES_SLOUCH,
         "absent": focus.NUDGES_ABSENT}
for name, pool in pools.items():
    ok(len(pool) >= 4, "the %s pool has at least four lines, so it cannot be a "
                       "catchphrase" % name, str(len(pool)))
    ok(all(line in focus.LINE_REGISTRY for line in pool),
       "every %s line is in LINE_REGISTRY, so _emit will let it out" % name)
    used = set(re.findall(r"\{(\w+)\}", " ".join(pool)))
    ok(used <= NUMERIC_FIELDS,
       "every field in the %s pool is a NUMBER, not a name" % name,
       str(sorted(used - NUMERIC_FIELDS)))
    ok(not any(line in focus.NAMED_LINES for line in pool),
       "and no %s line is a naming template" % name)

everything = [line for pool in pools.values() for line in pool]
ok(len(set(everything)) == len(everything),
   "no line appears in two pools, so a tier cannot be mistaken for another")
for key in ("eyes_on", "eyes_off", "eyes_blind", "ears_off", "relief"):
    ok(focus.LINES[key] in focus.LINE_REGISTRY,
       "LINES[%r] is registered" % key)
ok("no picture of you leaves this machine" in focus.LINES["eyes_on"],
   "opening the eyes says what does not leave", focus.LINES["eyes_on"])

# The second speaking path is gated exactly as hard as the first.
ok(focus.spoken_line(focus.LINES["eyes_off"]) == focus.LINES["eyes_off"],
   "spoken_line() says a registered line")
try:
    focus.spoken_line("Sir, you are slouching like a deckchair.")
    ok(False, "spoken_line() refuses a line that is not in the registry")
except ValueError:
    ok(True, "spoken_line() refuses a line that is not in the registry")
named = sorted(focus.NAMED_LINES)[0]
try:
    focus.spoken_line(named, label="somewhere")
    ok(False, "spoken_line() refuses a naming template - the eyes name nothing")
except ValueError:
    ok(True, "spoken_line() refuses a naming template - the eyes name nothing")

# ======================================================= 5. with no session

head("nudging with no clock running")

fresh_eyes()
end_session()
line, via = focus.MANAGER.note_eyes(present=True, head_down=True)
ok(line in focus.CALLOUTS_PHONE[1] and via is False,
   "head down with no session: one line, back to the tab that posted it", repr(line))
ok(focus.EYES.nudges == 1, "and it is counted as one nudge", str(focus.EYES.nudges))

line2, via2 = focus.MANAGER.note_eyes(present=True, head_down=True)
ok(line2 is None and via2 is False,
   "still bent a moment later: nothing said, because one nudge is one nudge", repr(line2))
clock.advance(focus.EYE_COOLDOWN_S - 1)
line3, _ = focus.MANAGER.note_eyes(present=True, head_down=True)
ok(line3 is None, "twenty nine seconds later: still quiet", repr(line3))
clock.advance(2)
line4, _ = focus.MANAGER.note_eyes(present=True, head_down=True)
ok(line4 in focus.CALLOUTS_PHONE[1],
   "past the cooldown: one more line, and only one", repr(line4))

fresh_eyes()
line, via = focus.MANAGER.note_eyes(present=True, slouched=True)
ok(line in focus.NUDGES_SLOUCH and via is False,
   "a sustained slouch earns a nudge from its own pool", repr(line))

fresh_eyes()
line, via = focus.MANAGER.note_eyes(present=False)
ok(line in focus.NUDGES_ABSENT and via is False,
   "an empty chair earns a nudge from its own pool", repr(line))

fresh_eyes()
line, via = focus.MANAGER.note_eyes(present=True)
ok(line is None and via is False, "and sitting up straight earns silence", repr(line))

# The ear law, said by the server, in the one moment it is felt as a fault.
fresh_eyes()
line, _ = focus.MANAGER.note_eyes(cmd="on", ears=False)
ok(focus.LINES["ears_off"] in line,
   "the eyes opening with the mic off says so, unprompted", repr(line))
fresh_eyes()
line, _ = focus.MANAGER.note_eyes(cmd="on", ears=True)
ok(focus.LINES["ears_off"] not in line and line == focus.LINES["eyes_on"],
   "with the ears already open it says nothing about them", repr(line))
fresh_eyes()
line, _ = focus.MANAGER.note_eyes(cmd="on", ears=None)
ok(focus.LINES["ears_off"] not in line,
   "and a page that did not say is not told off for a mic that may be on", repr(line))

# ==================================================== 6. inside a session

head("the eyes feeding the focus session")

fresh_eyes()
end_session()
session = install_session()
session.say = []
drifts_before = session.drifts

seq_before = session.seq
line, via = focus.MANAGER.note_eyes(present=True, head_down=True)
spoken = [entry["text"] for entry in session.say]
ok(via is True and line is None,
   "head down with a session running: the line goes into the say queue, not the reply")
ok(session.seq > seq_before and spoken and spoken[-1] in focus.CALLOUTS_PHONE[1],
   "and it comes out of the phone pool", json.dumps(spoken))
ok(session.drifts == drifts_before + 1,
   "a phone drift is counted like a tab drift", str(session.drifts))
ok(session._off_kind == "phone",                               # noqa: SLF001
   "and the session knows which kind of drift it is in")

public = focus.public_state(session)
ok(public["postureDrift"] is True and public["headDown"] is True and
   public["eyesOn"] is True,
   "the card can say head down without naming anything", json.dumps(
       {k: public[k] for k in ("postureDrift", "headDown", "eyesOn", "drifting")}))
ok(isinstance(public["nudges"], int) and isinstance(public["hushLeftS"], int),
   "the eyes' own numbers are numbers")

session.say = []
focus.MANAGER.note_eyes(present=True, head_down=False)
session.tick()
ok(session._off_kind == "tab",                                 # noqa: SLF001
   "head up and the session is back on ordinary terms")

# ====================================================== 7. the relief valve

head("the relief valve")

for phrase in ["no Jarvis, I need to do something important",
               "give me a minute",
               "I have to do something",
               "leave me alone",
               "give me a few minutes",
               "I'll be right back"]:
    ok(focus.parse_command(phrase, False) == ("relief", {}),
       "%r is the relief valve, with no session needed" % phrase,
       repr(focus.parse_command(phrase, False)))

# And it is not so wide that ordinary sentences trip it.
for phrase in ["what did I write about the important parts of the roadmap",
               "how long is left",
               "remember that the minute hand is broken"]:
    parsed = focus.parse_command(phrase, False)
    ok(parsed is None or parsed[0] != "relief",
       "%r is not the relief valve" % phrase, repr(parsed))

fresh_eyes()
end_session()
answer, state = focus.MANAGER.command("relief")
ok("silence" in answer and "important thing" in answer,
   "with no session, the valve answers in the tab that asked", repr(answer))
ok(focus.EYES.hushed() is True and round(focus.EYES.hush_left()) == 180,
   "three minutes of silence, and the state says how much is left",
   str(focus.EYES.hush_left()))
ok(state["hushed"] is True and state["hushLeftS"] == 180,
   "which the card can show", json.dumps({"hushed": state["hushed"],
                                          "hushLeftS": state["hushLeftS"]}))

line, via = focus.MANAGER.note_eyes(present=True, head_down=True)
ok(line is None and via is False, "and a phone posture during it says nothing at all",
   repr(line))
clock.advance(179)
line, _ = focus.MANAGER.note_eyes(present=True, head_down=True)
ok(line is None, "still nothing at two minutes fifty nine", repr(line))
clock.advance(2)
line, _ = focus.MANAGER.note_eyes(present=True, head_down=True)
ok(line in focus.CALLOUTS_PHONE[1],
   "and past three minutes the eyes are allowed a word again", repr(line))

# The valve outranks the cooldown, which is the entire point of having one.
fresh_eyes()
focus.EYES.spend(clock.monotonic())
ok(focus.EYES.may_nudge() is False, "a spent nudge starts a cooldown")
focus.EYES.hush(focus.RELIEF_S)
ok(focus.EYES.may_nudge() is False, "and a hush during it is still a hush")
clock.advance(focus.EYE_COOLDOWN_S + 1)
ok(focus.EYES.may_nudge() is False,
   "the cooldown expiring inside the valve does not reopen the mouth")

# With a session, the same sentence silences the session too and the clock keeps
# running - a valve that stopped the clock would be a pause with a nicer name.
fresh_eyes()
end_session()
session = install_session()
session.say = []
answer, state = focus.MANAGER.command("relief")
ok(state["state"] == "running" and state["snoozed"] is True,
   "with a session, the valve hushes it and the clock keeps running",
   json.dumps({"state": state["state"], "snoozed": state["snoozed"]}))
ok(state["hushed"] is True, "and the eyes are hushed by the same sentence")
said = [entry["text"] for entry in session.say]
ok(said and "silence" in said[-1],
   "spoken through the session, so every open tab hears it once", json.dumps(said))
end_session()

# ======================================================== 8. the ear law, in the page

head("the ear law, where it has to hold")

ok(EARS := re.search(r"const EARS_OFF_LINE = '([^']*)'", page_source),
   "the page has one copy of the ear-law line")
ok(EARS and EARS.group(1) == focus.LINES["ears_off"],
   "and it is character for character the server's sentence",
   repr(EARS.group(1) if EARS else None))

calls = re.findall(r"startListening\(\)\s*;", page_source)
ok(len(calls) == 1,
   "exactly one line in the page calls startListening()", str(len(calls)))
click_block = page_source.split("$('mic').onclick", 1)
ok(len(click_block) == 2 and "startListening();" in click_block[1][:400],
   "and it is the ear button")

eyes_block = page_source.split("================================================================= eyes ==", 1)
ok(len(eyes_block) == 2, "the eyes have their own section in the page")
eyes_only = eyes_block[1].split("async function ask(", 1)[0]
ok(not re.findall(r"startListening\(\)\s*;", eyes_only),
   "and nothing in it reaches for the microphone")
ok("audio: false" in eyes_only, "it asks for pixels with audio switched off")

# The mute gate, still the only one, and a muted tab still publishes.
ok(page_source.count("if (MUTED)") == 2 and "const MUTED = /(^|[?&])mute=1" in page_source,
   "?mute=1 is read once and gates only speak() and the idle status")
ok("noteSaid(line, false); return false; }   // the mute gate" in page_source,
   "a muted tab records the line it did not say, so a test tab is still checkable")

# ======================================================= 9. the look, and the screen

head("look at me, and what is not a look")

look_re = re.search(r"const LOOK_RE = new RegExp\((.*?), 'i'\);", page_source, re.S)
ok(bool(look_re), "the page has a LOOK_RE")
ok("'/look?q='" in page_source.replace('"', "'") or "/look?q=" in page_source,
   "and it posts the one frame to /look")
ok("grabFrame('cam')" in page_source,
   "grabbed from the camera by the one grabber, after the question exists")
ok(len(re.findall(r"getUserMedia\(\{", page_source)) == 1 and
   page_source.count("navigator.mediaDevices.getUserMedia") == 2,
   "there is exactly one call that opens a camera, and one check that it exists",
   str(page_source.count("navigator.mediaDevices.getUserMedia")))

print("\n  %d checks, %d failed\n" % (checks, len(failures)))
if failures:
    for claim in failures:
        print("    FAILED: %s" % claim)
    print("")
try:
    os.remove(focus.LEDGER_PATH)
    os.rmdir(_ledger_dir)
except OSError:
    pass
sys.exit(min(len(failures), 120))
