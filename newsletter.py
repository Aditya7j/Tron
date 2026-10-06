#!/usr/bin/env python3
"""newsletter.py - THE PUBLISHER's composition half: subscribers, and a draft from the notes.

WHY THIS IS A ROOT MODULE AND NOT A SCRIPT, which is the shape broadcast.py and director.py
already have and for their reason: two tool scripts need it (tools/compose_newsletter.py and
tools/send_newsletter.py both read the subscriber list), and publisher_proof needs to exercise
it as predicates with no server, no network and no card. A script under tools/ is not
importable without the path games only a script should be doing.

WHAT IT WILL NOT DO, and each of these is a refusal with a sentence rather than an invention:

  IT WILL NOT COMPOSE WITHOUT A SUBSCRIBER LIST. The file is the boss's, maintained by hand,
    and its absence is a thing he must be told about - exactly as broadcast.disclosure()
    refuses without `youtube_disclosure` rather than writing a legal line on his behalf.
  IT WILL NOT CITE WHAT IT CANNOT BACK. A newsletter body claims to be drawn from the boss's
    own research; if semantic recall returns nothing, there is no newsletter, because the
    alternative is prose with a fabricated provenance line under it.
  IT WILL NOT INVENT CODE. Every snippet in a draft is lifted VERBATIM out of a cited note's
    own text and is checked back against it before it ships - see snippets(). A plausible
    code sample the notes do not contain is the worst thing this file could produce, because
    it is the one kind of error a reader cannot catch and will paste into a terminal.
  IT NAMES NOTES BY ID AND NEVER BY FILENAME, which is the Broadcaster's rule and its reason:
    a newsletter is public, and "2026-09-30-19-react-js.md" tells a stranger what the boss was
    reading and when. The ids are meaningless outside this house and are exactly what makes
    the provenance auditable by the one person entitled to audit it.

THE SEND IS NOT HERE. Nothing in this module opens a socket or touches Gmail; it composes and
it reads a json file. tools/send_newsletter.py is the hand that goes out, it is gated by the
Chain Card like every other hand, and it re-reads this file at send time rather than trusting
a count that travelled on a proposal.
"""
import hashlib
import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent
SUBSCRIBERS_PATH = ROOT / "newsletter_subscribers.json"

# A newsletter subject is the most-read line in it, and a long one is truncated by every mail
# client on the subscribers' phones. 120 is generous and still inside the fold.
SUBJECT_MAX = 120
BODY_MAX = 20000
SNIPPET_MAX = 1600          # one snippet. Longer than this is a file, not an illustration.
SNIPPETS_MAX = 3            # beyond three, a newsletter is a repository
CITE_MAX = 6                # how many ids the provenance line names

# THE SAME STRICTNESS AS send_email.py's, deliberately restated rather than imported: this one
# validates a FILE the boss edits by hand, and the two have different jobs even where they
# agree. A subscriber list with a typo in it is a send that fails halfway down the list.
ADDRESS_RE = re.compile(r"^[^@\s,;:<>\"'()\[\]]{1,64}@[A-Za-z0-9.-]{1,255}\.[A-Za-z]{2,24}$")

# A fenced block in a markdown note.
FENCE_RE = re.compile(r"```([A-Za-z0-9_+-]{0,16})[ \t]*\r?\n(.*?)```", re.S)

NO_LIST = ("there is no subscriber list yet - create newsletter_subscribers.json at the "
           "project root and nothing will be sent to anybody until you have")
BAD_LIST = ("newsletter_subscribers.json is not readable as a subscriber list - it wants a "
            "\"subscribers\" array of objects with an \"email\", and nothing will be sent "
            "until it is")
EMPTY_LIST = ("the subscriber list has no usable address in it, so there is nobody to send "
              "to - put one in newsletter_subscribers.json first")
NO_GROUND = ("I have nothing in your notes about that, sir, so there is no newsletter to "
             "write - I will not compose one on a subject your own research does not cover")


def digest(value):
    """A sha256 prefix. The ONLY form an address may take in a log, a ledger or a report.

    The house's standing law is that no account email appears anywhere written except as a
    digest, and a subscriber list is a list of other people's addresses - strictly worse to
    leak than the boss's own. So the ledger row records who was written to by digest, which
    is enough to prove a send happened to a particular subscriber and useless to anybody who
    does not already hold the list.
    """
    return hashlib.sha256(str(value or "").encode("utf-8")).hexdigest()[:16]


def subscribers(path=None):
    """(rows, why) - the boss's list, validated, or a named refusal.

    NEVER WRITTEN BY THIS HOUSE. The file is read-only to every tool: a machine that could
    add an address to its own mailing list is a machine that can mail a stranger.
    """
    target = pathlib.Path(path) if path else SUBSCRIBERS_PATH
    if not target.exists():
        return [], NO_LIST
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return [], BAD_LIST
    rows = data.get("subscribers") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        return [], BAD_LIST
    out, seen = [], set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        email = str(row.get("email") or "").strip()
        if not email or not ADDRESS_RE.match(email) or email.lower() in seen:
            # A MALFORMED ENTRY IS SKIPPED RATHER THAN FATAL: one typo in a list of forty
            # must not stop the other thirty-nine, and the count the card shows is then the
            # count of addresses that will actually be written to - not the file's length.
            continue
        seen.add(email.lower())
        out.append({"email": email, "name": str(row.get("name") or "").strip()[:80],
                    "sha": digest(email)})
    if not out:
        return [], EMPTY_LIST
    return out, ""


def snippets(cited):
    """The fenced code blocks that are REALLY in the cited notes, verbatim, deduplicated.

    THE VERIFICATION IS THE POINT AND IT IS DONE TWICE. A block is taken out of a note's own
    text by FENCE_RE, and then - before it is returned - the extracted body is checked back
    against that same note's text with a plain substring test. The second check looks
    redundant and is not: it is what makes "never invented code the notes do not support" a
    property this function GUARANTEES rather than one its regex happens to have. If the
    extraction and the source ever disagree, nothing ships.

    NO SNIPPET IS SYNTHESISED, REFORMATTED OR REPAIRED. Not indented, not prettified, not
    completed. What the note says is what the subscriber reads, because the moment this
    function edits a line of code it becomes the author of code nobody reviewed.
    """
    out, seen = [], set()
    for hit in cited or []:
        text = str((hit or {}).get("text") or "")
        for lang, body in FENCE_RE.findall(text):
            code = body.rstrip()
            if not code.strip() or len(code) > SNIPPET_MAX:
                continue
            if code not in text:                    # the second check. See the docstring.
                continue
            key = code.strip()
            if key in seen:
                continue
            seen.add(key)
            out.append({"lang": (lang or "").strip().lower(), "code": code,
                        "noteId": str((hit or {}).get("id") or "")})
            if len(out) >= SNIPPETS_MAX:
                return out
    return out


def cited_line(cited):
    """The provenance line: how many of the boss's notes this went out on, and their ids.

    broadcast.cited_line()'s shape and its reasoning, on purpose - a reader who has seen one
    of this house's descriptions should recognise the other. Ids, never filenames.
    """
    n = len(cited or [])
    if not n:
        return ""
    return ("Written from %d note%s of my own research. Source ids: %s."
            % (n, "" if n == 1 else "s",
               ", ".join(str(c.get("id") or "")[:16] for c in (cited or [])[:CITE_MAX])))


def subject_for(topic):
    """A subject line from the topic, inside SUBJECT_MAX and carrying no unmeasured claim.

    NO NUMBER THIS FILE DID NOT COUNT, which is the Broadcaster's title rule: no "in 5
    minutes", no "part 3", nothing a reader can hold the boss to that nothing here measured.
    """
    said = re.sub(r"\s+", " ", str(topic or "")).strip()
    if not said:
        return ""
    # A LEADING CAPITAL, UNLESS THE WORD ALREADY HAS ONE OF ITS OWN. "pricing" should open a
    # subject as "Pricing"; "useEffect" must not become "UseEffect", because the identifier IS
    # the keyword a reader scans for and a mis-cased one reads as a different symbol. Measured
    # on this corpus: the first draft shipped "UseEffect cleanup in React - from my notes".
    first = said.split(" ", 1)[0]
    if first == first.lower():
        said = said[0].upper() + said[1:]
    tail = " - from my notes"
    if len(said) + len(tail) <= SUBJECT_MAX:
        return said + tail
    return said[:SUBJECT_MAX]


def compose(topic, cited=None, recall=None):
    """THE DRAFT: {ok, why, subject, body, snippets, citedIds, subscribers, ...}.

    A PURE FUNCTION OF ITS INPUTS WHEN `cited` IS PASSED, which is what lets publisher_proof
    assert the refusals and the citation discipline as predicates with no store, no Ollama and
    no network. Left to itself it asks ingest.recall() - the same retrieval server.py's chat
    path reaches through semantic_recall() at server.py:5232 - and does not reimplement it.
    """
    out = {"ok": False, "why": "", "topic": str(topic or "").strip(), "subject": "",
           "body": "", "snippets": [], "cited": [], "citedIds": [], "citedLine": "",
           "subscribers": 0, "best3": 0.0}
    if not out["topic"]:
        out["why"] = "no topic was given, so there is nothing to write about"
        return out

    # THE LIST IS CHECKED BEFORE A WORD IS WRITTEN. A draft composed for a list that does not
    # exist is work the boss has to be told was wasted; the refusal is cheaper and clearer.
    rows, why = subscribers()
    if why:
        out["why"] = why
        return out
    out["subscribers"] = len(rows)

    if cited is None:
        try:
            import ingest
            recall = recall if recall is not None else ingest.recall(out["topic"])
        except Exception as exc:                                   # noqa: BLE001
            out["why"] = "the notes could not be searched (%s)" % type(exc).__name__
            return out
        cited = (recall or {}).get("cited") or []
    if recall is not None:
        out["best3"] = float((recall or {}).get("best3") or 0.0)

    if not cited:
        out["why"] = NO_GROUND
        return out

    out["cited"] = [{"id": str(c.get("id") or ""), "score": c.get("score")} for c in cited]
    out["citedIds"] = [c["id"] for c in out["cited"] if c["id"]]
    if not out["citedIds"]:
        # A HIT WITH NO ID IS NOT A CITATION. It would make the provenance line a sentence
        # with nothing behind it, which is the one thing this module refuses hardest.
        out["why"] = NO_GROUND
        return out

    out["subject"] = subject_for(out["topic"])
    out["citedLine"] = cited_line(out["cited"])
    out["snippets"] = snippets(cited)

    # ---- THE BODY, IN FOUR PARTS AND IN THIS ORDER ------------------------------------
    # An opening, the passages' own substance, the code if the notes had any, and the
    # provenance line last. The parts are ASSEMBLED rather than generated: nothing in this
    # function asks a language model for a sentence, so nothing in a newsletter can be a
    # hallucination. What it says is what the notes say, quoted and attributed.
    parts = ["## %s" % out["subject"], "",
             "Notes from my own research on %s." % out["topic"], ""]
    for i, hit in enumerate(cited[:4], start=1):
        text = re.sub(r"```.*?```", "", str(hit.get("text") or ""), flags=re.S)
        text = re.sub(r"\s+", " ", text).strip()
        if not text:
            continue
        parts.append("**%d.** %s" % (i, text[:700]))
        parts.append("")
    if out["snippets"]:
        parts.append("### From the notes, verbatim")
        parts.append("")
        for snip in out["snippets"]:
            parts.append("```%s" % snip["lang"])
            parts.append(snip["code"])
            parts.append("```")
            parts.append("")
    parts.append("---")
    parts.append(out["citedLine"])
    out["body"] = "\n".join(parts)[:BODY_MAX]
    out["ok"] = True
    return out
