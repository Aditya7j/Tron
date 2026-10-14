"""THE CLOSER, phase 1. Writes to the Hunter's leads, reads what they write back, answers it, and
makes one of three kinds of demo when one is asked for - on its own, once the employer has said
"start the closer". It never decides that a business deserves a meeting: that is the employer's
word, through lock_meeting, and nothing here sends one without it.

WHERE IT KEEPS THINGS
    leads.json          THE HUNTER'S BOOK, the only lead store. A status moves through
                        hunter.update_lead() and nowhere else; the Closer's own fields live
                        under each row's "closer" key (threadId, requirement, meeting, ...).
    closer-log.json     THE AUDIT LOG. Every autonomous send - cold email, follow-up, reply,
                        demo, acknowledgement - and every reply read: to whom, when, what (the
                        body, and the demo file's name and sha256), and why (which reading of
                        which message triggered it). Visibility, not a gate: nothing waits on it.
    closer-state.json   THE SWITCH: on or off, since when, and the daily cap the employer saw
                        on the card. Written by tools/closer_start.py and by "stop the closer".
    closer-demos/       Every demo file exactly as it was attached.
    All three are gitignored: they are other businesses' words and addresses.

THE ON-SWITCH IS THE ONE CARD. Every send after it is autonomous, as the brief asks - but the
switch itself is a hand behind a yes, because the alternative is code that starts emailing real
businesses the first time a server boots. "stop the closer" is the panic key: no card, at once.

THE NEVER-LIST, enforced in code rather than asked of a model
    - NO INVENTED PRICE, DATE OR CAPABILITY. Every draft passes vet(): any digit, currency, URL,
      address, "free", "discount", "guarantee", "next week", "within two days" that is not in the
      employer's offer sheet (config.json "closer"), the lead's own row or the business's own
      message is a rejection. Then a second model reads the draft against the same facts and
      names any claim they do not support. A draft that fails three times is never sent: a reply
      falls back to a fixed honest sentence ("Aditya will follow up on that personally"), and a
      cold email simply waits for the next tick.
    - ONE UNSOLICITED FOLLOW-UP, AT MOST. A lead that has never written back gets the cold email
      and, after followUpAfterDays, one follow-up - then nothing, ever. _send() refuses a third
      unsolicited message whatever called it.
    - "ARE YOU AN AI?" IS ANSWERED YES. A fixed sentence, prefixed by code, not left to a model;
      and any draft claiming to be human is rejected outright.
    - A FAILED SEND IS NEVER RETRIED. The log row is written as "sending" BEFORE the network,
      then marked sent or failed. A cold email is sent to a lead only if no row of any status
      exists for it, and a reply only if no row answers that same message - so a crash between
      Gmail's yes and the log's write blocks a duplicate instead of causing one.
    - THE MODEL IS GROQ OR NOTHING. A business is never written to by the 1.7B local fallback;
      if Groq is throttled the work waits for the next tick.
    - A HUMAN IN THE THREAD TAKES IT OVER. A message in the thread sent from this mailbox that the
      Closer did not send means the employer answered by hand, and the Closer stops writing to
      that lead (it still reads and reports).

REPLIES ARE MATCHED BY THREAD, never by sender address: a business may answer from a different
address than it was written to. The only threads ever read are the ones the Closer's own sends
returned (google_api.get_thread, by id).

    python closer.py                    the switch, the book's statuses and the log's size
    python closer.py report             today's report, exactly as it is spoken
    python closer.py log [N]            the last N audit rows
    python closer.py tick               one tick now, on this thread, with the server's Groq
"""

import base64
import datetime
import hashlib
import html
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid, parseaddr

import hunter
# Every child this module starts - Chrome, taskkill, node - goes through _proc, which starts
# it with no console window: the daemon runs inside the server, on the employer's desktop.
from tools import _proc

HERE = os.path.dirname(os.path.abspath(__file__))
# Test seams, as hunter.py's TRONE_LEADS_PATH is.
LOG_PATH = os.environ.get("TRONE_CLOSER_LOG") or os.path.join(HERE, "closer-log.json")
STATE_PATH = os.environ.get("TRONE_CLOSER_STATE") or os.path.join(HERE, "closer-state.json")
DEMO_DIR = os.environ.get("TRONE_CLOSER_DEMOS") or os.path.join(HERE, "closer-demos")
CONFIG_PATH = os.environ.get("TRONE_CLOSER_CONFIG") or os.path.join(HERE, "config.json")

DEFAULT_DAILY, HARD_DAILY_MAX = 10, 25        # cold emails a day: the card's, and the ceiling
UNSOLICITED_MAX = 2                            # the cold email and ONE follow-up
REPLIES_PER_LEAD_PER_DAY = 6                   # a ping-pong with a responder that slips
                                               # past the auto-reply headers stops here
DRAFT_ATTEMPTS = 3
POLL_S = 5.0                                   # how often the daemon looks at the switch
DEFAULT_TICK_S = 120
INBOUND_PER_TICK = 4

# What a lead's status becomes when its last word is read. "unclear" waits for the employer.
LABELS = ("not-interested", "questions", "wants-demo", "wants-price", "wants-meeting",
          "meeting-time", "unclear")
STATUS_OF = {"not-interested": "not-interested", "questions": "questions",
             "wants-demo": "wants-demo", "wants-price": "wants-price",
             "wants-meeting": "wants-meeting", "meeting-time": "meeting-confirmed",
             "unclear": "replied"}
# ENGAGED: talking to us and not yet given a meeting - the employer's decision list.
ENGAGED = ("questions", "wants-demo", "wants-price", "wants-meeting", "replied")
MEETING = ("meeting-proposed", "meeting-confirmed")
DEMO_KINDS = ("code", "pitch", "mockup")
SAY_LABEL = {"questions": "has questions", "wants-demo": "wants a demo",
             "wants-price": "asked about price", "wants-meeting": "wants a meeting",
             "not-interested": "is not interested", "replied": "replied, and I could not "
             "tell what they want", "meeting-time": "named a time for the meeting",
             "unclear": "replied, and I could not tell what they want"}

_lock = threading.Lock()                       # this module's own files, this process
_chat = None
_config = None
_gmail = None


def configure(chat=None, config=None, gmail=None):
    """The server lends its Groq client and its config reader, as it does the Scholar's - one
    client, not a second one that could drift. `gmail` is a seam for tests (google_api)."""
    global _chat, _config, _gmail
    if chat is not None:
        _chat = chat
    if config is not None:
        _config = config
    if gmail is not None:
        _gmail = gmail


def _google():
    global _gmail
    if _gmail is None:
        import google_api
        _gmail = google_api
    return _gmail


def _now():
    return datetime.datetime.now()


def _today():
    return _now().date().isoformat()


def _clip(text, n):
    text = " ".join(str(text or "").split())
    return text if len(text) <= n else text[:n - 1].rstrip() + "\u2026"


# ------------------------------------------------------------------------------ the offer sheet

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


def settings(cfg=None):
    """(settings, problems). The offer sheet is config.json's "closer" block, and it is THE ONLY
    SOURCE of anything the Closer may claim: what is offered, its details, the pricing guidance
    and the answers to common questions. Nothing in it is ever inferred."""
    block = (cfg if cfg is not None else _read_config()).get("closer") or {}
    offer = block.get("offer") if isinstance(block.get("offer"), dict) else {}
    details = [_clip(d, 300) for d in (offer.get("details") or []) if str(d).strip()]
    faq = [{"q": _clip(f.get("q"), 200), "a": _clip(f.get("a"), 500)}
           for f in (offer.get("faq") or []) if isinstance(f, dict)
           and str(f.get("q") or "").strip() and str(f.get("a") or "").strip()]
    sender = _clip(offer.get("senderName"), 80)
    s = {"service": _clip(offer.get("service"), 300), "details": details[:20],
         "pricing": _clip(offer.get("pricing"), 600), "faq": faq[:20], "sender": sender,
         "signature": str(offer.get("signature") or sender or "").strip()[:400],
         "followUpAfterDays": block.get("followUpAfterDays", 5),
         "tickSeconds": block.get("tickSeconds", DEFAULT_TICK_S)}
    if not isinstance(s["followUpAfterDays"], int) or s["followUpAfterDays"] < 0:
        s["followUpAfterDays"] = 0
    if not isinstance(s["tickSeconds"], int) or not 30 <= s["tickSeconds"] <= 3600:
        s["tickSeconds"] = DEFAULT_TICK_S
    problems = []
    if not s["service"]:
        problems.append('closer.offer.service in config.json is empty, so I do not know what '
                        'we are offering and will not write to anyone')
    if not sender:
        problems.append("closer.offer.senderName in config.json is empty, so I do not know "
                        "whose name to sign")
    return s, problems


def facts(s, lead=None, theirs=""):
    """The whole of what a draft may rest on, as one text a checker can read."""
    out = ["WHAT WE OFFER: %s" % s["service"]]
    if s["details"]:
        out.append("DETAILS:\n" + "\n".join("- " + d for d in s["details"]))
    # "none set" and NOTHING MORE: this text is also what vet() allows words from, so a helpful
    # "no discount or free offer may be stated" here would make "free" and "discount" allowed.
    out.append("PRICING GUIDANCE: %s" % (s["pricing"] or "none set"))
    if s["faq"]:
        out.append("ANSWERS WE HAVE:\n" + "\n".join("Q: %s\nA: %s" % (f["q"], f["a"])
                                                    for f in s["faq"]))
    out.append("SENDER: %s" % s["sender"])
    if lead:
        out.append("RECIPIENT: %s - %s, %s%s" % (
            lead["name"], lead.get("category") or lead.get("niche") or "business",
            lead.get("city") or "", (" (" + lead["location"] + ")") if lead.get("location")
            else ""))
    if theirs:
        out.append("THEIR MESSAGE:\n" + theirs)
    return "\n\n".join(out)


# ------------------------------------------------------------------------------ the switch

def read_state():
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {"on": False}
    except (OSError, ValueError):
        return {"on": False}


def switch(on, by, daily=None):
    """Turn the Closer on or off. Off is immediate and needs no card; on is tools/closer_start.py,
    after one. The daily cap is the number the employer saw on that card."""
    state = read_state()
    state.update(on=bool(on), since=_now().isoformat(timespec="seconds"), by=str(by)[:20])
    if daily is not None:
        state["daily"] = max(1, min(HARD_DAILY_MAX, int(daily)))
    with _lock, hunter.file_lock(STATE_PATH):
        tmp = STATE_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(state, fh, indent=1)
        os.replace(tmp, STATE_PATH)
    return state


# ------------------------------------------------------------------------------ the audit log

def read_log(path=None):
    try:
        with open(path or LOG_PATH, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except FileNotFoundError:
        return []
    except (OSError, ValueError):
        raise OSError("the Closer's log (closer-log.json) cannot be read, and I will not send "
                      "anything I cannot write down")
    rows = data.get("entries") if isinstance(data, dict) else None
    return rows if isinstance(rows, list) else []


def _write_log(rows, path=None):
    path = path or LOG_PATH
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump({"version": 1, "entries": rows,
                   "updated": _now().isoformat(timespec="seconds"),
                   "note": "Every message the Closer sent or read. A row marked 'sending' is "
                           "one whose outcome was never written: check Gmail's Sent."},
                  fh, indent=1, ensure_ascii=False)
        fh.write("\n")
    os.replace(tmp, path)


def log_event(entry, path=None):
    """Append one row and return it with its id ("C-0001") and time. Written before a send."""
    with _lock, hunter.file_lock(path or LOG_PATH):
        rows = read_log(path)
        n = max((int(r["id"][2:]) for r in rows if re.fullmatch(r"C-\d+", str(r.get("id")))),
                default=0) + 1
        row = dict({"id": "C-%04d" % n, "at": _now().isoformat(timespec="seconds")}, **entry)
        _write_log(rows + [row], path)
        return dict(row)


def update_event(entry_id, path=None, **fields):
    with _lock, hunter.file_lock(path or LOG_PATH):
        rows = read_log(path)
        for r in rows:
            if r.get("id") == entry_id:
                r.update(fields)
                _write_log(rows, path)
                return dict(r)
    return None


SEND_KINDS = ("cold", "followup", "reply", "demo", "ack", "meeting")


def _ours(rows):
    """Gmail ids of every message the Closer sent - how a reply is told from our own mail."""
    return {r.get("gmailId") for r in rows if r.get("kind") in SEND_KINDS and r.get("gmailId")}


# ------------------------------------------------------------------------------ the vetting

_DIGITS = re.compile(r"\d[\d,.]*\d|\d")
_MONEY = re.compile(r"[\u20b9$\u20ac\u00a3]|\b(?:rs\.?|inr|usd|rupees?|lakhs?|crores?|"
                    r"free|discount\w*|no\s+cost|complimentary|cheap\w*|affordable|"
                    r"money[- ]back|refund\w*|guarantee\w*|risk[- ]free|trial|per\s+month|"
                    r"/\s*month|budget[- ]friendly)\b", re.I)
_WHEN = re.compile(r"\b(?:tomorrow|tonight|this\s+week|next\s+week|this\s+month|next\s+month|"
                   r"by\s+(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday|the\s+end|"
                   r"end\s+of|eod|eow)|within\s+(?:a|an|one|two|three|a\s+few|few|hours|days)|"
                   r"same[- ]day|overnight|asap|in\s+no\s+time|turnaround|deadline|"
                   r"(?:one|two|three|four|five|six|seven|ten|a\s+few|few|couple\s+of)\s+"
                   r"(?:days?|weeks?|months?|hours?))\b", re.I)
# ANY DENIAL OF BEING AN AI, in any phrasing a model has been seen to use. Measured on
# 2026-10-14: right under the fixed "yes, this was written by an AI", Groq wrote "You are not
# speaking to a bot." - which the first, narrower version of this pattern let through.
_HUMAN = re.compile(r"\b(?:i\s*am|i'm|this\s+is|you(?:'re|\s+are)\s+(?:talking|speaking|"
                    r"writing|chatting)\s+(?:to|with))\s+(?:a\s+|an\s+)?(?:real\s+|actual\s+)?"
                    r"(?:human|person|people)\b|\bnot\s+(?:\w+\s+){0,3}(?:an?\s+)?(?:ai|a\.i\.|"
                    r"bot|robot|chatbot|automated|machine|program)\b|\bno\s+(?:bot|robot|ai)\b|"
                    r"\b(?:real|actual)\s+(?:human|person)\b", re.I)
# CLAIMS OF RESULT, AND FLATTERY: measured in a real cold draft, "a trusted local practice" and
# "may help reduce no-shows" - neither in any fact. Allowed only where the facts or their own
# message already say it.
_OUTCOME = re.compile(r"\b(?:reduc\w+|increas\w+|boost\w*|grow(?:s|th|ing)?|improv\w+|"
                      r"sav(?:e|es|ing)\s+(?:time|money|hours)|more\s+(?:patients|customers|"
                      r"clients|sales|leads|bookings|revenue)|fewer|no-?shows?|roi|revenue|"
                      r"efficien\w+|streamlin\w+|transform\w*)\b", re.I)
_FLATTERY = re.compile(r"\b(?:you(?:'re|\s+are)\s+(?:a\s+|an\s+)?|your\s+)(?:trusted|leading|"
                       r"popular|well[- ]known|reputed|renowned|busy|growing|thriving|successful|"
                       r"top|premier|established|respected|amazing|great|wonderful)\b", re.I)
_SEEN = re.compile(r"\b(?:i|we)\s+(?:have\s+|'ve\s+)?(?:saw|seen|visited|noticed|came\s+across|"
                   r"loved?|checked\s+out|been\s+following|follow|read|reviewed|looked\s+at|"
                   r"browsed)\s+(?:your|the)\s+(?:website|site|reviews?|instagram|facebook|"
                   r"posts?|page|profile|portfolio|blog|menu|work)\b", re.I)
_PLACEHOLDER = re.compile(r"\[[A-Za-z][^\]]{0,40}\]|\{[a-z_ ]+\}|<[A-Z][A-Za-z ]+>|"
                          r"\byour\s+name\b|\bXXX+\b|lorem\s+ipsum", re.I)
_LINKISH = re.compile(r"https?://\S+|\bwww\.\S+|\b[\w.+-]+@[\w-]+\.[\w.]+|"
                      r"\b[a-z0-9-]+\.(?:com|in|io|co|net|org|ai|app)\b", re.I)


def _norm_num(n):
    return n.replace(",", "").rstrip(".")


def vet(text, allowed):
    """Every reason `text` may not be sent, given `allowed` - the facts, the lead's own row and
    the business's own words. An empty list is the only pass. Pure, so it is tested whole."""
    text, low_allowed = str(text or ""), str(allowed or "").lower()
    allowed_nums = {_norm_num(n) for n in _DIGITS.findall(str(allowed or ""))}
    problems = []
    for n in _DIGITS.findall(text):
        if _norm_num(n) not in allowed_nums:
            problems.append("the number %s is in nobody's facts" % n)
    for rx, what in ((_MONEY, "money word"), (_WHEN, "time promise"),
                     (_OUTCOME, "claim of a result"), (_FLATTERY, "claim about them")):
        for m in rx.finditer(text):
            if m.group(0).lower() not in low_allowed:
                problems.append("the %s %r is in nobody's facts" % (what, m.group(0)))
    for m in _LINKISH.finditer(text):
        if m.group(0).lower().rstrip(".,)") not in low_allowed:
            problems.append("the address %r was invented" % m.group(0))
    if _HUMAN.search(text):
        problems.append("it claims to be human")
    if _SEEN.search(text):
        problems.append("it claims to have looked at their %s" % _SEEN.search(text).group(0))
    if _PLACEHOLDER.search(text):
        problems.append("it still has a placeholder: %r" % _PLACEHOLDER.search(text).group(0))
    return list(dict.fromkeys(problems))


_SIGNOFF = re.compile(r"^\s*(?:best|regards|best\s+regards|warm\s+regards|kind\s+regards|"
                      r"many\s+thanks|thanks|thank\s+you|cheers|sincerely|warmly)\b[^\n]{0,20}$",
                      re.I | re.M)


def _tidy(body):
    """The model's body without a sign-off of its own - the signature is the employer's, added
    by code - and without the think-block a reasoning model may leave."""
    body = re.sub(r"<think>.*?</think>", "", str(body or ""), flags=re.S).strip()
    m = _SIGNOFF.search(body)
    if m and m.start() > len(body) * 0.5:
        body = body[:m.start()]
    return re.sub(r"\n{3,}", "\n\n", body).strip()


# ------------------------------------------------------------------------------ the model

def _ask_json(system, user):
    """(object, "") or (None, why). Groq through the server's own client, or nothing."""
    if _chat is None:
        return None, "no model is connected to the Closer"
    try:
        answer, error = _chat([{"role": "system", "content": system},
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
    """Groq could not be asked at all: wait for the next tick rather than fall back."""


# HOW LONG A REFUSAL MEANS, read off Groq's own sentence. Measured on 2026-10-14 with the free
# tier's 200 000 tokens a day spent: "on tokens per day (TPD): Limit 200000, Used 199693,
# Requested 432. Please try again in 54s". The window rolls, so a few hundred tokens trickle back
# a minute - and a Closer retrying every tick spent each trickle on a cold draft, then met the
# 429 on the checker, and threw the draft away: it burned the house's tokens and finished
# nothing. So a daily refusal waits TPD_WAIT_S at least, for a run of tokens big enough to finish
# a whole piece of work, and any other names its own wait. The butler shares this budget.
TPD_WAIT_S = 900


def backoff_s(why):
    why = str(why or "")
    m = re.search(r"try again in (?:(\d+)h)?(?:(\d+)m)?(?:([\d.]+)s)?", why)
    named = 0.0
    if m and any(m.groups()):
        named = (int(m.group(1) or 0) * 3600 + int(m.group(2) or 0) * 60
                 + float(m.group(3) or 0))
    if re.search(r"tokens per day|\bTPD\b", why):
        return max(TPD_WAIT_S, named)
    return named


_hold_until = 0.0


VERIFY_SYSTEM = (
    "You are a strict fact-checker for one outgoing business email. FACTS is everything the "
    "sender may claim. List every statement in DRAFT that (a) claims a service, feature, "
    "capability, result, client, statistic, price, discount, deadline, delivery time or "
    "guarantee that FACTS do not state; (b) claims specific knowledge of the recipient beyond "
    "FACTS - for example having seen their website, reviews or size; or (c) claims the writer "
    "is human or denies being an AI. Be strict: \"may help reduce no-shows\" is unsupported "
    "unless FACTS say so; \"a trusted local practice\" is unsupported unless FACTS say so; "
    "\"you are not speaking to a bot\" is always unsupported. Plain greetings, questions to the "
    "recipient, offers to talk or send an example, saying someone will follow up, and repeating "
    "what THEIR MESSAGE said are fine. Reply with JSON only: "
    '{"unsupported": ["<short quote>", ...]} and an empty list if nothing is unsupported.')


def checked(draft_text, fact_text):
    """[] if the draft may go, else the reasons it may not: vet() first, then a second model."""
    problems = vet(draft_text, fact_text)
    if problems:
        return problems
    got, err = _ask_json(VERIFY_SYSTEM, "FACTS:\n%s\n\nDRAFT:\n%s" % (fact_text, draft_text))
    if got is None:
        if "JSON" in err:
            return ["the checker's verdict could not be read, so it does not count as a pass"]
        raise ModelDown(err)
    bad = [str(q)[:160] for q in (got.get("unsupported") or []) if str(q).strip()]
    return ["unsupported: %r" % q for q in bad]


def _draft(system, user, fields, fact_text, check_fields=None):
    """Ask, vet, re-ask with the reasons, at most DRAFT_ATTEMPTS times. (object, attempts) or
    (None, last reasons). Raises ModelDown if Groq cannot be asked at all."""
    reasons = []
    for attempt in range(1, DRAFT_ATTEMPTS + 1):
        ask = user if not reasons else (
            user + "\n\nYOUR LAST DRAFT WAS REJECTED FOR: " + "; ".join(reasons[:6]) +
            ". Write it again without those.")
        got, err = _ask_json(system, ask)
        if got is None:
            if "JSON" not in err:
                raise ModelDown(err)
            reasons = [err]
            continue
        if any(not str(got.get(f) or "").strip() for f in fields):
            reasons = ["it left out %s" % ", ".join(f for f in fields if not got.get(f))]
            continue
        text = "\n".join(_flatten(got.get(f)) for f in (check_fields or fields))
        reasons = checked(text, fact_text)
        if not reasons:
            return got, attempt
    return None, reasons


def _flatten(value):
    if isinstance(value, list):
        return "\n".join(_flatten(v) for v in value)
    if isinstance(value, dict):
        return "\n".join(_flatten(v) for v in value.values())
    return str(value or "")


# ------------------------------------------------------------------------------ Gmail

def _sender(s):
    email = str((_google().token() or {}).get("email") or "")
    return formataddr((s["sender"], email)) if email and s["sender"] else email


def build_mime(to, subject, body, sender="", attachments=(), in_reply_to="", references=""):
    note = EmailMessage()
    note["To"] = to
    if sender:
        note["From"] = sender
    note["Subject"] = subject
    note["Date"] = formatdate(localtime=True)
    note["Message-ID"] = make_msgid()
    if in_reply_to:
        note["In-Reply-To"] = in_reply_to
        note["References"] = (references + " " + in_reply_to).strip() if references \
            else in_reply_to
    note.set_content(body)
    for a in attachments:
        main, sub = a["type"].split("/", 1)
        with open(a["file"], "rb") as fh:
            note.add_attachment(fh.read(), maintype=main, subtype=sub, filename=a["name"])
    return note.as_bytes(), str(note["Message-ID"])


def _send(lead, kind, why, to, subject, body, s, attachments=(), thread_id=None,
          inbound=None, by="closer", how="model"):
    """(row, "") or (row|None, why). THE ONLY WAY A MESSAGE LEAVES. The row is written as
    "sending" before Gmail is asked, and marked sent or failed after; it is never retried."""
    rows = read_log()
    if kind in ("cold", "followup"):
        unsolicited = sum(1 for r in rows if r.get("leadId") == lead["id"]
                          and r.get("kind") in ("cold", "followup"))
        if unsolicited >= UNSOLICITED_MAX:
            return None, "%s has had its cold email and its one follow-up already" % lead["id"]
        if any(r.get("leadId") == lead["id"] and r.get("kind") == "inbound" for r in rows):
            return None, "%s has written back, so nothing unsolicited goes to it" % lead["id"]
    if kind == "cold" and any(r.get("kind") == "cold" and (
            r.get("leadId") == lead["id"] or str(r.get("to")).lower() == to.lower())
            for r in rows):
        return None, "%s was already written to once - a cold email is never sent twice" % (
            lead["id"])
    if inbound and inbound.get("id") and any(
            r.get("inReplyTo") == inbound["id"] and r.get("kind") in SEND_KINDS for r in rows):
        return None, "that message was already answered"
    try:
        raw, header_id = build_mime(to, subject, body, _sender(s), attachments,
                                    in_reply_to=(inbound or {}).get("messageId", ""),
                                    references=(inbound or {}).get("references", ""))
    except (OSError, ValueError) as exc:
        return None, "the message could not be built (%s)" % exc
    row = log_event({"kind": kind, "leadId": lead["id"], "business": lead["name"], "to": to,
                     "subject": subject, "body": body[:8000], "why": why, "by": by,
                     "draft": how, "status": "sending", "headerId": header_id,
                     "inReplyTo": (inbound or {}).get("id"), "threadId": thread_id,
                     "attachments": [{k: a[k] for k in ("name", "file", "bytes", "sha256")}
                                     for a in attachments]})
    sent, err = _google().send_message(raw, thread_id)
    gid = str((sent or {}).get("id") or "")
    if err or not gid:
        reason = err or "Gmail accepted it but named no message, so I cannot prove it went"
        return update_event(row["id"], status="failed", error=str(reason)[:300]), reason
    return update_event(row["id"], status="sent", gmailId=gid,
                        threadId=str(sent.get("threadId") or thread_id or "")), ""


# ---- reading a thread

def _b64(data):
    data = str(data or "")
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def _headers(part):
    return {h.get("name", "").lower(): str(h.get("value") or "")
            for h in (part.get("headers") or [])}


def _html_text(markup):
    markup = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", markup)
    markup = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</li>", "\n", markup)
    return html.unescape(re.sub(r"<[^>]+>", " ", markup))


def _body_text(part):
    """The message's own text: text/plain if it has one, else its HTML without the tags."""
    found = {"text/plain": [], "text/html": []}

    def walk(p):
        mime = str(p.get("mimeType") or "").lower()
        if mime in found and (p.get("body") or {}).get("data") and not p.get("filename"):
            ctype = _headers(p).get("content-type", "")
            cs = re.search(r'charset="?([\w-]+)', ctype)
            try:
                found[mime].append(_b64(p["body"]["data"]).decode(
                    cs.group(1) if cs else "utf-8", "replace"))
            except LookupError:
                found[mime].append(_b64(p["body"]["data"]).decode("utf-8", "replace"))
        for child in p.get("parts") or []:
            walk(child)
    walk(part)
    if found["text/plain"]:
        return "\n".join(found["text/plain"])
    return _html_text("\n".join(found["text/html"]))


_QUOTE_HEAD = re.compile(r"\n[ \t>]*On\b[^\n]{0,300}(?:\n[^\n]{0,300})?\bwrote:[ \t]*\n|"
                         r"\n-{2,}\s*Original Message\s*-{2,}|\n_{5,}\s*\nFrom:|"
                         r"\nFrom:[^\n]+\n(?:Sent|Date):", re.I)


def strip_quoted(text):
    """What THEY wrote, without the quoted history under it."""
    text = "\n" + str(text or "").replace("\r\n", "\n")
    m = _QUOTE_HEAD.search(text)
    if m:
        text = text[:m.start()]
    lines = [ln for ln in text.split("\n") if not ln.lstrip().startswith(">")]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


_AUTO_SUBJECT = re.compile(r"\b(?:out\s+of\s+(?:the\s+)?office|automatic\s+reply|auto[- ]?reply|"
                           r"autoreply|away\s+from|on\s+leave|vacation)\b", re.I)
_BOUNCE_FROM = re.compile(r"^(?:mailer-daemon|postmaster)@", re.I)
_BOUNCE_SUBJECT = re.compile(r"delivery\s+status\s+notification|undeliverable|mail\s+delivery\s+"
                             r"(?:failed|subsystem)|returned\s+mail|delivery\s+failure", re.I)


def parse_message(msg):
    payload = msg.get("payload") or {}
    h = _headers(payload)
    name, addr = parseaddr(h.get("reply-to") or h.get("from", ""))
    _n, from_addr = parseaddr(h.get("from", ""))
    text = _body_text(payload) or str(msg.get("snippet") or "")
    auto = (h.get("auto-submitted", "no").lower() not in ("", "no")
            or "x-autoreply" in h or "x-autorespond" in h
            or h.get("precedence", "").lower() in ("auto_reply", "bulk", "junk")
            or bool(_AUTO_SUBJECT.search(h.get("subject", ""))))
    bounce = bool(_BOUNCE_FROM.match(from_addr) or _BOUNCE_SUBJECT.search(h.get("subject", "")))
    return {"id": str(msg.get("id") or ""), "labels": list(msg.get("labelIds") or []),
            "at": int(msg.get("internalDate") or 0), "from": from_addr, "replyTo": addr,
            "name": name, "subject": h.get("subject", ""), "messageId": h.get("message-id", ""),
            "references": h.get("references", ""), "text": strip_quoted(text)[:6000],
            "auto": auto, "bounce": bounce}


# ------------------------------------------------------------------------------ classification

_OPT_OUT = re.compile(r"\b(?:unsubscribe|remove\s+me|stop\s+(?:e-?mailing|writing|contacting)|"
                      r"not\s+interested|no\s+thanks?|no\s+thank\s+you|don'?t\s+(?:contact|"
                      r"e-?mail|write)|do\s+not\s+(?:contact|e-?mail|write)|please\s+stop|"
                      r"not\s+looking\s+for|nahi\s+chahiye|interested\s+nahi)\b", re.I)
_AI_ASKED = re.compile(r"\b(?:are|r)\s+(?:you|u)\s+(?:an?\s+)?(?:ai|a\.i\.|bot|robot|chatbot|"
                       r"human|real\s+person|real|automated|machine|chat\s*gpt)\b|"
                       r"\bis\s+this\s+(?:an?\s+)?(?:ai|bot|automated|auto-?generated|"
                       r"written\s+by)|\b(?:written|sent|generated)\s+by\s+(?:an?\s+)?(?:ai|bot|"
                       r"machine|chat\s*gpt)\b|\bkya\s+(?:aap|tum|ye|yeh)\s+(?:ai|bot|robot)\b",
                       re.I)

CLASSIFY_SYSTEM = (
    "You read one email that a business wrote back to a short cold email. For each kind of ask "
    "below, copy the EXACT words from their email that make that ask - a verbatim quote - or "
    "null if their email does not make it. Never infer an ask they did not write.\n"
    "- declines: they decline, or ask not to be contacted\n"
    "- demo: they ask to see a sample, example, demo, mockup, proposal or proof of work\n"
    "- price: they ask about price, cost, rates, a quote or budget\n"
    "- meeting: they ask for a call or a meeting\n"
    "%s"
    "- questions: a list of the other questions they ask about the service, each quoted\n"
    "- demoKind: if demo is not null, which ONE fits what they literally asked for: \"code\" (a "
    "short code sample or snippet - a technical proof), \"pitch\" (a short written proposal or "
    "sample copy), \"mockup\" (an image of a landing page, website or app screen), or \"none\" "
    "if none of the three fits (a video, a live trial, a working system...).\n"
    'Reply with JSON only: {"declines": null, "demo": null, "price": null, "meeting": null, %s'
    '"questions": [], "demoKind": "none"}')
_MEETING_TIME = ("- meetingTime: they accept a meeting time, or name a day or time for the "
                 "meeting already being arranged\n")


def _norm_words(text):
    return re.sub(r"[^a-z0-9 ]+", " ", str(text or "").lower()).split()


def _quoted(quote, text):
    """True when `quote` is really in `text` - the evidence rule. Punctuation and case are
    forgiven; words are not: a quote of four or more words may skip none of them."""
    q, t = _norm_words(quote), _norm_words(text)
    if not q:
        return False
    if " ".join(q) in " ".join(t):
        return True
    return len(q) >= 4 and all(w in set(t) for w in q)


def classify(lead, msg):
    """(reading, "") or (None, why). Rules first for what must never be a model's call - a bounce,
    an auto-reply, an opt-out - then the model, ON EVIDENCE: it must quote the words of theirs
    that make each ask, and an ask whose quote is not in their email is dropped. The label is
    then chosen here, by a fixed order, never by the model. Measured on 2026-10-14: asked for a
    label outright, Groq called a request for a mockup and a price "wants-meeting"."""
    if msg["bounce"]:
        return {"label": "bounce", "also": [], "demo": "none", "asks": [], "ai": False}, ""
    if msg["auto"]:
        return {"label": "auto", "also": [], "demo": "none", "asks": [], "ai": False}, ""
    text = msg["text"]
    ai = bool(_AI_ASKED.search(text))
    if _OPT_OUT.search(text) or re.fullmatch(r"\W*no\W*", text, re.I):
        return {"label": "not-interested", "also": [], "demo": "none", "asks": [], "ai": ai}, ""
    arranging = lead.get("status") == "meeting-proposed"
    system = CLASSIFY_SYSTEM % (_MEETING_TIME if arranging else "",
                                '"meetingTime": null, ' if arranging else "")
    # AN ANSWER THAT WILL NOT PARSE IS ASKED AGAIN, AND THEN IT IS "unclear". Measured against
    # Groq on 2026-10-14: the same email parsed twice and failed once (cut at the 400-token
    # ceiling). Holding the message would have held it forever; "unclear" answers nothing and
    # puts it in front of the employer. A model that cannot be reached at all still waits.
    for _attempt in range(DRAFT_ATTEMPTS):
        got, err = _ask_json(system, "THEIR EMAIL:\n%s" % text[:3000])
        if got is not None or "JSON" not in err:
            break
    if got is None and "JSON" not in err:
        return None, err
    got = got or {}

    def said(key):
        quote = got.get(key)
        return _clip(quote, 200) if isinstance(quote, str) and _quoted(quote, text) else None
    found = {"meeting-time": said("meetingTime") if arranging else None,
             "wants-meeting": said("meeting"), "wants-demo": said("demo"),
             "wants-price": said("price"), "not-interested": said("declines")}
    questions = [_clip(q, 200) for q in (got.get("questions") or [])
                 if isinstance(q, str) and _quoted(q, text) and not _AI_ASKED.search(q)][:5]
    order = ("meeting-time", "wants-meeting", "wants-demo", "wants-price")
    asked = [k for k in order if found[k]] + (["questions"] if questions else [])
    if found["not-interested"] and not asked:
        asked = ["not-interested"]
    if not asked and ai:
        asked = ["questions"]                  # all they asked is whether this is an AI
    label = asked[0] if asked else "unclear"
    demo = str(got.get("demoKind") or "none").strip().lower()
    demo = demo if found["wants-demo"] and demo in DEMO_KINDS else "none"
    asks = [found[k] for k in order if found[k]] + questions
    return {"label": label, "also": asked[1:], "demo": demo, "asks": asks, "ai": ai}, ""


def requirement(text):
    """THEIR STATED REQUIREMENT, VERBATIM: their own words, quote-stripped and clipped - never a
    model's paraphrase, so it can never say something they did not."""
    return _clip(text, 500)


# ------------------------------------------------------------------------------ drafting

COLD_SYSTEM = (
    "You write one short, personal first email from %(sender)s to a business. Rules:\n"
    "1. Begin with a short greeting to the business's team, then name the business and what "
    "it is naturally in the first sentence or two.\n"
    "2. Say in one or two sentences what %(sender)s offers, using ONLY the FACTS, and why it "
    "might matter to this kind of business - as a possibility, never as a claim about them.\n"
    "3. End with one low-pressure question, such as whether a short example would be useful.\n"
    "4. Never mention a price, discount, free offer, delivery date or timeline. Use no digits.\n"
    "5. Never claim to have seen their website, reviews or social media, to be a customer, or "
    "to be human.\n"
    "6. 60 to 110 words, plain text, no links, no greeting placeholders, NO sign-off and no "
    "name at the end - the signature is added after.\n"
    "Subject: three to seven words, specific to them, no digits, no clickbait.\n"
    'Reply with JSON only: {"subject": "...", "body": "..."}')

REPLY_SYSTEM = (
    "You write a short reply email for %(sender)s to a business that answered a cold email. "
    "Rules:\n"
    "1. Answer exactly what THIS business asked: %(asks)s.\n"
    "2. Use ONLY the FACTS. If they ask something the FACTS do not answer, say plainly that "
    "%(sender)s will follow up on that point personally. Never guess, never round up.\n"
    "3. %(price)s\n"
    "4. Never mention a discount, free offer, delivery date, deadline or turnaround unless the "
    "FACTS state it. No digits unless copied from the FACTS or from their message.\n"
    "5. Never claim to be human.\n"
    "6. %(extra)s\n"
    "7. Begin with a short greeting. 40 to 140 words, plain text, NO sign-off and no name at "
    "the end - the signature is added after.\n"
    'Reply with JSON only: {"body": "..."}')


def _optout_line(lead):
    return "If this isn't useful for %s, just reply \"no\" and I won't write again." % lead["name"]


def _signed(body, s):
    return "%s\n\n%s" % (body.rstrip(), s["signature"]) if s["signature"] else body


def draft_cold(lead, s):
    """(subject, body, how) or (None, None, why). Raises ModelDown."""
    fact_text = facts(s, lead)
    allowed = fact_text + "\n" + json.dumps({k: lead.get(k) for k in (
        "name", "category", "niche", "city", "location")}, ensure_ascii=False)
    got, n = _draft(COLD_SYSTEM % {"sender": s["sender"]}, fact_text, ("subject", "body"),
                    allowed)
    if got is None:
        return None, None, "no draft passed the checks (%s)" % "; ".join(n[:3])
    subject = _clip(got["subject"], 90).strip(" .\"'")
    body = _tidy(got["body"])
    return subject, _signed(body + "\n\n" + _optout_line(lead), s), "model, attempt %d" % n


AI_LINE = ("To answer your question directly: yes - this reply was written by Galaxy, an AI "
           "assistant working for %s. Decisions about meetings and terms are %s's own.")


def fallback(label, lead, s, demo_kind=None):
    """The fixed honest sentence for a reply no model draft could pass - never a guess."""
    who = s["sender"]
    if label == "wants-price":
        return ("Thank you for asking about pricing. It depends on what %s needs, so %s will "
                "come back to you on that directly rather than me guessing at a number."
                % (lead["name"], who))
    if label == "wants-meeting":
        return ("Glad to hear it. I'll check %s's availability and come back to you with times."
                % who)
    if label == "wants-demo":
        return ("Thank you - that is a specific need, so I'll have our team follow up on it "
                "directly rather than send you something half right.")
    if label == "not-interested":
        return "Understood - thank you for letting us know. I won't write again."
    if label == "meeting-time":
        return "Thank you - noted. I've passed this on to %s." % who
    return ("Thank you for the questions. I'd rather give you accurate answers than quick ones, "
            "so %s will follow up on them personally." % who)


def draft_reply(lead, msg, reading, s, demo=None):
    """(body, how). A model draft that passed every check, or the fixed honest sentence. Raises
    ModelDown if Groq cannot be asked, so the reply waits instead of falling back on a dead line.
    """
    label = reading["label"]
    asks = reading["asks"] or [label]
    if label in ("not-interested", "meeting-time"):
        body, how = fallback(label, lead, s), "fixed"
    else:
        price = ("If they ask about price, give the PRICING GUIDANCE exactly as written and "
                 "nothing more." if s["pricing"] else
                 "No pricing guidance has been set: if they ask about price, say it depends on "
                 "what they need and %s will come back to them on it directly. Never hint at "
                 "any figure." % s["sender"])
        extra = "Keep it warm and direct."
        if reading.get("ai"):
            extra += (" Their question about whether they are talking to an AI is answered in a "
                      "separate sentence above your text: do not mention it, and never say or "
                      "imply that a human is writing.")
        if "wants-meeting" in [label] + reading["also"]:
            extra = ("They want a meeting. Do NOT propose, accept or suggest any time or day; "
                     "say you will check %s's availability and come back to them."
                     % s["sender"])
        if "wants-demo" in [label] + reading["also"]:
            extra += (" They asked for a demo, and %s." % (
                "you are attaching %s - describe it in one sentence" % demo["describe"]
                if demo else "this specific need is better handled directly: say plainly that "
                "the team will follow up on it, and do not attempt it or promise when"))
        theirs = msg["text"][:2500]
        fact_text = facts(s, lead, theirs)
        if demo:
            fact_text += "\n\nATTACHED: %s" % demo["describe"]
        system = REPLY_SYSTEM % {"sender": s["sender"], "asks": "; ".join(asks)[:600],
                                 "price": price, "extra": extra}
        got, n = _draft(system, fact_text, ("body",), fact_text)
        if got is None:
            body, how = fallback(label, lead, s), "fixed, after %s" % "; ".join(n[:2])
        else:
            body, how = _tidy(got["body"]), "model, attempt %d" % n
    if reading.get("ai"):
        body = AI_LINE % (s["sender"], s["sender"]) + "\n\n" + body
    return _signed(body, s), how


# ------------------------------------------------------------------------------ the three demos

CODE_SYSTEM = (
    "Write a short code sample that answers this business's request for a technical proof, "
    "relevant to what %(sender)s offers (FACTS). Rules: python or javascript only; at most 35 "
    "lines; self-contained, standard library only, no network calls, no credentials, no "
    "placeholders like TODO; brief comments. Reply with JSON only: "
    '{"language": "python|javascript", "filename": "snake_case_name", "summary": "one sentence '
    'saying what it shows", "code": "..."}')
PITCH_SYSTEM = (
    "Write a one-page proposal from %(sender)s for this business, using ONLY the FACTS. No "
    "prices, dates, timelines, statistics or digits; no claims the FACTS do not make; nothing "
    "about the business you were not told. Reply with JSON only: "
    '{"title": "...", "summary": "two sentences", "points": ["three short points: what we '
    'would do"], "fit": "one or two sentences on why it suits them", "next": "one sentence"}')
MOCKUP_SYSTEM = (
    "Write the copy for a simple landing-page mockup for this business, as %(sender)s would "
    "sketch it for them. Use their name and kind of business; invent NO facts about them - no "
    "numbers, years, awards, reviews, prices, addresses or claims of results. Reply with JSON "
    'only: {"headline": "under ten words", "subhead": "one sentence", "features": [{"title": '
    '"two to four words", "text": "one short sentence"}, x3], "cta": "two to four words"}')


def _chrome():
    for p in (os.environ.get("TRONE_CHROME"),
              r"C:\Program Files\Google\Chrome\Application\chrome.exe",
              r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
              os.path.join(os.environ.get("LOCALAPPDATA") or "", r"Google\Chrome\Application"
                                                                 r"\chrome.exe"),
              r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"):
        if p and os.path.isfile(p):
            return p
    return None


def render(page_html, out_path, mode):
    """Headless Chrome, its own throwaway profile, no debugging port (9222 is the harnesses').
    "" on success, else why. A hung Chrome is killed with its whole tree: a stray one spins."""
    chrome = _chrome()
    if not chrome:
        return "there is no Chrome on this machine to draw it with"
    work = tempfile.mkdtemp(prefix="closer-render-")
    page = os.path.join(work, "page.html")
    with open(page, "w", encoding="utf-8") as fh:
        fh.write(page_html)
    args = [chrome, "--headless=new", "--disable-gpu", "--no-first-run",
            "--no-default-browser-check", "--disable-extensions", "--hide-scrollbars",
            "--user-data-dir=" + os.path.join(work, "profile"), "--force-device-scale-factor=1"]
    if mode == "png":
        args += ["--window-size=1280,860", "--screenshot=" + out_path]
    else:
        args += ["--no-pdf-header-footer", "--print-to-pdf=" + out_path]
    args.append(pathlib.Path(page).as_uri())
    try:
        proc = _proc.popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            proc.wait(timeout=60)
        except subprocess.TimeoutExpired:
            _proc.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)],
                      capture_output=True)
            return "Chrome did not finish drawing it in a minute"
    except OSError as exc:
        return "Chrome would not start (%s)" % exc
    finally:
        shutil.rmtree(work, ignore_errors=True)
    if not os.path.isfile(out_path) or os.path.getsize(out_path) < 3000:
        return "Chrome drew nothing worth sending"
    return ""


_PAGE_HEAD = ('<!doctype html><html><head><meta charset="utf-8"><meta http-equiv='
              '"Content-Security-Policy" content="default-src \'none\'; style-src '
              '\'unsafe-inline\'">')


def _palette(name):
    hue = int(hashlib.sha256(name.encode("utf-8")).hexdigest()[:4], 16) % 360
    return "hsl(%d,55%%,32%%)" % hue, "hsl(%d,60%%,95%%)" % hue


def mockup_html(lead, copy, s):
    e = html.escape
    dark, light = _palette(lead["name"])
    feats = "".join('<div class="f"><h3>%s</h3><p>%s</p></div>' % (e(f["title"]), e(f["text"]))
                    for f in copy["features"])
    return _PAGE_HEAD + """<style>
*{box-sizing:border-box;margin:0}body{font-family:Segoe UI,Arial,sans-serif;color:#1d1d1f;
background:#fff;width:1280px}nav{display:flex;justify-content:space-between;align-items:center;
padding:22px 64px;border-bottom:1px solid #eee}nav b{font-size:22px;color:%(dark)s}
nav span{color:#666;margin-left:28px;font-size:15px}.hero{background:%(light)s;
padding:96px 64px 88px}.hero h1{font-size:54px;line-height:1.1;max-width:900px;color:%(dark)s}
.hero p{font-size:22px;color:#444;margin-top:22px;max-width:760px}.cta{display:inline-block;
margin-top:36px;background:%(dark)s;color:#fff;padding:16px 34px;border-radius:8px;
font-size:18px;font-weight:600}.fs{display:flex;gap:28px;padding:72px 64px}.f{flex:1;
border:1px solid #e6e6e6;border-radius:12px;padding:28px}.f h3{font-size:21px;color:%(dark)s}
.f p{margin-top:10px;font-size:16px;color:#555;line-height:1.5}footer{padding:26px 64px;
color:#888;font-size:13px;border-top:1px solid #eee}.tag{background:#1d1d1f;color:#fff;
font-size:13px;padding:7px 64px}</style></head><body>
<div class="tag">Concept mockup prepared by %(sender)s for %(name)s - sample copy, not a live page.</div>
<nav><b>%(name)s</b><div><span>Home</span><span>Services</span><span>About</span>
<span>Contact</span></div></nav>
<section class="hero"><h1>%(headline)s</h1><p>%(subhead)s</p><div class="cta">%(cta)s</div>
</section><section class="fs">%(feats)s</section>
</body></html>""" % {"dark": dark, "light": light, "name": e(lead["name"]),
                              "headline": e(copy["headline"]), "subhead": e(copy["subhead"]),
                              "cta": e(copy["cta"]), "feats": feats, "sender": e(s["sender"])}


def pitch_html(lead, doc, s):
    e = html.escape
    dark, light = _palette(lead["name"])
    points = "".join("<li>%s</li>" % e(p) for p in doc["points"])
    return _PAGE_HEAD + """<style>@page{size:A4;margin:22mm}body{font-family:Georgia,serif;
color:#222;font-size:13pt;line-height:1.55}.band{border-left:6px solid %(dark)s;
background:%(light)s;padding:14px 18px;margin-bottom:22px}h1{font-size:23pt;color:%(dark)s;
margin:0}.for{color:#555;margin-top:6px;font-family:Segoe UI,Arial,sans-serif;font-size:11pt}
h2{font-family:Segoe UI,Arial,sans-serif;font-size:12pt;letter-spacing:.06em;
text-transform:uppercase;color:%(dark)s;margin:22px 0 6px}li{margin:6px 0}
.foot{margin-top:34px;color:#777;font-size:10pt;font-family:Segoe UI,Arial,sans-serif}
</style></head><body><div class="band"><h1>%(title)s</h1><div class="for">A short proposal
for %(name)s, from %(sender)s</div></div><p>%(summary)s</p><h2>What we would do</h2>
<ul>%(points)s</ul><h2>Why it suits %(name)s</h2><p>%(fit)s</p><h2>Next step</h2>
<p>%(next)s</p><div class="foot">%(pricing)s</div></body></html>""" % {
        "dark": dark, "light": light, "title": e(doc["title"]), "name": e(lead["name"]),
        "sender": e(s["sender"]), "summary": e(doc["summary"]), "points": points,
        "fit": e(doc["fit"]), "next": e(doc["next"]),
        "pricing": "Pricing and timelines are agreed with %s directly." % e(s["sender"])}


def _check_code(language, code):
    if len(code.splitlines()) > 60:
        return "it ran to more than sixty lines"
    if language == "python":
        try:
            compile(code, "<sample>", "exec")
        except SyntaxError as exc:
            return "it is not valid Python (%s)" % exc.msg
        return ""
    node = shutil.which("node")
    if not node:
        return "there is no node here to check JavaScript with"
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as fh:
        fh.write(code)
    try:
        done = _proc.run([node, "--check", fh.name], capture_output=True, timeout=20)
        return "" if done.returncode == 0 else "it is not valid JavaScript"
    finally:
        os.remove(fh.name)


def _save(lead, name, data, ctype):
    os.makedirs(DEMO_DIR, exist_ok=True)
    stamp = _now().strftime("%Y%m%d-%H%M%S")
    path = os.path.join(DEMO_DIR, "%s-%s-%s" % (lead["id"], stamp, name))
    if isinstance(data, str):
        data = data.encode("utf-8")
    if data is not None:
        with open(path, "wb") as fh:
            fh.write(data)
    return path


def _attachment(path, name, ctype):
    with open(path, "rb") as fh:
        raw = fh.read()
    return {"file": path, "name": name, "type": ctype, "bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest()}


def _slug(text, n=40):
    return re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-")[:n] or "sample"


def make_demo(kind, lead, msg, s):
    """(demo, "") - {"kind", "describe", "attachment"} - or (None, why). Raises ModelDown.
    Only the three kinds; anything else is the caller's honest "the team will follow up"."""
    fact_text = facts(s, lead, msg["text"][:2500])
    user = fact_text + "\n\nWHAT THEY ASKED:\n" + msg["text"][:1500]
    if kind == "code":
        got, n = _draft(CODE_SYSTEM % {"sender": s["sender"]}, user,
                        ("language", "filename", "summary", "code"), fact_text,
                        check_fields=("summary",))
        if got is None:
            return None, "no code sample passed the checks (%s)" % "; ".join(n[:2])
        language = str(got["language"]).strip().lower()
        if language not in ("python", "javascript"):
            return None, "the sample came back in %s, which I cannot check" % language[:20]
        code = str(got["code"]).strip() + "\n"
        bad = _check_code(language, code)
        if bad:
            return None, "the code sample failed its check: %s" % bad
        name = _slug(got["filename"]).replace("-", "_") + (".py" if language == "python"
                                                           else ".js.txt")
        path = _save(lead, name, code, "text/plain")
        return {"kind": "code", "attachment": _attachment(path, name, "text/plain"),
                "describe": "a short %s sample (%s): %s" % (
                    language.title(), name, _clip(got["summary"], 200))}, ""
    if kind == "pitch":
        got, n = _draft(PITCH_SYSTEM % {"sender": s["sender"]}, user,
                        ("title", "summary", "points", "fit", "next"), fact_text)
        if got is None:
            return None, "no proposal passed the checks (%s)" % "; ".join(n[:2])
        doc = {k: _clip(got[k], 600) for k in ("title", "summary", "fit", "next")}
        doc["points"] = [_clip(p, 300) for p in (got.get("points") or [])][:5]
        if len(doc["points"]) < 2:
            return None, "the proposal came back with fewer than two points"
        name = "proposal-%s.pdf" % _slug(lead["name"])
        path = _save(lead, name, None, "application/pdf")
        why = render(pitch_html(lead, doc, s), path, "pdf")
        if why:
            return None, "the proposal could not be drawn: %s" % why
        return {"kind": "pitch", "attachment": _attachment(path, name, "application/pdf"),
                "describe": "a one-page proposal (%s) titled \"%s\"" % (name, doc["title"])}, ""
    if kind == "mockup":
        got, n = _draft(MOCKUP_SYSTEM % {"sender": s["sender"]}, user,
                        ("headline", "subhead", "features", "cta"), fact_text)
        if got is None:
            return None, "no mockup copy passed the checks (%s)" % "; ".join(n[:2])
        feats = [f for f in (got.get("features") or []) if isinstance(f, dict)
                 and str(f.get("title") or "").strip() and str(f.get("text") or "").strip()][:3]
        if len(feats) < 3:
            return None, "the mockup copy came back with fewer than three features"
        copy = {"headline": _clip(got["headline"], 90), "subhead": _clip(got["subhead"], 200),
                "cta": _clip(got["cta"], 30),
                "features": [{"title": _clip(f["title"], 40), "text": _clip(f["text"], 140)}
                             for f in feats]}
        name = "mockup-%s.png" % _slug(lead["name"])
        path = _save(lead, name, None, "image/png")
        why = render(mockup_html(lead, copy, s), path, "png")
        if why:
            return None, "the mockup could not be drawn: %s" % why
        return {"kind": "mockup", "attachment": _attachment(path, name, "image/png"),
                "describe": "a landing-page mockup image (%s) headed \"%s\"" % (
                    name, copy["headline"])}, ""
    return None, "%s is not one of the three demos this phase makes" % kind


# ------------------------------------------------------------------------------ the work

def _with_email(leads):
    return [r for r in leads if r.get("email")]


def _lead(lead_id):
    leads, _bad = hunter.read_book()
    return next((r for r in leads if r["id"] == lead_id), None)


def _closer_fields(row):
    row.setdefault("closer", {})
    return row["closer"]


def _set(lead_id, status=None, **fields):
    def change(row):
        c = _closer_fields(row)
        c.update({k: v for k, v in fields.items()})
        if status:
            row["status"] = status
    return hunter.update_lead(lead_id, change)


def cold_one(s, daily, note):
    """Write to the next new lead that has an address, if today's cap allows. One per tick: the
    pace is the deliverability, and a cold domain is a blacklisted domain."""
    rows = read_log()
    today = _today()
    done_today = sum(1 for r in rows if r.get("kind") == "cold" and str(r.get("at"))[:10]
                     == today)
    if done_today >= daily:
        return None
    written = {r.get("leadId") for r in rows if r.get("kind") == "cold"}
    own = str((_google().token() or {}).get("email") or "").lower()
    leads, _bad = hunter.read_book()
    nxt = next((r for r in _with_email(leads) if r["status"] == "new"
                and r["id"] not in written and str(r["email"]).lower() != own), None)
    if nxt is None:
        return None
    subject, body, how = draft_cold(nxt, s)
    if subject is None:
        note("cold email to %s held: %s" % (nxt["id"], how))
        return None
    row, err = _send(nxt, "cold", "new lead in the book (%s, %s)" % (
        nxt.get("niche") or "lead", nxt.get("city") or "?"), nxt["email"], subject, body, s,
        how=how)
    if row is None:
        note("cold email to %s not sent: %s" % (nxt["id"], err))
        return None
    if row["status"] == "sent":
        _set(nxt["id"], "contacted", threadId=row["threadId"], coldEntry=row["id"],
             coldAt=row["at"], to=nxt["email"], subject=subject, coldHeaderId=row["headerId"])
        note("cold email to %s (%s) sent as %s" % (nxt["id"], nxt["name"], row["id"]))
    else:
        _set(nxt["id"], "send-failed", coldEntry=row["id"], failedAt=row["at"])
        note("cold email to %s FAILED and will not be retried: %s" % (nxt["id"], err))
    return row


def followups(s, note):
    days = s["followUpAfterDays"]
    if not days:
        return
    rows = read_log()
    leads, _bad = hunter.read_book()
    cutoff = (_now() - datetime.timedelta(days=days)).isoformat(timespec="seconds")
    for lead in leads:
        c = lead.get("closer") or {}
        if lead["status"] != "contacted" or not c.get("threadId") or c.get("handedOver"):
            continue
        mine = [r for r in rows if r.get("leadId") == lead["id"]]
        if any(r.get("kind") == "inbound" for r in mine):
            continue
        if any(r.get("kind") == "followup" for r in mine):
            continue
        cold = next((r for r in mine if r.get("kind") == "cold" and r.get("status") == "sent"),
                    None)
        if not cold or cold["at"] > cutoff:
            continue
        body = _signed("Hello again - just bringing this back to the top of your inbox in case "
                       "it got buried. If a short example of how this could work for %s would "
                       "help, reply and I'll send one over. If not, there's no need to answer: "
                       "this is the last note I'll send." % lead["name"], s)
        subject = "Re: " + str(cold.get("subject") or "")
        row, err = _send(lead, "followup", "no reply %d days after the cold email %s" % (
            days, cold["id"]), cold["to"], subject, body, s, thread_id=c["threadId"],
            inbound={"id": None, "messageId": cold.get("headerId") or ""}, how="fixed")
        note("follow-up to %s: %s" % (lead["id"], row["status"] if row else err))
        return                                  # one per tick, like the cold ones


def _replies_today(rows, lead_id):
    today = _today()
    return sum(1 for r in rows if r.get("leadId") == lead_id and str(r.get("at"))[:10] == today
               and r.get("kind") in ("reply", "demo", "ack") and r.get("status") == "sent")


def answer(lead, msg, reading, s, inbound_row, note):
    """Write back to one message the Closer has read and logged. Raises ModelDown."""
    label = reading["label"]
    rows = read_log()
    if (lead.get("closer") or {}).get("handedOver"):
        update_event(inbound_row["id"], reply="handed over - the employer is answering by hand")
        return
    if _replies_today(rows, lead["id"]) >= REPLIES_PER_LEAD_PER_DAY:
        update_event(inbound_row["id"], reply="held - %d replies to this lead today already"
                     % REPLIES_PER_LEAD_PER_DAY)
        return
    demo, demo_note = None, ""
    if "wants-demo" in [label] + reading["also"]:
        if reading["demo"] in DEMO_KINDS:
            demo, demo_note = make_demo(reading["demo"], lead, msg, s)
        else:
            demo_note = "asked for something none of the three demo kinds fits"
        if demo_note:
            note("demo for %s not made: %s" % (lead["id"], demo_note))
    body, how = draft_reply(lead, msg, reading, s, demo)
    kind = "demo" if demo else ("ack" if label in ("not-interested", "meeting-time") else
                                "reply")
    subject = msg["subject"] if msg["subject"].lower().startswith("re:") else \
        "Re: " + msg["subject"]
    why = "their reply %s read as %s%s" % (inbound_row["id"], label, (
        " (also %s)" % ", ".join(reading["also"])) if reading["also"] else "")
    if reading.get("ai"):
        why += "; they asked whether this is an AI, and were told yes"
    if demo_note and not demo:
        why += "; demo not attempted: " + demo_note
    row, err = _send(lead, kind, why, msg["replyTo"] or msg["from"], subject, body, s,
                     attachments=[demo["attachment"]] if demo else (),
                     thread_id=(lead.get("closer") or {}).get("threadId"), inbound=msg, how=how)
    state = row["status"] if row else "not sent: " + err
    update_event(inbound_row["id"], reply=state, replyEntry=(row or {}).get("id"))
    if demo and row and row["status"] == "sent":
        _set(lead["id"], demo={"kind": demo["kind"], "file": demo["attachment"]["name"],
                               "entry": row["id"]})
    note("%s to %s (%s): %s" % (kind, lead["id"], label, state))


def read_replies(s, note):
    """Read every thread the Closer started, and handle what is new in it."""
    rows = read_log()
    ours = _ours(rows)
    read = {r.get("gmailId"): r for r in rows if r.get("kind") == "inbound"}
    leads, _bad = hunter.read_book()
    budget = INBOUND_PER_TICK
    for lead in leads:
        c = lead.get("closer") or {}
        if not c.get("threadId") or lead["status"] in ("bounced", "send-failed"):
            continue
        thread, err = _google().get_thread(c["threadId"])
        if thread is None:
            note("could not read %s's thread: %s" % (lead["id"], err))
            if "403" in str(err) or "reconnect" in str(err):
                return
            continue
        for raw in thread.get("messages") or []:
            gid = str(raw.get("id") or "")
            labels = raw.get("labelIds") or []
            if gid in ours:
                continue
            if "SENT" in labels:
                # Sent from this mailbox, and not by the Closer: the employer answered by hand.
                if not c.get("handedOver"):
                    _set(lead["id"], handedOver=gid)
                    c["handedOver"] = gid
                    note("%s: the employer wrote in the thread by hand; I stop writing to it"
                         % lead["id"])
                continue
            if gid in read:
                prior = read[gid]
                if str(prior.get("reply") or "").startswith("held") and budget > 0:
                    budget -= 1
                    fresh = _lead(lead["id"]) or lead
                    answer(fresh, parse_message(raw), prior["reading"], s, prior, note)
                continue
            if budget <= 0:
                return
            budget -= 1
            handle_inbound(lead, parse_message(raw), s, note)
            lead = _lead(lead["id"]) or lead
            c = lead.get("closer") or {}


def handle_inbound(lead, msg, s, note):
    reading, err = classify(lead, msg)
    if reading is None:
        raise ModelDown(err)
    label = reading["label"]
    said = requirement(msg["text"])
    row = log_event({"kind": "inbound", "leadId": lead["id"], "business": lead["name"],
                     "from": msg["from"], "gmailId": msg["id"], "subject": msg["subject"],
                     "label": label, "reading": reading, "requirement": said,
                     "status": "read", "reply": "pending"})
    if label == "bounce":
        _set(lead["id"], "bounced", bouncedAt=row["at"])
        cold = (lead.get("closer") or {}).get("coldEntry")
        log_event({"kind": "bounce", "leadId": lead["id"], "business": lead["name"],
                   "to": (lead.get("closer") or {}).get("to"), "status": "failed",
                   "why": "Gmail returned the cold email %s as undeliverable" % cold,
                   "refers": cold})
        update_event(row["id"], reply="none - a bounce")
        note("%s bounced; marked bounced, nothing more goes to it" % lead["id"])
        return
    if label == "auto":
        update_event(row["id"], reply="none - an automatic reply")
        note("%s sent an automatic reply; ignored" % lead["id"])
        return
    status = STATUS_OF[label]
    if lead["status"] in MEETING and status not in ("meeting-confirmed", "not-interested"):
        status = lead["status"]
    fields = {"lastInboundId": msg["id"], "lastInboundAt": row["at"], "asked": label,
              "lastInboundHeader": msg["messageId"],
              "requirement": said, "requirementAt": row["at"],
              "replyTo": msg["replyTo"] or msg["from"]}
    if label == "meeting-time":
        fields["meetingTime"] = said
    if reading["ai"]:
        fields["aiAsked"] = True
    _set(lead["id"], status, **fields)
    note("%s replied: %s - %s" % (lead["id"], label, _clip(said, 80)))
    if label == "unclear":
        update_event(row["id"], reply="none - unclear, left for the employer")
        return
    try:
        answer(_lead(lead["id"]) or lead, msg, reading, s, row, note)
    except ModelDown as exc:
        update_event(row["id"], reply="held - the model could not be asked (%s)" % str(exc)[:80])
        raise


def google_ready():
    g = _google()
    _bearer, state, why = g.access()
    if state != "connected":
        return why or "Google is not connected"
    for scope in ("gmail.send", "gmail.readonly"):
        if not g.has_scope(scope):
            return ("the Google connection does not carry %s, so it wants reconnecting from the "
                    "Command Panel" % scope)
    return ""


def tick(note=None):
    """One pass: read replies and answer them, one follow-up, one cold email. Returns the notes."""
    notes = []

    def say(line):
        notes.append(line)
        if note:
            note(line)
    state = read_state()
    if not state.get("on"):
        say("the Closer is off")
        return notes
    s, problems = settings()
    if problems:
        say("not working: " + problems[0])
        return notes
    why = google_ready()
    if why:
        say("not working: " + why)
        return notes
    try:
        read_replies(s, say)
        followups(s, say)
        cold_one(s, int(state.get("daily") or DEFAULT_DAILY), say)
    except ModelDown as exc:
        global _hold_until
        wait = backoff_s(exc)
        _hold_until = time.time() + wait
        say("held until the model answers again%s: %s" % (
            " (not asking for %d min)" % round(wait / 60) if wait >= 60 else "",
            str(exc)[:160]))
    except OSError as exc:
        say("stopped this tick: %s" % exc)
    return notes


# ------------------------------------------------------------------------------ the employer's word

_FILLER = {"the", "a", "an", "and", "of", "dr", "clinic", "dental", "pvt", "ltd", "private",
           "limited", "india", "company", "co"}


def _words(text):
    return {w for w in re.sub(r"[^a-z0-9 ]+", " ", str(text).lower()).split()
            if len(w) > 2 and w not in _FILLER}


def find_lead(words):
    """(lead, "") or (None, why) for a name or an id the employer said."""
    leads, _bad = hunter.read_book()
    m = re.search(r"\bH-?(\d{1,6})\b", words, re.I)
    if m:
        want = "H-%04d" % int(m.group(1))
        hit = next((r for r in leads if r["id"] == want), None)
        return (hit, "") if hit else (None, "there is no lead %s in the book" % want)
    q = hunter._norm_name(words)
    if not q:
        return None, "I did not catch which business"
    exact = [r for r in leads if hunter._norm_name(r["name"]) == q]
    near = exact or [r for r in leads if q in hunter._norm_name(r["name"])
                     or (len(hunter._norm_name(r["name"])) > 3
                         and hunter._norm_name(r["name"]) in q)]
    if not near:
        qs = _words(words)
        scored = sorted(((len(qs & _words(r["name"])), r) for r in leads), key=lambda t: -t[0])
        near = [r for n, r in scored if n and n == scored[0][0]] if scored and scored[0][0] \
            else []
    talking = [r for r in near if (r.get("closer") or {}).get("threadId")]
    near = talking or near
    if len(near) == 1:
        return near[0], ""
    if not near:
        return None, "no business in the leads book is called anything like %r" % words[:60]
    return None, "that could be %s - say which, or use its H- number" % ", ".join(
        "%s (%s)" % (r["name"], r["id"]) for r in near[:3])


_MEETING_EN = re.compile(r"^(?:please\s+)?(?:(?:can|could|would)\s+you\s+)?(?:lock|book|fix|set\s+"
                         r"up|schedule|arrange|line\s+up)\s+(?:in\s+)?(?:a\s+|the\s+)?(?:meeting|"
                         r"call)\s+with\s+(?P<who>.+?)(?:\s+(?P<when>(?:on|at|for|this|next|"
                         r"tomorrow|today|between|around)\b.*))?[.!]?$", re.I)
_MEETING_HI = re.compile(r"^(?P<who>.+?)\s+(?:ke\s+saath|ke\s+sath|se)\s+(?:(?P<when>.+?)\s+)?"
                         r"(?:meeting|call)\s+(?:lock|fix|set|book|schedule)\s*(?:karo|kar\s+do|"
                         r"kardo)\b.*$", re.I)
_REPORT = re.compile(r"\b(?:today'?s|todays)\s+(?:leads?|lead\s+(?:update|report))\b|"
                     r"\baaj\s+k[ae]\s+(?:leads?|update)\b|\bleads?\s+(?:ka\s+)?(?:update|report|"
                     r"status|haal)\b|\bcloser\s+(?:update|report|status)\b|\bhow\s+are\s+(?:the\s+"
                     r")?leads\b|\bupdate\s+on\s+(?:the\s+)?leads\b", re.I)
_START = re.compile(r"^(?:please\s+)?(?:(?:can|could|would)\s+you\s+)?(?:start|turn\s+on|switch\s+on|"
                    r"resume|begin|run|chalu\s+karo|shuru\s+karo)\s+(?:the\s+)?closer\b|"
                    r"^closer\s+(?:chalu|shuru|start|on)\s*(?:karo|kar\s+do)?\b", re.I)
_STOP = re.compile(r"\b(?:stop|pause|halt|turn\s+off|switch\s+off|kill)\s+(?:the\s+)?closer\b|"
                   r"^closer\s+(?:band|bandh|ruko|roko|off|stop)\b", re.I)


def parse_request(sentence):
    """{"action": report|start|stop|meeting, ...} for the employer's sentence, or None."""
    text = " ".join(str(sentence or "").split()).strip()
    if not text:
        return None
    if text.endswith("?"):
        if not re.match(r"(?:please\s+)?(?:can|could|would)\s+you\b", text, re.I):
            return {"action": "report"} if _REPORT.search(text) else None
        text = text.rstrip("?").strip()
    if _STOP.search(text):
        return {"action": "stop"}
    if _START.search(text):
        return {"action": "start"}
    m = _MEETING_EN.match(text) or _MEETING_HI.match(text)
    if m:
        who = re.sub(r"^(?:the\s+)?", "", m.group("who")).strip(" ,.")
        # "on Friday at 4pm" is kept as "Friday at 4pm": it is spoken back on the card and
        # written into "Would ... work for you?", where a leading on/for/at does not belong.
        when = re.sub(r"^(?:on|for|at)\s+", "", (m.group("when") or "").strip(" ,."), flags=re.I)
        when = _clip(when, 120)
        return {"action": "meeting", "who": who, "when": when}
    if _REPORT.search(text):
        return {"action": "report"}
    return None


def describe_start(params):
    leads, _bad = hunter.read_book()
    written = {r.get("leadId") for r in read_log() if r.get("kind") == "cold"}
    n = sum(1 for r in _with_email(leads) if r["status"] == "new" and r["id"] not in written)
    return ("email the %d new lead%s in the book that %s an address, at most %d a day, then read "
            "their replies and answer them on my own" % (n, "" if n == 1 else "s",
                                                        "has" if n == 1 else "have",
                                                        int(params.get("daily") or 0)))


def describe_meeting(params):
    lead = _lead(str(params.get("lead") or ""))
    if not lead:
        return ""
    when = str(params.get("when") or "").strip()
    return "write to %s (%s) asking for a meeting%s" % (
        lead["name"], lead["id"], (" - offering %s" % when) if when else
        ", and ask them which times suit them")


def propose_meeting(lead_id, when=""):
    """THE EMPLOYER'S MEETING EMAIL, after his yes on the lock_meeting card. (line, ok)."""
    s, problems = settings()
    if problems:
        return "I could not write to them: %s." % problems[0], False
    why = google_ready()
    if why:
        return "I could not write to them: %s." % why, False
    lead = _lead(lead_id)
    if not lead:
        return "There is no lead %s in the book, so nothing was sent." % lead_id, False
    c = lead.get("closer") or {}
    to = c.get("replyTo") or c.get("to") or lead.get("email")
    if not to:
        return "%s has no email address, so nothing was sent." % lead["name"], False
    when = " ".join(str(when or "").split())[:120]
    ask = ("Would %s work for you? If not, just suggest a time that suits you." % when if when
           else "Could you share a few times that suit you?")
    body = _signed("Hello,\n\nThank you for the conversation so far. %s would like to set up a "
                   "short call with %s to talk it through properly. %s"
                   % (s["sender"], lead["name"], ask), s)
    subject = "Re: " + c["subject"] if c.get("subject") else "Meeting with %s" % s["sender"]
    inbound = {"id": None, "messageId": c.get("lastInboundHeader") or c.get("coldHeaderId", "")}
    row, err = _send(lead, "meeting", "the employer said: lock a meeting%s" % (
        " (%s)" % when if when else ""), to, subject, body, s,
        thread_id=c.get("threadId"), inbound=inbound, by="employer", how="fixed")
    if row is None or row["status"] != "sent":
        return "The meeting email to %s did not go: %s. It will not be retried on its own." % (
            lead["name"], err), False
    _set(lead["id"], "meeting-proposed", meetingAsked=when or "their choice",
         meetingEntry=row["id"], threadId=c.get("threadId") or row["threadId"])
    return ("Written to %s asking for a meeting%s, sir - Gmail's id for it is %s. When they "
            "answer with a time I'll mark it confirmed." % (
                lead["name"], " (%s)" % when if when else "", row["gmailId"])), True


# ------------------------------------------------------------------------------ the report

def _names(rows, n=6):
    out = ["%s (%s)" % (r["name"], SAY_LABEL.get(r["status"], r["status"])) for r in rows[:n]]
    if len(rows) > n:
        out.append("and %d more" % (len(rows) - n))
    return out


def report(day=None, boss="sir"):
    """THE ON-ASK REPORT, from the book and the log - never from the conversation's memory."""
    day = day or _today()
    try:
        rows = read_log()
    except OSError as exc:
        return str(exc) + "."
    leads, _bad = hunter.read_book()
    by_id = {r["id"]: r for r in leads}
    todays = [r for r in rows if str(r.get("at"))[:10] == day]
    cold = [r for r in todays if r.get("kind") == "cold"]
    sent = [r for r in cold if r.get("status") == "sent"]
    failed = [r for r in todays if r.get("kind") in SEND_KINDS + ("bounce",)
              and r.get("status") in ("failed", "sending")]
    follow = [r for r in todays if r.get("kind") == "followup" and r.get("status") == "sent"]
    approached = {r.get("leadId") for r in todays if r.get("kind") in ("cold", "followup")}
    inbound = [r for r in todays if r.get("kind") == "inbound"
               and r.get("label") not in ("auto", "bounce")]
    answered = [r for r in todays if r.get("kind") in ("reply", "demo", "ack")
                and r.get("status") == "sent"]
    demos = [r for r in answered if r.get("kind") == "demo"]
    parts = []
    if not todays:
        parts.append("Nothing went out and nothing came back today, %s." % boss)
    else:
        line = "Today, %s: %d lead%s approached and %d cold email%s sent" % (
            boss, len(approached), "" if len(approached) == 1 else "s", len(sent),
            "" if len(sent) == 1 else "s")
        if follow:
            line += ", plus %d follow-up%s" % (len(follow), "" if len(follow) == 1 else "s")
        parts.append(line + ".")
        if failed:
            parts.append("%d send%s failed and %s not retried: %s." % (
                len(failed), "" if len(failed) == 1 else "s",
                "was" if len(failed) == 1 else "were",
                "; ".join("%s - %s" % (r.get("business"), _clip(r.get("error") or r.get("why")
                                                                 or "outcome never written - "
                                                                 "check Sent", 70))
                          for r in failed[:4])))
        if inbound:
            told = []
            for r in inbound[:6]:
                told.append("%s %s: \"%s\"" % (r.get("business"), SAY_LABEL.get(
                    r.get("label"), r.get("label")), _clip(r.get("requirement"), 140)))
            parts.append("%d repl%s came in. %s." % (len(inbound), "y" if len(inbound) == 1
                                                     else "ies", ". ".join(told)))
        if answered:
            parts.append("I answered %d of them%s." % (len(answered), (
                ", %d with a demo attached" % len(demos)) if demos else ""))
    waiting = [r for r in leads if r["status"] in ENGAGED]
    if waiting:
        parts.append("Waiting on your meeting decision: %s. Say \"lock a meeting with\" and the "
                     "name for any of them." % ", ".join(_names(waiting)))
    confirmed = [r for r in leads if r["status"] == "meeting-confirmed"]
    if confirmed:
        parts.append("Meetings confirmed: %s." % "; ".join(
            "%s - \"%s\"" % (r["name"], _clip((r.get("closer") or {}).get("meetingTime"), 80))
            for r in confirmed[:4]))
    state = read_state()
    written = {r.get("leadId") for r in rows if r.get("kind") == "cold"}
    left = sum(1 for r in _with_email(leads) if r["status"] == "new" and r["id"] not in written)
    parts.append("The Closer is %s; %d new lead%s with an address still to write to." % (
        "on" if state.get("on") else "off", left, "" if left == 1 else "s"))
    return " ".join(parts)


# ------------------------------------------------------------------------------ the daemon

class Closer:
    """The Scholar's shape: its own thread, its own lock, and no lock of the server's. It acts
    only while closer-state.json says on, and then once every tickSeconds."""

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
                "lastNotes": last["notes"][-6:]}

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
                notes = tick(note=lambda line: sys.stderr.write("  closer: %s\n" % line))
            except Exception as exc:                           # noqa: BLE001
                notes = ["the tick threw (%s: %s)" % (type(exc).__name__, str(exc)[:120])]
                sys.stderr.write("  closer: %s\n" % notes[0])
            with self._lock:
                self._last = {"at": time.time(), "notes": notes, "busy": False}

    def start(self):
        if self._thread is not None:
            return False
        self._thread = threading.Thread(target=self._loop, name="closer-tick", daemon=True)
        self._thread.start()
        return True

    def stop(self):
        self._stop.set()
        self._wake.set()


MANAGER = Closer()


# ------------------------------------------------------------------------------ by hand

def _main(argv):                                               # pragma: no cover
    if argv[:1] == ["report"]:
        print(report())
        return 0
    if argv[:1] == ["log"]:
        for r in read_log()[-int(argv[1] if len(argv) > 1 else 15):]:
            print("%s %s %-8s %-7s %-6s %-34s %s" % (
                r["id"], r["at"], r.get("kind"), r.get("status"), r.get("leadId"),
                _clip(r.get("business"), 34), _clip(r.get("why") or r.get("requirement"), 70)))
        return 0
    if argv[:1] == ["tick"]:
        import server
        configure(chat=lambda m: server.call_groq(server.load_config()[0], m),
                  config=lambda: server.load_config()[0])
        for line in tick():
            print(line)
        return 0
    s, problems = settings()
    state = read_state()
    leads, _bad = hunter.read_book()
    counts = {}
    for r in leads:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    print("The Closer is %s. %s" % ("on" if state.get("on") else "off", "; ".join(
        problems) or "The offer sheet is filled in."))
    print("Book: %s. Log: %d rows." % (", ".join("%d %s" % (n, k) for k, n in counts.items()),
                                       len(read_log())))
    return 0


if __name__ == "__main__":                                     # pragma: no cover
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:                                          # noqa: BLE001
        pass
    sys.exit(_main(sys.argv[1:]))
