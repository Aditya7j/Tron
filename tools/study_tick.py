"""ONE STUDY TICK, BY HAND, WITH A TIMER ON IT.

    python tools/study_tick.py                       the next topic the rotation picks
    python tools/study_tick.py --topic finance       a named topic
    python tools/study_tick.py --url <watch url>     a named talk
    python tools/study_tick.py --audio fixture.wav   a file already on disk, no yt-dlp
    python tools/study_tick.py --tools              what is installed, and nothing else
    python tools/study_tick.py --digest             today's digest line, without offering it
    python tools/study_tick.py --inject fixture.json   articles and/or bullets, given
    python tools/study_tick.py --json               one line of JSON for a harness to read

WHY A CLI AND NOT JUST THE ENDPOINT. The endpoint returns immediately by design - the Async Law
says a study never blocks a conversation - so watching a tick through it means polling and
inferring. This runs the same tick() on the calling thread and prints what each stage cost,
which is the difference between "the pipe works" and "the pipe works and here is where the
ninety seconds went". study_proof.mjs's assertion (a) drives this file for that reason.

IT SHARES THE SERVER'S GROQ CLIENT AND BUILDS NOTHING OF ITS OWN. configure() hands scholar.py
the §28 functions by reference - the same call_groq, the same call_groq_whisper with its own
8 MB refusal, the same load_config. A CLI with its own HTTP client would be a second thing
that could drift from the client the running server uses, and the drift would only show up as
a proof that passes by hand and fails in the house.

NO CREDENTIAL REACHES THIS OUTPUT. It prints a key's presence, never a key.

--inject IS THE POISON TEST'S ONLY DOOR, and it is here rather than in the harness because
scholar.tick() is the thing being tested and a harness that re-implemented the pipe around an
injected bullet would be testing its own copy. The file it reads is a JSON object with
`articles` and/or `bullets`; both go to tick()'s own injection parameters, which are documented
there at length. What it CANNOT do is weaken the guard: the Safety model is still called, on
the real API, with the real policy, and its answer still decides the tick. The fixture is
written by study_proof.mjs into _runs/ - which is gitignored - so the toxic sentences the guard
has to refuse are never committed to this repository.
"""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import scholar                                    # noqa: E402  - after the path insert
import server                                     # noqa: E402


def wire():
    scholar.configure(chat=server.call_groq, whisper=server.call_groq_whisper,
                      ready=server.groq_ready, config=lambda: server.load_config()[0])


def main():
    ap = argparse.ArgumentParser(description="Run one Scholar tick with a timer on it.")
    ap.add_argument("--topic", default=None)
    ap.add_argument("--url", default=None)
    ap.add_argument("--audio", default=None)
    ap.add_argument("--no-build", action="store_true")
    ap.add_argument("--json", action="store_true", dest="as_json")
    ap.add_argument("--tools", action="store_true")
    ap.add_argument("--digest", action="store_true")
    ap.add_argument("--prune", default=None)
    ap.add_argument("--promote", default=None)
    ap.add_argument("--inject", default=None)
    # THE WHOLE STITCHED TRANSCRIPT, TO A FILE, because --json truncates it to 4000 characters
    # and sixteen minutes of speech is forty thousand. study_proof's stitched-order assertion
    # read the truncated field once and reported that chunks three and four were missing from a
    # transcript that had them - the splitter was correct and the harness was reading a summary.
    # A file rather than a longer JSON line: this is also the evidence the lookbook quotes.
    ap.add_argument("--transcript", default=None, metavar="PATH")
    args = ap.parse_args()

    inject_articles, inject_bullets = None, None
    if args.inject:
        with open(args.inject, "r", encoding="utf-8") as fh:
            fixture = json.load(fh)
        inject_articles = fixture.get("articles")
        inject_bullets = fixture.get("bullets")

    wire()
    cfg = server.load_config()[0]
    ready, why = server.groq_ready(cfg)

    if args.tools:
        report = scholar.tool_report()
        if args.as_json:
            print(json.dumps({"tools": report, "groqReady": bool(ready)}))
            return 0 if all(r["found"] for r in report.values()) else 1
        for name, row in report.items():
            print("%-8s %-5s %s" % (name, "yes" if row["found"] else "NO", row["version"]))
            print("         %s" % (row["path"] or "(not found)"))
        print("groq     %s" % ("ready" if ready else "NOT ready - %s" % why))
        return 0 if all(r["found"] for r in report.values()) else 1

    if args.digest:
        got = scholar.digest(boss_call=str(cfg.get("boss_call") or "sir"))
        print(json.dumps(got, indent=None if args.as_json else 2))
        return 0

    if args.prune:
        ok, said = scholar.prune(args.prune)
        print(json.dumps({"ok": ok, "said": said}) if args.as_json else said)
        return 0 if ok else 1

    if args.promote:
        # BY HAND ONLY, AND SAID OUT LOUD: the gate that guards promotion lives in the server,
        # where the boss's voice can answer it. This flag exists so the proof can check what
        # promote() does to the files, not to offer a way around the gate - a CLI the boss
        # runs himself IS the consent the gate exists to collect.
        ok, said, dest = scholar.promote(args.promote)
        print(json.dumps({"ok": ok, "said": said, "dest": dest})
              if args.as_json else "%s (%s)" % (said, dest))
        return 0 if ok else 1

    if not ready:
        print("Groq is not ready: %s" % why, file=sys.stderr)
        print("The tick will run and will fail at the model, which is the honest outcome.",
              file=sys.stderr)

    t0 = time.perf_counter()
    got = scholar.tick(topic_name=args.topic, why="cli", url=args.url,
                       audio_path=args.audio, do_build=not args.no_build,
                       inject_articles=inject_articles, inject_bullets=inject_bullets)
    wall = time.perf_counter() - t0

    if args.transcript:
        with open(args.transcript, "w", encoding="utf-8") as fh:
            fh.write(got.get("transcript") or "")

    if args.as_json:
        slim = dict(got)
        slim["transcript"] = (got.get("transcript") or "")[:4000]
        slim["wallS"] = round(wall, 3)
        print(json.dumps(slim))
        return 0 if got.get("ok") else 1

    print("topic     %s" % got["topic"])
    print("outcome   %s%s" % (got["outcome"], (" - " + got["reason"]) if got["reason"] else ""))
    if got.get("warn"):
        print("warn      %s" % got["warn"][:200])
    print("sources   %d  %s" % (len(got["sources"]), ", ".join(got["sources"][:3])[:120]))
    print("chunks    %d   largest sent %s  retries %d  400s %d"
          % (got["chunks"], _bytes(got["chunkBytesMax"]), got["retries"],
             got["four_hundreds"]))
    guard = got.get("guard") or {}
    if guard:
        print("guard     ok=%s toxic=%s grounded=%s onTopic=%s limbs=%s  %s"
              % (guard.get("ok"), guard.get("toxic"), guard.get("grounded"),
                 guard.get("onTopic"), guard.get("limbs"), guard.get("why", "")[:70]))
    for bullet in got["bullets"]:
        print("  - %s" % bullet[:150])
    if got["note"]:
        print("note      %s" % got["note"])
    if got.get("deleted"):
        print("deleted   %s" % got["deleted"])
    if args.transcript:
        print("script    %s  (%d characters)" % (args.transcript, len(got.get("transcript") or "")))
    print("")
    print("          fetch %5dms   split %5dms   stt %6dms   think %5dms"
          % (got["fetchMs"], got["splitMs"], got["sttMs"], got["thinkMs"]))
    print("          guard %5dms   write %5dms   build %5dms   TOTAL %5dms  (wall %.3fs)"
          % (got["guardMs"], got["writeMs"], got["buildMs"], got["totalMs"], wall))
    budget = float(got.get("budgetS") or scholar.TICK_BUDGET_S)
    print("          budget %.0fs declared - this tick %s it by %.1fs"
          % (budget, "missed" if got["totalMs"] / 1000.0 > budget else "kept within",
             abs(budget - got["totalMs"] / 1000.0)))
    return 0 if got.get("ok") else 1


def _bytes(n):
    n = int(n or 0)
    return "%.2f MB" % (n / 1048576.0) if n else "-"


if __name__ == "__main__":
    sys.exit(main())
