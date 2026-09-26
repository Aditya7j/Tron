#!/usr/bin/env python3
"""
server.py - Knowledge Galaxy server + brain.

  GET  /            static files from ./viewer ONLY (nothing above it is reachable)
  GET  /health      {"ok": true, ...} - a cheap liveness probe
  GET  /persona     the boot greeting wording, for the viewer to fill in
  POST /chat        {"question": "...", "session": "..."}
                 -> {"answer": "...", "nodes": [...], "kind": "notes"|"chat"}
  POST /remember    {"text": "remember that ..."} - writes a real markdown file
                    into <notes>/captures/, re-indexes in-process, and returns the
                    new node plus the whole link set for the viewer to splice in
  POST /see         ?q=<question>, body = ONE JPEG frame of the user's screen,
                    Content-Type: image/jpeg  ->  {"answer", "kind": "screen"}
  POST /reset       forgets the conversation history for a session

The assistant's character lives in one clearly marked PERSONA block at the top of
this file - edit that and nothing else to rewrite it.

Two model providers, chosen by "provider" in config.json:

  "bedrock"  (default)  AWS Bedrock Converse, signed with SigV4 by hand below.
                        Credentials come from config.json, then the environment,
                        then ~/.aws/credentials - the first complete pair wins.
  "openai"              api.openai.com, keyed by "openai_api_key".

config.json lives in the PROJECT ROOT, which is outside the served directory. No
credential of either kind is ever sent to the browser, and config.json is re-read
on every request so you can paste keys in without restarting.

  python server.py            run it
  python server.py --models   list the Bedrock model ids this account may use

Python 3, standard library only - no boto3.
"""

import base64
import configparser
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
    tool = str(payload.get("ran") or payload.get("tool")
               or payload.get("lapsed") or "")
    if not tool:
        return
    try:
        focus.MANAGER.hand_outcome(tool, "done" if payload.get("ran") else "no")
    except Exception:                                          # noqa: BLE001
        pass


focus.ASK_HAND = _focus_ask_hand
# THE LOCAL VOICE. Text in, WAV bytes out, through the piper binary as a subprocess -
# no pip dependency and nothing leaving the machine. Its own file for the same reason
# the three above have theirs: it owns a cache directory, a concurrency gate and the
# two knobs that decide how the voice sounds. Like search.py it NEVER raises, so a
# machine with no piper installed simply reports that it is not ready and the page
# falls back to the browser's own engine.
import say

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

DEFAULT_CONFIG = {
    # "bedrock" or "openai". Bedrock is the default because it can run on AWS
    # credentials you already have, with no second account and no second key.
    "provider": "bedrock",

    # ---- bedrock. Leave the three aws_* credentials blank to use the environment
    # or ~/.aws/credentials, which is the usual case. See resolve_aws() below.
    "aws_region": "us-east-1",
    "aws_profile": "",
    "aws_access_key_id": "",
    "aws_secret_access_key": "",
    "aws_session_token": "",
    # An inference profile, not a bare model id: modern Claude models on Bedrock are
    # only reachable through one. "python server.py --models" lists the alternatives.
    "bedrock_model_id": "us.anthropic.claude-sonnet-5",

    # ---- openai, used only when "provider" is "openai"
    "openai_api_key": "PUT-YOUR-KEY-HERE",
    "model": "gpt-6-astra",

    # ---- openrouter: one key that reaches every model in SPOKEN_MODELS below.
    # Every voice swap routes here, so this is the key a swap needs. Set "provider"
    # to "openrouter" to start here; a swap never writes to either of these, which
    # is why a restart always returns you to whatever this file says.
    "openrouter_api_key": "",
    "openrouter_model": "openai/gpt-6-astra",

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
    "notes_threshold": 0.60,
}
PLACEHOLDER_KEYS = {"", "put-your-key-here", "your-key-here", "sk-xxx", "changeme"}

# Bedrock model ids are long and easy to get subtly wrong, so a handful of short
# names resolve to a real inference profile. Anything not listed here is passed
# through untouched, and "python server.py --models" is the source of truth.
# The "us." prefix routes within the US; other regions use their own ("eu.", "apac.").
MODEL_ALIASES = {
    "haiku": "us.anthropic.claude-haiku-4-5-20251001-v1:0",
    "sonnet": "us.anthropic.claude-sonnet-5",
    "opus": "us.anthropic.claude-opus-5",
    "nova": "us.amazon.nova-pro-v1:0",
}

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

OPENAI_URL = "https://api.openai.com/v1/chat/completions"
MAX_ANSWER_TOKENS = 400   # the butler is brief; this is a ceiling, not a target
# None means "whatever the model's own default is", and that is deliberate: the
# newer models reject `temperature` outright ("deprecated for this model"), so
# sending a value would break them. Set a float here only for an older model.
TEMPERATURE = None
TOP_K = 6                 # most notes ever handed to the model
TITLE_WEIGHT = 3.5        # a hit in the title counts far more than one in the body
CONTEXT_CHARS = 1500      # per note, sent to the model
HISTORY_TURNS = 4         # user+assistant pairs kept per session
PRIOR_WEIGHT = 0.4        # how much the previous question steers retrieval
REQUEST_TIMEOUT = 60

# Sent to every provider, AWS included. Bedrock is signed without it - see the note
# where it is attached - and OpenRouter shows it in the activity log, which is the
# only reason it names a version: a swap that misbehaves is easier to place in time.
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
FRAME_MAX_BYTES = 4 * 1024 * 1024    # comfortably inside Bedrock's per-image limit
FRAME_MIN_BYTES = 900                # below this there is no picture, only a header
FRAME_MIN_EDGE = 140                 # a 60px sliver is not something to judge
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


def protected_answer(question, cfg=None, ear_open=False):
    """(class, payload) for a message that is about this machine, else (None, None).

    Classes 2 and 3 only. Class 1 lives above this in _hands_gate(), where the pending
    offer is, and class 4 is the Third Door and the registry, which answer_question()
    already owns. Zero retrieval either way: this function reaches the notes, the archive
    and the web exactly never, which is asserted rather than asserted-to in routing_proof.
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
    if not name:
        return None, None
    return name, {"ok": True, "kind": "chat", "nodes": [], "answer": line,
                  "route": name, "lookups": 0, "protected": name}


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
    messages = ([{"role": "system",
                  "content": SMALLTALK_PROMPT + hands.prompt_block()
                             + proposal_context(pending)}]
                + history + [{"role": "user", "content": question.strip()}])
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
    with _lock:
        hist = _history.setdefault(session, [])
        hist.append({"role": "user", "content": question.strip()})
        hist.append({"role": "assistant", "content": answer})
        del hist[:max(0, len(hist) - HISTORY_TURNS * 2)]
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
    notes CANNOT ANSWER IT. The two vetoes above the score are what makes the first half
    true - small talk and questions about this machine are turned back before any number
    is consulted at all, so "good morning" still costs nothing and touches nothing.

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
    if brain:
        merged["provider"] = "openrouter"
        merged["openrouter_model"] = brain
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

SEM_CONTEXT_CHARS = 1200      # per chunk, sent to the model


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


# ------------------------------------------------------------- aws  credentials
#
# Looked for in this order, and the FIRST source holding both an id and a secret
# wins outright. Sources are never mixed: half a key pair from config.json and
# half from the environment is how you get a signature error you cannot read.
#
#   1. config.json         aws_access_key_id / aws_secret_access_key / aws_session_token
#   2. the environment     AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY / AWS_SESSION_TOKEN
#   3. ~/.aws/credentials  under aws_profile, else $AWS_PROFILE, else "default"
#
# The region is allowed to come from anywhere, including ~/.aws/config, because a
# region is not a secret and a mismatched one fails loudly rather than silently.

CRED_FIELDS = ("aws_access_key_id", "aws_secret_access_key", "aws_session_token")


def _read_aws_ini(path, profile):
    """One profile out of an ~/.aws ini file. Missing or malformed reads as {}."""
    if not path or not os.path.exists(path):
        return {}
    parser = configparser.RawConfigParser()
    try:
        parser.read(path, encoding="utf-8")
    except Exception:                                          # noqa: BLE001
        return {}
    # ~/.aws/credentials uses [name]; ~/.aws/config uses [profile name].
    for section in (profile, "profile " + profile):
        if parser.has_section(section):
            return {k.lower(): str(v).strip() for k, v in parser.items(section)}
    return {}


def _blank(value):
    text = str(value or "").strip()
    return not text or text.upper().startswith("PUT-")


def resolve_aws(cfg):
    """Returns (creds, error). creds = {key, secret, token, region, source}."""
    profile = (str(cfg.get("aws_profile") or "").strip()
               or os.environ.get("AWS_PROFILE", "").strip() or "default")
    home = os.path.expanduser("~")
    cred_file = (os.environ.get("AWS_SHARED_CREDENTIALS_FILE")
                 or os.path.join(home, ".aws", "credentials"))
    conf_file = os.environ.get("AWS_CONFIG_FILE") or os.path.join(home, ".aws", "config")
    shared = _read_aws_ini(cred_file, profile)
    conf = _read_aws_ini(conf_file, profile)

    candidates = (
        ("config.json", {f: cfg.get(f) for f in CRED_FIELDS}),
        ("the environment", {f: os.environ.get(f.upper()) for f in CRED_FIELDS}),
        ("~/.aws/credentials [%s]" % profile, shared),
    )
    region = next((str(v).strip() for v in (
        cfg.get("aws_region"), os.environ.get("AWS_REGION"),
        os.environ.get("AWS_DEFAULT_REGION"), conf.get("region"),
    ) if not _blank(v)), DEFAULT_CONFIG["aws_region"])

    for source, bag in candidates:
        if _blank(bag.get("aws_access_key_id")) or _blank(bag.get("aws_secret_access_key")):
            continue
        return {
            "key": str(bag["aws_access_key_id"]).strip(),
            "secret": str(bag["aws_secret_access_key"]).strip(),
            "token": "" if _blank(bag.get("aws_session_token"))
                     else str(bag["aws_session_token"]).strip(),
            "region": region,
            "source": source,
        }, None

    return None, ("No AWS credentials found, so I found the relevant notes but "
                  "cannot write an answer. Put aws_access_key_id and "
                  "aws_secret_access_key in config.json in the project root, or set "
                  "AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY, or run \"aws "
                  "configure\" to write ~/.aws/credentials. No restart needed.")


# ------------------------------------------------------------------------ sigv4
#
# Signature Version 4 by hand, because boto3 is not in the standard library and
# this project promised no dependencies. Four steps: build a canonical request,
# hash it into a string to sign, derive a date/region/service key, sign.
#
# The one trap: outside S3, SigV4 wants each path segment percent-encoded TWICE in
# the canonical request, while the path on the wire is encoded once. Bedrock model
# ids contain a colon ("...-v1:0"), so the request path carries %3A and the string
# we sign carries %253A. Get this wrong and AWS returns SignatureDoesNotMatch,
# helpfully quoting the canonical string it expected. Paths without reserved
# characters are unaffected, which is why the control-plane calls worked first try.

def _derive_key(secret, stamp, region, service):
    key = ("AWS4" + secret).encode("utf-8")
    for part in (stamp, region, service, "aws4_request"):
        key = hmac.new(key, part.encode("utf-8"), hashlib.sha256).digest()
    return key


def aws_request(creds, service, host, path, body=b"", method="POST", query=""):
    """A SigV4-signed call. Raises urllib errors; callers translate them."""
    amz_date = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    stamp = amz_date[:8]
    payload_hash = hashlib.sha256(body).hexdigest()

    headers = {"host": host, "x-amz-date": amz_date}
    if body:
        headers["content-type"] = "application/json"
    if creds.get("token"):
        # Temporary credentials only. Omit it and STS-issued keys fail as invalid.
        headers["x-amz-security-token"] = creds["token"]

    names = sorted(headers)
    signed_headers = ";".join(names)
    canonical = "\n".join([
        method,
        urllib.parse.quote(path, safe="/-._~"),    # the second encoding pass
        query,
        "".join("%s:%s\n" % (n, headers[n].strip()) for n in names),
        signed_headers,
        payload_hash,
    ])
    scope = "%s/%s/%s/aws4_request" % (stamp, creds["region"], service)
    to_sign = "\n".join([
        "AWS4-HMAC-SHA256", amz_date, scope,
        hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
    ])
    signature = hmac.new(_derive_key(creds["secret"], stamp, creds["region"], service),
                         to_sign.encode("utf-8"), hashlib.sha256).hexdigest()
    headers["authorization"] = (
        "AWS4-HMAC-SHA256 Credential=%s/%s, SignedHeaders=%s, Signature=%s"
        % (creds["key"], scope, signed_headers, signature))
    headers["user-agent"] = USER_AGENT          # after signing: not a signed header

    url = "https://%s%s%s" % (host, path, ("?" + query) if query else "")
    req = urllib.request.Request(url, data=(body or None), headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as res:
        return json.loads(res.read().decode("utf-8", "replace") or "{}")


def aws_error_message(exc, model, creds):
    """Turn an HTTPError from Bedrock into one sentence a human can act on."""
    detail = ""
    try:
        payload = json.loads(exc.read().decode("utf-8", "replace"))
        detail = str(payload.get("message") or payload.get("Message") or "").strip()
    except Exception:                                          # noqa: BLE001
        pass
    kind = ""
    try:
        kind = str(exc.headers.get("x-amzn-ErrorType", "")).split(":")[0]
    except Exception:                                          # noqa: BLE001
        pass
    region = creds.get("region", "?")
    low = detail.lower()

    if exc.code in (401, 403) and ("security token" in low or "expired" in low):
        return ("AWS rejected the credentials (403): %s Temporary keys from a "
                "session token expire - refresh them and ask again." % detail)
    if exc.code in (401, 403) and "signature" in low:
        return ("AWS could not verify the request signature (403): %s Usually the "
                "secret access key is truncated or has a stray space." % detail)
    if exc.code == 403:
        return ("AWS denied the call (403): %s Either the IAM identity lacks "
                "bedrock:InvokeModel, or access to \"%s\" has not been granted in "
                "%s yet." % (detail, model, region))
    # Two very different image failures arrive as the same ValidationException, and
    # the generic "check the model id" advice below would misdirect both. Order
    # matters: a frame Bedrock could not decode says nothing about the model, and
    # telling someone to change a model id that is perfectly fine wastes an evening.
    if exc.code == 400 and "image" in low and (
            "could not process" in low or "malformed" in low or "invalid" in low):
        return ("Bedrock could not read that frame as an image: %s The bytes reached "
                "it intact, so this is the encoding, not the connection." % detail)
    if exc.code == 400 and ("image" in low or "modality" in low or "vision" in low):
        return ("\"%s\" will not accept an image in %s: %s Set "
                "\"bedrock_model_id\" in config.json to a model that reads images "
                "(the Claude 4.5+ ids all do)." % (model, region, detail))
    if exc.code in (400, 404) or kind in ("ValidationException", "ResourceNotFoundException"):
        return ("Bedrock will not accept the model id \"%s\" in %s (HTTP %s). %s "
                "Run \"python server.py --models\" to see the ids this account may "
                "use." % (model, region, exc.code, detail))
    if exc.code in (429, 503):
        return ("Bedrock is throttling or at capacity (HTTP %s). %s"
                % (exc.code, detail)).strip()
    return ("Bedrock returned HTTP %s %s. %s" % (exc.code, kind, detail)).strip()


# --------------------------------------------------------------------- the model

def provider_of(cfg):
    name = str(cfg.get("provider") or DEFAULT_CONFIG["provider"]).strip().lower()
    if name in ("openrouter", "open router", "router", "or"):
        return "openrouter"
    return "openai" if name in ("openai", "oai", "gpt") else "bedrock"


def display_label(model_id):
    """A model id as it should be read aloud or shown on the chip.

    ONE rule about digits, and it is the whole reason this is a function: a hyphen
    with a digit on either side is a version dot, and every other hyphen is a word
    gap. So "fable-5-1" is FABLE 5.1 while "gpt-6-astra" is GPT 6 ASTRA - not GPT
    6.ASTRA, and not FABLE 5 1.
    """
    name = str(model_id or "").split("/")[-1]
    name = re.sub(r"^(?:us|eu|apac)\.", "", name, flags=re.I)      # bedrock routing
    name = re.sub(r"^(?:anthropic|amazon|meta|mistral|openai|google)\.", "", name,
                  flags=re.I)
    name = re.sub(r"^claude-", "", name, flags=re.I)
    # Bedrock's tail: a date stamp and a "-v1:0", stripped before the digit rule so
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
    wanted = str(cfg.get("bedrock_model_id")
                 or DEFAULT_CONFIG["bedrock_model_id"]).strip()
    # "haiku", "claude-haiku" and "anthropic.claude-haiku" all mean the same thing.
    return MODEL_ALIASES.get(re.sub(r"^(anthropic\.|amazon\.|claude-)", "",
                                    wanted.lower()), wanted)


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
    return {
        "engine": engine,
        "model": state["model"],
        "installed": state["binary"],
        "modelPresent": state["model_file"],
        # The question the page actually asks: can I fetch audio from /say? Wanting the
        # web engine is a "no" just as firmly as a missing binary is.
        "ready": engine == "piper" and state["ready"],
        "why": (state["why"] if engine == "piper"
                else "config.json asks for the browser's voices"),
        "lengthScale": state["lengthScale"],
        "noiseScale": state["noiseScale"],
        "cacheFiles": files,
        "cacheBytes": size,
    }


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
        the AWS keys is not a state this project is going to have.

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


def bedrock_path(model, action="converse"):
    # safe="-._~" is exactly what the AWS SDKs treat as unreserved, so the colon
    # in a model id becomes %3A here and in the string we sign. See aws_request().
    return "/model/%s/%s" % (urllib.parse.quote(model, safe="-._~"), action)


def converse_body(messages, image=None):
    """The OpenAI message shape this code already speaks -> Bedrock Converse.

    Converse keeps the system prompt in its own field, wraps every turn's text in
    a content block, and insists the turns start with the user and then alternate.

    `image` is raw JPEG bytes and rides on the final user turn, ahead of its text,
    which is the order Anthropic's own guidance asks for with a single image.
    """
    system = [{"text": m["content"]} for m in messages if m["role"] == "system"]
    turns = [m for m in messages if m["role"] in ("user", "assistant")]
    while turns and turns[0]["role"] != "user":
        turns.pop(0)                       # a stray leading assistant turn is fatal
    merged = []
    for turn in turns:
        if merged and merged[-1]["role"] == turn["role"]:
            merged[-1]["content"][0]["text"] += "\n\n" + turn["content"]
        else:
            merged.append({"role": turn["role"],
                           "content": [{"text": turn["content"]}]})
    if image and merged and merged[-1]["role"] == "user":
        # Converse takes the format as a bare word ("jpeg"), so it is derived from
        # the one media-type constant rather than written out a second time.
        merged[-1]["content"].insert(0, {"image": {
            "format": FRAME_MEDIA_TYPE.split("/")[-1],
            "source": {"bytes": base64.b64encode(image).decode("ascii")},
        }})
    body = {"messages": merged, "inferenceConfig": {"maxTokens": MAX_ANSWER_TOKENS}}
    if TEMPERATURE is not None:
        body["inferenceConfig"]["temperature"] = TEMPERATURE
    if system:
        body["system"] = system
    return body


def call_bedrock(cfg, messages, image=None):
    """Returns (answer, error). Never raises."""
    creds, error = resolve_aws(cfg)
    if error:
        return None, error
    model = model_label(cfg)
    body = json.dumps(converse_body(messages, image)).encode("utf-8")
    try:
        # bedrock-runtime signs under the service name "bedrock", not its hostname.
        data = aws_request(creds, "bedrock",
                           "bedrock-runtime.%s.amazonaws.com" % creds["region"],
                           bedrock_path(model), body)
    except urllib.error.HTTPError as exc:
        return None, aws_error_message(exc, model, creds)
    except urllib.error.URLError as exc:
        return None, ("Could not reach Bedrock in %s (%s)."
                      % (creds["region"], exc.reason))
    except Exception as exc:                                   # noqa: BLE001
        return None, "Unexpected error talking to Bedrock: %s" % exc

    try:
        blocks = data["output"]["message"]["content"]
        answer = "".join(b.get("text", "") for b in blocks).strip()
    except Exception:                                          # noqa: BLE001
        return None, ("Bedrock replied in an unexpected shape: %s"
                      % json.dumps(data)[:300])
    if not answer:
        return None, "Bedrock returned an empty answer."
    return answer, None


def call_chat_completions(url, key, model, who, messages, image=None, extra=None):
    """OpenAI's /chat/completions shape, which OpenRouter speaks too.

    Returns (answer, error) and never raises. One implementation for both, because
    a second copy is how the image block ends up correct in one place only.
    """
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
        return None, "Could not reach the %s API (%s)." % (who, exc.reason)
    except Exception as exc:                                   # noqa: BLE001
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


def call_model(cfg, messages, image=None):
    """The one place that decides which provider gets the prompt.

    `image` is raw bytes of type FRAME_MEDIA_TYPE, or None. Both providers below
    encode it themselves, because they disagree about the shape and agree about
    nothing except the media type.
    """
    messages = wear_persona(cfg, messages)
    provider = provider_of(cfg)
    if provider == "openrouter":
        return call_openrouter(cfg, messages, image)
    if provider == "openai":
        return call_openai(cfg, messages, image)
    return call_bedrock(cfg, messages, image)


def credentials_error(cfg):
    """None when the model is callable, else one sentence saying what is missing."""
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
                    "\"provider\" to \"bedrock\" to use your AWS credentials "
                    "instead. No restart needed.")
        return None
    return resolve_aws(cfg)[1]


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
        "label": display_label(active),
        "provider": provider_of(cfg),
        "swapped": bool(override),
        "keyConfigured": credentials_error(cfg) is None,
        # What "go back to your normal brain" and a restart both mean, which is the
        # same thing by construction: this is read from the file, not from memory.
        "configModel": model_label(on_disk),
        "configLabel": display_label(model_label(on_disk)),
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
    global _brain
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


def restore_brain(door="voice"):
    """Back to whatever config.json says, which is also what a restart means."""
    global _brain
    with _brain_lock:
        was = _brain
        _brain = None
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
# "remember that X" writes a real markdown file and folds it into the live index.
#
# Two rules this section exists to enforce:
#
#   1. Writing a file is not indexing it. Every capture re-reads the corpus through
#      build.py's OWN functions and rewrites both notes-index.json and
#      graph-data.js, so the new note is retrievable by /chat on the very next
#      question with no rebuild step. Nothing here reimplements build.py's linking
#      rules - it imports them, so the two can never drift apart.
#   2. A capture never fails quietly. Every path below returns a spoken line, and
#      "written but not indexed" is reported as its own distinct failure rather
#      than being rounded up to success.

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


def write_capture(body, title):
    """Write the markdown file. Returns (relative_path, error)."""
    folder = os.path.join(notes_root(), CAPTURE_DIR)
    try:
        os.makedirs(folder, exist_ok=True)
    except Exception as exc:                                   # noqa: BLE001
        return None, "could not create %s (%s)" % (CAPTURE_DIR, exc)

    stem = build.slugify(title) or "capture"
    now = time.localtime()
    path = os.path.join(folder, stem + ".md")
    # Never overwrite an earlier capture: the same thought twice is two notes.
    suffix = 2
    while os.path.exists(path):
        path = os.path.join(folder, "%s-%d.md" % (stem, suffix))
        suffix += 1
        if suffix > 200:
            return None, "too many notes already named like that"

    text = ("# %s\n\n"
            "Captured %s.\n\n"
            "%s\n" % (title, time.strftime("%A %d %B %Y at %H:%M", now), body))
    try:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
        # Read it back. "The write returned without raising" is not the same claim
        # as "the note is on disk", and this is the one place that difference bites.
        with open(path, "r", encoding="utf-8") as fh:
            if body.split(".")[0][:40] not in fh.read():
                return None, "the file was written but came back empty"
    except Exception as exc:                                   # noqa: BLE001
        return None, "could not write %s (%s)" % (os.path.basename(path), exc)

    return os.path.relpath(path, ROOT).replace("\\", "/"), None


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
    """Capture a thought. Returns (status, payload) and never raises."""
    body = capture_body(text)
    if not body:
        return 400, {"ok": False, "answer": CAPTURE_LINES["empty"],
                     "error": "nothing followed \"remember that\"",
                     "nodes": [], "kind": "capture"}

    ensure_index()
    title = capture_title(body)

    rel, error = write_capture(body, title)
    if error:
        return 500, {"ok": False, "error": error, "nodes": [], "kind": "capture",
                     "answer": CAPTURE_LINES["failed"].format(reason=error)}

    try:
        nodes, links = reindex_preserving_ids()
    except Exception as exc:                                   # noqa: BLE001
        reason = "indexing failed (%s)" % exc
        return 500, {"ok": False, "error": reason, "file": rel, "nodes": [],
                     "kind": "capture",
                     "answer": CAPTURE_LINES["unindexed"].format(reason=reason)}

    node = next((n for n in nodes if n["file"] == rel), None)
    with _lock:
        indexed = {n.get("file") for n in _index["notes"]}
    if node is None or rel not in indexed:
        # The distinct failure the whole section exists to catch: on disk, invisible
        # to /chat. Reported as a failure, never rounded up to success.
        reason = "the note is on disk but did not make it into the index"
        return 500, {"ok": False, "error": reason, "file": rel, "nodes": [],
                     "kind": "capture",
                     "answer": CAPTURE_LINES["unindexed"].format(reason=reason)}

    degree = 0
    for link in links:
        if node["id"] in (link["source"], link["target"]):
            degree += 1

    return 200, {
        "ok": True,
        "answer": CAPTURE_LINES["saved"].format(title=title),
        "kind": "capture",
        "file": rel,
        "title": title,
        "anchor": pick_anchor(node["id"], links, title, body),
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


def answer_question(question, session):
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
        return 400, {"error": cfg_error, "nodes": node_ids, "kind": kind}

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
        messages = [{"role": "system", "content": SMALLTALK_PROMPT + hands.prompt_block()},
                    {"role": "user", "content": question.strip()}]
        said, hands_error = call_model(cfg, messages)
        if not hands_error:
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
        messages = ([{"role": "system", "content": COMPOSE_PROMPT}] + history +
                    [{"role": "user", "content": question.strip()}])
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
        with _lock:
            hist = _history.setdefault(session, [])
            hist.append({"role": "user", "content": question.strip()})
            hist.append({"role": "assistant", "content": answer})
            del hist[:max(0, len(hist) - HISTORY_TURNS * 2)]
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
        # this message list is the shortest one in the file.
        user_msg = ("Question: %s\n\nLive web results you may use, and nothing else:"
                    "\n\n%s" % (query, build_web_context(web)))
        messages = [{"role": "system", "content": WEB_PROMPT},
                    {"role": "user", "content": user_msg}]
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
        with _lock:
            hist = _history.setdefault(session, [])
            hist.append({"role": "user", "content": question.strip()})
            hist.append({"role": "assistant", "content": answer})
            del hist[:max(0, len(hist) - HISTORY_TURNS * 2)]
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
        with _lock:
            hist = _history.setdefault(session, [])
            hist.append({"role": "user", "content": question.strip()})
            hist.append({"role": "assistant", "content": WEB_SILENT_LINE})
            del hist[:max(0, len(hist) - HISTORY_TURNS * 2)]
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
    block = hands.prompt_block() if offer_hands else ""

    if kind == "chat":
        messages = ([{"role": "system", "content": SMALLTALK_PROMPT + block}] + history +
                    [{"role": "user", "content": question.strip()}])
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
        user_msg = ("Question: %s\n\nNotes and documents you may use, and nothing else:"
                    "\n\n%s" % (question.strip(), both))
        messages = ([{"role": "system", "content": SYSTEM_PROMPT + block}] + history +
                    [{"role": "user", "content": user_msg}])

    answer, error = call_model(cfg, messages)
    if error:
        return 502, {"error": error, "nodes": node_ids, "kind": kind,
                     "citations": cites}

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
    if asked is not None:
        if offer_hands:
            return hands.propose(asked, params, door="tag")
        # It was never offered hands for this message and it asked anyway. The tag is
        # not honoured and it is not read out either - a stray control tag spoken aloud
        # is a bug the employer has to interpret.
        sys.stderr.write("  tool: a tag arrived for a message the hands were not "
                         "offered to; ignored\n")
        answer = prose or hands.LINES["instead"]

    with _lock:
        hist = _history.setdefault(session, [])
        # Store the bare question, not the injected note context: history is for
        # follow-ups ("why?"), and re-sending old excerpts would blow up the prompt.
        hist.append({"role": "user", "content": question.strip()})
        hist.append({"role": "assistant", "content": answer})
        del hist[:max(0, len(hist) - HISTORY_TURNS * 2)]

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

    def _send_wav(self, data, source):
        """WAV bytes, with the cache verdict in a header so a harness can read it.

        no-store because the page caches nothing: say-cache/ on disk is the cache, and
        a browser holding a second copy would make a recast voice take a reload to hear.
        """
        self.send_response(200)
        self.send_header("Content-Type", "audio/wav")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Say-Source", source or "miss")
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

        if route == "/brains":
            # What the chip's menu is built from. The BUTTON must not be able to
            # offer a model the voice would be refused, so the menu is this list and
            # this list is derived from the allowlist itself - never typed into the
            # page, where it would drift the first time a model was retired.
            state = brain_state()
            return self._send_json(200, {
                "ok": True, "kind": "model", "nodes": [], "answer": "",
                "models": [{"say": say, "id": mid, "label": display_label(mid),
                            "pretty": pretty_name(mid),
                            "current": mid == state["model"]}
                           for say, mid in sorted(SPOKEN_MODELS.items(),
                                                  key=lambda kv: kv[1])],
                "pinned": sorted(spoken_aliases()),
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
            # Report what is configured, never the credential itself.
            creds = resolve_aws(cfg)[0] if provider_of(cfg) == "bedrock" else None
            doors = [name for name, _ in websearch.backends(cfg)]
            return self._send_json(200, {
                "ok": True,
                "notes": len(_index["notes"]),
                "links": _index["meta"].get("linkCount"),
                "provider": provider_of(cfg),
                "model": model_label(cfg),
                "region": creds["region"] if creds else None,
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
                # AND WHETHER THE SKY TURNS. A preference about the camera, published
                # for the same reason the voice pin is: the browser owns the camera and
                # cannot be told by any other route. Absent or false means the galaxy
                # rests, which is the default and the answer for everybody who has not
                # gone looking for the key.
                "sky": {"spin": bool(cfg.get("galaxy_spin"))},
                # AND HOW LONG THE EAR WAITS. The page runs the conversation - the voice
                # detector, the re-arm, the closers - so it needs the one number that
                # decides when a silent room means goodbye. Clamped here rather than
                # trusted: a zero would close the session before the first word and a
                # config typo must not be able to hold a microphone open all afternoon.
                "ear": {"timeoutS": max(5, min(600, int(
                    _number(cfg.get("conversation_timeout_s"),
                            DEFAULT_CONFIG["conversation_timeout_s"]))))},
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
        note = "captured" if payload.get("ok") else "CAPTURE FAILED"
        sys.stderr.write("  %s: %s\n" % (note, payload.get("file")
                                         or payload.get("error")))
        return status, payload

    def _hands_gate(self, question, session="default", ear_open=False):
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
            klass, said = protected_answer(question, load_config()[0], ear_open)
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
            cfg = load_config()[0]
            state = voice_state(cfg)
            # THE AUDITION PARAMETER, and it is the only reason this route takes a model
            # at all. Gated on CASTING_MODELS, so the door opens onto the three files the
            # casting panel names and nothing a page could invent - and gated on that
            # model's own readiness rather than the configured one's, because auditioning
            # Alan on a machine that has Ryan is exactly the case the panel exists to
            # show. A voice heard here is not a voice chosen: choosing is POST /voice.
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
            return self._send_wav(wav, source)

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
            gate_status, gated = self._hands_gate(question, session, ear_open)
            if gate_status is not None:
                return self._send_json(gate_status, gated)
            prefix = str(gated or "")
            # PROTECTED CLASSES 2 AND 3, above every retrieval in this server: whether the
            # ear is open, who he is, who I am, what I can do. Answered from live state and
            # the persona block, costing nothing - see protected_answer().
            klass, said = protected_answer(question, load_config()[0], ear_open)
            if klass is not None:
                # THE TRACE NAMES THE CLASS. The failure this catches is silent: a routing
                # change that quietly sends "who am i" back to the notes would still return
                # an answer, and this is the line that would stop reading "protected".
                sys.stderr.write("  route: %s - answered from state, 0 lookups: %r\n"
                                 % (klass, question.strip()[:60]))
                if prefix:
                    said["answer"] = prefix + " " + said["answer"]
                    said["handsLapsed"] = True
                return self._send_json(200, said)
            # Backstop. The viewer routes "remember that ..." to /remember itself,
            # but a stale tab must not be able to answer a capture instead of
            # performing it - the server is the real classifier either way.
            if CAPTURE_RE.match(question):
                return self._send_json(*self._capture(question))
            # Same backstop, same reason: changing brains is not asking a question,
            # and a stale tab must not be able to answer one instead of doing it.
            if is_swap_request(question):
                return self._send_json(*swap_brain(question))
            # And once more for the timer. "Thirty minutes on this" is an
            # instruction, not a question about the notes, and a tab that has not
            # been reloaded since the feature landed must not be able to have it
            # answered conversationally instead of started.
            if focus.is_focus_request(question):
                return self._send_json(*focus.handle({"say": question}))
            spent_before = lookups_so_far()
            try:
                status, payload = answer_question(question, session)
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
            return self._send_json(status, payload)

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
            try:
                status, payload = hands.execute(
                    door=door, proposal_id=str(data.get("id") or "")[:40] or None)
            except Exception as exc:                            # noqa: BLE001
                status, payload = 500, {
                    "ok": False, "kind": "tool", "nodes": [], "pending": None,
                    "error": "The tool hit an unexpected error: %s" % exc,
                    "answer": hands.LINES["failed"].format(reason=str(exc)[:160])}
            _hand_resolved(payload)
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
                elif cmd == "cancel":
                    status, payload = hands.cancel(door=door, proposal_id=ident)
                    # A no at the button door, told to the same organ the spoken no is
                    # told to. This is where "the card says plainly that tab-lock is off
                    # and why" actually happens.
                    _hand_resolved(payload)
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
                        "error": "cmd must be propose, cancel, withdraw or lapse.",
                        "answer": "", "pending": state["pending"]}
            except Exception as exc:                            # noqa: BLE001
                status, payload = 500, {
                    "ok": False, "kind": "tool", "nodes": [], "pending": None,
                    "error": "The hands hit an unexpected error: %s" % exc,
                    "answer": hands.LINES["failed"].format(reason=str(exc)[:160])}
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
            return self._send_json(200, {"ok": True, "forgotten": session,
                                         "proposalDropped": dropped})

        return self._send_json(404, {"error": "No such endpoint: %s" % route})

    def log_message(self, fmt, *args):
        sys.stderr.write("  %s\n" % (fmt % args))


def print_models():
    """python server.py --models - which Bedrock ids this account may actually use.

    Two lists, because they are invoked differently: foundation models you call by
    their own id, and inference profiles (the "us." prefixed ones) that route
    across regions. Modern Claude models are usually only reachable as a profile.
    """
    cfg = load_config()[0]
    creds, error = resolve_aws(cfg)
    if error:
        sys.exit("\n  " + error + "\n")
    host = "bedrock.%s.amazonaws.com" % creds["region"]
    print("\n  region      : %s" % creds["region"])
    print("  credentials : %s" % creds["source"])
    print("  configured  : %s\n" % model_label(cfg))

    def fetch(path, query=""):
        try:
            return aws_request(creds, "bedrock", host, path, method="GET", query=query)
        except urllib.error.HTTPError as exc:
            print("  (%s: %s)" % (path, aws_error_message(exc, "-", creds)))
        except Exception as exc:                               # noqa: BLE001
            print("  (%s: %s)" % (path, exc))
        return {}

    models = fetch("/foundation-models", "byOutputModality=TEXT")
    rows = [m for m in models.get("modelSummaries", [])
            if "ON_DEMAND" in (m.get("inferenceTypesSupported") or [])]
    print("  on-demand foundation models (%d)" % len(rows))
    for m in sorted(rows, key=lambda m: m.get("modelId", "")):
        print("    %-58s %s" % (m.get("modelId", "?"), m.get("modelName", "")))

    profiles = fetch("/inference-profiles").get("inferenceProfileSummaries", [])
    print("\n  inference profiles (%d)" % len(profiles))
    for p in sorted(profiles, key=lambda p: p.get("inferenceProfileId", "")):
        print("    %-58s %s" % (p.get("inferenceProfileId", "?"),
                                p.get("status", "")))
    print("\n  Paste one into \"bedrock_model_id\" in config.json. No restart "
          "needed.\n")


def _warm_log(line):
    """One line from the warm thread, to stderr where every other diagnostic goes."""
    sys.stderr.write("%s\n" % line)


def main():
    if not os.path.isdir(VIEWER_DIR):
        sys.exit("server.py: no viewer/ directory next to this file.")
    if "--models" in sys.argv[1:]:
        return print_models()
    load_config()
    ensure_index()

    handler = partial(GalaxyHandler, directory=VIEWER_DIR)
    httpd = ThreadingHTTPServer((HOST, PORT), handler)
    httpd.daemon_threads = True

    cfg = load_config()[0]
    creds = resolve_aws(cfg)[0] if provider_of(cfg) == "bedrock" else None
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
    print("  provider          :  %s%s" % (provider_of(cfg),
                                           "  (%s)" % creds["region"] if creds else ""))
    print("  model             :  %s" % model_label(cfg))
    print("  credentials       :  %s" % (
        creds["source"] if creds else
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

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n  shutting down")
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
