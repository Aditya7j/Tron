# Knowledge Galaxy

A 3D galaxy of your markdown notes, with a brain you can talk to.

```
build.py            indexer: every .md -> viewer/graph-data.js + notes-index.json
server.py           static server (viewer/ only) + /chat + /remember + /see + /model + SigV4 by hand
focus.py            focus sessions: the tick, the reader, the callouts, the ledger
preflight.py        runs every live chain against the running server and prints a verdict
test_focus_privacy.py   proves no identity is ever STORED: named out loud, kept nowhere
focus_live.mjs      the live loop: click FOCUS, settle, hear the callout, move the lock, hear the report
config.json         provider, credentials, model  <- project root, never served
focus-ledger.json   generated - aggregates only: counts, minutes, streak. No history
notes/              the markdown corpus
notes/captures/     written by /remember, indexed like any other folder
viewer/index.html   the galaxy (3d-force-graph from a CDN, no npm, no build step)
viewer/graph-data.js  generated - do not edit
notes-index.json    generated - full note text for the brain
```

## Run it

```bash
python build.py           # re-index whenever the notes change
python server.py          # http://127.0.0.1:4700
python server.py --models # which Bedrock model ids this account may use
```

`server.py` runs `build.py` for you if `notes-index.json` is missing, and reloads
the index whenever it changes on disk. `config.json` is re-read on every request,
so pasting credentials in does not need a restart — but editing `server.py` itself
does.

## Preflight

```bash
python preflight.py           # thirteen live chains, a tick or a cross each
python preflight.py --quiet   # just the summary line
python preflight.py --keep-note   # leave the probe note in the galaxy
```

Nothing in it is mocked. It talks to the running server over real HTTP, signs a real
call to the provider, writes a real markdown file into the real corpus and reads it
back through `/chat`, and sends a real JPEG to `/see`. Unit tests all passing while a
live chain is dead is the failure that costs an afternoon, and a mock cannot see it —
a mock is a description of what you believed at the time.

| | |
|---|---|
| 1 | the server is up and serving the viewer |
| 2 | `graph-data.js` loads, has nodes, and every `id` still equals its index |
| 3 | `/chat` answers a real question about a real note, with a `nodes` array |
| 4 | the credentials are valid, by one real signed call |
| 5 | the configured model is reachable, by one real round trip |
| 6 | `/remember` writes a file `/chat` retrieves immediately |
| 7 | `/see` answers a real JPEG |
| 8 | every file the browser is SERVED is byte-for-byte the file on disk |
| 9 | `config.json` is not reachable from the browser |
| 10 | `/model` loads the id it names, says one of its written lines through **both** doors without repeating itself, refuses the rest, and restores |
| 11 | a focus session ticks on the server with no browser involved, streams, and leaks nothing |
| 12 | the eyes nudge once, cool down, and cannot carry a picture — including under five smuggled names |
| 13 | the screen watch refuses four ways for nothing, then nudges once, and hands no frame back |

It finishes with `N pass, N fail, N warn` and exits with the number of failures, so
`python preflight.py --quiet && deploy` does the right thing.

Some details that are the difference between a harness and a decoration:

- **Check 7 builds a real JPEG with no image library.** There is no Pillow here, so
  `probe_frame()` writes a baseline JPEG by hand — Huffman tables, byte stuffing and
  all — with one shortcut: each 8×8 block carries only its DC coefficient, making it
  a flat colour. That is enough to draw large lettering, and the check is that the
  model *reads the heading back*. A 200 only proves the plumbing; a word read out of
  the pixels proves the bytes survived encoding, upload, base64 and the decoder. It
  is sent as `server.FRAME_MEDIA_TYPE`, imported rather than retyped, because a PNG
  probe would 400 and mimic a dead endpoint exactly.
- **Check 6 cleans up after itself.** The probe note is written into `notes/captures/`
  for real, verified on disk, retrieved through `/chat`, then deleted and the index
  rebuilt back to the original count. It plants *two* random tokens: one lands in the
  title, one is buried past `TITLE_WORDS` in the body — so retrieval and *the note's
  text reaching the model* are two separate claims with two separate proofs.
- **Check 9 reads bodies, not status codes.** `http.client` is used rather than
  `urllib` because it sends `..` and backslashes verbatim instead of normalising them
  away. `/..\config.json` earns a 301 into `viewer/` and then an innocent 200 of
  `index.html`; the check follows the redirect and compares the bytes, so "confined"
  and "leaking" cannot be confused. It also scans every response body collected
  during the whole run against the live credential values and against `config.json`'s
  own contents — reporting *which* check leaked, never the value.
- **Check 10 runs last, and that is not tidiness.** It swaps the model, so anywhere
  earlier a leftover override would silently re-point checks 3–7 at a brain
  `config.json` never named, and they would fail for a reason that has nothing to do
  with them. It restores in a `finally`, so a failure inside it still hands the next
  run a server on the configured brain. Its assertions come out of `server.py`'s own
  dictionaries rather than being retyped — including the bogus version, which is
  derived from the real ones so it can never accidentally become real.
- **Check 11 starts a real session and cannot touch your streak.** It runs for a few
  seconds — well under `MIN_LEDGER_S` (30 s), which is the same guard that stops a
  mis-tap counting as a session — and it ends with `abort`, the one ending that never
  records. Belt and braces, it checksums `focus-ledger.json` either side and fails if
  a byte moved: a harness that quietly edits your record of your own work is worse
  than no harness. It also stands down with a warning rather than interfering if a
  session is *already* running, since ending yours is not preflight's business. The
  privacy assertion is made against what the server actually sent over HTTP, not
  against `focus.public_state` in the preflight process — `test_focus_privacy.py`
  proves the module cannot leak, check 11 proves the route does not. It also asserts
  over the wire that a session locks **nothing** at the start and says so, that a
  dictated intent is attached without ever being read back, and that both the spoken
  override and the card's pill move the lock in one read with a spoken confirmation
  either way — accepting *both* lawful answers, since which one you get depends on what
  is really in front of the machine while preflight runs, and naming the one that
  happened. Plus six strings in the two system prompts, because an assistant that
  invents a way to move the lock costs you the session — and one that repeats a privacy
  promise which is no longer true is worse, since you will find out by hearing it.
  The privacy half of the check is now the *true* claim rather than the simple one: an
  identity may appear in **one** place, a sentence from the named pools whose blank
  holds exactly the name this machine's own reader would derive, and the check then
  reads the route until that sentence is **gone**. Spoken, then scrubbed, proved over
  HTTP.
- **It polls for the clock rather than sleeping and sampling once.** `elapsedS` is
  whole seconds, so a fixed 2.6-second wait leaves about half a second of margin on a
  counter that moves in steps of one. A check that fails occasionally for arithmetic
  reasons teaches you to ignore it, which is worse than not having it at all. Same
  discipline as the two spoken-line checks in the live loop, for the same reason.
- **Warnings are not failures.** A model phrasing an answer unhelpfully warns; a
  chain being dead fails. Only failures move the exit code. With no OpenRouter key
  configured, check 10 warns: the swapped id is verified, the swapped *answer* is not.
  With no Chrome on the DevTools port, check 11 warns: the session is verified at
  application level, tab-level locking is unavailable to verify.

## The model

Two providers, chosen by `"provider"` in `config.json`. **Bedrock is the default**,
because it runs on AWS credentials you probably already have.

```json
{
  "provider": "bedrock",
  "aws_region": "us-west-2",
  "bedrock_model_id": "claude-haiku"
}
```

Credentials are looked for in this order, and the **first source holding both an id
and a secret wins outright** — sources are never mixed, because half a key pair from
one place and half from another is how you get a signature error you cannot read:

1. `config.json` — `aws_access_key_id`, `aws_secret_access_key`, `aws_session_token`
2. the environment — `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN`
3. `~/.aws/credentials` — under `aws_profile`, else `$AWS_PROFILE`, else `default`

Leaving the three `aws_*` fields blank is the tidier option: nothing is duplicated
into the project, and `aws configure`/SSO refreshes happen without editing anything
here. Temporary keys (the `ASIA…` kind, with a session token) expire, and `/chat`
says so in as many words when they do.

`bedrock_model_id` accepts a full id, an inference profile, or one of four short
names — `haiku`, `sonnet`, `opus`, `nova`. Modern Claude models on Bedrock are only
reachable through an inference profile, so the short names resolve to `us.`-prefixed
profiles. To see what your account may actually use:

```bash
python server.py --models
```

SigV4 is signed by hand in `server.py` — no boto3, keeping the no-dependency
promise. Note the trap it documents: outside S3 the canonical request wants each
path segment percent-encoded **twice**, so a model id ending `-v1:0` travels as
`%3A` and is signed as `%253A`.

### OpenAI instead

```json
{ "provider": "openai", "openai_api_key": "sk-...", "model": "gpt-6-astra" }
```

Either way the credential lives outside `viewer/`, the server only ever serves
`viewer/`, and it is never included in any response — `/health` reports *whether*
one is configured, never what it is. Until one is, `/chat` still finds and lights
up the matching notes and tells you what is missing. `config.json` is re-read on
every request, so pasting credentials in needs no restart.

## Changing its brain while it is running

Say **"switch to Astra"**, **"try on Claude Fable 5.1"**, **"go back to your normal
brain"** — or **click the chip** in the bottom-left corner and pick from the list. The
chip always names the model that is answering, and turns amber the moment it is not the
one `config.json` names.

```
POST /model   body: {"say": "try on Claude Fable 5.1", "door": "voice"}
  ->  200  {"ok": true,  "model": "anthropic/claude-fable-5.1", "label": "FABLE 5.1",
            "door": "voice", "intro": "curated", "answer": "…"}
  ->  409  {"ok": false, "refused": "noid", "available": [...]}   nothing changed

POST /model   body: {"model": "openai/gpt-6-astra", "door": "button"}   the menu's door
GET  /brains  ->  every model it will answer to, with a written name for each
```

Swapped models are reached through **OpenRouter**, so one key in
`"openrouter_api_key"` reaches every model in the map. OpenRouter speaks the OpenAI
request shape, so it shares `call_chat_completions()` with the OpenAI provider rather
than getting a second copy of it.

The spoken-name map is **one dictionary**, `SPOKEN_MODELS` near the top of
`server.py`, and the viewer never has its own copy — the chip is painted only from
what the server replied, so it cannot describe a swap that did not happen.

**Swaps are runtime only.** The override lives in one module-level variable behind a
lock and is applied inside `load_config()`, the one function every request path
already goes through, so `/chat`, `/see`, `/health` and the chip cannot disagree about
which brain is in play. `config.json` is never written, so a restart always returns to
the model that file names — you cannot strand yourself on a brain you did not mean to
keep, and the chip shows the restart target in its tooltip so that is not a surprise.

### The rule that makes it safe

`KNOWN_MODEL_IDS` is an explicit set of ids known to exist. Name a family plus a
version and the candidate id is built and **checked against that set**; if it is not
there, the swap is refused and the refusal names what is actually available. There is
no fuzzy matching anywhere in `resolve_spoken_model()` and no nearest-match fallback.

The failure this exists to prevent is specific: say "opus 5", a loose matcher sees
"opus", discards the version, loads an older Opus and announces success — and you
lose an afternoon testing the wrong model. On OpenRouter today `claude-opus-4`,
`4.1`, `4.5`, `4.6`, `4.7`, `4.8` and `5` all coexist, as do `fable-5` and
`fable-5.1`, so this is not a hypothetical.

```
"switch to Opus 7"  -> 409  OPUS 7 is not a model I know of, sir, and I will not hand
                            you a different vintage of OPUS and call it that. I have
                            5, 4.8 and 4.1.
"switch to Opus"    -> 409  "OPUS" is a family, sir, not a model. …
"become Gandalf 3"  -> 409  I have never heard of Gandalf 3, sir, so I remain as I am. …
```

Three details in the wording, because a refusal that overstates itself is still a lie:

- It says **"is not a model I know of"**, not "does not exist". `claude-opus-4.5` is
  real; it is simply not in this allowlist. The distinction is the difference between
  a refusal and a false claim.
- A refusal replies with the state it did **not** change, so the chip and the voice
  agree that nothing moved.
- It never echoes your command back at you — "I have never heard of *switch to* GPT
  6" would be a refusal that cannot read.

### The chip label

One rule, and it is the whole reason `display_label()` is a function: **a hyphen with
a digit on either side is a version dot, every other hyphen is a word gap.** So
`gpt-6-astra` reads **GPT 6 ASTRA** — not GPT 6.ASTRA — and `fable-5-1` reads
**FABLE 5.1**, not FABLE 5 1. Bedrock's `-YYYYMMDD` stamp and `-v1:0` suffix are
stripped *before* the digit rule runs, or `haiku-4-5-20251001-v1:0` would come out as
HAIKU 4.5.20251001.

Swapping onto a brain with no key configured still succeeds — the identity claim is
honest — and says so in the same breath: *"…There is no OpenRouter key in config.json,
mind, so my next answer will be an apology rather than an insight."* The alternative
is a chip that reads FABLE 5.1 over a brain that cannot speak.

### What a swap says

The obvious way to write this is to ask the new brain to introduce itself in one dry
sentence, and it is a good idea about three quarters of the time. The other quarter is
a reasoning model, which answers that instruction with an empty string — so the
fallback template quietly becomes the only thing anyone ever hears, and a template is
not a butler. `CURATED_LINES` near the top of `server.py` fixes it at the front of the
ladder: a list of `(pattern, lines)` pairs, and a model with a pool gets a **written**
line instead of a prompt.

```python
CURATED_LINES = [
    (re.compile(r"(?:^|/)gpt-6-astra$", re.I), [
        "New brain fitted, sir — GPT-6 Astra. Do try to keep up.",
        "GPT-6 Astra online, sir. I now understand everything — except why you keep "
        "opening Instagram.",
        …four more
    ]),
]
```

Three decisions in that block:

- **They rotate, they are not shuffled.** `_curated_turn` maps the pool to the next
  index, so six swaps in a row are six different sentences and the seventh comes round
  to the first. `random.choice()` on a pool of six repeats about one swap in six, which
  is the single outcome a pool exists to prevent. Only the *starting* position is
  random, once per process, so a restart does not always open with the same joke.
- **The pattern is anchored.** `(?:^|/)gpt-6-astra$` — an unanchored `astra` also
  matches `gpt-6-astra-pro`, and greeting the Pro model with the plain model's line is
  exactly the substitution [the allowlist](#the-rule-that-makes-it-safe) refuses
  everywhere else, performed in the voice, where it is hardest to notice. So the Pro
  model gets no curated line at all rather than a borrowed one.
- **They are about this desk**, not about the model. A line that mentions a benchmark
  is a press release; a line that mentions the tab you have had open since Tuesday is
  a butler.

### One voice, three doors

Every door reaches `swap_to()`, and `swap_to()` is the only place in the project that
decides what a swap **says**. One rung deeper, `brain_intro()` is the whole ladder, in
order:

| | |
|---|---|
| `curated` | a pool matches the new id — used at once, and **no model is called at all** |
| `model` | no pool: the new brain is asked for one short sentence, and it is used only if it is *usable* — non-empty, under 220 characters, no "as an AI", no apology, and not carrying its own slug |
| `fallback` | anything else, including no credentials and a provider that throws: `BRAIN_LINES["swapped"]` with a **pretty name** — *"GPT-6 Astra it is, sir."*, never `openai/gpt-6-astra online` |

The doors:

- **the chip's menu** — built from `GET /brains`, so a retired model cannot linger in a
  list the page wrote down; each row posts the `id` it is showing with `door: "button"`
- **a spoken sentence** — `SWAP_RE` in the page, `resolve_spoken_model()` on the server
- **a control tag** — "you are being rather slow today, fetch something sharper" names
  no model and no command verb, so `SWAP_RE` will never catch it. It arrives as
  conversation, and the chat brain may answer with `[[brain: astra]]` instead of prose.
  Three things keep that from being a model that changes its own brain on a whim: the
  tag is taught **only** to `SMALLTALK_PROMPT`, where a question about *you* lands; the
  name it uses goes through the same allowlist as every other door; and whatever prose
  came with the tag is **discarded**. The model may ask for the swap. It may not narrate
  it — that is what one voice means.

A swap onto the brain already in play is not a swap: it says *"I am GPT-6 Astra
already, sir"* and spends no line, because being told twice who you are talking to is
how a good line stops being a good line.

### Pinned names

```json
"model_aliases": {
  "astra": "openai/gpt-6-astra",  "gpt-6 astra": "openai/gpt-6-astra",
  "gpt 6 astra": "openai/gpt-6-astra",  "gpt-6": "openai/gpt-6-astra"
}
```

Consulted as **step 0** of `resolve_spoken_model()`, before anything is parsed: a
phrase you nailed down means what you said it means, whatever the catalogue grows next
week. Both sides of the lookup go through `_alias_key()`, which keeps the vendor word,
turns hyphens into spaces and splits `gpt6` into `gpt 6`, so the four phrases above are
three keys — a hyphen is a transcription accident and must not be the difference
between the right brain and a refusal.

A pin may choose between real models. It cannot invent one: every value is checked
against `KNOWN_MODEL_IDS` at load, and one that names something this server does not
have is **dropped**, with a single line on stderr rather than a silent surprise.

And no qualifier is ever dropped on the way through. `MODEL_QUALIFIERS` — the words
that change which model you get, learned from the catalogue and topped up by hand —
makes `"opus 5 turbo"` a refusal instead of Opus 5, and a slug-tail identity match
makes `"gpt-6-astra-pro"` the Pro model instead of the plain one. Which is the whole
reason those four phrases are pinned rather than parsed: a catalogue change must not be
able to hand you a `-mini` mid-take.

### Proving it

```bash
python test_brain.py      # 140 checks: the pools, the rotation, the ladder, the pins
node brain_live.mjs       # 32 checks: a real Chrome, a real click, a real spoken line
```

`test_brain.py` stubs `call_model` with a function that **raises**, so "a curated line
never reaches a model" is proved by the absence of an explosion rather than by reading
the code. `brain_live.mjs` opens the menu by clicking the chip, clicks a row rather
than calling the function behind it, feeds `"switch to Astra"` through the same
function the microphone feeds, and reads both sentences out of the page's own log of
what it said:

```
by button:  GPT-6 Astra, sir. Same desk, same notes, same tab you have had open since Tuesday.
by voice:   GPT-6 Astra, at your service. Sit perfectly still for a minute and I shall
            tell you what you are stuck on.
```

## Notes elsewhere

```bash
python build.py "D:/path/to/my/vault"
```

Labels come from filenames, groups from the parent folder. Notes are linked when
one mentions another's title, when one contains a `[[wikilink]]` to another, or
when two notes cite `SHARED_WIKILINK_MIN` (6) or more of the same `[[targets]]`.

## Growing the brain

Say or type anything beginning **"remember that"** and it becomes a note.

```
remember that the finish window should be 900 milliseconds
  -> notes/captures/finish-window-should-be-900-milliseconds.md
```

The file is real markdown — an `# H1` title from the first few words (filler like
"the" and "that" skipped), today's date written inside, then the thought itself.
Existing files are never overwritten; a repeated title becomes `-2`, `-3`.

On screen the note is **born live, without a reload**: it appears at the position
of its most related existing note, flares white for `PULSE_MS` (1600 ms), and then
the camera flies to it — in that order, so you see where it came from before the
view moves. Its cluster colour and legend row appear with it if `captures` is new.

Two things this had to get right, both of which bite later if you skip them:

**Writing a file is not indexing it.** `/remember` re-indexes *in process* and the
capture is answerable by the very next question, with no rebuild and no restart.
It does that by importing `build.py` and calling `build.py`'s own label, slug,
excerpt and linking functions — not by reimplementing them — so a capture is linked
exactly as a rebuild would link it, and stays that way if those rules ever change.
The one thing it does not delegate is numbering: **ids must not shift.** Ids are
array indexes, and the open tab and its camera are holding the old ones, so
`reindex_preserving_ids()` re-sorts the fresh nodes into the existing order and
only then appends. The response carries the whole authoritative link set, because a
capture can resolve a `[[wikilink]]` that was dangling in a note written months ago.

**A capture never fails silently.** Every exit from the capture path speaks a line,
because a second brain that quietly forgets is worse than none. The write is
verified by reading the file back — "the write returned without raising" is not the
same claim as "the note is on disk" — and *written but not yet indexed* is reported
as its own outcome rather than rounded up to success, since the file is safe but the
galaxy does not know it yet. The trigger is also checked server-side, so a stale tab
cannot answer a capture instead of performing it.

## Sight

Click the **monitor button** to start a `getDisplayMedia` share, then ask about what
is on screen — "what am I looking at", "what do you think of this?" While the share
is live the page is unmistakable about it: a pulsing red frame around the whole
window, a red chip naming the captured size, and the button lit. A tool that can see
your screen and says so quietly is a tool you will one day forget is watching.

Nothing is recorded, nothing is streamed anywhere. The stream stays in the tab and
**one still frame** leaves it per question:

```
POST /see?q=<question>   body: one JPEG frame   ->  {"answer", "kind": "screen"}
```

Three properties it was built to have, since each of them is a way the feature could
otherwise quietly lie to you:

- **The frame is grabbed when you ask.** `grabFrame()` runs after the question
  exists and draws the *current* video frame, so there is no "last frame" variable
  to fall back to — not by policy, by construction. The page measures the frame's
  age against its own clock and sends it as `X-Frame-Age-Ms`; the server refuses
  anything older than `FRAME_MAX_AGE_MS` (10 s). Two clocks are never compared.
- **An ended share is never answered from memory.** `sharing()` reads the track's
  own `readyState` rather than a hopeful flag, a 1 s watchdog repaints the
  indicator, and the browser's own "Stop sharing" bar is caught through the track's
  `ended` event. Ask a screen question in the minute after a share ends and it says
  the share has ended — out loud — and sends nothing.
- **The declared media type matches the bytes.** `FRAME_TYPE` is one constant used
  three times: to encode with, to check the resulting blob against, and to declare
  on the wire. `canvas.toBlob()` silently falls back to PNG for a type it cannot
  encode, so the page refuses to send a frame whose blob type is not what it asked
  for and names both types when it does. The server then sniffs the first bytes
  (`FRAME_MAGIC`) rather than trusting the header. Every refusal carries the
  technical detail, because "the whole feature is dead" is nearly always one wrong
  string and a polite line that hides which string is no help at all.

Screen answers **never move the camera**. `decideCamera()` returns `'hold'` for
`kind: "screen"` explicitly: flying to a note would be claiming a source the answer
does not have. The frame it actually judged is shown beside the answer instead —
with its size, weight and age — and cleared the moment the next answer arrives, so a
picture can never sit beside an answer it was not the evidence for. `/see` is
stateless: no history in, no history out, no note text, no note indexes.

`VISION_PROMPT` lives in the same persona block as the rest of the character, and
its longest section is about not guessing. Small talk still goes to `/chat` while
sharing — "good afternoon" is not a request for a screenshot review.

## Focus sessions

An accountability timer that watches where you actually are and calls you out when
you drift. Say **"thirty minutes on this"**, or click the **crosshair button**. A
countdown card pins itself top-right and tints when you wander off.

It does not decide what to watch at the click — it asks you to go to your work, waits
until you have settled there, and says **"Locked on, sir."** when it has. That is
[the deferred lock](#when-it-decides--and-it-is-not-when-you-click), and it is the
difference between a timer that watches your work and one that watches the tab you
started it from.

```
GET  /focus[?home=1|0]   the whole session state, as booleans and counters
GET  /focus/stream       server-sent events: the same state, pushed
POST /focus              {"say": "…"}  or  {"cmd": "start|pause|abort|…", "minutes": n}
POST /focus              {"cmd": "intent", "text": "…"}   your answer, attached
```

Everything lives in `focus.py` — the tick, the reader, the callouts, the ledger — and
`server.py` touches exactly three things in it: `focus.MANAGER`, `focus.handle` and
`focus.is_focus_request`. Every knob is a named constant in the block at the top of
that file.

### The session lives on the server

Its own thread, its own one-second tick (`TICK_S`), independent of every browser tab
in existence. Reload the page, close it, open a second one: the session carries on and
each tab rejoins *the same one*. A timer that dies with a tab is a timer you cannot
trust to hold you to anything — and preflight check 11 proves the clock moves while no
browser is involved at all.

Updates reach the page over **server-sent events**, not polling. That is not a
preference. A hidden tab's `setInterval` is throttled to roughly once a minute under
Chrome's intensive throttling, and a hidden tab is *exactly* where the viewer is when
a callout matters — so "hear it within three seconds" is unreachable by polling from
the one tab that is not in front. Polling (`FOCUS_POLL_MS`) exists only as the
fallback for when the stream cannot be established at all.

### What it locks on to

The **frontmost application**, re-read with a fresh query every single tick. Never
from a cached notification API: in a long-lived process those go stale and cheerfully
report the first application they ever saw, forever — a watchdog that is certain you
are working is worse than no watchdog.

When that application is Chrome-family it also locks the active **tab, by the URL's
host only**. Site-level is the honest granularity: a single-page app's path changes on
every click, so locking the full URL would report a drift for using the very site you
are supposed to be on. The live loop proves this by walking `#one`, `#two/deep`,
`#three?q=1` on the locked host and asserting zero drifts.

One deliberate deviation from the spec, per platform:

| | how the frontmost app is read |
|---|---|
| **Windows** | three Win32 calls through `ctypes` — `GetForegroundWindow` → `GetWindowThreadProcessId` → `QueryFullProcessImageNameW`, plus `GetWindowTextW` for the title |
| **macOS** | `osascript` for the frontmost bundle id, and for a browser, the active tab's URL directly |
| **Linux** | `xdotool`, and it says plainly when that is not installed rather than guessing |

`GetForegroundWindow` **is** the fresh query the spec asks for — a syscall that
answers about *now*, with nothing between the server and the window manager that could
hold a stale answer. It is also about a thousand times cheaper than spawning a shell
1,800 times in a half-hour session. Windows has no bundle ids, so the process's own
image name is the honest equivalent: it is what the OS considers the application's
identity.

The active tab's URL comes from Chrome's **DevTools endpoint**, joined to the OS
foreground window *by title* — because a Chrome window's title is its active tab's
title. That needs Chrome started with:

```
chrome.exe --remote-debugging-port=9222
```

Without it, tab-level locking is simply unavailable. The session still runs, locks the
**application** only, and **says so out loud** — the card reads `app only`. It does
not invent a tab identity, and it does not call an unreadable tab a drift. `GET
/health` reports `focus: {app, browser, cdp, backend}` so you know which of the two
you are getting *before* you commit half an hour to it.

**An ambiguous join is not an answer.** With three browser windows open, two of them
can easily hold tabs with the same title — two blank tabs, or the same site open twice
— and the title is the only join available. Taking the first match would be guessing
which window is in front, and a guess locks a tab you never looked at. So the join
collects every matching tab's host and answers only when there is exactly **one**:
otherwise it returns nothing and the session waits. Two tabs on the same *host* are
not an ambiguity, which is a second reason site-level is the right granularity.

### When it decides — and it is not when you click

The FOCUS button lives in the Jarvis tab. So the surface in front of you at the moment
of the click is the one surface you are *guaranteed* to leave, and a session that
locked it would read your real work as a drift three seconds in. Locking at the click
is therefore not a shortcut, it is a bug.

Instead the lock is **deferred**. The session starts in `arming`, watches nothing, and
says so:

> "Thirty minutes, sir. Go to what you're working on and I'll lock on there. And what
> are we focusing on?"

The target is then the first surface that is **not** home base and that you are still
on `SETTLE_TICKS` (2) consecutive ticks later. When it decides, it says **"Locked on,
sir."** — four words, because a wrong lock has to be *audible* at the moment it
happens rather than inferred from a strange callout three minutes later. If it had to
settle for the application alone, that line gains a sentence saying so; the *absence*
of a caveat is how you know the site was locked too.

Four separate refusals hold that together, and every one of them exists because the
alternative is a wrong lock:

| it will not settle | because |
|---|---|
| at home base | that is the tab you are about to leave |
| on an unreadable read | the viewer's own 3D boot can stall the browser's scripting for a few seconds; that is a reason to wait, not to lock whatever answered first |
| on one tick | alt-tabbing *past* a window on the way to the right one must not become the thing you are held to for half an hour |
| on a guess | `TargetReader.settle()` and `settle_here()` are the only two methods that ever assign a target, and the only input either takes is a fresh read it performs itself. There is no method anywhere that accepts a target from outside — so a background window and a second monitor have no way in |

And it does not wait forever. If you never leave the Jarvis tab, then after
`DEFER_APP_ONLY_S` (45 s) it stops deferring and watches the **application** only:

> "You have not left this page in 46 seconds, sir, so I shall watch the application
> and not the site."

A wrong tab lock is worse than no tab lock, so the half that could have been wrong is
the half it throws away. The one case that does *not* wait 45 seconds is a machine with
no DevTools port at all: that is not a transient stall, it is a permanent fact about
the machine, so it settles app-only immediately rather than staging a 45-second pause
to discover something already known.

`deferred` is exposed as a **boolean** in the session state rather than inferred from
`state == "arming"`, so the status line and the debug panel can both say it plainly.
While it is true the card drops its confident clock for a dashed border and reads
`not locked on yet · go to your work`.

### Moving the lock, on purpose

Everything above is inference, and inference is occasionally wrong — you opened the
right tab through a redirect, or the two ticks landed on the wrong window. So there is
an explicit override with no cleverness in it at all. From the surface you want:

> "lock on this tab" · "keep me in this tab" · "this is the tab" · "stay on this tab"
> · "keep me right here" · "okay, I'm gonna need you to keep me in this tab."

Or press the **LOCK THIS TAB** pill on the countdown card, next to pause and end. It
flashes `LOCKED` for `FOCUS_LOCK_FLASH_MS` (1 s) from the *press* rather than from the
reply, because the press is a fact and what happened next arrives out loud.

Either way it locks in **one read** — `settle_here()`, not `settle()`. Making you hold
still for two ticks to prove a sentence you just said would be the machine doubting you
on principle. Three surfaces, three answers:

| said from | what happens |
|---|---|
| a work tab, or any other application | locks it on the spot: **"Locked on, sir."** The drift you were in the middle of is forgiven *silently* — you are not off task, you are telling me what the task is, and "Back. Thank you, sir." on the way past would be the machine taking credit for your correction. `_end_excursion(refund=True)` takes the drift back off the count, seconds and all |
| the Jarvis tab | locks **nothing**. It re-arms the deferred lock: **"Go to it, sir. I'll lock on where you land."** This is the one surface it cannot lock, because it is where the button lives |
| a browser with no readable site | locks the **application**, and says which half is missing. It does not wait here as `settle()` would: you have told it this is the surface, and waiting would be arguing with an instruction |
| a read that fails entirely | changes **nothing**, and says so. A working lock is never thrown away because one look failed |

`"lock on this tab"` is routed **before** the screen share. `SCREEN_RE` matches "this
tab" just as loudly, so whichever is tested first wins, and the one that changes what
is being watched goes first — mid-session, "lock on this tab" means the target, not a
photograph of it. Outside a live session the share keeps every phrase it had.

#### The card trap

A click on the countdown card is what brings that card — and therefore the Jarvis tab —
to the front. So a naive re-target reads the foreground, finds *itself*, and locks the
assistant's own tab: the single worst outcome, reached by the most obvious code.

When the request came from the card (`source: "card"`), or whenever the frontmost
process is our own, the window manager is not asked at all. The **browser** is asked
which of its own tabs is in front, and it answers with the browser in the background:

```
_FRONT_EXPR  =  ((document.visibilityState==='visible')?1:0) + (document.hasFocus()?2:0)
```

`visibilityState` is `'visible'` for the active tab of **every** window, backgrounded or
not; `hasFocus()` narrows that to the frontmost window when the browser is in front, so
it is preferred whenever anything answers to it. Home base is dropped *before a single
question is asked* — the tab you pressed the button in is not a candidate for the tab
you meant — and two distinct work hosts both answering `visible` is a **question, not
an answer**: it re-arms rather than guessing. On macOS there is a direct answer and it
is used instead: `URL of active tab of every window`, front to back.

That needs `Runtime.evaluate`, which the HTTP DevTools endpoint cannot do, so
`focus.py` carries **a WebSocket client in about sixty lines of stdlib** — handshake,
masked client frames, unmasked server frames, one question, socket closed. It runs only
on a re-target, never on the one-second tick, and every failure path returns `None`.
`test_focus_privacy.py` proves it against a real socket speaking the real protocol
(including that it masks its frames, as a client must), not a mock.

#### The assistant knows the recovery

A model asked "how do I move the lock?" will invent a plausible control, and both
plausible answers are ruinous: *bring the tab to the front and press FOCUS* locks the
assistant's own tab, and *end the session and start again* costs you the session. So
the true recovery is in `SYSTEM_PROMPT` **and** `SMALLTALK_PROMPT` — a question about
the timer matches no note, so it lands in the small-talk prompt — along with both
prohibitions, and preflight check 11 asserts all four strings are still there.

### "And what are we focusing on?"

The start line asks a question, so the microphone opens for **one answer, with no wake
word** (`FOCUS_ANSWER_MS`, after `FOCUS_ANSWER_WAIT_MS` so the recogniser does not
hear the assistant and answer on your behalf). Your answer is attached to the running
session as its `intent`.

The reply is **"Noted, sir."** whatever you said. Reading a dictated paragraph back at
someone is not an acknowledgement, it is an echo — and the rule has a number behind it:
past `INTENT_SPOKEN_MAX_CHARS` (44) the intent is still kept and still shown on the
card, but every line that would have recited it falls back to one that does not. Below
it, your own words colour the **first** callout and the **report card**:

> "That is not the invoice importer, sir."
> "Time, sir. On the invoice importer, 23 seconds on target out of 30 minutes planned,
> one drift. 88 percent clean."

Once, not five times — after the opening callout the ordinary pools take over, because
a line that repeats your own sentence at you is a parrot. Filler is never an intent
either: "um", "uh", "well", "stuff", "work" and their friends clean to nothing, so
"That is not uh, sir." cannot happen. The window is the microphone's, deliberately: it
was opened by a spoken question, so it closes on a spoken answer, on the first thought
heard, or on "stop". Typing during it is an ordinary question.

The `intent` is also the **one free-text field in the whole feature**, which is why it
gets its own checks. `FocusSession.set_intent()` is its only writer and is reached only
from the POST body — no reader, no probe and no window title has a path to it. The
privacy test proves that twice: by driving a whole session past every identity-handling
path and asserting the intent is still `""`, and by scanning `focus.py` itself to
assert `self.intent` is assigned in exactly two places.

### Privacy, structurally

Identities are compared and discarded inside the reader. `TargetReader` holds salted,
truncated `blake2b` hashes — per-process, never sent anywhere — and its only output is
a verdict made of booleans. Two structural gates stand between that and the browser:

- **`public_state()` copies from the `PUBLIC_KEYS` whitelist**, so the state the client
  sees is a fixed set of booleans, counters and canned lines. Adding a field is a
  deliberate act; leaking one is not something a careless edit can do.
- **`_say()` refuses any template not in `LINE_REGISTRY`.** A future edit cannot slip
  an f-string of window titles into the spoken queue, because no function will accept
  one.

There is exactly **one** string in the payload that is not a canned line, and it is the
one string that came from you rather than from watching you: the `intent` you dictated.
See ["And what are we focusing on?"](#and-what-are-we-focusing-on) — it has a single
writer, reached only from the POST body.

`test_focus_privacy.py` proves all of it — **222 checks** — by feeding the reader
identities it chose itself and then hunting for them in every byte of every state, in
both JSON spellings, after every step of a whole session. It is deliberately hostile
rather than reassuring: it is not enough for a leak to be *unfamiliar*, because every
string that leaves is also matched against `LINE_REGISTRY` as a filled-in template, so
a hash, a truncation or a base64 of an app name fails too. Preflight check 11 makes the
same assertion against what the server really sent over HTTP, and the live loop makes
it against the real hosts at the exact moment a leak would be most useful to whoever
wanted one.

#### Said out loud, written down nowhere

One thing *is* spoken that is never stored: **the name of the place you drifted into.**

> "Sir, Instagram can wait."
> "Twice into YouTube, sir. It is starting to look deliberate."
> "Third time in Slack, sir. The detours are becoming the project."

That is a deliberate hole in the wall above, so it is drilled as narrowly as it can be.
The name is derived **inside the reader**, from the host or the application string it
already compares — never from a window title, because a title is the document you have
open and that is exactly the granularity this feature refuses to have. It comes back as
one field of one verdict, `look()["label"]`, and only when the verdict has already
established a **readable drift**: a target exists, and what is in front is neither it
nor home base. It is then a local in `tick()`, a field in one sentence, and gone.

Nothing keeps it. `_forget_names()` takes the whole line out of the say queue one tick
after it was delivered (`LABEL_LINE_TTL_S`, 6 s — several times what delivery needs, far
less than a record), and forces the same scrub when a session ends, since an ended
session never ticks again. So the name is in no key, no counter, no report card and no
ledger; the queue is a delivery buffer, not a transcript.

The promise is therefore not *"it never names where you were"* — it does, out loud, in
the moment, which is the entire point. The promise is that **nothing keeps a record**,
and `NAME_DRIFTS = False` at the top of `focus.py` turns even the speaking off: no line
containing a name can then be reached at all, because `_emit()` refuses those templates.

The test for this could be fooled by a lazy author, so it is written not to be: it
drives a drift into **a made-up host that appears nowhere in `focus.py`** — not in the
map, not in a comment, not in an example — and then asserts that name is absent from the
state, the report, the ledger, the session's own attributes and the reader's. A test
that grepped for "Instagram" would be searching for a word that is in the source anyway.
It also asserts the opposite for the same reason: that `"instagram"` *is* in the source,
which is why it does not search for it.

### Drifting

An app or tab switch is not a drift until `DRIFT_GRACE_MS` (800 ms) has passed —
alt-tab overshoot is not a moral failing. After that you get a spoken callout drawn
from canned pools that escalate over three tiers: `TIER2_AFTER_DRIFTS` (3) starts
speaking sharply, `TIER3_AFTER_DRIFTS` (6) stops being polite about it. While one
drift persists it repeats every `NAG_DEFAULT_S` (20 s).

**And it names the place.** "That is not the task, sir" is a line you can ignore; "Sir,
Instagram can wait" is one you argue with. The name comes from the surface itself:

| in front of you | spoken as |
|---|---|
| `instagram.com`, `youtube.com` / `youtu.be`, `x.com` / `twitter.com`, `reddit.com`, `tiktok.com`, `netflix.com`, `mail.google.com` | Instagram, YouTube, X, Reddit, TikTok, Netflix, Gmail |
| any other site | the **bare domain** — "Sir, example.com can wait", and `news.bbc.co.uk` → `bbc.co.uk` |
| a desktop application | its display name, from the same string the reader compares: `slack.exe` and `com.tinyspeck.slackmacgap` are both **Slack**, and an unmapped one is title-cased |
| a browser whose site cannot be read | the **browser's** name, which is honest about what is actually known |
| the Jarvis tab | *nothing.* Home base is never named, because it is never a drift |

Each tier has **four** named lines and four nameless ones, not three: a single excursion
at tier three can outlast a pool, and three phrases in rotation stop being a callout by
the second lap and start being a ringtone. The counts are spoken as words for the same
reason — "third time in Slack" is a sentence, "drift number 3 in Slack" is a log entry
read aloud. The **first** callout of a session names both halves when it can:

> "Sir — Instagram does not look like 'the thumbnail sprint' to me."

The nags stay nameless on purpose. The callout thirty seconds ago already said where you
are, and a nag that repeats it every twenty seconds would turn the one thing this feature
refuses to log into the thing it says most often. Where the name goes afterwards — which
is nowhere — is ["Said out loud, written down nowhere"](#said-out-loud-written-down-nowhere).

**"Be harsh with me."** Drill sergeant is a register, not a tier: its own pool, named and
nameless, with no escalation left in it because you asked for the top of it. Still the
butler, simply done softening it — a Jarvis that swears at you is one you switch off, and
a switched-off Jarvis holds you to nothing. "Ease up" puts it back, mid-session. Nothing
else changes: the same drifts are counted the same way, and the ledger cannot tell
afterwards which register they were counted in.

| say | what it does |
|---|---|
| *(anything, once, right after the start line)* | becomes the session's `intent` — no wake word, one answer, "Noted, sir." |
| "call me out every thirty seconds" | sets the nag cadence (`NAG_MIN_S`–`NAG_MAX_S`) |
| "give me fifteen seconds" | snoozes: silence, not absolution — the clock still counts it |
| "it's okay, I'm doing research" | excuses: **refunds** the current excursion and stays quiet until you are back |
| "lock on this tab" / "keep me in this tab" / "this is the tab" | [moves the lock here](#moving-the-lock-on-purpose), in one read, and forgives the drift you were in the middle of without a word about it |
| "be harsh with me" / "drill sergeant" / "call me out properly" | the drill-sergeant register, named and nameless pools, no tiers |
| "ease up" / "be civil" | back to the butler, mid-session |
| "pause" / "carry on" | holds and releases the clock |
| "another five minutes" | extends (`EXTEND_DEFAULT_MIN`, capped at `EXTEND_MAX_MIN`) |
| "how long have I got" | the status line, spoken |
| "I'm done" / "scrap the timer" | finish with a report, or abort with none |

Only `START_RE` may match when no session is running. That is what keeps "give me
fifteen seconds" a snooze *during* a session and an ordinary question to the notes
brain at any other time.

**The Jarvis tab is home base.** Coming back to talk to it is never a drift; that time
goes in its own bucket. The viewer says so itself — a `FOCUS_HOME_BEAT_MS` heartbeat
while `document.hasFocus()`, and an explicit retraction on `blur`. Hence the
three-valued `?home=` parameter: `1` says "this tab has the keyboard right now", `0`
says "it just lost it, forget that I said so", and *absent* says nothing about focus at
all — which is what preflight uses, so asking the question cannot change the answer.

Five buckets are kept — `onTargetS`, `driftS`, `homeS`, `excusedS`, `unknownS` — and
they do not all count the same way. Only on-target and drift decide whether a session
was clean; home, excused and *I could not see* are kept separately rather than being
rounded into whichever total flatters the number. Each tick's `dt` is clamped to
`TICK_S * 5`, so closing a laptop lid cannot dump an hour into a bucket.

### The end

A spoken report card: minutes on target out of planned, the drift count, a clean
percentage, and what that did to the streak.

> Time, sir. 28 minutes on target out of 30 planned, one drift. 93 percent clean.
> That extends your streak to 4.

A session at least `CLEAN_RATIO` (85%) clean grows the streak. `focus-ledger.json`
holds **aggregates only** — `sessions, plannedMinutes, onTargetMinutes, driftMinutes,
drifts, cleanSessions, streak, bestStreak, updated` — and no history: not when, not
how long, and certainly not what you were doing. Nothing shorter than `MIN_LEDGER_S`
(30 s) is written at all, because that is a mis-tap, not a session, and aborting never
records.

### The live loop

```bash
node focus_live.mjs      # needs the server running; Node 24, no npm install
```

The loop the feature had to survive, driven end to end and nothing in it mocked — and
it is the *exact* click flow, in order:

```
click FOCUS in the Jarvis tab  →  hear "go to what you're working on"
  →  answer "what are we focusing on?" out loud  →  switch to the work tab
  →  hear "Locked on, sir."  →  switch away  →  hear the callout within three
  seconds  →  switch back  →  move the lock from all three surfaces it can be
  moved from  →  end the session  →  hear the report
```

It asserts that **nothing is locked at the click** (`deferred: true`, `locked: false`)
and that the lock arrives afterwards, out loud, on the surface you settled on — which
is the whole point of the deferred lock, and would be invisible to a test that only
checked the end state. It launches a **headed** Chrome on the DevTools port (headed is not
optional — the reader asks the window manager which window is in front, and a headless
browser has no window to be in front), opens a work site and a distraction on
genuinely different hosts with genuinely different titles, and switches between them
with real CDP activations and real `Input.dispatchMouseEvent` clicks.

`speechSynthesis.speak` is **wrapped, not stubbed**, so the line is recorded *and*
still comes out of the speakers — you should hear this run. The measured latency is
wall time from the activate call to a new line appearing in the page's own record of
what was spoken: the browser's speaker, not the server's queue. Last run: **63 checks,
0 failed** in 65 seconds, locked on **1,141 ms** after reaching the work tab and the
callout spoken **1,218 ms** after the tab switch, with the viewer as a background tab
throughout.

Five of those checks are about [the name](#said-out-loud-written-down-nowhere), and they
are the reason this file is worth its runtime: the distraction it opened is an unmapped
host, so the callout had to name it **by bare domain** — the run asserts the spoken line
contains `iana.org` and no subdomain, no path and no URL, that **exactly one** line names
it, that no field outside `say` names it anywhere in the payload the browser holds, and
then it polls the page's own state until the naming sentence is *gone* from it. Last run
it was spoken at 1,218 ms and scrubbed **6,162 ms** later, proved against the browser
rather than against the server's memory.

The second half of the run is [moving the lock](#moving-the-lock-on-purpose) from all
three surfaces, because each one has a different right answer: the spoken sentence from
a work tab (which must lock it in one read *and* take the drift back off the count), the
same sentence from the Jarvis tab (which must lock nothing and re-arm), and a real mouse
press on the pill. For the press it opens a **second browser window** first — a tab can
only be `visible` while home base is the thing in front if it belongs to another window,
and that is the entire geometry of [the card trap](#the-card-trap). *Which* host got
locked is then proved the only way that leaves the privacy intact: by behaviour. The
window behind the card stops counting as a drift, and the site that was the target until
the press starts counting as one.

Every spoken-line check **polls** for the line rather than sleeping a fixed interval and
sampling once. That is not fussiness: at a latency of ~1.2 s against a 3 s promise, a
single sample after a fixed wait is a coin toss on which side of it the line lands, and
it will not always come down the same way. It also asserts the drift is *still live* at
the instant of return, so "welcome back" can never be spoken about a drift that quietly
resolved itself while nobody was looking.

What it does **not** assert is an absolute total in any bucket. Settling takes as long
as it takes, and on a desktop with other windows on it a second or two legitimately
lands in the home bucket because the Jarvis window really did come to the front for a
moment. So the path-change check asserts that on-target time *grew* across the
navigations with zero drifts, and logs all four buckets either side of it — a
surprising total is usually the machine being busy, and it is easier to see that than
to guess it.

## The eyes

Click the **eye button** and the webcam becomes a posture sensor. It notices three
things — that you are there, that your head has gone down into your lap, that you are
folding in the chair — and says something dry about the last two. The camera frames
**never leave the machine**.

That is a sentence every product says, so here is the shape that makes it true rather
than stated. The video element, the two MediaPipe landmarkers and every coordinate they
produce live in the tab. What crosses to the server is this, and there is no other
field:

```
POST /eyes   {"cmd": "posture", "present": true, "headDown": false,
              "slouched": false, "ears": true}
          -> {"answer", "viaSession", "tuning", "focus"}
```

Three booleans and a word about the microphone. `handle_eyes()` reads exactly those
four names, so a frame arriving under some other one would change nothing — and the
route reads JSON only, with **no branch that reads bytes at all**. Post a real JPEG to
it and it answers 400 with a sentence about JSON. Nothing in `PUBLIC_KEYS` could hold a
picture, a landmark or a measurement of your face; a boolean saying your head is down
says nothing whatever about what it is down *at*, which is deliberate — "the phone" is
an inference, and the lines that make it are allowed to sound like one.

### It measures you, not a constant

The geometry is a pure function — landmarks in, numbers out, no DOM, no clock, no
fetch — and it is all **relative to your own neutral**. `POSTURE.metrics()` reads face
landmarks 10/152/33/263 and pose 0/11/12 into three ratios: `pitch` (how foreshortened
your chin is), `drop` (how far your nose has fallen toward your shoulder line) and
`sit` (how high in frame your eyes are). The first `EYE_CALIBRATE_MIN` (8) readings
after the camera opens become your baseline, and until it exists the organ says it is
still measuring rather than claiming a posture. Then:

| | threshold | meaning |
|---|---|---|
| head down | `pitch > base × 1.30` or `drop < base × 0.72` | chin foreshortened, or nose fallen to the shoulders |
| slouched | `sit < base × 0.93` and `drop < base × 0.86` | sitting lower *and* sunk into the shoulders |

A tall person, a low desk and a 4:3 laptop camera all shift those raw numbers and none
of them shift the ratios, which is the entire reason the baseline exists.

### The nudges

The page reads at `EYE_READ_MS` (140 ms, ~7 readings a second) and only posts when a
boolean **changes** or `EYE_BEAT_MS` (2 s) has passed, so the traffic is a heartbeat
rather than a log of your body. A posture must hold for `EYE_SUSTAIN_MS` (700 ms)
before it is reported at all — that is what the boolean *means*, and it is why the line
lands inside a second without ever landing early.

The division of labour is the point: **the page owns the camera, the landmarks and the
sustain; the server owns the cooldown, the drift and the valve.** So one nudge, then
`EYE_COOLDOWN_S` (30 s) of quiet however bent you stay — and the cooldown is spent
*last*, after every other refusal, so a nudge that was never said does not cost you the
thirty seconds after it. Absence gets a much longer grace, `EYE_ABSENCE_MS` (12 s),
because glancing at a notification is not leaving. And if the page stops reporting for
`EYE_STALE_S` (6 s) the server reports the eyes **closed**, because a stale boolean is
not a fact: a closed tab cannot leave a posture standing.

Slouch and absence are nudges and nothing more — no drift, no count, no mark on the
report card. A spine is not a decision about the work. **Head down is different**: with
a session running it is a [drift](#drifting), counted on the same books as a tab drift,
with the same tiers and the same escalation, out of its own line pool. The card says
"head down" rather than implying you are in the wrong window (`postureDrift`), and
`tick()` consults the eyes *first* — a head in your lap beats an on-target window and
beats home base, because you are not working either way.

[One nudger per moment](#said-out-loud-written-down-nowhere) is decided in
`note_eyes()` and only there: with a session live the line goes into the say queue,
where every open tab speaks it once; with no session it comes back in the reply and the
tab that posted says it. Never both, never neither. The eye lines carry **no `{label}`**
at all and `spoken_line()` refuses a naming template outright — an organ that watches
your body has nothing it could legitimately name.

### Look at me

"Look at me", "what do you think of my shirt?", "what am I wearing" — these send
**one** frame:

```
POST /look?q=<question>   body: one JPEG frame   ->  {"answer", "kind": "look", "brain"}
```

Same frame discipline as [Sight](#sight): grabbed after the question exists, age
declared and checked, media type sniffed rather than trusted, and the exact frame that
was judged shown beside the answer so the upload is never invisible. `WEBCAM_PROMPT`
tells the model it is looking at *one live webcam photograph of your employer at their
desk*, asks for one to three sentences of dry wit, and says explicitly that this is
**not a picture of their screen**. The notes are not in front of it and a look cites
none.

"What do you think of **this screen**" is not a look. `LOOK_RE` and the screen organ's
matcher are disjoint, and a live check proves it in the page rather than in the regex.

### The relief valve

> "No Jarvis, I need to do something important." · "Give me a minute."

`RELIEF_S` (180 s) of silence, for the eyes *and* the session. It is honest about the
bargain: the clock keeps counting, so the silence costs you the minutes it covers — a
valve that stopped the clock would be a way of never finishing anything. Returning to
neutral clears the session's snooze but **not** the hush, so the three minutes you
asked for are the three minutes you get.

### The ear law

**No organ may turn the microphone on.** An organ may open the conversation; it may
never open the microphone. Opening the camera while the mic is off is therefore *said*,
because that is the moment the rule is felt as a fault rather than a promise:

> "Eyes open, sir. Posture only — no picture of you leaves this machine. My ears are
> off, sir — tap the ear button and just talk."

The eyes are announced the whole time they are open: the button lit, a chip naming the
state. No camera is ever open unannounced, and closing it says so too.

Every tab loads with **`?mute=1`** for testing — the page records what it would have
said instead of speaking it, so a background tab never talks at you and a silence is
still checkable.

### The live loop

```bash
node eyes_live.mjs       # needs the server running; Node 24, no npm install
```

Real headed Chrome, a real (fictional) camera via `--use-fake-device-for-media-stream`,
the viewer at `?mute=1`, and the MediaPipe CDN **blocked on purpose** with
`Network.setBlockedURLs` — which does double duty. It stops the real, face-less detector
from out-voting the recorded postures fed through `__galaxy.eyes.feed()`, and it *is*
the honest-degradation check: with the landmarkers unreachable the organ says it cannot
see and claims no posture at all.

Eleven phases, and the two the request asked for by name:

```
  NUDGE:  "Ah. The lap."                              (+734 ms, of which 700 is the sustain)
  DRIFT:  "Head down, sir. That is not the work."     (+1,053 ms, in the say queue)
  RELIEF: "3 minutes of silence, sir. Go and do the important thing."
          → 3.4 s held bent, nothing said, hushed: true, and the clock still running
```

Last run: **56 checks, 0 failed.** The pools are read out of `focus.py` through a
subprocess rather than copied, so a line this harness recognises is a line that file
actually holds. Two things it learned to stop guessing about, both now waited for
rather than hoped for: the eyes' 30 s cooldown is the *organ's*, so a session starting
inside it is covered by it and a silence there is correct; and a posture cannot be a
new drift while an ordinary one is already in progress, because `_off_target()`
continues an excursion rather than nesting a second inside it.

`preflight.py` check 12 covers the same ground over HTTP, and its centrepiece is a
**smuggling test**: a frame, a JPEG, landmark coordinates, face measurements and two
identities are posted to `/eyes` under the names they would really be sent under, and
the reply is searched for every one of them. It deliberately does *not* pull the relief
valve — a preflight that helped itself to three minutes of your silence to prove
silence works would cost you the thing it is checking — so the six relief phrases are
parsed in-process instead, where they change nothing.

## The screen watch

Say **"watch my screen"**. It shares your whole desktop, and then it costs nothing at
all until the moment it has something to say.

Every five seconds the page shrinks the current frame to a **32×18 grayscale
thumbnail** — 576 numbers — and compares it with the last one. No network, no disk, no
model: a subtraction and a count. While the picture keeps changing, a stillness clock
keeps resetting and the chip goes on saying **"watching · no frame sent"**, which is
counted rather than claimed. When the screen has sat unchanged past **60 seconds**, and
only then, **one** frame goes to the brain with no question attached, an unasked-for
sentence comes back, it is spoken, and the organ shuts up for **three minutes**.

```
GET  /stuck                          -> {"tuning": {...}, "watch": {...}}      free
POST /stuck?stillS=<seconds>   body: one JPEG frame
     -> 200 {"answer", "kind": "nudge", "unasked": true, "spent": true, "saw": {...}}
     -> 429/409/400 {"error", "why", "quiet", "spent": false}                  free
```

### The fraction is the feature

Two thresholds, and the second one is the whole difference between a watch you keep and
a watch you turn off within the hour:

- a **cell** has changed when its luma moved by more than `WATCH_CELL_DELTA` (10), which
  is above the noise a video encoder invents in a still image;
- the **screen** has changed when more than `WATCH_CHANGED_FRACTION` (1.5 %) of the 576
  cells did — about nine of them.

A clock ticking in the corner moves one cell. A blinking cursor moves one. If either of
those reset the stillness clock, the nudge would never arrive and the feature would be a
decoration that happened to compile. Sitting and reading is *exactly* the state this
organ exists to notice, so the arithmetic has to be able to tell reading from typing.

### The page owns the clock, the server owns the purse

The 5 s loop is the page's, because it is free and local and there is no reason to pay
a round trip for a subtraction. But the page measures the stillness; it does not decide
what stillness is worth. Both windows — the 60 s threshold and the 180 s cooldown — are
the server's, held once in `server.py` as `STUCK_STILL_S` and `STUCK_COOLDOWN_S`, handed
to the page on `GET /stuck` when the watch starts, and re-stated on **every** reply
including the refusals. A second copy of a number is a number that will drift, and this
one would drift into either silence or a nagging.

So `POST /stuck` refuses in order of what a refusal costs, cheapest first:

| | | |
|---|---|---|
| the relief valve is open | `429 hushed` | silently |
| the purse is shut | `429 cooldown` | silently |
| the screen is still moving | `409 moving` | silently |
| the bytes are not a fresh JPEG | `400 mismatch/stale/tiny/noframe` | out loud |

The first three never read the body as an image and never reach a model. They are
silent on purpose: a suppressed nudge that announces itself is not a suppressed nudge,
so the reply carries `quiet: true` and the page says nothing. A frame *fault* is spoken,
because a watch that has gone blind while still claiming to watch is worth hearing about.

The relief valve is the eyes' — `focus.EYES.hush_until`, three minutes — and it covers
every organ, this one included. **"No Jarvis, I need to do something important"** buys
silence from the whole assistant, not from one part of it.

### The tab-share trap

A captured single tab can never police tabs. It goes on rendering itself while you
wander off to another one, so the stillness clock would measure a page you are not
looking at; and its top strip is page content, so its own scrolling reads as work. The
picker is therefore opened on Entire Screen by default (`displaySurface: 'monitor'`,
with `selfBrowserSurface: 'exclude'` so watching the watcher is not even on the menu) —
but that is a hint, and a hint can be overruled. So the page asks the **track** what it
actually got, through `getSettings().displaySurface`, rather than assuming it got what
it asked for, and says so:

> "That is a single browser tab, sir, and a tab cannot watch a desk: it carries on
> painting itself while you wander off to another one, and its own scrolling would read
> as work. Say 'watch my screen' again and choose Entire Screen in the picker."

It also listens for `configurationchange`, because the share-switching bar lets you
change surfaces *after* the watch has started, and a refusal that only applies at the
first second is a refusal with a hole in it.

### One share, two jobs

While the watch is running, **"what do you think of this?"** and any other screen
question answer from the *same* share. No second picker, no second red bar, nothing to
grant twice. The share frame around the window keeps its red "this screen is being
captured" ring and gains an amber one for "and it is being diffed every five seconds".

This organ is **screen-only** and never touches the camera; the [eyes](#the-eyes) are
camera-only and never touch the screen. Wanting both is two switches, deliberately —
one switch that opened both would be a switch nobody could describe.

### The face

While it is watching, a small card with the assistant's face pins itself to the top-right
corner of the *real desktop*, over the menu bar and across every Space, through
**Document Picture-in-Picture** — the only route a browser has to a genuinely
always-on-top window. `requestWindow()` needs transient activation and the share picker
has just consumed it, so the card first appears in the page and upgrades itself to the
desktop on your next click. If the browser will not give it a window at all, it says so
rather than pretending:

> "I will not let my face off the page in this browser, sir, so the card stays in the
> corner of the tab."

### Proving it

```bash
python test_watch.py     # 124 checks, 0 failed
node watch_live.mjs      # 51 checks, 0 failed — needs the server; Node 24, no npm install
```

`test_watch.py` is in-process and its first section is the one that matters: the loop is
driven for many ticks and the browser is allowed exactly **two** fetches in the whole
organ, both to `/stuck`. The diff object has no `fetch`, `toBlob`, `createObjectURL` or
`sendBeacon` anywhere in it — the thumbnails cannot leave, by construction rather than by
policy. It also parses the page's own default windows out of `index.html` and compares
them to `server.WATCH.tuning()` exactly, so the two copies cannot drift past a test run.

`watch_live.mjs` drives real Chrome against the **real monitor** with
`--auto-select-desktop-capture-source=Entire screen`, and it runs `--headless=new` on
purpose: a headed run would paint this galaxy's animated 3D scene onto the very screen
being watched and reset the stillness clock forever. Last run:

```
  STILL:  60 s reached on the real monitor (attempt 2; the desk reset the clock 14 times)
  NUDGE:  one frame, 61 KB of 800×500, 24 ms old, one model call, spoken as sent
  COOLDOWN: the same request 1 s later — 429 cooldown, nothing said for 3 s, no second call
  SAME SHARE: "what do you think of this?" answered from it, no second picker, still watching
```

One honest gap, reported rather than papered over: this Chrome will not auto-select a
*tab* capture at all — three ways of asking it to, including a uniquely-titled tab and
dropping the `monitor` hint, all came back `screen:0:0`. So the trap phase in the live
harness sets the trap and says it could not be sprung here; the refusal itself is proved
in `test_watch.py` and by check 13.

`preflight.py` check 13 covers the money over HTTP. It tries four ways to make the
assistant think — a moving screen, a PNG wearing a JPEG's content type, a frame that was
already a minute old, and a request with no picture in it — and asserts the nudge counter
does not move while the refusal counter moves four times. Then it spends the one real
nudge, searches the reply for the frame as raw bytes, as base64 and as a data URL, and
says out loud in its last note that the 180 s cooldown it just started is the price of
having proved the nudge works at all.

## The character

Everything the assistant *is* lives in one block at the top of `server.py`, between
the `THE PERSONA` banner and `end of the persona block`. Four values:

| | |
|---|---|
| `SYSTEM_PROMPT` | how it answers questions about the notes |
| `SMALLTALK_PROMPT` | greetings, jokes, and anything the notes cannot answer |
| `VISION_PROMPT` | how it judges one still frame of your own screen |
| `BOOT_GREETING` | the line the page opens with, served at `GET /persona` |

To make it a pirate or a sardonic librarian instead of a butler, edit those four
and nothing else anywhere in the project. The structural rules hold whoever it is:
only retrieved notes are ever sent to the model, small talk is classified before
anything may move the camera, and the reply is capped at `SPOKEN_MAX_CHARS` before
it is read aloud.

The out-of-scope path matters more than it looks. A question the notes cannot answer
is classified `"chat"` and arrives at the model with **no notes attached**, so
`SMALLTALK_PROMPT` is what stops it answering from its own knowledge — that rule
lives there, not in `SYSTEM_PROMPT`.

### The boot greeting

> Good afternoon, sir. 30 notes indexed, all present and accounted for.

`GET /persona` returns wording only — `{salutation}, sir. {notes} indexed, …`. The
viewer fills `{notes}` from `GRAPH.nodes.length` and `{salutation}` from the
reader's own clock (before 12 morning, before 17 afternoon, otherwise evening; the
small hours count as the tail of the evening). The count is never hardcoded on
either side, so it is right the moment you re-run `build.py`. The greeting is shown
immediately, spoken on your first click like any other line, and passes no note
indexes — so it cannot move the camera.

## Proving where the answer came from

`/chat` returns `nodes` (indexes into `GRAPH.nodes`) and `kind` (`"notes"` or
`"chat"`). The viewer has exactly one function that reads them and decides what the
camera does — `decideCamera()` in `viewer/index.html`. Nothing else moves it.

| sources | what happens |
|---|---|
| `kind: "chat"` | **hold.** Nothing moves, nothing lights, the panel is not touched |
| `kind: "screen"` | **hold.** The answer came from your screen, so it cites no note |
| `kind: "model"` | **hold.** Changing brains is not a claim about any note |
| `kind: "focus"` | **hold.** A callout is about where you are, not about any note |
| 1–3 notes | **fly.** Camera flies to the top source, lights it *and its direct neighbours*, opens its panel |
| 4+ notes (`CLUSTER_MIN`) | **cluster.** Camera does not move at all; exactly the cited notes light up |
| an error | **cluster.** The matched notes light, but nothing flies — there is no answer to prove |

Two supporting decisions make that honest:

- **The `nodes` array is trimmed, not padded.** Keyword scoring always leaves a weak
  tail — ask about payroll and one note scores 25 while six others score 5 for the
  word "policy". Returning a fixed six would make the indexes a lie, and the camera
  is aimed from those indexes. `SCORE_FLOOR_RATIO` (0.30) keeps only notes within
  30% of the best score, so a specific question genuinely resolves to one or two
  notes and a broad one genuinely spreads.
- **Small talk is classified before anything is allowed to move.**
  `classify_question()` in `server.py` peels greetings and filler off the front of
  the message; if nothing substantial is left, or the message is about the assistant
  rather than the notes, it returns `kind: "chat"` with **no** indexes at all. So
  "good morning" and "tell me a joke" cannot reach the camera code even in
  principle. "Thanks! Now what about pricing?" still counts as a real question, and
  a bare follow-up ("why not?") inherits the previous question's context.

The spoken answer stays short and never recites a note — the note is on screen to be
read. `SPOKEN_MAX_CHARS` (260) caps it at a sentence boundary.

## Voice

Browser-native only — `speechSynthesis` out, `webkitSpeechRecognition` in. Nothing
paid, nothing installed. Chrome or Edge; Firefox and Safari have no recognition, so
the mic button disables itself and typing still works.

Answers are spoken in a British English voice when the system has one. Browsers
refuse audio until you have interacted with the page, so the first line waits for
your first click — if an answer lands before then it is held, not lost, and the
status line tells you to click.

The microphone buffers. Speech recognition finalises a phrase every time you pause
for breath, and people pause mid-sentence, so nothing is dispatched on the first
final result. Each new phrase is appended and the clock restarts; only a pause of
`FINISH_MS` (900 ms, one constant at the top of `viewer/index.html`) decides the
thought is over, and then the whole combined sentence goes through the same
`/chat` path as typing. Saying just **"stop"**, "wait", "cancel", "quiet",
"never mind" and the like skips the buffer and fires at once.

`http://127.0.0.1:4700/?mute=1` never speaks. The check lives inside the one
function that speaks, so no code path can route around it — useful for a
background tab you do not want talking at you.

## Controls

| | |
|---|---|
| click a node | fly to it, light its neighbours, open the panel |
| `remember that …` | write a new note and watch it born into the galaxy |
| `switch to <model>` | change the answering brain; `go back to your normal brain` undoes it |
| click the brain chip | the same thing with a mouse — a menu of every model the server will answer to, written names only, and the way home at the bottom |
| *"you're being slow today, fetch something sharper"* | names no model, so the chat brain answers with a `[[brain: …]]` tag and the **server** performs and announces the swap |
| `thirty minutes on this` | start a focus session; `I'm done` ends it with a report card |
| ⌖ (crosshair) | start / end a focus session (`FOCUS_DEFAULT_MIN`, 30) |
| *then go to your work* | nothing is locked at the click — the first surface you stay on for two ticks becomes the target, and you hear **"Locked on, sir."** |
| *then say what it is for* | the mic opens for one answer, no wake word; your words colour the first callout and the report card |
| `lock on this tab` | [move the lock](#moving-the-lock-on-purpose) to whatever you are on now, in one read; from the Jarvis tab it re-arms instead |
| LOCK THIS TAB | the same thing from the countdown card — and it asks the *browser* which tab is in front, because the press is what brought the card there |
| drag / scroll | orbit / zoom (idle rotation resumes after ~5s) |
| right-drag | pan; the idle orbit then circles the new centre, not the origin |
| click a legend row | mute or unmute a folder |
| 🎤 | start / stop listening |
| 🖥 | start / stop sharing your screen (one frame per question, never recorded) |
| 👁 | start / stop the [posture eyes](#the-eyes) — three booleans leave the tab, no frame does |
| `look at me` / `what do you think of my shirt?` | send **one** webcam frame and get one to three dry sentences |
| `no Jarvis, I need to do something important` | three minutes with every nudge off — eyes and screen watch alike; the clock keeps running |
| `watch my screen` | start the [screen watch](#the-screen-watch) — a free 32×18 diff every 5 s, one frame only after 60 s of stillness |
| `stop watching my screen` | end it; the chip, the desktop face and the share it opened all go |
| amber *watching* chip | how many frames have actually been sent, and how long the screen has been still |
| `what do you think of this?` *while watching* | answered from the **same** share — no second picker |
| `/` | focus the ask bar |
| `Esc` | stop the voice and the mic, close the panel |
| `↻` | forget the conversation history |
| `?mute=1` | this tab never speaks |
