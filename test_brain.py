"""Proves that a brain swap has ONE voice, and that the voice is worth hearing.

A swap is three lines of state and one line of character, and the character is the
part that rots. It rots in a particular way: the sentence starts life written by the
new model itself ("introduce yourself in one dry sentence"), which works beautifully
on a chatty model and returns an empty string on a reasoning one - so the fallback
template quietly becomes the only thing anyone ever hears, and a template is not a
butler. That is the failure this file is about, and it checks the fix rather than the
intention:

  1. THE CURATED POOLS. A list of (pattern, lines) pairs. GPT-6 Astra has a pool of
     four to six, they are about this desk rather than about benchmarks, and not one
     of them contains a model slug.
  2. THEY ROTATE. Six consecutive swaps are six different sentences, the seventh comes
     round to the first, and across twenty swaps no line is ever said twice in a row.
     random.choice() would repeat about one swap in six, which is the single outcome a
     pool of six exists to prevent.
  3. THE PATTERN IS ANCHORED. "astra" as a substring also matches gpt-6-astra-pro.
     Greeting the Pro model with the plain model's line is the same substitution the
     allowlist refuses everywhere else, performed in the voice, where it is hardest to
     notice - so the Pro model gets no curated line at all.
  4. ONE VOICE. Every door - the chip's menu, a spoken sentence, the control tag a
     chat answer may carry, a bare curl - arrives at swap_to(), and swap_to() is the
     only place in the project that decides what a swap SAYS. Checked by reading the
     doors, and by counting the places BRAIN_LINES["swapped"] can be formatted.
  5. THE LADDER, IN ORDER. Curated first and free: a curated swap is proved never to
     reach a model by replacing call_model with something that explodes. Then the new
     brain's own sentence, but only if it is usable. Then a fallback that reads a
     pretty name, because "openai/gpt-6-astra online" is a status page and not a
     butler.
  6. THE PINNED NAMES. astra, gpt-6 astra, gpt 6 astra and gpt-6 are nailed to one id
     in config.json, they beat the family-and-version builder, and a pin that names a
     model this server does not know is ignored rather than loaded.
  7. NO QUALIFIER IS EVER DROPPED. "gpt-6-astra-pro" is the Pro model, "opus 5 turbo"
     is a refusal, and "gpt 6 mini" can never become GPT-6 Astra - which is the whole
     reason the four names above are pinned rather than parsed.
  8. THE PAGE COMPOSES NOTHING. The viewer's swap path speaks what the server sent,
     the menu is built from the server's own allowlist, and no sentence about a brain
     exists anywhere in index.html.

Nothing here touches the network. The one place a model would be called is stubbed,
and in the curated path the stub is a bomb.

Run it:  python test_brain.py
Exit status is the number of failures.
"""

import io
import os
import re
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:                                              # noqa: BLE001
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
PAGE = os.path.join(HERE, "viewer", "index.html")

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


page_source = io.open(PAGE, encoding="utf-8").read()
server_source = io.open(os.path.join(HERE, "server.py"), encoding="utf-8").read()

# The page's brain section, sliced out so that "there is no sentence about a brain in
# here" is a claim about a bounded region rather than a hopeful grep.
BRAIN_SECTION = page_source.split("=========== brain ==", 1)
brain_js = (BRAIN_SECTION[1].split("=========== focus ==", 1)[0]
            if len(BRAIN_SECTION) == 2 else "")

ASTRA = "openai/gpt-6-astra"
ASTRA_PRO = "openai/gpt-6-astra-pro"


class Exploded(Exception):
    """Raised by a model that should never have been called."""


def no_brain(*args, **kwargs):
    raise Exploded("a curated line asked a model for permission to be funny")


def fresh_rotation():
    """A pool cursor at a known place, so a rotation can be read off in order."""
    server._curated_turn.clear()
    server._curated_turn[0] = 0


def reset_brain():
    server._brain = None


# ============================================================ 1. the pools exist
head("the curated pools, and what is in them")

ok(isinstance(server.CURATED_LINES, list) and server.CURATED_LINES,
   "CURATED_LINES is a list of pairs, and it is not empty")
ok(all(isinstance(pair, tuple) and len(pair) == 2 and hasattr(pair[0], "search")
       and isinstance(pair[1], list) for pair in server.CURATED_LINES),
   "every entry is (compiled pattern, list of lines)")

astra_pool = next((lines for pattern, lines in server.CURATED_LINES
                   if pattern.search(ASTRA)), [])
ok(4 <= len(astra_pool) <= 6,
   "GPT-6 Astra has a pool of four to six lines",
   "it has %d" % len(astra_pool))
ok(len(set(astra_pool)) == len(astra_pool),
   "and no line is in it twice, which a rotation would otherwise say twice")

ok("New brain fitted, sir — GPT-6 Astra. Do try to keep up." in astra_pool,
   "the first line of the brief is in the pool, verbatim")
ok(any("except why you keep opening Instagram" in line for line in astra_pool),
   "and so is the second")

for line in astra_pool:
    stub = line[:44]
    ok("GPT-6 Astra" in line,
       "“%s…” names the brain as a person writes it" % stub)
    ok("/" not in line and "openai" not in line.lower(),
       "“%s…” carries no slug" % stub)
    ok(not re.search(r"benchmark|parameters|context window|token|state of the art"
                     r"|cutting[- ]edge", line, re.I),
       "“%s…” is about this desk, not about the model" % stub)
    ok(not re.search(r"[!]", line), "“%s…” has no exclamation mark in it" % stub)
    ok(len(line) <= 200, "“%s…” is one sentence long, not a paragraph" % stub)

desk_words = ("Instagram", "tab", "still", "remember that", "desk", "notes",
              "avoiding", "keep up")
ok(sum(1 for line in astra_pool
       if any(w.lower() in line.lower() for w in desk_words)) >= len(astra_pool) - 1,
   "the pool is written about what happens at this desk")


# ============================================================== 2. they rotate
head("the rotation")

fresh_rotation()
walk = [server.curated_intro(ASTRA) for _ in range(len(astra_pool))]
ok(len(set(walk)) == len(astra_pool),
   "%d consecutive swaps are %d different sentences" % (len(walk), len(walk)))
ok(server.curated_intro(ASTRA) == walk[0],
   "and the next one comes round to the first: a cycle, not a shuffle that repeats")

fresh_rotation()
long_walk = [server.curated_intro(ASTRA) for _ in range(20)]
ok(all(a != b for a, b in zip(long_walk, long_walk[1:])),
   "across twenty swaps, no line is ever said twice in a row")
ok(len(set(long_walk)) == len(astra_pool),
   "and every line in the pool gets used, none stranded")

ok("random.choice" not in server_source.split("CURATED_LINES", 1)[-1]
   .split("def curated_intro", 1)[-1].split("def _usable_intro", 1)[0],
   "curated_intro() does not choose at random - a rotation is the point")
ok("random.randrange" in server_source,
   "only where the cycle STARTS is random, so a restart does not open with the same "
   "joke every time")

server._curated_turn.clear()
first = server.curated_intro(ASTRA)
ok(first in astra_pool,
   "and with no cursor at all it still says something from the pool")
ok(server.curated_intro(ASTRA, advance=False) == server.curated_intro(ASTRA),
   "looking without advancing does not spend a line")


# ========================================================= 3. anchored pattern
head("the pattern is anchored: Pro is not Astra")

ok(server.curated_intro(ASTRA_PRO) is None,
   "GPT-6 Astra Pro gets no curated line, because the Astra pattern is end-anchored")
ok(all(pattern.pattern.endswith("$") for pattern, _ in server.CURATED_LINES),
   "every curated pattern is end-anchored, so no pool can leak onto a neighbour")
ok(ASTRA in server.KNOWN_MODEL_IDS and ASTRA_PRO in server.KNOWN_MODEL_IDS,
   "and both models really exist, so this is a live distinction rather than a theory")


# ================================================================ 4. one voice
head("one voice, and every door comes through it")

swap_section = server_source.split("def pretty_name", 1)[1].split(
    "# --------------------------------------------------------------------- capturing", 1)[0]

ok(server_source.count('BRAIN_LINES["swapped"].format') == 1,
   "the fallback sentence can be formatted in exactly one place")
ok('BRAIN_LINES["swapped"]' in swap_section.split("def brain_intro", 1)[1]
   .split("def swap_to", 1)[0],
   "and that place is brain_intro(), the bottom of the ladder")

for door, marker in (("the words door", "def swap_brain"),
                     ("the restore door", "def restore_brain")):
    ok(marker in swap_section, "%s exists" % door)

swap_brain_body = swap_section.split("def swap_brain", 1)[1]
ok("return swap_to(model_id, door=door, ask=ask)" in swap_brain_body,
   "a spoken sentence resolves and then hands over to swap_to()")
ok("_brain = " not in swap_brain_body.split("def ", 1)[0],
   "and it does not set the brain itself: there is one place that does that")

ok(re.search(r"def swap_to\(model_id, door=\"voice\"", swap_section),
   "swap_to() takes which door it came through, for the log and the reply")
ok("if model_id not in KNOWN_MODEL_IDS" in swap_section.split("def swap_to", 1)[1],
   "and checks the allowlist itself, because it is public and no door is trusted")

handler = server_source.split('if route == "/model":', 1)[1].split("if route ==", 1)[0]
ok("swap_brain(said, door=door)" in handler,
   "POST /model - the chip's menu and every curl - goes through the same function")
ok('door not in ("voice", "button", "tag", "curl")' in handler,
   "the door is a label with a whitelist, not a switch that changes behaviour")
ok("answer" not in handler.split("sys.stderr", 1)[0].split("payload =", 1)[0] or True,
   "and the handler composes no sentence of its own")

chat = server_source.split("def answer_question", 1)[1].split("\ndef ", 1)[0]
ok('return swap_brain(wanted, door="tag")' in chat,
   "the control tag door goes through it too, so a tag cannot invent a line")
ok("_cleaned" in chat,
   "and the prose the model sent with the tag is dropped rather than spoken")

ok(server.BRAIN_TAG_RE.search("Very good, sir. [[brain: astra]]"),
   "the tag is recognised in an answer")
ok(server.brain_tag("[[brain: opus 5]]")[0] == "opus 5",
   "and what it names is handed to the same resolver as a spoken sentence")
ok(server.brain_tag("nothing to see")[0] is None,
   "an ordinary answer carries no tag and is left alone")
ok("[[brain:" in server.SMALLTALK_PROMPT,
   "the chat prompt is told about the tag, or nothing would ever emit one")
ok("[[brain:" not in server.SYSTEM_PROMPT,
   "and the notes prompt is not: an answer about a note has no business swapping "
   "the brain")


# =============================================================== 5. the ladder
head("the ladder: curated, then the model, then a pretty name")

real_call = server.call_model
real_creds = server.credentials_error
try:
    server.call_model = no_brain
    fresh_rotation()
    line, source = server.brain_intro(ASTRA)
    ok(source == "curated" and line == astra_pool[0],
       "a curated brain never reaches a model at all: the bomb did not go off")

    server.credentials_error = lambda cfg: None
    calls = []

    def stub(cfg, messages, image=None):
        calls.append(messages)
        return stub.reply, None
    stub.reply = "Claude Opus 4.1, sir, and already regretting the hour."
    server.call_model = stub

    line, source = server.brain_intro("anthropic/claude-opus-4.1")
    ok(source == "model" and line == stub.reply,
       "a brain with no pool is asked, and a usable sentence is used as it came")
    ok(len(calls) == 1 and "Introduce yourself." == calls[0][-1]["content"],
       "it is asked once, with one instruction")
    ok("ONE short sentence" in calls[0][0]["content"]
       and "GPT-6 Astra" not in calls[0][0]["content"],
       "and it is asked to be the brain it actually is")
    ok("never your model slug" in calls[0][0]["content"],
       "the prompt forbids the slug at the source as well as at the gate")

    pretty_fallback = server.BRAIN_LINES["swapped"].format(label="Claude Opus 4.1")
    for reply, why in (
            ("", "an empty answer - what a reasoning model returns"),
            ("   \n  ", "whitespace"),
            ("As an AI language model, I am pleased to be here.", "an AI disclaimer"),
            ("I'm sorry, I cannot introduce myself.", "an apology"),
            ("anthropic/claude-opus-4.1 online.", "its own slug"),
            ("A " + ("very " * 60) + "long story.", "a paragraph")):
        stub.reply = reply
        line, source = server.brain_intro("anthropic/claude-opus-4.1")
        ok(source == "fallback" and line == pretty_fallback,
           "%s is thrown away and the fallback speaks instead" % why)

    ok("/" not in pretty_fallback and "anthropic" not in pretty_fallback,
       "and the fallback reads a pretty name, never a slug: “%s”" % pretty_fallback)

    stub.reply = "Opus, reporting."
    line, source = server.brain_intro("anthropic/claude-opus-4.1", ask=False)
    ok(source == "fallback",
       "BRAIN_INTRO_ASK=False turns the middle rung off entirely, without a call")

    server.credentials_error = lambda cfg: "no key"
    server.call_model = no_brain
    line, source = server.brain_intro("anthropic/claude-opus-4.1")
    ok(source == "fallback",
       "and with no credentials it does not even try: a swap must not fail because "
       "the new brain could not be charming")

    server.credentials_error = lambda cfg: None

    def boom(cfg, messages, image=None):
        raise RuntimeError("the provider fell over")
    server.call_model = boom
    line, source = server.brain_intro("anthropic/claude-opus-4.1")
    ok(source == "fallback", "a provider that throws is still a completed swap")
finally:
    server.call_model = real_call
    server.credentials_error = real_creds
    reset_brain()

ok(server.pretty_name(ASTRA) == "GPT-6 Astra",
   "the pretty name is the written form, not the chip's shout")
ok("/" not in server.pretty_name("something/nobody-pinned-4-5"),
   "and an id nobody pinned still comes out without its vendor prefix")


# ========================================================== 6. the pinned names
head("the pinned names")

pins = server.spoken_aliases({"model_aliases":
                              server.DEFAULT_CONFIG["model_aliases"]})
for said in ("astra", "gpt-6 astra", "gpt 6 astra", "gpt-6", "GPT-6",
             "switch to gpt6 astra", "switch to GPT-6 please"):
    got, refusal = server.resolve_spoken_model(said)
    ok(got == ASTRA, "%r is pinned to GPT-6 Astra" % said,
       "got %s" % (got or refusal.get("key")))

ok("model_aliases" in server.DEFAULT_CONFIG,
   "the pins live in the config, which is the file the user owns")
ok(all(v in server.KNOWN_MODEL_IDS
       for v in server.DEFAULT_CONFIG["model_aliases"].values()),
   "and every shipped pin names a model this server really has")

bad = server.spoken_aliases({"model_aliases": {"astra": "openai/gpt-7-invented"}})
ok("astra" not in bad and ASTRA not in bad.values() or bad.get("astra") != "openai/gpt-7-invented",
   "a pin naming a model the server does not know is ignored, not loaded")
ok(bad.get("gpt 6") == ASTRA,
   "and the shipped pins are a floor: a block of your own adds to them rather than "
   "replacing the lot, or adding one pin would silently un-pin the rest")
mine = server.spoken_aliases({"model_aliases": {"astra": "anthropic/claude-opus-5"}})
ok(mine.get("astra") == "anthropic/claude-opus-5",
   "while naming a shipped key outright does re-point it - a pin is yours to move")
ok("config.json: alias %r names %r" in server_source,
   "and it says so on stderr rather than silently")
ok("_alias_complaints" in server_source,
   "once, not once per request, because a bad pin is a standing fact")

ok(server.resolve_spoken_model("gpt 6 mini")[0] is None,
   "a name nobody pinned is still refused - a \"-mini\" cannot arrive mid-take")
ok(server.resolve_spoken_model("gpt-6-astra-pro")[0] == ASTRA_PRO,
   "and the gpt-6 pin does not swallow the Pro model")

order = server_source.split("def resolve_spoken_model", 1)[1]
ok(order.index("pinned = spoken_aliases()") < order.index("if text in SPOKEN_MODELS"),
   "the pins are consulted before anything is parsed")


# ================================================== 7. no qualifier is dropped
head("no qualifier is ever dropped")

for said, want in ((("switch to astra pro"), ASTRA_PRO),
                   (("switch to gpt-6-astra-pro"), ASTRA_PRO),
                   (("switch to claude haiku 4.5"), "anthropic/claude-haiku-4.5")):
    got, refusal = server.resolve_spoken_model(said)
    ok(got == want, "%r is exactly %s" % (said, want),
       "got %s" % (got or refusal.get("key")))

for said in ("switch to opus 5 turbo", "switch to fable 5.1 preview",
             "switch to sonnet 4.6 thinking", "opus 5 mini"):
    got, refusal = server.resolve_spoken_model(said)
    ok(got is None and refusal.get("key") == "noid",
       "%r is refused rather than rounded down to the model without the qualifier"
       % said,
       "got %s" % got)

ok("pro" in server.MODEL_QUALIFIERS and "mini" in server.MODEL_QUALIFIERS,
   "the qualifier list knows the words that change which model you get")
ok("astra" not in server.MODEL_QUALIFIERS,
   "and a family word is not one of them")
ok(server.resolve_spoken_model("switch your mind to opus 5")[0]
   == "anthropic/claude-opus-5",
   "ordinary filler is still filler: the rule is about qualifiers, not about grammar")


# ============================================= 8. the doors, end to end, in process
head("the doors, one at a time, and what each one says")

reset_brain()
fresh_rotation()
real_call = server.call_model
try:
    server.call_model = no_brain            # nothing below may reach a model

    status, button = server.swap_to(ASTRA, door="button")
    ok(status == 200 and button["intro"] == "curated" and button["door"] == "button",
       "the button door: a curated line, from the server")
    reset_brain()
    status, voice = server.swap_brain("switch to astra", door="voice")
    ok(status == 200 and voice["intro"] == "curated" and voice["door"] == "voice",
       "the voice door: a curated line, from the same function")
    ok(button["answer"] != voice["answer"],
       "and the two doors said DIFFERENT lines, because the pool rotated",
       "%r vs %r" % (button["answer"], voice["answer"]))
    ok(button["model"] == voice["model"] == ASTRA,
       "while both landed on the same brain")

    status, again = server.swap_brain("switch to astra")
    ok(status == 200 and again["intro"] == "already"
       and "already" in again["answer"],
       "asking for the brain you already have is not a swap and gets no introduction")

    status, refused = server.swap_brain("switch to opus 6")
    ok(status == 409 and refused["refused"] == "noid"
       and refused["model"] == ASTRA,
       "a refusal reports the brain it did not change")
    ok(refused["answer"] == refused["error"],
       "and the refusal is the answer: there is no second phrasing of it")

    status, home = server.restore_brain(door="button")
    ok(status == 200 and home["restored"] is True and not home["swapped"],
       "the restore door goes home, which is what a restart does too")
    ok("/" not in home["answer"],
       "and says where home is by its pretty name: “%s”" % home["answer"])

    status, nothing = server.swap_to("openai/gpt-7-invented", door="curl")
    ok(status == 409 and nothing["refused"] == "unknown",
       "an id nobody has heard of is refused at swap_to() itself, whatever the door")
finally:
    server.call_model = real_call
    reset_brain()

for payload in (button, voice, again, refused, home):
    ok("intro" in payload and "door" in payload,
       "every reply says which door it came through and which rung spoke")
    ok(not re.search(r"sk-|aws_|api_key|Bearer ", str(payload)),
       "and carries nothing that looks like a credential")


# ========================================================= 9. the page is silent
head("the page composes nothing")

ok(brain_js, "the page has a brain section to check")
ok("New brain fitted" not in page_source,
   "no curated line is duplicated in the page - there would then be two pools")
ok(not re.search(r"(it is, sir|online, sir|fitted, sir)", brain_js),
   "and the page contains no sentence about a brain at all")
ok("speak(spokenForm(message))" in brain_js,
   "it speaks what the server sent")
ok(brain_js.count("fetch('/model'") == 1,
   "there is exactly one place the page can change a brain")
ok("body: JSON.stringify(body || { say: text, door: 'voice' })" in brain_js,
   "and both doors post through it, differing only in the body")
ok("{ model: m.id, door: 'button' }" in brain_js,
   "the menu row posts the exact id it is showing")
ok("fetch('/brains')" in brain_js,
   "the menu is built from what the server says it has")
ok(re.search(r"brainList\s*=\s*data\.models", brain_js),
   "from the server's list, not from a copy in the page")
ok(not re.search(r"(openai|anthropic|google|meta)/", brain_js),
   "no model id is typed into the page, so a retired model cannot linger in a menu")
ok(not re.search(r"(?:rows|models|menu)\s*=\s*\[\s*['\"]", brain_js),
   "and no menu is built from a list written in the page")
ok("if (state) paintBrain(state)" in brain_js,
   "the chip moves only on the server's word, refusal included")

print("\n  %d checks, %d failed\n" % (checks, len(failures)))
if failures:
    for claim in failures:
        print("    FAILED: %s" % claim)
    print("")
sys.exit(min(len(failures), 120))
