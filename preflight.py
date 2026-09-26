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
    """6. /remember writes a real file and /chat can retrieve it at once."""
    if not state["up"]:
        return FAIL, ["skipped: the server is not reachable"]
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

    status, _, body = post_json("/remember", {"text": text}, timeout=120)
    data = as_json(body) or {}
    if status != 200 or not data.get("ok"):
        return FAIL, ["POST /remember returned HTTP %s: %s"
                      % (status, first_line(data.get("error") or body[:200]))]

    rel = data.get("file") or ""
    path = os.path.join(ROOT, rel.replace("/", os.sep))
    if not os.path.isfile(path):
        return FAIL, ["the reply claimed %s but there is no such file" % rel]
    with open(path, "r", encoding="utf-8") as fh:
        written = fh.read()
    if canary not in written:
        return FAIL, ["%s exists but does not contain what was captured" % rel]

    new_id = (data.get("nodes") or [None])[0]
    detail = ["wrote %s (%d bytes) as node %s, degree %s"
              % (rel, len(written), new_id, (data.get("node") or {}).get("degree"))]

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
        rebuild = subprocess.run([sys.executable, os.path.join(ROOT, "build.py")],
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
    detail.append("no credential and no part of config.json appears in any of the %d "
                  "responses this run collected" % len(bodies))
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
    done = subprocess.run([sys.executable, os.path.join(ROOT, "build.py")],
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


CHECKS = [
    ("the server is up and serving the viewer", check_server),
    ("the graph data loads and has nodes", check_graph),
    ("/chat answers a real question, with nodes", check_chat),
    ("the key in config.json is valid", check_credentials),
    ("the configured model is reachable", check_model),
    ("/remember writes a note /chat can find at once", check_remember),
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
