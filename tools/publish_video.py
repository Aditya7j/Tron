#!/usr/bin/env python3
"""publish_video.py - the hand that makes an unlisted film public, and the only one that can.

It prints exactly one of FOUR things, and §43 added the fourth because three were not enough to
tell the truth with: "That film is already public, sir - <title>." (nothing was sent), "It is
public now, sir - <title>." (sent and CONFIRMED by a read-back), "YouTube accepted the change,
sir, but my own read still says ... so I will not call it done ..." (sent, accepted, and this
house could not confirm it), or "Publishing failed: <reason>" (refused). send_email.py's
contract, for send_email.py's reason - the assistant speaks what the hand observed rather than
deciding for itself that the thing worked, and this is the second hand in the house whose work
cannot be taken back.

TWO ABSOLUTES, AND ONE LINE USED TO BREAK BOTH. Never print a failure sentence when the update
returned success; never print a success sentence without a confirmed read. The old code read
videos.list exactly once, immediately, took a stale privacyStatus for the truth, and said
"Publishing failed" about three films YouTube had already accepted - see publish() in
broadcast.py for the propagation lag and the backoff that answers it.

§42 TOOK THE URL OUT OF THAT FIRST LINE and it is worth saying why here, where the contract is:
this stdout is SPOKEN ALOUD, and a watch URL read aloud is thirty syllables nobody can write
down. The link travels on the /execute payload's `url` field instead, beside the sentence, where
the glass can make it a link - see _hand_link() in server.py. Nothing in this file prints an
http, an https or a www any more, and broadcaster_proof asserts it.

WHY THIS IS A HAND AND THE UPLOAD IS NOT. The upload takes a minute and lands UNLISTED - a URL
nobody has - so it runs on the server's own thread with a progress bus, behind the Doorman's
BOSS-only gate. This takes four hundred milliseconds and is the instant the film becomes visible
to the world, so it is a registry tool: the Hands' gate puts a human between this house and an
act that strangers can see, which is exactly what the gate is for. Being a hand also means it
inherits the Chain Card, the one-pending-at-a-time slot, and the handshake window - so §40's
"public only on the boss's spoken Yes" needed no new gate written for it, and "a guest's yes
leaves the film unlisted" is a property of the window's BOSS seal rather than a rule in this file.

THREE REFUSALS, AND THE FIRST IS THE ONE THAT MATTERS.

  IT WILL ONLY PUBLISH A FILM THIS HOUSE UPLOADED. A registry tool can be proposed by a language
    model, so the `video` parameter can arrive invented - a video id is sixteen characters that a
    model is entirely capable of producing from nothing. An invented id is a request to make
    somebody else's video public. So the id is checked against jobs-ledger.json, which upload()
    wrote at the moment the bytes were accepted, and an id that is not in there is refused by
    name. The ledger, and not the request, is the authority on what this house has published.
  IT WILL NOT PUBLISH WHAT IS ALREADY PUBLIC, because a second flip is a second ledger row
    recording a transition that did not happen, and an audit trail with a fictitious entry in it
    is worse than none.
  AND IT NEVER DELETES. There is no path in broadcast.py that can - see METHODS_ALLOWED - so
    there is nothing in this file that could reach one.

  in    {"video": "<id>", "title": "...", "url": "...", ...} on stdin, UTF-8
  out   one plain-ASCII line
  exit  0 public, 1 not - and every failure path ends here, named

THE CREDENTIAL NEVER TRAVELS. The registry holds none of it and the server passes none of it:
this script asks broadcast.py for a token itself, in the process already trusted with secrets/.
Nothing about it goes back up the pipe, because stdout is spoken aloud in a room.
"""
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import broadcast  # noqa: E402

NO_ROAD = "I have no road to your channel yet, Addi - connect YouTube, and I shall."
RECONNECT = ("The road to your channel has closed, Addi - Google will not renew the "
             "connection, so it wants reconnecting in the Command Panel.")
# A YOUTUBE VIDEO ID, and nothing else gets as far as the network. Eleven characters of
# URL-safe base64 is the format Google has used for every video for fifteen years.
ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")


def say(line):
    sys.stdout.buffer.write(str(line).encode("ascii", "replace") + b"\n")
    sys.stdout.buffer.flush()


def fail(reason):
    say("Publishing failed: %s" % reason)
    return 1


def _title_of(video, seen):
    """The film's title for the spoken line, from the two authorities and never from a model.

    §42 puts a title where a URL used to be, which means a string this house did not write
    could end up spoken aloud - and the habit in this file is already explicit about that:
    "model text does not reach a log or a spoken line". The `title` on stdin came in with a
    proposal a language model is allowed to compose, so it is NOT read here, even though it
    is the obvious place to look.

    TWO AUTHORITIES, IN ORDER. YouTube's own read-back first: broadcast.verify() asks what
    the channel actually holds, and what the channel holds is what this house uploaded. Then
    the ledger's `topic`, which upload() wrote from the Director's own folder. If both are
    silent the sentence says "the film" rather than guessing - a goodbye with a blank in it
    reads as a bug, and a goodbye naming the wrong film is worse than either.
    """
    title = str((seen or {}).get("title") or "").strip()
    if not title:
        row = broadcast.uploaded(video) or {}
        title = str(row.get("topic") or "").strip()
    # One line, flattened: this goes to a neural voice and through an ASCII encoder.
    title = re.sub(r"\s+", " ", title)[:120].strip()
    return title or "the film"


def main():
    raw = sys.stdin.buffer.read().decode("utf-8", "replace")
    try:
        params = json.loads(raw) if raw.strip() else {}
    except ValueError as exc:
        return fail("the parameters were not JSON (%s)" % exc)
    if not isinstance(params, dict):
        return fail("the parameters were not an object")

    video = str(params.get("video") or "").strip()
    if not video:
        return fail("no film was named")
    if not ID_RE.match(video):
        # The id is not echoed. It may have come from a model, and this house's habit is that
        # model text does not reach a log or a spoken line.
        return fail("that is not a video id I can act on")

    # ---- THE GUARD. See the module docstring's first refusal. -------------------------------
    row = broadcast.uploaded(video)
    if not row:
        return fail("I have no record of putting that film up, so I shall not make it public - "
                    "the only films I publish are the ones I uploaded myself")

    _bearer, state, why = broadcast.access()
    if state in ("absent", "no-client"):
        say(NO_ROAD)
        return 1
    if state == "reconnect":
        say(RECONNECT)
        return 1
    if why:
        return fail(why)

    scope = broadcast.scope_report()
    if not scope["canPublish"]:
        # NAMED, NOT A 403 HALFWAY THROUGH. The narrow grant can upload and cannot flip privacy,
        # and a boss who approved the narrow screen should hear that sentence rather than watch a
        # confirmation succeed and nothing change.
        return fail(scope["whyNotPublish"])

    # ---- §43's FIRST READ, AND IT IS WHAT MAKES THE RETRY PATH HEAL ITSELF. -----------------
    # The film's privacy is read BEFORE anything is sent. If it is already public this hand
    # sends no update at all - which is idempotence, and it is the whole repair for the case
    # §43 was written about: a publish that really worked, was reported as failed, and is now
    # being retried by a boss who was told to say it again. The retry must not re-send an
    # update to a film that is already where he wants it; it must look, agree, and say so.
    was = broadcast.verify(video)
    if was["ok"] and was["privacy"] == broadcast.PRIVACY_PUBLIC:
        # Not an error worth the word "failed", so it exits 0: the world the boss asked for is
        # the world that exists. It is still said out loud, because he asked for a change.
        # §42: AND WITHOUT THE URL IT USED TO END ON. This line is not one of the two the
        # mandate names, and it is fixed anyway - it is a success path of this same hand, it
        # is spoken in a room by the same voice, and leaving one URL behind in the one branch
        # nobody tests is how a law lasts a fortnight.
        say("That film is already public, sir - %s." % _title_of(video, was))
        return 0

    got = broadcast.publish(video)
    # ---- §43's THREE OUTCOMES, AND THE ORDER OF THESE TESTS IS THE LAW ----------------------
    # TWO ABSOLUTES, both of which the old code broke in one line: never print a failure
    # sentence when the update returned success, and never print a success sentence without a
    # confirmed read. So `unverified` is tested BEFORE `ok`, because it is neither of those
    # things and must not be allowed to fall into either.
    if got.get("unverified"):
        # ACCEPTED, UNCONFIRMED. The sentence is the truth and the exit code is not the
        # sentence: the hands report this as failed - which is right, because nothing should
        # treat it as done - while the spoken line says exactly what happened and what to do.
        # It names the retry phrase on purpose: the first read above is what makes saying it
        # again safe, so the instruction and the mechanism were built in the same breath.
        say("YouTube accepted the change, sir, but my own read still says %s after %.0f "
            "seconds, so I will not call it done - look at the Studio, and say make it "
            "public again and I shall re-read before I re-send."
            % (got.get("privacy") or "unlisted", got.get("confirmSeconds") or 0))
        return 1
    if not got["ok"]:
        return fail(got["why"])
    # §42 - THE SECOND GOODBYE. This stdout IS the spoken answer: hands.execute() returns the
    # script's stdout as the payload's `answer`, and the page speaks that. It used to end on
    # the watch URL, so the last thing the boss heard about a film going public was a web
    # address being read out.
    #
    # THE TRANSITION IS NOT LOST, it has moved to where an audit fact belongs: the ledger row
    # broadcast.publish() just wrote carries privacyFrom and privacyTo, which is the same six
    # words in the one place that keeps them. And the URL rides on the /execute payload's own
    # `url` field - see _hand_link() in server.py - so the glass can make it clickable.
    say("It is public now, sir - %s." % _title_of(video, got))
    return 0


if __name__ == "__main__":
    sys.exit(main())
