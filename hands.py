#!/usr/bin/env python3
"""hands.py - the registry, the proposal, the confirmation gate, and the execution.

The assistant can read, see, remember and look things up. This is the first module in
which it can DO something, and everything here is arranged around one sentence: nothing
runs until a human says so, and no part of this machine can route around that.

Read in this order, because each piece exists to protect the one before it:

  THE REGISTRY.  tools/registry.json is the only source of truth. A tool id that is not
    in it does not exist - looked up exactly, with no fuzzy match and no nearest-name
    fallback, exactly the discipline the model allowlist keeps. The brain is shown the
    capability SENTENCES and never the file, so it cannot learn a path, a timeout or a
    filename from us. The registry holds no keys; a tool that needs one reads config.json
    itself, server-side, and the wire never carries it.

  THE PROPOSAL.  The brain asks for hands with one control tag, [[tool: id | {json}]],
    in the same discipline as [[brain: ...]]: the tag is the request, and whatever prose
    arrived with it is DISCARDED. The spoken proposal is then composed from the registry
    template - never from the model's own words - because a model that paraphrases an
    action can understate it, and "shall I tidy that up for you?" is a poor description of
    sending mail to a stranger. A missing required parameter is a refusal that names the
    field, and nothing is left pending.

  THE CONFIRMATION.  One pending proposal at a time, in one slot, for the whole machine.
    It is answered from either door - the Yes/No pair in the asking tab, or the words
    yes / go ahead / do it, no / cancel / never mind while the mic is open - and anything
    else lets it go, because silence is not consent and a changed subject is a withdrawal.
    It lapses on its own after CONFIRM_TTL_S and says so once.

  THE EXECUTION.  subprocess.run([sys.executable, script], input=json_text): a list, not
    a string, JSON on stdin and never on argv, shell=False always, the registry's timeout,
    and output captured with errors="replace" because this is Windows. One at a time. The
    script's stdout is the ONLY evidence - on a non-zero exit, a timeout or a missing file
    the assistant says plainly that the tool failed and gives the reason it observed.

  THE LEDGER.  tools-ledger.json holds outcomes and nothing else: four counts per tool
    and the timestamp of the last actual run. No parameters, no bodies, no recipients, no
    addresses. Every other surface in this file follows the same rule - the trace log
    records that two parameters were validated, never what they were.

The one thing that is NOT here: any judgement about whether a request was a good idea.
That is the human's job, and the whole point of the pair of buttons is that they are the
ones who does it.
"""

import json
import pathlib
import re
import subprocess
from tools import _proc
import sys
import threading
import time

ROOT = pathlib.Path(__file__).resolve().parent
TOOLS_DIR = ROOT / "tools"
REGISTRY_PATH = TOOLS_DIR / "registry.json"
LEDGER_PATH = ROOT / "tools-ledger.json"

# How long a proposal waits for a word before it lets itself go. Two minutes: long
# enough to read the parameters and think about them, short enough that a tab left open
# over lunch cannot be confirmed by somebody walking past.
CONFIRM_TTL_S = 120
# The most of a script's stdout that is ever quoted back. The voice caps itself again in
# the viewer; this cap is so a script that dumps a logfile cannot flood the card.
EVIDENCE_MAX_CHARS = 600
TYPES = ("string", "text", "integer", "number", "boolean")
OUTCOMES = ("ok", "failed", "refused", "lapsed")

# ---------------------------------------------------------------------- the chain
# More than one hand, in order, behind ONE word. Everything below is arranged so that a
# chain is a different PROPOSAL and not a different GATE: it goes into the same single slot,
# it is answered at the same doors, and it is therefore covered by the Doorman's voiceprint
# law, the TTL, the withdrawal rule and the supersede rule without any of them being told
# that chains exist. A second gate for multi-step work would have been a second gate to
# forget to guard, and the guard is the whole point of this file.
#
# FOUR, and it is a cap rather than a limit discovered at runtime: a plan longer than four
# steps cannot be read off a card in the time a TTL allows, and a human approving a list
# they have not finished reading is the exact failure the pair of buttons exists to prevent.
CHAIN_MAX_STEPS = 4
# How much of an earlier step's evidence may be pasted into a later step's text. The
# evidence is already capped at EVIDENCE_MAX_CHARS; this is the tighter cap for the case
# where it travels onward into something that gets SENT, because a body that is mostly
# somebody else's stdout is not a letter the employer wrote.
CHAIN_PASTE_MAX = 200
# THE CHAIN TAG, and it is deliberately NOT a regex like TOOL_TAG_RE above. Measured, not
# assumed: the tag's terminator is "]]" and a JSON array's terminator is "]", so a model
# asked for [[chain: [ {...}, {...} ]]] writes "}}]]" and the three closing brackets a
# regex would have to demand NEVER ARRIVE. The first probe of this scored 0 chains out of
# 5 for exactly that reason, and all six of the next six closed with a single "]". So the
# array is parsed by json's own scanner, which is the authority on where an array ends, and
# the terminator is then whatever happens to be left over. See chain_tag().
CHAIN_TAG_AT = re.compile(r"\[\[\s*chain\s*:\s*", re.I)
# {{step1}} - where an earlier step's result belongs. One or two digits, so a typo cannot
# address step 400 and a runaway cannot be written at all.
STEP_REF_RE = re.compile(r"\{\{\s*step\s*(\d{1,2})\s*\}\}", re.I)
_DECODER = json.JSONDecoder()
CHAIN_STATUSES = ("ok", "halted", "refused")
# The most chain rows kept on disk. A ledger is an account, not an archive, and an
# unbounded list in a file that is rewritten on every single outcome is a file that grows
# until somebody notices.
CHAIN_LEDGER_MAX = 50

# THE CONTROL TAG. [[tool: send_email | {"to": "...", "subject": "..."}]] - the id is
# bounded and the parameters are one flat JSON object. The tag is the only way the brain
# can ask for hands, and it is taught to the notes and small-talk prompts only: hands are
# offered from your desk, never from a web page, so WEB_PROMPT never learns it.
TOOL_TAG_RE = re.compile(r"\[\[\s*tool\s*:\s*([^\]\n|]{1,60}?)\s*"
                         r"(?:\|\s*(\{.*?\})\s*)?\]\]", re.I | re.S)

# THE TWO WORDS, and they must be the WHOLE message. "yes" is consent; "yes, and while
# you are at it, what is the population of Tokyo" is a new subject, which withdraws the
# request rather than approving it.
#
# People do not answer in single words, though. "Yes, go ahead" and "no, never mind" are
# what a microphone actually hears, so a word of the right kind may repeat, joined by a
# comma or an "and" - and NOTHING else may appear. A message that mixes the two kinds,
# "yes, cancel that", matches neither and is therefore a withdrawal: an ambiguous answer
# is not consent.
# "haan" is Hindi for yes and it is how the boss actually answers half the time, usually
# doubled or with the English word after it - "haan yes", "haan haan do it". It is here and
# not in a separate list because a yes is a yes in whatever language it arrives in, and a
# second list would be a second thing for the gate to forget to read.
#
# SECTION 35 ADDED `nahi` AND ONE SPELLING, AND THE ASYMMETRY IS THE REASON. `haan` was here
# from the start and its opposite was not, which meant this house heard the boss's Hindi yes
# and not his Hindi no - and of the two, the unheard NO is the worse one to be missing: an
# unheard yes is a hand that does not run and he says it again, while an unheard no leaves the
# proposal standing in the slot AND sends the refusal to the notes as a new subject. `nahi`,
# `nahin` and `nahi ji` go in; `na` and `naa` deliberately do NOT, because "na" is also an
# English filler and a Hindi tag question ("you'll do it, na?"), and a two-letter alternative
# inside an anchored whole-message pattern is the cheapest way to turn this grammar into a
# sieve - which is the one failure preflight's pool check exists to catch.
# `thik hai` is the same word as `theek hai` romanised the other way, and a romanisation this
# file does not list is a word the boss says and the gate does not hear.
_YES_WORDS = r"""
      yes | yes\s+please | yep | yeah | yup | aye | ok | okay | okey\s*dokey
    | haan | haan\s*ji | han | theek\s+hai | thik\s+hai | thek\s+hai
    | kar\s+do | bilkul
    | sure | go\s+ahead | go\s+on | do\s+it | send\s+it | please\s+do | do\s+so
    | proceed | confirm(?:ed)? | affirmative | very\s+well | if\s+you\s+would
    | that'?s\s+right | correct | please
"""
_NO_WORDS = r"""
      no | no\s+thanks | no\s+thank\s+you | nope | nah | negative | cancel
    | nahi | nahin | nahi\s*ji | nahin\s*ji
    | cancel\s+(?:it|that) | stop | don'?t | do\s+not | never\s*mind | forget\s+it
    | leave\s+it | hold\s+off | not\s+now | not\s+yet | scrap\s+(?:it|that)
    | on\s+second\s+thought(?:s)? | thank\s+you
"""
_WHOLE = r"""^[\s"'(]*(?:%s)(?:[\s,]+(?:and\s+|but\s+)?(?:%s))*[\s.!,"')]*$"""

YES_RE = re.compile(_WHOLE % (_YES_WORDS, _YES_WORDS), re.I | re.X)
NO_RE = re.compile(_WHOLE % (_NO_WORDS, _NO_WORDS), re.I | re.X)

# Every line this module can speak, in one place, so the voice is one voice and a new
# outcome cannot arrive with wording invented at the call site.
LINES = {
    "nothing": "There is nothing awaiting your word, sir.",
    "unknown": "I have no such tool to hand, sir, and I will not guess at a near one.",
    "missing": "I should need the {field} before I could do that, sir, so I have set the "
               "request aside.",
    "badtype": "The {field} I was given is not a {type}, sir, so I have set the request "
               "aside.",
    "unreadable": "The details of that request would not parse, sir, so nothing is "
                  "pending.",
    "noregistry": "I have no tools configured, sir; there is nothing I could run.",
    "superseded": "I have let the earlier request go, sir.",
    "withdrawn": "You have changed the subject, sir, so I have let that request go.",
    "refused": "Very good, sir. I have done nothing.",
    "lapsed": "The matter lapsed unanswered, sir; nothing was done.",
    "busy": "One thing at a time, sir; I am still at the last one.",
    "noscript": "The script for that is not where the registry says it is, sir, so "
                "nothing ran.",
    "timeout": "The tool was still running after {seconds} seconds, sir, so I stopped "
               "it. I cannot tell you whether it finished.",
    "failed": "The tool failed, sir: {reason}",
    "silent": "The tool exited without saying anything, sir, so I will not claim it "
              "worked.",
    "crashed": "I could not start the tool at all, sir: {reason}",
    # For the one case where a tag arrives that was never offered: the tag is dropped,
    # and if there was no prose with it there has to be SOMETHING to say.
    "instead": "I am not sure I can help with that one, sir.",
    # THE CHAIN. Every one of these names the STEP it went wrong at, because "the plan would
    # not parse" tells a human nothing they can act on and "step 2 needs the subject" tells
    # them exactly what to say next.
    "chainempty": "That came back as a plan with no steps in it, sir, so there is nothing "
                  "pending.",
    "chainlong": "That is a plan of {n} steps, sir, and I will not put more than {max} "
                 "behind a single word. Ask me for the first part and then the rest.",
    "chainbadstep": "Step {at} of that plan would not parse, sir, so nothing is pending.",
    "chainunknown": "Step {at} of that plan asks for a tool I do not have, sir, and I will "
                    "not guess at a near one, so nothing is pending.",
    "chainstep": "Step {at} of that plan is not something I can do yet: {why} So nothing "
                 "is pending.",
    "chainref": "Step {at} of that plan refers to step {to}, sir, which is not before it, "
                "so nothing is pending.",
    "chainreffield": "Step {at} of that plan would paste an earlier result into {field}, "
                     "sir, and that is not a field I will fill in on your behalf. Nothing "
                     "is pending.",
}

_lock = threading.Lock()          # guards _pending, _running and _seq
_cache = {"mtime": 0.0, "tools": [], "error": ""}
_pending = None                   # the one slot: see propose()
_running = None                   # the id of the tool currently executing, or None
_seq = 0


# ------------------------------------------------------------------- the registry

def _slug(value, limit=40):
    text = str(value or "").strip().lower()
    return text if re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,%d}" % (limit - 1), text) else ""


def _clean_tool(raw):
    """One registry entry, validated, or None with a reason on stderr.

    An entry that does not validate DOES NOT EXIST - it is not repaired, defaulted or
    guessed at. The registry is the source of truth, and a source of truth that quietly
    fixes itself is a source of surprises.
    """
    if not isinstance(raw, dict):
        return None, "not an object"
    tool_id = _slug(raw.get("id"))
    if not tool_id:
        return None, "no usable id"
    script = str(raw.get("script") or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,60}\.py", script) or script.startswith("."):
        # A bare filename inside tools/, so there is no path to traverse and no
        # extension to be surprised by. This is the only place a filename is accepted.
        return None, "%s: script must be a plain .py filename inside tools/" % tool_id
    caps = [str(c).strip() for c in (raw.get("capabilities") or []) if str(c).strip()]
    if not caps:
        return None, "%s: no capability sentences, so the brain could never match it" % tool_id
    params, seen = [], set()
    for item in (raw.get("params") or []):
        if not isinstance(item, dict):
            return None, "%s: a parameter is not an object" % tool_id
        name = _slug(item.get("name"), 32)
        kind = str(item.get("type") or "string").strip().lower()
        if not name or name in seen:
            return None, "%s: a parameter has no usable name" % tool_id
        if kind not in TYPES:
            return None, "%s: %s has type %r, which is not one of %s" % (
                tool_id, name, kind, ", ".join(TYPES))
        seen.add(name)
        params.append({"name": name, "type": kind,
                       "required": bool(item.get("required"))})
    proposal = str(raw.get("proposal") or "").strip()
    if not proposal:
        return None, "%s: no proposal template, so it could not be asked for" % tool_id
    # THE STEP LINE: the same action as an IMPERATIVE rather than a question, for the numbered
    # list on a Chain Card. It is required rather than defaulted, and required for the same
    # reason `proposal` is: a tool with no sentence of its own would have to be described by
    # something, and the only somethings available are its id - which is a filename, not
    # English - or the model's own prose, which is the one voice this module will not use.
    #
    # AND IT NAMES LESS THAN THE CARD SHOWS, DELIBERATELY. The chain's line is SPOKEN, so a
    # step line that interpolated {body} or {minutes} would read the employer's correspondence
    # out loud to whoever is in the room - exactly the leak preflight 16(f) plants a canary
    # for. The rows below the list still show every parameter in full, because that is read
    # with the eyes by the one person entitled to read it.
    step = str(raw.get("step") or "").strip()
    if not step:
        return None, ("%s: no step template, so it could not appear in a chain's numbered "
                      "list in anything but its own filename" % tool_id)
    for secret in ("{body}", "{minutes}", "{description}"):
        if secret in step:
            return None, ("%s: the step template interpolates %s, and a step line is spoken "
                          "aloud - see the note above _clean_tool's step check" % (tool_id,
                                                                                  secret))
    try:
        timeout = float(raw.get("timeout_s") or 0)
    except (TypeError, ValueError):
        timeout = 0.0
    if not 0.5 <= timeout <= 600:
        return None, "%s: timeout_s must be between 0.5 and 600" % tool_id
    triggers = []
    for pattern in (raw.get("triggers") or []):
        try:
            triggers.append(re.compile(str(pattern), re.I))
        except re.error as exc:
            return None, "%s: trigger %r does not compile (%s)" % (tool_id, pattern, exc)
    # THE DOORS, when an entry names any: the only doors propose() will accept it from. A tool
    # that names doors is never offered to the brain (prompt_parts skips it), never taken from
    # a [[tool: ...]] tag and never a step of a chain - because its parameters must come from
    # the employer's own sentence, parsed by the server, and never from a model's. The ledger's
    # two hands are the reason: an amount a model filled in is an invented number with a
    # card around it. An entry that names none keeps every door, exactly as before.
    doors = tuple(d for d in (_slug(x, 12) for x in (raw.get("doors") or [])) if d)
    if raw.get("doors") and not doors:
        return None, "%s: doors names no usable door" % tool_id
    if "tag" in doors:
        return None, "%s: a door list exists to shut out the tag; it cannot name it" % tool_id
    return {"id": tool_id, "name": str(raw.get("name") or tool_id).strip(),
            "script": script, "capabilities": caps, "params": params,
            "timeout_s": timeout, "proposal": proposal, "step": step,
            "triggers": triggers, "doors": doors}, ""


def registry(force=False):
    """The validated tools, re-read whenever the file changes underneath us.

    Cached on mtime so that adding a hand means editing JSON and asking again - no
    restart - while a question does not cost a file read.
    """
    global _cache
    try:
        mtime = REGISTRY_PATH.stat().st_mtime
    except OSError:
        _cache = {"mtime": 0.0, "tools": [],
                  "error": "tools/registry.json is not there"}
        return []
    if not force and mtime == _cache["mtime"]:
        return _cache["tools"]
    try:
        data = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        sys.stderr.write("  tools: registry unreadable (%s); no hands this run\n" % exc)
        _cache = {"mtime": mtime, "tools": [], "error": "registry unreadable: %s" % exc}
        return []
    tools, ids = [], set()
    for raw in (data.get("tools") if isinstance(data, dict) else data) or []:
        tool, why = _clean_tool(raw)
        if tool is None:
            sys.stderr.write("  tools: registry entry ignored - %s\n" % why)
            continue
        if tool["id"] in ids:
            sys.stderr.write("  tools: duplicate id %r ignored\n" % tool["id"])
            continue
        ids.add(tool["id"])
        tools.append(tool)
    _cache = {"mtime": mtime, "tools": tools, "error": ""}
    return tools


def find(tool_id):
    """Exactly this id or nothing at all. The whole gate rests on this being exact."""
    wanted = str(tool_id or "").strip().lower()
    for tool in registry():
        if tool["id"] == wanted:
            return tool
    return None


def public_registry():
    """What GET /tools serves: no script path, no trigger, no timeout arithmetic."""
    return [{"id": t["id"], "name": t["name"], "capabilities": list(t["capabilities"]),
             "params": [dict(p) for p in t["params"]], "timeoutS": t["timeout_s"]}
            for t in registry()]


def prompt_block():
    """The hands, described to the brain: capability sentences, and one tag.

    Composed here rather than typed into the prompt constants, and that is deliberate
    twice over: the persona block stays exactly as it was, and the brain can only ever be
    told about tools that really exist, because this is generated from the registry that
    the executor also reads. A capability sentence cannot drift out of date.

    IT IS NOW A COMPOSITION, not a construction. Every caller that wants the whole thing
    still gets the identical string; prompt_parts() exists for the one caller that needs
    the seam - the context budget, which must be able to say how many characters the
    manifest costs and how many the protocol costs, separately, because a budget that can
    only report a total cannot tell you which block to cut. The join is exact: the lines
    are joined with newlines and the protocol was the last line, so manifest + "\\n" +
    protocol is the same bytes it always was. Preflight asserts that equality rather than
    trusting this paragraph, because two functions composing one string can disagree.
    """
    manifest, protocol = prompt_parts()
    if not manifest:
        return ""
    return manifest + "\n" + protocol


def prompt_parts():
    """(manifest, protocol) - prompt_block() split at its seam, for the context budget.

    ("", "") when there are no hands at all, which is the same nothing prompt_block()
    returns: a machine with no tools is told about no tools, not told about a protocol
    for using the tools it does not have.
    """
    tools = registry()
    if not tools:
        return "", ""
    lines = ["\n- YOUR HANDS: there are a few things you can actually DO, by asking the "
             "server to run a script. These are all of them, and there are no others:"]
    for tool in tools:
        if tool.get("doors"):
            continue        # a door-bound hand is never the brain's to ask for - see _clean_tool
        shape = ", ".join("%s (%s%s)" % (p["name"], p["type"],
                                        "" if p["required"] else ", optional")
                          for p in tool["params"]) or "no details needed"
        lines.append("  * %s - %s. Details: %s"
                     % (tool["id"], "; ".join(tool["capabilities"]), shape))
    # THE CLOCK, and it is here for exactly one reason: a calendar hand that takes ISO
    # stamps cannot be filled in by a model that does not know what day it is. "Tuesday"
    # is not a date; "tomorrow at four" is not a date; both are things an employer says
    # every day. Without this line the model must either guess a year or refuse, and
    # guessing a year puts a meeting in the wrong one on the employer's real phone.
    now = time.localtime()
    lines.append(
        "  RIGHT NOW IT IS %s, and your timezone offset is %s. Times you are given as "
        "\"start\" or \"end\" must be written as ISO-8601 - 2026-09-28T16:00 for an hour, "
        "or 2026-09-28 on its own for a whole day - and worked out from that clock: "
        "\"tomorrow\", \"Tuesday\" and \"in an hour\" are all resolvable from it, so "
        "resolve them rather than passing the words through. If they name an hour with no "
        "day, it is today unless that hour has already gone, in which case it is "
        "tomorrow. Leave \"end\" out when they did not give one; the server says half an "
        "hour out loud rather than inventing a length quietly."
        % (time.strftime("%A %d %B %Y at %H:%M", now), time.strftime("%z", now) or "local"))
    lines.append(
        "  If, and ONLY if, they have just asked you to do one of those things, do not "
        "answer in prose. Reply with nothing but a control tag naming the tool and the "
        "details you were given, as JSON: "
        "[[tool: add_calendar_event | {\"title\": \"call the client\", \"start\": "
        "\"%s\"}]]. Use the id exactly as written above; the server checks it "
        % time.strftime("%Y-%m-%dT16:00", now)
        # One element, not two: lines are joined with newlines, and a newline dropped in
        # here would cut the sentence in half in the middle of a clause.
        + "against the tools it really has and refuses rather than guessing, so never "
        "invent one and never reach for a near neighbour. Fill in only what they told "
        "you - never invent an address, a time or a recipient, and if a required detail "
        "is genuinely missing, ask for that one thing in prose instead.\n"
        "  NOTHING HAPPENS WHEN YOU DO THIS. The server puts the request to them, in its "
        "own words, and waits for a yes. So never say that you have done it, never "
        "mention the tag, and never promise to do it later.\n"
        "  AND A REQUEST TO DRAFT IS STILL A REQUEST. \"draft an email to her saying I am "
        "fine\", \"write to that address\", \"put something in my calendar for Tuesday\" "
        "all name one of the tools above, and the tag is how they get their draft: the "
        "server shows them every detail you filled in and sends nothing until they say "
        "yes. Writing the letter out in prose instead leaves them holding words they "
        "cannot send, which is the one outcome they did not ask for.")
    return "\n".join(lines), chain_protocol()


def chain_protocol():
    """THE CHAIN PROTOCOL, taught alongside the single tag and never instead of it.

    Three sentences carry the whole of it and each was measured before it was written:

      THE SHAPE. A JSON array of {"hand", "params"} objects, which is the shape the mandate
        names. The example is a real one, with a real clock in it, for the same reason the
        single tag's example has one.
      ONE INTENT IS NOT A CHAIN. Without this sentence a model that has just been taught a
        new toy reaches for it, and a chain of one is a proposal with extra ceremony - a
        second card shape, a second executor and a second receipt for work the ordinary path
        already does. Measured after this sentence was added: 6 single-intent directives out
        of 6 still came back as ordinary [[tool: ]] tags and none as a chain of one.
      STEP N MAY USE STEP N-1, in a {{stepN}} placeholder, and ONLY inside a long text
        field. The model is told the restriction rather than left to discover it, because
        propose_chain() refuses a placeholder in an address by name and a refusal the model
        could have avoided is a turn wasted on both sides.

    WHAT IT DOES NOT SAY. It does not describe the Chain Card, the halt law or the ledger.
    The model is being asked for a plan, not for a user interface, and every sentence about
    what the server will do with the plan is a sentence it can get wrong out loud.
    """
    return (
        "  AND A DIRECTIVE MAY CONTAIN MORE THAN ONE. \"add a meeting and email the team\", "
        "\"put it in the calendar then write to Tom\" name TWO of the things above in one "
        "breath. When, and only when, the one message genuinely asks for more than one of "
        "them, reply with nothing but a chain tag: a JSON array of steps, in the order they "
        "must happen, using \"hand\" for the id and \"params\" for the details.\n"
        "  [[chain: [{\"hand\": \"add_calendar_event\", \"params\": {\"title\": \"Vendor "
        "call\", \"start\": \"%s\"}}, {\"hand\": \"send_email\", \"params\": {\"to\": "
        "\"team@example.com\", \"subject\": \"Vendor call\", \"body\": \"I have put the "
        "vendor call in the diary. {{step1}}\"}}]]\n"
        "  Every id must be one of the ids above, at most %d steps, and the same rules apply "
        "to each step as to a single one: fill in only what they told you, and if a required "
        "detail for ANY step is genuinely missing, ask for that one thing in prose instead "
        "of guessing it.\n"
        "  ONE INTENT IS NOT A CHAIN. A message that asks for a single thing gets the "
        "ordinary [[tool: ...]] tag, never this one.\n"
        "  STEP N MAY USE STEP N-1. Write {{stepN}} where an earlier step's result belongs - "
        "only ever inside a long text field such as a body or a description, and never in an "
        "address, a subject, a title or a time. The server fills it in after that step has "
        "actually succeeded, and shows them the placeholder before they say yes.\n"
        "  NOTHING HAPPENS WHEN YOU DO THIS EITHER. They are shown the numbered plan and "
        "asked once for the whole of it."
        % (time.strftime("%Y-%m-%dT16:00"), CHAIN_MAX_STEPS))


def hands_wanted(text):
    """Is this message worth offering the brain a chance to ask for hands?

    A door, not a decision. It answers "might this be an instruction rather than a
    question?" and nothing else: which tool - if any - is the brain's judgement, made
    against the capability sentences and resolved by find() exactly. That separation is
    the point. A regex that chose the tool would be the nearest-name fallback this whole
    module refuses to have.
    """
    said = str(text or "")
    if not said.strip():
        return False
    return any(pattern.search(said)
               for tool in registry() for pattern in tool["triggers"])


# ------------------------------------------------------------------ the proposal

def tool_tag(answer):
    """(id or None, raw params text or None, the answer with the tag stripped)."""
    text = str(answer or "")
    found = TOOL_TAG_RE.search(text)
    if not found:
        return None, None, text
    stripped = re.sub(r"\s{2,}", " ", TOOL_TAG_RE.sub("", text)).strip()
    return found.group(1).strip(), found.group(2), stripped


def chain_tag(answer):
    """(steps or None, why, the answer with the tag stripped).

    THE ONE THING THIS IS NOT IS A REGEX, and that is a measurement rather than a taste. See
    the note on CHAIN_TAG_AT: the tag closes with "]]" and a JSON array closes with "]", so
    the model writes "}}]]" and a pattern demanding "]]]" reads nothing at all - 0 chains out
    of 5 on the first probe, 6 out of 6 once the scan below replaced it, every one of the six
    having written a single "]".

    So json's own scanner decides where the array ends and the leftover is only asked to
    begin with a "]". That leniency costs nothing, because nothing here is trusted: every
    step is looked up in the registry exactly and validated against its schema in
    propose_chain(). The safety is in find() and validate(), never in the bracket count.

    `why` is for the trace and is never spoken: it says what shape arrived, not what was in
    it, in this file's usual habit that model text does not reach disk.
    """
    said = str(answer or "")
    at = CHAIN_TAG_AT.search(said)
    if not at:
        return None, "", said
    start = said.find("[", at.end() - 1)
    if start < 0:
        return None, "a chain tag with no array after it", said
    try:
        value, ends = _DECODER.raw_decode(said, start)
    except ValueError:
        # The reason is not carried: it quotes the text it failed on, and the text came
        # from a language model.
        return None, "the array would not parse", said
    if not isinstance(value, list):
        return None, "the chain tag carried a %s and not an array" % type(value).__name__, said
    if not said[ends:].lstrip().startswith("]"):
        return None, "the array was not inside a closed tag", said
    # Everything from the tag's opening bracket to the last of the closing ones comes out,
    # so the prose - if the model sent any, which it is told not to - reads cleanly.
    tail = ends + (len(said[ends:]) - len(said[ends:].lstrip()))
    while tail < len(said) and said[tail] == "]":
        tail += 1
    stripped = re.sub(r"\s{2,}", " ", said[:at.start()] + said[tail:]).strip()
    return value, "%d step(s)" % len(value), stripped


# THE CLEAN MOUTH, section 26 PART 2. Any tag that escapes chain_tag()'s four refusal
# paths still ends up in prose, and prose is what the employer reads and the voice reads
# out. chain_tag() was written to DECIDE and it returns `said` untouched whenever it
# declines - which is correct for a decision and wrong for a mouth, and the ordinary answer
# path in server.py compounded it: it records that a chain tag was seen and then never
# takes it out, so a model that wrote a plan while answering a question about the notes had
# [[chain: [{"hand": ... reach the answer surface verbatim.
#
# WHAT IT REMOVES IS THE PROTOCOL AND NOTHING ELSE, and the control is the point: an answer
# that is legitimately ABOUT JSON must still show its braces. So there is no blanket sweep
# of "{{", "}}" or bracketed arrays. Four shapes come out, each of which only this protocol
# produces:
#   a chain tag, however it terminates - including not at all (truncated JSON);
#   a tool tag that TOOL_TAG_RE could not read, for the same reason;
#   a bare array of step objects with no tag around it, found by json's own scanner and
#     kept only if it really is a list of dicts carrying "hand" - the array-without-tag case;
#   a {{stepN}} placeholder, which is addressed to the runner and means nothing to a reader.
# A sentence containing [{"a": 1}] has no "hand" key, no tag and no {{stepN}}, and leaves
# here byte-identical. That is asserted rather than described, in chain_proof's fuzz set.
CHAIN_TAG_ANY = re.compile(r"\[\[\s*chain\s*:.*?(?:\]\]+|\Z)", re.I | re.S)
TOOL_TAG_ANY = re.compile(r"\[\[\s*tool\s*:.*?(?:\]\]+|\Z)", re.I | re.S)


def _hand_arrays(text):
    """(start, end) for every bare JSON array of step objects. json decides the extent."""
    spans, at = [], 0
    while True:
        at = text.find("[", at)
        if at < 0:
            return spans
        try:
            value, ends = _DECODER.raw_decode(text, at)
        except ValueError:
            at += 1
            continue
        if (isinstance(value, list) and value
                and all(isinstance(one, dict) and "hand" in one for one in value)):
            spans.append((at, ends))
            at = ends
        else:
            at += 1


def clean_mouth(text):
    """The answer with the chain protocol taken out of it, and nothing else touched.

    Returns "" if the text was nothing BUT protocol - the caller substitutes a line, because
    an empty answer surface is its own bug and this function must not be the one guessing
    which sentence belongs there.
    """
    said = str(text or "")
    said = CHAIN_TAG_ANY.sub(" ", said)
    said = TOOL_TAG_ANY.sub(" ", said)
    for start, ends in reversed(_hand_arrays(said)):
        said = said[:start] + " " + said[ends:]
    said = STEP_REF_RE.sub(" ", said)
    return re.sub(r"\s{2,}", " ", said).strip()


def readings(params):
    """The DERIVED blanks: a human sentence for values that are machine stamps.

    Keyed on parameter NAMES, not on tool ids, and computed from the validated
    parameters by the very function the script will use - google_api.event_times - so the
    sentence the employer approves and the body that goes to Google cannot disagree about
    what time the thing is. That is the whole reason this exists rather than a second
    formatter living in the registry.

    These never enter params, which means they never reach the script, never reach the
    rows the page renders verbatim, and never reach the ledger. They are sentence
    furniture. A failure to derive one is silent on purpose: the blank is then left
    standing in the proposal, visible, and the proposal still happens - losing the whole
    question because a date was odd would be worse than showing a human a stray {when},
    and the script re-checks the stamps itself before anything is sent.
    """
    out = {}
    if "start" in params:
        try:
            import google_api
            _s, _e, when, duration, err = google_api.event_times(params.get("start", ""),
                                                                 params.get("end", ""))
            if err:
                out["_refusal"] = err
            else:
                out["when"] = when
                out["duration"] = duration
        except Exception:
            # The reading is furniture; losing it must not lose the proposal. An import
            # that failed here leaves the blanks standing rather than refusing, because a
            # broken module is not the employer's mistake and the script checks again.
            pass
    # THERE IS NO {preview} HERE, AND THAT IS A DELIBERATE OMISSION WITH A TEST BEHIND IT.
    # A 200-character preview of the email body was written here first, and the registry's
    # proposal sentence read it out: "...and it reads: 'Dear Tom, about the numbers...'".
    # Preflight check 16 clause (f) caught it within the hour. That clause plants a fresh
    # canary string in send_email's BODY and fails if the canary turns up in the spoken
    # line, because `line` is not a caption - speakLine() says it out loud, and an email
    # body is the one parameter here that can be nobody else's business. A machine that
    # reads your correspondence aloud to whoever is standing in the room has picked the
    # wrong half of a trade nobody offered it.
    # The body is still shown - on the CARD, in the rows, in full and verbatim, which is
    # more than a truncated preview and is the copy that actually travels. So the employer
    # reads what they are approving with their eyes, and the room hears only who it is to
    # and what it is about.
    return out


def _fill(template, params):
    """The registry's sentence with {blanks} filled from validated parameters only.

    Not str.format: a parameter whose value contains a brace would raise, an unknown
    blank would raise, and neither of those is a reason to lose a proposal. Only the
    names the schema declared are substituted - plus the derived readings above;
    anything else is left standing, visible, where a human will notice the template is
    wrong.
    """
    def swap(match):
        key = match.group(1)
        return str(params[key]) if key in params else match.group(0)
    return re.sub(r"\{([a-z0-9_]{1,32})\}", swap, str(template or ""))


def validate(tool, raw):
    """(params, refusal) - the schema is the shape, and nothing else gets through.

    Extra keys are dropped rather than passed on: the schema is the contract with the
    script, and a parameter the script never asked for is either a model's invention or
    somebody's experiment. Both are better dropped than forwarded.
    """
    if not isinstance(raw, dict):
        return None, dict(key="unreadable", line=LINES["unreadable"])
    params = {}
    for spec in tool["params"]:
        name, kind = spec["name"], spec["type"]
        if name not in raw or raw[name] is None or (isinstance(raw[name], str)
                                                   and not raw[name].strip()):
            if spec["required"]:
                # NAMED, because "I need more information" is useless to a human who
                # cannot see the schema.
                return None, dict(key="missing", field=name,
                                  line=LINES["missing"].format(field=name))
            continue
        value = raw[name]
        if kind in ("string", "text"):
            value = str(value).strip()[:4000 if kind == "text" else 400]
        elif kind == "integer":
            try:
                value = int(str(value).strip())
            except (TypeError, ValueError):
                return None, dict(key="badtype", field=name,
                                  line=LINES["badtype"].format(field=name,
                                                               type="whole number"))
        elif kind == "number":
            try:
                value = float(str(value).strip())
            except (TypeError, ValueError):
                return None, dict(key="badtype", field=name,
                                  line=LINES["badtype"].format(field=name, type="number"))
        elif kind == "boolean":
            text = str(value).strip().lower()
            if text in ("true", "yes", "1", "on"):
                value = True
            elif text in ("false", "no", "0", "off"):
                value = False
            else:
                return None, dict(key="badtype", field=name,
                                  line=LINES["badtype"].format(field=name,
                                                               type="yes or no"))
        params[name] = value
    return params, None


def _public(slot, now=None):
    """The pending proposal as the page may see it - including the exact parameters.

    They travel because the human is about to approve them and must be able to READ
    them; the moment of trust is a thing you should be able to look at. They do not
    travel to the ledger, to the log, or into any spoken line.
    """
    if not slot:
        return None
    now = time.monotonic() if now is None else now
    out = {"id": slot["id"], "tool": slot["tool"], "name": slot["name"],
           "line": slot["line"], "params": dict(slot["params"]),
           "fields": [dict(p) for p in slot["fields"]],
           "ttlS": CONFIRM_TTL_S,
           "expiresInS": max(0, int(round(slot["expires"] - now)))}
    # A CHAIN CARRIES ITS STEPS AND KEEPS EVERY KEY ABOVE. `tool` is the first step's real
    # registry id rather than the word "chain", and that is load-bearing in three places that
    # know nothing about chains: _record() drops an outcome for an id the registry does not
    # have, so a chain named "chain" would have been refused and lapsed into silence; the
    # page's status strip reads it; and about_the_proposal() logs it. `params` and `fields`
    # stay EMPTY so that a card rendering the single-proposal rows for a chain shows nothing
    # at all rather than step one's parameters passed off as the whole plan.
    if slot.get("steps"):
        out["chain"] = True
        out["chainId"] = slot["chainId"]
        out["steps"] = [{"n": i + 1, "tool": s["tool"], "name": s["name"], "line": s["line"],
                         "params": dict(s["params"]),
                         "fields": [dict(f) for f in s["fields"]],
                         "uses": list(s["uses"])}
                        for i, s in enumerate(slot["steps"])]
    return out


def _reply(status, ok, line, **extra):
    payload = {"ok": ok, "kind": "tool", "nodes": [], "answer": line}
    payload.update(extra)
    if "pending" not in payload:
        with _lock:
            payload["pending"] = _public(_pending)
    return status, payload


def _log(fmt, *args):
    """The trace, and it may say what happened but never what it was given."""
    sys.stderr.write("  tool: " + (fmt % args if args else fmt) + "\n")


def _drop_for_refusal():
    """A refused proposal leaves the slot EMPTY, even of whatever was in it before.

    The alternative was to leave an older, valid proposal standing - and that is the one
    shape this must never have: a refusal is a confusing moment, and a "yes" spoken into
    a confusing moment must not be able to confirm something the employer had stopped
    thinking about. Losing a proposal costs them one sentence. The other way costs them
    an email.
    """
    global _pending
    with _lock:
        slot = _pending
        _pending = None
    if slot:
        _record_slot(slot, "lapsed")
        _log("proposal %s let go alongside a refusal", slot["tool"])


def propose(tool_id, params_text, door="tag"):
    """(status, payload). One pending proposal at a time, spoken in the registry's words.

    Every refusal below leaves NOTHING pending, which is the only safe direction for a
    refusal to fail in: a half-understood request left sitting in the slot is a request
    that a later "yes" could confirm.
    """
    global _pending, _seq
    if not registry():
        return _reply(409, False, LINES["noregistry"], refused="no-registry",
                      pending=None)
    tool = find(tool_id)
    if tool is None:
        # The id is not echoed back and not logged. It arrived from a language model,
        # and this file's habit is that model text does not reach disk.
        _drop_for_refusal()
        _log("proposal refused: no such tool id (%d characters), nothing pending",
             len(str(tool_id or "")))
        return _reply(404, False, LINES["unknown"], refused="unknown-tool", pending=None)
    if tool.get("doors") and str(door or "") not in tool["doors"]:
        # A DOOR-BOUND HAND ASKED FOR THROUGH ANOTHER DOOR - a tag, almost always, naming a tool
        # the brain was never told about. Refused in the same words as an unknown id, because
        # from the brain's side of the glass that is exactly what it is.
        _drop_for_refusal()
        _log("proposal refused: %s is not taken through the %s door, nothing pending",
             tool["id"], str(door or "")[:12])
        _record(tool["id"], "refused")
        return _reply(403, False, LINES["unknown"], refused="wrong-door", tool=tool["id"],
                      pending=None)

    if params_text is None or str(params_text).strip() in ("", "{}"):
        raw = {}
    elif isinstance(params_text, dict):
        raw = params_text
    else:
        try:
            raw = json.loads(str(params_text))
        except ValueError:
            _drop_for_refusal()
            _log("proposal refused: %s parameters would not parse", tool["id"])
            _record(tool["id"], "refused")
            return _reply(400, False, LINES["unreadable"], refused="unreadable-params",
                          tool=tool["id"], pending=None)

    params, refusal = validate(tool, raw)
    if refusal is not None:
        _drop_for_refusal()
        _log("proposal refused: %s %s%s", tool["id"], refusal["key"],
             " (%s)" % refusal["field"] if refusal.get("field") else "")
        _record(tool["id"], "refused")
        return _reply(400, False, refusal["line"], refused=refusal["key"],
                      field=refusal.get("field"), tool=tool["id"], pending=None)

    derived = readings(params)
    if derived.get("_refusal"):
        # A TIME THAT CANNOT BE READ IS A REFUSAL, NOT A CARD. The alternative was a
        # proposal reading "That would be 'nonsense', {when}, {duration}" which the
        # employer would approve and the script would then reject - one wasted click and
        # one confusing sentence to reach a refusal we could already see coming. The
        # script keeps its own check regardless: it can be run by hand.
        _drop_for_refusal()
        _log("proposal refused: %s unreadable time, nothing pending", tool["id"])
        _record(tool["id"], "refused")
        # A colon and not a dash: two of the reasons contain a dash of their own, and
        # "the calendar, sir - the start and the end are not the same kind of time - one
        # is a whole day" is a sentence a listener has to re-read.
        return _reply(400, False, "I cannot put that in the calendar, sir: %s."
                      % derived["_refusal"], refused="badtime", field="start",
                      tool=tool["id"], pending=None)
    # dict(params, **derived) and not params.update(derived): the derived blanks must not
    # be in the dict that goes into the slot, because that dict is what the script
    # receives on stdin and what the page renders as rows.
    line = _fill(tool["proposal"], dict(params, **derived))
    with _lock:
        superseded = _pending
        _seq += 1
        _pending = {"id": "%x-%d" % (int(time.time()), _seq), "tool": tool["id"],
                    "name": tool["name"], "params": params, "line": line,
                    "fields": tool["params"], "door": str(door or "tag")[:12],
                    "made": time.monotonic(),
                    "expires": time.monotonic() + CONFIRM_TTL_S}
        slot = _public(_pending)
    if superseded:
        # A new proposal lapses the old one with a single line, prepended to the new
        # question rather than spoken on its own: two sentences, one utterance.
        _record_slot(superseded, "lapsed")
        _log("proposal %s superseded by %s", superseded["tool"], tool["id"])
        line = LINES["superseded"] + " " + line
        slot["line"] = line
    _log("proposal %s (%d parameter%s validated) awaiting a word, %ds",
         tool["id"], len(params), "" if len(params) == 1 else "s", CONFIRM_TTL_S)
    return _reply(200, True, line, pending=slot, proposed=tool["id"],
                  superseded=bool(superseded))


def _step_refs(params, fields, at):
    """(uses, refusal) - which earlier steps this one quotes, and where it may quote them.

    THE ONE PLACE STATE PASSING IS BOUNDED, and it needs bounding because it is the single
    deliberate exception to this file's oldest rule: "the parameters come from the SLOT, never
    from the request that confirms it - no door can substitute a recipient between the asking
    and the doing." A {{step1}} is, precisely, a substitution between the asking and the
    doing. So it is allowed in exactly one place and refused everywhere else.

      ONLY INTO A `text` FIELD. Not a taste - a consequence. Across the whole registry the
        `text` fields are body, description and minutes; every address, subject, title, time,
        token and voice is a `string`. So "a placeholder may only land in a text field" and
        "a recipient can never be substituted" are the same sentence, and the second one is
        checkable by reading the schema rather than by trusting this function.
      ONLY BACKWARDS. Step 2 may quote step 1. A step that quotes itself or a later step
        cannot be satisfied at all, and a plan that cannot be satisfied must be refused while
        there is still a human reading it, not halfway through with one hand already run.
      AND IT IS VISIBLE BEFORE THE YES. The placeholder is not expanded here: it stays in the
        params, so the card shows "{{step1}}" in the body and the employer can see that a
        value they have not read yet will be pasted there. A silent expansion at run time
        would be this machine editing a letter after it was approved.
    """
    kinds = {f["name"]: f["type"] for f in fields}
    uses = set()
    for name, value in params.items():
        found = STEP_REF_RE.findall(str(value))
        if not found:
            continue
        if kinds.get(name) != "text":
            return None, dict(key="ref-field", field=name, at=at,
                              line=LINES["chainreffield"].format(at=at, field=name))
        for digits in found:
            n = int(digits)
            if not 1 <= n < at:
                return None, dict(key="ref-order", at=at, to=n,
                                  line=LINES["chainref"].format(at=at, to=n))
            uses.add(n)
    return sorted(uses), None


def _plan_words(n):
    return {2: "two-step", 3: "three-step", 4: "four-step"}.get(n, "%d-step" % n)


_ORDINALS = ("", "First", "Second", "Third", "Fourth")


def propose_chain(steps, door="tag", facts=None):
    """(status, payload). A plan of two or more hands in the ONE slot, behind ONE word.

    `facts` is the caller's chance to overwrite the parameters the SERVER is the authority on
    - tool_facts() in server.py, which knows which voice is currently speaking. It is passed
    in rather than imported so that this file keeps knowing nothing about that one, and it is
    applied PER STEP, because a chain that ended in set_voice would otherwise read the current
    voice off nowhere.

    A CHAIN OF ONE IS NOT A CHAIN. One step falls through to propose(), which is the mandate's
    own rule and is also the only way the existing card, receipt and ledger row stay the
    normal case rather than a special case of a bigger thing.

    EVERY REFUSAL BELOW LEAVES NOTHING PENDING, exactly as propose()'s do, and for the same
    reason: a half-understood plan left sitting in the slot is a plan a later "yes" could
    confirm. Each one also names the STEP NUMBER, because a plan is the one refusal where "it
    would not work" is genuinely ambiguous about which part.
    """
    global _pending, _seq
    if not registry():
        return _reply(409, False, LINES["noregistry"], refused="no-registry", pending=None)
    if not isinstance(steps, list) or not steps:
        _drop_for_refusal()
        _log("chain refused: no steps, nothing pending")
        return _reply(400, False, LINES["chainempty"], refused="chain-empty", pending=None)
    if len(steps) > CHAIN_MAX_STEPS:
        _drop_for_refusal()
        _log("chain refused: %d steps, over the cap of %d", len(steps), CHAIN_MAX_STEPS)
        return _reply(400, False, LINES["chainlong"].format(n=len(steps),
                                                            max=CHAIN_MAX_STEPS),
                      refused="chain-too-long", pending=None)
    if len(steps) == 1:
        one = steps[0] if isinstance(steps[0], dict) else {}
        _log("chain of one: falling through to the ordinary proposal")
        raw = one.get("params")
        return propose(one.get("hand") or one.get("tool"),
                       facts(one.get("hand") or one.get("tool"), raw) if facts else raw,
                       door=door)

    built = []
    for index, raw_step in enumerate(steps, 1):
        if not isinstance(raw_step, dict):
            _drop_for_refusal()
            _log("chain refused: step %d is not an object", index)
            return _reply(400, False, LINES["chainbadstep"].format(at=index),
                          refused="chain-bad-step", at=index, pending=None)
        wanted = raw_step.get("hand") or raw_step.get("tool")
        tool = find(wanted)
        if tool is not None and tool.get("doors"):
            tool = None     # a door-bound hand is never a step: a plan is a model's composition
        if tool is None:
            # The id is not echoed and not logged, in this file's habit: it came from a model.
            _drop_for_refusal()
            _log("chain refused: step %d names no tool this registry has", index)
            return _reply(404, False, LINES["chainunknown"].format(at=index),
                          refused="chain-unknown-tool", at=index, pending=None)
        raw = raw_step.get("params")
        if isinstance(raw, str):
            try:
                raw = json.loads(raw) if raw.strip() else {}
            except ValueError:
                _drop_for_refusal()
                _log("chain refused: step %d parameters would not parse", index)
                return _reply(400, False, LINES["chainbadstep"].format(at=index),
                              refused="chain-bad-step", at=index, pending=None)
        if raw is None:
            raw = {}
        if facts:
            raw = facts(tool["id"], raw)
            if isinstance(raw, str):
                try:
                    raw = json.loads(raw) if raw.strip() else {}
                except ValueError:
                    raw = {}
        params, refusal = validate(tool, raw)
        if refusal is not None:
            _drop_for_refusal()
            _log("chain refused: step %d %s %s%s", index, tool["id"], refusal["key"],
                 " (%s)" % refusal["field"] if refusal.get("field") else "")
            _record(tool["id"], "refused")
            return _reply(400, False,
                          LINES["chainstep"].format(at=index, why=refusal["line"]),
                          refused="chain-step-" + refusal["key"], at=index,
                          field=refusal.get("field"), tool=tool["id"], pending=None)
        uses, refusal = _step_refs(params, tool["params"], index)
        if refusal is not None:
            _drop_for_refusal()
            _log("chain refused: step %d %s", index, refusal["key"])
            return _reply(400, False, refusal["line"],
                          refused="chain-" + refusal["key"], at=index,
                          field=refusal.get("field"), pending=None)
        # THE DERIVED READINGS, per step, and a bad time is still a refusal rather than a
        # card - the same judgement propose() makes, at the step that made it. A plan whose
        # second entry is at "nonsense o'clock" must not be approvable, because the employer
        # would be approving a first step that runs and a second that was never going to.
        derived = readings(params)
        if derived.get("_refusal"):
            _drop_for_refusal()
            _log("chain refused: step %d unreadable time", index)
            _record(tool["id"], "refused")
            return _reply(400, False,
                          LINES["chainstep"].format(
                              at=index, why="I cannot read that time: %s."
                                            % derived["_refusal"]),
                          refused="chain-step-badtime", at=index, field="start",
                          tool=tool["id"], pending=None)
        built.append({"tool": tool["id"], "name": tool["name"], "params": params,
                      "line": _fill(tool["step"], dict(params, **derived)),
                      "fields": tool["params"], "uses": uses})

    # THE ONE SPOKEN SENTENCE. Composed from the registry's step templates, never from the
    # model's prose, for the reason the single proposal is: a model that paraphrases an
    # action can understate it, and a model paraphrasing TWO actions has twice the room.
    # The step lines carry no body, no minutes and no description - see _clean_tool - so
    # this sentence can be said out loud in a room with other people in it.
    spoken = "I have a %s plan, sir. %s Shall I execute the chain?" % (
        _plan_words(len(built)),
        " ".join("%s, %s" % (_ORDINALS[i + 1] if i + 1 < len(_ORDINALS) else "Then",
                            step["line"][:1].lower() + step["line"][1:])
                 for i, step in enumerate(built)))
    with _lock:
        superseded = _pending
        _seq += 1
        ident = "%x-%d" % (int(time.time()), _seq)
        _pending = {"id": ident, "chain": True, "chainId": "c%s" % ident,
                    "tool": built[0]["tool"],
                    "name": "A %s plan" % _plan_words(len(built)),
                    "params": {}, "fields": [], "steps": built, "line": spoken,
                    "door": str(door or "tag")[:12], "made": time.monotonic(),
                    "expires": time.monotonic() + CONFIRM_TTL_S}
        slot = _public(_pending)
    if superseded:
        _record_slot(superseded, "lapsed")
        _log("proposal %s superseded by a chain", superseded["tool"])
        spoken = LINES["superseded"] + " " + spoken
        slot["line"] = spoken
    _log("chain %s of %d steps (%s) awaiting one word, %ds", slot["chainId"], len(built),
         " -> ".join(s["tool"] for s in built), CONFIRM_TTL_S)
    return _reply(200, True, spoken, pending=slot,
                  proposed=[s["tool"] for s in built], chain=True,
                  chainId=slot["chainId"], superseded=bool(superseded))


# -------------------------------------------------------------- the confirmation

def is_confirmation(text):
    return bool(YES_RE.match(str(text or "")))


def is_refusal(text):
    return bool(NO_RE.match(str(text or "")))


def pending_public():
    with _lock:
        return _public(_pending)


def lapse_if_due():
    """(status, payload) if a proposal has just run out of time, else (None, None).

    Idempotent by construction: the slot is emptied under the lock before the line is
    composed, so two tabs asking at once produce exactly one lapse, counted once and
    spoken once. A lapse nobody is there to hear still empties the slot - which is the
    part that matters.
    """
    global _pending
    with _lock:
        slot = _pending
        if not slot or time.monotonic() < slot["expires"]:
            return None, None
        _pending = None
    _record_slot(slot, "lapsed")
    _log("proposal %s lapsed unanswered after %ds", slot["tool"], CONFIRM_TTL_S)
    return _reply(200, True, LINES["lapsed"], lapsed=slot["tool"], pending=None)


def clear_pending(reason="reset"):
    """The forget button, and anything else that means "none of this happened"."""
    global _pending
    with _lock:
        slot = _pending
        _pending = None
    if not slot:
        return False
    _record_slot(slot, "lapsed")
    _log("proposal %s cleared (%s)", slot["tool"], reason)
    return True


def cancel(door="button", proposal_id=None):
    """No. The one outcome that is always available and always free."""
    global _pending
    with _lock:
        slot = _pending
        if slot and proposal_id and slot["id"] != proposal_id:
            slot = None                    # a stale tab answering an older question
        if slot:
            _pending = None
    if not slot:
        return _reply(409, False, LINES["nothing"], refused="nothing-pending",
                      pending=None)
    _record_slot(slot, "refused")
    _log("proposal %s refused at the %s door; nothing ran", slot["tool"], door)
    return _reply(200, True, LINES["refused"], refused="by-hand", tool=slot["tool"],
                  door=door, pending=None)


def withdraw():
    """A changed subject is a withdrawal. Returns the line to prepend, or "".

    Called by /chat for any message that is neither a yes nor a no while something is
    pending. The employer is not interrupted or asked again: their new question is
    answered, with one sentence in front of it saying what was let go.
    """
    global _pending
    with _lock:
        slot = _pending
        if not slot:
            return ""
        _pending = None
    _record_slot(slot, "lapsed")
    _log("proposal %s withdrawn: the subject changed", slot["tool"])
    return LINES["withdrawn"]


# ----------------------------------------------------------------- the execution

def _evidence(text):
    line = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", " ", str(text or ""))
    line = re.sub(r"\s*\n\s*", " ", line).strip()
    line = re.sub(r"\s{2,}", " ", line)
    if len(line) > EVIDENCE_MAX_CHARS:
        line = line[:EVIDENCE_MAX_CHARS].rsplit(" ", 1)[0] + "..."
    return line


def _spawn(tool, params):
    """Run ONE registry script. (key, text, exitCode, tookS), and it never raises.

    `key` is one of ok, missing-script, timeout, not-startable, exit-N, no-evidence, and it
    is the whole failure taxonomy of this file in one place. It was pulled out of execute()
    when the chain arrived, for a reason worth stating: a chain executor with a subprocess
    call of its own would have been a second place for this taxonomy to be got wrong, and a
    timeout classified as a success in that second place is an email sent on the strength of
    a calendar entry that never existed. One spawner, one set of outcomes, two callers.

    It records nothing and speaks nothing. The caller owns the ledger and the wording,
    because a single hand and a halted plan say very different things about the same exit
    code.
    """
    script = (TOOLS_DIR / tool["script"]) if tool else None
    if tool is None or not script.is_file():
        return "missing-script", "", None, 0.0
    body = json.dumps(params, ensure_ascii=False)
    started = time.monotonic()
    try:
        # _proc.run, so a hand runs without a console window of its own. python.exe is
        # a console program too, and every hand is one - the flash was not the voice's
        # alone.
        done = _proc.run(
            [sys.executable, str(script)], input=body,
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=tool["timeout_s"], shell=False, cwd=str(TOOLS_DIR))
    except subprocess.TimeoutExpired:
        return "timeout", "", None, time.monotonic() - started
    except OSError as exc:
        return "not-startable", type(exc).__name__, None, time.monotonic() - started
    took = time.monotonic() - started
    out, err = _evidence(done.stdout), _evidence(done.stderr)
    if done.returncode != 0:
        # The reason it OBSERVED, in this order of preference: what the script said on
        # stdout, what it said on stderr, and failing both, the exit code. Never an
        # invented explanation.
        return ("exit-%d" % done.returncode,
                out or err or "it exited with status %d" % done.returncode,
                done.returncode, took)
    if not out:
        # A hand that fails silently is worse than no hand, and a success claimed with no
        # evidence is worse still.
        return "no-evidence", "", 0, took
    return "ok", out, 0, took


def _sentence(text):
    """A script's line, terminated, so a receipt of several of them can be read aloud.

    A hand's stdout is its own words and is not edited here beyond this: the receipt for a
    two-step plan joins two of them, and "Self test passed, token A Self test passed, token
    B" is one sentence to a listener and two facts to the machine.
    """
    line = str(text or "").strip()
    return line if not line or line[-1] in ".!?:" else line + "."


def _paste(params, fields, results):
    """Fill {{stepN}} from what step N actually printed. (params, pasted).

    THE SUBSTITUTION HAPPENS HERE AND NOWHERE ELSE, and it happens AFTER the step it quotes
    has succeeded - which is the whole of the state-passing contract:

      only into a `text` field, re-checked here rather than trusted from _step_refs(). The
        check at proposal time is what tells the employer early; this one is what makes it
        true. Two checks of one rule, and the cheap one is not the one that matters.
      only from a step that RAN. A placeholder for a step that halted is never reached,
        because the chain stops - but a placeholder for a step that somehow left no evidence
        resolves to nothing rather than to the literal "{{step2}}", so a body cannot go out
        with this machine's own markup in it.
      and capped at CHAIN_PASTE_MAX, because a letter that is mostly another program's
        stdout is not a letter the employer wrote.
    """
    kinds = {f["name"]: f["type"] for f in fields}
    out, pasted = dict(params), 0

    def swap(match):
        nonlocal pasted
        pasted += 1
        text = str(results.get(int(match.group(1)), "")).strip()
        if len(text) > CHAIN_PASTE_MAX:
            text = text[:CHAIN_PASTE_MAX].rsplit(" ", 1)[0] + "..."
        return text

    for name, value in params.items():
        if kinds.get(name) != "text" or not isinstance(value, str):
            continue
        out[name] = STEP_REF_RE.sub(swap, value)
    return out, pasted


def _run_chain(slot, door):
    """THE HALT LAW. Step by step, in order, and the first failure is the last thing tried.

    Called from execute() with the slot already claimed and _running already set, so every
    guard the single path has is behind this one too.

    WHAT HALTING MEANS, exactly: step N+1 is never STARTED. Not started and abandoned, not
    started and its result discarded - _spawn is not called for it at all, which is the only
    version of this law that is worth anything when step 2 is send_email. The assertion that
    proves it in chain_proof.mjs is a ledger count that does not move, because a count that
    does not move is evidence a subprocess did not run, and a log line saying "skipped" is
    only evidence that a log line was written.

    AND THE RECEIPT NAMES BOTH HALVES. "The calendar entry is in but the email failed" is two
    facts, and a receipt that gave only the second would leave the employer thinking nothing
    happened when something did - which is worse than the failure, because the failure is
    recoverable and a wrong belief about the calendar is not.

    The succeeded steps are named in the SCRIPTS' OWN WORDS - their stdout, which is this
    file's only admissible evidence - rather than in a past tense of the registry's step
    line. A sentence composed from the template would read "the calendar entry is in" whether
    it was in or not; the script's own line cannot, because the script is the thing that put
    it there.
    """
    steps = slot["steps"]
    ids = [s["tool"] for s in steps]
    results, done, halted = {}, [], None
    for index, step in enumerate(steps, 1):
        tool = find(step["tool"])
        params, pasted = _paste(step["params"], step["fields"], results)
        if pasted:
            _log("chain %s step %d: %d placeholder(s) filled from earlier evidence",
                 slot["chainId"], index, pasted)
        key, text, code, took = _spawn(tool, params)
        if key == "ok":
            _record(step["tool"], "ok", ran=True)
            results[index] = text
            done.append((index, step, text))
            _log("chain %s step %d/%d %s ok in %.1fs", slot["chainId"], index, len(steps),
                 step["tool"], took)
            continue
        # THE HALT. Recorded, named, and the loop is left - so nothing below this step is
        # spawned, and the ledger's count for those tools does not move.
        _record(step["tool"], "failed")
        if key == "missing-script":
            why = LINES["noscript"]
        elif key == "timeout":
            why = LINES["timeout"].format(seconds=int(tool["timeout_s"]))
        elif key == "not-startable":
            why = LINES["crashed"].format(reason=text)
        elif key == "no-evidence":
            why = LINES["silent"]
        else:
            why = LINES["failed"].format(reason=text)
        halted = (index, step, key, code, why)
        _log("chain %s HALTED at step %d/%d (%s, %s); %d step(s) not attempted",
             slot["chainId"], index, len(steps), step["tool"], key, len(steps) - index)
        break

    if halted is None:
        _record_chain(slot["chainId"], "ok", ids, len(steps), 0)
        line = "All %d steps are done, sir. %s" % (
            len(steps), " ".join(_sentence(ev) for _n, _s, ev in done))
        return _reply(200, True, _evidence(line), chain=True, chainId=slot["chainId"],
                      ran=ids, steps=[{"n": n, "tool": s["tool"], "ok": True,
                                       "evidence": ev} for n, s, ev in done],
                      chainStatus="ok", stoppedAt=0, door=door, pending=None)

    at, step, key, code, why = halted
    _record_chain(slot["chainId"], "halted", ids, len(done), at)
    # THE ORDER OF THIS SENTENCE IS THE POINT: what DID happen, then what did not, then the
    # reason, then the fact that the rest was abandoned. A receipt that opened with the
    # failure would bury the calendar entry that is now really in the employer's diary.
    parts = []
    if done:
        parts.append(" ".join(_sentence(ev) for _n, _s, ev in done))
    else:
        parts.append("Nothing had run yet, sir.")
    # NAMED BY INDEX AND BY THE REGISTRY'S OWN NAME FOR IT. The index is what the ledger
    # recorded and what the card numbered; the name is what a human remembers approving.
    parts.append("Step %d of %d - %s - failed: %s" % (
        at, len(steps), step["name"].rstrip(".").lower(), _sentence(why)))
    rest = len(steps) - at
    parts.append("I have stopped the chain%s." % (
        ", so step%s %s %s not attempted" % (
            "" if rest == 1 else "s",
            " and ".join(str(n) for n in range(at + 1, len(steps) + 1)),
            "was" if rest == 1 else "were") if rest else ""))
    return _reply(502, False, _evidence(" ".join(parts)), chain=True,
                  chainId=slot["chainId"], chainStatus="halted", stoppedAt=at,
                  failed=key, tool=step["tool"], exitCode=code,
                  ran=[s["tool"] for _n, s, _e in done],
                  steps=([{"n": n, "tool": s["tool"], "ok": True, "evidence": ev}
                          for n, s, ev in done]
                         + [{"n": at, "tool": step["tool"], "ok": False, "evidence": why}]
                         + [{"n": n, "tool": steps[n - 1]["tool"], "ok": None,
                             "evidence": ""} for n in range(at + 1, len(steps) + 1)]),
                  door=door, pending=None)


def execute(door="button", proposal_id=None):
    """Run the pending proposal, and say exactly what the script said. Nothing else.

    The parameters come from the SLOT, never from the request that confirms it: a
    confirmation carries consent and nothing else, so no door - page, harness or stale
    tab - can substitute a recipient between the asking and the doing.

    A CHAIN IS RUN FROM HERE TOO, by delegation and not by a door of its own. Every guard
    above this line - the claim under the lock, the stale-id check, the TTL, the busy
    refusal - is written once and applies to a plan exactly as it applies to a hand, and the
    Doorman at the three doors that call this function is guarding both without having been
    told there is a second thing to guard. /chain/execute is a NAME for this, not a way
    round it.
    """
    global _pending, _running
    with _lock:
        busy, slot = _running, _pending
        if busy:
            still = _public(_pending)
        else:
            if slot and proposal_id and slot["id"] != proposal_id:
                slot = None                # a stale tab answering an older question
            if slot and time.monotonic() >= slot["expires"]:
                slot = None                # out of time: lapse_if_due() has it
            if slot:
                # Claimed under the same lock that emptied the slot, so a second
                # confirmation of this proposal cannot find it and cannot run it twice.
                _pending = None
                _running = slot["tool"]
    if busy:
        # Busy is not "queued". A second hand starting while the first is mid-flight is
        # how two calendar entries become three.
        _log("execute refused: %s is still running", busy)
        return _reply(409, False, LINES["busy"], refused="busy", running=busy,
                      pending=still)
    if not slot:
        status, payload = lapse_if_due()
        if payload is not None:
            return status, payload
        _log("execute refused: nothing was pending")
        return _reply(409, False, LINES["nothing"], refused="nothing-pending",
                      pending=None)

    try:
        if slot.get("steps"):
            return _run_chain(slot, door)
        tool = find(slot["tool"])
        key, text, code, took = _spawn(tool, slot["params"])
        if key == "missing-script":
            _record(slot["tool"], "failed")
            _log("run %s FAILED: script missing", slot["tool"])
            return _reply(502, False, LINES["noscript"], failed="missing-script",
                          tool=slot["tool"], pending=None)
        if key == "timeout":
            _record(tool["id"], "failed")
            _log("run %s FAILED: timed out after %.0fs", tool["id"], tool["timeout_s"])
            return _reply(504, False,
                          LINES["timeout"].format(seconds=int(tool["timeout_s"])),
                          failed="timeout", tool=tool["id"], pending=None)
        if key == "not-startable":
            _record(tool["id"], "failed")
            _log("run %s FAILED: %s", tool["id"], text)
            return _reply(502, False, LINES["crashed"].format(reason=text),
                          failed="not-startable", tool=tool["id"], pending=None)
        if key.startswith("exit-"):
            _record(tool["id"], "failed")
            _log("run %s FAILED in %.1fs (exit %s)", tool["id"], took, code)
            return _reply(502, False, LINES["failed"].format(reason=text),
                          failed=key, tool=tool["id"], exitCode=code, pending=None)
        if key == "no-evidence":
            _record(tool["id"], "failed")
            _log("run %s FAILED in %.1fs: exit 0 and nothing on stdout", tool["id"], took)
            return _reply(502, False, LINES["silent"], failed="no-evidence",
                          tool=tool["id"], exitCode=0, pending=None)
        _record(tool["id"], "ok", ran=True)
        _log("run %s ok in %.1fs, %d characters of evidence", tool["id"], took, len(text))
        return _reply(200, True, text, tool=tool["id"], ran=tool["id"], door=door,
                      exitCode=0, tookS=round(took, 2), pending=None)
    finally:
        with _lock:
            _running = None


def state():
    """For /tools and the instruments: the shape, never the substance."""
    with _lock:
        return {"pending": _public(_pending), "busy": _running,
                "ttlS": CONFIRM_TTL_S, "count": len(registry()),
                "registryError": _cache.get("error") or ""}


# -------------------------------------------------------------------- the ledger

def _blank():
    return {"ok": 0, "failed": 0, "refused": 0, "lapsed": 0, "last": ""}


def ledger():
    """Outcomes only, sanitised on the way in as well as on the way out.

    Read through a whitelist so that a hand-edited file cannot introduce a key, and
    keyed only by ids that are in the registry now - so a tool that has been retired
    stops being counted rather than leaving a name lying about on disk.
    """
    try:
        data = json.loads(LEDGER_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    rows = data.get("tools") if isinstance(data, dict) else None
    out = {}
    for tool in registry():
        row = rows.get(tool["id"]) if isinstance(rows, dict) else None
        clean = _blank()
        if isinstance(row, dict):
            for key in OUTCOMES:
                try:
                    clean[key] = max(0, int(row.get(key) or 0))
                except (TypeError, ValueError):
                    clean[key] = 0
            # A timestamp, and only if it looks like one. Anything else is dropped
            # rather than carried forward, because this field is the one string on
            # disk and a string is where things hide.
            stamp = str(row.get("last") or "")
            clean["last"] = stamp if re.fullmatch(
                r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", stamp) else ""
        out[tool["id"]] = clean
    return out


def chain_ledger():
    """The chain transactions, read through a whitelist exactly as the counts above are.

    WHAT IS IN A ROW AND WHY IT IS SAFE: a chain id, a status from a fixed tuple, the registry
    IDS of the steps, how many ran, the 1-based index it stopped at, and a timestamp. Every
    one of those is either an integer, a constant, or a name that is already public in GET
    /tools - so the privacy claim this ledger makes is unchanged and still checkable by
    reading the schema: there remains no key a recipient, a subject or a body could be put
    into. That was the test each field had to pass to be here, and `params` is the field that
    failed it.
    """
    try:
        data = json.loads(LEDGER_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    rows = data.get("chains") if isinstance(data, dict) else None
    known = {t["id"] for t in registry()}
    out = []
    for row in (rows if isinstance(rows, list) else ()):
        if not isinstance(row, dict):
            continue
        status = str(row.get("status") or "")
        if status not in CHAIN_STATUSES:
            continue
        ident = str(row.get("id") or "")
        if not re.fullmatch(r"c[0-9a-f]{1,16}-\d{1,9}", ident):
            continue
        steps = [s for s in (row.get("steps") or ()) if isinstance(s, str) and s in known]
        if not steps:
            continue
        stamp = str(row.get("at") or "")
        try:
            ran, stopped = int(row.get("ran") or 0), int(row.get("stopped") or 0)
        except (TypeError, ValueError):
            continue
        out.append({"id": ident, "status": status, "steps": steps,
                    "ran": max(0, min(ran, len(steps))),
                    "stopped": max(0, min(stopped, len(steps))),
                    "at": stamp if re.fullmatch(
                        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", stamp) else ""})
    return out[-CHAIN_LEDGER_MAX:]


def _record_chain(chain_id, status, step_ids, ran, stopped):
    """ONE ROW FOR ONE PLAN, which is the mandate's single transaction.

    It is written IN ADDITION to the per-tool counts, never instead of them: a hand that ran
    is a hand that ran, and a tools table that stopped counting the ones that ran inside a
    chain would make check 16's accounting quietly wrong in the safe-looking direction.
    """
    if status not in CHAIN_STATUSES:
        return
    rows = chain_ledger()
    rows.append({"id": str(chain_id)[:32], "status": status,
                 "steps": [str(s) for s in step_ids][:CHAIN_MAX_STEPS],
                 "ran": int(ran), "stopped": int(stopped),
                 "at": time.strftime("%Y-%m-%dT%H:%M:%S")})
    _write_ledger(ledger(), rows[-CHAIN_LEDGER_MAX:])


def _record_slot(slot, outcome):
    """An outcome for whatever is in the slot - one hand, or every hand in a plan.

    WHY EVERY HAND AND NOT JUST THE FIRST. A refused two-step plan refused two hands, and a
    ledger that counted one of them would under-report exactly the case this round added. The
    ids are de-duplicated, so a plan that uses the same hand twice counts one refusal for it
    rather than two, because it was one word that refused them.
    """
    if not slot:
        return
    steps = slot.get("steps")
    if not steps:
        _record(slot["tool"], outcome)
        return
    for tool_id in dict.fromkeys(s["tool"] for s in steps):
        _record(tool_id, outcome)
    if outcome in ("refused", "lapsed"):
        # A plan nobody said yes to stopped at its first step, having run none of them.
        _record_chain(slot.get("chainId") or "c0-0", "refused",
                      [s["tool"] for s in steps], 0, 1)


def _write_ledger(rows, chains):
    """The one writer, so `chains` cannot be dropped by a path that only knew about counts.

    THE FAILURE MODE THIS EXISTS FOR, and it was a real one for the length of one draft:
    _record() used to rebuild the whole file as {"version", "tools"}, so the first per-tool
    count written after a chain finished ERASED the chain row that had just been written. The
    ledger would have shown a tools table that added up and no transactions at all.
    """
    try:
        LEDGER_PATH.write_text(
            json.dumps({"version": 1, "tools": rows, "chains": chains},
                       ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except OSError as exc:
        _log("ledger not written (%s)", exc)


def _record(tool_id, outcome, ran=False):
    """One count, up by one. No parameters, no bodies, no recipients - ever.

    Every write goes through here and every write goes through ledger() first, so the
    file can only ever hold four integers and one timestamp per registry id. That is
    what makes the privacy claim checkable rather than aspirational: there is no key a
    recipient could be put into.
    """
    if outcome not in OUTCOMES or not find(tool_id):
        return
    rows = ledger()
    row = rows.setdefault(tool_id, _blank())
    row[outcome] = row.get(outcome, 0) + 1
    if ran or outcome in ("ok", "failed"):
        row["last"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    # chain_ledger() is read and written straight back, so a per-tool count cannot erase a
    # transaction. See _write_ledger.
    _write_ledger(rows, chain_ledger())
