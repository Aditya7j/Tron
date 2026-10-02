#!/usr/bin/env python3
"""timings.py - where each word of a spoken line begins, in seconds of its own audio.

The standard library only - `re`, `wave`, `array`, `io` - and no model, no alignment
pass and no second subprocess. A forced aligner would be the honest way to get this and
it is also a 40 MB dependency, a second inference per sentence, and a new failure mode in
the one route that must never be slow: /say is the most frequent POST in a session and the
page is holding a sentence open waiting for it. So this file does the cheap thing well
instead, and the two halves of "well" are worth naming because they are what separate this
from a guess:

  IT IS NORMALISED TO THE REAL WAV. The weights below say how the duration is DIVIDED; the
    duration itself is read out of the bytes piper just produced. So the last word's start
    is always inside the audio and the sum of the parts is always the whole - which is the
    one property a per-word estimate has to have for a karaoke reveal not to drift off the
    end of a long sentence.
  AND THE SILENCE AT EITHER END IS MEASURED, NOT ASSUMED. A piper wav opens with 40-120ms
    of room tone and closes with a tail; spreading the words across the FILE instead of
    across the SPEECH puts every word about a tenth of a second early, which at the start
    of a sentence is exactly where it is most visible. wav_span() finds the first and last
    block of audio above the floor, and the words are laid out between those two instants.

WHAT THE WEIGHTS ARE. One word's share of the span is its syllable count plus whatever
pause it ENDS on - a comma is 0.45 of a syllable, a full stop 1.0, an ellipsis 1.2. The
pause is charged to the word before it rather than to the gap after it, which is the whole
of "pauses preserved": the next word's start is pushed later by exactly the rest the voice
takes, and the punctuated word keeps the breath it was read with instead of being clipped.

A FLOOR OF MIN_WEIGHT ON EVERY WORD, because a one-syllable word is not one-third of a
three-syllable word in time: "a" and "the" are faster than one syllable's share but far
from a third of "difficult", and a reveal that ran ahead on every article looked broken on
precisely the sentences people write.

A TOKEN WITH NO LETTERS IN IT gets one beat per digit. A voice reads "2026" as four
syllables and "19" as three, so a price or a year weighted as one word is a word the reveal
sits on for a quarter of the time it is actually being said.

IT NEVER RAISES, like say.py and search.py, and for the same reason: the caller's next move
is the same whatever went wrong. An unparseable WAV, a zero-length file, a text of nothing -
every one of them comes back as an empty list, and an empty list is the page's cue to show
the whole sentence at once, which is what it did before this file existed.
"""

import array
import io
import re
import wave

# ---- the pause each mark is worth, in syllable-equivalents. A comma is a rest about half
# a syllable long in a neural voice at length-scale 1.05; a full stop is a whole one. These
# are the only taste in this file and they are stated as numbers so a harness can read them.
PAUSE_WEIGHT = {
    ",": 0.45, ";": 0.70, ":": 0.70,
    "—": 0.45, "–": 0.45, "-": 0.45,    # em-dash, en-dash, and the hyphen everybody types
    ".": 1.00, "!": 1.00, "?": 1.00,
    "…": 1.20,                          # the ellipsis: the longest rest in prose
}
# WHY THE BARE ASCII HYPHEN IS IN THAT DICT (§40, one character, and it was §39's punchlist).
# §39 measured the fault and deliberately did not fix it, because re-weighting the tokeniser after
# the drift proof had run is how an unmeasured change ships. The fault: `-` used as a dash is what
# people actually type, and without an entry here it was charged 1 syllable and NO rest, so the
# reveal sat a quarter-second on a dash the voice plainly rests at and was that much late for the
# clause after it. Bounded, because the span is normalised - it could never accumulate past the
# next mark - but visibly wrong on exactly one word.
#
# IT IS SAFE FOR HYPHENATED WORDS, and that is a property of tokens() rather than of this line:
# the pause is read from the END of a whitespace-separated token, so `word-by-word` ends on `d`
# and takes nothing, `state-of-the-art,` ends on the comma inside it, and only a token that
# genuinely FINISHES on a hyphen - the standalone dash, or a line broken mid-compound - collects
# the rest. karaoke_proof re-ran at its 92 floor with this line in place.
# Closing marks are transparent: `card."` and `(yes)` end on the mark INSIDE them.
CLOSERS = "\"')]}»”’"
# No word is worth less than this many syllables' time. See the docstring.
MIN_WEIGHT = 0.62
# ---- the silence at either end. A block is 10ms and a block counts as speech when its
# peak reaches this fraction of the loudest block in the file. 3.5% is below piper's room
# tone on every voice in ./voices and well above the dither floor of a 16-bit file.
SILENCE_FLOOR = 0.035
BLOCK_MS = 10.0
VOWEL_RUN = re.compile(r"[aeiouy]+")
LETTERS = re.compile(r"[^a-z]")
DIGITS = re.compile(r"[^0-9]")


def syllables(word):
    """How many beats a reader gives one token. Never below 1.

    Vowel runs, less the silent terminal `e` - the oldest heuristic there is, and the
    three exceptions below are the three that matter in ordinary prose: `table` and
    `little` keep their final syllable because the `le` IS one, `see` and `agree` keep
    theirs because a doubled vowel is not a silent e, and a one-syllable word is never
    reduced to zero.
    """
    w = LETTERS.sub("", str(word or "").lower())
    if not w:
        # Digits, or a token of pure punctuation. "2026" is four beats; "$" is one.
        return max(1, len(DIGITS.sub("", str(word or ""))))
    n = len(VOWEL_RUN.findall(w))
    if n > 1 and w.endswith("e") and not w.endswith(("le", "ee", "ye", "oe", "ie")):
        n -= 1
    return max(1, n)


def tokens(text):
    """[(word, syllables, pause)] in reading order, split on whitespace and nothing else.

    WHITESPACE AND NOTHING ELSE is the load-bearing half: the page splits the same string
    the same way to find the spans it will reveal, so the two sides agree on what word
    number seven is by construction rather than by two regexes that have to stay in step.
    """
    out = []
    for raw in str(text or "").split():
        pause = 0.0
        for ch in reversed(raw):
            if ch in PAUSE_WEIGHT:
                pause = max(pause, PAUSE_WEIGHT[ch])
                break
            if ch in CLOSERS:
                continue
            break
        out.append((raw, syllables(raw), pause))
    return out


def word_timings(text, seconds, lead=0.0):
    """[start_second, ...] - one per whitespace-separated word, inside [lead, seconds].

    seconds is the END of the speech and lead is its START, both measured off the wav by
    wav_span(); the words are laid out between them in proportion to their weights. The
    first start is therefore `lead` exactly and the last is strictly less than `seconds`,
    which is the property the page's drift check is written against.
    """
    toks = tokens(text)
    span = float(seconds) - float(lead)
    if not toks or span <= 0:
        return []
    weights = [max(MIN_WEIGHT, float(syl)) + pause for _word, syl, pause in toks]
    total = sum(weights) or 1.0
    starts, at = [], float(lead)
    for weight in weights:
        starts.append(round(at, 3))
        at += span * weight / total
    return starts


def wav_span(data):
    """(seconds, speech_start, speech_end) read out of the WAV's own bytes.

    Never raises: a header this cannot parse comes back (0,0,0) and the caller shows the
    whole sentence at once. A file that parses but is not 16-bit comes back with its real
    length and no silence trim, because the length is still true and the trim is the part
    that needed the samples.
    """
    try:
        with wave.open(io.BytesIO(bytes(data or b"")), "rb") as fh:
            rate = fh.getframerate() or 0
            frames = fh.getnframes() or 0
            chans = max(1, fh.getnchannels() or 1)
            width = fh.getsampwidth() or 0
            raw = fh.readframes(frames)
    except Exception:                                          # noqa: BLE001
        return 0.0, 0.0, 0.0
    if not rate or not frames:
        return 0.0, 0.0, 0.0
    secs = round(frames / float(rate), 3)
    if width != 2 or not raw:
        return secs, 0.0, secs
    samples = array.array("h")
    try:
        samples.frombytes(raw[:len(raw) - (len(raw) % 2)])
    except Exception:                                          # noqa: BLE001
        return secs, 0.0, secs
    step = max(1, int(rate * BLOCK_MS / 1000.0)) * chans
    peaks = []
    for i in range(0, len(samples), step):
        block = samples[i:i + step]
        if not block:
            break
        # max() and -min() rather than a per-sample abs(): two C-level passes over an
        # array slice instead of a Python loop, which is the difference between a
        # microsecond and a millisecond per block on a ten-second line.
        peaks.append(max(max(block), -min(block)))
    loud = max(peaks) if peaks else 0
    if loud <= 0:
        return secs, 0.0, secs
    floor = loud * SILENCE_FLOOR
    first, last = 0, len(peaks) - 1
    while first < last and peaks[first] < floor:
        first += 1
    while last > first and peaks[last] < floor:
        last -= 1
    per = step / float(chans) / float(rate)
    start = round(first * per, 3)
    end = round(min(secs, (last + 1) * per), 3)
    if end <= start:
        return secs, 0.0, secs
    return secs, start, end


def timings_for(text, wav):
    """The whole answer for one spoken chunk, as the /say headers carry it.

    `starts` is in seconds from the first sample of the wav - which is the clock the page
    has, because it plays the decoded buffer from offset zero.
    """
    secs, start, end = wav_span(wav)
    if secs <= 0:
        return {"secs": 0.0, "speechStart": 0.0, "speechEnd": 0.0,
                "words": 0, "starts": []}
    starts = word_timings(text, end, start)
    return {"secs": secs, "speechStart": start, "speechEnd": end,
            "words": len(starts), "starts": starts}


def header(starts):
    """The X-Word-Timings value: three decimals, comma-separated, NUMBERS ONLY.

    No word ever goes in a header. The page already has the text it asked to be spoken and
    the privacy law in this house is that a log line counts characters and never prints
    them - a header is a log line somebody else keeps.
    """
    return ",".join("%.3f" % float(t) for t in (starts or []))


if __name__ == "__main__":                                      # a one-line check
    import json as _json
    import sys as _sys
    line = _sys.argv[1] if len(_sys.argv) > 1 else (
        "Good evening, sir. The pricing page is ready - three tiers, and the middle one "
        "is the one they take.")
    if len(_sys.argv) > 2:
        with open(_sys.argv[2], "rb") as _fh:
            _wav = _fh.read()
        print(_json.dumps(timings_for(line, _wav), indent=2))
    else:
        print(_json.dumps({"words": [t[0] for t in tokens(line)],
                           "syllables": [t[1] for t in tokens(line)],
                           "pauses": [t[2] for t in tokens(line)],
                           "startsOverTenSeconds": word_timings(line, 10.0)}, indent=2))
