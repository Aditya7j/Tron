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
_YES_WORDS = r"""
      yes | yes\s+please | yep | yeah | yup | aye | ok | okay | okey\s*dokey
    | haan | haan\s*ji | han | theek\s+hai | kar\s+do | bilkul
    | sure | go\s+ahead | go\s+on | do\s+it | send\s+it | please\s+do | do\s+so
    | proceed | confirm(?:ed)? | affirmative | very\s+well | if\s+you\s+would
    | that'?s\s+right | correct | please
"""
_NO_WORDS = r"""
      no | no\s+thanks | no\s+thank\s+you | nope | nah | negative | cancel
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
    return {"id": tool_id, "name": str(raw.get("name") or tool_id).strip(),
            "script": script, "capabilities": caps, "params": params,
            "timeout_s": timeout, "proposal": proposal, "triggers": triggers}, ""


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
    """
    tools = registry()
    if not tools:
        return ""
    lines = ["\n- YOUR HANDS: there are a few things you can actually DO, by asking the "
             "server to run a script. These are all of them, and there are no others:"]
    for tool in tools:
        shape = ", ".join("%s (%s%s)" % (p["name"], p["type"],
                                        "" if p["required"] else ", optional")
                          for p in tool["params"]) or "no details needed"
        lines.append("  * %s - %s. Details: %s"
                     % (tool["id"], "; ".join(tool["capabilities"]), shape))
    lines.append(
        "  If, and ONLY if, they have just asked you to do one of those things, do not "
        "answer in prose. Reply with nothing but a control tag naming the tool and the "
        "details you were given, as JSON: "
        "[[tool: add_calendar_event | {\"title\": \"call the client\", \"when\": "
        "\"four o'clock\"}]]. Use the id exactly as written above; the server checks it "
        "against the tools it really has and refuses rather than guessing, so never "
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
    return "\n".join(lines)


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


def _fill(template, params):
    """The registry's sentence with {blanks} filled from validated parameters only.

    Not str.format: a parameter whose value contains a brace would raise, an unknown
    blank would raise, and neither of those is a reason to lose a proposal. Only the
    names the schema declared are substituted; anything else is left standing, visible,
    where a human will notice the template is wrong.
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
    return {"id": slot["id"], "tool": slot["tool"], "name": slot["name"],
            "line": slot["line"], "params": dict(slot["params"]),
            "fields": [dict(p) for p in slot["fields"]],
            "ttlS": CONFIRM_TTL_S,
            "expiresInS": max(0, int(round(slot["expires"] - now)))}


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
        _record(slot["tool"], "lapsed")
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

    line = _fill(tool["proposal"], params)
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
        _record(superseded["tool"], "lapsed")
        _log("proposal %s superseded by %s", superseded["tool"], tool["id"])
        line = LINES["superseded"] + " " + line
        slot["line"] = line
    _log("proposal %s (%d parameter%s validated) awaiting a word, %ds",
         tool["id"], len(params), "" if len(params) == 1 else "s", CONFIRM_TTL_S)
    return _reply(200, True, line, pending=slot, proposed=tool["id"],
                  superseded=bool(superseded))


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
    _record(slot["tool"], "lapsed")
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
    _record(slot["tool"], "lapsed")
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
    _record(slot["tool"], "refused")
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
    _record(slot["tool"], "lapsed")
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


def execute(door="button", proposal_id=None):
    """Run the pending proposal, and say exactly what the script said. Nothing else.

    The parameters come from the SLOT, never from the request that confirms it: a
    confirmation carries consent and nothing else, so no door - page, harness or stale
    tab - can substitute a recipient between the asking and the doing.
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

    tool = find(slot["tool"])
    script = (TOOLS_DIR / tool["script"]) if tool else None
    try:
        if tool is None or not script.is_file():
            _record(slot["tool"], "failed")
            _log("run %s FAILED: script missing", slot["tool"])
            return _reply(502, False, LINES["noscript"], failed="missing-script",
                          tool=slot["tool"], pending=None)
        body = json.dumps(slot["params"], ensure_ascii=False)
        started = time.monotonic()
        try:
            done = subprocess.run(
                [sys.executable, str(script)], input=body,
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=tool["timeout_s"], shell=False, cwd=str(TOOLS_DIR))
        except subprocess.TimeoutExpired:
            _record(tool["id"], "failed")
            _log("run %s FAILED: timed out after %.0fs", tool["id"], tool["timeout_s"])
            return _reply(504, False,
                          LINES["timeout"].format(seconds=int(tool["timeout_s"])),
                          failed="timeout", tool=tool["id"], pending=None)
        except OSError as exc:
            _record(tool["id"], "failed")
            _log("run %s FAILED: %s", tool["id"], type(exc).__name__)
            return _reply(502, False,
                          LINES["crashed"].format(reason=type(exc).__name__),
                          failed="not-startable", tool=tool["id"], pending=None)
        took = time.monotonic() - started
        out = _evidence(done.stdout)
        err = _evidence(done.stderr)

        if done.returncode != 0:
            # The reason it OBSERVED, in this order of preference: what the script said
            # on stdout, what it said on stderr, and failing both, the exit code. Never
            # an invented explanation.
            reason = out or err or "it exited with status %d" % done.returncode
            _record(tool["id"], "failed")
            _log("run %s FAILED in %.1fs (exit %d)", tool["id"], took, done.returncode)
            return _reply(502, False, LINES["failed"].format(reason=reason),
                          failed="exit-%d" % done.returncode, tool=tool["id"],
                          exitCode=done.returncode, pending=None)
        if not out:
            # A hand that fails silently is worse than no hand, and a success claimed
            # with no evidence is worse still.
            _record(tool["id"], "failed")
            _log("run %s FAILED in %.1fs: exit 0 and nothing on stdout", tool["id"], took)
            return _reply(502, False, LINES["silent"], failed="no-evidence",
                          tool=tool["id"], exitCode=0, pending=None)
        _record(tool["id"], "ok", ran=True)
        _log("run %s ok in %.1fs, %d characters of evidence", tool["id"], took, len(out))
        return _reply(200, True, out, tool=tool["id"], ran=tool["id"], door=door,
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
    try:
        LEDGER_PATH.write_text(
            json.dumps({"version": 1, "tools": rows}, ensure_ascii=False, indent=2)
            + "\n", encoding="utf-8")
    except OSError as exc:
        _log("ledger not written (%s)", exc)
