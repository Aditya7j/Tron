"""FOCUS SESSIONS - an accountability timer that watches where you actually are.

The session lives HERE, on the server, with its own one-second tick on its own
thread. That is the whole architectural point: the countdown does not belong to a
browser tab. Reload the page, close it, open a second one - the session carries on
and every tab rejoins the same one. A timer that dies with a tab is a timer you
cannot trust to hold you to anything.

WHAT IT WATCHES
    The frontmost application, re-read with a FRESH query every single tick. Never
    from a cached notification API: in a long-lived headless process those go stale
    and cheerfully report the first application they ever saw, forever, which is
    the worst possible failure here - a watchdog that is certain you are working.
    When the frontmost app is Chrome-family it also locks the active TAB, by the
    URL's HOST only. Site-level is the honest granularity for a single-page app
    whose path changes on every click; locking the full URL would report a drift
    every time you clicked a button on the very site you are supposed to be on.

WHEN IT DECIDES - and it is not at the start
    The FOCUS button lives in the Jarvis tab, so the surface in front of you at the
    click is the one surface you are guaranteed to leave. Locking it would make your
    actual work read as a drift within seconds. So the lock is DEFERRED: nothing is
    watched until you settle, and settling means the same surface, not home base, for
    SETTLE_TICKS consecutive ticks - then "Locked on, sir." out loud, so a lock on the
    wrong thing is something you hear rather than something you deduce.

    Only where you ARE can settle. The candidate always comes from a fresh foreground
    read, so a background window and a second monitor cannot be it; an ambiguous
    title join across two browser windows resolves to nothing rather than to a guess;
    and a browser whose site cannot be read while the endpoint is alive - the viewer's
    own 3D boot can stall scripting for seconds - is a reason to wait, not to lock.
    If you never leave this page at all, then after DEFER_APP_ONLY_S it watches the
    APPLICATION only and says so. A wrong tab lock is worse than no tab lock, so the
    half that could be wrong is the half that gets dropped.

MOVING IT, ON PURPOSE
    Everything above is inference, and inference is occasionally wrong - so there is
    an explicit override with no cleverness in it at all: from the surface you want,
    say "lock on this tab" (or "keep me in this tab", or "this is the tab"), or press
    the pill on the countdown card. It locks on the spot, forgives the drift you were
    in the middle of, and says "Locked on, sir."

    Said from THIS page it cannot lock - this is the page the button lives in - so it
    re-arms the deferred lock instead and says where it will be looking. Pressed on
    the CARD it never asks the window manager anything, because clicking the card is
    what put the card in front; it asks the browser which of its own tabs is visible.
    See _probe_front_window(), which is the whole of that trap and its answer.

PRIVACY, STRUCTURALLY
    Identities are compared and discarded inside the reader. TargetReader stores
    salted hashes, never names, and its only output is a verdict made of booleans.
    Everything the client can see is built by public_state() from the PUBLIC_KEYS
    whitelist, and every spoken line must come from LINE_REGISTRY - so there is no
    code path that can put an app name or a URL into the state, not by policy but
    because nothing is able to write anything else. test_focus_privacy.py proves it.

    There is exactly one string in the state that is not a canned line: `intent`,
    your own answer to "what are we focusing on?". Its only writer is
    FocusSession.set_intent(), reached only from the POST body. No reader, no probe
    and no window title has a path to it, which is why it costs the promise nothing -
    and the privacy test asserts that too, rather than taking my word for it.

SAID OUT LOUD, WRITTEN DOWN NOWHERE
    One thing is spoken that is never stored: the NAME of the place you drifted into.
    "Sir, Instagram can wait" lands where "that is not the task" does not, so the name
    is derived - inside the reader, from the host or the application, never from a
    window title - handed up as one field of one verdict, formatted into one sentence,
    and dropped. It reaches the state only as that sentence, and only until the next
    tick: _forget_names() takes the line out of the queue once it has been delivered.
    It is in no other key, in no aggregate, in the report card, or in the ledger.

    The promise is therefore not "it never names where you were" - it does, out loud,
    in the moment, which is the entire point of it. The promise is that nothing keeps
    a record: not the state, not the ledger, not the report. NAME_DRIFTS = False turns
    even the speaking off, and then no line containing a name can be reached at all -
    _emit() refuses the templates. test_focus_privacy.py proves that with a name no
    canned sentence contains, so a test that merely greps for "Instagram" cannot pass
    it by accident.
"""

import base64
import hashlib
import json
import os
import platform
import random
import re
import socket
import struct
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

# =============================================================================
#  THE KNOBS - every one of them, in one place
# =============================================================================

TICK_S = 1.0              # the server's own heartbeat; the countdown runs on this
SSE_POLL_S = 0.25         # how promptly a pushed update reaches an open tab
SSE_KEEPALIVE_S = 15.0    # a comment down the stream so proxies keep it open
SSE_REFRESH_S = 10.0      # resend a live session even when nothing was said

DEFAULT_MINUTES = 30      # "start a focus session" with no number
MIN_MINUTES = 1
MAX_MINUTES = 240
EXTEND_DEFAULT_MIN = 5    # "give me five more minutes" with no number
EXTEND_MAX_MIN = 60

DRIFT_GRACE_MS = 800      # an app or tab switch is not a drift until this passes
NAG_DEFAULT_S = 20.0      # while ONE drift persists, repeat this often
NAG_MIN_S = 5.0
NAG_MAX_S = 600.0
SNOOZE_DEFAULT_S = 15.0   # "give me fifteen seconds" - silence, not absolution
SNOOZE_MAX_S = 300.0

TIER2_AFTER_DRIFTS = 3    # the 3rd drift of a session starts speaking sharply
TIER3_AFTER_DRIFTS = 6    # the 6th stops being polite about it
MAX_TIER = 3

# NAMING THE DRIFT. One switch, and it governs everything: the reader stops deriving
# a name at all, and _emit() refuses every template with a name in it, so there is no
# path left that could speak one. Set it to False and the callouts are the nameless
# ones and nothing else changes.
#
# A named line is the only place in this module where an identity becomes a WORD, and
# it lives for one tick: it is spoken, and then _forget_names() takes the line out of
# the queue. Named out loud, written down nowhere - which is a stronger promise than
# "not named", and a much more useful one.
NAME_DRIFTS = True
LABEL_MAX_CHARS = 28    # a name, not a sentence. Longer than this and nothing is said
LABEL_LINE_TTL_S = 6.0  # how long a line that NAMES something may sit in the queue

# THE DEFERRED LOCK. The FOCUS button lives in the Jarvis tab, so the one surface
# you are guaranteed to leave is the surface in front of you at the click. Locking it
# would make your actual work read as a drift within seconds. So nothing is locked at
# the click at all: the target is whatever you SETTLE on, and settling takes two
# consecutive ticks on the same surface, so passing through a window on the way does
# not become the thing you are held to.
SETTLE_TICKS = 2          # consecutive ticks on one surface before it is the target
DEFER_APP_ONLY_S = 45.0   # never left home base: watch the application, not the site
CLEAN_RATIO = 0.85        # a session at least this clean grows the streak
MIN_LEDGER_S = 30.0       # shorter than this is a mis-tap, not a session
LEDGER_HISTORY_MAX = 50   # rows kept; the oldest falls off rather than growing forever

# THE EYES. A webcam organ in the page publishes three booleans about your body -
# present, head down, slouched - and nothing else. No frame is uploaded for this and
# there is no field on this side that could hold one: the numbers are the whole signal.
#
# The two SUSTAIN windows are applied in the page, because the page is the only thing
# that has frames. They live here anyway and are handed to it in the reply to every
# report, so the timings are stated in one file rather than drifting apart in two.
# Everything after that is decided here, where the session is: the cooldown, the relief
# valve, and whether a posture is a drift.
EYE_SUSTAIN_MS = 700       # a posture must hold this long before a word is said
EYE_ABSENCE_MS = 12000     # glancing at a notification is not leaving the desk
EYE_COOLDOWN_S = 30.0      # one nudge, then quiet, however bent you remain
# A boolean older than this is not a fact any more. It is the whole defence against a
# closed laptop lid: the page stops reporting, the last posture goes stale, and a
# session cannot be held in a drift by a tab that no longer exists.
EYE_STALE_S = 6.0
# HEAD DOWN IS A DRIFT, counted through the same machinery a tab drift is counted
# through - so the nags, the tiers, "Back. Thank you, sir.", the clean percentage, the
# snooze and the excuse all work on it without a line of new code. Off, and the eyes
# still nudge; they simply stop touching the session's books.
EYE_PHONE_DRIFTS = True
# THE RELIEF VALVE. "I need to do something important" - and every nudge stops, the
# eyes' and the session's alike. The clock keeps counting, because this is silence and
# not absolution, which is the same bargain a snooze makes.
RELIEF_S = 180.0

# THE ANSWER WINDOW. The deferred start line ends with a question, so the microphone
# opens for exactly one answer with no wake word. What you say becomes the session's
# intent. It is never read back to you at length - "Noted, sir" is the whole reply.
INTENT_WINDOW_S = 30.0        # how long the server keeps that one answer expected
INTENT_MAX_CHARS = 120        # what is kept of a long answer
INTENT_SPOKEN_MAX_CHARS = 44  # longer than this is shown but NEVER spoken back

HOME_HINT_TTL_S = 3.0     # how long a tab's "I have focus" claim stays believable
HOME_BASE_HOSTS = frozenset(("127.0.0.1", "localhost", "::1", "[::1]"))

# Chrome-family, by executable on Windows and by bundle id / app name elsewhere.
CHROME_FAMILY = frozenset((
    "chrome.exe", "msedge.exe", "brave.exe", "vivaldi.exe", "opera.exe",
    "opera_gx.exe", "chromium.exe", "thorium.exe", "arc.exe",
    "com.google.chrome", "com.microsoft.edgemac", "com.brave.browser",
    "com.vivaldi.vivaldi", "com.operasoftware.opera", "company.thebrowser.browser",
    "google chrome", "microsoft edge", "brave browser", "chromium", "vivaldi",
))

# The active tab's URL comes from the browser's own DevTools endpoint, which is the
# only way to get a real URL without an extension - and a real URL is the point,
# since hashing a window title would give per-page granularity, the exact thing
# this feature is supposed not to do. Start Chrome with:
#     chrome.exe --remote-debugging-port=9222
# With no endpoint the session degrades to app-level locking and SAYS so, rather
# than inventing a tab identity or calling an unreadable tab a drift.
CDP_PORTS = (9222, 9223, 9224)
CDP_TIMEOUT_S = 0.45

# Asking the browser's own pages which of them is in front, for the card trap below.
# This costs a WebSocket per candidate tab, so it runs ONLY on an explicit re-target -
# a click or a sentence, once - and never on the one-second tick.
CDP_EVAL_TIMEOUT_S = 0.6  # per tab; a visible tab is never a frozen tab
CDP_EVAL_MAX_TABS = 24    # a bound, so forty open tabs cannot stall a button press
CAPABILITY_TTL_S = 3.0    # capability() only; the tick itself never reads a cache
HASH_BYTES = 12           # truncated, salted, per-process: internal only, never sent

# =============================================================================
#  THE LOCK THAT LOCKS - the numbers behind the teeth
# =============================================================================
#
# The tick reads the world once a second, which is the right cadence for a countdown
# and far too slow for a tab. Measured on this machine (lookbook 18.4): the browser's
# own account of which tab is live flips 13 ms after the switch, and one question to
# one tab costs 1-2 ms on a fresh socket. So the whole of the second and a half allowed
# for noticing a drift is spent on the poll interval and the grace, and there is no
# reason for either to be generous.
#
# The grace is SERVED IN THE WATCHER rather than again in _off_target(), exactly as a
# posture drift serves its grace in the page: Ctrl+Tab through a tab on the way back to
# this one is not a drift, and charging the same patience twice would put the callout
# the wrong side of the second and a half.
LOCK_POLL_S = 0.30        # how often the locked tab is asked whether it is still live
LOCK_GRACE_MS = 400       # passing through a tab is not leaving for one
LOCK_TITLE_CHARS = 24     # what the card may show of the locked tab's title
SUMMON_WITHIN_S = 30.0    # a second drift this soon after the first is a pull
LOCK_ACTIVATE_S = 1.2     # how long an activation is given to actually take effect

# WHY TAB-LEVEL LOCKING IS OFF, when it is - one word out of a fixed set, never a
# sentence. The card turns it into prose; it stays a word here so that no call site can
# put an explanation somebody wrote at two in the morning onto the wire.
#
#   ""          nothing to report: either a tab is locked, or none was asked for
#   noport      Chrome has no --remote-debugging-port, and the hand has been offered
#   declined    it was offered and you said no. The card says so and stops asking
#   ambiguous   two windows both claim the front tab, or the browser's answer and the
#               reader's target are not the same surface
#   unreadable  nothing in front could be read as a page at all
#   gone        the locked tab was closed, or navigated out from under the lock
TAB_LOCK_WHY = ("", "noport", "declined", "ambiguous", "unreadable", "gone")

LEDGER_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "focus-ledger.json")

# =============================================================================
#  WHAT IT SAYS - the only text that may ever leave this module
# =============================================================================
#
# _say() refuses any template that is not in LINE_REGISTRY, built at the bottom of
# this block. That is the structural half of the privacy promise: a future edit
# cannot slip an f-string of window titles into the spoken queue, because there is
# no function that will accept one.

LINES = {
    # The deferred start. It has to say BOTH things: that nothing is being watched
    # yet, and what happens next - a deferred lock nobody mentions is the same as a
    # broken one, because the silence is indistinguishable from a lock on the wrong
    # thing. The second sentence is a question, and the answer window opens on it.
    "arming": "{minutes} minutes, sir. Go to what you're working on and I'll lock on "
              "there. And what are we focusing on?",
    # The same start line, for the machine that cannot take a tab-level lock at all:
    # Chrome without --remote-debugging-port. One clause, inserted before the
    # question, because the question has to stay last - the client opens the
    # microphone on hearing it, and a sentence after it would be a sentence spoken
    # into an open microphone. Said ONCE, at the start, and never per tick: the
    # honesty belongs to the moment you commit to the session, and a caveat repeated
    # every three seconds is a caveat you stop hearing. THE LAW: the session never
    # silently downgrades. Silence about a missing lock is a wrong lock in a costume.
    "arming_app_only": "{minutes} minutes, sir. Go to what you're working on and I'll "
                       "lock on there. Tab-level locking is unavailable, sir - Chrome "
                       "was not launched with the DevTools port, so I shall watch the "
                       "application only. And what are we focusing on?",
    "locked": "Locked on. {minutes} minutes. I am watching, sir.",
    "locked_tab": "Locked on, site and all. {minutes} minutes. I am watching, sir.",
    # Deliberately four words. It is the audible half of the deferred lock: it fires
    # the moment the target is decided, so a lock on the WRONG surface is something
    # you hear at the moment it happens rather than discover at the first callout.
    "settled": "Locked on, sir.",
    "settled_app_only": "You have not left this page in {seconds} seconds, sir, so I "
                        "shall watch the application and not the site.",
    # The explicit re-target, said from the one surface it cannot lock: this page.
    # It promises the deferred lock all over again, in the words the start line used,
    # because "I have not done what you asked" is only acceptable when it is followed
    # by what will happen instead. Not a refusal - a re-arm.
    "retarget_armed": "Go to it, sir. I'll lock on where you land.",
    "notab": "I can see which application you are in, sir, but not which site. "
             "Application only, then.",
    "intent_noted": "Noted, sir.",

    # -- THE LOCK THAT LOCKS ----------------------------------------------------
    # The no-port path. What the SESSION says around the hand's offer: the sentence
    # before it, and the sentence when it is declined. Both of them commit out loud to
    # watching the application instead, because the whole law of this part is that the
    # feature never keeps the word "locked" after quietly losing the meaning of it.
    "lock_noport": "I cannot lock a tab, sir - Chrome has no debugging port open.",
    "lock_declined": "Tab-level locking is off, then, sir: no debugging port, and you "
                     "would rather I did not restart the browser. I shall watch the "
                     "application only.",
    # The tab went away under the lock. Said once, and it degrades honestly rather
    # than going on reporting a tab that no longer exists.
    "lock_gone": "The tab you locked has gone, sir. I am watching the application only.",
    # THE TWO GATED OFFERS. These are the registry's own proposal sentences, held here
    # a second time, and the duplication is deliberate: _emit() refuses any template
    # that is not in LINE_REGISTRY, which is the structural half of the privacy promise
    # and is not worth weakening so that a question can be phrased elsewhere. So the
    # gate holds the real pending proposal and this file speaks its own registered copy
    # of the words - and preflight check 19 asserts the two copies are identical, so the
    # pair cannot drift apart in silence.
    "ask_relaunch": "I need Chrome relaunched with the debugging port to lock a tab, "
                    "sir. Shall I?",
    "ask_summon": "Shall I bring you back?",
    # The summon itself, and its two failures are as plainly said as its success: a
    # summon that silently did nothing would be the worst sort of hand, because the one
    # thing the boss can check for himself is whether his screen changed.
    "summoned": "Here you are, sir - back where you said you would be.",
    "summon_none": "There is no locked tab to bring you back to, sir.",
    "summon_failed": "The tab would not come forward, sir, so you are still where you "
                     "were.",
    "unreadable": "I cannot see your windows at all, sir, so I shall keep time and "
                  "take your word for the rest.",
    "back": "Back. Thank you, sir.",
    "back_long": "Back at last, sir. That was {seconds} seconds.",
    "paused": "Paused, sir. The clock waits and so do I.",
    "resumed": "Resumed. {remaining} left, sir.",
    "extended": "{minutes} more minutes, sir. {remaining} on the clock.",
    "snoozed": "{seconds} seconds of silence, sir. The clock is still counting it.",
    "excused": "Research. Of course, sir. That excursion is off the books.",
    "excused_ontarget": "Nothing to excuse at present, sir. You are where you said "
                        "you would be.",
    "nag_set": "Every {seconds} seconds, then, sir.",
    "drill_on": "Very good, sir. No quarter.",
    "drill_off": "As you wish, sir. I shall go back to being civil about it.",
    "aborted": "Abandoned, sir. Nothing recorded.",
    "none": "There is no session running, sir.",
    "unknown": "I did not catch that as an instruction about the session, sir.",
    "already": "There is already a session running, sir. {remaining} left.",
    "status": "{remaining} left, sir. {ontarget} on target, {drifts}.",
    "report": "Time, sir. {ontarget} on target out of {planned} planned, "
              "{drifts}. {clean} percent clean. {streak}",
    # The same card, with your own words for the work in it. Only ever used when the
    # intent is short enough to be a phrase rather than a dictation - see
    # spoken_intent(): a long answer is kept and shown, never recited.
    # "On {intent}," rather than "{intent}:" so your own words are never the first
    # thing after a full stop - dictation arrives in lower case, and "Time, sir. the
    # invoice importer: ..." sounds like a transcription error read aloud.
    "report_intent": "Time, sir. On {intent}, {ontarget} on target out of {planned} "
                     "planned, {drifts}. {clean} percent clean. {streak}",
    "streak_up": "That extends your streak to {streak}.",
    "streak_new": "That starts a streak.",
    "streak_broken": "Your streak ends at {streak}.",
    "streak_none": "No streak yet.",
    # THE EYES, switched on and off. The first line is a promise and it is the true
    # one: what leaves the browser is three booleans, and the camera's frames are read
    # in the page and thrown away there.
    "eyes_on": "Eyes open, sir. Posture only - no picture of you leaves this machine.",
    "eyes_off": "Eyes closed, sir.",
    "eyes_blind": "The camera has stopped, sir, so my eyes are shut again.",
    # THE EAR LAW, and the reason it is a LINE rather than a comment: an organ may
    # open the conversation and it may never open the microphone. The eyes coming on
    # while the ears are off is exactly the moment that rule is felt as a fault, so it
    # is said out loud instead of being silently correct.
    "ears_off": "My ears are off, sir - tap the ear button and just talk.",
    # THE RELIEF VALVE. It says what it costs, because the clock does keep running.
    "relief": "{span} of silence, sir. Go and do the important thing.",
}

# Three tiers, and the difference between them is not volume, it is how much
# benefit of the doubt is left.
CALLOUTS = {
    1: (
        "That is not the task, sir.",
        "A detour, sir?",
        "Ah. Somewhere else entirely.",
        "You did say you would be working on something specific.",
        "Not the thing, sir.",
    ),
    2: (
        "That is drift number {drifts}, sir, and I am keeping count.",
        "Twice more and I stop being polite about it, sir.",
        "You asked me to hold you to this. I am holding you to it.",
        "Sir. The work is elsewhere.",
        "This is becoming a habit within the half hour, sir.",
    ),
    3: (
        "{drifts} drifts, sir. At this point I am simply narrating.",
        "We are well past the point where I pretend not to notice, sir.",
        "You are paying for this session in minutes, sir, and spending them here.",
        "I could stop the clock and we could both go home, sir.",
        "Sir.",
    ),
}

# THE LOCKED TAB'S OWN POOL. Reached only when the WATCHER caught the drift - the
# browser's own account of which of its tabs is live - which is precisely the drift no
# window reader can see: same machine, same application, same window, wrong tab.
#
# Tier one is the mandate's sentence, word for word. Note what none of these lines
# contain: a {label}. The named pools exist because "that is not the invoice importer"
# is a sharper callout than "that is not the task" - but here the sharpness is already
# in the fact, and the fact is about the tab you PROMISED rather than the one you
# wandered to. So this pool says where you should be and stays silent about where you
# are, which is both the better sentence and the smaller claim. It is therefore not in
# _NAMED_POOLS and needs no scrubbing: there is nothing in it to scrub.
CALLOUTS_LOCKED = {
    1: (
        "You have left the locked tab, sir - drift {drifts}.",
        "That is not the locked tab, sir.",
        "The tab you asked me to hold you to is still open, sir. This is not it.",
        "Off the locked tab, sir.",
    ),
    2: (
        "Off the locked tab again, sir - that is drift {drifts}.",
        "Drift {drifts}, sir, and not one of them in the tab you named.",
        "You locked a tab, sir. We are not in it.",
        "Sir. The locked tab is one keystroke away.",
    ),
    3: (
        "{drifts} drifts off a tab you locked yourself, sir.",
        "I am watching one tab, sir, and you are in all the others.",
        "The lock is doing its half, sir.",
        "Sir.",
    ),
}

# The FIRST callout of a session, when you told me what you were sitting down to do.
# Your own words are the sharpest thing available and they cost nothing to use, so the
# opening callout uses them - once. After that the ordinary pools take over, because a
# line that repeats your own sentence at you five times stops being a callout and
# starts being a parrot. {intent} is only ever the text YOU dictated; no reader on
# this machine can write to it.
#
# Every one of these keeps {intent} away from the start of a sentence, for the same
# reason report_intent does: dictation comes back in lower case and your own words
# should not be the thing that sounds wrong.
CALLOUTS_INTENT = (
    "That is not {intent}, sir.",
    "The plan was {intent}, sir.",
    "You said {intent}. This is not that.",
    "Was it not {intent}, sir?",
)

# THE SAME THREE TIERS, WITH THE PLACE IN THEM.
#
# FOUR lines per tier and not three, because a single excursion at tier three can
# outlast a pool: three phrases in rotation stop being a callout by the second lap and
# start being a ringtone. {label} is the derived name and it is never stored - see
# spoken_surface() above and _forget_names() below.
#
# {times} and {nth} are the drift count in words ("twice", "third"), because "drift
# number 3 in YouTube" is a log entry read aloud and "third time in YouTube" is a
# sentence. The _cap spellings exist so the count can open a line without the cheap
# trick of capitalising a formatted value at the last moment.
CALLOUTS_NAMED = {
    1: (
        "Sir, {label} can wait.",
        "{label}, sir. That is not the task.",
        "Ah. {label}.",
        "That is {label}, sir, and it is not the work.",
    ),
    2: (
        "{times_cap} into {label}, sir. It is starting to look deliberate.",
        "{label} again, sir. Drift number {drifts}, and I am keeping count.",
        "You keep arriving in {label}, sir. I keep noticing.",
        "{label}, sir. Twice more and I stop being polite about it.",
    ),
    3: (
        "{nth_cap} time in {label}, sir. The detours are becoming the project.",
        "{drifts} drifts, sir, and {label} has had the better part of them.",
        "{label}, for the {nth} time. I am simply narrating now, sir.",
        "You are paying for this session in minutes, sir, and spending them in "
        "{label}.",
    ),
}

# The opening callout, when you told me the work AND the place can be named. It is the
# sharpest line the whole feature has - your own sentence and the thing that is not it,
# in the same breath - so it is spent once and never repeated.
CALLOUTS_INTENT_NAMED = (
    "Sir - {label} does not look like '{intent}' to me.",
    "You said {intent}, sir. This is {label}.",
    "The plan was {intent}. This is {label}, sir.",
    "{label} is not {intent}, sir.",
)

# DRILL SERGEANT, for the days you ask for it. No tiers in here: you asked for the top
# of the register, so there is nowhere left to escalate to. Still the butler, simply
# done softening it - a Jarvis that swears at you is a Jarvis you switch off, and a
# switched-off Jarvis holds you to nothing at all.
CALLOUTS_DRILL = (
    "No. Back to work, sir.",
    "That is a choice you are making, sir. Unmake it.",
    "Wrong window. Correct it.",
    "You asked me not to be gentle about this, sir. Go back.",
)
CALLOUTS_DRILL_NAMED = (
    "{label}. No, sir. Back to work.",
    "Out of {label}, sir. Now.",
    "{label} is not on the list, sir. Close it.",
    "Drift {drifts}, sir, and it is {label} again. Go back.",
)

# The follow-up while a single excursion drags on. Shorter, because by now you know.
# Nameless on purpose, even with naming on: the callout thirty seconds ago already
# said where you are, and a nag that repeats the name every twenty seconds turns the
# one thing this feature refuses to log into the thing it says most often.
NAGS = {
    1: ("Still not the task, sir.", "Any moment now, sir.", "Sir?"),
    2: ("{seconds} seconds off task, sir.", "Still elsewhere, sir.",
        "The work has not moved, sir."),
    3: ("{seconds} seconds, sir.", "I am still here, sir. So is the work.",
        "Sir."),
}

# THE PHONE POSTURE - the eyes' own line pool, and it is a CALLOUT pool because a
# sustained head-down is counted as a drift like any other. Three tiers, four lines
# each, for the same reason the named pools have four: one excursion at tier three can
# outlast a shorter pool, and a callout on its second lap is a ringtone.
#
# Nameless, and structurally so: no pool the eyes can reach is in NAMED_LINES, so there
# is no path by which a posture nudge could name a site or an application. It also says
# nothing about WHAT is in your hand. The camera saw a head go down; "the phone" is an
# inference, and the lines that make it are allowed to sound like one.
CALLOUTS_PHONE = {
    1: (
        "Head down, sir. That is not the work.",
        "Whatever is in your lap, sir, it is not the task.",
        "Looking down, sir? The work is up here.",
        "Ah. The lap.",
    ),
    2: (
        "Head down again, sir. Drift number {drifts}, and I am keeping count.",
        "{times_cap} into your lap, sir. It is starting to look deliberate.",
        "Whatever is down there is winning, sir. Twice more and I stop being polite "
        "about it.",
        "You keep looking down, sir. I keep noticing.",
    ),
    3: (
        "{nth_cap} time with your head down, sir. The detours are becoming the "
        "project.",
        "{drifts} drifts, sir, and your lap has had the better part of them.",
        "Head down for the {nth} time. I am simply narrating now, sir.",
        "Sir. Head up.",
    ),
}
CALLOUTS_PHONE_DRILL = (
    "Head up. Whatever that is, put it down, sir.",
    "Out of your lap, sir. Now.",
    "That is not the work, sir. Eyes forward.",
    "Drift {drifts}, sir, and your head is still down. Up.",
)

# SLOUCH and ABSENCE are nudges and nothing more: no drift, no count, no mark on the
# report card. A posture is not a decision about the work, and a watchdog that spent
# your clean percentage on your spine would be measuring the wrong thing.
#
# Both pools are deliberately free of every {field}: they are said with no session in
# sight, by spoken_line(), which has no drift count to offer them.
NUDGES_SLOUCH = (
    "You are folding, sir. Sit up.",
    "Your spine, sir. It was straighter an hour ago.",
    "Shoulders, sir.",
    "Sit up, sir. You will thank me at fifty.",
)
NUDGES_ABSENT = (
    "Gone, sir? The clock has not gone anywhere.",
    "I appear to be watching an empty chair, sir.",
    "The desk is unattended, sir, and the work is not finished.",
    "Still here, sir. Are you?",
)

_NAMED_POOLS = ([CALLOUTS_INTENT_NAMED, CALLOUTS_DRILL_NAMED]
                + list(CALLOUTS_NAMED.values()))

# Every pool the EYES may draw from, and the reason it is a list rather than a comment:
# test_eyes.py walks it and asserts that not one line in it contains {label}, so the
# promise "an organ that watches your body never names a place" is checked rather than
# remembered.
EYE_POOLS = ([CALLOUTS_PHONE_DRILL, NUDGES_SLOUCH, NUDGES_ABSENT]
             + list(CALLOUTS_PHONE.values()))

LINE_REGISTRY = frozenset(list(LINES.values())
                          + [t for pool in CALLOUTS_LOCKED.values() for t in pool]
                          + list(CALLOUTS_INTENT)
                          + list(CALLOUTS_DRILL)
                          + [t for pool in CALLOUTS.values() for t in pool]
                          + [t for pool in NAGS.values() for t in pool]
                          + [t for pool in EYE_POOLS for t in pool]
                          + [t for pool in _NAMED_POOLS for t in pool])

# The named half of the registry, kept separately because _emit() has to be able to
# tell a line that will contain a name from one that cannot - it refuses the first
# kind outright when naming is switched off, and marks it for scrubbing when it is on.
NAMED_LINES = frozenset(t for pool in _NAMED_POOLS for t in pool)

# Numbers as a butler says them. Past the table it degrades to digits, which is the
# right failure: "the fourteenth time" is a sermon, "the 14th time" is a fact.
_TIMES_WORDS = ("no times", "once", "twice", "three times", "four times",
                "five times", "six times", "seven times", "eight times",
                "nine times", "ten times")
_NTH_WORDS = ("", "first", "second", "third", "fourth", "fifth", "sixth",
              "seventh", "eighth", "ninth", "tenth")


def _times_word(count):
    count = max(0, int(count))
    if count < len(_TIMES_WORDS):
        return _TIMES_WORDS[count]
    return "%d times" % count


def _nth_word(count):
    count = max(1, int(count))
    if count < len(_NTH_WORDS):
        return _NTH_WORDS[count]
    if 10 <= count % 100 <= 20:
        return "%dth" % count
    return "%d%s" % (count, {1: "st", 2: "nd", 3: "rd"}.get(count % 10, "th"))

# =============================================================================
#  WHAT THE CLIENT MAY SEE - the whitelist, and nothing outside it
# =============================================================================
#
# public_state() copies these keys and no others, coercing each to its declared
# type. Nothing about WHERE you were can survive the trip: there is no key here
# that could hold it, and a value of the wrong type is dropped rather than passed
# through. test_focus_privacy.py asserts the key set matches this exactly, so
# adding a key here without thinking about it fails a test.

STATES = ("idle", "arming", "running", "paused", "ended")
END_REASONS = ("finished", "ended-early", "aborted", None)
# "ask" is a note with a Yes and a No behind it: a line the session speaks while a
# proposal is pending at the hands gate, which the client paints as a proposal card
# rather than as prose. It is a kind and not a new channel on purpose - it travels in
# the same say queue, through the same _emit(), under the same registry.
SAY_KINDS = ("callout", "nag", "note", "report", "nudge", "ask")

PUBLIC_KEYS = {
    "state": str, "plannedS": int, "elapsedS": int, "remainingS": int,
    # Five buckets, and they do not all count the same way. onTarget and drift are
    # the only two that decide whether a session was clean; home (talking to me),
    # excused (you said it was research) and unknown (I could not see) are kept
    # separately rather than being rounded into whichever total flatters the number.
    "onTargetS": int, "driftS": int, "homeS": int, "excusedS": int, "unknownS": int,
    "drifts": int, "tier": int,
    "onTarget": bool, "drifting": bool, "inGrace": bool, "atHome": bool,
    "excused": bool, "snoozed": bool, "snoozeLeftS": int, "nagS": int,
    # The register you asked for. A boolean about HOW you are spoken to, which is why
    # it is allowed out here: it says nothing whatever about where you have been.
    "drill": bool,
    "appWatched": bool, "tabWatched": bool, "readable": bool, "locked": bool,
    # DEFERRED is the honest name for "nothing is being watched yet". It is exposed
    # rather than inferred from state == "arming" because the status line and the
    # debug panel both have to be able to say so out loud, and a caller should not
    # have to know that one of the five state words happens to imply it.
    "deferred": bool, "awaitingIntent": bool,
    # The ONE string here that is not an observation. It is what you dictated into
    # the answer window, and the only writer is FocusSession.set_intent(), reached
    # only from the POST body. No reader, no probe and no window title can put a
    # character in it - which is why adding it costs the privacy promise nothing.
    "intent": str,
    "cleanPct": int, "streak": int, "bestStreak": int, "sessions": int,
    "endedReason": str, "report": str, "seq": int, "say": list,
    # THE EYES. Three booleans about your body, two about the organ, one count - and
    # they are allowed out here for the same reason the rest of this list is: there is
    # no key below that could hold a frame, a landmark, a face or a measurement, and a
    # boolean saying your head is down says nothing whatever about what it is down at.
    # This IS the signal: what the camera produced was read in the browser, reduced to
    # these, and thrown away there.
    #
    # eyesOn is the organ AND its freshness in one word: a tab that stopped reporting
    # six seconds ago is reported as eyes closed, because a stale boolean is not a fact.
    "eyesOn": bool, "present": bool, "headDown": bool, "slouched": bool,
    # Whether the drift in progress is a posture one, so the card can say "head down"
    # instead of implying you are in the wrong window. Nameless either way.
    "postureDrift": bool,
    "hushed": bool, "hushLeftS": int, "nudges": int,
    # THE LOCKED TAB. This is the second string in this whitelist that came from an
    # observation, so it gets the same treatment the first one got - stated, bounded,
    # and justified rather than dropped in.
    #
    # lockedTab is up to LOCK_TITLE_CHARS characters of the title of the tab actually
    # being watched, stripped to a label's character set. It is here because the card
    # was asked to say WHICH tab it is holding you to, and a card that says LOCKED
    # without saying to what is the same card that used to say it while watching the
    # whole browser. It is written only when a tab lock is really taken - by the
    # deferred settle on a surface you stayed on, or by an explicit re-target - and it
    # is cleared by unlock, re-target, abort and finish. It is absent from the ledger
    # (SESSION_ROW_KEYS is unchanged), absent from the instrument, absent from every
    # spoken line, and never written to disk.
    #
    # tabLockWhy is one word out of TAB_LOCK_WHY - never a sentence, so no call site can
    # invent an explanation - and the card turns it into prose. It is how "no silent
    # degradation" is kept on the screen as well as out loud.
    "lockedTab": str, "tabLockWhy": str,
}


# =============================================================================
#  THE INSTRUMENT - what /focus/diag may say, which is booleans and statuses
# =============================================================================
#
# This exists because "it isn't working" is not a bug report and guessing is not
# debugging. Every question you would otherwise ask by adding a print statement is
# answered here, from the RUNNING process, and answered in a form that cannot name
# anything: a boolean, a small integer, or one word out of a fixed set.
#
# The rule is the same as PUBLIC_KEYS and it is enforced the same way - a copy
# through this whitelist with a type coercion, so a key that is not declared here
# cannot reach the wire even if somebody builds a dict with it in.
#
# Note what is a STATUS rather than a boolean: a lane is "on", "off", "unknown" or
# "n/a", because "am I on the right tab" has four honest answers and three of them
# are not "no". Collapsing "I could not read the tab" into False is how a watchdog
# ends up accusing you of drifting while blind.

TAB_READS = ("unknown",      # nothing readable in front at all
             "notbrowser",   # the front app is not a Chrome-family browser
             "read",         # a site was read out of the front tab
             "ambiguous",    # the endpoint is alive but two windows both claim front
             "noendpoint")   # a browser, with no --remote-debugging-port to ask
LANES = ("on", "off", "unknown", "n/a")
# What the TAB WATCHER is doing, for the instrument. "n/a" means there is no watcher at
# all, which is the ordinary answer on a machine with no debugging port and the asserted
# answer after an unlock - see lock_proof.mjs, which ends by reading watchers back to
# zero and watchPolls frozen.
WATCH_STATES = ("n/a", "on", "off", "gone")

DIAG_KEYS = {
    # THE PROCESS. First, and not by accident: a fresh interpreter passes every
    # check in this file while the long-lived one sits frozen on a stale config or a
    # dead tick thread. pid and uptimeS are how you tell which one answered you, and
    # tickAgeS is the freeze itself - one second is healthy, forty is the bug.
    "pid": int, "uptimeS": int, "tickAlive": bool, "tickAgeS": int, "ticks": int,
    "version": int,
    # THE FOREGROUND, from one fresh read taken while answering this request. No
    # cache: a diagnostic that tells you what was true three seconds ago is a
    # second bug rather than a tool for finding the first.
    "appReadable": bool, "frontIsBrowser": bool, "tabRead": str,
    # Is the front tab THIS page. The one surface a target must never be, and the
    # usual answer to "why won't it lock on" - you are still looking at me.
    "frontIsHome": bool,
    "cdpAlive": bool, "backend": str,
    # THE LOCK. appHash/tabHash are "is there a hash in the slot", never the hash:
    # twelve salted bytes are not an identity but they are not a diagnostic either,
    # so what crosses the wire is that a slot is filled.
    "sessionOn": bool, "state": str, "deferred": bool, "locked": bool,
    "appHash": bool, "tabHash": bool, "appTarget": bool, "tabTarget": bool,
    "candidate": bool, "settleTicks": int, "settleNeeded": int, "armingS": int,
    # ON TARGET, BY LANE, because "not on target" is four different faults.
    # readerOnTarget is a fresh read; sessionOnTarget is what the tick last decided.
    # If those two disagree the tick is stale, which is the whole reason both are here.
    "appLane": str, "tabLane": str, "postureLane": str,
    "readerOnTarget": bool, "sessionOnTarget": bool, "atHome": bool,
    "drifting": bool, "inGrace": bool, "excused": bool, "snoozed": bool,
    "intentOpen": bool, "eyesOn": bool,
    # THE TAB WATCHER, which is the one organ in this file that holds a plaintext
    # handle on a tab - so the instrument reports only that it exists, what it last
    # decided, and how many questions it has asked. watchers is the leak detector: a
    # session that ended with a watcher still in it is a watcher still polling a tab.
    "watchers": int, "watchPolls": int, "watchState": str,
}


# =============================================================================
#  READING THE FRONTMOST WINDOW - fresh, every tick, no cache anywhere
# =============================================================================

def _host_of(url):
    """The HOST of a URL and nothing else. Deliberately lossy: the path is what
    changes on every click of a single-page app, so the path is thrown away here
    rather than being allowed to cause a false drift downstream."""
    try:
        host = urllib.parse.urlsplit(str(url)).hostname
    except Exception:                                          # noqa: BLE001
        return None
    return (host or "").lower() or None


# =============================================================================
#  THE SPOKEN NAME - one identity, one sentence, one tick
# =============================================================================
#
# Everything else in this module turns an identity into a hash or a boolean. This
# turns one into a WORD, which is a deliberate hole in an otherwise solid wall, so it
# is drilled as narrowly as it can be:
#
#   * the only caller is TargetReader.look(), and only when the verdict already says
#     readable, not home base, not the target - a drift, about to be spoken about;
#   * the input is the reader's OWN identity string: an exe basename, a bundle id, a
#     hostname. Never a window title. A title is the document you have open, which is
#     exactly the granularity this feature exists not to have;
#   * a host becomes a site name or a bare domain. The path is already gone, thrown
#     away by _host_of() long before here, so no page can be named;
#   * nothing keeps it. A local in look(), a local in tick(), a field in one sentence,
#     then gone - see FocusSession._forget_names().
#
# None is always an acceptable answer: every named pool has a nameless twin, so a
# surface that cannot be named politely just gets the old line.

# The big ones get a proper name, because "instagram.com can wait" sounds like a
# solicitor talking. Longest suffix wins, so mail.google.com is Gmail while
# docs.google.com is merely google.com.
SITE_LABELS = (
    ("mail.google.com", "Gmail"),
    ("news.ycombinator.com", "Hacker News"),
    ("instagram.com", "Instagram"),
    ("youtube.com", "YouTube"),
    ("youtu.be", "YouTube"),
    ("reddit.com", "Reddit"),
    ("tiktok.com", "TikTok"),
    ("netflix.com", "Netflix"),
    ("twitter.com", "X"),
    ("x.com", "X"),
    ("facebook.com", "Facebook"),
    ("linkedin.com", "LinkedIn"),
    ("twitch.tv", "Twitch"),
    ("whatsapp.com", "WhatsApp"),
    ("discord.com", "Discord"),
)

# Applications, by the same string the reader compares: an exe basename on Windows,
# a bundle id or app name elsewhere. Unmapped names are title-cased instead, which is
# occasionally clumsy - "Msedgewebview2" - and clumsy is fine. Wrong is not.
APP_LABELS = {
    "chrome": "Chrome", "msedge": "Edge", "brave": "Brave", "firefox": "Firefox",
    "vivaldi": "Vivaldi", "opera": "Opera", "opera_gx": "Opera", "arc": "Arc",
    "safari": "Safari", "chromium": "Chromium", "thorium": "Thorium",
    "slack": "Slack", "slackmacgap": "Slack", "discord": "Discord",
    "teams": "Teams", "ms-teams": "Teams", "telegram": "Telegram",
    "whatsapp": "WhatsApp", "signal": "Signal", "zoom": "Zoom", "skype": "Skype",
    "spotify": "Spotify", "steam": "Steam", "epicgameslauncher": "Epic Games",
    "vlc": "VLC", "obs64": "OBS", "obs": "OBS", "mpv": "mpv",
    "code": "VS Code", "devenv": "Visual Studio", "idea64": "IntelliJ",
    "pycharm64": "PyCharm", "webstorm64": "WebStorm", "sublime_text": "Sublime Text",
    "notepad": "Notepad", "notepad++": "Notepad++", "windowsterminal": "Terminal",
    "wt": "Terminal", "powershell": "PowerShell", "pwsh": "PowerShell",
    "cmd": "Command Prompt", "conhost": "Console", "explorer": "File Explorer",
    "outlook": "Outlook", "excel": "Excel", "winword": "Word",
    "powerpnt": "PowerPoint", "onenote": "OneNote", "acrord32": "Acrobat",
    "acrobat": "Acrobat", "figma": "Figma", "notion": "Notion",
    "photoshop": "Photoshop", "illustrator": "Illustrator", "blender": "Blender",
    "unity": "Unity", "godot": "Godot", "finder": "Finder", "messages": "Messages",
    "mail": "Mail", "music": "Music", "terminal": "Terminal",
}

# Two-part suffixes, so news.bbc.co.uk reads "bbc.co.uk" rather than "co.uk". Not a
# complete public suffix list and it does not need to be: getting this wrong names a
# site slightly oddly, which is a cosmetic fault and not a private one.
_PUBLIC_SUFFIX_2 = frozenset((
    "co.uk", "org.uk", "ac.uk", "gov.uk", "me.uk", "co.jp", "or.jp", "ne.jp",
    "co.kr", "co.nz", "co.za", "co.in", "co.il", "com.au", "com.br", "com.cn",
    "com.mx", "com.tr", "com.sg", "com.hk", "com.tw",
))

# What a name may be MADE of. A whitelist, so a string full of punctuation cannot
# arrive in a spoken sentence; anything outside it is dropped, and if what survives
# is not word-shaped then nothing is said at all.
_LABEL_CLEAN_RE = re.compile(r"[^A-Za-z0-9 .+&'-]+")
_LABEL_WORD_RE = re.compile(r"[A-Za-z0-9]")


def _clean_label(text):
    """A short speakable name, or None."""
    name = _LABEL_CLEAN_RE.sub(" ", str(text or ""))
    name = " ".join(name.split())[:LABEL_MAX_CHARS].strip(" .-'&+")
    if not name or not _LABEL_WORD_RE.search(name):
        return None
    return name


def bare_domain(host):
    """example.com out of www.example.com; bbc.co.uk out of news.bbc.co.uk."""
    parts = [p for p in str(host or "").lower().split(".") if p]
    if len(parts) < 2:
        return ".".join(parts)
    tail = ".".join(parts[-2:])
    if tail in _PUBLIC_SUFFIX_2 and len(parts) >= 3:
        tail = ".".join(parts[-3:])
    return tail


def site_label(host):
    """The spoken name of a site. None for home base: this page is never a drift."""
    name = str(host or "").strip().strip(".").lower()
    if not name or name in HOME_BASE_HOSTS:
        return None
    for suffix, spoken in SITE_LABELS:
        if name == suffix or name.endswith("." + suffix):
            return spoken
    return _clean_label(bare_domain(name))


def app_label(app):
    """The spoken name of an application.

    "slack.exe" and "com.tinyspeck.slackmacgap" both have to come out as Slack, so a
    bundle id is reduced to its last component before the map is consulted a second
    time and the title-cased fallback takes over.
    """
    name = str(app or "").strip().lower()
    if not name:
        return None
    if name.endswith(".exe"):
        name = name[:-4]
    mapped = APP_LABELS.get(name)
    if mapped:
        return mapped
    if name.count(".") >= 2:                       # com.tinyspeck.slackmacgap
        name = name.rsplit(".", 1)[-1]
        mapped = APP_LABELS.get(name)
        if mapped:
            return mapped
    return _clean_label(name.replace("_", " ").replace("-", " ").title())


def spoken_surface(app, host):
    """The name for the surface in front of you, or None if it should not be named.

    A browser with a readable site is named by the site. A browser whose site cannot
    be read is named by the BROWSER, which is honest about what is actually known and
    says nothing about which page is open in it.
    """
    if not NAME_DRIFTS:
        return None
    if host:
        return site_label(host)
    return app_label(app)


def _cdp_active_host(window_title):
    """(host, endpoint_alive). Joins the OS's idea of the foreground window to the
    browser's idea of its tabs by title, because Chrome's window title IS its
    active tab's title. A fresh HTTP call every tick; nothing is remembered."""
    title = (window_title or "").strip()
    alive = False
    for port in CDP_PORTS:
        try:
            with urllib.request.urlopen("http://127.0.0.1:%d/json" % port,
                                        timeout=CDP_TIMEOUT_S) as res:
                targets = json.loads(res.read().decode("utf-8", "replace"))
        except Exception:                                      # noqa: BLE001
            continue
        alive = True
        if not isinstance(targets, list):
            continue
        pages = [t for t in targets
                 if isinstance(t, dict) and t.get("type") == "page" and t.get("url")]
        hits = set()
        for t in pages:
            page_title = (t.get("title") or "").strip()
            if page_title and (title == page_title or title.startswith(page_title)):
                hits.add(_host_of(t.get("url")))
        # AMBIGUITY IS NOT AN ANSWER. With three browser windows open, two of them can
        # easily hold tabs with the same title - two blank tabs, or the same site open
        # twice - and the title is the only join available. Taking the first match
        # would be guessing which window is in front, and a guess here locks a tab you
        # never looked at. One unambiguous host, or nothing.
        if len(hits) == 1:
            return hits.pop(), True
        # The endpoint answered but nothing matched, or too much did: an unmatched tab
        # is unknown, not "somewhere else". Saying otherwise would invent a drift.
        return None, True
    return None, alive


def _read_windows():
    """Foreground app + window title via three Win32 calls. This IS the fresh
    query: GetForegroundWindow is a syscall that answers about now, with nothing
    between us and the window manager that could hold a stale answer.

    Windows has no bundle ids, so the process's own image name is the honest
    equivalent - it is what the OS considers the application's identity."""
    import ctypes
    from ctypes import wintypes

    user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
    user32.GetForegroundWindow.restype = wintypes.HWND
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return None

    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND,
                                                ctypes.POINTER(wintypes.DWORD)]
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if not pid.value:
        return None

    app = None
    kernel32.OpenProcess.restype = wintypes.HANDLE
    handle = kernel32.OpenProcess(0x1000, False, pid.value)   # QUERY_LIMITED_INFO
    if handle:
        try:
            buf = ctypes.create_unicode_buffer(1024)
            size = wintypes.DWORD(1024)
            kernel32.QueryFullProcessImageNameW.argtypes = [
                wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
                ctypes.POINTER(wintypes.DWORD)]
            if kernel32.QueryFullProcessImageNameW(handle, 0, buf,
                                                   ctypes.byref(size)):
                app = os.path.basename(buf.value).lower()
        finally:
            kernel32.CloseHandle(handle)

    length = user32.GetWindowTextLengthW(hwnd)
    title = ""
    if length:
        tbuf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, tbuf, length + 1)
        title = tbuf.value
    return {"app": app, "title": title}


# Bundle id -> the name AppleScript answers to, for the two macOS reads: the
# frontmost tab below, and the front WINDOW in _front_window_darwin(). One tuple
# rather than two dicts, because a browser that is scriptable for one of those and
# missing from the other is a bug nobody would notice for months.
_DARWIN_BROWSERS = (
    ("com.google.chrome", "Google Chrome"),
    ("com.microsoft.edgemac", "Microsoft Edge"),
    ("com.brave.browser", "Brave Browser"),
)


def _read_darwin():
    """Frontmost bundle id from a command-line tool, run fresh every tick - which
    is exactly why it is a subprocess and not NSWorkspace's notification centre.
    In a long-lived non-app process that API stops firing and the last value it
    handed you becomes a permanent lie."""
    front = subprocess.run(
        ["osascript", "-e",
         'tell application "System Events" to get bundle identifier of first '
         'application process whose frontmost is true'],
        capture_output=True, text=True, timeout=3)
    app = (front.stdout or "").strip().lower() or None
    title = ""
    if app:
        name = dict(_DARWIN_BROWSERS).get(app)
        if name:
            # Ask the browser itself for the URL; the host is taken from it below.
            tab = subprocess.run(
                ["osascript", "-e",
                 'tell application "%s" to get URL of active tab of front window'
                 % name],
                capture_output=True, text=True, timeout=3)
            title = (tab.stdout or "").strip()
    return {"app": app, "title": title, "url": title or None}


def _read_linux():
    """Best effort, and honest about it: no xdotool means no reading."""
    out = subprocess.run(["xdotool", "getactivewindow", "getwindowclassname"],
                         capture_output=True, text=True, timeout=3)
    app = (out.stdout or "").strip().lower() or None
    name = subprocess.run(["xdotool", "getactivewindow", "getwindowname"],
                          capture_output=True, text=True, timeout=3)
    return {"app": app, "title": (name.stdout or "").strip()}


def _platform_backend():
    system = platform.system().lower()
    if system.startswith("win"):
        return _read_windows
    if system == "darwin":
        return _read_darwin
    return _read_linux


# Swappable so the privacy test can feed in identities it chose itself. Nothing in
# the running server ever sets this.
READER_BACKEND = None


def _probe_raw():
    """One fresh look. Returns plaintext, and every caller of this is inside
    TargetReader, which is the only place plaintext is allowed to exist."""
    backend = READER_BACKEND or _platform_backend()
    try:
        raw = backend()
    except Exception:                                          # noqa: BLE001
        return None
    if not isinstance(raw, dict) or not raw.get("app"):
        return None
    app = str(raw["app"]).strip().lower()
    host, cdp_alive = None, False
    if app in CHROME_FAMILY:
        if raw.get("url"):                       # macOS hands us the URL directly
            host, cdp_alive = _host_of(raw["url"]), True
        else:
            host, cdp_alive = _cdp_active_host(raw.get("title"))
    return {"app": app, "host": host, "browser": app in CHROME_FAMILY,
            "tab_readable": bool(cdp_alive)}


# =============================================================================
#  THE CARD TRAP - asking the BROWSER which tab is in front, not the OS
# =============================================================================
#
# Pressing a button on the countdown card brings the card's own process to the front.
# Here the card lives in a page, so at the instant of the press the frontmost window
# is the browser showing HOME BASE - the one surface a re-target must never choose. A
# naive "lock what is in front" would therefore lock the card, every time, correctly
# reading a foreground that the press itself created.
#
# So the browser is asked instead of the window manager. Its pages know which of them
# is visible even while the whole browser sits in the background, which is the one
# property that makes an answer possible at all here. None of this runs on the tick:
# it is a WebSocket per candidate tab, paid once, by a press or a sentence.

_FRONT_EXPR = ("((document.visibilityState==='visible')?1:0)"
               "+(document.hasFocus()?2:0)")


def _ws_frame(payload):
    """One masked text frame. Client frames MUST be masked; the mask is four random
    bytes and means nothing, which is exactly what the protocol asks of it."""
    mask = os.urandom(4)
    n = len(payload)
    if n < 126:
        head = struct.pack("!BB", 0x81, 0x80 | n)
    elif n < 65536:
        head = struct.pack("!BBH", 0x81, 0x80 | 126, n)
    else:
        head = struct.pack("!BBQ", 0x81, 0x80 | 127, n)
    return head + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(payload))


def _ws_read(sock, buf):
    """(opcode, payload) or None, consuming one frame from buf - a bytearray carried
    between calls, because one recv() can hand you two frames or half of one."""
    def fill(n):
        while len(buf) < n:
            chunk = sock.recv(4096)
            if not chunk:
                return False
            buf.extend(chunk)
        return True

    if not fill(2):
        return None
    if buf[1] & 0x80:
        return None            # a server frame is never masked; this is not a server
    length, at = buf[1] & 0x7F, 2
    if length == 126:
        if not fill(4):
            return None
        length, at = struct.unpack_from("!H", buf, 2)[0], 4
    elif length == 127:
        if not fill(10):
            return None
        length, at = struct.unpack_from("!Q", buf, 2)[0], 10
    if length > (1 << 20) or not fill(at + length):
        return None
    opcode, data = buf[0] & 0x0F, bytes(buf[at:at + length])
    del buf[:at + length]
    return opcode, data


def _ws_eval_int(ws_url, expression):
    """Evaluate one tiny expression in one page and return its integer value.

    A hand-rolled WebSocket client, because this project has no dependencies and the
    answer is not available anywhere else: the DevTools HTTP endpoints list titles and
    URLs, and neither of those knows which window is in front. Runtime.evaluate does.

    Any failure at all is None, and every caller reads None as "that tab did not
    answer" rather than as a fact about it. A visible tab is never a frozen one, so a
    tab that times out here is evidence against itself, not against the method.
    """
    parts = urllib.parse.urlsplit(ws_url or "")
    if parts.scheme != "ws" or not parts.hostname or not parts.path:
        return None
    port = parts.port or 80
    path = parts.path + (("?" + parts.query) if parts.query else "")
    sock = None
    try:
        sock = socket.create_connection((parts.hostname, port),
                                        timeout=CDP_EVAL_TIMEOUT_S)
        sock.settimeout(CDP_EVAL_TIMEOUT_S)
        sock.sendall(("GET %s HTTP/1.1\r\nHost: %s:%d\r\n"
                      "Upgrade: websocket\r\nConnection: Upgrade\r\n"
                      "Sec-WebSocket-Key: %s\r\nSec-WebSocket-Version: 13\r\n\r\n"
                      % (path, parts.hostname, port,
                         base64.b64encode(os.urandom(16)).decode("ascii"))
                      ).encode("ascii"))
        buf = bytearray()
        while b"\r\n\r\n" not in buf:
            chunk = sock.recv(4096)
            if not chunk or len(buf) > 65536:
                return None
            buf.extend(chunk)
        head, rest = bytes(buf).split(b"\r\n\r\n", 1)
        if b"101" not in head.split(b"\r\n", 1)[0]:
            return None        # not an upgrade; whatever it is, it is not a page
        buf = bytearray(rest)
        sock.sendall(_ws_frame(json.dumps(
            {"id": 1, "method": "Runtime.evaluate",
             "params": {"expression": expression, "returnByValue": True}}
        ).encode("utf-8")))
        deadline = time.monotonic() + CDP_EVAL_TIMEOUT_S
        while time.monotonic() < deadline:
            frame = _ws_read(sock, buf)
            if frame is None:
                return None
            opcode, data = frame
            if opcode != 1:
                continue
            try:
                msg = json.loads(data.decode("utf-8", "replace"))
            except ValueError:
                continue
            if msg.get("id") != 1:
                continue       # an event nobody subscribed to; not our answer
            value = ((msg.get("result") or {}).get("result") or {}).get("value")
            try:
                return int(value)
            except (TypeError, ValueError):
                return None
        return None
    except Exception:                                          # noqa: BLE001
        return None
    finally:
        if sock is not None:
            try:
                sock.close()
            except Exception:                                  # noqa: BLE001
                pass


def _cdp_front_host():
    """(host, endpoint_alive, ambiguous): the host of the tab the BROWSER says is in
    front, asked of the pages themselves, one question each.

    document.visibilityState is 'visible' for the active tab of every browser window
    even with the browser in the background - that is the property this rests on.
    document.hasFocus() narrows it to one window when the browser IS frontmost, so it
    is preferred when anything answers to it.

    Home base is dropped before a single question is asked: the tab you pressed the
    button in is not a candidate for the tab you meant. And the rule from
    _cdp_active_host holds here too - two windows both showing work is a question,
    not an answer, so it reports ambiguity and lets the voice route settle it.
    """
    alive, asked = False, 0
    visible, focused = set(), set()
    for port in CDP_PORTS:
        try:
            with urllib.request.urlopen("http://127.0.0.1:%d/json" % port,
                                        timeout=CDP_TIMEOUT_S) as res:
                targets = json.loads(res.read().decode("utf-8", "replace"))
        except Exception:                                      # noqa: BLE001
            continue
        alive = True
        if not isinstance(targets, list):
            continue
        for t in targets:
            if asked >= CDP_EVAL_MAX_TABS:
                break
            if not isinstance(t, dict) or t.get("type") != "page":
                continue
            url = str(t.get("url") or "")
            ws, host = t.get("webSocketDebuggerUrl"), _host_of(url)
            if not ws or not host or host in HOME_BASE_HOSTS:
                continue
            if not url.lower().startswith(("http://", "https://")):
                continue
            asked += 1
            seen = _ws_eval_int(ws, _FRONT_EXPR)
            if seen is None:
                continue
            if seen & 1:
                visible.add(host)
            if seen & 2:
                focused.add(host)
    # Focused first, then merely visible. Two tabs of the SAME host are not an
    # ambiguity: the host is all that is ever locked, so they agree.
    for hits in (focused, visible):
        if len(hits) == 1:
            return hits.pop(), alive, False
        if len(hits) > 1:
            return None, alive, True
    return None, alive, False


def _front_window_darwin():
    """macOS has a real answer to this and no guessing in it: a browser will list the
    active tab of EVERY window in front-to-back order, and it answers while sitting in
    the background. The first window that is not home base is the one behind the card.

    Untested on this machine, which is a Windows box. It is written to the same
    standard as the CDP path above so that neither platform is the clever one.
    """
    for bundle, name in _DARWIN_BROWSERS:
        try:
            out = subprocess.run(
                ["osascript", "-e",
                 'if application "%s" is running then tell application "%s" to get '
                 'URL of active tab of every window' % (name, name)],
                capture_output=True, text=True, timeout=3)
        except Exception:                                      # noqa: BLE001
            continue
        for url in (out.stdout or "").split(","):
            host = _host_of(url.strip())
            if host and host not in HOME_BASE_HOSTS:
                return {"app": bundle, "host": host, "browser": True,
                        "tab_readable": True, "ambiguous": False}
    return None


def _probe_front_window():
    """One fresh look, from the browser's point of view. The shape _probe_raw()
    returns, plus "ambiguous" - and None when there is nothing to ask.

    The APP identity still comes from the foreground read, because it is the string
    look() will compare against on every later tick: it has to be the OS's name for
    the process, not the browser's name for itself. That is also why a non-browser in
    front returns None - there is no tab to choose, and a foreground read is
    trustworthy precisely when the foreground is not ours.
    """
    front = _probe_raw()
    if not front or not front["browser"]:
        return None
    if front["host"] and front["host"] not in HOME_BASE_HOSTS:
        # The ordinary read already found a tab that is not this page, so it cannot be
        # the card and there is no trap to work around.
        return dict(front, ambiguous=False)
    # READER_BACKEND means a test chose these identities; shelling out to AppleScript
    # underneath it would answer about a machine the test is not describing.
    if READER_BACKEND is None and platform.system().lower() == "darwin":
        found = _front_window_darwin()
        if found:
            return found
    host, alive, ambiguous = _cdp_front_host()
    if ambiguous:
        return {"app": front["app"], "host": None, "browser": True,
                "tab_readable": bool(alive), "ambiguous": True}
    if host is None:
        return None
    return {"app": front["app"], "host": host, "browser": True,
            "tab_readable": True, "ambiguous": False}


# =============================================================================
#  ASKING FOR A HAND, without knowing what hands are
# =============================================================================
#
# Two things in this part are gated offers - relaunch the browser, bring me back - and
# the gate they go through is the one the boss already answers "yes" to: hands.propose(),
# one pending slot, the same two words, the same TTL. This file does not import that
# module, and the reason is worth stating: focus.py is imported by a privacy test, a
# preflight check and several harnesses that have no server around them, and a hard
# dependency on the tool registry would drag a registry read into all of them. So the
# server injects one callable here at import time, and this file knows nothing else
# about it - not the tool's parameters, not its script, not its words.
#
# A None hook is not an error. It means nobody wired the hands up - a test, a harness -
# and every caller below reads that as "no offer was made", which is the same outcome as
# the boss saying no. Nothing here ever runs a tool; it only ever asks.
ASK_HAND = None


def _ask_hand(tool_id):
    """Put a proposal in the gate. True if there is now something to say yes to.

    The SENTENCE is not taken from the gate, deliberately - see LINES["ask_relaunch"].
    What comes back from here is a boolean, so that a failure anywhere behind the hook
    (a gate already holding a proposal, a registry that will not read, a tool that is
    not installed) can neither be spoken as prose nor take the tick down with it.
    """
    hook = ASK_HAND
    if hook is None:
        return False
    try:
        return bool(hook(tool_id))
    except Exception:                                          # noqa: BLE001
        return False


def _cdp_front_target():
    """(target, endpoint_alive, ambiguous): the live tab as an IDENTITY, not a host.

    _cdp_front_host() answers the question the tick asks - "which site am I looking at" -
    and deliberately treats two tabs of the same host as agreement, because the host is
    all it ever locks. This answers a different question: WHICH TAB, as something that
    can be polled and activated later. Two tabs of the same host are therefore an
    ambiguity here rather than an agreement: activating the wrong one of them would put
    a page the boss did not ask for in front of him and call it a rescue.

    Home base is dropped before a single question is asked, as everywhere else: the tab
    you pressed the button in is not a candidate for the tab you meant.

    What comes back is plaintext - a target id, a socket url, a title, a host - and it is
    the caller's business to hold no more of it than it needs. Nothing on TargetReader
    touches this; the reader goes on holding salted hashes and nothing else.
    """
    alive, asked = False, 0
    hits, visible = [], []
    for port in CDP_PORTS:
        try:
            with urllib.request.urlopen("http://127.0.0.1:%d/json" % port,
                                        timeout=CDP_TIMEOUT_S) as res:
                targets = json.loads(res.read().decode("utf-8", "replace"))
        except Exception:                                      # noqa: BLE001
            continue
        alive = True
        if not isinstance(targets, list):
            continue
        for t in targets:
            if asked >= CDP_EVAL_MAX_TABS:
                break
            if not isinstance(t, dict) or t.get("type") != "page":
                continue
            url = str(t.get("url") or "")
            ws, host = t.get("webSocketDebuggerUrl"), _host_of(url)
            ident = str(t.get("id") or "")
            if not ws or not host or not ident or host in HOME_BASE_HOSTS:
                continue
            if not url.lower().startswith(("http://", "https://")):
                continue
            asked += 1
            seen = _ws_eval_int(ws, _FRONT_EXPR)
            if seen is None:
                continue
            found = {"id": ident, "ws": ws, "host": host, "port": port,
                     "title": str(t.get("title") or "")}
            if seen & 2:
                hits.append(found)
            elif seen & 1:
                visible.append(found)
    # Focused first, then merely visible - the same order as _cdp_front_host(), for the
    # same reason: the window with the keyboard in it is a better answer than a window
    # that merely has an active tab.
    for pool in (hits, visible):
        if len(pool) == 1:
            return pool[0], alive, False
        if len(pool) > 1:
            return None, alive, True
    return None, alive, False


class LockWatch:
    """The teeth. One tab, asked every LOCK_POLL_S whether it is still the live one.

    It holds three things a TargetReader would refuse to hold - a CDP target id, a
    socket url, and up to LOCK_TITLE_CHARS characters of the tab's title - so the
    exception is deliberate, bounded, and worth saying exactly what buys what:

      the id and the socket   are what makes the lock have teeth at all. Without an
        identity there is nothing to poll and nothing to activate, and "leaving the
        locked tab is noticed within a second and a half" is not implementable by
        comparing salted hashes of a window title.
      the title               is what the card was asked to show. It is the one observed
        string this feature puts on the wire, it is cut to LOCK_TITLE_CHARS, stripped to
        a label's character set, and it goes to the boss's own screen about the boss's
        own tab. It is never in the ledger, never in the instrument, never in a spoken
        line, and never on disk.

    All three die with the session: unlock, re-target, abort and finish each call
    release(), and after that this object answers "gone" to everything and holds nothing.

    ON LEAVING NOTHING ATTACHED. Every question opens a socket, asks, and closes it
    (_ws_eval_int), so between polls the browser reports this target as unattached -
    measured, lookbook 18.4. The leak worth guarding against is therefore not a CDP
    attachment, which cannot survive by construction; it is a watcher that goes on
    polling a tab after the session that made it has ended. Hence release(), the `live`
    flag every caller checks, and the `watchers` count in the instrument.
    """

    def __init__(self, port, target_id, ws_url, title):
        self.port = int(port)
        self.id = str(target_id)
        self.ws = str(ws_url)
        self.title = (_clean_label(title) or "")[:LOCK_TITLE_CHARS].strip()
        self.live = True
        self.state = "on"          # "on" | "off" | "gone"
        self.off_since = None      # when it first stopped being the live tab
        self.polls = 0
        self.misses = 0            # consecutive unanswered questions
        self.activations = 0

    def poll(self, now=None):
        """One question, and the state it leaves behind.

        Three misses in a row is "gone" rather than "off", and that distinction is the
        whole reason misses are counted: a tab that has been closed cannot be drifted
        away from, and accusing the boss of leaving a tab that no longer exists is how a
        man learns to ignore a watchdog.
        """
        if not self.live:
            return "gone"
        now = time.monotonic() if now is None else now
        self.polls += 1
        seen = _ws_eval_int(self.ws, _FRONT_EXPR)
        if seen is None:
            self.misses += 1
            if self.misses >= 3:
                self.state = "gone"
            return self.state
        self.misses = 0
        # BIT 1, and not bit 2. Bit 1 is "I am the active tab of my window", which is
        # the tab statement; bit 2 is "my window has the keyboard", which is the OS's
        # statement about applications and is already the window reader's job. Reading
        # tab-ness off bit 2 would count every click into VS Code twice.
        if seen & 1:
            self.state = "on"
            self.off_since = None
        else:
            if self.state != "off":
                self.off_since = now
            self.state = "off"
        return self.state

    def drifted(self, now=None):
        """Has it been off long enough to count? The grace lives here - LOCK_GRACE_MS."""
        if not self.live or self.state != "off" or self.off_since is None:
            return False
        now = time.monotonic() if now is None else now
        return (now - self.off_since) * 1000.0 >= LOCK_GRACE_MS

    def activate(self):
        """Bring the tab, and its window, to the front. True only if it worked.

        /json/activate is Target.activateTarget, and on Windows it raises the WINDOW as
        well as re-ordering the tabs - measured: the locked tab went from visible-but-
        unfocused to focused and the window in front of it dropped back. So there is
        nothing to synthesise here and no input to inject.

        The verdict is read back off the TAB rather than off the HTTP status, because
        "the browser accepted my request" is not the same claim as "the boss is looking
        at it", and the second one is what the sentence afterwards will say.
        """
        if not self.live:
            return False
        self.activations += 1
        try:
            with urllib.request.urlopen(
                    "http://127.0.0.1:%d/json/activate/%s" % (self.port, self.id),
                    timeout=CDP_TIMEOUT_S) as res:
                res.read()
        except Exception:                                      # noqa: BLE001
            return False
        deadline = time.monotonic() + LOCK_ACTIVATE_S
        while time.monotonic() < deadline:
            seen = _ws_eval_int(self.ws, _FRONT_EXPR)
            if seen is not None and seen & 1:
                self.state = "on"
                self.off_since = None
                return True
            time.sleep(0.1)
        return False

    def release(self):
        """Stop watching, for good. Idempotent, and there is no way back from it."""
        self.live = False
        self.state = "gone"
        self.off_since = None
        self.ws = ""
        self.id = ""
        self.title = ""


_CAPABILITY_CACHE = {"at": -1e9, "value": None}


def capability():
    """What this machine can actually watch, in booleans, before you commit to a
    session. Three answers, and the middle one is the one that surprises people.

      app  - can we see the frontmost application at all
      tab  - is the frontmost app a browser we could read a site out of
      cdp  - is a Chrome-family browser actually reachable for the active tab

    Tab-level locking needs `cdp`, and `cdp` needs Chrome to have been started with
    --remote-debugging-port=9222. Without it a session still works: it locks the
    APP and says out loud that it is watching the app only. Degrading loudly is the
    whole point - a watchdog that quietly stops watching half of what you asked it
    to is worse than one that never offered.
    """
    now = time.monotonic()
    if _CAPABILITY_CACHE["value"] and now - _CAPABILITY_CACHE["at"] < CAPABILITY_TTL_S:
        return dict(_CAPABILITY_CACHE["value"])
    # Cached only here, and only for a few seconds, because three dead CDP ports at
    # half a second each is a real wait to hang a page load on. The TICK never uses
    # this - it reads fresh every second, which is the rule that matters.
    raw = _probe_raw()
    value = {
        "app": raw is not None,
        "browser": bool(raw and raw["browser"]),
        "cdp": bool(raw and raw["tab_readable"]) or _cdp_active_host(None)[1],
        "backend": (READER_BACKEND or _platform_backend()).__name__,
    }
    _CAPABILITY_CACHE.update({"at": now, "value": value})
    return dict(value)


def _forget_capability():
    """Throw the capability cache away.

    Called in exactly one place - a relaunch hand that worked - because that is the one
    moment when something has DELIBERATELY changed what this machine can watch. A
    three-second-old "there is no debugging port" about a port that was opened half a
    second ago would make the lock refuse itself for the very reason the boss said yes
    to remove, which is a feature arguing with its own consent.
    """
    _CAPABILITY_CACHE.update({"at": -1e9, "value": None})


class TargetReader:
    """Holds the target as SALTED HASHES and answers only in booleans.

    Read the public methods and note what is not in them: no getter for the app, no
    getter for the host, no attribute holding either in plaintext, and no setter that
    takes a surface from anywhere but a fresh read of where you are. The identity
    exists as a local variable inside settle(), settle_here() and look() for a few
    microseconds and is then gone. That is what "compared and discarded inside the reader" means, and it is why
    no amount of carelessness elsewhere in this file can leak one - there is nothing
    to leak.

    The candidate a settle is building is held here too, and as hashes for the same
    reason: "the surface I am about to hold you to" is exactly as sensitive as the
    surface itself.
    """

    def __init__(self):
        self._salt = os.urandom(16)      # per reader: hashes cannot even be
        self._app = None                 # correlated between two sessions
        self._host = None
        self._locked = False
        self._watch_tab = False
        self._cand = None                # the surface being considered, as hashes
        self._cand_ticks = 0

    def _h(self, value):
        if value is None:
            return None
        return hashlib.blake2b(str(value).encode("utf-8", "replace"),
                              key=self._salt, digest_size=HASH_BYTES).digest()

    # -- settling, which is the only way a target is ever chosen --------------

    def forget_candidate(self):
        """Whatever was settling is no longer settling. Called when you are at home
        base, so the two ticks have to be two ticks somewhere you actually work."""
        self._cand = None
        self._cand_ticks = 0

    def settle(self):
        """One tick of settling, and the ONLY way self._app is ever assigned.

        There is no method on this class that locks a surface handed to it from
        elsewhere, and that is deliberate: every target this feature has ever
        watched was read from the foreground by this method, on a tick, twice. A
        background window cannot get in here, and neither can a second monitor,
        because _probe_raw() only ever answers about the window in front.

        What comes out is booleans. What goes in is discarded.
        """
        raw = _probe_raw()
        if not raw:
            self.forget_candidate()
            return {"readable": False, "home": False, "settled": False,
                    "waiting": False, "ticks": 0}

        home = bool(raw["browser"] and raw["host"] in HOME_BASE_HOSTS)
        if home:
            self.forget_candidate()
            return {"readable": True, "home": True, "settled": False,
                    "waiting": False, "ticks": 0}

        app_h = self._h(raw["app"])
        host_h = self._h(raw["host"]) if raw["host"] else None

        # A BROWSER WE CANNOT READ A SITE OUT OF, while the endpoint is alive, is not
        # a candidate yet. The viewer's own 3D boot can stall scripting for seconds,
        # and the title join can be momentarily ambiguous between two windows - both
        # of which resolve on their own within a tick or two. Settling app-only here
        # would turn a transient stall into a session that never watches the site,
        # which is precisely the wrong lock this whole path exists to avoid.
        #
        # With NO endpoint alive it is not transient, it is the machine: no browser
        # was started with --remote-debugging-port, tab-level locking is impossible,
        # and waiting 45 seconds to discover a permanent fact would be theatre. That
        # settles at application level and says so.
        if raw["browser"] and host_h is None and raw["tab_readable"]:
            self.forget_candidate()
            return {"readable": True, "home": False, "settled": False,
                    "waiting": True, "ticks": 0}

        key = (app_h, host_h)
        if key == self._cand:
            self._cand_ticks += 1
        else:
            self._cand, self._cand_ticks = key, 1
        if self._cand_ticks < SETTLE_TICKS:
            # Not yet. Passing THROUGH a window on the way to the right one must not
            # become the thing you are held to for the next half hour.
            return {"readable": True, "home": False, "settled": False,
                    "waiting": False, "ticks": self._cand_ticks}

        self._app, self._host = app_h, host_h
        self._watch_tab = host_h is not None
        self._locked = True
        return {"readable": True, "home": False, "settled": True, "waiting": False,
                "ticks": self._cand_ticks, "app": True, "tab": self._watch_tab,
                "browser": raw["browser"], "tab_readable": raw["tab_readable"]}

    def settle_app_only(self):
        """The 45-second fallback: watch the application in front of you and give up
        on the site. Still the foreground and still one fresh read - the only thing
        thrown away is the tab, which is the half that could have been wrong."""
        raw = _probe_raw()
        self.forget_candidate()
        if not raw:
            self._locked = False
            return {"locked": False, "readable": False, "tab": False}
        self._app = self._h(raw["app"])
        self._host = None
        self._watch_tab = False
        self._locked = True
        return {"locked": True, "readable": True, "tab": False,
                "browser": raw["browser"], "tab_readable": raw["tab_readable"]}

    def forget_target(self):
        """Watch nothing again. Only erases - there is no argument it could take and
        nothing it could be persuaded to remember - and it is how "I'll lock on where
        you land" becomes true at the moment it is said rather than a tick later."""
        self._app = None
        self._host = None
        self._watch_tab = False
        self._locked = False
        self.forget_candidate()

    def settle_here(self, via_browser=False):
        """THE EXPLICIT RE-TARGET: lock what is in front of you now, in one read.

        Settling takes two ticks because nobody has told me anything. Here you have:
        you said "lock on this tab", or pressed the pill that means it. One fresh read
        is the whole of the evidence needed, and making you hold still for a second to
        prove a sentence you just said would be the machine doubting you on principle.

        Still no surface comes in from outside. via_browser is a flag about WHICH fresh
        read to take - the window manager's, or the browser's own account of which of
        its tabs is visible - and the answer to both is discarded here as always.

        Returns booleans and a reason:
          ok        - the target moved, and self._app is the only thing that knows
          "home"    - that is this page, which is the one surface this cannot lock
          "ambiguous" / "unreadable" - nothing was decided and nothing was changed
        """
        raw = _probe_front_window() if via_browser else _probe_raw()
        if raw and raw.get("ambiguous"):
            return {"ok": False, "reason": "ambiguous", "tab": False,
                    "browser": True, "tab_readable": bool(raw["tab_readable"])}
        if not raw:
            return {"ok": False, "reason": "unreadable", "tab": False,
                    "browser": False, "tab_readable": False}
        if raw["browser"] and raw["host"] in HOME_BASE_HOSTS:
            return {"ok": False, "reason": "home", "tab": False, "browser": True,
                    "tab_readable": bool(raw["tab_readable"])}

        # A browser whose site cannot be read does NOT wait here, unlike settle(): you
        # have told me this is the surface, so the app is locked and the missing half
        # is said out loud. Waiting would be arguing with an instruction.
        self._app = self._h(raw["app"])
        self._host = self._h(raw["host"]) if raw["host"] else None
        self._watch_tab = self._host is not None
        self._locked = True
        self.forget_candidate()
        return {"ok": True, "reason": "", "tab": self._watch_tab,
                "browser": bool(raw["browser"]),
                "tab_readable": bool(raw["tab_readable"])}

    def confirms_host(self, host):
        """Is THIS the host you are holding me to? A comparator, not a setter.

        The class promise is "answers only in booleans", and this keeps it: plaintext
        goes in, a boolean comes out, nothing is assigned and nothing is returned that
        was not already known to the caller. It exists because two organs now know about
        the locked surface - this reader, by hash, and a LockWatch, by CDP target - and a
        watcher pointed at a different tab from the one the reader is holding would be a
        lock that disagreed with itself in silence. So the watcher is checked against the
        reader at the moment it is made, and dropped if the two do not agree.
        """
        if not self._locked or self._host is None or not host:
            return False
        return self._h(host) == self._host

    def look(self):
        """The verdict: booleans, and at most one word.

        The booleans are the whole of what the session runs on. `label` is the
        exception and it is a narrow one: a spoken name for the surface in front,
        derived HERE where the plaintext already legitimately exists, and only when
        the verdict has already established that this is a readable drift - a target
        exists, and the surface in front is neither it nor home base, which is to say
        the one case where a sentence is about to be said about it. Nothing is a drift
        before there is a target, so a deferred session derives nothing at all.

        Every other case returns label None, including home base: this page is never a
        drift and never gets named. The caller uses the word in the sentence it is
        emitting and drops it; nothing on this reader ever holds it.
        """
        raw = _probe_raw()
        if not raw:
            return {"readable": False, "on_app": False, "on_tab": None,
                    "home": False, "tab_readable": False, "on_target": None,
                    "label": None}
        home = bool(raw["browser"] and raw["host"] in HOME_BASE_HOSTS)
        on_app = self._locked and self._h(raw["app"]) == self._app
        on_tab = None
        if on_app and self._watch_tab:
            if raw["host"] is None:
                on_tab = None            # unreadable is not the same as elsewhere
            else:
                on_tab = self._h(raw["host"]) == self._host
        on_target = bool(on_app and on_tab is not False)
        # THE NAME, and only for the one case that will speak it. Computed from locals
        # that this frame is about to discard, assigned to nothing on self, and absent
        # from the answer entirely when you are at home base or where you said you
        # would be.
        label = None
        if NAME_DRIFTS and self._locked and not home and not on_target:
            label = spoken_surface(raw["app"], raw["host"])
        return {"readable": True, "on_app": bool(on_app), "on_tab": on_tab,
                "home": home, "tab_readable": bool(raw["tab_readable"]),
                "on_target": on_target, "label": label}

    def diagnose(self):
        """look(), for a human holding a bug report. Booleans, small ints and words.

        The same one fresh read, the same salted comparison, the same discard - and
        deliberately NOT built out of look(), because look() answers the question the
        session asks ("is this a drift") and this answers the question you ask ("which
        half of the lock is wrong"). A diagnostic that can only speak in the caller's
        vocabulary cannot tell you the caller is confused.

        There is no label here and no case in which there could be one: nothing on
        this path is about to say a sentence, so nothing needs a word for where you
        are. This is the one reader method whose answer is safe to print in full.
        """
        out = {"appReadable": False, "frontIsBrowser": False, "tabRead": "unknown",
               "frontIsHome": False,
               "appHash": self._app is not None, "tabHash": self._host is not None,
               "locked": bool(self._locked), "candidate": self._cand is not None,
               "settleTicks": int(self._cand_ticks),
               "appLane": "n/a", "tabLane": "n/a", "readerOnTarget": False}
        raw = _probe_raw()
        if not raw:
            return out
        out["appReadable"] = True
        out["frontIsBrowser"] = bool(raw["browser"])
        if not raw["browser"]:
            out["tabRead"] = "notbrowser"
        elif raw["host"]:
            out["tabRead"] = "read"
        elif raw["tab_readable"]:
            out["tabRead"] = "ambiguous"
        else:
            out["tabRead"] = "noendpoint"
        out["frontIsHome"] = bool(raw["browser"] and raw["host"] in HOME_BASE_HOSTS)
        if not self._locked:
            # No target, so there are no lanes to be on or off. "n/a" rather than
            # "off": a deferred session is not a session you are failing.
            return out
        on_app = self._h(raw["app"]) == self._app
        out["appLane"] = "on" if on_app else "off"
        if not self._watch_tab:
            out["tabLane"] = "n/a"           # app-only lock, by fallback or by machine
        elif not on_app:
            out["tabLane"] = "off"           # wrong app; the site is beside the point
        elif raw["host"] is None:
            out["tabLane"] = "unknown"       # right app, unreadable site: not a drift
        else:
            out["tabLane"] = "on" if self._h(raw["host"]) == self._host else "off"
        # The same arithmetic as look(): unknown and n/a are not off. If this line and
        # look()'s ever disagree, this one is wrong and the session is right.
        out["readerOnTarget"] = bool(on_app and out["tabLane"] != "off")
        return out

    @property
    def watching_tab(self):
        return self._watch_tab

    @property
    def locked(self):
        return self._locked


# =============================================================================
#  THE LEDGER - the running totals, and eight numbers per session
# =============================================================================
#
# There is a per-session row now, and the interesting part is what it is NOT allowed
# to be. A record of your working day is worth having - "was Tuesday afternoon
# actually as bad as it felt" is a real question and aggregates cannot answer it - but
# a free-form row is how a helpful summary becomes a behavioural log one field at a
# time. So the row is a WHITELIST of eight keys, declared once, below, and enforced on
# the way in and on the way out:
#
#   at, plannedMinutes, activeMinutes, onTargetMinutes, drifts, secondsAdrift,
#   percent, completed
#
# Four things are deliberately absent and they are the four somebody would add first:
# where you were (there is no plaintext to add - see TargetReader), what you said you
# were doing (`intent` is a sentence you dictated; it may live in memory for the
# length of a session and it is not going on disk), which app or site you drifted to,
# and the clock time of each drift. A row that cannot hold them cannot leak them.
#
# _write_ledger() rebuilds the file from these whitelists rather than serialising what
# it was handed, so a caller who mutates the dict it got from read_ledger() cannot
# smuggle a ninth key past the door. test_focus_privacy.py proves exactly that.

SESSION_ROW_KEYS = {"at": str, "plannedMinutes": int, "activeMinutes": int,
                    "onTargetMinutes": int, "drifts": int, "secondsAdrift": int,
                    "percent": int, "completed": bool}

_LEDGER_DEFAULT = {"sessions": 0, "plannedMinutes": 0, "onTargetMinutes": 0,
                   "driftMinutes": 0, "drifts": 0, "cleanSessions": 0,
                   "streak": 0, "bestStreak": 0, "updated": "",
                   "history": []}


def session_row(raw):
    """One end-of-session row, copied through SESSION_ROW_KEYS and coerced.

    The single door for both directions: nothing reaches the file except through
    here, and nothing comes back out of the file except through here either, so a row
    hand-edited into focus-ledger.json is filtered on read exactly as one written by
    _record() is filtered on write.
    """
    if not isinstance(raw, dict):
        return None
    out = {}
    for key, kind in SESSION_ROW_KEYS.items():
        value = raw.get(key)
        if kind is bool:
            out[key] = bool(value)
        elif kind is int:
            try:
                out[key] = int(round(float(value or 0)))
            except (TypeError, ValueError):
                out[key] = 0
        else:
            # The timestamp, and the only string in a row. Kept to the shape _record()
            # writes - minutes, never seconds - so a truncated or invented value
            # cannot turn into a paragraph.
            text = "" if value is None else str(value)
            out[key] = text[:16]
    return out


def _blank_ledger():
    """A fresh empty ledger. Copied per call because one value in _LEDGER_DEFAULT is
    now a list, and handing out the same list to every caller means the first one to
    append a row silently changes what "empty" means for the rest of the process."""
    return {key: ([] if isinstance(value, list) else value)
            for key, value in _LEDGER_DEFAULT.items()}


def read_ledger():
    try:
        with open(LEDGER_PATH, "r", encoding="utf-8") as fh:
            saved = json.load(fh)
        if not isinstance(saved, dict):
            raise ValueError
    except Exception:                                          # noqa: BLE001
        return _blank_ledger()
    out = _blank_ledger()
    for key, default in _LEDGER_DEFAULT.items():
        value = saved.get(key, default)
        if isinstance(default, list):
            rows = [session_row(item) for item in (value or [])] \
                if isinstance(value, list) else []
            out[key] = [row for row in rows if row][-LEDGER_HISTORY_MAX:]
        else:
            out[key] = value if isinstance(value, type(default)) else default
    return out


def _write_ledger(book):
    """Write the file from the whitelists, not from the dict handed in.

    Rebuilt rather than dumped on purpose: the alternative is that whether the ledger
    holds a key nobody approved depends on whether some caller upstream happened to
    put one in the dict. Here it cannot, and that is a property of this function
    rather than of everybody who ever calls it.
    """
    clean = {}
    for key, default in _LEDGER_DEFAULT.items():
        value = book.get(key, default) if isinstance(book, dict) else default
        if isinstance(default, list):
            rows = [session_row(item) for item in (value or [])] \
                if isinstance(value, list) else []
            clean[key] = [row for row in rows if row][-LEDGER_HISTORY_MAX:]
        elif isinstance(value, type(default)):
            clean[key] = value
        else:
            clean[key] = default
    tmp = LEDGER_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(clean, fh, indent=2)
        fh.write("\n")
    os.replace(tmp, LEDGER_PATH)


# =============================================================================
#  SPOKEN NUMBERS
# =============================================================================

_UNITS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
          "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11,
          "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
          "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19}
_TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fourty": 40, "fifty": 50,
         "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90}


def spoken_int(text):
    """The first number in a phrase, digits or words. None if there is not one."""
    said = str(text or "").lower()
    digits = re.search(r"\b(\d{1,3})\b", said)
    words = None
    best = len(said) + 1
    for tens_word, tens in _TENS.items():
        match = re.search(r"\b%s(?:[\s-]+(%s))?\b"
                          % (tens_word, "|".join(_UNITS)), said)
        if match and match.start() < best:
            best, words = match.start(), tens + _UNITS.get(match.group(1) or "", 0)
    for unit_word, unit in _UNITS.items():
        match = re.search(r"\b%s\b" % unit_word, said)
        if match and match.start() < best:
            best, words = match.start(), unit
    if digits and (words is None or digits.start() < best):
        return int(digits.group(1))
    return words


def spoken_minutes(text):
    """Minutes, understanding hours and the two halves people actually say."""
    said = str(text or "").lower()
    if re.search(r"\bhalf an hour\b|\bhalf hour\b", said):
        return 30
    if re.search(r"\b(quarter of an hour|quarter hour)\b", said):
        return 15
    number = spoken_int(said)
    if re.search(r"\bhours?\b", said):
        return (number or 1) * 60
    return number


def _mmss(seconds):
    seconds = max(0, int(round(seconds)))
    return "%d:%02d" % (seconds // 60, seconds % 60)


def _spoken_span(seconds):
    """A duration as a butler would say it, not as a stopwatch would print it."""
    seconds = max(0, int(round(seconds)))
    minutes = seconds // 60
    if minutes < 1:
        if seconds == 1:
            return "a second"        # "1 seconds on target" is nobody's butler
        return "%d seconds" % seconds
    if minutes == 1:
        return "a minute"
    return "%d minutes" % minutes


def _spoken_drifts(count):
    if not count:
        return "not one drift"
    if count == 1:
        return "one drift"
    return "%d drifts" % count


# The filler people actually say when answering "what are we focusing on?" out loud.
# Stripped so the stored intent is the WORK and not the preamble - "I'm working on the
# Q3 deck" becomes "the Q3 deck", which is the only form that reads well inside a
# callout. Anchored at the start; a phrase in the middle of your answer is yours.
_INTENT_PREFIX_RE = re.compile(
    r"^(?:(?:um|uh|er|so|well|okay|ok|right)[,\s]+)*"
    r"(?:(?:i'?m|i am|we'?re|we are|let'?s|i'?ll|i will|i want to|i need to|"
    r"i'?ve got to|i have to)\s+)?"
    r"(?:(?:just|only|mainly|mostly|currently|now)\s+)*"
    r"(?:(?:going to|gonna|about to|trying to)\s+)?"
    r"(?:(?:work|working|focus|focusing|focussing|concentrate|concentrating)\s+"
    r"(?:on|upon)\s+|(?:do|doing|write|writing|finish|finishing|build|building|"
    r"read|reading|review|reviewing|fix|fixing)\s+)?"
    r"(?:(?:it'?s|its|this is|that'?s|it is)\s+)?", re.I)

# An answer that is nothing but hesitation is not an answer. Without this, "uh" gets
# through as an intent and comes back at you later as "That is not uh, sir."
_INTENT_EMPTY_RE = re.compile(
    r"^(?:um|uh|er|erm|ah|hmm|well|so|okay|ok|right|yeah|yes|no|nothing|dunno|"
    r"i dunno|i don'?t know|stuff|things|work|it|this|that)$", re.I)


def clean_intent(text):
    """Your answer to "what are we focusing on?", tidied and capped.

    The one string in this module that comes from you rather than from watching you.
    It is trimmed of the filler that dictation always carries and shortened to
    INTENT_MAX_CHARS, and that is the whole of it: it is not parsed, not classified
    and not sent anywhere. Returns "" for an answer with nothing in it, which is the
    same as never having answered.
    """
    said = " ".join(str(text or "").split())
    said = _INTENT_PREFIX_RE.sub("", said, count=1).strip()
    said = said.strip(" .,;:!-–—\"'")
    # A dictated answer with no letters in it, or with nothing but hesitation in it,
    # is noise rather than an intent - and it is better to have none than to quote it.
    if not re.search(r"[a-z0-9]", said, re.I):
        return ""
    if _INTENT_EMPTY_RE.match(said):
        return ""
    if len(said) > INTENT_MAX_CHARS:
        said = said[:INTENT_MAX_CHARS].rsplit(" ", 1)[0].rstrip(" .,;:") + "…"
    return said


def spoken_intent(intent):
    """The intent IF it is short enough to be said, and "" if it is not.

    "Never parrot a long dictated intent back to me" is a rule, and a rule with no
    number behind it is a hope. This is the number: past INTENT_SPOKEN_MAX_CHARS the
    intent is still kept and still shown on the card, but every line that would have
    recited it falls back to one that does not.
    """
    said = str(intent or "").strip()
    if not said or len(said) > INTENT_SPOKEN_MAX_CHARS:
        return ""
    if said.endswith("…"):        # it was truncated, so it is a fragment
        return ""
    return said


# =============================================================================
#  THE EYES - three booleans about your body, and no picture of it anywhere
# =============================================================================
#
# Read the fields of this class and note what is not in them. There is no frame, no
# landmark, no face descriptor, no measurement and no history - and no field that could
# hold one, which is the same argument TargetReader makes about window titles. The page
# has the camera, reads it, reduces what it sees to three booleans, and sends those.
# This object is where they land.
#
# The policy lives here rather than in the page for one reason: the page can be closed,
# reloaded or muted, and a rule that only exists in it is a rule that a reload repeals.
# The cooldown, the relief valve and the drift counting are therefore server-side, and
# the page is left with the one job only it can do - looking.


def spoken_line(template, **fields):
    """Format ONE registered line for a caller that has no session to queue it in.

    The eyes nudge whether or not a session is running, so they need a way to speak
    that does not go through FocusSession._emit() - and it has to be gated exactly as
    hard, or the second path would be the way round the first. So: the same registry
    check, plus a refusal of every naming line, because an organ that watches your body
    has nothing it could legitimately name. Nothing is kept: no seq, no queue, no
    record. It is said and it is gone.
    """
    if template not in LINE_REGISTRY:
        raise ValueError("focus.py: refusing to speak a line that is not in "
                         "LINE_REGISTRY")
    if template in NAMED_LINES:
        raise ValueError("focus.py: the eyes never name anything")
    return template.format(**fields)


class Eyes:
    """What the webcam organ last reported, and whether it is still allowed a word."""

    def __init__(self):
        self.on = False
        self.at = 0.0          # when the page last reported anything at all
        self.present = False
        self.head_down = False
        self.slouched = False
        self.hush_until = 0.0
        self.last_nudge = 0.0
        # A count, for the card. Not a log: it says how often the eyes spoke, never
        # when, never about which posture, and it does not survive a restart.
        self.nudges = 0

    # -- what the page says ------------------------------------------------

    def report(self, on, present, head_down, slouched, now=None):
        """The whole write surface of this object, and it takes four booleans.

        A posture is only believed while you are present: "head down" derived from a
        frame with nobody in it is the landmark detector guessing, and a nudge built on
        a guess is worse than silence.
        """
        now = time.monotonic() if now is None else now
        self.on = bool(on)
        self.at = now
        if not self.on:
            self.present = self.head_down = self.slouched = False
            return
        self.present = bool(present)
        self.head_down = bool(head_down) and self.present
        self.slouched = bool(slouched) and self.present

    def close(self, now=None):
        self.report(False, False, False, False, now)

    # -- freshness ---------------------------------------------------------

    def fresh(self, now=None):
        now = time.monotonic() if now is None else now
        return bool(self.on) and (now - self.at) < EYE_STALE_S

    def posture(self, now=None):
        """The booleans, or all-False if the page has gone quiet. Every reader goes
        through here rather than touching the fields, so there is exactly one place
        where a stale report stops counting."""
        if not self.fresh(now):
            return {"fresh": False, "present": False, "head_down": False,
                    "slouched": False}
        return {"fresh": True, "present": self.present,
                "head_down": self.head_down, "slouched": self.slouched}

    # -- the voice ---------------------------------------------------------

    def hush(self, seconds=RELIEF_S, now=None):
        now = time.monotonic() if now is None else now
        self.hush_until = now + max(0.0, float(seconds))

    def hushed(self, now=None):
        now = time.monotonic() if now is None else now
        return now < self.hush_until

    def hush_left(self, now=None):
        now = time.monotonic() if now is None else now
        return max(0.0, self.hush_until - now)

    def may_nudge(self, now=None):
        """One nudge, then EYE_COOLDOWN_S of quiet however bent you stay. The relief
        valve outranks the cooldown, which is the point of having one."""
        now = time.monotonic() if now is None else now
        if now < self.hush_until:
            return False
        return (not self.last_nudge) or (now - self.last_nudge) >= EYE_COOLDOWN_S

    def spend(self, now=None):
        """Called only when a line is genuinely going out. A nudge that was refused
        further down - snoozed, or a session that would not queue it - must not start
        the cooldown, or the refusal would cost you the next thirty seconds of it."""
        self.last_nudge = time.monotonic() if now is None else now
        self.nudges += 1

    def tuning(self):
        """The numbers the PAGE has to apply, handed back with every report so the two
        halves cannot drift apart. The page reads the camera; these say when that is
        worth mentioning."""
        return {"sustainMs": int(EYE_SUSTAIN_MS), "absenceMs": int(EYE_ABSENCE_MS),
                "cooldownS": int(EYE_COOLDOWN_S), "staleS": int(EYE_STALE_S),
                "reliefS": int(RELIEF_S), "countsAsDrift": bool(EYE_PHONE_DRIFTS)}


EYES = Eyes()


# =============================================================================
#  THE SESSION
# =============================================================================

class FocusSession:
    """One session. Every mutation happens under the manager's lock."""

    def __init__(self, minutes, reader=None, seq0=0, tab_capable=None):

        self.planned_s = float(max(MIN_MINUTES, min(MAX_MINUTES, int(minutes)))) * 60
        self.reader = reader or TargetReader()
        self.state = "arming"
        self.started_monotonic = time.monotonic()
        # When the CURRENT deferral began, which is not always when the session did:
        # pausing for two minutes while still deferred and then resuming must not
        # arrive back with the 45 seconds already spent.
        self._arm_since = self.started_monotonic
        self.last_tick = self.started_monotonic
        self.elapsed_s = 0.0

        self.on_target_s = 0.0
        self.drift_s = 0.0
        self.home_s = 0.0
        self.excused_s = 0.0
        self.unknown_s = 0.0
        self.drifts = 0

        # the current excursion
        self._off_since = None
        # WHAT KIND of excursion it is: "tab" for a window or a site, "phone" for a
        # sustained head-down posture the eyes reported. Decided when the excursion
        # opens and never changed under it, so one drift is one kind of drift and the
        # pool it is spoken from cannot switch halfway through. It is not an identity:
        # two words, both of them about this app's own machinery.
        self._off_kind = "tab"
        self._counted = False
        self._excursion_s = 0.0
        self._next_nag = None
        self.excused = False

        self.nag_s = NAG_DEFAULT_S
        self.snooze_until = 0.0
        self.readable = True
        self.tab_watched = False
        self.tab_readable = False
        self.ended_reason = None
        self.report = ""
        # The say-sequence CONTINUES from the session before it, and that is not a
        # detail. The client speaks any line whose seq it has not spoken yet, so a
        # counter that restarted at 1 with every session would make a brand new
        # "locked on" look like a line already delivered - and the whole session
        # would run in silence. Monotonic for the life of the process; the client
        # re-bases itself if the process restarts underneath it.
        self.seq = int(seq0)
        self.say = []
        # THE SCRUB LIST. The seq of every line in the queue that has a NAME in it,
        # and the moment they stop being allowed to sit there. Both are bookkeeping
        # about the queue, not about you: a set of integers and a timestamp, holding
        # no record of where you went even while the line they refer to is still
        # waiting to be spoken.
        self._named_seqs = set()
        self._named_until = 0.0
        # Drill sergeant, off until asked for. Never inferred from a bad session:
        # escalating the register on its own would be the app deciding how it is
        # allowed to speak to you.
        self.drill = False
        self._home_hint_at = 0.0
        self._on_target_now = False
        self._at_home_now = False

        # THE TAB WATCHER, and the small amount of bookkeeping the offers need.
        #
        # self.watch is a LockWatch or None, and None is the ordinary state: no tab lock
        # has been taken yet, or this machine has no debugging port to ask. The three
        # flags below are each "have I already said this", because the difference between
        # a watchdog and a nag is entirely in how many times it offers the same thing.
        self.watch = None
        self.tab_lock_why = ""       # one word out of TAB_LOCK_WHY, for the card
        self._lock_drift_at = 0.0    # when the last counted locked-tab drift began
        self._summon_at = 0.0        # when the summon was last offered
        self._relaunch_asked = False # once per session, whatever the answer

        # THE ANSWER WINDOW. The start line ends with a question, so the client opens
        # the microphone for exactly one answer and posts it back. Nothing waits on
        # it: an unanswered question costs you nothing but a slightly duller callout.
        self.intent = ""
        self._intent_used = False
        self._intent_deadline = time.monotonic() + INTENT_WINDOW_S

        # CAN THIS MACHINE TAKE THE LOCK IT IS ABOUT TO PROMISE? Asked here, once, and
        # kept: capability()["cdp"] is the same boolean /health reports, and it is false
        # exactly when Chrome was started without --remote-debugging-port. The answer
        # decides which start line is spoken and is then never re-asked - the tick reads
        # the world fresh every second and has its own lines for losing the site
        # mid-session ("notab", "settled_app_only"), so re-deciding this one here would
        # only produce the same caveat twice. Passed in by tests and by any caller that
        # already knows; None means find out.
        self.tab_capable = bool(capability()["cdp"] if tab_capable is None
                                else tab_capable)
        self._note("arming" if self.tab_capable else "arming_app_only",
                   minutes=int(self.planned_s // 60))

    # -- the one thing you tell me, rather than the many I read ---------------

    @property
    def deferred(self):
        """Nothing is being watched yet. Exposed to the client as a boolean, because
        "arming" is a state word and this is a fact about the lock."""
        return self.state == "arming" and not self.reader.locked

    @property
    def awaiting_intent(self):
        return (not self.intent and self.state in ("arming", "running")
                and time.monotonic() < self._intent_deadline)

    def set_intent(self, text):
        """Attach your answer to the running session. The ONLY writer of self.intent,
        and it is reached only from the POST body - no reader, no probe and no window
        title has a path to this, which is why a free-text field costs the privacy
        promise nothing.

        The reply is "Noted, sir." whatever you said, however long it was. Reading a
        dictated sentence back to the person who just dictated it is not
        confirmation, it is an impression of a confirmation.
        """
        cleaned = clean_intent(text)
        if not cleaned:
            return False
        self.intent = cleaned
        self._intent_deadline = 0.0
        self._note("intent_noted")
        return True

    # -- speaking ----------------------------------------------------------

    def _emit(self, template, kind, **fields):
        """The only way a line reaches the client, and it will not accept a
        template that is not in the registry. This is the structural half of the
        privacy promise: there is no function here that will speak free text."""
        if template not in LINE_REGISTRY:
            raise ValueError("focus.py: refusing to speak a line that is not in "
                             "LINE_REGISTRY")
        if kind not in SAY_KINDS:
            raise ValueError("focus.py: unknown say kind %r" % kind)
        named = template in NAMED_LINES
        if named and not NAME_DRIFTS:
            # Unreachable through the pools - _callout_pool() does not offer a named
            # pool with the switch off - and it is checked here anyway, because the
            # switch is a promise and a promise enforced in one place only is a
            # promise that a future caller can walk around.
            raise ValueError("focus.py: naming is off; refusing a line with a name "
                             "in it")
        if named and not str(fields.get("label") or "").strip():
            raise ValueError("focus.py: refusing a naming line with nothing to name")
        self.seq += 1
        self.say.append({"seq": self.seq, "kind": kind,
                         "text": template.format(**fields)})
        if named:
            self._named_seqs.add(self.seq)
            self._named_until = time.monotonic() + LABEL_LINE_TTL_S
        del self.say[:-12]
        if self._named_seqs:
            # The twelve-line window may already have carried a named line out. Keep
            # the scrub list to what is actually in the queue rather than growing a
            # list of seqs forever.
            self._named_seqs &= set(line["seq"] for line in self.say)

    def _note(self, key, **fields):
        self._emit(LINES[key], "note", **fields)

    def _forget_names(self, now=None, force=False):
        """Take every line that NAMED something out of the queue.

        This is the other half of the privacy law, and the reason the promise can be
        "never written down" rather than "written down briefly". The queue is not a
        transcript, it is a delivery buffer: the client speaks any line whose seq it
        has not spoken yet, which takes one tick, and the twelve-line window would
        otherwise keep the sentence - and therefore the name - sitting in every /focus
        response for the next twelve lines and in the state of a paused session for as
        long as it stays paused.

        So a named line gets LABEL_LINE_TTL_S, several times what delivery needs and
        far less than a record, and then it is gone from the queue as though it had
        only ever been a sound. Called at the top of every tick, and forced when a
        session ends, because an ended session never ticks again.
        """
        if not self._named_seqs:
            return
        if not force and (now or time.monotonic()) < self._named_until:
            return
        self.say = [line for line in self.say
                    if line["seq"] not in self._named_seqs]
        self._named_seqs = set()
        self._named_until = 0.0

    # -- the clock ---------------------------------------------------------

    @property
    def remaining_s(self):
        return max(0.0, self.planned_s - self.elapsed_s)

    @property
    def clean_pct(self):
        counted = self.on_target_s + self.drift_s
        if counted <= 0:
            return 100
        return int(round(100.0 * self.on_target_s / counted))

    def note_home_hint(self):
        """A tab telling us it currently has keyboard focus. It is a boolean about
        this page, never a claim about any other, and it expires in seconds - so a
        tab that goes away cannot leave a permanent excuse behind."""
        self._home_hint_at = time.monotonic()

    def drop_home_hint(self):
        """The tab saying it has just LOST the keyboard. Only a tab may retract its
        own claim, which is why this takes no argument and names no one."""
        self._home_hint_at = 0.0

    def _home_hint_fresh(self, now):
        return (now - self._home_hint_at) < HOME_HINT_TTL_S

    def tick(self):
        now = time.monotonic()
        # First, before anything else can happen: a line that named a place has had
        # its tick, so it stops existing. Ahead of the paused return on purpose - a
        # session paused mid-drift still ticks, and that is precisely the case where
        # the sentence would otherwise sit in the state indefinitely.
        self._forget_names(now)
        dt = max(0.0, min(now - self.last_tick, TICK_S * 5))
        self.last_tick = now
        if self.state in ("ended", "paused"):
            return
        self.elapsed_s += dt

        if self.state == "arming":
            return self._tick_arming(now)

        verdict = self.reader.look()
        self.readable = bool(verdict["readable"])
        self.tab_readable = bool(verdict["tab_readable"])
        self.tab_watched = self.reader.watching_tab
        # A local, and it stays one. The name has exactly this method's lifetime and
        # the sentence it is about to be formatted into; there is no self.<anything>
        # on the other end of it.
        label = verdict.get("label")

        # HOME BASE. Two independent signals, either one is enough: the tab saying
        # it has focus, and the reader seeing home base's own host. Coming back to
        # talk to me is never a drift - it is the one place that is neither work
        # nor wandering, so it is counted in its own bucket and in neither total.
        at_home = self._home_hint_fresh(now) or bool(verdict["home"])
        self._at_home_now = at_home

        # THE EYES, and they are consulted before everything below on purpose.
        #
        # A phone in your lap is not rescued by the fact that the window in front of
        # you is the right one - that is precisely the drift no window reader can see,
        # and the reason this organ exists. It is not rescued by home base either: you
        # are not talking to me, you are looking down. And it counts even when the
        # windows cannot be read at all, because the eyes are the evidence here and
        # they can see perfectly well while the reader is blind.
        if EYE_PHONE_DRIFTS and EYES.posture(now)["head_down"]:
            self._on_target_now = False
            self._at_home_now = False
            return self._off_target(now, dt, kind="phone")

        if not self.readable:
            # Blind. Keeping time is still worth doing; accusing you is not. And it
            # is not counted as on target either - a watchdog that cannot see and
            # assumes the best is worse than no watchdog at all.
            self.unknown_s += dt
            self._end_excursion(now, refund=False)
            self._on_target_now = False
            return self._maybe_finish()

        if at_home or verdict["on_target"]:
            # THE WATCHER'S HALF, and it is asked HERE - after home base and after the
            # window reader have both said they are content - because it is the only
            # organ that can see the drift neither of them can: same machine, same
            # browser, same window, wrong tab. Two tabs of the same host read as the
            # same surface to the reader, which is correct for the reader and is exactly
            # the hole this closes.
            #
            # Home base outranks it, as it outranks everything: talking to me is not a
            # drift. And a drift the reader has already caught never reaches this line,
            # so no excursion is counted twice.
            if not at_home and self._tab_drifted(now):
                self._on_target_now = False
                return self._off_target(now, dt, kind="locked")
            self._on_target_now = bool(verdict["on_target"]) and not at_home
            if at_home and not verdict["on_target"]:
                self.home_s += dt
            else:
                self.on_target_s += dt
            self._end_excursion(now, refund=False)
            return self._maybe_finish()

        # Off target.
        self._on_target_now = False
        return self._off_target(now, dt, label=label)

    def _off_target(self, now, dt, label=None, kind="tab"):
        """One excursion, of either kind, from its first tick to its last.

        Both kinds of drift come through here and are counted identically, which is the
        whole of "the eyes feed the focus session": there is no second set of books for
        the posture, no separate counter, and nothing the report card has to be taught.
        The kind decides two things and no others - the grace it is allowed and the pool
        it is spoken from.
        """
        if self._off_since is None:
            self._off_since = now
            self._off_kind = kind
            self._counted = False
            self._excursion_s = 0.0
        off_for = now - self._off_since

        # An excuse takes the WHOLE excursion off the books, not just the part
        # already served. Charging for the remainder would make "it's okay, I'm
        # doing research" a refund with a subscription attached.
        if self.excused:
            self.excused_s += dt
            return self._maybe_finish()

        if not self._counted:
            # GRACE. Alt-tabbing through three windows to reach the right one is
            # not a drift, and treating it as one would make the count useless.
            #
            # A posture drift has ALREADY served its grace, in the page, for the whole
            # EYE_SUSTAIN_MS it had to hold before it was reported at all. Charging it a
            # second wait here would be charging it twice for the same patience, and it
            # would put the nudge the wrong side of a second.
            if off_for * 1000.0 < self._grace_ms():
                return self._maybe_finish()
            self._counted = True
            self.drifts += 1
            self._next_nag = now + self.nag_s
            if not self.excused and self._may_speak(now):
                self._callout(self._callout_pool(label), "callout", label=label)
            # AND IF IT IS THE SECOND ONE OFF THE LOCKED TAB, soon after the first, the
            # narrating stops and something is offered instead. After the callout, in
            # this order: the fact first, then the question about it.
            if self._off_kind == "locked":
                self._after_locked_drift(now)

        self.drift_s += dt
        self._excursion_s += dt
        if self._next_nag is not None and now >= self._next_nag:
            self._next_nag = now + self.nag_s
            if not self.excused and now >= self.snooze_until and self._may_speak(now):
                self._callout(NAGS[self.tier], "nag")
        return self._maybe_finish()

    def _grace_ms(self):
        # A LOCKED-TAB drift has already served its grace, in the watcher, for the whole
        # LOCK_GRACE_MS it had to stay off before drifted() would admit it - exactly as a
        # posture drift serves its grace in the page. Charging DRIFT_GRACE_MS again here
        # would be charging twice for the same patience, and it would put the callout the
        # wrong side of the second and a half the mandate allows for noticing.
        return 0.0 if self._off_kind in ("phone", "locked") else DRIFT_GRACE_MS

    def _may_speak(self, now):
        """Is this excursion allowed a word at this instant?

        A tab drift: always - the session's own cadence governs it. A posture drift:
        only through the eyes' cooldown, so the organ that can nudge you every second
        of the day cannot. Spending the cooldown is deliberately the LAST thing that
        happens, after every other refusal, because a nudge that was never said should
        not cost you the thirty seconds of quiet after it.
        """
        if self._off_kind != "phone":
            return True
        if now < self.snooze_until:
            return False
        if not EYES.may_nudge(now):
            return False
        EYES.spend(now)
        return True

    def note_posture(self, now=None):
        """The eyes have just reported a sustained head-down posture.

        Spoken about HERE rather than at the next tick, and that is the difference
        between meeting "nudged inside a second" and missing it by half: the page has
        already held the posture for EYE_SUSTAIN_MS, and waiting up to a full second
        more for the heartbeat would spend the rest of the budget on a sleep.
        """
        now = time.monotonic() if now is None else now
        if self.state != "running" or not EYE_PHONE_DRIFTS:
            return None
        if not EYES.posture(now)["head_down"]:
            return None
        self._on_target_now = False
        self._at_home_now = False
        # dt is zero: no time has passed since the last tick that this call may charge
        # anywhere. It is here to count the drift and say the line, not to keep time.
        return self._off_target(now, 0.0, kind="phone")

    def relief(self, seconds=RELIEF_S):
        """EVERY nudge off for three minutes - the session's and the eyes' alike.

        It is a snooze with the eyes included, and it is honest about the bargain: the
        clock carries on counting, so the silence costs you the minutes it covers. A
        valve that also stopped the clock would not be a relief valve, it would be a
        way of never finishing anything.
        """
        seconds = max(1.0, float(seconds))
        self.snooze_until = time.monotonic() + seconds
        EYES.hush(seconds)
        self._note("relief", span=_spoken_span(seconds))
        return None

    def _tick_arming(self, now):
        """The DEFERRED lock. Nothing is watched while this returns.

        The rule this enforces is one sentence long: the target is the first surface
        that is not home base and that you are still on a tick later. Everything else
        here is a way of refusing to guess.

          - at home base, nothing settles. The FOCUS button lives in the Jarvis tab,
            so the surface in front of you at the click is the one surface you are
            guaranteed to leave; locking it would make your real work read as a drift
            within seconds of starting.
          - unreadable, nothing settles. A read that fails at the click moment - the
            viewer's own 3D boot can stall the browser's scripting for a few seconds -
            is a reason to wait, not a reason to lock whatever answered first.
          - one tick is not enough. Alt-tabbing past a window on the way to the right
            one must not become the thing you are held to for half an hour.
          - and after DEFER_APP_ONLY_S of never leaving this page, it stops waiting
            and watches the APPLICATION only. A wrong tab lock is worse than no tab
            lock, so the half that could be wrong is the half that is dropped.
        """
        waited = now - self._arm_since

        # The tab's own claim outranks the reader here. On a machine with no readable
        # URL it is the ONLY way to know you are still talking to me, and without it
        # this would settle on the browser two ticks after the click - app-level, but
        # decided while you were still reading the start line.
        if self._home_hint_fresh(now):
            self.reader.forget_candidate()
            self._at_home_now = True
            if waited < DEFER_APP_ONLY_S:
                return None
            return self._give_up_on_the_tab(waited)

        step = self.reader.settle()
        self.readable = bool(step["readable"])
        self._at_home_now = bool(step["home"])

        if step["settled"]:
            self.state = "running"
            self.tab_watched = bool(step.get("tab"))
            self.tab_readable = bool(step.get("tab_readable"))
            # THE TEETH GO ON HERE, before the line is spoken, so that "Locked on, sir."
            # and the card underneath it are describing the same thing. No hand is
            # offered on this path: the start line already said whether this machine can
            # lock a tab at all, and proposing a browser restart forty-five seconds into
            # a session nobody asked about would be an interruption dressed as a service.
            self._attach_watch()
            # Four words, and they are the point: a wrong lock has to be AUDIBLE at
            # the moment it happens, not inferred from a callout three minutes later.
            self._note("settled")
            if step.get("browser") and not step.get("tab"):
                self._note("notab")
            return None

        if waited < DEFER_APP_ONLY_S:
            return None

        # Long enough. Either it was never readable, or every candidate kept moving.
        if not step["readable"]:
            self.state = "running"
            self.readable = False
            self._note("unreadable")
            return None
        return self._give_up_on_the_tab(waited)

    def _give_up_on_the_tab(self, waited):
        """DEFER_APP_ONLY_S has passed with nothing settling. Watch the application
        in front of you and stop pretending there is a site to watch."""
        info = self.reader.settle_app_only()
        self.state = "running"
        self.readable = bool(info["readable"])
        self.tab_watched = False
        # Giving up on the tab includes giving up the watcher. The word is left empty
        # rather than set to a reason, because this path says what happened out loud in a
        # whole sentence ("watching the application only") and a card repeating it in one
        # word would be the same news twice.
        self._release_watch("")
        self.tab_readable = bool(info.get("tab_readable"))
        if not info["locked"]:
            self._note("unreadable")
        else:
            self._note("settled_app_only", seconds=int(round(waited)))
        return None

    def retarget(self, from_card=False):
        """MOVE THE LOCK, because you said so. Three surfaces, three outcomes.

          a work tab, or any other application - lock it on the spot and say "Locked
            on, sir.". The drift in progress is forgiven SILENTLY: you are not off
            task, you are telling me what the task is, and "Back. Thank you, sir." on
            the way past would be the machine taking credit for your correction.
          this page - the one surface it cannot lock, because this is where the button
            lives. It re-arms the deferred lock and says where it will be looking.
          the card - never lets the window manager's answer be the card. A press here
            is what brought the card to the front, so the browser is asked instead;
            see _probe_front_window(). When even that cannot tell - two work windows,
            or no readable tab at all - it re-arms, which is a recovery rather than an
            apology: go to it, and it locks where you land.

        One thing it will never do is destroy a working lock over a failed read. If
        the windows cannot be read at all, it says so and changes nothing.
        """
        now = time.monotonic()
        step = self.reader.settle_here(via_browser=bool(from_card))

        if step["ok"]:
            # A paused session stays paused. Moving the lock is not resuming, and a
            # clock that restarted because you tidied up the target would be a clock
            # that punished you for it.
            if self.state != "paused":
                self.state = "running"
            self.readable = True
            self.tab_watched = bool(step["tab"])
            self.tab_readable = bool(step["tab_readable"])
            # You are demonstrably not at home base, whatever a claim from three
            # seconds ago says, and the next tick should not count you as there.
            self.drop_home_hint()
            self._at_home_now = False
            self._end_excursion(now, refund=True)
            self._on_target_now = True
            self._note("settled")
            if step["browser"] and not step["tab"]:
                self._note("notab")
            # AND THE TEETH. This is the explicit "lock this tab" - the pill, or the
            # sentence that means it - so this is the one path that may offer to relaunch
            # the browser for the port. is_browser decides whether a port is even the
            # right thing to want: a re-target onto an editor is a perfectly good lock
            # with nothing to ask for.
            self._offer_tab_lock(bool(step["browser"]))
            return None

        if step["reason"] == "unreadable" and not from_card:
            self._note("unreadable")
            return None
        self._rearm(now)
        # AND WHY IT COULD NOT BE DONE. A press that failed because Chrome has no
        # debugging port open is not a mystery to be left on a card that has gone quiet;
        # see _offer_port_after_failed_press(), which says so and offers the fix. Only
        # from the card or the sentence that means it, and only after the re-arm above has
        # finished clearing up after the old lock.
        if from_card and step["reason"] == "unreadable":
            self._offer_port_after_failed_press()
        return None

    def _rearm(self, now):
        """Back to the deferred lock: nothing watched, and it says so out loud.

        The old target is forgotten HERE rather than left running until something
        better turns up, because "I'll lock on where you land" has to be true at the
        moment it is said - and because a lock you have just asked me to move is, by
        your own account, the wrong one to be holding you to in the meantime.
        """
        self.reader.forget_target()
        # THE UNLOCK. Every watcher goes with the target and goes here, in the same
        # breath, because "I'll lock on where you land" has to be true at the moment it
        # is said - and a watcher left polling the tab you have just told me is the wrong
        # one would be the feature arguing with you.
        self._release_watch("")
        # Paused stays paused for the same reason as above; resume() sees an unlocked
        # reader and arms by itself, with the full wait in front of it.
        if self.state != "paused":
            self.state = "arming"
        self._arm_since = now
        self.tab_watched = False
        self._end_excursion(now, refund=True)
        self._note("retarget_armed")
        return None

    def _end_excursion(self, now, refund, quiet=False):
        if self._off_since is None:
            return
        was_counted, spent = self._counted, self._excursion_s
        self._off_since = None
        self._off_kind = "tab"
        self._counted = False
        self._excursion_s = 0.0
        self._next_nag = None
        # Coming back clears the excuse: it covered ONE excursion, not the rest of
        # the session. Otherwise one "it's fine" would buy permanent silence.
        was_excused, self.excused = self.excused, False
        self.snooze_until = 0.0
        if refund and was_counted:
            self.drifts = max(0, self.drifts - 1)
            self.drift_s = max(0.0, self.drift_s - spent)
        elif was_counted and not was_excused and not quiet:
            if spent >= 20:
                self._note("back_long", seconds=int(round(spent)))
            else:
                self._note("back")

    # -- the locked tab ----------------------------------------------------

    def _tab_drifted(self, now):
        """Has the watcher decided you are off the locked tab? Read only, and cheap.

        The POLL happens on the manager's thread at LOCK_POLL_S, not here: the tick is
        the thing that must not block, and a question that costs a socket has no business
        in the middle of a countdown. This reads the answer the watcher already has.
        """
        watch = self.watch
        if watch is None or not watch.live:
            return False
        if watch.state == "gone":
            self._lose_the_locked_tab()
            return False
        return watch.drifted(now)

    def _lose_the_locked_tab(self):
        """The tab was closed, or navigated out from under the lock. Say so, once.

        Degrading to the application is the right thing to do and saying nothing about it
        is not: from here on the session is watching something weaker than it promised,
        and a card that went on reading LOCKED while that was true would be the exact
        silence this Part exists to remove.
        """
        self._release_watch("gone")
        self._note("lock_gone")
        return None

    def _release_watch(self, why=None):
        """Stop watching a tab. Every unlock path in this class ends up here.

        why=None leaves the card's word alone (a re-target is about to set it); a word
        out of TAB_LOCK_WHY replaces it. Anything else becomes "", because a call site
        that invented a reason should get silence rather than a wire full of prose.
        """
        watch, self.watch = self.watch, None
        if watch is not None:
            watch.release()
        if why is not None:
            self.tab_lock_why = why if why in TAB_LOCK_WHY else ""
        return None

    def _attach_watch(self):
        """Point a watcher at the tab this session is now holding you to.

        Called only where a lock is actually taken - the deferred settle, and an explicit
        re-target - and it asks the browser itself rather than being handed a target by
        anybody. Every refusal leaves a WORD behind for the card, so that "tab-level
        locking is off" is never a thing the boss has to deduce from a missing line.
        """
        self._release_watch("")
        if not capability()["cdp"]:
            # No endpoint at all. Said as a word here; whether it is also OFFERED as a
            # hand is _offer_tab_lock()'s business, because only an explicit "lock this
            # tab" earns an offer to restart the browser.
            self.tab_lock_why = "noport"
            return None
        if not self.reader.watching_tab:
            # An application-level lock, by the machine or by the 45-second fallback.
            # There is no tab to watch and nothing to explain that the spoken line
            # ("watching the application only") has not already said.
            return None
        found, alive, ambiguous = _cdp_front_target()
        if not alive:
            self.tab_lock_why = "noport"
            return None
        if ambiguous:
            self.tab_lock_why = "ambiguous"
            return None
        if found is None:
            self.tab_lock_why = "unreadable"
            return None
        if not self.reader.confirms_host(found["host"]):
            # The browser's front tab and the reader's target are not the same surface.
            # It happens when the window manager and the browser were read a moment
            # apart, and the honest answer is to watch nothing rather than to watch a tab
            # the session is not actually holding you to.
            self.tab_lock_why = "ambiguous"
            return None
        self.watch = LockWatch(found["port"], found["id"], found["ws"], found["title"])
        self.tab_lock_why = ""
        return None

    def _offer_tab_lock(self, is_browser):
        """You asked for a tab lock. Take it, or say why not and offer to fix it.

        The offer is made ONLY when the surface you locked is a browser: a re-target onto
        VS Code has no tab to lock and no use for a debugging port, and proposing to
        restart Chrome at that moment would be an assistant answering a question nobody
        asked. Once per session either way - a gate that asks twice is a gate that gets
        ignored on both occasions.
        """
        self._attach_watch()
        if self.watch is not None or not is_browser:
            return None
        if self.tab_lock_why != "noport":
            return None
        return self._ask_for_the_port()

    def _ask_for_the_port(self):
        """Say that the debugging port is missing and, once, offer the hand that opens it.

        Both callers arrive here having already set tab_lock_why to "noport": the press
        that locked a browser it cannot read tabs out of, and the press that could not
        read the browser at all. Once per session either way - a gate that asks twice is
        a gate that gets ignored on both occasions - so the flag is set before the asking
        and never cleared.
        """
        if self._relaunch_asked:
            return None
        self._relaunch_asked = True
        self._note("lock_noport")
        if not _ask_hand("relaunch_chrome"):
            # Nothing to say yes to - no gate wired up, or it is already holding a
            # proposal. Either way the honest thing is the plain sentence, not a question
            # the boss cannot answer.
            self.tab_lock_why = "declined"
            self._note("lock_declined")
            return None
        self._ask("ask_relaunch")
        return None

    def _offer_port_after_failed_press(self):
        """THE PORTLESS PRESS, which is the case the card used to swallow whole.

        You pressed LOCK THIS TAB in a Chrome started without --remote-debugging-port.
        The read that would have named the tab could not even be attempted - there is no
        endpoint to ask - so settle_here() reported "unreadable" and the session re-armed.
        That much is correct and stays. What was missing is the REASON, and a card that
        simply goes quiet while the one thing you pressed it for silently does not happen
        is the whole of what this Part exists to remove.

        Called AFTER _rearm(), because _rearm() releases the watcher and clears the card's
        word on its way past: setting the word first would be writing it into a puddle.
        """
        if capability()["cdp"]:
            return None        # a port does exist; that read failed for another reason
        front = _probe_raw()
        if not front or not front["browser"]:
            # Not a browser in front. There is no tab to lock here and nothing a debugging
            # port would have fixed, so there is nothing to offer and nothing to explain.
            return None
        self.tab_lock_why = "noport"
        return self._ask_for_the_port()

    def decline_tab_lock(self):
        """He said no to the relaunch. The card stops asking and says why."""
        if self.watch is not None:
            return None
        self.tab_lock_why = "declined"
        self._note("lock_declined")
        return None

    def _after_locked_drift(self, now):
        """A second drift off the locked tab, soon after the first: offer to fix it.

        The first drift is absent-mindedness and gets a sentence. A second one inside
        SUMMON_WITHIN_S is a pull - something over there is winning - and at that point
        another sentence is just the same sentence again. So the assistant stops
        narrating and offers to do something, through the same gate as every other hand.

        Never oftener than twice the window, which is the difference between a watchdog
        and a man shouting the same question at you.
        """
        last, self._lock_drift_at = self._lock_drift_at, now
        if not last or (now - last) > SUMMON_WITHIN_S:
            return None
        if self._summon_at and (now - self._summon_at) < SUMMON_WITHIN_S * 2:
            return None
        self._summon_at = now
        if not _ask_hand("summon_tab"):
            return None
        self._ask("ask_summon")
        return None

    def note_summoned(self):
        """The summon worked and the boss is back on the locked tab.

        The drift is NOT refunded: it happened, he was away, and a rescue that also
        cleaned the record would make the sparkline a record of how often he accepted
        help rather than of how the session went. Quiet, because the hand is about to say
        its own sentence and "Back. Thank you, sir." on top of it would be two lines
        fighting over one moment.
        """
        self._end_excursion(time.monotonic(), refund=False, quiet=True)
        self._on_target_now = True
        return None

    def _ask(self, key):
        """A line with a Yes and a No behind it, through the one gate as always."""
        self._emit(LINES[key], "ask")
        return None

    def _callout_pool(self, label=None):
        """Which pool this callout comes out of. Two questions, in order.

        Can it be NAMED? Only if the reader handed up a name this tick, which it does
        only for a readable drift and only with NAME_DRIFTS on. Every pool below has a
        named and a nameless twin, so the answer decides the column and never the row.

        Are your own words still available? Only for the FIRST callout of a session: a
        line that quotes your sentence back at you five times stops being a callout and
        starts being a parrot, and only when the phrase is short enough to belong in a
        sentence - see spoken_intent(). Drill mode skips it, because you asked for the
        blunt instrument and the intent line is the precise one.
        """
        # THE EYES' OWN POOL, and it is decided before anything else because a posture
        # cannot be named and your own words are the wrong instrument for it: "that is
        # not the invoice importer" is a strange thing to say to a man looking at his
        # lap. Tiers and the register still apply, so a posture drift escalates exactly
        # like a tab drift and answers to "be harsher with me" the same way.
        if self._off_kind == "phone":
            return CALLOUTS_PHONE_DRILL if self.drill else CALLOUTS_PHONE[self.tier]
        # THE LOCKED TAB, and it keeps its own pool in BOTH registers rather than
        # deferring to the drill sergeant's. The drill pools are blunt and general -
        # "back to work" - and this pool's whole value is the fact in it: you left the
        # one tab you asked to be held to. Tiers still escalate, so "be harsher with me"
        # is still answered; it is answered with sharper sentences about the right thing.
        if self._off_kind == "locked":
            return CALLOUTS_LOCKED[self.tier]
        named = bool(label) and NAME_DRIFTS
        if self.drill:
            return CALLOUTS_DRILL_NAMED if named else CALLOUTS_DRILL
        if not self._intent_used and self.tier == 1 and spoken_intent(self.intent):
            return CALLOUTS_INTENT_NAMED if named else CALLOUTS_INTENT
        return (CALLOUTS_NAMED if named else CALLOUTS)[self.tier]

    def _callout(self, pool, kind, label=None):
        if time.monotonic() < self.snooze_until:
            return
        # Marked used only once it is actually going to be said. A snoozed callout
        # that spent the intent would leave the sharpest line unheard and unavailable.
        if pool is CALLOUTS_INTENT or pool is CALLOUTS_INTENT_NAMED:
            self._intent_used = True
        template = random.choice(pool)
        # Every field every pool might want, computed for all of them: a template
        # takes what it needs and format() ignores the rest, which is what keeps the
        # pools pure text that a reader can check at a glance. `label` is the only one
        # derived from an identity, and passing "" when there is none is what makes
        # _emit()'s refusal of a nameless naming line a real gate.
        self._emit(template, kind, drifts=self.drifts,
                   intent=spoken_intent(self.intent),
                   seconds=int(round(self._excursion_s)),
                   label=label or "",
                   times=_times_word(self.drifts),
                   times_cap=_times_word(self.drifts).capitalize(),
                   nth=_nth_word(self.drifts),
                   nth_cap=_nth_word(self.drifts).capitalize())

    @property
    def tier(self):
        if self.drifts >= TIER3_AFTER_DRIFTS:
            return 3
        if self.drifts >= TIER2_AFTER_DRIFTS:
            return 2
        return 1

    def _maybe_finish(self):
        if self.elapsed_s >= self.planned_s:
            self.finish("finished")
        return None

    # -- commands ----------------------------------------------------------

    def pause(self):
        if self.state == "paused":
            return None
        self.state = "paused"
        self._end_excursion(time.monotonic(), refund=False)
        self._note("paused")
        return None

    def resume(self):
        if self.state != "paused":
            return None
        self.state = "running" if self.reader.locked else "arming"
        self.last_tick = time.monotonic()
        if self.state == "arming":
            self._arm_since = self.last_tick      # the wait starts again, in full
        self._note("resumed", remaining=_spoken_span(self.remaining_s))
        return None

    def extend(self, minutes):
        minutes = max(1, min(EXTEND_MAX_MIN, int(minutes)))
        self.planned_s += minutes * 60.0
        if self.state == "ended":
            self.state = "running" if self.reader.locked else "arming"
            self.ended_reason = None
            self.report = ""
            if self.state == "arming":
                self._arm_since = time.monotonic()
        self._note("extended", minutes=minutes,
                   remaining=_spoken_span(self.remaining_s))
        return None

    def snooze(self, seconds):
        seconds = max(1.0, min(SNOOZE_MAX_S, float(seconds)))
        self.snooze_until = time.monotonic() + seconds
        self._note("snoozed", seconds=int(seconds))
        return None

    def set_nag(self, seconds):
        self.nag_s = max(NAG_MIN_S, min(NAG_MAX_S, float(seconds)))
        if self._next_nag is not None:
            self._next_nag = time.monotonic() + self.nag_s
        self._note("nag_set", seconds=int(self.nag_s))
        return None

    def set_drill(self, on):
        """The register, and it is yours to set. Both ways, by voice, mid-session.

        Nothing else changes: the same drifts are counted the same way and the ledger
        cannot tell afterwards which register they were counted in. This is a choice
        about how you are spoken to, not about what is true.
        """
        self.drill = bool(on)
        self._note("drill_on" if self.drill else "drill_off")
        return None

    def excuse(self):
        """Refunds the CURRENT excursion and goes quiet until you are back. Not a
        pardon for the session: _end_excursion clears it the moment you return."""
        if self._off_since is None:
            self._note("excused_ontarget")
            return None
        spent, was_counted = self._excursion_s, self._counted
        if was_counted:
            self.drifts = max(0, self.drifts - 1)
            self.drift_s = max(0.0, self.drift_s - spent)
        self._excursion_s = 0.0
        self._counted = True          # already accounted for; do not re-count it
        self.excused = True
        self._next_nag = None
        self._note("excused")
        return None

    def nudge(self, pool):
        """A posture nudge that is NOT a drift - a slouch, or an empty chair.

        It goes into the say queue so that every open tab speaks it once and none of
        them speaks it twice, and it touches no counter at all: nothing about your spine
        belongs on the report card, and a clean percentage that could be spent on
        sitting badly would be measuring the wrong thing entirely.
        """
        self._emit(random.choice(pool), "nudge")
        return None

    def status(self):
        self._note("status", remaining=_spoken_span(self.remaining_s),
                   ontarget=_spoken_span(self.on_target_s),
                   drifts=_spoken_drifts(self.drifts))
        return None

    def abort(self):
        self.state = "ended"
        self.ended_reason = "aborted"
        self.report = ""
        # The watcher dies with the session, here rather than at the next tick, because
        # an ended session never ticks again - the same reason the name scrub is forced
        # below. "Nothing recorded" has to include "nothing still watching".
        self._release_watch("")
        # An ended session never ticks again, so the scrub that would have happened on
        # the next tick happens here instead. "Nothing recorded" has to include the
        # sentence that named the place you were when you gave up.
        self._forget_names(force=True)
        self._note("aborted")
        return None

    def finish(self, reason="ended-early"):
        if self.state == "ended":
            return None
        self.state = "ended"
        self.ended_reason = reason
        self._release_watch("")          # same reason as abort(): nothing left watching
        # Before the report card is built, for the same reason as in abort(): the last
        # thing in the queue of a finished session is the summary, and the summary has
        # never named anywhere and is not about to start now.
        self._forget_names(force=True)
        # quiet: "Back. Thank you, sir." immediately before the report card would be
        # two lines fighting over the same moment.
        self._end_excursion(time.monotonic(), refund=False, quiet=True)
        streak_line = self._record()
        # The card names the work when you told me what it was and the phrase is short
        # enough to belong in a sentence. Otherwise the plain card: a report that
        # recites your own dictated paragraph back at you is not a summary.
        said = spoken_intent(self.intent)
        template = LINES["report_intent"] if said else LINES["report"]
        fields = {"ontarget": _spoken_span(self.on_target_s),
                  "planned": _spoken_span(self.planned_s),
                  "drifts": _spoken_drifts(self.drifts),
                  "clean": self.clean_pct, "streak": streak_line, "intent": said}
        self.report = template.format(**fields)
        self._emit(template, "report", **fields)
        return None

    def _record(self):
        """Update the ledger and return the one sentence about the streak."""
        book = read_ledger()
        if self.elapsed_s < MIN_LEDGER_S:
            return LINES["streak_none"] if not book["streak"] else \
                LINES["streak_up"].format(streak=book["streak"])
        clean = self.clean_pct >= int(CLEAN_RATIO * 100)
        before = int(book["streak"])
        book["sessions"] += 1
        book["plannedMinutes"] += int(round(self.planned_s / 60.0))
        book["onTargetMinutes"] += int(round(self.on_target_s / 60.0))
        book["driftMinutes"] += int(round(self.drift_s / 60.0))
        book["drifts"] += int(self.drifts)
        # THE ROW. Built from the eight whitelisted keys and handed to session_row()
        # anyway, so this call site is not the thing standing between the file and a
        # ninth field - there is nowhere for one to go.
        book["history"] = list(book.get("history") or [])
        book["history"].append(session_row({
            "at": time.strftime("%Y-%m-%d %H:%M"),
            "plannedMinutes": round(self.planned_s / 60.0),
            "activeMinutes": round(self.elapsed_s / 60.0),
            "onTargetMinutes": round(self.on_target_s / 60.0),
            "drifts": self.drifts,
            "secondsAdrift": round(self.drift_s),
            "percent": self.clean_pct,
            # The clock ran out, rather than you stopping it. Not the same question as
            # whether the session was clean, and worth keeping apart from it: a
            # half-hour abandoned at minute four is not a bad session, it is an
            # interrupted one.
            "completed": self.ended_reason == "finished",
        }))
        book["history"] = book["history"][-LEDGER_HISTORY_MAX:]
        if clean:
            book["cleanSessions"] += 1
            book["streak"] = before + 1
            book["bestStreak"] = max(int(book["bestStreak"]), book["streak"])
        else:
            book["streak"] = 0
        book["updated"] = time.strftime("%Y-%m-%d")
        try:
            _write_ledger(book)
        except Exception:                                      # noqa: BLE001
            pass                       # a ledger that cannot be written is not
        if clean:                      # a reason to lose the report card
            return (LINES["streak_up"].format(streak=book["streak"]) if before
                    else LINES["streak_new"])
        return (LINES["streak_broken"].format(streak=before) if before
                else LINES["streak_none"])


# =============================================================================
#  THE MANAGER - one session, one tick thread, one lock
# =============================================================================

class FocusManager:
    def __init__(self):
        self._lock = threading.RLock()
        self._session = None
        self._thread = None
        self._version = 0
        # THE PULSE, for the instrument. A tick thread that died, or one wedged inside
        # a probe that never came back, looks from the outside exactly like a feature
        # that does not work - and the difference is not discoverable by reading the
        # code, only by asking the process that is running it. So the loop stamps
        # itself, every second, whether or not there is a session to tick.
        self._born = time.monotonic()
        self._tick_at = 0.0
        self._ticks = 0

    # -- the tick ----------------------------------------------------------

    def _ensure_thread(self):
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._loop, name="focus-tick",
                                        daemon=True)
        self._thread.start()

    def _loop(self):
        """One second, forever, independent of every browser tab in existence.
        This is why a reload rejoins a session instead of restarting one.

        TWO CADENCES, and only one of them is the tick. The countdown still beats once a
        second and nothing about that has changed. But a locked TAB cannot be watched at
        one hertz and still be noticed inside the second and a half the mandate allows -
        so while a watcher is live this thread wakes every LOCK_POLL_S, asks the tab one
        question, and forces a tick early the moment the answer CHANGES. A poll that finds
        the same answer as last time is not news and costs a millisecond.

        The poll happens OUTSIDE the lock. It opens a socket and waits on a browser, and
        holding the session lock across that would make every /focus request queue behind
        the watchdog - a freeze caused by the organ that exists to catch freezes.
        """
        next_tick = time.monotonic() + TICK_S
        while True:
            watch = self._watch()
            due = max(0.0, next_tick - time.monotonic())
            flipped = False
            if watch is None:
                time.sleep(due if due else TICK_S)
            else:
                time.sleep(min(LOCK_POLL_S, due) if due else 0.0)
                was = watch.state
                watch.poll()
                # A verdict that CHANGED is worth a tick now: leaving the tab, and coming
                # back to it, are both things the boss should hear about before the next
                # second boundary rather than after it.
                flipped = watch.state != was
            now = time.monotonic()
            if now < next_tick and not flipped:
                continue
            if now >= next_tick:
                next_tick = now + TICK_S
            self._beat()

    def _watch(self):
        """The live LockWatch, or None. Only a RUNNING session is watched: a paused one is
        not being held to anything, and polling a tab through a pause would count a drift
        against a clock that is deliberately not running."""
        with self._lock:
            session = self._session
            if session is None or session.state != "running":
                return None
            watch = session.watch
            return watch if (watch is not None and watch.live) else None

    def _beat(self):
        """One tick of the session, and one stamp of the pulse."""
        with self._lock:
            # Stamped before the early return, because this is a fact about the
            # THREAD and not about the session: "no session" must read as a quiet
            # heartbeat, not as a freeze.
            self._tick_at = time.monotonic()
            self._ticks += 1
            session = self._session
            if session is None or session.state == "ended":
                return
            # len(say) is in here for one reason: the SCRUB. A tick that takes a
            # named line out of the queue adds no seq and changes no state, so
            # without this the stream would not push and every connected tab would
            # go on holding the sentence that named a place long after the server
            # had dropped it. A shorter queue is a change worth sending.
            before = (session.seq, session.state, len(session.say))
            try:
                session.tick()
            except Exception:                                  # noqa: BLE001
                # A reader that throws must not take the countdown with it.
                session.readable = False
            if before != (session.seq, session.state, len(session.say)):
                self._version += 1

    # -- commands ----------------------------------------------------------

    def command(self, cmd, minutes=None, seconds=None, text=None, source=None):
        """(spoken_reply, state). Every route into a session goes through here.

        `source` matters for exactly one command: a re-target that came from the card
        has to be read differently from one that was spoken, because the press itself
        changed what is in front. It is a flag about where the instruction came from,
        never about where you are.
        """
        with self._lock:
            session = self._session
            if cmd == "start":
                if session is not None and session.state != "ended":
                    return LINES["already"].format(
                        remaining=_spoken_span(session.remaining_s)), self._state()
                self._session = FocusSession(minutes or DEFAULT_MINUTES,
                                             seq0=session.seq if session else 0)
                self._version += 1
                self._ensure_thread()
                return self._drain(), self._state()

            # THE RELIEF VALVE, and the one command that works with no session in
            # sight. The eyes nudge whether or not a clock is running, so the sentence
            # that silences them must not need one either - "no Jarvis, I need to do
            # something important" is not a remark about a timer.
            if cmd == "relief":
                if session is not None and session.state != "ended":
                    session.relief(RELIEF_S)
                    self._version += 1
                    return self._drain(), self._state()
                EYES.hush(RELIEF_S)
                self._version += 1
                return (spoken_line(LINES["relief"],
                                    span=_spoken_span(RELIEF_S)), self._state())

            if session is None or (session.state == "ended" and cmd != "extend"):
                return LINES["none"], self._state()

            if cmd == "pause":
                session.pause()
            elif cmd == "resume":
                session.resume()
            elif cmd == "extend":
                session.extend(minutes or EXTEND_DEFAULT_MIN)
                self._ensure_thread()
            elif cmd == "snooze":
                session.snooze(seconds or SNOOZE_DEFAULT_S)
            elif cmd == "nag":
                session.set_nag(seconds or NAG_DEFAULT_S)
            elif cmd == "drill":
                session.set_drill(True)
            elif cmd == "gentle":
                session.set_drill(False)
            elif cmd == "excuse":
                session.excuse()
            elif cmd == "retarget":
                session.retarget(from_card=(str(source or "") == "card"))
            elif cmd == "intent":
                # An answer with nothing in it is not an error and not worth a line:
                # you were asked a question and you did not answer it, which is
                # allowed. The session carries on with the duller callouts.
                if not session.set_intent(text):
                    return None, self._state()
            elif cmd == "status":
                session.status()
            elif cmd == "abort":
                session.abort()
            elif cmd == "finish":
                session.finish("ended-early")
            else:
                return None, self._state()
            self._version += 1
            return self._drain(), self._state()

    # -- the locked tab ----------------------------------------------------

    def summon(self):
        """(line, summoned, state). Bring the boss back to the tab he locked.

        Reached from exactly one place - tools/summon_tab.py, which posts
        {"cmd": "summon"} to the loopback /focus after the boss said yes at the gate.
        The hand carries NO parameters, which is the point: the identity of the locked tab
        lives in this session and nowhere else, so there is no id for anybody to substitute
        and no way to point this at an arbitrary tab in the browser.

        The line comes back in the REPLY and is deliberately not queued - handle() reports
        viaSession false for it - because the hand's stdout is the evidence the assistant
        speaks, and the same sentence arriving twice from two directions is how a careful
        feature starts sounding broken.
        """
        with self._lock:
            session = self._session
            live = session is not None and session.state != "ended"
            watch = session.watch if live else None
            if watch is None or not watch.live:
                return LINES["summon_none"], False, self._state()
        # OUTSIDE THE LOCK. activate() waits up to LOCK_ACTIVATE_S for the browser to
        # actually put the tab in front - it reads the answer back off the tab rather than
        # trusting the request - and holding the tick thread out for a second to do that
        # would be exactly the freeze the pulse is there to catch.
        done = watch.activate()
        with self._lock:
            session = self._session
            if done and session is not None and session.watch is watch:
                session.note_summoned()
            self._version += 1
            return ((LINES["summoned"] if done else LINES["summon_failed"]),
                    bool(done), self._state())

    def hand_outcome(self, tool, outcome="done"):
        """(line, via_session). A proposal the FOCUS SESSION raised has been answered.

        The server calls this wherever a proposal resolves - the voice door and the button
        door alike - and it is the second half of "no silent degradation": a yes has to
        finish the job it was asked for, and a no has to be admitted on the card instead
        of leaving a feature that looks armed and is not.

        A relaunch that worked ends with the lock TAKING ITSELF: the port is up now, so the
        surface in front is read again through the browser's own account of it and locked
        properly, teeth and all. That is why the boss said yes.
        """
        tool = str(tool or "").strip().lower()
        good = str(outcome or "").strip().lower() in ("done", "ok", "yes", "success")
        if tool != "relaunch_chrome":
            # summon_tab needs nothing here: it speaks through its own stdout and its
            # refusals are already sentences. Any other tool is none of this file's
            # business at all.
            return None, False
        with self._lock:
            session = self._session
            if session is None or session.state == "ended":
                return None, False
            if good:
                # THE CACHE IS THE ONE THING THAT WOULD LIE HERE - see
                # _forget_capability(). The answer it is holding was taken before the
                # browser was relaunched.
                _forget_capability()
                # from_card, because the press that started this is what brought the
                # viewer to the front - the same reading the pill itself gets.
                session.retarget(from_card=True)
            else:
                session.decline_tab_lock()
            self._version += 1
            return self._drain(), True

    def _drain(self):
        """The lines added by the command just handled, as one spoken string."""
        session = self._session
        if session is None or not session.say:
            return None
        return session.say[-1]["text"]

    def note_home(self):
        with self._lock:
            if self._session is not None:
                self._session.note_home_hint()

    # -- the eyes ----------------------------------------------------------

    def _eyes_snapshot(self):
        """Everything about the eyes that the client can see, as a tuple, so a report
        that changed nothing does not push a frame down every open stream."""
        return (EYES.on, EYES.fresh(), EYES.present, EYES.head_down, EYES.slouched,
                EYES.hushed(), EYES.nudges)

    def note_eyes(self, cmd="posture", present=False, head_down=False,
                  slouched=False, ears=None):
        """The eyes reporting in. Returns (line_for_the_posting_tab, via_session).

        ONE NUDGER PER MOMENT, and this is where that is decided rather than in two
        places that could both decide yes. When a session is live the line goes into its
        say queue, where every open tab speaks it exactly once through the stream it
        already has. When there is no session the line comes back in this reply and the
        page that posted says it. Never both, and never neither.
        """
        now = time.monotonic()
        with self._lock:
            session = self._session
            live = session is not None and session.state in ("arming", "running")
            before = self._eyes_snapshot()

            if cmd in ("off", "blind"):
                EYES.close(now)
                self._version += 1
                return LINES["eyes_off" if cmd == "off" else "eyes_blind"], False

            if cmd == "on":
                # Present until told otherwise: the alternative is an empty-chair nudge
                # in the first second, aimed at a man who has just pressed the button.
                EYES.report(True, True, False, False, now)
                self._version += 1
                line = LINES["eyes_on"]
                # THE EAR LAW. An organ may open the conversation; it may never open the
                # microphone. So the eyes coming on with the ears off is SAID, because
                # that is the moment the rule is felt as a fault rather than a promise.
                if ears is False:
                    line += " " + LINES["ears_off"]
                return line, False

            EYES.report(True, present, head_down, slouched, now)
            post = EYES.posture(now)
            line, via, handled = None, False, False

            # HEAD DOWN, with a session watching: this is a drift and the session owns
            # it. The line, the count, the tier and the nag all come out of the same
            # machinery a tab drift uses - see _off_target().
            if (live and EYE_PHONE_DRIFTS and post["head_down"]
                    and session.state == "running"):
                seq_before = session.seq
                session.note_posture(now)
                via = session.seq > seq_before
                handled = True

            if not handled:
                # Everything else is a nudge and nothing more. A slouch is not a
                # decision about the work, and neither is an empty chair.
                pool = (CALLOUTS_PHONE[1] if post["head_down"]
                        else NUDGES_ABSENT if not post["present"]
                        else NUDGES_SLOUCH if post["slouched"]
                        else None)
                snoozed = live and now < session.snooze_until
                if pool is not None and not snoozed and EYES.may_nudge(now):
                    EYES.spend(now)
                    if live:
                        session.nudge(pool)
                        via = True
                    else:
                        line = spoken_line(random.choice(pool))

            if via or line or self._eyes_snapshot() != before:
                self._version += 1
            return line, via

    # -- state -------------------------------------------------------------

    def state(self, home=None):
        with self._lock:
            if home is not None and self._session is not None:
                if home:
                    self._session.note_home_hint()
                else:
                    self._session.drop_home_hint()
            return self._state()

    def version(self):
        with self._lock:
            return self._version

    def say_seq(self):
        """The highest say-seq in the queue, or 0 with no session.

        Read either side of a command to answer one question: did that reply go into
        the queue, where every open tab will speak it once, or is it a sentence only
        the caller has? The relief valve made that question load-bearing - it answers
        with no session in sight, so its line has no queue to travel in and the page
        that asked has to say it itself.
        """
        with self._lock:
            return self._session.seq if self._session is not None else 0

    def _state(self):
        return public_state(self._session)

    # -- the instrument ----------------------------------------------------

    def diag(self):
        """Everything /focus/diag answers, from THIS process, in DIAG_KEYS' vocabulary.

        Two-phase on purpose. The session's own facts are read under the lock, because
        a half-updated view of a countdown is worse than a slightly older one. The
        fresh foreground read is then taken OUTSIDE it, because _probe_raw() can spend
        the better part of a second on three dead CDP ports and a diagnostic that
        stalls the tick it is diagnosing is a trap rather than a tool.

        What that costs is precision no debugger needs: the reader may settle between
        the two phases, and a settle caught mid-flight is a thing worth seeing anyway.
        """
        with self._lock:
            now = time.monotonic()
            session = self._session
            live = session is not None and session.state != "ended"
            facts = {
                "pid": os.getpid(),
                "uptimeS": now - self._born,
                "tickAlive": bool(self._thread and self._thread.is_alive()),
                # Never ticked at all reads as "as stale as this process is old",
                # which is the truth and is louder than a zero.
                "tickAgeS": (now - self._tick_at) if self._tick_at else
                            (now - self._born),
                "ticks": self._ticks,
                "version": self._version,
                "sessionOn": live,
                "state": session.state if session is not None else "idle",
                "deferred": bool(session.deferred) if live else False,
                "sessionOnTarget": bool(session._on_target_now) if live else False,
                "atHome": bool(session._at_home_now) if live else False,
                "drifting": bool(live and session._counted
                                 and session.state == "running"),
                "inGrace": bool(live and session._off_since is not None
                                and not session._counted),
                "excused": bool(session.excused) if live else False,
                "snoozed": bool(live and now < session.snooze_until),
                "intentOpen": bool(session.awaiting_intent) if live else False,
                "armingS": (now - session._arm_since) if (live and session.deferred)
                           else 0,
                "settleNeeded": SETTLE_TICKS,
                # THE WATCHER. watchers is the leak detector and the reason it is an int
                # rather than a bool: "how many tabs is this process still polling" is the
                # question lock_proof.mjs asks after the session ends, and the answer has
                # to be zero. watchPolls frozen across the same interval is the second
                # half of the same assertion - a released watcher does not just report
                # itself gone, it stops asking.
                "watchers": 1 if (live and session.watch is not None
                                  and session.watch.live) else 0,
                "watchPolls": (session.watch.polls
                               if (live and session.watch is not None) else 0),
                "watchState": (session.watch.state
                               if (live and session.watch is not None
                                   and session.watch.live) else "n/a"),
            }
            reader = session.reader if session is not None else None
        # Outside the lock from here down.
        post = EYES.posture(time.monotonic())
        facts["eyesOn"] = bool(post["fresh"])
        facts["postureLane"] = ("unknown" if not post["fresh"]
                                else "off" if post["head_down"] else "on")
        cap = capability()
        facts["cdpAlive"] = bool(cap["cdp"])
        facts["backend"] = str(cap["backend"])
        # With no session there is no reader and therefore no target - and a throwaway
        # one answers the foreground half correctly while reporting an empty lock,
        # which is exactly the state of affairs.
        facts.update((reader or TargetReader()).diagnose())
        facts["appTarget"] = bool(facts["locked"] and facts["appHash"])
        facts["tabTarget"] = bool(facts["locked"] and facts["tabHash"])
        return public_diag(facts)


_BACKEND_RE = re.compile(r"^[A-Za-z0-9_]{1,24}$")


def public_diag(raw):
    """Copy through DIAG_KEYS, coerce, and enumerate every word. Same shape of
    function as public_state() and same reason for existing: the instrument is the
    first thing anybody reaches for when a feature misbehaves, so it is the first
    thing that would grow a field holding an app name at two in the morning."""
    out = {}
    for key, kind in DIAG_KEYS.items():
        value = raw.get(key)
        if kind is bool:
            out[key] = bool(value)
        elif kind is int:
            try:
                out[key] = int(round(float(value or 0)))
            except (TypeError, ValueError):
                out[key] = 0
        else:
            text = "" if value is None else str(value)
            if key in ("appLane", "tabLane", "postureLane"):
                out[key] = text if text in LANES else "unknown"
            elif key == "watchState":
                out[key] = text if text in WATCH_STATES else "n/a"
            elif key == "tabRead":
                out[key] = text if text in TAB_READS else "unknown"
            elif key == "state":
                out[key] = text if text in STATES else "idle"
            elif key == "backend":
                # A function name out of this module, and the one place a string from
                # outside could arrive: the privacy test swaps READER_BACKEND for a
                # callable of its own. An identifier or nothing.
                out[key] = text if _BACKEND_RE.match(text) else "custom"
            else:
                out[key] = text
    return out


def public_state(session):
    """Build the client's view from PUBLIC_KEYS and nothing else.

    Written as a copy through a whitelist rather than as a dict literal on
    purpose: a literal grows a field one day when somebody is debugging, and that
    field is an app name. Here the key has to be added to PUBLIC_KEYS first, which
    fails the privacy test until somebody has thought about it.
    """
    book = read_ledger()
    now = time.monotonic()
    # THE EYES live outside the session, because the camera does: it can be open with no
    # clock running, and closing a session must not silently blind the organ. So these
    # keys are filled in either way, and they are the same three booleans whether or not
    # anything is being timed.
    post = EYES.posture(now)
    eyes_raw = {
        "eyesOn": post["fresh"], "present": post["present"],
        "headDown": post["head_down"], "slouched": post["slouched"],
        "hushed": EYES.hushed(now), "hushLeftS": EYES.hush_left(now),
        "nudges": EYES.nudges,
    }
    if session is None:
        raw = {"state": "idle", "streak": book["streak"],
               "bestStreak": book["bestStreak"], "sessions": book["sessions"]}
        raw.update(eyes_raw)
    else:
        raw = {
            "state": session.state,
            "plannedS": session.planned_s,
            "elapsedS": session.elapsed_s,
            "remainingS": session.remaining_s,
            "onTargetS": session.on_target_s,
            "driftS": session.drift_s,
            "homeS": session.home_s,
            "excusedS": session.excused_s,
            "unknownS": session.unknown_s,
            "drifts": session.drifts,
            "tier": session.tier,
            "onTarget": session._on_target_now,
            "drifting": session._counted and session.state == "running",
            "inGrace": session._off_since is not None and not session._counted,
            "atHome": session._at_home_now,
            "excused": session.excused,
            "snoozed": now < session.snooze_until,
            "snoozeLeftS": max(0.0, session.snooze_until - now),
            "nagS": session.nag_s,
            "drill": session.drill,
            "appWatched": session.reader.locked,
            "tabWatched": session.tab_watched,
            "readable": session.readable,
            "locked": session.reader.locked,
            "deferred": session.deferred,
            "awaitingIntent": session.awaiting_intent,
            "intent": session.intent,
            "cleanPct": session.clean_pct,
            "streak": book["streak"],
            "bestStreak": book["bestStreak"],
            "sessions": book["sessions"],
            "endedReason": session.ended_reason,
            "report": session.report,
            "seq": session.seq,
            "say": session.say,
            # Which KIND of drift is in progress, so the card can say "head down"
            # rather than implying you are in the wrong window. Nameless either way:
            # there are two possible answers and both of them are about this app.
            "postureDrift": (session._off_kind == "phone" and session._counted
                             and session.state == "running"),
            # THE LOCKED TAB, for the card. Read straight off the live watcher rather
            # than from a copy kept beside it, so that "LOCKED: <title>" cannot outlive
            # the thing it describes by even one frame: release() empties the title, and
            # a released watcher is not this session's watcher any more either way.
            "lockedTab": (session.watch.title
                          if (session.watch is not None and session.watch.live) else ""),
            "tabLockWhy": session.tab_lock_why,
        }
        raw.update(eyes_raw)

    out = {}
    for key, kind in PUBLIC_KEYS.items():
        value = raw.get(key)
        if kind is bool:
            out[key] = bool(value)
        elif kind is int:
            try:
                out[key] = int(round(float(value or 0)))
            except (TypeError, ValueError):
                out[key] = 0
        elif kind is str:
            # Enumerated where it can be; the report and the lines are built only
            # from templates in LINE_REGISTRY, which contain no identity to leak.
            text = "" if value is None else str(value)
            if key == "state":
                out[key] = text if text in STATES else "idle"
            elif key == "endedReason":
                out[key] = text if text in END_REASONS else ""
            elif key == "tabLockWhy":
                # One word out of the fixed set or nothing at all. The enumeration is the
                # guard: it is what makes it impossible for a reason to reach the wire as
                # a sentence somebody wrote at a call site.
                out[key] = text if text in TAB_LOCK_WHY else ""
            elif key == "lockedTab":
                # Cut again HERE as well as in LockWatch, because this is the last line
                # before the wire and a bound that is only enforced at the source is a
                # bound that the next constructor forgets.
                out[key] = text[:LOCK_TITLE_CHARS]
            else:
                out[key] = text
        elif kind is list:
            lines = []
            for item in (value or []):
                if not isinstance(item, dict):
                    continue
                lines.append({"seq": int(item.get("seq") or 0),
                              "kind": str(item.get("kind") or "note"),
                              "text": str(item.get("text") or "")})
            out[key] = lines
    return out


# =============================================================================
#  WHAT YOU CAN SAY
# =============================================================================
#
# Ordered most specific first, and only START_RE is allowed to match when there is
# no session running - so "give me fifteen seconds" is a snooze during a session
# and an ordinary question to the notes brain at any other time.

_FOCUS_WORD = r"(?:focus|deep work|session|sprint|pomodoro)"
START_RE = re.compile(
    r"(?:\b(?:start|begin|kick off)\b[^.]{0,20}\b%s\b)"
    r"|(?:\b%s\b[^.]{0,24}\b(?:for|of)\b[^.]{0,20}\b(?:minutes?|mins?|hours?)\b)"
    r"|(?:\b(?:minutes?|mins?|hour|hours|half an hour|quarter of an hour)\b"
    r"[^.]{0,18}\b(?:on|of)\s+(?:this|that|it|work|focus)\b)"
    r"|(?:\blet'?s\s+do\b[^.]{0,26}\b(?:on this|on that|of %s)\b)"
    % (_FOCUS_WORD, _FOCUS_WORD, _FOCUS_WORD), re.I)

# THE RELIEF VALVE, and the ONE phrase besides a start that is allowed to match with no
# session running - because the eyes nudge with no session running. It is checked before
# the snooze on purpose: "give me a minute" is not fifteen seconds of quiet, it is a man
# telling you something has come up, and reading it as the smaller thing would be the
# app deciding how important your interruption was.
_RELIEF_RE = re.compile(
    r"\b(?:need|have)\s+to\s+do\s+something\b"
    r"|\b(?:something|anything)\s+(?:important|urgent)\b"
    r"|\bgive\s+me\s+a\s+(?:minute|moment|few\s+minutes)\b"
    r"|\bgive\s+me\s+(?:a\s+)?(?:couple|few)\s+of\s+minutes\b"
    r"|\b(?:leave|let)\s+me\s+(?:alone|be)\b"
    r"|\b(?:i'?ll|i\s+will)\s+be\s+(?:right\s+)?back\b", re.I)

_NAG_RE = re.compile(r"\b(?:call me out|nag me|tell me off|remind me|check on me)\b"
                     r"|\bevery\b[^.]{0,14}\bseconds?\b", re.I)
# THE REGISTER. Checked before the nag, because "call me out properly" is a request
# about the tone and _NAG_RE would otherwise read it as one about the cadence and
# quietly reset the timer instead.
_DRILL_RE = re.compile(r"\b(?:drill[ -]?sergeant|no mercy|tough love)\b"
                       r"|\bbe (?:harsh|harsher|brutal|blunt|savage|merciless)\b"
                       r"|\bdon'?t be (?:nice|polite|gentle|kind)\b"
                       r"|\b(?:harsher|rougher) with me\b"
                       r"|\b(?:call me out|tell me off)\s+"
                       r"(?:harder|properly|like you mean it)\b", re.I)
_GENTLE_RE = re.compile(r"\bbe (?:nice|nicer|gentle|gentler|kind|kinder|civil|"
                        r"polite)\b"
                        r"|\b(?:ease up|go easy|stand down|steady on)\b"
                        r"|\b(?:that'?s|that is) (?:too harsh|enough of that)\b", re.I)
_SNOOZE_RE = re.compile(r"\bgive me\b[^.]{0,14}\bseconds?\b"
                        r"|\b(?:snooze|hush|be quiet|shush|hold on|one moment|"
                        r"give me a second)\b", re.I)
_EXCUSE_RE = re.compile(r"\b(?:it'?s|its|this is|that'?s)\s+"
                        r"(?:ok|okay|fine|alright|all right|allowed|deliberate)\b"
                        r"|\b(?:i'?m|i am)\s+(?:doing\s+)?(?:research|reading|"
                        r"looking (?:it|this) up)\b"
                        r"|\b(?:this|it)\s+is\s+(?:research|work|related|"
                        r"for work|part of it)\b", re.I)
_EXTEND_RE = re.compile(r"\b(?:extend|another|add)\b[^.]{0,20}\b(?:minutes?|mins?)\b"
                        r"|\bgive me\b[^.]{0,20}\bmore\b[^.]{0,12}\b(?:minutes?|mins?)\b"
                        r"|\b(?:minutes?|mins?)\s+more\b", re.I)
_PAUSE_RE = re.compile(r"\bpause\b|\bhold the (?:clock|timer|session)\b"
                       r"|\bstop the clock\b", re.I)
_RESUME_RE = re.compile(r"\b(?:resume|unpause|carry on|continue|back on)\b", re.I)
_ABORT_RE = re.compile(r"\b(?:abort|scrap|forget|kill|bin|cancel)\b[^.]{0,20}"
                       r"\b(?:%s|timer|clock|it)\b" % _FOCUS_WORD, re.I)
_FINISH_RE = re.compile(r"\b(?:end|finish|stop|wrap up|we'?re done|i'?m done)\b"
                        r"[^.]{0,20}\b(?:%s|timer|clock)\b"
                        r"|\b(?:i'?m|we'?re)\s+done\b"
                        r"|\bthat'?s (?:it|enough)\b" % _FOCUS_WORD, re.I)
_STATUS_RE = re.compile(r"\bhow (?:long|much longer|much time|am i doing|is it going)\b"
                        r"|\btime (?:left|remaining)\b"
                        r"|\bwhere (?:am i|are we)\b", re.I)

# MOVING THE LOCK. Checked before everything else in a live session, and written wide
# on purpose: this is the sentence you reach for when the lock is already on the wrong
# thing, so a phrasing it misses is a phrasing that leaves you stuck with it. Lead-ins
# cost nothing - "okay, I'm gonna need you to keep me in this tab" is a search, not a
# match, so the throat-clearing in front of it is simply not looked at.
#
# "this tab" is also in the viewer's screen-share matcher, which is why the client
# checks focus phrases BEFORE the share: mid-session this is about the target.
_SURFACE = r"(?:tab|window|page|app|application|site|screen|thing|one)"
_THIS = r"(?:this|that)"
_THIS_SURFACE = r"(?:this|that|the current|the)\s+%s" % _SURFACE
_RETARGET_RE = re.compile(
    # "lock on this tab", "lock this window", "lock me into this page", "lock in here"
    r"\block(?:\s+(?:on|onto|in|into|me\s+(?:on|onto|in|into|to)))?\s+"
    r"(?:%(ts)s|here)\b"
    # "keep me in this tab", "keep me on this", "keep me here"
    r"|\bkeep\s+(?:me|us)\s+(?:in|on|with)\s+(?:%(this)s(?:\s+%(s)s)?|here)\b"
    r"|\bkeep\s+(?:me|us)\s+(?:right\s+)?here\b"
    # "stay on this tab", "stay in here", "hold on this one", "stay right here"
    r"|\b(?:stay|hold)\s+(?:on|in|with)\s+(?:%(this)s(?:\s+%(s)s)?|here)\b"
    r"|\bstay\s+(?:right\s+)?here\b"
    # "this is the tab", "this is my work tab", "this is the one"
    r"|\bthis\s+is\s+(?:the|my)\s+(?:\w+\s+){0,2}%(s)s\b"
    # "watch this tab", "watch here". Deliberately not bare "watch this", which
    # belongs to the screen share and means something else entirely.
    r"|\bwatch\s+(?:%(ts)s|here)\b"
    % {"s": _SURFACE, "this": _THIS, "ts": _THIS_SURFACE}, re.I)


def parse_command(text, session_live):
    """(cmd, kwargs) or None. session_live gates everything but starting, which is
    what keeps a perfectly ordinary question about the notes from being read as a
    snooze."""
    said = str(text or "").strip()
    if not said:
        return None
    if START_RE.search(said):
        return "start", {"minutes": spoken_minutes(said) or DEFAULT_MINUTES}
    # Before the live gate, and it is the only thing here that is: the eyes can be
    # nudging you with no session at all, and a valve you have to start a timer to reach
    # is not a valve.
    if _RELIEF_RE.search(said):
        return "relief", {}
    if not session_live:
        return None
    # First, and before the share can have it: mid-session "lock on this tab" is an
    # instruction about the target, not a question about the pixels.
    if _RETARGET_RE.search(said):
        return "retarget", {"source": "voice"}
    if _ABORT_RE.search(said):
        return "abort", {}
    if _FINISH_RE.search(said):
        return "finish", {}
    if _EXTEND_RE.search(said):
        return "extend", {"minutes": spoken_minutes(said) or EXTEND_DEFAULT_MIN}
    if _DRILL_RE.search(said):
        return "drill", {}
    if _GENTLE_RE.search(said):
        return "gentle", {}
    if _NAG_RE.search(said):
        return "nag", {"seconds": spoken_int(said) or NAG_DEFAULT_S}
    if _SNOOZE_RE.search(said):
        return "snooze", {"seconds": spoken_int(said) or SNOOZE_DEFAULT_S}
    if _EXCUSE_RE.search(said):
        return "excuse", {}
    if _PAUSE_RE.search(said):
        return "pause", {}
    if _RESUME_RE.search(said):
        return "resume", {}
    if _STATUS_RE.search(said):
        return "status", {}
    return None


MANAGER = FocusManager()


def is_focus_request(text):
    with MANAGER._lock:                                        # noqa: SLF001
        live = (MANAGER._session is not None                   # noqa: SLF001
                and MANAGER._session.state != "ended")         # noqa: SLF001
    return parse_command(text, live) is not None


def handle(payload):
    """(status, body) for POST /focus. The spoken phrase IS the interface."""
    said = str(payload.get("say") or payload.get("text")
               or payload.get("question") or "")[:400]
    cmd = str(payload.get("cmd") or "").strip().lower()
    if cmd:
        # WHERE THE INSTRUCTION CAME FROM, which only the re-target reads. "card" is
        # the pill on the countdown card saying so about itself: the press is what
        # brought the card to the front, so the reading has to allow for that. It is
        # a fact about the button, and no button can claim anything about your windows.
        kwargs = {"source": str(payload.get("source") or "")[:16].strip().lower()}
        if cmd == "intent":
            # The answer window's own channel, and deliberately not a spoken phrase
            # the parser has to recognise: your answer to "what are we focusing on?"
            # can be any sentence in the language, so no regex should be deciding
            # whether it was one. The client knows it asked; it says so here.
            kwargs["text"] = str(payload.get("text") or payload.get("say") or "")
        if payload.get("minutes") is not None:
            try:
                kwargs["minutes"] = int(payload["minutes"])
            except (TypeError, ValueError):
                pass
        if payload.get("seconds") is not None:
            try:
                kwargs["seconds"] = float(payload["seconds"])
            except (TypeError, ValueError):
                pass
    else:
        with MANAGER._lock:                                    # noqa: SLF001
            live = (MANAGER._session is not None               # noqa: SLF001
                    and MANAGER._session.state != "ended")     # noqa: SLF001
        parsed = parse_command(said, live)
        if parsed is None:
            return 400, {"ok": False, "kind": "focus", "nodes": [],
                         "answer": LINES["none"] if not live else LINES["unknown"],
                         "error": "I did not recognise that as a focus instruction.",
                         "focus": MANAGER.state()}
        cmd, kwargs = parsed

    if cmd == "eyes":
        # The camera's own channel is POST /eyes, not a spoken phrase. Left here so a
        # caller that finds the timer first is told where the eyes live rather than
        # having its booleans quietly ignored.
        return 400, {"ok": False, "kind": "focus", "nodes": [],
                     "answer": "", "error": "The eyes report to POST /eyes.",
                     "focus": MANAGER.state()}

    if cmd == "summon":
        # THE ONE COMMAND WITH A THIRD ANSWER. Every other command replies with a line and
        # a state; this one also has to say whether the screen actually changed, because
        # the hand on the other end of it reports success or failure to the boss on the
        # strength of this boolean and must not guess. viaSession is false and stated
        # rather than computed: the line is in this reply and in no queue, so the caller -
        # tools/summon_tab.py - is the only one who can say it.
        line, done, state = MANAGER.summon()
        return 200, {"ok": True, "kind": "focus", "nodes": [], "viaSession": False,
                     "answer": line or "", "cmd": cmd, "summoned": bool(done),
                     "focus": state}

    seq_before = MANAGER.say_seq()
    answer, state = MANAGER.command(cmd, minutes=kwargs.get("minutes"),
                                    seconds=kwargs.get("seconds"),
                                    text=kwargs.get("text"),
                                    source=kwargs.get("source"))
    return 200, {"ok": True, "kind": "focus", "nodes": [],
                 # ONE SPEAKER, same rule as the eyes: true means the reply is in the
                 # say queue and every open tab will speak it exactly once, so the
                 # caller must not. False means this sentence exists nowhere else -
                 # the relief valve with no session, or a refusal - and the caller is
                 # the only one who can say it.
                 "viaSession": MANAGER.say_seq() > seq_before,
                 "answer": answer or "", "cmd": cmd, "focus": state}


def handle_eyes(payload):
    """(status, body) for POST /eyes. Four booleans in, at most one sentence out.

    This body is the WHOLE contract with the camera, and the important thing about it is
    what it has no field for: no image, no landmark, no coordinate, no confidence, no
    measurement of your face. One arriving under some other name would change nothing,
    because nothing in here reads anything but the four names below.

    The reply carries the tuning back every time, so the windows the page applies are
    the ones this file states rather than a second copy that drifted.
    """
    cmd = str(payload.get("cmd") or "posture").strip().lower()
    if cmd not in ("posture", "on", "off", "blind"):
        cmd = "posture"
    ears = payload.get("ears")
    line, via = MANAGER.note_eyes(
        cmd=cmd,
        present=bool(payload.get("present")),
        head_down=bool(payload.get("headDown")),
        slouched=bool(payload.get("slouched")),
        # None means "the page did not say", which is not the same as "the ears are
        # off" - only an explicit false earns the ear-law sentence.
        ears=None if ears is None else bool(ears))
    return 200, {"ok": True, "kind": "eyes", "nodes": [],
                 # Spoken by the tab that posted, and only ever set when there was no
                 # session to carry it instead. viaSession says the other thing happened.
                 "answer": line or "", "viaSession": bool(via), "cmd": cmd,
                 "tuning": EYES.tuning(), "focus": MANAGER.state()}
