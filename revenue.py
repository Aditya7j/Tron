"""REVENUE MODE, phase 1. Finds small freelance jobs on Upwork, Fiverr and Freelancer.com, bids on
the ones the employer can genuinely do, does the work once a bid is accepted, and STOPS at "ready
for your review". Nothing goes to a client until the employer says "submit it" and then yes on the
card. It is Operator doing a longer job: every page is opened, read, typed into and pressed through
tools/operator_core.py - the same finder, executor, reader and Ctrl+M - and nothing here is a
browser layer of its own.

WHERE IT KEEPS THINGS (all gitignored: other people's job posts and the employer's client work)
    revenue-book.json   THE JOB BOOK. One row per job read: R-0001, platform, url, title, budget,
                        status, why, the bid as placed, the work's files and their sha256, the
                        submission and the payment as the platform showed it.
    revenue-log.json    THE AUDIT LOG. Every bid, message, delivery and payment read - what, to
                        whom, when and why. Written BEFORE a press, marked after; never retried.
    revenue-state.json  THE SWITCH, the day's caps, each platform's last session check and the
                        employer's own profile as each platform shows it.
    revenue-work/R-0001/  the work, a DELIVERY-NOTE.txt the employer may edit, and REVIEW.txt.
    proofs/revenue-R-0001-<day>.png   the platform's own payment page, for the Ledger card.

THE LOOP, and the one place it stops
    1. BROWSE AND BID, on its own. Each platform's search is read in a background tab; each new
       job is read in full and passes the FIT GATE (below) or is skipped with its reason. At most
       dailyBidLimit bids a day across all three, at least minGapMinutes apart, one per pass.
    2. DO THE WORK, on its own, once the platform shows the bid was awarded: code (compiled or
       node --check'd), writing, or a web page (rendered to PNG by headless Chrome, as the
       Closer's demos are). Groq through the server's client, never the local fallback.
    3. READY FOR REVIEW - AND STOP. The work sits in revenue-work/R-xxxx/ until the employer says
       "submit it" (or "send it", "submit R-0003") and yes on the revenue_submit card. That card
       is the one checkpoint, and it is a hand like every other: tools/revenue_submit.py.
    4. HONESTY IF ASKED. A client who asks whether AI was involved is told yes, in a fixed sentence
       (AI_LINE), not a model's. It is never volunteered, and never denied.
    5. REPORT AND RECORD. "revenue update" reads the book. A job the platform has paid is reported
       in one line ("Sir, I finished <title> - 3 hours, $25.") and its earning is put up as the
       LEDGER'S OWN CARD (add_ledger_entry on the ledger door), with the platform's page as proof
       - the one way anything financial reaches ledger.json. Revenue Mode never writes the book.

THE FIT GATE, enforced in code rather than asked of a model
    - THE EMPLOYER'S OWN WORDS ARE THE ONLY FACTS. His profile as each platform shows it (read
      live, once a day) plus config.json "revenue.profile" if he wrote one. A skill not in them
      is a skill he does not have. Every bid passes vet_bid() - no certification, review, award,
      "years of experience", guarantee, link or number that is not in his facts or the job - and
      then a second model reads it against the same facts.
    - SMALL AND ONE SCOPE. Fixed price only; the model's estimate must be 1..maxHours (4) and one
      deliverable set; "ongoing", "long-term", "full-time", "multiple phases" are refused by rule.
    - HIS RATE, HIS CURRENCY. The bid is hours x his own hourly rate (read off his profile), never
      below the client's minimum and never above the client's maximum - a job whose budget cannot
      carry his rate is skipped, and a budget in a currency he has no rate for is skipped rather
      than converted at a rate this file would have to invent.
    - ON THE PLATFORM, ALWAYS. A job post or a client message that asks for WhatsApp, Telegram,
      email, a QR code, UPI or "payment outside" is refused by rule; a client message that offers
      it is declined in a fixed sentence (OFF_PLATFORM_LINE) saying why.
    - NO PAID EXTRAS. A bid form's sponsored / highlight / featured upgrades are never ticked, and
      a bid whose form shows one ticked is not placed.

PACING IS A CAP, NOT A DISGUISE. A few bids a day, a fixed gap between them, one pass every
tickSeconds. Nothing here randomises timing, masks the browser or solves a challenge: a CAPTCHA,
"verify you are human" or "unusual activity" page stops that platform for the day and is reported.

NOT SIGNED IN IS A SENTENCE. Each pass first opens the platform's own profile page. A redirect to a
login page (measured 2026-10-15: Upwork -> /ab/account-security/login, Fiverr -> /login?return=)
is "I'm not signed into Upwork, sir", in the report and in the pass's notes - never a crash, never
a pass that looks like it worked.

CTRL+M, Operator's panic key, is armed for the length of every browser session. Pressed, it stops
the session at the step it was on AND switches Revenue Mode off - "takes control back".

    python revenue.py                 the switch, each platform's last check, the book's statuses
    python revenue.py report          the report, exactly as it is spoken
    python revenue.py log [N]         the last N audit rows
    python revenue.py tick            one pass now, on this thread, with the server's Groq
"""

import base64
import datetime
import hashlib
import html
import json
import os
import re
import sys
import threading
import time
import urllib.parse

import closer
import hunter
import ledger
from tools import operator_core as core

HERE = os.path.dirname(os.path.abspath(__file__))
BOOK_PATH = os.environ.get("TRONE_REVENUE_BOOK") or os.path.join(HERE, "revenue-book.json")
LOG_PATH = os.environ.get("TRONE_REVENUE_LOG") or os.path.join(HERE, "revenue-log.json")
STATE_PATH = os.environ.get("TRONE_REVENUE_STATE") or os.path.join(HERE, "revenue-state.json")
WORK_DIR = os.environ.get("TRONE_REVENUE_WORK") or os.path.join(HERE, "revenue-work")
CONFIG_PATH = os.environ.get("TRONE_REVENUE_CONFIG") or os.path.join(HERE, "config.json")

DEFAULT_DAILY, HARD_DAILY_MAX = 2, 5           # bids a day, all platforms together
DEFAULT_GAP_MIN = 45                           # minutes between two bids
DEFAULT_MAX_HOURS, HARD_MAX_HOURS = 4, 4       # phase 1: a job of a few hours, one scope
DEFAULT_DAYS = 2                               # "delivered in" - room for the review checkpoint
DEFAULT_TICK_S = 600
POLL_S = 5.0
JOBS_READ_PER_PASS = 4                         # new job pages opened per pass
SESSION_S = 420.0                              # one browser session's budget
DRAFT_ATTEMPTS = 3
PROFILE_MAX_AGE_S = 24 * 3600
PANIC_ID = 0x0B1D                              # Operator's hands use 0x0B1A..0x0B1C
WORK_KINDS = ("code", "writing", "webpage")

STATUSES = ("skipped", "bid", "bid-failed", "bid-unconfirmed", "awarded", "needs-input",
            "ready", "submitted", "submit-unconfirmed", "paid", "work-failed")
SAY_STATUS = {"bid": "bid placed, waiting on the client", "awarded": "awarded - working on it",
              "needs-input": "awarded, but the client has to send something first",
              "ready": "READY FOR YOUR REVIEW", "submitted": "submitted, waiting for payment",
              "submit-unconfirmed": "submitted, but the platform did not confirm it - check it",
              "bid-unconfirmed": "bid pressed, but the platform did not confirm it - check it",
              "paid": "paid", "work-failed": "awarded, but the work failed its checks"}

_lock = threading.Lock()
_chat = None
_work_chat = None
_config = None


def configure(chat=None, work_chat=None, config=None):
    """The server lends its Groq client (twice: the short ceiling for bids and checks, a longer
    one for the work itself) and its config reader. Never the local fallback."""
    global _chat, _work_chat, _config
    if chat is not None:
        _chat = chat
    if work_chat is not None:
        _work_chat = work_chat
    if config is not None:
        _config = config


def _now():
    return datetime.datetime.now()


def _today():
    return _now().date().isoformat()


def _stamp():
    return _now().isoformat(timespec="seconds")


_clip = closer._clip


# ------------------------------------------------------------------------------ the platforms

# WHAT A PLATFORM LAYER MAY HOLD: addresses, what a job link looks like, the NAMES a person reads on
# the bid form and its buttons, and the words the platform uses to confirm. Data only, as in
# operator_browser.SITES - every find and press is operator_core's and knows no site.
#   measured   read off the live site from the DevTools Chrome on 2026-10-15
#   unmeasured the platform's documented shape; the finder fails closed on it (a miss is a stop
#              with a sentence, never a guess), and the first live pass says which it is
PLATFORMS = {
    "freelancer": {
        "name": "Freelancer.com",
        # measured: /me lands on the signed-in user's own profile, "(n) Aditya Profile".
        "profile": "https://www.freelancer.com/me",
        # measured: results are <a href="/projects/<category>/<slug>"> whose text is the whole card
        # - title, "Budget $30 - 250 USD", "222 bids", the opening of the description.
        "search": "https://www.freelancer.com/search/projects?q={q}&types=fixed",
        "job_href": r"^/projects/[a-z0-9-]+/[^/?#]+$",
        # measured: the post, its skills and its id come first; then the bid form, OTHER
        # BIDDERS' questions and the messages sidebar - none of which is the client's post, and
        # the sidebar's "membership" chatter is not a red flag of this job's.
        "job_end": r"\n(?:Place a bid on this project|Clarification Board|About the Client)\n",
        # measured: three labelled fields and one button, "Place Bid".
        "fields": {"amount": '"Bid Amount"', "days": '"This project will be delivered in"',
                   "letter": '"Describe your proposal"'},
        "bid_button": "place bid",
        "bid_done": (r"\bretract bid\b", r"\bedit bid\b", r"\byour bid\b.{0,60}\b(placed|"
                     r"submitted|successful)", r"\bbid (placed|submitted)\b"),
        "letter_min": 100,
        "award": (r"\byou have been awarded\b", r"\baccept (the )?project\b",
                  r"\bawarded (to )?you\b"),
        "accept_button": "accept",
        # measured: Transaction History. ON AN EMPTY ACCOUNT IT SHOWS SAMPLE ROWS THAT NEVER GO
        # AWAY - "Random Stuff", "$56004.44 USD", "David Wang", 2019, STATUS PAID. Read for 35 s,
        # they stayed. A payment is therefore only ever a row naming the job's exact title, dated
        # on or after the submission, and not one of these.
        "earnings": "https://www.freelancer.com/payments/transactions",
        "placeholders": ("random stuff", "david wang", "3245-2653-1539-afvs", "56004.44"),
        "deliver_button": "send",
        "deliver_done": (r"\bsent\b", r"\bdelivered\b"),
    },
    "upwork": {
        "name": "Upwork",
        # measured signed out: -> /ab/account-security/login?redir=..., "Log in to Upwork".
        "profile": "https://www.upwork.com/freelancers/settings/profile",
        "search": "https://www.upwork.com/nx/search/jobs/?q={q}&t=1&sort=recency",   # t=1 fixed
        "job_href": r"^/(?:jobs|freelance-jobs/apply)/[^?#]*~[0-9a-f]+",
        "apply_button": "apply now",
        "fields": {"amount": '"Bid"', "letter": '"Cover Letter"'},
        "bid_button": "submit a proposal",
        "bid_done": (r"\bproposal (was )?submitted\b", r"\byour proposal\b.{0,40}\bsubmitted\b",
                     r"\bview proposal\b"),
        "letter_min": 50,
        "award": (r"\boffer\b.{0,40}\bfrom\b", r"\baccept offer\b"),
        "accept_button": "accept offer",
        "earnings": "https://www.upwork.com/nx/payments/reports/transaction-history",
        "placeholders": (),
        "deliver_button": "submit work",
        "deliver_done": (r"\bwork (was )?submitted\b", r"\bsubmitted for (payment|review)\b"),
    },
    "fiverr": {
        "name": "Fiverr",
        # measured signed out: -> /login?return=seller_dashboard_short_url, "Sign in to your
        # account". Fiverr has no open job board for sellers: its buyers' requests are BRIEFS
        # matched to a seller, answered with an offer - so its "search" is the briefs page.
        "profile": "https://www.fiverr.com/seller_dashboard",
        "search": "https://www.fiverr.com/briefs/seller",
        "job_href": r"^/briefs/[^?#]+",
        "apply_button": "send offer",
        "fields": {"amount": '"Price"', "days": '"Delivery"', "letter": '"Description"'},
        "bid_button": "send offer",
        "bid_done": (r"\boffer (was )?sent\b", r"\byour offer\b"),
        "letter_min": 50,
        "award": (r"\bnew order\b", r"\border (has )?started\b"),
        "accept_button": "",
        "earnings": "https://www.fiverr.com/earnings",
        "placeholders": (),
        "deliver_button": "deliver now",
        "deliver_done": (r"\bdelivered\b", r"\bdelivery (was )?sent\b"),
    },
}

# NOT SIGNED IN, generically: a login address, or the page saying so in its first lines.
_LOGIN_URL = re.compile(r"/(?:ab/account-security/)?(?:log-?in|sign-?in|sign-?up|auth)\b", re.I)
_LOGIN_TEXT = re.compile(r"\b(?:log ?in|sign ?in) to (?:upwork|fiverr|freelancer|your account)\b|"
                         r"\bwelcome back\b.{0,40}\b(?:log|sign) ?in\b", re.I)
# A CHALLENGE: the platform asking whether this is a person. Never solved here.
_CHALLENGE = re.compile(r"\bverify (?:that )?you(?:'re| are) (?:a )?human\b|\bare you a robot\b|"
                        r"\bcaptcha\b|\bunusual (?:traffic|activity)\b|\bpress (?:and|&) hold\b|"
                        r"\bchecking your browser\b|\bjust a moment\b|\battention required\b|"
                        r"\baccess (?:to this page has been )?denied\b|\bsecurity check\b", re.I)


class NotSignedIn(Exception):
    """The platform asked for a login. Carries the platform's key."""


class Challenge(Exception):
    """The platform asked whether this is a person. Carries the platform's key."""


def signed_out_line(key):
    return "I'm not signed into %s, sir - sign in to it in the DevTools Chrome and I'll pick it " \
           "up on the next pass." % PLATFORMS[key]["name"]


def challenge_line(key):
    return ("%s asked me to prove I'm a person, sir, so I stopped there for today - I don't "
            "answer those. It's open in the DevTools Chrome if you want to look." % (
                PLATFORMS[key]["name"]))


# ------------------------------------------------------------------------------ settings

def _read_config():
    if _config is not None:
        try:
            return _config() or {}
        except Exception:                                      # noqa: BLE001
            return {}
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def _int(value, lo, hi, default):
    return value if type(value) is int and lo <= value <= hi else default


def settings(cfg=None):
    """(settings, problems) from config.json's optional "revenue" block. Every field has a
    default: Revenue Mode's facts come from the employer's own platform profiles, so it needs no
    sheet to start - only something to search for."""
    block = (cfg if cfg is not None else _read_config()).get("revenue") or {}
    plats = [p for p in (block.get("platforms") or list(PLATFORMS)) if p in PLATFORMS]
    profile = block.get("profile") if isinstance(block.get("profile"), dict) else {}
    rates = {str(k).upper(): v for k, v in (block.get("hourlyRate") or {}).items()
             if str(k).upper() in ledger.CURRENCIES and type(v) is int and 0 < v <= 1000} \
        if isinstance(block.get("hourlyRate"), dict) else {}
    s = {"platforms": plats,
         "searches": [_clip(q, 60) for q in (block.get("searches") or
                                             ["react", "javascript", "html css"]) if str(q).strip()][:8],
         "daily": _int(block.get("dailyBidLimit"), 1, HARD_DAILY_MAX, DEFAULT_DAILY),
         "gapMin": _int(block.get("minGapMinutes"), 10, 1440, DEFAULT_GAP_MIN),
         "maxHours": _int(block.get("maxHours"), 1, HARD_MAX_HOURS, DEFAULT_MAX_HOURS),
         "days": _int(block.get("deliveryDays"), 1, 14, DEFAULT_DAYS),
         "tickSeconds": _int(block.get("tickSeconds"), 120, 7200, DEFAULT_TICK_S),
         "rates": rates,
         "skills": [_clip(x, 40) for x in (profile.get("skills") or []) if str(x).strip()][:40],
         "about": _clip(profile.get("about"), 1500),
         "name": _clip(profile.get("name"), 60)}
    problems = []
    if not plats:
        problems.append("revenue.platforms in config.json names none of upwork, fiverr, "
                        "freelancer")
    if not s["searches"]:
        problems.append("revenue.searches in config.json is empty, so I have nothing to look for")
    return s, problems


# ------------------------------------------------------------------------------ the three files

def _read_json(path, key):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except FileNotFoundError:
        return []
    except (OSError, ValueError):
        raise OSError("%s cannot be read, and I will not act on what I cannot write down"
                      % os.path.basename(path))
    rows = data.get(key) if isinstance(data, dict) else None
    return rows if isinstance(rows, list) else []


def _write_json(path, key, rows, note):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump({"version": 1, key: rows, "updated": _stamp(), "note": note}, fh, indent=1,
                  ensure_ascii=False)
        fh.write("\n")
    os.replace(tmp, path)


def read_state():
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {"on": False}
    except (OSError, ValueError):
        return {"on": False}


def _write_state(change):
    with _lock, hunter.file_lock(STATE_PATH):
        state = read_state()
        change(state)
        tmp = STATE_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(state, fh, indent=1, ensure_ascii=False)
        os.replace(tmp, STATE_PATH)
        return state


def switch(on, by, daily=None):
    """On is tools/revenue_start.py, after a card; off is immediate and needs none."""
    def change(state):
        state.update(on=bool(on), since=_stamp(), by=str(by)[:20])
        if daily is not None:
            state["daily"] = max(1, min(HARD_DAILY_MAX, int(daily)))
    return _write_state(change)


def note_platform(key, ok, line=""):
    def change(state):
        state.setdefault("platforms", {})[key] = {"ok": bool(ok), "line": line, "at": _stamp()}
    _write_state(change)


def read_log():
    return _read_json(LOG_PATH, "entries")


def log_event(entry):
    with _lock, hunter.file_lock(LOG_PATH):
        rows = read_log()
        n = max((int(r["id"][2:]) for r in rows if re.fullmatch(r"V-\d+", str(r.get("id")))),
                default=0) + 1
        row = dict({"id": "V-%04d" % n, "at": _stamp()}, **entry)
        _write_json(LOG_PATH, "entries", rows + [row],
                    "Every bid, message, delivery and payment Revenue Mode pressed or read. A row "
                    "still 'pressing' is one whose outcome was never written: check the platform.")
        return dict(row)


def update_event(entry_id, **fields):
    with _lock, hunter.file_lock(LOG_PATH):
        rows = read_log()
        for r in rows:
            if r.get("id") == entry_id:
                r.update(fields)
                _write_json(LOG_PATH, "entries", rows, "")
                return dict(r)
    return None


def read_book():
    return _read_json(BOOK_PATH, "jobs")


def _norm_url(url):
    parts = urllib.parse.urlsplit(str(url or ""))
    path = re.sub(r"/(?:details|proposals)/?$", "", parts.path.rstrip("/"))
    return "%s://%s%s" % (parts.scheme or "https", (parts.hostname or "").lower(), path)


def add_job(platform, url, title, **fields):
    """The job's row, new or already there - a job is read once, whatever finds it again."""
    with _lock, hunter.file_lock(BOOK_PATH):
        rows = read_book()
        key = _norm_url(url)
        hit = next((r for r in rows if _norm_url(r.get("url")) == key), None)
        if hit:
            return dict(hit), False
        n = max((int(r["id"][2:]) for r in rows if re.fullmatch(r"R-\d+", str(r.get("id")))),
                default=0) + 1
        row = dict({"id": "R-%04d" % n, "platform": platform, "url": key,
                    "title": _clip(title, 200), "seenAt": _stamp(), "status": "seen"}, **fields)
        _write_json(BOOK_PATH, "jobs", rows + [row],
                    "Every job Revenue Mode read, and what became of it.")
        return dict(row), True


def update_job(job_id, status=None, **fields):
    with _lock, hunter.file_lock(BOOK_PATH):
        rows = read_book()
        for r in rows:
            if r.get("id") == job_id:
                r.update(fields)
                if status:
                    r["status"] = status
                    r["statusAt"] = _stamp()
                _write_json(BOOK_PATH, "jobs", rows, "")
                return dict(r)
    return None


def find_job(job_id):
    return next((r for r in read_book() if r.get("id") == job_id), None)


def known_urls():
    """Every job already decided. A row still "seen" was read and never decided - measured live,
    Groq's daily limit landed mid-fit-check - so it is looked at again, not lost."""
    return {_norm_url(r.get("url")) for r in read_book() if r.get("status") != "seen"}


# ------------------------------------------------------------------------------ his facts

# The skills a profile may name, matched as whole words in HIS text. A skill is his when his own
# profile says it; this list only decides what counts as a skill-word, never whether he has it.
SKILL_WORDS = ("HTML5", "HTML", "CSS3", "CSS", "JavaScript", "TypeScript", "React.js", "React",
               "Redux", "SASS", "SCSS", "Tailwind", "Bootstrap", "jQuery", "Next.js", "Vue.js",
               "Angular", "Node.js", "Express", "Python", "Django", "Flask", "PHP", "Laravel",
               "WordPress", "Shopify", "MySQL", "PostgreSQL", "MongoDB", "Firebase", "Figma",
               "Photoshop", "Excel", "Java", "C#", "Docker", "AWS", "GraphQL",
               "copywriting", "content writing", "proofreading", "data entry")


def skills_in(text):
    found = []
    for word in SKILL_WORDS:
        if re.search(r"(?<![\w.])%s(?![\w])" % re.escape(word), str(text or ""), re.I):
            if not any(word.lower() in f.lower() for f in found):
                found.append(word)
    return found


# THE PLATFORM'S OWN WORDS AROUND HIS, cut before his profile is used as facts. Measured on his
# Freelancer profile: "No portfolio items have been added yet", "Add certification", "No reviews
# to see here", "Great reviews help you win more bids" - the page's furniture, which would
# otherwise make "portfolio", "certification" and "reviews" words his facts contain.
_FURNITURE = re.compile(r"^(?:upload cover photo|view client profile|general|add profile|edit "
                        r"profile|verifications|manage portfolio|add first item|browse projects|"
                        r"request (?:a )?reference|add (?:experience|education|qualification|"
                        r"publication|certification|article)|request reference|messages|"
                        r"(?:no|great) .*|showcase your best work.*|.*have been added\.?|"
                        r"[\d.%]+|portfolio|experience|education|qualifications|publications|"
                        r"certifications|articles|references)$", re.I)


def profile_facts(page_text):
    """His profile page's text without the platform's own furniture."""
    lines = [ln.strip() for ln in str(page_text or "").splitlines()]
    return "\n".join(ln for ln in lines if ln and not _FURNITURE.match(ln))[:5000]


def rate_in(text):
    """{currency: whole units an hour} read off his profile ("$10 USD / Hour")."""
    out = {}
    for m in re.finditer(r"([$\u20b9])\s?([\d,]+)(?:\.\d+)?\s*(USD|INR)?\s*/\s*(?:hour|hr)\b",
                         str(text or ""), re.I):
        cur = (m.group(3) or ("USD" if m.group(1) == "$" else "INR")).upper()
        out.setdefault(cur, int(m.group(2).replace(",", "")))
    return out


def facts_for(key, s=None, state=None):
    """(facts text, skills, rates, name) - everything a bid on `key` may rest on - or (None, ...)
    when his profile on that platform has not been read."""
    s = s or settings()[0]
    prof = ((state or read_state()).get("profiles") or {}).get(key) or {}
    text = prof.get("text") or ""
    if not text and not s["about"]:
        return None, [], {}, ""
    own = "\n".join(x for x in (s["about"], text) if x)
    skills = list(dict.fromkeys(s["skills"] + skills_in(own)))
    rates = dict(rate_in(text), **s["rates"])
    name = s["name"] or prof.get("name") or ""
    out = ["THE FREELANCER: %s" % (name or "the account holder")]
    out.append("SKILLS: %s" % (", ".join(skills) or "none stated"))
    out.append("HIS OWN PROFILE, AS %s SHOWS IT:\n%s" % (PLATFORMS[key]["name"].upper(), own))
    return "\n\n".join(out), skills, rates, name


# ------------------------------------------------------------------------------ a job, read

_BUDGET = re.compile(r"(?P<sym>[$\u20b9\u00a3\u20ac])?\s?(?P<lo>[\d,]+(?:\.\d+)?)\s*(?:[\u2013-]|to)\s*"
                     r"(?P<hi>[\d,]+(?:\.\d+)?)\s*(?P<cur>USD|INR|GBP|EUR|CAD|AUD|SGD|NZD|HKD)"
                     r"(?P<per>\s*(?:/|per)\s*(?:hour|hr))?", re.I)


def _units(text):
    whole, _dot, frac = str(text).replace(",", "").partition(".")
    return int(whole or 0) * 100 + int((frac + "00")[:2] or 0)


def budget_in(text):
    """{currency, lo, hi (in minor units), hourly} for the first budget the text states, or None."""
    m = _BUDGET.search(str(text or ""))
    if not m:
        return None
    return {"currency": m.group("cur").upper(), "lo": _units(m.group("lo")),
            "hi": _units(m.group("hi")), "hourly": bool(m.group("per"))}


def required_skills(text):
    """The "Skills Required" list a job page prints, one per line, up to the next section."""
    m = re.search(r"\bSkills? Required\b\s*\n(.*?)(?:\n(?:Project ID|About the Client|Report "
                  r"Project|Place a bid)\b|\Z)", str(text or ""), re.S | re.I)
    if not m:
        return []
    return [ln.strip() for ln in m.group(1).splitlines() if 0 < len(ln.strip()) <= 40][:15]


_LONG = re.compile(r"\b(?:long[- ]term|ongoing|full[- ]time|part[- ]time|retainer|monthly|per month|"
                   r"multiple (?:phases|milestones|projects|websites|apps)|several (?:weeks|months)|"
                   r"\d+\s*(?:-|to)\s*\d+\s*(?:weeks|months)|(?:weeks|months) of work|"
                   r"partner(?:ship)?|co-?founder|equity|maintain(?:ing)? (?:it|the site) going "
                   r"forward)\b", re.I)
_OFF_PLATFORM = re.compile(r"\b(?:whats\s?app|telegram|skype|signal app|wechat|discord|"
                           r"e-?mail me|contact me (?:at|on|via)|call me (?:at|on)|my (?:number|"
                           r"phone|email) is|gmail\.com|outlook\.com|qr\s?code|upi|paytm|google ?pay|"
                           r"phone ?pe|paypal|bank transfer|wire transfer|western union|crypto|"
                           r"usdt|outside (?:of )?(?:upwork|fiverr|freelancer|the platform|this "
                           r"site)|off[- ]platform|pay (?:you )?directly|direct payment)\b|"
                           r"\+?\d[\d -]{9,}\d", re.I)


def red_flags(text):
    """Every reason in the job's own words that it is not phase 1's to bid on, by rule."""
    out = []
    m = _OFF_PLATFORM.search(str(text or ""))
    if m:
        out.append("it asks to move off the platform (%r)" % m.group(0)[:40])
    m = _LONG.search(str(text or ""))
    if m:
        out.append("it is not one small scope (%r)" % m.group(0)[:40])
    return out


# ------------------------------------------------------------------------------ the model

def _ask_json(system, user, chat=None):
    """(object, "") or (None, why). Groq through the server's own client, or nothing."""
    chat = chat or _chat
    if chat is None:
        return None, "no model is connected to Revenue Mode"
    try:
        answer, error = chat([{"role": "system", "content": system},
                              {"role": "user", "content": user}])
    except Exception as exc:                                   # noqa: BLE001
        return None, "the model call threw (%s)" % type(exc).__name__
    if error or not answer:
        return None, str(error or "the model said nothing")[:200]
    text = re.sub(r"<think>.*?</think>", "", str(answer), flags=re.S)
    a, b = text.find("{"), text.rfind("}")
    if a < 0 or b <= a:
        return None, "the model did not answer in JSON"
    try:
        obj = json.loads(text[a:b + 1])
    except ValueError:
        return None, "the model's JSON would not parse (probably cut off)"
    return (obj, "") if isinstance(obj, dict) else (None, "the model's JSON was not an object")


class ModelDown(Exception):
    """Groq could not be asked at all: the pass waits rather than fall back."""


_hold_until = 0.0

FIT_SYSTEM = (
    "You decide whether one freelancer can deliver one small fixed-price job, using ONLY his "
    "SKILLS. Read the JOB and reply with JSON only:\n"
    '{"deliverables": [{"quote": "<exact words from the JOB naming one thing to deliver>", '
    '"skill": "<the ONE item from SKILLS that covers it, copied exactly, or null>"}], '
    '"kind": "code|writing|webpage|other", "hours": <whole hours an experienced person needs, '
    'all deliverables together>, "single": <true if it is one small piece of work with a clear '
    'end, false if open-ended or several projects>, "needs": ["<anything only the client can '
    'provide before work can start, e.g. their files, logins, content>"]}\n'
    "Rules: quote the JOB's own words, never paraphrase. A deliverable needing a skill not in "
    "SKILLS (design tools, mobile apps, a language he does not list) gets null. kind is code "
    "for scripts, fixes and components; webpage for an HTML/CSS page or site section; writing "
    "for text; other for anything else. At most six deliverables, each quote under fifteen "
    "words.")

BID_SYSTEM = (
    "You write one proposal for a freelancer, in the first person, as him. Rules:\n"
    "1. Open by naming what THIS client asked for, in their terms - no greeting fluff.\n"
    "2. Say how he would do it, in two to four concrete sentences, using ONLY his SKILLS and "
    "PROFILE.\n"
    "3. Mention relevant experience ONLY as his PROFILE states it. Never state a number of "
    "years. Never claim a certification, award, review, rating, portfolio, past client or "
    "result that the PROFILE does not state.\n"
    "4. No price, discount, deadline or delivery time (the form carries those). No guarantee. "
    "No links. No contact details. Do not mention AI and do not claim to be human.\n"
    "5. End with one short question about the work.\n"
    "6. 90 to 170 words, plain text, no placeholders, NO sign-off and no name at the end.\n"
    'Reply with JSON only: {"letter": "..."}')

VERIFY_SYSTEM = (
    "You are a strict fact-checker for one freelance proposal. PROFILE is everything true about "
    "the freelancer; JOB is the client's post. List every statement in DRAFT that (a) claims a "
    "skill, tool, employer, project, education, credential, review, rating, result, number of "
    "years or past client that PROFILE does not state; (b) promises a price, deadline, delivery "
    "time or guarantee; (c) claims the writer is human or denies being an AI; (d) gives any "
    "contact detail or asks to talk off the platform. Restating what the JOB asks for and how "
    "the work would be done with PROFILE's skills is fine. Reply with JSON only: "
    '{"unsupported": ["<short quote>", ...]} and an empty list if nothing is unsupported.')

# NOTHING HE IS NOT, by rule, whatever his facts contain: these are the claims a bid most often
# invents, and a bid needs none of them.
_FABRICATED = re.compile(r"\b(?:certif\w+|accredit\w+|award\w*|top[- ]rated|\d\s*-?star|five[- ]"
                         r"star|reviews?|ratings?|testimonials?|portfolio|guarantee\w*|100\s*%|"
                         r"satisfaction|years? of experience|\d+\+?\s*(?:years?|yrs)|decade|"
                         r"expert\w*|world[- ]class|ph\.?d|master'?s|clients? (?:like|including|"
                         r"such as)|fortune \d+)\b", re.I)


def vet_bid(text, facts, job_text):
    """Every reason `text` may not be sent as a bid. Pure; an empty list is the only pass."""
    text = str(text or "")
    allowed = (facts or "") + "\n" + (job_text or "")
    low = allowed.lower()
    nums = {closer._norm_num(n) for n in closer._DIGITS.findall(allowed)}
    problems = []
    for n in closer._DIGITS.findall(text):
        if closer._norm_num(n) not in nums:
            problems.append("the number %s is in nobody's facts" % n)
    for rx, what in ((closer._MONEY, "money word"), (closer._WHEN, "time promise")):
        for m in rx.finditer(text):
            if m.group(0).lower() not in low:
                problems.append("the %s %r is not the job's or his" % (what, m.group(0)))
    for m in _FABRICATED.finditer(text):
        problems.append("it claims %r, which a bid never states" % m.group(0))
    for m in closer._LINKISH.finditer(text):
        problems.append("the address %r" % m.group(0))
    if _OFF_PLATFORM.search(text):
        problems.append("it mentions going off the platform (%r)" % _OFF_PLATFORM.search(
            text).group(0))
    if closer._HUMAN.search(text):
        problems.append("it claims to be human")
    if re.search(r"\b(?:as an ai|an ai (?:model|assistant)|language model|chatgpt)\b", text, re.I):
        problems.append("it volunteers AI, which is answered only when asked")
    if closer._PLACEHOLDER.search(text):
        problems.append("it still has a placeholder: %r" % closer._PLACEHOLDER.search(text).group(0))
    return list(dict.fromkeys(problems))


def card_skip(budget, rates, s):
    """The reason a search result is not worth opening, from its card's budget alone - or "".
    Each opened job costs a page load and a model call; these three need neither."""
    if not budget:
        return ""
    if budget["hourly"]:
        return "it is hourly - phase 1 bids fixed price only"
    rate = rates.get(budget["currency"])
    if not rate:
        return "the budget is in %s and you have no hourly rate in %s" % (budget["currency"],
                                                                        budget["currency"])
    if budget["lo"] > rate * 100 * s["maxHours"]:
        return ("its minimum budget is more than %d hours at your rate - bigger than phase 1's "
                "jobs" % s["maxHours"])
    if budget["hi"] < rate * 100:
        return "its maximum budget is under one hour at your rate"
    return ""


def check_fit(job, facts, skills, s):
    """(fit, reasons). Rules first, then the model ON EVIDENCE: it must quote each deliverable
    and name the skill of his that covers it, and the code decides. Raises ModelDown."""
    reasons = list(job.get("flags") or [])
    budget = job.get("budget")
    if not budget:
        reasons.append("it states no budget I can read")
    elif budget["hourly"]:
        reasons.append("it is hourly - phase 1 bids fixed price only")
    if not skills:
        reasons.append("your profile names no skill I can bid with")
    if reasons:
        return None, reasons
    # THE LONGER CEILING: measured live on 2026-10-15, a fit answer quoting six deliverables was
    # cut at the butler's 400 tokens and came back unreadable. It costs only what it writes.
    got, err = _ask_json(FIT_SYSTEM, "SKILLS: %s\n\nJOB:\n%s" % (", ".join(skills),
                                                                 job["text"][:5000]),
                         chat=_work_chat or _chat)
    if got is None:
        if "JSON" in err:
            return None, ["the fit check could not be read (%s)" % err]
        raise ModelDown(err)
    owned = {x.lower() for x in skills}
    items = [d for d in (got.get("deliverables") or []) if isinstance(d, dict)]
    if not items:
        reasons.append("no deliverable could be named from the post")
    for d in items[:8]:
        quote, skill = str(d.get("quote") or ""), str(d.get("skill") or "").strip()
        if not closer._quoted(quote, job["text"]):
            reasons.append("the fit check quoted words the post does not contain (%r)"
                           % _clip(quote, 50))
        elif not skill or skill.lower() in ("null", "none") or skill.lower() not in owned:
            reasons.append("%r needs a skill your profile does not name" % _clip(quote, 60))
    kind = str(got.get("kind") or "other").lower()
    hours = got.get("hours")
    if kind not in WORK_KINDS:
        reasons.append("it is %s work, which phase 1 cannot deliver" % kind[:20])
    if type(hours) is not int or not 1 <= hours <= s["maxHours"]:
        reasons.append("it looks like %s hours of work, not 1 to %d" % (hours, s["maxHours"]))
    if got.get("single") is not True:
        reasons.append("it is not one small piece of work")
    if len(items) > 4:
        reasons.append("it asks for %d separate deliverables" % len(items))
    needs = [_clip(n, 120) for n in (got.get("needs") or []) if str(n).strip()][:5]
    if reasons:
        return None, list(dict.fromkeys(reasons))
    return {"kind": kind, "hours": hours, "needs": needs,
            "deliverables": [{"quote": _clip(d.get("quote"), 200), "skill": d.get("skill")}
                             for d in items]}, []


def price(budget, hours, rates):
    """(amount in minor units, "") or (None, why): his rate x the estimate, never under the
    client's minimum, and never above their maximum."""
    rate = rates.get(budget["currency"])
    if not rate:
        return None, "the budget is in %s and you have no hourly rate in %s" % (
            budget["currency"], budget["currency"])
    amount = max(budget["lo"], rate * 100 * int(hours))
    if amount > budget["hi"]:
        return None, "your rate for %d hours is above the client's maximum" % hours
    return amount, ""


def draft_bid(job, facts):
    """(letter, how) or (None, why). Raises ModelDown."""
    reasons = []
    user = "%s\n\nJOB:\n%s" % (facts, job["text"][:4000])
    for attempt in range(1, DRAFT_ATTEMPTS + 1):
        ask = user if not reasons else user + ("\n\nYOUR LAST DRAFT WAS REJECTED FOR: " +
                                               "; ".join(reasons[:6]) + ". Write it again.")
        got, err = _ask_json(BID_SYSTEM, ask, chat=_work_chat or _chat)
        if got is None:
            if "JSON" not in err:
                raise ModelDown(err)
            reasons = [err]
            continue
        letter = closer._tidy(got.get("letter"))
        if len(letter) < max(100, PLATFORMS[job["platform"]]["letter_min"]):
            reasons = ["it is too short"]
            continue
        reasons = vet_bid(letter, facts, job["text"])
        if reasons:
            continue
        verdict, err = _ask_json(VERIFY_SYSTEM, "PROFILE:\n%s\n\nJOB:\n%s\n\nDRAFT:\n%s" % (
            facts, job["text"][:3000], letter))
        if verdict is None:
            if "JSON" not in err:
                raise ModelDown(err)
            reasons = ["the checker's verdict could not be read"]
            continue
        reasons = ["unsupported: %r" % _clip(q, 120) for q in (verdict.get("unsupported") or [])
                   if str(q).strip()]
        if not reasons:
            return letter[:2500], "model, attempt %d" % attempt
    return None, "no draft passed the checks (%s)" % "; ".join(reasons[:3])


# ------------------------------------------------------------------------------ the browser

# Where any platform's post ends, failing its own job_end: the messages sidebar.
JOB_END = r"\n(?:Messages|Chats)\n"


class Session:
    """One background tab in the employer's DevTools Chrome, Operator's primitives on it, and
    Ctrl+M armed for as long as it is open. Every platform verb Revenue Mode has is here; the
    tests stand a fake with the same verbs in its place."""

    def __init__(self, panic=True, budget_s=SESSION_S, port=None):
        self.panic = core.PanicKey(PANIC_ID) if panic else None
        self.run = core.Run(self.panic, budget_s)
        self.port, self.browser_ws = (port, None) if port else core.live_port()
        if port:
            found = core.get_json("http://127.0.0.1:%d/json/version" % port)
            self.browser_ws = (found or {}).get("webSocketDebuggerUrl")
        self.tab = self.browser = self.target = None

    def __enter__(self):
        if self.port is None:
            raise core.Failed(core.NO_PORT)
        if self.panic is not None:
            refusal = core.arm_or_refuse(self.panic, "revenue")
            if refusal:
                raise core.Failed(refusal)
        self.browser = core.CDP(self.browser_ws)
        # IN THE BACKGROUND: a tab that reads does not take the employer's screen. A press brings
        # it to the front first (front()), as Operator's hands do - a background tab drops input.
        self.target = self.browser.call("Target.createTarget",
                                        {"url": "about:blank", "background": True})["targetId"]
        self.tab = core.CDP("ws://127.0.0.1:%d/devtools/page/%s" % (self.port, self.target))
        return self

    def __exit__(self, *exc):
        for step in (lambda: self.tab and self.tab.close(),
                     lambda: self.browser and self.target and self.browser.call(
                         "Target.closeTarget", {"targetId": self.target}, timeout=5.0),
                     lambda: self.browser and self.browser.close(),
                     lambda: self.panic and self.panic.disarm()):
            try:
                step()
            except Exception:                                  # noqa: BLE001
                pass
        return False

    # ---- looking
    def go(self, key, url, what, ready=None, wait=20.0):
        """Navigate, wait for the SPA to paint (`ready`: a JS expression, else 600+ characters of
        text), then check for a login or a challenge. The page dict."""
        core.navigate(self.run, self.tab, url, what)
        expr = ready or "(document.body && document.body.innerText.length > 600)"
        core.wait_for(self.run, self.tab, expr, timeout=wait)
        self.run.nap(1.0)
        page = core.read_page(self.tab, cap=8000) or {}
        where = str(self.tab.evaluate("location.href", timeout=5.0) or page.get("url") or "")
        head = "\n".join([page.get("title") or ""] + list(page.get("headings") or [])[:4] +
                         [(page.get("text") or "")[:600]])
        if _LOGIN_URL.search(urllib.parse.urlsplit(where).path) or _LOGIN_TEXT.search(head):
            raise NotSignedIn(key)
        if _CHALLENGE.search(head):
            raise Challenge(key)
        page["url"] = where
        return page

    def profile(self, key):
        page = self.go(key, PLATFORMS[key]["profile"], "reading your %s profile"
                       % PLATFORMS[key]["name"])
        return {"text": profile_facts(page.get("text")), "url": page["url"],
                "name": _clip((page.get("headings") or [""])[0], 60)}

    def search(self, key, query):
        layer = PLATFORMS[key]
        url = layer["search"].replace("{q}", urllib.parse.quote(query))
        rx = layer["job_href"]
        links = ("Array.from(document.querySelectorAll('a[href]')).filter(function(a){return new "
                 "RegExp(%s,'i').test(a.getAttribute('href'))}).map(function(a){return [a.innerText"
                 ".replace(/\\s+/g,' ').trim().slice(0,600), a.href]})" % json.dumps(rx))
        self.go(key, url, "searching %s for '%s'" % (layer["name"], query),
                ready="(%s).length > 2" % links)
        seen, out = set(), []
        for text, href in self.tab.evaluate(links, timeout=8.0) or []:
            if href in seen or not text:
                continue
            seen.add(href)
            out.append({"url": href, "card": text, "title": _clip(re.split(
                r"\s+(?:Budget|Est\. budget)\b", text)[0], 120)})
        return out

    def read_job(self, key, url):
        page = self.go(key, url, "reading a job on %s" % PLATFORMS[key]["name"],
                       ready="!!document.querySelector('h1') && document.body.innerText."
                             "length > 1200")
        full = page.get("text") or ""
        text = full
        m = re.search(PLATFORMS[key].get("job_end") or JOB_END, text)
        if m and m.start() > 200:
            text = text[:m.start()]
        return {"url": page["url"], "title": _clip((page.get("headings") or [""])[0] or
                                                    page.get("title"), 200),
                "text": text, "full": full}

    # ---- pressing
    def front(self):
        core.show_tab(self.run, self.tab, "ws://127.0.0.1:%d/devtools/page/%s"
                      % (self.port, self.target))

    def _field(self, description):
        found = core.wait_target(self.run, self.tab, description, timeout=10.0, role="field")
        if not found["ok"]:
            raise core.Failed(core.miss_line(found, description, verb="fill in the bid"))
        return found

    def _type(self, description, text):
        found = self._field(description)
        got = core.act_type(self.run, self.tab, found, str(text))
        return got

    def _press(self, words, verb):
        btn = core.wait_target(self.run, self.tab, "the %s button" % words, timeout=10.0,
                               role="button", exact=words)
        if not btn["ok"]:
            raise core.Failed(core.miss_line(btn, "the '%s' button" % words, verb=verb))
        return core.act_click(self.run, self.tab, btn)

    PAID_EXTRAS = (r"(function(){var bad=[];document.querySelectorAll('input[type=checkbox]')"
                   r".forEach(function(c){if(!c.checked)return;var e=c,t='';for(var i=0;i<6&&e;"
                   r"i++){t=(e.innerText||'');if(t.length>20)break;e=e.parentElement}if(/sponsor|"
                   r"highlight|featured|urgent|upgrade|boost|[$\u20b9\u00a3\u20ac]\s?\d/i.test(t))"
                   r"bad.push(t.replace(/\s+/g,' ').slice(0,60))});return bad})()")

    def place_bid(self, key, job, bid):
        """(status, line): "bid" when the platform's own words confirm it, "bid-unconfirmed" when
        Place was pressed and nothing confirmed it, Failed before any press."""
        layer = PLATFORMS[key]
        self.go(key, job["url"], "opening the job to bid")
        self.front()
        if layer.get("apply_button"):
            self._press(layer["apply_button"], "open the bid form")
            core.wait_for(self.run, self.tab, "document.querySelectorAll('textarea').length>0",
                          timeout=15.0)
        fields = layer["fields"]
        self.run.at("filling in the bid")
        self._type("the %s field" % fields["amount"], "%d" % (bid["amount"] // 100) if
                   bid["amount"] % 100 == 0 else "%d.%02d" % divmod(bid["amount"], 100))
        if fields.get("days"):
            self._type("the %s field" % fields["days"], str(bid["days"]))
        self._type("the %s field" % fields["letter"], bid["letter"])
        bad = self.tab.evaluate(self.PAID_EXTRAS, timeout=5.0) or []
        if bad:
            raise core.Failed("I did not place the bid - a paid upgrade is ticked on the form "
                              "(%s), and I never pay for one" % bad[0])
        before = (core.read_page(self.tab, cap=12000) or {}).get("text") or ""
        self.run.at("pressing %s" % layer["bid_button"])
        self._press(layer["bid_button"], "place the bid")
        # CONFIRMED BY THE PLATFORM'S OWN WORDS, and only by words that were NOT on the page
        # before the press - a form that already said "your bid" proves nothing.
        for _ in range(16):
            self.run.nap(1.0)
            text = (core.read_page(self.tab, cap=12000) or {}).get("text") or ""
            for rx in layer["bid_done"]:
                if len(re.findall(rx, text, re.I)) > len(re.findall(rx, before, re.I)):
                    return "bid", _clip(re.search(rx, text, re.I).group(0), 80)
        return "bid-unconfirmed", "Place was pressed and the page did not say the bid went in"

    def check_award(self, key, job):
        page = self.go(key, job["url"], "checking a bid on %s" % PLATFORMS[key]["name"])
        text = page.get("text") or ""
        return any(re.search(rx, text, re.I) for rx in PLATFORMS[key]["award"]), text

    def accept_award(self, key, job):
        if not PLATFORMS[key].get("accept_button"):
            return True
        self.front()
        self._press(PLATFORMS[key]["accept_button"], "accept the award")
        self.run.nap(3.0)
        text = (core.read_page(self.tab, cap=6000) or {}).get("text") or ""
        return not re.search(r"\baccept (?:the )?(?:project|offer)\b", text, re.I)

    def send_message(self, key, job, text):
        self.go(key, job["url"], "opening the job's messages")
        self.front()
        self._type("the message box", text)
        self._press("send", "send the message")
        return True

    def deliver(self, key, job, files, note):
        """Attach the files, type the note, press the platform's deliver control. (status, line)."""
        layer = PLATFORMS[key]
        self.go(key, job["url"], "opening the job to deliver")
        self.front()
        doc = self.tab.call("DOM.getDocument", {"depth": 1})
        node = self.tab.call("DOM.querySelector", {"nodeId": doc["root"]["nodeId"],
                                                   "selector": "input[type=file]"}).get("nodeId")
        if not node:
            raise core.Failed("I did not deliver anything - there is no place on the page to "
                              "attach a file")
        self.tab.call("DOM.setFileInputFiles", {"nodeId": node, "files": list(files)})
        self._type("the message box", note)
        self._press(layer["deliver_button"], "deliver the work")
        self.run.nap(4.0)
        text = (core.read_page(self.tab, cap=8000) or {}).get("text") or ""
        names = [os.path.basename(f) for f in files]
        if any(re.search(rx, text, re.I) for rx in layer["deliver_done"]) or \
                all(n in text for n in names):
            return "submitted", "the page shows the delivery"
        return "submit-unconfirmed", "pressed, and the page did not show the delivery"

    def earnings(self, key):
        page = self.go(key, PLATFORMS[key]["earnings"], "reading your %s transactions"
                       % PLATFORMS[key]["name"], wait=25.0)
        return page.get("text") or ""

    def screenshot(self, path):
        self.front()
        shot = self.tab.call("Page.captureScreenshot", {"format": "png"}, timeout=15.0)
        with open(path, "wb") as fh:
            fh.write(base64.b64decode(shot.get("data") or ""))
        return path


# ------------------------------------------------------------------------------ one pass

def _bids_today(rows):
    return [r for r in rows if r.get("kind") == "bid" and str(r.get("at"))[:10] == _today()]


def _gap_ok(rows, s):
    last = max((r.get("at") for r in rows if r.get("kind") == "bid"), default="")
    if not last:
        return True
    return (_now() - datetime.datetime.fromisoformat(last)).total_seconds() >= s["gapMin"] * 60


def ensure_profile(sess, key, note):
    """His profile on `key`, read live once a day. False (with the line noted) when it cannot be."""
    prof = ((read_state().get("profiles") or {}).get(key) or {})
    fresh = prof.get("text") and time.time() - prof.get("ts", 0) < PROFILE_MAX_AGE_S
    if fresh:
        return True
    got = sess.profile(key)
    if len(got["text"]) < 80:
        note("%s: your profile there is nearly empty, so I have nothing true to bid with"
             % PLATFORMS[key]["name"])
        return False

    def change(state):
        state.setdefault("profiles", {})[key] = dict(got, ts=time.time(), at=_stamp(),
                                                     sha256=hashlib.sha256(
                                                         got["text"].encode("utf-8")).hexdigest())
    _write_state(change)
    note("%s: read your profile (%d characters of your own words)" % (
        PLATFORMS[key]["name"], len(got["text"])))
    return True


def find_and_bid(sess, key, s, note, daily):
    """Read the next search's results, read new jobs, bid on the first that fits. One bid at most."""
    rows = read_log()
    # NO BID DUE, NO LOOKING: a job that fits but cannot be bid on today would only be read,
    # model-checked and lost. It is left in the search results for a pass that can bid on it.
    if len(_bids_today(rows)) >= daily:
        note("%s: today's %d bid%s placed - not looking for more" % (
            PLATFORMS[key]["name"], daily, " is" if daily == 1 else "s are"))
        return None
    if not _gap_ok(rows, s):
        note("%s: the last bid was under %d minutes ago - not looking yet" % (
            PLATFORMS[key]["name"], s["gapMin"]))
        return None
    state = read_state()
    turn = int((state.get("turns") or {}).get(key, 0))
    _write_state(lambda st: st.setdefault("turns", {}).__setitem__(key, turn + 1))
    query = s["searches"][turn % len(s["searches"])]
    facts, skills, rates, _name = facts_for(key, s)
    if facts is None:
        note("%s: your profile has not been read, so I did not look for work" % (
            PLATFORMS[key]["name"]))
        return None
    results = sess.search(key, query)
    known = known_urls()
    fresh = [r for r in results if _norm_url(r["url"]) not in known]
    note("%s: '%s' - %d results, %d new" % (PLATFORMS[key]["name"], query, len(results),
                                             len(fresh)))
    opened = 0
    for found in fresh:
        why_card = card_skip(budget_in(found["card"]), rates, s)
        if why_card:
            add_job(key, found["url"], found["title"], budget=budget_in(found["card"]),
                    query=query, status="skipped", why=[why_card], read="card")
            continue
        if opened >= JOBS_READ_PER_PASS:
            break
        opened += 1
        page = sess.read_job(key, found["url"])
        text = page["text"]
        job = {"platform": key, "url": page["url"] or found["url"], "title": page["title"] or
               found["title"], "text": text, "budget": budget_in(text) or budget_in(found["card"]),
               "flags": red_flags(text)}
        row, new = add_job(key, job["url"], job["title"], budget=job["budget"],
                           skills=required_skills(text), query=query, jobText=text[:6000])
        if not new and row.get("status") != "seen":
            continue
        if any(re.search(rx, page.get("full") or "", re.I) for rx in PLATFORMS[key]["bid_done"]):
            update_job(row["id"], "skipped", why=["you have already bid on it yourself"])
            note("%s skipped: already bid on" % row["id"])
            continue
        fit, why = check_fit(job, facts, skills, s)
        if fit is None:
            update_job(row["id"], "skipped", why=why[:4])
            note("%s skipped (%s): %s" % (row["id"], _clip(job["title"], 50), why[0]))
            continue
        amount, why_not = price(job["budget"], fit["hours"], rates)
        if amount is None:
            update_job(row["id"], "skipped", why=[why_not], fit=fit)
            note("%s skipped (%s): %s" % (row["id"], _clip(job["title"], 50), why_not))
            continue
        letter, how = draft_bid(job, facts)
        if letter is None:
            update_job(row["id"], "skipped", why=[how], fit=fit)
            note("%s held: %s" % (row["id"], how))
            continue
        bid = {"amount": amount, "currency": job["budget"]["currency"], "days": s["days"],
               "letter": letter, "hours": fit["hours"]}
        entry = log_event({"kind": "bid", "jobId": row["id"], "platform": key,
                           "title": job["title"], "url": job["url"], "status": "pressing",
                           "amount": amount, "currency": bid["currency"], "days": s["days"],
                           "letter": letter, "draft": how,
                           "why": "fits: %s; %d hours at your rate" % (
                               ", ".join(d["skill"] for d in fit["deliverables"]),
                               fit["hours"])})
        update_job(row["id"], "bid-unconfirmed", fit=fit, bid=dict(bid, entry=entry["id"]))
        try:
            status, line = sess.place_bid(key, job, bid)
        except core.Failed as exc:
            update_event(entry["id"], status="failed", error=str(exc)[:300])
            update_job(row["id"], "bid-failed", why=[str(exc)[:300]])
            note("%s bid NOT placed and will not be retried: %s" % (row["id"], exc))
            return None
        update_event(entry["id"], status=status, confirm=line)
        update_job(row["id"], status, bidAt=_stamp())
        note("%s %s on %s: %s %s - %s" % (row["id"], "BID PLACED" if status == "bid" else
                                          "bid pressed, unconfirmed", PLATFORMS[key]["name"],
                                          bid["currency"], ledger.money(amount, bid["currency"])
                                          if bid["currency"] in ledger.CURRENCIES else amount,
                                          line))
        return row["id"]
    return None


def watch_bids(sess, key, note):
    """Awards on bids placed, accepted; client messages answered where honesty requires it."""
    for job in [j for j in read_book() if j.get("platform") == key
                and j.get("status") in ("bid", "bid-unconfirmed")]:
        awarded, text = sess.check_award(key, job)
        if not awarded:
            continue
        entry = log_event({"kind": "accept", "jobId": job["id"], "platform": key,
                           "title": job["title"], "status": "pressing",
                           "why": "the platform shows the bid as awarded"})
        ok = sess.accept_award(key, job)
        update_event(entry["id"], status="accepted" if ok else "unconfirmed")
        update_job(job["id"], "awarded", awardedAt=_stamp(), seenLines=_line_keys(text))
        note("%s AWARDED on %s%s" % (job["id"], PLATFORMS[key]["name"],
                                    "" if ok else " (accept pressed, not confirmed)"))
    for job in [j for j in read_book() if j.get("platform") == key
                and j.get("status") in ("awarded", "needs-input", "ready", "submitted")]:
        _, text = sess.check_award(key, job)
        answer_client(sess, key, job, text, note)


AI_LINE = ("To answer your question directly: yes, AI was involved - I use an AI assistant in my "
           "work, and I review everything myself before it is delivered to you.")
OFF_PLATFORM_LINE = ("Thanks - I keep all communication and payment here on %s, as its terms "
                     "require, so I can't take payment or move the conversation outside it. Happy "
                     "to continue right here.")
# THE CLOSER'S "ARE YOU AN AI?", WIDENED to "was AI involved?" - the brief's own question. A client
# asks about the work as often as about the writer: "did you use AI for this?", "is this AI
# generated?", "was ChatGPT used?". The Closer's pattern alone let the first of those through.
_AI_ASKED = re.compile(closer._AI_ASKED.pattern + r"|\b(?:did|do|does|was|were|is|are|have|has)\s+"
                       r"(?:you|u|this|it|they|any)\s+(?:\w+\s+){0,3}?(?:use[ds]?|using|made|"
                       r"written|done|generated|created|involved)\s+(?:\w+\s+){0,3}?(?:ai|a\.i\.|"
                       r"chat\s*gpt|gpt|bots?|llms?)\b|\bai[- ](?:generated|written|made|"
                       r"involved)\b|\b(?:ai|chat\s*gpt|gpt)\s+(?:was|were)\s+(?:used|involved)\b|"
                       r"\b(?:was|were|is|are)\s+(?:an?\s+|any\s+)?(?:ai|chat\s*gpt|gpt)(?:\s+\w+)"
                       r"{0,2}?\s+(?:used|involved)\b",
                       re.I)


def _line_keys(text):
    return sorted({hashlib.sha1(ln.strip().encode("utf-8")).hexdigest()[:12]
                   for ln in str(text or "").splitlines() if ln.strip()})[:2000]


def new_lines(text, job):
    """The page's lines that were not there when the job was awarded, nor ours - what the client
    has written since. Only these are read for a question: the post itself, other bidders and the
    platform's own sidebar are not the client talking to him."""
    seen = set(job.get("seenLines") or [])
    ours = {AI_LINE, OFF_PLATFORM_LINE % PLATFORMS[job["platform"]]["name"]}
    return "\n".join(ln for ln in str(text or "").splitlines() if ln.strip() and ln.strip()
                     not in ours and hashlib.sha1(ln.strip().encode("utf-8")).hexdigest()[:12]
                     not in seen)


def answer_client(sess, key, job, text, note):
    """The two things a client message is answered with on its own, both fixed sentences: an
    honest yes to "was AI involved?", and a refusal to leave the platform. Each at most once per
    job. Anything else a client writes waits for the employer, in the report."""
    seen = set(job.get("answered") or [])
    fresh = new_lines(text, job)
    out = []
    if "ai" not in seen and _AI_ASKED.search(fresh):
        out.append(("ai", AI_LINE))
    if "off" not in seen and _OFF_PLATFORM.search(fresh):
        out.append(("off", OFF_PLATFORM_LINE % PLATFORMS[key]["name"]))
    for tag, line in out:
        entry = log_event({"kind": "message", "jobId": job["id"], "platform": key,
                           "status": "pressing", "body": line,
                           "why": "the client asked whether AI was involved" if tag == "ai" else
                           "the client asked to go off the platform"})
        try:
            sess.send_message(key, job, line)
            update_event(entry["id"], status="sent")
            seen.add(tag)
            update_job(job["id"], answered=sorted(seen))
            note("%s: answered the client (%s)" % (job["id"], "AI question" if tag == "ai"
                                                   else "declined off-platform"))
        except core.Failed as exc:
            update_event(entry["id"], status="failed", error=str(exc)[:200])
            seen.add(tag)                     # never retried: a failed press may have landed
            update_job(job["id"], answered=sorted(seen))
            note("%s: could not answer the client: %s" % (job["id"], exc))


_TX_DATE = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b")
_TX_AMOUNT = re.compile(r"([$\u20b9])\s?([\d,]+\.\d{2})\s*(USD|INR)?")


def payment_in(text, job, placeholders=()):
    """{amount, currency, on, line} when the transactions text holds a row that names this job's
    EXACT title, is dated on or after its submission and is none of the platform's sample rows -
    else None. Pure, and the reason a skeleton row can never become money in the ledger."""
    title = " ".join(str(job.get("title") or "").lower().split())
    if not title:
        return None
    since = str((job.get("submit") or {}).get("at") or job.get("submittedAt") or "")[:10]
    lines = [ln.strip() for ln in str(text or "").splitlines() if ln.strip()]
    starts = [i for i, ln in enumerate(lines) if _TX_DATE.fullmatch(ln)]
    for i, ln in enumerate(lines):
        if " ".join(ln.lower().split()) != title:
            continue
        # ONE ROW: from the date line that opens it to the next one (measured: each transaction
        # begins with its date) - so a sample row beside a real one cannot taint or lend to it.
        head = max([s for s in starts if s <= i], default=max(0, i - 8))
        tail = min([s for s in starts if s > i], default=i + 8)
        window = lines[head:tail]
        blob = "\n".join(window).lower()
        if any(p in blob for p in placeholders):
            continue
        dates = []
        for d in _TX_DATE.finditer("\n".join(window)):
            try:
                dates.append(datetime.date(int(d.group(3)), int(d.group(1)), int(d.group(2))))
            except ValueError:
                continue
        day = max(dates) if dates else None
        if day is None or (since and day.isoformat() < since):
            continue
        amounts = [m for m in _TX_AMOUNT.finditer("\n".join(window))]
        if not amounts:
            continue
        m = amounts[0]
        cur = (m.group(3) or ("USD" if m.group(1) == "$" else "INR")).upper()
        return {"amount": _units(m.group(2)), "currency": cur, "on": day.isoformat(),
                "line": _clip(" | ".join(window), 300)}
    return None


def watch_payments(sess, key, note):
    jobs = [j for j in read_book() if j.get("platform") == key
            and j.get("status") in ("submitted", "submit-unconfirmed")]
    if not jobs:
        return
    text = sess.earnings(key)
    for job in jobs:
        paid = payment_in(text, job, PLATFORMS[key].get("placeholders") or ())
        if not paid:
            continue
        os.makedirs(ledger.PROOFS_DIR, exist_ok=True)
        proof = os.path.join(ledger.PROOFS_DIR, "revenue-%s-%s.png" % (job["id"], paid["on"]))
        try:
            sess.screenshot(proof)
        except core.Failed as exc:
            note("%s: paid, but the proof screenshot failed (%s)" % (job["id"], exc))
            proof = None
        log_event({"kind": "payment", "jobId": job["id"], "platform": key, "status": "read",
                   "amount": paid["amount"], "currency": paid["currency"], "on": paid["on"],
                   "line": paid["line"], "proof": proof and os.path.basename(proof),
                   "why": "the platform's transactions list the job by its exact title"})
        update_job(job["id"], "paid", paid=dict(paid, proof=proof and os.path.relpath(
            proof, os.path.dirname(ledger.PROOFS_DIR)).replace(os.sep, "/"), at=_stamp()))
        note("%s PAID: %s" % (job["id"], ledger.money(paid["amount"], paid["currency"])
                               if paid["currency"] in ledger.CURRENCIES else paid["amount"]))


# ------------------------------------------------------------------------------ the work

PLAN_SYSTEM = (
    "You plan the deliverable for one small freelance job the freelancer has been awarded. "
    "Using ONLY his SKILLS, decide the files to hand over (one to four). Reply with JSON only: "
    '{"kind": "code|writing|webpage", "files": [{"name": "file name with extension", "what": '
    '"one sentence: what goes in it"}], "summary": "two sentences for the client describing '
    'what is delivered", "missing": ["anything the JOB depends on that only the client can '
    'provide and was not given - their files, logins, exact content"]}. Code: .py or .js or '
    ".jsx or .ts files. Webpage: one .html file with its CSS inline, plus .css/.js only if "
    "asked. Writing: .md files.")
FILE_SYSTEM = (
    "You are the freelancer delivering one file of an awarded job. Write the COMPLETE content of "
    "the file named below - finished, working, no placeholders like TODO or lorem ipsum, no "
    "invented statistics, testimonials, prices, addresses or contact details (where the job "
    "needs real content the client has not given, use an obvious bracketed note such as "
    "[client's phone number]). Output ONLY the file's content, nothing before or after it.")


def _strip_fence(text):
    text = re.sub(r"<think>.*?</think>", "", str(text or ""), flags=re.S).strip()
    m = re.match(r"^```[\w.+-]*\s*\n(.*?)\n```\s*$", text, re.S)
    return (m.group(1) if m else text).strip() + "\n"


def _safe_name(name):
    base = re.sub(r"[^A-Za-z0-9._-]+", "-", os.path.basename(str(name or ""))).strip(".-")
    return base[:60] or "work.txt"


def check_file(path):
    """"" or why the file may not go to review as it stands."""
    ext = os.path.splitext(path)[1].lower()
    with open(path, "r", encoding="utf-8") as fh:
        body = fh.read()
    if len(body.strip()) < 40:
        return "it is nearly empty"
    if re.search(r"\bTODO\b|lorem ipsum", body, re.I):
        return "it still has a TODO or lorem ipsum"
    if ext == ".py":
        return closer._check_code("python", body)
    if ext == ".js":
        return closer._check_code("javascript", body)
    if ext == ".html" and "</html>" not in body.lower():
        return "the HTML is not a whole page"
    return ""


def review_notes(path, job_text):
    """What the employer should check by eye: every figure and link in the work that is not in
    the job post. Written into REVIEW.txt, never fixed silently."""
    with open(path, "r", encoding="utf-8") as fh:
        body = fh.read()
    allowed = str(job_text or "").lower()
    out = []
    for m in closer._LINKISH.finditer(body):
        if m.group(0).lower() not in allowed:
            out.append("a link or address the post does not give: %s" % m.group(0)[:80])
    if os.path.splitext(path)[1].lower() in (".md", ".txt", ".html"):
        for m in re.finditer(r"\b\d[\d,.]*%?", re.sub(r"<[^>]+>", " ", body)):
            if m.group(0).strip(".,") not in allowed and len(m.group(0)) > 1:
                out.append("a figure the post does not give: %s" % m.group(0))
    return list(dict.fromkeys(out))[:15]


def do_work(job, note, s=None):
    """Make the deliverable for one awarded job and stop at "ready". Raises ModelDown."""
    s = s or settings()[0]
    _facts, skills, _rates, _name = facts_for(job["platform"], s)
    started = _stamp()
    text = job.get("jobText") or job.get("title")
    got, err = _ask_json(PLAN_SYSTEM, "SKILLS: %s\n\nJOB:\n%s" % (", ".join(skills), text[:5000]))
    if got is None:
        if "JSON" in err:
            update_job(job["id"], "work-failed", why=["the work plan could not be read"])
            return
        raise ModelDown(err)
    missing = [_clip(m, 160) for m in (got.get("missing") or []) if str(m).strip()][:5]
    if missing:
        update_job(job["id"], "needs-input", missing=missing)
        note("%s needs from the client: %s" % (job["id"], "; ".join(missing)))
        return
    files = [f for f in (got.get("files") or []) if isinstance(f, dict) and f.get("name")][:4]
    if not files:
        update_job(job["id"], "work-failed", why=["the plan named no file"])
        return
    folder = os.path.join(WORK_DIR, job["id"])
    os.makedirs(folder, exist_ok=True)
    made, problems, notes = [], [], []
    chat = _work_chat or _chat
    for f in files:
        fname = _safe_name(f["name"])
        try:
            body, error = chat([{"role": "system", "content": FILE_SYSTEM},
                                {"role": "user", "content": "JOB:\n%s\n\nTHE WHOLE DELIVERY: %s\n\n"
                                 "THIS FILE: %s - %s" % (text[:5000], json.dumps(files)[:800],
                                                         fname, _clip(f.get("what"), 300))}])
        except Exception as exc:                               # noqa: BLE001
            body, error = None, type(exc).__name__
        if error or not body:
            raise ModelDown(str(error or "the model said nothing"))
        path = os.path.join(folder, fname)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(_strip_fence(body))
        bad = check_file(path)
        if bad:
            problems.append("%s: %s" % (fname, bad))
        notes += ["%s: %s" % (fname, n) for n in review_notes(path, text)]
        if fname.lower().endswith(".html") and not bad:
            png = os.path.splitext(path)[0] + "-preview.png"
            with open(path, "r", encoding="utf-8") as fh:
                why = closer.render(fh.read(), png, "png")
            if why:
                notes.append("%s: the preview could not be drawn (%s)" % (fname, why))
        made.append(path)
    if problems:
        update_job(job["id"], "work-failed", why=problems)
        note("%s work failed its checks: %s" % (job["id"], problems[0]))
        return
    delivery = os.path.join(folder, "DELIVERY-NOTE.txt")
    with open(delivery, "w", encoding="utf-8") as fh:
        fh.write("Hi,\n\n%s\n\nAttached: %s.\n\nLet me know if you would like anything "
                 "changed.\n" % (_clip(got.get("summary"), 600), ", ".join(
                     os.path.basename(p) for p in made)))
    with open(os.path.join(folder, "REVIEW.txt"), "w", encoding="utf-8") as fh:
        fh.write("READY FOR YOUR REVIEW - %s (%s on %s)\n%s\n\nNothing has been sent. Read the "
                 "files, fix anything, edit DELIVERY-NOTE.txt as you like, then say \"submit "
                 "it\". Every file in this folder except REVIEW.txt and the -preview.png images "
                 "goes to the client.\n\nCHECK BY EYE:\n%s\n" % (
                     job["title"], job["id"], PLATFORMS[job["platform"]]["name"], job["url"],
                     "\n".join("- " + n for n in notes) or "- nothing flagged"))
    update_job(job["id"], "ready", work={"dir": os.path.relpath(folder, HERE).replace(os.sep, "/"),
                                         "files": [os.path.basename(p) for p in made],
                                         "startedAt": started, "readyAt": _stamp(),
                                         "notes": notes})
    log_event({"kind": "work", "jobId": job["id"], "platform": job["platform"],
               "status": "ready", "files": [os.path.basename(p) for p in made],
               "why": "awarded; made and checked, waiting for the employer's review"})
    note("%s READY FOR YOUR REVIEW: %s" % (job["id"], folder))


def deliverables(job):
    """[(path, sha256)] - what is in the job's folder NOW, as the employer left it."""
    folder = os.path.join(WORK_DIR, job["id"])
    out = []
    for name in sorted(os.listdir(folder)) if os.path.isdir(folder) else []:
        if name in ("REVIEW.txt", "DELIVERY-NOTE.txt") or name.endswith("-preview.png"):
            continue
        path = os.path.join(folder, name)
        if os.path.isfile(path):
            with open(path, "rb") as fh:
                out.append((path, hashlib.sha256(fh.read()).hexdigest()))
    return out


def submit(job_id, session_factory=None):
    """THE EMPLOYER'S "SUBMIT IT", after his yes on the revenue_submit card. (line, ok)."""
    job = find_job(job_id)
    if not job:
        return "There is no job %s in the book, so nothing was sent." % job_id, False
    if job.get("status") != "ready":
        return "%s is %s, not ready for review, so nothing was sent." % (
            job_id, job.get("status")), False
    files = deliverables(job)
    if not files:
        return "The folder for %s has no work in it, so nothing was sent." % job_id, False
    try:
        with open(os.path.join(WORK_DIR, job_id, "DELIVERY-NOTE.txt"), "r",
                  encoding="utf-8") as fh:
            delivery = fh.read().strip()
    except OSError:
        delivery = ""
    if _OFF_PLATFORM.search(delivery):
        return ("DELIVERY-NOTE.txt for %s mentions going off the platform (%r), so nothing was "
                "sent." % (job_id, _OFF_PLATFORM.search(delivery).group(0)), False)
    entry = log_event({"kind": "delivery", "jobId": job_id, "platform": job["platform"],
                       "status": "pressing", "by": "employer", "note": delivery[:4000],
                       "files": [{"name": os.path.basename(p), "sha256": h} for p, h in files],
                       "why": "the employer reviewed it and said submit"})
    try:
        with (session_factory or Session)() as sess:
            status, line = sess.deliver(job["platform"], job, [p for p, _ in files], delivery)
    except core.Aborted as stop:
        update_event(entry["id"], status="aborted", error=str(stop.args[0])[:200])
        return "Stopped - you took back control while %s. It may be half-sent, so check it." % (
            stop.args[0]), False
    except NotSignedIn as exc:
        update_event(entry["id"], status="failed", error="not signed in")
        return signed_out_line(exc.args[0]), False
    except Challenge as exc:
        update_event(entry["id"], status="failed", error="challenge")
        return challenge_line(exc.args[0]), False
    except core.Failed as exc:
        update_event(entry["id"], status="failed", error=str(exc)[:300])
        return core.failure_line(exc), False
    update_event(entry["id"], status=status, confirm=line)
    update_job(job_id, status, submittedAt=_stamp(),
               submit={"at": _stamp(), "entry": entry["id"],
                       "files": [{"name": os.path.basename(p), "sha256": h} for p, h in files]})
    name = PLATFORMS[job["platform"]]["name"]
    if status == "submitted":
        return "Submitted %s to the client on %s, sir - %d file%s. I'll watch for the payment." % (
            job["title"], name, len(files), "" if len(files) == 1 else "s"), True
    return ("I pressed submit for %s on %s, sir, but the page did not show the delivery - please "
            "look before I count it as sent." % (job["title"], name)), True


# ------------------------------------------------------------------------------ the pass

def tick(note=None, session_factory=None):
    """One pass: for each platform, check the session, then watch, pay, bid. Then one piece of
    work. Returns the notes."""
    notes = []

    def say(line):
        notes.append(line)
        if note:
            note(line)
    state = read_state()
    if not state.get("on"):
        say("Revenue Mode is off")
        return notes
    s, problems = settings()
    if problems:
        say("not working: " + problems[0])
        return notes
    daily = int(state.get("daily") or s["daily"])
    global _hold_until
    down = None
    try:
        with (session_factory or Session)() as sess:
            # A MODEL OUTAGE STOPS THE MODEL'S WORK, NOT THE LOOKING. Measured live on 2026-10-15:
            # Groq's daily limit on Freelancer.com's first fit check ended the whole pass, and
            # Upwork and Fiverr were never checked - so "I'm not signed into Upwork" was never
            # said. Every platform is still opened and checked; only find_and_bid waits.
            for key in s["platforms"]:
                paused = ((state.get("paused") or {}).get(key) or {})
                if paused.get("day") == _today():
                    say("%s: paused for today - %s" % (PLATFORMS[key]["name"], paused["why"]))
                    continue
                try:
                    if not ensure_profile(sess, key, say):
                        note_platform(key, False, "profile empty")
                        continue
                    note_platform(key, True, "signed in")
                    watch_bids(sess, key, say)
                    watch_payments(sess, key, say)
                    if down is None:
                        find_and_bid(sess, key, s, say, daily)
                except ModelDown as exc:
                    down = exc
                except NotSignedIn:
                    note_platform(key, False, signed_out_line(key))
                    say(signed_out_line(key))
                except Challenge:
                    _write_state(lambda st: st.setdefault("paused", {}).__setitem__(
                        key, {"day": _today(), "why": "it asked whether I am a person"}))
                    note_platform(key, False, challenge_line(key))
                    say(challenge_line(key))
                except core.Failed as exc:
                    if exc.args and str(exc.args[0]).startswith("I ran out of time"):
                        raise
                    note_platform(key, True, "signed in; %s" % _clip(exc, 120))
                    say("%s: %s" % (PLATFORMS[key]["name"], core.failure_line(exc)))
        if down is not None:
            raise down
        for job in [j for j in read_book() if j.get("status") == "awarded"][:1]:
            do_work(job, say, s)
    except core.Aborted as stop:
        switch(False, "ctrl+m")
        say("Ctrl+M - you took back control while %s. Revenue Mode is off." % stop.args[0])
    except ModelDown as exc:
        wait = closer.backoff_s(exc)
        _hold_until = time.time() + wait
        say("held until the model answers again%s: %s" % (
            " (not asking for %d min)" % round(wait / 60) if wait >= 60 else "", _clip(exc, 160)))
    except core.Failed as exc:
        say(core.failure_line(exc))
    except OSError as exc:
        say("stopped this pass: %s" % exc)
    return notes


# ------------------------------------------------------------------------------ the employer's word

_START = re.compile(r"^(?:please\s+)?(?:(?:can|could|would)\s+you\s+)?(?:be|get|go|stay)\s+in(?:to)?"
                    r"\s+(?:your\s+|the\s+)?revenue\s+mode\b|^(?:please\s+)?(?:start|enter|begin|"
                    r"turn\s+on|switch\s+on|switch\s+to|go\s+(?:in)?to|resume|activate)\s+(?:your\s+|"
                    r"the\s+)?revenue\s+mode\b|^revenue\s+mode\s+(?:on|start|chalu|shuru)\b", re.I)
_STOP = re.compile(r"\b(?:stop|exit|leave|end|pause|halt|quit|turn\s+off|switch\s+off|kill|"
                   r"get\s+out\s+of)\s+(?:your\s+|the\s+)?revenue\s+mode\b|^revenue\s+mode\s+"
                   r"(?:off|stop|band|bandh|ruko|roko)\b", re.I)
_REPORT = re.compile(r"\brevenue\s+(?:mode\s+)?(?:update|report|status)\b|\bhow(?:'s|\s+is)\s+"
                     r"(?:the\s+)?revenue\s+mode\b|\bwhat\s+(?:has|did)\s+revenue\s+mode\b|"
                     r"\brevenue\s+(?:ka|ki)\s+update\b|\bfreelance\s+(?:update|report|status)\b",
                     re.I)
_SUBMIT = re.compile(r"^(?:please\s+|ok(?:ay)?,?\s+|yes,?\s+)?(?:submit|send|deliver)\s+(?:it|that|"
                     r"the\s+work|this|(?P<id>R-?\d{1,5}))(?:\s+(?:to\s+the\s+client|now))?[.!]?$",
                     re.I)


def parse_request(sentence):
    """{"action": start|stop|report|submit, ...} for the employer's sentence, or None. A bare
    "submit it" is Revenue Mode's only while a job is ready for review - otherwise it is not ours."""
    text = " ".join(str(sentence or "").split()).strip()
    if not text:
        return None
    if _STOP.search(text):
        return {"action": "stop"}
    if _START.search(text.rstrip("?.! ")):
        return {"action": "start"}
    if _REPORT.search(text):
        return {"action": "report"}
    m = _SUBMIT.match(text)
    if m:
        if m.group("id"):
            return {"action": "submit", "job": "R-%04d" % int(re.sub(r"\D", "", m.group("id")))}
        ready = [j for j in read_book() if j.get("status") == "ready"]
        if not ready:
            return None
        return {"action": "submit", "job": ready[0]["id"] if len(ready) == 1 else "",
                "choices": [j["id"] for j in ready]}
    return None


def and_list(names):
    names = list(names)
    return ", ".join(names[:-1]) + " and " + names[-1] if len(names) > 1 else "".join(names)


def describe_start(params):
    s, _problems = settings()
    names = [PLATFORMS[p]["name"] for p in s["platforms"]]
    n = int(params.get("bids") or 0)
    return ("look for small fixed-price jobs on %s that your own profile says you can do, and bid "
            "on up to %d a day, on my own; when one is awarded I'll do the work and stop at "
            "\"ready for your review\"" % (and_list(names), n))


def describe_submit(params):
    job = find_job(str(params.get("job") or ""))
    if not job:
        return ""
    files = deliverables(job)
    return "send %s (%s) to the client on %s - %s, with the note in DELIVERY-NOTE.txt" % (
        job["title"], job["id"], PLATFORMS[job["platform"]]["name"],
        ", ".join(os.path.basename(p) for p, _ in files) or "no files")


# ------------------------------------------------------------------------------ report and record

def _ago(start, end):
    try:
        secs = (datetime.datetime.fromisoformat(end) -
                datetime.datetime.fromisoformat(start)).total_seconds()
    except (TypeError, ValueError):
        return ""
    hours, rest = divmod(int(secs), 3600)
    if hours >= 1:
        return "%d hour%s" % (hours + (1 if rest >= 1800 else 0), "" if hours == 1 and
                                                                     rest < 1800 else "s")
    return "%d minutes" % max(1, rest // 60)


def recorded(job_id, path=None):
    """The Ledger entry already holding this job's earning, or None - read from ledger.json
    itself, so there is no second record of what was earned."""
    entries, _bad = ledger.read_book(path)
    return next((e for e in entries if not e.get("void") and "%s:" % job_id in
                 str(e.get("note") or "")), None)


def ledger_card(today=None):
    """The add_ledger_entry params for the first paid job not yet in the Ledger, or None. The card
    is the Ledger's own; this only fills it in from what the platform showed."""
    for job in read_book():
        paid = job.get("paid") or {}
        if job.get("status") != "paid" or not paid or recorded(job["id"]):
            continue
        if paid.get("currency") not in ledger.CURRENCIES:
            continue
        proof = paid.get("proof") or None
        if proof and ledger.check_proof(proof)[1]:
            proof = None
        params = {"book": "boss", "kind": "income", "amount_paise": int(paid["amount"]),
                  "currency": paid["currency"], "category": "freelance", "on": paid["on"],
                  "proof": proof or "none",
                  "note": "%s: %s on %s (Revenue Mode)" % (job["id"], _clip(job["title"], 120),
                                                         PLATFORMS[job["platform"]]["name"])}
        params["entry"] = ledger.describe(params["book"], params["kind"], params["amount_paise"],
                                          params["category"], params["currency"], params["on"],
                                          proof)
        return params
    return None


def finished_line(job, boss="sir"):
    paid = job.get("paid") or {}
    took = _ago((job.get("awardedAt") or (job.get("work") or {}).get("startedAt")),
                job.get("submittedAt") or "")
    money = ledger.money(paid.get("amount", 0), paid.get("currency", "USD")) \
        if paid.get("currency") in ledger.CURRENCIES else str(paid.get("amount"))
    return "%s, I finished %s - %s%s." % (boss.capitalize(), job["title"],
                                          (took + ", ") if took else "", money)


def report(day=None, boss="sir"):
    """THE ON-ASK REPORT, from the book, the log and the state - never from memory."""
    day = day or _today()
    try:
        rows = read_log()
        book = read_book()
    except OSError as exc:
        return str(exc) + "."
    state = read_state()
    s, _problems = settings()
    parts = []
    for job in [j for j in book if j.get("status") == "paid" and not recorded(j["id"])]:
        parts.append(finished_line(job, boss))
    today = [r for r in rows if str(r.get("at"))[:10] == day]
    bids = [r for r in today if r.get("kind") == "bid"]
    read_today = [j for j in book if str(j.get("seenAt"))[:10] == day]
    skipped = [j for j in read_today if j.get("status") == "skipped"]
    if read_today or bids:
        line = "Today, %s: I looked at %d job%s and skipped %d" % (
            boss, len(read_today), "" if len(read_today) == 1 else "s", len(skipped))
        placed = [r for r in bids if r.get("status") == "bid"]
        line += "; %d bid%s placed" % (len(placed), "" if len(placed) == 1 else "s")
        line += (" (%s)" % "; ".join("%s on %s, %s" % (
            _clip(r.get("title"), 50), PLATFORMS[r["platform"]]["name"],
            ledger.money(r["amount"], r["currency"]) if r.get("currency") in ledger.CURRENCIES
            else r.get("amount")) for r in placed[:3])) if placed else ""
        failed = [r for r in bids if r.get("status") != "bid"]
        if failed:
            line += "; %d bid%s did not go cleanly: %s" % (
                len(failed), "" if len(failed) == 1 else "s", "; ".join(
                    "%s - %s" % (_clip(r.get("title"), 40), _clip(r.get("error") or
                                                                  r.get("confirm") or
                                                                  r.get("status"), 80))
                    for r in failed[:3]))
        parts.append(line + ".")
        if skipped:
            parts.append("Most recent skip: %s - %s." % (_clip(skipped[-1]["title"], 60),
                                                         _clip((skipped[-1].get("why") or ["?"])[0],
                                                               110)))
    else:
        parts.append("No jobs read today, %s." % boss)
    waiting = [j for j in book if j.get("status") in SAY_STATUS and j.get("status") != "paid"]
    for j in [x for x in waiting if x["status"] == "ready"]:
        parts.append("%s (%s) is READY FOR YOUR REVIEW in %s - say \"submit it\" when you're "
                     "happy." % (j["title"], j["id"], (j.get("work") or {}).get("dir")))
    others = [j for j in waiting if j["status"] not in ("ready", "bid")]
    if others:
        parts.append("Also: %s." % "; ".join("%s (%s) %s" % (_clip(j["title"], 50), j["id"],
                                                             SAY_STATUS[j["status"]])
                                             for j in others[:4]))
    open_bids = [j for j in waiting if j["status"] == "bid"]
    if open_bids:
        parts.append("%d bid%s open, waiting on clients." % (len(open_bids), "" if
                                                            len(open_bids) == 1 else "s"))
    plat = state.get("platforms") or {}
    down = [v["line"] for k, v in plat.items() if k in s["platforms"] and not v.get("ok")]
    parts.extend(down)
    parts.append("Revenue Mode is %s." % ("on" if state.get("on") else "off"))
    return " ".join(parts)


# ------------------------------------------------------------------------------ the daemon

class Revenue:
    """The Closer's shape: its own thread, acting only while revenue-state.json says on."""

    def __init__(self):
        self._lock = threading.Lock()
        self._thread = None
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._last = {"at": 0.0, "notes": [], "busy": False}

    def state(self):
        with self._lock:
            last = dict(self._last)
        return {"on": bool(read_state().get("on")), "busy": last["busy"],
                "lastTickAgoS": int(time.time() - last["at"]) if last["at"] else None,
                "lastNotes": last["notes"][-8:]}

    def poke(self):
        with self._lock:
            self._last["at"] = 0.0
        self._wake.set()

    def _loop(self):
        while not self._stop.is_set():
            self._wake.wait(POLL_S)
            self._wake.clear()
            if self._stop.is_set() or not read_state().get("on"):
                continue
            s, _problems = settings()
            with self._lock:
                due = (time.time() - self._last["at"] >= s["tickSeconds"]
                       and time.time() >= _hold_until)
                if due:
                    self._last["busy"] = True
            if not due:
                continue
            try:
                notes = tick(note=lambda line: sys.stderr.write("  revenue: %s\n" % line))
            except Exception as exc:                           # noqa: BLE001
                notes = ["the pass threw (%s: %s)" % (type(exc).__name__, str(exc)[:120])]
                sys.stderr.write("  revenue: %s\n" % notes[0])
            with self._lock:
                self._last = {"at": time.time(), "notes": notes, "busy": False}

    def start(self):
        if self._thread is not None:
            return False
        self._thread = threading.Thread(target=self._loop, name="revenue-tick", daemon=True)
        self._thread.start()
        return True

    def stop(self):
        self._stop.set()
        self._wake.set()


MANAGER = Revenue()


def _main(argv):                                               # pragma: no cover
    if argv[:1] == ["report"]:
        print(report())
        return 0
    if argv[:1] == ["log"]:
        for r in read_log()[-int(argv[1] if len(argv) > 1 else 15):]:
            print("%s %s %-8s %-16s %-6s %s" % (r["id"], r["at"], r.get("kind"), r.get("status"),
                                                r.get("jobId"), _clip(r.get("title") or
                                                                      r.get("why"), 80)))
        return 0
    if argv[:1] == ["tick"]:
        import server
        configure(chat=lambda m: server.call_groq(server.load_config()[0], m),
                  work_chat=lambda m: server.call_groq(server.load_config()[0], m,
                                                       max_tokens=WORK_TOKENS),
                  config=lambda: server.load_config()[0])
        for line in tick():
            print(line)
        return 0
    s, problems = settings()
    state = read_state()
    print("Revenue Mode is %s. %s" % ("on" if state.get("on") else "off",
                                      "; ".join(problems) or "Settings are fine."))
    for k, v in (state.get("platforms") or {}).items():
        print("  %-11s %s  %s" % (k, "ok " if v.get("ok") else "NO ", v.get("line")))
    counts = {}
    for j in read_book():
        counts[j["status"]] = counts.get(j["status"], 0) + 1
    print("Book: %s. Log: %d rows." % (", ".join("%d %s" % (n, k) for k, n in counts.items())
                                       or "empty", len(read_log())))
    return 0


# The work's answer ceiling: a 2-4 hour deliverable does not fit the butler's 400 tokens.
WORK_TOKENS = 6000


if __name__ == "__main__":                                     # pragma: no cover
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:                                          # noqa: BLE001
        pass
    sys.exit(_main(sys.argv[1:]))
