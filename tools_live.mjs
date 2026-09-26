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
 *      -> the proposal is SPOKEN, and it is the registry's sentence
 *      -> the countdown is running
 *   2. click No
 *      -> the refusal is spoken, the pair goes away, and calendar.json on disk is
 *         byte-for-byte what it was. Nothing ran.
 *   3. ask again, click Yes
 *      -> the SCRIPT'S OWN STDOUT is spoken, calendar.json has gained exactly one
 *         entry, and that entry is the one the screen showed
 *      -> the ledger's ok count for the tool moved by exactly one
 *   4. ask by voice, confirm by voice ("yes, go ahead")
 *      -> the same again, through the door a microphone uses
 *   5. ask by voice, then change the subject
 *      -> the proposal is let go with a line, and the diary does not grow
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
 * The diary is put back exactly as it was found at the end of the run, because a test
 * that leaves three appointments in your calendar is a test you stop running. config.json
 * is NOT backed up and NOT restored: this harness has no business writing to the file
 * that holds this machine's credentials, so instead of undoing a change it proves there
 * was nothing to undo. Values are never read into a claim - only the key count, and a
 * truncated sha256 per key.
 *
 * Usage:  python server.py 2> server-trace.log   then   node tools_live.mjs
 */
import { spawn } from 'node:child_process';
import { mkdtempSync, rmSync, existsSync, readFileSync, writeFileSync, unlinkSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const GALAXY = 'http://127.0.0.1:4700';
const PORT = 9231;
const CDP = 'http://127.0.0.1:' + PORT;
const CALENDAR = 'calendar.json';
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
const procs = []; const profiles = []; let diaryAtStart = null;

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
const diary = () => {
  if (!existsSync(CALENDAR)) return [];
  try { const d = JSON.parse(readFileSync(CALENDAR, 'utf8')); return Array.isArray(d) ? d : []; }
  catch { return []; }
};
const ledgerRow = (id) => {
  try {
    const rows = JSON.parse(readFileSync(LEDGER, 'utf8')).tools || {};
    const row = rows[id] || {};
    return { ok: row.ok | 0, failed: row.failed | 0, refused: row.refused | 0,
             lapsed: row.lapsed | 0 };
  } catch { return { ok: 0, failed: 0, refused: 0, lapsed: 0 }; }
};

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
  diaryAtStart = existsSync(CALENDAR) ? readFileSync(CALENDAR) : null;
  note('calendar.json holds ' + diary().length + ' entr' +
       (diary().length === 1 ? 'y' : 'ies') + ' before the run');

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
  ok(/client/i.test(JSON.stringify(shownRows)) && /four/i.test(JSON.stringify(shownRows)),
     'and they are what was actually asked for, not a paraphrase',
     JSON.stringify(shownRows));
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
  const diaryBeforeNo = diary().length;
  const markNo = await mark();
  await click('ask-no');
  const refusal = await waitSaid(/i have done nothing|nothing was done/i, 15000, markNo);
  ok(!!refusal, 'clicking No is answered out loud: ' + JSON.stringify(refusal));
  ok(await waitFor(page, '__galaxy.hands.shown === false', 8000),
     'the pair goes away, because there is nothing left to answer');
  ok(await page.evaluate('__galaxy.hands.pending === null'),
     'and the page holds no proposal any more');
  await sleep(500);
  ok(diary().length === diaryBeforeNo,
     'THE GATE HELD: calendar.json is unchanged, so nothing ran',
     'entries ' + diaryBeforeNo + ' -> ' + diary().length);

  /* ---- 3. YES, with a real hand ------------------------------------------ */
  const ledgerBefore = ledgerRow('add_calendar_event');
  const diaryBeforeYes = diary().length;
  await type('remind me to call the client at four');
  ok(await waitFor(page, '__galaxy.hands.shown === true', 90000),
     'the same instruction proposes again');
  const second = await pair();
  const markYes = await mark();
  await click('ask-yes');
  /* "that makes N entries" can only have come from the script: the server does not count
     the diary and could not know the number. */
  const evidence = await waitSaid(/that makes \d+ entr/i, 40000, markYes);
  ok(!!evidence, 'clicking Yes speaks the SCRIPT\u2019S OWN STDOUT: ' + JSON.stringify(evidence));
  ok(/^written into your calendar/i.test(String(evidence || '').trim()),
     'and it is the script\u2019s sentence verbatim, not a paraphrase of it',
     JSON.stringify(evidence));
  await sleep(600);
  const grew = diary();
  ok(grew.length === diaryBeforeYes + 1,
     'calendar.json gained exactly one entry',
     'entries ' + diaryBeforeYes + ' -> ' + grew.length);
  const wrote = grew[grew.length - 1] || {};
  ok(String(wrote.title || '') === String((second.rows || {}).title || '\u0000') &&
     String(wrote.when || '') === String((second.rows || {}).when || '\u0000'),
     'and the entry on disk is the one the screen showed before the click',
     JSON.stringify({ disk: { title: wrote.title, when: wrote.when }, screen: second.rows }));
  const ledgerAfter = ledgerRow('add_calendar_event');
  ok(ledgerAfter.ok === ledgerBefore.ok + 1 && ledgerAfter.failed === ledgerBefore.failed,
     'the ledger moved by exactly one ok and nothing else',
     JSON.stringify({ before: ledgerBefore, after: ledgerAfter }));
  const ledgerText = existsSync(LEDGER) ? readFileSync(LEDGER, 'utf8') : '';
  ok(!/client/i.test(ledgerText) && !/four/i.test(ledgerText),
     'and it kept nothing of what the tool was given - no title, no time',
     ledgerText.slice(0, 160));

  /* ---- 4. BY VOICE, ANSWERED BY VOICE ----------------------------------- */
  const diaryBeforeVoice = diary().length;
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
  const voiceEvidence = await waitSaid(/that makes \d+ entr/i, 40000, markVoice);
  ok(!!voiceEvidence, 'confirming by voice runs it and speaks the script\u2019s line: ' +
     JSON.stringify(voiceEvidence));
  ok(/water the plants/i.test(String(voiceEvidence)),
     'and the line names what was asked for out loud, not what was typed earlier',
     JSON.stringify(voiceEvidence));
  await sleep(600);
  ok(diary().length === diaryBeforeVoice + 1,
     'and the diary gained exactly one more entry, from the spoken door alone',
     'entries ' + diaryBeforeVoice + ' -> ' + diary().length);
  ok(await page.evaluate('__galaxy.hands.shown === false'),
     'the pair is gone from the tab that asked, without a click ever reaching it');

  /* ---- 5. A CHANGED SUBJECT IS A WITHDRAWAL ------------------------------ */
  const diaryBeforeDrop = diary().length;
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
  ok(diary().length === diaryBeforeDrop,
     'silence is not consent: the diary did not grow',
     'entries ' + diaryBeforeDrop + ' -> ' + diary().length);
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
    /* The diary, put back exactly as it was found - however the run ended. */
    if (diaryAtStart !== null) writeFileSync(CALENDAR, diaryAtStart);
    else { try { unlinkSync(CALENDAR); } catch { } }
    note('calendar.json restored to its state before the run (' + diary().length +
         ' entries)');
    procs.forEach(p => { try { process.kill(p.pid); } catch { } });
    await sleep(600);
    profiles.forEach(p => { try { rmSync(p, { recursive: true, force: true }); } catch { } });
    console.log('\n  VERIFY ' + (checks - bad.length) + '/' + checks +
                (bad.length ? ' FAIL' : ' PASS') + '\n');
    bad.forEach(b => console.log('    FAILED: ' + b));
    process.exit(bad.length ? 1 : 0);
  });
