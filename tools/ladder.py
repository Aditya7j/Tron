"""THE LENGTH LADDER: does the doorman still know him when he talks for longer?

    python tools/ladder.py            the table, and a LADDER json line at the end

The mandate asks for boss turns of roughly ten, twenty-five and forty-five words to score above
the floor and guests to score below it, and - if forty-five words cannot reach the floor - for the
CURVE to be reported rather than a threshold quietly moved to make a test pass. This file measures
and prints; speaker_proof.mjs section G spawns it and does the asserting.

WHY THE MEASUREMENT IS HERE AND NOT IN THE HARNESS, which is a deviation from speaker_proof's own
rule that it builds its fixtures itself rather than shelling out to python. Two things this needs
cannot be had on the other side of the wire:

  SENTENCES OF A GIVEN WORD COUNT. The rungs are defined in words, and the calibration fixtures
  in _spoken/cal are four fixed recordings per voice. Concatenating them makes a longer clip, but
  three of the four were the ENROLMENT audio, so a long rung built that way scores against a
  voiceprint partly made of itself - which is not a measurement, it is an echo.

  A ROSTER WITH ONE ROW IN IT. What the ladder is about is whether a stranger can reach the
  employer's row at length. Against the live store the strangers may have rows of their own -
  identify() would find them, correctly, and the number printed would be about the wrong pair of
  voices. The first draft of this script made exactly that mistake and reported a guest as
  admitted when the doorman had been right. identify(roster=...) takes an explicit roster so the
  comparison can be the one the gate actually turns on.

So: piper's voices, an in-memory roster, and nothing written anywhere.

WHY IT WRITES NOTHING TO THE STORE. speaker-store/ holds biometric data about named people and is
read-denied to me by standing rule. The roster here is built IN MEMORY out of piper's voices -
enrol() is never called, write() is never called, and the real store is neither read nor touched.
`identify(roster=...)` takes an explicit roster precisely so that a measurement can be made
against voices nobody has to live with afterwards.

AND NO VECTOR IS PRINTED, only cosines.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json  # noqa: E402

import say                 # noqa: E402
import voiceprint as vp    # noqa: E402

# Three piper voices. The first is the stand-in for the employer and the other two are the
# strangers whose scores have to stay under the floor however long they talk.
BOSS, GUESTS = "en_US-ryan-high", ["en_US-joe-medium", "en_GB-alan-medium"]

# THE RUNGS, and the word counts are the mandate's. The sentences are ordinary dictation and not
# a pangram: what is being measured is a larynx over a duration, so the text has to be the sort
# of thing somebody actually says to this machine.
RUNGS = [
    ("~10 words", "Put the vendor call in my calendar for tomorrow at four o'clock please."),
    ("~25 words", "I would like you to look through my notes for the cold brew recipe and tell "
                  "me what the steeping time is, because I have forgotten it again this week."),
    ("~45 words", "Before you do anything else this morning I want you to check whether the "
                  "roasting schedule leaves us enough time for the wholesale order, and if it "
                  "does not, draft a short note to the team explaining which deliveries will "
                  "have to move to Thursday afternoon instead."),
]

# THE ENROLMENT TEXT, which is deliberately not any of the rungs above. Scoring a clip against an
# enrolment made from that same clip measures nothing but the determinism of the model.
ENROL = [
    "The mornings here are quiet before the grinder starts, and I rather prefer them that way.",
    "There is a crate of the Colombian left on the loading dock that nobody has signed for yet.",
    "Remind me to speak to the landlord about the window in the back room before the weekend.",
]


def clip(text, model):
    """(samples, rate) for one spoken line. synthesise() hands back BYTES and not a path."""
    wav, reason, _source = say.synthesise(text, model)
    if not wav:
        raise SystemExit("piper could not speak: %s" % reason)
    # read_wav is a THREE-tuple: the rate comes out of the file and is never assumed. piper
    # writes 22.05 kHz here and the model wants 16 - fbank() resamples, but only when it is
    # told the truth, so the rate is carried and not dropped.
    samples, rate, why = vp.read_wav(wav)
    if samples is None:
        raise SystemExit("could not read the wav piper wrote: %s" % why)
    return samples, rate


def row(model, hands):
    """One in-memory roster row, enrolled from ENROL and never written to disk."""
    vecs = []
    seconds = 0.0
    for line in ENROL:
        samples, rate = clip(line, model)
        seconds += vp.seconds_of(samples, rate)
        vecs.append(vp.embed(samples, rate))
    return {"name": model.split("-")[1], "address_form": "sir", "hands": hands,
            "embedding": vp.average(vecs), "seconds": round(seconds, 2)}


FOUND = {"rungs": [], "windows": [], "curve": [],
         "floor": 0.0, "near": 0.0, "window": {}}


def main():
    if not vp.model_ready():
        raise SystemExit("no voiceprint model on disk - nothing to measure")
    FOUND["floor"] = vp.MATCH_THRESHOLD
    FOUND["near"] = vp.NEAR_THRESHOLD
    FOUND["window"] = {"seconds": vp.WINDOW_SECONDS, "hop": vp.WINDOW_HOP_SECONDS,
                       "min": vp.WINDOW_MIN_SECONDS, "gate": vp.WINDOW_GATE_RATIO,
                       "max": vp.WINDOW_MAX}
    print("floor %.2f   near band %.2f   window %.1fs hop %.1fs gate %.2f\n"
          % (vp.MATCH_THRESHOLD, vp.NEAR_THRESHOLD, vp.WINDOW_SECONDS,
             vp.WINDOW_HOP_SECONDS, vp.WINDOW_GATE_RATIO))
    # ONE ROW, AND THE ROW IS THE EMPLOYER'S. The first draft of this script enrolled all three
    # voices and then reported joe as "a guest, admitted" - which was the script being wrong and
    # the doorman being right: joe had a row of his own and identify() found it. What the ladder
    # is about is whether a STRANGER can reach the employer's row, so the strangers must have no
    # row to be recognised by. Their score below is a cosine against his voiceprint and nothing
    # else, which is the number the gate actually turns on.
    roster = [row(BOSS, True)]
    for one in roster:
        print("  enrolled %-6s hands=%-5s from %.1fs of speech"
              % (one["name"], one["hands"], one["seconds"]))
    print("  the other two voices are enrolled NOWHERE, which is what makes them guests\n")
    boss = roster[0]["name"]
    print("  %-10s %-6s %5s %6s %7s %7s %6s %4s  %s"
          % ("rung", "voice", "words", "secs", "whole", "best", "wins", "win", "verdict"))
    for label, text in RUNGS:
        for model in [BOSS] + GUESTS:
            samples, rate = clip(text, model)
            verdict = vp.identify(samples, rate, roster=roster)
            FOUND["rungs"].append({
                "rung": label, "voice": model.split("-")[1], "boss": model == BOSS,
                "words": len(text.split()), "seconds": round(vp.seconds_of(samples, rate), 2),
                "whole": verdict["whole"], "score": verdict["score"],
                "windows": verdict["windows"], "seal": vp.seal_for(verdict),
                "above": verdict["score"] >= vp.MATCH_THRESHOLD})
            # The whole-clip number and the windowed number side by side: the gap between them
            # is the entire case for windowing, and a rung where the gap is nought is a rung
            # that did not need it.
            gain = verdict["score"] - verdict["whole"]
            print("  %-10s %-6s %5d %6.2f %7.4f %7.4f %+6.4f %4d  %s / %s"
                  % (label, model.split("-")[1], len(text.split()),
                     vp.seconds_of(samples, rate), verdict["whole"], verdict["score"], gain,
                     verdict["windows"], vp.seal_for(verdict),
                     ("ABOVE" if verdict["score"] >= vp.MATCH_THRESHOLD else "under") +
                     ("  <-- THE BOSS, REFUSED" if model == BOSS
                      and verdict["score"] < vp.MATCH_THRESHOLD else "") +
                     ("  <-- A GUEST, ADMITTED" if model != BOSS
                      and verdict["score"] >= vp.MATCH_THRESHOLD else "")))
            del samples
        print()
    print("  (boss row is %r; a rung reading UNVERIFIED is in the near band, which is still a "
          "guest at the gate)\n" % boss)

    # ---- THE CASE WINDOWING IS ACTUALLY FOR, because the ladder above cannot show it.
    #
    # Every rung above gains +0.0000 for the boss: his whole-clip reading is already his best
    # one, so the maximum has nothing to find. That is not windowing failing - it is the FIXTURE
    # having no defect to cure. A piper clip is wall-to-wall speech by one speaker with no room,
    # no pause and nobody else in it, and windowing exists to throw away exactly those things.
    # So they are put in deliberately here, and the two numbers are printed side by side: what
    # the whole clip says, and what the best three seconds of it say.
    print("  THE TWO CLIPS THE WINDOWS ARE FOR (whole-clip reading vs best window):\n")
    import numpy as np
    speech, rate = clip(RUNGS[1][1], BOSS)
    guest, grate = clip(RUNGS[0][1], GUESTS[0])
    hush = np.zeros(int(8.0 * rate), dtype=np.asarray(speech).dtype)
    # THE INTERRUPTION IS RESAMPLED-BY-CONSTRUCTION, not concatenated blind: both clips come from
    # piper at the same rate, and splicing two different rates would make a third voice out of a
    # sample-rate error rather than out of two larynxes. Asserted rather than assumed.
    if grate != rate:
        raise SystemExit("the two fixtures disagree about rate (%d vs %d)" % (grate, rate))
    cases = [
        ("he speaks, then eight seconds of room",
         np.concatenate([np.asarray(speech), hush])),
        ("a guest talks over the middle of his sentence",
         np.concatenate([np.asarray(speech)[:int(2.5 * rate)], np.asarray(guest),
                         np.asarray(speech)[int(2.5 * rate):]])),
    ]
    for label, samples in cases:
        verdict = vp.identify(samples, rate, roster=roster)
        FOUND["windows"].append({
            "case": label, "seconds": round(vp.seconds_of(samples, rate), 2),
            "whole": verdict["whole"], "score": verdict["score"],
            "windows": verdict["windows"], "seal": vp.seal_for(verdict),
            "above": verdict["score"] >= vp.MATCH_THRESHOLD})
        print("  %-44s %6.2fs  whole %7.4f  best %7.4f  %+7.4f  %2d win  %s"
              % (label, vp.seconds_of(samples, rate), verdict["whole"], verdict["score"],
                 verdict["score"] - verdict["whole"], verdict["windows"],
                 vp.seal_for(verdict)))

    # ---- AND THE DEGRADATION CURVE, which is what decides whether the near band is reachable
    # at all. The band between NEAR_THRESHOLD and MATCH_THRESHOLD is where the doorman says
    # UNVERIFIED instead of nothing, and a band no real input ever lands in is a line of code
    # that has never run. The honest way to find out is to spoil the boss's own voice by degrees
    # until it stops being recognisable, and read off where it passes through.
    #
    # NOISE AND NOT A DIFFERENT SPEAKER, because a loud room is the case this is FOR: the
    # employer, in his own voice, with the grinder going. A mixture of two speakers would be
    # measuring something else and would reach the band for the wrong reason.
    print("\n  THE DEGRADATION CURVE - his own voice, buried by degrees:\n")
    rng = np.random.default_rng(20260927)
    speech = np.asarray(clip(RUNGS[1][1], BOSS)[0], dtype=np.float64)
    power = float(np.sqrt(np.mean(np.square(speech))))
    print("  %-8s %8s %7s %7s %4s  %s" % ("noise", "SNR dB", "whole", "best", "win", "seal"))
    for amount in (0.0, 0.5, 1.0, 1.5, 2.0, 3.0, 5.0, 8.0):
        noisy = speech + rng.normal(0.0, power * amount, speech.shape) if amount else speech
        snr = 99.0 if not amount else 20.0 * float(np.log10(1.0 / amount))
        verdict = vp.identify(np.clip(noisy, -1.0, 1.0), rate, roster=roster)
        seal = vp.seal_for(verdict)
        FOUND["curve"].append({
            "noise": amount, "snrDb": round(snr, 1), "whole": verdict["whole"],
            "score": verdict["score"], "seal": seal,
            "near": vp.NEAR_THRESHOLD <= verdict["score"] < vp.MATCH_THRESHOLD})
        band = ("  <-- THE NEAR BAND, and this is the input that reaches it"
                if vp.NEAR_THRESHOLD <= verdict["score"] < vp.MATCH_THRESHOLD else "")
        print("  x%-7.1f %8.1f %7.4f %7.4f %4d  %-10s%s"
              % (amount, snr, verdict["whole"], verdict["score"], verdict["windows"],
                 seal, band))


if __name__ == "__main__":
    main()
    # TAGGED AND LAST, for the reason utter.py gives: say.py writes its own progress lines to
    # stdout, so a caller that json-parsed the whole stream would choke on a cache miss and not
    # on a cache hit - the worst kind of intermittent. One line, one prefix, found by search.
    print("LADDER " + json.dumps(FOUND))
