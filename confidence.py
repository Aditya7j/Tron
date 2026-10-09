"""THE CONFIDENCE METER. How much the boss should trust Galaxy right now: a 0-100% score per
agent and one overall number, each with a one-line diagnosis, computed from ledgers that
already exist.

IT IS READ-ONLY. It reads three ledgers and writes one file of its own, confidence-cache.json
(the test files' last exit codes and the last report). It calls no model, opens no connection,
starts no agent, deletes nothing and sends nothing. The one thing it can start is the test
files, and only when asked (`python confidence.py --tests`), never on a schedule and never from
the daemon. test_confidence.py reads this file's source and imports to hold that.

WHY NO MODEL GRADES ANYTHING. A system scoring its own trustworthiness with itself is not a
measurement: a number a model invents about its own house is a vibe with a decimal point.
Every figure below is arithmetic on rows a ledger wrote at the time, and every diagnosis that
quotes a failure quotes the ledger's own words - truncated at DETAIL_MAX, never paraphrased.

WHAT IT READS
    jobs-ledger.json   (jobs.py)         the Director, the Broadcaster and the Publisher. One
                                         row per job; `outcome` is done, failed or unverified
                                         (a job that went stale is written as failed).
    study-ledger.json  (scholar.py)      the Scholar's study ticks; `outcome` is kept, skipped
                                         or failed.
    paper-ledger.json  (quant_paper.py)  the Quant's live paper-trades.
    confidence-cache.json (this file)    each test file's exit code, the last time it ran.
A ledger that does not exist is reported as "no data" - never guessed at, never a default.

WHAT COUNTS AS A SUCCESS, PER LEDGER, AND WHY
    jobs    outcome == "done". "unverified" is not done: it says nobody confirmed the act.
            A CORRECTION ROW (one carrying `corrects`, appended by broadcast.reconcile()) is
            not a run: it says an earlier row was wrong, so the earlier row counts as done and
            the correction is not counted a second time.
            Job names map to agents: director -> Director; broadcast and publish ->
            Broadcaster (both are broadcast.py's - the upload and the privacy change);
            newsletter -> Publisher (newsletter.py is "THE PUBLISHER's composition half").
    study   outcome == "kept". "skipped" is the poison guard throwing a draft away: the guard
            worked, but the draft was not one to keep, so it is not the Scholar's success.
            Rows whose `why` says "injected" are left out - they are deliberate attacks on the
            guard run by hand, not the Scholar's own work - and the report says how many.
    paper   outcome == "win" on live closed trades, judged ONLY through
            quant_paper.track_record(), so the Quant is scored only once MIN_TRADES_TO_JUDGE
            (30) trades have closed. A win rate on fewer is something quant_paper.py already
            refuses to state, and this file does not get to state it on its behalf. For the
            same reason the Quant's record is read whole rather than through the window.

THE WINDOW. A score reads the runs of the last WINDOW_DAYS (7) days, at most the last
WINDOW_RUNS (20) of them - whichever is fewer rows. With fewer than MIN_RUNS_TO_SCORE (3) runs
in the window there is no number, only "not enough data yet". So an agent idle for more than
seven days has no score at all: it cannot be vouched for today, whatever its past.

THE SCORE
    success   = runs that succeeded / runs in the window                              0..1
    freshness = 1.0 when the last run was within FRESH_FULL_H (24) hours, falling in a
                straight line to 0.0 at WINDOW_DAYS (168 hours)                       0..1
    score     = 100 x (W_SUCCESS x success + W_FRESH x freshness), rounded,
                with W_SUCCESS = 0.8 and W_FRESH = 0.2
    ceiling   if any of the agent's own test files exited non-zero the last time it ran,
              the score is min(score, TEST_RED_CEILING) = 25. However good the ledger looks,
              a red test file means the code under it is not the code that earned the record.

    A WORKED EXAMPLE. The Director has 20 runs in the window and 11 of them are done; its last
    run was 96 hours ago.
        success   = 11 / 20                            = 0.55
        freshness = 1 - (96 - 24) / (168 - 24)         = 0.5
        score     = 100 x (0.8 x 0.55 + 0.2 x 0.5)     = 54
    Had one of its test files been red, the 54 would be shown as 25.

THE OVERALL NUMBER is the plain mean of the agents that have a score, and the sentence names
every agent that does not. With no agent scored there is no overall number.

WHAT IT DOES NOT DO
    It predicts nothing. Every number is "here is what happened", never "how likely the next
    run is to work" - the same "measured, not forecast" rule as quant_paper.track_record().
    It adds no instrumentation. A field a ledger lacks is a note in this report, never a change
    to the agent that writes the ledger.

    python confidence.py              the report, as text
    python confidence.py --json       the report, as json
    python confidence.py --tests      run the test files, cache their exit codes, then report
"""

import datetime
import json
import os
import subprocess
import sys
import threading
import time

import quant_paper
from tools import _proc

HERE = os.path.dirname(os.path.abspath(__file__))
JOBS_LEDGER = os.path.join(HERE, "jobs-ledger.json")
STUDY_LEDGER = os.path.join(HERE, "study-ledger.json")
PAPER_LEDGER = quant_paper.LEDGER_PATH
CACHE_PATH = os.path.join(HERE, "confidence-cache.json")

WINDOW_DAYS, WINDOW_RUNS = 7, 20
MIN_RUNS_TO_SCORE = 3
FRESH_FULL_H = 24.0
W_SUCCESS, W_FRESH = 0.8, 0.2
TEST_RED_CEILING = 25
DETAIL_MAX = 160
# The rings the writers keep - jobs.LEDGER_MAX and scholar.LEDGER_HISTORY_MAX, copied rather
# than imported so this file loads nothing that can reach a network. test_confidence.py holds
# the two copies equal to their sources.
JOBS_RING, STUDY_RING = 50, 60
TEST_TIMEOUT_S = 900

# (key, name, ledger, the jobs-ledger names that are this agent's)
AGENTS = (("director", "Director", "jobs", ("director",)),
          ("broadcaster", "Broadcaster", "jobs", ("broadcast", "publish")),
          ("publisher", "Publisher", "jobs", ("newsletter",)),
          ("scholar", "Scholar", "study", ()),
          ("quant", "Quant", "paper", ()))
# An agent's own test files, whose last exit code can cap its score.
AGENT_TESTS = {"quant": ("test_quant.py", "test_quant_paper.py")}
# The agents proved only by a headed harness, which needs a live server and is never run here.
AGENT_PROOFS = {"director": "director_proof.mjs", "broadcaster": "broadcaster_proof.mjs",
                "publisher": "publisher_proof.mjs", "scholar": "study_proof.mjs"}

NOTICE = "Measured from what the ledgers recorded - not a forecast of the next run."

_cache_lock = threading.Lock()


# ------------------------------------------------------------------------------ reading

def _when(text):
    """A ledger timestamp as a naive local datetime, or None. jobs.py writes
    2026-10-09T10:04:46, scholar.py 2026-10-09 14:48, quant_paper.py an IST-aware ISO."""
    try:
        t = datetime.datetime.fromisoformat(str(text or "").strip())
    except ValueError:
        return None
    return t.astimezone().replace(tzinfo=None) if t.tzinfo is not None else t


def _read_json(path):
    """(data, why) - `why` is "" when the file was read, else the plain reason it was not."""
    name = os.path.basename(path)
    if not os.path.exists(path):
        return None, "%s does not exist yet" % name
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh), ""
    except (OSError, ValueError) as exc:
        return None, "%s could not be read (%s)" % (name, type(exc).__name__)


def _detail(text):
    text = " ".join(str(text or "").split())
    return text if len(text) <= DETAIL_MAX else text[:DETAIL_MAX - 3].rstrip() + "..."


def _run(at, ok, detail, at_text):
    return {"at": at, "ok": ok, "detail": _detail(detail), "atText": str(at_text or "")}


def jobs_runs(data, names):
    """(runs, notes) for the jobs-ledger names given."""
    rows = data.get("jobs") if isinstance(data, dict) else None
    rows = [r for r in rows if isinstance(r, dict)] if isinstance(rows, list) else []
    mine = [r for r in rows if str(r.get("name") or "") in names]
    corrected = {str(r.get("corrects")) for r in mine if r.get("corrects")}
    runs, notes, late, bad = [], [], 0, 0
    for r in mine:
        if r.get("corrects"):
            continue
        at = _when(r.get("at"))
        if at is None:
            bad += 1
            continue
        ok = str(r.get("outcome") or "") == "done"
        if not ok and str(r.get("at")) in corrected:
            ok, late = True, late + 1
        runs.append(_run(at, ok, r.get("detail") or r.get("why") or r.get("outcome"),
                         r.get("at")))
    if late:
        notes.append("%d run%s counted as done because a later correction row says so"
                     % (late, "" if late == 1 else "s"))
    if bad:
        notes.append("%d row%s without a readable time left out" % (bad, "" if bad == 1 else "s"))
    if len(rows) >= JOBS_RING:
        notes.append("jobs-ledger.json keeps only its last %d rows across every job, so older "
                     "runs have rolled off" % JOBS_RING)
    return runs, notes


def study_runs(data):
    """(runs, notes) for the Scholar."""
    rows = data.get("history") if isinstance(data, dict) else None
    rows = [r for r in rows if isinstance(r, dict)] if isinstance(rows, list) else []
    runs, notes, injected, bad = [], [], 0, 0
    for r in rows:
        if "injected" in str(r.get("why") or ""):
            injected += 1
            continue
        at = _when(r.get("at"))
        if at is None:
            bad += 1
            continue
        runs.append(_run(at, str(r.get("outcome") or "") == "kept",
                         r.get("reason") or r.get("outcome"), r.get("at")))
    if injected:
        notes.append("%d injected-test tick%s left out" % (injected, "" if injected == 1 else "s"))
    if bad:
        notes.append("%d row%s without a readable time left out" % (bad, "" if bad == 1 else "s"))
    if len(rows) >= STUDY_RING:
        notes.append("study-ledger.json keeps only its last %d ticks, so older ones have "
                     "rolled off" % STUDY_RING)
    return runs, notes


def read_cache(path=None):
    data, _why = _read_json(path or CACHE_PATH)
    data = data if isinstance(data, dict) else {}
    if not isinstance(data.get("tests"), dict):
        data["tests"] = {}
    return data


def _write_cache(cache, path=None):
    path = path or CACHE_PATH
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(cache, fh, indent=1, ensure_ascii=False)
        fh.write("\n")
    os.replace(tmp, path)


# ------------------------------------------------------------------------------ the math

def freshness(age_h):
    """1.0 within FRESH_FULL_H hours, a straight line down to 0.0 at WINDOW_DAYS."""
    full, zero = FRESH_FULL_H, WINDOW_DAYS * 24.0
    if age_h <= full:
        return 1.0
    if age_h >= zero:
        return 0.0
    return 1.0 - (age_h - full) / (zero - full)


def blend(success, fresh, red):
    """The score, 0..100, before and after the test ceiling: (raw, shown)."""
    raw = round(100 * (W_SUCCESS * success + W_FRESH * fresh))
    return raw, (min(raw, TEST_RED_CEILING) if red else raw)


def window(runs, now):
    """The runs of the last WINDOW_DAYS days, at most the last WINDOW_RUNS - fewer rows wins."""
    since = now - datetime.timedelta(days=WINDOW_DAYS)
    return [r for r in runs if r["at"] >= since][-WINDOW_RUNS:]


def _ago(hours):
    if hours < 1:
        return "%d min" % max(0, round(hours * 60))
    if hours < 48:
        return "%d h" % round(hours)
    return "%d days" % round(hours / 24)


def test_health(key, cache):
    files = AGENT_TESTS.get(key, ())
    results = cache.get("tests") or {}
    red = [f for f in files if f in results and results[f].get("exit") != 0]
    unrun = [f for f in files if f not in results]
    notes = []
    if not files:
        notes.append("no test file of its own - its proof is %s, a headed harness this meter "
                     "does not run" % AGENT_PROOFS.get(key, "a harness"))
    if unrun:
        notes.append("%s not yet run through the meter (python confidence.py --tests)"
                     % ", ".join(unrun))
    return {"files": list(files), "red": red, "unrun": unrun,
            "results": {f: results[f] for f in files if f in results}}, notes


def _verdict(key, name, source, runs, notes, tests, now, whole=False, min_runs=None,
             last_act=None):
    """One agent's entry. `whole` reads every run instead of the window (the Quant), and
    `last_act` is a later sign of life than the last run, if the agent has one."""
    out = {"agent": key, "name": name, "source": source, "status": "nodata", "score": None,
           "raw": None, "runs": 0, "succeeded": 0, "successRate": None, "freshness": None,
           "lastAt": None, "ageHours": None, "lastFailure": None, "capped": False,
           "tests": tests, "notes": notes}
    runs = sorted(runs, key=lambda r: r["at"])
    if not runs:
        out["diagnosis"] = "%s: no data - %s holds no %s run yet." % (name, source, name)
        return out
    last = max([runs[-1]["at"]] + ([last_act] if last_act else []))
    age_h = max(0.0, (now - last).total_seconds() / 3600.0)
    out.update(lastAt=last.isoformat(), ageHours=round(age_h, 1))
    failed = [r for r in runs if not r["ok"]]
    if failed:
        out["lastFailure"] = {"at": failed[-1]["atText"], "detail": failed[-1]["detail"]}
    judged = runs if whole else window(runs, now)
    need = MIN_RUNS_TO_SCORE if min_runs is None else min_runs
    out["runs"] = len(judged)
    if len(judged) < need:
        out["status"] = "thin"
        out["diagnosis"] = ("%s: not enough data yet - %d run%s in the last %d days, a score "
                            "needs %d. Last run %s ago."
                            % (name, len(judged), "" if len(judged) == 1 else "s", WINDOW_DAYS,
                               need, _ago(age_h)))
        return out
    ok = sum(1 for r in judged if r["ok"])
    success, fresh = ok / len(judged), freshness(age_h)
    raw, shown = blend(success, fresh, bool(tests["red"]))
    out.update(status="scored", score=shown, raw=raw, succeeded=ok,
               successRate=round(success, 3), freshness=round(fresh, 3), capped=shown < raw)
    line = ("%s %d%%: %d of %d runs succeeded%s, last run %s ago."
            % (name, shown, ok, len(judged), "" if whole else " in the window", _ago(age_h)))
    if out["capped"]:
        line += (" Capped at %d%% from %d%% - %s failed its last run."
                 % (TEST_RED_CEILING, raw, ", ".join(tests["red"])))
    if out["lastFailure"]:
        line += ' Last failure (%s): "%s"' % (out["lastFailure"]["at"],
                                             out["lastFailure"]["detail"])
    else:
        line += " No failure on record."
    out["diagnosis"] = line
    return out


def _quant(cache, now):
    tests, notes = test_health("quant", cache)
    source = os.path.basename(PAPER_LEDGER)
    if not os.path.exists(PAPER_LEDGER):
        out = _verdict("quant", "Quant", source, [], notes, tests, now)
        out["diagnosis"] = "Quant: no data - %s does not exist yet." % source
        return out
    trades = [t for t in quant_paper.read_trades(PAPER_LEDGER) if t.get("mode") == "live"]
    record = quant_paper.track_record(trades)
    runs = []
    for t in trades:
        if t.get("status") != "closed":
            continue
        at = _when(t.get("closedAt"))
        if at is not None:
            runs.append(_run(at, t.get("outcome") == "win", quant_paper.describe_close(t),
                             t.get("closedAt")))
    # Freshness follows the desk's last act, an opening included, not only its last close.
    acts = [a for a in (_when(t.get(k)) for t in trades for k in ("openedAt", "closedAt")) if a]
    out = _verdict("quant", "Quant", source, runs, notes, tests, now, whole=True,
                   min_runs=max(MIN_RUNS_TO_SCORE, quant_paper.MIN_TRADES_TO_JUDGE),
                   last_act=max(acts) if acts else None)
    if not trades:
        out["diagnosis"] = "Quant: no data - %s holds no live paper-trade yet." % source
    elif out["status"] != "scored":
        out["status"] = "thin"
        out["diagnosis"] = "Quant: not enough data yet - %s" % record["sentence"]
    return out


# ------------------------------------------------------------------------------ the report

def report(now=None, write=True):
    """Every agent's verdict and the overall number. Writes it to the cache when `write`."""
    now = now or datetime.datetime.now()
    with _cache_lock:
        cache = read_cache()
    sources = {"jobs": _read_json(JOBS_LEDGER), "study": _read_json(STUDY_LEDGER)}
    agents = []
    for key, name, ledger, names in AGENTS:
        if ledger == "paper":
            agents.append(_quant(cache, now))
            continue
        tests, notes = test_health(key, cache)
        data, why = sources[ledger]
        source = os.path.basename(JOBS_LEDGER if ledger == "jobs" else STUDY_LEDGER)
        if why:
            out = _verdict(key, name, source, [], notes, tests, now)
            out["diagnosis"] = "%s: no data - %s." % (name, why)
            agents.append(out)
            continue
        runs, more = jobs_runs(data, names) if ledger == "jobs" else study_runs(data)
        agents.append(_verdict(key, name, source, runs, more + notes, tests, now))
    scored = [a for a in agents if a["score"] is not None]
    unscored = [a for a in agents if a["score"] is None]
    overall = round(sum(a["score"] for a in scored) / len(scored)) if scored else None
    missing = ", ".join("%s (%s)" % (a["name"], "no data" if a["status"] == "nodata"
                                     else "not enough data yet") for a in unscored)
    if scored:
        sentence = ("Galaxy overall: %d%% - the mean of %s."
                    % (overall, ", ".join("%s %d%%" % (a["name"], a["score"]) for a in scored)))
        if unscored:
            sentence += " No score for %s." % missing
    else:
        sentence = ("No agent has enough recorded runs to score, so there is no overall number"
                    " - %s." % missing)
    rep = {"at": now.isoformat(timespec="seconds"), "overall": {
               "score": overall, "over": [a["name"] for a in scored],
               "unscored": [a["name"] for a in unscored], "sentence": sentence},
           "agents": agents, "notice": NOTICE,
           "rules": {"windowDays": WINDOW_DAYS, "windowRuns": WINDOW_RUNS,
                     "minRuns": MIN_RUNS_TO_SCORE, "wSuccess": W_SUCCESS, "wFresh": W_FRESH,
                     "testCeiling": TEST_RED_CEILING}}
    if write:
        with _cache_lock:
            cache = read_cache()
            cache["report"] = rep
            _write_cache(cache)
    return rep


def weakest(rep):
    """The scored agents sharing the lowest score - more than one on a tie, none if unscored."""
    scored = [a for a in rep["agents"] if a["score"] is not None]
    low = min((a["score"] for a in scored), default=None)
    return [a for a in scored if a["score"] == low]


def answer(view="overall", now=None):
    """(text, report) for a chat question. `view` is "overall", "weakest" or an agent key.
    Every figure in the text is one report() computed; nothing here is composed by a model."""
    rep = report(now=now)
    by_key = {a["agent"]: a for a in rep["agents"]}
    if view in by_key:
        a = by_key[view]
        parts = [a["diagnosis"]] + (["Notes: %s." % "; ".join(a["notes"])] if a["notes"] else [])
    elif view == "weakest":
        low = weakest(rep)
        if not low:
            parts = ["No agent has enough recorded runs to compare, so none can be called the "
                     "weakest."]
        else:
            parts = ["The weakest right now: %s, at %d%%."
                     % (" and ".join(a["name"] for a in low), low[0]["score"])]
            parts += [a["diagnosis"] for a in low]
        if rep["overall"]["unscored"]:
            parts.append("Not compared, for want of data: %s."
                         % ", ".join(rep["overall"]["unscored"]))
    else:
        parts = [rep["overall"]["sentence"]] + [a["diagnosis"] for a in rep["agents"]]
    return "\n\n".join(parts + [NOTICE]), rep


# ------------------------------------------------------------------------------ the tests

def test_files():
    return sorted(f for f in os.listdir(HERE)
                  if f.startswith("test_") and f.endswith(".py") and f != "test_confidence.py")


def run_tests(files=None, timeout=TEST_TIMEOUT_S):
    """Run each test file once, now, and cache its exit code. Only ever called by hand."""
    results = {}
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    for f in files or test_files():
        t0 = time.monotonic()
        try:
            # Through _proc, like every spawn in this house: no console window on Windows.
            p = _proc.run([sys.executable, os.path.join(HERE, f)], cwd=HERE, env=env,
                          capture_output=True, timeout=timeout)
            code = p.returncode
            lines = [ln.strip() for ln in p.stdout.decode("utf-8", "replace").splitlines()
                     if ln.strip()]
            summary = lines[-1] if lines else ""
        except subprocess.TimeoutExpired:
            code, summary = None, "timed out after %d s" % timeout
        results[f] = {"exit": code, "summary": _detail(summary),
                      "seconds": round(time.monotonic() - t0, 1),
                      "at": datetime.datetime.now().isoformat(timespec="seconds")}
        sys.stderr.write("  confidence: %s exited %s (%s)\n" % (f, code, results[f]["summary"]))
    with _cache_lock:
        cache = read_cache()
        cache["tests"].update(results)
        _write_cache(cache)
    return results


def render(rep):
    lines = [rep["overall"]["sentence"], ""]
    for a in rep["agents"]:
        lines.append("  " + a["diagnosis"])
        lines += ["      note: %s" % n for n in a["notes"]]
    return "\n".join(lines + ["", NOTICE])


if __name__ == "__main__":                                     # pragma: no cover
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:                                          # noqa: BLE001
        pass
    if "--tests" in sys.argv:
        run_tests()
    rep = report()
    print(json.dumps(rep, indent=1, ensure_ascii=False) if "--json" in sys.argv
          else render(rep))
