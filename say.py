#!/usr/bin/env python3
"""say.py - a line of text in, WAV bytes out, on this machine and nowhere else.

The standard library only, plus one binary that is already installed: piper. It is
invoked as a SUBPROCESS, never imported, which is the whole reason this file adds no
pip dependency - the same arrangement hands.py uses for the scripts it runs.

    synthesise("Good evening, sir.")  ->  (wav_bytes, "", "miss")

and like search.py it NEVER raises. A missing binary, a missing model, a crashed
process, a timeout - every one of them comes back as (None, reason, "") because the
caller's next move is the same in all of those cases: tell the page that the local
voice is unavailable so it can fall back to the browser's own engine and still finish
reading the answer. An exception here would turn a fallback into a 500.

WHY A CACHE. Loading a 120 MB model costs about 2.8 seconds before a single phoneme
is produced, and the greeting, the acknowledgements and the refusals are the same
handful of sentences every session. So every synthesis is written to say-cache/ under
a hash of (model, knobs, text) and the second ask is a file read. The cache is capped
by TOTAL BYTES rather than by count - one long answer is worth a hundred short ones -
and pruned oldest-first by mtime, so the lines you actually hear most stay warm.

WHY THE KNOBS ARE HERE. length-scale 1.05 and noise-scale 0.4 are warmth, not speed:
slightly longer phonemes and slightly less generator noise read as a considered voice
rather than a hurried one. They live beside the cache key on purpose - change one and
the old audio is a different file, not a stale hit.

WHICH VOICE. The model name comes from config.json's voice_model and the file comes
from ./voices/, so recasting the voice is one config line and a download. Nothing in
here knows the name of any particular voice.
"""

import hashlib
import os
import shutil
import subprocess
from tools import _proc
import sys
import threading
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
VOICE_DIR = os.path.join(ROOT, "voices")
CACHE_DIR = os.path.join(ROOT, "say-cache")

# ---- the voice's manner. See the docstring: warmth, not speed.
LENGTH_SCALE = 1.05
NOISE_SCALE = 0.4

# ---- limits. A chunk from the page is at most 180 characters; this ceiling is four
# times that, so a hand-made request still works and a runaway one is refused rather
# than handed to a model that will spend a minute on it.
MAX_CHARS = 720
SYNTH_TIMEOUT_S = 90

# ---- the cache. 96 MB of speech is roughly two hours of it, which is far more than
# one session ever repeats; the cap exists so an unattended week cannot fill a disk.
CACHE_MAX_BYTES = 96 * 1024 * 1024

# Two at a time, no more. The page buffers one chunk ahead, so two concurrent
# syntheses is the honest peak; a third would be three copies of a 120 MB model
# resident at once, which trades the gap between sentences for a swap storm.
_GATE = threading.BoundedSemaphore(2)
_PRUNE_LOCK = threading.Lock()

DEFAULT_MODEL = "en_US-ryan-high"


# ------------------------------------------------------------------ what exists

def binary():
    """Absolute path to piper, or "".

    PATH first, because that is what a user who installed it expects to matter, then
    the Scripts directory of the interpreter running this server - pip installs the
    launcher there and that directory is frequently NOT on PATH on Windows.
    """
    found = shutil.which("piper")
    if found:
        return found
    here = os.path.dirname(os.path.abspath(sys.executable))
    for candidate in (os.path.join(here, "Scripts", "piper.exe"),
                      os.path.join(here, "Scripts", "piper"),
                      os.path.join(here, "piper.exe"),
                      os.path.join(here, "piper")):
        if os.path.isfile(candidate):
            return candidate
    return ""


def model_path(model):
    """Absolute path to the .onnx for a voice name, or "".

    The name is treated as a NAME, not a path: no separators, no parents. A voice is
    a file in ./voices/ and nothing else, so a config typo cannot turn the voice
    setting into a file-read primitive.
    """
    name = str(model or "").strip() or DEFAULT_MODEL
    name = os.path.basename(name)
    if name.endswith(".onnx"):
        name = name[:-5]
    if not name or name.startswith("."):
        return ""
    path = os.path.join(VOICE_DIR, name + ".onnx")
    return path if os.path.isfile(path) else ""


def ready(model=DEFAULT_MODEL):
    """Booleans and a reason, for /health and for the 503 body.

    Never a path and never a size the page could not already see - the browser needs
    to know whether to use the local voice, not where it lives.
    """
    name = os.path.basename(str(model or "").strip() or DEFAULT_MODEL)
    exe = binary()
    onnx = model_path(name)
    if not exe:
        why = "piper is not installed on this machine"
    elif not onnx:
        why = "voices/%s.onnx is missing" % name
    elif not os.path.isfile(onnx + ".json"):
        why = "voices/%s.onnx.json is missing" % name
    else:
        why = ""
    return {
        "engine": "piper",
        "model": name,
        "binary": bool(exe),
        "model_file": bool(onnx),
        "ready": not why,
        "why": why,
        "lengthScale": LENGTH_SCALE,
        "noiseScale": NOISE_SCALE,
    }


# ----------------------------------------------------------------- the cache

def _key(text, model):
    raw = "\x00".join([str(model), "%.4f" % LENGTH_SCALE, "%.4f" % NOISE_SCALE, text])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def _cache_file(text, model):
    return os.path.join(CACHE_DIR, _key(text, model) + ".wav")


def _prune():
    """Oldest-first until the directory is under the cap. Never raises."""
    with _PRUNE_LOCK:
        try:
            entries = []
            total = 0
            for name in os.listdir(CACHE_DIR):
                if not name.endswith(".wav"):
                    continue
                path = os.path.join(CACHE_DIR, name)
                try:
                    stat = os.stat(path)
                except OSError:
                    continue
                entries.append((stat.st_mtime, stat.st_size, path))
                total += stat.st_size
            if total <= CACHE_MAX_BYTES:
                return
            entries.sort()
            for _mtime, size, path in entries:
                if total <= CACHE_MAX_BYTES:
                    return
                try:
                    os.remove(path)
                    total -= size
                except OSError:
                    continue
        except OSError:
            return


def cache_size():
    """(files, bytes) in say-cache/, for /health. Cheap and never raises."""
    files = 0
    total = 0
    try:
        for name in os.listdir(CACHE_DIR):
            if not name.endswith(".wav"):
                continue
            try:
                total += os.path.getsize(os.path.join(CACHE_DIR, name))
            except OSError:
                continue
            files += 1
    except OSError:
        pass
    return files, total


# ------------------------------------------------------------------ the voice

def synthesise(text, model=DEFAULT_MODEL):
    """(wav_bytes, reason, source) - and it never raises.

    source is "hit" when the bytes came out of say-cache/, "miss" when piper ran.
    On any failure the bytes are None and the reason is one plain sentence fit to be
    logged and shown; the page turns that into a named fallback and keeps reading.
    """
    line = str(text or "").strip()
    if not line:
        return None, "there was no text to speak.", ""
    if len(line) > MAX_CHARS:
        return None, ("the line is %d characters and the limit is %d."
                      % (len(line), MAX_CHARS)), ""

    state = ready(model)
    if not state["ready"]:
        return None, state["why"] + ".", ""
    name = state["model"]

    path = _cache_file(line, name)
    try:
        if os.path.isfile(path) and os.path.getsize(path) > 44:
            with open(path, "rb") as fh:
                data = fh.read()
            # Touched so that pruning measures "least recently heard" rather than
            # "written longest ago" - a line repeated every session should not age out.
            try:
                os.utime(path, None)
            except OSError:
                pass
            return data, "", "hit"
    except OSError:
        pass

    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
    except OSError as exc:
        return None, "say-cache/ could not be created (%s)." % exc, ""

    # A per-process temp name, so two threads synthesising the same line cannot hand
    # each other a half-written file. The rename at the end is the publish.
    tmp = path + ".%d.%d.part" % (os.getpid(), threading.get_ident())
    argv = [
        binary(),
        "-m", model_path(name),
        "--data-dir", VOICE_DIR,
        "-f", tmp,
        "--length-scale", "%.4f" % LENGTH_SCALE,
        "--noise-scale", "%.4f" % NOISE_SCALE,
    ]
    started = time.time()
    acquired = _GATE.acquire(timeout=SYNTH_TIMEOUT_S)
    if not acquired:
        return None, "the local voice was busy for longer than it is worth waiting.", ""
    try:
        # _proc.run, NOT subprocess.run. This is the line that flashed a black window on
        # the boss's desktop after every spoken answer: piper is a console program, and a
        # console program started with the default flags is given a console, which has a
        # window. Measured, class PseudoConsoleWindow, parented to the server.
        proc = _proc.run(
            argv, input=line.encode("utf-8"),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=SYNTH_TIMEOUT_S, shell=False, cwd=ROOT)
    except subprocess.TimeoutExpired:
        _unlink(tmp)
        return None, "piper did not finish within %ds." % SYNTH_TIMEOUT_S, ""
    except OSError as exc:
        _unlink(tmp)
        return None, "piper could not be started (%s)." % exc, ""
    finally:
        _GATE.release()

    if proc.returncode != 0:
        _unlink(tmp)
        tail = (proc.stderr or b"").decode("utf-8", "replace").strip()
        tail = tail.splitlines()[-1] if tail else "no output"
        return None, "piper exited %d: %s" % (proc.returncode, tail[:200]), ""

    try:
        size = os.path.getsize(tmp)
    except OSError:
        return None, "piper wrote no audio.", ""
    if size <= 44:                                  # a WAV header and nothing after it
        _unlink(tmp)
        return None, "piper wrote an empty WAV.", ""

    try:
        with open(tmp, "rb") as fh:
            data = fh.read()
        os.replace(tmp, path)
    except OSError as exc:
        _unlink(tmp)
        return None, "the audio could not be read back (%s)." % exc, ""

    # On every miss, never on a hit: a miss already cost seconds, so one listdir is
    # free, and a hit is the path that has to stay fast enough to sound seamless.
    _prune()
    sys.stderr.write("say: %d chars -> %d bytes in %.2fs (%s)\n"
                     % (len(line), len(data), time.time() - started, name))
    return data, "", "miss"


def _unlink(path):
    try:
        os.remove(path)
    except OSError:
        pass


if __name__ == "__main__":                                      # a one-line check
    import json as _json
    print(_json.dumps(ready(sys.argv[2] if len(sys.argv) > 2 else DEFAULT_MODEL),
                      indent=2))
    if len(sys.argv) > 1:
        wav, why, src = synthesise(sys.argv[1])
        print("bytes=%s source=%s why=%s" % (len(wav) if wav else 0, src, why or "-"))
