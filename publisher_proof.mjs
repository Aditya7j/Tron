/* PUBLISHER PROOF - the newsletter's two hands, the card that gates the send, and the
 * refusals that are sentences rather than stack traces.
 *
 * WHY .mjs AND NOT .py, which the mandate asked to be told: the central claim here is that
 * `send_newsletter` cannot fire without a prior propose and a boss Yes, and that claim is
 * about the REAL /tools and /execute doors on the running server - the same two routes a
 * page uses. broadcaster_proof.mjs is the house's template for exactly that shape (its §9
 * raises a real slot over POST /tools and photographs the card), and a .py harness would
 * have to either reimplement those doors or import hands.py in-process and prove a weaker
 * thing: that the library refuses, rather than that the DOOR refuses. The predicate half -
 * composition, citation discipline, snippet verification, the subscriber-file refusals -
 * is pure Python and is run here through one python -c per section, which is the same
 * arrangement broadcaster_proof uses for broadcast.py's predicates.
 *
 * NOTHING HERE SENDS AN EMAIL. Every send path in this file is either refused on purpose or
 * driven with google_api.send_message replaced in a subprocess. The live acceptance is a
 * separate, deliberate act by a human - see the report.
 */
import { spawnSync } from 'node:child_process';
import { existsSync, mkdirSync, writeFileSync, readFileSync } from 'node:fs';

const PYTHON =
  'C:/Users/Fullstack Developer/AppData/Local/Programs/Python/Python313/python.exe';
const GALAXY = 'http://127.0.0.1:4700';
const OUT = '_runs/sweep44';

let pass = 0, fail = 0;
const failures = [];
const say = (s) => console.log(s);
function ok(cond, claim, evidence) {
  if (cond) { pass++; say('  ok   ' + claim); } else {
    fail++; failures.push(claim); say('  FAIL ' + claim);
    if (evidence) say('         ' + String(evidence).slice(0, 420));
  }
}
const note = (s) => say('  note ' + s);
const step = (s) => say('\n  \u00b7\u00b7 ' + s);

if (!existsSync(OUT)) mkdirSync(OUT, { recursive: true });

/* One python per section, reading the LAST brace-opening line as JSON - broadcaster_proof's
   own runner, so a module that prints to stderr on import cannot corrupt the payload. */
function python(lines, ms) {
  const r = spawnSync(PYTHON, ['-c', lines.join('\n')],
    { encoding: 'utf8', timeout: ms || 180000, cwd: process.cwd(),
      env: { ...process.env, PYTHONIOENCODING: 'utf-8' } });
  if (r.error) throw new Error('python: ' + r.error.message);
  if (r.status !== 0) {
    throw new Error('python exited ' + r.status + ': ' + (r.stderr || '').slice(-900));
  }
  const out = (r.stdout || '').trim();
  const brace = out.lastIndexOf('\n{');
  try { return JSON.parse(brace >= 0 ? out.slice(brace + 1) : out); } catch (e) {
    throw new Error('python said something that was not JSON: ' + out.slice(-600));
  }
}

/* Run a hand exactly as hands.py runs it: a subprocess, parameters on stdin, one line out. */
function hand(script, params, extra) {
  const boot = [
    'import json, sys, pathlib',
    'sys.dont_write_bytecode = True',
    'sys.path.insert(0, "."); sys.path.insert(0, "tools")',
    ...(extra || []),
    'import importlib.util as iu',
    'spec = iu.spec_from_file_location("h", "tools/' + script + '")',
    'h = iu.module_from_spec(spec); spec.loader.exec_module(h)',
    'code = h.main()',
    'sys.stderr.write("RC=%d\\n" % code)',
  ].join('\n');
  const r = spawnSync(PYTHON, ['-c', boot], {
    encoding: 'utf8', timeout: 180000, cwd: process.cwd(),
    input: JSON.stringify(params || {}),
    env: { ...process.env, PYTHONIOENCODING: 'utf-8' } });
  const m = String(r.stderr || '').match(/RC=(-?\d+)/);
  return { said: String(r.stdout || '').trim(), code: m ? Number(m[1]) : null,
           err: String(r.stderr || '') };
}

async function http(path, init) {
  const res = await fetch(GALAXY + path, init);
  let body = null;
  try { body = await res.json(); } catch (e) { body = null; }
  return { status: res.status, body };
}
const post = (path, obj) => http(path, {
  method: 'POST', headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(obj) });

say('\n  PUBLISHER PROOF - the newsletter, its card, and its refusals');
say('  ' + '-'.repeat(74));

/* =====================================================================================
   1 · THE SEND CANNOT FIRE WITHOUT A CARD - by constant, by source, and through the door
   ===================================================================================== */
step('1 · send_newsletter cannot fire without a propose and a Yes');

const G = python([
  'import json, sys, re, pathlib, inspect',
  'sys.dont_write_bytecode = True',
  'sys.path.insert(0, ".")',
  'import hands, newsletter, jobs',
  'out = {}',
  // -- BY CONSTANT: it is in the registry, so propose() is the only thing that can build a
  //    slot for it, and execute() runs the SLOT and never a request.
  'reg = {t["id"]: t for t in hands.registry()}',
  'out["registered"] = sorted(k for k in reg if "newsletter" in k)',
  'out["sendScript"] = reg.get("send_newsletter", {}).get("script", "")',
  'out["sendParams"] = [p["name"] for p in reg.get("send_newsletter", {}).get("params", [])]',
  'out["caps"] = reg.get("send_newsletter", {}).get("capabilities", [])',
  'out["composeCaps"] = reg.get("compose_newsletter", {}).get("capabilities", [])',
  // -- BY SOURCE: execute() takes its parameters from the slot, and the hand's own source
  //    contains no call that could run itself.
  'ex = inspect.getsource(hands.execute)',
  'out["executeUsesSlot"] = bool(re.search(r"slot\\[.params.\\]", ex))',
  'out["executeTakesParamsFromRequest"] = bool(re.search(r"data\\.get\\(.params.\\)", ex))',
  'raw_hand = pathlib.Path("tools/send_newsletter.py").read_text(encoding="utf-8")',
  // COMMENTS AND DOCSTRINGS OUT BEFORE THE SCAN, which is broadcaster_proof section 1's own
  // lesson learned again: this file EXPLAINS that it holds no smtplib and reaches no hands.*,
  // so a scan over the raw text reads the promise back as the crime. The first run of this
  // proof failed two clauses on exactly that, against code that was correct.
  'TRIPLE = chr(34) * 3',
  'hand = re.sub(TRIPLE + "(?:.|\\n)*?" + TRIPLE, "", raw_hand)',
  'hand = re.sub(r"#.*$", "", hand, flags=re.M)',
  'out["strippedChars"] = len(raw_hand) - len(hand)',
  'out["handCallsExecute"] = bool(re.search(r"hands\\.|propose\\(|execute\\(", hand))',
  'out["handReReadsList"] = "newsletter.subscribers()" in hand',
  'out["handReComposes"] = "newsletter.compose(" in hand',
  'out["handReusesBuild"] = "from send_email import build" in raw_hand',
  'out["handHasSmtp"] = bool(re.search(r"smtplib|SMTP|app_password", hand))',
  // -- AND THE LEDGER KEYS the row needs are whitelisted, additively.
  'out["rowKeys"] = list(jobs.ROW_KEYS)',
  'out["outcomes"] = list(jobs.OUTCOMES)',
  'print(json.dumps(out))',
]);

ok(JSON.stringify(G.registered) === JSON.stringify(['compose_newsletter', 'send_newsletter']),
   'BOTH HANDS ARE IN THE REGISTRY AND NOWHERE ELSE: ' + G.registered.join(', ')
   + ' - which is what puts them behind hands.propose(), because a registry entry in this '
   + 'house is inseparable from the Chain Card',
   JSON.stringify(G.registered));
ok(G.executeUsesSlot === true && G.executeTakesParamsFromRequest === false,
   'BY SOURCE: hands.execute() reads its parameters from the SLOT and never from the request '
   + 'that confirms it - so no body posted to /execute by any tab can substitute a subject, a '
   + 'list or a recipient between the asking and the sending',
   JSON.stringify({ slot: G.executeUsesSlot, request: G.executeTakesParamsFromRequest }));
ok(G.handCallsExecute === false,
   'and the hand itself cannot reach the gate it is behind: there is no hands.*, no propose() '
   + 'and no execute() anywhere in send_newsletter.py, so it has no path to run itself',
   JSON.stringify(G.handCallsExecute));
ok(G.handReusesBuild === true && G.handHasSmtp === false,
   'IT REUSES send_email.py\u2019s OWN SERIALISER - `from send_email import build` - and contains '
   + 'no smtplib, no SMTP and no app password: one Gmail path, one place for the From header '
   + 'to be right',
   JSON.stringify({ build: G.handReusesBuild, smtp: G.handHasSmtp }));
ok(G.handReReadsList === true && G.handReComposes === true,
   'and it re-reads the subscriber list AND re-composes the body at send time rather than '
   + 'trusting what travelled on the card - publish_video\u2019s discipline, applied where the '
   + 'file can be edited inside the 120 seconds the card is up',
   JSON.stringify({ list: G.handReReadsList, compose: G.handReComposes }));

/* A SPECIFIC subject or recipient, which is what publish_video's rule is actually about: its
   own capabilities say "a film" and "the video that was just put up unlisted", so the generic
   NOUN is allowed and the particular THING is not. The first draft of this clause banned the
   words "subject", "recipient" and "subscriber list" outright and failed four honest
   sentences - a capability has to be able to say what KIND of thing it does. What may not
   appear is an address, a quoted title, or a named topic. */
const SPECIFIC = /@|["\u2018\u2019\u201c\u201d]|\bre:\s|\b(?:about|on)\s+(?:react|pricing|useeffect)\b/i;
const allCaps = [...(G.caps || []), ...(G.composeCaps || [])];
const guiltyCaps = allCaps.filter((c) => SPECIFIC.test(c));
ok(!guiltyCaps.length && allCaps.length === 4,
   'NO CAPABILITY SENTENCE NAMES A PARTICULAR SUBJECT OR ADDRESS, in either hand - all '
   + allCaps.length + ' say what KIND of thing they do and none says which. publish_video\u2019s '
   + 'rule, and its own capabilities read the same way: a capability naming a subject would be '
   + 'an invitation to propose a send for a newsletter that was never composed',
   JSON.stringify(guiltyCaps));

for (const key of ['subscribers', 'sent', 'failedCount', 'recipients', 'subject']) {
  ok((G.rowKeys || []).includes(key),
     'the ledger whitelists `' + key + '`, so the row can say what happened per address',
     JSON.stringify(G.rowKeys));
}

/* =====================================================================================
   2 · THE REFUSALS, EACH A SENTENCE AND NOT A STACK TRACE
   ===================================================================================== */
step('2 · a missing, malformed and empty subscriber list, each refused by name');

const R = python([
  'import json, sys, pathlib, tempfile',
  'sys.dont_write_bytecode = True',
  'sys.path.insert(0, ".")',
  'import newsletter',
  'tmp = pathlib.Path(tempfile.mkdtemp())',
  'out = {}',
  'missing = tmp / "nope.json"',
  'out["missing"] = newsletter.subscribers(missing)[1]',
  'bad = tmp / "bad.json"; bad.write_text("{ not json at all", encoding="utf-8")',
  'out["malformed"] = newsletter.subscribers(bad)[1]',
  'shape = tmp / "shape.json"; shape.write_text(json.dumps({"subscribers": "a string"}), encoding="utf-8")',
  'out["wrongShape"] = newsletter.subscribers(shape)[1]',
  'empty = tmp / "empty.json"; empty.write_text(json.dumps({"subscribers": []}), encoding="utf-8")',
  'out["empty"] = newsletter.subscribers(empty)[1]',
  'junk = tmp / "junk.json"',
  'junk.write_text(json.dumps({"subscribers": [{"email": "not-an-address"}, {"email": "x@y.zz"}, {"email": "X@Y.ZZ"}]}), encoding="utf-8")',
  'rows, why = newsletter.subscribers(junk)',
  'out["junkKept"] = [r["email"] for r in rows]',
  'out["junkWhy"] = why',
  // -- THE DIGEST, which is the only form an address may take in anything written.
  'out["digest"] = newsletter.digest("someone@example.com")',
  'out["digestLen"] = len(out["digest"])',
  'out["realList"] = len(newsletter.subscribers()[0])',
  'print(json.dumps(out))',
]);

note('missing   : ' + JSON.stringify(R.missing));
ok(/there is no subscriber list yet - create newsletter_subscribers\.json/.test(R.missing),
   'A MISSING LIST IS REFUSED BY NAME, with the filename and the shape in the sentence: "'
   + String(R.missing).slice(0, 110) + '..." - not a FileNotFoundError',
   JSON.stringify(R.missing));
ok(/is not readable as a subscriber list/.test(R.malformed)
   && /is not readable as a subscriber list/.test(R.wrongShape),
   'A MALFORMED one is too, and so is a right-shaped file with the wrong type inside it - '
   + 'both get the same named refusal rather than a ValueError or a TypeError',
   JSON.stringify({ malformed: R.malformed, wrongShape: R.wrongShape }));
ok(/no usable address in it/.test(R.empty),
   'and an EMPTY list is a different sentence from a missing one, because they are different '
   + 'problems: "' + String(R.empty).slice(0, 80) + '..."',
   JSON.stringify(R.empty));
ok(JSON.stringify(R.junkKept) === JSON.stringify(['x@y.zz']) && !R.junkWhy,
   'AND ONE TYPO DOES NOT STOP THE LIST: a malformed entry is skipped, a case-duplicate is '
   + 'dropped, and the count that survives is the count that will actually be written to - '
   + 'kept ' + JSON.stringify(R.junkKept) + ' out of three',
   JSON.stringify({ kept: R.junkKept, why: R.junkWhy }));
ok(R.digestLen === 16 && /^[0-9a-f]{16}$/.test(R.digest),
   'and an address in anything WRITTEN is a 16-character sha256 prefix - the standing law, '
   + 'applied to other people\u2019s addresses, which are worse to leak than the boss\u2019s own',
   JSON.stringify(R.digest));

/* =====================================================================================
   3 · THE COMPOSER: no citation, no newsletter - and no invented code, ever
   ===================================================================================== */
step('3 · a newsletter with nothing behind it is refused, and no code is invented');

const C = python([
  'import json, sys',
  'sys.dont_write_bytecode = True',
  'sys.path.insert(0, ".")',
  'import newsletter',
  'out = {}',
  // -- NO CITED HITS AT ALL.
  'out["noGround"] = newsletter.compose("a subject nothing in the notes covers", cited=[])["why"]',
  'out["noTopic"] = newsletter.compose("")["why"]',
  // -- HITS THAT CARRY NO ID are not citations: the provenance line would have nothing behind it.
  'out["idless"] = newsletter.compose("x", cited=[{"text": "words", "id": ""}])["why"]',
  // -- A REAL FIXTURE NOTE WITH TWO FENCED BLOCKS, one of them too long to ship.
  'CODE = "useEffect(() => {\\n  const t = setInterval(tick, 1000);\\n  return () => clearInterval(t);\\n}, []);"',
  'LONG = "x" * 2000',
  'note_text = ("Cleanup runs on unmount.\\n\\n```js\\n" + CODE + "\\n```\\n\\nAnd a long one:\\n\\n```js\\n" + LONG + "\\n```\\n")',
  'fix = [{"id": "aaaabbbbccccdddd#0000", "text": note_text, "score": 0.9}]',
  'kit = newsletter.compose("useEffect cleanup", cited=fix)',
  'out["ok"] = kit["ok"]',
  'out["subject"] = kit["subject"]',
  'out["citedIds"] = kit["citedIds"]',
  'out["citedLine"] = kit["citedLine"]',
  'out["snipN"] = len(kit["snippets"])',
  'out["snipCode"] = kit["snippets"][0]["code"] if kit["snippets"] else ""',
  'out["snipLang"] = kit["snippets"][0]["lang"] if kit["snippets"] else ""',
  'out["snipIsVerbatim"] = bool(kit["snippets"]) and kit["snippets"][0]["code"] in note_text',
  'out["bodyHasCode"] = CODE in kit["body"]',
  'out["bodyHasLong"] = LONG in kit["body"]',
  'out["bodyHasFilename"] = "2026-" in kit["body"] or ".md" in kit["body"]',
  // -- AND A NOTE WHOSE FENCE IS A LIE: the extracted text is not in the source. Simulated by
  //    handing snippets() a hit whose text has no fence at all but whose id suggests code.
  'out["noFenceNoSnippet"] = len(newsletter.snippets([{"id": "z#0", "text": "prose only, no fences here"}]))',
  'out["emptyFence"] = len(newsletter.snippets([{"id": "z#0", "text": "```js\\n\\n```"}]))',
  // -- the casing rule
  'out["subjCased"] = newsletter.subject_for("useEffect cleanup")',
  'out["subjLower"] = newsletter.subject_for("pricing a micro-saas")',
  'print(json.dumps(out))',
]);

note('refusal   : ' + JSON.stringify(C.noGround));
ok(C.noGround === 'I have nothing in your notes about that, sir, so there is no newsletter '
   + 'to write - I will not compose one on a subject your own research does not cover',
   'A NEWSLETTER WITH NO BACKING CITATION IS REFUSED, in these exact words: "' + C.noGround
   + '"',
   JSON.stringify(C.noGround));
ok(/no topic was given/.test(C.noTopic) && C.idless === C.noGround,
   'and so is a topic-less request, and so are hits that carry no id - a provenance line with '
   + 'nothing behind it is the one thing this module refuses hardest',
   JSON.stringify({ noTopic: C.noTopic, idless: C.idless }));

ok(C.ok === true && C.snipN === 1 && C.snipLang === 'js',
   'A FIXTURE NOTE WITH TWO FENCES YIELDS ONE SNIPPET: the short one ships, the 2000-character '
   + 'one is dropped as a file rather than an illustration',
   JSON.stringify({ ok: C.ok, n: C.snipN, lang: C.snipLang }));
ok(C.snipIsVerbatim === true && C.bodyHasCode === true && C.bodyHasLong === false,
   'AND IT IS VERBATIM OUT OF THE NOTE - the shipped snippet is a substring of the note\u2019s own '
   + 'text, checked back against it after extraction, so no line of code in a newsletter is '
   + 'one this house wrote',
   JSON.stringify({ verbatim: C.snipIsVerbatim, inBody: C.bodyHasCode,
                    longDropped: !C.bodyHasLong }));
ok(C.noFenceNoSnippet === 0 && C.emptyFence === 0,
   'a note with no fence yields NO snippet and an empty fence yields none either - zero is a '
   + 'legitimate answer and is never padded with something plausible',
   JSON.stringify({ noFence: C.noFenceNoSnippet, empty: C.emptyFence }));
ok(/^Written from 1 note of my own research\. Source ids: aaaabbbbccccdddd\.$/.test(C.citedLine),
   'THE PROVENANCE LINE NAMES IDS AND COUNTS: "' + C.citedLine + '"',
   JSON.stringify(C.citedLine));
ok(C.bodyHasFilename === false,
   'AND NO FILENAME REACHES THE BODY. A newsletter is public and a dated note filename tells a '
   + 'stranger what the boss was reading and when - the Broadcaster\u2019s rule, same reason',
   JSON.stringify(C.bodyHasFilename));
ok(C.subjCased === 'useEffect cleanup - from my notes'
   && C.subjLower === 'Pricing a micro-saas - from my notes',
   'and the subject capitalises a lower-case opening word while leaving an identifier alone: '
   + JSON.stringify([C.subjCased, C.subjLower]),
   JSON.stringify([C.subjCased, C.subjLower]));

/* =====================================================================================
   4 · THE HANDS AS SUBPROCESSES - the shape hands.py actually runs them in
   ===================================================================================== */
step('4 · both hands, run the way hands.py runs them: stdin in, one line out');

const composed = hand('compose_newsletter.py', { topic: 'useEffect cleanup in React' });
note('compose   : ' + JSON.stringify(composed.said));
ok(composed.code === 0 && /^Drafted '.*', sir - \d+ words, \d+ code snippet/.test(composed.said),
   'THE COMPOSER REPORTS THE SHAPE OF THE DRAFT AND NOT ITS PROSE: "'
   + composed.said.slice(0, 120) + '" - this line is spoken in a room, and the body is what '
   + 'the Chain Card is for',
   JSON.stringify(composed));
ok(!/@/.test(composed.said) && !/\.md\b/.test(composed.said),
   'and it names no address and no filename', JSON.stringify(composed.said));

const noTopic = hand('compose_newsletter.py', {});
ok(noTopic.code === 1 && /^I could not compose that: no topic was given$/.test(noTopic.said),
   'and a topic-less call is one refusal line and exit 1, not a traceback: "' + noTopic.said
   + '"',
   JSON.stringify(noTopic));

/* THE SEND, DRIVEN WITH GMAIL REPLACED. Three subscribers, the middle one refused by the
   transport, so the per-address reporting is exercised rather than asserted about. */
const partial = hand('send_newsletter.py',
  { topic: 'useEffect cleanup in React', subject: 'x', subscribers: 3 },
  [
    'import pathlib, json, tempfile',
    'import newsletter, google_api, jobs',
    'tmp = pathlib.Path(tempfile.mkdtemp())',
    'lst = tmp / "subs.json"',
    'lst.write_text(json.dumps({"subscribers": [{"email": "a@x.test"}, {"email": "b@x.test"}, {"email": "c@x.test"}]}), encoding="utf-8")',
    'newsletter.SUBSCRIBERS_PATH = lst',
    'jobs.LEDGER_PATH = pathlib.Path("_runs/sweep44/_ledger_partial.json")',
    'jobs.LEDGER_PATH.unlink(missing_ok=True)',
    'google_api.access = lambda: ("tok", "connected", "")',
    'google_api.token = lambda: {"email": "boss@x.test"}',
    'SENT = {"n": 0}',
    'def fake_send(raw):',
    '    SENT["n"] += 1',
    '    if SENT["n"] == 2:',
    '        return None, "Gmail refused it (HTTP 400)"',
    '    return {"id": "mid%d" % SENT["n"]}, ""',
    'google_api.send_message = fake_send',
  ]);
note('partial   : ' + JSON.stringify(partial.said));
ok(partial.code === 1
   && /^The newsletter went to 2 of 3 subscribers, sir - 1 did not, the first because /
      .test(partial.said),
   'A PARTIAL SEND IS NEITHER A SUCCESS NOR A FAILURE AND IS SAID AS ITSELF: "'
   + partial.said.slice(0, 130) + '" - exit 1, because two thirds is not done',
   JSON.stringify(partial));
ok(!/@/.test(partial.said),
   'and not one address is in the spoken line - the per-address detail is in the ledger, '
   + 'which is where an audit fact belongs and where it can be a digest',
   JSON.stringify(partial.said));

const PL = JSON.parse(readFileSync(OUT + '/_ledger_partial.json', 'utf8'));
/* `jobs`, which is what jobs._append_ledger actually writes - not `rows`, which is what this
   harness guessed first and then read back as an empty object over a perfectly good row. */
const ledgerRows = Array.isArray(PL) ? PL : (PL.jobs || []);
const nrow = ledgerRows.filter((r) => r && r.name === 'newsletter').slice(-1)[0] || {};
note('ledger    : ' + JSON.stringify(nrow).slice(0, 300));
ok(nrow.outcome === 'failed' && nrow.subscribers === 3 && nrow.sent === 2
   && nrow.failedCount === 1,
   'THE LEDGER ROW SPLITS THEM: 3 subscribers, 2 sent, 1 failed, outcome failed - a partial '
   + 'send recorded as a partial send',
   JSON.stringify(nrow));
ok(Array.isArray(nrow.recipients) && nrow.recipients.length === 3
   && nrow.recipients.filter((r) => r.ok).length === 2,
   'and it carries ONE ENTRY PER ADDRESS, three of them, two ok - so which subscriber missed '
   + 'out is a readable fact and not an inference from a count',
   JSON.stringify(nrow.recipients));
ok((nrow.recipients || []).every((r) => /^[0-9a-f]{16}$/.test(String(r.sha || ''))
                                   && !JSON.stringify(r).includes('@')),
   'AND EVERY ADDRESS IN IT IS A DIGEST: no @ anywhere in the recipients array, which is the '
   + 'standing law holding in the one place a mailing list could most easily leak',
   JSON.stringify(nrow.recipients));
ok(!JSON.stringify(nrow).includes('@'),
   'nor anywhere else in the row', JSON.stringify(nrow).slice(0, 200));

/* AND THE DRIFT CLAUSE: the card said one number, the file holds another. */
const drifted = hand('send_newsletter.py',
  { topic: 'useEffect cleanup in React', subject: 'x', subscribers: 9 },
  [
    'import pathlib, json, tempfile',
    'import newsletter, google_api, jobs',
    'tmp = pathlib.Path(tempfile.mkdtemp())',
    'lst = tmp / "subs.json"',
    'lst.write_text(json.dumps({"subscribers": [{"email": "a@x.test"}]}), encoding="utf-8")',
    'newsletter.SUBSCRIBERS_PATH = lst',
    'jobs.LEDGER_PATH = pathlib.Path("_runs/sweep44/_ledger_drift.json")',
    'jobs.LEDGER_PATH.unlink(missing_ok=True)',
    'google_api.access = lambda: ("tok", "connected", "")',
    'google_api.token = lambda: {"email": "boss@x.test"}',
    'google_api.send_message = lambda raw: ({"id": "mid1"}, "")',
  ]);
note('drift     : ' + JSON.stringify(drifted.said));
ok(drifted.code === 0 && /The card said 9, and the list held 1 when you gave the word/
   .test(drifted.said),
   'THE CARD\u2019S COUNT IS CHECKED AGAINST THE FILE AT SEND TIME AND THE DIFFERENCE IS SPOKEN: "'
   + drifted.said.slice(0, 140) + '" - the file can be edited in the 120 seconds the card is '
   + 'up, and a send to a different list than the one approved must not be silent',
   JSON.stringify(drifted));

/* AND A SEND WITH NO LIST AT ALL IS REFUSED BEFORE GMAIL IS ASKED FOR A TOKEN. */
const listless = hand('send_newsletter.py',
  { topic: 'anything', subject: 'x', subscribers: 1 },
  [
    'import pathlib, tempfile',
    'import newsletter, google_api',
    'newsletter.SUBSCRIBERS_PATH = pathlib.Path(tempfile.mkdtemp()) / "absent.json"',
    'def boom():',
    '    raise AssertionError("google_api.access was called before the list was checked")',
    'google_api.access = lambda: boom()',
    'google_api.send_message = lambda raw: boom()',
  ]);
ok(listless.code === 1 && /^The newsletter did not go: there is no subscriber list yet/
   .test(listless.said),
   'A SEND WITH NO SUBSCRIBER FILE IS REFUSED BEFORE A TOKEN IS EVEN ASKED FOR - the stubs '
   + 'here raise if Gmail is touched, and they were not: "' + listless.said.slice(0, 100)
   + '..."',
   JSON.stringify(listless));

/* =====================================================================================
   5 · NO CREDENTIAL ANYWHERE THE CARD OR THE REGISTRY CAN SHOW
   ===================================================================================== */
step('5 · no credential in the registry, the card, or anything spoken');

const S = python([
  'import json, sys, pathlib, re',
  'sys.dont_write_bytecode = True',
  'sys.path.insert(0, ".")',
  'import hands, newsletter',
  'out = {}',
  'reg = pathlib.Path("tools/registry.json").read_text(encoding="utf-8")',
  'out["regHasSecret"] = bool(re.search(r"gsk_|sk-|AIza|client_secret|refresh_token|app_password|Bearer ", reg))',
  'out["regHasAt"] = "@" in reg',
  'facts = {t["id"]: t for t in hands.registry()}',
  'out["sendKeys"] = sorted(facts["send_newsletter"].keys())',
  'out["noScriptPathLeak"] = facts["send_newsletter"]["script"]',
  // -- WHAT THE CARD WOULD SHOW, built by the real propose() with no server in the way.
  'kit = newsletter.compose("useEffect cleanup in React")',
  'params = {"topic": "useEffect cleanup in React", "subject": kit["subject"],',
  '          "subscribers": kit["subscribers"], "opening": kit["body"][:400],',
  '          "cited": ", ".join(kit["citedIds"]), "snippets": len(kit["snippets"])}',
  'status, payload = hands.propose("send_newsletter", params, door="harness")',
  'slot = payload.get("pending") or {}',
  'out["status"] = status',
  'out["line"] = payload.get("answer") or ""',
  'out["rows"] = [f["name"] for f in slot.get("fields") or []]',
  'out["shownSubs"] = (slot.get("params") or {}).get("subscribers")',
  'out["realSubs"] = kit["subscribers"]',
  'out["cardText"] = json.dumps(slot)',
  'out["cardHasAt"] = "@" in out["cardText"]',
  'out["cardHasSecret"] = bool(re.search(r"gsk_|sk-|AIza|client_secret|refresh_token|Bearer ", out["cardText"]))',
  'hands.cancel(door="harness")',
  'print(json.dumps(out))',
]);

ok(S.regHasSecret === false && S.regHasAt === false,
   'THE REGISTRY CARRIES NO CREDENTIAL AND NOT ONE @ SIGN: no key, no token, no secret, and '
   + 'no address - the subscriber list is a separate file the registry does not name',
   JSON.stringify({ secret: S.regHasSecret, at: S.regHasAt }));
ok(S.status === 200 && /going to \d+ subscriber/.test(S.line),
   'THE REAL propose() RAISES THE CARD and speaks the registry\u2019s own sentence: "'
   + String(S.line).slice(0, 130) + '"',
   JSON.stringify({ status: S.status, line: S.line }));
ok(JSON.stringify(S.rows) === JSON.stringify(['topic', 'subject', 'subscribers', 'opening',
                                              'cited', 'snippets']),
   'and the card has SIX ROWS the boss can read before he answers - topic, subject, '
   + 'subscribers, opening, cited, snippets - because approving something invisible is not '
   + 'approving it',
   JSON.stringify(S.rows));
ok(S.shownSubs === S.realSubs && typeof S.shownSubs === 'number',
   'THE COUNT ON THE CARD IS THE REAL LIST LENGTH AT THE MOMENT IT WAS RAISED: '
   + S.shownSubs + ' = ' + S.realSubs + ' - not a number the proposal carried from somewhere '
   + 'else',
   JSON.stringify({ shown: S.shownSubs, real: S.realSubs }));
ok(S.cardHasAt === false && S.cardHasSecret === false,
   'AND THE CARD ITSELF SHOWS NO ADDRESS AND NO CREDENTIAL - a count, a subject, an opening '
   + 'and note ids. The boss knows who is on his list; the glass does not have to say it',
   S.cardText ? String(S.cardText).slice(0, 200) : '');

/* =====================================================================================
   6 · THROUGH THE REAL DOOR - the claim that matters, over HTTP
   ===================================================================================== */
step('6 · the real /tools and /execute doors on the running server');

const health = await http('/health');
if (health.status !== 200) {
  ok(false, 'the server is answering on 4700 so the real doors can be exercised',
     'GET /health -> ' + health.status);
} else {
  ok(true, 'the server is answering on 4700');

  // (a) /execute with NOTHING pending must refuse. The gate, from the outside.
  await post('/tools', { cmd: 'withdraw', door: 'button' });
  const bare = await post('/execute', { door: 'button', session: 'pub44' });
  ok(bare.status === 409 && (bare.body || {}).refused === 'nothing-pending',
     'WITH NOTHING PENDING, /execute REFUSES: ' + bare.status + ' refused='
     + (bare.body || {}).refused + ' - so there is no door through which send_newsletter can '
     + 'be made to fire without a proposal first. This is the claim, measured at the door '
     + 'rather than asserted in English',
     JSON.stringify(bare.body && bare.body.answer));

  // (b) a proposal is raised over the real route, and the card is read back off /tools.
  const kit = python([
    'import json, sys',
    'sys.dont_write_bytecode = True',
    'sys.path.insert(0, ".")',
    'import newsletter',
    'k = newsletter.compose("useEffect cleanup in React")',
    'print(json.dumps({"subject": k["subject"], "subs": k["subscribers"],',
    '                  "cited": ", ".join(k["citedIds"]), "opening": k["body"][:300],',
    '                  "snips": len(k["snippets"])}))',
  ]);
  const raised = await post('/tools', {
    cmd: 'propose', tool: 'send_newsletter', door: 'button',
    params: { topic: 'useEffect cleanup in React', subject: kit.subject,
              subscribers: kit.subs, opening: kit.opening, cited: kit.cited,
              snippets: kit.snips } });
  const slot = (raised.body || {}).pending || {};
  note('card line : ' + JSON.stringify(String(slot.line || '').slice(0, 150)));
  ok(raised.status === 200 && slot.tool === 'send_newsletter',
     'A PROPOSAL RAISED THROUGH POST /tools STANDS AS send_newsletter, with '
     + ((slot.fields || []).length) + ' rows and ' + slot.expiresInS + 's on the clock',
     JSON.stringify({ status: raised.status, tool: slot.tool }));
  ok(Number(slot.expiresInS) > 0 && Number(slot.ttlS) === 120,
     'and it is on a 120-second clock like every other card in this house',
     JSON.stringify({ ttl: slot.ttlS, left: slot.expiresInS }));
  ok(String((slot.params || {}).subscribers) === String(kit.subs),
     'THE RECIPIENT COUNT ON THE LIVE CARD IS THE REAL LIST LENGTH: ' + kit.subs,
     JSON.stringify(slot.params && slot.params.subscribers));
  ok(!JSON.stringify(slot).includes('@'),
     'and the live card carries no address either', JSON.stringify(slot).slice(0, 160));

  // (c) A STALE ID CANNOT CONFIRM IT. The one-pending slot, from the outside.
  const stale = await post('/execute', { door: 'button', session: 'pub44',
                                         id: 'not-this-proposal' });
  ok(stale.status === 409,
     'AND A CONFIRMATION NAMING A DIFFERENT PROPOSAL CANNOT RUN IT: ' + stale.status
     + ' - a stale tab answering an older question is refused, which is what stops a yes '
     + 'meant for something else from sending a newsletter',
     JSON.stringify(stale.body && stale.body.answer));

  // (d) AND THE HARNESS TAKES ITS CARD AWAY rather than leaving one to lapse in a live house.
  const gone = await post('/tools', { cmd: 'withdraw', door: 'button' });
  const after = await http('/tools');
  const stillPending = ((after.body || {}).state || after.body || {}).pending;
  ok(gone.status === 200 && !stillPending,
     'and the harness withdraws its own card - nothing is left standing in a live house for '
     + 'a later word to confirm',
     JSON.stringify(stillPending));
}

/* =====================================================================================
   the verdict
   ===================================================================================== */
writeFileSync(OUT + '/publisher_card.json',
  JSON.stringify({ rows: S.rows, line: S.line, shownSubs: S.shownSubs }, null, 1));
say('');
say('  ' + '-'.repeat(74));
if (fail) { say('  FAILED:'); for (const f of failures) say('    - ' + f); say(''); }
say('  VERIFY ' + pass + '/' + (pass + fail) + (fail ? ' FAIL' : ' PASS'));
say('');
process.exit(fail ? 1 : 0);
