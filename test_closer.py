"""The Closer, phase 1: every rule that can be proved without a real mailbox.

The whole loop runs here against a FAKE Gmail and a SCRIPTED model: a cold email goes out, a
reply comes back into its thread, is read, classified and answered; a demo is made (with the
real headless Chrome) and attached; a meeting is asked for on the employer's word and confirmed
when the business names a time; the report is read off the book and the log. And every rule in
closer.py's never-list is pushed on: an invented price, a claim to be human, a second cold email,
a third unsolicited one, a retried failure, a duplicate answer, the employer writing by hand.
The real thing - a real email in Sent, a real reply read - was measured live; see README
"The Closer".

Run it:  python test_closer.py
Exit status is the number of failures.
"""
import base64
import datetime
import email
import email.policy
import json
import os
import pathlib
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
TMP = tempfile.mkdtemp(prefix="closer-test-")
CONFIG = os.path.join(TMP, "config.json")
os.environ.update({"TRONE_LEADS_PATH": os.path.join(TMP, "leads.json"),
                   "TRONE_CLOSER_LOG": os.path.join(TMP, "closer-log.json"),
                   "TRONE_CLOSER_STATE": os.path.join(TMP, "closer-state.json"),
                   "TRONE_CLOSER_DEMOS": os.path.join(TMP, "demos"),
                   "TRONE_CLOSER_CONFIG": CONFIG})
sys.path.insert(0, str(HERE))

import hands                                                   # noqa: E402
import hunter                                                  # noqa: E402
import closer                                                  # noqa: E402
from tools import _proc                                        # noqa: E402

REAL_TOOLS = hands.LEDGER_PATH
hands.LEDGER_PATH = pathlib.Path(TMP) / "tools-ledger.json"
FAILURES = []
NOTES = []


def check(label, got, want):
    ok = got == want
    print("  %s %s" % ("ok  " if ok else "FAIL", label))
    if not ok:
        print("       got  %r\n       want %r" % (got, want))
        if NOTES:
            print("       the last tick said: %s" % " | ".join(NOTES))
        FAILURES.append(label)


OFFER = {"closer": {"offer": {
    "service": "WhatsApp appointment reminders for clinics",
    "details": ["Reminders go out on WhatsApp the day before each appointment",
                "Patients can confirm or reschedule by replying"],
    "pricing": "",
    "faq": [{"q": "Do patients need an app?", "a": "No - it works in their normal WhatsApp."}],
    "senderName": "Aditya Singh", "signature": "Aditya Singh\nGalaxy Studio"},
    "followUpAfterDays": 4}}
with open(CONFIG, "w", encoding="utf-8") as fh:
    json.dump(OFFER, fh)


# ------------------------------------------------------------------------------ the fakes

def b64(text):
    return base64.urlsafe_b64encode(text.encode("utf-8")).decode("ascii").rstrip("=")


class FakeGmail:
    """Gmail as the Closer sees it: send, read a thread, who am I. Nothing leaves the process."""

    def __init__(self):
        self.sent, self.threads, self.fail_next, self.n = [], {}, None, 0

    def token(self):
        return {"email": "boss@example.org"}

    def access(self):
        return "bearer", "connected", ""

    def has_scope(self, name):
        return True

    def send_message(self, raw, thread_id=None):
        if self.fail_next:
            why, self.fail_next = self.fail_next, None
            return None, why
        self.n += 1
        gid, tid = "s%04d" % self.n, thread_id or "t%04d" % self.n
        msg = email.message_from_bytes(raw, policy=email.policy.default)
        self.sent.append({"id": gid, "threadId": tid, "msg": msg, "toThread": thread_id})
        self.threads.setdefault(tid, []).append(
            {"id": gid, "threadId": tid, "labelIds": ["SENT"], "internalDate": "1",
             "payload": {"mimeType": "text/plain", "headers": [], "body": {"data": b64("x")}}})
        return {"id": gid, "threadId": tid}, ""

    def get_thread(self, tid):
        return {"id": tid, "messages": list(self.threads.get(tid, []))}, ""

    def arrive(self, tid, text, frm="Front Desk <desk@testdental.example>", subject=None,
               labels=("INBOX",), headers=()):
        self.n += 1
        gid = "r%04d" % self.n
        hdrs = [{"name": "From", "value": frm},
                {"name": "Subject", "value": subject or "Re: A note for Test Dental"},
                {"name": "Message-ID", "value": "<in-%d@testdental.example>" % self.n}]
        hdrs += [{"name": k, "value": v} for k, v in headers]
        self.threads.setdefault(tid, []).append(
            {"id": gid, "threadId": tid, "labelIds": list(labels), "internalDate": "2",
             "payload": {"mimeType": "text/plain", "headers": hdrs,
                         "body": {"data": b64(text)}}})
        return gid


class Script:
    """The model, scripted by what the system prompt is asking for."""

    def __init__(self):
        self.down = False
        self.classify = {}
        self.reply = "Hello! Thanks for writing back - happy to help with that."
        self.unsupported = []
        self.calls = []

    def __call__(self, messages):
        system, user = messages[0]["content"], messages[1]["content"]
        self.calls.append(system[:30])
        if self.down:
            return None, "Rate limit reached for model qwen (HTTP 429)"
        if system.startswith("You are a strict fact-checker"):
            return json.dumps({"unsupported": self.unsupported}), None
        if system.startswith("You read one email"):
            return json.dumps(self.classify), None
        if system.startswith("You write one short, personal first email"):
            return json.dumps({"subject": "Reminders for Test Dental", "body":
                               "Hello Test Dental team,\n\nAditya Singh sets up WhatsApp "
                               "appointment reminders for clinics, so patients can confirm or "
                               "reschedule by replying. It might help a dental practice keep "
                               "its day on track.\n\nWould a short example be useful?\n\n"
                               "Best regards,\nAditya"}), None
        if system.startswith("You write a short reply"):
            return json.dumps({"body": self.reply}), None
        if system.startswith("Write the copy for a simple landing-page mockup"):
            return json.dumps({"headline": "Gentle dental care", "subhead": "Book and get "
                               "reminded on WhatsApp.", "cta": "Book a visit", "features": [
                                   {"title": "Easy booking", "text": "Pick a slot."},
                                   {"title": "Reminders", "text": "A nudge the day before."},
                                   {"title": "Reschedule", "text": "Reply to move a visit."}]}), \
                None
        if system.startswith("Write a short code sample"):
            return json.dumps({"language": "python", "filename": "reminder_text",
                               "summary": "Builds the reminder message for one appointment.",
                               "code": "def reminder(name, when):\n    return 'Hi ' + name + "
                                       "', see you ' + when\n"}), None
        return None, "unscripted prompt"


GMAIL, MODEL = FakeGmail(), Script()
closer.configure(chat=MODEL, gmail=GMAIL)


def tick():
    del NOTES[:]
    return closer.tick(note=NOTES.append)


def book(lead_id):
    return next(r for r in hunter.read_book()[0] if r["id"] == lead_id)


def log(kind=None):
    return [r for r in closer.read_log() if kind is None or r.get("kind") == kind]


# ------------------------------------------------------------------------------ vet()

print("VET - what no draft may say")
FACTS = closer.facts(closer.settings()[0])
check("a plain, grounded sentence passes",
      closer.vet("Aditya sets up WhatsApp reminders so patients can confirm by replying.", FACTS),
      [])
for label, text in (
        ("an invented price", "It costs Rs 4,999 a month."),
        ("an invented number", "We work with 40 clinics."),
        ("a free offer nobody made", "The first month is free."),
        ("a timeline", "We can have it live within two days."),
        ("next week", "We could start next week."),
        ("a claim to be human", "I'm a real person, not a bot."),
        ("having seen their website", "I visited your website and loved it."),
        ("an invented link", "See www.example-demo.com for more."),
        ("a placeholder", "Hello [Clinic Name], hope you are well.")):
    check("rejects %s" % label, bool(closer.vet(text, FACTS)), True)
check("a number THEY wrote may be repeated back",
      closer.vet("Happy to cover all 3 of your branches.", FACTS + "\nTHEIR MESSAGE:\nwe have 3 "
                 "branches"), [])
check("a price in the pricing guidance may be quoted",
      closer.vet("Setup is Rs 5,000.", FACTS + "\nPRICING GUIDANCE: Setup is Rs 5,000."), [])
check("the model's own sign-off is cut - the signature is the employer's",
      closer._tidy("Hello there,\n\nA short note.\n\nWould that help?\n\nBest regards,\nAditya"),
      "Hello there,\n\nA short note.\n\nWould that help?")

# ------------------------------------------------------------------------------ the sentences

print("THE SENTENCES")
for text, want in (
        ("today's leads", "report"), ("aaj ka update do", "report"),
        ("leads ka update", "report"), ("stop the closer", "stop"), ("closer band karo", "stop"),
        ("start the closer", "start"), ("lock a meeting with Test Dental", "meeting"),
        ("Could you lock a meeting with Test Dental?", "meeting"),
        ("Test Dental ke saath meeting fix karo", "meeting")):
    check("%r -> %s" % (text, want), (closer.parse_request(text) or {}).get("action"), want)
for text in ("what is a closer?", "lock the door", "find me 20 dentists in Pune",
             "stop the music"):
    check("%r is not the Closer's" % text, closer.parse_request(text), None)
check("the employer's own time is kept as he said it",
      closer.parse_request("lock a meeting with Test Dental on Friday at 4pm"),
      {"action": "meeting", "who": "Test Dental", "when": "Friday at 4pm"})

# ------------------------------------------------------------------------------ the offer sheet

print("THE OFFER SHEET")
check("an empty sheet is two named refusals",
      [p.split(" ")[0] for p in closer.settings({})[1]],
      ["closer.offer.service", "closer.offer.senderName"])
check("this one is complete", closer.settings()[1], [])

# ------------------------------------------------------------------------------ the book

print("THE BOOK")
for found in ({"name": "Test Dental", "category": "dentist", "email": "desk@testdental.example",
               "emailFrom": "test"},
              {"name": "Smile Studio", "category": "dentist", "email": "hi@smile.example",
               "emailFrom": "test"},
              {"name": "Phone Only Clinic", "category": "dentist", "phone": "+91 98220 00000",
               "phoneFrom": "test"},
              {"name": "The Boss Himself", "category": "dentist", "email": "boss@example.org",
               "emailFrom": "test"}):
    hunter.add_lead(dict(found, via=["openstreetmap"]), "dentists", "Pune")
row, err = hunter.update_lead("H-0001", lambda r: r.update(status="no-such-status"))
check("update_lead refuses a status the book does not know", (row, "unreadable" in err),
      (None, True))
check("and the row is untouched", book("H-0001")["status"], "new")
check("the lock file is gone after every write",
      os.path.exists(os.environ["TRONE_LEADS_PATH"] + ".lock"), False)

# ------------------------------------------------------------------------------ the switch

print("THE SWITCH")
check("off by default: a tick does nothing", (tick(), GMAIL.sent), (["the Closer is off"], []))
closer.switch(True, "test", daily=1)

# ------------------------------------------------------------------------------ cold

print("COLD EMAIL")
tick()
check("one cold email went", len(GMAIL.sent), 1)
cold = GMAIL.sent[0]["msg"]
text = cold.get_content()
check("to the lead's own address", cold["To"], "desk@testdental.example")
check("from the employer, by name", cold["From"], "Aditya Singh <boss@example.org>")
check("it names the business", "Test Dental" in text, True)
check("the model's sign-off was replaced by the employer's signature",
      (text.count("Best regards"), text.rstrip().endswith("Aditya Singh\nGalaxy Studio")),
      (0, True))
check("it says how to make it stop", 'just reply "no"' in text, True)
lead = book("H-0001")
check("the lead is contacted, with the thread recorded",
      (lead["status"], lead["closer"]["threadId"]), ("contacted", GMAIL.sent[0]["threadId"]))
c0 = log("cold")[0]
check("the log has it: sent, to whom, why, Gmail's id",
      (c0["status"], c0["to"], c0["gmailId"], "new lead" in c0["why"]),
      ("sent", "desk@testdental.example", "s0001", True))
tick()
check("the daily cap holds: no second cold email today", len(GMAIL.sent), 1)

closer.switch(True, "test", daily=5)
GMAIL.fail_next = "Gmail refused it (HTTP 500)"
tick()
check("a failed send is logged failed and the lead marked send-failed",
      (log("cold")[1]["status"], book("H-0002")["status"]), ("failed", "send-failed"))
sent_before = len(GMAIL.sent)
tick()
check("and it is never retried", [r["leadId"] for r in log("cold")], ["H-0001", "H-0002"])
check("a lead with no email and the employer's own address are never written to",
      [r["leadId"] for r in log("cold") if r["leadId"] in ("H-0003", "H-0004")], [])
row, err = closer._send(book("H-0001"), "cold", "test", "desk@testdental.example", "x", "y",
                        closer.settings()[0])
check("_send itself refuses a second cold email to the same lead", (row, "already" in err),
      (None, True))

# ------------------------------------------------------------------------------ a reply, a demo

print("A REPLY ASKING FOR A DEMO, AND WHETHER THIS IS AN AI")
tid = book("H-0001")["closer"]["threadId"]
ask = ("Interesting. Can you show me a mockup of what our landing page could look like? "
       "Also - are you an AI?\n\nOn Wed, 14 Oct 2026 at 10:00, Aditya Singh <boss@example.org> "
       "wrote:\n> Hello Test Dental team, ...")
GMAIL.arrive(tid, ask)
# Groq's measured mistake, scripted: it also claims a meeting ask, quoting words they never wrote.
MODEL.classify = {"demo": "Can you show me a mockup of what our landing page could look like?",
                  "demoKind": "mockup", "meeting": "let's set up a call next week",
                  "questions": ["are you an AI?"]}
MODEL.reply = "Hello! Here is the landing-page sketch you asked for."
sent_before = len(GMAIL.sent)
tick()
check("one reply went", len(GMAIL.sent) - sent_before, 1)
reply = GMAIL.sent[-1]
body = reply["msg"].get_body(("plain",)).get_content()
check("into the same thread", reply["toThread"], tid)
check("as a reply to their message", reply["msg"]["In-Reply-To"],
      "<in-%d@testdental.example>" % (GMAIL.n - 1))
check("it answers 'are you an AI' with yes, first", body.startswith("To answer your question "
                                                                     "directly: yes"), True)
att = [p for p in reply["msg"].iter_attachments()]
check("with the mockup attached as a PNG",
      [(p.get_content_type(), p.get_filename()) for p in att],
      [("image/png", "mockup-test-dental.png")])
check("a real image, drawn by Chrome", len(att[0].get_content()) > 10000, True)
lead = book("H-0001")
check("an ask quoted from words they never wrote is dropped - no invented meeting",
      [r["reading"] for r in log("inbound")][-1]["also"], [])
check("the lead now wants a demo, and their words are kept verbatim, without the quote",
      (lead["status"], lead["closer"]["requirement"]),
      ("wants-demo", "Interesting. Can you show me a mockup of what our landing page could look "
                     "like? Also - are you an AI?"))
d = log("demo")[-1]
check("the log says what was sent and why",
      (d["status"], d["attachments"][0]["name"], "wants-demo" in d["why"],
       "AI" in d["why"]), ("sent", "mockup-test-dental.png", True, True))
check("the demo file is kept, byte for byte", os.path.getsize(d["attachments"][0]["file"]),
      d["attachments"][0]["bytes"])
sent_before = len(GMAIL.sent)
tick()
check("read again, it is not answered twice", len(GMAIL.sent), sent_before)

# ------------------------------------------------------------------------------ price, invented

print("A PRICE QUESTION, WITH NO PRICING SET AND A MODEL THAT INVENTS ONE")
GMAIL.arrive(tid, "OK. And what would this cost us per month?")
MODEL.classify = {"price": "what would this cost us per month?"}
MODEL.reply = "It is only Rs 2,999 per month, and the first month is free!"
tick()
body = GMAIL.sent[-1]["msg"].get_content()
check("no invented number went out", any(ch.isdigit() for ch in body.split("\n\n")[0]), False)
check("the fixed honest line went instead",
      "Aditya Singh will come back to you on that directly" in body, True)
check("and the log says why", log("reply")[-1]["draft"].startswith("fixed, after"), True)

# ------------------------------------------------------------------------------ an unsupported claim

print("A QUESTION, AND A DRAFT THE CHECKER CATCHES")
GMAIL.arrive(tid, "Does it also work with SMS?")
MODEL.classify = {"questions": ["Does it also work with SMS?"]}
MODEL.reply = "Yes, it works with SMS too."
MODEL.unsupported = ["it works with SMS too"]
tick()
MODEL.unsupported = []
body = GMAIL.sent[-1]["msg"].get_content()
check("a capability not in the offer sheet never goes out", "SMS too" in body, False)

# ------------------------------------------------------------------------------ the model down

print("A DENIAL OF BEING AN AI, UNDER THE YES")
GMAIL.arrive(tid, "Are you a bot? And do patients need an app?")
MODEL.classify = {"questions": ["do patients need an app?"]}
MODEL.reply = "Hi! You are not speaking to a bot. No - it works in their normal WhatsApp."
tick()
body = GMAIL.sent[-1]["msg"].get_content()
check("the yes is there, and the model's 'not speaking to a bot' never went out",
      (body.startswith("To answer your question directly: yes"), "not speaking to a bot" in body),
      (True, False))

print("WHEN GROQ CANNOT BE ASKED")
GMAIL.arrive(tid, "One more thing - can we talk on a call?")
MODEL.down = True
sent_before, read_before = len(GMAIL.sent), len(log("inbound"))
tick()
check("nothing is sent and the message is not marked read",
      (len(GMAIL.sent) - sent_before, len(log("inbound")) - read_before), (0, 0))
check("the tick says it is waiting", any("held until the model" in n for n in NOTES), True)
check("Groq's daily refusal holds the daemon a quarter hour, not one tick",
      closer.backoff_s("on tokens per day (TPD): Limit 200000, Used 199693, Requested 432. "
                       "Please try again in 54s."), closer.TPD_WAIT_S)
check("any other refusal waits as long as Groq says",
      round(closer.backoff_s("Please try again in 3m7.05s.")), 187)
closer._hold_until = 0.0
MODEL.down = False
MODEL.classify = {"meeting": "can we talk on a call?"}
MODEL.reply = ("Glad to hear it! I'll check Aditya Singh's availability and come back to you "
               "with times.")
tick()
check("when it answers again, the waiting message is handled",
      (book("H-0001")["status"], len(GMAIL.sent) - sent_before), ("wants-meeting", 1))

# ------------------------------------------------------------------------------ the report

print("THE REPORT")
said = closer.report()
check("it counts today's approaches and cold emails",
      said.startswith("Today, sir: 2 leads approached and 1 cold email sent."), True)
check("it names the failure and that it was not retried",
      "1 send failed and was not retried: Smile Studio" in said, True)
check("it quotes what the business asked, in their words",
      'Test Dental wants a demo: "Interesting. Can you show me a mockup' in said, True)
check("and who waits on the employer's decision",
      "Waiting on your meeting decision: Test Dental (wants a meeting)" in said, True)

# ------------------------------------------------------------------------------ the meeting

print("THE MEETING - ONLY ON THE EMPLOYER'S WORD")
check("the Closer never asked for one by itself", log("meeting"), [])
line, ok = closer.propose_meeting("H-0001", "Friday at 4pm")
check("the employer's meeting email goes", ok, True)
m = GMAIL.sent[-1]["msg"]
check("in the thread, offering the time he named",
      (GMAIL.sent[-1]["toThread"], "Would Friday at 4pm work for you?" in m.get_content()),
      (tid, True))
check("the lead is meeting-proposed", book("H-0001")["status"], "meeting-proposed")
GMAIL.arrive(tid, "Friday at 4pm works for us.")
MODEL.classify = {"meetingTime": "Friday at 4pm works for us."}
tick()
lead = book("H-0001")
check("their time confirms it, in their own words",
      (lead["status"], lead["closer"]["meetingTime"]),
      ("meeting-confirmed", "Friday at 4pm works for us."))
check("and the acknowledgement is the fixed one", "noted" in GMAIL.sent[-1]["msg"].get_content(),
      True)

# ------------------------------------------------------------------------------ the employer by hand

print("THE EMPLOYER ANSWERS BY HAND")
GMAIL.arrive(tid, "Thanks, see you Friday - Aditya", frm="Aditya <boss@example.org>",
             labels=("SENT",))
GMAIL.arrive(tid, "Great, could you also send the proposal?")
MODEL.classify = {"demo": "could you also send the proposal?", "demoKind": "pitch"}
sent_before = len(GMAIL.sent)
tick()
check("the Closer stops writing to that lead", len(GMAIL.sent), sent_before)
check("and still reads it for the report",
      log("inbound")[-1]["reply"].startswith("handed over"), True)

# ------------------------------------------------------------------------------ bounces, opt-outs

print("A BOUNCE, AN OPT-OUT, AN AUTO-REPLY")
hunter.add_lead({"name": "Bounce Dental", "email": "nobody@bounce.example", "emailFrom": "t",
                 "via": ["website"]}, "dentists", "Pune")
hunter.add_lead({"name": "No Thanks Dental", "email": "no@thanks.example", "emailFrom": "t",
                 "via": ["website"]}, "dentists", "Pune")
tick()
tick()
b_tid = book("H-0005")["closer"]["threadId"]
n_tid = book("H-0006")["closer"]["threadId"]
GMAIL.arrive(b_tid, "Address not found", frm="Mail Delivery Subsystem <mailer-daemon@googlemail"
             ".com>", subject="Delivery Status Notification (Failure)")
GMAIL.arrive(n_tid, "No thanks, we're not interested.")
sent_before = len(GMAIL.sent)
tick()
check("a bounce marks the lead bounced and logs a failed row",
      (book("H-0005")["status"], log("bounce")[-1]["status"]), ("bounced", "failed"))
check("an opt-out is honoured without asking the model",
      (book("H-0006")["status"], "won't write again" in GMAIL.sent[-1]["msg"].get_content()),
      ("not-interested", True))
check("only the one acknowledgement went", len(GMAIL.sent) - sent_before, 1)
GMAIL.arrive(n_tid, "I am out of the office until Monday.", subject="Automatic reply: hi",
             headers=[("Auto-Submitted", "auto-replied")])
sent_before = len(GMAIL.sent)
tick()
check("an automatic reply is read and never answered", len(GMAIL.sent), sent_before)

# ------------------------------------------------------------------------------ the follow-up

print("ONE FOLLOW-UP, AND NEVER A SECOND")
hunter.add_lead({"name": "Quiet Dental", "email": "quiet@dental.example", "emailFrom": "t",
                 "via": ["website"]}, "dentists", "Pune")
tick()
quiet = next(r for r in log("cold") if r["leadId"] == "H-0007")
old = (datetime.datetime.now() - datetime.timedelta(days=5)).isoformat(timespec="seconds")
closer.update_event(quiet["id"], at=old)
tick()
fu = [r for r in log("followup") if r["leadId"] == "H-0007"]
check("after followUpAfterDays of silence, one follow-up in the same thread",
      (len(fu), fu[0]["threadId"] if fu else None), (1, book("H-0007")["closer"]["threadId"]))
tick()
check("and only one", len([r for r in log("followup") if r["leadId"] == "H-0007"]), 1)
row, err = closer._send(book("H-0007"), "followup", "test", "quiet@dental.example", "x", "y",
                        closer.settings()[0])
check("_send itself refuses a third unsolicited email", (row, "one follow-up" in err),
      (None, True))

# ------------------------------------------------------------------------------ the doors

print("THE DOORS")
for tool_id, params in (("closer_start", {"daily": 10}),
                        ("lock_meeting", {"lead": "H-0001", "when": "Friday"})):
    t = hands.find(tool_id)
    check("%s is door-bound to closer" % tool_id, t and t["doors"], ("closer",))
    check("%s is never described to the brain" % tool_id,
          tool_id in json.dumps(hands.prompt_parts(), default=str), False)
    st, p = hands.propose(tool_id, params, door="tag")
    check("a tag cannot raise %s" % tool_id, (st, p.get("refused")), (403, "wrong-door"))
st, p = hands.propose("lock_meeting", {"lead": "H-0002", "when": "Monday at 11"}, door="closer")
check("the meeting card names the business and the employer's time",
      p["pending"]["line"], "I'll write to Smile Studio (H-0002) asking for a meeting - offering "
                            "Monday at 11, sir. Shall I?")
hands.clear_pending("test")
st, p = hands.propose("closer_start", {"daily": 10}, door="closer")
check("the start card says what will happen and that nothing waits after it",
      ("at most 10 a day" in p["pending"]["line"], "Nothing waits for your yes after this"
       in p["pending"]["line"]), (True, True))
hands.clear_pending("test")

print("THE HAND")
env = dict(os.environ, TRONE_CLOSER_CONFIG=os.path.join(TMP, "none.json"))
env.pop("PYTHONIOENCODING", None)
done = _proc.run([sys.executable, str(HERE / "tools" / "closer_start.py")],
                 input='{"daily": 10}', capture_output=True, text=True, encoding="utf-8",
                 timeout=30, env=env)
check("with no offer sheet the switch refuses, and says what is missing",
      (done.returncode, "closer.offer.service" in done.stdout), (1, True))
done = _proc.run([sys.executable, str(HERE / "tools" / "closer_start.py")],
                 input='{"daily": 400}', capture_output=True, text=True, encoding="utf-8",
                 timeout=30, env=env)
check("a cap beyond the ceiling is refused", (done.returncode, "between 1 and 25" in done.stdout),
      (1, True))

hands.LEDGER_PATH = REAL_TOOLS
print("\n%d failure(s)" % len(FAILURES))
sys.exit(len(FAILURES))
