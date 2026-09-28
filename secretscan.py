"""secretscan.py - does this text carry a credential? One opinion, three readers.

WHY IT IS ITS OWN FILE. Three places need this answer and they must not disagree:
server.py refuses at PROPOSAL time so the employer is told before a card ever goes up,
tools/save_note.py refuses again at WRITE time because a tool that trusts its caller to
have checked is a tool that writes a secret the day the caller changes, and preflight.py
asserts the whole notes tree is clean. Three copies of a regex is three chances to fix
two of them.

WHAT IT IS FOR, in one sentence: a note is forever and a note is INDEXED, so a password
dictated into one is a password that a later question can be answered with, out loud, by a
machine that has forgotten where it came from. The galaxy has no concept of a secret and
should not gain one; the cure is that credentials never get in.

THE ONE RULE ABOUT ITS OWN OUTPUT, and it is the standing law of this project: no finding
ever carries the value. A report names the KIND, the position and the length - "an AWS
access key id, 20 characters, at offset 112" - and never the characters. A scanner that
quotes what it found has copied the secret into the log that was written to prove the
secret was kept out of the note.

  found(text)   -> [] or a list of {"kind", "at", "len"}, value-free, in text order
  reason(hits)  -> one sentence naming the kinds, for a refusal the employer will hear
  clean(text)   -> True when found() is empty. For readers that only want the boolean.

WHICH DIRECTION IT ERRS IN, deliberately. A false positive refuses a note and says why,
and the employer rephrases: one sentence lost. A false negative puts a live credential in
an indexed file that will be read back to him in a year. So the labelled patterns below
are broad ("the password is <something that looks like a value>") and the shaped ones are
narrow (a real AKIA prefix, a real PEM header), which is the combination that catches a
dictated secret without refusing the sentence "my password is in the vault" - "in" is a
word, and a value is not.
"""
import re

# -- SHAPED CREDENTIALS. Each of these is recognisable on its own, with no label in front,
# because the issuer gave it a prefix nobody else uses. A hit here is very nearly certain,
# which is why these do not require any context at all.
SHAPES = (
    ("an AWS access key id", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("a Google OAuth client secret", re.compile(r"\bGOCSPX-[A-Za-z0-9_-]{16,}")),
    ("a Google API key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
    # An OAuth refresh token and an authorization code. Both start with a shape that is
    # not otherwise seen in prose, and both are exactly what the one consent click mints.
    ("an OAuth refresh token", re.compile(r"\b1//[0-9A-Za-z_-]{20,}")),
    ("an OAuth authorization code", re.compile(r"\b4/[0-9A-Za-z_-]{30,}")),
    ("an Anthropic API key", re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}")),
    ("an API key of the sk- family", re.compile(r"\bsk-[A-Za-z0-9]{32,}\b")),
    ("a GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b")),
    ("a Slack token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}")),
    ("a private key", re.compile(r"-----BEGIN[A-Z ]*PRIVATE KEY-----")),
    # A JWT: three dot-separated base64url runs, the first of which decodes to "{"..."
    # so it begins eyJ. Bearer tokens arrive in this shape far more often than not.
    ("a signed token (JWT)",
     re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}")),
)

# -- WHAT A VALUE LOOKS LIKE, for the labelled patterns below. One unbroken run of six or
# more, carrying at least one digit or one symbol or a capital after a lowercase - which is
# what separates "hunter2", "Kx9-mm4Q" and "p@ssw0rd" from "vault", "somewhere" and
# "changed". This is the whole reason "my password is in the vault" is not a finding: "in"
# is three letters and "the" is not a value either.
#
# THE CAMEL TEST IS SCOPED CASE-SENSITIVE and that is not a flourish, it is a bug that was
# caught by the battery. LABELLED is compiled IGNORECASE - it has to be, because he may say
# "Password" or "API key" - and under IGNORECASE `[A-Z]` matches lowercase, so
# `\S*[a-z]\S*[A-Z]` degenerated into "has two letters" and read the word "rotated" as a
# value. "the api key was rotated last week" was refused as a credential. (?-i:...) turns
# the flag off for exactly the three characters that depend on case and nothing else.
VALUE = r"""(?:
      (?=[^\s]{6,})                          # six or more, unbroken
      (?= \S*[0-9] | \S*[^\sA-Za-z0-9] | (?-i:\S*[a-z]\S*[A-Z]) )   # digit, symbol or camel
      \S+
   )"""

# -- LABELLED CREDENTIALS. The employer saying what it is. "is" and "was" are here on
# purpose: a person dictating a secret says "the password is", never "password=".
LABEL = r"""(?: pass \s* (?: word | phrase ) | api \s* key | secret \s* (?: key | access \s* key )?
          | client \s* secret | access \s* token | refresh \s* token | bearer \s* token
          | auth \s* (?: orization )? \s* (?: code | token ) | private \s* key
          | credential s? | pin \s* (?: code | number ) )"""

LABELLED = re.compile(r"\b" + LABEL + r"\b \s* (?: is | was | :+ | = ) \s* " + VALUE,
                      re.IGNORECASE | re.VERBOSE)

# AND THE CONFIG FIELD NAMES THIS PROJECT'S OWN config.json USES, which is the one file
# whose shape is known here. "aws_secret_access_key: ..." pasted into a note is the exact
# accident this whole module exists to stop, and it would otherwise arrive as an
# underscored word the LABEL above does not read as English.
FIELDS = re.compile(r"\b(?:aws_(?:access_key_id|secret_access_key|session_token)"
                    r"|google_client_secret|refresh_token|client_secret)\b\s*[:=]\s*\S{6,}",
                    re.IGNORECASE)


def found(text):
    """[] or a list of value-free findings, in the order they appear.

    Each finding is {"kind": <English>, "at": <offset>, "len": <characters>}. The value is
    not in there and must never be put in there - see the module docstring.
    """
    said = str(text or "")
    hits = []
    for kind, pattern in SHAPES:
        for match in pattern.finditer(said):
            hits.append({"kind": kind, "at": match.start(),
                         "len": match.end() - match.start()})
    for kind, pattern in (("a labelled password or key", LABELLED),
                          ("a credential field from a config file", FIELDS)):
        for match in pattern.finditer(said):
            hits.append({"kind": kind, "at": match.start(),
                         "len": match.end() - match.start()})
    # OVERLAPS ARE COLLAPSED TO THE LONGEST. "the client secret is GOCSPX-..." matches both
    # a shape and a label, and reporting it twice would have the refusal say "two
    # credentials" about one. Sorted by position so the sentence reads in text order.
    hits.sort(key=lambda h: (h["at"], -h["len"]))
    kept = []
    for hit in hits:
        if kept and hit["at"] < kept[-1]["at"] + kept[-1]["len"]:
            continue
        kept.append(hit)
    return kept


def clean(text):
    """True when nothing in `text` looks like a credential."""
    return not found(text)


def reason(hits):
    """One sentence naming the kinds and nothing else, for a refusal he will hear."""
    kinds = []
    for hit in hits:
        if hit["kind"] not in kinds:
            kinds.append(hit["kind"])
    if not kinds:
        return ""
    if len(kinds) == 1:
        return "it carries what looks like %s" % kinds[0]
    return "it carries what looks like %s and %s" % (", ".join(kinds[:-1]), kinds[-1])
