"""THE QUANT'S PAPER DESK - Phase II.2. A daemon that looks for setups on NIFTY and BANKNIFTY
during market hours, opens HYPOTHETICAL trades when one appears, follows each one against real
prices until its target, its stop or the clock closes it, and keeps the score.

IT TRADES NOTHING. Every row this file writes is a logged hypothesis: an entry price that was
the real market price at that moment and was not bought, a target and a stop that were stated
in advance, and an outcome measured afterwards. There is no account here, no credential, no
connection to anyone who could fill an instruction, and nothing that pretends to be one - not
disabled, not commented out, not stubbed. test_quant_paper.py reads this file's own source
and its imports to hold that.

WHAT IT READS
    Prices: yfinance, the same source as Phase II.1. Five-minute bars for the trade and daily
    closes for context. The bar still forming is dropped; only completed bars are judged.
    News: search.py's public backends (searxng when configured, ddg-lite, ddg-html,
    wikipedia) - never the keyed one, because the caller hands in a config holding nothing
    but the searxng URL. Headlines are recorded beside a trade as CONTEXT for whoever audits
    it; they do not vote. A headline's tone read by keyword is noise, and read by a model it is
    an unauditable opinion made on every tick - neither belongs in a first version.

WHAT IT DOES NOT COVER, AND WHY
    Option chains (PE/CE). Asked on 2026-10-09, Yahoo returned no expiries at all for ^NSEI,
    ^NSEBANK, NIFTY.NS or BANKNIFTY.NS. Pricing a contract without its chain would mean
    inventing the premium, so the universe is the two indices until a chain source is agreed.

THE TOOLKIT, AND WHY THIS MUCH AND NO MORE (all on 5-minute bars unless said otherwise)
    EMA(20) vs EMA(50)   the trend. A pullback is only bought in an uptrend and only sold in a
                         downtrend, because a pullback against the trend is just the trend.
    RSI(14), Wilder      the trigger. In an uptrend, RSI crossing back UP through 40 says the
                         dip has stopped falling; in a downtrend, crossing DOWN through 60 says
                         the bounce has stopped rising. Same formula as server.wilder_rsi().
    ATR(14), Wilder      the size of the move. Stop 1.5 x ATR away, target 2.25 x ATR away -
                         a 1.5 : 1 reward to risk, scaled to how much the index is actually
                         moving today rather than to a fixed number of points.
    Daily RSI(14)        the context. No new long when the daily reading is above 70 and no
                         new short when it is below 30: a stretched daily move is the one
                         place a five-minute pullback is least likely to resume.
    LEFT OUT: MACD (it is EMA(12) minus EMA(26) - a second reading of the trend the EMA pair
    already gives); volume spikes and VWAP (Yahoo reports zero volume for both indices, every
    bar); support/resistance levels (choosing the pivots is a judgement call, and an ATR
    stop is the mechanical version of the same idea that anyone can recompute).

THE RULES OF THE DAY (IST, NSE: 09:15-15:30, Monday to Friday)
    No entry before 09:30 (the opening fifteen minutes are noise) or after 15:00. Every open
    trade is closed at 15:20 if neither level was touched - these are intraday setups and
    none is held overnight. One open trade per index at a time, two entries per index per day
    at most. A holiday is read from the data, not from a calendar this file would have to keep
    true: a weekday whose bars never arrive is a day the exchange did not open.

WHEN A BAR TOUCHES BOTH LEVELS, THE STOP WINS. A five-minute bar does not say which came
first, and the assumption that flatters the record is the one this file must not make.

THE KILL SWITCH: a file named quant-paper.off in this folder. While it exists no new trade
opens; it is read on every tick, so no restart is needed. Trades already open are still
followed to their exit, because abandoning one would leave a hole in the record.

THE RECORD SPEAKS ONLY OF WHAT HAPPENED. track_record() reports counts, and a win rate only
once MIN_TRADES_TO_JUDGE trades have closed. It never states an accuracy the ledger has not
measured.

    python quant_paper.py --dryrun       replays the last 60 days of 5-minute bars through
                                         the same functions, into paper-dryrun.json - a
                                         verification run, never the track record.
"""

import datetime
import json
import os
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
LEDGER_PATH = os.path.join(HERE, "paper-ledger.json")
DRYRUN_PATH = os.path.join(HERE, "paper-dryrun.json")
HALT_PATH = os.path.join(HERE, "quant-paper.off")

IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
# (symbol, Yahoo ticker, the name a news search uses)
UNIVERSE = (("NIFTY", "^NSEI", "Nifty 50"), ("BANKNIFTY", "^NSEBANK", "Bank Nifty"))

BAR = datetime.timedelta(minutes=5)
SESSION_OPEN, SESSION_CLOSE = (9, 15), (15, 30)
FIRST_ENTRY, LAST_ENTRY, TIME_EXIT = (9, 30), (15, 0), (15, 20)
EMA_FAST, EMA_SLOW, RSI_N, ATR_N = 20, 50, 14, 14
RSI_LONG_TRIGGER, RSI_SHORT_TRIGGER = 40.0, 60.0
DAILY_STRETCHED_HIGH, DAILY_STRETCHED_LOW = 70.0, 30.0
STOP_ATR, TARGET_ATR = 1.5, 2.25
# A time exit within a tenth of an ATR of the entry is called breakeven, not a win or a loss.
BREAKEVEN_ATR = 0.1
MAX_ENTRIES_PER_DAY = 2
MIN_TRADES_TO_JUDGE = 30
# Every five minutes, twenty seconds after a bar completes. The mandate's floor is a minute.
TICK_S, TICK_OFFSET_S = 300, 20

NOTICE = "Simulated paper-trade: not a real position, not advice."

_ledger_lock = threading.Lock()


def log(line):
    sys.stderr.write("  paper: %s\n" % line)


# ------------------------------------------------------------------------------ the math

def ema(values, n):
    """EMA(n), seeded with the mean of the first n values; None until then.
        ema_t = ema_(t-1) + (value_t - ema_(t-1)) * 2 / (n + 1)"""
    out = [None] * len(values)
    if len(values) < n:
        return out
    cur = sum(values[:n]) / n
    out[n - 1] = cur
    k = 2.0 / (n + 1)
    for i in range(n, len(values)):
        cur += (values[i] - cur) * k
        out[i] = cur
    return out


def _wilder(series, n):
    """Wilder's smoothing of `series` (index 0 is a placeholder): seed = mean of 1..n, then
    avg_t = (avg_(t-1) * (n - 1) + x_t) / n. None until the seed."""
    out = [None] * len(series)
    if len(series) < n + 1:
        return out
    cur = sum(series[1:n + 1]) / n
    out[n] = cur
    for i in range(n + 1, len(series)):
        cur = (cur * (n - 1) + series[i]) / n
        out[i] = cur
    return out


def rsi_series(closes, n=RSI_N):
    """Wilder's RSI(n) at every close, None for the first n. The formula is server.wilder_rsi()'s,
    written out there; test_quant_paper.py checks the two agree to the last digit."""
    gains = [0.0] + [max(b - a, 0.0) for a, b in zip(closes, closes[1:])]
    losses = [0.0] + [max(a - b, 0.0) for a, b in zip(closes, closes[1:])]
    ag, al = _wilder(gains, n), _wilder(losses, n)
    out = []
    for g, l in zip(ag, al):
        if g is None:
            out.append(None)
        elif l == 0:
            out.append(100.0 if g > 0 else 50.0)
        else:
            out.append(100.0 - 100.0 / (1.0 + g / l))
    return out


def atr_series(highs, lows, closes, n=ATR_N):
    """Wilder's ATR(n). true range_t = max(high - low, |high - close_(t-1)|, |low - close_(t-1)|)."""
    tr = [0.0] + [max(h - l, abs(h - pc), abs(l - pc))
                  for h, l, pc in zip(highs[1:], lows[1:], closes)]
    return _wilder(tr, n)


# ------------------------------------------------------------------------------ the data

def _hm(dt):
    return (dt.hour, dt.minute)


def fetch_bars(ticker, period="5d", now=None):
    """(completed 5-minute bars oldest first, the latest price, error). A bar is
    {"t": its start, IST-aware, "o", "h", "l", "c"}. The latest price is the last row
    Yahoo returned, the forming bar included - the market's price at this moment."""
    try:
        import yfinance
    except ImportError:
        return [], None, "yfinance is not installed"
    try:
        hist = yfinance.Ticker(ticker).history(period=period, interval="5m",
                                               auto_adjust=False, timeout=10)
    except Exception as exc:                                   # noqa: BLE001
        return [], None, "yfinance could not fetch %s: %s" % (ticker, exc)
    now = (now or datetime.datetime.now(IST)).astimezone(IST)
    bars, latest = [], None
    for ts, row in hist.iterrows():
        vals = [row.get(k) for k in ("Open", "High", "Low", "Close")]
        if any(v is None or v != v for v in vals):            # v != v is NaN
            continue
        t = ts.to_pydatetime().astimezone(IST)
        latest = float(vals[3])
        if t + BAR <= now:
            bars.append({"t": t, "o": float(vals[0]), "h": float(vals[1]),
                         "l": float(vals[2]), "c": float(vals[3])})
    return bars, latest, ""


def fetch_daily(ticker, now=None):
    """[(date, close)] of COMPLETED sessions: today's bar is dropped until 16:00 IST."""
    try:
        import yfinance
        hist = yfinance.Ticker(ticker).history(period="1y", interval="1d",
                                               auto_adjust=False, timeout=10)
    except Exception:                                          # noqa: BLE001
        return []
    now = (now or datetime.datetime.now(IST)).astimezone(IST)
    out = [(ts.date(), float(c)) for ts, c in hist["Close"].dropna().items()]
    if out and out[-1][0] >= now.date() and _hm(now) < (16, 0):
        out = out[:-1]
    return out


def daily_rsi_before(daily, day):
    """Daily RSI(14) on the closes strictly before `day` - what was known that morning."""
    closes = [c for d, c in daily if d < day]
    rs = rsi_series(closes)
    return rs[-1] if rs and rs[-1] is not None else None


# ------------------------------------------------------------------------------ the setup

def indicators(bars):
    closes = [b["c"] for b in bars]
    return {"emaFast": ema(closes, EMA_FAST), "emaSlow": ema(closes, EMA_SLOW),
            "rsi": rsi_series(closes),
            "atr": atr_series([b["h"] for b in bars], [b["l"] for b in bars], closes)}


def signal_at(bars, ind, i, daily_rsi):
    """A setup on bar i, judged at its close, or None. Pure: same answer live and in a replay."""
    if i < 1:
        return None
    fast, slow, rsi, atr = (ind["emaFast"][i], ind["emaSlow"][i], ind["rsi"][i], ind["atr"][i])
    prev = ind["rsi"][i - 1]
    if None in (fast, slow, rsi, atr, prev) or atr <= 0:
        return None
    end = bars[i]["t"] + BAR
    if not (FIRST_ENTRY <= _hm(end) <= LAST_ENTRY):
        return None
    close = bars[i]["c"]
    direction = None
    if fast > slow and close > slow and prev < RSI_LONG_TRIGGER <= rsi:
        if daily_rsi is not None and daily_rsi > DAILY_STRETCHED_HIGH:
            return None
        direction = "long"
        why = ["trend up: 20-EMA %.1f above 50-EMA %.1f, close above the 50-EMA" % (fast, slow),
               "pullback over: 5m RSI(14) turned up through %d (%.1f -> %.1f)"
               % (RSI_LONG_TRIGGER, prev, rsi)]
    elif fast < slow and close < slow and prev > RSI_SHORT_TRIGGER >= rsi:
        if daily_rsi is not None and daily_rsi < DAILY_STRETCHED_LOW:
            return None
        direction = "short"
        why = ["trend down: 20-EMA %.1f below 50-EMA %.1f, close below the 50-EMA" % (fast, slow),
               "bounce over: 5m RSI(14) turned down through %d (%.1f -> %.1f)"
               % (RSI_SHORT_TRIGGER, prev, rsi)]
    if direction is None:
        return None
    why.append("ATR(14) %.1f points sets the stop at %.2gx and the target at %.3gx"
               % (atr, STOP_ATR, TARGET_ATR))
    if daily_rsi is not None:
        why.append("daily RSI(14) %.1f, not stretched against the trade" % daily_rsi)
    return {"direction": direction, "reasons": why, "atr": atr,
            "snapshot": {"emaFast": round(fast, 2), "emaSlow": round(slow, 2),
                         "rsiPrev": round(prev, 2), "rsi": round(rsi, 2), "atr": round(atr, 2),
                         "dailyRsi": round(daily_rsi, 2) if daily_rsi is not None else None}}


def open_trade(symbol, ticker, bar, entry, sig, mode, opened_at, news=()):
    sign = 1 if sig["direction"] == "long" else -1
    atr = sig["atr"]
    return {"id": "pt-%s-%s" % (symbol, bar["t"].strftime("%Y%m%d-%H%M")), "mode": mode,
            "symbol": symbol, "ticker": ticker, "direction": sig["direction"],
            "entry": round(entry, 2), "target": round(entry + sign * TARGET_ATR * atr, 2),
            "stop": round(entry - sign * STOP_ATR * atr, 2), "atr": round(atr, 2),
            "signalBar": bar["t"].isoformat(), "openedAt": opened_at.isoformat(),
            "reasons": list(sig["reasons"]), "indicators": dict(sig["snapshot"]),
            "news": list(news), "status": "open", "exit": None, "closedAt": None,
            "exitReason": None, "outcome": None, "pnlPts": None}


def advance(trade, bars):
    """Follow an open trade through the completed bars after its signal bar. Returns the
    trade, closed if a level was touched or the clock ran out. Pure: bars are history."""
    if trade["status"] != "open":
        return trade
    start = datetime.datetime.fromisoformat(trade["signalBar"])
    day = start.date()
    long_ = trade["direction"] == "long"
    for b in bars:
        if b["t"] <= start:
            continue
        end = b["t"] + BAR
        hit_stop = b["l"] <= trade["stop"] if long_ else b["h"] >= trade["stop"]
        hit_target = b["h"] >= trade["target"] if long_ else b["l"] <= trade["target"]
        if hit_stop:                       # both touched in one bar: the stop wins
            return _close(trade, trade["stop"], end, "stop")
        if hit_target:
            return _close(trade, trade["target"], end, "target")
        if b["t"].date() > day or _hm(end) >= TIME_EXIT:
            return _close(trade, b["c"], end, "time")
    return trade


def _close(trade, price, at, reason):
    t = dict(trade)
    pnl = (price - t["entry"]) if t["direction"] == "long" else (t["entry"] - price)
    if reason == "target":
        outcome = "win"
    elif reason == "stop":
        outcome = "loss"
    else:
        band = BREAKEVEN_ATR * float(t["atr"])
        outcome = "win" if pnl > band else "loss" if pnl < -band else "breakeven"
    t.update(status="closed", exit=round(price, 2), closedAt=at.isoformat(),
             exitReason=reason, outcome=outcome, pnlPts=round(pnl, 2))
    return t


def describe_open(t, tag=""):
    return ("%sOPEN %s %s %s @ %.2f, target %.2f, stop %.2f - %s"
            % (tag, t["id"], t["symbol"], t["direction"], t["entry"], t["target"], t["stop"],
               "; ".join(t["reasons"][:2])))


def describe_close(t, tag=""):
    return ("%sCLOSE %s %s %s @ %.2f (%s) - %s, %+.2f points"
            % (tag, t["id"], t["symbol"], t["direction"], t["exit"], t["exitReason"],
               t["outcome"], t["pnlPts"]))


# ------------------------------------------------------------------------------ the ledger

def read_trades(path=None):
    with _ledger_lock:
        try:
            with open(path or LEDGER_PATH, "r", encoding="utf-8") as fh:
                book = json.load(fh)
            rows = book.get("trades") if isinstance(book, dict) else None
            return [r for r in rows if isinstance(r, dict)] if isinstance(rows, list) else []
        except (OSError, ValueError):
            return []


def write_trades(trades, path=None, note=""):
    path = path or LEDGER_PATH
    book = {"trades": list(trades), "updated": datetime.datetime.now(IST).isoformat(),
            "note": note or "Simulated paper-trades. Not real positions, not advice."}
    with _ledger_lock:
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(book, fh, indent=1)
            fh.write("\n")
        os.replace(tmp, path)


def halted():
    return os.path.exists(HALT_PATH)


def track_record(trades=None):
    """What the ledger has measured, and nothing it has not. Live trades only."""
    trades = read_trades() if trades is None else trades
    live = [t for t in trades if t.get("mode") == "live"]
    closed = [t for t in live if t.get("status") == "closed"]
    wins = [t for t in closed if t.get("outcome") == "win"]
    losses = [t for t in closed if t.get("outcome") == "loss"]
    even = [t for t in closed if t.get("outcome") == "breakeven"]
    n = len(closed)
    out = {"closed": n, "open": len(live) - n, "wins": len(wins), "losses": len(losses),
           "breakeven": len(even), "enough": n >= MIN_TRADES_TO_JUDGE,
           "minToJudge": MIN_TRADES_TO_JUDGE, "winRate": None, "avgWinPts": None,
           "avgLossPts": None}
    if n == 0:
        out["sentence"] = ("No paper-trade has closed yet, so there is no track record to "
                           "report - not enough data to judge accuracy.")
        return out
    if n < MIN_TRADES_TO_JUDGE:
        out["sentence"] = ("Only %d paper-trade%s closed so far (%d won, %d lost, %d "
                           "breakeven) - not enough to judge accuracy yet. A win rate is "
                           "reported once %d have closed."
                           % (n, "" if n == 1 else "s", len(wins), len(losses), len(even),
                              MIN_TRADES_TO_JUDGE))
        return out
    out["winRate"] = round(100.0 * len(wins) / n, 1)
    out["avgWinPts"] = round(sum(t["pnlPts"] for t in wins) / len(wins), 2) if wins else None
    out["avgLossPts"] = (round(sum(t["pnlPts"] for t in losses) / len(losses), 2)
                         if losses else None)
    out["sentence"] = ("%d paper-trades closed: %d won, %d lost, %d breakeven - a measured "
                       "win rate of %.1f%% so far. Average win %s points, average loss %s "
                       "points. Measured on simulated trades, not a forecast."
                       % (n, len(wins), len(losses), len(even), out["winRate"],
                          "%+.2f" % out["avgWinPts"] if wins else "n/a",
                          "%+.2f" % out["avgLossPts"] if losses else "n/a"))
    return out


# ------------------------------------------------------------------------------ the desk

class PaperDesk:
    """The loop, on its own daemon thread. It holds no lock of the server's: the ledger lock
    above is this module's own and is never held across a network call."""

    def __init__(self):
        self._thread = None
        self._stop = threading.Event()
        self._search_url = ""
        self._seen = {}            # symbol -> start of the last bar judged for an entry
        self._news = {}            # (symbol, date) -> headlines, at most one search a day
        self._said = set()         # one-a-day log lines already written
        self.last = {"at": "", "what": ""}

    def start(self, search_url=""):
        if self._thread is not None:
            return False
        self._search_url = str(search_url or "")
        self._thread = threading.Thread(target=self._loop, name="paper-desk", daemon=True)
        self._thread.start()
        return True

    def stop(self):
        self._stop.set()

    def _loop(self):
        while not self._stop.is_set():
            now = time.time()
            wait = TICK_S - ((now - TICK_OFFSET_S) % TICK_S)
            if self._stop.wait(max(wait, 60)):
                return
            try:
                self.tick()
            except Exception as exc:                           # noqa: BLE001
                log("the tick threw (%s: %s); the desk carries on" % (type(exc).__name__, exc))

    def _once(self, key, line):
        if key not in self._said:
            self._said.add(key)
            log(line)

    def headlines(self, symbol, name, day):
        """Up to three public headlines, once per index per day, for the audit trail."""
        key = (symbol, day)
        if key not in self._news:
            try:
                import search
                cfg = {"search_url": self._search_url} if self._search_url else None
                rows = search.search("%s stock market news today" % name, want=3, cfg=cfg)
                self._news[key] = [{"title": str(r.get("title") or "")[:160],
                                    "host": str(r.get("host") or "")} for r in rows[:3]]
            except Exception as exc:                           # noqa: BLE001
                log("news for %s could not be read (%s)" % (symbol, exc))
                self._news[key] = []
        return self._news[key]

    def tick(self, now=None):
        now = (now or datetime.datetime.now(IST)).astimezone(IST)
        trades = read_trades()
        open_ = [t for t in trades if t.get("mode") == "live" and t.get("status") == "open"]
        weekday = now.weekday() < 5
        in_session = weekday and SESSION_OPEN <= _hm(now) <= (SESSION_CLOSE[0], SESSION_CLOSE[1] + 10)
        if not in_session and not open_:
            return {"skipped": "market closed"}
        changed = False
        for symbol, ticker, name in UNIVERSE:
            mine = [t for t in open_ if t["symbol"] == symbol]
            if not in_session and not mine:
                continue
            bars, latest, err = fetch_bars(ticker, now=now)
            if err or not bars:
                log("%s: no bars (%s)" % (symbol, err or "empty"))
                continue
            for t in mine:
                after = advance(t, bars)
                if after["status"] == "closed":
                    trades = [after if r["id"] == t["id"] else r for r in trades]
                    log(describe_close(after))
                    changed = True
            if not in_session:
                continue
            if bars[-1]["t"].date() != now.date():
                if _hm(now) >= (9, 30):
                    self._once(("closed", now.date(), symbol),
                               "%s: no bars today - the exchange is not trading (holiday?)"
                               % symbol)
                continue
            if halted():
                self._once(("halt", now.date(), now.hour), "kill switch on (%s): no new "
                           "paper-trades" % os.path.basename(HALT_PATH))
                continue
            i = len(bars) - 1
            if self._seen.get(symbol) == bars[i]["t"]:
                continue
            self._seen[symbol] = bars[i]["t"]
            if any(r["symbol"] == symbol and r.get("mode") == "live" and r["status"] == "open"
                   for r in trades):
                continue
            today = sum(1 for r in trades if r["symbol"] == symbol and r.get("mode") == "live"
                        and r["signalBar"][:10] == now.date().isoformat())
            if today >= MAX_ENTRIES_PER_DAY:
                continue
            sig = signal_at(bars, indicators(bars), i,
                            daily_rsi_before(fetch_daily(ticker, now=now), now.date()))
            if sig is None:
                continue
            # The entry is the price NOW (the forming bar's last print), and the trade is
            # followed from the next completed bar on - the few seconds of the forming bar
            # before this moment are neither credited nor charged.
            trade = open_trade(symbol, ticker, bars[i], latest if latest else bars[i]["c"],
                               sig, "live", now, self.headlines(symbol, name, now.date()))
            trade["dataLagS"] = int((now - (bars[i]["t"] + BAR)).total_seconds())
            trades.append(trade)
            log(describe_open(trade))
            changed = True
        if changed:
            write_trades(trades)
        self.last = {"at": now.isoformat(), "what": "ticked"}
        return {"ticked": now.isoformat(), "changed": changed}


MANAGER = PaperDesk()


# ------------------------------------------------------------------------------ the dry run

def replay(symbol, ticker, bars, daily, mode="dryrun"):
    """Walk `bars` as if each one had just closed, through the live functions. Returns trades.
    The entry is the signal bar's close - in a replay that IS the price at that moment."""
    ind = indicators(bars)
    trades, open_t, per_day = [], None, {}
    for i in range(len(bars)):
        if open_t is not None:
            # Only the bar that just closed: every earlier one was judged on its own step.
            open_t = advance(open_t, [bars[i]])
            if open_t["status"] == "closed":
                log(describe_close(open_t, "[dry run] "))
                trades.append(open_t)
                open_t = None
        if open_t is not None:
            continue
        day = bars[i]["t"].date()
        if per_day.get(day, 0) >= MAX_ENTRIES_PER_DAY:
            continue
        sig = signal_at(bars, ind, i, daily_rsi_before(daily, day))
        if sig is None:
            continue
        open_t = open_trade(symbol, ticker, bars[i], bars[i]["c"], sig, mode,
                            bars[i]["t"] + BAR)
        per_day[day] = per_day.get(day, 0) + 1
        log(describe_open(open_t, "[dry run] "))
    if open_t is not None:
        trades.append(open_t)
    return trades


def dryrun(period="60d"):
    """Replay recent history into DRYRUN_PATH. A verification run - never the track record."""
    now = datetime.datetime.now(IST)
    out = []
    for symbol, ticker, _name in UNIVERSE:
        bars, _latest, err = fetch_bars(ticker, period=period, now=now)
        if err:
            log("[dry run] %s: %s" % (symbol, err))
            continue
        out += replay(symbol, ticker, bars, fetch_daily(ticker, now=now))
    write_trades(out, DRYRUN_PATH, "DRY RUN - a replay of historical bars for verification "
                                   "only. Not the track record, not real positions, not advice.")
    closed = [t for t in out if t["status"] == "closed"]
    return {"trades": len(out), "closed": len(closed),
            "wins": sum(t["outcome"] == "win" for t in closed),
            "losses": sum(t["outcome"] == "loss" for t in closed),
            "breakeven": sum(t["outcome"] == "breakeven" for t in closed),
            "byExit": {r: sum(t["exitReason"] == r for t in closed)
                       for r in ("target", "stop", "time")},
            "pnlPts": round(sum(t["pnlPts"] for t in closed), 2), "path": DRYRUN_PATH}


if __name__ == "__main__":                                     # pragma: no cover
    if "--dryrun" in sys.argv:
        print(json.dumps(dryrun(), indent=1))
    else:
        print(__doc__)
