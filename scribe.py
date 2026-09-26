#!/usr/bin/env python3
"""scribe.py - a few seconds of audio in, a line of text out, on this machine only.

This is the Scribe's ear. The page mixes the meeting - what comes out of the speakers
and what comes in at the microphone - into one stream, cuts it into three-second
chunks, and posts them here one at a time. Each chunk is decoded and transcribed by
faster-whisper and comes back as {text, start, end, language}.

THE PRIVACY LAW, WHICH IS THE FIRST THING THIS FILE IS FOR. No audio byte is ever
written to disk. Not to a temporary file, not to a cache, not to a log. That is not a
policy statement, it is the reason the decode is done the way it is: faster-whisper
accepts a FILE-LIKE OBJECT as well as a path, PyAV decodes straight out of it, so the
chunk lives in one bytes object in RAM and the reference is dropped the moment the
transcript exists. Measured on this machine, both routes give the same transcript off
the same bytes:

    path     0.97s  segs=3  "According to current web sources, Java's script was..."
    BytesIO  0.73s  segs=3  "According to current web sources, Java's script was..."

so nothing is bought by touching the disk except a file somebody has to remember to
delete. The transcript TEXT is held by the page, in RAM, until the session ends; this
file holds none of it either - see `state()`, which counts chunks and seconds and
keeps no words.

AND IT NEVER RAISES, for the same reason say.py never raises: the caller's next move
is identical for a missing library, a half-written chunk and a burst of noise that
decodes to nothing - tell the page, in one sentence, and keep the meeting running. An
exception here would turn a silent three seconds into a 500 and take the panel down
with it. The two real failures are both proved rather than assumed:

    junk   -> InvalidDataError: [Errno 1094995529] Invalid data found when processing
    empty  -> InvalidDataError: [Errno 1094995529] Invalid data found when processing

both of which come back as ("", why) and are shown as a skipped chunk.

WHY base.en, cpu, int8. The mandate's three settings, and the measurements that make
them the right three on this box: a 3-second chunk transcribes in about 0.50s and a
12.8-second one in 0.73s, so the transcriber runs roughly 17x faster than the meeting
it is listening to - there is no queue, and a laptop fan is the worst that happens.
int8 is what keeps the model near 140 MB rather than near 500; `base.en` is
English-only, which is both smaller and better at English than `base`; and `cpu` is
not a compromise but the only honest choice on a machine whose GPU is already drawing
a twelve-thousand-point head at sixty frames a second.

ONE MODEL, HELD, AND WARMED IN THE BACKGROUND. A cold start pays for a download
(about 145 MB from HuggingFace, once, cached under ~/.cache/huggingface); a warm one
costs 0.98s. Either way the load happens on a daemon thread started when the server
starts, so `python server.py` answers /health immediately and the first chunk of the
first meeting does not pay for the model. A chunk that arrives while the model is
still loading WAITS for it rather than being refused - the alternative is throwing
away three seconds of somebody's meeting to save them a second.
"""

import io
import os
import threading
import time

MODEL_NAME = "base.en"
DEVICE = "cpu"
COMPUTE_TYPE = "int8"

# Four of the eight logical processors. The whole machine would transcribe a chunk a
# little faster and make piper stutter doing it: the Scribe is a background listener
# and the voice is a foreground promise.
CPU_THREADS = 4

# A chunk is three seconds, which is about 96 KB of 16 kHz mono PCM in a WAV wrapper.
# This ceiling is far above that on purpose - a hand-made request, or a browser that
# hands over a whole webm cluster, still works - and a runaway upload is refused
# rather than decoded.
MAX_CHUNK_BYTES = 8 * 1024 * 1024

# How long a chunk will wait for the model on a cold first meeting. Past this the
# chunk is refused with a sentence rather than held for ever.
LOAD_WAIT_S = 45.0

# Greedy decoding. beam_size=5 costs about three times as much for a transcript that
# differs on proper nouns a meeting's minutes will not turn on.
BEAM_SIZE = 1

_LOCK = threading.Lock()          # one transcribe at a time through one model
_LOAD_LOCK = threading.Lock()
_READY = threading.Event()

_model = None
_why = ""
_loading = False
_load_ms = 0
_import_ok = None

_seen = {"chunks": 0, "bytes": 0, "audioS": 0.0, "chars": 0, "refused": 0,
         "transcribeMs": 0}


def available():
    """Can faster-whisper be imported at all? The one question the button asks.

    Cached, because the answer cannot change inside a process and the import costs
    0.20s the first time.
    """
    global _import_ok, _why
    if _import_ok is None:
        try:
            import faster_whisper                              # noqa: F401
            _import_ok = True
        except Exception as exc:                               # noqa: BLE001
            _import_ok = False
            _why = "faster-whisper is not installed on this machine (%s)" % exc
    return _import_ok


def _load():
    global _model, _why, _loading, _load_ms
    with _LOAD_LOCK:
        if _model is not None or not available():
            _loading = False
            return _model
        started = time.time()
        _loading = True
        try:
            from faster_whisper import WhisperModel
            _model = WhisperModel(MODEL_NAME, device=DEVICE,
                                  compute_type=COMPUTE_TYPE, cpu_threads=CPU_THREADS)
            _load_ms = int((time.time() - started) * 1000)
            _why = ""
            _READY.set()
        except Exception as exc:                               # noqa: BLE001
            _model = None
            _why = "the transcriber could not load %s (%s)" % (MODEL_NAME, exc)
        finally:
            _loading = False
    return _model


def warm():
    """Start the load on a daemon thread. Called once, when the server starts."""
    if not available() or _model is not None:
        return False
    threading.Thread(target=_load, name="scribe-warm", daemon=True).start()
    return True


def state():
    """What the page is allowed to know: booleans, names and counts. No words.

    `installed` decides whether the Scribe button works at all - false is what puts
    SCRIBE: TRANSCRIBER OFFLINE on the seal. `ready` is whether the model is loaded
    right now; a page may start a meeting on `installed` alone, because a chunk waits.
    """
    return {
        "installed": bool(available()),
        "ready": _model is not None,
        "loading": bool(_loading),
        "model": MODEL_NAME,
        "device": DEVICE,
        "computeType": COMPUTE_TYPE,
        "cpuThreads": CPU_THREADS,
        "loadMs": _load_ms,
        "why": _why,
        # The privacy law, stated where a harness can read it rather than only in a
        # comment: this process has no path it would write audio to.
        "keepsAudio": False,
        "keepsText": False,
        "chunks": _seen["chunks"],
        "refused": _seen["refused"],
        "audioSeconds": round(_seen["audioS"], 1),
        "audioBytes": _seen["bytes"],
        "transcribedChars": _seen["chars"],
        "transcribeMs": _seen["transcribeMs"],
        "maxChunkBytes": MAX_CHUNK_BYTES,
    }


def transcribe(data, language="en"):
    """Bytes in, ({text, start, end, language}, why) out. Never raises.

    `why` is empty on success and one plain sentence otherwise. A chunk that decodes
    but holds no speech is a SUCCESS with an empty text: three seconds of a quiet room
    is a true answer, and silence is what most of a meeting's audio is. Proved rather
    than hoped - three seconds of digital silence gives zero segments and not the
    "Thank you." a whisper model is famous for inventing.
    """
    if not available():
        return None, _why or "faster-whisper is not installed on this machine"
    size = len(data or b"")
    if not size:
        _seen["refused"] += 1
        return None, "the chunk had no bytes in it."
    if size > MAX_CHUNK_BYTES:
        _seen["refused"] += 1
        return None, ("the chunk is %.1f MB and the limit is %.1f MB."
                      % (size / 1048576.0, MAX_CHUNK_BYTES / 1048576.0))

    if _model is None:
        if not _loading:
            # Nobody warmed it - a hand-made request, or a server started before this
            # file existed. Load it here rather than refusing.
            threading.Thread(target=_load, name="scribe-load", daemon=True).start()
        if not _READY.wait(LOAD_WAIT_S):
            _seen["refused"] += 1
            return None, (_why or "the transcriber is still loading %s." % MODEL_NAME)
    model = _model
    if model is None:
        _seen["refused"] += 1
        return None, _why or "the transcriber is unavailable."

    started = time.time()
    try:
        with _LOCK:
            # THE BYTES, AND THE ONLY COPY OF THEM. A BytesIO over the buffer we were
            # handed - no NamedTemporaryFile, no cache directory, nothing with a path.
            segments, info = model.transcribe(
                io.BytesIO(data), beam_size=BEAM_SIZE,
                language=language or None,
                # Each chunk is decoded on its own, so there is no previous text to
                # condition on and asking for it invites a model to repeat the last
                # thing it was sure of when this chunk is noise.
                condition_on_previous_text=False,
                # Silero, bundled with faster-whisper and running on the onnxruntime
                # already installed. It is here for the failure mode a meeting makes
                # constantly: near-silence, which a whisper model will happily
                # transcribe as "Thank you." or a subtitle credit.
                vad_filter=True)
            rows = list(segments)
    except Exception as exc:                                   # noqa: BLE001
        _seen["refused"] += 1
        name = type(exc).__name__
        return None, ("that chunk was not audio this machine could decode (%s)" % name)

    text = " ".join((r.text or "").strip() for r in rows).strip()
    start = float(rows[0].start) if rows else 0.0
    end = float(rows[-1].end) if rows else 0.0
    lang = getattr(info, "language", "") or (language or "")
    took = int((time.time() - started) * 1000)

    _seen["chunks"] += 1
    _seen["bytes"] += size
    _seen["chars"] += len(text)
    _seen["transcribeMs"] += took
    _seen["audioS"] += float(getattr(info, "duration", 0.0) or 0.0)

    return {"text": text, "start": round(start, 3), "end": round(end, 3),
            "language": lang, "tookMs": took,
            "durationS": round(float(getattr(info, "duration", 0.0) or 0.0), 3)}, ""


if __name__ == "__main__":                                     # a hand check, not a test
    import sys
    print("installed:", available(), _why)
    t0 = time.time()
    _load()
    print("load %.2fs  state: %s" % (time.time() - t0, state()))
    for path in sys.argv[1:]:
        with open(path, "rb") as fh:
            blob = fh.read()
        out, why = transcribe(blob)
        print(os.path.basename(path), "->", why or out)
