"""§45, THE FOUR MODES - every rule that can be proved without a model or a network.

WHAT THIS FILE IS ABOUT. A mode is a word in a file and a paragraph in front of the brain, so
almost nothing about it is interesting - and the three things that ARE interesting are each a
bug that would have shipped silently:

  1. THE COLLISION. server.STUDY_NOW_RE reads "(study|research) <topic>" and "mode" is a
     perfectly good topic as far as it is concerned, so "study mode" matches it with
     topic="mode". Read in the wrong order, the sentence asking for Study Mode would instead
     spend ninety seconds of Groq researching the word "mode", write a note about it, and
     answer "Studying mode now, sir" - a reply that looks entirely normal. This file puts the
     sentence through the WHOLE funnel (protected_answer) rather than through either regex, so
     the assertion is about the order the server really reads them in, and it holds a bomb in
     scholar.MANAGER.request to prove no tick was queued.
  2. NORMAL IS A TRUE BASELINE. persona_prompt() in Normal Mode must return byte-for-byte what
     it returned before §45 existed - not "nearly", not "the same except a blank line". That is
     the whole claim of Normal Mode as a reset target, and it is asserted here against the
     persona text rebuilt independently rather than against persona_prompt() itself.
  3. THE DOORMAN LEAVES NO TRACE. A refused switch must leave the file exactly as it was. A
     refusal that said no and wrote the word anyway would be a refusal in prose only.

And two more that are cheap to prove and would be embarrassing to get wrong: that no mode
changes the capabilities manifest by a single character (v1 gates NOTHING), and that the
twelve control sentences in mode._MODE_NOT are not mode switches - "what is work mode" is a
question, and answering it by silently becoming terse is the kind of thing nobody reports as a
bug because they cannot tell it happened.

NOTHING HERE TOUCHES THE NETWORK OR A MODEL. The mode file is redirected into a temp
directory before mode is imported, the Scholar's shelf is redirected to a temp folder with
notes this file writes itself, and the one place a study tick could start is a bomb.

Run it:  python test_mode.py
Exit status is the number of failures.
"""
import io
import json
import os
import re
import shutil
import sys
import tempfile
import time

sys.dont_write_bytecode = True
# The one shared final line, so run_tests.py reads a result rather than
# guessing at this suite's private dialect. See testkit.py.
import testkit
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:                                              # noqa: BLE001
    pass

# THE REDIRECT COMES BEFORE THE IMPORT, which is test_revenue.py's own arrangement and it is
# load-bearing for the same reason: mode.STATE_PATH is read at import time, so a redirect after
# `import mode` would write the real mode-state.json and leave this machine in whatever mode
# the last assertion happened to set.
TMP = tempfile.mkdtemp(prefix="mode-test-")
os.environ["TRONE_MODE_STATE"] = os.path.join(TMP, "mode-state.json")

import mode                                                    # noqa: E402
import scholar                                                 # noqa: E402
import server                                                  # noqa: E402

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


class Exploded(Exception):
    """Raised by something that should never have been reached."""


page_source = io.open(os.path.join(HERE, "viewer", "index.html"), encoding="utf-8").read()
server_source = io.open(os.path.join(HERE, "server.py"), encoding="utf-8").read()


# ============================================================ 1. THE SENTENCES

head("1. the sentences, the controls that must not fire, and the recap's two directions")

SET = [("work mode", "work"), ("go to work mode", "work"), ("switch to work mode", "work"),
       ("work mode mein jao", "work"), ("work mode on karo", "work"),
       ("work mode chalu karo", "work"), ("kaam mode mein jao", "work"),
       ("focus mode", "work"), ("turn on work mode", "work"), ("be in work mode", "work"),
       ("play mode", "play"), ("play mode mein jao", "play"), ("play mode on karo", "play"),
       ("play mode chalu karo", "play"), ("masti mode mein jao", "play"),
       ("chill mode", "play"), ("switch to play mode", "play"),
       ("study mode", "study"), ("study mode mein jao", "study"),
       ("study mode on karo", "study"), ("study mode chalu karo", "study"),
       ("padhai mode mein jao", "study"), ("go into study mode", "study"),
       ("normal mode", "normal"), ("normal mode mein jao", "normal"),
       ("normal mode mein wapas aao", "normal"), ("reset mode", "normal"),
       ("mode off", "normal"), ("exit work mode", "normal"), ("stop study mode", "normal"),
       ("turn off play mode", "normal"), ("wapas normal mein aao", "normal")]
missed = [(s, mode.parse_request(s)) for s, want in SET
          if (mode.parse_request(s) or {}).get("mode") != want]
ok(not missed, "all %d trigger phrases parse to the right mode" % len(SET), repr(missed[:4]))

false_fires = [(s, mode.parse_request(s)) for s in mode._MODE_NOT
               if mode.parse_request(s) is not None]
ok(not false_fires, "none of the %d control sentences is a mode command" % len(mode._MODE_NOT),
   repr(false_fires[:4]))

# THE RECAP'S TWO DIRECTIONS, and the second one is the bug this block was added for.
#
# A question about the SESSION is the recap: it asks what is on the shelf, and the shelf is
# what study_report() reads. A question about a TOPIC is not, however similarly it is worded
# - it must fall through to the notes search, which can actually go and look the topic up.
# The old pattern ended in `.{0,30}`, which took either, so "what did you study about
# physics" was answered with the four syllabus notes on the shelf and not one word about
# physics. Both lists are asserted, because fixing the leak by narrowing too far would be
# the same bug facing the other way - the recap simply never firing.
RECAP_YES = ("what did you study", "what did you study today", "what did you learn",
             "what did you learn today", "what did you just study",
             "what have you learned", "what have you been studying",
             "what did you learn so far", "what have you learned recently",
             "what did you study abhi tak", "study recap", "the study summary")
recap_missed = [s for s in RECAP_YES
                if (mode.parse_request(s) or {}).get("action") != "update"]
ok(not recap_missed, "all %d session questions are the recap" % len(RECAP_YES),
   repr(recap_missed))

# THE ASYMMETRY THAT LET THE FIRST ONE THROUGH, kept as its own assertion because it is the
# kind of thing that comes back: the two verb arms were written separately, so `stud*` took
# "did" or "have" and `learn*` took only "have". "What did you learn" is not a rarer sentence
# than "what did you study" and must not be a rarer match.
ok((mode.parse_request("what did you learn") or {}).get("action") == "update" and
   (mode.parse_request("what did you study") or {}).get("action") == "update" and
   (mode.parse_request("what have you learned") or {}).get("action") == "update" and
   (mode.parse_request("what have you studied") or {}).get("action") == "update",
   "did/have and study/learn are symmetric - all four pairings are the recap")

ok(mode.parse_request("study update") == {"action": "update"}, "\"study update\" is the recap")
ok(mode.parse_request("padhai ka update") == {"action": "update"},
   "\"padhai ka update\" is the recap")
ok((mode.parse_request("which mode are you in") or {}).get("action") == "ask",
   "\"which mode are you in\" is a reading, not a switch")
ok(mode.parse_request("") is None and mode.parse_request(None) is None,
   "an empty sentence is not a mode command")


# ============================================================ 2. THE FLAG ON DISK

head("2. the flag on disk")

ok(mode.current() == "normal", "with no file at all the mode is normal")
ok(mode.read_state() == {"mode": "normal", "since": "", "by": ""},
   "and read_state() answers the full shape, not a bare word", repr(mode.read_state()))

mode.switch("work", by="chat")
ok(mode.current() == "work", "a switch is visible at once")
ok(os.path.exists(mode.STATE_PATH), "and it reached the disk")
ok(not os.path.exists(mode.STATE_PATH + ".tmp"), "the .tmp was replaced, not left behind")
ok(not os.path.exists(mode.STATE_PATH + ".lock"), "and the lock was released")
with open(mode.STATE_PATH, encoding="utf-8") as fh:
    on_disk = json.load(fh)
ok(sorted(on_disk) == ["by", "mode", "since"] and on_disk["by"] == "chat",
   "the file holds {mode, since, by} and nothing else", repr(on_disk))

# A FRESH READ, not the one in memory - there is no "one in memory", which is the point.
ok(mode.read_state()["mode"] == "work", "the mode survives a re-read (it would a restart)")

mode.switch("fiesta")
ok(mode.current() == "normal", "a mode nobody has heard of is written as normal")

with open(mode.STATE_PATH, "w", encoding="utf-8") as fh:
    fh.write("{this is not json")
ok(mode.current() == "normal", "a corrupt file reads as normal and does not raise")
with open(mode.STATE_PATH, "w", encoding="utf-8") as fh:
    json.dump({"mode": "play", "since": "2026-10-19 10:00:00", "by": "voice"}, fh)
ok(mode.current() == "play", "and a good file written by someone else is read")
with open(mode.STATE_PATH, "w", encoding="utf-8") as fh:
    json.dump({"mode": "WORK"}, fh)
ok(mode.current() == "work", "the word is read case-insensitively")
with open(mode.STATE_PATH, "w", encoding="utf-8") as fh:
    json.dump(["play"], fh)
ok(mode.current() == "normal", "a file holding a list, not an object, reads as normal")


# ============================================================ 3. WHAT THE BRAIN READS

head("3. what the brain reads - and normal is byte-identical")

mode.switch("normal")
# THE BASELINE, REBUILT INDEPENDENTLY. This is the persona block exactly as persona_prompt()
# composed it before §45, assembled here from server.persona() so that the assertion is
# "persona_prompt() adds nothing in Normal Mode" rather than "persona_prompt() equals itself".
who = server.persona(None)
BASELINE = (
    "WHO YOU ARE\n"
    "- Your name is %(assistant)s. You are the personal assistant of %(formal)s, "
    "and you have served him long enough to call him %(call)s.\n"
    "- Asked who or what you are, say it in your own voice, beginning from this: "
    "\"%(intro)s\" Never answer that question with a search, never describe "
    "yourself as a language model, and never give any other name - there is no "
    "other name.\n"
    "- Asked who HE is, or what his name is, or whether you know him: you do. He is "
    "%(formal)s, and you call him %(call)s.\n"
    "- HOW YOU ADDRESS HIM. In warm speech - an answer, an acknowledgment, a "
    "remark - call him %(call)s. Keep \"sir\" for the formal moments: asking his "
    "permission, declining something, calling him back to his work. Never both in "
    "one sentence, and never in every sentence.\n"
    % {"assistant": who["assistant"], "formal": who["boss_formal"],
       "call": who["boss_call"], "intro": who["self_intro"]})

ok(server.persona_prompt(None) == BASELINE,
   "NORMAL MODE: persona_prompt() is byte-for-byte what it was before §45",
   "len %d vs %d" % (len(server.persona_prompt(None)), len(BASELINE)))
ok(mode.prompt_block("normal") == "", "normal's block is the empty string, not a paragraph")

manifest_normal = server.capabilities_manifest(None)
for name in ("work", "play", "study"):
    mode.switch(name)
    got = server.persona_prompt(None)
    ok(got.startswith(BASELINE), "%s MODE: the persona is untouched above the block" % name)
    ok(got != BASELINE and mode.prompt_block(name) in got,
       "%s MODE: and the block is appended below it" % name)
    ok(len(mode.prompt_block(name)) < 600,
       "%s MODE: the block is short (%d chars, paid on every call)"
       % (name, len(mode.prompt_block(name))))
    # V1 GATES NOTHING, and this is the assertion rather than the intention: the manifest is
    # what tells the brain which hands and senses exist, and not one character of it moves.
    ok(server.capabilities_manifest(None) == manifest_normal,
       "%s MODE: the capabilities manifest is identical - nothing is gated" % name)

mode.switch("normal")
ok(server.persona_prompt(None) == BASELINE, "and back to normal restores it exactly")

# THE ONE FUNNEL. persona_prompt() is the only place in server.py that reads a mode block, so
# a ninth call site added tomorrow gets the mode for free and cannot be forgotten.
# COUNTED AS THE CALL AND NOT AS THE PHRASE, because persona_prompt()'s own docstring names
# the function - a count of "mode.prompt_block(" reads 2 and says nothing about the code.
ok(server_source.count("block = mode.prompt_block()") == 1,
   "mode.prompt_block() is CALLED in exactly one place in server.py",
   "found %d" % server_source.count("block = mode.prompt_block()"))
ok("brain_preamble" in server_source and
   server.brain_preamble(None).startswith(server.persona_prompt(None)),
   "and brain_preamble() carries it through to all eight call sites")


# ============================================================ 4. THE COLLISION

head("4. \"study mode\" is a mode, not a study of the word \"mode\"")

# THE PROOF IS A BOMB IN THE SCHOLAR'S DOOR. If the funnel reads §30 before §45, this request()
# is reached and the assertion fails loudly rather than by a subtle difference in a sentence.
real_request = scholar.MANAGER.request


def bomb(*a, **kw):
    raise Exploded("scholar.MANAGER.request was reached by a mode sentence")


scholar.MANAGER.request = bomb
mode.switch("normal")
try:
    for phrase in ("study mode", "study mode mein jao", "study mode chalu karo",
                   "padhai mode mein jao", "exit study mode", "stop study mode"):
        mode.switch("normal")
        try:
            name, said = server.protected_answer(phrase)
            blew = ""
        except Exploded as exc:
            name, said, blew = None, None, str(exc)
        want = "normal" if phrase.split()[0] in ("exit", "stop") else "study"
        ok(not blew and name == "mode" and said and said.get("mode") == want,
           "%-24r -> the mode route, mode now %s" % (phrase, want),
           blew or "route %r, payload %r" % (name, said))
    # AND THE SCHOLAR'S OWN SENTENCE STILL REACHES THE SCHOLAR. The section above it must not
    # have eaten the branch it was placed in front of - which is the other half of the order,
    # and the half a careless fix to the first half would break.
    for phrase in ("study micro-saas now", "research transformer attention",
                   "go study something new"):
        try:
            server.protected_answer(phrase)
            reached = False
        except Exploded:
            reached = True
        ok(reached, "%-34r still reaches the Scholar" % phrase)

    # AND A TOPIC-SCOPED QUESTION GOES TO NEITHER OF THEM, which is the narrow channel this
    # sentence has to thread and the reason it is proved through the funnel rather than
    # through the regex. "What did you study about physics" must not be the shelf recap,
    # because the shelf cannot answer it - and it must not become a STUDY either, because
    # ninety seconds of Groq researching "about physics" is the expensive bug §45 was built
    # to prevent, now arriving through the door the repair opened. It belongs to the brain,
    # so the right outcome is the quiet one: no bomb, and no route claimed here at all.
    for phrase in ("what did you study about physics", "what did you learn about physics",
                   "what have you learned about derivatives",
                   "what did you study on rate limiting"):
        try:
            name, said = server.protected_answer(phrase)
            blew = ""
        except Exploded as exc:
            name, said, blew = None, None, str(exc)
        ok(not blew and name is None,
           "%-42r is the brain's, not the shelf's or the Scholar's" % phrase,
           blew or "route %r" % (name,))
finally:
    scholar.MANAGER.request = real_request

# AND THE ORDER IS A FACT ABOUT THE FILE, not only about these sentences: §45's branch is above
# §30's in server.py, so a later edit that moves one of them fails here rather than in the wild.
ok(server_source.index("§45: THE FOUR MODES") < server_source.index("§30: THE CURRICULUM"),
   "§45's branch stands above §30's in server.py")


# ============================================================ 5. THE FUNNEL'S ANSWERS

head("5. the switch, the reading, and what the payload carries")

mode.switch("normal")
name, said = server.protected_answer("work mode mein jao")
ok(name == "mode" and mode.current() == "work", "a Hinglish switch sets the mode")
ok(said.get("modeChanged") is True and said.get("modeAsked") == "set" and
   said.get("mode") == "work", "and the payload says what changed", repr(said))
ok(bool(said.get("answer")) and said.get("kind") == "chat" and said.get("lookups") == 0,
   "it answers with one spoken line, no card, no lookup", repr(said.get("answer")))
ok("pending" not in said, "and leaves NOTHING pending - there is no card to confirm")
ok(said.get("protected") == "mode" and "mode" in server.UNPAID_CLASSES,
   "the route is unpaid, like the clock's")

name, said = server.protected_answer("work mode")
ok(said.get("modeChanged") is False and mode.current() == "work",
   "switching into the mode he is already in changes nothing and says so")

name, said = server.protected_answer("which mode are you in")
ok(name == "mode" and said.get("modeAsked") == "ask" and said.get("modeChanged") is False,
   "\"which mode are you in\" reads the file and sets nothing")
ok("work" in said.get("answer", "").lower(), "and names the mode out loud",
   repr(said.get("answer")))

name, said = server.protected_answer("normal mode")
ok(mode.current() == "normal" and said.get("modeChanged") is True, "the reset works")

# THE DOORMAN. A spoken sentence under somebody else's seal is refused, and the FILE IS
# UNTOUCHED - the refusal is the absence of a write, not a sentence about one.
#
# study_allowed() STANDS DOWN SILENTLY WHEN NOBODY IS ENROLLED - that is its own documented
# clause, for its own reason, and it means this test's verdict depends on ambient state this
# file does not control: a machine with no enrolled hands-voice would pass GUEST through and
# never notice the Doorman had nothing to refuse with. A test whose answer changes with
# whoever's laptop runs it is not a test of §45's gate, so a voice is ENROLLED here, the way
# the real house enrolls one, rather than borrowed from whatever is already on disk.
class _FakeVoiceprint:
    def has_hands_voice(self):
        return True

_real_voiceprint = server.voiceprint
server.voiceprint = _FakeVoiceprint()
try:
    mode.switch("study", by="chat")
    before = mode.read_state()
    name, said = server.protected_answer("work mode mein jao", spoken=True, seal="GUEST")
    ok(name == "mode" and said.get("refused") == "not-the-boss",
       "a guest's spoken switch is refused at the Scholar's doorman", repr(said))
    ok(mode.read_state() == before,
       "and the mode file is byte-identical - the refusal left no trace",
       repr(mode.read_state()))
    ok(said.get("mode") == "study" and said.get("modeChanged") is False,
       "the payload still reports the REAL mode, so the badge cannot be moved by a guest")

    name, said = server.protected_answer("work mode mein jao", spoken=True, seal="BOSS")
    ok(mode.current() == "work" and not said.get("refused"),
       "and the boss's own voice is obeyed")
finally:
    # RESTORED EVEN ON FAILURE, because every section below this one calls protected_answer()
    # too, and a fake left standing would make a later section pass or fail on a verdict that
    # was never real either.
    server.voiceprint = _real_voiceprint
mode.switch("normal")


# ===================================================== EVERY GATE THAT STANDS DOWN
#
# study_allowed() is not the only law in server.py that opens itself when nobody is
# enrolled, and the bug that made this block necessary - a GUEST sailing through on a
# machine with an empty roster, with the test cheerfully reporting a pass - is a bug
# every one of them can have. It got caught here once, by accident. So the OTHERS are
# enumerated rather than trusted, from server.py's own source, and the count is a
# claim: a fourth gate on this pattern fails this check on the day it lands, and
# whoever adds it has to come here and force it closed before their suite means
# anything.
#
# Three gates, named with what each one costs when it is wrong, because that is the
# whole reason they do not all make the same choice:
#
#   fullscreen_allowed  a bigger window. Opens on a store that will not read, too.
#   study_allowed       a mode switch, which is undone by saying so again.
#   the Hands gate      an email leaving the house. This one FAILS CLOSED on a store
#                       that will not read, and the asymmetry is deliberate.
head("5b. no law in server.py stands down without this file knowing")

server_src = io.open(os.path.join(HERE, "server.py"), encoding="utf-8").read()
STAND_DOWNS = re.findall(r"^\s*(?:if not |guarded = )voiceprint\.has_hands_voice\(\)",
                         server_src, re.M)
ok(len(STAND_DOWNS) == 3,
   "exactly three laws in server.py read has_hands_voice(), and all three are below",
   "%d found" % len(STAND_DOWNS))


class _NobodyEnrolled:
    """An empty roster - the state every one of these gates opens itself for."""

    def has_hands_voice(self):
        return False

    def seal_for(self, verdict):
        return "GUEST"


class _SomebodyEnrolled:
    def has_hands_voice(self):
        return True

    def seal_for(self, verdict):
        return "GUEST"


# BOTH DIRECTIONS, which is the point. Forcing the guard CLOSED proves the refusal is
# real; forcing it OPEN proves the stand-down is the documented clause rather than a
# gate that never worked. A test that only ever ran the second one - which is what a
# machine with an empty speaker-store silently does - proves nothing at all.
for gate, action in ((server.fullscreen_allowed, "fill the screen"),
                     (server.study_allowed, "switch the mode")):
    server.voiceprint = _SomebodyEnrolled()
    try:
        allowed, refusal = gate(True, "GUEST")
        ok(allowed is False and refusal,
           "with a voice enrolled, a GUEST may not %s - and is told so" % action,
           repr((allowed, refusal))[:120])
        allowed, _ = gate(True, "BOSS")
        ok(allowed is True, "while the boss may %s" % action)
        server.voiceprint = _NobodyEnrolled()
        allowed, _ = gate(True, "GUEST")
        ok(allowed is True,
           "and with NOBODY enrolled the law stands down for %s - documented, and proved "
           "here rather than met by accident" % action)
    finally:
        server.voiceprint = _real_voiceprint


# ============================================================ 6. STUDY UPDATE

head("6. \"study update\", read off the shelf and never from a model")

SHELF = os.path.join(TMP, "shelf")
os.makedirs(SHELF, exist_ok=True)
real_dir, scholar.STUDY_DIR = scholar.STUDY_DIR, SHELF
try:
    line = mode.study_report(boss_call="sir", days=7)
    ok("not written a study note" in line and "sir" in line,
       "an empty shelf is said out loud, not filled in", repr(line))

    def note(days_ago, topic):
        """A fixture in scholar.write_note()'s REAL shape, front matter and all.

        THE ORDER OF THOSE TWO LINES IS THE WHOLE FIXTURE. studied_today() reads the first
        2000 bytes looking for "topic: " and breaks at the first "# " - so a note with its
        heading above its front matter is reported by its TITLE and a real one by its TOPIC.
        The first draft of this fixture had them the other way round and four assertions
        below failed on title case, which is the fixture being wrong rather than the code:
        every note on the real shelf is written by write_note() and has topic: first.
        """
        when = time.localtime(time.time() - days_ago * 86400.0)
        path = os.path.join(SHELF, "%s-%s.md" % (time.strftime("%Y-%m-%d", when),
                                                 topic.replace(" ", "-")))
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("---\ntopic: %s\nsources:\n  - https://example.invalid/x\n"
                     "model: fixture\nsafety-screened: true\nwritten-by: test_mode.py\n"
                     "---\n\n# %s - auto-studied\n\n- a bullet.\n" % (topic, topic.title()))

    note(0, "rate limiting")
    note(0, "vector stores")
    note(2, "micro saas")
    line = mode.study_report(boss_call="sir", days=7)
    ok("rate limiting" in line and "vector stores" in line,
       "today's two notes are both named", repr(line))
    ok("2 days ago" in line and "micro saas" in line, "and the older one is placed in time")
    ok("3 notes" in line, "the count is the real file count", repr(line))
    ok(line.count(".") <= 4 and "\n" not in line,
       "it is ONE spoken line, in revenue.report()'s shape", repr(line))

    # THE WINDOW IS REAL: a note older than the window is not in the recap.
    note(30, "ancient history")
    ok("ancient history" not in mode.study_report(days=7),
       "a note outside the window is not in the recap")
    ok("ancient history" in mode.study_report(days=40),
       "and is in a wider one - the window is the only thing excluding it")

    # AND THROUGH THE FUNNEL, in every mode - the recap is not gated on Study Mode, because a
    # command that worked only after remembering to flip a flag is a command nobody uses.
    for name in ("normal", "work", "play", "study"):
        mode.switch(name)
        route, said = server.protected_answer("study update")
        ok(route == "mode" and said.get("modeAsked") == "update" and
           "rate limiting" in said.get("answer", ""),
           "\"study update\" is answered in %s mode" % name,
           repr(said.get("answer"))[:120])
    mode.switch("normal")
    route, said = server.protected_answer("what did you study today")
    ok(route == "mode" and said.get("modeAsked") == "update",
       "\"what did you study today\" is the recap, not a new study tick")
finally:
    scholar.STUDY_DIR = real_dir


# ============================================================ 7. THE PAGE

head("7. the badge, and the baseline it must not disturb")

ok('id="mode-badge"' in page_source, "the badge span exists")
ok('id="mode-badge" data-mode="normal" hidden' in page_source,
   "it ships HIDDEN and normal, so the status strip is unchanged at baseline")
ok("#mode-badge{" in page_source and '#mode-badge[data-mode="work"]' in page_source,
   "it has its own CSS, per mode")
ok("function modePaint(" in page_source and "modePaint(data.mode)" in page_source,
   "and it is painted from the /study poll that was already running")
ok("el.hidden = !ok" in page_source, "normal hides it rather than writing NORMAL in it")
ok(page_source.count("modePaint(") == 2,
   "painted in exactly one place, from one definition",
   "found %d references" % page_source.count("modePaint("))
# THE DECK'S OWN "WORK MODE" IS A DIFFERENT FEATURE AND IS NOT TOUCHED. focus.py is the one
# that owns it, and §45 must not have reached into it.
ok("mode.py" not in io.open(os.path.join(HERE, "focus.py"), encoding="utf-8").read() and
   "import mode" not in io.open(os.path.join(HERE, "focus.py"), encoding="utf-8").read(),
   "focus.py does not know this file exists - the deck's work mode is untouched")
ok("mode.prompt_block" not in io.open(os.path.join(HERE, "scholar.py"),
                                      encoding="utf-8").read(),
   "and scholar.py's architecture was not rewritten - §45 added no function to it")


# ============================================================ done

mode.switch("normal")
shutil.rmtree(TMP, ignore_errors=True)
testkit.summary(__file__, checks, failures)
sys.exit(min(len(failures), 120))
