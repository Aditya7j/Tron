"""THE LEDGER. Two books in one file, and nothing in either is a number this house made up.
Every rupee here is a rupee somebody recorded, with a reason, and most should carry a proof.

WHY TWO BOOKS AND NOT ONE
    "galaxy"  GALAXY'S OWN BOOK - what running this house costs: the model bills, hosting, the
              domain, a paid tool. Nothing in the codebase logs this (no token counter, no
              billing API), so unlike confidence.py this file reads no other ledger. It IS one.
    "boss"    THE BOSS'S BOOK - his business income and expenses: YouTube, the newsletter,
              consulting, whatever he runs through Galaxy.
    One file, one `book` field, because the arithmetic - add, sum, balance, the proof check -
    is identical and is written once.

AN ENTRY
    id          "L-0001", in the order written, never reused
    book        "galaxy" or "boss"
    at          when it was RECORDED, to the second
    on          the day the money moved (YYYY-MM-DD) - what a period is filtered by. Today
                unless the entry names a date.
    kind        "income" or "expense"
    amount      a positive INTEGER in the currency's minor unit - paise for INR, cents for USD
    currency    "INR" (the default) or "USD". Nothing else: a currency whose minor unit this file
                does not know is a currency it cannot add up honestly. Totals are kept PER
                CURRENCY and never converted, because a conversion is an exchange rate this file
                would have to invent.
    category    one short word ("groq", "hosting", "youtube"), or "general"
    note        what was said, kept as it was said
    proof       a path under proofs/, or null
    enteredBy   "chat" (a card the boss said yes to) or "cli" (typed at a terminal)
    void        false, or true with voidReason and voidedAt

AMOUNTS ARE INTEGER PAISE, NEVER FLOAT - the oldest rule in any ledger, so 1900 paise and 1900
paise are 3800 paise and never 37.99999999999999 rupees. This file has no float in it at all,
and test_ledger.py reads its syntax tree to hold that: no float literal, no float(), and no "/"
operator, because in Python one integer divided by another IS a float. Money is split with
divmod. ledger.json is read with a parse_float that refuses, so a hand-edited 500.5 is an
unreadable row, named in every summary, and never a number in a total.

NOTHING IS EVER DELETED. A wrong entry is VOIDED: void=true, a reason, a time - and it stays in
the file, where every summary still counts it as voided. The ledger is a record of what was
SAID, the correction included, the same principle as jobs.py's correction rows.

PROOF, AND WHAT IT MEANS HERE. A path to a file already on disk under proofs/ - a screenshot, a
PDF, an exported statement row. This file never opens, OCRs or judges it; it records that a
path was given and checks the file exists at the moment of writing. An entry without one is
NOT refused - most small expenses have no receipt - but it is UNVERIFIED, and every summary of
a period says how much of its total is unverified. "No proof" is shown, never averaged away.

THE GATE. A chat question can reach a write here, and that is the one write a chat question can
reach beyond what hands.py already gates - so it goes through hands.py and nowhere else. The
server parses the sentence (parse_request), hands.propose() puts the card up in the registry's
words, and only a yes runs tools/add_ledger_entry.py or tools/void_ledger_entry.py, which call
add_entry() and void_entry(). The server itself never calls either; test_ledger.py reads
server.py's syntax tree to hold that. Both tools are registered with doors ["ledger"], so the
model is never told they exist and a [[tool: ...]] tag naming one is refused.

WHAT IT DOES NOT DO
    No projection, no burn rate, no forecast: a balance is money recorded, not a trend.
    No payment integration, no bank or UPI reading, no OCR: every number is typed or said.
    No entry from anything it can see but was not told - job counts, API usage, tokens. That
    is the invented number quant_paper.py and confidence.py both refuse to make.

    python ledger.py                              both books, all time, and what is unverified
    python ledger.py summary galaxy 2026-10       one book, one month
    python ledger.py add galaxy expense "500" groq "October bill" [--proof proofs/x.pdf]
                         [--on 2026-10-01] [--currency USD]
    python ledger.py void L-0003 "entered twice"
"""

import datetime
import json
import os
import re
import sys
import threading

HERE = os.path.dirname(os.path.abspath(__file__))
# The two overrides are a test seam: test_ledger.py points a tool script, which runs in its own
# process, at a temporary book. Nothing in the house sets them.
LEDGER_PATH = os.environ.get("TRONE_LEDGER_PATH") or os.path.join(HERE, "ledger.json")
PROOFS_DIR = os.environ.get("TRONE_PROOFS_DIR") or os.path.join(HERE, "proofs")

BOOKS = ("galaxy", "boss")
BOOK_NAMES = {"galaxy": "Galaxy's own book", "boss": "your business book"}
KINDS = ("income", "expense")
CURRENCIES = {"INR": "₹", "USD": "$"}           # both have 100 minor units to the major
DEFAULT_CURRENCY = "INR"
CATEGORY_MAX, NOTE_MAX, REASON_MAX = 40, 300, 200
MAX_AMOUNT = 10 ** 10                                 # 10 crore rupees, in paise: a typo guard

_lock = threading.Lock()


# ------------------------------------------------------------------------------ money

def _group(digits, indian):
    """1234567 -> 12,34,567 (Indian) or 1,234,567."""
    if len(digits) <= 3:
        return digits
    head, tail = digits[:-3], digits[-3:]
    size = 2 if indian else 3
    parts = []
    while head:
        parts.insert(0, head[-size:])
        head = head[:-size]
    return ",".join(parts + [tail])


def money(amount, currency=DEFAULT_CURRENCY):
    """Integer minor units as a person writes them: 125050 INR -> ₹1,250.50. Exact - divmod,
    never a division."""
    whole, minor = divmod(abs(int(amount)), 100)
    return "%s%s%s.%02d" % ("-" if amount < 0 else "", CURRENCIES.get(currency, currency + " "),
                            _group(str(whole), currency == "INR"), minor)


_MULT = {"k": 1000, "thousand": 1000, "hazaar": 1000, "hazar": 1000, "hajar": 1000,
         "lakh": 100000, "lakhs": 100000, "lac": 100000, "crore": 10 ** 7, "crores": 10 ** 7,
         "cr": 10 ** 7}
_USD = ("$", "usd", "dollar", "dollars", "bucks")
_MONTHS = {"january": 1, "jan": 1, "february": 2, "feb": 2, "march": 3, "april": 4, "apr": 4,
           "may": 5, "june": 6, "jun": 6, "july": 7, "jul": 7, "august": 8, "aug": 8,
           "september": 9, "sept": 9, "sep": 9, "october": 10, "oct": 10, "november": 11,
           "nov": 11, "december": 12, "dec": 12}
_MONTH_RE = "|".join(sorted(_MONTHS, key=len, reverse=True))
# Numbers that are not money, taken out before the amount is looked for: an ISO date, an entry
# id, a day and month ("3 October"), a month and year ("October 2026"), a proof path.
_NOT_MONEY = re.compile(r"\b\d{4}-\d{2}(?:-\d{2})?\b|\bL-\d+\b|\b\d{1,2}\s+(?:%s)\b|"
                        r"\b(?:%s)\s+\d{4}\b|\bproofs[\\/]\S+" % (_MONTH_RE, _MONTH_RE), re.I)
# The figure may not start inside a word ("qwen3"), may end a sentence ("...500."), and is
# never an ordinal ("on the 5th").
_AMOUNT = re.compile(r"""(?P<pre>₹|\brs\.?|\binr\b|\$|\busd\b)?\s*
    (?<![A-Za-z0-9_.,])(?P<num>\d{1,3}(?:,\d{2,3})+|\d+)(?:\.(?P<frac>\d{1,2}))?(?!\d)(?!\.\d)(?!(?:st|nd|rd|th)\b)
    (?:\s*(?P<mult>k|thousand|hazaar|hazar|hajar|lakhs?|lac|crores?|cr)\b)?
    (?:\s*(?P<post>rupees?|rupaye|rupaiye|rupay|rupiya|rs\b\.?|inr\b|dollars?|usd\b|bucks))?""",
                     re.I | re.X)


def parse_amount(text):
    """(minor units, currency, error) from a sentence - "Groq ka bill 500 rupaye" is (50000,
    "INR", ""). A figure marked as money (₹, rs, rupaye, $, dollars) wins; an unmarked one is
    taken only if it is the only number there. Two candidates is a question, never a guess."""
    clean = _NOT_MONEY.sub(" ", str(text or ""))
    found = []
    for m in _AMOUNT.finditer(clean):
        whole = int(m.group("num").replace(",", ""))
        minor = int((m.group("frac") or "").ljust(2, "0"))
        mult = _MULT.get((m.group("mult") or "").lower(), 1)
        mark = (m.group("pre") or m.group("post") or "").lower().rstrip(".")
        currency = "USD" if mark in _USD or mark.startswith("dollar") else DEFAULT_CURRENCY
        found.append(((whole * 100 + minor) * mult, currency, bool(mark or m.group("mult"))))
    marked = sorted({(a, c) for a, c, k in found if k})
    plain = sorted({(a, c) for a, c, k in found if not k})
    pick = marked if marked else plain
    if not pick:
        return None, None, "I did not hear an amount in that, sir."
    if len(pick) > 1:
        return None, None, ("I heard more than one figure in that, sir (%s), and I will not "
                            "guess which is the amount."
                            % ", ".join(money(a, c) for a, c in pick))
    amount, currency = pick[0]
    if amount <= 0:
        return None, None, "An amount of nothing is not an entry, sir."
    if amount > MAX_AMOUNT:
        return None, None, "That is more than %s, sir, which I take to be a slip." % money(
            MAX_AMOUNT)
    return amount, currency, ""


# ------------------------------------------------------------------------------ the file

def _no_float(text):
    """json.load's parse_float: a float in the file is not a number this ledger will hold."""
    return "FLOAT:" + text


def read_book(path=None):
    """(entries, unreadable) - the rows that are entries, and how many rows are not. A row
    is unreadable when it lacks a field or its amount is not a positive integer; it is never
    repaired, and every summary names how many there are."""
    try:
        with open(path or LEDGER_PATH, "r", encoding="utf-8") as fh:
            data = json.load(fh, parse_float=_no_float)
    except FileNotFoundError:
        return [], 0
    except (OSError, ValueError):
        return [], -1                          # the whole file is unreadable
    rows = data.get("entries") if isinstance(data, dict) else None
    rows = rows if isinstance(rows, list) else []
    good = [r for r in rows if _well_formed(r)]
    return good, len(rows) - len(good)


def _well_formed(r):
    return (isinstance(r, dict) and isinstance(r.get("id"), str) and r.get("book") in BOOKS
            and r.get("kind") in KINDS and r.get("currency") in CURRENCIES
            and type(r.get("amount")) is int and r["amount"] > 0
            and _date(r.get("on")) is not None)


def _write_book(entries, path=None):
    path = path or LEDGER_PATH
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump({"version": 1, "entries": entries,
                   "updated": datetime.datetime.now().isoformat(timespec="seconds"),
                   "note": "Two books, amounts in integer paise (cents for USD). Nothing is "
                           "deleted: a wrong entry is voided and stays."},
                  fh, indent=1, ensure_ascii=False)
        fh.write("\n")
    os.replace(tmp, path)


def _raw_rows(path=None):
    """Every row in the file, readable or not - a write must carry the unreadable ones too."""
    try:
        with open(path or LEDGER_PATH, "r", encoding="utf-8") as fh:
            data = json.load(fh, parse_float=_no_float)
    except FileNotFoundError:
        return []
    rows = data.get("entries") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        raise ValueError("the ledger file holds no list of entries")
    return rows


def _date(value):
    try:
        return datetime.date.fromisoformat(str(value or ""))
    except ValueError:
        return None


def check_proof(proof):
    """(relative path or None, error). Inside proofs/ and present on disk, or refused."""
    if proof in (None, "") or str(proof).strip().lower() in ("none", "null", "-"):
        return None, ""
    raw = str(proof).strip().strip("\"'")
    root = os.path.realpath(PROOFS_DIR)
    base = os.path.dirname(root)               # "proofs/x.pdf" is relative to proofs/'s parent
    full = os.path.realpath(raw if os.path.isabs(raw) else os.path.join(base, raw))
    try:
        inside = os.path.commonpath([full, root]) == root and full != root
    except ValueError:                                         # another drive altogether
        inside = False
    if not inside:
        return None, "A proof has to be a file inside proofs/, sir; %s is not." % raw
    if not os.path.isfile(full):
        return None, "There is no file at %s, sir, so I cannot record it as proof." % raw
    return os.path.relpath(full, base).replace(os.sep, "/"), ""


def check_entry(book, kind, amount, category, currency=DEFAULT_CURRENCY, on=None):
    """The error sentence for an entry that cannot be written, or "". Shared by the card (so
    a refusal comes before a card, not after a yes) and by add_entry (which trusts nobody)."""
    if book not in BOOKS:
        return "The book must be galaxy or boss, sir, not %r." % book
    if kind not in KINDS:
        return "An entry is income or expense, sir, not %r." % kind
    if type(amount) is not int:
        return "An amount is a whole number of paise, sir - never a %s." % type(amount).__name__
    if amount <= 0 or amount > MAX_AMOUNT:
        return "An amount must be above nothing and below %s, sir." % money(MAX_AMOUNT)
    if currency not in CURRENCIES:
        return "I keep INR and USD only, sir, not %r." % currency
    if not str(category or "").strip():
        return "An entry needs a category, sir."
    if on is not None and _date(on) is None:
        return "%r is not a date I can read, sir - YYYY-MM-DD." % on
    return ""


def describe(book, kind, amount, category, currency=DEFAULT_CURRENCY, on=None, proof=None):
    """The entry as one sentence - the card's spoken line, and the line the tool script
    re-composes and compares before it writes, so what was approved is what is written."""
    day = _date(on) or datetime.date.today()
    return ("An %s of %s for %s, in %s, dated %s, %s"
            % (kind, money(amount, currency), category,
               BOOK_NAMES.get(book, book), "%d %s %d" % (day.day, day.strftime("%B"),
                                                         day.year),
               "with proof at %s" % proof if proof
               else "with no proof attached, so it would be marked unverified"))


def add_entry(book, kind, amount, category, note="", currency=DEFAULT_CURRENCY, proof=None,
              on=None, entered_by="cli", now=None, path=None):
    """(entry, error). Called by tools/add_ledger_entry.py after a yes, or by the CLI - never
    by the server. Everything is checked again here; the caller is trusted with nothing."""
    error = check_entry(book, kind, amount, category, currency, on)
    if error:
        return None, error
    proof_path, error = check_proof(proof)
    if error:
        return None, error
    now = now or datetime.datetime.now()
    with _lock:
        try:
            rows = _raw_rows(path)
        except (OSError, ValueError) as exc:
            return None, "The ledger file could not be read (%s), sir, so nothing was " \
                         "written." % type(exc).__name__
        taken = [int(r["id"][2:]) for r in rows if isinstance(r, dict)
                 and re.fullmatch(r"L-\d+", str(r.get("id") or ""))]
        entry = {"id": "L-%04d" % (max(taken, default=0) + 1), "book": book,
                 "at": now.isoformat(timespec="seconds"),
                 "on": (_date(on) or now.date()).isoformat(), "kind": kind, "amount": amount,
                 "currency": currency, "category": str(category).strip().lower()[:CATEGORY_MAX],
                 "note": " ".join(str(note or "").split())[:NOTE_MAX], "proof": proof_path,
                 "enteredBy": str(entered_by or "cli")[:40], "void": False,
                 "voidReason": None, "voidedAt": None}
        _write_book(rows + [entry], path)
    return entry, ""


def void_entry(entry_id, reason, now=None, path=None):
    """(entry, error). The entry stays in the file, struck out - never removed."""
    reason = " ".join(str(reason or "").split())[:REASON_MAX]
    if not reason:
        return None, "A void needs a reason, sir, so the book says why."
    now = now or datetime.datetime.now()
    with _lock:
        try:
            rows = _raw_rows(path)
        except (OSError, ValueError) as exc:
            return None, "The ledger file could not be read (%s), sir, so nothing was " \
                         "changed." % type(exc).__name__
        hit = next((r for r in rows if isinstance(r, dict)
                    and str(r.get("id") or "").upper() == str(entry_id or "").upper()), None)
        if hit is None:
            return None, "There is no entry %s in the book, sir." % entry_id
        if hit.get("void"):
            return None, "%s is already void, sir (%s)." % (hit["id"], hit.get("voidReason"))
        hit.update(void=True, voidReason=reason, voidedAt=now.isoformat(timespec="seconds"))
        _write_book(rows, path)
    return dict(hit), ""


def find_entry(entry_id=None, last=False, path=None):
    """One entry by id, or the most recent one still standing."""
    entries, _bad = read_book(path)
    if last:
        live = [e for e in entries if not e.get("void")]
        return live[-1] if live else None
    return next((e for e in entries if e["id"].upper() == str(entry_id or "").upper()), None)


# ------------------------------------------------------------------------------ periods

def _month(year, month):
    start = datetime.date(year, month, 1)
    end = datetime.date(year + (month == 12), month % 12 + 1, 1)
    return start, end, "%s %d" % (start.strftime("%B"), year)


def parse_period(text, today=None):
    """{"start", "end" (exclusive), "label"} named in a sentence, or the whole of time."""
    today = today or datetime.date.today()
    t = str(text or "").lower()
    iso = re.search(r"\b(\d{4})-(\d{2})\b(?!-\d)", t)
    if iso and 1 <= int(iso.group(2)) <= 12:
        start, end, label = _month(int(iso.group(1)), int(iso.group(2)))
    elif re.search(r"\b(?:is|iss|this)\s+(?:mahine|mahina|month)\b", t):
        start, end, label = _month(today.year, today.month)
    elif re.search(r"\b(?:pichle|pichhle|pichla|last|previous)\s+(?:mahine|mahina|month)\b", t):
        prev = today.replace(day=1) - datetime.timedelta(days=1)
        start, end, label = _month(prev.year, prev.month)
    elif re.search(r"\b(?:is|iss|this)\s+(?:saal|sal|year)\b", t):
        start, end = datetime.date(today.year, 1, 1), datetime.date(today.year + 1, 1, 1)
        label = "%d" % today.year
    elif re.search(r"\b(?:pichle|pichhle|last|previous)\s+(?:saal|sal|year)\b", t):
        start, end = datetime.date(today.year - 1, 1, 1), datetime.date(today.year, 1, 1)
        label = "%d" % (today.year - 1)
    elif re.search(r"\b(?:aaj|today)\b", t):
        start, end = today, today + datetime.timedelta(days=1)
        label = "today, %d %s" % (today.day, today.strftime("%B"))
    else:
        named = re.search(r"\b(%s)\b(?:\s+(\d{4}))?" % _MONTH_RE, t)
        # "may" is a month only when a year or "mein" says so - "may I see" is not May.
        if named and (named.group(1) != "may" or named.group(2)
                      or re.search(r"\bmay\s+(?:mein|me|main)\b", t)):
            month = _MONTHS[named.group(1)]
            year = int(named.group(2)) if named.group(2) else (
                today.year if month <= today.month else today.year - 1)
            start, end, label = _month(year, month)
        else:
            return {"start": None, "end": None, "label": "all time"}
    return {"start": start, "end": end, "label": label}


def _in(entry, period):
    if not period or period.get("start") is None:
        return True
    day = _date(entry.get("on"))
    return day is not None and period["start"] <= day < period["end"]


# ------------------------------------------------------------------------------ the totals

def _totals(entries):
    """{currency: {income, expense, net, unverifiedIncome, unverifiedExpense, entries}}"""
    out = {}
    for e in entries:
        t = out.setdefault(e["currency"], {"income": 0, "expense": 0, "net": 0,
                                           "unverifiedIncome": 0, "unverifiedExpense": 0,
                                           "entries": 0})
        t[e["kind"]] += e["amount"]
        t["net"] += e["amount"] if e["kind"] == "income" else -e["amount"]
        t["entries"] += 1
        if not e.get("proof"):
            t["unverifiedIncome" if e["kind"] == "income" else "unverifiedExpense"] += \
                e["amount"]
    return out


def _plural(n, one, many):
    return "%d %s" % (n, one if n == 1 else many)


def summary(book, period=None, category=None, path=None):
    """What the book holds for a period: per currency, income, expense, net, and how much of
    each is unverified. Voided entries are counted and named, never summed."""
    if book not in BOOKS:
        raise ValueError("book must be one of %s" % ", ".join(BOOKS))
    period = period or {"start": None, "end": None, "label": "all time"}
    entries, bad = read_book(path)
    mine = [e for e in entries if e["book"] == book and _in(e, period)
            and (not category or e["category"] == category)]
    live = [e for e in mine if not e.get("void")]
    totals = _totals(live)
    voided = len(mine) - len(live)
    head = "%s, %s%s" % (BOOK_NAMES[book], period["label"],
                         " (%s only)" % category if category else "")
    if not live:
        sentence = "%s: no entries." % head
    else:
        parts = []
        for cur in sorted(totals):
            t = totals[cur]
            unverified_total = t["unverifiedIncome"] + t["unverifiedExpense"]
            parts.append("income %s, expenses %s, net %s across %s - %s"
                         % (money(t["income"], cur), money(t["expense"], cur),
                            money(t["net"], cur), _plural(t["entries"], "entry", "entries"),
                            "none of it unverified" if not unverified_total else
                            "%s of it unverified (no proof): %s of the income, %s of the "
                            "expenses" % (money(unverified_total, cur),
                                          money(t["unverifiedIncome"], cur),
                                          money(t["unverifiedExpense"], cur))))
        # Each currency on its own: rupees and dollars are never added together.
        sentence = "%s: %s." % (head, parts[0] if len(parts) == 1 else "; ".join(
            "in %s, %s" % (cur, part) for cur, part in zip(sorted(totals), parts)))
    if voided:
        sentence += " %s not counted." % _plural(voided, "voided entry", "voided entries")
    if bad:
        sentence += (" The ledger file could not be read at all." if bad < 0 else
                     " %s in the file could not be read and %s not counted."
                     % (_plural(bad, "row", "rows"), "is" if bad == 1 else "are"))
    return {"book": book, "period": period["label"], "category": category,
            "totals": totals, "entries": len(live), "voided": voided, "unreadable": bad,
            "sentence": sentence[:1].upper() + sentence[1:]}


def balance(book, path=None):
    """All time, recorded money only - not a bank balance and not a forecast."""
    out = summary(book, None, path=path)
    out["sentence"] = out["sentence"].replace(", all time:", ", everything recorded:", 1)
    return out


def unverified(book=None, period=None, path=None):
    """The standing entries with no proof, oldest first, and their totals per currency."""
    entries, _bad = read_book(path)
    rows = [e for e in entries if not e.get("void") and not e.get("proof")
            and (book is None or e["book"] == book) and _in(e, period)]
    totals = _totals(rows)
    label = (period or {}).get("label") or "all time"
    where = BOOK_NAMES[book] if book else "either book"
    standing = sum(1 for e in entries if not e.get("void")
                   and (book is None or e["book"] == book) and _in(e, period))
    if not standing:
        # Not "every one carries a proof": there is no "every one" to speak of.
        sentence = "There are no entries in %s, %s, so nothing is unverified." % (where, label)
    elif not rows:
        sentence = "No unverified entry in %s, %s - %s." % (
            where, label, "its one entry carries a proof" if standing == 1
            else "all %d carry a proof" % standing)
    else:
        sentence = ("%s in %s, %s, %s no proof: %s. %s: %s."
                    % (_plural(len(rows), "entry", "entries"), where, label,
                       "carries" if len(rows) == 1 else "carry",
                       "; ".join("%s of expenses and %s of income"
                                 % (money(totals[cur]["expense"], cur),
                                    money(totals[cur]["income"], cur))
                                 for cur in sorted(totals)),
                       "It is" if len(rows) == 1 else "They are",
                       "; ".join("%s %s %s %s for %s"
                                 % (e["id"], e["on"], e["kind"],
                                    money(e["amount"], e["currency"]), e["category"])
                                 for e in rows[:10])
                       + ("; and %d more" % (len(rows) - 10) if len(rows) > 10 else "")))
    return {"book": book, "period": label, "entries": [dict(e) for e in rows],
            "totals": totals, "sentence": sentence}


# ------------------------------------------------------------------------------ the chat

_GALAXY_WORDS = re.compile(r"\b(?:groq|gemini|openrouter|ollama|api|hosting|server|domain|vps|"
                           r"cloud|galaxy\s*(?:ka|ke|ki|'s)|galaxy\s+book)\b", re.I)
_BOSS_WORDS = re.compile(r"\b(?:business|boss|youtube|newsletter|consulting|client|sponsor\w*|"
                         r"freelance|course|mera\s+book|my\s+book)\b", re.I)
_INCOME_WORDS = re.compile(r"\b(?:income|revenue|kamai|kamaya|earning|earned|received|mila|"
                           r"mili|aaya|aayi|aya|ayi|sponsorship)\b", re.I)
_EXPENSE_WORDS = re.compile(r"\b(?:bill|kharcha|kharch|expense|spent|spend|paid|bhara|bhari|"
                            r"fee|fees|subscription|cost|kharida|kharidi)\b", re.I)
CATEGORIES = ("groq", "gemini", "openrouter", "ollama", "hosting", "domain", "server", "vps",
              "youtube", "newsletter", "consulting", "sponsorship", "client", "course")
_PROOF = re.compile(r"\b(?:proof|receipt|rasid|raseed)\s*[:=-]?\s*(proofs[\\/][^\s,;]+)", re.I)
_ON = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")
_ID = re.compile(r"\bL-(\d{1,6})\b", re.I)
_LAST = re.compile(r"\b(?:last|aakhri|akhri|pichli|latest|recent)\s+entry\b", re.I)
_REASON = re.compile(r"\b(?:because|kyunki|kyuki|kyonki|reason|wajah|since)\b\s*[:,-]?\s*(.+)$",
                     re.I)


def book_in(text):
    """"galaxy", "boss", "both" (two signals that disagree) or None."""
    g, b = bool(_GALAXY_WORDS.search(text)), bool(_BOSS_WORDS.search(text))
    return "both" if g and b else "galaxy" if g else "boss" if b else None


def kind_in(text):
    i, e = bool(_INCOME_WORDS.search(text)), bool(_EXPENSE_WORDS.search(text))
    return "both" if i and e else "income" if i else "expense" if e else None


def category_in(text):
    low = str(text or "").lower()
    return next((c for c in CATEGORIES if re.search(r"\b%s\b" % c, low)), None)


def parse_request(text, action, today=None):
    """What a sentence asks of the book. For "add" and "void" it is a hand's parameters or an
    error sentence - the card is the server's to put up, through hands.propose()."""
    text = str(text or "").strip()
    today = today or datetime.date.today()
    if action == "add":
        amount, currency, error = parse_amount(text)
        if error:
            return {"action": "add", "error": error}
        book, kind = book_in(text), kind_in(text)
        if book in (None, "both"):
            return {"action": "add", "error": "Which book is that for, sir - Galaxy's own "
                                              "running costs, or your business?"}
        if kind in (None, "both"):
            return {"action": "add", "error": "Is that money coming in or going out, sir?"}
        on = _ON.search(text)
        on = on.group(1) if on else today.isoformat()
        proof = _PROOF.search(text)
        proof_path, error = check_proof(proof.group(1) if proof else None)
        category = category_in(text) or "general"
        error = error or check_entry(book, kind, amount, category, currency, on)
        if error:
            return {"action": "add", "error": error}
        params = {"book": book, "kind": kind, "amount_paise": amount, "currency": currency,
                  "category": category, "on": on, "proof": proof_path or "none",
                  "note": text[:NOTE_MAX],
                  "entry": describe(book, kind, amount, category, currency, on, proof_path)}
        return {"action": "add", "error": "", "tool": "add_ledger_entry", "params": params}
    if action == "void":
        found = _ID.search(text)
        entry = (find_entry("L-%04d" % int(found.group(1))) if found
                 else find_entry(last=True) if _LAST.search(text) else None)
        if entry is None:
            return {"action": "void", "error": ("There is no entry %s in the book, sir."
                                                % found.group(0).upper() if found else
                                                "Which entry, sir? Name it - L-0003 - or say "
                                                "the last entry.")}
        if entry.get("void"):
            return {"action": "void", "error": "%s is already void, sir (%s)."
                                               % (entry["id"], entry.get("voidReason"))}
        said = _REASON.search(text)
        reason = (said.group(1) if said else _ID.sub("", text)).strip(" .,:;-")[:REASON_MAX]
        params = {"id": entry["id"], "reason": reason or text[:REASON_MAX],
                  "entry": entry_line(entry)}
        return {"action": "void", "error": "", "tool": "void_ledger_entry", "params": params}
    book = book_in(text)
    return {"action": action, "error": "", "book": book if book in BOOKS else None,
            "period": parse_period(text, today), "category": category_in(text)}


def entry_line(e):
    """One existing entry, for a void card: what is about to be struck out."""
    return ("%s, %s of %s for %s in %s, dated %s%s"
            % (e["id"], e["kind"], money(e["amount"], e["currency"]), e["category"],
               BOOK_NAMES[e["book"]], e["on"], ", with proof" if e.get("proof") else
               ", unverified"))


def answer(req, path=None):
    """(text, data) for a read - a summary, a balance or the unverified list. No gate: it is a
    read, like confidence.answer(). Both books when the sentence names neither."""
    books = [req["book"]] if req.get("book") else list(BOOKS)
    if req["action"] == "unverified":
        data = unverified(req.get("book"), req.get("period"), path=path)
        return data["sentence"], data
    if req["action"] == "balance":
        rows = [balance(b, path=path) for b in books]
    else:
        rows = [summary(b, req.get("period"), req.get("category"), path=path) for b in books]
    tail = ("Recorded money only - not a bank balance, and not a forecast."
            if req["action"] == "balance" else "Recorded money only, not a forecast.")
    return "\n\n".join([r["sentence"] for r in rows] + [tail]), {"books": rows}


# ------------------------------------------------------------------------------ by hand

def _main(argv):                                               # pragma: no cover
    import argparse
    ap = argparse.ArgumentParser(prog="ledger.py", description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd")
    s = sub.add_parser("summary")
    s.add_argument("book", choices=BOOKS)
    s.add_argument("period", nargs="?", default="")
    a = sub.add_parser("add")
    a.add_argument("book", choices=BOOKS)
    a.add_argument("kind", choices=KINDS)
    a.add_argument("amount", help='"500", "1,250.50", "1.5 lakh" - never a float')
    a.add_argument("category")
    a.add_argument("note", nargs="?", default="")
    a.add_argument("--proof")
    a.add_argument("--on")
    a.add_argument("--currency", default=DEFAULT_CURRENCY, choices=sorted(CURRENCIES))
    v = sub.add_parser("void")
    v.add_argument("id")
    v.add_argument("reason")
    args = ap.parse_args(argv)
    if args.cmd == "add":
        amount, _cur, error = parse_amount(args.amount + " rupees")
        entry, error = (None, error) if error else add_entry(
            args.book, args.kind, amount, args.category, args.note, args.currency,
            args.proof, args.on, entered_by="cli")
        print(error or "Written as %s: %s." % (entry["id"], entry_line(entry)))
        return 1 if error else 0
    if args.cmd == "void":
        entry, error = void_entry(args.id, args.reason)
        print(error or "%s is void: %s. It stays in the book." % (entry["id"],
                                                                 entry["voidReason"]))
        return 1 if error else 0
    if args.cmd == "summary":
        print(summary(args.book, parse_period(args.period) if args.period else None)["sentence"])
        return 0
    for b in BOOKS:
        print(summary(b)["sentence"])
    print(unverified()["sentence"])
    return 0


if __name__ == "__main__":                                     # pragma: no cover
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:                                          # noqa: BLE001
        pass
    sys.exit(_main(sys.argv[1:]))
