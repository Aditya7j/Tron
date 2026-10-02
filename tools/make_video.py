"""THE DIRECTOR'S HAND CRANK - §35 PART 2's manual path.

    python tools/make_video.py --topic "micro-saas pricing"
    python tools/make_video.py --topic "micro-saas pricing" --json
    python tools/make_video.py --topic "nothing at all" --json     the graceful-empty path
    python tools/make_video.py --probe                             what is installed, only

A THIN CLI OVER director.py, AND NOTHING ELSE - the shape tools/study_tick.py has over
scholar.py, for the same reason. The pipeline has to live in a root module because server.py
imports it to answer "make a video about X", and a script under tools/ is not importable
without the path games that only a script should be doing. So the policy, the filtergraphs and
the budgets are all in director.py, this file holds the argument parsing and the printing, and
there is exactly one implementation of the Director rather than one per entry point.

WHY A CLI EXISTS AT ALL when the spoken path exists: the endpoint returns in milliseconds and
renders on a daemon thread, which is correct for a conversation and useless for watching where
the hundred and eighty seconds went. This runs the pipeline on the calling thread and prints
the cost of each stage. director_proof drives this file for that reason.

NO CREDENTIAL REACHES THIS OUTPUT. config.json is read only inside director.py, and only
through server.load_config().
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import director                                   # noqa: E402  - after the path insert


def main():
    ap = argparse.ArgumentParser(description="Make a short video from the boss's own notes.")
    ap.add_argument("--topic", default=None)
    ap.add_argument("--json", action="store_true", dest="as_json")
    ap.add_argument("--probe", action="store_true")
    ap.add_argument("--keep-parts", action="store_true",
                    help="leave the scene mp4s and per-line WAVs on disk")
    ap.add_argument("--no-bus", action="store_true",
                    help="run make() without the progress bus, for a predicate-level proof")
    args = ap.parse_args()

    if args.probe:
        state = director.probe()
        print(json.dumps(state) if args.as_json else json.dumps(state, indent=2))
        return 0 if (state["ffmpeg"] and state["ffprobe"] and state["voice"]) else 1

    if not args.topic:
        ap.error("--topic is required (or --probe)")

    # ON THIS THREAD EITHER WAY. MANAGER.request() is the server's door and returns before the
    # work starts, which is the wrong shape for a hand crank: the process would exit while the
    # daemon thread was still on scene two. --no-bus skips the job bus for a predicate-level
    # proof; both paths render here and now.
    out = (director.make(args.topic, keep_parts=args.keep_parts) if args.no_bus
           else director.direct(args.topic, keep_parts=args.keep_parts))
    if args.as_json:
        # ONE LINE, LAST, so a harness can read the tail and ignore anything a module printed to
        # stdout on the way. No indent for the same reason.
        print(json.dumps(out))
    else:
        probe = out.get("probe") or {}
        print("")
        print("  topic      : %s" % out.get("topic"))
        print("  answer     : %s" % out.get("answer"))
        print("  script     : %d beats, prose by %s, citing %s"
              % (out.get("beats") or 0, out.get("source") or "-",
                 ", ".join(out.get("cited") or []) or "nothing"))
        print("  voiceover  : %.1fs  (budget %.0f-%.0fs, %s)"
              % (out.get("voiceS") or 0.0, director.VOICE_MIN_S, director.VOICE_MAX_S,
                 "inside" if out.get("budgetOk") else "OUTSIDE"))
        print("  captions   : %d cues%s"
              % (out.get("cues") or 0,
                 (", %d line(s) trimmed to hold the ceiling" % out["trimmed"])
                 if out.get("trimmed") else ""))
        print("  scenes     : title + %d beats%s"
              % (out.get("beats") or 0, " + chart" if out.get("chart") else " (no chart)"))
        print("  wall       : %.1fs  (budget %.0fs)" % (out.get("wallS") or 0.0,
                                                        director.WALL_MAX_S))
        print("  file       : %s" % (out.get("path") or "-"))
        if probe:
            print("  ffprobe    : %d video, %d audio, %.2fs, %s/%s, %d bytes"
                  % (probe.get("video", 0), probe.get("audio", 0), probe.get("durationS", 0.0),
                     probe.get("vcodec") or "-", probe.get("acodec") or "-",
                     probe.get("bytes", 0)))
        if out.get("job"):
            print("  job        : %s" % out["job"])
        if out.get("why"):
            print("  why        : %s" % out["why"])
        print("")
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
