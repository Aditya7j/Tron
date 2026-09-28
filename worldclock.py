"""worldclock.py - WHAT TIME IT IS SOMEWHERE ELSE, AND WHAT DAY THAT IS HERE.

WHY THIS IS A MODULE AND NOT A WEB SEARCH. "What time is it in Tokyo" is a question about
arithmetic on a table, and the table is on this disk. Sending it to a search engine costs a
round trip, a rate limit and a page of advertising to compute a subtraction - and worse, it
makes the answer depend on a network, so the one question in the house with a certain answer
becomes the one that can fail. So: zero lookups, like the four protected classes, and for the
same reason. Nothing in this file opens a socket.

THE DAY IS THE POINT. A clock reading on its own is a half-answer and the missing half is the
one that causes a missed call: "it is nine in the morning in Tokyo" is useless to a man in
India at half past five in the morning unless he is also told that Tokyo's nine is TODAY and
not tomorrow. The mandate says it in the sentence it asks for - "in Tokyo, sir - tomorrow,
against your clock" - and the phrase "against your clock" is load-bearing: the offset is
computed between the target's calendar date and THIS MACHINE's calendar date at the same
instant, so it is a statement about the employer's day and not about UTC's.

WHERE THE ZONE RULES COME FROM, and why there is a fallback. `zoneinfo` is the standard
library and is what this module prefers, but on Windows the standard library ships the CODE
and not the DATA: `ZoneInfo("Asia/Tokyo")` raises ZoneInfoNotFoundError on this machine
because the IANA database is not on it and `tzdata` is a separate package. `dateutil`, which
is already installed here, carries its own copy of the IANA database inside its wheel, so the
second door uses that. Both doors read the real rules - the DST transitions, the half-hour
zones, the ones that changed their minds - which is the whole reason a hand-written table of
UTC offsets is NOT what this file contains. A hand-written table is wrong twice a year in
March and October, silently, and the answer it gives is exactly as confident as a right one.

FAILURE MODE IF BOTH DOORS ARE SHUT: every reading refuses, `ready()` is False, and the panel
row says so. It does not fall back to a guess. A clock that is sometimes an hour out is worse
than no clock, because nobody checks a clock they trust.
"""

import datetime
import re
import unicodedata

# -------------------------------------------------------------------------------------------
# THE ZONE DOOR. Tried once and remembered, because the failure is a missing package and a
# missing package does not arrive halfway through a session.
# -------------------------------------------------------------------------------------------

_SOURCE = ""
_GET = None


def _zone_door():
    """(getter, source-name). The getter takes an IANA key and returns a tzinfo or None."""
    global _SOURCE, _GET
    if _GET is not None:
        return _GET, _SOURCE
    try:
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

        def viastdlib(key):
            try:
                return ZoneInfo(key)
            except (ZoneInfoNotFoundError, KeyError, ValueError):
                return None

        # PROVE IT BEFORE ADOPTING IT. Importing zoneinfo succeeds on a machine with no
        # database at all, so the import is not the test - one real key is.
        if viastdlib("Asia/Tokyo") is not None:
            _GET, _SOURCE = viastdlib, "zoneinfo"
            return _GET, _SOURCE
    except Exception:
        pass
    try:
        from dateutil.zoneinfo import get_zonefile_instance

        zf = get_zonefile_instance()

        def viadateutil(key):
            return zf.get(key)

        if viadateutil("Asia/Tokyo") is not None:
            _GET, _SOURCE = viadateutil, "dateutil.zoneinfo"
            return _GET, _SOURCE
    except Exception:
        pass

    def never(_key):
        return None

    _GET, _SOURCE = never, ""
    return _GET, _SOURCE


def ready():
    """Whether there is a zone database on this machine at all."""
    _get, src = _zone_door()
    return bool(src)


def source():
    """Which door answered, for the panel's state line and for the lookbook."""
    _get, src = _zone_door()
    return src


# -------------------------------------------------------------------------------------------
# THE PLACES. A city is not a zone: "Tokyo" is a word a person says and "Asia/Tokyo" is a key
# in a database, and the mapping between them is editorial. So it is written out, with the
# aliases people actually use, and a place that is not in it is REFUSED rather than guessed.
#
# WHY REFUSING IS THE FEATURE. The tempting alternative is to hand the word to the zone
# database's own key list and match loosely: "Asia/Kolkata" would then answer "Kolkata", which
# is right, and "America/Indiana/Knox" would answer "Knox", which nobody meant. Worse, a fuzzy
# match turns an unknown place into a confident wrong answer in a different hemisphere - which
# is the one outcome a clock must never produce. A short table that says "I do not know" is
# more useful than a long one that says "half past four" about the wrong continent.
#
# THE TILES. `board=True` marks the handful the Command Panel shows without being asked. They
# are chosen to span the working day rather than to be the largest cities: a board where every
# tile reads the same hour teaches nothing.
# -------------------------------------------------------------------------------------------

PLACES = [
    # (canonical label, IANA zone, aliases, on the board)
    ("London", "Europe/London", ("uk", "england", "britain", "gb"), True),
    ("New York", "America/New_York", ("nyc", "new york city", "manhattan", "ny"), True),
    ("San Francisco", "America/Los_Angeles",
     ("sf", "bay area", "silicon valley", "california"), True),
    ("Tokyo", "Asia/Tokyo", ("japan",), True),
    ("Dubai", "Asia/Dubai", ("uae", "abu dhabi", "emirates"), True),
    ("Sydney", "Australia/Sydney", ("australia",), True),
    ("Los Angeles", "America/Los_Angeles", ("la", "hollywood"), False),
    ("Chicago", "America/Chicago", (), False),
    ("Denver", "America/Denver", ("colorado",), False),
    ("Seattle", "America/Los_Angeles", (), False),
    ("Boston", "America/New_York", (), False),
    ("Washington", "America/New_York", ("dc", "washington dc"), False),
    ("Miami", "America/New_York", ("florida",), False),
    ("Toronto", "America/Toronto", (), False),
    ("Vancouver", "America/Vancouver", (), False),
    ("Montreal", "America/Toronto", (), False),
    ("Mexico City", "America/Mexico_City", ("mexico",), False),
    ("Bogota", "America/Bogota", ("colombia", "bogotá"), False),
    ("Lima", "America/Lima", ("peru",), False),
    ("Santiago", "America/Santiago", ("chile",), False),
    ("Buenos Aires", "America/Argentina/Buenos_Aires", ("argentina",), False),
    ("Sao Paulo", "America/Sao_Paulo", ("brazil", "brasil", "são paulo"), False),
    ("Rio de Janeiro", "America/Sao_Paulo", ("rio",), False),
    ("Reykjavik", "Atlantic/Reykjavik", ("iceland", "reykjavík"), False),
    ("Dublin", "Europe/Dublin", ("ireland",), False),
    ("Lisbon", "Europe/Lisbon", ("portugal",), False),
    ("Madrid", "Europe/Madrid", ("spain",), False),
    ("Barcelona", "Europe/Madrid", (), False),
    ("Paris", "Europe/Paris", ("france",), False),
    ("Brussels", "Europe/Brussels", ("belgium",), False),
    ("Amsterdam", "Europe/Amsterdam", ("netherlands", "holland"), False),
    ("Berlin", "Europe/Berlin", ("germany",), False),
    ("Munich", "Europe/Berlin", ("münchen",), False),
    ("Frankfurt", "Europe/Berlin", (), False),
    ("Zurich", "Europe/Zurich", ("switzerland", "zürich"), False),
    ("Geneva", "Europe/Zurich", (), False),
    ("Milan", "Europe/Rome", (), False),
    ("Rome", "Europe/Rome", ("italy",), False),
    ("Vienna", "Europe/Vienna", ("austria",), False),
    ("Prague", "Europe/Prague", ("czechia", "czech republic"), False),
    ("Warsaw", "Europe/Warsaw", ("poland",), False),
    ("Stockholm", "Europe/Stockholm", ("sweden",), False),
    ("Oslo", "Europe/Oslo", ("norway",), False),
    ("Copenhagen", "Europe/Copenhagen", ("denmark",), False),
    ("Helsinki", "Europe/Helsinki", ("finland",), False),
    ("Athens", "Europe/Athens", ("greece",), False),
    ("Istanbul", "Europe/Istanbul", ("turkey", "turkiye", "türkiye"), False),
    ("Kyiv", "Europe/Kyiv", ("ukraine", "kiev"), False),
    ("Moscow", "Europe/Moscow", ("russia",), False),
    ("Cairo", "Africa/Cairo", ("egypt",), False),
    ("Lagos", "Africa/Lagos", ("nigeria",), False),
    ("Accra", "Africa/Accra", ("ghana",), False),
    ("Nairobi", "Africa/Nairobi", ("kenya",), False),
    ("Addis Ababa", "Africa/Addis_Ababa", ("ethiopia",), False),
    ("Johannesburg", "Africa/Johannesburg", ("south africa", "joburg"), False),
    ("Cape Town", "Africa/Johannesburg", (), False),
    ("Casablanca", "Africa/Casablanca", ("morocco",), False),
    ("Tel Aviv", "Asia/Jerusalem", ("israel",), False),
    ("Jerusalem", "Asia/Jerusalem", (), False),
    ("Riyadh", "Asia/Riyadh", ("saudi arabia", "saudi"), False),
    ("Doha", "Asia/Qatar", ("qatar",), False),
    ("Tehran", "Asia/Tehran", ("iran",), False),
    ("Karachi", "Asia/Karachi", ("pakistan",), False),
    ("Lahore", "Asia/Karachi", (), False),
    ("Kabul", "Asia/Kabul", ("afghanistan",), False),
    ("Delhi", "Asia/Kolkata", ("new delhi",), False),
    ("Mumbai", "Asia/Kolkata", ("bombay",), False),
    ("Bengaluru", "Asia/Kolkata", ("bangalore",), False),
    ("Chennai", "Asia/Kolkata", ("madras",), False),
    ("Hyderabad", "Asia/Kolkata", (), False),
    ("Pune", "Asia/Kolkata", (), False),
    ("Kolkata", "Asia/Kolkata", ("calcutta", "india"), False),
    ("Kathmandu", "Asia/Kathmandu", ("nepal",), False),
    ("Colombo", "Asia/Colombo", ("sri lanka",), False),
    ("Dhaka", "Asia/Dhaka", ("bangladesh",), False),
    ("Yangon", "Asia/Yangon", ("myanmar", "burma", "rangoon"), False),
    ("Bangkok", "Asia/Bangkok", ("thailand",), False),
    ("Hanoi", "Asia/Bangkok", ("vietnam",), False),
    ("Ho Chi Minh City", "Asia/Bangkok", ("saigon",), False),
    ("Jakarta", "Asia/Jakarta", ("indonesia",), False),
    ("Singapore", "Asia/Singapore", (), False),
    ("Kuala Lumpur", "Asia/Kuala_Lumpur", ("malaysia",), False),
    ("Manila", "Asia/Manila", ("philippines",), False),
    ("Hong Kong", "Asia/Hong_Kong", ("hongkong",), False),
    ("Taipei", "Asia/Taipei", ("taiwan",), False),
    ("Shanghai", "Asia/Shanghai", ("china",), False),
    ("Beijing", "Asia/Shanghai", ("peking",), False),
    ("Shenzhen", "Asia/Shanghai", (), False),
    ("Seoul", "Asia/Seoul", ("korea", "south korea"), False),
    ("Osaka", "Asia/Tokyo", (), False),
    ("Perth", "Australia/Perth", (), False),
    ("Adelaide", "Australia/Adelaide", (), False),
    ("Brisbane", "Australia/Brisbane", (), False),
    ("Melbourne", "Australia/Melbourne", (), False),
    ("Auckland", "Pacific/Auckland", ("new zealand", "nz"), False),
    ("Wellington", "Pacific/Auckland", (), False),
    ("Suva", "Pacific/Fiji", ("fiji",), False),
    ("Honolulu", "Pacific/Honolulu", ("hawaii",), False),
    ("Anchorage", "America/Anchorage", ("alaska",), False),
    # THE DATE LINE, and both halves of it are here on purpose. Apia and Pago Pago are about
    # a hundred miles apart and their clocks read the same minute on DIFFERENT DAYS - +13 and
    # -11 - which is the one pair that proves the day offset is computed and not assumed from
    # a sign. clock_proof.mjs reads exactly these two.
    ("Apia", "Pacific/Apia", ("samoa",), False),
    ("Pago Pago", "Pacific/Pago_Pago", ("american samoa",), False),
    ("Nuku'alofa", "Pacific/Tongatapu", ("tonga", "nukualofa"), False),
    ("Kiritimati", "Pacific/Kiritimati", ("christmas island",), False),
    ("Midway", "Pacific/Midway", (), False),
    # UTC itself, because a man who works with servers asks for it and it is not a city.
    ("UTC", "UTC", ("gmt", "zulu", "utc time", "coordinated universal time"), False),
]


def _fold(text):
    """Lower case, accents off, punctuation off, one space. "São Paulo" -> "sao paulo"."""
    s = unicodedata.normalize("NFKD", str(text or ""))
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = s.lower().replace("’", "'").replace("`", "'")
    s = re.sub(r"[^a-z0-9' ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _index():
    """folded word -> (label, zone). Built once; canonical labels win over aliases."""
    if getattr(_index, "_cache", None):
        return _index._cache
    table = {}
    for label, zone, aliases, _board in PLACES:
        for word in (label,) + tuple(aliases):
            key = _fold(word)
            # FIRST WRITER WINS, and the canonical label is written first for every row, so
            # an alias can never quietly re-point a city somebody named exactly.
            if key and key not in table:
                table[key] = (label, zone)
    _index._cache = table
    return table


def places_known():
    """How many distinct words this module will answer to. Read by the panel and preflight."""
    return len(_index())


def board_places():
    """The tiles, in the order they are shown. Declared in PLACES, not sorted here: the order
    is editorial - it walks westward through a working day - and sorting by offset would put
    the board in a different order every March."""
    return [label for label, _z, _a, on in PLACES if on]


# -------------------------------------------------------------------------------------------
# THE READING
# -------------------------------------------------------------------------------------------


def home():
    """(label, offset-minutes) for THIS machine, from the operating system, right now.

    Not from the config and not from a constant: the employer's clock is whatever his laptop
    says it is, and a stored home zone would be wrong the first time he flies anywhere.

    NO tzinfo IS RETURNED, and that is deliberate. The obvious shape for this function was to
    hand back `datetime.now().astimezone().tzinfo`, which on Windows is a FIXED-OFFSET object
    carrying today's offset and no rules at all. Converting a January instant through it would
    silently use September's offset, so every caller below converts with a bare `.astimezone()`
    instead - which asks the platform for the offset that applied AT THAT INSTANT. It matters
    to exactly one caller today, the harness passing a fixed `at`, and it is the sort of thing
    that is wrong for six months before anybody notices.
    """
    now = datetime.datetime.now().astimezone()
    off = now.utcoffset() or datetime.timedelta(0)
    return (now.tzname() or "local", int(off.total_seconds() // 60))


def _clock_words(when):
    """Twelve-hour, written so that it reads correctly BOTH on the caption and out loud.

    THE COLON IS THE POINT. "3 30 in the afternoon" is what the first draft produced, and a
    neural voice reads a bare pair of numbers as two separate numbers - "three, thirty" - while
    "3:30" is read as a clock by every engine in the house. The Quiet Tongue does not normalise
    this, and should not: a colon between two numbers is not a mark that needs a pause, it is
    part of how a time is written.
    """
    hour24 = when.hour
    minute = when.minute
    hour12 = hour24 % 12 or 12
    # THE TWO HOURS THAT HAVE NAMES. "twelve o'clock in the afternoon" is not wrong so much as
    # not English, and "twelve o'clock at night" makes the listener work out which midnight.
    if minute == 0 and hour24 == 12:
        return "twelve noon"
    if minute == 0 and hour24 == 0:
        return "midnight"
    if 5 <= hour24 < 12:
        part = "in the morning"
    elif 12 <= hour24 < 17:
        part = "in the afternoon"
    elif 17 <= hour24 < 21:
        part = "in the evening"
    else:
        part = "at night"
    if minute == 0:
        # "nine o'clock at night" rather than "nine at night", which sounds unfinished.
        return "%d o'clock %s" % (hour12, part)
    return "%d:%02d %s" % (hour12, minute, part)


def resolve(place):
    """(label, zone) for a spoken place name, or (None, None). Exact on the folded form."""
    key = _fold(place)
    if not key:
        return None, None
    hit = _index().get(key)
    if hit:
        return hit
    # ONE TOLERATED SHAPE, and only one: a trailing country or qualifier the employer added
    # for clarity - "tokyo japan", "paris france". The head must itself be a whole known word,
    # so this cannot become a substring match on an unknown place.
    parts = key.split(" ")
    for cut in range(len(parts) - 1, 0, -1):
        hit = _index().get(" ".join(parts[:cut]))
        if hit:
            return hit
    return None, None


def reading(place, at=None):
    """A dict about one place, or None if the place is unknown or there is no zone database.

    `at` is for the harness and for nothing else: a fixed instant makes the date-line pair
    reproducible. Left None it is now, which is the only thing a real caller ever wants.
    """
    label, zone = resolve(place)
    if not label:
        return None
    get, _src = _zone_door()
    tz = get(zone)
    if tz is None:
        return None
    now = at or datetime.datetime.now(datetime.timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=datetime.timezone.utc)
    there = now.astimezone(tz)
    # Bare, so the platform resolves the home offset for THIS instant - see home().
    here = now.astimezone()
    # THE DAY OFFSET, and it is a difference of CALENDAR DATES rather than of hours. Rounding
    # an hour difference into days is the bug this avoids: Tokyo is four and a half hours from
    # here, which is nought days by any arithmetic on the offset, and is still tomorrow at
    # nine in the evening.
    days = (there.date() - here.date()).days
    off = there.utcoffset() or datetime.timedelta(0)
    return {
        "place": label,
        "zone": zone,
        "iso": there.isoformat(timespec="seconds"),
        "hhmm": there.strftime("%H:%M"),
        "clock": _clock_words(there),
        "date": there.strftime("%Y-%m-%d"),
        "weekday": there.strftime("%A"),
        "offsetMinutes": int(off.total_seconds() // 60),
        "abbrev": there.tzname() or "",
        "dayOffset": days,
        "dayWord": DAY_WORDS.get(days, ""),
    }


# The three the day offset can be for any pair of real zones - the spread is 26 hours end to
# end, so two calendar dates apart is arithmetically impossible and is left out rather than
# given a word it would never wear.
DAY_WORDS = {-1: "yesterday", 0: "today", 1: "tomorrow"}


def spoken(place, boss_call="sir", at=None):
    """The sentence, or a plain refusal. THIS IS THE WHOLE PUBLIC ANSWER.

    The mandate's shape: "...in Tokyo, Addi - tomorrow, against your clock". The day clause is
    always present, including when it is "today", because a clause that only appears when the
    news is bad trains the listener to hear its absence as nothing at all - and then a missing
    "tomorrow" is indistinguishable from a machine that forgot.
    """
    if not ready():
        return ("I cannot tell you, %s - there is no timezone database on this machine, and I "
                "will not work it out from an offset I would have to guess at." % boss_call)
    r = reading(place, at=at)
    if r is None:
        # PLAINLY REFUSED. No nearest match, no "did you mean", no hemisphere. See PLACES.
        #
        # THE WORD IS GIVEN BACK CAPITALISED because it arrives from the funnel's peel, which
        # lower-cases everything - and "I do not know where narnia is" reads as a machine that
        # did not recognise the word as a place name at all, which is a second and untrue claim
        # on top of the true one. Only the first letter of each word, and only where the word is
        # entirely lower case, so a name he typed as "iOS" or "McMurdo" is left as he typed it.
        said = re.sub(r"\s+", " ", str(place or "that")).strip()[:60]
        said = " ".join(w[:1].upper() + w[1:] if w.islower() else w for w in said.split(" "))
        return ("I do not know where %s is, %s, so I will not guess at its clock."
                % (said, boss_call))
    day = r["dayWord"]
    if r["dayOffset"] == 0:
        # "today, against your clock" is the honest form and it is also the reassuring one:
        # it says the offset was computed and came out nought.
        tail = "today, against your clock"
    else:
        tail = "%s, against your clock" % day
    return "It is %s in %s, %s - %s." % (r["clock"], r["place"], boss_call, tail)


def here_now(boss_call="sir"):
    """His own clock, for "what time is it" with no place in it. No day clause: a day offset
    against himself is nought by construction, and saying so would be comic."""
    now = datetime.datetime.now().astimezone()
    return "It is %s, %s." % (_clock_words(now), boss_call)


def board(at=None):
    """Every tile the Command Panel shows, plus the machine's own clock first.

    The page ticks these itself between reads - see the viewer - so this route is a truth
    anchor and not an animation frame. It carries the offset in MINUTES so the page can tick
    without asking again, and the day offset in days so the page never computes one.
    """
    rows = []
    now = at or datetime.datetime.now(datetime.timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=datetime.timezone.utc)
    here = now.astimezone()
    hoff = int((here.utcoffset() or datetime.timedelta(0)).total_seconds() // 60)
    rows.append({"place": "Here", "zone": "local", "home": True,
                 "hhmm": here.strftime("%H:%M"), "date": here.strftime("%Y-%m-%d"),
                 "weekday": here.strftime("%A"), "offsetMinutes": hoff,
                 "abbrev": here.tzname() or "", "dayOffset": 0, "dayWord": "today"})
    for label in board_places():
        r = reading(label, at=now)
        if r:
            r["home"] = False
            rows.append(r)
    return rows


# -------------------------------------------------------------------------------------------
# THE SENTENCE THAT ASKS. Read by the funnel, which is why it is anchored at both ends: a
# clock class that matched "what time" anywhere in an utterance would swallow "what time did I
# write that note about Tokyo", which is a question for the notes and has a different answer.
# -------------------------------------------------------------------------------------------

# THE FRAGMENTS, NAMED, because the first draft wrote `(?:'s| is)?` inline three times and
# every one of them was broken the same way: under re.VERBOSE a space in the PATTERN is
# stripped, including the one inside an alternation, so `(?:'s| is)?` compiles to `(?:'s|is)?`
# and "what is the time in Sydney" never matched at all while "what time is it in Sydney" did.
# The symptom was a clock class that worked on the phrasing I happened to test with. Whitespace
# in a verbose pattern must be written `\s`, and writing it once is how it stays written.
_WHAT = r"what(?:'s|’s|s|\s+is)?"       # what, what's, whats, what is
_NOW = r"(?:\s+(?:right\s+now|now|currently|at\s+the\s+moment|just\s+now))?"
_ASKS = (r"(?:%s\s+(?:the\s+)?time | what\s+time\s+is\s+it | what\s+day\s+is\s+it"
         r" | %s\s+the\s+date | how\s+late\s+is\s+it"
         r" | time | the\s+time | local\s+time | current\s+time)" % (_WHAT, _WHAT))

# "what time is it in tokyo", "time in tokyo", "what's the time in new york right now",
# "what day is it in sydney", "how late is it in berlin".
#
# THE PLACE GROUP IS LAZY. Greedy, it swallowed the trailing adverb - "Sydney right now" went
# to resolve() as a place name and was refused as an unknown city, which is a refusal about
# the wrong thing. Lazy, the optional _NOW after it takes those words instead.
CLOCK_WHERE_RE = re.compile(r"""^(?:so\s+)?""" + _ASKS + _NOW + r"""
    \s+(?:in|at|over\s+in|for)\s+
    (?P<place>[^?.!,]{1,60}?)""" + _NOW + r"""
    [\s?.!]*$""", re.IGNORECASE | re.VERBOSE)

# "what time is it in tokyo" with the place first: "tokyo time", "what is tokyo's time".
CLOCK_POSSESSIVE_RE = re.compile(r"""^
    (?:""" + _WHAT + r"""\s+(?:the\s+)?)?
    (?P<place>[a-z][a-z .'À-ɏ-]{1,40}?)
    (?:'s)?\s+(?:local\s+)?time""" + _NOW + r"""
    [\s?.!]*$""", re.IGNORECASE | re.VERBOSE)

# And his own clock, with no place in it at all.
CLOCK_HERE_RE = re.compile(r"""^(?:
      """ + _WHAT + r"""\s+the\s+time | what\s+time\s+is\s+it | how\s+late\s+is\s+it
    | (?:the\s+)?time\s+please
    )
    (?:\s+here)?""" + _NOW + r"""
    (?:\s+here)?
    [\s?.!]*$""", re.IGNORECASE | re.VERBOSE)

# THE WORDS THAT MEAN IT IS NOT A CLOCK QUESTION AT ALL, checked before the two above. Every
# one of them turns "time in X" into a question with a different door: a note to search, a
# duration to compute, a calendar to read. Without this, "how much time is left in Tokyo"
# would come back as a clock reading, which answers a question nobody asked.
CLOCK_NOT_RE = re.compile(
    r"\b(?:note|notes|wrote|written|write|remember|said|meeting|calendar|schedule|"
    r"flight|left|remaining|zone\s+difference|difference\s+between|convert|"
    r"how\s+long|duration|deadline|timer|alarm|timezone\s+of|history|weather)\b",
    re.IGNORECASE)


def asked(message):
    """('where', place) | ('here', '') | (None, '') for one whole utterance.

    Given the ADDRESSLESS form by the funnel, the same as the four protected classes get.
    """
    text = re.sub(r"\s+", " ", str(message or "")).strip()
    if not text or CLOCK_NOT_RE.search(text):
        return None, ""
    m = CLOCK_WHERE_RE.match(text)
    if m:
        return "where", m.group("place").strip()
    # HIS OWN CLOCK IS TRIED BEFORE THE POSSESSIVE, and the order is the fix for a real bug.
    # The possessive pattern's place group is lazy and its "what's the" prefix is optional, so
    # "what is the time" matched it with the place read as "what is the" - which resolve()
    # rightly did not know, and the branch then returned a flat no. Three of the boss's most
    # ordinary phrasings fell out of the class that way. The "here" forms are anchored to the
    # whole utterance and cannot swallow a city, so they go first.
    if CLOCK_HERE_RE.match(text):
        return "here", ""
    m = CLOCK_POSSESSIVE_RE.match(text)
    if m:
        place = m.group("place").strip()
        # THE POSSESSIVE FORM IS THE LOOSE ONE, so it is only allowed to fire on a place this
        # module actually knows. "what's the response time" must not become a refusal about a
        # city called "response"; it must fall through to the ordinary funnel.
        if resolve(place)[0]:
            return "where", place
    return None, ""


if __name__ == "__main__":
    # A reading, not a test. clock_proof.mjs is the proof; this is for reading by eye.
    print("source: %r  places: %d" % (source(), places_known()))
    print("home  : %r" % (home(),))
    for word in ("Tokyo", "London", "New York", "Apia", "Pago Pago", "Kolkata",
                 "Narnia", "Zanzibar-on-Sea"):
        print("  %-16s %s" % (word, spoken(word, "Addi")))
    print("  here            %s" % here_now("Addi"))
    for row in board():
        print("  tile %-14s %s %s %+d" % (row["place"], row["hhmm"], row["weekday"],
                                          row["dayOffset"]))
