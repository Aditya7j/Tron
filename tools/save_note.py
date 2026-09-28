#!/usr/bin/env python3
"""save_note.py - one remembered thought into notes/captures/<slug>.md, and nothing else.

THE HAND BEHIND "remember that ...". The employer says it, the server strips the trigger
and titles the thought, the card goes up, and this runs only after a word is given. Before
PART 8 the capture was written the instant the sentence was heard, with no card at all -
the one write in this project that happened without consent. It is a hand now, and it goes
through the same slot, the same TTL and the same Doorman as the calendar and the email.

  in    {"title": "Finish Window Should Be 900ms", "body": "The finish window ..."}
         on stdin, UTF-8
  out   one ASCII line, which is the only thing the assistant is allowed to claim
  exit  0 written, 1 did not

WHAT IT REFUSES, and every one of them is somebody else's decision to make:

  AN EMPTY BODY. The server refuses this first - "remember that" and nothing after is a
    sentence he thought better of - and this refuses it again, because a tool that trusts
    its caller to have checked is a tool that writes an empty note the day the caller
    changes. Same argument as save_minutes.py, same shape.
  A FOLDER THAT IS NOT ONE OF TWO NAMES. `folder` is optional and defaults to captures.
    It exists because the Census files its answers in notes/census/ rather than among
    passing thoughts, and it is an ALLOWLIST of two literal words rather than a path:
    "any subdirectory of notes" would be a parameter a model fills in, and a parameter a
    model fills in with a path is a traversal waiting for a bad day. A third folder is a
    one-line edit here, made deliberately, by a person.
  A CREDENTIAL. secretscan.py's opinion, which is the SAME opinion the server used to
    refuse at proposal time, imported rather than restated so the two cannot drift. A
    password in a note is not a small problem: notes are INDEXED, so it becomes a passage
    that a later question can be answered out loud with. The refusal names the KIND and
    never the value - see secretscan's own docstring.
  A TITLE THAT IS NOT A NAME. The title becomes a FILENAME, so it goes through build.py's
    slugify and then its basename, and the resolved path is checked against the resolved
    captures directory afterwards. That last check is the one that holds even if slugify is
    one day made cleverer than it should be.

WHAT IT DOES NOT REFUSE: a name already taken. A capture is not minutes - the same thought
twice is two thoughts, not a correction - so it steps aside to -2, -3, the way
write_capture always did. save_minutes refuses instead, and the difference is deliberate.

WHERE IT WRITES. notes/captures/ or notes/census/, each of which the galaxy shows as its
own cluster. The star itself is born by the server: it re-indexes in process, keeping every
existing node id, so the note is a citizen that the very next question can cite. This
script's job ends at "the bytes are on disk and I have read them back".
"""
import json
import pathlib
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import build                                                   # noqa: E402
import secretscan                                              # noqa: E402

NOTES = HERE.parent / "notes"
# TWO WORDS, AND THEY ARE WORDS RATHER THAN PATHS. See the docstring: the value arrives
# through a registry parameter, so the only safe shape for it is a key in a table written
# here. Anything else is refused by name and nothing is written.
FOLDERS = {"captures": "captures", "census": "census"}
DEFAULT_FOLDER = "captures"

MAX_TITLE = 120
MAX_BODY = 20000              # a remembered thought is a sentence; this is a runaway guard
MAX_SUFFIX = 200


def say(line):
    sys.stdout.buffer.write(str(line).encode("ascii", "replace") + b"\n")
    sys.stdout.buffer.flush()


def main():
    raw = sys.stdin.buffer.read().decode("utf-8", "replace")
    try:
        params = json.loads(raw) if raw.strip() else {}
    except ValueError as exc:
        say("Not remembered: the parameters were not JSON (%s)" % exc)
        return 1
    if not isinstance(params, dict):
        say("Not remembered: the parameters were not an object")
        return 1

    body = str(params.get("body") or "").strip()[:MAX_BODY]
    title = str(params.get("title") or "").strip()[:MAX_TITLE]
    if not body:
        say("Not remembered: there was nothing to write down")
        return 1

    asked = str(params.get("folder") or DEFAULT_FOLDER).strip().lower()
    if asked not in FOLDERS:
        # NAMED, and the names are listed: a refusal that said "bad folder" would leave
        # whoever sent it guessing, and there are only two right answers.
        say("Not remembered: %r is not one of the folders I write into (%s)"
            % (asked[:40], ", ".join(sorted(FOLDERS))))
        return 1
    captures = NOTES / FOLDERS[asked]

    # THE PRIVACY LAW, AT THE DOOR WHERE A NOTE IS MADE. Both fields, because a title is
    # derived from the first few words of the body and a secret said early lands in both.
    hits = secretscan.found(body) or secretscan.found(title)
    if hits:
        # The kinds and the count. Not the offset, not the length, and never the value:
        # this line is spoken aloud and written to a log, and a refusal that quotes the
        # secret has copied it into the record that exists to prove it was kept out.
        say("Not remembered: %s, and a credential does not go into a note that will be "
            "indexed and read back to you. Say it again without the value."
            % secretscan.reason(hits))
        return 1

    stem = build.slugify(title) or "capture"
    # basename LAST, so a title carrying a separator has already lost it and cannot arrive
    # here as a name that looks innocent.
    stem = pathlib.PurePath(stem).name or "capture"

    try:
        captures.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        say("Not remembered: could not reach the %s folder (%s)" % (asked, exc))
        return 1

    root = captures.resolve()
    path = (captures / (stem + ".md")).resolve()
    suffix = 2
    while path.exists():
        path = (captures / ("%s-%d.md" % (stem, suffix))).resolve()
        suffix += 1
        if suffix > MAX_SUFFIX:
            say("Not remembered: there are already too many notes named like that")
            return 1

    # THE CHECK THAT HOLDS WHATEVER THE SLUG DID, AND WHATEVER `folder` SAID. A resolved
    # path outside the resolved folder is refused without being written.
    try:
        inside = path.is_relative_to(root)
    except AttributeError:                                     # pragma: no cover
        inside = str(path).startswith(str(root))
    if not inside:
        say("Not remembered: that title would write outside the notes folder")
        return 1

    shown = title or build.label_from_filename(stem)
    text = ("# %s\n\n"
            "Captured %s.\n\n"
            "%s\n" % (shown, time.strftime("%A %d %B %Y at %H:%M"), body))
    try:
        path.write_text(text, encoding="utf-8")
        # Read it back. "write_text returned" is not the same claim as "the note is on
        # disk", and this is the one place that difference bites: the whole point of the
        # feature is that he can stop holding the thought himself.
        back = path.read_text(encoding="utf-8")
        if body[:40] not in back:
            say("Not remembered: the file was written but came back wrong")
            return 1
    except OSError as exc:
        say("Not remembered: could not write the file (%s)" % exc)
        return 1

    words = len(body.split())
    say("Noted and filed: notes/%s/%s - %d word%s."
        % (FOLDERS[asked], path.name, words, "" if words == 1 else "s"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
