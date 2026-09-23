#!/usr/bin/env python3
"""selftest.py - the hermetic hand. Reads a token on stdin and prints it back.

This exists so that the tool machinery can be proved end to end - registry, proposal,
validation, the confirmation gate, the subprocess, the ledger - WITHOUT a harness ever
touching your calendar, your mailbox or anything else you care about. Every preflight
run exercises the whole chain through this script, which is why it is the one tool in
the registry that does nothing.

The contract every tool in this directory keeps:

  in    one JSON object on stdin, UTF-8, decoded from bytes rather than trusting the
        console code page - this is Windows, and a pipe here is cp1252 by default
  out   ASCII on stdout, and stdout is the ONLY evidence. The assistant speaks it.
  exit  0 means it happened. Anything else means it did not, and the reason belongs
        on stdout or stderr where a human can read it.

Run it by hand:  echo {"token": "hello"} | python tools/selftest.py
"""
import json
import sys


def say(line):
    """ASCII on stdout, whatever the console thinks its code page is."""
    sys.stdout.buffer.write(str(line).encode("ascii", "replace") + b"\n")
    sys.stdout.buffer.flush()


def main():
    raw = sys.stdin.buffer.read().decode("utf-8", "replace")
    try:
        params = json.loads(raw) if raw.strip() else {}
    except ValueError as exc:
        say("Self test failed: the parameters were not JSON (%s)" % exc)
        return 1
    if not isinstance(params, dict):
        say("Self test failed: the parameters were not an object")
        return 1
    token = str(params.get("token") or "")
    if not token:
        say("Self test failed: no token was given")
        return 1
    # Echoed, capped, and stripped of anything that is not a printable character: the
    # token travels back so the caller can prove THIS run produced THIS line, and a
    # control character in a spoken sentence is a bug looking for somewhere to happen.
    clean = "".join(c for c in token[:120] if c.isprintable())
    say("Self test passed, token %s" % clean)
    return 0


if __name__ == "__main__":
    sys.exit(main())
