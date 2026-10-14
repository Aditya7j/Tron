"""The Hunter, phase 1: the parts that are pure - no network.

What a sentence becomes (hunter.parse_request) and what must NOT become a hunt; what a page
yields (hunter.read_contacts) and, above all, what it must not - an address the site hid, an
image filename that looks like an email, a number nobody labelled as a phone; one business,
one row (keys, add_lead's merge); the status the Hunter may write, which is "new" and nothing
else; the door, which no tag can open; and the card's own line. The hunt itself was measured
live against the real sources instead - see README "The Hunter" - because a fixture can be
made to say anything about OpenStreetMap.

Run it:  python test_hunter.py
Exit status is the number of failures.
"""
import datetime
import inspect
import json
import os
import pathlib
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
TMP = tempfile.mkdtemp(prefix="hunter-test-")
BOOK = os.path.join(TMP, "leads.json")
os.environ["TRONE_LEADS_PATH"] = BOOK
sys.path.insert(0, str(HERE))

import hands                                                   # noqa: E402
import hunter                                                  # noqa: E402

REAL_TOOLS = hands.LEDGER_PATH
hands.LEDGER_PATH = pathlib.Path(TMP) / "tools-ledger.json"
FAILURES = []


def check(label, got, want):
    ok = got == want
    print("  %s %s" % ("ok  " if ok else "FAIL", label))
    if not ok:
        print("       got  %r\n       want %r" % (got, want))
        FAILURES.append(label)


def parsed(sentence):
    p = hunter.parse_request(sentence)
    return None if p is None else (p["what"], p["where"], p["count"], p["asked"])


print("THE SENTENCE - what becomes a hunt")
check("find me 20 dentists in Pune", parsed("find me 20 dentists in Pune"),
      ("dentists", "Pune", 20, 20))
check("a tail after the town stays part of what",
      parsed("find SaaS startups in Bangalore working on fintech"),
      ("SaaS startups working on fintech", "Bangalore", 10, 10))
check("Hinglish", parsed("Pune mein 15 dentists dhundo"), ("dentists", "Pune", 15, 15))
check("a count in words, a polite opening",
      parsed("could you find twenty CA firms in Ahmedabad?"), ("CA firms", "Ahmedabad", 20, 20))
check("the word leads", parsed("find leads for interior designers in Mumbai"),
      ("interior designers", "Mumbai", 10, 10))
check("over the cap: held to 25, and what was asked is kept",
      parsed("get me 40 marketing agencies in Delhi"), ("marketing agencies", "Delhi", 25, 40))
check("a lower-case town is capitalised", parsed("find 5 dentists in pune")[1], "Pune")

print("THE SENTENCE - what must not")
for s in ("find me the best biryani in Hyderabad", "find me a good dentist in Pune",
          "find flights in Delhi", "find me jobs in Bangalore", "what are dentists in Pune",
          "find the time in Tokyo", "search for python tutorials on youtube",
          "find me the best dentists in Pune", "find a flat in Koramangala",
          "get the weather in Mumbai", "find news in Pune", "remind me to call dentists in Pune"):
    check("not a hunt: %s" % s, hunter.parse_request(s), None)

print("THE CARD'S LINE")
check("{plan}", hunter.describe({"what": "dentists", "where": "Pune", "count": 20}),
      "20 dentists in Pune")
check("{plan} says the cap out loud",
      hunter.describe({"what": "agencies", "where": "Delhi", "count": 25, "asked": 40}),
      "25 agencies in Delhi (you asked for 40; 25 is the most one hunt chases)")
check("hands.readings fills {plan} from hunter.describe",
      hands.readings({"what": "dentists", "where": "Pune", "count": 5}).get("plan"),
      "5 dentists in Pune")

print("TOPICS - what a company must answer to")
saas_fintech = hunter.topics("B2B SaaS startups working on fintech")
check("saas is soft, fintech is hard", [soft for _p, soft in saas_fintech], [True, False])
check("a fintech company with no SaaS recorded still matches",
      hunter.matches("Groww | fintech | financial services", saas_fintech), 1)
check("a software company that is not fintech does not",
      hunter.matches("Hasura | software industry", saas_fintech), None)
check("a public-sector bank is not fintech",
      hunter.matches("Canara Bank | financial sector | banking | financial services",
                     hunter.topics("fintech companies")), None)
check("soft words alone still filter",
      hunter.matches("Canara Bank | banking", hunter.topics("SaaS companies")), None)
check("no topic at all takes everything", hunter.matches("anything", hunter.topics("companies")), 0)

print("WHAT IS A BUSINESS'S OWN SITE")
check("a bare domain gets a scheme", hunter.own_site("dixitdentalcare.com"),
      "http://dixitdentalcare.com")
check("facebook is not a website", hunter.own_site("https://facebook.com/someclinic"), None)
check("a directory's page about it is not its site", hunter.own_site(
    "https://www.apneareamein.com/Magarpattacity-Pune/Doctor - Dentist in Magarpatta City.php"),
    None)
check("practo is not its site", hunter.own_site("https://www.practo.com/pune/doctor/x"), None)
check("one segment down is still its own", hunter.own_site("https://example.in/clinic"),
      "https://example.in/clinic")
check("two sites.google.com sites are two keys",
      hunter.site_key("https://sites.google.com/view/a-clinic") !=
      hunter.site_key("https://sites.google.com/view/b-clinic"), True)

print("WHAT A PAGE YIELDS - and what it must not")
PAGE = """<html><head><title>Smile Dental</title><style>.x{color:#fff}</style>
<script>var e = "tracker@sentry.io"; var t = "tel:9999999999";</script></head><body>
<a href="mailto:Hello@SmileDental.in?subject=hi">Write to us</a>
<a href="tel:+91-98765-43210">Call</a>
<a href="/contact-us/">Contact</a>
<p>Our logo: logo@2x.png and sprite@3x.webp</p>
<p>Registration no. 27AAACB1234C1Z5, order 9123456789 shipped.</p>
<p>Phone: 020 2612 3456</p>
<a href="/cdn-cgi/l/email-protection" class="__cf_email__" data-cfemail="0f6a776e">[email protected]</a>
</body></html>"""
got = hunter.read_contacts(PAGE, "https://smiledental.in/")
check("mailto is read, lower-cased", got["emails"], ["hello@smiledental.in"])
check("tel: first, then the labelled one; the unlabelled order number is not a phone",
      got["phones"], ["+919876543210", "02026123456"])
check("the contact page is found and made absolute", got["contact"],
      "https://smiledental.in/contact-us/")
check("Cloudflare's hidden address is noticed and NOT decoded", got["hidden"], True)
check("nothing from inside <script>", "tracker@sentry.io" in got["emails"], False)
BARE = "<html><body><h1>Welcome</h1><p>We are open Monday to Saturday.</p></body></html>"
check("a page with nothing on it yields nothing - nothing is composed",
      {k: v for k, v in hunter.read_contacts(BARE, "https://x.in/").items() if k != "title"},
      {"emails": [], "phones": [], "contact": None, "hidden": False})
SAME = '<a href="#contact">Contact</a><a href="https://x.in/">Contact us</a>'
check("#contact on the same page is not a contact page",
      hunter.read_contacts(SAME, "https://x.in/")["contact"], None)
check("the site's own domain is preferred",
      hunter._pick_email(["owner@gmail.com", "info@x.in"], "https://www.x.in/"), "info@x.in")
check("webmail is taken when it is all there is",
      hunter._pick_email(["owner@gmail.com"], "https://www.x.in/"), "owner@gmail.com")

print("REFUSALS ARE NOTICED")
check("429", hunter._refusal(429, ""), "HTTP 429")
check("a 200 that is a challenge", hunter._refusal(200, "<title>Just a moment...</title>"),
      "a challenge page")
check("an ordinary page", hunter._refusal(200, "<html>dentist</html>"), "")
EMPTY = {"what": "dentists", "where": "Pune", "count": 5, "added": [], "merged": 0, "known": 0,
         "no_contact": 0, "unreadable": 0, "candidates": 0, "web_found": 0, "stopped": False,
         "from": {"openstreetmap": 0, "wikidata": 0}}
refused_line = hunter.report(dict(EMPTY, refused={"openstreetmap": "HTTP 429",
                                                  "wikidata": "HTTP 403"},
                                  notes=["OpenStreetMap started refusing (HTTP 429), so I "
                                         "stopped asking it", "Wikidata refused (HTTP 403)"]))
check("a refusal is never reported as an empty listing",
      ("lists any" in refused_line, refused_line.startswith(
          "I could not look for dentists in Pune, sir - both listings refused me")),
      (False, True))
check("and the line names who refused and how", "HTTP 429" in refused_line, True)
check("an honest empty listing is still said as one",
      hunter.report(dict(EMPTY, refused={}, notes=[])).startswith(
          "Neither OpenStreetMap nor Wikidata lists any dentists in Pune"), True)

print("ONE BUSINESS, ONE ROW")
now = datetime.datetime(2026, 10, 14, 12, 0)
a = {"name": "Smile Dental", "website": "https://www.smiledental.in/", "phone": "+91 98765 43210",
     "via": ["openstreetmap"], "ref": "osm:node/1"}
outcome, row = hunter.add_lead(a, "dentists", "Pune", now=now)
check("first find is added as H-0001, status new", (outcome, row["id"], row["status"]),
      ("added", "H-0001", "new"))
again = {"name": "Smile Dental Clinic", "website": "http://smiledental.in", "email": "hi@smiledental.in",
         "emailFrom": "http://smiledental.in", "via": ["wikidata", "website"], "ref": "wikidata:Q1"}
outcome, row = hunter.add_lead(again, "dentists", "Pune",
                               now=now + datetime.timedelta(days=3))
check("same website, other spelling: merged, not a second row", (outcome, row["id"]),
      ("merged", "H-0001"))
check("the merge filled the blank email and kept the first name",
      (row["email"], row["name"]), ("hi@smiledental.in", "Smile Dental"))
check("sources are united", (row["source"], row["via"]),
      ("listings+web", ["openstreetmap", "website", "wikidata"]))
check("lastSeen moves, foundAt does not", (row["foundAt"], row["lastSeen"]),
      ("2026-10-14", "2026-10-17"))
by_phone = {"name": "Totally Different Name", "phone": "098765 43210", "via": ["openstreetmap"]}
check("same phone, different formatting: the same business",
      hunter.add_lead(by_phone, "dentists", "Pune", now=now)[0], "merged")
# The Closer, later, moves a status; a re-find must never move it back.
rows = json.load(open(BOOK, encoding="utf-8"))
rows["leads"][0]["status"] = "contacted"
json.dump(rows, open(BOOK, "w", encoding="utf-8"))
hunter.add_lead(a, "dentists", "Pune", now=now)
check("a re-find never touches a status the Closer set",
      hunter.read_book()[0][0]["status"], "contacted")
other = {"name": "Bright Smiles", "phone": "+91 91111 22222", "via": ["openstreetmap"]}
check("a different business is H-0002", hunter.add_lead(other, "dentists", "Pune", now=now)[1]["id"],
      "H-0002")
check("known() finds a business before its site is read",
      (hunter.known({"name": "x", "website": "https://smiledental.in/about"}, "Pune") or {}).get("id"),
      "H-0001")
check("add_lead takes no status - the Hunter can only ever write 'new'",
      "status" in inspect.signature(hunter.add_lead).parameters, False)
check("one book, two rows", len(hunter.read_book()[0]), 2)

print("THE HAND REFUSES A BAD CARD")
env = dict(os.environ, TRONE_LEADS_PATH=BOOK)
env.pop("PYTHONIOENCODING", None)      # a suite run with it set hides a hand's stdin bug
for card, label in (({"what": "dentists", "where": "Pune", "count": 0}, "count 0"),
                    ({"what": "dentists", "where": "Pune", "count": 99}, "count over the cap"),
                    ({"what": "", "where": "Pune", "count": 5}, "no what"),
                    ("not json", "not JSON")):
    body = card if isinstance(card, str) else json.dumps(card)
    done = subprocess.run([sys.executable, str(HERE / "tools" / "hunt_leads.py")], input=body,
                          capture_output=True, text=True, encoding="utf-8", timeout=30, env=env)
    check("refused, exit 1, nothing looked for: %s" % label,
          (done.returncode, "nothing was looked for" in done.stdout), (1, True))

print("THE DOOR")
tool = hands.find("hunt_leads")
check("registered, door-bound to hunt", tool and tool["doors"], ("hunt",))
check("never described to the brain",
      "hunt_leads" in json.dumps(hands.prompt_parts(), default=str), False)
st, p = hands.propose("hunt_leads", {"what": "dentists", "where": "Pune", "count": 5}, door="tag")
check("a tag cannot raise it", (st, p.get("refused"), hands.pending_public()),
      (403, "wrong-door", None))
st, p = hands.propose("hunt_leads", {"what": "dentists", "where": "Pune", "count": 20},
                      door="hunt")
check("through its own door the card speaks the plan", (st, p["pending"]["line"]),
      (200, "I'll hunt for 20 dentists in Pune in open listings and on their own websites, sir, "
            "and keep only those with public contact details. Nothing is sent to anyone. "
            "Shall I?"))
hands.clear_pending("test")

hands.LEDGER_PATH = REAL_TOOLS
print("\n%d failure(s)" % len(FAILURES))
sys.exit(len(FAILURES))
