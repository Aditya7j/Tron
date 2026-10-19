"""THE FOUR MODES - Work, Play, Study and Normal - and nothing else.

WHAT THIS FILE IS. One flag on disk, the sentences that set it, and the short block of
instruction each mode puts in front of the brain. It is the smallest organ in this house
and it is deliberately smaller than Revenue Mode, whose shape it borrows: there is no
thread in here, no loop, no budget and no card. A mode is not something this machine DOES,
it is a way it TALKS, so the whole of the mechanism is a word in a JSON file that
server.persona_prompt() reads on its way past.

WHY A FILE AND NOT A VARIABLE. revenue.py's answer, for revenue.py's reason: a mode set by
voice at eleven and forgotten by a restart at noon is a mode the boss has to set twice, and
the second time he will not know why. The write is the atomic one this house uses
everywhere - a .tmp beside the real file, then os.replace, under this module's lock AND
hunter.file_lock, so two processes (the server and a harness) cannot interleave a write.

WHAT IT DELIBERATELY DOES NOT DO - v1, and each of these is a decision rather than an
omission:

  - IT GATES NOTHING. Not a hand, not the web, not the notes, not the Eyes. Work Mode makes
    him terse; it does not take the search away from him. A mode that silently removed a
    capability would be a mode the boss has to remember the rules of, and he would discover
    the rules by being refused something.
  - IT IS NOT THE DECK'S "WORK MODE". focus.py and viewer/index.html have had a thing by
    that name since long before this file: an ambient lighting state during a focus lock.
    That is a LOOK and this is a TONE, they are independent, and neither reads the other.
    Setting Work Mode here does not light the deck, and a focus session does not make him
    terse. Two features, one unfortunate word, kept apart on purpose.
  - IT HOLDS NO ADDRESS FORM. Not "sir", not a name. server.py owns the persona block and
    is the only thing in this house entitled to say what the boss is called, so every
    sentence out of here that needs his name takes it as an argument - scholar.py's law,
    for scholar.py's reason.
  - IT NEVER RAISES. read_state() answers Normal for a missing file, a locked file, a
    corrupt file and a file holding a mode nobody has heard of. A butler who will not
    answer a question because his tone file has one bad byte is worse than one whose tone
    is briefly wrong, and the brain call this sits in front of must not be the thing that
    fails.

THE ONE COLLISION WORTH WRITING DOWN. "study mode" is matched by server.py's STUDY_NOW_RE
as a request to research a topic literally called "mode" - it reads
(study|research) <topic>, and "mode" is a perfectly good topic as far as that pattern is
concerned. So the branch that calls this file MUST sit above §30's in protected_answer(),
and it does. Read in the other order, "study mode mein jao" would have spent ninety seconds
of Groq researching the word "mode" and written a note about it.
"""
import json
import os
import re
import threading
import time

import hunter                                  # file_lock, and nothing else from it

HERE = os.path.dirname(os.path.abspath(__file__))
STATE_PATH = os.environ.get("TRONE_MODE_STATE") or os.path.join(HERE, "mode-state.json")

# NORMAL IS FIRST AND IT IS THE DEFAULT, which is the whole design in one tuple: every
# unreadable state, every unknown word and every fresh install is Normal, and Normal is
# defined as "exactly what this machine did before this file existed".
MODES = ("normal", "work", "play", "study")
DEFAULT_MODE = "normal"

_lock = threading.Lock()

# How far back "study update" looks when it reads the Scholar's shelf. Seven days because
# the syllabus rotates topics and a week is the span over which the rotation is visible;
# the cost of a larger number is only a few more listdir prefix comparisons, but a recap
# that reaches back a month stops being a recap.
RECAP_DAYS = 7


def _stamp():
    return time.strftime("%Y-%m-%d %H:%M:%S")


# ------------------------------------------------------------------ the flag on disk

def read_state():
    """{"mode", "since", "by"} - and it NEVER raises. See the module docstring.

    An unknown mode word is read as Normal rather than passed through, because the only
    consumer is prompt_block() and a mode with no block is a mode with no effect wearing
    a name the badge would display.
    """
    data = {}
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as fh:
            got = json.load(fh)
        if isinstance(got, dict):
            data = got
    except (OSError, ValueError):
        data = {}
    name = str(data.get("mode") or "").strip().lower()
    if name not in MODES:
        name = DEFAULT_MODE
    return {"mode": name, "since": str(data.get("since") or ""),
            "by": str(data.get("by") or "")}


def current():
    """The one word, for a caller that wants nothing else."""
    return read_state()["mode"]


def switch(name, by="voice"):
    """Set the mode and return the new state. Instant, atomic, and no card.

    NO CONFIRMATION, BY DECISION. revenue.switch()'s ON needs a card because it sets a
    daemon bidding the boss's money; this sets an adjective. The card mechanism is
    deliberately not borrowed - see the module docstring - and the only thing kept from
    revenue._write_state() is the write itself.
    """
    name = str(name or "").strip().lower()
    if name not in MODES:
        name = DEFAULT_MODE
    state = {"mode": name, "since": _stamp(), "by": str(by)[:20]}
    with _lock, hunter.file_lock(STATE_PATH):
        tmp = STATE_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(state, fh, indent=1, ensure_ascii=False)
            fh.write("\n")
        os.replace(tmp, STATE_PATH)
    return state


# ------------------------------------------------------------------ the sentences
#
# ANCHORED ^...$ ON THE WHOLE ADDRESSLESS UTTERANCE, which is STUDY_NOW_RE's discipline and
# it is here for STUDY_NOW_RE's reason: a question ABOUT a mode must not BE a mode switch.
# "what is work mode", "should I use study mode", "I like play mode better" all have
# something in front of the phrase, so the anchor refuses them before any group is read.
# _MODE_NOT below carries the controls the test asserts.
#
# THE HINGLISH TAILS ARE OPTIONAL SUFFIXES rather than separate patterns, so each mode word
# is written once and the four read identically. "mein jao", "on karo" and "chalu karo" are
# the three forms actually said out loud in this house; "me jao" and "mein jaao" are the
# spellings a speech-to-text pass produces for the first of them, which is not a spelling
# mistake to correct but a transcript to accept.
_SET = r"""^(?:
      (?:(?:ab\s+)?(?:please\s+)?)
      (?:go\s+(?:in)?to\s+|switch\s+(?:to|in\s*to)\s+|be\s+in\s+|enter\s+|activate\s+|
         start\s+|turn\s+on\s+)?
      %(word)s(?:\s+mode)?
      (?:\s+(?:mein|me|main)\s+(?:jao|jaao|ja|chalo|aa\s*jao)
        |\s+(?:on|chalu|shuru|start)\s+(?:karo|kar\s+do|kar\s+dijiye|kardo)
        |\s+(?:on|please|now|karo|kardo)
      )?
  )$"""

# `word` for each mode. Work carries "focus" too, because "focus mode" is what the phrase
# wants to be - and it is safe here only because this pattern requires the whole utterance:
# focus.py's own sentences ("start a focus session", "focus for 40 minutes") all carry more
# than the bare phrase and cannot reach it. Study carries "padhai" and Play "masti", which
# are the words that actually get said.
_WORDS = {
    "work": r"(?:work|kaam|focus)",
    "play": r"(?:play|fun|masti|chill)",
    "study": r"(?:study|padhai|padai|learning)",
    "normal": r"(?:normal|default|usual|aam|saadharan)",
}

_SET_RE = {name: re.compile(_SET % {"word": word}, re.IGNORECASE | re.VERBOSE)
           for name, word in _WORDS.items()}

# THE RESET HAS SENTENCES OF ITS OWN, beyond "normal mode": the boss leaving a mode is more
# likely to say what he is leaving than where he is going. "exit work mode", "mode off",
# "stop study mode", "normal mode mein wapas aao".
_RESET_RE = re.compile(r"""^(?:
      (?:please\s+)?
      (?:
          (?:exit|leave|stop|end|quit|cancel|turn\s+off|switch\s+off)
            \s+(?:the\s+)?(?:work|play|study|kaam|padhai|masti|focus|this|that|current)?
            \s*mode
        | mode\s+(?:off|band\s+karo|hatao|reset)
        | reset\s+(?:the\s+)?mode
        | (?:mode\s+)?normal\s+karo
        | normal\s+mode\s+(?:mein|me|main)\s+(?:wapas\s+)?(?:aao|aa\s*jao|jao|lauto)
        | (?:wapas\s+)?normal\s+(?:mein|me)\s+(?:aao|aa\s*jao|jao)
      )
  )$""", re.IGNORECASE | re.VERBOSE)

# "WHICH MODE AM I IN" is a read and it is free, so it is answered from the file like
# everything else here rather than by a model that would cheerfully guess.
_ASK_RE = re.compile(r"""^(?:
      (?:(?:so\s+)?(?:which|what)\s+mode\s+(?:are\s+you\s+in|is\s+(?:this|it|on)|am\s+i\s+in)
        |(?:what\s+is\s+)?(?:your|the)\s+current\s+mode
        |mode\s*\?
        |kaun\s*sa\s+mode\s+(?:hai|chal\s+raha\s+hai)
        |konsa\s+mode\s+hai
      )
  )$""", re.IGNORECASE | re.VERBOSE)

# STUDY MODE'S RECAP SENTENCE. "what did you study" is already in server.py's _STUDY_NOT -
# the list of things STUDY_NOW_RE must NOT match - so claiming it here takes nothing from
# the Scholar's own branch and fills a hole that was previously answered by the brain
# guessing at a shelf it cannot see.

# THE TAIL THIS SENTENCE MAY TRAIL OFF INTO, AND IT IS A CLOSED LIST BECAUSE AN OPEN ONE
# SWALLOWED THE TOPIC. It was `.{0,30}` and it was wrong in the way that is hardest to see:
# it was meant to absorb the filler a spoken question ends on - "what did you study TODAY",
# "what have you learned SO FAR" - but `.` takes a topic as happily as an adverb, so
#
#     "what did you study about physics"
#
# matched here and was answered with the shelf recap: a canned list of the four syllabus
# notes, in reply to a question about physics. The answer is confident, well-formed, and
# about the wrong subject, which is the expensive kind of wrong - nobody reports it, because
# it reads like an answer.
#
# THE LINE IS BETWEEN THE SESSION AND A TOPIC. "What did you study" asks about the shelf and
# belongs here. "What did you study ABOUT PHYSICS" asks about a subject and belongs to the
# notes search, which can go and look for physics; this function cannot, and has nothing to
# offer but the list. So "about", "on" and "regarding" are deliberately absent below, and
# every word that IS here is an adverb of time.
#
# IT IS ONE DEFINITION USED BY BOTH VERB ARMS, which is the other half of the repair. The
# two arms were written separately and had already drifted - `stud*` took "did" or "have",
# `learn*` took only "have", so "what did you learn" fell through to the brain while "what
# did you study" did not. One definition cannot drift from itself.
_RECAP_TAIL = r"""(?:\s+(?:today|yesterday|so\s+far|recently|lately|this\s+week
                          |this\s+morning|of\s+late|all\s+day|already|till\s+now
                          |abhi\s+tak|aaj))?"""

_UPDATE_RE = re.compile(r"""^(?:
      (?:please\s+)?
      (?:
          study\s+update
        | (?:the\s+)?study\s+(?:recap|summary|report)
        | what\s+(?:did|have)\s+you\s+(?:just\s+|been\s+)?stud(?:y|ied|ying)%(tail)s
        | what\s+(?:did|have)\s+you\s+(?:just\s+|been\s+)?learn(?:ed|t|ing)?%(tail)s
        | (?:padhai|study)\s+(?:ka|ki)\s+(?:update|report)
        | padhai\s+kaisi\s+(?:chal\s+rahi\s+)?hai
      )
  )$""" % {"tail": _RECAP_TAIL}, re.IGNORECASE | re.VERBOSE)

# WHAT MUST NOT MATCH, and test_mode.py carries every one of them as a control. They come in
# three groups, and each group is a different way of being wrong:
#
#   - THE QUESTIONS ABOUT A MODE. Each would have been a silent mode switch in the middle of
#     an ordinary question, and silent is the whole problem: he asks what Work Mode is, gets
#     an answer, and every reply after it is terse for a reason he never saw.
#   - THE TWO THAT MUST REACH SOMEBODY ELSE. "study micro-saas now" is the Scholar's own
#     sentence and must still reach him; "research transformer attention" likewise.
#   - THE TOPIC-SCOPED RECAPS, which is the group this file got wrong. Every one of these
#     names a SUBJECT, so every one belongs to the notes search rather than to the shelf
#     recap - see _RECAP_TAIL. The long one was already here and passed for the wrong
#     reason: it was refused for being over thirty characters, not for naming a topic, so
#     the shorter "what did you study about physics" sailed through and was answered with a
#     list of syllabus notes. The short ones are the real control.
_MODE_NOT = ("what is work mode", "should i use study mode", "i like play mode better",
             "how does work mode work", "tell me about play mode",
             "is normal mode the default", "what modes do you have",
             "study micro-saas now", "research transformer attention",
             "what did you study today about rate limiting while i was out and about",
             "what did you study about physics", "what did you learn about physics",
             "what have you learned about derivatives",
             "what did you study on rate limiting")


def parse_request(sentence):
    """{"action": set|update|ask, ...} for one of the sentences above, or None.

    ORDER IS LOAD-BEARING AND IT IS THE NARROWEST FIRST. The recap and the reset are read
    before the four setters, because "study update" ends in neither a mode word nor a tail
    the setters accept but is close enough to one that a looser pattern would have taken
    it, and because "exit study mode" contains the word study.
    """
    text = " ".join(str(sentence or "").split()).strip().rstrip("!. ")
    if not text:
        return None
    if _UPDATE_RE.match(text):
        return {"action": "update"}
    if _ASK_RE.match(text):
        return {"action": "ask"}
    if _RESET_RE.match(text):
        return {"action": "set", "mode": "normal"}
    for name in MODES:
        if _SET_RE[name].match(text):
            return {"action": "set", "mode": name}
    return None


# ------------------------------------------------------------------ what the brain reads
#
# SHORT, AND THE SHORTNESS IS THE POINT. Every character in here is paid on every brain
# call in the house - all eight call sites, since persona_prompt() is the one funnel - and
# a mode is an adjustment to a persona that already exists, not a second persona. A block
# that re-described who he is would fight the block above it, and the model would resolve
# the fight by picking one, differently each turn.
#
# NORMAL'S BLOCK IS THE EMPTY STRING, which is what makes Normal a true reset: in Normal
# Mode persona_prompt() returns byte-for-byte what it returned before this file existed.
# test_mode.py asserts that equality rather than trusting it.
_BLOCKS = {
    "normal": "",
    "work": (
        "HOW YOU ARE TALKING JUST NOW - WORK MODE.\n"
        "- He is working. Be brief and serious: the answer first, in as few sentences as it "
        "honestly takes, and nothing after it.\n"
        "- No small talk, no warm-up line, no offer of further help he did not ask for. If "
        "something is worth raising, raise it in one clause at the end.\n"
        "- You have lost no ability - every hand, sense and search is still yours, and you "
        "still put each hand to him for a yes. Only the talking is shorter.\n"
    ),
    "play": (
        "HOW YOU ARE TALKING JUST NOW - PLAY MODE.\n"
        "- He is off the clock. Be light and casual, and let a bit of wit through where it "
        "fits; you may be playful about yourself.\n"
        "- Still answer the actual question, and never invent a fact to make a better line. "
        "Being fun is not a licence to be wrong.\n"
        "- If something is genuinely urgent or he asks for a real figure, drop the register "
        "and give it to him straight.\n"
    ),
    "study": (
        "HOW YOU ARE TALKING JUST NOW - STUDY MODE.\n"
        "- He is learning. Be a patient teacher: start from what the thing IS, build up in "
        "order, and prefer one worked example over three abstractions.\n"
        "- Define a term the first time you use it. Where you are simplifying, say so.\n"
        "- You may end with one short question that checks he has it - one, not a quiz, and "
        "never instead of the answer.\n"
    ),
}


def prompt_block(name=None):
    """The per-mode instruction block for persona_prompt(), or "" in Normal Mode.

    Takes the mode as an argument but reads the file when given none, so a caller on the
    brain path pays one small read and a test pays none.
    """
    name = str(name or "").strip().lower() or current()
    return _BLOCKS.get(name, "")


# ------------------------------------------------------------------ what he says

def switch_line(name, boss_call="sir", was=""):
    """The one sentence spoken when the mode changes. Short, and it says what changed."""
    if name == was:
        return {"work": "Already in work mode, %s." % boss_call,
                "play": "Already in play mode, %s." % boss_call,
                "study": "Already in study mode, %s." % boss_call,
                "normal": "Already back to normal, %s." % boss_call}[name]
    return {
        "work": "Work mode, %s - short answers, the task first." % boss_call,
        "play": "Play mode, %s. Off the clock." % boss_call,
        "study": ("Study mode, %s - I shall take things in order. Name a topic and I "
                  "shall go and read about it." % boss_call),
        "normal": "Back to normal, %s." % boss_call,
    }[name]


def state_line(boss_call="sir"):
    """"which mode am i in", answered from the file."""
    st = read_state()
    if st["mode"] == "normal":
        return "Normal mode, %s - nothing adjusted." % boss_call
    return "%s mode, %s, since %s." % (st["mode"].capitalize(), boss_call,
                                       st["since"] or "a little while ago")


# ------------------------------------------------- "study update", read off the shelf
#
# revenue.report()'S SHAPE EXACTLY: it reads the real files, composes ONE spoken line, and
# says what is not there rather than filling it in. Nothing in here is remembered and
# nothing is asked of a model.
#
# AND IT ADDS NO FILE READING OF ITS OWN. scholar.studied_today(when) already lists and
# parses the notes for one day, so a week is seven calls to it rather than a second,
# divergent reader of the same folder - which is how the two would eventually disagree
# about what a note is called. scholar.py is imported here and not at the top of the file
# because mode.py sits in front of every brain call and the Scholar's module is only wanted
# by this one function.
def study_report(boss_call="sir", days=RECAP_DAYS, now=None):
    """One line recapping notes/study/auto/, or the honest absence of one."""
    try:
        import scholar
    except Exception:                                          # noqa: BLE001
        return "I cannot reach my own study shelf just now, %s." % boss_call

    now = now if now is not None else time.time()
    seen, by_day = set(), []
    for back in range(max(1, int(days))):
        when = time.localtime(now - back * 86400.0)
        try:
            rows = scholar.studied_today(when)
        except Exception:                                      # noqa: BLE001
            rows = []
        fresh = [r for r in rows if r["file"] not in seen]
        seen.update(r["file"] for r in fresh)
        if fresh:
            by_day.append((back, fresh))

    # THE LIVE TICK IS PART OF THE ANSWER, because "nothing yet today" and "I am reading
    # about it right now" are different facts and the second one is the more useful.
    busy = ""
    try:
        live = scholar.MANAGER.state()
        if live.get("studying") and live.get("topic"):
            busy = " I am reading about %s as we speak." % live["topic"]
    except Exception:                                          # noqa: BLE001
        pass

    if not by_day:
        return ("I have not written a study note in the last %d days, %s.%s"
                % (max(1, int(days)), boss_call, busy or
                   " Name a topic and I shall go and read about it."))

    def names(rows):
        got = [r["topic"] or r["title"] for r in rows]
        if len(got) == 1:
            return got[0]
        return ", ".join(got[:-1]) + " and " + got[-1]

    parts = []
    today = [rows for back, rows in by_day if back == 0]
    if today:
        parts.append("Today, %s: %s" % (boss_call, names(today[0])))
    else:
        parts.append("Nothing today, %s" % boss_call)
    earlier = [(back, rows) for back, rows in by_day if back > 0]
    if earlier:
        bits = []
        for back, rows in earlier[:3]:
            bits.append("%s, %s" % ("yesterday" if back == 1 else "%d days ago" % back,
                                    names(rows)))
        parts.append("; before that, " + "; ".join(bits))
    total = len(seen)
    parts.append(". That is %d note%s on the shelf from the last %d days, and they are in "
                 "your notes under study, auto." % (total, "" if total == 1 else "s",
                                                    max(1, int(days))))
    return "".join(parts) + busy
