#!/usr/bin/env python3
"""run_tests.py - every suite in this repository, one summary, one exit code.

WHY THIS EXISTS, in one paragraph, because the answer is the whole design.

Three days before this was written test_focus_privacy.py failed 5 assertions.
Then it failed 17. test_eyes.py had been failing 5 for long enough that nobody
had ever counted them. test_hands_privacy.py crashed and printed nothing at all,
because it replaces sys.stderr with a capture object and the traceback went into
the capture. test_confidence.py and test_watch.py crashed too. All of it sat on
main under a board where twelve features were marked DONE. Nothing caught any of
it because nothing was looking, and nothing was looking because every suite
spoke its own dialect and there was no one place that read them.

So: FOUR OUTCOMES, and the distinction between the last two is the point.

  PASS   it ran and every check passed
  FAIL   it ran and one or more checks failed
  SKIP   it declined to run, and said why ("no Chrome on this machine")
  ERROR  it crashed. A traceback is not a skip, and a timeout is not a skip.

test_closer.py raises IndexError on a machine with no Chrome. That is an ERROR.
Swallowing it, or counting it as a skip, is the exact accident this file exists
to make impossible, so the runner's rule is blunt: a suite that did not print the
shared final line did not finish, whatever its exit code says.

HOW A SUITE REPORTS. One line, from testkit.summary(), parsed rather than
guessed at. See testkit.py for the contract.

THE KNOWN-FAIL LEDGER. known-fails.json lists the checks that are failing today
with a reason, an owner and a date. A failure IN the ledger is reported and does
not break the build. A failure NOT in the ledger breaks it. And - the half that
matters as much, because it is how "the three fails are expected" became folklore
nobody rechecked - A LEDGER ENTRY THAT NOW PASSES ALSO BREAKS THE BUILD. A stale
ledger is how a fixed bug quietly returns.

ZERO TEST FILES IS A FAILURE. A runner that runs nothing and reports green is
the easiest thing in this file to ship by accident, so it is checked first and
tested on purpose (run_tests.py --self-test).

  python run_tests.py              every suite, plus preflight --offline
  python run_tests.py --live       and preflight's live checks too
  python run_tests.py --only mode  just the suites whose name contains "mode"
  python run_tests.py --self-test  prove the runner fails on an empty directory

Exit status is the number of unexplained outcomes, capped at 120.
"""

import io
import json
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
sys.dont_write_bytecode = True

import testkit                                                 # noqa: E402

LEDGER_PATH = os.path.join(ROOT, "known-fails.json")

# A suite gets this long and then it is an ERROR. test_revenue.py is the slowest
# honest suite at about 35 seconds, so this is an order of magnitude of slack: it
# is here to catch a hang, not to police a slow machine.
TIMEOUT_S = 600

PASS, FAIL, SKIP, ERROR = "PASS", "FAIL", "SKIP", "ERROR"
MARK = {PASS: "ok  ", FAIL: "FAIL", SKIP: "skip", ERROR: "ERR "}


class Outcome(object):
    """What one suite did. Built only by run_suite(), read by everything else."""

    def __init__(self, suite, status, checks=0, failed=(), skipped=(), note="", ms=0):
        self.suite = suite
        self.status = status
        self.checks = checks
        self.failed = list(failed)
        self.skipped = list(skipped)
        self.note = note
        self.ms = ms


def discover():
    """Every test_*.py in the repo root, in a stable order.

    The root only, deliberately. tools/ has its own scripts and archive/ holds
    retired ones, and a runner that walked the tree would resurrect those on the
    day somebody drops an old file back in to look at it.
    """
    return sorted(n for n in os.listdir(ROOT)
                  if n.startswith("test_") and n.endswith(".py")
                  and os.path.isfile(os.path.join(ROOT, n)))


def parse(text, suite):
    """Read one suite's output for the shared final line.

    Last-wins on RESULT, because a suite that prints the line twice has a bug
    worth seeing rather than hiding, and the last one is the real end of the run.
    Returns None when there is no RESULT line at all, which is the signal that
    the suite did not finish.
    """
    result, failed, skipped = None, [], []
    for line in text.splitlines():
        if line.startswith(testkit.RESULT_PREFIX + " "):
            fields = {}
            for token in line.split()[1:]:
                key, _, value = token.partition("=")
                fields[key] = value
            result = fields
            failed, skipped = [], []           # a second RESULT starts a fresh list
        elif line.startswith(testkit.FAILED_PREFIX + " "):
            failed.append(line[len(testkit.FAILED_PREFIX) + 1:].strip())
        elif line.startswith(testkit.SKIPPED_PREFIX + " "):
            skipped.append(line[len(testkit.SKIPPED_PREFIX) + 1:].strip())
    if result is None:
        return None
    try:
        checks = int(result.get("checks", 0))
    except ValueError:
        return None
    return checks, failed, skipped


def run_suite(name, argv=(), label=None):
    """One suite, in its own process, and what it did.

    Its own process for two reasons that are not negotiable. These suites
    monkeypatch module globals at import - focus.time, hands.REGISTRY_PATH,
    sys.stderr - and one of them would poison the next in a shared interpreter.
    And a suite that crashes the interpreter must not take the runner with it.
    """
    label = label or os.path.splitext(name)[0]
    started = time.time()
    env = dict(os.environ)
    # PYTHONIOENCODING is stripped on purpose: a suite run with it set passes
    # while a live hand mis-decodes the same bytes from stdin, so the runner must
    # not be the thing that quietly supplies it. -X utf8 below does the honest
    # equivalent for this process and does not leak into the subprocesses a suite
    # spawns.
    env.pop("PYTHONIOENCODING", None)
    try:
        done = subprocess.run([sys.executable, "-X", "utf8", os.path.join(ROOT, name)]
                              + list(argv),
                              cwd=ROOT, env=env, stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, timeout=TIMEOUT_S)
        text = done.stdout.decode("utf-8", "replace")
        code = done.returncode
    except subprocess.TimeoutExpired as exc:
        text = (exc.output or b"").decode("utf-8", "replace")
        return Outcome(label, ERROR, note="no result after %ds - hung, not skipped" % TIMEOUT_S,
                       ms=(time.time() - started) * 1000), text

    ms = (time.time() - started) * 1000
    read = parse(text, label)
    if read is None:
        # THE RULE THIS FILE EXISTS FOR. No final line means it did not finish,
        # and the exit code is not evidence of anything: test_hands_privacy.py
        # exits 1 from a swallowed IndexError and test_closer.py exits 1 from an
        # IndexError on a machine with no Chrome. Neither is a skip.
        tail = [l for l in text.strip().splitlines() if l.strip()][-1:]
        return Outcome(label, ERROR, ms=ms,
                       note="exit %s, no %s line%s"
                            % (code, testkit.RESULT_PREFIX,
                               " - last said: " + tail[0].strip() if tail else "")), text

    checks, failed, skipped = read
    if failed:
        status = FAIL
    elif checks == 0 and skipped:
        status = SKIP
    else:
        status = PASS
    return Outcome(label, status, checks, failed, skipped, ms=ms), text


# ============================================================ the known-fail ledger

def load_ledger():
    """The ledger, or an empty one, and never a crash on a comma.

    A ledger that cannot be parsed is itself a build failure rather than an
    empty ledger, because "the file is malformed" and "nothing is known to fail"
    must not look the same from here. That is the same mistake as a runner that
    finds no tests and reports green.
    """
    if not os.path.isfile(LEDGER_PATH):
        return [], "known-fails.json is not there"
    try:
        with io.open(LEDGER_PATH, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError) as exc:
        return None, "known-fails.json is unreadable: %s" % exc
    entries = data.get("entries") if isinstance(data, dict) else data
    if not isinstance(entries, list):
        return None, "known-fails.json has no entries list"
    rows = []
    for raw in entries:
        if not isinstance(raw, dict) or not raw.get("suite"):
            return None, "known-fails.json has a row that is not a row: %r" % (raw,)
        rows.append({"suite": str(raw["suite"]),
                     "check": None if raw.get("check") is None else str(raw["check"]),
                     "error": bool(raw.get("error")),
                     "why": str(raw.get("why") or ""),
                     "owner": str(raw.get("owner") or ""),
                     "added": str(raw.get("added") or "")})
    return rows, ""


def reconcile(outcomes, ledger, partial=False):
    """What the ledger explains, what it does not, and what it no longer needs.

    Three lists come back and all three can break the build:

      unexplained  a failure or an error nothing in the ledger covers
      stale        a ledger row whose check now passes, or whose suite is gone
      explained    reported, with the reason, and forgiven

    The stale list is not a tidiness feature. A row that outlives its failure is
    how a repaired bug comes back unnoticed, and it is how "those three are
    expected" turns into folklore. It breaks the build on purpose.
    """
    seen = {o.suite: o for o in outcomes}
    explained, unexplained, stale = [], [], []
    used = set()

    for o in outcomes:
        if o.status == ERROR:
            rows = [r for r in ledger if r["suite"] == o.suite and r["error"]]
            if rows:
                explained.append((o.suite, "(the whole suite errors)", rows[0]))
                used.add(id(rows[0]))
            else:
                unexplained.append((o.suite, "ERROR: " + o.note))
        for claim in o.failed:
            rows = [r for r in ledger
                    if r["suite"] == o.suite and r["check"] == claim]
            if rows:
                explained.append((o.suite, claim, rows[0]))
                used.add(id(rows[0]))
            else:
                unexplained.append((o.suite, claim))

    for row in ledger:
        if id(row) in used:
            continue
        o = seen.get(row["suite"])
        if o is None:
            if partial:
                # --only ran a subset on purpose. "That suite did not run" is not
                # evidence that its row is stale, and reporting it as such would
                # teach people to ignore the stale list, which is the one list
                # here that nobody may learn to ignore.
                continue
            stale.append((row, "no suite called %s ran" % row["suite"]))
        elif row["error"]:
            stale.append((row, "the suite no longer errors - it is %s" % o.status))
        elif o.status == ERROR:
            # The suite crashed before it could reach this check, so the row is
            # neither proved nor disproved. Not stale; the ERROR itself is the
            # finding, and it is reported above.
            continue
        else:
            stale.append((row, "that check passes now"))
    return explained, unexplained, stale


# ============================================================ the self-test

def self_test():
    """Prove the runner fails loudly on an empty directory.

    A runner that runs nothing and reports green is the exact failure this file
    exists to prevent and the easiest one to ship by accident, so the claim is
    exercised rather than asserted in a comment: discovery is pointed at a
    directory with no suites in it and the verdict is read back.
    """
    import tempfile
    global ROOT
    real, ROOT = ROOT, tempfile.mkdtemp(prefix="run-tests-selftest-")
    try:
        found = discover()
        print("  an empty directory discovers %d suites" % len(found))
        if found:
            print("  SELF-TEST FAILED: discovery found something in an empty directory")
            return 1
        print("  and main() refuses to call that a pass:")
        code = main(argv=[], _suites=found)
        if code == 0:
            print("  SELF-TEST FAILED: zero suites exited 0")
            return 1
        print("\n  self-test passed: zero suites is exit %d, not green" % code)
        return 0
    finally:
        ROOT = real


# ============================================================ the run

def main(argv=None, _suites=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    live = "--live" in argv
    only = ""
    if "--only" in argv:
        at = argv.index("--only")
        only = argv[at + 1] if at + 1 < len(argv) else ""

    suites = discover() if _suites is None else list(_suites)
    if only:
        suites = [s for s in suites if only in s]

    print("")
    print("  run_tests  ·  %s  ·  %s"
          % (os.path.basename(ROOT), time.strftime("%d %b %Y %H:%M:%S")))
    print("")

    if not suites and not only:
        # Loud, and first, and before anything else can print a reassuring zero.
        print("  NO TEST FILES FOUND in %s" % ROOT)
        print("  A runner that runs nothing and reports green is the failure this")
        print("  runner exists to prevent. Refusing to report anything at all.")
        print("")
        return 1
    if not suites:
        print("  --only %r matched no suite" % only)
        print("")
        return 1

    ledger, trouble = load_ledger()
    if ledger is None:
        print("  THE LEDGER IS BROKEN: %s" % trouble)
        print("  Refusing to run, because an unreadable ledger and an empty one")
        print("  must not look the same from here.")
        print("")
        return 1
    if trouble:
        print("  (%s - every failure will be unexplained)" % trouble)
        print("")

    outcomes, transcripts = [], {}
    for name in suites:
        outcome, text = run_suite(name)
        outcomes.append(outcome)
        transcripts[outcome.suite] = text
        print("  %-5s %-22s %4d checks  %5d failed  %3d skipped  %6.0f ms%s"
              % (MARK[outcome.status], outcome.suite, outcome.checks,
                 len(outcome.failed), len(outcome.skipped), outcome.ms,
                 "  " + outcome.note if outcome.note else ""))

    # preflight last, and through its own --offline flag rather than through a
    # second list of what its offline checks are. One definition, in preflight.py.
    if _suites is None:
        args = [] if live else ["--offline"]
        outcome, text = run_suite("preflight.py", args,
                                  label="preflight" + ("" if live else " --offline"))
        # The ledger keys on the plain name, whichever way preflight was run.
        outcome.suite = "preflight"
        outcomes.append(outcome)
        transcripts[outcome.suite] = text
        print("  %-5s %-22s %4d checks  %5d failed  %3d skipped  %6.0f ms%s"
              % (MARK[outcome.status], outcome.suite, outcome.checks,
                 len(outcome.failed), len(outcome.skipped), outcome.ms,
                 "  " + outcome.note if outcome.note else ""))

    explained, unexplained, stale = reconcile(outcomes, ledger, partial=bool(only))

    print("")
    checks = sum(o.checks for o in outcomes)
    print("  %d suites, %d checks, %d failed, %d skipped, %d errored"
          % (len(outcomes), checks,
             sum(len(o.failed) for o in outcomes),
             sum(len(o.skipped) for o in outcomes),
             sum(1 for o in outcomes if o.status == ERROR)))

    for o in outcomes:
        for reason in o.skipped:
            print("    skipped  %s: %s" % (o.suite, reason))

    if explained:
        print("")
        print("  KNOWN, and in the ledger - reported, not forgiven:")
        for suite, claim, row in explained:
            print("    %s: %s" % (suite, claim))
            print("        %s  [%s, since %s]"
                  % (row["why"] or "no reason given", row["owner"] or "unowned",
                     row["added"] or "an unrecorded date"))

    if unexplained:
        print("")
        print("  NOT IN THE LEDGER - this is what breaks the build:")
        for suite, claim in unexplained:
            print("    %s: %s" % (suite, claim))

    if stale:
        print("")
        print("  THE LEDGER IS STALE - also breaks the build, and for the same reason:")
        for row, why in stale:
            print("    %s: %s" % (row["suite"], row["check"] or "(the whole suite)"))
            print("        %s" % why)

    print("")
    if unexplained or stale:
        print("  RED. %d unexplained, %d stale ledger rows."
              % (len(unexplained), len(stale)))
        print("")
        for suite in sorted({s for s, _ in unexplained}):
            print("  ---- %s ----" % suite)
            print(transcripts.get(suite, "").strip()[-3000:])
            print("")
        return min(len(unexplained) + len(stale), 120)

    print("  GREEN%s." % (" (%d known failures, all ledgered)" % len(explained)
                          if explained else ""))
    print("")
    return 0


if __name__ == "__main__":
    if "--self-test" in sys.argv[1:]:
        sys.exit(self_test())
    sys.exit(main())
