"""utter.py - turn a sentence into a wave file a harness can say out loud.

WHY THIS EXISTS. The mandate says every behavioural fixture runs twice: once typed, for
determinism, and once SPOKEN, through the real microphone via the Open Ear, with real
recognition. A harness cannot talk, so piper talks for it and this module is the mouth.

HOW THE SPOKEN PASS ACTUALLY WORKS, measured rather than assumed. The obvious route -
Chrome's --use-file-for-fake-audio-capture, which presents a .wav to the page as a capture
device - DOES reach getUserMedia (track label "Fake Default Audio Input", 48 kHz, and an
analyser on it shows the utterance) and DOES NOT reach webkitSpeechRecognition: with the
fake file armed the recogniser fired audiostart and speechstart and returned zero results
and zero errors, because Chrome's speech input opens the system default input device
directly instead of taking the page's capture stream. --headless=new returns no transcripts
at all. So the spoken pass is ACOUSTIC: this file's wave goes out of the default render
device, crosses the room, and arrives at the microphone array, where Chrome's own
recogniser hears it and produces words nobody in this project typed.

TWO PROFILES, because the two paths want opposite things.
  room(...)  - what the speakers play. Piper's native 22050 Hz (WebAudio resamples on
               decode, so resampling here would only add a generation of error), and short
               padding: a lead so the recogniser has a floor to measure and a brief tail,
               nothing more, because this file is played once and not looped.
  device(...) - what --use-file-for-fake-audio-capture wants, still worth having because
               the fake device IS the right tool for the analyser, the VAD and the barge-in
               gate, which do read the page's own stream. 48 kHz because that is the rate
               the fake device reports - hand it 22050 and it plays back fast and high -
               and a long tail because the file LOOPS for as long as the browser lives:
               without it the loop point lands mid-word and the analyser sees one
               unbroken sentence forever. The path handed to the flag must be ABSOLUTE; a
               relative one is silently ignored and the real microphone is used instead.

Standard library only - and in 3.13 that means no audioop (PEP 594 removed it), so the
resampler below is nine lines of linear interpolation rather than a call.
"""

import array
import hashlib
import io
import os
import pathlib
import sys
import wave

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DEVICE_RATE = 48000       # what Chrome's fake capture device reports
# THE BOSS DOES NOT SOUND LIKE GALAXY, deliberately. Galaxy speaks in say.DEFAULT_MODEL;
# a fixture that spoke in the same voice would make the barge-in log unreadable, because
# the whole question there is "was that him or was that me". A different voice is a
# different trace.
BOSS_MODEL = "en_GB-alan-medium"
ROOM_LEAD_S = 0.20        # silence before the words, out of the speakers
ROOM_TAIL_S = 0.30
DEVICE_LEAD_S = 0.45      # the recogniser needs a floor to measure
DEVICE_TAIL_S = 2.60      # so the loop point is never mid-syllable


def _resample(samples, src_rate, dst_rate):
    """Linear interpolation. Good enough for speech a recogniser will re-digitise anyway."""
    if src_rate == dst_rate:
        return samples
    n = int(len(samples) * dst_rate / src_rate)
    out = array.array("h", bytes(2 * n))
    ratio = src_rate / dst_rate
    last = len(samples) - 1
    for i in range(n):
        pos = i * ratio
        j = int(pos)
        if j >= last:
            out[i] = samples[last]
            continue
        frac = pos - j
        out[i] = int(samples[j] + (samples[j + 1] - samples[j]) * frac)
    return out


def _loud(samples, target_rms=0.22, ceiling=0.97):
    """RMS-normalise with a soft limiter.

    WHY: piper's wave peaks at full scale and still measures only 0.027 RMS in the room at
    two feet, because speech is mostly quiet with brief peaks. Chrome opens the microphone
    with noiseSuppression and autoGainControl on - which is what the spec asks for - and a
    far-field signal that faint is exactly what a noise suppressor is built to remove. Peak
    gain cannot help (the peaks are already at the rail); what raises the AVERAGE is
    compression. tanh is the limiter: it is monotonic, has no knee to tune, and the
    distortion it adds lands where speech recognisers are least sensitive.
    """
    import math

    n = len(samples)
    if not n:
        return samples
    total = 0
    for v in samples:
        total += v * v
    rms = math.sqrt(total / n) / 32768.0
    if rms <= 0:
        return samples
    gain = target_rms / rms
    if gain <= 1.0:
        return samples
    lim = ceiling * 32767.0
    out = array.array("h", bytes(2 * n))
    for i in range(n):
        x = samples[i] * gain / lim
        out[i] = int(lim * math.tanh(x))
    return out


def _mono(frames, channels):
    data = array.array("h")
    data.frombytes(frames)
    if channels == 1:
        return data
    out = array.array("h", bytes(2 * (len(data) // channels)))
    for i in range(len(out)):
        out[i] = data[i * channels]
    return out


def _speak(text, model, gain, rate, lead_s, tail_s, loud=0.0):
    """The sentence as mono 16-bit PCM at `rate`, padded. Returns (bytes, rate)."""
    import say                                        # noqa: PLC0415  (path set above)

    raw, why, _src = say.synthesise(str(text), model or BOSS_MODEL)
    if raw is None:
        raise RuntimeError("piper would not speak %r: %s" % (text, why))
    with wave.open(io.BytesIO(raw)) as src:
        native = src.getframerate()
        samples = _mono(src.readframes(src.getnframes()), src.getnchannels())
    out_rate = native if rate is None else rate
    samples = _resample(samples, native, out_rate)
    if loud:
        samples = _loud(samples, loud)
    if gain != 1.0:
        for i in range(len(samples)):
            samples[i] = max(-32768, min(32767, int(samples[i] * gain)))
    lead = array.array("h", bytes(2 * int(out_rate * lead_s)))
    tail = array.array("h", bytes(2 * int(out_rate * tail_s)))
    return (lead + samples + tail).tobytes(), out_rate


def _write(path, body, rate, text):
    path = str(path)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with wave.open(path, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(rate)
        out.writeframes(body)
    return {"path": os.path.abspath(path), "bytes": len(body) + 44, "rate": rate,
            "seconds": round(len(body) / 2 / rate, 3), "text": str(text)}


ROOM_RMS = 0.22           # the compressed level the room path is normalised to


def room(path, text, model=None, gain=1.0, loud=ROOM_RMS):
    """For the speakers: piper's own rate, short padding, compressed, played once."""
    body, rate = _speak(text, model, gain, None, ROOM_LEAD_S, ROOM_TAIL_S, loud)
    return _write(path, body, rate, text)


def device(path, text, model=None, gain=1.0, loud=0.0):
    """For --use-file-for-fake-audio-capture: 48 kHz, long tail, looped forever. NOT
       compressed by default - the fake device feeds the analyser and the VAD, and those
       two want piper's real dynamics, not a level chosen to survive a room."""
    body, rate = _speak(text, model, gain, DEVICE_RATE, DEVICE_LEAD_S, DEVICE_TAIL_S, loud)
    return _write(path, body, rate, text)


def cached(text, kind="room", model=None, gain=1.0, where=None):
    """Synthesis is the slow part of a spoken fixture; a sentence is spoken many times
       across a round of proofs, so the wave is keyed by everything that shapes it and
       written once. Returns the same dict as room()/device()."""
    key = hashlib.sha1(("%s|%s|%s|%s|%s|%s" % (kind, text, model or BOSS_MODEL, gain,
                                               DEVICE_RATE, ROOM_RMS)
                        ).encode("utf-8")).hexdigest()[:16]
    folder = pathlib.Path(where or (ROOT / "_spoken"))
    path = folder / ("%s-%s.wav" % (kind, key))
    if path.exists():
        with wave.open(str(path)) as w:
            return {"path": str(path.resolve()), "bytes": path.stat().st_size,
                    "rate": w.getframerate(),
                    "seconds": round(w.getnframes() / w.getframerate(), 3),
                    "text": str(text), "cached": True}
    made = (device if kind == "device" else room)(path, text, model, gain)
    made["cached"] = False
    return made


if __name__ == "__main__":
    # utter.py [--device] [--gain G] <out.wav|-> <sentence...>     printed as JSON
    import json
    argv = sys.argv[1:]
    kind = "room"
    gain = 1.0
    while argv and argv[0].startswith("--"):
        flag = argv.pop(0)
        if flag == "--device":
            kind = "device"
        elif flag == "--gain":
            gain = float(argv.pop(0))
        else:
            print("unknown flag %s" % flag)
            raise SystemExit(2)
    if len(argv) < 2:
        print("usage: utter.py [--device] [--gain G] <out.wav|-> <sentence>")
        raise SystemExit(2)
    out, sentence = argv[0], " ".join(argv[1:])
    made = (cached(sentence, kind, gain=gain) if out == "-"
            else (device if kind == "device" else room)(out, sentence, gain=gain))
    # TAGGED, because say.py prints its own progress line to stdout and a caller that
    # json-parsed the whole of stdout would choke on the first cache miss and not on the
    # second - the worst kind of intermittent.
    print("UTTER " + json.dumps(made))
