"""Proves the confidence meter: a score is arithmetic on the ledgers, or it is not given.

  1. THE FORMULA. freshness() and blend() match hand-computed values, and the worked example in
     confidence.py's docstring (11 of 20 done, last run 96 hours ago -> 54) comes out of a
     stubbed jobs ledger exactly.
  2. THE WINDOW. Only the last 7 days count, at most the last 20 runs; fewer than
     MIN_RUNS_TO_SCORE runs is "not enough data yet", with no percentage anywhere.
  3. NO DATA. A missing ledger, or one with no row of the agent's, is "no data", said plainly
     - never a number, never a default. With nothing scored there is no overall number.
  4. THE LEDGER RULES. "unverified" is not done; a correction row turns the row it corrects
     into done and is not itself a run; broadcast and publish are the Broadcaster's,
     newsletter the Publisher's; a Scholar skip is not a success and an injected tick is left
     out. The last failure is the ledger's own words, verbatim.
  5. THE QUANT. Judged only through quant_paper.track_record(): 4 closed trades is "not enough"
     with no percentage, 30 is a score, and dry-run trades never count.
  6. THE TEST CEILING. A red test file caps the agent at TEST_RED_CEILING whatever its ledger
     says; run_tests() records exit codes in the cache, on request only.
  7. THE OVERALL NUMBER AND THE CACHE. The mean of the scored agents; the cache is written to
     its own path and nowhere else, and report(write=False) writes nothing.
  8. THE CHAT. The three questions route to "confidence"; concepts, the paper desk's own
     questions and a phone do not; every figure in the answer is the report's own.
  9. READ-ONLY AND MODEL-FREE. confidence.py imports nothing that reaches a network or a
     model, starts a process only inside run_tests(), writes only through _write_cache(), and
     neither it nor server.py's new lines name an execution API or a model call.
 10. THE TREND. rising, falling, steady and early come out of hand-built runs as the docstring
     says, and the middle run of an odd count belongs to neither half.
 11. THE PER-RESPONSE LINE. answer_quant and answer_paper end with the agent's line, which
     matches the cached score; four reads cost one ledger read, a stale cache exactly one more,
     and none of it writes a file. Only those two functions call it, so an answer that touched
     no agent carries no line. A meter that throws costs the answer nothing.
 12. /health AND THE TILE. The real /health handler, on a loopback server of this file's own,
     carries "confidence" with nulls on empty ledgers; the page's own railConfidence(), run in
     node, prints "--" for every null and no number until MIN_RUNS_TO_SCORE is met.

Nothing touches the network beyond that loopback port, the real ledgers or the real cache.

Run it:  python test_confidence.py
Exit status is the number of failures.
"""

import ast
import datetime
import inspect
import io
import json
import os
import re
import sys
import tempfile
import threading
import time
import urllib.request
from functools import partial
from http.server import ThreadingHTTPServer

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:                                              # noqa: BLE001
    pass

import confidence as cf                                        # noqa: E402
import quant_paper as qp                                       # noqa: E402
import server                                                  # noqa: E402
from tools import _proc                                        # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
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


NOW = datetime.datetime(2026, 10, 9, 12, 0, 0)
TMP = tempfile.mkdtemp()
REAL = {n: getattr(cf, n) for n in ("JOBS_LEDGER", "STUDY_LEDGER", "PAPER_LEDGER",
                                    "CACHE_PATH", "HERE")}
REAL_CACHE_MTIME = (os.path.getmtime(REAL["CACHE_PATH"]) if os.path.exists(REAL["CACHE_PATH"])
                    else None)
cf.JOBS_LEDGER = os.path.join(TMP, "jobs-ledger.json")
cf.STUDY_LEDGER = os.path.join(TMP, "study-ledger.json")
cf.PAPER_LEDGER = os.path.join(TMP, "paper-ledger.json")
cf.CACHE_PATH = os.path.join(TMP, "confidence-cache.json")


def hours_ago(h):
    return NOW - datetime.timedelta(hours=h)


def job(name, outcome, h, detail="", **more):
    return dict({"at": hours_ago(h).isoformat(timespec="seconds"), "job": "j%x" % int(h * 100),
                 "name": name, "outcome": outcome, "detail": detail or outcome}, **more)


def tick(outcome, h, reason="", why="daemon"):
    return {"at": hours_ago(h).strftime("%Y-%m-%d %H:%M"), "topic": "t", "why": why,
            "outcome": outcome, "reason": reason}


def put(path, data):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh)


def clear():
    for p in (cf.JOBS_LEDGER, cf.STUDY_LEDGER, cf.PAPER_LEDGER, cf.CACHE_PATH):
        if os.path.exists(p):
            os.remove(p)


def agent(rep, key):
    return next(a for a in rep["agents"] if a["agent"] == key)


try:
    # -----------------------------------------------------------------------------------
    head("1. the formula, by hand")
    ok(cf.freshness(0) == 1.0 and cf.freshness(24) == 1.0, "fresh within 24 hours: 1.0")
    ok(cf.freshness(96) == 0.5, "96 hours: 1 - (96 - 24) / 144 = 0.5")
    ok(cf.freshness(168) == 0.0 and cf.freshness(500) == 0.0, "168 hours and beyond: 0.0")
    ok(cf.blend(0.55, 0.5, False) == (54, 54), "0.8 x 0.55 + 0.2 x 0.5 = 54")
    ok(cf.blend(0.55, 0.5, True) == (54, 25), "the same with a red test file: shown as 25")
    ok(cf.blend(1.0, 1.0, False) == (100, 100) and cf.blend(0.0, 0.0, False) == (0, 0),
       "the bounds are 0 and 100")
    clear()
    rows = [job("director", "done" if i < 11 else "failed", 100 - i * 0.2,
                detail="the notes hold nothing on this" if i >= 11 else "made it")
            for i in range(20)]
    put(cf.JOBS_LEDGER, {"version": 1, "jobs": rows})
    d = agent(cf.report(now=NOW), "director")
    ok(d["status"] == "scored" and d["runs"] == 20 and d["succeeded"] == 11
       and d["ageHours"] == 96.2 and d["score"] == round(100 * (0.8 * 0.55
                                                                + 0.2 * cf.freshness(96.2))),
       "a stubbed ledger: 11 of 20 done, last run 96.2 h ago", str(d))
    rows[-1] = job("director", "failed", 96, detail="the notes hold nothing on this")
    put(cf.JOBS_LEDGER, {"version": 1, "jobs": rows})
    d = agent(cf.report(now=NOW), "director")
    ok(d["score"] == 54 and d["diagnosis"].startswith("Director 54%: 11 of 20 runs succeeded"),
       "the docstring's worked example: 54%", d["diagnosis"])

    # -----------------------------------------------------------------------------------
    head("2. the window")
    rows = ([job("director", "failed", 200 + i) for i in range(10)]          # older than 7 days
            + [job("director", "failed", 100 - i) for i in range(5)]          # 5 oldest in window
            + [job("director", "done", 50 - i) for i in range(20)])           # the last 20
    put(cf.JOBS_LEDGER, {"version": 1, "jobs": rows})
    d = agent(cf.report(now=NOW), "director")
    ok(d["runs"] == 20 and d["succeeded"] == 20,
       "25 runs inside 7 days and 10 outside: only the last 20 are read", str(d))
    put(cf.JOBS_LEDGER, {"version": 1, "jobs": [job("director", "done", 5),
                                                job("director", "done", 4)]})
    d = agent(cf.report(now=NOW), "director")
    ok(d["score"] is None and d["status"] == "thin" and "not enough data yet" in d["diagnosis"]
       and "%" not in d["diagnosis"], "2 runs: 'not enough data yet', no percentage",
       d["diagnosis"])
    put(cf.JOBS_LEDGER, {"version": 1, "jobs": [job("director", "done", 200 + i)
                                                for i in range(10)]})
    d = agent(cf.report(now=NOW), "director")
    ok(d["score"] is None and d["runs"] == 0 and "%" not in d["diagnosis"],
       "10 perfect runs eight days ago: no score today, whatever the past", d["diagnosis"])

    # -----------------------------------------------------------------------------------
    head("3. no data, said plainly")
    clear()
    rep = cf.report(now=NOW)
    ok(all(a["score"] is None and a["status"] == "nodata" for a in rep["agents"]),
       "no ledger at all: every agent is 'no data'")
    ok(all("no data" in a["diagnosis"] and "does not exist yet" in a["diagnosis"]
           and "%" not in a["diagnosis"] for a in rep["agents"]),
       "and each says which file does not exist, with no figure",
       str([a["diagnosis"] for a in rep["agents"]]))
    ok(rep["overall"]["score"] is None and "no overall number" in rep["overall"]["sentence"]
       and "%" not in rep["overall"]["sentence"], "nothing scored: no overall number",
       rep["overall"]["sentence"])
    put(cf.JOBS_LEDGER, {"version": 1, "jobs": [job("director", "done", 1)] * 5})
    rep = cf.report(now=NOW)
    b = agent(rep, "broadcaster")
    ok(b["status"] == "nodata" and "holds no Broadcaster run yet" in b["diagnosis"],
       "a ledger with no row of the agent's: no data", b["diagnosis"])
    with open(cf.JOBS_LEDGER, "w") as fh:
        fh.write("{not json")
    ok(agent(cf.report(now=NOW), "director")["diagnosis"]
       == "Director: no data - jobs-ledger.json could not be read (JSONDecodeError).",
       "an unreadable ledger is named, not scored as empty")

    # -----------------------------------------------------------------------------------
    head("4. the ledger rules")
    clear()
    put(cf.JOBS_LEDGER, {"version": 1, "jobs": [
        job("broadcast", "done", 10), job("broadcast", "unverified", 9),
        job("publish", "failed", 8, detail="the read-back disagreed"),
        job("publish", "done", 2, detail="confirmed-late: v1 is public",
            corrects=hours_ago(8).isoformat(timespec="seconds")),
        job("newsletter", "done", 3), job("newsletter", "done", 2),
        job("newsletter", "failed", 1, detail="x" * 400)]})
    rep = cf.report(now=NOW)
    b, p = agent(rep, "broadcaster"), agent(rep, "publisher")
    ok(b["runs"] == 3 and b["succeeded"] == 2,
       "Broadcaster: broadcast + publish, the correction is not a run, 'unverified' is not done",
       str(b))
    ok(any("correction row" in n for n in b["notes"]),
       "and the late confirmation is noted, not silent", str(b["notes"]))
    ok(b["lastFailure"]["detail"] == "unverified" and p["runs"] == 3 and p["succeeded"] == 2,
       "the corrected publish is no longer the last failure; Publisher is the newsletter rows")
    ok(len(p["lastFailure"]["detail"]) == cf.DETAIL_MAX
       and p["lastFailure"]["detail"].endswith("...")
       and p["lastFailure"]["detail"][:-3] == "x" * (cf.DETAIL_MAX - 3),
       "a long detail is truncated, never reworded")
    put(cf.STUDY_LEDGER, {"version": 1, "history": [
        tick("kept", 6), tick("skipped", 5, "poison guard: invented figures"),
        tick("failed", 4, "Groq is rate limiting (429)."), tick("kept", 3),
        tick("failed", 2, "planted", why="cli+injected-articles"),
        tick("skipped", 1, "poison guard: a goal the evidence never states")]})
    s = agent(cf.report(now=NOW), "scholar")
    ok(s["runs"] == 5 and s["succeeded"] == 2,
       "Scholar: kept is success, skipped and failed are not, the injected tick is left out",
       str(s))
    ok(s["lastFailure"]["detail"] == "poison guard: a goal the evidence never states"
       and '"poison guard: a goal the evidence never states"' in s["diagnosis"],
       "the diagnosis quotes the ledger's own words", s["diagnosis"])
    ok(any("1 injected-test tick left out" == n for n in s["notes"]),
       "and says how many injected ticks it left out", str(s["notes"]))

    # -----------------------------------------------------------------------------------
    head("5. the Quant, only through track_record()")
    clear()

    def trade(outcome, h, mode="live", status="closed"):
        at = hours_ago(h).astimezone().isoformat()
        return {"id": "pt-%s" % h, "mode": mode, "symbol": "NIFTY", "ticker": "^NSEI",
                "direction": "long", "entry": 100.0, "target": 104.5, "stop": 97.0, "atr": 2.0,
                "signalBar": at, "openedAt": at, "status": status,
                "exit": 104.5 if outcome == "win" else 97.0, "closedAt": at if status ==
                "closed" else None, "exitReason": "target" if outcome == "win" else "stop",
                "outcome": outcome if status == "closed" else None,
                "pnlPts": 4.5 if outcome == "win" else -3.0}
    q = agent(cf.report(now=NOW), "quant")
    ok(q["status"] == "nodata" and q["diagnosis"]
       == "Quant: no data - paper-ledger.json does not exist yet.", "no ledger: no data")
    four = [trade("win", 5), trade("win", 4), trade("loss", 3), trade("loss", 2)]
    qp.write_trades(four + [dict(t, mode="dryrun", id="d%d" % i) for i, t in
                            enumerate(four * 10)], cf.PAPER_LEDGER)
    q = agent(cf.report(now=NOW), "quant")
    ok(q["score"] is None and "Only 4 paper-trades closed so far" in q["diagnosis"]
       and "%" not in q["diagnosis"],
       "4 live trades (and 40 dry-run ones): track_record's own 'not enough', no percentage",
       q["diagnosis"])
    thirty = [trade("win", 30 - i) for i in range(12)] + [trade("loss", 18 - i * 0.5)
                                                        for i in range(18)]
    qp.write_trades(thirty + [trade("", 0.5, status="open")], cf.PAPER_LEDGER)
    q = agent(cf.report(now=NOW), "quant")
    ok(q["status"] == "scored" and q["successRate"] == 0.4 and q["score"] == 52
       and q["ageHours"] == 0.5,
       "30 closed, 12 won, a trade opened 30 min ago: 0.8 x 0.4 + 0.2 x 1.0 = 52", str(q))
    ok(q["lastFailure"]["detail"] == cf._detail(qp.describe_close(thirty[-1])),
       "the Quant's last failure is quant_paper's own close line")

    # -----------------------------------------------------------------------------------
    head("6. the test ceiling")
    cf._write_cache({"tests": {"test_quant.py": {"exit": 0}, "test_quant_paper.py": {"exit": 2}}})
    q = agent(cf.report(now=NOW), "quant")
    ok(q["score"] == 25 and q["raw"] == 52 and q["capped"]
       and "Capped at 25% from 52% - test_quant_paper.py failed its last run" in q["diagnosis"],
       "a red test file caps 52 at 25, and says so", q["diagnosis"])
    cf._write_cache({"tests": {"test_quant.py": {"exit": None}}})
    q = agent(cf.report(now=NOW), "quant")
    ok(q["score"] == 25 and any("test_quant_paper.py not yet run" in n for n in q["notes"]),
       "a timed-out test is red; one never run is noted, not assumed green", str(q["notes"]))
    cf._write_cache({"tests": {"test_quant.py": {"exit": 0}, "test_quant_paper.py": {"exit": 0}}})
    ok(agent(cf.report(now=NOW), "quant")["score"] == 52, "both green: no ceiling")
    fake = os.path.join(TMP, "fakeroot")
    os.makedirs(fake)
    for name, code in (("test_green.py", 0), ("test_red.py", 3), ("test_confidence.py", 9)):
        with open(os.path.join(fake, name), "w") as fh:
            fh.write("print('  1 checks, %d failed')\nraise SystemExit(%d)\n" % (code, code))
    cf.HERE = fake
    got = cf.run_tests()
    cf.HERE = REAL["HERE"]
    cache = cf.read_cache()
    ok(set(got) == {"test_green.py", "test_red.py"} and cache["tests"]["test_red.py"]["exit"] == 3
       and cache["tests"]["test_green.py"]["exit"] == 0
       and cache["tests"]["test_red.py"]["summary"] == "1 checks, 3 failed",
       "run_tests(): each file's exit code and last line cached; it never runs itself", str(got))

    # -----------------------------------------------------------------------------------
    head("7. the overall number and the cache")
    clear()
    put(cf.JOBS_LEDGER, {"version": 1, "jobs": [job("director", "done", 1 + i) for i in range(4)]
                         + [job("newsletter", "done", 2), job("newsletter", "failed", 3),
                            job("newsletter", "failed", 1)]})
    rep = cf.report(now=NOW, write=False)
    ok(not os.path.exists(cf.CACHE_PATH), "report(write=False) writes nothing")
    ok(rep["overall"]["score"] == round((100 + round(100 * (0.8 / 3 + 0.2))) / 2)
       and rep["overall"]["over"] == ["Director", "Publisher"]
       and "No score for Broadcaster (no data), Scholar (no data), Quant (no data)"
       in rep["overall"]["sentence"], "the mean of the scored two, the other three named",
       rep["overall"]["sentence"])
    cf.report(now=NOW)
    ok(json.load(open(cf.CACHE_PATH, encoding="utf-8"))["report"]["overall"]["score"]
       == rep["overall"]["score"], "report() caches what it computed")
    ok(not os.path.exists(cf.CACHE_PATH + ".tmp"), "atomically: no .tmp left behind")
    ok([a["name"] for a in cf.weakest(rep)] == ["Publisher"], "the weakest is the lowest score")

    # -----------------------------------------------------------------------------------
    head("8. the chat")
    for q_, view in (("Galaxy ka confidence kitna hai", "overall"),
                     ("kaunsa agent sabse weak hai abhi", "weakest"),
                     ("Quant kitna reliable hai", "quant"),
                     ("how reliable is the Director", "director"),
                     ("Scholar pe kitna bharosa kar sakte hai", "scholar"),
                     ("which agent is the least reliable", "weakest")):
        ok(server.classify_query(q_) == ("confidence", False)
           and server.confidence_request(q_) == view, "%r -> confidence (%s)" % (q_, view),
           str((server.classify_query(q_), server.confidence_request(q_))))
    for q_, want in (("what is a confidence interval", None), ("how reliable is RSI", None),
                     ("Quant ka track record kya hai", "paper"),
                     ("Quant ki win rate batao", "paper"),
                     ("is the Samsung Galaxy S24 reliable", None),
                     ("is the director of Infosys trustworthy", None),
                     ("RSI of Reliance", "quant")):
        got = server.classify_query(q_)[0]
        ok(got != "confidence" and (want is None or got == want),
           "%r is not a confidence question (%s)" % (q_, got))
    st, p = server.answer_confidence("Galaxy ka confidence kitna hai", "test-confidence",
                                     "confidence")
    rep = p["confidence"]["report"]
    figures = ["%d%%" % rep["overall"]["score"]] + ["%d%%" % a["score"] for a in rep["agents"]
                                                    if a["score"] is not None]
    ok(st == 200 and p["route"] == "confidence" and all(f in p["answer"] for f in figures)
       and p["answer"].endswith(cf.NOTICE),
       "overall: every figure the report computed is in the answer, which ends measured-not-"
       "forecast", p["answer"])
    shown = set(re.findall(r"\b\d+%", p["answer"]))
    ok(shown <= set(figures), "and no percentage appears that the report did not compute",
       str(shown - set(figures)))
    st, p = server.answer_confidence("kaunsa agent sabse weak hai abhi", "test-confidence",
                                     "confidence")
    ok(p["answer"].startswith("The weakest right now: Publisher, at %d%%."
                              % agent(p["confidence"]["report"], "publisher")["score"])
       and "Not compared, for want of data: Broadcaster, Scholar, Quant." in p["answer"],
       "weakest: names the lowest, and who was not compared", p["answer"])
    st, p = server.answer_confidence("Quant kitna reliable hai", "test-confidence", "confidence")
    ok(p["answer"].startswith("Quant: no data - paper-ledger.json does not exist yet.")
       and "%" not in p["answer"], "the Quant with no ledger: no data, no figure", p["answer"])

    # -----------------------------------------------------------------------------------
    head("10. the trend, by hand")

    def runs_of(flags):
        return [{"ok": bool(f)} for f in flags]
    ok(cf.trend(runs_of([0, 0, 0, 1, 1, 1])) == "rising", "0 of 3, then 3 of 3: rising")
    ok(cf.trend(runs_of([1, 1, 1, 1, 1, 0])) == "falling", "3 of 3, then 2 of 3 (-0.33): falling")
    ok(cf.trend(runs_of([1, 1, 0, 0, 1, 0, 1, 0])) == "steady", "2 of 4, then 2 of 4: steady")
    ok(cf.trend(runs_of([1, 1, 1, 0, 1, 1, 1])) == "steady",
       "7 runs: the middle failure is in neither half, so 3 of 3 and 3 of 3 is steady")
    ok(cf.trend(runs_of([1] * 5)) == "early", "5 runs: halves too small to compare - early")

    # -----------------------------------------------------------------------------------
    head("11. the per-response line, read from the cache")
    clear()
    qp.write_trades(thirty, cf.PAPER_LEDGER)
    computed = {"n": 0}
    real_report = cf.report

    def counting(*a, **k):
        computed["n"] += 1
        return real_report(*a, **k)
    cf.report = counting
    real_quant = {n: getattr(server, n) for n in ("quant_reading", "call_model")}
    try:
        cf.forget()
        line = cf.agent_line("quant")
        q = agent(cf.cached(), "quant")
        ok(line == "Quant confidence: %d%% (falling)." % q["score"],
           "the line is the cached score and trend: %r (12 wins, then 18 losses: falling)" % line)
        st, p = server.answer_paper("Quant ka track record kya hai", "test-confidence", "paper")
        ok(st == 200 and p["answer"].endswith("\n\n" + line)
           and p["answer"].count("confidence:") == 1,
           "answer_paper ends with it, once", p["answer"])
        server.quant_reading = lambda req: {
            "symbol": "RELIANCE", "ticker": "RELIANCE.NS", "rsi": 72.31, "shown": "72.3",
            "zone": "overbought", "label": "RSI 72.3 - overbought zone (>70)",
            "asOf": "2026-10-08", "close": 1175.3, "bars": 125}
        server.call_model = lambda cfg, messages, image=None: (
            "Reliance closed on 8 October with an RSI of 72.3.", "")
        st, p = server.answer_quant({}, "RSI of Reliance", "test-confidence", [], "quant")
        ok(st == 200 and p["answer"].endswith(server.QUANT_DISCLAIMER + "\n\n" + line),
           "answer_quant ends with the risk line and then it", p["answer"])
        cf.health()
        ok(computed["n"] == 1,
           "a line, a cached read, two answers and a /health read: ONE ledger read", str(computed))
        cf._memo["at"] = time.monotonic() - cf.REFRESH_S - 1
        cf.agent_line("quant")
        cf.agent_line("quant")
        ok(computed["n"] == 2, "older than REFRESH_S: exactly one recompute, then cached again",
           str(computed))
        ok(not os.path.exists(cf.CACHE_PATH), "and nothing on the hot path wrote a file")
    finally:
        cf.report = real_report
        for n, v in real_quant.items():
            setattr(server, n, v)
    qp.write_trades(four, cf.PAPER_LEDGER)
    cf.forget()
    ok(cf.agent_line("quant") == "Quant confidence: -- (not enough data yet).",
       "4 trades: '--' and the reason, no number")
    os.remove(cf.PAPER_LEDGER)
    cf.forget()
    ok(cf.agent_line("quant") == "Quant confidence: -- (no data).", "no ledger: '--', no data")
    srv_tree = ast.parse(io.open(os.path.join(HERE, "server.py"), encoding="utf-8").read())

    def callers(dotted):
        out = set()
        for fn in [n for n in ast.walk(srv_tree) if isinstance(n, ast.FunctionDef)]:
            if any(isinstance(c, ast.Call) and ast.unparse(c.func) == dotted
                   for c in ast.walk(fn)):
                out.add(fn.name)
        return out
    ok(callers("confidence_tail") == {"answer_quant", "answer_paper"}
       and callers("confidence.agent_line") == {"confidence_tail"},
       "only the Quant's two answers carry the line - a general, current or knowledge answer "
       "never reaches it", str((callers("confidence_tail"), callers("confidence.agent_line"))))
    real_cached = cf.cached
    cf.cached = lambda: 1 / 0
    try:
        ok(cf.agent_line("quant") == "" and server.confidence_tail("quant") == ""
           and cf.health() == {"overall": None, "at": None, "agents": {}},
           "a meter that throws: no line, null health, and the answer is not touched")
    finally:
        cf.cached = real_cached

    # -----------------------------------------------------------------------------------
    head("12. /health and the tile")
    clear()
    cf.forget()
    httpd = ThreadingHTTPServer(("127.0.0.1", 0),
                                partial(server.GalaxyHandler, directory=server.VIEWER_DIR))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        url = "http://127.0.0.1:%d/health" % httpd.server_address[1]
        live = json.load(urllib.request.urlopen(url, timeout=120))
    finally:
        httpd.shutdown()
        httpd.server_close()
    conf = live.get("confidence")
    ok(isinstance(conf, dict) and conf.get("overall") is None
       and conf.get("agents") == {k: None for k, _n, _l, _j in cf.AGENTS},
       "the real /health handler, empty ledgers: confidence.overall null, every agent null",
       json.dumps(conf))
    page = io.open(os.path.join(HERE, "viewer", "index.html"), encoding="utf-8").read()
    fn = re.search(r"\n  function railConfidence\(data\) \{.*?\n  \}", page, re.S)
    ok(fn and "railSet('confidence', railConfidence(data)" in page,
       "the page paints the cell through railConfidence(), inside railFrom()")

    def tile(payloads):
        script = (fn.group(0) + "\nconsole.log(JSON.stringify(" + json.dumps(payloads)
                  + ".map(railConfidence)));")
        out = _proc.run(["node", "-e", script], capture_output=True, timeout=60)
        return json.loads(out.stdout.decode("utf-8") or "null")
    ok(tile([live, {"confidence": {"overall": None}}, {"confidence": {"overall": 87}},
             {"ok": True}]) == ["--", "--", "87%", ""],
       "in node: null -> '--', 87 -> '87%', an old server with no field -> an empty cell")
    shown = []
    # The cache reads the real clock, so these runs are an hour or two before the real now -
    # NOW-relative rows would drift out of the window on any later day this file is run.
    real_now = datetime.datetime.now()
    for n in range(1, cf.MIN_RUNS_TO_SCORE + 1):
        put(cf.JOBS_LEDGER, {"version": 1, "jobs": [
            {"at": (real_now - datetime.timedelta(hours=1 + i)).isoformat(timespec="seconds"),
             "name": "director", "outcome": "done", "detail": "done"} for i in range(n)]})
        cf.forget()
        shown.append(tile([{"confidence": cf.health()}])[0])
    ok(all(s == "--" for s in shown[:-1]) and re.fullmatch(r"\d+%", shown[-1] or ""),
       "1 and 2 runs: the tile reads '--'; the 3rd run (MIN_RUNS_TO_SCORE) is the first number",
       str(shown))
finally:
    for n, v in REAL.items():
        setattr(cf, n, v)
    cf.forget()

# ---------------------------------------------------------------------------------------
head("9. read-only and model-free")
src = io.open(os.path.join(HERE, "confidence.py"), encoding="utf-8").read()
tree = ast.parse(src)
imported = set()
for node in ast.walk(tree):
    if isinstance(node, ast.Import):
        imported |= {a.name.split(".")[0] for a in node.names}
    elif isinstance(node, ast.ImportFrom):
        imported.add((node.module or "").split(".")[0])
ok(imported <= {"datetime", "json", "os", "subprocess", "sys", "threading", "time",
                "quant_paper", "tools"},
   "confidence.py imports only stdlib basics, quant_paper and tools._proc", str(sorted(imported)))


def calls_in(fn_name_pred):
    """{enclosing function: [dotted call names]} across confidence.py."""
    out = {}
    for fn in [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]:
        for node in ast.walk(fn):
            if isinstance(node, ast.Call):
                name = ast.unparse(node.func)
                if fn_name_pred(name):
                    out.setdefault(fn.name, []).append(name)
    return out


ok(set(calls_in(lambda n: n.startswith(("subprocess.", "_proc.")))) == {"run_tests"}
   and calls_in(lambda n: n.startswith("subprocess.")) == {},
   "a process is started only inside run_tests(), and only through tools._proc")
writers = {}
for fn in [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]:
    for node in ast.walk(fn):
        if (isinstance(node, ast.Call) and ast.unparse(node.func) == "open"
                and any(isinstance(a, ast.Constant) and a.value in ("w", "a", "wb", "ab")
                        for a in node.args[1:2])):
            writers.setdefault(fn.name, 0)
ok(set(writers) == {"_write_cache"}, "a file is opened for writing only in _write_cache()",
   str(writers))
ok(not calls_in(lambda n: n in ("os.remove", "os.unlink", "shutil.rmtree", "os.rmdir")),
   "nothing is deleted")
replaces = calls_in(lambda n: n == "os.replace")
ok(set(replaces) == {"_write_cache"}, "and the one rename is the cache's own atomic write")
MODEL = re.compile(r"requests\.|urllib|http\.client|socket|call_model|assemble\(|groq|ollama|"
                   r"openrouter|anthropic|openai|gemini", re.I)
new_server = (inspect.getsource(server.confidence_request)
              + inspect.getsource(server.answer_confidence)
              + inspect.getsource(server.confidence_tail))
for name, text in (("confidence.py", src), ("server.py's new lines", new_server)):
    hits = sorted(set(m.group(0) for m in MODEL.finditer(text)))
    ok(not hits, "%s names no network call and no model" % name, str(hits))
EXEC = re.compile(r"place_?order|placeorder|order_?place|modify_?order|cancel_?order|"
                  r"kiteconnect|kite\.|smartapi|smart_api|upstox|zerodha|fyers|dhanhq|"
                  r"angel\s*one|5paisa|icicidirect|breeze|/orders\b|\bbroker(?:s|\s+api)?\b|"
                  r"access_token|api_secret|totp", re.I)
for name, text in (("confidence.py", src), ("server.py's new lines", new_server)):
    hits = sorted(set(m.group(0) for m in EXEC.finditer(text)))
    ok(not hits, "%s names no order-execution API or brokerage" % name, str(hits))
import jobs                                                    # noqa: E402
import scholar                                                 # noqa: E402
ok(cf.JOBS_RING == jobs.LEDGER_MAX and cf.STUDY_RING == scholar.LEDGER_HISTORY_MAX,
   "the copied ring sizes still equal jobs.py's and scholar.py's")
after = (os.path.getmtime(REAL["CACHE_PATH"]) if os.path.exists(REAL["CACHE_PATH"]) else None)
ok(after == REAL_CACHE_MTIME, "the real confidence-cache.json was never touched")

print("\n  %d checks, %d failed\n" % (checks, len(failures)))
if failures:
    for claim in failures:
        print("    FAILED: %s" % claim)
    print("")
sys.exit(min(len(failures), 120))
