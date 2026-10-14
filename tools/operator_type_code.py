#!/usr/bin/env python3
"""operator_type_code.py - Operator, phase 1.2: type a solution into the code editor of
the page the focus session has LOCKED, at the cursor, and prove it landed.

    echo {"code": "class Solution:\\n    def twoSum(self, nums, target):\\n        ..."} | python tools/operator_type_code.py
    Typed the solution into the editor - 3 lines added at the cursor.

THE CONTRACT, as tools/selftest.py states it:

  in    {"code": "..."} on stdin, UTF-8, newlines as \\n. The exact text to type. This hand
        has no opinion on whether it is correct, or even in the editor's language.
  out   ONE line of plain ASCII on stdout, and stdout is the ONLY evidence.
  exit  0 means every line was typed AND read back out of the editor's own model in the
        place it was sent. 1 means it was not, and the line says how much did land.

WHAT THIS HAND DOES NOT DO, which is most of its design:

  NO NEW TAB. It types into the tab the focus session already holds, found the way
    focus.py finds tabs (below). Phase 1.1's operator_browser.py is the opposite case: it
    only ever worked in a fresh tab so that your own work was never touched. Here your
    own work is the point, so the rules about touching it are tighter, not looser.
  NO BUTTONS. Run and Submit are never pressed, and no modifier key is ever sent - so
    not even LeetCode's Ctrl+Enter can fire by accident.
  NO REPLACING. It inserts at the cursor. It never selects all and never clears. If a
    selection is standing when it starts, the selection is COLLAPSED to its end first,
    so typing inserts beside it rather than replacing it. Boilerplate already in the
    editor stays where it is, and the result may want tidying by hand - an accepted,
    named limitation of this phase, not a defect to hide.
  NO DECISION ABOUT THE CODE. It arrives as a parameter. hands.py's server side fills it
    from the latest code block Galaxy wrote in chat (server.tool_facts), so a model never
    re-types it into a tag.

FINDING THE LOCKED TAB. The identity of the locked tab lives inside the running focus
session, which is in the server's process, not this one. The server publishes exactly
one thing about it - lockedTab, up to 24 characters of the tab's title cleaned to a
label's character set (focus.py LockWatch) - and deliberately never the target id. So
this does what focus.py's _cdp_active_host does: it joins a title to the DevTools target
list, scanning focus.py's three ports in their order, home base excluded. One match is
the tab. Several are narrowed by asking each page whether it is focused, then visible
(_cdp_front_target's _FRONT_EXPR, in its order), and two left over is a refusal, never a
guess - typing into the wrong one of two same-named tabs is not a recoverable mistake.

FINDING THE EDITOR. Monaco (LeetCode, measured) and CodeMirror 5 and 6 draw their own
text over a hidden real input, so the visible lines are not something to type into. The
editor is found through its own API on window - monaco.editor.getEditors(), the
CodeMirror instance on .CodeMirror, the EditorView behind .cm-content - because that API
is also the only honest way to READ IT BACK. The editor with focus wins; otherwise the
largest visible writable one. It is focused through its API (editor.focus()), never by
a click, because a click moves the cursor and the cursor is where you asked for it.

HOW IT TYPES, AND WHY THE ORDER IS NOT THE OBVIOUS ONE. Measured on LeetCode's Monaco,
2026-10-14, with a seven-line Python snippet at the end of a two-line body:

  Input.insertText, whole block     landed, WRONG: indents 8, 16, 28, 44, 56, 64
  Input.insertText, line by line    landed, WRONG: the same staircase
  Input.dispatchKeyEvent, per char  landed, WRONG: the same staircase
  synthetic paste, line by line     landed, EXACT

Monaco auto-indents every new line to the line above it, and the code's own indentation
then stacks on top. For Python that is not cosmetic, it is a different program. A paste
is not auto-indented, which is exactly why a person moving a solution in pastes it. So
the paste comes first: a ClipboardEvent carrying the text, dispatched at the editor's own
input. The system clipboard is never read or written. Input.insertText and then
dispatchKeyEvent are the fallbacks, in the order phase 1.2 named them.

  EVERY LINE IS READ BACK. After each line the editor's whole text is compared with what
  it must be: the text before, with everything typed so far at the cursor. Three outcomes:
  exact (next line); UNCHANGED (nothing landed, so trying again cannot duplicate anything:
  once more on the same path, then the next path); or CHANGED BUT WRONG - stop at once,
  never retry, and say which line. A retry after a partial landing is how a solution
  ends up in the editor twice.

THE PANIC KEY is phase 1.1's: Ctrl+M, registered system-wide only while this runs,
checked before every line, unregistered in a finally. Lines are paced LINE_PAUSE_S apart
so typing is visible and stoppable - a fifty-line paste in one event would finish before
a hand could reach the key. If Ctrl+M cannot be armed on Windows the hand refuses to
start. On abort it reports how many lines were in the editor, as read back.

Standard library only. The CDP client, the panic key, the run machinery and the
locked-tab join are operator_core's (phase 1.3), imported rather than copied: this file
held a fourth copy of them until then. What is left here is the part that is only this
hand's - the editor, read and typed through its own API, line by line.
"""
import json
import sys
import time

try:
    from tools import operator_core as core          # imported by the server
except ImportError:                                  # run as a hand, from tools/
    import operator_core as core

LINE_PAUSE_S = 0.06               # visible, stoppable typing: ~16 lines a second
# How long a line is given to SHOW UP before it is called "nothing landed". Measured on
# LeetCode's Monaco, 2026-10-14: right after the editor was handed focus, a paste took
# effect AFTER the read-back that followed it - the read saw no change, the line was sent
# again, and it landed twice. So a line is waited for until it matches, or has changed and
# held still across two reads, and "unchanged" is only believed after this long.
LAND_WAIT_S = 0.8
FOCUS_SETTLE_S = 0.25             # after the hand itself moves focus into the editor
# The registry kills this hand at timeout_s (35). Finishing inside 28 means a slow page is
# reported in this file's words, with the line count read back, never as a bare timeout.
BUDGET_S = 28.0

NO_PORT = core.NO_PORT
NO_LOCK = "I did not type anything - there is no page locked to type into, sir."
Failed = core.Failed
Aborted = core.Aborted
say = core.say


def note(text):
    """For a developer, never for the room: stderr is not spoken on success."""
    core.note("operator_type_code", text)


def lines_word(n):
    return "one line" if n == 1 else "%d lines" % n


# =============================================================================
#  THE EDITOR - found, focused and READ through its own API
# =============================================================================

# One function in the page, kept on window under a name nobody else uses, because the
# same editor must be found on every line: Monaco, CodeMirror 5, CodeMirror 6. `pick`
# chooses (focused first, else the largest visible writable one) and remembers the choice;
# every other verb acts on the remembered editor and nothing else.
_EDITOR_JS = r"""
(function (verb, arg) {
  var W = window, S = W.__operatorTypeCode || (W.__operatorTypeCode = {});
  var area = function (el) { var r = el.getBoundingClientRect(); return r.width * r.height; };
  var all = function () {
    var out = [];
    if (W.monaco && W.monaco.editor && W.monaco.editor.getEditors) {
      W.monaco.editor.getEditors().forEach(function (e) {
        var d = e.getDomNode(), m = e.getModel();
        if (!d || !m) return;
        if (e.getOption && W.monaco.editor.EditorOption &&
            e.getOption(W.monaco.editor.EditorOption.readOnly)) return;
        out.push({kind: 'monaco', ed: e, dom: d,
          focused: e.hasTextFocus(),
          value: function () { return m.getValue(1); },
          sel: function () { var s = e.getSelection();
            return [m.getOffsetAt(s.getStartPosition()), m.getOffsetAt(s.getEndPosition())]; },
          collapse: function () { e.setPosition(e.getSelection().getEndPosition()); },
          focus: function () { e.focus(); },
          input: function () { return d.querySelector('textarea'); },
          lang: function () { return m.getLanguageId ? m.getLanguageId() : ''; }});
      });
    }
    document.querySelectorAll('.CodeMirror').forEach(function (d) {
      var c = d.CodeMirror;
      if (!c || c.getOption('readOnly')) return;
      out.push({kind: 'codemirror5', ed: c, dom: d, focused: c.hasFocus(),
        value: function () { return c.getValue('\n'); },
        sel: function () { return [c.indexFromPos(c.getCursor('from')),
                                   c.indexFromPos(c.getCursor('to'))]; },
        collapse: function () { c.setCursor(c.getCursor('to')); },
        focus: function () { c.focus(); },
        input: function () { return c.getInputField(); },
        lang: function () { var m = c.getOption('mode'); return String(m && m.name || m || ''); }});
    });
    document.querySelectorAll('.cm-editor .cm-content').forEach(function (d) {
      var v = d.cmView && d.cmView.view;
      if (!v || !v.state || v.state.readOnly) return;
      out.push({kind: 'codemirror6', ed: v, dom: v.dom, focused: v.hasFocus,
        value: function () { return v.state.doc.toString(); },
        sel: function () { var r = v.state.selection.main; return [r.from, r.to]; },
        collapse: function () { v.dispatch({selection: {anchor: v.state.selection.main.to}}); },
        focus: function () { v.focus(); },
        input: function () { return v.contentDOM; },
        lang: function () { return ''; }});
    });
    return out.filter(function (x) { return area(x.dom) > 400; });
  };
  if (verb === 'pick') {
    var eds = all();
    if (!eds.length) return null;
    var best = eds.filter(function (x) { return x.focused; })[0] ||
               eds.slice().sort(function (a, b) { return area(b.dom) - area(a.dom); })[0];
    S.cur = best;
    best.focus();
    var s = best.sel(), hadSelection = s[1] > s[0];
    if (hadSelection) best.collapse();
    s = best.sel();
    return {kind: best.kind, count: eds.length, wasFocused: best.focused,
            collapsed: hadSelection, at: s[1], value: best.value(), lang: best.lang()};
  }
  var cur = S.cur;
  if (!cur) return null;
  if (verb === 'read') {
    var s2 = cur.sel(), inp = cur.input();
    return {value: cur.value(), at: s2[1],
            focused: !!inp && (document.activeElement === inp || inp.contains(document.activeElement))};
  }
  if (verb === 'refocus') { cur.focus(); return true; }
  if (verb === 'paste') {
    var t = cur.input();
    if (!t) return false;
    var dt = new DataTransfer();
    dt.setData('text/plain', arg);
    t.dispatchEvent(new ClipboardEvent('paste', {clipboardData: dt, bubbles: true,
                                                 cancelable: true}));
    return true;
  }
  if (verb === 'forget') { delete W.__operatorTypeCode; return true; }
  return null;
})(%s, %s)
"""


def editor(tab, verb, arg=None):
    return tab.evaluate(_EDITOR_JS % (json.dumps(verb), json.dumps(arg)), timeout=5.0)


def landed(tab, want, unchanged, wait=LAND_WAIT_S):
    """The editor's text once the last line has had time to arrive: as soon as it equals
    `want`, or has changed from `unchanged` and read the same twice, or at the deadline.
    A plain sleep, not run.nap(): Ctrl+M is honoured between lines, and an abort taken in
    here could leave a late line in the editor that the count did not include."""
    end = time.monotonic() + wait
    last = None
    while True:
        got = (editor(tab, "read") or {}).get("value")
        if got == want or (got != unchanged and got == last):
            return got
        if time.monotonic() >= end:
            return got
        last = got
        time.sleep(0.04)


def chunks_of(code):
    """One chunk per line, the newline carried at the FRONT of the next line, so the
    cursor never sits after a newline it typed. A chunk of a single character is merged
    into its neighbour: a lone "\\n" or "}" typed as one key is exactly what an editor's
    auto-indent and electric characters act on."""
    lines = code.split("\n")
    out = [lines[0]] + ["\n" + line for line in lines[1:]]
    merged = []
    for piece in out:
        if merged and (len(piece) <= 1 or len(merged[-1]) <= 1):
            merged[-1] += piece
        else:
            merged.append(piece)
    if len(merged) > 1 and len(merged[-1]) <= 1:
        merged[-2] += merged.pop()
    return [m for m in merged if m]


def send(tab, path, text):
    """Deliver one chunk by one path. Nothing here judges whether it landed."""
    if path == "paste":
        editor(tab, "paste", text)
    elif path == "insertText":
        tab.call("Input.insertText", {"text": text})
    else:
        for ch in text:
            if ch == "\n":
                for kind in ("keyDown", "keyUp"):
                    params = {"type": kind, "key": "Enter", "code": "Enter",
                              "windowsVirtualKeyCode": 13, "nativeVirtualKeyCode": 13}
                    if kind == "keyDown":
                        params["text"] = "\r"
                    tab.call("Input.dispatchKeyEvent", params)
            else:
                tab.call("Input.dispatchKeyEvent", {"type": "keyDown", "key": ch,
                                                    "text": ch, "unmodifiedText": ch})
                tab.call("Input.dispatchKeyEvent", {"type": "keyUp", "key": ch})


PATHS = ("paste", "insertText", "keys")


def type_code(run, tab, code, progress):
    """(lines_landed, path, info). Raises Failed / Aborted. `progress` holds the count of
    lines VERIFIED in the editor so far, so an abort reports what was read back - not
    what was sent, and not what the step text happened to say when the key went down."""
    run.at("finding the code editor on the page")
    info = editor(tab, "pick")
    if not info:
        raise Failed("I did not type anything - I could not find a code editor I can "
                     "read back on the locked page (Monaco or CodeMirror)")
    note("editor %s (%d on the page), focused before=%s, selection collapsed=%s, "
         "cursor offset %d, language %r"
         % (info["kind"], info["count"], info["wasFocused"], info["collapsed"],
            info["at"], info.get("lang")))
    before, at = info["value"], int(info["at"])
    if not info["wasFocused"]:
        time.sleep(FOCUS_SETTLE_S)    # the hand moved focus; let the editor take it
    pieces = chunks_of(code)
    total = code.count("\n") + 1
    typed, landed_lines, path_i = "", 0, 0
    progress["total"] = total
    for piece in pieces:
        run.at("typing line %d of %d" % (landed_lines + 1, total))
        state = editor(tab, "read")
        if not state or not state.get("focused"):
            # Somebody clicked elsewhere, or the editor lost focus: typing on would put
            # the next line wherever focus went. That is the user taking control too.
            raise Failed("I stopped after %s - the editor lost the cursor, so the rest "
                         "would have gone somewhere else" % lines_word(landed_lines))
        want = before[:at] + typed + piece + before[at:]
        tries = 0
        unchanged = before[:at] + typed + before[at:]
        while True:
            send(tab, PATHS[path_i], piece)
            got = landed(tab, want, unchanged)
            if got == want:
                break
            if got != unchanged:
                # LANDED, BUT NOT AS SENT. Never retried: a retry is how it doubles.
                raise Failed("I stopped at line %d - the editor changed what I typed (%s "
                             "path), so %s landed cleanly before it; please check that "
                             "line" % (landed_lines + 1, PATHS[path_i],
                                       lines_word(landed_lines)))
            # NOTHING LANDED - believed only after LAND_WAIT_S, and checked once more after
            # the refocus below, because a retry on top of a late arrival is a double.
            tries += 1
            editor(tab, "refocus")
            got = landed(tab, want, unchanged, wait=0.3)
            if got == want:
                break
            if got != unchanged:
                raise Failed("I stopped at line %d - the editor changed what I typed (%s "
                             "path), so %s landed cleanly before it; please check that "
                             "line" % (landed_lines + 1, PATHS[path_i],
                                       lines_word(landed_lines)))
            if tries == 1:
                continue                      # once more on the same path: nothing landed
            if path_i + 1 >= len(PATHS):
                raise Failed(("I typed %s, then the editor would not take any more by "
                              "any of the three ways I know" % lines_word(landed_lines))
                             if landed_lines else
                             "I did not type anything - the editor would not take text by "
                             "any of the three ways I know")
            note("path %s landed nothing on line %d; trying %s"
                 % (PATHS[path_i], landed_lines + 1, PATHS[path_i + 1]))
            path_i, tries = path_i + 1, 0
        typed += piece
        landed_lines = typed.count("\n") + 1
        progress["landed"] = landed_lines
        run.nap(LINE_PAUSE_S)
    return landed_lines, PATHS[path_i], info


def main():
    try:
        raw = sys.stdin.buffer.read().decode("utf-8", "replace")
        params = json.loads(raw) if raw.strip() else {}
    except ValueError:
        say("I did not type anything, sir - the request was not JSON.")
        return 1
    code = str((params or {}).get("code") or "") if isinstance(params, dict) else ""
    code = code.replace("\r\n", "\n").replace("\r", "\n")
    if not code.strip():
        say("I did not type anything, sir - there was no code to type.")
        return 1

    label = core.locked_label()
    if label is None:
        say("I did not type anything - I could not reach the focus session to ask which "
            "page is locked, sir.")
        return 1
    if not label:
        say(NO_LOCK)
        return 1

    panic = core.PanicKey(0x0B1B)
    run = core.Run(panic, BUDGET_S)
    tab = None
    progress = {"landed": 0, "total": code.count("\n") + 1}
    try:
        if not panic.arm():
            if sys.platform == "win32":
                say("I could not arm Ctrl+M, sir (%s), so I have not touched the page."
                    % panic.why)
                return 1
            sys.stderr.write("operator_type_code: NO PANIC KEY - %s\n" % panic.why)
        run.at("finding the locked page")
        found = core.find_locked_tab(label, verb="type anything")
        tab = core.CDP(found["ws"])
        landed, path, _info = type_code(run, tab, code, progress)
        note("typed by %s" % path)
        say("Typed the solution into the editor - %s added at the cursor."
            % lines_word(landed))
        return 0
    except Aborted as stop:
        # How much landed is what was READ BACK, line by line - never what was sent.
        done, total = progress["landed"], progress["total"]
        if not done:
            say("Stopped - you took back control after %s; nothing was typed."
                % str(stop.args[0]))
        else:
            say("Stopped - you took back control after typing %d of %s; those %d %s in "
                "the editor." % (done, lines_word(total), done,
                                 "is" if done == 1 else "are"))
        return 1
    except Failed as exc:
        reason = str(exc).strip().rstrip(".")
        if reason == NO_PORT.rstrip("."):
            say(NO_PORT)
        else:
            say("%s%s." % (reason[:1].upper(), reason[1:]) if reason.startswith("I ")
                else "That did not work, sir - %s." % reason)
        return 1
    finally:
        panic.disarm()
        if tab is not None:
            try:
                editor(tab, "forget")
            except Failed:
                pass
            tab.close()


if __name__ == "__main__":
    sys.exit(main())
