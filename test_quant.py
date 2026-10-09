"""Proves the Quant's first indicator: an RSI asked of a named symbol is computed, not guessed.

Phase II.1 is one indicator on one symbol from end-of-day closes, and four things can go
wrong with it, each in a way that looks fine from the chair:

  1. THE CLASSIFIER STEALS A CONCEPT. "what is RSI" names no symbol, so it is a concept and
     must still reach KNOWLEDGE_PROMPT. Only "RSI of <a symbol>" is quant - and "mujhe
     Reliance ka RSI batao" is quant even though "mujhe" is a personal pointer.
  2. THE RESOLVER GUESSES. A name must match an alias EXACTLY. "reliance power" is not
     Reliance, "hdfc" alone is three companies, and "xyzabc123" is nobody: each is refused
     out loud, and the refusal never fetches and never asks a model.
  3. THE ARITHMETIC IS WRONG. wilder_rsi() is checked against the standard worked example
     (the StockCharts RSI table: 33 closes, first RSI 70.53), and at its edges.
  4. THE REPLY GIVES ADVICE OR LOSES THE RISK LINE. The risk line is appended by the server,
     verbatim, to every reading; a model reply that says "buy", carries a tag, loses the
     figure, or fails outright is replaced by the template. Checked with a stubbed model.
  5. A SESSION STILL TRADING IS NOT A CLOSE. Before 16:00 IST the bar dated today is
     dropped; after it, kept. Checked with a stubbed yfinance and an injected clock.

Nothing here touches the network: yfinance and the model are both stubbed.

Run it:  python test_quant.py
Exit status is the number of failures.
"""

import datetime
import os
import sys
import types

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:                                              # noqa: BLE001
    pass

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
    """Raised by something that should never have been called."""


def bomb(*args, **kwargs):
    raise Exploded("called when nothing should have been")


# ---------------------------------------------------------------------------------------
head("1. the classifier: a named symbol is quant, a concept is not")
QUANT = [
    ("RSI of Reliance", "RELIANCE"),
    ("Reliance ka RSI kya hai", "RELIANCE"),
    ("nifty RSI", "NIFTY"),
    ("bank nifty ka RSI batao", "BANKNIFTY"),
    ("banknifty rsi", "BANKNIFTY"),
    ("mujhe reliance ka rsi batao", "RELIANCE"),
    ("what is the RSI of Reliance today", "RELIANCE"),
    ("abhi Nifty 50 ka RSI kitna hai?", "NIFTY"),
    ("relative strength index of TCS", "TCS"),
    ("L & T ka RSI", "LT"),
    ("Reliance's RSI", "RELIANCE"),
    ("sensex rsi", "SENSEX"),
]
for q, sym in QUANT:
    cls = server.classify_query(q)
    req = server.quant_request(q) or {}
    ok(cls == ("quant", True) and req.get("symbol") == sym,
       "%r -> quant, %s" % (q, sym), "got %s %s" % (cls, req))

NOT_QUANT = [
    ("what is RSI", ("general", True)),
    ("explain RSI", ("general", True)),
    ("RSI kya hota hai", ("general", True)),
    ("how is RSI calculated", ("general", True)),
    ("what is RSI in trading", ("general", True)),
    ("what is the RSI of a stock", ("general", True)),
    ("what is compound interest", ("general", True)),
    ("what is react", ("general", False)),
    ("NSE vs BSE", ("current", True)),
]
for q, want in NOT_QUANT:
    got = server.classify_query(q)
    ok(got == want, "%r -> %s, as before" % (q, want), "got %s" % (got,))
for q in ("is RSI reliable", "my portfolio ka RSI"):
    ok(server.quant_request(q) is None,
       "%r is not a quant question (no symbol, or their own things)" % q)
ok("quant" in server.QUERY_CLASSES, "quant is a declared query class")

# ---------------------------------------------------------------------------------------
head("2. the resolver: exact aliases, and a refusal rather than a guess")
for q, name in (("RSI of xyzabc123", "xyzabc123"), ("reliance power ka RSI", "reliance power"),
                ("hdfc ka rsi", "hdfc"), ("RSI for tata motors", "tata motors")):
    req = server.quant_request(q) or {}
    ok(server.classify_query(q)[0] == "quant" and req.get("symbol") is None
       and req.get("name") == name,
       "%r is quant with no symbol (name %r)" % (q, name), "got %s" % req)
tickers = [t for _s, t, _a in server.QUANT_LISTINGS]
ok(len(set(tickers)) == len(tickers), "every listing has its own Yahoo ticker")
ok(all(t.endswith(".NS") or t.startswith("^") for t in tickers),
   "every ticker is an NSE equity (.NS) or an index (^)")
ok(server.QUANT_ALIASES["bank nifty"][0] == "BANKNIFTY"
   and server.QUANT_ALIASES["nifty"][0] == "NIFTY",
   "bank nifty and nifty are different symbols")

# ---------------------------------------------------------------------------------------
head("3. the arithmetic: Wilder's RSI(14) against the standard worked example")
# StockCharts' RSI table: 33 closes; the first RSI is on close 15, and the next 18 follow.
CLOSES = [44.3389, 44.0902, 44.1497, 43.6124, 44.3278, 44.8264, 45.0955, 45.4245, 45.8433,
          46.0826, 45.8931, 46.0328, 45.6140, 46.2820, 46.2820, 46.0028, 46.0328, 46.4116,
          46.2222, 45.6439, 46.2122, 46.2521, 45.7137, 46.4515, 45.7835, 45.3548, 44.0288,
          44.1783, 44.2181, 44.5672, 43.4205, 42.6628, 43.1314]
EXPECTED = [70.53, 66.32, 66.55, 69.41, 66.36, 57.97, 62.93, 63.26, 56.06, 62.38, 54.71,
            50.42, 39.99, 41.46, 41.87, 45.46, 37.30, 33.08, 37.77]
got = [round(server.wilder_rsi(CLOSES[:n]), 2) for n in range(15, len(CLOSES) + 1)]
ok(got == EXPECTED, "all 19 RSI values match the table to two places", "got %s" % got)
ok(server.wilder_rsi(CLOSES[:14]) is None, "14 closes are one too few for RSI(14)")
ok(server.wilder_rsi([float(i) for i in range(30)]) == 100.0, "nothing fell: RSI 100")
ok(server.wilder_rsi([5.0] * 30) == 50.0, "nothing moved: RSI 50")
ok(server.wilder_rsi([float(30 - i) for i in range(30)]) == 0.0, "nothing rose: RSI 0")

head("   the zones, on the figure as shown")
for value, zone, label in ((72.04, "overbought", "RSI 72.0 - overbought zone (>70)"),
                           (70.04, "neutral", "RSI 70.0 - neutral range (30-70)"),
                           (51.3, "neutral", "RSI 51.3 - neutral range (30-70)"),
                           (30.0, "neutral", "RSI 30.0 - neutral range (30-70)"),
                           (28.4, "oversold", "RSI 28.4 - oversold zone (<30)")):
    ok(server.rsi_zone(value) == (zone, label), "%.2f -> %s" % (value, label),
       "got %s" % (server.rsi_zone(value),))

# ---------------------------------------------------------------------------------------
head("4. the reply: the number from the server, the risk line from the server")
READING = {"symbol": "RELIANCE", "ticker": "RELIANCE.NS", "rsi": 72.31, "shown": "72.3",
           "zone": "overbought", "label": "RSI 72.3 - overbought zone (>70)",
           "asOf": "2026-10-08", "close": 1175.3, "bars": 125}
real = {n: getattr(server, n) for n in ("quant_reading", "call_model", "daily_closes")}


def ask(question, said=None, error="", reading=READING):
    calls = []

    def model(cfg, messages, image=None):
        calls.append(messages)
        return said, error
    server.quant_reading = (lambda req: dict(reading)) if reading is not None else bomb
    server.call_model = model if said is not None or error else bomb
    try:
        status, payload = server.answer_quant({}, question, "test-quant", [], "quant")
    finally:
        for n, fn in real.items():
            setattr(server, n, fn)
    return status, payload, calls


GOOD = "Reliance closed on 8 October with an RSI of 72.3, which sits in the overbought zone."
status, p, calls = ask("RSI of Reliance", said=GOOD)
ok(status == 200 and p["route"] == "quant" and p["qclass"] == "quant",
   "200, route quant, qclass quant")
ok(p["symbol"] == "RELIANCE" and p["rsi"] == 72.31 and p["zone"] == "overbought"
   and p["asOf"] == "2026-10-08", "the payload carries symbol, rsi, zone and asOf")
ok(p["nodes"] == [] and p["kind"] == "compose", "same shape as the knowledge route")
ok(p["answer"].startswith(GOOD), "a clean model reply is kept as it was")
ok(p["answer"].endswith("\n\n" + server.QUANT_DISCLAIMER),
   "and the risk line is appended to it, verbatim")
ok(len(calls) == 1 and calls[0][0]["content"].startswith(server.QUANT_PROMPT),
   "one model call, on QUANT_PROMPT")
ok("RSI 72.3 - overbought zone (>70)" in calls[0][-1]["content"],
   "the computed reading is handed to the model as evidence")

for said, why in (("RSI is 72.3, overbought. A good time to sell, sir.", "says sell"),
                  ("72.3 and overbought - book profits before the target of 1200.",
                   "names a target"),
                  ("72.3 overbought, sure-shot reversal coming.", "says sure-shot"),
                  ("Reliance ko abhi kharid lo, RSI 72.3 hai.", "says kharid"),
                  ("Reliance is in the overbought zone.", "drops the figure"),
                  ("RSI 72.3, overbought. [[brain: llama]]", "carries a tag")):
    status, p, _c = ask("RSI of Reliance", said=said)
    ok(status == 200 and p["answer"] == server.quant_template(READING) + "\n\n"
       + server.QUANT_DISCLAIMER,
       "a reply that %s is replaced by the template, risk line kept" % why,
       "got %r" % p["answer"])
TAILS = (" *This is a technical reading, not financial advice.*",
         " Please note this is not a trade recommendation.",
         " Markets are subject to risk.")
for tail in TAILS:
    status, p, _c = ask("RSI of Reliance", said=GOOD + tail)
    ok(p["answer"] == GOOD + "\n\n" + server.QUANT_DISCLAIMER,
       "a disclaimer the model wrote itself is removed - one risk line, the fixed one (%s)"
       % tail.strip()[:40], "got %r" % p["answer"])
status, p, _c = ask("RSI of Reliance", error="every engine is down")
ok(status == 200 and p["rsi"] == 72.31
   and p["answer"].startswith(server.quant_template(READING))
   and p["answer"].endswith(server.QUANT_DISCLAIMER),
   "every engine down: the template still reports the reading, with the risk line")
ok(not server.QUANT_ADVICE_RE.search(server.quant_template(READING) + server.QUANT_DISCLAIMER),
   "and neither the template nor the risk line trips the advice check")
ok(not server.QUANT_ADVICE_RE.search(GOOD + " Overbought, oversold, selling pressure."),
   "the advice check does not fire on overbought, oversold or selling")

# MEASURED 2026-10-09: BANKNIFTY's raw RSI was 36.446. The label said 36.4, the model said
# 36.4, and the figure check looked for round(round(36.446, 2), 1) = 36.5 - so a correct
# reply was thrown away for the template. The check must read the label's own figure.
real_closes = server.daily_closes
server.daily_closes = lambda ticker, now=None: (
    [datetime.date(2026, 10, 8)] * 3, [1.0, 2.0, 3.0], "")
real_calc = server.QUANT_CALCULATORS["rsi"]
server.QUANT_CALCULATORS["rsi"] = lambda closes: 36.446
try:
    r = server.quant_reading(server.quant_request("bank nifty ka RSI"))
finally:
    server.daily_closes = real_closes
    server.QUANT_CALCULATORS["rsi"] = real_calc
ok(r["rsi"] == 36.45 and r["shown"] == "36.4" and r["label"].startswith("RSI 36.4 "),
   "36.446 is shown as 36.4 in label and check alike, never double-rounded to 36.5",
   "got %s" % r)
status, p, _c = ask("bank nifty ka RSI", reading=r,
                    said="BANKNIFTY's RSI stands at 36.4, in the neutral range.")
ok(p["answer"].startswith("BANKNIFTY's RSI stands at 36.4"),
   "so a reply that says 36.4 is kept", "got %r" % p["answer"])

head("   the refusals: no fetch, no model")
status, p, _c = ask("RSI of xyzabc123", reading=None)
ok(status == 200 and p["answer"] == "xyzabc123 ko kis exchange symbol se match karu, pata nahi."
   and p["symbol"] is None and p["rsi"] is None and p["route"] == "quant",
   "an unknown name says pata nahi, and neither fetches nor asks a model",
   "got %s" % p)
status, p, _c = ask("RSI of Reliance", reading={"error": "network down"})
ok(status == 502 and "network down" in p["error"] and "answer" not in p,
   "a failed fetch is a 502 with the reason, and no number is invented")

# ---------------------------------------------------------------------------------------
head("5. a session still trading is not a close")


class FakeSeries:
    def __init__(self, dates, values):
        self.index, self._values = dates, values

    def dropna(self):
        return self

    def __iter__(self):
        return iter(self._values)


IST = server._IST
DAYS = [datetime.datetime(2026, 10, d, tzinfo=IST) for d in (6, 7, 8, 9)]
fake = types.ModuleType("yfinance")
fake.Ticker = lambda t: types.SimpleNamespace(
    history=lambda **kw: {"Close": FakeSeries(DAYS, [10.0, 11.0, 12.0, 13.0])})
saved = sys.modules.get("yfinance")
sys.modules["yfinance"] = fake
try:
    d, c, e = server.daily_closes("X", now=datetime.datetime(2026, 10, 9, 11, 25, tzinfo=IST))
    ok(not e and c == [10.0, 11.0, 12.0] and d[-1].isoformat() == "2026-10-08",
       "at 11:25 IST the bar dated today is dropped", "got %s %s %s" % (d, c, e))
    d, c, e = server.daily_closes("X", now=datetime.datetime(2026, 10, 9, 16, 5, tzinfo=IST))
    ok(c == [10.0, 11.0, 12.0, 13.0], "at 16:05 IST it is a close, and kept")
    d, c, e = server.daily_closes("X", now=datetime.datetime(2026, 10, 10, 9, 0, tzinfo=IST))
    ok(c == [10.0, 11.0, 12.0, 13.0], "on Saturday morning Friday's bar is kept")
    fake.Ticker = lambda t: types.SimpleNamespace(history=bomb)
    d, c, e = server.daily_closes("X")
    ok(c == [] and "could not fetch" in e, "a transport error comes back as a reason")
finally:
    if saved is not None:
        sys.modules["yfinance"] = saved
    else:
        sys.modules.pop("yfinance", None)

print("\n  %d checks, %d failed\n" % (checks, len(failures)))
if failures:
    for claim in failures:
        print("    FAILED: %s" % claim)
    print("")
sys.exit(min(len(failures), 120))
