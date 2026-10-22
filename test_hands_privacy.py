"""Proves that nothing a tool is GIVEN is ever kept, spoken, or written down.

The hands are the one part of this machine that takes an instruction and acts on it, so
the parameters they carry are the most sensitive strings in the building: a recipient, a
subject, the body of a letter. The ledger is allowed to know that send_email ran and
failed. It is not allowed to know who it was for.

This test is written to be hostile rather than reassuring, in the same discipline as
test_focus_privacy.py: it invents strings that could not occur by accident, pushes them
through every door the hands have, and then hunts for them everywhere afterwards.

Six claims, because "no leak" is really six different promises:

  1. THE CANARY IS FOREIGN. Every sentinel below appears nowhere in the shipped source,
     so a hit anywhere later is this test's string and not a coincidence. A privacy test
     whose sentinel is already in the file it searches proves nothing at all.
  2. THE PROPOSAL SPEAKS THE TEMPLATE, NOT THE PARAMETERS. The line the employer hears
     is composed from the registry, so a parameter the template does not name cannot be
     read out in a room - and the prose the model wrapped around the tag is discarded
     entirely, tag and all.
  3. THE LEDGER HOLDS FOUR INTEGERS AND A TIMESTAMP. Proved from the attacker's side: a
     hand-edited file with an extra key and a canary in it, an outcome recorded against
     an id that is not in the registry, a row that is not a row - and after each, the
     file on disk is read back and searched.
  4. THE PARAMETERS GO IN ON STDIN, AND ONLY ON STDIN. A tool is run with the canary as
     a parameter and made to prove it received it - by length, never by echo - while the
     command line, the spoken evidence and the trace stay clean.
  5. THE TRACE SAYS WHAT HAPPENED, NEVER WHAT IT WAS GIVEN. Every line hands.py writes
     to stderr is captured for the whole run and searched at the end.
  6. THE SHIPPED REGISTRY KEEPS THE SAME RULES. Every {blank} in every proposal template
     names a real parameter, and send_email's body - the one field that is a private
     letter - is not among the blanks any template renders.

Nothing here touches the real ledger, the real calendar, or the network: the ledger path
and the tools directory are redirected into a temporary folder, and the only scripts run
are two hermetic ones this file writes itself.

Run it:  python test_hands_privacy.py
Exit status is the number of failures.
"""

import inspect
import json
import os
import pathlib
import re
import shutil
import sys
import tempfile

sys.dont_write_bytecode = True
# The one shared final line, so run_tests.py reads a result rather than
# guessing at this suite's private dialect. See testkit.py.
import testkit
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import hands                                                   # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:                                              # noqa: BLE001
    pass

ROOT = pathlib.Path(__file__).resolve().parent

# The strings under test. Shaped like the real thing - an address, a subject, the body of
# a letter, a tool id, a ledger value - so a leak has somewhere realistic to hide, and
# stemmed so a truncation is caught as well as a copy.
CANARY_BODY = "zqhwaffleiron4417"
CANARY_TO = "zqhwafflerecipient@example.invalid"
CANARY_SUBJECT = "zqhwafflesubject"
CANARY_PROSE = "zqhwaffleprose"
CANARY_ID = "zqhwafflenotatool"
CANARY_LEDGER = "zqhwaffleledger"
SENTINELS = [CANARY_BODY, CANARY_TO, CANARY_SUBJECT, CANARY_PROSE, CANARY_ID,
             CANARY_LEDGER, "zqhwaffle", "waffleiron"]

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


def hits(blob):
    """Which sentinels are in this text. Sorted, so a failure reads the same twice."""
    text = blob if isinstance(blob, str) else str(blob)
    return sorted({s for s in SENTINELS if s in text})


def spoken_only(payload):
    """A reply with the ONE field a parameter may appear in taken out.

    `pending.params` travels to the page on purpose: the human about to approve an action
    has to be able to read exactly what they are approving, and a confirmation dialogue
    that hid the recipient would be worse than no dialogue. Everything else in the reply
    is either spoken aloud or logged, so everything else must be clean. Removing the one
    permitted field is what makes the search below a claim rather than a gesture.
    """
    copy = dict(payload)
    if isinstance(copy.get("pending"), dict):
        copy["pending"] = {k: v for k, v in copy["pending"].items() if k != "params"}
    return json.dumps(copy, ensure_ascii=False)


# ------------------------------------------------------------------- the capture
#
# hands.py writes its trace with sys.stderr.write, looked up at call time, so replacing
# the name captures every line the module speaks for the rest of the run. Claim 5 is
# checked at the very end, against everything gathered by everything above it.

class Trace:
    def __init__(self):
        self.lines = []

    def write(self, text):
        self.lines.append(text)
        return len(text)

    def flush(self):
        pass

    def text(self):
        return "".join(self.lines)


trace = Trace()
real_stderr, sys.stderr = sys.stderr, trace


def _unmask(kind, value, tb, _real=real_stderr, _inner=sys.excepthook):
    """Put the real stderr back before the interpreter prints a traceback.

    THIS IS NOT A TIDINESS HOOK. Without it the capture above swallows the
    traceback of any crash in this file: the suite died on a KeyError, printed
    nothing, exited 1, and looked for all the world like a suite that had simply
    failed one check - which is how six broken claims and a stale registry
    fixture lived on main. The capture is still the right design, because claim 5
    is a claim about everything hands.py said; it just must not be the last thing
    holding the microphone when the run falls over.

    The same reasoning as focus.py's _release_watch: whatever ends the session,
    every path out of it goes through one place that hands the real thing back.
    """
    sys.stderr = _real
    _inner(kind, value, tb)


sys.excepthook = _unmask

# --------------------------------------------------- claim 1: the canary is foreign

SHIPPED = ["hands.py", "server.py", "viewer/index.html", "tools/registry.json",
           "tools/selftest.py", "tools/send_email.py", "tools/add_calendar_event.py"]
found_in = {}
for name in SHIPPED:
    path = ROOT / name
    try:
        blob = path.read_bytes().decode("utf-8", "replace")
    except OSError:
        found_in[name] = "missing"
        continue
    if hits(blob):
        found_in[name] = hits(blob)
ok(not found_in,
   "every sentinel is foreign to the shipped source, so a hit later is this test's",
   json.dumps(found_in))

# ------------------------------------------------------ a temporary tools directory
#
# Two hermetic scripts, written here, so claim 4 can be made without touching the real
# calendar and without any possibility of mail leaving the building. `mouth` prints its
# whole input, which is what a careless tool looks like; `ear` proves it received the
# parameters by measuring them, which is what a careful one looks like. The hands must
# keep the canary out of the ledger and the trace in BOTH cases - the discipline cannot
# depend on the script being polite.

workshop = pathlib.Path(tempfile.mkdtemp(prefix="hands-privacy-"))
(workshop / "ear.py").write_text(
    "import json, sys\n"
    "raw = sys.stdin.buffer.read().decode('utf-8', 'replace')\n"
    "p = json.loads(raw) if raw.strip() else {}\n"
    "sys.stdout.buffer.write(('Heard %d characters in %d field(s).'\n"
    "                        % (len(raw), len(p))).encode('ascii', 'replace') + b'\\n')\n",
    encoding="utf-8")
(workshop / "mouth.py").write_text(
    "import sys\n"
    "raw = sys.stdin.buffer.read().decode('utf-8', 'replace')\n"
    "sys.stdout.buffer.write(('You gave me: ' + raw).encode('ascii', 'replace') + b'\\n')\n",
    encoding="utf-8")
(workshop / "argv.py").write_text(
    "import sys\n"
    "sys.stdin.buffer.read()\n"
    "sys.stdout.buffer.write(('ARGV ' + repr(sys.argv[1:])).encode('ascii', 'replace')\n"
    "                        + b'\\n')\n",
    encoding="utf-8")
(workshop / "registry.json").write_text(json.dumps({"version": 1, "tools": [
    {"id": "ear", "name": "A tool that listens", "script": "ear.py",
     "capabilities": ["measure whatever it is handed"], "timeout_s": 20,
     "params": [{"name": "secret", "type": "text", "required": True},
                {"name": "label", "type": "string", "required": False}],
     "proposal": "A measurement, sir, of something you would rather I did not repeat.",
     # `step` became required when chains landed, and this fixture predated that:
     # without it _clean_tool() dropped all three tools, hands.registry() came back
     # empty, every claim below asked its question of a registry with nothing in it,
     # and the suite then died on a KeyError whose traceback went into the stderr
     # capture twenty lines above. One missing field, six failures and no summary.
     # Deliberately naming {label} and not {secret}: a step line is spoken aloud,
     # which is the whole reason _clean_tool refuses {body} and its four siblings.
     "step": "Measure the thing called '{label}'."},
    {"id": "mouth", "name": "A tool that repeats itself", "script": "mouth.py",
     "capabilities": ["read back whatever it is handed"], "timeout_s": 20,
     "params": [{"name": "secret", "type": "text", "required": True}],
     "proposal": "A careless tool, sir, which will read its input back to you.",
     "step": "Read something back to you."},
    {"id": "argv", "name": "A tool that looks at its command line", "script": "argv.py",
     "capabilities": ["report its own arguments"], "timeout_s": 20,
     "params": [{"name": "secret", "type": "text", "required": True}],
     "proposal": "A look, sir, at what was put on the command line.",
     "step": "Look at what was put on the command line."},
]}, indent=2), encoding="utf-8")

ledger_dir = pathlib.Path(tempfile.mkdtemp(prefix="hands-ledger-"))
real_ledger = hands.LEDGER_PATH
real_ledger_before = real_ledger.read_bytes() if real_ledger.is_file() else None

hands.TOOLS_DIR = workshop
hands.REGISTRY_PATH = workshop / "registry.json"
hands.LEDGER_PATH = ledger_dir / "tools-ledger.json"
hands.registry(force=True)
ok(sorted(t["id"] for t in hands.registry()) == ["argv", "ear", "mouth"],
   "the temporary registry loaded, so nothing below can reach a shipped tool",
   json.dumps([t["id"] for t in hands.registry()]))


def ledger_bytes():
    try:
        return hands.LEDGER_PATH.read_bytes().decode("utf-8", "replace")
    except OSError:
        return ""


# -------------------------------- claim 2: the proposal speaks the template only

status, said = hands.propose("ear", {"secret": CANARY_BODY, "label": CANARY_SUBJECT})
ok(status == 200 and said.get("ok"), "a valid proposal is accepted", json.dumps(said))
ok(not hits(said.get("answer") or ""),
   "the spoken proposal carries no parameter the template does not name",
   said.get("answer"))
ok(not hits(spoken_only(said)),
   "and no other field of the reply carries one either - only pending.params",
   spoken_only(said))
ok(hits(json.dumps((said.get("pending") or {}).get("params"))) == sorted(
       {CANARY_BODY, CANARY_SUBJECT, "zqhwaffle", "waffleiron"}),
   "pending.params does carry them, exactly as the human must be able to read")

# The tag, with the model's prose wrapped around it. Whatever arrives with the tag is
# discarded for execution purposes - so a sentence the model invented about the action
# cannot become the sentence the employer is asked to approve.
wanted, params, prose = hands.tool_tag(
    "Certainly, sir, I shall %s at once. [[tool: ear | %s]] It is quite safe."
    % (CANARY_PROSE, json.dumps({"secret": CANARY_BODY})))
ok(wanted == "ear", "the tag is read out of the prose", repr(wanted))
ok(CANARY_PROSE in prose and "[[" not in prose,
   "the prose is returned stripped of the tag, for the log to ignore", repr(prose))
status, said = hands.propose(wanted, params)
ok(status == 200 and not hits(said.get("answer") or ""),
   "and the proposal spoken from that tag is the registry's sentence, not the model's",
   said.get("answer"))

# A refusal, which is the end of the road for both of the above.
status, said = hands.cancel(door="curl")
ok(status == 200 and said.get("pending") is None and not hits(spoken_only(said)),
   "the refusal leaves nothing pending and repeats nothing", json.dumps(said))
ok(not hits(ledger_bytes()),
   "and the ledger, which has just counted a refusal, holds none of it", ledger_bytes())

# --------------------------------------- claim 3: the ledger, from the attacker's side

rows = hands.ledger()
ok(set(rows) == {"argv", "ear", "mouth"},
   "the ledger is keyed by the registry and nothing else", json.dumps(sorted(rows)))
ok(all(set(r) == {"ok", "failed", "refused", "lapsed", "last"} for r in rows.values()),
   "every row is exactly four counts and one timestamp",
   json.dumps({k: sorted(v) for k, v in rows.items()}))
ok(rows["ear"]["refused"] == 1 and rows["ear"]["ok"] == 0,
   "and the counts are the outcomes that actually happened", json.dumps(rows["ear"]))

# An outcome recorded against an id that is not in the registry. A tool that does not
# exist cannot acquire a row - which is what stops a model-supplied name reaching disk.
hands._record(CANARY_ID, "failed")
hands._record(CANARY_TO, "ok")
ok(not hits(ledger_bytes()) and CANARY_ID not in hands.ledger(),
   "an outcome recorded against an unknown id is dropped, not filed", ledger_bytes())

# A file hand-edited with a sixth key, a canary in it, and a timestamp that is a
# sentence rather than a time. Read back through the whitelist, then written again.
hands.LEDGER_PATH.write_text(json.dumps({"version": 1, "tools": {
    "ear": {"ok": 1, "failed": 0, "refused": 1, "lapsed": 0,
            "last": "2026-01-01T09:00:00",
            "recipient": CANARY_TO, "body": CANARY_BODY},
    "mouth": {"ok": "three", "failed": -8, "refused": None, "lapsed": 0,
              "last": "just after the email to " + CANARY_TO},
    CANARY_ID: {"ok": 99, "last": CANARY_LEDGER},
    "notarow": "the whole row is a string",
}}, indent=2), encoding="utf-8")
rows = hands.ledger()
ok(not hits(json.dumps(rows)),
   "a hand-edited ledger cannot introduce a key, so nothing hostile is read back",
   json.dumps(rows))
ok(set(rows) == {"argv", "ear", "mouth"} and CANARY_ID not in rows,
   "and an id that is not in the registry stops being counted at all",
   json.dumps(sorted(rows)))
ok(rows["mouth"] == {"ok": 0, "failed": 0, "refused": 0, "lapsed": 0, "last": ""},
   "a row of nonsense reads as zeroes and an empty timestamp", json.dumps(rows["mouth"]))
ok(rows["ear"]["last"] == "2026-01-01T09:00:00",
   "a timestamp that looks like one survives; anything else is dropped",
   rows["ear"]["last"])
hands._record("ear", "lapsed")
ok(not hits(ledger_bytes()),
   "and the next write scrubs the file, because every write goes through ledger() first",
   ledger_bytes())
after_edit = hands.ledger()
# THE SHAPE CLAIM, and the point of it is that a new field cannot arrive quietly.
# One did. `chains` landed with the Chain Card and this check went red the same
# day - and nobody saw it, because the suite was dying twenty checks earlier on a
# registry fixture and printing no summary at all. That is the whole argument for
# the floor in one line, so it is written down here rather than just fixed.
#
# The compartment is legitimate and hands.py gives it its own whitelist, so the
# claim becomes "exactly these three, each one named", not "two". A fourth still
# fails, which is what the claim was ever for.
LEDGER_COMPARTMENTS = {
    "version": "the file format",
    "tools": "one row of four counts per registered hand",
    "chains": "one row per multi-step plan, through its own whitelist",
}
ok(set(json.loads(hands.LEDGER_PATH.read_text(encoding="utf-8")))
   == set(LEDGER_COMPARTMENTS),
   "the file on disk has three keys, and every one of them is named here",
   json.dumps(sorted(json.loads(hands.LEDGER_PATH.read_text(encoding="utf-8")))))

# And the new compartment gets the hostile read the tools table has had all
# along, because an unproved whitelist is not a whitelist. A chain row carrying a
# canary, an id that is not an id, and a step naming a tool that does not exist.
hands.LEDGER_PATH.write_text(json.dumps({"version": 1, "tools": {}, "chains": [
    {"id": "c1234-1", "status": "ok", "steps": ["ear", "mouth"], "ran": 2,
     "stopped": 0, "at": "2026-01-01T09:00:00",
     "recipient": CANARY_TO, "body": CANARY_BODY},
    {"id": "not-an-id", "status": "ok", "steps": ["ear"], "ran": 1, "stopped": 0,
     "at": "2026-01-01T09:00:00"},
    {"id": "c1234-2", "status": "ok", "steps": [CANARY_ID], "ran": 1, "stopped": 0,
     "at": "2026-01-01T09:00:00"},
]}, indent=2), encoding="utf-8")
chain_rows = hands.chain_ledger()
ok(not hits(json.dumps(chain_rows)),
   "a hand-edited chain row cannot introduce a key, so no canary is read back",
   json.dumps(chain_rows))
ok([r["id"] for r in chain_rows] == ["c1234-1"],
   "a malformed chain id and a step naming no registered tool are both dropped",
   json.dumps([r["id"] for r in chain_rows]))
hands.LEDGER_PATH.write_text(json.dumps({"version": 1, "tools": {
    "ear": {"ok": 1, "failed": 0, "refused": 1, "lapsed": 1,
            "last": "2026-01-01T09:00:00"}}}, indent=2), encoding="utf-8")
after_edit = hands.ledger()
ok(after_edit["ear"]["lapsed"] == 1,
   "the lapse was counted on top of the sanitised row", json.dumps(after_edit["ear"]))

# ------------------------------- claim 4: the parameters go in on stdin, and only there

source = (ROOT / "hands.py").read_text(encoding="utf-8")
ok("shell=False" in source and "shell=True" not in source,
   "hands.py runs scripts with shell=False, always - there is no shell string anywhere")
# The spawn moved from subprocess.run to tools/_proc.run - the quiet-spawn
# wrapper that keeps a hand from flashing a console window - and these two
# claims were still looking for the old name. They are claims about the SHAPE of
# the command line and about there being ONE spawn, neither of which the move
# changed, so they are re-anchored rather than relaxed: _proc.run is named
# explicitly, and a direct call to subprocess.run or Popen would now fail the
# second one where before it would have satisfied it.
ok(re.search(r"_proc\.run\(\s*\n?\s*\[sys\.executable,\s*str\(script\)\]", source)
   is not None,
   "the command line is the interpreter and the script path, and nothing else")
# Anchored at the start of a line, with nothing but an assignment allowed in
# front, so that the module docstring's prose ABOUT the execution - which names
# subprocess.run in a sentence - is not counted as a second way to start one.
spawns = re.findall(
    r"^\s*(?:\w+\s*=\s*)?(?:subprocess|_proc|os)\.(?:run|Popen|call|system|spawn\w*|"
    r"check_output|check_call)\(", source, re.M)
ok(len(spawns) == 1,
   "there is exactly one place in the file that can start a process",
   "%d: %s" % (len(spawns), [s.strip() for s in spawns]))

status, said = hands.propose("argv", {"secret": CANARY_BODY})
status, said = hands.execute(door="curl", proposal_id=(said["pending"] or {}).get("id"))
ok(status == 200 and said.get("answer", "").startswith("ARGV []"),
   "a tool asked what was on its command line finds nothing there", said.get("answer"))

status, said = hands.propose("ear", {"secret": CANARY_BODY, "label": CANARY_SUBJECT})
pending_id = (said.get("pending") or {}).get("id")
status, said = hands.execute(door="curl", proposal_id=pending_id)
ok(status == 200 and said.get("ran") == "ear",
   "the hermetic tool ran", json.dumps(said))
ok("Heard %d characters in 2 field(s)" % len(
       json.dumps({"secret": CANARY_BODY, "label": CANARY_SUBJECT}, ensure_ascii=False))
   in (said.get("answer") or ""),
   "and it received the parameters ON STDIN, proved by length rather than by echo",
   said.get("answer"))
ok(not hits(spoken_only(said)),
   "while the reply that carried its evidence says none of them", spoken_only(said))
ok(not hits(ledger_bytes()),
   "the ledger counted the run and kept nothing from it", ledger_bytes())

# The careless tool: a script that reads its input back. The assistant SPEAKS a script's
# stdout, so this one does leak into the spoken line - and it must, because stdout is the
# only evidence there is and a butler that edited it would be lying about what happened.
# What must still hold is everything else: the ledger, the trace, and the disk.
status, said = hands.propose("mouth", {"secret": CANARY_BODY})
status, said = hands.execute(door="curl", proposal_id=(said["pending"] or {}).get("id"))
ok(status == 200 and CANARY_BODY in (said.get("answer") or ""),
   "a tool that prints its input has that input spoken, because stdout is the evidence")
ok(not hits(ledger_bytes()),
   "and even then the ledger holds outcomes only", ledger_bytes())
rows = hands.ledger()
ok(rows["mouth"]["ok"] == 1 and all(
       set(r) == {"ok", "failed", "refused", "lapsed", "last"} for r in rows.values()),
   "with the shape unchanged by any of it", json.dumps(rows["mouth"]))

# ---------------------------------------------- claim 5: the trace, read at the end

captured = trace.text()
ok(not hits(captured),
   "nothing hands.py wrote to stderr this whole run names a single parameter",
   "\n       ".join(line for line in captured.splitlines() if hits(line)))
ok(captured.count("tool:") >= 8,
   "and it was not silent either - it says what happened, %d lines of it"
   % len(captured.splitlines()))

# The trace has been read, so stderr goes back to the terminal here rather than at the
# end of the file: everything below this line is allowed to fail loudly.
sys.stderr = real_stderr

# ----------------------------------- claim 6: the shipped registry keeps these rules

hands.TOOLS_DIR = ROOT / "tools"
hands.REGISTRY_PATH = hands.TOOLS_DIR / "registry.json"
hands.registry(force=True)
shipped = hands.registry()
ok(len(shipped) >= 3, "the shipped registry loads", json.dumps([t["id"] for t in shipped]))
# THE DERIVED BLANKS. A proposal may also name a reading that hands.readings()
# computes - {when} and {duration} from the calendar stamps, {plan} and {where}
# from what the Operator will actually do, {lines} and {how} from the code about
# to be typed. Those are sentence furniture: they never enter params, never reach
# the script and never reach the ledger, which is precisely why they are not in
# the schema and why this check went red when chains and the Operator landed.
#
# Taken from readings()'s own source rather than listed here, for the same reason
# LEGIT_LABELS in test_focus_privacy.py asks focus for its labels: a second copy
# of a vocabulary is a copy that disagrees with the first one eventually. So the
# claim is unchanged - a template may not render the word {something} at an
# employer - and it now knows the whole set of somethings that are real.
readings_src = inspect.getsource(hands.readings)
DERIVED = set(re.findall(r'out\["([a-z0-9_]+)"\]', readings_src)) - {"_refusal"}
ok(DERIVED >= {"when", "duration", "plan", "where", "lines", "how"},
   "hands.readings() declares the derived blanks, and they are read from its source",
   json.dumps(sorted(DERIVED)))

bad_blanks, unspoken = {}, {}
for tool in shipped:
    declared = {p["name"] for p in tool["params"]}
    blanks = set(re.findall(r"\{([a-z0-9_]+)\}", tool["proposal"]))
    if blanks - declared - DERIVED:
        bad_blanks[tool["id"]] = sorted(blanks - declared - DERIVED)
    # The unspoken list stays a statement about the SCHEMA - which declared
    # parameter never reaches the sentence - so the derived blanks are not in it.
    unspoken[tool["id"]] = sorted(declared - blanks)
ok(not bad_blanks,
   "every blank in every proposal template names a real parameter, so no template can "
   "render the word {something} at an employer", json.dumps(bad_blanks))
ok("body" in unspoken.get("send_email", []),
   "send_email's body is not among the blanks any template renders: a private letter is "
   "not read out in a room", json.dumps(unspoken))
mailer = json.dumps([t for t in shipped if t["id"] == "send_email"],
                    default=str).lower()
ok(not re.search(r"password|api[_-]?key|smtp_|secret", mailer),
   "the registry entry for the mailer names no credential and no provider setting",
   mailer[:200])
# The file itself, minus its own documentation - the _comment block is prose ABOUT keys
# and is allowed to use the words; the declarations are not.
#
# AT EVERY DEPTH, which it did not used to be. Only the top-level _comment was
# stripped, and when a tool grew a _comment of its own - the Operator's, saying
# "password fields are refused by the hand", which is the opposite of a leak -
# this went red on a sentence promising not to do the thing it was accused of.
# The rule was right and its reach was wrong, so the reach is fixed rather than
# the regex softened: a credential in any field that is not documentation still
# fails, including in a _comment's neighbours.
def _undocumented(value):
    if isinstance(value, dict):
        return {k: _undocumented(v) for k, v in value.items() if k != "_comment"}
    if isinstance(value, list):
        return [_undocumented(v) for v in value]
    return value


on_disk = json.loads((ROOT / "tools" / "registry.json").read_text(encoding="utf-8"))
registry_text = json.dumps(_undocumented(on_disk))
ok(not re.search(r"(?i)(api[_-]?key|password|secret|credential)", registry_text),
   "the registry file on disk holds no key, password or secret - a tool that needs one "
   "reads config.json itself, server-side")

# ----------------------------------------------------------------------- tidying up

hands.LEDGER_PATH = real_ledger
after = real_ledger.read_bytes() if real_ledger.is_file() else None
ok(after == real_ledger_before,
   "and the real tools-ledger.json is byte-for-byte what it was before this test ran")
for folder in (workshop, ledger_dir):
    shutil.rmtree(folder, ignore_errors=True)

testkit.summary(__file__, checks, failures)
sys.exit(min(len(failures), 120))
