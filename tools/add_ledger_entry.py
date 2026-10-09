#!/usr/bin/env python3
"""add_ledger_entry.py - one entry into one of the two books, after a yes, and nothing else.

THE HAND BEHIND "Groq ka bill 500 rupaye add karo". The server parses the sentence
(ledger.parse_request), the card goes up through hands.propose() on the ledger door, and this
runs only after a word is given - the same slot, the same TTL and the same Doorman as every
other hand in this house.

  in    {"entry": "An expense of ₹500.00 for groq, in Galaxy's own book, ...",
         "book": "galaxy", "kind": "expense", "amount_paise": 50000, "currency": "INR",
         "category": "groq", "on": "2026-10-09", "proof": "none", "note": "..."}
         on stdin, UTF-8
  out   one line, which is the only thing the assistant is allowed to claim
  exit  0 written, 1 not

WHAT IT REFUSES, on top of everything ledger.add_entry() refuses for itself:

  A CARD THAT DOES NOT MATCH ITS FIGURES. `entry` is the sentence the boss heard and said yes
    to. It is composed again here, by the same ledger.describe(), from the parameters that
    will actually be written - and if the two differ by a paisa, nothing is written. What was
    approved is what goes in the book.
  AN AMOUNT THAT IS NOT AN INTEGER. JSON may carry a 500.5; this ledger does not.
"""

import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import ledger                                                  # noqa: E402


def main():
    # BOTH STREAMS, and stdin is the one that matters. hands._spawn() writes the card as UTF-8,
    # but a Windows python started without PYTHONIOENCODING reads stdin in the ANSI codepage,
    # so "₹500.00" arrived as "â‚¹500.00" and the card check below - correctly - refused it.
    try:
        sys.stdin.reconfigure(encoding="utf-8")
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:                                          # noqa: BLE001
        pass
    try:
        p = json.loads(sys.stdin.read() or "{}", parse_float=ledger._no_float)
    except ValueError:
        print("The entry would not parse, so nothing was written.")
        return 1
    if not isinstance(p, dict):
        print("The entry would not parse, so nothing was written.")
        return 1
    amount = p.get("amount_paise")
    if type(amount) is not int:
        print("The amount is not a whole number of paise, so nothing was written.")
        return 1
    proof = p.get("proof")
    proof = None if str(proof or "none").strip().lower() == "none" else proof
    proof_path, error = ledger.check_proof(proof)
    if error:
        print(error)
        return 1
    currency = str(p.get("currency") or ledger.DEFAULT_CURRENCY)
    said = ledger.describe(p.get("book"), p.get("kind"), amount, p.get("category"), currency,
                           p.get("on"), proof_path)
    if said != p.get("entry"):
        print("The card and its figures disagree, so nothing was written: the card said "
              "%r, the figures say %r." % (p.get("entry"), said))
        return 1
    entry, error = ledger.add_entry(p.get("book"), p.get("kind"), amount, p.get("category"),
                                    p.get("note") or "", currency, proof_path, p.get("on"),
                                    entered_by="chat")
    if error:
        print(error)
        return 1
    print("Written into %s as %s: %s of %s for %s, %s."
          % (ledger.BOOK_NAMES[entry["book"]], entry["id"], entry["kind"],
             ledger.money(entry["amount"], entry["currency"]), entry["category"],
             "with its proof" if entry["proof"] else "unverified, with no proof"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
