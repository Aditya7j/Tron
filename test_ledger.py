"""Proves the ledger: every rupee is one somebody recorded, to the paisa, and nothing is lost.

  1. MONEY. money() and parse_amount() on hand-checked inputs; ten entries of 10 paise are
     exactly one rupee, and 1900 + 1900 paise are exactly 3800 - never 37.99999999999999.
  2. AN ENTRY. add_entry() numbers entries in order, refuses a float, a bool, a string, zero, a
     negative, an unknown book, kind or currency, an empty category and an unreadable date; a
     proof must be a file that exists inside proofs/.
  3. NOTHING IS DELETED. void_entry() keeps the row and adds the reason and time; a second void,
     an unknown id and an empty reason are refused; the file never has fewer rows than before.
  4. THE TOTALS. summary() per book, per period and per currency (rupees and dollars are never
     added); voided entries are counted and named, never summed; every summary says how much is
     unverified, "none of it" included; a hand-edited float or broken row is named and never
     summed, and reading the file yields no float at all.
  5. THE SENTENCE. parse_request() turns "Groq ka bill 500 rupaye add karo" into a card's
     parameters, and refuses - in words - a missing book, a missing direction, two figures, no
     figure and a proof that is not there; a void finds its entry by id or as the last one.
  6. THE CHAT. The four questions and their cousins route to "ledger"; concepts, reminders,
     the paper desk, the meter and "remember that" do not.
  7. THE GATE. The first sentence writes NOTHING - it puts up a card on the ledger door. A yes
     writes exactly the card's figures, through the real /chat door; a no and a change of
     subject write nothing; a tag, a chain, another door and a body claiming the ledger door are
     all refused, and the brain is never told the hands exist. A card whose sentence and figures
     disagree writes nothing. A guest is told nothing and offered nothing.
 7b. THE BOUNDARY. A ₹ card is added and voided through the real spawner with PYTHONIOENCODING
     and PYTHONUTF8 taken out of the environment - the way the server runs the hands - because
     with them inherited, a hand that read stdin in the ANSI codepage passed every check above.
  8. THE SOURCE. No float anywhere in ledger.py or its two hands - no float literal, no float(),
     no "/" operator. server.py never calls add_entry() or void_entry(); only the hands do.
     ledger.py deletes nothing, imports nothing that reaches a network, and both hands are
     door-bound in the registry. ledger.json and proofs/ are gitignored.

Nothing touches the network beyond a loopback server of this file's own, the real ledger, the
real proofs folder or the real tools-ledger.json.

Run it:  python test_ledger.py
Exit status is the number of failures.
"""

import ast
import datetime
import io
import json
import os
import pathlib
import re
import shutil
import sys
import tempfile
import threading
import urllib.request
from functools import partial
from http.server import ThreadingHTTPServer

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:                                              # noqa: BLE001
    pass

TMP = tempfile.mkdtemp()
BOOK = os.path.join(TMP, "ledger.json")
PROOFS = os.path.join(TMP, "proofs")
os.makedirs(PROOFS)
# The hands run in their own process, so the temporary book reaches them through the
# environment - set before ledger is imported, so this process agrees with them.
os.environ["TRONE_LEDGER_PATH"] = BOOK
os.environ["TRONE_PROOFS_DIR"] = PROOFS

import ledger as lg                                            # noqa: E402
import hands                                                   # noqa: E402
import server                                                  # noqa: E402
from tools import _proc                                        # noqa: E402

REAL_BOOK = os.path.join(HERE, "ledger.json")
REAL_TOOLS = hands.LEDGER_PATH
before = {p: (open(p, "rb").read() if os.path.exists(p) else None)
          for p in (REAL_BOOK, str(REAL_TOOLS))}
hands.LEDGER_PATH = pathlib.Path(TMP) / "tools-ledger.json"
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


def fresh():
    for p in (BOOK, BOOK + ".tmp"):
        if os.path.exists(p):
            os.remove(p)
    hands.clear_pending("test")


def rows():
    return json.load(open(BOOK, encoding="utf-8"))["entries"] if os.path.exists(BOOK) else []


def proof(name):
    with open(os.path.join(PROOFS, name), "w") as fh:
        fh.write("a receipt")
    return "proofs/" + name


OCT = datetime.datetime(2026, 10, 9, 12, 0, 0)
TODAY = OCT.date()

ok(lg.LEDGER_PATH == BOOK and lg.PROOFS_DIR == PROOFS, "the book and proofs/ are temporary")

# ---------------------------------------------------------------------------------------
head("1. money, to the paisa")
ok(lg.money(12500000) == "₹1,25,000.00" and lg.money(123405, "USD") == "$1,234.05"
   and lg.money(5) == "₹0.05" and lg.money(-50000) == "-₹500.00",
   "money(): Indian grouping for rupees, Western for dollars, the sign in front")
for text, want in (("Groq ka bill 500 rupaye add karo", (50000, "INR")),
                   ("₹1,250.50 hosting", (125050, "INR")),
                   ("Rs. 99 domain", (9900, "INR")),
                   ("$5 groq", (500, "USD")), ("5 dollars to Groq", (500, "USD")),
                   ("1.5 lakh consulting", (15000000, "INR")), ("2k youtube", (200000, "INR")),
                   ("1,25,000 rupaye", (12500000, "INR")), ("the bill was 500.", (50000, "INR")),
                   ("qwen3 bill 40 rupees", (4000, "INR")),
                   ("on 2026-10-01 the Groq bill 500 add karo", (50000, "INR")),
                   ("October 2026 ka bill 300", (30000, "INR")),
                   ("due on the 5th, 500 rupaye", (50000, "INR"))):
    got = lg.parse_amount(text)
    ok(got[:2] == want and got[2] == "", "%r -> %s" % (text, lg.money(*want)), str(got))
for text, why in (("500 aur 300", "more than one figure"), ("no amount at all", "did not hear"),
                  ("pay it on the 5th", "did not hear"), ("0 rupaye", "nothing")):
    got = lg.parse_amount(text)
    ok(got[0] is None and why in got[2], "%r is refused: %s" % (text, got[2]))
fresh()
for _ in range(10):
    lg.add_entry("galaxy", "expense", 10, "test", now=OCT)
lg.add_entry("boss", "income", 1900, "test", now=OCT)
lg.add_entry("boss", "income", 1900, "test", now=OCT)
g, b = lg.summary("galaxy"), lg.summary("boss")
ok(g["totals"]["INR"]["expense"] == 100 and "₹1.00" in g["sentence"],
   "ten entries of 10 paise are exactly ₹1.00 (as floats, 0.1 x 10 is 0.9999999999999999)")
ok(b["totals"]["INR"]["income"] == 3800 and "₹38.00" in b["sentence"],
   "1900 + 1900 paise are exactly 3800 paise, ₹38.00")

# ---------------------------------------------------------------------------------------
head("2. an entry")
fresh()
e, err = lg.add_entry("galaxy", "expense", 50000, "groq", "October bill", now=OCT)
ok(not err and e["id"] == "L-0001" and e["amount"] == 50000 and e["on"] == "2026-10-09"
   and e["at"] == "2026-10-09T12:00:00" and e["proof"] is None and e["void"] is False
   and e["enteredBy"] == "cli" and e["currency"] == "INR",
   "the first entry is L-0001, in paise, today, unverified, standing", str(e))
e2, _ = lg.add_entry("boss", "income", 250000, "consulting", on="2026-09-30", now=OCT)
ok(e2["id"] == "L-0002" and e2["on"] == "2026-09-30", "the next is L-0002, on its own date")
for args, why in ((("galaxy", "expense", 500.5, "groq"), "never a float"),
                  (("galaxy", "expense", True, "groq"), "never a bool"),
                  (("galaxy", "expense", "500", "groq"), "never a str"),
                  (("galaxy", "expense", 0, "groq"), "above nothing"),
                  (("galaxy", "expense", -500, "groq"), "above nothing"),
                  (("house", "expense", 500, "groq"), "galaxy or boss"),
                  (("galaxy", "loan", 500, "groq"), "income or expense"),
                  (("galaxy", "expense", 500, "  "), "needs a category")):
    got, err = lg.add_entry(*args, now=OCT)
    ok(got is None and why in err, "refused: %r - %s" % (args[2] if why.startswith(("never", "above"))
                                                       else args, err))
got, err = lg.add_entry("galaxy", "expense", 500, "groq", currency="EUR", now=OCT)
ok(got is None and "INR and USD only" in err, "a currency it cannot add up honestly is refused")
got, err = lg.add_entry("galaxy", "expense", 500, "groq", on="9 Oct", now=OCT)
ok(got is None and "YYYY-MM-DD" in err, "an unreadable date is refused")
outside = os.path.join(TMP, "elsewhere.png")
open(outside, "w").close()
got, err = lg.add_entry("galaxy", "expense", 500, "groq", proof=outside, now=OCT)
ok(got is None and "inside proofs/" in err, "a proof outside proofs/ is refused")
got, err = lg.add_entry("galaxy", "expense", 500, "groq", proof="proofs/../elsewhere.png",
                        now=OCT)
ok(got is None and "inside proofs/" in err, "and so is one that climbs out of it")
got, err = lg.add_entry("galaxy", "expense", 500, "groq", proof="proofs/missing.pdf", now=OCT)
ok(got is None and "no file at" in err, "a proof that is not on disk is refused")
got, err = lg.add_entry("galaxy", "expense", 500, "groq", proof=proof("groq-oct.pdf"), now=OCT)
ok(not err and got["proof"] == "proofs/groq-oct.pdf", "a proof that is there is recorded")
ok(len(rows()) == 3 and not os.path.exists(BOOK + ".tmp"),
   "refusals wrote nothing; the three entries were written atomically")

# ---------------------------------------------------------------------------------------
head("3. nothing is ever deleted")
counts = [len(rows())]
v, err = lg.void_entry("L-0001", "entered twice", now=OCT)
counts.append(len(rows()))
ok(not err and v["void"] and v["voidReason"] == "entered twice"
   and v["voidedAt"] == "2026-10-09T12:00:00" and v["amount"] == 50000,
   "a void keeps the row and its figures, and adds the reason and the time")
for args, why in ((("L-0001", "again"), "already void"), (("L-0999", "x"), "no entry L-0999"),
                  (("L-0002", "   "), "needs a reason")):
    got, err = lg.void_entry(*args, now=OCT)
    ok(got is None and why in err, "refused: %s" % err)
e, _ = lg.add_entry("galaxy", "expense", 700, "hosting", now=OCT)
counts.append(len(rows()))
ok(e["id"] == "L-0004" and counts == sorted(counts) and counts[-1] == 4,
   "ids are never reused and the file never shrinks: %s rows" % counts)
ok(lg.find_entry(last=True)["id"] == "L-0004" and lg.find_entry("l-0001")["void"],
   "the last standing entry and an entry by id are found")

# ---------------------------------------------------------------------------------------
head("4. the totals")
fresh()
lg.add_entry("galaxy", "expense", 50000, "groq", now=OCT)                          # unverified
lg.add_entry("galaxy", "expense", 120000, "hosting", proof=proof("host.pdf"), now=OCT)
lg.add_entry("galaxy", "expense", 999, "groq", currency="USD", now=OCT)           # $9.99
lg.add_entry("galaxy", "expense", 30000, "domain", on="2026-09-15", now=OCT)
lg.add_entry("boss", "income", 2500000, "youtube", now=OCT)
lg.add_entry("galaxy", "expense", 77700, "groq", now=OCT)
lg.void_entry("L-0006", "wrong amount", now=OCT)
october = lg.parse_period("October mein", TODAY)
s = lg.summary("galaxy", october)
inr, usd = s["totals"]["INR"], s["totals"]["USD"]
ok(inr["expense"] == 170000 and inr["unverifiedExpense"] == 50000 and inr["entries"] == 2
   and usd["expense"] == 999 and usd["entries"] == 1 and s["voided"] == 1,
   "Galaxy, October: ₹1,700.00 of which ₹500.00 unverified; $9.99 apart; one void",
   json.dumps(s["totals"]))
ok("in INR, income ₹0.00, expenses ₹1,700.00, net -₹1,700.00 across 2 entries - "
   "₹500.00 of it unverified (no proof)" in s["sentence"]
   and "in USD, income $0.00, expenses $9.99" in s["sentence"]
   and "1 voided entry not counted" in s["sentence"],
   "the sentence keeps each currency on its own and names the void", s["sentence"])
ok(lg.summary("galaxy", lg.parse_period("pichle mahine", TODAY))["totals"]["INR"]["expense"]
   == 30000, "September is filtered by the day the money moved")
whole = lg.summary("galaxy")
ok(whole["totals"]["INR"]["expense"] == 200000, "all time: every standing rupee, the void not")
boss = lg.summary("boss", october)
ok("none of it unverified" not in boss["sentence"]
   and "₹25,000.00 of it unverified" in boss["sentence"],
   "an income with no proof is unverified too", boss["sentence"])
lg.add_entry("boss", "expense", 100, "course", proof=proof("course.png"), on="2026-08-02",
             now=OCT)
aug = lg.summary("boss", lg.parse_period("august", TODAY))
ok("none of it unverified" in aug["sentence"], "fully proven: 'none of it unverified' is said",
   aug["sentence"])
ok(lg.summary("boss", lg.parse_period("2026-01", TODAY))["sentence"]
   == "Your business book, January 2026: no entries.", "an empty period says so")
u = lg.unverified(None, None)
ok([x["id"] for x in u["entries"]] == ["L-0001", "L-0003", "L-0004", "L-0005"]
   and u["sentence"].startswith("4 entries in either book, all time, carry no proof"),
   "unverified(): the four standing entries with no proof, the void left out", u["sentence"])
ok(lg.balance("galaxy")["sentence"].startswith("Galaxy's own book, everything recorded:"),
   "balance(): everything recorded")
ok(lg.unverified("boss", lg.parse_period("august", TODAY))["sentence"]
   == "No unverified entry in your business book, August 2026 - its one entry carries a proof."
   and lg.unverified("boss", lg.parse_period("2026-01", TODAY))["sentence"]
   == "There are no entries in your business book, January 2026, so nothing is unverified.",
   "fully proven says so; an empty book never claims its entries carry proofs")
raw = json.load(open(BOOK, encoding="utf-8"))
raw["entries"].append(dict(raw["entries"][0], id="L-0099", amount=500.5))
raw["entries"].append({"id": "L-0100", "book": "galaxy"})
open(BOOK, "w", encoding="utf-8").write(json.dumps(raw))
entries, bad = lg.read_book()
s = lg.summary("galaxy")
ok(bad == 2 and s["totals"]["INR"]["expense"] == 200000
   and "2 rows in the file could not be read and are not counted" in s["sentence"],
   "a hand-edited 500.5 and a broken row are named, never summed", s["sentence"])


def walk(v):
    if isinstance(v, float):
        return True
    if isinstance(v, dict):
        return any(walk(x) for x in v.values())
    if isinstance(v, list):
        return any(walk(x) for x in v)
    return False


ok(not walk(lg._raw_rows()) and not walk(entries) and not walk(s),
   "reading the file yields no float anywhere - even the hand-edited 500.5 arrives as a refusal")
e, err = lg.add_entry("galaxy", "expense", 100, "test", now=OCT)
ok(not err and sum(1 for r in lg._raw_rows() if r.get("id") in ("L-0099", "L-0100")) == 2,
   "and a write carries the unreadable rows forward untouched")

# ---------------------------------------------------------------------------------------
head("5. the sentence")
fresh()
req = lg.parse_request("Groq ka bill 500 rupaye add karo", "add", TODAY)
want = {"book": "galaxy", "kind": "expense", "amount_paise": 50000, "currency": "INR",
        "category": "groq", "on": "2026-10-09", "proof": "none",
        "note": "Groq ka bill 500 rupaye add karo",
        "entry": "An expense of ₹500.00 for groq, in Galaxy's own book, dated 9 October "
                 "2026, with no proof attached, so it would be marked unverified"}
ok(req["tool"] == "add_ledger_entry" and req["params"] == want,
   "Groq ka bill 500 rupaye add karo -> the card's exact parameters", json.dumps(req))
req = lg.parse_request("client ka payment 25000 aaya, business book mein add karo, receipt "
                       "proofs/inv-7.pdf", "add", TODAY)
ok("no file at proofs/inv-7.pdf" in req["error"], "a proof that is not there: refused in words",
   req["error"])
proof("inv-7.pdf")
req = lg.parse_request("client ka payment 25000 aaya, business book mein add karo, receipt "
                       "proofs/inv-7.pdf on 2026-10-02", "add", TODAY)
ok(req["params"]["book"] == "boss" and req["params"]["kind"] == "income"
   and req["params"]["amount_paise"] == 2500000 and req["params"]["proof"] == "proofs/inv-7.pdf"
   and req["params"]["on"] == "2026-10-02" and "with proof at proofs/inv-7.pdf"
   in req["params"]["entry"], "a business income, with its proof and its date", json.dumps(req))
for text, why in (("chai 50 rupaye add karo", "Which book"),
                  ("Groq 500 rupaye add karo", "coming in or going out"),
                  ("Groq ka bill 500 aur 300 add karo", "more than one figure"),
                  ("Groq ka bill add karo", "did not hear an amount")):
    ok(why in lg.parse_request(text, "add", TODAY)["error"], "%r refused: %s" % (text, why))
lg.add_entry("galaxy", "expense", 50000, "groq", now=OCT)
lg.add_entry("galaxy", "expense", 120000, "hosting", now=OCT)
req = lg.parse_request("L-1 void karo kyunki entered twice", "void", TODAY)
ok(req["params"] == {"id": "L-0001", "reason": "entered twice",
                     "entry": "L-0001, expense of ₹500.00 for groq in Galaxy's own book, "
                              "dated 2026-10-09, unverified"},
   "a void by id, its reason after 'kyunki'", json.dumps(req))
req = lg.parse_request("last entry galat thi, void karo", "void", TODAY)
ok(req["params"]["id"] == "L-0002" and req["params"]["reason"],
   "'last entry' is the most recent one still standing; with no 'because', his own words are "
   "the reason", json.dumps(req["params"]))
ok("no entry L-0042" in lg.parse_request("L-0042 void karo", "void", TODAY)["error"],
   "an unknown id is refused before a card")

# ---------------------------------------------------------------------------------------
head("6. the chat")
for q, action in (("Groq ka bill 500 rupaye add karo", "add"),
                  ("is mahine ka kharcha kitna hua", "summary"),
                  ("business income kitna hai October mein", "summary"),
                  ("koi unverified entry hai kya", "unverified"),
                  ("how much did I spend this month", "summary"),
                  ("Galaxy ka balance batao", "balance"),
                  ("L-0003 void karo, galat entry thi", "void"),
                  ("client payment 25000 aaya, business book mein add karo", "add")):
    ok(server.classify_query(q) == ("ledger", True) and server.ledger_request(q) == action,
       "%r -> ledger (%s)" % (q, action))
for q in ("what is income tax", "how much income tax do I pay", "what does Groq cost",
          "add a reminder to pay the electricity bill on 5th", "add a meeting at 5 pm",
          "Quant ka track record kya hai", "Galaxy ka confidence kitna hai", "RSI of Reliance",
          "what is a balance sheet", "remember that the Groq bill was 500"):
    ok(server.classify_query(q)[0] != "ledger", "%r is not a ledger question (%s)"
       % (q, server.classify_query(q)[0]))

# ---------------------------------------------------------------------------------------
head("7. the gate")
fresh()
# The server reads the real clock, so the card it puts up is dated today.
now_card = lg.parse_request("Groq ka bill 500 rupaye add karo", "add")["params"]
st, p = server.answer_ledger("Groq ka bill 500 rupaye add karo", "test-ledger", "ledger")
pending = hands.pending_public()
ok(st == 200 and p["route"] == "ledger" and pending and pending["tool"] == "add_ledger_entry"
   and pending["params"] == now_card
   and p["answer"] == now_card["entry"] + ", sir. Shall I write it down?",
   "the first sentence puts up a card, in the card's own words", p.get("answer"))
ok(not os.path.exists(BOOK), "and writes NOTHING - never on the first sentence")
st, p = hands.cancel(door="voice", proposal_id=pending["id"])
ok(not os.path.exists(BOOK) and hands.pending_public() is None, "a no writes nothing")
server.answer_ledger("Groq ka bill 500 rupaye add karo", "test-ledger", "ledger")
hands.withdraw()
ok(not os.path.exists(BOOK) and hands.pending_public() is None,
   "a change of subject withdraws it and writes nothing")
server.answer_ledger("Groq ka bill 500 rupaye add karo", "test-ledger", "ledger")
st, p = hands.execute(door="voice", proposal_id=hands.pending_public()["id"])
book = rows()
ok(p["ok"] and p["answer"] == "Written into Galaxy's own book as L-0001: expense of "
   "₹500.00 for groq, unverified, with no proof."
   and len(book) == 1 and book[0]["amount"] == 50000 and book[0]["enteredBy"] == "chat",
   "a yes runs the hand, which writes exactly the card's figures and says so", p.get("answer"))

httpd = ThreadingHTTPServer(("127.0.0.1", 0),
                            partial(server.GalaxyHandler, directory=server.VIEWER_DIR))
threading.Thread(target=httpd.serve_forever, daemon=True).start()
base = "http://127.0.0.1:%d" % httpd.server_address[1]


def post(route, body):
    req = urllib.request.Request(base + route, data=json.dumps(body).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.load(r)
    except urllib.error.HTTPError as exc:
        return json.load(exc)


try:
    fresh()
    first = post("/chat", {"question": "business mein client payment 25000 aaya, add karo",
                           "session": "test-ledger"})
    ok((first.get("pending") or {}).get("tool") == "add_ledger_entry" and not os.path.exists(BOOK),
       "THROUGH /chat: the sentence is a card and nothing is written", json.dumps(first)[:300])
    second = post("/chat", {"question": "haan", "session": "test-ledger"})
    book = rows()
    ok(second.get("ok") and len(book) == 1 and book[0]["book"] == "boss"
       and book[0]["kind"] == "income" and book[0]["amount"] == 2500000,
       "and 'haan' through the same door writes ₹25,000.00 into the business book",
       json.dumps(second)[:300])
    third = post("/chat", {"question": "haan", "session": "test-ledger"})
    ok(len(rows()) == 1, "a second 'haan' writes nothing more", json.dumps(third)[:200])
    read = post("/chat", {"question": "business income kitna hai is mahine",
                          "session": "test-ledger"})
    ok(read.get("route") == "ledger" and "₹25,000.00" in (read.get("answer") or "")
       and read.get("pending") is None,
       "a read needs no gate: answered from the book", (read.get("answer") or "")[:200])
    wire = post("/tools", {"cmd": "propose", "tool": "add_ledger_entry", "door": "ledger",
                           "params": want})
    ok(wire.get("refused") == "wrong-door" and hands.pending_public() is None,
       "a body claiming the ledger door over /tools is refused", json.dumps(wire)[:200])
finally:
    httpd.shutdown()
    httpd.server_close()

for door in ("tag", "button", "voice"):
    st, p = hands.propose("add_ledger_entry", dict(want), door=door)
    ok(p.get("refused") == "wrong-door" and hands.pending_public() is None,
       "the %s door is refused, nothing pending" % door)
st, p = hands.propose_chain([{"tool": "add_ledger_entry", "params": dict(want)}], door="tag")
ok(not p.get("ok") and hands.pending_public() is None, "and a chain step naming it is refused")
manifest = hands.prompt_block()
ok("add_ledger_entry" not in manifest and "void_ledger_entry" not in manifest
   and "save_note" in manifest, "the brain is never told the ledger's hands exist")
count = len(rows())
tampered = dict(want, amount_paise=500000)          # ₹5,000 under a card that says ₹500
done = _proc.run([sys.executable, os.path.join(HERE, "tools", "add_ledger_entry.py")],
                 input=json.dumps(tampered), capture_output=True, text=True, encoding="utf-8",
                 timeout=60)
ok(done.returncode == 1 and "disagree" in done.stdout and len(rows()) == count,
   "a card whose sentence and figures disagree writes nothing", done.stdout.strip())
st, p = server.answer_ledger("Groq ka bill 500 rupaye add karo", "test-ledger", "ledger",
                             guest=True)
ok(p.get("refused") == "guest" and hands.pending_public() is None
   and not re.search(r"\d", p["answer"]), "a guest: no card, no figure")
st, p = server.answer_ledger("is mahine ka kharcha kitna hua", "test-ledger", "ledger",
                             guest=True)
ok(p.get("refused") == "guest" and not re.search(r"\d", p["answer"]),
   "and no read either")
fresh()
lg.add_entry("galaxy", "expense", 50000, "groq", now=OCT)
server.answer_ledger("L-0001 void karo kyunki entered twice", "test-ledger", "ledger")
pending = hands.pending_public()
ok(pending and pending["tool"] == "void_ledger_entry" and not rows()[0]["void"],
   "a void is a card too, and the entry stands until a yes")
st, p = hands.execute(door="voice", proposal_id=pending["id"])
ok(p.get("ok") and rows()[0]["void"] and rows()[0]["voidReason"] == "entered twice"
   and len(rows()) == 1, "a yes strikes it out - and the row is still there", p.get("answer"))

# ---------------------------------------------------------------------------------------
head("7b. the subprocess boundary, crossed the way the server crosses it")
# MEASURED 2026-10-09: every card carries "₹", and hands._spawn() writes it to the hand's stdin
# as UTF-8 - which a Windows python started WITHOUT PYTHONIOENCODING reads in the ANSI
# codepage, so the card arrived as "â‚¹500.00" and the card check refused every live write.
# The checks above crossed this boundary too and still passed, because this file is usually
# run with PYTHONIOENCODING=utf-8 and the hands inherited it. So these take it away first -
# from os.environ, which is what hands._spawn() hands down - and then go through the real
# spawner with the real scripts. Whatever the caller's environment, this is the server's.
hidden = {k: os.environ.pop(k) for k in ("PYTHONIOENCODING", "PYTHONUTF8") if k in os.environ}
try:
    fresh()
    server.answer_ledger("Groq ka bill 1,250.50 rupaye add karo", "test-ledger", "ledger")
    card = hands.pending_public()
    ok(card and "₹1,250.50" in card["params"]["entry"],
       "a card carrying ₹ is up, with no PYTHONIOENCODING anywhere in the environment")
    st, p = hands.execute(door="voice", proposal_id=card["id"])
    book = rows()
    ok(p.get("ok") and len(book) == 1 and book[0]["amount"] == 125050
       and "₹1,250.50" in p["answer"],
       "and a yes WRITES it - the ₹ survived stdin, and the reply came back intact",
       p.get("answer"))
    # Its own entry, written in-process, so the void hand is judged on its own even when the
    # add hand above is the one that broke.
    fresh()
    lg.add_entry("galaxy", "expense", 125050, "groq")
    server.answer_ledger("L-0001 void karo kyunki entered twice", "test-ledger", "ledger")
    card = hands.pending_public()
    st, p = (hands.execute(door="voice", proposal_id=card["id"]) if card
             else (None, {"answer": "no card went up"}))
    ok(p.get("ok") and rows()[0]["void"],
       "and the void hand, whose card carries ₹ too, strikes it out", p.get("answer"))
finally:
    os.environ.update(hidden)

# ---------------------------------------------------------------------------------------
head("8. the source")


def floats_in(path):
    tree = ast.parse(io.open(path, encoding="utf-8").read())
    hits = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, float):
            hits.append("literal %r line %d" % (node.value, node.lineno))
        elif isinstance(node, ast.Call) and ast.unparse(node.func) == "float":
            hits.append("float() line %d" % node.lineno)
        elif isinstance(node, (ast.BinOp, ast.AugAssign)) and isinstance(node.op, ast.Div):
            hits.append("'/' line %d" % node.lineno)
    return tree, hits


for name in ("ledger.py", "tools/add_ledger_entry.py", "tools/void_ledger_entry.py"):
    tree, hits = floats_in(os.path.join(HERE, name))
    ok(not hits, "%s has no float literal, no float() and no '/' operator" % name, str(hits))
src = io.open(os.path.join(HERE, "ledger.py"), encoding="utf-8").read()
tree = ast.parse(src)
imported = set()
for node in ast.walk(tree):
    if isinstance(node, ast.Import):
        imported |= {a.name.split(".")[0] for a in node.names}
    elif isinstance(node, ast.ImportFrom):
        imported.add((node.module or "").split(".")[0])
ok(imported <= {"datetime", "json", "os", "re", "sys", "threading", "argparse"},
   "ledger.py imports only the standard library's basics", str(sorted(imported)))
calls = {ast.unparse(n.func) for n in ast.walk(tree) if isinstance(n, ast.Call)}
ok(not calls & {"os.remove", "os.unlink", "shutil.rmtree", "os.rmdir", "pathlib.Path.unlink"},
   "ledger.py deletes no file")
ok(not re.search(r"requests\.|urllib|http\.client|socket|call_model|groq\.|openai|gemini\.",
                 src, re.I), "and reaches no network and no model")
srv = ast.parse(io.open(os.path.join(HERE, "server.py"), encoding="utf-8").read())
direct = sorted({ast.unparse(n.func) for n in ast.walk(srv) if isinstance(n, ast.Call)}
                & {"ledger.add_entry", "ledger.void_entry", "ledger._write_book"})
ok(not direct, "server.py never writes the book itself - only through a hand", str(direct))
for name, fn in (("add_ledger_entry", "ledger.add_entry"),
                 ("void_ledger_entry", "ledger.void_entry")):
    text = io.open(os.path.join(HERE, "tools", name + ".py"), encoding="utf-8").read()
    ok(fn + "(" in text, "%s.py is the one that calls %s()" % (name, fn))
reg = {t["id"]: t for t in hands.registry(force=True)}
ok(all(reg[i]["doors"] == ("ledger",) and not reg[i]["triggers"]
       for i in ("add_ledger_entry", "void_ledger_entry"))
   and all(not t["doors"] for i, t in reg.items() if "ledger" not in i),
   "both hands are door-bound with no trigger; every other hand keeps every door")
ignore = io.open(os.path.join(HERE, ".gitignore"), encoding="utf-8").read().split()
ok("ledger.json" in ignore and "proofs/" in ignore, "ledger.json and proofs/ are gitignored")

hands.LEDGER_PATH = REAL_TOOLS
after = {p: (open(p, "rb").read() if os.path.exists(p) else None)
         for p in (REAL_BOOK, str(REAL_TOOLS))}
ok(after == before, "the real ledger.json and tools-ledger.json were never touched")
shutil.rmtree(TMP, ignore_errors=True)

print("\n  %d checks, %d failed\n" % (checks, len(failures)))
if failures:
    for claim in failures:
        print("    FAILED: %s" % claim)
    print("")
sys.exit(min(len(failures), 120))
