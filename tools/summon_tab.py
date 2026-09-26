#!/usr/bin/env python3
"""summon_tab.py - bring the boss back to the tab he said he would work in.

The second drift inside thirty seconds is not absent-mindedness, it is a pull. At that
point a callout has already been said once and ignored once, so Galaxy stops narrating
and offers to do something about it: "Shall I bring you back?" - and if the answer is
yes, this is the hand that does it. Chrome's own activateTarget raises the tab AND its
window (measured: the locked tab went from visible-but-unfocused to focused, and the
window in front of it dropped back), so there is nothing to simulate and no input to
synthesise.

    echo {} | python tools/summon_tab.py
    Here you are, sir - back where you said you would be.

THE CONTRACT, as tools/selftest.py states it:

  in    one JSON object on stdin (this hand takes no parameters and reads it anyway,
        so that the shape of every hand is the same)
  out   ASCII on stdout, and stdout is the ONLY evidence. The assistant speaks it.
  exit  0 means it happened. Anything else means it did not.

WHY THIS ASKS THE SERVER INSTEAD OF DOING IT ITSELF, which is the whole design of the
hand: the identity of the locked tab lives in the running focus session and nowhere
else. It is not in the registry, not in this file, not in the proposal the boss
approved, and not on the wire between the page and the server - the proposal he sees
says "Shall I bring you back?" and carries no parameters at all, because a hand that
took a target id as a parameter would be a hand that could be pointed at any tab in
the browser by anybody who could reach the gate. So this posts one word to the local
server and the session, which already knows where you promised to be, does the rest.

  ONE DOOR. POST /focus {"cmd": "summon"} on 127.0.0.1 - the same door the pause
    button and the spoken commands use, and a door that only exists on loopback.
  THE SENTENCE IS THE SERVER'S. It knows whether the tab was still there, whether
    the window came up, and whether there was a lock at all; this file does not
    second-guess it and never invents a success.
  NOTHING IS QUEUED TWICE. The server answers this command with viaSession false,
    which is its way of saying "this sentence exists nowhere else" - so the line
    printed here is spoken exactly once, by the assistant running this hand.
"""
import json
import sys
import urllib.request

SERVER = "http://127.0.0.1:4700/focus"
TIMEOUT_S = 8.0


def say(line):
    sys.stdout.write(line.rstrip() + "\n")


def main():
    try:
        sys.stdin.read()          # the shape of every hand, even with nothing in it
    except Exception:                                          # noqa: BLE001
        pass

    body = json.dumps({"cmd": "summon", "source": "hand"}).encode("utf-8")
    request = urllib.request.Request(
        SERVER, data=body, method="POST",
        headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_S) as res:
            payload = json.loads(res.read().decode("utf-8", "replace"))
    except Exception as exc:                                   # noqa: BLE001
        # The server being unreachable is the one failure worth naming exactly: this
        # hand runs as a subprocess OF that server, so it means something has gone
        # wrong between two halves of the same machine.
        say("I could not reach the session to do it, sir (%s), so you are still where "
            "you were." % type(exc).__name__)
        return 1

    line = str(payload.get("answer") or "").strip()
    if not payload.get("ok"):
        say(line or "The session would not have it, sir, so nothing moved.")
        return 1
    if not payload.get("summoned"):
        # A refusal with a sentence: no lock, no readable target, or the tab has been
        # closed since. Reported as a failure because nothing happened, and the boss
        # asked for something to happen.
        say(line or "There is no locked tab to bring you back to, sir.")
        return 1
    say(line or "Here you are, sir - back where you said you would be.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
