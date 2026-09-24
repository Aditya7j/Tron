#!/usr/bin/env python3
"""ingest.py - THE INGESTION ENGINE, and the semantic recall it exists to serve.

Two halves of one contract, in one file because they must never disagree:

  THE WRITE HALF   walk notes/ and archive/, read .md .txt .pdf .docx, cut the text
                   into ~500-token chunks with 50 of overlap, embed each chunk with
                   the local nomic-embed-text model in Ollama, and keep text, path,
                   page number and vector in a persistent ChromaDB at vector-store/.

  THE READ HALF    embed a question the same way, fetch the five nearest chunks by
                   cosine similarity, and say how well the best of them did.

They are one file because a store written with one prefix scheme, one embedding model
or one chunk size and read with another is not a store, it is a coincidence. SCHEME
below is stamped into every manifest row, and changing any of those knobs changes it,
which makes the next rebuild re-embed everything instead of silently mixing vectors
that were never comparable.

WHAT THIS FILE WILL NOT DO. recall() NEVER RAISES - not for a dead Ollama, not for a
missing store, not for a corrupt sqlite file. It returns available=False and a reason,
and server.py falls back to the keyword index it has always had. The same rule search.py
follows, for the same reason: a retrieval layer that can take the assistant down with it
is worse than no retrieval layer, because the old one worked.

THE WINDOWS CONTRACT, which is most of the defensive code in here:
  - pathlib throughout, and every path that crosses into the store is stored as a
    forward-slashed relative string, so a rebuild on one machine and a read on
    another cannot disagree about "notes\\a.md" versus "notes/a.md";
  - every byte that becomes text is decoded with errors="replace", because a single
    stray 0x9d in one archived invoice must not be the reason the index has no rows;
  - ONE BAD FILE IS SKIPPED, LOUDLY, AND THE WALK CARRIES ON. A password-protected
    PDF, a .docx that is really a renamed .zip, a file being written while we read
    it - each is logged with its reason and left out of the index. It is recorded in
    the manifest as skipped, so the next rebuild tries it again rather than treating
    a transient failure as a permanent verdict.

THE DIAL, AND WHY IT IS NOT 0.65. The specification set it at 0.65 and said in the same
breath that it is a dial and not a law: too eager for the web, 0.70; too shy, 0.60. It
is 0.60 here, and this is the measurement that moved it. Every number below is from this
machine, this corpus and this model, asked as an ordinary question:

  "what time does the northern depot open"     0.792  a .txt answers it
  "how much does the espresso blend cost"      0.759  a note answers it
  "when do we have to pay the supplier"        0.750  page 1 of a PDF answers it
  "what colour is the car?"                    0.702  a PDF answers it without ever
                                                      using the word "car"
  "when does the insurance renew"              0.696  a .docx answers it
  "what happens if a sack of beans is too wet" 0.619  THE CONTRACT ANSWERS THIS
                                                      EXACTLY - clause 3 is about
                                                      moisture content - and at 0.65
                                                      it was being sent to the web
  ------------------------------------------ the valley -------------------------------
  "what does the lease photographs file show"  0.570  nothing holds it
  "who signed the contract"                    0.548  only a scan holds it
  "who was the first Sikh PM of India"         0.487  nothing holds it, and its own
                                                      best guess says so

The gap between the lowest true hit and the highest false one is 0.5705 to 0.6193, so
any dial in there is defensible and 0.60 is the middle of it. 0.65 is not in it at all -
it sits above a question the archive answers word for word, which is one measured false
negative in nine.

THE ASYMMETRY THAT DECIDES THE DIRECTION, because the two mistakes do not cost the same.
Set too low, a question the collection cannot really answer opens the notes door, and the
worst case is the assistant saying the notes do not cover it - a wasted turn. Set too
high, a question the employer's own signed contract answers goes out to a search engine
and comes back citing a stranger's blog. That second one is the exact failure this whole
feature was built to end, so when the evidence is ambiguous the dial leans down.

What it cannot do is block a lookup that was never about the notes: "look this up" still
forces a search and the weather still fetches, because REALWORLD_RE and the force
trigger in server.py sit above this number and always have. config.json's
notes_threshold moves it without touching this file, and /health reports where it is.

  python ingest.py            rebuild what changed, print a summary
  python ingest.py --force    re-embed everything, ignoring the hashes
  python ingest.py --ask "what colour is the car?"      one query, scored

Standard library plus chromadb and pypdf. The embedder is reached over plain HTTP with
urllib - no SDK, and nothing leaves this machine.
"""

import hashlib
import json
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

# ---------------------------------------------------------------- configuration

ROOT = Path(__file__).resolve().parent
STORE_DIR = ROOT / "vector-store"
MANIFEST_PATH = STORE_DIR / "manifest.json"
CONFIG_PATH = ROOT / "config.json"
COLLECTION = "galaxy"

# WHERE IT LOOKS. notes/ is the galaxy - every .md in there is already a planet. archive/
# is the other half of the point of this feature: the filing cabinet, where a contract
# nobody will ever write a wikilink to can be dropped and still be found.
ROOTS = ("notes", "archive")

SUFFIXES = (".md", ".markdown", ".txt", ".pdf", ".docx")

SKIP_DIRS = {
    ".git", ".svn", ".hg", "node_modules", "viewer", "__pycache__", "vector-store",
    ".obsidian", ".trash", ".vscode", ".idea", "venv", ".venv", "env", "say-cache",
}

# THE CHUNK. 500 tokens with 50 of overlap, as specified - and the arithmetic that
# turns that into words, said out loud rather than hidden in a magic number. There is
# no tokeniser in here on purpose: nomic-embed-text's is a wordpiece vocabulary, and
# shipping a copy of it to get a count we only use to decide where to cut would be a
# megabyte of dependency for a rounding error. English prose runs about 1.3 wordpiece
# tokens to the word, so 500 tokens is roughly 385 words, and the model's 2048-token
# context has room to spare even if a particular page is denser than that.
CHUNK_TOKENS = 500
CHUNK_OVERLAP_TOKENS = 50
TOKENS_PER_WORD = 1.30
CHUNK_WORDS = int(round(CHUNK_TOKENS / TOKENS_PER_WORD))            # 385
OVERLAP_WORDS = int(round(CHUNK_OVERLAP_TOKENS / TOKENS_PER_WORD))  # 38
MIN_CHUNK_WORDS = 4      # below this a "chunk" is a page number and a letterhead

# THE EMBEDDER. nomic-embed-text wants its inputs labelled: a question and the passage
# that answers it are not the same kind of text, and telling the model which is which is
# what makes an asymmetric search work. Measured here, the prefixes lift a true match
# from 0.726 to 0.753 and they are what the model's authors document, so they are used -
# and they are part of SCHEME, because a store embedded without them cannot be queried
# with them.
EMBED_MODEL = "nomic-embed-text"
OLLAMA_URL = "http://127.0.0.1:11434"
DOC_PREFIX = "search_document: "
QUERY_PREFIX = "search_query: "
EMBED_BATCH = 32
EMBED_TIMEOUT = 180

SCHEME = "nomic-prefix-v1/chunk%d-%d" % (CHUNK_TOKENS, CHUNK_OVERLAP_TOKENS)

# THE GATE. The notes door opens when the best of the top THREE clears the threshold -
# the top three rather than the top one, for the same reason note_confidence() in
# server.py measures the best of the retrieved set: the claim being tested is "does the
# collection hold this", which is a claim about the collection and not about whichever
# row happened to sort first.
NOTES_THRESHOLD = 0.60           # the dial. See the header for the nine measurements.
TOP_K = 5
GATE_TOP = 3
# WHICH OF THE FIVE GET NAMED. A cited chunk has to do two things: clear the dial, and
# come within this much of the best one. The second test is the one that matters, and it
# is here because the first on its own is far too generous - a question whose best hit
# scores 0.75 will often have four more between 0.62 and 0.66, and a card that names five
# files for an answer that came from one is a provenance lie of exactly the kind the
# existing chips code goes to such lengths to avoid. Same argument as SCORE_FLOOR_RATIO
# in server.py, and roughly the same number.
CITE_RATIO = 0.92

# A page number cannot be null in ChromaDB metadata, and "0" is a real page in nobody's
# document, so absence is spelled out as a number that cannot be mistaken for one.
NO_PAGE = -1

# THE ONE HONEST LINE. Said when a page exists, is cited, and holds no text: a scan is a
# photograph of writing, and this machine cannot read a photograph. It is a fixed string
# and it is appended by server.py, never generated - a model asked to describe a page it
# cannot see will describe one anyway, and it will be plausible.
SCAN_LINE = ("I can see page %d, sir, but it is a scan \u2014 there is no text in it "
             "for me to read.")


class IngestError(Exception):
    """Something this file did not manage. Always carries a sentence for the log."""


class BadDocument(IngestError):
    """This one file cannot be read. The walk carries on without it."""


class EmbedDown(IngestError):
    """The embedder is not answering. Nothing can be indexed until it is."""


# ------------------------------------------------------------------ the knobs

_DEFAULTS = {
    "vector_recall": True,
    "embed_model": EMBED_MODEL,
    "ollama_url": OLLAMA_URL,
    "notes_threshold": NOTES_THRESHOLD,
}


def settings():
    """The four knobs, read from config.json fresh, with nothing secret among them.

    config.json is read HERE, server-side, exactly as send_email.py reads it: this
    module is imported by the server and by build.py, and neither of them hands any of
    this to the browser. The keys are a model name, a localhost URL, a float and a
    boolean - there is no credential in this function and there must never be one, so
    that store_state() below can be reported to the page without a second thought.
    """
    out = dict(_DEFAULTS)
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as fh:
            cfg = json.load(fh)
        if not isinstance(cfg, dict):
            return out
    except Exception:                                          # noqa: BLE001
        return out
    if isinstance(cfg.get("embed_model"), str) and cfg["embed_model"].strip():
        out["embed_model"] = cfg["embed_model"].strip()
    url = cfg.get("ollama_url")
    if isinstance(url, str) and url.strip().startswith(("http://", "https://")):
        out["ollama_url"] = url.strip().rstrip("/")
    if cfg.get("vector_recall") is not None:
        out["vector_recall"] = bool(cfg["vector_recall"])
    try:
        # Clamped, because a threshold outside this range is not a preference, it is a
        # typo that would either send everything to the web or nothing.
        thr = float(cfg.get("notes_threshold", NOTES_THRESHOLD))
        if 0.2 <= thr <= 0.95:
            out["notes_threshold"] = thr
    except (TypeError, ValueError):
        pass
    return out


def _say(line):
    """Print a progress line that cannot itself be the reason a rebuild fails.

    A filename on this machine can hold a character the console's code page has no
    glyph for, and a build that dies printing the name of the file it just indexed is
    the most annoying possible failure. Same guarantee as preflight.py's out().
    """
    enc = getattr(sys.stdout, "encoding", None) or "utf-8"
    try:
        line.encode(enc)
    except (UnicodeEncodeError, LookupError):
        line = line.encode(enc, "replace").decode(enc, "replace")
    print(line)


# -------------------------------------------------------------------- the walk

def walk(roots=ROOTS, base=ROOT):
    """Every readable document under the given roots, as forward-slashed relpaths.

    Sorted, so that two rebuilds of an unchanged corpus produce byte-identical
    manifests and a diff of the manifest means something.
    """
    found = []
    for name in roots:
        top = Path(base) / name
        if not top.is_dir():
            continue
        for dirpath, dirnames, filenames in os.walk(top):
            dirnames[:] = sorted(d for d in dirnames
                                 if d not in SKIP_DIRS and not d.startswith("."))
            for fname in sorted(filenames):
                if fname.startswith("."):
                    continue
                if not fname.lower().endswith(SUFFIXES):
                    continue
                found.append(rel_of(Path(dirpath) / fname, base))
    return sorted(set(found))


def rel_of(path, base=ROOT):
    """'C:\\...\\trone\\archive\\a.pdf' -> 'archive/a.pdf'. One spelling, everywhere."""
    try:
        rel = Path(path).resolve().relative_to(Path(base).resolve())
    except ValueError:
        rel = Path(path)
    return str(rel).replace("\\", "/")


def file_fingerprint(path):
    """sha256 of the bytes, plus the size, which is what "changed" means here.

    Not the mtime: a file restored from a backup, a checkout, or a sync client gets a
    new mtime and the same content, and re-embedding a thousand unchanged pages
    because a folder was copied is exactly the minutes this feature exists to avoid.
    The size is folded in because it is free and it makes a hash collision need to be
    a collision at the same length as well.
    """
    h = hashlib.sha256()
    size = 0
    with open(path, "rb") as fh:
        while True:
            block = fh.read(1024 * 1024)
            if not block:
                break
            size += len(block)
            h.update(block)
    return "%s-%d" % (h.hexdigest()[:32], size)


# -------------------------------------------------------------- the extractors
#
#  Each returns (pages, scan_pages, bad_pages):
#    pages       [(page_number_or_NO_PAGE, text), ...] in document order
#    scan_pages  [page_number, ...] - the page exists and holds no text at all
#    bad_pages   [page_number, ...] - the page exists and would not decode
#
#  Nothing in here guesses. A page with no text is reported as having no text; it is
#  never filled in from the page before it, and the assistant is never told it said
#  something. That is the whole of THE CITATION's "never invent scan contents", and
#  the only place it can be honoured is here, at the point where the text either
#  exists or does not.

def _decode(raw):
    """Bytes to text, and it always succeeds. errors="replace", per the contract."""
    for encoding in ("utf-8-sig", "utf-8", "cp1252"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", "replace")


def _plain_pages(path):
    with open(path, "rb") as fh:
        return [(NO_PAGE, _decode(fh.read()))], [], []


def _markdown_pages(path):
    """Markdown, cleaned by build.py's own cleaner so a chunk reads like prose.

    Imported lazily, and only here: build.py imports this module to run the vector pass
    at the end of a build, so a top-level import in the other direction would be a
    cycle. If that import ever fails the raw markdown is chunked instead, which is
    worse prose and a perfectly good vector.
    """
    with open(path, "rb") as fh:
        raw = _decode(fh.read())
    try:
        import build
        prose = build.clean_for_excerpt(raw, Path(path).stem)
    except Exception:                                          # noqa: BLE001
        prose = raw
    return [(NO_PAGE, prose)], [], []


def _pdf_pages(path):
    """One entry per page, with the page's own number, which is the whole point.

    A PDF is the only format here that has pages at all, so it is the only one that can
    be cited to one - and a citation to "page 4" that came from counting characters
    rather than from the page tree would be a guess wearing a number.
    """
    try:
        from pypdf import PdfReader
    except ImportError as exc:                                 # pragma: no cover
        raise BadDocument("pypdf is not installed (%s)" % exc)
    import logging
    import warnings
    # pypdf reports a malformed file twice: once through warnings, and once through its
    # own logger, which writes to stderr whatever the warning filter says. A corrupt file
    # is ALREADY reported by this module, with the path and the reason, so the library's
    # own "EOF marker not found" is a second voice saying less. Quietened here rather
    # than globally, so nothing else in the process has its logging changed.
    logging.getLogger("pypdf").setLevel(logging.CRITICAL)
    pages, scans, bad = [], [], []
    try:
        with warnings.catch_warnings():
            # pypdf is chatty about malformed-but-readable files. The verdict we care
            # about is whether text came out, and that is tested directly below.
            warnings.simplefilter("ignore")
            reader = PdfReader(str(path), strict=False)
            if getattr(reader, "is_encrypted", False):
                try:
                    # An empty owner password is the common case for "protected" files
                    # that are not actually secret. A real password is not guessed at.
                    if not reader.decrypt(""):
                        raise BadDocument("the file is encrypted")
                except BadDocument:
                    raise
                except Exception as exc:                       # noqa: BLE001
                    raise BadDocument("the file is encrypted (%s)" % exc)
            total = len(reader.pages)
            for number in range(1, total + 1):
                try:
                    with warnings.catch_warnings():
                        warnings.simplefilter("ignore")
                        text = reader.pages[number - 1].extract_text() or ""
                except Exception as exc:                       # noqa: BLE001
                    bad.append(number)
                    _say("      ! %s page %d would not decode (%s); skipped"
                         % (rel_of(path), number, type(exc).__name__))
                    continue
                text = text.replace("\x00", " ")
                if text.strip():
                    pages.append((number, text))
                else:
                    # THE SCAN. The page is there, it has area, and it has no text: an
                    # image of writing. Recorded by number so the assistant can say so.
                    scans.append(number)
    except BadDocument:
        raise
    except Exception as exc:                                   # noqa: BLE001
        raise BadDocument("%s: %s" % (type(exc).__name__, exc))
    if not pages and not scans and not bad:
        raise BadDocument("no pages at all")
    return pages, scans, bad


_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_WT_RE = re.compile(r"<w:t(?:\s[^>]*)?>(.*?)</w:t>", re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")


def _docx_pages(path):
    """A .docx is a zip of XML, so the standard library is enough to read one.

    NO PAGE NUMBERS, and that is a fact about the format rather than a shortcut: a Word
    document has no pages until something lays it out, and the page you would see
    depends on the printer driver. So a .docx is cited by file alone, and a citation
    that named a page would be inventing one.
    """
    import zipfile
    import xml.etree.ElementTree as ET
    try:
        with zipfile.ZipFile(str(path)) as zf:
            try:
                raw = zf.read("word/document.xml")
            except KeyError:
                raise BadDocument("no word/document.xml inside it")
    except BadDocument:
        raise
    except Exception as exc:                                   # noqa: BLE001
        raise BadDocument("%s: %s" % (type(exc).__name__, exc))

    paragraphs = []
    try:
        root = ET.fromstring(raw)
        for para in root.iter(_W + "p"):
            parts = []
            for node in para.iter():
                if node.tag == _W + "t":
                    parts.append(node.text or "")
                elif node.tag in (_W + "tab",):
                    parts.append("\t")
                elif node.tag in (_W + "br", _W + "cr"):
                    parts.append("\n")
            line = "".join(parts).strip()
            if line:
                paragraphs.append(line)
    except ET.ParseError:
        # A document.xml that will not parse is still usually readable: the run texts
        # are right there between tags. Worse structure, same words, and the
        # alternative is losing the file entirely.
        text = _decode(raw)
        for hit in _WT_RE.findall(text):
            line = _TAG_RE.sub("", hit).strip()
            if line:
                paragraphs.append(line)
        if not paragraphs:
            raise BadDocument("word/document.xml is malformed and holds no run text")
    body = "\n\n".join(paragraphs)
    if not body.strip():
        raise BadDocument("it has no text in it")
    return [(NO_PAGE, body)], [], []


def extract(path):
    """(pages, scan_pages, bad_pages) for any suffix this file claims to read."""
    suffix = Path(path).suffix.lower()
    if suffix in (".md", ".markdown"):
        return _markdown_pages(path)
    if suffix == ".txt":
        return _plain_pages(path)
    if suffix == ".pdf":
        return _pdf_pages(path)
    if suffix == ".docx":
        return _docx_pages(path)
    raise BadDocument("nothing here reads %s files" % (suffix or "extensionless"))


# ------------------------------------------------------------------ the chunker

_WS_RE = re.compile(r"[ \t\u00a0]+")
_NL_RE = re.compile(r"\n{3,}")


def tidy(text):
    """Collapse the whitespace a PDF extractor leaves behind, keep the paragraphs."""
    text = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    text = _WS_RE.sub(" ", text)
    text = "\n".join(line.strip() for line in text.split("\n"))
    return _NL_RE.sub("\n\n", text).strip()


def chunk_pages(pages):
    """[(page, text)] -> [{"text", "page", "page_end"}], ~CHUNK_WORDS with overlap.

    THE CHUNK MAY CROSS A PAGE BREAK, AND IT IS CITED TO THE PAGE IT STARTS ON. Both
    halves of that are deliberate. Cutting strictly at page boundaries sounds tidier
    and is worse: a clause that begins at the foot of page 4 and ends at the head of
    page 5 becomes two half-thoughts, each embedded as though the other did not exist,
    and the question that asks about the whole clause matches neither well. So the
    words run on - and the page recorded is the page where the passage BEGINS, which is
    where a reader opening the file would want to look. page_end is kept beside it so a
    citation that spans two pages can say so instead of pretending it does not.
    """
    words = []            # [(word, page)]
    for page, text in pages:
        for word in tidy(text).split():
            words.append((word, page))
    chunks = []
    step = max(1, CHUNK_WORDS - OVERLAP_WORDS)
    start = 0
    total = len(words)
    while start < total:
        window = words[start:start + CHUNK_WORDS]
        if not window:
            break
        # The tail of a document is folded into the chunk before it rather than kept as
        # a three-word chunk of its own: a vector built from "Signed, A. Patel" is a
        # near-match for every signature block in the corpus.
        if len(window) < MIN_CHUNK_WORDS and chunks:
            break
        text = " ".join(w for w, _ in window)
        pages_in = [p for _, p in window if p != NO_PAGE]
        chunks.append({
            "text": text,
            "page": pages_in[0] if pages_in else NO_PAGE,
            "page_end": pages_in[-1] if pages_in else NO_PAGE,
        })
        if start + CHUNK_WORDS >= total:
            break
        start += step
    return chunks


# ----------------------------------------------------------------- the embedder

def _post(url, payload, timeout):
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, body, {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as res:
        return json.loads(res.read().decode("utf-8", "replace"))


def embed(texts, kind="document", cfg=None):
    """Text in, unit-length vectors out, through Ollama on this machine.

    Batched, because the per-call overhead is most of the cost for short chunks, and
    because a thousand-chunk corpus is thirty round trips rather than a thousand.

    TWO ENDPOINTS, because Ollama renamed this one. /api/embed is the current shape and
    takes a list; /api/embeddings is the old one and takes a single prompt. Trying the
    modern one first and falling back means this works on whatever is installed instead
    of requiring a version nobody was told to have.
    """
    cfg = cfg or settings()
    base = cfg["ollama_url"]
    model = cfg["embed_model"]
    prefix = DOC_PREFIX if kind == "document" else QUERY_PREFIX
    items = [prefix + str(t or "") for t in texts]
    if not items:
        return []
    out = []
    for at in range(0, len(items), EMBED_BATCH):
        batch = items[at:at + EMBED_BATCH]
        try:
            data = _post(base + "/api/embed",
                         {"model": model, "input": batch}, EMBED_TIMEOUT)
            vectors = data.get("embeddings")
            if not isinstance(vectors, list) or len(vectors) != len(batch):
                raise EmbedDown("/api/embed returned %s vectors for %d inputs"
                                % (len(vectors) if isinstance(vectors, list) else "no",
                                   len(batch)))
        except urllib.error.HTTPError as exc:
            if exc.code not in (404, 405):
                raise EmbedDown("%s said HTTP %s" % (base, exc.code))
            vectors = []
            for one in batch:
                try:
                    legacy = _post(base + "/api/embeddings",
                                   {"model": model, "prompt": one}, EMBED_TIMEOUT)
                except Exception as exc2:                      # noqa: BLE001
                    raise EmbedDown("neither /api/embed nor /api/embeddings answered "
                                    "on %s (%s)" % (base, exc2))
                vec = legacy.get("embedding")
                if not isinstance(vec, list) or not vec:
                    raise EmbedDown("/api/embeddings returned no vector; is %r pulled? "
                                    "try: ollama pull %s" % (model, model))
                vectors.append(vec)
        except urllib.error.URLError as exc:
            raise EmbedDown("could not reach Ollama at %s (%s) - is it running?"
                            % (base, getattr(exc, "reason", exc)))
        except EmbedDown:
            raise
        except Exception as exc:                               # noqa: BLE001
            raise EmbedDown("%s: %s" % (type(exc).__name__, exc))
        for vec in vectors:
            out.append([float(x) for x in vec])
    return out


# --------------------------------------------------------------------- the store
#
#  ChromaDB, opened lazily and once. The import is half a second and the first open of
#  a fresh store is four, which is nothing in a rebuild and would be four seconds of a
#  question if it happened on the request path - so server.py warms this in a thread at
#  startup and every question after that pays nothing. Everything in here is guarded:
#  the store is a file on disk, files on disk get corrupted, and the answer to a
#  corrupt store is the keyword index and a line in the log.

_store_lock = threading.Lock()
_store = {"collection": None, "why": "not opened yet", "opened": 0.0, "stamp": None}


def _stamp():
    """A cheap fingerprint of the store's own bookkeeping: the manifest's mtime and size.

    Two syscalls, microseconds, and it is the whole of how a long-running server notices
    that somebody rebuilt the index underneath it. The manifest is written last and
    atomically by reindex(), so a changed stamp means a finished rebuild - never a
    half-written one.
    """
    try:
        st = MANIFEST_PATH.stat()
        return (st.st_mtime_ns, st.st_size)
    except OSError:
        return None


def _drop_system_cache():
    """Make ChromaDB forget every client it is holding for this process.

    THE REASON THIS FUNCTION HAS TO EXIST, measured rather than assumed. ChromaDB keeps
    one System per store path in a process-wide cache, so asking for a PersistentClient
    on the same path a second time hands back the FIRST one - HNSW index and all. That
    index lives in memory. When `python build.py` adds rows in a separate process, a
    server holding the old handle sees them in count() (that reads sqlite) and does NOT
    see them in query() (that reads the in-memory graph). The symptom is the worst kind:
    retrieval that works perfectly, on yesterday's corpus, with no error anywhere.

    Clearing the cache and reopening returns the new rows immediately - verified on this
    machine with a row added by a child process and a query that then ranked it first.
    Guarded, because it reaches for a class path that is chromadb's business and not ours:
    if it ever moves, the worst case is a handle that stays warm a little too long, and
    the next restart fixes it.
    """
    try:
        try:
            from chromadb.api.shared_system_client import SharedSystemClient
        except ImportError:                     # older layouts kept it in api.client
            from chromadb.api.client import SharedSystemClient
        SharedSystemClient.clear_system_cache()
        return True
    except Exception as exc:                                   # noqa: BLE001
        _say("  vectors    : could not clear the client cache (%s: %s); a restart will "
             "pick up the rebuild" % (type(exc).__name__, exc))
        return False


def _open_collection(create=True):
    import chromadb
    from chromadb.config import Settings
    STORE_DIR.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(
        path=str(STORE_DIR),
        settings=Settings(anonymized_telemetry=False, allow_reset=False))
    if not create:
        names = [c.name for c in client.list_collections()]
        if COLLECTION not in names:
            raise IngestError("the store has no %r collection yet" % COLLECTION)
    # embedding_function=None on purpose: every vector in here is one we computed with
    # the model we chose. A collection holding a default embedder would quietly embed
    # anything added without vectors using a different model entirely.
    return client.get_or_create_collection(
        name=COLLECTION, metadata={"hnsw:space": "cosine"}, embedding_function=None)


def collection(create=False):
    """The one collection, or None with a reason left in _store["why"].

    Cached, and REVALIDATED against the manifest on every call - see _stamp(). That is the
    line that makes "rebuild the index while the server is running" work, which is not an
    exotic case: it is what preflight does, what the employer does after filing a new
    contract, and what anybody does the first time they try this feature out. Two syscalls
    on the request path buys an index that is never silently a build behind.
    """
    stamp = _stamp()
    with _store_lock:
        col = _store["collection"]
        if col is not None and _store["stamp"] == stamp:
            return col
        stale = col is not None
        if stale:
            _store["collection"] = None
    if stale:
        _say("  vectors    : the store changed on disk; reopening")
        _drop_system_cache()
    try:
        started = time.monotonic()
        col = _open_collection(create=create)
        took = time.monotonic() - started
    except Exception as exc:                                   # noqa: BLE001
        with _store_lock:
            _store["why"] = "%s: %s" % (type(exc).__name__, exc)
        return None
    with _store_lock:
        _store["collection"] = col
        _store["why"] = ""
        _store["opened"] = took
        _store["stamp"] = stamp
    return col


def forget_store():
    """Drop the handle, so the next caller reopens. Used after a rebuild."""
    with _store_lock:
        _store["collection"] = None
        _store["why"] = "not opened yet"
        _store["stamp"] = None


# ------------------------------------------------------------------ the manifest

def load_manifest():
    try:
        with open(MANIFEST_PATH, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, dict) and isinstance(data.get("files"), dict):
            return data
    except Exception:                                          # noqa: BLE001
        pass
    return {"scheme": SCHEME, "model": _DEFAULTS["embed_model"], "files": {},
            "built": "", "chunks": 0}


def save_manifest(manifest):
    """Written to a temporary file and moved into place, so an interrupted rebuild
    leaves the previous manifest rather than half of a new one."""
    STORE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = MANIFEST_PATH.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=1, sort_keys=True)
        fh.write("\n")
    os.replace(tmp, MANIFEST_PATH)
    # AND THE WRITER IS NOT STALE. This process added the rows itself, so its in-memory
    # index already holds them; without this line collection() would see a new stamp,
    # conclude somebody else had rebuilt, and throw away a perfectly warm handle at the
    # end of every build.
    with _store_lock:
        if _store["collection"] is not None:
            _store["stamp"] = _stamp()


def chunk_ids(rel, count):
    """Stable ids for one file's chunks: a hash of the path, and an ordinal.

    A hash rather than the path itself because an id is also a key in a sqlite index,
    and a path can hold a quote, a hash, a space or a character the store would rather
    not see. Stable across rebuilds, so re-embedding a changed file overwrites its own
    rows instead of accumulating a second copy beside them.
    """
    stem = hashlib.sha1(rel.encode("utf-8")).hexdigest()[:16]
    return ["%s#%04d" % (stem, i) for i in range(count)]


# -------------------------------------------------------------------- the build

def reindex(roots=ROOTS, base=ROOT, force=False, log=_say):
    """Walk, hash, embed what changed, and leave the store exactly matching the disk.

    Returns a summary dict. Raises EmbedDown only if there was something to embed and
    the embedder would not answer - an unchanged corpus needs no embedder at all, which
    is what makes a no-op rebuild take a quarter of a second and no model load.
    """
    started = time.monotonic()
    cfg = settings()
    manifest = load_manifest()
    if manifest.get("scheme") != SCHEME or manifest.get("model") != cfg["embed_model"]:
        # THE SCHEME CHANGED, so every vector in there was made by different rules and
        # none of them is comparable with a new one. Said out loud, because "the rebuild
        # took four minutes this time" deserves a reason.
        if manifest.get("files"):
            log("  vectors    : scheme changed (%s -> %s); re-embedding everything"
                % (manifest.get("scheme"), SCHEME))
        force = True
        manifest = {"scheme": SCHEME, "model": cfg["embed_model"], "files": {},
                    "built": "", "chunks": 0}

    col = collection(create=True)
    if col is None:
        raise IngestError("could not open the vector store at %s (%s)"
                          % (rel_of(STORE_DIR, base), _store["why"]))

    on_disk = walk(roots, base)
    known = manifest["files"]
    summary = {"files": len(on_disk), "fresh": 0, "changed": 0, "unchanged": 0,
               "removed": 0, "skipped": 0, "chunks": 0, "embedded": 0,
               "scans": 0, "scan_files": 0, "pages": 0, "roots": list(roots),
               "seconds": 0.0, "model": cfg["embed_model"], "threshold":
               cfg["notes_threshold"]}

    # ---- gone from the disk, so gone from the store. Before the adds, so that a file
    # renamed in the same rebuild cannot have its new rows deleted by its old name.
    for rel in sorted(set(known) - set(on_disk)):
        ids = known[rel].get("ids") or []
        if ids:
            try:
                col.delete(ids=ids)
            except Exception as exc:                           # noqa: BLE001
                log("      ! could not drop the old rows for %s (%s)" % (rel, exc))
        known.pop(rel, None)
        summary["removed"] += 1
        log("      - %s is gone; %d chunk%s dropped"
            % (rel, len(ids), "" if len(ids) == 1 else "s"))

    for rel in on_disk:
        path = Path(base) / rel
        try:
            fingerprint = file_fingerprint(path)
        except Exception as exc:                               # noqa: BLE001
            summary["skipped"] += 1
            log("      ! %s could not be read (%s); skipped" % (rel, exc))
            continue
        row = known.get(rel)
        if (not force and row and row.get("hash") == fingerprint
                and not row.get("skipped")):
            summary["unchanged"] += 1
            summary["chunks"] += int(row.get("chunks") or 0)
            summary["pages"] += int(row.get("pages") or 0)
            if row.get("scan_pages"):
                summary["scans"] += len(row["scan_pages"])
                summary["scan_files"] += 1
            continue

        try:
            pages, scans, bad = extract(path)
        except BadDocument as exc:
            # ONE BAD FILE, LOGGED AND SKIPPED, AND THE WALK CARRIES ON. Recorded in the
            # manifest so the next rebuild tries it again: a file that was being written
            # while we read it is not permanently broken, and a verdict cached for ever
            # would make it so.
            summary["skipped"] += 1
            if row and row.get("ids"):
                try:
                    col.delete(ids=row["ids"])
                except Exception:                              # noqa: BLE001
                    pass
            known[rel] = {"hash": fingerprint, "skipped": str(exc), "ids": [],
                          "chunks": 0, "pages": 0, "scan_pages": [],
                          "kind": path.suffix.lower().lstrip(".")}
            log("      ! %s skipped: %s" % (rel, exc))
            continue
        except Exception as exc:                               # noqa: BLE001
            summary["skipped"] += 1
            log("      ! %s skipped: unexpected %s: %s" % (rel, type(exc).__name__, exc))
            continue

        chunks = chunk_pages(pages)
        page_count = len(pages) + len(scans) + len(bad)
        if chunks:
            vectors = embed([c["text"] for c in chunks], "document", cfg)
            summary["embedded"] += len(vectors)
        else:
            vectors = []
        ids = chunk_ids(rel, len(chunks))

        # The old rows go before the new ones arrive. Same ids in most cases, so an add
        # would be an upsert anyway - but a file that shrank from nine chunks to four
        # would otherwise keep five stale vectors that still answer questions.
        if row and row.get("ids"):
            try:
                col.delete(ids=row["ids"])
            except Exception as exc:                           # noqa: BLE001
                log("      ! could not drop the previous rows for %s (%s)" % (rel, exc))
        if chunks:
            col.add(ids=ids, embeddings=vectors,
                    documents=[c["text"] for c in chunks],
                    metadatas=[{"file": rel, "page": int(c["page"]),
                                "page_end": int(c["page_end"]),
                                "kind": path.suffix.lower().lstrip("."),
                                "chunk": i, "of": len(chunks)}
                               for i, c in enumerate(chunks)])

        known[rel] = {"hash": fingerprint, "ids": ids, "chunks": len(chunks),
                      "pages": page_count, "scan_pages": scans, "bad_pages": bad,
                      "kind": path.suffix.lower().lstrip("."),
                      "words": sum(len(c["text"].split()) for c in chunks)}
        summary["chunks"] += len(chunks)
        summary["pages"] += page_count
        if scans:
            summary["scans"] += len(scans)
            summary["scan_files"] += 1
        if row:
            summary["changed"] += 1
        else:
            summary["fresh"] += 1
        note = ""
        if scans:
            note += ", %d image-only page%s" % (len(scans), "" if len(scans) == 1 else "s")
        if bad:
            note += ", %d unreadable page%s" % (len(bad), "" if len(bad) == 1 else "s")
        log("      %s %s: %d chunk%s%s"
            % ("+" if not row else "~", rel, len(chunks),
               "" if len(chunks) == 1 else "s", note))

    manifest["files"] = known
    manifest["scheme"] = SCHEME
    manifest["model"] = cfg["embed_model"]
    manifest["chunks"] = summary["chunks"]
    manifest["built"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    save_manifest(manifest)
    summary["seconds"] = time.monotonic() - started
    try:
        summary["rows"] = col.count()
    except Exception:                                          # noqa: BLE001
        summary["rows"] = summary["chunks"]
    return summary


# ------------------------------------------------------------------- the recall

def _cosine_from_distance(distance):
    """Chroma's cosine space returns 1 - cos, so this is the similarity back again."""
    try:
        sim = 1.0 - float(distance)
    except (TypeError, ValueError):
        return 0.0
    return max(-1.0, min(1.0, sim))


def _dead(why, threshold=NOTES_THRESHOLD):
    return {"available": False, "why": why, "hits": [], "best": 0.0, "best3": 0.0,
            "opens": False, "threshold": threshold, "cited": [], "scans": [],
            "ms": 0}


def recall(question, prior="", top_k=TOP_K, cfg=None):
    """THE READ HALF. Question in, at most five chunks out, with a verdict.

        available   False means "use the keyword index", and it is never an error the
                    employer has to see: no store, no Ollama, an empty collection and a
                    corrupt sqlite file all arrive here as the same quiet False.
        best3       the best similarity among the top three, 0..1
        opens       best3 >= threshold: the notes door may open on this alone
        cited       the hits worth showing the model and naming on the card
        scans       image-only pages in the files that were cited, so the assistant can
                    say "there is no text in it for me to read" instead of guessing

    THIS FUNCTION NEVER RAISES. Every failure is a fallback, and the fallback is the
    keyword retrieval that has always been there.
    """
    cfg = cfg or settings()
    threshold = cfg["notes_threshold"]
    if not cfg["vector_recall"]:
        return _dead("vector_recall is off in config.json", threshold)
    text = str(question or "").strip()
    if not text:
        return _dead("nothing was asked", threshold)
    # A BARE FOLLOW-UP HAS NOTHING TO EMBED. "why not?" is three words of grammar and no
    # subject, and its vector points at nothing in particular - so the question before it
    # is prepended, exactly as score_notes() lends the prior to the keyword scorer. Only
    # for genuinely short questions: a full sentence is its own best query, and padding
    # it with the previous one drags the search towards a subject that has been left.
    if prior and len(text.split()) <= 3:
        text = "%s %s" % (str(prior).strip(), text)

    started = time.monotonic()
    col = collection(create=False)
    if col is None:
        return _dead(_store["why"] or "the vector store is not open", threshold)
    try:
        rows = col.count()
    except Exception as exc:                                   # noqa: BLE001
        return _dead("the store would not answer (%s)" % exc, threshold)
    if not rows:
        # THE EMPTY STORE IS A FALLBACK, NOT A FAILURE, and it is the one the spec names:
        # a fresh checkout has no vectors and must still answer questions.
        return _dead("the vector store is empty; run build.py", threshold)

    try:
        vector = embed([text], "query", cfg)[0]
    except EmbedDown as exc:
        return _dead(str(exc), threshold)
    except Exception as exc:                                   # noqa: BLE001
        return _dead("%s: %s" % (type(exc).__name__, exc), threshold)

    try:
        got = col.query(query_embeddings=[vector],
                        n_results=max(1, min(int(top_k), rows)),
                        include=["documents", "metadatas", "distances"])
    except Exception as exc:                                   # noqa: BLE001
        return _dead("the query failed (%s)" % exc, threshold)

    ids = (got.get("ids") or [[]])[0]
    docs = (got.get("documents") or [[]])[0]
    metas = (got.get("metadatas") or [[]])[0]
    dists = (got.get("distances") or [[]])[0]
    hits = []
    for i, cid in enumerate(ids):
        meta = metas[i] if i < len(metas) else {}
        meta = meta if isinstance(meta, dict) else {}
        page = int(meta.get("page", NO_PAGE) or NO_PAGE)
        end = int(meta.get("page_end", page) or page)
        hits.append({
            "id": str(cid),
            "file": str(meta.get("file") or ""),
            "name": Path(str(meta.get("file") or "")).name,
            "page": page if page > 0 else None,
            "page_end": end if end > 0 else None,
            "kind": str(meta.get("kind") or ""),
            "chunk": int(meta.get("chunk", 0) or 0),
            "of": int(meta.get("of", 0) or 0),
            "score": round(_cosine_from_distance(dists[i] if i < len(dists) else 1.0), 4),
            "text": str(docs[i] if i < len(docs) else ""),
        })

    best = max((h["score"] for h in hits), default=0.0)
    best3 = max((h["score"] for h in hits[:GATE_TOP]), default=0.0)
    opens = best3 >= threshold
    floor = max(threshold, best * CITE_RATIO)
    cited = [h for h in hits if h["score"] >= floor] if opens else []
    if opens and not cited:
        cited = hits[:1]
    return {"available": True, "why": "", "hits": hits, "best": round(best, 4),
            "best3": round(best3, 4), "opens": opens, "threshold": threshold,
            "cited": cited, "scans": scan_pages_for(h["file"] for h in cited),
            "ms": int((time.monotonic() - started) * 1000)}


# ------------------------------------------------------------------ the citation

def cite_label(hit):
    """'Q3_Contract.pdf · page 4' - the sentence the side panel shows, built once here.

    One function so that the panel, the chip's tooltip and any harness that checks the
    wording are all reading the same string. A .docx or a .md has no page, so it is
    named alone rather than given a page it does not have.
    """
    name = hit.get("name") or Path(str(hit.get("file") or "")).name or "untitled"
    page, end = hit.get("page"), hit.get("page_end")
    if not page:
        return name
    if end and end > page:
        return "%s \u00b7 pages %d\u2013%d" % (name, page, end)
    return "%s \u00b7 page %d" % (name, page)


def citations(hits, limit=TOP_K):
    """What the BROWSER is told about a citation, over a fixed set of keys.

    A copy-through like web_sources() in server.py, and for the same reason: the page
    gets a file name, a page number, a label and a score, and never the absolute path of
    anything on this disk. "archive/Q3_Contract.pdf" is a relative path inside the
    project and is the one the employer would type; "C:\\Users\\..." is a fact about
    this machine that the browser has no business holding.
    """
    out = []
    for hit in hits[:limit]:
        rel = str(hit.get("file") or "")
        if not rel or rel.startswith(("/", "\\")) or ":" in rel or ".." in rel:
            continue                    # not a relative path inside the project; drop it
        out.append({
            "file": rel,
            "name": hit.get("name") or Path(rel).name,
            "page": hit.get("page") or None,
            "pageEnd": hit.get("page_end") or None,
            "label": cite_label(hit),
            "kind": hit.get("kind") or Path(rel).suffix.lstrip("."),
            "score": float(hit.get("score") or 0.0),
        })
    return out


def scan_pages_for(files):
    """[{"file", "name", "page", "line"}] for every image-only page in these files.

    Read from the manifest rather than from the document, because the manifest is where
    the extractor already wrote down what it found - and because opening a PDF again on
    the request path to re-learn something we know is a hundred milliseconds spent on
    nothing.
    """
    manifest = load_manifest()
    rows = manifest.get("files") or {}
    out, seen = [], set()
    for rel in files:
        rel = str(rel or "")
        if rel in seen or rel not in rows:
            continue
        seen.add(rel)
        for page in (rows[rel].get("scan_pages") or []):
            out.append({"file": rel, "name": Path(rel).name, "page": int(page),
                        "line": SCAN_LINE % int(page)})
    return out


def image_only_files():
    """Files that are all photograph and no text: every page a scan, nothing indexed.

    These cannot be found by searching, because there is nothing in them to search. So
    they are matched by NAME instead - see name_match() - and the honest line is all
    they can ever produce.
    """
    rows = (load_manifest().get("files") or {})
    out = []
    for rel, row in sorted(rows.items()):
        if not row.get("chunks") and row.get("scan_pages"):
            out.append({"file": rel, "name": Path(rel).name,
                        "pages": sorted(int(p) for p in row["scan_pages"])})
    return out


_WORD_RE = re.compile(r"[a-z0-9]+")
_NAME_STOP = {"the", "a", "an", "of", "and", "pdf", "docx", "txt", "md", "doc",
              "file", "final", "copy", "scan", "scanned", "v1", "v2", "draft"}


def name_match(question, candidates=None):
    """Which image-only file, if any, the question is actually about, by its name.

    Deliberately strict: every distinctive word of the file's own name has to appear in
    the question. "what does the Q3 contract say" finds Q3_Contract_scan.pdf; "what is
    our pricing" does not, and must not - an honest line about the wrong file is still
    the wrong answer.
    """
    words = set(_WORD_RE.findall(str(question or "").lower()))
    if not words:
        return None
    best = None
    for row in (candidates if candidates is not None else image_only_files()):
        stem = Path(row["name"]).stem
        parts = [w for w in _WORD_RE.findall(stem.lower()) if w not in _NAME_STOP]
        parts = [w for w in parts if len(w) > 1]
        if not parts:
            continue
        if all(w in words for w in parts):
            # The longest name that fully matches wins: "q3 contract" beats "contract".
            if best is None or len(parts) > best[0]:
                best = (len(parts), row)
    return best[1] if best else None


# --------------------------------------------------------------------- the state

def store_state(cfg=None):
    """What /health may say about all this: numbers, names and booleans only.

    Every value in here is safe to hand to the browser, which is why it is assembled in
    one function that can be read in one screen. No path outside the project, no key, no
    credential - there is no credential in this subsystem at all, and the only URL is
    the loopback address of a model server on this machine.
    """
    cfg = cfg or settings()
    manifest = load_manifest()
    rows = manifest.get("files") or {}
    scans = sum(len(r.get("scan_pages") or []) for r in rows.values())
    skipped = [rel for rel, r in rows.items() if r.get("skipped")]
    state = {
        "on": bool(cfg["vector_recall"]),
        "present": MANIFEST_PATH.exists(),
        "files": len(rows),
        "chunks": int(manifest.get("chunks") or 0),
        "scanPages": scans,
        "imageOnly": len(image_only_files()),
        "skipped": len(skipped),
        "model": cfg["embed_model"],
        "threshold": round(float(cfg["notes_threshold"]), 3),
        "scheme": SCHEME,
        "built": str(manifest.get("built") or ""),
        "chunkTokens": CHUNK_TOKENS,
        "overlapTokens": CHUNK_OVERLAP_TOKENS,
    }
    col = None
    with _store_lock:
        col = _store["collection"]
        why = _store["why"]
    if col is not None:
        try:
            state["rows"] = col.count()
        except Exception:                                      # noqa: BLE001
            state["rows"] = None
        state["ready"] = True
    else:
        state["ready"] = False
        state["why"] = str(why or "")[:200]
    return state


def warm(log=None):
    """Open the store now, on a thread, so no question ever pays for the first open.

    Four seconds the first time a ChromaDB is opened, a fraction of that afterwards.
    Called by server.py at startup; safe to call twice, and safe to call on a machine
    with no store at all - it reports and returns.
    """
    col = collection(create=False)
    if log:
        if col is None:
            log("server.py: vector recall is standing by on the keyword index (%s)"
                % (_store["why"] or "no store"))
        else:
            try:
                rows = col.count()
            except Exception:                                  # noqa: BLE001
                rows = "?"
            log("server.py: vector store open in %.1fs, %s chunks"
                % (_store["opened"], rows))
    return col is not None


# ----------------------------------------------------------------------- the cli

def _print_summary(summary):
    _say("  vectors    : %d file%s, %d chunk%s in the store (%d embedded now)"
         % (summary["files"], "" if summary["files"] == 1 else "s",
            summary["chunks"], "" if summary["chunks"] == 1 else "s",
            summary["embedded"]))
    _say("               %d new, %d changed, %d unchanged, %d removed, %d skipped"
         % (summary["fresh"], summary["changed"], summary["unchanged"],
            summary["removed"], summary["skipped"]))
    if summary["scans"]:
        _say("               %d image-only page%s in %d file%s - honestly reported, "
             "never guessed at"
             % (summary["scans"], "" if summary["scans"] == 1 else "s",
                summary["scan_files"], "" if summary["scan_files"] == 1 else "s"))
    _say("               %s, threshold %.2f, in %.1fs"
         % (summary["model"], summary["threshold"], summary["seconds"]))


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--ask" in argv:
        at = argv.index("--ask")
        question = " ".join(argv[at + 1:]) or "what colour is the car?"
        got = recall(question)
        _say("  %r" % question)
        if not got["available"]:
            _say("  no vector recall: %s" % got["why"])
            return 1
        _say("  best %.4f (top three %.4f), threshold %.2f -> %s"
             % (got["best"], got["best3"], got["threshold"],
                "THE NOTES ANSWER THIS" if got["opens"] else "the web gate decides"))
        for hit in got["hits"]:
            _say("    %.4f  %-44s %s"
                 % (hit["score"], cite_label(hit),
                    re.sub(r"\s+", " ", hit["text"])[:70]))
        for scan in got["scans"]:
            _say("    scan:  %s" % scan["line"])
        return 0
    force = "--force" in argv
    try:
        summary = reindex(force=force)
    except IngestError as exc:
        _say("ingest.py: %s" % exc)
        return 1
    _print_summary(summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
