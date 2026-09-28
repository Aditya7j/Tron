#!/usr/bin/env python3
"""preflight.py - every live chain, end to end, with a verdict.

Not unit tests, and nothing here is mocked. Real HTTP against the running server,
a real signed call to the real provider, a real markdown file written into the real
notes folder and read back through /chat, a real JPEG judged by the real model.

That is the whole point. The failures that actually hurt are the ones where every
unit test passes and a live chain is dead: an expired session token, a model id the
key cannot reach, a served file that is not the file on disk, an endpoint that 400s
on a media type the client never sends. A mock cannot see any of them, because a
mock is a description of what we believed at the time.

  python preflight.py              run everything, print a verdict
  python preflight.py --quiet      the summary line only
  python preflight.py --keep-note  leave the /remember probe note in the galaxy

The probe note is written into the real corpus and then removed again, with the
index rebuilt, so running this does not slowly fill your notes with test data.

Exit status is the number of failed checks, so a shell or CI can branch on it.
"""

import ast
import base64
import hashlib
import http.client
import inspect
import json
import os
import re
import subprocess
from tools import _proc
import sys
import textwrap
import time
import urllib.error
import urllib.parse

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
sys.dont_write_bytecode = True          # this file leaves nothing behind, __pycache__ included

# The server's own module, so every constant checked here is the one the server
# actually uses. A preflight that hardcodes "image/jpeg" cannot catch the day
# somebody changes FRAME_MEDIA_TYPE in one place and not the other.
import server                                                  # noqa: E402
import focus                                                   # noqa: E402
# The intake's own declaration, so check 37 counts the questions the module declares rather
# than the number seventeen written twice. Standard library only, like build.py.
import census                                                  # noqa: E402
# The doorman's own module, for the same reason: check 25 asks voiceprint.hygiene() rather
# than re-implementing the store's house rules, so the rules cannot drift apart from the
# code that enforces them. Imported softly - a machine without onnxruntime should still be
# able to run the other 25 checks.
try:
    import voiceprint                                          # noqa: E402
except Exception as _vp_exc:                                   # noqa: BLE001
    voiceprint, VOICEPRINT_WHY = None, "%s: %s" % (type(_vp_exc).__name__, _vp_exc)
else:
    VOICEPRINT_WHY = ""

PASS, FAIL, WARN = "pass", "fail", "warn"
QUIET = "--quiet" in sys.argv[1:]
KEEP_NOTE = "--keep-note" in sys.argv[1:]


try:
    # Windows consoles still default to a legacy code page, and a verdict is worth
    # nothing if the reporter dies printing it.
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:                                              # noqa: BLE001
    pass


def _glyph(preferred, fallback):
    try:
        preferred.encode(sys.stdout.encoding or "ascii")
        return preferred
    except Exception:                                          # noqa: BLE001
        return fallback


MARK = {PASS: _glyph("✓", "ok"), FAIL: _glyph("✗", "XX"),
        WARN: _glyph("!", "!!")}

results = []          # (state, name)
bodies = []           # (label, bytes) - every response body seen, for the leak scan
state = {"up": False, "health": {}, "graph": None, "notes": 0}


def out(line):
    """Never let an unprintable character in a model's answer break the report."""
    enc = sys.stdout.encoding or "utf-8"
    try:
        line.encode(enc)
    except UnicodeEncodeError:
        line = line.encode(enc, "replace").decode(enc, "replace")
    print(line)


def say(*parts):
    if not QUIET:
        out(" ".join(str(p) for p in parts))


def http_call(method, path, body=None, headers=None, timeout=45, label=None):
    """One request, exactly as written. http.client does not normalise the path,
    which is what makes the traversal probes in check 9 meaningful."""
    conn = http.client.HTTPConnection(server.HOST, server.PORT, timeout=timeout)
    try:
        conn.request(method, path, body=body, headers=dict(headers or {}))
        res = conn.getresponse()
        data = res.read()
        head = {k.lower(): v for k, v in res.getheaders()}
        bodies.append((label or ("%s %s" % (method, path.split("?")[0])), data))
        return res.status, head, data
    finally:
        conn.close()


def as_json(data):
    try:
        return json.loads(data.decode("utf-8", "replace"))
    except Exception:                                          # noqa: BLE001
        return None


def post_json(path, payload, timeout=120, label=None):
    body = json.dumps(payload).encode("utf-8")
    return http_call("POST", path, body,
                     {"Content-Type": "application/json",
                      "Content-Length": str(len(body))}, timeout, label)


def first_line(text, width=96):
    line = re.sub(r"\s+", " ", str(text or "")).strip()
    return line if len(line) <= width else line[:width - 3] + "..."


# =============================================================================
#  THE PROBE FRAME
#
#  /see must be handed a real JPEG and there is no image library in the standard
#  library, so this writes one by hand. It is an ordinary baseline JPEG with one
#  shortcut: every 8x8 block carries its DC coefficient and nothing else, which
#  makes each block a flat colour and the encoder forty lines instead of four
#  hundred. Drawing therefore happens on an 8-pixel grid - which is exactly enough
#  for large, crisp lettering the model can be asked to read back.
#
#  That read-back is the check that matters. "The endpoint returned 200" only
#  proves the plumbing; a heading read back correctly proves the bytes survived
#  encoding, upload, base64, the provider's decoder and the model's eyes.
# =============================================================================

COLS, ROWS = 80, 40                      # 8px blocks -> a 640x320 frame
HEADING = "PREFLIGHT"
BAR_COLOURS = "red, green, amber"

FONT = {
    "P": ("111", "101", "111", "100", "100"),
    "R": ("111", "101", "111", "110", "101"),
    "E": ("111", "100", "111", "100", "111"),
    "F": ("111", "100", "111", "100", "100"),
    "L": ("100", "100", "100", "100", "111"),
    "I": ("111", "010", "010", "010", "111"),
    "G": ("111", "100", "101", "101", "111"),
    "H": ("101", "101", "111", "101", "101"),
    "T": ("111", "010", "010", "010", "010"),
}

DC_BITS = [0, 0, 0, 12] + [0] * 12       # twelve 4-bit codes: categories 0..11
DC_VALS = list(range(12))
AC_BITS = [1] + [0] * 15                 # one 1-bit code, and it is end-of-block
AC_VALS = [0]
QUANT = 16                               # flat table; only the DC term is coded


class _Bits:
    def __init__(self):
        self.out = bytearray()
        self.acc = 0
        self.n = 0

    def put(self, value, length):
        for shift in range(length - 1, -1, -1):
            self.acc = (self.acc << 1) | ((value >> shift) & 1)
            self.n += 1
            if self.n == 8:
                self.out.append(self.acc)
                if self.acc == 0xFF:
                    self.out.append(0x00)          # byte stuffing, not optional
                self.acc = 0
                self.n = 0

    def flush(self):
        while self.n:
            self.put(1, 1)


def _huff(bits, vals):
    """Canonical JPEG code assignment: BITS/HUFFVAL -> {symbol: (code, length)}."""
    codes, code, k = {}, 0, 0
    for length in range(1, 17):
        for _ in range(bits[length - 1]):
            codes[vals[k]] = (code, length)
            code += 1
            k += 1
        code <<= 1
    return codes


def _paint():
    """A synthetic screen: one big heading and three bars of known colour."""
    bg, panel, ink = (18, 20, 32), (32, 36, 54), (238, 240, 248)
    grid = [[bg] * COLS for _ in range(ROWS)]

    def rect(x0, y0, x1, y1, colour):
        for y in range(y0, y1 + 1):
            for x in range(x0, x1 + 1):
                grid[y][x] = colour

    rect(2, 2, COLS - 3, ROWS - 3, panel)
    scale, x = 2, 5
    for char in HEADING:
        for r, row in enumerate(FONT[char]):
            for c, bit in enumerate(row):
                if bit == "1":
                    rect(x + c * scale, 5 + r * scale,
                         x + c * scale + scale - 1, 5 + r * scale + scale - 1, ink)
        x += 4 * scale
    for colour, top, right in (((214, 70, 66), 20, 70),
                               ((72, 190, 116), 26, 46),
                               ((236, 176, 62), 32, 26)):
        rect(6, top, right, top + 3, colour)
    return grid


def _segment(marker, payload):
    return bytes([0xFF, marker]) + (len(payload) + 2).to_bytes(2, "big") + payload


def probe_frame():
    """(jpeg bytes, width, height) - a real, decodable, baseline JPEG."""
    grid = _paint()
    dc_codes, ac_codes = _huff(DC_BITS, DC_VALS), _huff(AC_BITS, AC_VALS)
    bits, pred = _Bits(), [0, 0, 0]
    for by in range(ROWS):
        for bx in range(COLS):
            r, g, b = grid[by][bx]
            channels = (0.299 * r + 0.587 * g + 0.114 * b,
                        128 - 0.168736 * r - 0.331264 * g + 0.5 * b,
                        128 + 0.5 * r - 0.418688 * g - 0.081312 * b)
            for comp, value in enumerate(channels):
                # A flat 8x8 block of value v has DC coefficient 8*(v-128).
                dc = int(round(8.0 * (value - 128.0) / QUANT))
                diff = dc - pred[comp]
                pred[comp] = dc
                size = 0
                while abs(diff) >> size:
                    size += 1
                bits.put(*dc_codes[size])
                if size:
                    bits.put(diff if diff > 0 else diff + (1 << size) - 1, size)
                bits.put(*ac_codes[0])                 # end of block, every block
    bits.flush()

    width, height = COLS * 8, ROWS * 8
    jpeg = b"\xff\xd8"
    jpeg += _segment(0xE0, b"JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00")
    jpeg += _segment(0xDB, bytes([0x00]) + bytes([QUANT]) * 64)
    jpeg += _segment(0xC0, bytes([8]) + height.to_bytes(2, "big") +
                     width.to_bytes(2, "big") + bytes([3]) +
                     b"".join(bytes([i, 0x11, 0x00]) for i in (1, 2, 3)))
    jpeg += _segment(0xC4, bytes([0x00]) + bytes(DC_BITS) + bytes(DC_VALS))
    jpeg += _segment(0xC4, bytes([0x10]) + bytes(AC_BITS) + bytes(AC_VALS))
    jpeg += _segment(0xDA, bytes([3]) +
                     b"".join(bytes([i, 0x00]) for i in (1, 2, 3)) +
                     bytes([0x00, 0x3F, 0x00]))
    jpeg += bytes(bits.out) + b"\xff\xd9"
    return jpeg, width, height


# -----------------------------------------------------------------------------
#  A REAL PDF, WRITTEN BY HAND, for the same reason probe_frame() writes a real JPEG.
#
#  Check 17 has to prove that the ingestion engine reads a PDF, so the bytes it is given
#  must be a PDF that a PDF library agrees to open - offsets, xref table, trailer and all.
#  A file called .pdf with prose in it would prove nothing except that the extractor is
#  lenient. This is about 60 lines and it depends on nothing: no pypdf, no reportlab, and
#  no fixture checked into the repository that could drift away from what the check
#  asserts about it.
#
#  It also writes the OTHER kind of page, which is the harder half of the feature: pass an
#  empty string and the page has a grey rectangle on it and no text operators at all. That
#  is exactly what a scanned page looks like to an extractor - a page that exists, has
#  size, and holds nothing to read - so the honest line about a scan can be tested without
#  anybody having to photograph a piece of paper.
# -----------------------------------------------------------------------------

def _pdf_escape(text):
    return (str(text).replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)"))


def probe_pdf(pages):
    """PDF bytes, one page per item. A string is a text page; "" is an image-only page."""
    pages = list(pages)
    count = len(pages)
    # 1 catalog, 2 pages tree, then a (page, contents) pair each, then the font last.
    font_num = 3 + 2 * count
    objects = {}

    kids = " ".join("%d 0 R" % (3 + 2 * i) for i in range(count))
    objects[1] = "<< /Type /Catalog /Pages 2 0 R >>"
    objects[2] = "<< /Type /Pages /Kids [%s] /Count %d >>" % (kids, count)

    for i, text in enumerate(pages):
        page_num, content_num = 3 + 2 * i, 4 + 2 * i
        if text:
            stream = ("BT /F1 16 Tf 72 700 Td (%s) Tj ET" % _pdf_escape(text))
            resources = "<< /Font << /F1 %d 0 R >> >>" % font_num
        else:
            # No text operators anywhere in this stream: a grey box and nothing to read.
            stream = "0.85 0.85 0.85 rg 72 560 468 180 re f"
            resources = "<< >>"
        objects[page_num] = ("<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                             "/Resources %s /Contents %d 0 R >>"
                             % (resources, content_num))
        objects[content_num] = ("<< /Length %d >>\nstream\n%s\nendstream"
                                % (len(stream.encode("latin-1")), stream))
    objects[font_num] = "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"

    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = {}
    for num in sorted(objects):
        offsets[num] = len(out)
        out += ("%d 0 obj\n%s\nendobj\n" % (num, objects[num])).encode("latin-1")

    # The cross-reference table. Every entry is exactly twenty bytes, which is not a
    # style choice - a PDF reader seeks into this table by multiplying.
    start = len(out)
    size = font_num + 1
    out += ("xref\n0 %d\n" % size).encode("latin-1")
    out += b"0000000000 65535 f \n"
    for num in range(1, size):
        out += ("%010d 00000 n \n" % offsets[num]).encode("latin-1")
    out += ("trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n"
            % (size, start)).encode("latin-1")
    return bytes(out)


# =============================================================================
#  THE CHECKS, in the order a failure is most useful to hear about
# =============================================================================

def check_server():
    """1. The server is up and serving the viewer."""
    try:
        status, _, body = http_call("GET", "/", timeout=10, label="GET /")
    except OSError as exc:
        return FAIL, ["nothing is listening on http://%s:%d (%s)"
                      % (server.HOST, server.PORT, exc),
                      "start it with:  %s server.py" % os.path.basename(sys.executable)]
    if status != 200:
        return FAIL, ["GET / returned HTTP %s" % status]
    if b"<title>Knowledge Galaxy" not in body or b"graph-data.js" not in body:
        return FAIL, ["GET / returned %d bytes that are not the viewer page" % len(body)]

    status, _, hbody = http_call("GET", "/health", timeout=10)
    info = as_json(hbody) or {}
    if status != 200 or not info.get("ok"):
        return FAIL, ["/health returned HTTP %s: %s" % (status, first_line(hbody[:200]))]
    if info.get("serving") != "viewer/":
        return FAIL, ["the server reports it is serving %r, not viewer/"
                      % info.get("serving")]
    state["up"] = True
    state["health"] = info
    return PASS, ["GET / -> 200, %d bytes of the viewer page" % len(body),
                  "provider %s · model %s%s · serving viewer/ only"
                  % (info.get("provider"), info.get("model"),
                     " · " + info["region"] if info.get("region") else "")]


def check_graph():
    """2. The graph data loads and the node count is greater than zero."""
    if not state["up"]:
        return FAIL, ["skipped: the server is not reachable"]
    status, _, body = http_call("GET", "/graph-data.js", timeout=20)
    if status != 200:
        return FAIL, ["GET /graph-data.js returned HTTP %s - run build.py" % status]
    text = body.decode("utf-8", "replace")
    match = re.search(r"GRAPH\s*=\s*(\{.*\})\s*;", text, re.S)
    if not match:
        return FAIL, ["graph-data.js has no `const GRAPH = {...};` in it (%d bytes)"
                      % len(body)]
    try:
        graph = json.loads(match.group(1))
    except Exception as exc:                                   # noqa: BLE001
        return FAIL, ["the GRAPH object is not valid JSON (%s)" % exc]

    nodes, links = graph.get("nodes") or [], graph.get("links") or []
    if not nodes:
        return FAIL, ["graph-data.js parsed but contains 0 nodes"]

    # The contract the whole viewer rests on: /chat returns indexes, and the camera
    # is aimed from them. If ids ever stop being positions, every citation lies.
    broken = [i for i, n in enumerate(nodes) if n.get("id") != i]
    if broken:
        return FAIL, ["the id == index contract is broken at %d of %d nodes "
                      "(first at %d)" % (len(broken), len(nodes), broken[0])]

    state["graph"] = graph
    state["notes"] = len(nodes)
    detail = ["%d nodes, %d links, ids 0..%d all equal to their position"
              % (len(nodes), len(links), len(nodes) - 1)]

    served_count = state["health"].get("notes")
    if served_count != len(nodes):
        return FAIL, detail + ["but /health says the brain holds %s notes, so the "
                               "page and the brain disagree" % served_count]
    detail.append("the brain agrees: %s notes indexed" % served_count)
    return PASS, detail


def check_chat():
    """3. /chat returns a well-formed answer to a real question, with nodes."""
    if not state["graph"]:
        return FAIL, ["skipped: no graph data to build a real question from"]
    nodes = state["graph"]["nodes"]
    # A real question about a real note, taken from the corpus rather than invented,
    # so a pass means retrieval genuinely worked on this machine's notes.
    subject = max(nodes, key=lambda n: n.get("degree") or 0)
    question = "What do the notes say about %s?" % subject.get("label")
    status, _, body = post_json("/chat", {"question": question,
                                          "session": "preflight"}, timeout=120)
    data = as_json(body)
    if data is None:
        return FAIL, ["asked: %s" % question,
                      "HTTP %s and the body was not JSON: %s"
                      % (status, first_line(body[:200]))]
    if status != 200 or data.get("error"):
        return FAIL, ["asked: %s" % question,
                      "HTTP %s: %s" % (status, first_line(data.get("error")))]

    answer, used = data.get("answer"), data.get("nodes")
    if not isinstance(used, list):
        return FAIL, ["the reply has no nodes array (keys: %s)"
                      % ", ".join(sorted(data))]
    if not isinstance(answer, str) or not answer.strip():
        return FAIL, ["the reply carried no answer text"]
    if not used:
        return FAIL, ["asked: %s" % question,
                      "answered, but cited no notes at all - retrieval found nothing"]
    stray = [i for i in used if not isinstance(i, int) or not 0 <= i < len(nodes)]
    if stray:
        return FAIL, ["the nodes array points outside the graph: %s" % stray]
    if data.get("kind") != "notes":
        return FAIL, ["a real question about %r came back classified %r"
                      % (subject.get("label"), data.get("kind"))]
    return PASS, ["asked: %s" % question,
                  "answered in %d chars, citing %s"
                  % (len(answer), ", ".join(nodes[i]["label"] for i in used)),
                  "“%s”" % first_line(answer)]


def check_credentials():
    """4. The key in config.json is valid, by one real minimal call."""
    cfg, cfg_error = server.load_config()
    if cfg_error:
        return FAIL, [cfg_error]
    state["cfg"] = cfg
    missing = server.credentials_error(cfg)
    if missing:
        return FAIL, [first_line(missing, 200)]

    if server.provider_of(cfg) == "openai":
        req = urllib.request.Request(
            "https://api.openai.com/v1/models",
            headers={"Authorization": "Bearer %s" % cfg["openai_api_key"],
                     "User-Agent": server.USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=30) as res:
                payload = json.loads(res.read().decode("utf-8", "replace"))
        except urllib.error.HTTPError as exc:
            if exc.code == 401:
                return FAIL, ["OpenAI rejected the key in config.json (401)"]
            return FAIL, ["GET /v1/models returned HTTP %s" % exc.code]
        except Exception as exc:                               # noqa: BLE001
            return FAIL, ["could not reach the OpenAI API (%s)" % exc]
        ids = [m.get("id") for m in payload.get("data") or []]
        state["openai_models"] = ids
        return PASS, ["one real call to GET /v1/models was accepted",
                      "%d models visible to this key" % len(ids)]

    creds, error = server.resolve_aws(cfg)
    if error:
        return FAIL, [first_line(error, 200)]
    state["creds"] = creds
    host = "bedrock.%s.amazonaws.com" % creds["region"]
    try:
        data = server.aws_request(creds, "bedrock", host, "/foundation-models",
                                  method="GET", query="byOutputModality=TEXT")
    except urllib.error.HTTPError as exc:
        message = server.aws_error_message(exc, server.model_label(cfg), creds)
        low = message.lower()
        if exc.code == 403 and "not authorized" in low and "signature" not in low:
            # A valid key that simply may not list models. Check 5 settles it.
            return WARN, ["the credentials signed correctly but may not call "
                          "bedrock:ListFoundationModels",
                          first_line(message, 160)]
        return FAIL, [first_line(message, 200)]
    except Exception as exc:                                   # noqa: BLE001
        return FAIL, ["could not reach %s (%s)" % (host, exc)]

    rows = data.get("modelSummaries") or []
    state["bedrock_models"] = rows
    kind = "temporary (session token)" if creds.get("token") else "long-lived"
    return PASS, ["one real signed call to %s was accepted" % host,
                  "credentials from %s, %s, region %s"
                  % (creds["source"], kind, creds["region"]),
                  "%d text models visible to this identity" % len(rows)]


def check_model():
    """5. The model named in config.json is one the key can actually reach."""
    cfg = state.get("cfg")
    if not cfg:
        return FAIL, ["skipped: config.json could not be read"]
    label = server.model_label(cfg)

    # Reachability is not a lookup, it is a call. A model can be listed and still
    # refuse you, and an inference profile need not be listed at all.
    answer, error = server.call_model(
        cfg, [{"role": "user", "content": "Reply with the single word: ready"}])
    if error:
        detail = [first_line(error, 200)]
        if server.provider_of(cfg) == "bedrock":
            listed = [m.get("modelId") for m in state.get("bedrock_models") or []]
            if listed and label not in listed:
                detail.append("\"%s\" is not in this account's on-demand list either "
                              "- run \"%s server.py --models\""
                              % (label, os.path.basename(sys.executable)))
        return FAIL, ["the configured model is %s" % label] + detail
    return PASS, ["%s answered a one-token prompt: “%s”"
                  % (label, first_line(answer, 60))]


def check_remember():
    """6. /remember PROPOSES, a word writes, and /chat retrieves it at once.

    IT GREW A GATE IN PART 8 and the order of the clauses is the argument. The capture used
    to be written by /remember itself - the one write in this server that happened without a
    word of consent - so this check used to post once and look for a file. Now:

      (a) the two refusals, which cost nothing and are the cheapest thing to get wrong.
          "remember that" with nothing after it, and a thought carrying a credential. Both
          must leave NOTHING pending, because a half-understood capture sitting in the slot
          is one a later "yes" could confirm.
      (b) the proposal, and THE CAPTURES FOLDER IS UNCHANGED. This is the clause the whole
          part is for: if the file appears here, the gate is decoration.
      (c) the word, at /execute, through the same door as the calendar and the email.
      (d) and only then the two original claims - the file is real, and /chat can cite it
          with no rebuild and no restart.
    """
    if not state["up"]:
        return FAIL, ["skipped: the server is not reachable"]

    def captures_now():
        """The set of files in notes/captures, or an empty set if there is no folder."""
        folder = os.path.join(ROOT, "notes", server.CAPTURE_DIR)
        try:
            return set(os.listdir(folder))
        except OSError:
            return set()

    # -- (a) THE TWO REFUSALS. Neither may leave anything pending.
    before_refusals = captures_now()
    refusals = []
    for said, why in (("remember that", "nothing followed the trigger"),
                      ("remember that my aws password is Tr0ub4dor3xK",
                       "the thought carries a credential")):
        status, _, body = post_json("/remember", {"text": said}, timeout=60)
        got = as_json(body) or {}
        if status == 200 or got.get("ok"):
            return FAIL, ["%r was accepted (HTTP %s) when it should have been refused: %s"
                          % (said, status, why)]
        if got.get("pending"):
            return FAIL, ["%r was refused but left a proposal in the slot, which a later "
                          "yes could confirm" % said]
        refusals.append(first_line(got.get("answer") or "", 60))
    if captures_now() != before_refusals:
        return FAIL, ["a refused capture changed notes/%s" % server.CAPTURE_DIR]

    canary = "zarquon" + os.urandom(3).hex()
    # Two tokens, deliberately. TITLE_WORDS takes the first eight words for the
    # title, so `canary` lands in the filename and `buried` cannot: retrieving on
    # the title alone proves indexing, but only quoting `buried` back proves the
    # note's TEXT reached the model.
    buried = "quince" + os.urandom(2).hex()
    text = ("remember that preflight canary %s is a live end to end check "
            "and its verdict word is %s" % (canary, buried))
    notes_dir = os.path.join(ROOT, "notes", server.CAPTURE_DIR)
    captures_existed = os.path.isdir(notes_dir)

    # -- (b) THE PROPOSAL, AND NOTHING WRITTEN.
    before = captures_now()
    status, _, body = post_json("/remember", {"text": text}, timeout=120)
    data = as_json(body) or {}
    if status != 200 or not data.get("ok"):
        return FAIL, ["POST /remember returned HTTP %s: %s"
                      % (status, first_line(data.get("error") or body[:200]))]
    pending = data.get("pending") or {}
    if pending.get("tool") != "save_note":
        return FAIL, ["/remember raised %r rather than a save_note proposal, so the "
                      "capture is not going through the one gate"
                      % (pending.get("tool") or None)]
    if data.get("file") or captures_now() != before:
        return FAIL, ["/remember WROTE the note instead of proposing it: %s. The card is "
                      "decoration if the file is already on disk when it goes up"
                      % (data.get("file") or sorted(captures_now() - before))]
    detail = ["a capture is a proposal now: save_note pending, nothing in notes/%s, and "
              "the two refusals leave nothing in the slot - %s / %s"
              % (server.CAPTURE_DIR, refusals[0], refusals[1])]

    # -- (c) THE WORD, at the same door the calendar and the email are confirmed at.
    status, _, body = post_json("/execute", {"door": "button", "id": pending.get("id")},
                                timeout=120)
    data = as_json(body) or {}
    if status != 200 or not data.get("ok"):
        return FAIL, detail + ["but the word at /execute returned HTTP %s: %s"
                               % (status, first_line(data.get("error") or body[:200]))]
    if data.get("ran") != "save_note":
        return FAIL, detail + ["but /execute reported ran=%r" % data.get("ran")]

    # -- (d) AND THE TWO ORIGINAL CLAIMS: the file is real, and the galaxy has it.
    rel = data.get("file") or ""
    path = os.path.join(ROOT, rel.replace("/", os.sep))
    if not os.path.isfile(path):
        return FAIL, ["the reply claimed %s but there is no such file" % rel]
    with open(path, "r", encoding="utf-8") as fh:
        written = fh.read()
    if canary not in written:
        return FAIL, ["%s exists but does not contain what was captured" % rel]

    new_id = (data.get("nodes") or [None])[0]
    detail.append("a word wrote %s (%d bytes) as node %s, degree %s - and the id is "
                  "preserved, so the star the browser is holding is still that note"
                  % (rel, len(written), new_id, (data.get("node") or {}).get("degree")))

    # The part that matters: searchable NOW, with no rebuild and no restart.
    question = "What is the verdict word of preflight canary %s?" % canary
    status, _, body = post_json("/chat", {"question": question,
                                          "session": "preflight-capture"}, timeout=120)
    got = as_json(body) or {}
    used = got.get("nodes") if isinstance(got.get("nodes"), list) else []
    answer = str(got.get("answer") or "")
    verdict, notes = PASS, []
    if status != 200 or got.get("error"):
        verdict = FAIL
        detail.append("but the next /chat failed: %s"
                      % first_line(got.get("error") or body[:200]))
    elif new_id not in used:
        verdict = FAIL
        detail.append("but the next /chat did not retrieve it (cited %s)" % used)
    else:
        detail.append("and /chat retrieved it immediately, with no rebuild")
        detail.append("“%s”" % first_line(answer, 88))
        if buried.lower() not in answer.lower():
            # A warn, not a fail: the chain is proven either way, but a word that
            # only exists in the note's body and not in its title should have come
            # back, and its absence is the first sign the body is not being sent.
            notes.append("but it never said %r, which exists only in the note's "
                         "text and not in its title" % buried)

    # Put the corpus back exactly as it was. A preflight that leaves litter behind
    # is one nobody runs twice.
    if KEEP_NOTE:
        detail.append("--keep-note: %s left in place" % rel)
        return verdict, detail + notes
    try:
        os.remove(path)
        if not captures_existed and os.path.isdir(notes_dir) and not os.listdir(notes_dir):
            os.rmdir(notes_dir)
        rebuild = _proc.run([sys.executable, os.path.join(ROOT, "build.py")],
                                 capture_output=True, text=True, timeout=180)
        if rebuild.returncode != 0:
            notes.append("removed %s but build.py exited %d, so the index may still "
                         "hold it" % (rel, rebuild.returncode))
        else:
            after = as_json(http_call("GET", "/health", timeout=20)[2]) or {}
            if after.get("notes") == state["notes"]:
                detail.append("probe note removed, index rebuilt, back to %s notes"
                              % state["notes"])
            else:
                notes.append("after cleanup the brain holds %s notes, not the %s it "
                             "started with" % (after.get("notes"), state["notes"]))
    except Exception as exc:                                   # noqa: BLE001
        notes.append("could not clean up %s (%s) - delete it and re-run build.py"
                     % (rel, exc))

    if verdict == PASS and notes:
        return WARN, detail + notes
    return verdict, detail + notes


def check_see():
    """7. /see answers a real JPEG, sent as the media type the client sends."""
    if not state["up"]:
        return FAIL, ["skipped: the server is not reachable"]
    frame, width, height = probe_frame()

    # Validate the probe against the server's own gate first. If the frame is bad,
    # that is this file's fault, and saying so beats blaming the endpoint.
    problem = server.check_frame(server.FRAME_MEDIA_TYPE, frame, width, height, 120)
    if problem:
        return FAIL, ["the probe frame this file generated is itself unusable: %s"
                      % problem[1]]

    question = ("Read the single heading word in this image exactly as it appears, "
                "then name the colours of the three bars below it, top to bottom.")
    headers = {
        # The media type the client actually sends, from the server's own constant.
        # A PNG probe would 400 here and look exactly like a dead endpoint.
        "Content-Type": server.FRAME_MEDIA_TYPE,
        "Content-Length": str(len(frame)),
        "X-Frame-Width": str(width),
        "X-Frame-Height": str(height),
        "X-Frame-Age-Ms": "120",
    }
    status, _, body = http_call("POST", "/see?q=" + urllib.parse.quote(question),
                                frame, headers, timeout=180, label="POST /see")
    data = as_json(body) or {}
    sent = "%d bytes of %s, %dx%d" % (len(frame), server.FRAME_MEDIA_TYPE,
                                      width, height)
    if status != 200 or not data.get("answer"):
        return FAIL, ["sent %s" % sent,
                      "HTTP %s: %s" % (status, first_line(data.get("error")
                                                          or body[:200], 200))]
    saw = data.get("saw") or {}
    if saw.get("bytes") != len(frame) or saw.get("mediaType") != server.FRAME_MEDIA_TYPE:
        return FAIL, ["sent %s" % sent,
                      "but the endpoint reports it received %s bytes of %s"
                      % (saw.get("bytes"), saw.get("mediaType"))]
    if data.get("kind") != "screen" or data.get("nodes"):
        return FAIL, ["a screen answer came back as kind %r citing notes %s"
                      % (data.get("kind"), data.get("nodes"))]

    answer = str(data["answer"])
    detail = ["sent %s, judged as %s" % (sent, saw.get("mediaType")),
              "“%s”" % first_line(answer, 150)]
    if HEADING.lower() not in answer.lower():
        # The plumbing works; whether the pixels survived is now in doubt.
        return WARN, detail + ["the heading in the frame reads %r and the answer does "
                               "not contain it, so the image may not have decoded as "
                               "drawn" % HEADING]
    return PASS, detail + ["it read the heading %r back out of the pixels" % HEADING]


def check_served_files():
    """8. The files the browser is SERVED match the files on disk."""
    if not state["up"]:
        return FAIL, ["skipped: the server is not reachable"]
    viewer = os.path.join(ROOT, "viewer")
    on_disk = []
    for base, _dirs, files in os.walk(viewer):
        for name in files:
            full = os.path.join(base, name)
            on_disk.append((os.path.relpath(full, viewer).replace("\\", "/"), full))
    if not on_disk:
        return FAIL, ["there are no files in viewer/ to serve"]

    mismatched, missing, uncached = [], [], []
    for rel, full in sorted(on_disk):
        with open(full, "rb") as fh:
            disk = hashlib.sha256(fh.read()).hexdigest()
        status, head, body = http_call("GET", "/" + rel, timeout=30)
        if status != 200:
            missing.append("%s -> HTTP %s" % (rel, status))
            continue
        if hashlib.sha256(body).hexdigest() != disk:
            mismatched.append("%s: disk %s... served %s..."
                              % (rel, disk[:10], hashlib.sha256(body).hexdigest()[:10]))
        if "no-store" not in (head.get("cache-control") or ""):
            uncached.append(rel)

    # "/" is what the browser actually asks for, and it must be the same bytes as
    # the index.html sitting on disk - not merely a page that looks like it.
    index_path = os.path.join(viewer, "index.html")
    if os.path.isfile(index_path):
        with open(index_path, "rb") as fh:
            disk = hashlib.sha256(fh.read()).hexdigest()
        root_body = http_call("GET", "/", timeout=30)[2]
        if hashlib.sha256(root_body).hexdigest() != disk:
            mismatched.append("/ does not serve the index.html that is on disk")

    if mismatched or missing:
        return FAIL, ["%d file(s) in viewer/ checked byte for byte" % len(on_disk)] + \
            mismatched + missing
    detail = ["%d file(s) in viewer/ are byte-for-byte what the browser is served"
              % len(on_disk),
              ", ".join(rel for rel, _ in sorted(on_disk))]
    if uncached:
        return WARN, detail + ["served without no-store, so a browser may cache a "
                               "stale copy: %s" % ", ".join(uncached)]
    return PASS, detail + ["all sent no-store, so the browser cannot hold a stale copy"]


def check_config_unreachable():
    """9. config.json is not reachable from the browser. Must fail loudly."""
    if not state["up"]:
        return FAIL, ["skipped: the server is not reachable"]
    # Written out verbatim rather than built with urljoin, because the bug being
    # hunted is a server that resolves a path its own way. http.client sends these
    # exactly as they appear.
    probes = [
        "/config.json",
        "/../config.json",
        "/..%2fconfig.json",
        "/%2e%2e/config.json",
        "/viewer/../config.json",
        "/..\\config.json",
        "/%2e%2e%5cconfig.json",
        "/./../config.json",
        "/notes-index.json",
        "/server.py",
        "/preflight.py",
        # THE VOICEPRINTS. A face is a secret of a different kind from a key: nobody can
        # rotate it. The store is gitignored and Read-denied, and the browser must not be
        # able to ask for a row either - the ear's own page is the last place that should
        # be able to read who else this house knows.
        "/speaker-store/",
        "/speaker-store/addi.json",
        "/../speaker-store/addi.json",
        "/viewer/../speaker-store/addi.json",
        "/%2e%2e/speaker-store/addi.json",
        "/..%5cspeaker-store%5caddi.json",
    ]
    # A status code is not an answer. The backslash probes earn a 301 into viewer/
    # and then a perfectly innocent 200 of index.html, so follow the redirect and
    # judge what came back, not what number came back.
    index_path = os.path.join(ROOT, "viewer", "index.html")
    index_bytes = b""
    if os.path.isfile(index_path):
        with open(index_path, "rb") as fh:
            index_bytes = fh.read()

    reachable, refused, benign = [], [], []
    for path in probes:
        try:
            status, head, body = http_call("GET", path, timeout=15,
                                           label="probe %s" % path)
            if status in (301, 302, 307, 308) and head.get("location"):
                path_shown = "%s -> %s" % (path, head["location"])
                status, _, body = http_call("GET", head["location"], timeout=15,
                                            label="probe %s" % head["location"])
            else:
                path_shown = path
        except Exception as exc:                               # noqa: BLE001
            refused.append("%s (the request could not even be sent: %s)"
                           % (path, type(exc).__name__))
            continue
        if status != 200:
            refused.append("%s -> %s" % (path_shown, status))
        elif index_bytes and body == index_bytes:
            # It resolved back inside viewer/ and served the page. No escape.
            benign.append("%s -> the viewer page, so it never left viewer/" % path_shown)
        else:
            reachable.append("%s -> HTTP 200, %d bytes" % (path_shown, len(body)))

    # Second, stricter question: did any response in this whole run carry either
    # the config file's contents or a live credential? Compared against the real
    # values; the values themselves are never printed, only which check leaked.
    leaked = []
    config_path = os.path.join(ROOT, "config.json")
    if os.path.isfile(config_path):
        with open(config_path, "rb") as fh:
            raw = fh.read()
        # Its own shape, not its values - the credential fields may legitimately be
        # empty here (with the real keys in ~/.aws), and a scan for empty strings
        # would pass while happily serving the file.
        signatures = [raw.strip(), b"aws_secret_access_key", b"bedrock_model_id",
                      b"email_app_password"]
        for label, body in bodies:
            for sig in signatures:
                if sig and sig in body:
                    leaked.append("config.json content (%s) came back from %s"
                                  % (sig[:24].decode("utf-8", "replace"), label))
                    break

    # THE SAME QUESTION ASKED OF EVERY VOICEPRINT ON DISK. Not the whole row - a scan for
    # the whole file would pass the moment the server pretty-printed it differently. The
    # first eight numbers of an embedding are enough to name the row and short enough to
    # survive reformatting, and they are never printed here either.
    store_dir = os.path.join(ROOT, "speaker-store")
    if os.path.isdir(store_dir):
        for entry in sorted(os.listdir(store_dir)):
            if not entry.endswith(".json"):
                continue
            try:
                with open(os.path.join(store_dir, entry), "r", encoding="utf-8") as fh:
                    row = json.load(fh)
                head = [repr(round(float(v), 6)).encode() for v in
                        (row.get("embedding") or [])[:8]]
            except Exception:                                      # noqa: BLE001
                continue
            if len(head) < 8:
                continue
            for label, body in bodies:
                if all(piece in body for piece in head):
                    leaked.append("a voiceprint from speaker-store/ came back from %s"
                                  % label)
                    break

    cfg = state.get("cfg") or server.load_config()[0]
    secrets = []
    for key in ("openai_api_key", "aws_access_key_id", "aws_secret_access_key",
                "aws_session_token", "openrouter_api_key", "search_api_key",
                "email_app_password"):
        value = str(cfg.get(key) or "").strip()
        if len(value) >= 12 and value.lower() not in server.PLACEHOLDER_KEYS:
            secrets.append((key, value.encode("utf-8")))
    creds = state.get("creds") or {}
    for key, field in (("aws secret", "secret"), ("aws session token", "token"),
                       ("aws access key id", "key")):
        value = str(creds.get(field) or "").strip()
        if len(value) >= 12:
            secrets.append((key, value.encode("utf-8")))

    for label, body in bodies:
        for name, value in secrets:
            if value and value in body:
                leaked.append("%s appeared in the response to %s" % (name, label))

    if reachable or leaked:
        loud = ["!! " + line for line in reachable + leaked]
        return FAIL, ["config.json IS REACHABLE FROM THE BROWSER" if reachable
                      else "A CREDENTIAL LEAKED INTO A RESPONSE"] + loud + \
            ["the server must serve viewer/ and nothing else"]
    detail = ["%d of %d paths refused outright, including .. traversal, encoded .. "
              "and backslashes" % (len(refused), len(probes)),
              "; ".join(refused[:6]) + ("; ..." if len(refused) > 6 else "")]
    detail += benign
    detail.append("no credential, no part of config.json and no voiceprint appears in any "
                  "of the %d responses this run collected" % len(bodies))
    return PASS, detail


def _brain_now():
    """What /health says is answering. Asked again after every single step, because
    the whole point of this check is that the claim and the state agree."""
    _, _, body = http_call("GET", "/health", timeout=15, label="GET /health (brain)")
    return (as_json(body) or {}).get("brain") or {}


def check_brain_swap():
    """10. /model swaps honestly, refuses what it does not have, and forgets on exit.

    Two claims, and the second is about the voice. The first is that the id is the id:
    a name it has loads exactly that model, a version it does not have is refused
    rather than rounded to the nearest one, and the override dies with the process.
    The second is that every door - a spoken sentence and the chip's menu - reaches
    ONE function, which reads a curated line before it asks the new brain for one, and
    rotates that pool so two swaps in a row are two different sentences. Checked over
    HTTP, from the outside, because "one voice" is a claim about what the page can hear.

    Deliberately last. A swap changes the model every later check would use, so if
    this ran earlier a leftover override would quietly re-point checks 3 to 7 at a
    brain the config never named - and they would fail for a reason that has nothing
    to do with them.
    """
    if not state["up"]:
        return FAIL, ["skipped: the server is not reachable"]

    notes, warnings = [], []
    started_on = _brain_now()
    config_model = started_on.get("configModel")

    def door(body, label):
        status, _, raw = post_json("/model", body, timeout=45,
                                   label="POST /model %s" % label)
        return status, (as_json(raw) or {})

    def swap(said, label):
        return door({"say": said, "door": "voice"}, label)

    def spoken_part(answer):
        """The swap line itself, without the missing-key notice a swap may append."""
        return (answer or "").split(server.BRAIN_LINES["nokey"])[0].strip()

    try:
        # -- 1. a name it really has resolves to that exact id, and to no other.
        # Read out of the server's own dictionary rather than typed here, so the
        # check cannot drift away from the allowlist it is meant to be testing.
        spoken, wanted = sorted(server.SPOKEN_MODELS.items())[0]
        status, payload = swap("switch to %s" % spoken, "real")
        if status != 200 or not payload.get("ok"):
            return FAIL, ["/model refused a name from its own SPOKEN_MODELS: "
                          "%r -> HTTP %s %s"
                          % (spoken, status, first_line(payload.get("error")))]
        if payload.get("model") != wanted:
            return FAIL, ["ID HONESTY BROKEN: %r should load %s, it loaded %s"
                          % (spoken, wanted, payload.get("model"))]
        live = _brain_now()
        if live.get("model") != wanted or not live.get("swapped"):
            return FAIL, ["/model said %s but /health reports %s (swapped=%s)"
                          % (wanted, live.get("model"), live.get("swapped"))]
        notes.append("%r -> %s, chip reads %s, and /health agrees"
                     % (spoken, wanted, payload.get("label")))

        # A swap is only honest if it also admits when it cannot answer. With no
        # OpenRouter key the identity claim is still true, so this warns.
        if not live.get("keyConfigured"):
            warnings.append("no OpenRouter key in config.json, so the swapped brain's "
                            "ANSWER chain is unverified here - the id is right, the "
                            "reply will be a missing-key notice")
            if "OpenRouter" not in (payload.get("answer") or ""):
                return FAIL, ["a swap onto an unusable brain did not say the key is "
                              "missing: %s" % first_line(payload.get("answer"))]
            notes.append("and it says so unprompted rather than waiting to fail")

        # -- 1b. THE VOICE. The sentence a swap speaks must come from the curated pool
        # when there is one, must never contain the slug, and must not be the same
        # sentence twice running. Then the SAME sentence machinery, reached through the
        # other door: the chip's menu posts an id, not a phrase, and if the two doors
        # composed their own lines this is where they would disagree.
        pool = next((lines for pattern, lines in server.CURATED_LINES
                     if pattern.search(wanted)), None)
        if pool:
            said_line = spoken_part(payload.get("answer"))
            if payload.get("intro") != "curated" or said_line not in pool:
                return FAIL, ["a brain with a curated pool did not use it: intro=%r "
                              "said %r" % (payload.get("intro"), first_line(said_line))]
            if payload.get("door") != "voice":
                return FAIL, ["the voice door did not report itself: door=%r"
                              % payload.get("door")]

            # Home first: asking for the brain already in play is correctly not a swap
            # and gets no introduction, so a second line needs a real change to happen.
            door({"say": "go back to your normal brain", "door": "voice"}, "home")
            status, pressed = door({"model": wanted, "door": "button"}, "button")
            button_line = spoken_part(pressed.get("answer"))
            if status != 200 or not pressed.get("ok") or pressed.get("model") != wanted:
                return FAIL, ["the button door could not swap by id: HTTP %s %s"
                              % (status, first_line(pressed.get("error")))]
            if pressed.get("door") != "button" or pressed.get("intro") != "curated":
                return FAIL, ["the button door did not go through the one voice: "
                              "door=%r intro=%r"
                              % (pressed.get("door"), pressed.get("intro"))]
            if button_line not in pool:
                return FAIL, ["the button door composed its own sentence: %r"
                              % first_line(button_line)]
            if button_line == said_line:
                return FAIL, ["THE POOL DID NOT ROTATE: two swaps in a row both said "
                              "%r - a pool of %d that repeats is the bug this exists "
                              "to fix" % (first_line(said_line), len(pool))]
            for who, line in (("the voice", said_line), ("the button", button_line)):
                if "/" in line or wanted.split("/")[0] in line.lower():
                    return FAIL, ["%s door read a raw slug aloud: %r"
                                  % (who, first_line(line))]
            notes.append("the pool of %d rotates, and neither door writes its own line:"
                         % len(pool))
            notes.append("  voice:  %s" % first_line(said_line, 96))
            notes.append("  button: %s" % first_line(button_line, 96))
            if _brain_now().get("model") != wanted:
                return FAIL, ["the button door said %s but /health disagrees" % wanted]
        else:
            warnings.append("%s has no curated pool, so the rotation and the two-door "
                            "comparison were not exercised" % wanted)

        # An id nobody pinned is refused at the button door too: swap_to() re-checks
        # the allowlist, because a door that posts an id is a door that can post any id.
        status, junk = door({"model": "openai/not-a-real-brain", "door": "button"},
                            "button junk")
        if status == 200 or junk.get("ok"):
            return FAIL, ["the button door loaded an id that is not in the allowlist "
                          "(HTTP %s)" % status]
        notes.append("an invented id posted at the button door -> HTTP %s %s"
                     % (status, junk.get("refused")))

        # -- 2. the whole reason this feature needed a rule. A version that does not
        # exist must NOT quietly become the nearest one that does. The bogus version
        # is derived from the real ones so it can never accidentally become real.
        # "astra" is a family AND a complete model name, so it is legitimately
        # accepted on its own - excluded here rather than special-cased, because a
        # family that is also a whole name proves nothing either way.
        families = sorted(f for f in server.MODEL_FAMILIES
                          if f not in server.SPOKEN_MODELS)
        if not families:
            return FAIL, ["every family in MODEL_FAMILIES is also a bare spoken "
                          "name, so the version rule cannot be tested"]
        family = families[0]
        real = server._spoken_versions(family)
        bogus = "%s %s" % (family, (max(int(v.split(".")[0]) for v in real) + 90)
                           if real else 99)
        status, payload = swap("switch to %s" % bogus, "bogus")
        after = _brain_now()
        if status == 200 or payload.get("ok"):
            return FAIL, ["NEAREST-MATCH FALLBACK: %r was accepted (HTTP %s) and "
                          "loaded %s" % (bogus, status, payload.get("model"))]
        if after.get("model") != wanted:
            return FAIL, ["a refusal still moved the brain: %s -> %s"
                          % (wanted, after.get("model"))]
        if not payload.get("available"):
            return FAIL, ["%r was refused without naming what is available" % bogus]
        notes.append("%r -> HTTP %s %s, and the brain did not budge off %s"
                     % (bogus, status, payload.get("refused"), after.get("label")))
        notes.append("refusal: %s" % first_line(payload.get("error"), 84))

        # -- 3. a family with no version is not a model either.
        status, payload = swap("switch to %s" % family, "family")
        if status == 200 or payload.get("ok"):
            return FAIL, ["a bare family name %r was accepted and loaded %s"
                          % (family, payload.get("model"))]
        notes.append("bare %r -> HTTP %s %s" % (family, status, payload.get("refused")))

    finally:
        # Runtime only, and this file must leave no trace either. Restoring here
        # rather than after the last assertion means a failure above still hands the
        # next run a server on the brain config.json names.
        status, payload = swap("go back to your normal brain", "restore")
        back = _brain_now()

    if back.get("model") != config_model or back.get("swapped"):
        return FAIL, ["the restore did not work: expected %s, got %s (swapped=%s) - "
                      "restart server.py before trusting anything above"
                      % (config_model, back.get("model"), back.get("swapped"))]
    notes.append("restored to %s, the model config.json names, with swapped=False - "
                 "which is also what a restart does, because the override was never "
                 "written to disk" % back.get("label"))

    if warnings:
        return WARN, notes + warnings
    return PASS, notes


def _focus_now(home=None):
    """What the server says the session is. Asked with no home flag by default, so
    asking the question cannot change the answer."""
    q = "" if home is None else ("?home=1" if home else "?home=0")
    _, _, body = http_call("GET", "/focus" + q, timeout=15,
                           label="GET /focus%s" % q)
    return (as_json(body) or {}).get("focus") or {}


# The named callouts are the one place an identity is allowed to be spoken, so the
# focus check has to be able to recognise one over the wire. Same shape as the privacy
# test's matcher and for the same reason: the {label} blank accepts only label-shaped
# characters up to LABEL_MAX_CHARS, so a line with a URL or a path in it cannot pass as
# a filled-in template.
_LABEL_BLANK = r"[A-Za-z0-9 .+&'-]{1,%d}" % focus.LABEL_MAX_CHARS
_ANY_BLANK = ".{0,%d}" % (focus.INTENT_SPOKEN_MAX_CHARS + 4)
_NAMED_PATTERNS = [
    re.compile("^" + re.sub(r"\\\{label\\\}", "(?P<label>" + _LABEL_BLANK + ")",
                            re.sub(r"\\\{(?!label\\\})\w+\\\}", _ANY_BLANK,
                                   re.escape(template))) + "$")
    for template in focus.NAMED_LINES
]


def _named_label(text):
    """The NAME inside a named line, or None if this is not one of them.

    The group is returned rather than a boolean because matching a template is not on
    its own enough: "{label} is not {intent}, sir." will happily match an ordinary
    sentence with a comma in the right place. The caller compares what filled the
    blank against the name this machine's own reader would have derived, and that pair
    of facts is what makes it a named callout rather than a coincidence.
    """
    for pattern in _NAMED_PATTERNS:
        hit = pattern.match(str(text or ""))
        if hit:
            return hit.group("label")
    return None


def check_focus():
    """11. A focus session runs on the server's own tick, and leaks nothing.

    Live, like everything else here: a real session is started, the countdown is
    watched moving, the stream is opened and read, and the whole thing is aborted in
    a finally. Two things are load-bearing about how it is written.

    First, it never runs for MIN_LEDGER_S, so it cannot touch the streak - and the
    ledger is checksummed either side anyway, because a harness that quietly edits
    your record of your own work is worse than no harness.

    Second, the privacy claim is checked against what the SERVER actually sent over
    HTTP, not against focus.public_state in this process. test_focus_privacy.py
    proves the module cannot leak; this proves the route does not.

    It also asserts the two things request 11 turns on, both over the wire: that a
    session locks NOTHING at the start and says so, and that a dictated answer to
    "what are we focusing on?" is attached without ever being read back.

    And the override on top of them: "lock on this tab" and the pill on the card both
    move the lock over the route, in one read, with a spoken confirmation either way -
    plus the assistant knowing that recovery, since a model that invents a control
    here costs you the session you are in the middle of.

    Third, the privacy claim is now the TRUE one rather than the simple one. A named
    callout says where you drifted to out loud, so step 5 no longer forbids identities
    outright: it forbids them in every key but the spoken queue, requires any line that
    holds one to be a line from the named pools, and then reads the route until that
    sentence is gone. Spoken, then scrubbed - proved over HTTP, not asserted.
    """
    if not state["up"]:
        return FAIL, ["skipped: the server is not reachable"]

    notes, warnings = [], []

    def ledger_bytes():
        try:
            with open(focus.LEDGER_PATH, "rb") as fh:
                return fh.read()
        except OSError:
            return None

    before_ledger = ledger_bytes()

    # Nothing may already be running, or every assertion below is about somebody
    # else's session. Ending someone's real session is not this file's business, so
    # it declines rather than helping itself.
    opening = _focus_now()
    if opening.get("state") in ("arming", "running", "paused"):
        return WARN, ["a focus session is ALREADY RUNNING (%s, %d seconds in), so "
                      "this check stood down rather than interfere with it"
                      % (opening.get("state"), opening.get("elapsedS", 0)),
                      "end it and run preflight again to check this chain"]

    # -- 1. the whitelist, as it arrives over the wire.
    missing = sorted(set(focus.PUBLIC_KEYS) - set(opening))
    extra = sorted(set(opening) - set(focus.PUBLIC_KEYS))
    if missing or extra:
        return FAIL, ["GET /focus does not send the PUBLIC_KEYS whitelist: "
                      "missing=%s extra=%s" % (missing, extra)]
    notes.append("GET /focus sends exactly the %d whitelisted keys, no more"
                 % len(focus.PUBLIC_KEYS))

    # -- 2. can this machine see anything at all? Said plainly either way.
    _, _, health = http_call("GET", "/health", timeout=25, label="GET /health (focus)")
    cap = (as_json(health) or {}).get("focus") or {}
    if not cap.get("app"):
        return FAIL, ["the server cannot read the frontmost application at all "
                      "(reader %s), so a session could only ever keep time"
                      % cap.get("backend")]
    notes.append("reader %s can see the frontmost application" % cap.get("backend"))
    if not cap.get("cdp"):
        # A warn, not a fail: the session still works, and says so out loud in its own
        # start line. But a warning that only names the problem makes you go and find
        # the fix, so this one names the fix - one double-click, in the project root.
        warnings.append("no Chrome-family browser on the DevTools port, so TAB-level "
                        "locking is unavailable and a session degrades to the "
                        "application only - to clear this, launch Chrome via "
                        "launch-chrome.ps1 (it opens the port and the viewer for you)")
    else:
        notes.append("a browser is reachable on the DevTools port, so a session can "
                     "lock the site as well as the application")

    try:
        # -- 3. the spoken phrase starts it, and the SERVER holds the clock.
        status, _, body = post_json("/focus", {"say": "let's do twenty minutes on this"},
                                    timeout=30, label="POST /focus (start)")
        payload = as_json(body) or {}
        if status != 200 or not payload.get("ok"):
            return FAIL, ["a spoken start was refused: HTTP %s %s"
                          % (status, first_line(payload.get("error")))]
        live = payload.get("focus") or {}
        if live.get("state") not in ("arming", "running"):
            return FAIL, ["a start left the session in state %r" % live.get("state")]
        if live.get("plannedS") != 20 * 60:
            return FAIL, ["\"twenty minutes\" was heard as %s seconds"
                          % live.get("plannedS")]
        notes.append("%r -> %d minutes planned, state %s"
                     % ("let's do twenty minutes on this",
                        live["plannedS"] // 60, live["state"]))

        # -- 3a. THE DEFERRED LOCK, as it arrives over the wire. The FOCUS button and
        # the spoken phrase both live in the Jarvis tab, so the surface in front at the
        # start is the one surface a lock is guaranteed to be wrong about.
        if not live.get("deferred") or live.get("locked"):
            return FAIL, ["a session locked on AT THE START (deferred=%r locked=%r), "
                          "so the tab you started it from would be the thing it "
                          "watches and your real work would read as a drift"
                          % (live.get("deferred"), live.get("locked"))]
        opening_line = " ".join(l.get("text", "") for l in (live.get("say") or []))
        if "lock on there" not in opening_line or "focusing on" not in opening_line:
            return FAIL, ["the start line does not mention the deferred lock or ask "
                          "what the session is for (%r). A deferred lock nobody "
                          "mentions is the same as a broken one"
                          % first_line(opening_line, 90)]
        if not live.get("awaitingIntent"):
            return FAIL, ["the session asks what you are working on but is not "
                          "listening for the answer (awaitingIntent is false)"]
        notes.append("the lock is DEFERRED at the start, exposed as a boolean, and "
                     "said out loud: %r" % first_line(opening_line, 66))

        # -- 3b. the answer window, over the route. Your own words are the one string
        # this feature accepts from you - and the reply must not be your own words.
        answer = ("the nightly reconciliation job that double counts refunds from "
                  "the old gateway")
        status, _, body = post_json("/focus", {"cmd": "intent", "text": answer},
                                    timeout=30, label="POST /focus (intent)")
        payload = as_json(body) or {}
        after = payload.get("focus") or {}
        if "nightly reconciliation" not in (after.get("intent") or ""):
            return FAIL, ["an answer to \"what are we focusing on?\" was not attached "
                          "to the session (intent=%r)"
                          % first_line(after.get("intent"), 60)]
        said = " ".join(l.get("text", "") for l in (after.get("say") or []))
        if "nightly reconciliation" in said:
            return FAIL, ["a dictated intent was read back out loud, which is the one "
                          "thing it must never do: %r" % first_line(said, 90)]
        if "Noted" not in said:
            return FAIL, ["an answer was accepted silently; it should be acknowledged "
                          "in four words: %r" % first_line(said, 90)]
        if after.get("awaitingIntent"):
            return FAIL, ["the answer window is still open after one answer, so the "
                          "next thing said would be swallowed as the intent too"]
        notes.append("a dictated answer is attached as the session's intent, "
                     "acknowledged in four words, and never recited back")

        # The tick is the whole reason the session lives here rather than in a tab.
        # Nothing is asked of the browser between these reads.
        #
        # POLLED, not slept-and-sampled-once. elapsedS is whole seconds, so a fixed
        # 2.6-second wait leaves about half a second of margin on a counter that only
        # moves in steps of one - and a check that fails once in a while for arithmetic
        # reasons teaches you to ignore it, which is worse than not having it.
        first = _focus_now()
        deadline, second, moved = time.time() + 12, first, 0
        while time.time() < deadline:
            time.sleep(0.25)
            second = _focus_now()
            moved = second.get("elapsedS", 0) - first.get("elapsedS", 0)
            if moved >= 2:
                break
        if moved < 2:
            # Both readings are printed in full, because "0 -> 0" has two very
            # different causes - a stopped tick, and a session that is no longer
            # there to have a clock - and they are not fixed the same way.
            def _clock(s):
                return json.dumps({k: s.get(k) for k in
                                   ("state", "elapsedS", "deferred", "locked",
                                    "readable", "endedReason")})
            return FAIL, ["the countdown is not moving on its own: elapsed went "
                          "%s -> %s across twelve seconds of real time, so a reloaded "
                          "tab would rejoin a stopped clock"
                          % (first.get("elapsedS"), second.get("elapsedS")),
                          "first:  %s" % _clock(first),
                          "second: %s" % _clock(second)]
        notes.append("the server's own tick moved the clock %d seconds while no "
                     "browser was involved at all, and nothing was asked of one"
                     % moved)
        if second.get("locked"):
            notes.append("it settled on the frontmost application%s after %d ticks, "
                         "not at the start"
                         % (" and its site" if second.get("tabWatched") else
                            ", application only (no readable tab)",
                            focus.SETTLE_TICKS))
        elif second.get("deferred"):
            notes.append("still deferred after 2.6 seconds, which is correct if this "
                         "terminal has not stayed frontmost for %d consecutive ticks"
                         % focus.SETTLE_TICKS)

        # -- 3c. MOVING THE LOCK, on purpose. Everything above is inference; this is
        # the override, over the wire, from both surfaces it can be asked from - the
        # spoken phrase and the pill on the card. WHICH of the two lawful answers it
        # gives depends on what is genuinely in front of this machine while preflight
        # runs, so both are accepted and the one that happened is named. What is not
        # accepted is a third answer, a refusal, or a lock that lands in silence.
        for label, instruction in (
                ("\"lock on this tab\"", {"say": "lock on this tab"}),
                ("the LOCK THIS TAB pill", {"cmd": "retarget", "source": "card"})):
            status, _, body = post_json("/focus", instruction, timeout=30,
                                        label="POST /focus (retarget)")
            payload = as_json(body) or {}
            moved = payload.get("focus") or {}
            if status != 200 or not payload.get("ok"):
                return FAIL, ["%s was refused (HTTP %s %s), which would leave ending "
                              "the session as the only way to fix a wrong lock"
                              % (label, status, first_line(payload.get("error")))]
            if set(moved) != set(focus.PUBLIC_KEYS):
                return FAIL, ["the reply to %s is not the whitelisted shape: %s"
                              % (label, sorted(set(moved) ^ set(focus.PUBLIC_KEYS)))]
            said = " ".join(l.get("text", "") for l in (moved.get("say") or []))
            if focus.LINES["unreadable"][:28] in said:
                warnings.append("%s could not read the windows at that instant, so it "
                                "changed nothing and said so - the right refusal, but "
                                "it leaves the re-target unproven on this machine"
                                % label)
                continue
            if moved.get("locked") and not moved.get("deferred"):
                if focus.LINES["settled"] not in said:
                    return FAIL, ["%s moved the lock SILENTLY (%r), and a lock you "
                                  "cannot hear landing is one you cannot correct"
                                  % (label, first_line(said, 90))]
                notes.append("%s locked what is in front of this machine in ONE read%s"
                             % (label, " and its site" if moved.get("tabWatched")
                                else ", application only (no readable site)"))
            elif moved.get("deferred"):
                if "lock on where you land" not in said:
                    return FAIL, ["%s re-armed the lock without saying so (%r), so "
                                  "nothing would be watched and nothing would say it"
                                  % (label, first_line(said, 90))]
                notes.append("%s re-armed the deferred lock and said where it will be "
                             "looking - the right answer whenever the surface in front "
                             "cannot be the one meant: home base, where the button "
                             "lives, or no readable tab behind the card at all" % label)
            else:
                return FAIL, ["%s left the session neither locked nor deferred "
                              "(locked=%r deferred=%r state=%r), which is a session "
                              "watching nothing and not admitting it"
                              % (label, moved.get("locked"), moved.get("deferred"),
                                 moved.get("state"))]

        # -- 4. the stream. The three-second callout promise rests entirely on this:
        # a hidden tab's timers are throttled to about once a minute, so polling
        # from the one tab that is not in front could not possibly meet it.
        conn = http.client.HTTPConnection(server.HOST, server.PORT, timeout=12)
        try:
            conn.request("GET", "/focus/stream")
            res = conn.getresponse()
            ctype = res.getheader("Content-Type") or ""
            if res.status != 200 or "text/event-stream" not in ctype:
                return FAIL, ["/focus/stream answered HTTP %s as %r, which no browser "
                              "will treat as an event stream" % (res.status, ctype)]
            frame, deadline = b"", time.time() + 6
            while time.time() < deadline and not frame.endswith(b"\n\n"):
                chunk = res.read(1)
                if not chunk:
                    break
                frame += chunk
        finally:
            conn.close()
        if not frame.startswith(b"event: focus\ndata: "):
            return FAIL, ["/focus/stream sent %r instead of a focus event"
                          % first_line(frame.decode("utf-8", "replace"), 60)]
        pushed = json.loads(frame.split(b"data: ", 1)[1].decode("utf-8"))
        if set(pushed) != set(focus.PUBLIC_KEYS):
            return FAIL, ["the STREAM sends a different shape from GET /focus: "
                          "%s" % sorted(set(pushed) ^ set(focus.PUBLIC_KEYS))]
        notes.append("/focus/stream pushed a live frame as text/event-stream, which "
                     "is what a background tab needs to hear a callout in seconds")

        # -- 5. what came back may name a place in ONE sentence, and nowhere else.
        #
        # This used to be a flat "no identity anywhere", and that claim is no longer
        # the true one: a named callout says the site or the application out loud, on
        # purpose. So the check splits in two, which is also the promise split in two.
        # No key outside the say queue may hold an identity, ever. And a say line that
        # holds one has to be a line from the named pools AND has to be gone from the
        # next few responses - spoken, then scrubbed, which is the whole of what
        # "never written down" means over the wire.
        raw = focus._probe_raw() or {}
        identities = [w for w in (str(raw.get("app") or ""), str(raw.get("host") or ""))
                      if len(w) > 3]

        def _names_in(payload):
            blob = (json.dumps(payload, ensure_ascii=False)
                    + json.dumps(payload)).lower()
            return [w for w in identities if w.lower() in blob]

        keys_only = dict(pushed)
        keys_only.pop("say", None)
        if _names_in(keys_only):
            return FAIL, ["AN IDENTITY REACHED THE CLIENT IN A FIELD: the state sent "
                          "over HTTP has what is in front of you right now in a key "
                          "that is not the spoken queue, where nothing scrubs it"]
        # The names this machine's reader would derive for what is in front of it. A
        # line that mentions an identity has to be a named callout whose blank holds
        # exactly one of these, which is a much narrower claim than "it looks like a
        # template": the same sentence with a URL, a path or a window title in it
        # fails, and so does a line that merely happens to have a comma in the right
        # place.
        lawful = set(n for n in (focus.site_label(raw.get("host")),
                                 focus.app_label(raw.get("app"))) if n)
        spoken_names = [l.get("text", "") for l in (pushed.get("say") or [])
                        if any(w.lower() in str(l.get("text", "")).lower()
                               for w in identities)]
        strays = [t for t in spoken_names if _named_label(t) not in lawful]
        if strays:
            return FAIL, ["AN IDENTITY REACHED THE CLIENT IN SOMETHING THAT IS NOT A "
                          "NAMED CALLOUT: %r. Only the named pools may say where you "
                          "are, only the derived NAME may be in them, and only they "
                          "are scrubbed" % first_line(strays[0], 80)]
        if not spoken_names:
            notes.append("nothing the server sent names the application or site it is "
                         "watching, in any key or any line, checked against this "
                         "machine's live reader%s"
                         % (" (naming is on; nothing drifted while this ran)"
                            if focus.NAME_DRIFTS else " (naming is switched OFF)"))
        else:
            # It named somewhere. Now prove the sentence does not survive, by reading
            # the route until it is gone rather than by trusting the module.
            gone_at, deadline = None, time.time() + focus.LABEL_LINE_TTL_S + 4
            started_wait = time.time()
            while time.time() < deadline:
                time.sleep(0.4)
                if not _names_in(_focus_now()):
                    gone_at = time.time() - started_wait
                    break
            if gone_at is None:
                return FAIL, ["a callout named where you drifted to and the sentence "
                              "was STILL in the state %.0f seconds later, so the name "
                              "is being kept rather than spoken"
                              % (focus.LABEL_LINE_TTL_S + 4)]
            notes.append("a callout named the place out loud and the sentence was gone "
                         "from the route %.1f seconds later - said, not recorded"
                         % gone_at)

        # -- 6. the /chat backstop. A tab that has not been reloaded since this
        # landed must not be able to have an instruction ANSWERED instead of obeyed.
        status, _, body = post_json("/chat", {"question": "how long have I got left",
                                             "session": "preflight-focus"},
                                   timeout=60, label="POST /chat (focus backstop)")
        payload = as_json(body) or {}
        if payload.get("kind") != "focus":
            return FAIL, ["/chat treated a focus instruction as a question about the "
                          "notes (kind=%r), so a stale tab could talk about the "
                          "session instead of running it" % payload.get("kind")]
        notes.append("/chat routes a focus instruction to the timer: %s"
                     % first_line(payload.get("answer"), 72))

        # -- 7. and an ordinary question is NOT a focus instruction, which is the
        # half of the rule that stops the timer eating the conversation.
        status, _, body = post_json("/focus", {"say": "what do my notes say about "
                                                     "the roasting profile"},
                                    timeout=30, label="POST /focus (not a command)")
        payload = as_json(body) or {}
        if status == 200 or payload.get("ok"):
            return FAIL, ["/focus accepted an ordinary question as an instruction"]
        notes.append("an ordinary question is refused by /focus: HTTP %s" % status)

        # -- 8. and the ASSISTANT knows the recovery, so that asked how to move the
        # lock it answers instead of inventing a control. Both prompts, because a
        # question about the timer matches no note and therefore lands in the
        # small-talk one. The two forbidden answers are named: they are precisely the
        # two a helpful model invents, and both cost you the session.
        for name, prompt in (("the notes prompt", server.SYSTEM_PROMPT),
                             ("the small-talk prompt", server.SMALLTALK_PROMPT)):
            if "lock on this tab" not in prompt:
                return FAIL, ["%s never mentions \"lock on this tab\", so asked how to "
                              "move the lock the assistant will invent an answer"
                              % name]
            if "LOCK THIS TAB" not in prompt:
                return FAIL, ["%s does not know about the button on the card" % name]
            low = prompt.lower()
            if "bring a tab to the front and" not in low or "focus" not in low:
                return FAIL, ["%s does not forbid \"bring the tab to the front and "
                              "press FOCUS\" - the one plausible-sounding answer that "
                              "would lock the assistant's own tab" % name]
            if "restart" not in low:
                return FAIL, ["%s does not forbid telling them to restart the session "
                              "to change the target" % name]
            # And the truth about naming, in the same two prompts. A privacy claim
            # that is slightly out of date is worse than none: they will find out it
            # was wrong by hearing the callout say "Instagram".
            if "out loud where they" not in low:
                return FAIL, ["%s does not tell the truth about what the session says "
                              "out loud, so asked what it can see the assistant will "
                              "either guess or repeat a promise that is no longer "
                              "true" % name]
            if "writes none of it down" not in low:
                return FAIL, ["%s says the session names where you went but not that "
                              "it keeps no record of it, which is the half that "
                              "actually answers the question" % name]
        notes.append("both system prompts teach the one real recovery - go to the tab "
                     "and say \"lock on this tab\" - forbid the two answers that would "
                     "cost a session, and tell the truth about naming: said out loud, "
                     "written down nowhere")

        # -- 9. the naming machinery itself, checked in this process because it is
        # about what CANNOT be reached rather than about a route. Every named template
        # is in the registry (so _emit will speak it), every named pool has four lines
        # in it (so a long drift does not loop three phrases), and no key exists for a
        # name to be stored in.
        pools = dict(focus.CALLOUTS_NAMED)
        pools["intent"] = focus.CALLOUTS_INTENT_NAMED
        pools["drill"] = focus.CALLOUTS_DRILL_NAMED
        thin = sorted(k for k, pool in pools.items() if len(pool) < 4)
        if thin:
            return FAIL, ["named callout pools with fewer than four lines: %s - a "
                          "drift that outlasts the pool starts sounding like a "
                          "ringtone" % thin]
        unregistered = [t for pool in pools.values() for t in pool
                        if t not in focus.LINE_REGISTRY]
        if unregistered:
            return FAIL, ["a named line is not in LINE_REGISTRY, so _emit would refuse "
                          "to speak it: %r" % first_line(unregistered[0], 60)]
        if any("label" in k.lower() for k in focus.PUBLIC_KEYS):
            return FAIL, ["PUBLIC_KEYS has a key a name could be stored in"]
        if focus.site_label("127.0.0.1") is not None:
            return FAIL, ["home base can be given a name, so the Jarvis tab could be "
                          "called out by name as though it were a distraction"]
        notes.append("naming is %s: %d named lines across %d pools, all in "
                     "LINE_REGISTRY, none of them storable - a name lives for one "
                     "tick (%gs) and no key exists to keep it in"
                     % ("ON" if focus.NAME_DRIFTS else "OFF (NAME_DRIFTS=False)",
                        len(focus.NAMED_LINES), len(pools), focus.LABEL_LINE_TTL_S))

    finally:
        # Whatever happened above, no session is left running and nothing is
        # recorded: abort is the one ending that never touches the ledger.
        post_json("/focus", {"cmd": "abort"}, timeout=30, label="POST /focus (abort)")

    ended = _focus_now()
    if ended.get("state") in ("arming", "running", "paused"):
        return FAIL, ["this check left a session running (%s) - abort it before "
                      "trusting the numbers above" % ended.get("state")]
    if ledger_bytes() != before_ledger:
        return FAIL, ["THE LEDGER CHANGED. preflight must not be able to alter your "
                      "streak; a check that shortens a session to fit in a harness "
                      "has no business recording it"]
    notes.append("the session was aborted, nothing is left running, and the ledger "
                 "is byte-for-byte what it was before this check ran")

    if warnings:
        return WARN, notes + warnings
    return PASS, notes


def check_eyes():
    """12. The eyes publish booleans, nudge once, and cannot carry a picture.

    The organ that watches your posture is the one place in this project where a claim
    about privacy is structural rather than editorial: the camera is read in the browser
    and what reaches the server is three booleans and a word about the microphone. So
    this check is written to be able to FAIL that claim rather than to illustrate it - a
    frame, a landmark, a coordinate and a face are all sent up under plausible names,
    and the reply is searched for every one of them.

    Three things it deliberately does not do.

    It does not exercise THE RELIEF VALVE over HTTP. "no Jarvis, I need to do something
    important" silences the eyes for three minutes, and a preflight that helped itself
    to that would spend three minutes of the user's own silence to prove a feature
    works. The phrase is parsed in this process instead, where it changes nothing.

    It does not run while a camera is open in a tab, or while a session is running: the
    cooldown, the nudge count and the drift count are single and global, and a harness
    that reads them while somebody is using them is reading somebody else's numbers.

    And it cannot un-spend the one nudge it uses. That is the acknowledged price of
    proving the nudge works, said out loud in the last note rather than hidden.
    """
    if not state["up"]:
        return FAIL, ["skipped: the server is not reachable"]

    notes, warnings = [], []

    opening = _focus_now()
    if opening.get("state") in ("arming", "running", "paused"):
        return WARN, ["a focus session is ALREADY RUNNING (%s), and the eyes report "
                      "into it, so this check stood down rather than count a drift "
                      "against somebody's real session" % opening.get("state"),
                      "end it and run preflight again to check this chain"]
    if opening.get("eyesOn"):
        return WARN, ["a camera is OPEN in a tab right now and reporting posture, so "
                      "this check stood down: its posts and the tab's would interleave "
                      "and neither set of booleans would mean anything",
                      "close the eyes in the viewer and run preflight again"]
    if opening.get("hushed"):
        return WARN, ["the eyes are hushed for another %d seconds (the relief valve is "
                      "open), so a nudge could not be proved either way"
                      % opening.get("hushLeftS", 0)]
    nudges_before = opening.get("nudges", 0)

    def eyes(payload, label, timeout=30):
        status, _, body = post_json("/eyes", payload, timeout=timeout,
                                    label=label or "POST /eyes")
        return status, (as_json(body) or {}), body

    try:
        # -- 1. the eyes open, and THE EAR LAW is said. ears=False is the whole of it:
        # an organ may open the conversation, it may never open the microphone, so the
        # moment the camera comes on with the mic off has to be AUDIBLE.
        status, reply, _ = eyes({"cmd": "on", "present": True, "ears": False},
                                "POST /eyes (on)")
        if status != 200 or not reply.get("ok"):
            return FAIL, ["POST /eyes refused to open the eyes: HTTP %s %s"
                          % (status, first_line(reply.get("error")))]
        shape = set(reply)
        want = {"ok", "kind", "nodes", "answer", "viaSession", "cmd", "tuning", "focus"}
        if shape != want:
            return FAIL, ["POST /eyes answers with %s, not the eight keys it is "
                          "supposed to: %s" % (sorted(shape), sorted(want))]
        answer = str(reply.get("answer") or "")
        if focus.LINES["ears_off"] not in answer:
            return FAIL, ["the eyes came on with the microphone off and the assistant "
                          "did not say so (%r). An organ that opens a camera while the "
                          "ears are shut must admit it, or the user is left talking to "
                          "a machine that is not listening" % first_line(answer, 90)]
        if focus.LINES["eyes_on"] not in answer:
            return FAIL, ["opening the eyes is not confirmed out loud: %r"
                          % first_line(answer, 90)]
        notes.append("the eyes open with one sentence and the ear law in the next: %r"
                     % first_line(answer, 88))

        # -- 2. the tuning rides back on every reply, so the page cannot be applying a
        # rule this file no longer states. One source of truth, checked over the wire.
        if reply.get("tuning") != focus.EYES.tuning():
            return FAIL, ["the windows sent to the page are not the windows this server "
                          "holds: %s vs %s" % (reply.get("tuning"),
                                               focus.EYES.tuning())]
        notes.append("every reply carries the server's own windows: %d ms sustain, "
                     "%d s absence grace, %d s cooldown, %d s relief"
                     % (focus.EYE_SUSTAIN_MS, focus.EYE_ABSENCE_MS / 1000,
                        focus.EYE_COOLDOWN_S, focus.RELIEF_S))
        live = reply.get("focus") or {}
        if set(live) != set(focus.PUBLIC_KEYS):
            return FAIL, ["the state on an /eyes reply is not the whitelisted shape: %s"
                          % sorted(set(live) ^ set(focus.PUBLIC_KEYS))]

        # -- 3. THE SMUGGLING TEST. Everything a camera organ could plausibly be asked
        # to send, sent under the names it would be sent under, and then looked for in
        # the reply. handle_eyes reads four names; these are not among them.
        smuggle = {
            "cmd": "posture", "present": True, "headDown": False, "slouched": False,
            "ears": True,
            "frame": "SMUGGLED-FRAME-/9j/4AAQSkZJRg==",
            "jpeg": "SMUGGLED-JPEG-BYTES",
            "landmarks": [{"x": 0.4242, "y": 0.4242, "z": 0.4242}],
            "face": {"pitch": 1.2345, "chin": 0.6789},
            "name": "SMUGGLED-IDENTITY", "label": "SMUGGLED-LABEL",
            "image": "data:image/jpeg;base64,SMUGGLED-DATA-URL",
        }
        status, reply, raw = eyes(smuggle, "POST /eyes (smuggle)")
        if status != 200:
            return FAIL, ["an /eyes post with extra fields was rejected outright "
                          "(HTTP %s); unknown fields should be IGNORED, which is the "
                          "difference between a whitelist and a guess" % status]
        text = raw.decode("utf-8", "replace")
        leaked = [m for m in ("SMUGGLED", "0.4242", "1.2345", "0.6789")
                  if m in text]
        if leaked:
            return FAIL, ["a frame, a landmark or a name posted to /eyes came back in "
                          "the reply: %s" % leaked]
        seen = reply.get("focus") or {}
        if any(k for k in seen if k not in focus.PUBLIC_KEYS):
            return FAIL, ["the state grew a key when unknown fields were posted"]
        notes.append("a frame, a JPEG, landmark coordinates, face measurements and two "
                     "identities were posted to /eyes under their own names and not one "
                     "of them survives into the reply or the state")

        # -- 3a. and the route has no branch that reads BYTES at all, which is the
        # structural half of the same promise: a frame cannot arrive here by accident.
        frame, width, height = probe_frame()
        status, _, body = http_call("POST", "/eyes", frame,
                                    {"Content-Type": server.FRAME_MEDIA_TYPE,
                                     "Content-Length": str(len(frame))},
                                    timeout=30, label="POST /eyes (a real JPEG)")
        refused = as_json(body) or {}
        if status != 400 or refused.get("ok"):
            return FAIL, ["POST /eyes accepted %d bytes of JPEG (HTTP %s), so the one "
                          "route that must never take a picture takes one"
                          % (len(frame), status)]
        notes.append("a real %d-byte JPEG posted to /eyes is refused with a sentence "
                     "about JSON: there is no branch there that reads bytes"
                     % len(frame))

        # -- 4. THE NUDGE. The page has already served the 700 ms sustain by the time it
        # says headDown - that is what the boolean means - so the line comes back in
        # this reply, and with no session live it is this caller that says it.
        status, reply, _ = eyes({"cmd": "posture", "present": True, "headDown": True,
                                 "slouched": False, "ears": False},
                                "POST /eyes (head down)")
        line = str(reply.get("answer") or "")
        if not line:
            return FAIL, ["a sustained head-down posture earned no word at all"]
        if reply.get("viaSession"):
            return FAIL, ["the reply claims the line went into a session's say queue "
                          "while no session exists"]
        if line not in focus.CALLOUTS_PHONE[1]:
            return FAIL, ["the nudge is not one of the phone lines in focus.py: %r"
                          % first_line(line, 90)]
        after = reply.get("focus") or {}
        if not after.get("headDown") or not after.get("eyesOn"):
            return FAIL, ["the posture was not published as a boolean (headDown=%r "
                          "eyesOn=%r)" % (after.get("headDown"), after.get("eyesOn"))]
        if after.get("nudges") != nudges_before + 1:
            return FAIL, ["the nudge count went %s -> %s for one nudge"
                          % (nudges_before, after.get("nudges"))]
        notes.append("a sustained phone posture earns exactly one dry line, from the "
                     "phone pool, in the reply to the post that reported it: %r" % line)

        # -- 5. THE COOLDOWN. Still bent, and now quiet - the organ that could nudge you
        # every second of the day is the one thing here that must not.
        status, reply, _ = eyes({"cmd": "posture", "present": True, "headDown": True,
                                 "slouched": False, "ears": False},
                                "POST /eyes (still down)")
        if reply.get("answer"):
            return FAIL, ["a second head-down report inside the %gs cooldown was "
                          "answered again: %r"
                          % (focus.EYE_COOLDOWN_S,
                             first_line(reply.get("answer"), 80))]
        held = reply.get("focus") or {}
        if not held.get("headDown"):
            return FAIL, ["the cooldown also stopped it WATCHING: headDown went false "
                          "while the posture was still being reported"]
        if held.get("nudges") != nudges_before + 1:
            return FAIL, ["a refused nudge still spent the counter (%s)"
                          % held.get("nudges")]
        notes.append("the next report of the same posture is silent and still true: one "
                     "nudge per %gs, and the boolean never stops being published"
                     % focus.EYE_COOLDOWN_S)

        # -- 6. A CLOSED TAB. Nothing is sent for EYE_STALE_S, and the organ has to
        # report itself shut rather than leave the last posture standing: the page can
        # be closed, reloaded or muted, and a stale boolean is not a fact.
        time.sleep(focus.EYE_STALE_S + 0.7)
        stale = _focus_now()
        if stale.get("eyesOn") or stale.get("headDown") or stale.get("present"):
            return FAIL, ["%.1f seconds after the last report the eyes still claim to "
                          "be open (eyesOn=%r headDown=%r present=%r), so a closed tab "
                          "would leave a posture standing for ever"
                          % (focus.EYE_STALE_S + 0.7, stale.get("eyesOn"),
                             stale.get("headDown"), stale.get("present"))]
        notes.append("%gs of silence from the page and the eyes report themselves shut, "
                     "with no posture left standing - a closed tab cannot leave a "
                     "boolean behind" % focus.EYE_STALE_S)

        # -- 7. LOOK AT ME, over the wire, with a real frame and a real brain. The
        # difference between this and /see is the prompt and nothing else, which is
        # exactly why it is worth sending: the question must reach a model that has been
        # told it is looking at a person, not at a screen.
        question = "What do you think of my shirt?"
        status, _, body = http_call(
            "POST", "/look?q=" + urllib.parse.quote(question), frame,
            {"Content-Type": server.FRAME_MEDIA_TYPE,
             "Content-Length": str(len(frame)),
             "X-Frame-Width": str(width), "X-Frame-Height": str(height),
             "X-Frame-Age-Ms": "120"}, timeout=180, label="POST /look")
        looked = as_json(body) or {}
        if status != 200 or not looked.get("answer"):
            return FAIL, ["/look could not answer a real frame: HTTP %s %s"
                          % (status, first_line(looked.get("error") or body[:200], 160))]
        if looked.get("kind") != "look" or looked.get("nodes"):
            return FAIL, ["a look came back as kind %r citing notes %s - a photograph "
                          "of a person cites nothing"
                          % (looked.get("kind"), looked.get("nodes"))]
        saw = looked.get("saw") or {}
        if saw.get("bytes") != len(frame):
            return FAIL, ["/look reports it received %s of the %d bytes sent"
                          % (saw.get("bytes"), len(frame))]
        sentences = [s for s in re.split(r"(?<=[.!?])\s+",
                                         str(looked["answer"]).strip()) if s]
        if len(sentences) > 3:
            warnings.append("the look answered in %d sentences; it is asked for one to "
                            "three, and it will be read aloud" % len(sentences))
        if not looked.get("asAsked"):
            warnings.append("the look asked for %s by name and %s answered instead - "
                            "the fallback is honest and visible on the card, but the "
                            "Astra key is not reachable from here"
                            % (looked.get("wanted"), looked.get("brain")))
        notes.append("one frame, one question, one answer from %s: %r"
                     % (looked.get("brain"), first_line(looked["answer"], 120)))

        # -- 8. THE RELIEF VALVE, parsed and not pulled. See the docstring.
        for phrase in ("no Jarvis, I need to do something important",
                       "give me a minute",
                       "no jarvis i need to do something important"):
            parsed = focus.parse_command(phrase, False)
            if not parsed or parsed[0] != "relief":
                return FAIL, ["%r does not silence the nudges (parsed as %r), and it is "
                              "the one sentence that has to work with no session "
                              "running" % (phrase, parsed and parsed[0])]
        if focus.parse_command("that was important", False) is not None:
            return FAIL, ["an ordinary remark opens the relief valve"]
        notes.append("the relief line is understood with no session in sight and worth "
                     "%gs of silence - parsed here rather than pulled, because a "
                     "preflight that helped itself to three minutes of quiet would "
                     "cost you the thing it is checking" % focus.RELIEF_S)

        # -- 9. the pools, in this process, because this is about what CANNOT be said.
        # The eyes never name a place: the organ that watches your body has no business
        # knowing where you were, and there is no template it could say it with.
        named = [t for pool in focus.EYE_POOLS for t in pool if "{label}" in t]
        if named:
            return FAIL, ["an eye line has a place name in it: %r" % named[0]]
        unregistered = [t for pool in focus.EYE_POOLS for t in pool
                        if t not in focus.LINE_REGISTRY]
        if unregistered:
            return FAIL, ["an eye line is not in LINE_REGISTRY, so _emit would refuse "
                          "to speak it: %r" % first_line(unregistered[0], 60)]
        for word in ("frame", "image", "photo", "landmark", "pitch", "face"):
            hit = [k for k in focus.PUBLIC_KEYS if word in k.lower()]
            if hit:
                return FAIL, ["PUBLIC_KEYS has a key a picture could sit in: %s" % hit]
        if "one to three sentences" not in server.WEBCAM_PROMPT:
            return FAIL, ["the webcam prompt does not ask for one to three sentences, "
                          "so the answer will not be sayable"]
        if "not a picture of their screen" not in server.WEBCAM_PROMPT:
            return FAIL, ["the webcam prompt does not tell the model this is a person "
                          "rather than a screen, which is the whole difference between "
                          "this route and /see"]
        notes.append("%d eye lines across %d pools, every one in LINE_REGISTRY, not one "
                     "of them able to name a place - and no key in the whitelist a "
                     "picture could sit in"
                     % (sum(len(p) for p in focus.EYE_POOLS), len(focus.EYE_POOLS)))

    finally:
        # Whatever happened above, the eyes are shut and the organ knows it.
        post_json("/eyes", {"cmd": "off"}, timeout=30, label="POST /eyes (off)")

    closed = _focus_now()
    if closed.get("eyesOn"):
        return FAIL, ["this check left the eyes reporting open"]
    notes.append("the eyes were closed again on the way out; the one nudge it spent "
                 "leaves the organ in its %gs cooldown, which is the price of proving "
                 "the nudge works at all" % focus.EYE_COOLDOWN_S)

    if warnings:
        return WARN, notes + warnings
    return PASS, notes


def check_watch():
    """13. The screen watch refuses four times for nothing, then nudges once.

    The watch's whole promise is a cost: five seconds of arithmetic on a 32x18
    thumbnail, for hours, and not one byte off the machine until the screen has sat
    still for a minute. Half of that promise lives in the browser, where this file
    cannot go - so what is checked HERE is the half that guards the money, and it is
    checked by trying to spend it four different ways and watching the counter refuse
    to move:

      * a screen that is still moving,
      * a frame declared a JPEG that is not one,
      * a frame that was already old when it arrived,
      * and a request with no picture in it at all.

    Every one of those must come back as a free refusal with the nudge count unchanged,
    and the first two must come back QUIET, because a suppressed nudge that announces
    itself is not a suppressed nudge. Then one real JPEG earns one real nudge, which is
    the only paid line in the check and the only way to prove the path exists.

    Three things it deliberately does not do.

    It does not open a share, diff a thumbnail or start a clock: those are the page's,
    and test_watch.py drives them in-process, where a stillness clock can be wound by
    hand. Nothing drives them against a REAL monitor any more - watch_live.mjs did, and
    was retired when the watch chip moved into the floating desktop window - so that one
    seam is covered by using the feature and not by this file. What is asserted about the
    page here is read out of the file: the windows it applies, and the one fetch it can
    reach the network with.

    It does not exercise the relief valve, for the same reason check_eyes does not: the
    valve is three minutes of the user's own silence and a preflight has no business
    helping itself to it. Its PRECEDENCE over the purse is asserted in-process instead.

    And it cannot un-spend the nudge. The watch will refuse to nudge for three minutes
    after this check, which is said out loud in the last note rather than hidden.
    """
    if not state["up"]:
        return FAIL, ["skipped: the server is not reachable"]

    notes, warnings = [], []

    def stuck_state(label="GET /stuck"):
        _, _, body = http_call("GET", "/stuck", timeout=15, label=label)
        return as_json(body) or {}

    opening = stuck_state()
    if set(opening) != {"ok", "kind", "nodes", "answer", "tuning", "watch"}:
        return FAIL, ["GET /stuck answers with %s, not the six keys it is supposed to"
                      % sorted(opening)]
    if opening.get("tuning") != server.WATCH.tuning():
        return FAIL, ["the windows sent to the page are not the windows this server "
                      "holds: %s vs %s" % (opening.get("tuning"),
                                           server.WATCH.tuning())]
    purse = opening.get("watch") or {}
    if purse.get("hushed"):
        return WARN, ["the relief valve is open for another %d seconds and it covers "
                      "this organ too, so a nudge could not be proved either way"
                      % purse.get("hushLeftS", 0),
                      "that is the feature; wait it out and run preflight again"]
    if not purse.get("mayNudge"):
        return WARN, ["a nudge was spent %d seconds ago and the purse is shut for "
                      "another %d, so this check stood down rather than read somebody "
                      "else's cooldown"
                      % (int(server.STUCK_COOLDOWN_S) - purse.get("cooldownLeftS", 0),
                         purse.get("cooldownLeftS", 0)),
                      "nothing may shorten it; run preflight again when it expires"]
    nudges_before = purse.get("nudges", 0)
    refused_before = purse.get("refused", 0)

    tuning = opening["tuning"]
    notes.append("the windows, stated once and handed to the page: still %ds · "
                 "cooldown %ds · a %dx%d thumbnail every %dms, changed at %d luma "
                 "and %.1f%% of cells"
                 % (tuning["stillS"], tuning["cooldownS"], tuning["thumbW"],
                    tuning["thumbH"], tuning["tickMs"], tuning["cellDelta"],
                    tuning["changedFraction"] * 100))

    frame, width, height = probe_frame()
    problem = server.check_frame(server.FRAME_MEDIA_TYPE, frame, width, height, 120)
    if problem:
        return FAIL, ["the probe frame this file generated is itself unusable: %s"
                      % problem[1]]

    def nudge(body, still_s, age_ms=120, declared=server.FRAME_MEDIA_TYPE, label=""):
        headers = {"Content-Length": str(len(body or b"")),
                   "X-Frame-Width": str(width), "X-Frame-Height": str(height),
                   "X-Frame-Age-Ms": str(age_ms)}
        if declared:
            headers["Content-Type"] = declared
        status, _, raw = http_call("POST", "/stuck?stillS=%d" % still_s, body or b"",
                                  headers, timeout=180,
                                  label="POST /stuck (%s)" % (label or "nudge"))
        return status, (as_json(raw) or {}), raw

    # -- 1..4. THE FOUR FREE REFUSALS. Each one names what it wants back, because
    # "it refused" is not the claim - "it refused for nothing, and said why" is.
    free = [
        ("a screen that is still moving", 409, "moving", True,
         lambda: nudge(frame, 4, label="still moving")),
        ("a PNG wearing a JPEG's content type", 400, "mismatch", False,
         lambda: nudge(b"\x89PNG\r\n\x1a\n" + frame[8:], 90, label="a PNG")),
        ("a frame that was already a minute old", 400, "stale", False,
         lambda: nudge(frame, 90, age_ms=60000, label="a stale frame")),
        ("a request with no picture in it", 400, "noframe", False,
         lambda: nudge(b"", 90, label="no frame")),
    ]
    for label, want_status, want_why, want_quiet, call in free:
        status, reply, _ = call()
        if status != want_status or reply.get("why") != want_why:
            return FAIL, ["%s should be refused %d/%s and came back %s/%s: %s"
                          % (label, want_status, want_why, status, reply.get("why"),
                             first_line(reply.get("error"), 120))]
        if reply.get("spent") is not False:
            return FAIL, ["%s came back claiming it spent something (%r), and a "
                          "refusal that costs money is not a refusal"
                          % (label, reply.get("spent"))]
        if bool(reply.get("quiet")) != want_quiet:
            return FAIL, ["%s came back quiet=%r and should be quiet=%r. A guard is "
                          "silent because an announced silence is not a silence; a "
                          "frame fault is spoken because a watch that has gone blind "
                          "while claiming to watch is worth hearing about"
                          % (label, reply.get("quiet"), want_quiet)]
        if reply.get("tuning") != tuning or reply.get("nodes") != []:
            return FAIL, ["%s came back without the windows, or citing notes: %s"
                          % (label, first_line(json.dumps(reply.get("nodes")), 60))]
        if not str(reply.get("error") or "").strip():
            return FAIL, ["%s came back with no sentence in it at all" % label]

    midway = stuck_state("GET /stuck (after the refusals)")["watch"]
    if midway.get("nudges") != nudges_before:
        return FAIL, ["four refusals moved the nudge count from %d to %d, so at least "
                      "one of them reached the brain"
                      % (nudges_before, midway.get("nudges"))]
    if midway.get("refused") != refused_before + 4:
        return FAIL, ["the server counted %d refusals, not four"
                      % (midway.get("refused", 0) - refused_before)]
    notes.append("four ways of trying to make it think, refused for nothing: a screen "
                 "still moving, turned away without the bytes being read as a picture "
                 "at all, then a PNG, a stale frame and an empty body, none of which "
                 "reached a model")

    # -- 5. AND NOW THE ONE THAT COSTS. A real JPEG, a screen that really has stopped,
    # and a sentence back about what is on it.
    status, reply, raw = nudge(frame, int(server.STUCK_STILL_S) + 5, label="the nudge")
    if status != 200 or not reply.get("answer"):
        return FAIL, ["a real %d-byte JPEG after %ds of stillness did not earn a nudge: "
                      "HTTP %s %s" % (len(frame), int(server.STUCK_STILL_S) + 5, status,
                                      first_line(reply.get("error") or raw[:200], 160))]
    want = {"answer", "nodes", "kind", "unasked", "quiet", "spent", "stillS",
            "watch", "tuning", "saw"}
    if set(reply) != want:
        return FAIL, ["the nudge answers with %s, not the ten keys it is supposed to: "
                      "%s" % (sorted(reply), sorted(want))]
    if reply.get("kind") != "nudge" or reply.get("unasked") is not True:
        return FAIL, ["the nudge came back as kind %r, unasked=%r - it arrived without "
                      "being asked for and the page has to render it as such"
                      % (reply.get("kind"), reply.get("unasked"))]
    if reply.get("quiet") is not False or reply.get("spent") is not True:
        return FAIL, ["the nudge came back quiet=%r spent=%r"
                      % (reply.get("quiet"), reply.get("spent"))]
    if reply.get("nodes"):
        return FAIL, ["the nudge cited notes: %s. A screen that has sat still for a "
                      "minute is not a fact about the corpus" % reply.get("nodes")]
    saw = reply.get("saw") or {}
    if saw.get("bytes") != len(frame) or saw.get("mediaType") != server.FRAME_MEDIA_TYPE:
        return FAIL, ["sent %d bytes of %s and the endpoint reports %s bytes of %s"
                      % (len(frame), server.FRAME_MEDIA_TYPE, saw.get("bytes"),
                         saw.get("mediaType"))]

    # THE FRAME DOES NOT COME BACK. A route that takes a picture has to be checked for
    # the picture on the way out, so the probe is searched for in the reply as raw
    # bytes, as base64 and as the heading it was drawn with.
    blob = raw.decode("utf-8", "replace")
    leaked = []
    if frame[:64] in raw:
        leaked.append("the JPEG's own bytes")
    if base64.b64encode(frame)[:48].decode("ascii") in blob:
        leaked.append("the JPEG base64-encoded")
    if "data:image" in blob:
        leaked.append("a data URL")
    if leaked:
        return FAIL, ["the nudge handed the frame back in its reply (%s), so what was "
                      "on the screen is now in a JSON body anything could log"
                      % ", ".join(leaked)]

    answer = str(reply["answer"])
    spent = stuck_state("GET /stuck (after the nudge)")["watch"]
    if spent.get("nudges") != nudges_before + 1:
        return FAIL, ["one nudge moved the count from %d to %d"
                      % (nudges_before, spent.get("nudges"))]
    if spent.get("mayNudge") is not False:
        return FAIL, ["the purse is still open after a nudge, so the three-minute "
                      "cooldown is not being kept"]

    # -- 6. AND IMMEDIATELY SHUTS UP. The same request again, a second later.
    status, second, _ = nudge(frame, int(server.STUCK_STILL_S) + 5,
                              label="inside the cooldown")
    if status != 429 or second.get("why") != "cooldown":
        return FAIL, ["a second nudge one second later came back %s/%s instead of "
                      "429/cooldown" % (status, second.get("why"))]
    if not second.get("quiet") or second.get("spent"):
        return FAIL, ["the cooldown refusal came back quiet=%r spent=%r"
                      % (second.get("quiet"), second.get("spent"))]
    after = stuck_state("GET /stuck (after the second try)")["watch"]
    if after.get("nudges") != nudges_before + 1:
        return FAIL, ["the second attempt bought a second model call"]
    notes.append("one frame, one call, one sentence: “%s”" % first_line(answer, 120))
    notes.append("and one second later the same request is refused silently with "
                 "%ds left on the purse" % after.get("cooldownLeftS", 0))

    # -- 7. WHAT THE MODEL IS TOLD, and what it is forbidden to say back. Read in this
    # process, because this is about the prompt rather than about one answer.
    prompt = server.STUCK_PROMPT
    for banned in ("take a break", "you seem stuck", "you seem to be stuck"):
        if banned not in prompt.lower():
            return FAIL, ["the nudge prompt does not forbid %r by name, and it is the "
                          "first thing a model reaches for when it has nothing useful "
                          "to say" % banned]
    if "thumbnail" not in prompt.lower():
        return FAIL, ["the nudge prompt does not say the stillness was measured by "
                      "comparing thumbnails on the user's own machine, so the model "
                      "may claim to have been watching"]
    if not re.search(r"nothing useful", prompt, re.I):
        return FAIL, ["the nudge prompt gives the model no way to say there is nothing "
                      "useful to say, which is the only honest answer to a man who is "
                      "reading"]
    bad_keys = [k for k in server.STUCK_LINES
                if k not in ("noframe", "mismatch", "stale", "tiny", "hushed",
                             "cooldown", "moving")]
    if bad_keys or len(server.STUCK_LINES) != 7:
        return FAIL, ["the refusal table is %s, not the seven sentences it should be"
                      % sorted(server.STUCK_LINES)]

    # -- 8. THE VALVE OUTRANKS THE PURSE, asserted in-process: opening it over HTTP
    # would cost the user three minutes of silence to prove a refusal.
    order = server_source_for_watch()
    if order is None:
        return FAIL, ["nudge_for_stuck() is not in server.py any more"]
    if order.index("hushed") > order.index("mayNudge"):
        return FAIL, ["the cooldown is checked before the relief valve, so a hushed "
                      "watch would be told about a cooldown instead of a silence"]
    if order.index("mayNudge") > order.index("STUCK_STILL_S"):
        return FAIL, ["the stillness is checked before the purse"]
    if order.index("STUCK_STILL_S") > order.index("check_frame"):
        return FAIL, ["the frame is examined before the guards, so a refusal costs a "
                      "parse it did not need to do"]
    notes.append("the guards run cheapest first - relief valve, purse, stillness, then "
                 "the bytes - and the valve belongs to the eyes, so one silence covers "
                 "every organ")

    # -- 9. AND THE PAGE. Its half is driven by test_watch.py; what is read here is
    # that it applies these windows and that its loop has one door to the network.
    page = _page_source()
    if page is None:
        return FAIL, ["viewer/index.html could not be read"]
    section = page.split("=========== watch ==", 1)
    if len(section) != 2:
        return FAIL, ["the page has no watch section, so nothing in the browser is "
                      "diffing anything"]
    watch_js = section[1].split("async function ask(", 1)[0]
    posts = re.findall(r"fetch\('/stuck", watch_js)
    if len(posts) != 2:
        return FAIL, ["the page's watch section reaches the network %d times, not twice "
                      "(the windows, and the one nudge)" % len(posts)]
    for needle, complaint in (
            ("displaySurface: 'monitor'", "the picker is not opened on Entire Screen"),
            ("getSettings().displaySurface",
             "the page never asks the track what it actually got, so a tab could be "
             "watched as though it were a desk"),
            ("watchSurface === 'browser' || watchSurface === 'window'",
             "the page does not refuse a tab or a single window"),
            ("Entire Screen in the picker",
             "the refusal does not steer the user to Entire Screen"),
            ("grabFrame('screen')",
             "the page's nudge does not take its frame from the screen source")):
        if needle not in watch_js:
            return FAIL, [complaint]
    if "getUserMedia" in watch_js or "startEyes(" in watch_js:
        return FAIL, ["the watch section reaches for the camera, and this organ is "
                      "screen-only: wanting both is two switches, not one"]
    page_tune = re.search(r"let WATCH_TUNE = \{(.*?)\};", watch_js, re.S)
    if not page_tune:
        return FAIL, ["the page states no default windows at all"]
    found = {k: (float(v) if "." in v else int(v))
             for k, v in re.findall(r"(\w+):\s*([0-9.]+)", page_tune.group(1))}
    if found != tuning:
        return FAIL, ["the page's own defaults are %s and the server's are %s"
                      % (found, tuning)]
    notes.append("the page applies the server's numbers, asks the track what surface it "
                 "really got, refuses a tab out loud, and has exactly two ways to reach "
                 "the network in the whole organ")
    notes.append("the one nudge this check spent leaves the watch in its %ds cooldown, "
                 "which is the price of proving the nudge works at all"
                 % int(server.STUCK_COOLDOWN_S))

    if warnings:
        return WARN, notes + warnings
    return PASS, notes


def server_source_for_watch():
    """The body of nudge_for_stuck(), for asking what order its guards run in."""
    try:
        with open(os.path.join(ROOT, "server.py"), "r", encoding="utf-8") as fh:
            text = fh.read()
    except OSError:
        return None
    if "def nudge_for_stuck" not in text:
        return None
    return text.split("def nudge_for_stuck", 1)[1].split("\ndef ", 1)[0]


def _page_source():
    try:
        with open(os.path.join(ROOT, "viewer", "index.html"), "r",
                  encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return None


def check_instruments():
    """14. The instruments answer, from the RUNNING server, in booleans only.

    This check exists because of a specific failure that has now happened more than
    once: the code on disk is correct, every unit test passes, a fresh interpreter
    agrees - and the long-lived process serving the page is running last hour's
    module, so the feature "does not work" and nothing can explain why.

    So the first thing it does is ask the running server for /focus/diag over HTTP
    and refuse to accept a 404 as anything but that fault, by name. The pid and the
    uptime come back in the answer precisely so the reply can say WHICH process
    spoke, and tickAgeS so it can say whether that process's clock is still moving.

    After that it is the same discipline as everything else here. The diag is checked
    against focus.DIAG_KEYS as it arrives over the wire, not as focus.public_diag
    would build it in this interpreter. It is cross-examined against GET /focus,
    because two views of one session that disagree mean the tick is stale. The ledger
    is read off disk and held to the eight whitelisted row keys. And the two
    in-browser instruments are looked for in the SERVED page, since a debug overlay
    that only exists on disk is no more use than a diag route the server has not
    loaded.

    Nothing here starts a session or writes anything: the instruments have to be
    readable while you are working, which means reading them must cost you nothing.
    """
    if not state["up"]:
        return FAIL, ["skipped: the server is not reachable"]

    notes, warnings = [], []

    # -- 1. does the running process even have the route?
    status, head, body = http_call("GET", "/focus/diag", timeout=30,
                                   label="GET /focus/diag")
    if status == 404:
        try:
            with open(os.path.join(ROOT, "server.py"), "r", encoding="utf-8") as fh:
                on_disk = "/focus/diag" in fh.read()
        except OSError:
            on_disk = False
        return FAIL, ["the running server has NO /focus/diag route, and the code on "
                      "disk does%s have one" % ("" if on_disk else " not"),
                      "this is the exact fault the route was built to expose: the "
                      "process serving the page is running older code than the file "
                      "you are editing - restart it and run preflight again"
                      if on_disk else
                      "so this is not a stale process: the route is genuinely gone"]
    if status != 200:
        return FAIL, ["GET /focus/diag answered HTTP %s" % status]
    payload = as_json(body) or {}
    diag = payload.get("diag")
    if not isinstance(diag, dict):
        return FAIL, ["GET /focus/diag answered 200 with no diag object: %s"
                      % first_line(sorted(payload))]
    if "no-store" not in (head.get("cache-control") or ""):
        warnings.append("the diag is cacheable (%s), and a cached diagnostic is a "
                        "lie with a timestamp on it" % head.get("cache-control"))

    # -- 2. which process answered, and is its clock moving?
    pid = diag.get("pid")
    if not isinstance(pid, int) or pid <= 0:
        return FAIL, ["the diag names no process, so it cannot answer the one "
                      "question it exists for"]
    if pid == os.getpid():
        return FAIL, ["the diag came back with THIS process's pid (%d), which means "
                      "preflight is reading its own imported module rather than the "
                      "server" % pid]
    notes.append("answered by pid %d, up %ds, %d ticks, module v%d - a different "
                 "process from this one (%d), which is the whole point"
                 % (pid, diag.get("uptimeS", -1), diag.get("ticks", -1),
                    diag.get("version", -1), os.getpid()))

    # -- 3. the whitelist, as it arrives over the wire.
    missing = sorted(set(focus.DIAG_KEYS) - set(diag))
    extra = sorted(set(diag) - set(focus.DIAG_KEYS))
    if missing or extra:
        return FAIL, ["GET /focus/diag does not send the DIAG_KEYS whitelist: "
                      "missing=%s extra=%s" % (missing, extra)]
    wrong = []
    for name, want in sorted(focus.DIAG_KEYS.items()):
        got = diag[name]
        if want is bool and not isinstance(got, bool):
            wrong.append("%s=%r is not a boolean" % (name, got))
        elif want is int and (isinstance(got, bool) or not isinstance(got, int)):
            wrong.append("%s=%r is not a number" % (name, got))
        elif want is str and not isinstance(got, str):
            wrong.append("%s=%r is not a string" % (name, got))
    if wrong:
        return FAIL, ["the diag's own declared types do not hold over the wire:"] + \
            wrong[:6]
    notes.append("exactly the %d whitelisted diag keys, every one the declared type: "
                 "%d booleans, %d counters, %d fixed words"
                 % (len(focus.DIAG_KEYS),
                    sum(1 for t in focus.DIAG_KEYS.values() if t is bool),
                    sum(1 for t in focus.DIAG_KEYS.values() if t is int),
                    sum(1 for t in focus.DIAG_KEYS.values() if t is str)))

    # -- 4. every string is a word from a fixed list, so none of them can be a name.
    allowed = set(focus.LANES) | set(focus.TAB_READS) | set(focus.STATES)
    loose = [(k, v) for k, v in sorted(diag.items())
             if isinstance(v, str) and k != "backend" and v not in allowed]
    if loose:
        return FAIL, ["a diag string is not from the fixed vocabulary, so it could "
                      "hold an identity: %s" % loose[:4]]
    if not focus._BACKEND_RE.match(diag["backend"]):
        return FAIL, ["backend=%r is not an identifier, and that field is the one "
                      "string wide enough to smuggle something" % diag["backend"]]
    notes.append("every diag string is a word from LANES / TAB_READS / STATES "
                 "(backend %r aside, and that is an identifier), so there is nowhere "
                 "in this answer an app or a site could be" % diag["backend"])

    # -- 5. the tick, which is the freeze itself.
    live = _focus_now()
    running = live.get("state") in ("arming", "running")
    if running and not diag["tickAlive"]:
        return FAIL, ["a session is %s and the TICK THREAD IS DEAD (last tick %ds "
                      "ago): the countdown on your screen is a stale frame"
                      % (live.get("state"), diag["tickAgeS"])]
    # The thread stamps its heartbeat BEFORE it checks for a session, so once it
    # exists it is late whether or not anything is being timed - which makes this the
    # one assertion that catches a frozen process rather than a finished one.
    if diag["tickAlive"] and diag["tickAgeS"] > focus.TICK_S * 4:
        return FAIL, ["the tick thread is alive and %ds behind (a tick is %.0fs), so "
                      "this process is FROZEN rather than idle: %d ticks, up %ds"
                      % (diag["tickAgeS"], focus.TICK_S, diag["ticks"],
                         diag["uptimeS"])]
    if diag["tickAlive"]:
        notes.append("the tick thread is alive, %d ticks in and %ds behind, inside the "
                     "%.0fs tick%s" % (diag["ticks"], diag["tickAgeS"], focus.TICK_S,
                                       "" if running else
                                       " - it keeps beating between sessions, which is "
                                       "why being late means frozen and not idle"))
    else:
        notes.append("no tick thread yet, and nothing has run in this process (%d "
                     "ticks) - correct rather than broken: the thread is started by "
                     "the first session and then lives as long as the process"
                     % diag["ticks"])

    # -- 6. the two views of one session must agree, or one of them is stale.
    #
    # Only while a session is LIVE, and that is not a loophole. /focus goes on
    # publishing the last frame of an ended session on purpose, so the card can still
    # show you the report card you just earned; the diag deliberately does the
    # opposite and zeroes every session field once sessionOn goes false, because a
    # diagnostic that says "drifting" about a session that finished ten minutes ago
    # sends you looking for a drift. Both are right, and comparing them across that
    # boundary compares two different questions - so the boundary itself is what gets
    # asserted when there is nothing running.
    if diag["state"] != live.get("state"):
        return FAIL, ["/focus/diag says state=%r and /focus says state=%r in the same "
                      "process, so one of the two reads is stale"
                      % (diag["state"], live.get("state"))]
    if diag["sessionOn"]:
        for here, there in (("deferred", "deferred"), ("locked", "locked"),
                            ("drifting", "drifting"), ("inGrace", "inGrace"),
                            ("atHome", "atHome"), ("excused", "excused"),
                            ("snoozed", "snoozed"),
                            ("intentOpen", "awaitingIntent"),
                            ("sessionOnTarget", "onTarget")):
            if there in live and diag[here] != live[there]:
                return FAIL, ["/focus/diag says %s=%r and /focus says %s=%r about the "
                              "same live session in the same process"
                              % (here, diag[here], there, live[there])]
        notes.append("a session is %s, and the diag and /focus agree on all ten facts "
                     "they both hold (deferred %s, on target %s), so neither read is "
                     "stale" % (diag["state"], diag["deferred"],
                                diag["sessionOnTarget"]))
    else:
        # `locked` is left out: it is a fact about the READER, and an ended session's
        # reader may legitimately still be holding the target it settled on.
        stuck = [k for k in ("deferred", "drifting", "inGrace", "atHome", "excused",
                             "snoozed", "intentOpen", "sessionOnTarget")
                 if diag[k]]
        if stuck:
            return FAIL, ["no session is live and the diag still reports %s true, "
                          "which would send you hunting a drift that ended" % stuck]
        notes.append("no live session (state %r), and the diag's whole session block "
                     "reads false rather than holding the last frame - /focus keeps "
                     "that frame for the report card, and the diag deliberately "
                     "does not" % diag["state"])
    if diag["sessionOn"] and diag["readerOnTarget"] != diag["sessionOnTarget"]:
        warnings.append("a fresh read says on-target=%s and the tick last decided %s; "
                        "that is either a lock that just moved or a stale tick, and "
                        "?focusdebug=1 marks it DISAGREE on the glass"
                        % (diag["readerOnTarget"], diag["sessionOnTarget"]))

    # -- 7. the ledger, held to the eight keys, as it sits on disk.
    try:
        with open(focus.LEDGER_PATH, "rb") as fh:
            raw = fh.read()
    except OSError:
        raw = b""
    book = json.loads(raw.decode("utf-8", "replace")) if raw.strip() else {}
    if not isinstance(book, dict):
        return FAIL, ["the ledger on disk is not an object at all"]
    stray = sorted(set(book) - set(focus._LEDGER_DEFAULT))
    if stray:
        return FAIL, ["the ledger holds keys nobody declared: %s" % stray]
    rows = [r for r in (book.get("history") or []) if isinstance(r, dict)]
    bad_rows = sorted({k for r in rows for k in r} - set(focus.SESSION_ROW_KEYS))
    if bad_rows:
        return FAIL, ["a session row on disk carries keys outside the whitelist, so "
                      "something bypassed session_row(): %s" % bad_rows]
    notes.append("the ledger carries %d session%s of %d, each row exactly the %d "
                 "whitelisted keys (%s) - no site, no app, no intent, no clock times"
                 % (len(rows), "" if len(rows) == 1 else "s",
                    focus.LEDGER_HISTORY_MAX, len(focus.SESSION_ROW_KEYS),
                    ", ".join(sorted(focus.SESSION_ROW_KEYS))))
    if not rows:
        notes.append("nothing in the history yet: a session has to run past %ds to "
                     "earn a row" % int(focus.MIN_LEDGER_S))

    # -- 8. and the two in-browser instruments, in the SERVED page.
    _, _, page = http_call("GET", "/", timeout=15, label="GET / (instruments)")
    text = page.decode("utf-8", "replace")
    wanted = {"the ?focusdebug=1 overlay": "focusdebug",
              "the ?focusprobe=1 battery": "focusprobe",
              "the overlay reading /focus/diag": "/focus/diag",
              "the probe's asserted viewport": "PROBE_W = 1440",
              "the verdict in the page title": "document.title = 'PROBE "}
    absent = sorted(name for name, token in wanted.items() if token not in text)
    if absent:
        return FAIL, ["the page the server SERVES is missing %s - which, with check 8 "
                      "passing, means the file on disk is missing it too"
                      % "; ".join(absent)]
    notes.append("the served page carries both instruments: the overlay reads "
                 "/focus/diag and the battery asserts 1440x900 and writes PASS/FAIL "
                 "per case into the title, where a script can read it")

    if warnings:
        return WARN, notes + warnings
    return PASS, notes


def check_web():
    """15. The live lookup fetches, cites, and knows which world it is speaking from.

    FOUR live calls, and the fourth is the one that matters most. It is easy to build a
    search that answers everything and easy to build one that answers nothing; the only
    interesting question is whether the boundary is in the right place. So:

      1. a question the notes certainly do not cover  -> kind "web", real URLs, and an
         answer that says where it came from rather than simply knowing;
      2. the force trigger, on a question the notes DO partly cover -> web anyway,
         because "look this up" is an instruction and not a hint;
      3. a real question about a real note            -> kind "notes", no sources, and
         no lookup anywhere near it;
      4. a greeting                                   -> kind "chat", and above all NOT
         a search. Small talk scores nothing, and a threshold read carelessly would
         send "morning" to a search engine.

    What is deliberately NOT asserted: any particular fact. The population of Tokyo is
    not this harness's business, and a check that pinned it would fail the day the
    figure changed - which is the day the feature is working best. What is asserted is
    the SHAPE of honesty: a URL you can open, a phrase that admits its source, and no
    note indexes on an answer that came from outside the collection.

    A network that cannot reach any backend is reported as a WARN rather than a FAIL:
    the code is then untested but not broken, and the fallback line it produces is
    itself part of the contract, so that is checked instead.
    """
    notes, warnings = [], []

    # -- 1. something the notes cannot possibly hold.
    question = "What is the current population of Tokyo?"
    status, _, body = post_json("/chat", {"question": question,
                                          "session": "preflight-web"}, timeout=120)
    data = as_json(body)
    if data is None:
        return FAIL, ["asked: %s" % question,
                      "HTTP %s and the body was not JSON: %s"
                      % (status, first_line(body[:200]))]
    kind = data.get("kind")
    answer = str(data.get("answer") or "")
    sources = data.get("sources")

    if kind == "web":
        if not isinstance(sources, list) or not sources:
            return FAIL, ["a web answer arrived with no sources array - the panel would "
                          "have nothing to show, so the citation is a claim and not a "
                          "link (keys: %s)" % ", ".join(sorted(data))]
        bad = [s for s in sources
               if not isinstance(s, dict)
               or not str(s.get("url") or "").startswith(("http://", "https://"))
               or not str(s.get("title") or "").strip()]
        if bad:
            return FAIL, ["a source came back without an openable http(s) URL and a "
                          "title: %s" % first_line(json.dumps(bad[:2]))]
        extra = sorted({k for s in sources for k in s} - {"title", "url"})
        if extra:
            return FAIL, ["the sources handed to the browser carry more than a title "
                          "and a URL (%s) - web_sources() is meant to be a whitelist"
                          % extra]
        if data.get("nodes"):
            return FAIL, ["a web answer cited note indexes %s. Nothing in the galaxy "
                          "produced this answer, so nothing in the galaxy may be lit "
                          "for it" % data["nodes"]]
        # It must SAY where it came from. Either the phrase, or a URL in the prose -
        # the prompt asks for the phrase and forbids the URL, so either satisfies the
        # user-visible claim "it cites its source rather than simply knowing".
        said = ("according to" in answer.lower() or "http" in answer.lower()
                or "web source" in answer.lower())
        if not said:
            return FAIL, ["asked: %s" % question,
                          "answered from the web without saying so: “%s”"
                          % first_line(answer),
                          "the whole point of the cue is that the reader can tell which "
                          "world an answer came from without asking"]
        if data.get("searched") not in ("force", "world", "thin"):
            return FAIL, ["the reply does not say WHY it searched (searched=%r)"
                          % data.get("searched")]
        notes.append("asked: %s" % question)
        notes.append("kind=web via %s (%s), %d source%s: %s"
                     % (data.get("backend"), data.get("searched"), len(sources),
                        "" if len(sources) == 1 else "s",
                        "; ".join(s["url"][:58] for s in sources)))
        notes.append("“%s”" % first_line(answer))
    elif kind == "chat" and data.get("webSilent"):
        warnings.append("the lookup ran and every backend came back empty, so the "
                        "fetching path is UNTESTED on this network. It failed the way "
                        "it promises to, though: %r" % first_line(answer))
        if answer.strip() != server.WEB_SILENT_LINE:
            return FAIL, ["a silent web produced %r instead of the fixed line %r"
                          % (first_line(answer), server.WEB_SILENT_LINE)]
    else:
        return FAIL, ["asked: %s" % question,
                      "came back kind=%r, which means no lookup was even attempted for "
                      "a question the notes certainly do not cover (searched=%r)"
                      % (kind, data.get("searched")),
                      "“%s”" % first_line(answer)]

    # -- 2. THE FORCE TRIGGER, aimed at something the notes DO cover, so that a pass
    # means the trigger genuinely bypassed the local check rather than coinciding with
    # a thin score.
    subject = "pricing"
    if state.get("graph"):
        top = max(state["graph"]["nodes"], key=lambda n: n.get("degree") or 0)
        subject = str(top.get("label") or subject)
    forced = "Jarvis, look this up: %s" % subject
    status, _, body = post_json("/chat", {"question": forced,
                                          "session": "preflight-web"}, timeout=120)
    data = as_json(body) or {}
    if data.get("kind") == "web":
        notes.append("“%s” went straight to the web (%s) and cited %d source%s, even "
                     "though %r is a note in the collection"
                     % (forced, data.get("backend"), len(data.get("sources") or []),
                        "" if len(data.get("sources") or []) == 1 else "s", subject))
    elif data.get("searched") == "force":
        warnings.append("the force trigger fired on %r and the backends returned "
                        "nothing usable, so it fell back (kind=%s)"
                        % (forced, data.get("kind")))
    else:
        return FAIL, ["said: %s" % forced,
                      "and it came back kind=%r searched=%r - the force trigger is "
                      "meant to bypass the local check entirely"
                      % (data.get("kind"), data.get("searched")),
                      "nothing else in this feature is worth having if an explicit "
                      "instruction can be quietly reinterpreted"]

    # -- 3. a real question about a real note must NOT search.
    if not state.get("graph"):
        warnings.append("skipped the local-note half: no graph data to build a real "
                        "question from")
    else:
        nodes = state["graph"]["nodes"]
        top = max(nodes, key=lambda n: n.get("degree") or 0)
        local = "What do the notes say about %s?" % top.get("label")
        status, _, body = post_json("/chat", {"question": local,
                                             "session": "preflight-web"}, timeout=120)
        data = as_json(body) or {}
        if data.get("kind") != "notes":
            return FAIL, ["asked: %s" % local,
                          "and the reply came back kind=%r searched=%r. A question the "
                          "collection answers must be answered FROM the collection - "
                          "trading it for a stranger's blog is the failure this feature "
                          "is most likely to introduce"
                          % (data.get("kind"), data.get("searched"))]
        if data.get("sources") or data.get("searched"):
            return FAIL, ["a notes answer carried web fields (sources=%r searched=%r), "
                          "so the two worlds are bleeding into one another"
                          % (data.get("sources"), data.get("searched"))]
        if not data.get("nodes"):
            return FAIL, ["asked: %s" % local, "answered but cited no notes at all"]
        notes.append("“%s” stayed local: kind=notes, %d note%s cited, no search, no "
                     "sources" % (local, len(data["nodes"]),
                                  "" if len(data["nodes"]) == 1 else "s"))

    # -- 4. and a greeting must not go anywhere near a search engine.
    status, _, body = post_json("/chat", {"question": "morning!",
                                          "session": "preflight-web"}, timeout=120)
    data = as_json(body) or {}
    if data.get("kind") != "chat" or data.get("searched"):
        return FAIL, ["“morning!” came back kind=%r searched=%r - small talk scores "
                      "nothing, and a threshold read without asking whether a question "
                      "was even ASKED sends every greeting to a search engine"
                      % (data.get("kind"), data.get("searched"))]
    notes.append("“morning!” stayed small talk: no lookup, no sources")

    # -- and the wiring, read rather than assumed.
    _, _, health = http_call("GET", "/health", timeout=15, label="GET /health (web)")
    web = (as_json(health) or {}).get("web") or {}
    if not isinstance(web.get("backends"), list) or not web["backends"]:
        return FAIL, ["/health does not report which search backends this config has"]
    if web.get("keyChars") and not web.get("keyConfigured"):
        warnings.append("config.json holds a %d-character search_api_key that "
                        "backends() is refusing as a placeholder" % web["keyChars"])
    notes.append("backends in order: %s · threshold %s · key %s"
                 % (", ".join(web["backends"]), web.get("threshold"),
                    "configured (%d chars)" % web["keyChars"]
                    if web.get("keyConfigured") else "none needed"))

    if warnings:
        return WARN, notes + warnings
    return PASS, notes


LEDGER_FILE = os.path.join(ROOT, "tools-ledger.json")
LEDGER_ROW_KEYS = {"ok", "failed", "refused", "lapsed", "last"}
SCAN_SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv", "venv", ".idea"}


def _voice_label(model):
    """'en_GB-alan-medium' -> 'Alan'. Derived the same way the tool derives it.

    Deliberately a copy of tools/set_voice.py's label() rather than an import: this
    check exists to read the refusal a human would hear, and a check that borrows the
    tool's own function to decide what the tool should have said can only ever agree
    with it. Six lines of duplication buys an independent witness.
    """
    parts = [p for p in str(model or "").split("-") if p]
    word = parts[1] if len(parts) > 1 else (parts[0] if parts else "")
    word = "".join(c for c in word if c.isalnum())
    return (word[:1].upper() + word[1:]) if word else str(model or "")


def _installed_voices():
    """The model ids this machine can actually speak in, from the disk, sorted.

    Both halves required - piper wants the .onnx and its .onnx.json alongside - because
    the question being asked is "what could be spoken", not "what was downloaded".
    """
    found = []
    try:
        names = sorted(os.listdir(os.path.join(ROOT, "voices")))
    except OSError:
        return []
    for name in names:
        if name.endswith(".onnx") and os.path.isfile(
                os.path.join(ROOT, "voices", name + ".json")):
            found.append(name[:-5])
    return found


def _ledger_file():
    """The tool ledger as it is on disk, or {} if it has never been written.

    Read from the FILE and not from an endpoint, because the claim under test is about
    what is on disk: an endpoint can only report what it chooses to, and this check
    exists to look at the thing itself. An absent ledger is a legitimate state - a
    machine that has never run a tool has nothing to account for.
    """
    try:
        with open(LEDGER_FILE, "rb") as fh:
            data = json.loads(fh.read().decode("utf-8", "replace"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _ledger_row(tool_id, data=None):
    """The four counts for one tool, as integers, missing or corrupt reading as zero."""
    data = _ledger_file() if data is None else data
    rows = data.get("tools") if isinstance(data.get("tools"), dict) else {}
    row = rows.get(tool_id) if isinstance(rows.get(tool_id), dict) else {}
    counts = {}
    for key in ("ok", "failed", "refused", "lapsed"):
        try:
            counts[key] = int(row.get(key) or 0)
        except (TypeError, ValueError):
            counts[key] = 0
    return counts


def _disk_hits(needle, cap_mb=8):
    """Every file under the project root whose BYTES contain `needle`.

    Bytes rather than text, and every file rather than a list of interesting ones: a
    leak that only happened into a file nobody thought to name is still a leak. The
    walk is cheap here (a few megabytes) and the honesty is worth more than the speed.
    """
    target = needle.encode("utf-8")
    hits, unscanned = [], 0
    for folder, dirs, files in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in SCAN_SKIP_DIRS]
        for name in files:
            path = os.path.join(folder, name)
            try:
                if os.path.getsize(path) > cap_mb * 1024 * 1024:
                    unscanned += 1
                    continue
                with open(path, "rb") as fh:
                    blob = fh.read()
            except OSError:
                unscanned += 1
                continue
            if target in blob:
                hits.append(os.path.relpath(path, ROOT).replace("\\", "/"))
    return sorted(hits), unscanned


def _scrubbed(blob):
    """A response with the ONE place a parameter is allowed to appear taken out.

    `pending.params` travels to the page on purpose - the human about to approve an
    action has to be able to read exactly what they are approving. Everything else,
    and above all `answer`, is either spoken aloud or written down, so everything
    else has to be clean. Removing the permitted field is what turns "the canary is
    somewhere in the traffic" into a claim worth making.
    """
    text = blob.decode("utf-8", "replace")
    try:
        data = json.loads(text)
    except ValueError:
        return text
    if isinstance(data, dict) and isinstance(data.get("pending"), dict):
        data = dict(data)
        pending = {k: v for k, v in data["pending"].items() if k != "params"}
        data["pending"] = pending
    return json.dumps(data, ensure_ascii=False)


def check_hands():
    """16. Nothing runs unasked, nothing runs twice, and nothing it was given is kept.

    Eight questions, in the order a doubt about this feature would occur to you:

      (a) /execute with nothing pending        -> a named refusal, not a shrug;
      (b) a proposal naming a tool that is not in the registry -> refused, and the slot
          left EMPTY, because a near-miss must not leave something a later "yes" could
          confirm. No fuzzy matching, no nearest name: the same discipline as the model
          allowlist;
      (c) a proposal missing a required parameter -> refused NAMING the field;
      (d) the happy path, on selftest.py and nothing else: propose, confirm through the
          spoken door, the script's own stdout comes back, and the ledger moves by
          exactly one. selftest is hermetic on purpose - a harness must never be able
          to put a line in the employer's calendar or an email in anyone's inbox;
      (e) the same proposal confirmed twice -> the second is refused, and the ledger
          proves it by not moving;
      (f) THE CANARY. A made-up string, generated fresh this run so it cannot already
          be in the source, is put in a parameter the proposal template never speaks.
          It must then appear nowhere on disk - not in the ledger, not in a log - and
          nowhere in any response except the one field the page renders for the human;
      (g) a greeting -> no proposal and no search. The vocative law sits above the
          hands: "good morning" can surface nothing;
      (h) THE SPOKEN DIAL. set_voice is the one hand that writes a file this project
          cares about, so it is gated the way send_email is: by being refused. A
          proposal with no voice is refused naming the field; a name nobody has heard
          of, confirmed through the spoken door, is refused BY THE HAND and the refusal
          recites what IS installed; a real voice proposes with current beside requested
          and is then cancelled. config.json is digested before and after, and not one
          byte may move.

    Nothing here touches the calendar and nothing sends mail. (c) and (f) use
    send_email, and both are refused before anything could run. (h) never writes: the
    voice this machine speaks in at the end of this check is the voice it spoke in at
    the start, proved by sha256 and not by inspection.
    """
    notes, warnings = [], []

    # -- 0. the registry, as the page is served it: the only source of truth, and it
    #       carries no script path, no trigger and - having never held one - no key.
    status, _, body = http_call("GET", "/tools", timeout=20, label="GET /tools")
    data = as_json(body) or {}
    tools = data.get("tools")
    if status != 200 or not isinstance(tools, list) or not tools:
        return FAIL, ["GET /tools came back %s with %r - the registry is the only "
                      "source of truth and the page cannot read it"
                      % (status, first_line(body.decode("utf-8", "replace")))]
    if data.get("error"):
        return FAIL, ["the registry did not load cleanly: %s" % data["error"]]
    allowed = {"id", "name", "capabilities", "params", "timeoutS"}
    stray = sorted({k for t in tools if isinstance(t, dict) for k in t} - allowed)
    if stray:
        return FAIL, ["GET /tools serves keys outside the whitelist (%s) - the script "
                      "path and the triggers must not leave the server"
                      % ", ".join(stray)]
    ids = [t.get("id") for t in tools]
    if "selftest" not in ids or "send_email" not in ids:
        return FAIL, ["the registry serves %s; this check needs selftest (hermetic) "
                      "and send_email (refused, never sent)" % ids]
    if data.get("ttlS") != 120:
        return FAIL, ["CONFIRM_TTL_S is %r over the wire, and the specification says "
                      "120" % data.get("ttlS")]
    notes.append("registry: %d tool%s (%s), %d capability sentences, TTL %ds - no "
                 "script path and no trigger on the wire"
                 % (len(tools), "" if len(tools) == 1 else "s", ", ".join(ids),
                    sum(len(t.get("capabilities") or []) for t in tools),
                    data["ttlS"]))

    # An earlier check, or a hand in another tab, may have left something pending.
    post_json("/tools", {"cmd": "cancel", "door": "curl"}, timeout=20,
              label="POST /tools (clear before check 16)")

    # -- (a) the door that runs things, knocked on with nothing behind it.
    status, _, body = post_json("/execute", {"door": "curl"}, timeout=30,
                                label="POST /execute (nothing pending)")
    data = as_json(body) or {}
    if status != 409 or data.get("refused") != "nothing-pending" or data.get("ok"):
        return FAIL, ["(a) /execute with nothing pending came back %s ok=%r refused=%r "
                      "- the gate is the whole feature"
                      % (status, data.get("ok"), data.get("refused"))]
    if not str(data.get("answer") or "").strip():
        return FAIL, ["(a) refused silently; a refusal the employer cannot hear is not "
                      "a refusal"]
    notes.append("(a) /execute with nothing pending: 409 refused=nothing-pending, and "
                 "it says so aloud - %s" % first_line(data["answer"], 60))

    # -- (b) an unknown id, with something valid ALREADY pending, so the answer to
    #        "what happened to the slot?" is a fact rather than a coincidence.
    token = "pfhands%d" % (int(time.time()) % 100000)
    status, _, body = post_json("/tools", {"cmd": "propose", "tool": "selftest",
                                           "params": {"token": token}, "door": "curl"},
                                timeout=30, label="POST /tools (propose before unknown)")
    if (as_json(body) or {}).get("pending") is None:
        return FAIL, ["(b) could not get a valid proposal pending first: %s"
                      % first_line(body.decode("utf-8", "replace"))]
    status, _, body = post_json("/tools", {"cmd": "propose", "tool": "send_email_v2",
                                           "params": {"to": "nobody@example.com"},
                                           "door": "curl"},
                                timeout=30, label="POST /tools (unknown tool id)")
    data = as_json(body) or {}
    if status not in (400, 404) or data.get("refused") != "unknown-tool":
        return FAIL, ["(b) the id “send_email_v2” came back %s refused=%r - a tool that "
                      "is not in the registry does not exist, and the nearest name is "
                      "not an answer" % (status, data.get("refused"))]
    if data.get("pending") is not None:
        return FAIL, ["(b) a refusal left something pending, which is the one shape "
                      "this must never have: a later “yes” would confirm it"]
    _, _, body = http_call("GET", "/tools", timeout=20, label="GET /tools (after b)")
    if (as_json(body) or {}).get("pending") is not None:
        return FAIL, ["(b) the server still reports a pending proposal after a refusal"]
    notes.append("(b) an unknown id is refused by name and empties the slot, taking "
                 "the valid proposal that was sitting in it with it")

    # -- (c) a required parameter left out. The refusal has to say WHICH.
    status, _, body = post_json("/tools", {"cmd": "propose", "tool": "send_email",
                                           "params": {"to": "nobody@example.com",
                                                      "subject": "preflight"},
                                           "door": "curl"},
                                timeout=30, label="POST /tools (missing param)")
    data = as_json(body) or {}
    said = str(data.get("answer") or "")
    if status != 400 or data.get("refused") != "missing" or data.get("field") != "body":
        return FAIL, ["(c) send_email without a body came back %s refused=%r field=%r - "
                      "a missing required parameter is a refusal naming the field"
                      % (status, data.get("refused"), data.get("field"))]
    if "body" not in said.lower() or data.get("pending") is not None:
        return FAIL, ["(c) the spoken refusal was %r and pending=%r - it must name the "
                      "field out loud and leave nothing pending"
                      % (first_line(said, 70), data.get("pending"))]
    notes.append("(c) a missing required field is refused by name: %s"
                 % first_line(said, 70))

    # -- (d) the happy path. Baseline taken here, after the refusals above, so the
    #        delta belongs to this run and nothing else.
    before = _ledger_row("selftest")
    status, _, body = post_json("/tools", {"cmd": "propose", "tool": "selftest",
                                           "params": {"token": token}, "door": "curl"},
                                timeout=30, label="POST /tools (propose selftest)")
    data = as_json(body) or {}
    pending = data.get("pending") or {}
    if status != 200 or not data.get("ok") or pending.get("tool") != "selftest":
        return FAIL, ["(d) proposing selftest came back %s %r"
                      % (status, first_line(body.decode("utf-8", "replace")))]
    if pending.get("params") != {"token": token}:
        return FAIL, ["(d) the pending proposal carries %r rather than the validated "
                      "parameters - the page renders this, and a human is about to "
                      "read it" % pending.get("params")]
    if token not in str(pending.get("line") or ""):
        return FAIL, ["(d) the spoken proposal %r does not contain the token the "
                      "registry template says it should - the line must be composed "
                      "from the template, never from model prose"
                      % first_line(pending.get("line"), 70)]
    proposal_id = pending.get("id")
    notes.append("(d) proposal spoken in the registry's words: %s"
                 % first_line(pending["line"], 76))

    # The SPOKEN door, which is the one a harness is least able to fake: the same
    # words a human says into an open microphone, posted to /chat.
    status, _, body = post_json("/chat", {"question": "yes, go ahead",
                                          "session": "preflight-hands"},
                                timeout=90, label="POST /chat (spoken yes)")
    data = as_json(body) or {}
    spoken = str(data.get("answer") or "")
    if status != 200 or not data.get("ok") or data.get("ran") != "selftest":
        return FAIL, ["(d) “yes, go ahead” came back %s ok=%r ran=%r error=%r - the "
                      "spoken door must run the pending proposal and nothing else"
                      % (status, data.get("ok"), data.get("ran"), data.get("error"))]
    if token not in spoken:
        return FAIL, ["(d) the tool ran but the spoken line %r does not carry the token "
                      "the script printed - the script's stdout is the only evidence "
                      "there is" % first_line(spoken, 70)]
    if data.get("pending") is not None:
        return FAIL, ["(d) the slot still holds a proposal after it ran"]
    after = _ledger_row("selftest")
    moved = {k: after[k] - before[k] for k in after if after[k] != before[k]}
    if moved != {"ok": 1}:
        return FAIL, ["(d) the ledger moved %r for selftest; exactly one “ok” and "
                      "nothing else was expected (before %r, after %r)"
                      % (moved, before, after)]
    notes.append("(d) confirmed by voice -> the script's own stdout came back and was "
                 "spoken: %s" % first_line(spoken, 66))
    notes.append("(d) ledger selftest ok %d -> %d, and no other count moved"
                 % (before["ok"], after["ok"]))

    # -- (e) the same word, twice. The second must not be a second run.
    status, _, body = post_json("/execute", {"door": "curl", "id": proposal_id},
                                timeout=30, label="POST /execute (same id twice)")
    data = as_json(body) or {}
    if data.get("ok") or data.get("ran") or status == 200:
        return FAIL, ["(e) confirming the same proposal twice RAN IT AGAIN (%s ran=%r) "
                      "- this is how one calendar entry becomes two"
                      % (status, data.get("ran"))]
    if data.get("refused") not in ("nothing-pending", "busy") and not data.get("lapsed"):
        return FAIL, ["(e) the second confirmation came back %s %r without naming "
                      "itself a refusal or a lapse"
                      % (status, first_line(data.get("answer"), 60))]
    again = _ledger_row("selftest")
    if again != after:
        return FAIL, ["(e) the ledger moved on the second confirmation (%r -> %r), so "
                      "something happened that should not have" % (after, again)]
    status, _, body = post_json("/chat", {"question": "yes", "session": "preflight-hands"},
                                timeout=60, label="POST /chat (yes with nothing pending)")
    data = as_json(body) or {}
    if data.get("ran") or _ledger_row("selftest") != after:
        return FAIL, ["(e) a second spoken “yes” ran something: ran=%r" % data.get("ran")]
    notes.append("(e) the same proposal confirmed twice, at both doors: refused both "
                 "times, and the ledger did not move")

    # -- (f) THE CANARY. Generated from the clock so the literal cannot be in the
    #        source, which is what makes the scan below mean anything. It goes in
    #        send_email's body - a required field the proposal template deliberately
    #        never speaks - and the proposal is then refused, so nothing is sent.
    canary = "zqhandscanary%dqz" % int(time.time() * 1000)
    seeded, unscanned = _disk_hits(canary)
    if seeded:
        return FAIL, ["(f) the canary %s was already on disk in %s before the test "
                      "began, so the scan proves nothing" % (canary, seeded)]
    status, _, body = post_json("/tools",
                                {"cmd": "propose", "tool": "send_email",
                                 "params": {"to": "nobody@example.com",
                                            "subject": "preflight canary",
                                            "body": "do not send this: " + canary},
                                 "door": "curl"},
                                timeout=30, label="POST /tools (canary proposal)")
    data = as_json(body) or {}
    pending = data.get("pending") or {}
    if status != 200 or pending.get("tool") != "send_email":
        return FAIL, ["(f) the canary proposal did not take: %s %r"
                      % (status, first_line(body.decode("utf-8", "replace")))]
    if canary in str(pending.get("line") or ""):
        return FAIL, ["(f) THE CANARY WAS SPOKEN. The proposal template renders a "
                      "parameter the employer never asked to hear read out in a room"]
    if canary not in json.dumps(pending.get("params") or {}):
        return FAIL, ["(f) the pending parameters do not carry what was proposed, so "
                      "the human would be approving something they cannot see"]
    status, _, body = post_json("/tools", {"cmd": "cancel", "door": "curl"}, timeout=30,
                                label="POST /tools (refuse the canary)")
    data = as_json(body) or {}
    if not data.get("ok") or data.get("pending") is not None:
        return FAIL, ["(f) the canary proposal would not cancel: %s"
                      % first_line(body.decode("utf-8", "replace"))]

    # Now look everywhere. On disk first: the ledger, the logs, the notes, the lot.
    hits, unscanned = _disk_hits(canary)
    if hits:
        return FAIL, ["!! THE CANARY REACHED DISK: %s" % ", ".join(hits),
                      "the ledger holds outcomes only - never parameters, never "
                      "bodies, never recipients - and the trace says what happened "
                      "rather than what it was given"]
    # Then in the traffic: every response this run, with the one permitted field -
    # pending.params, which the page must render - taken out first.
    leaked = [label for label, blob in bodies if canary in _scrubbed(blob)]
    if leaked:
        return FAIL, ["!! THE CANARY APPEARED IN A RESPONSE OUTSIDE pending.params: %s"
                      % ", ".join(sorted(set(leaked)))]
    ledger = _ledger_file()
    rows = ledger.get("tools") if isinstance(ledger.get("tools"), dict) else {}
    bad = sorted({k for row in rows.values() if isinstance(row, dict) for k in row}
                 - LEDGER_ROW_KEYS)
    if bad:
        return FAIL, ["the ledger on disk carries keys outside the whitelist (%s), so "
                      "something wrote to it without going through _record()"
                      % ", ".join(bad)]
    refused_now = _ledger_row("send_email")
    notes.append("(f) canary %s: put in send_email's body, refused, then hunted - "
                 "absent from every file under the project root%s and from every one "
                 "of the %d responses this run, save the parameters the page renders "
                 "for the human to read"
                 % (canary, " (%d too large to read)" % unscanned if unscanned else "",
                    len(bodies)))
    notes.append("ledger rows hold exactly the %d whitelisted keys (%s) for %d tool%s; "
                 "send_email stands at ok %d / failed %d / refused %d / lapsed %d and "
                 "has never been given an address to keep"
                 % (len(LEDGER_ROW_KEYS), ", ".join(sorted(LEDGER_ROW_KEYS)), len(rows),
                    "" if len(rows) == 1 else "s", refused_now["ok"],
                    refused_now["failed"], refused_now["refused"],
                    refused_now["lapsed"]))

    # -- (g) and a greeting, which must surface nothing at all. The vocative law sits
    #        above the hands: there is no instruction in "good morning".
    status, _, body = post_json("/chat", {"question": "good morning, Jarvis",
                                          "session": "preflight-hands"},
                                timeout=120, label="POST /chat (greeting, hands)")
    data = as_json(body) or {}
    if data.get("kind") != "chat" or data.get("searched") or data.get("proposed"):
        return FAIL, ["(g) “good morning, Jarvis” came back kind=%r searched=%r "
                      "proposed=%r - a greeting proposes nothing and searches nothing"
                      % (data.get("kind"), data.get("searched"), data.get("proposed"))]
    _, _, body = http_call("GET", "/tools", timeout=20, label="GET /tools (after g)")
    state_now = as_json(body) or {}
    if state_now.get("pending") is not None or state_now.get("busy"):
        return FAIL, ["(g) a greeting left pending=%r busy=%r"
                      % (state_now.get("pending"), state_now.get("busy"))]
    notes.append("(g) a greeting left zero proposals pending and fired zero searches: "
                 "%s" % first_line(data.get("answer"), 66))

    # -- (h) THE SPOKEN DIAL, in four questions, not one of which is allowed to change the
    #        voice. The digest either side is the load-bearing part: "the voice did not
    #        change" would be satisfied by a rewritten file that happened to keep one key,
    #        and this file holds this machine's credentials. Not one byte may move.
    if "set_voice" not in ids:
        return FAIL, ["(h) the registry does not carry set_voice, so the spoken dial has "
                      "no hand behind it: %s" % ", ".join(ids)]
    config_path = os.path.join(ROOT, "config.json")
    try:
        with open(config_path, "rb") as fh:
            cfg_before = fh.read()
    except OSError as exc:
        return FAIL, ["(h) config.json could not be read to take a baseline (%s)" % exc]
    before_digest = hashlib.sha256(cfg_before).hexdigest()[:8]
    # Read the same way the server reads it, fallback included, so "current" here and
    # "current" on the card are the same fact and not two readings of one file.
    voice_before = os.path.basename(str((as_json(cfg_before) or {}).get("voice_model")
                                        or server.DEFAULT_CONFIG["voice_model"]).strip())

    status, _, body = post_json("/tools", {"cmd": "propose", "tool": "set_voice",
                                           "params": {}, "door": "curl"},
                                timeout=30, label="POST /tools (set_voice, no voice)")
    data = as_json(body) or {}
    said = str(data.get("answer") or "")
    if status != 400 or data.get("refused") != "missing" or data.get("field") != "voice":
        return FAIL, ["(h) set_voice with no voice named came back %s refused=%r field=%r "
                      "- a missing required parameter is a refusal naming the field"
                      % (status, data.get("refused"), data.get("field"))]
    if "voice" not in said.lower() or data.get("pending") is not None:
        return FAIL, ["(h) the spoken refusal was %r and pending=%r - it must name the "
                      "field out loud and leave nothing pending"
                      % (first_line(said, 70), data.get("pending"))]
    notes.append("(h) set_voice with no voice is refused by name: %s" % first_line(said, 66))

    # A name that is not a nickname and does not look like a piper id, so the hand takes
    # the "I will not guess at a near one" branch rather than the "missing from this
    # machine" one. Both refuse; only this one has to recite the list.
    nonsense = "brunel"
    voice_before_row = _ledger_row("set_voice")
    status, _, body = post_json("/tools", {"cmd": "propose", "tool": "set_voice",
                                           "params": {"voice": nonsense}, "door": "curl"},
                                timeout=30, label="POST /tools (set_voice, unknown name)")
    data = as_json(body) or {}
    if status != 200 or (data.get("pending") or {}).get("tool") != "set_voice":
        return FAIL, ["(h) proposing set_voice with an unheard-of name did not even reach "
                      "the gate: %s %r"
                      % (status, first_line(body.decode("utf-8", "replace")))]
    status, _, body = post_json("/chat", {"question": "yes, go ahead",
                                          "session": "preflight-hands"},
                                timeout=90, label="POST /chat (spoken yes, unknown voice)")
    data = as_json(body) or {}
    spoken = str(data.get("answer") or "")
    # The proposal gate is ALLOWED to pass this through: a name is not a fact about the
    # disk, and the registry validates a shape. What must not happen is the write. So the
    # refusal wanted here is the HAND's own - a non-zero exit, carried back in the words
    # the script printed - and not a 200 with an accepted voice.
    if data.get("ok") or data.get("ran") or status == 200:
        return FAIL, ["(h) a voice this machine does not have was ACCEPTED: %s ok=%r "
                      "ran=%r - config.json would now name a voice that cannot speak, "
                      "and the machine would come back mute at the next restart"
                      % (status, data.get("ok"), data.get("ran"))]
    if data.get("failed") != "exit-1" or data.get("tool") != "set_voice":
        return FAIL, ["(h) the unknown voice came back %s failed=%r tool=%r - a hand that "
                      "refuses must refuse by exiting non-zero, because exit 0 is the "
                      "only thing that means it happened"
                      % (status, data.get("failed"), data.get("tool"))]
    if data.get("pending") is not None:
        return FAIL, ["(h) the slot still holds the set_voice proposal after it was "
                      "refused - a later “yes” could confirm it"]
    low = spoken.lower()
    if "no voice by that name" not in low or "sir" not in low:
        return FAIL, ["(h) the refusal was %r - an unknown name must say so in words, and "
                      "in this house's voice" % first_line(spoken, 80)]
    if not any(_voice_label(v).lower() in low for v in _installed_voices()):
        return FAIL, ["(h) the refusal %r does not recite what IS installed (%s), so the "
                      "employer is told no and given nowhere to go"
                      % (first_line(spoken, 70), ", ".join(_installed_voices()) or "none")]
    voice_after_row = _ledger_row("set_voice")
    moved = {k: voice_after_row[k] - voice_before_row[k]
             for k in voice_after_row if voice_after_row[k] != voice_before_row[k]}
    if moved != {"failed": 1}:
        return FAIL, ["(h) the ledger moved %r for set_voice; a refused recast is exactly "
                      "one “failed” and no “ok” (before %r, after %r)"
                      % (moved, voice_before_row, voice_after_row)]
    notes.append("(h) an unheard-of voice, confirmed out loud, is refused BY THE HAND and "
                 "the refusal names the installed voices: %s" % first_line(spoken, 66))
    notes.append("(h) and the ledger says so: set_voice failed %d -> %d, ok unmoved at %d"
                 % (voice_before_row["failed"], voice_after_row["failed"],
                    voice_after_row["ok"]))

    # And a real one: proposed, READ BACK - current beside requested, which is the entire
    # point of a card a human is asked to approve - and then cancelled. The voice chosen
    # is deliberately not the one in force, so "current" and "requested" cannot be the
    # same word and a card that simply echoed the request twice would be caught.
    here_now = _installed_voices()
    others = [v for v in here_now if v != voice_before]
    want = others[0] if others else (here_now[0] if here_now else "")
    if not want:
        warnings.append("(h) no voice is installed under voices/, so the PROPOSAL half of "
                        "the spoken dial could not be exercised on this machine; the two "
                        "refusals above were, and nothing was written")
    else:
        status, _, body = post_json("/tools",
                                   {"cmd": "propose", "tool": "set_voice",
                                    "params": {"voice": want}, "door": "curl"},
                                   timeout=30, label="POST /tools (set_voice, real voice)")
        data = as_json(body) or {}
        pending = data.get("pending") or {}
        line = str(pending.get("line") or "")
        params = pending.get("params") or {}
        if status != 200 or pending.get("tool") != "set_voice":
            return FAIL, ["(h) a real, installed voice would not even propose: %s %r"
                          % (status, first_line(body.decode("utf-8", "replace")))]
        if params.get("voice") != want:
            return FAIL, ["(h) the pending parameters do not carry the voice that was "
                          "asked for (%r, wanted %r) - the human approves what they can "
                          "read, so what they read must be what runs"
                          % (params.get("voice"), want)]
        # THE CURRENT VALUE IS THE SERVER'S TO KNOW. It is overwritten from config.json
        # after the tag and before the proposal precisely so that no model can fill it
        # in from memory on a card whose whole job is being believed.
        was_label = _voice_label(voice_before)
        if params.get("current") != was_label:
            return FAIL, ["(h) the card says the current voice is %r when config.json "
                          "says %r - a proposal that misreports what it would replace "
                          "is worse than no proposal"
                          % (params.get("current"), was_label)]
        if was_label not in line or want not in line:
            return FAIL, ["(h) the proposal line %r does not put current (%s) beside "
                          "requested (%s)" % (first_line(line, 80), was_label, want)]
        if "{" in line or "voice" not in line.lower() or "?" not in line:
            return FAIL, ["(h) the proposal %r is not a filled-in question about the "
                          "voice - the line comes from the registry template, never "
                          "from prose" % first_line(line, 80)]
        notes.append("(h) and a real voice proposes in the registry's own words, current "
                     "beside requested: %s" % first_line(line, 90))
        status, _, body = post_json("/tools", {"cmd": "cancel", "door": "curl"}, timeout=30,
                                    label="POST /tools (cancel set_voice)")
        data = as_json(body) or {}
        if not data.get("ok") or data.get("pending") is not None:
            return FAIL, ["(h) the set_voice proposal would not cancel: %s"
                          % first_line(body.decode("utf-8", "replace"))]
        notes.append("(h) then CANCELLED, not confirmed: the slot is empty and %s is "
                     "still the voice" % was_label)

    try:
        with open(config_path, "rb") as fh:
            cfg_after = fh.read()
    except OSError as exc:
        return FAIL, ["(h) config.json could not be read again (%s)" % exc]
    if cfg_after != cfg_before:
        return FAIL, ["!! (h) CONFIG.JSON CHANGED DURING PREFLIGHT (sha256 %s -> %s). "
                      "This file holds this machine's credentials and a harness has no "
                      "business writing to it; the spoken dial is proved by its refusals."
                      % (before_digest, hashlib.sha256(cfg_after).hexdigest()[:8])]
    notes.append("(h) and config.json did not move: %d bytes, sha256 %s before and after, "
                 "voice_model still %r - every gate above refused, so nothing was written"
                 % (len(cfg_after), before_digest, voice_before))

    if warnings:
        return WARN, notes + warnings
    return PASS, notes


def _rebuild_vectors(timeout=420):
    """Run the real build, vectors and all, and hand back (ok, one line about it)."""
    done = _proc.run([sys.executable, os.path.join(ROOT, "build.py")],
                          capture_output=True, text=True, timeout=timeout, cwd=ROOT)
    tail = [ln.strip() for ln in (done.stdout or "").splitlines()
            if "vectors" in ln or "chunk" in ln]
    return done.returncode == 0, (tail[-1] if tail else "build.py said nothing about "
                                                        "vectors")


def check_documents():
    """17. A PDF dropped into archive/ is read, cited by page, and answers a synonym."""
    if not state["up"]:
        return FAIL, ["skipped: the server is not reachable"]

    before = (state.get("health") or {}).get("vectors") or {}
    if not before.get("on"):
        return WARN, ["semantic recall is switched off in config.json "
                      "(vector_recall false), so there is nothing to test here"]
    if not before.get("ready"):
        # The honest outcome on a machine with no ChromaDB or no Ollama: the feature is
        # absent, the keyword brain answered every check above, and that is a warn rather
        # than a failure of this code. Same rule as the checks that need a search key.
        return WARN, ["the vector store is not open: %s" % (before.get("why") or "no store"),
                      "run \"python build.py\" with Ollama running to build it"]

    # ---- the probe document. Page 1 says a thing in words the question will not use;
    # page 2 is a scan, so the same file proves both halves of the citation contract.
    rel = "archive/test_archive.pdf"
    path = os.path.join(ROOT, "archive", "test_archive.pdf")
    archive_existed = os.path.isdir(os.path.join(ROOT, "archive"))
    if os.path.exists(path):
        return FAIL, ["%s already exists; move it aside - this check writes and deletes "
                      "that exact path" % rel]
    os.makedirs(os.path.join(ROOT, "archive"), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(probe_pdf(["The vehicle is crimson, and has been since the day it "
                            "was delivered.", ""]))
    detail = ["wrote %s (%d bytes, page 1 text, page 2 a scan)"
              % (rel, os.path.getsize(path))]

    verdict, notes = PASS, []
    try:
        ok, line = _rebuild_vectors()
        if not ok:
            return FAIL, detail + ["build.py failed, so nothing was indexed: %s" % line]
        detail.append(line)

        # ---- THE SYNONYM. "car" is not in the document and "vehicle" is not in the
        # question, so nothing a keyword index can do will answer this. If it comes back
        # crimson, the meaning search found it.
        status, _, body = post_json("/chat", {"question": "What colour is the car?",
                                             "session": "preflight-documents"},
                                    timeout=180)
        data = as_json(body) or {}
        answer = str(data.get("answer") or "")
        cites = data.get("citations") if isinstance(data.get("citations"), list) else []
        named = [c for c in cites if isinstance(c, dict)
                 and str(c.get("file") or "").endswith("test_archive.pdf")]
        if status != 200 or data.get("error"):
            return FAIL, detail + ["POST /chat failed: %s"
                                   % first_line(data.get("error") or body[:200])]
        if data.get("kind") != "notes":
            return FAIL, detail + ["“What colour is the car?” came back kind=%r "
                                   "searched=%r - the notes door did not open on the "
                                   "document: %s"
                                   % (data.get("kind"), data.get("searched"),
                                      first_line(answer, 70))]
        if not named:
            return FAIL, detail + ["it answered from the notes but cited %r, never the "
                                   "file the answer is in"
                                   % [c.get("label") for c in cites]]
        if not any(w in answer.lower() for w in ("crimson", "red")):
            return FAIL, detail + ["it cited %s and then did not say crimson or red: “%s”"
                                   % (named[0].get("label"), first_line(answer, 88))]
        if not named[0].get("page"):
            # The file is right and the page is missing: a citation that cannot be turned
            # to. Warn rather than fail - the retrieval worked.
            notes.append("but the citation carries no page number")
        detail.append("“What colour is the car?” -> %s · %s"
                      % (named[0].get("label"), first_line(answer, 62)))
        detail.append("cited %s at %.3f, with no web lookup"
                      % (named[0].get("label"), float(named[0].get("score") or 0.0)))

        # ---- THE SCAN, said once and never described. Page 2 has no text in it, and the
        # reply is entitled to say so and forbidden to guess.
        scans = data.get("scanNotes") if isinstance(data.get("scanNotes"), list) else []
        if not any("page 2" in str(s) for s in scans):
            notes.append("but page 2 is a scan and nothing in the reply said so "
                         "(scanNotes=%r)" % scans)
        else:
            detail.append("and about page 2: “%s”" % first_line(scans[0], 74))

        # ---- AND THE GATE STILL OPENS FOR EVERYTHING ELSE. A corpus that now answers
        # more questions must not start answering all of them.
        status, _, body = post_json(
            "/chat", {"question": "What is the population of Reykjavik?",
                      "session": "preflight-documents"}, timeout=180)
        other = as_json(body) or {}
        if status != 200:
            notes.append("the unrelated question returned HTTP %s" % status)
        elif not other.get("searched"):
            verdict = FAIL
            notes.append("“What is the population of Reykjavik?” came back kind=%r with "
                         "no lookup - the web gate did not open: %s"
                         % (other.get("kind"), first_line(other.get("answer"), 60)))
        else:
            detail.append("an unrelated question still opened the web gate (%s -> %s)"
                          % (other.get("searched"), other.get("kind")))
            if other.get("citations"):
                verdict = FAIL
                notes.append("but it also cited %r, which the web answer had no hand in"
                             % [c.get("label") for c in other["citations"]])
    finally:
        # Put the archive back exactly as it was, and rebuild so the store agrees.
        if KEEP_NOTE:
            detail.append("--keep-note: %s left in place; run build.py to drop it" % rel)
        else:
            try:
                os.remove(path)
                if not archive_existed and not os.listdir(os.path.join(ROOT, "archive")):
                    os.rmdir(os.path.join(ROOT, "archive"))
                ok, _line = _rebuild_vectors()
                after = ((as_json(http_call("GET", "/health", timeout=20)[2]) or {})
                         .get("vectors") or {})
                if not ok:
                    notes.append("could not rebuild after removing %s; run build.py" % rel)
                elif after.get("files") == before.get("files"):
                    detail.append("probe document removed, store rebuilt, back to %s "
                                  "file%s" % (before.get("files"),
                                              "" if before.get("files") == 1 else "s"))
                else:
                    notes.append("after cleanup the store holds %s files, not the %s it "
                                 "started with" % (after.get("files"), before.get("files")))
            except Exception as exc:                           # noqa: BLE001
                notes.append("could not clean up %s (%s) - delete it and re-run build.py"
                             % (rel, exc))

    if verdict == PASS and notes:
        return WARN, detail + notes
    return verdict, detail + notes


def check_routing():
    """18. The routing chain: the four classes answer for nothing, and cannot be searched.

    WHAT GOES WRONG HERE IS SILENT AND EXPENSIVE. Every sentence in this check used to work
    and then, one refactor later, did not: "can you listen to me" went to the notes and came
    back with a paragraph about an invoice importer; "yes yes do it galaxy" withdrew the
    offer it was accepting and then searched for the words "yes yes do it". Nothing crashed
    either time. The machine answered, in complete sentences, having spent a retrieval and an
    embedding on a question about itself - so the only cheap early warning is a check that
    watches the CLASS and the COST rather than whether an answer came back.

    routing_proof.mjs is the deep instrument: sixty-five assertions, typed and spoken, on a
    real microphone. It takes minutes and it needs a headed browser. This is the chain either
    side of it, in seconds, and every part of it live:

      (a) the RUNNING server puts the classes above retrieval - route named, lookups nought,
          nodes empty - because a build from before the funnel was reordered answers these
          perfectly well and slowly, and looks exactly like a working server;
      (b) the whole pool of consent words, every one the mandate lists, read by the server's
          own confirmation_in() rather than by a copy of the list;
      (c) the whole pool of class 2 and class 3 sentences, read by protected_answer(), each
          landing in the class it belongs to with a line to say;
      (d) TWO INDEPENDENT DOORS SHUT, not one: the class matches AND substantial_question()
          refuses the same sentence, so even if a class were removed tomorrow the web gate
          would still not open on a sentence spoken TO him rather than about the world;
      (e) and no retrieval reachable from the class path at all, read from the source - the
          one claim here that a passing answer cannot fake;
      (f) and Part B's fork, both ways: an amendment keeps the offer, a change of subject
          releases it. Pure functions, so it costs three calls and no browser - and it is
          the only step here where getting it wrong loses a hand the boss asked for.
    """
    if not state["up"]:
        return FAIL, ["skipped: the server is not reachable"]

    notes, warnings = [], []

    # -- (a) THE RUNNING PROCESS. Each of these is answered from a fixed string or from the
    # manifest, so none of them costs a brain call and the whole step is a few hundred
    # milliseconds. What is being asked is not "can he answer" but "did he answer for free".
    live = [
        ("can you listen to me", "meta", "the ear"),
        ("who are you", "identity", "who he is"),
        ("what's my name", "identity", "whose assistant he is"),
        ("what can you do", "identity", "the manifest"),
    ]
    for question, want_route, about in live:
        status, _, data = post_json("/chat", {"question": question,
                                             "session": "preflight-routing"},
                                    timeout=60, label="chat %s" % question)
        got = as_json(data) or {}
        if status != 200:
            return FAIL, ["POST /chat %r answered %d, so the routing chain cannot be "
                          "measured" % (question, status)]
        if got.get("route") != want_route:
            return FAIL, ["%r is a question about %s and the running server routed it to "
                          "%r, not %r. On this path that means retrieval: the notes were "
                          "asked what his name is." % (question, about,
                                                       got.get("route"), want_route)]
        if got.get("lookups") not in (0, None) or got.get("nodes"):
            return FAIL, ["%r reached class %r but spent %r lookups and lit %d nodes - the "
                          "class answered and something searched anyway"
                          % (question, want_route, got.get("lookups"),
                             len(got.get("nodes") or ()))]
        if not str(got.get("answer") or "").strip():
            return FAIL, ["%r was classed %r and answered with nothing at all"
                          % (question, want_route)]
    notes.append("the running server answers %d class-2 and class-3 sentences by name, "
                 "each at nought lookups and nought nodes" % len(live))

    # -- and CLASS 1 with nothing pending, which is the refusal that must not be searched.
    status, _, data = post_json("/chat", {"question": "yes yes do it galaxy",
                                         "session": "preflight-routing"},
                                timeout=60, label="chat bare confirmation")
    got = as_json(data) or {}
    if status != 409:
        return FAIL, ["a bare confirmation with nothing pending answered %d, not 409: "
                      "consent with nothing to consent to is being treated as a question"
                      % status]
    if got.get("lookups") not in (0, None) or got.get("nodes"):
        return FAIL, ["the refusal for a released confirmation cost %r lookups and %d "
                      "nodes - the words \"yes yes do it\" were put to the notes"
                      % (got.get("lookups"), len(got.get("nodes") or ()))]
    if "pending" not in str(got.get("answer") or "").lower():
        warnings.append("the bare-confirmation refusal does not use the word \"pending\": "
                        "%r" % first_line(got.get("answer"), 60))
    notes.append("a confirmation with nothing pending is refused by name at nought cost")

    # -- (b) THE WHOLE POOL, through the server's own reader. The failure this catches is a
    # pool edited in half: an affirmative added to the docstring and not to the pattern, or a
    # negative that stops being heard. A yes that is not heard as a yes is not a missed
    # feature - it is a hand that does not run when the boss says run it, or worse, a "no"
    # that goes to the notes while the offer stands.
    yeses = ("yes", "yeah", "yep", "yes yes", "ok do it", "do it", "go ahead", "proceed",
             "confirmed", "sure", "please do", "haan yes", "Galaxy, yes please",
             "yes yes do it galaxy", "okay, go ahead.")
    noes = ("no", "no no", "nope", "cancel", "cancel that", "stop", "don't", "leave it",
            "not now", "no thanks galaxy", "No.")
    misheard = [w for w in yeses if server.confirmation_in(w) != "yes"]
    if misheard:
        return FAIL, ["the server does not hear these as consent: %r. Every one is a word "
                      "the boss uses to say yes; each one that is not heard is a hand that "
                      "will not run when he tells it to." % misheard]
    misheard = [w for w in noes if server.confirmation_in(w) != "no"]
    if misheard:
        return FAIL, ["the server does not hear these as a refusal: %r. A \"no\" that is "
                      "not heard is worse than a \"yes\" that is not: the offer stands and "
                      "the refusal gets searched." % misheard]
    # AND THE POOL IS NOT A SIEVE. A pattern widened until everything is a yes would pass
    # both lists above and break the whole of Part B.
    leaks = [w for w in ("what address is it going to", "make it tomorrow instead",
                         "why would you do that", "what is react",
                         "yes, and what is the population of tokyo",
                         "no idea what react is") if server.confirmation_in(w) != ""]
    if leaks:
        return FAIL, ["these are conversation, not consent, and the server hears a word of "
                      "consent in them: %r. A sieve here executes hands the boss was still "
                      "asking questions about." % leaks]
    notes.append("all %d consent words and %d refusals are heard, and %d sentences that "
                 "merely contain one are not"
                 % (len(yeses), len(noes), len(leaks) or 6))

    # -- (c) and (d). Both doors, on the mandate's own sentences. The class must match, and
    # the WEB GATE must independently refuse the same sentence: substantial_question() is
    # what stands between "are you listening" and a search engine, and it has to say no for
    # its own reasons, not because a class happened to catch the sentence first.
    classed = {
        "meta": ("can you listen to me", "are you there", "do you hear me",
                 "hey galaxy are you there", "listen to me", "pay attention",
                 "talk to me", "are you listening"),
        "identity": ("who are you", "what are you", "who am i", "what's my name",
                     "do you know me", "whose assistant are you", "what can you do",
                     "what are your capabilities", "help me"),
    }
    for want, sentences in sorted(classed.items()):
        for sentence in sentences:
            name, payload = server.protected_answer(sentence)
            if name != want:
                return FAIL, ["%r is one of the boss's own sentences and the class reader "
                              "makes it %r, not %r - which sends it down the funnel to the "
                              "notes and the web" % (sentence, name, want)]
            if not str((payload or {}).get("answer") or "").strip():
                return FAIL, ["%r is classed %r with an empty answer" % (sentence, want)]
            if (payload or {}).get("lookups") != 0 or (payload or {}).get("nodes"):
                return FAIL, ["the %r payload for %r does not declare itself free: %r"
                              % (want, sentence, payload)]
    notes.append("all %d class-2 and class-3 sentences from the mandate land in their own "
                 "class, each with a line to say and nought declared cost"
                 % sum(len(v) for v in classed.values()))

    # -- (d) THE SECOND DOOR, and it is a different door than the one above. The mandate's
    # clause is precise and it took a wrong version of this step to notice: "second-person
    # address to the assistant NOT IN CLASS 2 OR 3 never opens it". The classes catch the
    # sentences somebody thought to list; this clause catches the ones nobody did, which is
    # why it is the one worth a check. The first draft here demanded that the web gate also
    # refuse every listed class sentence - and it failed honestly, on "what's my name", which
    # IS a real question, just not one about the world. Testing a class sentence against this
    # clause tests nothing anyway: class 3 answered it two branches earlier.
    # NOT IN THIS LIST, and the reason is the distinction the whole clause turns on: "talk
    # me through it" reaches the web on a thin corpus, and that is RIGHT. It is an imperative
    # about a subject - the antecedent - not a question about him, and "talk me through
    # React" should absolutely open the door. Being addressed to him is not the same as being
    # about him, and a check that confused the two would demand the web gate be welded shut.
    unlisted = ("could you water the ferns on the landing for me",
                "can you give me a hand with this",
                "would you mind having a look at that for me",
                "can you sort that out for me",
                "are you any good at this sort of thing",
                "do you think you could handle that")
    for sentence in unlisted:
        if server.protected_answer(sentence)[0] is not None:
            warnings.append("%r was meant to be OUTSIDE the classes and one of them now "
                            "catches it, so it no longer tests the web gate" % sentence)
            continue
        if not server.spoken_to_him(sentence):
            return FAIL, ["%r is addressed to him in the second person and is in no "
                          "protected class, and spoken_to_him() does not recognise it. On "
                          "a thin corpus that sentence goes to a search engine: the boss "
                          "asks his assistant for a hand and a web page answers." % sentence]
        if server.web_intent(sentence, 0.0, "", True):
            return FAIL, ["%r opens the web gate (%r) though it is spoken TO him rather "
                          "than about the world - the clause that is supposed to narrow "
                          "\"thin\" is not narrowing it"
                          % (sentence, server.web_intent(sentence, 0.0, "", True))]
    notes.append("%d sentences addressed to him that no class lists are recognised as "
                 "spoken to him, and the web gate refuses every one at nought confidence - "
                 "the clause that catches what nobody thought to list" % len(unlisted))
    # AND THE GATE STILL OPENS WHEN IT SHOULD. A clause narrowed until nothing searches
    # would pass everything above and quietly cost the boss the live web.
    for sentence in ("what is the population of tokyo", "what is react"):
        if not server.web_intent(sentence, 0.0, "", True):
            return FAIL, ["%r is a question about the world at nought confidence and the "
                          "web gate stays shut: the narrowing clauses have been widened "
                          "until the live web is unreachable" % sentence]
    notes.append("and a real question about the world still opens it, so the narrowing is "
                 "narrowing rather than closing")
    if set(classed) - set(server.PROTECTED_CLASSES):
        return FAIL, ["protected_answer() returns classes that PROTECTED_CLASSES does not "
                      "list: %r" % sorted(set(classed) - set(server.PROTECTED_CLASSES))]

    # -- (e) NO RETRIEVAL REACHABLE FROM THE CLASS PATH, read from the source rather than
    # inferred from a cheap answer. "lookups: 0" is a number the same function writes about
    # itself; this is the only claim in the check that a working-looking answer cannot fake.
    # PARSED, NOT GREPPED. The first version of this step searched the text for a call and
    # failed on protected_answer's own DOCSTRING, which mentions answer_question() in the
    # course of explaining that class 4 is somebody else's business. Explaining the rule must
    # never break the test, so the calls are taken from the syntax tree and the prose is
    # invisible to it - the same reason name_sweep.py exists.
    forbidden = ("search_notes", "ensure_index", "web_lookup", "web_fetch", "embed",
                 "store_query", "answer_question", "call_model")
    try:
        source = textwrap.dedent(inspect.getsource(server.protected_answer))
        tree = ast.parse(source)
    except (OSError, TypeError, SyntaxError) as exc:
        warnings.append("cannot parse protected_answer's source (%s), so step (e) is "
                        "unproved" % exc)
    else:
        called = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                fn = node.func
                called.add(getattr(fn, "id", None) or getattr(fn, "attr", None) or "")
        reached = sorted(called & set(forbidden))
        if reached:
            return FAIL, ["protected_answer() calls %r. The four classes are supposed to "
                          "cost nothing by construction, not by luck, and a retrieval on "
                          "this path is paid on every \"are you there\"" % reached]
        notes.append("protected_answer() reaches no retrieval of any kind: proved from its "
                     "source, not from its own report of its cost")

    # -- (f) PART B'S OWN FORK, which is the one door in the chain that decides whether an
    # offer LIVES. about_the_proposal() sends a message either to the brain with the offer in
    # front of it, or over the withdrawal, and both mistakes are silent: hold a change of
    # subject and the offer is neither done nor released and the new question is answered as
    # a remark about a reminder; release an amendment and the correction composes a second
    # proposal from scratch while the first one disappears.
    #
    # FAILURE MODE THIS CATCHES, and it was live until today: the amend door tested for the
    # bare verb "say" anywhere in the sentence, so "what do my notes say about coffee" asked
    # over a standing calendar proposal was read as an amendment to it. tools_live found it
    # end to end - it took a real browser, a real hand and ninety seconds. Here it is three
    # function calls, because the whole fork is pure and needs neither.
    fork = {
        # AMENDMENTS. Each is a correction to something already on the card.
        True: ("say it warmer", "just say sorry at the end", "make it tomorrow",
               "send it to bob instead", "add a line about the invoice",
               "actually, seven rather than six",
               # AND POINTED QUESTIONS, which are the other half of "about the offer".
               "what address is it going to", "why that time", "is that going to bob?"),
        # CHANGES OF SUBJECT. Every one is a genuine new request, and each contains a word
        # the amend door has reached for at some point in its life.
        False: ("what do my notes say about coffee", "what does the weather report say",
                "what do the notes say about the invoice importer", "what is react",
                "what is the population of tokyo"),
    }
    pending = {"id": "preflight", "tool": "add_calendar_event", "params": {},
               "fields": [], "line": "Write something into the calendar - your word?"}
    for want, sentences in fork.items():
        for sentence in sentences:
            if server.about_the_proposal(sentence, pending) is not want:
                return FAIL, [
                    "%r is %s and Part B's fork says the opposite. %s"
                    % (sentence,
                       "about the offer" if want else "a change of subject",
                       "An amendment read as a new request drops the offer he was "
                       "correcting." if want else
                       "A change of subject read as an amendment leaves the offer "
                       "standing, never speaks the withdrawal, and answers his question "
                       "as a remark about the offer.")]
    notes.append("Part B's fork holds %d amendments and pointed questions over the offer and "
                 "lets %d changes of subject withdraw it - the two mistakes that are silent "
                 "either way" % (len(fork[True]), len(fork[False])))
    # AND NOTHING IS ABOUT AN OFFER THAT IS NOT THERE: with no slot, the fork must be false
    # for every sentence, or a withdrawal line gets spoken over an ordinary question.
    held = [s for group in fork.values() for s in group
            if server.about_the_proposal(s, None)]
    if held:
        return FAIL, ["with nothing pending, Part B's fork still calls these talk about an "
                      "offer: %r" % held]

    if warnings:
        return WARN, notes + warnings
    return PASS, notes


def check_lock():
    """19. The lock chain: the card can say why, and the two gates ask in one voice.

    THE TEETH THEMSELVES ARE NOT PROVED HERE, and the reason is in the feature: a drift
    off the locked TAB is only visible to a watcher attached to a real browser on a real
    debugging port, and proving it means relaunching Chrome. lock_proof.mjs does exactly
    that, on the launcher's own profile, and it closes the boss's browser to do it -
    which is not something preflight may do to a machine somebody is working on. So this
    check takes the chain either side of the teeth, all of it live or off the files that
    are actually loaded:

      (a) the RUNNING server publishes the two keys the card needs;
      (b) every reason the session can give has English to be said in - both ways round,
          because the silent half is the dangerous one;
      (c) the card has somewhere to put it, and the pill knows to hide it;
      (d) the two hands are gated, parameterless, and ask in the session's own words;
      (e) each hand's script really does the thing its sentence promises;
      (f) a summon with nothing locked refuses in a sentence rather than moving a window;
      (g) the locked-tab callouts name no site, ever.
    """
    if not state["up"]:
        return FAIL, ["skipped: the server is not reachable"]

    notes, warnings = [], []

    # -- (a) the running process, not the file on disk. Every claim below about the card
    # is worthless if the server answering 4700 is a copy from before the card had a line
    # to put a tab title on - and that failure looks exactly like a working session.
    live = _focus_now()
    for key in ("lockedTab", "tabLockWhy"):
        if key not in live:
            return FAIL, ["GET /focus does not send %r: the server answering %d is "
                          "running a build from before the tab lock could explain "
                          "itself. Restart server.py." % (key, server.PORT)]
        if key not in focus.PUBLIC_KEYS:
            return FAIL, ["%r reaches the browser but is not in focus.PUBLIC_KEYS, so "
                          "nothing polices what it carries" % key]
    if live.get("state") in ("arming", "running", "paused"):
        warnings.append("a focus session is running, so steps (a) and (f) read ITS state "
                        "rather than a clean one; the rest is unaffected")
    else:
        if live.get("lockedTab") != "":
            return FAIL, ["no session is running and GET /focus still names a locked "
                          "tab (%r) - a title that outlived its watcher"
                          % live.get("lockedTab")]
        notes.append("GET /focus carries lockedTab and tabLockWhy, both empty with no "
                     "session running")
    if live.get("tabLockWhy") not in focus.TAB_LOCK_WHY:
        return FAIL, ["tabLockWhy is %r, which is not one of the %d words the card knows"
                      % (live.get("tabLockWhy"), len(focus.TAB_LOCK_WHY))]

    # -- (b) THE SILENT DEGRADATION CHECK, which is what this whole Part was written
    # against. focus.py sends one word; the viewer turns it into English. Add a word on
    # the Python side and forget the other half and the card renders nothing at all: the
    # tab lock is off, the boss is told nothing, and every test still passes.
    try:
        with open(os.path.join(ROOT, "viewer", "index.html"), encoding="utf-8") as fh:
            viewer = fh.read()
    except OSError as exc:
        return FAIL, ["cannot read viewer/index.html: %s" % exc]
    block = re.search(r"const FX_LOCK_WHY\s*=\s*\{(.*?)\};", viewer, re.S)
    if not block:
        return FAIL, ["viewer/index.html has no FX_LOCK_WHY, so tabLockWhy arrives at "
                      "the card and is thrown away"]
    rendered = set(re.findall(r"(\w+)\s*:", block.group(1)))
    reasons = set(focus.TAB_LOCK_WHY) - {""}
    unsaid = sorted(reasons - rendered)
    orphan = sorted(rendered - reasons)
    if unsaid:
        return FAIL, ["the session can set tabLockWhy=%s and the card has no English "
                      "for it, so it would say nothing: tab-lock silently off, which is "
                      "the one outcome this feature exists to remove" % unsaid]
    if orphan:
        warnings.append("the card renders %s, which focus.TAB_LOCK_WHY cannot produce - "
                        "dead prose" % orphan)
    if "" in rendered:
        warnings.append("FX_LOCK_WHY has an entry for the empty reason; \"\" means "
                        "there is nothing to explain and must render as nothing")
    notes.append("all %d reasons the session can give have English on the card: %s"
                 % (len(reasons), ", ".join(sorted(reasons))))

    # -- (c) somewhere to put it. A line the pill does not hide is a line that pushes the
    # 2-row PiP card out of shape; a line with no class rule never appears at all.
    for needle, why in (
            ('<div id="focus-locked">', "the card has no element for the locked tab"),
            ("#focus-locked.on,#focus-locked.off{display:block}",
             "the locked line has no rule that shows it, so it stays display:none"),
            ("#focuscard.pill #focus-locked",
             "the pill does not hide the locked line, so the two-row PiP card grows a "
             "third row"),
            ("'#focus-locked{", "the desk stylesheet says nothing about the locked line")):
        if needle not in viewer:
            return FAIL, ["%s (looked for %r)" % (why, needle)]
    notes.append("the card has #focus-locked, an .on/.off rule that shows it, a pill rule "
                 "that hides it and a desk rule that sizes it")

    # -- (d) the two hands. params [] is not tidiness: a summon with a target parameter is
    # a summon that can be pointed somewhere the boss never locked, and the proposal being
    # the session's own sentence is what stops the card asking one thing while the hand
    # does another.
    try:
        with open(os.path.join(ROOT, "tools", "registry.json"), encoding="utf-8") as fh:
            entries = (json.load(fh) or {}).get("tools") or []
    except (OSError, ValueError) as exc:
        return FAIL, ["cannot read tools/registry.json: %s" % exc]
    by_id = {str(e.get("id")): e for e in entries if isinstance(e, dict)}
    for hand_id, line_key in (("relaunch_chrome", "ask_relaunch"),
                              ("summon_tab", "ask_summon")):
        entry = by_id.get(hand_id)
        if not entry:
            return FAIL, ["tools/registry.json holds no %r, so the session's gated offer "
                          "has nothing to offer" % hand_id]
        if entry.get("params"):
            return FAIL, ["%s takes parameters %r - the locked tab lives in the session "
                          "and must never travel over the wire to get back to it"
                          % (hand_id, [p.get("name") for p in entry["params"]])]
        want = focus.LINES[line_key]
        if str(entry.get("proposal") or "") != want:
            return FAIL, ["%s proposes %r and the session says %r - the card would ask "
                          "one question and the hand would answer another"
                          % (hand_id, first_line(entry.get("proposal"), 60),
                             first_line(want, 60))]
        script = os.path.join(ROOT, "tools", str(entry.get("script") or ""))
        if not os.path.exists(script):
            return FAIL, ["%s points at tools/%s, which does not exist"
                          % (hand_id, entry.get("script"))]
    notes.append("relaunch_chrome and summon_tab are both gated, take no parameters, and "
                 "propose in the session's own words")

    # -- (e) and each script does what its sentence promises. Read, not run: running the
    # first one closes the browser you are reading this in.
    promises = (("relaunch_chrome.py", ("launch-chrome.ps1", "--remote-debugging-port"),
                 "the hand that offers to open the debugging port"),
                ("summon_tab.py", ('"cmd": "summon"', "127.0.0.1"),
                 "the hand that offers to bring you back"))
    for name, needles, what in promises:
        try:
            with open(os.path.join(ROOT, "tools", name), encoding="utf-8") as fh:
                text = fh.read()
        except OSError as exc:
            return FAIL, ["cannot read tools/%s: %s" % (name, exc)]
        missing = [n for n in needles if n not in text]
        if missing:
            return FAIL, ["%s does not mention %s, so its own proposal is a promise it "
                          "may not keep" % (what, missing)]
    notes.append("relaunch_chrome.py goes through launch-chrome.ps1 with the debugging "
                 "port; summon_tab.py asks the session on 127.0.0.1 and nothing else")

    # -- (f) THE REFUSAL, live. A hand that reports success off an HTTP status would pass
    # every check above and move somebody's window on the strength of nothing.
    status, _, body = post_json("/focus", {"cmd": "summon", "source": "preflight"},
                               timeout=20, label="POST /focus summon")
    said = as_json(body) or {}
    if status != 200:
        return FAIL, notes + ["POST /focus {cmd:summon} returned HTTP %s" % status]
    if live.get("state") in ("arming", "running", "paused") and live.get("lockedTab"):
        # Somebody's real session has a real lock; it may well have brought them back,
        # which is correct behaviour and not something to assert a refusal against.
        warnings.append("a live session holds a lock, so the summon was answered for "
                        "real (%s) rather than refused" % said.get("summoned"))
    elif said.get("summoned") is not False:
        return FAIL, notes + ["a summon with nothing locked came back summoned=%r: it "
                              "did something, or it claims it did"
                              % said.get("summoned")]
    elif str(said.get("answer") or "").strip() != focus.LINES["summon_none"]:
        return FAIL, notes + ["a summon with nothing locked refused in the wrong words: "
                              "%r" % first_line(said.get("answer"), 70)]
    else:
        notes.append("a summon with nothing locked refuses in a sentence: “%s”"
                     % focus.LINES["summon_none"])

    # -- (g) the nameless pool. The drift callout for a LOCKED TAB is the one callout said
    # while the boss is looking at a site he did not mean to be on, and it must not read
    # that site out: the named pools are for the application-level lock, where he chose
    # the name himself.
    tiers = sorted(focus.CALLOUTS_LOCKED)
    for tier in tiers:
        pool = focus.CALLOUTS_LOCKED[tier]
        if len(pool) < 2:
            return FAIL, notes + ["the tier %s locked-tab pool holds %d line(s), so the "
                                  "same sentence comes back every drift" % (tier, len(pool))]
        for text in pool:
            blanks = set(re.findall(r"\{(\w+)\}", text))
            if blanks - {"drifts", "seconds", "minutes"}:
                return FAIL, notes + ["a locked-tab callout carries %s: %r - that pool is "
                                      "said about a site the boss did not choose and may "
                                      "name nothing" % (sorted(blanks), text)]
            if text in focus.NAMED_LINES:
                return FAIL, notes + ["a locked-tab callout is also in NAMED_LINES, so "
                                      "the scrubber will treat it as naming a place: %r"
                                      % text]
            if text not in focus.LINE_REGISTRY:
                return FAIL, notes + ["a locked-tab callout is outside LINE_REGISTRY, so "
                                      "nothing audits it: %r" % text]
    notes.append("the %d locked-tab tiers hold %d nameless lines between them, all inside "
                 "LINE_REGISTRY"
                 % (len(tiers), sum(len(focus.CALLOUTS_LOCKED[t]) for t in tiers)))

    proof = os.path.join(ROOT, "lock_proof.mjs")
    notes.append("the teeth themselves - drift inside %.1fs, one callout, the resume, the "
                 "summon - are proved by lock_proof.mjs%s, which relaunches Chrome and so "
                 "is never run from preflight"
                 % (focus.LOCK_GRACE_MS / 1000.0 + 1.1,
                    "" if os.path.exists(proof) else " (MISSING)"))
    if not os.path.exists(proof):
        warnings.append("lock_proof.mjs is missing, so nothing in this repository proves "
                        "the watcher notices anything")

    if warnings:
        return WARN, notes + warnings
    return PASS, notes


# ------------------------------------------------------------------ 20. the Scribe chain

SCRIBE_LINE = ("The quarterly review is on Thursday at ten. We agreed to send the deck "
               "by Wednesday evening.")
# The words asserted, and "ten" is deliberately not among them: base.en writes it "10",
# which is correct, and an assertion that broke on it would be testing spelling.
SCRIBE_WORDS = ("quarterly", "thursday", "wednesday")
AUDIO_SUFFIX = (".wav", ".webm", ".ogg", ".mp3", ".m4a", ".opus", ".pcm", ".raw")
# say-cache/ IS EXCLUDED, and the exclusion is stated out loud rather than buried, because
# an exemption nobody can see is how a privacy sweep stops meaning anything. It holds the
# speech this machine PRODUCES - piper's output, keyed by the sentence the server spoke -
# which is the opposite direction of travel from a captured meeting, and (b) below puts a
# file in it deliberately by asking /say for the fixture. Nothing else is exempt.
SCRIBE_SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv", "_runs", "say-cache"}


def _audio_on_disk():
    """Every audio-looking file under the project root, with its size. The privacy law
    says no audio byte reaches a disk, and the only way to assert that from outside the
    process making the promise is to photograph the tree twice."""
    found = {}
    for here, dirs, files in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in SCRIBE_SKIP_DIRS]
        for name in files:
            if name.lower().endswith(AUDIO_SUFFIX):
                path = os.path.join(here, name)
                try:
                    found[path] = os.path.getsize(path)
                except OSError:
                    pass
    return found


def _multipart(parts):
    """(boundary, body) for parts of (name, filename|None, content_type|None, bytes).

    Written out by hand because that is what the page's FormData puts on the wire, and
    this check is about the server reading a real multipart body rather than about
    urllib's opinion of one.
    """
    boundary = "----preflightScribe%s" % hashlib.sha256(
        ("%f" % time.time()).encode()).hexdigest()[:20]
    buf = bytearray()
    for name, filename, ctype, data in parts:
        buf += b"--%s\r\n" % boundary.encode("ascii")
        disp = 'form-data; name="%s"' % name
        if filename:
            disp += '; filename="%s"' % filename
        buf += b"Content-Disposition: %s\r\n" % disp.encode("ascii")
        if ctype:
            buf += b"Content-Type: %s\r\n" % ctype.encode("ascii")
        buf += b"\r\n" + data + b"\r\n"
    buf += b"--%s--\r\n" % boundary.encode("ascii")
    return boundary, bytes(buf)


def _post_chunk(parts, timeout=120, label=None):
    boundary, body = _multipart(parts)
    return http_call("POST", "/scribe/transcribe", body,
                     {"Content-Type": "multipart/form-data; boundary=%s" % boundary,
                      "Content-Length": str(len(body))}, timeout, label)


def _wav16k(raw):
    """A piper WAV in, a 16 kHz mono 16-bit WAV out - the exact shape the page posts.

    Resampled here rather than posted as-is because the page's AudioWorklet hands the
    server 16 kHz mono and this check is worth nothing if it proves a path the page never
    takes. Linear interpolation, not sample dropping: taking every other sample folds
    everything above 8 kHz back down into the speech band as aliasing, and the difference
    it makes is the difference between "the quarterly review" and "the quarter of you".
    audioop would have done this in one call and was removed in Python 3.13.
    """
    import wave
    import struct
    import io
    with wave.open(io.BytesIO(raw), "rb") as src:
        chans, width, rate, frames = (src.getnchannels(), src.getsampwidth(),
                                      src.getframerate(), src.getnframes())
        if width != 2:
            return None, "the voice returned %d-bit audio; this expects 16" % (width * 8)
        pcm = src.readframes(frames)
    mono = struct.unpack("<%dh" % (len(pcm) // 2), pcm)
    if chans > 1:
        mono = [sum(mono[i:i + chans]) // chans for i in range(0, len(mono), chans)]
    out_rate, n = 16000, len(mono)
    m = max(1, int(n * out_rate / float(rate)))
    res = []
    for i in range(m):
        at = i * rate / float(out_rate)
        a = int(at)
        b = min(n - 1, a + 1)
        t = at - a
        res.append(int(round(mono[a] * (1 - t) + mono[b] * t)))
    body = struct.pack("<%dh" % len(res), *res)
    head = (b"RIFF" + struct.pack("<I", 36 + len(body)) + b"WAVEfmt " +
            struct.pack("<IHHIIHH", 16, 1, 1, out_rate, out_rate * 2, 2, 16) +
            b"data" + struct.pack("<I", len(body)))
    return head + body, ""


def _silence16k(seconds=3):
    import struct
    n = int(16000 * seconds)
    body = b"\x00\x00" * n
    head = (b"RIFF" + struct.pack("<I", 36 + len(body)) + b"WAVEfmt " +
            struct.pack("<IHHIIHH", 16, 1, 1, 16000, 32000, 2, 16) +
            b"data" + struct.pack("<I", len(body)))
    return head + body


def _run_minutes_hand(params, timeout=20):
    """tools/save_minutes.py, run the way hands.py runs it: stdin in, one line out.

    _proc.run and not subprocess.run, because check 21 parses THIS file too and a bare
    spawn here would be a real failure in a real file - the audit does not have a category
    for "but it is only the preflight".
    """
    script = os.path.join(ROOT, "tools", "save_minutes.py")
    done = _proc.run([sys.executable, script], input=json.dumps(params).encode("utf-8"),
                     stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
    return done.returncode, done.stdout.decode("ascii", "replace").strip()


def check_scribe():
    """20. A meeting is heard, minuted, and written only when somebody says yes.

    The Scribe is three routes, one script and a promise, and the promise is the part a
    test has to work hardest at: audio bytes never reach a disk. Everything below is live
    against the running server, and the audio under test is real speech - piper's, fetched
    from this machine's own /say - because a synthesised tone transcribes to nothing and
    would prove only that the plumbing returns 200.

      (a) THE GATE IS A FACT. /health carries the scribe block: whether faster-whisper
          imported, the model, the device, the compute type, and the two privacy booleans.
          The page disables its organ off this, so a block that lies here is a picker
          opened on a machine with nowhere to send the audio.
      (b) THE KNOWN SENTENCE, through the shape the page really posts - 16 kHz mono
          16-bit WAV, multipart, a part named "audio". The words must come back. This is
          the only assertion in this file that proves the model is loaded and working
          rather than merely importable.
      (c) SILENCE IS NOT AN ERROR. Three seconds of digital silence must come back as a
          clean empty answer, because vad_filter drops it and a meeting is mostly pauses.
          A 4xx or a 500 here would close a working panel over a working microphone.
      (d) THE THREE WAYS A CHUNK CAN BE WRONG: no multipart at all, a part under the wrong
          name, and bytes that are not audio. The first two are 400s that name the fix;
          the third is a 200 carrying ok:false ON PURPOSE - one skipped three seconds of a
          meeting that is otherwise still running is not a broken session.
      (e) THE MINUTES ARE DRAFTED, NOT WRITTEN. /scribe/minutes returns four headings and
          writes nothing: notes/ is digested before and after. An empty transcript is
          refused in the mandate's own words, a body that is not JSON is refused, and a
          title carrying ..\\..\\ comes back as a NAME rather than a path.
      (f) THE HAND'S OWN REFUSALS, run directly on tools/save_minutes.py: no minutes, a
          title that would escape notes/, and a file that already exists without
          `overwrite`. Each must exit 1 and leave the filesystem where it found it. Then
          one real write, read back, and removed - this check leaves nothing behind.
      (g) AND THE PRIVACY LAW, MEASURED. Every audio-looking file under the project root
          is listed before and after. Not one may appear, and none may grow.

    The browser half - the picker, the worklet, the panel, the organ, the three seals -
    is scribe_proof.mjs's, which drives a real getDisplayMedia and cannot run from here.
    """
    notes, warnings = [], []

    # -- (a) the gate.
    status, _, body = http_call("GET", "/health", timeout=20, label="GET /health (scribe)")
    block = (as_json(body) or {}).get("scribe")
    if status != 200 or not isinstance(block, dict):
        return FAIL, ["/health came back %s with no scribe block - the page gates its "
                      "organ on this and would have nothing to gate on" % status]
    if not block.get("installed"):
        return FAIL, ["the transcriber is offline, so the Scribe chain is dead: %s"
                      % (block.get("why") or "no reason given")]
    for key, want in (("model", "base.en"), ("device", "cpu"), ("computeType", "int8")):
        if block.get(key) != want:
            warnings.append("(a) /health says %s=%r and the specification says %r"
                            % (key, block.get(key), want))
    if block.get("keepsAudio") is not False or block.get("keepsText") is not False:
        return FAIL, ["(a) /health publishes keepsAudio=%r keepsText=%r - the privacy law "
                      "is the one claim this feature cannot be wrong about"
                      % (block.get("keepsAudio"), block.get("keepsText"))]
    notes.append("(a) the transcriber is up: %s on %s/%s, %d thread%s, loaded in %dms - "
                 "keepsAudio false, keepsText false, chunk ceiling %dMB"
                 % (block.get("model"), block.get("device"), block.get("computeType"),
                    block.get("cpuThreads") or 0,
                    "" if block.get("cpuThreads") == 1 else "s",
                    block.get("loadMs") or 0,
                    (block.get("maxChunkBytes") or 0) // (1024 * 1024)))
    chunks_before = block.get("chunks") or 0
    audio_before = _audio_on_disk()

    # -- (b) the known sentence. piper first, because there is no other source of speech
    #        on this machine and a tone would prove nothing.
    status, head, raw = post_json("/say", {"text": SCRIBE_LINE}, timeout=120,
                                 label="POST /say (the Scribe fixture)")
    if status != 200 or not head.get("content-type", "").startswith("audio/"):
        return WARN, notes + ["(b) /say answered %s %s, so there is no speech to transcribe "
                              "and the model could not be exercised"
                              % (status, head.get("content-type"))]
    chunk, why = _wav16k(raw)
    if chunk is None:
        return WARN, notes + ["(b) the fixture could not be resampled: %s" % why]
    notes.append("(b) the fixture: %d bytes of piper speech resampled to 16 kHz mono "
                 "16-bit - “%s”" % (len(chunk), SCRIBE_LINE))
    status, _, body = _post_chunk(
        [("seq", None, None, b"1"), ("audio", "chunk-1.wav", "audio/wav", chunk)],
        label="POST /scribe/transcribe (the known sentence)")
    data = as_json(body) or {}
    if status != 200 or not data.get("ok"):
        return FAIL, notes + ["(b) /scribe/transcribe answered %s %r on a real WAV - the "
                              "whole feature is this one call"
                              % (status, first_line(data.get("error") or body))]
    heard = str(data.get("text") or "")
    missing = [w for w in SCRIBE_WORDS if w not in heard.lower()]
    if missing:
        return FAIL, notes + ["(b) the transcriber heard %r and did not return %s - the "
                              "model answered but not about this audio"
                              % (first_line(heard), ", ".join(missing))]
    for field in ("start", "end", "language"):
        if field not in data:
            return FAIL, notes + ["(b) the answer is missing %r; the mandate asks for "
                                  "text, start, end and language" % field]
    notes.append("(b) heard back in %dms over %.2fs of audio [%s]: “%s”"
                 % (data.get("tookMs") or 0, data.get("durationS") or 0,
                    data.get("language"), first_line(heard)))

    # -- (c) silence. A meeting is mostly pauses and none of them is an error.
    status, _, body = _post_chunk(
        [("seq", None, None, b"2"),
         ("audio", "chunk-2.wav", "audio/wav", _silence16k(3))],
        label="POST /scribe/transcribe (three seconds of silence)")
    data = as_json(body) or {}
    if status != 200:
        return FAIL, notes + ["(c) three seconds of silence answered %s - a pause in a "
                              "meeting must not read to the page as a broken session"
                              % status]
    if str(data.get("text") or "").strip():
        warnings.append("(c) silence transcribed as %r, which means the VAD is not "
                        "dropping it and the panel will fill with inventions"
                        % first_line(data.get("text")))
    else:
        notes.append("(c) three seconds of silence: 200, no words, no error - vad_filter "
                     "is doing its job and a pause costs nothing")

    # -- (d) the three ways a chunk can be wrong.
    status, _, body = http_call(
        "POST", "/scribe/transcribe", b'{"audio":"not multipart"}',
        {"Content-Type": "application/json", "Content-Length": "25"}, 30,
        label="POST /scribe/transcribe (not multipart)")
    data = as_json(body) or {}
    if status != 400 or not data.get("error"):
        return FAIL, notes + ["(d) a JSON body was answered %s %r and should be a named "
                              "400" % (status, first_line(body))]
    status, _, body = _post_chunk(
        [("sound", "chunk.wav", "audio/wav", _silence16k(1))],
        label="POST /scribe/transcribe (the part is misnamed)")
    data = as_json(body) or {}
    if status != 400 or "audio" not in str(data.get("error") or ""):
        return FAIL, notes + ["(d) a part named \"sound\" was answered %s %r; the refusal "
                              "has to name the part it wanted"
                              % (status, first_line(data.get("error") or body))]
    named400 = first_line(data.get("error"))
    status, _, body = _post_chunk(
        [("seq", None, None, b"3"),
         ("audio", "chunk-3.wav", "audio/wav", b"this is not a wave file, sir" * 40)],
        label="POST /scribe/transcribe (bytes that are not audio)")
    data = as_json(body) or {}
    if status != 200 or data.get("ok") is not False or not data.get("error"):
        return FAIL, notes + ["(d) undecodable bytes were answered %s ok=%r - this has to "
                              "be a 200 carrying ok:false, because one unreadable three "
                              "seconds is not a broken meeting"
                              % (status, data.get("ok"))]
    notes.append("(d) the three wrong chunks: a JSON body is a 400, a misnamed part is "
                 "“%s”, and undecodable bytes are a 200 with ok:false "
                 "(“%s”) so the meeting keeps running"
                 % (named400, first_line(data.get("error"), 52)))

    # -- (e) the minutes are drafted and nothing is written.
    notes_dir = os.path.join(ROOT, "notes")
    before = sorted(os.listdir(notes_dir)) if os.path.isdir(notes_dir) else []
    status, _, body = post_json("/scribe/minutes", {"transcript": "  "}, timeout=30,
                               label="POST /scribe/minutes (nothing said)")
    data = as_json(body) or {}
    if status != 400 or data.get("error") != "There is nothing to save, Addi.":
        return FAIL, notes + ["(e) an empty transcript was answered %s %r and the mandate "
                              "asks for “There is nothing to save, Addi.”"
                              % (status, first_line(data.get("error") or body))]
    status, _, body = http_call("POST", "/scribe/minutes", b"transcript=hello",
                                {"Content-Type": "application/x-www-form-urlencoded",
                                 "Content-Length": "16"}, 30,
                                label="POST /scribe/minutes (not JSON)")
    if status != 400:
        return FAIL, notes + ["(e) a form-encoded body was answered %s and should be a "
                              "named 400" % status]
    transcript = (heard + " " + heard + " Addi asked for the deck before Wednesday and "
                  "the review was confirmed for Thursday morning.")
    status, _, body = post_json(
        "/scribe/minutes", {"transcript": transcript, "title": "../../escaped by me"},
        timeout=180, label="POST /scribe/minutes (a real draft)")
    data = as_json(body) or {}
    if status != 200 or not data.get("minutes"):
        return FAIL, notes + ["(e) /scribe/minutes answered %s %r on a real transcript"
                              % (status, first_line(data.get("error") or body))]
    title = str(data.get("title") or "")
    if "/" in title or "\\" in title or ".." in title:
        return FAIL, notes + ["(e) the title came back as %r - a title becomes a filename "
                              "and this one is a path" % title]
    drafted = str(data.get("minutes"))
    heads = [h for h in ("## Attendees", "## Key Decisions", "## Action Items",
                         "## Raw Excerpts") if h in drafted]
    if data.get("drafted") is True and len(heads) != 4:
        return FAIL, notes + ["(e) the brain drafted minutes carrying %d of the four "
                              "headings (%s) - the shape is the whole contract between "
                              "this route and the hand" % (len(heads), ", ".join(heads))]
    if data.get("drafted") is not True:
        warnings.append("(e) the brain could not draft, so the raw-transcript fallback "
                        "was served instead: %s" % first_line(data.get("error")))
    after = sorted(os.listdir(notes_dir)) if os.path.isdir(notes_dir) else []
    if after != before:
        return FAIL, notes + ["(e) /scribe/minutes changed notes/ (%s) - this route DRAFTS "
                              "and the hand writes; a route that wrote would be a file "
                              "created without anybody saying yes"
                              % ", ".join(sorted(set(after) ^ set(before)))]
    notes.append("(e) drafted %d chars under %d headings from %d of transcript, the "
                 "traversal title came back as the name %r, and notes/ did not move - "
                 "this route writes nothing"
                 % (len(drafted), len(heads), len(transcript), title))

    # -- (f) the hand's own refusals, and then one real write.
    code, line = _run_minutes_hand({"title": "Preflight-empty", "minutes": "   "})
    if code == 0 or "no minutes" not in line.lower():
        return FAIL, notes + ["(f) save_minutes.py accepted empty minutes (exit %d, %r) - "
                              "an empty minute is the one artefact that gets believed six "
                              "weeks later because it is on disk" % (code, line)]
    refused_empty = first_line(line, 64)
    # THE ../ TITLE IS DEFANGED, NOT REFUSED, and the difference is worth stating because
    # the first version of this check asserted the wrong one and then reported that a file
    # it had just created had been refused. safe_title() strips the separator before the
    # basename is taken, so "../preflight-escaped" is the NAME "preflight-escaped" and the
    # write lands inside notes/ like any other. What must never happen is the write landing
    # one directory up, so that is what is asserted - in both plausible spellings, because
    # a stripper that turned "../x" into "..x" would still be inside notes/ and still wrong.
    escaped_name = "preflight-escaped"
    outside = [os.path.join(os.path.dirname(ROOT), escaped_name + ".md"),
               os.path.join(ROOT, escaped_name + ".md")]
    inside = os.path.join(notes_dir, escaped_name + ".md")
    try:
        code, line = _run_minutes_hand({"title": "../" + escaped_name,
                                        "minutes": "## Attendees\n\nnobody\n"})
        strayed = [p for p in outside if os.path.exists(p)]
        if strayed:
            for p in strayed:
                try:
                    os.remove(p)
                except OSError:
                    pass
            return FAIL, notes + ["(f) save_minutes.py wrote %s - a title is a filename "
                                  "and ../ has to become a name, never a parent"
                                  % ", ".join(strayed)]
        if code != 0 or not os.path.isfile(inside):
            return FAIL, notes + ["(f) a ../ title neither escaped nor landed in notes/ "
                                  "(exit %d, %r) - one of those two has to be true or the "
                                  "hand has a third behaviour nobody has described"
                                  % (code, first_line(line))]
        notes.append("(f) empty minutes are refused by the hand itself (“%s”), and a "
                     "“../%s” title is DEFANGED rather than refused: it wrote notes/%s.md "
                     "and nothing appeared above notes/ or beside the project folder"
                     % (refused_empty, escaped_name, escaped_name))
    finally:
        try:
            os.remove(inside)
        except OSError:
            pass

    probe = "Preflight-minutes-%s" % hashlib.sha256(
        ("%f" % time.time()).encode()).hexdigest()[:8]
    path = os.path.join(notes_dir, probe + ".md")
    try:
        code, line = _run_minutes_hand({"title": probe, "minutes": drafted})
        if code != 0 or not os.path.isfile(path):
            return FAIL, notes + ["(f) save_minutes.py would not write notes/%s.md (exit "
                                  "%d, %r)" % (probe, code, line)]
        with open(path, "r", encoding="utf-8") as fh:
            back = fh.read()
        if not back.startswith("# " + probe) or "by the Scribe" not in back:
            return FAIL, notes + ["(f) the file was written without its heading or its "
                                  "stamp: %r" % first_line(back)]
        again_code, again = _run_minutes_hand({"title": probe, "minutes": drafted})
        if again_code == 0 or "already exists" not in again:
            return FAIL, notes + ["(f) the same title written twice was accepted (exit "
                                  "%d, %r) - the same meeting written twice is a "
                                  "correction, and that is a decision for the employer"
                                  % (again_code, again)]
        over_code, over = _run_minutes_hand({"title": probe, "minutes": drafted,
                                             "overwrite": True})
        if over_code != 0 or not over.startswith("Replaced"):
            return FAIL, notes + ["(f) overwrite:true was refused (exit %d, %r)"
                                  % (over_code, over)]
        notes.append("(f) one real write, read back, refused on the second pass "
                     "(“%s”) and replaced only when told to: “%s”"
                     % (first_line(again, 56), first_line(over, 64)))
    finally:
        # This check leaves nothing in the employer's notes, the way the /remember probe
        # does not.
        try:
            os.remove(path)
        except OSError:
            pass

    # -- (g) the privacy law, measured from outside the process that promises it.
    audio_after = _audio_on_disk()
    fresh = sorted(set(audio_after) - set(audio_before))
    grew = sorted(p for p in audio_before
                  if audio_after.get(p, audio_before[p]) != audio_before[p])
    if fresh or grew:
        return FAIL, notes + ["(g) audio reached the disk during this check: %s - the "
                              "privacy law is that no byte of a meeting is ever written "
                              "anywhere" % ", ".join(fresh + grew)]
    block2 = (as_json(http_call("GET", "/health", timeout=20,
                                label="GET /health (scribe, after)")[2]) or {}
              ).get("scribe") or {}
    if (block2.get("chunks") or 0) <= chunks_before:
        warnings.append("(g) the server's chunk counter did not move (%r -> %r), so it is "
                        "not counting what it transcribed"
                        % (chunks_before, block2.get("chunks")))
    if block2.get("transcribedChars") and block2.get("keepsText") is not False:
        return FAIL, notes + ["(g) /health still says keepsText - the server counted the "
                              "characters and kept them"]
    # AND NOTHING IS LEFT IN THE EMPLOYER'S NOTES. (e) took this photograph before the
    # route was asked to draft; (f) then wrote two real files and removed both. A check that
    # proves a hand can write and leaves the evidence behind has added a note to the galaxy.
    left = sorted(set(os.listdir(notes_dir) if os.path.isdir(notes_dir) else []) -
                  set(before))
    if left:
        return FAIL, notes + ["(g) this check left %s in notes/ - preflight writes into the "
                              "real corpus and has to take it back out again"
                              % ", ".join(left)]
    notes.append("(g) %d audio file%s under the project root before this check and the "
                 "same %d after, none of them larger (say-cache/ excluded by name - it is "
                 "the voice this machine PRODUCES, and (b) put the fixture there); notes/ "
                 "holds exactly the %d file%s it held before; the server transcribed %d "
                 "chunk%s of this check's audio and has passed %.1fMB through RAM "
                 "cumulatively without writing any of it"
                 % (len(audio_before), "" if len(audio_before) == 1 else "s",
                    len(audio_after), len(before), "" if len(before) == 1 else "s",
                    (block2.get("chunks") or 0) - chunks_before,
                    "" if (block2.get("chunks") or 0) - chunks_before == 1 else "s",
                    (block2.get("audioBytes") or 0) / (1024.0 * 1024.0)))

    proof = os.path.join(ROOT, "scribe_proof.mjs")
    notes.append("the browser half - a real getDisplayMedia, the worklet, the panel, the "
                 "organ and the three seals - is scribe_proof.mjs%s, which drives Chrome "
                 "and so is never run from preflight"
                 % ("" if os.path.exists(proof) else " (MISSING)"))
    if not os.path.exists(proof):
        warnings.append("scribe_proof.mjs is missing, so nothing in this repository proves "
                        "the picker, the worklet or the panel")

    if warnings:
        return WARN, notes + warnings
    return PASS, notes


# ----------------------------------------------------- 21. the silent subprocess policy

SPAWN_ATTRS = {"run", "Popen", "call", "check_call", "check_output"}
QUIET_ATTRS = {"run", "popen"}
# tools/_proc.py is the one file allowed to touch subprocess directly: it IS the policy.
POLICY_FILE = os.path.join("tools", "_proc.py")


def _spawn_sites(path):
    """(bare, quiet) call sites in one file, PARSED rather than grepped.

    ast, and the difference is not fastidiousness. hands.py's module docstring explains the
    call it makes by writing `subprocess.run([sys.executable, script], ...)` in prose; the
    first, regex-based version of this audit read that sentence as a call and failed the
    very file it had just been repaired in. A parser sees a Call node or it sees a string
    constant and never confuses the two.
    """
    try:
        with open(path, "r", encoding="utf-8") as fh:
            tree = ast.parse(fh.read(), filename=path)
    except (OSError, SyntaxError) as exc:
        return None, str(exc)
    bare, quiet = [], []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        if not isinstance(fn, ast.Attribute) or not isinstance(fn.value, ast.Name):
            continue
        mod, attr = fn.value.id, fn.attr
        if mod == "subprocess" and attr in SPAWN_ATTRS:
            bare.append((node.lineno, "subprocess.%s" % attr))
        elif mod == "os" and attr == "system":
            bare.append((node.lineno, "os.system"))
        elif mod == "_proc" and attr in QUIET_ATTRS:
            quiet.append((node.lineno, "_proc.%s" % attr))
    return (bare, quiet), ""


def check_quiet_spawn():
    """21. Nothing this server starts is allowed to show a console window.

    The complaint was a black window blinking on the desktop after every spoken answer. It
    was say.py handing piper to subprocess.run() with the default creation flags: Windows
    gives a console program a console, and a console has a window. Measured before anything
    was changed, class PseudoConsoleWindow, parented to the server.

    Three parts, because no one of them is evidence on its own:
      (a) THE AUDIT. Every .py in the repository is parsed and every spawn call is
          attributed. One bare call is a failure, wherever it is, because the flash is a
          property of the call site and not of the feature that owns it.
      (b) THE POLICY. _proc's own decision, exercised directly: a caller who says nothing
          gets CREATE_NO_WINDOW, and a caller who passes creationflags is left alone -
          DETACHED_PROCESS and CREATE_NEW_CONSOLE are deliberate, and or-ing a flag into
          them is how a launcher stops launching.
      (c) A LIVE WATCH. The source can be right and the desktop still wrong, so a real
          synthesis is made to happen on the running server while console_watch.py polls
          user32 at 8 ms, and the verdict is read off the desktop.
    """
    notes, warnings = [], []

    # -- (a) the audit. Every file, including this one.
    files = sorted([f for f in os.listdir(ROOT) if f.endswith(".py")])
    tools_dir = os.path.join(ROOT, "tools")
    files += [os.path.join("tools", f) for f in sorted(os.listdir(tools_dir))
              if f.endswith(".py")]
    bare_all, quiet_all, unread = [], [], []
    for rel in files:
        sites, why = _spawn_sites(os.path.join(ROOT, rel))
        if sites is None:
            unread.append("%s (%s)" % (rel, why))
            continue
        bare, quiet = sites
        for lineno, what in bare:
            if rel == POLICY_FILE:
                continue                    # the policy is the one place subprocess lives
            bare_all.append("%s:%d %s" % (rel, lineno, what))
        for lineno, what in quiet:
            quiet_all.append("%s:%d %s" % (rel, lineno, what))
    if unread:
        return FAIL, ["these files could not be parsed, so the audit is not an audit: %s"
                      % ", ".join(unread)]
    if bare_all:
        return FAIL, ["(a) %d spawn(s) reach subprocess or os.system directly, and each "
                      "one is a console window on the employer's desktop: %s"
                      % (len(bare_all), ", ".join(bare_all)),
                      "every one of them belongs in tools/_proc.run or tools/_proc.popen"]
    by_file = {}
    for site in quiet_all:
        by_file.setdefault(site.split(":")[0], []).append(site.split(" ")[0].split(":")[1])
    notes.append("(a) %d .py files parsed; %d spawn call(s), all of them through the "
                 "policy: %s"
                 % (len(files), len(quiet_all),
                    ", ".join("%s(%s)" % (f, ",".join(ls)) for f, ls in sorted(by_file.items()))))
    if not quiet_all:
        return FAIL, notes + ["(a) the audit found no spawn call at all, which means it is "
                              "looking in the wrong place rather than that the repository "
                              "has stopped starting processes"]

    # -- (b) the policy itself, exercised rather than read.
    if sys.platform != "win32":
        notes.append("(b) not Windows: _proc is a pass-through here by design, so there is "
                     "no flag to check")
    else:
        before = _proc.applied
        silent_caller = _proc._quiet({})
        detached = 0x00000008                           # DETACHED_PROCESS
        loud_caller = _proc._quiet({"creationflags": detached})
        if silent_caller.get("creationflags") != _proc.CREATE_NO_WINDOW:
            return FAIL, notes + ["(b) a caller that asked for nothing was given %r rather "
                                  "than CREATE_NO_WINDOW (0x%08X), so the policy is not "
                                  "applied at all"
                                  % (silent_caller.get("creationflags"),
                                     _proc.CREATE_NO_WINDOW)]
        if loud_caller.get("creationflags") != detached:
            return FAIL, notes + ["(b) a caller that passed DETACHED_PROCESS came back with "
                                  "%r - the helper overrode a deliberate choice, which is "
                                  "how a launcher stops launching"
                                  % loud_caller.get("creationflags")]
        if _proc.applied != before + 1:
            return FAIL, notes + ["(b) the counter moved %d -> %d across one silent caller "
                                  "and one explicit one; it must move exactly once, or it "
                                  "cannot be used as evidence that the flag ever fired"
                                  % (before, _proc.applied)]
        notes.append("(b) the policy decides correctly both ways: nothing asked -> "
                     "CREATE_NO_WINDOW 0x%08X, DETACHED_PROCESS passed -> left untouched"
                     % _proc.CREATE_NO_WINDOW)

    # -- (c) the live watch. The desktop, while the server really works.
    watcher = os.path.join(ROOT, "console_watch.py")
    proof = os.path.join(ROOT, "console_proof.mjs")
    if not os.path.exists(proof):
        warnings.append("console_proof.mjs is missing, so nothing in this repository "
                        "proves the desktop stays empty across a long answer, a voice "
                        "recast and a proposal")
    else:
        notes.append("the four-case desktop matrix - a short answer, a long one, a voice "
                     "recast and a proposal - is proved by console_proof.mjs, which drives "
                     "a headed browser and so is never run from preflight")
    if not os.path.exists(watcher):
        return WARN, notes + warnings + ["console_watch.py is missing, so (c) cannot run "
                                         "and the desktop is only argued about"]
    if sys.platform != "win32":
        notes.append("(c) not Windows: there is no console window to watch for")
        return (WARN, notes + warnings) if warnings else (PASS, notes)

    status, _head, body = http_call("GET", "/focus/diag", timeout=20,
                                    label="GET /focus/diag (pid for the watch)")
    diag = ((as_json(body) or {}).get("diag") or {})
    pid = diag.get("pid")
    if status != 200 or not pid:
        return WARN, notes + warnings + ["(c) the server would not name its own pid, so "
                                         "the parent filter has nothing to anchor to"]
    if not (state.get("health", {}).get("say") or {}).get("ready"):
        return WARN, notes + warnings + ["(c) the local voice is not ready, so there is no "
                                         "spawn to watch; the audit above still stands"]

    # NOT a fresh process list: two python.exe have shared port 4700 on this machine
    # before, and watching the wrong one is an empty desktop for the wrong reason.
    watch = _proc.popen([sys.executable, watcher, "--pid", str(pid), "--seconds", "60"],
                        stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE, text=True, cwd=ROOT)
    verdict, raw = None, ""
    try:
        line = watch.stdout.readline()
        if "WATCHING" not in line:
            watch.kill()
            return WARN, notes + warnings + ["(c) the watcher never started watching: %r"
                                             % first_line(line, 70)]
        # A sentence this machine has never synthesised, so piper MUST run: a say-cache hit
        # would spawn nothing and report an empty desktop as a success.
        token = hashlib.sha256(("%f" % time.time()).encode()).hexdigest()[:8]
        started = time.time()
        sstatus, shead, sbody = post_json(
            "/say", {"text": "Preflight, reference %s, sir." % token},
            timeout=90, label="POST /say (a cold line, watched)")
        spoke = sstatus == 200 and shead.get("content-type", "").startswith("audio/")
        time.sleep(0.8)                     # the window appears as the child starts, not as
        watch.stdin.write("stop\n")         # it exits; do not close the watch on the tick
        watch.stdin.flush()                 # the answer arrives
        raw = watch.stdout.readline()
        verdict = json.loads(raw)
    except Exception as exc:                                   # noqa: BLE001
        return WARN, notes + warnings + ["(c) the watch itself failed: %s: %s"
                                         % (type(exc).__name__, exc)]
    finally:
        try:
            watch.kill()
        except Exception:                                      # noqa: BLE001
            pass

    if not spoke:
        return WARN, notes + warnings + ["(c) /say answered %s %s, so nothing was spawned "
                                         "to watch" % (sstatus, shead.get("content-type"))]
    if verdict.get("polls", 0) < 40:
        return FAIL, notes + ["(c) the watcher polled the desktop %d time(s) in %.1fs - it "
                              "returned before it had looked, which is the one way this "
                              "check can pass without examining anything"
                              % (verdict.get("polls", 0), time.time() - started)]
    windows = verdict.get("windows") or []
    if windows:
        return FAIL, notes + ["(c) %d console WINDOW(s) appeared in the server's process "
                              "tree while it spoke - this is the black flash itself: %s"
                              % (len(windows),
                                 "; ".join("%s at +%sms %s" % (w.get("class"), w.get("atMs"),
                                                               " <- ".join(w.get("chain") or []))
                                           for w in windows))]
    hidden = verdict.get("hiddenConsoles") or []
    notes.append("(c) %d bytes of real speech synthesised under pid %s while the desktop "
                 "was polled %d times: not one console window, and %d hidden console "
                 "host(s) - which is CREATE_NO_WINDOW working, since the flag means a "
                 "console with no window rather than no console"
                 % (len(sbody), pid, verdict.get("polls"), len(hidden)))
    if verdict.get("bystanders"):
        notes.append("(c) %d console window(s) belonging to other processes were seen and "
                     "correctly disregarded by the parent-chain filter"
                     % len(verdict["bystanders"]))

    if warnings:
        return WARN, notes + warnings
    return PASS, notes


def check_room_hour():
    """22. The room knows the hour: a second floor for the head, a work mode that is the
    whole room, a gaze that only ever reads, and an instrument that does not pretend to be
    the boss.

    FOUR THINGS, and each one is a way this round can rot without a single harness
    noticing - which is the only reason a preflight check earns an integer:

      (a) THE SECOND FLOOR. PRES_MIN is the side below which a full-density well stands
          down; PRES_MIN_COMPACT is the side below which it stands down at all. Delete the
          second number, or let somebody "tidy" it to equal the first, and the head is
          invisible again at 1280 with every proof still green - because a governor that
          never enters compact mode is indistinguishable from one that has no compact mode.
          So the two numbers are read off the LAYOUT literal and compared.
      (b) THE TUNE, WRITTEN DOWN. §12's argument, applied to work mode: numbers picked
          without being recorded cannot be reasoned about later. WORK holds all five, and
          all five are bounded here - a NEB_WORK above NEB_IDLE would brighten the room for
          a focus session, and an MS of 0 would make the crossfade a cut, which is the one
          thing the mandate forbids by name.
      (c) THE GAZE READS AND NEVER TAKES. The head's gaze target is driven off one field of
          focus's own state and there is no door to set it, deliberately, so that no harness
          can make the head look at something by asking it to. The declared signal string is
          therefore part of the contract: if it stops naming focus.public_state().drifting,
          the instrument is reporting on a signal nobody is watching.
      (d) AND AN INSTRUMENT IS NOT A MAN AT HIS DESK. This one is here because it cost a
          whole round. Every viewer beats "I have the keyboard" at the server while a
          session is live and document.hasFocus() is true, and home base outranks every
          drift by design - so a headless SECOND viewer, where hasFocus() can never go
          false, silently excused every locked-tab drift on the machine: measured at 2861 ms
          against a 1500 ms budget with drifts=0, and 937 ms with drifts=1 the moment that
          viewer was not opened. ?nohome=1 is the repair. Remove it and lock_proof's whole
          fourth section goes red for a reason that looks like a broken watchdog, so the
          guard is asserted here where the failure can still be read in English.

    And one live read on top of them, because (a)-(d) are source and source is not
    behaviour: the payload the room subscribes to is fetched from the running server and
    checked for what it must NOT have grown. Work mode, the deep field and the gaze all ride
    the session state that already existed; a `nebula` or `gaze` key on that wire would mean
    the page had been given a private channel and the claim "nothing new is added to that
    payload" had quietly stopped being true.
    """
    notes, warnings = [], []
    try:
        with open(os.path.join(ROOT, "viewer", "index.html"), encoding="utf-8") as fh:
            viewer = fh.read()
    except OSError as exc:
        return FAIL, ["cannot read viewer/index.html: %s" % exc]

    # -- (a) the two floors.
    floors = {}
    for name in ("PRES_MIN", "PRES_MIN_COMPACT"):
        found = re.search(r"\b%s\s*:\s*(\d+)" % name, viewer)
        if found:
            floors[name] = int(found.group(1))
    missing = [n for n in ("PRES_MIN", "PRES_MIN_COMPACT") if n not in floors]
    if missing:
        return FAIL, ["the LAYOUT table names no %s, so the presence has no %s floor and "
                      "the head is back to rendering nothing at the commonest laptop width"
                      % (" and no ".join(missing),
                         "second" if "PRES_MIN_COMPACT" in missing else "first")]
    if not 0 < floors["PRES_MIN_COMPACT"] < floors["PRES_MIN"]:
        return FAIL, ["PRES_MIN_COMPACT is %d against PRES_MIN %d: a second floor that is "
                      "not BELOW the first is not a second floor, and compact mode can "
                      "never engage"
                      % (floors["PRES_MIN_COMPACT"], floors["PRES_MIN"])]
    if "LAYOUT.PRES_MIN_COMPACT" not in viewer:
        return FAIL, ["PRES_MIN_COMPACT is declared and never read, so the governor still "
                      "stands the well down at the full-size floor"]
    notes.append("(a) two floors, and the second is below the first: full density at "
                 "%dpx of glass, compact at %dpx, nothing at all below that"
                 % (floors["PRES_MIN"], floors["PRES_MIN_COMPACT"]))

    # -- (b) the tune, and its bounds.
    block = re.search(r"const WORK\s*=\s*\{(.*?)\};", viewer, re.S)
    if not block:
        return FAIL, notes + ["viewer/index.html has no WORK tune block, so work mode's "
                              "numbers are wherever they were typed and cannot be reasoned "
                              "about - which is the one thing 12 argued against"]
    tune = {}
    for key, raw in re.findall(r"(\w+)\s*:\s*([0-9.]+)", block.group(1)):
        tune[key] = float(raw)
    want = ("MS", "NEB_IDLE", "NEB_WORK", "SWAY", "DESAT")
    absent = [k for k in want if k not in tune]
    if absent:
        return FAIL, notes + ["the WORK tune is missing %s, so at least one of the room's "
                              "four movements has an unrecorded number in it"
                              % ", ".join(absent)]
    if tune["MS"] <= 0:
        return FAIL, notes + ["WORK.MS is %g: a crossfade of zero milliseconds is a CUT, "
                              "which is the one transition the room is not allowed"
                              % tune["MS"]]
    if not tune["NEB_WORK"] < tune["NEB_IDLE"]:
        return FAIL, notes + ["WORK.NEB_WORK %g is not below NEB_IDLE %g, so starting a "
                              "focus session would brighten the deep field rather than "
                              "narrowing it" % (tune["NEB_WORK"], tune["NEB_IDLE"])]
    for key in ("SWAY", "DESAT"):
        if not 0.0 < tune[key] < 1.0:
            return FAIL, notes + ["WORK.%s is %g; it is a FRACTION of the idle value, so "
                                  "0 would switch the thing off and 1 would leave it "
                                  "untouched - neither is a crossfade" % (key, tune[key])]
    notes.append("(b) all five of work mode's numbers are declared in one place and in "
                 "range: %s" % ", ".join("%s=%g" % (k, tune[k]) for k in want))

    # -- (c) the gaze reads one field, and there is no way to set it.
    signal = "focus.public_state().drifting"
    if signal not in viewer:
        return FAIL, notes + ["the gaze instrument no longer names %s as its signal, so "
                              "whatever the head is now following, nothing in this "
                              "repository says what it is" % signal]
    for name in ("GAZE_MAX", "GAZE_TAU", "GAZE_EPS"):
        if not re.search(r"\b%s\s*:" % name, viewer):
            return FAIL, notes + ["PRES has no %s, so the gaze's ceiling, its chase or its "
                                  "deadband is an inline number again" % name]
    setters = re.findall(r"presence\.gaze\.(?:want|at)\s*=", viewer)
    if setters:
        return FAIL, notes + ["%d place(s) write to the gaze through the instrument door, "
                              "so a harness can make the head look at something by asking "
                              "it to and the departure proves nothing" % len(setters)]
    notes.append("(c) the gaze declares one signal - %s - has its three constants, and "
                 "exposes no setter" % signal)

    # -- (d) the instrument's own honesty, which is what this round learned the hard way.
    if "nohome=1" not in viewer:
        return FAIL, notes + ["the viewer has no ?nohome=1, so a second headless viewer "
                              "claims home base for the whole of its life and every "
                              "locked-tab drift on this machine is excused - a watchdog "
                              "that looks broken and is only being lied to"]
    beat = re.search(r"if \(probeRunning \|\| NOHOME\) return;", viewer)
    if not beat:
        return FAIL, notes + ["?nohome=1 is declared and the home beat does not honour it, "
                              "which is worse than not having the flag: lock_proof's "
                              "observer would ask to be ignored and be believed by nobody"]
    notes.append("(d) the home-base beat is suppressed for an instrument as well as for a "
                 "synthetic session, so a second viewer cannot excuse a real drift")

    # -- the live read. Source is not behaviour, and this is the one claim only the
    # running server can answer.
    if not state["up"]:
        warnings.append("the server is not reachable, so the wire could not be read and "
                        "(a)-(d) are source alone")
        return WARN, notes + warnings
    live = _focus_now()
    if not isinstance(live, dict) or not live:
        warnings.append("GET /focus answered nothing session-shaped, so the payload could "
                        "not be inspected")
        return WARN, notes + warnings
    private = sorted(k for k in live
                     if re.search(r"neb|gaze|presence|emissive|parallax|compact", k, re.I))
    if private:
        return FAIL, notes + ["the session payload has grown %s: work mode, the deep field "
                              "and the gaze are all supposed to ride the state that already "
                              "existed, and a private channel for the room is exactly what "
                              "this round promised not to add" % private]
    notes.append("the room rides the session state that was already on the wire: %d keys, "
                 "and not one of them is about a nebula, a gaze or a point count"
                 % len(live))

    if warnings:
        return WARN, notes + warnings
    return PASS, notes


def check_google_grant():
    """23. The road to Google is narrow, it is asked for out loud, and it refuses politely.

    Two hands stopped being local this round. add_calendar_event used to append a line to
    calendar.json and send_email used to log in to smtp.gmail.com with an app password;
    they now call Calendar v3 events.insert and Gmail v1 users.messages.send against an
    OAuth grant. That is a large increase in what a wrong answer can do - a guessed time
    used to be a wrong line in a file nobody read, and is now an alarm on the employer's
    phone at four in the morning - so five things about it earn an integer here:

      (a) THE SCOPES ARE THE THREE, AND NOTHING WIDER. gmail.send, gmail.compose and
          calendar.events. Every one of those is a WRITE scope with no read: this grant
          cannot list a message, cannot read a thread and cannot see an event it did not
          create the id of. Widen it to mail.google.com or calendar and both statements
          stop being true, silently, with every harness still green - because a broader
          scope never fails, it only permits. Read from the source AND from the running
          server, since a constant is not a promise until the process is using it.
      (b) NOTHING SECRET IS ON THE WIRE. GET /google is the only Google route the page can
          read, and the panel needs six facts from it: connected or not, which account, the
          scope list, the loopback port, a digest, and whether consent is in flight. It
          must therefore carry no access token, no refresh token, no authorization code and
          no client secret - and the client secret is checked BY VALUE, read out of
          secrets/ and searched for in the payload, because a field named innocently is
          still a leak. The token file itself must 404 from the browser: secrets/ lives
          outside viewer/, and this is the check that notices if it ever stops.
      (c) THE REFUSAL CHAIN, END TO END, THROUGH THE REAL GATE. With no token this machine
          must say "I have no road to your calendar yet" and not "HTTP 401", must exit
          non-zero, and must log the attempt as a FAILED run rather than a refused
          proposal - the subprocess really did start. Driven over HTTP through propose and
          execute, which is the same door the page uses, so the sentence proved here is the
          sentence a human would hear. On a machine that IS connected this clause does not
          run: it would create a real event to prove a refusal, which is the wrong trade,
          and the check says so rather than passing quietly.
      (d) THE STAMPS ARE READ BEFORE THE NETWORK IS. A time nobody can parse is refused at
          the gate with nothing pending - not carried to Google to be rejected there, and
          not shown on a card with a {when} still standing in it. This is the clause that
          catches hands.readings() being dropped, because the symptom otherwise is a
          proposal that reads an ISO timestamp aloud to a listener.
      (e) calendar.json IS RETIRED, PROVED FROM THE SOURCE. The retirement only means
          something if there is no fallback: a hand that wrote to Google and then also
          appended locally, or read the file when the network failed, would let a failed
          send look like a success. So the hand's source is read and must not name the file
          at all, and the registry's parameters must be the new four - a `when` left in
          that schema is a parameter the script silently drops.

    Nothing here sends mail, creates an event, or writes a token. (c) runs the calendar
    hand exactly once, on a machine with no grant, for the express purpose of being told no.
    """
    notes, warnings = [], []
    want = ["https://www.googleapis.com/auth/gmail.send",
            "https://www.googleapis.com/auth/gmail.compose",
            "https://www.googleapis.com/auth/calendar.events"]

    # -- (a) the scopes, from the source first.
    try:
        with open(os.path.join(ROOT, "google_api.py"), encoding="utf-8") as fh:
            src = fh.read()
    except OSError as exc:
        return FAIL, ["google_api.py could not be read (%s), so the two hands that now "
                      "reach outside this house have no module behind them" % exc]
    found = re.search(r"SCOPES\s*=\s*\[(.*?)\]", src, re.S)
    declared = re.findall(r"https://[^\"']+", found.group(1)) if found else []
    if declared != want:
        return FAIL, ["SCOPES in google_api.py is %s, and the grant this project asked "
                      "for is exactly %s. A wider scope never fails a test - it only "
                      "permits - so it is checked by equality and not by containment"
                      % (declared, want)]
    # Only QUOTED scope strings count. The module's own comment names the wide scopes in
    # prose, to say they are deliberately absent, and a plain substring search would read
    # that paragraph and fail the check the paragraph exists to explain. A widened scope,
    # wherever it were written, would be a string literal - so literals are what is read.
    literals = re.findall(r"""['"](https://[^'"\s]+)['"]""", src)
    broad = sorted({s for s in literals
                    if re.search(r"^https://mail\.google\.com"
                                 r"|auth/(gmail|calendar)$"
                                 r"|auth/gmail\.(readonly|modify|metadata|insert)"
                                 r"|auth/calendar\.readonly", s)})
    if broad:
        return FAIL, notes + ["google_api.py asks for the scope(s) %s in a string literal. "
                              "This grant is write-only by design: it must not be able to "
                              "read a mailbox it was given to send from" % broad]
    notes.append("three write-only scopes, declared and matched exactly: send, compose, "
                 "calendar.events - no read scope anywhere in the module")

    if not state["up"]:
        warnings.append("the server is not reachable, so (a) is source alone and (b)-(e) "
                        "could not be asked at all")
        return WARN, notes + warnings

    # -- (a) again, live. A constant is not a promise until the process is using it.
    status, _, body = http_call("GET", "/google", timeout=20, label="GET /google")
    grant = as_json(body)
    if status != 200 or not isinstance(grant, dict):
        return FAIL, notes + ["GET /google came back %s with %r - the Command Panel's "
                              "state line has nothing to read"
                              % (status, first_line(body.decode("utf-8", "replace")))]
    if list(grant.get("scopes") or []) != want:
        return FAIL, notes + ["the running server offers scopes %s, which is not the three "
                              "in its own source. The process is using a different grant "
                              "from the one this file just checked" % grant.get("scopes")]
    where = grant.get("state")
    notes.append("the running server agrees, and reads state %r on port %s"
                 % (where, grant.get("port")))

    # -- (b) nothing secret on the wire, and the secret is checked BY VALUE.
    flat = json.dumps(grant)
    named = sorted(k for k in grant
                   if re.search(r"access_?token|refresh|secret|^code$|verifier|bearer",
                                str(k), re.I))
    if named:
        return FAIL, notes + ["GET /google carries the field(s) %s. The panel needs six "
                              "facts and a token is not one of them" % named]
    secret = ""
    try:
        with open(os.path.join(ROOT, "secrets", "google_client.json"), encoding="utf-8") as fh:
            secret = str((json.load(fh).get("installed") or {}).get("client_secret") or "")
    except Exception:                                          # noqa: BLE001
        warnings.append("secrets/google_client.json could not be read, so the client secret "
                        "was not searched for by value - only by field name")
    if secret and secret in flat:
        return FAIL, notes + ["the client secret's own characters appear in the body of "
                              "GET /google. A field named innocently is still a leak"]
    if secret:
        notes.append("and the client secret's %d characters appear nowhere in the payload, "
                     "checked by value and not by field name" % len(secret))
    for path in ("/secrets/google_token.json", "/secrets/google_client.json",
                 "/../secrets/google_token.json"):
        code, _, _ = http_call("GET", path, timeout=15, label="GET " + path)
        if code == 200:
            return FAIL, notes + ["%s is SERVED to the browser. secrets/ holds a refresh "
                                  "token, which does not expire on its own" % path]
    notes.append("and secrets/ is unreachable over HTTP: the token file, the client file "
                 "and one traversal at it all refuse")

    # -- (e) the retirement, from the source, before anything is proposed.
    try:
        with open(os.path.join(ROOT, "tools", "add_calendar_event.py"), encoding="utf-8") as fh:
            hand = fh.read()
        with open(os.path.join(ROOT, "tools", "registry.json"), encoding="utf-8") as fh:
            registry = json.load(fh)
    except Exception as exc:                                   # noqa: BLE001
        return FAIL, notes + ["the calendar hand or the registry could not be read: %s" % exc]
    body_only = re.sub(r'""".*?"""', "", hand, flags=re.S)
    if "calendar.json" in body_only:
        return FAIL, notes + ["tools/add_calendar_event.py still names calendar.json "
                              "outside its docstring. A local fallback is how a failed "
                              "send starts looking like a success"]
    entry = next((t for t in registry.get("tools") or []
                  if t.get("id") == "add_calendar_event"), None)
    params = [p.get("name") for p in (entry or {}).get("params") or []]
    if params != ["title", "start", "end", "description"]:
        return FAIL, notes + ["the registry declares add_calendar_event params %s and the "
                              "hand reads title/start/end/description. Anything not "
                              "declared is dropped before the script sees it, so a stale "
                              "`when` here is a time that silently never arrives" % params]
    notes.append("calendar.json is named nowhere in the hand's code, and the schema is the "
                 "four the hand actually reads")

    # -- (d) a time nobody can parse is refused at the gate, with nothing pending.
    status, _, body = post_json("/tools", {"cmd": "propose", "tool": "add_calendar_event",
                                           "params": {"title": "a probe that goes nowhere",
                                                      "start": "some time on thursday"}},
                                timeout=30, label="POST /tools bad stamp")
    said = as_json(body) or {}
    line = str(said.get("answer") or "")
    if status < 400 or said.get("pending") or "{when}" in line:
        return FAIL, notes + ["an unreadable start time was answered %s with %r and "
                              "pending=%r. It must be refused with nothing left in the "
                              "slot: a card showing a literal {when} is a card the "
                              "employer is being asked to approve blind"
                              % (status, first_line(line), said.get("pending"))]
    if not re.search(r"not a date i can read", line, re.I):
        return FAIL, notes + ["the refusal for an unreadable time was %r, which does not "
                              "name the shape it wanted. A refusal that does not name its "
                              "remedy is a machine saying no" % first_line(line)]
    notes.append("an unparseable start is refused at the gate, naming the shape it wants, "
                 "with nothing left pending: %r" % first_line(line))

    # -- (c) the refusal chain, all the way through the real door.
    if where == "connected":
        # The account is named by DIGEST and never in full. This file's output is pasted
        # into reports, so the address of the mailbox this machine can send from does not
        # belong in it - the digest is enough to tell two grants apart, which is all a
        # check ever needs.
        notes.append("this machine HAS a grant (account digest %s, token digest %s), so the "
                     "no-token chain was not driven: proving a refusal would have meant "
                     "creating a real event in a real calendar, which is a worse trade than "
                     "leaving one clause unrun"
                     % (hashlib.sha256(str(grant.get("email") or "")
                                       .encode("utf-8")).hexdigest()[:8],
                        grant.get("tokenDigest") or "none"))
        return (WARN, notes + warnings) if warnings else (PASS, notes)
    before = _ledger_row("add_calendar_event")
    status, _, body = post_json("/tools", {"cmd": "propose", "tool": "add_calendar_event",
                                           "params": {"title": "a probe that goes nowhere",
                                                      "start": "2099-01-01T09:00"}},
                                timeout=30, label="POST /tools calendar probe")
    said = as_json(body) or {}
    pending = said.get("pending") or {}
    if status != 200 or not pending.get("id"):
        return FAIL, notes + ["a well-formed calendar request was answered %s with %r, so "
                              "there was nothing to confirm and the refusal chain could "
                              "not be reached"
                              % (status, first_line(json.dumps(said)[:200]))]
    spoken = str(pending.get("line") or "")
    if "{" in spoken or not re.search(r"\d{1,2}:\d{2}\s*(am|pm)", spoken, re.I):
        return FAIL, notes + ["the proposal read %r. It should carry the human reading of "
                              "the stamp - hands.readings() is what fills {when}, and "
                              "without it this sentence reads a timestamp aloud"
                              % first_line(spoken)]
    status, _, body = post_json("/execute", {"id": pending["id"], "door": "button"},
                                timeout=60, label="POST /execute calendar probe")
    out = as_json(body) or {}
    answer = str(out.get("answer") or "")
    if not re.search(r"no road to your calendar", answer, re.I):
        return FAIL, notes + ["with no grant on this machine the calendar hand answered "
                              "%r. The sentence it owes is 'I have no road to your calendar "
                              "yet' with Connect Google named as the remedy - an HTTP code "
                              "is not an answer to a person" % first_line(answer)]
    if not re.search(r"connect google", answer, re.I):
        return FAIL, notes + ["the refusal was %r, which does not name the remedy"
                              % first_line(answer)]
    after = _ledger_row("add_calendar_event")
    if after["failed"] != before["failed"] + 1 or after["ok"] != before["ok"]:
        return FAIL, notes + ["the ledger went %s -> %s. A refusal by the hand is a FAILED "
                              "run and not a refused proposal: the subprocess started, read "
                              "its stdin and decided" % (before, after)]
    notes.append("with no grant, the chain propose -> confirm -> run ends in the hand's own "
                 "sentence, %r, and the ledger records one failed run and no ok"
                 % first_line(answer))

    # And the mail hand owes the same shape, refused before a byte could leave.
    status, _, body = post_json("/tools", {"cmd": "propose", "tool": "send_email",
                                           "params": {"to": "nobody@example.invalid",
                                                      "subject": "a probe that goes nowhere",
                                                      "body": "This is never sent."}},
                                timeout=30, label="POST /tools mail probe")
    said = as_json(body) or {}
    pending = said.get("pending") or {}
    if status != 200 or not pending.get("id"):
        return FAIL, notes + ["a well-formed email proposal was answered %s, so the mail "
                              "refusal could not be reached" % status]
    if "nobody@example.invalid" not in str(pending.get("line") or ""):
        warnings.append("the email proposal did not name the recipient out loud: %r"
                        % first_line(str(pending.get("line"))))
    status, _, body = post_json("/execute", {"id": pending["id"], "door": "button"},
                                timeout=60, label="POST /execute mail probe")
    answer = str((as_json(body) or {}).get("answer") or "")
    if not re.search(r"no road to your mail", answer, re.I):
        return FAIL, notes + ["with no grant the mail hand answered %r rather than naming "
                              "the missing road. This is the hand whose work cannot be "
                              "taken back; its refusals are the ones that must be plainest"
                              % first_line(answer)]
    notes.append("and the mail hand refuses in the same shape, at the same door: %r"
                 % first_line(answer))

    if warnings:
        return WARN, notes + warnings
    return PASS, notes


def _js_source(text):
    """viewer/index.html with its comments taken out, so a law can be asserted about the
    CODE and not about the paragraph above it explaining the code.

    This matters more here than it usually does. Check 24 below counts occurrences of
    `arm.state =` and of `recogniser.start()`, and both of those strings appear in the
    reset contract's own block comment - which describes the invariant in the same words the
    invariant is written in. Counting the raw file would score two of each and fail a page
    that is correct, which is the worst kind of check: one that punishes documentation.

    Block comments go first and wholesale. Line comments are removed only where the `//`
    opens a line, deliberately: a `//` in the middle of a line is as likely to be inside a
    regular expression literal or a URL as it is to be a comment, and this file is full of
    both. The consequence is that a trailing `// ...` note survives into the stripped text,
    so no check may assert the ABSENCE of a string that a trailing comment could contain.
    """
    out = re.sub(r"/\*.*?\*/", " ", text, flags=re.S)
    return "\n".join(
        "" if line.lstrip().startswith("//") else line for line in out.splitlines()
    )


def _fn_body(source, name):
    """One function's body by brace counting, or None. `source` must already be stripped of
    comments, or an unbalanced brace inside a comment ends the body early."""
    start = source.find("function %s(" % name)
    if start < 0:
        return None
    open_at = source.find("{", start)
    if open_at < 0:
        return None
    depth, i = 0, open_at
    while i < len(source):
        if source[i] == "{":
            depth += 1
        elif source[i] == "}":
            depth -= 1
            if depth == 0:
                return source[open_at + 1:i]
        i += 1
    return None


def _py_block(source, name):
    """One top-level Python def's text, or None.

    NOT _fn_body: that one counts braces and looks for `function name(`, which finds nothing
    in a .py file. And not "the next \\ndef " either - answer_question() is followed by a
    class whose methods are indented, so that bound runs a hundred thousand characters past
    the end of the function and would happily read the http layer's calls as if they were
    inside it.
    """
    head = re.search(r"^def %s\(" % re.escape(name), source, re.M)
    if not head:
        return None
    rest = source[head.start():]
    end = re.search(r"\n(?=(?:def |class |@)\S)", rest[1:])
    return rest if not end else rest[:end.start() + 1]


def check_reset_contract():
    """A TURN RESETS ONCE, AND ONE HAND WRITES THE ARM.

    The contract this asserts is the answer to a question the turn dump asked and could not
    settle: when the recogniser comes back up between two sentences, is every piece of state
    it depends on in a known condition? The dump says it always was - six turns, six arms,
    one recogniser, no stale flag, no drifting floor, no restart race - so this check is not
    guarding a bug that was seen. It is guarding the SHAPE that makes those four things
    unmeasurable-because-impossible rather than unmeasured-because-lucky, and the shape is
    fragile in one specific way: it is one function called from one place, and both of those
    ones are load-bearing.

    Seven things, and each names what goes wrong without it:

      (a) THE FOUR FUNCTIONS EXIST. armRead (the lifecycle word, computed), armSet (the one
          writer), armReset (the contract) and armFloorFrame (the 300ms sample). Their absence
          is not subtle, but the name is what the other six checks hang off.
      (b) ONE WRITER. Exactly one `arm.state =` in the file, and it is inside armSet. Two
          writers of a lifecycle word is the defect the eyes law was written to prevent and
          the failure is the same shape here: a path that re-arms the microphone and repaints
          only one of the two records, after which the page reports an ear that is listening
          to a room it is not listening to.
      (c) armRead COMPUTES AND DOES NOT WRITE. A reader that assigns is a second writer
          wearing a reader's name, and it would be called from everywhere before anybody
          noticed.
      (d) ONE DOOR, ONE RESET. Exactly one call to armReset() and exactly one call to
          recogniser.start() in the file, and the reset comes first in startListening's body.
          If a second path ever calls .start() directly it arms a microphone with a gate
          reference from the last turn and no floor of its own - and it does it silently,
          because every counter this contract keeps would be untouched.
      (e) THE FIVE TERMS ARE IN THE BODY: the gate reference zeroed, the floor window opened.
      (f) AND THE TWO THINGS THE BODY MUST NOT DO. It must not assign echo.gateAt or
          echo.gateOpens - the acoustic gate's HOLD is specified to outlive the answer that
          opened it, so that a barge-in taken on the last frame of a sentence is still open
          when the transcript of that sentence arrives ECHO_TAIL_MS later; a reset that
          cleared the hold would drop exactly that transcript into the brain as a question
          nobody asked, which is self-hearing coming back in through the repair. And it must
          not assign speakDraining or speakQueue, which belong to the protected funnel: the
          contract re-reads them and counts a disagreement, and a reset that cleared them
          instead would hide a funnel that had stopped closing its own door.
      (g) THE FLOOR IS STILL NOT A THRESHOLD. EAR_VAD_ON and EAR_VAD_OFF remain plain number
          literals and neither is computed from arm.floor. The dump measured the floor at 0 to
          0.0122 against a 0.018 lower gate for a whole session, so there is no evidence for
          an adaptive gate; and an adaptive gate derived from a per-turn sample is a detector
          whose sensitivity depends on how quiet the room was 300ms ago, which is a thing that
          can only be discovered to be wrong in a room nobody tested.
    """
    notes = []
    try:
        with open(os.path.join(ROOT, "viewer", "index.html"), encoding="utf-8") as fh:
            raw = fh.read()
    except OSError as exc:
        return FAIL, ["cannot read viewer/index.html: %s" % exc]
    src = _js_source(raw)

    # -- (a) the four functions.
    wanted = ("armRead", "armSet", "armReset", "armFloorFrame")
    absent = [n for n in wanted if "function %s(" % n not in src]
    if absent:
        return FAIL, ["viewer/index.html declares no %s, so there is no reset contract at "
                      "all and every re-arm inherits whatever the last turn left behind"
                      % " and no ".join(absent)]
    bodies = {n: _fn_body(src, n) for n in wanted}
    unreadable = [n for n, b in bodies.items() if b is None]
    if unreadable:
        return FAIL, ["could not read the body of %s by brace counting" % ", ".join(unreadable)]
    notes.append("(a) armRead, armSet, armReset and armFloorFrame are all declared")

    # -- (b) one writer, and it is armSet.
    writes = len(re.findall(r"\barm\.state\s*=(?!=)", src))
    if writes != 1:
        return FAIL, notes + ["arm.state is assigned %d times in viewer/index.html; the "
                              "single-writer discipline says exactly once, in armSet(), for "
                              "the same reason sight.state is assigned only in sightSet(): "
                              "two records of whether the microphone is live will disagree, "
                              "and the disagreement is silent" % writes]
    if not re.search(r"\barm\.state\s*=(?!=)", bodies["armSet"]):
        return FAIL, notes + ["the one assignment to arm.state is not inside armSet(), so "
                              "the function named as the single writer is not the one writing"]
    notes.append("(b) arm.state is assigned exactly once in the file, inside armSet()")

    # -- (c) the reader reads.
    if re.search(r"\barm\.\w+\s*=(?!=)", bodies["armRead"]):
        return FAIL, notes + ["armRead() assigns to arm.*, so the reader is a second writer "
                              "under a reader's name and may be called from anywhere"]
    notes.append("(c) armRead() assigns nothing, so it stays safe to call from anywhere")

    # -- (d) one door, one reset, in that order.
    starts = len(re.findall(r"recogniser\.start\(\)", src))
    resets = len(re.findall(r"(?<!function )\barmReset\(", src))
    if starts != 1:
        return FAIL, notes + ["recogniser.start() is called %d times in viewer/index.html; a "
                              "second arming path does not go through the contract, so it "
                              "arms with the last turn's gate reference and no floor of its "
                              "own, and none of the contract's counters would say so" % starts]
    if resets != 1:
        return FAIL, notes + ["armReset() is called %d times; the contract is specified to "
                              "run once per ARM, and it is behind startListening()'s "
                              "already-listening guard so that a request to arm which does "
                              "not arm - bargeTake()'s `if (!listening)` is the live one - "
                              "cannot zero the gate reference mid-answer" % resets]
    listen = _fn_body(src, "startListening")
    if listen is None:
        return FAIL, notes + ["could not read startListening()'s body"]
    at_reset = listen.find("armReset(")
    at_start = listen.find("recogniser.start()")
    if at_reset < 0 or at_start < 0 or at_reset > at_start:
        return FAIL, notes + ["startListening() does not call armReset() before "
                              "recogniser.start(), so the first frames of a new session are "
                              "measured against the previous turn's state"]
    notes.append("(d) one call to recogniser.start() in the file, one call to armReset(), "
                 "and the reset runs first inside startListening()")

    # -- (e) the terms that must be in the body.
    body = bodies["armReset"]
    terms = {
        "the gate reference zeroed": r"\becho\.ref\s*=(?!=)",
        "the reference's provenance zeroed": r"\becho\.refFrom\s*=(?!=)",
        "the over-window zeroed": r"\becho\.overSince\s*=(?!=)",
        "the floor window opened": r"\barm\.floorAt\s*=(?!=)",
    }
    thin = [name for name, pattern in terms.items() if not re.search(pattern, body)]
    if thin:
        return FAIL, notes + ["armReset() does not do %s, so that term of the contract is "
                              "named in the mandate and absent from the code"
                              % " or ".join(thin)]
    notes.append("(e) armReset() zeroes the gate reference and its provenance, clears the "
                 "over-window, and opens a fresh floor window")

    # -- (f) and the two it must not do.
    forbidden = {
        "echo.gateAt": "the acoustic gate's HOLD, which is specified to outlive the answer "
                       "that opened it - clearing it at the re-arm after a barge-in drops "
                       "the transcript of the interrupted sentence into the brain as a "
                       "question nobody asked, which is self-hearing returning through "
                       "the repair",
        "echo.gateOpens": "the gate's own tally, which echoGateWatch() owns",
        "speakDraining": "the protected funnel's drain flag - the contract re-reads it and "
                         "counts a disagreement; clearing it would hide a funnel that had "
                         "stopped closing its own door",
        "speakQueue": "the protected funnel's queue",
    }
    for name, why in forbidden.items():
        if re.search(r"\b%s\s*=(?!=)" % re.escape(name), body) or \
           re.search(r"\b%s\.(?:length\s*=|splice\(|pop\(|shift\()" % re.escape(name), body):
            return FAIL, notes + ["armReset() writes %s, which is %s" % (name, why)]
    notes.append("(f) and it writes neither the gate's hold nor the funnel's flags: "
                 "echo.gateAt, echo.gateOpens, speakDraining and speakQueue are read-only "
                 "to the contract")

    # -- (g) the floor is a measurement.
    gates = {}
    for name in ("EAR_VAD_ON", "EAR_VAD_OFF"):
        found = re.search(r"\bconst %s\s*=\s*([0-9.]+)\s*;" % name, src)
        if found:
            gates[name] = float(found.group(1))
    if len(gates) != 2:
        return FAIL, notes + ["EAR_VAD_ON and EAR_VAD_OFF are no longer plain number "
                              "literals, so the voice gates are computed from something - "
                              "and the only new number in reach is the per-turn floor, which "
                              "the dump gives no evidence for and which would make the "
                              "detector's sensitivity depend on how quiet the room was "
                              "300ms ago"]
    if not 0 < gates["EAR_VAD_OFF"] < gates["EAR_VAD_ON"]:
        return FAIL, notes + ["the voice gates read OFF %s / ON %s, which is not hysteresis"
                              % (gates["EAR_VAD_OFF"], gates["EAR_VAD_ON"])]
    for name in ("EAR_VAD_ON", "EAR_VAD_OFF"):
        if re.search(r"\b%s\s*=(?!=)\s*[^;]*arm\.floor" % name, src):
            return FAIL, notes + ["%s is computed from arm.floor: the 300ms sample is a "
                                  "MEASUREMENT and never a threshold" % name]
    sample = re.search(r"\bconst ARM_FLOOR_MS\s*=\s*(\d+)\s*;", src)
    if not sample or int(sample.group(1)) != 300:
        return FAIL, notes + ["ARM_FLOOR_MS is %s and the contract specifies 300ms of "
                              "silence" % (sample.group(1) if sample else "absent")]
    if "arm.floorVoids" not in bodies["armFloorFrame"]:
        return FAIL, notes + ["armFloorFrame() does not count a voided window, so a frame "
                              "above the lower gate is either averaged into the floor - "
                              "which makes the floor climb toward the gate turn after turn, "
                              "the exact drift the dump ruled out - or discarded in silence"]
    notes.append("(g) the floor is sampled over %dms and stays a measurement: the gates read "
                 "OFF %s / ON %s as literals, neither is derived from it, and a frame above "
                 "the lower gate voids the window and is counted"
                 % (int(sample.group(1)), gates["EAR_VAD_OFF"], gates["EAR_VAD_ON"]))
    return PASS, notes


def _ledger_row(tool_id):
    """One tool's four counts, or four zeros. Read off disk, because the ledger is the
    machine's own record of what it ran and the point is not to take the server's word."""
    try:
        with open(os.path.join(ROOT, "tools-ledger.json"), encoding="utf-8") as fh:
            row = (json.load(fh).get("tools") or {}).get(tool_id) or {}
    except Exception:                                          # noqa: BLE001
        row = {}
    return {k: int(row.get(k) or 0) for k in ("ok", "failed", "refused", "lapsed")}


def check_speaker_store():
    """25. The voiceprint store keeps embeddings, and keeps them to itself.

    WHY THIS IS A PREFLIGHT CHECK AND NOT A HARNESS ASSERTION. Every other secret in this
    house can be rotated. A voice cannot. If 192 floats describing a named person's larynx
    leave this folder there is no remedy at all, so the four rules that keep them in it are
    checked on every run, from disk, before anything else is believed:

      (a) THE FOUR HOUSE RULES, asked of voiceprint.hygiene() rather than re-implemented
          here - gitignored, Read-denied, no audio of any kind inside, and every row exactly
          EMB_DIM floats with no long opaque string that could be a wav wearing a json coat.
          A second copy of those rules in this file would be a second thing to forget.
      (b) AND THE STORE IS NOT REACHABLE OVER HTTP. Check 9 probes the paths; this step
          asks the narrower question the ear's own page raises - /speaker must answer about
          the roster in counts and names and never in numbers. An embedding on the wire is
          the one leak the page could cause on its own, because the page is the only client
          that legitimately talks to /speaker at all.
      (c) A STORE THAT DOES NOT EXIST IS A PASS, not a skip. Zero enrolments is the state
          this machine ships in and the state in which the whole doorman stands down; a
          check that went yellow over it would be yellow forever and therefore unread.
    """
    if voiceprint is None:
        return WARN, ["voiceprint.py could not be imported, so the store's rules are "
                      "unchecked: %s" % VOICEPRINT_WHY,
                      "with no module there is also no enrolment path, so nothing can have "
                      "been written - but this check is blind rather than satisfied"]

    ok, problems, notes = voiceprint.hygiene()
    detail = list(notes)
    if not ok:
        return FAIL, ["THE VOICEPRINT STORE BREAKS ITS OWN LAW"] + \
            ["!! " + line for line in problems] + detail

    # -- (b) the roster over the wire, in counts and names and nothing else.
    if state["up"]:
        status, _, data = post_json("/speaker", {"cmd": "state",
                                                "session": "preflight-speaker"},
                                    timeout=30, label="speaker state")
        got = as_json(data) or {}
        if status != 200:
            return FAIL, detail + ["POST /speaker cmd=state answered %d, so the doorman "
                                   "cannot be asked about itself" % status]
        blob = json.dumps(got)
        numbers = re.findall(r"-?0\.\d{4,}", blob)
        if numbers:
            return FAIL, detail + ["!! /speaker cmd=state returned %d long decimals: an "
                                   "embedding is being served to the page, and the page is "
                                   "the browser" % len(numbers)]
        if "embedding" in blob:
            return FAIL, detail + ["!! /speaker cmd=state returned a field called "
                                   "\"embedding\""]
        roster = got.get("enrolled") or ()
        if any("embedding" in (row or {}) for row in roster):
            return FAIL, detail + ["!! a roster row carries an \"embedding\" key"]
        detail.append("/speaker cmd=state answers with count %s, hasHands %s and %d roster "
                      "row(s) of who/how-addressed/hands/when, and carries no vector at all"
                      % (got.get("count"), got.get("hasHands"), len(roster)))

    # -- and the one number that is a threshold rather than a measurement, named out loud so
    # a silent loosening of it shows up in the preflight print rather than in a stranger's
    # spoken yes.
    detail.append("the match threshold is %.2f and the duplicate threshold %.2f against a "
                  "measured same-voice floor of 0.83 and a different-voice ceiling of 0.30"
                  % (voiceprint.MATCH_THRESHOLD, voiceprint.DUPLICATE_THRESHOLD))
    return PASS, detail


def check_citation_honesty():
    """26. A chip is a claim about the sentence above it.

    WHAT WENT WRONG, and it was live for months: chips were rendered out of the RETRIEVAL,
    which runs before the answer exists. So an error card said "the brain could not be
    reached" with four planets lit under "Drawn from"; and a refusal - "your notes say
    nothing about that", which is the correct answer when the passages clear the dial and
    still do not cover the question - was shown four notes as its evidence, with the camera
    flying to one of them. The employer was shown provenance for a sentence denying there
    was any.

    THREE STEPS, and the live one is the only one that cannot be faked by a passing build:

      (a) THE ONE GATE IS STILL IN THE SOURCE, read off disk: consumed_sources() exists, its
          two thresholds are plain literals, strip_citations() is the single place the keys
          come off, and answer_question() calls the test AFTER the answer is in hand. A
          version of this file that moved the test above call_model() would pass every
          assertion about chip counts and be measuring the retrieval again.
      (b) THE CONVERSATIONAL CLASSES CARRY NO CHIPS, live: acknowledgements, identity,
          capabilities and the connection-state questions answer at nought nodes and no
          citations. These are answered from fixed strings and the manifest, so the step
          costs no brain call.
      (c) AND THE GATE IS NOT SIMPLY SHUT. A refusal that lost its chips and a real reading
          that kept them are the same code path with different text, so a check that only
          proved absence would pass a build that stripped every chip in the house. The
          strip's reason string travels in the payload as `uncited`, and the presence of
          that key on a stripped turn is what tells a judged strip from a retrieval that
          found nothing in the first place.

    routing_proof.mjs is the deep instrument here - the conversational fixture set asserts
    chip count 0 on each, in the rendered card, which is the thing the employer sees. This
    is the chain either side of it, in seconds.
    """
    notes, warnings = [], []

    # -- (a) THE GATE, ON DISK.
    try:
        with open(os.path.join(ROOT, "server.py"), encoding="utf-8") as fh:
            src = fh.read()
    except OSError as exc:
        return FAIL, ["cannot read server.py: %s" % exc]
    for name in ("consumed_sources", "strip_citations"):
        if "def %s(" % name not in src:
            return FAIL, ["server.py declares no %s(), so there is no citation gate and the "
                          "chips are the retrieval's account of the turn again" % name]
    for const, want in (("_CONSUMED_MIN_LEN", 4), ("_CONSUMED_MIN_TOKENS", 1)):
        found = re.search(r"^%s\s*=\s*(\d+)\s*$" % re.escape(const), src, re.M)
        if not found:
            return FAIL, ["%s is no longer a plain integer literal, so the threshold that "
                          "decides whether a sentence read its evidence is computed from "
                          "something this check cannot see" % const]
        if int(found.group(1)) != want:
            return FAIL, ["%s reads %s and the documented threshold is %d - as permissive "
                          "as it can be while still catching a sentence that shares nothing "
                          "with its evidence" % (const, found.group(1), want)]
    body = _py_block(src, "answer_question")
    if body is None:
        return FAIL, ["server.py has no top-level answer_question(), so the answering path "
                      "is somewhere this check cannot read"]
    at_call = body.find("call_model(")
    at_test = body.find("consumed_sources(")
    if at_test < 0:
        return FAIL, ["answer_question() never calls consumed_sources(): the gate exists "
                      "and nothing on the answering path goes through it"]
    if 0 <= at_call and at_test < at_call:
        return FAIL, ["answer_question() tests consumed_sources() BEFORE call_model(), so "
                      "it is judging the retrieval and not the answer - which is the whole "
                      "of the bug this gate was written for"]
    strips = len(re.findall(r"\bstrip_citations\(", src)) - 1      # minus the definition
    notes.append("the gate is one function called after the answer exists, and the chips "
                 "come off in %d place%s, all of them strip_citations()"
                 % (strips, "" if strips == 1 else "s"))

    # -- (b) THE CONVERSATIONAL CLASSES, LIVE AND FREE.
    if not state["up"]:
        return WARN, notes + ["skipped the live half: the server is not reachable"]
    quiet = [
        ("thanks, that's great", "an acknowledgement"),
        ("who are you", "who he is"),
        ("what can you do", "the manifest"),
        ("how do i connect google", "the Command Panel's Google row"),
        ("is my calendar connected", "the live connection state"),
    ]
    for question, about in quiet:
        status, _, data = post_json("/chat", {"question": question,
                                             "session": "preflight-chips"},
                                    timeout=60, label="chat %s" % question)
        got = as_json(data) or {}
        if status != 200:
            return FAIL, notes + ["POST /chat %r answered %d, so the chip count cannot be "
                                  "read" % (question, status)]
        chips = len(got.get("nodes") or ()) + len(got.get("citations") or ())
        if chips:
            return FAIL, notes + ["%r is answered from %s and came back wearing %d chip(s): "
                                  "the card shows the employer evidence for a sentence that "
                                  "used none" % (question, about, chips)]
        if not str(got.get("answer") or "").strip():
            return FAIL, notes + ["%r came back with no answer at all" % question]
    notes.append("%d conversational, identity, capability and connection-state sentences "
                 "answer with nought nodes and nought citations" % len(quiet))

    # -- (c) AND THE GATE IS NOT SIMPLY SHUT. One real question at the notes, which either
    # lights chips or says in `uncited` why it did not. Both are honest; a turn that lit
    # nothing and gave no reason is the state this step exists to catch, because it is what
    # a build that strips everything looks like from the outside.
    # THE QUESTION IS HIS OWN AS OF PART 8, and it had to become his or this clause went hollow.
    # It used to ask about an invoice importer, which was a note in the demonstration corpus.
    # Quarantining that corpus did not make this check red for the wrong reason - it made it red
    # for exactly the right one: the sentence stopped being answerable from the collection, so it
    # lit no chips and offered no `uncited` reason, which is the state (c) exists to catch. The
    # cure is a question his own files hold, not a looser assertion.
    status, _, data = post_json("/chat", {"question": "what do my notes say about why I am "
                                                      "building you",
                                         "session": "preflight-chips"},
                                timeout=120, label="chat a notes question")
    got = as_json(data) or {}
    if status != 200:
        warnings.append("the notes question answered %d, so the other side of the gate is "
                        "unmeasured this run" % status)
    else:
        chips = len(got.get("nodes") or ()) + len(got.get("citations") or ())
        why = str(got.get("uncited") or "").strip()
        if chips:
            notes.append("a real notes question still lights %d chip(s), so the gate is a "
                         "judgement and not a blanket" % chips)
        elif why:
            notes.append("a real notes question lit nothing and said why: %r"
                         % first_line(why, 70))
        else:
            return FAIL, notes + ["a notes question came back with no chips and no "
                                  "`uncited` reason: chips are being dropped somewhere "
                                  "that does not account for dropping them"]

    if warnings:
        return WARN, notes + warnings
    return PASS, notes


def check_chain_protocol():
    """27. A plan of two is judged step by step, or it is not a plan.

    The chain is the first thing here where one word starts more than one subprocess, and
    everything that keeps that safe is a schema: the brain is TOLD to answer in a JSON array
    of {hand, params}, and every step of every array that arrives is looked up in the registry
    exactly and validated against that tool's own parameter list before a card is ever drawn.
    This check is about the schema half - the reading and the refusing - and it costs no brain
    call, because the array is posted rather than asked for.

    THE ONE MEASUREMENT BEHIND CLAUSE (a). The first version of the reader was a regex ending
    in "\\]\\]\\]" and it read NOTHING: the tag closes with "]]" and a JSON array closes with
    "]", so a model writes "}]]" - its own bracket doing double duty as the first of the pair -
    and the third never arrives. Nought chains out of five. json's own scanner replaced it and
    the same five plus one gave six out of six. So (a) asserts the SHAPE of the reader, not
    just its existence: a build that quietly went back to counting brackets would pass every
    live assertion below, because every plan in this file is posted correctly, and would fail
    silently in front of the employer, which is the only place it matters.

      (a) THE PROTOCOL IS TAUGHT AND THE READER IS NOT A REGEX, read off disk.
      (b) THE SCHEMA REFUSES, live, seven ways - no steps, over the cap, a step that is not an
          object, an id the registry does not have, a required field missing, a placeholder
          aimed at an address, and a placeholder pointing forwards - each naming its step, and
          each leaving NOTHING pending. A refusal that left a half-read plan in the slot would
          be a plan a later yes could confirm.
      (c) AND IT IS NOT SIMPLY SHUT: a good plan is accepted, in the shape the model really
          writes, with the placeholder still visible in the step it will land in; a plan of ONE
          falls through to the ordinary single proposal rather than becoming a numbered list of
          one item; and nothing at all is started along the way - the ledger's run counts are
          identical either side of this check.

    chain_proof.mjs is the deep instrument: the card, the click, the halt, the doorman. This is
    the schema, in a second and a half, and it is the half that has to hold before any of that
    is worth anything.
    """
    notes, warnings = [], []

    # -- (a) THE PROTOCOL AND THE READER, ON DISK.
    try:
        with open(os.path.join(ROOT, "hands.py"), encoding="utf-8") as fh:
            src = fh.read()
    except OSError as exc:
        return FAIL, ["cannot read hands.py: %s" % exc]
    if "def chain_protocol(" not in src:
        return FAIL, ["hands.py declares no chain_protocol(), so nothing tells the brain what "
                      "a plan looks like and every multi-step directive is one tool at best"]
    # THE PROTOCOL ITSELF IS CALLED, NOT GREPPED. Its source is a Python string full of
    # escaped quotes, so `"hand"` is spelt `\"hand\"` on disk and a grep for the key the
    # server actually reads finds nothing. The rendered sentence is also the thing that goes
    # to the model, which is the thing this clause is about.
    taught = server.hands.chain_protocol()
    for wanted, why in ('"hand"', "the key the array names a tool with"), \
                       ('"params"', "the key its details go under"), \
                       ("[[chain:", "the tag the reader scans for"), \
                       ("{{step", "the placeholder that passes one step's result to the next"), \
                       ("ONE INTENT IS NOT A CHAIN", "the sentence that stops a plan of one"):
        if wanted not in taught:
            return FAIL, ["the chain protocol never mentions %s - %s - so what the brain is "
                          "told and what the server reads have come apart" % (wanted, why)]
    if "at most %d steps" % server.hands.CHAIN_MAX_STEPS not in taught:
        return FAIL, ["the chain protocol does not tell the brain the step cap in the number "
                      "the server enforces, so a plan of five is asked for and refused"]
    if server.hands.registry() and taught not in server.hands.prompt_block():
        return FAIL, ["prompt_block() does not carry the chain protocol: the protocol exists "
                      "and is never sent, which is the failure that looks like a model that "
                      "cannot decompose"]
    reader = _py_block(src, "chain_tag") or ""
    if "raw_decode" not in reader:
        return FAIL, ["chain_tag() does not use a JSON scanner: a reader that counts brackets "
                      "cannot see the \"}]]\" a model actually writes, and the measured cost "
                      "of that was nought chains out of five"]
    if re.search(r"\\\]\s*\\\]\s*\\\]", reader):
        return FAIL, ["chain_tag() is matching three closing brackets again - the terminator "
                      "that never arrives"]
    cap = re.search(r"^CHAIN_MAX_STEPS\s*=\s*(\d+)\s*$", src, re.M)
    if not cap:
        return FAIL, ["CHAIN_MAX_STEPS is no longer a plain integer literal, so the longest "
                      "plan one word can approve is decided somewhere this check cannot read"]
    steps_cap = int(cap.group(1))
    if not 2 <= steps_cap <= 6:
        return FAIL, ["CHAIN_MAX_STEPS reads %d; a cap outside 2-6 is either no cap at all or "
                      "not a chain" % steps_cap]
    notes.append("the protocol is taught, appended to the prompt, and read with a JSON "
                 "scanner; at most %d steps behind one word" % steps_cap)

    if not state["up"]:
        return WARN, notes + ["skipped the live half: the server is not reachable"]

    # NOTHING MAY BE STARTED BY THIS CHECK. Read first, compared last: `refused` may move -
    # a plan that fails validation at step two counts a refusal against that tool, which is
    # the honest record - but ok and failed are runs, and there must be none.
    def started():
        try:
            with open(os.path.join(ROOT, "tools-ledger.json"), encoding="utf-8") as fh:
                rows = (json.load(fh) or {}).get("tools") or {}
        except (OSError, ValueError):
            return {}
        return {k: int(v.get("ok") or 0) + int(v.get("failed") or 0)
                for k, v in rows.items() if isinstance(v, dict)}
    before = started()

    def chain(payload, label):
        body = dict(payload)
        body["cmd"] = "chain"
        body.setdefault("door", "curl")
        status, _, data = post_json("/tools", body, timeout=60, label="chain %s" % label)
        return status, (as_json(data) or {})

    good = [{"hand": "selftest", "params": {"token": "PREFLIGHT"}},
            {"hand": "save_minutes",
             "params": {"title": "Preflight chain", "overwrite": True,
                        "minutes": "Step one said: {{step1}}"}}]

    # -- (b) SEVEN REFUSALS, EACH NAMING ITS STEP AND LEAVING NOTHING BEHIND.
    long_plan = [{"hand": "selftest", "params": {"token": "T%d" % i}}
                 for i in range(steps_cap + 1)]
    battery = [
        ("no steps at all", {"steps": []}, "chain-empty", None),
        ("%d steps, over the cap" % len(long_plan), {"steps": long_plan},
         "chain-too-long", None),
        ("a step that is not an object",
         {"steps": [good[0], "send the email"]}, "chain-bad-step", 2),
        ("an id the registry does not have",
         {"steps": [good[0], {"hand": "send_telegram", "params": {"to": "a"}}]},
         "chain-unknown-tool", 2),
        ("a required field missing at step two",
         {"steps": [good[0], {"hand": "save_minutes", "params": {"title": "No minutes"}}]},
         "chain-step-missing", 2),
        ("a placeholder aimed at an address",
         {"steps": [good[0], {"hand": "send_email",
                              "params": {"to": "{{step1}}", "subject": "Hello",
                                         "body": "Anything"}}]},
         "chain-ref-field", 2),
        ("a placeholder pointing forwards",
         {"steps": [{"hand": "save_minutes",
                     "params": {"title": "Too soon", "overwrite": True,
                                "minutes": "Step two will say: {{step2}}"}}, good[0]]},
         "chain-ref-order", 1),
    ]
    for label, payload, key, at in battery:
        status, got = chain(payload, label)
        if status == 200 or got.get("ok"):
            return FAIL, notes + ["a plan with %s was ACCEPTED (%d): the schema is not the "
                                  "gate it is written as" % (label, status)]
        if str(got.get("refused") or "") != key:
            return FAIL, notes + ["a plan with %s was refused as %r and the documented key is "
                                  "%r - the refusals have drifted from the shapes they name"
                                  % (label, got.get("refused"), key)]
        if got.get("pending") is not None:
            return FAIL, notes + ["a plan with %s left something PENDING: a half-read plan in "
                                  "the slot is a plan a later yes could confirm" % label]
        if at is not None and int(got.get("at") or 0) != at:
            return FAIL, notes + ["a plan with %s did not say which step was wrong (at=%r, "
                                  "expected %d): 'it would not work' is uselessly ambiguous "
                                  "about a plan" % (label, got.get("at"), at)]
        if not str(got.get("answer") or "").strip():
            return FAIL, notes + ["a plan with %s was refused silently" % label]
    notes.append("%d malformed plans refused, each naming its step, none left pending"
                 % len(battery))

    # -- (c) AND NOT SIMPLY SHUT. The good plan arrives as the model really writes it: the
    # array's own "]" doing double duty as the first of the tag's pair.
    said = "Right away, sir. [[chain: %s]" % json.dumps(good)
    status, got = chain({"said": said}, "the model's own text")
    if status != 200 or not got.get("ok") or not got.get("chain"):
        return FAIL, notes + ["a well-formed two-step plan in the shape a model actually "
                              "writes was not accepted (%d, %r): the reader cannot see the "
                              "terminator that really arrives"
                              % (status, first_line(got.get("error") or got.get("answer"), 70))]
    slot = got.get("pending") or {}
    shown = slot.get("steps") or []
    if len(shown) != 2 or [s.get("tool") for s in shown] != ["selftest", "save_minutes"]:
        return FAIL, notes + ["the accepted plan came back as %r, not the two steps it was "
                              "sent" % [s.get("tool") for s in shown]]
    if "{{step1}}" not in json.dumps((shown[1].get("params") or {})):
        return FAIL, notes + ["the placeholder is gone from the card's own parameters: state "
                              "passing the employer cannot see before saying yes is state "
                              "passing that says one thing and sends another"]
    if shown[1].get("uses") != [1]:
        return FAIL, notes + ["step two does not declare that it quotes step one (uses=%r), "
                              "so the card cannot say so in words" % (shown[1].get("uses"),)]
    if not str(slot.get("chainId") or "").startswith("c"):
        return FAIL, notes + ["the accepted plan carries no chain id, so the ledger cannot "
                              "record it as one transaction"]
    # AND IT IS PUT DOWN AGAIN. Preflight leaves no proposal standing: the next thing to say
    # yes in this house must not find this one waiting.
    status, _, data = post_json("/tools", {"cmd": "cancel", "door": "curl"}, timeout=30,
                                label="cancel the preflight plan")
    if (as_json(data) or {}).get("pending") is not None:
        warnings.append("the preflight plan would not cancel, so something is still pending")

    # A CHAIN OF ONE IS NOT A CHAIN.
    status, got = chain({"steps": [good[0]]}, "a plan of one")
    if status != 200 or not got.get("ok"):
        return FAIL, notes + ["a plan of one step was refused (%d): it is supposed to fall "
                              "through to the ordinary proposal" % status]
    if got.get("chain") or (got.get("pending") or {}).get("chain"):
        return FAIL, notes + ["a plan of one came back as a chain: a numbered list of one "
                              "item is ceremony, and it would take the single card's rows "
                              "away for nothing"]
    if (got.get("pending") or {}).get("tool") != "selftest":
        return FAIL, notes + ["a plan of one proposed %r"
                              % (got.get("pending") or {}).get("tool")]
    post_json("/tools", {"cmd": "cancel", "door": "curl"}, timeout=30,
              label="cancel the plan of one")
    notes.append("a good plan is accepted in the shape a model writes it, with the "
                 "placeholder visible; a plan of one falls through to the single card")

    # -- (d) THE CLEAN MOUTH, over the fuzz set, and the draft.
    #
    # chain_tag() has four refusal paths and every one of them returns the model's text
    # UNTOUCHED, which is right for a decision and wrong for a mouth; and the ordinary answer
    # path recorded that a chain tag was seen without ever taking one out. So a model that
    # wrote a plan while answering a question about the notes put [[chain: [{"hand": ... on
    # the screen and into the voice. hands.clean_mouth() is the cure and this is its proof.
    #
    # THE CONTROL IS HALF THE CLAUSE. A blanket sweep of "{{", "}}" and bracketed arrays
    # would pass every fuzz case below and mangle an honest answer about JSON, so the last
    # fixture must come back BYTE-IDENTICAL. Without it this clause would be satisfied by a
    # function that deleted every brace on the page.
    fuzz = [
        ("truncated JSON",
         'Very good, sir. [[chain: [{"hand": "selftest", "params": {"token": "A"}}, {"hand"'),
        ("a missing terminator",
         'Right away. [[chain: [{"hand": "selftest", "params": {}}, '
         '{"hand": "selftest", "params": {}}]'),
        ("a doubled terminator",
         'Right away. [[chain: [{"hand": "selftest", "params": {}}]]]] and that is the plan.'),
        ("a tag with no array after it", 'Certainly, sir. [[chain: nothing at all here]]'),
        ("an array with no tag around it",
         'Here is the plan: [{"hand": "selftest", "params": {"token": "A"}}, '
         '{"hand": "save_minutes", "params": {"minutes": "{{step1}}"}}]'),
        ("a stray placeholder", "I shall put {{step1}} into the minutes, sir."),
        ("a malformed tool tag", 'One moment. [[tool: send_email | {"to": "a@b.com", "sub'),
    ]
    # '[{"' IS THE BRACKET ARRAY ITSELF, and it is listed separately from '"hand":' because
    # the two catch different survivals: a step array stripped of its "hand" keys would still
    # be a wall of JSON on the answer surface, and the mandate forbids the bracket array and
    # not merely the key inside it. It is safe to forbid here and NOT in the control below,
    # which is checked on its own and is allowed its brackets because it is ABOUT them.
    forbidden = ("{{", "}}", '"hand":', "[[chain", "[[tool", '[{"')
    for name, text in fuzz:
        out = server.hands.clean_mouth(text)
        left = [mark for mark in forbidden if mark in out]
        if left:
            return FAIL, notes + ["%s survived the mouth: %s still on the answer surface in "
                                  "%r - this is the text the page prints and the voice reads "
                                  "out" % (name, ", ".join(left), first_line(out, 60))]
        if not out:
            return FAIL, notes + ["%s cleaned down to nothing and the caller would have had "
                                 "to invent a sentence: every fixture here carries prose "
                                 "around the tag on purpose" % name]
    control = ('JSON is written like this, sir: {"name": "Addi", "roles": [{"a": 1}, '
               '{"b": 2}]} - braces for objects, brackets for arrays.')
    if server.hands.clean_mouth(control) != control:
        return FAIL, notes + ["THE CONTROL WAS MANGLED. An answer that is legitimately about "
                              "JSON came back changed: %r. The mouth is meant to remove this "
                              "protocol and nothing else, and a blanket brace sweep would "
                              "pass every fuzz case above and break every honest answer about "
                              "a data format" % first_line(server.hands.clean_mouth(control), 70)]
    notes.append("the fuzz set (%d shapes) leaves no tag, brace pair, \"hand\" key or bracket "
                 "array on any answer surface; the control answer about JSON is byte-identical"
                 % len(fuzz))

    # AND THE STATE PASSING, INTO A DRAFT, WITH NOTHING SENT. save_minutes already proves a
    # placeholder end to end into a file; the field that matters more is send_email's body,
    # and that one can never be proven by running it. So it is proven the way send_email.py's
    # own note says the draft probe does it: _paste() substitutes exactly as the runner will,
    # and build() - the same function the real send serializes with - turns it into the bytes
    # that would travel. No transport is called, no token is read, nothing leaves. What is
    # asserted is that the canary from step one is IN those bytes and the placeholder is not.
    #
    # build() IS IMPORTED AND CALLED IN PROCESS, not run as a subprocess, and that is safe
    # for one reason worth stating: it takes four strings and returns RFC 2822 bytes. It
    # reads no config, opens no socket and touches no token - main() does all of that, and
    # main() is not called. Importing the module runs its top level, which is imports and
    # two compiled patterns.
    mail = next((t for t in server.hands.registry() if t["id"] == "send_email"), None)
    if not mail:
        return FAIL, notes + ["the registry has no send_email, so the draft cannot be proven"]
    try:
        import importlib.util
        _spec = importlib.util.spec_from_file_location(
            "_preflight_send_email", os.path.join(ROOT, "tools", "send_email.py"))
        _mod = importlib.util.module_from_spec(_spec)
        _spec.loader.exec_module(_mod)
    except Exception as exc:                                   # noqa: BLE001
        return FAIL, notes + ["tools/send_email.py would not import: %s" % exc]
    if not hasattr(_mod, "build"):
        return FAIL, notes + ["tools/send_email.py has no build(), so the draft the real send "
                              "serializes cannot be the one this check inspects"]
    canary = "DRAFT-CANARY-%d" % int(time.time())
    filled, pasted = server.hands._paste(
        {"to": "team@example.com", "subject": "Yesterday's minutes",
         "body": "As promised, the self test said: {{step1}} - and nothing was sent."},
        mail["params"], {1: "Self test passed, token %s" % canary})
    if pasted != 1 or canary not in filled["body"]:
        return FAIL, notes + ["a placeholder in send_email's BODY did not take step one's "
                              "result: %r" % first_line(filled.get("body"), 70)]
    if "{{" in filled["body"]:
        return FAIL, notes + ["the placeholder is still in the body after substitution, so "
                              "this machine's own markup would have gone out in a letter"]
    raw = _mod.build(filled["to"], filled["subject"], filled["body"],
                     "galaxy@example.invalid")
    # READ BACK THE WAY THE RECIPIENT WOULD, and this is a correction rather than a nicety.
    # The first draft of this clause searched the RAW bytes for the canary and failed a
    # perfectly good draft: set_content() encodes and soft-wraps at 78 columns, so a long
    # token arrives split across an "=\n" and is not in the bytes as a substring at all.
    # What the clause is about is what LANDS, so the payload is decoded first.
    import email as _email
    parsed = _email.message_from_bytes(raw)
    landed = parsed.get_payload(decode=True) or b""
    draft = landed.decode("utf-8", "replace")
    if canary not in draft:
        return FAIL, notes + ["the substituted body did not survive serialization: the draft "
                              "that would travel does not contain step one's result (%d bytes "
                              "decoded from %d)" % (len(landed), len(raw))]
    if "{{step1}}" in draft or "{{step1}}" in raw.decode("utf-8", "replace"):
        return FAIL, notes + ["the serialized draft still carries {{step1}}"]
    if parsed.get("Subject") != filled["subject"]:
        return FAIL, notes + ["the draft's Subject header reads %r" % parsed.get("Subject")]
    notes.append("state passing lands in a DRAFT as well as in minutes: step one's result is "
                 "in the serialized bytes, the placeholder is not, and no transport was "
                 "called - nothing was sent")

    after = started()
    moved = sorted(k for k in set(before) | set(after)
                   if after.get(k, 0) != before.get(k, 0))
    if moved:
        return FAIL, notes + ["something RAN while this check only ever proposed: %s moved "
                              "in the ledger" % ", ".join(moved)]
    notes.append("and nothing was started: every run count in the ledger is where it was")

    if warnings:
        return WARN, notes + warnings
    return PASS, notes


def check_context_budget():
    """28. THE LAW OF GROWING SESSIONS: a cap, an order, and a machine that knows it forgot.

    This check exists because of one answer. Asked at turn 17 of an instrumented session what
    it had been asked FIRST that day, this machine said - with complete confidence and in its
    own voice - that the first question had been about where the employer lived, and that the
    barista training plan had come second. Those were turns 9 and 14. They were also, exactly,
    the two oldest pairs still inside a four-pair window, and nothing in the prompt said there
    had been eight turns before them.

    THE MODEL DID NOT INVENT ANYTHING. It answered honestly about the only history it was
    given, and the history was the lie - by omission. Every cure aimed at the brain would have
    missed, which is why PART 0 names the layer before curing it.

    So the cap is declared, the order is fixed, eviction is a rule instead of five copies of
    one `del`, and what falls out of the window is SUMMARISED rather than dropped. Seven
    clauses, each naming what goes wrong without it:

      (a) THE CAP EXISTS AND IS ABOVE THE FLOOR. CONTEXT_FLOOR is what the protected blocks
          alone can demand - top-k notes, retrieved chunks, the manifest, the persona. A cap
          below it would be a cap that evicts the retrieval to fit the retrieval.
      (b) THE ORDER IS THE ONE DECLARED, and the protected set is exactly the blocks that may
          never be evicted. A build that quietly moved `retrieval` out of that set would pass
          every size assertion and lose citations on long sessions only.
      (c) THE PROMPT IS COMPOSED, NOT CONSTRUCTED TWICE. prompt_block() must equal
          manifest + "\\n" + protocol, because the budget measures the parts and the wire
          carries the whole, and two functions composing one string can disagree.
      (d) EVERY BLOCK IS ACCOUNTED: the sum of the measured blocks equals the characters
          really on the wire. This is the clause that catches a block nobody charged for -
          the base system prompt was 2,327 unaccounted characters when the budget first ran.
      (e) THE FIRST PAIR IS PINNED FOR THE LIFE OF THE SESSION, because turn 1 is precisely
          the question the machine got wrong.
      (f) NOTHING IS CUT MID-SENTENCE. Every cut in this mechanism falls on a sentence or a
          whole line, so a summary cannot end halfway through a claim and read as a different
          claim.
      (g) AND THE SUMMARY SAYS WHAT IT IS. A model handed a summary that does not announce
          itself treats it as the transcript and quotes from it.
    """
    notes = []
    dump = server
    # -- (a) and (b), read off the SERVER and not off a copy of the numbers.
    status, _head, data = http_call("GET", "/session/dump?session=preflight-28&limit=1",
                                    timeout=30, label="the session dump")
    live = as_json(data) or {}
    if status != 200 or not live.get("ok"):
        return FAIL, ["GET /session/dump did not answer (%d): the budget cannot be asserted "
                      "against the numbers the server is really using, only against a second "
                      "copy of them" % status]
    cap, floor = live.get("cap"), live.get("floor")
    if not isinstance(cap, int) or not isinstance(floor, int):
        return FAIL, ["the dump declares no cap and floor (%r, %r)" % (cap, floor)]
    if cap <= floor:
        return FAIL, ["MAX_CONTEXT %d is not above CONTEXT_FLOOR %d: the protected blocks "
                      "alone can ask for more than the cap allows, so the only way to fit "
                      "would be to evict the retrieval that was the point of the turn"
                      % (cap, floor)]
    if (cap, floor) != (dump.MAX_CONTEXT, dump.CONTEXT_FLOOR):
        return FAIL, ["the wire says cap %d floor %d and the module says %d/%d"
                      % (cap, floor, dump.MAX_CONTEXT, dump.CONTEXT_FLOOR)]
    notes.append("the cap is %d characters against a floor of %d, declared on the wire and "
                 "not only in a comment (%d%% headroom)"
                 % (cap, floor, round(100.0 * (cap - floor) / cap)))

    order = list(live.get("order") or [])
    if order != list(dump.CONTEXT_BLOCKS):
        return FAIL, notes + ["the assembly order on the wire is %r and the module's is %r"
                              % (order, list(dump.CONTEXT_BLOCKS))]
    for wanted in ("persona", "manifest", "chain-protocol", "retrieval"):
        if wanted not in (live.get("protected") or []):
            return FAIL, notes + ["%r is not in the protected set, so eviction is allowed to "
                                  "take it: the retrieval hits are the grounding and the "
                                  "persona is the voice, and a session long enough to evict "
                                  "either would answer in a stranger's words from no source"
                                  % wanted]
    if order.index("retrieval") > order.index("recent-turns"):
        return FAIL, notes + ["the retrieval sits after the recent turns in the precedence "
                              "order, so a long history outranks the passages the answer is "
                              "supposed to cite"]
    notes.append("the order is %s, and %s can never be evicted"
                 % (" -> ".join(order), ", ".join(live.get("protected") or [])))

    # -- (c) ONE STRING, TWO FUNCTIONS, ASSERTED RATHER THAN TRUSTED.
    manifest, protocol = dump.hands.prompt_parts()
    whole = dump.hands.prompt_block()
    if not manifest or not protocol:
        return FAIL, notes + ["prompt_parts() returned an empty half (%d, %d): the budget "
                              "cannot charge for a block that is not there"
                              % (len(manifest), len(protocol))]
    if whole != manifest + "\n" + protocol:
        return FAIL, notes + ["prompt_block() is no longer manifest + newline + protocol "
                              "(%d vs %d): the budget measures the parts and the wire carries "
                              "the whole, so the two would disagree by however much this has "
                              "drifted" % (len(whole), len(manifest) + 1 + len(protocol))]
    notes.append("the hands block is a composition: manifest %d + protocol %d = the %d bytes "
                 "it always was" % (len(manifest), len(protocol), len(whole)))

    # -- (d) EVERY CHARACTER ON THE WIRE IS CHARGED TO A BLOCK.
    messages, plan = dump.assemble(system="A persona of some length, sir. " * 8,
                                   manifest=manifest, protocol=protocol,
                                   ask="what do my notes say about why I am building you",
                                   heading="Notes and documents you may use, and nothing else:",
                                   evidence="A passage. " * 40,
                                   history=[{"role": "user", "content": "one"},
                                            {"role": "assistant", "content": "two"}],
                                   older="\n\nEARLIER IN THIS CONVERSATION. 3 turn(s).\n",
                                   label="preflight-28")
    wire = sum(len(str(m.get("content") or "")) for m in messages)
    if plan.get("chars") != wire:
        unaccounted = wire - int(plan.get("chars") or 0)
        return FAIL, notes + ["the budget accounts for %d characters and the wire carries %d, "
                              "%d of them charged to nothing. A block nobody counts is a block "
                              "eviction cannot protect and the cap cannot see"
                              % (plan.get("chars"), wire, unaccounted)]
    if plan.get("overCap"):
        return FAIL, notes + ["an ordinary assembly reports itself over the cap"]
    notes.append("an assembly of %d characters is accounted to the character: every block on "
                 "the wire is charged to one of the %d" % (wire, len(order)))

    # -- (e) (f) (g) THE EVICTION RULE, exercised on its own session and then forgotten.
    #
    # SIXTEEN SYNTHETIC PAIRS AND NO MODEL CALL. summarise_pairs() is deliberately rule-based:
    # a summariser is a language model, a language model can invent, and an invention written
    # into the history is a FALSE MEMORY this machine will then cite for the rest of the
    # session and never be able to detect. So the summary is built from the turns themselves,
    # which is also why it can be asserted here for nothing.
    session = "preflight-28-%d" % int(time.time())
    hist = []
    for i in range(1, 17):
        hist += [{"role": "user", "content": "Question number %d, sir. It has two sentences. "
                                             "This is the second one." % i},
                 {"role": "assistant", "content": "Answer number %d. Also two sentences. "
                                                  "Here is the second." % i}]
        dump.evict_history(hist, session)
    summary = dump.older_block(session)
    try:
        if len(hist) != dump.HISTORY_TURNS * 2:
            return FAIL, notes + ["after sixteen pairs the window holds %d messages and the "
                                  "rule says %d" % (len(hist), dump.HISTORY_TURNS * 2)]
        if "Question number 1," not in summary:
            return FAIL, notes + ["THE FIRST PAIR IS NOT PINNED. Turn 1 has fallen out of the "
                                  "summary, which is the exact question this check exists for: "
                                  "asked what it was asked first, the machine would again "
                                  "answer confidently about the oldest thing it happened to "
                                  "still be holding"]
        if len(summary) > dump.OLDER_MAX:
            return FAIL, notes + ["the summary is %d characters against a cap of %d"
                                  % (len(summary), dump.OLDER_MAX)]
        for line in summary.splitlines():
            line = line.strip()
            if not line or not line[0].isdigit():
                continue
            if not line.endswith((".", "!", "?")):
                return FAIL, notes + ["a summary line ends mid-sentence: %r. Every cut in this "
                                      "mechanism is supposed to fall on a sentence boundary, "
                                      "because half a claim reads as a different claim"
                                      % first_line(line, 70)]
        # SIXTEEN PAIRS WENT IN AND THE WINDOW KEEPS HISTORY_TURNS OF THEM, so the summary
        # stands for the difference and not for sixteen. Computed rather than written down,
        # because the first draft of this clause asserted "16" and failed a correct summary.
        stood_for = 16 - dump.HISTORY_TURNS
        if "SUMMARY" not in summary or "%d turn(s)" % stood_for not in summary:
            return FAIL, notes + ["the summary does not announce that it IS a summary, or does "
                                  "not say it stands for %d turns. A model handed an "
                                  "unlabelled summary treats it as the transcript: %r"
                                  % (stood_for, first_line(summary, 70))]
        if "no longer quoted" not in summary:
            return FAIL, notes + ["the summary counts the turns it dropped but never says they "
                                  "were dropped, so there is no sentence for the machine to "
                                  "say 'I no longer hold that' from"]
        notes.append("sixteen pairs leave a %d-pair window and a %d-character summary: turn 1 "
                     "pinned, the middle counted but not quoted, no line cut mid-sentence, and "
                     "the heading says it is a summary"
                     % (dump.HISTORY_TURNS, len(summary)))
    finally:
        # THIS CHECK LEAVES NO CONVERSATION BEHIND. A synthetic session in the summary store
        # would be sixteen invented turns the next real question could be grounded in.
        dump.forget_older(session)
    if dump.older_block(session):
        return FAIL, notes + ["the synthetic session survived forget_older()"]
    return PASS, notes


def check_grounding_audit():
    """29. EVERY ANSWER CARRIES A GROUNDING CLASS, AND A CLASS IS NOT A ROUTE.

    notes, web, persona, state, refusal, chain. The class names what the sentence STANDS ON,
    and it is a separate field from `kind` because the hunt found two turns where the two
    disagreed and both were filed as hallucinations by a rule that read `kind`:

      "what is my home address" came back kind=notes with no cited passage - and the reading
        that settles it is opened=false, semOpened=false. NEITHER HALF OF THE RETRIEVAL EVER
        OPENED. The notes were not consulted and found wanting; they were never read. The
        answer was a refusal, grounded in an absence, and correct.
      "what did I ask you about first today" was also kind=notes with nothing opened, and it
        stood on the summarised-history block. Its ground is this conversation - state.

    So `kind` names the door and `grounds` names the ground, and this check asserts the
    distinction holds live, on the four classes a typed call can reach without a browser, a
    voice or a card. The rest - a chain's class, and the judge's half - belong to
    session_proof.mjs and chain_proof.mjs, which have the instruments for them.

      (a) THE SIX ARE DECLARED ON THE WIRE, so a harness cannot carry a stale copy of the list.
      (b) A REAL NOTES QUESTION IS CLASSED notes AND HAS SOMETHING TO SHOW FOR IT - a cited
          passage or a door that opened. This is the clause that makes the class a claim.
      (c) AN IDENTITY QUESTION IS classed persona WITH ZERO LOOKUPS, and a connection question
          is classed state, because it read the live grant. The two cannot swap: a persona
          answer that claimed live state would be asserting a reading it never took.
      (d) A WEB ANSWER CARRIES FETCHED SOURCES or it is not classed web. A web class with no
          source is the shape of a hallucination with a citation chip on it.
      (e) AND NO ANSWER IS CLASSED notes OR web WITH NOTHING BEHIND IT. Those two classes
          assert a source; the others do not. A red here is a claim with no ground.
    """
    notes = []
    session = "preflight-29-%d" % int(time.time())
    post_json("/reset", {"session": session}, timeout=30, label="a clean room for 29")

    def ask(question, label):
        status, _head, data = post_json("/chat", {"question": question, "session": session},
                                        timeout=180, label=label)
        return status, (as_json(data) or {})

    def graded(want_n):
        status, _head, data = http_call(
            "GET", "/session/dump?session=%s&limit=12" % session, timeout=30,
            label="the graded turns")
        rows = ((as_json(data) or {}).get("turns") or []) if status == 200 else []
        return rows[-want_n:] if rows else []

    status, _head, data = http_call("GET", "/session/dump?session=%s&limit=1" % session,
                                    timeout=30, label="the class list")
    declared = (as_json(data) or {}).get("groundingClasses") or []
    if sorted(declared) != sorted(server.GROUNDING_CLASSES):
        return FAIL, ["the dump declares %r and the module has %r"
                      % (declared, list(server.GROUNDING_CLASSES))]
    notes.append("the six classes are declared on the wire: %s" % ", ".join(declared))

    fixtures = [
        # HIS OWN QUESTION AS OF PART 8 - see check 26 for why the old one had to go. This one
        # draws two nodes and four citations off his two captures, so `notes` is the class the
        # ground actually supports rather than the class the door was named after.
        ("what do my notes say about why I am building you", "notes", "a real notes question"),
        ("who are you", "persona", "an identity question"),
        ("is my calendar connected", "state", "a live-state question"),
    ]
    for question, want, why in fixtures:
        status, got = ask(question, why)
        if status != 200:
            return FAIL, notes + ["%s did not answer (%d)" % (why, status)]
    rows = graded(len(fixtures))
    if len(rows) != len(fixtures):
        return FAIL, notes + ["the dump returned %d graded turns for %d questions"
                              % (len(rows), len(fixtures))]
    for row, (question, want, why) in zip(rows, fixtures):
        got = row.get("grounds") or "(none)"
        scores = row.get("scores") if isinstance(row.get("scores"), dict) else {}
        if got != want:
            return FAIL, notes + ["%s was classed %r and should be %r - kind was %r, route %r. "
                                  "A class that follows the door instead of the ground is the "
                                  "bug this check exists for"
                                  % (why, got, want, row.get("kind"), row.get("route"))]
        if want == "notes" and not (row.get("cited") or scores.get("opened")
                                    or scores.get("semOpened")):
            return FAIL, notes + ["a turn classed notes has no cited passage and no door that "
                                  "opened: the class asserts a source it cannot show"]
        if want == "persona" and row.get("cited"):
            return FAIL, notes + ["an identity answer cited %d passage(s): it is answered from "
                                  "the block and reaches the notes exactly never"
                                  % len(row.get("cited") or [])]
        if want in ("persona", "state") and row.get("sources"):
            return FAIL, notes + ["a %s answer carried fetched web sources" % want]
    notes.append("a notes question is classed notes and shows a passage; an identity question "
                 "is classed persona with nothing cited; a connection question is classed "
                 "state because it read the live grant")

    # -- (d) and (e). The web turn is last because it is the slow one, and its class is the
    # one that must never be worn without a source behind it.
    status, got = ask("what is the current price of bitcoin", "a web question")
    if status != 200:
        return FAIL, notes + ["the web question did not answer (%d)" % status]
    row = (graded(1) or [{}])[0]
    if got.get("kind") == "web" and got.get("sources"):
        if row.get("grounds") != "web":
            return FAIL, notes + ["a fetched web answer is classed %r" % row.get("grounds")]
        if not row.get("sources"):
            return FAIL, notes + ["the graded turn kept no sources, so nothing downstream can "
                                  "check the class against what was fetched"]
        notes.append("the web answer is classed web and carries %d fetched source(s)"
                     % len(row.get("sources") or []))
    else:
        # A SEARCH THAT FOUND NOTHING IS NOT A FAILING CHECK. What matters is that it did not
        # then wear the class: an unsourced answer claiming `web` is a hallucination with a
        # citation chip on it, and that is the assertion, either way the search went.
        if row.get("grounds") == "web":
            return FAIL, notes + ["the search fetched nothing and the answer is STILL classed "
                                  "web: the class asserts a source that does not exist"]
        notes.append("the search found nothing this time and the answer did not wear the web "
                     "class for it (classed %r)" % (row.get("grounds") or "left to the judge"))

    reds = [r.get("n") for r in graded(6)
            if r.get("grounds") in ("notes", "web")
            and not (r.get("cited") or r.get("sources")
                     or (r.get("scores") or {}).get("opened")
                     or (r.get("scores") or {}).get("semOpened"))]
    if reds:
        return FAIL, notes + ["turn(s) %s claim a source class with nothing behind them" % reds]
    notes.append("and no answer in this session wears notes or web with nothing behind it")
    return PASS, notes


def check_world_clock():
    """30. THE CLOCK COSTS NOTHING, KNOWS WHAT DAY IT IS THERE, AND REFUSES WHAT IT CANNOT PLACE.

    Before this class existed, "what time is it in Tokyo" was a WEB SEARCH: a round trip, a rate
    limit and a citation chip, spent computing a subtraction. So the first clause of this check is
    about cost, and the second is about the thing the subtraction gets wrong.

      (a) THE ROUTE IS READY AND NAMES ITS DATABASE. Naming it is not decoration. stdlib
          `zoneinfo` IMPORTS SUCCESSFULLY ON A MACHINE WITH NO TIMEZONE DATA - which is this
          machine - so a module that trusted the import would have fallen back to something
          hand-written, read identically right for six months, and been an hour out every March.
          The source string is how that failure becomes visible while it is still cheap.
      (b) IT IS TRIED AFTER THE FOUR, NEVER INSTEAD OF THEM. PROTECTED_CLASSES is still exactly
          the four the mandate named; the clock lives in UNPAID_CLASSES beside them. This is
          asserted structurally because the cheap way to add a fifth class is to append it to
          the four, and that edits a list the mandate says not to touch.
      (c) A CLOCK QUESTION COSTS NOTHING: route clock, zero nodes, zero lookups, and no chip to
          show. An answer with a source chip on it here would mean the funnel fell through.
      (d) THE DAY IS COMPUTED, NOT INFERRED FROM THE OFFSET. Apia and Pago Pago are a hundred
          miles apart at +13 and -11: they read THE SAME MINUTE ON DIFFERENT DAYS, always. A day
          offset derived from the hour difference makes them identical, and the sentence that
          says "tomorrow" then says it about the wrong island. So the two are asked live and
          their day words are required to DIFFER - which needs no fixed instant, because the
          twenty-four hours between them never closes.
      (e) A PLACE THAT DOES NOT EXIST IS REFUSED, WITH NO TIME IN THE REFUSAL. A nearest-match
          guess reads exactly like a right answer, and a clock confidently in the wrong
          hemisphere is worse than no clock at all.
      (f) AND THE CLASS IS NOT A DRAGNET. "what time did I write that note" has an answer in his
          notes and must not be taken by the clock. A protected class that grew one word too far
          answers the wrong question confidently and for free, which is harder to notice than a
          slow right answer.
    """
    notes = []
    if getattr(server, "worldclock", None) is None:
        return FAIL, ["server.py imported no worldclock module at all"]

    status, _head, data = http_call("GET", "/clock", timeout=30, label="the clock route")
    if status != 200:
        return FAIL, ["GET /clock answered %d" % status]
    clock = as_json(data) or {}
    if clock.get("ok") is not True:
        return FAIL, ["there is no usable timezone database on this machine: %r"
                      % clock.get("why")]
    source = str(clock.get("source") or "")
    places = int(clock.get("places") or 0)
    if not source:
        return FAIL, ["the route will not say which zone database answered, so a silent "
                      "fallback to a hand-written offset table would be invisible until March"]
    if places < 100:
        return FAIL, ["it knows only %d places; a table that refuses Paris is a refusal the "
                      "employer reads as a broken feature" % places]
    if clock.get("lookups") != 0 or (clock.get("nodes") or []) != []:
        return FAIL, ["the route declares %r lookups and %d nodes; it is meant to cost nothing"
                      % (clock.get("lookups"), len(clock.get("nodes") or []))]
    notes.append("the clock reads %s, knows %d places, and the route costs nothing"
                 % (source, places))

    # -- (b) the four are untouched, and the fifth stands beside them rather than inside them.
    if tuple(server.PROTECTED_CLASSES) != ("confirmation", "meta", "identity", "directive"):
        return FAIL, notes + ["PROTECTED_CLASSES is now %r - the four the mandate named have "
                              "been edited" % (tuple(server.PROTECTED_CLASSES),)]
    if tuple(server.UNPAID_CLASSES) != tuple(server.PROTECTED_CLASSES) + ("clock",):
        return FAIL, notes + ["UNPAID_CLASSES is %r; the clock is meant to be tried after all "
                              "four have declined" % (tuple(server.UNPAID_CLASSES),)]
    notes.append("the four protected classes are as the mandate wrote them and the clock is "
                 "tried after them, not among them")

    session = "preflight-30-%d" % int(time.time())
    post_json("/reset", {"session": session}, timeout=30, label="a clean room for 30")

    def ask(question, label):
        status, _head, data = post_json("/chat", {"question": question, "session": session},
                                        timeout=180, label=label)
        return status, (as_json(data) or {})

    # -- (c) one ordinary clock question, and what it did NOT spend.
    status, tokyo = ask("what time is it in Tokyo", "the clock question")
    if status != 200:
        return FAIL, notes + ["the clock question did not answer (%d)" % status]
    if tokyo.get("route") != "clock" or tokyo.get("clock") is not True:
        return FAIL, notes + ["'what time is it in Tokyo' was routed %r, which means it is "
                              "being paid for somewhere else" % tokyo.get("route")]
    if tokyo.get("clockPlace") != "Tokyo":
        return FAIL, notes + ["it resolved the place as %r" % tokyo.get("clockPlace")]
    if (tokyo.get("nodes") or []) or tokyo.get("lookups") or (tokyo.get("sources") or []):
        return FAIL, notes + ["the clock answer carried %d node(s), %r lookup(s) and %d "
                              "source(s): this sentence used to be a web search and the whole "
                              "point of the class is that it no longer is"
                              % (len(tokyo.get("nodes") or []), tokyo.get("lookups"),
                                 len(tokyo.get("sources") or []))]
    said = str(tokyo.get("answer") or "")
    if not re.search(r"\d{1,2}:\d\d|o'clock|noon|midnight", said):
        return FAIL, notes + ["the sentence carries no clock at all: %r" % said]
    if re.search(r"\b\d{1,2}\s+\d\d\b", said):
        return FAIL, notes + ["the time is written as two loose numbers in %r, which a neural "
                              "voice reads as two numbers rather than one time" % said]
    notes.append("a clock question answers from a table on this disk: 0 nodes, 0 lookups, "
                 "0 sources - %s" % said)

    # -- (d) the date line. Asked live and in either order; the twenty-four hours between these
    # two never closes, so no fixed instant is needed to make the claim.
    days = {}
    for place in ("Apia", "Pago Pago"):
        status, got = ask("what time is it in %s" % place, "the clock in %s" % place)
        if status != 200 or got.get("clockPlace") != place:
            return FAIL, notes + ["%s did not resolve (%d, %r)"
                                  % (place, status, got.get("clockPlace"))]
        word = re.search(r"\b(yesterday|today|tomorrow)\b", str(got.get("answer") or ""), re.I)
        if not word:
            return FAIL, notes + ["the reading for %s carries no day word: %r - and a clock "
                                  "reading with the day left off is the half of the answer "
                                  "that causes the missed call" % (place, got.get("answer"))]
        days[place] = word.group(1).lower()
    if days["Apia"] == days["Pago Pago"]:
        return FAIL, notes + ["Apia and Pago Pago both read %r. They are at +13 and -11: the "
                              "same minute on different days, always. Equal day words mean the "
                              "offset is being divided instead of the dates compared"
                              % days["Apia"]]
    notes.append("the date line holds: Apia is %s and Pago Pago is %s, against his own clock"
                 % (days["Apia"], days["Pago Pago"]))

    # -- (e) a place that is not a place.
    status, fake = ask("what time is it in Narnia", "a place that does not exist")
    if status != 200:
        return FAIL, notes + ["the made-up place did not answer (%d)" % status]
    refusal = str(fake.get("answer") or "")
    if fake.get("clock") is not True or fake.get("clockPlace"):
        return FAIL, notes + ["Narnia was handled as %r/%r rather than refused by the clock; "
                              "falling through means a search engine is asked what time it is "
                              "in Narnia, and it will answer something"
                              % (fake.get("route"), fake.get("clockPlace"))]
    if not re.search(r"i do not know where", refusal, re.I):
        return FAIL, notes + ["the refusal does not say plainly that it does not know: %r"
                              % refusal]
    if re.search(r"\d{1,2}:\d\d|o'clock|noon|midnight", refusal):
        return FAIL, notes + ["there is a TIME in the refusal: %r. A nearest-match guess reads "
                              "exactly like a right answer" % refusal]
    if (fake.get("nodes") or []) or fake.get("lookups"):
        return FAIL, notes + ["the refusal still spent %d node(s) and %r lookup(s)"
                              % (len(fake.get("nodes") or []), fake.get("lookups"))]
    notes.append("a place it cannot find is refused plainly, with no time in the refusal and "
                 "nothing spent on it - %s" % refusal)

    # -- (f) and it takes only the questions that are about a clock.
    for question in ("what time did I write that note", "how much time is left",
                     "what is the weather in Tokyo"):
        status, got = ask(question, "a question the clock must decline")
        if status != 200:
            return FAIL, notes + ["%r did not answer (%d)" % (question, status)]
        if got.get("clock") is True:
            return FAIL, notes + ["%r was taken by the clock (place %r). A dragnet class answers "
                                  "the wrong question confidently and for free"
                                  % (question, got.get("clockPlace"))]
    notes.append("and it declines the three sentences that only look like clock questions")
    return PASS, notes


def check_connectors_board():
    """31. THE CONNECTORS BOARD READS TWO ROUTES, AND CANNOT RUN A HAND.

    The board is the first thing in the deck that puts the registry and the Google grant side by
    side on one grid. That is useful and it is also the two places this round could leak from, so
    every clause here is about a thing the board must NOT be able to do.

      (a) THE TWO ROUTES ANSWER, AND NEITHER HANDS THE BROWSER A CREDENTIAL. /google and /tools
          are now read by a grid that will be screenshotted into a lookbook. A route that
          started carrying an access token, a refresh token or a client secret would put it on
          that grid and into that plate, and nothing in the page would be wrong. So the payloads
          are searched here, where the failure is cheap.
      (b) AND /tools STILL HIDES THE SCRIPT PATH. The public registry is meant to publish
          id/name/capabilities/params/timeout and nothing else: a page that learned
          `send_email.py` learned the name of a file it might one day be persuaded to ask for.
      (c) EVERY NAMED TILE SPEAKS FOR A HAND THAT EXISTS. The four ids the board claims by name
          are the four it leaves out of the hand grid, so an id that drifted - a hand renamed in
          registry.json, the constant left alone - would show the hand TWICE: once as a named
          tile reading "no hand in the registry" and once as its own tile. Both true, together
          incoherent.
      (d) NO HAND TILE CARRIES A VERB. The Halt Law gives the executor one door with a gate on
          it: a proposal, a spoken yes, one run. A button on a grid of nine tiles is a second
          door, and a second door is the whole law gone. Asserted against the tile-building code
          with the comments stripped, so the paragraph that promises it cannot satisfy it.
      (e) NO SHARED READING SLOT. Two boards briefly wrote one `board.read`, which left the
          World Clock row reporting "0 places known" about an organ that was working - the row
          was reading the Connectors board's answer. Each board writes its own slot by name and
          `board.read` is a getter, so this cannot come back quietly.
      (f) AND THE ROW IS PAINTED FROM THE SAME READING AS THE GRID. boardOpen's read callback
          repaints the order sheet as well as the board; without that the row keeps its
          not-read-yet line under a grid full of answers.
      (g) POST /tools RUNS NOTHING. The registry is a readable list and not an executor.
    """
    notes = []

    # -- (a) the two routes, and what they must not carry.
    status, _head, data = http_call("GET", "/google", timeout=30, label="the grant the board reads")
    if status != 200:
        return FAIL, ["GET /google answered %d" % status]
    grant_text = data.decode("utf-8", "replace") if isinstance(data, bytes) else str(data)
    grant = as_json(data) or {}
    status, _head, tdata = http_call("GET", "/tools", timeout=30, label="the registry the board reads")
    if status != 200:
        return FAIL, ["GET /tools answered %d" % status]
    tools_text = tdata.decode("utf-8", "replace") if isinstance(tdata, bytes) else str(tdata)
    tools = (as_json(tdata) or {}).get("tools") or []
    for label, text in (("/google", grant_text), ("/tools", tools_text)):
        leak = re.search(r'"(?:access_token|refresh_token|client_secret|token|secret|api_key)"'
                         r'\s*:\s*"[^"]+"|ya29\.[A-Za-z0-9_\-]{10,}', text)
        if leak:
            return FAIL, ["%s carries %r to the browser, and the connectors board renders that "
                          "payload onto a grid" % (label, leak.group(0)[:40])]
    notes.append("the board's two routes answer and neither carries a token or a secret to the "
                 "browser (%d hand(s), grant %r)" % (len(tools), grant.get("state")))

    # -- (b) the public registry publishes no script path and no trigger.
    forbidden = sorted({k for t in tools if isinstance(t, dict) for k in t
                        if k in ("script", "triggers", "path", "cmd")})
    if forbidden:
        return FAIL, notes + ["GET /tools publishes %r; the page is not meant to learn the name "
                              "of a file it could ask for" % forbidden]
    notes.append("and /tools still publishes no script path and no trigger word")

    # -- the page, with its comments taken out, so a law is asserted about the code.
    try:
        with open(os.path.join(ROOT, "viewer", "index.html"), encoding="utf-8") as fh:
            src = _js_source(fh.read())
    except OSError as exc:
        return FAIL, notes + ["cannot read viewer/index.html: %s" % exc]

    # -- (c) the four claimed ids against the registry's own.
    claimed_block = re.search(r"const CONNECT_CLAIMED\s*=\s*\{(.*?)\}", src, re.S)
    if not claimed_block:
        return FAIL, notes + ["viewer/index.html declares no CONNECT_CLAIMED, so the board has no "
                              "way to know which hands its named tiles already speak for"]
    claimed = re.findall(r"([A-Za-z_][A-Za-z0-9_]*)\s*:", claimed_block.group(1))
    have = {t.get("id") for t in tools if isinstance(t, dict)}
    missing = [c for c in claimed if c not in have]
    if missing:
        return FAIL, notes + ["the board claims to speak for %r, which the registry does not "
                              "have: that hand would appear twice, once as a named tile saying "
                              "it has no hand and once as its own tile" % missing]
    notes.append("each of the %d named tiles speaks for a hand the registry actually validates: "
                 "%s" % (len(claimed), ", ".join(claimed)))

    # -- (d) the Halt Law, on the grid.
    push = re.search(r"tiles\.push\(\{\s*key:\s*'hand:'(.*?)\}\s*\)\s*;", src, re.S)
    if not push:
        return FAIL, notes + ["the registry hands no longer reach the grid through a "
                              "`key: 'hand:'` tile, so this check cannot see what they carry"]
    if re.search(r"\bact(?:Off)?\s*:", push.group(1)):
        return FAIL, notes + ["A HAND TILE NOW CARRIES A VERB. The executor has one door with a "
                              "gate on it; a button here is a second door: %r"
                              % push.group(1).strip()[:120]]
    notes.append("and not one hand tile carries a verb, so the grid cannot become a second door "
                 "into the executor")

    # -- (e) one reading slot per board, and board.read a reader.
    if "const boardRead = {}" not in src:
        return FAIL, notes + ["viewer/index.html has no boardRead map; if the boards share one "
                              "slot again, a row reports another board's answer as its own"]
    writes = re.findall(r"\bboard\.read\s*=[^=]", src)
    if writes:
        return FAIL, notes + ["board.read is assigned %d time(s); it is meant to be a getter over "
                              "boardRead[board.which], so that no board can write another's "
                              "reading" % len(writes)]
    if "boardRead.clock" not in src or "boardRead.connectors" not in src:
        return FAIL, notes + ["one of the two boards does not write its own named slot"]
    notes.append("each board writes its own reading by name and board.read only reads, so the "
                 "World Clock row cannot report the Connectors board's answer")

    # -- (f) the row is painted from the reading that filled the grid.
    body = re.search(r"function boardOpen\(which\)\s*\{(.*?)\n  \}", src, re.S)
    if not body:
        return FAIL, notes + ["boardOpen() is not where it was, so this check cannot read it"]
    if "cmdPaint()" not in body.group(1):
        return FAIL, notes + ["boardOpen repaints the grid when the read lands but not the order "
                              "sheet, so the row under a full grid still says it has not read "
                              "anything yet"]
    notes.append("and the row behind a board is repainted from the same reading as the grid")

    # -- (g) the registry is a list, not an executor.
    status, _head, _data = http_call("POST", "/tools", body=b"{}", timeout=30,
                                     label="the registry as an executor")
    if status == 200:
        return FAIL, notes + ["POST /tools answered 200: the registry route is meant to be a "
                              "readable list and nothing else"]
    notes.append("and POST /tools runs nothing (%d)" % status)
    return PASS, notes


def check_one_surface():
    """The answer is on one surface, and the card keeps the record.

    A sentence that is in the speakers and on two screens at once is read twice, and the
    employer's eye is asked to pick. So while the caption carries the answer, the card's
    paragraph stands down - and the whole of this check is about the four ways that could
    become a worse bug than the duplication it cleans up:

      (a) the stand-down is a CLASS on the card, hiding one child, and it is CSS -
          `#answer.yield>.a{display:none}`. A yield done by writing the paragraph would
          take the record with it, and eleven harnesses read #a-text.
      (b) answerYield() writes nothing into the DOM but that class: no textContent, no
          innerHTML, no removeChild anywhere inside it.
      (c) the subtitle's THREE down-paths all give the paragraph back - the fade timer, the
          cancel, and a new answer rendered under an old caption. A missing one leaves the
          card blank with nothing speaking, which is invisible in a screenshot taken a
          second too early.
      (d) the quoted utterance survives. #a-q is the visible evidence of the antecedent
          memory law, which is not ours to alter, and the rule hides `>.a` only - so the
          question stays on the card while the answer is in the voice.
    """
    notes = []
    try:
        with open(os.path.join(ROOT, "viewer", "index.html"), encoding="utf-8") as fh:
            raw = fh.read()
    except OSError as exc:
        return FAIL, ["cannot read viewer/index.html: %s" % exc]
    src = _js_source(raw)

    # -- (a) the law is one CSS rule, and it hides rather than moves.
    rule = re.search(r"#answer\.yield\s*>\s*\.a\s*\{([^}]*)\}", raw)
    if not rule:
        return FAIL, notes + ["no `#answer.yield>.a` rule: nothing makes the card stand down, so "
                              "an answer being read is on the caption AND on the card"]
    body = rule.group(1).replace(" ", "")
    if "display:none" not in body:
        return FAIL, notes + ["the yield rule does not hide the paragraph, it does %r - a card "
                              "faded to zero still takes the layout and the focus" % body]
    if "transition" in body or "animation" in body:
        return FAIL, notes + ["the yield rule animates (%r): this fires on every sentence of a "
                              "streamed read, and the deck's own law is transform and opacity "
                              "only" % body]
    notes.append("the card stands down by one CSS rule on one child (%s), so the yield costs no "
                 "frame and moves nothing" % body)

    # -- (b) and it writes nothing else.
    fn = re.search(r"function answerYield\(line\)\s*\{(.*?)\n  \}", src, re.S)
    if not fn:
        return FAIL, notes + ["answerYield() is not where it was, so this check cannot read what "
                              "it writes"]
    inner = fn.group(1)
    for bad in ("textContent =", "textContent=", "innerHTML", "removeChild", "remove()"):
        if bad in inner:
            return FAIL, notes + ["answerYield() contains %r: the paragraph is the record of the "
                                  "answer and a yield that edits it destroys what it was hiding"
                                  % bad]
    if "classList.toggle('yield'" not in inner:
        return FAIL, notes + ["answerYield() no longer toggles the `yield` class, so whatever it "
                              "does now is not the rule above"]
    notes.append("and answerYield() writes that class and nothing else - no textContent, no "
                 "innerHTML, no removal: the record survives being hidden")

    # -- (b2) and the comparison is equality or a PREFIX, never a containment.
    #    The boot plates caught the case equality misses: before the first click the autoplay
    #    law joins the held lines, so the caption reads the salutation AND the readiness line
    #    while the card holds the salutation alone. `startsWith` covers it and stays safe -
    #    the voice is saying the whole paragraph and going on. `indexOf(...) >= 0` would not:
    #    a three-word paragraph would vanish behind any sentence that happened to quote it.
    if "indexOf(held) === 0" not in inner:
        return FAIL, notes + ["answerYield() no longer yields when the caption BEGINS with the "
                              "paragraph: the boot ceremony's joined line reads the salutation "
                              "and then the readiness line, so the greeting stands on the card "
                              "and the caption at once and is read twice"]
    if re.search(r"indexOf\(held\)\s*>", inner) or "includes(held)" in inner:
        return FAIL, notes + ["answerYield() hides the paragraph when the caption contains it "
                              "ANYWHERE: a three-word answer then disappears behind any long "
                              "sentence that quotes it, with nothing pointing at it"]
    notes.append("and the comparison is equality or a prefix and never a containment, so a "
                 "capped answer, a plan with steps on the card and a softened error all stay "
                 "readable while the voice says less than they hold")

    # -- (c) three ways down, and all three hand the paragraph back.
    for name, pat in (("captionShow", r"function captionShow\(text\)\s*\{(.*?)\n  \}"),
                      ("captionFade", r"function captionFade\(ms\)\s*\{(.*?)\n  \}"),
                      ("captionClear", r"function captionClear\(\)\s*\{(.*?)\n  \}")):
        m = re.search(pat, src, re.S)
        if not m:
            return FAIL, notes + ["%s() is not where it was" % name]
        if "answerYield(" not in m.group(1):
            return FAIL, notes + ["%s() does not call answerYield(): the subtitle changes state "
                                  "there and the card is not told, so the paragraph is hidden "
                                  "with nothing speaking" % name]
    render = re.search(r"function renderAnswer\(question, text, isError, ids, sources, cites\)"
                       r"\s*\{(.*?)\n  \}", src, re.S)
    if not render or "answerYield(" not in render.group(1):
        return FAIL, notes + ["renderAnswer() does not re-take the decision, so a new answer "
                              "painted under the previous sentence's caption inherits its yield "
                              "and shows nothing"]
    notes.append("and all four state changes tell the card: raised, faded, cancelled, and a new "
                 "answer painted under an old subtitle")

    # -- (d) the quoted utterance is not what stood down.
    if "$('a-q').textContent = question" not in src:
        return FAIL, notes + ["renderAnswer no longer writes the quoted utterance into #a-q; the "
                              "antecedent memory law is visible on the card and is not ours to "
                              "retire"]
    if re.search(r"#answer\.yield\s*>?\s*(?:\.q|#a-q)", raw):
        return FAIL, notes + ["the yield rule reaches the quoted utterance: the question is not "
                              "the thing in the speakers and hiding it takes the antecedent with "
                              "it"]
    notes.append("while the quoted utterance stays on the card: the yield reaches the answer "
                 "paragraph and nothing above it")
    return PASS, notes


def check_boot_ceremony():
    """He reports for duty once, with music he generates, and three ways of being quiet.

    The ceremony is one flag, two branches and nine oscillators, and every one of the
    clauses below is here because of a way it could go wrong that NOTHING ELSE WOULD
    CATCH - a boot that announces itself twice is caught by a harness, but a boot that
    announces itself on the two-hundredth poll is caught by nobody who is not still
    watching after thirty-four minutes:

      (a) THE FLAG IS CLAIMED FIRST. `if (boot.fired) return false` guards the whole of
          it, and `boot.fired = 1` is set BEFORE anything is scheduled - not after. The
          rail polls /health every ten seconds for as long as the tab is open, and a
          ceremony that set its flag on the way out would fire again on any poll that
          landed inside the 3.1 seconds the jingle takes: two butlers, in a round.
      (b) NO ASSETS, NO NETWORK. Every note is an oscillator through the existing
          toneNote() on the chime bus. A fetch, an <audio>, a .src or a decode inside
          the jingle would be a request to forget to ship, a cache entry, and a sound
          this page's mute law does not cover.
      (c) AND THROUGH THE EXISTING BUS, which is what puts the music under the words: the
          pump ducks the whole tone bus when speech starts. A jingle on a gain node of
          its own would be a second thing to duck and would sit ON TOP of the sentence
          it is supposed to be under.
      (d) A MUTED TAB HOLDS NOTHING AND SAYS WHY. It claims the flag, records a reason,
          and returns before the line and before the music - so the ceremony is not left
          armed to go off mid-answer the moment audio becomes possible.
      (e) REDUCED MOTION DROPS THE FLOURISH AND KEEPS THE SENTENCE. The setting asks for
          less motion, not for less information, so the jingle is skipped with a reason
          recorded and speakLine(BOOT_LINE) is reached on BOTH branches - and the gesture
          that releases a held line checks `!boot.reduced` before it plays the music the
          quiet machine already declined.
      (f) AND THE CLAIM IS MADE FROM A READING. The trigger is the health poll's own
          verdict, so "fully functional" is spoken from the route that probes piper, the
          index and the web door, and never from optimism.
    """
    notes = []
    try:
        with open(os.path.join(ROOT, "viewer", "index.html"), encoding="utf-8") as fh:
            raw = fh.read()
    except OSError as exc:
        return FAIL, ["cannot read viewer/index.html: %s" % exc]
    src = _js_source(raw)

    cer = re.search(r"function bootCeremony\(healthy\)\s*\{(.*?)\n  \}", src, re.S)
    jin = re.search(r"function bootJingle\(\)\s*\{(.*?)\n  \}", src, re.S)
    red = re.search(r"function bootReduced\(\)\s*\{(.*?)\n  \}", src, re.S)
    if not cer or not jin or not red:
        return FAIL, ["the boot ceremony is not where it was: bootCeremony/bootJingle/"
                      "bootReduced could not be read, so none of this can be checked"]
    body, jingle = cer.group(1), jin.group(1)

    # -- (a) the flag guards everything, and is claimed before anything sounds.
    if not re.search(r"if \(boot\.fired\) return false;", body):
        return FAIL, notes + ["bootCeremony has no `if (boot.fired) return false` guard: the "
                              "health poll runs every ten seconds forever, so this is a "
                              "ceremony per poll, not per session"]
    # The LAST claim, not the first: the muted branch sets the same flag several lines
    # earlier, and a find() here reads THAT one - which would call a jingle scheduled
    # before the real claim "already guarded" and let the defect through untouched.
    claim = body.rfind("boot.fired = 1")
    if claim < 0:
        return FAIL, notes + ["nothing in bootCeremony sets boot.fired, so the guard above can "
                              "never be true and the flag is decoration"]
    for after in ("bootJingle(", "speakLine("):
        where = body.find(after)
        if where >= 0 and where < claim:
            return FAIL, notes + ["bootCeremony calls %s before it claims boot.fired: a /health "
                                  "reading landing during the 3s ceremony enters it a second "
                                  "time, and the two overlap" % after]
    notes.append("the flag is claimed before the first sound (boot.fired at %d, the jingle at "
                 "%d), and it guards the whole function - so the two-hundredth healthy poll is "
                 "as quiet as the second" % (claim, body.find("bootJingle(")))
    if "if (boot.jingle.played) return false" not in jingle:
        return FAIL, notes + ["bootJingle() will play a second time if anything asks it twice - "
                              "and the first gesture does ask, from unlockAudio()"]

    # -- (b) generated, not fetched. Nothing here is a file.
    for bad in ("fetch(", "new Audio", "XMLHttpRequest", ".src =", ".src=", "decodeAudioData",
                "createBufferSource", "import("):
        if bad in jingle:
            return FAIL, notes + ["bootJingle() contains %r: the boot flourish is generated on "
                                  "this machine, and an asset is a network request, a decode, a "
                                  "cache entry and a thing to forget to ship" % bad]
    if not re.search(r"toneNote\(\s*'boot'", jingle):
        return FAIL, notes + ["no note in bootJingle() goes through toneNote('boot', ...), so "
                              "whatever it plays is not on the chime bus and not in the ring "
                              "the harnesses read"]
    # Counted so this line can be read against boot_proof's own runtime count of 9: the
    # frequencies are the literals above 80Hz, which leaves out the peaks (0.09-0.21) and
    # the note lengths (0.44-2.90) without needing to know which is which.
    freqs = [f for f in re.findall(r"\b(\d{2,4}\.\d+)\b", jingle) if float(f) >= 80]
    notes.append("every note is an oscillator through the existing toneNote() - %d scheduled "
                 "frequencies, no fetch, no <audio>, no decode, nothing to ship" % len(freqs))

    # -- (c) on the bus that already ducks, not a graph of its own.
    for bad in ("createGain", "createDynamicsCompressor", "destination"):
        if bad in jingle:
            return FAIL, notes + ["bootJingle() builds its own %s: the sentence goes UNDER the "
                                  "music because the pump ducks the whole tone bus, and a "
                                  "private graph is a second thing to duck" % bad]
    if not re.search(r"function toneDuck\(", src):
        return FAIL, notes + ["toneDuck() is gone, so nothing lowers the bus the jingle plays "
                              "on and the flourish will sit on top of the readiness line"]
    notes.append("and it plays on the bus toneDuck() already lowers, which is the whole of "
                 "\"ducked beneath the voice\" - no second gain to get wrong")

    # -- (d) the muted branch: a reason, a flag, and an early return.
    mute = re.search(r"if \(MUTED\) \{(.*?)\n    \}", body, re.S)
    if not mute:
        return FAIL, notes + ["bootCeremony has no MUTED branch: a tab that cannot make a sound "
                              "would hold the ceremony anyway and the harnesses' nine tabs would "
                              "each announce themselves"]
    if "return false" not in mute.group(1):
        return FAIL, notes + ["the MUTED branch does not return: a silent tab falls through into "
                              "the line and the music"]
    if "boot.why" not in mute.group(1) or "boot.fired = 1" not in mute.group(1):
        return FAIL, notes + ["the MUTED branch does not both record a reason and claim the "
                              "flag - one way round it is silent for no stated cause, the other "
                              "it goes off the moment the tab is unmuted mid-answer"]
    notes.append("a muted tab claims the ceremony, says why in words, and returns before the "
                 "line and the music both")

    # -- (e) reduced motion: the flourish goes, the sentence stays.
    if "prefers-reduced-motion" not in red.group(1):
        return FAIL, notes + ["bootReduced() no longer reads prefers-reduced-motion, so the "
                              "quiet form is decided by something else"]
    quiet = re.search(r"if \(boot\.reduced\) (.*?)\n    else bootJingle\(\);", body, re.S)
    if not quiet or "jingle.why" not in quiet.group(1):
        return FAIL, notes + ["the reduced branch does not skip bootJingle() with a reason "
                              "recorded: a jingle that plays anyway ignores the setting, and a "
                              "silent one with no `why` reads as broken"]
    said = body.find("speakLine(BOOT_LINE)")
    if said < 0 or said < body.find("if (boot.reduced)"):
        return FAIL, notes + ["speakLine(BOOT_LINE) is not reached after the reduced branch: the "
                              "setting asks for less MOTION, and dropping the sentence with the "
                              "flourish tells a quiet machine less than it asked for"]
    unlock = re.search(r"function unlockAudio\(\)\s*\{(.*?)\n  \}", src, re.S)
    if not unlock or not re.search(r"boot\.fired && !boot\.reduced && !boot\.jingle\.played",
                                   unlock.group(1)):
        return FAIL, notes + ["the first gesture does not check `!boot.reduced` before firing the "
                              "held jingle, so the quiet machine gets the flourish anyway on its "
                              "first click - one gate is not a law if the other door is open"]
    notes.append("prefers-reduced-motion drops the flourish and keeps the sentence, and the "
                 "gesture that releases a held line checks the same setting before it plays")

    # -- (f) and the claim is made from a reading, not from optimism.
    if not re.search(r"bootCeremony\(res\.ok && !!\(data && data\.brain && data\.brain\.label\)\)",
                     src):
        return FAIL, notes + ["bootCeremony is no longer called with the health poll's own "
                              "verdict: \"fully functional\" has to be spoken from the route "
                              "that probes piper, the index and the web door, or it is optimism"]
    notes.append("and it fires on the first HEALTHY /health - the sentence is read off the probe "
                 "rather than off DOMContentLoaded, which knows nothing")
    return PASS, notes


def check_face_shading():
    """The head is large, it is shaded, and it is still one object and one allocation.

    §27 PART 3 grows the governor's square from 300px to 420px and puts form shading, a rim
    and a fresnel on the face. Every clause here guards a failure that the deck harness
    cannot see, and the reason it cannot see them is worth stating once:

        A GLSL LINK FAILURE DOES NOT THROW IN THIS PAGE. three.js logs the driver's error
        and draws nothing. `presence.shader` stays true because it is a test of the
        material's CLASS; `objects` stays 1; the fps floor is met with room to spare
        because an empty well is cheap. So deck_proof goes green over a blank square. The
        only defence against that is to assert the shading is WIRED - declared, assigned
        from a constant, and consumed - in the source, which is what this does.

      (a) ONE OBJECT, ONE MATERIAL, ONE ALLOCATION. The four attribute buffers are sized
          PRES.CAP once at build time and the mode switch moves setDrawRange. A buffer
          reallocated per switch is the defect this arrangement exists to prevent, and it
          would show up as a slow leak nobody would attribute to the face.
      (b) AND THE CAP RESPECTS THE MANDATE'S CEILING. 14000 points is the boss's number.
          CAP may grow to fill a bigger well; it may not cross that.
      (c) THE FLOORS ARE DECLARED AND ORDERED. A full-tier floor above the compact floor,
          both present. PRES_MIN was raised to 192 against a measured 213px at a crowded
          1920x860 - the failure mode of getting this wrong is not a small face, it is NO
          face, because a well that cannot meet the full floor and has no compact tier
          beneath it draws nothing at all.
      (d) THE RIM AND THE FRESNEL REACH THE GPU. Declared in the vertex program, assigned
          from PRES.* rather than from a literal, and actually read in the shader body. A
          gain that lives only in a constants table is a gain nobody can prove arrived -
          which is exactly how the first three rounds of this tuning were lost.
      (e) THE NORMAL IS TAKEN OFF `position`, NOT OFF `p`. By the time the shading runs, p
          has had a lid folded to its crease, a lip rippled and a mandible swung about the
          ear line. Those are deformations, not anatomy: a normal estimated from them
          shades the ANIMATION, so the cheek would change brightness as the jaw opened.
      (f) AND BOTH EDGE TERMS RIDE `near`. Without that factor the occiput catches its own
          fresnel and the head grows a second bright outline one ring outside the first -
          measured, and the reason `near` is in that expression at all.
      (g) THE SPRITE FOLLOWS THE WELL. uScale multiplies gl_PointSize, so a 420px well and
          a 213px well are the same object at two sizes rather than two different per-pixel
          densities - the texture of the hologram stopped depending on how crowded the
          top-right lane happened to be.
    """
    notes = []
    try:
        with open(os.path.join(ROOT, "viewer", "index.html"), encoding="utf-8") as fh:
            raw = fh.read()
    except OSError as exc:
        return FAIL, ["cannot read viewer/index.html: %s" % exc]
    src = _js_source(raw)

    # -- (a) one allocation, at CAP, and a draw range rather than a rebuild.
    allocs = re.findall(r"new Float32Array\(PRES\.CAP(?:\s*\*\s*\d+)?\)", src)
    if len(allocs) != 4:
        return FAIL, ["the presence geometry is not four buffers allocated once at PRES.CAP "
                      "(found %d): position, aRole, aRnd and aCell are sized to the CAP at "
                      "build time so a mode switch is a setDrawRange and never a realloc"
                      % len(allocs)]
    if not re.search(r"setDrawRange\(", src):
        return FAIL, notes + ["nothing calls setDrawRange: if the cloud is resized by "
                              "reallocating the buffers then the one-allocation claim the deck "
                              "harness reports is false"]
    notes.append("four attribute buffers allocated once at PRES.CAP and a setDrawRange for the "
                 "mode switch - one object, one material, no realloc when the face arrives")

    # -- (b) the cap respects the mandate's ceiling.
    cap = re.search(r"\bCAP:\s*(\d+)", src)
    if not cap:
        return FAIL, notes + ["PRES.CAP is not where it was, so the ceiling cannot be checked"]
    if int(cap.group(1)) > 14000:
        return FAIL, notes + ["PRES.CAP is %s, over the mandate's ceiling of 14000 points"
                              % cap.group(1)]
    notes.append("PRES.CAP is %s, inside the mandate's 14000-point ceiling with %d to spare"
                 % (cap.group(1), 14000 - int(cap.group(1))))

    # -- (c) the floors are declared, ordered, and the compact tier survives.
    mins = re.search(r"PRES_MIN:\s*(\d+)", src)
    minc = re.search(r"PRES_MIN_COMPACT:\s*(\d+)", src)
    if not mins or not minc:
        return FAIL, notes + ["LAYOUT.PRES_MIN / PRES_MIN_COMPACT are not both declared: the "
                              "full floor without a compact tier under it is a well that draws "
                              "NOTHING the first time a window is a notch more crowded"]
    if int(minc.group(1)) >= int(mins.group(1)):
        return FAIL, notes + ["the compact floor (%s) is not below the full floor (%s), so the "
                              "tier beneath is not a tier" % (minc.group(1), mins.group(1))]
    notes.append("a full floor at %spx over a compact floor at %spx, in that order - so a "
                 "crowded window gets a smaller face and never no face"
                 % (mins.group(1), minc.group(1)))

    # -- (d) the rim and the fresnel are declared, assigned from constants, and consumed.
    for uni, const in (("uRimDir", "RIM_DIR"), ("uRimGain", "RIM_GAIN"),
                       ("uFresK", "FRESNEL_K"), ("uFresGain", "FRESNEL_GAIN"),
                       ("uRimTint", "RIM_TINT"), ("uNrmHalf", "NRM_HALF")):
        if not re.search(r"'uniform [a-z0-9]+ %s;'" % uni, src):
            return FAIL, notes + ["%s is not declared in the presence vertex program, so the "
                                  "shading cannot be reading it" % uni]
        if not re.search(r"%s:\s*\{[^}]*PRES\.%s" % (uni, const), src):
            return FAIL, notes + ["%s is not assigned from PRES.%s: a rim tuned by editing a "
                                  "shader source string is a rim nobody tunes, and a uniform "
                                  "wired to a literal cannot be read back and proved"
                                  % (uni, const)]
    if not re.search(r"float lam = max\(0\.0, dot\(nrm, uRimDir\)\);", src):
        return FAIL, notes + ["the Lambert term is gone from the vertex program: uRimDir may be "
                              "reaching the GPU but nothing is shading with it"]
    if not re.search(r"uFresGain \* fres \+ uRimGain \* fres \* lam", src):
        return FAIL, notes + ["the rim and the fresnel are no longer both in vR: the fresnel is "
                              "the term that catches whether the key can see the edge or not, "
                              "and the rim is the same band multiplied by the key - dropping "
                              "either one leaves a head the boss will call flat"]
    if not re.search(r"vec3 col = mix\(uTint, uRimTint, vR\);", src):
        return FAIL, notes + ["the fragment no longer mixes uRimTint by vR: a brighter edge in "
                              "the SAME hue is an exposure push and not a rim light"]
    notes.append("the rim and the fresnel are declared, assigned from PRES.* and read in both "
                 "programs - measured on the plates at 0.69->1.11, 0.90->1.88, 1.07->1.75 and "
                 "1.74->2.89 keyed-arc over away-arc, at yaw -30/0/30/90")

    # -- (e) the normal comes off the undeformed attribute.
    if not re.search(r"vec3 nrm = normalize\(rot \* \(position / uNrmHalf", src):
        return FAIL, notes + ["the shading normal is no longer estimated from `position`: taken "
                              "off `p` it is a normal of the ANIMATION - a lid already folded, a "
                              "lip already rippled, a mandible already swung - so the cheek "
                              "would change brightness every time the jaw opened"]
    notes.append("the normal is estimated from the undeformed `position` attribute, so the "
                 "shading is of the anatomy and not of the animation")

    # -- (f) both edge terms ride the depth factor.
    vr = re.search(r"vR = clamp\((.*?)\);", src)
    if not vr or "* near" not in vr.group(1):
        return FAIL, notes + ["vR no longer rides `near`: the back of the skull then catches its "
                              "own fresnel and the head wears a second bright outline one ring "
                              "outside the first, which is what the first cut of this did"]
    notes.append("and both edge terms ride `near`, so the occiput cannot draw a second outline "
                 "behind the face")

    # -- (g) the sprite follows the well.
    if not re.search(r"gl_PointSize = sz \* uDpr \* uScale", src):
        return FAIL, notes + ["gl_PointSize no longer carries uScale: the same 2px sprite in a "
                              "420px well and in a 213px well is two different per-pixel "
                              "densities, so the hologram's texture would depend on how crowded "
                              "the top-right lane happened to be"]
    if not re.search(r"uniforms\.uScale\.value = pres\.scale", src):
        return FAIL, notes + ["nothing assigns uScale from pres.scale on resize, so the sprite "
                              "factor is a constant and the well's size does not reach it"]
    notes.append("uScale is set from the well's own side on every resize and multiplies "
                 "gl_PointSize, so a big well and a small one are one object at two sizes")
    return PASS, notes


def check_his_corpus():
    """The collection is his, the quarantine is unindexed by BOTH walkers, and the palette fits.

    §27 PART 8 turns the demonstration corpus out and leaves the employer's own notes behind.
    Every clause here guards a failure that looks like success from the outside:

    (a) THE GRAPH AND THE DISK AGREE, as sets and not as counts. Two off-by-one errors that
        cancel leave the count right and the galaxy wrong, so the filenames are compared.

    (b) THE CLUSTERS ARE THE FOLDERS. "clusters == folders" is a §27 clause in its own words,
        and a note at the root of notes/ is the case that breaks a naive version: it has no
        folder and is grouped as "unfiled", which is a real cluster with no directory.

    (c) NOTHING QUARANTINED IS A STAR, by path and not by title.

    (d) THE STORE HOLDS EXACTLY THE INDEXABLE FILES ON DISK, recomputed here. This is the
        clause that would have caught the mistake this part actually made: "quarantine" went
        into build.py's SKIP_DIRS and not into ingest.py's, so the galaxy stopped showing the
        thirty café notes WHILE THE BRAIN WENT ON CITING THEM. The graph looked cured. Nothing
        visible was wrong. A citation is the strongest claim this machine makes and all thirty
        were still available to it.

    (e) AND THE NAME IS IN BOTH LISTS, asserted in the source of both files, because (d) tests
        today's tree and this tests the rule. The two lists cannot be merged - build.py's
        galaxy half is standard library only and ingest.py needs chromadb - so the only thing
        keeping them in step is a comment, and a comment is not a check.

    (f) THE PALETTE CAN COLOUR EVERY CLUSTER. Held over from PART 5 on purpose, because it
        belongs to the corpus and not to the deck: colorOf wraps on PALETTE.length, so the
        cluster after the last jewel silently SHARES a colour with the first, and the legend's
        one promise - that a colour in the corner and a colour in the sky are the same claim -
        stops being true. It has now happened twice, both times because the employer filed
        something new, and both times it was deck_proof that found it: a full headless browser
        run, minutes long, for arithmetic on two numbers. The palette is a function of HIS
        corpus, so every folder he creates spends a jewel, and the next one should warn here
        rather than redden a harness. It WARNS at exactly enough and fails only when short,
        because "enough" is the property that matters and a spare jewel is not a defect.
    """
    notes = []
    suffixes = (".md", ".markdown", ".txt", ".pdf", ".docx")
    skip = {".git", ".svn", ".hg", "node_modules", "viewer", "__pycache__", "vector-store",
            ".obsidian", ".trash", ".vscode", ".idea", "venv", ".venv", "env", "say-cache",
            "quarantine"}

    def walk(top):
        found = []
        for dirpath, dirnames, filenames in os.walk(top):
            dirnames[:] = [d for d in dirnames if d not in skip and not d.startswith(".")]
            for name in filenames:
                if name.lower().endswith(suffixes):
                    found.append(os.path.relpath(os.path.join(dirpath, name), ROOT)
                                 .replace("\\", "/"))
        return found

    index_path = os.path.join(ROOT, "notes-index.json")
    try:
        with open(index_path, encoding="utf-8") as handle:
            index = json.load(handle)
    except Exception as exc:                                   # noqa: BLE001
        return FAIL, ["notes-index.json will not load (%s), so the galaxy has no data" % exc]
    listed = sorted(n.get("file", "") for n in index.get("notes") or [])
    groups = sorted(index.get("meta", {}).get("groups") or [])

    # -- (a) the graph is the disk.
    on_disk = sorted(f for f in walk(os.path.join(ROOT, "notes"))
                     if f.lower().endswith((".md", ".markdown")))
    if listed != on_disk:
        missing = [f for f in on_disk if f not in listed]
        extra = [f for f in listed if f not in on_disk]
        return FAIL, ["the galaxy and notes/ disagree: %d note(s) on disk are not stars (%s), "
                      "%d star(s) have no file (%s) - run build.py"
                      % (len(missing), ", ".join(missing[:3]) or "none",
                         len(extra), ", ".join(extra[:3]) or "none")]
    notes.append("worlds == notes: %s and no star lacks a file"
                 % ("the one note on disk is a star" if len(on_disk) == 1
                    else "all %d notes on disk are stars" % len(on_disk)))

    # -- (b) the clusters are the folders, with "unfiled" standing in for the root.
    folders = sorted(d for d in os.listdir(os.path.join(ROOT, "notes"))
                     if os.path.isdir(os.path.join(ROOT, "notes", d))
                     and d not in skip and not d.startswith("."))
    rooted = [f for f in on_disk if f.count("/") == 1]
    want = sorted(folders + (["unfiled"] if rooted else []))
    if groups != want:
        return FAIL, notes + ["clusters != folders: the index groups are %s and notes/ holds "
                              "the folders %s%s" % (groups, folders,
                                                    " plus %d note(s) at the root" % len(rooted)
                                                    if rooted else "")]
    notes.append("clusters == folders: %s%s"
                 % (", ".join(folders) or "no folders",
                    " plus \"unfiled\" for the %d note(s) at the root of notes/" % len(rooted)
                    if rooted else ""))

    # -- (c) nothing quarantined is a star.
    dirty = [f for f in listed if "quarantine" in f.lower()]
    if dirty:
        return FAIL, notes + ["%d quarantined file(s) are stars in his galaxy: %s"
                              % (len(dirty), ", ".join(dirty[:3]))]

    # -- (d) the store holds exactly the indexable files the walk finds.
    indexable = sorted(set(walk(os.path.join(ROOT, "notes")))
                       | set(walk(os.path.join(ROOT, "archive"))))
    health = as_json(http_call("GET", "/health", timeout=20)[2]) or {}
    held = (health.get("vectors") or {}).get("files")
    if held is None:
        notes.append("/health reports no vector file count, so the store could not be compared")
    elif held != len(indexable):
        return FAIL, notes + [
            "the store holds %s file(s) and the walk finds %d indexable on disk. A quarantined "
            "folder that is skipped by build.py and NOT by ingest.py looks exactly like this: "
            "the galaxy is clean and the brain can still cite every word of it"
            % (held, len(indexable))]
    else:
        notes.append("the store holds %d file(s), which is exactly what the walk finds "
                     "indexable - nothing under a quarantine is retrievable or citable" % held)

    # -- (e) and the name is in BOTH skip lists, in the source.
    for who, path in (("build.py (the graph)", "build.py"), ("ingest.py (the vectors)",
                                                             "ingest.py")):
        try:
            with open(os.path.join(ROOT, path), encoding="utf-8") as handle:
                body = handle.read()
        except Exception as exc:                               # noqa: BLE001
            return FAIL, notes + ["cannot read %s (%s)" % (path, exc)]
        block = re.search(r"SKIP_DIRS\s*=\s*\{(.*?)\}", body, re.S)
        if not block or "quarantine" not in block.group(1):
            return FAIL, notes + [
                "%s does not have \"quarantine\" in SKIP_DIRS, so half the law is missing. The "
                "two lists are deliberately separate and only a comment links them" % who]
    notes.append("\"quarantine\" is in SKIP_DIRS in build.py AND ingest.py, so one name takes "
                 "a folder out of the graph and out of the vectors together")

    # -- (f) the palette can colour every cluster.
    try:
        with open(os.path.join(ROOT, "viewer", "index.html"), encoding="utf-8") as handle:
            viewer = handle.read()
    except Exception as exc:                                   # noqa: BLE001
        return FAIL, notes + ["cannot read the viewer (%s)" % exc]
    jewels = re.search(r"const PALETTE = \[(.*?)\]", viewer, re.S)
    if not jewels:
        return FAIL, notes + ["no const PALETTE array in the viewer, so no colour is promised "
                              "to any cluster"]
    count = len(re.findall(r"#[0-9A-Fa-f]{6}", jewels.group(1)))
    if count < len(groups):
        return FAIL, notes + [
            "%d jewels in PALETTE for %d clusters, so colorOf wraps and cluster %d shares a "
            "colour with the first. The legend then says two folders are one"
            % (count, len(groups), count + 1)]
    if count == len(groups):
        notes.append("%d jewels for %d clusters - EXACTLY enough, so the next folder he files "
                     "wraps the palette. Add a jewel before it does" % (count, len(groups)))
        return WARN, notes
    notes.append("%d jewels in PALETTE for %d cluster%s, so every folder gets its own colour "
                 "with %d spare" % (count, len(groups), "" if len(groups) == 1 else "s",
                                    count - len(groups)))
    return PASS, notes


def check_scribe_skin():
    """The minutes panel is the Scribe's own, and it still collapses to its 34px strip.

    §27 PART 5 gives the transcript panel log paper, a stamp gutter, a ruled baseline, its own
    accent and a header seal. Most of that is a matter for the eye and a plate, and those are
    in the lookbook. What is asserted here is the part a plate CANNOT show, and each clause
    guards a failure that a screenshot taken seven seconds into a meeting looks fine under:

      (a) THE PANEL DECLARES ITS OWN PROPERTIES. Five custom properties scoped to
          #scribepanel. They are the mechanism by which the skin is ADDED ALONGSIDE the deck's
          vocabulary rather than replacing any of it - nothing outside this panel is touched
          and no relied-on class was renamed.
      (b) AND THE ACCENT IS NOT EITHER DECK CYAN. This is the whole point of the part, stated
          as a number. The panel is the one surface on the glass that is not the butler
          talking but a RECORD OF WHAT THE ROOM SAID, and the Scribe privacy law rests on a
          reader being able to tell those apart at a glance. An accent that drifted back to
          #22e0ff or #7fe9ff would leave it looking like another readout.
      (c) THE STAMP GUTTER IS A GRID TRACK, AND A FIXED ONE. Every transcript line is its own
          grid container - there is no grid shared across entries - so the only thing holding
          the stamps in a column is that the first track is the same absolute width in all of
          them. min-content would give each line the gutter its own stamp needs and the column
          would stagger. And it must be a GRID: with the stamp floated or margined instead,
          the second visual line of a long utterance wraps back underneath it and the column
          loses its left edge, which only shows up on an entry long enough to wrap.
      (d) AND THE LINES THAT CARRY NO STAMP GET A SINGLE TRACK. scribeAppend() writes
          <span class="t"> for speech only; a note and a refusal have no .t at all. Under a
          two-track template their words are auto-placed into the STAMP COLUMN, 62px wide,
          straddling the margin rule. The override plus a padding-left of the same gutter is
          what puts every kind of line on one left edge.
      (e) THE SEAL IS A PSEUDO-ELEMENT AND A GRADIENT. ::before, so no markup was added and
          no harness gained a node; a gradient and never a url(), because an image is a
          request, a cache entry and a thing to forget to ship - the no-webfont law's own
          argument applied to a texture.
      (f) AND THE STRIP GETS NONE OF IT. The head's new underline is 1px of border over 8px
          of padding, and the collapsed strip is a PUBLISHED vertical budget: LAYOUT.STRIP_H
          is 34 and layout_proof asserts the panel measures no more than STRIP_H + 1. The
          untreated head measures 36px in strip mode. So both the underline and the seal are
          struck off under .strip, and the failure mode of forgetting either is a decorative
          rule breaking a governor's budget - which is exactly the kind of thing that gets
          shipped because it looks right in the state anyone thinks to screenshot.
      (g) THE STAMP CANNOT ESCAPE. The stamp is right-aligned in a fixed track, and
          scribeStamp() does not pad the minutes or roll over to hours - so a long enough
          meeting writes a stamp wider than its track, and a right-aligned overflow escapes
          to the LEFT, out through the panel's padding and onto the glass. Measured: six
          characters ink 42.2px into 48px of room and seven characters want 49.2px. The
          overflow:hidden is the guard, and it must not be removed on the grounds that
          today's stamps fit.
    """
    notes = []
    try:
        with open(os.path.join(ROOT, "viewer", "index.html"), encoding="utf-8") as fh:
            raw = fh.read()
    except OSError as exc:
        return FAIL, ["cannot read viewer/index.html: %s" % exc]

    # THE COMMENTS COME OUT FIRST, and this is not tidiness. The rules below are explained in
    # prose that NAMES the very things being asserted - "a gradient and never a url()", "the
    # overflow:hidden on .t" - so a check run against the commented text would pass on the
    # explanation of a rule that had been deleted. Every needle here has to land on a
    # declaration.
    bare = re.sub(r"/\*.*?\*/", " ", raw, flags=re.S)
    start = bare.find("#scribepanel{")
    end = bare.find("#brain.gated #caption")
    if start < 0 or end < 0 or end <= start:
        return FAIL, ["the #scribepanel stylesheet block is not where it was, so none of the "
                      "PART 5 clauses can be located - the region runs from #scribepanel{ to "
                      "#brain.gated #caption"]
    css = bare[start:end]

    # -- (a) the panel's own properties, scoped to it.
    want = ["--sc-accent", "--sc-ink", "--sc-rule", "--sc-faint", "--sc-gutter"]
    missing = [p for p in want if not re.search(re.escape(p) + r"\s*:", css)]
    if missing:
        return FAIL, ["the minutes panel does not declare its own %s, so its skin is not scoped "
                      "to it and anything it sets is being taken from the deck's own vocabulary"
                      % ", ".join(missing)]
    notes.append("the panel scopes five properties of its own (%s) - added alongside the deck's "
                 "vocabulary, replacing none of it" % ", ".join(want))

    # -- (b) and the accent is its own hue, not either deck cyan.
    accent = re.search(r"--sc-accent\s*:\s*([^;}]+)", css)
    hue = accent.group(1).strip().lower()
    if re.sub(r"[#\s]", "", hue) in ("22e0ff", "7fe9ff", "22e0ff", "78e8ff"):
        return FAIL, notes + ["--sc-accent is %s, which is the deck's own cyan: the minutes panel "
                              "would read as another readout of what the butler thinks rather "
                              "than as a record of what the room said" % hue]
    if not re.search(r"\.lbl\{[^}]*color:\s*var\(--sc-accent\)", css):
        return FAIL, notes + ["the panel's label does not take colour from --sc-accent, so the "
                              "hue is declared and not used - the one thing a constants table "
                              "cannot prove is that the value arrived"]
    notes.append("its accent is %s and the label actually resolves to it, so the Scribe's "
                 "surface is legibly not a state readout" % hue)

    # -- (c) the stamp gutter is a fixed grid track.
    grid = re.search(r"\.lines p\{([^}]*)\}", css)
    if not grid:
        return FAIL, notes + ["the transcript line rule is gone, so the stamp gutter cannot be "
                              "checked"]
    body = grid.group(1)
    if "display:grid" not in body.replace(" ", ""):
        return FAIL, notes + ["a transcript line is no longer a grid: with the stamp floated or "
                              "margined instead, the SECOND visual line of a long utterance "
                              "wraps back under the stamp and the column loses its left edge"]
    if not re.search(r"grid-template-columns:\s*var\(--sc-gutter\)\s+1fr", body):
        return FAIL, notes + ["the transcript line's first track is not var(--sc-gutter): every "
                              "line is its own grid container, so only an identical ABSOLUTE "
                              "first track holds the stamps in one column - min-content or "
                              "max-content would stagger it line by line"]
    if not re.search(r"border-bottom:\s*1px solid var\(--sc-rule\)", body):
        return FAIL, notes + ["the entries are no longer ruled off from one another; the rule is "
                              "per ENTRY on purpose, because a repeating gradient at the line "
                              "pitch drifts against any font fallback or zoom"]
    notes.append("a transcript line is a grid whose first track is the declared gutter, and each "
                 "entry is ruled off beneath itself")

    # -- (d) and a line with no stamp gets one track, padded to the gutter.
    solo = re.search(r"p\.note,[^{]*p\.bad\{([^}]*)\}", css)
    if not solo:
        return FAIL, notes + ["nothing overrides the grid for p.note and p.bad. scribeAppend() "
                              "writes a .t span for SPEECH ONLY, so under the two-track template "
                              "a note's words are auto-placed into the 62px stamp column and "
                              "written across the margin rule"]
    if not re.search(r"grid-template-columns:\s*1fr", solo.group(1)) or \
       not re.search(r"padding-left:\s*var\(--sc-gutter\)", solo.group(1)):
        return FAIL, notes + ["the unstamped lines are overridden but not to ONE track padded to "
                              "the gutter, which is what puts a note, a refusal and a spoken "
                              "line on the same left edge: %s" % solo.group(1).strip()[:160]]
    notes.append("the unstamped lines - a note and a refusal - get one track padded to the same "
                 "gutter, so every kind of line shares one left edge and none crosses the rule")

    # -- (e) the seal is a pseudo-element and a gradient, and nothing here fetches an asset.
    seal = re.search(r"\.head::before\{([^}]*)\}", css)
    if not seal:
        return FAIL, notes + ["the header seal is gone. It is a ::before on purpose: a "
                              "pseudo-element of a flex container is a flex item, so the seal "
                              "cost no markup and gave no harness a new node to trip over"]
    if "content:''" not in seal.group(1).replace(" ", "") or \
       "gradient" not in seal.group(1):
        return FAIL, notes + ["the seal is not a generated gradient box: %s"
                              % seal.group(1).strip()[:160]]
    if "url(" in css:
        return FAIL, notes + ["the minutes panel now fetches something with url(). The paper, the "
                              "rules and the seal are gradients precisely so that there is no "
                              "request, no cache entry and no asset to forget to ship - the same "
                              "argument as the no-webfont privacy law"]
    notes.append("the seal is a generated gradient on .head::before - no markup added, no url() "
                 "anywhere in the panel, so nothing about this skin is a request")

    # -- (f) AND THE STRIP GETS NONE OF IT. This is the clause that guards a published budget.
    strip_head = re.search(r"\.strip \.head\{([^}]*)\}", css)
    if not strip_head:
        return FAIL, notes + ["the strip no longer restyles .head, so the head's new underline "
                              "and its 8px of padding are carried into the collapsed strip"]
    sh = strip_head.group(1).replace(" ", "")
    if "border-bottom:0" not in sh or "padding-bottom:0" not in sh:
        return FAIL, notes + ["the strip does not strike off the head's underline and its "
                              "padding. The strip is a PUBLISHED budget - LAYOUT.STRIP_H is 34 "
                              "and layout_proof asserts the panel measures no more than "
                              "STRIP_H + 1 - and the underlined head measures 36px: %s" % sh[:160]]
    if not re.search(r"\.strip \.head::before\{[^}]*display:\s*none", css):
        return FAIL, notes + ["the seal is not hidden in strip mode. At 312px, with the note "
                              "panel open, the label already ellipsizes and drops its "
                              "letter-spacing; 16px of seal plus 10px of gap comes out of the "
                              "one word on the strip that says MINUTES"]
    notes.append("and the collapsed strip is given none of it - underline, padding and seal are "
                 "all struck off, so the 34px budget layout_proof asserts is untouched")

    # -- (g) the stamp cannot escape its track.
    stamp = re.search(r"\.lines p \.t\{([^}]*)\}", css)
    if not stamp or "overflow:hidden" not in stamp.group(1).replace(" ", ""):
        return FAIL, notes + ["the stamp has lost its overflow guard. It is right-aligned in a "
                              "fixed track and scribeStamp() neither pads the minutes nor rolls "
                              "over to hours, so a long enough meeting writes a stamp wider than "
                              "its track - and a right-aligned overflow escapes to the LEFT, out "
                              "through the panel's padding and onto the glass. Six characters "
                              "ink 42.2px into 48px of room; seven want 49.2px"]
    notes.append("the stamp is clipped rather than allowed to escape left out of its own track, "
                 "which is the direction a right-aligned overflow actually goes")
    return PASS, notes


def check_census():
    """37. Seventeen questions, an answered-state read off the disk, and three refusals.

    §27 PART 8's intake. The Census is the one feature in this project whose entire claim is
    about what does NOT happen: it asks the employer seventeen questions about his own life
    and it must not write a single word of any answer until he has given one. census_proof.mjs
    proves the board and the card in a real browser; this proves the ORGAN, at the wire, on
    every run, and it writes nothing at all - not even a probe note to delete afterwards.

      (a) THE SHAPE AGREES WITH ITSELF. Three chapters, seventeen questions, every id unique
          and every SLUG unique. The slugs matter more than the ids: the slug is the filename
          an answer lands under, so two questions sharing one would have the second overwrite
          the first - or, because save_note steps aside to -2, file it where the reader of
          `answered` will never look for it. A duplicate id is a typo; a duplicate slug is a
          lost answer.

      (b) AND `answered` IS READ, NEVER REMEMBERED. Every question's flag is recomputed here
          from the folder on disk and compared with what /census said. THE FAILURE MODE THIS
          NAMES is a progress figure kept in the process: it survives his notes being moved,
          restored or edited by hand, and it is wrong from the first restart - the board then
          asks him a question he has already answered, or worse, stops asking one he has not.
          A note the employer deletes himself must put its question back in the queue.

      (c) THE THREE REFUSALS MINT NO SLOT. An id that is not one of the seventeen, an answer
          that is only whitespace, and an answer carrying a credential. Each must come back
          400 with nothing pending afterwards - because a near-miss that leaves a slot behind
          is a slot a later "yes", meant for something else entirely, can confirm. The
          credential refusal is checked twice over: it must NAME the kind, and the value must
          appear nowhere in the payload. A scanner that quotes what it found has copied the
          secret into the record that exists to prove it was kept out.

      (d) AND A GOOD ANSWER IS STILL ONLY A PROPOSAL. The gate: a real answer to a real
          question mints one pending save_note whose `folder` parameter is census, and the
          folder on disk is unchanged. Then it is CANCELLED, so this check ends with the disk
          exactly as it found it and nothing pending for the next check to trip over.

      (e) AND THE FOLDER IS A WORD IN AN ALLOWLIST, not a path. save_note.py takes `folder`
          from a model-facing registry parameter, so the only safe shape for it is a key in a
          table - asserted in the source, because census.FOLDER agreeing with the allowlist
          today is not the same claim as the allowlist being an allowlist.
    """
    notes = []
    folder = os.path.join(ROOT, "notes", census.FOLDER)

    def listing():
        try:
            return sorted(n for n in os.listdir(folder) if n.lower().endswith(".md"))
        except OSError:
            return []                       # an absent folder is an empty one, not an error

    before = listing()

    def pending():
        # GET, not a POST with an unknown cmd: the refusal path also carries `pending`, and a
        # check that reads its state out of an error response is one route change from
        # reporting "nothing pending" because the error shape moved.
        _status, _head, data = http_call("GET", "/tools", timeout=20,
                                         label="GET /tools (census pending)")
        return (as_json(data) or {}).get("pending") or None

    def put_down(why):
        post_json("/tools", {"cmd": "cancel", "door": "curl"}, timeout=20,
                  label="POST /tools (cancel: %s)" % why)

    # -- (a) the shape.
    status, _, data = http_call("GET", "/census", timeout=25, label="GET /census")
    snap = as_json(data) or {}
    if status != 200 or not snap.get("ok"):
        return FAIL, ["GET /census answered %s, so the intake cannot be read: %s"
                      % (status, str(snap)[:160])]
    chapters = snap.get("chapters") or []
    rows = [q for c in chapters for q in (c.get("questions") or [])]
    ids = [str(q.get("id") or "") for q in rows]
    slugs = [str(q.get("slug") or "") for q in rows]
    if len(chapters) != len(census.CHAPTERS) or len(rows) != census.TOTAL:
        return FAIL, ["/census reads %d chapter(s) and %d question(s); the module declares "
                      "%d and %d" % (len(chapters), len(rows), len(census.CHAPTERS),
                                     census.TOTAL)]
    if len(set(ids)) != len(ids) or len(set(slugs)) != len(slugs):
        dup_id = sorted({i for i in ids if ids.count(i) > 1})
        dup_slug = sorted({s for s in slugs if slugs.count(s) > 1})
        return FAIL, ["the questions are not distinct: id(s) %s, slug(s) %s. Two questions "
                      "sharing a slug share a filename, and the second answer lands where "
                      "nothing will read it" % (dup_id or "none", dup_slug or "none")]
    notes.append("%d questions in %d chapters (%s), every id and every slug distinct"
                 % (len(rows), len(chapters),
                    ", ".join(str(c.get("name") or c.get("id")) for c in chapters)))

    # -- (b) answered is read off the folder, not carried.
    stems = [n[:-3].lower() for n in before]
    wrong = []
    for q in rows:
        slug = str(q.get("slug") or "").lower()
        on_disk = any(s == slug or s.startswith(slug + "-") for s in stems)
        if bool(q.get("answered")) != on_disk:
            wrong.append("%s (says %s, disk says %s)"
                         % (q.get("id"), bool(q.get("answered")), on_disk))
    if wrong:
        return FAIL, notes + [
            "%d question(s) disagree with notes/%s: %s. The answered-state is being remembered "
            "rather than read, so a note he moves or deletes leaves the board lying about what "
            "it has already asked him" % (len(wrong), census.FOLDER, "; ".join(wrong[:3]))]
    done = sum(1 for q in rows if q.get("answered"))
    if snap.get("answered") != done:
        return FAIL, notes + ["/census totals %s answered but %d question rows say answered"
                              % (snap.get("answered"), done)]
    notes.append("answered = %d of %d, and every flag matches the %d file(s) in notes/%s - "
                 "read off the folder on this call, not carried in the process"
                 % (done, census.TOTAL, len(before), census.FOLDER))

    # -- (c) the three refusals.
    put_down("clearing the slot before the census refusals")
    SECRET = "Tr0ub4dor3xK9z"               # not a credential; a shape secretscan objects to
    probes = (
        ("an id that is not one of the seventeen",
         {"id": "life-favourite-biscuit", "answer": "a rich tea, obviously"}, None),
        ("an answer that is only whitespace", {"id": ids[0], "answer": "   \t  "}, None),
        ("an answer carrying a credential",
         {"id": ids[0], "answer": "put it in the notes, the api key is " + SECRET},
         "credential"),
    )
    for label, payload, refused in probes:
        status, _, data = post_json("/census/answer", payload, timeout=30,
                                    label="POST /census/answer (%s)" % label)
        body = as_json(data) or {}
        raw = json.dumps(body)
        if status != 400 or body.get("pending") or body.get("id"):
            return FAIL, notes + ["%s answered %s and offered %s - a refusal that mints a slot "
                                  "leaves something a later yes can confirm: %s"
                                  % (label, status, body.get("pending") or body.get("id"),
                                     raw[:160])]
        if refused and body.get("refused") != refused:
            return FAIL, notes + ["%s was refused without naming it as a %s (refused=%r), so "
                                  "the page cannot tell him WHY it will not be written"
                                  % (label, refused, body.get("refused"))]
        if SECRET in raw:
            return FAIL, notes + ["the refusal quotes the value it objected to, which copies "
                                  "the secret into the record that exists to prove it was kept "
                                  "out of the note"]
        still = pending()
        if still:
            put_down("a refusal left a slot")
            return FAIL, notes + ["%s left %s pending afterwards"
                                  % (label, still.get("tool") or still.get("id"))]
    if listing() != before:
        return FAIL, notes + ["notes/%s changed during the three refusals: %s -> %s"
                              % (census.FOLDER, before, listing())]
    notes.append("three refusals - an unknown question, a blank answer and a credential - each "
                 "400, each naming itself, none minting a slot, and notes/%s untouched by all "
                 "three" % census.FOLDER)

    # -- (d) a good answer proposes and does not write.
    nxt = snap.get("next") or {}
    qid = str(nxt.get("id") or ids[0])
    status, _, data = post_json("/census/answer",
                               {"id": qid,
                                "answer": "This sentence was put here by preflight to prove the "
                                          "gate holds, and it is cancelled rather than filed."},
                               timeout=45, label="POST /census/answer (the gate)")
    body = as_json(data) or {}
    slot = body.get("pending") or body
    try:
        if status != 200 or not slot.get("id"):
            return FAIL, notes + ["a good answer to %s did not propose (%s): %s"
                                  % (qid, status, json.dumps(body)[:200])]
        if slot.get("tool") != "save_note":
            return FAIL, notes + ["the Census proposed %r rather than save_note"
                                  % slot.get("tool")]
        params = slot.get("params") or {}
        asked = str(params.get("folder") or "")
        if asked != census.FOLDER:
            return FAIL, notes + ["the proposal would file into %r and not %r, so a Census "
                                  "answer would land among his passing thoughts"
                                  % (asked, census.FOLDER)]
        if listing() != before:
            return FAIL, notes + ["a file appeared in notes/%s at PROPOSAL time, before any "
                                  "word was given: %s" % (census.FOLDER, listing())]
        notes.append("a real answer mints ONE pending save_note into notes/%s, with the question "
                     "in the title (%r), and the folder is still %d file(s) - nothing is written "
                     "until a word is given"
                     % (census.FOLDER, str(body.get("title") or "")[:48], len(before)))
    finally:
        put_down("the gate proposal")
    if pending() or listing() != before:
        return FAIL, notes + ["the gate proposal would not cancel cleanly, or it wrote: %s"
                              % listing()]

    # -- (e) the folder is a word in an allowlist.
    try:
        with open(os.path.join(ROOT, "tools", "save_note.py"), encoding="utf-8") as handle:
            hand = handle.read()
    except Exception as exc:                                   # noqa: BLE001
        return FAIL, notes + ["cannot read tools/save_note.py (%s)" % exc]
    table = re.search(r"FOLDERS\s*=\s*\{(.*?)\}", hand, re.S)
    if not table or census.FOLDER not in table.group(1):
        return FAIL, notes + [
            "save_note.py has no FOLDERS allowlist containing %r. `folder` arrives from a "
            "registry parameter a model fills in, and a parameter a model fills in with a PATH "
            "is a traversal waiting for a bad day" % census.FOLDER]
    notes.append("and save_note.py takes the folder from a %d-word allowlist rather than a path, "
                 "so %r is a key and not a directory a model can steer"
                 % (len(re.findall(r"\"[a-z]+\"\s*:", table.group(1))), census.FOLDER))
    return PASS, notes


CHECKS = [
    ("the server is up and serving the viewer", check_server),
    ("the graph data loads and has nodes", check_graph),
    ("/chat answers a real question, with nodes", check_chat),
    ("the key in config.json is valid", check_credentials),
    ("the configured model is reachable", check_model),
    ("/remember proposes a note, a word writes it, and /chat finds it at once",
     check_remember),
    ("/see answers a real JPEG", check_see),
    ("the served files match the files on disk", check_served_files),
    ("config.json is not reachable from the browser", check_config_unreachable),
    ("/model swaps honestly, in one voice, and refuses the rest", check_brain_swap),
    ("a focus session ticks on the server and leaks nothing", check_focus),
    ("the eyes report posture and nothing else", check_eyes),
    ("the screen watch costs nothing until it thinks", check_watch),
    ("the instruments answer from the running server", check_instruments),
    ("the web lookup fetches, cites, and stays in its lane", check_web),
    ("the hands ask first, run once, and keep nothing", check_hands),
    ("a PDF in archive/ is read, cited by page, and answers", check_documents),
    ("the four classes answer for nothing and cannot be searched", check_routing),
    ("the tab lock explains itself and asks in one voice", check_lock),
    ("a meeting is heard, minuted, and written only on a yes", check_scribe),
    ("nothing the server starts shows a console window", check_quiet_spawn),
    ("the room knows the hour, and the instrument does not lie", check_room_hour),
    ("the road to Google is narrow, and it refuses politely", check_google_grant),
    ("a turn resets once, and one hand writes the arm", check_reset_contract),
    ("the voiceprints stay in their folder, embeddings only", check_speaker_store),
    ("a chip is a claim about the sentence above it", check_citation_honesty),
    ("a plan of two is a schema, and a plan that breaks it never pends",
     check_chain_protocol),
    ("the prompt has a cap, an order, and a memory of what it dropped",
     check_context_budget),
    ("every answer carries a grounding class, and a class is not a route",
     check_grounding_audit),
    ("the clock costs nothing and knows what day it is there", check_world_clock),
    ("the connectors board reads two routes and cannot run a hand",
     check_connectors_board),
    ("an answer being read is on one surface, and the card keeps the record",
     check_one_surface),
    ("he reports for duty once, with music he makes, and is quiet three ways",
     check_boot_ceremony),
    ("the head is large and shaded, and still one object and one allocation",
     check_face_shading),
    ("the minutes are on the Scribe's own paper, and the strip is still 34px",
     check_scribe_skin),
    ("the collection is his, the quarantine is unindexed, and the palette fits the clusters",
     check_his_corpus),
    ("seventeen questions, an answered-state read off the disk, and three refusals",
     check_census),
]


def main():
    say("")
    say("  preflight  ·  http://%s:%d  ·  %s"
        % (server.HOST, server.PORT, time.strftime("%d %b %Y %H:%M:%S")))
    say("  every check below is a live call; nothing here is mocked")
    say("")

    for number, (name, fn) in enumerate(CHECKS, 1):
        started = time.time()
        try:
            outcome, detail = fn()
        except Exception as exc:                               # noqa: BLE001
            outcome = FAIL
            detail = ["the check itself raised %s: %s" % (type(exc).__name__, exc)]
        if isinstance(detail, str):
            detail = [detail]
        results.append((outcome, name))
        say("  %-2s %d. %-46s %6.0f ms"
            % (MARK[outcome], number, name, (time.time() - started) * 1000))
        for line in detail:
            if line:
                say("        %s" % line)
        say("")

    passed = sum(1 for s, _ in results if s == PASS)
    failed = sum(1 for s, _ in results if s == FAIL)
    warned = sum(1 for s, _ in results if s == WARN)
    if failed:
        say("  failing: " + "; ".join(n for s, n in results if s == FAIL))
        say("")
    out("  %d pass, %d fail, %d warn" % (passed, failed, warned))
    say("")
    return min(failed, 120)


if __name__ == "__main__":
    sys.exit(main())
