#!/usr/bin/env python3
"""operator_browser.py - Operator: open a site in a new tab and, given something to look
for, search it, open the first match and start it playing - on ANY site, by the generic
primitives in operator_core.

    echo {"site": "youtube", "query": "kesariya arijit singh"} | python tools/operator_browser.py
    Opened YouTube and started playing kesariya arijit singh - the first result, 'Kesariya - Brahmastra'.

THE CONTRACT, as tools/selftest.py states it:

  in    {"site": "<a name, a domain or an http(s) URL>", "query": "..."} on stdin, UTF-8.
        query is optional; without it the site is only opened.
  out   ONE line of plain ASCII on stdout, and stdout is the ONLY evidence.
  exit  0 means the thing the line names happened and was SEEN to happen. 1 means it did
        not, and the line says why and where it stopped.

PHASE 1.3: ONE RECIPE, NOT THREE HANDS. Phase 1.1 wrote play_youtube() and play_hotstar()
as two bespoke flows. Each was really the same five generic steps, and now IS them:

    open the site            navigate()
    find its search          find_target("the search box"); if there is none, press the
                             control named "search" and look again (a search that lives
                             behind a button or a link, as Hotstar's does)
    type the query, send it  act_type() + act_submit() - Enter, read back as a moved page
    open the first match     the first result in reading order whose name is a confident
                             match for the query (find_target, ordinal 1)
    start it                 wait_playing(); if it sits still, press the page's own
                             play / watch control, found by name, and watch again

WHAT A SITE LAYER MAY HOLD, AND NOTHING ELSE. What is irreducibly site-specific is data,
not code: where the site's home is, which regions are adverts or Shorts rather than
results, which links count as a result, how the site marks an advert, and whether its
previews play muted. SITES below is the whole of it. Everything that FINDS or PRESSES
anything is operator_core's, and knows no site.

  YOUTUBE   folded cleanly. The layer: home, the advert/Shorts/masthead regions to pass
            over, "/watch?v=" as what a result links to (and "list=" as what it does not -
            a Mix is a playlist, not the song), and ".ad-showing" as the advert marker.
            Phase 1.1 typed the query into a hand-built results URL; this uses the site's
            own search box like a person, which costs one page load and buys not knowing
            YouTube's URL scheme.
  HOTSTAR   folded, with a thin layer. Its search lives behind a "Search" link (found by
            name, as any site's would be) and its result tiles are pictures named by alt
            text (which the finder reads). The layer holds what the DOM cannot say: its
            previews and trailers play MUTED and a playing video of 30 s or less is
            probably an advert (no marker exists - measured 2026-10-14), and its home is
            /in. BEST-EFFORT, as in 1.1: a React SPA behind a login and a subscription.
  ANY OTHER the same recipe with an empty layer: search it, open the first confident match,
  SITE      and start it if there is a video. Without a query, opened and nothing more, and
            the line says "I only opened it" in so many words.

THE PANIC KEY, the new tab, the budget and the one-line contract are 1.1's, now shared
from operator_core.
"""
import json
import re
import sys
import time
import urllib.parse

try:
    from tools import operator_core as core          # imported by hands.py for describe()
except ImportError:                                  # run as a hand, from tools/
    import operator_core as core

WHO = "operator_browser"
# The registry kills this hand at timeout_s (60). Finishing inside 52 means a slow site is
# reported in this file's words, as the step it was on, never as a bare timeout.
BUDGET_S = 52.0
PLAY_TIMEOUT_S = 15.0
SEARCH_WAIT_S = 20.0
OPENER_GRACE_S = 4.0

# =============================================================================
#  THE SITE LAYERS - data only; see the docstring for what may live here
# =============================================================================

SITES = {
    "youtube": {
        "name": "YouTube",
        "home": "https://www.youtube.com/",
        "aliases": ("youtube", "youtube.com", "www.youtube.com", "m.youtube.com", "yt",
                    "you tube"),
        # Not results: adverts, Shorts shelves, the masthead, and the lockup YouTube draws a
        # Mix (a playlist) in (measured 2026-10-14). The Mix is passed over by REGION, not
        # by its "list=" link: the same day, in a profile that had played the song, the
        # ordinary first result's own title link carried "&list=RD..." too, and a "list="
        # rule excluded every real result.
        "skip": ("ytd-ad-slot-renderer, ytd-promoted-video-renderer, ytd-in-feed-ad-layout-"
                 "renderer, ytd-reel-shelf-renderer, ytd-shorts, [is-shorts], ytd-masthead, "
                 "#masthead-ad, ytd-display-ad-renderer, ytd-rich-shelf-renderer[is-shorts], "
                 "yt-lockup-view-model, ytd-radio-renderer, ytd-playlist-renderer"),
        "result_href": "/watch?v=",
        "result_not": "",
        "ad_marker": ".ad-showing, .ad-interrupting",
        "need_sound": False,
        "short_is_ad": False,
        "title_tail": " - YouTube",
        "verb": "started playing",
    },
    "hotstar": {
        # Measured from this machine on 2026-10-14: hotstar.com and jiohotstar.com both end
        # at /in, in one and two redirects.
        "name": "Hotstar",
        "home": "https://www.hotstar.com/in",
        "aliases": ("hotstar", "hotstar.com", "www.hotstar.com", "jiohotstar",
                    "jiohotstar.com", "www.jiohotstar.com", "jio hotstar", "hot star",
                    "disney+ hotstar", "disney hotstar", "disney plus hotstar"),
        "skip": "",
        "result_href": "",
        "result_not": "",
        "ad_marker": "",
        "need_sound": True,       # tile previews and title-page trailers play MUTED
        "short_is_ad": True,      # no advert marker in the DOM; a <=30 s clip is the tell
        "title_tail": "",
        "verb": "started",
        "best_effort": True,
    },
}

# What a page's own "start it" control is called, most specific first. Generic, not any
# one site's: these are the words streaming and video pages use for the same button.
# Measured 1.4: a series page offered "Watch Latest Season S3 E1" beside a "WATCH AGAIN"
# control, and bare "watch" preferred the shorter one - so the season forms come first.
PLAY_WORDS = ("watch live", "watch latest episode", "watch latest season", "watch latest",
              "watch first episode", "watch first season", "watch now", "play now",
              "continue watching", "resume", "watch", "play")
NOT_PLAY = ("watchlist", "trailer", "add to")
# NEVER PRESSED, WHATEVER ELSE THEY SAY (Operator 1.4). Measured logged out on Hotstar: the
# only "watch" control was "Subscribe to watch", the play step pressed it, and the run
# landed on the site's paywall. A purchase or a sign-in is the employer's to start, like
# Run and Submit on a code page; when one of these is all there is, it IS the wall, and
# the line says so instead.
GATES = ("subscribe", "upgrade", "buy", "rent", "purchase", "sign in", "sign up", "log in",
         "login", "get plan", "choose plan", "join now")

NO_PORT = core.NO_PORT


# =============================================================================
#  WHAT WILL BE DONE - shared by the run and by hands.py's proposal
# =============================================================================

def resolve(site, query=""):
    """(kind, url, plan, layer) for what the hand WILL do - used by the run and, through
    describe(), by hands.py's proposal, so the sentence the employer approves and the
    thing that happens are computed by the same code. kind is a SITES key, "search" (any
    other site, with a query), "open" (no query), or "" when the site cannot be opened at
    all, in which case plan is the reason."""
    raw = " ".join(str(site or "").split())
    q = " ".join(str(query or "").split())
    key = raw.lower().rstrip("/")
    for name in ("https://", "http://"):
        if key.startswith(name) and urllib.parse.urlsplit(key).path in ("", "/"):
            key = key[len(name):]
    key = key.rstrip("/")
    for kind, layer in SITES.items():
        if key in layer["aliases"]:
            if not q:
                return kind, layer["home"], "do nothing more - there is nothing to search for", layer
            plan = ("try to start the first match for '%s'" % q if layer.get("best_effort")
                    else "play the first result for '%s'" % q)
            return kind, layer["home"], plan, layer
    if not raw:
        return "", "", "there was no site to open", None
    # A scheme with no "//" - javascript:, data:, file:, chrome: - is not a bare domain with
    # https:// missing; it is something that must not be opened at all.
    scheme = raw.split(":", 1)[0].lower() if ":" in raw else ""
    if "://" not in raw and scheme and not raw.split(":", 1)[1].split("/", 1)[0].isdigit():
        return "", "", "I only open web pages, and '%s' is not one" % raw, None
    # https by default; plain http for this machine's own servers, which have no TLS.
    loopback = raw.lower().split(":", 1)[0].split("/", 1)[0] in ("localhost", "127.0.0.1")
    url = raw if "://" in raw else ("http://" if loopback else "https://") + raw
    parts = urllib.parse.urlsplit(url)
    host = (parts.hostname or "").lower()
    try:
        parts.port
    except ValueError:
        return "", "", "'%s' is not a web address I can open" % raw, None
    if parts.scheme not in ("http", "https"):
        return "", "", "I only open web pages, and '%s' is not one" % raw, None
    if not host or " " in raw or not all(c.isalnum() or c in ".-" for c in host):
        return "", "", "'%s' is not a web address I can open" % raw, None
    if "." not in host and host != "localhost":
        host += ".com"
        url = urllib.parse.urlunsplit((parts.scheme, host + (":%d" % parts.port
                                                             if parts.port else ""),
                                       parts.path, parts.query, parts.fragment))
    if q:
        return ("search", url, "search it for '%s', open the first match, and start it if "
                "it is a video" % q, {"name": host})
    return "open", url, "do nothing more on it - no search, no clicks", None


# THE SENTENCE (Operator 1.4). Measured live, 2026-10-14: "play bigg boss on hotstar" went
# to the hands-offer model, which declined the tag on both asks ("looked like an
# instruction and was not one"), and the turn became a web search about where Bigg Boss
# streams. 1.2 met the same failure for "type it in" and answered it with a protected route;
# this is that route's grammar for this hand. The SITE must be one this file already knows
# (a SITES alias) or a real domain with a dot - a bare word like "spotify" is left to the
# model, so nothing here names a new site.
_SITE = r"(?P<site>(?:www\.)?[a-z0-9-]+(?:\.[a-z0-9-]+)+(?:/\S*)?|%s)" % "|".join(
    re.escape(a) for layer in SITES.values() for a in sorted(layer["aliases"], key=len,
                                                               reverse=True))
_BROWSE_RULES = (
    re.compile(r"^(?:please\s+)?(?:can\s+you\s+)?(?:play|put\s+on|stream|watch|start)\s+"
               r"(?P<query>.+?)\s+(?:on|from)\s+" + _SITE + r"$", re.I),
    re.compile(r"^(?:please\s+)?(?:can\s+you\s+)?(?:open|go\s+to|launch)\s+" + _SITE +
               r"\s+and\s+(?:play|search(?:\s+for)?|watch|look\s+(?:up|for)|find)\s+"
               r"(?P<query>.+)$", re.I),
    re.compile(r"^(?:please\s+)?(?:can\s+you\s+)?(?:search|look\s+up|find)\s+(?:for\s+)?"
               r"(?P<query>.+?)\s+on\s+" + _SITE + r"$", re.I),
)


def parse_request(sentence):
    """{"site", "query"} for an explicit ask to open a known site (or a domain) and play or
    search something on it, or None. Pure."""
    s = " ".join(str(sentence or "").split()).strip().rstrip(".!?")
    if not s or len(s) > 200:
        return None
    for rx in _BROWSE_RULES:
        m = rx.match(s)
        if m:
            query = m.group("query").strip(" ,'\"")
            site = m.group("site").strip()
            if query and resolve(site, query)[0]:
                return {"site": site, "query": query}
    return None


def describe(site, query=""):
    """(where, plan) for hands.py's proposal blanks {where} and {plan}, or None when the
    site cannot be opened (the blanks then stand, visibly, and the run refuses)."""
    kind, url, plan, layer = resolve(site, query)
    if not kind:
        return None
    where = (layer or {}).get("name") or urllib.parse.urlsplit(url).hostname or url
    return where, plan


# =============================================================================
#  THE RECIPE - generic steps; a layer only tunes them
# =============================================================================

def search_site(run, tab, query, name):
    """Find the site's search box - or the control that opens one - type the query and
    send it. Returns how it was sent."""
    run.at("looking for %s's search box" % name)
    # The box, or the control that opens one, whichever the page draws: watched for TOGETHER
    # in one loop, because on a slow line a page paints late, and looking for the box for
    # twenty seconds and only then for the opener spent the run's budget on the wrong half
    # (measured on Hotstar, whose search lives behind a link). The box wins whenever both
    # are there - YouTube draws a Search button right beside its box - and the opener is
    # only taken once it has stood alone for OPENER_GRACE_S.
    end = time.monotonic() + SEARCH_WAIT_S
    opener, opener_since = None, None
    while True:
        run.check()
        box = core.find_target(tab, "the search box")
        if box["ok"]:
            break
        opener = core.find_target(tab, "the search button", role="button")
        if opener["ok"]:
            opener_since = opener_since or time.monotonic()
            if time.monotonic() - opener_since >= OPENER_GRACE_S:
                break
        else:
            opener_since = None
        if time.monotonic() >= end:
            break
        run.nap(0.4)
    if not box["ok"]:
        # A search that lives behind a button or link: press it, then the box appears.
        if not (opener and opener["ok"]):
            raise core.Failed(core.miss_line(box, "a search box", verb="search %s" % name))
        run.at("opening %s's search" % name)
        core.act_click(run, tab, opener)
        box = core.wait_target(run, tab, "the search box", timeout=10.0)
        href = str(opener["pick"].get("href") or "")
        if not box["ok"] and opener["pick"].get("role") in ("link", "tab") and href and \
                not href.startswith(("#", "javascript:")):
            # A LINK THAT TOOK THE CLICK AND WENT NOWHERE is followed by its address.
            # Measured on Hotstar, 2026-10-14, on a slow line: a trusted click reached the
            # Search link (href /in/explore) and the page stayed on /in/home - the app's
            # router was not ready for it. Loading the address a link names is what a
            # person does next, and unlike a second click on a toggle it cannot undo
            # anything.
            target = urllib.parse.urljoin(tab.evaluate("location.href", timeout=5.0) or "",
                                          href)
            core.note(WHO, "the search link took the click and stayed put; following %s"
                      % target)
            core.navigate(run, tab, target, "opening %s's search page" % name)
            box = core.wait_target(run, tab, "the search box", timeout=15.0)
        if not box["ok"]:
            raise core.Failed("I pressed %s's Search, but no search box I am sure of "
                              "appeared" % name)
    core.note(WHO, "search box %r (%.2f via %s)" % (box["pick"]["name"], box["pick"]["conf"],
                                                   box["pick"]["src"]))
    run.at("typing '%s' into %s's search" % (query, name))
    core.act_type(run, tab, box, query)
    run.at("searching %s for '%s'" % (name, query))
    sent = core.act_submit(run, tab, box)
    core.note(WHO, "search sent by %s: %s" % (sent["path"], core.effect_words(sent["effects"])))
    return sent


def open_first_match(run, tab, query, layer, name):
    """Click the first result, in reading order, whose name is a confident match for the
    query. The layer narrows WHERE results are (skip, href); the matching is generic."""
    run.at("looking for '%s' in %s's results" % (query, name))
    how = dict(role="result", ordinal=1, words=query.lower().split(), outside_chrome=True,
               skip=layer.get("skip") or None, href_has=layer.get("result_href") or None,
               href_not=layer.get("result_not") or None)
    found = core.wait_target(run, tab, "the first result", timeout=20.0, **how)
    if not found["ok"] and layer.get("result_href"):
        # The layer says what a result LINKS to, so "the first result" can be taken by
        # structure when no title carries the query's words - YouTube's search is fuzzy
        # and titles are often translated (measured: "tum hi ho" under a Hindi title).
        how["words"] = []
        found = core.find_target(tab, "the first result", **how)
    if not found["ok"]:
        raise core.Failed(core.miss_line(found, "a result for '%s'" % query,
                                         verb="open anything on %s" % name))
    label = core.label_of(found["pick"])
    core.note(WHO, "first match %r (%.2f) of %d ranked" % (found["pick"]["name"],
                                                           found["pick"]["conf"],
                                                           len(found["ranked"])))
    run.at("opening '%s'" % label)
    results_url = tab.evaluate("location.href", timeout=5.0) or ""
    res = core.act_click(run, tab, found)
    fx = res["effects"]
    if not (fx.get("navigated") or fx.get("href")):
        # An SPA may move a beat after the witness stopped looking.
        if not core.wait_for(run, tab, "location.href !== %s" % json.dumps(results_url),
                             timeout=6.0):
            raise core.Failed("I clicked '%s' but the page did not move on" % label)
    return label, found


def start_playback(run, tab, layer, label):
    """(playing, ad, muted). Watch the page's video; if it sits still, press the page's own
    play / watch control by name and watch again."""
    flags = dict(need_sound=bool(layer.get("need_sound")),
                 short_is_ad=bool(layer.get("short_is_ad")),
                 ad_marker=layer.get("ad_marker") or "")
    run.at("waiting for '%s' to start" % label)
    has_video = core.wait_for(run, tab, "!!document.querySelector('video')", timeout=6.0)
    if has_video:
        playing, ad, muted = core.wait_playing(run, tab, timeout=5.0 if flags["need_sound"]
                                               else PLAY_TIMEOUT_S, **flags)
        if playing:
            return playing, ad, muted
    else:
        muted = False
    for word in PLAY_WORDS:
        btn = core.find_target(tab, "the %s button" % word, role="button",
                               exact=word, skip="header, nav")
        said_on_it = core.norm_name(btn["pick"]["name"]) if btn.get("pick") else ""
        if btn["ok"] and any(g in said_on_it for g in GATES):
            core.note(WHO, "the play control is a gate (%r); not pressed" % said_on_it[:60])
            raise core.Failed("I found %s, but the only way to play it is '%s' - that is "
                              "a sign-in or a subscription, and it is yours to start, sir. "
                              "The page is open for you" % (
                                  core.ascii_words(page_title(tab, layer), 60) or label,
                                  core.ascii_words(said_on_it, 40)))
        if btn["ok"] and not any(n in said_on_it for n in NOT_PLAY):
            run.at("pressing '%s' on '%s'" % (core.label_of(btn["pick"]), label))
            core.act_click(run, tab, btn)
            break
    run.at("waiting for '%s' to start" % label)
    if not core.wait_for(run, tab, "!!document.querySelector('video')", timeout=8.0):
        return False, False, muted
    playing, ad, more_muted = core.wait_playing(run, tab, timeout=PLAY_TIMEOUT_S, **flags)
    return playing, ad, muted or more_muted


# WHAT STOOD IN THE WAY, read only after playback failed. Generic phrasing, not any site's:
# a visible DIALOG is read first (a wall is usually a modal over the page), then the page.
# 'login' also covers the OTP step - a visible phone-number or one-time-code input is a
# sign-in wall whatever it says around it.
_WALL_JS = r"""
(function () {
  var shown = function (e) { var r = e.getBoundingClientRect(); return r.width > 2 && r.height > 2 &&
    (!e.checkVisibility || e.checkVisibility({visibilityProperty: true})); };
  var dlg = Array.prototype.slice.call(document.querySelectorAll('[role=dialog], [aria-modal=true], dialog[open]')).filter(shown);
  var t = (dlg.length ? dlg.map(function (d) { return d.innerText; }).join(' ')
                      : (document.body && document.body.innerText || '')).toLowerCase().replace(/\s+/g, ' ');
  var otp = Array.prototype.slice.call(document.querySelectorAll(
    'input[type=tel], input[autocomplete=one-time-code], input[name*=otp i], input[placeholder*=mobile i], input[placeholder*=phone i]')).filter(shown);
  if (otp.length || /(log ?in|sign ?in)\b.{0,40}\b(to )?(watch|continue|proceed|enjoy|stream)|enter (your )?(mobile|phone) number|enter (the )?otp|verify (your )?(mobile|number|phone)/.test(t))
    return 'login';
  if (/(subscribe|upgrade)\b.{0,40}\b(to )?(watch|continue|premium|plan)|choose (a |your )?plan|buy (a )?plan|available (only )?(on|with) premium|premium (plan|members|subscribers)/.test(t))
    return 'subscription';
  return '';
})()
"""


def page_title(tab, layer):
    """The watch page's own title, without the site's wrapper around it. Generic: a
    leading "Watch " and a trailing " on X" / " - X" / " | X" where X names the site
    (measured on Hotstar: "Watch Bigg Boss Agniparikshe S1 Episode 1 on JioHotstar"),
    plus the layer's own title_tail."""
    title = " ".join(str(tab.evaluate("document.title", timeout=5.0) or "").split())
    tail = layer.get("title_tail") or ""
    if tail and title.endswith(tail):
        title = title[:-len(tail)]
    name = str(layer.get("name") or "").lower()
    m = re.match(r"^(?:watch\s+)?(.+?)(?:\s+(?:on|-|\||\u2013)\s+([^|\-\u2013]+))?$", title,
                 re.I)
    if m and m.group(2) and name and name.replace(" ", "") in m.group(2).lower().replace(" ", ""):
        return m.group(1)
    if m and title.lower().startswith("watch "):
        return m.group(1) + ((" " + m.group(2)) if m.group(2) else "")
    return title


def search_and_play(run, tab, url, query, layer):
    name = layer.get("name") or "the site"
    core.navigate(run, tab, url, "opening %s" % name)
    search_site(run, tab, query, name)
    label, _found = open_first_match(run, tab, query, layer, name)
    playing, ad, muted = start_playback(run, tab, layer, label)
    said = core.ascii_words(page_title(tab, layer), 70)
    if core.norm_name(said) in ("", core.norm_name(name)):
        # The watch page's title can still be the site's own name while an advert plays
        # (measured on YouTube: "YouTube"); the result's own name is then the honest one.
        said = label
    if playing:
        if layer.get("best_effort"):
            # The watch page's title, not the tile's caption: measured, the caption read
            # "bigg boss agniparikshe bigg boss agniparikshe 2026 kannada..." (alt text and
            # text run together) while the page said what was actually playing.
            return "Opened %s and %s %s%s." % (
                name, layer.get("verb", "started"), said or label,
                " - a short clip is playing first, most likely an advert" if ad else "")
        tail = " - the first result, '%s'" % said if said else ""
        if ad:
            tail += " (an advert is playing first)"
        if muted:
            tail += " - muted, as the player was left"
        return "Opened %s and %s %s%s." % (name, layer.get("verb", "started playing"),
                                           core.ascii_words(query) or "it", tail)
    label = said or label        # the page's own name for it, in every line below
    wall = tab.evaluate(_WALL_JS, timeout=5.0)
    if wall == "login":
        raise core.Failed("I found %s on %s, but it wants you logged in before it will play "
                          "- the page is open for you" % (label, name))
    if wall == "subscription":
        raise core.Failed("I found %s on %s, but it needs a subscription to play - the page "
                          "is open for you" % (label, name))
    if muted:
        raise core.Failed("I found %s on %s, but only a silent preview played, not the thing "
                          "itself - the page is open for you to take from there" % (label, name))
    if layer.get("generic") and not tab.evaluate("!!document.querySelector('video')"):
        return ("Opened %s, searched it for '%s' and opened the first match, '%s' - there "
                "is no video on it to start." % (name, core.ascii_words(query), said))
    raise core.Failed("I found %s on %s and opened it, but nothing started playing within "
                      "%.0f seconds - the page is open for you" % (label, name, PLAY_TIMEOUT_S))


def open_only(run, tab, url):
    landed = core.navigate(run, tab, url, "opening %s" % (urllib.parse.urlsplit(url).hostname
                                                           or url))
    host = urllib.parse.urlsplit(landed).hostname or landed
    return ("Opened %s - I only opened it; nothing on the page was searched or clicked."
            % core.ascii_words(host, 80))


# =============================================================================
#  MAIN
# =============================================================================

def main():
    try:
        raw = sys.stdin.buffer.read().decode("utf-8", "replace")
        params = json.loads(raw) if raw.strip() else {}
    except ValueError:
        core.say("I could not read what to open, sir - the request was not JSON.")
        return 1
    if not isinstance(params, dict):
        core.say("I could not read what to open, sir.")
        return 1
    query = " ".join(str(params.get("query") or "").split())
    kind, url, plan, layer = resolve(params.get("site"), query)
    if not kind:
        core.say("I did not open anything, sir - %s." % core.ascii_words(plan, 160))
        return 1

    port, browser_ws = core.live_port()
    if port is None:
        core.say(NO_PORT)
        return 1

    panic = core.PanicKey(0x0B1A)
    run = core.Run(panic, BUDGET_S)
    tab = None
    try:
        refusal = core.arm_or_refuse(panic, WHO)
        if refusal:
            core.say(refusal)
            return 1
        tab = core.open_tab(run, port, browser_ws)
        if kind in SITES and query:
            line = search_and_play(run, tab, url, query, layer)
        elif kind == "search":
            line = search_and_play(run, tab, url, query, dict(layer, generic=True))
        else:
            line = open_only(run, tab, url)
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
