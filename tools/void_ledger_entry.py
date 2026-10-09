#!/usr/bin/env python3
"""void_ledger_entry.py - strike one entry out of the ledger, after a yes. It deletes nothing.

  in    {"entry": "L-0003, expense of ₹500.00 for groq in Galaxy's own book, ...",
         "id": "L-0003", "reason": "entered twice"} on stdin, UTF-8
  out   one line, which is the only thing the assistant is allowed to claim
  exit  0 voided, 1 not

The entry keeps its row, its figures and its place; it gains void=true, the reason and the
time, and no total counts it again. That is ledger.void_entry(), and this is its only caller
apart from a person at the command line.

IT REFUSES AN ENTRY THAT CHANGED UNDER THE CARD. `entry` is how the entry read when the card
went up. It is read again here, now, by the same ledger.entry_line() - and if it is gone,
already void, or reads differently, nothing is changed. A yes is consent to strike out the
thing that was shown, not whatever has that id by the time the word arrives.
"""

import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import ledger                                                  # noqa: E402


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:                                          # noqa: BLE001
        pass
    try:
        p = json.loads(sys.stdin.read() or "{}", parse_float=ledger._no_float)
    except ValueError:
        p = None
    if not isinstance(p, dict) or not p.get("id"):
        print("The request would not parse, so nothing was voided.")
        return 1
    now = ledger.find_entry(p["id"])
    if now is None:
        print("There is no entry %s in the book, so nothing was voided." % p["id"])
        return 1
    if now.get("void"):
        print("%s is already void (%s), so nothing was changed." % (now["id"],
                                                                     now.get("voidReason")))
        return 1
    if ledger.entry_line(now) != p.get("entry"):
        print("%s no longer reads as it did on the card, so nothing was voided." % now["id"])
        return 1
    entry, error = ledger.void_entry(now["id"], p.get("reason"))
    if error:
        print(error)
        return 1
    print("%s is void: %s. It stays in the book, struck out, and no total counts it."
          % (entry["id"], entry["voidReason"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
