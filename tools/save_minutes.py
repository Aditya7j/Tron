#!/usr/bin/env python3
"""save_minutes.py - one meeting's minutes into notes/<title>.md, and nothing else.

The Scribe listens, the brain summarises, and this writes. That division is the whole
design: by the time this script runs there is nothing left to decide, which is what
makes it small enough to read in one sitting and safe enough to hand a confirmation to.

  in    {"title": "Meeting-2026-09-26-1432", "minutes": "## Attendees\\n...",
         "overwrite": false} on stdin, UTF-8
  out   one ASCII line, which is the only thing the assistant is allowed to claim
  exit  0 written, 1 did not

THE THREE THINGS IT REFUSES, and each one is a decision somebody else must make:

  AN EMPTY BODY. Minutes with nothing in them are a file that will be believed later.
    The panel catches this first and says "There is nothing to save, Addi."; this
    refuses it again, because a tool that trusts its caller to have checked is a tool
    that writes an empty file the day the caller changes.
  A NAME THAT IS NOT A NAME. The title becomes a FILENAME, so it is stripped to
    [A-Za-z0-9 ._-] and then to its basename. A title carrying ..\\..\\ or a drive
    letter cannot reach out of notes/ - the resolved path is checked against the
    resolved notes directory afterwards, which is the check that holds even if the
    stripping above is one day made cleverer than it should be.
  A FILE THAT ALREADY EXISTS, unless `overwrite` is true. Minutes are not a capture:
    the same meeting written twice is a correction, not a second note, so this does
    not quietly rename to -2 the way write_capture does. It refuses and names the
    file, and the page turns that into the Overwrite / Cancel pair - one more human
    decision rather than one more guess.

WHERE IT WRITES. notes/, the top level, beside the seven category folders rather than
inside one: the category of a meeting is not this script's judgement to make, and
build.py walks the tree, so the note joins the galaxy on the next rebuild. The line
below says so, because a note the employer cannot find yet is worth one clause.
"""
import json
import pathlib
import re
import sys
import time

NOTES = pathlib.Path(__file__).resolve().parent.parent / "notes"

MAX_TITLE = 120
MAX_MINUTES = 200000          # a long meeting is perhaps 30k; this is a runaway guard
SAFE = re.compile(r"[^A-Za-z0-9 ._-]+")


def say(line):
    sys.stdout.buffer.write(str(line).encode("ascii", "replace") + b"\n")
    sys.stdout.buffer.flush()


def safe_title(raw):
    """A title a filesystem will take, or ''. Never a path, never a parent."""
    clean = SAFE.sub(" ", str(raw or "")).strip()
    clean = re.sub(r"\s+", " ", clean)[:MAX_TITLE].strip(" .")
    # basename LAST, so that "../x" has already lost its slash and cannot arrive here
    # as a name that looks innocent.
    return pathlib.PurePath(clean).name


def main():
    raw = sys.stdin.buffer.read().decode("utf-8", "replace")
    try:
        params = json.loads(raw) if raw.strip() else {}
    except ValueError as exc:
        say("Minutes failed: the parameters were not JSON (%s)" % exc)
        return 1
    if not isinstance(params, dict):
        say("Minutes failed: the parameters were not an object")
        return 1

    title = safe_title(params.get("title"))
    body = str(params.get("minutes") or "").strip()[:MAX_MINUTES]
    overwrite = bool(params.get("overwrite"))
    if not title:
        title = "Meeting-" + time.strftime("%Y-%m-%d-%H%M")
    if not body:
        say("Minutes failed: there were no minutes to save")
        return 1

    try:
        NOTES.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        say("Minutes failed: could not reach the notes folder (%s)" % exc)
        return 1

    path = (NOTES / (title + ".md")).resolve()
    # THE CHECK THAT HOLDS WHATEVER THE STRIPPING DID. A resolved path that is not
    # inside the resolved notes folder is refused without being written.
    try:
        inside = path.is_relative_to(NOTES.resolve())
    except AttributeError:                                     # pragma: no cover
        inside = str(path).startswith(str(NOTES.resolve()))
    if not inside:
        say("Minutes failed: that title would write outside the notes folder")
        return 1

    existed = path.exists()
    if existed and not overwrite:
        say("Minutes not saved: notes/%s already exists. Say overwrite and I will "
            "replace it." % path.name)
        return 1

    heading = "# %s\n\n" % title
    stamp = "Minutes taken %s by the Scribe.\n\n" % time.strftime(
        "%A %d %B %Y at %H:%M")
    text = heading + stamp + body.rstrip() + "\n"
    try:
        path.write_text(text, encoding="utf-8")
        # Read it back. "write_text returned" is not the same claim as "the minutes
        # are on disk", and a meeting is the worst thing to be wrong about.
        back = path.read_text(encoding="utf-8")
        if title not in back or body[:40] not in back:
            say("Minutes failed: the file was written but came back wrong")
            return 1
    except OSError as exc:
        say("Minutes failed: could not write the file (%s)" % exc)
        return 1

    words = len(re.findall(r"\S+", body))
    sections = len(re.findall(r"^\s*#{1,6}\s+\S", body, re.M))
    say("%s notes/%s - %d words in %d section%s. It joins the galaxy on the next "
        "rebuild." % ("Replaced" if existed else "Written to", path.name, words,
                      sections, "" if sections == 1 else "s"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
