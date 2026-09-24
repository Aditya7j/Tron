#!/usr/bin/env python3
"""
build.py - Knowledge Galaxy indexer, and the ingestion engine behind it.

TWO INDEXES, from one walk of the disk, and they answer different questions.

  THE GALAXY, from every .md under the notes directory:
    viewer/graph-data.js  ->  const GRAPH = {nodes: [...], links: [...]}
    notes-index.json      ->  the same nodes plus full note text, for the brain
                              (kept in the PROJECT ROOT, never inside viewer/)

  THE VECTORS, from every .md .txt .pdf and .docx under notes/ AND archive/:
    vector-store/         ->  a persistent ChromaDB of ~500-token chunks, each with
                              its text, its path, its page number and its embedding

Contract that the rest of the project depends on, and that this file will not break:
  every node's `id` is a plain integer equal to its index in GRAPH.nodes,
  and notes-index.json lists the notes in exactly the same order.

WHY THE GALAXY IS STILL MARKDOWN ONLY. A planet is a note somebody wrote and linked to
other notes; a scanned contract in archive/ is neither. Adding one as a star would put
an unlinked dot in the sky for every file anybody ever filed, and the shape of the
galaxy is the shape of the thinking in notes/. So the graph is untouched by this - the
archive is searchable, citable and readable, and it is not a constellation.

The vector pass is incremental and hashed, so a rebuild of an unchanged corpus is a
quarter of a second and does not wake the embedder at all. It is also OPTIONAL: if
ChromaDB or Ollama is not there, the reason is printed and the galaxy is still built,
because the keyword brain has always worked without either.

Python 3. The galaxy half is standard library only; the vector half lives in ingest.py
and needs chromadb, pypdf and a local Ollama.

Usage:
    python build.py                 # auto-detects ./notes, else the project root
    python build.py path/to/notes
    python build.py --no-vectors    # the galaxy only, no embedding
    python build.py --vectors-only  # the vector store only, leave the galaxy alone
    python build.py --force-vectors # re-embed every chunk, ignoring the hashes
"""

import json
import os
import re
import sys
import unicodedata
from datetime import datetime, timezone

# ---------------------------------------------------------------- configuration

EXCERPT_CHARS = 700          # roughly, cut on a word boundary
SHARED_WIKILINK_MIN = 6      # co-citation: N shared [[targets]] => a link
MIN_MENTION_SLUG_WORDS = 2   # single-word titles are too generic to match on
MIN_MENTION_WORD_LEN = 6     # ...unless that one word is long

SKIP_DIRS = {
    ".git", ".svn", ".hg", "node_modules", "viewer", "__pycache__",
    ".obsidian", ".trash", ".vscode", ".idea", "venv", ".venv", "env",
}

# Words that should not be Title Cased when a label is built from a filename.
ACRONYMS = {
    "pnl": "PnL", "okr": "OKR", "okrs": "OKRs", "kpi": "KPI", "kpis": "KPIs",
    "roi": "ROI", "sop": "SOP", "sops": "SOPs", "faq": "FAQ", "faqs": "FAQs",
    "api": "API", "ui": "UI", "ux": "UX", "ai": "AI", "hr": "HR", "it": "IT",
    "b2b": "B2B", "b2c": "B2C", "seo": "SEO", "crm": "CRM", "saas": "SaaS",
    "q1": "Q1", "q2": "Q2", "q3": "Q3", "q4": "Q4", "eu": "EU", "us": "US",
    "uk": "UK", "vat": "VAT", "cogs": "COGS", "ltv": "LTV", "cac": "CAC",
}
LOWERCASE_WORDS = {"and", "or", "of", "the", "a", "an", "to", "for", "in",
                   "on", "at", "vs", "with"}

# ---------------------------------------------------------------------- helpers

WIKILINK_RE = re.compile(r"\[\[([^\]\[]+?)\]\]")
FRONTMATTER_RE = re.compile(r"\A---\s*\n.*?\n---\s*\n", re.DOTALL)
CODEFENCE_RE = re.compile(r"^```.*?^```", re.DOTALL | re.MULTILINE)
IMAGE_RE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
MDLINK_RE = re.compile(r"\[([^\]]+)\]\([^)]*\)")
HTMLTAG_RE = re.compile(r"<[^>\n]+>")
LISTMARK_RE = re.compile(r"^\s{0,3}(?:[-*+]|\d{1,3}[.)])\s+", re.MULTILINE)
HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s*", re.MULTILINE)
QUOTE_RE = re.compile(r"^\s{0,3}>\s?", re.MULTILINE)
HRULE_RE = re.compile(r"^\s{0,3}(?:[-*_]\s*){3,}$", re.MULTILINE)
EMPHASIS_RE = re.compile(r"(\*\*|__|\*|_|`|~~)")
WS_RE = re.compile(r"\s+")


def slugify(text):
    """'Monthly PnL Summary' -> 'monthly-pnl-summary' (also used on filenames)."""
    text = unicodedata.normalize("NFKD", str(text))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^\w\s-]", " ", text.lower(), flags=re.UNICODE)
    text = re.sub(r"[\s_-]+", "-", text.strip())
    return text.strip("-")


def slug_words(slug):
    return [w for w in slug.split("-") if w]


def label_from_filename(stem):
    """'monthly-pnl-summary' -> 'Monthly PnL Summary'."""
    words = slug_words(slugify(stem)) or [stem]
    out = []
    for i, w in enumerate(words):
        if w in ACRONYMS:
            out.append(ACRONYMS[w])
        elif i > 0 and w in LOWERCASE_WORDS:
            out.append(w)
        else:
            out.append(w[:1].upper() + w[1:])
    return " ".join(out)


def wikilink_targets(raw_text):
    """Raw [[Target|alias]] / [[Target#heading]] -> normalised target slugs."""
    targets = []
    for hit in WIKILINK_RE.findall(raw_text):
        target = hit.split("|", 1)[0].split("#", 1)[0].strip()
        if not target:
            continue
        target = target.rsplit("/", 1)[-1]
        if target.lower().endswith(".md"):
            target = target[:-3]
        slug = slugify(target)
        if slug:
            targets.append(slug)
    return targets


def clean_for_excerpt(raw_text, label):
    """Markdown -> readable prose, so the side panel shows sentences not syntax."""
    text = FRONTMATTER_RE.sub("", raw_text)
    text = CODEFENCE_RE.sub(" ", text)
    text = IMAGE_RE.sub(" ", text)
    text = MDLINK_RE.sub(r"\1", text)
    text = WIKILINK_RE.sub(
        lambda m: m.group(1).split("|")[-1].split("#")[0].strip(), text)
    text = HTMLTAG_RE.sub(" ", text)
    text = HRULE_RE.sub(" ", text)
    text = QUOTE_RE.sub("", text)

    # Drop a leading H1 that just repeats the title - the panel shows it already.
    lines = text.lstrip().split("\n")
    if lines and lines[0].startswith("#"):
        first = HEADING_RE.sub("", lines[0]).strip()
        if slugify(first) == slugify(label):
            lines = lines[1:]
    text = "\n".join(lines)

    text = HEADING_RE.sub("", text)
    text = LISTMARK_RE.sub("", text)
    text = EMPHASIS_RE.sub("", text)
    return WS_RE.sub(" ", text).strip()


def make_excerpt(prose, limit=EXCERPT_CHARS):
    if len(prose) <= limit:
        return prose
    cut = prose[:limit]
    space = cut.rfind(" ")
    if space > limit * 0.6:
        cut = cut[:space]
    return cut.rstrip(" ,;:.-") + "…"


def mention_pattern(slug):
    """Regex matching a title in prose, tolerant of separators and case."""
    words = slug_words(slug)
    if not words:
        return None
    if len(words) < MIN_MENTION_SLUG_WORDS and len(words[0]) < MIN_MENTION_WORD_LEN:
        return None
    body = r"[\s\-_/]+".join(re.escape(w) for w in words)
    return re.compile(r"(?<![\w])" + body + r"(?![\w])", re.IGNORECASE)


def read_text(path):
    with open(path, "rb") as fh:
        data = fh.read()
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", "replace")


def find_markdown(root):
    found = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(
            d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")
        )
        for name in sorted(filenames):
            if name.lower().endswith((".md", ".markdown")):
                found.append(os.path.join(dirpath, name))
    return found


FLAGS = ("--no-vectors", "--vectors-only", "--force-vectors")


def pick_notes_root(project_root, argv):
    # Positional arguments only: the flags are not directories, and a path argument is
    # still the first thing after the program name for every caller that had one.
    argv = [a for a in argv if a not in FLAGS]
    if len(argv) > 1:
        given = os.path.abspath(argv[1])
        if not os.path.isdir(given):
            sys.exit("build.py: not a directory: %s" % given)
        return given
    default = os.path.join(project_root, "notes")
    if os.path.isdir(default):
        return default
    return project_root


# ------------------------------------------------------------------------ build

def build_nodes(notes_root, project_root):
    nodes = []
    for path in find_markdown(notes_root):
        stem = os.path.splitext(os.path.basename(path))[0]
        label = label_from_filename(stem)
        raw = read_text(path)
        prose = clean_for_excerpt(raw, label)

        parent = os.path.basename(os.path.dirname(os.path.abspath(path)))
        if os.path.abspath(os.path.dirname(path)) == os.path.abspath(notes_root):
            parent = "unfiled"

        rel = os.path.relpath(path, project_root).replace("\\", "/")
        nodes.append({
            "id": len(nodes),                      # == index in nodes, by contract
            "label": label,
            "group": parent,
            "file": rel,
            "slug": slugify(stem),
            "excerpt": make_excerpt(prose),
            "chars": len(prose),
            "words": len(prose.split()),
            "raw": raw,                            # stripped before graph-data.js
            "prose": prose,                        # stripped before graph-data.js
        })
    return nodes


def build_links(nodes):
    """
    Three signals, strongest wins:
      wikilink  - A contains [[B]]
      mention   - A's prose contains B's title
      shared    - A and B both point at >= SHARED_WIKILINK_MIN of the same targets
    """
    by_slug = {}
    for node in nodes:
        by_slug.setdefault(node["slug"], node["id"])

    patterns = [(n["id"], mention_pattern(n["slug"])) for n in nodes]
    out_targets = []
    unresolved = {}
    pairs = {}   # (lo, hi) -> {"kinds": set(), "weight": int}

    def add(a, b, kind, weight=1):
        if a == b:
            return
        key = (min(a, b), max(a, b))
        entry = pairs.setdefault(key, {"kinds": set(), "weight": 0})
        entry["kinds"].add(kind)
        entry["weight"] += weight

    for node in nodes:
        targets = wikilink_targets(node["raw"])
        resolved = set()
        for slug in targets:
            tid = by_slug.get(slug)
            if tid is None:
                unresolved[slug] = unresolved.get(slug, 0) + 1
                continue
            if tid != node["id"]:
                resolved.add(tid)
                add(node["id"], tid, "wikilink")
        out_targets.append(resolved)

        for other_id, pattern in patterns:
            if other_id == node["id"] or pattern is None:
                continue
            if pattern.search(node["prose"]):
                add(node["id"], other_id, "mention")

    for i in range(len(nodes)):
        for j in range(i + 1, len(nodes)):
            shared = out_targets[i] & out_targets[j]
            if len(shared) >= SHARED_WIKILINK_MIN:
                add(i, j, "shared", weight=len(shared) // SHARED_WIKILINK_MIN)

    order = {"wikilink": 0, "mention": 1, "shared": 2}
    links = []
    for (a, b), entry in sorted(pairs.items()):
        kind = sorted(entry["kinds"], key=lambda k: order[k])[0]
        links.append({
            "source": a,
            "target": b,
            "kind": kind,
            "weight": entry["weight"],
        })
    return links, unresolved


def js_dump(obj):
    return json.dumps(obj, ensure_ascii=False, indent=1, sort_keys=False)


def write_outputs(project_root, notes_root, nodes, links, unresolved):
    degree = {n["id"]: 0 for n in nodes}
    for link in links:
        degree[link["source"]] += 1
        degree[link["target"]] += 1

    groups = []
    for node in nodes:
        if node["group"] not in groups:
            groups.append(node["group"])
    groups.sort()

    graph_nodes = []
    index_notes = []
    for node in nodes:
        graph_nodes.append({
            "id": node["id"],
            "label": node["label"],
            "group": node["group"],
            "file": node["file"],
            "slug": node["slug"],
            "excerpt": node["excerpt"],
            "words": node["words"],
            "degree": degree[node["id"]],
        })
        index_notes.append({
            "id": node["id"],
            "label": node["label"],
            "group": node["group"],
            "file": node["file"],
            "slug": node["slug"],
            "excerpt": node["excerpt"],
            "text": node["prose"],
        })

    generated = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    meta = {
        "generated": generated,
        "notesRoot": os.path.relpath(notes_root, project_root).replace("\\", "/"),
        "noteCount": len(nodes),
        "linkCount": len(links),
        "groups": groups,
        "excerptChars": EXCERPT_CHARS,
    }

    viewer_dir = os.path.join(project_root, "viewer")
    os.makedirs(viewer_dir, exist_ok=True)
    graph_path = os.path.join(viewer_dir, "graph-data.js")
    with open(graph_path, "w", encoding="utf-8") as fh:
        fh.write("// Generated by build.py on %s - do not edit by hand.\n" % generated)
        fh.write("// Every node's id equals its index in GRAPH.nodes.\n")
        fh.write("const GRAPH = {\n")
        fh.write(' "meta": %s,\n' % js_dump(meta))
        fh.write(' "nodes": %s,\n' % js_dump(graph_nodes))
        fh.write(' "links": %s\n' % js_dump(links))
        fh.write("};\n")
        fh.write("if (typeof window !== 'undefined') { window.GRAPH = GRAPH; }\n")

    index_path = os.path.join(project_root, "notes-index.json")
    with open(index_path, "w", encoding="utf-8") as fh:
        json.dump({"meta": meta, "notes": index_notes}, fh,
                  ensure_ascii=False, indent=1)
        fh.write("\n")

    return graph_path, index_path, degree, groups


def build_vectors(project_root, force=False):
    """THE INGESTION ENGINE, run as the second half of a build.

    Kept behind its own try/except and its own import for one reason: the galaxy must
    still build on a machine where chromadb was never installed and Ollama was never
    started. Everything this can go wrong with - a missing package, a stopped model
    server, a locked sqlite file - prints a sentence saying which, and the build that
    has already written graph-data.js still exits zero. A semantic index is an upgrade
    to retrieval, not a new precondition for having a galaxy at all.
    """
    try:
        import ingest
    except Exception as exc:                                   # noqa: BLE001
        print("  vectors    : skipped - could not import ingest.py (%s)" % exc)
        return None
    try:
        summary = ingest.reindex(force=force)
    except ingest.EmbedDown as exc:
        print("  vectors    : skipped - %s" % exc)
        print("               the galaxy is built; retrieval falls back to keywords")
        return None
    except ingest.IngestError as exc:
        print("  vectors    : skipped - %s" % exc)
        return None
    except Exception as exc:                                   # noqa: BLE001
        print("  vectors    : skipped - unexpected %s: %s" % (type(exc).__name__, exc))
        return None
    ingest._print_summary(summary)
    return summary


def main():
    project_root = os.path.dirname(os.path.abspath(__file__))
    notes_root = pick_notes_root(project_root, sys.argv)
    do_vectors = "--no-vectors" not in sys.argv
    vectors_only = "--vectors-only" in sys.argv
    force_vectors = "--force-vectors" in sys.argv

    print("Knowledge Galaxy indexer")
    print("  notes root : %s" % notes_root)

    if vectors_only:
        build_vectors(project_root, force=force_vectors)
        return

    nodes = build_nodes(notes_root, project_root)
    if not nodes:
        sys.exit("build.py: found no .md files under %s" % notes_root)

    links, unresolved = build_links(nodes)
    graph_path, index_path, degree, groups = write_outputs(
        project_root, notes_root, nodes, links, unresolved)

    kinds = {}
    for link in links:
        kinds[link["kind"]] = kinds.get(link["kind"], 0) + 1
    orphans = [n["label"] for n in nodes if degree[n["id"]] == 0]

    print("  notes      : %d" % len(nodes))
    print("  links      : %d (%s)" % (
        len(links), ", ".join("%s %d" % (k, kinds[k]) for k in sorted(kinds)) or "none"))
    print("  groups     : %d (%s)" % (len(groups), ", ".join(groups)))
    if orphans:
        print("  unlinked   : %d (%s)" % (len(orphans), ", ".join(orphans[:6])))
    if unresolved:
        top = sorted(unresolved.items(), key=lambda kv: -kv[1])[:6]
        print("  dangling   : %d wikilink target(s): %s" % (
            len(unresolved), ", ".join("%s x%d" % (k, v) for k, v in top)))
    print("  wrote      : %s" % os.path.relpath(graph_path, project_root))
    print("  wrote      : %s" % os.path.relpath(index_path, project_root))

    # ---- and now the other index, over the other formats, in the other two folders.
    # Last, so that a vector pass that cannot run has already left a complete galaxy
    # behind it, and /remember's in-process rebuild (which calls the functions above
    # directly, not this main) is unaffected either way.
    if do_vectors:
        build_vectors(project_root, force=force_vectors)


if __name__ == "__main__":
    main()
