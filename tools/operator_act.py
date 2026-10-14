#!/usr/bin/env python3
"""operator_act.py - Operator, phase 1.3: the ONE generic door. Act on the page the focus
session has LOCKED - click, type, choose, scroll to, hover over - whatever site it is.

    echo {"action": "click", "target": "the subscribe button", "expect": "subscribe"} | python tools/operator_act.py
    Clicked 'Subscribe' on the locked page - it now reads 'Subscribed'.

THE CONTRACT, as tools/selftest.py states it:

  in    {"action": "click" | "type" | "select" | "scroll" | "hover",
         "target": "<a plain description: the subscribe button, the search box>",
         "text":   "<what to type, or which option to choose>"     (type, select)
         "submit": true                                            (type: press Enter after)
         "expect": "<the name the server's dry look found>",       (filled by the server)
         "page_url": "<the locked tab's address at that moment>"}  (filled by the server)
        on stdin, UTF-8.
  out   ONE line of plain ASCII on stdout, and stdout is the ONLY evidence.
  exit  0 means the thing the line names happened and was SEEN to happen - the element
        received the event and the line says what changed. 1 means it did not, and the
        line says why.

NO SITE IS NAMED IN THIS FILE, and none may be. The element is found by operator_core's
finder - text, aria, label, role, placeholder - with a confidence, and below the dial the
hand says what it looked for and the nearest miss, and touches nothing. That is the whole
of "no new site hardcoded by name": a page the generic read cannot handle is reported, not
taught.

WHAT YOU APPROVED IS WHAT IT TOUCHES. The server looks before the card is drawn (a dry
find on the locked page, nothing pressed) and writes the name it found into `expect`. The
run looks again, and if the best match is no longer that name - the page changed between
the card and the Yes - it refuses rather than pressing whatever is there now.

THE DISCIPLINE IS 1.1's AND 1.2's, UNCHANGED: an explicit ask, a locked tab, a "shall I?"
card, Ctrl+M registered only while this runs and checked before every step, and a read-back
of what landed. The paths each action tries, and the rule about never retrying an action
that landed, are operator_core's and are documented there.

WHICH TAB, AND WHERE IT IS. The locked tab - never a new one. The card carries its address
(`page_url`, read by the server through the focus session's own socket), and the tab is
found by that, because the title the lock published is the title AT LOCK TIME and goes
stale with the first click that navigates. Before acting, the tab is BROUGHT TO THE FRONT
(operator_core.show_tab): the employer usually speaks from the Galaxy viewer, so the locked
tab is a background tab at the moment of Yes, and a background tab does not take pointer
input promptly (measured: ~3.5 s per event, a mouseover and no click). It is also how the
employer sees the action happen.

NOT DONE HERE, BY DESIGN: no new tab (it acts where you are - the locked tab), no password
fields (refused by name), no modifier keys (so no Ctrl+Enter "submit" by accident), and no
action that is not one of the five.
"""
import json
import re
import sys

try:
    from tools import operator_core as core          # imported by the server
except ImportError:                                  # run as a hand, from tools/
    import operator_core as core

WHO = "operator_act"
# The registry kills this hand at timeout_s (40). Finishing inside 32 means a slow page is
# reported in this file's words, as the step it was on, never as a bare timeout.
BUDGET_S = 32.0
FIND_WAIT_S = 6.0
ACTIONS = ("click", "type", "select", "scroll", "hover")
VERB = {"click": "click anything", "type": "type anything", "select": "choose anything",
        "scroll": "scroll anywhere", "hover": "move the pointer"}


# =============================================================================
#  THE SENTENCE - how the server reads an ask into this hand's parameters
# =============================================================================
#
# One grammar, here, beside the hand it fills, so the parse and the run cannot drift. It is
# deliberately NARROW: an imperative that starts the sentence and names an action this hand
# has. Anything that is a question, mentions the code editor (operator_type_code's door), or
# is "search for X" without saying ON THIS PAGE (the web search's) is not this door's.
#
# "press" and "hit" are only actions when what follows is plainly a control ("press the
# play button", "press Enter" is not one - no target), because "press release" and "hit
# songs of 2024" are not instructions to a browser.

_POLITE = r"(?:(?:please|kindly|now|then|just|go\s+ahead\s+and|can\s+you|could\s+you|would\s+you)\s+)*"
_CONTROL = (r"(?:button|link|tab|icon|box|field|bar|dropdown|drop\s+down|checkbox|check\s+box|"
            r"option|toggle|switch|menu|result|video|input)")
_RULES = (
    ("click", re.compile(r"^" + _POLITE + r"(?:click|tap|double[-\s]?click)\s+(?:on\s+)?(?P<target>.+)$", re.I)),
    ("click", re.compile(r"^" + _POLITE + r"(?:press|hit|push)\s+(?:on\s+)?(?P<target>(?:the\s+)?.+?\b" + _CONTROL + r"s?|[\"'\u201c].+[\"'\u201d])$", re.I)),
    # Hinglish: "subscribe button pe click karo"
    ("click", re.compile(r"^" + _POLITE + r"(?P<target>.+?)\s+(?:pe|par|per)\s+(?:click|tap)\s+(?:kar(?:o|do|na|ein|en|iye)?|karke\s+do)\b.*$", re.I)),
    ("type", re.compile(r"^" + _POLITE + r"(?:type|enter|write|fill\s+in|put|input)\s+(?P<text>.+?)\s+(?:in|into|in\s+to|inside)\s+(?P<target>(?:the|this|that|my)\s+.+?|.+?\b" + _CONTROL + r")(?P<submit>\s*(?:,\s*)?(?:and\s+)?(?:then\s+)?(?:press|hit)\s+enter|\s*(?:,\s*)?(?:and\s+)?(?:then\s+)?(?:submit|search)(?:\s+it)?)?$", re.I)),
    ("type", re.compile(r"^" + _POLITE + r"(?:fill|fill\s+out|fill\s+up)\s+(?P<target>(?:the|this|that|my)\s+.+?)\s+with\s+(?P<text>.+?)(?P<submit>\s*(?:,\s*)?(?:and\s+)?(?:then\s+)?(?:press\s+enter|submit(?:\s+it)?))?$", re.I)),
    ("search", re.compile(r"^" + _POLITE + r"search\s+(?:for\s+)?(?P<text>.+?)\s+(?:on|in)\s+(?:this|the)\s+(?:page|site|website|tab)$", re.I)),
    ("search", re.compile(r"^" + _POLITE + r"search\s+(?:this|the)\s+(?:page|site|website|tab)\s+for\s+(?P<text>.+)$", re.I)),
    ("select", re.compile(r"^" + _POLITE + r"(?:select|choose|pick)\s+(?P<text>.+?)\s+(?:from|in|on|under)\s+(?P<target>(?:the|this|that)\s+.+)$", re.I)),
    # Operator 1.4: a picker named by what it should SHOW. "switch to java" names no control
    # at all - the value names the kind (core.VALUE_KINDS), and the kind finds the picker by
    # its current value. A value of no known kind is not an action ("switch to plan B").
    ("switch", re.compile(r"^" + _POLITE + r"(?:switch|change|set)\s+(?:the\s+)?(?P<target>[a-z ]{2,30}?)\s+to\s+(?P<text>.+)$", re.I)),
    ("switch", re.compile(r"^" + _POLITE + r"(?:switch|change)\s+(?:it\s+)?(?:over\s+)?to\s+(?P<text>.+)$", re.I)),
    ("scroll", re.compile(r"^" + _POLITE + r"scroll\s+(?:down\s+|up\s+)?(?:to|till|until)\s+(?P<target>.+)$", re.I)),
    ("hover", re.compile(r"^" + _POLITE + r"(?:hover|mouse)\s+(?:the\s+(?:pointer|mouse|cursor)\s+)?(?:over|on|onto)\s+(?P<target>.+)$", re.I)),
)
_QUESTION_RE = re.compile(r"^(?:how|why|what|what's|whats|when|where|which|who|whose|is|are|"
                          r"does|do|did|should|shall\s+i|can\s+i|explain|tell\s+me)\b", re.I)
_EDITOR_RE = re.compile(r"\beditor\b", re.I)
# What operator_type_code types: "it", "the solution", "your code". Never this door's text.
_CODE_TEXT_RE = re.compile(r"^(?:it|that|this|them|the\s+(?:solution|code|answer)|"
                           r"(?:your|my)\s+(?:solution|code|answer))$", re.I)


def parse_request(sentence):
    """{"action", "target", "text", "submit"} for an explicit ask to act on the page, or
    None. Pure: the server calls it on every addressless form of the sentence."""
    s = " ".join(str(sentence or "").split()).strip().rstrip(".!")
    if not s or len(s) > 300 or _QUESTION_RE.match(s):
        return None
    for action, rx in _RULES:
        m = rx.match(s)
        if not m:
            continue
        g = m.groupdict()
        target = (g.get("target") or "").strip(" ,")
        text = (g.get("text") or "").strip(" ,")
        if len(text) >= 2 and text[0] in "\"'\u201c\u2018" and text[-1] in "\"'\u201d\u2019":
            text = text[1:-1].strip()
        if action == "switch":
            kind = core.kind_of_value(text)
            if not kind:
                return None
            asked = " ".join(w for w in target.lower().split()
                             if w not in ("dropdown", "picker", "it", "over", "this", "that"))
            if asked and asked not in (kind, "editor", "code", "editor language",
                                       "code language"):
                return None              # "set the timer to 5" is not this
            return {"action": "select", "target": "the %s dropdown" % kind, "text": text,
                    "submit": False}
        if action == "search":
            return {"action": "type", "target": "the search box", "text": text,
                    "submit": True}
        if not target or len(target) > 120:
            return None
        if action == "type" and (_EDITOR_RE.search(target) or _CODE_TEXT_RE.match(text)):
            return None                      # operator_type_code's door, not this one
        if action in ("type", "select") and not text:
            return None
        return {"action": action, "target": target, "text": text,
                "submit": bool(g.get("submit"))}
    return None


def describe(params):
    """The {plan} blank for the card: what will be done, to what. Built from `expect` (the
    name the dry look found) when there is one, so the card names the thing itself.

    WHAT IS TYPED IS SPOKEN ONLY WHEN IT IS SHORT. The proposal line is read aloud; forty
    characters of a search query is what you asked for out loud anyway, and anything longer
    is "the text on the card", where the eyes can read it. A password field is refused by
    the hand, so its contents can never reach this line."""
    action = str(params.get("action") or "").strip().lower()
    target = core.describe_target(params.get("target"))
    expect = core.ascii_words(params.get("expect"), 50)
    thing = "'%s'" % expect if expect else target
    text = " ".join(str(params.get("text") or "").split())
    said = ("'%s'" % core.ascii_words(text, 40)) if text and len(text) <= 40 and \
        core.ascii_words(text, 40) else "the text on the card"
    if action == "click":
        return "click %s" % thing
    if action == "type":
        return "type %s into %s%s" % (said, thing, " and press Enter"
                                      if _truthy(params.get("submit")) else "")
    if action == "select":
        return "choose %s in %s" % (said, thing)
    if action == "scroll":
        return "scroll to %s" % thing
    if action == "hover":
        return "rest the pointer on %s" % thing
    return ""


def _truthy(value):
    return value is True or str(value).strip().lower() in ("true", "yes", "1", "on")


# =============================================================================
#  THE RUN
# =============================================================================

def _how(found, res):
    """A short note on HOW, when it was not the ordinary trusted path - the line owes the
    employer that a site may have ignored a synthetic event."""
    path = str(res.get("path") or "")
    if path == "keyboard":
        return " (by keyboard - something covered it)"
    if path == "dom" or (path and not res.get("trusted", True)):
        return " - a synthetic click, which some sites ignore"
    if path.startswith("setter"):
        return " - set directly, as the keyboard did not land it"
    if path == "synthetic":
        return " - by synthetic events, so a hover-only menu may not have opened"
    return ""


def act(run, tab, params):
    """The line for one action on `tab`. Raises core.Failed / core.Aborted."""
    action = params["action"]
    target = params["target"]
    verb = VERB[action]
    run.at("looking for %s" % core.describe_target(target))
    found = core.wait_target(run, tab, target, timeout=FIND_WAIT_S,
                             headings=(action == "scroll"))
    if not found["ok"]:
        raise core.Failed(core.miss_line(found, target, verb=verb))
    pick = found["pick"]
    name = core.label_of(pick)
    core.note(WHO, "found %r (%s, %.2f via %s); next %s"
              % (pick.get("name"), pick.get("role"), pick.get("conf"), pick.get("src"),
                 [(c["name"][:30], c["conf"]) for c in found["ranked"][1:3]]))
    expect = core.norm_name(params.get("expect"))
    if expect and core.norm_name(pick.get("name")) != expect:
        raise core.Failed("I did not %s - the page changed after you approved it: I was to "
                          "act on '%s', and the best match now is '%s'"
                          % (verb, core.ascii_words(params.get("expect"), 50), name))
    if action == "click":
        run.at("clicking '%s'" % name)
        res = core.act_click(run, tab, found)
        core.note(WHO, "click: " + core.fx_note(res))
        seen = core.effect_words(res["effects"])
        if res.get("newTab"):
            # Chrome brings a new tab to the front; the locked page is put back in front of
            # it, so the employer is still where the lock says, and the new tab is left
            # where it opened, unfollowed.
            core.note(WHO, "the click opened a new tab (%s); back to the locked page"
                      % ("opened by this tab" if res["newTab"].get("opener") else "opener unknown"))
            core.show_tab(run, tab, tab.ws_url)
            return ("Clicked '%s' on the locked page - %s; you are still on the locked page."
                    % (name, seen))
        if seen:
            return "Clicked '%s' on the locked page - %s%s." % (name, seen, _how(found, res))
        return ("Clicked '%s' on the locked page - it took the click, though nothing on the "
                "page visibly changed%s." % (name, _how(found, res)))
    if action == "type":
        text = params["text"]
        res = core.act_type(run, tab, found, text)
        core.note(WHO, "type: path=%s replaced=%s" % (res.get("path"), res.get("replaced")))
        line = "Typed %s into '%s'%s" % (
            ("'%s'" % core.ascii_words(text, 40)) if len(text) <= 40 and
            core.ascii_words(text, 40) else "%d characters" % len(text), name,
            " (replacing what was there)" if res.get("replaced") else "")
        if res["path"] == "setter":
            line += " - set directly, as typing did not land"
        if _truthy(params.get("submit")):
            run.at("sending '%s'" % name)
            sub = core.act_submit(run, tab, found)
            seen = core.effect_words(sub["effects"])
            how = "pressed Enter" if sub["path"] == "enter" else "pressed %s" % sub["path"]
            line += (" and %s - %s" % (how, seen)) if seen else (
                " and %s, though nothing on the page visibly changed" % how)
        return line + "."
    if action == "select":
        res = core.act_select(run, tab, found, params["text"])
        if res["path"] == "already":
            return "'%s' already shows '%s' - I left it as it was." % (
                name, core.ascii_words(res["chosen"], 40))
        if res.get("path", "").startswith("custom/") and not res.get("verified"):
            return ("I chose '%s' in '%s', but it still shows '%s' - check it yourself, sir."
                    % (core.ascii_words(res["chosen"], 40), name,
                       core.ascii_words(res.get("shows"), 40) or "something else"))
        return "Chose '%s' in '%s'%s." % (core.ascii_words(res["chosen"], 40), name,
                                          _how(found, res))
    if action == "scroll":
        run.at("scrolling to '%s'" % name)
        res = core.act_scroll(run, tab, found)
        if res["path"] == "already":
            return "'%s' is already near the top of the locked page - I did not need to scroll." % name
        return "Scrolled to '%s'%s." % (
            name, "" if res["path"] == "wheel" else " (moved it there directly)")
    if action == "hover":
        run.at("moving the pointer to '%s'" % name)
        res = core.act_hover(run, tab, found)
        seen = core.effect_words(res.get("effects"))
        return "The pointer is resting on '%s'%s%s." % (name, (" - " + seen) if seen else "",
                                                        _how(found, res))
    raise core.Failed("I do not know how to %s" % action)


def main():
    try:
        raw = sys.stdin.buffer.read().decode("utf-8", "replace")
        params = json.loads(raw) if raw.strip() else {}
    except ValueError:
        core.say("I did not touch anything, sir - the request was not JSON.")
        return 1
    if not isinstance(params, dict):
        core.say("I did not touch anything, sir.")
        return 1
    action = str(params.get("action") or "").strip().lower()
    if action not in ACTIONS:
        core.say("I did not touch anything, sir - '%s' is not something I can do on a page."
                 % core.ascii_words(action, 30))
        return 1
    params["action"] = action
    params["target"] = " ".join(str(params.get("target") or "").split())
    params["text"] = str(params.get("text") or "")
    if not params["target"]:
        core.say("I did not touch anything, sir - there was nothing named to act on.")
        return 1
    if action in ("type", "select") and not params["text"].strip():
        core.say("I did not touch anything, sir - there was nothing to %s."
                 % ("type" if action == "type" else "choose"))
        return 1

    label, locked = core.lock_state()
    if label is None:
        core.say("I did not touch anything - I could not reach the focus session to ask "
                 "which page is locked, sir.")
        return 1
    if not locked:
        core.say(core.NO_LOCK)
        return 1

    panic = core.PanicKey(0x0B1C)
    run = core.Run(panic, BUDGET_S)
    tab = None
    try:
        refusal = core.arm_or_refuse(panic, WHO)
        if refusal:
            core.say(refusal)
            return 1
        run.at("finding the locked page")
        page = core.find_locked_tab(label, verb=VERB[action],
                                    url=str(params.get("page_url") or "").strip() or None)
        tab = core.CDP(page["ws"])
        core.show_tab(run, tab, page["ws"])
        line = act(run, tab, params)
        run.check()               # a Ctrl+M on the last tick is still a Ctrl+M
        core.say(line)
        return 0
    except core.Aborted as stop:
        core.say("Stopped - you took back control while %s." % core.ascii_words(stop.args[0], 120))
        return 1
    except core.Failed as exc:
        core.say(core.failure_line(exc))
        return 1
    finally:
        panic.disarm()
        if tab is not None:
            tab.close()


if __name__ == "__main__":
    sys.exit(main())
