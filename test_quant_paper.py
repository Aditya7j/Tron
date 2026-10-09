"""Proves the Quant's paper desk: hypothetical trades, followed honestly, reported honestly.

  1. THE MATH. rsi_series() agrees with server.wilder_rsi() to the last digit; EMA and ATR
     match hand-computed values.
  2. THE SETUP. signal_at() fires a long only in an uptrend on RSI crossing up through 40, a
     short only in a downtrend crossing down through 60, never outside 09:30-15:00, and never
     against a stretched daily RSI.
  3. THE EXIT. advance() closes at the target, at the stop, at the 15:20 time exit - and when
     one bar touches both levels, at the STOP, because the bar does not say which came first.
  4. THE LIVE LIFECYCLE. tick() opens a trade on one tick and closes it on a later one, in a
     temporary ledger, through the same code the daemon runs. Prices are stubbed.
  5. THE KILL SWITCH. With quant-paper.off present no trade opens - and an open one is still
     followed to its exit.
  6. THE RECORD. With 0 or 4 trades it says "not enough", with no percentage anywhere; a win
     rate appears only at MIN_TRADES_TO_JUDGE, and no sentence claims a number it did not
     measure.
  7. THE CHAT. The three questions route to "paper"; every trade shown ends with the
     SIMULATED line; "what is paper trading" stays a concept.
  8. NOTHING HERE CAN TRADE. quant_paper.py imports only what it needs to read prices and
     news, and neither file names an execution API.

Nothing touches the network or the real ledger.

Run it:  python test_quant_paper.py
Exit status is the number of failures.
"""

import ast
import datetime
import io
import os
import re
import sys
import tempfile

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:                                              # noqa: BLE001
    pass

import quant_paper as qp                                       # noqa: E402
import server                                                  # noqa: E402

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


IST = qp.IST


def at(h, m, day=9):
    return datetime.datetime(2026, 10, day, h, m, tzinfo=IST)


def bar(t, o, h, l, c):
    return {"t": t, "o": o, "h": h, "l": l, "c": c}


# ---------------------------------------------------------------------------------------
head("1. the math")
CLOSES = [44.3389, 44.0902, 44.1497, 43.6124, 44.3278, 44.8264, 45.0955, 45.4245, 45.8433,
          46.0826, 45.8931, 46.0328, 45.6140, 46.2820, 46.2820, 46.0028, 46.0328, 46.4116,
          46.2222, 45.6439, 46.2122, 46.2521, 45.7137, 46.4515, 45.7835, 45.3548, 44.0288,
          44.1783, 44.2181, 44.5672, 43.4205, 42.6628, 43.1314]
rs = qp.rsi_series(CLOSES)
ok(all(rs[n - 1] == server.wilder_rsi(CLOSES[:n]) for n in range(15, len(CLOSES) + 1)),
   "rsi_series() equals server.wilder_rsi() at every close, exactly")
ok(rs[:14] == [None] * 14 and round(rs[14], 2) == 70.53, "None until the seed, then 70.53")
ok(qp.ema([1, 2, 3, 4, 5], 3) == [None, None, 2.0, 3.0, 4.0], "EMA(3) seeded with the mean")
atr = qp.atr_series([11, 12, 13, 12], [9, 10, 11, 10], [10, 11, 12, 11], 2)
ok(atr == [None, None, 2.0, 2.0], "ATR(2) on true ranges 2, 2, 2", "got %s" % atr)

# ---------------------------------------------------------------------------------------
head("2. the setup")


def ind_for(fast, slow, rsi_prev, rsi, atr_v=20.0):
    return {"emaFast": [None, fast], "emaSlow": [None, slow], "rsi": [rsi_prev, rsi],
            "atr": [None, atr_v]}


B = [bar(at(10, 25), 0, 0, 0, 22000), bar(at(10, 30), 0, 0, 0, 22010)]   # closes 10:35
s = qp.signal_at(B, ind_for(22000, 21980, 38.0, 42.0), 1, 55.0)
ok(s and s["direction"] == "long", "uptrend + RSI up through 40 -> long")
ok(s and any("40" in r for r in s["reasons"]) and s["snapshot"]["atr"] == 20.0,
   "and the reasons and indicators are recorded with it")
s = qp.signal_at(B[:1] + [bar(at(10, 30), 0, 0, 0, 21950)], ind_for(21960, 21990, 63.0, 58.0),
                 1, 45.0)
ok(s and s["direction"] == "short", "downtrend + RSI down through 60 -> short")
ok(qp.signal_at(B, ind_for(21980, 22000, 38.0, 42.0), 1, 55.0) is None,
   "RSI up through 40 in a DOWNtrend is no long")
ok(qp.signal_at(B, ind_for(22000, 21980, 41.0, 45.0), 1, 55.0) is None,
   "no cross (already above 40) -> nothing")
ok(qp.signal_at(B, ind_for(22000, 21980, 38.0, 42.0), 1, 74.0) is None,
   "daily RSI 74 (stretched) blocks a new long")
early = [bar(at(9, 15), 0, 0, 0, 22000), bar(at(9, 20), 0, 0, 0, 22010)]  # closes 09:25
ok(qp.signal_at(early, ind_for(22000, 21980, 38.0, 42.0), 1, 55.0) is None,
   "nothing before 09:30")
late = [bar(at(15, 0), 0, 0, 0, 22000), bar(at(15, 5), 0, 0, 0, 22010)]   # closes 15:10
ok(qp.signal_at(late, ind_for(22000, 21980, 38.0, 42.0), 1, 55.0) is None,
   "nothing after 15:00")

# ---------------------------------------------------------------------------------------
head("3. the exit")
SIG = {"direction": "long", "reasons": ["trend up", "pullback over"], "atr": 20.0,
       "snapshot": {"atr": 20.0}}
T = qp.open_trade("NIFTY", "^NSEI", B[1], 22010.0, SIG, "live", at(10, 35))
ok(T["target"] == 22055.0 and T["stop"] == 21980.0, "long: target +2.25 ATR, stop -1.5 ATR")
won = qp.advance(T, [bar(at(10, 35), 22010, 22030, 22000, 22025),
                     bar(at(10, 40), 22025, 22060, 22020, 22050)])
ok(won["status"] == "closed" and won["exitReason"] == "target" and won["outcome"] == "win"
   and won["pnlPts"] == 45.0 and won["exit"] == 22055.0, "target touched -> win, +45 points")
lost = qp.advance(T, [bar(at(10, 35), 22010, 22015, 21975, 21990)])
ok(lost["outcome"] == "loss" and lost["pnlPts"] == -30.0, "stop touched -> loss, -30 points")
both = qp.advance(T, [bar(at(10, 35), 22010, 22070, 21970, 22050)])
ok(both["exitReason"] == "stop", "one bar touches both -> the stop, never the flattering one")
timed = qp.advance(T, [bar(at(15, 10), 22010, 22020, 22000, 22040),
                       bar(at(15, 15), 22040, 22045, 22030, 22041)])
ok(timed["exitReason"] == "time" and timed["outcome"] == "win" and timed["pnlPts"] == 31.0,
   "neither touched by 15:20 -> time exit at the close, judged on points")
flat = qp.advance(T, [bar(at(15, 15), 22010, 22015, 22005, 22011)])
ok(flat["outcome"] == "breakeven", "a time exit within 0.1 ATR is breakeven")
ok(qp.advance(T, [bar(at(10, 30), 22010, 22100, 21900, 22010)])["status"] == "open",
   "the signal bar itself is never judged against its own trade")

# ---------------------------------------------------------------------------------------
head("4. the live lifecycle, through tick(), in a temporary ledger")
tmp = tempfile.mkdtemp()
real = {n: getattr(qp, n) for n in ("LEDGER_PATH", "HALT_PATH", "fetch_bars", "fetch_daily",
                                    "signal_at")}
qp.LEDGER_PATH = os.path.join(tmp, "paper-ledger.json")
qp.HALT_PATH = os.path.join(tmp, "quant-paper.off")
FEED = {}
qp.fetch_bars = lambda ticker, period="5d", now=None: (
    [b for b in FEED.get(ticker, []) if b["t"] + qp.BAR <= now], 22012.0, "")
qp.fetch_daily = lambda ticker, now=None: []
fires = {"on": True}
qp.signal_at = lambda bars, ind, i, d: (dict(SIG) if fires["on"] and bars[i]["t"] == at(10, 30)
                                        else None)
desk = qp.PaperDesk()
desk.headlines = lambda symbol, name, day: [{"title": "a headline", "host": "example.org"}]
try:
    FEED["^NSEI"] = [bar(at(10, 25), 22000, 22005, 21995, 22000),
                     bar(at(10, 30), 22000, 22012, 21998, 22010)]
    desk.tick(now=at(10, 35, 9) + datetime.timedelta(seconds=20))
    book = qp.read_trades()
    ok(len(book) == 1 and book[0]["status"] == "open" and book[0]["entry"] == 22012.0
       and book[0]["mode"] == "live", "tick 1 opens one live trade at the price of that moment",
       "got %s" % book)
    ok(book and book[0]["news"] == [{"title": "a headline", "host": "example.org"}]
       and book[0]["dataLagS"] == 20, "with its headlines and its data lag recorded")
    desk.tick(now=at(10, 40) + datetime.timedelta(seconds=20))
    ok(len(qp.read_trades()) == 1, "the same bar never opens a second trade")
    FEED["^NSEI"].append(bar(at(10, 35), 22010, 22060, 22008, 22050))
    desk.tick(now=at(10, 40) + datetime.timedelta(seconds=25))
    book = qp.read_trades()
    ok(len(book) == 1 and book[0]["status"] == "closed" and book[0]["outcome"] == "win"
       and book[0]["exit"] == book[0]["target"],
       "tick 3 closes it at the target - open -> close, through the daemon's own code",
       "got %s" % book)
    ok(os.path.exists(qp.LEDGER_PATH) and not os.path.exists(real["LEDGER_PATH"] + ".tmp"),
       "the ledger is written atomically, to the temporary path only")

    head("5. the kill switch")
    open(qp.HALT_PATH, "w").close()
    qp.write_trades([])
    desk._seen.clear()
    FEED["^NSEI"] = FEED["^NSEI"][:2]
    desk.tick(now=at(10, 35) + datetime.timedelta(seconds=20))
    ok(qp.read_trades() == [] and qp.halted(), "halted: the same setup opens nothing")
    os.remove(qp.HALT_PATH)
    desk._seen.clear()
    desk.tick(now=at(10, 35) + datetime.timedelta(seconds=20))
    ok(len(qp.read_trades()) == 1, "switch removed: it opens again, with no restart")
    open(qp.HALT_PATH, "w").close()
    FEED["^NSEI"].append(bar(at(10, 35), 22010, 22015, 21970, 21990))
    desk.tick(now=at(10, 40) + datetime.timedelta(seconds=25))
    book = qp.read_trades()
    ok(book[0]["status"] == "closed" and book[0]["outcome"] == "loss",
       "halted: the trade already open is still followed to its exit (a stop, here)")
    os.remove(qp.HALT_PATH)

    head("   a slow tick does not hold up a question")
    import threading
    import time as _time
    fast_fetch = qp.fetch_bars

    def slow_fetch(ticker, period="5d", now=None):
        _time.sleep(2.5)
        return fast_fetch(ticker, period, now)
    qp.fetch_bars = slow_fetch
    worker = threading.Thread(target=desk.tick,
                              kwargs={"now": at(10, 45) + datetime.timedelta(seconds=20)})
    worker.start()
    _time.sleep(0.2)
    t0 = _time.perf_counter()
    st, p = server.answer_paper("Quant ka track record kya hai", "test-paper", "paper")
    took = _time.perf_counter() - t0
    ok(worker.is_alive() and st == 200 and took < 0.5,
       "a question answered in %.0f ms while a tick sat 2.5 s inside its fetch" % (took * 1000))
    worker.join()
    qp.fetch_bars = fast_fetch
    ok(desk.tick(now=at(18, 0))["skipped"] == "market closed",
       "evenings with nothing open: no fetch at all")
    ok(desk.tick(now=datetime.datetime(2026, 10, 10, 11, 0, tzinfo=IST))["skipped"]
       == "market closed", "Saturday: no fetch at all")
finally:
    for n, v in real.items():
        setattr(qp, n, v)

# ---------------------------------------------------------------------------------------
head("6. the record says only what it measured")


def closed(outcome, pnl):
    t = dict(T, status="closed", outcome=outcome, pnlPts=pnl, exit=0.0, exitReason="target")
    return t


r = qp.track_record([])
ok(r["closed"] == 0 and r["winRate"] is None and "not enough data" in r["sentence"]
   and "%" not in r["sentence"], "0 trades: no track record, said plainly")
four = [closed("win", 40), closed("win", 30), closed("loss", -25), closed("loss", -20)]
r = qp.track_record(four)
ok(r["winRate"] is None and r["sentence"].startswith("Only 4 paper-trades closed so far")
   and "not enough to judge accuracy yet" in r["sentence"] and "%" not in r["sentence"],
   "4 trades: 'only 4 ... not enough to judge accuracy yet', and no percentage",
   r["sentence"])
dry = [dict(t, mode="dryrun") for t in four * 10]
ok(qp.track_record(dry)["closed"] == 0, "dry-run trades never count toward the record")
many = [closed("win", 40)] * 12 + [closed("loss", -25)] * 17 + [closed("breakeven", 1)]
r = qp.track_record(many)
ok(r["enough"] and r["winRate"] == 40.0 and r["avgWinPts"] == 40.0
   and r["avgLossPts"] == -25.0 and "measured win rate of 40.0%" in r["sentence"],
   "30 trades: the measured rate, average win and average loss", r["sentence"])
claims = re.compile(r"\b\d+\s*(?:-|to|or)\s*\d+\s+out\s+of\s+10\b|\bout\s+of\s+10\b|"
                    r"\b(?:target|expected|aim\w*)\s+(?:accuracy|win\s*rate)\b", re.I)
src = io.open(os.path.join(HERE, "quant_paper.py"), encoding="utf-8").read()
ok(not claims.search(src), "quant_paper.py states no accuracy target about itself")

# ---------------------------------------------------------------------------------------
head("7. the chat")
for q, view in (("Quant ka track record kya hai", "record"), ("koi open setup hai abhi", "open"),
                ("aaj ke paper trades dikhao", "today"), ("Quant ki win rate batao", "record")):
    ok(server.classify_query(q) == ("paper", True) and server.paper_request(q) == view,
       "%r -> paper (%s)" % (q, view))
for q, want in (("what is paper trading", "general"), ("RSI of Reliance", "quant"),
                ("what is the accuracy of RSI", "general"), ("show my open positions", None)):
    got = server.classify_query(q)[0]
    ok(got != "paper" and (want is None or got == want), "%r is not a paper question (%s)"
       % (q, got))
real_read = qp.read_trades
try:
    today = datetime.datetime.now(IST).replace(hour=10, minute=35, second=0, microsecond=0)
    t_open = dict(T, openedAt=today.isoformat(), id="pt-a")
    t_won = dict(won, openedAt=today.isoformat(), id="pt-b")
    qp.read_trades = lambda path=None: [t_open, t_won, dict(t_won, mode="dryrun", id="pt-c")]
    st, p = server.answer_paper("aaj ke paper trades dikhao", "test-paper", "paper")
    ok(st == 200 and p["route"] == "paper" and len(p["paper"]["trades"]) == 2,
       "today: both live trades, the dry-run one left out")
    blocks = p["answer"].split("\n\n")[1:]
    ok(len(blocks) == 2 and all(b.endswith(qp.NOTICE) for b in blocks),
       "every trade shown ends with the SIMULATED line", p["answer"])
    st, p = server.answer_paper("koi open setup hai abhi", "test-paper", "paper")
    ok(len(p["paper"]["trades"]) == 1 and "still open" in p["answer"]
       and p["answer"].endswith(qp.NOTICE), "open: the one open trade, with its line")
    st, p = server.answer_paper("Quant ka track record kya hai", "test-paper", "paper")
    ok("Only 1 paper-trade closed so far" in p["answer"] and "%" not in p["answer"]
       and "not real positions, not advice" in p["answer"],
       "record: one closed trade is 'not enough', no percentage", p["answer"])
    qp.read_trades = lambda path=None: []
    st, p = server.answer_paper("Quant ka track record kya hai", "test-paper", "paper")
    ok("not enough data" in p["answer"] and p["paper"]["record"]["winRate"] is None,
       "record with an empty ledger: not enough data, no figure")
finally:
    qp.read_trades = real_read

# ---------------------------------------------------------------------------------------
head("8. nothing here can trade")
tree = ast.parse(src)
imported = set()
for node in ast.walk(tree):
    if isinstance(node, ast.Import):
        imported |= {a.name.split(".")[0] for a in node.names}
    elif isinstance(node, ast.ImportFrom):
        imported.add((node.module or "").split(".")[0])
ok(imported <= {"datetime", "json", "os", "sys", "threading", "time", "yfinance", "search"},
   "quant_paper.py imports only stdlib basics, yfinance and search.py", str(sorted(imported)))
EXEC = re.compile(r"place_?order|placeorder|order_?place|modify_?order|cancel_?order|"
                  r"kiteconnect|kite\.|smartapi|smart_api|upstox|zerodha|fyers|dhanhq|"
                  # \bbroker\b, not "broker": FINANCE_RE has long named "brokerage" as a
                  # finance CONCEPT a question may ask about, and that is not a connection.
                  r"angel\s*one|5paisa|icicidirect|breeze|/orders\b|\bbroker(?:s|\s+api)?\b|"
                  r"access_token|"
                  r"api_secret|totp", re.I)
server_src = io.open(os.path.join(HERE, "server.py"), encoding="utf-8").read()
for name, text in (("quant_paper.py", src), ("server.py", server_src)):
    hits = sorted(set(m.group(0) for m in EXEC.finditer(text)))
    ok(not hits, "%s names no order-execution API or brokerage" % name, str(hits))

print("\n  %d checks, %d failed\n" % (checks, len(failures)))
if failures:
    for claim in failures:
        print("    FAILED: %s" % claim)
    print("")
sys.exit(min(len(failures), 120))
