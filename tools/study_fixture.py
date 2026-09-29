"""THE FIXTURE THAT IS TOO BIG ON PURPOSE.

    python tools/study_fixture.py _runs/study/big.wav            ~26 MB, 5 chunk slots
    python tools/study_fixture.py out.wav --minutes 14
    python tools/study_fixture.py out.wav --json

Builds one 16 kHz mono 16-bit WAV larger than Groq's 25 MB free-tier ceiling, so the Chunking
Law can be proved against a file the transcriber would refuse whole. It is written with the
`wave` module out of the standard library, which is the only reason this file is not just an
ffmpeg command: the exact byte count has to be chosen, not discovered, or "over 25 MB" is a
property of whatever bitrate an encoder felt like.

WHY IT SPEAKS ORDINALS. Stitched order is the assertion that is easy to get wrong and hard to
see: four transcripts joined by completion time read like a transcript and lie about the
sequence. So each CHUNK_SECONDS slot of this fixture is filled with speech that names its own
position - "section one", "section two" - repeated with variation across the whole slot, so
every chunk has many chances to be transcribed and the stitched result must read one, two,
three, four in that order or the splitter or the stitcher is broken. Silence padding was the
first draft and it was a bad one: whisper on 235 seconds of silence returns nothing, and a
chunk that transcribes to "" cannot testify about its own position.

Piper does the speaking, through tools/utter.py - the same voice every spoken harness uses, so
nothing new is installed for this and the fixture is reproducible from the tree.
"""
import argparse
import json
import os
import sys
import wave

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import scholar                                    # noqa: E402  - after the path insert
from tools import _proc                           # noqa: E402  - piper and ffmpeg, quietly

RATE = scholar.AUDIO_RATE
BYTES_PER_S = scholar.AUDIO_BYTES_PER_S
ORDINALS = ("one", "two", "three", "four", "five", "six", "seven", "eight")

# WHISPER WRITES DIGITS FOR SPOKEN NUMBERS, and an order assertion that does not know this
# fails against a pipe that is working perfectly. Measured on 2026-09-29: piper said "Section
# one", whisper-large-v3-turbo returned "Section 1.", every ordinal count came back zero, and
# the stitched-order check read ['one','one','one','one'] on four chunks that were in fact in
# exactly the right order. The regex, not the splitter, was broken - which is the most
# expensive kind of test failure, because it points at the wrong file. Anything asserting on
# this fixture must match the word OR the digit, so both spellings live here, once.
ORDINAL_ALTS = {w: "(?:%s|%d)" % (w, i + 1) for i, w in enumerate(ORDINALS)}

# Five sentences per slot, all naming the slot's ordinal, so the chunk has five independent
# chances to say where it is. The wording varies because a single sentence looped for four
# minutes runs into whisper's repetition suppression and comes back as one line.
SENTENCES = (
    "Section {n}. This is section {n} of the study fixture.",
    "You are listening to part {n} of the recording.",
    "The speaker in section {n} is talking about revenue and about audience.",
    "Remember that this passage belongs to section {n}, not to any other section.",
    "That was section {n}, and section {n} ends here for now.",
)


def say(text, folder):
    """One piper wave at 16 kHz mono, via utter.py. Returns raw frames."""
    out = os.path.join(folder, "say-%d.wav" % (abs(hash(text)) % 10**10))
    if not os.path.exists(out):
        res = _proc.run([sys.executable, os.path.join(ROOT, "tools", "utter.py"),
                         out, text], capture_output=True, text=True, timeout=180,
                        cwd=ROOT)
        if not os.path.exists(out):
            raise SystemExit("utter.py made no wave for %r: %s"
                             % (text[:40], (res.stderr or res.stdout)[-300:]))
    raw = os.path.join(folder, os.path.basename(out).replace(".wav", "-16k.wav"))
    if not os.path.exists(raw):
        ff = scholar.ffmpeg_exe()
        if not ff:
            raise SystemExit("ffmpeg is not installed, so the fixture cannot be built.")
        _proc.run([ff, "-hide_banner", "-loglevel", "error", "-y", "-i", out,
                   "-ac", "1", "-ar", str(RATE), "-c:a", "pcm_s16le", raw],
                  check=True, timeout=180)
    with wave.open(raw, "rb") as w:
        return w.readframes(w.getnframes())


def build(path, minutes=13.6, slot_s=None):
    slot_s = int(slot_s or scholar.CHUNK_SECONDS)
    total_s = int(minutes * 60)
    slots = max(2, -(-total_s // slot_s))          # ceil, and never fewer than two
    folder = os.path.join(ROOT, "_runs", "study", "say")
    os.makedirs(folder, exist_ok=True)
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)

    gap = b"\x00\x00" * int(RATE * 0.45)           # a breath, so sentences do not run together
    written, marks = 0, []
    with wave.open(path, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(RATE)
        for i in range(slots):
            name = ORDINALS[i % len(ORDINALS)]
            block = b""
            for tmpl in SENTENCES:
                block += say(tmpl.format(n=name), folder) + gap
            marks.append({"slot": i + 1, "ordinal": name, "alt": ORDINAL_ALTS[name],
                          "startS": round(written / BYTES_PER_S, 2)})
            want = slot_s * BYTES_PER_S
            got = 0
            while got < want:
                piece = block[:want - got]
                out.writeframes(piece)
                got += len(piece)
            written += got
    size = os.path.getsize(path)
    return {"path": os.path.relpath(path, ROOT).replace("\\", "/"), "bytes": size,
            "mb": round(size / 1048576.0, 2), "seconds": round(size / BYTES_PER_S, 1),
            "slots": slots, "slotSeconds": slot_s, "rate": RATE,
            "overGroqHardMax": size > scholar.GROQ_HARD_MAX,
            "groqHardMax": scholar.GROQ_HARD_MAX,
            # THE COUNT IS TAKEN FROM THE SAMPLES AND NOT FROM THE FILE, because a wav file is
            # its audio plus a 44-byte header and ffmpeg splits on the audio. Counted off `size`
            # this said 5 for four exact 240-second slots - 44 bytes past the fourth boundary -
            # and a harness asserting equality against it would have failed a splitter that was
            # perfectly correct. Measured: 4 chunks of 7 680 078 bytes for a 30 720 044-byte
            # fixture, each carrying a 67-byte header of its own.
            "expectChunks": -(-written // (slot_s * BYTES_PER_S)), "marks": marks}


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Build a >25 MB spoken WAV fixture.")
    ap.add_argument("out")
    ap.add_argument("--minutes", type=float, default=13.6)
    ap.add_argument("--slot", type=int, default=None)
    ap.add_argument("--json", action="store_true", dest="as_json")
    args = ap.parse_args()
    got = build(args.out, args.minutes, args.slot)
    if args.as_json:
        print(json.dumps(got))
    else:
        print("%s  %.2f MB  %.0fs  %d slots of %ds  over Groq's %d: %s"
              % (got["path"], got["mb"], got["seconds"], got["slots"], got["slotSeconds"],
                 got["groqHardMax"], got["overGroqHardMax"]))
        for mark in got["marks"]:
            print("   slot %d  '%s'  starts at %.0fs" % (mark["slot"], mark["ordinal"],
                                                         mark["startS"]))
