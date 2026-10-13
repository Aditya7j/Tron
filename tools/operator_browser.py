#!/usr/bin/env python3
"""operator_browser.py - Operator, phase 1.1: open a site, and for YouTube or Hotstar,
search it, click the first result and start it playing.

    echo {"site": "youtube", "query": "kesariya arijit singh"} | python tools/operator_browser.py
    Opened YouTube and started playing kesariya arijit singh - the first result, 'Kesariya - Brahmastra'.

THE CONTRACT, as tools/selftest.py states it:

  in    {"site": "youtube" | "hotstar" | <anything else>, "query": "..."} on stdin, UTF-8.
        query is optional, and is ignored for any site that is not YouTube or Hotstar.
  out   ONE line of plain ASCII on stdout, and stdout is the ONLY evidence. The assistant
        speaks it.
  exit  0 means the thing the line names happened and was SEEN to happen. 1 means it did
        not, and the line says why: no debugging port, a page that did not load in time, a
        result that could not be found, a video that would not start, or Ctrl+H.

WHAT EACH SITE GETS, and what each success line is allowed to claim:

  YOUTUBE   the results page for the query, the first ordinary video result clicked
            (adverts, Shorts and channel cards are passed over), and then the <video>
            element is WATCHED until its clock moves. "Started playing" is said only after
            currentTime has advanced while not paused - a watch page that loaded and sat
            still is a failure, not a success with an asterisk.
  HOTSTAR   BEST-EFFORT, AND SAYS SO. hotstar.com and jiohotstar.com both land on
            https://www.hotstar.com/in from this machine (measured 2026-10-14: hotstar.com
            -> /in in one redirect, jiohotstar.com -> /in in two), so that is where this
            goes. The site's own Search is used, the first result whose text matches the
            query is clicked, a Watch button is pressed if the title page has one, and the
            <video> is watched exactly as YouTube's is. Hotstar is a React SPA that changes
            shape without notice and puts most of what it carries behind a login and a
            subscription; when it stops short the line names where it stopped. Expect this
            path to need iteration after real use - that is the nature of the site, not a
            defect being hidden.
  ANYTHING  treated as a bare domain or a full http(s) URL and OPENED, nothing more. The
  ELSE      success line says "I only opened it" in so many words, because "opened" heard
            as "did the task" is exactly the kind of quiet overclaim a hand must not make.
            A bare word with no dot gets ".com" and the line names the host it reached.

THE PANIC KEY. While this hand is driving - and only then - Ctrl+H is registered
system-wide (RegisterHotKey, on a thread of its own). Pressing it sets a flag that is
checked before every navigate, click and keystroke and on every tick of every wait, so the
run stops at the next safe point rather than in the middle of a network call, prints
"Stopped - you took back control after <the step in progress>." and exits 1. The key is
UNREGISTERED in a finally on the way out, whatever the outcome, so Chrome's own Ctrl+H
(History) is suppressed while a run is in flight and comes back the instant the hand exits.
If the key cannot be registered on Windows (another program holds Ctrl+H) the hand REFUSES
to start: the proposal promised the key, and a promise of a brake that is not there is the
silent downgrade this house does not do. Off Windows it degrades loudly - see PanicKey.

THE PRIMITIVES ARE GENERAL ON PURPOSE. find_and_click(), focus_input(), type_text() and
press_key() know nothing about YouTube or Hotstar: they find a thing by its VISIBLE TEXT (or
a selector when structure is all there is, like "the first result"), click it with a real
Input.dispatchMouseEvent - a trusted gesture, which is what lets a video start with sound -
and type into whatever has focus with Input.insertText, the house's own precedent
(chain_proof.mjs, console_proof.mjs, census_proof.mjs). A later phase will reuse them on
other pages; nothing here should be taught a site's quirks below the site functions.

THE BROWSER THIS DRIVES is the DevTools Chrome launch-chrome.ps1 starts, found on the same
ports focus.py and relaunch_chrome.py look at, in their order. It works in a NEW TAB, never
the tab you were in: the Galaxy viewer lives in this same browser, and a hand that navigated
it away would be a hand that closed the assistant to play a song.

Standard library only, single file, like every hand. The WebSocket client is focus.py's
_ws_frame/_ws_read, copied rather than imported because a hand is one file; it is extended
here with a persistent connection and a request/response call(), which is the one thing
focus.py's one-question-per-socket _ws_eval_int never needed.
"""
import base64
import json
import os
import socket
import struct
import sys
import threading
import time
import unicodedata
import urllib.parse
import urllib.request

PORTS = (9222, 9223, 9224)        # focus.py's CDP_PORTS, in its order
HTTP_TIMEOUT_S = 1.5
CALL_TIMEOUT_S = 10.0             # one CDP request; Page.navigate is the slow one
POLL_S = 0.25                     # every wait ticks this often, and checks Ctrl+H each tick
LOAD_TIMEOUT_S = 25.0             # a real page on a real connection, not a fixture
FIND_TIMEOUT_S = 15.0             # an SPA paints its results some time after "complete"
PLAY_TIMEOUT_S = 15.0             # first frame, an ad's first frame, or a nudge and a retry
# The whole run's own budget. The registry kills this hand at timeout_s (60); finishing
# inside 52 means a slow site is reported in this file's words, as the step it was on,
# rather than as a bare timeout that hands.py can only call a crash.
BUDGET_S = 52.0

YOUTUBE_HOME = "https://www.youtube.com/"
YOUTUBE_RESULTS = "https://www.youtube.com/results?search_query=%s"
# Measured from this machine on 2026-10-14: both domains end here (see the docstring).
HOTSTAR_HOME = "https://www.hotstar.com/in"

SITE_ALIASES = {
    "youtube": ("youtube", "youtube.com", "www.youtube.com", "m.youtube.com", "yt",
                "you tube"),
    "hotstar": ("hotstar", "hotstar.com", "www.hotstar.com", "jiohotstar",
                "jiohotstar.com", "www.jiohotstar.com", "jio hotstar", "hot star",
                "disney+ hotstar",
                "disney hotstar", "disney plus hotstar"),
}

# The same sentence family focus.py uses for this exact condition ("I cannot lock a tab,
# sir - Chrome has no debugging port open."), so the house names it one way.
NO_PORT = ("I cannot do that, sir - Chrome has no debugging port open. Ask me to "
           "relaunch Chrome with the debugging port first.")


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
    letters = sum(ch.isalnum() for ch in kept)
    total = sum(not ch.isspace() for ch in " ".join(str(text or "").split()))
    if not letters or (total and letters < total * 0.5):
        return ""
    if len(kept) > limit:
        kept = kept[:limit].rsplit(" ", 1)[0] + "..."
    return kept


def say(line):
    sys.stdout.buffer.write(str(line).encode("ascii", "replace") + b"\n")
    sys.stdout.buffer.flush()


class Failed(Exception):
    """A reason, in words that can be spoken. Raised anywhere; printed once, in main."""


class Aborted(Exception):
    """Ctrl+H. Carries the step that was in progress."""


# =============================================================================
#  THE PANIC KEY - Ctrl+H, armed for the length of one run and not a moment longer
# =============================================================================

MOD_CONTROL = 0x0002
MOD_NOREPEAT = 0x4000
VK_H = 0x48
WM_HOTKEY = 0x0312
WM_QUIT = 0x0012
HOTKEY_ID = 0x0B1A                 # any id; it is private to the thread that registers it


class PanicKey:
    """Ctrl+H as a system-wide hotkey, on a background thread with its own message loop.

    RegisterHotKey binds the key to the CALLING THREAD's message queue, and only that
    thread may unregister it - so one thread registers, pumps GetMessage, and unregisters
    in its own finally. disarm() asks it to leave by posting WM_QUIT to it, which is the
    only message that makes GetMessage return 0. No window is created: with hWnd NULL the
    WM_HOTKEY arrives on the thread queue, which is all this needs.

    While registered, the keystroke is CONSUMED by Windows for us - so Chrome's own Ctrl+H
    (History) does nothing during a run. That is intended: the key belongs to the person
    taking control back. It returns to Chrome the moment UnregisterHotKey runs.

    OFF WINDOWS THERE IS NO PANIC KEY, AND THIS SAYS SO RATHER THAN CRASHING. The house
    runs on Windows in production (say.py and _proc.py exist because of CREATE_NO_WINDOW),
    but it is developed elsewhere too, and a developer's Mac must be able to run the hand.
    `armed` stays False and `why` names the reason; main() prints it to stderr, where a
    developer will see it and the room will not hear it.
    """

    def __init__(self):
        self.fired = threading.Event()
        self.armed = False
        self.why = ""
        self._tid = None
        self._thread = None
        self._ready = threading.Event()

    def arm(self):
        if sys.platform != "win32":
            # LOUD, ON PURPOSE: no ctypes.windll off Windows, so no RegisterHotKey, so no
            # Ctrl+H. The run proceeds without a brake on a dev machine only.
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


# =============================================================================
#  THE RUN - the step in progress, the brake, and the clock
# =============================================================================

class Run:
    """What every primitive consults before it acts: has Ctrl+H been pressed, and is
    there time left. `step` is a gerund phrase ("searching YouTube for x") so the abort
    line can say what was in progress in plain English."""

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
        """A wait that is also a brake check, so Ctrl+H never waits for a poll to end."""
        end = time.monotonic() + seconds
        while True:
            self.check()
            left = end - time.monotonic()
            if left <= 0:
                return
            time.sleep(min(0.05, left))


# =============================================================================
#  CDP - focus.py's WebSocket client, kept open and taught to ask more than one thing
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
    """(opcode, payload) or None, consuming one frame from buf (focus.py:_ws_read). The
    size cap is 8 MB rather than focus.py's 1 MB: a Runtime.evaluate here returns objects,
    not a single integer, though nothing it asks for comes close."""
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
    """One open DevTools WebSocket and a call() that waits for ITS answer.

    Events arrive on the same socket interleaved with answers; nothing here enables a
    domain, so there are few, and they are skipped by id exactly as _ws_eval_int skips
    them. Any transport failure is Failed with a reason - every caller is mid-step and
    the step name is what the line will carry.
    """

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

    def evaluate(self, expression, gesture=False, await_promise=False,
                 timeout=CALL_TIMEOUT_S):
        """The value of one expression in the page. `gesture` makes Chrome treat it as
        user-initiated - the documented way to let play() start a video with sound."""
        res = self.call("Runtime.evaluate",
                        {"expression": expression, "returnByValue": True,
                         "userGesture": bool(gesture), "awaitPromise": bool(await_promise)},
                        timeout=timeout)
        if res.get("exceptionDetails"):
            return None
        return (res.get("result") or {}).get("value")

    def close(self):
        try:
            self.sock.close()
        except Exception:                                      # noqa: BLE001
            pass


def get_json(url, method="GET", timeout=HTTP_TIMEOUT_S):
    """The answer, or None (relaunch_chrome.get_json, plus PUT for /json/new, which
    Chrome has refused as a GET since version 111)."""
    try:
        req = urllib.request.Request(url, method=method)
        with urllib.request.urlopen(req, timeout=timeout) as res:
            return json.loads(res.read().decode("utf-8", "replace"))
    except Exception:                                          # noqa: BLE001
        return None


def live_port():
    """(port, browser websocket url) for the first port that answers, or (None, None).
    relaunch_chrome.live_port, asking for the browser's own socket as well."""
    for port in PORTS:
        found = get_json("http://127.0.0.1:%d/json/version" % port)
        if isinstance(found, dict):
            return port, found.get("webSocketDebuggerUrl")
    return None, None


def open_tab(run, port, browser_ws):
    """A fresh tab, brought to the front with its window un-minimized, as a CDP session.

    A new tab, never an existing one: the viewer lives in this browser. Brought forward
    because the employer asked to WATCH something; and un-minimized through the browser's
    own Browser.setWindowBounds, because Page.bringToFront does nothing for a minimized
    window (measured; see the voice_proof keepFront note).
    """
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
#  THE GENERAL PRIMITIVES - nothing below this line knows what site it is on
# =============================================================================

def navigate(run, tab, url, what):
    """Go to url and wait for document.readyState === 'complete' on THAT document."""
    run.at(what)
    res = tab.call("Page.navigate", {"url": url}, timeout=LOAD_TIMEOUT_S)
    if res.get("errorText"):
        raise Failed("the page did not load (%s)" % res["errorText"])
    end = time.monotonic() + LOAD_TIMEOUT_S
    while time.monotonic() < end:
        state = tab.evaluate("[document.readyState, location.href]", timeout=5.0)
        if (isinstance(state, list) and state[0] == "complete"
                and str(state[1]).startswith(("http://", "https://"))):
            return str(state[1])
        run.nap()
    raise Failed("the page did not finish loading within %.0f seconds" % LOAD_TIMEOUT_S)


def wait_for(run, tab, expression, timeout=FIND_TIMEOUT_S):
    """Poll an expression until it is truthy; its value, or None at the timeout. The
    caller decides what None means, because only the caller knows what was expected."""
    end = time.monotonic() + timeout
    while True:
        value = tab.evaluate(expression, timeout=5.0)
        if value:
            return value
        if time.monotonic() >= end:
            return None
        run.nap()


# THE FINDER. One function in the page that picks ONE element and marks it, so the click
# that follows (a real mouse event, from Python) and its fallback (.click(), in the page)
# act on the same node. Matching is on what a person SEES - text, aria-label, title, alt,
# placeholder - normalised for case and whitespace; ranked exact > starts-with > contains,
# then the tightest match (shortest text) so the label wins over the card that wraps it,
# then document order. A match that is not itself clickable climbs to the nearest ancestor
# that is. `selector` narrows the pool when structure is all there is ("the first result"),
# `within` scopes it, `skip` names ancestors to pass over (adverts), `hrefHas` filters
# links. Shadow DOM is not entered: neither site in this phase needs it, and a later phase
# that does will add it here, once, for everyone.
_FIND_JS = r"""
(function (o) {
  var norm = function (s) { return String(s || '').replace(/\s+/g, ' ').trim().toLowerCase(); };
  var CLICKABLE = 'a[href],button,[role=button],[role=link],[role=tab],[role=option],' +
                  '[role=menuitem],[onclick],input[type=submit],input[type=button],summary,label';
  var root = o.within ? document.querySelector(o.within) : document;
  if (!root) return null;
  var visible = function (el) {
    var r = el.getBoundingClientRect();
    if (r.width < 2 || r.height < 2) return false;
    var cs = getComputedStyle(el);
    return cs.visibility !== 'hidden' && cs.display !== 'none' && +cs.opacity > 0.05;
  };
  // Each thing a person can see, SEPARATELY - joined, a button whose text and aria-label
  // both read "Watch Now" says "watch now watch now" and can never match exactly. A tile
  // that is only a picture is named by its images' alt text.
  var said = function (el) {
    var out = [el.innerText || el.textContent, el.getAttribute('aria-label'),
               el.getAttribute('title'), el.getAttribute('alt'), el.getAttribute('placeholder')];
    var imgs = el.querySelectorAll ? el.querySelectorAll('img[alt]') : [];
    for (var k = 0; k < imgs.length && k < 3; k++) out.push(imgs[k].getAttribute('alt'));
    return out.map(norm).filter(Boolean);
  };
  var avoid = (o.notText || []).map(norm);
  var pool;
  if (o.selector) {
    pool = Array.prototype.slice.call(root.querySelectorAll(o.selector));
  } else {
    pool = Array.prototype.slice.call(root.querySelectorAll(CLICKABLE));
    if (o.text) {
      var q0 = norm(o.text), w = document.createTreeWalker(root, NodeFilter.SHOW_TEXT), n;
      while ((n = w.nextNode())) {
        if (n.parentElement && norm(n.data).indexOf(q0) >= 0) pool.push(n.parentElement);
      }
      pool = pool.concat(Array.prototype.slice.call(
        root.querySelectorAll('[aria-label],[title],[alt]')));
    }
  }
  var q = norm(o.text), best = null, bestKey = null, seen = new Set();
  for (var i = 0; i < pool.length; i++) {
    var el = pool[i];
    if (seen.has(el)) continue;
    seen.add(el);
    if (o.skip && el.closest(o.skip)) continue;
    if (o.hrefHas && String(el.getAttribute('href') || '').indexOf(o.hrefHas) < 0) continue;
    if (el.closest('[data-op-ignore]')) continue;
    var texts = said(el);
    if (o.needText && !texts.length) continue;
    if (avoid.length && texts.some(function (t) {
      return avoid.some(function (a) { return t.indexOf(a) >= 0; }); })) continue;
    var rank = 3, size = 0;
    if (q) {
      texts.forEach(function (t) {
        var r = t === q ? 0 : t.indexOf(q) === 0 ? 1 : t.indexOf(q) >= 0 ? 2 : 3;
        if (r < rank || (r === rank && t.length < size)) { rank = r; size = t.length; }
      });
      if (rank === 3) continue;
    } else {
      rank = 0;
    }
    if (!visible(el)) continue;
    // `first`: document order decides among ALL matches ("the first result that mentions
    // it"); otherwise the best match wins and the tightest text breaks the tie.
    var key = o.first ? [0, 0, i] : [rank, size, i];
    if (!best || key[0] < bestKey[0] || (key[0] === bestKey[0] &&
        (key[1] < bestKey[1] || (key[1] === bestKey[1] && key[2] < bestKey[2])))) {
      best = el; bestKey = key;
    }
  }
  if (!best) return null;
  var hit = best.closest(CLICKABLE) || best;
  document.querySelectorAll('[data-op-pick]').forEach(function (e) {
    e.removeAttribute('data-op-pick'); });
  hit.setAttribute('data-op-pick', o.nonce);
  hit.scrollIntoView({block: 'center', inline: 'center'});
  var r = hit.getBoundingClientRect();
  var x = Math.round(r.left + r.width / 2), y = Math.round(r.top + r.height / 2);
  var top = document.elementFromPoint(x, y);
  return {x: x, y: y, clear: !!top && (top === hit || hit.contains(top) || top.contains(hit)),
          // The cleanest name it has: a title attribute (YouTube's, without the duration
          // aria-label adds), a picture's alt (Hotstar's tiles), then the visible text.
          label: String(best.getAttribute('title') ||
                        ((best.querySelector && best.querySelector('img[alt]')) || {alt: ''}).alt ||
                        best.innerText || best.textContent || best.getAttribute('aria-label') ||
                        '').replace(/\s+/g, ' ').trim().slice(0, 200),
          href: hit.getAttribute('href') || ''};
})(%s)
"""


def find(tab, text=None, selector=None, within=None, skip=None, href_has=None,
         need_text=False, first=False, not_text=()):
    """The element a person would mean, marked in the page, or None. Nothing is clicked.
    `first` takes the first match in document order rather than the best; `not_text`
    passes over anything whose visible text contains one of these ("watchlist")."""
    opts = {"text": text or "", "selector": selector, "within": within, "skip": skip,
            "hrefHas": href_has, "needText": bool(need_text), "first": bool(first),
            "notText": list(not_text or ()),
            "nonce": base64.b16encode(os.urandom(4)).decode("ascii")}
    found = tab.evaluate(_FIND_JS % json.dumps(opts), timeout=5.0)
    if isinstance(found, dict):
        found["nonce"] = opts["nonce"]
        return found
    return None


def click_at(tab, x, y):
    """A real left click at viewport (x, y): moved, pressed, released. Trusted input, so
    the page gets a genuine user activation - which is what lets media start with sound."""
    for kind in ("mouseMoved", "mousePressed", "mouseReleased"):
        tab.call("Input.dispatchMouseEvent",
                 {"type": kind, "x": x, "y": y, "button": "left" if kind != "mouseMoved"
                  else "none", "clickCount": 1 if kind != "mouseMoved" else 0})


def find_and_click(run, tab, what, timeout=FIND_TIMEOUT_S, **how):
    """Wait for the element find() describes, then click it. Its label, or Failed naming
    what was looked for. If something is drawn over it (a banner, a tooltip) the real
    click would land on the cover, so the page's own .click() is used on the marked node
    instead - still the same element, just without the trusted gesture."""
    end = time.monotonic() + timeout
    while True:
        run.check()
        found = find(tab, **how)
        if found:
            break
        if time.monotonic() >= end:
            raise Failed("I could not find %s on the page" % what)
        run.nap()
    run.check()               # the last safe point before the page is touched
    run.nap(0.15)             # scrollIntoView settles before the coordinates are used
    again = tab.evaluate(
        "(function(){var e=document.querySelector('[data-op-pick=\"%s\"]');if(!e)return null;"
        "var r=e.getBoundingClientRect(),x=Math.round(r.left+r.width/2),"
        "y=Math.round(r.top+r.height/2),t=document.elementFromPoint(x,y);"
        "return {x:x,y:y,clear:!!t&&(t===e||e.contains(t)||t.contains(e))};})()"
        % found["nonce"], timeout=5.0) or found
    if again.get("clear"):
        click_at(tab, again["x"], again["y"])
    else:
        tab.evaluate("(function(){var e=document.querySelector('[data-op-pick=\"%s\"]');"
                     "if(e)e.click();})()" % found["nonce"], gesture=True)
    return found


_FOCUS_JS = r"""
(function (hint) {
  var norm = function (s) { return String(s || '').replace(/\s+/g, ' ').trim().toLowerCase(); };
  var h = norm(hint);
  var els = document.querySelectorAll('input:not([type=hidden]):not([disabled]),textarea,' +
    '[contenteditable=""],[contenteditable=true],[role=searchbox],[role=textbox],[role=combobox]');
  for (var i = 0; i < els.length; i++) {
    var el = els[i], r = el.getBoundingClientRect();
    if (r.width < 2 || r.height < 2) continue;
    var says = norm([el.getAttribute('placeholder'), el.getAttribute('aria-label'),
                     el.getAttribute('name'), el.getAttribute('type'), el.id,
                     el.getAttribute('title')].join(' '));
    if (h && says.indexOf(h) < 0) continue;
    el.scrollIntoView({block: 'center'});
    r = el.getBoundingClientRect();
    el.setAttribute('data-op-input', '1');
    return {x: Math.round(r.left + r.width / 2), y: Math.round(r.top + r.height / 2)};
  }
  return null;
})(%s)
"""


def focus_input(run, tab, hint="", what="a box to type in", timeout=FIND_TIMEOUT_S):
    """Find a visible text input whose placeholder / label / name / type mentions `hint`
    (any visible input if hint is empty), click into it for real, and confirm it now has
    focus. Typing then goes through type_text(), which types into whatever has focus."""
    end = time.monotonic() + timeout
    while True:
        run.check()
        spot = tab.evaluate(_FOCUS_JS % json.dumps(hint or ""), timeout=5.0)
        if spot:
            break
        if time.monotonic() >= end:
            raise Failed("I could not find %s on the page" % what)
        run.nap()
    run.check()
    click_at(tab, spot["x"], spot["y"])
    run.nap(0.15)
    focused = tab.evaluate("(function(){var a=document.activeElement;return !!a&&"
                           "(a.hasAttribute('data-op-input')||!!a.closest('[data-op-input]')||"
                           "a.isContentEditable||/^(INPUT|TEXTAREA)$/.test(a.tagName));})()")
    if not focused:
        tab.evaluate("(function(){var e=document.querySelector('[data-op-input]');"
                     "if(e)e.focus();})()", gesture=True)
    return True


def type_text(run, tab, text):
    """Type into whatever currently has focus. Input.insertText, as the proofs do: one
    'input' event with the whole string, which React and plain inputs both accept, and
    no keyboard layout to get wrong for non-ASCII text."""
    run.check()
    tab.call("Input.insertText", {"text": str(text)})


_KEYS = {
    "Enter": {"code": "Enter", "windowsVirtualKeyCode": 13, "text": "\r"},
    "Escape": {"code": "Escape", "windowsVirtualKeyCode": 27},
    "Tab": {"code": "Tab", "windowsVirtualKeyCode": 9},
}


def press_key(run, tab, key):
    """One named key, down and up, to whatever has focus (chain_proof.mjs's Enter)."""
    run.check()
    spec = _KEYS[key]
    for kind in ("keyDown", "keyUp"):
        params = {"type": kind, "key": key, "code": spec["code"],
                  "windowsVirtualKeyCode": spec["windowsVirtualKeyCode"],
                  "nativeVirtualKeyCode": spec["windowsVirtualKeyCode"]}
        if kind == "keyDown" and spec.get("text"):
            params["text"] = spec["text"]
        tab.call("Input.dispatchKeyEvent", params)


_VIDEO_JS = r"""
(function () {
  var vs = Array.prototype.slice.call(document.querySelectorAll('video'));
  var best = null, area = 0;
  vs.forEach(function (v) { var r = v.getBoundingClientRect();
    if (r.width * r.height > area) { area = r.width * r.height; best = v; } });
  if (!best) return null;
  return {t: best.currentTime, paused: best.paused, ready: best.readyState,
          ended: best.ended, muted: best.muted,
          d: isFinite(best.duration) ? best.duration : -1,
          // YouTube marks its player .ad-showing. Hotstar has NO reliable marker: an
          // .ad-info node was seen once, then absent for a whole 10-second pre-roll in a
          // 0.7 s timeline (2026-10-14) - see short_is_ad in wait_playing.
          ad: !!document.querySelector('.ad-showing, .ad-interrupting')};
})()
"""


def wait_playing(run, tab, timeout=PLAY_TIMEOUT_S, need_sound=False, short_is_ad=False):
    """(playing, ad, muted) once the page's biggest <video> is SEEN to play: not paused,
    and its clock has moved between two looks. If it sits paused - an autoplay policy, a
    player waiting for a click - it is asked to play() once, as a user gesture, and
    watched again. A video element that exists is not a video that is playing, and only
    the second is ever reported. `ad` lets the line say an advert is playing first.

    need_sound: a MUTED video does not count. Measured on Hotstar 2026-10-14: a search
    result tile plays a muted 35-second hover preview, and a show page plays a muted
    full-width trailer, and either one reads as "playing" by the clock alone - which is
    how the first version of this reported "started bigg boss" from a results page that
    never moved. `muted` in the answer is True when that is all it saw.

    short_is_ad: a playing video of 30 seconds or less counts as a probable advert. For a
    site with no ad marker in the DOM, the clip itself is the only tell - measured on
    Hotstar: a 10-second video played, then the 1745-second highlights replaced it."""
    end = time.monotonic() + timeout
    nudged, last, saw_muted = False, None, False
    started = time.monotonic()
    while time.monotonic() < end:
        now = tab.evaluate(_VIDEO_JS, timeout=5.0)
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


# =============================================================================
#  THE SITES - the only part of this file that knows anything about one
# =============================================================================

def resolve(site, query=""):
    """(kind, url, plan) for what the hand WILL do - used by the run and by hands.py's
    proposal, so the sentence the employer approves and the thing that happens are
    computed by the same code. kind is youtube / hotstar / open, or "" when the site
    cannot be opened at all, in which case plan is the reason."""
    raw = " ".join(str(site or "").split())
    q = " ".join(str(query or "").split())
    key = raw.lower().rstrip("/")
    for name in ("https://", "http://"):
        if key.startswith(name) and urllib.parse.urlsplit(key).path in ("", "/"):
            key = key[len(name):]
    key = key.rstrip("/")
    if key in SITE_ALIASES["youtube"]:
        if q:
            return ("youtube", YOUTUBE_RESULTS % urllib.parse.quote_plus(q),
                    "play the first result for '%s'" % q)
        return "youtube", YOUTUBE_HOME, "do nothing more - there is nothing to search for"
    if key in SITE_ALIASES["hotstar"]:
        if q:
            return ("hotstar", HOTSTAR_HOME,
                    "try to start the first match for '%s'" % q)
        return "hotstar", HOTSTAR_HOME, "do nothing more - there is nothing to search for"
    if not raw:
        return "", "", "there was no site to open"
    # A scheme with no "//" - javascript:, data:, file:, chrome: - is not a bare domain
    # with https:// missing; it is something that must not be opened at all. Measured: it
    # used to get https:// stuck on the front and die parsing "alert(1)" as a port.
    scheme = raw.split(":", 1)[0].lower() if ":" in raw else ""
    if "://" not in raw and scheme and not raw.split(":", 1)[1].split("/", 1)[0].isdigit():
        return "", "", "I only open web pages, and '%s' is not one" % raw
    # https by default; plain http for this machine's own servers, which have no TLS.
    loopback = raw.lower().split(":", 1)[0].split("/", 1)[0] in ("localhost", "127.0.0.1")
    url = raw if "://" in raw else ("http://" if loopback else "https://") + raw
    parts = urllib.parse.urlsplit(url)
    host = (parts.hostname or "").lower()
    try:
        parts.port
    except ValueError:
        return "", "", "'%s' is not a web address I can open" % raw
    if parts.scheme not in ("http", "https"):
        return "", "", "I only open web pages, and '%s' is not one" % raw
    if not host or " " in raw or not all(c.isalnum() or c in ".-" for c in host):
        return "", "", "'%s' is not a web address I can open" % raw
    if "." not in host and host != "localhost":
        host += ".com"
        url = urllib.parse.urlunsplit((parts.scheme, host + (":%d" % parts.port
                                                             if parts.port else ""),
                                       parts.path, parts.query, parts.fragment))
    return "open", url, "do nothing more on it - no search, no clicks"


def describe(site, query=""):
    """(where, plan) for hands.py's proposal blanks {where} and {plan}, or None when the
    site cannot be opened (the blanks then stand, visibly, and the run refuses). `where`
    is the HOST that will be opened, so a guessed ".com" is on the card before Yes."""
    kind, url, plan = resolve(site, query)
    if not kind:
        return None
    where = {"youtube": "YouTube", "hotstar": "Hotstar"}.get(kind) or (
        urllib.parse.urlsplit(url).hostname or url)
    return where, plan


def play_youtube(run, tab, url, query):
    navigate(run, tab, url, "opening YouTube's results for '%s'" % query)
    run.at("looking for the first video in the results")
    # Structure, not text, because "the first result" has no text of its own: the title
    # link of the first ordinary video card, outside adverts and Shorts shelves. Measured
    # on 2026-10-14: the bare "any /watch link" also catches Mix cards (yt-lockup-view-
    # model, a playlist) and thumbnails whose only text is the duration, so the title link
    # is asked for first and the bare form is only the fallback for a redesign. Everything
    # about HOW it is found and clicked is the general finder.
    skip = ("ytd-ad-slot-renderer, ytd-promoted-video-renderer, ytd-in-feed-ad-layout-"
            "renderer, ytd-reel-shelf-renderer, ytd-shorts, [is-shorts], ytd-masthead, "
            "#masthead-ad, ytd-display-ad-renderer")
    try:
        found = find_and_click(run, tab, "a video in YouTube's results", timeout=12.0,
                               selector="ytd-video-renderer a#video-title[href*='/watch?v=']",
                               skip=skip, need_text=True)
    except Failed:
        found = find_and_click(run, tab, "a video in YouTube's results", timeout=3.0,
                               selector="a[href*='/watch?v=']", skip=skip, need_text=True)
    title = found.get("label") or ""
    run.at("opening '%s'" % (ascii_words(title, 60) or "the first result"))
    if not wait_for(run, tab, "location.pathname === '/watch'", timeout=12.0):
        raise Failed("I clicked the first result but YouTube never opened the video page")
    run.at("waiting for the video to start")
    playing, ad, muted = wait_playing(run, tab)
    if not playing:
        raise Failed("I opened the video, but it did not start playing within %.0f "
                     "seconds" % PLAY_TIMEOUT_S)
    # The watch page's own title first: measured 2026-10-14, the RESULTS page showed
    # "Tum Hi Ho" under a Hindi-translated title the line cannot speak, while the watch
    # page carried the original English one.
    watched = tab.evaluate("(function(){var h=document.querySelector("
                           "'h1.ytd-watch-metadata, #title h1');return (h&&h.innerText)||"
                           "document.title.replace(/ - YouTube$/,'');})()", timeout=5.0)
    said_title = ascii_words(watched, 70) or ascii_words(title, 70)
    tail = " - the first result, '%s'" % said_title if said_title else ""
    if ad:
        tail += " (an advert is playing first)"
    if muted:
        tail += " - muted, as the player was left"
    return "Opened YouTube and started playing %s%s." % (ascii_words(query) or "it", tail)


_WALL_JS = r"""
(function () {
  var t = (document.body && document.body.innerText || '').toLowerCase();
  if (/log ?in to (watch|continue)|login to (watch|continue)|sign in to watch/.test(t)) return 'login';
  if (/subscribe to watch|upgrade to watch|choose a plan|buy a plan/.test(t)) return 'subscription';
  return '';
})()
"""


def play_hotstar(run, tab, url, query):
    """BEST-EFFORT. See the docstring: an SPA that moves, behind a login."""
    navigate(run, tab, url, "opening Hotstar")
    run.at("opening Hotstar's search")
    # The site's own Search, found by its words - the nav item reads "Search" (and is a
    # link to /in/explore today, which is the point of not hard-coding that).
    find_and_click(run, tab, "Hotstar's Search button", text="search",
                   selector="a, button, [role=button], [role=link], nav *, header *")
    run.at("typing '%s' into Hotstar's search" % query)
    focus_input(run, tab, "search", what="Hotstar's search box")
    type_text(run, tab, query)
    press_key(run, tab, "Enter")
    run.at("looking for '%s' in Hotstar's results" % query)
    # The FIRST result LINK whose visible text or picture alt mentions the query. A link,
    # because the suggestion list under the box is bare <p> text that echoes the query
    # exactly and goes nowhere when clicked (measured: "bigg boss" ranked the suggestion
    # over every real tile). First, because "the first result" is what was promised.
    found = find_and_click(run, tab, "a result for '%s'" % query, text=query,
                           selector="a[href]", first=True,
                           skip="header, nav, [role=search], [data-op-input]")
    label = ascii_words(found.get("label"), 60) or ascii_words(query)
    run.at("opening '%s'" % label)
    if not wait_for(run, tab, "!/\\/explore/.test(location.pathname)", timeout=10.0):
        raise Failed("I clicked %s, but Hotstar stayed on its search results" % label)
    run.at("starting '%s'" % label)
    # A watch link plays by itself; a title page plays a MUTED trailer and wants its Watch
    # button pressed. need_sound is what tells the two apart - see wait_playing.
    playing, ad, muted = wait_playing(run, tab, timeout=5.0, need_sound=True,
                                      short_is_ad=True)
    if not playing:
        buttons = "button, a[href], [role=button]"
        for word in ("watch live", "watch latest episode", "watch first episode",
                     "watch now", "watch", "play", "resume"):
            if find(tab, text=word, selector=buttons, skip="header, nav",
                    not_text=("watchlist",)):
                run.at("pressing Watch on '%s'" % label)
                find_and_click(run, tab, "a Watch button", timeout=2.0, text=word,
                               selector=buttons, skip="header, nav",
                               not_text=("watchlist",))
                break
        run.at("starting '%s'" % label)
        playing, ad, more_muted = wait_playing(run, tab, timeout=PLAY_TIMEOUT_S,
                                               need_sound=True, short_is_ad=True)
        muted = muted or more_muted
    if playing:
        return "Opened Hotstar and started %s%s." % (
            label, " - a short clip is playing first, most likely an advert" if ad else "")
    wall = tab.evaluate(_WALL_JS, timeout=5.0)
    if wall == "login":
        raise Failed("I found %s on Hotstar, but it wants you logged in before it will "
                     "play - the page is open for you" % label)
    if wall == "subscription":
        raise Failed("I found %s on Hotstar, but it needs a subscription to play - the "
                     "page is open for you" % label)
    if muted:
        raise Failed("I found %s on Hotstar, but only a silent preview played, not the "
                     "thing itself - the page is open for you to take from there" % label)
    raise Failed("I found %s on Hotstar and opened it, but no video started - the page "
                 "is open for you to take from there" % label)


def open_only(run, tab, url):
    landed = navigate(run, tab, url, "opening %s" % (urllib.parse.urlsplit(url).hostname
                                                      or url))
    host = urllib.parse.urlsplit(landed).hostname or landed
    return ("Opened %s - I only opened it; nothing on the page was searched or clicked."
            % ascii_words(host, 80))


# =============================================================================
#  MAIN
# =============================================================================

def main():
    try:
        raw = sys.stdin.buffer.read().decode("utf-8", "replace")
        params = json.loads(raw) if raw.strip() else {}
    except ValueError:
        say("I could not read what to open, sir - the request was not JSON.")
        return 1
    if not isinstance(params, dict):
        say("I could not read what to open, sir.")
        return 1
    query = " ".join(str(params.get("query") or "").split())
    kind, url, plan = resolve(params.get("site"), query)
    if not kind:
        say("I did not open anything, sir - %s." % ascii_words(plan, 160))
        return 1

    port, browser_ws = live_port()
    if port is None:
        say(NO_PORT)
        return 1

    panic = PanicKey()
    run = Run(panic)
    tab = None
    try:
        if not panic.arm():
            if sys.platform == "win32":
                say("I could not arm Ctrl+H, sir (%s), so I have not touched the browser."
                    % panic.why)
                return 1
            sys.stderr.write("operator_browser: NO PANIC KEY - %s\n" % panic.why)
        tab = open_tab(run, port, browser_ws)
        if kind == "youtube" and query:
            line = play_youtube(run, tab, url, query)
        elif kind == "hotstar" and query:
            line = play_hotstar(run, tab, url, query)
        else:
            line = open_only(run, tab, url)
        run.check()               # a Ctrl+H on the last tick is still a Ctrl+H
        say(line)
        return 0
    except Aborted as stop:
        say("Stopped - you took back control after %s." % ascii_words(stop.args[0], 120))
        return 1
    except Failed as exc:
        reason = str(exc).strip().rstrip(".")
        say("%s%s." % (reason[:1].upper(), reason[1:]) if reason.startswith("I ")
            else "That did not work, sir - %s." % reason)
        return 1
    finally:
        panic.disarm()
        if tab is not None:
            tab.close()


if __name__ == "__main__":
    sys.exit(main())
