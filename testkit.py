"""testkit.py - the one line every suite ends with, so a runner can read it.

WHY THIS EXISTS. Before Phase III each suite announced its result in its own
dialect: test_mode.py said "85 checks, 0 failed", test_hunter.py said
"0 failure(s)", test_confidence.py and test_watch.py crashed before saying
anything at all. A runner that has to guess which of those a file speaks is a
runner that guesses wrong silently, and that is most of why seventeen failures
in test_focus_privacy.py sat on main under a board marked DONE.

So the suites keep their own voices - the "  ok   ..." and "  FAIL ..." lines
that make a run readable by a person are untouched - and gain ONE machine line
on top. The precedent is hands.py's ledger: a human-facing trace and a
machine-facing record, written from the same call so they cannot drift.

THE CONTRACT, which run_tests.py and nothing else depends on:

    TRONE-RESULT suite=<name> checks=<n> failed=<n> skipped=<n>
    TRONE-FAILED <the claim that failed>        (one line per failure)
    TRONE-SKIPPED <the reason, printed>         (one line per declared skip)

RESULT is last-wins and must be the final word of a healthy run, which is what
makes its ABSENCE meaningful: a suite that crashed never printed one, so the
runner calls that ERROR rather than quietly reading the exit code as a count.
That distinction - a traceback is not a skip - is the whole point of the floor.

A SKIP IS A DECLARATION, NOT A SHRUG. skip() prints its reason on both the
human and the machine line, because "no Chrome on this machine" is a fact the
reader of a green run needs and an unexplained absence is how a suite stops
testing anything without anybody noticing.
"""

import os
import sys

# One line per failure and per skip rather than a comma-joined list, because a
# claim in this house is a whole English sentence and sentences contain commas.
# The runner splits on the newline, which no claim contains.
RESULT_PREFIX = "TRONE-RESULT"
FAILED_PREFIX = "TRONE-FAILED"
SKIPPED_PREFIX = "TRONE-SKIPPED"

_skips = []


def suite_name(path=None):
    """The name a suite is known by: its filename, no directory, no extension.

    The ledger is keyed on this, so it is computed in exactly one place. A suite
    that spelled its own name would eventually spell it differently from the
    file it lives in, and the ledger would then hold a row nothing can match.
    """
    return os.path.splitext(os.path.basename(path or sys.argv[0]))[0]


def skip(reason):
    """Decline one block of checks, out loud, with the reason on the record.

    Returns False so a caller can write `if testkit.skip(...): ...` or, more
    usually, `if not CHROME and testkit.skip("no Chrome on this machine"): pass`
    and read as English either way.
    """
    text = str(reason).strip()
    _skips.append(text)
    print("  SKIP %s" % text)
    return False


def summary(path, checks, failures, skips=None):
    """Print the human line, then the machine lines, then leave.

    `failures` is the list of claims that failed - the claim text, not a count,
    because the known-fail ledger matches on the claim. `skips` defaults to
    everything skip() was told about, which is what a suite that uses skip()
    wants and costs a suite that does not nothing.

    Does not exit. The caller exits, because the exit code is the suite's own
    long-standing promise (the number of failures, capped at 120 so a run of 300
    broken checks cannot wrap round to 0 on a POSIX exit status) and this file
    is not the place to change it.
    """
    failures = list(failures or [])
    skips = list(_skips if skips is None else skips)
    print("\n  %d checks, %d failed, %d skipped\n" % (checks, len(failures), len(skips)))
    for claim in failures:
        print("    FAILED: %s" % claim)
    if failures:
        print("")
    print("%s suite=%s checks=%d failed=%d skipped=%d"
          % (RESULT_PREFIX, suite_name(path), checks, len(failures), len(skips)))
    for claim in failures:
        print("%s %s" % (FAILED_PREFIX, claim))
    for reason in skips:
        print("%s %s" % (SKIPPED_PREFIX, reason))
    sys.stdout.flush()
    return len(failures)
