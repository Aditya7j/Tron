"""THE HUNTER, phase 1. Finds businesses in public, open listings, reads each one's own website for
a public way to reach it, and keeps what it found in the leads book. It sends nothing to anyone.

THE TWO SOURCES, and why they are these and not the ones the brief first named
    "listings"  OPEN BUSINESS LISTINGS - OpenStreetMap (through Nominatim) for places with a
                door: dentists, clinics, shops, offices; and Wikidata for companies with a
                headquarters and an industry: "SaaS startups in Bangalore working on fintech".
                Both are open data whose operators publish a usage policy that allows an
                identified, paced client (Nominatim: one request a second, a real User-Agent).
    "web"       THE BUSINESS'S OWN WEBSITE - its home page and its contact page, read for an
                email or a phone number the business itself published, and the contact page's
                address as the form link. robots.txt is read first and obeyed.
    Measured 2026-10-14, from this machine, with this file's honest User-Agent:
      - Google Maps and Google Search are NOT here. Google's terms forbid automated collection
        from either, and neither answers a client that says what it is. The legitimate Maps
        door is the Places API, which needs a key with billing - a decision for the boss, not
        for this file. See README "The Hunter".
      - DuckDuckGo answered both test queries with HTTP 202 and a challenge page. search.py
        gets results only by presenting a Chrome User-Agent; the Hunter will not, so it has
        no general web search, and says so rather than borrowing that disguise.
      - search.sapti.me (config.json's search_url) failed TLS: its certificate has expired.
      - Overpass answered 504 and then timed out, so it is not a source this file leans on.
      - Nominatim: "dentists in Pune", 50 rows a page, 7 with a phone and 6 with a website.
      - Wikidata: 191 Bangalore-headquartered companies with a website and an industry, 2.6 s.
    One description goes to BOTH sources every time - "dentists in Pune" and "fintech startups
    in Bangalore" take the same path. Whichever source knows the kind of thing answers.

THE BOOK - leads.json, the house's own convention. ledger.py, jobs.py and focus.py all keep a
JSON file written whole through a .tmp and os.replace; there is no SQLite or CSV anywhere in
this codebase, so a third storage convention was not invented for this one.

A LEAD
    id          "H-0001", in the order written, never reused
    name        as the listing names it
    category    what the listing calls it ("dentist", "fintech | software industry")
    niche       what was asked for ("dentists"), so a hunt's rows can be found again
    location    an address or a headquarters, as the listing gives it
    city        where was asked
    website     the business's own site, or null. A social-network page is not one.
    email       or null - ONLY an address seen on a page, never composed. emailFrom is the
                page it was seen on.
    phone       or null - ONLY a number published as one (a tel: link, a listing's phone tag,
                or text labelled phone/call/mobile). phoneFrom says where.
    contactPage the site's own contact page (the form link), or null
    source      "listings", "web" or "listings+web": which of the two found what is in the row
    via         the backends behind that: openstreetmap, wikidata, website
    ref         the listing's own id - "osm:node/123", "wikidata:Q123"
    foundAt     the date it was first found (YYYY-MM-DD); lastSeen the last hunt that found it
    status      new / contacted / replied / closed / dead. THE HUNTER ONLY EVER WRITES "new":
                add_lead() takes no status at all, and a merge never touches one. Changing it
                is the Closer's, later.

NEVER INVENTED. A lead with no email, no phone and no contact page is SKIPPED and counted, never
guessed at. An address hidden behind Cloudflare's email protection is left hidden: that is the
site saying it does not want to be harvested, and decoding it would be overruling the site.

ONE BUSINESS, ONE ROW. Two finds are the same business when they share a website host, a phone
number (its last ten digits), an email, a listing id, or the same name in the same city. A second
find fills only the blanks of the first row and moves lastSeen; it never becomes a second row.

    python hunter.py                         what the book holds
    python hunter.py list [N]                the last N leads
    python hunter.py hunt "find 5 dentists in Pune"     a real hunt, from a terminal
"""

import datetime
import html
import json
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
from html.parser import HTMLParser

HERE = os.path.dirname(os.path.abspath(__file__))
# A test seam, like ledger.py's: test_hunter.py points a tool script at a temporary book.
LEADS_PATH = os.environ.get("TRONE_LEADS_PATH") or os.path.join(HERE, "leads.json")

STATUSES = ("new", "contacted", "replied", "closed", "dead")
SOURCES = ("listings", "web", "listings+web")
DEFAULT_COUNT, MAX_COUNT = 10, 25
NAME_MAX, FIELD_MAX = 160, 300

# WHO IS ASKING, said plainly. Not a browser's string: every request this file makes says it is
# a program, and a site that refuses programs is refused back - skipped, never retried.
UA = "TroneHunter/1.0 (personal lead-research assistant; paced, one request at a time)"
NOMINATIM = "https://nominatim.openstreetmap.org/search"
WIKIDATA_API = "https://www.wikidata.org/w/api.php"
WIKIDATA_SPARQL = "https://query.wikidata.org/sparql"

# The pace. Nominatim's policy is an absolute maximum of one request a second; the same gap is
# kept for any one website, and a small gap between any two requests at all.
HOST_GAP_S = {"nominatim.openstreetmap.org": 1.2, "query.wikidata.org": 2.0,
              "www.wikidata.org": 1.0}
SITE_GAP_S, ANY_GAP_S = 1.0, 0.3
FETCH_TIMEOUT_S = 10.0
PAGE_MAX_BYTES = 1_500_000
# The registry kills the hand at timeout_s (180). Finishing inside this means a slow hunt is
# reported in its own words, with what it found, never as a bare timeout.
BUDGET_S = 165.0
NOMINATIM_PAGES = 3                       # 50 a page; a fourth page is a bulk download
REFUSED = (403, 429, 503, 509)
CHALLENGE_MARKERS = ("cf-chl", "just a moment...", "captcha", "attention required",
                     "verify you are human", "unusual traffic", "access denied")

_lock = threading.Lock()


# ------------------------------------------------------------------------------ the sentence

_NUM_WORDS = {"five": 5, "ten": 10, "fifteen": 15, "twenty": 20, "twenty five": 25,
              "twenty-five": 25, "thirty": 30, "forty": 40, "fifty": 50, "a dozen": 12,
              "dozen": 12, "a few": 5, "few": 5, "some": DEFAULT_COUNT}
_COUNT = r"(?P<count>\d{1,3}|%s)" % "|".join(sorted((re.escape(w) for w in _NUM_WORDS),
                                                   key=len, reverse=True))
_VERB = (r"(?:find|get|hunt(?:\s+for|\s+down)?|search\s+for|look\s+for|dig\s+up|scout|"
         r"source|pull\s+(?:up\s+)?|track\s+down)")
_WHERE = r"(?P<where>[a-z][a-z .'-]{1,40}?)"
_TAIL = (r"(?P<tail>\s+(?:working\s+(?:on|in)|that|who|which|focused\s+on|focusing\s+on|"
         r"doing|building|specialis\w+\s+in|specializ\w+\s+in|into)\b.*?)?")
_EN = re.compile(r"^(?:please\s+)?(?:(?:can|could|would)\s+you\s+)?%s\s+(?:me\s+|us\s+)?"
                 r"(?:(?:about|around|some)\s+)?(?:%s\s+)?(?:(?:new\s+)?leads?\s*"
                 r"(?:for|on|among|of|:|-)\s*)?(?P<what>.+?)\s+(?:in|at|around|near|from|"
                 r"based\s+in)\s+%s%s(?:\s+for\s+me)?\s*(?:please)?[?.!]*$"
                 % (_VERB, _COUNT, _WHERE, _TAIL), re.I)
_HI = re.compile(r"^%s\s+(?:mein|me|main)\s+(?:%s\s+)?(?P<what>.+?)\s+(?:dhundo|dhoondo|"
                 r"dhundho|dhoondho|dhund\s+do|dhoondh\s+do|dhundh\s+do|nikalo|dhundh\s+ke\s+"
                 r"do)\b(?P<tail>)[?.!]*$" % (_WHERE, _COUNT), re.I)
# Words that make "find me the best X in Y" a recommendation rather than a hunt - unless a count
# or the word "leads" says otherwise.
_ADVICE = re.compile(r"\b(?:best|good|great|cheap\w*|nearest|closest|famous|popular|"
                     r"recommended|top[\s-]?rated)\b", re.I)
_BUSINESS_NOUNS = re.compile(r"\b(?:compan(?:y|ies)|startups?|firms?|businesses|agenc(?:y|ies)|"
                             r"studios?|clinics?|shops?|stores?|restaurants?|cafes?|salons?|"
                             r"gyms?|hotels?|schools?|institutes?|consultants?|consultancies|"
                             r"vendors?|suppliers?|manufacturers?|distributors?|dealers?|"
                             r"brands?|labs?|practices|offices?|outlets?|"
                             r"\w{3,}ists|\w{3,}ers|\w{3,}ors)\b", re.I)


def _count(word):
    word = str(word or "").strip().lower()
    if not word:
        return None
    return int(word) if word.isdigit() else _NUM_WORDS.get(word)


def parse_request(sentence):
    """{"what", "where", "count", "asked"} for an explicit ask to find businesses, or None.

    "find me 20 dentists in Pune"                       -> dentists / Pune / 20
    "find SaaS startups in Bangalore working on fintech" -> SaaS startups working on fintech /
                                                           Bangalore / 10
    "Pune mein 15 dentists dhundo"                      -> dentists / Pune / 15
    "find me the best biryani in Hyderabad"             -> None: a question, not a hunt
    `asked` is the count as said, before it is held to MAX_COUNT."""
    text = re.sub(r"\s+", " ", str(sentence or "")).strip().rstrip(".!?")
    m = _EN.match(text) or _HI.match(text)
    if not m:
        return None
    what = m.group("what").strip(" ,:-")
    tail = (m.group("tail") or "").strip()
    where = re.sub(r"\s+(?:please|for\s+me)$", "", m.group("where").strip(" ,.-"), flags=re.I)
    what = re.sub(r"^(?:the|some|a\s+few|a\s+list\s+of|list\s+of)\s+", "", what, flags=re.I)
    if not what or not where or len(what) > 80:
        return None
    asked = _count(m.group("count"))
    leads_word = bool(re.search(r"\bleads?\b", text, re.I))
    hunt_verb = bool(re.match(r"^(?:please\s+)?hunt\b", text, re.I))
    if asked is None and not leads_word and not hunt_verb:
        # No number and no "leads": it has to name businesses, in the plural, and not ask
        # for the best one - "find me a good dentist in Pune" is a question for the web.
        if _ADVICE.search(what) or not _BUSINESS_NOUNS.search(what):
            return None
        if not re.search(r"(?:s|ies|ple)\b", what.split()[-1], re.I):
            return None
    if re.search(r"\b(?:job|jobs|flat|flats|apartment|house|room|rooms|ticket|tickets|"
                 r"flight|flights|movie|movies|song|songs|video|videos|news|weather)\b",
                 what, re.I):
        return None                      # a hunt is for businesses, never for these
    if tail:
        what = "%s %s" % (what, tail)
    count = min(max(asked or DEFAULT_COUNT, 1), MAX_COUNT)
    return {"what": what[:80], "where": where.title() if where.islower() else where,
            "count": count, "asked": asked or count}


def describe(params):
    """The {plan} blank on the card: "20 dentists in Pune". The same words the run's line uses."""
    what = str(params.get("what") or "").strip()
    where = str(params.get("where") or "").strip()
    try:
        count = int(params.get("count") or DEFAULT_COUNT)
    except (TypeError, ValueError):
        count = DEFAULT_COUNT
    if not what or not where:
        return ""
    try:
        asked = int(params.get("asked") or count)
    except (TypeError, ValueError):
        asked = count
    plan = "%d %s in %s" % (count, what, where)
    if asked > count:
        plan += " (you asked for %d; %d is the most one hunt chases)" % (asked, count)
    return plan


# ------------------------------------------------------------------------------ the book

def _norm_name(text):
    text = re.sub(r"[^a-z0-9 ]+", " ", str(text or "").lower())
    words = [w for w in text.split() if w not in ("the", "pvt", "private", "ltd", "limited",
                                                  "llp", "inc", "co", "india")]
    return "".join(words)


SHARED_HOSTS = ("business.site", "wixsite.com", "sites.google.com", "blogspot.com",
                "wordpress.com", "github.io", "godaddysites.com", "weebly.com", "webflow.io",
                "netlify.app", "vercel.app", "carrd.co", "linktr.ee")
# Not a business's own site. Social networks are the next phase's, with their own compliance
# approach; directories are other people's listings, under terms of their own.
NOT_OWN_SITE = ("facebook.com", "fb.com", "instagram.com", "linkedin.com", "twitter.com",
                "x.com", "wa.me", "whatsapp.com", "youtube.com", "t.me", "justdial.com",
                "practo.com", "sulekha.com", "indiamart.com", "tradeindia.com", "zomato.com",
                "swiggy.com", "google.com", "goo.gl", "maps.app.goo.gl", "g.page",
                "crunchbase.com", "tracxn.com", "glassdoor.com", "ambitionbox.com",
                "wikipedia.org", "lybrate.com", "clinicspots.com", "magicpin.in")


def _host(url):
    try:
        host = urllib.parse.urlsplit(str(url or "")).hostname or ""
    except ValueError:
        return ""
    return host.lower()[4:] if host.lower().startswith("www.") else host.lower()


def own_site(url):
    """The URL if it is a business's own website, else None. Scheme added when it is missing."""
    url = str(url or "").strip().split(";")[0].strip()
    if not url:
        return None
    if not re.match(r"^https?://", url, re.I):
        url = "http://" + url
    host = _host(url)
    if not host or "." not in host:
        return None
    if any(host == d or host.endswith("." + d) for d in NOT_OWN_SITE):
        return None
    # A PAGE DEEP INSIDE SOMEBODY ELSE'S SITE IS A LISTING, not a website. Measured on the first
    # live hunt: a Pune clinic's OSM "website" was apneareamein.com/Magarpattacity-Pune/Doctor -
    # Dentist in Magarpatta City.php - a directory's page about it. A business's own address is
    # its root, or one level down; a shared host (sites.google.com/x) is one level by design.
    depth = len([p for p in urllib.parse.urlsplit(url).path.split("/") if p])
    if depth > (2 if any(host.endswith(d) for d in SHARED_HOSTS) else 1):
        return None
    return url


def site_key(url):
    host = _host(url)
    if not host:
        return None
    if any(host == d or host.endswith("." + d) for d in SHARED_HOSTS):
        # Two segments, not one: every sites.google.com/view/<name> shares "view", and one
        # segment would make every business on it the same business.
        path = "/".join(urllib.parse.urlsplit(url).path.strip("/").split("/")[:2]).lower()
        return "web:%s/%s" % (host, path)
    return "web:" + host


def phone_digits(phone):
    digits = re.sub(r"\D", "", str(phone or ""))
    return digits[-10:] if len(digits) >= 10 else None


def keys(lead):
    """Every key that names this business. Two leads sharing any one are the same business."""
    out = set()
    if lead.get("website"):
        k = site_key(lead["website"])
        if k:
            out.add(k)
    if phone_digits(lead.get("phone")):
        out.add("tel:" + phone_digits(lead["phone"]))
    if lead.get("email"):
        out.add("mail:" + str(lead["email"]).lower())
    if lead.get("ref"):
        out.add("ref:" + str(lead["ref"]).lower())
    name = _norm_name(lead.get("name"))
    if name:
        out.add("name:%s|%s" % (name, _norm_name(lead.get("city"))))
    return out


def read_book(path=None):
    """(leads, unreadable): the rows that are leads, and how many rows are not (-1: no file
    could be read at all). An unreadable row is never repaired and never dropped on a write."""
    try:
        with open(path or LEADS_PATH, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except FileNotFoundError:
        return [], 0
    except (OSError, ValueError):
        return [], -1
    rows = data.get("leads") if isinstance(data, dict) else None
    rows = rows if isinstance(rows, list) else []
    good = [r for r in rows if _well_formed(r)]
    return good, len(rows) - len(good)


def _well_formed(r):
    return (isinstance(r, dict) and re.fullmatch(r"H-\d+", str(r.get("id") or ""))
            and str(r.get("name") or "").strip() and r.get("status") in STATUSES
            and r.get("source") in SOURCES)


def _raw_rows(path=None):
    try:
        with open(path or LEADS_PATH, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except FileNotFoundError:
        return []
    rows = data.get("leads") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        raise ValueError("the leads file holds no list of leads")
    return rows


def _write_book(rows, path=None):
    path = path or LEADS_PATH
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump({"version": 1, "leads": rows,
                   "updated": datetime.datetime.now().isoformat(timespec="seconds"),
                   "note": "Leads the Hunter found in public listings and on the businesses' "
                           "own sites. Every email and phone was seen on the page named "
                           "beside it. The Hunter writes status 'new' and nothing else."},
                  fh, indent=1, ensure_ascii=False)
        fh.write("\n")
    os.replace(tmp, path)


def _clip(value, limit=FIELD_MAX):
    value = " ".join(str(value or "").split())[:limit]
    return value or None


def _source(via):
    listed = bool(set(via) & {"openstreetmap", "wikidata"})
    web = "website" in via
    return "listings+web" if listed and web else "web" if web else "listings"


def add_lead(found, niche, city, now=None, path=None):
    """("added" | "merged", row) - or (None, error). One business, one row: a find that shares
    a key with a row already in the book fills that row's blanks and moves its lastSeen, and
    never touches its status. There is no status argument: a new row is "new", always."""
    name = _clip(found.get("name"), NAME_MAX)
    if not name:
        return None, "a lead needs a name"
    now = now or datetime.datetime.now()
    lead = {"name": name, "category": _clip(found.get("category")),
            "niche": _clip(niche, 80), "location": _clip(found.get("location")),
            "city": _clip(city, 80), "website": _clip(found.get("website")),
            "email": _clip(found.get("email"), 120), "emailFrom": _clip(found.get("emailFrom")),
            "phone": _clip(found.get("phone"), 40), "phoneFrom": _clip(found.get("phoneFrom")),
            "contactPage": _clip(found.get("contactPage")), "ref": _clip(found.get("ref"), 80)}
    via = sorted(set(found.get("via") or []))
    with _lock:
        rows = _raw_rows(path)
        mine = keys(lead)
        hit = next((r for r in rows if _well_formed(r) and keys(r) & mine), None)
        if hit is not None:
            for field, value in lead.items():
                if value and not hit.get(field):
                    hit[field] = value
            hit["via"] = sorted(set(hit.get("via") or []) | set(via))
            hit["source"] = _source(hit["via"])
            hit["lastSeen"] = now.date().isoformat()
            _write_book(rows, path)
            return "merged", dict(hit)
        taken = [int(r["id"][2:]) for r in rows if isinstance(r, dict)
                 and re.fullmatch(r"H-\d+", str(r.get("id") or ""))]
        row = dict({"id": "H-%04d" % (max(taken, default=0) + 1)}, **lead)
        row.update(source=_source(via), via=via, foundAt=now.date().isoformat(),
                   lastSeen=now.date().isoformat(), status="new")
        _write_book(rows + [row], path)
        return "added", dict(row)


def known(found, city, path=None):
    """The row already in the book for this find, or None - checked BEFORE a site is read, so
    a business found last week costs no second visit to its website."""
    probe = dict(found, city=city)
    mine = keys(probe)
    leads, _bad = read_book(path)
    return next((r for r in leads if keys(r) & mine), None)


def summary(path=None):
    leads, bad = read_book(path)
    if bad < 0:
        return "The leads book could not be read at all."
    if not leads:
        return "The leads book is empty."
    by_status = {s: sum(1 for r in leads if r["status"] == s) for s in STATUSES}
    niches = {}
    for r in leads:
        niches[(r.get("niche") or "?", r.get("city") or "?")] = niches.get(
            (r.get("niche") or "?", r.get("city") or "?"), 0) + 1
    line = "%d lead%s in the book (%s); %d with an email, %d with a phone. %s." % (
        len(leads), "" if len(leads) == 1 else "s",
        ", ".join("%d %s" % (n, s) for s, n in by_status.items() if n),
        sum(1 for r in leads if r.get("email")), sum(1 for r in leads if r.get("phone")),
        "; ".join("%s in %s: %d" % (k[0], k[1], n) for k, n in sorted(niches.items())))
    return line + (" %d row(s) could not be read." % bad if bad else "")


# ------------------------------------------------------------------------------ the wire

class Stopped(Exception):
    """The budget is spent: stop asking anybody anything."""


class Wire:
    """Every request the hunt makes, through one door: paced per host, identified honestly,
    capped in size and in time. It remembers which sources have refused, and never asks one of
    them again in this run."""

    def __init__(self, budget_s=BUDGET_S, clock=time.monotonic, sleep=time.sleep):
        self.clock, self.sleep = clock, sleep
        self.deadline = clock() + budget_s
        self.last_any, self.last_host = 0.0, {}
        self.requests = 0
        self.refused = {}                 # source label -> the reason, said once

    def left(self):
        return self.deadline - self.clock()

    def get(self, url, accept="text/html,application/xhtml+xml;q=0.9,*/*;q=0.5",
            timeout=FETCH_TIMEOUT_S, host_gap=None):
        """(status, final_url, text, content_type). status None for a network failure."""
        host = urllib.parse.urlsplit(url).hostname or ""
        gap = host_gap if host_gap is not None else HOST_GAP_S.get(host, SITE_GAP_S)
        wait = max(self.last_any + ANY_GAP_S, self.last_host.get(host, 0.0) + gap) - self.clock()
        if self.left() < max(wait, 0) + 2.0:
            raise Stopped()
        if wait > 0:
            self.sleep(wait)
        timeout = max(1.0, min(timeout, self.left() - 1.0))
        self.requests += 1
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": accept,
                                                   "Accept-Language": "en"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                ctype = resp.headers.get("Content-Type", "")
                raw = resp.read(PAGE_MAX_BYTES)
                charset = resp.headers.get_content_charset() or "utf-8"
                return resp.status, resp.geturl(), raw.decode(charset, "replace"), ctype
        except urllib.error.HTTPError as exc:
            try:
                body = exc.read(20000).decode("utf-8", "replace")
            except Exception:                                  # noqa: BLE001
                body = ""
            return exc.code, url, body, ""
        except Exception:                                      # noqa: BLE001 - timeouts, TLS, DNS
            return None, url, "", ""
        finally:
            now = self.clock()
            self.last_any = now
            self.last_host[host] = now


def _refusal(status, text):
    """The reason a response is a refusal, or ""."""
    if status in REFUSED:
        return "HTTP %d" % status
    low = (text or "")[:20000].lower()
    if status == 200 and any(m in low for m in CHALLENGE_MARKERS) and len(low) < 20000:
        return "a challenge page"
    return ""


# ------------------------------------------------------------------------------ listings

_POI = ("amenity", "shop", "office", "craft", "healthcare", "tourism", "leisure", "club")


def _first(tags, *names):
    for n in names:
        value = str(tags.get(n) or "").strip()
        if value:
            return value.split(";")[0].strip()
    return ""


def _osm_row(r, city):
    tags = r.get("extratags") or {}
    addr = r.get("address") or {}
    parts = [addr.get(k) for k in ("house_number", "road", "neighbourhood", "suburb",
                                   "city_district", "city", "town", "village")]
    location = ", ".join(dict.fromkeys(p for p in parts if p)) or (r.get("display_name") or "")
    phone = _first(tags, "phone", "contact:phone", "contact:mobile", "mobile")
    email = _first(tags, "email", "contact:email")
    ref = "osm:%s/%s" % (r.get("osm_type"), r.get("osm_id"))
    return {"name": r.get("name") or "", "category": str(r.get("type") or "").replace("_", " "),
            "location": location[:FIELD_MAX], "city": city,
            "website": own_site(_first(tags, "website", "contact:website", "url")),
            "phone": phone or None, "phoneFrom": "openstreetmap %s" % ref if phone else None,
            "email": email if _EMAIL_FULL.match(email or "") else None,
            "emailFrom": "openstreetmap %s" % ref if _EMAIL_FULL.match(email or "") else None,
            "ref": ref, "via": ["openstreetmap"]}


def from_openstreetmap(wire, what, where, notes):
    """Places of this kind in this town, from Nominatim, a page of 50 at a time."""
    rows, seen = [], []
    head = re.split(r"\s+(?:working|that|who|which|focused|focusing|doing|building|"
                    r"speciali[sz]\w*|into)\b", what, maxsplit=1, flags=re.I)[0]
    for _page in range(NOMINATIM_PAGES):
        q = {"q": "%s in %s" % (head, where), "format": "jsonv2", "extratags": 1,
             "addressdetails": 1, "limit": 50}
        if seen:
            q["exclude_place_ids"] = ",".join(str(s) for s in seen)
        status, _url, text, _ct = wire.get(NOMINATIM + "?" + urllib.parse.urlencode(q),
                                           accept="application/json")
        why = _refusal(status, text)
        if why:
            wire.refused["openstreetmap"] = why
            notes.append("OpenStreetMap started refusing (%s), so I stopped asking it" % why)
            break
        if status != 200:
            notes.append("OpenStreetMap did not answer (%s)" % (status or "no connection"))
            break
        try:
            page = json.loads(text)
        except ValueError:
            break
        if not isinstance(page, list) or not page:
            break
        seen += [p.get("place_id") for p in page if p.get("place_id")]
        rows += [_osm_row(p, where) for p in page
                 if p.get("category") in _POI and str(p.get("name") or "").strip()]
        # EVERY PAGE, not "enough for the count". Measured: a second "5 dentists in Pune" after a
        # first hunt of 20 read page one only, found its every contactable clinic already in the
        # book, and wrote nothing - while pages two and three held new ones. Three requests is
        # the whole cost.
        if len(page) < 50:
            break
    return rows


# What a word in the request means when it is matched against Wikidata's own industry names.
_SYNONYMS = {
    "saas": ("software as a service", "saas", "software", "cloud computing"),
    # Not "banking" and not "financial services": measured, those two brought in Vijaya Bank and
    # Canara Bank for "fintech startups in Bangalore". Precision over reach - a lead list is read
    # by a person, and every wrong row is one they have to strike out.
    "software": ("software",), "fintech": ("fintech", "financial technology", "payment",
                                            "lending", "insurtech", "neobank", "wealthtech",
                                            "digital bank", "stockbrok"),
    "ai": ("artificial intelligence", "machine learning"), "edtech": ("educational technology",
                                                                       "edtech", "education"),
    "healthtech": ("health", "medical"), "ecommerce": ("e-commerce", "ecommerce", "retail"),
    "it": ("information technology", "it service", "it consulting"),
    "biotech": ("biotechnology", "pharmaceutical"), "pharma": ("pharmaceutical",),
    "logistics": ("logistics", "transport", "delivery"), "gaming": ("video game", "gaming"),
    "media": ("media", "entertainment"), "food": ("food", "restaurant"),
    "travel": ("travel", "tourism"), "edu": ("education",), "auto": ("automotive",),
    "realestate": ("real estate",), "proptech": ("real estate",), "agritech": ("agricultur",),
    "cybersecurity": ("security",), "security": ("security",), "hr": ("human resource",),
    "marketing": ("marketing", "advertising"), "aerospace": ("aerospace", "space"),
}
_GENERIC = set("""companies company startups startup firms firm businesses business enterprises
    enterprise ventures venture brands brand players player organisations organizations orgs
    working work works on in with that which who are is the a an of for and based focused
    focusing doing building build offering providing into around near new some small medium
    mid sized large local top best good india indian b2b b2c d2c early stage stages funded
    product products service services solutions solution space sector industry tech""".split())


# HOW a company sells, not WHAT it works on. Wikidata almost never records a business model, so a
# soft word only ranks - measured: "SaaS startups working on fintech" required both, and found one
# company in Bangalore where twenty fintech companies stood. A request of soft words alone ("SaaS
# companies in Pune") still filters by them, since then they are all there is.
_SOFT = {"saas", "software", "cloud", "tech", "technology", "platform", "app", "apps",
         "digital", "online", "internet"}
STARTUP_YEARS = 15


def topics(what):
    """The words in a request that a company must answer to: [(phrases, soft)], any one phrase
    of a topic will do. "B2B SaaS startups working on fintech" -> saas (soft), fintech."""
    out = []
    for word in re.findall(r"[a-z][a-z0-9+-]*", str(what or "").lower()):
        word = {"e-commerce": "ecommerce", "real-estate": "realestate"}.get(word, word)
        if word in _GENERIC or len(word) < 2:
            continue
        stem = word[:-1] if word.endswith("s") and len(word) > 4 else word
        phrases = _SYNONYMS.get(word) or _SYNONYMS.get(stem) or (stem,)
        if all(phrases != p for p, _soft in out):
            out.append((phrases, word in _SOFT or stem in _SOFT))
    return out


def matches(hay, wanted):
    """How many topics this text answers to, or None if it fails a topic it must answer to."""
    hay = " %s " % str(hay or "").lower()
    hits = [any(p in hay for p in phrases) for phrases, _soft in wanted]
    hard = [h for h, (_p, soft) in zip(hits, wanted) if not soft]
    if hard and not all(hard):
        return None
    if not hard and wanted and not any(hits):
        return None
    return sum(hits)


def _wikidata_place(wire, where, notes):
    q = {"action": "wbsearchentities", "search": where, "language": "en", "type": "item",
         "limit": 5, "format": "json"}
    status, _u, text, _c = wire.get(WIKIDATA_API + "?" + urllib.parse.urlencode(q),
                                    accept="application/json")
    why = _refusal(status, text)
    if why or status != 200:
        wire.refused["wikidata"] = why or "HTTP %s" % (status or "none")
        notes.append("Wikidata %s" % ("refused (%s)" % why if why else "did not answer"))
        return None
    try:
        hits = json.loads(text).get("search") or []
    except ValueError:
        return None
    for hit in hits:                    # a city, a district or a state - not a film named Pune
        desc = str(hit.get("description") or "").lower()
        if re.search(r"\b(?:city|capital|metropol|district|state|town|municipal|country|"
                     r"region|province|county|village|area|neighbourhood|suburb)\b", desc):
            return hit.get("id")
    return None


_SPARQL = """SELECT ?c ?cLabel ?cDescription ?site ?hqLabel (MIN(YEAR(?inc)) AS ?founded)
  (GROUP_CONCAT(DISTINCT ?indL; separator=" | ") AS ?inds) WHERE {
  ?c wdt:P159 ?hq . ?hq wdt:P131* wd:%s .
  ?c wdt:P856 ?site .
  FILTER NOT EXISTS { ?c wdt:P576 [] }
  FILTER NOT EXISTS { ?c wdt:P31 wd:Q5 }
  OPTIONAL { ?c wdt:P452 ?ind . ?ind rdfs:label ?indL . FILTER(LANG(?indL) = "en") }
  OPTIONAL { ?c schema:description ?cDescription . FILTER(LANG(?cDescription) = "en") }
  OPTIONAL { ?c wdt:P571 ?inc }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
} GROUP BY ?c ?cLabel ?cDescription ?site ?hqLabel LIMIT 3000"""


def from_wikidata(wire, what, where, notes, today=None):
    """Companies headquartered in this place whose name, description or industry answers to
    the request's topics (see matches), best match first. A request with no topic ("companies
    in Pune") takes them all. "startups" drops a company FOUNDED, by Wikidata's own record,
    more than STARTUP_YEARS ago; one with no founding year recorded is kept, not guessed at."""
    wanted = topics(what)
    startup = bool(re.search(r"\bstart-?ups?\b", str(what or ""), re.I))
    oldest = (today or datetime.date.today()).year - STARTUP_YEARS
    place = _wikidata_place(wire, where, notes)
    if not place:
        return []
    status, _u, text, _c = wire.get(
        WIKIDATA_SPARQL + "?" + urllib.parse.urlencode({"query": _SPARQL % place,
                                                        "format": "json"}),
        accept="application/sparql-results+json", timeout=40.0)
    why = _refusal(status, text)
    if why or status != 200:
        wire.refused["wikidata"] = why or "HTTP %s" % (status or "none")
        notes.append("Wikidata %s" % ("refused (%s)" % why if why else "did not answer"))
        return []
    try:
        rows = json.loads(text)["results"]["bindings"]
    except (ValueError, KeyError, TypeError):
        return []
    out, seen = [], set()
    for b in rows:
        val = {k: str((b.get(k) or {}).get("value") or "") for k in
               ("c", "cLabel", "cDescription", "site", "hqLabel", "inds", "founded")}
        qid = val["c"].rsplit("/", 1)[-1]
        if qid in seen or re.fullmatch(r"Q\d+", val["cLabel"]):
            continue                    # no English name: Wikidata echoes the id back
        score = matches("%s | %s | %s" % (val["cLabel"], val["cDescription"], val["inds"]),
                        wanted)
        if score is None:
            continue
        if startup and val["founded"].isdigit() and int(val["founded"]) < oldest:
            continue
        site = own_site(val["site"])
        if not site:
            continue
        seen.add(qid)
        out.append((-score, len(out), {
            "name": val["cLabel"], "category": val["inds"] or val["cDescription"],
            "location": val["hqLabel"] or where, "city": where, "website": site,
            "ref": "wikidata:" + qid, "via": ["wikidata"]}))
    return [row for _s, _i, row in sorted(out, key=lambda t: t[:2])]


# ------------------------------------------------------------------------------ the website

_EMAIL_FULL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._%+-]{0,63}@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*"
                         r"\.[A-Za-z]{2,24}$")
_EMAIL_IN = re.compile(r"(?<![\w.+-])[A-Za-z0-9][A-Za-z0-9._%+-]{0,63}@[A-Za-z0-9-]+"
                       r"(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,24}(?![\w-])")
_NOT_EMAIL = re.compile(r"\.(?:png|jpe?g|gif|svg|webp|avif|css|js|ico)$|@(?:\d+x|example\.|"
                        r"domain\.|email\.com$|yourdomain|yoursite|sentry|wixpress|"
                        r"[\w.-]*\.wix\.com$)|^(?:name|user|username|you|your|email)@", re.I)
_PHONE_LABELLED = re.compile(r"(?:phone|tel|telephone|call(?:\s+us)?|mobile|mob|cell|"
                             r"whats\s?app|contact(?:\s+(?:no|number))?)\s*(?:no\.?|number|"
                             r"#)?\s*[:.\-]?\s*(\+?\d[\d\s().-]{8,18}\d)", re.I)
_CONTACT = re.compile(r"contact|reach[\s-]?us|get[\s-]?in[\s-]?touch|enquir|inquir", re.I)


class _Page(HTMLParser):
    """The visible text, the links and their words, and whether the site hid its address."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.text, self.links, self.title = [], [], ""
        self.hidden_email = False
        self._skip = 0
        self._in_title = False
        self._a = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in ("script", "style", "noscript", "template", "svg"):
            self._skip += 1
        if tag == "title":
            self._in_title = True
        if tag == "a":
            self._a = [a.get("href") or "", []]
        if "data-cfemail" in a or "__cf_email__" in (a.get("class") or ""):
            self.hidden_email = True
        if "email-protection" in (a.get("href") or ""):
            self.hidden_email = True

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript", "template", "svg") and self._skip:
            self._skip -= 1
        if tag == "title":
            self._in_title = False
        if tag == "a" and self._a is not None:
            self.links.append((self._a[0], " ".join(self._a[1]).strip()))
            self._a = None

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        if self._skip:
            return
        self.text.append(data)
        if self._a is not None:
            self._a[1].append(data.strip())


def read_contacts(page_html, page_url):
    """What a page itself publishes: {"emails", "phones", "contact", "hidden"}.
    Emails from mailto: links first, then from the visible text; phones from tel: links, then
    only from text that labels them as a phone. Nothing is composed and nothing is decoded."""
    page = _Page()
    try:
        page.feed(page_html or "")
    except Exception:                                          # noqa: BLE001 - broken HTML
        pass
    emails, phones, contact = [], [], None
    for href, words in page.links:
        href = html.unescape(href or "").strip()
        low = href.lower()
        if low.startswith("mailto:"):
            addr = urllib.parse.unquote(href[7:].split("?")[0]).strip()
            if _EMAIL_FULL.match(addr) and not _NOT_EMAIL.search(addr):
                emails.append(addr)
        elif low.startswith("tel:"):
            number = re.sub(r"[^\d+]", "", urllib.parse.unquote(href[4:]))
            if 10 <= len(number.lstrip("+")) <= 13:
                phones.append(number)
        elif contact is None and (_CONTACT.search(words or "") or _CONTACT.search(
                urllib.parse.urlsplit(href).path or "")):
            full = urllib.parse.urljoin(page_url, href).split("#")[0]
            # "#contact" on the home page is a section of THIS page, not a contact page.
            if (full.startswith(("http://", "https://")) and _host(full) == _host(page_url)
                    and full.rstrip("/") != page_url.split("#")[0].rstrip("/")):
                contact = full
    text = " ".join(" ".join(page.text).split())
    for addr in _EMAIL_IN.findall(text):
        if not _NOT_EMAIL.search(addr):
            emails.append(addr)
    for raw in _PHONE_LABELLED.findall(text):
        number = re.sub(r"[^\d+]", "", raw)
        if 10 <= len(number.lstrip("+")) <= 13:
            phones.append(number)
    return {"emails": list(dict.fromkeys(e.lower() for e in emails)),
            "phones": list(dict.fromkeys(phones)), "contact": contact,
            "hidden": page.hidden_email, "title": " ".join(page.title.split())}


def _pick_email(emails, site):
    """The site's own domain first; a webmail address next (common for a small clinic)."""
    host = _host(site)
    own = [e for e in emails if host and (e.split("@")[1] == host
                                          or e.split("@")[1].endswith("." + host)
                                          or host.endswith("." + e.split("@")[1]))]
    return (own or emails or [None])[0]


def _robots(wire, site):
    """(allowed, why). A robots.txt that cannot be fetched for a 4xx means no rules; a server
    error or a refusal is treated as a no, the cautious reading."""
    parts = urllib.parse.urlsplit(site)
    status, _u, text, _c = wire.get("%s://%s/robots.txt" % (parts.scheme, parts.netloc),
                                    accept="text/plain,*/*;q=0.5", timeout=6.0)
    if status is None:
        return False, "it did not answer"
    if status in (401, 403):
        return False, "it refused even its robots.txt (HTTP %d)" % status
    if status >= 500 or status == 429:
        return False, "it is refusing (HTTP %d)" % status
    if status != 200:
        return True, ""
    rp = urllib.robotparser.RobotFileParser()
    rp.parse(text.splitlines())
    return (rp.can_fetch(UA, site), "its robots.txt asks programs not to read it")


def read_site(wire, site):
    """What a business's own site publishes about reaching it. {"email", "emailFrom", "phone",
    "phoneFrom", "contactPage", "why"} - why is "" when the site was read."""
    out = {"email": None, "emailFrom": None, "phone": None, "phoneFrom": None,
           "contactPage": None, "why": "", "hidden": False}
    allowed, why = _robots(wire, site)
    if not allowed:
        out["why"] = why
        return out
    status, final, text, ctype = wire.get(site)
    refusal = _refusal(status, text)
    if refusal or status != 200:
        out["why"] = refusal or ("it did not answer" if status is None else "HTTP %d" % status)
        return out
    if "html" not in (ctype or "text/html").lower():
        out["why"] = "its home page is not a web page"
        return out
    found = read_contacts(text, final)
    pages = [(final, found)]
    contact = found["contact"]
    if contact and not found["emails"] and wire.left() > 8:
        status, cfinal, ctext, cctype = wire.get(contact)
        if status == 200 and not _refusal(status, ctext) and "html" in (cctype or "html"):
            pages.append((cfinal, read_contacts(ctext, cfinal)))
    for url, f in pages:
        out["hidden"] = out["hidden"] or f["hidden"]
        email = _pick_email(f["emails"], final)
        if email and not out["email"]:
            out["email"], out["emailFrom"] = email, url
        if f["phones"] and not out["phone"]:
            out["phone"], out["phoneFrom"] = f["phones"][0], url
    out["contactPage"] = contact
    return out


# ------------------------------------------------------------------------------ the hunt

def _interleave(*lists):
    out = []
    for i in range(max((len(x) for x in lists), default=0)):
        out += [x[i] for x in lists if i < len(x)]
    return out


def hunt(what, where, count, wire=None, path=None, now=None, log=None):
    """Find up to `count` NEW leads for "<what> in <where>" and write each one as it is found.
    Returns the facts the closing line is made of - nothing in it is estimated."""
    wire = wire or Wire()
    log = log or (lambda line: None)
    count = min(max(int(count), 1), MAX_COUNT)
    notes = []
    r = {"what": what, "where": where, "count": count, "added": [], "merged": 0,
         "known": 0, "no_contact": 0, "unreadable": 0, "hidden": 0, "candidates": 0,
         "from": {"openstreetmap": 0, "wikidata": 0}, "web_found": 0, "notes": notes,
         "stopped": False, "requests": 0}
    try:
        osm = from_openstreetmap(wire, what, where, notes)
        log("openstreetmap: %d candidates" % len(osm))
        wd = from_wikidata(wire, what, where, notes)
        log("wikidata: %d candidates" % len(wd))
        # Duplicates across the two listings are one candidate: a company in both is read once.
        pool, taken = [], set()
        for cand in _interleave(osm, wd):
            k = keys(cand)
            if k & taken:
                continue
            taken |= k
            pool.append(cand)
        r["candidates"] = len(pool)
        for cand in pool:
            if len(r["added"]) >= count:
                break
            if known(cand, where, path):
                r["known"] += 1
                add_lead(cand, what, where, now=now, path=path)       # fill blanks, lastSeen
                continue
            if cand.get("website") and not cand.get("email"):
                site = read_site(wire, cand["website"])
                if site["why"]:
                    log("site %s not read: %s" % (_host(cand["website"]), site["why"]))
                    if not (cand.get("phone") or cand.get("email")):
                        r["unreadable"] += 1
                        continue
                got = False
                for field in ("email", "emailFrom", "phone", "phoneFrom", "contactPage"):
                    if site.get(field) and not cand.get(field):
                        cand[field] = site[field]
                        got = got or field in ("email", "phone", "contactPage")
                if got:
                    cand["via"] = list(cand["via"]) + ["website"]
                    r["web_found"] += 1
                r["hidden"] += 1 if site.get("hidden") and not cand.get("email") else 0
            if not (cand.get("email") or cand.get("phone") or cand.get("contactPage")):
                r["no_contact"] += 1
                continue
            outcome, row = add_lead(cand, what, where, now=now, path=path)
            if outcome == "added":
                r["added"].append(row)
                for v in ("openstreetmap", "wikidata"):
                    r["from"][v] += v in row["via"]
                log("%s %s" % (row["id"], row["name"][:40]))
            elif outcome == "merged":
                r["merged"] += 1
    except Stopped:
        r["stopped"] = True
    r["requests"] = wire.requests
    r["refused"] = dict(wire.refused)
    return r


def _ids(rows):
    if not rows:
        return ""
    if len(rows) == 1:
        return rows[0]["id"]
    return "%s to %s" % (rows[0]["id"], rows[-1]["id"])


def report(r):
    """The one line the hand prints - what was found, what was skipped and why, from where."""
    n, want = len(r["added"]), r["count"]
    plan = "%s in %s" % (r["what"], r["where"])
    if n:
        head = "Found %d of the %d %s you asked for, sir - written to the leads book as %s, " \
               "marked new." % (n, want, plan, _ids(r["added"])) if n < want else \
               "Found all %d %s, sir - written to the leads book as %s, marked new." % (
                   want, plan, _ids(r["added"]))
    elif r["candidates"]:
        head = "I found no new %s with public contact details, sir, so nothing new was " \
               "written." % plan
    elif r.get("refused"):
        # A REFUSAL IS NOT AN EMPTY LISTING. Measured against a live 429 and 403: this branch
        # used to say "neither lists any dentists in Pune" - a claim about Pune made from a
        # door that was shut. The notes below name who refused and how.
        head = "I could not look for %s, sir - %s, so nothing was written." % (
            plan, "both listings refused me" if len(r["refused"]) > 1 else
            "a listing refused me and the other had none")
    else:
        head = "Neither OpenStreetMap nor Wikidata lists any %s, sir, and I have no web " \
               "search I may use honestly, so nothing was written." % plan
    tail = []
    if r["no_contact"]:
        tail.append("%d had no public contact information and %s skipped rather than guessed"
                    % (r["no_contact"], "was" if r["no_contact"] == 1 else "were"))
    if r["unreadable"]:
        tail.append("%d website%s refused me or could not be read, so %s skipped"
                    % (r["unreadable"], "" if r["unreadable"] == 1 else "s",
                       "it was" if r["unreadable"] == 1 else "they were"))
    if r["known"] + r["merged"]:
        tail.append("%d %s already in the book" % (r["known"] + r["merged"],
                                                  "was" if r["known"] + r["merged"] == 1
                                                  else "were"))
    line = head + (" " + "; ".join(tail)[:1].upper() + "; ".join(tail)[1:] + "." if tail else "")
    if n:
        src = [("%d from OpenStreetMap" % r["from"]["openstreetmap"]) if r["from"]["openstreetmap"]
               else "", ("%d from Wikidata" % r["from"]["wikidata"]) if r["from"]["wikidata"]
               else ""]
        line += " %s%s." % (" and ".join(s for s in src if s),
                            ", with contact details read off %d of their own websites"
                            % r["web_found"] if r["web_found"] else "")
    if r["stopped"]:
        line += " I stopped at the time limit, so a second hunt may find more."
    elif n < want and r["candidates"]:
        line += " That is every one the open listings gave me - %d looked at." % r["candidates"]
    for note in r["notes"]:
        line += " %s%s." % (note[:1].upper(), note[1:])
    return line


# ------------------------------------------------------------------------------ by hand

def _main(argv):                                               # pragma: no cover
    if argv[:1] == ["hunt"] and len(argv) > 1:
        parsed = parse_request(" ".join(argv[1:]))
        if not parsed:
            print("That is not a hunt I can read - try: find 5 dentists in Pune")
            return 1
        r = hunt(parsed["what"], parsed["where"], parsed["count"],
                 log=lambda line: sys.stderr.write("  hunt: %s\n" % line))
        print(report(r))
        return 0
    if argv[:1] == ["list"]:
        leads, _bad = read_book()
        for row in leads[-int(argv[1] if len(argv) > 1 else 20):]:
            print("%s  %-36s %-22s %-28s %-16s %s" % (
                row["id"], row["name"][:36], (row.get("email") or "-")[:22],
                (row.get("website") or "-")[:28], row.get("phone") or "-", row["source"]))
        return 0
    print(summary())
    return 0


if __name__ == "__main__":                                     # pragma: no cover
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:                                          # noqa: BLE001
        pass
    sys.exit(_main(sys.argv[1:]))
