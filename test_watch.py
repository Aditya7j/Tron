"""Proves that the screen watch costs nothing until it needs to think.

The watch is the one organ that may speak without being asked, and the one that runs
for hours at a time. Both of those make the interesting claims about MONEY and SILENCE
rather than about accuracy, so that is what this file checks - and it checks each one
against the code rather than against a comment:

  1. THE LOOP IS FREE. The page's watch section contains exactly one fetch that can
     carry a frame, it is inside nudgeNow(), and nudgeNow() is reachable from the tick
     only past the stillness threshold. A tick that is not a nudge has no code path to
     a network call at all - which is proved by reading the section rather than by
     promising it.
  2. THE GUARDS ARE FREE TOO, AND THEY ARE ORDERED. Relief valve, then the cooldown,
     then the stillness - each refused before a byte is looked at as an image, each
     with "quiet": true so the page says nothing, and every one of them with the model
     call replaced by something that would explode if it were ever reached.
  3. THE COOLDOWN IS SPENT LAST. A nudge that failed to reach the brain must not buy
     three minutes of silence, or the next one is punished for the first one's bad luck.
  4. THE RELIEF VALVE COVERS THIS ORGAN. "No Jarvis, I need to do something important"
     lives in the eyes and silences EVERY nudge. It is checked here by opening it over
     there and asking this route for one.
  5. ONE SET OF NUMBERS. The stillness window, the cooldown, the tick, the thumbnail
     and both diff thresholds are stated once in server.py, handed to the page in every
     reply, and the page's own defaults are compared against them character by
     character - so the half that measures and the half that pays cannot drift apart.
  6. THE TAB-SHARE TRAP. A captured tab cannot police tabs. The page refuses 'browser'
     and 'window' out loud, names Entire Screen in the refusal, and asks for a monitor
     in the picker - and it asks the TRACK what it got rather than trusting the hint.
  7. IT NEVER TOUCHES THE CAMERA. The watch section reaches for FRAME_SOURCES.screen
     and nothing else: no getUserMedia, no startEyes, no 'cam'.
  8. NO NOTES GO IN AND NONE COME OUT. A screen that has sat still for a minute is not
     a fact about the corpus, so the nudge carries no history, indexes no note and
     returns an empty nodes list.

A fake clock drives the cooldown and the valve, so nothing here waits in real time.
The frame is three magic bytes and some padding, because this file is about the gates
and not about the codec - the real, decodable JPEG lives in preflight.py, where a real
model looks at it.

Run it:  python test_watch.py
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
    """Everything with a window in it reads time.monotonic(). Replace it in both
    modules and the three minutes below take no time at all."""

    def __init__(self):
        self.t = 90000.0

    def monotonic(self):
        return self.t

    def time(self):
        return 1770000000.0 + (self.t - 90000.0)

    def sleep(self, seconds):
        self.t += seconds

    def strftime(self, fmt, *args):
        return "2026-01-01"

    def localtime(self, *args):
        import time as _real
        return _real.localtime()

    def advance(self, seconds):
        self.t += seconds


clock = Clock()
focus.time = clock

# No reader and no ledger: the watch works on a machine where nothing else can be
# seen at all, and this file must not write a ledger into anyone's project folder.
focus.READER_BACKEND = lambda: {"app": None, "title": None, "url": None}
import tempfile                                                # noqa: E402

_ledger_dir = tempfile.mkdtemp(prefix="focus-watch-")
focus.LEDGER_PATH = os.path.join(_ledger_dir, "focus-ledger.json")

import server                                                  # noqa: E402

server.time = clock

page_source = io.open(PAGE, encoding="utf-8").read()
server_source = io.open(os.path.join(HERE, "server.py"), encoding="utf-8").read()

# The watch's own section of the page, and the two halves of it that matter. Sliced
# out rather than searched for across the whole file, because "there is exactly one
# fetch" is only a true claim about a bounded region.
WATCH_SECTION = page_source.split("================================================================ watch ==", 1)
watch_js = WATCH_SECTION[1].split("async function ask(", 1)[0] if len(WATCH_SECTION) == 2 else ""

# Enough of a JPEG to pass the header checks and the size floor. See the docstring.
FRAME = b"\xff\xd8\xff\xe0" + b"JFIF\x00" + (b"\x5a" * 1400)


def fresh_watch():
    """A clean purse, so one test's cooldown is never another test's mystery."""
    server.WATCH = server.Watch()
    focus.EYES = focus.Eyes()
    return server.WATCH


class Exploded(Exception):
    """Raised by the stubs below. If this ever escapes, something that was supposed
    to be free spent money."""


def no_brain(*args, **kwargs):
    raise Exploded("the model was called on a path that is supposed to be free")


def stub_brain(answer="Line 41: the assertion compares a Decimal with a float.",
               error=None):
    """A brain that answers instantly and records that it was asked. The nudge's
    quality is not testable here; whether it was PAID FOR is, exactly."""
    calls = []

    def call(cfg, messages, image=None):
        calls.append({"image": len(image or b""), "messages": messages})
        return answer, error

    server.call_model = call
    server.load_config = lambda: ({"provider": "bedrock", "model": "x"}, None)
    server.credentials_error = lambda cfg: None
    return calls


def nudge(still_s=90.0, width=1280, height=720, age_ms=200, frame=FRAME,
          declared="image/jpeg"):
    return server.nudge_for_stuck(frame, declared, width, height, age_ms, still_s)


print("\n  the watch  ·  576 grey numbers a tick, and one frame a minute at most\n")

# ===================================================== 1. the loop is free

head("what the five-second loop costs")

ok(bool(watch_js), "the watch has its own section in the page",
   "the section header was not found")

# The whole claim, in one number. A fetch inside this section that is NOT the nudge
# would be a loop that talks to the network on a schedule.
fetches = re.findall(r"fetch\(([^\n]*)", watch_js)
ok(len(fetches) == 2,
   "the watch section contains exactly two fetches", str(fetches))
ok(any("'/stuck'" in f for f in fetches) and any("'/stuck?stillS='" in f for f in fetches),
   "and both are /stuck: the windows on start, and the one nudge", str(fetches))

tick = watch_js.split("function watchTick()", 1)
ok(len(tick) == 2, "there is a watchTick()")
# The tick reads the screen; watchFeed() decides. Both are read here, because "the
# loop never touches the network" is a claim about the pair of them.
tick_body = tick[1].split("\n  async function", 1)[0] if len(tick) == 2 else ""
ok("fetch(" not in tick_body,
   "neither the tick nor the feed it hands off to touches the network")
ok("if (watchStillMs() < WATCH_TUNE.stillS * 1000) return verdict;" in tick_body,
   "and it returns before nudgeNow() unless the stillness threshold is past")
ok(tick_body.index("stillS * 1000) return") < tick_body.index("nudgeNow()"),
   "the threshold is checked BEFORE the nudge, not after it")
# The seam, for the same reason the eyes have one: recorded input through the one
# door the real input comes through.
ok("function watchFeed(now)" in watch_js and "feed: watchFeed" in page_source,
   "the diff is driven through one seam, which a test can drive by hand")
ok(len(re.findall(r"watchFeed\(", watch_js)) == 2,
   "and the tick is the only thing in the organ that feeds it",
   str(re.findall(r".{20}watchFeed\(", watch_js)))

# The diff: the only thing that runs every five seconds, and it has no way out of the
# process at all. No fetch, no blob, no toBlob, no object URL.
diff_block = watch_js.split("const WATCH_DIFF = {", 1)
ok(len(diff_block) == 2, "the diff is written as one object")
diff_only = diff_block[1].split("\n  };", 1)[0] if len(diff_block) == 2 else ""
for forbidden in ("fetch", "toBlob", "createObjectURL", "XMLHttpRequest", "sendBeacon",
                  "WebSocket", "FormData"):
    ok(forbidden not in diff_only,
       "the diff has no %s in it" % forbidden)
ok("getImageData" in watch_js and "toBlob" not in watch_js.split("async function nudgeNow", 1)[0],
   "the thumbnail is read back with getImageData and never encoded")

# 32x18 is 576 cells. Stated in the canvas element too, so a glance at the markup
# says how much of your screen this ever looks at.
ok('<canvas id="thumb" width="32" height="18"' in page_source,
   "the thumbnail canvas is 32x18 in the markup as well")

# ===================================================== 2. the guards, in order

head("the three refusals, each of them free")

fresh_watch()
server.call_model = no_brain          # any model call from here is a test failure

# 3rd guard first, on its own: the screen is still moving.
status, body = nudge(still_s=12.0)
ok(status == 409, "a screen still moving is refused 409", str(status))
ok(body["quiet"] is True,
   "and the refusal is quiet - the page says nothing about a nudge it did not make")
ok(body["spent"] is False and body["why"] == "moving",
   "nothing was spent and the reason is named", json.dumps(body.get("why")))
ok("12 seconds" in body["error"],
   "the sentence says how long it has actually been still", body["error"])
ok(server.WATCH.nudges == 0 and server.WATCH.refused == 1,
   "the purse counts it as a refusal, not as a nudge",
   "nudges=%d refused=%d" % (server.WATCH.nudges, server.WATCH.refused))

# The purse. One nudge, then the cooldown, however still the screen stays.
fresh_watch()
calls = stub_brain()
status, body = nudge()
ok(status == 200 and body["spent"] is True,
   "a minute of stillness with an open purse buys one nudge", str(status))
ok(len(calls) == 1 and calls[0]["image"] == len(FRAME),
   "exactly one model call, carrying exactly one frame", str(len(calls)))
ok(body["unasked"] is True and body["quiet"] is False,
   "it is marked unasked, and it is not quiet")

server.call_model = no_brain          # the second one must not reach the brain
status, body = nudge()
ok(status == 429 and body["why"] == "cooldown",
   "the second nudge inside the cooldown is refused 429", str(status))
ok(body["quiet"] is True and body["spent"] is False,
   "quietly, and free")
ok("%d seconds" % int(server.STUCK_COOLDOWN_S) in body["error"] or
   re.search(r"\b1[0-9][0-9] seconds\b", body["error"]),
   "and it says how long is left", body["error"])

clock.advance(server.STUCK_COOLDOWN_S - 1)
ok(server.nudge_for_stuck(FRAME, "image/jpeg", 1280, 720, 200, 90.0)[0] == 429,
   "one second short of the cooldown it is still refused")
clock.advance(2)
calls = stub_brain()
status, body = nudge()
ok(status == 200 and len(calls) == 1,
   "a second past it, the purse opens again", str(status))

# And the order: with the valve open AND the cooldown running AND the screen moving,
# the valve is the one that answers - the cheapest refusal wins.
fresh_watch()
server.call_model = no_brain
focus.EYES.hush(focus.RELIEF_S)
server.WATCH.spend()
status, body = nudge(still_s=3.0)
ok(status == 429 and body["why"] == "hushed",
   "valve, cooldown and a moving screen at once: the valve answers", str(body["why"]))

# ============================================ 3. the cooldown is spent last

head("a nudge that never arrived buys no silence")

fresh_watch()
stub_brain(answer=None, error="Bedrock refused the call: ThrottlingException.")
status, body = nudge()
ok(status == 502 and body["spent"] is False,
   "a brain that fails comes back 502 and spends nothing", str(status))
ok(server.WATCH.may_nudge(),
   "so the purse is still open: the next nudge is not punished for this one's bad luck")
ok(body["quiet"] is False,
   "and this one IS said out loud - a watch that cannot reach its brain is worth "
   "hearing about")

# The same rule for a frame that will not do, and for a machine with no key in it.
fresh_watch()
server.call_model = no_brain
status, body = nudge(frame=b"\x89PNG\r\n\x1a\n" + b"\x00" * 1400)
ok(status == 400 and body["why"] == "mismatch",
   "a PNG declared as a JPEG is refused before the brain", str(body.get("why")))
ok(body["spent"] is False and server.WATCH.may_nudge(),
   "and it costs neither a call nor the cooldown")
ok(body["quiet"] is False,
   "a frame fault is spoken: the watch has gone blind while claiming to watch")

fresh_watch()
status, body = nudge(age_ms=45000)
ok(status == 400 and body["why"] == "stale",
   "a frame grabbed 45 seconds ago is refused", str(body.get("why")))
fresh_watch()
status, body = nudge(frame=b"\xff\xd8\xff" + b"\x00" * 20)
ok(status == 400 and body["why"] == "tiny",
   "and so is 23 bytes of header", str(body.get("why")))

# =========================================== 4. the relief valve covers this

head("the silence the eyes were asked for includes this organ")

fresh_watch()
server.call_model = no_brain
focus.EYES.hush(focus.RELIEF_S)
status, body = nudge()
ok(status == 429 and body["why"] == "hushed",
   "with the eyes' valve open, a perfectly earned nudge is refused", str(status))
ok(body["quiet"] is True, "quietly - an announced silence is not a silence")
ok(body["watch"]["hushed"] is True and body["watch"]["hushLeftS"] > 170,
   "and the reply says how much of it is left", json.dumps(body["watch"]))
ok(server.WATCH.may_nudge(),
   "the valve does not spend the cooldown either: it is three minutes off, not a nudge")

clock.advance(focus.RELIEF_S + 1)
calls = stub_brain()
ok(nudge()[0] == 200 and len(calls) == 1,
   "when the three minutes are up, the watch speaks again")

# The valve is read from the organ that owns it, not copied. One grep, because a
# second copy of a promise is a promise that will one day be half kept.
stuck_block = server_source.split("def nudge_for_stuck", 1)[1].split("\ndef ", 1)[0]
ok("focus.EYES" not in stuck_block and "state[\"hushed\"]" in stuck_block,
   "nudge_for_stuck() reads the valve through WATCH.state(), in one place")
ok("focus.EYES.hushed(now)" in server_source.split("class Watch", 1)[1],
   "and WATCH.state() reads it from focus.EYES itself")

# ================================================ 5. one set of numbers

head("the windows, stated once")

tuning = server.WATCH.tuning()
ok(tuning["stillS"] == 60, "the screen must sit still for 60 seconds", str(tuning))
ok(tuning["cooldownS"] == 180, "then three minutes of quiet", str(tuning))
ok(tuning["tickMs"] == 5000, "the diff runs every five seconds", str(tuning))
ok((tuning["thumbW"], tuning["thumbH"]) == (32, 18),
   "against a 32x18 thumbnail", str(tuning))
ok(tuning["cellDelta"] == 10 and tuning["changedFraction"] == 0.015,
   "a cell moves at 10 luma, the screen moves at 1.5% of cells", str(tuning))

# The page's defaults, parsed out of the page. Not "roughly the same numbers": the
# same numbers, or the page is applying a threshold the purse does not agree with.
defaults = re.search(r"let WATCH_TUNE = \{(.*?)\};", watch_js, re.S)
ok(bool(defaults), "the page states its defaults in one object literal")
page_tune = {}
if defaults:
    for key, value in re.findall(r"(\w+):\s*([0-9.]+)", defaults.group(1)):
        page_tune[key] = float(value) if "." in value else int(value)
ok(page_tune == tuning,
   "and they are the server's numbers exactly", "%s vs %s" % (page_tune, tuning))

# Every reply carries them, refusals included, so a page that has been open all day
# is corrected by the next thing it hears rather than by a reload.
fresh_watch()
server.call_model = no_brain
for label, call in (("a moving screen", lambda: nudge(still_s=1.0)),
                    ("a bad frame", lambda: nudge(frame=b"nope" * 400))):
    _, payload = call()
    ok(payload.get("tuning") == tuning,
       "the refusal for %s carries the windows back" % label)
calls = stub_brain()
fresh_watch()
_, payload = nudge()
ok(payload.get("tuning") == tuning, "and so does the nudge itself")
ok("if (data && data.tuning) WATCH_TUNE = Object.assign" in watch_js,
   "the page applies what it is handed, every time")
ok("await watchTune();" in watch_js and "fetch('/stuck')" in watch_js,
   "and it asks for them before it starts a clock")

# GET /stuck: the windows and the purse, with no frame and no model call.
get_route = server_source.split('if route == "/stuck":', 1)[1].split("if ", 1)[0]
ok("WATCH.tuning()" in get_route and "call_model" not in get_route,
   "GET /stuck hands over the numbers without calling anything")

# ================================================= 6. the tab-share trap

head("a tab cannot police tabs, and is told so")

ok("displaySurface: 'monitor'" in watch_js,
   "the picker is opened on Entire Screen")
ok("selfBrowserSurface: 'exclude'" in watch_js,
   "and this very tab is kept out of it")
ok("track.getSettings().displaySurface" in watch_js or
   "getSettings().displaySurface" in watch_js,
   "what it actually got is read off the track, not assumed from the hint")
ok("watchSurface === 'browser' || watchSurface === 'window'" in watch_js,
   "a tab and a single window are both refused")
ok(watch_js.count("watchSurface === 'browser' || watchSurface === 'window'") == 2,
   "on the way in AND when the surface is switched mid-share",
   str(watch_js.count("watchSurface === 'browser' || watchSurface === 'window'")))
ok("configurationchange" in watch_js,
   "which is what the configurationchange event is listened for")

trap = re.search(r"tab: '(.*?)',\n\s*window:", watch_js, re.S)
trap_text = re.sub(r"'\s*\+\s*\n\s*'", "", trap.group(1)) if trap else ""
ok("Entire Screen" in trap_text,
   "the refusal names the one thing to do about it", trap_text[:90])
ok("carries on painting itself" in trap_text or "wander" in trap_text,
   "and says why a tab cannot do this job", trap_text[:90])
ok("scrolling" in trap_text,
   "including the half that would read as work", trap_text[:120])
refuse = watch_js.split("function refuseSurface", 1)
ok(len(refuse) == 2 and "speak(" in refuse[1].split("\n  }", 1)[0],
   "and it is spoken, not left in the status line")
ok("if (!had) endShare();" in watch_js,
   "a share this organ opened and may not use is closed again")

# The start phrase and the question about the screen must not collide.
watch_re = re.search(r"const WATCH_RE = new RegExp\(", watch_js)
ok(bool(watch_re), "the page has a WATCH_RE")
# The window is the head of ask() down to the point where the request is actually sent:
# every branch this claim is about lives above that line. It used to be a flat 3000
# characters, which is not a fact about the code - the share branch drifted past it as
# comments were added above it, and the check failed on a file where all three branches
# were still in the right order. Anchored on something real instead.
ask_block = page_source.split("async function ask(question)", 1)[1].split("busy = true", 1)[0]
ok(ask_block.index("WATCH_OFF_RE.test(question)") < ask_block.index("WATCH_RE.test(question)"),
   "\"stop watching\" is tested before \"watch my screen\", which it contains")
ok(ask_block.index("WATCH_RE.test(question)") <
   ask_block.index("sharing() && localKind(question)"),
   "and both are tested before the share branch, which would photograph them instead")

# ============================================ 7. it never touches the camera

head("screen only")

for forbidden in ("getUserMedia", "startEyes(", "eyeFeed(", "'cam'", "camframe"):
    ok(forbidden not in watch_js,
       "the watch section never reaches for %s" % forbidden)
ok("grabFrame('screen')" in watch_js,
   "its one frame comes from the screen source, through the one grabber")
ok(watch_js.count("grabFrame(") == 1,
   "and it grabs exactly once, in nudgeNow()", str(watch_js.count("grabFrame(")))

# ========================================== 8. no notes in, no notes out

head("a still screen is not a fact about the corpus")

fresh_watch()
calls = stub_brain()
_, body = nudge()
ok(body["nodes"] == [], "the nudge cites no notes", str(body["nodes"]))
ok(set(body) == {"answer", "nodes", "kind", "unasked", "quiet", "spent", "stillS",
                 "watch", "tuning", "saw"},
   "and the reply has exactly the documented keys", str(sorted(body)))
ok(body["kind"] == "nudge", "its kind is nudge", body["kind"])
ok("ensure_index" not in stuck_block and "answer_question" not in stuck_block,
   "nudge_for_stuck() neither indexes nor asks the notes brain anything")
ok("history" not in stuck_block and "session" not in stuck_block,
   "and it carries no history and belongs to no session")

# What the model is actually told. Two messages, one of them the standing prompt, and
# no note text anywhere in either.
msgs = calls[0]["messages"]
ok(len(msgs) == 2 and msgs[0]["role"] == "system" and msgs[1]["role"] == "user",
   "the brain gets one system prompt and one line of context", str(len(msgs)))
ok("Nobody has asked you anything" in msgs[1]["content"],
   "which says plainly that nobody asked", msgs[1]["content"][:60])
ok("90 seconds" in msgs[1]["content"] and "1280 by 720" in msgs[1]["content"],
   "how long the screen has been still, and how big the frame is",
   msgs[1]["content"][:160])

# The proof of what was sent, reported as sizes rather than as content.
ok(body["saw"]["bytes"] == len(FRAME) and body["saw"]["mediaType"] == "image/jpeg",
   "the reply reports the frame as a byte count and a media type", json.dumps(body["saw"]))
ok(not any(isinstance(v, str) and len(v) > 40 for v in body["saw"].values()),
   "and nothing in it is long enough to be a picture", json.dumps(body["saw"]))

# ================================================== 9. what the nudge is for

head("the prompt, and the sentences it forbids")

prompt = server.STUCK_PROMPT
ok(len(prompt) > 800, "there is a standing prompt for the nudge", str(len(prompt)))
ok("did not watch" in prompt.lower() or "You did not watch them" in prompt,
   "it says out loud that the model did not watch anybody")
ok("thumbnail" in prompt.lower(),
   "and that the stillness was measured on the man's own machine")
for banned in ("take a break", "you seem stuck", "you seem to be stuck"):
    ok(banned in prompt.lower(),
       "the prompt forbids \"%s\" by name" % banned)
ok("notes" in prompt.lower(),
   "and says the notes are not in front of it")
ok(re.search(r"nothing useful", prompt, re.I) is not None,
   "with permission to say there is nothing useful to say")

# Every line this organ can say, and not one of them is written by a model.
ok(sorted(server.STUCK_LINES) ==
   ["cooldown", "hushed", "mismatch", "moving", "noframe", "stale", "tiny"],
   "the refusals are a fixed table of seven sentences", str(sorted(server.STUCK_LINES)))
for key, line in server.STUCK_LINES.items():
    ok("{" not in line.replace("{detail}", "").replace("{leftS}", "")
       .replace("{stillS}", ""),
       "the %s line has no unexpected placeholder in it" % key, line)

# ============================================ 10. the face, and the chip

head("a face on the desktop, so you always know")

ok("documentPictureInPicture.requestWindow" in watch_js,
   "the face asks for a Document Picture-in-Picture window")
ok("disallowReturnToOpener: true" in watch_js,
   "with no button back into this tab: it is a card, not a window to work in")
ok("win.moveTo(" in watch_js and "availWidth" in watch_js,
   "and it is aimed at the top-right of the real desktop")
ok("if (watchOn) stopWatch('face');" in watch_js,
   "closing the face stops the watch - a watch with its face shut is the thing "
   "this is for")
ok("const FACE_MARKUP" in watch_js and watch_js.count("FACE_MARKUP") >= 3,
   "one markup serves both homes", str(watch_js.count("FACE_MARKUP")))
ok("facePinWanted = true;" in watch_js and "pointerdown" in watch_js,
   "a pin refused for want of a gesture is retried on the next click")
ok("nopin" in watch_js and "will not let my face off the" in watch_js,
   "and if it never lands, the page says so rather than pretending")

# The chip. It must not claim a frame count it has not sent.
ok("'watching · ' + (watchNudges" in watch_js,
   "the chip counts the frames it has sent rather than claiming a number")
ok("no frame sent" in watch_js,
   "and says \"no frame sent\" for as long as that is true")

# ======================================= 11. the honest end of the watch

head("when it stops, and whether it says so")

stop = watch_js.split("function stopWatch(reason)", 1)
stop_body = stop[1].split("\n  /* THE TICK", 1)[0] if len(stop) == 2 else ""
ok("clearInterval(watchTimer)" in stop_body,
   "stopping clears the five-second timer")
ok("closeFace();" in stop_body, "and takes the face down with it")
ok("reason === 'said' || reason === 'chip' || reason === 'face'" in stop_body,
   "a man changing his mind gets a pleasantry; a share that died gets the truth")
ok("if (was && watchOn) stopWatch('ended');" in page_source,
   "and a share ended from Chrome's own bar stops the watch too")
ok("if (mine && reason !== 'ended' && sharing()) endShare();" in stop_body,
   "a share the watch opened goes out with the watch")
ok("watchOpenedShare = !had;" in watch_js,
   "and one that was already running is left alone: it is not the watch's to close")
ok("stopWatch('blind')" in watch_js,
   "a live track producing no picture stops it rather than watching nothing")

print("\n  %d checks, %d failed\n" % (checks, len(failures)))
if failures:
    for claim in failures:
        print("    FAILED: %s" % claim)
    print("")
try:
    os.remove(focus.LEDGER_PATH)
except OSError:
    pass
try:
    os.rmdir(_ledger_dir)
except OSError:
    pass
sys.exit(min(len(failures), 120))
