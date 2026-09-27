"""voiceprint.py - the doorman's memory: one 192-float embedding per enrolled voice.

WHY THIS EXISTS. The Hands gate asks "shall I?" and takes a spoken yes. Until now any voice in
the room could answer it, because the page could hear words but had no idea WHO said them. This
module is the part that knows. It turns a few seconds of speech into one vector, compares that
vector against the enrolled set by cosine, and answers with a name or with GUEST.

WHAT IT IS NOT. It is not a transcriber and it never returns words. It is not a store of audio:
every function here takes samples as an argument and none of them writes samples anywhere. The
only thing that reaches the disk is the embedding, and the embedding cannot be played back.

THE MODEL. WeSpeaker's ECAPA-TDNN (ECAPA_TDNN_GLOB_c512-ASTP-emb192-fbank80), exported to ONNX
by the WeSpeaker org and run through the onnxruntime that was already installed on this machine.
80-bin fbank in, 192 floats out, 24.9 MB on disk. The alternative was a hand-rolled MFCC
supervector, which needs no download and is far weaker across microphones; the alternative that
was NOT available is anything torch-shaped, because torch is not installed and the standing rule
forbids adding pip dependencies. A model file is an asset, not a dependency.

THE FEATURE FRONT-END IS THE RISK IN THIS FILE, and it is worth saying so out loud. The model was
trained on Kaldi fbank, and a front-end that is subtly wrong - a window off by a power, a missing
pre-emphasis, the wrong mel formula - does not throw. It produces embeddings that look entirely
reasonable and score like noise, and a doorman built on one would let the wrong voice through
while every assertion about shapes and dimensions passed. So this file reimplements
torchaudio.compliance.kaldi.fbank's defaults in numpy, deliberately and step by step, and the
thing it is checked on is the only thing that matters: two sentences from one voice must score
high and two voices must score low. The shapes are not the proof.
"""

import io
import json
import math
import os
import pathlib
import re
import unicodedata
import wave

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parent
MODEL_PATH = ROOT / "models" / "ecapa_tdnn512_LM.onnx"
STORE_DIR = ROOT / "speaker-store"

EMB_DIM = 192                 # what the ONNX graph declares on its output
SAMPLE_RATE = 16000           # what the model was trained at; everything is resampled to it
NUM_MEL_BINS = 80
FRAME_LENGTH_MS = 25.0
FRAME_SHIFT_MS = 10.0
LOW_FREQ = 20.0
HIGH_FREQ = 0.0               # 0 means nyquist, as Kaldi reads it
PREEMPH = 0.97
POVEY_POWER = 0.85            # the povey window is hann raised to this; it is torchaudio's default
EPSILON = float(np.finfo(np.float32).eps)

# THE THREE NUMBERS THE DOORMAN IS JUDGED BY, and they are measured rather than chosen. The
# calibration is in _runs/after/VOICEPRINT_CAL.txt: twelve utterances across three voices, all
# 18 same-voice pairs and all 48 cross-voice pairs.
#
#     same voice      0.8182 .. 0.9382   (mean 0.8880)
#     different voice 0.0244 .. 0.2954   (mean 0.1659)
#     gaussian noise  -0.0216 .. 0.0430  against each voice's centre
#
# A gap of 0.523 between the worst same-voice pair and the best different-voice pair. That gap is
# also the evidence that the Kaldi front-end above is right: a front-end with the window or the
# mel formula wrong still returns 192 finite floats, but it cannot put two readings of one voice
# at 0.89.
#
# THE THRESHOLD IS NOT THE MIDPOINT (0.557), on purpose. The calibration voices are piper's, and
# synthetic speech is unnaturally self-consistent: no head cold, no different chair, no second
# microphone, no room. A real speaker's same-voice floor across sessions sits materially below
# 0.82, so a threshold tuned to the midpoint of a TTS measurement would be tuned to refuse the
# boss on a Tuesday. 0.50 keeps a 0.20 margin over the loudest false friend measured here while
# leaving real-session drift somewhere to go. It is deliberately not lower than that, because
# the two errors do not cost the same: refusing the boss costs him a keystroke - the keyboard Yes
# is always open - whereas admitting a stranger costs him a sent email.
MATCH_THRESHOLD = 0.50
# Different voices topped out at 0.2954 and the same voice bottomed out at 0.8182, so anything
# in between separates them; 0.70 is placed nearer the same-voice floor because the cost of a
# missed duplicate (two rows for one person) is an untidy store, while the cost of a false
# duplicate is a refusal to enrol a real second person, which has no workaround in the UI.
DUPLICATE_THRESHOLD = 0.70
# Embedding quality flattens off above roughly three seconds of speech per utterance; three
# sentences of the length the prompt asks for ran 4.2s to 6.6s each in calibration. Eight seconds
# of total speech is therefore a floor that a cooperative speaker clears easily and a one-word
# answer cannot. The refusal names the seconds still missing rather than just saying no.
ENROL_MIN_SECONDS = 8.0
ENROL_MIN_SENTENCES = 3

_session = None


# ---------------------------------------------------------------------------------------------
# THE RESAMPLER. The room arrives at 48 kHz and the model wants 16 kHz, and dropping every third
# sample would fold everything above 8 kHz back down into the speech band as alias - which is a
# change to the spectrum the embedding is entirely made of. So: a windowed-sinc low-pass at just
# under the new nyquist, then linear interpolation onto the new grid. Linear interpolation is
# acceptable HERE only because the signal has already been band-limited well below the point
# where its error matters; on its own it would be a second aliaser.
# ---------------------------------------------------------------------------------------------

def _lowpass(samples, cutoff_hz, rate, taps=64):
    if cutoff_hz >= rate / 2.0:
        return samples
    fc = cutoff_hz / rate                                  # cycles per sample
    n = np.arange(-taps, taps + 1, dtype=np.float64)
    h = np.sinc(2.0 * fc * n) * np.blackman(2 * taps + 1)
    h /= h.sum()
    return np.convolve(samples, h, mode="same")


def resample(samples, src_rate, dst_rate=SAMPLE_RATE):
    """Mono float samples in [-1, 1] at src_rate -> the same seconds of audio at dst_rate."""
    samples = np.asarray(samples, dtype=np.float64).ravel()
    if src_rate == dst_rate or samples.size == 0:
        return samples.astype(np.float64)
    if dst_rate < src_rate:
        samples = _lowpass(samples, 0.45 * dst_rate, src_rate)
    n_out = int(round(samples.size * dst_rate / float(src_rate)))
    if n_out <= 1:
        return np.zeros(0, dtype=np.float64)
    grid = np.arange(n_out, dtype=np.float64) * (float(src_rate) / dst_rate)
    return np.interp(grid, np.arange(samples.size, dtype=np.float64), samples)


# ---------------------------------------------------------------------------------------------
# THE ONE DECODER. The page sends 16 kHz 16-bit mono WAV because that is what scribeWav()
# already builds, and a harness sends whatever a piper model wrote - 22.05 kHz mono, usually.
# Both arrive here, and NOTHING ELSE DOES: there is no mp3 branch, no ffmpeg subprocess and no
# temp file, which is most of why this module cannot accidentally retain audio. It takes bytes
# and returns an array; the bytes are the caller's to drop.
#
# `wave` is standard library and reads PCM only. That is a feature: a compressed container
# arriving here is refused in a sentence rather than half-decoded into something that would
# embed to a plausible-looking vector.
# ---------------------------------------------------------------------------------------------

def read_wav(data):
    """WAV bytes -> (mono float samples in [-1, 1], rate, "") or (None, 0, why). Never raises.

    THE RATE COMES OUT OF THE FILE and is returned rather than assumed, which is why this is a
    three-tuple and not a two. The page sends 16 kHz because scribeWav() built it; a piper
    fixture sends 22.05 kHz; a different microphone will send 44.1 or 48. Hard-coding any one
    of those would not throw - it would resample the audio to the wrong length, shift every
    formant, and embed to a vector that scores like a stranger. fbank() resamples correctly
    when it is told the truth, and this is where the truth comes from.

    FAILURE MODE IT CATCHES, and it is the one that would be silent: a stereo file averaged
    to mono is fine, but a stereo file read as mono - every other sample belonging to the
    other channel - is a signal at half the sample rate with a comb filter across it. It
    embeds. It scores like a stranger. So the channel count is read and de-interleaved
    explicitly rather than assumed to be one.
    """
    if not data:
        return None, 0, "there were no bytes to read"
    try:
        with wave.open(io.BytesIO(data), "rb") as fh:
            channels = fh.getnchannels()
            width = fh.getsampwidth()
            rate = fh.getframerate()
            raw = fh.readframes(fh.getnframes())
    except Exception as exc:                                   # noqa: BLE001
        return None, 0, ("that was not PCM WAV this machine could read (%s)"
                         % type(exc).__name__)
    if not raw:
        return None, 0, "the WAV held no audio frames"
    if width == 1:                                             # unsigned 8-bit, Kaldi's least
        arr = (np.frombuffer(raw, dtype=np.uint8).astype(np.float64) - 128.0) / 128.0
    elif width == 2:
        arr = np.frombuffer(raw, dtype="<i2").astype(np.float64) / 32768.0
    elif width == 3:                                           # 24-bit packed, three bytes LE
        b = np.frombuffer(raw, dtype=np.uint8)
        b = b[: (b.size // 3) * 3].reshape(-1, 3).astype(np.int32)
        val = b[:, 0] | (b[:, 1] << 8) | (b[:, 2] << 16)
        arr = np.where(val & 0x800000, val - 0x1000000, val).astype(np.float64) / 8388608.0
    elif width == 4:
        arr = np.frombuffer(raw, dtype="<i4").astype(np.float64) / 2147483648.0
    else:
        return None, 0, ("the WAV uses %d-byte samples, which this reader does not decode"
                         % width)
    if channels > 1:
        usable = (arr.size // channels) * channels
        arr = arr[:usable].reshape(-1, channels).mean(axis=1)
    return arr, rate, ""


def seconds_of(samples, rate):
    return float(np.asarray(samples).size) / float(rate or SAMPLE_RATE)


# ---------------------------------------------------------------------------------------------
# KALDI FBANK, REIMPLEMENTED. Every step below mirrors one step of
# torchaudio.compliance.kaldi.fbank with its default arguments, in the same order, because the
# order is load-bearing: pre-emphasis after DC removal is not the same filter as pre-emphasis
# before it, and windowing after pre-emphasis is not the same as before.
# ---------------------------------------------------------------------------------------------

def _mel(freq):
    return 1127.0 * np.log(1.0 + freq / 700.0)


def _mel_banks(num_bins, padded_window, rate, low_freq, high_freq):
    """(num_bins, padded_window//2 + 1) triangular filters on the POWER spectrum."""
    num_fft_bins = padded_window // 2                 # Kaldi builds over this many, then pads 1
    nyquist = 0.5 * rate
    if high_freq <= 0.0:
        high_freq = high_freq + nyquist
    fft_bin_width = rate / float(padded_window)
    mel_low, mel_high = _mel(low_freq), _mel(high_freq)
    delta = (mel_high - mel_low) / (num_bins + 1)

    bins = np.arange(num_bins, dtype=np.float64).reshape(-1, 1)
    left = mel_low + bins * delta
    centre = mel_low + (bins + 1.0) * delta
    right = mel_low + (bins + 2.0) * delta

    mel = _mel(fft_bin_width * np.arange(num_fft_bins, dtype=np.float64)).reshape(1, -1)
    up = (mel - left) / (centre - left)
    down = (right - mel) / (right - centre)
    bank = np.maximum(0.0, np.minimum(up, down))
    return np.pad(bank, ((0, 0), (0, 1)), mode="constant")


def fbank(samples, rate=SAMPLE_RATE, cmn=True):
    """Mono float samples in [-1, 1] -> (frames, 80) float32 log-mel, mean-normalised.

    FAILURE MODE THIS SHAPE CATCHES: none. A (frames, 80) array of the right dtype is what a
    completely wrong front-end also produces. The check that matters is on the scores.
    """
    samples = np.asarray(samples, dtype=np.float64).ravel()
    if rate != SAMPLE_RATE:
        samples = resample(samples, rate, SAMPLE_RATE)
    # Kaldi reads waveforms on the int16 scale, and the energy floor and epsilon below are
    # calibrated to it. Feeding [-1, 1] here costs about 90 dB and floors the whole spectrum.
    samples = samples * 32768.0

    win = int(round(SAMPLE_RATE * FRAME_LENGTH_MS / 1000.0))          # 400
    hop = int(round(SAMPLE_RATE * FRAME_SHIFT_MS / 1000.0))           # 160
    if samples.size < win:
        return np.zeros((0, NUM_MEL_BINS), dtype=np.float32)
    n_frames = 1 + (samples.size - win) // hop                        # snip_edges=True

    idx = np.arange(win)[None, :] + hop * np.arange(n_frames)[:, None]
    frames = samples[idx]                                             # (n_frames, 400)

    frames = frames - frames.mean(axis=1, keepdims=True)              # remove_dc_offset
    # preemphasis, Kaldi's edge convention: x[0] uses itself as its predecessor
    prev = np.concatenate([frames[:, :1], frames[:, :-1]], axis=1)
    frames = frames - PREEMPH * prev

    padded = 1
    while padded < win:                                              # round_to_power_of_two
        padded *= 2                                                  # 512
    hann = 0.5 - 0.5 * np.cos(2.0 * math.pi * np.arange(win) / (win - 1))
    frames = frames * np.power(hann, POVEY_POWER)                    # the povey window

    spectrum = np.abs(np.fft.rfft(frames, n=padded)) ** 2.0          # use_power=True
    bank = _mel_banks(NUM_MEL_BINS, padded, SAMPLE_RATE, LOW_FREQ, HIGH_FREQ)
    feats = np.log(np.maximum(spectrum @ bank.T, EPSILON))

    if cmn:
        feats = feats - feats.mean(axis=0, keepdims=True)             # what WeSpeaker does next
    return feats.astype(np.float32)


# ---------------------------------------------------------------------------------------------
# THE EMBEDDING
# ---------------------------------------------------------------------------------------------

def model_ready():
    return MODEL_PATH.is_file()


def _sess():
    global _session
    if _session is None:
        if not model_ready():
            raise RuntimeError("the voiceprint model is not on disk at %s" % MODEL_PATH)
        import onnxruntime as ort                                    # noqa: PLC0415
        opts = ort.SessionOptions()
        # One thread, deliberately. This runs on the same machine as piper, whisper, the deck's
        # animation loop and the server, and a burst of eight threads for 40 ms of maths is how
        # the deck drops the frames that deck_proof then reports as a thermal red.
        opts.intra_op_num_threads = 1
        opts.inter_op_num_threads = 1
        _session = ort.InferenceSession(str(MODEL_PATH), sess_options=opts,
                                        providers=["CPUExecutionProvider"])
    return _session


def embed(samples, rate=SAMPLE_RATE):
    """Mono float samples -> a 192-float L2-normalised list. The samples are not retained."""
    feats = fbank(samples, rate)
    if feats.shape[0] < 25:                                          # under ~0.25 s of audio
        return None
    out = _sess().run(["embs"], {"feats": feats[None, :, :]})[0][0]
    vec = np.asarray(out, dtype=np.float64)
    norm = float(np.linalg.norm(vec))
    if not norm or not np.isfinite(norm):
        return None
    return (vec / norm).tolist()


def cosine(a, b):
    """Cosine of two embeddings. Both are stored L2-normalised, so this is a dot product - but
    it normalises anyway, because a caller handing in a raw vector should get a real cosine and
    not a number that is silently a magnitude."""
    x, y = np.asarray(a, dtype=np.float64), np.asarray(b, dtype=np.float64)
    nx, ny = float(np.linalg.norm(x)), float(np.linalg.norm(y))
    if not nx or not ny:
        return 0.0
    return float(np.dot(x, y) / (nx * ny))


def average(vectors):
    """The enrolment embedding: the L2-normalised mean of the per-sentence embeddings.

    WHY A MEAN AND NOT A CONCATENATION: three sentences give three points around the speaker's
    true centre, and the mean is a better estimate of that centre than any one of them. It also
    keeps the stored shape at exactly EMB_DIM whatever the sentence count, so the store's own
    hygiene check can assert one number instead of a multiple.
    """
    m = np.mean(np.asarray(vectors, dtype=np.float64), axis=0)
    norm = float(np.linalg.norm(m))
    if not norm:
        return None
    return (m / norm).tolist()


# ---------------------------------------------------------------------------------------------
# THE STORE. Flat json, one file per voice, embeddings only.
# ---------------------------------------------------------------------------------------------

AUDIO_SUFFIXES = (".wav", ".mp3", ".ogg", ".flac", ".m4a", ".webm", ".opus", ".aac", ".pcm",
                  ".raw", ".aiff", ".wma")


def slug(name):
    text = unicodedata.normalize("NFKD", str(name)).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return text or "voice"


def store_path():
    return STORE_DIR


def enrolled():
    """Every voiceprint on disk, in enrolment order. Missing folder is not an error: zero
    enrolments is a legitimate state and the whole doorman stands down in it."""
    if not STORE_DIR.is_dir():
        return []
    out = []
    for path in sorted(STORE_DIR.glob("*.json")):
        try:
            row = json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        if not isinstance(row, dict):
            continue
        vec = row.get("embedding")
        if not isinstance(vec, list) or len(vec) != EMB_DIM:
            continue
        out.append({
            "name": str(row.get("name") or ""),
            "address_form": str(row.get("address_form") or ""),
            "hands": bool(row.get("hands")),
            "embedding": vec,
            "at": row.get("at"),
            "file": path.name,
            "seconds": row.get("seconds"),
            "sentences": row.get("sentences"),
        })
    out.sort(key=lambda r: (r.get("at") or 0))
    return out


def has_hands_voice():
    return any(r["hands"] for r in enrolled())


def write(name, address_form, hands, embedding, seconds=None, sentences=None, at=None):
    """The one function that writes the store. Nothing here accepts samples, by construction."""
    if not isinstance(embedding, list) or len(embedding) != EMB_DIM:
        raise ValueError("an embedding must be exactly %d floats" % EMB_DIM)
    STORE_DIR.mkdir(parents=True, exist_ok=True)
    row = {
        "name": str(name),
        "address_form": str(address_form or ""),
        "hands": bool(hands),
        "embedding": [float(x) for x in embedding],
        "dim": EMB_DIM,
        "at": int(at if at is not None else __import__("time").time() * 1000),
        "seconds": None if seconds is None else round(float(seconds), 2),
        "sentences": None if sentences is None else int(sentences),
        "model": MODEL_PATH.name,
    }
    path = STORE_DIR / (slug(name) + ".json")
    path.write_text(json.dumps(row, indent=2), encoding="utf-8")
    return path


def forget(name):
    path = STORE_DIR / (slug(name) + ".json")
    if path.is_file():
        path.unlink()
        return True
    return False


def identify(samples, rate=SAMPLE_RATE, roster=None):
    """Who is speaking. Returns a verdict dict and never the audio it was given.

    The verdict's `who` is a name or the literal 'GUEST'. A guest carries address_form '' and
    hands False, and the empty address form is deliberate: the mandate's law is that a guest is
    addressed by no form at all rather than by a guessed one, and the cheapest way to make that
    true everywhere is for there to be no form to reach for.
    """
    rows = enrolled() if roster is None else roster
    vec = embed(samples, rate)
    if vec is None:
        return {"who": "GUEST", "address_form": "", "hands": False, "score": 0.0,
                "best": "", "known": len(rows), "why": "too little audio to embed"}
    scored = sorted(((cosine(vec, r["embedding"]), r) for r in rows),
                    key=lambda p: p[0], reverse=True)
    if not scored:
        return {"who": "GUEST", "address_form": "", "hands": False, "score": 0.0,
                "best": "", "known": 0, "why": "nobody is enrolled"}
    score, row = scored[0]
    if score >= MATCH_THRESHOLD:
        return {"who": row["name"], "address_form": row["address_form"], "hands": row["hands"],
                "score": round(score, 4), "best": row["name"], "known": len(rows),
                "why": "cosine %.3f at or above %.2f" % (score, MATCH_THRESHOLD)}
    return {"who": "GUEST", "address_form": "", "hands": False, "score": round(score, 4),
            "best": row["name"], "known": len(rows),
            "why": "closest was %s at cosine %.3f, under %.2f" % (row["name"], score,
                                                                  MATCH_THRESHOLD)}


def enrol(clips, name, address_form, hands, replace=False):
    """(row, why) - the whole of enrolment, from a list of (samples, rate) to one row on disk.

    IT LIVES HERE AND NOT IN THE ROUTE so that the refusals cannot drift apart. There are
    three of them and each one is a sentence rather than a code:

      TOO LITTLE SPEECH names the seconds still missing, because "that was not enough" tells
      a person to guess and "another 3.4 seconds, please" tells them what to do. Measured on
      the audio that arrived, not on the number of files, since three one-word answers are
      three sentences and four seconds.
      TOO FEW SENTENCES is separate from the seconds for the reason the average exists: one
      long reading gives one point around the speaker's centre, and the mean of three is a
      better estimate of that centre than a longer single take.
      A DUPLICATE is refused by name. The cost of not refusing is two rows for one larynx
      and a store where forgetting somebody only half works.

    REPLACE IS HOW A VOICE IS LEARNED AGAIN, and the ORDER of it is the point. A cold, a new
    microphone or a room with a different floor all move a larynx's measurement, so re-learning
    has to be possible - but the obvious way round, forget then enrol, deletes the house's only
    hands-privileged row and then discovers the new sentences were four seconds short. That
    leaves the Hands law stood down silently, which is the one failure this whole part exists
    to prevent. So `replace` changes nothing except which rows the duplicate check can see: the
    row of the SAME name is invisible to it, every other row is not, and write() then overwrites
    that one file. Nothing is deleted at any point, and a refusal above this line leaves the old
    row exactly where it was.

    THE SAMPLES ARE NOT RETAINED and cannot be: they arrive as an argument, they are read
    once by embed(), and the only thing that leaves this function is EMB_DIM floats and the
    row that was written. There is no branch in here that opens a file for writing audio.
    """
    vectors, seconds = [], 0.0
    for samples, rate in clips:
        arr = np.asarray(samples, dtype=np.float64).ravel()
        if arr.size == 0:
            continue
        vec = embed(arr, rate)
        if vec is None:
            continue
        vectors.append(vec)
        seconds += seconds_of(arr, rate)
    if len(vectors) < ENROL_MIN_SENTENCES:
        return None, ("I have %d usable sentence%s and I need %d - say another %d, each a "
                      "full breath long." % (len(vectors), "" if len(vectors) == 1 else "s",
                                             ENROL_MIN_SENTENCES,
                                             ENROL_MIN_SENTENCES - len(vectors)))
    if seconds < ENROL_MIN_SECONDS:
        return None, ("That was %.1f seconds of speech and I need %.1f - another %.1f "
                      "seconds, if you would." % (seconds, ENROL_MIN_SECONDS,
                                                  ENROL_MIN_SECONDS - seconds))
    mean = average(vectors)
    if mean is None:
        return None, "those sentences averaged to nothing, which means the audio was silence."
    # MATCHED ON THE FILENAME, because the filename is what write() derives from the name and
    # is therefore the only thing that decides which row gets overwritten. Comparing the names
    # themselves would let "Addi " and "addi" look like two rows to this check and one row to
    # write(), which is the way round that silently deletes somebody.
    mine = slug(name) + ".json"
    seen = [row for row in enrolled() if not (replace and row.get("file") == mine)]
    already = duplicate_of(mean, roster=seen)
    if already:
        return None, ("That is already enrolled, as %s. One voice, one row - tell me to "
                      "forget %s first if the name is wrong." % (already, already))
    path = write(name, address_form, hands, mean, seconds=seconds, sentences=len(vectors))
    return ({"name": str(name), "address_form": str(address_form or ""), "hands": bool(hands),
             "seconds": round(seconds, 2), "sentences": len(vectors), "file": path.name,
             "dim": EMB_DIM}, "")


def seal_for(verdict):
    """The three words the live seal is allowed to read: BOSS, a NAME, or GUEST.

    BOSS IS A PRIVILEGE AND NOT A ROW NUMBER. The first enrolment is the boss and carries
    hands: true, but the thing the seal is reporting is the thing the Hands gate will act
    on - so it reads BOSS for exactly the voices the gate will take a yes from, and a name
    for an enrolled voice that has no hands. If those two ever disagreed the seal would be
    reassuring about a privilege it does not have.

    IT IS COMPUTED HERE, on the server, and not in the page: the page is shown this string
    and does not derive it, so a stale tab cannot promote a guest by relabelling them.
    """
    if not isinstance(verdict, dict) or verdict.get("who") in (None, "", "GUEST"):
        return "GUEST"
    return "BOSS" if verdict.get("hands") else str(verdict["who"])


def hygiene():
    """(ok, problems, notes) - the store's four house rules, checked on disk.

    THE FOUR, and each one is here because its absence is invisible from the outside:
      gitignored   - an embedding is biometric data about a named person. The folder was
                     listed in .gitignore before it existed, and a rule that is only a
                     comment is worth nothing, so the rule is read back rather than
                     remembered.
      denied       - Read(./speaker-store/**) in .claude/settings.json, so the assistant
                     that wrote this file cannot read a voiceprint back out of it. Same
                     posture as secrets/.
      no audio     - the law is embeddings only, forever. A wav inside this folder would
                     mean some path retained a sample, and the folder is the only place
                     such a path could plausibly have put it.
      the shape    - every row is exactly EMB_DIM floats and carries no long opaque string
                     that could be audio wearing a json coat. A base64 wav in a field
                     called "sample" would pass a check that only counted the embedding.

    Notes are returned even when ok, because preflight prints the reasoning and not just
    the verdict.
    """
    problems, notes = [], []

    ignore_path = ROOT / ".gitignore"
    text = ignore_path.read_text(encoding="utf-8", errors="replace") if ignore_path.is_file() else ""
    rules = [ln.strip() for ln in text.splitlines() if ln.strip() and not ln.strip().startswith("#")]
    if "speaker-store/" in rules or "speaker-store" in rules:
        notes.append("speaker-store/ is in .gitignore, beside secrets/")
    else:
        problems.append("speaker-store/ is NOT in .gitignore, so 192 floats per named "
                        "person are one `git add -A` from a remote")

    deny_path = ROOT / ".claude" / "settings.json"
    deny = []
    try:
        deny = list(((json.loads(deny_path.read_text(encoding="utf-8")).get("permissions")
                      or {}).get("deny")) or [])
    except Exception:                                          # noqa: BLE001
        deny = []
    if any("speaker-store" in str(rule) for rule in deny):
        notes.append("Read(./speaker-store/**) is denied in .claude/settings.json")
    else:
        problems.append("speaker-store/ is not Read-denied in .claude/settings.json, so "
                        "the assistant can read a voiceprint back out of the store")

    if not STORE_DIR.is_dir():
        notes.append("the store folder does not exist yet, which is a legitimate state: "
                     "zero enrolments stands the whole doorman down")
        return (not problems), problems, notes

    strays, rows = [], 0
    for path in sorted(STORE_DIR.rglob("*")):
        if path.is_dir():
            continue
        if path.suffix.lower() in AUDIO_SUFFIXES:
            strays.append(path.name)
            continue
        if path.suffix.lower() != ".json":
            strays.append(path.name)
            continue
        rows += 1
        try:
            row = json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, OSError) as exc:
            problems.append("%s is not readable json (%s)" % (path.name, type(exc).__name__))
            continue
        vec = row.get("embedding")
        if not isinstance(vec, list) or len(vec) != EMB_DIM:
            problems.append("%s carries %s where %d floats belong"
                            % (path.name, type(vec).__name__, EMB_DIM))
        for key, value in row.items():
            if key == "embedding":
                continue
            if isinstance(value, str) and len(value) > 256:
                problems.append("%s has a %d-character string in %r - an embedding is "
                                "192 numbers and nothing here needs a blob" % (path.name,
                                                                               len(value), key))
            if isinstance(value, list) and len(value) > EMB_DIM:
                problems.append("%s has a %d-long list in %r" % (path.name, len(value), key))
    if strays:
        problems.append("the store holds %s, and the law is embeddings only, forever: an "
                        "audio file in here means some path kept a sample"
                        % ", ".join(strays[:6]))
    else:
        notes.append("%d voiceprint%s on disk, no audio of any kind among them"
                     % (rows, "" if rows == 1 else "s"))
    return (not problems), problems, notes


def duplicate_of(embedding, roster=None):
    """The name this embedding is already enrolled as, or ''. Guards re-enrolment."""
    rows = enrolled() if roster is None else roster
    for row in rows:
        if cosine(embedding, row["embedding"]) >= DUPLICATE_THRESHOLD:
            return row["name"]
    return ""
