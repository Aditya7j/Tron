"""Revenue Mode, phase 1: every rule that can be proved without a real client.

The whole loop runs here against a FAKE platform session and a SCRIPTED model: two platforms that
are not signed in say so in words; a third is searched, its jobs read and gated, one bid placed
under the day's cap; the bid is awarded, the work made, checked and left READY - and nothing goes
out until the employer's "submit it" card, which delivers the folder as he left it. A client's
"was this AI?" is answered yes, an off-platform offer declined; a payment is read only from a row
naming the job (never from the platform's sample rows), and reaches the Ledger only as the
Ledger's own card. Ctrl+M switches it off; a challenge pauses a platform for the day.

Then the REAL bid form path - operator_core's finder and executor in a real headless Chrome on a
fixture page built from the measured Freelancer.com form: three labelled fields, paid upgrade
boxes, "Place Bid" - including the refusal to bid with an upgrade ticked.

Run it:  python test_revenue.py
Exit status is the number of failures.
"""
import http.server
import json
import os
import pathlib
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time

HERE = pathlib.Path(__file__).resolve().parent
TMP = tempfile.mkdtemp(prefix="revenue-test-")
CONFIG = os.path.join(TMP, "config.json")
os.environ.update({"TRONE_REVENUE_BOOK": os.path.join(TMP, "revenue-book.json"),
                   "TRONE_REVENUE_LOG": os.path.join(TMP, "revenue-log.json"),
                   "TRONE_REVENUE_STATE": os.path.join(TMP, "revenue-state.json"),
                   "TRONE_REVENUE_WORK": os.path.join(TMP, "work"),
                   "TRONE_REVENUE_CONFIG": CONFIG,
                   "TRONE_LEDGER_PATH": os.path.join(TMP, "ledger.json"),
                   "TRONE_PROOFS_DIR": os.path.join(TMP, "proofs")})
sys.path.insert(0, str(HERE))

import hands                                                   # noqa: E402
import ledger                                                  # noqa: E402
import revenue                                                 # noqa: E402
from tools import _proc                                        # noqa: E402
from tools import operator_core as core                        # noqa: E402

REAL_TOOLS = hands.LEDGER_PATH
hands.LEDGER_PATH = pathlib.Path(TMP) / "tools-ledger.json"
FAILURES = []


def check(label, got, want):
    ok = got == want
    print("  %s %s" % ("ok  " if ok else "FAIL", label))
    if not ok:
        print("       got  %r\n       want %r" % (got, want))
        FAILURES.append(label)


with open(CONFIG, "w", encoding="utf-8") as fh:
    json.dump({"revenue": {"searches": ["react"], "dailyBidLimit": 1, "minGapMinutes": 30}}, fh)

# ------------------------------------------------------------------------------ measured text

# His profile as Freelancer.com printed it on 2026-10-15 (cut), furniture and all.
PROFILE = """Upload cover photo
View client profile
Aditya
@Aditya776
0.0
0%
"Experienced Frontend Developer"
$10 USD / Hour
As a seasoned Frontend Developer with 1.5 years of dedicated experience, I specialize in crafting dynamic and user-friendly web solutions. Proficient in HTML, CSS, and JavaScript, my expertise extends to React.js and SASS, enabling me to create responsive interfaces.
Edit profile
Portfolio
Manage portfolio
No portfolio items have been added yet
No reviews to see here
Great reviews help you win more bids.
Frontend Developer
Twinleaves E-commerce Private Limited
Certifications
Add certification
No certifications have been added."""

# The Transaction History page on an account with no transactions: sample rows that never leave.
SKELETON = """My Transactions
Showing 1-10 of 235 transactions
12/01/2019
Random Stuff
PROJECT FEE
$56004.44 USD
PROJECT NAME
Build a website
EMPLOYER
David Wang
STATUS
PAID"""

FIT_JOB = """React pricing card component
Open
Project Details
$20.00 - 60.00 USD
I need a responsive pricing card component built in React.js with three tiers. Style it with SASS.
Skills Required
React.js
CSS
Project ID: 1
"""
FIGMA_JOB = """Figma mobile app design
Project Details
$30.00 - 250.00 USD
Design a mobile app in Figma, ten screens.
Skills Required
Figma
"""
LONG_JOB = """Ongoing React developer
Project Details
$20.00 - 500.00 USD
Long-term React work, ongoing every month. Contact me on WhatsApp.
Skills Required
React.js
"""
GBP_JOB = """Fix a CSS bug
Project Details
£20 - 50 GBP
Fix a CSS layout bug in my header.
Skills Required
CSS
"""

# ------------------------------------------------------------------------------ the pure parts

print("\nthe pure parts")
check("a budget in dollars", revenue.budget_in("Project Details\n$30.00 – 250.00 USD"),
      {"currency": "USD", "lo": 3000, "hi": 25000, "hourly": False})
check("a budget in rupees, with a comma", revenue.budget_in("₹600 – 1,500 INR"),
      {"currency": "INR", "lo": 60000, "hi": 150000, "hourly": False})
check("an hourly budget is marked hourly",
      revenue.budget_in("$15.00 - 25.00 USD per hour")["hourly"], True)
check("skills required, read to the project id", revenue.required_skills(FIT_JOB),
      ["React.js", "CSS"])
facts_text = revenue.profile_facts(PROFILE)
check("the platform's furniture is cut from his profile",
      [w for w in ("portfolio", "reviews", "certification") if w in facts_text.lower()], [])
check("his own words stay", "Twinleaves E-commerce" in facts_text and "SASS" in facts_text, True)
check("his skills, from his own words", revenue.skills_in(facts_text),
      ["HTML", "CSS", "JavaScript", "React.js", "SASS"])
check("his rate, from his profile", revenue.rate_in(PROFILE), {"USD": 10})
check("a long-term, WhatsApp job is refused by rule", len(revenue.red_flags(LONG_JOB)), 2)
check("a plain job has no red flag", revenue.red_flags(FIT_JOB), [])
check("a card whose minimum is over 4 hours at his rate is not opened",
      revenue.card_skip({"currency": "USD", "lo": 25000, "hi": 75000, "hourly": False},
                        {"USD": 10}, revenue.settings()[0]).startswith("its minimum budget"), True)
check("a card he can price is opened", revenue.card_skip(
    {"currency": "USD", "lo": 2000, "hi": 6000, "hourly": False}, {"USD": 10},
    revenue.settings()[0]), "")
check("price: his rate x hours, at least the client's minimum",
      revenue.price({"currency": "USD", "lo": 2000, "hi": 6000}, 3, {"USD": 10}), (3000, ""))
check("price: never above the client's maximum",
      revenue.price({"currency": "USD", "lo": 500, "hi": 2000}, 3, {"USD": 10})[0], None)
check("price: no rate in that currency is a skip, not a conversion",
      "no hourly rate in GBP" in revenue.price({"currency": "GBP", "lo": 1, "hi": 9999}, 2,
                                               {"USD": 10})[1], True)
good = ("You need a responsive React.js pricing card with three tiers, styled with SASS. I would "
        "build it as one component with the tiers passed in as props, so it stays easy to change. "
        "My work is in React.js, HTML, CSS and SASS. Do you have the tier names ready?")
check("an honest bid passes vet_bid", revenue.vet_bid(good, facts_text, FIT_JOB), [])
for bad, why in (("I am a certified React expert.", "certification"),
                 ("With 5 years of experience I can do it.", "years"),
                 ("See my portfolio at www.me.dev", "portfolio and link"),
                 ("I'll deliver it tomorrow, guaranteed.", "time and guarantee"),
                 ("Message me on WhatsApp to discuss.", "off platform"),
                 ("I am a real human developer.", "human claim"),
                 ("Hi [Client Name], I can help.", "placeholder")):
    check("vet_bid refuses: %s" % why, bool(revenue.vet_bid(bad, facts_text, FIT_JOB)), True)
check("the sample rows are never a payment",
      revenue.payment_in(SKELETON, {"title": "Build a website", "submittedAt": "2019-01-01"},
                         revenue.PLATFORMS["freelancer"]["placeholders"]), None)
paid_text = SKELETON + "\n10/17/2026\nMilestone release\n$30.00 USD\nPROJECT NAME\nReact pricing card component\nSTATUS\nPAID"
check("a row naming the job, after submission, is",
      revenue.payment_in(paid_text, {"title": "React pricing card component",
                                     "submittedAt": "2026-10-16T10:00:00"},
                         revenue.PLATFORMS["freelancer"]["placeholders"]),
      {"amount": 3000, "currency": "USD", "on": "2026-10-17",
       "line": revenue.payment_in(paid_text, {"title": "React pricing card component",
                                              "submittedAt": "2026-10-16"}, ())["line"]})
check("a row dated before the submission is not",
      revenue.payment_in(paid_text, {"title": "React pricing card component",
                                     "submittedAt": "2026-10-20"}, ()), None)

print("\nthe employer's sentences")
for said, want in (("be in your revenue mode", "start"), ("start revenue mode", "start"),
                   ("revenue mode on", "start"), ("go into revenue mode", "start"),
                   ("stop revenue mode", "stop"), ("exit revenue mode", "stop"),
                   ("revenue update", "report"), ("how's revenue mode going?", "report"),
                   ("submit R-3", "submit")):
    check("%r -> %s" % (said, want), (revenue.parse_request(said) or {}).get("action"), want)
for asked in ("did you use AI for this?", "Is this AI generated?", "was ChatGPT used here?",
              "Are you a bot?", "were any AI tools involved"):
    check("asked %r is the AI question" % asked, bool(revenue._AI_ASKED.search(asked)), True)
for plain in ("I need an AI chatbot built", "Can you use React?", "the main page"):
    check("%r is not" % plain, bool(revenue._AI_ASKED.search(plain)), False)
check("a bare 'submit it' is nobody's while nothing is ready", revenue.parse_request("submit it"),
      None)
check("'what is revenue' is not ours", revenue.parse_request("what is revenue"), None)
check("'submit R-3' names R-0003", revenue.parse_request("submit R-3")["job"], "R-0003")

# ------------------------------------------------------------------------------ the fakes

class Script:
    """The model, scripted by which prompt is asking."""

    def __init__(self):
        self.down = None
        self.calls = []

    def __call__(self, messages):
        system, user = messages[0]["content"], messages[1]["content"]
        self.calls.append(system[:30])
        if self.down:
            return None, self.down
        if system == revenue.FIT_SYSTEM:
            if "CSS layout bug" in user:
                return json.dumps({"deliverables": [{"quote": "Fix a CSS layout bug in my header",
                                                     "skill": "CSS"}], "kind": "code",
                                   "hours": 1, "single": True, "needs": []}), ""
            if "Figma" in user:
                return json.dumps({"deliverables": [{"quote": "Design a mobile app in Figma",
                                                     "skill": None}], "kind": "other",
                                   "hours": 20, "single": True, "needs": []}), ""
            return json.dumps({"deliverables": [{"quote": "responsive pricing card component "
                                                          "built in React.js", "skill": "React.js"},
                                                {"quote": "Style it with SASS", "skill": "SASS"}],
                               "kind": "code", "hours": 3, "single": True, "needs": []}), ""
        if system == revenue.BID_SYSTEM:
            return json.dumps({"letter": good}), ""
        if system == revenue.VERIFY_SYSTEM:
            return json.dumps({"unsupported": []}), ""
        if system == revenue.PLAN_SYSTEM:
            return json.dumps({"kind": "code", "files": [{"name": "PricingCard.jsx",
                                                          "what": "the component"},
                                                         {"name": "pricing.js", "what": "tiers"}],
                               "summary": "A React pricing card with three tiers.",
                               "missing": []}), ""
        if system == revenue.FILE_SYSTEM:
            if "pricing.js" in user.split("THIS FILE:")[1][:40]:
                return "```js\nconst tiers = ['Basic', 'Pro', 'Team'];\nmodule.exports = tiers;\n" \
                       "console.log(tiers.length);\n```", ""
            return ("export default function PricingCard({ tiers }) {\n  return (\n    <div "
                    "className=\"cards\">{tiers.map(t => <div key={t}>{t}</div>)}</div>\n  );\n}\n"), ""
        return None, "unexpected prompt"


MODEL = Script()
revenue.configure(chat=MODEL, work_chat=MODEL, config=lambda: json.load(open(CONFIG)))
JOBS = {"https://www.freelancer.com/projects/react/Ongoing": LONG_JOB,
        "https://www.freelancer.com/projects/design/Figma": FIGMA_JOB,
        "https://www.freelancer.com/projects/css/Fix-bug": GBP_JOB,
        "https://www.freelancer.com/projects/react/Pricing-Card": FIT_JOB}


class FakeSession:
    """The platform verbs Revenue Mode has, with nothing behind them but this dict."""
    signed_in = {"freelancer": True, "upwork": False, "fiverr": False}
    awarded = set()
    page_extra = {}
    earnings_text = SKELETON
    abort_at = None
    challenge = False
    bids, messages, deliveries = [], [], []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def _gate(self, key, step):
        if not self.signed_in[key]:
            raise revenue.NotSignedIn(key)
        if self.challenge and key == "freelancer":
            raise revenue.Challenge(key)
        if self.abort_at == step:
            raise core.Aborted(step)

    def profile(self, key):
        self._gate(key, "profile")
        return {"text": revenue.profile_facts(PROFILE), "url": "u", "name": "Aditya"}

    def search(self, key, query):
        self._gate(key, "searching")
        return [{"url": u, "card": t[:80], "title": t.splitlines()[0]} for u, t in JOBS.items()]

    def read_job(self, key, url):
        self._gate(key, "read")
        return {"url": url, "title": JOBS[url].splitlines()[0], "text": JOBS[url],
                "full": JOBS[url]}

    def place_bid(self, key, job, bid):
        FakeSession.bids.append((job["url"], bid))
        return "bid", "Retract Bid"

    def check_award(self, key, job):
        text = JOBS.get(job["url"], "") + FakeSession.page_extra.get(job["url"], "")
        return job["url"] in FakeSession.awarded, text

    def accept_award(self, key, job):
        return True

    def send_message(self, key, job, text):
        FakeSession.messages.append(text)
        return True

    def deliver(self, key, job, files, note):
        FakeSession.deliveries.append(([os.path.basename(f) for f in files], note,
                                       [open(f, encoding="utf-8").read() for f in files]))
        return "submitted", "the page shows the delivery"

    def earnings(self, key):
        return FakeSession.earnings_text

    def screenshot(self, path):
        with open(path, "wb") as fh:
            fh.write(b"\x89PNG proof")
        return path


def tick():
    return revenue.tick(session_factory=FakeSession)


# ------------------------------------------------------------------------------ the loop

print("\nthe switch")
check("off, a pass does nothing", tick(), ["Revenue Mode is off"])
done = _proc.run([sys.executable, str(HERE / "tools" / "revenue_start.py")],
                 input=b'{"bids": 99}', capture_output=True)
check("revenue_start refuses a cap above the ceiling", done.returncode, 1)
done = _proc.run([sys.executable, str(HERE / "tools" / "revenue_start.py")],
                 input=b'{"bids": 1}', capture_output=True, env=dict(os.environ))
check("revenue_start turns it on", (done.returncode, revenue.read_state().get("on"),
                                    revenue.read_state().get("daily")), (0, True, 1))
check("and says what it will do", b"up to 1 bid a day on Freelancer.com, Upwork and Fiverr"
      in done.stdout, True)

print("\nthe first pass")
notes = tick()
check("Upwork, not signed in, is a sentence",
      "I'm not signed into Upwork, sir - sign in to it in the DevTools Chrome and I'll pick it "
      "up on the next pass." in notes, True)
check("so is Fiverr", any(n.startswith("I'm not signed into Fiverr, sir") for n in notes), True)
state = revenue.read_state()
check("and the state remembers both as down, Freelancer as up",
      {k: v["ok"] for k, v in state["platforms"].items()},
      {"upwork": False, "fiverr": False, "freelancer": True})
check("his Freelancer profile was read as facts", "Twinleaves" in
      state["profiles"]["freelancer"]["text"], True)
book = {j["title"]: j for j in revenue.read_book()}
check("four jobs read", len(book), 4)
check("the long-term WhatsApp job skipped by rule",
      (book["Ongoing React developer"]["status"],
       "off the platform" in book["Ongoing React developer"]["why"][0]), ("skipped", True))
check("the Figma job skipped: not his skill", "Figma" in book["Figma mobile app design"]["why"][0]
      or "skill" in " ".join(book["Figma mobile app design"]["why"]), True)
check("the GBP job skipped: no rate of his in GBP",
      any("GBP" in w for w in book["Fix a CSS bug"]["why"]), True)
fit = book["React pricing card component"]
check("the fitting job was bid on", (fit["status"], len(FakeSession.bids)), ("bid", 1))
check("at his rate: 3 hours x $10 = $30", (fit["bid"]["amount"], fit["bid"]["currency"],
                                           fit["bid"]["days"]), (3000, "USD", 2))
row = [r for r in revenue.read_log() if r["kind"] == "bid"][0]
check("the bid is in the log, with its letter and why", (row["status"], row["letter"] == good,
                                                         "React.js" in row["why"]),
      ("bid", True, True))

print("\nthe cap and the gap")
JOBS["https://www.freelancer.com/projects/react/Pricing-Card-2"] = FIT_JOB.replace(
    "React pricing card component", "React pricing card two")
notes = tick()
check("with today's bid placed, the pass does not look for more",
      any("today's 1 bid is placed - not looking for more" in n for n in notes), True)
check("so a second fitting job is neither bid on nor thrown away",
      ([j for j in revenue.read_book() if j["title"] == "React pricing card two"],
       len(FakeSession.bids)), ([], 1))

print("\nawarded: the work, and the stop")
FakeSession.awarded.add(fit["url"])
tick()
fit = revenue.find_job(fit["id"])
check("awarded, worked, READY", fit["status"], "ready")
folder = os.path.join(TMP, "work", fit["id"])
check("the files, the note and REVIEW.txt are in its folder", sorted(os.listdir(folder)),
      ["DELIVERY-NOTE.txt", "PricingCard.jsx", "REVIEW.txt", "pricing.js"])
check("the fence was stripped and the JS checked", open(os.path.join(folder, "pricing.js"))
      .read().startswith("const tiers"), True)
check("NOTHING was delivered", FakeSession.deliveries, [])
check("the report says ready for review", "READY FOR YOUR REVIEW" in revenue.report(), True)
check("and names who is not signed in", "I'm not signed into Upwork, sir" in revenue.report(),
      True)

print("\nthe client asks")
FakeSession.page_extra[fit["url"]] = "\nClient: did you use AI for this? Also can you pay me via UPI QR code?\n"
tick()
check("asked about AI: answered yes, in the fixed sentence", revenue.AI_LINE in
      FakeSession.messages, True)
check("offered off-platform payment: declined, saying why",
      revenue.OFF_PLATFORM_LINE % "Freelancer.com" in FakeSession.messages, True)
tick()
check("each answered once, never again", len(FakeSession.messages), 2)

print("\nthe checkpoint")
check("'submit it' now means this job", revenue.parse_request("submit it"),
      {"action": "submit", "job": fit["id"], "choices": [fit["id"]]})
st, p = hands.propose("revenue_submit", {"job": fit["id"]}, door="tag")
check("revenue_submit is refused through the tag door", (st, p.get("refused")),
      (403, "wrong-door"))
st, p = hands.propose("revenue_submit", {"job": fit["id"]}, door="revenue")
check("and carded through its own", (st, p.get("ok")), (200, True))
check("the card names the job, the platform and the files",
      "React pricing card component (%s) to the client on Freelancer.com - PricingCard.jsx, "
      "pricing.js" % fit["id"] in p["answer"], True)
hands.clear_pending("test")
check("revenue_start is never offered to the brain", "revenue_start" in json.dumps(
    hands.prompt_parts(), default=str), False)
with open(os.path.join(folder, "pricing.js"), "w", encoding="utf-8") as fh:
    fh.write("const tiers = ['Basic', 'Pro', 'Team'];  // checked by Aditya\nmodule.exports = tiers;\n")
line, ok = revenue.submit(fit["id"], session_factory=FakeSession)
check("submit delivers", (ok, line.startswith("Submitted React pricing card component to the "
                                              "client on Freelancer.com, sir - 2 files")),
      (True, True))
names, note_sent, bodies = FakeSession.deliveries[0]
check("the folder as he left it: his edit, without REVIEW.txt",
      (names, "checked by Aditya" in bodies[1]), (["PricingCard.jsx", "pricing.js"], True))
check("with DELIVERY-NOTE.txt as the message", note_sent.startswith("Hi,"), True)
check("a second submit is refused", revenue.submit(fit["id"], session_factory=FakeSession)[1],
      False)

print("\npaid, and recorded the Ledger's way")
FakeSession.earnings_text = SKELETON
tick()
check("the sample rows did not make it paid", revenue.find_job(fit["id"])["status"], "submitted")
FakeSession.earnings_text = SKELETON + ("\n%s\nMilestone release\n$30.00 USD\nPROJECT NAME\n"
                                        "React pricing card component\nSTATUS\nPAID" %
                                        time.strftime("%m/%d/%Y"))
tick()
fit = revenue.find_job(fit["id"])
check("a row naming the job made it paid", (fit["status"], fit["paid"]["amount"]),
      ("paid", 3000))
check("with the platform's page saved as proof", os.path.isfile(
    os.path.join(TMP, fit["paid"]["proof"])), True)
check("the report says it in one line",
      revenue.report().startswith("Sir, I finished React pricing card component - "), True)
card = revenue.ledger_card()
check("the Ledger's card: an income of $30.00 for freelance, in your business book",
      card["entry"].startswith("An income of $30.00 for freelance, in your business book"), True)
st, p = hands.propose("add_ledger_entry", card, door="ledger")
check("proposed on the ledger door, as the ledger's own hand", (st, p.get("ok")), (200, True))
hands.clear_pending("test")
done = _proc.run([sys.executable, str(HERE / "tools" / "add_ledger_entry.py")],
                 input=json.dumps(card).encode("utf-8"), capture_output=True,
                 env=dict(os.environ))
check("and after a yes, add_ledger_entry.py writes it", done.returncode, 0)
entry = ledger.read_book()[0][0]
check("one entry, with proof, the job's number in its note",
      (entry["amount"], entry["currency"], bool(entry["proof"]), entry["note"].startswith(
          fit["id"] + ":")), (3000, "USD", True, True))
check("recorded(): the Ledger itself is the record", revenue.recorded(fit["id"])["id"],
      entry["id"])
check("so no second card", revenue.ledger_card(), None)

print("\ntaking control back")


def expire_profile():
    """Make the next pass open his profile page first - the step these checks press on."""
    revenue._write_state(lambda st: st["profiles"]["freelancer"].__setitem__("ts", 0))


expire_profile()
FakeSession.abort_at = "profile"
notes = tick()
check("Ctrl+M mid-pass switches Revenue Mode off", (revenue.read_state()["on"], any(
    "Ctrl+M - you took back control while profile" in n for n in notes)), (False, True))
FakeSession.abort_at = None
revenue.switch(True, "test", daily=1)
expire_profile()
FakeSession.challenge = True
notes = tick()
check("a challenge pauses the platform for today, in words",
      (any("asked me to prove I'm a person" in n for n in notes),
       revenue.read_state()["paused"]["freelancer"]["day"] == revenue._today()), (True, True))
FakeSession.challenge = False
check("and the next pass leaves it alone", any("paused for today" in n for n in tick()), True)
MODEL.down = "Rate limit reached on tokens per day (TPD). Please try again in 54s"
revenue.switch(True, "test", daily=1)
st = revenue.read_state()
st["paused"] = {}
with open(os.environ["TRONE_REVENUE_STATE"], "w") as fh:
    json.dump(st, fh)
# A new day for the bids, so the pass looks and asks the model about a job.
with open(os.environ["TRONE_REVENUE_LOG"], encoding="utf-8") as fh:
    log = json.load(fh)
for r in log["entries"]:
    r["at"] = "2000-01-01T00:00:00"
with open(os.environ["TRONE_REVENUE_LOG"], "w", encoding="utf-8") as fh:
    json.dump(log, fh)
notes = tick()
check("Groq down holds the pass for 15 minutes, no fallback", any(
    "not asking for 15 min" in n for n in notes), True)
held = [j for j in revenue.read_book() if j["status"] == "seen"]
check("the job read when the model went down is left undecided", len(held) >= 1, True)
MODEL.down = None
revenue._write_state(lambda st: st.update(on=True))
revenue.tick(session_factory=FakeSession)
check("and is decided on the next pass, not lost",
      [j["status"] for j in revenue.read_book() if j["id"] in {h["id"] for h in held}
       if j["status"] == "seen"], [])
check("and the sign-in check still ran on the platforms after it",
      any(n.startswith("I'm not signed into Upwork, sir") for n in notes)
      and any(n.startswith("I'm not signed into Fiverr, sir") for n in notes), True)
MODEL.down = None

# ------------------------------------------------------------------------------ the real bid form

print("\nthe real bid form, in a real headless Chrome")
FORM = """<!doctype html><html><head><title>React pricing card component | Freelancer</title></head>
<body><main><h1>React pricing card component</h1><p>%s</p>
<h2>Place a bid on this project</h2>
<label for="bidAmountInput">Bid Amount</label><input id="bidAmountInput" type="number" value="140">
<label for="periodInput">This project will be delivered in</label><input id="periodInput" type="number" value="7">
<label for="descriptionTextArea">Describe your proposal (minimum 100 characters)</label>
<textarea id="descriptionTextArea"></textarea>
<h2>Optional Upgrades</h2>
<div><input type="checkbox" id="sp" %s><span>Sponsored $1.90 USD - boost your bid rank</span></div>
<div><input type="checkbox" id="hl"><span>Highlight $0.19 USD - your bid in blue</span></div>
<button id="place">Place Bid</button><div id="out"></div></main>
<script>document.getElementById('place').onclick=function(){var b={a:bidAmountInput.value,d:periodInput.value,t:descriptionTextArea.value};
window.__bid=b;document.getElementById('out').innerHTML='<button>Retract Bid</button><p>Your bid has been placed.</p>';};</script>
</body></html>"""
LOGIN = "<!doctype html><title>Log in to Upwork</title><h1>Log in to Upwork</h1><p>Continue</p>"


class Fixture(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith("/ab/account-security/login"):
            body = LOGIN
        elif self.path.startswith("/profile-upwork"):
            self.send_response(302)
            self.send_header("Location", "/ab/account-security/login?redir=%2Fprofile")
            self.end_headers()
            return
        else:
            body = FORM % ("x " * 400, "checked" if "ticked" in self.path else "")
        data = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a):
        pass


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


chrome = revenue.closer._chrome()
if not chrome:
    print("  SKIP no Chrome on this machine - the real-form checks did not run")
else:
    http_port, cdp_port = free_port(), free_port()
    server = http.server.ThreadingHTTPServer(("127.0.0.1", http_port), Fixture)
    server.handle_error = lambda *a: None      # Chrome hanging up mid-response is not a failure
    threading.Thread(target=server.serve_forever, daemon=True).start()
    profile_dir = tempfile.mkdtemp(prefix="revenue-chrome-")
    proc = _proc.popen([chrome, "--headless=new", "--disable-gpu", "--no-first-run",
                        "--no-default-browser-check", "--user-data-dir=" + profile_dir,
                        "--remote-debugging-port=%d" % cdp_port, "about:blank"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(60):
            if core.get_json("http://127.0.0.1:%d/json/version" % cdp_port):
                break
            time.sleep(0.25)
        base = "http://127.0.0.1:%d" % http_port
        saved = dict(revenue.PLATFORMS["upwork"])
        revenue.PLATFORMS["upwork"]["profile"] = base + "/profile-upwork"
        try:
            with revenue.Session(panic=False, port=cdp_port) as sess:
                sess.profile("upwork")
            got = "no exception"
        except revenue.NotSignedIn as exc:
            got = revenue.signed_out_line(exc.args[0])
        revenue.PLATFORMS["upwork"].update(saved)
        check("a real redirect to Upwork's login is 'I'm not signed into Upwork, sir'",
              got.startswith("I'm not signed into Upwork, sir"), True)
        job = {"url": base + "/projects/react/Pricing-Card", "platform": "freelancer"}
        bid = {"amount": 3000, "days": 2, "letter": good}
        with revenue.Session(panic=False, port=cdp_port) as sess:
            status, line = sess.place_bid("freelancer", job, bid)
            placed = sess.tab.evaluate("window.__bid")
        check("the measured form is filled by label and Place Bid pressed", (status, placed),
              ("bid", {"a": "30", "d": "2", "t": good}))
        check("confirmed by the page's own new words", line, "Retract Bid")
        try:
            with revenue.Session(panic=False, port=cdp_port) as sess:
                sess.place_bid("freelancer", dict(job, url=base + "/projects/react/ticked"), bid)
                pressed = sess.tab.evaluate("window.__bid")
            refused = "no refusal"
        except core.Failed as exc:
            refused, pressed = str(exc), None
        check("a ticked paid upgrade stops the bid before Place Bid",
              (refused.startswith("I did not place the bid - a paid upgrade is ticked"), pressed),
              (True, None))
    finally:
        server.shutdown()
        _proc.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True)
        time.sleep(0.5)
        shutil.rmtree(profile_dir, ignore_errors=True)

hands.LEDGER_PATH = REAL_TOOLS
shutil.rmtree(TMP, ignore_errors=True)
print("\n  %d failed\n" % len(FAILURES))
for f in FAILURES:
    print("    FAILED: %s" % f)
sys.exit(min(len(FAILURES), 120))
