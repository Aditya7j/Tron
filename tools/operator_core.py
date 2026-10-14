#!/usr/bin/env python3
"""operator_core.py - Operator, phase 1.3: the ONE generic door's machinery. Not a hand.

Phases 1.1 and 1.2 each copied the same four things into their own file - the CDP client,
the Ctrl+M key, the run clock and (1.2) the locked-tab join - and then wrote a bespoke hand
on top for one site's DOM. This file is those four things ONCE, plus the three that make a
bespoke hand unnecessary:

  THE FINDER     find_target("the subscribe button") on ANY page, by what a person sees
                 and what the accessibility tree says: visible text, aria-label and
                 aria-labelledby, <label>, role (explicit or implied by the tag), placeholder,
                 title, alt, value, name/id - ranked into a CONFIDENCE between 0 and 1. Below
                 THRESHOLD it says so and names the nearest miss; two different things tied
                 at the top is a refusal too. Never a guess, never a site's CSS selector.
  THE EXECUTOR   click / type / select / scroll / hover / a named key, each through REAL
                 input first (Input.dispatchMouseEvent, Input.insertText, dispatchKeyEvent,
                 mouseWheel) with the synthetic DOM call only as the last, NAMED fallback.
                 Every action is read back: did the target receive the event, was it
                 trusted, and what changed on the page. Like 1.2's editor: a path that
                 landed nothing may be followed by the next path; a path that landed
                 SOMETHING - even the wrong thing - is never retried, because a second click
                 on a toggle is how "subscribe" becomes "unsubscribe".
  THE READER     read_page(): the page's readable TEXT - headings, the main body, form
                 labels - with navigation, page chrome and code editors left out. That is
                 what grounds an answer in the problem actually on screen rather than in
                 the problem's name (carry-forward A from 1.2).

WHAT STAYS OUT, ON PURPOSE: no screenshots and no vision (DOM and accessibility tree only,
like 1.1 and 1.2), and NO SITE NAMES. A site that defeats the generic read is reported as
such by the hand that asked; nothing in this file grows a selector for it. The "site
layers" in operator_browser.py are the only place a site is named, and what they may hold
is listed there.

IMPORTED, NOT COPIED, and that is a change of house rule worth stating: "a hand is one
file" made sense for three hands; it made four copies of a WebSocket client. A hand
imports this as `operator_core` (it is run with tools/ as its directory) and the server
imports it as `tools.operator_core`. Standard library only, like every hand.
"""
import base64
import hashlib
import json
import os
import re
import socket
import struct
import sys
import threading
import time
import unicodedata
import urllib.parse
import urllib.request

SERVER = "http://127.0.0.1:4700"  # the focus session lives in the server's process
PORTS = (9222, 9223, 9224)        # focus.py's CDP_PORTS, in its order
HTTP_TIMEOUT_S = 1.5
CALL_TIMEOUT_S = 10.0             # one CDP request; Page.navigate is the slow one
POLL_S = 0.25                     # every wait ticks this often, and checks Ctrl+M each tick
LOAD_TIMEOUT_S = 25.0             # a real page on a real connection, not a fixture
FIND_TIMEOUT_S = 15.0             # an SPA paints its results some time after "complete"
EFFECT_WAIT_S = 2.0               # how long an action's consequence is looked for

# THE CONFIDENCE DIAL. 0.60 is where a name that holds every word asked for, on an element
# of the right kind, lands even when the name is long ("Kesariya - Brahmastra | Ranbir
# Kapoor | ... | Arijit Singh" for "kesariya arijit singh" scores 0.77), and where half the
# words on the right kind of element (0.5 * 1.0 = 0.50) does not. A tie inside TIE_GAP
# between two DIFFERENT names is refused rather than broken by document order.
THRESHOLD = 0.60
TIE_GAP = 0.03
SCROLL_BAND = 0.35                # "scrolled to" = its top in the upper 35% of the view
SCROLL_AIM = 0.15                 # and the wheel aims it at 15% from the top

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
NO_LOCK = "I did not touch anything - there is no page locked for me to act on, sir."


# =============================================================================
#  SAYING IT
# =============================================================================

def ascii_words(text, limit=90):
    """Plain ASCII for the one line that is spoken. Accents fold (Kesariya stays
    Kesariya); a title in a script ASCII cannot carry comes back empty rather than as a
    row of question marks read aloud, and the caller then simply leaves it out."""
    folded = unicodedata.normalize("NFKD", str(text or ""))
    kept = "".join(ch for ch in folded if ord(ch) < 128 and (ch.isprintable() or ch == " "))
    kept = " ".join(kept.split())
    # "+" and "#" count as letters here: "C++" and "C#" are names, not punctuation (measured:
    # LeetCode's language button was spoken as "a button" until they did).
    letters = sum(ch.isalnum() or ch in "+#" for ch in kept)
    total = sum(not ch.isspace() for ch in " ".join(str(text or "").split()))
    if not letters or (total and letters < total * 0.5):
        return ""
    if len(kept) > limit:
        kept = kept[:limit].rsplit(" ", 1)[0] + "..."
    return kept


def say(line):
    sys.stdout.buffer.write(str(line).encode("ascii", "replace") + b"\n")
    sys.stdout.buffer.flush()


_BORN = time.monotonic()


def note(who, text):
    """For a developer, never for the room: stderr is not spoken on success. Stamped with
    the seconds since the hand started, because "where did the time go" is the usual
    question a slow run leaves."""
    sys.stderr.write("%s: +%.2fs %s\n" % (who, time.monotonic() - _BORN, text))
    sys.stderr.flush()


def fx_note(res):
    """One line on how an action landed, for note(): the path, whether trusted, and the
    events the page's witness saw (type, trusted, into the target)."""
    fx = (res or {}).get("effects") or {}
    got = [(g.get("type"), bool(g.get("trusted")), bool(g.get("into")))
           for g in (fx.get("got") or [])][:8]
    return ("path=%s trusted=%s tried=%s events=%s muts=%s changed=%s navigated=%s"
            % ((res or {}).get("path"), (res or {}).get("trusted"), (res or {}).get("tried"),
               got, fx.get("muts"), fx.get("changed"), fx.get("navigated")))


class Failed(Exception):
    """A reason, in words that can be spoken. Raised anywhere; printed once, in main."""


class Aborted(Exception):
    """Ctrl+M. Carries the step that was in progress."""


def failure_line(exc):
    """The one spoken line for a Failed: a sentence that begins "I " is the hand's own
    voice already; anything else is a reason and gets the house's preface."""
    reason = str(exc).strip().rstrip(".")
    if reason == NO_PORT.rstrip("."):
        return NO_PORT
    return ("%s%s." % (reason[:1].upper(), reason[1:]) if reason.startswith(("I ", "That "))
            else "That did not work, sir - %s." % reason)


# =============================================================================
#  THE PANIC KEY - Ctrl+M, armed for the length of one run and not a moment longer
# =============================================================================

MOD_CONTROL = 0x0002
MOD_NOREPEAT = 0x4000
VK_M = 0x4D
WM_HOTKEY = 0x0312
WM_QUIT = 0x0012


class PanicKey:
    """Ctrl+M as a system-wide hotkey, on a background thread with its own message loop.

    RegisterHotKey binds the key to the CALLING THREAD's message queue, and only that
    thread may unregister it - so one thread registers, pumps GetMessage, and unregisters
    in its own finally. disarm() posts WM_QUIT, the only message that makes GetMessage
    return 0.

    WAS Ctrl+H, MOVED TO Ctrl+M. Measured live: Chrome's own Ctrl+H (History) is only
    SUPPOSED to be suppressed while RegisterHotKey holds it, and on at least one run it
    was not - History opened anyway, mid-action, which is the one failure this key exists
    to prevent. Ctrl+M carries no Chrome shortcut of its own, so there is nothing for it
    to race against and nothing for UnregisterHotKey to hand back when this disarms.

    OFF WINDOWS THERE IS NO PANIC KEY, AND THIS SAYS SO RATHER THAN CRASHING. `armed`
    stays False and `why` names the reason; every hand refuses to start on Windows without
    it, and prints it to stderr elsewhere (a developer's Mac must be able to run a hand).
    """

    def __init__(self, hotkey_id=0x0B1A):
        self.hotkey_id = hotkey_id
        self.fired = threading.Event()
        self.armed = False
        self.why = ""
        self._tid = None
        self._thread = None
        self._ready = threading.Event()

    def arm(self):
        if sys.platform != "win32":
            self.why = "not Windows: RegisterHotKey does not exist here, so no Ctrl+M"
            return False
        try:
            import ctypes
            from ctypes import wintypes
        except Exception as exc:                               # noqa: BLE001
            self.why = "ctypes is unavailable (%s), so no Ctrl+M" % type(exc).__name__
            return False

        def pump():
            user32 = ctypes.WinDLL("user32", use_last_error=True)
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            self._tid = kernel32.GetCurrentThreadId()
            ok = user32.RegisterHotKey(None, self.hotkey_id, MOD_CONTROL | MOD_NOREPEAT, VK_M)
            if not ok:
                self.why = "RegisterHotKey refused Ctrl+M (error %d)" % ctypes.get_last_error()
                self._ready.set()
                return
            self.armed = True
            self._ready.set()
            try:
                msg = wintypes.MSG()
                while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                    if msg.message == WM_HOTKEY and msg.wParam == self.hotkey_id:
                        self.fired.set()
            finally:
                user32.UnregisterHotKey(None, self.hotkey_id)
                self.armed = False

        self._thread = threading.Thread(target=pump, name="ctrl-m", daemon=True)
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


def arm_or_refuse(panic, who):
    """None when the brake is armed (or there is no brake to have, off Windows), else the
    refusal line. A proposal promised the key; a promise of a brake that is not there is
    the silent downgrade this house does not do."""
    if panic.arm():
        return None
    if sys.platform == "win32":
        return ("I could not arm Ctrl+M, sir (%s), so I have not touched the browser."
                % panic.why)
    note(who, "NO PANIC KEY - %s" % panic.why)
    return None


# =============================================================================
#  THE RUN - the step in progress, the brake, and the clock
# =============================================================================

class Run:
    """What every primitive consults before it acts: has Ctrl+M been pressed, and is
    there time left. `step` is a gerund phrase ("searching for x") so the abort line can
    say what was in progress in plain English. `panic` may be None for a read-only use
    (the server's dry find), which has no brake because it touches nothing."""

    def __init__(self, panic, budget_s):
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
        """A wait that is also a brake check, so Ctrl+M never waits for a poll to end."""
        end = time.monotonic() + seconds
        while True:
            self.check()
            left = end - time.monotonic()
            if left <= 0:
                return
            time.sleep(min(0.03, left))


# =============================================================================
#  CDP - focus.py's WebSocket framing, kept open and taught to ask more than one thing
# =============================================================================

def _ws_frame(payload):
    """One masked text frame (focus.py:_ws_frame). Client frames MUST be masked."""
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
    """(opcode, payload) or None, consuming one frame from buf (focus.py:_ws_read), with
    an 8 MB cap: a page read returns text, not a single integer."""
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
    """One open DevTools WebSocket and a call() that waits for ITS answer. Any transport
    failure is Failed with a reason.

    EVENTS ARE KEPT, not skipped: the last EVENT_KEEP of them, numbered, so an action can
    ask "did a navigation START since I pressed?" (page_events()). Measured 2026-10-14 on
    Wikipedia: for ~7 s after a click on a same-site link, the old document answers no
    Runtime.evaluate at all, so a witness that only evaluates cannot tell a page that is
    navigating from a page that has hung. The browser's own Page.frameStartedLoading can.
    """

    EVENT_KEEP = 300

    def __init__(self, ws_url):
        parts = urllib.parse.urlsplit(ws_url or "")
        if parts.scheme != "ws" or not parts.hostname or not parts.path:
            raise Failed("the browser gave me no address to talk to the tab on")
        port = parts.port or 80
        path = parts.path + (("?" + parts.query) if parts.query else "")
        self._next = 0
        self.buf = bytearray()
        self.ws_url = ws_url
        self.target_id = None
        self.events = []          # [(serial, method, params)], the newest EVENT_KEEP
        self.serial = 0
        self.page_on = False
        self.main_frame = None
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
                if "method" in msg and "id" not in msg:
                    self.serial += 1
                    self.events.append((self.serial, msg["method"], msg.get("params") or {}))
                    del self.events[:-self.EVENT_KEEP]
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

    def evaluate(self, expression, gesture=False, await_promise=False,
                 timeout=CALL_TIMEOUT_S):
        """The value of one expression in the page, or None if it threw. `gesture` makes
        Chrome treat it as user-initiated - the documented way to let play() start a video
        with sound, and the reason the synthetic fallbacks below pass it."""
        res = self.call("Runtime.evaluate",
                        {"expression": expression, "returnByValue": True,
                         "userGesture": bool(gesture), "awaitPromise": bool(await_promise)},
                        timeout=timeout)
        if res.get("exceptionDetails"):
            return None
        return (res.get("result") or {}).get("value")

    def page_events(self):
        """Turn the Page domain's events on (once), and learn the main frame's id. Returns
        the serial to read from."""
        if not self.page_on:
            self.call("Page.enable", timeout=5.0)
            self.page_on = True
            try:
                tree = self.call("Page.getFrameTree", timeout=5.0)
                self.main_frame = ((tree.get("frameTree") or {}).get("frame") or {}).get("id")
            except Failed:
                self.main_frame = None
        return self.serial

    def saw_main(self, since, *methods):
        """saw(), kept to events about the MAIN frame (when its id is known)."""
        out = []
        for e in self.saw(since, *methods):
            p = e[2]
            fid = p.get("frameId") or (p.get("frame") or {}).get("id")
            if (p.get("frame") or {}).get("parentId"):
                continue
            if self.main_frame and fid and fid != self.main_frame:
                continue
            out.append(e)
        return out

    def drain(self, seconds=0.0):
        """Read whatever events have arrived, for up to `seconds`, answering nothing."""
        end = time.monotonic() + seconds
        try:
            while True:
                left = max(0.01, end - time.monotonic())
                self.sock.settimeout(left)
                frame = _ws_read(self.sock, self.buf)
                if frame is None or frame[0] == 8:
                    return
                if frame[0] != 1:
                    continue
                try:
                    msg = json.loads(frame[1].decode("utf-8", "replace"))
                except ValueError:
                    continue
                if "method" in msg and "id" not in msg:
                    self.serial += 1
                    self.events.append((self.serial, msg["method"], msg.get("params") or {}))
                    del self.events[:-self.EVENT_KEEP]
                if time.monotonic() >= end:
                    return
        except (socket.timeout, OSError):
            return

    def saw(self, since, *methods):
        """The events named, received after serial `since`."""
        return [e for e in self.events if e[0] > since and e[1] in methods]

    def close(self):
        try:
            self.sock.close()
        except Exception:                                      # noqa: BLE001
            pass


# A real document load starting IN THE MAIN FRAME (see CDP.saw_main). Not a pushState
# (navigatedWithinDocument - the document keeps answering through one), and not an iframe:
# measured on LeetCode, opening a menu fired both, and they were read as "the page moved on".
NAV_STARTED = ("Page.frameRequestedNavigation", "Page.frameStartedLoading",
               "Page.frameNavigated")


def get_json(url, method="GET", timeout=HTTP_TIMEOUT_S):
    """The answer, or None (PUT for /json/new, which Chrome refuses as a GET since 111)."""
    try:
        req = urllib.request.Request(url, method=method)
        with urllib.request.urlopen(req, timeout=timeout) as res:
            return json.loads(res.read().decode("utf-8", "replace"))
    except Exception:                                          # noqa: BLE001
        return None


def live_port(ports=PORTS):
    """(port, browser websocket url) for the first port that answers, or (None, None)."""
    for port in ports:
        found = get_json("http://127.0.0.1:%d/json/version" % port)
        if isinstance(found, dict):
            return port, found.get("webSocketDebuggerUrl")
    return None, None


def _unminimize(browser_ws, target_id):
    """Un-minimize the window holding a target, through the browser's own socket. Cosmetic
    failures are swallowed: the tab works whether or not the window could be restored."""
    if not browser_ws or not target_id:
        return
    try:
        browser = CDP(browser_ws)
        try:
            win = browser.call("Browser.getWindowForTarget", {"targetId": target_id},
                               timeout=3.0)
            if (win.get("bounds") or {}).get("windowState") == "minimized":
                browser.call("Browser.setWindowBounds",
                             {"windowId": win.get("windowId"),
                              "bounds": {"windowState": "normal"}}, timeout=3.0)
        finally:
            browser.close()
    except Failed:
        pass


def show_tab(run, tab, ws_url):
    """Bring an EXISTING tab to the front of its window, its window un-minimized.

    WHY THE GENERIC DOOR DOES THIS BEFORE IT ACTS. The employer gives the instruction from
    the Galaxy viewer - another tab - so the locked tab is usually a BACKGROUND tab at the
    moment of Yes, and a background tab does not process pointer input promptly: measured
    2026-10-14, a real press on a background tab's checkbox took ~3.5 s per event and
    delivered a mouseover and no click. A person switches to the tab before clicking in it,
    and so does this; it is also how the employer SEES the action happen. The viewer is not
    closed or navigated - it is simply no longer the tab in front.
    """
    run.at("bringing the locked page to the front")
    parts = urllib.parse.urlsplit(ws_url or "")
    target_id = parts.path.rsplit("/", 1)[-1] if parts.path else ""
    port = parts.port
    browser_ws = None
    if port:
        found = get_json("http://127.0.0.1:%d/json/version" % port)
        if isinstance(found, dict):
            browser_ws = found.get("webSocketDebuggerUrl")
        if target_id:
            get_json("http://127.0.0.1:%d/json/activate/%s" % (port, target_id), timeout=3.0)
    _unminimize(browser_ws, target_id)
    try:
        tab.call("Page.bringToFront", timeout=3.0)
    except Failed:
        pass
    # A tab that was in the background paints its first frame a beat after it is shown.
    end = time.monotonic() + 1.5
    while time.monotonic() < end:
        if tab.evaluate("document.visibilityState", timeout=2.0) == "visible":
            break
        run.nap(0.1)
    run.nap(0.15)


def open_tab(run, port, browser_ws):
    """A fresh tab, brought to the front with its window un-minimized, as a CDP session.
    A new tab, never an existing one: the viewer lives in this browser. Un-minimized via
    Browser.setWindowBounds, because Page.bringToFront does nothing for a minimized window."""
    run.at("opening a new tab")
    target = get_json("http://127.0.0.1:%d/json/new?about:blank" % port, method="PUT",
                      timeout=5.0)
    if not isinstance(target, dict) or not target.get("webSocketDebuggerUrl"):
        raise Failed("the browser would not open a new tab for me")
    tab = CDP(target["webSocketDebuggerUrl"])
    tab.target_id = target.get("id")
    get_json("http://127.0.0.1:%d/json/activate/%s" % (port, tab.target_id), timeout=3.0)
    if browser_ws:
        try:
            browser = CDP(browser_ws)
            try:
                win = browser.call("Browser.getWindowForTarget",
                                   {"targetId": tab.target_id}, timeout=3.0)
                if (win.get("bounds") or {}).get("windowState") == "minimized":
                    browser.call("Browser.setWindowBounds",
                                 {"windowId": win.get("windowId"),
                                  "bounds": {"windowState": "normal"}}, timeout=3.0)
            finally:
                browser.close()
        except Failed:
            pass                  # cosmetic: the tab works whether or not it is in view
    try:
        tab.call("Page.bringToFront", timeout=3.0)
    except Failed:
        pass
    return tab


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


def lock_state():
    """(label, locked): the session's lockedTab and whether a tab lock is live at all -
    `tabLocked`, which says so for an untitled page whose label is "". (None, False) when
    the server cannot be asked."""
    found = get_json(SERVER + "/focus", timeout=4.0)
    if not isinstance(found, dict):
        return None, False
    f = found.get("focus") or {}
    label = str(f.get("lockedTab") or "").strip()
    return label, bool(f.get("tabLocked")) or bool(label)


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


def find_locked_tab(label, verb="touch anything", url=None):
    """The one DevTools page that is the locked tab, as {ws, title, host, url}.

    The server publishes the lock's title and deliberately never its target id, so this
    joins the title to the target list the way focus.py's _cdp_active_host does: focus.py's
    three ports in their order, home base excluded. Several matches are narrowed by focused,
    then visible (_cdp_front_target's order); two left over is a refusal, never a guess.

    `url`, WHEN THE CARD CARRIES ONE, IS JOINED ON INSTEAD (Operator 1.3). The published
    title is the tab's title AT LOCK TIME, so after a click that navigates the locked tab -
    the second step of almost anything - a title join finds nothing; and an untitled page
    never had a title to join. The server reads the locked tab's address through the focus
    session's own socket when it draws the card, so the URL is the lock's, not a model's,
    and a page that has moved since the card was approved is a refusal here.
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
            where = str(t.get("url") or "")
            host = (urllib.parse.urlsplit(where).hostname or "").lower()
            if not t.get("webSocketDebuggerUrl") or not host or host in HOME_BASE_HOSTS:
                continue
            if not where.lower().startswith(("http://", "https://")):
                continue
            if (where == url) if url else (lock_label(t.get("title")) == label):
                hits.append({"ws": t["webSocketDebuggerUrl"], "host": host,
                             "title": str(t.get("title") or ""), "url": where})
        if hits:
            break
    if not alive:
        raise Failed(NO_PORT)
    if not hits:
        if url:
            raise Failed("I did not %s - the locked page is no longer at the address it had "
                         "when you approved this, so it has moved on since" % verb)
        raise Failed("I did not %s - the locked page, '%s', is not open in the browser I "
                     "can reach, or its title has changed since it was locked" % (verb, label))
    if len(hits) > 1 and url and label:
        hits = [h for h in hits if lock_label(h["title"]) == label] or hits
    if len(hits) == 1:
        return hits[0]
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
    raise Failed("I did not %s - %d tabs answer to the locked page, and I will not guess "
                 "which one you meant" % (verb, len(hits)))


# =============================================================================
#  NAVIGATING AND WAITING
# =============================================================================

INTERACTIVE_OK_S = 8.0


def navigate(run, tab, url, what):
    """Go to url and wait for document.readyState === 'complete' on THAT document - or for
    'interactive' held INTERACTIVE_OK_S, because some pages never complete: measured
    2026-10-14, github.com/login sat at 'interactive' for 24 s with its whole form drawn,
    waiting on a resource that never finished. The DOM is what this acts on, and the DOM
    is there at 'interactive'."""
    run.at(what)
    res = tab.call("Page.navigate", {"url": url}, timeout=LOAD_TIMEOUT_S)
    if res.get("errorText"):
        raise Failed("the page did not load (%s)" % res["errorText"])
    start = time.monotonic()
    end = start + LOAD_TIMEOUT_S
    while time.monotonic() < end:
        state = tab.evaluate("[document.readyState, location.href]", timeout=5.0)
        if (isinstance(state, list) and str(state[1]).startswith(("http://", "https://"))
                and (state[0] == "complete" or (state[0] == "interactive" and
                                                time.monotonic() - start > INTERACTIVE_OK_S))):
            return str(state[1])
        run.nap()
    raise Failed("the page did not finish loading within %.0f seconds" % LOAD_TIMEOUT_S)


def wait_for(run, tab, expression, timeout=FIND_TIMEOUT_S):
    """Poll an expression until it is truthy; its value, or None at the timeout."""
    end = time.monotonic() + timeout
    while True:
        value = tab.evaluate(expression, timeout=5.0)
        if value:
            return value
        if time.monotonic() >= end:
            return None
        run.nap()


# =============================================================================
#  THE PAGE LIBRARY - one script, installed once per document, that every verb below uses
# =============================================================================
#
# Installed on window under a versioned name and reused until the document changes, so a
# find and the click that follows it act on the SAME node (kept in L.picked by nonce, which
# survives shadow roots where a marker attribute and querySelector would not).
#
# THE NAMES OF A THING, each scored SEPARATELY (joined, a button whose text and aria-label
# both read "Watch Now" says "watch now watch now" and never matches exactly):
#   aria-label, aria-labelledby, <label>      weight 1.00 - what assistive tech reads
#   visible text, placeholder, value          weight 1.00 - what a person reads
#   title                                     weight 0.95
#   alt (own, or a picture inside)            weight 0.90 / 0.85
#   type=submit -> "submit", a search field -> "search"   0.85 - what it IS, unwritten
#   name / id / data-testid                   0.70 / 0.60 - a developer's word, weaker
# A name's score is how much of the ASKED words it holds (coverage) with a small bonus for
# holding little else (precision): cov * (0.75 + 0.25 * prec) * weight, or the full weight
# for an exact match. Words match on a shared stem of four letters or more, so "subscribe"
# finds "Subscribed" and "search" finds "searchbox".
#
# THE KIND OF A THING comes from its role, explicit or implied by its tag - button, link,
# field, select, checkbox, tab, option. Asking for a "button" and finding a link is common
# on the real web (0.8); finding a text field when a button was asked for is not (0.4).
#
# THE TIE-BREAKS are honest ones: in the viewport beats scrolled away, a smaller element
# beats the card that wraps it, then document order. A tie between two DIFFERENT names is
# not broken at all - the finder says it is ambiguous and the hand refuses.
_LIB_JS = r"""
(function () {
  var V = 3;
  if (window.__trOp && window.__trOp.v === V) return window.__trOp;
  var L = {v: V, picked: {}, watches: {}};
  var norm = function (s) { return String(s || '').replace(/\s+/g, ' ').trim().toLowerCase(); };
  var toks = function (s) { return norm(s).match(/[\p{L}\p{N}]+/gu) || []; };
  L.norm = norm;
  var same = function (w, t) {
    if (w === t) return true;
    if (w.length >= 4 && t.length >= 4) return t.indexOf(w) === 0 || w.indexOf(t) === 0;
    return false;
  };
  // Every element, light DOM and every OPEN shadow root, in document order (a host's
  // shadow contents follow the host). Closed roots cannot be entered by anyone.
  var everything = function () {
    var out = [];
    var walk = function (root) {
      var all = root.querySelectorAll('*');
      for (var i = 0; i < all.length; i++) {
        out.push(all[i]);
        if (all[i].shadowRoot) walk(all[i].shadowRoot);
      }
    };
    walk(document);
    return out;
  };
  L.everything = everything;
  // OPACITY IS NOT ASKED OF A FORM CONTROL. A native <select>, checkbox or file input laid
  // at opacity 0 over a styled fake is the real control and takes the real click - measured
  // on www.wikipedia.org's language picker, which an opacity check filtered out entirely.
  // CLIPPED AWAY IS NOT VISIBLE (Operator 1.4). Measured on LeetCode: the topic-tag links
  // sit inside a COLLAPSED accordion - their own box is 73x24, but an ancestor with
  // overflow:hidden is 0 px tall - and the finder offered a card for a link no person can
  // see; the click then landed on what was actually there. So the box is intersected with
  // every clipping ancestor (overflow other than visible), up to the page's own scroller.
  var clipCache = new Map();
  // 'hide' for overflow hidden/clip (what is outside is gone), 'scroll' for auto/scroll
  // (what is outside is a scroll away - LeetCode's description pane - and still findable,
  // unless the scroller itself has collapsed to nothing), '' for visible.
  var clips = function (p) {
    if (clipCache.has(p)) return clipCache.get(p);
    var cs = getComputedStyle(p), o = cs.overflowX + ' ' + cs.overflowY;
    var c = /hidden|clip/.test(o) ? 'hide' : /auto|scroll/.test(o) ? 'scroll' : '';
    clipCache.set(p, c);
    return c;
  };
  var unclipped = function (el, r) {
    var left = r.left, top = r.top, right = r.right, bottom = r.bottom;
    for (var p = el.parentElement, k = 0; p && p !== document.body && p !== document.documentElement && k < 40; p = p.parentElement, k++) {
      var kind = clips(p);
      if (!kind) continue;
      var pr = p.getBoundingClientRect();
      if (kind === 'scroll') {
        if (pr.width < 2 || pr.height < 2) return false;
        // Past a scroller, the element is as good as scrolled into ITS view: what clips
        // from here on clips the scroller, not where the element happens to sit now.
        left = pr.left; top = pr.top; right = pr.right; bottom = pr.bottom;
        continue;
      }
      left = Math.max(left, pr.left); top = Math.max(top, pr.top);
      right = Math.min(right, pr.right); bottom = Math.min(bottom, pr.bottom);
      if (right - left < 2 || bottom - top < 2) return false;
    }
    return true;
  };
  var visible = function (el) {
    var r = el.getBoundingClientRect();
    if (r.width < 2 || r.height < 2) return false;
    var control = /^(SELECT|INPUT)$/.test(el.tagName);
    if (el.checkVisibility && !el.checkVisibility({opacityProperty: !control,
                                                    visibilityProperty: true})) return false;
    return unclipped(el, r);
  };
  L.visible = visible;
  var inView = function (r) {
    return r.bottom > 0 && r.right > 0 && r.top < innerHeight && r.left < innerWidth;
  };
  var TEXTY = /^(text|search|email|url|tel|password|number|)$/;
  var roleOf = function (el) {
    var r = (el.getAttribute('role') || '').toLowerCase().split(' ')[0];
    var tag = el.tagName, type = (el.getAttribute('type') || '').toLowerCase();
    var popup = (el.getAttribute('aria-haspopup') || '').toLowerCase() === 'listbox';
    if (r === 'combobox') return (tag === 'INPUT' || tag === 'TEXTAREA' || el.isContentEditable) ? 'field' : 'select';
    if (r === 'searchbox' || r === 'textbox') return 'field';
    if (r === 'button' || r === 'menuitem' || r === 'menuitemradio' || r === 'menuitemcheckbox')
      return popup ? 'select' : 'button';
    if (r === 'link') return 'link';
    if (r === 'checkbox' || r === 'switch' || r === 'radio') return 'checkbox';
    if (r === 'tab') return 'tab';
    if (r === 'option') return 'option';
    if (r === 'listbox') return 'select';
    if (r === 'heading' || /^H[1-6]$/.test(tag)) return 'heading';
    if (tag === 'A' && el.hasAttribute('href')) return 'link';
    if (tag === 'BUTTON') return popup ? 'select' : 'button';
    if (tag === 'SUMMARY') return 'button';
    if (tag === 'SELECT') return 'select';
    if (tag === 'TEXTAREA') return 'field';
    if (tag === 'OPTION') return 'option';
    if (tag === 'INPUT') {
      if (/^(button|submit|reset|image)$/.test(type)) return 'button';
      if (/^(checkbox|radio)$/.test(type)) return 'checkbox';
      if (TEXTY.test(type)) return 'field';
      return 'other';
    }
    if (el.isContentEditable && !(el.parentElement && el.parentElement.isContentEditable)) return 'field';
    if (el.hasAttribute('onclick') || (el.tabIndex >= 0 && el.hasAttribute('tabindex'))) return 'button';
    return 'other';
  };
  L.roleOf = roleOf;
  var rootOf = function (el) { var n = el.getRootNode(); return n.getElementById ? n : document; };
  var namesOf = function (el, role) {
    var out = [], tag = el.tagName, type = (el.getAttribute('type') || '').toLowerCase();
    var add = function (src, t, w) { t = norm(t); if (t && t.length <= 400) out.push({src: src, t: t, w: w}); };
    add('aria-label', el.getAttribute('aria-label'), 1);
    var lb = el.getAttribute('aria-labelledby');
    if (lb) add('aria-labelledby', lb.split(/\s+/).map(function (id) {
      var n = rootOf(el).getElementById(id); return n ? n.textContent : ''; }).join(' '), 1);
    if (el.labels) for (var i = 0; i < el.labels.length; i++) add('label', el.labels[i].innerText, 1);
    // A field's innerText is its CONTENT, not its name - a contenteditable that holds a
    // draft is not named by the draft.
    if (role !== 'field' && role !== 'select') add('text', el.innerText, 1);
    if (tag === 'SELECT') {
      var so = el.options && el.options[el.selectedIndex];
      if (so) add('text', so.text, 0.9);
    }
    add('title', el.getAttribute('title'), 0.95);
    add('placeholder', el.getAttribute('placeholder') || el.getAttribute('aria-placeholder'), 1);
    add('alt', el.getAttribute('alt'), 0.9);
    var img = el.querySelector && el.querySelector('img[alt]');
    if (img) add('alt', img.getAttribute('alt'), 0.85);
    if (tag === 'INPUT' && /^(button|submit|reset)$/.test(type)) add('value', el.value, 1);
    if (type === 'submit' || (tag === 'BUTTON' && el.form && (type === '' || type === 'submit')))
      add('kind', 'submit', 0.85);
    if (role === 'field' && (type === 'search' || (el.getAttribute('role') || '') === 'searchbox' ||
        (el.closest && el.closest('[role=search], form[action*=search i], form[class*=search i]'))))
      add('kind', 'search', 0.85);
    var dev = function (s) { return String(s || '').replace(/([a-z])([A-Z])/g, '$1 $2').replace(/[_\-.:]+/g, ' '); };
    add('name', dev(el.getAttribute('name')), 0.7);
    add('id', dev(el.id), 0.6);
    add('testid', dev(el.getAttribute('data-testid')), 0.6);
    return out;
  };
  L.namesOf = namesOf;
  var textScore = function (names, words, exact) {
    var best = {s: 0, name: '', src: ''};
    names.forEach(function (n) {
      var s = 0;
      if (exact) {
        // WHOLE WORDS, and a name that STARTS with the phrase ranks first (Operator 1.4).
        // Measured on Hotstar: "watch" matched "Add to watchlist" as a substring, tied
        // with "Watch Latest Season S3 E1", and the tie refusal pressed nothing at all.
        var et = toks(exact), nw = toks(n.t);
        if (n.t === exact) s = 1;
        else if (et.length && nw.length) {
          var hit = -1;
          for (var q = 0; q + et.length <= nw.length; q++) {
            if (nw.slice(q, q + et.length).join(' ') === et.join(' ')) { hit = q; break; }
          }
          if (hit >= 0) s = (hit === 0 ? 0.9 : 0.85) * (0.75 + 0.25 * et.length / nw.length);
        } else if (n.t.indexOf(exact) >= 0) {
          s = 0.85 * (0.75 + 0.25 * exact.length / n.t.length);   // no word to match on
        }
      } else if (words.length) {
        if (n.t === words.join(' ')) s = 1;
        else {
          var nt = toks(n.t);
          if (!nt.length) return;
          // "E-mail" is two tokens and "email" is one word: neighbours are also tried
          // joined, so the hyphen a site chose does not decide whether it is found.
          var joined = nt.slice(1).map(function (t, k) { return nt[k] + t; });
          // A word found EXACTLY counts 1; found only by a shared stem, 0.85. Measured on
          // LeetCode's language list: "python3" matched both "Python3" and "Python" by stem,
          // scored them equal, and the finder - correctly, on those numbers - refused a tie
          // that an exact match should have won outright.
          var all2 = nt.concat(joined);
          var cov = words.reduce(function (acc, w) {
            return acc + (all2.indexOf(w) >= 0 ? 1 : all2.some(function (t) { return same(w, t); }) ? 0.85 : 0);
          }, 0) / words.length;
          var prec = nt.filter(function (t, k) { return words.some(function (w) {
            return same(w, t) || (k + 1 < nt.length && same(w, t + nt[k + 1])) || (k > 0 && same(w, nt[k - 1] + t)); }); }).length / nt.length;
          s = cov * (0.75 + 0.25 * prec);
        }
      }
      s *= n.w;
      if (s > best.s) best = {s: s, name: n.t, src: n.src};
    });
    return best;
  };
  var COMPAT = {
    button: {button: 1, link: 0.8, select: 0.7, checkbox: 0.6, tab: 0.75, option: 0.6},
    link: {link: 1, button: 0.8, tab: 0.75},
    result: {link: 1, button: 0.6},
    field: {field: 1, select: 0.6},
    select: {select: 1, button: 0.7, field: 0.7},
    checkbox: {checkbox: 1, button: 0.6},
    tab: {tab: 1, button: 0.75, link: 0.75},
    option: {option: 1, button: 0.6, link: 0.6},
    heading: {heading: 1, link: 0.6, tab: 0.6, button: 0.5}
  };
  var CHROME = 'header, nav, footer, [role=banner], [role=navigation], [role=contentinfo], ' +
               '[role=search], aside, [role=complementary]';
  var nameFor = function (el, role) {
    var n = namesOf(el, role).filter(function (x) { return /^(aria|label|text|title|placeholder|alt|value)/.test(x.src); })[0];
    return n ? n.t : '';
  };
  L.nameFor = nameFor;

  // o: {words, exact, role, ordinal, skip, within, hrefHas, hrefNot, outsideChrome, nonce}
  L.find = function (o) {
    var words = (o.words || []).map(norm).filter(Boolean);
    var exact = norm(o.exact);
    var want = o.role || '';
    var within = o.within ? document.querySelector(o.within) : null;
    var all = everything(), cands = [], roleCount = 0, soleCand = null;
    for (var i = 0; i < all.length; i++) {
      var el = all[i];
      var role = roleOf(el);
      if (role === 'other') continue;
      // A heading is somewhere to SCROLL to, never something to press: it is a candidate
      // only when the caller says so (the scroll verb) or asked for a heading by name.
      if (role === 'heading' && !o.headings && want !== 'heading') continue;
      if (within && !within.contains(el)) continue;
      if (o.skip && el.closest && el.closest(o.skip)) continue;
      if (el.closest && el.closest('[data-op-ignore]')) continue;
      if (o.outsideChrome && el.closest && el.closest(CHROME)) continue;
      if (o.hrefHas && String(el.getAttribute('href') || '').indexOf(o.hrefHas) < 0) continue;
      if (o.hrefNot && String(el.getAttribute('href') || '').indexOf(o.hrefNot) >= 0) continue;
      if (!visible(el)) continue;
      var rf = want ? ((COMPAT[want] || {})[role] || 0.4) : 1;
      var ts = (words.length || exact) ? textScore(namesOf(el, role), words, exact)
                                       : {s: 0.8, name: nameFor(el, role), src: 'role'};
      if (want === 'result' && role === 'link' && toks(ts.name).length < 2 && !exact) ts.s *= 0.7;
      var r = el.getBoundingClientRect(), iv = inView(r);
      var conf = ts.s * rf * (iv ? 1 : 0.97);
      var cand = {el: el, i: i, conf: conf, role: role, name: ts.name || nameFor(el, role),
                  src: ts.src, iv: iv, area: r.width * r.height,
                  disabled: !!(el.disabled || el.getAttribute('aria-disabled') === 'true'),
                  type: (el.getAttribute('type') || '').toLowerCase(), tag: el.tagName.toLowerCase(),
                  href: String(el.getAttribute('href') || '').slice(0, 300)};
      if (want && rf >= 0.99) { roleCount++; soleCand = cand; }
      if (conf <= 0.05) continue;
      cands.push(cand);
    }
    // THE POINTER FALLBACK, for controls that are only a <div> with a click handler and no
    // role (measured: LeetCode's Description / Editorial tabs). Only when words were asked
    // for and nothing with a role carries them: a text node holding the words, climbed at
    // most four levels to the outermost element styled cursor:pointer - which is how the
    // page itself tells a person "this is clickable". Weaker evidence, scored 0.85.
    // Never when the caller said what a match must LINK to (hrefHas) - a div is not a
    // link, and measured on YouTube's results, a Shorts tile's clickable <div> was taken
    // as "the first result" by exactly this path when no /watch link had loaded yet.
    // Run whenever nothing with a role is a NEAR-EXACT match (0.9), not only when nothing is
    // confident: measured on LeetCode, a control whose long description merely mentioned
    // "topics" (0.78) beat the visible role-less chip that reads exactly "Topics" (0.85),
    // because the chip was never looked at.
    if ((words.length || exact) && want !== 'field' && want !== 'select' && !o.hrefHas &&
        !cands.some(function (c) { return c.conf >= 0.9; })) {
      var seenP = new Set(), tw = document.createTreeWalker(within || document.body, NodeFilter.SHOW_TEXT), tn;
      var probe = exact || words.join(' ');
      var n0 = 0;
      while ((tn = tw.nextNode()) && n0 < 4000) {
        n0++;
        var hit0 = norm(tn.data);
        if (!hit0 || hit0.length > 200) continue;
        if (!(exact ? hit0.indexOf(exact) >= 0 : words.some(function (w) { return toks(hit0).some(function (t) { return same(w, t); }); })))
          continue;
        var e0 = tn.parentElement, ptr = null;
        for (var up = 0; e0 && up < 5; up++, e0 = e0.parentElement) {
          if (getComputedStyle(e0).cursor === 'pointer') ptr = e0;
          else if (ptr) break;
        }
        if (!ptr || seenP.has(ptr) || roleOf(ptr) !== 'other' || !visible(ptr)) continue;
        if (o.skip && ptr.closest(o.skip)) continue;
        if (o.outsideChrome && ptr.closest(CHROME)) continue;
        if (within && !within.contains(ptr)) continue;
        seenP.add(ptr);
        var tsP = textScore([{src: 'text', t: norm(ptr.innerText), w: 1}], words, exact);
        var rP = ptr.getBoundingClientRect(), ivP = inView(rP);
        var cP = tsP.s * 0.85 * (want && want !== 'button' && want !== 'tab' ? 0.8 : 1) * (ivP ? 1 : 0.97);
        if (cP > 0.05) cands.push({el: ptr, i: all.indexOf(ptr), conf: cP, role: 'button', name: tsP.name,
                                   src: 'pointer', iv: ivP, area: rP.width * rP.height, disabled: false,
                                   type: '', tag: ptr.tagName.toLowerCase(), href: ''});
      }
    }
    // THE CURRENT VALUE (Operator 1.4). A picker that never names its own kind - LeetCode's
    // language button reads "Python3", and nothing on it says "language" - is found by WHAT
    // IT SHOWS: when the ask implies a kind of value (o.values: the language names, the
    // themes...), a control that opens something (a <select>, a combobox, a button with
    // aria-haspopup or aria-expanded) whose current text IS one of those values is that
    // picker. Only when nothing above was confident, and only on an exact value.
    if (o.values && o.values.length && !cands.some(function (c) { return c.conf >= o.threshold; })) {
      var vals = o.values.map(norm);
      for (var vi = 0; vi < all.length; vi++) {
        var ve = all[vi], vr = roleOf(ve);
        var opener = vr === 'select' || (vr === 'button' &&
                     (ve.hasAttribute('aria-haspopup') || ve.hasAttribute('aria-expanded')));
        if (!opener || !visible(ve)) continue;
        if (o.skip && ve.closest(o.skip)) continue;
        var shows = ve.tagName === 'SELECT' ? norm((ve.options[ve.selectedIndex] || {}).text)
                                            : norm(ve.innerText || ve.textContent);
        if (!shows || vals.indexOf(shows) < 0) continue;
        var vrr = ve.getBoundingClientRect();
        cands.push({el: ve, i: vi, conf: 0.75, role: 'select', name: shows, src: 'current value',
                    iv: inView(vrr), area: vrr.width * vrr.height, disabled: !!ve.disabled,
                    type: '', tag: ve.tagName.toLowerCase(), href: ''});
      }
    }
    // A thing nested inside another candidate with the SAME name is the same control said
    // twice (an <a> inside a role=button card); the inner, tighter one is kept.
    cands = cands.filter(function (c) {
      return !cands.some(function (d) { return d !== c && c.el.contains(d.el) && d.conf >= c.conf - 0.02; });
    });
    // THE ONLY ONE. A field or a dropdown asked for by words that match nothing, on a page
    // with exactly one of that kind visible, is that one - but only just over the dial,
    // and it says why. Never for buttons or links: there is never only one of those.
    // Measured: Hotstar's search page has one input, placeholder "Movies, shows and more",
    // with no word "search" on it anywhere - it scores 0 on the words and is still the box.
    var sole = '';
    if ((want === 'field' || want === 'select') && roleCount === 1 && soleCand &&
        !cands.some(function (c) { return c.conf >= 0.6 && c.role === want; })) {
      soleCand.conf = Math.max(soleCand.conf, 0.62);
      soleCand.src = 'the only one';
      if (cands.indexOf(soleCand) < 0) cands.push(soleCand);
      sole = want;
    }
    var picked = null;
    if (o.ordinal) {
      var pool = cands.filter(function (c) { return c.conf >= o.threshold; })
                      .sort(function (a, b) { return a.i - b.i; });
      picked = o.ordinal > 0 ? pool[o.ordinal - 1] : pool[pool.length + o.ordinal];
      cands = (picked ? [picked] : []).concat(pool.filter(function (c) { return c !== picked; }));
    } else {
      cands.sort(function (a, b) {
        return (b.conf - a.conf) || ((b.iv ? 1 : 0) - (a.iv ? 1 : 0)) || (a.area - b.area) || (a.i - b.i);
      });
      picked = cands[0] || null;
    }
    var out = cands.slice(0, 6).map(function (c) {
      return {conf: Math.round(c.conf * 1000) / 1000, role: c.role, name: c.name.slice(0, 120),
              src: c.src, inView: c.iv, disabled: c.disabled, type: c.type, tag: c.tag,
              href: c.href};
    });
    if (picked && o.nonce) L.picked[o.nonce] = picked.el;
    return {ranked: out, sole: sole, count: cands.length};
  };

  // THE POINT TO PRESS. The centre if nothing covers it; else the first of a few points
  // inside it that is uncovered; else null, and the caller takes a path that needs no
  // point at all. elementFromPoint is followed down open shadow roots.
  var deepAt = function (x, y) {
    var t = document.elementFromPoint(x, y);
    while (t && t.shadowRoot) {
      var inner = t.shadowRoot.elementFromPoint(x, y);
      if (!inner || inner === t) break;
      t = inner;
    }
    return t;
  };
  var hits = function (el, t) { return !!t && (t === el || el.contains(t) || (t.contains(el) && t !== document.body && t !== document.documentElement)); };
  L.spot = function (nonce, scroll) {
    var el = L.picked[nonce];
    if (!el || !el.isConnected) return {gone: true};
    if (scroll) el.scrollIntoView({block: 'center', inline: 'center', behavior: 'instant'});
    var r = el.getBoundingClientRect();
    var pts = [[0.5, 0.5], [0.3, 0.5], [0.7, 0.5], [0.5, 0.3], [0.5, 0.7], [0.15, 0.5]];
    for (var k = 0; k < pts.length; k++) {
      var x = Math.round(r.left + r.width * pts[k][0]), y = Math.round(r.top + r.height * pts[k][1]);
      if (x < 0 || y < 0 || x >= innerWidth || y >= innerHeight) continue;
      var t = deepAt(x, y);
      if (hits(el, t)) return {x: x, y: y, clear: true, inView: true};
    }
    var c = deepAt(Math.round(r.left + r.width / 2), Math.round(r.top + r.height / 2));
    return {clear: false, inView: inView(r), cover: c ? nameFor(c, roleOf(c)).slice(0, 60) || c.tagName.toLowerCase() : ''};
  };

  // THE WITNESS. Armed before an action, read after it: did the target RECEIVE the event
  // (composedPath contains it), was the event TRUSTED, and what changed - the address,
  // the title, the target's own state and name, the page's DOM, where focus went.
  var stateOf = function (el) {
    if (!el) return {};
    return {name: nameFor(el, roleOf(el)), pressed: el.getAttribute('aria-pressed'),
            expanded: el.getAttribute('aria-expanded'), checked: el.getAttribute('aria-checked'),
            selected: el.getAttribute('aria-selected'), cb: el.checked === undefined ? null : el.checked,
            value: el.value === undefined ? null : String(el.value).slice(0, 500),
            connected: el.isConnected};
  };
  var deepActive = function () {
    var a = document.activeElement;
    while (a && a.shadowRoot && a.shadowRoot.activeElement) a = a.shadowRoot.activeElement;
    return a;
  };
  L.deepActive = deepActive;
  L.arm = function (nonce) {
    var el = L.picked[nonce];
    var w = {got: [], muts: 0, before: stateOf(el), href: location.href, title: document.title,
             active: deepActive()};
    var onEv = function (ev) {
      var path = ev.composedPath ? ev.composedPath() : [ev.target];
      var into = !!el && path.indexOf(el) >= 0;
      var t = path[0];
      w.got.push({type: ev.type, trusted: ev.isTrusted, into: into,
                  on: into ? '' : (t && t.nodeType === 1 ? (nameFor(t, roleOf(t)) || t.tagName.toLowerCase()).slice(0, 60) : '')});
    };
    ['click', 'mousedown', 'pointerdown', 'keydown', 'input', 'change', 'mouseover', 'wheel'].forEach(function (k) { window.addEventListener(k, onEv, true); });
    var mo = new MutationObserver(function (list) {
      for (var i = 0; i < list.length; i++) {
        var m = list[i];
        if (m.type === 'attributes' && /^data-op-/.test(m.attributeName || '')) continue;
        w.muts++;
      }
    });
    mo.observe(document, {subtree: true, childList: true, attributes: true, characterData: true});
    w.stop = function () {
      ['click', 'mousedown', 'pointerdown', 'keydown', 'input', 'change', 'mouseover', 'wheel'].forEach(function (k) { window.removeEventListener(k, onEv, true); });
      mo.disconnect();
    };
    L.watches[nonce] = w;
    return true;
  };
  L.effects = function (nonce, keep) {
    var w = L.watches[nonce], el = L.picked[nonce];
    if (!w) return null;
    var after = stateOf(el), changed = [];
    ['name', 'pressed', 'expanded', 'checked', 'selected', 'cb', 'value', 'connected'].forEach(function (k) {
      if (String(w.before[k]) !== String(after[k])) changed.push(k);
    });
    var res = {got: w.got.slice(0, 40), muts: w.muts, changed: changed,
               nameNow: (after.name || '').slice(0, 80), valueNow: after.value,
               href: location.href !== w.href, title: document.title !== w.title,
               focus: deepActive() !== w.active, hover: !!el && el.matches(':hover')};
    if (!keep) { w.stop(); delete L.watches[nonce]; }
    return res;
  };

  // FIELDS. What is in one, whether it has the keyboard, and selecting its contents so the
  // next insertion REPLACES them (a search box that kept yesterday's query is the case).
  L.fieldValue = function (nonce) {
    var el = L.picked[nonce];
    if (!el) return null;
    var v = (el.value !== undefined && el.tagName !== 'BUTTON') ? el.value : el.innerText;
    var a = deepActive();
    return {value: String(v == null ? '' : v), focused: !!a && (a === el || el.contains(a)),
            password: (el.getAttribute('type') || '').toLowerCase() === 'password'};
  };
  L.selectAll = function (nonce) {
    var el = L.picked[nonce];
    if (!el) return false;
    if (el.select && el.value !== undefined) { el.select(); return true; }
    if (el.isContentEditable) {
      var rg = document.createRange(); rg.selectNodeContents(el);
      var s = getSelection(); s.removeAllRanges(); s.addRange(rg); return true;
    }
    return false;
  };
  L.focus = function (nonce) { var el = L.picked[nonce]; if (!el) return false; el.focus(); return true; };
  // THE FIELD THAT TOOK OVER. Some search boxes are a stand-in that, clicked, hands the
  // cursor to a different input drawn in its place (measured: Wikipedia's Vector 2022). If
  // what has the keyboard now is a text field and the one clicked is gone or hidden, or
  // the new one sits where it was, that field IS the box - adopt it under the same nonce.
  L.adoptActive = function (nonce) {
    var old = L.picked[nonce], a = deepActive();
    if (!a || a === document.body || roleOf(a) !== 'field' || !visible(a)) return null;
    var ok = !old || !old.isConnected || !visible(old);
    if (!ok) {
      var r1 = old.getBoundingClientRect(), r2 = a.getBoundingClientRect();
      var ix = Math.max(0, Math.min(r1.right, r2.right) - Math.max(r1.left, r2.left));
      var iy = Math.max(0, Math.min(r1.bottom, r2.bottom) - Math.max(r1.top, r2.top));
      ok = ix * iy > 0.3 * Math.min(r1.width * r1.height, r2.width * r2.height);
    }
    if (!ok) return null;
    L.picked[nonce] = a;
    return {name: nameFor(a, 'field')};
  };
  // The native setter, then input and change: how a framework-controlled field is told a
  // value changed when no real input path landed. SYNTHETIC, and reported as such.
  L.setValue = function (nonce, text) {
    var el = L.picked[nonce];
    if (!el) return false;
    if (el.isContentEditable) { el.textContent = text; }
    else {
      var proto = el.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
      var d = Object.getOwnPropertyDescriptor(proto, 'value');
      if (d && d.set) d.set.call(el, text); else el.value = text;
    }
    el.dispatchEvent(new Event('input', {bubbles: true, composed: true}));
    el.dispatchEvent(new Event('change', {bubbles: true, composed: true}));
    return true;
  };
  L.domClick = function (nonce) { var el = L.picked[nonce]; if (!el) return false; el.click(); return true; };
  L.mouseOver = function (nonce) {
    var el = L.picked[nonce];
    if (!el) return false;
    ['pointerover', 'pointerenter', 'mouseover', 'mouseenter'].forEach(function (k) {
      el.dispatchEvent(new MouseEvent(k, {bubbles: k.indexOf('enter') < 0, composed: true}));
    });
    return true;
  };
  L.rect = function (nonce) {
    var el = L.picked[nonce];
    if (!el || !el.isConnected) return null;
    var r = el.getBoundingClientRect();
    return {top: r.top, bottom: r.bottom, h: innerHeight, w: innerWidth,
            inView: r.top >= 0 && r.bottom <= innerHeight + 1 && r.height > 0,
            partly: r.bottom > 0 && r.top < innerHeight};
  };
  L.scrollIntoView = function (nonce) {
    var el = L.picked[nonce]; if (!el) return false;
    el.scrollIntoView({block: 'center', behavior: 'instant'}); return true;
  };

  // NATIVE <select>: its options by name, and which one is chosen now.
  L.options = function (nonce) {
    var el = L.picked[nonce];
    if (!el || el.tagName !== 'SELECT') return null;
    return {index: el.selectedIndex, value: el.value,
            options: Array.prototype.map.call(el.options, function (op, i) {
              return {i: i, text: norm(op.text), label: String(op.text).trim(), value: op.value,
                      disabled: op.disabled}; })};
  };
  L.setIndex = function (nonce, i) {
    var el = L.picked[nonce];
    if (!el || el.tagName !== 'SELECT') return false;
    el.selectedIndex = i;
    el.dispatchEvent(new Event('input', {bubbles: true, composed: true}));
    el.dispatchEvent(new Event('change', {bubbles: true, composed: true}));
    return true;
  };
  window.__trOp = L;
  return L;
})()
"""


# THE LIBRARY'S VERSION IS ITS OWN HASH (Operator 1.4). It is cached on window between
# calls, and with a hand-numbered version a page that was open before an update went on
# running the OLD finder - measured: a fix to visibility read as no fix at all on a LeetCode
# tab that had been open for an hour. Any change to the text now reinstalls it.
_LIB_JS = _LIB_JS.replace("var V = 3;", "var V = '%s';" % hashlib.sha1(
    _LIB_JS.encode("utf-8")).hexdigest()[:12], 1)


def lib_call(tab, expr, gesture=False, timeout=6.0):
    """Install the page library if this document does not have it, then evaluate `expr`
    with `L` bound to it. One round trip either way."""
    return tab.evaluate("(function(){var L=%s;return (%s);})()" % (_LIB_JS.strip(), expr),
                        gesture=gesture, timeout=timeout)


# =============================================================================
#  THE FINDER - a plain description in, one confident candidate out (or a reason)
# =============================================================================

# What a person calls a kind of thing, mapped to the finder's kinds. Words that are about
# the KIND are taken out of the words to match: "the subscribe button" looks for "subscribe"
# among buttons, not for the word "button" in anybody's label.
ROLE_WORDS = {
    "button": "button", "buttons": "button", "btn": "button", "icon": "button",
    "link": "link", "links": "link",
    "result": "result", "results": "result", "video": "result", "videos": "result",
    "item": "result", "card": "result", "tile": "result", "entry": "result",
    "box": "field", "field": "field", "input": "field", "textbox": "field",
    "textarea": "field", "searchbox": "field", "bar": "field",
    "dropdown": "select", "drop-down": "select", "select": "select", "picker": "select",
    "combobox": "select", "selector": "select",
    "checkbox": "checkbox", "tickbox": "checkbox", "toggle": "checkbox", "switch": "checkbox",
    "radio": "checkbox",
    "tab": "tab", "option": "option",
    "heading": "heading", "section": "heading",
}
# Two-word kinds, folded before the single words are read.
ROLE_PHRASES = (("drop down", "dropdown"), ("check box", "checkbox"), ("tick box", "tickbox"),
                ("text box", "textbox"), ("text field", "field"), ("input field", "field"),
                ("search bar", "search box"), ("text area", "textarea"))
# Only words that are never PART of a name. Prepositions stay, because they usually are:
# measured on YouTube, a stopword "in" turned "the sign in button" into a search for
# "sign", and "Sign in" then scored 0.70 instead of 1.0. "add to cart", "log in", "save for
# later" are the same case. Where a phrase only says WHERE ("on the page", "at the top")
# it is cut whole by _WHERE_RE before any word is read.
STOPWORDS = frozenset("""the a an this that these those please my your its it there here
    called named labelled labeled label says saying which one thing""".split())
_WHERE_RE = re.compile(r"\s+(?:(?:on|in|at|of|from)\s+(?:the\s+|this\s+)?"
                       r"(?:page|site|website|web\s*page|screen|tab|top|bottom|left|right|"
                       r"header|footer|sidebar|corner)(?:\s+of\s+the\s+(?:page|screen))?)+\s*$",
                       re.I)
ORDINALS = {"first": 1, "1st": 1, "second": 2, "2nd": 2, "third": 3, "3rd": 3, "fourth": 4,
            "4th": 4, "fifth": 5, "5th": 5, "last": -1, "top": 1}


# WHAT A KIND OF PICKER SHOWS (Operator 1.4, item 2). Generic vocabularies, not any one
# site's: the names a language picker, a theme switch or a quality menu displays. A kind
# word in the description ("the language dropdown") lets the finder recognise the picker
# by its current value; a value in an ask ("switch to java") names the kind.
VALUE_KINDS = {
    "language": ("c", "c++", "c#", "java", "python", "python3", "javascript", "typescript",
                 "php", "swift", "kotlin", "dart", "go", "golang", "ruby", "scala", "rust",
                 "racket", "erlang", "elixir", "r", "perl", "haskell", "lua", "bash", "shell",
                 "mysql", "ms sql server", "oracle", "postgresql", "pandas", "sql", "html",
                 "css", "json", "yaml", "markdown", "plain text", "english", "hindi",
                 "deutsch", "espanol", "francais", "italiano", "portugues", "nederlands",
                 "japanese", "chinese", "korean", "russian", "arabic"),
    "theme": ("light", "dark", "system", "auto", "default", "high contrast"),
    "quality": ("auto", "144p", "240p", "360p", "480p", "720p", "1080p", "1440p", "2160p",
                "4k", "low", "medium", "high", "full hd", "hd"),
    "speed": ("0.25", "0.5", "0.75", "normal", "1", "1x", "1.25", "1.5", "1.75", "2", "2x"),
    "sort": ("relevance", "newest", "oldest", "most recent", "most popular", "popular",
             "top", "trending", "price: low to high", "price: high to low", "rating"),
}


def kind_of_value(text):
    """The VALUE_KINDS kind whose vocabulary holds `text` exactly ("java" -> "language"),
    or ""."""
    t = " ".join(str(text or "").split()).lower()
    t = unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode("ascii")
    for kind, values in VALUE_KINDS.items():
        if t in values:
            return kind
    return ""


def parse_target(description):
    """{"words", "exact", "role", "ordinal"} for a plain description. Pure; the server uses
    it for the card and the hand for the run, so both read the description the same way.

        "the subscribe button"      -> words [subscribe], role button
        "the search box"            -> words [search], role field
        'the "Sign in" link'        -> exact "sign in", role link
        "the first result"          -> words [], role result, ordinal 1
        "the second video"          -> role result, ordinal 2
    """
    raw = " ".join(str(description or "").split())
    exact = ""
    quoted = re.search(r"[\"\u201c\u2018']([^\"\u201d\u2019']{1,80})[\"\u201d\u2019']", raw)
    if quoted:
        exact = quoted.group(1).strip().lower()
        raw = (raw[:quoted.start()] + " " + raw[quoted.end():]).strip()
    text = _WHERE_RE.sub("", " " + raw.lower()).strip()
    for two, one in ROLE_PHRASES:
        text = re.sub(r"\b%s\b" % re.escape(two), one, text)
    role, ordinal, words = "", 0, []
    for tok in re.findall(r"[\w][\w'+#.-]*", text, re.UNICODE):
        tok = tok.strip(".'")
        if not tok:
            continue
        if tok in ORDINALS and not ordinal:
            ordinal = ORDINALS[tok]
            continue
        if tok in ROLE_WORDS:
            role = ROLE_WORDS[tok]          # the LAST kind-word wins: "search box button"
            continue
        if tok in STOPWORDS:
            continue
        words.append(tok)
    if ordinal and not role:
        role = "result"
    kinds = [w for w in words if w in VALUE_KINDS]
    values = list(VALUE_KINDS[kinds[0]]) if kinds else []
    return {"words": words, "exact": exact, "role": role, "ordinal": ordinal,
            "values": values}


def norm_name(text):
    """A found name as the page library normalises it: lowercased, whitespace collapsed."""
    return " ".join(str(text or "").split()).lower()


def describe_target(description):
    """The description, tidied for a sentence: "the subscribe button"."""
    d = " ".join(str(description or "").split()).strip(" .")
    return d if re.match(r"(?i)^(the|a|an|this|that|my|your)\b", d) else "the " + d


def find_target(tab, description, threshold=THRESHOLD, call_timeout=8.0, **how):
    """One look at the page. Returns a dict:

        ok        True when the top candidate clears `threshold`, is not tied with a
                  DIFFERENT name, and is not disabled
        why       when not ok: "nothing" | "unsure" | "tie" | "disabled"
        pick      the chosen candidate (name, role, conf, ...) - present even when not ok,
                  so the refusal can name the nearest miss
        ranked    the top six, for the developer's stderr
        nonce     the handle the executor uses; the page holds the node under it

    `how` passes straight to the page: skip (a selector of regions to pass over, e.g. a
    site layer's adverts), within, href_has, href_not, outside_chrome, and the parsed
    fields may be overridden (words, exact, role, ordinal).
    """
    spec = parse_target(description)
    for key in ("words", "exact", "role", "ordinal"):
        if how.get(key) is not None:
            spec[key] = how.pop(key)
    nonce = base64.b16encode(os.urandom(5)).decode("ascii")
    opts = {"words": spec["words"], "exact": spec["exact"], "role": spec["role"],
            "ordinal": spec["ordinal"], "threshold": threshold, "nonce": nonce,
            "skip": how.get("skip"), "within": how.get("within"),
            "hrefHas": how.get("href_has"), "hrefNot": how.get("href_not"),
            "outsideChrome": bool(how.get("outside_chrome")),
            "headings": bool(how.get("headings")),
            "values": list(how.get("values") or spec.get("values") or [])}
    found = lib_call(tab, "L.find(%s)" % json.dumps(opts), timeout=call_timeout)
    ranked = list((found or {}).get("ranked") or [])
    out = {"ok": False, "why": "nothing", "pick": ranked[0] if ranked else None,
           "ranked": ranked, "nonce": nonce, "spec": spec,
           "sole": (found or {}).get("sole") or ""}
    if not ranked:
        return out
    top = ranked[0]
    if top["conf"] < threshold:
        out["why"] = "unsure"
        return out
    if not spec["ordinal"] and len(ranked) > 1:
        second = ranked[1]
        if (second["conf"] >= threshold and top["conf"] - second["conf"] < TIE_GAP
                and second["name"] != top["name"] and second["role"] == top["role"]
                and top["inView"] == second["inView"]):
            out["why"] = "tie"
            return out
    if top.get("disabled"):
        out["why"] = "disabled"
        return out
    out["ok"] = True
    out["why"] = ""
    return out


def wait_target(run, tab, description, timeout=FIND_TIMEOUT_S, **how):
    """find_target, polled until it is ok or the time is up; the last look either way. An
    SPA paints its controls some time after "complete", so one look is not enough."""
    end = time.monotonic() + timeout
    while True:
        run.check()
        found = find_target(tab, description, **dict(how))
        if found["ok"] or time.monotonic() >= end:
            return found
        run.nap()


def label_of(cand):
    """How a candidate is named in a spoken line: its own name, or its kind."""
    if not cand:
        return ""
    return ascii_words(cand.get("name"), 60) or ("a %s" % (cand.get("role") or "control"))


def miss_line(found, description, verb="touch anything"):
    """The refusal for a find that is not ok, naming the nearest miss and its score -
    operator_type_code's "I could not find a readable editor" discipline, generalised."""
    what = describe_target(description)
    pick = found.get("pick")
    why = found.get("why")
    if why == "nothing" or not pick:
        return "I did not %s - I could not find %s on the page" % (verb, what)
    near = "'%s' (%s)" % (label_of(pick), pick.get("role"))
    if why == "tie":
        other = found["ranked"][1]
        return ("I did not %s - two different things match %s equally well, %s and '%s', "
                "and I will not guess" % (verb, what, near, label_of(other)))
    if why == "disabled":
        return "I did not %s - %s is there, %s, but it is disabled" % (verb, what, near)
    return ("I did not %s - nothing on the page is a confident match for %s; the nearest "
            "was %s at %d%%" % (verb, what, near, int(round(pick["conf"] * 100))))


# =============================================================================
#  THE EXECUTOR - real input first, the synthetic call last and named, everything read back
# =============================================================================

def _mouse(tab, kind, x, y, button="left", clicks=1, **extra):
    params = {"type": kind, "x": x, "y": y, "button": button if kind != "mouseMoved" else "none",
              "clickCount": clicks if kind != "mouseMoved" else 0}
    params.update(extra)
    tab.call("Input.dispatchMouseEvent", params)


def click_at(tab, x, y):
    """A real left click at viewport (x, y): moved, pressed, released. Trusted input, so
    the page gets a genuine user activation - which is what lets media start with sound."""
    _mouse(tab, "mouseMoved", x, y)
    _mouse(tab, "mousePressed", x, y)
    _mouse(tab, "mouseReleased", x, y)


_KEYS = {
    "Enter": {"code": "Enter", "windowsVirtualKeyCode": 13, "text": "\r"},
    "Escape": {"code": "Escape", "windowsVirtualKeyCode": 27},
    "Tab": {"code": "Tab", "windowsVirtualKeyCode": 9},
    " ": {"code": "Space", "windowsVirtualKeyCode": 32, "text": " "},
    "ArrowDown": {"code": "ArrowDown", "windowsVirtualKeyCode": 40},
    "ArrowUp": {"code": "ArrowUp", "windowsVirtualKeyCode": 38},
    "Home": {"code": "Home", "windowsVirtualKeyCode": 36},
}


def press_key(run, tab, key):
    """One named key, down and up, to whatever has focus. Never a modifier: nothing here can
    send Ctrl+Enter, so no editor's "submit" shortcut can fire by accident."""
    run.check()
    spec = _KEYS[key]
    for kind in ("keyDown", "keyUp"):
        params = {"type": kind, "key": key, "code": spec["code"],
                  "windowsVirtualKeyCode": spec["windowsVirtualKeyCode"],
                  "nativeVirtualKeyCode": spec["windowsVirtualKeyCode"]}
        if kind == "keyDown" and spec.get("text"):
            params["text"] = spec["text"]
        tab.call("Input.dispatchKeyEvent", params)


def type_keys(tab, text):
    """Each character as a real key press with text - the keyboard path."""
    for ch in text:
        if ch == "\n":
            tab.call("Input.dispatchKeyEvent", {"type": "keyDown", "key": "Enter",
                                                "code": "Enter", "text": "\r",
                                                "windowsVirtualKeyCode": 13})
            tab.call("Input.dispatchKeyEvent", {"type": "keyUp", "key": "Enter",
                                                "code": "Enter", "windowsVirtualKeyCode": 13})
            continue
        tab.call("Input.dispatchKeyEvent", {"type": "keyDown", "key": ch, "text": ch,
                                            "unmodifiedText": ch})
        tab.call("Input.dispatchKeyEvent", {"type": "keyUp", "key": ch})


def type_chars(tab, text):
    """Each character as the full sequence a real keyboard produces - rawKeyDown, char,
    keyUp. Measured on www.wikipedia.org's native <select>: type_keys() (keyDown carrying
    the text) moved its type-ahead by the FIRST letter only ("deutsch" chose "dansk"),
    while this sequence chose "deutsch" exactly."""
    for ch in text:
        tab.call("Input.dispatchKeyEvent", {"type": "rawKeyDown", "key": ch})
        tab.call("Input.dispatchKeyEvent", {"type": "char", "text": ch, "unmodifiedText": ch,
                                            "key": ch})
        tab.call("Input.dispatchKeyEvent", {"type": "keyUp", "key": ch})


class NewTabWatch:
    """Did an action open a NEW TAB? Asked of the browser itself (Operator 1.4, item 3).

    Measured in 1.3: a click on a target=_blank link left the page unchanged, so the line
    read "nothing on the page visibly changed" - true of the page and false about what
    happened. A browser-level socket with Target.setDiscoverTargets reports every target;
    the ones that existed when it was armed are set aside, and a page created after it -
    opened BY the locked tab, when Chrome says so - is the new tab. Best-effort: if the
    browser socket cannot be had, it reports nothing rather than failing the action.
    """

    def __init__(self, tab_ws):
        self.sock = None
        self.mine = ""
        self.known = set()
        parts = urllib.parse.urlsplit(tab_ws or "")
        self.mine = parts.path.rsplit("/", 1)[-1] if parts.path else ""
        port = parts.port
        try:
            found = get_json("http://127.0.0.1:%d/json/version" % port) if port else None
            if not isinstance(found, dict) or not found.get("webSocketDebuggerUrl"):
                return
            self.sock = CDP(found["webSocketDebuggerUrl"])
            res = self.sock.call("Target.getTargets", timeout=4.0)
            self.known = {t.get("targetId") for t in res.get("targetInfos") or []}
            self.sock.call("Target.setDiscoverTargets", {"discover": True}, timeout=4.0)
        except Failed:
            self.close()

    def opened(self, wait=1.0):
        """[{id, url, opener}] for page targets created since arming."""
        if self.sock is None:
            return []
        self.sock.drain(wait)
        out, seen = [], set()
        for _n, method, params in self.sock.events:
            info = params.get("targetInfo") or {}
            tid = info.get("targetId")
            if method not in ("Target.targetCreated", "Target.targetInfoChanged"):
                continue
            if info.get("type") != "page" or tid in self.known or tid in seen:
                continue
            if info.get("openerId") and self.mine and info.get("openerId") != self.mine:
                continue
            seen.add(tid)
            out.append({"id": tid, "url": str(info.get("url") or ""),
                        "opener": info.get("openerId") == self.mine})
        return out

    def close(self):
        if self.sock is not None:
            self.sock.close()
            self.sock = None


def _href(tab):
    return tab.evaluate("location.href", timeout=5.0) or ""


def _arm(tab, nonce):
    """Mark the event serial and start the page's witness. Returns the serial."""
    since = tab.page_events()
    lib_call(tab, "L.arm(%s)" % json.dumps(nonce))
    return since


def _settle_after_nav(run, tab, href_before):
    """A navigation STARTED: wait for a document that answers again, and say where it
    is. The old one stops answering for the length of the request (seconds, on a slow
    line); evaluating against it in that window only queues behind it."""
    end = time.monotonic() + LOAD_TIMEOUT_S
    while time.monotonic() < end:
        if run is not None:
            run.check()
        try:
            now = tab.evaluate("location.href", timeout=1.5)
        except Failed:
            now = None
        if now:
            return {"navigated": True, "href": now != href_before, "got": [], "muts": 0,
                    "changed": [], "received": True, "trusted": True, "title": False}
        tab.drain(0.3)
    raise Failed("I pressed it and the page started to load, but nothing answered for "
                 "%.0f seconds" % LOAD_TIMEOUT_S)


def _effects(tab, nonce, href_before, wait=EFFECT_WAIT_S, run=None, keep=False, since=None):
    """What happened after an action, looked for until something did or `wait` ran out.
    A navigation wipes the page's library with the old document, so a missing witness and
    a moved address together read as "it navigated" - the strongest effect there is. A
    document that does not answer at all is a navigation only if the browser SAID one
    started (`since` is the event serial _arm returned); otherwise it is a failure."""
    end = time.monotonic() + wait
    last = None
    while True:
        try:
            res = lib_call(tab, "L.effects(%s, true)" % json.dumps(nonce), timeout=3.0)
        except Failed:
            tab.drain(0.05)
            if since is not None and tab.saw_main(since, *NAV_STARTED):
                return _settle_after_nav(run, tab, href_before)
            if time.monotonic() >= end + LOAD_TIMEOUT_S:
                raise
            continue
        if res is None:
            now = _href(tab)
            last = {"navigated": True, "href": now != href_before, "got": [], "muts": 0,
                    "changed": [], "received": True, "trusted": True}
            if now != href_before or time.monotonic() >= end:
                return last
        else:
            got = res.get("got") or []
            res["received"] = any(g.get("into") for g in got)
            res["trusted"] = any(g.get("into") and g.get("trusted") for g in got)
            res["navigated"] = False
            last = res
            if res["href"] or res["changed"] or res["title"] or time.monotonic() >= end:
                break
            if res["muts"] >= 3 and time.monotonic() >= end - wait + 0.6:
                break
        if run is not None:
            run.nap(0.12)
        else:
            time.sleep(0.12)
    if not keep:
        lib_call(tab, "L.effects(%s, false)" % json.dumps(nonce))
    return last


def effect_words(fx):
    """The visible consequences of an action, as a short phrase for the line."""
    if not fx:
        return ""
    if fx.get("newTab"):
        # Said FIRST and in so many words: the locked page itself usually did not change,
        # and "nothing changed" would have been the old line (measured in 1.3).
        return "this opened a new tab, sir - I have not followed it"
    if fx.get("navigated"):
        return "the page moved on"
    bits = []
    ch = fx.get("changed") or []
    if "name" in ch and fx.get("nameNow"):
        bits.append("it now reads '%s'" % ascii_words(fx["nameNow"], 50))
    elif any(k in ch for k in ("pressed", "checked", "cb", "selected")):
        bits.append("its state changed")
    elif "expanded" in ch:
        bits.append("it opened")
    # An address that changed WITHOUT a document load is a single-page app's own routing
    # (pushState) - it may be the click's doing or the app's, so it is said as what it is,
    # after the element's own change. Measured on LeetCode: a menu button that "opened"
    # was once reported as "the page moved on" because the app rewrote its URL that second.
    if fx.get("href"):
        bits.append("the address changed")
    if fx.get("title"):
        bits.append("the page title changed")
    if not bits and fx.get("muts", 0) >= 3:
        bits.append("the page changed")
    return ", ".join(bits)


def act_click(run, tab, found):
    """Click the found thing. Returns {path, trusted, effects}. Raises Failed.

    THE PATHS, in order, and why that order:
      pointer   a real mouse press at a point of the element nothing covers. Trusted, with
                a user activation - what sites that sniff synthetic clicks look for.
      keyboard  the element focused and Enter pressed (Space for a checkbox). Also trusted:
                Chrome turns Enter on a focused button or link into a real click event.
                Taken when no point of the element is uncovered (a banner over it).
      dom       element.click(), with a user gesture. Synthetic (isTrusted false), and the
                line says so; taken only when both trusted paths could not be sent.

    THE NO-RETRY RULE. A path is followed by the next ONLY when the event never reached
    the element. If it reached it - trusted or not - the click happened, and a second one on
    a toggle undoes the first. If it reached something ELSE (a cover that appeared between
    the look and the press), that something may have acted, so the run stops and says
    what the click landed on.
    """
    nonce = found["nonce"]
    name = label_of(found["pick"])
    run.check()
    spot = lib_call(tab, "L.spot(%s, true)" % json.dumps(nonce))
    if not spot or spot.get("gone"):
        raise Failed("I did not click anything - '%s' disappeared from the page before I "
                     "could press it" % name)
    run.nap(0.12)                      # scrollIntoView settles before coordinates are used
    spot = lib_call(tab, "L.spot(%s, false)" % json.dumps(nonce)) or {}
    href = _href(tab)
    tried = []
    tabs = NewTabWatch(getattr(tab, "ws_url", ""))
    try:
        res = _click_paths(run, tab, found, nonce, name, spot, href, tried)
        fresh = tabs.opened(0.8 if not res["effects"].get("navigated") else 0.2)
        if fresh:
            res["effects"]["newTab"] = fresh[0]
            res["newTab"] = fresh[0]
        return res
    finally:
        tabs.close()


def _click_paths(run, tab, found, nonce, name, spot, href, tried):
    """act_click's three paths and its no-retry rule; see act_click."""
    for path in ("pointer", "keyboard", "dom"):
        if path == "pointer" and not spot.get("clear"):
            tried.append("pointer (covered by %s)" % (spot.get("cover") or "something"))
            continue
        run.check()                    # the last safe point before the page is touched
        since = _arm(tab, nonce)
        if path == "pointer":
            click_at(tab, spot["x"], spot["y"])
        elif path == "keyboard":
            if not lib_call(tab, "L.focus(%s)" % json.dumps(nonce)):
                tried.append("keyboard (could not focus it)")
                continue
            role = found["pick"].get("role")
            press_key(run, tab, " " if role == "checkbox" else "Enter")
        else:
            lib_call(tab, "L.domClick(%s)" % json.dumps(nonce), gesture=True)
        fx = _effects(tab, nonce, href, run=run, since=since)
        got = fx.get("got") or []
        clicks = [g for g in got if g.get("type") == "click"]
        # A CLICK IS A CLICK EVENT INTO THE TARGET, OR A NAVIGATION - nothing less. Measured
        # 2026-10-14: on a background tab a real press delivered only a mouseover to a
        # checkbox, and an earlier witness that counted "any event into it" called that a
        # click that had landed.
        if fx.get("navigated") or any(g.get("into") for g in clicks):
            trusted = fx.get("navigated") or any(g.get("into") and g.get("trusted")
                                                 for g in clicks)
            return {"path": path, "trusted": bool(trusted), "effects": fx, "tried": tried}
        stray = [g for g in clicks if not g.get("into")]
        if stray:
            raise Failed("I stopped - my click on '%s' landed on '%s' instead, so I did not "
                         "try again" % (name, ascii_words(stray[0].get("on"), 50) or
                                        "something else"))
        if any(g.get("into") and g.get("type") in ("mousedown", "pointerdown") for g in got):
            # HALF A CLICK: the press reached it and no click followed. A page that acts on
            # mousedown has acted already, so this is the no-retry case, not "nothing".
            raise Failed("I stopped - '%s' took my press but no click followed, so I did not "
                         "try again in case it had already acted" % name)
        tried.append("%s (nothing arrived)" % path)
    raise Failed("I could not click '%s' - %s" % (name, "; ".join(tried)))


def act_type(run, tab, found, text, replace=True):
    """Type `text` into the found field. Returns {path, value, replaced}. Raises Failed.

    Focus first, by a real click on the field when it does not already have the keyboard
    (a click is safe on a text field; it is how a person starts typing). Then, when
    `replace`, the field's own contents are SELECTED so the text replaces them - a search
    box that kept the last query is the usual case, and the card says "replacing".

    THE PATHS, measured in 1.1 and 1.2 and kept in their order for plain fields:
      insertText   Input.insertText: one trusted input event carrying the whole string,
                   which React and plain inputs both accept, with no keyboard layout.
      keys         one real key press per character.
      setter       the element's native value setter, then input and change events.
                   Synthetic; it exists for framework fields that ignore the first two.
    A path is followed by the next only when the field is UNCHANGED. A field that changed
    to something other than what was sent (an autocomplete, a mask, a length cap) is
    reported as it reads and never typed into again.
    """
    nonce = found["nonce"]
    name = label_of(found["pick"])
    state = lib_call(tab, "L.fieldValue(%s)" % json.dumps(nonce))
    if state is None:
        raise Failed("I did not type anything - the field disappeared from the page")
    if state.get("password"):
        raise Failed("I did not type anything - '%s' is a password field, and I do not type "
                     "into those" % name)
    if not state.get("focused"):
        run.at("putting the cursor in '%s'" % name)
        spot = lib_call(tab, "L.spot(%s, true)" % json.dumps(nonce)) or {}
        run.nap(0.1)
        spot = lib_call(tab, "L.spot(%s, false)" % json.dumps(nonce)) or spot
        if spot.get("clear"):
            click_at(tab, spot["x"], spot["y"])
            run.nap(0.15)
        state = lib_call(tab, "L.fieldValue(%s)" % json.dumps(nonce)) or {}
        if not state.get("focused"):
            took = lib_call(tab, "L.adoptActive(%s)" % json.dumps(nonce))
            if took:
                note("operator", "the click handed the cursor to another field, %r; typing "
                     "there" % took.get("name"))
                state = lib_call(tab, "L.fieldValue(%s)" % json.dumps(nonce)) or {}
        if not state.get("focused"):
            lib_call(tab, "L.focus(%s)" % json.dumps(nonce), gesture=True)
            run.nap(0.1)
            state = lib_call(tab, "L.fieldValue(%s)" % json.dumps(nonce)) or {}
        if not state.get("focused"):
            raise Failed("I did not type anything - '%s' would not take the cursor" % name)
    before = str(state.get("value") or "")
    replaced = bool(replace and before)
    if replaced:
        lib_call(tab, "L.selectAll(%s)" % json.dumps(nonce))
    want = text if replace else before + text
    run.at("typing into '%s'" % name)
    for path in ("insertText", "keys", "setter"):
        run.check()
        if path == "insertText":
            tab.call("Input.insertText", {"text": text})
        elif path == "keys":
            type_keys(tab, text)
        else:
            lib_call(tab, "L.setValue(%s, %s)" % (json.dumps(nonce), json.dumps(want)),
                     gesture=True)
        got, end = None, time.monotonic() + 1.0
        while True:
            got = str((lib_call(tab, "L.fieldValue(%s)" % json.dumps(nonce)) or {})
                      .get("value") or "")
            if got.strip() == want.strip() or time.monotonic() >= end:
                break
            run.nap(0.08)
        if got.strip() == want.strip():
            return {"path": path, "value": got, "replaced": replaced}
        if got not in (before, "") and not (replaced and got == ""):
            raise Failed("I stopped - '%s' now reads '%s', not what I typed, so I did not "
                         "type into it again" % (name, ascii_words(got, 60)))
        if replaced:
            lib_call(tab, "L.selectAll(%s)" % json.dumps(nonce))
    raise Failed("I did not type anything - '%s' would not take text by any of the three "
                 "ways I know" % name)


def act_submit(run, tab, found, button_words=("search", "submit", "go")):
    """Send what was typed: Enter in the field, read back as a moved address, a changed
    title or a page that changed. If Enter did nothing, the field's own submit control is
    found GENERICALLY (a button named search / submit / go, or the form's submit button)
    and clicked. Returns {path, effects}."""
    nonce = found["nonce"]
    href = _href(tab)
    run.check()
    since = _arm(tab, nonce)
    press_key(run, tab, "Enter")
    fx = _effects(tab, nonce, href, wait=3.0, run=run, since=since)
    if fx.get("navigated") or fx.get("href") or fx.get("title") or fx.get("muts", 0) >= 5:
        return {"path": "enter", "effects": fx}
    for word in button_words:
        btn = find_target(tab, "the %s button" % word, role="button")
        if btn["ok"]:
            res = act_click(run, tab, btn)
            return {"path": "button '%s'" % label_of(btn["pick"]), "effects": res["effects"]}
    return {"path": "enter", "effects": fx}


def act_select(run, tab, found, option):
    """Choose `option` in the found dropdown. Returns {path, chosen}. Raises Failed.

    A NATIVE <select>: the option is matched by its visible text (exact, then a confident
    word match), then chosen by the KEYBOARD first - the select focused and the option's
    name TYPED, which is the closed select's own type-ahead and fires a trusted change -
    and by setting selectedIndex with input and change events if that did not land.
    Measured on www.wikipedia.org's 300-option language list: Home and ArrowDown x N
    landed on the wrong option (a list with hidden and grouped entries does not step one
    index per press), and type-ahead landed exactly. Read back: the select's own index.

    THE NO-RETRY RULE DOES NOT APPLY HERE, AND WHY: choosing an option is idempotent - a
    second, correct choice leaves the select exactly as if the first had been right - so a
    keyboard landing on the wrong option is CORRECTED by the setter and the line says so.
    A toggle is the case the rule exists for, and a dropdown is not one.

    A CUSTOM dropdown (an ARIA combobox or a button that opens a listbox): the trigger is
    clicked for real, the option is found among what appeared by the same finder, clicked
    for real, and read back as the trigger now showing the option's name or the option
    marked selected.
    """
    nonce = found["nonce"]
    name = label_of(found["pick"])
    want = " ".join(str(option or "").split()).lower()
    opts = lib_call(tab, "L.options(%s)" % json.dumps(nonce))
    if opts:
        words = re.findall(r"\w+", want)
        best, best_s = None, 0.0
        for op in opts["options"]:
            if op.get("disabled"):
                continue
            t = op["text"]
            if t == want:
                s = 1.0
            else:
                tw = re.findall(r"\w+", t)
                if not tw or not words:
                    continue
                cov = sum(1 for w in words if any(x == w or (len(w) >= 4 and x.startswith(w))
                                                  for x in tw)) / len(words)
                prec = sum(1 for x in tw if any(x == w or (len(w) >= 4 and x.startswith(w))
                                                for w in words)) / len(tw)
                s = cov * (0.75 + 0.25 * prec)
            if s > best_s:
                best, best_s = op, s
        if not best or best_s < THRESHOLD:
            raise Failed("I did not choose anything - '%s' has no option that is a confident "
                         "match for '%s'" % (name, ascii_words(option, 40)))
        if opts["index"] == best["i"]:
            return {"path": "already", "chosen": best["text"]}
        run.at("choosing '%s' in '%s'" % (ascii_words(best["text"], 40), name))
        lib_call(tab, "L.focus(%s)" % json.dumps(nonce))
        # Chrome's type-ahead keeps what was typed for about a second; a word typed inside
        # that window is APPENDED to the last one and matches nothing.
        run.nap(1.1)
        type_chars(tab, best["label"])
        run.nap(0.15)
        now = lib_call(tab, "L.options(%s)" % json.dumps(nonce)) or {}
        if now.get("index") == best["i"]:
            return {"path": "keyboard", "chosen": best["text"]}
        wrong = now.get("index") not in (opts["index"], None)
        lib_call(tab, "L.setIndex(%s, %d)" % (json.dumps(nonce), best["i"]), gesture=True)
        now = lib_call(tab, "L.options(%s)" % json.dumps(nonce)) or {}
        if now.get("index") == best["i"]:
            return {"path": "setter" + (" (corrected the keyboard's landing)" if wrong else ""),
                    "chosen": best["text"]}
        raise Failed("I could not choose '%s' in '%s'" % (ascii_words(option, 40), name))
    # A custom one: open it, then pick the option from what appeared.
    run.at("opening '%s'" % name)
    act_click(run, tab, found)
    end = time.monotonic() + 4.0
    while True:
        opt = find_target(tab, option, role="option")
        if opt["ok"] or time.monotonic() >= end:
            break
        run.nap()
    if not opt["ok"]:
        press_key(run, tab, "Escape")
        raise Failed(miss_line(opt, "the '%s' option" % ascii_words(option, 40),
                               verb="choose anything") + " - I closed the list again")
    chosen = label_of(opt["pick"])
    run.at("choosing '%s'" % chosen)
    res = act_click(run, tab, opt)
    # READ BACK: the trigger now SHOWS the choice, which is what a person checks. Looked
    # for a few times, because a menu closes and its button re-renders a beat later.
    want = norm_name(opt["pick"].get("name"))
    shows = ""
    end = time.monotonic() + 3.0
    while True:
        shows = norm_name(lib_call(tab, "(function(){var e=L.picked[%s];return e&&e.isConnected?"
                                   "(e.tagName==='SELECT'?e.options[e.selectedIndex].text:"
                                   "(e.innerText||e.textContent)):''})()" % json.dumps(nonce)))
        if (want and want in shows) or time.monotonic() >= end:
            break
        run.nap(0.25)
    return {"path": "custom/" + res["path"], "chosen": chosen,
            "shows": shows, "verified": bool(want and want in shows)}


def act_scroll(run, tab, found):
    """Bring the found thing UP, to the upper part of the view - what "scroll to the
    history section" means to a person: real mouse-wheel turns over the page first (what
    lazy-loading pages listen for), then scrollIntoView if the wheel could not get it
    there. Read back: the element's top inside the upper band of the viewport.

    MEASURED 1.4: the old rule stopped as soon as the element was anywhere in the
    viewport. Wikipedia's History heading sat at y=614 of a 987-px viewport, nothing
    moved, and the line said "Scrolled 'history' into view" - while on this screen that
    part of a too-tall window was below the display. So the goal is the band, and a run
    that had nothing to do says so ("already near the top")."""
    nonce = found["nonce"]
    name = label_of(found["pick"])
    moved = False
    for _ in range(25):
        run.check()
        r = lib_call(tab, "L.rect(%s)" % json.dumps(nonce))
        if not r:
            raise Failed("I stopped - '%s' disappeared from the page while I scrolled" % name)
        band = (r["top"] >= -1 and r["top"] <= SCROLL_BAND * r["h"])
        if band:
            return {"path": "wheel" if moved else "already"}
        delta = max(-600, min(600, r["top"] - SCROLL_AIM * r["h"]))
        if abs(delta) < 4:
            break
        _mouse(tab, "mouseWheel", int(r["w"] / 2), int(r["h"] / 2), deltaX=0, deltaY=delta)
        run.nap(0.12)
        r2 = lib_call(tab, "L.rect(%s)" % json.dumps(nonce)) or r
        if abs(r2["top"] - r["top"]) < 2:
            break                      # the wheel moved nothing: an inner scroller, or the end
        moved = True
    r = lib_call(tab, "L.rect(%s)" % json.dumps(nonce)) or {}
    if r and r["top"] >= -1 and r["top"] <= SCROLL_BAND * r["h"]:
        return {"path": "wheel"}
    lib_call(tab, "(function(){var e=L.picked[%s];if(e)e.scrollIntoView({block:'start',"
                  "behavior:'instant'});return !!e})()" % json.dumps(nonce))
    run.nap(0.1)
    r = lib_call(tab, "L.rect(%s)" % json.dumps(nonce)) or {}
    if r.get("inView") or r.get("partly"):
        # The page may simply end before the element can reach the band: in view is
        # still in view, and the line does not claim more.
        return {"path": "scrollIntoView"}
    raise Failed("I could not bring '%s' into view" % name)


def act_hover(run, tab, found):
    """Rest the real pointer on the found thing and read back :hover. If the pointer could
    not be placed (covered), synthetic mouseover/mouseenter are sent and NAMED, because a
    CSS :hover menu will not open for them."""
    nonce = found["nonce"]
    name = label_of(found["pick"])
    spot = lib_call(tab, "L.spot(%s, true)" % json.dumps(nonce)) or {}
    run.nap(0.12)
    spot = lib_call(tab, "L.spot(%s, false)" % json.dumps(nonce)) or spot
    href = _href(tab)
    since = _arm(tab, nonce)
    if spot.get("clear"):
        _mouse(tab, "mouseMoved", spot["x"], spot["y"])
        fx = _effects(tab, nonce, href, wait=0.8, run=run, since=since)
        if fx.get("hover"):
            return {"path": "pointer", "effects": fx}
    lib_call(tab, "L.mouseOver(%s)" % json.dumps(nonce))
    fx = _effects(tab, nonce, href, wait=0.8, run=run, since=since)
    if fx.get("received"):
        return {"path": "synthetic", "effects": fx}
    raise Failed("I could not rest the pointer on '%s'" % name)


# =============================================================================
#  THE READER - the readable text of a page, for grounding an answer in it
# =============================================================================
#
# Headings, the main body and the labels of the form, in reading order, from VISIBLE text
# only (a hidden tab panel is not on the page as far as a person is concerned). Left out:
# page chrome (header, nav, footer, aside), scripts and styles, and CODE EDITORS - Monaco,
# CodeMirror 5 and 6 and anything marked role=code - because an editor's contents are the
# employer's draft, not the problem, and feeding the draft back as "the problem" is how a
# wrong signature becomes a confident one. Engines are named, not sites: the same three
# 1.2 already reads through.
#
# If the page has a single main landmark (main, [role=main], or one article) holding most
# of its text, only that is read. Block boundaries become newlines; nothing is summarised.
_READ_JS = r"""
(function (cap, edCap) {
  var JUNK = 'script, style, noscript, template, svg, header, nav, footer, aside, ' +
             '[role=banner], [role=navigation], [role=contentinfo], [role=complementary], ' +
             '.monaco-editor, .CodeMirror, .cm-editor, [role=code], textarea, [aria-hidden=true], ' +
             '[data-op-ignore]';
  var BLOCK = /^(P|DIV|LI|UL|OL|PRE|H[1-6]|TR|TD|TH|SECTION|ARTICLE|BLOCKQUOTE|DD|DT|LABEL|FIGCAPTION|BR|TABLE|DETAILS|SUMMARY)$/;
  var visCache = new Map();
  var shown = function (el) {
    if (visCache.has(el)) return visCache.get(el);
    var v = !el.checkVisibility || el.checkVisibility({visibilityProperty: true});
    visCache.set(el, v);
    return v;
  };
  var textOf = function (root) {
    var out = [], last = null, n = 0;
    var w = document.createTreeWalker(root, NodeFilter.SHOW_TEXT | NodeFilter.SHOW_ELEMENT, {
      acceptNode: function (node) {
        if (node.nodeType === 1) {
          if (node.matches(JUNK)) return NodeFilter.FILTER_REJECT;
          if (!shown(node)) return NodeFilter.FILTER_REJECT;
          return NodeFilter.FILTER_SKIP;
        }
        return /\S/.test(node.data) ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_SKIP;
      }});
    var node;
    while ((node = w.nextNode())) {
      var blk = node.parentElement;
      while (blk && blk !== root && !BLOCK.test(blk.tagName)) blk = blk.parentElement;
      var piece = node.data.replace(/\s+/g, ' ');
      // 10<sup>9</sup> is 10^9, not "10 9": measured on a constraints list, where the
      // difference is a wrong bound.
      if (node.parentElement && node.parentElement.closest('sup')) piece = '^' + piece.trim();
      else if (node.parentElement && node.parentElement.closest('sub')) piece = '_' + piece.trim();
      if (blk !== last && out.length) out.push('\n');
      else if (/^[\^_]/.test(piece)) { /* glued to what it raises */ }
      else if (out.length && !/\s$/.test(out[out.length - 1]) && !/^\s/.test(piece)) out.push(' ');
      out.push(piece);
      last = blk;
      n += piece.length;
      if (n > cap * 1.5) break;
    }
    return out.join('').replace(/[ \t]+\n/g, '\n').replace(/\n[ \t]+/g, '\n').replace(/\n{3,}/g, '\n\n').trim();
  };
  var body = document.body;
  if (!body) return null;
  var all = textOf(body);
  var mains = Array.prototype.slice.call(document.querySelectorAll('main, [role=main]'));
  if (!mains.length) {
    var arts = document.querySelectorAll('article');
    if (arts.length === 1) mains = [arts[0]];
  }
  var main = '';
  if (mains.length === 1) {
    var t = textOf(mains[0]);
    if (t.length >= 0.4 * all.length && t.length >= 200) main = t;
  }
  var text = main || all;
  var heads = Array.prototype.slice.call(document.querySelectorAll('h1, h2, h3'))
    .filter(function (h) { return !h.closest(JUNK) && shown(h); })
    .map(function (h) { return h.innerText.replace(/\s+/g, ' ').trim(); })
    .filter(Boolean).slice(0, 20);
  var labels = Array.prototype.slice.call(document.querySelectorAll('label'))
    .filter(function (l) { return shown(l) && !l.closest(JUNK); })
    .map(function (l) { return l.innerText.replace(/\s+/g, ' ').trim(); })
    .filter(Boolean).slice(0, 30);
  // THE EDITOR, READ SEPARATELY AND LABELLED. Left out of the page text above because it
  // is not the problem; returned here because what is in it usually IS the contract - a
  // platform's starter code carries the exact function name, parameters and language the
  // grader calls. 1.2's wrong signature for Merge Sorted Array was this field missing.
  // Read through the engine's own API, the same three 1.2 types through; the focused
  // editor first, else the largest.
  var ed = null;
  try {
    var eds = [];
    if (window.monaco && monaco.editor && monaco.editor.getEditors) monaco.editor.getEditors().forEach(function (e) {
      var m = e.getModel(), d = e.getDomNode();
      if (m && d) eds.push({kind: 'monaco', focused: e.hasTextFocus(), dom: d, value: m.getValue(1),
                            lang: m.getLanguageId ? m.getLanguageId() : ''});
    });
    document.querySelectorAll('.CodeMirror').forEach(function (d) {
      var c = d.CodeMirror; if (!c) return;
      var md = c.getOption('mode');
      eds.push({kind: 'codemirror5', focused: c.hasFocus(), dom: d, value: c.getValue('\n'),
                lang: String(md && md.name || md || '')});
    });
    document.querySelectorAll('.cm-editor .cm-content').forEach(function (d) {
      var v = d.cmView && d.cmView.view; if (!v) return;
      eds.push({kind: 'codemirror6', focused: v.hasFocus, dom: v.dom, value: v.state.doc.toString(), lang: ''});
    });
    eds = eds.filter(function (x) { var r = x.dom.getBoundingClientRect(); x.area = r.width * r.height; return x.area > 400; });
    var pick = eds.filter(function (x) { return x.focused; })[0] ||
               eds.sort(function (a, b) { return b.area - a.area; })[0];
    if (pick) ed = {kind: pick.kind, lang: pick.lang, count: eds.length,
                    text: pick.value.slice(0, edCap), cut: pick.value.length > edCap};
  } catch (e) { ed = null; }
  return {title: document.title, url: location.href, headings: heads, labels: labels,
          scope: main ? 'main' : 'page', chars: text.length, cut: text.length > cap,
          text: text.slice(0, cap), editor: ed};
})(%d, %d)
"""

READ_CAP = 6000
EDITOR_CAP = 3000


def read_page(tab, cap=READ_CAP, timeout=6.0, editor_cap=EDITOR_CAP):
    """{title, url, headings, labels, scope, chars, cut, text, editor} for the page, or
    None. A pure read: nothing is clicked, focused, scrolled or marked. `editor_cap` is
    how much of the code editor comes back - the typing card compares it EXACTLY, so it
    asks for all of it."""
    found = tab.evaluate(_READ_JS % (int(cap), int(editor_cap)), timeout=timeout)
    return found if isinstance(found, dict) else None


def read_ws(ws_url, cap=READ_CAP, timeout=6.0, editor_cap=EDITOR_CAP):
    """read_page on a tab named by its socket - the server's way in, from the focus
    session's own lock. None on any failure: grounding is furniture, and losing it must
    not lose the answer."""
    try:
        tab = CDP(ws_url)
    except Failed:
        return None
    try:
        return read_page(tab, cap=cap, timeout=timeout, editor_cap=editor_cap)
    except Failed:
        return None
    finally:
        tab.close()


# =============================================================================
#  VIDEO - is the page's biggest <video> SEEN to play
# =============================================================================

_VIDEO_JS = r"""
(function (adSel) {
  var vs = Array.prototype.slice.call(document.querySelectorAll('video'));
  var best = null, area = 0;
  vs.forEach(function (v) { var r = v.getBoundingClientRect();
    if (r.width * r.height > area) { area = r.width * r.height; best = v; } });
  if (!best) return null;
  return {t: best.currentTime, paused: best.paused, ready: best.readyState,
          ended: best.ended, muted: best.muted || best.volume === 0,
          d: isFinite(best.duration) ? best.duration : -1,
          ad: !!(adSel && document.querySelector(adSel))};
})(%s)
"""


def wait_playing(run, tab, timeout=15.0, need_sound=False, short_is_ad=False, ad_marker=""):
    """(playing, ad, muted) once the page's biggest <video> is SEEN to play: not paused,
    and its clock has moved between two looks. If it sits paused it is asked to play()
    once, as a user gesture, and watched again. need_sound: a MUTED video (a hover preview,
    a trailer) does not count. short_is_ad: a clip of 30 s or less counts as a probable
    advert. ad_marker: a site layer's selector that means "an advert is showing"."""
    end = time.monotonic() + timeout
    nudged, last, saw_muted = False, None, False
    started = time.monotonic()
    while time.monotonic() < end:
        now = tab.evaluate(_VIDEO_JS % json.dumps(ad_marker or ""), timeout=5.0)
        if now and last and not now["paused"] and now["t"] > last["t"] + 0.05:
            if not (need_sound and now.get("muted")):
                ad = bool(now.get("ad")) or (short_is_ad and 0 < now.get("d", -1) <= 30)
                return True, ad, bool(now.get("muted"))
            saw_muted = True
        if (now and now["paused"] and not nudged and not (need_sound and now.get("muted"))
                and time.monotonic() - started > 4.0):
            nudged = True
            run.check()
            tab.evaluate("(function(){var v=Array.prototype.slice.call("
                         "document.querySelectorAll('video')).sort(function(a,b){"
                         "var r=a.getBoundingClientRect(),s=b.getBoundingClientRect();"
                         "return s.width*s.height-r.width*r.height;})[0];"
                         "return v?v.play().then(function(){return 1},function(){return 0}):0;})()",
                         gesture=True, await_promise=True, timeout=5.0)
        last = now
        run.nap(0.5)
    return False, False, saw_muted
