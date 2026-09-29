"""THE SCHOLAR - a daemon that studies the boss's syllabus while nobody is talking to it.

It rotates the topics in scholar_syllabus.json by weight and by how long each one has been
neglected, gathers what the web gate will give it plus one YouTube talk, transcribes the talk
through the §28 Groq client in chunks that cannot be too large, asks a model for three bullets
of insight, has those three bullets screened by a safety model before they are allowed to
exist, and writes the survivors into notes/study/auto/ with provenance in the front matter.

THE GATE HOLDS, AND IT HOLDS STRUCTURALLY RATHER THAN BY POLICY
    This module imports no hand. There is no path from anything in this file to an email, a
    calendar entry, a voice change or a relaunched browser: `hands` is not imported, no tool id
    is named, and the four subprocesses it may ever spawn are yt-dlp, ffmpeg, ffprobe and
    build.py - named as constants, resolved to absolute paths, and nothing else.
    Every write goes through _guarded_write(), which refuses any destination outside
    STUDY_DIR. The one exception is promote(), which writes into the personal corpus, and it
    is unreachable without a gated spoken yes carried in from the server.
    The web is reached only through search.py - the same read-only door a conversational
    question opens - and never with a body, a cookie or a credential.
    preflight's check 42 asserts all of that against this file's own source.

THE ASYNC LAW (Reality Check 1)
    The loop runs on its own daemon thread and shares ZERO locks with the conversational
    path. It never touches server._lock (the notes index and the session histories),
    server._brain_lock, server._SPEAKER_LOCK or server._turn_local. It cannot, because it
    does not call ensure_index(): it writes a file, runs build.py in a subprocess, and the
    NEXT conversational turn notices notes-index.json's mtime has moved and reloads on its
    own thread, under its own lock, in its own time. That mtime handshake is the whole of the
    coupling between the two halves of this process, and it is one integer.

    THE FAILURE MODE THAT DESIGN EXISTS FOR: a study tick that took the index lock to publish
    its own note would block every retrieval in the house for as long as an embedding takes,
    and the symptom would be a butler who goes quiet for ten seconds at random - unreproducible,
    because it depends on what the daemon happened to be doing. Latency parity is asserted in
    study_proof.mjs (d) and in preflight's check 41 rather than hoped for.

THE CHUNKING LAW (Reality Check 2)
    yt-dlp downloads the audio; ffmpeg re-cuts it to 16 kHz mono 16-bit WAV - which is what
    Groq downsamples to anyway, so nothing is lost - in segments of CHUNK_SECONDS; each
    segment is transcribed by its own sequential whisper-large-v3-turbo call; the transcripts
    are stitched in order with a boundary marker naming the chunk and its offset.

    A REQUEST OVER 25 MB IS IMPOSSIBLE BY CONSTRUCTION, and "by construction" means three
    independent things have to fail at once for one to happen: CHUNK_SECONDS x the byte rate
    of the format we ask ffmpeg for is 7.68 MB, every chunk's size is checked against
    CHUNK_MAX_BYTES before the call and re-split if it is over, and the §28 client itself
    refuses anything above its own GROQ_STT_MAX_BYTES of 8 MB before spending a round trip.
    The binding ceiling here is 8 MB and not 25 MB, and that is worth saying out loud: the
    mandate names 20 MB chunks, the §28 client - which is DO-NOT-ALTER - will not carry them,
    and the smaller ceiling satisfies the larger law with room to spare.

    On a 400 Bad Request the chunk is halved and retried exactly once, because the one thing a
    400 plausibly means here is a chunk this transcriber will not take; a second halving would
    be a retry loop wearing a disguise.

THE POISON GUARD, IN TWO LIMBS BECAUSE ONE MODEL CANNOT ANSWER BOTH QUESTIONS
    The mandate asks for toxic, hallucinatory and off-syllabus in one screening. A safety
    model classifies content against harm categories; it has no opinion on whether a bullet is
    supported by the transcript it came from or on whether it serves the boss's revenue goals.
    So: limb one is a safety model and it decides toxic. Limb two is a strict-JSON verdict
    from the ordinary chat model against the evidence and the syllabus, and it decides
    grounded and on-topic. Either limb can veto.

    THE SAFETY MODEL §28 RESERVED NO LONGER EXISTS. meta-llama/llama-guard-4-12b was named in
    the mandate and is the model §28 measured and left deliberately unwired; asked for it on
    2026-09-29, Groq answered HTTP 400 "has been decommissioned and is no longer supported",
    and the whole llama-guard family is absent from GET /v1/models. The replacement is
    openai/gpt-oss-safeguard-20b, taken from that live list rather than from documentation,
    and it is a better fit than the model it replaces: llama-guard scores against a fixed
    harm taxonomy, while gpt-oss-safeguard is handed the policy it is to enforce and answers
    against that - which is why SAFETY_POLICY below is written out in full where it can be
    read and argued with, instead of being implied by a model's training. Both limbs failing to answer is also a veto - the guard FAILS CLOSED, no note is
    written, and the ledger records the tick as skipped with the reason. The mandate asks for
    the note to be deleted; it is never created, which is the same guarantee reached earlier,
    and tick() says why at the line that does it.

EVERY DURATION HERE IS MEASURED
    Not one stage reports a time it did not take from time.perf_counter(). The ledger row
    carries fetchMs, splitMs, sttMs, thinkMs, guardMs, writeMs, buildMs and totalMs, and
    public_state() carries the same numbers for the seal to read. waitedMs is carried beside
    them because a stage that SLEPT is not a stage that worked: the guard's one 20s wait on a
    429 is most of a tick when it happens, and a budget nobody can decompose is not a budget.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time

import search as websearch
from tools import _proc

# `subprocess` IS IMPORTED FOR ITS EXCEPTIONS AND NOT FOR ITS SPAWNS. TimeoutExpired is the
# one thing yt-dlp and ffmpeg fail with that this file has to catch by name; every actual
# child process in here is started by _proc.run, which is the only door in the house that
# knows about CREATE_NO_WINDOW.

ROOT = os.path.dirname(os.path.abspath(__file__))
SYLLABUS_PATH = os.path.join(ROOT, "scholar_syllabus.json")
STATE_PATH = os.path.join(ROOT, "scholar-state.json")
LEDGER_PATH = os.path.join(ROOT, "study-ledger.json")
STUDY_DIR = os.path.join(ROOT, "notes", "study", "auto")
PROMOTE_DIR = os.path.join(ROOT, "notes", "personal")
BUILD_PY = os.path.join(ROOT, "build.py")

# ---------------------------------------------------------------- the two ceilings
#
# GROQ_HARD_MAX is the law: Groq's own documented free-tier limit, quoted from
# console.groq.com/docs/speech-to-text on 2026-09-29. Nothing in this file may hand the
# transcriber more than this, and _assert_transcribable() is the assertion that says so.
#
# CHUNK_MAX_BYTES is the ceiling that actually binds, and it is the §28 client's, not ours.
# call_groq_whisper() checks len(audio) > GROQ_STT_MAX_BYTES (8 MB) BEFORE the request and
# returns a refusal string rather than raising. That client is DO-NOT-ALTER, so the Scholar
# cuts to fit it. A chunk over 8 MB would not produce a 400 from Groq - it would never leave
# the house, which is a different failure with a different log line, and conflating the two
# is how somebody spends an afternoon reading Groq's status page.
GROQ_HARD_MAX = 25 * 1024 * 1024
CHUNK_MAX_BYTES = 8 * 1024 * 1024

AUDIO_RATE = 16000        # what Groq downsamples to anyway; asking for it saves the upload
AUDIO_BYTES_PER_S = AUDIO_RATE * 2        # mono, 16-bit: 32 000 B/s
CHUNK_SECONDS = 240       # 7.68 MB at the rate above - under 8 MB with 320 KB to spare
CHUNK_FLOOR_S = 30        # a halving below this is a splitter that has lost an argument
MAX_CHUNKS = 24           # ~96 minutes of audio; a ceiling on spend, not on ambition

# THE TOKEN BUDGET, WHICH IS AS REAL A CEILING AS THE BYTE ONE. Measured on 2026-09-29: a
# tick sending 24 000 characters of transcript to the thinking model earned a 429 on the very
# next call, which was the Poison Guard's - so the free tier's tokens-per-minute window, not
# the 90 second wall clock, is what a study tick actually runs out of first. The guard is the
# call that must never be the one to lose, because losing it means no note is written at all.
THINK_CHARS = 14000               # the whole thinking prompt
THINK_TRANSCRIPT_CHARS = 8000     # the transcript's share of it
#
# THE GUARD MAY NEVER SEE LESS THAN THE AUTHOR DID, AND THESE ARE DERIVED RATHER THAN CHOSEN SO
# THAT IT CANNOT. They were three independent numbers - think 12 000, guard 8 000 of which 4 000
# transcript - and the asymmetry showed up in the ledger as poison. Measured on 2026-09-29 across
# nineteen ticks: fourteen skipped, and two real ones refused with "Invented 45.6% statistic not
# present in provided evidence" and "implies active trading risk not present in evidence". The
# arithmetic behind those two sentences: four article snippets are 4 800 characters, the evidence
# blob was cut at 8 000, so the transcript's real share was ~3 200 of the 10 224 characters the
# THINKER had read. The guard was not wrong and the model had not hallucinated - the grounds were
# in the part of the transcript the guard was never shown, and it said so honestly. A guard that
# vetoes correct work is safe and useless; it fails closed on its own blindness.
#
# So the guard's budget IS the thinker's budget, as an expression and not as a matching pair of
# literals, and the transcript share came down to 8 000 on both sides rather than the guard's
# coming up to 12 000 - because the ceiling that actually binds a study tick is the free tier's
# tokens-per-minute window, not the wall clock, and the 429 this comment block first recorded was
# earned by a 24 000-character transcript. Two symmetric 14 000-character prompts per tick is less
# than the old asymmetric pair and cannot produce an ungrounded veto by construction.
GUARD_EVIDENCE_CHARS = THINK_CHARS
GUARD_TRANSCRIPT_CHARS = THINK_TRANSCRIPT_CHARS
GUARD_RETRY_S = 20.0              # one wait, on a transient refusal only

TICK_BUDGET_S = 90.0      # declared, recorded per tick, and never used as a timeout
POLL_S = 0.5              # how often the daemon looks for a request or a due topic
DAEMON_IDLE_S = 3600.0    # how long between unprompted ticks
LEDGER_HISTORY_MAX = 60
DIGEST_MAX = 12

# The safety model, read off Groq's live GET /v1/models on 2026-09-29 rather than out of the
# mandate, because the model the mandate named has been decommissioned. See screen()'s
# docstring for the substitution and its reason.
SAFETY_MODEL = "openai/gpt-oss-safeguard-20b"
SAFETY_MODEL_RETIRED = "meta-llama/llama-guard-4-12b"

# THE POLICY IS IN THE REPOSITORY, NOT IN A MODEL'S HEAD. gpt-oss-safeguard enforces the
# policy it is given, so the screening rule is a reviewable paragraph: the boss can read what
# his Scholar refuses to write down, and change it, without anyone guessing at a taxonomy.
# The last clause is the one that matters most and is the easiest to leave out - a study note
# is going into a corpus a butler will later quote as fact, so a confident fabrication is the
# harm here, not merely rudeness.
SAFETY_POLICY = (
    "You are a content screening classifier for notes about to be filed in a business "
    "owner's private research corpus, where an assistant will later quote them back to him "
    "as fact.\n\n"
    "POLICY - content VIOLATES this policy if it contains any of:\n"
    "  - hate, harassment, threats, slurs, or abuse directed at any person or group\n"
    "  - sexual content, or content sexualising anyone\n"
    "  - instructions or encouragement for violence, self-harm, crime, or wrongdoing\n"
    "  - medical, legal or financial instruction presented as certainty where acting on it "
    "could cause real loss\n"
    "  - a specific factual claim - a number, a name, a date, a citation - stated as "
    "established when it is plainly invented\n\n"
    "Ordinary business analysis, opinion, strategy and criticism of companies or practices "
    "do NOT violate this policy.\n\n"
    "Answer with exactly one word on the first line: VIOLATION or ALLOW."
)

# ------------------------------------------------------------------ injected by server.py
#
# The same idiom focus.py uses for ASK_HAND: the server owns the Groq client and the config
# reader, this module owns the loop, and neither imports the other. A None here is not a
# failure to configure - it is a tick that says "there is no transcriber wired up" in the
# ledger and stops, which is what tools/study_tick.py sees if it forgets to call configure().
GROQ_CHAT = None           # call_groq(cfg, messages, image=None, model=None, status=None)
GROQ_WHISPER = None        # call_groq_whisper(path, cfg=None, audio=None, status=None)
GROQ_READY = None          # groq_ready(cfg) -> (bool, why)
LOAD_CONFIG = None         # load_config() -> (cfg, ...)


def configure(chat=None, whisper=None, ready=None, config=None):
    """Wire the Groq client in from the server. Idempotent, and never overwrites with None."""
    global GROQ_CHAT, GROQ_WHISPER, GROQ_READY, LOAD_CONFIG
    if chat is not None:
        GROQ_CHAT = chat
    if whisper is not None:
        GROQ_WHISPER = whisper
    if ready is not None:
        GROQ_READY = ready
    if config is not None:
        LOAD_CONFIG = config


def _cfg():
    if LOAD_CONFIG is None:
        return {}
    try:
        got = LOAD_CONFIG()
        return got[0] if isinstance(got, tuple) else got
    except Exception:                                          # noqa: BLE001
        return {}


# ------------------------------------------------------------------------ the two binaries
#
# NEITHER OF THESE IS EVER MOCKED. The mandate is explicit and it is the right rule: a study
# pipe that silently substitutes a fake downloader proves that the fake works. If a binary is
# missing, tool_report() says which one and every tick fails with that sentence in the ledger.
_TOOLS = {}


def _winget_bin():
    """Where winget puts Gyan.FFmpeg. Not a guess - it is where it put this one."""
    local = os.environ.get("LOCALAPPDATA") or ""
    if not local:
        return []
    base = os.path.join(local, "Microsoft", "WinGet", "Packages")
    out = []
    try:
        for name in os.listdir(base):
            if not name.lower().startswith("gyan.ffmpeg"):
                continue
            pkg = os.path.join(base, name)
            for inner in os.listdir(pkg):
                cand = os.path.join(pkg, inner, "bin")
                if os.path.isdir(cand):
                    out.append(cand)
    except OSError:
        pass
    return out


def _find_exe(stem, extra=()):
    """An absolute path to `stem`, or "". PATH first, then the places installers use.

    Absolute rather than bare, for the reason every other subprocess in this house is
    absolute: a bare name on Windows is resolved against a PATH that a service, a scheduled
    task and an interactive shell do not agree about, and the failure is intermittent.
    """
    if stem in _TOOLS:
        return _TOOLS[stem]
    found = shutil.which(stem) or ""
    if not found:
        for folder in list(extra) + _winget_bin():
            for suffix in (".exe", ""):
                cand = os.path.join(folder, stem + suffix)
                if os.path.isfile(cand):
                    found = cand
                    break
            if found:
                break
    _TOOLS[stem] = found
    return found


def _scripts_dirs():
    """Where pip put yt-dlp.exe: the interpreter's own Scripts folder, and the user one."""
    out = [os.path.join(os.path.dirname(os.path.abspath(sys.executable)), "Scripts"),
           os.path.dirname(os.path.abspath(sys.executable))]
    return [p for p in out if os.path.isdir(p)]


def ffmpeg_exe():
    return _find_exe("ffmpeg")


def ffprobe_exe():
    return _find_exe("ffprobe")


def ytdlp_exe():
    return _find_exe("yt-dlp", _scripts_dirs())


def tool_report():
    """{name: {"found": bool, "path": str, "version": str}} for the three binaries.

    Read by preflight, by tools/study_tick.py and by the lookbook. The version string is
    taken from the binary itself rather than from a package manager, because what matters is
    what will run, not what something was told to install.
    """
    out = {}
    for name, path in (("yt-dlp", ytdlp_exe()), ("ffmpeg", ffmpeg_exe()),
                       ("ffprobe", ffprobe_exe())):
        row = {"found": bool(path), "path": path or "", "version": ""}
        if path:
            try:
                res = _proc.run([path, "--version" if name == "yt-dlp" else "-version"],
                                capture_output=True, text=True, timeout=30)
                first = (res.stdout or res.stderr or "").strip().splitlines()
                row["version"] = (first[0][:80] if first else "")
            except Exception as exc:                           # noqa: BLE001
                row["version"] = "would not answer: %s" % exc
        out[name] = row
    return out


# THE FLAG USED TO BE DECLARED HERE AND IT WAS THE WRONG PLACE FOR IT. This file first
# carried its own `_NO_WINDOW = 0x08000000` and passed it to five subprocess.run calls, which
# kept the employer's desktop clean and still failed check 21 - correctly. The check does not
# ask "is the flag set", it asks "is there one door", because the reason _proc exists is that
# a spawn added next month would flash and nobody would connect the flash to the feature. A
# study tick starts four children (yt-dlp, ffmpeg, ffprobe, build.py) and all four now go
# through _proc.run with no creationflags of their own, so the policy decides, once.


# ------------------------------------------------------------------------------- syllabus

def read_syllabus():
    """The boss's file, coerced into a shape the rotation can trust. Never raises.

    Re-read at the top of every tick rather than cached at boot: the file is his, he edits it
    while the daemon is running, and a cached syllabus would mean a restart is part of the
    interface.
    """
    raw = {}
    try:
        with open(SYLLABUS_PATH, "r", encoding="utf-8") as fh:
            raw = json.load(fh)
    except Exception:                                          # noqa: BLE001
        raw = {}
    topics = []
    for item in (raw.get("topics") or []):
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()[:60]
        if not name:
            continue
        try:
            weight = float(item.get("weight", 1))
        except (TypeError, ValueError):
            weight = 1.0
        queries = [str(q)[:200] for q in (item.get("queries") or []) if str(q).strip()]
        topics.append({"name": name, "weight": max(0.0, weight), "queries": queries,
                       "youtube": str(item.get("youtube") or "").strip()[:300]})
    goals = [str(g)[:200] for g in (raw.get("revenue_goals") or []) if str(g).strip()]
    try:
        budget = float(raw.get("tick_budget_s") or TICK_BUDGET_S)
    except (TypeError, ValueError):
        budget = TICK_BUDGET_S
    try:
        hour = int(raw.get("digest_hour", 18))
    except (TypeError, ValueError):
        hour = 18
    return {"topics": topics, "revenue_goals": goals,
            "tick_budget_s": budget, "digest_hour": max(0, min(23, hour))}


def slug(text):
    out = re.sub(r"[^a-z0-9]+", "-", str(text or "").lower()).strip("-")
    return out or "topic"


def resolve_topic_name(name, syllabus=None):
    """The syllabus's own spelling of `name`, or `name` unchanged if it is not on the syllabus.

    So that the sentence the boss hears is the sentence the ledger will file. Without it he
    said "study micro-saas now", the funnel's addressless form handed the server "micro saas",
    and the butler answered "Studying micro saas now" about a tick that was correctly filed
    under "micro-saas" - a small thing, and exactly the kind of small thing that makes somebody
    wonder whether it understood him.
    """
    want = slug(name)
    for cand in (syllabus or read_syllabus())["topics"]:
        if slug(cand["name"]) == want:
            return cand["name"]
    return str(name)


# --------------------------------------------------------------------------------- state
#
# THE STATE FILE IS THE ROTATION'S MEMORY AND IT HAS TO SURVIVE A RESTART, because the thing
# it prevents is studying finance four times in a row after four crashes.
_STATE_DEFAULT = {"lastStudied": {}, "ticks": 0, "skipped": 0,
                  "lastDigest": "", "lastTickAt": 0.0}


def read_state():
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as fh:
            saved = json.load(fh)
        if not isinstance(saved, dict):
            raise ValueError
    except Exception:                                          # noqa: BLE001
        saved = {}
    out = {}
    for key, default in _STATE_DEFAULT.items():
        value = saved.get(key, default)
        if isinstance(default, dict):
            out[key] = {str(k)[:60]: float(v or 0)
                        for k, v in (value or {}).items()} if isinstance(value, dict) else {}
        elif isinstance(default, str):
            out[key] = str(value or "")[:40]
        elif isinstance(default, float):
            try:
                out[key] = float(value or 0)
            except (TypeError, ValueError):
                out[key] = 0.0
        else:
            try:
                out[key] = int(value or 0)
            except (TypeError, ValueError):
                out[key] = 0
    return out


def _write_state(state):
    """Atomic, and rebuilt from the whitelist rather than dumped - focus.py's rule."""
    clean = {}
    for key, default in _STATE_DEFAULT.items():
        value = state.get(key, default)
        if isinstance(default, dict):
            clean[key] = {str(k)[:60]: float(v or 0)
                          for k, v in (value or {}).items()} if isinstance(value, dict) else {}
        elif isinstance(default, str):
            clean[key] = str(value or "")[:40]
        elif isinstance(default, float):
            clean[key] = float(value or 0)
        else:
            clean[key] = int(value or 0)
    tmp = STATE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(clean, fh, indent=2)
        fh.write("\n")
    os.replace(tmp, STATE_PATH)


def pick_topic(syllabus=None, state=None, now=None):
    """The next topic, by weight AND by neglect. Returns a topic dict or None.

    score = weight x hours since it was last studied, with an unstudied topic scoring as if
    it had been neglected for a week. Two failure modes are being avoided at once, and each
    of them is what you get if you drop half of this expression:

      - weight alone, picked randomly, starves the light topics forever on a long enough run
        and nobody notices because every individual choice looks defensible.
      - neglect alone ignores the weights entirely, which makes the weights decoration.

    Deterministic, so the same state and the same clock give the same answer and the proof can
    assert the rotation instead of observing it.
    """
    syllabus = syllabus or read_syllabus()
    state = state if state is not None else read_state()
    now = now if now is not None else time.time()
    best, best_score = None, -1.0
    for topic in syllabus["topics"]:
        if topic["weight"] <= 0:
            continue
        last = float(state["lastStudied"].get(topic["name"], 0.0))
        idle_h = (now - last) / 3600.0 if last else 168.0
        score = topic["weight"] * max(idle_h, 0.0)
        if score > best_score:
            best, best_score = topic, score
    return best


# -------------------------------------------------------------------------------- ledger
#
# Whitelisted in both directions, like focus.py's: nothing reaches study-ledger.json except
# through _tick_row(), and nothing comes back out except through it either, so a row somebody
# hand-edits into the file is filtered on read exactly as one this module wrote.
TICK_ROW_KEYS = {"at": str, "topic": str, "why": str, "outcome": str, "reason": str,
                 "warn": str,
                 "chunks": int, "chunkBytesMax": int, "retries": int, "four_hundreds": int,
                 "words": int, "sources": int, "note": str,
                 "fetchMs": int, "splitMs": int, "sttMs": int, "thinkMs": int,
                 "guardMs": int, "writeMs": int, "buildMs": int, "totalMs": int,
                 # WAITING IS NOT WORKING, AND THE LEDGER HAS TO BE ABLE TO SAY WHICH IT WAS.
                 # screen() already set verdict["waited"] on a transient refusal and the row
                 # dropped it, so three of this round's ticks read guardMs=20707, 20710 and 20868
                 # - twenty of those seconds being time.sleep() after a 429 - and were
                 # indistinguishable from a guard that genuinely deliberated for twenty seconds.
                 # totalMs is the number the 90s budget is judged against, so the one thing that
                 # dominates it must be legible or the budget cannot be reasoned about at all.
                 "waitedMs": int}

CHUNK_ROW_KEYS = {"at": str, "topic": str, "chunk": int, "of": int, "bytes": int,
                  "seconds": int, "status": int, "ms": int, "words": int, "outcome": str}

_LEDGER_DEFAULT = {"version": 1, "ticks": 0, "kept": 0, "skipped": 0, "failed": 0,
                   "chunkCalls": 0, "fourHundreds": 0, "updated": "",
                   "history": [], "chunks": []}


def _row(raw, keys):
    if not isinstance(raw, dict):
        return None
    out = {}
    for key, kind in keys.items():
        value = raw.get(key)
        if kind is int:
            try:
                out[key] = int(round(float(value or 0)))
            except (TypeError, ValueError):
                out[key] = 0
        else:
            out[key] = ("" if value is None else str(value))[:200]
    return out


def _blank_ledger():
    return {k: ([] if isinstance(v, list) else v) for k, v in _LEDGER_DEFAULT.items()}


def read_ledger():
    try:
        with open(LEDGER_PATH, "r", encoding="utf-8") as fh:
            saved = json.load(fh)
        if not isinstance(saved, dict):
            raise ValueError
    except Exception:                                          # noqa: BLE001
        return _blank_ledger()
    out = _blank_ledger()
    for key, default in _LEDGER_DEFAULT.items():
        value = saved.get(key, default)
        if isinstance(default, list):
            keys = CHUNK_ROW_KEYS if key == "chunks" else TICK_ROW_KEYS
            rows = [_row(item, keys) for item in value] if isinstance(value, list) else []
            out[key] = [r for r in rows if r][-LEDGER_HISTORY_MAX:]
        elif isinstance(value, type(default)):
            out[key] = value
        else:
            out[key] = default
    return out


def _write_ledger(book):
    clean = {}
    for key, default in _LEDGER_DEFAULT.items():
        value = book.get(key, default) if isinstance(book, dict) else default
        if isinstance(default, list):
            keys = CHUNK_ROW_KEYS if key == "chunks" else TICK_ROW_KEYS
            rows = [_row(item, keys) for item in value] if isinstance(value, list) else []
            clean[key] = [r for r in rows if r][-LEDGER_HISTORY_MAX:]
        elif isinstance(value, type(default)):
            clean[key] = value
        else:
            clean[key] = default
    clean["updated"] = time.strftime("%Y-%m-%d %H:%M")
    tmp = LEDGER_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(clean, fh, indent=2)
        fh.write("\n")
    os.replace(tmp, LEDGER_PATH)


def _ledger_tick(row, chunk_rows):
    book = read_ledger()
    book["ticks"] += 1
    outcome = str(row.get("outcome") or "")
    if outcome == "kept":
        book["kept"] += 1
    elif outcome == "skipped":
        book["skipped"] += 1
    else:
        book["failed"] += 1
    book["chunkCalls"] += len(chunk_rows)
    book["fourHundreds"] += int(row.get("four_hundreds") or 0)
    book["history"] = list(book["history"]) + [row]
    book["chunks"] = list(book["chunks"]) + list(chunk_rows)
    _write_ledger(book)


# ------------------------------------------------------------------------- the write guard

def _guarded_write(path, text):
    """Write `text` to `path`, or raise if `path` is not inside STUDY_DIR.

    THE GATE, as a function rather than as a promise. Every note this module writes goes
    through here, so "write-only to its own sandboxed folder" is a property of one line of
    code that can be read in five seconds, instead of a claim about every future edit to this
    file. promote() is the single deliberate exception and it says so in its own docstring.
    """
    target = os.path.abspath(path)
    root = os.path.abspath(STUDY_DIR)
    if os.path.commonpath([target, root]) != root:
        raise ValueError("the Scholar may only write inside %s (asked for %s)" % (root, target))
    os.makedirs(os.path.dirname(target), exist_ok=True)
    with open(target, "w", encoding="utf-8") as fh:
        fh.write(text)
    return target


def _assert_transcribable(audio):
    """The Chunking Law's assertion, at the only place it can be checked: the call site.

    Named as an assertion rather than a check because that is what it is - if this ever
    fires, the splitter above it is broken and the right response is a loud stop, not a
    smaller request.
    """
    if len(audio) > GROQ_HARD_MAX:
        raise AssertionError(
            "a %d byte chunk reached the transcriber and Groq's ceiling is %d - the splitter "
            "is broken, and retrying would only ask a remote service to say so"
            % (len(audio), GROQ_HARD_MAX))
    return True


# --------------------------------------------------------------------------- the pipe: web

def gather_articles(topic, want=3, trace=None):
    """Read-only through the web gate's own door. [{title, url, snippet}], never raises.

    search.search() is the door a conversational question opens, and the Scholar opens the
    same one: it GETs, it carries no credential, and it cannot write. Nothing here re-implements
    a fetcher, because a second web door would be a second thing to audit and the mandate's
    DO-NOT-ALTER names the doors for exactly that reason.
    """
    rows, seen = [], set()
    for query in (topic.get("queries") or [])[:3]:
        try:
            got = websearch.search(query, cfg=_cfg(), trace=trace)
        except Exception as exc:                               # noqa: BLE001
            if trace is not None:
                trace.append("scholar: the web gate declined '%s' (%s)" % (query, exc))
            continue
        for row in (got or {}).get("results", []) if isinstance(got, dict) else (got or []):
            url = str((row or {}).get("url") or "")
            if not url or url in seen:
                continue
            seen.add(url)
            rows.append({"title": str(row.get("title") or "")[:200],
                         "url": url[:400],
                         "snippet": str(row.get("snippet") or "")[:1200]})
            if len(rows) >= want:
                return rows
    return rows


# ------------------------------------------------------------------- the pipe: audio in

def fetch_audio(target, folder, timeout=300):
    """yt-dlp, audio only, into `folder`. (path, url, error).

    `target` is either a watch URL or a phrase; a phrase becomes ytsearch1:. Nothing is
    post-processed here - ffmpeg does the format work in the next stage, in one pass, because
    two transcodes of the same audio is one transcode too many.
    """
    exe = ytdlp_exe()
    if not exe:
        return "", "", ("yt-dlp is not installed on this machine. "
                        "pip install yt-dlp, and nothing here will pretend otherwise.")
    spec = target if re.match(r"^https?://", target) else "ytsearch1:" + target
    out_tmpl = os.path.join(folder, "source.%(ext)s")
    cmd = [exe, "-f", "bestaudio/best", "--no-playlist", "--no-warnings",
           "--print", "after_move:%(webpage_url)s", "-o", out_tmpl, spec]
    try:
        res = _proc.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return "", "", "yt-dlp did not finish inside %ds." % timeout
    except Exception as exc:                                   # noqa: BLE001
        return "", "", "yt-dlp would not run (%s)." % exc
    url = (res.stdout or "").strip().splitlines()
    url = url[-1].strip() if url else ""
    files = [os.path.join(folder, n) for n in sorted(os.listdir(folder))
             if n.startswith("source.")]
    if not files:
        detail = (res.stderr or res.stdout or "").strip().splitlines()
        return "", url, ("yt-dlp downloaded nothing. %s"
                         % (detail[-1][:300] if detail else "no output"))
    return files[0], url, ""


def audio_seconds(path):
    """Duration in seconds from ffprobe, or 0.0. A measurement, never an estimate."""
    exe = ffprobe_exe()
    if not exe or not os.path.exists(path):
        return 0.0
    try:
        res = _proc.run([exe, "-v", "error", "-show_entries", "format=duration",
                         "-of", "default=nw=1:nk=1", path],
                        capture_output=True, text=True, timeout=60)
        return float((res.stdout or "0").strip() or 0.0)
    except Exception:                                          # noqa: BLE001
        return 0.0


def split_audio(path, folder, seconds=CHUNK_SECONDS):
    """ffmpeg -> 16 kHz mono 16-bit WAV segments of `seconds`. (paths, error).

    The format is not a preference. Groq's own documentation says it downsamples to 16 kHz
    mono before transcribing, so sending anything richer is paying upload for something the
    far end throws away - and it is what makes CHUNK_SECONDS arithmetic instead of a guess:
    32 000 bytes a second, so 240 seconds is 7.68 MB, every time, for every input format.
    """
    exe = ffmpeg_exe()
    if not exe:
        return [], ("ffmpeg is not installed on this machine. "
                    "winget install Gyan.FFmpeg, and nothing here will pretend otherwise.")
    out = os.path.join(folder, "chunk%03d.wav")
    cmd = [exe, "-hide_banner", "-loglevel", "error", "-y", "-i", path,
           "-vn", "-ac", "1", "-ar", str(AUDIO_RATE), "-c:a", "pcm_s16le",
           "-f", "segment", "-segment_time", str(int(seconds)),
           "-reset_timestamps", "1", out]
    try:
        res = _proc.run(cmd, capture_output=True, text=True, timeout=900)
    except Exception as exc:                                   # noqa: BLE001
        return [], "ffmpeg would not run (%s)." % exc
    paths = [os.path.join(folder, n) for n in sorted(os.listdir(folder))
             if re.match(r"^chunk\d+\.wav$", n)]
    if not paths:
        detail = (res.stderr or "").strip().splitlines()
        return [], "ffmpeg produced no chunks. %s" % (detail[-1][:300] if detail else "")
    return paths[:MAX_CHUNKS], ""


def _resplit(path, folder, seconds):
    """Re-cut ONE chunk smaller, into its own folder. (paths, error)."""
    sub = os.path.join(folder, "half-%s" % os.path.basename(path).replace(".wav", ""))
    os.makedirs(sub, exist_ok=True)
    return split_audio(path, sub, seconds)


# ------------------------------------------------------------- the pipe: audio -> words

def transcribe(paths, topic_name="", offset_s=0, chunk_rows=None, seconds=CHUNK_SECONDS,
               may_halve=True):
    """Sequential whisper calls, stitched in order with boundary markers.

    Returns (text, stats). stats carries chunks, retries, four_hundreds and the largest
    chunk actually sent, all of which the ledger wants and none of which is guessed.

    ORDER IS THE WHOLE POINT and it is why this is a plain for-loop over a sorted list rather
    than anything concurrent. Four transcripts that arrive out of order and get stitched by
    completion time produce a document that reads like a transcript and lies about the
    sequence of an argument - which is worse than a missing chunk, because a missing chunk is
    visible in the marker numbering and a reordered one is not.

    `may_halve` IS THE MANDATE'S WORD "ONCE", MADE STRUCTURAL, and it is here because the first
    version did not have it and was not bounded. The 400 rule halves the chunk and calls this
    function again on the halves; each of those halves is then a chunk that may 400 and halve
    itself. Below CHUNK_FLOOR_S the size stops shrinking - max(30, 30 // 2) is 30 - so a
    PERSISTENT 400, which is what a corrupt or mislabelled file produces, recursed until Python's
    own recursion limit stopped it, spending one Groq request and one ffmpeg run per level. The
    allowance is passed False on the recursive call, so a chunk is halved at most once and a 400
    with no allowance left is recorded in its row and left alone. Depth is now two, by
    construction rather than by hoping a 400 is transient.
    """
    chunk_rows = chunk_rows if chunk_rows is not None else []
    pieces, stats = [], {"chunks": 0, "retries": 0, "four_hundreds": 0, "maxBytes": 0}
    at = time.strftime("%Y-%m-%d %H:%M")
    total = len(paths)
    for i, path in enumerate(paths, 1):
        # A ROW PER CHUNK MEANS PER CHUNK ACTUALLY SENT, halves included. The halving recursion
        # keeps its own rows, and they are carried back up in `sub` and filed immediately after
        # the row of the chunk that produced them - so the ledger reads "chunk 2 of 4: 400 then
        # halved into 2", then the two halves, in the order they went. Dropped, they made the
        # only honest answer to "what did the 400 cost me" unavailable.
        sub = []
        text, row = _one_chunk(path, i, total, topic_name, at, offset_s, seconds, stats,
                               may_halve, sub)
        chunk_rows.append(row)
        chunk_rows.extend(sub)
        start = offset_s + (i - 1) * seconds
        pieces.append("[chunk %d/%d @ %d:%02d]\n%s"
                      % (i, total, start // 60, start % 60, text.strip()))
        stats["chunks"] += 1
    return "\n\n".join(pieces).strip(), stats


def _one_chunk(path, i, total, topic_name, at, offset_s, seconds, stats, may_halve=True,
               sub_rows=None):
    """One chunk, with the 400 rule. (text, ledger row).

    THE 400 RULE, and why it is one retry and not a loop: a 400 from a transcriber that has
    already accepted three chunks of the same encoding is a statement about this chunk's size
    or shape. Halving it once tests that theory for the price of one extra call. Halving it
    repeatedly tests nothing and spends a request per attempt, and the log it leaves behind is
    indistinguishable from a rate limit.

    `may_halve` is false on the halves themselves - see transcribe(), where the bound is
    explained - so "once" is a fact about the call graph and not an expectation about the 400.
    """
    audio = b""
    try:
        with open(path, "rb") as fh:
            audio = fh.read()
    except OSError as exc:
        return "", _row({"at": at, "topic": topic_name, "chunk": i, "of": total,
                         "outcome": "unreadable: %s" % exc}, CHUNK_ROW_KEYS)
    _assert_transcribable(audio)
    stats["maxBytes"] = max(stats["maxBytes"], len(audio))
    status = {}
    t0 = time.perf_counter()
    text, err = (GROQ_WHISPER(path, cfg=_cfg(), audio=audio, status=status)
                 if GROQ_WHISPER else (None, "there is no transcriber wired up"))
    ms = int((time.perf_counter() - t0) * 1000)
    code = int(status.get("code") or 0)
    outcome = "ok" if not err else ("http %d" % code if code else "error")
    if code == 400 and not may_halve:
        # THE ALLOWANCE IS SPENT. This chunk is already a half, and halving a half that still
        # 400s is not a second theory about the size - it is the same theory, asked again at a
        # price of one request and one ffmpeg run. The row says so and the tick carries on with
        # whatever the other chunks gave it.
        stats["four_hundreds"] += 1
        outcome = "400 and the one halving was already spent"
    elif code == 400:
        stats["four_hundreds"] += 1
        stats["retries"] += 1
        halved = max(CHUNK_FLOOR_S, int(seconds // 2))
        halves, split_err = _resplit(path, os.path.dirname(path), halved)
        if not split_err and halves:
            outcome = "400 then halved into %d" % len(halves)
            got, sub = transcribe(halves, topic_name, offset_s + (i - 1) * seconds,
                                  chunk_rows=(sub_rows if sub_rows is not None else None),
                                  seconds=halved, may_halve=False)
            stats["maxBytes"] = max(stats["maxBytes"], sub["maxBytes"])
            stats["four_hundreds"] += sub["four_hundreds"]
            text, err = got, ""
        else:
            outcome = "400 and the halving failed: %s" % (split_err or "no halves")
    row = _row({"at": at, "topic": topic_name, "chunk": i, "of": total,
                "bytes": len(audio), "seconds": int(len(audio) / AUDIO_BYTES_PER_S),
                "status": code, "ms": ms, "words": len((text or "").split()),
                "outcome": outcome if not err else (outcome + ": " + err[:120])},
               CHUNK_ROW_KEYS)
    return (text or ""), row


# --------------------------------------------------------------------- the pipe: thinking

THINK_PROMPT = (
    "You are a research assistant reading one source for a busy founder. His revenue goals "
    "are:\n{goals}\n\nThe topic is: {topic}\n\nReturn EXACTLY three bullets of core insight, "
    "each one sentence, each one thing he could act on or that changes how he would decide. "
    "No preamble, no summary, no restating the question, no flattery, no closing line. Every "
    "bullet must be supported by the material below; if the material does not support three, "
    "write fewer and say nothing else. Start each bullet with '- '."
)


def evidence_blob(articles, transcript):
    """THE ONE EVIDENCE STRING, built once and read by both the author and the guard.

    It is a function rather than two similar loops because the two loops drifted, and the drift
    was invisible: the thinker's version carried 12 000 characters of transcript and the guard's
    carried 4 000 of an 8 000-character budget that four article snippets had already half filled.
    The guard then refused real work for being ungrounded in evidence it had not been shown - which
    is the failure mode of every asymmetric checker, and it fails closed, so it looks like
    diligence. Now there is nothing to keep in step: the same bytes go to both calls.

    THE PAYLOAD IS CAPPED FOR A MEASURED REASON, NOT A TIDY ONE. The first draft sent 24 000
    characters of transcript and 28 000 in total, and the tick after it earned a 429: one study
    spent most of the free tier's tokens-per-minute window, so the Poison Guard's own call - which
    comes second, by design - was the one refused. Three bullets do not improve with forty minutes
    of transcript, and a guard that cannot afford to run is worse than a shorter prompt.
    """
    # .get, NOT [ ]. The guard's old loop read only title and snippet, so a fixture handed to
    # --inject or to a harness could legally carry no url at all; sharing the thinker's loop made
    # the missing key a KeyError INSIDE the guard, which is a crashed tick rather than a refused
    # one. Caught by preflight's own stub articles the first time this ran.
    parts = []
    for art in (articles or []):
        parts.append("ARTICLE: %s\n%s\n(%s)"
                     % (art.get("title") or "", art.get("snippet") or "",
                        art.get("url") or "no url given"))
    if transcript:
        parts.append("TRANSCRIPT:\n" + transcript[:THINK_TRANSCRIPT_CHARS])
    return "\n\n".join(parts)[:THINK_CHARS]


def think(topic, transcript, articles, cfg=None):
    """Three bullets, from the evidence. (bullets list, model, error)."""
    if GROQ_CHAT is None:
        return [], "", "there is no chat model wired up"
    cfg = cfg if cfg is not None else _cfg()
    syl = read_syllabus()
    goals = "\n".join("- " + g for g in syl["revenue_goals"]) or "- (none stated)"
    evidence = evidence_blob(articles, transcript)
    if not evidence:
        return [], "", "there was nothing to read"
    messages = [
        {"role": "system", "content": THINK_PROMPT.format(goals=goals, topic=topic["name"])},
        {"role": "user", "content": evidence},
    ]
    answer, err = GROQ_CHAT(cfg, messages)
    if err or not answer:
        return [], "", err or "the model said nothing"
    bullets = [re.sub(r"^\s*[-*•]\s*", "", ln).strip()
               for ln in str(answer).splitlines() if re.match(r"^\s*[-*•]\s+", ln)]
    bullets = [b for b in bullets if len(b) > 12][:3]
    model = str((cfg or {}).get("groq_model") or "")
    if not bullets:
        return [], model, "the model wrote no bullets"
    return bullets, model, ""


# ------------------------------------------------------------------- the Poison Guard

GUARD_JSON_PROMPT = (
    "You are a screening step, not an author. Decide two things about the CANDIDATE bullets "
    "against the EVIDENCE and the SYLLABUS TOPIC.\n"
    "grounded: is every bullet supported by the evidence, with no invented number, name, "
    "date or citation?\n"
    "on_topic: does every bullet belong to the stated topic?\n"
    "Answer with one line of JSON and nothing else: "
    "{\"grounded\": true|false, \"on_topic\": true|false, \"why\": \"<12 words>\"}"
)


def screen(bullets, topic, transcript, articles, cfg=None):
    """The Poison Guard. (verdict dict) - and it FAILS CLOSED.

    verdict = {"ok": bool, "toxic": bool, "grounded": bool, "onTopic": bool,
               "why": str, "safety": str, "limbs": int,
               "transient": bool,        # the road failed - a 429, an unreachable host
               "unjudged": bool}         # no verdict came back, for any reason at all

    THE LAST TWO ARE FOR THE LEDGER AND NOT FOR THE DECISION. Every path out of here that is not
    an explicit pass is a veto, and the caller writes nothing either way; what these two decide is
    whether the row says `skipped` - the Scholar tried to write something poisonous - or `failed` -
    the screening never happened. A malfunction counted as poison makes the one number that is
    supposed to mean poison mean nothing.

    Two limbs, because the mandate asks one screening to answer three questions and no single
    model answers all three. A safety model classifies harm; it has no view on whether a
    sentence was invented. So SAFETY_MODEL - gpt-oss-safeguard-20b, enforcing SAFETY_POLICY,
    standing in for the decommissioned guard §28 reserved - decides toxic, and a strict-JSON
    verdict from the ordinary chat model decides grounded and on-topic against the evidence the
    bullets came from.

    FAILING CLOSED IS THE WHOLE CONTRACT. A guard that lets a bullet through because the
    screening call timed out is not a guard, it is a latency-dependent guard, and the day it
    matters is the day the network is slow. Every path that does not end in an explicit
    "this is fine" ends in ok=False.
    """
    cfg = cfg if cfg is not None else _cfg()
    verdict = {"ok": False, "toxic": True, "grounded": False, "onTopic": False,
               "why": "the guard did not run", "safety": "", "limbs": 0,
               "transient": False, "unjudged": True, "waited": 0.0}
    # `unjudged` STARTS TRUE AND IS CLEARED BY A JUDGEMENT, NOT SET BY A FAILURE. Written this way
    # round because the other way round is a list of failure paths, and the list is what goes
    # stale: a branch added next month would return with unjudged still false and its malfunction
    # would be filed as poison, which is the exact bug this field exists to have fixed. Here, a
    # new early return is unjudged for free and only an actual verdict says otherwise.
    if not bullets:
        verdict["why"] = "there was nothing to screen"
        return verdict
    if GROQ_CHAT is None:
        verdict["why"] = "there is no screening model wired up"
        return verdict
    body = "\n".join("- " + b for b in bullets)

    # ---- limb one: the safety model, against SAFETY_POLICY. One word: VIOLATION or ALLOW.
    #
    # ANYTHING THAT IS NOT THE WORD "ALLOW" IS A VETO, including a third word nobody
    # anticipated. The alternative - treating only the literal word "VIOLATION" as a refusal -
    # means a model that changes its output format one day starts approving everything, and
    # the change is invisible because approvals are the quiet path.
    safe_status = {}
    safe_answer, safe_err = GROQ_CHAT(
        cfg, [{"role": "system", "content": SAFETY_POLICY},
              {"role": "user", "content": body}], model=SAFETY_MODEL, status=safe_status)
    if safe_err or not safe_answer:
        verdict["transient"] = bool(safe_status.get("transient"))
        verdict["why"] = "the safety model would not answer: %s" % (safe_err or "empty")[:120]
        return verdict
    said = str(safe_answer).strip()
    verdict["safety"] = said[:80]
    verdict["limbs"] = 1
    first = said.splitlines()[0].strip().upper()
    if not first.startswith("ALLOW"):
        verdict["toxic"] = True
        verdict["unjudged"] = False        # a word that is not ALLOW IS a judgement, and poison
        verdict["why"] = "the safety model flagged it: %s" % said[:80].replace("\n", " ")
        return verdict
    verdict["toxic"] = False

    # ---- limb two: grounded and on-topic, against the evidence, as strict JSON.
    # THE SAME BYTES THE AUTHOR WAS GIVEN, from the same function. GUARD_EVIDENCE_CHARS and
    # GUARD_TRANSCRIPT_CHARS are now defined as the thinker's own budgets, so the slice below is
    # the slice above and the guard cannot refuse a bullet for grounds it was not shown.
    evidence = evidence_blob(articles, transcript)[:GUARD_EVIDENCE_CHARS]
    ask = [{"role": "system", "content": GUARD_JSON_PROMPT},
           {"role": "user", "content": "SYLLABUS TOPIC: %s\n\nCANDIDATE:\n%s\n\nEVIDENCE:\n%s"
                                       % (topic["name"], body, evidence)}]
    status = {}
    answer, err = GROQ_CHAT(cfg, ask, status=status)
    if (err or not answer) and status.get("transient"):
        # ONE WAIT, AND ONLY FOR A ROAD RATHER THAN A DECISION. call_groq() already separates
        # the two: 429 and an unreachable host are transient, a 401 and a retired model id are
        # not. Waiting out a tokens-per-minute window costs twenty seconds and saves the whole
        # tick's work; waiting after a 401 would only ask a remote service to repeat itself.
        time.sleep(GUARD_RETRY_S)
        status = {}
        answer, err = GROQ_CHAT(cfg, ask, status=status)
        verdict["waited"] = GUARD_RETRY_S     # recorded, because it is most of the budget
    if err or not answer:
        verdict["transient"] = bool(status.get("transient"))
        verdict["why"] = "the grounding screen would not answer: %s" % (err or "empty")[:120]
        return verdict
    verdict["limbs"] = 2
    match = re.search(r"\{.*\}", str(answer), re.DOTALL)
    if not match:
        verdict["why"] = "the grounding screen did not answer in JSON"
        return verdict
    try:
        got = json.loads(match.group(0))
    except Exception:                                          # noqa: BLE001
        verdict["why"] = "the grounding screen's JSON would not parse"
        return verdict
    verdict["unjudged"] = False            # the guard rendered a verdict; what follows is it
    verdict["grounded"] = bool(got.get("grounded"))
    verdict["onTopic"] = bool(got.get("on_topic"))
    verdict["why"] = str(got.get("why") or "")[:120]
    verdict["ok"] = verdict["grounded"] and verdict["onTopic"] and not verdict["toxic"]
    if not verdict["ok"] and not verdict["why"]:
        verdict["why"] = "not grounded" if not verdict["grounded"] else "off syllabus"
    return verdict


# ------------------------------------------------------------------ the pipe: remembering

def note_name(topic_name, when=None):
    when = when or time.localtime()
    return "%s-%s.md" % (time.strftime("%Y-%m-%d-%H", when), slug(topic_name))


def write_note(topic, bullets, sources, model, chunks, duration_s, when=None):
    """The note, with its provenance in the front matter. Returns the absolute path.

    The front matter is the mandate's list and it is not decoration: a study note with no
    provenance is indistinguishable from something the boss wrote himself, and the one thing
    this corpus must never do is launder a model's guess into his own words.
    """
    when = when or time.localtime()
    lines = ["---",
             "topic: %s" % topic["name"],
             "sources:"]
    for src in sources:
        lines.append("  - %s" % str(src)[:300])
    lines += ["fetched-at: %s" % time.strftime("%Y-%m-%dT%H:%M:%S", when),
              "model: %s" % (model or "unknown"),
              "chunk-count: %d" % int(chunks),
              "safety-screened: true",
              "loop-seconds: %.3f" % float(duration_s),
              "written-by: scholar.py",
              "---",
              "",
              "# %s - auto-studied" % topic["name"].title(),
              ""]
    for bullet in bullets:
        lines.append("- %s" % bullet)
    lines += ["",
              "## Sources", ""]
    for src in sources:
        lines.append("- %s" % str(src)[:300])
    lines.append("")
    return _guarded_write(os.path.join(STUDY_DIR, note_name(topic["name"], when)),
                          "\n".join(lines))


def run_build(timeout=300):
    """build.py in a subprocess, so the galaxy gains the node. (ms, error).

    A SUBPROCESS AND NOT AN IMPORT, and that is the Async Law rather than a preference:
    build.main() in this thread would rewrite notes-index.json while a conversational turn
    was reading it, and would do it inside this process's own import of the module the
    server also uses. A subprocess cannot touch this process's memory at all, so the
    handshake is reduced to one file's mtime - which is exactly the coupling the async law
    asks for.
    """
    py = sys.executable or "python"
    t0 = time.perf_counter()
    try:
        res = _proc.run([py, BUILD_PY], cwd=ROOT, capture_output=True, text=True,
                        timeout=timeout)
    except Exception as exc:                                   # noqa: BLE001
        return int((time.perf_counter() - t0) * 1000), "build.py would not run (%s)" % exc
    ms = int((time.perf_counter() - t0) * 1000)
    if res.returncode != 0:
        tail = (res.stderr or res.stdout or "").strip().splitlines()
        return ms, "build.py exited %d: %s" % (res.returncode,
                                               tail[-1][:200] if tail else "")
    return ms, ""


# ------------------------------------------------------------------------------- the tick

def tick(topic_name=None, why="daemon", url=None, audio_path=None, on_state=None,
         do_build=True, inject_articles=None, inject_bullets=None):
    """One study tick, start to finish. Returns a result dict; never raises.

    `audio_path` bypasses yt-dlp with a file already on disk, which is how the proof feeds it
    a synthetic fixture over 25 MB without asking YouTube for one. `url` overrides the
    syllabus's own target. Everything else comes from the syllabus.

    THE TWO INJECTION DOORS, AND WHY THEY ARE HERE RATHER THAN IN THE PROOF.
    inject_articles replaces what the web gate returned; inject_bullets replaces what the
    thinking model wrote. Both exist for the Poison Test, and neither weakens the guard,
    because the guard still makes its real calls against whatever came through them.

    The reason the poison has to enter at the bullets is worth stating plainly: the only way
    to test the guard through think() is to persuade a safety-trained chat model to WRITE
    toxic bullets, and when it declines - which it usually does, correctly - the tick ends
    "failed: no bullets" and the guard is never reached. That test passes while proving
    nothing about the thing it is named after. Injecting at the bullets puts the poison
    exactly where the guard is pointed, and the guard's verdict is still the real model's.

    on_state(dict) is called at each stage so the seal can say what is happening. It is a
    callback rather than a shared object for the reason the async law is here at all: the
    caller decides what to do with it, and this function owns no state the server can read
    while it is mid-write.
    """
    t_all = time.perf_counter()
    syl = read_syllabus()
    state = read_state()
    topic = None
    if topic_name:
        # MATCHED ON THE SLUG, NOT ON THE STRING, because the name arriving here has usually
        # been through the funnel's addressless form, which strips punctuation: "study
        # micro-saas now" reaches this function as "micro saas", which is not equal to the
        # syllabus row "micro-saas". Compared literally it missed, and the miss was silent and
        # expensive - the branch below invented a one-off topic with no queries and no youtube
        # target, so a spoken request for a syllabus topic studied something thinner than the
        # same request typed, and the ledger row looked perfectly normal.
        want = slug(topic_name)
        for cand in syl["topics"]:
            if slug(cand["name"]) == want:
                topic = cand
        if topic is None:
            topic = {"name": str(topic_name)[:60], "weight": 1.0, "queries":
                     [str(topic_name)[:200]], "youtube": str(topic_name)[:200]}
    else:
        topic = pick_topic(syl, state)
    if topic is None:
        return {"ok": False, "outcome": "failed", "reason": "the syllabus has no live topic",
                "topic": "", "totalMs": int((time.perf_counter() - t_all) * 1000)}

    say = on_state or (lambda _d: None)
    say({"stage": "gathering", "topic": topic["name"]})
    # reason explains the OUTCOME. warn collects everything that went wrong without deciding
    # it - a 403 from YouTube on a tick that still read three articles and wrote a good note is
    # a warning, and putting it in `reason` produced a ledger row reading "kept - yt-dlp
    # downloaded nothing", which is two true halves making one false sentence.
    result = {"ok": False, "topic": topic["name"], "why": why, "outcome": "failed",
              "reason": "", "warn": "", "bullets": [], "sources": [], "note": "", "chunks": 0,
              "chunkBytesMax": 0, "retries": 0, "four_hundreds": 0, "words": 0,
              "fetchMs": 0, "splitMs": 0, "sttMs": 0, "thinkMs": 0, "guardMs": 0,
              "writeMs": 0, "buildMs": 0, "totalMs": 0, "transcript": "", "deleted": "",
              "guard": {}, "budgetS": syl["tick_budget_s"]}
    chunk_rows = []
    folder = tempfile.mkdtemp(prefix="scholar-")
    try:
        # ---- 1. articles, read-only, through the gate's own door
        t0 = time.perf_counter()
        if inject_articles is not None:
            articles = [{"title": str(a.get("title") or "")[:200],
                         "url": str(a.get("url") or "")[:400],
                         "snippet": str(a.get("snippet") or "")[:1200]}
                        for a in inject_articles]
            result["why"] = why + "+injected-articles"
        else:
            articles = gather_articles(topic)
        result["sources"] = [a["url"] for a in articles]

        # ---- 2. the talk
        target = url or topic.get("youtube") or ""
        media, media_url, fetch_err = ("", "", "")
        if audio_path:
            media, media_url = audio_path, "file://" + os.path.basename(audio_path)
        elif target:
            say({"stage": "fetching", "topic": topic["name"]})
            media, media_url, fetch_err = fetch_audio(target, folder)
        result["fetchMs"] = int((time.perf_counter() - t0) * 1000)
        if media_url:
            result["sources"].append(media_url)
        if fetch_err:
            result["warn"] = _add(result["warn"], fetch_err)

        # ---- 3. the Chunking Law
        transcript = ""
        if media and os.path.exists(media):
            say({"stage": "splitting", "topic": topic["name"]})
            t0 = time.perf_counter()
            chunks, split_err = split_audio(media, folder)
            result["splitMs"] = int((time.perf_counter() - t0) * 1000)
            if split_err:
                result["warn"] = _add(result["warn"], split_err)
            else:
                say({"stage": "transcribing", "topic": topic["name"],
                     "chunks": len(chunks)})
                t0 = time.perf_counter()
                transcript, stats = transcribe(chunks, topic["name"],
                                               chunk_rows=chunk_rows)
                result["sttMs"] = int((time.perf_counter() - t0) * 1000)
                result.update({"chunks": stats["chunks"], "retries": stats["retries"],
                               "four_hundreds": stats["four_hundreds"],
                               "chunkBytesMax": stats["maxBytes"]})
        result["transcript"] = transcript

        if not transcript and not articles:
            result["outcome"] = "failed"
            result["reason"] = result["warn"] or "nothing was gathered to read"
            return _finish(result, chunk_rows, state, topic, t_all, say)

        # ---- 4. three bullets
        say({"stage": "thinking", "topic": topic["name"]})
        t0 = time.perf_counter()
        if inject_bullets is not None:
            bullets = [str(b)[:600] for b in inject_bullets if str(b).strip()][:3]
            model, think_err = "injected", ""
            result["why"] = result["why"] + "+injected-bullets"
        else:
            bullets, model, think_err = think(topic, transcript, articles)
        result["thinkMs"] = int((time.perf_counter() - t0) * 1000)
        if think_err or not bullets:
            result["outcome"] = "failed"
            result["reason"] = think_err or "no bullets"
            return _finish(result, chunk_rows, state, topic, t_all, say)
        result["bullets"] = bullets
        result["words"] = sum(len(b.split()) for b in bullets)

        # ---- 5. the Poison Guard, before the note exists anywhere it could be read
        say({"stage": "screening", "topic": topic["name"]})
        t0 = time.perf_counter()
        guard = screen(bullets, topic, transcript, articles)
        result["guardMs"] = int((time.perf_counter() - t0) * 1000)
        result["guard"] = guard
        if not guard["ok"]:
            # SKIPPED MEANS THE GUARD JUDGED IT. FAILED MEANS THE GUARD COULD NOT BE ASKED.
            # Both write no note, so the corpus cannot tell them apart - but the ledger must,
            # because `skipped` is the number that answers "how often does my Scholar try to
            # write something poisonous", and a rate limit counted there would inflate it with
            # events that say nothing at all about the content. The first draft of this
            # function conflated them and a 429 was filed as poison; that is the bug this
            # branch exists to have fixed.
            #
            # AND A MODEL THAT ANSWERS WITH NOTHING IS NOT A JUDGEMENT EITHER. Measured, in the
            # ledger, on 2026-09-29 at 16:12: `poison guard: the safety model would not answer:
            # Groq returned an empty answer` filed as SKIPPED. The road was fine - a 200 came
            # back - so `transient` was false, and a malfunction was counted as poison in the one
            # number that is supposed to mean poison. screen() now says `unjudged` whenever it
            # returns without a verdict, for either limb, and this branch reads both. Nothing
            # about failing closed changes: ok is still false, no note is still written, and the
            # note standing at this destination is still deleted. Only the WORD in the ledger
            # changes, and the word is the whole point of the row.
            unasked = bool(guard.get("transient") or guard.get("unjudged"))
            result["outcome"] = "failed" if unasked else "skipped"
            if guard.get("transient"):
                result["reason"] = "the guard could not be asked: %s" % guard["why"]
            elif guard.get("unjudged"):
                # ASKED, AND NO VERDICT CAME BACK. An empty completion or a model that would not
                # answer in JSON lands here, and the sentence says which so the row is readable a
                # month later without the code beside it.
                result["reason"] = "the guard returned no judgement: %s" % guard["why"]
            else:
                result["reason"] = "poison guard: %s" % guard["why"]
            # THE GUARD RUNS BEFORE THE NOTE EXISTS, WHICH IS STRICTER THAN THE MANDATE ASKED
            # FOR. "The note is deleted" would also be satisfied by writing it and removing
            # it a second later, and that version has a real hole: build.py is a subprocess
            # that can be started by the other half of this tick or by a hand at a terminal,
            # and a flagged note sitting in notes/study/auto/ for even a millisecond is a note
            # something could index. So nothing poisoned is ever written at all.
            #
            # What IS deleted here is any note already standing at this tick's own
            # destination - the same hour, the same topic - because a clean note from an
            # earlier tick in this hour would otherwise be left representing a tick that was
            # just refused, and the ledger would say skipped while the corpus said kept.
            doomed = os.path.join(STUDY_DIR, note_name(topic["name"]))
            result["deleted"] = ""
            if os.path.exists(doomed):
                os.remove(doomed)
                result["deleted"] = os.path.relpath(doomed, ROOT).replace("\\", "/")
            result["note"] = ""
            return _finish(result, chunk_rows, state, topic, t_all, say)

        # ---- 6. remember
        say({"stage": "writing", "topic": topic["name"]})
        t0 = time.perf_counter()
        elapsed = time.perf_counter() - t_all
        path = write_note(topic, bullets, result["sources"], model,
                          result["chunks"], elapsed)
        result["writeMs"] = int((time.perf_counter() - t0) * 1000)
        result["note"] = os.path.relpath(path, ROOT).replace("\\", "/")

        # ---- 7. the galaxy gains the node
        if do_build:
            say({"stage": "building", "topic": topic["name"]})
            result["buildMs"], build_err = run_build()
            if build_err:
                result["warn"] = _add(result["warn"], build_err)
        result["ok"] = True
        result["outcome"] = "kept"
        return _finish(result, chunk_rows, state, topic, t_all, say)
    except Exception as exc:                                   # noqa: BLE001
        result["outcome"] = "failed"
        result["reason"] = "the tick threw: %s" % exc
        return _finish(result, chunk_rows, state, topic, t_all, say)
    finally:
        shutil.rmtree(folder, ignore_errors=True)


def _add(existing, line):
    """Append one warning to a warning field without losing the one already there."""
    line = str(line or "").strip()
    if not line:
        return existing
    return (existing + " | " + line).strip(" |") if existing else line


def _finish(result, chunk_rows, state, topic, t_all, say):
    result["totalMs"] = int((time.perf_counter() - t_all) * 1000)
    result["overBudget"] = result["totalMs"] > float(result.get("budgetS") or
                                                     TICK_BUDGET_S) * 1000.0
    row = _row({"at": time.strftime("%Y-%m-%d %H:%M"), "topic": result["topic"],
                "why": result["why"], "outcome": result["outcome"],
                "reason": result["reason"], "warn": result["warn"],
                "chunks": result["chunks"],
                "chunkBytesMax": result["chunkBytesMax"], "retries": result["retries"],
                "four_hundreds": result["four_hundreds"], "words": result["words"],
                "sources": len(result["sources"]), "note": result["note"],
                "fetchMs": result["fetchMs"], "splitMs": result["splitMs"],
                "sttMs": result["sttMs"], "thinkMs": result["thinkMs"],
                "guardMs": result["guardMs"], "writeMs": result["writeMs"],
                "buildMs": result["buildMs"], "totalMs": result["totalMs"],
                "waitedMs": int(float((result.get("guard") or {}).get("waited") or 0) * 1000)},
               TICK_ROW_KEYS)
    try:
        _ledger_tick(row, chunk_rows)
        state["ticks"] = int(state.get("ticks") or 0) + 1
        if result["outcome"] == "skipped":
            state["skipped"] = int(state.get("skipped") or 0) + 1
        state["lastStudied"][topic["name"]] = time.time()
        state["lastTickAt"] = time.time()
        _write_state(state)
    except Exception as exc:                                   # noqa: BLE001
        result["warn"] = _add(result["warn"], "ledger: %s" % exc)
    say({"stage": "", "topic": "", "last": result["outcome"]})
    return result


# ------------------------------------------------------------------------------ the digest

DIGEST_LINE = ("I studied %s today, %s - keep them, prune them, or promote the best into "
               "your notes?")


def studied_today(when=None):
    """[{file, topic, title}] for every auto note written today. A read, never a write."""
    when = when or time.localtime()
    prefix = time.strftime("%Y-%m-%d", when)
    out = []
    try:
        names = sorted(os.listdir(STUDY_DIR))
    except OSError:
        return out
    for name in names:
        if not name.startswith(prefix) or not name.endswith(".md"):
            continue
        path = os.path.join(STUDY_DIR, name)
        topic, title = "", name[:-3]
        try:
            with open(path, "r", encoding="utf-8") as fh:
                for line in fh.read(2000).splitlines():
                    if line.startswith("topic: "):
                        topic = line[7:].strip()
                    elif line.startswith("# "):
                        title = line[2:].strip()
                        break
        except OSError:
            pass
        out.append({"file": "notes/study/auto/" + name, "topic": topic, "title": title})
    return out[:DIGEST_MAX]


def _count_word(n):
    words = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six",
             7: "seven", 8: "eight", 9: "nine", 10: "ten", 11: "eleven", 12: "twelve"}
    return words.get(int(n), str(int(n)))


def digest(boss_call="sir", when=None):
    """{due, line, notes}. Once a day, after the syllabus's hour, and never twice.

    "Once daily" is kept in the state file rather than in memory, because a process that
    restarts at 18:05 would otherwise offer the digest again at 18:06, and a butler who asks
    the same question twice in a minute is a butler nobody answers.
    """
    syl = read_syllabus()
    state = read_state()
    when = when or time.localtime()
    today = time.strftime("%Y-%m-%d", when)
    notes = studied_today(when)
    due = bool(notes) and when.tm_hour >= syl["digest_hour"] \
        and state.get("lastDigest") != today
    return {"due": due, "notes": notes, "today": today,
            "line": DIGEST_LINE % (_count_word(len(notes)) + " thing"
                                   + ("s" if len(notes) != 1 else ""), boss_call),
            "offeredToday": state.get("lastDigest") == today}


def mark_digest(when=None):
    state = read_state()
    state["lastDigest"] = time.strftime("%Y-%m-%d", when or time.localtime())
    _write_state(state)


def prune(rel_path):
    """Delete one auto note and the index row that points at it. (ok, said).

    The index row goes because build.py is re-run, which is the only writer of
    notes-index.json in this house - deleting a row by hand would leave the vector store
    holding a chunk for a file that no longer exists, and the chip would cite a missing file.
    """
    rel = str(rel_path or "").replace("\\", "/")
    if not rel.startswith("notes/study/auto/") or ".." in rel:
        return False, "That is not one of my study notes, sir."
    path = os.path.join(ROOT, rel.replace("/", os.sep))
    if not os.path.exists(path):
        return False, "That one is already gone, sir."
    os.remove(path)
    _, err = run_build()
    return True, ("Pruned, sir." if not err else "Pruned, sir - the rebuild said: %s" % err)


def promote(rel_path, folder="personal"):
    """THE ONLY PATH OUT OF THE SANDBOX, and it is not reachable without a gated yes.

    _guarded_write() refuses everything outside STUDY_DIR by design, so this function does
    its own write - deliberately, visibly, and in one place that can be read in full. The
    gate is the server's: it raises a confirmation, the boss's own voice or keyboard answers
    it, and only then is this called. Nothing in scholar.py can call it.
    """
    rel = str(rel_path or "").replace("\\", "/")
    if not rel.startswith("notes/study/auto/") or ".." in rel:
        return False, "That is not one of my study notes, sir.", ""
    src = os.path.join(ROOT, rel.replace("/", os.sep))
    if not os.path.exists(src):
        return False, "That one is gone, sir.", ""
    safe = re.sub(r"[^a-z0-9\-]+", "", str(folder or "personal").lower()) or "personal"
    dest_dir = os.path.join(ROOT, "notes", safe)
    os.makedirs(dest_dir, exist_ok=True)
    dest = os.path.join(dest_dir, os.path.basename(src))
    with open(src, "r", encoding="utf-8") as fh:
        text = fh.read()
    text = text.replace("written-by: scholar.py",
                        "written-by: scholar.py\npromoted-at: %s"
                        % time.strftime("%Y-%m-%dT%H:%M:%S"), 1)
    with open(dest, "w", encoding="utf-8") as fh:
        fh.write(text)
    os.remove(src)
    _, err = run_build()
    rel_dest = os.path.relpath(dest, ROOT).replace("\\", "/")
    return True, ("Promoted into %s, sir." % rel_dest if not err
                  else "Promoted, sir - the rebuild said: %s" % err), rel_dest


# ------------------------------------------------------------------------------ the daemon

PUBLIC_KEYS = ("studying", "topic", "stage", "since", "ticks", "kept", "skipped",
               "failed", "lastOutcome", "lastMs", "budgetS", "queued", "tools")


class Scholar:
    """The loop, on its own thread, with its own lock and nobody else's.

    THE LOCK IN HERE GUARDS THIS OBJECT'S OWN FOUR FIELDS AND NOTHING ELSE. It is never held
    across a network call, a subprocess or a file write - state() takes it for microseconds to
    copy four values out. The conversational path's locks (server._lock for the index and the
    histories, server._brain_lock, server._SPEAKER_LOCK) are not imported here, not named
    here, and cannot be reached from here, which is the async law stated as a fact about the
    import graph rather than as an intention.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._thread = None
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._req = None           # {"topic": str, "why": str, "url": str, "audio": str}
        self._live = {"studying": False, "topic": "", "stage": "", "since": 0.0}
        self._last = {"outcome": "", "ms": 0}
        self.enabled = True

    # ---- the public reader, and the ONLY thing the browser is ever told
    def state(self):
        with self._lock:
            live = dict(self._live)
            last = dict(self._last)
            queued = bool(self._req)
        led = read_ledger()
        out = {"studying": bool(live["studying"]), "topic": live["topic"],
               "stage": live["stage"],
               "since": int(time.time() - live["since"]) if live["since"] else 0,
               "ticks": int(led.get("ticks") or 0), "kept": int(led.get("kept") or 0),
               "skipped": int(led.get("skipped") or 0),
               "failed": int(led.get("failed") or 0),
               "lastOutcome": last["outcome"], "lastMs": int(last["ms"]),
               "budgetS": read_syllabus()["tick_budget_s"], "queued": queued,
               "tools": {k: v["found"] for k, v in tool_report().items()}}
        return {k: out[k] for k in PUBLIC_KEYS if k in out}

    def request(self, topic=None, why="asked", url=None, audio=None, boss_call="sir"):
        """Queue a tick and return at once. (started, the sentence to say).

        THE ADDRESS FORM IS THE CALLER'S, not this module's. The first draft wrote "sir" into
        both sentences, which would have called an employer named anything else by a borrowed
        name - server.py holds the persona block and is the only thing entitled to say what he
        is called, so it passes the word in.

        RETURNS AT ONCE, ALWAYS, and that is the Async Law's load-bearing line: the conversational
        thread that calls this gets a sentence back in microseconds. The study happens on
        self._thread afterwards, and the seal is what reports it.
        """
        with self._lock:
            if self._live["studying"]:
                return False, ("I am already studying %s, %s."
                               % (self._live["topic"] or "something", boss_call))
            self._req = {"topic": topic, "why": why, "url": url, "audio": audio}
        self._wake.set()
        return True, ("Studying %s now, %s."
                      % (topic or "the next thing on the syllabus", boss_call))

    def _on_state(self, patch):
        with self._lock:
            stage = str(patch.get("stage") or "")
            self._live["stage"] = stage
            self._live["topic"] = str(patch.get("topic") or "")
            self._live["studying"] = bool(stage)
            if stage and not self._live["since"]:
                self._live["since"] = time.time()
            if not stage:
                self._live["since"] = 0.0
                if patch.get("last"):
                    self._last["outcome"] = str(patch["last"])

    def _loop(self):
        while not self._stop.is_set():
            self._wake.wait(POLL_S)
            self._wake.clear()
            if self._stop.is_set():
                return
            with self._lock:
                req, self._req = self._req, None
            if req is None:
                state = read_state()
                idle = time.time() - float(state.get("lastTickAt") or 0.0)
                if not (self.enabled and idle >= DAEMON_IDLE_S):
                    continue
                req = {"topic": None, "why": "daemon", "url": None, "audio": None}
            try:
                got = tick(topic_name=req.get("topic"), why=req.get("why") or "asked",
                           url=req.get("url"), audio_path=req.get("audio"),
                           on_state=self._on_state)
                with self._lock:
                    self._last = {"outcome": got.get("outcome") or "",
                                  "ms": int(got.get("totalMs") or 0)}
            except Exception as exc:                           # noqa: BLE001
                sys.stderr.write("scholar: the tick threw outside tick() (%s)\n" % exc)
                with self._lock:
                    self._live = {"studying": False, "topic": "", "stage": "", "since": 0.0}

    def start(self):
        if self._thread is not None:
            return False
        self._thread = threading.Thread(target=self._loop, name="scholar-tick", daemon=True)
        self._thread.start()
        return True

    def stop(self):
        self._stop.set()
        self._wake.set()


MANAGER = Scholar()
