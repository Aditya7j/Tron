#!/usr/bin/env python3
"""set_voice.py - recast the voice by asking for it out loud.

The casting panel is the audition room: three candidates, one sentence, a button that
writes the decision. This is the same decision taken the other way round - by saying
"switch your voice to Alan" - and it exists because a butler you have to click is a
butler with a settings screen.

    echo {"voice": "alan"} | python tools/set_voice.py
    Speaking as Alan now, sir.

THE CONTRACT, kept exactly as tools/selftest.py states it:

  in    one JSON object on stdin, UTF-8, decoded from bytes rather than trusting the
        console code page - this is Windows, and a pipe here is cp1252 by default
  out   ASCII on stdout, and stdout is the ONLY evidence. The assistant speaks it.
  exit  0 means it happened. Anything else means it did not.

And that last line is the whole reason the sentence this prints is in the present
tense. "Speaking as Alan now, sir" is spoken by /say, which re-reads config.json on
every chunk - so by the time the words are synthesised the file already says Alan and
the sentence is read in the voice it is announcing. The evidence is audible.

FOUR RULES, and each is a thing that could otherwise go wrong quietly:

  A NAME IS A NAME, NEVER A PATH. The value is basenamed and matched against the
    .onnx files that are actually in ./voices/. There is no separator, no parent, and
    no way for a voice setting to become a file-read primitive. say.py keeps the same
    rule at the other end; this is the first lock, not the only one.
  WHAT IS INSTALLED IS A FACT. An id that is not on this disk is refused in words
    that say so, rather than written to config.json and discovered at the next
    restart by a machine that came back mute.
  EVERY OTHER KEY SURVIVES. config.json holds credentials. They are read here as
    opaque values, written back unexamined, never logged, never printed, and never
    counted by anything but len(). One key changes.
  THE REPLACE IS ATOMIC. Written to a temporary file beside it and moved into place,
    because a crash halfway through rewriting the file that holds the keys is not a
    state this project is going to have.

Nicknames exist because nobody says "en underscore G B dash alan dash medium" out
loud. A full model id passes through untouched, so the table is a convenience and
never a gate.
"""
import glob
import json
import os
import sys

# This script is run with cwd=tools/ by hands.py, so every path here is derived from
# __file__ and never from the working directory.
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
VOICE_DIR = os.path.join(ROOT, "voices")
CONFIG_PATH = os.path.join(ROOT, "config.json")

# The names a human says. The value is a model id, checked against the disk like any
# other - a nickname is a shortcut to a name, not a promise that the file is there.
NICKNAMES = {
    "ryan": "en_US-ryan-high",
    "joe": "en_US-joe-medium",
    "alan": "en_GB-alan-medium",
    # Alan is the northern English voice in this set, and "sound like the northern one"
    # is how somebody who has heard all three asks for him.
    "northern": "en_GB-alan-medium",
}


def say(line):
    """ASCII on stdout, whatever the console thinks its code page is."""
    sys.stdout.buffer.write(str(line).encode("ascii", "replace") + b"\n")
    sys.stdout.buffer.flush()


def label(model):
    """'en_GB-alan-medium' -> 'Alan'. The name a person would use for that voice."""
    parts = [p for p in str(model or "").split("-") if p]
    word = parts[1] if len(parts) > 1 else (parts[0] if parts else "")
    word = "".join(c for c in word if c.isalnum())
    return word[:1].upper() + word[1:] if word else str(model or "")


def installed():
    """Every voice this machine can actually speak in, sorted, as model ids.

    The disk is the authority. Both files are required: piper needs the .onnx and its
    .onnx.json alongside, and half a voice is not a voice.
    """
    found = []
    for path in sorted(glob.glob(os.path.join(VOICE_DIR, "*.onnx"))):
        if os.path.isfile(path + ".json"):
            found.append(os.path.basename(path)[:-5])
    return found


def resolve(asked):
    """(model id or "", the raw name as given). Nicknames in, ids straight through."""
    raw = os.path.basename(str(asked or "").strip())
    if raw.endswith(".onnx"):
        raw = raw[:-5]
    if not raw or raw.startswith("."):
        return "", raw
    return NICKNAMES.get(raw.lower(), raw), raw


def names(models):
    """'Ryan, Alan or Joe' - the installed voices, said the way a person would."""
    words = [label(m) for m in models]
    if not words:
        return "none at all"
    if len(words) == 1:
        return words[0]
    return ", ".join(words[:-1]) + " or " + words[-1]


def write_model(model):
    """One key changed in config.json, atomically. Returns an error string or ""."""
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as fh:
            raw = json.load(fh)
        if not isinstance(raw, dict):
            return "config.json does not contain a JSON object"
    except FileNotFoundError:
        return "config.json is not there"
    except Exception as exc:                                        # noqa: BLE001
        return "config.json could not be read (%s)" % exc

    raw["voice_model"] = model
    # The engine comes with it, for the same reason the casting button carries it:
    # a piper voice chosen while config.json asks for the browser's own voices is a
    # setting that would be silently ignored, and an announcement in the wrong voice
    # is a sentence that contradicts itself out loud.
    raw["voice_engine"] = "piper"

    tmp = CONFIG_PATH + ".setvoice.tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(raw, fh, indent=2)
            fh.write("\n")
        os.replace(tmp, CONFIG_PATH)
    except Exception as exc:                                        # noqa: BLE001
        try:
            os.unlink(tmp)
        except OSError:
            pass
        return "config.json could not be written (%s)" % exc
    # Keys, not values, and stderr rather than stdout: this is the trace, not evidence.
    sys.stderr.write("  set_voice: voice_model -> %s (%d keys preserved)\n"
                     % (model, len(raw)))
    return ""


def main():
    raw_in = sys.stdin.buffer.read().decode("utf-8", "replace")
    try:
        params = json.loads(raw_in) if raw_in.strip() else {}
    except ValueError as exc:
        say("I could not read that request, sir: the details were not JSON (%s)." % exc)
        return 1
    if not isinstance(params, dict):
        say("I could not read that request, sir: the details were not an object.")
        return 1

    here = installed()
    model, asked = resolve(params.get("voice"))
    # MISSING PARAMETER, NAMED. "I need more information" is useless to somebody who
    # cannot see the schema, so the field is said out loud.
    if not asked:
        say("I should need the voice before I could change it, sir.")
        return 1

    if model not in here:
        # TWO REFUSALS, AND THEY ARE NOT THE SAME REFUSAL. A name nobody has heard of
        # is a misunderstanding, and the cure is the list. A real voice that is not on
        # this disk is a fact about this machine, and saying "no such voice" about a
        # voice that exists would send somebody looking for a typo they never made.
        known = asked.lower() in NICKNAMES or model.lower().endswith(
            ("-high", "-medium", "-low", "-x_low"))
        if known:
            say("%s is not on this machine, sir; voices/%s.onnx is missing. "
                "I have %s." % (label(model), model, names(here)))
        else:
            say("I have no voice by that name, sir, and I will not guess at a near "
                "one. On this machine I have %s." % names(here))
        return 1

    problem = write_model(model)
    if problem:
        say("I could not change the voice, sir: %s." % problem)
        return 1
    say("Speaking as %s now, sir." % label(model))
    return 0


if __name__ == "__main__":
    sys.exit(main())
