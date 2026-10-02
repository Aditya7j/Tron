"""THE DIRECTOR - §35 PART 2.  A video about one of the boss's own topics, made locally.

    python tools/make_video.py --topic "micro-saas pricing"
    python tools/make_video.py --topic "micro-saas pricing" --json
    python tools/make_video.py --topic "nothing at all" --json     the graceful-empty path
    python tools/make_video.py --probe                             what is installed, only

WHY A CLI AND NOT JUST AN ENDPOINT, which is study_tick.py's answer and this file's too: the
endpoint returns immediately, because a three-minute render may not block a conversation, so
watching a render through it means polling and inferring. This runs the same pipeline on the
calling thread and prints what each stage cost - the difference between "the pipe works" and
"the pipe works and here is where the hundred and eighty seconds went". director_proof drives
this file for that reason.

ZERO NEW VENDORS, and that is a constraint with teeth. Every frame is produced by an ffmpeg
filtergraph and no bitmap is ever composited in Python, because Pillow is not installed and
§35 forbids installing it. The five enables in the Gyan build are the whole of what is needed:

  gradients     an lavfi SOURCE, so the dark background is generated and there is no asset
                directory to keep in step with the palette.
  drawtext      the cards, with an explicit fontfile. THE WINDOWS ESCAPE IS LOAD-BEARING:
                the path must be written  fontfile='C\\:/Windows/Fonts/arialbd.ttf'  because a
                bare C: is read as the start of a filter option, and the failure mode is not a
                missing font, it is the whole filtergraph refusing to parse.
  drawbox       the animated chart - but NOT the way it reads. ITS w/h/x/y ARE EVALUATED ONCE,
                at graph-init, in this build: there is no `eval=frame` option on it at all
                ("Could not set non-existent option 'eval'"), and `t` at init is unknown, so
                w='min(300,300*max(0,t)/2)' does not grow - it comes out FULL WIDTH on frame one.
                Measured, after shipping six "animated" boxes that never animated: a bar card
                sampled at 0.12s showed every bar already at its final length. What IS per-frame
                is the timeline `enable` option, which the filter does support, so a growing box
                is a row of fixed-width slices each switched on at its own time - see _grow_box().
                drawtext's `alpha` IS a real per-frame expression, which is why the fades always
                worked and hid the fact that the boxes did not. geq would also do it, thirty
                times slower per frame, which is why it is not used.
  subtitles     the burned captions, through libass, which owns the line-breaking and the
                outline. A drawtext per caption would make the filtergraph length grow with the
                script.
  concat        the DEMUXER with -c copy, one scene per file at identical codec parameters,
                then ONE final pass that muxes the AAC voiceover and burns the subtitles. The
                alternative - one giant filter_complex with xfade between every scene -
                re-encodes every frame of every scene for each edit, and that is the whole
                difference between a 180-second budget kept and missed.

THE FAILURE MODE NAMED FOR THE WHOLE FILE: if any of those rungs is wrong, the symptom is a
zero-byte mp4 and an ffmpeg exit code, never a silently ugly frame. So every stage checks the
size of its own output, and director_proof reads the final file with ffprobe rather than
trusting a return code.

AND IT REPORTS ON THE GLASS WHILE IT WORKS. The boss's law in §35 PART 3 is that a
backend-only job is not accepted, so this is the progress bus's first producer: five steps,
declared up front, each emitting an ordered event, and one ledger row on completion. Nothing in
jobs.py knows what a video is.

WHAT IT WILL NOT DO. A topic the notes hold nothing on gets a sentence and no mp4 - "the notes
hold nothing on X" - because a video made out of a model's general knowledge would be a video
about nothing the boss wrote, dressed as a video about his own work. recall()'s `opens` flag is
the whole of that test, and it is the server's own retrieval, not a second copy of it.

NO CREDENTIAL REACHES THIS OUTPUT, and config.json is read only through server.load_config().
"""
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import wave

import ingest
import jobs
import say
# THE ONLY DOOR TO A CHILD PROCESS IN THIS HOUSE, and this module is the heaviest user of it:
# one render spawns six ffmpeg encodes, an ffprobe and five piper calls. Through subprocess.run
# directly, every one of those is a console window opening and closing on the employer's desktop
# while he is working - which is what preflight's check 21 exists to catch, and did.
from tools import _proc

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT_ROOT = os.path.join(ROOT, "output", "videos")

# server IS NOT IMPORTED AT MODULE LEVEL, and that is the one import in this file that needs a
# reason. server.py imports this module to answer "make a video about X", so importing it back
# here at module scope is a cycle: whichever of the two is loaded second gets a half-built
# module object, and the symptom is an AttributeError at the first render rather than at import.
# write_script() imports it inside the function instead, where the cycle is already resolved -
# the same shape scholar.py uses for the functions the server hands it.

# ---- THE BUDGETS, every one of them an assertion in director_proof ---------------------------
VOICE_MIN_S = 40.0          # §35: "voiceover 40-70s". Below this it is a clip, not a video.
VOICE_MAX_S = 70.0
WALL_MAX_S = 240.0          # §36 raised §35's 180: the Director's Cut re-encodes the whole
                            # timeline to cross-fade it, where §35 joined with -c copy.
WORDS_PER_S = 2.45          # measured from ryan-high, and used only to AIM the script. The
                            # real duration is read off the synthesised WAVs, never predicted.
BEATS_MAX = 5               # beat cards. Five 10-second beats is the 50-second middle of the
                            # voiceover budget, and six would push a 60s script past 70s.
FPS = 30
W, H = 1280, 720

# ---- §36 PART 2 - THE DIRECTOR'S CUT ---------------------------------------------------------
# THE DEFECT, IN THE BOSS'S OWN WORDS: "a captioned slideshow whose card bodies duplicate the
# captions, with no chart, no code, no diagram". He scored it 20% and the score stands. Every
# number below is one clause of the answer, and each is asserted rather than styled.
PAUSE_S = 0.4               # §36: "0.4s pause after each beat". It is REAL SILENCE in the
                            # voiceover and therefore in the caption clock too - a pause that
                            # existed only in the picture would desynchronise the subtitles.
XFADE_S = 0.5               # every scene cross-dissolves into the next. Each scene file is
                            # rendered XFADE_S longer than the slot it owns, so the sum of the
                            # slots is still the length of the audio - see stitch().
# §38 REDEFINES HOOK_S, and the old meaning was the defect. It used to be 4.5 seconds of LEAD
# SILENCE that the hook card sat over: the boss watched the render and the first thing he said
# was that the opening carries no voice. The card held the whole hook sentence in 54-pixel type,
# in silence, and the voice then spoke that same sentence over the NEXT scene - so the opening
# claim arrived twice, printed and then narrated, and neither arrival was the start of the film.
#
# There is no lead now. The voiceover begins at t=0 with the hook sentence, and HOOK_S is the
# hook card's SHARE OF THAT FIRST BEAT - a title card over the opening words, which is what a
# title card is. The beat keeps its own classified scene for the rest of its airtime, and that is
# not a detail: measured, letting the hook card consume the whole first beat cost the useEffect
# video its CODE CARD, because `code` was the type the opening sentence had been classified to
# and §36 requires a code card in that film. The card is capped at half the beat so that the
# beat's visual always gets at least as long as the title that introduced it.
HOOK_S = 4.5                # long enough to READ a headline in 54-pixel type, which 3.0 was not
CTA_S = 5.0                 # the sign-off, over the tail silence - the one bookend that remains
CHART_SPAN = 20.0           # the widest top-to-bottom ratio one chart may hold: past this the
                            # small bars are stubs and the chart says only "one is bigger",
                            # which the viewer already heard. See chart_figures().
CHART_S = 4.5               # a recap chart, when the script carries figures no beat claimed
# NO STATIC FRAME LONGER THAN 2 SECONDS, and the threshold is measured and not chosen. Gray
# frames sampled one second apart at 160x90, mean absolute difference, 0-255: a frozen card reads
# 0.0, §35's default drift speed of 0.01 reads 0.5 to 2.4, and this palette at MOTION_SPEED over
# a pinned ramp reads 4.3 to 7.4 at every half second of an eighteen-second scene. So 3.0 sits
# above everything §35 shipped and below the WORST reading of what §36 ships.
#
# AND THE SPEED IS 0.10 BECAUSE 0.05 WAS A LOTTERY, which is the defect this number was raised to
# fix rather than a preference. With the ramp endpoints unpinned (see _gradient) the orientation
# was random per scene, so the same filtergraph gave one beat 7.6 and the next 1.8 - two of the
# five beats in the first §36 pricing render were below the floor while the other three were
# double it, and nothing in the code said which. Pinned, every scene drifts the same measurable
# amount; at 0.10 the worst half-second of a long scene reads 4.28, where 0.05 pinned reads 2.77
# and 0.18 swings erratically between 1.84 and 3.11 as the rotation passes through phases where
# the ramp is nearly self-similar. 0.10 is the one speed measured to clear the floor everywhere.
MOTION_SPEED = 0.10
MOTION_MAD_MIN = 3.0
MOTION_SAMPLE = (160, 90)
GRADIENT_SEED = 7          # pinned for the reason in _gradient(): an unpinned ramp is a lottery
# A CARD BODY MUST NEVER DUPLICATE ITS CAPTIONS. Shared tokens over the UNION of the two bags -
# a card of 3 keywords against a 25-token sentence reads 0.12, and §35's beat card, which WAS
# the sentence, reads 1.00. Measured over the union rather than over the card alone on purpose:
# a one-word headline drawn from the sentence is good design, and dividing by the card's own
# size would call it a 100% duplicate and forbid it.
DUP_MAX = 0.40
HEADLINE_WORDS = 8          # §36: "headline (<=8 words) + one visual"

# ---- §38 - THE TOPIC GUARD, THE LIST PARSER, AND VOICE AT FRAME ZERO -------------------------
# THE DEFECT, FROM THE FRAMES: beat four of the useEffect video spoke "If I pick a tab in the
# share picker, say so honestly and steer me to share the entire screen" - a sentence about this
# house's own screen-share behaviour, narrated over a video about a React hook. Every number
# below was measured off that render before it was chosen.
#
# A RETRIEVED CHUNK IS NOT AUTOMATICALLY ON TOPIC, and the recall score already said so. On
# "explain useEffect in react" the four react notes score 0.778, 0.743, 0.675 and 0.673, and the
# Jarvis prompt-pack chunk that supplied the passenger scores 0.568 - the band is 0.105 wide and
# the passenger sits 0.210 below the best. On "micro-saas pricing" ten chunks span 0.835 to
# 0.759, a band of 0.077 with nothing to drop. So the floor is RELATIVE to the best hit, because
# an absolute one would be a different number for every topic, and it is 0.15: above both real
# bands and below the one passenger this corpus contains.
RECALL_GAP = 0.15
# AND THE SECOND READER IS LEXICAL, because the first is a model and a model can be unreachable.
# A beat is corroborated when its own content words appear in the TOPIC or in two or more of the
# surviving notes - the vocabulary the retrieved set agrees on. Measured over both regression
# scripts: the passenger corroborates ZERO words, and the weakest sentence that belongs - "Treat
# pricing as an iterative experiment..." - corroborates TWO. The floor is one word, which is
# below everything that belongs and above nothing. The share is reported beside it as the
# strength, and is never the test: a count cannot be gamed by a short sentence.
TOPIC_MIN_WORDS = 1
TOPIC_NOTES_MIN = 2         # how many surviving notes must hold a word for it to corroborate
# A BULLET IS A WHOLE LIST ITEM. The frames showed THE LIST rendering "Say" and "Entire" - two
# single words, because the first draft reduced each clause to keywords and then, when the label
# ran long, to its first keyword alone. Three words is the floor, and the beat loses the list
# rather than the list losing its words: a two-word item is a chip, and chips_scene draws those.
BULLET_MIN_WORDS = 3
BULLET_MAX_WORDS = 7        # what fits one 36px row inside the card's 1000px of width
# AND A LIST OF WHOLE ITEMS REPRINTS THE SENTENCE'S OWN WORDS, which is the collision §38 walks
# into: measured, a whole-item list scores 1.000 against §36's duplication ceiling of 0.40, so
# every list beat would degrade to chips and THE LIST would never render again. The resolution is
# §36's own, written into duplication() for figures: the ITEMS ARE THE VISUAL, the way bar labels
# are, and what the law then measures on a list card is the headline. But §35's wound stays shut -
# the card may carry the LIST and never the SENTENCE, so the sentence must still hold words the
# card does not print. Measured over seven real list beats the number is bimodal and there is no
# middle: a sentence that is nothing but its list leaves 0 unprinted content words (three cases),
# a sentence with a real stem leaves 6 or 7 (three cases). Three sits clear of both.
BULLET_KEEP_WORDS = 3

# ---- THE PALETTE, the frozen glass's own two darks, so the video looks like the house --------
BG0, BG1 = "0x0a0e14", "0x16202e"
INK = "white"
DIM = "0xa8b3c4"
BAR = "0x4ea1ff"
KEYW = "0xff9f6b"           # a code keyword
LIT = "0x7fd48a"            # a code string or number

FONT_BOLD = "C\\:/Windows/Fonts/arialbd.ttf"       # see the escape note in the docstring
FONT_PLAIN = "C\\:/Windows/Fonts/arial.ttf"
# THE CODE CARD'S FONT IS FIXED-WIDTH AND THAT IS LOAD-BEARING, not a style note. Keyword
# colouring means drawing one line as several drawtext filters side by side, and the only way to
# know where the next one starts is to know the advance width of a character - which a
# proportional font does not have. Consolas advances 0.5498 of the font size per character,
# measured off this machine's own metrics, and MONO_COLS is what fits the card at size 30.
FONT_MONO = "C\\:/Windows/Fonts/consola.ttf"
FONT_MONO_BOLD = "C\\:/Windows/Fonts/consolab.ttf"
MONO_ADVANCE = 0.5498
MONO_COLS = 46

STEPS = ["script", "voice", "scenes", "captions", "stitch"]


# =============================================================================================
#  THE DESK: what is installed
# =============================================================================================
def _which(name):
    return shutil.which(name) or shutil.which(name + ".exe") or ""


def probe():
    """What this file needs, as booleans and versions. Never a path to a credential."""
    ff, fp = _which("ffmpeg"), _which("ffprobe")
    ver = ""
    if ff:
        try:
            out = _proc.run([ff, "-version"], capture_output=True, text=True,
                            timeout=20).stdout
            ver = (out.splitlines() or [""])[0][:90]
        except (OSError, subprocess.SubprocessError):
            ver = ""
    voice = say.ready(say.DEFAULT_MODEL)
    return {"ffmpeg": bool(ff), "ffprobe": bool(fp), "ffmpegVersion": ver,
            "voice": bool(voice.get("ready")), "voiceWhy": str(voice.get("why") or ""),
            "voiceModel": say.DEFAULT_MODEL,
            # THE MONOSPACE PAIR IS REPORTED TOO, because §36's code card is the one scene type
            # that depends on a font this house did not already use. Missing, the filtergraph does
            # not fall back to Arial - it refuses to parse, and the whole render dies on the beat
            # that happened to be classified `code`. A probe that answered "fonts: ok" while the
            # one font a scene type needs was absent would be a probe worth deleting.
            "fonts": {"bold": os.path.exists("C:/Windows/Fonts/arialbd.ttf"),
                      "plain": os.path.exists("C:/Windows/Fonts/arial.ttf"),
                      "mono": os.path.exists("C:/Windows/Fonts/consola.ttf"),
                      "monoBold": os.path.exists("C:/Windows/Fonts/consolab.ttf")}}


def slug_of(topic):
    said = re.sub(r"[^a-z0-9]+", "-", str(topic or "").strip().lower()).strip("-")
    return (said or "untitled")[:48]


# EVERY drawtext CARRIES THESE TWO, and the second one is a bug fix rather than a preference.
# drawtext's `y` means, by default, "the top of the bounding box OF THIS STRING" - so two drawtexts
# given the same y do NOT share a baseline unless they happen to contain the same tallest glyph.
# The code card showed it first: `// React 19:` and `no wrapper needed` are one source line drawn
# as separate tokens so each can take its own colour, and the tokens with no ascender in them -
# `no`, `wrapper` - rode five pixels high on the glass while `React` and `needed` sat correctly.
# y_align=font refers y to the FONT's own line metrics instead, which are the same whatever the
# string, and that is what makes a row of per-token drawtexts one line of code. It moves every
# text down by the ascent-to-cap-height difference, which is why the card geometry was re-measured
# against plates after it went in rather than reasoned about.
TEXT = "expansion=none:y_align=font"
# EVERY drawtext CARRIES IT, and it is not a tidying flag. By default drawtext expands %{...}
# sequences in its text, which means a note quoting "up 50%" is a filtergraph that will not
# parse: ffmpeg answers "Stray % near ''" and refuses the whole graph, so the symptom is a
# missing SCENE and not a missing character. Escaping the percent does not help - \% is still
# stray - so expansion is turned off instead, which also removes the whole class: no clock
# sequence, no metadata sequence, nothing in the boss's own prose can address the renderer.


def _esc(text):
    """drawtext's own escaping, and the order matters.

    Backslash first or it would escape the escapes that follow it. The colon and the single
    quote are the two characters that end a filter option. The percent is NOT escaped here -
    see TEXT above; it is disarmed by turning expansion off, which is the fix that cannot be
    half-applied. Newlines are not escaped either, they are REMOVED, because a drawtext with a
    literal newline in it is a filtergraph that will not parse.
    """
    said = str(text or "")
    for a, b in (("\\", "\\\\"), (":", "\\:"), ("'", "\u2019"),
                 ("[", "\\["), ("]", "\\]"), (",", "\\,"), (";", "\\;")):
        said = said.replace(a, b)
    return re.sub(r"\s+", " ", said).strip()


def _wrap(text, cols):
    """Hard-wrapped lines, because drawtext does not wrap and libass is not in play on a card."""
    words, lines, cur = str(text or "").split(), [], ""
    for word in words:
        if len(cur) + len(word) + 1 > cols and cur:
            lines.append(cur)
            cur = word
        else:
            cur = (cur + " " + word).strip()
    if cur:
        lines.append(cur)
    return lines


def _run(args, timeout=120):
    """One subprocess, quietly, with its stderr kept for the one line that matters.

    ffmpeg's stderr is five hundred lines of banner and two of diagnosis, so only the tail is
    carried - and it is carried rather than printed, because the caller turns it into a bus
    event and a ledger `detail`, both of which are single-line fields.
    """
    try:
        done = _proc.run(args, capture_output=True, text=True, timeout=timeout,
                         encoding="utf-8", errors="replace")
    except (OSError, subprocess.SubprocessError) as exc:
        return 1, "", str(exc)[:300]
    tail = "\n".join((done.stderr or "").strip().splitlines()[-4:])
    return done.returncode, done.stdout or "", tail


def wav_seconds(path):
    """A WAV's duration from its own RIFF header. No ffprobe, no estimate, no arithmetic."""
    try:
        with wave.open(path, "rb") as fh:
            rate = fh.getframerate() or 22050
            return round(fh.getnframes() / float(rate), 3)
    except (OSError, wave.Error):
        return 0.0


# =============================================================================================
#  STEP 1 - THE SCRIPT, out of the boss's own notes
# =============================================================================================
def _numbers_in(text):
    """The figures a passage carries, each with its UNIT - the condition for a chart scene.

    PERCENTAGES, MULTIPLES AND MONEY. §35 read percentages and multiples only, bounded at 1000,
    and that bound is why the boss's own pricing video had no chart in it: every quantity in
    those notes is a price. §36 asks for "values parsed from the cited note", so money is read
    too - "$50-$100 per month rather than $19", "$5,000-$10,000 MRR", "$10k" - with k and m
    expanded, because $10k and $10,000 are the same number written two ways and would otherwise
    be two bars.

    THE UNIT IS CARRIED BECAUSE A CHART NEEDS ONE SCALE. A bar of 10 percent beside a bar of
    5,000 dollars is not a comparison, it is two rectangles whose lengths mean nothing together,
    so chart_figures() picks ONE unit family and the bars inside it share a scale. A chart of
    "2026" and "4700" - the failure mode of looking for digits rather than quantities - is still
    impossible: a number with no unit beside it is not a figure here.
    """
    out, seen = [], set()
    pattern = (r"(?:(?P<cur>[$£€])\s?(?P<money>\d{1,3}(?:,\d{3})*(?:\.\d+)?|\d+(?:\.\d+)?)"
               r"\s*(?P<scale>[kKmM])?\b)"
               r"|(?:(?P<num>\d{1,4}(?:\.\d+)?)\s*(?P<unit>%|x\b|percent))")
    for m in re.finditer(pattern, str(text or ""), re.I):
        if m.group("money"):
            try:
                val = float(m.group("money").replace(",", ""))
            except ValueError:
                continue
            mult = {"k": 1000.0, "m": 1000000.0}.get((m.group("scale") or "").lower(), 1.0)
            val *= mult
            if not 0 < val <= 10000000:
                continue
            unit = "$"
            label = "%s%s" % (m.group("cur"), _money(val))
        else:
            try:
                val = float(m.group("num"))
            except ValueError:
                continue
            if not 0 < val <= 1000:
                continue
            unit = "x" if m.group("unit").lower() == "x" else "%"
            label = ("%gx" % val) if unit == "x" else ("%g%%" % val)
        # THE SAME FIGURE TWICE IS ONE BAR. The narration restates its own numbers, and a chart
        # with two identical bars reads as a rendering fault rather than as emphasis.
        if (unit, val) in seen:
            continue
        seen.add((unit, val))
        out.append({"value": val, "label": label, "unit": unit})
    return out


_ONES = {"zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
         "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13,
         "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
         "nineteen": 19}
_TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fourty": 40, "fifty": 50, "sixty": 60,
         "seventy": 70, "eighty": 80, "ninety": 90}
_SCALES = {"hundred": 100, "thousand": 1000, "million": 1000000}
# The unit has to be SAID for the figure to be charted, which is what keeps "two hundred
# customers" off a chart of prices and "2026" off a chart of anything.
_SAID_UNITS = {"dollar": "$", "dollars": "$", "buck": "$", "bucks": "$", "pound": "$",
               "pounds": "$", "euro": "$", "euros": "$", "percent": "%", "per-cent": "%",
               "points": "%", "times": "x", "fold": "x"}
# A range says its unit once: "fifty to a hundred dollars" is two prices, not one.
_RANGE_JOINS = frozenset(("to", "or", "and", "through", "up", "until", "upto"))
# And a comparison says it once at the other end: "$50-$100, rather than nineteen".
_COMPARE_CUES = frozenset(("than", "versus", "vs", "instead", "beats", "against", "not",
                           "from", "over", "under", "above", "below"))


def _spoken_numbers(text):
    """The figures a passage says IN WORDS, each with its unit. Returns the _numbers_in shape.

    THIS EXISTS BECAUSE THE NARRATION IS WRITTEN TO BE SPOKEN, and the first real §36 render is
    the evidence. The script for "micro-saas pricing" came out of the model as "fifty to a hundred
    dollars a month, rather than nineteen" and "two hundred customers at fifty dollars" - every
    quantity in the boss's own pricing video spelled out, because digits read badly aloud. A
    digit-only parser therefore found nothing and the video the mandate requires to carry a chart
    carried none, while the voice was saying four prices.

    THREE RULES, AND EACH ONE IS A SENTENCE SHAPE THESE NOTES ACTUALLY USE:
      - a run of number words is read the ordinary way, with "a hundred" meaning one hundred;
      - a run inherits a unit FORWARD across a range join only - "fifty to a hundred dollars" is
        $50 and $100, while "a hundred at a hundred dollars" is NOT two prices, because "at" is
        not a range word and the first hundred counts customers;
      - a run inherits a unit BACKWARD after a comparison cue - "rather than nineteen" is $19,
        which is the whole point of the sentence and the bar the chart would otherwise miss.

    A run with no unit after all three rules is dropped. That is the same bar as _numbers_in's:
    a number with no quantity attached is not a figure, and a chart of "two hundred customers"
    beside "$50" is two rectangles whose lengths mean nothing together.
    """
    words = [w for w in re.split(r"[^A-Za-z0-9$%.,-]+", str(text or "")) if w]
    # HYPHENS ARE SPLIT, because "twenty-five" is two number words and "per-cent" is a unit.
    flat = []
    for w in words:
        for part in w.split("-"):
            part = part.strip(".,")
            if part:
                flat.append(part.lower())
    runs, i = [], 0
    while i < len(flat):
        word = flat[i]
        start = i
        if word in ("a", "an") and i + 1 < len(flat) and flat[i + 1] in _SCALES:
            i += 1
            word = flat[i]
        if word not in _ONES and word not in _TENS and word not in _SCALES:
            i += 1
            continue
        total, current, used = 0, 0, False
        while i < len(flat):
            word = flat[i]
            if word in _ONES:
                current += _ONES[word]
            elif word in _TENS:
                current += _TENS[word]
            elif word == "hundred":
                current = max(1, current) * 100
            elif word in _SCALES:
                total += max(1, current) * _SCALES[word]
                current = 0
            elif word in ("a", "an") and i + 1 < len(flat) and flat[i + 1] in _SCALES:
                pass
            else:
                break
            used = True
            i += 1
        if not used:
            continue
        value = float(total + current)
        # "ONE POINT FIVE" IS 1.5 AND NOT ONE, which matters because a multiple is usually said
        # that way: without this, "a three times multiple beats a one point five" charted a bar of
        # 1 against a bar of 3 - a wrong number on the glass, which is worse than no chart.
        if i + 1 < len(flat) and flat[i] == "point" and flat[i + 1] in _ONES:
            digits, j = "", i + 1
            while j < len(flat) and flat[j] in _ONES and _ONES[flat[j]] < 10:
                digits += str(_ONES[flat[j]])
                j += 1
            if digits:
                value = float("%d.%s" % (int(value), digits))
                i = j
        runs.append({"value": value, "from": start, "to": i, "unit": ""})
    # PASS ONE - the unit that is actually spoken, within two words and never across another run.
    for run in runs:
        for step in range(run["to"], min(len(flat), run["to"] + 3)):
            word = flat[step]
            if word in _SAID_UNITS:
                run["unit"] = _SAID_UNITS[word]
                break
            if word in _ONES or word in _TENS or word in _SCALES:
                break
    # PASS TWO - forward across a range join, then backward after a comparison cue. Forward first,
    # so that "fifty to a hundred dollars, rather than nineteen" can hand $ along the whole chain.
    for n, run in enumerate(runs):
        if run["unit"] or n + 1 >= len(runs) or not runs[n + 1]["unit"]:
            continue
        between = flat[run["to"]:runs[n + 1]["from"]]
        if between and all(w in _RANGE_JOINS for w in between):
            run["unit"] = runs[n + 1]["unit"]
    for n, run in enumerate(runs):
        if run["unit"]:
            continue
        before = flat[max(0, run["from"] - 2):run["from"]]
        if not any(w in _COMPARE_CUES for w in before):
            continue
        for earlier in reversed(runs[:n]):
            if earlier["unit"]:
                run["unit"] = earlier["unit"]
                break
    out, seen = [], set()
    for run in runs:
        val, unit = run["value"], run["unit"]
        if not unit or val <= 0:
            continue
        if unit == "$" and val > 10000000:
            continue
        if unit != "$" and val > 1000:
            continue
        if (unit, val) in seen:
            continue
        seen.add((unit, val))
        label = ("$" + _money(val)) if unit == "$" else (("%g%%" % val) if unit == "%"
                                                        else "%gx" % val)
        out.append({"value": val, "label": label, "unit": unit})
    return out


def _money(val):
    """1000.0 -> 1,000 and 50.0 -> 50. A label, not a format string the caller has to remember."""
    whole = int(round(val))
    if abs(val - whole) > 0.004:
        return "{:,.2f}".format(val)
    return "{:,}".format(whole)


def chart_figures(text, floor=2):
    """The one unit family worth charting out of `text`, or [] - at most four bars.

    ONE FAMILY, THE BIGGEST, AND NEVER FEWER THAN TWO BARS. One bar is not a comparison - it is
    a rectangle with a label, and it says less than the sentence it sits under. Ties break
    towards money because a price is the figure a pricing note is actually about.

    AND THE BARS MUST BE COMPARABLE, which the first real render proved by not being. A pricing
    beat says $19, $50, $100 and $5,000 in one sentence - a seat price three times and an annual
    revenue goal once - and on a shared scale the plate came out as one full-width bar and three
    identical stubs: a chart that shows the viewer nothing except that one number is much bigger,
    which he could hear. So the figures are clustered by MAGNITUDE and the largest comparable run
    wins: the widest span kept is CHART_SPAN to one, ties going to the smaller values, because in
    a pricing note the small comparable numbers are the prices and the outlier is the goal.
    """
    # BOTH READERS, DIGITS FIRST. A note writes "$50" and the narration says "fifty dollars", and
    # the same figure must not become two bars - so the spoken reader's output is merged under the
    # same (unit, value) dedupe the digit reader uses on itself.
    figs, seen = [], set()
    for fig in _numbers_in(text) + _spoken_numbers(text):
        key = (fig["unit"], fig["value"])
        if key in seen:
            continue
        seen.add(key)
        figs.append(fig)
    if not figs:
        return []
    best, order = [], {"$": 3, "x": 2, "%": 1}
    for unit in sorted({f["unit"] for f in figs}, key=lambda u: -order.get(u, 0)):
        family = [f for f in figs if f["unit"] == unit]
        if len(family) > len(best):
            best = family
    if len(best) < floor:
        return []
    # The run is found over the SORTED values and then the original order is restored, because the
    # narration's order is the order the viewer heard the numbers in.
    ladder = sorted(best, key=lambda f: f["value"])
    run = []
    for start in range(len(ladder)):
        low = ladder[start]["value"] or 1.0
        # The ladder is ascending, so this filter is a contiguous run by construction, and only a
        # STRICTLY longer one replaces the incumbent - which is what sends a tie to the lower
        # values, since `start` walks upwards from the smallest.
        span = [f for f in ladder[start:] if (f["value"] / low) <= CHART_SPAN]
        if len(span) > len(run):
            run = span
    keep = [f for f in best if f in run]
    return keep[:4] if len(keep) >= floor else []


# =============================================================================================
#  §36 PART 2 - THE SCENE GRAMMAR, as pure functions
#
#  EVERY DECISION ABOUT WHAT A SCENE SHOWS IS MADE HERE, where it returns a value a harness can
#  read, and never inside the builder that returns an ffmpeg error string. §35 learned this the
#  hard way with beat_rows(): a card that only reports "" or a line of stderr cannot be asked
#  what it put on the glass, so "the whole sentence is on the card" was not a property any proof
#  could check until the arithmetic was lifted out. §36 lifts out the whole grammar.
# =============================================================================================
# The stop list is for SALIENCE and not for language: it exists so that a headline reads
# "Pricing - B2B - Subscriptions" rather than "Because They Accept Without The".
_STOP = frozenset("""
the a an and or but if then than that this these those there here for with without from into
onto upon about above below over under again further once all any both each few more most other
some such only own same so too very can will just should now also its it is are was were be
been being have has had do does did doing of to in on at by as not no nor you your yours i me
my we our us they them their he she his her who whom which what when where why how rather
instead while which because since although though per via they're dont don't cant can't
""".split())

# WHAT MAKES A BEAT A CODE BEAT. Names, not a guess at syntax: the house knows a small set of
# APIs by name and draws the SHAPE of the one the narration mentions. Nothing here invents
# behaviour - every line is the signature as the library documents it, and the card says so in a
# dim footer, because a code card that implied it had been copied out of the boss's notes would
# be the same offence as a chart of a number nobody said.
CODE_SHAPES = {
    "useeffect": ("useEffect", [
        "useEffect(() => {",
        "  const id = subscribe(source)",
        "  return () => unsubscribe(id)",
        "}, [source])",
    ]),
    "usestate": ("useState", [
        "const [value, setValue] =",
        "  useState(initial)",
        "setValue(next)",
    ]),
    "usereducer": ("useReducer", [
        "const [state, dispatch] =",
        "  useReducer(reducer, initial)",
        "dispatch({ type: \"added\" })",
    ]),
    "usememo": ("useMemo", [
        "const total = useMemo(",
        "  () => rows.reduce(sum, 0),",
        "  [rows])",
    ]),
    "usecallback": ("useCallback", [
        "const onPick = useCallback(",
        "  (id) => select(id),",
        "  [select])",
    ]),
    "useref": ("useRef", [
        "const box = useRef(null)",
        "<div ref={box} />",
        "box.current.focus()",
    ]),
    "forwardref": ("forwardRef", [
        "// React 19: no wrapper needed",
        "function Field({ ref, ...rest }) {",
        "  return <input ref={ref} />",
        "}",
    ]),
    "usecontext": ("useContext", [
        "const theme =",
        "  useContext(ThemeContext)",
    ]),
}
# A hook this file has no shape for is still a CODE beat if the narration names one - the card
# then shows the identifier and the sentence's own keywords, and never a fabricated signature.
_HOOK_RE = re.compile(r"\buse[A-Z][A-Za-z0-9]+\b")
_CODE_WORDS = ("hook", "hooks", "api", "component", "boilerplate", "function", "callback",
               "endpoint", "library", "framework", "dependency", "render", "props", "state")
_FLOW_WORDS = ("then", "before", "after", "rather than", "instead of", "next", "first",
               "finally", "launch", "validate", "iterate", "refine", "pipeline", "step",
               "from", "towards", "toward", "pushing")


def _words(text):
    """Content tokens, lowercased, in order, with the stop list and the short words removed."""
    out = []
    for raw in re.split(r"[^A-Za-z0-9$%.\-]+", str(text or "")):
        word = raw.strip(".-").lower()
        if len(word) < 3 or word in _STOP or word.isdigit():
            continue
        out.append(word)
    return out


_FIG_TOKEN = re.compile(r"^[$£€]?[0-9][0-9.,]*[%kmx]?$", re.I)


def duplication(card_text, caption_text):
    """§36's no-duplication measure: the share of the SPOKEN SENTENCE reprinted on the card.

    THE DENOMINATOR IS THE CAPTION AND NOT THE UNION OF THE TWO BAGS, and that is a correction
    with a measurement behind it. Over the union, the label "Founders · Nineteen · Dollars"
    against its own fifteen-word sentence reads 0.50 while §35's whole-sentence card reads 1.00 -
    so the union punishes a card for being SHORT, which is the exact opposite of what §36 asks
    for, and a three-word title would have failed the law written to require it. Over the caption
    the same label reads 0.27, §35's card still reads 1.00, and the number now means something a
    person can check: how much of what the voice is saying is also printed as prose on the glass.

    FIGURES ARE NOT PROSE, and are excluded from both bags. A bar labelled $50 under a voice
    saying fifty dollars is the chart §36 names first, not a duplicated caption; counting the
    label as a reprinted word would have made the mandated scene type the hardest one to pass.
    """
    keep = lambda bag: {w for w in bag if not _FIG_TOKEN.match(w)}    # noqa: E731
    a, b = keep(_words(card_text)), keep(_words(caption_text))
    if not a or not b:
        return 0.0
    return round(len(a & b) / float(len(b)), 3)


def shared_budget(caption_text):
    """How many of a sentence's own content words a card may reprint and still clear DUP_MAX.

    THE LAW IS ENFORCED IN THE GENERATOR AND MEASURED IN THE RENDERER, rather than asserted and
    hoped for. A six-word sentence cannot carry a five-word label without reprinting most of
    itself, so the label SHRINKS WITH THE SENTENCE: the budget is the largest count that still
    clears DUP_MAX, and every card builder takes its element count from it.

    Counted down in a loop rather than solved, because the arithmetic has an edge - at ten
    content words 0.40 x 10 is exactly 4 and 4/10 is not strictly under 0.40 - and a loop over a
    bag of at most thirty words is obviously right where a ceiling-minus-one is not.
    """
    total = len({w for w in _words(caption_text) if not _FIG_TOKEN.match(w)})
    if total <= 1:
        return 1
    count = total
    while count > 1 and count / float(total) >= DUP_MAX:
        count -= 1
    return count


def keywords_in(text, limit=4):
    """The most load-bearing words of a sentence, in the order it says them.

    LONGEST-FIRST AND THEN RE-ORDERED, which is cruder than a part-of-speech tagger and is the
    whole of what is available: no new vendors, and the house has no tagger. Length is a decent
    proxy for specificity in English prose - "subscriptions" outranks "accept" - and the
    re-ordering matters because a chip row that reads in the sentence's own order reads as a
    summary, while one sorted by length reads as a word cloud.
    """
    # THE ORIGINAL SPELLING IS CARRIED BACK, because _words() lowercases and a card that printed
    # "Useeffect" over a voice saying useEffect reads as a typo in the house's own name for things.
    surface = {}
    for raw in re.split(r"[^A-Za-z0-9$%.\-]+", str(text or "")):
        key = raw.strip(".-").lower()
        if key and key not in surface:
            surface[key] = raw.strip(".-")
    seen, ranked, weak = [], [], []
    for word in _words(text):
        stem = word[:6]
        if stem in seen:
            continue
        seen.append(stem)
        # ADVERBS GO LAST, because length is a proxy for specificity and a bad one at the top of
        # the scale: "significantly" is the longest word in its sentence and says nothing about
        # what the sentence is about, and the first chart plate carried the headline
        # "Significantly · High-ticket · Objectives" to prove it. They are demoted and not dropped
        # - a sentence whose only long words are adverbs still needs a label.
        (weak if word.endswith("ly") and len(word) > 5 else ranked).append(word)
    ranked = ranked + weak
    picked = sorted(sorted(ranked, key=lambda w: (w in weak, -len(w)))[:limit], key=ranked.index)
    return [surface.get(w, w).strip("$%") or surface.get(w, w) for w in picked]


def _cap(word):
    """Title-case a keyword, unless it carries its own capitals already: useEffect, not UseEffect."""
    word = str(word or "")
    if any(c.isupper() for c in word[1:]):
        return word
    return word[:1].upper() + word[1:]


def headline_of(text, words=HEADLINE_WORDS, keys=3):
    """A card headline of at most `words` words - a LABEL for the beat, never the beat.

    IT IS BUILT FROM KEYWORDS AND NOT FROM THE SENTENCE'S FIRST CLAUSE, and the reason is the
    law it has to satisfy. A first clause is the caption's own opening words, so it duplicates
    them by construction and reads as a truncated sentence on the glass - which is §35's defect
    with fewer characters. Three keywords joined by a middot read as a title instead, and they
    land near 0.21 on duplication() against a fourteen-token caption.

    `keys` is capped by the caller against shared_budget(): a short sentence gets a two-word
    title rather than a title that reprints half of it.
    """
    picked = keywords_in(text, max(1, keys))
    if not picked:
        return "In your notes"
    out = " · ".join(_cap(w) for w in picked)
    return " ".join(out.split()[:words])


def topic_head(topic, words=HEADLINE_WORDS):
    """The video's own topic as a card headline. THE STRUCTURAL TYPES' LABEL, and here is why.

    A flow diagram and a bullet stack are the two scene types whose VISUAL is made of the
    sentence's own words - three boxes and four bullets are already four to eight content words on
    the glass - and a keyword headline above them spends the duplication budget twice over on the
    same words. Measured: with a keyword headline, every flow and every list beat in a five-beat
    script degraded to a chips card, which is §36 losing two of its five scene types to the law
    that was written to produce them.

    The topic is a label the whole video shares, it is what the boss asked for in his own words,
    and it contributes almost nothing to the shared-token count - so the budget goes where it
    belongs: on the boxes and the bullets, which are the visual.
    """
    said = re.sub(r"\s+", " ", str(topic or "")).strip()
    if not said:
        return ""
    out = " ".join(_cap(w) for w in said.split()[:words])
    return out[:46]


_BULLET_LEAD = re.compile(r"^(?:and|or|then|also|plus|but|so|which|that)\s+", re.I)


def _bullet_item(part):
    """One whole list item, verbatim, or "" if it is not one. §38: NEVER A FIRST WORD.

    The item is the author's own words in the author's own order - a leading conjunction peeled
    off the front, the punctuation that joined it to the next item taken off the back, and the
    first letter raised because it is now the start of a line. Nothing else is touched: no
    keyword reduction, no truncation, no re-ordering.
    """
    said = re.sub(r"\s+", " ", str(part or "")).strip()
    said = said.strip("-–—·•").strip()
    said = _BULLET_LEAD.sub("", said).strip().rstrip(".,;:!?").strip()
    words = said.split()
    if not (BULLET_MIN_WORDS <= len(words) <= BULLET_MAX_WORDS):
        return ""
    if not re.search(r"[A-Za-z]{3}", said):
        return ""
    return said[0].upper() + said[1:]


def bullets_of(text, limit=4, keys=2):
    """2 to 4 WHOLE list items out of one sentence's own list, or [] if it has none.

    §38, FROM THE FRAMES: THE LIST rendered "Say" and "Entire" - two single words, one per row,
    on a card captioned with a whole sentence. The cause is in the function this replaces: it
    reduced each clause to two keywords, and then, whenever the resulting label ran past 26
    characters, replaced the label with its FIRST KEYWORD ALONE. That last line is the defect.
    A one-word bullet is not a shortened bullet, it is a different thing wearing a bullet's
    bullet point, and it tells the viewer nothing the caption underneath is not already saying
    better.

    SO A BULLET IS NOW A WHOLE ITEM OR THERE IS NO LIST. Three words is the floor and seven the
    ceiling - seven words of 36px type is 1000px, which is the card's own width, so the ceiling
    is the glass and not a preference. An item that cannot clear the floor is not shortened and
    it is not padded: the WHOLE list is refused, the function returns [], and card_plan() draws
    the beat as a headline and keyword chips instead.

    THAT REFUSAL IS THE DESIGN AND NOT A GIVING-UP, because the two cases are genuinely two
    different visuals. "Handles authentication, payments, and email" has one- and two-word items
    - those are CHIPS, and chips_scene draws exactly that, as pills in rows. "Validate the idea
    first, then launch the product and refine the pricing" has three-word phrases - that is a
    LIST, and the stack with grown dots draws it. The old code forced every list-shaped sentence
    into the stack and shaved it until it fitted; the shaving is what the boss saw.

    A SEMICOLON LIST COUNTS, which is the mandate's "whole short sentences": a sentence built as
    "first you gather the notes; then you write the script" is a list whose separator happens to
    be a semicolon, and there is no reading on which those clauses are not its items.

    `keys` SURVIVES AS THE NARROWING LEVER AND NO LONGER MEANS KEYWORDS. card_plan() measures
    two widths of every structural card and takes the cheapest that clears the law (see its
    comment); for a list the only honest narrowing left is FEWER ITEMS, because narrowing the
    items themselves is the defect this function exists to remove.
    """
    said = re.sub(r"\s+", " ", str(text or "")).strip()
    chunk = ""
    for part in re.split(r"(?<=[:;])\s+", said):
        if part.count(",") >= 1:
            chunk = part
            break
    if chunk:
        parts = re.split(r",\s*(?:and\s+|or\s+)?|\s+and\s+", chunk)
    elif said.count(";") >= 1:
        parts = said.split(";")
    else:
        return []
    parts = [p for p in parts if p.strip()]
    # THE STEM IS NOT AN ITEM. "A good launch checklist covers writing the landing page, wiring
    # the payment flow, and emailing the first hundred users" splits into an eight-word first
    # part that is the sentence's lead-in welded to its first item, and two clean items after it.
    # The lead-in is DROPPED WHOLE rather than cut back to its tail, because its tail is a
    # fragment and fragments are what this function exists to stop printing; what the lead-in
    # said is what the headline is for. Only the first part may go this way - a long part in the
    # MIDDLE of a list is a list whose items do not fit, and that is a chips beat.
    if len(parts) > 2 and len(parts[0].split()) > BULLET_MAX_WORDS:
        parts = parts[1:]
    out = []
    for part in parts:
        item = _bullet_item(part)
        if not item:
            return []                 # one unusable item refuses the list - see the docstring
        if item.lower() not in [o.lower() for o in out]:
            out.append(item)
    if len(out) < 2:
        return []
    out = out[:(limit if keys >= 2 else 2)]
    # AND THE CARD MAY CARRY THE LIST BUT NEVER THE SENTENCE - see BULLET_KEEP_WORDS. A sentence
    # that is nothing more than its own list has no list card: three items that print all eight
    # of its content words are §35's whole-sentence card with dots beside it.
    said_bag, printed = set(_words(said)), set(_words(" ".join(out)))
    if len(said_bag - printed) < BULLET_KEEP_WORDS:
        return []
    return out


def flow_of(text, limit=4, keys=2):
    """2 to 4 flow boxes out of a sentence that describes a movement, or [].

    THE ARROW IS THE CLAIM, so the boxes have to be the two sides of one: "price at $19" ->
    "price at $50-$100", "useEffect" -> "TanStack Query". The split points are the words a
    sentence uses to say "not this but that" or "this then that", which is also what makes the
    diagram honest - the order on the glass is the order the voice says them in.
    """
    said = re.sub(r"\s+", " ", str(text or ""))
    parts = re.split(r"\s+(?:rather than|instead of|then|and then|before|after|towards?|"
                     r"pushing|into|to)\s+", said, flags=re.I)
    boxes = []
    for part in parts:
        words = keywords_in(part, max(1, keys))
        if words:
            # NARROWED BY DROPPING A WORD, NEVER BY SLICING CHARACTERS. The first flow plate read
            # "Technical Authenticati" in one box and "Validate Revenue-gener" in the next, because
            # a 22-character slice cuts mid-word; one keyword is a label and half a word is a bug.
            label = " ".join(_cap(w) for w in words)
            boxes.append(label if len(label) <= 20 else _cap(words[0]))
    seen, out = set(), []
    for box in boxes:
        if box.lower() in seen:
            continue
        seen.add(box.lower())
        out.append(box)
    return out[:limit] if len(out) >= 2 else []


def code_of(text):
    """(api, lines) for a code beat, or ("", []) - the shape of the API the narration names."""
    said = str(text or "")
    for m in _HOOK_RE.finditer(said) or []:
        shape = CODE_SHAPES.get(m.group(0).lower())
        if shape:
            return shape[0], list(shape[1])
    for key, shape in CODE_SHAPES.items():
        if re.search(r"\b%s\b" % re.escape(key), said, re.I):
            return shape[0], list(shape[1])
    m = _HOOK_RE.search(said)
    if m:
        # NAMED BUT NOT KNOWN: the identifier goes on the card and no signature is drawn under
        # it, because the alternative is inventing one.
        return m.group(0), []
    return "", []


def classify_beat(text, topic=""):
    """Every scene type this beat COULD be drawn as, best first. Pure, and the spine of §36.

    Returned as a list rather than one answer so that classify_all() can keep a video from
    becoming four of the same card - which is a director's decision and not a classifier's.
    """
    out = []
    api, lines = code_of(text)
    if api and lines:
        out.append("code")
    if chart_figures(text):
        out.append("chart")
    if api and not lines:
        out.append("code")
    said = str(text or "")
    if flow_of(said) and any(w in said.lower() for w in _FLOW_WORDS):
        out.append("flow")
    if bullets_of(said):
        out.append("bullets")
    # A TECH BEAT WITH NO IDENTIFIER IN IT IS NOT A CODE BEAT - _CODE_WORDS ("hook", "api",
    # "props") says the sentence is ABOUT code, and there is still nothing to type on the glass.
    # It falls through to chips, and the proof says so rather than letting the house pretend it
    # found code it did not find.
    out.append("chips")
    seen, ordered = set(), []
    for kind in out:
        if kind in seen:
            continue
        seen.add(kind)
        # A CANDIDATE THAT CANNOT KEEP THE DUPLICATION LAW IS NOT A CANDIDATE. card_plan() returns
        # the type it would actually have to draw, so a flow diagram whose boxes would reprint half
        # the sentence is filtered out HERE - which matters because classify_all() then enforces
        # variety over types that are really available. Filtering afterwards let the director
        # choose a type for variety and the renderer silently draw a different one.
        if kind == "chips" or card_plan(kind, text, topic)[0] == kind:
            ordered.append(kind)
    return ordered


SCENE_KINDS = ("hook", "chart", "code", "flow", "bullets", "chips", "cta")
SAME_KIND_MAX = 2
# §36's VARIETY LAW, as numbers the proof can read instead of two literals in a harness: a film of
# VARIETY_BEATS beats or more wants VARIETY_MIN distinct scene types. It is a want and not a
# guarantee - see the second pass in classify_all() for how far the director can honour it.
VARIETY_BEATS = 4
VARIETY_MIN = 3


def classify_all(beats, topic=""):
    """One scene type per beat, with VARIETY ENFORCED. The list the ledger row carries.

    §36 asks for at least three distinct scene types in any video of four beats or more, and a
    classifier alone cannot promise that: five pricing sentences are five number beats, and five
    bar charts in a row is the slideshow again with bars on it. So a type that has already been
    used SAME_KIND_MAX times steps aside for the next candidate the beat qualifies for - the
    editorial rule a human cutting this would apply, applied deterministically so the proof can
    reproduce it.

    §38 ADDED A SECOND PASS, because stepping aside needs somewhere to step and the single greedy
    pass could WALK PAST A TYPE THAT WAS AVAILABLE. Measured on this round's pricing render: five
    beats offering chart, flow and chips between them were drawn as chart · chart · chips · chips ·
    chips - two distinct types where three were on the table. The cause is that the first pass
    takes each beat's best candidate the moment it is under the cap, so a beat qualifying for both
    chart and flow spends the chart it shares with its neighbours and the flow nobody else can
    draw is never reached. The repair is a reassignment rather than a re-ranking: while the film is
    short of VARIETY_MIN, each undrawn type in SCENE_KINDS order takes the FIRST beat that
    qualifies for it AND currently holds a type drawn more than once - first-fit in beat order, so
    the result is reproducible from the beat list alone, and never at the cost of a type's only
    instance. It cannot invent variety: a script of plain prose sentences still comes back as one
    repeated type, which is the honest answer and what director_proof's prose fixture asserts.
    """
    options = [classify_beat(beat, topic) for beat in beats]
    counts, out = {}, []
    for opts in options:
        pick = next((k for k in opts if counts.get(k, 0) < SAME_KIND_MAX), opts[-1])
        counts[pick] = counts.get(pick, 0) + 1
        out.append(pick)
    if len(out) >= VARIETY_BEATS:
        for kind in SCENE_KINDS:
            if len(set(out)) >= VARIETY_MIN:
                break
            if kind in out:
                continue
            for i, opts in enumerate(options):
                if kind in opts and counts.get(out[i], 0) > 1:
                    counts[out[i]] -= 1
                    counts[kind] = counts.get(kind, 0) + 1
                    out[i] = kind
                    break
    return out


def _semicolon_split(parts):
    """§38: a too-long sentence joined by SEMICOLONS becomes its own independent clauses.

    WHY THIS EXISTS, MEASURED. The two highest-scoring react notes on "explain useEffect in
    react" - 0.778 and 0.743 - carry their best claims in 37- and 51-word sentences, and the
    >32-word rule below dropped both OUTRIGHT. That left the composer with one candidate per
    note and sent it hunting a third beat down the ranking, where it found a chunk from a
    different document about this house's screen-share picker and narrated it over a video about
    a hook. So the off-topic beat had two causes and this is the upstream one: the topic's best
    material was unusable and something had to fill the slot.

    ONLY THE SEMICOLON, and only because a semicolon is already a declaration by the author that
    what sits either side of it stands alone - which is the exact property a comma does not have.
    The second half is capitalised and given a terminal stop, so it is a sentence in writing as
    well as in grammar; both halves then face every rule below unchanged, including the word
    ceiling, so a 51-word clause pair that splits into 40 and 11 still loses the 40. Nothing is
    cut: a clause that fails is dropped exactly as the whole sentence used to be.

    AND THE PARENT MUST ITSELF LOOK LIKE A SENTENCE. The capital-letter test below is the chunk
    boundary guard, and capitalising my own halves would launder a mid-clause fragment straight
    past it - so a parent that would have failed that test is not split at all.
    """
    out = []
    for part in parts:
        part = (part or "").strip()
        if len(part.split()) <= 32 or ";" not in part:
            out.append(part)
            continue
        if not re.match(r'^["\']?[A-Z0-9$]', part):
            out.append(part)                      # let the guard below drop it, as before
            continue
        halves = []
        for clause in part.split(";"):
            clause = clause.strip().strip(",").strip()
            if len(clause.split()) < 5:           # a trailing "and so on" is not a clause
                halves = []
                break
            if not re.search(r"[.!?][\"')\]]?$", clause):
                clause += "."
            halves.append(clause[0].upper() + clause[1:])
        out.extend(halves or [part])
    return out


def _sentences(text):
    """Narratable sentences out of a retrieved chunk. Three repairs, each for a seen defect.

    THE SCHOLAR'S HEADER IS NOT PROSE. Every auto-studied chunk begins "<Title> - auto-studied "
    and then the first sentence, with no full stop between them - so a naive sentence split
    returns the note's own filing header welded to its opening claim, and the voice reads
    "Micro-Saas - auto-studied Target B2B customers" aloud as though it were a sentence. It is
    stripped by its marker rather than by position, so a note without one is untouched.

    TYPOGRAPHY IS FLATTENED TO ASCII, and the reason is narrower than it looks. A note holds
    "$200–$300" with a real EN DASH - this console renders it as a box, which is cp1252 lying
    about a correct note and not a corrupt one, so there is nothing here to repair. It is
    flattened anyway because the consumer is a SPEECH SYNTHESISER: a dash between two figures
    is a range the voice should read as one, and the ASCII hyphen is the form piper was trained
    on. The fonts would have drawn either.

    URLS AND SOURCE LISTS ARE NOT NARRATION. The Scholar's notes end with the pages they were
    built from, and a sentence split returns that block as a sentence - so without this the
    voice reads "Sources https://www.microsaasideas.net/handbook/pricing-strategies" aloud,
    character by character, and it is burned into a caption as well.

    AND A SENTENCE TOO LONG TO NARRATE IS DROPPED, NOT CUT. Chopping at a word count produced
    "...allowing you to reach $10k MRR with fewer." - a fragment that reads as a complete
    sentence and is not one, which is the same defect class as the model's mid-word truncation
    and is worse for being self-inflicted. A clause boundary is tried first; failing that the
    sentence is skipped, because there are five retrieved notes and no shortage of candidates.
    """
    said = str(text or "")
    for a, b in (("–", "-"), ("—", "-"), ("‘", "'"), ("’", "'"),
                 ("“", '"'), ("”", '"'), ("…", "..."), ("�", ""),
                 # THE LIGATURES ARE SINGLE CODEPOINTS OUT OF THE PDF NOTES. A pdf-kind chunk
                 # holds "speciﬁc" as one character, which piper cannot pronounce and libass
                 # may not have a glyph for - so a caption would carry a blank box where the
                 # voice said nothing.
                 ("ﬁ", "fi"), ("ﬂ", "fl"), ("ﬀ", "ff"), ("ﬃ", "ffi"), ("ﬄ", "ffl")):
        said = said.replace(a, b)
    said = re.sub(r"\s+", " ", re.sub(r"[#*`>\[\]()]", " ", said)).strip()
    said = re.sub(r"^.{0,60}?\s-\s*auto-studied\s+", "", said)
    out = []
    for part in _semicolon_split(re.split(r"(?<=[.!?])\s+", said)):
        part = part.strip()
        if len(part) <= 25:
            continue
        if "http" in part or "www." in part or re.match(r"^sources?\b", part, re.I):
            continue
        # A SENTENCE THAT DOES NOT BEGIN LIKE ONE IS A CHUNK BOUNDARY, NOT A SENTENCE. Retrieval
        # returns a window into a document, so the first "sentence" of a chunk routinely starts
        # mid-clause - "is page content, so scrolling reads as change." - and it is indetectable
        # downstream because it ends in a full stop like any other. Requiring a capital or a
        # digit at the front costs one legitimate sentence in a thousand and removes the whole
        # class.
        if not re.match(r'^["\']?[A-Z0-9$]', part):
            continue
        if len(part.split()) > 32:
            # DROPPED OUTRIGHT, AND NOT CUT AT A CLAUSE BOUNDARY. Cutting was tried and it
            # fabricated its own fragments: trimming at the last comma inside the limit turned
            # "...applies them to specific, underserved niches." into "...applies them to
            # specific." - a fragment that ends in a full stop and so cannot be told from a
            # sentence by anything downstream. There is no shortage of candidates across five
            # retrieved notes, so the sentence that will not fit is simply not used. Every
            # surviving beat is a sentence somebody actually wrote.
            continue
        out.append(part)
    return out


def compose_script(topic, hits, want_words):
    """Beats from the retrieved note text, deterministically. The fallback, and the floor.

    WHY A DETERMINISTIC COMPOSER EXISTS AT ALL when the house has a model: because this is the
    stage that decides whether an mp4 appears, and a render that depended on a cloud round trip
    would fail as "no video" on a dropped connection. The model improves the prose when it is
    reachable - see write_script() - and this guarantees there IS prose. It also makes
    director_proof's fixed run repeatable, which an assertion about a 45-to-60-second script
    needs.
    """
    beats, used, spent, taken = [], [], 0, []
    for hit in hits:
        if len(beats) >= BEATS_MAX or spent >= want_words:
            break
        # ONE BEAT PER NOTE, AND IT IS THE LEAST REPETITIVE SENTENCE THE NOTE HAS.
        #
        # The defect this replaces was real and the two heuristics tried before it both failed
        # honestly. The Scholar studies a topic more than once, so the top five hits on
        # "micro-saas pricing" are three notes that open with the SAME claim in different words,
        # and taking sentences in document order produced a script whose beats 1, 2 and 3 all
        # said "target B2B customers at $200-$300". A first-six-words key missed it. So did word
        # overlap: "Target B2B customers for niche micro-SaaS because they accept $200-$300
        # monthly subscriptions" against "Target B2B customers with flat-rate subscriptions of
        # $200-$300/month" shares six content words out of twenty-nine and scores 0.24, which no
        # safe threshold catches - they are the same POINT and not the same WORDS, and lexical
        # similarity cannot see that difference. A threshold low enough to catch it would start
        # discarding genuinely distinct sentences about one topic.
        #
        # So the cause is addressed instead of the symptom, twice over. One beat per note means
        # a restated lede can only be chosen once however many notes repeat it - and it makes
        # every cited id a note that contributed a sentence, which is the only honest reading of
        # §35's "citing note ids". Choosing each note's LEAST overlapping sentence then spends
        # the duplicated notes on what they say that the others do not: note two's lede loses to
        # note one's, so note two offers its "smart copy" paragraph instead. Containment rather
        # than Jaccard, because the question is whether this sentence is already COVERED, and a
        # short restatement of a long accepted beat has high containment and low Jaccard.
        best, best_score = "", 2.0
        for line in _sentences(hit.get("text") or ""):
            bag = {w.strip(".,;:\"'!?").lower() for w in line.split() if len(w) > 3}
            if not bag:
                continue
            score = max([len(bag & old) / float(len(bag)) for old in taken] or [0.0])
            if score < best_score:
                best, best_score, best_bag = line, score, bag
        # 0.6 CONTAINMENT IS A NEAR-VERBATIM REPEAT, not a paraphrase - it is the one thing this
        # test can judge reliably, so it is the only thing it is asked to judge. A note whose
        # every sentence is already covered contributes nothing and is not cited.
        if not best or best_score > 0.6:
            continue
        taken.append(best_bag)
        beats.append(best)
        spent += len(best.split())
        if hit.get("id") and hit["id"] not in used:
            used.append(hit["id"])
    return beats, used


def write_script(topic, hits, want_words):
    """(beats, cited, source) - the model's version if it is reachable, the composer's if not.

    THE CITATIONS ARE NOT THE MODEL'S TO CHOOSE. They are the ids of the notes that were
    actually retrieved and handed to it, which is the only version of "citing note ids" that
    means anything: a model asked to cite its sources will cite plausibly, and a plausible
    citation is worse than none because it survives being read.
    """
    base, cited = compose_script(topic, hits, want_words)
    if not base:
        return [], [], "none"
    corpus = "\n\n".join(("- " + re.sub(r"\s+", " ", (h.get("text") or ""))[:700])
                         for h in hits[:5])
    # IT IS ASKED FOR MORE SENTENCES THAN THE VIDEO WILL USE, and that is the fix for a measured
    # failure rather than padding. The dispatcher has a token ceiling this prompt cannot raise,
    # so a request for 142 words comes back cut mid-word every time; the truncation guard below
    # then correctly discards the broken tail, and the model path landed on three sentences and a
    # 31-second voiceover - under a floor that asserts 40. Asking for BEATS_MAX + 2 means the
    # sentence lost to the ceiling is a sentence that was surplus to begin with.
    # AND THE LENGTH IT ASKS FOR IS NOW REACHABLE, which is §38's finding and not a style note.
    # The old ask said "short" and "under 28 words", the model obliged with 12-word sentences,
    # and the floor below demands 108 words of the FIVE that survive truncation - 21.6 words
    # each. So every model draft failed a test it had been instructed to fail, both regression
    # videos shipped "prose by notes", and the composer's note-lifted sentences - one of which
    # was the share-picker passenger - were the only prose this house had ever rendered.
    # Measured on the useEffect draft under the old wording: 7 sentences, 65 words over the five
    # that survive, against a floor of 108.
    #
    # "ABOUT 24 WORDS EACH" AND NOT "BETWEEN 20 AND 28 WORDS", and the reason is the dispatcher
    # rather than the prose. This house's chat provider is Opus 5 on Bedrock with extended
    # thinking on, and MAX_ANSWER_TOKENS is 400 for every answer the butler gives - a ceiling
    # the whole reply shares with its own reasoning. A two-ended range is a constraint the model
    # verifies sentence by sentence before answering, and measured, it spent the entire 400 on
    # reasoningContent and came back with NO TEXT BLOCK AT ALL: `output.message.content` held one
    # reasoning block and nothing else, which this server reads - correctly - as "Bedrock
    # returned an empty answer", and which would have pinned the model path permanently shut.
    # One number to aim at costs almost no reasoning. Measured over four calls, two topics:
    # 118, 126, 127 and 134 words over the first five sentences, every one clearing the floor,
    # against 0 words on all three runs of the range wording.
    ask = [
        {"role": "system",
         "content": ("You are writing the narration for a short explainer video, to be read "
                     "aloud by a single voice. Use ONLY the notes provided; invent no facts, "
                     "no statistics and no examples that are not in them. Write %d spoken "
                     "sentences of about 24 words each, one per line. Every sentence must be "
                     "about the topic itself; ignore any note that is about something else. No "
                     "bullets, no headings, no stage directions, no numbering, no markdown. "
                     "Plain spoken English. Do not mention notes, sources, documents or videos. "
                     "Begin with the first sentence of narration and nothing else."
                     % (BEATS_MAX + 2))},
        {"role": "user",
         "content": "Topic: %s\n\nThe notes:\n%s" % (topic, corpus)},
    ]
    try:
        import server                                              # see the header's note
        answer, error = server.call_model(server.load_config()[0], ask)
    except Exception as exc:                                       # noqa: BLE001
        answer, error = "", str(exc)[:120]
    if error or not answer:
        return base, cited, "notes"
    lines = []
    for raw in str(answer).splitlines():
        line = re.sub(r"^\s*(?:[-*\u2022]|\d+[.)])\s*", "", raw).strip().strip('"')
        # A MODEL THAT ANSWERED WITH A HEADING STILL GETS ITS SENTENCES USED. Anything short
        # enough to be a label rather than a sentence is dropped, which also removes the
        # "Here is the narration:" preamble without having to anticipate its wording.
        if len(line.split()) >= 5 and not line.endswith(":"):
            lines.append(line)
    # A TRAILING SENTENCE THAT DOES NOT END IS A TRUNCATION, AND IT IS DROPPED. The dispatcher
    # has a token ceiling, and the observed failure is a final line cut mid-WORD - "treat the
    # price itself as an experi" - which a return code cannot see. Narrated it is audibly
    # broken, and burned into a caption it is broken in writing too, so the half-sentence goes
    # even though it cost tokens. Only the LAST line is tested: an interior line without a full
    # stop is a style, but the last one is the ceiling.
    while lines and not re.search(r"[.!?][\"')\]]?$", lines[-1]):
        lines.pop()
    lines = lines[:BEATS_MAX]
    # AND THE MODEL'S VERSION HAS TO CLEAR THE FLOOR, IN WORDS, BEFORE A SINGLE ONE IS SPOKEN.
    # The old test asked for 80 words, which is about 33 seconds of ryan-high and so passed a
    # script that could not reach the 40-second floor it was going to be measured against. The
    # number is now derived from the floor itself at the measured rate, with a margin, so the two
    # cannot drift apart: a model answer that cannot clear it is a failed instruction rather than
    # a short script, and the composer's version - which reliably runs long - is used instead.
    floor_words = int(VOICE_MIN_S * WORDS_PER_S) + 10
    if len(lines) < 4 or sum(len(l.split()) for l in lines) < floor_words:
        return base, cited, "notes"
    # THE MODEL PATH CITES WHAT THE MODEL WAS SHOWN, which is hits[:5] and not the composer's
    # selection. The composer cites only the notes it took a sentence from, because that is what
    # IT used; the model read all five, so all five are its sources. Each path reports its own
    # truth rather than sharing one list that is right for only one of them.
    return lines, [h["id"] for h in hits[:5] if h.get("id")], "model"


# =============================================================================================
#  §38 PART 1 - THE TOPIC GUARD
#  Two readers, and the order matters. The notes are tiered BEFORE the draft, so the writer -
#  model or composer - never sees the passenger and never cites it; the beats are then read again
#  AFTER the draft, because a writer handed five on-topic notes can still wander. The second
#  reader is a model where one is reachable and a lexical count where one is not, and the count
#  runs either way: a guard that only works when the cloud answers is not a guard.
# =============================================================================================
def note_tier(topic, hits):
    """(kept, dropped) - the retrieved notes close enough to the best hit to be about the topic.

    RETRIEVAL ALREADY KNEW, AND NOBODY ASKED IT. The share-picker sentence came out of a chunk
    that scored 0.568 on "explain useEffect in react" while the four react notes scored 0.778,
    0.743, 0.675 and 0.673 - it was the fifth of five, 0.210 below the best, and every stage
    downstream treated it as an equal. ingest.recall()'s own gate had admitted it correctly: it
    IS related to a house that answers questions about screen sharing. It is not related to the
    HOOK.

    THE FLOOR IS RELATIVE TO THE BEST HIT, because an absolute one is a different number for
    every topic and every embedding: "micro-saas pricing" returns ten chunks from 0.835 to
    0.759, and any absolute floor that dropped the useEffect passenger at 0.568 would either
    keep it or cut into that band. Measured, the two real bands are 0.105 and 0.077 wide and the
    passenger sits at 0.210, so RECALL_GAP = 0.15 passes every note of both topics and drops the
    one chunk that did not belong.

    THE FIRST HIT IS ALWAYS KEPT, even if it is the only one. A topic whose notes disagree with
    each other is a thin topic, which this file reports rather than repairs.
    """
    rows = [h for h in (hits or []) if (h.get("text") or "").strip()]
    if not rows:
        return [], []
    best = max(float(h.get("score") or 0.0) for h in rows)
    kept = [h for h in rows if float(h.get("score") or 0.0) >= best - RECALL_GAP]
    dropped = [h for h in rows if h not in kept]
    return (kept or rows[:1]), dropped


def topic_vocabulary(topic, hits):
    """The words the retrieved set AGREES on, plus the topic's own. The second reader's lexicon.

    AGREEMENT IS THE SIGNAL, not frequency. One note can be about anything; a word that appears
    in TWO of the notes retrieved for a topic is a word that topic is made of. The boss's own
    phrasing is added unconditionally because it is the one description of the subject that is
    not a guess - he typed it.
    """
    counts = {}
    for hit in (hits or []):
        for word in set(_words(hit.get("text") or "")):
            counts[word] = counts.get(word, 0) + 1
    agreed = {w for w, n in counts.items() if n >= TOPIC_NOTES_MIN}
    return agreed | set(_words(topic))


def beat_relevance(beat, vocab):
    """(corroborated, share) - THE NAMED RELEVANCE CHECK the mandate asks every beat to pass.

    Measured over both regression scripts before the floor was chosen. "If I pick a tab in the
    share picker, say so honestly and steer me to share the entire screen" corroborates ZERO
    words of the useEffect lexicon. The weakest sentence that belongs - "Treat pricing as an
    iterative experiment rather than a one-time decision" - corroborates TWO, and everything
    else lands between 0.25 and 0.722 share. So one word is below everything legitimate and
    above nothing, and that is the test.

    THE COUNT IS THE TEST AND THE SHARE IS THE REPORT, deliberately the way round that looks
    less sophisticated. A share floor is gamed by brevity: a four-word beat carrying one topic
    word scores 0.25 and outranks a twenty-word beat carrying four. The share is reported beside
    the count because it is the number a person reads to see HOW on-topic a kept beat was.
    """
    bag = set(_words(beat))
    if not bag:
        return 0, 0.0
    shared = bag & set(vocab or ())
    return len(shared), round(len(shared) / float(len(bag)), 3)


def _grounded(text, corpus_words):
    """Is every content word of this sentence a word the notes or the topic actually used?

    THE ONE GUARD A REWRITE NEEDS. Everything else in this file refuses to invent, and asking a
    model to rewrite narration is the one place that discipline could leak - a fluent rewrite
    that adds a statistic is worse than the off-topic sentence it replaced, because it reads as
    though it came from the boss's own documents. So a rewrite may only RE-ARRANGE: every word
    longer than the stop list's reach must already appear in the notes handed to the writer or
    in the topic. Measured cost: ordinary function words and inflections are below _words()'s
    three-character floor or inside _STOP, so a faithful rewrite passes and an invented figure
    does not.
    """
    bag = set(_words(text))
    return bool(bag) and not (bag - set(corpus_words or ()))


_GUARD_RE = re.compile(r"^\s*(\d+)\s*[.):\-]?\s*(KEEP|DROP|REWRITE)\b\s*[:\-]?\s*(.*)$", re.I)


def topic_guard(topic, beats, hits, report=None):
    """§38: every beat is about the topic, or it is rewritten, or it is not spoken. (beats, log).

    THE MODEL JUDGES AND THE COUNT VETOES, and neither one alone decides. The model is the same
    thinker that wrote the draft, asked a different question - one pass, one verdict per beat -
    because it is the only reader in this house that can tell that a sentence about a share
    picker is off-topic for a React hook when both are software. The lexical count runs on every
    beat regardless of what the model said, or whether it answered at all, so the law holds with
    the network down.

    REWRITE IS PREFERRED OVER DROP and the reason is structural: BEATS_MAX is 5, the voiceover
    floor is 40 seconds, and a dropped beat costs about ten seconds of narration that nothing can
    give back - so a drop can push a legitimate video under its own budget. A rewrite keeps the
    count. It is accepted only if it is grounded in the notes (see _grounded), clears the
    relevance floor itself, and is a sentence by shape; otherwise the ORIGINAL is kept if the
    count says it was fine all along, and only then is the beat dropped.

    WHAT IS NOT DONE HERE: the citation list is not re-derived from the survivors. The notes were
    tiered before the draft, so the ids name an on-topic set either way; a guard drop leaves a
    cited note whose sentence was cut, which is reported in the log rather than papered over.
    """
    rows = [str(b or "").strip() for b in (beats or []) if str(b or "").strip()]
    if not rows:
        return [], []
    vocab = topic_vocabulary(topic, hits)
    corpus = set(vocab) | set(_words(" ".join((h.get("text") or "") for h in (hits or []))))
    verdicts, why = {}, ""
    ask = [
        {"role": "system",
         "content": ("You are checking the narration of a short explainer video, one sentence "
                     "per line, against its stated topic. For each numbered sentence answer on "
                     "its own line with the number and exactly one of: KEEP if the sentence is "
                     "about the topic; REWRITE: <sentence> if it is about something else but "
                     "can be made about the topic using only wording from the notes; DROP if it "
                     "is about something else entirely. Prefer REWRITE over DROP. Invent no "
                     "facts, no statistics and no examples. Answer with the numbered lines and "
                     "nothing else.")},
        {"role": "user",
         "content": "Topic: %s\n\nThe notes:\n%s\n\nThe sentences:\n%s"
                    % (topic,
                       "\n\n".join("- " + re.sub(r"\s+", " ", (h.get("text") or ""))[:700]
                                   for h in (hits or [])[:5]),
                       "\n".join("%d. %s" % (n, r) for n, r in enumerate(rows, start=1)))},
    ]
    try:
        import server                                              # see the header's note
        answer, err = server.call_model(server.load_config()[0], ask)
    except Exception as exc:                                       # noqa: BLE001
        answer, err = "", str(exc)[:120]
    if err or not answer:
        why = err or "no answer"
    else:
        for raw in str(answer).splitlines():
            found = _GUARD_RE.match(raw)
            if not found:
                continue
            n = int(found.group(1))
            if 1 <= n <= len(rows):
                verdicts[n] = (found.group(2).upper(), found.group(3).strip().strip('"'))
    out, log = [], []
    for n, text in enumerate(rows, start=1):
        call, offered = verdicts.get(n, ("", ""))
        words, share = beat_relevance(text, vocab)
        fix, fix_words, fix_share = "", 0, 0.0
        if call == "REWRITE" and offered:
            fix_words, fix_share = beat_relevance(offered, vocab)
            if (10 <= len(offered.split()) <= 32
                    and re.match(r'^["\']?[A-Z0-9$]', offered)
                    and fix_words >= TOPIC_MIN_WORDS
                    and _grounded(offered, corpus)):
                fix = offered if re.search(r"[.!?][\"')\]]?$", offered) else offered + "."
        row = {"n": n, "text": text, "words": words, "share": share,
               "call": call or "unread", "by": "model" if call else "corroboration"}
        if fix:
            out.append(fix)
            row.update({"verdict": "rewritten", "spoken": fix,
                        "words": fix_words, "share": fix_share})
        elif call == "DROP" or words < TOPIC_MIN_WORDS:
            row["verdict"] = "dropped"
            row["by"] = "model" if call == "DROP" else "corroboration"
        else:
            out.append(text)
            row.update({"verdict": "kept", "spoken": text})
        log.append(row)
    if report:
        cut = [r for r in log if r["verdict"] != "kept"]
        report.note("topic guard: %d of %d beats kept%s%s"
                    % (len(out), len(rows),
                       (", " + " · ".join("%d %s by %s" % (r["n"], r["verdict"], r["by"])
                                          for r in cut)) if cut else "",
                       (" (thinker silent: %s)" % why) if why else ""))
    return out, log


def script_markdown(topic, beats, cited, hits, source):
    """output/videos/<slug>/script.md - the thing a human reads to check the machine.

    It carries the note IDS, which is §35's "citing note ids", and the file NAME beside each,
    because an id is checkable and a name is readable and the boss should not have to grep for
    which of his own documents this came out of.
    """
    byid = {h.get("id"): h for h in hits}
    out = ["# %s" % topic, "",
           "_written %s from %d retrieved notes, prose by %s_"
           % (time.strftime("%Y-%m-%d %H:%M"), len(cited), source), "",
           "## Narration", ""]
    for n, line in enumerate(beats, start=1):
        out.append("%d. %s" % (n, line))
    out += ["", "## Cited notes", ""]
    for ident in cited:
        hit = byid.get(ident) or {}
        out.append("- `%s` - %s%s" % (ident, hit.get("name") or hit.get("file") or "?",
                                      (" p%s" % hit["page"]) if hit.get("page") else ""))
    return "\n".join(out) + "\n"


# =============================================================================================
#  STEP 2 - THE VOICEOVER, and the timings that come free with it
# =============================================================================================
def voice_lines(beats, folder, report=None):
    """One WAV per line, and therefore exact per-line timings. Returns (rows, why).

    THE TIMINGS ARE MEASURED AND NOT ESTIMATED, which is the whole reason the voiceover is
    synthesised line by line rather than as one block of text. A caption track built from
    words-per-minute drifts a syllable per sentence and a second by the end, and burned
    captions that drift are worse than no captions: they are visibly wrong for the whole of the
    second half.
    """
    rows, at = [], 0.0
    for n, line in enumerate(beats, start=1):
        wav_bytes, why, _source = say.synthesise(line, say.DEFAULT_MODEL)
        if not wav_bytes:
            return [], "the voice would not speak line %d: %s" % (n, why)
        path = os.path.join(folder, "line%02d.wav" % n)
        with open(path, "wb") as fh:
            fh.write(wav_bytes)
        secs = wav_seconds(path)
        if secs <= 0:
            return [], "line %d synthesised to a WAV with no duration" % n
        rows.append({"n": n, "text": line, "wav": path, "start": round(at, 3),
                     "seconds": secs})
        at += secs
        if report:
            report.note("line %d of %d - %.1fs" % (n, len(beats), secs))
    return rows, ""


def fit_budget(rows):
    """Drop trailing lines until the narration is inside VOICE_MAX_S. Returns (rows, dropped).

    THE BUDGET IS ENFORCED HERE AND AIMED AT EVERYWHERE ELSE, and that division is the point.
    Upstream, words-per-second is an estimate: it varies with the voice, with the model's
    sentence length, and with whether the prose came from the model or the composer, so every
    word-count target can be missed and one of them was - a 77-second voiceover against a
    70-second ceiling. Here the durations are MEASURED, one WAV per line, so the ceiling can be
    made true by subtraction instead of hoped for.

    It trims from the END because the script is written to taper - the first beats carry the
    claim and the last the aside - and because dropping a tail line leaves every surviving
    line's `n` and `start` untouched, so the captions and scenes need no renumbering. It keeps
    three lines whatever happens: a video that trimmed itself down to one sentence should fail
    its own floor loudly rather than ship as a ten-second clip.
    """
    dropped = []
    while len(rows) > 3 and sum(r["seconds"] for r in rows) > VOICE_MAX_S:
        dropped.append(rows.pop())
    return rows, dropped


def timeline(rows, lead=0.0, gap=PAUSE_S):
    """Stamp each row's `start` on the FINISHED audio clock. Returns the rows and the total.

    ONE FUNCTION, BECAUSE THERE IS ONE CLOCK AND THREE READERS. The joined WAV, the caption cues
    and the xfade offsets all have to agree to the frame, and in §35 they agreed by each
    recomputing the same sum from `seconds` plus a hand-passed `offset`. §36 adds a 0.4-second
    pause after every beat, which is a third term in that sum - and a third term is exactly the
    kind of change that makes two of three readers right. So the sum is computed HERE, written
    onto the rows, and everything downstream READS `start` instead of adding anything.

    The pause is real silence between the lines rather than a longer tail on each WAV, so the
    sentence breaks piper already renders are preserved untouched: `voice_lines` measures the
    speech, `timeline` spaces it.
    """
    at = float(lead)
    for row in rows:
        row["start"] = round(at, 3)
        row["slot"] = round(row["seconds"] + gap, 3)
        at += row["seconds"] + gap
    return rows, round(at, 3)


def join_wavs(rows, dest, lead=0.0, tail=0.0, gap=PAUSE_S):
    """One voiceover WAV, concatenated frame-exactly through the wave module.

    NOT THROUGH FFMPEG, and that is deliberate rather than contrary: the per-line WAVs are the
    clock the captions are cut against, so the joined file has to be the arithmetic sum of them
    to the frame. An ffmpeg concat would be correct too and would put a re-encode between the
    measurement and the thing measured, which is one more place for a drift nobody would look
    for.

    LEAD AND TAIL ARE THE SYNC, and they are silence rather than a delay filter for the same
    reason. The title card holds the first three seconds of the picture; without a lead of
    exactly that much silence the narration starts under the TITLE and every beat card arrives
    three seconds after the sentence it displays - which is the defect this argument exists to
    fix, and it is invisible in every duration the pipeline prints. The tail does the same
    service at the other end: -shortest ends the file when the audio stops, so a chart with no
    silence under it is a scene that is encoded, concatenated and then entirely trimmed away.

    GAP IS §36's PAUSE, and it is written here rather than asked of piper. A pause synthesised
    into the text - a trailing full stop, an ellipsis - comes out a different length every line
    and is not measurable afterwards; written as frames of zero it is exactly PAUSE_S on every
    line, which is what lets timeline(), the cues and the xfade offsets share one arithmetic.

    Silence is written as zero frames, which is only true silence for signed PCM - piper's
    output is 16-bit signed, and sampwidth is read from the file rather than assumed.
    """
    try:
        with wave.open(rows[0]["wav"], "rb") as first:
            params = first.getparams()
        quiet = params.nchannels * params.sampwidth
        hush = lambda secs: b"\x00" * (int(params.framerate * secs) * quiet)   # noqa: E731
        with wave.open(dest, "wb") as out:
            out.setparams(params)
            if lead > 0:
                out.writeframes(hush(lead))
            for row in rows:
                with wave.open(row["wav"], "rb") as fh:
                    out.writeframes(fh.readframes(fh.getnframes()))
                if gap > 0:
                    out.writeframes(hush(gap))
            if tail > 0:
                out.writeframes(hush(tail))
    except (OSError, wave.Error, IndexError) as exc:
        return 0.0, str(exc)[:160]
    return wav_seconds(dest), ""


# =============================================================================================
#  STEPS 3 AND 4 - THE SCENES, AND THE CAPTIONS CUT AGAINST THEM
# =============================================================================================
def _gradient(seconds):
    """The moving background. THE `speed` IS THE MOTION LAW, not a flourish.

    §36: "no static frame longer than 2s - slow background drift or zoom on every scene". This is
    the drift, and it is on the SOURCE so that every scene type inherits it without a line of its
    own: gradients rotates its own ramp, and at MOTION_SPEED the gray frame-to-frame difference
    one second apart measures 4.3 to 7.4 against a MOTION_MAD_MIN of 3.0.

    AND THE RAMP ENDPOINTS AND SEED ARE PINNED, which is the load-bearing half of this line. Left
    out, as §35 left them, gradients picks x0/y0/x1/y1 from a random seed on every invocation -
    so each scene of the same video got a different ramp ORIENTATION, and the drift of an
    orientation whose rotation is nearly self-similar is almost invisible. Measured on the first
    §36 pricing render: s01-chart 4.7 to 7.6, s03-flow 1.8 to 2.3, from one code path and one
    constant. A motion law asserted against a random variable is a coin toss with a threshold on
    it, and the law is not the only thing it cost - two of five beats really were nearly static.
    Pinned to the frame diagonal, every scene drifts alike and the number is reproducible.
    """
    return ("gradients=s=%dx%d:c0=%s:c1=%s:nb_colors=2:x0=0:y0=0:x1=%d:y1=%d:seed=%d:"
            "duration=%.2f:rate=%d:speed=%s"
            % (W, H, BG0, BG1, W, H, GRADIENT_SEED, max(0.5, seconds), FPS, MOTION_SPEED))


def _grow_box(x, y, width, height, color, at=0.0, span=0.9, steps=10, thick="fill"):
    """A BOX THAT GROWS, built out of timeline-gated slices because `w` is not a per-frame value.

    THE REASON IS IN THE MODULE DOCSTRING and it is worth repeating here, because the broken form
    reads better than the working one: drawbox evaluates w/h/x/y ONCE, at init, and this build has
    no `eval=frame` option to change that. Every `w='min(420\\,420*max(0\\,t-0.15)/0.9)'` in §36's
    first draft therefore drew a full-width box on frame one - six of them, including the chart's
    bars and the "animated accent underline" - and nothing failed, because a full bar is exactly
    what the frame is supposed to end up holding. It was found by measuring the bar band's mean
    gray at 0.12s against 3.2s and watching it not move.

    What IS per-frame is the timeline `enable` option. So the bar is `steps` abutting slices, each
    switched on at its own time: the slices are integer-rounded off one cumulative width so they
    cannot leave a one-pixel seam, and `gte` rather than `between` so each one STAYS on.
    """
    steps = max(1, min(16, int(steps)))
    draws, last = [], 0
    for i in range(steps):
        edge = int(round(width * (i + 1) / float(steps)))
        if edge > last:
            draws.append("drawbox=x=%d:y=%d:w=%d:h=%d:color=%s:t=%s:enable='gte(t\\,%0.3f)'"
                         % (x + last, y, edge - last, height, color, thick,
                            at + span * (i / float(steps))))
            last = edge
    return draws


def _headline(headline, kicker=""):
    """The one card furniture every scene type shares: a headline, a kicker, a growing rule.

    ONE FUNCTION BECAUSE THE LAW IS ONE LAW. §36's card is "headline (<=8 words) + one visual",
    so the headline band is identical on all five scene types and only the visual below it
    changes - which is also what makes the frame recognisable as the same video from scene to
    scene. The animated accent underline is §36's, and it is the same drawbox trick §35 used on
    the title card, kept because it costs no second codec path.
    """
    draws = []
    if kicker:
        draws.append("drawtext=%s:fontfile='%s':text='%s':fontsize=22:fontcolor=%s:x=96:y=74"
                     % (TEXT, FONT_PLAIN, _esc(kicker.upper()), DIM))
    # A MIDDOT NEVER ENDS A LINE. The keyword separator has spaces round it, so a greedy wrap can
    # leave it dangling at the break - the first chart plate read "Customers · High-ticket ·" over
    # "Objectives", which looks like a truncated title rather than a wrapped one. The line break is
    # itself a separator, so the dangling one is simply removed.
    rows = [row.rstrip(" ·") for row in _wrap(headline, 34)[:2]]
    for i, row in enumerate(rows):
        draws.append("drawtext=%s:fontfile='%s':text='%s':fontsize=46:fontcolor=%s:"
                     "x=96:y=%d:alpha='min(1\\,max(0\\,(t-%0.2f)/0.45))'"
                     % (TEXT, FONT_BOLD, _esc(row), INK, 118 + i * 56, 0.1 + 0.12 * i))
    draws += _grow_box(96, 190 + 56 * (len(rows) - 1), 420, 3, BAR, at=0.15, span=0.9, steps=14)
    return draws


def hook_head(topic, sentence):
    """§38: the hook card's headline, <=8 words, GUARANTEED to clear DUP_MAX against the hook.

    THE HOOK CARD IS A CARD NOW AND NOT AN EXEMPTION. §36 let it carry the whole sentence and
    said why: it owned the lead silence, so there was no caption under it to duplicate. §38 took
    the lead away - the hook sentence is spoken from t=0 and captioned like every other beat - so
    that argument expires with it, and the one law every other card keeps applies here too.

    THE TOPIC IS TRIED FIRST, for topic_head()'s reason: it is what the boss asked for in his own
    words, it is the right thing to print over the opening sentence of a film about it, and it
    costs almost nothing against the duplication ceiling. The sentence's own keywords are the
    fallback for a topic too thin to print, and the house's four words are the floor.
    """
    budget = shared_budget(sentence)
    for cand in (topic_head(topic), headline_of(sentence, keys=min(3, budget)), "In your notes"):
        if cand and duplication(cand, sentence) < DUP_MAX:
            return " ".join(str(cand).split()[:HEADLINE_WORDS])
    return "In your notes"


def hook_card(topic, headline, seconds, dest):
    """THE OPENING SCENE: the topic, a headline, and the rule drawn under it - over the first
    spoken sentence.

    WHAT CHANGED IS WHAT IS MISSING. There is no body text: the hook sentence the voice is saying
    is in the captions, where §36 put every other sentence. There is no "from your own notes"
    footer either, and that is the captions' doing rather than taste - it sat at y=620, which is
    where two rows of burned-in subtitles now live, and a footer under a caption is a collision.
    The CTA card still signs the film off in those words.

    It keeps the kicker, the 54-pixel headline and the drawn rule, so the opening still reads as
    an opening rather than as a beat that happens to be first.

    AND THE KICKER IS DROPPED WHEN IT WOULD SAY THE HEADLINE TWICE. On every other card the
    kicker is the topic and the headline is something else, so the pair carries two facts; on the
    hook card hook_head() tries the topic FIRST and usually wins it, which put
    "EXPLAIN USEEFFECT IN REACT" in 24px directly above "Explain useEffect In React" in 54px on
    the first §38 plate. The test is over the content words rather than the string, because the
    kicker is upper-cased and the headline is title-cased - the same words, drawn twice, is the
    thing being refused. The rule and the headline keep their positions either way.
    """
    draws = []
    if set(_words(topic)) - set(_words(headline)):
        draws.append("drawtext=%s:fontfile='%s':text='%s':fontsize=24:fontcolor=%s:x=96:y=86"
                     % (TEXT, FONT_PLAIN, _esc(str(topic).upper()), DIM))
    for i, row in enumerate(_wrap(headline, 26)[:2]):
        draws.append("drawtext=%s:fontfile='%s':text='%s':fontsize=54:fontcolor=%s:"
                     "x=96:y=%d:alpha='min(1\\,max(0\\,(t-%0.2f)/0.5))'"
                     % (TEXT, FONT_BOLD, _esc(row), INK, 230 + i * 72, 0.2 + 0.14 * i))
    draws += _grow_box(96, 160, 520, 4, BAR, at=0.1, span=1.0, steps=14)
    return _encode(_gradient(seconds) + "," + ",".join(draws), seconds, dest)


def cta_card(headline, note_ids, seconds, dest, channel="GALAXY · from your own notes"):
    """THE BOOKEND AT THE BACK: the channel line and the ids of the notes that were cited.

    THE IDS ARE THE RECEIPT and they are short-formed to eight characters because a full digest
    is forty and four of them do not fit a 1280-pixel card. They are note ids and not credentials
    - the standing law about digests is about keys, and these already appear in the ledger row
    and in script.md.
    """
    draws = ["drawtext=%s:fontfile='%s':text='%s':fontsize=26:fontcolor=%s:"
             "x=96:y=96:alpha='min(1\\,t/0.6)'" % (TEXT, FONT_PLAIN, _esc(channel), DIM)]
    for i, row in enumerate(_wrap(headline, 28)[:2]):
        draws.append("drawtext=%s:fontfile='%s':text='%s':fontsize=52:fontcolor=%s:"
                     "x=96:y=%d:alpha='min(1\\,max(0\\,(t-%0.2f)/0.6))'"
                     % (TEXT, FONT_BOLD, _esc(row), INK, 200 + i * 66, 0.2 + 0.15 * i))
    draws += _grow_box(96, 170, 460, 4, BAR, at=0.1, span=1.0, steps=14)
    short = [str(i).split("#")[0][:8] for i in (note_ids or [])][:4]
    if short:
        draws.append("drawtext=%s:fontfile='%s':text='%s':fontsize=24:fontcolor=%s:"
                     "x=96:y=420:alpha='min(1\\,max(0\\,(t-1.0)/0.8))'"
                     % (TEXT, FONT_MONO, _esc("cited  " + "  ".join(short)), DIM))
    return _encode(_gradient(seconds) + "," + ",".join(draws), seconds, dest)


def chart_scene(headline, figures, seconds, dest, kicker="by the numbers"):
    """(a) THE NUMBER BEAT: bars that grow, one scale, values read off the cited prose.

    Bars grown with drawbox's per-frame w expression, staggered by a fifth of a second each, so
    the row reads left to right. The scale is the largest figure present rather than 100, or a
    pair of 3% and 4% bars would both be invisible slivers. The label sits at the END of its own
    bar, which is why its fade waits until the bar has finished growing.
    """
    figures = [f for f in (figures or [])][:4]
    top = max([f["value"] for f in figures] or [1.0])
    draws = _headline(headline, kicker)
    span, left = 740, 150
    for i, fig in enumerate(figures):
        y = 296 + i * 76
        full = int(70 + (span - 70) * (fig["value"] / top))
        delay = 0.25 + 0.2 * i
        # SIXTEEN SLICES IS THE SMOOTHEST THIS FILTER ALLOWS: at 1.2s of growth that is a step
        # every 75ms, or about two frames at 30fps, which reads as a bar wiping out rather than as
        # a row of blocks appearing. See _grow_box() for why it cannot simply be an expression.
        draws += _grow_box(left, y, full, 40, BAR, at=delay, span=1.2, steps=16)
        draws.append("drawtext=%s:fontfile='%s':text='%s':fontsize=28:fontcolor=%s:"
                     "x=%d:y=%d:alpha='min(1\\,max(0\\,(t-%0.2f)/0.5))'"
                     % (TEXT, FONT_BOLD, _esc(fig["label"]), INK, left + full + 18, y + 6,
                        delay + 1.0))
    return _encode(_gradient(seconds) + "," + ",".join(draws), seconds, dest)


def code_scene(headline, api, lines, seconds, dest):
    """(b) THE CODE BEAT: monospace, keyword-coloured, typed on in time with the narration.

    THE TYPING IS PER TOKEN AND NOT PER CHARACTER, which is a measured compromise. Per character
    is one drawtext per glyph - about two hundred filters on a four-line card - and the graph
    stops parsing long before it stops being slow. Per token reads as typing at any frame rate a
    viewer sees, and the reveal is spread across 70% of the scene's own seconds, which is what
    makes it "synced to the voiceover": the scene lasts exactly as long as the sentence does.

    THE COLOURING NEEDS THE FIXED-WIDTH ADVANCE, which is the only arithmetic here: each token's
    x is the column it starts at times MONO_ADVANCE times the font size, so a keyword can be
    orange and the identifier after it white without either one moving.
    """
    lines = [ln for ln in (lines or [])][:6]
    size = 30 if max([len(ln) for ln in lines] or [0]) <= MONO_COLS else 26
    adv = MONO_ADVANCE * size
    draws = _headline(headline, "code")
    draws.append("drawbox=x=136:y=276:w=%d:h=%d:color=0x00000066:t=fill"
                 % (int(adv * (MONO_COLS + 2)) + 40, 40 + 44 * max(1, len(lines))))
    # THE SPREAD IS CUT AGAINST THE SPOKEN SLOT AND NOT AGAINST THE FILE. Every scene is rendered
    # XFADE_S longer than its slot so the next one can dissolve over its tail, and typing that
    # ran into the dissolve would finish the line after the sentence had already moved on.
    spread = max(0.8, (seconds - XFADE_S) * 0.7)
    total = sum(max(1, len(ln.split())) for ln in lines) or 1
    done = 0
    keywords = ("const", "function", "return", "import", "export", "from", "use", "if",
                "=>", "await", "async", "let", "var", "new", "class")
    for i, line in enumerate(lines):
        y = 300 + i * 44
        col = len(line) - len(line.lstrip(" "))
        # A COMMENT IS A PROPERTY OF THE LINE AND NOT OF THE TOKEN, which the first draft got
        # wrong: testing each token for "//" dimmed the slashes and left the words after them in
        # editor colours, so "// React 19: no wrapper needed" reached the glass with its "19:"
        # highlighted as a literal. The plate showed it before any assertion could.
        commented = line.lstrip().startswith("//")
        for token in line.split():
            delay = 0.2 + spread * (done / float(total))
            word = token.strip("(),;{}[]")
            if commented:
                colour = DIM
            elif word in keywords or word.startswith("use"):
                colour = KEYW
            elif re.match(r'^["\'\d]', word) or word in ("true", "false", "null"):
                colour = LIT
            else:
                colour = INK
            draws.append("drawtext=%s:fontfile='%s':text='%s':fontsize=%d:fontcolor=%s:"
                         "x=%d:y=%d:alpha='min(1\\,max(0\\,(t-%0.2f)/0.18))'"
                         % (TEXT, FONT_MONO, _esc(token), size, colour,
                            int(160 + col * adv), y, delay))
            col += len(token) + 1
            done += 1
        # THE CURSOR, and it is the one element that moves after the typing stops: a 2-pixel
        # block that blinks on the last line, so the card is never a still frame even if the
        # background drift were ever switched off.
        # DRAWBOX'S COLOUR IS NOT AN EXPRESSION - only x, y, w and h are, and a colour with an
        # `if()` in it is a parse error rather than a blink. The blink is therefore timeline
        # editing: drawbox supports `enable`, so the box is drawn on the half-second and skipped
        # on the half-second. Same reason the appear-on-cue boxes below use enable and not alpha.
        if i == len(lines) - 1:
            draws.append("drawbox=x=%d:y=%d:w=%d:h=%d:color=%s@0.9:t=fill:"
                         "enable='lt(mod(t\\,1)\\,0.5)'"
                         % (int(160 + col * adv), y + 4, max(8, int(adv)), size, BAR))
    if not lines:
        draws.append("drawtext=%s:fontfile='%s':text='%s':fontsize=40:fontcolor=%s:"
                     "x=160:y=320:alpha='min(1\\,max(0\\,(t-0.3)/0.6))'"
                     % (TEXT, FONT_MONO_BOLD, _esc(api or "()"), KEYW))
    draws.append("drawtext=%s:fontfile='%s':text='%s':fontsize=20:fontcolor=%s:"
                 "x=136:y=%d:alpha='min(1\\,max(0\\,(t-1.2)/0.8))'"
                 % (TEXT, FONT_PLAIN, _esc("the shape of %s - not a quote from your notes"
                                           % (api or "the API")), DIM,
                    # CLEAR OF THE PANEL, which ends at 276 + 40 + 44n: the first arithmetic put
                    # the footer's cap-height exactly on that edge and the plate showed the text
                    # sitting on the box's own border.
                    276 + 40 + 44 * max(1, len(lines)) + 14))
    return _encode(_gradient(seconds) + "," + ",".join(draws), seconds, dest)


def flow_scene(headline, boxes, seconds, dest):
    """(c) THE PROCESS BEAT: two to four boxes, left to right, with arrows between them.

    THE ARROWHEAD IS A GLYPH AND NOT A POLYGON, because there is no filter in this build that
    draws a triangle and geq is thirty times slower per frame than drawbox. A chevron in the
    plain font on the end of a two-pixel rule reads as an arrow at 720p and costs one drawtext.
    """
    boxes = [b for b in (boxes or [])][:4]
    draws = _headline(headline, "how it goes")
    n = max(1, len(boxes))
    gap = 34
    width = int((W - 2 * 130 - gap * (n - 1)) / n)
    for i, box in enumerate(boxes):
        x = 130 + i * (width + gap)
        delay = 0.3 + 0.45 * i
        draws.append("drawbox=x=%d:y=320:w=%d:h=120:color=%s@0.9:t=3:enable='gte(t\\,%0.2f)'"
                     % (x, width, BAR, delay))
        # CENTRED IN THE BOX, which needs the row count first: a one-row label pinned to the same y
        # as the first of two rows sits high in its own box and reads as a layout fault.
        lines = _wrap(box, max(8, int(width / 15)))[:2]
        top = 320 + int((120 - len(lines) * 36) / 2)
        for j, row in enumerate(lines):
            draws.append("drawtext=%s:fontfile='%s':text='%s':fontsize=28:fontcolor=%s:"
                         "x=%d:y=%d:alpha='min(1\\,max(0\\,(t-%0.2f)/0.5))'"
                         % (TEXT, FONT_BOLD, _esc(row), INK, x + 18, top + j * 36, delay + 0.1))
        if i < len(boxes) - 1:
            draws += _grow_box(x + width, 379, gap - 10, 2, DIM,
                               at=delay + 0.35, span=0.35, steps=6)
            draws.append("drawtext=%s:fontfile='%s':text='%s':fontsize=30:fontcolor=%s:"
                         "x=%d:y=362:alpha='min(1\\,max(0\\,(t-%0.2f)/0.3))'"
                         % (TEXT, FONT_BOLD, _esc("›"), DIM, x + width + gap - 14,
                            delay + 0.6))
    return _encode(_gradient(seconds) + "," + ",".join(draws), seconds, dest)


def bullets_scene(headline, items, seconds, dest):
    """(d) THE LIST BEAT: a staggered bullet stack, each row arriving on its own beat."""
    items = [i for i in (items or [])][:4]
    draws = _headline(headline, "the list")
    for i, item in enumerate(items):
        y = 300 + i * 72
        delay = 0.3 + 0.4 * i
        # A 14-PIXEL DOT GETS FOUR SLICES AND NOT SIXTEEN: past four, a slice is under a pixel wide
        # and rounds away to nothing, so the extra gates would be filters that draw no ink.
        draws += _grow_box(136, y + 14, 14, 14, BAR, at=delay, span=0.3, steps=4)
        draws.append("drawtext=%s:fontfile='%s':text='%s':fontsize=36:fontcolor=%s:"
                     "x=176:y=%d:alpha='min(1\\,max(0\\,(t-%0.2f)/0.45))'"
                     % (TEXT, FONT_BOLD, _esc(item), INK, y, delay + 0.1))
    return _encode(_gradient(seconds) + "," + ",".join(draws), seconds, dest)


def chips_scene(headline, chips, seconds, dest):
    """(e) THE FALLBACK: the headline and the beat's keywords as chips, laid out in rows.

    IT IS THE FALLBACK AND IT IS STILL A VISUAL. A beat with no figures, no identifier, no
    sequence and no list is a claim - so the card shows what the claim is ABOUT and leaves the
    sentence to the caption, which is the whole of §36's law in the one case where there is
    nothing to draw.

    THE BOX IS SIZED FOR THE TYPE THAT GOES IN IT, and §38 is where that stopped being true by
    accident: the width was `20 * chars * 0.62` while the label is drawn at fontsize 32, so the
    estimate was 12.4 px per character against a measured 15.0 to 19.3 - and "Handling" spilled
    about 27 pixels out through the right-hand side of its own outline on the §38 plate. The
    coefficient is now taken from the SAME fontsize the drawtext uses, measured here: at 32 px
    bold, ink-to-ink, Pricing is 15.0 px per character, Handling 16.8, Micro-saas 16.5 and the
    worst case in this corpus is a three-letter B2b at 19.3, because the per-character average
    rises as the word shortens. 0.62 of the font size is 19.84, which covers it, and the 48 is
    the 24 px of padding on each side that the label's own x already assumes.
    """
    chips = [c for c in (chips or [])][:6]
    draws = _headline(headline, "in your notes")
    x, y = 136, 320
    for i, chip in enumerate(chips):
        text = _cap(chip)
        wide = int(32 * len(text) * 0.62) + 48
        if x + wide > W - 120:
            x, y = 136, y + 86
        delay = 0.3 + 0.35 * i
        draws.append("drawbox=x=%d:y=%d:w=%d:h=62:color=%s@0.8:t=2:enable='gte(t\\,%0.2f)'"
                     % (x, y, wide, BAR, delay))
        draws.append("drawtext=%s:fontfile='%s':text='%s':fontsize=32:fontcolor=%s:"
                     "x=%d:y=%d:alpha='min(1\\,max(0\\,(t-%0.2f)/0.45))'"
                     % (TEXT, FONT_BOLD, _esc(text), INK, x + 24, y + 14, delay + 0.08))
        x += wide + 20
    return _encode(_gradient(seconds) + "," + ",".join(draws), seconds, dest)


MIN_ITEMS = {"chart": 2, "code": 0, "flow": 2, "bullets": 2, "chips": 1}
# WHAT A SCENE TYPE NEEDS BEFORE IT IS DRAWN AT ALL, which is not the same number as the floor the
# trim loop stops at: `code`'s trim floor is all of its lines (a half signature is a defect) while
# what it NEEDS is one - the identifier. Separated because card_plan() is a public, standalone
# function and a caller who asks for a chart of a sentence holding no figures used to be handed
# back ("chart", headline, []) - a scene with a title and no visual at all. The pipeline never
# asked, because classify_beat() only offers a type whose builder found something; this makes the
# function honest on its own terms rather than only in the one path that happens to call it.
NEED_ITEMS = {"chart": 2, "code": 1, "flow": 2, "bullets": 2, "chips": 0}


def card_share(kind, headline, items, beat):
    """The duplication share §36's law is applied to, per scene type. ONE measure, ONE place.

    §38: A LIST'S ITEMS ARE ITS VISUAL, exactly as a chart's labels are - duplication() already
    excludes figures from both bags for this reason, and says so. A bullets card made of whole
    list items measures 1.000 by construction, because a whole item IS the author's own words;
    measuring it as prose would make the scene type §38 mandates the one scene type that can
    never be drawn. So on a list card the law measures the HEADLINE, and the card's own protection
    against becoming the sentence is bullets_of()'s BULLET_KEEP_WORDS span law instead.

    EVERY OTHER TYPE IS UNCHANGED, and the trim loop reads this function too - so the measure the
    candidates are sorted by and the measure the trim loop enforces cannot drift apart, which they
    would if one of them kept its own arithmetic.
    """
    if kind == "bullets":
        return duplication(headline, beat)
    return duplication((headline or "") + " " + " ".join(items or ()), beat)


def card_plan(kind, beat, topic=""):
    """(kind, headline, items, card_text) for one beat, GUARANTEED to clear DUP_MAX. Pure.

    THIS IS WHERE §36's FIRST LAW IS KEPT, and it keeps it by DEGRADING rather than by asserting.
    A card that reprints too much of its own sentence drops its last element, then the one before
    it, and if it still cannot clear the ceiling without falling under the minimum its own scene
    type needs - a flow diagram with one box is not a flow diagram - it becomes a chips card with
    a budgeted keyword list, which always clears because a one-word chip against a three-word
    sentence is 0.33. The scene type the video actually used is what goes in the ledger row, so a
    degradation is visible in the log rather than hidden behind a passing assertion.

    THE ALTERNATIVE WAS TO ASSERT AND FAIL THE RENDER, and it is the wrong trade: the boss would
    get no video because one sentence out of five was too short to label, and the law exists to
    make the video better rather than to make it conditional.
    """
    budget = shared_budget(beat)
    headline = headline_of(beat, keys=min(3, budget))
    if kind == "chart":
        items = [f["label"] for f in chart_figures(beat)]
    elif kind == "code":
        api, lines = code_of(beat)
        items = ([api] if api else []) + list(lines)
    elif kind in ("flow", "bullets"):
        # THE STRUCTURAL TYPES SPEND THEIR BUDGET ON THE VISUAL - see topic_head(). Two box widths
        # and two headlines are measured, and the cheapest pair that clears the law wins: a
        # narrower diagram is still a diagram, where a chips card has lost the arrows that were
        # the whole claim.
        #
        # THE SECOND HEADLINE IS THE BEAT'S OWN LONGEST KEYWORD, AND IT IS USUALLY FREE. The
        # measure is over a SET of tokens, so a headline made of a word the boxes have already
        # printed costs nothing at all - which is what saves the short on-topic process sentence.
        # Measured: "Validate the idea first, then launch the product and refine the pricing" has
        # seven content words and a budget of two, and the topic headline spends one of them on
        # the word `pricing` that the sentence itself says - 0.43, over the ceiling, so the whole
        # flow degraded to chips. With `Validate` as the headline, which box one already carries,
        # the same diagram measures 0.286 and survives.
        build = flow_of if kind == "flow" else bullets_of
        heads = [h for h in (topic_head(topic), headline_of(beat, keys=1)) if h] or [headline]
        cand = []
        for width, boxes in enumerate((build(beat), build(beat, keys=1))):
            for rank, head in enumerate(heads):
                if boxes:
                    cand.append((card_share(kind, head, boxes, beat),
                                 width, rank, head, boxes))
        if cand:
            # LEGAL FIRST, THEN THE WIDER BOXES, THEN THE TOPIC'S OWN HEADLINE, THEN the lowest
            # share - in that order, because a diagram that clears the law with two keywords per
            # box says more than one that clears it with one, and the sort has to be total or the
            # ledger's scene list would depend on dict ordering.
            cand.sort(key=lambda c: (c[0] >= DUP_MAX, c[1], c[2], c[0]))
            _, _, _, headline, items = cand[0]
        else:
            items = []
    else:
        kind, items = "chips", keywords_in(beat, min(5, budget + 1))
    # NOTHING TO SHOW IS NOT A SCENE OF THIS TYPE - see NEED_ITEMS.
    if kind != "chips" and len(items) < NEED_ITEMS.get(kind, 1):
        return card_plan("chips", beat, topic)
    # §38: TWO READINGS OF THE CARD, AND THEY ARE NOT THE SAME STRING ANY MORE. `text` is what the
    # card PRINTS, which is what gets returned and what the plates can be checked against; `share`
    # is what the LAW measures, which for a list is the headline alone - see card_share().
    text = lambda rows: headline + " " + " ".join(rows)                 # noqa: E731
    share = lambda rows: card_share(kind, headline, rows, beat)         # noqa: E731
    # A SIGNATURE IS NOT TRIMMED, it is kept or it is replaced. Dropping the last lines of
    # useReducer's shape leaves `const [state, dispatch] =` on the glass with nothing after the
    # equals sign - which looks like a rendering fault, where a chips card merely looks plainer. So
    # the code card's floor is ALL of its lines and the only way out is the chips fallback below.
    floor = len(items) if kind == "code" else MIN_ITEMS.get(kind, 1)
    while items and share(items) >= DUP_MAX and len(items) > floor:
        items = items[:-1]
    if share(items) >= DUP_MAX and kind != "chips":
        return card_plan("chips", beat, topic)
    while kind == "chips" and items and share(items) >= DUP_MAX:
        items = items[:-1]
    if kind == "chips" and share(items) >= DUP_MAX:
        # A SENTENCE OF TWO CONTENT WORDS CANNOT LEND ONE OF THEM TO A TITLE: half of it is over
        # the ceiling by arithmetic, and the chips loop above can only drop chips - the headline is
        # what is left. So the last resort is a headline the sentence did not supply: the topic the
        # boss asked for, and then the house's own four words.
        for fallback in (topic_head(topic), "In your notes"):
            if fallback and card_share(kind, fallback, items, beat) < DUP_MAX:
                headline = fallback
                break
        else:
            headline, items = "In your notes", []
    return kind, headline, items, text(items)


# THE ONE TABLE THE PIPELINE DISPATCHES THROUGH, so that "five scene types" is a fact about this
# file rather than a claim in a docstring, and a sixth cannot be added without appearing here.
def scene_for(kind, beat, seconds, dest, topic=""):
    """Draw it. Returns (err, kind, card_text, share) - the TEXT is what was printed, the SHARE
    is what the law measured.

    `card_text` is everything the card actually prints apart from its furniture, and it is
    returned rather than re-derived so that duplication() is measured against the same strings
    the filtergraph drew. A law checked against a second guess at what was drawn is not checked.
    The `kind` comes back too, because card_plan() is allowed to change it.

    §38 ADDS THE SHARE AS ITS OWN RETURN VALUE, because the two are no longer the same arithmetic
    for every type: a list card prints its items and the law measures its headline (see
    card_share), so a caller that re-derived the share from the text would read 1.000 on a legal
    card and the ledger would report a violation that did not happen. The renderer hands back
    both numbers rather than letting its caller guess which rule applied.
    """
    kind, headline, items, card_text = card_plan(kind, beat, topic)
    if kind == "chart":
        want = {f["label"]: f for f in chart_figures(beat)}
        err = chart_scene(headline, [want[i] for i in items if i in want], seconds, dest)
    elif kind == "code":
        api, lines = code_of(beat)
        err = code_scene(headline, api, [ln for ln in lines if ln in items], seconds, dest)
    elif kind == "flow":
        err = flow_scene(headline, items, seconds, dest)
    elif kind == "bullets":
        err = bullets_scene(headline, items, seconds, dest)
    else:
        err = chips_scene(headline, items, seconds, dest)
    return err, kind, card_text, card_share(kind, headline, items, beat)


def _encode(graph, seconds, dest):
    """One scene, at the ONE set of codec parameters every scene shares.

    IDENTICAL PARAMETERS ARE WHAT MAKES THE CONCAT DEMUXER LEGAL. -c copy refuses to join
    streams that disagree about profile, pixel format or timebase, and its complaint arrives as
    a non-zero exit with a line of stderr rather than as a broken file - which is the good
    failure, and the reason this is one function instead of five call sites.
    """
    ff = _which("ffmpeg")
    if not ff:
        return "ffmpeg is not on the PATH"
    code, _out, err = _run([
        ff, "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", graph, "-t", "%.2f" % max(0.5, seconds),
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-pix_fmt", "yuv420p", "-r", str(FPS), "-video_track_timescale", "90000",
        "-an", dest], timeout=90)
    if code != 0 or not os.path.exists(dest) or os.path.getsize(dest) < 1024:
        return err or "ffmpeg wrote no scene"
    return ""


def _srt_time(secs):
    whole = int(secs)
    ms = int(round((secs - whole) * 1000))
    return "%02d:%02d:%02d,%03d" % (whole // 3600, (whole % 3600) // 60, whole % 60, ms)


def _ass_time(secs):
    whole = int(secs)
    cs = int(round((secs - whole) * 100))
    return "%d:%02d:%02d.%02d" % (whole // 3600, (whole % 3600) // 60, whole % 60, cs)


CAPTION_COLS = 42           # the subtitle convention, and one line of it at Arial 30 on 720p
CAPTION_ROWS = 2            # two of them per cue, counted in WRAPPED LINES and not in
                            # characters: splitting an 84-character budget and then wrapping it
                            # greedily produced a three-row cue whose third row held six
                            # characters, because the wrap loses up to a word per line and the
                            # splitter had not accounted for it. Wrapping first makes the row
                            # count an invariant rather than an estimate.


def caption_cues(rows, offset=0.0):
    """The one caption list both files are written from. Returns [{start, end, lines}].

    `offset` IS NOW ZERO FROM THE PIPELINE, and the parameter stays because the arithmetic it
    expresses stays true. In §35 the voice clock and the scene clock were reconciled here by
    adding the title card's length to every cue; in §36 `timeline()` stamps the finished clock
    onto each row before anything reads it, so a cue is simply its line's own start and the
    reconciliation happens in one place instead of two. A caller with un-stamped rows - the
    predicate tests do exactly that - can still pass the lead in and get the §35 answer.

    AND A SENTENCE IS SPLIT ACROSS CUES RATHER THAN SHOWN WHOLE. A 30-word beat is thirteen
    seconds of narration, and burned as one cue it is a six-line wall of text that sits on
    screen for thirteen seconds - unreadable, and in the way. Each cue's share of its line's
    measured duration is proportional to its share of the line's characters, which is an
    approximation WITHIN one already-measured sentence: the sentence still starts and ends
    exactly when the voice does, so the approximation cannot accumulate across the video. Only
    per-word timings would do better, and piper does not report them.
    """
    cues = []
    for row in rows:
        # WRAPPED FIRST, THEN GROUPED. _wrap is the same function the cue is rendered through, so
        # grouping its output two lines at a time is the only arrangement in which "no cue is
        # taller than CAPTION_ROWS" is true by construction. Re-wrapping a group reproduces the
        # same break, because a greedy wrap's first line does not change when the text after it
        # gets shorter.
        wrapped = _wrap(re.sub(r"\s+", " ", row["text"]).strip(), CAPTION_COLS)
        parts = [" ".join(wrapped[i:i + CAPTION_ROWS])
                 for i in range(0, len(wrapped), CAPTION_ROWS)]
        spend = float(sum(len(p) for p in parts) or 1)
        at = row["start"] + offset
        for part in parts:
            secs = row["seconds"] * (len(part) / spend)
            cues.append({"start": at, "end": at + secs, "lines": _wrap(part, CAPTION_COLS)})
            at += secs
    return cues


def write_srt(cues, dest):
    """The SRT, which is the ARTEFACT: §35 asks for one, and a player or a human can use it."""
    out = []
    for n, cue in enumerate(cues, start=1):
        out.append("%d\n%s --> %s\n%s\n" % (n, _srt_time(cue["start"]), _srt_time(cue["end"]),
                                            "\n".join(cue["lines"])))
    text = "\n".join(out)
    with open(dest, "w", encoding="utf-8") as fh:
        fh.write(text)
    return text


def write_ass(cues, dest):
    """The ASS, which is what is BURNED - because an SRT cannot carry its own geometry.

    THIS IS NOT A SECOND SOURCE OF TRUTH. Both files are written from the same `cues` list, so
    they cannot disagree; what differs is only what each format can express.

    AND THE REASON THE BURN NEEDS ASS IS MEASURED, NOT STYLISTIC. Burning the SRT with
    force_style='FontSize=22' produced captions about 55 pixels tall that collided with the beat
    card and printed the same sentence twice, illegibly, over itself. libass renders subtitle
    coordinates in the script's own resolution and an SRT declares none, so it inherits a
    288-line default and every size is multiplied by 720/288 - which means a point size in
    force_style is not a pixel size and cannot be made into one. An ASS header states
    PlayResX/PlayResY equal to the real frame, and from there 30 means 30 pixels, MarginV means
    pixels from the bottom edge, and the caption band is where it was put rather than where a
    default scaling happened to land.
    """
    head = [
        "[Script Info]", "ScriptType: v4.00+", "WrapStyle: 2", "ScaledBorderAndShadow: yes",
        "PlayResX: %d" % W, "PlayResY: %d" % H, "",
        "[V4+ Styles]",
        ("Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
         "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
         "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding"),
        ("Style: Say,Arial,30,&H00FFFFFF,&H00FFFFFF,&HC8000000,&HC8000000,0,0,0,0,"
         "100,100,0,0,1,2,0,2,80,80,40,1"), "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    for cue in cues:
        # BRACES ARE STRIPPED BECAUSE THEY ARE CODE IN THIS FORMAT. {\an8} inside the Text field
        # is an override block, so a note that happened to contain a brace could reposition or
        # restyle the caption - the same class of problem as the percent in drawtext.
        said = "\\N".join(line.replace("{", "(").replace("}", ")") for line in cue["lines"])
        # §36's CAPTION FADES, and the override block goes in AFTER the braces above have been
        # neutralised - otherwise a note containing a brace could close this block and the rest of
        # the sentence would be read as tags. 120ms each way is short enough that a cue is at full
        # opacity for the syllable it belongs to and long enough that the cut is not a flicker.
        head.append("Dialogue: 0,%s,%s,Say,,0,0,0,,{\\fad(%d,%d)}%s"
                    % (_ass_time(cue["start"]), _ass_time(cue["end"]), 120, 120, said))
    text = "\n".join(head) + "\n"
    with open(dest, "w", encoding="utf-8") as fh:
        fh.write(text)
    return text


# =============================================================================================
#  STEP 5 - THE STITCH
# =============================================================================================
def xfade_offsets(slots):
    """Where each cross-dissolve begins in the running output. A PURE FUNCTION, so it is asserted.

    THIS IS THE ONE PIECE OF ARITHMETIC THAT CAN SILENTLY DESYNC THE WHOLE VIDEO, so it is
    separated from the filtergraph that uses it. Each scene file is `slot + XFADE_S` long. xfade
    produces `a + b - XFADE_S`, so if the n-th transition starts at the sum of the first n slots,
    the chain's length after n+1 scenes is that sum plus the next slot plus one XFADE_S - and
    therefore scene n is fully on screen from exactly `sum(slots[:n])`, which is where the
    narration's n-th line starts on the audio clock timeline() stamped. The whole picture is then
    `sum(slots) + XFADE_S` long against audio of `sum(slots)`, and -shortest trims the half-second
    of overhang off the sign-off card.

    §35 joined with the concat demuxer and -c copy, which cannot dissolve: the cut was a hard one
    on a frame, and "a captioned slideshow" is what a hard cut between two still cards looks like.
    """
    offsets, at = [], 0.0
    for slot in slots[:-1]:
        at += slot
        offsets.append(round(at, 3))
    return offsets


def stitch(scenes, slots, voice_wav, sub_path, dest, folder):
    """ONE pass: the scenes cross-dissolved, the voice muxed, the captions burned.

    ONE PASS AND NOT §35's TWO, because the join is no longer free. §35 concatenated with -c copy
    and then re-encoded once to burn the captions; an xfade chain re-encodes by definition, so
    putting the burn in the same filter_complex costs nothing extra and keeps the frame count
    touched by exactly one encoder. It is also why WALL_MAX_S moved from 180 to 240.

    -shortest is what makes the mp4 end when the narration does rather than on the last scene's
    final frame, which is now half a second of dissolve-out with nothing to dissolve into.
    """
    ff = _which("ffmpeg")
    if not ff:
        return "ffmpeg is not on the PATH"
    if not scenes or len(scenes) != len(slots):
        return "the scene list and the slot list disagree"
    # THE SUBTITLE PATH IS WRITTEN FOR A FILTER OPTION, not for Windows. The drive colon is
    # escaped for the same reason the fontfile's is, and the backslashes are turned round first
    # - a filter option containing C:\Users is two parse errors, not one.
    #
    # NO force_style, BECAUSE THE STYLE IS IN THE FILE. Every value force_style could set is
    # already stated in the ASS header against a declared PlayRes, which is the only way a point
    # size means a pixel size - see write_ass().
    sub = sub_path.replace("\\", "/").replace(":", "\\:")
    args = [ff, "-hide_banner", "-loglevel", "error", "-y"]
    for path in scenes:
        args += ["-i", path]
    args += ["-i", voice_wav]
    chain, last = [], "0:v"
    for n, offset in enumerate(xfade_offsets(slots), start=1):
        label = "x%d" % n
        chain.append("[%s][%d:v]xfade=transition=fade:duration=%.2f:offset=%.3f[%s]"
                     % (last, n, XFADE_S, offset, label))
        last = label
    chain.append("[%s]subtitles='%s'[v]" % (last, sub))
    args += ["-filter_complex", ";".join(chain), "-map", "[v]",
             "-map", "%d:a:0" % len(scenes),
             "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-pix_fmt", "yuv420p",
             "-r", str(FPS), "-c:a", "aac", "-b:a", "128k", "-ac", "2",
             "-shortest", "-movflags", "+faststart", dest]
    code, _out, err = _run(args, timeout=240)
    if code != 0 or not os.path.exists(dest) or os.path.getsize(dest) < 4096:
        return "the final mux failed: %s" % (err or "no output")
    return ""


def poster(video, dest, at=1.8):
    """THE THUMBNAIL, grabbed out of the finished file. For the future Broadcaster.

    OUT OF THE FINISHED FILE AND NOT DRAWN AGAIN, which is the point: a poster rendered from the
    same filtergraph would be a second thing that could disagree with the video, and a thumbnail
    that does not look like the first seconds of the clip is the oldest bait there is. 1.8s is
    inside the hook card and past its fade-in, so the headline is at full opacity.

    Pillow is not installed on this machine, so the JPEG comes out of ffmpeg's own mjpeg encoder.
    """
    ff = _which("ffmpeg")
    if not ff:
        return "ffmpeg is not on the PATH"
    code, _out, err = _run([ff, "-hide_banner", "-loglevel", "error", "-y",
                            "-ss", "%.2f" % at, "-i", video, "-frames:v", "1",
                            "-q:v", "3", dest], timeout=60)
    if code != 0 or not os.path.exists(dest) or os.path.getsize(dest) < 2048:
        return err[:160] or "ffmpeg wrote no poster"
    return ""


def motion_mad(video, at, scratch=""):
    """§36's MOTION LAW, measured: mean absolute gray difference between t and t+1s.

    IT IS A NUMBER AND NOT AN EYE. "No static frame longer than 2s" cannot be asserted by looking
    at a plate, so two frames one second apart are decoded at MOTION_SAMPLE, converted to a
    single gray plane, and differenced byte by byte. The scale that comes out of it, on this
    palette: a frozen card reads 0.0, §35's gradient at its default speed of 0.01 reads 1.1 to
    2.4, and MOTION_SPEED's 0.05 reads 6.3 to 15.2 - which is why MOTION_MAD_MIN is 3.0, above
    everything §35 could produce and below everything §36 does.

    Returns a float, or -1.0 if the frames could not be read - and the caller must treat -1.0 as
    "not measured" rather than as "failed", because an unmeasurable sample is a broken probe and
    not a static video.
    """
    ff = _which("ffmpeg")
    if not ff:
        return -1.0
    wide, high = MOTION_SAMPLE
    raw = scratch or os.path.join(os.path.dirname(os.path.abspath(video)),
                                  "_motion-%d.gray" % os.getpid())
    # fps=1 AFTER the seek, so the two frames are exactly one second apart on the output clock
    # whatever the source frame rate is; 2.05s of it to be sure the second frame exists.
    code, _out, _err = _run([ff, "-hide_banner", "-loglevel", "error", "-y",
                             "-ss", "%.3f" % max(0.0, at), "-i", video, "-t", "2.05",
                             "-vf", "fps=1,scale=%d:%d" % (wide, high),
                             "-pix_fmt", "gray", "-f", "rawvideo", raw], timeout=60)
    plane = wide * high
    try:
        if code != 0:
            return -1.0
        with open(raw, "rb") as fh:
            data = fh.read(plane * 2)
        if len(data) < plane * 2:
            return -1.0
        first, second = data[:plane], data[plane:plane * 2]
        return round(sum(abs(a - b) for a, b in zip(first, second)) / float(plane), 2)
    except OSError:
        return -1.0
    finally:
        try:
            os.remove(raw)
        except OSError:
            pass


def motion_mads(video, times):
    """motion_mad over several sample points. Returns [{at, mad}] in the order given."""
    return [{"at": round(float(t), 2), "mad": motion_mad(video, t)} for t in times]


def probe_streams(path):
    """What ffprobe says is actually in the file - the only honest answer to "did it work".

    §35 asks for "ffprobe confirms one video + one audio stream", and the reason that is the
    assertion rather than "the file exists" is that every single failure mode in this pipeline
    produces a file: a dropped -map produces a silent mp4, a failed concat produces a 48-byte
    one, and a return code of zero produces both.
    """
    fp = _which("ffprobe")
    if not fp:
        return {"ok": False, "why": "ffprobe is not on the PATH"}
    code, out, err = _run([fp, "-v", "error", "-show_entries",
                           "stream=codec_type,codec_name:format=duration,size",
                           "-of", "json", path], timeout=40)
    if code != 0:
        return {"ok": False, "why": err[:160] or "ffprobe refused the file"}
    try:
        data = json.loads(out or "{}")
    except ValueError:
        return {"ok": False, "why": "ffprobe said something that was not JSON"}
    streams = data.get("streams") or []
    video = [s for s in streams if s.get("codec_type") == "video"]
    audio = [s for s in streams if s.get("codec_type") == "audio"]
    try:
        secs = round(float((data.get("format") or {}).get("duration") or 0), 2)
    except (TypeError, ValueError):
        secs = 0.0
    return {"ok": len(video) == 1 and len(audio) == 1, "video": len(video),
            "audio": len(audio), "durationS": secs,
            "vcodec": (video[0].get("codec_name") if video else ""),
            "acodec": (audio[0].get("codec_name") if audio else ""),
            "bytes": int((data.get("format") or {}).get("size") or 0), "why": ""}


# =============================================================================================
#  THE PIPELINE
# =============================================================================================
def make(topic, report=None, keep_parts=False):
    """The whole Director, one topic in, one dict out. It never raises.

    IT NEVER RAISES because its two callers are a page waiting for a sentence and a thread with
    nowhere to put a traceback. Every stage returns a reason instead, the bus gets the reason as
    an event, the ledger gets it as a row, and the boss gets one plain line.
    """
    began = time.monotonic()
    topic = re.sub(r"\s+", " ", str(topic or "")).strip()
    out = {"ok": False, "topic": topic, "slug": slug_of(topic), "cited": [], "beats": 0,
           "voiceS": 0.0, "wallS": 0.0, "path": "", "why": "", "answer": "",
           "source": "", "job": (report.job if report else ""), "steps": []}
    if not topic:
        out["why"] = "no topic"
        out["answer"] = "Tell me what the video should be about, sir."
        return out

    # ---- STEP 1 - THE SCRIPT -----------------------------------------------------------------
    if report:
        report.step("script", "reading the notes on %s" % topic[:40])
    try:
        found = ingest.recall(topic, top_k=5)
    except Exception as exc:                                       # noqa: BLE001
        found = {"opens": False, "hits": [], "why": str(exc)[:120]}
    hits = [h for h in (found.get("hits") or []) if (h.get("text") or "").strip()]
    # THE GRACEFUL EMPTY, and it is the FIRST thing checked for a reason: every stage after this
    # one costs seconds, and a topic the notes are silent on should cost a sentence. recall()'s
    # own `opens` is the test, not a score this file re-derives.
    if not found.get("opens") or not hits:
        out["why"] = "the notes hold nothing on this"
        out["answer"] = "The notes hold nothing on %s, sir, so there is no video to make." % topic
        out["wallS"] = round(time.monotonic() - began, 2)
        return out

    # §38: THE NOTES ARE TIERED BEFORE A WORD IS WRITTEN. recall() returns what is RELATED; this
    # keeps what is about the TOPIC, by the gap in its own scores. Doing it here rather than
    # after the draft is what makes the citation list honest: a note the writer never saw is a
    # note the CTA card never claims.
    hits, passengers = note_tier(topic, hits)
    out["notesKept"], out["notesDropped"] = len(hits), len(passengers)
    if passengers and report:
        report.note("set aside %d retrieved note%s more than %.2f below the best hit"
                    % (len(passengers), "" if len(passengers) == 1 else "s", RECALL_GAP))

    want = int(52 * WORDS_PER_S)                      # aim at the middle of the 40-70s budget
    beats, cited, source = write_script(topic, hits, want)
    # §38: AND THE DRAFT IS READ BACK AGAINST THE TOPIC BEFORE IT IS NARRATED. The guard runs
    # here, before voice_lines() spends a second of synthesis on a sentence that will not ship.
    if beats:
        beats, out["guard"] = topic_guard(topic, beats, hits, report=report)
    if not beats:
        out["why"] = "the notes gave no usable sentences"
        out["answer"] = ("The notes mention %s, sir, but not in enough prose to narrate."
                         % topic)
        out["wallS"] = round(time.monotonic() - began, 2)
        return out
    out["source"], out["cited"], out["beats"] = source, cited, len(beats)
    out["guardMin"] = min([r["words"] for r in out.get("guard") or [] if r["verdict"] != "dropped"]
                          or [0])

    folder = os.path.join(OUT_ROOT, out["slug"])
    os.makedirs(folder, exist_ok=True)
    if report:
        report.note("%d beats, %d notes cited, prose by %s" % (len(beats), len(cited), source))

    # ---- STEP 2 - THE VOICEOVER --------------------------------------------------------------
    if report:
        report.step("voice", "%d lines to the %s voice" % (len(beats), say.DEFAULT_MODEL))
    rows, why = voice_lines(beats, folder, report=report)
    if not rows:
        out["why"] = why
        out["answer"] = "I could not narrate it, sir: %s" % why
        out["wallS"] = round(time.monotonic() - began, 2)
        return out
    rows, cut = fit_budget(rows)
    if cut and report:
        report.note("trimmed %d line%s to hold the %.0fs ceiling"
                    % (len(cut), "" if len(cut) == 1 else "s", VOICE_MAX_S))
    out["trimmed"] = len(cut)
    # AND THE SCRIPT FILE IS WRITTEN AFTER THE TRIM, not before it. script.md is what a human
    # opens to check the machine, so it has to describe the video that EXISTS - a listing that
    # still carried a sixth beat the ceiling removed would be a document that disagrees with the
    # mp4 beside it, which is worse than no document.
    beats = [r["text"] for r in rows]
    with open(os.path.join(folder, "script.md"), "w", encoding="utf-8") as fh:
        fh.write(script_markdown(topic, beats, cited, hits, source))
    out["beats"] = len(beats)

    # ---- THE ONE CLOCK, AND THE SCENE PLAN THAT SHARES IT ------------------------------------
    # EVERYTHING IS DECIDED HERE, BEFORE A FRAME OR A SAMPLE IS WRITTEN, because the audio's
    # padding, the captions' starts and the cross-dissolve offsets are three readings of one
    # number and §36 added a term to it. timeline() stamps the clock; the scene plan below is
    # built from the same `slot` values it wrote, so the picture cannot drift from the voice.
    kinds = classify_all(beats, topic)
    # THE RECAP CHART IS THE ONE SCENE NOT TIED TO A SENTENCE, and it exists only when the
    # narration carries comparable figures that no single beat claimed. The figures are read out
    # of the NARRATION and never out of the note text: a bar for a number the voiceover never
    # says is a bar the boss cannot check. Two bars is the floor, because one bar is a rectangle
    # with a label and says less than the sentence under it.
    recap = [] if "chart" in kinds else chart_figures(" ".join(beats))
    # LEAD ZERO - see HOOK_S. The first sentence starts the file, and the hook card takes the
    # front of that first beat's slot instead of sitting in front of it: the two shares add back
    # to the slot timeline() wrote, so the sum of the slots is still exactly the audio length and
    # xfade_offsets() reads the same clock it always did.
    rows, voiced_to = timeline(rows, lead=0.0, gap=PAUSE_S)
    hook_s = round(min(HOOK_S, rows[0]["slot"] / 2.0), 3)
    tail_s = (CHART_S if recap else 0.0) + CTA_S
    plan = ([{"kind": "hook", "slot": hook_s, "at": 0.0, "row": rows[0]}]
            + [{"kind": kinds[0], "slot": round(rows[0]["slot"] - hook_s, 3), "at": hook_s,
                "row": rows[0]}]
            + [{"kind": k, "slot": r["slot"], "at": r["start"], "row": r}
               for k, r in zip(kinds[1:], rows[1:])]
            + ([{"kind": "chart", "slot": CHART_S, "at": voiced_to, "recap": True}]
               if recap else [])
            + [{"kind": "cta", "slot": CTA_S,
                "at": voiced_to + (CHART_S if recap else 0.0)}])
    out["sceneTypes"] = [p["kind"] for p in plan]
    out["sceneKinds"] = sorted(set(kinds))
    voice_wav = os.path.join(folder, "voice.wav")
    full, why = join_wavs(rows, voice_wav, lead=0.0, tail=tail_s, gap=PAUSE_S)
    if not full:
        out["why"] = why or "the voiceover would not join"
        out["answer"] = "I could not assemble the narration, sir."
        out["wallS"] = round(time.monotonic() - began, 2)
        return out
    # THE BUDGET IS ABOUT THE NARRATION AND NOT ABOUT THE FILE. §35 asserts "voiceover 40-70s",
    # and padding is not voiceover - a lead and a tail that counted towards it would let a
    # 36-second script pass the budget by growing its own title card.
    out["voiceS"] = round(sum(r["seconds"] for r in rows), 3)
    out["audioS"] = full
    # THE FLOOR IS REPORTED AND NOT ENFORCED, which is the opposite of the ceiling, and the
    # asymmetry is real: a long script can be shortened by subtraction, but a short one can only
    # be lengthened by inventing prose the notes do not contain - which is the one thing this
    # whole file refuses to do. So a thin topic yields a short video and SAYS SO, in the dict,
    # the ledger and the proof, rather than padding itself to clear a number.
    out["budgetOk"] = bool(VOICE_MIN_S <= out["voiceS"] <= VOICE_MAX_S)
    if not out["budgetOk"] and report:
        report.note("narration is %.1fs, outside the %.0f-%.0fs budget"
                    % (out["voiceS"], VOICE_MIN_S, VOICE_MAX_S))

    # ---- STEP 3 - THE SCENES -----------------------------------------------------------------
    total = len(plan)
    if report:
        report.step("scenes", "%d scenes - %s" % (total, " · ".join(out["sceneTypes"])))
    scenes, slots, dups = [], [], []
    for i, beat_plan in enumerate(plan):
        kind, slot = beat_plan["kind"], beat_plan["slot"]
        # EVERY SCENE FILE IS ITS SLOT PLUS ONE DISSOLVE, which is what xfade_offsets() assumes.
        # The arithmetic lives in that function; this is the one place it is paid for.
        seconds = slot + XFADE_S
        path = os.path.join(folder, "s%02d-%s.mp4" % (i, kind))
        if kind == "hook":
            # §38: AND THE HOOK IS MEASURED LIKE EVERY OTHER CARD. It has a caption under it now,
            # so it has a duplication share, and that share goes into the dict and the ledger
            # beside the others - the one card that used to be exempt is the one a regression
            # would reach for first.
            head = hook_head(topic, beats[0])
            err, card_text = hook_card(topic, head, seconds, path), head
            dups.append({"n": beat_plan["row"]["n"], "kind": "hook",
                         "share": duplication(head, beats[0]),
                         "printed": duplication(head, beats[0])})
        elif kind == "cta":
            err, card_text = cta_card(topic, cited, seconds, path), ""
        elif beat_plan.get("recap"):
            err = chart_scene("What the numbers say", recap, seconds, path, kicker="recap")
            card_text = ""
        else:
            text = beat_plan["row"]["text"]
            err, kind, card_text, share = scene_for(kind, text, seconds, path, topic=topic)
            # card_plan() may have DEGRADED the type to keep the duplication law; the plan and the
            # ledger row must say what was drawn and not what was intended.
            beat_plan["kind"] = kind
            out["sceneTypes"][i] = kind
            # §36's FIRST LAW, MEASURED AT RENDER TIME AND NOT ONLY IN THE PROOF. The card's own
            # strings are compared with the sentence the captions will carry, and the number goes
            # into the dict and the ledger - so a future change that quietly reintroduces the
            # sentence-on-a-card defect shows up in a real render, not just under a harness.
            dups.append({"n": beat_plan["row"]["n"], "kind": kind, "share": share,
                         # §38: and the PRINTED share is carried beside the LAW's share, so a
                         # list card's exemption is a number in the ledger rather than a silence.
                         "printed": duplication(card_text, text)})
        if err:
            out["why"] = "scene %d (%s): %s" % (i, kind, err)
            out["answer"] = "The renderer refused the %s scene, sir." % kind
            out["wallS"] = round(time.monotonic() - began, 2)
            return out
        scenes.append(path)
        slots.append(slot)
        if report:
            report.note("scene %d of %d - %s" % (len(scenes), total, kind))
    out["dup"] = dups
    out["dupMax"] = max([d["share"] for d in dups] or [0.0])
    # AND THE VARIETY IS COUNTED OVER WHAT WAS DRAWN, not over what was proposed. classify_all()
    # chose these types before card_plan() had measured a single label, and card_plan() is allowed
    # to degrade one - a code beat whose signature would reprint its own narration becomes chips.
    # Reporting the proposal would mean the dict could claim four distinct scene types in a film
    # holding two, which is exactly the slideshow §36 was written against. The bookends and the
    # recap are excluded because the variety law is about the BEATS: a hook and a sign-off that
    # counted towards it would hand every two-beat video three types for free.
    # §38: the hook carries a `row` now, because it is a title card over a spoken beat rather
    # than a silent lead - so it is excluded by NAME here. The variety law is about what the
    # beats were DRAWN as, and a bookend that counted towards it would hand every video a type.
    out["sceneKinds"] = sorted({p["kind"] for p in plan
                                if p.get("row") and p["kind"] != "hook"})

    # ---- STEP 4 - THE CAPTIONS ---------------------------------------------------------------
    # OFFSET ZERO: timeline() already stamped the finished clock onto every row.
    cues = caption_cues(rows)
    if report:
        report.step("captions", "%d cues from the measured timings" % len(cues))
    srt_path = os.path.join(folder, "captions.srt")
    ass_path = os.path.join(folder, "captions.ass")
    write_srt(cues, srt_path)
    write_ass(cues, ass_path)
    out["cues"] = len(cues)

    # ---- STEP 5 - THE STITCH -----------------------------------------------------------------
    if report:
        report.step("stitch", "%d scenes, voice and captions into one file" % len(scenes))
    final = os.path.join(folder, "final.mp4")
    err = stitch(scenes, slots, voice_wav, ass_path, final, folder)
    if err:
        out["why"] = err
        out["answer"] = "The stitch failed, sir: %s" % err
        out["wallS"] = round(time.monotonic() - began, 2)
        return out

    streams = probe_streams(final)
    # THE POSTER IS A FAIL-SOFT, like the chart was in §35: it is an artefact BESIDE the video for
    # a Broadcaster that does not exist yet, and losing a finished render over a JPEG is the wrong
    # trade. Whether it exists is reported rather than assumed.
    poster_path = os.path.join(folder, "poster.jpg")
    poster_err = poster(final, poster_path)
    out["poster"] = ("" if poster_err
                     else os.path.relpath(poster_path, ROOT).replace("\\", "/"))
    if poster_err and report:
        report.note("no poster: %s" % poster_err)
    out["path"] = os.path.relpath(final, ROOT).replace("\\", "/")
    out["wallS"] = round(time.monotonic() - began, 2)
    out["probe"] = streams
    # READ OFF THE SCENE LIST FOR THE SAME REASON sceneKinds is: §36 requires the pricing video to
    # CONTAIN a chart and the react video to CONTAIN a code card, and "classify_all proposed one"
    # is not that. sceneTypes already carries the recap chart as a chart and already carries every
    # degradation, so these two flags are now derivable from the artefact rather than asserted
    # beside it.
    out["chart"] = "chart" in out["sceneTypes"]
    out["code"] = "code" in out["sceneTypes"]
    out["steps"] = STEPS
    if not streams.get("ok"):
        out["why"] = streams.get("why") or ("%d video and %d audio streams"
                                            % (streams.get("video", 0), streams.get("audio", 0)))
        out["answer"] = "The file came out wrong, sir: %s" % out["why"]
        return out
    if not keep_parts:
        # THE PARTS GO AND THE SCRIPT STAYS. The scene mp4s and per-line WAVs are intermediate
        # and large; script.md, captions.srt and final.mp4 are the three a human might open.
        for name in os.listdir(folder):
            if re.match(r"^(s\d\d.*\.mp4|line\d\d\.wav|silent\.mp4|scenes\.txt)$", name):
                try:
                    os.remove(os.path.join(folder, name))
                except OSError:
                    pass
    out["ok"] = True
    out["answer"] = ("Your video on %s is ready, sir - %.0f seconds, from %d of your own notes."
                     % (topic, streams.get("durationS") or out["voiceS"], len(cited)))
    return out


def direct(topic, keep_parts=False, report=None):
    """make(), with the progress bus around it. THE ONE ENTRY POINT the server uses.

    The bus is wired HERE rather than inside make() so that make() stays testable without a bus
    and so there is exactly one place that CLOSES a job - which is what makes "one ledger row
    per job" a property rather than a convention.

    AND THE CALLER MAY HAND IN THE JOB IT ALREADY OPENED. Exactly one does: _Manager.request()
    must put a job id into the same HTTP reply that announces the render, which means the id has
    to exist before the thread that renders does. The alternative was for the server to read
    MANAGER.live() straight after request() and hope the id was there - which returned the
    placeholder "pending" when it was quick and "" when the render had already finished, so the
    page would have polled an id matching no job. The closer is still this function alone.
    """
    report = report or jobs.Reporter("director", STEPS, verb="directing", topic=topic)
    try:
        out = make(topic, report=report, keep_parts=keep_parts)
    except Exception as exc:                                       # noqa: BLE001
        report.failed("unexpected: %s" % exc)
        return {"ok": False, "topic": topic, "why": str(exc)[:160], "job": report.job,
                "answer": "The Director hit an unexpected error, sir."}
    out["job"] = report.job
    if out.get("ok"):
        # §36: THE LEDGER ROW CARRIES THE SCENE-TYPE LIST, because "the video had a chart in it"
        # is otherwise a claim that exists only inside a harness. A boss reading the ledger a week
        # later can see which beats were drawn as what, and a regression to five identical cards
        # is visible in the log without opening the mp4.
        report.done(out["answer"], cited=out["cited"],
                    durationS=(out.get("probe") or {}).get("durationS") or out["voiceS"],
                    path=out["path"], sceneTypes=out.get("sceneTypes") or [],
                    poster=out.get("poster") or "")
    else:
        report.failed(out.get("why") or "no video", why=out.get("why") or "")
    return out


# =============================================================================================
#  THE MANAGER - one render at a time, off the conversational thread
# =============================================================================================
class _Manager:
    """The Async Law at its load-bearing point, and scholar.MANAGER's shape deliberately.

    A render takes sixty-seven seconds cold. protected_answer() runs on the thread that is
    holding the boss's HTTP request open, so calling direct() from there would freeze the glass
    for over a minute with no chip, no steps and no way to tell a working machine from a hung
    one - which is the precise failure §35 PART 3 exists to forbid. So request() queues the work
    on a daemon thread and returns a SENTENCE immediately; the progress bus is what reports
    afterwards, exactly as the Scholar's seal is.

    ONE AT A TIME, and the lock is not politeness. A render spends five piper calls, a model
    call and six ffmpeg encodes, and two at once on this machine would contend for the same CPU
    and the same output folder - two jobs on one topic write the same scene files, so the second
    would stitch the first's half-written frames. A second request while one is live is answered
    with what is already running rather than queued, because the boss asking twice means he
    wants to know, not that he wants two videos.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._live = ""                 # the job id of the render in flight, "" when idle
        self._topic = ""
        self.last = {}                  # the last finished result, for a harness and a log

    def live(self):
        with self._lock:
            return self._live, self._topic

    def request(self, topic, why="boss"):
        """(started, sentence, job). Never blocks, never raises, never renders on this thread.

        THE JOB ID IS THE THIRD RETURN VALUE and not something the caller reads back off
        live(), because live() is only true WHILE the render is in flight: a caller that read it
        afterwards got "" and a caller that read it before the thread had started got a
        placeholder. Returned here it is the id of the job this call opened, always, and on the
        busy path it is the id of the one already running - which is what the glass should be
        showing the boss anyway.
        """
        said = re.sub(r"\s+", " ", str(topic or "")).strip()
        if not said:
            return False, "Tell me what the video should be about, sir.", ""
        with self._lock:
            if self._live:
                return False, ("I am still making the one about %s, sir - one at a time."
                               % self._topic), self._live
            # OPENED ON THIS THREAD, under this lock, before the renderer exists. jobs has its
            # own lock and never calls back into this class, so there is no order to get wrong.
            report = jobs.Reporter("director", STEPS, verb="directing", topic=said)
            self._live, self._topic = report.job, said

        def run():
            try:
                out = direct(said, report=report)
            except Exception as exc:                               # noqa: BLE001
                out = {"ok": False, "topic": said, "why": str(exc)[:160]}
                sys.stderr.write("director: %s\n" % exc)
            with self._lock:
                self._live, self._topic = "", ""
                self.last = out
            sys.stderr.write("director: %r finished ok=%s why=%r\n"
                             % (said, bool(out.get("ok")), out.get("why") or ""))

        threading.Thread(target=run, name="director", daemon=True).start()
        # THE SENTENCE IS §35's, WORD FOR WORD - "building your video on X - about three minutes,
        # sir" - because PART 3 requires the announcement at job start to be one line in text and
        # speech, and a sentence composed in two places is a sentence that drifts in one of them.
        return True, ("Building your video on %s - about three minutes, sir." % said), report.job


MANAGER = _Manager()
