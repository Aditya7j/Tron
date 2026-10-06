#!/usr/bin/env python3
"""compose_newsletter.py - the hand that DRAFTS a newsletter. It sends nothing.

It prints exactly one of two things: a one-line report of the draft it composed, or
"I could not compose that: <reason>". save_note.py's shape - a hand that writes something
down and tells you what it wrote - and deliberately NOT send_email.py's, because nothing
here reaches outside the house.

WHY THIS IS IN THE REGISTRY AT ALL, since drafting needs no consent. Because the registry is
the only way the brain can be told this exists, and because in this house a registry entry is
inseparable from the Chain Card: hands.propose() builds a card for every tool there is. That
is a cost of one confirmation on a harmless act, and it is the right cost to pay - the
alternative is a second execution path that runs scripts without a card, which is precisely
the parallel mechanism the Publisher mandate forbids building. So the draft is carded like
everything else, and the card's rows are what the boss is about to have composed FOR him
rather than what is about to leave the house.

THE DRAFT IS NOT STORED, AND ONE LINE ABOUT IT IS. It is composed, reported, and thrown away;
tools/send_newsletter.py composes again from the same topic at send time, so there is no draft
on disk for a later send to have drifted from - the topic and the notes are the durable things,
and both are the boss's. A cached draft would also be a copy of his research sitting in a file
nobody audits.

WHAT IS WRITTEN DOWN IS THE TOPIC AND THE SUBJECT, AND THAT IS NOT A DRAFT. It is the fact
that drafting happened and what it was about - two short strings, no body, no passages, no
snippets. The "draft is not stored" law is unchanged: a reader of the ledger learns that the
boss asked for a newsletter on something and what it would have been called, which is exactly
what a later "send the newsletter" needs to know and no more than that.

THE DEFECT THIS EXISTS FOR, and it was live: server.py's _newsletter_topic() answers a bare
"send the newsletter" by reading the most recent `newsletter` row out of the ledger. With no
row ever written here, the most recent one could only be a past SEND - so a boss who drafted
"B2B Agents" and then said "send the newsletter" got the previous test send, "useEffect
cleanup", proposed back at him. Drafting is the more recent signal of what he currently wants;
it has to leave a trace or it cannot be that signal.

  in    {"topic": "..."} on stdin, UTF-8
  out   one plain-ASCII line
  exit  0 composed, 1 not - and every refusal path ends here, named
"""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import newsletter  # noqa: E402


def say(line):
    sys.stdout.buffer.write(str(line).encode("ascii", "replace") + b"\n")
    sys.stdout.buffer.flush()


def fail(reason):
    say("I could not compose that: %s" % reason)
    return 1


def main():
    raw = sys.stdin.buffer.read().decode("utf-8", "replace")
    try:
        params = json.loads(raw) if raw.strip() else {}
    except ValueError as exc:
        return fail("the parameters were not JSON (%s)" % exc)
    if not isinstance(params, dict):
        return fail("the parameters were not an object")

    topic = str(params.get("topic") or "").strip()
    if not topic:
        return fail("no topic was given")

    draft = newsletter.compose(topic)
    if not draft["ok"]:
        return fail(draft["why"])

    # ---- THE ONE LINE IN THE LEDGER. See the docstring's third paragraph. -------------------
    # OUTCOME "done" AND NOT A FIFTH WORD, which the brief suggested and I did not take: the
    # concrete harm is in jobs.finish(), where `_SEEN["done" if outcome == "done" else
    # "failed"] += 1`. An outcome of "drafted" is not "done", so every draft would increment
    # the house's FAILED counter - visible on /jobs and asserted by bus_proof. A draft that
    # succeeded ended fine, so its outcome is `done`; what distinguishes it from a send is
    # `sent: 0` with `failedCount: 0` and ONE step rather than two, which are fields that
    # already exist and already mean exactly that. jobs.OUTCOMES stays a closed vocabulary
    # about how a job ENDED rather than a label for what kind of job it was - the job's NAME
    # is what says that.
    try:
        import jobs
        rep = jobs.Reporter("newsletter", ["compose"], verb="DRAFTING", topic=topic)
        rep.step("compose", draft["subject"])
        rep.done("drafted, not sent - %d subscriber(s) on the list" % draft["subscribers"],
                 subject=draft["subject"], subscribers=draft["subscribers"],
                 sent=0, failedCount=0)
    except Exception as exc:                                       # noqa: BLE001
        # A LEDGER THAT WILL NOT WRITE DOES NOT UNMAKE THE DRAFT. The sentence below is still
        # true about what was composed; what is lost is the trace a later bare "send the
        # newsletter" would have read, so it is named on stderr rather than swallowed.
        sys.stderr.write("  newsletter: the draft row could not be written (%s)\n" % exc)

    # THE REPORT IS COUNTS AND IDS, NOT THE NEWSLETTER. This line is spoken aloud in a room,
    # so it carries the shape of the draft - how long, how many snippets, which notes - and
    # not its prose. The boss reads the body on the Chain Card when he is asked to SEND it,
    # which is the moment a body is worth his attention.
    say("Drafted '%s', sir - %d words, %d code snippet%s, from %d of your notes (%s). "
        "Say send the newsletter and I shall put the card up."
        % (draft["subject"],
           len(draft["body"].split()),
           len(draft["snippets"]),
           "" if len(draft["snippets"]) == 1 else "s",
           len(draft["citedIds"]),
           ", ".join(i[:16] for i in draft["citedIds"][:4])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
