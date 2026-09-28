"""census.py - the seventeen questions this house is allowed to ask about its employer.

WHAT IT IS FOR. The galaxy was built out of a corpus that was not his: a dummy cafe, an
invoice importer, a cold brew recipe. PART 8 quarantined that and left a true but very
small collection behind, and the honest way to grow it is to ASK rather than to infer.
So this is a fixed list of questions, in three chapters, and every answer becomes one
note in notes/census/ - written by the save_note hand, behind the same card as everything
else. Nothing here writes a file and nothing here holds an answer in memory.

THE LAW IT SERVES, in the mandate's own words: no personal fact enters any note except
via the Census, the remember hand, or the Scribe's minutes. This is the first of those
three, and it is the only one with a list: the other two are things he says. A question
that is not in the bank below cannot be asked, which is what stops an intake from
drifting into an interrogation.

WHY THE STATE IS READ AND NOT REMEMBERED. "Which questions has he answered?" is answered
by listing notes/census/ and matching filenames against the slug each question's title
slugifies to - so the answer survives a restart, a rebuild, a note deleted by hand, and a
note written by hand. A server that kept a progress counter would be a second model of
the same fact, and the two go out of step the first time he removes a note. The cost of
reading it from the folder is one listdir per ask, which is nothing.

  CHAPTERS                  three, in the order they are asked
  state(notes_root)         every chapter and question with `answered` and `file`
  question(qid)             one question or None
  next_question(root, ch)   the first unanswered one, chapter-first then anywhere
  note_for(qid, answer)     (title, body) for the save_note hand, or (None, reason)

WHAT IT DOES NOT DO: judge an answer. "I would rather not say" is a legitimate answer to
a question about his family and becomes a note saying so, which is a fact about him worth
keeping. The only refusals are an unknown question, an empty answer, and a credential -
and the last of those is secretscan's opinion, taken by the server at the door.
"""
import os

import build

FOLDER = "census"             # inside the notes directory, beside captures/

# -- THE BANK. `id` is the wire name and never changes; `title` is what the note is
# called, and it is what the answered-state is derived from, so changing a title orphans
# the note that answers it - which is why they are plain and durable rather than clever.
# `ask` is read aloud and shown on the board. `hint` is the empty field's own example, and
# it is an EXAMPLE rather than a default: nothing is ever written from it.
CHAPTERS = (
    {
        "id": "life",
        "name": "Life",
        "note": "Where you are, who is around you, and what the days look like.",
        "questions": (
            {"id": "life-name", "title": "My Name",
             "ask": "What is your full name, and what should I call you?",
             "hint": "Adedayo Fullstack - Addi to you"},
            {"id": "life-home", "title": "Where I Live",
             "ask": "Where do you live, and which clock do you keep?",
             "hint": "Lagos - my own clock is the one on the board"},
            {"id": "life-born", "title": "My Birthday And Birthplace",
             "ask": "When is your birthday, and where were you born?",
             "hint": "the month and the town is enough"},
            {"id": "life-household", "title": "My Household",
             "ask": "Who lives with you, and what should I know about them?",
             "hint": "names, and what you would want me to remember"},
            {"id": "life-rhythm", "title": "My Daily Rhythm",
             "ask": "What does an ordinary weekday look like - when do you start, "
                    "and when do you stop?",
             "hint": "at the desk by seven, done by eight"},
            {"id": "life-why", "title": "Why I Am Building You",
             "ask": "Why are you building me, and what should I be for?",
             "hint": "in your own words - this is the note I will be asked about most"},
        ),
    },
    {
        "id": "work",
        "name": "People & Work",
        "note": "What you do, who you do it with, and who it is for.",
        "questions": (
            {"id": "work-role", "title": "My Work And Title",
             "ask": "What do you do, and what is your title?",
             "hint": "what you would say at a table of strangers"},
            {"id": "work-company", "title": "My Company",
             "ask": "What is the company called, and what does it actually do?",
             "hint": "the name, and the one sentence"},
            {"id": "work-people", "title": "The People I Work With",
             "ask": "Who do you work with most closely, and what does each of them do?",
             "hint": "names and roles - I will hear these names again"},
            {"id": "work-clients", "title": "My Clients And Partners",
             "ask": "Which clients or partners matter most at the moment?",
             "hint": "who, and what you owe them"},
            {"id": "work-projects", "title": "What I Am Working On",
             "ask": "What are you working on right now, and what is the deadline on it?",
             "hint": "one or two, not the whole list"},
            {"id": "work-sign", "title": "How I Sign My Mail",
             "ask": "When I write on your behalf, how should the letter be signed?",
             "hint": "the name and the line beneath it"},
        ),
    },
    {
        "id": "study",
        "name": "Education & Study",
        "note": "Where you were taught, and what you are still learning.",
        "questions": (
            {"id": "study-school", "title": "My Schooling",
             "ask": "Where did you go to school?",
             "hint": "the schools, and the years if you like"},
            {"id": "study-degree", "title": "What I Studied",
             "ask": "What did you study after school, and where?",
             "hint": "the subject, the institution"},
            {"id": "study-now", "title": "What I Am Learning Now",
             "ask": "What are you learning at the moment?",
             "hint": "a course, a language, a craft"},
            {"id": "study-langs", "title": "The Languages I Speak",
             "ask": "Which languages do you speak, and how well?",
             "hint": "and which one you would rather be addressed in"},
            {"id": "study-reading", "title": "What I Am Reading",
             "ask": "What are you reading, and what is next after it?",
             "hint": "titles are enough"},
        ),
    },
)

TOTAL = sum(len(c["questions"]) for c in CHAPTERS)
MAX_ANSWER = 2000             # a census answer is a sentence or two, not an essay
BY_ID = {}
for _chapter in CHAPTERS:
    for _q in _chapter["questions"]:
        BY_ID[_q["id"]] = dict(_q, chapter=_chapter["id"],
                               chapterName=_chapter["name"],
                               slug=build.slugify(_q["title"]))


def folder_path(notes_root):
    """notes/census, as an absolute path. Not created here - the hand creates it."""
    return os.path.join(str(notes_root), FOLDER)


def _stems(notes_root):
    """The basenames already in notes/census, lowercased, without .md.

    An unreadable folder is an EMPTY folder as far as this is concerned, and that is the
    safe direction: every question reads as unanswered, so the worst case is being asked
    something twice. The opposite default - treating an unreadable folder as "all done" -
    would silently end the intake.
    """
    try:
        names = os.listdir(folder_path(notes_root))
    except OSError:
        return set()
    out = set()
    for name in names:
        low = str(name).lower()
        if low.endswith(".md"):
            out.add(low[:-3])
    return out


def _answer_files(stems, slug):
    """Every file that answers `slug`, including save_note's -2, -3 step-asides.

    A question answered twice is two notes and both are shown: the second is not a
    correction of the first - see save_note.py's own note on why it steps aside rather
    than refusing - and a board that reported only one of them would be hiding a file
    that is in the galaxy.
    """
    found = []
    for stem in sorted(stems):
        if stem == slug:
            found.append(stem + ".md")
            continue
        if stem.startswith(slug + "-") and stem[len(slug) + 1:].isdigit():
            found.append(stem + ".md")
    return found


def question(qid):
    """One question, with its chapter and slug attached, or None."""
    got = BY_ID.get(str(qid or "").strip().lower())
    return dict(got) if got else None


def state(notes_root):
    """Every chapter and question, with `answered` read off the disk. Never raises."""
    stems = _stems(notes_root)
    chapters, answered = [], 0
    for chapter in CHAPTERS:
        rows, done = [], 0
        for q in chapter["questions"]:
            slug = BY_ID[q["id"]]["slug"]
            files = _answer_files(stems, slug)
            if files:
                done += 1
            rows.append({"id": q["id"], "ask": q["ask"], "title": q["title"],
                         "hint": q["hint"], "slug": slug,
                         "answered": bool(files),
                         "file": ("%s/%s/%s" % (os.path.basename(str(notes_root)),
                                                FOLDER, files[0])) if files else "",
                         "files": len(files)})
        answered += done
        chapters.append({"id": chapter["id"], "name": chapter["name"],
                         "note": chapter["note"], "questions": rows,
                         "answered": done, "total": len(rows)})
    return {"chapters": chapters, "answered": answered, "total": TOTAL,
            "folder": "%s/%s" % (os.path.basename(str(notes_root)), FOLDER)}


def next_question(notes_root, chapter=""):
    """The question to put next: unanswered, in the named chapter if it has one left.

    CHAPTER FIRST AND THEN ANYWHERE, because an intake that stopped at the end of a
    chapter would need him to know he had to press the next one - and the board would
    show a finished chapter with no question on it, which reads as broken rather than
    as done. When everything is answered this returns None and the board says so.
    """
    snap = state(notes_root)
    want = str(chapter or "").strip().lower()
    pools = []
    if want:
        pools.append([c for c in snap["chapters"] if c["id"] == want])
    pools.append(snap["chapters"])
    for pool in pools:
        for chap in pool:
            for row in chap["questions"]:
                if not row["answered"]:
                    out = dict(row)
                    out["chapter"] = chap["id"]
                    out["chapterName"] = chap["name"]
                    return out
    return None


def note_for(qid, answer):
    """(title, body) for the save_note hand, or (None, reason) - the reason is spoken.

    THE QUESTION GOES INTO THE NOTE, and that is not decoration. The note is retrieved by
    the same vector and keyword search as every other note, so "where does he live"
    should find the note whose body contains the words "Where do you live". An answer
    filed on its own - "Lagos." - is a passage nobody's question matches.
    """
    got = question(qid)
    if not got:
        return None, "that is not one of the Census questions"
    said = str(answer or "").strip()
    said = " ".join(said.split())[:MAX_ANSWER]
    if not said:
        return None, "there was no answer to file"
    if said[-1] not in ".!?":
        said += "."
    body = ("%s\n\nAsked in the Census, under %s: \"%s\""
            % (said, got["chapterName"], got["ask"]))
    return got["title"], body
