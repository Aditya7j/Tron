"""jobs.py - THE PROGRESS BUS.  §35 PART 3.

THE BOSS'S LAW, in his own words: while Galaxy works, the glass shows what he is doing, step
by step, so the boss knows not to disturb.  A backend-only job is not accepted.

That is a law about a FEELING and it has a mechanical consequence: a job that takes three
minutes and says nothing is indistinguishable, from the far side of the glass, from a job that
has died.  So every long-running thing in this house emits ordered events, and this module is
the one place they are kept.  The Director is the first producer; nothing in here knows what a
video is, and that is the point - prompts 27-30 reuse this unchanged.

WHY IT IS A LIST AND NOT A STREAM, and this decides the whole schema.  The page that reads
this polls, for the reason written over #seal-study in the stylesheet: nothing here has to
arrive by a deadline, and the seal only has to be right in the tab a person is looking at.  A
polling reader means the endpoint must return THE WHOLE BOUNDED LIST AND NEVER A DELTA.  A
delta API is the obvious design and it is the wrong one here, because its failure mode is
silent: Chrome throttles a background tab's timers to about once a minute, so a five-step job
that finishes inside one throttled interval would deliver its events to a reader that had
already stopped asking, and the step list would be missing its middle rows with nothing
admitting they were dropped.  Returning the whole list makes a missed poll cost nothing.

THE THREE FIELDS ON TOP OF §35's SIX, each for a named failure:

  seq       a monotonic counter per job, so a reader can ASSERT the rows are ordered and
            complete rather than trusting that they are.  A producer that emits step 3 twice,
            or 4 before 3, is a bug the proof must be able to see - and array position cannot
            see it, because array position is produced by the same append that made the bug.
  job       an identifier DISTINCT from the job's name.  Two Directors started a second apart
            are two rows; without this they would be one row whose i/n jumps backwards.
  outcome   a closed vocabulary - running, done, failed, unverified - because a chip that reads DO NOT
            DISTURB has to have exactly one way to stop reading it.

AND elapsed_s IS MONOTONIC.  time.monotonic(), never the wall clock, whose failure mode is a
step that appears to have taken minus three thousand six hundred seconds after a DST change.
The wall clock is kept too, as a formatted string for the ledger, where a human reads it.

WHAT IT COPIES RATHER THAN INVENTS:
  - ITS OWN LOCK, never the conversation's.  scholar.py's Async Law: a status poll that could
    block a turn is worse than no status at all.  Nothing in this file calls out to anything -
    no model, no subprocess, no network - inside a locked block.
  - A WHITELIST IN BOTH DIRECTIONS, like scholar.PUBLIC_KEYS and focus.public_state().
    `detail` is the only free-text field and it is truncated, so a producer that puts an
    absolute path or a transcript into a detail string cannot reach the browser with it.
  - BOUNDS ON EVERYTHING.  An unbounded list in a process that runs for weeks is a leak with a
    nice name.

AND A JOB IS JUDGED STALE ON READ, NOT REAPED ON A TIMER.  If a producer dies mid-run this
module would otherwise hold a job `running` for ever and the glass would read DO NOT DISTURB
until the server restarted.  So a job whose last event is older than JOB_STALE_S is reported
failed by whichever reader notices - the same trick hands.lapse_if_due() uses, idempotent for
the same reason: the transition happens under the lock before the answer is composed.

Standard library only.
"""

import json
import os
import re
import threading
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LEDGER_PATH = ROOT / "jobs-ledger.json"

# ---- THE BOUNDS, each a number with a reason ------------------------------------------------
JOBS_MAX = 8            # how many jobs are remembered at once. More than one job will ever run
                        # at a time, few enough that the endpoint stays a few hundred bytes.
EVENTS_MAX = 60         # events kept per job. A five-step Director uses seven; sixty is room
                        # for a producer that reports per-scene without becoming a log file.
DETAIL_MAX = 160        # the only free-text field, and the only place a producer could leak.
JOB_STALE_S = 300.0     # five minutes without an event and the reader calls it failed. Longer
                        # than §35's 180s video budget by enough that a slow machine is not
                        # declared dead, short enough that the chip cannot stick for an hour.
LEDGER_MAX = 50         # the same ring hands.py keeps its chains in, and for the same reason.

# ---- THE WHITELISTS, both directions -------------------------------------------------------
# §43 ADDED THE FOURTH, AND IT IS THE ONLY HONEST WORD FOR WHAT IT NAMES: the act was
# accepted and this house could not confirm it. "done" would be a claim nobody verified and
# "failed" would be a lie about an action that very likely took effect - which is exactly the
# lie §43 exists to undo, because `failed` was written over three publishes that YouTube had
# accepted. A row reading `unverified` is a row a human can act on: it says go and look.
# THE HAND STILL REPORTS IT AS FAILED, and that is not a contradiction - an exit code is a
# verdict about whether to trust the result, and the sentence and the ledger carry the detail
# the exit code has no room for. See tools/publish_video.py.
OUTCOMES = ("running", "done", "failed", "unverified")
# What an EVENT may carry. §35 fixes the first six; seq is this module's.
EVENT_KEYS = ("job", "step", "i", "n", "detail", "elapsed_s", "seq", "at")
# What a JOB may carry on the way out. No producer object, no callable, no path that was not
# explicitly offered as a ledger field.
PUBLIC_KEYS = ("job", "name", "verb", "topic", "n", "outcome", "elapsedS", "startedAt",
               "steps", "events", "chip", "stale", "result")
# WHAT A FINISHED JOB MAY SHOW THE PAGE, and it is a SUBSET of the ledger's own fields rather
# than a second channel. §35's PART 3 asks the answer card to be "replaced by the result card on
# completion (mp4 path, duration, cited notes)", and the page cannot read a ledger - /jobs is the
# only route it polls - so these three ride the public row. Whitelisted for the reason every
# other list in this module is: a producer may fill them and may not invent a fourth, so nothing
# a pipeline keeps for its own bookkeeping can reach the browser by being passed to finish().
# §36 adds two: `sceneTypes` so the ledger row records what each beat was DRAWN as, and `poster`
# so the thumbnail beside final.mp4 is addressable by the Broadcaster that will read these rows.
# §40 adds three, and they are the Broadcaster's whole record: `videoId` is the name YouTube gave
# the film, `url` is where a human can watch it, and `privacy` is what it is RIGHT NOW. The third
# is the one that earns its place - in a house that may never delete, a film's privacy is the only
# property of a published thing that can still be changed, so every row says which it was left at.
RESULT_KEYS = ("cited", "durationS", "path", "sceneTypes", "poster",
               "videoId", "url", "privacy")
# And what one may write into the ledger. The Director's row is the reason `cited`, `durationS`
# and `path` are here - a producer may fill them and may not invent a seventh key.
# §40's `privacyFrom`/`privacyTo` are ledger-only and deliberately NOT in RESULT_KEYS: the page
# shows what a film IS, and the TRANSITION - who moved it from unlisted to public, and when - is
# an audit fact that belongs in the written record rather than in a card. The wide `youtube` scope
# was taken in exchange for writing them down, so they are written down.
ROW_KEYS = ("at", "job", "name", "topic", "outcome", "elapsedS", "steps", "detail",
            "cited", "durationS", "path", "sceneTypes", "poster", "why",
            "videoId", "url", "privacy", "privacyFrom", "privacyTo",
            # §43's three, and all three are about the gap between an act and its evidence.
            # `confirmSeconds` is how long the read-back took to agree - 0.0 when the first
            # read already agreed, which is what every fixture produced and what made the
            # defect invisible. `reads` is how many times it was asked. `corrects` names the
            # earlier row a correction row is about; the ledger is append-only, so a row is
            # never edited and a later row says what the earlier one got wrong.
            "confirmSeconds", "reads", "corrects")

_LOCK = threading.Lock()
_JOBS = {}              # job id -> the record below, insertion-ordered (dicts are, since 3.7)
_SEEN = {"opened": 0, "done": 0, "failed": 0, "stale": 0, "events": 0}


def _now():
    """One clock, named once. See the module docstring: never time.time() for a duration."""
    return time.monotonic()


def _clean_detail(text):
    """The one free-text field, flattened and cut.

    Newlines go because this string is rendered into a single-line chip and a one-line trace,
    and a detail containing a newline would break both in a way that looks like a layout bug.
    """
    said = re.sub(r"\s+", " ", str(text or "")).strip()
    return said[:DETAIL_MAX]


def _word(text, cap=40):
    return re.sub(r"\s+", " ", str(text or "")).strip()[:cap]


# =============================================================================================
#  THE PRODUCER'S SIDE
# =============================================================================================
def open_job(name, steps, verb="", topic=""):
    """Start a job and return its id.

    `steps` IS THE WHOLE PLAN, declared up front, and that is what makes the glass honest. A
    bus whose producer invented steps as it went could only ever render "step 4", never
    "4 of 5" - and "4 of 5" is the number that tells the boss whether to wait. It is also what
    lets the answer card show the steps that have NOT happened yet, greyed, which is the half
    of a progress list that actually answers "how much longer".
    """
    plan = [_word(s, 24) for s in (steps or []) if _word(s, 24)]
    job = uuid.uuid4().hex[:10]
    rec = {
        "job": job,
        "name": _word(name, 40) or "job",
        # THE CHIP'S VERB, uppercased once here rather than in the page, so that the glass and
        # the ledger and a harness cannot disagree about its case.
        "verb": (_word(verb, 16) or _word(name, 16)).upper(),
        "topic": _word(topic, 120),
        "plan": plan,
        "n": len(plan),
        "i": 0,
        "seq": 0,
        "outcome": "running",
        "started": _now(),
        "startedAt": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "last": _now(),
        "events": [],
        "row": {},
    }
    with _LOCK:
        _JOBS[job] = rec
        # OLDEST OUT FIRST, and a RUNNING job is never the one evicted: a bus that dropped the
        # job the glass is currently watching to make room for a finished one would blank the
        # chip mid-flight. Finished rows are already on disk by then and are the cheap ones to
        # forget.
        while len(_JOBS) > JOBS_MAX:
            victim = next((k for k, v in _JOBS.items() if v["outcome"] != "running"), None)
            if victim is None:
                victim = next(iter(_JOBS))
            _JOBS.pop(victim, None)
        _SEEN["opened"] += 1
    emit(job, plan[0] if plan else "starting", 1 if plan else 0, detail="")
    return job


def emit(job, step, i=None, n=None, detail=""):
    """One ordered event. Returns the seq it was given, or 0 if the job is not known.

    IT NEVER RAISES AND IT NEVER BLOCKS. A producer is in the middle of real work when it calls
    this, and a progress bus that could abort the thing it is reporting on would be strictly
    worse than no progress bus - the boss would rather have a video and no chip than a chip and
    no video. So a bad job id, a bad index and a detail with a newline in it are all absorbed.
    """
    with _LOCK:
        rec = _JOBS.get(str(job or ""))
        if not rec:
            return 0
        rec["seq"] += 1
        if i is not None:
            try:
                rec["i"] = max(0, min(int(i), rec["n"] or int(i)))
            except (TypeError, ValueError):
                pass
        if n is not None:
            try:
                rec["n"] = max(rec["n"], int(n))
            except (TypeError, ValueError):
                pass
        rec["last"] = _now()
        row = {"job": rec["job"], "step": _word(step, 24), "i": rec["i"], "n": rec["n"],
               "detail": _clean_detail(detail),
               "elapsed_s": round(rec["last"] - rec["started"], 1),
               "seq": rec["seq"], "at": time.strftime("%H:%M:%S")}
        rec["events"].append(row)
        while len(rec["events"]) > EVENTS_MAX:
            # THE FIRST EVENT IS NEVER DROPPED. It is the only one that records when the job
            # actually began doing something, and a truncated list that has lost its head reads
            # as a job that started at step twelve.
            rec["events"].pop(1 if len(rec["events"]) > 1 else 0)
        _SEEN["events"] += 1
        return rec["seq"]


def finish(job, outcome="done", detail="", **fields):
    """Close a job, write its ONE ledger row, and return the row.

    §35: "each job writes one ledger row on completion". One, so this is the only place that
    writes, and it is idempotent on the outcome - a producer whose `finally` calls it after its
    own success call does not get a second row, because the second call finds the job already
    closed and returns the row it wrote the first time.
    """
    job = str(job or "")
    outcome = outcome if outcome in OUTCOMES else "failed"
    with _LOCK:
        rec = _JOBS.get(job)
        if not rec:
            return {}
        if rec["outcome"] != "running":
            return dict(rec.get("row") or {})
        rec["outcome"] = outcome
        rec["last"] = _now()
        rec["i"] = rec["n"] if outcome == "done" else rec["i"]
        row = {"at": time.strftime("%Y-%m-%dT%H:%M:%S"), "job": rec["job"],
               "name": rec["name"], "topic": rec["topic"], "outcome": outcome,
               "elapsedS": round(rec["last"] - rec["started"], 1),
               "steps": rec["n"], "detail": _clean_detail(detail)}
        for key, val in (fields or {}).items():
            if key in ROW_KEYS and key not in row:
                row[key] = val
        rec["row"] = row
        # THE RESULT, FOR THE GLASS, taken from the ROW that was just built and not from the
        # caller's kwargs - so the page and the ledger cannot disagree about what was made, and a
        # field the ledger refused cannot appear on the wire.
        rec["result"] = {k: row[k] for k in RESULT_KEYS if k in row}
        _SEEN["done" if outcome == "done" else "failed"] += 1
    # OUTSIDE THE LOCK, because this one touches the disk. The Async Law applies to this
    # module's own lock as much as to the conversation's: a /jobs poll must not wait on a write.
    _append_ledger(row)
    rec["events"].append({"job": job, "step": outcome, "i": rec["i"], "n": rec["n"],
                          "detail": _clean_detail(detail),
                          "elapsed_s": row["elapsedS"], "seq": rec["seq"] + 1,
                          "at": time.strftime("%H:%M:%S")})
    with _LOCK:
        rec["seq"] += 1
    return dict(row)


class Reporter:
    """A producer's handle, so a pipeline reads as its own steps rather than as bus calls.

    It exists for one reason that is not sugar: `step()` advances the index ITSELF, from the
    plan the job was opened with, so a producer cannot emit "3 of 5" for the fourth step. The
    commonest way a progress bar lies is an index maintained by hand at four call sites.
    """

    def __init__(self, name, steps, verb="", topic=""):
        self.plan = [_word(s, 24) for s in (steps or []) if _word(s, 24)]
        self.job = open_job(name, self.plan, verb=verb, topic=topic)
        self.at = 0

    def step(self, name, detail=""):
        """Announce the named step as STARTING. Returns its 1-based index."""
        try:
            self.at = self.plan.index(_word(name, 24)) + 1
        except ValueError:
            self.at = min(self.at + 1, max(1, len(self.plan)))
        emit(self.job, name, self.at, detail=detail)
        return self.at

    def note(self, detail, step=""):
        """Same step, more news - "scene 3 of 5" inside the scenes step."""
        emit(self.job, step or (self.plan[self.at - 1] if self.at else "working"),
             self.at, detail=detail)

    def done(self, detail="", **fields):
        return finish(self.job, "done", detail, **fields)

    def failed(self, detail="", **fields):
        return finish(self.job, "failed", detail, **fields)


# =============================================================================================
#  THE READER'S SIDE
# =============================================================================================
def chip_text(rec):
    """The one string the glass shows: DIRECTING · 3/5 SCENES · 42s.

    Composed HERE and not in the browser, for the reason every other seal word in this house is:
    the page renders what the server decided, so a harness asserting the strip text is asserting
    the thing the boss actually sees rather than a parallel implementation of it.
    """
    if not rec or rec["outcome"] != "running":
        return ""
    last = (rec["events"] or [{}])[-1]
    step = str(last.get("step") or "").upper()
    secs = int(round(max(0.0, rec["last"] - rec["started"])))
    bits = [rec["verb"]]
    if rec["n"]:
        bits.append("%d/%d%s" % (rec["i"] or 1, rec["n"], (" " + step) if step else ""))
    elif step:
        bits.append(step)
    bits.append("%ds" % secs)
    return " · ".join(bits)


def _steps_public(rec):
    """The answer card's live list: every planned step, with the one word that says where it is.

    THE WHOLE PLAN, including what has not happened. A list that showed only completed steps
    would answer "what has it done" and not "how much longer", and the second is the question
    the boss is actually asking when he looks at the glass.
    """
    out = []
    for n, name in enumerate(rec["plan"], start=1):
        if rec["outcome"] == "failed" and n == rec["i"]:
            state = "failed"
        elif n < rec["i"] or rec["outcome"] == "done":
            state = "done"
        elif n == rec["i"]:
            state = "running" if rec["outcome"] == "running" else "stopped"
        else:
            state = "waiting"
        out.append({"n": n, "step": name, "state": state})
    return out


def _judge_stale(now=None):
    """Mark as failed any running job that has gone quiet. Called by every reader, under lock.

    Idempotent by construction, exactly as hands.lapse_if_due() is: the outcome is changed
    under the lock before anything is composed from it, so two tabs polling at once produce one
    transition and one ledger row.
    """
    at = _now() if now is None else now
    gone = []
    with _LOCK:
        for rec in _JOBS.values():
            if rec["outcome"] == "running" and at - rec["last"] > JOB_STALE_S:
                rec["outcome"] = "failed"
                rec["row"] = {
                    "at": time.strftime("%Y-%m-%dT%H:%M:%S"), "job": rec["job"],
                    "name": rec["name"], "topic": rec["topic"], "outcome": "failed",
                    "elapsedS": round(rec["last"] - rec["started"], 1),
                    "steps": rec["n"],
                    "detail": "no event for %ds - the producer stopped reporting"
                              % int(JOB_STALE_S),
                    "why": "stale"}
                _SEEN["stale"] += 1
                _SEEN["failed"] += 1
                gone.append(dict(rec["row"]))
    for row in gone:
        _append_ledger(row)
    return gone


def public(job=None, now=None):
    """What GET /jobs answers: the whole bounded list, whitelisted, newest last.

    Modelled on GET /study, which is the endpoint in this house that already does this
    correctly: a whitelist, no lock of the conversation's, and counts rather than contents.
    """
    _judge_stale(now=now)
    at = _now() if now is None else now
    with _LOCK:
        recs = [r for r in _JOBS.values() if not job or r["job"] == str(job)]
        out = []
        for rec in recs:
            end = rec["last"] if rec["outcome"] != "running" else at
            row = {
                "job": rec["job"], "name": rec["name"], "verb": rec["verb"],
                "topic": rec["topic"], "n": rec["n"], "outcome": rec["outcome"],
                "elapsedS": round(max(0.0, end - rec["started"]), 1),
                "startedAt": rec["startedAt"], "steps": _steps_public(rec),
                "events": [{k: e.get(k) for k in EVENT_KEYS} for e in rec["events"]],
                "chip": chip_text(rec),
                "result": dict(rec.get("result") or {}),
                "stale": bool(rec["outcome"] == "running"
                              and at - rec["last"] > JOB_STALE_S),
            }
            out.append({k: row[k] for k in PUBLIC_KEYS if k in row})
        live = next((r for r in reversed(out) if r["outcome"] == "running"), None)
        return {"jobs": out, "live": live, "chip": (live or {}).get("chip", ""),
                "busy": bool(live), "seen": dict(_SEEN),
                "maxJobs": JOBS_MAX, "staleS": int(JOB_STALE_S)}


def forget_all(reason="reset"):
    """The ↻ button's reach into this module. Finished jobs only - see the eviction note."""
    with _LOCK:
        for key in [k for k, v in _JOBS.items() if v["outcome"] != "running"]:
            _JOBS.pop(key, None)
    return reason


# =============================================================================================
#  THE LEDGER
# =============================================================================================
def ledger():
    """The rows on disk, sanitised on the way IN as well as on the way out.

    Read through ROW_KEYS so that a hand-edited file cannot introduce a key, which is the same
    discipline hands.ledger() keeps and for the same reason: it is what makes "this file can
    only hold these fields" checkable rather than aspirational.
    """
    try:
        data = json.loads(LEDGER_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    rows = data.get("jobs") if isinstance(data, dict) else None
    out = []
    for row in (rows if isinstance(rows, list) else []):
        if isinstance(row, dict):
            out.append({k: row[k] for k in ROW_KEYS if k in row})
    return out[-LEDGER_MAX:]


def _append_ledger(row):
    """One row, appended, through a temp file and os.replace.

    ATOMIC BECAUSE TWO THINGS WRITE HERE: a producer finishing, and a reader noticing a job has
    gone stale. A half-written jobs-ledger.json would be read as an empty one by ledger()
    above, which is the quietest possible way to lose the record of every job this house has
    ever run.
    """
    try:
        rows = ledger()
        rows.append({k: row[k] for k in ROW_KEYS if k in row})
        tmp = LEDGER_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps({"version": 1, "jobs": rows[-LEDGER_MAX:]},
                                  ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, LEDGER_PATH)
    except OSError:
        # A ledger that will not write is not a reason to fail a job that has already run.
        pass
