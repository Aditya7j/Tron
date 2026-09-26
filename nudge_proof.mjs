/* THE SILENT NUDGE - the two sentences nobody asked for, and when the voice is allowed.
 *
 * PART C, second half: "Posture and watch nudges during speech or an open ear are caption
 * only; spoken only when idle and ear closed." Two sentences in this page arrive unasked -
 * the posture nudge when he has been hunched over for a minute, and the watch nudge when
 * his screen has not moved - and at their worst both are a voice cutting across the middle
 * of something he is doing on purpose.
 *
 * WHAT IS BEING PROVED, and every one of these names the failure it catches:
 *
 *   IT STILL SPEAKS. Idle, ear shut, audio unlocked: the nudge is SPOKEN, and the line
 *     really went into the one funnel that speaks. The failure mode is the obvious
 *     over-correction - a gate so careful that the nudge never says anything, which is a
 *     feature removed rather than a feature made polite. This is asserted FIRST on purpose.
 *   WHILE THE BUTLER IS READING, CAPTION ONLY - and the line must not have entered the
 *     speech funnel at all, which is checked by its absence from __galaxy.speech.said
 *     rather than by a flag the nudge sets about itself. Failure mode: a second voice on
 *     top of the answer he actually asked for.
 *   AND THE HELD CAPTION WAITS ITS TURN. A nudge held back by speech does not overwrite
 *     the subtitle belonging to the words coming out of the speakers; it captions itself
 *     when the queue runs dry. Failure mode is the frozen-level mistake in text: a subtitle
 *     that disagrees with the audio.
 *   WITH THE EAR OPEN, CAPTION ONLY, IN TOTAL SILENCE. Nothing is being read, nothing is in
 *     flight, and the voice is still withheld - because an open ear means the recogniser is
 *     armed between turns, and a nudge spoken into that is a sentence the microphone hears
 *     and transcribes as HIS. Failure mode: the butler asking himself about his own posture.
 *     This is the one a naive implementation gets wrong, because in that moment the room is
 *     quiet and speaking looks harmless.
 *   WITH AN ANSWER IN FLIGHT, CAPTION ONLY. The queue is empty and the ear is shut, so
 *     every "is anything happening" test based on audio says yes, go ahead - and the answer
 *     he is waiting for is a second away. Failure mode: the nudge that lands in the gap
 *     between the question and the reply.
 *   BOTH REAL CALLERS GO THROUGH THE GATE, read out of the page's own source: the posture
 *     nudge and the watch nudge each call nudgeSpeak() and neither reaches speakLine()
 *     directly. Failure mode is the one that arrives in six months - a third unasked
 *     sentence, added by somebody who never read this file, speaking straight past the rule.
 *   AND THE COUNTERS ACCOUNT FOR EVERY CALL: spoken + held equals the nudges made. A gate
 *     whose own ledger does not add up cannot be used as evidence for anything else here.
 *
 * Headed and NOT muted, because "it was spoken" is a claim about the speakers: a ?mute=1 tab
 * records every line with aloud:false and would make the first assertion unfalsifiable. It
 * talks out loud for a few seconds. It asks the server for audio and for one real answer,
 * and it writes nothing anywhere.
 *
 * Usage:  python server.py 2> server-trace.log   then   node nudge_proof.mjs
 */
import { spawn, spawnSync } from 'node:child_process';
import { mkdtempSync, existsSync, readFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const GALAXY = 'http://127.0.0.1:4700';
const PORT = 9242;
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
      const bomb = setTimeout(() => { this.w.delete(id); rej(new Error(method + ' timed out')); }, 40000);
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

/* A GENUINE GESTURE. document.body.click() does not unlock audio - Chrome wants an event it
   believes came from a human, which over CDP means Input.dispatchMouseEvent. Copied from
   voice_proof for the same reason it exists there: without it, "it was spoken" is never
   true and every assertion below passes for the wrong reason. */
async function realClick(page, x, y) {
  for (const type of ['mousePressed', 'mouseReleased']) {
    await page.send('Input.dispatchMouseEvent',
      { type, x, y, button: 'left', clickCount: 1, buttons: type === 'mousePressed' ? 1 : 0 });
    await sleep(40);
  }
}

/* The whole gate's state in one read, plus the two things it is not allowed to touch. */
const STATE = '({quiet: __galaxy.nudge.quiet, caption: {up: __galaxy.caption.up,' +
  ' text: __galaxy.caption.text}, said: __galaxy.speech.said,' +
  ' queue: __galaxy.voice.queue, draining: __galaxy.voice.draining,' +
  ' earOpen: __galaxy.ear.open, listening: __galaxy.speech.listening,' +
  ' unlocked: __galaxy.speech.unlocked, muted: __galaxy.speech.muted})';

/* Did this exact sentence go into the one funnel that speaks? said[] is written by
   speakLine() itself, so a line that is not in there never got near the engine - which is
   what "caption only" has to mean if it means anything. */
const carried = (s, line) => (s.said || []).some((e) => e.text.indexOf(line) >= 0);
const spokenAloud = (s, line) =>
  (s.said || []).some((e) => e.text.indexOf(line) >= 0 && e.aloud === true);

/* ---- the sentences. The real ones, from the two callers, so the text under test is the
   text he would actually hear. ---- */
const POSTURE = 'Sit back a little, Addi - you have been over the desk for a minute.';
const WATCH = 'Nothing has moved on that screen for four minutes, Addi.';
const ANSWER_Q = 'what is the web gate';

say('\n  NUDGE PROOF - the unasked sentence, and when the voice is allowed');

const health = await (await fetch(GALAXY + '/health').catch(() => null))?.json()
  .catch(() => null) || null;
if (!health || !health.ok) {
  say('\n  the server on 4700 is not answering; start it first: python server.py');
  process.exit(1);
}
note('the server: model ' + health.model + ' · say ' + JSON.stringify(health.say));

const exe = CHROMES.find((p) => existsSync(p));
if (!exe) { say('\n  no Chrome on this machine'); process.exit(1); }
const profile = mkdtempSync(join(tmpdir(), 'nudge-'));
/* NOT muted and headed: the subject of the first assertion is what comes out of the
   speakers. No autoplay flag either - the real gesture below is meant to do the unlocking,
   exactly as a person's first click does. */
const chrome = spawn(exe, ['--remote-debugging-port=' + PORT, '--user-data-dir=' + profile,
  '--no-first-run', '--no-default-browser-check', '--window-size=1200,820',
  '--new-window', GALAXY], { detached: true, stdio: 'ignore' });

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
try { await page.send('Page.bringToFront'); } catch (e) { note('bringToFront: ' + e.message); }
ok(await waitFor(page, '!!(window.__galaxy && __galaxy.nudge && __galaxy.voice)', 30000),
   'the viewer is up and the nudge door is open');

/* ---- 1. THE VOICE IS STILL ALLOWED ------------------------------------------------ */
step('idle, ear shut: the nudge is SPOKEN');
/* EMPTY CANVAS, CHOSEN RATHER THAN GUESSED - voice_proof's picker, for its reason: an
   unlocking click that landed on the ear button would open the microphone, and an open
   microphone is the state section 3 is about. */
const spot = await page.json('(function(){' +
  'var pick=function(f){var x=Math.round(innerWidth*0.5), y=Math.round(innerHeight*f);' +
  ' var e=document.elementFromPoint(x,y);' +
  ' return {x:x, y:y, hit: e ? (e.id || e.tagName.toLowerCase()) : null,' +
  '  bad: !!(e && e.closest && (e.closest("#bar") || e.closest("#cmd") ||' +
  '          e.closest("#toprail") || e.closest("button")))};};' +
  'var s=pick(0.3); if(s.bad) s=pick(0.2); if(s.bad) s=pick(0.12);' +
  'return s;})()');
note('the unlocking click lands on ' + JSON.stringify(spot.hit));
ok(spot.bad === false, 'there is empty canvas to click, so the gesture is not a control',
   JSON.stringify(spot));
await realClick(page, spot.x, spot.y);
await sleep(400);
const unlocked = await waitFor(page, '__galaxy.speech.unlocked === true', 8000);
ok(unlocked, 'the first click unlocked the audio, so a line CAN be spoken from here - ' +
   'without this every "caption only" below would pass for the wrong reason',
   JSON.stringify(await page.json(STATE)));
/* Any line the boot greeting left in the queue is drained first, because "idle" is a
   precondition of this assertion and not something to hope for. */
await waitFor(page, '!__galaxy.voice.draining && __galaxy.voice.queue === 0', 30000);
const before1 = await page.json(STATE);
const r1 = await page.json('__galaxy.nudge.say(' + JSON.stringify(POSTURE) + ')');
await sleep(600);
const s1 = await page.json(STATE);
note('the gate said: ' + JSON.stringify(r1) + ' · blockedBy ' +
     JSON.stringify(s1.quiet.blockedBy));
ok(r1.spoke === true && r1.why === '' &&
   s1.quiet.spoken === before1.quiet.spoken + 1 && s1.quiet.held === before1.quiet.held &&
   carried(s1, POSTURE),
   'IT STILL SPEAKS: idle and with the ear shut the posture nudge went to the voice - ' +
   'spoken ' + before1.quiet.spoken + ' -> ' + s1.quiet.spoken + ', held unchanged at ' +
   s1.quiet.held + ', and the line is in the speech funnel\u2019s own record',
   JSON.stringify({ r1, quiet: s1.quiet, said: s1.said }));
ok(spokenAloud(s1, POSTURE),
   '       and ALOUD, not merely queued: the funnel recorded it as having reached the ' +
   'speakers, which is the only reading that distinguishes a nudge from a subtitle',
   JSON.stringify(s1.said));
ok(s1.caption.up === true && s1.caption.text.indexOf('Sit back') >= 0,
   '       and the caption says it too, because a spoken nudge is still a subtitle',
   JSON.stringify(s1.caption));

/* ---- 2. WHILE THE BUTLER IS READING ---------------------------------------------- */
step('while the butler is reading: caption only, and the held caption waits');
const LONG = 'Here is a long answer, sir, of the sort you would not want spoken over. ' +
  'It runs for several sentences precisely so that the nudge below arrives in the middle ' +
  'of it rather than in a gap. And it keeps going for one sentence more, so the queue is ' +
  'still draining when the unasked sentence is offered to the gate.';
await page.evaluate('__galaxy.speech.speakLine(' + JSON.stringify(LONG) + ')');
ok(await waitFor(page, '__galaxy.voice.draining === true', 8000),
   'the butler is reading a long answer - the state the rule is about');
const before2 = await page.json(STATE);
const r2 = await page.json('__galaxy.nudge.say(' + JSON.stringify(WATCH) + ')');
const s2 = await page.json(STATE);
note('the gate said: ' + JSON.stringify(r2));
ok(r2.spoke === false && r2.why === 'the butler is reading' &&
   s2.quiet.held === before2.quiet.held + 1 &&
   s2.quiet.spoken === before2.quiet.spoken &&
   s2.quiet.deferred === before2.quiet.deferred + 1,
   'CAPTION ONLY WHILE HE IS BEING READ TO: the watch nudge was held, by name - "' +
   r2.why + '" - and its caption deferred rather than dropped',
   JSON.stringify({ r2, before: before2.quiet, after: s2.quiet }));
ok(!carried(s2, WATCH),
   '       and THE LINE NEVER ENTERED THE SPEECH FUNNEL: it is absent from the record ' +
   'speakLine() itself writes, which is what withholding a voice has to mean',
   JSON.stringify(s2.said.map((e) => e.text.slice(0, 40))));
ok(s2.caption.text.indexOf('Nothing has moved') < 0,
   '       and THE SUBTITLE STILL BELONGS TO THE AUDIO: the caption was not stolen from ' +
   'the words coming out of the speakers - it reads "' +
   s2.caption.text.slice(0, 48) + '..."', JSON.stringify(s2.caption));
/* The deferred caption is the second half of the same rule: held back, not thrown away. */
const landed = await waitFor(page,
  '__galaxy.caption.text.indexOf("Nothing has moved") >= 0', 40000);
const s2b = await page.json(STATE);
ok(landed && s2b.draining === false && !carried(s2b, WATCH),
   '       and THE HELD CAPTION TOOK ITS TURN: when the queue ran dry the nudge captioned ' +
   'itself, still without a voice - "' + s2b.caption.text.slice(0, 48) + '"',
   JSON.stringify({ landed, caption: s2b.caption, draining: s2b.draining }));

/* ---- 3. THE EAR IS OPEN, AND THE ROOM IS SILENT ---------------------------------- */
step('the ear open in a silent room: still caption only');
await waitFor(page, '!__galaxy.voice.draining && __galaxy.voice.queue === 0', 30000);
const raise = await page.json('__galaxy.ear.raise()');
note('the one click: ' + JSON.stringify(raise));
ok(await waitFor(page, '__galaxy.ear.open === true', 10000),
   'the ear is open, on one click, as the contract says');
/* The wake chime is a sound, and this assertion is about a silent room, so it is waited
   out rather than tolerated. */
await waitFor(page, '!__galaxy.voice.draining && __galaxy.voice.queue === 0', 20000);
const before3 = await page.json(STATE);
ok(before3.earOpen === true && before3.draining === false && before3.queue === 0,
   'and NOTHING IS BEING SAID: queue ' + before3.queue + ', draining ' + before3.draining +
   ' - so what follows is not the speech rule wearing the ear\u2019s clothes',
   JSON.stringify(before3));
const t3 = await page.json('Date.now()');
const r3 = await page.json('__galaxy.nudge.say(' + JSON.stringify(POSTURE) + ')');
await sleep(400);
const s3 = await page.json(STATE);
note('the gate said: ' + JSON.stringify(r3));
ok(r3.spoke === false && /ear is open|recogniser is armed/.test(r3.why) &&
   s3.quiet.held === before3.quiet.held + 1 &&
   s3.quiet.spoken === before3.quiet.spoken,
   'AN OPEN EAR IS ITS OWN REASON TO STAY QUIET: in a silent room, with nothing in ' +
   'flight, the voice was still withheld - "' + r3.why + '" - because the recogniser is ' +
   'armed between turns and a nudge spoken into it is transcribed as his',
   JSON.stringify({ r3, before: before3.quiet, after: s3.quiet }));
ok(s3.caption.up === true && s3.caption.text.indexOf('Sit back') >= 0 &&
   !spokenAloud({ said: s3.said.filter((e) => e.at >= t3) }, POSTURE),
   '       and it was CAPTIONED AT ONCE rather than deferred: nothing was being read, so ' +
   'there was no subtitle to wait for - "' + s3.caption.text.slice(0, 48) + '"',
   JSON.stringify({ caption: s3.caption, said: s3.said }));

/* ---- 4. AN ANSWER IN FLIGHT ------------------------------------------------------ */
step('an answer in flight: caption only, with the speakers silent');
await page.evaluate('__galaxy.ear.close("nudge proof")');
ok(await waitFor(page, '__galaxy.ear.open === false', 8000),
   'the ear is shut again, so the reason below can only be the answer');
await waitFor(page, '!__galaxy.voice.draining && __galaxy.voice.queue === 0', 30000);
/* ask() rather than a fetch of our own, because `busy` is the page's own flag and only the
   page's own path sets it. The web gate makes this question slow enough to be caught in
   flight. There is no __galaxy.busy door and none is added: the gate PUBLISHES its reason,
   so "an answer is in flight" is read where the rule itself reads it. */
page.evaluate('__galaxy.ask(' + JSON.stringify(ANSWER_Q) + ')').catch(() => {});
const inFlight = await waitFor(page,
  '__galaxy.nudge.quiet.blockedBy === "an answer is in flight"', 10000);
const before4 = await page.json(STATE);
const r4 = inFlight ? await page.json('__galaxy.nudge.say(' + JSON.stringify(WATCH) + ')')
                    : { spoke: null, why: 'never caught in flight' };
const s4 = await page.json(STATE);
note('the gate said: ' + JSON.stringify(r4) + ' · queue ' + before4.queue +
     ' draining ' + before4.draining);
ok(inFlight && r4.spoke === false && r4.why === 'an answer is in flight' &&
   before4.queue === 0 && before4.draining === false,
   'THE GAP BETWEEN THE QUESTION AND THE REPLY IS NOT A GAP: the speakers were silent and ' +
   'the ear was shut, so every audio test said "go ahead" - and the gate still said "' +
   r4.why + '", a second before the answer arrived',
   JSON.stringify({ inFlight, r4, before: before4 }));
ok(!carried(s4, WATCH) || !spokenAloud(s4, WATCH),
   '       and nothing of it reached the speakers',
   JSON.stringify(s4.said.map((e) => e.text.slice(0, 40) + ' aloud=' + e.aloud)));
await waitFor(page, '__galaxy.nudge.quiet.blockedBy !== "an answer is in flight"', 60000);

/* ---- 5. THE LEDGER, AND THE SOURCE ---------------------------------------------- */
step('the gate\u2019s own arithmetic, and both callers');
const end = await page.json(STATE);
const dSpoken = end.quiet.spoken - before1.quiet.spoken;
const dHeld = end.quiet.held - before1.quiet.held;
/* Deltas rather than totals, because the two organs that nudge for real are still live in
   this page and a spontaneous nudge mid-run would be correct behaviour, not a failure. */
ok(dSpoken === 1 && dHeld === 3 && dSpoken + dHeld === 4,
   'EVERY CALL IS ACCOUNTED FOR: across the four nudges this file made, ' + dSpoken +
   ' was spoken and ' + dHeld + ' were held - one voice, three captions, nothing dropped ' +
   'and nothing counted twice',
   JSON.stringify({ before: before1.quiet, end: end.quiet, dSpoken, dHeld }));

/* AND THE RULE IS NOT OPTIONAL, which is a claim about the source rather than about a run.
   Read from the file: the two unasked sentences both hand their line to nudgeSpeak(), and
   nudgeSpeak() is the only thing between them and the voice. */
const src = readFileSync('viewer/index.html', 'utf8');
const callers = [...src.matchAll(/const\s+said\s*=\s*nudgeSpeak\(/g)].length;
const defs = [...src.matchAll(/function\s+nudgeSpeak\(/g)].length;
/* Calls, not mentions: the name also appears in three comments pointing here, and counting
   prose would make this assertion fail the next time somebody explains the rule properly. */
const calls = [...src.matchAll(/(?:=|return)\s*nudgeSpeak\(/g)].length;
const speaks = [...src.matchAll(/nudgeSpeak\(/g)].length;
ok(callers === 2 && defs === 1 && calls === 3,
   'BOTH UNASKED SENTENCES GO THROUGH THE GATE: ' + callers + ' callers hand their line ' +
   'to nudgeSpeak(), which is defined ' + defs + ' time and called ' + calls +
   ' - the posture nudge, the watch nudge and the harness door, and nothing else (' +
   (speaks - defs - calls) + ' further mentions are comments pointing at the rule)',
   JSON.stringify({ callers, defs, calls, speaks }));
/* The posture and watch paths are the two blocks that used to speak directly. If either
   ever calls the funnel again on its own line, the rule is back to being a comment - so
   both windows are read, not just the first. */
const windows = [...src.matchAll(/const\s+said\s*=\s*nudgeSpeak\(/g)]
  .map((m) => src.slice(Math.max(0, m.index - 200), m.index + 500));
ok(windows.length === 2 && windows.every((w) => w.indexOf('speakLine(') < 0),
   '       and NEITHER OF THEM REACHES THE FUNNEL DIRECTLY: no speakLine() anywhere around ' +
   'either call site, so the gate cannot be walked around by accident tomorrow',
   JSON.stringify(windows.map((w) => w.slice(180, 280))));

say('\n  VERIFY ' + pass + '/' + (pass + fail) + (fail ? ' FAIL' : ' PASS'));
if (fail) { say(''); for (const f of failures) say('    FAILED: ' + f); }
page.close();
spawnSync('taskkill', ['/PID', String(chrome.pid), '/T', '/F']);
process.exit(fail ? 1 : 0);
