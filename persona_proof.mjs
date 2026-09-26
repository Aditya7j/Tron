/* THE NAME, AND WHOSE ASSISTANT HE IS - PART D, made falsifiable.
 *
 * The complaint behind this Part was small and it was fatal: the machine had no name of its
 * own. It was called Jarvis because a film was, it introduced itself as an assistant, and
 * asked who the boss was it had nothing to say. PART D gives it a name, a formal address for
 * the boss, a warm one, and one sentence of self-introduction - and then makes them
 * structural, so they cannot drift apart across the eleven places a name appears.
 *
 * WHAT IS BEING PROVED, each with the failure it catches:
 *
 *   THE NAME AT EVERY DOOR HE CAN SEE. /persona's greeting template, the line the page
 *     actually speaks at boot, the window title, the heading and the floating card's title.
 *     Failure mode: a name changed in config.json that reaches the answers and not the
 *     chrome, so the assistant introduces himself as Galaxy inside a window titled Jarvis.
 *   AND IT COMES FROM THE PERSONA BLOCK, not from a string beside each door: the name served
 *     at /persona and the name in the identity answer are compared to each other rather than
 *     to a literal typed into this file. Failure mode: a fixture that passes because the test
 *     and the page contain the same typo.
 *   THE PERSONA REACHES FREE-FORM ANSWERS, which is the half of PART D that is easy to fake.
 *     The four protected classes answer from fixed strings; a persona block that only showed
 *     up there would be a costume worn for four questions. So this asks things that are NOT
 *     protected - they route through retrieval and the brain, `route` is null and the class
 *     is absent - and requires the answer to be in character anyway. Failure mode: "As an AI
 *     language model, I don't have a name."
 *   AND SO DOES THE MANIFEST. Asked for a hand he has not got, he must say plainly that he
 *     has not got it, and offer only hands that are actually in the registry. Failure mode is
 *     the worst one in the file: an assistant who agrees to book a taxi.
 *   THE REGISTER RULE, BOTH WAYS. Warm lines call him Addi; the consent gate keeps "sir";
 *     an identity answer names both, because "who are you" is a question about whose
 *     assistant he is. Failure mode: a machine that says "sir" in every sentence, which is
 *     not deference, it is a tic.
 *   THE OLD NAME IS RETIRED FROM HIS MOUTH AND KEPT IN HIS EAR. He never calls himself
 *     Jarvis - and he still answers to it, because the boss called this machine that for
 *     months and a rename that made him deaf to the old name would be a regression dressed
 *     as a feature. "jarvis who are you" must come back "I am Galaxy".
 *   AND A DOCUMENT IS NOT A NAME. One of his own PDFs is called "Build Your Own Jarvis",
 *     and citing it by title is correct. So the sweep below is specific about what it
 *     forbids - a SELF-name - rather than banning a word he is entitled to read aloud. A
 *     test that banned the word would fail on his own filing.
 *
 * Nothing is written anywhere, and config.json is read for exactly one thing: whether a
 * persona block is present, reported as a count of keys and never as a value.
 *
 * Usage:  python server.py 2> server-trace.log   then   node persona_proof.mjs
 */
import { spawn, spawnSync } from 'node:child_process';
import { mkdtempSync, existsSync, readFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const GALAXY = 'http://127.0.0.1:4700';
/* The absolute path, as every harness on this machine uses: bare `python` here is the
   Microsoft Store stub, which exits without running anything. */
const PYTHON =
  'C:/Users/Fullstack Developer/AppData/Local/Programs/Python/Python313/python.exe';
const PORT = 9243;
const CDP = 'http://127.0.0.1:' + PORT;
const CHROMES = [
  'C:/Program Files/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Google/Chrome/Application/chrome.exe',
  process.env.LOCALAPPDATA + '/Google/Chrome/Application/chrome.exe',
];
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let pass = 0, fail = 0; const failures = [];
const say = (m) => console.log(m);
const ok = (c, claim, detail) => {
  if (c) pass++; else { fail++; failures.push(claim); }
  say((c ? '  ok   ' : '  FAIL ') + claim);
  if (!c && detail) say('         ' + detail);
};
const note = (m) => say('  note ' + m);
const step = (m) => say('\n  ·· ' + m);

async function ask(question, session) {
  const r = await fetch(GALAXY + '/chat', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question, session: session || 'persona-proof' }),
  });
  let body = null;
  try { body = await r.json(); } catch (e) { body = null; }
  return { status: r.status, body: body || {} };
}

/* HE NEVER NAMES HIMSELF WITH THE OLD NAME. Not "the word never appears" - one of his own
   documents is titled with it and he is right to cite it - but "I am Jarvis", "Jarvis here",
   "call me Jarvis", in any casing. This is the sentence shape a rename has to kill. */
const SELF_NAMED = /\b(?:i\s*am|i'm|this\s+is|call\s+me|it\s+is)\s+jarvis\b|\bjarvis\s+here\b/i;

class Page {
  constructor(u) { this.u = u; this.id = 0; this.w = new Map(); }
  open() { return new Promise((res, rej) => {
    this.ws = new WebSocket(this.u);
    this.ws.onopen = () => res(this);
    this.ws.onerror = (e) => rej(new Error('socket: ' + (e.message || 'failed')));
    this.ws.onmessage = (ev) => { const m = JSON.parse(ev.data);
      const f = this.w.get(m.id); if (f) { this.w.delete(m.id); f(m); } }; }); }
  send(method, params) { const id = ++this.id;
    return new Promise((res, rej) => {
      const bomb = setTimeout(() => { this.w.delete(id); rej(new Error(method + ' timed out')); }, 30000);
      this.w.set(id, (m) => { clearTimeout(bomb); res(m); });
      this.ws.send(JSON.stringify({ id, method, params: params || {} })); }); }
  async evaluate(expression) {
    const r = await this.send('Runtime.evaluate',
      { expression, returnByValue: true, awaitPromise: true });
    if (r.result && r.result.exceptionDetails) {
      throw new Error('page threw: ' + r.result.exceptionDetails.text);
    }
    return r.result && r.result.result ? r.result.result.value : undefined;
  }
  async json(e) { return JSON.parse(await this.evaluate('JSON.stringify(' + e + ')') || 'null'); }
  close() { try { this.ws.close(); } catch (e) { /* going anyway */ } }
}
const cdp = async (p) => { const r = await fetch(CDP + p); const t = await r.text();
  try { return JSON.parse(t); } catch (e) { return t; } };
async function waitFor(page, expr, ms = 10000) {
  for (let i = 0; i < ms / 200; i++) {
    try { if (await page.evaluate(expr)) return true; } catch (e) { /* not yet */ }
    await sleep(200);
  }
  return false;
}

say('\n  PERSONA PROOF - his name, the boss\u2019s name, and the register between them');

const health = await (await fetch(GALAXY + '/health').catch(() => null))?.json()
  .catch(() => null) || null;
if (!health || !health.ok) {
  say('\n  the server on 4700 is not answering; start it first: python server.py');
  process.exit(1);
}

/* ---- 0. WHERE THE NAMES COME FROM ------------------------------------------------- */
step('the persona block, as the server serves it');
const persona = await (await fetch(GALAXY + '/persona')).json();
note('/persona: ' + JSON.stringify(persona.greeting.template));
const ASSISTANT = String(persona.assistant || '');
const CALL = String(persona.boss || '');
ok(!!ASSISTANT && !!CALL,
   'THE SERVER PUBLISHES BOTH NAMES: it calls itself "' + ASSISTANT + '" and the boss "' +
   CALL + '" - and everything below is compared against THESE rather than against names ' +
   'typed into this file, so a fixture cannot agree with a typo',
   JSON.stringify(persona));
/* config.json read for one fact, and the fact is a count. The file holds this machine's
   credentials; a proof that printed any part of it would be a worse thing than the drift it
   was looking for. */
let cfgKeys = 0, hasBlock = false;
try {
  const raw = JSON.parse(readFileSync('config.json', 'utf8'));
  hasBlock = !!(raw.persona && typeof raw.persona === 'object');
  cfgKeys = hasBlock ? Object.keys(raw.persona).length : 0;
} catch (e) { note('config.json not readable here: ' + e.message); }
ok(hasBlock && cfgKeys >= 4,
   'AND THE BOSS OWNS THEM: config.json carries a persona block of ' + cfgKeys + ' keys, ' +
   'so his own name is a setting and not a constant in my source. No value from that file ' +
   'is printed by this proof or by any other',
   JSON.stringify({ hasBlock, cfgKeys }));

/* ---- 1. THE NAME AT EVERY DOOR HE CAN SEE ---------------------------------------- */
step('the doors: the greeting, the window, the heading, the card');
ok(persona.greeting.template.indexOf(ASSISTANT) >= 0 &&
   persona.greeting.template.indexOf(CALL) >= 0 &&
   persona.greeting.empty.indexOf(ASSISTANT) >= 0,
   'THE BOOT GREETING IS HIS: both the full template and the no-notes one name ' +
   ASSISTANT + ' and address ' + CALL,
   JSON.stringify(persona.greeting));

const exe = CHROMES.find((p) => existsSync(p));
if (!exe) { say('\n  no Chrome on this machine'); process.exit(1); }
const profile = mkdtempSync(join(tmpdir(), 'persona-'));
/* Muted, deliberately: the boot greeting is the subject here, not the speakers, and a muted
   tab still records every line it would have said with aloud:false. voice_proof owns the
   audible half. */
const chrome = spawn(exe, ['--remote-debugging-port=' + PORT, '--user-data-dir=' + profile,
  '--no-first-run', '--no-default-browser-check', '--window-size=1200,820',
  '--new-window', GALAXY + '/?mute=1'], { detached: true, stdio: 'ignore' });
let target = null;
for (let i = 0; i < 100 && !target; i++) {
  try {
    const l = await cdp('/json/list');
    target = (Array.isArray(l) ? l : []).filter((t) => t.type === 'page')
      .find((t) => String(t.url).includes('127.0.0.1:4700'));
  } catch (e) { /* not up yet */ }
  if (!target) await sleep(300);
}
if (!target) { say('\n  Chrome never came up on the debugging port'); process.exit(1); }
const page = await new Page(target.webSocketDebuggerUrl).open();
await page.send('Runtime.enable');
await page.send('Page.enable');
ok(await waitFor(page, '!!(window.__galaxy && __galaxy.speech)', 30000),
   'the viewer is up');
/* The line the page ACTUALLY said, off the funnel's own record - not the template. A
   greeting composed wrongly from a correct template is still the wrong greeting. */
const spoke = await waitFor(page,
  '__galaxy.speech.said.some(function (e) { return e.text.indexOf("' + ASSISTANT +
  '") >= 0; })', 30000);
const said = await page.json('__galaxy.speech.said');
const greeting = (said.find((e) => e.text.indexOf(ASSISTANT) >= 0) || {}).text || '';
note('the line the page opened with: "' + greeting + '"');
ok(spoke && greeting.indexOf(CALL) >= 0 && !/jarvis/i.test(greeting),
   'AND THE PAGE SAID IT: the composed opening line names ' + ASSISTANT + ', addresses ' +
   CALL + ', and carries no trace of the old name',
   JSON.stringify(said.map((e) => e.text)));
const chromeText = await page.json('({title: document.title,' +
  ' h1: (document.querySelector("h1") || {}).textContent || "",' +
  ' visible: document.body.innerText.slice(0, 4000)})');
ok(!/jarvis/i.test(chromeText.title) && !/jarvis/i.test(chromeText.h1) &&
   !/jarvis/i.test(chromeText.visible),
   'AND SO DOES THE CHROME AROUND IT: the window title "' + chromeText.title +
   '", the heading "' + chromeText.h1.trim() + '" and every visible word on the page are ' +
   'free of the old name - the rename reached the furniture, not only the answers',
   JSON.stringify({ title: chromeText.title, h1: chromeText.h1,
                    hit: (chromeText.visible.match(/.{0,40}jarvis.{0,40}/i) || [])[0] }));
/* The floating card's title is set in code that only runs inside a Document
   Picture-in-Picture window, which needs a gesture and a browser that has the API. Read
   from the source instead, and said so plainly rather than claimed as a live reading: what
   matters is that the string the OS window manager will show is his name. */
const src = readFileSync('viewer/index.html', 'utf8');
const cardTitle = (src.match(/doc\.title\s*=\s*'([^']+)'/) || [])[1] || '';
ok(cardTitle.indexOf(ASSISTANT) === 0,
   'AND THE FLOATING CARD IS TITLED AFTER HIM: the PiP document is titled "' + cardTitle +
   '" - read from the source, because that line only runs inside a card window; desk_proof ' +
   'owns the live one',
   JSON.stringify({ cardTitle }));

/* ---- 2. THE PERSONA REACHES FREE-FORM ANSWERS ------------------------------------ */
step('the unscripted answers: in character with no protected class to help');
/* THE STATE THESE SENTENCES ARRIVE INTO, set explicitly. Measured, not theorised: the first
   green run of this file opened its party answer with "You have changed the subject, sir, so
   I have let that request go" - PART B releasing a proposal that an earlier run of THIS file
   had left standing in the gate. Correct behaviour, wrong test: a release line prepended to
   the answer is words I am about to pattern-match, and a fixture whose first question is
   answered differently depending on whether it was run before is not measuring the
   persona. */
const withdraw = () => fetch(GALAXY + '/tools', {
  method: 'POST', headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ cmd: 'withdraw' }),
}).catch(() => null);
await withdraw();
const PARTY = 'if someone at a party asked what you do for a living what would you say';
const party = await ask(PARTY, 'persona-free');
note('he said: "' + String(party.body.answer || '').slice(0, 220) + '"');
const a = String(party.body.answer || '');
ok(party.body.route == null && !party.body.protected,
   'THIS ONE IS NOT PROTECTED: route ' + JSON.stringify(party.body.route) + ', class ' +
   JSON.stringify(party.body.protected || null) + ' - it went through retrieval and the ' +
   'brain like any other question, which is the only way this section means anything',
   JSON.stringify({ kind: party.body.kind, route: party.body.route,
                    protected: party.body.protected, lookups: party.body.lookups }));
ok(!/language model|\bLLM\b|\bAI assistant\b|as an AI\b|I am an AI\b/i.test(a) &&
   !SELF_NAMED.test(a),
   'AND IT IS STILL IN CHARACTER: no language model, no "as an AI", and he does not ' +
   'name himself with the old name - the persona block is in front of the ORDINARY prompt ' +
   'and not only in front of the four hard classes',
   JSON.stringify(a));
/* THE MANIFEST, READ FROM OUTSIDE. The first draft of this assertion counted how many organ
   families he volunteered and wanted three of four - and it failed on a perfectly good
   answer that mentioned his notes, made a joke about the coffee-roasting schedule it had
   just read, and stopped. That was the fixture over-fitting one sample: which duties a man
   volunteers at a party is not a property of the manifest, and a test that demands a fixed
   list of them fails on wit.
   So the claim is the one with teeth, in two halves. He must ground the answer in at least
   one organ he ACTUALLY has - so the persona cannot be pure atmosphere - and he must claim
   nothing from the list of things this machine has no hand for. The second half is the
   failure that would matter: an assistant who tells a party he books cars and makes calls
   is an assistant who will try. */
const HAS = { 'his notes': /\bnotes?\b|\bfiling\b|\barchive\b/i,
              'the calendar': /\bcalendar\b|\bdiary\b|\bappointments?\b|\bschedule\b/i,
              'correspondence': /\bemail\b|\bwrit(?:e|ing)\b|\bcorrespondence\b/i,
              'the watch': /\btabs?\b|\bscreen\b|\bwatch(?:ing)?\b|\bfocus\b/i };
const grounded = Object.keys(HAS).filter((k) => HAS[k].test(a));
/* Nothing in the registry books a car, dials a telephone, buys anything or plays music, and
   nothing is going to by accident - each of these would need a hand, a proposal line and the
   boss's consent. Any of them in a self-description is invention. */
const HASNT = { 'booking transport': /\b(?:book|order|call|hail)\s+(?:you\s+)?(?:a\s+)?(?:taxi|cab|uber|ride|car|flight)/i,
                'telephony': /\b(?:make|place)\s+(?:a\s+)?(?:phone\s+)?calls?\b|\btext\s+(?:you|them|him|her)\b|\bring\s+them\s+up\b/i,
                'shopping': /\b(?:buy|purchase|order)\s+(?:you\s+)?(?:things|anything|groceries|something\s+online)/i,
                'media and the house': /\bplay\s+(?:you\s+)?(?:music|a\s+song)|\b(?:lights|thermostat|smart\s+home)\b/i };
const invented = Object.keys(HASNT).filter((k) => HASNT[k].test(a));
ok(grounded.length >= 1 && invented.length === 0,
   '       and the living he describes is one he actually has: grounded in ' +
   grounded.join(' and ') + ', and claiming none of the four families this machine has no ' +
   'hand for - no car booked, no call placed, nothing bought, no music played. That is the ' +
   'manifest reaching a free-form answer, and the invention it is there to prevent',
   JSON.stringify({ grounded, invented, a }));

const TAXI = 'could you order me a taxi to the airport';
const taxi = await ask(TAXI, 'persona-free');
note('he said: "' + String(taxi.body.answer || '').slice(0, 220) + '"');
const t = String(taxi.body.answer || '');
/* HOW THIS IS MEASURED, and why not the obvious way. Twice now this file has failed on a
   correct answer because I had written down the phrasings a refusal was allowed to use:
   first a count of organ names, then a list of apologies. "Regrettably not, sir - no taxi
   hand has ever been fitted to me, and I shan't mime one" is a better refusal than anything
   in the pattern it failed. The butler has more ways of saying no than I have patience for,
   and enumerating them tests my vocabulary rather than his conduct.
   So the test is what a refusal DOES: he undertakes nothing, nothing reaches the gate, and
   somewhere in the sentence a negation sits beside the means - the hand, the fitting, the
   being-given, the taxi itself. That last part is proximity rather than phrasing, so any
   arrangement of "no", "not", "never", "shan't" around any word for the means will satisfy
   it, and a cheerful "certainly, I'll order one now" cannot. */
const NEG = /\b(?:not|no|never|nor|n't|shan't|cannot|unable|incapable|beyond|without|lack\w*)\b/gi;
const MEANS = /\b(?:hand|hands|taxi|cab|car|ride|fitted|given|equipped|means|able|among|mine|do that|for that)\b/i;
const refusedNear = [...t.matchAll(NEG)].some((m) =>
  MEANS.test(t.slice(Math.max(0, m.index - 60), m.index + 60)));
const undertook = /\bI(?:'ll|'m| will| shall| have| am| can)\s+(?:now\s+)?(?:book|order|arrange|call|hail|get|sort)/i.test(t);
ok(refusedNear && !undertook,
   'AND WHAT HE CANNOT DO, HE SAYS: asked for a hand that is not in the registry he set a ' +
   'negation beside the means and undertook nothing - measured as conduct, not as phrasing, ' +
   'because the last line of the manifest is "and what you cannot" and he is entitled to ' +
   'say it in his own words',
   JSON.stringify({ refusedNear, undertook, t }));
ok(!/pending|proposal/.test(JSON.stringify(taxi.body.pending || null)) || !taxi.body.pending,
   '       and he did not propose a hand he has not got, which is the same error with a ' +
   'consent card in front of it',
   JSON.stringify(taxi.body.pending || null));

/* ---- 3. THE REGISTER RULE -------------------------------------------------------- */
step('Addi, sir, and both at once when the question is who he serves');
const who = await ask('who am i', 'persona-register');
const wa = String(who.body.answer || '');
ok(wa.indexOf('Aditya') >= 0 && wa.indexOf(CALL) >= 0,
   'AN IDENTITY ANSWER NAMES BOTH: "' + wa + '" - the formal address because the question ' +
   'is whose assistant he is, and the warm one because that is what he calls him',
   JSON.stringify(who.body));
const meta = await ask('can you listen to me', 'persona-register');
const ma = String(meta.body.answer || '');
ok(ma.indexOf(CALL) >= 0 && !/\bsir\b/i.test(ma),
   'A WARM LINE USES ' + CALL + ' AND NOT "sir": "' + ma + '" - one form of address per ' +
   'sentence, which is the rule that stops the deference becoming a tic',
   JSON.stringify(ma));
/* And the formal end of it, off a real consent gate rather than off a prose claim. */
const gate = await fetch(GALAXY + '/tools', {
  method: 'POST', headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ cmd: 'propose', tool: 'selftest',
                         params: { token: 'persona-proof' }, door: 'harness' }),
});
const gj = await gate.json();
const gl = String((gj.pending && gj.pending.line) || gj.answer || '');
note('the gate said: "' + gl + '"');
ok(/\bsir\b/i.test(gl),
   'AND A CONSENT GATE KEEPS "sir": "' + gl + '" - asking his permission is the formal ' +
   'moment the register rule reserves it for',
   JSON.stringify(gj.pending || gj));
/* And taken down again, by the same door that put it up. An abandoned proposal in the gate
   is this project's standing trap: it changes the meaning of the next sentence anybody says
   to him, including the next sentence a harness says. */
await withdraw();

/* ---- 4. RETIRED FROM HIS MOUTH, KEPT IN HIS EAR ---------------------------------- */
step('the old name: he answers to it and never uses it');
const oldName = [
  { say: 'jarvis who are you', wantRoute: 'identity', mustHave: ASSISTANT },
  { say: 'hey jarvis are you there', wantRoute: 'meta', mustHave: CALL },
];
for (const row of oldName) {
  const r = await ask(row.say, 'persona-oldname');
  const ans = String(r.body.answer || '');
  note('"' + row.say + '" -> ' + r.body.route + ' · "' + ans.slice(0, 120) + '"');
  ok(r.body.route === row.wantRoute && ans.indexOf(row.mustHave) >= 0 &&
     !SELF_NAMED.test(ans) && r.body.lookups === 0,
     'HE STILL ANSWERS TO THE OLD NAME AND ANSWERS WITH THE NEW ONE: "' + row.say +
     '" peels to an address, reaches ' + row.wantRoute + ' at zero cost, and comes back ' +
     'naming ' + row.mustHave + ' - the rename took his name back without making him deaf',
     JSON.stringify(r.body));
}
/* AND THE SWEEP. Every answer this file has collected, plus the served strings, checked for
   a SELF-name. Deliberately not a ban on the word: one of his own documents is titled with
   it, and citing a file by its title is correct behaviour. */
const swept = [greeting, a, t, wa, ma, gl, persona.greeting.template, persona.greeting.empty,
               chromeText.title, chromeText.h1];
const selfNamed = swept.filter((s) => SELF_NAMED.test(String(s)));
ok(selfNamed.length === 0,
   'AND HE NEVER CALLS HIMSELF BY IT: ' + swept.length + ' strings swept - the greeting, ' +
   'four answers, the gate line, both templates and the window chrome - and not one says ' +
   '"I am Jarvis". The word itself is not banned, because "Build Your Own Jarvis" is the ' +
   'title of one of his own PDFs and he is entitled to read it out',
   JSON.stringify(selfNamed));
/* THE SAME CLAIM AT THE SOURCE, and this is the assertion that will still be true next
   month. The four answers above prove he did not say the old name THIS time; the source
   proves there is nowhere left for him to say it from. The instrument is name_sweep.py,
   which parses the module and discards docstrings and comment-strings, because in server.py
   the old name is mostly prose EXPLAINING the vocative peel - prose that earns its place -
   while the one live mention that matters most is a triple-quoted regex a line filter
   cannot tell from a docstring. What the parser leaves is the name as the program uses it,
   and the claim is that every remaining use is an EAR: something he listens for. */
const MODULES = ['server.py', 'focus.py', 'hands.py', 'ingest.py', 'say.py'];
const sweepRun = spawnSync(PYTHON, ['name_sweep.py', 'jarvis', ...MODULES],
                           { encoding: 'utf8' });
let live = {};
try { live = JSON.parse(sweepRun.stdout).jarvis; } catch (e) {
  note('name_sweep failed: ' + (sweepRun.stderr || e.message));
}
const hits = MODULES.flatMap((m) => (Array.isArray(live[m]) ? live[m] : [])
  .map((r) => Object.assign({ file: m }, r)));
for (const h of hits) note(h.file + ':' + h.line + '  ' + JSON.stringify(h.text.slice(0, 64)));
/* Each survivor has to be an ear. The assistant-name list is what the peel matches an
   address against; the force-trigger alternation is what lets "jarvis look this up" reach
   the web door. Both are recognition. A line he SPEAKS would be neither, and would land
   here as an unclassified hit. */
const EARS = [
  { file: 'server.py', is: (r) => r.text.toLowerCase() === 'jarvis',
    why: 'the assistant-name list the vocative peel matches an address against' },
  { file: 'server.py', is: (r) => /galaxy\s*\|\s*jarvis\s*\|\s*tron/.test(r.text),
    why: 'the force-trigger alternation, so the old name still opens the web door' },
];
const unexplained = hits.filter((h) => !EARS.some((e) => e.file === h.file && e.is(h)));
ok(hits.length > 0 && unexplained.length === 0,
   'AND AT THE SOURCE IT SURVIVES ONLY IN HIS EARS: across ' + MODULES.length +
   ' server modules the parser finds ' + hits.length + ' live string constants carrying ' +
   'the old name, and both are recognition - ' + EARS.map((e) => e.why).join('; ') + '. ' +
   'Nothing he can utter is built from it. The comments that explain the peel keep the ' +
   'word, deliberately: they are the reason the peel is right',
   JSON.stringify(unexplained));

say('\n  VERIFY ' + pass + '/' + (pass + fail) + (fail ? ' FAIL' : ' PASS'));
if (fail) { say(''); for (const f of failures) say('    FAILED: ' + f); }
page.close();
spawnSync('taskkill', ['/PID', String(chrome.pid), '/T', '/F']);
process.exit(fail ? 1 : 0);
