#!/usr/bin/env python3
"""send_newsletter.py - the hand that sends the newsletter to the list. One message each.

It prints one line, and that line is the truth about every address: either every subscriber
was written to, or it says which were and which were not. A PARTIAL SEND IS NOT A SUCCESS and
is never reported as one - send_email.py's own contract is that a hand which cannot confirm
itself must say so rather than claim it worked, and with a list there are as many
confirmations to make as there are addresses.

ONE MESSAGE PER SUBSCRIBER, AND NO CC OR BCC ANYWHERE. send_email.py refuses a comma in a
recipient for a stated reason - "a confirmation dialogue that showed one address and sent to
four would make the gate a decoration" - and that reason does not weaken because the boss
approved a list. It also means no subscriber ever sees another subscriber's address, which a
BCC gets right by accident and a CC gets catastrophically wrong once.

IT REUSES THE GMAIL PATH RATHER THAN RE-IMPLEMENTING IT. send_email.build() serialises the
RFC 2822 bytes and google_api.send_message() puts them on the wire, exactly as the
one-recipient hand does; there is no second OAuth dance, no SMTP, and no second place for the
From header to be got wrong. If the grant is revoked, this hand says the same sentence
send_email.py says, because it is asking the same function.

THE LIST IS RE-READ AT SEND TIME AND THE PROPOSAL'S COUNT IS NOT TRUSTED. publish_video.py
checks its video id against its own ledger rather than against the request, for the reason
that a parameter which travelled through a model and a card is a parameter that may have
drifted; here the risk is sharper, because the file can be edited by hand in the 120 seconds
the card is up. So `subscribers` on the card is what the boss was SHOWN, and the addresses
written to are whatever the file says when the word is given - and if the two disagree, the
spoken line says so instead of quietly sending to a different list than the one approved.

  in    {"subject": "...", "topic": "...", "subscribers": N, ...} on stdin, UTF-8
  out   one plain-ASCII line
  exit  0 every address was written to, 1 otherwise
"""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import google_api  # noqa: E402
import newsletter  # noqa: E402

TOOLS = pathlib.Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from send_email import build  # noqa: E402  - the one serialiser, reused and not rewritten

NO_ROAD = "I have no road to your mail yet, Addi - Connect Google, and I shall."
RECONNECT = ("The road to your mail has closed, Addi - Google will not renew the "
             "connection, so it wants reconnecting in the Command Panel.")


def say(line):
    sys.stdout.buffer.write(str(line).encode("ascii", "replace") + b"\n")
    sys.stdout.buffer.flush()


def fail(reason):
    say("The newsletter did not go: %s" % reason)
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
        return fail("no topic was given, so there is nothing to compose")
    shown = params.get("subscribers")

    # ---- 1. THE LIST, RE-READ. See the docstring's fourth paragraph. -----------------------
    rows, why = newsletter.subscribers()
    if why:
        return fail(why)

    # ---- 2. THE NEWSLETTER, RE-COMPOSED FROM THE NOTES AT SEND TIME. ----------------------
    # Composed again rather than carried: the body is thousands of characters and a parameter
    # that size travelling through a card is a parameter nobody read. What the boss approved
    # is a subject, a count, an opening and a citation list - and all four are re-derived
    # here from the same topic and the same notes, so what goes out is what he was shown.
    draft = newsletter.compose(topic)
    if not draft["ok"]:
        return fail(draft["why"])

    # ---- 3. THE COUNT HE WAS SHOWN AGAINST THE COUNT THAT EXISTS. -------------------------
    try:
        shown_n = int(shown) if shown is not None else None
    except (TypeError, ValueError):
        shown_n = None
    drift = (shown_n is not None and shown_n != len(rows))

    bearer, state, state_why = google_api.access()
    if state in ("absent", "no-client"):
        say(NO_ROAD)
        return 1
    if state == "reconnect":
        say(RECONNECT)
        return 1
    if state_why:
        return fail(state_why)
    if not bearer:
        return fail("there is no usable token for your mail")

    sender = str((google_api.token() or {}).get("email") or "")

    # ---- 4. ONE MESSAGE EACH, AND A RESULT FOR EVERY ONE. ---------------------------------
    results = []
    for i, row in enumerate(rows):
        note = build(row["email"], draft["subject"], draft["body"], sender)
        sent, err = google_api.send_message(note)
        message_id = str((sent or {}).get("id") or "")
        if err:
            results.append({"i": i, "sha": row["sha"], "ok": False, "why": str(err)[:160]})
        elif not message_id:
            # GMAIL'S OWN ID IS THE EVIDENCE. An accepted call that names no message is not
            # a proven send, and send_email.py refuses to claim one for the same reason.
            results.append({"i": i, "sha": row["sha"], "ok": False,
                            "why": "Gmail accepted it but named no message"})
        else:
            results.append({"i": i, "sha": row["sha"], "ok": True, "id": message_id})

    went = [r for r in results if r["ok"]]
    stuck = [r for r in results if not r["ok"]]

    # ---- 5. THE LEDGER ROW, in the append-only record the Director and Broadcaster use. ---
    # NOT hands.py's ledger, and that is deliberate rather than convenient: hands.py's own
    # docstring says it holds four integers and one timestamp per tool and that "there is no
    # key a recipient could be put into", which is a privacy claim this mandate must not
    # break to satisfy its own reporting clause. jobs-ledger.json is the house's rich
    # append-only record, it already carries additive per-feature keys, and the addresses go
    # into it as DIGESTS - see newsletter.digest().
    try:
        import jobs
        rep = jobs.Reporter("newsletter", ["compose", "send"], verb="SENDING", topic=topic)
        rep.step("compose", draft["subject"])
        rep.step("send", "%d subscriber(s)" % len(rows))
        row_fields = {
            "subscribers": len(rows),
            "sent": len(went),
            "failedCount": len(stuck),
            "recipients": results,
            "cited": draft["citedIds"],
            "subject": draft["subject"],
        }
        detail = ("%d of %d subscriber(s) written to" % (len(went), len(rows)))
        (rep.done if not stuck else rep.failed)(detail, **row_fields)
    except Exception as exc:                                       # noqa: BLE001
        # A LEDGER THAT WOULD NOT WRITE DOES NOT UNSEND AN EMAIL. The send already happened,
        # so the line below still tells the truth about it, and the failure to record is
        # named rather than swallowed.
        sys.stderr.write("  newsletter: the ledger row could not be written (%s)\n" % exc)

    # ---- 6. THE ONE LINE, AND IT IS PER-ADDRESS WHEN IT HAS TO BE. ------------------------
    drift_clause = ""
    if drift:
        drift_clause = (" The card said %d, and the list held %d when you gave the word - "
                        "I sent to the list." % (shown_n, len(rows)))
    if not stuck:
        say("The newsletter has gone to %d subscriber%s, sir, under '%s'.%s"
            % (len(went), "" if len(went) == 1 else "s", draft["subject"], drift_clause))
        return 0
    if not went:
        say("The newsletter reached nobody, sir - all %d attempt%s failed, the first "
            "because %s.%s" % (len(stuck), "" if len(stuck) == 1 else "s",
                               stuck[0]["why"], drift_clause))
        return 1
    # A PARTIAL SEND, SAID AS A PARTIAL SEND. Not "sent" and not "failed": the number that
    # went, the number that did not, and why the first failure failed.
    say("The newsletter went to %d of %d subscribers, sir - %d did not, the first because "
        "%s. It is in the ledger per address.%s"
        % (len(went), len(rows), len(stuck), stuck[0]["why"], drift_clause))
    return 1


if __name__ == "__main__":
    sys.exit(main())
