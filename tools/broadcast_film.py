"""THE BROADCASTER'S HAND CRANK - §40's manual and proof path.

    python tools/broadcast_film.py --status
    python tools/broadcast_film.py --connect                     the boss's one consent click
    python tools/broadcast_film.py --channel                     prerequisite (b), checked
    python tools/broadcast_film.py --scopes --json               the scope decision, as evidence
    python tools/broadcast_film.py --discovery --json            re-prove it against Google
    python tools/broadcast_film.py --card    <folder> --json     what the boss would approve
    python tools/broadcast_film.py --upload  <folder> --json     unlisted, on this thread
    python tools/broadcast_film.py --publish <videoId>           the flip, bypassing no gate
    python tools/broadcast_film.py --verify  <videoId> --json
    python tools/broadcast_film.py --recent --json               the lost-id recovery path

A THIN CLI OVER broadcast.py AND NOTHING ELSE - tools/make_video.py's shape over director.py,
for its reason: the client has to live in a root module because server.py imports it, and a
script under tools/ is not importable without path games that only a script should do. So the
scopes, the prohibition and the package all live in broadcast.py, this file holds the argument
parsing and the printing, and there is exactly one Broadcaster rather than one per entry point.

WHY A CRANK EXISTS when the spoken path exists: the endpoint returns in milliseconds and uploads
on a daemon thread, which is right for a conversation and useless for watching where the bytes
went. This runs on the calling thread and prints each stage. broadcaster_proof drives this file.

AND --publish IS NOT A BACK DOOR, which is the one thing about this file worth being careful
about. It bypasses the SPOKEN gate because a harness has no voice, and it bypasses nothing else:
broadcast.publish() refuses without the wide scope, publish_video.py's ledger guard is the hand's
and not the client's, and the Delete Prohibition is in the transport where no entry point can
reach around it. A human running this is a human at this machine's own keyboard, which this house
has always treated as the boss.

NO CREDENTIAL REACHES THIS OUTPUT. The token is read only inside broadcast.py, and --status
prints a digest.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import broadcast                                   # noqa: E402  - after the path insert


def jdump(obj, as_json, indent=2):
    # ONE LINE, LAST, when --json: a harness reads the tail and ignores anything a module
    # printed on the way. No indent for the same reason.
    print(json.dumps(obj) if as_json else json.dumps(obj, indent=indent))


def main():
    ap = argparse.ArgumentParser(description="Put the Director's films on YouTube.")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--connect", action="store_true")
    ap.add_argument("--channel", action="store_true")
    ap.add_argument("--scopes", action="store_true")
    ap.add_argument("--discovery", action="store_true")
    ap.add_argument("--recent", action="store_true")
    ap.add_argument("--card", default="")
    ap.add_argument("--upload", default="")
    ap.add_argument("--publish", default="")
    ap.add_argument("--verify", default="")
    ap.add_argument("--no-bus", action="store_true",
                    help="run without the progress bus, for a predicate-level proof")
    ap.add_argument("--json", action="store_true", dest="as_json")
    args = ap.parse_args()
    bus = not args.no_bus

    if args.status:
        jdump(broadcast.status(), args.as_json)
        return 0 if broadcast.status()["state"] == "connected" else 1

    if args.scopes:
        jdump(broadcast.scope_report(), args.as_json)
        return 0

    if args.discovery:
        got = broadcast.discovery_check()
        jdump(got, args.as_json)
        return 0 if got["ok"] else 1

    if args.connect:
        # THE ONE CLICK THAT IS THE BOSS'S. This opens his browser and waits; it cannot
        # press Allow, and §40 PART 0 names the consent as a prerequisite for that reason.
        got = broadcast.connect(background=False)
        jdump(got, args.as_json)
        if not args.as_json and got.get("url"):
            print("\n  the browser would not open - paste this into it yourself:\n  %s\n"
                  % got["url"])
        return 0 if got.get("state") == "connected" else 1

    if args.channel:
        got = broadcast.channel()
        jdump(got, args.as_json)
        return 0 if got["ok"] else 1

    if args.recent:
        got = broadcast.recent_uploads()
        jdump(got, args.as_json)
        return 0 if got["ok"] else 1

    if args.card:
        got = broadcast.card(args.card)
        if args.as_json:
            jdump(got, True)
        elif not got["ok"]:
            print("\n  refused   : %s\n" % got["why"])
        else:
            print("")
            print("  title     : %s   (%d/%d)" % (got["title"], got["titleChars"],
                                                  broadcast.TITLE_MAX))
            print("  tags      : %s   (%d/%d chars)"
                  % (", ".join(got["tags"]), got["tagChars"], broadcast.TAGS_TOTAL_MAX))
            print("  thumbnail : %s   (%d bytes)" % (got["thumbnail"] or "-",
                                                     got["thumbnailBytes"]))
            print("  privacy   : %s, and it asks for %s" % (got["privacy"], got["asks"]))
            print("  description (%d/%d):" % (got["descriptionChars"], broadcast.DESC_MAX))
            for line in got["description"].splitlines():
                print("      | %s" % line)
            print("")
        return 0 if got["ok"] else 1

    if args.upload:
        got = broadcast.upload(args.upload, report=bus)
        if args.as_json:
            jdump(got, True)
        else:
            print("")
            print("  folder    : %s" % got["folder"])
            print("  title     : %s" % got["title"])
            print("  video     : %s" % (got["videoId"] or "-"))
            print("  url       : %s" % (got["url"] or "-"))
            print("  privacy   : %s" % (got["privacy"] or "-"))
            print("  bytes     : %d in %d chunk(s), %d resume(s), %d retry(ies)"
                  % (got["bytes"], got["chunks"], got.get("resumes") or 0,
                     got.get("retries") or 0))
            print("  thumbnail : %s" % ("set" if got["thumb"] else "not set"))
            print("  wall      : %.1fs" % (got["elapsedS"] or 0.0))
            if got.get("job"):
                print("  job       : %s" % got["job"])
            if got["why"]:
                print("  why       : %s" % got["why"])
            print("")
        return 0 if got["ok"] else 1

    if args.publish:
        got = broadcast.publish(args.publish, report=bus)
        if args.as_json:
            jdump(got, True)
        else:
            print("")
            print("  video     : %s" % got["videoId"])
            print("  privacy   : %s -> %s" % (got["from"] or "-", got.get("privacy") or "-"))
            print("  url       : %s" % got["url"])
            if got["why"]:
                print("  why       : %s" % got["why"])
            print("")
        return 0 if got["ok"] else 1

    if args.verify:
        got = broadcast.verify(args.verify)
        jdump(got, args.as_json)
        return 0 if got["ok"] else 1

    ap.error("nothing to do - try --status, --card <folder> or --upload <folder>")


if __name__ == "__main__":
    sys.exit(main())
