#!/usr/bin/env python3
"""search.py - a question goes out, at most three snippets come back. Nothing else.

The standard library only: urllib, html.parser, json, re. No SDK, no API key, no pip.
The interface is deliberately one function wide, because everything upstream of it is
about honesty rather than about search:

    search("current population of tokyo") -> [{"title", "url", "snippet", ...}, ...]

and it NEVER raises. A dead network, a captcha, a redesigned results page, a timeout,
a hostile 40 MB response - every one of them returns an empty list, because the caller's
next move is the same in all of those cases: say the web is silent and fall back to the
notes. An exception here would turn a quiet "I could not find out" into a 500.

THE BACKENDS, in the order they are tried, and why there are five of them:

  1. tavily     only if config.json carries search_api_key. The paid door, off by default.
  2. searxng    only if config.json carries search_url. Somebody's own instance.
  3. ddg lite   lite.duckduckgo.com/lite/ by POST. The primary, and no key exists for it.
  4. ddg html   html.duckduckgo.com/html/ by POST. The same index, different markup.
  5. wikipedia  the MediaWiki search API. Always up, real URLs, no key - and useless for
                today's weather, which is exactly why it is last rather than absent.

DuckDuckGo answers a normal question perfectly well and then serves an HTTP 202
challenge page to six requests in ten seconds. That is not a bug to code around, it is a
rate limit to respect: hence the in-memory cache below, the fall-through to the next
backend on a challenge, and Wikipedia at the end so that a throttled minute still
produces something citable rather than a shrug.

WHAT IS REFUSED, and this is the part that matters more than the fetching:

  - a snippet under MIN_SNIPPET_CHARS is not evidence, it is a headline;
  - a snippet that reads like a paywall or a cookie wall describes the wall, not the
    answer, and a model handed one will cheerfully invent what was behind it;
  - a URL that is not http(s), or that is one of the engine's own redirect/ad hops, is
    not a source anybody can check. DuckDuckGo's `//duckduckgo.com/l/?uddg=` wrapper is
    unwrapped back to the real address rather than passed on, because a citation the
    reader cannot click is indistinguishable from one that was made up.

Nothing from this module reaches the browser directly. server.py copies out exactly
`title` and `url` per result; the snippet goes to the model and the trace goes to the
log. The query itself DOES leave the machine when a lookup happens - that is what a web
search is - and that is stated plainly in the README rather than buried here.
"""

import json
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser

# ----------------------------------------------------------------- the dials

WEB_TIMEOUT = 8.0          # per request; a lookup nobody asked twice for can wait 8s
WANT = 3                   # snippets handed to the brain, as specified
MIN_SNIPPET_CHARS = 60     # below this it is a headline, not evidence
MAX_SNIPPET_CHARS = 420    # per snippet, sent to the model
MAX_TITLE_CHARS = 140
MAX_QUERY_CHARS = 240      # a paragraph is not a query; the tail is noise anyway
MAX_BYTES = 900_000        # a results page is ~30 KB. This is the hostile-response cap.
CACHE_TTL_S = 120.0        # the same question twice in two minutes is one request
CACHE_MAX = 32

# A plain browser User-Agent, and not as a disguise: the lite endpoint serves its
# challenge page to an obvious script and its ordinary results to an ordinary client.
# One request per question, no crawling, no parallel fan-out.
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

DDG_LITE = "https://lite.duckduckgo.com/lite/"
DDG_HTML = "https://html.duckduckgo.com/html/"
WIKI_API = "https://en.wikipedia.org/w/api.php"
TAVILY_URL = "https://api.tavily.com/search"

# Phrases that mean "you are looking at the wall, not the article". A snippet holding
# one of these is dropped: the answer is behind it, and a model given the wall will
# reliably invent what it thinks was behind it.
PAYWALL_MARKERS = (
    "subscribe to continue", "subscription required", "subscribers only",
    "to continue reading", "continue reading with", "sign in to read",
    "log in to read", "register to read", "create a free account",
    "create an account to continue", "this content is for members",
    "become a member to", "paywall", "start your free trial",
    "enable javascript", "javascript is disabled", "javascript to continue",
    "accept cookies", "cookie policy", "we use cookies",
    "verify you are human", "are you a robot", "unusual traffic",
    "access denied", "403 forbidden", "page not found",
)

# Hosts that are never a source: the engines' own redirect and advertising hops.
BLOCKED_HOSTS = ("duckduckgo.com", "www.duckduckgo.com", "lite.duckduckgo.com",
                 "html.duckduckgo.com", "google.com", "www.google.com",
                 "bing.com", "www.bing.com", "doubleclick.net", "adservice.google.com")

# What a challenge page looks like from here. Checked because an HTTP 200 carrying a
# captcha is the failure that otherwise reads as "the web has nothing about Tokyo".
CHALLENGE_MARKERS = ("captcha", "anomaly.js", "unusual traffic",
                     "verify you are human", "detected unusual")

_TAG_RE = re.compile(r"<[^>]{0,200}>")
_WS_RE = re.compile(r"\s+")

_cache = {}                       # query -> (stamp, results)
_cache_lock = threading.Lock()


# ------------------------------------------------------------------ plumbing

def _note(trace, line):
    """One line about one attempt. Never a key, never a cookie - see _describe_cfg."""
    if trace is not None:
        trace.append(line)


def _clean(text, limit):
    text = _WS_RE.sub(" ", _TAG_RE.sub(" ", str(text or ""))).strip()
    if len(text) > limit:
        text = text[:limit].rsplit(" ", 1)[0] + "…"
    return text


def _fetch(url, data=None, headers=None, timeout=WEB_TIMEOUT):
    """(status, text) or (0, "") - and it never raises, which is the whole contract."""
    head = {"User-Agent": UA, "Accept": "text/html,application/json;q=0.9",
            "Accept-Language": "en-US,en;q=0.9"}
    head.update(headers or {})
    try:
        req = urllib.request.Request(url, data=data, headers=head)
        with urllib.request.urlopen(req, timeout=timeout) as res:
            raw = res.read(MAX_BYTES)
            status = getattr(res, "status", None) or res.getcode()
        return int(status), raw.decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        try:
            body = exc.read(4096).decode("utf-8", "replace")
        except Exception:                                      # noqa: BLE001
            body = ""
        return int(exc.code), body
    except Exception:                                          # noqa: BLE001
        # Timeout, DNS, TLS, a proxy, a closed socket. All the same answer upstream.
        return 0, ""


def _blocked(text):
    low = text[:4000].lower()
    return any(marker in low for marker in CHALLENGE_MARKERS)


def _unwrap(href):
    """The real address behind an engine's redirect hop, or the address itself.

    DuckDuckGo's html endpoint hands back `//duckduckgo.com/l/?uddg=https%3A%2F%2F...`.
    Passing that on would cite a URL that is not where the words came from, which is a
    fabricated source with extra steps.
    """
    href = (href or "").strip()
    if href.startswith("//"):
        href = "https:" + href
    if "uddg=" in href:
        try:
            query = urllib.parse.urlsplit(href).query
            got = urllib.parse.parse_qs(query).get("uddg") or []
            if got:
                href = urllib.parse.unquote(got[0])
        except Exception:                                      # noqa: BLE001
            return ""
    return href


def _usable(title, url, snippet):
    """(ok, why-not). The why is for the trace, so a thin day can be read back."""
    if not url.startswith(("http://", "https://")):
        return False, "not an http url"
    host = urllib.parse.urlsplit(url).netloc.lower()
    if not host:
        return False, "no host"
    if any(host == bad or host.endswith("." + bad) for bad in BLOCKED_HOSTS):
        return False, "engine or ad host " + host
    if "/y.js" in url or "/aclk" in url or "/aclick" in url:
        return False, "sponsored link"
    if not title:
        return False, "no title"
    if len(snippet) < MIN_SNIPPET_CHARS:
        return False, "snippet too short (%d chars)" % len(snippet)
    low = snippet.lower()
    for marker in PAYWALL_MARKERS:
        if marker in low:
            return False, "looks like a wall: %r" % marker
    return True, ""


def _collect(rows, want, backend, trace):
    """Raw (title, url, snippet) triples -> the results we are willing to cite."""
    out, seen = [], set()
    for title, url, snippet in rows:
        url = _unwrap(url)
        title = _clean(title, MAX_TITLE_CHARS)
        snippet = _clean(snippet, MAX_SNIPPET_CHARS)
        ok, why = _usable(title, url, snippet)
        if not ok:
            _note(trace, "%s: skipped %s - %s" % (backend, url[:60] or "(no url)", why))
            continue
        host = urllib.parse.urlsplit(url).netloc.lower()
        if host in seen:
            _note(trace, "%s: skipped %s - second hit from the same site" % (backend, host))
            continue
        seen.add(host)
        out.append({"title": title, "url": url, "snippet": snippet,
                    "host": host, "backend": backend})
        if len(out) >= want:
            break
    return out


# ------------------------------------------------------- the duckduckgo parser

class _DDGParser(HTMLParser):
    """Both DuckDuckGo layouts in one pass, by class name rather than by structure.

    lite/  : <a class='result-link' href=...>title</a>  +  <td class='result-snippet'>
    html/  : <a class="result__a" href=...>title</a>    +  <a class="result__snippet">

    Written as a tiny state machine on purpose. A regex over a results page works until
    the day an attribute order changes, and then it fails silently - which here would
    look exactly like "the web knows nothing about that".
    """

    TITLE_CLASSES = ("result-link", "result__a")
    SNIPPET_CLASSES = ("result-snippet", "result__snippet")

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows = []              # [title, url, snippet]
        self._want = None           # "title" | "snippet" | None
        self._depth = 0

    def _classes(self, attrs):
        return (dict(attrs).get("class") or "").lower().split()

    def handle_starttag(self, tag, attrs):
        classes = self._classes(attrs)
        if tag == "a" and any(c in classes for c in self.TITLE_CLASSES):
            self.rows.append(["", dict(attrs).get("href") or "", ""])
            self._want, self._depth = "title", 1
            return
        if any(c in classes for c in self.SNIPPET_CLASSES) and self.rows:
            self._want, self._depth = "snippet", 1
            return
        if self._want:
            self._depth += 1       # <b> around a matched word, mostly

    def handle_endtag(self, tag):
        if not self._want:
            return
        self._depth -= 1
        if self._depth <= 0:
            self._want = None

    def handle_data(self, data):
        if not self._want or not self.rows:
            return
        if self._want == "title":
            self.rows[-1][0] += data
        else:
            self.rows[-1][2] += data


def _ddg(endpoint, query, want, trace, label):
    body = urllib.parse.urlencode({"q": query, "kl": "wt-wt"}).encode("utf-8")
    status, text = _fetch(endpoint, data=body,
                          headers={"Content-Type": "application/x-www-form-urlencoded",
                                   "Referer": endpoint, "Origin": endpoint.rsplit("/", 2)[0]})
    if status != 200 or not text:
        _note(trace, "%s: HTTP %s, nothing to read" % (label, status))
        return []
    if _blocked(text):
        _note(trace, "%s: HTTP 200 with a challenge page, not results - rate limited"
              % label)
        return []
    parser = _DDGParser()
    try:
        parser.feed(text)
    except Exception:                                          # noqa: BLE001
        _note(trace, "%s: the results page did not parse" % label)
        return []
    if not parser.rows:
        _note(trace, "%s: parsed clean and found no result rows" % label)
        return []
    _note(trace, "%s: %d raw rows" % (label, len(parser.rows)))
    return _collect(parser.rows, want, label, trace)


# ------------------------------------------------------------ wikipedia, last

def _wikipedia(query, want, trace):
    """The floor under everything else: free, keyless, and always answering.

    It cannot tell you today's price of anything, and it is not being asked to. It is
    here so that a throttled minute still ends in a citable sentence rather than in a
    shrug, and the caller can see which backend answered.
    """
    url = WIKI_API + "?" + urllib.parse.urlencode({
        "action": "query", "format": "json", "list": "search",
        "srsearch": query, "srlimit": max(want * 2, 6), "srprop": "snippet",
        "utf8": "1",
    })
    status, text = _fetch(url, headers={"Accept": "application/json"})
    if status != 200 or not text:
        _note(trace, "wikipedia: HTTP %s" % status)
        return []
    try:
        hits = (json.loads(text).get("query") or {}).get("search") or []
    except Exception:                                          # noqa: BLE001
        _note(trace, "wikipedia: the reply was not the JSON it promises")
        return []
    rows = []
    for hit in hits:
        title = str(hit.get("title") or "")
        if not title:
            continue
        rows.append((title + " - Wikipedia",
                     "https://en.wikipedia.org/wiki/" +
                     urllib.parse.quote(title.replace(" ", "_")),
                     str(hit.get("snippet") or "")))
    _note(trace, "wikipedia: %d raw rows" % len(rows))
    # Every article is on one host, so the one-hit-per-site rule in _collect would keep
    # a single row. That rule is about not citing one site three times as three
    # sources; three Wikipedia articles ARE three sources, so they are collected
    # without it - and they still face the length and wall filters.
    out = []
    for title, url_, snippet in rows:
        title = _clean(title, MAX_TITLE_CHARS)
        snippet = _clean(snippet, MAX_SNIPPET_CHARS)
        ok, why = _usable(title, url_, snippet)
        if not ok:
            _note(trace, "wikipedia: skipped %s - %s" % (title[:40], why))
            continue
        out.append({"title": title, "url": url_, "snippet": snippet,
                    "host": "en.wikipedia.org", "backend": "wikipedia"})
        if len(out) >= want:
            break
    return out


# ------------------------------------------------- the two configured backends

def _searxng(base, query, want, trace):
    """Somebody's own SearXNG. JSON in one request, and no key involved."""
    url = base.rstrip("/") + "/search?" + urllib.parse.urlencode(
        {"q": query, "format": "json", "safesearch": "0"})
    status, text = _fetch(url, headers={"Accept": "application/json"})
    if status != 200 or not text:
        _note(trace, "searxng: HTTP %s" % status)
        return []
    try:
        results = json.loads(text).get("results") or []
    except Exception:                                          # noqa: BLE001
        _note(trace, "searxng: answered %d bytes that were not JSON (a login wall, "
                     "usually)" % len(text))
        return []
    rows = [(r.get("title"), r.get("url"), r.get("content")) for r in results
            if isinstance(r, dict)]
    _note(trace, "searxng: %d raw rows" % len(rows))
    return _collect(rows, want, "searxng", trace)


def _tavily(key, query, want, trace):
    """The paid door, used only if a key is sitting in config.json.

    The key is read here and nowhere else, it is never logged, and nothing about it
    but its length ever reaches a trace line.
    """
    body = json.dumps({"api_key": key, "query": query, "max_results": max(want * 2, 5),
                       "search_depth": "basic"}).encode("utf-8")
    status, text = _fetch(TAVILY_URL, data=body,
                          headers={"Content-Type": "application/json",
                                   "Accept": "application/json"})
    if status != 200 or not text:
        _note(trace, "tavily: HTTP %s (key %d chars)" % (status, len(key)))
        return []
    try:
        results = json.loads(text).get("results") or []
    except Exception:                                          # noqa: BLE001
        _note(trace, "tavily: the reply was not JSON")
        return []
    rows = [(r.get("title"), r.get("url"), r.get("content")) for r in results
            if isinstance(r, dict)]
    _note(trace, "tavily: %d raw rows" % len(rows))
    return _collect(rows, want, "tavily", trace)


# ----------------------------------------------------------------- the door

def backends(cfg=None):
    """[(name, callable)] in the order they will be tried, for this config.

    Exposed rather than private so that preflight can say out loud which doors exist
    on this machine, and so a reader can see that the keyed ones are absent by default.
    """
    cfg = cfg or {}
    key = str(cfg.get("search_api_key") or "").strip()
    base = str(cfg.get("search_url") or "").strip()
    chain = []
    if key and key.lower() not in ("", "put-your-key-here", "your-key-here", "changeme"):
        chain.append(("tavily", lambda q, w, t: _tavily(key, q, w, t)))
    if base.startswith(("http://", "https://")):
        chain.append(("searxng", lambda q, w, t: _searxng(base, q, w, t)))
    chain.append(("ddg-lite", lambda q, w, t: _ddg(DDG_LITE, q, w, t, "ddg-lite")))
    chain.append(("ddg-html", lambda q, w, t: _ddg(DDG_HTML, q, w, t, "ddg-html")))
    chain.append(("wikipedia", lambda q, w, t: _wikipedia(q, w, t)))
    return chain


def search(query, want=WANT, cfg=None, trace=None, use_cache=True):
    """Query in, at most `want` snippets out. Empty list on any kind of failure.

    Each dict is {"title", "url", "snippet", "host", "backend"}. The caller decides
    what the browser may see - server.py copies out title and url and nothing else.
    """
    query = _WS_RE.sub(" ", str(query or "")).strip()[:MAX_QUERY_CHARS]
    if len(query) < 2:
        _note(trace, "nothing to search for")
        return []

    key = query.lower()
    now = time.monotonic()
    if use_cache:
        with _cache_lock:
            hit = _cache.get(key)
            if hit and (now - hit[0]) < CACHE_TTL_S:
                _note(trace, "cache: the same question %ds ago, %d results reused - "
                             "asking again would earn a rate limit, not fresher facts"
                      % (now - hit[0], len(hit[1])))
                return [dict(r) for r in hit[1]]

    results = []
    for name, fn in backends(cfg):
        try:
            results = fn(query, want, trace)
        except Exception as exc:                               # noqa: BLE001
            # A backend that throws is a backend that failed. Never the caller's problem.
            _note(trace, "%s: raised %s, moving on" % (name, type(exc).__name__))
            results = []
        if results:
            _note(trace, "%s answered with %d usable result%s"
                  % (name, len(results), "" if len(results) == 1 else "s"))
            break

    if use_cache and results:
        with _cache_lock:
            _cache[key] = (now, [dict(r) for r in results])
            if len(_cache) > CACHE_MAX:
                for stale in sorted(_cache, key=lambda k: _cache[k][0])[:len(_cache) // 2]:
                    _cache.pop(stale, None)
    if not results:
        _note(trace, "every backend came back empty: the web is silent")
    return results


def forget():
    """Drop the cache. For tests and for a preflight that wants a real request."""
    with _cache_lock:
        _cache.clear()


if __name__ == "__main__":                                     # pragma: no cover
    import sys
    asked = " ".join(sys.argv[1:]) or "current population of tokyo"
    log = []
    found = search(asked, trace=log)
    for line in log:
        print("  ·", line)
    print()
    for i, r in enumerate(found, 1):
        print("%d. %s\n   %s\n   %s\n" % (i, r["title"], r["url"], r["snippet"][:160]))
    if not found:
        print("nothing usable came back")
