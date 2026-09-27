/* THE MOMENT OF TRUST, in a real window, with a real hand on a real button.
 *
 * Everything else about the hands can be proved over HTTP, and preflight check 16 does
 * exactly that. This file exists for the one claim HTTP cannot make: that a human being
 * sitting in front of this machine is SHOWN what is about to happen, in words, before
 * anything happens - and that the two answers available to them, the button and the
 * spoken word, do the same thing.
 *
 * So: headed Chrome, no mute, nothing stubbed. The page's funnel - speakLine() - is
 * WATCHED rather than the engine, so every line is recorded AND still comes out of the
 * speakers, whether it is read locally by piper or by the browser. The buttons are pressed
 * with real mouse events at real coordinates, because a synthetic .click() would prove
 * that a handler works and not that a person could reach it. Every claim about a spoken
 * line is POLLED, never slept-and-sampled: a test that sleeps for two seconds and looks
 * once passes on a fast machine and lies on a slow one.
 *
 * The run, in order:
 *
 *   1. type "remind me to call the client at four" into the box, with the keyboard
 *      -> the Yes/No pair appears, carrying the EXACT parameters, read back out of the
 *         rendered DOM rather than out of the reply
 *      -> the ROWS carry the ISO stamp that will travel; the SENTENCE carries the human
 *         reading of that same stamp, and its duration, out loud
 *      -> the proposal is SPOKEN, and it is the registry's sentence
 *      -> the countdown is running
 *   2. click No
 *      -> the refusal is spoken, the pair goes away, and the LEDGER records no run at
 *         all. Nothing was started.
 *   3. ask again, click Yes
 *      -> the SCRIPT'S OWN STDOUT is spoken, and the ledger records exactly one run
 *      -> which sentence that is depends on this machine: connected, it is Google's
 *         receipt with Google's own event id; unconnected, it is the script's refusal
 *         naming the missing road. Both are strings only the SCRIPT knows.
 *   4. ask by voice, confirm by voice ("yes, go ahead")
 *      -> the same again, through the door a microphone uses
 *   5. ask by voice, then change the subject
 *      -> the proposal is let go with a line, and the ledger records no run
 *   6. THE SPOKEN DIAL: ask by voice to be recast in the voice ALREADY IN FORCE, and
 *      confirm by voice
 *      -> the card reads current beside requested, the hand runs, and the sentence that
 *         comes back is the script's own - announced, by design, in the voice it names
 *      -> config.json keeps its key count, its voice_model, and an identical digest of
 *         every other key it holds
 *
 * That last round is deliberately a recast to the voice already speaking. The door has
 * to be proved all the way through to the write - a gate that is only ever tested by
 * refusing is a gate nobody has walked through - and the only recast that can be run
 * against a real config.json without changing this machine is the one that asks for what
 * it already says. The refusals (an unknown name, a voice that is not on this disk, a
 * missing field) are HTTP-shaped and preflight check 16 clause (h) owns them.
 *
 * WHAT THIS HARNESS WRITES: nothing. It used to restore calendar.json at the end, because
 * the calendar hand appended to it; that hand now calls Calendar API v3 and the file is
 * retired, so this file reads it once and asserts it was never touched. The one thing that
 * follows from that is worth saying plainly: on a machine WITH a Google grant, section 3
 * and section 4 each create a real event in the employer's real calendar, approved by a
 * real click, and this harness does not delete them - they are his, and a test that
 * reached into somebody's calendar to tidy up after itself would be a test with a wider
 * licence than the feature it is testing. The disposable probe event, created and deleted
 * inside one run, belongs to google_hands_proof.mjs. config.json
 * is NOT backed up and NOT restored: this harness has no business writing to the file
 * that holds this machine's credentials, so instead of undoing a change it proves there
 * was nothing to undo. Values are never read into a claim - only the key count, and a
 * truncated sha256 per key.
 *
 * Usage:  python server.py 2> server-trace.log   then   node tools_live.mjs
 */
import { spawn } from 'node:child_process';
/* writeFileSync and unlinkSync are gone from this list on purpose: with calendar.json
   retired there is nothing left for this harness to write or delete, and an import it does
   not need is an invitation to start writing again. */
import { mkdtempSync, rmSync, existsSync, readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const GALAXY = 'http://127.0.0.1:4700';
const PORT = 9231;
const CDP = 'http://127.0.0.1:' + PORT;
/* calendar.json IS NOT HERE ANY MORE, and its absence is the point of this comment.
   Until this round the calendar hand appended a line to that file, so the witness for
   "the gate held" was the file's length: No left it alone, Yes made it longer. The hand
   now calls Calendar v3 events.insert, so there is no local file to count - and a harness
   that counted one would be counting a fossil.
   The witness is therefore the LEDGER, which is a better one and always was: it is the
   machine's own record of runs, it distinguishes ok from failed from refused, and it
   cannot be satisfied by a script that wrote a file without being asked. See runs() below.
   The one thing it does NOT witness is what the hand did to the world - so the sections
   below read GET /google and assert the two different true outcomes: with no token, the
   script's own refusal sentence; with one, Google's event id. */
const LEDGER = 'tools-ledger.json';
const CONFIG = 'config.json';
const CHROMES = [
  'C:/Program Files/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Google/Chrome/Application/chrome.exe',
  process.env.LOCALAPPDATA + '/Google/Chrome/Application/chrome.exe',
];
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let checks = 0; const bad = [];
const ok = (c, claim, detail) => {
  checks++; console.log((c ? '  ok   ' : '  FAIL ') + claim);
  if (!c) { bad.push(claim); if (detail) console.log('         ' + detail); }
};
const note = (m) => console.log('  note ' + m);
/* Held out here so the cleanup below runs even if the run dies in the middle: a harness
   that crashes must not leave a browser open or an appointment in someone's diary. */
const procs = []; const profiles = [];
/* Whether this machine has a Google grant, read once from the server before the run and
   printed, because every calendar assertion below has two true outcomes and which one is
   correct is not this harness's choice to make. */
let grant = { state: 'unknown' };
/* THE RETIRED FILE, AS FOUND. Read rather than restored: this harness used to put
   calendar.json back at the end because the hand under test wrote to it, and now it reads
   the file only to prove that nothing did. A harness that still restored it would be
   perfectly capable of hiding the exact regression it should be catching. '\u0000' stands
   for absent, because absent and empty are different states and both are fine. */
const calendarFileAtStart = existsSync('calendar.json')
  ? readFileSync('calendar.json', 'utf8') : '\u0000';

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
      const bomb = setTimeout(() => { this.w.delete(id); rej(new Error(method + ' timed out')); }, 25000);
      this.w.set(id, (m) => { clearTimeout(bomb); res(m); });
      this.ws.send(JSON.stringify({ id, method, params: params || {} })); }); }
  async evaluate(expression, userGesture = false) {
    const r = await this.send('Runtime.evaluate',
      { expression, returnByValue: true, awaitPromise: true, userGesture });
    if (r.result && r.result.exceptionDetails) {
      throw new Error('page threw: ' + r.result.exceptionDetails.text);
    }
    return r.result && r.result.result ? r.result.result.value : undefined;
  }
  async json(e) { return JSON.parse(await this.evaluate('JSON.stringify(' + e + ')') || 'null'); }
  close() { try { this.ws.close(); } catch { } }
}
const cdp = async (p) => { const r = await fetch(CDP + p); const t = await r.text();
  try { return JSON.parse(t); } catch { return t; } };

/* ---- what is on disk, which is the only witness that cannot be stage-managed ---- */
const ledgerRow = (id) => {
  try {
    const rows = JSON.parse(readFileSync(LEDGER, 'utf8')).tools || {};
    const row = rows[id] || {};
    return { ok: row.ok | 0, failed: row.failed | 0, refused: row.refused | 0,
             lapsed: row.lapsed | 0 };
  } catch { return { ok: 0, failed: 0, refused: 0, lapsed: 0 }; }
};
/* HOW MANY TIMES THE SCRIPT HAS ACTUALLY BEEN STARTED. ok + failed only: `refused` counts
   proposals the gate threw out before a subprocess existed and `lapsed` counts ones nobody
   answered, so including either would make "nothing ran" fail on a run where nothing ran.
   This is the number every gate assertion below is written against. */
const runs = (id) => { const r = ledgerRow(id); return r.ok + r.failed; };

/* config.json, described rather than read. Nothing in here returns a value: the key
   count, the voice setting - which is the one thing the round below is about - and a
   truncated sha256 per remaining key, which is enough to notice a change and not enough
   to be a leak. A digest is how you watch a file you are not allowed to look at. */
const digest = (s) => createHash('sha256').update(String(s)).digest('hex').slice(0, 8);
const configFacts = () => {
  let obj = {}, bytes = 0;
  try {
    const raw = readFileSync(CONFIG);
    bytes = raw.length;
    obj = JSON.parse(raw.toString('utf8')) || {};
  } catch { return null; }
  const keys = Object.keys(obj).sort();
  const others = {};
  for (const k of keys) {
    if (k === 'voice_model' || k === 'voice_engine') continue;
    others[k] = digest(JSON.stringify(obj[k]));
  }
  return { bytes, keys: keys.length, names: keys.join(','),
           voice: String(obj.voice_model || ''), engine: String(obj.voice_engine || ''),
           others: JSON.stringify(others), seal: digest(JSON.stringify(others)) };
};
/* 'en_GB-alan-medium' -> 'Alan'. Derived here, and not imported from the tool, so that
   what this file expects to hear is an independent reading of the same name. */
const voiceLabel = (model) => {
  const parts = String(model || '').split('-').filter(Boolean);
  const word = (parts[1] || parts[0] || '').replace(/[^a-z0-9]/gi, '');
  return word ? word[0].toUpperCase() + word.slice(1) : String(model || '');
};

async function waitFor(page, expr, ms = 10000) {
  for (let i = 0; i < ms / 150; i++) {
    try { if (await page.evaluate(expr)) return true; } catch { }
    await sleep(150);
  }
  return false;
}

async function main() {
  console.log('\n  the hands: proposed, read, refused, and then done\n');
  const exe = CHROMES.find((p) => existsSync(p));
  if (!exe) throw new Error('no chrome.exe');
  const health = await (await fetch(GALAXY + '/health')).json();
  note('server up, model ' + (health.model || '?'));

  const profile = mkdtempSync(join(tmpdir(), 'hands-'));
  profiles.push(profile);
  /* HEADED, and NOT muted: the subject of this file is a window a person is looking at
     and a voice they can hear. --autoplay-policy is what lets the first line be spoken
     without waiting for a click, which matters because the FIRST thing spoken here is
     the proposal itself - the sentence a person is about to answer. */
  const chrome = spawn(exe, [
    '--remote-debugging-port=' + PORT, '--user-data-dir=' + profile,
    '--no-first-run', '--no-default-browser-check',
    '--autoplay-policy=no-user-gesture-required',
    '--window-size=1400,940', '--new-window', GALAXY,
  ], { detached: true, stdio: 'ignore' });
  procs.push(chrome);

  for (let i = 0; i < 80; i++) { try { await cdp('/json/version'); break; } catch { await sleep(250); } }
  note('chrome: ' + ((await cdp('/json/version')).Browser || '?'));
  let target = null;
  for (let i = 0; i < 40; i++) {
    const l = await cdp('/json/list');
    target = (Array.isArray(l) ? l : []).filter(t => t.type === 'page')
      .find(t => t.url.includes('127.0.0.1:4700'));
    if (target) break; await sleep(300);
  }
  if (!target) throw new Error('no viewer page');
  const page = new Page(target.webSocketDebuggerUrl);
  await page.open();
  await page.send('Runtime.enable');
  ok(await waitFor(page, '!!(window.__galaxy && window.__galaxy.hands)', 30000),
     'the viewer is up and exposes the hands');
  await waitFor(page, '__galaxy.nodes.length > 0', 20000);
  ok(await page.evaluate('__galaxy.speech.muted') === false,
     'this tab is NOT muted, so every line below is a line that was actually said');

  /* THE FUNNEL, NOT THE ENGINE. Wrapped, not stubbed: recorded AND still spoken.
     speakLine() is the one function in that page that speaks, and it is what is watched
     here - because on the local voice there is no utterance to intercept at all. A wrapper
     around speechSynthesis.speak would have recorded nothing on the piper path and every
     claim below would have failed for want of an instrument, not for want of a voice.
     The funnel announces every line it accepts, whichever engine then reads it, and that
     announcement is the record - one entry per sentence, in the order the page said them. */
  ok(await page.evaluate(`
    (function () {
      if (window.__spoken) return 'already';
      if (!(window.__galaxy && __galaxy.speech && __galaxy.speech.speakLine)) return '';
      window.__spoken = [];
      addEventListener('speakLine', function (ev) {
        window.__spoken.push(String((ev.detail && ev.detail.text) || ''));
      });
      return 'wrapped';
    })()`) !== '',
     'the recorder below is wrapped around the page’s funnel, speakLine(), rather than ' +
     'around speechSynthesis - so it hears the local voice too');
  /* And the page's own six-second record, which catches a line that speak() held back
     because the autoplay policy had not been released yet. Both are consulted: the
     question "was it said" must not be answered by the wrapper alone. */
  const spokenAll = async () => (await page.json('window.__spoken')) || [];
  const heldBack = async () => (await page.json(
    '__galaxy.speech.said.filter(function(s){return !s.aloud}).map(function(s){return s.text})')) || [];
  /* Lines spoken SINCE A MARK, because several of the claims below are about a sentence
     that arrives after another sentence containing many of the same words: the proposal
     says "written into your calendar", and so does the script. Reading the whole history
     and taking the last match would find the proposal and call it evidence - a check
     that passes by looking at the wrong sentence is worse than no check. */
  const mark = async () => (await spokenAll()).length;
  const waitSaid = async (re, ms = 30000, from = 0) => {
    const until = Date.now() + ms;
    while (Date.now() < until) {
      const lines = (await spokenAll()).slice(from).concat(await heldBack());
      const hit = lines.filter((l) => re.test(l)).pop();
      if (hit) return hit;
      await sleep(150);
    }
    return null;
  };

  /* One real click, at the middle of a real element, after scrolling it into view. */
  const click = async (id) => {
    await page.evaluate('document.getElementById(' + JSON.stringify(id) +
                        ').scrollIntoView({block:"center"})');
    await sleep(120);
    const box = await page.json('(function(){var r=document.getElementById(' +
      JSON.stringify(id) + ').getBoundingClientRect();return {x:Math.round(r.left+r.width/2),' +
      'y:Math.round(r.top+r.height/2)};})()');
    for (const type of ['mousePressed', 'mouseReleased']) {
      await page.send('Input.dispatchMouseEvent',
        { type, x: box.x, y: box.y, button: 'left', clickCount: 1 });
    }
    return box;
  };
  /* Typed, with the keyboard, into the box - not handed to ask(). The employer's hands
     are the subject of this file.
     AND THE BOX HAS TO BE SUMMONED FIRST. There is no standing field any more: "/" raises
     the type-line, exactly as a person's left hand does it, and the insert follows into
     whatever the page gave focus to. Pressing the key rather than calling typeLine.raise()
     is the point - a proof that used the door would stop proving the keyboard works. */
  const type = async (text) => {
    for (const t of ['keyDown', 'char', 'keyUp']) {
      await page.send('Input.dispatchKeyEvent', { type: t, key: '/', code: 'Slash',
        text: '/', unmodifiedText: '/', windowsVirtualKeyCode: 191,
        nativeVirtualKeyCode: 191 });
    }
    await sleep(120);
    const up = await page.json('({up: __galaxy.typeLine.up, focused: __galaxy.typeLine.focused})');
    if (!up.up || !up.focused) throw new Error('the slash did not summon the type-line');
    await page.send('Input.insertText', { text });
    for (const type of ['keyDown', 'keyUp']) {
      await page.send('Input.dispatchKeyEvent', {
        type, key: 'Enter', code: 'Enter', windowsVirtualKeyCode: 13,
        nativeVirtualKeyCode: 13, text: type === 'keyDown' ? '\r' : undefined });
    }
  };
  /* Said out loud, through the very door a dictated sentence comes in by. */
  const say = (words) => page.evaluate('void __galaxy.ask(' + JSON.stringify(words) + ')');
  const pair = () => page.json('({shown: __galaxy.hands.shown, label: __galaxy.hands.label,' +
    ' rows: __galaxy.hands.rows, clock: __galaxy.hands.clock,' +
    ' buttons: __galaxy.hands.buttons, pending: __galaxy.hands.pending})');

  await page.evaluate('document.getElementById("reset").click()', true);
  await sleep(800);
  /* THE GRANT, READ BEFORE ANYTHING IS ASKED FOR. Not to decide whether to run - every
     assertion below runs either way - but to decide which sentence is the correct one, and
     to say so in the log so a reader of the log knows which half was exercised. */
  try {
    const r = await fetch(GALAXY + '/google');
    grant = await r.json();
  } catch (e) { grant = { state: 'unknown', why: String(e && e.message) }; }
  const connected = grant && grant.state === 'connected';
  note('the Google grant reads ' + JSON.stringify(grant && grant.state) +
       (grant && grant.email ? ' as ' + grant.email : '') +
       ' - so the calendar hand is expected to ' +
       (connected ? 'WRITE A REAL EVENT' : 'REFUSE, naming the missing road'));
  note('calendar.json is no longer a backend; the ledger is the witness. ' +
       'add_calendar_event has run ' + runs('add_calendar_event') + ' times before this run');

  /* ---- 1. TYPED, and a proposal that shows its work ----------------------- */
  const markOne = await mark();
  await type('remind me to call the client at four');
  const appeared = await waitFor(page, '__galaxy.hands.shown === true', 90000);
  ok(appeared, 'typing an instruction raises the Yes/No pair in the asking tab');
  const first = await pair();
  note('1: ' + JSON.stringify(first && first.label));
  note('   rows: ' + JSON.stringify(first && first.rows));
  ok(!!first.pending && first.pending.tool === 'add_calendar_event',
     'the proposal names the tool from the registry: ' +
     JSON.stringify(first.pending && first.pending.tool));
  const shownRows = first.rows || {};
  const params = (first.pending && first.pending.params) || {};
  ok(Object.keys(shownRows).length >= 2 &&
     Object.keys(params).every((k) => String(shownRows[k]) === String(params[k])),
     'THE MOMENT OF TRUST: every validated parameter is rendered on screen, verbatim',
     JSON.stringify({ shown: shownRows, validated: params }));
  ok(/client/i.test(JSON.stringify(shownRows)),
     'and they are what was actually asked for, not a paraphrase',
     JSON.stringify(shownRows));
  /* THE STAMP AND THE READING, and this is the pair the round changed. The rows carry the
     machine stamp because that is literally what will be sent to Google - a card showing
     "four o'clock" while an ISO timestamp goes over the wire would be a card the employer
     cannot actually check. The SENTENCE carries the human reading, derived by the same
     function the script uses, which is why they cannot disagree.
     Failure mode if this breaks: hands.readings() stopped being called, or the registry's
     template lost its {when} - and the symptom would be a proposal spoken with a literal
     "{when}" in it, or one that reads an ISO stamp out loud to a listener. */
  const stamp = String(shownRows.start || '');
  ok(/^\d{4}-\d{2}-\d{2}(T\d{2}:\d{2}(:\d{2})?)?/.test(stamp),
     'the card shows the ISO stamp that will travel, not the words that were said: ' +
     JSON.stringify(stamp), JSON.stringify(shownRows));
  const composed = String((first.pending && first.pending.line) || '');
  /* Re-derived here on purpose rather than imported: a proof that asked the code under
     test what the right answer was would prove only that it is self-consistent. */
  let reading = '';
  const hhmm = stamp.match(/T(\d{2}):(\d{2})/);
  if (hhmm) {
    const h = +hhmm[1], m = hhmm[2];
    reading = (h % 12 || 12) + ':' + m + ' ' + (h < 12 ? 'am' : 'pm');
  }
  ok(!!reading && composed.indexOf(reading) >= 0,
     'and the SPOKEN line is the human reading of that same stamp - ' +
     JSON.stringify(reading) + ' out of ' + JSON.stringify(stamp),
     JSON.stringify({ stamp, expected: reading, line: composed }));
  ok(composed.indexOf(stamp) < 0 && !/\{[a-z]+\}/.test(composed),
     'the sentence reads no ISO stamp aloud and has no blank left standing in it',
     JSON.stringify(composed));
  ok(/\bminutes\b|\bhour|all day\b/i.test(composed),
     'and it says how LONG, out loud, so a default half hour is never a silent one',
     JSON.stringify(composed));
  ok(/^yes$/i.test(first.buttons.yes.trim()) && /^no$/i.test(first.buttons.no.trim()),
     'the two answers are Yes and No, and nothing else',
     JSON.stringify(first.buttons));
  const proposalLine = await waitSaid(/shall i/i, 20000, markOne);
  ok(!!proposalLine, 'the proposal was SPOKEN, not merely drawn', JSON.stringify(proposalLine));
  const card = await page.evaluate('document.getElementById("a-text").textContent');
  ok(proposalLine === (first.pending && first.pending.line),
     'and the sentence spoken is the registry’s template, filled in - the exact line ' +
     'the server composed',
     JSON.stringify({ spoke: proposalLine, composed: first.pending && first.pending.line }));
  ok(String(card).indexOf(String(proposalLine)) >= 0,
     'the card shows the same words it said, so hearing it and reading it agree',
     JSON.stringify({ card: String(card).slice(0, 120) }));
  ok(/your word/i.test(first.label) && /calendar/i.test(first.label),
     'and the pair is headed by what is being asked for: ' + JSON.stringify(first.label));
  const clockOne = first.clock;
  await sleep(2200);
  const clockTwo = (await pair()).clock;
  ok(/\d/.test(clockOne) && clockOne !== clockTwo,
     'the countdown is running: ' + JSON.stringify(clockOne) + ' -> ' + JSON.stringify(clockTwo));

  /* ---- 2. NO, with a real hand ------------------------------------------- */
  const runsBeforeNo = runs('add_calendar_event');
  const markNo = await mark();
  await click('ask-no');
  const refusal = await waitSaid(/i have done nothing|nothing was done/i, 15000, markNo);
  ok(!!refusal, 'clicking No is answered out loud: ' + JSON.stringify(refusal));
  ok(await waitFor(page, '__galaxy.hands.shown === false', 8000),
     'the pair goes away, because there is nothing left to answer');
  ok(await page.evaluate('__galaxy.hands.pending === null'),
     'and the page holds no proposal any more');
  await sleep(500);
  /* THE GATE HELD, and the witness is the ledger rather than a file the hand no longer
     writes. Failure mode if this breaks: the No door started running the script anyway -
     the single worst defect this file exists to catch - and the tell would be ok+failed
     climbing by one on a click that was supposed to stop everything. */
  ok(runs('add_calendar_event') === runsBeforeNo,
     'THE GATE HELD: the ledger records no run at all, so the script was never started',
     'runs ' + runsBeforeNo + ' -> ' + runs('add_calendar_event') +
     ' (' + JSON.stringify(ledgerRow('add_calendar_event')) + ')');

  /* ---- 3. YES, with a real hand ------------------------------------------ */
  const ledgerBefore = ledgerRow('add_calendar_event');
  await type('remind me to call the client at four');
  ok(await waitFor(page, '__galaxy.hands.shown === true', 90000),
     'the same instruction proposes again');
  const second = await pair();
  const markYes = await mark();
  await click('ask-yes');
  /* TWO SENTENCES, ONE OF WHICH IS TRUE ON THIS MACHINE, and either one proves the same
     thing: that the words spoken after the click came out of the SCRIPT and not out of the
     server. Connected, only the script can know Google's event id. Unconnected, only the
     script knows the road-to-your-calendar refusal - the server has no such string in it.
     Failure mode if this breaks: the server started paraphrasing a tool's outcome, which
     is the failure that would let a machine claim a success it never observed. */
  const receipt = /written into your google calendar/i;
  const refusal2 = /no road to your calendar/i;
  const evidence = await waitSaid(connected ? receipt : refusal2, 60000, markYes);
  ok(!!evidence, 'clicking Yes speaks the SCRIPT\u2019S OWN STDOUT: ' + JSON.stringify(evidence));
  if (connected) {
    ok(/google's id for it is \S+/i.test(String(evidence || '')),
       'and the receipt carries GOOGLE\u2019S OWN EVENT ID, which this machine could not ' +
       'have invented', JSON.stringify(evidence));
  } else {
    ok(/connect google/i.test(String(evidence || '')),
       'and the refusal names its remedy in the same breath - a no that tells you what ' +
       'would make it a yes', JSON.stringify(evidence));
  }
  await sleep(600);
  const ledgerAfter = ledgerRow('add_calendar_event');
  /* THE SCRIPT RAN, EXACTLY ONCE, and which column it landed in is the connection's to
     decide: a refusal is a FAILED run, not a refused proposal, because the subprocess
     really did start, really did read its stdin and really did make a decision. */
  ok(ledgerAfter.ok + ledgerAfter.failed === ledgerBefore.ok + ledgerBefore.failed + 1,
     'the ledger records exactly one run, no more and no fewer',
     JSON.stringify({ before: ledgerBefore, after: ledgerAfter }));
  ok(connected ? (ledgerAfter.ok === ledgerBefore.ok + 1)
               : (ledgerAfter.failed === ledgerBefore.failed + 1),
     'and it landed in the right column: ' + (connected ? 'ok' : 'failed') +
     ', because an unwritten event is not a written one',
     JSON.stringify({ before: ledgerBefore, after: ledgerAfter, connected }));
  ok((existsSync('calendar.json') ? readFileSync('calendar.json', 'utf8') : '\u0000')
     === calendarFileAtStart,
     'AND THE RETIRED FILE WAS NOT TOUCHED: calendar.json is not a backend any more, so a ' +
     'byte written to it would mean a fallback had crept back in',
     JSON.stringify({ existed: existsSync('calendar.json') }));
  const ledgerText = existsSync(LEDGER) ? readFileSync(LEDGER, 'utf8') : '';
  ok(!/client/i.test(ledgerText) && !/four/i.test(ledgerText),
     'and it kept nothing of what the tool was given - no title, no time',
     ledgerText.slice(0, 160));

  /* ---- 4. BY VOICE, ANSWERED BY VOICE ----------------------------------- */
  const runsBeforeVoice = runs('add_calendar_event');
  await say('remind me to water the plants at seven');
  ok(await waitFor(page, '__galaxy.hands.shown === true', 90000),
     'the same request spoken into the microphone proposes the same way');
  const third = await pair();
  note('4: ' + JSON.stringify(third.label));
  note('   rows: ' + JSON.stringify(third.rows));
  ok(/plants/i.test(JSON.stringify(third.rows)),
     'with the spoken details rendered for reading', JSON.stringify(third.rows));
  ok(await page.evaluate('__galaxy.hands.saidYes("yes, go ahead") === true'),
     'the page agrees with the server about what consent sounds like');
  const markVoice = await mark();
  await say('yes, go ahead');
  const voiceEvidence = await waitSaid(connected ? receipt : refusal2, 60000, markVoice);
  ok(!!voiceEvidence, 'confirming by voice runs it and speaks the script\u2019s line: ' +
     JSON.stringify(voiceEvidence));
  if (connected) {
    ok(/water the plants/i.test(String(voiceEvidence)),
       'and the line names what was asked for out loud, not what was typed earlier',
       JSON.stringify(voiceEvidence));
  } else {
    /* Unconnected, the refusal is the same sentence whatever was asked for - so what is
       provable here is that the SPOKEN door ran the hand at all, which is the thing this
       section is actually about. The title is proved on the card above instead. */
    ok(/plants/i.test(JSON.stringify(third.rows)),
       'and the card still shows what was asked for, spoken door or not',
       JSON.stringify(third.rows));
  }
  await sleep(600);
  ok(runs('add_calendar_event') === runsBeforeVoice + 1,
     'and the ledger records exactly one more run, from the spoken door alone',
     'runs ' + runsBeforeVoice + ' -> ' + runs('add_calendar_event'));
  ok(await page.evaluate('__galaxy.hands.shown === false'),
     'the pair is gone from the tab that asked, without a click ever reaching it');

  /* ---- 5. A CHANGED SUBJECT IS A WITHDRAWAL ------------------------------ */
  const runsBeforeDrop = runs('add_calendar_event');
  await say('remind me to renew the insurance on friday');
  ok(await waitFor(page, '__galaxy.hands.shown === true', 90000),
     'one more proposal, to walk away from');
  const markDrop = await mark();
  /* THIS SENTENCE, AND NOT A TIDIER ONE. It is a plain question about the notes that
     happens to contain the verb "say", and that is the whole reason it is here: the amend
     door in server.py once tested for that verb anywhere in the sentence, so this exact
     question over a standing proposal was read as an amendment TO the proposal. The offer
     was neither run nor released, the withdrawal below was never spoken, and the page was
     handed the same pending slot back and drew the card again. A shorter probe - "what is
     react" - passes without ever touching that door. Keep the verb. */
  await say('what do my notes say about coffee');
  const letGo = await waitSaid(/changed the subject|let that request go/i, 60000, markDrop);
  ok(!!letGo, 'changing the subject lets the proposal go, and says so: ' +
     JSON.stringify(letGo));
  await sleep(500);
  ok(runs('add_calendar_event') === runsBeforeDrop,
     'silence is not consent: the ledger records no run',
     'runs ' + runsBeforeDrop + ' -> ' + runs('add_calendar_event'));
  ok(await page.evaluate('__galaxy.hands.pending === null'),
     'and nothing is pending in the page either');

  /* ---- 6. THE SPOKEN DIAL ------------------------------------------------- */
  const before = configFacts();
  ok(!!before, 'config.json is readable, so the claims below have a witness');
  if (before) {
    /* The voice in force, asked for by the name a person says. This is the whole trick
       of the round: the recast that is safe to actually run is the one that asks for the
       voice already speaking, so the door is walked through rather than merely rattled. */
    const label = voiceLabel(before.voice);
    note('6: config.json holds ' + before.keys + ' keys, voice_model ' +
         JSON.stringify(before.voice) + ', other keys seal ' + before.seal);
    const dialLedgerBefore = ledgerRow('set_voice');
    const markDial = await mark();
    await say('switch your voice to ' + label);
    ok(await waitFor(page, '__galaxy.hands.shown === true', 90000),
       'asking out loud to be recast raises the same Yes/No pair');
    const dial = await pair();
    note('   rows: ' + JSON.stringify(dial.rows));
    ok(!!dial.pending && dial.pending.tool === 'set_voice',
       'and it is the set_voice hand behind it, from the registry: ' +
       JSON.stringify(dial.pending && dial.pending.tool));
    /* CURRENT BESIDE REQUESTED. The requested voice came from the brain; the current one
       did NOT - the server overwrites that field from config.json before the proposal is
       composed, because a card whose whole job is being believed cannot carry a model's
       recollection of what this machine sounds like. */
    const dialRows = dial.rows || {};
    ok(String(dialRows.current || '') === label,
       'the card states the voice IN FORCE, read off the disk by the server: ' +
       JSON.stringify(dialRows.current) + ' (config.json says ' + JSON.stringify(label) + ')');
    ok(String(dialRows.voice || '').length > 0 &&
       /voice/i.test(String(dial.pending.line)) && /\?$/.test(String(dial.pending.line).trim()),
       'beside the voice requested, as a question: ' + JSON.stringify(dial.pending.line));
    const dialProposal = await waitSaid(/shall i change the voice/i, 20000, markDial);
    ok(!!dialProposal, 'and the recast is proposed OUT LOUD before anything is written',
       JSON.stringify(dialProposal));

    const markSaidYes = await mark();
    await say('yes, go ahead');
    /* "Speaking as X now, sir." is the script's own stdout and nothing else says it. By
       the time these words are synthesised config.json already names the voice - /say
       re-reads it per chunk - so the sentence is read in the voice it announces. */
    const recast = await waitSaid(/speaking as .+ now, sir/i, 40000, markSaidYes);
    ok(!!recast, 'confirming by voice runs the hand and speaks the script’s own line: ' +
       JSON.stringify(recast));
    ok(new RegExp('speaking as ' + label + ' now', 'i').test(String(recast || '')),
       'and it names the voice it is being read in: ' + JSON.stringify(recast));
    ok(await waitFor(page, '__galaxy.hands.shown === false', 8000),
       'the pair goes, the word having been given');
    const dialLedgerAfter = ledgerRow('set_voice');
    ok(dialLedgerAfter.ok === dialLedgerBefore.ok + 1 &&
       dialLedgerAfter.failed === dialLedgerBefore.failed,
       'the ledger moved by exactly one ok for set_voice and nothing else',
       JSON.stringify({ before: dialLedgerBefore, after: dialLedgerAfter }));

    await sleep(600);
    const after = configFacts();
    ok(!!after && after.keys === before.keys && after.names === before.names,
       'EVERY OTHER KEY SURVIVED: config.json still holds the same ' + before.keys +
       ' keys, by name',
       JSON.stringify({ before: before.keys, after: after && after.keys }));
    ok(!!after && after.seal === before.seal,
       'and their values are untouched - the digest of every key but the voice is ' +
       'identical either side of the write (' + before.seal + ')',
       JSON.stringify({ before: before.others, after: after && after.others }));
    ok(!!after && after.voice === before.voice,
       'the voice this machine speaks in is the voice it spoke in before the run: ' +
       JSON.stringify(after && after.voice));
    ok(!!after && after.engine === 'piper',
       'and the engine came with it, so the announcement is not read in the wrong voice: ' +
       JSON.stringify(after && after.engine));
    const ledgerNow = existsSync(LEDGER) ? readFileSync(LEDGER, 'utf8') : '';
    ok(!new RegExp(before.voice.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'i').test(ledgerNow),
       'and the ledger kept no note of which voice was asked for',
       ledgerNow.slice(0, 160));
  }

  page.close();
}

main().catch((e) => { bad.push('the run itself: ' + e.message); console.log('\n  ERROR ' + e.message); })
  .finally(async () => {
    /* NOTHING TO PUT BACK. This block used to restore calendar.json, because the hand
       under test wrote to it. The hand now writes to Google and this harness only READS
       that file, to prove nothing touched it - so a restore here would be a harness
       quietly repairing the evidence of the regression it exists to find. The events this
       run may have created on the real calendar are not ours to delete either: they are
       the employer's, they were approved one click at a time, and google_hands_proof owns
       the probe event that IS cleaned up. */
    note('calendar.json was read, never written: ' +
         (calendarFileAtStart === '\u0000' ? 'it was absent before the run and still is'
                                           : 'it is byte-for-byte as it was found'));
    procs.forEach(p => { try { process.kill(p.pid); } catch { } });
    await sleep(600);
    profiles.forEach(p => { try { rmSync(p, { recursive: true, force: true }); } catch { } });
    console.log('\n  VERIFY ' + (checks - bad.length) + '/' + checks +
                (bad.length ? ' FAIL' : ' PASS') + '\n');
    bad.forEach(b => console.log('    FAILED: ' + b));
    process.exit(bad.length ? 1 : 0);
  });
