#!/usr/bin/env python3
"""relaunch_chrome.py - open the DevTools port, so a tab can actually be locked.

Tab-level locking needs Chrome's --remote-debugging-port. Without it a focus session
watches the APPLICATION, which means every tab in the browser looks like the one you
promised to work in. The old behaviour when the port was missing was to quietly fall
back to that, which is the one thing a watchdog must never do: it kept the word
"locked" and dropped the meaning. So the port is now something Galaxy can ASK for.

    echo {} | python tools/relaunch_chrome.py
    The debugging port is open on 9222, sir - Chrome/153.0.8010.54, with the three
    tabs you had restored. A tab can be locked properly now.

THE CONTRACT, as tools/selftest.py states it:

  in    one JSON object on stdin (this hand takes no parameters, and reads it anyway
        so that the shape of every hand is the same)
  out   ASCII on stdout, and stdout is the ONLY evidence. The assistant speaks it.
  exit  0 means it happened. Anything else means it did not.

WHAT THIS IS CAREFUL ABOUT, and each line of it was measured rather than assumed:

  IT DESTROYS NOTHING IT DOES NOT HAVE TO. A browser already running only blocks this
    launch if it holds THE SAME PROFILE; the launcher uses a profile of its own. On
    the machine this was written on, a second Chrome on its own --user-data-dir opened
    the port in 332 ms with nineteen processes of ordinary browsing still running
    beside it. So the ordinary case closes nothing at all, and the boss's real windows
    are never in this hand's way.
  THE SESSION COMES BACK. In the one case that does need the profile cleared - a
    portless Chrome already on the DevTools profile - launch-chrome.ps1 closes it with
    WM_CLOSE, which is what the X button sends and the only exit that writes "Last
    Session"; then --restore-last-session hands the tabs back. Measured both ways:
    after a force kill the relaunch came back with one empty tab, after a polite close
    it came back with every tab plus the viewer.
  IT CHECKS FIRST. If the port already answers, this hand does nothing and says so.
    A hand that restarts a browser to discover the restart was unnecessary is a hand
    that cost you your tabs for a fact it could have read.
  IT PROVES IT. Nothing here reports success because a process started. The port is
    asked for its version and the server is asked what /health now sees, and the
    sentence is built out of those two answers.
  IT RUNS THE LAUNCHER, rather than reimplementing it. The flags live in exactly one
    place - launch-chrome.ps1 - so the double-click on the Desktop and this hand
    cannot drift apart. That is also why -Quiet exists: the launcher waits for a
    keypress on failure, and there is nobody here to press anything.
"""
import json
import os
import subprocess
import _proc
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LAUNCHER = os.path.join(ROOT, "launch-chrome.ps1")
PORTS = (9222, 9223, 9224)        # the three focus.py looks at, in its order
PORT = 9222                       # the one the launcher opens by default
PORT_WAIT_S = 30.0                # the launcher's own patience is 18s; this is slack
SERVER = "http://127.0.0.1:4700"


def say(line):
    sys.stdout.write(line.rstrip() + "\n")


def get_json(url, timeout=1.5):
    """The answer, or None. Never an exception: every caller here reads None as "that
    endpoint did not answer", which is a fact about the port and not about us."""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as res:
            return json.loads(res.read().decode("utf-8", "replace"))
    except Exception:                                          # noqa: BLE001
        return None


def live_port():
    """(port, version-string) for the first port that answers, or (None, "")."""
    for port in PORTS:
        found = get_json("http://127.0.0.1:%d/json/version" % port)
        if isinstance(found, dict):
            return port, str(found.get("Browser") or "a browser")
    return None, ""


def tab_count(port):
    """How many ordinary pages came back. Titles and urls are NOT read: the count is
    the whole of what the sentence needs, and this hand has no business holding a
    list of what the boss had open."""
    found = get_json("http://127.0.0.1:%d/json/list" % port)
    if not isinstance(found, list):
        return 0
    return sum(1 for t in found
               if isinstance(t, dict) and t.get("type") == "page"
               and str(t.get("url") or "").lower().startswith(("http://", "https://")))


def spoken_count(n):
    return ("no tabs", "one tab", "two tabs", "three tabs", "four tabs", "five tabs",
            "six tabs")[n] if n < 7 else "%d tabs" % n


def main():
    try:
        sys.stdin.read()          # the shape of every hand, even with nothing in it
    except Exception:                                          # noqa: BLE001
        pass

    port, version = live_port()
    if port is not None:
        # NOTHING TO DO, and saying so is the honest outcome rather than a failure.
        # focus.py caches capability() for three seconds, so a lock attempted a moment
        # from now will see this port.
        say("The debugging port was already open on %d, sir - %s. Nothing needed "
            "restarting; a tab can be locked as it is." % (port, version))
        return 0

    if not os.path.isfile(LAUNCHER):
        say("I cannot find launch-chrome.ps1 where it should be, sir, so I have not "
            "touched the browser.")
        return 1

    started = time.monotonic()
    try:
        done = _proc.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
             "-File", LAUNCHER, "-Port", str(PORT), "-Quiet"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=90, shell=False, cwd=ROOT)
    except subprocess.TimeoutExpired:
        say("The launcher was still running after ninety seconds, sir, so I stopped "
            "waiting. I cannot tell you what state the browser is in.")
        return 1
    except OSError as exc:
        say("I could not start the launcher at all, sir: %s." % type(exc).__name__)
        return 1

    # The launcher's own verdict is worth reading, but it is NOT the evidence: it can
    # exit 0 having warned about /health while the port is perfectly open, and it can
    # exit 2 on a port that came up a moment later. The port is the evidence.
    port, version = None, ""
    deadline = time.monotonic() + PORT_WAIT_S
    while time.monotonic() < deadline:
        port, version = live_port()
        if port is not None:
            break
        time.sleep(0.3)

    if port is None:
        tail = " ".join((done.stdout or "").split())[-220:]
        say("The debugging port never answered, sir, so tab-level locking is still "
            "unavailable. The launcher said: %s" % (tail or "nothing at all."))
        return 1

    # Give the restored tabs a moment to register as pages before counting them, and
    # give focus.py's three-second capability cache time to expire - so that "a tab
    # can be locked now" is true when it is said, not shortly afterwards.
    time.sleep(3.2)
    tabs = tab_count(port)
    health = get_json(SERVER + "/health", timeout=4) or {}
    sees = bool((health.get("focus") or {}).get("cdp"))

    say("The debugging port is open on %d, sir - %s, with %s restored%s. %s"
        % (port, version, spoken_count(tabs),
           " in %.0f seconds" % (time.monotonic() - started),
           "I can see it from here, so a tab can be locked properly now."
           if sees else
           "The server has not noticed it yet; it will within a few seconds."))
    return 0


if __name__ == "__main__":
    sys.exit(main())
