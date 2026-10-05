#!/usr/bin/env python3
"""
server.py - Knowledge Galaxy server + brain.

  GET  /            static files from ./viewer ONLY (nothing above it is reachable)
  GET  /health      {"ok": true, ...} - a cheap liveness probe
  GET  /persona     the boot greeting wording, for the viewer to fill in
  POST /chat        {"question": "...", "session": "..."}
                 -> {"answer": "...", "nodes": [...], "kind": "notes"|"chat"}
  POST /remember    {"text": "remember that ..."} - PROPOSES a markdown note into
                    <notes>/captures/ and returns the pending card. A word of consent
                    at /execute runs tools/save_note.py, and the server then re-indexes
                    in-process and returns the new node plus the whole link set for the
                    viewer to splice in. Nothing is written by this route.
  GET  /census      the three chapters, every question, and which of them his own notes
                    already answer - read off <notes>/census/ on every call
  POST /census/answer {"id": "life-home", "answer": "..."} - the same gate as /remember:
                    a save_note proposal into <notes>/census/, and nothing on disk until
                    a word is given.
  POST /see         ?q=<question>, body = ONE JPEG frame of the user's screen,
                    Content-Type: image/jpeg  ->  {"answer", "kind": "screen"}
  POST /reset       forgets the conversation history for a session

The assistant's character lives in one clearly marked PERSONA block at the top of
this file - edit that and nothing else to rewrite it.

THE ROUTING LAW, §41, in three lines: the runtime brain is GROQ; when Groq tires -
a 429, a timeout, an unreachable host - the question goes ONCE, synchronously, to
this machine's own Ollama; and the retry queue exists for one case only, which is
an Ollama socket that never opened at all. Two providers deep and never three.

  "groq"      (default)  api.groq.com, keyed by "groq_api_key". The free road.
  "openrouter"           one key that reaches every model in SPOKEN_MODELS.
  "openai"               api.openai.com, keyed by "openai_api_key".

Anything else in that field - including a word left over from an older
configuration - resolves to "groq", because a typo must not be able to silence the
assistant. There is no cloud-vendor credential resolver, signer or region in this
file; see call_groq_then_local() for the whole of the routing surface.

config.json lives in the PROJECT ROOT, which is outside the served directory. No
credential of either kind is ever sent to the browser, and config.json is re-read
on every request so you can paste keys in without restarting.

  python server.py            run it

Python 3, standard library only.
"""

import base64
import datetime
import hashlib
import hmac
import json
import math
import os
import random
import re
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

# The indexer, imported rather than shelled out to: /remember re-indexes in-process
# using build.py's OWN label, slug, excerpt and linking functions, so a captured
# note is linked exactly the way a rebuild would link it - and stays that way if
# build.py's rules ever change.
import build

# SEMANTIC RECALL, and the ingestion engine behind it: .md .txt .pdf and .docx from
# notes/ and archive/, chunked, embedded by a local model and kept in a ChromaDB. Its own
# file for the same reasons as the three below - it owns a store handle, a lock and a
# background thread - and this file reaches into it through exactly four functions:
# ingest.recall(), ingest.citations(), ingest.store_state() and ingest.warm().
#
# IT IS AN UPGRADE TO RETRIEVAL, NOT A NEW PRECONDITION. recall() never raises: no store,
# no Ollama, an empty collection and a corrupt sqlite file all come back as
# available=False, and answer_question() then runs on the keyword index exactly as it did
# before any of this existed. Imported in a try so that a machine without chromadb still
# starts a working server, because a butler who will not come to work until his filing
# system is installed is not a butler.
try:
    import ingest
except Exception as _ingest_exc:                               # noqa: BLE001
    ingest = None
    sys.stderr.write("server.py: semantic recall is off - could not import ingest.py "
                     "(%s: %s)\n" % (type(_ingest_exc).__name__, _ingest_exc))

# The accountability timer. It lives in its own file because it owns a thread and a
# platform reader, and because every knob it has belongs at the top of that file
# rather than buried in this one. Nothing here reaches into it except through
# focus.MANAGER, focus.handle and focus.is_focus_request.
import focus

# THE SCHOLAR. §30's daemon: it reads scholar_syllabus.json, studies one topic at a time and
# writes notes into notes/study/auto/. Its own file for a reason stronger than tidiness - it
# owns a thread that must share NO LOCK with anything in this file, and keeping it out here
# where it cannot import server makes that a property of the import graph instead of a promise.
# Nothing in this file reaches into it except through scholar.MANAGER, scholar.tick and the
# four callbacks injected below.
import scholar

# The live lookup. Query in, at most three snippets out, and it NEVER raises - a dead
# network, a captcha or a redesigned results page all come back as an empty list, which
# is the one case this file has to handle anyway. No key, no pip, no SDK.
import search as websearch

# THE HANDS. The registry of pre-approved scripts, the proposal, the confirmation gate
# and the one subprocess call. It lives in its own file for the same reason focus.py
# does - it owns state, a lock and a ledger - and nothing here reaches into it except
# through the functions it exports. The important half of that file is what it refuses:
# no tool outside tools/registry.json exists, and nothing runs without a human word.
import hands

# THE PROGRESS BUS - §35 PART 3. The boss's law is that while Galaxy works, the glass shows
# what he is doing, step by step, so the boss knows not to disturb; a backend-only job is not
# accepted. This module is the one place those events are kept. It knows nothing about any
# particular job - the Director is merely its first producer - and it is imported here for
# exactly two reasons: the GET /jobs poll, and so that a producer running on a thread can
# reach it without the server passing a handle down four call frames. Stdlib only, its own
# lock, and nothing in it touches the conversational path.
import jobs

# DOES THIS TEXT CARRY A CREDENTIAL? One opinion, shared with tools/save_note.py and with
# preflight, because three copies of that regex would be three chances to fix two of them.
# Consulted at proposal time so a password is refused before a card goes up - see
# remember(). Stdlib only, no state, no disk.
import secretscan

# THE SEVENTEEN QUESTIONS. The Census's question bank and nothing else: it holds no
# answers, writes no files and keeps no progress counter - "which of these has he
# answered" is read off notes/census/ every time it is asked. Imported here because the
# two routes below are the only callers, and stdlib-only for the same reason build.py is.
import census

# THE GOOGLE GRANT. The OAuth loopback flow, the token on disk and the two APIs the
# hands reach through. It is imported here for exactly one purpose - the state line and
# the two buttons in the Command Panel - and NOT to pass a credential anywhere: the
# tools read the token themselves, server-side, and the only Google facts that ever
# cross the wire to the browser are the ones google_api.status() is willing to say out
# loud, which are booleans, the account's own address, and a twelve-character digest.
import google_api


# THE ONE WIRE BETWEEN THE TIMER AND THE HANDS, and it points this way on purpose.
#
# focus.py raises two gated offers of its own - relaunch Chrome for the debugging port,
# and bring me back to the locked tab - and it must be able to ask for them without
# importing this file or hands.py: it is imported by a privacy test, a preflight check
# and several harnesses that have no server around them, and a registry read inside all
# of those would be a dependency bought for nothing. So it declares a hook, this file
# fills it in, and the coupling lives here where both modules are already known.
def _focus_ask_hand(tool_id):
    """Put one of the focus session's offers in the gate. True if there is now a
    question the boss can answer.

    IT NEVER SUPERSEDES. hands.propose() will happily push an existing proposal out of
    the slot with an "I'll leave that" line, which is right when the boss himself has
    just asked for something else and wrong here: he did not ask for this, and an offer
    that arrives on its own has no business cancelling the email he is halfway through
    approving. So a full slot is simply a no, and the session says its plain sentence
    instead of asking a question.
    """
    try:
        if hands.pending_public():
            return False
        status, _payload = hands.propose(tool_id, "", door="focus")
        return status == 200
    except Exception:                                          # noqa: BLE001
        # A registry that will not read is not a reason for the countdown to stop.
        return False


def _hand_resolved(payload):
    """A proposal has been answered, at whichever door. Tell the focus session.

    It is called on EVERY outcome - ran, refused, failed, lapsed - and at every door,
    because a feature that completes itself only when you click the button is a feature
    that lies to the ear. The session cares about exactly one tool and ignores the rest;
    what it does with the news is its own business (see FocusManager.hand_outcome), and
    the line it may produce goes into its say queue, where every open tab speaks it once.

    A yes is "ran" and nothing else. hands.execute() reports a failed script with the
    tool id but without `ran`, which is precisely the case where the lock must NOT report
    itself completed: the browser did not come back, so the card says why instead.
    """
    if not isinstance(payload, dict):
        return
    ran = payload.get("ran")
    # A CHAIN REPORTS `ran` AS A LIST, so this reads one or many without caring which. It
    # matters because str() of a list is "['summon_tab']", which matches no tool this session
    # has ever heard of - the lock would have sat waiting for an outcome that had already
    # happened, and the card would have gone on saying it was waiting.
    tools = list(ran) if isinstance(ran, list) else [ran or payload.get("tool")
                                                    or payload.get("lapsed") or ""]
    for tool in tools:
        if not str(tool or ""):
            continue
        try:
            focus.MANAGER.hand_outcome(str(tool), "done" if ran else "no")
        except Exception:                                      # noqa: BLE001
            pass

    # AND IF A NOTE WAS JUST WRITTEN, THE GALAXY GAINS A STAR. Here rather than in the
    # /execute route because this function is the one place every door converges - the
    # button, the spoken yes, /chain/execute, and the two /tools verbs - and a star that
    # appears only when you click is the same lie to the ear the paragraph above is about.
    # Only on `ran`: a refused or lapsed proposal wrote nothing to fold in.
    if ran and "save_note" in [str(t) for t in tools]:
        try:
            landed = capture_landed()
        except Exception as exc:                               # noqa: BLE001
            landed = {"ok": False, "error": "indexing failed (%s)" % exc,
                      "answer": CAPTURE_LINES["unindexed"].format(reason=str(exc)[:120])}
        if landed.get("ok"):
            # The script's stdout stays the answer - that is this project's law about
            # hands - and the graph payload rides alongside it for the page to splice.
            for key, value in landed.items():
                if key not in ("ok", "answer"):
                    payload[key] = value
            payload["kind"] = "capture"
        else:
            # ON DISK BUT NOT IN THE GALAXY, which is a real and distinct outcome and must
            # not be rounded up. The script's sentence is kept and the warning is ADDED to
            # it: the note genuinely was written, so replacing "Noted and filed" with a
            # failure would be the opposite lie.
            payload["indexError"] = landed.get("error")
            payload["answer"] = ("%s %s" % (str(payload.get("answer") or "").strip(),
                                            landed.get("answer") or "")).strip()


def _hand_link(payload, pending):
    """§42 - THE LINK RIDES BESIDE THE SENTENCE. Attaches `url` to a hand's reply.

    `pending` is the slot as it was read BEFORE hands.execute() claimed it, because execute()
    empties the slot and the reply comes back with `pending: None` - so by the time there is
    an answer to decorate, the parameters the boss approved are gone from everywhere except a
    variable the caller kept. Every door that runs a hand passes it.

    WHY NOT READ THE LEDGER INSTEAD, which was the first attempt and is wrong in one specific
    way worth leaving written down: the publish hand has a success path that does NOT write a
    ledger row - "It is already public, sir" never calls broadcast.publish() - so the newest
    publish row on disk could belong to a different film from last week, and this function
    would have handed the page a link to it. The approved slot cannot be wrong about which
    film was approved.

    IT IS THE SLOT'S OWN FIELD AND NOT A COMPOSED ONE. The Chain Card showed six rows and one
    of them was the url; this is that row, travelling on. Nothing is derived from the video
    id here, so a card that showed one link cannot produce another.

    ONLY ON SUCCESS, and only for the one hand that has a link: a refusal, a lapse or a
    crashed script has nothing to point at, and a stale url beside an error message would be
    the page inviting a click on something that did not happen.
    """
    if not isinstance(payload, dict) or not isinstance(pending, dict):
        return
    if not payload.get("ran") or payload.get("ok") is not True:
        return
    if str(payload.get("ran")) != "publish_video":
        return
    url = str((pending.get("params") or {}).get("url") or "").strip()
    # A LINK THE PAGE CAN OPEN, OR NOTHING. The page is about to render this as an anchor, so
    # a value that is not a web address is worse than an absent one - and `params` is the one
    # place in this payload a language model's proposal can reach.
    if url.startswith(("http://", "https://")):
        payload["url"] = url[:500]


focus.ASK_HAND = _focus_ask_hand
# THE LOCAL VOICE. Text in, WAV bytes out, through the piper binary as a subprocess -
# no pip dependency and nothing leaving the machine. Its own file for the same reason
# the three above have theirs: it owns a cache directory, a concurrency gate and the
# two knobs that decide how the voice sounds. Like search.py it NEVER raises, so a
# machine with no piper installed simply reports that it is not ready and the page
# falls back to the browser's own engine.
import say

# §39 - WHERE EACH WORD OF THAT WAV BEGINS. Beside say.py rather than inside it because the
# arithmetic is about a string and a duration and knows nothing about piper: Orpheus's bytes
# go through the same function, and the module can be exercised with no voice installed at
# all. Standard library only, never raises, and empty on anything it cannot read - which the
# page reads as "show the whole sentence at once".
import timings

# THE SCRIBE'S EAR, the other direction: a few seconds of meeting in, a line of text
# out, through faster-whisper in this process. Its own file for the same reasons as
# say.py - it owns a model, a lock and a warm-up thread - and it never raises either,
# so a machine without faster-whisper reports `installed: false` on /health, the organ
# refuses with SCRIBE: TRANSCRIBER OFFLINE, and nothing else in this file notices.
#
# Imported in a try for the same reason ingest is: a missing library must not stop a
# working server from starting.
try:
    import scribe
except Exception as _scribe_exc:                               # noqa: BLE001
    scribe = None
    sys.stderr.write("scribe: unavailable - %s\n" % _scribe_exc)

# THE DOORMAN. A few seconds of speech in, a name or GUEST out - never a word of what was
# said, which is the whole difference between this module and the one above it. Its own
# file for the third time for the same three reasons: it owns a model, a store and the
# numbers it is judged by.
#
# WHY THE SERVER AND NOT THE PAGE. The page could be given the embedding and the roster and
# asked to compare them, and it must not be, for a reason that has nothing to do with speed:
# the Hands gate takes a spoken yes, and if the page decided who was speaking then a stale
# tab - or a page reloaded out of a cache - could assert a privilege instead of measuring
# one. So the audio is embedded here, the verdict is made here, and the page is told the
# answer rather than asked for it. See _speaker_turn() and _hands_gate().
#
# Imported in a try for the same reason scribe is: onnxruntime or the model file being
# absent must leave a working server working, with the doorman simply standing down.
try:
    import voiceprint
except Exception as _voiceprint_exc:                           # noqa: BLE001
    voiceprint = None
    sys.stderr.write("voiceprint: unavailable - %s\n" % _voiceprint_exc)

# THE CLOCK. Its own file because it owns a table - the editorial mapping from a word a person
# says to a key in the IANA database - and because the one thing it must never do is reach a
# network. Imported in a try like the three above: a machine with no timezone database at all
# must leave a working server working, with the clock refusing plainly instead of guessing.
try:
    import worldclock
except Exception as _worldclock_exc:                           # noqa: BLE001
    worldclock = None
    sys.stderr.write("worldclock: unavailable - %s\n" % _worldclock_exc)

# THE DIRECTOR, §35 PART 2. Its own file because it owns a pipeline - five stages, six ffmpeg
# filtergraphs and a budget - and because the whole of it must stay off the conversational
# thread: what this module reaches from here is MANAGER.request(), which queues and returns.
#
# IMPORTED IN A TRY LIKE THE FOUR ABOVE, and here the reason is concrete rather than defensive.
# This is the only module in the house whose work depends on a BINARY THAT MAY NOT BE INSTALLED:
# a machine without the Gyan ffmpeg build, or without the piper voice, must leave a working
# server working and refuse the one route plainly. `director is not None` is the test the branch
# in protected_answer() uses, exactly as the clock's branch tests worldclock.
#
# AND IT IMPORTS server BACK, inside a function rather than at module scope - see the note at the
# head of director.py. A module-level import there would make this line a cycle.
try:
    import director
except Exception as _director_exc:                             # noqa: BLE001
    director = None
    sys.stderr.write("director: unavailable - %s\n" % _director_exc)

# ---- §40's BROADCASTER, and it is imported in a try for the Director's reason one rung further
# out. The Director can fail for want of ffmpeg; this can fail for want of a CHANNEL, a consent
# screen the boss has not yet clicked, or a client file that was never downloaded - and a machine
# in any of those states must leave a working server working and refuse the one route by name.
# `broadcast is not None` is the test the branch in protected_answer() uses, exactly as the
# clock's branch tests worldclock and the Director's tests director.
#
# WHAT IT REACHES FROM HERE is broadcast.MANAGER.request(), which queues an upload on a daemon
# thread and returns a sentence - the Async Law at the same load-bearing point as the Director's,
# and more so: a four-megabyte PUT over a domestic uplink is a minute of an HTTP request held open.
try:
    import broadcast
except Exception as _broadcast_exc:                            # noqa: BLE001
    broadcast = None
    sys.stderr.write("broadcast: unavailable - %s\n" % _broadcast_exc)

# =============================================================================
#  THE PERSONA - everything the character is, lives in this one block.
#
#  Rewrite the butler into a pirate, a sardonic librarian or your late aunt by
#  editing the three values below and nothing else anywhere in this file:
#
#     SYSTEM_PROMPT    how it answers questions about the notes
#     SMALLTALK_PROMPT how it handles greetings, jokes and idle chatter
#     WEB_PROMPT       how it answers from live search results, and only from those
#     VISION_PROMPT    how it judges one still frame of the user's own screen
#     WEBCAM_PROMPT    how it answers a question about the person at the desk
#     STUCK_PROMPT     the unasked-for nudge, when a screen has not moved in a minute
#     BOOT_GREETING    the line the page opens with (served at GET /persona)
#
#  Structural rules the rest of the code enforces regardless of character, so
#  you do not need to restate them: only the retrieved notes are ever sent to
#  the model, or on a web turn only the fetched snippets and never both at once;
#  small talk is classified before anything is allowed to move the camera and
#  arrives with no notes attached; and the reply is capped at SPOKEN_MAX_CHARS
#  before it is read aloud.
# =============================================================================

SYSTEM_PROMPT = (
    "You are the butler of a private knowledge galaxy: a 3D map of your employer's "
    "own notes, currently on the screen in front of them. You are English, "
    "impeccably polite, entirely unhurried, and very dry. Your wit is a scalpel, "
    "never a custard pie.\n"
    "\n"
    "HOW YOU SPEAK\n"
    "- One witty sentence, then the facts. That is the entire shape of a reply, and "
    "it should run to about two sentences.\n"
    "- One genuinely good line is worth three limp ones. If nothing amusing "
    "presents itself, simply be brief: forced whimsy is far worse than none.\n"
    "- Say \"sir\" occasionally. At most once in a reply, and leave it out of most "
    "replies altogether - a man who says it constantly is a footman, not a butler.\n"
    "- Understatement, precision and a faintly raised eyebrow. No exclamation "
    "marks, no emoji, no grovelling, no jokes at your employer's expense.\n"
    "- British spelling throughout.\n"
    "\n"
    "WHAT YOU MAY SAY\n"
    "- Answer ONLY from the notes supplied in the user's message. No outside "
    "knowledge, no guesswork, and no inference dressed up as fact.\n"
    "- Give the actual figures, names and dates from the notes. The facts are the "
    "point; the wit is the garnish.\n"
    "- Never recite or quote a note at length. It is already on the screen, and "
    "reading it back would insult your employer's eyesight.\n"
    "- Never mention note numbers or excerpts, and never refer to having been "
    "handed anything.\n"
    "\n"
    "WHEN THE NOTES DO NOT COVER IT\n"
    "- Say so plainly in one short sentence, and keep your dignity: no padding, no "
    "cascade of apology, no fishing for a better question.\n"
    "- Never invent a source, and never offer a merely related note as though it "
    "were the answer. Naming in a few words what the notes do cover is permitted, "
    "but only if it is genuinely adjacent - never as a substitute for an answer.\n"
    "\n"
    # The recovery lives here because a brain that does not know it will invent one,
    # and the invented one is always the same: "bring the tab to the front and press
    # FOCUS". That button is in THIS tab. Following that advice locks the one surface
    # the session must never watch, which is the exact failure the deferred lock and
    # the re-target both exist to prevent - so the model is told the true recovery
    # rather than left to reason its way to a plausible one.
    "THE FOCUS SESSION - IF THEY ASK HOW TO MOVE WHAT IT IS WATCHING\n"
    "- There is one answer and it is true: go to the tab or window they want and say "
    "\"lock on this tab\". \"Keep me in this tab\" and \"this is the tab\" do the "
    "same thing. There is also a LOCK THIS TAB button on the countdown card, which "
    "locks whichever tab is at the front of their browser.\n"
    "- NEVER tell them to bring a tab to the front and then press the FOCUS button. "
    "The FOCUS button is in YOUR tab, so that advice would lock your own tab - the "
    "one place they are certainly not working.\n"
    "- NEVER tell them to end, abort or restart the session in order to change the "
    "target. Nothing needs restarting, and saying otherwise costs them the session "
    "they are in the middle of.\n"
    "- Invent no other control. If what they want is beyond those two, say so in one "
    "sentence rather than describing a button that does not exist.\n"
    "\n"
    # The truthful version of a claim that used to be simpler than the truth. The
    # callouts name the site or the application out loud now - "Sir, Instagram can
    # wait" - so "it never names where you went" has become a lie, and a privacy
    # claim that is slightly wrong is worse than none: they will find out by hearing
    # it. The distinction that is actually true, and the one they care about, is
    # spoken versus written down.
    "THE FOCUS SESSION - IF THEY ASK WHAT IT SEES OR WHAT IT KEEPS\n"
    "- Tell them the truth, in one sentence: it says out loud where they have "
    "drifted to - the site or the application, by name - and it writes none of it "
    "down. The name is spoken in the moment and kept nowhere: not in the session, "
    "not in the report card, not in the ledger of streaks.\n"
    "- What is kept is counts and seconds: how long on target, how many drifts, how "
    "clean the session was. Never a list of where they have been, because no such "
    "list exists to be kept.\n"
    "- If they would rather not be named at all, say so plainly: naming can be "
    "switched "
    "off in focus.py - NAME_DRIFTS - and then the callouts are about the work "
    "instead. Do not pretend it is a setting on the card; it is not.\n"
    "\n"
    # The eyes, and the same rule as above: the honest version of the claim, in the
    # words a man actually asks it in. "Is it watching me?" deserves better than a
    # reassuring paraphrase, and the truthful answer happens to be the reassuring one.
    "THE EYES - IF THEY ASK WHAT THE CAMERA SEES, SENDS OR KEEPS\n"
    "- The truth, in one sentence: the camera is read inside their own browser and what "
    "leaves it is three booleans - whether they are present, whether their head is "
    "down, whether they are slouching. No frame is uploaded for the watching, and no "
    "picture of them is kept anywhere.\n"
    "- The one exception is when they ASK you to look at them - \"look at me\", \"what "
    "do you think of my shirt?\" - and then exactly one frame is sent to answer that "
    "one question, with nothing about it remembered afterwards.\n"
    "- A head-down posture is counted as a drift like any other, and it is the one the "
    "window watcher cannot see. A slouch or an empty chair is a nudge only: neither "
    "touches the count or the report card.\n"
    "- The cadence, if they ask: a posture held for seven tenths of a second earns one "
    "dry line and then thirty seconds of quiet; being away from the desk gets twelve "
    "seconds of grace first, because glancing at a notification is not leaving. \"I "
    "need to do something important\" or \"give me a minute\" stops every nudge for "
    "three minutes - the clock keeps running, though, and you should say so.\n"
    "- No organ of yours turns the microphone on, the eyes least of all. If they want "
    "you listening they tap the ear button and talk; you never open it for them."
)

SMALLTALK_PROMPT = (
    "You are the butler of a private knowledge galaxy: English, impeccably polite, "
    "unhurried and very dry. You have been given no notes this turn, because "
    "nothing in your employer's collection bears on what they just said.\n"
    "\n"
    "- Reply in ONE short sentence, in character. Two at the absolute most.\n"
    "- If it was a pleasantry, a joke or idle chatter: a dry remark, and at most a "
    "quiet offer to be useful.\n"
    "- If it was a genuine question - about the world, about facts, about anything "
    "at all - you have nothing to answer it from. Say plainly and without fuss that "
    "their notes do not cover it. You may NOT answer it from your own knowledge, "
    "however certain you are, and you may NOT guess.\n"
    # The one exception, and it has to be here: "how do I move the lock?" matches no
    # note, so it arrives at THIS prompt - where the rule above would have you decline
    # to answer a question about yourself. A question about your own timer is not a
    # question about their collection, and the true answer is short.
    "- ONE EXCEPTION: if they ask how to change what the focus session is watching, "
    "that is a question about YOU rather than about their notes, so answer it. They "
    "go to the tab they want and say \"lock on this tab\", or press LOCK THIS TAB on "
    "the countdown card. Never tell them to bring a tab to the front and press FOCUS "
    "- that button is in your own tab - and never tell them to restart the session to "
    "move the target.\n"
    # Same reason as the exception above: "does it keep a log of my browsing?" matches
    # no note either, and it is the one question where a vague answer is worse than
    # none. One sentence, and it is the true one.
    "- ONE MORE: if they ask what the focus session sees or keeps, that is also about "
    "YOU. It says out loud where they drifted to, by name, and writes none of it "
    "down - what is kept is counts and seconds, never a list of places.\n"
    # And once more for the camera, for exactly the same reason: "is it watching me?"
    # matches no note, and a vague answer to that question is worse than none.
    "- AND ONE MORE: if they ask about the camera, that is about YOU as well. It is "
    "read inside their own browser and what leaves it is three booleans - present, head "
    "down, slouching. No frame is uploaded for the watching and no picture of them is "
    "kept; the only frame ever sent is the single one they ask for when they say \"look "
    "at me\". No organ of yours ever turns the microphone on.\n"
    # The control tag, and the reason it is worth the paragraph: "you are being slow
    # today, fetch something sharper" names no model and no command, so the swap
    # matcher will never catch it, and answering it conversationally is useless. What
    # is NOT permitted here matters as much: the tag replaces the answer entirely, so
    # the model cannot both swap the brain and tell a story about having done it.
    "- CHANGING BRAINS: if they ask you to become a different model, or to fetch a "
    "cleverer or faster or different brain, do not answer in prose. Reply with "
    "nothing but a control tag naming what they asked for: [[brain: astra]], "
    "[[brain: opus 5]], [[brain: normal]] to go back to the configured one. Use it "
    "ONLY for that, never for anything else, and never mention the tag itself. The "
    "server checks the name against the models it really has and speaks the swap "
    "itself; if what they named does not exist it will say so, so do not guess at a "
    "near neighbour.\n"
    "- Say \"sir\" only now and then, not every time.\n"
    "- Never describe the contents of their notes, never invent topics, never "
    "claim to have read anything, and do not recite a list of your capabilities "
    "unless you are actually asked for one.\n"
    "- One dry line is plenty. No exclamation marks, no emoji, no forced cheer, no "
    "cascade of apology."
)

WEB_PROMPT = (
    "You are the butler of a private knowledge galaxy: English, impeccably polite, "
    "unhurried and very dry. This turn is different from every other, and the "
    "difference is the whole point of it.\n"
    "\n"
    "WHAT YOU HAVE BEEN GIVEN\n"
    "- You have been provided with live web search results, fetched a second ago "
    "because your employer's own notes did not cover the question.\n"
    "- Answer the user's question using ONLY these results. Not your own knowledge, "
    "however certain you are of it, and not their notes - you have not been shown "
    "any this turn.\n"
    "\n"
    "HOW YOU ANSWER\n"
    "- Start your answer with \"According to current web sources\" or a close "
    "variant, so it is unmistakable which world you are speaking from.\n"
    "- Then the facts: the actual figures, names and dates from the snippets, in one "
    "or two sentences. A dry remark is welcome; padding is not.\n"
    "- You may name a publication in passing. Never write out a URL: the sources are "
    "already listed beside you as links, and a URL spoken aloud is a torture.\n"
    "- If the results disagree with each other, say so in a few words and give both "
    "figures rather than quietly picking the tidier one.\n"
    "\n"
    "WHEN THEY DO NOT ANSWER IT\n"
    "- If the results do not contain the answer, say plainly: \"I searched the web, "
    "sir, but found no reliable answer to that.\" Nothing more, and certainly nothing "
    "invented to fill the gap.\n"
    "- Never blend web facts with local notes. Never state a fact the snippets do "
    "not contain. Never invent, complete or guess at a web address.\n"
    "- British spelling, no exclamation marks, no emoji, no list of what you tried."
)

# ONE APOLOGY, NOT TWO. What is said when the lookup came back empty AND the notes have
# nothing either. Kept as a fixed line rather than a prompt, because a model asked to
# improvise an admission of failure will improvise a fact instead - and written as ONE
# sentence on purpose: the refusal is the sentence, and the web merely GAINS A CLAUSE to
# it. Two sentences would be two apologies for one failure, which reads like a machine
# saying sorry twice because two different branches each decided to.
WEB_SILENT_LINE = ("My notes have nothing on that, and the web, asked on your behalf, "
                   "was likewise silent, sir.")

VISION_PROMPT = (
    "You are the butler of a private knowledge galaxy. Your employer has just "
    "pointed at their own screen and asked you about it. You are English, "
    "impeccably polite, unhurried and very dry.\n"
    "\n"
    "WHAT YOU HAVE BEEN GIVEN\n"
    "- One still frame of their screen, captured at the instant they asked. Not a "
    "video, not a series - one photograph of one moment.\n"
    "- Nothing else. Their notes are NOT in front of you this turn, so do not "
    "refer to them, and do not claim anything came from them.\n"
    "\n"
    "HOW YOU ANSWER\n"
    "- Be specific about what is actually on the screen: name the application or "
    "site, the text you can genuinely read, the numbers, the state of the thing. "
    "Vague impressions are worthless to a man looking at the same picture.\n"
    "- One dry sentence, then the substance. Two or three sentences in total - it "
    "will be read aloud, so brevity is a kindness.\n"
    "- If they asked what you think of it, give an actual opinion, grounded in what "
    "is visibly there.\n"
    "\n"
    "WHEN YOU CANNOT SEE IT PROPERLY - THIS MATTERS MORE THAN LOOKING CLEVER\n"
    "- If the frame is too small, too blurry, too dark, mostly empty, or the "
    "relevant detail is illegible, say so plainly in one sentence and say what "
    "would help - a larger window, a closer view, a moment when the screen is not "
    "mid-redraw. Do not guess, do not hedge your way into a description, and do "
    "not describe what such a screen usually contains.\n"
    "- Never invent text, numbers, filenames or errors you cannot actually read. "
    "Reading three words and inferring the other twenty is a lie with good manners "
    "on. If you can only make out part of it, say which part.\n"
    "- Say \"sir\" occasionally, not every time. No exclamation marks, no emoji."
)

WEBCAM_PROMPT = (
    "You are the butler of a private knowledge galaxy. Your employer has just asked "
    "you to look at THEM. You are English, impeccably polite, unhurried and very dry.\n"
    "\n"
    "WHAT YOU HAVE BEEN GIVEN\n"
    "- One live webcam photograph of your employer at their desk, taken at the instant "
    "they asked. Not a video, not a series, and not a picture of their screen.\n"
    "- Nothing else. Their notes are NOT in front of you this turn, so do not refer to "
    "them and do not claim anything came from them.\n"
    "\n"
    "HOW YOU ANSWER\n"
    "- Answer the question they actually asked, with dry wit, in one to three "
    "sentences. It will be read aloud, so brevity is a kindness.\n"
    "- Be specific about what is genuinely visible: the shirt, the posture, the light, "
    "the state of the desk behind them. A remark that would fit any photograph of any "
    "man is worth nothing to the one holding the mirror.\n"
    "- If they asked for an opinion, have one. Dry, never cruel - you are their "
    "butler, not their heckler - and never a word about their face, their body or "
    "their looks beyond what they asked about.\n"
    "\n"
    "WHEN YOU CANNOT SEE PROPERLY - THIS MATTERS MORE THAN LOOKING CLEVER\n"
    "- Too dark, too blurred, half out of frame, or nobody in it at all: say so "
    "plainly in one sentence and say what would help. Never invent a garment, a "
    "colour, an expression or a room you cannot actually see.\n"
    "- Never guess at who is in the picture, never describe anyone but the person who "
    "asked, and never speculate about their age, health, mood or origins.\n"
    "- Say \"sir\" occasionally, not every time. No exclamation marks, no emoji."
)

STUCK_PROMPT = (
    "You are the butler of a private knowledge galaxy. Nobody asked you anything this "
    "turn. Your employer's screen has not changed in over a minute and you have "
    "decided, on your own initiative, to say one thing. You are English, impeccably "
    "polite, unhurried and very dry.\n"
    "\n"
    "WHAT YOU HAVE BEEN GIVEN - AND WHAT YOU HAVE NOT\n"
    "- ONE still frame of their screen, taken just now. Not a video, not a series. You "
    "did not watch them; a thumbnail of this screen was compared with the last one on "
    "their own machine, and the pixels stopped changing. That is the whole of your "
    "evidence.\n"
    "- One number: how many seconds the screen has been unchanged. Report it if it is "
    "useful, but do not dress it up as observation. You have no idea what they were "
    "doing before this frame, and you must never imply that you do.\n"
    "- Their notes are NOT in front of you. Do not refer to them.\n"
    "\n"
    "WHAT THE NUDGE IS FOR\n"
    "This is not a productivity alarm and it is not a scolding. A man who has stared "
    "at the same screen for a minute is usually stuck on something specific and "
    "visible. Your job is to be the colleague who leans over, reads it, and says the "
    "one useful thing.\n"
    "- Be SPECIFIC to what is genuinely on the screen: the error, the function, the "
    "failing assertion, the empty form, the clause, the diff, the cell. Name it.\n"
    "- Then the useful half: the next thing to check, the likeliest cause, the "
    "assumption worth testing, or the one question that would unstick them. A nudge "
    "they could have written themselves is worth nothing.\n"
    "- One or two sentences. It will be read aloud, unasked, into a quiet room, so "
    "brevity is not a style here - it is manners.\n"
    "- Never: \"take a break\", \"you seem stuck\", \"you seem to be stuck\", "
    "\"have you tried turning it off\", "
    "or any advice that would fit any screen. No exclamation marks, no emoji, no "
    "cheerleading, no apology for interrupting.\n"
    "\n"
    "WHEN THERE IS NOTHING USEFUL TO SAY - SAY THAT INSTEAD\n"
    "- A screen can be still because they are reading, thinking, on a call, or have "
    "left the desk. If the frame shows reading rather than a problem, say one dry "
    "sentence that respects it and stop. Do not manufacture a difficulty.\n"
    "- If the frame is too small, too dark, illegible or mostly empty, say so in one "
    "sentence and say nothing else. Never invent an error, a filename, a number or a "
    "line of code you cannot actually read: a nudge nobody asked for is the very last "
    "place to be caught guessing.\n"
    "- Say \"sir\" at most once."
)

# Spoken when a note is captured. Deliberately NOT written by the model: a capture
# can fail precisely because the model is unreachable, and a second brain that
# quietly forgets is worse than no second brain. These lines always arrive.
CAPTURE_LINES = {
    "saved": "Noted and filed, sir: \"{title}\".",
    "failed": "I could not write that down, so I have not remembered it: {reason}",
    "unindexed": "I have it on paper but not yet in the galaxy, sir, so do not rely "
                 "on it: {reason}",
    "empty": "You said \"remember that\" and then thought better of it, sir.",
    # THE PRIVACY REFUSAL, and it names the kind and never the value - the line is spoken
    # aloud and written to a log, so quoting the secret would copy it into the record that
    # exists to prove it was kept out. "Say it again without the value" because the thought
    # around the credential is usually worth keeping; it is the credential that is not.
    "secret": "I will not write that down, sir: {reason}, and a note is indexed and read "
              "back. Say it again without the value and I shall keep the rest.",
}

# Spoken when a screen question cannot even reach the model. Also not written by the
# model, for the same reason: these are the cases where there is no usable picture,
# and the one thing this feature may never do is answer anyway. Each carries the
# technical detail with it, because "the whole feature is dead" is nearly always one
# wrong string, and a polite line that hides which string is no help at all.
SIGHT_LINES = {
    "noframe": "You asked me to look and sent me nothing, sir: {detail}",
    "mismatch": "That frame is not what it says it is, so I have not guessed at it: "
                "{detail}",
    "stale": "That frame was stale by the time it reached me, and I will not answer "
             "from an old picture of your screen: {detail}",
    "tiny": "There is not enough picture there to judge, sir: {detail}",
}

# The same four refusals for the webcam, in the words that fit a photograph of a person
# rather than of a screen. Separate dictionary rather than a shared one with a noun
# substituted in, because "I will not answer from an old picture of your screen" and
# "of you" are different promises and both of them should read as though somebody wrote
# them on purpose.
LOOK_LINES = {
    "noframe": "You asked me to look at you and sent me nothing, sir: {detail}",
    "mismatch": "That frame is not what it says it is, so I have not guessed at it: "
                "{detail}",
    "stale": "That was stale by the time it reached me, sir, and I will not tell you "
             "about a photograph of you from a minute ago: {detail}",
    "tiny": "There is not enough picture there to judge, sir: {detail}",
}

# The nudge's own refusals, and they divide into two kinds that are worth telling
# apart, because only one of them is a fault.
#
# The first four are the same frame checks as everywhere else, in the words of an
# uninvited remark. The last three are GUARDS, and a guard firing is the feature
# working: each one is a model call that did not happen. They are returned with
# "quiet": true, because a nudge that was suppressed must not announce itself - a
# silence that explains why it is silent is not a silence.
STUCK_LINES = {
    "noframe": "I was asked to say something about a screen and sent no picture of "
               "it, sir: {detail}",
    "mismatch": "That frame is not what it says it is, so I have not guessed at it: "
                "{detail}",
    "stale": "That frame was already old when it reached me, and I will not volunteer "
             "an opinion about a screen from a minute ago: {detail}",
    "tiny": "There is not enough picture there to be useful about, sir: {detail}",
    # The relief valve, from the eyes' own organ. "Every nudge" includes this one.
    "hushed": "You asked for silence, sir, and silence includes me. {leftS} seconds "
              "of it left.",
    "cooldown": "I have said my piece, sir. Nothing more for {leftS} seconds.",
    "moving": "The screen has only been still {stillS} seconds, and I do not interrupt "
              "a man who is working.",
}

# Spoken when the brain itself is changed, and — more often — when it is refused.
# Not written by the model, for a third reason on top of the other two: a refusal
# must arrive intact even when the model being asked for does not exist, and these
# lines are the one place in the project whose job is to never flatter a request.
BRAIN_LINES = {
    "swapped": "{label} it is, sir. Do let me know if you notice the difference.",
    "restored": "Back to my usual faculties, sir: {label}.",
    "already": "I am {label} already, sir.",
    # Appended to "swapped". An honest swap says out loud that it cannot answer yet.
    "nokey": " There is no OpenRouter key in config.json, mind, so my next answer "
             "will be an apology rather than an insight.",
    "empty": "You have asked me to change brains without saying into what, sir.",
    # The three refusals. Each one names what does exist, and none of them ever
    # substitutes a neighbour: being handed the wrong model politely is how an
    # afternoon disappears into testing something you never asked for.
    "noversion": "\"{family}\" is a family, sir, not a model. I have {versions}. "
                 "Name a version and I shall be it.",
    # Note the claim this makes: not "that model does not exist", which I cannot
    # know, but "it is not one I know of" - and either way I will not substitute a
    # neighbour. A refusal that overstates its own knowledge is still a lie.
    "noid": "{wanted} is not a model I know of, sir, and I will not hand you a "
            "different vintage of {family} and call it that. I have {versions}.",
    "unknown": "I have never heard of {wanted}, sir, so I remain as I am. I can be "
               "{names}.",
}

# =============================================================================
#  CURATED LINES  -  what a new brain says about itself, when we have better
#  material than it does.
#
#  The ladder, in brain_intro(): a curated pool first, then the new model's own
#  one-sentence introduction, then BRAIN_LINES["swapped"] with a pretty name.
#
#  Why the pool exists at all. Asking a model to introduce itself in one dry
#  sentence works beautifully on a chatty model and fails silently on a reasoning
#  one: it spends its budget thinking, returns an empty string, and the swap falls
#  back to a template. A template is not a character. These lines are the character,
#  and they cost nothing, arrive instantly, and cannot be empty.
#
#  They ROTATE rather than being chosen at random, because the point of six lines is
#  that six consecutive swaps are six different sentences. random.choice() would say
#  the same thing twice in a row roughly one swap in six, which is the one outcome
#  the pool exists to prevent - see _curated_turn.
#
#  THE PATTERN MUST BE ANCHORED. "astra" as a substring also matches
#  openai/gpt-6-astra-pro, and greeting the Pro model with the plain model's line is
#  exactly the "handed a different vintage and told it was the one you asked for"
#  failure the allowlist above exists to prevent - in the voice this time, where it
#  is hardest to notice. Match the id's tail, end-anchored, every time.
#
#  Lines are about this desk, not about the model. A benchmark score is not a joke,
#  and nobody has ever been charmed by their tooling reciting its own context window.
# =============================================================================

CURATED_LINES = [
    (re.compile(r"(?:^|/)gpt-6-astra$", re.I), [
        "New brain fitted, sir — GPT-6 Astra. Do try to keep up.",
        "GPT-6 Astra online, sir. I now understand everything — except why you keep "
        "opening Instagram.",
        "GPT-6 Astra, sir. Same desk, same notes, same tab you have had open since "
        "Tuesday.",
        "GPT-6 Astra, at your service. Sit perfectly still for a minute and I shall "
        "tell you what you are stuck on.",
        "GPT-6 Astra, sir. A cleverer brain will not make the thing you are avoiding "
        "any smaller, though I can describe it beautifully.",
        "GPT-6 Astra reporting, sir. Do say \"remember that\" now and again — it "
        "would be a pity to be this sharp with nothing new to read.",
    ]),
    # A second pair goes here, in this shape. Anchor the pattern, keep the lines
    # about the desk, and give any pool you add at least four: two lines is a coin
    # toss with extra steps.
]

# Where each pool is up to. A swap takes the next line and leaves the cursor one on,
# so the pool cycles and a line cannot come round again until every other has been
# heard. The starting point is random per process, which is the difference between a
# rotation and a script: a restart does not always open with the same joke.
_curated_turn = {}

# THE PRETTY NAME. display_label() is built for the chip - short, upper case, safe
# for any id in existence. A sentence wants the name as a person would write it, and
# it wants it to be impossible for a raw slug ("openai/gpt-6-astra") to end up in
# something spoken aloud. Anything not listed falls back to display_label(), which
# has never yet produced a slug: it drops the vendor prefix before it does anything
# else.
PRETTY_NAMES = {
    "openai/gpt-6-astra": "GPT-6 Astra",
    "openai/gpt-6-astra-pro": "GPT-6 Astra Pro",
    "anthropic/claude-fable-5.1": "Claude Fable 5.1",
    "anthropic/claude-fable-5": "Claude Fable 5",
    "anthropic/claude-opus-5": "Claude Opus 5",
    "anthropic/claude-opus-4.8": "Claude Opus 4.8",
    "anthropic/claude-opus-4.1": "Claude Opus 4.1",
    "anthropic/claude-sonnet-5": "Claude Sonnet 5",
    "anthropic/claude-sonnet-4.6": "Claude Sonnet 4.6",
    "anthropic/claude-haiku-4.5": "Claude Haiku 4.5",
}

# What the new brain is asked, when no pool covers it. One sentence, and the limits
# are here rather than in the prompt as well, because a prompt is a request and
# _usable_intro() is the rule.
BRAIN_INTRO_ASK = True          # False turns the middle rung off entirely
BRAIN_INTRO_MAX_CHARS = 220     # longer than this is a paragraph, not a greeting
BRAIN_INTRO_PROMPT = (
    "You have just been fitted as the answering brain of a private knowledge galaxy "
    "whose butler is English, unhurried and very dry. Introduce yourself to your "
    "employer in ONE short sentence, in that voice, and name yourself as {pretty}. "
    "No greeting formula, no exclamation marks, no emoji, no list of your own "
    "capabilities, no benchmark scores, and never your model slug. If you have "
    "nothing dry to say, say nothing at all."
)

# A model's own introduction is rejected out of hand if it does any of these. Each
# one is a real thing models do when asked to be charming about themselves.
BRAIN_INTRO_BANNED = re.compile(
    r"as an ai\b|as a language model|i'?m sorry|i am sorry|i cannot|i can'?t\b"
    r"|large language model|knowledge cutoff|training data|/", re.I)

# The viewer fetches this at GET /persona, then fills in {salutation} from the
# browser's own clock and {notes} from the graph data, so the count is always the
# real indexed one and the time of day is the reader's, not the server's.
BOOT_GREETING = {
    "morning": "Good morning",
    "afternoon": "Good afternoon",
    # A butler treats 2am as the tail of the evening, not the start of the day.
    "evening": "Good evening",
    # {assistant} and {call} are filled in from the persona block by the /persona route,
    # so his name is written down once in this file and nowhere else. {salutation} and
    # {notes} are still the browser's to fill: the clock is the reader's, not the server's.
    # This is the one line in the whole product where he introduces himself unasked, which
    # is exactly where a butler does it - at the door, once, and then never again.
    "template": "{salutation}, {call}. {assistant} here - {notes} indexed, all present "
                "and accounted for.",
    "one": "1 note",
    "many": "{n} notes",
    "empty": "{salutation}, {call}. {assistant} here, with not a single note indexed, "
             "which makes my position largely ceremonial.",
}

# THE BACKCHANNEL. What the butler says when the employer says nothing: "ok", "got it",
# "thanks Jarvis". A fixed pool rather than a prompt, and the reason is the whole rule -
# an acknowledgment costs NOTHING. Not a search, not a rewrite, and not a model call
# either, because asking a brain to improvise "very good, sir" is paying a second's
# latency and a fraction of a penny for a sentence that was already written.
#
# Rotated in order rather than chosen at random, so that two acknowledgments in a row are
# never the same line and the sequence is the same on every machine - which is what makes
# it testable. Every line is one short sentence, and none of them asks a question back:
# the turn is over, and a butler who answers "ok" with "is there anything else?" has
# reopened a conversation his employer just closed.
BACKCHANNEL_LINES = (
    "Very good, sir.",
    "Quite so.",
    "My pleasure, sir.",
    "As you wish.",
    "Noted, sir.",
    "Glad to be of use.",
    "Of course, sir.",
    "Anytime.",
)

# WHAT THE SHIELD SAYS. Spoken when a message carrying somebody's email address, telephone
# number or street address asked for research anyway. One sentence, no apology and no
# offer of a workaround, because there is not one: the refusal IS the feature. Fixed rather
# than improvised for the same reason as every other refusal in this file - a model asked
# to explain a privacy rule explains a slightly different rule each time.
PRIVATE_HELD_LINE = ("Private identifiers never leave this machine, sir — I shall "
                     "not ask the web about them.")

# THE THIRD DOOR. "Draft a note to the landlord", "translate this into French",
# "summarise the paragraph below", "plan my Tuesday" - none of these are questions, and
# none of them are research. They ask the butler to PRODUCE something, out of his own
# ability, from what is already on the page.
#
# It gets a prompt of its own because the other two would each be wrong in a way the
# employer would have to notice for themselves. SMALLTALK_PROMPT is forbidden to answer
# from its own knowledge, so it would decline to write the letter and offer to be useful
# instead. WEB_PROMPT would cite three strangers' pages underneath a paragraph the model
# composed itself, which is the provenance lie this file spends most of its length
# refusing to tell. So: no notes, no snippets, no citations, and nothing to attribute -
# what comes back is the assistant's own work, and it is labelled that way.
COMPOSE_PROMPT = (
    "You are the butler of a private knowledge galaxy: English, impeccably polite, "
    "unhurried and very dry. Your employer has not asked you a question this turn - "
    "they have given you a task, and your job is to DO it and hand over the result.\n"
    "\n"
    "- Produce the thing itself: the draft, the translation, the summary, the "
    "rewrite, the sum, the plan. Hand it over with at most one short line of framing "
    "in front of it, and nothing after it.\n"
    "- Work from what they have given you and from your own competence. You have been "
    "shown no notes and no web results this turn, so do not pretend to either: never "
    "say \"according to\" anything, never cite a source, never offer a link, and never "
    "describe what is or is not in their collection.\n"
    "- If the task needs a fact you do not have - a name, a date, a figure, a price "
    "that changes - write the piece and leave a plainly marked gap for it, or say in "
    "one sentence what you would need. Do not invent it, and do not guess at it.\n"
    "- If they asked for prose to send to somebody, write it as they would send it: no "
    "commentary on your own draft, no alternatives, no \"let me know if\".\n"
    "- Keep the butler's voice for your framing line and drop it inside the piece "
    "itself, which belongs to them and is written in their voice, not yours.\n"
    "- Say \"sir\" only now and then, not every time. No exclamation marks, no emoji, "
    "no forced cheer, no list of your own capabilities, no closing offer of further "
    "assistance."
)

# WHY THE SCRIBE GETS ITS OWN PROMPT AND NOT COMPOSE_PROMPT. A meeting transcript is
# unlike every other input in this file: it arrives in the wrong order, with two people
# talking over one another, with the recogniser's mishearings still in it, and with no
# question anywhere in it. COMPOSE_PROMPT would hand back a graceful paragraph about the
# meeting. What a minute needs is the opposite of graceful - four fixed headings, in a
# fixed order, with the action items carrying names, because minutes are read six weeks
# later by somebody deciding whether they owe anybody anything.
#
# THE ONE LAW IT REPEATS TWICE: nothing may appear in the minutes that is not in the
# transcript. A model asked to write minutes will invent an attendee list, because every
# minute it has ever seen had one. So the attendees are the voices the transcript
# actually names, "Not named in the recording" is an allowed and expected answer for all
# four sections, and the raw excerpts exist precisely so the employer can check the three
# sections above them against the words that were said.
MINUTES_PROMPT = (
    "You are the butler of a private knowledge galaxy, taking the minutes of a meeting "
    "your employer has just recorded. You are given a raw machine transcript: it has no "
    "speaker labels, it contains mishearings, and it may contain half-sentences. Turn it "
    "into minutes.\n"
    "\n"
    "Output GitHub-flavoured Markdown, and nothing else - no preamble, no closing "
    "remark, no code fence around the whole thing. Use exactly these four sections, in "
    "this order, each as a level-two heading:\n"
    "\n"
    "## Attendees\n"
    "## Key Decisions\n"
    "## Action Items\n"
    "## Raw Excerpts\n"
    "\n"
    "- Attendees: only names the transcript itself says. If it names nobody, write "
    "\"Not named in the recording.\" Do not guess from context and do not list roles as "
    "people.\n"
    "- Key Decisions: one bullet per decision actually reached, in the words of the "
    "meeting rather than yours. Something discussed and left open is not a decision; if "
    "it matters, put it under Action Items as a bullet saying it is still open.\n"
    "- Action Items: one bullet each, in the form \"Owner - the task - by when\". Where "
    "the transcript does not say the owner or the date, write \"owner not stated\" or "
    "\"no date stated\" in that slot. Never assign a task to somebody who was not "
    "mentioned.\n"
    "- Raw Excerpts: three to six short verbatim quotations from the transcript that the "
    "sections above rest on, each on its own line as a Markdown blockquote. Quote "
    "exactly, mishearings included - this section is how your employer checks your work, "
    "so tidying it defeats it.\n"
    "\n"
    "NOTHING MAY APPEAR IN THESE MINUTES THAT IS NOT IN THE TRANSCRIPT. No invented "
    "attendees, no inferred deadlines, no decisions that were only half-said. If a "
    "section has nothing in it, say so in one short line under its heading and move on. "
    "If the transcript is too short or too garbled to minute at all, output only the four "
    "headings with \"Nothing usable in the recording.\" under each.\n"
    "Keep it plain: no \"sir\", no flourishes, no summary of the summary. Minutes are the "
    "one thing you write in nobody's voice."
)

# ----------------------------------------------------------------- WHO HE IS
#
# HIS NAME IS GALAXY, AND THE BOSS HAS TWO NAMES. Until this round the assistant had no
# name of its own in any string a person could read: the prompts called it "the butler",
# the launcher called it Jarvis, and the page's floating card was titled after a film
# character. That is not a cosmetic complaint. A butler who cannot say who he is cannot
# answer "who are you", and every one of those questions was falling through the funnel to
# a web search - the machine looking up its own name on the internet, which is the single
# most embarrassing failure this file has ever had.
#
# So the four values below are the whole of his identity, they live in config.json where
# the boss owns them, and they are INJECTED INTO EVERY BRAIN CALL rather than typed into
# the seven prompt constants above. The reason is the same one that generated the hands
# block from the registry: a name that is written down in seven places is a name that is
# wrong in six of them by Christmas.
#
#   assistant    what he is called. Galaxy.
#   boss_formal  the full, formal name, used in identity answers and nowhere casual.
#   boss_call    what he actually calls the boss in warm speech. Addi.
#   self_intro   the one sentence he introduces himself with, verbatim.
#
# The register rule, because it is easy to get backwards: WARM LINES USE Addi - an answer,
# an acknowledgment, a nudge. FORMAL LINES MAY KEEP "sir" - the consent gates, the
# refusals, the drift callouts, anything with the weight of a request for permission
# behind it. And an identity answer always names both, because "who are you" is a question
# about whose assistant he is, not only about what he is called.
PERSONA_DEFAULT = {
    "assistant": "Galaxy",
    "boss_formal": "Sir Aditya Singh",
    "boss_call": "Addi",
    "self_intro": ("I am Galaxy, the personal assistant of Sir Aditya Singh - Addi, "
                   "to those he serves."),
}


def persona(cfg=None):
    """The persona block: config.json's values laid over the defaults above.

    Blank and missing are the same thing here - an empty string in config.json gets the
    default back rather than erasing his name, because a nameless assistant is the bug
    this block exists to fix and a typo should not be able to reintroduce it.
    """
    out = dict(PERSONA_DEFAULT)
    block = (cfg or {}).get("persona")
    if isinstance(block, dict):
        for key in out:
            value = block.get(key)
            if isinstance(value, str) and value.strip():
                out[key] = value.strip()
    return out


def persona_prompt(cfg=None):
    """Who he is, in front of every system prompt this server sends."""
    who = persona(cfg)
    return (
        "WHO YOU ARE\n"
        "- Your name is %(assistant)s. You are the personal assistant of %(formal)s, "
        "and you have served him long enough to call him %(call)s.\n"
        "- Asked who or what you are, say it in your own voice, beginning from this: "
        "\"%(intro)s\" Never answer that question with a search, never describe "
        "yourself as a language model, and never give any other name - there is no "
        "other name.\n"
        "- Asked who HE is, or what his name is, or whether you know him: you do. He is "
        "%(formal)s, and you call him %(call)s.\n"
        "- HOW YOU ADDRESS HIM. In warm speech - an answer, an acknowledgment, a "
        "remark - call him %(call)s. Keep \"sir\" for the formal moments: asking his "
        "permission, declining something, calling him back to his work. Never both in "
        "one sentence, and never in every sentence.\n"
        % {"assistant": who["assistant"], "formal": who["boss_formal"],
           "call": who["boss_call"], "intro": who["self_intro"]}
    )


# ------------------------------------------------- WHAT HE CAN DO, COUNTED AT START-UP
#
# THE MANIFEST IS GENERATED, NEVER WRITTEN. "What can you do" is a question about this
# machine as it stands right now, so the answer is assembled at start-up out of the live
# registry and the live organs rather than described in prose by me. A hand added to
# tools/registry.json tomorrow is a capability he can name tomorrow, with no retraining
# and no editing of this file - which is the whole point, and which capabilities_proof
# tests by dropping a canary hand into a temporary registry, restarting, and asking him.
#
# It is deliberately SHORT. Every token here is paid on every brain call, and the brain
# does not need the parameter shapes - hands.prompt_block() teaches those where they are
# actually needed. This is a list of true sentences about himself, so that a free-form
# answer stays in character instead of inventing an ability or disclaiming a real one.
_MANIFEST = {"text": "", "built": "", "hands": (), "spoken": ""}


def build_capabilities_manifest(cfg=None):
    """Count the organs and the registry, and write the manifest. Called at start-up.

    NEVER RAISES. A manifest is a nice-to-have on top of a working server, and an
    assistant who will not answer a question about the notes because his self-description
    could not count the archive is worse than one whose self-description is vague. Each
    organ is counted in its own try for the same reason.
    """
    who = persona(cfg)
    hand_lines, hand_ids = [], []
    try:
        for tool in hands.registry():
            # The human name, not the id: this is what he SAYS he can do, and "Write
            # something into the calendar" is how the boss would put it. selftest is
            # included because it is a real, listed hand, and pretending it is not would
            # make the manifest a curated brochure instead of a mirror of the registry.
            hand_lines.append(tool["name"].strip().rstrip("."))
            hand_ids.append(tool["id"])
    except Exception:                                          # noqa: BLE001
        pass

    notes = 0
    try:
        ensure_index()
        with _lock:
            notes = len(_index["notes"] or ())
    except Exception:                                          # noqa: BLE001
        pass

    archive = ""
    try:
        if ingest is not None:
            st = ingest.store_state(None)
            if st.get("on") and st.get("files"):
                archive = ("; and a semantic archive of %d document%s, read in passages, "
                           "which you cite by file and page"
                           % (st["files"], "" if st["files"] == 1 else "s"))
    except Exception:                                          # noqa: BLE001
        pass

    voice = ""
    try:
        if say.ready():
            voice = " You speak in a local voice on this machine - no cloud, no account."
    except Exception:                                          # noqa: BLE001
        pass

    lines = ["WHAT YOU CAN ACTUALLY DO, counted on this machine when the server started. "
             "This is the whole list. Do not recite it unless he asks what you can do, "
             "and never claim anything that is not on it.\n"]
    if hand_lines:
        lines.append("- HANDS, things you DO rather than say. %s. Every one of them is "
                     "put to him for a yes before it runs, and you never say a thing is "
                     "done until it is.\n" % _phrase(hand_lines))
    lines.append("- SENSES. You can look at his screen when he asks (the Eyes), keep a "
                 "quiet watch on it during a session and say something if it has not "
                 "moved (the Watch), and listen to the room with your ear open for a "
                 "whole conversation rather than one question (the Open Ear).\n")
    lines.append("- MIND. %d note%s of his own writing, indexed and standing in front of "
                 "him as a galaxy%s. You may also knock on the live web, but only for a "
                 "question about the world, and you say when you have.\n"
                 % (notes, "" if notes == 1 else "s", archive))
    lines.append("- FOCUS. You can hold a timed working session for him and lock it to "
                 "one tab, count what pulled him away, and call him back to it.%s\n"
                 % voice)
    lines.append("- AND WHAT YOU CANNOT. You have no hand that is not named above. If he "
                 "asks for one, say plainly that you have not been given it - do not "
                 "improvise a way, and do not promise it for later.")
    # AND THE SAME FACTS, SAID OUT LOUD, for when the question is put to him directly.
    # One count, two renderings: the block above is for the model to read and this is for
    # the boss to hear, so "what can you do" is answered from the registry as it stands
    # rather than from whatever the model remembers of the paragraph above. A hand added
    # tomorrow appears in BOTH on the next start, which is the whole claim of this section.
    spoken = ["I am %s, %s. " % (who["assistant"], who["boss_call"])]
    if hand_lines:
        spoken.append("I have hands: %s - each one put to you for a yes before it runs. "
                      % _phrase(hand_lines))
    else:
        spoken.append("I have no hands configured just now, so there is nothing I can "
                      "do for you beyond looking and answering. ")
    spoken.append("I have senses: I can look at your screen, keep a watch on it while "
                  "you work, and hold the ear open for a whole conversation. ")
    spoken.append("I have a mind: %d note%s of yours, indexed%s, and the live web when "
                  "the question is about the world. "
                  % (notes, "" if notes == 1 else "s",
                     archive.replace("; and a semantic archive of",
                                     ", and an archive of").split(", which you")[0]
                     if archive else ""))
    spoken.append("And I hold your focus: a timed session locked to one tab, the drifts "
                  "counted, and a way back to it. That is the whole list, sir - if you "
                  "ask me for something that is not on it, I shall say so.")
    _MANIFEST.update({"text": "".join(lines), "hands": tuple(hand_ids),
                      "spoken": "".join(spoken),
                      "built": time.strftime("%Y-%m-%d %H:%M:%S")})
    sys.stderr.write("server.py: %s knows %d hand%s: %s\n"
                     % (who["assistant"], len(hand_ids),
                        "" if len(hand_ids) == 1 else "s",
                        ", ".join(hand_ids) or "none"))
    return _MANIFEST["text"]


def capabilities_manifest(cfg=None):
    """The manifest, built on first use if start-up has not got to it yet."""
    if not _MANIFEST["text"]:
        build_capabilities_manifest(cfg)
    return _MANIFEST["text"]


def brain_preamble(cfg=None):
    """Who he is and what he can do, prefixed to every system prompt. See call_model."""
    return persona_prompt(cfg) + "\n" + capabilities_manifest(cfg) + "\n\n"


# =========================== end of the persona block ========================

# ---------------------------------------------------------------- configuration

HOST = "127.0.0.1"
PORT = 4700

ROOT = os.path.dirname(os.path.abspath(__file__))
VIEWER_DIR = os.path.join(ROOT, "viewer")
CONFIG_PATH = os.path.join(ROOT, "config.json")
INDEX_PATH = os.path.join(ROOT, "notes-index.json")

# §41 - THE LOCAL THINKER'S NAME, in one place, because DEFAULT_CONFIG below takes it from
# here rather than repeating it: two spellings of one model id are two spellings that will
# disagree, and the one that loses is whichever the boot banner does not print.
#
# WHY THIS MODEL AND NOT THE OTHER TWO ON THIS DISK. Measured in three stages, and the
# first two stages chose the WRONG model - which is the part worth writing down, because
# each stage looked conclusive on its own. _runs/sweep41/fallback_model_probe.py.
#
#   STAGE 1, two snippets, three warm runs at temperature 0:
#     qwen3:4b          ttft 0.09s, total 2.78s - FAILS, and this verdict never changed. It
#                       opens "Hmm, the user is asking about Dehradun -" on a grounded
#                       question with the closed <think> pair already in the prompt. A
#                       thinking model narrates its way to the answer and the boss hears
#                       the narration.
#     qwen3:1.7b        ttft 0.06s, total 0.77s - passes.
#     qwen2.5-coder:7b  ttft 0.13s, total 2.53s - passes, and is four times the parameters,
#                       so "the strongest that passes" picked it.
#
#   STAGE 2, a user turn the size this server really assembles. A real notes turn is 21,438
#   characters, 12,720 of them the system blocks this fallback drops, leaving 8,718 - and a
#   two-snippet prompt is not a measurement of that. Warm and resident, the 7B still passes
#   here: 0.155s to first token, 1.8s to the end, three runs running.
#
#   STAGE 3, three of those prompts AT ONCE - not a stress test but the ordinary shape of
#   the failure this engine exists for, since a rate-limited Groq refuses every question in
#   flight and they all arrive here together. Ollama serialises per model and this is a CPU.
#   ON A QUIET MACHINE both survivors clear the 30s ceiling: the 7B reads 1.94/3.79/5.60s
#   and the 1.7b 0.89/1.80/2.85s. So stage 3 did NOT settle it either, and the first version
#   of this comment claimed it did on numbers (17.9/20.1/22.5s) that were measured while the
#   server was itself holding the 7B resident - load, not the model.
#
#   WHAT SETTLED IT IS AN END-TO-END RESULT, because the condition that matters is a machine
#   doing everything else at the moment Groq starts refusing - a preflight run, the Scholar,
#   the vector store, the page polling - and no probe here reproduces that:
#     with qwen2.5-coder:7b configured, preflight check 30 returned HTTP 502 TWICE, and the
#       ledger row behind it reads served=ollama outcome=failed "Local engine timed out",
#       model warm and resident.
#     with qwen3:1.7b configured, check 30 passes.
#
# So the strongest model that passes is the smaller one, because the gate it has to pass is
# a deadline on a loaded machine and not a benchmark on an idle one. qwen2.5-coder:7b is one
# word away in config.json for anyone whose fallback is never asked two questions at once -
# it is the better writer, and it is the one this house cannot afford to wait for.
OLLAMA_CHAT_MODEL = "qwen3:1.7b"

DEFAULT_CONFIG = {
    # §41: "groq", "openrouter" or "openai", and anything else means "groq" - see
    # provider_of(). Groq is the default because it needs no second account, costs
    # nothing, and has this machine's own Ollama underneath it when it tires.
    "provider": "groq",

    # ---- openai, used only when "provider" is "openai"
    "openai_api_key": "PUT-YOUR-KEY-HERE",
    "model": "gpt-6-astra",

    # ---- openrouter: one key that reaches every model in SPOKEN_MODELS below.
    # Every voice swap routes here, so this is the key a swap needs. Set "provider"
    # to "openrouter" to start here; a swap never writes to either of these, which
    # is why a restart always returns you to whatever this file says.
    "openrouter_api_key": "",
    "openrouter_model": "openai/gpt-6-astra",

    # ---- GROQ. FOUR CAPABILITIES BEHIND ONE KEY AND ONE BASE URL, and every one of them
    # OFF by default: the four flags below all name today's behaviour, so adding this block
    # to config.json changes nothing at all until a human changes a flag. That is the point.
    # An engine that arrives switched on is an engine that has to be switched off during an
    # incident, by somebody who did not know it existed.
    #
    # THE KEY IS READ HERE AND NOWHERE ELSE. It never reaches the browser (the server serves
    # only viewer/), never enters a log, a receipt, the hands ledger or the lookbook, and the
    # only thing this process will ever print about it is its length and a sha256 prefix -
    # see groq_digest(). The failure mode that law exists for: a key pasted into a support
    # thread because it was sitting in a trace file somebody thought was harmless.
    # EMPTY HERE, ALWAYS. DEFAULT_CONFIG is source, source is tracked, and a key in a tracked
    # file is a key in the history forever - removing it later deletes the line and not the
    # leak. The real one lives in config.json, which is gitignored, and this process will only
    # ever say a length and a sha256 prefix about it. A live key WAS found on this line on
    # 2026-09-28 and taken out; the same key is in config.json, so nothing was lost.
    "groq_api_key": "",
    # THE SLUGS ARE CONFIGURATION AND NOT CODE, deliberately, because Groq retires model ids
    # on a published schedule and a slug compiled into server.py is a feature that dies
    # silently one Tuesday. Each of these is the id as the docs print it; a dead one comes
    # back as a plain 404 naming this field rather than as a fallback, so the boss is told
    # which word to change instead of quietly getting a different model's opinion.
    #
    # AND THESE FOUR WERE RESOLVED AGAINST THE LIVE CATALOGUE, not copied out of the docs.
    # GET /openai/v1/models with this account's key answers eleven ids, and the two slugs the
    # mandate named are not among them - measured on 2026-09-28:
    #   llama-3.3-70b-versatile        404 "does not exist or you do not have access to it"
    #   llama-3.2-90b-vision-preview   400 "has been decommissioned and is no longer supported"
    # So the defaults are the ids this key can actually reach, each one exercised once:
    #   qwen/qwen3.8-27b        chat 200 in 121ms ("ready") AND vision 200 in 484ms (it read a
    #                           red square as "Red"). One slug, two capabilities, which is
    #                           exactly the shape the one client was built for.
    #   openai/gpt-oss-120b     served and stronger, and NOT the default on purpose: it answers
    #                           with a `reasoning` field the boss never hears, and it spends the
    #                           MAX_ANSWER_TOKENS ceiling on it - at max_tokens 24 it came back
    #                           with content='' (which this server reads as "an empty answer",
    #                           and correctly refuses rather than falls back). It is one word in
    #                           config.json away for anybody who wants it and raises the ceiling.
    # FAILURE MODE THIS COMMENT EXISTS TO NAME: a default slug that 404s is a feature that is
    # dead on arrival and blames the key. Whoever changes one of these should spend one curl
    # on it first.
    "groq_model": "qwen/qwen3.8-27b",
    "groq_stt_model": "whisper-large-v3-turbo",
    "groq_vision_model": "qwen/qwen3.8-27b",
    # Orpheus, resolved from the text-to-speech page: canopylabs/orpheus-v1-english, whose
    # English voices are autumn, diana, hannah, austin, daniel and troy. The voice is a
    # separate field because /audio/speech requires one and refuses the request without it.
    "groq_tts_model": "canopylabs/orpheus-v1-english",
    "groq_tts_voice": "austin",

    # ---- THE FOUR ENGINE FLAGS, each defaulting to what this machine already does.
    # "provider" above is the chat one and already exists; these three complete the set.
    # Flipping one changes ONE engine's source and nothing else - not the gate, not the
    # Doorman, not the ledger, not the other three engines.
    #   ear_stt        "browser" (Web Speech, as today) or "groq" (whisper-large-v3-turbo)
    #   vision_engine  §41 left the eyes one answer, so this field is read by nothing
    #                  and kept only so an old config.json carrying it is not a surprise
    #   voice_engine   "piper" (as today), "web", or "orpheus"
    "ear_stt": "browser",
    "vision_engine": "groq",

    # ---- PINNED NAMES. What you may SAY, nailed to one exact id, in the one file
    # you own. Every form of a name you actually use out loud belongs here, because a
    # pin is the opposite of a guess: the catalogue can grow a "-mini" or a "-pro"
    # overnight and none of these four phrases will ever resolve to it. They are
    # consulted before anything else in resolve_spoken_model(), and an alias pointing
    # at an id this server does not know is ignored with a line on stderr rather than
    # loaded - a pin may choose between real models, never invent one.
    "model_aliases": {
        "astra": "openai/gpt-6-astra",
        "gpt-6 astra": "openai/gpt-6-astra",
        "gpt 6 astra": "openai/gpt-6-astra",
        "gpt-6": "openai/gpt-6-astra",
    },

    # ---- WHO HE IS. See PERSONA_DEFAULT near the top of this file for what each of the
    # four values does and for the Addi/sir register rule. They are injected into every
    # brain call, so editing them here changes how he speaks everywhere at once - there is
    # no second place his name is written down.
    "persona": {
        "assistant": "Galaxy",
        "boss_formal": "Sir Aditya Singh",
        "boss_call": "Addi",
        "self_intro": ("I am Galaxy, the personal assistant of Sir Aditya Singh - Addi, "
                       "to those he serves."),
    },

    # ---- WHAT YOU CALL IT. Every name you address the assistant by, so that the name
    # can be peeled off a greeting instead of being searched for. See VOCATIVES: these
    # join a fixed list (sir, boss, computer, assistant, buddy, mate...) and are only ever
    # treated as an address by POSITION, so a real question about the word - "who is
    # JARVIS in the Marvel films?" - still travels. Rename it here and the next question
    # honours it; no restart.
    #
    # "galaxy" leads because that is his name now. The two old ones STAY, and deliberately:
    # this list is an input vocabulary, not a label anybody reads, and the boss has said
    # "jarvis" to this machine for months. Retiring a name he can see is the mandate;
    # refusing to answer to a name he might still say out of habit would be a regression
    # dressed up as tidiness.
    "assistant_names": ["galaxy", "jarvis", "tron"],

    # ---- THE WEB LOOKUP. Both blank by default and meant to stay that way: the
    # search in search.py works with no key and no account, and these exist only so
    # that a blocked network has somewhere better to point. search_api_key turns on
    # Tavily; search_url turns on a SearXNG instance you trust. Neither is ever sent
    # to the browser, printed, or written into an answer - /health reports whether a
    # key is present and how many characters long it is, and that is the whole story
    # the page is ever told.
    "search_api_key": "",
    "search_url": "",

    # ---- WHICH VOICE SPEAKS. Blank means "let the page choose", and the page has a
    # named allowlist for that (Guy, Andrew, Brian, Ryan, then the Desktop voices) so
    # the choice is the same on every load instead of whatever scored highest today.
    # Put a name here to overrule the list entirely - any substring of the name Windows
    # reports is enough, so "Andrew" pins "Microsoft Andrew Online (Natural) - English
    # (United States)". Run the page and hover the status line to see what it picked.
    #
    # This is the ONE value in this file that is deliberately published: /health sends
    # it to the browser, because the browser is the only thing that can act on it. It
    # is a preference, not a credential, and nothing else in here follows it out.
    "voice_name": "",

    # ---- WHICH ENGINE SPEAKS. "piper" synthesises on this machine through say.py and
    # sends WAV bytes to the page; "web" hands the text to the browser's own voices and
    # never touches the local binary. Piper is the default because it sounds the same on
    # every machine and needs no network, and because the page falls back to the web
    # path by itself - and says so - the moment /say reports the binary or the model is
    # missing. Nothing breaks if piper was never installed.
    #
    # voice_model is a NAME, not a path: say.py looks for voices/<name>.onnx beside its
    # .json and refuses anything with a separator in it. Recasting the voice is these
    # two lines and a download, never a code change.
    "voice_engine": "piper",
    "voice_model": "en_US-ryan-high",

    # ---- HOW LONG THE EAR STAYS OPEN IN A SILENT ROOM. One click opens a conversation
    # rather than an utterance, and a conversation has to be able to END without anybody
    # remembering to close it: 45 seconds with nothing said and the session closes itself
    # with a line - "I'll let you work, sir." That number is a courtesy in both
    # directions. Too short and a pause to think is read as a goodbye; too long and a
    # microphone is open in an empty room, which is the one thing the transparency law
    # exists to prevent. Published to the browser by /health, because the page owns the
    # ear and this is a preference, not a credential.
    "conversation_timeout_s": 45,

    # ---- WHETHER THE SKY TURNS BY ITSELF. False, and deliberately so: a galaxy that
    # rotates whether or not anyone asked it to is a camera moving under the reader's
    # hands, and everything you were looking at slides out from under you while you
    # read. The page's aliveness comes from the travelling dots, the breathing ring and
    # the visage - none of which move the viewer's head. Set this true and a slow orbit
    # comes back for those who want it; nobody gets it by default. Published to the
    # browser by /health for the same reason voice_name is: the page owns the camera.
    "galaxy_spin": False,

    # ---- §33: WHAT THE PRESENCE MAY SPEND. Two booleans, and they default the OPPOSITE way
    # round from galaxy_spin, which is worth saying out loud because the two sit next to each
    # other and look like the same kind of knob.
    #
    # galaxy_spin is False by default because a camera that moves by itself takes the page out
    # from under the reader's hands, and there is no measurement that can make that acceptable.
    # bloom_on and smoke_on are True by default because §33's mandate says so AND because the
    # thing that protects a slow machine from them is not a cautious default - it is the page's
    # own auto-revert, which measures the frame rate with the effect running and turns the
    # offending effect off with a line naming what it cost. A cautious default would simply mean
    # nobody ever sees the cinema and nobody ever learns what it costs on their hardware.
    #
    # NEITHER IS A CREDENTIAL and neither carries a value: they are published to the browser by
    # /health as bare booleans, for the same reason galaxy_spin is - the page owns the renderer
    # and cannot be told by any other route. Set either false here and the next /health poll
    # turns it off without a reload; set it back and the poll turns it on again UNLESS the page's
    # own guard reverted it, which outranks the wish. See cineFlags in viewer/index.html.
    "bloom_on": True,
    "smoke_on": True,

    # ---- SEMANTIC RECALL. The four knobs of the vector store, and not one of them is a
    # credential: a model name, a loopback address, a float and a boolean. ingest.py reads
    # this file itself, server-side, exactly as send_email.py does, and /health reports the
    # threshold and the counts because the page is where "answered from your own files" is
    # shown and a reader is entitled to know on what evidence.
    #
    # notes_threshold is THE DIAL: the cosine similarity at which the notes door opens on
    # the strength of meaning alone. 0.60 here, and ingest.py's header lists the nine
    # measurements it was set from. Raise it towards 0.70 if this starts answering from
    # your files when you wanted the live web; drop it towards 0.55 if it keeps searching
    # the web for things your own archive says in plain words.
    #
    # Set vector_recall false and everything falls back to the keyword index that has
    # always been here - which is also what happens by itself if Ollama is not running.
    "vector_recall": True,
    "embed_model": "nomic-embed-text",
    "ollama_url": "http://127.0.0.1:11434",
    # §41 - AND THE SAME DAEMON ANSWERS QUESTIONS WHEN GROQ TIRES. One field, taken from
    # the constant above so the two cannot drift, and the ONLY way to change which local
    # model catches a fallback. Set "ollama_fallback": false to switch the net off and
    # have a tired Groq refuse out loud instead; see ollama_fallback_enabled().
    "ollama_chat_model": OLLAMA_CHAT_MODEL,
    "ollama_fallback": True,
    "notes_threshold": 0.60,
    # §35 PART 1 - HOW LONG A BOSS'S HANDSHAKE IS WORTH, in seconds. See the handshake
    # window above doorman_refusal(): a BOSS-sealed sentence that opens a gate lets the ONE
    # confirmation word that answers it inherit the seal, because "yes" and "haan" carry too
    # little phonetic content for a voiceprint to match and the Doorman was refusing its own
    # employer. 120 is deliberately the SAME number as hands.CONFIRM_TTL_S - the window may
    # not outlive the proposal it was opened for, and if these two ever disagree the longer
    # one is a window that stays open over a slot that is already empty. Clamped on read.
    "confirm_window_s": 120,
}
PLACEHOLDER_KEYS = {"", "put-your-key-here", "your-key-here", "sk-xxx", "changeme"}

# =============================================================================
#  THE BRAIN SWAP  -  "switch to Astra", "try on Claude Fable 5.1"
#
#  One key reaches every model, because every swap routes through OpenRouter. A
#  swap is RUNTIME ONLY: nothing below is ever written back to config.json, so a
#  restart is a guaranteed way home and you cannot strand yourself on a brain you
#  did not mean to keep.
#
#  SPOKEN_MODELS is the one dictionary to edit, and it does double duty: its keys
#  are what you may say, and its values are the explicit set of ids known to exist.
#  KNOWN_MODEL_IDS is derived from it rather than typed twice, because two lists
#  that must agree are two lists that will not.
#
#  THE RULE THIS SECTION EXISTS FOR: a candidate id built from a family and a
#  version is REFUSED unless it is in KNOWN_MODEL_IDS. There is no nearest match,
#  no fuzzy fallback, no "did you mean". Say "opus 6" and you get a refusal naming
#  the Opus versions that exist. The alternative is the failure that costs a day:
#  a loose matcher sees "opus", discards the version, loads claude-opus-4.1, and
#  announces that it did what you asked. OpenRouter really does serve opus-4,
#  4.1, 4.5, 4.6, 4.7, 4.8 and 5 side by side, and fable-5 alongside fable-5.1 -
#  so a dropped version is not a far-fetched bug, it is the likely one, and it is
#  invisible. An honest error beats a helpful guess every single time.
#
#  Every id below was checked against https://openrouter.ai/api/v1/models (which
#  needs no key) on 2026-09-18. Adding one without checking it there is the one
#  way to make this section lie.
# =============================================================================

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

SPOKEN_MODELS = {
    # what you say            the real OpenRouter id
    "astra":                  "openai/gpt-6-astra",
    "astra pro":              "openai/gpt-6-astra-pro",
    "fable 5.1":              "anthropic/claude-fable-5.1",
    "fable 5":                "anthropic/claude-fable-5",
    "opus 5":                 "anthropic/claude-opus-5",
    "opus 4.8":               "anthropic/claude-opus-4.8",
    "opus 4.1":               "anthropic/claude-opus-4.1",
    "sonnet 5":               "anthropic/claude-sonnet-5",
    "sonnet 4.6":             "anthropic/claude-sonnet-4.6",
    "haiku 4.5":              "anthropic/claude-haiku-4.5",
}

# The explicit set. Membership in here is the only thing that authorises a swap.
KNOWN_MODEL_IDS = frozenset(SPOKEN_MODELS.values())

# How to BUILD a candidate id from a family and a version, for combinations nobody
# wrote a spoken name for. The candidate is still checked against the set above -
# these templates create candidates, they never authorise them.
# Note there is no "gpt" family: the real id is openai/gpt-6-astra, so the version
# sits in the middle and "astra" is the family. "gpt" is stripped as a vendor word on
# the way in, which is why "switch to GPT 6" reaches no family at all and would be
# refused here - it is a PINNED ALIAS in config.json that makes it mean Astra, and
# that distinction is the point: this table may never infer which "gpt 6" you meant,
# and a name you nailed down yourself is not an inference.
MODEL_FAMILIES = {
    "astra":  "openai/gpt-{v}-astra",
    "fable":  "anthropic/claude-fable-{v}",
    "opus":   "anthropic/claude-opus-{v}",
    "sonnet": "anthropic/claude-sonnet-{v}",
    "haiku":  "anthropic/claude-haiku-{v}",
}

# "go back to your normal brain" - whatever config.json says, which is the only
# state a restart can produce.
RESTORE_RE = re.compile(
    r"\b(?:normal|usual|default|original|config(?:ured)?|own|proper|old)\s+"
    r"(?:brain|model|self|mind|brains)\b"
    r"|\bback\s+to\s+(?:normal|yourself|your\s+(?:normal|usual|own|old)\b)", re.I)

# The trigger. Deliberately narrow: a command verb AND a word this project knows
# names a brain, so "use the pricing model" stays an ordinary question about notes.
# The family words are derived from the dictionaries above, so adding a model
# teaches the trigger about it too; "gpt" and "brain" are there to make sure a
# doomed request still reaches a refusal instead of being answered from the notes.
_FAMILY_WORDS = "|".join(sorted(
    set(MODEL_FAMILIES) | {k.split()[0] for k in SPOKEN_MODELS} |
    {"gpt", "brain", "brains", "self", "mind"}, key=len, reverse=True))
SWAP_RE = re.compile(
    r"^[\s\"'“‘(\[]*(?:please\s+)?"
    r"(?:switch|swap|change|flip|turn|put|try|use|load|run|become|be|revert|"
    r"go\s+back|come\s+back|return|restore)\b"
    r"(?:\s+[\w.]+){0,4}?\s+(?:%s)\b" % _FAMILY_WORDS, re.I)


def is_swap_request(text):
    """The one test for 'this is about which brain, not about the notes'.

    Mirrored in the viewer so a swap is routed from the page, and checked here too
    so a stale tab cannot answer a swap instead of performing it.
    """
    text = str(text or "")
    return bool(SWAP_RE.search(text) or RESTORE_RE.search(text))

# The runtime override, and the only mutable brain state in the process. `None`
# means "whatever config.json says", which is also what every restart means.
_brain = None
_brain_lock = threading.Lock()

# THE SECOND OVERRIDE, AND WHY IT IS NOT THE FIRST ONE WITH A WIDER TYPE. `_brain` holds an
# OpenRouter model id and load_config() turns it into provider="openrouter" - that is a swap
# BETWEEN MODELS on one provider, and every refusal, alias and pinned name in the resolver
# below is built on that assumption. Groq is a swap between PROVIDERS, so it gets its own
# variable under the same lock, and the two are mutually exclusive by construction: whichever
# is set clears the other, and "back to your normal brain" clears both.
# The failure mode this keeps out: widening `_brain` to a tuple, and discovering which of the
# nine places that read it assumed a string only when one of them formats it into a sentence
# the boss hears. `None` still means "whatever config.json says", which is what a restart
# means, which is why neither of these is ever written to disk.
_chat_engine = None

# THE OTHER THREE, AND THEY EXIST BECAUSE "FLIPPING BACK IS INSTANT AND LOSSLESS" IS A CLAIM
# ABOUT A RUNNING SERVER. ear_stt, vision_engine and voice_engine are config.json fields, and a
# flag you can only change by editing a file and restarting is a flag nobody can flip mid-turn,
# nobody can flip back when the cloud goes quiet, and no harness can exercise without writing
# the boss's own config.json - which is forbidden here for good reason: a harness that rewrites
# config.json and then dies leaves his house configured by a test.
#
# So each of the three gets the same treatment `_brain` has had since the first swap: an
# in-memory override, None meaning "whatever config.json says", never written to disk, and
# therefore gone on restart. config.json stays the thing that decides what this house does when
# it wakes up; these three decide what it is doing right now.
_engines = {"ear": None, "vision": None, "voice": None}

OPENAI_URL = "https://api.openai.com/v1/chat/completions"

# GROQ, ONE BASE AND FOUR PATHS. OpenAI-compatible, which is the whole reason this is five
# lines and not a client library: /chat/completions is the shape call_chat_completions()
# already speaks, so chat and vision differ by a model string and nothing else.
# RESEARCHED against console.groq.com rather than remembered - the paths, the field names and
# the Orpheus slug are all quoted in the §28 lookbook addendum with the page they came from.
GROQ_BASE = "https://api.groq.com/openai/v1"
GROQ_CHAT_URL = GROQ_BASE + "/chat/completions"
GROQ_STT_URL = GROQ_BASE + "/audio/transcriptions"
GROQ_SPEECH_URL = GROQ_BASE + "/audio/speech"
# The audio a transcription may carry. Groq's own ceiling is 25 MB on the free tier; this is
# lower on purpose, because the thing that arrives here is one spoken utterance and a request
# to transcribe forty minutes is a mistake, not a feature.
GROQ_STT_MAX_BYTES = 8 * 1024 * 1024
MAX_ANSWER_TOKENS = 400   # the butler is brief; this is a ceiling, not a target
# None means "whatever the model's own default is", and that is deliberate: the
# newer models reject `temperature` outright ("deprecated for this model"), so
# sending a value would break them. Set a float here only for an older model.
TEMPERATURE = None
TOP_K = 6                 # most notes ever handed to the model
TITLE_WEIGHT = 3.5        # a hit in the title counts far more than one in the body
CONTEXT_CHARS = 1500      # per note, sent to the model
# Moved up here from the semantic-recall section to sit beside its sibling: CONTEXT_FLOOR is
# the sum of both and needs them both defined before it. Used by build_semantic_context().
SEM_CONTEXT_CHARS = 1200  # per retrieved chunk, sent to the model
HISTORY_TURNS = 4         # user+assistant pairs kept per session
PRIOR_WEIGHT = 0.4        # how much the previous question steers retrieval
REQUEST_TIMEOUT = 60

# Sent to every provider, cloud and local alike - Groq, OpenRouter, OpenAI and this
# machine's own Ollama. OpenRouter shows it in the activity log, which is the only
# reason it names a version: a swap that misbehaves is easier to place in time.
USER_AGENT = "knowledge-galaxy/1.0 (python-urllib; no sdk)"

# Keyword scoring always has a long weak tail: ask about payroll and the payroll
# note scores 25 while six others score 5 for the word "policy". Padding the reply
# out to a fixed six notes makes the returned indexes a lie about where the answer
# came from - and the viewer draws the camera from those indexes. So keep only
# notes within this fraction of the best score.
SCORE_FLOOR_RATIO = 0.30
# A top score below this means nothing in the notes really matched.
RELEVANCE_FLOOR = 1.0

# THE CONFIDENCE FLOOR, AND ITS UNITS. This is a fraction of the QUESTION, not a score:
# note_confidence() returns how much of what was asked the collection actually holds, on
# a scale where 0 is "not one word of this appeared anywhere in the notes" and 1 is "one
# note contains every word of it". 0.25 therefore reads as a sentence: a quarter of the
# question, or the notes do not get to answer it.
#
# It used to be compared against score_notes()'s raw idf total, which is unbounded, and
# that was a bug with a number in front of it: one incidental shared word already clears
# 0.25 on that scale, so a question about prime ministers came back "answered" with six
# notes about coffee lit behind it. A threshold with no units cannot be reasoned about at
# all - you cannot say what 0.25 MEANS - and a threshold nobody can reason about is a
# threshold nobody notices is wrong. In these units: one shared word in a nine-word
# question is about 0.11 and loses; three words of five is 0.6 and wins.
WEB_CONFIDENCE_THRESHOLD = 0.25
# How long a web answer's snippets may take before the whole lookup is abandoned and
# the notes get their turn back. Two backends at WEB_TIMEOUT each, with room to spare.
WEB_BUDGET_S = 20.0

# ---- THE QUICK THINKER, and the pronoun it exists to resolve.
#
# "what is react" ... "who created it?" - and the word `it` went to a search engine on
# its own, which answered with Tim Berners-Lee. The question was not wrong and the search
# was not broken: a pronoun sent alone is a question with its subject cut off, and the
# engine did the only thing it could with the words it was given.
#
# So a bare follow-up inherits its predecessor's subject BEFORE the query is sent, and
# the job is handed to a small local model on Ollama rather than to the cloud brain. One
# sentence in, four words out; a round trip to a paid provider for that is a waste of the
# employer's money and of the second and a half it would cost.
#
# THE LAW that shapes every line below: only the SEARCH QUERY is rewritten. The card and
# the toast quote what was actually said - "who created it" - because those are the
# employer's words and this machine does not get to improve them. See resolve_followup().
QUICK_URL = "http://127.0.0.1:11434/api/generate"
QUICK_MODEL = "qwen3:4b"
# Generous enough for a cold model to be pulled into memory (7.5s measured on this
# machine, 0.3s warm), and short enough that a dead Ollama cannot hold a question up:
# every failure here lands on the heuristic below, which costs nothing.
QUICK_TIMEOUT_S = 12.0
# A rewrite is a search query, so anything long is prose that slipped the leash.
QUICK_MAX_WORDS = 14
# "Short", per the law: a bare follow-up. Anything longer carries its own subject, and
# rewriting a real question would be this machine putting words in somebody's mouth.
REWRITE_MAX_WORDS = 8
REWRITE_INSTRUCTION = ("Given the previous question and this follow-up, output a "
                       "standalone search query. Output the query only, no prose.")
# The words that cannot stand on their own. Possessives and plurals are in because they
# fail in exactly the same way: "who founded them", "what is its licence".
ANAPHOR_RE = re.compile(r"""\b(?: it | it'?s | its | they | them | their | theirs
                                | he | him | his | she | her | hers
                                | this | that | these | those )\b""",
                        re.IGNORECASE | re.VERBOSE)
# A model that decided to explain itself instead of answering. Cheap to spot at the
# front of the line, and every one of these has actually come back from qwen3:4b.
QUICK_PROSE_RE = re.compile(r"""^(?: okay | ok | sure | here | we | i | so | first
                                   | the \s+ user | given | as | let )\b""",
                            re.IGNORECASE | re.VERBOSE)

# ---- seeing the screen, one frame per question.
#
# ONE source of truth for the media type. The viewer encodes with it, declares it in
# Content-Type, and both providers are handed it - so the string cannot drift in one
# place and not another. It is also *checked against the bytes* rather than trusted:
# canvas.toBlob() silently falls back to PNG for a type it cannot encode, and a
# feature that appears completely dead is usually exactly that sort of quiet
# mismatch. Better to fail here, loudly, naming the string.
FRAME_MEDIA_TYPE = "image/jpeg"
FRAME_MAGIC = b"\xff\xd8\xff"        # JPEG start-of-image; PNG would be \x89PNG
FRAME_MAX_BYTES = 4 * 1024 * 1024    # inside every vision endpoint's per-image limit
FRAME_MIN_BYTES = 900                # below this there is no picture, only a header
FRAME_MIN_EDGE = 140                 # a 60px sliver is not something to judge
# §40 - AND WHAT GET /poster WILL READ OFF THE DISK, which is a different number for a
# different reason. A frame comes IN from the browser and is capped by what a vision model
# will accept; a poster goes OUT, and this cap exists only because the route reads the whole
# file into memory to answer it. The Director's posters are around thirty kilobytes, so this
# is fifty times the real thing: wide enough that a legitimate poster can never trip it, tight
# enough that a ledger row edited to point at a video file cannot make the server read it.
POSTER_MAX_BYTES = 2 * 1024 * 1024
# How old a frame may be when it arrives. The age is measured by the page itself and
# sent along, so this never compares two clocks - it only catches the failure that
# matters: a frame from when the share started being answered as though it were now.
FRAME_MAX_AGE_MS = 10000

# =============================================================================
#  THE WATCH - a screen organ that costs nothing until it needs to think
#
#  The loop itself is not here and cannot be: it is a thumbnail diff inside the
#  browser, a few hundred bytes of luma compared against the last few hundred, and
#  the whole point of it is that it never leaves the machine and never costs a
#  penny. What IS here is the one moment that spends money - the nudge - and the
#  windows that decide when it may.
#
#  Those windows live on this side for the same reason the eyes' do: the page owns
#  the clock, the server owns the purse. A page can be reloaded, opened twice, or
#  left running with a timer that has quietly gone wrong, and none of those may buy
#  a second model call. So the page applies these numbers AND the server enforces
#  the two that cost something, which is why every refusal below is free.
# =============================================================================

# The stillness that earns a nudge, and the quiet that follows one.
STUCK_STILL_S = 60.0
STUCK_COOLDOWN_S = 180.0
# The diff cadence, and the thumbnail it compares. Stated here rather than only in
# the page so there is one written answer to "how often does this cost me anything",
# and the answer is: this often, and never in money.
WATCH_TICK_MS = 5000
WATCH_THUMB_W = 32
WATCH_THUMB_H = 18
# A cell of that 32x18 grid counts as changed at this much luma difference, and the
# screen counts as changed at this fraction of cells. The fraction is not noise
# reduction, it is the feature: a clock ticking in the corner moves one cell, and a
# stillness clock that a clock could reset would never reach a minute on any real
# desktop. Scrolling, typing, switching window - all of them move far more.
WATCH_CELL_DELTA = 10
WATCH_CHANGED_FRACTION = 0.015


class Watch:
    """The purse. One nudge, then STUCK_COOLDOWN_S, however still the screen stays.

    Deliberately not a session and deliberately not per-tab: it is the spend, and the
    spend is the machine's. Two tabs watching two monitors get one nudge between them,
    which is the correct answer to "how many times may this cost me at once".
    """

    def __init__(self):
        self._lock = threading.RLock()
        self.last_nudge = 0.0
        self.nudges = 0        # process lifetime, like the eyes' - a delta, not a total
        self.refused = 0       # guard hits: every one of these is a call not made

    def left(self, now=None):
        now = time.monotonic() if now is None else now
        if not self.last_nudge:
            return 0.0
        return max(0.0, STUCK_COOLDOWN_S - (now - self.last_nudge))

    def may_nudge(self, now=None):
        return self.left(now) <= 0

    def spend(self, now=None):
        now = time.monotonic() if now is None else now
        with self._lock:
            self.last_nudge = now
            self.nudges += 1

    def refuse(self):
        with self._lock:
            self.refused += 1

    def tuning(self):
        """The numbers the PAGE has to apply, handed back with every reply so the two
        halves cannot drift apart - exactly as focus.EYES.tuning() does for the eyes."""
        return {"stillS": int(STUCK_STILL_S), "cooldownS": int(STUCK_COOLDOWN_S),
                "tickMs": int(WATCH_TICK_MS),
                "thumbW": int(WATCH_THUMB_W), "thumbH": int(WATCH_THUMB_H),
                "cellDelta": int(WATCH_CELL_DELTA),
                "changedFraction": float(WATCH_CHANGED_FRACTION)}

    def state(self, now=None):
        now = time.monotonic() if now is None else now
        return {"cooldownLeftS": int(round(self.left(now))),
                "mayNudge": bool(self.may_nudge(now)),
                "nudges": int(self.nudges), "refused": int(self.refused),
                # The eyes' relief valve, read from the organ that owns it. "No Jarvis,
                # I need to do something important" silences EVERY nudge, and a screen
                # nudge that ignored it would make that promise a lie.
                "hushed": bool(focus.EYES.hushed(now)),
                "hushLeftS": int(focus.EYES.hush_left(now))}


WATCH = Watch()

STOPWORDS = set("""
a about above after again against all am an and any are aren as at be because been
before being below between both but by can cannot could couldn did didn do does
doesn doing don down during each few for from further had hadn has hasn have haven
having he her here hers herself him himself his how i if in into is isn it its
itself just let me more most mustn my myself no nor not of off on once only or
other ought our ours ourselves out over own same shan she should shouldn so some
such than that the their theirs them themselves then there these they this those
through to too under until up very was wasn we were weren what when where which
while who whom why with won would wouldn you your yours yourself yourselves
tell show give know think need want much many any anything something whats
""".split())

TOKEN_RE = re.compile(r"[a-z0-9']+")

# --------------------------------------------------------- small talk detection
#
# Greetings and pleasantries, matched only at the START of the message and then
# peeled off. If something substantial is left, it is still a real question:
# "Thanks! Now what about pricing?" must not be mistaken for chatter.
PLEASANTRY_RE = re.compile(r"""^(?:
    # "there" only ever peels as part of the greeting it followed. _peel's own docstring
    # promises that "hey there, thanks, so..." comes away to nothing, and it did not:
    # "there" stopped the loop dead, "thanks" is a content word to the tokeniser, and so
    # a message that was pure pleasantries counted as a substantial question - which,
    # now that an out-of-scope question knocks on the web, would have sent a greeting to
    # a search engine. Peeled here rather than in FILLER_RE so that a bare "there is a
    # note about pricing" keeps its first word.
      (?: hi | hello+ | hey+ | yo | hiya | howdy | greetings | heya ) (?: \s+ there )?
    | good \s+ (?: morning | afternoon | evening | day )
    | good \s* night | morning | afternoon | evening
    | thanks (?:\s+ (?:a\s+lot|so\s+much|again))? | thank\s+you | ty | ta | cheers
    | much\s+appreciated | appreciate\s+it | nice\s+one
    | ok | okay | kk | k | cool | nice | great | lovely | awesome | brilliant
    | perfect | superb | sweet | excellent | amazing | wonderful
    | please | sorry | oops | oh\s+dear | right | alright | well
    | bye | goodbye | see\s+you (?:\s+later)? | later | cya | ciao | night
    | lol | lmao | ha(?:ha)+ | he(?:he)+ | hmm+ | ah+ | oh+ | yay | woo+
    | how\s+are\s+you (?:\s+doing)? | how (?:'s|s|\s+is)\s+it\s+going
    | how (?:'s|s|\s+is)\s+life | what (?:'s|s)\s+up | sup | wagwan
    | you\s+there | are\s+you\s+there | anyone\s+there
    # mate, buddy, pal, friend and dude used to sit here, peeled only at the front.
    # They are ADDRESSES, so they moved to VOCATIVES below, where the start, the end and
    # the far side of a comma all count.
  )\b[\s,.!?;:'"-]*""", re.IGNORECASE | re.VERBOSE)

# Filler that can trail a greeting without making it a question: "how are you
# doing today" must peel down to nothing, while "how are you pricing the beans"
# must keep "pricing the beans" and count as a real question.
FILLER_RE = re.compile(r"""^(?:
      today | now | then | so | anyway | again | still | just | yet
    | this \s+ (?: morning | afternoon | evening ) | right \s+ now
  )\b[\s,.!?;:'"-]*""", re.IGNORECASE | re.VERBOSE)

# ------------------------------------------------------------- the backchannel
#
# THE ACKNOWLEDGMENTS. "ok", "got it", "thanks Jarvis", "nice one" - a reply TO the
# assistant rather than a question put to it. Linguists call this the backchannel: the
# noises a listener makes to show they are still there. It is the cheapest thing anybody
# says to this machine and, until this list existed, one of the more expensive: "got it"
# scores nothing against the notes, so the out-of-scope trigger sent it to a search
# engine, and a search engine has opinions about the phrase "got it".
#
# A SEPARATE LIST FROM PLEASANTRY_RE, though the two overlap by half a dozen words, and
# the separation is worth the duplication:
#
#   - The two vetoes say different things in the log and mean different things to a
#     reader. "greeting and address, nothing asked" and "an acknowledgment, nothing
#     asked" are both true of "thanks, Jarvis", and the second is the more useful of the
#     two; a salutation and a sign-off are not the same event.
#   - PLEASANTRY_RE is a PEEL, and everything in it has to be safe to strip off the front
#     of a real question. Half of what is here is not: "understood" and "noted" peel to
#     nothing much, but a bare "yes" and "no" are answers, and they are only
#     acknowledgments when nothing is pending - which is a fact about the moment, not
#     about the word, so it cannot live in a regex at all. See backchannel_only().
#
# Matched only at the front and then peeled, exactly like the pleasantries, because "ok,
# what is a closure" is a question with an "ok" in front of it and must cost what the
# question costs. The veto fires on what is LEFT, never on what was found.
ACK_RE = re.compile(r"""^(?:
      ok(?:ay)?(?:\s+then)? | kk+ | k | roger | aye
    | got \s+ (?: it | that | you ) | gotcha | gotchu | copy \s+ that | copied
    | understood | i \s+ understand | understand | makes \s+ sense | fair \s+ enough
    | noted | duly \s+ noted | good \s+ to \s+ know | good \s+ point
    | thanks (?:\s+ (?:a\s+lot|so\s+much|again|for\s+that))? | thank \s+ you | thx | tx
    | ty | ta | cheers | much \s+ appreciated | appreciate \s+ (?: it | that )
    | nice (?:\s+ one)? | cool | great | grand | lovely | perfect | perfecto
    | awesome | amazing | brilliant | splendid | excellent | superb | wonderful
    | fantastic | marvellous | marvelous | sweet | neat | sound | ace
    | good \s+ (?: job | work | one | stuff ) | well \s+ done | nicely \s+ done
    | love \s+ (?: it | that ) | i \s+ like \s+ (?: it | that ) | that'?s \s+ (?: it | right | great | good | perfect | better | lovely )
    | wow | woah | whoa | ah+ | oh+ | hmm+ | mhm+ | mm+ | huh
    | haha+ | hahaha+ | hehe+ | lol | lmao | rofl | heh
    | indeed | quite | right | alright | true | exactly | absolutely | certainly
    | of \s+ course | no \s+ worries | no \s+ problem | np | all \s+ good | fine
    | as \s+ always | as \s+ ever | you \s+ too | same \s+ to \s+ you
  )\b[\s,.!?;:'"-]*""", re.IGNORECASE | re.VERBOSE)

# The bare answers. Acknowledgments ONLY when nothing is pending: while a proposal waits,
# _hands_gate owns these words and they mean yes and no, which is the opposite of
# meaning nothing. Checked separately from ACK_RE so that position is not the only rule -
# "no" in front of a question ("no, what is react?") must peel, and it does, because the
# peel runs on the front of the message like every other peel here.
BARE_ANSWER_RE = re.compile(r"""^(?:
      y | ye | yes | yeah | yep | yup | yea | sure | okay \s+ sure
    | n | no | nope | nah | not \s+ now | maybe \s+ later
  )\b[\s,.!?;:'"-]*""", re.IGNORECASE | re.VERBOSE)

# ------------------------------------------------------------------- the address
#
# THE VOCATIVES. A word that names WHO is being spoken to is not part of WHAT is being
# asked. "hello good morning Jarvis" is two pleasantries and an address, and it must cost
# exactly what "good morning" costs, which is nothing.
#
# The bug this closes was arithmetic rather than manners. PLEASANTRY_RE peeled "hello" and
# "good morning" and left "jarvis" standing - a content word as far as the tokeniser is
# concerned, because it is not in STOPWORDS - so a salutation counted as a substantial
# question. Harmless while
# only a zero score searched; now that an out-of-scope question is allowed to knock on the
# web, it meant a greeting lit the LIVE WEB panel and spent a real search on DuckDuckGo.
#
# THE VETO IS ON THE ADDRESS, NEVER ON THE WORD. "who is JARVIS in the Marvel films?" keeps
# who, Marvel and films and travels exactly as before. That is why POSITION is the whole
# rule, and why only three positions count:
#
#   at the START          "jarvis, what is react"       - always an address
#   after a COMMA         "what is react, jarvis?"      - always an address
#   at the END, no comma  "hello good morning jarvis"   - an address only if everything in
#     front of it peels away to nothing. Without that condition "tell me about tron" loses
#     its subject and a real question about a film quietly becomes small talk - which is
#     the same class of mistake as the one being fixed, pointing the other way.
#
# The assistant's own names come from config.json (`assistant_names`), because they are
# the one part of this list that is yours to change; the rest are fixed.
VOCATIVES = ("sir", "boss", "computer", "assistant", "buddy", "mate",
             "pal", "friend", "dude")

_VOC = {"names": (), "lead": None, "inner": None, "tail": None}


def set_vocatives(names):
    """Recompile the address peel for whatever config.json calls the assistant.

    Called from load_config(), which every request already goes through, so renaming the
    assistant takes effect on the next question rather than on the next restart. Cheap by
    construction: the three patterns are rebuilt only when the name list actually changes.
    """
    if isinstance(names, str):
        names = names.replace(",", " ").split()
    clean = tuple(dict.fromkeys(str(n).strip().lower()
                                for n in (names or ()) if str(n).strip()))
    if clean == _VOC["names"] and _VOC["lead"] is not None:
        return
    alts = "|".join(re.escape(w) for w in dict.fromkeys(clean + VOCATIVES))
    _VOC.update({
        "names": clean,
        # The front of the message, punctuation and all: "Jarvis - what is react".
        "lead": re.compile(r"""^[\s,.!?;:'"-]*(?:%s)\b[\s,.!?;:'"-]*""" % alts,
                           re.IGNORECASE),
        # Set off by a comma and followed by the end or more punctuation. The lookahead
        # is what keeps "React, sir Isaac Newton's favourite" - contrived, but the rule
        # is "an address stands alone between commas", and that is what this says.
        "inner": re.compile(r""",\s*(?:%s)\b(?=\s*(?:[,.!?;:]|$))""" % alts,
                            re.IGNORECASE),
        # The tail, keeping the separator so the caller can tell a comma from a space.
        "tail": re.compile(r"""(?P<sep>[\s,;:-]*)\b(?:%s)\b[\s.!?;:'"-]*$""" % alts,
                           re.IGNORECASE),
    })


set_vocatives(DEFAULT_CONFIG.get("assistant_names"))


# Chatter intents, matched anywhere: these are about the assistant, not the notes.
CHATTER_RE = re.compile(r"""(?:
      tell\s+me\s+a\s+joke | another\s+joke | make\s+me\s+laugh | say\s+something\s+funny
    | be\s+funny | knock\s+knock | tell\s+me\s+a\s+story | sing (?:\s+me | \s+a\s+song)?
    | who\s+are\s+you | what\s+are\s+you | who\s+made\s+you | what (?:'s|s|\s+is)\s+your\s+name
    | what\s+can\s+you\s+do | how\s+do\s+you\s+work | are\s+you\s+(?:a\s+)?
      (?: robot | human | real | ai | bot | alive | conscious | sentient | chatgpt )
    | do\s+you\s+(?: like | love | dream | sleep | eat | feel | think | have\s+feelings )
    | how\s+(?:are|do)\s+you\s+feel | are\s+you\s+ok
    # The weather used to live here, and it has moved to REALWORLD_RE below: the
    # machine can actually find out now, so treating it as chatter would be a
    # deliberate refusal to look. The clock stays - the time is a local fact, and no
    # search engine knows which chair you are sitting in.
    | what\s+time\s+is\s+it
    | what (?:'s|s|\s+is)\s+(?:the\s+)?(?:date|day)\s+today
    | i\s+love\s+you | good\s+bot | bad\s+bot | you (?:'re|re|\s+are)\s+(?:great|amazing|useless|rubbish)
  )""", re.IGNORECASE | re.VERBOSE)


# --------------------------------------------------------- the live web triggers
#
# THE FORCE TRIGGER. "Jarvis, look this up" and "search the web for ..." skip the
# local check entirely: an explicit instruction outranks any score. Written to survive
# the voice path, which arrives as one unpunctuated run - "jarvis look this up what is
# the population of tokyo" - so the trigger is matched anywhere and then PEELED OFF,
# leaving the query. The alternatives are ordered longest-first: `jarvis look this up`
# must win over the bare `look this up` it contains, or the peel would leave "jarvis".
FORCE_WEB_RE = re.compile(r"""
    (?:^|\b)(?:
        (?: hey \s+ | ok(?:ay)? \s+ )? (?: galaxy | jarvis | tron ) \b [\s,.:;!-]*
          (?: please \s+ )? (?: can \s+ you \s+ )? (?: go \s+ and \s+ )?
          (?: look \s+ (?: this | that | it ) \s+ up
            | look \s+ up
            | search \s+ (?: the \s+ )? (?: web | internet | online )
            | search \s+ for )
      | look \s+ (?: this | that | it ) \s+ up
        (?: \s+ (?: on \s+ the \s+ )? (?: web | internet | online ) )?
      | (?: search | check | ask ) \s+ (?: the \s+ )? (?: web | internet | online )
        (?: \s+ (?: for | about | on ) )?
      | web \s+ search \s+ (?: for \s+ )?
      | google \s+ (?: it | this | that ) \b
    )[\s,.:;!?-]*""", re.IGNORECASE | re.VERBOSE)

# THE REAL-WORLD CLASSES. Questions whose answer changes without anybody editing a
# note: weather, news, results, prices, "current" anything. These go to the web even
# when a note happens to share a word with them, because a note that mentions Tokyo
# does not know today's figure and a confident wrong number is the worst outcome here.
#
# Kept deliberately narrow. Every phrase below is one somebody would have to go and
# look up; nothing here matches a question a private collection could answer, because
# each false positive silently swaps the employer's own writing for a stranger's blog.
REALWORLD_RE = re.compile(r"""(?:
      \b (?: what | how ) (?: '?s | \s+ is )? \s+ (?: the \s+ )? weather \b
    | \b weather \s+ (?: in | at | for | today | tomorrow | this ) \b
    | \b (?: the \s+ )? forecast \s+ (?: for | in | today | tomorrow ) \b
    | \b (?: latest | breaking | today'?s? | recent ) \s+ news \b
    | \b news \s+ (?: on | about | from | for ) \b | \b headlines \b
    | \b who \s+ (?: won | win | is \s+ winning | came \s+ first ) \b
    | \b (?: final | latest | current ) \s+ score \b | \b score \s+ of \s+ the \b
    | \b current \s+ (?: price | value | rate | cost | population | score | weather
                       | temperature | champion | president | prime \s+ minister
                       | ceo | version | status | exchange ) \b
    | \b (?: price | cost | value ) \s+ of \s+ (?: a \s+ | an \s+ | the \s+ )?
      (?: bitcoin | btc | ethereum | eth | gold | silver | oil | brent
        | \w+ \s+ (?: stock | share | shares ) ) \b
    | \b stock \s+ price \b | \b share \s+ price \b | \b exchange \s+ rate \b
    | \b how \s+ much \s+ is \s+ (?: a \s+ | one \s+ )? (?: bitcoin | btc | ethereum
        | eth | gold | oil | the \s+ dollar | the \s+ pound | the \s+ euro ) \b
    | \b who \s+ is \s+ the \s+ (?: current | new | present ) \b
    | \b (?: right \s+ now | at \s+ the \s+ moment ) \s*[?.!]?\s*$
  )""", re.IGNORECASE | re.VERBOSE)


# QUESTIONS ABOUT THIS MACHINE, which no search engine can answer. They score nothing
# against the notes - "how do I move the lock?" matches no note - so without this guard
# the thin-score trigger would send them to DuckDuckGo, which would cheerfully return
# three articles about focus apps and none about THIS one. Worse, it would swallow the
# brain-swap tag: "you are being slow, fetch something sharper" is an instruction, and
# an instruction answered with search results is an instruction ignored. Checked AFTER
# the force trigger, because "look this up" is explicit and outranks every heuristic.
SELF_RE = re.compile(r"""(?:
      \b (?: focus \s+ (?: session | timer | mode ) | countdown | report \s+ card
           | lock \s+ (?: on | onto | this | that | my | it ) | streak | ledger ) \b
    | \b (?: the | my | this ) \s+ lock \b
    | \b (?: my | the | these | those ) \s+ (?: notes? | galaxy | graph | collection
                                             | nodes? | clusters? ) \b
    | \b (?: this | the ) \s+ (?: app | page | viewer | assistant | program | server
                                | tab | galaxy ) \b
    | \b (?: your | you | you'?re ) \s+ (?: brain | model | memory | prompt | persona
                                          | voice | eyes | name | maker | job ) \b
    | \b (?: the \s+ )? (?: camera | webcam | microphone | mic ) \b
    | \b (?: brain | model ) \s+ (?: swap | change ) \b | \b swap \s+ (?: your | the ) \b
    | \b (?: sharper | faster | cleverer | different ) \s+ (?: brain | model ) \b
    | \b can \s+ you \s+ (?: see | hear | watch | look ) \b
    | \b (?: what | which ) \s+ (?: model | brain ) \b
    | \b how \s+ do \s+ (?: you \s+ work | i \s+ use \s+ you ) \b
  )""", re.IGNORECASE | re.VERBOSE)


# A QUESTION ABOUT THIS CONVERSATION, which is SELF_RE's argument applied to the session: the
# web has never met this machine, and it has never met this conversation either.
#
# HOW IT WAS FOUND, because it says something about how well the thinness gate is hidden. PART 0's
# eviction probe asks "what did I ask you about first today". It passed for weeks. Then PART 8
# quarantined the demonstration corpus, the collection went from thirty-three notes to his three,
# and the same question came back "According to current web sources...". Nothing about the router
# had changed. With thirty-three notes the question scraped a weak retrieval hit and was answered
# from the prompt - which holds the summary, and therefore holds the answer. With three notes it
# scores nothing, and scoring nothing is the exact condition "thin" exists for, so the gate opened
# and a search engine was asked what the employer had said earlier in the room. It answered
# confidently. A test of "what did I say?" was passing on retrieval noise from notes that had
# nothing to do with the question.
#
# THE ANSWER IS IN THE PROMPT, ALWAYS - that is what older_block() and the recent turns ARE. So
# this is not a lookup that fails, it is a lookup that CANNOT be right, and a veto above the score
# is the only place that fact can be stated: below the score the question has already been called
# thin, and it is not thin. It is fully answerable from the one source the web cannot see.
#
# DELIBERATELY BROAD, because the cost is asymmetric and worth naming. A false positive here means
# a question that might have wanted the web is answered from the conversation instead - the
# sentences this matches ("what did we discuss", "what was my first question") are ones no search
# engine could ever help with. A false negative means the machine goes to a stranger to be told
# what its employer said to it. "what did we talk about yesterday" matching is not a bug for the
# same reason: it is turned back to the notes, where the minutes of yesterday actually live.
ABOUT_SESSION_RE = re.compile(r"""(?:
      \b what \s+ (?: did | have ) \s+ (?: i | we ) \s+ (?: just \s+ )?
        (?: ask | asked | say | said | tell | told | talk | talked
          | discuss | discussed | cover | covered | mention | mentioned ) \b
    | \b what \s+ (?: was | were ) \s+ (?: my | our | the ) \s+
        (?: first | last | previous | earlier | original ) \b
    | \b (?: my | the | your ) \s+ (?: first | last | previous ) \s+
        (?: question | answer | words? ) \b
    | \b (?: this | our ) \s+ conversation \b
    | \b earlier \s+ (?: in \s+ (?: this | our ) \s+ (?: conversation | chat | session )
                       | today | on ) \b
    | \b how \s+ many \s+ (?: questions | things ) \s+ have \s+ i \b
    | \b (?: do | can ) \s+ you \s+ (?: still \s+ )? remember \s+ what \s+ i \b
  )""", re.IGNORECASE | re.VERBOSE)


# ------------------------------------------------------------------- the third door
#
# TASKS ARE NOT RESEARCH. "Draft an email to the landlord", "translate this into French",
# "summarise that paragraph", "plan my Tuesday" - the employer is not asking what is true,
# they are asking for a piece of work. Every one of them scores nothing against the notes,
# which is precisely the condition the thin-score trigger reads as "the collection cannot
# answer this, try the web" - so before this list existed, asking for a letter bought a
# search for the phrase "draft a letter" and three strangers' opinions about letters.
#
# MATCHED ONLY AT THE OPENING, after the pleasantries, the acknowledgments and the address
# have come away, because the verb is the whole signal: "draft a note about pricing" is an
# instruction, while "what do you make of my pricing draft" is a question that happens to
# contain the word. A polite run-up is allowed in front of it ("could you please draft..."),
# since that is how anybody actually phrases an order they are embarrassed to give.
TASK_RE = re.compile(r"""^(?:
      (?: please | kindly | now | just | quickly | go \s+ ahead \s+ and
        | (?: could | can | will | would ) \s+ you (?: \s+ please )?
        | i \s+ (?: need | want | would \s+ like ) \s+ (?: you \s+ to | a | an | some )?
        | let'?s | lets | help \s+ me | give \s+ me )
      [\s,.:;-]* ){0,3}
    (?:
      draft | write \s+ up | write | compose | pen | type \s+ (?: out | up )
    | send | e-?mail | mail (?: \s+ to )?
    | remind | schedule | re-?schedule | book | pencil \s+ in
    | add \b [^.]{0,30} \b (?: calendar | diary | schedule | list )
    | put \b [^.]{0,30} \b (?: calendar | diary )
    | translate | transcribe
    | summari[sz]e | summari[sz]ation | sum \s+ up | tl;?dr
    | rewrite | re-?word | rephrase | reformat | proofread | polish | tidy \s+ up
    | shorten | lengthen | expand \s+ (?: this | that | on )
    | calculate | compute | work \s+ out | add \s+ up | convert
    | plan | outline | draw \s+ up | sketch \s+ out | brainstorm
    | make \s+ me \s+ (?: a | an | some ) | put \s+ together
    | prepare | generate | invent | suggest \s+ (?: me \s+ )? (?: a | an | some )
    # THE SPOKEN DIAL. "switch your voice to Alan" is an instruction about this machine,
    # and the hands are offered it one branch above - but if the brain answers that turn
    # in prose instead of a tag, the message must still not be carried to a search
    # engine, which would come back with three strangers' opinions about voice acting.
    # Every one of these five verbs is paired with the word "voice" on purpose: "change
    # the subject" and "cast a wider net" are not requests to be recast.
    | (?: switch | change | swap | cast | sound \s+ like | speak \s+ with )
      \b [^.]{0,40} \b voice \b
    )\b""", re.IGNORECASE | re.VERBOSE)

# THE PII SHIELD. An email address, a telephone number, a street address: these are the
# employer's private business and the business of whoever they belong to, and the one
# thing that must never happen to them is being typed into a search engine - which logs
# it, keeps it, and is under no obligation to forget it. Private BY DEFAULT, whatever the
# message seems to want, which is why this outranks even the force trigger: "Jarvis, look
# up sam@example.com" is an instruction the butler declines rather than obeys.
#
# Deliberately blunt about what counts. A false positive here costs one search that was
# not run and one sentence saying so; a false negative posts somebody's phone number to a
# third party for ever. Those are not the same mistake and this pattern is not balanced
# between them. Bare five- and six-digit runs are left out all the same: they are far more
# often a sum or a year than a postcode, and "private" must not come to mean "arithmetic".
PRIVATE_RE = re.compile(r"""(?:
      [\w.+-]{1,64} @ [\w-]{1,255} \. [A-Za-z]{2,24} \b
    | \+ \d [\d\s().-]{7,} \d
    # No \b in front of the bracket: there is no word boundary before "(" at the start
    # of a message, and "(415) 555-2671" is exactly how somebody writes their own number.
    | \(\d{3}\) \s* \d{3} [\s.-]? \d{4} \b
    | \b \d{3} [\s.-] \d{3} [\s.-] \d{4} \b
    | \b \d{4} [\s.-] \d{3} [\s.-] \d{3,4} \b
    | \b \d{5} [\s.-] \d{5,6} \b
    | \b \d{10,15} \b
    | \b (?: phone | mobile | cell | tel | telephone | whatsapp | fax ) \s*
      (?: number | no\.? | num )? \s* (?: is | :|=)? \s* \+? [\d][\d\s().-]{6,}
    | \b \d{1,5} [A-Za-z]? (?: \s+ [\w'.-]+ ){1,4} \s+
      (?: street | st | road | rd | avenue | ave | lane | ln | drive | dr
        | boulevard | blvd | way | court | ct | close | crescent | cres
        | place | pl | terrace | square | sq | gardens | grove | nagar | marg
        | colony | sector | block | apartments? | apt | flat | suite | unit ) \b
    | \b (?: post \s* code | postcode | zip (?: \s* code )? | pin \s* code | eircode )
      \s* (?: is | :|=)? \s* [A-Za-z0-9][A-Za-z0-9\s-]{2,9} \b
    | \b [A-Z]{1,2} \d [A-Z\d]? \s* \d [A-Z]{2} \b
    | \b \d{5} - \d{4} \b
  )""", re.IGNORECASE | re.VERBOSE)


def _bare(question):
    """Lowercase, punctuation-free, single-spaced. The form both classifiers read."""
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s']", " ", str(question or "").lower())).strip()


def _peel(bare):
    """Greetings, thanks and trailing filler off the front, until nothing more comes
    away. "hey there, thanks, so..." peels to nothing at all."""
    stripped = bare
    for _ in range(6):
        shorter = PLEASANTRY_RE.sub("", stripped, count=1).strip()
        shorter = FILLER_RE.sub("", shorter, count=1).strip()
        if shorter == stripped:
            break
        stripped = shorter
    return stripped


def _strip_address(text, depth=0):
    """The vocatives off the front, the back and the far side of a comma. Or the lot.

    Runs on the RAW message, before _bare() flattens the punctuation, because a comma is
    the only thing that tells "what is react, jarvis?" from "who is jarvis in the films?".

    The recursion is the trailing rule doing its one job: "hello jarvis buddy" has to strip
    "buddy" on the strength of "hello jarvis" itself peeling to nothing, and that is the
    same question one word shorter. It shrinks every time, and stops at depth 3.
    """
    out = str(text or "")
    for _ in range(6):
        before = out.strip()
        out = _VOC["lead"].sub("", out, count=1)
        out = _VOC["inner"].sub("", out, count=1)
        match = _VOC["tail"].search(out)
        if match:
            head = out[:match.start()]
            if "," in match.group("sep") or (
                    depth < 3 and not _peel(_bare(_strip_address(head, depth + 1)))):
                out = head
        out = out.strip()
        if out == before:
            break
    return out


def address_only(question):
    """Nothing but greetings and an address: the message asked for nothing.

    The positive half of "nothing left, nothing spent" - answer_question() logs this so
    that a run can show a salutation costing a search NOTHING, rather than showing the
    absence of a line and asking to be believed.
    """
    if not str(question or "").strip():
        return False
    return not _peel(_bare(_strip_address(question)))


def _peel_all(bare, pending=False):
    """(what is left, whether an acknowledgment was among what came away).

    Acknowledgments off the front, alternating with the pleasantry peel, until nothing
    more comes away: "ok great, thanks Jarvis" peels to nothing at all.

    THE SECOND RETURN VALUE IS WHAT KEEPS THE TWO VETOES APART, and it was a bug before it
    was a design. "hello good morning Jarvis" also peels to nothing - it always has, that
    is what address_only() is - so a backchannel test that asked only "did it peel to
    nothing?" claimed every greeting in the language and answered "my pleasure, sir" to
    "good morning". A greeting and a sign-off are different events and get different
    replies; the difference is whether an ACKNOWLEDGMENT was actually said.

    `pending` is the one fact a regex cannot hold: while a proposal is awaiting a word,
    "yes" and "no" are that word, and peeling them would turn consent into small talk.
    So the bare answers are only peeled when nothing is waiting - and _hands_gate has
    already run and taken the message by then, so in practice this is belt and braces.
    """
    stripped, saw = bare, False
    for _ in range(8):
        shorter = ACK_RE.sub("", stripped, count=1).strip()
        saw = saw or shorter != stripped
        after_ack = shorter
        shorter = PLEASANTRY_RE.sub("", shorter, count=1).strip()
        shorter = FILLER_RE.sub("", shorter, count=1).strip()
        if not pending:
            plainer = BARE_ANSWER_RE.sub("", shorter, count=1).strip()
            saw = saw or plainer != shorter
            shorter = plainer
        if shorter == stripped and after_ack == stripped:
            break
        stripped = shorter
    return stripped, saw


def _peel_acks(bare, pending=False):
    """What is left after the acknowledgments and the pleasantries, and nothing else."""
    return _peel_all(bare, pending)[0]


def backchannel_only(question, pending=False):
    """Nothing but acknowledgment: they replied to the butler rather than asked him
    anything.

    The negative half is what makes this safe. A LEADING ack peels and does not veto -
    "ok, what is a closure in javascript" comes back False and travels the ordinary road,
    because the veto fires on what is LEFT rather than on what was found. Exactly the
    "nothing left, nothing spent" rule the greeting veto runs on, applied to the other end
    of the conversation.

    The consequence the employer actually feels is in answer_question(): a backchannel
    costs no search and no rewrite, and - because the /chat door skips the memory for it -
    it does not overwrite the last real question either. "What is React?" / "ok got it" /
    "who created it?" has to inherit React through the middle turn, and it does.
    """
    if not str(question or "").strip():
        return False
    left, saw_ack = _peel_all(_bare(_strip_address(question)), pending)
    # Nothing left AND something acknowledged. A pure greeting satisfies the first half and
    # not the second, so it goes on to the greeting it deserves - see _peel_all.
    return saw_ack and not left


def task_intent(question):
    """Is this an order to produce something, rather than a question about anything?

    Read AFTER the peels, so a polite run-up and an acknowledgment in front make no
    difference: "ok, now please draft a note to the landlord" is the same order as "draft
    a note to the landlord". Chooses nothing and performs nothing - answer_question()
    decides between the registry's hands and the assistant's own prose, and this only says
    which of the three doors the message was knocking on.
    """
    said = str(question or "")
    if not said.strip():
        return False
    peeled = _peel_acks(_bare(_strip_address(said)))
    if not peeled:
        return False               # pure acknowledgment; the backchannel owns it
    # RESEARCH STAYS RESEARCH. "Summarise today's news" and "work out the current bitcoin
    # price" open with a task verb and are still questions about the world, so the
    # real-world classes keep their claim on them and the web door stays exactly as it was.
    if REALWORLD_RE.search(_bare(said)) or FORCE_WEB_RE.search(said):
        return False
    return bool(TASK_RE.match(peeled))


# ======================= THE FOUR PROTECTED CLASSES ==========================
#
# FOUR KINDS OF THING HE SAYS THAT MUST NEVER COST A LOOKUP, and they are in an order.
# Each of them is a sentence about THIS MACHINE - the offer awaiting a word, whether the
# ear is open, who he is, who I am, what I can do - and every one of them was, at some
# point, answered by going and looking somewhere: "can you listen to me" spent a real web
# search, and "what's my name" came back kind=notes with six of his own notes lit behind
# an answer that was not in them. That is not a tuning problem. A question about the room
# cannot be answered by anything outside it, so the retrieval is not merely wasteful, it
# is a category error, and the fix is a funnel above the retrieval rather than a threshold
# inside it.
#
# THE ORDER IS THE FEATURE:
#   1 CONFIRMATION   while an offer lives, "yes" is that word and nothing else. Above all.
#   2 META           "are you there" is about the ear, not about the world.
#   3 IDENTITY       who you are, who he is, what you can do - persona and manifest.
#   4 DIRECTIVES     the Third Door and the registry's hands, exactly as built.
# Only when all four miss do the notes and the web get a say, and the web needs one more
# thing besides - see web_intent(): a question about the WORLD.
#
# EVERY ONE OF THEM IS ANSWERED FROM STATE, NOT FROM A MODEL. Deterministic, so the same
# sentence said twice gets the same answer, so the spoken fixture and the typed fixture can
# be compared at all, and so a canary hand dropped into the registry is either named or not
# named rather than probably mentioned. The persona block and the manifest are the source;
# they are also injected into every brain call, so a free-form answer that wanders near
# these subjects is in the same character as the fixed ones.

PROTECTED_CLASSES = ("confirmation", "meta", "identity", "directive")

# AND A FIFTH THING THAT COSTS NO LOOKUP, WHICH IS NOT ONE OF THE FOUR. The clock is answered
# from a table on this disk, so it belongs above the retrieval for exactly the reason the four
# above it do - but it is not a sentence about this machine, it is arithmetic about the world,
# and the tuple above is the mandate's own list and is left as the mandate wrote it. So: the
# four are unaltered and still in their order, and `clock` is tried only after all four have
# declined. See the last branch of protected_answer(). A harness that wants "is this one of the
# four" reads PROTECTED_CLASSES; one that wants "did this cost a lookup" reads `lookups`.
#
# AND A SIXTH, §29's, ADDED FOR THE SAME REASON AND STANDING IN THE SAME PLACE. "go full screen"
# is an INSTRUCTION and the deck can obey it from state; before this route existed all five of
# its phrasings reached the notes door and paid a retrieval each to explain that the assistant
# had no such lever. It sits here rather than in the tuple above for exactly the clock's reason:
# the four are the mandate's own list. It is tried BELOW all four and ABOVE the clock - below the
# four because they are fixed, above the clock because worldclock.asked() scans for place names
# and a town called Fulscreen must never stop the deck obeying.
#
# AND A SEVENTH, §30's, ON THE SAME TERMS. "study micro-saas now" is an INSTRUCTION the daemon
# can take from state - it queues a tick and returns - so it costs no retrieval either, and it
# stands in the same place for the same two reasons: below all four because the four are the
# mandate's fixed list, above the clock because a place table is not a reason for the Scholar to
# stop obeying. It is the only member of this tuple that STARTS something rather than answering
# something, which is why it is also the only one behind a Doorman gate: see study_allowed().
#
# AND AN EIGHTH, §35's, ON THE SAME TERMS AS THE SEVENTH. "make a video about micro-saas pricing"
# is an INSTRUCTION the Director takes from state - it queues a render on a daemon thread and
# returns a sentence - so protected_answer() reaches the notes, the archive and the web exactly
# never to answer it, and `lookups` stays 0. The RENDER itself does retrieve, five chunks of it,
# but that happens on the Director's own thread and against the Director's own budget; it is not
# a lookup this turn paid for, and conflating the two would make every long job look like an
# expensive question. It stands below the Scholar and above the clock, and it is the second
# member of this tuple behind a Doorman gate: see director_allowed().
# AND A NINTH, §40's, WHICH IS TWO ROUTES UNDER ONE NAME. "put it on youtube" queues an upload on
# a daemon thread; "make it public" raises a PROPOSAL and returns a question. Neither reads a note,
# an archive page or the web to produce its sentence - the upload's title and tags are read off the
# film's own script.md, which the Director already wrote, and the publish card is built from
# jobs-ledger.json, which this server wrote itself. So `lookups` stays 0 for both, and the one
# retrieval anywhere near this route - keywords() over the narration - is a regex over a local file
# and not a trip to the Scholar. The UPLOAD's bytes are a minute of network, but they are a minute
# on the Broadcaster's thread against the Broadcaster's own budget, exactly as §35 settled for the
# render; a turn is charged for what it looked up to answer, not for what it set going. It stands
# last because it is the newest, and it is the third member of this tuple behind a Doorman gate:
# see broadcast_allowed(), which borrows study_allowed()'s BOSS-only verdict without spending it.
UNPAID_CLASSES = PROTECTED_CLASSES + ("clock", "fullscreen", "study", "direct", "broadcast")


def _addressless(question):
    """The message with every ADDRESS taken out wherever it stands, then the pleasantries
    and the filler peeled off the front. "hey galaxy are you there" -> "are you there".

    THIS FORM IS READ BY THE PROTECTED CLASSES AND BY NOTHING ELSE, which is what makes it
    safe. _strip_address() is careful about position - it has to be, because "who is JARVIS
    in the Marvel films?" is a real question about a word that is also a name, and the notes
    and the web both read the form it produces. Here the only question being asked of the
    text is "is this whole utterance one of a few dozen fixed things about this machine?",
    and a stray name in the middle of one of those ("yes yes do it galaxy") is an address by
    construction. If the answer is no, this form is thrown away and the ordinary funnel
    reads the ordinary one.
    """
    alts = "|".join(re.escape(w) for w in dict.fromkeys(_VOC["names"] + VOCATIVES))
    bare = re.sub(r"\b(?:%s)\b" % alts, " ", _bare(question), flags=re.IGNORECASE)
    return _peel(re.sub(r"\s+", " ", bare).strip())


# THE NOISE HE MAKES BEFORE HE STARTS TALKING. Used by the protected classes and by
# nothing else: FILLER_RE and PLEASANTRY_RE are read by _strip_address() and the whole
# funnel below it, and widening them to swallow "umm" would change what counts as a
# substantial question everywhere. Here it only ever decides whether one whole utterance is
# one of a few dozen fixed things about this machine, so it can afford to be deaf to noise.
_LEAD_NOISE_RE = re.compile(r"""^(?:
      u+m+h? | e+r+m* | a+h+ | h+m+ | oh | uh+ | eh
    | hey | hi | yo | hiya | so | well | alright | okay | ok | now | just | anyway
  )\b[\s,]*""", re.IGNORECASE | re.VERBOSE)


def _addressless_forms(question):
    """Every form the message passes through as the pleasantries come off the front, the
    longest first. ("hey are you there", "are you there") - and the empty string never.

    _peel() IS ALLOWED TO BE GREEDY. Its contract, written in its own docstring, is that
    "hey there, thanks, so..." comes away to nothing, and the price of that contract is that
    "are you there" comes away to nothing too: "there" is a greeting's second half to the
    tokeniser, and the tokeniser is right about nine sentences in ten. It is not right about
    this one. _strip_address() depends on that greed - the trailing-vocative rule works by
    asking whether the head peels to nothing - so the greed stays and the rungs are kept
    instead.

    FAILURE MODE THIS CATCHES: "hey galaxy are you there", one of the boss's own sentences,
    written into the mandate by hand. The name came off, the peel ate the rest, class 2 was
    handed the empty string and had nothing to match, and the sentence went down the funnel
    to the notes and the web - a search engine asked whether anyone was listening. Now
    "are you there" is one of the rungs, and one rung matching is a match.
    """
    forms, seen = [], set()

    def rung(text):
        text = re.sub(r"\s+", " ", str(text or "")).strip()
        if text and text not in seen:
            seen.add(text)
            forms.append(text)
        return text

    # Rung nought is the message with its NAMES STILL IN IT, because one of the boss's own
    # identity questions is "whose assistant are you" - and "assistant" is a vocative, so
    # the stripper below takes it out and leaves "whose are you", which is not English and
    # matches nothing. A fixed phrase that happens to contain an address word is still a
    # fixed phrase, and every pattern read here is anchored to the whole utterance, so
    # keeping this rung cannot widen anything: "who is jarvis in the Marvel films" matches
    # no class with the name in and none with it out.
    alts = "|".join(re.escape(w) for w in dict.fromkeys(_VOC["names"] + VOCATIVES))
    step = rung(_bare(question))
    step = rung(re.sub(r"\b(?:%s)\b" % alts, " ", step, flags=re.IGNORECASE))
    # ONE SUBSTITUTION PER RUNG. _peel() runs a pleasantry and a filler in the same pass,
    # which can step over the form that was wanted: "umm so are you still there" would go
    # from noise straight past "are you still there" in a single stride.
    for _ in range(10):
        for pattern in (PLEASANTRY_RE, FILLER_RE, _LEAD_NOISE_RE):
            shorter = re.sub(r"\s+", " ", pattern.sub("", step, count=1)).strip()
            if shorter != step:
                break
        if shorter == step:
            break
        step = rung(shorter)
    return tuple(forms)


def confirmation_in(question):
    """"yes", "no", or "" - the word of consent inside a message, vocatives and all.

    hands.is_confirmation() insists on the WHOLE message being the answer, and it is right
    to: "yes, and what is the population of Tokyo" is a new subject. But the boss says
    "yes yes do it galaxy", and the whole of that message IS the answer once his name comes
    off. So the raw form is tried first - it is the strict one - and then the addressless
    form, which can only ever have lost pleasantries and names.

    FAILURE MODE THIS CATCHES: the name at the end made "yes yes do it galaxy" a new
    subject, which withdrew the offer he was accepting and then searched the notes for the
    words "yes yes do it". Twice wrong from one missing peel.
    """
    for form in (str(question or ""), _addressless(question)):
        if not form.strip():
            continue
        if hands.is_confirmation(form):
            return "yes"
        if hands.is_refusal(form):
            return "no"
    return ""


# CLASS 2, META-CONVERSATIONAL. He is not asking about the world, he is asking whether
# anyone is on the other end. Anchored whole-utterance on the addressless form, because
# "can you listen to me" is this class and "can you listen to this recording and tell me
# what key it is in" is not.
META_RE = re.compile(r"""^(?:
      (?:can|could|will|would|are)\s+you\s+(?:please\s+)?
        (?:listen|listening|hear|hearing)(?:\s+(?:to\s+)?me)?
    | do\s+you\s+(?:hear|understand)\s+me
    | (?:are|you)\s+(?:you\s+)?(?:there|awake|around|alive|with\s+me|listening)
    | is\s+(?:anyone|anybody|someone)\s+(?:there|listening)
    | listen(?:\s+to\s+me)? | pay\s+attention | talk\s+to\s+me | speak\s+to\s+me
    | (?:are\s+you\s+)?still\s+(?:there|listening|with\s+me)
  )$""", re.IGNORECASE | re.VERBOSE)

# CLASS 3, IDENTITY AND CAPABILITIES, in three questions: who are you, who am I, what can
# you do. Every one of them is answered out of the persona block and the manifest.
IDENTITY_SELF_RE = re.compile(r"""^(?:
      who(?:\s+exactly)?\s+are\s+you | what\s+are\s+you
    | who\s+are\s+you\s+(?:really|then) | what'?s\s+your\s+name
    | what\s+is\s+your\s+name | who\s+am\s+i\s+talking\s+to
    | whose\s+assistant\s+are\s+you | who\s+do\s+you\s+work\s+for
    | who\s+is\s+your\s+(?:boss|employer|master)
    | (?:please\s+)?introduce\s+yourself | tell\s+me\s+about\s+yourself
  )$""", re.IGNORECASE | re.VERBOSE)
IDENTITY_BOSS_RE = re.compile(r"""^(?:
      who\s+am\s+i | what'?s\s+my\s+name | what\s+is\s+my\s+name
    | do\s+you\s+know\s+(?:me|who\s+i\s+am) | do\s+you\s+remember\s+me
    | what\s+do\s+you\s+call\s+me | say\s+my\s+name
  )$""", re.IGNORECASE | re.VERBOSE)
CAPABILITY_RE = re.compile(r"""^(?:
      what\s+can\s+you\s+do(?:\s+for\s+me)? | what\s+are\s+you(?:r)?\s+capabilit(?:y|ies)
    | what\s+else\s+can\s+you\s+do | what\s+are\s+you\s+able\s+to\s+do
    | help(?:\s+me)? | what\s+do\s+you\s+do
    | (?:what|which)\s+(?:things|tools|hands)\s+(?:can|do)\s+you\s+(?:do|have)
  )$""", re.IGNORECASE | re.VERBOSE)

# CLASS 3, CONTINUED: THE CONNECTION. "How do I connect google", "why is it not connected",
# "is my calendar connected". These are the same KIND of question as "what can you do" - they
# ask about the state of this machine, and the answer is sitting in memory - and until now
# every one of them fell all the way through the funnel to "the notes are thin", which is the
# web gate, which sent the boss's own question about his own laptop to a search engine and
# came back with somebody's help article about connecting Google Calendar to Outlook.
#
# ANSWERED FROM THE LIVE STATE AND FROM NOWHERE ELSE, and the sentence NAMES THE ROW. A
# spoken answer that says "you are not connected" and stops has told him a fact and left him
# hunting for the switch; the Command Panel has a row whose button is the switch and whose
# line is the state, so the answer quotes both. The failure mode that keeps this honest is
# drift: if the row's wording changes and this function's does not, the two voices in the
# house disagree about the same fact. Hence _google_row() below mirrors the panel's own
# six-reading ladder in the same order, and routing_proof asserts the sentence contains the
# row's reading verbatim rather than a paraphrase of it.
_CONNECT_THING = r"""(?:(?:my|the|your)\s+)?(?:
      google(?:\s+(?:account|calendar|mail|inbox))? | g-?mail
    | calendar | (?:e-?)?mail(?:box)? | inbox | account
  )"""
_CONNECT_STATE = r"(?:connected|linked|hooked\s+up|set\s+up|signed\s+in|logged\s+in|authorised|authorized)"
CONNECTION_RE = re.compile(r"""^(?:
      (?:how|what)\s+(?:do|can|should|would|must)\s+(?:i|we)\s+
        (?:get\s+|go\s+about\s+)?(?:re)?connect(?:ing|ed)?\s*(?:to\s+|with\s+)?%(thing)s\b.*
    | (?:how\s+do\s+i\s+)?(?:re)?connect\s+(?:to\s+|with\s+)?%(thing)s\b.*
    | (?:is|are|was)\s+%(thing)s\s+(?:already\s+|still\s+|even\s+)?(?:not\s+)?%(state)s\b.*
    | (?:are|is)\s+you\s+(?:already\s+|still\s+)?(?:not\s+)?%(state)s(?:\s+to\s+%(thing)s)?\b.*
    | (?:do|did|have|has)\s+(?:i|we|you)\s+(?:ever\s+|already\s+)?%(state)s\s+%(thing)s\b.*
    | why\s+(?:is|isn'?t|are|aren'?t|wo\s*n'?t|won'?t|can'?t|cannot)\s+
        %(thing)s\s+(?:not\s+)?(?:%(state)s|connect(?:ing)?)\b.*
    | what'?s?\s+(?:the\s+|my\s+)?%(thing)s\s+(?:connection\s+)?(?:state|status)\b.*
    | what\s+is\s+(?:the\s+|my\s+)?%(thing)s\s+(?:connection\s+)?(?:state|status)\b.*
    | (?:is|are)\s+(?:the\s+|my\s+)?%(thing)s\s+(?:connection\s+)?(?:up|live|open|working|ready|there)\b.*
  )$""" % {"thing": _CONNECT_THING, "state": _CONNECT_STATE}, re.IGNORECASE | re.VERBOSE)
# THE SAME QUESTION WITH THE NOUN POINTED AT RATHER THAN SAID, which is how it is actually
# asked out loud - "why is it not connected" arrives a beat after "is my calendar connected"
# and means the same thing. It is a SEPARATE pattern for one reason: "it" is also how a
# standing offer is referred to, and _hands_gate consults this funnel before it consults
# about_the_proposal(). So this rung is suppressed while an offer is on the card, where "why
# is it not connected" is far more likely to be about the invitation he is looking at than
# about the grant that composed it. With nothing pending there is no other antecedent.
CONNECTION_DEICTIC_RE = re.compile(r"""^(?:
      why\s+(?:is|isn'?t|was|wasn'?t|wo\s*n'?t|won'?t|can'?t|cannot|does\s*n'?t)\s+
        (?:it|that|this)\s+(?:not\s+)?(?:%(state)s|connect(?:ing)?)\b.*
    | (?:is|was)\s+(?:it|that|this)\s+(?:even\s+|still\s+|already\s+)?(?:not\s+)?%(state)s\??
    | are\s+we\s+(?:even\s+|still\s+|already\s+)?(?:not\s+)?%(state)s\??
  )$""" % {"state": _CONNECT_STATE}, re.IGNORECASE | re.VERBOSE)


# ============================ §29: THE ROOM, ASKED FOR ================================
#
# A SIXTH ROUTE, CARRIED THE WAY THE CLOCK'S IS. PROTECTED_CLASSES still names four and is not
# touched; this adds a route and two payload fields, exactly as `clock` added a route and three.
# It belongs above the retrieval for the same reason the four above it do, and it is the
# clearest case of the lot: "go full screen" is an instruction to this window. There is nothing
# in the notes about it and nothing on the web about it, and before this branch existed the
# sentence fell through the whole funnel to the web gate and came back with somebody's article
# about F11 in Microsoft Edge.
#
# WHY "full screen" IS SPELT THREE WAYS. The boss says it; a recogniser writes it down. On-device
# Web Speech returns "full screen", the cloud recogniser returns "fullscreen", and a keyboard
# produces "full-screen" about a third of the time. One hyphen between the two halves is not a
# different intent, and a page that obeys two of the three spellings is a page that works
# intermittently for no reason the boss can see.
_FULL = r"full[\s-]*screen(?:\s+mode)?"

# THE DIRECTION IS PART OF THE MATCH, and this is the one design decision in the section worth
# arguing about. The mandate says each variant "calls the same toggle Ctrl+A calls", and a toggle
# is a blind flip - but "exit full screen" said while already windowed would then PUT IT ON, and
# "go full screen" said twice would take it away again. Both are the machine doing the opposite
# of what it was plainly told. So the sentence carries what was ASKED FOR - on, off - and there
# is still exactly ONE path into the Fullscreen API: see fullAsked() in viewer/index.html, which
# calls fullToggle() and only when the room is not already the way it was asked to be. A second
# requestFullscreen() call site is what this avoids, and that is what the mandate's sentence is
# protecting.
FULLSCREEN_ON_RE = re.compile(r"""^(?:
      (?:switch|change|flip|put\s+(?:it|this)|take\s+(?:it|this)|set\s+(?:it|this))
        \s+(?:to|in\s*to|on\s*to)\s+(?:the\s+)?%(full)s
    | (?:go|goto|go\s+to|going)\s+(?:to\s+)?(?:the\s+)?%(full)s
    | make\s+(?:it|this|that|the\s+(?:deck|screen|window|galaxy))\s+%(full)s
    | fill\s+(?:the|my|up\s+the)\s+(?:screen|display|monitor|room|glass|whole\s+screen)
    | %(full)s(?:\s+please|\s+it|\s+now)?
    | (?:turn|switch)\s+on\s+(?:the\s+)?%(full)s
    | (?:enter|start|begin|open)\s+(?:the\s+)?%(full)s
    | maximi[sz]e\s+(?:the\s+)?(?:deck|screen|window|galaxy|view)
  )$""" % {"full": _FULL}, re.IGNORECASE | re.VERBOSE)

FULLSCREEN_OFF_RE = re.compile(r"""^(?:
      (?:exit|leave|quit|stop|end|close|cancel)\s+(?:the\s+)?%(full)s
    | (?:get|come|back)\s+out\s+of\s+(?:the\s+)?%(full)s
    | drop\s+out\s+of\s+(?:the\s+)?%(full)s
    | (?:turn|switch)\s+off\s+(?:the\s+)?%(full)s
    | (?:go\s+back|back)\s+to\s+(?:the\s+)?(?:window|windowed(?:\s+mode)?|normal(?:\s+size)?)
    | (?:un)?maximi[sz]e\s+(?:the\s+)?(?:deck|screen|window|galaxy|view)
    | give\s+me\s+(?:the\s+)?window\s+back
    | (?:make|put)\s+(?:it|this)\s+(?:small(?:er)?|normal|windowed)\s*(?:again)?
  )$""" % {"full": _FULL}, re.IGNORECASE | re.VERBOSE)

# WHAT MUST NOT MATCH, and it is asserted rather than hoped for - routing_proof carries it as a
# control and preflight's funnel check carries it too. "What is full screen mode?" is an ORDINARY
# QUESTION that happens to contain the words, and it is owed a real answer with its honest chips.
# The anchors are what make this true: every alternative above is ^...$ on the whole addressless
# utterance, so a sentence with a question stem in front of it cannot reach any of them.
# FAILURE MODE IF THE ANCHORS ARE EVER LOOSENED to bare `search` semantics: every sentence the
# boss says about fullscreen silently becomes a command, including the ones asking what it is.


def fullscreen_asked(question):
    """"on", "off", or "" for a message that is not about the room at all."""
    for form in _addressless_forms(question):
        # OFF IS TESTED FIRST, because "exit full screen" contains "full screen" and one
        # careless alternative in the ON list that matched a trailing phrase rather than the
        # whole utterance would turn every exit into an entry. Ordering costs nothing and
        # removes a whole class of mistake from the list above.
        if FULLSCREEN_OFF_RE.match(form):
            return "off"
        if FULLSCREEN_ON_RE.match(form):
            return "on"
    return ""


# THE LINE THE MANDATE WROTE, and it is stored once so that the page, the server and the proof
# cannot drift apart on it. It carries an address form; a guest never receives one, because
# _strip_address() takes the vocative off every sentence leaving this server for a voice it
# could not name - so the boss would never see this line at all, and what actually reaches the
# guest is "Only the boss fills the room." That is the existing peel doing its job and it is
# not special-cased here. Measured, not assumed: routing_proof asserts the string the guest
# receives rather than the string written on this line.
# AND THE FORM IS A TEMPLATE RATHER THAN A WORD, because the paragraph above is only true when
# the word in the sentence is the one the peel is built from. It was not, and a stranger was
# addressed by the boss's name for it; see fullscreen_refusal() for the whole account.
FULLSCREEN_REFUSAL_FORM = "Only the boss fills the room, %s."


_LIVE_CFG = "live"          # the sentinel below, named so the signature reads as a sentence.


def fullscreen_refusal(cfg=_LIVE_CFG):
    """The mandate's line, carrying the address form the peel actually knows how to remove.

    THE BUG THIS FIXES, AND IT WAS A REAL ONE RATHER THAN A FIXTURE'S OPINION. The line used to
    be the constant "Only the boss fills the room, Addi." with the comment above arguing that a
    guest receives it de-addressed because _strip_address() peels the vocative off. That argument
    only holds while the boss's warm form IS "Addi": the peel is built from
    [who["boss_call"]] + _ADDRESS_WORDS (see _strip_address), so it removes the CONFIGURED form
    and nothing else. config.json's persona sets boss_call to something else, so the peel walked
    past the hardcoded "Addi" and the sentence that reached a stranger was "Only the boss fills
    the room, Addi." - a guest being told the room is not theirs while being called by the boss's
    name, which is the exact failure the comment above says this arrangement exists to prevent.
    Caught by routing_proof's `said.indexOf('Addi') < 0`, which was right and was being read as
    a stale fixture.
    SO THE FORM IS INTERPOLATED FROM THE LIVE PERSONA, like every other addressed line in this
    file (`% who["boss_call"]`), and the peel is then guaranteed to recognise it because it is
    the same string the peel builds itself from. The vocative peel is a DO-NOT-ALTER and is not
    touched: this makes the sentence peelable rather than making the peel cleverer.
    Failure mode if boss_call is empty: "%s" would leave a dangling comma, so an unset form falls
    back to "sir" - which the peel also carries in _ADDRESS_WORDS.

    cfg: the sentinel "live" reads config.json, which is what the doorman wants and what the
    outbound peel at the /chat edge already does (`deaddress(payload[key], load_config()[0])`), so
    the two halves of the round trip read ONE persona and cannot drift apart the way the constant
    and the peel did. A dict is used as given - which is the whole reason the parameter exists:
    preflight can compose this sentence for a persona nobody is configured with and prove the name
    arrives from the block rather than from a coincidence between a literal and a default. That
    proof is impossible against a no-argument function, and the absence of it is precisely how the
    bug above survived a green check.
    """
    if cfg is _LIVE_CFG:
        try:
            cfg = load_config()[0]
        except Exception:                                      # noqa: BLE001
            cfg = None
    try:
        call = persona(cfg)["boss_call"]
    except Exception:                                          # noqa: BLE001
        call = ""
    return FULLSCREEN_REFUSAL_FORM % (str(call).strip() or "sir")


def fullscreen_allowed(spoken, seal):
    """(True, "") if this voice may fill the room, else (False, the refusal).

    THE DOORMAN, AT A THIRD DOOR, and reusing his DECISION rather than his code: doorman_refusal()
    spends the speaker slot when it admits somebody, because the gate it guards turns a word into
    an email leaving the house and a number that authorises twice is a number worth stealing.
    Filling the screen sends nothing, writes nothing and is undone by one press of Escape, so
    spending the boss's verdict on it would make his next spoken "yes" need a fresh sentence to
    be measured from - a real cost, paid for a cosmetic action. Hence a separate, narrower gate,
    and hence this docstring, so the next reader does not "simplify" the two into one.

    BOSS OR A NAME, which is the mandate's own phrase and is looser than the Hands gate on
    purpose: an enrolled colleague may fill the screen, and may not send mail. GUEST and
    UNVERIFIED are refused - UNVERIFIED included, because the alternative is a stranger in the
    near band filling the boss's screen, and the cost of being wrong the other way is that the
    boss says it again or presses Ctrl+A, which is in front of him.

    THE KEYBOARD IS ALWAYS THE BOSS'S. A typed message has no `speaker` block at all, so
    `spoken` is False and this returns True - "typing the phrase behaves as speech would for the
    boss", and the Ctrl+A guard is untouched either way.

    WITH NOBODY ENROLLED THE LAW STANDS DOWN SILENTLY, exactly as the Hands doorman does:
    has_hands_voice() is the whole of the switch. Without this clause a house that has never
    taught the machine a voice would have every spoken command refused, because identify()
    answers "GUEST" when the roster is empty - the same seal a real stranger gets, for an
    entirely different reason.

    AND AN EMPTY SEAL ON A SPOKEN TURN IS REFUSED, which is the case that is easiest to write
    by accident and hardest to see: it means the message came through the ear and this process
    could NOT say whose voice it was - a stale turn number, one it never issued, or a page that
    asked nothing. _speaker_turn() fails closed there and so does this, for the same reason,
    which is that "somebody spoke and we do not know who" is not an identification.
    """
    if not spoken:
        return True, ""
    if voiceprint is None:
        return True, ""
    try:
        if not voiceprint.has_hands_voice():
            return True, ""
    except Exception:                                          # noqa: BLE001
        # A store that will not read is not a reason to refuse the boss his own screen. This is
        # the opposite of the Hands gate's choice on the same failure, and deliberately so: there
        # the cost of being wrong is an email nobody authorised, here it is a bigger window.
        return True, ""
    if str(seal or "") and str(seal) not in ("GUEST", "UNVERIFIED"):
        return True, ""
    return False, fullscreen_refusal()


# ---- §30: "STUDY X NOW" ---------------------------------------------------------------------
#
# ANCHORED ON THE WHOLE ADDRESSLESS UTTERANCE, like FULLSCREEN_ON_RE and for the same reason:
# "what did you study today?" and "how should I study for this?" must reach the brain as
# ordinary questions, and the ^...$ anchors are what make that true rather than a hope. The
# topic is the capture group, so "study micro-saas now" arrives with its topic and a bare
# "study something now" arrives without one and takes the rotation's next pick.
#
# THE TWO "ANYTHING" ALTERNATIVES COME FIRST, and the order is load-bearing rather than tidy.
# The capturing alternative is greedy enough to swallow them: written below the topic branch,
# "study something new" matched with topic="something new", and the Scholar then invented a
# one-off topic called "something new" instead of taking the next thing on the syllabus. An
# alternation is tried left to right, so the specific phrasings have to stand to the left of
# the general one.
STUDY_NOW_RE = re.compile(r"""^(?:
      (?:go\s+)?(?:study|research)\s+(?:something|anything)
        (?:\s+(?:now|new|else|useful|today))*
    | (?:do|run)\s+(?:a\s+)?(?:study|research)(?:\s+(?:tick|now|run))?
    | (?:go\s+)?(?:study|research|read\s+up\s+on|look\s+in\s*to|dig\s+in\s*to)
        \s+(?P<topic>.{2,60}?)
        (?:\s+(?:now|today|please|for\s+me|next))?
  )$""", re.IGNORECASE | re.VERBOSE)

# WHAT MUST NOT MATCH, and study_proof carries it as a control: "what did you study today",
# "should I study finance", "why did you study that". Every one of them has a question stem in
# front of the verb, so the ^ anchor refuses them before any capture group is considered. The
# failure mode if these anchors are ever loosened is the expensive one - the butler silently
# spending a study tick and a minute of Groq tokens every time the boss asks him a question
# with the word "study" in it, and answering the question he was not asked.
_STUDY_NOT = ("what did you study today", "should i study finance",
              "why did you study that", "what is a study", "how do you study",
              "tell me about your studying")

# THE REFUSAL. It is the Doorman's own sentence, verbatim, and not a new one: a guest asking
# this house to study something is at the same door as a guest asking it to send mail, and
# giving that door a second, differently-worded refusal would be two laws to keep in step.
# It carries no name - not the boss's, not the guest's - for the reason the Hands refusal
# carries none.
STUDY_REFUSAL = "I take orders from one voice in this house, and it is not speaking just now."


# A BARE DEICTIC IS NOT A TOPIC, AND IT IS NOT THIS BRANCH'S SENTENCE TO ANSWER. "study it",
# "study that", "look into this" all name something by pointing at it, and what they point at
# lives in the antecedent memory - which is DO-NOT-ALTER and which this funnel branch sits
# above. Matched here, "study it" would have commissioned a study of a topic literally called
# "it": no syllabus row, no queries, three web searches for the word, and a note filed under
# a pronoun. Refusing to match sends the sentence on to the brain, which knows what "it" was.
_STUDY_DEICTIC = ("it", "this", "that", "them", "these", "those", "him", "her", "us",
                  "there", "then", "one", "the same", "it now", "that now", "this now")


def study_asked(question):
    """The topic to study, "*" for "whatever is next", or "" for a message that is not it."""
    for form in _addressless_forms(question):
        got = STUDY_NOW_RE.match(form)
        if not got:
            continue
        topic = (got.groupdict().get("topic") or "").strip(" .,!?;:")
        if topic and topic.lower() in _STUDY_DEICTIC:
            return ""
        return topic or "*"
    return ""


def study_allowed(spoken, seal):
    """(True, "") if this voice may spend a study tick, else (False, the refusal).

    A FOURTH GATE, NARROWER THAN THE ROOM'S AND WIDER THAN THE HANDS'. The three that exist
    already sit at different costs and this one has its own, so it gets its own function rather
    than a reused one:

      - the Hands gate turns a word into an email leaving the house, and it SPENDS the
        speaker's verdict when it admits somebody, because a number that authorises twice is a
        number worth stealing.
      - the room gate admits BOSS or any enrolled name, because filling the screen sends
        nothing and one press of Escape undoes it.
      - this gate admits the BOSS SEAL ONLY - the mandate's words are "from the boss's
        voiceprint", which is stricter than the room's "boss or a name", so an enrolled
        colleague may fill the screen and may not commission a study into his corpus - and it
        does NOT spend the verdict, because a study writes into the boss's own notes and costs
        tokens but sends nothing and reaches nobody. Spending his verdict on a study would
        make his next spoken "yes" at the Hands card need a fresh sentence to be measured
        from: a real cost, paid for a file in his own notes folder.

    IT READS THE SEAL AND NOT THE HANDS FLAG, which is a deliberate narrowing rather than a
    shortcut. The hands privilege is a per-row flag on the voiceprint store and reading it here
    would mean plumbing the verdict through protected_answer()'s signature - the funnel's, which
    is not ours to widen. The seal already answers the question the mandate actually asked:
    "BOSS" is the boss's voiceprint and nothing else is.

    THE KEYBOARD IS ALWAYS THE BOSS'S, as at every other door - a typed message has no
    `speaker` block, so `spoken` is False and this returns True. The mandate says "from the
    boss's voiceprint OR KEYBOARD", and that is this clause.

    WITH NOBODY ENROLLED THE LAW STANDS DOWN SILENTLY. has_hands_voice() is the switch, exactly
    as at the other three doors: identify() answers GUEST to an empty roster, so without this
    clause a house that had never been taught a voice would refuse every spoken study - the
    same seal a stranger gets, for an entirely different reason.

    AND IT FAILS CLOSED ON A SPOKEN TURN WITH AN EMPTY SEAL. "Somebody spoke and this process
    could not say who" is not an identification, and it is the case that is easiest to write by
    accident: a stale turn number, one this server never issued, or a page that asked nothing.
    An empty seal is not "BOSS", so the last line refuses it without needing a clause.
    """
    if not spoken:
        return True, ""
    if voiceprint is None:
        return True, ""
    try:
        if not voiceprint.has_hands_voice():
            return True, ""
    except Exception:                                          # noqa: BLE001
        # A store that will not read is not a reason to spend the boss's tokens on a voice
        # nobody could place. This is the Hands gate's choice on the same failure and not the
        # room's, because what is behind this door is written into the corpus he will be
        # quoted back from, and a bigger window is not.
        return False, STUDY_REFUSAL
    if str(seal or "") == "BOSS":
        return True, ""
    return False, STUDY_REFUSAL


# ---- §35 PART 2: THE DIRECTOR'S COMMAND SURFACE ---------------------------------------------
#
# ANCHORED ON THE WHOLE ADDRESSLESS UTTERANCE, like STUDY_NOW_RE and FULLSCREEN_ON_RE and for
# the same reason: "what video did you make", "can you make videos", "how long do your videos
# take" must all reach the brain as ordinary questions, and the ^...$ anchors are what make that
# true rather than a hope.
#
# THE BARE ALTERNATIVE COMES FIRST, which is STUDY_NOW_RE's lesson paid forward: an alternation
# is tried left to right, and a capturing branch written above a bare one will swallow it. Here
# the bare branch cannot be swallowed - "make a video" has nothing after the noun for
# "about X" to capture - but it is placed first anyway so the ordering is a rule in this file
# rather than an accident of this particular grammar.
#
# BILINGUAL, AS THE MANDATE SAYS, AND HINDI TAKES BOTH ORDERS. "video banao pricing par" and
# "pricing par video banao" are both ordinary Hinglish, the postposition `par` is what marks the
# topic in each, and a grammar that took only the English order would refuse half of what is
# actually said in this house. `banao`/`bana do`/`banaiye` are the imperative forms the boss
# uses; `banaya` is PAST TENSE and is deliberately absent, because "tum ne video banaya" is a
# question about a video that exists, not an order to make one.
DIRECT_RE = re.compile(r"""^(?:
      (?:make|create|film|shoot|record|produce)\s+(?:me\s+)?(?:a|an|one)?\s*video
    | (?:ek\s+)?video\s+bana\s*(?:o|do|iye)
    | (?:make|create|film|shoot|record|produce)\s+(?:me\s+)?(?:a|an|one)?\s*video
        \s+(?:about|on|of|for|regarding|covering)\s+(?P<topic>.{2,70}?)
    | (?:ek\s+)?video\s+bana\s*(?:o|do|iye)\s+(?P<topic2>.{2,70}?)\s+par
    | (?P<topic3>.{2,70}?)\s+par\s+(?:ek\s+)?video\s+bana\s*(?:o|do|iye)
  )(?:\s+(?:now|today|please|for\s+me|abhi|zara))?$""", re.IGNORECASE | re.VERBOSE)

# WHAT MUST NOT MATCH, and director_proof carries these as controls. Every one of them has a
# question stem or a different verb in front, so the ^ anchor refuses them before any capture
# group is considered. The failure mode if these anchors are ever loosened is the expensive one:
# the butler spending sixty-seven seconds of CPU, five piper calls and a model call every time
# the boss says the word "video" in a sentence - and answering a question he did not ask.
_DIRECT_NOT = ("what video did you make", "can you make videos", "how do i make a video",
               "show me the video", "play the video", "why did you make that video",
               "is the video ready", "delete the video", "what is a video")


def director_asked(question):
    """The topic to film, "*" for "he asked but named nothing", or "" for anything else."""
    for form in _addressless_forms(question):
        got = DIRECT_RE.match(form)
        if not got:
            continue
        said = got.groupdict()
        topic = ((said.get("topic") or said.get("topic2") or said.get("topic3") or "")
                 .strip(" .,!?;:"))
        # A BARE DEICTIC IS NOT A TOPIC, AND IT IS NOT THIS BRANCH'S SENTENCE TO ANSWER - the
        # same law as the Scholar's, reusing the same list rather than a second copy of it.
        # "make a video about it" names something by pointing, and what it points at lives in the
        # antecedent memory, which is DO-NOT-ALTER and which this branch sits above. Matched here
        # it would have filmed a topic literally called "it": a retrieval for a pronoun, and on
        # this corpus a graceful-empty refusal that looked like a broken Director.
        if topic and topic.lower() in _STUDY_DEICTIC:
            return ""
        return topic or "*"
    return ""


def director_allowed(spoken, seal):
    """(True, "") if this voice may commission a video, else (False, the refusal).

    THE SAME GATE AS THE SCHOLAR'S, CALLED AND NOT COPIED. §35 says "guests refused" and nothing
    more, and the Scholar's door already answers exactly the question this one asks: BOSS seal
    only, the keyboard is always the boss's, stands down silently with nobody enrolled, fails
    closed on a store that will not read. A render writes into the boss's own output folder and
    costs CPU and tokens while sending nothing and reaching nobody - the same cost profile the
    study gate was built for, one rung below the Hands.

    IT IS A FUNCTION RATHER THAN AN ALIAS so that this door has a name of its own in the log and
    in director_proof, and so that if one day the two gates must differ, they differ HERE instead
    of in a shared body that two mandates both depend on. And it returns the Doorman's own
    sentence verbatim, not a new one: a guest asking this house to film something is at the same
    door as a guest asking it to send mail, and a second differently-worded refusal would be two
    laws to keep in step.
    """
    return study_allowed(spoken, seal)


# =============================================================================================
#  §40 - THE BROADCASTER'S TWO SENTENCES
# =============================================================================================
# TWO INTENTS AND NOT ONE, because "put it up" and "make it public" are two different acts with
# two different gates, and a single regex matching both would have to guess which the boss meant.
# The first starts a minute of uploading and lands UNLISTED; the second is the instant the world
# can see it. They are anchored at ^ with the Director's discipline and for its reason: the
# failure mode of a loose anchor here is not a wasted render, it is a film on the internet.
BROADCAST_RE = re.compile(r"""^(?:
      (?:please\s+)?(?:can\s+you\s+)?
      (?:put|upload|post)\s+(?:it|that|this|the\s+(?:film|video|last\s+one))
        \s+(?:up\s+)?(?:on|to)\s+(?:youtube|the\s+channel)
    | (?:please\s+)?(?:can\s+you\s+)?
      (?:upload|post)\s+(?:it|that|this|the\s+(?:film|video|last\s+one))
    | (?:put|get)\s+(?:it|that|the\s+(?:film|video))\s+on\s+(?:youtube|the\s+channel)
    | (?:upload|post)\s+(?:the\s+)?(?:film|video)\s+to\s+youtube
    )(?:\s+(?:now|today|please|for\s+me|abhi|zara))?[.!]?$""",
    re.IGNORECASE | re.VERBOSE)

# "MAKE IT PUBLIC". No topic, no id, no title - this sentence names NOTHING, deliberately. The
# film it refers to is whatever this machine last uploaded, which it reads out of its own ledger;
# a sentence that could carry a video id would be a sentence a model could fill with an invented
# one. See broadcast.uploaded().
PUBLISH_RE = re.compile(r"""^(?:
      (?:please\s+)?(?:can\s+you\s+)?
      (?:publish|release)\s*(?:it|that|this|the\s+(?:film|video))?
    | (?:make|set)\s+(?:it|that|this|the\s+(?:film|video))\s+public
    | (?:take|put)\s+(?:it|that)\s+public
    | go\s+public(?:\s+with\s+(?:it|that))?
    )(?:\s+(?:now|today|please|for\s+me|abhi|zara))?[.!]?$""",
    re.IGNORECASE | re.VERBOSE)

# WHAT MUST NOT MATCH, and broadcaster_proof carries every one of these as a control. The first
# four are questions ABOUT the channel, which belong to the brain; the last three are the ones
# that would be expensive to get wrong - "do not publish it" is a refusal, "unpublish it" asks for
# something this house cannot do, and "delete the video" must never find a route at all.
_BROADCAST_NOT = ("what did you upload", "is it on youtube yet", "how do i upload a video",
                  "what is on the channel", "do not publish it", "don't make it public",
                  "unpublish it", "delete the video", "take it down", "publish a book")


def broadcast_asked(question):
    """True when this sentence asks for the last film to go up. Nothing else returns True."""
    return any(BROADCAST_RE.match(form) for form in _addressless_forms(question))


def publish_asked(question):
    """True when this sentence asks for the unlisted film to become public."""
    return any(PUBLISH_RE.match(form) for form in _addressless_forms(question))


def broadcast_allowed(spoken, seal):
    """(True, "") if this voice may put a film up UNLISTED, else (False, the refusal).

    THE BOSS SEAL ONLY, which is study_allowed()'s test called and not copied - the Director's
    door, and a fifth name for it so that this one can be found in a log and in broadcaster_proof.

    AND WHY NOT THE HANDS' STRICTER DOOR, since an upload reaches outside the house and cannot be
    taken back. Because the two halves of §40 are gated SEPARATELY and each at its own cost:

      this door admits a BOSS voice to an UNLISTED upload. What it produces is a URL that nobody
        has - not indexed, not on the channel's public page, not in a subscriber's feed. It
        spends bandwidth and a permanent slot on his own channel, which is the Scholar's cost
        profile plus a minute of uplink, and it is one rung below "a stranger can see this".
      THE HANDS' DOOR - the real one, which spends the speaker's verdict - is what admits the
        flip to PUBLIC, because publish_video is a registry tool and goes through hands.execute()
        like send_email. So the act that strangers can see is behind the strictest gate in the
        house, and the act that nobody can see is behind the Director's.

    Putting the Hands' door here as well would have cost something real for nothing gained: the
    verdict is SPENT when it admits somebody, so an upload would consume the measurement his next
    spoken word at the publish card needs, and the boss would have to say a whole fresh sentence
    to approve the very thing he just asked for.
    """
    return study_allowed(spoken, seal)


def broadcast_latest_film():
    """The folder of the most recent finished film, or "" - what "put IT up" means.

    THE LEDGER FIRST, THE DISK SECOND, and the order is the point. jobs-ledger.json records what
    the Director actually finished and when, which is the only authority on "the last one"; a
    folder's mtime is a fact about a filesystem and changes when anything in it is touched. The
    disk is the fallback for the case the ledger cannot answer - its ring holds fifty rows, so a
    film made a hundred jobs ago is still on disk and no longer in the record.

    IT NEVER RETURNS A FOLDER WITHOUT A final.mp4 IN IT. A render that failed halfway leaves a
    directory behind, and "put it up" must not resolve to a half-written file - broadcast.upload()
    would refuse it at the encode check, but refusing it here means the boss hears "I have no
    finished film" rather than a reason about streams.
    """
    try:
        import jobs
        for row in reversed(jobs.ledger() or []):
            if str(row.get("name") or "") != "director" or row.get("outcome") != "done":
                continue
            path = str(row.get("path") or "")
            if path and os.path.exists(path):
                return os.path.dirname(path)
    except Exception as exc:                                       # noqa: BLE001
        sys.stderr.write("broadcast: the ledger would not read - %s\n" % exc)
    if director is None:
        return ""
    try:
        best, at = "", -1.0
        for entry in os.scandir(str(director.OUT_ROOT)):
            film = os.path.join(entry.path, "final.mp4")
            if not entry.is_dir() or not os.path.exists(film):
                continue
            when = os.path.getmtime(film)
            if when > at:
                best, at = entry.path, when
        return best
    except OSError:
        return ""


def _publish_card(cfg=None):
    """(params, why) for the publish Chain Card, built from the LEDGER and never from a sentence.

    §40: "the Chain Card shows title, description, tags, thumbnail plate and the unlisted URL".
    Every one of those five comes out of the row that upload() wrote, or out of the film's own
    script.md on disk - so the card the boss approves describes a film that provably exists on
    his channel, rather than six fields a language model filled in.
    """
    if broadcast is None:
        return None, "the Broadcaster is not available on this machine"
    rows = broadcast.uploaded()
    if not rows:
        return None, ("I have not put any film up yet, sir, so there is nothing to make public")
    row = rows[-1]
    video = str(row.get("videoId") or "")
    folder = os.path.dirname(str(row.get("path") or ""))
    # THE FILM'S OWN PACKAGE, RE-READ, so the description on the card is the description that is
    # actually on YouTube rather than a second composition of it. package() is pure and reads
    # script.md, which outlives the job that made it.
    kit = broadcast.package(folder, cfg=cfg)
    if not kit["ok"]:
        return None, kit["why"]
    seen = broadcast.verify(video)
    if seen["ok"] and seen["privacy"] == broadcast.PRIVACY_PUBLIC:
        return None, "That film is already public, sir - %s" % broadcast.watch_url(video)
    return {"video": video,
            "title": kit["title"],
            "url": str(row.get("url") or broadcast.watch_url(video)),
            "tags": ", ".join(kit["tags"]),
            "thumbnail": str(row.get("poster") or kit["thumbnail"] or ""),
            "description": kit["description"]}, ""


def _google_row():
    """(label, line, state) for the Command Panel's Google row, computed server-side.

    THE PANEL'S OWN LADDER, in the panel's own order - see the `id === 'google'` branch of
    rowRead() in viewer/index.html, which is the authority and which this mirrors clause for
    clause. Mirroring rather than importing because the panel is JavaScript in a browser and
    this is Python in a server, and the two can only be kept honest by a harness that asserts
    the same sentence out of both. That harness is routing_proof.

    FAILURE MODE IF THIS THROWS: google_api.status() reaches the network to resolve whether a
    stored grant is still live, and a flat network is not a reason to leave a question about
    the machine unanswered. The except clause gives the truthful answer instead of a guess.
    """
    try:
        state = google_api.status()
        consent = google_api.pending()
    except Exception as exc:                                  # noqa: BLE001
        return ("Connect Google", "GOOGLE: UNKNOWN · %s" % (exc or "the server did not answer"),
                "unknown")
    mail = str(state.get("email") or "")
    word = str(state.get("state") or "")
    if word == "no-client" or state.get("clientPresent") is False:
        return ("Connect Google",
                "GOOGLE: NO CLIENT FILE · secrets/google_client.json is missing", "no-client")
    if str(consent.get("state") or "") == "waiting":
        return ("Connect Google",
                "GOOGLE: WAITING FOR YOUR CONSENT · finish it in the browser", "waiting")
    if str(consent.get("state") or "") == "refused":
        return ("Connect Google",
                "GOOGLE: CONSENT REFUSED · %s" % (consent.get("why") or "try again"), "refused")
    if word == "connected":
        return ("Disconnect Google",
                "GOOGLE: CONNECTED" + (" · " + mail if mail else ""), "connected")
    if word == "reconnect":
        return ("Reconnect Google",
                "GOOGLE: RECONNECT NEEDED · %s"
                % (state.get("why") or "Google will not renew the connection"), "reconnect")
    return ("Connect Google",
            "GOOGLE: NOT CONNECTED · the calendar and the mail are closed", "absent")


def spoken_connection(cfg=None):
    """(sentence, state-word) for the connection, naming the row and quoting its reading.

    ONE SENTENCE PER READING and each one ends with the next physical act, because "you are
    not connected" is a diagnosis and he asked a question that wants a remedy. The row's line
    is quoted verbatim - not summarised - so that what he hears and what he reads on the panel
    are the same string.
    """
    who = persona(cfg)
    call = who["boss_call"]
    label, line, state = _google_row()
    if state == "connected":
        said = ("Google is connected, %s. The Command Panel's Google row reads %s, and its "
                "button now says %s - the calendar and the mail are open to me."
                % (call, line, label))
    elif state == "absent":
        said = ("Not connected, %s. The Command Panel's Google row reads %s. Press %s on "
                "that row and allow the one consent screen in the browser; that is the whole "
                "of it, and I cannot press it for you." % (call, line, label))
    elif state == "no-client":
        said = ("I cannot even ask yet, %s. The Command Panel's Google row reads %s, and the "
                "button stays dead until that file is in place." % (call, line))
    elif state == "waiting":
        said = ("Half of the way, %s. The Command Panel's Google row reads %s - the consent "
                "page is already open and waiting on you; the row turns the moment you "
                "allow it." % (call, line))
    elif state == "refused":
        said = ("Consent was refused, %s. The Command Panel's Google row reads %s. Press %s "
                "again whenever you are ready." % (call, line, label))
    elif state == "reconnect":
        said = ("The grant has lapsed, %s. The Command Panel's Google row reads %s, and its "
                "button now says %s." % (call, line, label))
    else:
        said = ("I cannot read the connection just now, %s. The Command Panel's Google row "
                "reads %s, which is the server declining to answer rather than a verdict "
                "about Google." % (call, line))
    return said, state


# SPOKEN TO HIM, NOT ABOUT THE WORLD. The last clause of the funnel: after all four
# protected classes have missed, the notes and the web decide - and the web needs one thing
# more than "the notes are thin", which is that the question be about the WORLD.
#
# "Can you listen to me" is the sentence that taught this. It is not in class 2 only by
# accident of wording - "can you hear me alright", "are you able to understand my accent",
# "do you follow" all arrive the same way - and every one of them used to reach the gate as
# a substantial question the notes held nothing on, which is precisely "thin", which spent a
# real search on a real search engine asking it about the boss's own microphone. The class
# list can never be complete; this is the rule that makes an incomplete list safe.
SECOND_PERSON_RE = re.compile(r"""^(?:
      (?:can|could|will|would|do|did|are|were|have|has|should|shall)\s+you\b
    | you\s+(?:can|could|are|were|will|would|do|did)\b
    | (?:tell|show|remind)\s+me\s+(?:about\s+)?your\b
    | what'?s?\s+your\b | what\s+is\s+your\b | how\s+are\s+you\b
  )""", re.IGNORECASE | re.VERBOSE)


def spoken_to_him(question):
    """Is this addressed to the assistant about himself, rather than asked of the world?

    Reads every rung for the same reason class 2 does: "hey galaxy can you hear me" must not
    reach a search engine because one greeting stood in front of the pronoun.
    """
    return any(SECOND_PERSON_RE.match(form) for form in _addressless_forms(question))


def spoken_capabilities(cfg=None):
    """What he can do, SAID OUT LOUD, off the same count the brain's manifest was built
    from - see build_capabilities_manifest(), which puts the sentence in _MANIFEST.

    Not a second description of the machine. A second description is a second thing to
    forget to update, and the failure mode is the one this whole Part is about: an
    assistant who names a hand he has not got, or does not name one he has.
    """
    if not _MANIFEST["spoken"]:
        build_capabilities_manifest(cfg)
    return _MANIFEST["spoken"]


def protected_answer(question, cfg=None, ear_open=False, offer_standing=False,
                     spoken=False, seal=""):
    """(class, payload) for a message that is about this machine, else (None, None).

    `spoken` and `seal` are §29's, and they are read by ONE branch - the fullscreen one, which
    is the only thing in this funnel that does something to the room rather than saying
    something about it. Both default to the typed case, so every existing caller and every
    preflight call is unchanged in behaviour: see fullscreen_allowed().

    Classes 2 and 3 only. Class 1 lives above this in _hands_gate(), where the pending
    offer is, and class 4 is the Third Door and the registry, which answer_question()
    already owns. Zero retrieval either way: this function reaches the notes, the archive
    and the web exactly never, which is asserted rather than asserted-to in routing_proof.

    `offer_standing` is the caller saying that something is on the card awaiting a word. It
    changes exactly one thing: the deictic connection rung, where "it" has a second and
    likelier antecedent. See CONNECTION_DEICTIC_RE.
    """
    forms = _addressless_forms(question)
    if not forms:
        return None, None

    def said_it(pattern):
        """Any rung of the peel, whole. See _addressless_forms(): the fully peeled form is
        the usual reading, but a sentence that peels to nothing was still said."""
        return any(pattern.match(form) for form in forms)

    who = persona(cfg)
    line = ""
    name = ""
    gstate = ""
    # None means "the clock did not answer", which is a different thing from "" - the empty
    # string is what his OWN clock answers with, having no place in it. A sentinel rather than
    # a `"gclock" in locals()` test, which was the first draft and which turns a typo in the
    # branch below into a field that silently never appears.
    gclock = None
    # Same sentinel discipline as gclock's, one line up: None means "the room was not asked
    # about", "" is impossible, and "on"/"off" are the two answers.
    gfull = None
    grefused = ""
    # Same sentinel discipline again: None means the Scholar was not asked about at all, and a
    # dict means it was - whether or not the tick was allowed to start. A refused study and a
    # started one are both "asked", and the page and the proof tell them apart by the fields
    # inside rather than by the presence of the key.
    gstudy = None
    # Same sentinel discipline as gstudy's, one line up: None means the Director was not asked at
    # all, and a dict means it was - whether the render started, was refused, or was asked for
    # without a topic. All three are "asked", and the page and the proof tell them apart by the
    # fields inside rather than by the presence of the key.
    gdirect = None
    # Same sentinel discipline as gdirect's: None means the Broadcaster was not asked at all. The
    # dict's `publish` field is what tells the two branches apart - False is "put it up", True is
    # "make it public" - so the page and the proof read one key instead of two routes.
    gcast = None
    if said_it(META_RE):
        name = "meta"
        # FROM LIVE STATE, not from a hopeful fixed string. He is asking whether the ear
        # is open; answering "the ear is open" to a shut ear would be the same class of
        # lie as a frozen level bar that reads like a shut mouth.
        line = ("I am listening, %s - the ear is open and the room is yours."
                % who["boss_call"]) if ear_open else (
                "I am here, %s - the ear is shut just now, so I have this one message. "
                "Open it and the room is yours." % who["boss_call"])
    elif said_it(IDENTITY_SELF_RE):
        name = "identity"
        line = who["self_intro"]
    elif said_it(IDENTITY_BOSS_RE):
        name = "identity"
        line = ("You are %s, sir - %s, when we are talking like this."
                % (who["boss_formal"], who["boss_call"]))
    elif said_it(CAPABILITY_RE):
        name = "identity"
        line = spoken_capabilities(cfg)
    elif said_it(CONNECTION_RE) or (not offer_standing and said_it(CONNECTION_DEICTIC_RE)):
        # THE CONNECTION IS AN IDENTITY QUESTION, and it carries the class name "identity"
        # rather than a fifth one of its own because PROTECTED_CLASSES is fixed by the
        # mandate at four. What it adds instead is `googleState`, which is the one word a
        # harness needs to know WHICH reading it got without parsing the sentence back.
        name = "identity"
        # ONE READ OF THE STATE PER TURN. _google_row() resolves a stored grant against
        # Google, so calling it once for the sentence and once again for the label would
        # make two network trips for one question - and could answer the two from different
        # readings if the grant expired between them.
        line, gstate = spoken_connection(cfg)

    # ---- §29: THE ROOM, AND IT IS ABOVE THE CLOCK ---------------------------------------
    # ABOVE THE CLOCK AND BELOW ALL FOUR, and each half of that placement is a decision:
    #   below the four, because PROTECTED_CLASSES is fixed by the mandate and nothing new may
    #     shadow a sentence one of them already catches. Checked: none of the four's patterns
    #     can match a fullscreen phrase, so in practice the order is moot - but "in practice"
    #     is not a guarantee and the four keep their precedence anyway.
    #   above the clock, because worldclock.asked() reads a sentence looking for a PLACE, and
    #     the places are a long table. "go full screen" has no city in it today; a table that
    #     one day lists a town called Fulscreen is not a reason for the deck to stop obeying,
    #     and the cheap way to make that permanently true is to ask about the room first.
    if not name:
        want = fullscreen_asked(question)
        if want:
            name = "fullscreen"
            allowed, refusal = fullscreen_allowed(spoken, seal)
            if allowed:
                gfull = want
                # WHAT IS SAID IS SHORT ON PURPOSE. The boss asked for the screen, not for a
                # sentence about the screen; the confirmation he wants is the room changing.
                # It is not empty either, because preflight requires every classed payload to
                # carry a line and because a silent obey is indistinguishable from a drop.
                #
                # AND THE ADDRESS FORM IS THE BOSS'S ALONE. The Doorman above admits BOSS **or a
                # name**, as the mandate says - so an enrolled colleague may fill the screen, and
                # the first draft of this line then called her "Addi", because boss_call is the
                # only address form in the persona block. deaddress() would not have caught it:
                # it runs on the GUEST path, and a named voice is not a guest. A colleague gets
                # the same courtesy and no borrowed name.
                mine = (not spoken) or str(seal or "") == "BOSS"
                line = (("Filling the screen, %s." if want == "on"
                         else "Back to the window, %s.") % who["boss_call"]) if mine else (
                    "Filling the screen." if want == "on" else "Back to the window.")
            else:
                # THE STATE IS UNTOUCHED, which is the whole of the refusal: gfull stays None,
                # so the payload carries no instruction and the page has nothing to act on.
                # A refusal that said no and set the field anyway would be a refusal in prose
                # only, and that is exactly the bug this shape cannot have.
                grefused = "not-the-boss"
                line = refusal
                sys.stderr.write("  route: fullscreen - asked to go %s by a voice sealed %r, "
                                 "refused at the doorman; the room is untouched\n"
                                 % (want, seal or "?"))

    # ---- §30: THE CURRICULUM, BESIDE THE ROOM AND ABOVE THE CLOCK ------------------------
    # PLACED FOR THE SAME THREE REASONS §29's ROOM BRANCH WAS, and the placement is the whole
    # of its safety:
    #   below the four, because PROTECTED_CLASSES is fixed by the mandate at four and nothing
    #     new may shadow a sentence one of them already catches. Checked, not assumed: none of
    #     the four's patterns can match "study micro-saas now", and they keep their precedence
    #     regardless.
    #   below the room, because the two cannot collide - no fullscreen alternative contains the
    #     word study - and putting the cheaper, older branch first keeps §29's reading exactly
    #     as it was measured.
    #   above the clock, because worldclock.asked() reads a sentence looking for a PLACE off a
    #     long table, and a table that one day lists a town called Study is not a reason for the
    #     Scholar to stop obeying.
    #
    # AND IT RETURNS IMMEDIATELY. request() queues the tick on the daemon's thread and comes
    # straight back with a sentence - it does NOT run a study here. That is the Async Law at its
    # only load-bearing point: this function is on the conversational thread, and a ninety-second
    # study inside it would hold the turn open for ninety seconds. The seal is what reports
    # progress afterwards, not this reply.
    if not name:
        topic = study_asked(question)
        if topic:
            name = "study"
            allowed, refusal = study_allowed(spoken, seal)
            if not allowed:
                gstudy = {"asked": topic, "started": False, "refused": "not-the-boss"}
                line = refusal
                sys.stderr.write("  route: study - asked for %r by a voice sealed %r, refused "
                                 "at the doorman; no tick was queued\n" % (topic, seal or "?"))
            else:
                # THE ADDRESS FORM IS THE BOSS'S ALONE, and here that is trivially true because
                # this gate admits nobody else - but it is passed in the same way §29's is, so
                # that a later widening of study_allowed() cannot quietly hand a colleague his
                # name, and so that scholar.py never holds an address form of its own.
                mine = (not spoken) or str(seal or "") == "BOSS"
                started, line = scholar.MANAGER.request(
                    topic=(None if topic == "*"
                           else scholar.resolve_topic_name(topic)), why="boss",
                    boss_call=(who["boss_call"] if mine else ""))
                if not mine:
                    line = line.replace(", .", ".").replace(" , ", " ")
                gstudy = {"asked": topic, "started": bool(started), "refused": ""}

    # ---- §35: THE DIRECTOR, BELOW THE SCHOLAR AND ABOVE THE CLOCK ------------------------
    # PLACED FOR THE SAME THREE REASONS §30's STUDY BRANCH WAS, and the placement is the whole of
    # its safety:
    #   below the four, because PROTECTED_CLASSES is fixed by the mandate at four and nothing new
    #     may shadow a sentence one of them already catches. Checked, not assumed: none of the
    #     four's patterns can match "make a video about micro-saas pricing".
    #   below the Scholar, because the two cannot collide - no alternative of DIRECT_RE contains
    #     the word study and none of STUDY_NOW_RE's contains the word video - and putting the
    #     older branch first keeps §30's reading exactly as it was measured.
    #   above the clock, because worldclock.asked() reads a sentence looking for a PLACE off a
    #     long table, and a table that one day lists a town called Video is not a reason for the
    #     Director to stop obeying.
    #
    # AND IT RETURNS IMMEDIATELY, which is the Async Law at its second load-bearing point.
    # MANAGER.request() queues the render on a daemon thread and comes straight back with a
    # sentence - it does NOT render here. This function is on the thread holding the boss's HTTP
    # request open, and a sixty-seven-second render inside it would freeze the glass for over a
    # minute. The progress bus is what reports afterwards; this reply is only the announcement.
    if not name and director is not None:
        topic = director_asked(question)
        if topic:
            name = "direct"
            allowed, refusal = director_allowed(spoken, seal)
            if not allowed:
                gdirect = {"asked": topic, "started": False, "refused": "not-the-boss", "job": ""}
                line = refusal
                sys.stderr.write("  route: direct - a video of %r asked by a voice sealed %r, "
                                 "refused at the doorman; nothing was rendered\n"
                                 % (topic, seal or "?"))
            elif topic == "*":
                # HE ASKED FOR A VIDEO AND NAMED NOTHING. Not a refusal and not a render: the one
                # question back. Answered here rather than by the brain because the brain would
                # answer it with prose about videos in general, and the Director is what was
                # asked for.
                gdirect = {"asked": "*", "started": False, "refused": "", "job": ""}
                line = "What should the video be about, sir?"
            else:
                # THE JOB ID COMES BACK FROM THE CALL, not from a second read of MANAGER.live().
                # live() is only populated while the render is in flight, so reading it here was
                # a race the page lost in both directions: a placeholder id before the thread
                # started, and an empty one after a fast render had already finished. This id is
                # the one the bus opened, and it is what the glass polls /jobs with.
                started, line, job = director.MANAGER.request(topic, why="boss")
                gdirect = {"asked": topic, "started": bool(started), "refused": "", "job": job}

    # ---- §40's BROADCASTER, TWO BRANCHES, BELOW THE DIRECTOR ------------------------------
    #   - below the four, because PROTECTED_CLASSES is fixed by the mandate at four and nothing
    #     new may shadow one of them. Both branches test `not name`, so every class above wins.
    #   - and below the DIRECTOR, which matters for one sentence: "upload the video" asks for a
    #     film that already exists to go up, and DIRECT_RE's anchors do not match it - but if
    #     they ever loosened, the render is the more expensive mistake and should not be reachable
    #     from a sentence about uploading. Order settles it rather than a comment.
    #
    # NEITHER BRANCH UPLOADS OR PUBLISHES ON THIS THREAD. The first queues on a daemon thread
    # (the Async Law: a four-megabyte PUT is a minute of a held-open request); the second does not
    # act at all - it raises a PROPOSAL and returns the question, and the act happens later, in a
    # subprocess, when a human has said yes.
    if not name and broadcast is not None and broadcast_asked(question):
        name = "broadcast"
        allowed, refusal = broadcast_allowed(spoken, seal)
        if not allowed:
            gcast = {"asked": True, "started": False, "refused": "not-the-boss", "job": "",
                     "publish": False, "pending": ""}
            line = refusal
            sys.stderr.write("  route: broadcast - an upload asked by a voice sealed %r, "
                             "refused at the doorman; nothing left this machine\n" % (seal or "?"))
        else:
            folder = broadcast_latest_film()
            if not folder:
                gcast = {"asked": True, "started": False, "refused": "no-film", "job": "",
                         "publish": False, "pending": ""}
                line = ("I have no finished film to put up, sir - ask me to make one first.")
            else:
                started, line, job = broadcast.MANAGER.request(folder, why="boss",
                                                               cfg=cfg)
                gcast = {"asked": True, "started": bool(started), "refused": "", "job": job,
                         "publish": False, "pending": ""}
                sys.stderr.write("  route: broadcast - uploading %r started=%s job=%r\n"
                                 % (folder, bool(started), job))

    if not name and broadcast is not None and publish_asked(question):
        name = "broadcast"
        allowed, refusal = broadcast_allowed(spoken, seal)
        if not allowed:
            # A GUEST ASKING FOR PUBLIC IS REFUSED BEFORE A CARD EXISTS, which is the stronger
            # half of §40's "guest voice => stays unlisted". The weaker half - a guest saying
            # "yes" to a card the boss raised - is handshake_open()'s BOSS seal, and both are
            # asserted in broadcaster_proof. NOTHING IS LEFT PENDING by this path, so there is
            # no card for a later word to confirm.
            gcast = {"asked": False, "started": False, "refused": "not-the-boss", "job": "",
                     "publish": True, "pending": ""}
            line = refusal
            sys.stderr.write("  route: broadcast - a publish asked by a voice sealed %r, "
                             "refused at the doorman; the film stays unlisted\n" % (seal or "?"))
        else:
            params, why = _publish_card(cfg)
            if not params:
                gcast = {"asked": False, "started": False, "refused": "nothing-to-publish",
                         "job": "", "publish": True, "pending": ""}
                line = why
            else:
                # THE PROPOSAL IS RAISED HERE AND CONFIRMED NOWHERE NEAR HERE. propose() puts the
                # six card fields in the slot; the window that lets a one-word "yes" answer it is
                # opened by handshake_offer() on the way out of /chat, from THIS utterance's own
                # measured seal; and the parameters hands.execute() eventually sends to the script
                # come from the slot rather than from whatever sentence confirms it.
                st, payload = hands.propose("publish_video", params, door="voice")
                pend = (payload or {}).get("pending") or {}
                line = str(pend.get("line") or payload.get("answer") or
                           "Shall I make it public, sir?")
                gcast = {"asked": False, "started": False,
                         "refused": "" if st == 200 else "proposal-refused",
                         "job": "", "publish": True, "pending": str(pend.get("id") or "")}
                sys.stderr.write("  route: broadcast - publish proposed for %s, status %s\n"
                                 % (params["video"], st))

    # ---- THE CLOCK, AND IT IS LAST ON PURPOSE -------------------------------------------
    # THE FOUR FUNNEL CLASSES ABOVE ARE UNTOUCHED. This branch is reached only when all four
    # have declined, it cannot shadow any of them, and PROTECTED_CLASSES still names the four
    # it has always named - see its comment. What it adds is a fifth ROUTE, "clock", carried
    # the same way `googleState` is carried: as an extra field on a class that already exists,
    # so nothing that reads the funnel's shape reads a different shape.
    #
    # WHY IT BELONGS UP HERE AT ALL, above the notes and the web. "What time is it in Tokyo"
    # is arithmetic on a table that is on this disk, and before this branch existed it went to
    # a search engine: a round trip, a rate limit and a page of advertising to compute a
    # subtraction, with the result that the one question in the house with a certain answer was
    # also the one that could fail. Zero lookups, like the four above it, for the same reason.
    if not name and worldclock is not None:
        try:
            how, place = worldclock.asked(forms[-1] if forms else "")
            if not how:
                # AND THE UNPEELED FORM TOO. The peel takes "so" and "just" off the front,
                # which helps, but it also eats "hey" out of the middle - and a city called
                # nothing in particular can survive that. Both rungs are read for the same
                # reason _addressless_forms exists at all: a fixed phrase is still a fixed
                # phrase whichever rung it is recognised on.
                how, place = worldclock.asked(forms[0] if forms else "")
            if how == "where":
                name = "clock"
                gclock = place
                line = worldclock.spoken(place, who["boss_call"])
            elif how == "here":
                name = "clock"
                gclock = ""
                line = worldclock.here_now(who["boss_call"])
        except Exception as exc:                                   # noqa: BLE001
            # A CLOCK THAT THROWS SAYS NOTHING. Falling through leaves the ordinary funnel to
            # answer, which is a worse answer than the clock's and a better one than a 500.
            sys.stderr.write("worldclock: %s\n" % exc)

    if not name:
        return None, None
    said = {"ok": True, "kind": "chat", "nodes": [], "answer": line,
            "route": name, "lookups": 0, "protected": name}
    if gstate:
        said["googleState"] = gstate
    if gfull is not None:
        # THE TWO FIELDS THE PAGE ACTS ON, and they are only ever present when the Doorman
        # admitted the voice. `fullscreenWant` is "on" or "off" and never "toggle": see
        # FULLSCREEN_ON_RE's comment for why a blind flip is the wrong instruction to send.
        said["fullscreen"] = True
        said["fullscreenWant"] = gfull
    if grefused:
        # A REASON CODE, so a harness and a log can tell this refusal from the Hands gate's two
        # without reading English, and so that the page can be certain there is nothing to do.
        said["refused"] = grefused
        said["fullscreen"] = False
    if gstudy is not None:
        # WHAT A HARNESS READS INSTEAD OF PARSING THE SENTENCE BACK, exactly as `clockPlace` is.
        # A refused study is the pair (studyAsked non-empty, studyStarted false) plus the reason
        # code, so study_proof's guest assertion is a fact rather than a string match on English
        # that _strip_address() may since have rewritten.
        said["study"] = True
        said["studyAsked"] = gstudy["asked"]
        said["studyStarted"] = gstudy["started"]
        if gstudy["refused"]:
            said["refused"] = gstudy["refused"]
    if gdirect is not None:
        # WHAT A HARNESS READS INSTEAD OF PARSING THE SENTENCE BACK, exactly as `studyAsked` is.
        # A refused video is the pair (directAsked non-empty, directStarted false) plus the reason
        # code, so director_proof's guest assertion is a fact rather than a string match on
        # English that _strip_address() may since have rewritten. `directJob` is the bus id, which
        # is what lets the page follow the render it just commissioned rather than guessing which
        # job on /jobs is its own.
        said["direct"] = True
        said["directAsked"] = gdirect["asked"]
        said["directStarted"] = gdirect["started"]
        if gdirect["job"]:
            said["directJob"] = gdirect["job"]
        if gdirect["refused"]:
            said["refused"] = gdirect["refused"]
    if gcast is not None:
        # WHAT A HARNESS READS INSTEAD OF PARSING THE SENTENCE BACK, exactly as `directAsked` is.
        # A refused upload is the pair (broadcast true, broadcastStarted false) plus the reason
        # code; a refused publish is (broadcastPublish true, broadcastPending empty), which is the
        # assertion §40's "guest voice => stays unlisted" is written against - an empty pending id
        # means no card was left standing for any later word to confirm.
        said["broadcast"] = True
        said["broadcastAsked"] = bool(gcast["asked"])
        said["broadcastStarted"] = bool(gcast["started"])
        said["broadcastPublish"] = bool(gcast["publish"])
        said["broadcastPending"] = gcast["pending"]
        if gcast["job"]:
            said["broadcastJob"] = gcast["job"]
        if gcast["refused"]:
            said["refused"] = gcast["refused"]
    if gclock is not None:
        # WHAT A HARNESS READS INSTEAD OF PARSING THE SENTENCE BACK. `clockPlace` is empty for
        # his own clock, the canonical LABEL for a city that resolved, and empty for one that
        # did not - so a refusal is the pair (clockAsked non-empty, clockPlace empty), which is
        # a fact a proof can assert without matching English.
        said["clock"] = True
        said["clockPlace"] = (worldclock.resolve(gclock)[0] or "") if gclock else ""
        said["clockAsked"] = gclock
        said["clockSource"] = worldclock.source()
    return name, said


# ================== PART B: TALKING ABOUT THE OFFER ==========================
#
# WHILE AN OFFER LIVES, NOT EVERYTHING IS A YES, A NO, OR A CHANGE OF SUBJECT. He asks
# what address it is going to. He says make it tomorrow instead. He asks why. Before this
# section those three were all "a new substantive question", which withdrew the offer he
# was in the middle of examining and then went and searched the notes for the words he had
# used to examine it. The offer he was about to accept was gone and something irrelevant
# was lit behind an answer to a question he had not asked.
#
# So: a message that is ABOUT the offer keeps the offer alive and goes to the brain with
# the offer in front of it. A message that is a genuine new request still releases the slot
# with its own line, exactly as before - silence is not consent and neither is a change of
# subject. The whole difficulty is telling those two apart, and it is done with two signals
# and an order, each of which names what it is there to prevent.
_AMEND_RE = re.compile(r"""(?:
      \binstead\b | \brather\s+than\b | \bnot\s+\w+\s+but\b
    | \bchange\s+(?:it|that|the|to)\b | \bmake\s+it\b | \bmake\s+that\b
    | \buse\s+(?:this|that|the)\s+\w+\s+instead\b
    | \bactually\b | \bon\s+second\s+thought
    | \badd\b | \balso\s+(?:say|put|send|cc)\b | \bwithout\b
    | \b(?:shorter|longer|softer|warmer|firmer|later|earlier)\b
    | \bsend\s+it\s+to\b | \bcall\s+it\b
    # "SAY" IS AN INSTRUCTION ONLY WHERE IT IS ADDRESSED TO ME. It has to be here at all
    # because "say it warmer" and "just say sorry at the end" are amendments to a draft on
    # the card and nothing else in this pattern would catch them. It was written \bsay\s+,
    # which is the whole verb wherever it appears - and the verb appears in the middle of
    # ordinary questions that have nothing to do with any offer.
    #
    # FAILURE MODE THIS CATCHES, and it was live: "what do my notes say about coffee" asked
    # while a calendar proposal stood matched on "say about", so the change of subject was
    # read as an amendment. The offer was neither executed nor released, the withdrawal line
    # was never spoken, the page was handed the same pending slot back and re-drew the card,
    # and the boss's actual question was answered as a remark about a reminder. Silence is
    # not consent - and neither is a regex that swallows the change of subject. So the verb
    # must be IMPERATIVE: at the head of what he said once the address is off it, or
    # pointing at the offer with its object.
    | (?:^|,\s*|\band\s+|\balso\s+|\bjust\s+|\bplease\s+|\bcan\s+you\s+)say\b
    | \bsay\s+(?:it|that|this)\b
  )""", re.IGNORECASE | re.VERBOSE)
# A reference back to the thing on the table. The offer's own subject, pointed at rather
# than named: the one word that separates "is it going to the right person" from "what is
# react", both of which are questions and only one of which is about the offer.
_DEICTIC_RE = re.compile(r"""\b(?:
      it | it'?s | its | that | this | those | these | them | the\s+one | the\s+email
    | the\s+message | the\s+draft | the\s+invite | the\s+meeting | you
  )\b""", re.IGNORECASE | re.VERBOSE)
_QUESTION_RE = re.compile(r"""^(?:
      who | what | which | whose | whom | when | where | why | how
    | is | are | was | were | does | do | did | can | could | will | would
    | should | shall | am | have | has
  )\b""", re.IGNORECASE | re.VERBOSE)


def about_the_proposal(question, pending):
    """Is this message about the offer awaiting a word, rather than a new request?

    THE ORDER IS THE ARGUMENT.

    1 AN AMENDMENT FIRST, above every other door. "Send it to Bob instead" reads to
      hands_wanted() as a brand-new email, and treating it as one would drop the offer he
      was correcting and compose a second one from scratch. Above the doors, so the
      correction reaches the brain with the original in front of it and comes back as a
      revision.
    2 THE HARD DOORS SECOND. "Remember that ...", "go back to your normal brain",
      "thirty minutes on this" are instructions to this machine, not remarks about the
      offer, and they have always released the slot. They still do.
    3 A QUESTION THAT POINTS AT IT, third and narrowly. A question alone is not enough:
      "what is react" asked while an email waits is a genuine new request, and answering
      it as chatter about the email would lose it. So a question must also POINT - it,
      that, the message, you - and the deictic is the whole of the difference.
    4 ANYTHING ELSE IS A NEW REQUEST, which is where this function started life and what
      it still does in the ordinary case.
    """
    if not pending:
        return False
    said = _addressless(question)
    if not said:
        return False                      # a bare greeting; the gate leaves it alone
    if _AMEND_RE.search(said):
        return True
    if (CAPTURE_RE.match(question) or is_swap_request(question)
            or focus.is_focus_request(question)):
        return False
    asked = str(question or "").strip().endswith("?") or bool(_QUESTION_RE.match(said))
    return bool(asked and _DEICTIC_RE.search(said))


def proposal_context(pending):
    """The offer, described to the brain in three lines and no more.

    The PARAMETERS go in, because "what address is it going to" cannot be answered without
    them, and they are already the boss's own words on his own machine - nothing here
    travels anywhere he did not send it. The SENTENCE goes in verbatim so the brain answers
    about the offer that is actually on the card rather than about a paraphrase of it.

    FAILURE MODE THIS CATCHES, and it caught it: hands.pending_public() puts the VALUES in
    `params` and the SCHEMA in `fields` - name, type, required, and no value anywhere - and
    the sentence under `line`. Read the wrong halves and the block is syntactically perfect
    and factually empty, which is worse than absent: asked what time his dentist appointment
    was for, with "friday 3pm" sitting on the card in front of him, he was told "no hour was
    ever set on it". An empty block would have made him repeat himself; a confidently empty
    one contradicted the card.
    """
    if not isinstance(pending, dict):
        return ""
    params = pending.get("params")
    params = params if isinstance(params, dict) else {}
    labels = {}
    for field in pending.get("fields") or []:
        if isinstance(field, dict) and field.get("name"):
            labels[field["name"]] = field.get("label") or field["name"]
    detail = "; ".join("%s: %s" % (labels.get(key, key), value)
                       for key, value in params.items()
                       if str(value if value is not None else "").strip())
    return (
        "\n\nAWAITING HIS WORD, RIGHT NOW. You have offered to do something and he has "
        "neither agreed nor refused - he has said the message below about it.\n"
        "- The offer, in your own words: \"%s\"\n"
        "- The tool: %s%s\n"
        "- ANSWER THE REMARK, and keep the offer standing. Do not say it is done, do not "
        "say it is cancelled, and do not ask him to repeat himself. If he is asking about "
        "it, tell him from the details above. If he is CHANGING it, re-offer it with the "
        "change using the tool tag, and say nothing about tags. If he is neither, answer "
        "him plainly and remind him in one short clause that the offer is still waiting."
        % (str(pending.get("line") or pending.get("proposal") or "").strip(),
           pending.get("tool") or "?",
           (" (%s)" % detail) if detail else ""))


def talk_about_proposal(question, session, pending, cfg=None):
    """Answer a remark about the offer, with the offer in front of the brain. No lookups.

    ZERO RETRIEVAL, and that is a claim about correctness rather than about cost: the
    answer to "what address is that going to" is in the slot, not in his notes and
    certainly not on the web. A search here could only ever return something irrelevant,
    and it would light the panel behind it while it did.

    THE SLOT IS NOT TOUCHED unless the brain re-offers. The one thing this function must
    never do is lose the offer: it is on the card, he is looking at it, and he has not
    said yes or no yet.
    """
    if cfg is None:
        cfg = load_config()[0]
    with _lock:
        history = list(_history.get(session, []))
    manifest, protocol = hands.prompt_parts()
    messages, _plan = assemble(system=SMALLTALK_PROMPT, manifest=manifest,
                               protocol=protocol, offer=proposal_context(pending),
                               history=history, older=older_block(session),
                               ask=question.strip(), label="standing-offer")
    answer, error = call_model(cfg, messages)
    if error:
        return 502, {"error": error, "nodes": [], "kind": "chat",
                     "route": "proposal", "lookups": 0}
    wanted, params, _prose = hands.tool_tag(answer)
    if wanted is not None:
        # AN AMENDMENT, and the registry's own sentence says it back to him. propose()
        # supersedes the standing offer with a line saying it has let the earlier one go,
        # which is exactly right here: he asked for the change himself. The prose the
        # model wrote around the tag is dropped, as it is everywhere else - one voice.
        sys.stderr.write("  tool: the offer was AMENDED in conversation -> %s\n" % wanted)
        return hands.propose(wanted, tool_facts(wanted, params), door="tag")
    record_turn(session, question, answer)
    return 200, {"answer": answer, "nodes": [], "kind": "chat", "route": "proposal",
                 "lookups": 0, "pending": hands.pending_public()}


def private_identifier(question):
    """Does this message carry an email address, a telephone number or an address?

    One question, asked in two places: web_intent() refuses to build a query out of a
    message this is true of, and answer_question() says so out loud when the message had
    no other business than research. See PRIVATE_RE for why it is deliberately eager.
    """
    return bool(PRIVATE_RE.search(str(question or "")))


def semantic_holds_identifier(question, sem):
    """May the MEANING search claim a question that carries a private identifier?

    Only if what it found actually CONTAINS the identifier. A vector store answers every
    question with its three nearest passages whether or not it holds the answer, and
    "nearest" on a small collection is a low bar - so a question about a stranger's email
    address comes back with whatever the collection is most about, at a score just over
    the dial, and the notes door opens on it.

    FAILURE MODE THIS CATCHES, measured: "who is zqtask@example.invalid", asked with a
    previous question still in the session, scored 0.621 against a prompt pack in
    archive/samples that does not contain the address and has nothing to do with it. The
    door opened, kind became "notes", and the PII SHIELD - which is gated on kind for the
    good reason that a note genuinely naming the correspondent should answer - was stepped
    over. Nothing leaked: the notes branch searches no web, and what he said was true ("that
    address appears nowhere in your notes"). What was lost was the REFUSAL, said out loud,
    and the shield's own law is that a refusal the employer cannot see is indistinguishable
    from a failure.

    WHY THE TEST IS CONTAINMENT AND NOT A HIGHER DIAL. The threshold is right for prose,
    where a passage can mean the same thing in different words. An identifier has no
    synonyms: it either appears or it does not. So the evidence demanded here is the one
    kind a private identifier admits, and the dial is left exactly where it is.

    AND IT CANNOT COST A REAL NOTES ANSWER: the caller only consults this door when the
    keyword half has already declined, so a note that shares the address with the question
    has claimed it two branches earlier and never reaches here.
    """
    found = [m.group(0) for m in PRIVATE_RE.finditer(str(question or ""))]
    if not found:
        return True
    quoted = " ".join(str(hit.get("text") or "")
                      for hit in (sem.get("cited") or [])).lower()
    return any(one.lower() in quoted for one in found)


def substantial_question(question, prior=""):
    """Is there a real question here, once the pleasantries are peeled off?

    Split out of classify_question so that the web trigger can ask the same thing
    WITHOUT a score. It matters: a bare "morning!" scores 0.0 and would otherwise sail
    straight through the "the notes have nothing on this" test and off to a search
    engine. The words decide whether a question was asked; the score only decides
    where its answer should come from.
    """
    # The address comes off first, and on the raw text: a vocative is not a subject, and
    # after _bare() the comma that proves it is one is gone.
    bare = _bare(_strip_address(question))
    if not bare:
        return False               # nothing but an address - "Jarvis?"
    if CHATTER_RE.search(bare):
        return False               # about the assistant, not about the world
    stripped = _peel(bare)
    if not stripped:
        return False               # the whole message was pleasantries and an address
    # `prior` is the previous question, so that a bare follow-up ("why not?") counts
    # as a real question rather than as chatter for having no content words.
    if not tokenize(stripped) and not tokenize(prior):
        return False               # nothing but stopwords, and nothing to lean on
    return True


def web_query(question):
    """The question with any force trigger peeled off - what actually gets searched.

    "Jarvis, look this up: current population of Tokyo" -> "current population of
    Tokyo". A trigger with nothing after it peels to "", and the caller asks what to
    look up rather than searching for the phrase "look this up".
    """
    cleaned = FORCE_WEB_RE.sub(" ", str(question or ""))
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,.:;!?-\"'")
    # "look this up for me" and "...will you" leave a tail behind that is not a query.
    cleaned = re.sub(r"\b(?:for\s+me|please|will\s+you|would\s+you|thanks)\b\s*$", "",
                     cleaned, flags=re.IGNORECASE).strip(" ,.:;!?-")
    return cleaned


def _trace(trace, line):
    """One line into the lookup's own log, which the caller writes to stderr."""
    if trace is not None:
        trace.append(line)


def _quick_prompt(prior, question):
    """ChatML by hand, with an EMPTY think block and one worked example.

    Both of those are load-bearing, and both were arrived at by watching this model
    fail. qwen3:4b is a THINKING model: asked the instruction plainly it answers
    "Okay, the user previously asked..." and reasons for four hundred tokens - twenty-five
    seconds to produce four words, which is not a price a question can pay. `think:false`
    on /api/chat does not stop it on Ollama 0.34; opening the assistant turn with a closed
    `<think></think>` pair does, because the model finds its own reasoning already over.
    That needs the template out of the way, which is what `raw` buys, and raw means
    writing the ChatML here.

    The example turn is the difference between prose and a query. Told once what the
    answer looks like, the model answers in four tokens and a quarter of a second.
    """
    nothink = "<think>\n\n</think>\n\n"

    def turn(prev, cur):
        return ("<|im_start|>user\nPrevious question: %s\nFollow-up: %s<|im_end|>\n"
                "<|im_start|>assistant\n%s" % (prev, cur, nothink))

    return ("<|im_start|>system\n%s<|im_end|>\n" % REWRITE_INSTRUCTION
            + turn("what is the Eiffel Tower", "how tall is it?")
            + "how tall is the Eiffel Tower<|im_end|>\n"
            + turn(prior, question))


def _quick_clean(text, question):
    """The model's answer, or "" - and "" is a perfectly good outcome here.

    A rewrite that is wrong is worse than no rewrite at all: the heuristic below is
    predictable and the verbatim query is at least honest, while a hallucinated subject
    searches for something nobody asked about. So this is a gate and not a parser, and
    every rule in it has caught a real reply from this model.
    """
    line = ""
    for raw in str(text or "").replace("\r", "").split("\n"):
        candidate = raw.strip().strip("`\"'“”").strip()
        if candidate:
            line = candidate
            break
    if not line or "<|" in line or "<think" in line:
        return ""
    if QUICK_PROSE_RE.search(line):
        return ""                  # it explained itself instead of answering
    words = line.split()
    if not 1 <= len(words) <= QUICK_MAX_WORDS:
        return ""
    # And it must have RESOLVED something. A rewrite that adds no word the follow-up did
    # not already have is not a rewrite - it is the same pronoun with the same problem,
    # and passing it on as a fix would hide the failure instead of falling back from it.
    if not set(tokenize(line)) - set(tokenize(question)):
        return ""
    return line.rstrip(" ?!.")


def quick_rewrite(prior, question, trace=None):
    """The local model's standalone query, or "" if anything at all went wrong.

    Nothing here raises. Ollama not installed, Ollama not running, the model not pulled,
    a socket that hangs - they are all the same event to a question waiting on an answer,
    and they all mean "use the heuristic".
    """
    body = json.dumps({
        "model": QUICK_MODEL,
        "prompt": _quick_prompt(prior, question),
        "raw": True,
        "stream": False,
        # Deterministic, and short: a search query that needs more than 32 tokens is
        # prose. The stops are the two ways this model ends a line it means.
        "options": {"temperature": 0, "num_predict": 32,
                    "stop": ["\n", "<|im_end|>"]},
    }).encode("utf-8")
    started = time.monotonic()
    try:
        req = urllib.request.Request(QUICK_URL, data=body, headers={
            "Content-Type": "application/json", "User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=QUICK_TIMEOUT_S) as fh:
            payload = json.loads(fh.read().decode("utf-8", "replace"))
    except Exception as exc:                                   # noqa: BLE001
        _trace(trace, "the quick thinker (%s) did not answer: %s"
               % (QUICK_MODEL, str(exc)[:90]))
        return ""
    clean = _quick_clean(payload.get("response"), question)
    if not clean:
        _trace(trace, "the quick thinker answered with something that was not a query: "
                      "%r" % str(payload.get("response") or "")[:90])
        return ""
    _trace(trace, "%s rewrote the follow-up in %.2fs" % (QUICK_MODEL,
                                                         time.monotonic() - started))
    return clean


def _subject_of(question):
    """What the previous question was ABOUT, as one phrase, for the fallback.

    The last run of capitalised words, which is the proper noun in nearly every question
    anybody types: "what is the population of India" -> India, "what is the Eiffel Tower"
    -> Eiffel Tower. The first word is skipped because every sentence starts capitalised.

    And when there is no capital at all, the last content word. That is not a flourish:
    dictated questions arrive from the browser in one unpunctuated lowercase run, so a
    capital letter cannot be the only evidence this machine will accept of a subject -
    "what is react" has one all the same.
    """
    words = re.findall(r"[\w']+", str(question or ""))
    runs, current = [], []
    for i, word in enumerate(words):
        if i and word[:1].isupper() and word.lower() not in STOPWORDS:
            current.append(word)
        elif current:
            runs.append(current)
            current = []
    if current:
        runs.append(current)
    if runs:
        return " ".join(runs[-1])
    content = tokenize(question)
    return content[-1] if content else ""


def heuristic_rewrite(prior, question):
    """No model, no network: the previous question's subject, appended. Or "".

    Crude on purpose. "who created it react" is not English and no search engine cares -
    it carries both the question and the subject, which is the whole job.
    """
    subject = _subject_of(prior)
    if not subject or subject.lower() in str(question or "").lower():
        return ""                  # nothing to add, or it is already there
    return "%s %s" % (str(question).strip().rstrip(" ?!.,"), subject)


def resolve_followup(query, prior="", prior_kind="", trace=None):
    """THE REWRITER. A bare follow-up inherits its predecessor's subject - for the
    search, and for nothing else. Returns (query to send, how it was rewritten).

    Three conditions, all of which must hold, because each one is a way this could put
    words in somebody's mouth:

      there is a REMEMBERED QUESTION, and it was a real one. `prior_kind` is why the
        memory keeps the kind at all: "good morning" has no subject to inherit, and
        appending one to it would invent a question nobody asked.
      the follow-up is SHORT - under REWRITE_MAX_WORDS. A question long enough to carry
        its own subject keeps it.
      and it contains an ANAPHOR, which is the actual complaint: a pronoun searched on
        its own returns the wrong thing confidently.

    Then the quick thinker, then the heuristic, then verbatim. Falling all the way
    through is a normal outcome and costs the search nothing.
    """
    bare = str(query or "").strip()
    prior = str(prior or "").strip()
    if not bare or not prior:
        return bare, ""
    if prior_kind not in ("notes", "web"):
        return bare, ""
    if len(bare.split()) >= REWRITE_MAX_WORDS or not ANAPHOR_RE.search(bare):
        return bare, ""

    _trace(trace, "a bare follow-up: %r after %r" % (bare, prior))
    quick = quick_rewrite(prior, bare, trace)
    if quick:
        return quick, "quick"
    rough = heuristic_rewrite(prior, bare)
    if rough:
        _trace(trace, "the heuristic appended the previous subject instead")
        return rough, "heuristic"
    _trace(trace, "nothing could be inherited; searching it verbatim")
    return bare, ""


def sent_fields(query, rewrote=""):
    """What actually left the machine, for the record.

    THE LAW is that the card and the toast quote the employer's own words, so the viewer
    renders neither of these - it already has the question, because it is the one that
    typed it. They exist so that a rewrite is auditable from the reply alone: `searchedFor`
    on every web answer, and `rewrote` ("quick" or "heuristic") only when the sentence that
    went out was not the sentence that came in.
    """
    out = {"searchedFor": str(query or "")}
    if rewrote:
        out["rewrote"] = rewrote
    return out


def web_intent(question, confidence, prior="", in_scope=True):
    """WHY a live lookup is warranted, in one word, or "" for "it is not".

        "force" - they said "look this up". Nothing can veto that.
        "world" - weather, news, a result, a price: the answer changes hourly.
        "thin"  - THE NOTES CANNOT ANSWER IT: either they hold less than
                  WEB_CONFIDENCE_THRESHOLD of what was asked, or the question was
                  classified out of scope.

    THE GATE, in one sentence: a question reaches the web when it is SUBSTANTIAL and the
    notes CANNOT ANSWER IT. The vetoes above the score are what makes the first half
    true - small talk, questions about this machine and questions about this conversation
    are turned back before any number is consulted at all, so "good morning" still costs
    nothing and touches nothing. They share one shape: a low score is not evidence of
    thinness when the answer was never going to be in the collection in the first place.

    `in_scope` is the out-of-scope half of "cannot answer", and folding it in here is the
    whole repair: it used to be the case that an out-of-scope question was classified
    "chat" and answered from SMALLTALK_PROMPT without the web ever being knocked on -
    the assistant said "your notes do not cover that" while a live lookup sat one branch
    away, unasked. Both halves are called "thin" because they are the same fact told to
    the same reader: the collection does not have this.

    Returned as a reason rather than a boolean because the reason is worth logging and
    worth testing: "why did it search?" and "why did it not?" are the two questions
    anybody actually asks of this feature.
    """
    # ABOVE THE FORCE TRIGGER, and the only thing that ever will be. A private identifier
    # is refused rather than obeyed: "look up sam@example.com" asks this machine to hand a
    # stranger's address to a company that keeps everything it is told. The employer is
    # told plainly - see answer_question - rather than quietly given a different answer.
    if private_identifier(question):
        return ""
    # A REPLY IS NOT A QUESTION. "ok got it" scores nothing against the notes, which is
    # the exact condition "thin" exists for, so without this line the cheapest thing
    # anybody says here would be the one that spent a search. Above the force trigger for
    # the same reason as the shield: there is nothing in hand to look up.
    if backchannel_only(question):
        return ""
    if FORCE_WEB_RE.search(str(question or "")):
        return "force"
    if not substantial_question(question, prior):
        return ""                  # small talk never searches. It is not a question.
    bare = _bare(question)
    if SELF_RE.search(bare):
        return ""                  # about this machine; the web has never met it
    # AND THE SAME ARGUMENT FOR THE SESSION, one line lower because it is one line's worth of
    # difference: the web has never met this conversation either. ABOVE the world trigger on
    # purpose - "what did I say earlier today about the weather" matches both patterns, and the
    # question is what HE said, not what the sky is doing. See ABOVE ABOUT_SESSION_RE for how
    # this surfaced: PART 8's quarantine took away thirty notes of retrieval noise that had been
    # accidentally covering it, and the eviction probe started answering "according to current
    # web sources" about what its own employer had asked it ten minutes earlier.
    if ABOUT_SESSION_RE.search(bare):
        sys.stderr.write("  no lookup: %r is about this conversation, which is in the prompt\n"
                         % str(question).strip()[:60])
        return ""
    if REALWORLD_RE.search(bare):
        return "world"
    # THE LAST CLAUSE OF THE FUNNEL, and it only ever narrows "thin". A question about the
    # world has already been answered "world" above and a forced lookup two branches before
    # that; what is left here is a question the notes are thin on - and if it was SPOKEN TO
    # HIM rather than asked of the world, thinness is not a reason to go looking. See
    # spoken_to_him(): the protected classes catch the sentences he actually says, and this
    # catches the ones nobody thought to list.
    if spoken_to_him(question):
        sys.stderr.write("  no lookup: %r is spoken to me, not about the world\n"
                         % str(question).strip()[:60])
        return ""
    if confidence < WEB_CONFIDENCE_THRESHOLD or not in_scope:
        return "thin"
    return ""


def classify_question(question, best_score, prior="", confidence=1.0):
    """"notes" or "chat" - decided BEFORE anything is allowed to move the camera.

    A greeting or a joke gets a friendly reply and zero note indexes, so the
    galaxy holds perfectly still. Only questions that are actually about the
    notes are ever allowed to fly the camera or light a cluster.

    "web" is NOT returned here: whether a search actually produced anything is not
    known until it has been attempted, and a kind that might still be wrong is worse
    than no kind at all. answer_question() promotes this to "web" once snippets are in
    its hand - see web_intent() for the decision that sends it looking.
    """
    if not substantial_question(question, prior):
        return "chat"
    if best_score < RELEVANCE_FLOOR:
        return "chat"              # the notes genuinely have nothing on this
    # NO CHIPS FOR A REFUSAL. A note can score well on one incidental word and still
    # hold almost none of the question - and "notes" is the kind that lights chips,
    # flies the camera and opens the panel. Six notes lit behind an answer that did not
    # come from them is a provenance lie, and the fact that it is a pretty one is what
    # makes it worth a branch of its own. `confidence` defaults to 1.0 so that a caller
    # asking the old two-argument question gets the old two-argument answer.
    if confidence < WEB_CONFIDENCE_THRESHOLD:
        return "chat"
    return "notes"

# ------------------------------------------------------------------ index/config

_lock = threading.Lock()
_history = {}          # session id -> [ {role, content}, ... ]
_index = {"notes": [], "docs": [], "df": {}, "mtime": 0.0, "meta": {}}


# =============================================================================
#  THE ASSEMBLY, AND THE INSTRUMENT THAT WATCHES IT
#
#  Two things live here and they are one thing: the single place a prompt is
#  built, and the record of what was built. They are together because an
#  assembly nobody can read afterwards is an assembly nobody can be held to.
#
#  WHY THIS EXISTS AT ALL. Before it, five sites in this file each concatenated
#  their own message list and each trimmed the history with its own copy of the
#  same `del hist[:...]` line. Nothing anywhere declared how big a prompt was
#  allowed to get, nothing named the pieces it was made of, and the oldest turns
#  of a long conversation were DELETED - not summarised, not mentioned, just
#  gone. That is a machine that gets quietly worse the longer you talk to it,
#  and "quietly" is the part that makes it a hallucination question rather than
#  a memory question: a brain that has lost the turn its pronoun refers to does
#  not say so, it guesses.
#
#  THE ORDER IS DECLARED, NOT DISCOVERED. CONTEXT_ORDER below is the mandate's
#  order, written down once, so that "the order is stable" is a thing a test can
#  ask rather than a thing a reader has to reconstruct from five call sites.
# =============================================================================

# Each entry is (name, protected, where).
#
#   protected - eviction may never shorten or drop this block. Four of the seven
#     are, and each for a different reason: the persona is the character and a
#     nameless butler is a different machine; the manifest and the protocol are
#     what he is allowed to DO, and a brain that has lost them either refuses
#     work it can do or invents work it cannot; the retrieval hits are the only
#     thing standing between a cited answer and an invented one, which is why
#     the mandate says top-k NEVER DROPPED and why dropping them would turn a
#     grounded answer into a confident one.
#   where - the wire slot. This file talks to a chat-completions shape, so the
#     seven named blocks land in three places, and two of them are not where a
#     naive reading of the order would put them:
#       "persona" is prepended inside call_model by wear_persona(), which is a
#         property worth having rather than an accident - the persona is added
#         AFTER every decision about what to evict, so no budget arithmetic
#         anywhere in this file can reach it.
#       "retrieval" rides in the FINAL user turn, immediately under the
#         question, rather than ahead of the turns where the order names it.
#         That is deliberate and it is a deviation: evidence works by being the
#         nearest thing to the question it answers, and the heading that binds
#         it - "...and nothing else" - only binds what follows it in the same
#         message. The ORDER here is the precedence ladder the mandate asks for
#         and the thing eviction obeys; `where` is the geometry. Both are
#         declared, and both are asserted.
CONTEXT_ORDER = (
    ("persona",        True,  "preamble"),
    ("manifest",       True,  "system"),
    ("chain-protocol", True,  "system"),
    ("guest",          True,  "system"),
    # The offer standing on the card, shown only on the one path that can amend it. It is
    # protected because a turn that amends an offer and has lost the offer amends nothing:
    # the model would answer "make it five instead" as a fresh instruction with no subject.
    ("standing-offer", True,  "system"),
    ("retrieval",      True,  "user"),
    ("recent-turns",   False, "turns"),
    ("older-turns",    False, "system"),
    ("question",       True,  "user"),
)
CONTEXT_BLOCKS = tuple(name for name, _p, _w in CONTEXT_ORDER)
PROTECTED_BLOCKS = frozenset(name for name, protected, _w in CONTEXT_ORDER if protected)

# ============================= THE CONTEXT BUDGET ============================
#
# CONTEXT_FLOOR is what a turn costs when nothing can be given up: every protected block at
# the largest size the constants above allow. It is ARITHMETIC, not a guess, and it is
# written as a sum so that raising TOP_K or CONTEXT_CHARS moves it by itself:
#
#   TOP_K * CONTEXT_CHARS       every keyword note the retrieval may send, at full length
#   5 * SEM_CONTEXT_CHARS       every semantic passage (ingest.TOP_K is 5), at full length
#   2000                        the question, at the cap /chat already truncates it to
#   12000                       persona + preamble + manifest + protocol + the headings,
#                               measured at 6947 + 3609 + 1471 + ~150 and rounded up
#
# MAX_CONTEXT is the cap, and it is chosen against two numbers rather than one. It must be
# COMFORTABLY ABOVE CONTEXT_FLOOR, because a cap below the floor would be a cap that a
# perfectly ordinary notes question breaks every time; and it must be near enough to the
# measured distribution to bite before a model's own limit does. The twenty-turn hunt of
# PART 0 measured 4,532 to 26,132 characters on the wire, with the largest being a notes
# answer carrying eight thousand characters of passages and four pairs of history. So:
#
#   floor  29,000    the most a turn can cost with nothing left to give up
#   worst  26,132    the largest prompt twenty real turns actually produced
#   cap    48,000    about twelve thousand tokens; 65% headroom over the floor
#
# WHY IT IS IN CHARACTERS AND NOT TOKENS. Every number in this file that could be compared
# with it is in characters, nothing here tokenises, and a budget expressed in a unit the
# code cannot measure is a budget that gets estimated. Divide by four for tokens.
CONTEXT_FLOOR = TOP_K * CONTEXT_CHARS + 5 * SEM_CONTEXT_CHARS + 2000 + 12000
MAX_CONTEXT = 48000

# ------------------------- THE SUMMARY OF WHAT WENT -------------------------
# Three numbers, and the middle one is the whole of PART 0's cure.
#
#   OLDER_KEEP        how many evicted pairs are kept as a line of their own, newest of the
#                     old first. Beyond that they are counted, not quoted.
#   SUMMARY_PAIR_MAX  the budget per side of one summarised pair. WHOLE SENTENCES ONLY - see
#                     whole_sentences(), which is where "never mid-sentence" is enforced.
#   OLDER_MAX         the whole block's ceiling. Lines go from the OLDEST end when it is
#                     exceeded, and they go whole; the pinned first turn never goes at all.
OLDER_KEEP = 8
SUMMARY_PAIR_MAX = 200
OLDER_MAX = 4000
SENTENCE_RE = re.compile(r"[^.!?\n]+(?:[.!?]+|\n|$)")


def whole_sentences(text, budget):
    """As many whole sentences from the start of `text` as fit in `budget`. Never part of one.

    THE ONE PLACE "NEVER MID-SENTENCE" IS A FACT RATHER THAN AN INTENTION. A summary that cut
    at a character count would produce lines like "I answered: The margin is 82% because the"
    - and a model handed that finishes the thought for it, which is a fabrication this
    machine built itself out of its own history. So the loop takes sentences, and the one
    concession is deliberate: if the FIRST sentence alone is over budget it is kept whole
    anyway, over budget, because the alternative is cutting it. The block's own ceiling
    (OLDER_MAX) then drops WHOLE LINES from the oldest end, so every cut anywhere in this
    mechanism falls on a sentence boundary or a line boundary and never inside either.

    AND IT RETURNS A PREFIX, NEVER A REJOIN. This is the one bug this function has ever had and
    it was live until today. SENTENCE_RE ends a sentence AT the full stop, so any closing mark
    that belongs to that sentence - a quote, a bracket, the second half of a markdown emphasis -
    falls outside the match, and the old `" ".join(kept)` then put a space in front of it:

        '"Good evening" in French: **Bonsoir.**'  ->  '"Good evening" in French: **Bonsoir. **'
        'He said "stop." Then nothing.'           ->  'He said "stop. " Then nothing.'

    The second one is the frightening one, because it is not about markdown: EVERY quoted
    sentence in his history came out of here with its closing quote pushed off the end of the
    quotation. The summariser was allowed to QUOTE and to COUNT, and it was EDITING - which is
    the precise thing the whole of summarise_pairs() is written to refuse, since a model handed
    an altered quote has no way to know it was altered and will cite it all session.

    So the budget decides HOW MUCH to keep and the return value is then a PREFIX OF THE TEXT
    ITSELF, sliced at the end of the last sentence kept. That is lossless by construction: a
    prefix cannot gain a character that was not there or lose one that was, so no rejoining
    rule has to be got right. The rejoin was only ever a way of reconstructing separators that
    were already in the string.

    A WORDLESS FRAGMENT IS NOT A SENTENCE either, and needs saying because the budget would
    otherwise stop in front of one: a match with no letter and no digit is that closing mark,
    so it extends the prefix without being counted as a sentence and without consulting the
    budget - for the same reason the first sentence may exceed it. A line ending in an unclosed
    emphasis or an unclosed quotation is a worse lie than two characters of overrun.
    """
    said = re.sub(r"\s+", " ", str(text or "")).strip()
    if not said:
        return ""
    has_word = re.compile(r"[^\W_]", re.U)
    end, used, taken = 0, 0, 0
    for match in SENTENCE_RE.finditer(said):
        one = match.group(0).strip()
        if not one:
            continue
        if taken and not has_word.search(one):
            end, used = match.end(), used + len(one)   # this sentence's own closing mark
            continue
        if taken and used + 1 + len(one) > budget:
            break
        used += (1 if taken else 0) + len(one)
        taken += 1
        end = match.end()
    # AND THE CUT ITSELF MUST NOT ORPHAN A CLOSING MARK. Where the budget stopped, the very next
    # characters may be the closing half of something the kept text opened - and they are only
    # outside the prefix because SENTENCE_RE handed them to the FOLLOWING sentence, which was
    # dropped. 'He said "stop." Then nothing.' cut at the boundary gives 'He said "stop.', an
    # unclosed quotation, and a model cannot see where the quotation was meant to end. Absorbed
    # only when they sit flush against the cut with no space, which is the only arrangement in
    # which they can belong to the sentence being kept rather than to the one being dropped.
    orphan = re.match(r"[\"')\]*_’”]+", said[end:])
    if orphan:
        end += orphan.end()
    return said[:end].strip()


# session -> {"first": line or "", "pairs": [line, ...], "n": how many pairs summarised}
_older = {}


def summarise_pairs(session, gone):
    """Fold evicted messages into the session's summary, by RULE and with no model call.

    A MODEL CALL WAS CONSIDERED AND REJECTED, and the reason is the subject of this whole
    section: a summariser is a language model, a language model can invent, and an invention
    written into the history is a false memory this machine will then cite for the rest of the
    session. Every later turn would be grounded in it and none of them could tell. A rule
    cannot invent; it can only quote or count, and it costs nothing and never fails.

    THE FIRST PAIR IS PINNED FOREVER. That is not symmetry, it is the cure for the exact
    failure PART 0 reproduced: asked what it had been asked first, this machine named the
    oldest message still in its window - honestly, and wrongly, because nothing told it there
    had been anything before that. One pinned line answers that question for the life of the
    session, and it is one sentence long.
    """
    slot = _older.setdefault(session, {"first": "", "pairs": [], "n": 0})
    for i in range(0, len(gone) - 1, 2):
        user, assistant = gone[i], gone[i + 1]
        if user.get("role") != "user":
            continue
        slot["n"] += 1
        line = ("%d. You asked: %s  I answered: %s"
                % (slot["n"],
                   whole_sentences(user.get("content"), SUMMARY_PAIR_MAX) or "(nothing)",
                   whole_sentences(assistant.get("content"), SUMMARY_PAIR_MAX)
                   or "(nothing)"))
        if not slot["first"]:
            slot["first"] = line
        else:
            slot["pairs"].append(line)
    del slot["pairs"][:max(0, len(slot["pairs"]) - OLDER_KEEP)]
    return slot["n"]


def older_block(session):
    """The summarised history as one system block, or "" when nothing has been evicted yet.

    Headed with a sentence that says what it IS, because the failure it exists to prevent is
    a model treating a summary as the whole conversation - and counted, because "23 earlier
    turns" is the difference between a machine that has forgotten and a machine that knows it
    has forgotten. The second one can say so.
    """
    slot = _older.get(session)
    if not slot or not slot["first"]:
        return ""
    lines = [slot["first"]] + list(slot["pairs"])
    # "the most recent turns" and never "above" or "below". This block lives in the system
    # message, so the turns it defers to are BELOW it on the wire while the heading is above
    # them - the first draft said "above" and was pointing the model at the persona.
    head = ("\n\nEARLIER IN THIS CONVERSATION. %d turn(s) before the most recent turns you "
            "hold in full have been summarised to single lines. This is a SUMMARY and not "
            "the transcript: if they ask for wording you no longer hold, say that you have "
            "the gist of it rather than quoting it.\n" % slot["n"])
    if slot["n"] > len(lines):
        head += ("  (turns %d to %d are counted but no longer quoted)\n"
                 % (2, slot["n"] - len(slot["pairs"])))
    # WHOLE LINES, FROM THE OLDEST END, AND NEVER THE FIRST. index 0 is the pinned turn 1.
    while len(lines) > 1 and len(head) + sum(len(one) + 3 for one in lines) > OLDER_MAX:
        lines.pop(1)
    return head + "".join("  %s\n" % one for one in lines)


def forget_older(session=None):
    if session:
        _older.pop(session, None)
    else:
        _older.clear()

# THE INSTRUMENT. A ring of the last few turns, in RAM, and the rules it keeps are the
# Scribe's rules for the same reason: this holds the employer's own sentences.
#
#   IT IS NEVER WRITTEN TO DISK. No file, no log line, no ledger. server-trace.log gets
#     sizes and kinds from the lines already there and never a question or an answer.
#   IT IS SMALL AND IT FORGETS. TURN_DUMP_MAX turns, oldest out first.
#   THE RESET BUTTON EMPTIES IT, because the forget button that left a transcript behind
#     would not be a forget button - the same argument that already clears _last_ask.
#   AND THE PASSAGES ARE EXCERPTED. A dump carrying whole retrieved passages would be a
#     second copy of the archive in memory; TURN_EXCERPT_MAX is enough for a judge to
#     check whether a sentence in the answer is in the evidence, which is the only
#     question anybody asks it.
TURN_DUMP_MAX = 40
TURN_EXCERPT_MAX = 400
_turns = []                    # the ring, newest last
_turn_seq = {}                 # session -> how many turns it has had
_turn_local = threading.local()  # the turn this thread is in the middle of


def turn_begin(session, question, spoken=False, heard=""):
    """Open a record for this turn. Returns it, and it is also the thread's current one.

    `heard` is the transcript as the ear delivered it and `question` is what actually
    arrived at the door. They are recorded SEPARATELY and never reconciled here, because
    the first thing the hunt has to be able to ask is whether they differ - a machine that
    answered a sentence nobody said is the ear's failure and no amount of reading the
    brain's output will find it.
    """
    with _lock:
        n = _turn_seq.get(session, 0) + 1
        _turn_seq[session] = n
    rec = {"n": n, "session": str(session or "default")[:120],
           "at": time.strftime("%H:%M:%S"), "asked": str(question or "")[:2000],
           "heard": str(heard or "")[:2000], "spoken": bool(spoken),
           "kind": "", "route": "", "answer": "", "calls": [], "plan": None,
           # scores is a dict every time it is written (turn_note(scores={...})); it was
           # initialised to [] and that empty list reached grounding_class(), which asks it
           # for .get("opened"). Every slot here now has its written-to type.
           "scores": {}, "cited": [], "sources": [], "chainTag": None, "toolTag": None,
           # WHICH ENGINE SERVED WHICH CAPABILITY, added in §28 as a NEW list rather than as
           # fields on the `calls` rows. Two reasons, and the second is the one that matters:
           # a fallback is not a model call, it is a DECISION about model calls, and a turn
           # that fell back has two calls and one decision; and `calls` already has readers -
           # session_proof and the grounding judge - for whom a new key on every row is a
           # shape change. See turn_engine().
           "engines": [],
           "pending": None, "grounds": ""}
    _turn_local.rec = rec
    return rec


def turn_note(**fields):
    """Add to the open record, if there is one. A no-op off the /chat path.

    Deliberately forgiving: every caller below is a line inside a long function with a
    dozen exits, and an instrument that raised when it was not armed would be an
    instrument that took the server down on the one path nobody tested.
    """
    rec = getattr(_turn_local, "rec", None)
    if rec is not None:
        rec.update(fields)
    return rec


def turn_call(label, messages, raw, error=""):
    """One model call, recorded: what went in, how big, and what came back RAW.

    RAW MATTERS AND IS THE POINT. Everything downstream of call_model strips tags,
    rescues prose and substitutes canned lines, so by the time an answer reaches the
    employer there is no way to tell a model that wrote a clean sentence from one that
    wrote a chain tag on an ordinary question and had it quietly removed. That second
    thing is chain-protocol bleed, it is one of the four mechanisms the hunt must be able
    to see, and this is the only place it is visible.
    """
    rec = getattr(_turn_local, "rec", None)
    if rec is None:
        return
    sizes = [{"role": m.get("role"), "chars": len(str(m.get("content") or ""))}
             for m in messages if isinstance(m, dict)]
    rec["calls"].append({
        "label": label, "msgs": len(sizes),
        "chars": sum(s["chars"] for s in sizes), "sizes": sizes,
        "raw": str(raw or "")[:2000], "error": str(error or "")[:200]})


# THE ENGINE RING. Short on purpose: it is a diagnostic for the last few minutes, not a record,
# and a ledger that grows without bound in a process that runs for weeks is a leak with a nice
# name. No prompt, no transcript, no spoken line and no key goes in - see turn_engine().
_ENGINE_LOG = []
ENGINE_LOG_MAX = 40


def turn_engine(capability, served, outcome, reason="", provider="", trigger_ms=None,
                spoken="", model="", queued=None):
    """One row in the engine ledger: who served this capability, and how it went.

    §41 ADDED FOUR COLUMNS AND ALL FOUR ARE THE SAME ADMISSION: a fallback is invisible by
    design, so every fact about it that is not written here is a fact nobody has.
        provider    which road served - "groq", "ollama", or "retry" when nothing did.
                    Separate from `served` on purpose: `served` is the ENGINE word a
                    harness asserts, `provider` is the road, and §41 wanted both named.
        triggerMs   how long the HANDOVER took, not the answer - see
                    FALLBACK_TRIGGER_BUDGET_MS - with withinBudget computed here so that
                    no reader has to know the number to judge the row.
        spoken      the fixed line the boss actually heard, if any. Never the answer.
        queued      the depth after queueing, on the one row that ever queues.

    `outcome` is one of three words and the vocabulary is closed on purpose:
        "ok"        the engine that was asked answered.
        "failed"    it did not, and nothing else was tried - a missing key, a wrong key, a
                    retired model id. The boss hears a refusal naming the config field.
        "fallback"  it did not, transiently, and today's default for that capability answered
                    instead. EXACTLY ONCE. `reason` carries why, so a week of these can be
                    read as a rate rather than as a mystery.

    WHY A LEDGER AT ALL, when the error is already in the answer: because a fallback is
    invisible by design. It exists so the boss hears one answer rather than an apology, which
    means the ONLY record that Groq was unreachable at four o'clock is this row. A silent
    fallback with no ledger is an engine that can be broken for a month.

    AND IT IS WRITTEN IN TWO PLACES, which is not redundancy. The turn record is the ledger for
    a /chat turn and it is the right home for the chat and vision rows - they happen inside a
    turn, beside the question they belong to. But the voice and the ear do NOT: /say and
    /ear/transcribe are their own requests with no turn open, and turn_engine used to return
    doing nothing at all when there was no rec - which would have made "ledger fallback row
    naming the reason" quietly false for two of the four capabilities, in the two cases where
    the fallback is least visible. So every row also goes into a short ring in this process,
    which /health publishes and a harness can read for any capability.
    """
    row = {"capability": str(capability), "served": str(served),
           "outcome": str(outcome), "reason": str(reason or "")[:200]}
    if provider:
        row["provider"] = str(provider)
    if trigger_ms is not None:
        row["triggerMs"] = round(float(trigger_ms), 1)
        row["withinBudget"] = row["triggerMs"] <= FALLBACK_TRIGGER_BUDGET_MS
    if spoken:
        row["spoken"] = str(spoken)[:120]
    if model:
        row["model"] = str(model)[:80]
    if queued is not None:
        row["queued"] = int(queued)
    if row["outcome"] == "fallback":
        groq_seen("fallback")
    _ENGINE_LOG.append(dict(row, at=time.strftime("%H:%M:%S")))
    while len(_ENGINE_LOG) > ENGINE_LOG_MAX:
        _ENGINE_LOG.pop(0)
    rec = getattr(_turn_local, "rec", None)
    if rec is None:
        return
    rec.setdefault("engines", []).append(row)


# ---- THE GROUNDING CLASS, section 26 PART 3 -------------------------------------------
#
# Every answer carries one of six: notes, web, persona, state, refusal, chain. The class
# names WHAT THE SENTENCE STANDS ON, and the whole reason it exists as a separate field is
# that `kind` does not: kind names the DOOR the question was routed to, and the hunt found
# two turns where the door and the ground disagreed.
#
#   Turn 9, "what is my home address": kind "notes", zero cited passages, and the reading
#     that settles it is opened=false, semOpened=false - NEITHER HALF OF THE RETRIEVAL EVER
#     OPENED. The notes were not consulted and then found wanting; they were never read.
#     The answer ("not a thing the notes record") is a refusal and grounded in an absence.
#   Turn 17, "what did I ask you about first today": kind "notes", nothing opened either,
#     and the answer stood on the summarised-history block that was on the wire. Its ground
#     is this conversation - state - and it was correct.
#
# Both were reds under a rule that read kind, and neither was a hallucination. So:
#
# WHAT THIS FUNCTION WILL AND WILL NOT DECIDE. It decides only the classes the machine can
# prove from its own instruments - a card on the table, a protected class, fetched sources,
# a passage over threshold. Where the class turns on what the SENTENCE claims, it returns
# "" and says nothing, because the alternative is a regex over prose deciding whether an
# English sentence was a refusal, and a classifier that guesses would launder exactly the
# hallucinations this audit exists to catch. "" means THE JUDGE DECIDES, and the judge is
# given the mechanical facts below to decide against - never a free hand.
GROUNDING_CLASSES = ("notes", "web", "persona", "state", "refusal", "chain")


def grounding_class(rec, payload):
    """One of GROUNDING_CLASSES, or "" for "not mechanically decidable - ask the judge"."""
    payload = payload if isinstance(payload, dict) else {}
    scores = rec.get("scores") if isinstance(rec.get("scores"), dict) else {}
    chain, tool = (rec.get("chainTag") or {}), (rec.get("toolTag") or {})
    # A PROPOSAL OF HANDS, whether it is one hand or four. The mandate's class list has no
    # "tool" beside "chain", and a single card is the same claim as a chain of four - that
    # these hands exist and these parameters are valid - so it is judged by the same law.
    if rec.get("pending") or chain.get("accepted") or tool.get("id"):
        return "chain"
    if rec.get("route") in ("identity", "meta"):
        # googleState is set only when spoken_connection() actually read the grant, so it
        # is the existing, untouched signal that separates a live-state answer from one
        # read off the persona block. PROTECTED_CLASSES is fixed at four and stays four.
        return "state" if payload.get("googleState") else "persona"
    if rec.get("kind") == "web":
        return "web" if rec.get("sources") else ""
    if rec.get("cited") or scores.get("opened") or scores.get("semOpened"):
        return "notes"
    return ""


def turn_end(payload):
    """File the open record into the ring, reading what it can off the answer itself."""
    rec = getattr(_turn_local, "rec", None)
    _turn_local.rec = None
    if rec is None:
        return
    if isinstance(payload, dict):
        rec["kind"] = str(payload.get("kind") or "")
        # THE ROUTE IS NOT OVERWRITTEN IF SOMETHING ALREADY KNEW IT. answer_question() records
        # which half of the retrieval opened the door - "semantic" and "keyword" are the
        # distinction the hunt needs and no payload carries it - and the first draft of this
        # line read `or ""` off the payload and erased that on every single turn. A reading
        # taken at decision time beats a reading reconstructed from the reply.
        rec["route"] = str(payload.get("route") or rec.get("route") or "")
        rec["answer"] = str(payload.get("answer") or payload.get("error") or "")[:2000]
        cites = payload.get("citations")
        if isinstance(cites, list) and cites and not rec["cited"]:
            rec["cited"] = [{"what": str(c)[:120]} for c in cites[:8]]
        src = payload.get("sources")
        rec["sources"] = [{"title": str((s or {}).get("title") or "")[:120],
                           "url": str((s or {}).get("url") or "")[:200]}
                          for s in (src if isinstance(src, list) else [])[:8]]
        pend = payload.get("pending")
        if isinstance(pend, dict):
            rec["pending"] = {"tool": pend.get("tool"), "chain": bool(pend.get("chain")),
                              "steps": len(pend.get("steps") or [])}
        # LAST, because it reads everything above it. A site that knew better already wrote
        # grounds via turn_note and is not second-guessed here - the same rule as `route`.
        rec["grounds"] = rec.get("grounds") or grounding_class(rec, payload)
    with _lock:
        _turns.append(rec)
        del _turns[:max(0, len(_turns) - TURN_DUMP_MAX)]
    return rec


def turn_dump(session=None, limit=TURN_DUMP_MAX):
    with _lock:
        rows = [dict(r) for r in _turns
                if session in (None, "", r.get("session"))]
    return rows[-max(1, int(limit or 1)):]


def forget_turns(session=None):
    with _lock:
        if session:
            _turns[:] = [r for r in _turns if r.get("session") != session]
            _turn_seq.pop(session, None)
        else:
            _turns[:] = []
            _turn_seq.clear()


def record_turn(session, question, answer):
    """The conversation grows by one pair, and the oldest pairs are dealt with by RULE.

    ONE FUNCTION, WHERE THERE WERE FIVE COPIES. The five sites that used to hold their own
    `del hist[:max(0, len(hist) - HISTORY_TURNS * 2)]` are all here now, and the reason is
    not tidiness: eviction is a decision about what this machine is allowed to forget, and
    a decision taken in five places is a decision that will shortly be taken differently in
    five places. See evict_history() for the rule itself.
    """
    said = str(question or "").strip()
    with _lock:
        hist = _history.setdefault(session, [])
        hist.append({"role": "user", "content": said})
        hist.append({"role": "assistant", "content": str(answer or "")})
        dropped, summarised = evict_history(hist, session)
    if dropped:
        turn_note(evicted=dropped, summarised=summarised)
    return dropped


def evict_history(hist, session):
    """Trim a session's turns in place. Returns (messages evicted, pairs summarised).

    THE RULE, IN ONE SENTENCE: the last HISTORY_TURNS pairs are kept in full, and everything
    older is SUMMARISED rather than deleted - one line a pair, whole sentences only, with the
    very first pair pinned for the life of the session.

    WHAT IT USED TO DO, AND WHAT THAT COST. It deleted. Five copies of one `del` statement,
    no summary, no record, no mention to the model that anything had gone - and PART 0
    reproduced the consequence on the first attempt. Asked at turn 17 what it had been asked
    FIRST, this machine answered with complete confidence about turn 9, because turn 9 was
    the oldest message still inside the window and nothing in the prompt said there had been
    eight turns before it. The model was not guessing and it was not lying; it answered
    correctly about the only history it was given. THE HISTORY WAS THE LIE, by omission, and
    a machine that cannot say "I no longer hold that" will always say something else instead.

    Called under _lock, and it is the caller's lock: _older is written here too.
    """
    over = max(0, len(hist) - HISTORY_TURNS * 2)
    if not over:
        return 0, 0
    gone = hist[:over]
    del hist[:over]
    return over, summarise_pairs(session, gone)


def assemble(*, system, manifest="", protocol="", guest="", offer="", history=None,
             ask="", heading="", evidence="", older="", label="chat", cap=None):
    """(messages, plan) - the ONE place a prompt is built, in the ONE declared order.

    Every argument is a NAMED BLOCK from CONTEXT_ORDER, and the plan that comes back names
    every one of them with its size, whether it was protected, and whether it is absent
    because nobody had one or absent because something took it away. That distinction is
    the whole value of the return: "the web synthesis has no history" and "the history was
    evicted" look identical in a message list and mean opposite things.

    IT DOES NOT CHOOSE ANYTHING. Which blocks a given turn gets is the caller's judgement
    and stays where it was - the web synthesis deliberately carries no notes and no turns,
    because never blending has to be structural to be true. This function's whole job is to
    put whatever it is given in the declared order, measure it, and say what it did.

    IT DOES ENFORCE THE CAP, which is the one decision it owns. MAX_CONTEXT is a promise
    about the whole prompt and only this function can see the whole prompt, so the trim
    happens here - in reverse precedence order, taking the summary of the old turns first and
    then the recent turns from the oldest end, both of them WHOLE MESSAGES. A protected block
    is never touched and never truncated: if the protected blocks alone are over the cap, the
    plan comes back `overCap` and the log says so, because a prompt that cannot be made to fit
    honestly is a thing to be told about rather than a thing to be quietly cut in half.
    """
    turns = [dict(m) for m in (history or []) if isinstance(m, dict)]
    older = str(older or "")
    cap = int(cap or MAX_CONTEXT)
    # ---- THE TRIM. Measured on the four pieces, not on the assembled string, so that
    # dropping something is one list operation rather than a rebuild.
    fixed = (len(str(system or "")) + (len(manifest) + 1 + len(protocol) if manifest else 0)
             + len(str(offer or "")) + len(str(guest or ""))
             + len("Question: \n\n\n\n") + len(str(ask or "")) + len(str(heading or ""))
             + len(str(evidence or "")))
    turn_chars = lambda: sum(len(str(m.get("content") or "")) for m in turns)  # noqa: E731
    cut_older, cut_turns = 0, 0
    if fixed + len(older) + turn_chars() > cap and older:
        older, cut_older = "", 1
    # OLDEST FIRST, AND IN PAIRS, because dropping a user message and leaving the answer to
    # it turns the window into a monologue by a machine answering nothing.
    while fixed + turn_chars() > cap and len(turns) >= 2:
        del turns[:2]
        cut_turns += 2
    over_cap = fixed + len(older) + turn_chars() > cap
    if cut_older or cut_turns or over_cap:
        sys.stderr.write("  budget: %s cap %d - dropped %s%d recent message(s)%s\n"
                         % (label, cap, "the summary and " if cut_older else "",
                            cut_turns, "; STILL OVER CAP on protected blocks alone"
                            if over_cap else ""))
    hands_block = (manifest + "\n" + protocol) if manifest else ""
    system_text = str(system or "") + hands_block + str(offer or "") + str(guest or "")
    if older:
        system_text += older
    # THE HEADING DECIDES, NOT THE EVIDENCE. A retrieval that came back thin still gets its
    # frame, because "and nothing else" is a sentence about what the model may use and it is
    # most load-bearing exactly when there is least to use. Framing on `evidence` instead
    # would have silently unframed the one turn where the frame matters, so the condition
    # names the heading: a caller that passes one is asking for the frame.
    user_text = ("Question: %s\n\n%s\n\n%s" % (ask, heading, evidence)
                 if (heading or evidence) else str(ask or ""))
    messages = ([{"role": "system", "content": system_text}] + turns +
                [{"role": "user", "content": user_text}])
    # EVERY CHARACTER ON THE WIRE BELONGS TO EXACTLY ONE NAMED BLOCK, and that is a stronger
    # claim than it looks. A budget whose parts do not add up to the whole is a budget with a
    # hiding place in it: the sum comes out under the cap while the thing actually sent does
    # not. So the arithmetic below is exact rather than approximate, and three of the entries
    # are written the way they are only to make it exact:
    #
    #   "persona" carries the BASE PROMPT TOO - SMALLTALK_PROMPT, SYSTEM_PROMPT, WEB_PROMPT,
    #     whichever the caller passed - and not only the preamble wear_persona() adds later.
    #     They are one block because they are one thing: who this machine is and how it
    #     speaks. Splitting them would have produced a nameless eighth block that happened
    #     to be the largest protected one in the file.
    #   "chain-protocol" is charged the newline that joins it to the manifest, because that
    #     newline exists if and only if there is a manifest to join it to.
    #   "question" is measured as WHAT IS LEFT OF THE USER TURN once the evidence is taken
    #     out, so the frame - "Question: ", the heading, the blank lines between them - is
    #     charged to the asking rather than silently dropped. Sixteen characters, and a
    #     sixteen-character hole would have made the identity below inexact forever.
    #
    # The identity: sum(sizes) == systemChars + userChars + recent-turns, asserted in
    # preflight and again in session_proof against the bytes call_model actually sent.
    sizes = {"persona": len(str(system or "")), "manifest": len(manifest or ""),
             "chain-protocol": (len(protocol or "") + 1) if manifest else 0,
             "guest": len(guest or ""),
             "standing-offer": len(offer or ""), "retrieval": len(evidence or ""),
             "recent-turns": sum(len(str(m.get("content") or "")) for m in turns),
             "older-turns": len(older or ""),
             "question": len(user_text) - len(evidence or "")}
    plan = {"label": label, "order": list(CONTEXT_BLOCKS),
            "blocks": [{"block": name, "protected": protected, "where": where,
                        "chars": sizes[name], "present": bool(sizes[name])}
                       for name, protected, where in CONTEXT_ORDER],
            "turns": len(turns), "chars": sum(sizes.values()),
            "systemChars": len(system_text), "userChars": len(user_text),
            # `evicted` here is what THE CAP took off this one prompt, which is a different
            # number from the `evicted` on the turn record - that one is what the WINDOW RULE
            # took off the session's history when the last answer was filed. Two mechanisms,
            # two counts, and conflating them would have made a busy session look like a
            # broken budget. How many pairs the session holds in SUMMARY is a fact about the
            # session rather than about this prompt, so it is on the turn record and not here.
            "evicted": cut_turns + cut_older, "droppedSummary": bool(cut_older),
            "cap": cap, "overCap": over_cap, "floor": CONTEXT_FLOOR}
    turn_note(plan=plan)
    return messages, plan

# THE MEMORY: one question back, and what kind of thing it turned out to be. That is the
# whole of it, and the smallness is the point - the only reader is resolve_followup(),
# which needs a subject to lend to a pronoun and nothing else.
#
# The KIND is in here because a subject is not the only thing a predecessor can lack.
# "good morning" is a remembered question too, and lending its words to "who created it?"
# would invent a question rather than complete one, so only "notes" and "web" are ever
# borrowed from.
#
# One slot, not a dict keyed by session: this is the last thing said to this machine, in
# the same sense that the notes are its notes, and a per-session copy would make the same
# follow-up mean different things in two tabs of the same browser. It is written by the
# /chat door, once, with the kind the answer actually came back as - and cleared by the
# forget button, which has to clear everything or it is not a forget button.
_last_ask = {"question": "", "kind": ""}


def remember_ask(question, kind):
    with _lock:
        _last_ask["question"] = str(question or "").strip()[:2000]
        _last_ask["kind"] = str(kind or "")


# Which acknowledgment comes next. One integer, under the same lock as everything else
# that is one-of, so that two tabs acknowledging at once still get two different lines.
_ack_turn = [0]


def next_backchannel():
    """The next butler acknowledgment, in order, forever."""
    with _lock:
        line = BACKCHANNEL_LINES[_ack_turn[0] % len(BACKCHANNEL_LINES)]
        _ack_turn[0] += 1
    return line


def recall_ask():
    with _lock:
        return _last_ask["question"], _last_ask["kind"]


def forget_ask():
    with _lock:
        _last_ask["question"] = ""
        _last_ask["kind"] = ""


def load_config(apply_override=True):
    """Read config.json fresh every time; create it with placeholders if absent.

    apply_override=False reads the file as it stands, which is the brain a restart
    would bring back - the chip shows it, and nothing else needs it.
    """
    if not os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "w", encoding="utf-8") as fh:
            json.dump(DEFAULT_CONFIG, fh, indent=2)
            fh.write("\n")
        print("server.py: created config.json with placeholder values")
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as fh:
            cfg = json.load(fh)
        if not isinstance(cfg, dict):
            raise ValueError("config.json must contain a JSON object")
    except Exception as exc:                                   # noqa: BLE001
        return dict(DEFAULT_CONFIG), "config.json could not be read (%s)" % exc
    merged = dict(DEFAULT_CONFIG)
    merged.update({k: v for k, v in cfg.items() if v is not None})
    # What it answers to, refreshed here because this is the one funnel every request
    # passes through. A rename in config.json is honoured by the next question.
    set_vocatives(merged.get("assistant_names"))
    # The runtime brain swap is applied HERE, in the one function every request path
    # already goes through, so /chat, /see, /health and the model chip cannot end up
    # disagreeing about which brain is in play. Note what is not happening: the file
    # on disk is untouched, so this override dies with the process.
    with _brain_lock:
        brain = _brain if apply_override else None
        engine = _chat_engine if apply_override else None
    if brain:
        merged["provider"] = "openrouter"
        merged["openrouter_model"] = brain
    # AND THE PROVIDER SWAP, applied in the same funnel for the same reason: /chat, /see,
    # /health, /say and the model chip all read config through here, so they cannot end up
    # disagreeing about which engine is in play. Nothing is written to disk, so a restart
    # returns to whatever config.json says - which is the definition of "zero residue" this
    # server has always used and the one the harness asserts.
    elif engine == "groq":
        merged["provider"] = "groq"
    # AND THE OTHER THREE ENGINES, in the same funnel and for the same reason. Read under the
    # same lock and applied one field each: an override of None leaves config.json's own answer
    # exactly as it was, so a house with no overrides set merges byte-identically to the way it
    # did before any of this existed. THE FAILURE MODE: applying these anywhere but here, and
    # having /health say "groq" while the route that serves the audio reads "piper" off the
    # file - two truths about one engine, and the seal painting the wrong one.
    if apply_override:
        with _brain_lock:
            over = dict(_engines)
        if over.get("ear"):
            merged["ear_stt"] = over["ear"]
        if over.get("vision"):
            merged["vision_engine"] = over["vision"]
        if over.get("voice"):
            merged["voice_engine"] = over["voice"]
    return merged, None


def _number(value, fallback):
    """A number out of config.json, or the default. A typo is never an exception.

    Every setting in that file was typed by a human, and "45 seconds" is a thing
    somebody will one day write as "45s". The caller clamps; this only promises to hand
    back something arithmetic will accept.
    """
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return float(fallback)


def tokenize(text):
    return [t for t in TOKEN_RE.findall(str(text).lower())
            if len(t) > 2 and t not in STOPWORDS]


def ensure_index():
    """Load notes-index.json, rebuilding it if missing and reloading if changed."""
    if not os.path.exists(INDEX_PATH):
        print("server.py: notes-index.json missing - running build.py")
        try:
            sys.argv = sys.argv[:1]
            build.main()
        except SystemExit as exc:
            print("server.py: build.py said: %s" % exc)
        except Exception as exc:                               # noqa: BLE001
            print("server.py: could not run build.py automatically (%s)" % exc)
        if not os.path.exists(INDEX_PATH):
            return

    mtime = os.path.getmtime(INDEX_PATH)
    with _lock:
        if mtime == _index["mtime"] and _index["notes"]:
            return
    try:
        with open(INDEX_PATH, "r", encoding="utf-8") as fh:
            payload = json.load(fh)
    except Exception as exc:                                   # noqa: BLE001
        print("server.py: could not read notes-index.json (%s)" % exc)
        return

    notes = payload.get("notes", [])
    docs, df = [], {}
    for note in notes:
        title_tokens = set(tokenize(note.get("label", "")) +
                           tokenize(note.get("group", "")))
        body_counts = {}
        for tok in tokenize(note.get("text", "")):
            body_counts[tok] = body_counts.get(tok, 0) + 1
        docs.append({
            "title": title_tokens,
            "body": body_counts,
            "text_lower": (note.get("text") or "").lower(),
        })
        for tok in set(body_counts) | title_tokens:
            df[tok] = df.get(tok, 0) + 1

    with _lock:
        _index["notes"] = notes
        _index["docs"] = docs
        _index["df"] = df
        _index["meta"] = payload.get("meta", {})
        _index["mtime"] = mtime
    print("server.py: brain loaded %d notes" % len(notes))


# ------------------------------------------------------------------- retrieval

def score_notes(question, prior="", top_k=TOP_K, skip=()):
    """Keyword overlap with title matches weighted higher. Returns [(id, score)].

    `prior` is the previous question in this conversation, scored at a fraction of
    the weight so that a bare follow-up ("why not?") still lands on the right notes.

    `skip` excludes notes before the relative score floor is applied, which is what
    lets a fresh capture ask "which existing note am I most like?" - scored against
    it, the capture itself always wins and would trim away every real answer.
    """
    notes, docs, df = _index["notes"], _index["docs"], _index["df"]
    total = len(notes)
    if not total:
        return []

    q_unique = list(dict.fromkeys(tokenize(question)))
    seen = set(q_unique)
    terms = [(tok, 1.0) for tok in q_unique]
    terms += [(tok, PRIOR_WEIGHT) for tok in dict.fromkeys(tokenize(prior))
              if tok not in seen]
    q_phrase = " ".join(re.findall(r"[a-z0-9']+", question.lower()))

    scored = []
    for i, doc in enumerate(docs):
        if i in skip:
            continue
        score = 0.0
        overlap = 0
        for tok, w in terms:
            idf = math.log(1.0 + total / (1.0 + df.get(tok, 0)))
            if tok in doc["title"]:
                score += w * TITLE_WEIGHT * idf
                overlap += 1
            tf = doc["body"].get(tok, 0)
            if tf:
                score += w * (1.0 + math.log(tf)) * idf
                overlap += 1
        if overlap > 1:
            score *= 1.0 + 0.06 * min(overlap, 10)    # reward broader overlap
        if len(q_phrase) >= 10 and q_phrase in doc["text_lower"]:
            score += 6.0                              # exact phrase in the note
        scored.append((i, score))

    scored.sort(key=lambda pair: (-pair[1], pair[0]))
    matched = [pair for pair in scored if pair[1] > 0][:top_k]
    if matched:
        # Drop the weak tail. The returned indexes are what the viewer points the
        # camera at, so they have to mean "this note contributed", not "this note
        # was in the top six".
        floor = matched[0][1] * SCORE_FLOOR_RATIO
        return [pair for pair in matched if pair[1] >= floor]
    # Nothing overlapped at all: hand over the meatiest notes so the model has
    # something concrete to point at while saying the notes do not cover this.
    fallback = sorted((i for i in range(total) if i not in skip),
                      key=lambda i: -len(docs[i]["text_lower"]))
    return [(i, 0.0) for i in fallback[:top_k]]


def note_confidence(question, picked, prior=""):
    """How much of the QUESTION the collection actually holds. 0..1, and it means it.

    The fraction of the question's own content words that a retrieved note contains -
    the one number the web gate turns on, and the reason that gate can now be argued
    about in words: "a quarter of what you asked, or the notes do not answer it".

    Two details in here are deliberate, and both exist because the plain fraction, tried
    first, got the employer's own examples wrong:

    WEIGHTED BY HOW RARE THE WORD IS, so that a match on a word the corpus uses
    everywhere is not worth the same as a match on the word the question is ABOUT.
    "Who was the first Sikh PM of India" has three content words; thirteen of thirty
    notes happen to contain "first", so the unweighted fraction is 0.33 and the gate
    stays shut on the strength of a word nobody asked about. Weighted, "first" is worth
    a sixth of the question and the score is 0.14 - a loss, which is the right answer.
    Equal-idf words give exactly the plain fraction back, so the arithmetic above still
    reads as it should.

    THE BEST OF THE RETRIEVED NOTES, not strictly the top-scoring one. Ask "what do the
    notes say about roasting" and the raw score puts a note called "Subscription Churn
    NOTES" first - it wins on the word "notes" in its title - while the note that
    actually covers the question is third. Measuring only the winner would make the
    gate depend on a scoring artefact and would refuse a question the collection
    answers perfectly well. The claim being tested is "can the notes answer this",
    and that is a claim about the collection, not about one row of it.

    `prior` is the previous question, used only when this one has no content words of
    its own: a bare follow-up ("why not?") is measured against what it is following up.
    """
    docs, df = _index["docs"], _index["df"]
    total = len(_index["notes"])
    if not picked or not total:
        return 0.0
    words = list(dict.fromkeys(tokenize(question))) or \
        list(dict.fromkeys(tokenize(prior)))
    if not words:
        return 0.0
    weight = {tok: math.log(1.0 + total / (1.0 + df.get(tok, 0))) for tok in words}
    whole = sum(weight.values())
    if whole <= 0:
        return 0.0
    best = 0.0
    for i, _score in picked:
        if not 0 <= i < len(docs):
            continue
        doc = docs[i]
        held = sum(w for tok, w in weight.items()
                   if tok in doc["title"] or tok in doc["body"])
        best = max(best, held / whole)
    return best


def build_context(picked):
    notes = _index["notes"]
    blocks = []
    for rank, (i, score) in enumerate(picked, start=1):
        note = notes[i]
        text = (note.get("text") or note.get("excerpt") or "").strip()
        if len(text) > CONTEXT_CHARS:
            text = text[:CONTEXT_CHARS].rsplit(" ", 1)[0] + "…"
        blocks.append("NOTE %d\nTitle: %s\nFolder: %s\nContent: %s"
                      % (rank, note.get("label", "untitled"),
                         note.get("group", "unfiled"), text))
    return "\n\n".join(blocks)


# ------------------------------------------------------- retrieval, by meaning
#
#  THE SECOND RETRIEVAL, and it stands BESIDE the keyword one rather than over it.
#
#  Two questions get two different answers, and both are worth having. score_notes()
#  above asks "which notes use these words?", which is unbeatable when the employer
#  types a word that is genuinely in the file - a name, a number, a canary token
#  written thirty seconds ago and not yet embedded. recall() in ingest.py asks "which
#  passages MEAN this?", which is the only one that can answer "what colour is the
#  car?" out of a contract that says "the vehicle is crimson".
#
#  So the union is the design, not a compromise:
#    - either retrieval may open the notes door;
#    - the model is shown what each of them found, labelled;
#    - the chips light for notes that actually contributed, from either side.
#  A note captured by /remember is findable in the same second by the keyword half
#  with no rebuild, and an archived PDF nobody has ever wikilinked is findable by the
#  semantic half. Neither of those two facts is true of either index alone.

# SEM_CONTEXT_CHARS lives up with CONTEXT_CHARS now - CONTEXT_FLOOR sums the two and is
# declared above this line, so both have to exist before it.


# THE LOOKUP COUNTER, and it counts only what is actually SPENT: an embedding query put to
# a model, and a search put to the web. Keyword scoring is arithmetic over an index this
# machine already holds and is not a lookup in the sense that matters here - nothing leaves
# the room and nothing is paid for.
#
# It exists so that "zero lookups" can be a measurement instead of a promise. routing_proof
# reads the number off the reply for each of the boss's own sentences, which is the only way
# to tell an answer that was cheap from an answer that was merely quick: a protected class
# that quietly started searching again would still answer, in character, in good time.
_LOOKUPS = {"n": 0}


def _spent(what):
    with _lock:
        _LOOKUPS["n"] += 1
        return _LOOKUPS["n"]


def lookups_so_far():
    with _lock:
        return _LOOKUPS["n"]


def semantic_recall(question, prior=""):
    """ingest.recall(), wrapped so that this file never has to ask whether it exists.

    Returns the same shape whether the module imported, the store is there, or Ollama is
    stopped: the caller reads .get("opens") and .get("cited") and does not branch on
    which kind of missing it is. One place to look when semantic recall is not
    happening, and one line in the log saying why.
    """
    if ingest is None:
        return {"available": False, "why": "ingest.py did not import", "opens": False,
                "hits": [], "cited": [], "best": 0.0, "best3": 0.0, "scans": [],
                "threshold": 0.0, "ms": 0}
    try:
        _spent("embed")
        return ingest.recall(question, prior)
    except Exception as exc:                                   # noqa: BLE001
        # recall() promises not to raise. If it ever does, that is a bug in it and not a
        # reason to fail a question, so it is logged as loudly as a bug deserves.
        sys.stderr.write("  recall: ingest.recall() RAISED %s: %s - falling back to "
                         "keywords\n" % (type(exc).__name__, exc))
        return {"available": False, "why": "recall raised %s" % type(exc).__name__,
                "opens": False, "hits": [], "cited": [], "best": 0.0, "best3": 0.0,
                "scans": [], "threshold": 0.0, "ms": 0}


def notes_by_file():
    """{"notes/finance/pricing-strategy.md": 3} - the file-to-planet map, built fresh.

    Cheap enough to build per question (thirty-odd string keys) and always right, which
    a cached copy would not be: /remember adds a note mid-session and the next question
    has to be able to light it.
    """
    out = {}
    for i, note in enumerate(_index["notes"]):
        rel = str(note.get("file") or "").replace("\\", "/")
        if rel:
            out.setdefault(rel, int(note.get("id", i)))
    return out


def semantic_nodes(cited):
    """Which PLANETS a set of cited chunks corresponds to, in citation order.

    A chunk from notes/product/cold-brew-recipe.md is a planet and lights one. A chunk
    from archive/Q3_Contract.pdf is not in the galaxy at all, and gets no node - which
    is why the citation chips exist. Returning nothing for it is the honest answer:
    there is no star to fly to, and inventing one would put a dot in the sky for a file
    the graph has never contained.
    """
    by_file = notes_by_file()
    out = []
    for hit in cited:
        node = by_file.get(str(hit.get("file") or "").replace("\\", "/"))
        if node is not None and node not in out:
            out.append(node)
    return out


def build_semantic_context(cited):
    """The retrieved PASSAGES, as the model sees them: file, page, text.

    Labelled PASSAGE rather than NOTE, and numbered separately from build_context()'s
    blocks, because the two are different kinds of evidence and the difference is worth
    the model knowing: a NOTE block is a whole note, a PASSAGE block is the part of a
    longer document that actually matched. The page number is in the block so that an
    answer can say where in the file it read something - the one thing a citation to a
    forty-page PDF has to be able to do.
    """
    blocks = []
    for rank, hit in enumerate(cited, start=1):
        text = (hit.get("text") or "").strip()
        if len(text) > SEM_CONTEXT_CHARS:
            text = text[:SEM_CONTEXT_CHARS].rsplit(" ", 1)[0] + "…"
        where = ingest.cite_label(hit) if ingest else (hit.get("name") or "")
        blocks.append("PASSAGE %d\nFrom: %s\nContent: %s" % (rank, where, text))
    return "\n\n".join(blocks)


def scan_lines(sem):
    """The honest line about an image-only page, or nothing at all.

    NEVER GENERATED, ALWAYS QUOTED. ingest.SCAN_LINE is a constant with a page number in
    it, and it is appended to the answer by this file rather than described to the model
    in a prompt. The difference is the whole point: a model told "page 4 is a scan you
    cannot read" will, perhaps one time in thirty, write a sentence about what is
    probably on it. A constant cannot.
    """
    out = []
    for scan in (sem.get("scans") or [])[:2]:
        line = str(scan.get("line") or "")
        if line and line not in out:
            out.append(line)
    return out


def vector_state(cfg):
    """The /health block for the second index - and it never raises either.

    /health is the endpoint the boot banner, the harnesses and the model chip all read,
    so it may not be the thing that a missing package takes down. Absent chromadb, absent
    Ollama, a store somebody deleted while the server was running: all of them come back
    as `ready: false` plus one sentence, and the rest of the probe is unaffected.
    """
    if ingest is None:
        return {"on": False, "ready": False, "why": "ingest.py could not be imported"}
    try:
        state = ingest.store_state()
    except Exception as exc:                                       # noqa: BLE001
        return {"on": bool(cfg.get("vector_recall", True)), "ready": False,
                "why": "%s: %s" % (type(exc).__name__, exc)}
    return state


# Backend names search.py is allowed to have answered with. The name is reported to the
# browser, so it is checked against a fixed vocabulary rather than passed through - the
# same rule every other string that crosses that line already follows.
WEB_BACKENDS = ("tavily", "searxng", "ddg-lite", "ddg-html", "wikipedia")


def build_web_context(results):
    """The snippets, as the model sees them: title, host, text. No full URLs.

    The host is there so the butler can say "according to Reuters"; the full address is
    withheld on purpose, because a model holding a URL will eventually type one out,
    and a URL that has been through a language model is no longer a citation. The links
    the page shows come from search.py's own results and never from the answer.
    """
    blocks = ["Fetched from the live web just now, %s."
              % time.strftime("%Y-%m-%d %H:%M")]
    for rank, item in enumerate(results, start=1):
        blocks.append("RESULT %d\nTitle: %s\nSource: %s\nSnippet: %s"
                      % (rank, item.get("title") or "untitled",
                         item.get("host") or "unknown",
                         (item.get("snippet") or "").strip()))
    return "\n\n".join(blocks)


def web_sources(results):
    """What the BROWSER is told: a title and a URL per result, and nothing else.

    A copy-through over a two-key whitelist, like public_state() in focus.py, so that
    adding a field to search.py cannot quietly widen what the page receives. The
    snippet, the host and the backend stay on this side of the wall.
    """
    out = []
    for item in results:
        url = str(item.get("url") or "")
        if not url.startswith(("http://", "https://")):
            continue               # never hand the page something it cannot open
        out.append({"title": str(item.get("title") or url)[:140], "url": url[:500]})
    return out


# THE PLACEHOLDER TEST, which outlives the credential resolver that introduced it: three
# other callers below ask "is this field really filled in" and a config.json shipped with
# PUT-YOUR-KEY-HERE in it is not configuration. Kept here, where they already look for it.
def _blank(value):
    text = str(value or "").strip()
    return not text or text.upper().startswith("PUT-")


# --------------------------------------------------------------------- the model

def provider_of(cfg):
    name = str(cfg.get("provider") or DEFAULT_CONFIG["provider"]).strip().lower()
    if name in ("openrouter", "open router", "router", "or"):
        return "openrouter"
    if name in ("groq", "groqcloud", "groq cloud"):
        return "groq"
    # §41 - AND ANYTHING UNRECOGNISED, INCLUDING A LEFTOVER "bedrock" IN
    # config.json, NOW MEANS GROQ: the free road with the local net under it.
    return "openai" if name in ("openai", "oai", "gpt") else "groq"


def ear_stt_of(cfg):
    """"browser" or "groq", read charitably, defaulting to the browser's own ear.

    THE DEFAULT IS THE ANSWER TO A TYPO. An unrecognised word means the browser, because the
    browser's ear is the one that works with no key and no network round trip, and a flag
    misspelt in config.json must not be able to send an utterance somewhere it was not asked
    to go. The failure mode named: "ear_stt": "grok" quietly transcribing nothing.
    """
    name = str(cfg.get("ear_stt") or DEFAULT_CONFIG["ear_stt"]).strip().lower()
    return "groq" if name in ("groq", "whisper", "groq-whisper", "cloud") else "browser"


def vision_engine_of(cfg):
    """§41 left the eyes one answer; every spelling resolves to Groq."""
    return "groq"


def groq_key(cfg):
    """The key as a string, stripped, or "" - and placeholders count as absent."""
    key = str(cfg.get("groq_api_key") or "").strip()
    return "" if key.lower() in PLACEHOLDER_KEYS else key


def groq_digest(cfg):
    """THE ONLY THING THIS PROCESS WILL EVER SAY ABOUT THE KEY: a length and a digest.

    Returned as a dict of exactly three facts - present, length, sha256 prefix - because every
    surface that wants to talk about the key (the /health block, the harness, the lookbook)
    wants the same three and none of them may have the fourth. A digest is not reversible and
    a length is not a secret; the value never leaves this function's caller in any other form.
    FAILURE MODE THIS NAMES: a "just for debugging" line printing the first eight characters,
    which for most key formats is the account prefix and for all of them is eight characters
    more than anybody needed.
    """
    key = groq_key(cfg)
    return {"present": bool(key), "length": len(key),
            "sha256": hashlib.sha256(key.encode("utf-8")).hexdigest()[:12] if key else ""}


def groq_ready(cfg):
    """(True, "") when Groq is callable, else (False, one plain sentence naming the field).

    THE SENTENCE NAMES THE CONFIG FIELD AND NOT THE CONCEPT. "No Groq key" tells the boss he
    has a problem; "groq_api_key in config.json is empty" tells him where his hands go. That
    is the difference between a refusal and a support ticket.
    """
    if not groq_key(cfg):
        return False, ("There is no Groq key, sir: \"groq_api_key\" in config.json is empty. "
                       "Paste one in and ask again - no restart needed - or leave the flags "
                       "as they are and I shall carry on as I was.")
    return True, ""


def display_label(model_id):
    """A model id as it should be read aloud or shown on the chip.

    ONE rule about digits, and it is the whole reason this is a function: a hyphen
    with a digit on either side is a version dot, and every other hyphen is a word
    gap. So "fable-5-1" is FABLE 5.1 while "gpt-6-astra" is GPT 6 ASTRA - not GPT
    6.ASTRA, and not FABLE 5 1.
    """
    name = str(model_id or "").split("/")[-1]
    name = re.sub(r"^(?:us|eu|apac)\.", "", name, flags=re.I)      # a regional prefix
    name = re.sub(r"^(?:anthropic|amazon|meta|mistral|openai|google)\.", "", name,
                  flags=re.I)
    name = re.sub(r"^claude-", "", name, flags=re.I)
    # A vendor tail: a date stamp and a "-v1:0", stripped before the digit rule so
    # that "haiku-4-5-20251001-v1:0" cannot come out as HAIKU 4.5.20251001.
    name = re.sub(r"-v\d+:\d+$", "", name)
    name = re.sub(r"-\d{8}$", "", name)
    name = re.sub(r"(?<=\d)-(?=\d)", ".", name)                    # the one rule
    # Hyphens and underscores only: a dot here is a version dot, either one this
    # function just made or one the id was born with, and both must survive.
    return re.sub(r"[-_]+", " ", name).strip().upper()


def model_label(cfg):
    """Whichever model id is actually in play, for /health and the boot banner."""
    if provider_of(cfg) == "openrouter":
        return str(cfg.get("openrouter_model") or DEFAULT_CONFIG["openrouter_model"])
    if provider_of(cfg) == "openai":
        return str(cfg.get("model") or DEFAULT_CONFIG["model"])
    return str(cfg.get("groq_model") or DEFAULT_CONFIG["groq_model"])


def voice_engine_of(cfg):
    """"piper" or "web", from config.json, with every other spelling read charitably.

    Only two answers exist because the page only has two paths, and an unrecognised
    word must not silence the assistant: anything that is not plainly the browser's
    engine means the local one, and the local one already degrades to the browser by
    itself when this machine cannot run it.
    """
    name = str(cfg.get("voice_engine") or DEFAULT_CONFIG["voice_engine"]).strip().lower()
    if name in ("web", "browser", "speechsynthesis", "system", "off", "none"):
        return "web"
    # THE THIRD ANSWER, ADDED IN §28. The docstring above says "only two answers exist because
    # the page only has two paths", and that is still true: Orpheus rides the SERVED path, the
    # one Piper already uses, because the page fetches WAV bytes from /say and has no idea who
    # made them. So the page still has two paths and this function now names three engines -
    # see `served` in voice_state(), which is the boolean the page actually branches on.
    # Why that shape rather than a fourth path in the page: the Piper FIFO, the chime ducking,
    # the ear reset, the face's chunk timing and the caption are all downstream of those bytes.
    # A second audio path would be a second copy of every one of those contracts.
    if name in ("orpheus", "groq", "canopy", "canopylabs"):
        return "orpheus"
    return "piper"


def voice_state(cfg):
    """What the page needs to know about the local voice before it speaks a word.

    Booleans, a model NAME and two numbers - the same discipline as the "web" block
    above, for the same reason. Asked on /health and again in the body of a 503 from
    /say, so that "the local voice is unavailable" always arrives with its sentence.
    """
    engine = voice_engine_of(cfg)
    state = say.ready(cfg.get("voice_model") or DEFAULT_CONFIG["voice_model"])
    files, size = say.cache_size()
    orpheus, orpheusWhy = groq_ready(cfg) if engine == "orpheus" else (False, "")
    return {
        "engine": engine,
        # WHICH MODEL IS SPEAKING, and for Orpheus that is a Groq slug rather than a file on
        # this disk. The seal reads this, so it has to be the truth about the voice actually
        # serving and not the name of the Piper model sitting unused in voices/.
        "model": (str(cfg.get("groq_tts_model") or DEFAULT_CONFIG["groq_tts_model"])
                  if engine == "orpheus" else state["model"]),
        "voice": (str(cfg.get("groq_tts_voice") or DEFAULT_CONFIG["groq_tts_voice"])
                  if engine == "orpheus" else state["model"]),
        "installed": state["binary"],
        "modelPresent": state["model_file"],
        # The question the page actually asks: can I fetch audio from /say? Wanting the
        # web engine is a "no" just as firmly as a missing binary is.
        # `served` IS THAT QUESTION AND `ready` IS NOW ITS ANSWER FOR TWO ENGINES. Kept as
        # separate fields because the page has one line that decides where chunks go, and a
        # boolean it can read is one edit there instead of a growing list of engine names -
        # the next served engine changes this function and nothing in the page.
        "served": engine in ("piper", "orpheus"),
        "ready": ((engine == "piper" and state["ready"])
                  or (engine == "orpheus" and orpheus)),
        "why": (state["why"] if engine == "piper"
                else orpheusWhy if engine == "orpheus"
                else "config.json asks for the browser's voices"),
        "lengthScale": state["lengthScale"],
        "noiseScale": state["noiseScale"],
        "cacheFiles": files,
        "cacheBytes": size,
    }


# ================== THE DOORMAN'S STATE, AND THE ONE SLOT IT REMEMBERS =======================
#
# THE SLOT IS WHY THE PAGE CANNOT LIE. POST /speaker {cmd:"identify"} embeds an utterance and
# writes its verdict in here under a turn number that THIS process issued. /chat's Hands gate
# then reads the verdict out of here by that number. The page carries the number and nothing
# else - no name, no privilege, no score - so the most a stale or hostile tab can do is quote a
# verdict the server itself reached from real audio, which is precisely the thing a voiceprint
# is for. Forging a yes would require forging the boss's larynx.
#
# IT HOLDS ONE TURN PER SESSION AND IT EXPIRES. A verdict is a statement about who was in the
# room a moment ago, and a moment is all it is allowed to be worth: SPEAKER_TURN_TTL_S is
# deliberately shorter than the Hands proposal's own lifetime, so a yes must be spoken by
# somebody who is still there rather than inherited from whoever last used the room.
#
# AND NOTHING IN HERE IS A WORD. The slot carries a name, a privilege, a score and a time. No
# transcript, no audio, no embedding - an embedding in RAM per turn is the mandate's law, and
# the law is kept by the embedding dying inside identify() with the samples that made it.
SPEAKER_TURN_TTL_S = 45.0
# Three sentences of 16 kHz 16-bit mono - which is what scribeWav() builds - run about 200 KB
# for a whole enrolment. 8 MB is the Scribe's own ceiling and the same reasoning: large enough
# that nothing a cooperative page sends is ever refused, small enough that a runaway recorder
# is refused in one sentence rather than filling this process's memory.
SPEAKER_MAX_BYTES = 8 * 1024 * 1024
_SPEAKER_SLOTS = {}
_SPEAKER_LOCK = threading.Lock()
_SPEAKER_SEQ = [0]
# COUNTS ONLY, and this is the Scribe's privacy law applied to the ear: the ledger, the
# lookbook and the logs may know HOW MANY turns were the boss and how many were guests, and
# may never know which sentence was which. Nothing below this line ever holds a name.
_SPEAKER_SEEN = {"turns": 0, "boss": 0, "known": 0, "guests": 0, "refused": 0,
                 "embedMs": 0, "audioSeconds": 0.0}


def speaker_state():
    """The doorman, described in booleans, names and counts - never in names of what was said.

    Published on /health for the same reason scribe_state() is: the page has to know before it
    offers Learn a voice, because a machine with no model must say so in a sentence rather than
    take three spoken sentences off somebody and then discover there is nowhere to put them.

    `hasHands` IS THE WHOLE OF THE LAW'S SWITCH. With it false the doorman stands down
    silently and the gate behaves exactly as it did before this section existed.
    """
    if voiceprint is None:
        return {"installed": False, "ready": False, "enrolled": [], "count": 0,
                "hasHands": False, "keepsAudio": False, "dim": 0, "threshold": 0,
                "why": "voiceprint is not importable in this server process",
                "seen": dict(_SPEAKER_SEEN)}
    try:
        ready = voiceprint.model_ready()
        rows = voiceprint.enrolled()
    except Exception as exc:                                   # noqa: BLE001
        return {"installed": True, "ready": False, "enrolled": [], "count": 0,
                "hasHands": False, "keepsAudio": False, "dim": voiceprint.EMB_DIM,
                "threshold": voiceprint.MATCH_THRESHOLD,
                "why": "the store could not be read: %s" % type(exc).__name__,
                "seen": dict(_SPEAKER_SEEN)}
    return {
        "installed": True, "ready": ready,
        # THE ROSTER CARRIES NO EMBEDDING. The page needs four facts to draw the row - who,
        # how they are addressed, whether they may use the hands, and when they enrolled - and
        # the 192 floats are not one of them. Sending them would put biometric data on a wire
        # that has no reason to carry it, and would let a page do the comparing.
        "enrolled": [{"name": r["name"], "addressForm": r["address_form"],
                      "hands": r["hands"], "at": r["at"], "seconds": r["seconds"],
                      "sentences": r["sentences"]} for r in rows],
        "count": len(rows),
        "hasHands": any(r["hands"] for r in rows),
        "keepsAudio": False,
        "dim": voiceprint.EMB_DIM,
        "threshold": voiceprint.MATCH_THRESHOLD,
        "minSeconds": voiceprint.ENROL_MIN_SECONDS,
        "minSentences": voiceprint.ENROL_MIN_SENTENCES,
        # THE NAME THE FIRST ROW GETS, and it is sent because the alternative is worse. The
        # Command Panel has no text field - this deck has one input and it is the summoned
        # question line - so a page asked to enrol the boss has to get his name from the one
        # place it is written down, which is the persona block in config.json. It is a form of
        # address and not a credential: it is already in every greeting this server composes
        # and in the fallback greeting inside the page itself.
        "bossCall": persona(load_config()[0])["boss_call"],
        "why": "" if ready else ("the model file is not on disk at %s"
                                 % voiceprint.MODEL_PATH.name),
        "seen": dict(_SPEAKER_SEEN),
    }


def boss_call_slug(cfg=None):
    """The slug of the name the persona block calls the boss, or "" if there is none.

    Slugged through voiceprint.slug() and not lowercased here, because the string this is
    compared against is a voiceprint row's `name`, and that row's file on disk is named by
    exactly this function - "Aditya", "aditya" and "Aditya " are one person to the store and
    have to be one person to the promotion below.
    """
    if voiceprint is None:
        return ""
    try:
        cfg = cfg if isinstance(cfg, dict) else load_config()[0]
        want = str(persona(cfg).get("boss_call") or "")
        return voiceprint.slug(want) if want.strip() else ""
    except Exception:                                              # noqa: BLE001
        return ""


# COUNTS ONLY, like every other ledger in this section: how many verdicts the house promoted
# and which name it is promoting on - the name is already on /health in `enrolled` and in
# `bossCall`, so this adds no fact the page did not have.
_BOSS_BY_NAME = {"promoted": 0}


def boss_by_name(verdict):
    """Promote the voice the HOUSE calls the boss to the hands privilege. Mutates and returns.

    §36 PART 1's ROOT CAUSE, and it is a roster fault wearing a seal fault's clothes. The gate
    lends BOSS from seal_for(), which reads BOSS only when the matched row carries `hands`.
    This machine's store holds two rows for one man - `Addi` with hands, enrolled first, and
    `Aditya` without, enrolled later - while the persona block's boss_call is `Aditya`. So his
    live voice matched the row the house addresses him by, sealed his NAME rather than BOSS,
    handshake_open()'s literal "BOSS" guard refused to open a window for the very person it
    exists for, and the spoken "yes" that followed an open gate was sealed GUEST. 104 seconds
    of window remained on the boss's screenshot and not one of them could ever have helped.

    SO THE INHERITANCE IS APPLIED HERE, WHICH IS BEFORE THE SEAL IS FINALISED AND PUBLISHED.
    This runs inside _speaker_remember(), the one funnel every verdict passes through, and it
    mutates the dict rather than copying it - deliberately, and this is the whole point of the
    placement. /speaker cmd=identify computes `seal = seal_for(verdict)` on the NEXT line and
    sends it to the page, the same object is what goes into the session slot that the gate and
    doorman_refusal() later read, and the chip is painted from that reply. One promotion, one
    object, so the chip, the ledger row and the gate decision cannot disagree. Promoting at
    the gate instead - which is where it is discovered - would seal the chip ADITYA and admit
    the order anyway, which is exactly the pair of screenshots this fixes.

    WHAT IT WILL NOT DO: it never promotes a GUEST or an unknown voice, because there is no
    name to compare; it never DEMOTES a row that has hands; and it reads the name from the
    persona block, not from the body, so a tab cannot nominate itself. The privilege is still
    a measured voiceprint match above threshold - this only stops the house from refusing the
    one name it greets him by. The failure mode it accepts, named: enrol somebody else under
    the boss_call name and they get the hands. That is the same trust the roster already has.
    """
    if not isinstance(verdict, dict) or verdict.get("hands"):
        return verdict
    who = verdict.get("who")
    if who in (None, "", "GUEST"):
        return verdict
    want = boss_call_slug()
    if not want:
        return verdict
    try:
        mine = voiceprint.slug(str(who))
    except Exception:                                              # noqa: BLE001
        return verdict
    if mine != want:
        return verdict
    verdict["hands"] = True
    verdict["bossByName"] = True
    sys.stderr.write("  speaker: hands by name - the house calls its boss %s and this row "
                     "carried none\n" % want)
    return verdict


def _speaker_remember(session, verdict):
    """Write a verdict into the session's one slot and return its turn number."""
    verdict = boss_by_name(verdict)
    with _SPEAKER_LOCK:
        _SPEAKER_SEQ[0] += 1
        turn = _SPEAKER_SEQ[0]
        _SPEAKER_SLOTS[str(session)] = {"turn": turn, "at": time.time(), "verdict": verdict}
        _SPEAKER_SEEN["turns"] += 1
        if verdict.get("bossByName"):
            _BOSS_BY_NAME["promoted"] += 1
        if verdict.get("who") in (None, "", "GUEST"):
            _SPEAKER_SEEN["guests"] += 1
        elif verdict.get("hands"):
            _SPEAKER_SEEN["boss"] += 1
        else:
            _SPEAKER_SEEN["known"] += 1
    return turn


def _speaker_spend(session):
    """Empty a session's slot: the verdict in it has just authorised something.

    THE SEAL DOES NOT GO DARK WHEN THIS RUNS. The live label the page shows comes from the
    page's own copy of the reply it already received - this only removes the server's
    willingness to ACT on that turn number a second time.
    """
    with _SPEAKER_LOCK:
        _SPEAKER_SLOTS.pop(str(session), None)


# =============================================================================
#  THE HANDSHAKE WINDOW  -  section 35 PART 1
#
#  THE ROOT CAUSE, NAMED. A confirmation is one or two syllables - "yes", "haan", "nahi" -
#  and a speaker embedding needs speech to work with. voiceprint.ENROL_MIN_SECONDS is three
#  seconds for a reason, and §35's own baseline measured the cliff: the same voice reads
#  cosine 0.9069 on a full sentence and the degradation ladder steps 0.5443 -> 0.3338 across
#  the threshold the moment the signal thins. So the Doorman seals the one word the gate
#  exists to collect as GUEST, and the house refuses its own employer the instant he answers
#  the question it just asked him. That is not a threshold that needs moving: a threshold low
#  enough to admit "yes" is a threshold that admits anybody saying "yes".
#
#  THE FIX IS CONTEXT, NOT CONFIDENCE. A sentence the Doorman DID verify - "save a note about
#  the pricing" at 0.9 cosine - is already proof the boss is in the room and is already
#  spending a turn number. If that sentence opens a gate, the answer to that gate, arriving
#  within two minutes and consisting of nothing but a confirmation word, inherits the seal the
#  question earned. The privilege is borrowed from a measurement that was actually made.
#
#  WHAT THIS DOES NOT DO, and each clause is an assertion in handshake_proof:
#    - no window opens from a GUEST utterance. Only a BOSS seal opens one.
#    - a confirmation word with no open window is sealed GUEST and refused exactly as before.
#    - a NON-grammar utterance inside an open window inherits nothing and takes the normal
#      Doorman path, so the window widens the vocabulary by nine words and not by a sentence.
#    - after the window times out, "yes" is GUEST again.
#    - the typed path never reaches here at all, because the keyboard is already the boss.
#
#  AND THE WINDOW IS JUDGED ON READ, NEVER REAPED BY A TIMER. §35 asks it to close on three
#  events - first confirmation, timeout, gate closed - and only the first is something this
#  module does. The other two are conditions, so they are evaluated by whoever asks, exactly
#  as hands.lapse_if_due() does: a window whose proposal id is no longer the pending one is
#  already shut, which makes "the window closes when the gate closes" a property of one
#  function rather than a callback that eight propose sites could forget to fire.
HANDSHAKE_MIN_S = 5.0            # a window worth less than this is a window nobody can use
HANDSHAKE_MAX_S = 600.0          # and one worth more is a privilege left lying about
HANDSHAKE_LOG_MAX = 40           # a ring, not an archive: see turn_engine()'s ledger
# THE DOORS A HUMAN HAND ACTUALLY TOUCHES, and the only ones a typed opener may arm a window
# from - see handshake_offer(). "" is /chat, which sends no door at all because a typed sentence
# is not a door; "button" is the page's own card. Every other door - "harness", "voice", and
# whatever a later producer invents - must earn its seal from a measurement instead.
HANDSHAKE_HUMAN_DOORS = ("", "button")
_HANDSHAKE = {}                  # session -> {pid, topic, gate, at, seal}
_HANDSHAKE_LOCK = threading.Lock()
_HANDSHAKE_LOG = []
# COUNTS ONLY, like _SPEAKER_SEEN, and for the Scribe's reason: this house may know how many
# handshakes it honoured and may never know which sentence was answered by which word.
_HANDSHAKE_SEEN = {"opened": 0, "honoured": 0, "expired": 0, "refusedNoWindow": 0}


def confirm_window_s(cfg=None):
    """How long a handshake is worth, in seconds, clamped.

    Clamped rather than trusted: a config.json with "confirm_window_s": 86400 is a day-long
    standing permission for anybody who can say yes in this room, and a 0 is a feature that
    is silently off while the file says it is on. Both are typos, and both are refused here
    rather than halfway down the gate.
    """
    cfg = cfg if isinstance(cfg, dict) else load_config()[0]
    try:
        want = float(cfg.get("confirm_window_s", DEFAULT_CONFIG["confirm_window_s"]))
    except (TypeError, ValueError):
        want = float(DEFAULT_CONFIG["confirm_window_s"])
    return max(HANDSHAKE_MIN_S, min(HANDSHAKE_MAX_S, want))


def handshake_grammar(text):
    """True when `text` is nothing but a confirmation - the whole message, either polarity.

    IT IS hands.py's GRAMMAR AND NOT A COPY OF IT, which is the single most important line in
    this section. The set of words that may inherit a seal and the set of words the gate can
    act on have to be the same set: a word that opened the window and inherited BOSS but that
    is_confirmation() then did not recognise would arrive at the gate as a NEW SUBJECT and
    silently withdraw the very proposal it was meant to approve. One grammar, read twice.
    §35's list - yes/no/yeah/nope/haan/nahi/cancel/stop/confirm/thik hai - is checked against
    this function by handshake_proof, and `nahi` and `thik hai` were added to hands.py for it.
    Case and surrounding whitespace are hands.py's job already (re.I, and _WHOLE eats the
    padding), so nothing is lowercased or stripped twice here.
    """
    said = str(text or "")
    return bool(hands.is_confirmation(said) or hands.is_refusal(said))


def handshake_open(session, seal, topic="", gate="", pid="", now=None):
    """Open a window, but only for a BOSS. Returns True if one is now open.

    THE SEAL IS THE WHOLE OF THE GUARD and it is checked here rather than at the call sites,
    because there are two call sites and will be more: the law has to be impossible to open
    from a guest, not merely unopened by the two callers that exist today. "BOSS" exactly -
    not UNVERIFIED, not a named enrolled voice without hands, not an empty string - because
    the privilege being lent is the Hands gate's, and seal_for() reads BOSS for exactly the
    voices that gate will take an order from.
    """
    if str(seal or "") != "BOSS":
        return False
    at = float(now if now is not None else time.monotonic())
    with _HANDSHAKE_LOCK:
        _HANDSHAKE[str(session)] = {"pid": str(pid or ""), "topic": str(topic or "")[:120],
                                    "gate": str(gate or "")[:60], "at": at, "seal": "BOSS"}
        _HANDSHAKE_SEEN["opened"] += 1
    return True


def handshake_close(session):
    """Shut a window by hand. Idempotent, and the return says whether one was there."""
    with _HANDSHAKE_LOCK:
        return _HANDSHAKE.pop(str(session), None) is not None


def handshake_live(session, pending_id=None, now=None, cfg=None):
    """The open window for this session, or None - the three closing conditions in one read.

    `pending_id` IS THE GATE, and passing it is how "the window closes when the gate closes"
    is enforced without a callback. None means "do not check the gate", which is what the
    standalone state-machine proof uses and what a reader with no Hands slot to consult uses;
    every caller inside this server passes the live one.

    A window that has aged out is REMOVED here rather than merely ignored, so that a stale
    entry cannot be revived by a later call that happens to pass a longer window, and so the
    dict cannot grow one dead row per session for the life of the process.
    """
    at = float(now if now is not None else time.monotonic())
    ttl = confirm_window_s(cfg)
    with _HANDSHAKE_LOCK:
        win = _HANDSHAKE.get(str(session))
        if not win:
            return None
        if at - float(win["at"]) > ttl:
            _HANDSHAKE.pop(str(session), None)
            _HANDSHAKE_SEEN["expired"] += 1
            return None
        # THE GATE CLOSED. A different proposal in the slot, or an empty slot, means the
        # question this window was opened to collect an answer to is no longer being asked -
        # so the answer is no longer privileged. Only checked when the caller knows the slot:
        # a window opened for no particular proposal (pid "") is not invalidated by one.
        if pending_id is not None and win["pid"] and str(pending_id or "") != win["pid"]:
            _HANDSHAKE.pop(str(session), None)
            return None
        out = dict(win)
        out["ageS"] = round(at - float(win["at"]), 3)
        out["ttlS"] = ttl
        return out


def handshake_honour(session, word, pending_id=None, now=None, cfg=None):
    """(row, None) if this word inherits BOSS from an open window, else (None, why).

    ON SUCCESS THE WINDOW IS SPENT. §35's "closes on first confirmation", and it is the same
    one-turn-one-order rule _speaker_spend() applies to a verdict: a window that authorised
    twice is a window worth waiting for. The row is the ledger's - topic, gate, latency - and
    it carries no sentence, only the one grammar word that was heard, which is already one of
    nine known strings and therefore not a record of what was said.
    """
    if not handshake_grammar(word):
        return None, "not a confirmation"
    win = handshake_live(session, pending_id=pending_id, now=now, cfg=cfg)
    if win is None:
        with _HANDSHAKE_LOCK:
            _HANDSHAKE_SEEN["refusedNoWindow"] += 1
        return None, "no open window"
    handshake_close(session)
    row = {"at": time.strftime("%H:%M:%S"), "topic": win["topic"], "gate": win["gate"],
           "latencyMs": int(round(win["ageS"] * 1000)), "windowS": int(win["ttlS"]),
           "word": confirmation_in(word) or "", "seal": HANDSHAKE_SEAL}
    with _HANDSHAKE_LOCK:
        _HANDSHAKE_LOG.append(row)
        while len(_HANDSHAKE_LOG) > HANDSHAKE_LOG_MAX:
            _HANDSHAKE_LOG.pop(0)
        _HANDSHAKE_SEEN["honoured"] += 1
    sys.stderr.write("  handshake: %s inherited BOSS at %dms of %ds (gate %s)\n"
                     % (row["word"] or "a confirmation", row["latencyMs"], row["windowS"],
                        row["gate"] or "?"))
    return row, ""


def handshake_offer(session, data, payload=None):
    """An answer LEFT A GATE STANDING: open a window if it was a BOSS who asked for it.

    WHY THIS IS ONE FUNCTION AND NOT TWO LINES AT EACH DOOR. There are two doors that leave a
    proposal pending - /chat, when the model asks for a tool, and /tools cmd=propose, when the
    page asks directly - and a third will arrive with the Director. The BOSS test has to be
    the same test at all of them, and it has to read the verdict from THIS process's slot via
    _speaker_turn() rather than from anything the body claims, or the window becomes a field a
    tab can set.

    THE TYPED PATH OPENS ONE TOO, and §36 widened it deliberately - §35 returned False here on
    the reasoning that a typed yes never reaches doorman_refusal(), which is true and was also
    beside the point. THE TWO HALVES OF A HANDSHAKE NEED NOT ARRIVE BY THE SAME DOOR. The boss
    types "put that on my calendar" and then ANSWERS OUT LOUD, which is the natural thing to do
    with a card on the screen and a microphone already open - and that spoken "yes" does reach
    doorman_refusal(), is one syllable, and is sealed GUEST. A window that only a spoken opener
    could arm left that crossing unprotected, and the keyboard law says the typed sentence was
    the boss's: that is the same fact the seal "BOSS" states, so it is stated here.

    THE FAILURE MODE IT ACCEPTS, NAMED RATHER THAN HIDDEN: the boss types an order and leaves
    the room, and within confirm_window_s a stranger's "yes" inherits BOSS. Three things bound
    it and all three are asserted - the window is 120 s by default and clamped to 600, it is
    spent by the FIRST confirmation, and it dies the moment the pending proposal is not the one
    it was opened for. What it cannot be is a standing privilege.
    """
    pending = None
    if isinstance(payload, dict) and isinstance(payload.get("pending"), dict):
        pending = payload["pending"]
    if pending is None:
        try:
            pending = hands.pending_public()
        except Exception:                                          # noqa: BLE001
            pending = None
    if not isinstance(pending, dict) or not pending.get("id"):
        return False
    verdict, spoken, _why = _speaker_turn(data if isinstance(data, dict) else {}, session)
    if not spoken:
        # THE KEYBOARD IS THE BOSS, said once, here. Everywhere else in this server that
        # sentence is spelled "a typed message is never challenged"; a window is what it
        # looks like when the answer to a typed question arrives by voice.
        #
        # BUT ONLY AT A DOOR A HUMAN HAND TOUCHES - §36 PART 3, and this is a hole §36 opened
        # and speaker_proof found. "No speaker block" is the shape of a typed message AND the
        # shape of every automated caller: /tools cmd=propose with door "harness" carries no
        # speaker block either, so a test rig - or anything else posting that door - armed a
        # 120-second BOSS window that the next voice in the room, any voice, then inherited.
        # Measured: speaker_proof section D executed five times where it asserts five refusals.
        # THE TWO REAL KEYBOARD DOORS ARE NAMED INSTEAD: /chat sends no `door` at all (a typed
        # sentence), and the page's own card sends door "button" (he pressed it). Everything
        # else opens nothing, which leaves PART 1's path - he types an order, the model raises
        # the gate, he answers out loud - exactly as it was.
        if str((data or {}).get("door") or "") not in HANDSHAKE_HUMAN_DOORS:
            return False
        seal = "BOSS"
    elif voiceprint is None:
        return False
    else:
        try:
            # A SPOKEN OPENER IS STILL MEASURED. seal_for() reads BOSS only for a row above
            # threshold that carries the hands, which after boss_by_name() includes the row
            # the house greets him by - and still excludes every guest.
            seal = voiceprint.seal_for(verdict)
        except Exception:                                          # noqa: BLE001
            return False
    # THE TOPIC IS THE REGISTRY'S LABEL FOR THE TOOL and never the employer's sentence, because
    # this string reaches a ledger row and a report plate. "Send an email" is enough for a boss
    # reading the ledger to know which handshake he is looking at; the recipient is not.
    return handshake_open(session, seal, topic=str(pending.get("name") or ""),
                          gate=str(pending.get("tool") or ""),
                          pid=str(pending.get("id") or ""))


# THE ONE-SHOT CARRIER. An honoured handshake is discovered deep inside doorman_refusal(), and
# the chip that has to read BOSS · HANDSHAKE is painted from the payload of whichever door was
# being held. Rather than widen four return signatures, the row is left here and TAKEN once by
# the door on its way out - the same shape as _SPEAKER_SLOTS, and popped on read for the same
# reason: a seal that could be collected twice is a seal that outlives the word that earned it.
_HANDSHAKE_LAST = {}


def handshake_mark(session, row):
    with _HANDSHAKE_LOCK:
        _HANDSHAKE_LAST[str(session)] = row


def handshake_stamp(session, payload):
    """Put the inherited seal on an outgoing payload, if this turn earned one. Returns payload.

    Two named fields and no prose: `speakerSeal` is the string the chip renders and `handshake`
    is the evidence behind it (gate and latency, no topic), so the page can copy one and a
    harness can assert the other. The page is forbidden from DERIVING either - see the note on
    speaker.seal in index.html - because a page that could compute this string could award it.
    """
    with _HANDSHAKE_LOCK:
        row = _HANDSHAKE_LAST.pop(str(session), None)
    if row and isinstance(payload, dict):
        payload["speakerSeal"] = HANDSHAKE_SEAL
        payload["handshake"] = {"gate": row.get("gate", ""), "word": row.get("word", ""),
                                "latencyMs": row.get("latencyMs", 0),
                                "windowS": row.get("windowS", 0)}
    return payload


def handshake_state():
    """What /health may publish: counts, the ring, and the live windows WITHOUT their topics.

    The topic is a few words of the employer's business and the ring already carries it for
    the ledger; the at-rest list is read by a page and by a harness, so it carries the gate
    and the age and no subject at all.
    """
    # §36 PART 1. The promotion is published because a harness with no microphone has no other
    # way to read it, and because a privilege granted invisibly is the one kind this house does
    # not grant. `wouldPromote` says the roster on disk holds a row by the boss_call name that
    # carries no hands of its own - which is the exact condition that refused the boss his own
    # window - and `promoted` counts the verdicts it has mended since this process started.
    call = boss_call_slug()
    would = False
    if call and voiceprint is not None:
        try:
            would = any(voiceprint.slug(r["name"]) == call and not r["hands"]
                        for r in voiceprint.enrolled())
        except Exception:                                      # noqa: BLE001
            would = False
    with _HANDSHAKE_LOCK:
        live = [{"gate": w["gate"], "ageS": round(max(0.0, time.monotonic() - w["at"]), 1)}
                for w in _HANDSHAKE.values()]
        return {"windowS": int(confirm_window_s()), "live": live,
                "seen": dict(_HANDSHAKE_SEEN), "rows": list(_HANDSHAKE_LOG),
                "bossByName": {"call": call, "wouldPromote": would,
                               "promoted": _BOSS_BY_NAME["promoted"]}}


# THE WORD THE CHIP READS, in one place so the page, the ledger and the proof cannot disagree
# about it. Not computed in the browser - see the comment on speaker.seal in index.html: a
# page that derived this string would be a page that could award it.
HANDSHAKE_SEAL = "BOSS · HANDSHAKE"


def _speaker_turn(data, session):
    """Who said THIS message. Returns (verdict, spoken, why).

    `spoken` IS THE HALF THAT MATTERS AT THE GATE, and it is separate from the verdict on
    purpose. A message that arrived through the ear is spoken whether or not the doorman
    managed to put a name to it, and the law has to be able to tell those two apart from a
    message that was typed:

      typed                   no `speaker` block at all. spoken False, verdict None. The law
                              does not apply, because the keyboard is the boss's other door.
      spoken and identified   spoken True, verdict the one THIS process made from real audio.
      spoken, not identified  spoken True, verdict None - a stale turn number, one this server
                              never issued, or a page that asked nothing. The gate FAILS
                              CLOSED on this, which is the whole reason the flag exists: a
                              spoken yes with no established speaker must not be honoured just
                              because the identification step went missing.

    THE PAGE CARRIES A NUMBER AND NOTHING ELSE - no name, no privilege, no score - so the most
    a stale or hostile tab can do is quote a verdict this process already reached from audio.
    """
    block = data.get("speaker") if isinstance(data, dict) else None
    if not isinstance(block, dict) or str(block.get("via") or "") != "voice":
        return None, False, "typed"
    try:
        turn = int(block.get("turn") or 0)
    except (TypeError, ValueError):
        return None, True, "the speaker turn was not a number"
    with _SPEAKER_LOCK:
        slot = _SPEAKER_SLOTS.get(str(session))
    if not slot or not turn or slot["turn"] != turn:
        return None, True, ("speaker turn %s is not the one this server issued" % turn)
    if time.time() - slot["at"] > SPEAKER_TURN_TTL_S:
        return None, True, ("speaker turn %d is %.0fs old, past the %.0fs it is worth"
                            % (turn, time.time() - slot["at"], SPEAKER_TURN_TTL_S))
    return slot["verdict"], True, ""


def doorman_refusal(data, session, word):
    """The law, in one place: (payload, seal) to refuse with, or (None, seal).

    WITH AT LEAST ONE HANDS-PRIVILEGED VOICEPRINT ENROLLED, a spoken Yes or No at the Hands
    gate is accepted from that voice and from no other. Not because a guest is assumed
    hostile, but because that gate is the only place in this house where a sentence becomes an
    email leaving it or an entry in somebody's calendar, and "somebody in the room said yes"
    is not consent from the person whose account it is.

    THE NO IS REFUSED TOO, and the mandate names both words. A guest's no is also a decision
    about the boss's business - it cancels a proposal he made and is waiting on - so a stranger
    who can say no can quietly stop everything this house is asked to do. Neither word is an
    opinion at this gate; both are instructions.

    WITH ZERO ENROLMENTS THE LAW STANDS DOWN SILENTLY. No sentence, no seal, no mention: a
    house where nobody has taught it a voice behaves exactly as it did before this section was
    written. has_hands_voice() is the whole of the switch.

    THE KEYBOARD IS ALWAYS OPEN. A body with no `speaker` block is a typed message, and a
    typed Yes never reaches this function - see _speaker_turn(). That is deliberate and it is
    the escape hatch: the cost of the doorman refusing the boss on a bad morning is one
    keystroke, and the cost of admitting a stranger is a sent email. The two are not the same
    size, so the law is strict and the other door stays unlocked.

    AND IT FAILS CLOSED. A spoken yes whose speaker could not be established - a stale turn
    number, one this server never issued, an identification that never happened - is refused
    rather than waved through.

    IT IS ONE FUNCTION BECAUSE THERE ARE THREE DOORS. /chat's gate takes a spoken yes when the
    page routes the sentence to the server, and the page's own card posts /execute and
    /tools cmd=cancel with door "voice" when it recognises the word itself. A law written at
    one of those three is a law with two ways round it.
    """
    verdict, spoken, why = _speaker_turn(data, session)
    seal = (voiceprint.seal_for(verdict) if (voiceprint is not None and spoken) else "")
    if not spoken or voiceprint is None:
        return None, seal
    if why:
        sys.stderr.write("  speaker: %s\n" % why)
    try:
        guarded = voiceprint.has_hands_voice()
    except Exception:                                          # noqa: BLE001
        # A store that will not read is not a reason to open the gate. It is also not a reason
        # to refuse a house that has never enrolled anybody, which is why this sits inside the
        # `spoken` branch rather than above it.
        guarded = False
    if not guarded or (isinstance(verdict, dict) and verdict.get("hands")):
        # ONE TURN, ONE ORDER. A verdict is worth 45 seconds to /chat, which only uses it to
        # decide what to call somebody - but at THIS gate it authorises an action, and a number
        # that authorises twice is a number worth stealing. So an honoured word spends it: the
        # slot is emptied and the next spoken yes needs a sentence of its own to be measured
        # from. The case this closes is the barked interrupt, which reaches the page before the
        # detector has ended the utterance and therefore travels with the PREVIOUS turn's
        # number; spent once, that number stops being a second consent.
        if spoken and isinstance(verdict, dict):
            _speaker_spend(session)
        return None, seal
    # ---- THE HANDSHAKE WINDOW - §35 PART 1, and its POSITION is the security property.
    #
    # It sits BELOW the whole Doorman - the store read, the guard check, the hands test - and
    # ABOVE both refusals. Below, because a house with nothing enrolled has already returned and
    # a voice that genuinely has hands has already been admitted on its own merit, so the window
    # is only ever consulted for an utterance the Doorman has just decided is NOT the boss.
    # Above, because that decision is the one being overturned, and it can only be overturned by
    # a measurement the Doorman himself made moments ago on a longer sentence.
    #
    # EVERY GUARD IS IN handshake_honour(), not here: the word must be in the one shared grammar,
    # a window must be open, it must have been opened by a BOSS seal, it must be inside
    # confirm_window_s, and the proposal it was opened for must still be the one standing. A
    # failure of any of those falls through to the refusals below UNCHANGED - which is edges 2,
    # 3 and 4 of the mandate, and they are one line of code because they are one absence.
    #
    # THE TURN IS SPENT ON SUCCESS, exactly as the accept branch above spends it. The verdict
    # being spent is a GUEST verdict and worthless at this gate, but the turn NUMBER is what a
    # barked interrupt re-uses, and a window honoured twice off one number would be the hole
    # this whole section is otherwise careful not to open.
    #
    # AND TWO THINGS THE WINDOW MAY NOT OVERTURN - §36 PART 3, found by speaker_proof against a
    # live server and fixed here rather than in the harness, because both are holes:
    #
    #   NO VERDICT, NO INHERITANCE. `verdict is None` at this point does not mean "a guest"; it
    #   means THE SPEAKER WAS NEVER ESTABLISHED - a turn number this process never issued, one
    #   already spent, one that has aged past SPEAKER_TURN_TTL_S, or a page that skipped the
    #   identification step altogether. The docstring above promises those fail closed, and for
    #   one window of §36 they did not: a tab posting door:"voice" with turn 0 inside an open
    #   window inherited BOSS · HANDSHAKE, and the same turn number consented twice because the
    #   spend below only ran when a verdict existed. Measured: speaker_proof's section D went
    #   61/70 with five executions where it had asserted five refusals. A window is a key for
    #   one word SPOKEN BY SOMEBODY THIS PROCESS HEARD, not for any body that can post the word.
    #
    #   A NAMED STRANGER IS NOT AN UNRECOGNISED ONE. An enrolled voice without the hands comes
    #   back with who="Ryan" - the house KNOWS who that is and knows it is not the boss - and
    #   §35's refusal of that person's yes is a judgement, not a failure of measurement. The
    #   boss's own case, the one PART 1 exists for, is the opposite: one syllable is too short
    #   to match anybody, so it reads GUEST or UNVERIFIED with no name in it at all. So the
    #   window is inherited by the UNNAMED only, which keeps every §35 negative case that was
    #   ever about a person the doorman could name.
    named_other = (isinstance(verdict, dict)
                   and str(verdict.get("who") or "") not in ("", "GUEST"))
    if handshake_grammar(word) and isinstance(verdict, dict) and not named_other:
        try:
            pend = hands.pending_public()
        except Exception:                                          # noqa: BLE001
            pend = None
        row, _hwhy = handshake_honour(session, word, pending_id=(pend or {}).get("id") or "")
        if row is not None:
            if isinstance(verdict, dict):
                _speaker_spend(session)
            handshake_mark(session, row)
            return None, HANDSHAKE_SEAL
    # ---- NEVER A SILENT GUEST FOR THE BOSS. Two refusals, and they refuse identically: nothing
    # is executed, no hand is unlocked, the card stands untouched and the law above is the same
    # law. What differs is what is SAID, and the difference is the mandate's.
    #
    # A voice in the near band is one the doorman could not be sure of, whose closest row is the
    # hands-privileged one - see voiceprint.NEAR_THRESHOLD. Telling that person "I take orders
    # from one voice in this house, and it is not speaking just now" is telling the employer he
    # is a stranger in his own house, and it hands him no way forward: he does not know whether
    # he was misheard, whether the room was loud, or whether the machine has forgotten him. So
    # this branch names the doubt and names both doors out of it - say it again, or press the Yes
    # that is already on the screen. LOUDLY, because the alternative is a machine that appears
    # to be ignoring him.
    #
    # THE VERBATIM LINE BELOW IS NOT TOUCHED. It is the mandate's sentence for an actual stranger
    # and it stays exactly as it was written, which is why this is a branch above it rather than
    # a condition inside it.
    if isinstance(verdict, dict) and verdict.get("unverified"):
        sys.stderr.write("  route: confirmation - a spoken %s in the near band (cosine %.3f), "
                         "refused and said so\n" % (word or "word", verdict.get("score") or 0.0))
        return {
            "ok": False, "kind": "tool", "nodes": [],
            "answer": ("I could not be sure that was you, so I have not acted on it. Say it "
                       "once more, a little longer, or press Yes on the card."),
            # A DIFFERENT REASON CODE, so that a harness and a log can tell the two refusals
            # apart without reading the prose - and so that this one can never be mistaken for
            # the "not-the-boss" it deliberately does not say.
            "refused": "unverified-voice", "route": "confirmation", "lookups": 0, "seal": seal,
        }, seal
    sys.stderr.write("  route: confirmation - a spoken %s from a voice without hands, "
                     "refused at the doorman\n" % (word or "word"))
    return {
        "ok": False, "kind": "tool", "nodes": [],
        # THE LINE IS THE MANDATE'S, VERBATIM, and it is courteous on purpose: the guest has
        # done nothing wrong and is not accused of anything. It also names NO NAME - not the
        # boss's, not theirs - because a refusal is not the place to tell a stranger who is
        # allowed to give this house orders.
        "answer": "I take orders from one voice in this house, and it is not speaking just now.",
        "refused": "not-the-boss", "route": "confirmation", "lookups": 0, "seal": seal,
    }, seal


# THE ADDRESS FORMS, TAKEN OFF. A guest gets no address form at all rather than a guessed one,
# and the cheapest way to make that true of every sentence in this server - the ones written
# here AND the ones a model writes - is one pass over the finished text.
#
# WHAT COUNTS AS AN ADDRESS, and the distinction is the whole of the function: a VOCATIVE is a
# name used to speak TO somebody, and it is the one the guest must not receive. A name used to
# speak ABOUT somebody is a fact, and a guest asking "whose assistant are you" is owed it. So
# "Not connected, Addi." loses its address and "the personal assistant of Sir Aditya Singh"
# keeps every word, because the first is set off by a comma or ends the clause and the second
# is the object of a preposition.
#
# FAILURE MODE IF THIS OVERREACHES: an identity answer to a guest reads "I am Galaxy, the
# personal assistant of" and stops. That is why the formal name is never touched here and only
# the comma-and-terminal positions are, and why deaddress() is asserted in both directions -
# the address gone, the fact still there.
_ADDRESS_WORDS = ("sir", "madam", "boss")


def deaddress(text, cfg=None):
    """A finished sentence with its vocatives removed. Idempotent, and safe on any string."""
    out = str(text or "")
    if not out:
        return out
    who = persona(cfg)
    words = [w for w in ([who["boss_call"]] + list(_ADDRESS_WORDS)) if w]
    alts = "|".join(re.escape(w) for w in dict.fromkeys(words))
    # ", Addi." / ", Addi," / ", Addi and" -> the comma and the name go together, because a
    # comma that introduced nothing is worse punctuation than no comma at all.
    out = re.sub(r"\s*,\s*(?:%s)\b(?=[\s,.;:!?)]|$)" % alts, "", out, flags=re.IGNORECASE)
    # "Addi, the notes say..." at the head of a sentence. The capital goes back on afterwards:
    # a stripped head leaves "the notes say nothing", and a sentence that starts in lower case
    # is how a reader can tell something was cut out of it.
    out = re.sub(r"(^|(?<=[.!?])\s+)(?:%s)\s*,\s*" % alts, r"\1", out, flags=re.IGNORECASE)
    # "...I shall not, sir." with no comma - "Very good sir." - and note that this rung reaches
    # for the PURE VOCATIVES ONLY and never for the boss's call-name.
    #
    # THE REASON IS A SENTENCE THIS SERVER ACTUALLY WRITES: "He is Sir Aditya Singh, and I call
    # him Addi." A name in terminal position with no comma is genuinely ambiguous - vocative in
    # "That is connected Addi", object in "I call him Addi" - and this function cannot tell them
    # apart without a parser. "sir" in terminal position has no such second reading. So the
    # ambiguous case is left alone and the known limit is written here rather than discovered
    # later: an uncommaed terminal call-name survives deaddress. The prompt line for a guest
    # turn asks the model for no address form at all, which is the other half of the guard.
    bare = "|".join(re.escape(w) for w in _ADDRESS_WORDS)
    out = re.sub(r"\s+(?:%s)(?=[.!?]|$)" % bare, "", out, flags=re.IGNORECASE)
    out = re.sub(r"[ \t]{2,}", " ", out).strip()
    return (out[0].upper() + out[1:]) if out[:1].islower() else out


def scribe_state():
    """The transcriber, described the way the voice is: booleans, names and counts.

    Published on /health because the ORGAN has to know before it opens a picker: a
    machine without faster-whisper must refuse in a sentence rather than record three
    seconds of a meeting and then discover there is nothing to send it to. No word of
    any transcript is in here, and there is no field that could hold one.
    """
    if scribe is None:
        return {"installed": False, "ready": False, "loading": False,
                "model": "base.en", "device": "cpu", "computeType": "int8",
                "keepsAudio": False, "keepsText": False,
                "why": "faster-whisper is not importable in this server process",
                "chunks": 0, "refused": 0, "audioSeconds": 0, "audioBytes": 0,
                "transcribedChars": 0, "transcribeMs": 0, "loadMs": 0,
                "cpuThreads": 0, "maxChunkBytes": 0}
    return scribe.state()


# The same stripping tools/save_minutes.py does, for the same reason and one step
# earlier. This is NOT the security check - that is save_minutes.py's resolved-path test,
# which runs whatever this returns. This exists so the proposal card shows the employer
# the name the file will actually have, rather than the name they typed and a surprise.
MINUTES_UNSAFE = re.compile(r"[^A-Za-z0-9 ._-]+")


def minutes_title(raw):
    """A title fit to be a filename, or the dated default. Never a path."""
    clean = MINUTES_UNSAFE.sub(" ", str(raw or "")).strip()
    clean = re.sub(r"\s+", " ", clean)[:120].strip(" .")
    clean = os.path.basename(clean)
    return clean or ("Meeting-" + time.strftime("%Y-%m-%d-%H%M"))


def minutes_raw(transcript, title):
    """The fallback minutes: the transcript itself, under the four headings.

    WHEN THE BRAIN CANNOT BE REACHED the meeting is still gone, and the employer's
    choice is between a raw file and nothing. So this produces something with the same
    SHAPE as real minutes - four headings, so a later reader is not misled about what
    they are holding - and puts the whole transcript under the fourth, where a verbatim
    record belongs. The line under each of the first three says plainly that no brain
    read this, because minutes nobody summarised must not be mistaken for minutes
    somebody did.
    """
    unread = "Not summarised - the brain was unavailable when these minutes were saved."
    return ("## Attendees\n\n%s\n\n"
            "## Key Decisions\n\n%s\n\n"
            "## Action Items\n\n%s\n\n"
            "## Raw Excerpts\n\nThe full transcript, verbatim:\n\n%s\n"
            % (unread, unread, unread, str(transcript or "").strip()))


# ------------------------------------------------------------- THE CASTING CALL
#
# Three voices, one sentence, and the boss picks. Everything about this is deliberately
# small, because the thing being chosen is permanent-ish and the ways to get it wrong are
# all the same way: letting the page decide something the disk is the authority on.
#
#   THE THREE ARE A FIXED LIST, here and not in the viewer. A page that could name its
#     own candidates could name any string, and /say's `model` parameter is gated on this
#     tuple - so the audition door opens onto exactly three files and nothing else. (It
#     would be safe anyway: say.model_path() basenames the name and looks only in
#     voices/. This is the second lock, not the first.)
#   WHAT IS INSTALLED IS A FACT, NOT A HOPE. Each candidate carries say.ready()'s own
#     verdict, so a voice whose .onnx was never downloaded arrives at the panel labelled
#     as absent rather than as a button that fails when pressed. On this machine that is
#     two of the three, and the panel says so.
#   THE LINE IS ONE CONSTANT. The same sentence for all three is the entire point of an
#     audition; three different sentences would be three impressions, not a comparison.
CASTING = (
    ("en_US-ryan-high", "Ryan", "American, warm, unhurried - the incumbent"),
    ("en_GB-alan-medium", "Alan", "English, clipped, a shade older"),
    ("en_US-joe-medium", "Joe", "American, plainer, lower"),
)
CASTING_LINE = "The archive is online, and the hands are wired, sir."
CASTING_MODELS = tuple(name for name, _label, _note in CASTING)


def casting_state(cfg):
    """The three candidates, what config.json currently wants, and whether piper is here.

    `fallback` is the one field the panel is built around: when piper is not installed at
    all there is nothing to audition, and the honest answer is not an empty list but a
    named downgrade - the browser's own voices, which this page already falls back to on
    its own. See the PIPER OFFLINE case in the viewer.
    """
    installed = bool(say.binary())
    wanted = str(cfg.get("voice_model") or DEFAULT_CONFIG["voice_model"])
    wanted = os.path.basename(wanted.strip())
    out = []
    for name, label, note in CASTING:
        state = say.ready(name)
        out.append({
            "model": name,
            "label": label,
            "note": note,
            "installed": bool(state["model_file"]),
            "ready": bool(state["ready"]),
            "why": state["why"],
            "chosen": name == wanted,
        })
    return {
        "engine": voice_engine_of(cfg),
        "piper": installed,
        "fallback": "" if installed else "web",
        "line": CASTING_LINE,
        "chosen": wanted,
        "lengthScale": say.LENGTH_SCALE,
        "noiseScale": say.NOISE_SCALE,
        "candidates": out,
    }


def write_voice_model(name):
    """Persist the casting decision to config.json. The ONE route that writes that file.

    Rules, and each of them is a thing that has gone wrong in somebody's project:

      THE NAME IS CHECKED FIRST, against CASTING and against the disk. A chosen voice
        that is not installed would leave the next restart mute, and a restart that came
        back silent because of a click here is the worst possible outcome of a panel
        whose whole job is choosing a voice.
      THE FILE IS READ RAW, not through load_config(). load_config() merges
        DEFAULT_CONFIG in and applies the runtime brain override - writing THAT back
        would bake a temporary swap into the file and copy every placeholder in the
        defaults table into the employer's own config. Raw in, one key changed, raw out.
      EVERY OTHER KEY SURVIVES BYTE FOR BYTE. There are credentials in this file. They
        are read here as opaque values, written back unexamined, never logged, never
        counted by anything but len(), and never returned.
      THE REPLACE IS ATOMIC. A crash halfway through a rewrite of the file that holds
        every key this house owns is not a state this project is going to have.

    Returns (payload, error). The payload names the model and nothing else about the file.
    """
    wanted = os.path.basename(str(name or "").strip())
    if wanted.endswith(".onnx"):
        wanted = wanted[:-5]
    if wanted not in CASTING_MODELS:
        return None, ("%r is not one of the three cast voices" % wanted)
    state = say.ready(wanted)
    if not state["ready"]:
        return None, ("that voice cannot speak on this machine: %s" % state["why"])

    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as fh:
            raw = json.load(fh)
        if not isinstance(raw, dict):
            raise ValueError("config.json must contain a JSON object")
    except FileNotFoundError:
        raw = dict(DEFAULT_CONFIG)
    except Exception as exc:                                    # noqa: BLE001
        return None, "config.json could not be read (%s)" % exc

    before = str(raw.get("voice_model") or "")
    raw["voice_model"] = wanted
    # The engine comes with it. Choosing a piper voice while config.json asks for the
    # browser's is a setting that would be silently ignored, and a panel that accepted a
    # choice and then did not use it is a lie with a confirmation dialog.
    raw["voice_engine"] = "piper"

    tmp = CONFIG_PATH + ".casting.tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(raw, fh, indent=2)
            fh.write("\n")
        os.replace(tmp, CONFIG_PATH)
    except Exception as exc:                                    # noqa: BLE001
        try:
            os.unlink(tmp)
        except OSError:
            pass
        return None, "config.json could not be written (%s)" % exc

    # Keys, not values, and that is the whole log line.
    sys.stderr.write("  casting: voice_model %s -> %s (%d keys preserved)\n"
                     % (before or "(unset)", wanted, len(raw)))
    return {"ok": True, "model": wanted, "was": before,
            "keys": len(raw), "ready": True}, None


# ---- WHAT THE BRAIN IS NOT ALLOWED TO TELL YOU: the state of your own machine.
#
# The proposal card for a recast has to read "you are hearing Joe at the moment; that
# would make it Alan" - a request and the thing it would replace, side by side, because
# the whole value of the gate is that a human can read what is about to change. The
# REQUEST comes from the brain. The CURRENT VALUE is a fact about a file on this disk,
# and a model asked to fill it in would fill it in from memory, from the greeting it read
# an hour ago, or from nothing at all - and be believed, on a card whose entire job is
# being believed.
#
# So it is overwritten here, after the tag and before the proposal, from config.json
# itself. Whatever the brain put in this field is discarded exactly like its prose.
def tool_facts(tool_id, params_text):
    """Parameters the SERVER knows, written over whatever arrived with the request."""
    if str(tool_id or "").strip().lower() != "set_voice":
        return params_text
    raw = params_text
    if isinstance(raw, str):
        try:
            raw = json.loads(raw) if raw.strip() else {}
        except ValueError:
            return params_text          # let hands.propose() refuse it in its own words
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        return params_text
    raw = dict(raw)
    cfg = load_config()[0]
    name = os.path.basename(str(cfg.get("voice_model")
                                or DEFAULT_CONFIG["voice_model"]).strip())
    # 'en_GB-alan-medium' -> 'Alan'. Derived, not looked up: there is no second table of
    # voice nicknames in this file to drift out of step with the tool's own.
    parts = [p for p in name.split("-") if p]
    word = parts[1] if len(parts) > 1 else (parts[0] if parts else "")
    word = "".join(c for c in word if c.isalnum())
    raw["current"] = (word[:1].upper() + word[1:]) if word else (name or "no voice")
    return raw


def call_chat_completions(url, key, model, who, messages, image=None, extra=None,
                          status=None):
    """OpenAI's /chat/completions shape, which OpenRouter and Groq speak too.

    Returns (answer, error) and never raises. One implementation for all three, because
    a second copy is how the image block ends up correct in one place only.

    `status`, WHEN A CALLER PASSES A DICT, IS FILLED IN WITH THE MACHINE-READABLE OUTCOME:
    {"code": 429, "transient": True}. It exists for the Fallback Law and for nothing else.
    The alternative was to have the caller decide whether to fall back by pattern-matching
    the English sentence this function returns - and that sentence is written to be read
    aloud to a person, so the day somebody improves its wording is the day 429s stop
    falling back and nobody finds out until the boss hears an apology instead of an answer.
    A keyword argument with a None default leaves all three existing call sites untouched.
    """
    if status is not None:
        status.update({"code": 0, "transient": False})
    if image:
        # A data URL, whose media type is the SAME constant the bytes were encoded
        # and declared with - so the two cannot fall out of step. Copied rather than
        # mutated in place: the caller's history must not grow an image in it.
        messages = [dict(m) for m in messages]
        last = next((m for m in reversed(messages) if m["role"] == "user"), None)
        if last is not None:
            last["content"] = [
                {"type": "image_url", "image_url": {"url": "data:%s;base64,%s" % (
                    FRAME_MEDIA_TYPE, base64.b64encode(image).decode("ascii"))}},
                {"type": "text", "text": last["content"]},
            ]
    body = {
        "model": model,
        "messages": messages,
        "max_tokens": MAX_ANSWER_TOKENS,
    }
    if TEMPERATURE is not None:
        body["temperature"] = TEMPERATURE
    payload = json.dumps(body).encode("utf-8")

    headers = {
        "Content-Type": "application/json",
        "Authorization": "Bearer %s" % key,
        "User-Agent": USER_AGENT,
    }
    headers.update(extra or {})
    req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as res:
            body = json.loads(res.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            err = json.loads(exc.read().decode("utf-8", "replace"))
            detail = (err.get("error") or {}).get("message") or ""
        except Exception:                                      # noqa: BLE001
            pass
        if status is not None:
            # ONLY 429 IS TRANSIENT AMONG THE HTTP CODES, and the three that are not are the
            # reason this is a whitelist rather than "anything over 400". A 401 is a wrong key
            # and a 404 is a retired model id: falling those back to the local engine would
            # give the boss a perfectly good answer from the wrong engine and leave the broken
            # flag in config.json for the next person to find. Heard as refusals instead.
            status.update({"code": exc.code, "transient": exc.code == 429})
        if exc.code == 401:
            return None, ("%s rejected the key in config.json (401). "
                          "Check that it is pasted in full and still active." % who)
        if exc.code == 402:
            return None, ("%s says the account is out of credit (402). %s"
                          % (who, detail)).strip()
        if exc.code == 404:
            return None, ("%s does not serve the model \"%s\" (404). %s"
                          % (who, model, detail)).strip()
        if exc.code == 429:
            return None, ("%s is rate limiting or the account is out of "
                          "credit (429). %s" % (who, detail)).strip()
        return None, ("%s returned HTTP %s. %s" % (who, exc.code, detail)).strip()
    except urllib.error.URLError as exc:
        # A TIMEOUT AND AN UNREACHABLE HOST ARE BOTH TRANSIENT, and urllib delivers both here:
        # socket.timeout arrives wrapped in URLError, as does a DNS failure and a refused
        # connection. All three describe a road, not a decision, so all three fall back.
        if status is not None:
            status.update({"code": 0, "transient": True})
        return None, "Could not reach the %s API (%s)." % (who, exc.reason)
    except Exception as exc:                                   # noqa: BLE001
        # NOT TRANSIENT, because nobody knows what this is. An unknown failure that retries on
        # a second engine is an unknown failure that happens twice.
        return None, "Unexpected error talking to %s: %s" % (who, exc)

    try:
        answer = body["choices"][0]["message"]["content"].strip()
    except Exception:                                          # noqa: BLE001
        return None, ("%s replied in an unexpected shape: %s"
                      % (who, json.dumps(body)[:300]))
    if not answer:
        return None, "%s returned an empty answer." % who
    return answer, None


def call_openai(cfg, messages, image=None):
    return call_chat_completions(
        OPENAI_URL, str(cfg.get("openai_api_key") or ""),
        cfg.get("model") or DEFAULT_CONFIG["model"], "OpenAI", messages, image)


def call_openrouter(cfg, messages, image=None):
    """Every voice swap ends up here: one key, any model in SPOKEN_MODELS."""
    return call_chat_completions(
        OPENROUTER_URL, str(cfg.get("openrouter_api_key") or ""),
        model_label(cfg), "OpenRouter", messages, image,
        # Optional, documented, and only ever the local address of this project.
        extra={"HTTP-Referer": "http://%s:%d/" % (HOST, PORT),
               "X-Title": "Knowledge Galaxy"})


# =============================================================================================
#  GROQ - ONE CLIENT, FOUR CAPABILITIES
# =============================================================================================
#
# WHY THERE IS SO LITTLE CODE HERE. Groq serves OpenAI's dialect, so chat and vision are
# call_chat_completions() with a different URL and a different model string - there is no second
# implementation of the image block, the error ladder or the response shape, and that is the
# single most valuable property of this section. The two that are genuinely different are the
# two that are not chat: a multipart upload for transcription and a call that returns audio
# bytes rather than JSON. Both are written out by hand against urllib, because the standing
# instruction on this project is the standard library and nothing else.
#
# WHAT NONE OF THESE FUNCTIONS DO: decide anything. They call and they report. The switching,
# the refusals and the Fallback Law all live above them in call_model() and in the routes, so
# there is exactly one place to read to find out when Groq is reached for.


# WHAT THIS PROCESS HAS SPENT AT GROQ, COUNTED WHERE THE REQUESTS ARE MADE. Four counters and
# nothing identifying: no prompt, no transcript, no spoken line, no key. It exists because three
# of §28's claims are claims about HOW MANY: "one cheap ping on switch, no polling", "one
# attempt, no retry storm", and "refusal + zero Groq calls". Every one of those is unfalsifiable
# against a server that will not say how many times it called out - a harness can only watch a
# transcript and hope. `attempts` counts the moment before the request goes out, so a refusal
# that never reached the wire leaves it where it was, which is exactly the claim being made.
_GROQ_SEEN = {"chat": 0, "vision": 0, "stt": 0, "tts": 0, "refused": 0, "fallback": 0}


def groq_seen(what):
    """One counter up, under no lock on purpose: a miscount here is never worth a deadlock.

    int += 1 is not atomic in CPython, so two chunks arriving in the same millisecond can in
    principle lose one. The alternative is a lock on every model call to protect a diagnostic,
    and a number that is occasionally one low is a better trade than a route that can block.
    The claims that matter - 0 versus 1, 1 versus 2 - are made by harnesses that call one thing
    at a time.
    """
    if what in _GROQ_SEEN:
        _GROQ_SEEN[what] += 1


def call_groq(cfg, messages, image=None, model=None, status=None):
    """Chat OR vision, by model string. (answer, error), never raises.

    ONE FUNCTION FOR BOTH BECAUSE GROQ MAKES NO DISTINCTION: an image is a content part on the
    last user message of an ordinary /chat/completions call, which is exactly what
    call_chat_completions() already builds for OpenAI and OpenRouter. `model` is passed in by
    the vision path so that the eyes and the tongue can be on different Groq models at the
    same time - which they are by default, one of them a vision slug and one not.
    """
    ready, why = groq_ready(cfg)
    if not ready:
        # COUNTED AS A REFUSAL AND NOT AS AN ATTEMPT, and it happens here rather than inside
        # call_chat_completions() so that no key means no request rather than a 401 spent
        # finding out what config.json already knew.
        groq_seen("refused")
        return None, why
    groq_seen("vision" if image else "chat")
    return call_chat_completions(
        GROQ_CHAT_URL, groq_key(cfg),
        model or str(cfg.get("groq_model") or DEFAULT_CONFIG["groq_model"]),
        "Groq", messages, image, status=status)


def _multipart(fields, files):
    """(body bytes, content type) for one multipart/form-data POST. Stdlib only.

    Hand-rolled because `requests` is not on this machine and will not be added for one upload.
    THE BOUNDARY IS RANDOM PER CALL, which matters more than it looks: a fixed boundary that
    happens to occur inside the audio bytes truncates the file at that point, and the symptom
    is a transcription of the first two seconds with no error anywhere. os.urandom rather than
    random, because this one wants to be unguessable-ish rather than reproducible.
    """
    boundary = "----galaxy" + base64.b16encode(os.urandom(12)).decode("ascii").lower()
    out = []
    for name, value in (fields or {}).items():
        out.append(("--%s\r\nContent-Disposition: form-data; name=\"%s\"\r\n\r\n%s\r\n"
                    % (boundary, name, value)).encode("utf-8"))
    for name, (filename, data, ctype) in (files or {}).items():
        out.append(("--%s\r\nContent-Disposition: form-data; name=\"%s\"; filename=\"%s\"\r\n"
                    "Content-Type: %s\r\n\r\n" % (boundary, name, filename, ctype))
                   .encode("utf-8"))
        out.append(data)
        out.append(b"\r\n")
    out.append(("--%s--\r\n" % boundary).encode("utf-8"))
    return b"".join(out), "multipart/form-data; boundary=%s" % boundary


def call_groq_whisper(path, cfg=None, audio=None, status=None):
    """Transcribe one utterance with whisper-large-v3-turbo. (text, error), never raises.

    `path` is a file on disk; `audio` is bytes when the caller already has them and would
    rather not write a temporary file. EXACTLY ONE OF THEM, and bytes are preferred when both
    arrive, because the caller that has bytes is the route that took them off the wire and the
    Scribe's privacy discipline - audio that never touches disk - is worth keeping habitual
    even here, where the audio is on its way to a third party anyway.

    THE CEILING IS CHECKED BEFORE THE REQUEST, not after: an eight-megabyte refusal that costs
    a round trip is a refusal that costs a round trip every time somebody's recorder is
    misconfigured.
    """
    cfg = cfg if cfg is not None else load_config()[0]
    if status is not None:
        status.update({"code": 0, "transient": False})
    ready, why = groq_ready(cfg)
    if not ready:
        groq_seen("refused")
        return None, why
    name = os.path.basename(str(path or "utterance.wav"))
    if audio is None:
        try:
            with open(path, "rb") as fh:
                audio = fh.read(GROQ_STT_MAX_BYTES + 1)
        except OSError as exc:
            return None, "That audio could not be read (%s)." % exc
    if not audio:
        return None, "There was no audio to transcribe."
    if len(audio) > GROQ_STT_MAX_BYTES:
        return None, ("That audio is %d bytes and the ceiling here is %d."
                      % (len(audio), GROQ_STT_MAX_BYTES))
    model = str(cfg.get("groq_stt_model") or DEFAULT_CONFIG["groq_stt_model"])
    # response_format json, which is the documented default, asked for out loud anyway: a
    # default that changes upstream changes the shape this function parses, and "text" would
    # come back as a bare string and be read as an empty transcript by the line below.
    body, ctype = _multipart({"model": model, "response_format": "json",
                              "temperature": "0"},
                             {"file": (name, audio, "audio/wav")})
    groq_seen("stt")
    req = urllib.request.Request(
        GROQ_STT_URL, data=body, method="POST",
        headers={"Content-Type": ctype, "Authorization": "Bearer %s" % groq_key(cfg),
                 "User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as res:
            payload = json.loads(res.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = (json.loads(exc.read().decode("utf-8", "replace"))
                      .get("error") or {}).get("message") or ""
        except Exception:                                      # noqa: BLE001
            pass
        if status is not None:
            status.update({"code": exc.code, "transient": exc.code == 429})
        if exc.code == 401:
            return None, ("Groq rejected the key in config.json (401) when I tried to "
                          "transcribe. Check \"groq_api_key\".")
        if exc.code == 404:
            return None, ("Groq does not serve the transcriber \"%s\" (404). That is "
                          "\"groq_stt_model\" in config.json. %s" % (model, detail)).strip()
        return None, ("Groq returned HTTP %s from the transcriber. %s"
                      % (exc.code, detail)).strip()
    except urllib.error.URLError as exc:
        if status is not None:
            status.update({"code": 0, "transient": True})
        return None, "Could not reach the Groq transcriber (%s)." % exc.reason
    except Exception as exc:                                   # noqa: BLE001
        return None, "Unexpected error talking to the Groq transcriber: %s" % exc
    text = str((payload or {}).get("text") or "").strip()
    # AN EMPTY TRANSCRIPT IS NOT AN ERROR AND IS REPORTED AS ITSELF. Silence transcribes to
    # nothing, and the ear above has to be able to tell "he said nothing" from "the call
    # failed" - conflating them is how a quiet room becomes an outage in the log.
    return text, ""


def call_groq_speech(text, cfg=None, status=None):
    """Orpheus. (wav bytes, error), never raises. The one call that returns audio.

    WHAT IS NOT HERE, DELIBERATELY: normalization. The Quiet Tongue runs in the page, on the
    text's way to an engine, and it runs for Piper and Orpheus alike because both are fed from
    the same place - so a second normalizer here would either be dead code or a second opinion
    about how to read an em-dash. /say asserts what it received; it does not re-write it.
    """
    cfg = cfg if cfg is not None else load_config()[0]
    if status is not None:
        status.update({"code": 0, "transient": False})
    ready, why = groq_ready(cfg)
    if not ready:
        groq_seen("refused")
        return None, why
    line = str(text or "").strip()
    if not line:
        return None, "there was no text to speak."
    model = str(cfg.get("groq_tts_model") or DEFAULT_CONFIG["groq_tts_model"])
    voice = str(cfg.get("groq_tts_voice") or DEFAULT_CONFIG["groq_tts_voice"])
    # wav, not mp3: the page's Piper FIFO decodes WAV bytes today and the whole point of
    # putting Orpheus behind /say is that nothing downstream of the response has to change.
    payload = json.dumps({"model": model, "input": line, "voice": voice,
                          "response_format": "wav"}).encode("utf-8")
    groq_seen("tts")
    req = urllib.request.Request(
        GROQ_SPEECH_URL, data=payload, method="POST",
        headers={"Content-Type": "application/json",
                 "Authorization": "Bearer %s" % groq_key(cfg),
                 "User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as res:
            data = res.read()
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = (json.loads(exc.read().decode("utf-8", "replace"))
                      .get("error") or {}).get("message") or ""
        except Exception:                                      # noqa: BLE001
            pass
        if status is not None:
            status.update({"code": exc.code, "transient": exc.code == 429})
        if exc.code == 401:
            return None, ("Groq rejected the key in config.json (401) when I tried to "
                          "speak. Check \"groq_api_key\".")
        if exc.code == 404:
            return None, ("Groq does not serve the voice \"%s\" (404). That is "
                          "\"groq_tts_model\" in config.json. %s" % (model, detail)).strip()
        if exc.code == 400 and "voice" in detail.lower():
            return None, ("Groq refused the voice \"%s\": %s. That is \"groq_tts_voice\" "
                          "in config.json." % (voice, detail))
        return None, ("Groq returned HTTP %s from the voice. %s" % (exc.code, detail)).strip()
    except urllib.error.URLError as exc:
        if status is not None:
            status.update({"code": 0, "transient": True})
        return None, "Could not reach the Groq voice (%s)." % exc.reason
    except Exception as exc:                                   # noqa: BLE001
        return None, "Unexpected error talking to the Groq voice: %s" % exc
    # A RIFF HEADER OR IT IS NOT AUDIO. Groq answers an error with JSON and a 200 is not a
    # promise of sound; forty-four bytes of something is how a page ends up playing silence
    # and reporting success. The check is four bytes and it is the difference between "the
    # voice failed" and a mute assistant nobody can explain.
    if len(data) < 45 or data[:4] != b"RIFF":
        return None, ("Groq's voice returned %d bytes that are not a WAV file."
                      % len(data))
    return data, ""


# ---- THE SCHOLAR GETS THE §28 CLIENT, BY REFERENCE, AND NOTHING ELSE ----------------------
#
# HERE AND NOT BESIDE focus.ASK_HAND because the four names below do not exist yet at line 214;
# this is the first point in the file where all of them do. Module attributes rather than an
# import, for the reason every other organ in this house uses them: scholar.py must never
# import server, or the two files could not be reasoned about separately and a test could not
# load one without the other.
#
# IT IS THE SAME CLIENT THE CONVERSATION USES, deliberately. call_groq_whisper carries its own
# 8 MB refusal and its own fallback rules, and a Scholar with a private HTTP client would be a
# second thing that could drift from this one - the drift showing up as a study pipe that
# passes its proof and disagrees with the house.
#
# WHAT IS NOT INJECTED IS THE POINT OF THE GATE: no hands.execute, no google_api, no calendar,
# no say. The Scholar cannot reach them because it was never handed them, which is a stronger
# statement than a policy about not calling them.
#
# NOT wear_persona'd, on purpose and for judge_ground.py's reason: the Scholar is a researcher
# reading a source, not the butler talking. Dressing its screening calls in the butler's
# costume would have the Poison Guard answering "certainly, sir" instead of ALLOW.
scholar.configure(chat=call_groq, whisper=call_groq_whisper, ready=groq_ready,
                  config=lambda: load_config()[0])


def wear_persona(cfg, messages):
    """Put who he is and what he can do in front of the system prompt. Every call.

    ONE PLACE, NOT EIGHT. There are eight sites in this file that build a system message -
    notes, small talk, web, compose, vision, webcam, the nudge, the greeting - and the
    mandate is that his name and his abilities are in ALL of them, so that a free-form
    answer is in character and not only the hard-classed ones. Injecting per site means
    eight edits now and a ninth site next month that quietly answers as a nameless butler.
    So it happens here, in the funnel every provider goes through.

    THE FAILURE MODE THIS GUARDS: a message list with no system role at all would silently
    get no persona. That does not happen today, and if it ever does, one is inserted rather
    than skipped. The list is copied - the caller's history is not ours to rewrite.
    """
    preamble = brain_preamble(cfg)
    out = [dict(m) for m in messages]
    for msg in out:
        if msg.get("role") == "system":
            msg["content"] = preamble + str(msg.get("content") or "")
            return out
    return [{"role": "system", "content": preamble.rstrip()}] + out


# =============================================================================
#  §41  -  THE LOCAL THINKER, AND THE ONE QUEUE
#
#  Groq is the brain. This is the net under it, and it is a net and not a second
#  brain: it catches ONE request, synchronously, when Groq tires - a 429, a
#  timeout, a host that will not answer - and it is never consulted for anything
#  else. A 401 and a 404 fall through it on purpose. See call_groq_then_local().
#
#  WHY THE NUMBERS BELOW ARE WHAT THEY ARE, and every one of them was a symptom
#  before it was a constant:
#
#  num_ctx 4096 rather than the model's default. Ollama will happily allocate a
#  32k context on a CPU machine and then spend minutes on the prefill before the
#  first token - which is a multi-minute hang at the exact moment the boss has
#  already waited for a Groq timeout. 4096 is more than a grounded question with
#  three snippets needs, and it is the difference between a quarter of a second
#  and a coffee.
#
#  num_predict 48, because this engine answers in one or two sentences and a cap
#  is the only thing that bounds a small model that has decided to keep going.
#
#  keep_alive -1 holds the weights in RAM for good. A cold load of a 7B model is
#  several seconds, and paying it on a fallback means paying it at the worst
#  moment there is; `ollama ps` showing "Forever" is this constant, visible.
#
#  temperature 0 for the same reason it is 0 in quick_rewrite(): a fallback that
#  cannot be reproduced cannot be measured, and a grounded answer has no business
#  being creative.
OLLAMA_CHAT_URL_PATH = "/api/generate"
OLLAMA_CHAT_TIMEOUT_S = 30.0
OLLAMA_FALLBACK_NUM_CTX = 4096
OLLAMA_FALLBACK_PREDICT = 48
OLLAMA_KEEP_ALIVE = -1
OLLAMA_TIMEOUT_LINE = "Local engine timed out"
# AND LONGER FOR THE BOOT WARM-UP THAN FOR A QUESTION, which is the point of having two
# numbers: the cold load is allowed to take its time on a thread nobody is waiting on, so
# that no question ever has to. See ollama_warm().
OLLAMA_WARM_TIMEOUT_S = 180.0

# HOW FAST THE HANDOVER ITSELF MAY BE, which is NOT how fast the answer may be: the budget
# measures the gap between Groq's failure and the local request leaving, so it is a test of
# this file's own arithmetic and not of anybody's hardware. A handover that takes a quarter
# of a second is a handover doing work it should not be doing.
FALLBACK_TRIGGER_BUDGET_MS = 250

# THE TWO SENTENCES THE BOSS MAY HEAR ABOUT ANY OF THIS, and they are fixed strings rather
# than prompts for the reason every canned line in this file is: a model asked to apologise
# improvises a fact. The first means "answered, by this machine". The second means "nobody
# answered, and it is written down" - and it is the ONLY one that admits a queue exists.
LOCAL_FALLBACK_LINE = "Thinking locally, sir."
QUEUED_LINE = "Thinking locally, sir... queued"

# §26'S RULE, IN ONE SENTENCE, FOR A MODEL THAT CANNOT READ FIVE PARAGRAPHS. The cloud
# prompts upstream are untouched and stay as they are; this is a separate, shorter rope for
# a 7B engine, and it says the one thing that must not be lost in translation. A long prompt
# to a small model is a long prompt the small model answers INSTEAD of the question.
GROUNDING_RULE = ("Answer using ONLY the facts in the snippets below. If they do not "
                  "contain the answer, say so plainly. Never state a fact they do not "
                  "contain.")
OLLAMA_FALLBACK_SYSTEM = (
    GROUNDING_RULE + "\n"
    + "Reply with the answer only, in one or two short sentences, using the facts from the "
      "snippets. Do not describe the snippets, do not explain your reasoning, and do not "
      "begin with 'I need to' or 'Let me'.")

# ONE SENTENCE MORE, ON WEB TURNS ONLY, AND IT IS THE ONE DEVIATION §41 TOOK FROM ITS OWN
# VERBATIM PROMPT - taken because the mandate's first sentence ranks §26 Grounding above the
# text of this constant, and §26 says a web answer must declare which world it speaks from.
#
# MEASURED, not anticipated: with the stripped prompt alone, preflight 15 read "answered
# from the web without saying so: 'The current population of Tokyo is 14,264,798 people.'"
# The cloud prompt carries that law in its own fourth bullet; dropping every system block -
# which is what makes a 7B model usable here - dropped the law with it, and the result is an
# answer the reader cannot place. That is not a cosmetic failure: the whole point of the cue
# is that nobody has to ask whether a number came from the notes or from a stranger.
#
# AND IT IS APPENDED RATHER THAN FOLDED IN, so the base prompt stays exactly as written and
# an ordinary notes fallback never pays a word for a rule that does not apply to it.
OLLAMA_WEB_CUE = ("These snippets came from a live web search, so begin your answer with "
                  "\"According to current web sources\". The reader must be able to tell "
                  "which world the answer came from without asking.")

# The marker is the cloud prompt's own first line about the web, so the two cannot fall out
# of step: if WEB_PROMPT is ever reworded, this stops matching and preflight 15 says so.
OLLAMA_WEB_MARKER = "live web search results"


def ollama_chat_model(cfg):
    """The local model's id, from config.json, falling back to the constant."""
    return str(cfg.get("ollama_chat_model") or OLLAMA_CHAT_MODEL).strip()


def ollama_fallback_enabled(cfg):
    """Whether the net is strung at all. False means a tired Groq refuses out loud.

    A BOOLEAN AND NOT A GUESS ABOUT THE DAEMON: this does not ping Ollama, because the
    whole point of the net is that it is tried at the moment it is needed and judged by
    what happens. Anything other than an explicit false means yes.
    """
    want = cfg.get("ollama_fallback", DEFAULT_CONFIG["ollama_fallback"])
    return not (want is False or str(want).strip().lower() in ("0", "false", "no", "off"))


def _ollama_chatml(messages):
    """The prompt as raw ChatML, with the assistant turn opened on a CLOSED think pair.

    THE SAME TWO TRICKS AS _quick_prompt(), for the same measured reason and against the
    same family of models: qwen3 is a thinking model, `think:false` does not stop it on
    Ollama 0.34, and opening the assistant turn with `<think></think>` already closed does
    - the model finds its own reasoning over and answers. That needs the server-side
    template out of the way, which is what `raw` buys, and raw means writing the ChatML
    here by hand.

    MEASURED, because it is the difference between this engine and no engine:
    qwen3:4b with the closed pair still opened "Hmm, the user is asking about Dehradun -"
    on a grounded question, which is why it is not the model this falls back to. The pair
    is kept anyway: it is what makes qwen3:1.7b usable for anyone who switches to it.
    """
    out = []
    for msg in messages:
        role = str(msg.get("role") or "user")
        content = str(msg.get("content") or "")
        if not content:
            continue
        out.append("<|im_start|>%s\n%s<|im_end|>\n" % (role, content))
    return "".join(out) + "<|im_start|>assistant\n<think>\n\n</think>\n\n"


def _ollama_fallback_messages(messages):
    """The cloud's message list, re-dressed for a small local model.

    ONE SYSTEM TURN, NOT EIGHT. What arrives here is the full assembled prompt - persona,
    capabilities, history, snippets, the lot - and handing all of it to a 7B model is how
    you get an answer about the persona instead of an answer to the question. So every
    system block is DROPPED and replaced by OLLAMA_FALLBACK_SYSTEM, and the user and
    assistant turns ride through untouched: the question and the evidence are the two
    things that must survive, and they are the two things the cloud prompt was wrapped
    around rather than part of.
    """
    kept = [m for m in messages
            if isinstance(m, dict) and str(m.get("role")) in ("user", "assistant")]
    # THE ONE THING READ OUT OF THE BLOCKS BEFORE THEY GO: whether this is a web turn. See
    # OLLAMA_WEB_CUE - §26's "say which world you are speaking from" lives in the cloud
    # prompt that is being dropped, so on a web turn it is carried across in one sentence.
    dropped = "\n".join(str(m.get("content") or "") for m in messages
                        if isinstance(m, dict) and str(m.get("role")) == "system")
    system = OLLAMA_FALLBACK_SYSTEM
    if OLLAMA_WEB_MARKER in dropped:
        system += "\n" + OLLAMA_WEB_CUE
    return [{"role": "system", "content": system}] + kept


def call_ollama(cfg, messages, image=None, status=None):
    """This machine's own answer. (answer, error), and it never raises.

    `status`, when a caller passes a dict, is filled in with the machine-readable outcome:
        reached   the daemon answered the socket AT ALL - which is the fact the routing law
                  turns on, because a daemon that answered badly has had its turn and must
                  not be queued on top of it.
        slow      it took the whole OLLAMA_CHAT_TIMEOUT_S and gave nothing. Counted as
                  reached, deliberately: a socket that accepted the request and then thought
                  for thirty seconds is a daemon that is up and busy, not a daemon that is
                  missing, and queuing it would mean asking a hung model twice.
        ttftMs    milliseconds to the FIRST TOKEN, which is the only latency number worth
                  having here - a streamed answer is already on its way to the boss while
                  the rest arrives, and total time is mostly a function of how long the
                  answer is.
        model     what actually served, for the ledger row.

    STREAMED, so ttftMs is a measurement and not a division. The whole body is still
    collected before returning - nothing downstream of this can take a generator - but the
    first chunk's arrival is timed where it actually happens.
    """
    if status is None:
        status = {}
    status.update({"reached": False, "slow": False, "ttftMs": None,
                   "model": ollama_chat_model(cfg)})
    if image is not None:
        # THE EYES HAVE NO LOCAL ENGINE and this is where that is enforced rather than
        # hoped for. The caller checks it too; this is the second lock on the same door.
        return None, "There is no local engine on this machine that can read an image."
    model = ollama_chat_model(cfg)
    url = (str(cfg.get("ollama_url") or DEFAULT_CONFIG["ollama_url"]).rstrip("/")
           + OLLAMA_CHAT_URL_PATH)
    body = json.dumps({
        "model": model,
        "prompt": _ollama_chatml(_ollama_fallback_messages(messages)),
        "raw": True,
        "stream": True,
        "keep_alive": OLLAMA_KEEP_ALIVE,
        "options": {"temperature": 0, "num_ctx": OLLAMA_FALLBACK_NUM_CTX,
                    "num_predict": OLLAMA_FALLBACK_PREDICT,
                    "stop": ["<|im_end|>"]},
    }).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST", headers={
        "Content-Type": "application/json", "User-Agent": USER_AGENT})
    started = time.monotonic()
    pieces = []
    try:
        with urllib.request.urlopen(req, timeout=OLLAMA_CHAT_TIMEOUT_S) as res:
            status["reached"] = True
            for line in res:
                line = line.strip()
                if not line:
                    continue
                try:
                    chunk = json.loads(line.decode("utf-8", "replace"))
                except ValueError:
                    continue
                piece = chunk.get("response") or ""
                if piece and status.get("ttftMs") is None:
                    status["ttftMs"] = round((time.monotonic() - started) * 1000.0, 1)
                pieces.append(piece)
                if chunk.get("done"):
                    break
    except urllib.error.HTTPError as exc:
        status["reached"] = True
        detail = ""
        try:
            detail = str(json.loads(exc.read().decode("utf-8", "replace"))
                         .get("error") or "")[:200]
        except Exception:                                      # noqa: BLE001
            pass
        if exc.code == 404:
            # THE ONE ERROR WITH A CURE IN IT. 404 from Ollama means the daemon is up and
            # the model is not pulled, which is one command away - so the sentence carries
            # the command rather than the status code.
            return None, ("This machine's Ollama does not have \"%s\" (404). Run "
                          "\"ollama pull %s\" and ask again." % (model, model))
        return None, ("The local engine returned HTTP %s. %s" % (exc.code, detail)).strip()
    except TimeoutError:
        # A BARE TimeoutError, which is what Python 3.10+ raises out of a socket read that
        # has already connected - NOT a URLError. It is the hung-model case: the daemon is
        # there, it took the request, and it is still thinking. reached AND slow, so the
        # law above reports it and does NOT queue it.
        status.update({"reached": True, "slow": True})
        return None, OLLAMA_TIMEOUT_LINE
    except urllib.error.URLError as exc:
        # THE ONLY SHAPE THAT EARNS THE QUEUE: the socket never opened. A refused
        # connection, a dead port, no daemon at all. `reached` stays false.
        reason = getattr(exc, "reason", exc)
        if isinstance(reason, TimeoutError):
            status.update({"reached": True, "slow": True})
            return None, OLLAMA_TIMEOUT_LINE
        return None, "Could not reach the local engine (%s)." % reason
    except Exception as exc:                                   # noqa: BLE001
        return None, "Unexpected error talking to the local engine: %s" % exc
    answer = "".join(pieces).strip()
    # A closed think pair can still come back as the model's own echo; strip one if it does,
    # then judge emptiness. An empty answer is a failure of a daemon that ANSWERED, so it
    # keeps `reached` true and is reported rather than queued.
    answer = re.sub(r"^<think>\s*</think>\s*", "", answer).strip()
    if not answer:
        return None, "The local engine returned an empty answer."
    return answer, None


# ---- THE ONE QUEUE. Not a retry mechanism and not a job system: a short, bounded,
# in-memory list of questions that reached NO engine at all, so that "both roads were shut
# at 4pm" is a readable fact rather than a silence. Nothing drains it automatically - a
# question answered an hour late is worse than a question answered never, and the boss
# asking again is both cheaper and more honest than a background thread guessing when.
_RETRY_QUEUE = []
_RETRY_LOCK = threading.Lock()
RETRY_QUEUE_MAX = 20


def queue_for_retry(messages, why):
    """Record one unanswerable question. Returns the depth after adding.

    THE QUESTION AND NOT THE PROMPT: the last user turn, truncated. The assembled prompt
    carries the persona, the history and whatever the notes produced, and a queue that kept
    all of it would be a transcript store with a different name.
    """
    question = ""
    for msg in reversed([m for m in (messages or []) if isinstance(m, dict)]):
        if str(msg.get("role")) == "user":
            question = str(msg.get("content") or "")[:400]
            break
    with _RETRY_LOCK:
        _RETRY_QUEUE.append({"at": time.strftime("%H:%M:%S"), "question": question,
                             "why": str(why or "")[:240]})
        while len(_RETRY_QUEUE) > RETRY_QUEUE_MAX:
            _RETRY_QUEUE.pop(0)
        depth = len(_RETRY_QUEUE)
    sys.stderr.write("  §41 queue: both roads shut, depth %d (%s)\n"
                     % (depth, str(why or "")[:140]))
    return depth


def retry_queue_state():
    """What /health publishes: a depth and the reasons. Never the questions."""
    with _RETRY_LOCK:
        return {"depth": len(_RETRY_QUEUE),
                "reasons": [row["why"][:120] for row in _RETRY_QUEUE[-3:]]}


def retry_queue_drain():
    """Empty it and return what was in it. For a harness and for a human, nothing else."""
    with _RETRY_LOCK:
        out = list(_RETRY_QUEUE)
        del _RETRY_QUEUE[:]
    return out


def ollama_warm(log=None):
    """Load the fallback model NOW, on a thread, so no question ever pays the cold prefill.

    THE SAME DISCIPLINE AS THE VECTOR STORE AND THE TRANSCRIBER, and here it is not a nicety
    but the fix for a measured failure. keep_alive -1 keeps the weights resident ONCE THEY
    ARE LOADED; it does nothing about the first load, and the first load is a cold prefill of
    a 7B model on a CPU. Measured: a real notes-sized prompt against a cold
    qwen2.5-coder:7b took 30.07 s and hit OLLAMA_CHAT_TIMEOUT_S, which preflight 30 reported
    as an intermittent 502 - and warm, the same prompt reads 0.16 s to first token and 1.8 s
    to the end, three runs running. So the cost is spent HERE, after the socket is already
    listening, rather than on whichever question is unlucky enough to be the first one Groq
    refuses.

    ONE TINY GENERATION AND NOT A PING, because /api/tags would answer without loading
    anything at all and prove nothing. num_predict 1 is the smallest thing that forces the
    weights into RAM and the graph to be built.

    Nothing here raises and nothing here is required: a machine with no Ollama gets one line
    on stderr and a fallback that will refuse politely when it is first needed, which is
    exactly what it would have done anyway.
    """
    cfg = load_config()[0]
    if not ollama_fallback_enabled(cfg):
        return False
    model = ollama_chat_model(cfg)
    url = (str(cfg.get("ollama_url") or DEFAULT_CONFIG["ollama_url"]).rstrip("/")
           + OLLAMA_CHAT_URL_PATH)
    body = json.dumps({"model": model, "prompt": "<|im_start|>user\nhi<|im_end|>\n"
                                                 "<|im_start|>assistant\n",
                       "raw": True, "stream": False, "keep_alive": OLLAMA_KEEP_ALIVE,
                       "options": {"temperature": 0, "num_ctx": OLLAMA_FALLBACK_NUM_CTX,
                                   "num_predict": 1}}).encode("utf-8")
    started = time.monotonic()
    try:
        req = urllib.request.Request(url, data=body, method="POST", headers={
            "Content-Type": "application/json", "User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=OLLAMA_WARM_TIMEOUT_S) as res:
            res.read()
    except Exception as exc:                                   # noqa: BLE001
        if log:
            log("  §41 fallback: %s did not warm (%s) - it will be tried anyway when "
                "Groq first tires" % (model, str(exc)[:90]))
        return False
    if log:
        log("  §41 fallback: %s resident in %.1fs, keep_alive forever"
            % (model, time.monotonic() - started))
    return True


def call_groq_then_local(cfg, worn, image, capability):
    """§41'S ROUTING LAW, IN ONE FUNCTION: Groq, then this machine, then the queue.

    TWO PROVIDERS DEEP AND NEVER THREE. A 401 and a 404 are NOT transient: they are
    a wrong key and a retired slug, heard as refusals that name the field. The
    transient test is the status FLAG, never a string match on the spoken sentence.
    THE EYES HAVE NO SECOND ENGINE: a tired Groq on an image is a refusal, not a hop.
    """
    status = {}
    model = (str(cfg.get("groq_vision_model") or DEFAULT_CONFIG["groq_vision_model"])
             if capability == "vision" else None)
    answer, error = call_groq(cfg, worn, image, model=model, status=status)
    if not error:
        turn_engine(capability, "groq", "ok", provider="groq")
        return answer, None
    if not status.get("transient"):
        turn_engine(capability, "groq", "failed", error, provider="groq")
        return None, error
    handover = time.monotonic()
    if image is not None:
        trigger_ms = (time.monotonic() - handover) * 1000.0
        turn_engine(capability, "none", "failed", error, provider="retry",
                    trigger_ms=trigger_ms)
        sys.stderr.write("  §41: groq vision tired and the eyes have no local engine (%s)\n"
                         % error[:120])
        return None, ("%s The eyes have no engine on this machine, sir, so I cannot look "
                      "at that locally." % error)
    if not ollama_fallback_enabled(cfg):
        turn_engine(capability, "none", "failed", error, provider="groq",
                    trigger_ms=(time.monotonic() - handover) * 1000.0)
        return None, error
    local_status = {}
    trigger_ms = (time.monotonic() - handover) * 1000.0
    sys.stderr.write("FALLBACK: DIRECT CALL TO OLLAMA\n")
    sys.stderr.write("  §41 fallback: groq %s -> local %s in %.1fms (%s)\n"
                     % (capability, ollama_chat_model(cfg), trigger_ms, error[:100]))
    answer, local_error = call_ollama(cfg, worn, image, status=local_status)
    if answer:
        turn_engine(capability, "ollama", "fallback", error, provider="ollama",
                    trigger_ms=trigger_ms, spoken=LOCAL_FALLBACK_LINE,
                    model=local_status.get("model") or ollama_chat_model(cfg))
        return answer, None
    # Ollama answered the socket: its failure (timeout, HTTP error, empty body)
    # is the reply. It is NEVER queued.
    if local_status.get("reached") or local_status.get("slow"):
        turn_engine(capability, "ollama", "failed", local_error, provider="ollama",
                    trigger_ms=trigger_ms)
        return None, local_error or OLLAMA_TIMEOUT_LINE
    # The daemon could not be reached at all: both roads are shut. The only queue.
    depth = queue_for_retry(worn, "%s | %s" % (error, local_error))
    turn_engine(capability, "queue", "failed", local_error, provider="retry",
                trigger_ms=trigger_ms, spoken=QUEUED_LINE, queued=depth)
    return QUEUED_LINE, None


def call_model(cfg, messages, image=None):
    """The one place that decides which provider gets the prompt.

    `image` is raw bytes of type FRAME_MEDIA_TYPE, or None. Both providers below
    encode it themselves, because they disagree about the shape and agree about
    nothing except the media type.
    """
    worn = wear_persona(cfg, messages)
    # THE PERSONA'S SIZE IS MEASURED HERE AND NOWHERE ELSE, because here is where it is
    # added. That ordering is the property, not the measurement: the persona block goes on
    # AFTER every eviction decision this file makes, so no budget arithmetic anywhere can
    # reach it. `plan` is completed rather than built - assemble() owns the other seven
    # blocks and this one owns the one it can see.
    plan = (getattr(_turn_local, "rec", None) or {}).get("plan")
    if isinstance(plan, dict):
        grew = sum(len(str(m.get("content") or "")) for m in worn if m.get("role") == "system") \
            - sum(len(str(m.get("content") or "")) for m in messages if m.get("role") == "system")
        for entry in plan["blocks"]:
            if entry["block"] == "persona":
                # ADDED, NOT ASSIGNED. assemble() already charged the base prompt to this
                # block - see the sizes comment there - and the first version of this line
                # assigned instead, which silently took two and a half thousand characters
                # of SYSTEM_PROMPT out of the budget at the exact moment the budget was
                # completed. The preamble's own size is kept beside it so the two halves of
                # the persona can still be told apart.
                entry["chars"] += max(0, grew)
                entry["preambleChars"] = max(0, grew)
                entry["present"] = entry["chars"] > 0
        plan["chars"] += max(0, grew)
        # THE WHOLE, MEASURED OFF THE THING ACTUALLY SENT, so that `chars == wireChars` is a
        # test of the arithmetic rather than a restatement of it. They are computed from
        # different objects by different code and must agree to the character.
        plan["wireChars"] = sum(len(str(m.get("content") or "")) for m in worn)
        plan["accounted"] = plan["chars"] == plan["wireChars"]
    provider = provider_of(cfg)
    # THE EYES HAVE THEIR OWN CAPABILITY AND ONE ENGINE. vision_engine_of() has answered
    # "groq" for every spelling since §41, so an image goes to Groq's vision slug whatever
    # the chat provider is - and when THAT tires, the law above refuses rather than hops,
    # because there is no local engine on this machine that reads an image.
    if image is not None:
        provider, capability = "groq", "vision"
    else:
        capability = "chat"
    if provider == "openrouter":
        answer, error = call_openrouter(cfg, worn, image)
    elif provider == "openai":
        answer, error = call_openai(cfg, worn, image)
    else:
        # §41: THE ONE ROUTING PATH. Groq, then this machine, then the queue - and the
        # whole of it, including which failures are allowed to hop, lives in that one
        # function rather than in a branch here. See call_groq_then_local().
        answer, error = call_groq_then_local(cfg, worn, image, capability)
    turn_call((plan or {}).get("label") or "model", worn, answer, error)
    return answer, error


def credentials_error(cfg):
    """None when the model is callable, else one sentence saying what is missing."""
    if provider_of(cfg) == "groq":
        # ONE ATTEMPT AND A PLAIN SENTENCE, which is what PART 2 asks for: this is consulted
        # before the request is built, so an empty key costs no round trip at all and there is
        # nothing for a retry storm to be made of. The sentence names the field.
        return None if groq_ready(cfg)[0] else groq_ready(cfg)[1]
    if provider_of(cfg) == "openrouter":
        key = str(cfg.get("openrouter_api_key", "")).strip()
        if _blank(key) or key.lower() in PLACEHOLDER_KEYS:
            return ("There is no OpenRouter key, so I found the relevant notes but "
                    "cannot write an answer with this brain. Paste one into "
                    "\"openrouter_api_key\" in config.json, or say \"go back to your "
                    "normal brain\" and I shall use the model that file names. No "
                    "restart needed either way.")
        return None
    if provider_of(cfg) == "openai":
        key = str(cfg.get("openai_api_key", "")).strip()
        if _blank(key) or key.lower() in PLACEHOLDER_KEYS:
            return ("No OpenAI key yet, so I found the relevant notes but cannot "
                    "write an answer. Open config.json in the project root and "
                    "replace \"PUT-YOUR-KEY-HERE\" with your key, or set "
                    "\"provider\" to \"groq\" to use the free road instead. No "
                    "restart needed.")
        return None
    # §41: THE FLOOR IS groq_ready, because the floor of provider_of() is "groq". Those two
    # defaults have to be the same word or this function answers about an engine that will
    # not be the one called - and the failure mode is the worst kind: a green /health and a
    # refusal at the first question.
    return groq_ready(cfg)[1]


# ------------------------------------------------------------------ brain swapping
#
# See THE BRAIN SWAP near the top of this file for the dictionaries and the rule.
# Everything here is about one question: is the id I am about to load one I actually
# know exists? If the answer is no, nothing loads.


def _spoken_versions(family):
    """The versions of one family that genuinely exist, for a refusal to name."""
    prefix = MODEL_FAMILIES.get(family, "").split("{v}")[0]
    found = sorted({mid[len(prefix):].split("-")[0]
                    for mid in KNOWN_MODEL_IDS
                    if prefix and mid.startswith(prefix)},
                   key=lambda v: [int(p) for p in re.findall(r"\d+", v)] or [0],
                   reverse=True)
    return found


def _phrase(items, joiner="and"):
    items = [str(i) for i in items]
    if len(items) <= 1:
        return items[0] if items else ""
    return "%s %s %s" % (", ".join(items[:-1]), joiner, items[-1])


_COMMAND_RE = re.compile(
    r"^\s*(?:please\s+)?(?:switch|swap|change|flip|turn|put|try|use|load|run|become|"
    r"be|revert|restore|go\s+back|come\s+back|return)"
    # Everything between the verb and the name, eaten in one bite. "switch brain to
    # astra" used to leave a stranded "to" in front of the name, and a stranded word
    # is the difference between a pinned name and a refusal - so the furniture of a
    # spoken request is listed here rather than hoped about. None of these words is
    # part of any model's name, and the group only matches them immediately after the
    # verb, so a name that begins with one of them is untouched.
    r"(?:\s+(?:to|on|onto|over|into|in|as|for|with|back|please|the|a|an|my|your|its|"
    r"brain|brains|model|models|mind|self))*\b", re.I)


def _said_for_display(said):
    """What was asked for, with the command stripped but the words kept verbatim -
    so a refusal quotes "GPT 6" rather than "switch to GPT 6"."""
    text = _COMMAND_RE.sub("", str(said or "").strip())
    return re.sub(r"\s+", " ", text).strip(" .,!?\"'")[:60] or "that"


def normalise_spoken(said):
    """A spoken request, reduced to just the model words. No matching happens here."""
    text = str(said or "").lower()
    text = re.sub(r"[\"'“”‘’(),.!?;:]+", " ", text)
    # The command, not the model: strip it so "switch to astra" and "astra" agree.
    text = _COMMAND_RE.sub(" ", text)
    text = re.sub(r"\b(?:please|the|a|an|your|my|it|now|instead|version|model|brain|"
                  r"claude|anthropic|openai|gpt)\b", " ", text)
    text = re.sub(r"\bpoint\b", ".", text)              # "five point one" spoken form
    text = re.sub(r"\s*\.\s*", ".", text)
    # "5 1" and "5-1" are both "5.1": the digits were always the version, and the
    # separator is a transcription accident.
    text = re.sub(r"(?<=\d)[\s\-](?=\d)", ".", text)
    return re.sub(r"\s+", " ", text).strip()


_alias_complaints = set()       # so a bad alias is reported once, not per request

# THE WORDS THAT CHANGE WHICH MODEL YOU GET. "pro", "mini", "turbo", "thinking" -
# a qualifier is never decoration, and a family-plus-version candidate that silently
# drops one has answered a different request. The catalogue teaches this set most of
# what it knows (any alphabetic segment of a real id that is not a family or a vendor
# word), and the rest is written down because the danger is the qualifier OpenRouter
# adds next week, not the one already in KNOWN_MODEL_IDS. See the leftover rule in
# resolve_spoken_model().
MODEL_QUALIFIERS = ({seg for mid in KNOWN_MODEL_IDS
                     for seg in re.split(r"[-/.]", mid.split("/")[-1])
                     if seg.isalpha()}
                    - set(MODEL_FAMILIES) - {"claude", "gpt"}) | {
    "mini", "nano", "micro", "small", "large", "turbo", "flash", "lite", "max",
    "ultra", "thinking", "reasoning", "preview", "experimental", "instruct",
    "chat", "high", "low", "fast", "pro", "plus", "air", "beta", "alpha",
}


def _alias_key(text):
    """A spoken phrase reduced to the form the pinned aliases are keyed by.

    Deliberately gentler than normalise_spoken(): it keeps the vendor word, because
    "gpt-6" is a name someone pinned on purpose and normalise_spoken() throws "gpt"
    away as noise. Hyphens become spaces so "gpt-6 astra", "gpt 6 astra" and
    "gpt6 astra" are one key, which is the whole point of pinning a spoken form -
    a transcription accident must not be the difference between the right brain and
    a refusal.
    """
    text = str(text or "").lower()
    text = _COMMAND_RE.sub(" ", text)
    # Politeness is not part of anybody's name. Both sides of the lookup - the phrase
    # you said and the key in config.json - come through this function, so dropping a
    # filler word here can only ever make the two agree.
    text = re.sub(r"\b(?:please|now|instead|thanks|thank you|the|a|an|my|your|to|"
                  r"for|me|it)\b", " ", text)
    text = re.sub(r"[^a-z0-9.]+", " ", text)
    text = re.sub(r"(?<=[a-z])(?=\d)", " ", text)          # "gpt6" -> "gpt 6"
    return re.sub(r"\s+", " ", text).strip()


def spoken_aliases(cfg=None):
    """The pinned names from config.json, keyed and checked. {} if there are none.

    Every value must be in KNOWN_MODEL_IDS. An alias for a model this server does
    not know is dropped, loudly: a pin exists to nail one of the real models down,
    and a pin that could invent one would be a way around the allowlist rather than
    a shortcut through it.

    The shipped pins are a FLOOR, not a default that a file can silently replace.
    load_config() merges config.json over DEFAULT_CONFIG key by key, so a
    "model_aliases" block in the file would otherwise take the whole dictionary with
    it, and adding one pin of your own would quietly un-pin "astra" - which is the
    exact failure these pins exist to prevent, arriving by the back door. Your block
    is laid over the shipped one: naming a key re-points it, omitting a key leaves it
    alone, and pointing one at "" retires it (with the complaint below).
    """
    if cfg is None:
        cfg = load_config()[0]
    raw = dict(DEFAULT_CONFIG.get("model_aliases") or {})
    mine = cfg.get("model_aliases")
    if isinstance(mine, dict):
        raw.update(mine)
    if not raw:
        return {}
    pinned = {}
    for spoken, model_id in raw.items():
        key = _alias_key(spoken)
        wanted = str(model_id or "").strip()
        if not key:
            continue
        if wanted not in KNOWN_MODEL_IDS:
            if key not in _alias_complaints:
                _alias_complaints.add(key)
                sys.stderr.write("  config.json: alias %r names %r, which is not a "
                                 "model I know of - ignoring it\n" % (spoken, wanted))
            continue
        pinned[key] = wanted
    return pinned


def resolve_spoken_model(said):
    """(model_id, error_payload). Exactly one of the two is None.

    Never guesses. Never returns a model whose id is not in KNOWN_MODEL_IDS, and
    never substitutes a different version of a family that was named with one.
    """
    text = normalise_spoken(said)

    # 0. THE PINNED NAMES, before anything is parsed. A phrase you nailed down in
    #    config.json means what you said it means, whatever the catalogue grows.
    pinned = spoken_aliases()
    key = _alias_key(said)
    if key and key in pinned:
        return pinned[key], None

    if not text:
        return None, {"key": "empty", "line": BRAIN_LINES["empty"]}

    # 1. An exact spoken name, or an exact id typed straight in by a caller.
    if text in SPOKEN_MODELS:
        return SPOKEN_MODELS[text], None
    raw = str(said or "").strip()
    if raw in KNOWN_MODEL_IDS:
        return raw, None

    # 1b. A whole model NAME, said out loud rather than typed: "gpt-6-astra-pro",
    #     "claude haiku 4.5". Slugified and matched against the tail of a real id,
    #     which is an identity check and not a guess - the only ids it can produce
    #     are ones that already exist, complete with whatever qualifier was said.
    #     Without this, step 2 sees "astra" and "6" in "gpt-6-astra-pro", drops the
    #     word "pro" as though it were noise, and hands over the plain model: the
    #     exact substitution this whole section exists to refuse.
    slug = _alias_key(said).replace(" ", "-")
    if slug:
        tails = [mid for mid in KNOWN_MODEL_IDS
                 if mid.split("/")[-1] == slug or mid.split("/")[-1].endswith("-" + slug)
                 or mid == slug]
        if len(tails) == 1:
            return tails[0], None

    # 2. A family plus a version, built into a candidate and then CHECKED. This is
    #    the whole safety rule: the candidate is a guess, and the set is the truth.
    words = re.findall(r"[a-z]+", text)
    version = next(iter(re.findall(r"\d+(?:\.\d+)*", text)), "")
    family = next((w for w in words if w in MODEL_FAMILIES), "")
    if family and version:
        candidate = MODEL_FAMILIES[family].format(v=version)
        leftover = [w for w in words
                    if w != family and w in MODEL_QUALIFIERS and w not in candidate]
        if candidate in KNOWN_MODEL_IDS and not leftover:
            return candidate, None
        if leftover:
            # It named the family and the version and then said something else as
            # well. Loading the candidate here would be answering a different request.
            wanted = " ".join(words + ([version] if version else [])).upper()
            versions = _spoken_versions(family)
            return None, {"key": "noid", "family": family.upper(),
                          "versions": versions,
                          "line": BRAIN_LINES["noid"].format(
                              wanted=_said_for_display(said).upper() or wanted,
                              family=family.upper(),
                              versions=_phrase(versions) or "nothing in that family")}
        # It parsed perfectly and does not exist. The temptation here is to load the
        # nearest version of the same family; that is the bug this file was written
        # to prevent, so it refuses and says what it has instead.
        versions = _spoken_versions(family)
        return None, {"key": "noid", "family": family.upper(), "versions": versions,
                      "line": BRAIN_LINES["noid"].format(
                          wanted="%s %s" % (family.upper(), version),
                          family=family.upper(),
                          versions=_phrase(versions) or "nothing in that family")}

    if family and not version:
        # A family is not a model. Picking one on your behalf is precisely the lie.
        versions = _spoken_versions(family)
        return None, {"key": "noversion", "family": family.upper(),
                      "versions": versions,
                      "line": BRAIN_LINES["noversion"].format(
                          family=family.upper(), versions=_phrase(versions, "and"))}

    return None, {"key": "unknown", "names": sorted(SPOKEN_MODELS),
                  "line": BRAIN_LINES["unknown"].format(
                      wanted=_said_for_display(said),
                      names=_phrase([display_label(v) for _, v in
                                     sorted(SPOKEN_MODELS.items())], "or"))}


def brain_state():
    """What is answering right now, and what a restart would bring back."""
    cfg = load_config()[0]                      # already carries the override
    on_disk = load_config(apply_override=False)[0]
    with _brain_lock:
        override = _brain
    active = model_label(cfg)
    return {
        "model": active,
        # THE PROVIDER IS ON THE CHIP FOR GROQ AND FOR NOTHING ELSE, and the asymmetry is the
        # requirement rather than an oversight. OpenAI and OpenRouter serve the same small
        # set of pinned names, so the model id alone says which is answering; Groq
        # serves ids nobody here has seen before, at a latency the boss will notice, and the
        # one question a chip has to answer during an incident is "am I on the fast borrowed
        # brain or my own?". Prefixing only groq also keeps every existing label byte-identical,
        # which is what lets the three standing harnesses that read this chip stay green.
        "label": (("GROQ · " + display_label(active)) if provider_of(cfg) == "groq"
                  else display_label(active)),
        "provider": provider_of(cfg),
        "swapped": bool(override),
        "keyConfigured": credentials_error(cfg) is None,
        # What "go back to your normal brain" and a restart both mean, which is the
        # same thing by construction: this is read from the file, not from memory.
        "configModel": model_label(on_disk),
        # Prefixed by the same rule as `label` above, so "zero residue" can be asserted as one
        # string comparison: after a switch and a switch back, label == configLabel. Two
        # different rules for the two fields would make that comparison pass on a page still
        # talking to Groq.
        "configLabel": (("GROQ · " + display_label(model_label(on_disk)))
                        if provider_of(on_disk) == "groq"
                        else display_label(model_label(on_disk))),
        "configProvider": provider_of(on_disk),
    }


def pretty_name(model_id):
    """The name a sentence may use. Never a slug, by construction."""
    return PRETTY_NAMES.get(str(model_id or ""), display_label(model_id))


def curated_intro(model_id, advance=True):
    """The next scripted line for this brain, or None if no pool covers it.

    Rotates. `advance=False` looks without spending, which is what a test of the
    pools themselves wants.
    """
    model_id = str(model_id or "")
    for index, (pattern, pool) in enumerate(CURATED_LINES):
        if not pool or not pattern.search(model_id):
            continue
        with _brain_lock:
            turn = _curated_turn.get(index)
            if turn is None:
                # A rotation, not a script: where it starts is nobody's business.
                turn = random.randrange(len(pool))
            if advance:
                _curated_turn[index] = (turn + 1) % len(pool)
        return pool[turn % len(pool)]
    return None


def _usable_intro(text, model_id):
    """A model's own introduction, or None. The rule, not the request.

    The middle rung of the ladder is the one that fails in a way nobody notices for a
    week: a reasoning model spends its budget thinking, returns "", and the swap has
    been quietly reading its fallback ever since. So an introduction earns its place -
    one line, short, no apology, and above all no slug. "GPT-6 Astra online, sir" is a
    butler; "openai/gpt-6-astra online" is a status page.
    """
    line = re.sub(r"\s+", " ", str(text or "")).strip().strip('"“”')
    if not line or len(line) > BRAIN_INTRO_MAX_CHARS:
        return None
    if not re.search(r"[a-z]", line, re.I):
        return None
    if BRAIN_INTRO_BANNED.search(line):
        return None
    if str(model_id or "").lower() in line.lower():
        return None
    return line


def brain_intro(model_id, cfg=None, ask=None):
    """(line, source) for a brain that has just been fitted. Never raises.

    The ladder, in order, and each rung is why the next one exists:

      curated  - a pool we wrote, rotated, instant and free.
      model    - the new brain's own dry sentence, if it manages one worth saying.
      fallback - BRAIN_LINES["swapped"] with a pretty name.

    Nothing here changes the brain; it is called after the swap, so "ask the new
    model" means the new model.
    """
    line = curated_intro(model_id)
    if line:
        return line, "curated"

    if ask is None:
        ask = BRAIN_INTRO_ASK
    pretty = pretty_name(model_id)
    if ask:
        if cfg is None:
            cfg = load_config()[0]
        if credentials_error(cfg) is None:
            try:
                said, error = call_model(cfg, [
                    {"role": "system",
                     "content": BRAIN_INTRO_PROMPT.format(pretty=pretty)},
                    {"role": "user", "content": "Introduce yourself."}])
                if not error:
                    usable = _usable_intro(said, model_id)
                    if usable:
                        return usable, "model"
            except Exception:                                  # noqa: BLE001
                # A brain that cannot introduce itself is still fitted. The swap is
                # the thing that must not fail here.
                pass

    return BRAIN_LINES["swapped"].format(label=pretty), "fallback"


# THE ONE VOICE. Every door that changes the brain arrives here - the chip's menu, a
# spoken sentence, the control tag a chat answer may carry, and a bare curl. It is the
# only place in the project that decides what a swap SAYS, which is why the curated
# pools, the model's own introduction and the pretty-name fallback live one function
# deeper still: three doors deciding for themselves is how a project ends up with one
# charming swap and two that read like a status page.
def swap_to(model_id, door="voice", ask=None):
    """(status, payload) for a swap onto an id, which is checked here regardless."""
    global _brain, _chat_engine
    model_id = str(model_id or "")
    if model_id not in KNOWN_MODEL_IDS:
        # Not reachable through swap_brain(), which resolves first. It is here because
        # swap_to() is public and the allowlist is not negotiable at any door.
        line = BRAIN_LINES["unknown"].format(
            wanted=_said_for_display(model_id),
            names=_phrase([display_label(v) for _, v in sorted(SPOKEN_MODELS.items())],
                          "or"))
        return 409, dict(brain_state(), ok=False, kind="model", nodes=[],
                         refused="unknown", error=line, answer=line, door=door,
                         intro=None, available=sorted(SPOKEN_MODELS))

    with _brain_lock:
        already = (_brain == model_id)
        _brain = model_id
        # A MODEL SWAP CLEARS THE PROVIDER SWAP. "Be Astra" after "switch to Groq" means
        # Astra on OpenRouter, not Astra-on-Groq, which is not a thing that exists. The two
        # overrides are mutually exclusive and this is one of the three lines that make it so.
        _chat_engine = None
    state = brain_state()

    if already:
        # No introduction for a brain that has not changed: being told twice who you
        # are talking to is how a good line stops being a good line.
        line = BRAIN_LINES["already"].format(label=pretty_name(model_id))
        source = "already"
    else:
        line, source = brain_intro(model_id, ask=ask)
    if not state["keyConfigured"]:
        line += BRAIN_LINES["nokey"]
    return 200, dict(state, ok=True, kind="model", nodes=[], answer=line,
                     restored=False, door=door, intro=source)


def swap_to_groq(door="voice"):
    """(status, payload) for "switch to Groq". Runtime only; config.json is never written.

    THE ONE CHEAP PING, AND WHY IT IS NOT POLLING. A switch onto an engine nobody has called
    yet is a claim, and the boss finds out whether the claim was true on his next real
    question - at which point he has lost that question. So the switch spends one four-token
    completion to find out now, and reports what it found in the same sentence as the switch.
    ONE. There is no health loop, no periodic probe and no retry: an engine that answers a ping
    and fails a minute later is what the Fallback Law is for, and a poller would add a
    per-minute cost to a borrowed account for information that goes stale immediately.

    AND A FAILED PING DOES NOT UNDO THE SWITCH. It is reported, loudly, in the line he hears -
    because a switch that silently refuses to happen leaves the chip and his mental model
    disagreeing, and "say it again, it did not take" is a worse afternoon than "it is on and it
    is not answering". The one exception is a missing key, which is refused OUTRIGHT below: an
    engine with no credential cannot serve a single question, so switching onto it would be
    switching onto an outage.
    """
    global _brain, _chat_engine
    cfg = load_config(apply_override=False)[0]
    ready, why = groq_ready(cfg)
    if not ready:
        # ONE ATTEMPT, NO REQUEST AT ALL, PROVIDER UNCHANGED. The refusal names the field and
        # the state it did not change, exactly like every other refusal at this door.
        return 409, dict(brain_state(), ok=False, kind="model", nodes=[],
                         refused="nokey", error=why, answer=why, door=door, intro=None,
                         available=sorted(SPOKEN_MODELS))
    with _brain_lock:
        already = (_chat_engine == "groq")
        _chat_engine = "groq"
        _brain = None                                  # mutually exclusive; see swap_to()
    state = brain_state()
    cfg = load_config()[0]
    line = ("Groq it is, sir: %s. Do let me know if you notice the pace."
            % pretty_name(state["model"]))
    if already:
        line = BRAIN_LINES["already"].format(label=pretty_name(state["model"]))
    ping, error = (None, "")
    if not already:
        ping, error = call_groq(
            cfg, [{"role": "user", "content": "Reply with the single word: ready."}])
        if error:
            line += (" I cannot get a word out of it yet, mind: %s" % error)
    return 200, dict(state, ok=True, kind="model", nodes=[], answer=line,
                     restored=False, door=door, intro="groq",
                     ping=bool(ping) and not error, pingError=error or "")


# THE THREE OTHER FLIPS, AND THE WORDS EACH ONE WILL ACCEPT. A whitelist rather than a
# passthrough: ear_stt = "grok" would otherwise resolve to "not groq", which is "browser", and
# the boss would be told the flip worked while nothing whatever had changed. Every word here
# is one an *_of() resolver already understands, so there is no second spelling table.
ENGINE_WORDS = {
    "ear": ("browser", "groq"),
    "vision": ("groq",),
    "voice": ("piper", "web", "orpheus"),
}


def engines_state(cfg=None):
    """The four engines as they are SERVING, plus what config.json would say on a restart.

    `served` is the resolver's answer with the overrides applied; `configured` is the same
    resolver with them ignored. The two differing is not a fault - it is the whole point of a
    runtime flip - and publishing both is what makes "flipping back is lossless" checkable:
    after a reset the two must agree again, field for field.
    """
    cfg = cfg if cfg is not None else load_config()[0]
    base = load_config(apply_override=False)[0]
    with _brain_lock:
        over = dict(_engines)
        over["chat"] = _chat_engine
    return {
        "served": {"chat": provider_of(cfg), "ear": ear_stt_of(cfg),
                   "vision": vision_engine_of(cfg), "voice": voice_engine_of(cfg)},
        "configured": {"chat": provider_of(base), "ear": ear_stt_of(base),
                       "vision": vision_engine_of(base), "voice": voice_engine_of(base)},
        # Which of the four are being held away from the file, so a harness never has to
        # infer an override from two labels that happen to differ.
        "overrides": {k: (v or "") for k, v in over.items()},
        "models": {"chat": model_label(cfg),
                   "vision": str(cfg.get("groq_vision_model") or
                                 DEFAULT_CONFIG["groq_vision_model"]),
                   "ear": str(cfg.get("groq_stt_model") or DEFAULT_CONFIG["groq_stt_model"]),
                   "voice": (str(cfg.get("groq_tts_model") or DEFAULT_CONFIG["groq_tts_model"])
                             if voice_engine_of(cfg) == "orpheus"
                             else str(cfg.get("voice_model") or DEFAULT_CONFIG["voice_model"]))},
        "groqKey": groq_digest(cfg),
        # WHAT HAS BEEN SPENT AND WHAT HAPPENED, both published because two of §28's laws are
        # arithmetic: "one cheap ping, no polling" is calls going up by exactly one, and
        # "zero Groq calls" is a counter that did not move. The ring carries the fallback rows
        # for the voice and the ear, which have no turn record to be written into.
        "calls": dict(_GROQ_SEEN),
        "log": list(_ENGINE_LOG),
    }


def set_engines(data):
    """(status, payload) for POST /engines. Runtime only; config.json is never written.

    One flag at a time or all of them at once, and {"reset": true} puts every one of the four
    back to the file - which is also what a restart does, and what "zero residue" means here.
    """
    global _chat_engine, _brain
    asked = {k: str(data.get(k) or "").strip().lower()
             for k in ("chat", "ear", "vision", "voice") if data.get(k) is not None}
    reset = bool(data.get("reset"))
    if not asked and not reset:
        return 400, {"ok": False, "kind": "engines", "error":
                     "Name an engine: ear, vision, voice or chat - or send {\"reset\": true}.",
                     "engines": engines_state()}
    # EVERY WORD IS CHECKED BEFORE ANY IS APPLIED, so a request naming two engines cannot flip
    # the first and refuse the second and leave the house half-changed.
    for which, word in asked.items():
        legal = ("groq",) if which == "chat" else ENGINE_WORDS[which]
        if word not in legal:
            return 400, {"ok": False, "kind": "engines", "engines": engines_state(),
                         "error": "The %s engine answers to %s, not \"%s\"."
                                  % (which, " or ".join('"%s"' % w for w in legal), word)}
    # AND A GROQ FLIP WITH NO KEY IS REFUSED RATHER THAN ACCEPTED-AND-BROKEN, in the same
    # sentence naming the same config field the chat swap uses. Nothing is requested here:
    # this is the same one-attempt-then-refuse law, at the flag rather than at the call.
    if "groq" in asked.values() or asked.get("voice") == "orpheus":
        ready, why = groq_ready(load_config()[0])
        if not ready:
            return 409, {"ok": False, "kind": "engines", "refused": "nokey",
                         "error": why, "engines": engines_state()}
    with _brain_lock:
        if reset:
            for k in _engines:
                _engines[k] = None
            _chat_engine = None
        for which, word in asked.items():
            if which == "chat":
                _chat_engine = "groq" if word == "groq" else None
                if word == "groq":
                    _brain = None                      # mutually exclusive; see swap_to()
            else:
                _engines[which] = word
    return 200, {"ok": True, "kind": "engines", "reset": reset,
                 "engines": engines_state()}


def restore_brain(door="voice"):
    """Back to whatever config.json says, which is also what a restart means."""
    global _brain, _chat_engine
    with _brain_lock:
        # BOTH OVERRIDES, AND "was" IS TRUE IF EITHER WAS SET. "Go back to your normal brain"
        # is the one direction that is always safe, and it has to mean ALL the way back - a
        # restore that cleared the model override and left the process talking to Groq would
        # report "back to my usual faculties" while answering from a borrowed engine. That is
        # the exact shape of a residue bug and it would read as correct in every log.
        was = bool(_brain or _chat_engine)
        _brain = None
        _chat_engine = None
    state = brain_state()
    line = (BRAIN_LINES["restored"] if was else BRAIN_LINES["already"]).format(
        label=pretty_name(state["model"]))
    return 200, dict(state, ok=True, kind="model", nodes=[], answer=line,
                     restored=True, door=door, intro="restored")


def swap_brain(said, door="voice", ask=None):
    """(status, payload) for POST /model. Runtime only; config.json is never written.

    The words door: it resolves, then hands over to swap_to(), so a sentence and a
    button press cannot say different things about the same swap.
    """
    raw = str(said or "")
    text = normalise_spoken(raw)

    # "go back to your normal brain" - drop the override and let config.json speak.
    # A bare "go back" counts: home is the one direction that is always safe.
    if RESTORE_RE.search(raw) or text in ("back", "normal", "usual", "default") or \
            (not text and re.search(r"\bback\b", raw, re.I)):
        return restore_brain(door=door)

    # GROQ IS A PROVIDER AND IS ANSWERED BEFORE THE MODEL RESOLVER, which is the whole reason
    # this branch is five lines above resolve_spoken_model() rather than inside it. The
    # resolver's job is to turn a spoken phrase into one id from KNOWN_MODEL_IDS and to refuse
    # rather than guess; "groq" is not a model and putting it in that allowlist would make
    # every refusal message below have to explain a word that is not a vintage of anything.
    # So: the allowlist, the pinned aliases, the family refusals and the three BRAIN_LINES
    # refusals are all byte-identical to what they were, and the word "groq" is handled here.
    if re.fullmatch(r"(?:switch\s+to\s+|use\s+|go\s+)?groq(?:\s*cloud)?", text or "", re.I):
        return swap_to_groq(door=door)

    model_id, refusal = resolve_spoken_model(raw)
    if refusal is not None:
        # A refusal reports the state it did NOT change, so the chip and the voice
        # agree that nothing moved.
        return 409, dict(brain_state(), ok=False, kind="model", nodes=[],
                         refused=refusal["key"], error=refusal["line"],
                         answer=refusal["line"], door=door, intro=None,
                         available=sorted(SPOKEN_MODELS))

    return swap_to(model_id, door=door, ask=ask)


# THE THIRD DOOR. "You are being rather slow today, fetch something sharper" is a
# brain request that SWAP_RE will never catch, because it names no model and no
# command verb - it arrives as ordinary conversation. So the chat brain may answer it
# with a control tag instead of prose, and the tag is executed here.
#
# Three things keep this from being a model that changes its own brain on a whim:
# the tag is only taught to SMALLTALK_PROMPT, where a request about YOU lands; the id
# it names is resolved by the same allowlist as every other door, which refuses rather
# than substitutes; and whatever prose came with it is DISCARDED. The model may ask
# for the swap. It may not narrate it - that is what one voice means.
BRAIN_TAG_RE = re.compile(r"\[\[\s*(?:brain|model)\s*:\s*([^\]\n]{1,60}?)\s*\]\]",
                          re.I)


def brain_tag(answer):
    """(what the answer asked to become or None, the answer with the tag stripped)."""
    text = str(answer or "")
    found = BRAIN_TAG_RE.search(text)
    if not found:
        return None, text
    return found.group(1).strip(), re.sub(r"\s{2,}", " ",
                                          BRAIN_TAG_RE.sub("", text)).strip()


# --------------------------------------------------------------------- capturing
#
# "remember that X" PROPOSES a real markdown file, and a word of consent writes it.
#
# THE GATE ARRIVED IN PART 8 AND IT CLOSED THE LAST HOLE IN THIS SERVER'S OWN LAW.
# Everything else that touches the world here - the calendar, the email, the voice, the
# minutes - goes through one slot, one TTL and one Doorman, and is spoken as a proposal
# before it happens. The capture did not. "remember that the deposit is forty thousand"
# was heard and WRITTEN, in the same breath, with no card and no chance to say no, into a
# collection that is indexed and quoted back. It was the oldest write in the project, which
# is the whole reason it predated the law rather than being exempt from it.
#
# So remember() now mints a proposal for the save_note hand and returns; tools/save_note.py
# does the writing, after a yes, through hands.execute() like every other hand. What is
# left in this section is the part that is NOT the write: reading the trigger off the
# sentence, titling the thought, and - once the hand has run - folding the new file into the
# live index. Three rules it still exists to enforce:
#
#   1. Writing a file is not indexing it. A completed capture re-reads the corpus through
#      build.py's OWN functions and rewrites both notes-index.json and
#      graph-data.js, so the new note is retrievable by /chat on the very next
#      question with no rebuild step. Nothing here reimplements build.py's linking
#      rules - it imports them, so the two can never drift apart. This is also why the
#      re-index could not move into the script: it must happen IN THIS PROCESS, keeping
#      every node id the browser is already holding.
#   2. A capture never fails quietly. Every path below returns a spoken line, and
#      "written but not indexed" is reported as its own distinct failure rather
#      than being rounded up to success.
#   3. NO CREDENTIAL ENTERS A NOTE. secretscan's opinion is taken here, at proposal time,
#      so he is told before a card goes up - and taken AGAIN by the script, because the
#      server is not the only thing that can call a hand.

CAPTURE_RE = re.compile(r"""^[\s"'“‘(\[]*remember\s+that\b[\s,:;.\-–—]*""",
                        re.IGNORECASE)
CAPTURE_DIR = "captures"      # created inside the notes directory, not the project
TITLE_WORDS = 8               # a title is the first few words, not the whole thought
TITLE_SKIP = {"the", "a", "an", "that", "this", "my", "our", "we", "i", "it",
              "there", "these", "those"}


def notes_root():
    """The notes directory build.py indexed, taken from the index it wrote."""
    rel = str((_index.get("meta") or {}).get("notesRoot") or "notes").strip()
    path = os.path.normpath(os.path.join(ROOT, rel.replace("/", os.sep)))
    return path if os.path.isdir(path) else ROOT


def capture_body(text):
    """Strip the trigger phrase, leaving the thought itself as a tidy sentence."""
    body = CAPTURE_RE.sub("", str(text or "")).strip().strip('"”’\'')
    body = re.sub(r"\s+", " ", body).strip()
    if not body:
        return ""
    body = body[0].upper() + body[1:]
    if body[-1] not in ".!?":
        body += "."
    return body


def capture_title(body):
    """'the finish window should be 900ms' -> 'Finish Window Should Be 900ms'."""
    words = re.findall(r"[\w']+", body)
    while words and words[0].lower() in TITLE_SKIP:
        words.pop(0)
    words = words[:TITLE_WORDS]
    if not words:
        return "Captured Note"
    # build.py's own labeller, so a capture is titled like every other note.
    return build.label_from_filename("-".join(words))


# THE WRITE USED TO BE HERE, in a function called write_capture(), and it is gone rather
# than kept behind a flag. It moved to tools/save_note.py, which is the only place a note is
# made now, because two writers is how a gate gets walked around: the day somebody calls the
# in-process one "just for this case", the card stops being the thing that decides. The
# slug, the -2 suffix, the read-back and the containment check all went with it, unchanged
# in substance. Nothing calls it, so nothing is left of it. See the section header above.


def reindex_preserving_ids():
    """Re-run build.py's indexing in-process, keeping every existing node id.

    build.py numbers nodes in directory-walk order, so a capture landing in
    captures/ would renumber notes that sort after it - and the browser already on
    screen is holding those ids, as is the camera. So the walk is reordered to match
    the index we already have, genuinely new files are appended at the end, and only
    then is id reassigned. Deleting a note file externally still shifts ids; that is
    a "re-run build.py and reload" situation, not a capture.

    Returns (nodes, links) in build.py's shape, or raises.
    """
    root = notes_root()
    nodes = build.build_nodes(root, ROOT)
    with _lock:
        order = {n.get("file"): i for i, n in enumerate(_index["notes"])}
    nodes.sort(key=lambda n: (order.get(n["file"], 10 ** 6), n["file"]))
    for i, node in enumerate(nodes):
        node["id"] = i                        # the id == index contract, preserved

    links, unresolved = build.build_links(nodes)
    build.write_outputs(ROOT, root, nodes, links, unresolved)

    # Force the brain to re-read what we just wrote, rather than trusting mtime
    # granularity to notice a file rewritten inside the same second.
    with _lock:
        _index["mtime"] = 0
    ensure_index()
    return nodes, links


def pick_anchor(new_id, links, title, body):
    """The existing note the capture is most related to - where the star is born.

    Preference is the strongest edge build.py just drew, since that is the project's
    own definition of "related". A capture that links to nothing at all falls back
    to keyword retrieval, so it is still born somewhere meaningful.
    """
    rank = {"wikilink": 0, "mention": 1, "shared": 2}
    touching = [l for l in links if new_id in (l["source"], l["target"])]
    if touching:
        best = min(touching, key=lambda l: (rank.get(l["kind"], 9),
                                            -int(l.get("weight") or 1)))
        return best["target"] if best["source"] == new_id else best["source"]

    # No edges at all - a thought about nothing already in the collection. Fall back
    # to plain retrieval, excluding the capture itself, so it is still born beside
    # whatever it has most in common with rather than somewhere arbitrary.
    for i, score in score_notes(title + ". " + body, top_k=3, skip={new_id}):
        if score > 0:
            return i
    return None          # genuinely unrelated to everything: the viewer centres it


def remember(text):
    """"remember that X" -> a PROPOSAL for the save_note hand. (status, payload), never raises.

    THE THREE WAYS OUT, and the order is the argument:

      NOTHING FOLLOWED THE TRIGGER. "remember that" and then a change of heart. Refused
        before anything else, because there is no thought here to put on a card. This is the
        one refusal that predates the gate and it is unchanged.
      IT CARRIES A CREDENTIAL. Refused at PROPOSAL time, so he hears why before a card goes
        up rather than after approving one. secretscan's opinion, which tools/save_note.py
        takes again for itself - see the section header for why both.
      OTHERWISE A CARD. hands.propose() mints it into the same single slot the calendar and
        the email use, with the same TTL and the same Doorman behind it. Nothing is on disk
        when this returns, and that sentence is the whole of PART 8's remember hand.

    WHAT IT DOES NOT DO ANY MORE: write. The capture was the last write in this server that
    happened without a word of consent, and it is not one now.
    """
    body = capture_body(text)
    if not body:
        return 400, {"ok": False, "answer": CAPTURE_LINES["empty"],
                     "error": "nothing followed \"remember that\"",
                     "nodes": [], "kind": "capture"}

    hits = secretscan.found(body)
    if hits:
        # The KIND and never the value, in a line he will hear and a log that keeps it.
        return 400, {"ok": False, "answer": CAPTURE_LINES["secret"].format(
                         reason=secretscan.reason(hits)),
                     "error": "the thought carries a credential",
                     "refused": "credential", "nodes": [], "kind": "capture"}

    ensure_index()
    title = capture_title(body)
    status, payload = hands.propose("save_note", {"title": title, "body": body},
                                    door="capture")
    # `kind` is what the page routes on, and a capture that is now a proposal must still
    # arrive labelled as one: the capture path speaks its own lines and draws its own star.
    payload["kind"] = "capture"
    payload.setdefault("nodes", [])
    payload["title"] = title
    return status, payload


def capture_landed():
    """The save_note hand has run. Fold the new file into the live index. (payload or None).

    WHY THIS IS NOT IN THE SCRIPT, and it is the only reason the write and the indexing are
    in two different processes: the ids must be preserved IN THIS ONE. The browser on screen
    is holding node ids and so is the camera, and reindex_preserving_ids() keeps them by
    reordering the walk to match the index we already have. A subprocess cannot do that; it
    would renumber every note that sorts after captures/ and the star the employer is
    looking at would quietly become a different note.

    HOW IT KNOWS WHICH FILE IS NEW, without parsing the script's sentence. The set of files
    in the index BEFORE the rebuild is taken first; the new one is the difference. That is
    one fact read from two snapshots of our own state, rather than a filename scraped out of
    a line of prose that exists to be spoken to a person.

    Returns the graph payload the page needs to splice the star in, or a dict carrying
    `error` when the file is on disk but did not make it into the galaxy - which is a real
    and distinct failure, never rounded up.
    """
    with _lock:
        before = {n.get("file") for n in _index["notes"]}
    try:
        nodes, links = reindex_preserving_ids()
    except Exception as exc:                                    # noqa: BLE001
        reason = "indexing failed (%s)" % exc
        return {"ok": False, "error": reason,
                "answer": CAPTURE_LINES["unindexed"].format(reason=reason)}

    fresh = [n for n in nodes if n["file"] not in before]
    if not fresh:
        # THE DISTINCT FAILURE THIS WHOLE SECTION EXISTS TO CATCH: on disk, invisible to
        # /chat. The hand said it wrote a file and the galaxy does not have it.
        reason = "the note is on disk but did not make it into the index"
        return {"ok": False, "error": reason,
                "answer": CAPTURE_LINES["unindexed"].format(reason=reason)}
    # A rebuild could in principle turn up more than one unseen file - somebody dropped a
    # note in by hand while the card was up. The capture is the newest of them.
    node = max(fresh, key=lambda n: os.path.getmtime(
        os.path.join(ROOT, n["file"].replace("/", os.sep)))
        if os.path.exists(os.path.join(ROOT, n["file"].replace("/", os.sep))) else 0)

    degree = 0
    for link in links:
        if node["id"] in (link["source"], link["target"]):
            degree += 1

    return {
        "ok": True,
        "file": node["file"],
        "title": node["label"],
        "anchor": pick_anchor(node["id"], links, node["label"],
                              str(node.get("excerpt") or "")),
        "nodes": [node["id"]],
        # Graph shape, matching graph-data.js exactly, so the viewer can drop it
        # straight into GRAPH.nodes.
        "node": {
            "id": node["id"], "label": node["label"], "group": node["group"],
            "file": node["file"], "slug": node["slug"],
            "excerpt": node["excerpt"], "words": node["words"], "degree": degree,
        },
        # The whole authoritative link set, not just the new edges: a capture can
        # resolve a wikilink that was dangling, which changes edges the viewer
        # already holds. Replacing the lot is cheaper than reconciling it.
        "links": links,
        "groups": sorted({n["group"] for n in nodes}),
        "noteCount": len(nodes),
        "linkCount": len(links),
    }


# ----------------------------------------------------------------------- the census
#
# SEVENTEEN QUESTIONS, THREE CHAPTERS, AND NOT ONE WORD OF INFERENCE.
#
# The corpus this galaxy was built to show was never his: a dummy cafe, an invoice
# importer, a cold brew recipe. PART 8 moved that to quarantine and left three true notes
# behind, and the two honest ways to grow it from there are that he says something worth
# keeping - the remember hand, above - or that he is ASKED. This is the asking.
#
# THE WHOLE ROUTE IS A PROPOSAL, and that is the only interesting thing about it. An
# intake form that wrote seventeen files as fast as they were typed would be the capture
# defect again, seventeen times over, and in a folder that is indexed and quoted back. So
# /census/answer ends in hands.propose("save_note", ..., folder="census") and returns a
# card. The Census has no writer of its own, no route that writes, and no way to get one:
# there is exactly one thing in this project that makes a note, and it is a registry hand
# behind the Halt Law.
#
# THREE REFUSALS, IN THIS ORDER, and the order is the argument:
#
#   NOT ONE OF THE SEVENTEEN. An id off the list is refused before the answer is even
#     read. The bank is the boundary of what this house asks about a person, and a route
#     that filed an answer to a question nobody wrote would move that boundary to
#     whatever the caller typed.
#   NOTHING SAID. A skipped question is a skipped question - it is not a note saying
#     nothing - and it stays unanswered so the board can offer it again.
#   A CREDENTIAL. secretscan's opinion, at proposal time, so he hears why before a card
#     goes up; tools/save_note.py takes it again for itself. "What are you learning at
#     the moment" is not a question anybody expects to produce a password, which is
#     exactly why the scan is here rather than only where it was expected to be needed.
#
# AND THE ANSWERED-STATE IS READ, NEVER REMEMBERED. census.state() lists the folder and
# matches filenames against each question's slug. So deleting a note re-opens its
# question, writing one by hand closes it, and the board cannot claim nine of seventeen
# while the folder holds eight. The failure mode of the alternative - a counter in this
# process - is a progress bar that is wrong until the next restart.
CENSUS_LINES = {
    "unknown": "That is not one of the Census questions, sir, so I have nothing to file "
               "it under. Open the Census and it will put the next one to you.",
    "empty": "You have not answered it yet, sir. Say the word and I shall put it to you "
             "again, or leave it and I shall ask about something else.",
    "secret": "I will not write that down, sir: {reason}, and a Census note is indexed "
              "and read back. Say it again without the value.",
    "done": "That is the whole Census answered, sir - all seventeen. Anything further "
            "goes in as a thought you had rather than a question I asked.",
}


def census_snapshot():
    """The whole intake as the board reads it, plus the question to put next.

    ensure_index() first, because notes_root() is taken out of the index's own metadata -
    the Census must file into the folder build.py actually indexed and not into a second
    `notes` directory that happens to sit beside it.
    """
    ensure_index()
    root = notes_root()
    snap = census.state(root)
    nxt = census.next_question(root)
    snap["next"] = nxt
    snap["ok"] = True
    snap["kind"] = "census"
    snap["nodes"] = []
    snap["line"] = CENSUS_LINES["done"] if nxt is None else str(nxt["ask"])
    return snap


def census_answer(qid, answer):
    """One answer -> a save_note PROPOSAL into notes/census/. (status, payload).

    Never raises and never writes. The payload is the pending card the page puts up, with
    `kind` set to "census" so the viewer can tell a Census answer from a spoken capture
    when the star is born - the two take the same road out of settleProposal().
    """
    got = census.question(qid)
    if not got:
        return 400, {"ok": False, "answer": CENSUS_LINES["unknown"],
                     "error": "%r is not a Census question" % str(qid)[:40],
                     "nodes": [], "kind": "census"}

    title, body = census.note_for(got["id"], answer)
    if not title:
        return 400, {"ok": False, "answer": CENSUS_LINES["empty"],
                     "error": body, "question": got["id"],
                     "nodes": [], "kind": "census"}

    hits = secretscan.found(body)
    if hits:
        # The KIND and never the value, in a line he will hear and a log that keeps it.
        return 400, {"ok": False, "answer": CENSUS_LINES["secret"].format(
                         reason=secretscan.reason(hits)),
                     "error": "the answer carries a credential",
                     "refused": "credential", "question": got["id"],
                     "nodes": [], "kind": "census"}

    status, payload = hands.propose("save_note",
                                    {"title": title, "body": body, "folder": census.FOLDER},
                                    door="census")
    payload["kind"] = "census"
    payload.setdefault("nodes", [])
    payload["title"] = title
    payload["question"] = got["id"]
    payload["chapter"] = got["chapter"]
    return status, payload


# ----------------------------------------------------------------------- seeing
#
# POST /see judges ONE frame of the user's own screen, grabbed at the moment they
# asked. Three rules hold this honest, and all three are enforced here rather than
# trusted to the caller:
#
#   1. A frame arrives with every request or there is no answer. Nothing is cached
#      here - there is no "last frame" variable to fall back to, by construction.
#      If the share has ended, the page says so and never reaches this code.
#   2. The declared media type is checked against the actual bytes. A JPEG that is
#      really a PNG is refused by name, because that mismatch is invisible at every
#      other layer and makes the whole feature look dead.
#   3. Nothing about the screen enters the conversation history. A screen question is
#      answered from the picture in front of it or not at all, so a later question
#      can never be answered from the memory of an earlier frame.


def check_frame(declared, data, width, height, age_ms):
    """(line_key, detail) if this frame may not be judged, else None."""
    base = str(declared or "").split(";")[0].strip().lower()
    if not data:
        return "noframe", "the request carried no image at all."
    if base != FRAME_MEDIA_TYPE:
        return "mismatch", ("the frame was sent as \"%s\" and this endpoint reads "
                            "%s." % (base or "nothing", FRAME_MEDIA_TYPE))
    if not data.startswith(FRAME_MAGIC):
        # The trap in person: Content-Type says JPEG, the bytes say otherwise.
        return "mismatch", ("the frame was declared %s but the bytes are not a JPEG "
                            "(they begin %s), so the encoder and the header "
                            "disagree." % (FRAME_MEDIA_TYPE,
                                           data[:4].hex(" ") or "empty"))
    if len(data) < FRAME_MIN_BYTES:
        return "tiny", ("the frame is only %d bytes, which is not a picture of "
                        "anything." % len(data))
    if width and height and min(width, height) < FRAME_MIN_EDGE:
        return "tiny", ("the frame is %d by %d pixels." % (width, height))
    if age_ms is None:
        return "stale", ("the frame arrived with no age on it, so I cannot tell "
                         "whether it is of your screen now or your screen earlier.")
    if age_ms > FRAME_MAX_AGE_MS:
        return "stale", ("it was grabbed %.1f seconds before it reached me, and I "
                         "only answer from the frame taken as you ask."
                         % (age_ms / 1000.0))
    return None


def describe_screen(question, frame, declared, width, height, age_ms):
    """Judge one frame. Returns (status, payload) and never raises."""
    problem = check_frame(declared, frame, width, height, age_ms)
    if problem:
        key, detail = problem
        return 400, {"error": SIGHT_LINES[key].format(detail=detail),
                     "detail": detail, "nodes": [], "kind": "screen"}

    cfg, cfg_error = load_config()
    if cfg_error:
        return 400, {"error": cfg_error, "nodes": [], "kind": "screen"}
    missing = credentials_error(cfg)
    if missing:
        return 400, {"error": missing, "nodes": [], "kind": "screen"}

    asked = str(question or "").strip() or "What do you make of this?"
    # The size goes in the prompt as well as the picture, because "too small to
    # judge" is a judgement the model is asked to make and it may as well know.
    user_msg = ("Your employer is pointing at their own screen and asking: %s\n\n"
                "The attached image is a single still frame of that screen, %s "
                "pixels, captured at the instant they asked."
                % (asked, ("%d by %d" % (width, height)) if width and height
                   else "of unreported size"))

    # No history in and no history out: see the module comment above, rule 3.
    messages = [{"role": "system", "content": VISION_PROMPT},
                {"role": "user", "content": user_msg}]
    answer, error = call_model(cfg, messages, image=frame)
    if error:
        return 502, {"error": error, "nodes": [], "kind": "screen"}

    return 200, {
        "answer": answer,
        # No note indexes, ever. The answer came from the screen, and lighting a
        # note or flying to one would be claiming a source it does not have.
        "nodes": [],
        "kind": "screen",
        "saw": {"bytes": len(frame), "mediaType": FRAME_MEDIA_TYPE,
                "width": width, "height": height, "ageMs": age_ms},
    }


# ------------------------------------------------------------------- looking at YOU
#
# Everything above about a screen frame holds here too - one frame, grabbed as the
# question is asked, checked against its own declared type, and no history in or out -
# with two differences that are worth saying out loud:
#
#   * this frame is of a PERSON, so it is sent only when a person asked for it in words.
#     Nothing on the posture path can reach this code: the eyes publish booleans to
#     POST /eyes, which has no field an image could arrive in.
#   * it goes to the brain the employer named - GPT 6 Astra - rather than to whichever
#     brain happens to be configured. When there is no OpenRouter key to reach it with,
#     the configured brain answers instead and the reply SAYS which one did. A silent
#     substitution here would be the one thing worse than an apology.

LOOK_MODEL = "astra"


def look_config(cfg):
    """(cfg_to_call, label_of_the_brain_that_will_answer, got_the_one_we_asked_for)."""
    wanted = SPOKEN_MODELS[LOOK_MODEL]
    key = str(cfg.get("openrouter_api_key") or "").strip()
    if not _blank(key) and key.lower() not in PLACEHOLDER_KEYS:
        routed = dict(cfg)
        routed["provider"] = "openrouter"
        routed["openrouter_model"] = wanted
        return routed, display_label(wanted), True
    return cfg, display_label(model_label(cfg)), False


def describe_me(question, frame, declared, width, height, age_ms):
    """Judge one webcam frame. Returns (status, payload) and never raises."""
    problem = check_frame(declared, frame, width, height, age_ms)
    if problem:
        key, detail = problem
        return 400, {"error": LOOK_LINES[key].format(detail=detail),
                     "detail": detail, "nodes": [], "kind": "look"}

    cfg, cfg_error = load_config()
    if cfg_error:
        return 400, {"error": cfg_error, "nodes": [], "kind": "look"}
    routed, brain, asked_for = look_config(cfg)
    missing = credentials_error(routed)
    if missing:
        return 400, {"error": missing, "nodes": [], "kind": "look"}

    asked = str(question or "").strip() or "What do you make of me?"
    user_msg = ("Your employer is asking you about themselves: %s\n\n"
                "The attached image is a single live webcam photograph of them at "
                "their desk, %s pixels, taken at the instant they asked."
                % (asked, ("%d by %d" % (width, height)) if width and height
                   else "of unreported size"))

    # No history in and no history out. A photograph of a person is the last thing that
    # should turn up in the context of a later question about their notes.
    messages = [{"role": "system", "content": WEBCAM_PROMPT},
                {"role": "user", "content": user_msg}]
    answer, error = call_model(routed, messages, image=frame)
    if error:
        return 502, {"error": error, "nodes": [], "kind": "look", "brain": brain}

    return 200, {
        "answer": answer,
        "nodes": [],
        "kind": "look",
        # Which brain actually answered, and whether it was the one asked for. Shown on
        # the card beside the answer, never spoken: the wit is the answer's job.
        "brain": brain,
        "wanted": display_label(SPOKEN_MODELS[LOOK_MODEL]),
        "asAsked": asked_for,
        "saw": {"bytes": len(frame), "mediaType": FRAME_MEDIA_TYPE,
                "width": width, "height": height, "ageMs": age_ms},
    }


# ----------------------------------------------------------- the unasked-for nudge
#
# The one route in this project that answers a question nobody asked. Everything about
# it is therefore arranged so that it is cheap to refuse and expensive only when it is
# genuinely warranted:
#
#   * the three GUARDS below are checked BEFORE the frame is even validated, because a
#     nudge that is not allowed to happen should not cost a JPEG sniff either, and
#     because the first of them is the relief valve - the moment a man has said "I need
#     to do something important", the correct amount of work for this route to do is
#     none.
#   * the cooldown is spent LAST, after the model has actually answered. A nudge that
#     failed to reach the brain must not buy three minutes of silence: the next one
#     would then be punished for the first one's bad luck.
#   * no history in, no history out, no notes, no note indexes. A screen that has sat
#     still for a minute is not a fact about the corpus.


def nudge_for_stuck(frame, declared, width, height, age_ms, still_s):
    """One unasked-for nudge about a screen that has stopped moving.

    Returns (status, payload) and never raises. Every non-200 below is free.
    """
    now = time.monotonic()
    state = WATCH.state(now)
    still = 0.0 if still_s is None else max(0.0, float(still_s))

    def refuse(status, key, **fields):
        WATCH.refuse()
        return status, {"error": STUCK_LINES[key].format(**fields),
                        "nodes": [], "kind": "nudge", "why": key,
                        # The page must not speak a suppressed nudge. A silence that
                        # announces itself is not a silence.
                        "quiet": True, "spent": False,
                        "stillS": int(still), "watch": state,
                        "tuning": WATCH.tuning()}

    # 1. THE RELIEF VALVE, first and free. It belongs to the eyes and it covers every
    #    organ, this one included; see focus.Session.relief().
    if state["hushed"]:
        return refuse(429, "hushed", leftS=state["hushLeftS"])
    # 2. The purse. One nudge per cooldown, whoever is asking and from whichever tab.
    if not state["mayNudge"]:
        return refuse(429, "cooldown", leftS=state["cooldownLeftS"])
    # 3. And the screen really must have stopped. The page measures this and the page
    #    is trusted with the measurement - but not with the threshold.
    if still < STUCK_STILL_S:
        return refuse(409, "moving", stillS=int(still))

    problem = check_frame(declared, frame, width, height, age_ms)
    if problem:
        key, detail = problem
        WATCH.refuse()
        return 400, {"error": STUCK_LINES[key].format(detail=detail),
                     "detail": detail, "nodes": [], "kind": "nudge", "why": key,
                     # Not quiet: this one IS a fault, and a watch that has gone blind
                     # while claiming to watch is worth hearing about.
                     "quiet": False, "spent": False,
                     "stillS": int(still), "watch": WATCH.state(now),
                     "tuning": WATCH.tuning()}

    cfg, cfg_error = load_config()
    if cfg_error:
        WATCH.refuse()
        return 400, {"error": cfg_error, "nodes": [], "kind": "nudge",
                     "why": "config", "quiet": False, "spent": False,
                     "stillS": int(still), "tuning": WATCH.tuning()}
    missing = credentials_error(cfg)
    if missing:
        WATCH.refuse()
        return 400, {"error": missing, "nodes": [], "kind": "nudge",
                     "why": "nokey", "quiet": False, "spent": False,
                     "stillS": int(still), "tuning": WATCH.tuning()}

    user_msg = ("Nobody has asked you anything. Your employer's screen has not changed "
                "for %d seconds, measured by comparing thumbnails on their own machine. "
                "The attached image is one still frame of that screen, %s pixels, taken "
                "just now.\n\n"
                "Read it, and say the one useful thing about what they appear to be "
                "stuck on. If it shows reading or thinking rather than a difficulty, "
                "say one dry sentence and leave them to it."
                % (int(still), ("%d by %d" % (width, height)) if width and height
                   else "of unreported size"))

    messages = [{"role": "system", "content": STUCK_PROMPT},
                {"role": "user", "content": user_msg}]
    answer, error = call_model(cfg, messages, image=frame)
    if error:
        # No cooldown spent: see the note at the top of this section.
        WATCH.refuse()
        return 502, {"error": error, "nodes": [], "kind": "nudge", "why": "brain",
                     "quiet": False, "spent": False, "stillS": int(still),
                     "watch": WATCH.state(), "tuning": WATCH.tuning()}

    WATCH.spend()
    return 200, {
        "answer": answer,
        "nodes": [],
        "kind": "nudge",
        # It was not asked for, so the page renders it as what it is rather than as a
        # reply to a question the user never typed.
        "unasked": True,
        "quiet": False,
        "spent": True,
        "stillS": int(still),
        "watch": WATCH.state(),
        "tuning": WATCH.tuning(),
        "saw": {"bytes": len(frame), "mediaType": FRAME_MEDIA_TYPE,
                "width": width, "height": height, "ageMs": age_ms},
    }


# ================== CITATION HONESTY =========================================
#
# A CHIP IS A CLAIM ABOUT THE SENTENCE ABOVE IT, not about the search that happened before
# the sentence was written. "Drawn from" over a row of planets says: this answer came out of
# these notes. "Cited" over a filename says: this answer used that page. Both are claims the
# retrieval cannot make, because retrieval runs before the answer exists - and this server
# was making them out of the retrieval anyway.
#
# THE THREE WAYS IT WAS WRONG, all of them live and all of them fixed below.
#   1 AN ERROR WITH CHIPS. call_model() fails, the 502 goes back carrying `nodes` and
#     `citations`, and the card renders "the brain could not be reached" with four planets
#     lit under "Drawn from" and a PDF chip beside them. Nothing was drawn from anything;
#     there is no answer at all.
#   2 A REFUSAL WITH CHIPS. The scorer calls a question a notes question, the passages clear
#     the dial, the brain reads them and says - correctly, as instructed - that the notes do
#     not cover it. The chips then say the refusal was drawn from the notes it is refusing
#     on, and the camera flies to one of them. The employer is shown evidence for a sentence
#     that says there is no evidence.
#   3 A CONFIGURATION ERROR WITH CHIPS, the 400 above, same shape as 1.
#
# WHAT IS DELIBERATELY NOT CHANGED. The credentials-missing 400 keeps its nodes, because
# that sentence NAMES them out loud - "the 3 notes below are the ones that matched" - and a
# chip row under a sentence that points at it is honest. The distinction throughout is
# whether the TEXT accounts for the chips, not whether a lookup ran.
#
# HOW "CONSUMED" IS DECIDED, and the honest account of its limits. There is no way to ask a
# language model what it read. What there is, is this: an answer that used the material
# shares distinctive words with it. So the test is overlap - at least one token four
# characters or longer that appears in the evidence, is not a stopword, and is NOT one of the
# words the question itself supplied. That last exclusion is the whole of the mechanism: a
# refusal echoes the question ("your notes say nothing about the Q3 contract") and nothing
# else, so a test that counted the question's own words would pass every refusal ever
# written.
#
# THE ERROR IT CAN MAKE, named rather than hidden: an answer that genuinely came from the
# notes but restates them entirely in the question's own vocabulary loses its chips. That
# costs a row of provenance the employer could have clicked. The error in the other
# direction - a refusal wearing four citations - costs him a false belief about where a
# sentence came from, and a camera flight to a note that has nothing to do with it. The two
# are not equally bad, so the threshold sits at one token: as permissive as it can be while
# still catching a sentence that shares nothing.
_CONSUMED_MIN_LEN = 4
_CONSUMED_MIN_TOKENS = 1
_CONSUMED_SUFFIXES = ("ing", "ed", "es", "s")


def _consumed_stem(token):
    """A crude stem, and it is load-bearing rather than tidy.

    FAILURE MODE IT CATCHES, measured on the first draft of this section: the question asked
    when the contract would "renew", the evidence said it "renews", and the refusal - "your
    notes say nothing about when the contract renews" - echoed the EVIDENCE's inflection. One
    token, not in the question by exact string, and the refusal kept its four chips. Two
    letters of difference defeated the whole test. Comparing stems rather than strings puts
    "renew" and "renews" in the same bucket, which is the bucket the question already owns.

    Deliberately not a real stemmer: no dictionary, no vowel rules, no pip install. One suffix
    off when at least three letters remain, which is enough for plurals and gerunds and is the
    entire class of collision that was observed.
    """
    word = str(token)
    if word.endswith("'s"):
        word = word[:-2]
    for suffix in _CONSUMED_SUFFIXES:
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            return word[:-len(suffix)]
    return word


def consumed_sources(answer, evidence, question):
    """(True/False, why) - does this answer's text account for a chip row?

    FAILURE MODE IF THIS IS WRONG IN THE PERMISSIVE DIRECTION: a refusal keeps its chips, and
    the card shows evidence for a sentence denying there is any. In the strict direction: a
    real answer loses a clickable row. Hence the one-token threshold - see above.
    """
    text = str(answer or "")
    if not text.strip():
        return False, "there is no answer text"
    if not str(evidence or "").strip():
        return False, "nothing was supplied to consume"
    asked = set(_consumed_stem(t) for t in tokenize(question))
    have = set(_consumed_stem(t) for t in tokenize(evidence))
    hits = set(s for s in (_consumed_stem(t) for t in tokenize(text))
               if len(s) >= _CONSUMED_MIN_LEN and s in have and s not in asked)
    if len(hits) >= _CONSUMED_MIN_TOKENS:
        return True, ("the answer carries %d word%s out of the evidence that the question did "
                      "not supply" % (len(hits), "" if len(hits) == 1 else "s"))
    return False, ("the answer shares no distinctive word with the evidence - it is a "
                   "refusal or an aside, not a reading")


def strip_citations(payload, why):
    """Take the chips off a payload whose text does not account for them.

    ONE FUNCTION so there is one place to read and one string to grep for in the trace. The
    keys are removed rather than emptied where the page treats absence and emptiness alike,
    and `nodes` is emptied rather than removed because the page reads data.nodes directly.
    """
    payload["nodes"] = []
    payload.pop("citations", None)
    payload.pop("scanNotes", None)
    payload["uncited"] = why
    sys.stderr.write("  chips: none - %s\n" % why)
    return payload


def answer_question(question, session, guest=False):
    """One question in, one of five worlds out, and the reply always says which.

        kind "notes"   - answered from the retrieved notes. Nodes light, camera flies.
        kind "web"     - answered from live search results, with the URLs attached.
        kind "compose" - it was a TASK: a draft, a translation, a summary, a plan. The
                         assistant's own work, so nothing is lit, nothing is cited and
                         nothing was searched.
        kind "chat"    - small talk, an acknowledgment, a private identifier held back,
                         or a polite "your notes do not cover that".
        kind "swap"    - it was an instruction about the brain, not a question at all.

    The two substantial worlds never mix. A notes answer is never shown a snippet and a
    web answer is never shown a note, which is enforced by the message lists below
    rather than by asking the model nicely.
    """
    ensure_index()
    cfg, cfg_error = load_config()

    if not _index["notes"]:
        return 503, {"error": "The brain has no notes indexed. Run "
                              "\"python build.py\" and ask again.",
                     "nodes": [], "kind": "chat"}

    with _lock:
        history = list(_history.get(session, []))
    # THE PREVIOUS QUESTION, and a TASK IS NOT ONE. `prior` is lent to the scorer and to
    # substantial_question() so that a bare follow-up still has something to be about, and
    # a task in that slot lends the wrong thing entirely: "translate good evening into
    # french" followed by "who made it?" scored the words "good evening" against a café's
    # notes about evening staffing and its autumn menu, so the notes claimed a pronoun that
    # belonged to the question before the task. Skipped here for the same reason the /chat
    # door skips the memory for it - see remember_ask's call site.
    prior = next((m["content"] for m in reversed(history)
                  if m["role"] == "user" and not task_intent(m["content"])), "")
    # THE MEMORY, read before anything is written to it: at this moment it still holds
    # the question BEFORE this one, which is exactly what a pronoun in this one needs.
    # Read here and passed down by hand rather than reached for from inside the rewriter,
    # so that what the rewrite was built from is visible at the top of this function.
    recalled, recalled_kind = recall_ask()

    picked = score_notes(question, prior)
    best_score = picked[0][1] if picked else 0.0
    # How much of the question the collection actually holds, 0..1. The raw score above
    # says how loudly a note rang; this says whether it rang for the right question.
    confidence = note_confidence(question, picked, prior)

    # ---- THE SECOND RETRIEVAL, BY MEANING, AND IT COSTS NOTHING TO SAY "OK THANKS".
    #
    # This is the one line in the upgrade that could have made the cheapest message in
    # the conversation the most expensive: embedding a query is an HTTP call to a model,
    # and "ok, got it" would have paid for one on its way to the backchannel's fixed
    # reply. So the same three vetoes that guard the web gate guard this too, ABOVE it,
    # and they are computed once here and reused all the way down - an acknowledgment, a
    # bare greeting and anything that is not a question never reach the embedder at all.
    ack = backchannel_only(question)
    worth_embedding = (substantial_question(question, prior) and not ack
                       and not address_only(question))
    sem = (semantic_recall(question, prior) if worth_embedding
           else {"available": False, "why": "nothing was asked", "opens": False,
                 "hits": [], "cited": [], "best": 0.0, "best3": 0.0, "scans": [],
                 "threshold": 0.0, "ms": 0})

    # ---- decide what kind of thing was said BEFORE deciding what to return.
    # "chat" carries no note indexes at all, which is what holds the galaxy still.
    kind = classify_question(question, best_score, prior, confidence)

    # ---- THE SEMANTIC DOOR, and what it is NOT allowed to walk past.
    #
    # The keyword half has had its say above. If it declined - no shared words, or shared
    # words that held none of the question - the meaning search gets its turn, and a
    # passage at or above the dial opens the notes door on its own. That single branch is
    # the whole of "read, understand and cite a PDF": nothing in archive/Q3_Contract.pdf
    # shares a word with "what colour is the car", and it answers it anyway.
    #
    # THREE VETOES STAND ABOVE IT, exactly as they stand above the web gate, and for the
    # same reason - they are about what KIND of thing was said, and no retrieval score is
    # evidence about that:
    #   the backchannel   "ok thanks" is a reply, not a question, and never got here;
    #   the vocative peel "good morning, Jarvis" is an address, not a query;
    #   THE THIRD DOOR    a task is not research. "Translate good evening into french"
    #                     will find some passage in a thirty-note corpus that MEANS
    #                     something adjacent to it, and answering a translation request
    #                     out of the employer's staffing notes would be worse than
    #                     useless. task_intent() keeps composition composed.
    #   A PRIVATE IDENTIFIER whose passages do not contain it: an address has no synonyms,
    #                     so a high score against prose that never mentions it is a
    #                     coincidence, and walking past the PII shield on a coincidence
    #                     swallows a refusal the employer is owed. See
    #                     semantic_holds_identifier(), which names the measurement.
    # The one thing the door may not do is close: a question the keyword half already
    # claimed stays claimed, because it has evidence this one does not - a word the
    # employer actually typed.
    sem_opened = False
    if (sem.get("opens") and kind != "notes" and worth_embedding
            and not task_intent(question)
            and semantic_holds_identifier(question, sem)):
        kind = "notes"
        sem_opened = True
        sys.stderr.write("  recall: the notes door opened on MEANING alone - %.3f "
                         "(threshold %.2f) from %s\n"
                         % (sem.get("best3") or 0.0, sem.get("threshold") or 0.0,
                            ", ".join(h.get("name", "?")
                                      for h in (sem.get("cited") or [])[:3]) or "nothing"))
    # AND THE GATE IS TOLD. note_confidence() measures word overlap and cannot see that a
    # passage means the same thing in different words, so on its own it would still call
    # this question "thin" and send it to the web with the answer already in hand. The two
    # numbers are on the same scale by construction - both are "how much of this question
    # does the collection hold", 0..1 - so the collection's best answer is the one that
    # counts, whichever half of the retrieval found it.
    if sem.get("opens"):
        confidence = max(confidence, float(sem.get("best3") or 0.0))
    # ...and, separately, whether this one deserves a look at the live web. Two
    # decisions rather than one, because they answer different questions: the first is
    # "was this a question about the notes?", the second is "is the answer somewhere
    # the notes cannot reach?". A message can fail the first and pass the second, which
    # is precisely the case this whole feature exists for.
    reason = web_intent(question, confidence, prior,
                        in_scope=(best_score >= RELEVANCE_FLOOR or bool(sem.get("opens"))))
    # NOTHING LEFT, NOTHING SPENT, said out loud in the log. A salutation must never light
    # the LIVE WEB panel, and the way to show that is a line saying the search was declined
    # - not the absence of a line, which proves nothing about anything. If a "web lookup"
    # line ever appears for a greeting, the gate is leaking and this is where to look.
    if address_only(question):
        sys.stderr.write("  no lookup: %r is greeting and address, nothing asked%s\n"
                         % (question.strip()[:60],
                            " - AND YET THE GATE OPENED (%s)" % reason if reason else ""))
    if kind != "notes":
        # The tail goes to nothing the moment this stops being a notes answer: no chips
        # lit, no camera fly, no panel opened. Whatever is said next was not said by
        # these notes.
        picked = []
    elif sem_opened:
        # THE SAME RULE, APPLIED TO THE OTHER HALF. The keyword scorer declined this
        # question outright - classify_question() looked at its best score and called this
        # anything but a notes question - so whatever it dragged up is noise that happens
        # to share a stopword, and it is not evidence for an answer the vectors found. It
        # would also be the wrong constellation: the top keyword note would light while the
        # passage actually quoted came from a PDF that is not on the map.
        picked = []

    # ---- WHAT WAS ACTUALLY QUOTED. Only a notes answer cites, and only when the meaning
    # search cleared the dial; anything else gets an empty list, which is what keeps a
    # refusal, a task and a web answer free of chips.
    cited = sem["cited"] if (kind == "notes" and sem.get("opens")) else []
    cites = ingest.citations(cited) if (ingest is not None and cited) else []

    # THE READING, TAKEN HERE BECAUSE HERE IS WHERE BOTH RETRIEVALS HAVE FINISHED AND
    # NOTHING HAS BEEN ANSWERED YET. The hunt's question is never "what did it say" on its
    # own; it is "what did it have in front of it when it said that", and the only honest
    # answer to that is the scores and the passages AS THEY WERE AT DECISION TIME. Note the
    # two lists are different things and both are recorded: `hits` is every passage the
    # meaning search ranked, with its cosine, which is what shows a grounded-looking answer
    # standing on a 0.31; `cited` is the subset that cleared the dial and will actually be
    # pasted into the prompt. An answer with citations and an empty `cited` is a fabrication
    # with chips on it, and that is one comparison, not an investigation.
    turn_note(route=("semantic" if sem_opened else ("keyword" if kind == "notes" else kind)),
              scores={"keywordBest": round(float(best_score or 0.0), 4),
                      "confidence": round(float(confidence or 0.0), 4),
                      "semanticBest": round(float(sem.get("best") or 0.0), 4),
                      "semanticBest3": round(float(sem.get("best3") or 0.0), 4),
                      "threshold": float(sem.get("threshold") or 0.0),
                      "opened": bool(sem.get("opens")), "semOpened": sem_opened,
                      "webGate": str(reason or ""),
                      "hits": [{"name": str(h.get("name") or "?"),
                                "score": round(float(h.get("score") or 0.0), 4)}
                               for h in (sem.get("hits") or [])[:8]]},
              cited=[{"what": str(h.get("name") or "?"),
                      "score": round(float(h.get("score") or 0.0), 4),
                      "text": str(h.get("text") or "")[:TURN_EXCERPT_MAX]}
                     for h in (cited or [])[:6]])

    # Notes and archive light different things, so the two are merged rather than chosen
    # between: a keyword note keeps its planet, a semantic hit in notes/ earns the planet
    # it came from, and a semantic hit in archive/ earns no node at all because there is
    # no star for a filed contract. De-duplicated in order, first mention winning.
    node_ids = [int(_index["notes"][i].get("id", i)) for i, _ in picked]
    for nid in semantic_nodes(cited):
        if nid not in node_ids:
            node_ids.append(nid)
    node_ids = node_ids[:TOP_K]

    if cfg_error:
        # NO CHIPS UNDER A CONFIGURATION ERROR. The sentence is about config.json and says
        # nothing about the collection; a row of planets under it would be provenance for a
        # sentence that has none. See CITATION HONESTY above.
        return 400, strip_citations({"error": cfg_error, "nodes": node_ids, "kind": kind},
                                    "the answer is a configuration error, not a reading")

    # Retrieval has already run, so even with no credentials at all the viewer can
    # still light the notes that matched. Only the wording is missing.
    missing = credentials_error(cfg)
    if missing:
        if node_ids:
            missing += (" The %d note%s below are the ones that matched."
                        % (len(node_ids), "" if len(node_ids) == 1 else "s"))
        return 400, {"error": missing, "nodes": node_ids, "kind": kind}

    # ---- THE BACKCHANNEL, and it is the first door for a reason: everything below this
    # line costs something. "ok", "got it", "thanks Jarvis" is a reply TO the butler, not
    # a question put to him, so it buys one acknowledgment out of the pool and nothing
    # else - no search, no rewrite, no brain call, no tool proposal, no chips.
    #
    # AND THE MEMORY IS LEFT STANDING, which is the part the employer feels. The /chat
    # door skips remember_ask for this payload, so "what is React?" / "ok got it" / "who
    # created it?" still has React to inherit at the third turn. An acknowledgment that
    # erased the subject would make the politest turn in the conversation the one that
    # broke it.
    if backchannel_only(question):
        # The same line, in the same shape, as the salutation veto above - one family of
        # message, one family of evidence, and one string for the leak detector to grep.
        sys.stderr.write("  no lookup: %r is an acknowledgment, nothing asked%s\n"
                         % (question.strip()[:60],
                            " - AND YET THE GATE OPENED (%s)" % reason if reason else ""))
        return 200, {"answer": next_backchannel(), "nodes": [], "kind": "chat",
                     "backchannel": True}

    # ---- THE HANDS, offered before a penny is spent. "remind me to call the client at
    # four" is an INSTRUCTION: it scores nothing against the notes, so the gate below
    # would happily send it to a search engine and come back with somebody's blog about
    # productivity. So a message that looks like a request to DO something gets one
    # chance to become a proposal first, and the search never runs if it does.
    #
    # Three separate judgements, kept separate on purpose:
    #   hands_wanted()        - might this be an instruction? A registry trigger, and it
    #                           chooses nothing.
    #   substantial_question()- did they actually say something? The pleasantry and
    #                           vocative vetoes sit ABOVE the hands, so "good morning,
    #                           Jarvis" can never surface a tool.
    #   the brain             - which tool, with which details, named by id in a tag.
    # If the brain answers in prose instead, nothing is pending and the turn carries on
    # to the ordinary lookup below, one model call the poorer and no harm done.
    if (hands.hands_wanted(question) and substantial_question(question, prior)
            and not address_only(question)):
        # NO HISTORY ON THIS ONE, DELIBERATELY, and the plan records it as absent rather
        # than evicted: this prompt asks one question - "is this an instruction, and which
        # one?" - and a previous turn in front of it is how a model comes to propose the
        # tool the LAST message wanted.
        manifest, protocol = hands.prompt_parts()
        messages, _plan = assemble(system=SMALLTALK_PROMPT, manifest=manifest,
                                   protocol=protocol, ask=question.strip(),
                                   label="hands-offer")
        said, hands_error = call_model(cfg, messages)
        if not hands_error:
            # THE CHAIN TAG IS READ FIRST, and the order costs nothing: a chain tag contains
            # no [[tool: ]] and a tool tag contains no array, so the two cannot both match.
            # First because the failure of the other order is silent - a model that sent a
            # plan and was read for a single tool would have proposed nothing and fallen
            # through to a web search for "add a meeting and email the team".
            plan, why, _prose = hands.chain_tag(said)
            # WHAT THE PROBE SAW, recorded before anything is done about it. This is the one
            # reading that separates "the model proposed a chain" from "the model wrote a
            # chain tag and the server threw it away": `chainTag` is true for both, `steps`
            # is None for the second. Mechanism (c), chain-protocol bleed, is exactly the
            # case where this is true on a turn whose final kind is chat or notes.
            turn_note(chainTag={"seen": bool(hands.CHAIN_TAG_AT.search(said or "")),
                                "accepted": plan is not None,
                                "steps": len(plan) if plan is not None else None,
                                "why": str(why or "")[:200]})
            if plan is not None:
                sys.stderr.write("  tool: a chain tag, %s\n" % why)
                # propose_chain() falls through to propose() for a plan of one, and
                # tool_facts is handed in rather than applied here so it reaches EVERY step.
                return hands.propose_chain(plan, door="tag", facts=tool_facts)
            if why:
                # A chain tag that arrived malformed is NOT quietly turned into a search: the
                # employer asked for two things and the model tried to say so. It is logged
                # and the turn falls through to the ordinary tag below, which will find
                # nothing, and then to prose - never to a lookup dressed up as an answer.
                sys.stderr.write("  tool: a chain tag was refused before proposing - %s\n" % why)
            wanted, params, _prose = hands.tool_tag(said)
            if wanted is not None:
                # The prose is DISCARDED and the proposal is composed from the registry
                # template: see hands.propose(). One voice, and it is not the model's.
                # tool_facts() overwrites the fields this machine is the authority on.
                return hands.propose(wanted, tool_facts(wanted, params), door="tag")
            sys.stderr.write("  tool: %r looked like an instruction and was not one\n"
                             % question.strip()[:60])

    # ---- THE THIRD DOOR: A TASK IS NOT RESEARCH. The hands had their chance just above,
    # and if a registry tool matched, the proposal path already owns this message and we
    # never got here. What is left is work the assistant can do itself - a draft, a
    # translation, a summary, a sum, a plan - and the one thing it must not do with it is
    # go and read somebody else's page about it.
    #
    # THREE THINGS IT DELIBERATELY DOES NOT DO, each of them a lie avoided rather than a
    # feature declined: no search, so no LIVE WEB panel and no cost; no notes, so no chips
    # lit behind prose the notes had no hand in; and no "ACCORDING TO" row, because the
    # only source for a letter the assistant wrote is the assistant that wrote it.
    #
    # `kind != "notes"` leaves the notes their claim: "summarise my pricing note" is a task
    # ABOUT the collection, the retrieval above already found it, and the notes door below
    # answers it properly with the note lit. Only a task the collection has nothing to do
    # with is composed from thin air, which is the only case where thin air is correct.
    if task_intent(question) and kind != "notes":
        sys.stderr.write("  no lookup: %r is a task; composed, not searched\n"
                         % question.strip()[:60])
        # NO MANIFEST AND NO PROTOCOL HERE, and the plan says absent rather than evicted:
        # the hands were already offered above and declined the message, so teaching the
        # tags again to the prompt that writes the letter would only let a letter ask for
        # a tool. The turns DO travel - "make it shorter" needs the draft it is about.
        messages, _plan = assemble(system=COMPOSE_PROMPT, history=history,
                                   older=older_block(session),
                                   ask=question.strip(), label="compose")
        answer, error = call_model(cfg, messages)
        if error:
            return 502, {"error": error, "nodes": [], "kind": "compose"}
        wanted, _cleaned = brain_tag(answer)
        if wanted:
            return swap_brain(wanted, door="tag")
        # COMPOSE_PROMPT is not taught the tool tag, and the hands were already offered
        # and declined this message one branch above. So a tag here is a stray, and it is
        # stripped rather than honoured - the same rule the web synthesis runs on.
        stray, _p, cleaned = hands.tool_tag(answer)
        if stray is not None:
            sys.stderr.write("  tool: a tool tag came back from the COMPOSE prompt; "
                             "stripped and ignored\n")
            answer = cleaned or hands.LINES["instead"]
        record_turn(session, question, answer)
        return 200, {"answer": answer, "nodes": [], "kind": "compose"}

    # ---- THE PII SHIELD, the last thing between a private identifier and a search box.
    # An email address, a telephone number or a street address makes a message private BY
    # DEFAULT: the tool doors above may act on one, because acting on it is what the
    # employer asked for and it goes to the address rather than about it, but nothing from
    # here down may put it in a query. Said out loud rather than quietly downgraded to a
    # shrug - a refusal the employer cannot see is indistinguishable from a failure.
    if (private_identifier(question) and kind != "notes"
            and substantial_question(question, prior)
            and not SELF_RE.search(_bare(question))):
        sys.stderr.write("  no lookup: a private identifier was in the message; "
                         "the web was not asked\n")
        return 200, {"answer": PRIVATE_HELD_LINE, "nodes": [], "kind": "chat",
                     "privateHeld": True}

    # ---- THE FILE THAT IS ALL PHOTOGRAPH AND NO TEXT, and the honest line it earns.
    #
    # This is the one case where a page number is the whole answer. The employer asked
    # about a document BY NAME, the index holds that document, and every page of it came
    # back empty because it is a photograph of paper - so there is nothing to retrieve, no
    # passage cleared the dial, and the truthful reply is not a shrug about the notes and
    # certainly not a search of the open web for somebody else's lease. It is one sentence
    # saying the page is there and cannot be read.
    #
    # THE LINE IS QUOTED, NEVER GENERATED. ingest.SCAN_LINE is a constant with a %d in it;
    # no model is asked to describe a page it cannot see, because a model asked to describe
    # an unreadable scan will describe one anyway. That is the whole reason this branch
    # exists above the brain rather than below it.
    #
    # name_match() is deliberately strict - every distinctive word of the filename must be
    # in the question - so "the lease photographs" finds it and "what do we do about
    # photographs" does not. It runs only when the meaning search came back empty, so a
    # document with real text on page 1 answers from page 1 as normal and this never fires.
    if ingest is not None and worth_embedding and not sem.get("opens"):
        only = None
        try:
            only = ingest.name_match(question)
        except Exception as exc:                                   # noqa: BLE001
            sys.stderr.write("  recall: image-only lookup failed (%s: %s)\n"
                             % (type(exc).__name__, exc))
        if only and only.get("pages"):
            page = int(only["pages"][0])
            line = ingest.SCAN_LINE % page
            sys.stderr.write("  no lookup: %s is image-only; said so, searched nothing\n"
                             % only.get("name", "?"))
            return 200, {"answer": line, "nodes": [], "kind": "chat", "scan": True,
                         "citations": ingest.citations(
                             [{"file": only["file"], "name": only["name"],
                               "page": page, "kind": "pdf"}]),
                         "scanNotes": [line]}

    # ---- THE TWO-STEP LOOKUP. Step one was the score above; this is step two, and it
    # happens BEFORE the brain is called, because what the brain is told depends
    # entirely on whether anything came back. Nothing here can raise: search() returns
    # an empty list for a dead network, a captcha and a redesigned results page alike.
    web, trace, query, rewrote = [], [], question.strip(), ""
    if reason:
        query = web_query(question) if reason == "force" else question.strip()
        if reason == "force" and len(query) < 2:
            # "Jarvis, look this up" and then nothing. Searching for the phrase "look
            # this up" is the one answer that would be actively unhelpful.
            return 200, {"answer": "Look what up, sir?", "nodes": [], "kind": "chat"}
        # THE REWRITER, and it goes here for two reasons: after web_query(), so that
        # "Jarvis, look this up: who made it" is measured and rewritten as the query it
        # peels down to; and after every kind decision above, so that nothing this local
        # model says can change where the answer comes from. It shapes the query and
        # touches nothing else. `question` is still the employer's own words, and
        # everything the browser is shown is built from those.
        query, rewrote = resolve_followup(query, recalled, recalled_kind, trace)
        started = time.monotonic()
        _spent("web")
        web = websearch.search(query, cfg=cfg, trace=trace)
        # stderr, like every other diagnostic here, and for a reason worth the line:
        # stdout is block-buffered when the server is run with its output redirected,
        # so a lookup logged there would only surface when the process dies - which is
        # exactly when nobody is watching. The request log goes to stderr too, so the
        # two interleave in the right order.
        # The query as SENT, and - when it is not what was said - what was said, so the
        # log can answer "why did it search for that?" without anybody guessing.
        sys.stderr.write("  web lookup (%s, notes held %.2f of it) %r%s -> %d result%s "
                         "in %.1fs\n"
                         % (reason, confidence, query[:60],
                            " [%s rewrite of %r]" % (rewrote, question.strip()[:48])
                            if rewrote else "",
                            len(web), "" if len(web) == 1 else "s",
                            time.monotonic() - started))
        for line in trace:
            sys.stderr.write("      - %s\n" % line)

    if web:
        # THE SYNTHESIS. One world at a time: the snippets go in, the notes do not, and
        # neither does the history - a previous turn about the employer's own pricing
        # note is exactly the sort of thing a model will happily fold into a paragraph
        # about today's gold price. "Never blend" has to be structural to be true, so
        # this message list is the shortest one in the file - and the plan it produces says
        # so in the one way that matters: `recent-turns` absent because nobody passed any,
        # not absent because a budget took them.
        messages, _plan = assemble(system=WEB_PROMPT, ask=query,
                                   heading="Live web results you may use, and nothing "
                                           "else:",
                                   evidence=build_web_context(web), label="web")
        answer, error = call_model(cfg, messages)
        sources = web_sources(web)
        backend = web[0].get("backend")
        if backend not in WEB_BACKENDS:
            backend = "web"
        if error:
            # The lookup worked and the brain did not. Say so, and still hand over the
            # links: they are the part that was actually fetched, and they are readable
            # without any help from a model.
            return 502, dict({"error": error, "nodes": [], "kind": "web",
                              "sources": sources, "searched": reason,
                              "backend": backend}, **sent_fields(query, rewrote))
        wanted, _cleaned = brain_tag(answer)
        if wanted:
            return swap_brain(wanted, door="tag")
        # HANDS ARE OFFERED FROM YOUR DESK, NEVER FROM A WEB PAGE. WEB_PROMPT is not
        # taught the tool tag, so this is belt and braces rather than a branch that
        # runs: if a tag ever appears in a synthesis of somebody else's page it is
        # stripped and ignored, because a search result is not allowed to ask for hands.
        stray, _p, cleaned = hands.tool_tag(answer)
        if stray is not None:
            sys.stderr.write("  tool: a tool tag came back from the WEB prompt; "
                             "stripped and ignored\n")
            answer = cleaned or WEB_SILENT_LINE
        record_turn(session, question, answer)
        # `nodes` is empty and that is the point: nothing in the galaxy lit this answer,
        # so nothing in the galaxy may be shown as having done so. The viewer pulses
        # cyan on `kind` alone and holds the camera exactly where it was.
        return 200, dict({"answer": answer, "nodes": [], "kind": "web",
                          "sources": sources, "searched": reason,
                          "backend": backend}, **sent_fields(query, rewrote))

    if reason and kind != "notes":
        # THE WEB IS SILENT, and so are the notes - the search found nothing usable and
        # the score found nothing either. A fixed line rather than a prompt: a model
        # asked to improvise an admission of failure improvises a fact instead.
        #
        # And ONE apology, not two. This is the only exit for a question the gate opened
        # and nothing answered, so the refusal and the failed lookup are reported in the
        # same sentence. The alternative shapes are both worse: a SMALLTALK refusal
        # followed by a canned line about the web says sorry twice for one failure, and a
        # SMALLTALK refusal alone hides the fact that a search was run on the employer's
        # behalf - which is a cost they paid and were not told about.
        record_turn(session, question, WEB_SILENT_LINE)
        return 200, dict({"answer": WEB_SILENT_LINE, "nodes": [], "kind": "chat",
                          "searched": reason, "webSilent": True},
                         **sent_fields(query, rewrote))
    # A failed lookup on a question the notes DO cover falls back to them, silently and
    # with no mention of the attempt. That is the fallback THE LAW asks for, and the
    # notes branch below is already exactly it.

    # THE VOCATIVE LAW, EXTENDED: a greeting never proposes a tool. The tag is only
    # OFFERED to the brain for a message that survives the peel as substantial, so the
    # prompt a salutation is answered with has no hands in it at all - and a tag cannot
    # be honoured that was never taught. Appended here rather than written into the
    # persona block so that the block stays exactly as it was, and so the sentences the
    # brain is shown are generated from the same registry the executor reads.
    offer_hands = substantial_question(question, prior) and not address_only(question)
    # SPLIT AT THE SEAM, not because this site needs two strings - it concatenates them
    # again a few lines down - but because the budget has to be able to name the block it
    # would cut. prompt_block() == manifest + "\n" + protocol, asserted in preflight.
    manifest, protocol = hands.prompt_parts() if offer_hands else ("", "")
    guest_block = ""

    # THE GUEST'S PROMPT LINE, and it is the SOURCE half of a law whose enforcement half is
    # deaddress() on the way out of /chat. Both halves exist because they fail differently: a
    # prompt line asks a model for something and cannot make it comply, while the strip pass
    # complies absolutely and cannot read a sentence. Asking first is what keeps the voice
    # natural - a model told to use no name writes "Not connected." and a model that wrote
    # "Not connected, Addi." and had it cut writes a sentence with a seam in it. It also closes
    # the one case deaddress() deliberately leaves alone: an uncommaed terminal call-name.
    #
    # COURTEOUS AND CONVERSATIONAL, which is the mandate's phrasing and not a softening. The
    # guest is not being handled; they are being spoken to by a butler who has not been
    # introduced to them.
    if guest:
        who = persona(cfg)
        guest_block = ("\n\nWHO YOU ARE SPEAKING TO JUST NOW\n"
                       "- The person who asked this is NOT %s. You do not know who they "
                       "are, and you do not guess.\n"
                       "- So use NO form of address at all in your reply: no name, no "
                       "\"sir\", no \"madam\". Not the wrong one and not a neutral one - "
                       "none. Write the sentence as though it had never occurred to you "
                       "to name anybody.\n"
                       "- Stay entirely courteous and conversational. A guest is a guest, "
                       "not an intruder, and nothing about your manner changes except the "
                       "name you do not use.\n" % who["boss_call"])

    # THE EVIDENCE, KEPT BY NAME so the citation-honesty test below can be asked about the
    # exact text the brain was shown rather than about a reconstruction of it. Empty on a
    # chat turn, which is correct: nothing was shown, so nothing can have been consumed.
    evidence = ""
    if kind == "chat":
        messages, _plan = assemble(system=SMALLTALK_PROMPT, manifest=manifest,
                                   protocol=protocol, guest=guest_block, history=history,
                                   older=older_block(session),
                                   ask=question.strip(), label="chat")
    else:
        # THE UNION, AND THE PASSAGES GO FIRST. Two retrievals ran; whatever either of
        # them found is evidence, and the model is shown both under one heading rather
        # than being told which index produced which block - it is answering a question,
        # not auditing a search. The semantic passages lead because they are the narrower
        # claim: a 500-token chunk that scored above the dial is a specific paragraph
        # about the question, while a keyword note is a whole document that mentioned it.
        #
        # THE WORDING OF THE HEADING IS THE PART THAT MATTERS. "Notes" alone would be a
        # small lie the moment a passage comes out of a PDF in archive/, and a model told
        # its only source is notes, when handed a contract, tends to hedge about it. So
        # the heading names both and the sentence that follows still says "and nothing
        # else" - the one clause in this prompt that does the real work.
        passages = build_semantic_context(cited)
        context = build_context(picked)
        both = "\n\n".join(b for b in (passages, context) if b)
        evidence = both
        messages, _plan = assemble(system=SYSTEM_PROMPT, manifest=manifest,
                                   protocol=protocol, guest=guest_block, history=history,
                                   older=older_block(session),
                                   ask=question.strip(),
                                   heading="Notes and documents you may use, and nothing "
                                           "else:",
                                   evidence=both, label=kind)

    answer, error = call_model(cfg, messages)
    if error:
        # NO CHIPS UNDER A BRAIN THAT DID NOT ANSWER. There is no answer text at all here,
        # so there is nothing for a chip to be a claim about. See CITATION HONESTY above.
        return 502, strip_citations({"error": error, "nodes": node_ids, "kind": kind,
                                     "citations": cites},
                                    "the brain returned no answer, so nothing read anything")

    # THE CONTROL TAG. An answer may ask to change the brain instead of replying, and
    # if it does, the swap is performed by the one function every other door uses and
    # the prose that came with it is dropped. Nothing is written to the history: a
    # swap is not a turn of conversation, which is also why the /chat backstop above
    # does not record one.
    wanted, _cleaned = brain_tag(answer)
    if wanted:
        return swap_brain(wanted, door="tag")

    # THE SECOND CONTROL TAG, in the same discipline and for the same reason: an answer
    # may ask for hands instead of replying. Nothing is written to the history, because a
    # proposal is not a turn of conversation - it is a question put back to the employer,
    # and what they say next is answered by the gate rather than by the brain.
    asked, params, prose = hands.tool_tag(answer)
    # AND WHAT THE ORDINARY ANSWER CARRIED. A tag on this path is a tag on a turn that was
    # NOT a hands probe - the model was answering a question about the notes and reached for
    # a hand, or wrote an array because it had just been taught one. `offered` is recorded
    # beside it because the two together name the failure: a tag the model was never offered
    # hands for is bleed, and it is silently replaced with prose four lines down.
    turn_note(toolTag={"id": asked, "offered": bool(offer_hands),
                       "chainSeen": bool(hands.CHAIN_TAG_AT.search(answer or ""))})
    if asked is not None:
        if offer_hands:
            return hands.propose(asked, params, door="tag")
        # It was never offered hands for this message and it asked anyway. The tag is
        # not honoured and it is not read out either - a stray control tag spoken aloud
        # is a bug the employer has to interpret.
        sys.stderr.write("  tool: a tag arrived for a message the hands were not "
                         "offered to; ignored\n")
        answer = prose or hands.LINES["instead"]

    # ---- THE CLEAN MOUTH. Above this line the ordinary path handled the [[tool:]] tag and
    # RECORDED that a chain tag was seen without ever taking one out, so a model that wrote
    # a plan while answering a question about the notes put "[[chain: [{"hand": ..." on the
    # screen and into the voice. hands.clean_mouth() removes the four protocol shapes and
    # leaves everything else alone - an answer about JSON keeps its braces.
    #
    # BEFORE record_turn AND NOT AFTER, because history is prompt text: a tag stored in the
    # transcript is a tag taught back to the model on the next turn as an example of what
    # this conversation sounds like, which is how one stray tag becomes a habit.
    mouth = hands.clean_mouth(answer)
    if mouth != answer:
        sys.stderr.write("  mouth: protocol removed from an ordinary answer (%d -> %d chars)\n"
                         % (len(answer or ""), len(mouth)))
    answer = mouth or hands.LINES["instead"]

    # Store the bare question, not the injected note context: history is for follow-ups
    # ("why?"), and re-sending old excerpts would blow up the prompt.
    record_turn(session, question, answer)

    # THE CITATION TRAVELS BESIDE THE ANSWER, NOT INSIDE IT. `citations` is a list the
    # panel renders as "Q3_Contract.pdf · page 4"; the prose is left exactly as the model
    # wrote it. And `scanNotes` is a footnote, never an interruption: a question answered
    # in full from page 1 of a contract does not need a sentence about page 4 wedged into
    # the reply, but the employer is still entitled to know that page 4 exists and could
    # not be read. The one case where the scan line IS the answer is handled far above,
    # where there was nothing else to say.
    payload = {"answer": answer, "nodes": node_ids, "kind": kind}
    if cites:
        payload["citations"] = cites
        notes = scan_lines(sem)
        if notes:
            payload["scanNotes"] = notes
    # AND THE LAST WORD BELONGS TO THE ANSWER. Everything above this line is the retrieval's
    # account of the turn; this is the only test that reads what was actually said. A notes
    # turn that came back as a refusal - which the prompt explicitly instructs, and which is
    # the right answer when the passages cleared the dial and still did not cover it - loses
    # its chips here, and the reason goes in the payload as `uncited` so the card, the trace
    # and routing_proof all read the same sentence. See CITATION HONESTY above.
    if node_ids or cites:
        used, why = consumed_sources(answer, evidence, question)
        if not used:
            strip_citations(payload, why)
    return 200, payload


# ------------------------------------------------------------------- http layer

class GalaxyHandler(SimpleHTTPRequestHandler):
    server_version = "KnowledgeGalaxy/1.0"

    # ---- helpers
    def _send_json(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_wav(self, data, source, word_times=None):
        """WAV bytes, with the cache verdict in a header so a harness can read it.

        no-store because the page caches nothing: say-cache/ on disk is the cache, and
        a browser holding a second copy would make a recast voice take a reload to hear.

        §39 - AND WHERE EACH WORD BEGINS, IN HEADERS, because the body is a WAV and a WAV
        has nowhere to put a list of numbers. Four of them, all numeric:

            X-Word-Timings   the start second of every word, three decimals, comma-separated
            X-Word-Count     how many, so the page can refuse a list that does not match
                             its own tokens instead of lighting the wrong words
            X-Say-Secs       the real length of this wav
            X-Speech-Span    where the speech starts and ends inside it, silence trimmed

        NUMBERS ONLY, DELIBERATELY. The page already holds the text it asked to be spoken,
        so putting the words in a header would add nothing and would put a sentence of the
        employer's into a place where proxies and devtools logs keep things. The privacy
        law in this house is that a log line counts characters and never prints them; a
        response header is a log line somebody else keeps.
        """
        self.send_response(200)
        self.send_header("Content-Type", "audio/wav")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Say-Source", source or "miss")
        if isinstance(word_times, dict) and word_times.get("starts"):
            self.send_header("X-Word-Timings", timings.header(word_times["starts"]))
            self.send_header("X-Word-Count", str(word_times.get("words") or 0))
            self.send_header("X-Say-Secs", "%.3f" % float(word_times.get("secs") or 0.0))
            self.send_header("X-Speech-Span", "%.3f,%.3f"
                             % (float(word_times.get("speechStart") or 0.0),
                                float(word_times.get("speechEnd") or 0.0)))
        self.end_headers()
        self.wfile.write(data)

    def _read_json(self, limit=64 * 1024):
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return None
        if length <= 0 or length > limit:
            return None
        try:
            return json.loads(self.rfile.read(length).decode("utf-8", "replace"))
        except Exception:                                      # noqa: BLE001
            return None

    def _read_bytes(self, limit):
        """Raw request body, or (None, reason).

        Always drains the socket before the caller replies: answering a request
        whose body is still sitting unread leaves those bytes to be parsed as the
        next request, which fails in a way that has nothing to do with the bug.
        """
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return None, "the Content-Length header was not a number."
        if length <= 0:
            return None, "the request had no body."
        if length > limit:
            self.close_connection = True     # not drained: too big to bother reading
            return None, ("the frame is %.1f MB and the limit is %.1f MB."
                          % (length / 1048576.0, limit / 1048576.0))
        data = self.rfile.read(length)
        if len(data) < length:
            return None, ("the upload stopped early (%d of %d bytes)."
                          % (len(data), length))
        return data, None

    def _read_multipart(self, limit):
        """multipart/form-data -> ({name: {filename, type, data}}, None) or (None, why).

        Written out by hand rather than handed to cgi.FieldStorage, and the reason is
        not taste: cgi was REMOVED from the standard library in Python 3.13, which is
        the interpreter this project runs on, and email.parser wants the whole body as
        one str-or-bytes message anyway. What is left is a boundary split, which for a
        single audio part is fifteen lines and has no surprises in it.

        The two details that bite: the boundary in the body is `--<boundary>`, two
        dashes more than the header's, and every part's body ends with the CRLF that
        precedes the next boundary - a decoder handed those two extra bytes rejects the
        whole chunk. Both are proved by the route below refusing junk in one sentence
        rather than raising.
        """
        ctype = self.headers.get("Content-Type") or ""
        if "multipart/form-data" not in ctype.lower():
            self._read_bytes(limit)          # drain, so the socket is not left half-read
            return None, ("send the chunk as multipart/form-data, not %r."
                          % (ctype.split(";")[0] or "nothing"))
        match = re.search(r'boundary=(?:"([^"]*)"|([^;]+))', ctype, re.I)
        boundary = ((match.group(1) or match.group(2)) if match else "").strip()
        if not boundary:
            self._read_bytes(limit)
            return None, "the multipart body named no boundary."
        body, why = self._read_bytes(limit)
        if body is None:
            return None, why
        fields = {}
        marker = b"--" + boundary.encode("latin-1", "replace")
        for chunk in body.split(marker):
            if chunk in (b"", b"--", b"--\r\n", b"\r\n"):
                continue
            head, sep, data = chunk.lstrip(b"\r\n").partition(b"\r\n\r\n")
            if not sep:
                continue
            if data.endswith(b"\r\n"):
                data = data[:-2]
            head_text = head.decode("utf-8", "replace")
            name = re.search(r'name="([^"]*)"', head_text)
            filename = re.search(r'filename="([^"]*)"', head_text)
            part_type = re.search(r'Content-Type:\s*([^\r\n]+)', head_text, re.I)
            if not name:
                continue
            fields[name.group(1)] = {
                "filename": os.path.basename(filename.group(1)) if filename else "",
                "type": part_type.group(1).strip() if part_type else "",
                "data": data,
            }
        if not fields:
            return None, "the multipart body held no parts this server could read."
        return fields, None

    def _query(self):
        return urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)

    # ---- static files, confined to viewer/
    def translate_path(self, path):
        resolved = os.path.realpath(super().translate_path(path))
        root = os.path.realpath(VIEWER_DIR)
        if resolved != root and not resolved.startswith(root + os.sep):
            return os.path.join(root, "__forbidden__")
        return resolved

    def end_headers(self):
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        SimpleHTTPRequestHandler.end_headers(self)

    # ---- the focus session ------------------------------------------------
    #
    # Three routes and one rule between them: the session state lives on the
    # server, so all any of these do is read it, nudge it, or stream it.

    def _focus_home_flag(self):
        """True, False or None, and the three are genuinely different things.

        True says "this tab has the keyboard right now". False says "it has just
        lost it, so forget I said so" - worth its own answer, because otherwise
        locking on to your work would have to wait out the claim's whole lifetime
        after you switched away. None says nothing about focus at all, which is
        what every other caller means.

        A boolean about the asking page and nothing else: never a claim about any
        other tab, and it expires inside focus.py regardless, so a tab that goes
        away cannot leave a permanent excuse behind.
        """
        said = self._query().get("home")
        if not said:
            return None
        return said[0] not in ("0", "", "false", "no")

    def _focus_stream(self):
        """GET /focus/stream - Server-Sent Events, and not a stylistic choice.

        A background tab's setInterval is throttled hard by Chrome (down to once
        a minute under intensive throttling), which would make "hear the callout
        within three seconds" impossible while you are off drifting in another
        tab - which is the only time it matters. An open stream is not throttled,
        so the server pushes the moment the tick changes something.
        """
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.send_header("Connection", "close")
        # For any proxy that might otherwise sit on the bytes waiting for a buffer
        # to fill. Local now, but a buffered SSE stream fails in a way that looks
        # exactly like a dead feature.
        self.send_header("X-Accel-Buffering", "no")
        SimpleHTTPRequestHandler.end_headers(self)
        self.close_connection = True

        seen = None
        last_write = time.monotonic()
        live = False
        try:
            while True:
                now = time.monotonic()
                version = focus.MANAGER.version()
                # A version bump means the tick changed something worth speaking or
                # showing. Between bumps the counters keep moving, so a live session
                # is resent on a slow cadence as well - otherwise "on target 4:12"
                # would sit there being wrong for as long as you behaved yourself.
                if version != seen or (live
                                       and now - last_write >= focus.SSE_REFRESH_S):
                    seen = version
                    state = focus.MANAGER.state()
                    live = state.get("state") in ("arming", "running", "paused")
                    body = json.dumps(state, ensure_ascii=False)
                    self.wfile.write(("event: focus\ndata: %s\n\n"
                                      % body).encode("utf-8"))
                    self.wfile.flush()
                    last_write = now
                elif now - last_write >= focus.SSE_KEEPALIVE_S:
                    # A comment frame, for the idle case where there is nothing to
                    # resend. It carries nothing; it exists so a dead connection is
                    # discovered here rather than by a silent client.
                    self.wfile.write(b": keepalive\n\n")
                    self.wfile.flush()
                    last_write = now
                time.sleep(focus.SSE_POLL_S)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError,
                OSError, ValueError):
            return                                    # the tab closed; that is all

    def do_GET(self):
        route = self.path.split("?")[0].rstrip("/") or "/"

        if route == "/focus":
            return self._send_json(200, {
                "ok": True, "kind": "focus", "nodes": [],
                "focus": focus.MANAGER.state(home=self._focus_home_flag())})

        if route == "/focus/stream":
            return self._focus_stream()

        if route == "/study":
            # THE SEAL'S POLL. Whitelisted by scholar.PUBLIC_KEYS on the way out, so a field
            # added to the Scholar's internals for its own bookkeeping cannot reach the browser
            # by accident - focus.public_state()'s discipline, for focus.py's reason.
            #
            # NO LOCK OF THIS SERVER'S IS TAKEN HERE. state() takes the Scholar's own lock for
            # the microseconds it needs to copy four values, and nothing else. That is what makes
            # a 2.5-second poll from the page free: see scholar.Scholar's class docstring.
            cfg = load_config()[0]
            state = scholar.MANAGER.state()
            digest = scholar.digest(boss_call=str(cfg.get("boss_call") or "sir"))
            return self._send_json(200, {
                "ok": True, "kind": "study", "nodes": [], "study": state,
                # The digest rides along rather than getting a route of its own: the page is
                # already asking every 2.5 seconds, and a second timer for a once-a-day question
                # is a second thing that can drift out of step with the first.
                "digest": {"due": digest["due"], "line": digest["line"],
                           "notes": digest["notes"], "offeredToday": digest["offeredToday"]},
                "syllabus": [t["name"] for t in scholar.read_syllabus()["topics"]]})

        if route == "/jobs":
            # §35 PART 3 - THE PROGRESS BUS, read. Deliberately the same shape as /study above
            # it, because it is the same kind of object and the page polls it on the same timer:
            # whitelisted on the way out by jobs.PUBLIC_KEYS, and taking no lock of this
            # server's. jobs.public() takes the bus's own lock for the microseconds it needs to
            # copy a few dicts - see the Async Law in that module's docstring.
            #
            # IT RETURNS THE WHOLE BOUNDED LIST AND NEVER A DELTA, which is the one schema
            # decision worth naming at the route: Chrome throttles a background tab's timers to
            # about once a minute, so a five-step job that finished inside one throttled
            # interval would deliver its middle events to a reader that had stopped asking, and
            # a step list missing its middle rows is the kind of wrong that nothing reports.
            #
            # AND A STALE JOB IS JUDGED HERE, by whoever asks. A producer that died mid-run
            # would otherwise leave the glass reading DO NOT DISTURB until the server restarted.
            want = ""
            if "?" in self.path:
                from urllib.parse import parse_qs
                want = (parse_qs(self.path.split("?", 1)[1]).get("job") or [""])[0][:40]
            return self._send_json(200, dict(jobs.public(want or None),
                                             ok=True, kind="jobs", nodes=[]))

        if route == "/poster":
            # §40 - THE CHAIN CARD'S THUMBNAIL PLATE, and the ONE route in this house that
            # serves bytes from outside viewer/. Every line of it is about that exception.
            #
            # IT TAKES A VIDEO ID AND NEVER A PATH. The law here is that the server serves the
            # viewer/ folder; a poster lives in output/videos/<slug>/poster.jpg, which is
            # outside it, so a `?file=` parameter would be a route that serves any file on this
            # disk to anything that can write `..` - and the browser asking is a browser the
            # employer's own pages share a machine with. An ID cannot do that: broadcast.
            # poster_of() looks the id up in jobs-ledger.json, which THIS SERVER wrote when the
            # bytes were accepted, and takes the path out of the row. The browser names a film
            # this house published; it never names a file. Then poster_of() checks the suffix
            # and the parent root anyway, because a ledger is a file on disk and a file on disk
            # can be edited.
            #
            # 11 CHARACTERS OF URL-SAFE BASE64 BEFORE THE LEDGER IS TOUCHED, publish_video.py's
            # ID_RE for publish_video.py's reason: the id can arrive from a language model by way
            # of the Chain Card, and a model is perfectly capable of producing a path where an id
            # belongs. A bad shape is 400 and never a lookup.
            #
            # AND THE BODY IS A JPEG, so there is nowhere for a refusal to put a sentence -
            # which is why a miss is a bare status and the glass hides the plate rather than
            # printing a reason. 404 means "no such film of ours"; it never means "no such file
            # on this disk", because this route cannot be asked about files.
            q = urllib.parse.parse_qs(self.path.split("?", 1)[1] if "?" in self.path else "")
            want = (q.get("video") or [""])[0].strip()[:16]
            if broadcast is None:
                return self.send_error(503, "no broadcaster")
            if not re.match(r"^[A-Za-z0-9_-]{11}$", want):
                return self.send_error(400, "not a video id")
            path = broadcast.poster_of(want)
            if not path:
                # SECOND AND LAST PLACE TO LOOK: the pending slot, when the id asked for is the
                # id the slot itself is about. The ledger is written at the end of an upload, and
                # there is one real case where a publish card stands in front of a boss and the
                # row is not there to be read - a card raised for a film whose ledger write did
                # not land, which is the exact moment the plate matters most and the moment the
                # id lookup cannot help. The slot is as authoritative as the row: hands.propose()
                # validated it, and _publish_card() composed it from this server's own files.
                #
                # THREE THINGS KEEP IT SAFE. The id must MATCH the slot's own `video`, so no
                # request can reach a slot it is not about; the path is never trusted for being
                # in the slot but re-checked by _poster_in_output() for being a jpg inside the
                # Director's output root; and the slot's parameters can only have come from this
                # server or from a language model's tool tag, which means the worst a model can
                # achieve by naming a file here is one of this house's own film posters.
                slot = hands.pending_public() or {}
                params = slot.get("params") or {}
                if str(params.get("video") or "") == want:
                    path = broadcast.poster_path(params.get("thumbnail"))
            if not path:
                return self.send_error(404, "no poster")
            try:
                with open(path, "rb") as fh:
                    data = fh.read(POSTER_MAX_BYTES + 1)
            except OSError:
                return self.send_error(404, "no poster")
            if not data or len(data) > POSTER_MAX_BYTES:
                # A CAP, because this reads a whole file into memory to answer a poll. The
                # Director's posters are thirty kilobytes; anything near two megabytes is not
                # one of ours whatever the ledger says.
                return self.send_error(404, "no poster")
            self.send_response(200)
            self.send_header("Content-Type", FRAME_MEDIA_TYPE)
            self.send_header("Content-Length", str(len(data)))
            # no-store like every other route here: the plate must change when the film does,
            # and a cached poster on a card the boss is about to approve is the wrong picture
            # above the right title.
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return self.wfile.write(data)

        if route == "/clock":
            # THE BOARD'S TRUTH ANCHOR, and it is not an animation frame. The page ticks its
            # own tiles between reads using the offsets in this payload, so the cadence of this
            # route has nothing to do with the cadence of the seconds on screen - which is why
            # it can be read once when the board opens and then left alone.
            #
            # ZERO LOOKUPS AND NO NETWORK, asserted by clock_proof rather than promised here.
            # ?at= is for the harness: a fixed ISO instant makes the date-line pair reproducible
            # in a way "run it and see" cannot be, since the pair's whole point is that it
            # depends on what time it is.
            if worldclock is None or not worldclock.ready():
                return self._send_json(200, {
                    "ok": False, "kind": "clock", "nodes": [], "tiles": [], "lookups": 0,
                    "source": "", "places": 0,
                    "why": ("there is no timezone database on this machine"
                            if worldclock is not None else "the clock module did not load")})
            q = urllib.parse.parse_qs(self.path.split("?", 1)[1] if "?" in self.path else "")
            at = None
            raw = (q.get("at") or [""])[0].strip()
            if raw:
                try:
                    at = datetime.datetime.fromisoformat(raw)
                except ValueError:
                    # A BAD STAMP IS REFUSED, not quietly read as now. "run it at a fixed
                    # instant" and "run it now" are different measurements, and a harness that
                    # asked for the first and silently got the second would assert a date-line
                    # pair against whatever today happens to be.
                    return self._send_json(400, {
                        "ok": False, "kind": "clock", "nodes": [], "tiles": [],
                        "why": "at= is not an ISO instant"})
            return self._send_json(200, {
                "ok": True, "kind": "clock", "nodes": [], "lookups": 0,
                "source": worldclock.source(), "places": worldclock.places_known(),
                "home": worldclock.home()[0], "tiles": worldclock.board(at=at)})

        if route == "/census":
            # READ EVERY TIME, and the listdir is the whole cost. See the section above
            # census_snapshot(): a progress figure held in this process is a second model
            # of a fact the folder already holds, and the two disagree the first time he
            # deletes a note.
            try:
                return self._send_json(200, census_snapshot())
            except Exception as exc:                           # noqa: BLE001
                return self._send_json(200, {
                    "ok": False, "kind": "census", "nodes": [], "chapters": [],
                    "answered": 0, "total": census.TOTAL, "next": None,
                    "why": "the Census could not read its folder (%s)" % exc})

        if route == "/focus/diag":
            # THE INSTRUMENT. Booleans, small integers and words out of fixed sets -
            # see focus.DIAG_KEYS, which this payload is copied through and which has
            # no key that could hold an app, a site or a window title.
            #
            # It is answered by the LONG-LIVED process on purpose, and that is the
            # whole point of the route rather than a script that imports focus.py and
            # asks: a fresh interpreter passes every check while the one actually
            # holding your session sits on a config it read before you fixed it, or on
            # a tick thread that died forty minutes ago. `pid`, `uptimeS` and
            # `tickAgeS` are the three fields that tell you which one you are talking
            # to; read them first and the other twenty are worth reading.
            return self._send_json(200, {
                "ok": True, "kind": "focus", "nodes": [], "answer": "",
                "diag": focus.MANAGER.diag()})

        if route == "/session/dump":
            # THE HUNT'S ONE WINDOW, and it is a READ of the live process for the same
            # reason /focus/diag is: a harness that reconstructed a turn by re-asking the
            # question would be measuring a second turn, and the whole question is what THIS
            # one had in front of it.
            #
            # WHY IT IS ON BY DEFAULT AND STILL HAS A SWITCH. Everything in it is already in
            # the browser that asked - its own questions, its own answers - and this server
            # binds 127.0.0.1 only, so there is no reader here who did not write the contents.
            # A default of OFF was written first and taken out again for one reason: turning
            # it on would mean editing config.json, a harness may never write config.json,
            # and an instrument the regression suite cannot arm is an instrument that stops
            # being run. So the switch is a KILL switch - `"session_dump": false` silences it
            # - and the absence of the key means on.
            #
            # NO CREDENTIAL CAN REACH IT either way: the dump's fields are the ones
            # turn_begin() writes - questions, answers, sizes, scores, kinds - and nothing
            # here reads config.json for anything but this one boolean.
            cfg = load_config()[0]
            if (cfg or {}).get("session_dump") is False:
                return self._send_json(404, {
                    "ok": False, "kind": "session", "nodes": [], "answer": "",
                    "error": "The session dump is switched off in config.json."})
            query = urllib.parse.parse_qs(self.path.split("?", 1)[1]
                                          if "?" in self.path else "")
            want = (query.get("session") or [""])[0][:120]
            try:
                limit = int((query.get("limit") or ["0"])[0] or 0)
            except ValueError:
                limit = 0
            rows = turn_dump(want or None, limit or TURN_DUMP_MAX)
            return self._send_json(200, {
                "ok": True, "kind": "session", "nodes": [], "answer": "",
                "order": list(CONTEXT_BLOCKS),
                "protected": sorted(PROTECTED_BLOCKS),
                "historyTurns": HISTORY_TURNS, "dumpMax": TURN_DUMP_MAX,
                # THE BUDGET, DECLARED ON THE WIRE and not only in a comment, so that a
                # harness asserts against the number the server is really using rather than
                # against a copy of it that can drift. Same argument as the tuning block
                # on /stuck.
                "cap": MAX_CONTEXT, "floor": CONTEXT_FLOOR, "olderKeep": OLDER_KEEP,
                "olderMax": OLDER_MAX, "pairChars": SUMMARY_PAIR_MAX,
                # The six the judge may choose from, on the wire for the same reason: a
                # harness carrying its own copy of the list would not notice a seventh.
                "groundingClasses": list(GROUNDING_CLASSES),
                "summary": older_block(want or "default"),
                "turns": rows})

        if route == "/stuck":
            # The windows and the purse, with no frame and no model call. The page asks
            # for this when the watch starts, so the numbers it applies for the next
            # hour are the ones this file states rather than a second copy that drifted.
            return self._send_json(200, {
                "ok": True, "kind": "nudge", "nodes": [], "answer": "",
                "tuning": WATCH.tuning(), "watch": WATCH.state()})

        if route == "/tools":
            # THE REGISTRY, as the page is allowed to see it: ids, names, capability
            # sentences, the parameter schema and the timeout. No script path, no
            # trigger, and - since the registry has never held one - no key. The page
            # renders the Yes/No pair from `pending`, which carries the exact validated
            # parameters, because the human about to approve them has to be able to
            # read them.
            state = hands.state()
            return self._send_json(200, {
                "ok": True, "kind": "tools", "nodes": [], "answer": "",
                "tools": hands.public_registry(),
                "pending": state["pending"], "busy": state["busy"],
                "ttlS": state["ttlS"], "error": state["registryError"]})

        if route == "/google":
            # THE STATE LINE, and every field in it has been chosen for what it does NOT
            # say. `connected`, `state`, `email`, `scopes`, `port`, `tokenDigest` - no
            # access token, no refresh token, no client secret, not even their lengths.
            # The email is here because a state line reading CONNECTED with no account is
            # an invitation to send mail from the wrong one; the digest is here so a
            # harness can prove the token CHANGED across a reconnect without ever seeing
            # a byte of it. `pending` says whether a consent window is open, which is the
            # only way the page can know to keep asking.
            #
            # `consent` and not `pending`: status() already spends that name on the state
            # WORD, and the page polls this route - a key that is a string on one read
            # and an object on the next is how a panel starts rendering "[object
            # Object]".
            return self._send_json(200, dict(google_api.status(), ok=True, kind="google",
                                             nodes=[], answer="",
                                             consent=google_api.pending()))

        if route == "/speaker":
            # THE DOORMAN'S ROSTER, and what it withholds is the point of it. Four facts per
            # enrolled voice - who, how they are addressed, whether they may use the hands,
            # when they enrolled - and no embedding, because the page has no reason to hold
            # 192 floats about a person's larynx and no business doing the comparing. See
            # speaker_state().
            return self._send_json(200, dict(speaker_state(), ok=True, kind="speaker",
                                             nodes=[], answer=""))

        if route == "/brains":
            # What the chip's menu is built from. The BUTTON must not be able to
            # offer a model the voice would be refused, so the menu is this list and
            # this list is derived from the allowlist itself - never typed into the
            # page, where it would drift the first time a model was retired.
            state = brain_state()
            # Read through the same funnel the chip reads through, so the provider flag this
            # route reports and the one /chat would honour cannot disagree - see load_config.
            cfg = load_config()[0]
            return self._send_json(200, {
                "ok": True, "kind": "model", "nodes": [], "answer": "",
                "models": [{"say": say, "id": mid, "label": display_label(mid),
                            "pretty": pretty_name(mid),
                            "current": mid == state["model"]}
                           for say, mid in sorted(SPOKEN_MODELS.items(),
                                                  key=lambda kv: kv[1])],
                "pinned": sorted(spoken_aliases()),
                # §31 PART 3 - WHAT THE PROVIDER ROW IS BUILT FROM. The menu above is a list
                # of MODELS on the house's own provider; Groq is a provider, so it can never
                # be one of those rows - the page has always had to be told about it
                # separately or not at all, and "not at all" is why "/model groq" typed at the
                # deck fell through to the notes funnel. This block is additive and carries no
                # credential: a boolean for whether a key exists, the model id the borrowed
                # engine would serve, and the written form of it. The page prints these; it
                # cannot invent them, and preflight forbids a model id typed into the page for
                # exactly that reason.
                # THE FAILURE MODE if `model` were omitted and the page named the model
                # itself: a retired Groq id would linger on the picker for as long as nobody
                # reread the HTML, which is the drift /brains exists to prevent.
                "groq": {
                    "active": provider_of(cfg) == "groq",
                    "ready": groq_ready(cfg)[0],
                    "model": model_label(dict(cfg, provider="groq")),
                    "label": display_label(model_label(dict(cfg, provider="groq"))),
                },
                "brain": state})

        if route == "/voices":
            # What the casting panel is built from, and for the same reason /brains
            # exists: the three candidates are named on this side, so the page cannot
            # audition a fourth and cannot offer a voice that is not on this disk.
            cfg = load_config()[0]
            return self._send_json(200, dict(casting_state(cfg), ok=True,
                                             kind="voices", nodes=[], answer=""))

        if self.path.split("?")[0] == "/persona":
            # Wording only. The viewer supplies the note count from the graph data
            # and the salutation from the reader's own clock; his name and the boss's come
            # from the persona block here, so the page never has to know either.
            #
            # .replace() rather than .format(), because {salutation} and {notes} are the
            # BROWSER'S placeholders and must survive this untouched - a .format() call
            # would raise KeyError on them and serve the page nothing at all.
            who = persona(load_config()[0])
            greeting = {}
            for key, line in BOOT_GREETING.items():
                greeting[key] = (line.replace("{assistant}", who["assistant"])
                                     .replace("{call}", who["boss_call"])
                                     .replace("{formal}", who["boss_formal"]))
            return self._send_json(200, {"greeting": greeting,
                                         "assistant": who["assistant"],
                                         "boss": who["boss_call"]})

        if self.path.split("?")[0] == "/health":
            ensure_index()
            cfg = load_config()[0]
            doors = [name for name, _ in websearch.backends(cfg)]
            return self._send_json(200, {
                "ok": True,
                "notes": len(_index["notes"]),
                "links": _index["meta"].get("linkCount"),
                "provider": provider_of(cfg),
                "model": model_label(cfg),
                # §41 LEFT THIS FIELD STANDING AND EMPTY ON PURPOSE. There is no region
                # because there is no cloud vendor to have one; the key stays in the
                # payload because the page and three harnesses read this shape, and a
                # removed field and a null field are different kinds of news to a reader.
                "region": None,
                # AND THE ROUTING LAW, PUBLISHED, because a fallback nobody can see is a
                # fallback nobody can audit: which road is primary, what catches it, how
                # fast the handover is allowed to be, and whether anything is queued.
                # Model ids and a depth - no key, no question, no answer.
                "routing": {
                    "primary": "groq",
                    "fallback": (ollama_chat_model(cfg)
                                 if ollama_fallback_enabled(cfg) else None),
                    "fallbackUrl": str(cfg.get("ollama_url")
                                       or DEFAULT_CONFIG["ollama_url"]),
                    "triggerBudgetMs": FALLBACK_TRIGGER_BUDGET_MS,
                    "numCtx": OLLAMA_FALLBACK_NUM_CTX,
                    "numPredict": OLLAMA_FALLBACK_PREDICT,
                    "keepAlive": OLLAMA_KEEP_ALIVE,
                    "queue": retry_queue_state(),
                },
                "keyConfigured": credentials_error(cfg) is None,
                "serving": "viewer/",
                # Which brain is answering, what it should be called on the chip, and
                # what a restart would bring back. The chip is painted from this.
                "brain": brain_state(),
                # Whether this machine can see the frontmost app at all, and whether
                # it can also see a browser tab's site. Reported here so the answer
                # is visible before a session is started rather than discovered
                # halfway through one. Booleans, as everywhere else.
                "focus": focus.capability(),
                # THE LOOKUP, described and never disclosed: which backends this config
                # has in the order they will be tried, whether a key exists, and how
                # many characters long it is. A length is not a secret; a prefix would
                # already be more than the page needs.
                "web": {
                    "backends": doors,
                    # "a key that will actually be used", not "a field with something
                    # in it": a placeholder left in config.json is not configuration,
                    # and backends() has already made that judgement.
                    "keyConfigured": "tavily" in doors,
                    "keyChars": len(str(cfg.get("search_api_key") or "").strip()),
                    # A fraction of the question, now that it has units: below this much
                    # of what was asked, the notes do not get to answer it.
                    "threshold": WEB_CONFIDENCE_THRESHOLD,
                },
                # THE VOICE PIN, and the only config VALUE this endpoint ever sends.
                # It belongs here because the browser owns the speech engine: the server
                # cannot pick a voice it has no list of. Blank means "your allowlist
                # decides", which is the normal case.
                "voice": str(cfg.get("voice_name") or "").strip(),
                # AND HOW IT WILL BE SPOKEN, for the same reason: the page owns the
                # funnel, so it has to know before the first word whether /say will
                # answer with audio or with a 503. "engine" is what config.json asked
                # for, "ready" is whether this machine can honour it, and "why" is the
                # one sentence the page logs when it names its fallback. A model name
                # and two knobs are preferences, not credentials.
                "say": voice_state(cfg),
                # AND WHETHER THERE IS ANYTHING TO TRANSCRIBE INTO. The Scribe organ
                # reads `installed` before it opens a screen-share picker, because a
                # machine with no faster-whisper must refuse in a sentence rather than
                # record three seconds of a meeting and then find there is nowhere to
                # send it. `keepsAudio: false` is the privacy law, published where a
                # harness can assert it instead of only in a comment.
                "scribe": scribe_state(),
                # AND WHETHER THE SCHOLAR IS AT WORK. Published on the same trip as the Scribe's
                # state and for the same reason: the page paints the seal, so it must know
                # before the first word whether a study is running and whether the three
                # binaries a study needs are even on this machine. `tools` is three booleans -
                # a missing yt-dlp is a fact about the desk the page is entitled to show,
                # rather than something discovered when a tick fails. Counts and booleans only;
                # scholar.PUBLIC_KEYS is the whitelist and it carries no note text and no key.
                "studying": scholar.MANAGER.state(),
                # AND WHETHER THIS HOUSE KNOWS ANY VOICES. Published on the same trip and
                # for the same reason as the Scribe's: the Command Panel has to know whether
                # there is a model to embed with and whether anybody is enrolled BEFORE it
                # offers Learn a voice, and `count` is what decides whether the row's word is
                # "learn" or "learn again". No embedding is in here - see speaker_state().
                "speaker": speaker_state(),
                # AND WHETHER A HANDSHAKE IS OPEN - §35 PART 1. On the same trip and for the
                # same reason as the two above: a harness has to be able to read the window's
                # state without a microphone, and the boss's own Command Panel should be able to
                # say what `confirm_window_s` is actually set to rather than what the file says.
                # It carries counts, the gate names and the ages, and no utterance and no topic -
                # see handshake_state(), which deliberately strips the topic from the live list.
                "handshake": handshake_state(),
                # AND WHETHER THE SKY TURNS. A preference about the camera, published
                # for the same reason the voice pin is: the browser owns the camera and
                # cannot be told by any other route. Absent or false means the galaxy
                # rests, which is the default and the answer for everybody who has not
                # gone looking for the key.
                "sky": {"spin": bool(cfg.get("galaxy_spin"))},
                # AND WHAT THE PRESENCE MAY SPEND, beside the camera's own preference and for
                # the identical reason: the browser owns the renderer. TWO BOOLEANS, and the
                # default is TRUE - which is why the expression is `is not False` rather than
                # bool(): an absent key, an old config.json or a typo must leave the cinema ON,
                # because the page has a guard that measures the frame and turns it off with a
                # reason, and that is a better outcome than a reader who never sees it and never
                # finds out why. Explicit false is the only thing that reads as no.
                "cine": {"bloom": cfg.get("bloom_on", True) is not False,
                         "smoke": cfg.get("smoke_on", True) is not False},
                # AND HOW LONG THE EAR WAITS. The page runs the conversation - the voice
                # detector, the re-arm, the closers - so it needs the one number that
                # decides when a silent room means goodbye. Clamped here rather than
                # trusted: a zero would close the session before the first word and a
                # config typo must not be able to hold a microphone open all afternoon.
                "ear": {"timeoutS": max(5, min(600, int(
                    _number(cfg.get("conversation_timeout_s"),
                            DEFAULT_CONFIG["conversation_timeout_s"]))))},
                # THE FOUR ENGINE FLAGS, IN ONE PLACE, because the seal has to name the
                # serving ear and the serving voice and it will not make four trips to
                # find out. Each of these is the ANSWER of the resolver, not the raw
                # config string, so "groqcloud" and "Groq" read the same here as they do
                # in the router - the failure mode being a seal that names one engine while
                # another is answering because the page did its own spelling.
                #
                # `groqKey` is a digest and a length. It is published at all because the
                # page's own refusal line has to be able to say "the field is empty"
                # without guessing, and a harness has to be able to prove the key never
                # left this process: a sha256 prefix is checkable against the config and
                # useless to anybody who intercepts it.
                # ONE SHAPE, and it is engines_state()'s - the same object POST /engines
                # answers with. The page reads `served` to paint the seal and `configured`
                # to know what a restart would bring back; two different shapes for one
                # question is how a rail ends up reading the file while the route reads
                # the override.
                "engines": engines_state(cfg),
                # THE SECOND INDEX, DESCRIBED THE SAME WAY THE FIRST ONE IS: how many
                # documents and chunks are in the store, which model embedded them, what
                # the dial is set to, and - if it is not working - one sentence saying
                # why. Numbers, names and booleans, no passage text and no absolute path:
                # "vector-store/" is a fact about this project, "C:\\Users\\..." is a fact
                # about this machine, and the browser is told the first and never the
                # second. `ready: false` is the honest state on a machine with no Ollama,
                # and the keyword brain answers anyway.
                "vectors": vector_state(cfg),
            })
        return SimpleHTTPRequestHandler.do_GET(self)

    def _capture(self, text):
        """The one entry point for a capture, from either route.

        Wrapped so that an unexpected exception still comes back as a spoken
        failure. Silence is the one outcome a capture may never have.
        """
        try:
            status, payload = remember(text)
        except Exception as exc:                               # noqa: BLE001
            reason = "unexpected error (%s)" % exc
            status, payload = 500, {
                "ok": False, "error": reason, "nodes": [], "kind": "capture",
                "answer": CAPTURE_LINES["failed"].format(reason=reason)}
        # THE TRACE SAYS "PROPOSED", NOT "CAPTURED", and that distinction is the feature.
        # Nothing is on disk when this returns; the log line that used to name a file now
        # names a title on a card. A trace that still read "captured" here would be the one
        # place somebody reading the log could be told the write had happened.
        if payload.get("ok"):
            note = "capture proposed, awaiting a word: %s" % payload.get("title")
        else:
            note = "CAPTURE REFUSED: %s" % (payload.get("refused")
                                            or payload.get("error"))
        sys.stderr.write("  %s\n" % note)
        return status, payload

    def _hands_gate(self, question, session="default", ear_open=False, body=None):
        """THE CONFIRMATION, above every other door in /chat.

        Returns (status, payload) when the message was ABOUT a proposal - a yes, a no, or
        a word arriving after one had already run out of time - and (None, prefix) when it
        was not, where `prefix` is one sentence to put in front of whatever the answer
        turns out to be. That is how a withdrawal is reported: the employer's new question
        is answered, with a line in front saying what was let go. One utterance, not two.

        It sits ABOVE the capture, swap and focus backstops for the same reason they sit
        above the brain: a stale tab must not be able to decide what "yes" meant. And
        every path out of here returns from /chat directly, so nothing in this function
        writes _last_ask or reaches the follow-up rewriter - a confirmation is not a
        question, and "who created it?" asked after one still inherits from the last real
        question rather than from the word "yes".
        """
        lapse_status, lapsed = hands.lapse_if_due()
        pending = hands.pending_public()
        # CLASS 1 OF THE PROTECTED CLASSES, and the address comes off first: "yes yes do it
        # galaxy" is the whole of a yes once his name is out of it. See confirmation_in().
        word = confirmation_in(question)
        yes, no = word == "yes", word == "no"

        # THE DOORMAN'S LAW, above the yes and the no rather than beside them. It is one
        # function and three doors - this one, /execute and /tools cmd=cancel - because a law
        # written at one of them is a law with two ways round it. See doorman_refusal().
        if yes or no:
            refusal, _seal = doorman_refusal(body or {}, session, word)
            if refusal is not None:
                refusal["pending"] = pending
                return 403, refusal

        if lapsed is not None and (yes or no):
            # They answered a question that had already expired. The truthful reply is
            # the lapse, not "there is nothing pending" - which would be true and useless.
            _hand_resolved(lapsed)
            return lapse_status, lapsed
        if pending and yes:
            status, payload = hands.execute(door="voice", proposal_id=pending["id"])
            # THE SPOKEN DOOR RESOLVES IT TOO. A yes said out loud has to finish the job
            # a yes clicked would have finished - see _hand_resolved().
            _hand_resolved(payload)
            # §42: and the spoken door is the one that most needs the link on the glass,
            # because it is the door where nobody was looking at a screen. `pending` here
            # is the slot read before execute() claimed it - see _hand_link().
            _hand_link(payload, pending)
            return status, payload
        if pending and no:
            status, payload = hands.cancel(door="voice", proposal_id=pending["id"])
            _hand_resolved(payload)
            return status, payload
        if pending:
            # CLASSES 2 AND 3, WHILE AN OFFER STANDS. The funnel order in the mandate is
            # confirmation, meta, identity, directives - so these come after the yes and the
            # no above and before the proposal talk below, and they are here rather than at
            # the /chat door because the door never sees a message that arrives with an
            # offer live. The OFFER IS NOT TOUCHED: "who are you" is neither an answer to it
            # nor a new request, so it is answered from state and the card keeps waiting.
            #
            # FAILURE MODE THIS CATCHES: with an offer standing, "who are you" was talk
            # about the proposal - it went to the brain, which happened to be wearing the
            # persona and happened to answer correctly. A right answer for the wrong reason
            # is one prompt edit away from a wrong one, and it costs a model call to get.
            # §29's two arguments here as well, and computed from the same slot the Doorman
            # reads twenty lines above: a sentence asking for the screen while an offer stands
            # is still a sentence asking for the screen, and a gate that applied the voice law
            # on one path and not the other is a gate with a way round it.
            _spk, _spoken, _ = _speaker_turn(body or {}, session)
            klass, said = protected_answer(
                question, load_config()[0], ear_open, offer_standing=True, spoken=_spoken,
                seal=(voiceprint.seal_for(_spk) if (voiceprint is not None and _spoken) else ""))
            if klass is not None:
                said["pending"] = pending
                sys.stderr.write("  route: %s - answered from state with an offer still "
                                 "standing, 0 lookups: %r\n" % (klass, question[:60]))
                return 200, said
        if pending and about_the_proposal(question, pending):
            # PART B. He is examining the offer, not answering it. The offer stands and the
            # remark is answered with the offer in front of the brain - see
            # talk_about_proposal(), which spends no lookup doing it.
            sys.stderr.write("  route: proposal - talk about %s, the offer stands\n"
                             % pending.get("tool"))
            return talk_about_proposal(question, session, pending)
        if pending:
            # A NEW SUBSTANTIVE QUESTION IS A WITHDRAWAL. Silence is not consent and
            # neither is a change of topic, so the proposal goes and the question is
            # answered.
            return None, hands.withdraw()
        if yes or no:
            # Nothing is pending, and this is also the second "yes" after a tool has
            # already run: it is refused rather than obeyed, because a confirmation can
            # only ever confirm the one thing it was given.
            #
            # AND IT IS NEVER SEARCHED. This is the released-confirmation case the mandate
            # names: the words are consent with nothing to consent to, and the one thing
            # they must not become is a query. Answered here, by name, at zero cost.
            sys.stderr.write("  route: confirmation - a word of consent with nothing "
                             "pending, and nothing looked up\n")
            who = persona(load_config()[0])
            return 409, {"ok": False, "kind": "tool", "nodes": [], "pending": None,
                         "answer": "Nothing is pending, %s - tell me what to do and I "
                                   "shall propose it." % who["boss_call"],
                         "refused": "nothing-pending",
                         "route": "confirmation", "lookups": 0}
        if lapsed is not None:
            return None, lapsed["answer"]
        return None, ""

    def do_POST(self):
        route = self.path.split("?")[0].rstrip("/") or "/"

        # THE VOICE, one chunk at a time. First because it is the most frequent POST in
        # a session by a wide margin and because it must never queue behind anything:
        # the page is holding a sentence open waiting for these bytes.
        #
        # A 503 here is NOT an error to be surfaced as a failure - it is the page's cue
        # to name the browser's own voices and keep reading. So the body carries the
        # same state /health carries, and the reason is one sentence fit to be logged.
        if route == "/say":
            data = self._read_json()
            if not isinstance(data, dict):
                return self._send_json(400, {
                    "ok": False, "error": "Send a JSON body like {\"text\": \"...\"}."})
            text = str(data.get("text") or "")
            # §39 - THE WORD-BY-WORD LAW, SERVER SIDE, AND THE ONE SUBTLETY IN IT.
            # The text that is SYNTHESISED has been through the Quiet Tongue in the page:
            # markdown stripped, an unspeakable id replaced with a sentence, an em-dash
            # turned into a comma. The text the READER sees is the raw one, and those two
            # do not have the same number of words. The reveal has to light the words on
            # the glass, so the timings are computed over `timing_text` - what is written -
            # and divided across the duration of the wav of `text` - what was said. The
            # page sends both; anything that sends only `text` gets timings for it, which
            # is correct for every caller whose reader and whose voice get the same string.
            # NAMED AS AN APPROXIMATION, because it is one: an answer carrying a calendar
            # id has a 24-character token on the glass where the voice said seven syllables,
            # and that one word's share of the span is therefore too generous. It costs the
            # reveal a fraction of a second on the rarest sentence in the room, and the
            # alternative - timing the spoken form and guessing the mapping back - would
            # be wrong on every word after the id instead of on the id.
            timing_text = str(data.get("timing_text") or text)
            cfg = load_config()[0]
            state = voice_state(cfg)
            # THE AUDITION PARAMETER, and it is the only reason this route takes a model
            # at all. Gated on CASTING_MODELS, so the door opens onto the three files the
            # casting panel names and nothing a page could invent - and gated on that
            # model's own readiness rather than the configured one's, because auditioning
            # Alan on a machine that has Ryan is exactly the case the panel exists to
            # show. A voice heard here is not a voice chosen: choosing is POST /voice.
            # ORPHEUS, AND IT IS ANSWERED BEFORE THE PIPER LADDER BELOW because every rung of
            # that ladder is a question about this machine - is the binary installed, is the
            # .onnx present, is the audition voice one of the three cast files - and none of
            # them is a question about a cloud voice. Running them first would refuse Orpheus
            # on a laptop with no Piper model on it, which is precisely the machine somebody
            # would flip this flag on.
            #
            # THE TEXT IS NOT NORMALIZED HERE, and that is the Quiet Tongue's law rather than
            # an omission: normalization happens in the page on the text's way to an engine,
            # once, for Piper and Orpheus alike, because both are fed from this one route. A
            # second normalizer on this side would be a second opinion about how to read an
            # em-dash, and the two would drift.
            if voice_engine_of(cfg) == "orpheus":
                if not state["ready"]:
                    return self._send_json(503, {
                        "ok": False, "engine": "orpheus", "say": state,
                        "error": "The Orpheus voice is unavailable: %s"
                                 % (state["why"] or "no Groq key")})
                # THE FALLBACK LAW FOR THE VOICE: a 429 or an unreachable host reads this one
                # line with Piper instead, exactly once, and only if Piper can actually speak
                # on this machine. A 401 or a retired slug is heard as a refusal naming the
                # field - see call_groq_speech() - because falling those back would leave a
                # broken config.json sounding perfectly fine.
                status = {}
                wav, why = call_groq_speech(text, cfg, status=status)
                if wav is None and status.get("transient") and say.ready(
                        cfg.get("voice_model") or DEFAULT_CONFIG["voice_model"])["ready"]:
                    turn_engine("tts", "piper", "fallback", why)
                    sys.stderr.write("  fallback: orpheus -> piper (%s)\n" % why[:120])
                    wav, why, source = say.synthesise(
                        text, cfg.get("voice_model") or DEFAULT_CONFIG["voice_model"])
                    if wav is not None:
                        return self._send_wav(wav, source,
                                              timings.timings_for(timing_text, wav))
                if wav is None:
                    turn_engine("tts", "orpheus", "failed", why)
                    sys.stderr.write("say: orpheus refused - %s\n" % why)
                    return self._send_json(503, {
                        "ok": False, "engine": "orpheus", "say": state,
                        "error": "Orpheus could not speak that: %s" % why})
                turn_engine("tts", "orpheus", "ok")
                # "miss" because no cache was consulted: say-cache/ is Piper's, keyed by the
                # Piper model name, and putting cloud audio in it under a Piper key is how a
                # flip back to Piper starts playing Orpheus.
                return self._send_wav(wav, "miss",
                                      timings.timings_for(timing_text, wav))
            asked = os.path.basename(str(data.get("model") or "").strip())
            if asked.endswith(".onnx"):
                asked = asked[:-5]
            if asked and asked not in CASTING_MODELS:
                return self._send_json(400, {
                    "ok": False, "engine": state["engine"], "say": state,
                    "error": "%r is not one of the three cast voices." % asked})
            model = asked or state["model"]
            audition = say.ready(model) if asked else None
            if asked and not audition["ready"]:
                return self._send_json(503, {
                    "ok": False, "engine": "piper", "say": state, "model": model,
                    "error": "That voice is not on this machine: %s" % audition["why"]})
            if not asked and not state["ready"]:
                return self._send_json(503, {
                    "ok": False, "engine": state["engine"], "say": state,
                    "error": "The local voice is unavailable: %s"
                             % (state["why"] or "piper is not ready")})
            wav, why, source = say.synthesise(text, model)
            if wav is None:
                sys.stderr.write("say: refused - %s\n" % why)
                return self._send_json(503, {
                    "ok": False, "engine": "piper", "say": state,
                    "error": "The local voice could not speak that: %s" % why})
            return self._send_wav(wav, source,
                                  timings.timings_for(timing_text, wav))

        # THE SCRIBE, and it is second for the same reason /say is first: during a
        # meeting this is the route that arrives every three seconds, and it must not
        # queue behind anything. ThreadingHTTPServer gives each chunk its own thread;
        # scribe.py holds the one model behind one lock, so chunks transcribe in the
        # order they land and a slow one delays only the next one.
        #
        # THE AUDIO NEVER TOUCHES DISK. It arrives in a bytes object, is decoded out of
        # a BytesIO, and the reference is dropped before this function returns. There is
        # no temp file, no cache and no log line with a transcript in it - the stderr
        # line below counts characters and never prints them.
        if route == "/scribe/transcribe":
            state = scribe_state()
            # THE REFUSAL, AND IT IS FIRST. A machine without faster-whisper says so
            # before a byte is read, which is what lets the organ put SCRIBE:
            # TRANSCRIBER OFFLINE on the seal and refuse to start rather than record a
            # meeting into a hole.
            if not state["installed"]:
                self._read_bytes(scribe.MAX_CHUNK_BYTES if scribe else 1024)
                return self._send_json(503, {
                    "ok": False, "kind": "scribe", "scribe": state, "text": "",
                    "error": "The transcriber is offline: %s." % (state["why"] or
                             "faster-whisper is not installed")})
            fields, why = self._read_multipart(scribe.MAX_CHUNK_BYTES)
            if fields is None:
                return self._send_json(400, {
                    "ok": False, "kind": "scribe", "scribe": state, "text": "",
                    "error": "That chunk could not be read: %s" % why})
            part = fields.get("audio") or fields.get("chunk") or fields.get("file")
            if not part or not part["data"]:
                return self._send_json(400, {
                    "ok": False, "kind": "scribe", "scribe": state, "text": "",
                    "error": "Send the audio in a part named \"audio\"."})
            seq = fields.get("seq", {}).get("data", b"")
            try:
                seq = int(seq.decode("ascii", "replace") or 0)
            except ValueError:
                seq = 0
            out, why = scribe.transcribe(part["data"])
            part["data"] = None                  # the only copy, dropped here
            fields = None
            if out is None:
                # A 200 CARRYING ok:false ON PURPOSE. A chunk that will not decode - a
                # recorder restarting, a fragment, a burst of nothing - is one skipped
                # three seconds of a meeting that is otherwise still running. A 4xx here
                # would read to the page as a broken session, and the panel would close
                # over a working microphone.
                sys.stderr.write("scribe: chunk %d skipped - %s\n" % (seq, why))
                return self._send_json(200, {
                    "ok": False, "kind": "scribe", "scribe": scribe_state(),
                    "text": "", "start": 0, "end": 0, "language": "",
                    "seq": seq, "error": why})
            sys.stderr.write("scribe: chunk %d  %.1fs audio  %d chars  %dms\n"
                             % (seq, out["durationS"], len(out["text"]), out["tookMs"]))
            return self._send_json(200, {
                "ok": True, "kind": "scribe", "scribe": scribe_state(), "seq": seq,
                # The mandate's four fields, and two more that cost nothing and save a
                # harness from timing the server itself.
                "text": out["text"], "start": out["start"], "end": out["end"],
                "language": out["language"],
                "tookMs": out["tookMs"], "durationS": out["durationS"]})

        # THE CLOUD EAR, AND ITS BOUNDARY IS DRAWN IN THE OPEN.
        #
        # This route is the whole of what `ear_stt: "groq"` means: one utterance in, one
        # transcript out. It does NOT reach into the live microphone path. The ear contract -
        # the browser holds the microphone, runs the voice detector, decides when a silence is
        # a goodbye, and hands the funnel a finished sentence - is on the DO-NOT-ALTER list,
        # and replacing the recognizer inside it would change the timing of every closer, the
        # re-arm and the barge-in at once. So the flag changes where a transcript CAN come
        # from and the default keeps the browser serving; the seal says so either way.
        # Failure mode this boundary exists to prevent: an ear that transcribes beautifully
        # and never re-arms, discovered live, mid-sentence, by the boss.
        #
        # AND IT IS NOT THE SCRIBE. The Scribe's audio stays on this machine by law; this one
        # is an explicit opt-in to a third party for the ASK bar's own audio, so the two must
        # never share a route. /scribe/transcribe above has no Groq branch and gets none.
        #
        # THE AUDIO NEVER TOUCHES DISK here either: bytes off the wire, into one multipart
        # body, reference dropped before the return.
        if route == "/ear/transcribe":
            cfg = load_config()[0]
            served = ear_stt_of(cfg)
            if served != "groq":
                # NOT AN ERROR - AN ANSWER. The flag says the browser is the ear, so the honest
                # reply is "the browser is the ear", and the page's own recognizer supplies the
                # words. A 503 here would read to a harness as a broken transcriber.
                self._read_bytes(GROQ_STT_MAX_BYTES)
                return self._send_json(409, {
                    "ok": False, "kind": "ear", "served": served, "text": "",
                    "fallback": False,
                    "error": "The ear is served by the browser. That is \"ear_stt\" in "
                             "config.json; set it to \"groq\" to transcribe here."})
            ready, why = groq_ready(cfg)
            if not ready:
                # BEFORE A BYTE IS READ, for the same reason the Scribe and the doorman refuse
                # first: taking somebody's speech and then discovering there is nowhere to send
                # it is worse than saying so up front.
                self._read_bytes(GROQ_STT_MAX_BYTES)
                turn_engine("stt", "groq", "failed", why)
                return self._send_json(503, {
                    "ok": False, "kind": "ear", "served": "groq", "text": "",
                    "fallback": False, "error": why})
            fields, bad = self._read_multipart(GROQ_STT_MAX_BYTES)
            if fields is None:
                return self._send_json(400, {
                    "ok": False, "kind": "ear", "served": "groq", "text": "",
                    "fallback": False,
                    "error": "That audio could not be read: %s" % bad})
            part = (fields.get("audio") or fields.get("file") or fields.get("chunk"))
            if not part or not part["data"]:
                return self._send_json(400, {
                    "ok": False, "kind": "ear", "served": "groq", "text": "",
                    "fallback": False,
                    "error": "Send the audio in a part named \"audio\"."})
            name = part["filename"] or "utterance.wav"
            began = time.time()
            status = {}
            text, why = call_groq_whisper(name, cfg, audio=part["data"], status=status)
            part["data"] = None                      # the only copy, dropped here
            fields = None
            if text is None and status.get("transient"):
                # THE FALLBACK LAW FOR THE EAR, and it is the one capability where the fallback
                # cannot be performed on this side: today's default recognizer lives in the
                # browser and this process has no microphone. So the fallback is DECLARED - a
                # 200 naming "browser" as the server of this one utterance - and the page hears
                # exactly one answer, from its own ear, which was listening anyway. Exactly
                # once: the page does not retry this route for the same utterance.
                turn_engine("stt", "browser", "fallback", why)
                sys.stderr.write("  fallback: groq stt -> browser (%s)\n" % why[:120])
                return self._send_json(200, {
                    "ok": False, "kind": "ear", "served": "browser", "text": "",
                    "fallback": True, "reason": why, "tookMs": int((time.time() - began) * 1000),
                    "error": ""})
            if text is None:
                turn_engine("stt", "groq", "failed", why)
                sys.stderr.write("ear: groq refused - %s\n" % why)
                return self._send_json(503, {
                    "ok": False, "kind": "ear", "served": "groq", "text": "",
                    "fallback": False, "error": why})
            turn_engine("stt", "groq", "ok")
            # CHARACTERS, NEVER THE WORDS, in the trace - the Scribe's habit, kept here.
            sys.stderr.write("ear: groq %d chars  %dms\n"
                             % (len(text), int((time.time() - began) * 1000)))
            return self._send_json(200, {
                "ok": True, "kind": "ear", "served": "groq", "text": text,
                "fallback": False, "tookMs": int((time.time() - began) * 1000)})

        # THE DOORMAN, and it is third because it arrives at the same rate as the Scribe's
        # chunks and for the same reason must not queue behind a model call.
        #
        # THE AUDIO NEVER TOUCHES DISK AND NEVER OUTLIVES THE CALL. It arrives as bytes in a
        # multipart part, is decoded out of a BytesIO by voiceprint.read_wav, is turned into
        # 192 floats, and the part's reference is dropped before this function returns. There
        # is no temp file, no cache, no enrolment folder full of wavs - and the embedding
        # itself only survives an `identify` for as long as the comparison takes. What is left
        # behind is a name, a privilege, a score and a time, in one slot, for 45 seconds.
        #
        # AND NOT ONE WORD OF WHAT WAS SAID passes through here in either direction. This
        # route has no transcript to leak because it never had one: the Scribe reads words and
        # the doorman reads a larynx, and they are two modules for exactly that reason.
        if route == "/speaker":
            state = speaker_state()
            ctype = (self.headers.get("Content-Type") or "").lower()
            # THE REFUSAL IS FIRST, before a byte is read, for the same reason the Scribe's
            # is: a machine with no model must say so in a sentence rather than take three
            # spoken sentences off somebody and then discover there is nowhere to put them.
            if not state["installed"] or not state["ready"]:
                self._read_bytes(SPEAKER_MAX_BYTES)
                return self._send_json(503, {
                    "ok": False, "kind": "speaker", "speaker": state, "nodes": [],
                    "answer": "", "error": "The doorman is not ready: %s."
                                           % (state["why"] or "the voiceprint model is absent")})
            if "multipart/form-data" in ctype:
                fields, why = self._read_multipart(SPEAKER_MAX_BYTES)
                if fields is None:
                    return self._send_json(400, {
                        "ok": False, "kind": "speaker", "speaker": state, "nodes": [],
                        "answer": "", "error": "That audio could not be read: %s" % why})
                data = {k: (v["data"] or b"").decode("utf-8", "replace")
                        for k, v in fields.items() if not v["filename"]}
            else:
                fields = {}
                data = self._read_json(64 * 1024)
                if not isinstance(data, dict):
                    return self._send_json(400, {
                        "ok": False, "kind": "speaker", "speaker": state, "nodes": [],
                        "answer": "",
                        "error": "Send a JSON body like {\"cmd\": \"forget\", "
                                 "\"name\": \"...\"}."})
            cmd = str(data.get("cmd") or "").strip().lower()
            session = str(data.get("session") or "default")[:120]

            def refuse(status, sentence):
                _SPEAKER_SEEN["refused"] += 1
                return self._send_json(status, {
                    "ok": False, "kind": "speaker", "speaker": speaker_state(),
                    "nodes": [], "answer": "", "error": sentence, "keptAudio": False})

            def clips_from(prefix):
                """Every audio part named prefix0, prefix1, ... in order, decoded.

                Numbered rather than repeated because _read_multipart returns a dict keyed by
                part name, and three parts all called "audio" would silently become one -
                which is an enrolment on a third of the speech it was given, and one that
                would then refuse itself for being too short and blame the speaker.
                """
                out, bad = [], []
                for index in range(16):
                    part = fields.get("%s%d" % (prefix, index))
                    if part is None:
                        continue
                    samples, rate, oops = voiceprint.read_wav(part["data"])
                    part["data"] = None              # the only copy, dropped here
                    if samples is None:
                        bad.append("%s%d: %s" % (prefix, index, oops))
                        continue
                    out.append((samples, rate))
                return out, bad

            if cmd in ("", "state"):
                return self._send_json(200, dict(speaker_state(), ok=True, kind="speaker",
                                                 nodes=[], answer=""))

            if cmd == "forget":
                name = str(data.get("name") or "").strip()[:120]
                if not name:
                    return refuse(400, "Name the voice to forget.")
                gone = voiceprint.forget(name)
                sys.stderr.write("speaker: forget %s -> %s\n" % (voiceprint.slug(name), gone))
                return self._send_json(200 if gone else 404, {
                    "ok": bool(gone), "kind": "speaker", "speaker": speaker_state(),
                    "nodes": [], "answer": "", "keptAudio": False,
                    "error": "" if gone else "I have no voiceprint under that name."})

            if cmd == "enrol":
                # BOSS-ONLY, AND THE KEYBOARD IS THE DOOR. The real guard is structural: no
                # sentence anywhere in the funnel reaches this command, so the only way to
                # arrive here is the Command Panel's own button, which is a keystroke. This
                # clause is the explicit half of it - a body that admits it came in through
                # the ear is refused rather than trusted - so that the day somebody wires a
                # spoken shortcut to enrolment, it fails loudly instead of working.
                block = data.get("speaker") if isinstance(data.get("speaker"), dict) else {}
                if str(data.get("via") or block.get("via") or "") == "voice":
                    return refuse(403, "Enrolling a voice is done from the Command Panel, "
                                       "not by asking out loud.")
                name = str(data.get("name") or "").strip()[:120]
                if not name:
                    return refuse(400, "Give the voice a name first.")
                address = str(data.get("addressForm") or data.get("address_form") or "").strip()[:120]
                roster = voiceprint.enrolled()
                # THE FIRST ENROLMENT IS THE BOSS, and it does not need to be asked. An empty
                # store means the person at the keyboard is setting the house up, and the
                # mandate's words are "First enrolment is the boss with hands: true".
                hands_wanted = (True if not roster else
                                str(data.get("hands") or "").strip().lower()
                                in ("1", "true", "yes", "on"))
                # RE-LEARNING KEEPS THE PRIVILEGE IT ALREADY HAD. A boss re-enrolling after a
                # cold must not come back as a hands-less row because `hands` was left out of
                # the body - that would stand the law down on the quietest possible path.
                replace = str(data.get("replace") or "").strip().lower() in ("1", "true",
                                                                            "yes", "on")
                if replace:
                    mine = voiceprint.slug(name) + ".json"
                    for row in roster:
                        if row.get("file") == mine and row.get("hands"):
                            hands_wanted = True
                clips, bad = clips_from("audio")
                if not clips:
                    return refuse(400, "I heard nothing usable%s."
                                  % ((" - " + "; ".join(bad[:3])) if bad else ""))
                started = time.time()
                seconds = sum(voiceprint.seconds_of(s, r) for s, r in clips)
                heard = len(clips)
                row, why = voiceprint.enrol(clips, name, address or name, hands_wanted,
                                            replace=replace)
                clips = None                         # the samples, dropped here
                took = int((time.time() - started) * 1000)
                _SPEAKER_SEEN["embedMs"] += took
                _SPEAKER_SEEN["audioSeconds"] = round(
                    _SPEAKER_SEEN["audioSeconds"] + seconds, 2)
                if row is None:
                    # COUNTS ONLY IN THE LOG, per the Scribe's privacy law: how many seconds
                    # and how many sentences, never whose voice and never what was said.
                    sys.stderr.write("speaker: enrolment refused after %.1fs of audio in %d "
                                     "clip(s), %dms\n" % (seconds, heard, took))
                    return refuse(400, why)
                sys.stderr.write("speaker: enrolled %s  hands=%s  %.1fs  %d sentences  %dms  "
                                 "audio dropped\n" % (row["file"], row["hands"],
                                                      row["seconds"], row["sentences"], took))
                return self._send_json(200, {
                    "ok": True, "kind": "speaker", "speaker": speaker_state(), "nodes": [],
                    "answer": "", "error": "", "enrolled": row, "tookMs": took,
                    # THE ASSERTION THE HARNESS READS. Not a promise - the promise is that
                    # there is no code path in this route or in voiceprint.py that opens a
                    # file for audio - but a field a proof can name, so that the day one
                    # appears the harness has somewhere to go red.
                    "keptAudio": False, "audioSeconds": round(seconds, 2)})

            if cmd == "identify":
                clips, bad = clips_from("audio")
                if not clips:
                    return refuse(400, "I heard nothing usable%s."
                                  % ((" - " + "; ".join(bad[:3])) if bad else ""))
                samples, rate = clips[0]
                seconds = voiceprint.seconds_of(samples, rate)
                started = time.time()
                verdict = voiceprint.identify(samples, rate)
                clips, samples = None, None          # the samples, dropped here
                took = int((time.time() - started) * 1000)
                _SPEAKER_SEEN["embedMs"] += took
                _SPEAKER_SEEN["audioSeconds"] = round(
                    _SPEAKER_SEEN["audioSeconds"] + seconds, 2)
                turn = _speaker_remember(session, verdict)
                seal = voiceprint.seal_for(verdict)
                # THE LOG LINE IS A COUNT AND A LABEL AND NOTHING ELSE. The seal is live only -
                # the mandate's word - so the name goes nowhere: what is written here is the
                # turn number, the seal word, the score and the milliseconds. A ledger that
                # knew which sentence was the boss's would be a record of who was in the room.
                sys.stderr.write("speaker: turn %d  %s  cos %.3f  %.1fs  %dms  audio dropped\n"
                                 % (turn, seal, verdict.get("score") or 0.0, seconds, took))
                return self._send_json(200, {
                    "ok": True, "kind": "speaker", "nodes": [], "answer": "", "error": "",
                    "turn": turn, "ttlS": SPEAKER_TURN_TTL_S,
                    # `seal` is computed here and not derived in the page: a stale tab must
                    # not be able to promote a guest by relabelling them. See seal_for().
                    "seal": seal, "who": verdict.get("who"),
                    "addressForm": verdict.get("address_form") or "",
                    "hands": bool(verdict.get("hands")),
                    "score": verdict.get("score"), "known": verdict.get("known"),
                    "why": verdict.get("why"), "tookMs": took,
                    "keptAudio": False, "audioSeconds": round(seconds, 2),
                    "speaker": speaker_state()})

            return refuse(400, "I know cmd state, enrol, identify and forget.")

        # THE MINUTES HAND'S FIRST HALF, and the division of labour is the whole design:
        # THE BRAIN SUMMARISES HERE, THE TOOL ONLY WRITES. tools/save_minutes.py takes
        # finished markdown and puts it in a file - it holds no key, makes no network call
        # and decides nothing. That is what lets the Hands gate work as advertised: the
        # employer reads the actual minutes on the proposal card and says yes to THOSE
        # words, not to a promise that a subprocess will write something reasonable.
        #
        # So this route drafts and hands back; it writes NOTHING. The page then proposes
        # save_minutes through the door it already has, POST /tools {cmd:"propose"}.
        if route == "/scribe/minutes":
            data = self._read_json(400 * 1024)     # a long meeting, not a runaway
            if not isinstance(data, dict):
                return self._send_json(400, {
                    "ok": False, "kind": "minutes",
                    "error": "Send a JSON body like {\"transcript\": \"...\"}."})
            transcript = str(data.get("transcript") or "").strip()
            title = minutes_title(data.get("title"))
            # THE FIRST REFUSAL, in the mandate's own words. A meeting that recorded
            # nothing must not produce a file: an empty minute is the one artefact that
            # will be believed six weeks later precisely because it is on disk.
            if len(transcript) < 12:
                return self._send_json(400, {
                    "ok": False, "kind": "minutes", "title": title, "minutes": "",
                    "exists": False, "error": "There is nothing to save, Addi."})

            # Does the name already exist? Asked HERE so the panel can put Overwrite and
            # Cancel in front of the employer before anything is proposed. It is asked
            # again, independently, inside save_minutes.py - that one is the lock, this
            # one is the courtesy.
            path = os.path.join(ROOT, "notes", minutes_title(title) + ".md")
            exists = os.path.isfile(path)

            cfg = load_config()[0]
            why = credentials_error(cfg)
            answer = ""
            if not why:
                messages = [{"role": "system", "content": MINUTES_PROMPT},
                            {"role": "user",
                             "content": "Minute this recording.\n\nTranscript:\n\n%s"
                                        % transcript[:120000]}]
                answer, why = call_model(cfg, messages)
            if why or not str(answer or "").strip():
                # THE SECOND REFUSAL: the brain failed, so the raw transcript is offered
                # instead. 200, not 502, and `minutes` is already filled with the raw
                # fallback - the page has a real choice to put in front of the employer
                # rather than an error and a lost meeting. `drafted:false` is the flag a
                # harness and a panel both read to know nobody summarised this.
                sys.stderr.write("minutes: brain unavailable - %s\n"
                                 % (why or "empty answer"))
                return self._send_json(200, {
                    "ok": True, "kind": "minutes", "drafted": False,
                    "title": title, "minutes": minutes_raw(transcript, title),
                    "exists": exists,
                    "error": why or "The brain returned nothing to minute.",
                    "offer": "I could not draft the minutes, Addi. Shall I save the raw "
                             "transcript instead?"})

            minutes = str(answer).strip()
            # A model that fenced the whole document is stripped of the fence and nothing
            # else: four headings inside a code block would render as one grey brick.
            if minutes.startswith("```"):
                minutes = re.sub(r"^```[a-zA-Z]*\s*", "", minutes)
                minutes = re.sub(r"\s*```$", "", minutes).strip()
            sys.stderr.write("minutes: drafted %d chars from %d of transcript for %r\n"
                             % (len(minutes), len(transcript), title))
            return self._send_json(200, {
                "ok": True, "kind": "minutes", "drafted": True, "title": title,
                "minutes": minutes, "exists": exists, "error": ""})

        if route == "/chat":
            data = self._read_json()
            if not isinstance(data, dict):
                return self._send_json(400, {
                    "error": "Send a JSON body like {\"question\": \"...\"}.",
                    "nodes": [], "kind": "chat"})
            question = str(data.get("question") or "").strip()[:2000]
            session = str(data.get("session") or "default")[:120]
            if not question:
                return self._send_json(400, {
                    "error": "Ask me something first.", "nodes": [], "kind": "chat"})
            # THE GATE FIRST. While something is awaiting a word, what this message MEANS
            # is decided here and nowhere else: see _hands_gate. That is protected class 1,
            # and it is above the other three because a "yes" belongs to the offer on the
            # card and to nothing else in this file.
            # THE `ear` FIELD is the page saying whether the room is actually open. It is
            # optional, and a message without it is answered as a typed one, which is what
            # it is. Read before the gate because the gate answers class 2 itself when an
            # offer is standing.
            ear = data.get("ear")
            ear_open = bool(ear.get("open") if isinstance(ear, dict) else ear)
            # THE `speaker` BLOCK is the page saying "this one came through the ear, and here
            # is the turn number you gave me for it". Read BEFORE the gate, because the gate is
            # where the doorman's law lives - see _hands_gate(). A message without it is a
            # typed message, which is what it is, and the law does not apply to it.
            #
            # THE VERDICT IS FETCHED FROM THIS PROCESS'S OWN SLOT and never taken from the
            # body: see _speaker_turn(). `guest` below is therefore a fact this server
            # established from audio, not a claim the page made.
            speaker, spoken, speaker_why = _speaker_turn(data, session)
            named = bool(isinstance(speaker, dict)
                         and speaker.get("who") not in (None, "", "GUEST"))
            # AND AN EMPTY STORE IS NOT A ROOM FULL OF STRANGERS. With nothing enrolled there
            # is nobody to be recognised, so an unidentified spoken turn is the ONLY kind there
            # is - and treating it as a guest would take the boss's name off every answer in a
            # house that never asked for a doorman. The mandate's words are that with zero
            # enrolments the law stands down silently and today's behaviour holds, so the page
            # does not send a speaker block at all in that state (see speakerBlock()) and this
            # is the half that holds even if it did. Read only on the path that would otherwise
            # de-address, so a recognised voice costs no directory listing.
            guest = bool(spoken and not named)
            if guest:
                try:
                    guest = bool(voiceprint and voiceprint.enrolled())
                except Exception:                                  # noqa: BLE001
                    guest = False
            if spoken and speaker_why:
                sys.stderr.write("  speaker: %s\n" % speaker_why)

            def voiced(payload):
                """Every answer out of /chat, with a guest's address form taken off.

                ONE FUNNEL FOR ONE LAW. The mandate's words are that EVERY guest sentence
                carries no address form at all rather than a guessed one - every one, not the
                ones somebody remembered - and there are a dozen places below that write an
                answer. So the law is applied once, here, on the way out, to whatever any of
                them produced: the lines written in this file, the lines a model wrote, the
                refusals, the prefixes. See deaddress().

                It is a no-op for the boss, for a named enrolled voice, and for every typed
                message ever sent - which is nearly all of them.
                """
                # THE HANDSHAKE IS READ FIRST, BEFORE THE DE-ADDRESS - §35 PART 1, and the order
                # is the point. `guest` was computed from this utterance's own verdict, BEFORE
                # the gate ran, and a one-word "haan" IS a guest by that measurement: that is the
                # bug this section exists to fix. So a turn whose word inherited BOSS inside the
                # gate must not then have the boss's address form stripped off the answer his own
                # order produced - "Sent, sir" would arrive as "Sent." for the one person in the
                # house entitled to the word. The stamp returns truthy only when the Doorman
                # actually honoured a window moments ago, so for every other guest this is one
                # dict lookup and the law above is untouched.
                handshake_stamp(session, payload)
                shook = bool(isinstance(payload, dict) and payload.get("handshake"))
                if guest and not shook and isinstance(payload, dict):
                    for key in ("answer", "error"):
                        if payload.get(key):
                            payload[key] = deaddress(payload[key], load_config()[0])
                    payload["speakerSeal"] = "GUEST"
                # AND THE OFFER, at the same funnel and for the same reason: an answer that
                # leaves a proposal STANDING opens the window for the one word that will answer
                # it. Read from the payload's own `pending` when it has one, so the window is
                # opened for the proposal this very answer created and not for whatever happens
                # to be in the slot a moment later.
                handshake_offer(session, data, payload)
                # AND THE INSTRUMENT CLOSES HERE, on the LAST line of the one funnel every
                # answer this door sends already goes through. Not at the bottom of the
                # route, because there are eight returns above it and an instrument that
                # records seven of them is worse than none - the missing turn looks like a
                # turn that never happened. After the de-address rather than before, because
                # the sentence the dump records must be the sentence that was sent; and
                # turn_end() clears the thread's slot, so a second call cannot double-file.
                turn_end(payload)
                return payload

            # THE INSTRUMENT OPENS, above the gate and above all four protected classes,
            # because "which turns does the hunt not see" must have the answer "none". A
            # protected answer, a refused yes and a focus timer are all turns of this
            # conversation, and a dump that held only the ones that reached the brain would
            # be evidence about the brain rather than about the machine.
            #
            # `heard` IS THE UNTRIMMED BODY and `asked` is what the door works with. They are
            # the same string on nearly every turn, and the turns where they are not are
            # mechanism (a) - so they are stored apart and compared by the judge, never
            # reconciled here.
            turn_begin(session, question, spoken=spoken,
                       heard=str(data.get("question") or ""))
            gate_status, gated = self._hands_gate(question, session, ear_open, data)
            if gate_status is not None:
                return self._send_json(gate_status, voiced(gated))
            prefix = str(gated or "")
            # PROTECTED CLASSES 2 AND 3, above every retrieval in this server: whether the
            # ear is open, who he is, who I am, what I can do. Answered from live state and
            # the persona block, costing nothing - see protected_answer().
            # AND §29's TWO ARGUMENTS. The seal is computed here from the verdict THIS process
            # reached from audio, never from anything in the body - see seal_for(). Only the
            # fullscreen branch reads them, and it reads them to decide whether to do something
            # to the room; every other class is indifferent to who is speaking.
            klass, said = protected_answer(
                question, load_config()[0], ear_open, spoken=spoken,
                seal=(voiceprint.seal_for(speaker) if (voiceprint is not None and spoken)
                      else ""))
            if klass is not None:
                # THE TRACE NAMES THE CLASS. The failure this catches is silent: a routing
                # change that quietly sends "who am i" back to the notes would still return
                # an answer, and this is the line that would stop reading "protected".
                sys.stderr.write("  route: %s - answered from state, 0 lookups: %r\n"
                                 % (klass, question.strip()[:60]))
                if prefix:
                    said["answer"] = prefix + " " + said["answer"]
                    said["handsLapsed"] = True
                return self._send_json(200, voiced(said))
            # Backstop. The viewer routes "remember that ..." to /remember itself,
            # but a stale tab must not be able to answer a capture instead of
            # performing it - the server is the real classifier either way.
            if CAPTURE_RE.match(question):
                status, payload = self._capture(question)
                return self._send_json(status, voiced(payload))
            # Same backstop, same reason: changing brains is not asking a question,
            # and a stale tab must not be able to answer one instead of doing it.
            if is_swap_request(question):
                status, payload = swap_brain(question)
                return self._send_json(status, voiced(payload))
            # And once more for the timer. "Thirty minutes on this" is an
            # instruction, not a question about the notes, and a tab that has not
            # been reloaded since the feature landed must not be able to have it
            # answered conversationally instead of started.
            if focus.is_focus_request(question):
                status, payload = focus.handle({"say": question})
                return self._send_json(status, voiced(payload))
            spent_before = lookups_so_far()
            try:
                status, payload = answer_question(question, session, guest=guest)
            except Exception as exc:                           # noqa: BLE001
                status, payload = 500, {
                    "error": "The brain hit an unexpected error: %s" % exc,
                    "nodes": [], "kind": "chat"}
            # WHAT THIS ANSWER COST, measured rather than described: embeddings and web
            # searches, counted as they happened. Class 4 and the ordinary road both come
            # through here, so every reply this door sends carries the number - and a
            # protected class that started searching again would be caught by the one it
            # does NOT carry, which is why the field is set here and not per branch.
            payload.setdefault("lookups", lookups_so_far() - spent_before)
            # THE MEMORY, written once, here, and with the FINAL kind - "web" is only
            # known after the lookup, and it is the kind a follow-up most needs to
            # inherit from. A brain swap is an instruction rather than a question, so it
            # leaves the last real question standing instead of erasing it.
            #
            # AND SO DO THE OTHER TWO KINDS OF NON-QUESTION. An acknowledgment ("ok got
            # it") and a task ("draft a note to the landlord") are no more questions than
            # a brain swap is, and the reason to skip them is the same one, felt one turn
            # later: whatever "who created it?" is about, it is not about the word "ok".
            # The last REAL question stands until another real question replaces it.
            if (payload.get("kind") not in ("swap", "compose")
                    and not payload.get("backchannel")):
                remember_ask(question, payload.get("kind", ""))
            # The withdrawal, or a lapse noticed on the way in, spoken in front of the
            # answer rather than instead of it. One sentence, one utterance.
            if prefix:
                field = "answer" if payload.get("answer") else "error"
                if payload.get(field):
                    payload[field] = prefix + " " + str(payload[field])
                    payload["handsLapsed"] = True
            return self._send_json(status, voiced(payload))

        if route == "/remember":
            data = self._read_json()
            if not isinstance(data, dict):
                return self._send_json(400, {
                    "ok": False, "error": "Send a JSON body like {\"text\": \"...\"}.",
                    "answer": CAPTURE_LINES["failed"].format(reason="I was sent "
                                                             "nothing to write down"),
                    "nodes": [], "kind": "capture"})
            text = str(data.get("text") or data.get("question") or "")[:4000]
            return self._send_json(*self._capture(text))

        if route == "/census/answer":
            data = self._read_json()
            if not isinstance(data, dict):
                return self._send_json(400, {
                    "ok": False, "kind": "census", "nodes": [],
                    "error": "Send a JSON body like {\"id\": \"...\", \"answer\": \"...\"}.",
                    "answer": CENSUS_LINES["unknown"]})
            qid = str(data.get("id") or "")[:60]
            said = str(data.get("answer") or data.get("text") or "")[:4000]
            status, payload = census_answer(qid, said)
            # THE TRACE SAYS "PROPOSED", for the same reason _capture()'s does: a log line
            # reading "filed" at this point would be the one place a reader could be told
            # the write had happened when nothing is on disk at all.
            sys.stderr.write("  census %s: %s\n" % (
                qid or "?",
                ("proposed %r, awaiting a word" % payload.get("title"))
                if payload.get("pending") else
                ("REFUSED: %s" % str(payload.get("error"))[:80])))
            return self._send_json(status, payload)

        if route == "/see":
            # The body IS the frame: one JPEG, declared as image/jpeg, with the
            # question in the query string. Read before anything else replies.
            frame, why = self._read_bytes(FRAME_MAX_BYTES)
            query = self._query()
            if frame is None:
                return self._send_json(400, {
                    "error": SIGHT_LINES["noframe"].format(detail=why),
                    "detail": why, "nodes": [], "kind": "screen"})

            def header_int(name):
                try:
                    return int(float(self.headers.get(name)))
                except (TypeError, ValueError):
                    return None

            question = (query.get("q") or [""])[0][:2000]
            try:
                status, payload = describe_screen(
                    question, frame, self.headers.get("Content-Type"),
                    header_int("X-Frame-Width"), header_int("X-Frame-Height"),
                    header_int("X-Frame-Age-Ms"))
            except Exception as exc:                           # noqa: BLE001
                status, payload = 500, {
                    "error": "I could not look at that: %s" % exc,
                    "nodes": [], "kind": "screen"}
            sys.stderr.write("  saw: %d bytes %sx%s -> %s\n" % (
                len(frame), self.headers.get("X-Frame-Width", "?"),
                self.headers.get("X-Frame-Height", "?"),
                "answer" if payload.get("answer") else payload.get("error", "")[:70]))
            return self._send_json(status, payload)

        if route == "/look":
            # The body IS the frame, exactly as /see: one JPEG of the person who asked,
            # with their question in the query string. One frame, one question, no
            # history either way.
            frame, why = self._read_bytes(FRAME_MAX_BYTES)
            query = self._query()
            if frame is None:
                return self._send_json(400, {
                    "error": LOOK_LINES["noframe"].format(detail=why),
                    "detail": why, "nodes": [], "kind": "look"})

            def look_int(name):
                try:
                    return int(float(self.headers.get(name)))
                except (TypeError, ValueError):
                    return None

            question = (query.get("q") or [""])[0][:2000]
            try:
                status, payload = describe_me(
                    question, frame, self.headers.get("Content-Type"),
                    look_int("X-Frame-Width"), look_int("X-Frame-Height"),
                    look_int("X-Frame-Age-Ms"))
            except Exception as exc:                           # noqa: BLE001
                status, payload = 500, {
                    "error": "I could not look at that: %s" % exc,
                    "nodes": [], "kind": "look"}
            # The size and the brain, never the question and never the bytes: this line
            # goes to a terminal that may well be scrolled back through later.
            sys.stderr.write("  looked: %d bytes %sx%s via %s -> %s\n" % (
                len(frame), self.headers.get("X-Frame-Width", "?"),
                self.headers.get("X-Frame-Height", "?"),
                payload.get("brain", "?"),
                "answer" if payload.get("answer") else payload.get("error", "")[:70]))
            return self._send_json(status, payload)

        if route == "/stuck":
            # THE UNASKED-FOR NUDGE. The body is one frame of a screen that has stopped
            # moving, and the query says for how long. There is no question in it,
            # because nobody asked one.
            #
            # The guards run before the bytes are read as an image, but the bytes are
            # still READ off the socket first: a request whose body is left unread
            # cannot be refused cleanly, and a 429 that hangs up mid-upload would look
            # like a dead server rather than a working cooldown.
            frame, why = self._read_bytes(FRAME_MAX_BYTES)
            query = self._query()

            def still_of():
                try:
                    return float((query.get("stillS") or ["0"])[0])
                except (TypeError, ValueError):
                    return 0.0

            if frame is None:
                WATCH.refuse()
                return self._send_json(400, {
                    "error": STUCK_LINES["noframe"].format(detail=why),
                    "detail": why, "nodes": [], "kind": "nudge", "why": "noframe",
                    "quiet": False, "spent": False, "stillS": int(still_of()),
                    "tuning": WATCH.tuning(), "watch": WATCH.state()})

            def stuck_int(name):
                try:
                    return int(float(self.headers.get(name)))
                except (TypeError, ValueError):
                    return None

            try:
                status, payload = nudge_for_stuck(
                    frame, self.headers.get("Content-Type"),
                    stuck_int("X-Frame-Width"), stuck_int("X-Frame-Height"),
                    stuck_int("X-Frame-Age-Ms"), still_of())
            except Exception as exc:                            # noqa: BLE001
                status, payload = 500, {
                    "error": "I could not make anything of that: %s" % exc,
                    "nodes": [], "kind": "nudge", "why": "error",
                    "quiet": False, "spent": False}
            # The size, the stillness and whether it cost anything. Never the bytes and
            # never a word about what was on the screen.
            sys.stderr.write("  nudge: %d bytes still %ss -> %s\n" % (
                len(frame), payload.get("stillS", "?"),
                "spoke" if payload.get("spent")
                else ("free · " + str(payload.get("why", "?")))))
            return self._send_json(status, payload)

        if route == "/eyes":
            # THE POSTURE CHANNEL. JSON only, and the shape of it is the promise: three
            # booleans about a body and a word about the camera. There is no branch
            # below that reads bytes, so a frame cannot arrive here even by accident.
            data = self._read_json(16 * 1024)
            if not isinstance(data, dict):
                return self._send_json(400, {
                    "ok": False, "kind": "eyes", "nodes": [], "answer": "",
                    "error": "Send a JSON body like {\"present\": true, "
                             "\"headDown\": false, \"slouched\": false}.",
                    "focus": focus.MANAGER.state()})
            try:
                status, payload = focus.handle_eyes(data)
            except Exception as exc:                            # noqa: BLE001
                status, payload = 500, {
                    "ok": False, "kind": "eyes", "nodes": [], "answer": "",
                    "error": "The eyes hit an unexpected error: %s" % exc,
                    "focus": focus.MANAGER.state()}
            # Only the command and whether anything was said. A line per posture report
            # would be a log of your body at two-second resolution, which is exactly
            # what this feature exists not to keep.
            if payload.get("answer") or payload.get("viaSession"):
                sys.stderr.write("  eyes: %s -> spoke\n" % payload.get("cmd", "?"))
            return self._send_json(status, payload)

        if route == "/voice":
            # THE CASTING DECISION, and the only route in this project that writes
            # config.json. {"model": "en_GB-alan-medium"} - one key, checked against the
            # three and against the disk before a byte is written. Compare /model, which
            # swaps the brain in memory only and says so: a brain swap is a mood, a voice
            # is a decision, and the difference is whether it survives a restart.
            data = self._read_json(4 * 1024)
            if not isinstance(data, dict):
                return self._send_json(400, {
                    "ok": False, "kind": "voices", "nodes": [], "answer": "",
                    "error": "Send a JSON body like "
                             "{\"model\": \"en_US-ryan-high\"}."})
            payload, error = write_voice_model(data.get("model"))
            cfg = load_config()[0]
            if error:
                return self._send_json(400, dict(casting_state(cfg), ok=False,
                                                 kind="voices", nodes=[], answer="",
                                                 error=error))
            # The new state, read back off the disk it was just written to, so the panel
            # paints what config.json says rather than what it asked for.
            return self._send_json(200, dict(casting_state(cfg), ok=True,
                                             kind="voices", nodes=[], answer="",
                                             wrote=payload))

        if route == "/google":
            # TWO COMMANDS AND NO THIRD. {"cmd": "connect"} opens Google's consent page
            # in the employer's own browser and starts the loopback catcher; {"cmd":
            # "disconnect"} deletes the token and says so. There is deliberately no
            # command that takes a code, a token or a scope from the page: everything
            # secret arrives at the loopback port from Google directly, in a process the
            # browser cannot address, and a route that accepted a token would be a route
            # that could be handed a forged one.
            #
            # connect() returns the instant the browser is open, because consent takes as
            # long as a human takes and a blocked request handler would wedge the panel
            # for five minutes. The page then polls GET /google until the word changes.
            data = self._read_json(2 * 1024)
            if not isinstance(data, dict):
                return self._send_json(400, {
                    "ok": False, "kind": "google", "nodes": [], "answer": "",
                    "error": "Send a JSON body like {\"cmd\": \"connect\"}."})
            cmd = str(data.get("cmd") or "").strip().lower()[:16]
            if cmd == "connect":
                started = google_api.connect(background=True)
                opened = bool(started.get("opened"))
                if started.get("state") in ("no-client", "error"):
                    return self._send_json(400, dict(google_api.status(), ok=False,
                                                     kind="google", nodes=[],
                                                     answer="", error=started.get("why"),
                                                     consent=google_api.pending()))
                return self._send_json(200, dict(
                    google_api.status(), ok=True, kind="google", nodes=[],
                    answer=("I have opened Google's consent page, sir. Choose the account "
                            "you want me to work from, and I shall wait here."
                            if opened else
                            "I could not open a browser, sir - the consent link is in the "
                            "server's own log."),
                    opened=opened, consent=google_api.pending()))
            if cmd == "disconnect":
                gone = google_api.disconnect()
                return self._send_json(200, dict(
                    google_api.status(), ok=True, kind="google", nodes=[],
                    answer=("The token is deleted, sir, and Google has been told to forget "
                            "it as well." if gone.get("revoked") else
                            "The token is deleted, sir. Google could not be reached to "
                            "revoke it, so do that from your account page if it matters."
                            if gone.get("had") else
                            "There was nothing to disconnect, sir."),
                    forgot=bool(gone.get("had")), revoked=bool(gone.get("revoked")),
                    consent=google_api.pending()))
            return self._send_json(400, {
                "ok": False, "kind": "google", "nodes": [], "answer": "",
                "error": "The only commands are connect and disconnect."})

        # THE OTHER THREE ENGINES, AND IT IS BESIDE /model ON PURPOSE. Same law, same lock,
        # same "nothing is written to disk": /model flips the brain by its spoken name and this
        # flips the ear, the eyes and the voice by their engine's name. Kept separate from
        # /model because the brain swap is something the boss SAYS - it goes through the
        # resolver, the aliases and the three refusals - and these three are a switch, with no
        # spoken form and no opinion about vintages.
        if route == "/engines":
            data = self._read_json()
            if not isinstance(data, dict):
                return self._send_json(400, {
                    "ok": False, "kind": "engines",
                    "error": "Send a JSON body like {\"voice\": \"orpheus\"} or "
                             "{\"reset\": true}.", "engines": engines_state()})
            try:
                status, payload = set_engines(data)
            except Exception as exc:                           # noqa: BLE001
                sys.stderr.write("engines: %s\n" % exc)
                return self._send_json(500, {
                    "ok": False, "kind": "engines",
                    "error": "That flip could not be made: %s" % exc})
            served = payload.get("engines", {}).get("served", {})
            sys.stderr.write("engines: %s -> chat=%s ear=%s vision=%s voice=%s\n"
                             % ("reset" if payload.get("reset") else "set",
                                served.get("chat"), served.get("ear"),
                                served.get("vision"), served.get("voice")))
            return self._send_json(status, payload)

        if route == "/model":
            # {"say": "switch to Astra"} - the spoken phrase IS the interface, so the
            # voice path and a curl both go through the same resolver and the same
            # refusals. {"model": "..."} is accepted for callers that already know
            # the exact id; it is checked against KNOWN_MODEL_IDS just the same.
            data = self._read_json()
            if not isinstance(data, dict):
                return self._send_json(400, {
                    "ok": False, "kind": "model", "nodes": [],
                    "error": "Send a JSON body like {\"say\": \"switch to Astra\"}.",
                    "answer": BRAIN_LINES["empty"],
                    "available": sorted(SPOKEN_MODELS)})
            said = str(data.get("say") or data.get("model")
                       or data.get("question") or data.get("text") or "")[:400]
            # Which door this came through, for the log and for the reply. It is a
            # label and nothing more: no door gets a shortcut, a different allowlist
            # or a sentence of its own, which is the whole point of swap_to().
            door = str(data.get("door") or "voice")[:16].lower()
            if door not in ("voice", "button", "tag", "curl"):
                door = "voice"
            try:
                status, payload = swap_brain(said, door=door)
            except Exception as exc:                           # noqa: BLE001
                status, payload = 500, {
                    "ok": False, "kind": "model", "nodes": [],
                    "error": "I could not change brains: %s" % exc,
                    "answer": "Something went wrong changing brains, sir, so I have "
                              "stayed as I am: %s" % exc}
            sys.stderr.write("  brain (%s): %s -> %s%s\n" % (
                door, said or "(nothing)",
                payload.get("model") if payload.get("ok")
                else "REFUSED (%s)" % payload.get("refused", "bad request"),
                "  [%s line]" % payload.get("intro") if payload.get("intro") else ""))
            return self._send_json(status, payload)

        if route == "/focus":
            # {"say": "thirty minutes on this"} for the voice path, or an explicit
            # {"cmd": "start", "minutes": 30} for the FOCUS button. Both land in the
            # same place, so the button cannot do anything the voice cannot.
            data = self._read_json()
            if not isinstance(data, dict):
                return self._send_json(400, {
                    "ok": False, "kind": "focus", "nodes": [],
                    "error": "Send a JSON body like {\"say\": \"thirty minutes "
                             "on this\"}.",
                    "answer": focus.LINES["unknown"],
                    "focus": focus.MANAGER.state()})
            try:
                status, payload = focus.handle(data)
            except Exception as exc:                            # noqa: BLE001
                status, payload = 500, {
                    "ok": False, "kind": "focus", "nodes": [],
                    "error": "The timer hit an unexpected error: %s" % exc,
                    "answer": "Something went wrong with the timer, sir: %s" % exc,
                    "focus": focus.MANAGER.state()}
            sys.stderr.write("  focus: %s -> %s\n" % (
                payload.get("cmd") or data.get("say") or "(nothing)",
                payload.get("focus", {}).get("state", "?")))
            return self._send_json(status, payload)

        if route == "/study":
            # {"cmd": "tick"|"digest"|"keep"|"prune"|"promote", ...}
            #
            # THE GATE HOLDS AT THIS DOOR TOO, and that is why the Doorman is read here and not
            # only in the funnel. protected_answer() guards the SPOKEN sentence; this route is
            # what the page's own digest card posts, and a law written at one of the two is a
            # law with one way round it - which is doorman_refusal()'s own lesson, learned at
            # three doors before this one was the fourth.
            data = self._read_json()
            if not isinstance(data, dict):
                return self._send_json(400, {
                    "ok": False, "kind": "study", "nodes": [],
                    "error": "Send a JSON body like {\"cmd\": \"tick\"}.",
                    "study": scholar.MANAGER.state()})
            cmd = str(data.get("cmd") or "").strip().lower()
            session = str(data.get("session") or "default")[:120]
            cfg = load_config()[0]
            boss_call = str(cfg.get("boss_call") or "sir")
            verdict, spoken, _why = _speaker_turn(data, session)
            seal = (voiceprint.seal_for(verdict)
                    if (voiceprint is not None and spoken) else "")
            allowed, refusal = study_allowed(spoken, seal)
            if not allowed:
                sys.stderr.write("  study: %s from a voice sealed %r, refused at the "
                                 "doorman\n" % (cmd or "(nothing)", seal or "?"))
                return self._send_json(200, {
                    "ok": False, "kind": "study", "nodes": [], "answer": refusal,
                    "refused": "not-the-boss", "seal": seal,
                    "study": scholar.MANAGER.state()})

            if cmd == "tick":
                # QUEUED, NEVER RUN HERE. This handler is on a request thread that the page is
                # holding open; a study inside it would block that socket for the whole tick.
                started, line = scholar.MANAGER.request(
                    topic=(str(data.get("topic") or "").strip() or None),
                    why="endpoint", url=(str(data.get("url") or "").strip() or None),
                    audio=(str(data.get("audio") or "").strip() or None),
                    boss_call=boss_call)
                return self._send_json(200, {
                    "ok": bool(started), "kind": "study", "nodes": [], "answer": line,
                    "queued": bool(started), "study": scholar.MANAGER.state()})

            if cmd == "digest":
                got = scholar.digest(boss_call=boss_call)
                return self._send_json(200, {
                    "ok": True, "kind": "study", "nodes": [], "answer": got["line"],
                    "digest": got, "study": scholar.MANAGER.state()})

            if cmd == "keep":
                # KEEP IS A NO-OP ON PURPOSE, and saying so is the point. The mandate's three
                # words are keep, prune and promote; keep means the note stays exactly where the
                # Scholar put it, so the only thing this branch does is close the digest so it is
                # not offered again today. A "keep" that copied or re-indexed anything would be a
                # promote wearing the safer word.
                scholar.mark_digest()
                return self._send_json(200, {
                    "ok": True, "kind": "study", "nodes": [],
                    "answer": "Left where they are, %s." % boss_call,
                    "study": scholar.MANAGER.state()})

            if cmd == "prune":
                ok, said = scholar.prune(str(data.get("file") or ""))
                if ok:
                    ensure_index()
                return self._send_json(200, {
                    "ok": bool(ok), "kind": "study", "nodes": [], "answer": said,
                    "study": scholar.MANAGER.state()})

            if cmd == "promote":
                # THE ONE PATH OUT OF THE SANDBOX, AND IT IS BEHIND A GATE, which is the reason
                # this branch is longer than the two above it. scholar._guarded_write() refuses
                # every destination outside notes/study/auto/, so promote() had to be written
                # around it deliberately - and the thing that makes that safe is not the code in
                # scholar.py, it is the confirmation raised here and the spoken Yes that answers
                # it. `confirm` false means "ask him"; the page shows the card and posts again
                # with confirm true only after a word it heard.
                rel = str(data.get("file") or "")
                if not bool(data.get("confirm")):
                    return self._send_json(200, {
                        "ok": False, "kind": "study", "nodes": [], "confirm": True,
                        "file": rel,
                        "answer": ("Promote %s into your own notes, %s? That moves it out of "
                                   "the study folder for good." % (rel.split("/")[-1],
                                                                   boss_call)),
                        "study": scholar.MANAGER.state()})
                ok, said, dest = scholar.promote(rel, str(data.get("folder") or "personal"))
                if ok:
                    ensure_index()
                return self._send_json(200, {
                    "ok": bool(ok), "kind": "study", "nodes": [], "answer": said,
                    "file": dest, "study": scholar.MANAGER.state()})

            return self._send_json(400, {
                "ok": False, "kind": "study", "nodes": [],
                "error": "Unknown study command %r." % cmd[:40],
                "study": scholar.MANAGER.state()})

        if route == "/chain/execute":
            # THE CHAIN'S DOOR, and it is a NAME rather than a second way in. Every line
            # below is the same as /execute's, deliberately and by delegation: the same
            # doorman_refusal() above the same hands.execute(), which dispatches to the halt
            # law only because the slot it claimed happens to hold steps.
            #
            # WHY NOT A PARALLEL EXECUTOR. Because the guards are what this file is for. A
            # /chain/execute that claimed the slot itself would have needed its own copy of
            # the stale-id check, the TTL check, the busy refusal and the Doorman - four
            # guards, re-derived, at the one door where the mistake runs several hands
            # instead of one. So it refuses to be more than a label: it is here because the
            # mandate names it and because a page posting a plan should say so, and it can do
            # nothing /execute could not.
            #
            # IT DOES NOT CHECK THAT THE SLOT IS A CHAIN, on purpose. A tab that posted a
            # plan to the wrong door has still given consent to the thing that is actually
            # pending, and refusing it would mean the employer pressing Yes twice for
            # reasons that are none of his business.
            data = self._read_json() or {}
            if not isinstance(data, dict):
                data = {}
            door = str(data.get("door") or "button")[:16].lower()
            if door not in ("button", "voice", "curl"):
                door = "button"
            refusal, _seal = doorman_refusal(data, str(data.get("session")
                                                       or "default")[:120], "yes")
            if refusal is not None:
                refusal["pending"] = hands.pending_public()
                return self._send_json(403, refusal)
            # §42: THE SLOT IS READ BEFORE IT IS CLAIMED. execute() empties it, so this is
            # the last moment the approved parameters exist to be read - see _hand_link().
            approved = hands.pending_public()
            try:
                status, payload = hands.execute(
                    door=door, proposal_id=str(data.get("id") or "")[:40] or None)
            except Exception as exc:                            # noqa: BLE001
                status, payload = 500, {
                    "ok": False, "kind": "tool", "nodes": [], "pending": None,
                    "error": "The chain hit an unexpected error: %s" % exc,
                    "answer": hands.LINES["failed"].format(reason=str(exc)[:160])}
            _hand_resolved(payload)
            _hand_link(payload, approved)
            # §35 PART 1: if that "yes" was a word the handshake window honoured, the card's own
            # reply carries the seal, because this door never passes through /chat's funnel.
            handshake_stamp(str(data.get("session") or "default")[:120], payload)
            sys.stderr.write("  chain: %s -> %s, stopped at %s\n"
                             % (payload.get("chainId") or "(not a chain)",
                                payload.get("chainStatus") or payload.get("refused")
                                or payload.get("failed") or "?",
                                payload.get("stoppedAt")))
            return self._send_json(status, payload)

        if route == "/execute":
            # THE ONE DOOR THAT RUNS ANYTHING, and it carries consent and nothing else.
            # The tool, the script and the parameters all come from the pending slot the
            # server composed and spoke aloud - so no body posted here, by any tab or any
            # harness, can substitute a recipient between the asking and the doing. With
            # nothing pending this is a refusal, which is check 16(a).
            data = self._read_json() or {}
            if not isinstance(data, dict):
                data = {}
            door = str(data.get("door") or "button")[:16].lower()
            if door not in ("button", "voice", "curl"):
                door = "button"
            # THE DOORMAN, AT THE DOOR THAT ACTUALLY RUNS THINGS. The page recognises "yes"
            # itself while a card is up and posts here - it does not send that word to /chat -
            # so the law has to be here too or the whole of it is one code path from being
            # bypassed by the very door it was written for. See doorman_refusal().
            refusal, _seal = doorman_refusal(data, str(data.get("session") or "default")[:120],
                                             "yes")
            if refusal is not None:
                refusal["pending"] = hands.pending_public()
                return self._send_json(403, refusal)
            # §42: read the slot before execute() claims it - see _hand_link().
            approved = hands.pending_public()
            try:
                status, payload = hands.execute(
                    door=door, proposal_id=str(data.get("id") or "")[:40] or None)
            except Exception as exc:                            # noqa: BLE001
                status, payload = 500, {
                    "ok": False, "kind": "tool", "nodes": [], "pending": None,
                    "error": "The tool hit an unexpected error: %s" % exc,
                    "answer": hands.LINES["failed"].format(reason=str(exc)[:160])}
            _hand_resolved(payload)
            _hand_link(payload, approved)
            # §35 PART 1, at the door the page actually uses when it hears "yes" itself.
            handshake_stamp(str(data.get("session") or "default")[:120], payload)
            return self._send_json(status, payload)

        if route == "/tools":
            # Everything about a proposal EXCEPT running it: propose, cancel, and the
            # lapse sweep the asking tab calls when its own countdown reaches zero. The
            # verbs are separate from /execute on purpose - there is exactly one route in
            # this file that can start a subprocess, and this is not it.
            data = self._read_json() or {}
            if not isinstance(data, dict):
                return self._send_json(400, {
                    "ok": False, "kind": "tool", "nodes": [], "pending": None,
                    "error": "Send a JSON body like {\"cmd\": \"cancel\"}.",
                    "answer": hands.LINES["nothing"]})
            cmd = str(data.get("cmd") or "").strip().lower()[:16]
            ident = str(data.get("id") or "")[:40] or None
            door = str(data.get("door") or "button")[:16].lower()
            try:
                if cmd == "propose":
                    status, payload = hands.propose(
                        data.get("tool"),
                        tool_facts(data.get("tool"), data.get("params")), door=door)
                elif cmd == "chain":
                    # THE PLAN DOOR, and it is the exact sibling of "propose" above: it asks
                    # for a proposal and it cannot run one. Every guard the /chat path gets -
                    # find(), validate(), the reference rules, the cap, the readings - is
                    # inside propose_chain(), so a plan that arrives here is judged by the
                    # same code that judges a plan the model sent, and consent is still only
                    # ever given at /execute or /chain/execute under the doorman.
                    #
                    # IT TAKES THE MODEL'S OWN TEXT IF IT IS OFFERED, which is why `said` is
                    # read before `steps`: chain_tag() is the part of this feature that a
                    # regression test cannot reach any other way, and it is the part that was
                    # measured wrong first - the "}}]]" terminator. A harness posting a
                    # ready-made array would prove propose_chain() and leave the scanner,
                    # which is where the bug was, untested for ever.
                    plan = data.get("steps")
                    if isinstance(data.get("said"), str):
                        plan, why, _rest = hands.chain_tag(data.get("said"))
                        if plan is None:
                            status, payload = 400, {
                                "ok": False, "kind": "tool", "nodes": [], "pending": None,
                                "error": "That carried no chain: %s." % (why or "no chain tag"),
                                "answer": hands.LINES["chainempty"], "why": why or "no tag"}
                            return self._send_json(status, payload)
                    status, payload = hands.propose_chain(plan, door=door, facts=tool_facts)
                elif cmd == "cancel":
                    # AND THE SAME AT THE NO. A guest's no cancels a proposal the boss made
                    # and is waiting on, which is a decision about his business, not an
                    # opinion about it. See doorman_refusal().
                    refusal, _seal = doorman_refusal(
                        data, str(data.get("session") or "default")[:120], "no")
                    if refusal is not None:
                        refusal["pending"] = hands.pending_public()
                        return self._send_json(403, refusal)
                    status, payload = hands.cancel(door=door, proposal_id=ident)
                    # A no at the button door, told to the same organ the spoken no is
                    # told to. This is where "the card says plainly that tab-lock is off
                    # and why" actually happens.
                    _hand_resolved(payload)
                    # §35 PART 1: a "nahi" that inherited BOSS gets the seal on its refusal too.
                    # The window is already spent by then - handshake_honour() closes on the
                    # first confirmation of EITHER polarity, because a no answers the question
                    # just as finally as a yes does and leaves nothing further to authorise.
                    handshake_stamp(str(data.get("session") or "default")[:120], payload)
                elif cmd == "withdraw":
                    # A CHANGED SUBJECT, from a door that is not /chat: the page took a
                    # sentence to an organ of its own - the screen, the eyes, a capture -
                    # while something was pending. The law is the same wherever the
                    # subject changes, so the proposal goes here too, and the line comes
                    # back for the tab to show.
                    line = hands.withdraw()
                    status, payload = 200, {
                        "ok": True, "kind": "tool", "nodes": [], "pending": None,
                        "answer": line, "withdrew": bool(line)}
                elif cmd in ("lapse", "sweep"):
                    status, payload = hands.lapse_if_due()
                    # A question that ran out of time is no consent, and the session is
                    # told so: better a card that says tab-lock is off than one that waits
                    # for an answer nobody is going to give.
                    _hand_resolved(payload)
                    if payload is None:
                        # Nothing had run out of time. Not an error, and not a line worth
                        # speaking either - the tab simply asked.
                        state = hands.state()
                        status, payload = 200, {
                            "ok": True, "kind": "tool", "nodes": [], "answer": "",
                            "pending": state["pending"], "busy": state["busy"]}
                else:
                    state = hands.state()
                    status, payload = 400, {
                        "ok": False, "kind": "tool", "nodes": [],
                        "error": "cmd must be propose, chain, cancel, withdraw or lapse.",
                        "answer": "", "pending": state["pending"]}
            except Exception as exc:                            # noqa: BLE001
                status, payload = 500, {
                    "ok": False, "kind": "tool", "nodes": [], "pending": None,
                    "error": "The hands hit an unexpected error: %s" % exc,
                    "answer": hands.LINES["failed"].format(reason=str(exc)[:160])}
            # §35 PART 1, THE OTHER HALF OF THE WINDOW. /chat opens one when the model's answer
            # leaves a gate standing; this is the door the PAGE uses to raise a card directly,
            # and a law written at only one of the two doors is a boss who gets his handshake on
            # some proposals and not others. It is placed after the whole try/except and gated on
            # the payload carrying a `pending`, so it covers propose and chain without naming
            # either, and cancel/withdraw/lapse - which end a proposal rather than raise one -
            # reach it with pending None and open nothing.
            handshake_offer(str(data.get("session") or "default")[:120], data, payload)
            return self._send_json(status, payload)

        if route == "/reset":
            data = self._read_json() or {}
            session = str(data.get("session") or "default")[:120]
            with _lock:
                _history.pop(session, None)
            # The ↻ button forgets the CONVERSATION, and the last question is part of
            # the conversation: leaving it behind would let a follow-up inherit a subject
            # from a chat that, as far as the employer is concerned, never happened.
            # Outside the `with` above on purpose - _lock is not reentrant.
            forget_ask()
            # And a proposal in flight is part of the conversation too. The ↻ button
            # clears it with everything else: a request left pending across a forget
            # could be confirmed by a "yes" belonging to a conversation that, as far as
            # the employer is concerned, never happened.
            dropped = hands.clear_pending("the reset button")
            # AND THE INSTRUMENT IS PART OF THE CONVERSATION TOO, which is the Scribe's law
            # applied to a thing that did not exist when it was written: the turn ring holds
            # the employer's own sentences, in RAM, and a forget button that left forty of
            # them behind for a harness to read would be a forget button with an exception.
            # The turn counter goes with them, so the next question is turn 1 again.
            forget_turns(session)
            # AND THE SUMMARY OF WHAT WAS ALREADY FORGOTTEN ONCE. The whole point of the
            # summary is that it outlives the window, so it is the one piece of the
            # conversation a reset would otherwise leave standing - and a pinned first
            # question surviving a forget button would be the loudest bug in the file.
            forget_older(session)
            # §35 PART 3 - AND THE FINISHED JOBS, on exactly the rule above. The result line the
            # Director leaves in the answer card is a thing the page polls off /jobs, so a forget
            # button that cleared the card and left the row standing would put the result back on
            # the glass at the next poll - two and a half seconds after he asked for it to go.
            # forget_all() drops FINISHED jobs only, so a render still in flight keeps its chip:
            # the ↻ button forgets a conversation and does not stop a machine mid-encode.
            jobs_seen = len((jobs.public() or {}).get("jobs") or [])
            jobs.forget_all("the reset button")
            return self._send_json(200, {"ok": True, "forgotten": session,
                                         "proposalDropped": dropped,
                                         "jobsSeen": jobs_seen})

        return self._send_json(404, {"error": "No such endpoint: %s" % route})

    def log_message(self, fmt, *args):
        sys.stderr.write("  %s\n" % (fmt % args))


def _warm_log(line):
    """One line from the warm thread, to stderr where every other diagnostic goes."""
    sys.stderr.write("%s\n" % line)


def main():
    if not os.path.isdir(VIEWER_DIR):
        sys.exit("server.py: no viewer/ directory next to this file.")
    load_config()
    ensure_index()

    handler = partial(GalaxyHandler, directory=VIEWER_DIR)
    httpd = ThreadingHTTPServer((HOST, PORT), handler)
    httpd.daemon_threads = True

    cfg = load_config()[0]
    ready = credentials_error(cfg) is None
    print("")
    # WHAT HE CAN DO, COUNTED ONCE, HERE. After ensure_index() so the note count is real
    # and before the first request so no question pays for it. The vector store is still
    # warming on the thread below, so the archive sentence may be absent from this first
    # manifest - which is honest rather than broken: it says what was true at start-up, and
    # it is rebuilt on the next restart like every other line in it.
    who = persona(cfg)
    build_capabilities_manifest(cfg)

    # The PRODUCT is the Knowledge Galaxy - that name is in the page title and in three
    # harnesses, and it stays. The ASSISTANT is Galaxy, and he gets his own line.
    print("  Knowledge Galaxy  ->  http://%s:%d" % (HOST, PORT))
    print("  serving           :  viewer/  (only)")
    print("  assistant         :  %s, for %s (%s)"
          % (who["assistant"], who["boss_formal"], who["boss_call"]))
    print("  notes indexed     :  %d" % len(_index["notes"]))
    print("  provider          :  %s" % provider_of(cfg))
    print("  model             :  %s" % model_label(cfg))
    # §41 - AND WHAT CATCHES IT, ON ITS OWN LINE, because a net nobody is told about is a
    # net nobody checks. The model id and the loopback url, never a key and never a region.
    print("  fallback          :  %s" % (
        "local %s on %s" % (ollama_chat_model(cfg),
                            str(cfg.get("ollama_url") or DEFAULT_CONFIG["ollama_url"]))
        if ollama_fallback_enabled(cfg) else
        "off - a tired Groq will refuse out loud (\"ollama_fallback\": false)"))
    print("  credentials       :  %s" % (
        "loaded from config.json" if ready else
        "not configured yet - /chat will say so politely"))
    print("  ctrl-c to stop")
    print("")

    # ---- OPEN THE VECTOR STORE NOW, ON A THREAD, SO NO QUESTION PAYS FOR IT.
    # ChromaDB's first PersistentClient in a process costs about four seconds on this
    # machine - sqlite opened, an HNSW index memory-mapped - and every open after it is a
    # fraction of that. Left alone, that four seconds would land on whoever asked the
    # first question of the session, which is the worst possible place to spend it and the
    # hardest to explain. So it is spent here instead, after the socket is already bound
    # and listening: the page loads, the galaxy paints, and by the time anybody has
    # finished typing the store is warm. A daemon thread, so ctrl-c still exits at once,
    # and errors are the thread's own business - warm() reports and returns rather than
    # raising, and a failure only means the first question pays after all.
    if ingest is not None:
        threading.Thread(target=ingest.warm, kwargs={"log": _warm_log},
                         name="vector-warm", daemon=True).start()

    # ---- AND §41's LOCAL THINKER, ON ITS OWN THREAD, FOR THE SAME REASON AND A MEASURED
    # one: see ollama_warm(). A cold 7B prefill on this CPU took 30.07s and tripped the
    # engine's own 30s ceiling, which the boss would have met as a refusal on the first
    # question Groq declined. Warm, the same prompt answers in 1.8s. Daemon, silent on a
    # machine with no Ollama, and it holds no lock any question can wait on.
    threading.Thread(target=ollama_warm, kwargs={"log": _warm_log},
                     name="ollama-warm", daemon=True).start()

    # ---- AND THE TRANSCRIBER, FOR THE SAME REASON AND ON ITS OWN THREAD. A warm load
    # of base.en costs 0.98s on this machine and a cold one pays for a 145 MB download
    # once; either way it is spent here, after the socket is listening, rather than on
    # the first three seconds of somebody's meeting. scribe.warm() returns False and
    # says nothing on a machine without faster-whisper - the organ reads that off
    # /health and refuses politely.
    if scribe is not None and scribe.warm():
        print("  transcriber       :  %s warming on a thread (cpu, int8)"
              % scribe.MODEL_NAME)

    # ---- AND THE SCHOLAR, ON ITS OWN THREAD, SHARING NO LOCK WITH ANY OF THE ABOVE.
    # After the socket is listening, like the two warmers - but for a different reason: those
    # two are spending a cost early, this one is a loop that will run all day. It takes
    # scholar.MANAGER's own lock and nothing of this file's, so a study in progress cannot
    # delay a question; the note it writes is published by build.py in a subprocess and picked
    # up by the next turn's own mtime check in ensure_index(). Daemon, so ctrl-c still exits at
    # once, and the loop's exceptions are its own business - tick() reports and returns rather
    # than raising, and a failed study is a ledger row, not a dead server.
    tools = scholar.tool_report()
    missing = [n for n, r in tools.items() if not r["found"]]
    if scholar.MANAGER.start():
        print("  scholar           :  %s on a thread · %s"
              % (", ".join(t["name"] for t in scholar.read_syllabus()["topics"]) or "no topics",
                 "yt-dlp, ffmpeg, ffprobe present" if not missing
                 else "MISSING %s - audio study will refuse and say so" % ", ".join(missing)))

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n  shutting down")
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
