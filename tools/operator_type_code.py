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

THE PANIC KEY is phase 1.1's: Ctrl+H, registered system-wide only while this runs,
checked before every line, unregistered in a finally. Lines are paced LINE_PAUSE_S apart
so typing is visible and stoppable - a fifty-line paste in one event would finish before
a hand could reach the key. If Ctrl+H cannot be armed on Windows the hand refuses to
start. On abort it reports how many lines were in the editor, as read back.

Standard library only, one file. The CDP client, the panic key and the run machinery are
copied from operator_browser.py (which copied the framing from focus.py), and the label
cleaning and front-tab expression from focus.py - copied rather than imported, because a
hand is one file.
"""
import base64
import json
import os
import re
import socket
import struct
import sys
import threading
import time
import urllib.parse
import urllib.request

SERVER = "http://127.0.0.1:4700"  # the focus session lives in the server's process
PORTS = (9222, 9223, 9224)        # focus.py's CDP_PORTS, in its order
HTTP_TIMEOUT_S = 1.5
CALL_TIMEOUT_S = 8.0
POLL_S = 0.25
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

# focus.py, copied: what the server's lockedTab is made of.
HOME_BASE_HOSTS = frozenset(("127.0.0.1", "localhost", "::1", "[::1]"))
LOCK_TITLE_CHARS = 24
LABEL_MAX_CHARS = 28
_LABEL_CLEAN_RE = re.compile(r"[^A-Za-z0-9 .+&'-]+")
_LABEL_WORD_RE = re.compile(r"[A-Za-z0-9]")
_FRONT_EXPR = ("((document.visibilityState==='visible')?1:0)"
               "+(document.hasFocus()?2:0)")

NO_PORT = ("I cannot do that, sir - Chrome has no debugging port open. Ask me to "
           "relaunch Chrome with the debugging port first.")
NO_LOCK = "I did not type anything - there is no page locked to type into, sir."


def say(line):
    sys.stdout.buffer.write(str(line).encode("ascii", "replace") + b"\n")
    sys.stdout.buffer.flush()


def note(text):
    """For a developer, never for the room: stderr is not spoken on success."""
    sys.stderr.write("operator_type_code: %s\n" % text)


class Failed(Exception):
    """A reason, in words that can be spoken."""


class Aborted(Exception):
    """Ctrl+H. Carries the step that was in progress."""


def lines_word(n):
    return "one line" if n == 1 else "%d lines" % n


# =============================================================================
#  THE PANIC KEY - operator_browser.py's, unchanged
# =============================================================================

MOD_CONTROL = 0x0002
MOD_NOREPEAT = 0x4000
VK_H = 0x48
WM_HOTKEY = 0x0312
WM_QUIT = 0x0012
HOTKEY_ID = 0x0B1B


class PanicKey:
    """Ctrl+H on a background thread with its own message loop: RegisterHotKey binds to
    the calling thread, only that thread may unregister it, and WM_QUIT is what makes
    GetMessage return. While registered, Chrome's own Ctrl+H (History) is suppressed; it
    comes back the instant UnregisterHotKey runs. Off Windows there is NO panic key and
    `why` says so loudly - see operator_browser.PanicKey for the full reasoning."""

    def __init__(self):
        self.fired = threading.Event()
        self.armed = False
        self.why = ""
        self._tid = None
        self._thread = None
        self._ready = threading.Event()

    def arm(self):
        if sys.platform != "win32":
            # LOUD, ON PURPOSE: no RegisterHotKey off Windows, so no Ctrl+H.
            self.why = "not Windows: RegisterHotKey does not exist here, so no Ctrl+H"
            return False
        try:
            import ctypes
            from ctypes import wintypes
        except Exception as exc:                               # noqa: BLE001
            self.why = "ctypes is unavailable (%s), so no Ctrl+H" % type(exc).__name__
            return False

        def pump():
            user32 = ctypes.WinDLL("user32", use_last_error=True)
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            self._tid = kernel32.GetCurrentThreadId()
            ok = user32.RegisterHotKey(None, HOTKEY_ID, MOD_CONTROL | MOD_NOREPEAT, VK_H)
            if not ok:
                self.why = "RegisterHotKey refused Ctrl+H (error %d)" % ctypes.get_last_error()
                self._ready.set()
                return
            self.armed = True
            self._ready.set()
            try:
                msg = wintypes.MSG()
                while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                    if msg.message == WM_HOTKEY and msg.wParam == HOTKEY_ID:
                        self.fired.set()
            finally:
                user32.UnregisterHotKey(None, HOTKEY_ID)
                self.armed = False

        self._thread = threading.Thread(target=pump, name="ctrl-h", daemon=True)
        self._thread.start()
        self._ready.wait(3.0)
        return self.armed

    def disarm(self):
        if self._thread is None or not self._thread.is_alive():
            return
        import ctypes
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        for _ in range(20):
            if user32.PostThreadMessageW(self._tid, WM_QUIT, 0, 0):
                break
            time.sleep(0.05)
        self._thread.join(2.0)


class Run:
    """The brake and the clock, consulted before every line (operator_browser.Run)."""

    def __init__(self, panic, budget_s=BUDGET_S):
        self.panic = panic
        self.step = "starting"
        self.deadline = time.monotonic() + budget_s

    def at(self, step):
        self.step = step
        self.check()

    def check(self):
        if self.panic is not None and self.panic.fired.is_set():
            raise Aborted(self.step)
        if time.monotonic() > self.deadline:
            raise Failed("I ran out of time while %s, sir, so I stopped there" % self.step)

    def nap(self, seconds=POLL_S):
        end = time.monotonic() + seconds
        while True:
            self.check()
            left = end - time.monotonic()
            if left <= 0:
                return
            time.sleep(min(0.02, left))


# =============================================================================
#  CDP - operator_browser.py's client (framing from focus.py), unchanged
# =============================================================================

def _ws_frame(payload):
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
    def fill(n):
        while len(buf) < n:
            chunk = sock.recv(65536)
            if not chunk:
                return False
            buf.extend(chunk)
        return True

    if not fill(2):
        return None
    if buf[1] & 0x80:
        return None
    length, at = buf[1] & 0x7F, 2
    if length == 126:
        if not fill(4):
            return None
        length, at = struct.unpack_from("!H", buf, 2)[0], 4
    elif length == 127:
        if not fill(10):
            return None
        length, at = struct.unpack_from("!Q", buf, 2)[0], 10
    if length > (8 << 20) or not fill(at + length):
        return None
    opcode, data = buf[0] & 0x0F, bytes(buf[at:at + length])
    del buf[:at + length]
    return opcode, data


class CDP:
    def __init__(self, ws_url):
        parts = urllib.parse.urlsplit(ws_url or "")
        if parts.scheme != "ws" or not parts.hostname or not parts.path:
            raise Failed("the browser gave me no address to talk to the tab on")
        port = parts.port or 80
        path = parts.path + (("?" + parts.query) if parts.query else "")
        self._next = 0
        self.buf = bytearray()
        try:
            self.sock = socket.create_connection((parts.hostname, port), timeout=5.0)
            self.sock.sendall(("GET %s HTTP/1.1\r\nHost: %s:%d\r\n"
                               "Upgrade: websocket\r\nConnection: Upgrade\r\n"
                               "Sec-WebSocket-Key: %s\r\nSec-WebSocket-Version: 13\r\n\r\n"
                               % (path, parts.hostname, port,
                                  base64.b64encode(os.urandom(16)).decode("ascii"))
                               ).encode("ascii"))
            while b"\r\n\r\n" not in self.buf:
                chunk = self.sock.recv(4096)
                if not chunk or len(self.buf) > 65536:
                    raise OSError("no handshake")
                self.buf.extend(chunk)
        except OSError as exc:
            raise Failed("the browser would not let me talk to the tab (%s)"
                         % type(exc).__name__)
        head, rest = bytes(self.buf).split(b"\r\n\r\n", 1)
        if b"101" not in head.split(b"\r\n", 1)[0]:
            raise Failed("the browser refused the DevTools connection to the tab")
        self.buf = bytearray(rest)

    def call(self, method, params=None, timeout=CALL_TIMEOUT_S):
        self._next += 1
        mid = self._next
        try:
            self.sock.sendall(_ws_frame(json.dumps(
                {"id": mid, "method": method, "params": params or {}}).encode("utf-8")))
            deadline = time.monotonic() + timeout
            while True:
                left = deadline - time.monotonic()
                if left <= 0:
                    raise socket.timeout()
                self.sock.settimeout(left)
                frame = _ws_read(self.sock, self.buf)
                if frame is None:
                    raise OSError("the DevTools connection closed")
                opcode, data = frame
                if opcode == 8:
                    raise OSError("the DevTools connection closed")
                if opcode != 1:
                    continue
                try:
                    msg = json.loads(data.decode("utf-8", "replace"))
                except ValueError:
                    continue
                if msg.get("id") != mid:
                    continue
                if "error" in msg:
                    raise Failed("the browser refused %s: %s" % (
                        method, (msg["error"] or {}).get("message", "no reason given")))
                return msg.get("result") or {}
        except socket.timeout:
            raise Failed("the browser did not answer %s within %.0f seconds"
                         % (method, timeout))
        except OSError as exc:
            raise Failed("the browser stopped answering (%s)" % (str(exc) or
                                                                 type(exc).__name__))

    def evaluate(self, expression, gesture=False, timeout=CALL_TIMEOUT_S):
        res = self.call("Runtime.evaluate",
                        {"expression": expression, "returnByValue": True,
                         "userGesture": bool(gesture)}, timeout=timeout)
        if res.get("exceptionDetails"):
            return None
        return (res.get("result") or {}).get("value")

    def close(self):
        try:
            self.sock.close()
        except Exception:                                      # noqa: BLE001
            pass


def get_json(url, timeout=HTTP_TIMEOUT_S):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as res:
            return json.loads(res.read().decode("utf-8", "replace"))
    except Exception:                                          # noqa: BLE001
        return None


# =============================================================================
#  THE LOCKED TAB - focus.py's title join, from outside the server's process
# =============================================================================

def clean_label(text):
    """focus.py's _clean_label, copied: the shape lockedTab is cut from."""
    name = _LABEL_CLEAN_RE.sub(" ", str(text or ""))
    name = " ".join(name.split())[:LABEL_MAX_CHARS].strip(" .-'&+")
    if not name or not _LABEL_WORD_RE.search(name):
        return None
    return name


def lock_label(title):
    """What focus.py's LockWatch and state() would show for a tab with this title."""
    return (clean_label(title) or "")[:LOCK_TITLE_CHARS].strip()


def locked_label():
    """The session's lockedTab, or "" - and None when the server cannot be asked."""
    found = get_json(SERVER + "/focus", timeout=4.0)
    if not isinstance(found, dict):
        return None
    return str((found.get("focus") or {}).get("lockedTab") or "").strip()


def _front_bits(ws):
    """_FRONT_EXPR asked of one page on a socket of its own, or None."""
    try:
        tab = CDP(ws)
    except Failed:
        return None
    try:
        value = tab.evaluate(_FRONT_EXPR, timeout=1.0)
        return int(value) if value is not None else None
    except (Failed, TypeError, ValueError):
        return None
    finally:
        tab.close()


def find_locked_tab(label):
    """The one DevTools page whose title is the locked tab's, as {ws, title, host}.

    Raises Failed for no port, no match, and an ambiguity that _FRONT_EXPR cannot settle.
    """
    alive, hits = False, []
    for port in PORTS:
        targets = get_json("http://127.0.0.1:%d/json" % port)
        if targets is None:
            continue
        alive = True
        for t in targets if isinstance(targets, list) else ():
            if not isinstance(t, dict) or t.get("type") != "page":
                continue
            url = str(t.get("url") or "")
            host = (urllib.parse.urlsplit(url).hostname or "").lower()
            if not t.get("webSocketDebuggerUrl") or not host or host in HOME_BASE_HOSTS:
                continue
            if not url.lower().startswith(("http://", "https://")):
                continue
            if lock_label(t.get("title")) == label:
                hits.append({"ws": t["webSocketDebuggerUrl"], "host": host,
                             "title": str(t.get("title") or "")})
        if hits:
            break
    if not alive:
        raise Failed(NO_PORT)
    if not hits:
        raise Failed("I did not type anything - the locked page, '%s', is not open in the "
                     "browser I can reach, or its title has changed since it was locked"
                     % label)
    if len(hits) == 1:
        return hits[0]
    # _cdp_front_target's order: focused, then merely visible. Two left is a question.
    focused, visible = [], []
    for hit in hits:
        bits = _front_bits(hit["ws"])
        if bits is None:
            continue
        if bits & 2:
            focused.append(hit)
        elif bits & 1:
            visible.append(hit)
    for pool in (focused, visible):
        if len(pool) == 1:
            return pool[0]
        if len(pool) > 1:
            break
    raise Failed("I did not type anything - %d tabs answer to the locked page's name, "
                 "'%s', and I will not guess which one you meant" % (len(hits), label))


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
    A plain sleep, not run.nap(): Ctrl+H is honoured between lines, and an abort taken in
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

    label = locked_label()
    if label is None:
        say("I did not type anything - I could not reach the focus session to ask which "
            "page is locked, sir.")
        return 1
    if not label:
        say(NO_LOCK)
        return 1

    panic = PanicKey()
    run = Run(panic)
    tab = None
    progress = {"landed": 0, "total": code.count("\n") + 1}
    try:
        if not panic.arm():
            if sys.platform == "win32":
                say("I could not arm Ctrl+H, sir (%s), so I have not touched the page."
                    % panic.why)
                return 1
            sys.stderr.write("operator_type_code: NO PANIC KEY - %s\n" % panic.why)
        run.at("finding the locked page")
        found = find_locked_tab(label)
        tab = CDP(found["ws"])
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
