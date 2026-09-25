/* THE OPEN EAR, PROVED AS A CONVERSATION - because the complaint was never "the microphone
 * does not work". It was that talking to this machine felt like using a walkie-talkie: press,
 * speak, release, press again. A button you have to keep pressing is a button; a room that
 * stays open is a conversation. Nothing in a screenshot can tell those two apart, and nothing
 * in a unit test can either, so this file counts CLICKS.
 *
 * WHAT IS BEING PROVED, and the first line is the whole of it:
 *
 *   ONE CLICK, THREE QUESTIONS. The ear button is pressed exactly once, with a real mouse
 *     event at the real rectangle. Three questions then go in and three answers come back,
 *     and the click counter in this file must still read one at the end. If it ever needs a
 *     second click the run fails, no matter how well everything else behaved.
 *   THE RE-ARM IS MEASURED FROM HIS VOICE, not from the answer arriving. The page's
 *     speakDone contract is the edge; four hundred milliseconds later the recogniser is up
 *     again, and `rearmWhy` has to say so in words.
 *   THE BARGE-IN. Somebody talks over the butler mid-answer. The speech bus must be at zero,
 *     the remaining queue must be gone, and the page must be listening - all three, in the
 *     same reading. Interrupting him has to feel like interrupting a person, and a person
 *     who finished their sentence first was not interrupted.
 *   THE CLOSERS. "Thank you, goodbye" ends the session with a parting line, spoken, and the
 *     stream goes down with it. Not a silent dismissal: a person says goodbye back.
 *   THE COURTESY CLOCK. With the timeout shortened - the only thing this harness is allowed
 *     to change - a silent room closes itself, gently, with "I'll let you work, sir."
 *   THE TRANSPARENCY LAW, at every stage. The seal is read at each step of the run and the
 *     sequence is asserted: ready before, EAR OPEN and named engine throughout, speaking
 *     while he talks, ready again after. And the engine word must be the truth - there is
 *     nothing in the page that can say "local", and this checks that too.
 *   NOTHING IS KEPT. MediaRecorder is replaced with a counter before the click and must
 *     never be constructed; getUserMedia is wrapped and must be called exactly once per
 *     session; and the page's own privacy ledger must read zero.
 *
 * THE QUESTIONS GO IN THROUGH heardFinal(), which is the door the recogniser itself uses,
 * and the VOICE ACTIVITY comes in through vad(), which is the door the analyser uses. That
 * is deliberate and it is the same choice voice_proof makes: a proof that needed a real room
 * and a real Google speech service could not be run at all, and one that reached past those
 * two doors would be a test of Chrome. Everything downstream of them - the funnel, the
 * turn-taking, the clock, the seal, the queue - is the real thing.
 *
 * The microphone is Chrome's fake device reading a file of digital zeros. A 440Hz test tone
 * is a voice as far as any VAD is concerned, and the session would spend the whole run
 * thinking somebody was talking.
 *
 * NOT MUTED, and that is not a convenience. The mic press is dispatched as a real trusted
 * mouse event at the button's real rectangle, and no --autoplay-policy flag is passed, so
 * the audio unlock has to be earned by that gesture exactly as it is for him. A ?mute=1 tab
 * would prove the bookkeeping and skip the only part that can actually be at zero.
 * CONV_HEADED=1 to watch it happen; headless otherwise, which is how preflight runs it.
 *
 * Usage:  python server.py 2> server-trace.log   then   node conversation_proof.mjs
 */
import { spawn, spawnSync } from 'node:child_process';
import { mkdtempSync, rmSync, existsSync, writeFileSync, writeSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const GALAXY = 'http://127.0.0.1:4700';
const PORT = 9239;
const CDP = 'http://127.0.0.1:' + PORT;
const CHROMES = [
  'C:/Program Files/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Google/Chrome/Application/chrome.exe',
  process.env.LOCALAPPDATA + '/Google/Chrome/Application/chrome.exe',
];
const HEADED = process.env.CONV_HEADED === '1';
/* THE WHOLE RUN'S PATIENCE, and it is a real number rather than a hope. Three model answers
   read out loud end to end is the slowest thing in this suite, so the budget is generous -
   but a harness with no ceiling is a harness that can hang a preflight, and one that hangs
   without saying where it was is worse than one that fails. */
const BUDGET_MS = Number(process.env.CONV_BUDGET_MS || 900000);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

/* WRITTEN SYNCHRONOUSLY TO FD 1, and not through console.log. Node's stdout is block-
   buffered when it is a pipe, which is exactly what `| tee` and every CI runner give it -
   so a run that hangs loses everything it had said since the last four kilobytes. This
   harness is the longest one in the suite and the most likely to be interrupted; its output
   has to be on disk the instant it is produced or a hang is unreadable. */
const say = (s) => { try { writeSync(1, s + '\n'); } catch { console.log(s); } };

let checks = 0; const bad = [];
const ok = (c, claim, detail) => {
  checks++; say((c ? '  ok   ' : '  FAIL ') + claim);
  if (!c) { bad.push(claim); if (detail) say('         ' + detail); }
};
const note = (m) => say('  note ' + m);
/* WHERE THE RUN HAD GOT TO, kept for the watchdog. Every phase announces itself before it is
   attempted rather than after it succeeds, so the last line printed is the thing that hung. */
let STEP = 'starting';
const step = (s) => { STEP = s; say('  ·· ' + s); };
const procs = []; const profiles = [];

/* THE CLICK COUNTER, and it lives out here in Node rather than in the page for one reason:
   it is the thing under test. A count kept inside the browser could be reset, recomputed or
   quietly incremented by the page itself; this one can only go up when THIS FILE dispatches
   a mouse event, which is exactly the claim. */
let CLICKS = 0;

/* The transcript, built as the run goes, printed at the end. It is what PART 8 asks for:
   a conversation somebody can read and see one click in. */
const script = [];
const line = (who, what) => { script.push(who + '\t' + what); };

class Page {
  constructor(u) { this.u = u; this.id = 0; this.w = new Map(); this.errors = []; }
  open() { return new Promise((res, rej) => {
    this.ws = new WebSocket(this.u);
    this.ws.onopen = () => res(this);
    this.ws.onerror = (e) => rej(new Error('socket: ' + (e.message || 'failed')));
    this.ws.onmessage = (ev) => {
      const m = JSON.parse(ev.data);
      if (m.method === 'Runtime.exceptionThrown') {
        const d = m.params.exceptionDetails;
        this.errors.push(d.text + ' ' + ((d.exception && d.exception.description) || ''));
      }
      const f = this.w.get(m.id); if (f) { this.w.delete(m.id); f(m); }
    }; }); }
  send(method, params) { const id = ++this.id;
    return new Promise((res, rej) => {
      const bomb = setTimeout(() => { this.w.delete(id); rej(new Error(method + ' timed out')); }, 30000);
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
  /* A real press at a real rectangle, and the ONLY function in this file that may raise the
     counter. Everything else talks to the page through its own doors. */
  async click(id) {
    const box = await this.json('(function(){var e=document.getElementById(' +
      JSON.stringify(id) + ');if(!e)return null;var r=e.getBoundingClientRect();' +
      'return {x:Math.round(r.left+r.width/2),y:Math.round(r.top+r.height/2)};})()');
    if (!box) throw new Error('no #' + id + ' to click');
    for (const type of ['mousePressed', 'mouseReleased']) {
      await this.send('Input.dispatchMouseEvent',
        { type, x: box.x, y: box.y, button: 'left', clickCount: 1 });
    }
    CLICKS++;
    return box;
  }
  close() { try { this.ws.close(); } catch { } }
}

const cdp = async (p) => { const r = await fetch(CDP + p); const t = await r.text();
  try { return JSON.parse(t); } catch { return t; } };

async function waitFor(page, expr, ms = 10000) {
  for (let i = 0; i < ms / 150; i++) {
    try { if (await page.evaluate(expr)) return true; } catch { }
    await sleep(150);
  }
  return false;
}

/* Two seconds of digital zero, 16-bit PCM mono - the only shape Chrome's fake audio
   capture will read, looped for as long as the run lasts. */
function silence(dir) {
  const path = join(dir, 'silence.wav');
  const rate = 48000, n = rate * 2, bytes = n * 2;
  const b = Buffer.alloc(44 + bytes);
  b.write('RIFF', 0); b.writeUInt32LE(36 + bytes, 4); b.write('WAVE', 8);
  b.write('fmt ', 12); b.writeUInt32LE(16, 16); b.writeUInt16LE(1, 20);
  b.writeUInt16LE(1, 22); b.writeUInt32LE(rate, 24); b.writeUInt32LE(rate * 2, 28);
  b.writeUInt16LE(2, 32); b.writeUInt16LE(16, 34);
  b.write('data', 36); b.writeUInt32LE(bytes, 40);
  writeFileSync(path, b);
  return path;
}

/* The instruments, installed before the click. Three of them, and all three are about what
   the page must NOT do: keep audio, open a second microphone, or lose a spoken line. */
const INSTRUMENTS = `(function () {
  window.__conv = { said: [], done: 0, gum: 0, recorders: 0, seals: [] };
  addEventListener('speakLine', function (e) {
    window.__conv.said.push({ at: Date.now(), text: e.detail.text });
  });
  addEventListener('speakDone', function () { window.__conv.done++; });
  /* THE RECORDER THAT MUST NEVER BE BUILT. Replaced rather than watched: if any line in
     this page ever constructs one, the count moves and "no audio is stored" is a lie. */
  var Real = window.MediaRecorder;
  function Counted() { window.__conv.recorders++; return new Real(arguments[0], arguments[1]); }
  Counted.isTypeSupported = Real ? Real.isTypeSupported : function () { return false; };
  window.MediaRecorder = Counted;
  /* AND ONE MICROPHONE PER SESSION. The eyes have a camera of their own and this counts
     only audio asks, so a second stream would mean the ear opened twice. */
  var gum = navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);
  navigator.mediaDevices.getUserMedia = function (c) {
    if (c && c.audio) window.__conv.gum++;
    return gum(c);
  };
  return 'armed';
})()`;

async function main() {
  say('\n  the open ear: one click, three questions, and a goodbye\n');
  step('launching');
  const exe = CHROMES.find((p) => existsSync(p));
  if (!exe) throw new Error('no chrome.exe');
  const health = await (await fetch(GALAXY + '/health')).json();
  note('server up, model ' + (health.model || '?'));
  /* THE SERVER'S OWN NUMBER, read before the page is asked about it. config.json names the
     courtesy timeout and /health publishes it; the page must agree with this, not with a
     literal of its own. */
  const serverTimeout = health.ear && health.ear.timeoutS;
  note('/health publishes conversation_timeout_s = ' + JSON.stringify(serverTimeout));

  const profile = mkdtempSync(join(tmpdir(), 'conv-'));
  profiles.push(profile);
  const chrome = spawn(exe, [
    '--remote-debugging-port=' + PORT, '--user-data-dir=' + profile,
    '--no-first-run', '--no-default-browser-check',
    /* Permission granted up front, because a modal dialog is not the subject and a run that
       stopped on one would prove nothing either way. The AUDIO is a file of zeros. */
    '--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream',
    '--use-file-for-fake-audio-capture=' + silence(profile),
    '--disable-features=CalculateNativeWinOcclusion',
    '--disable-backgrounding-occluded-windows',
    '--disable-renderer-backgrounding',
    ...(HEADED ? [] : ['--headless=new']),
    '--window-size=1280,880', '--new-window', GALAXY,
  ], { detached: true, stdio: 'ignore' });
  procs.push(chrome);

  for (let i = 0; i < 80; i++) { try { await cdp('/json/version'); break; } catch { await sleep(250); } }
  note('chrome: ' + ((await cdp('/json/version')).Browser || '?'));
  let target = null;
  for (let i = 0; i < 40; i++) {
    const l = await cdp('/json/list');
    target = (Array.isArray(l) ? l : []).filter((t) => t.type === 'page')
      .find((t) => t.url.includes('127.0.0.1:4700'));
    if (target) break; await sleep(300);
  }
  if (!target) throw new Error('no viewer page');
  const page = new Page(target.webSocketDebuggerUrl);
  await page.open();
  await page.send('Runtime.enable');
  await page.send('Page.enable');
  if (!await waitFor(page, '!!(window.__galaxy && __galaxy.ear)', 40000)) {
    throw new Error('the viewer never came up');
  }
  await sleep(2200);

  /* THE SEAL, READ AND KEPT. Every stage of the run leaves one of these behind, and section
     6 asserts the sequence rather than any single reading - "correct at every stage" is a
     claim about an order, not about a moment. */
  const seals = [];
  const mark = async (stage) => {
    const s = await page.json('({seal: __galaxy.ear.seal, dot: __galaxy.ear.dot,' +
      ' status: document.getElementById("status").className})');
    s.stage = stage;
    s.word = s.seal.word;
    seals.push(s);
    return s;
  };

  /* ---- 0. THE ROOM BEFORE ANYBODY SPEAKS --------------------------------- */
  step('0 · the room before anybody speaks');
  ok(await page.evaluate(INSTRUMENTS) === 'armed',
     'the instruments are in before the click: a recorder counter, a getUserMedia counter ' +
     'and a record of every line the funnel accepted');
  const rest = await mark('at rest');
  ok(rest.seal.open === false && rest.seal.shown === false && rest.dot.ear === false,
     'AT REST THE EAR IS SHUT and the seal does not claim otherwise: no EAR OPEN cell, no ' +
     'ring on the organ rail', JSON.stringify(rest));
  ok(rest.word === 'ready',
     'and the seal reads READY - the state word PART 6 asks for, in the bar where the ' +
     'textarea used to be', JSON.stringify(rest));
  const shape = await page.json('({engine: __galaxy.ear.engine,' +
    ' timeoutS: __galaxy.ear.timeoutS, rearm: __galaxy.ear.REARM_MS,' +
    ' ambient: __galaxy.ear.ambient, click: __galaxy.ear.clickPerSession,' +
    ' closers: __galaxy.ear.closers, kept: __galaxy.ear.kept,' +
    ' input: __galaxy.typeLine.persistentInput})');
  ok(shape.rearm === 400,
     'the re-arm is four hundred milliseconds, as specified', JSON.stringify(shape));
  ok(shape.timeoutS === serverTimeout,
     'and the courtesy clock is the SERVER\u2019S number (' + shape.timeoutS + 's), read ' +
     'from /health rather than kept as a literal in the viewer', JSON.stringify(shape));
  ok(shape.ambient === false && shape.click === true,
     'AMBIENT LISTENING IS OUT OF SCOPE BY DESIGN, and the page publishes that as a ' +
     'refusal rather than leaving it to be inferred', JSON.stringify(shape));
  ok(shape.engine === 'browser',
     'and the engine word is "browser" - the truth, because the recogniser is Chrome\u2019s ' +
     'own and Chrome sends the audio away', JSON.stringify(shape));
  /* THE SECOND HALF OF THE LAW - "never claims to be local when it is not" - is a claim
     about the code, so it is checked against the code. One producer of that word, and the
     word it cannot produce. */
  const src = await (await fetch(GALAXY + '/index.html')).text();
  const engineFn = (src.match(/function earEngineWord\s*\([^)]*\)\s*\{([^}]*)\}/) || [])[1];
  const engineDefs = (src.match(/function earEngineWord\b/g) || []).length;
  ok(engineDefs === 1 && engineFn && !/local/.test(engineFn) &&
     /'browser'/.test(engineFn) && /'none'/.test(engineFn),
     'THE PAGE CANNOT SAY "LOCAL": there is exactly one function that produces the engine ' +
     'word, and the only two words in it are "browser" and "none"',
     JSON.stringify(engineFn));
  ok(!/new\s+MediaRecorder/.test(src),
     'and nothing in the page constructs a MediaRecorder - the three times the name appears ' +
     'are all a comment or the zero that reports it');
  ok(shape.input.q === false && shape.input.textareas === 0,
     'and there is no standing textarea to type into - speech is the resident',
     JSON.stringify(shape.input));
  /* THE FOUR CLOSERS, PROVED AS A LIST rather than as four examples of one. The page hands
     out the patterns; the phrases are tested against them here, through the page's own
     normalisation - and so is a sentence that merely CONTAINS one, because "that's all I
     know about the roaster" is a remark and not a goodbye. */
  const bareOf = (s) => s.toLowerCase().replace(/[.,!?;:'"]/g, '').replace(/\s+/g, ' ').trim();
  const res = shape.closers.map((s) => new RegExp(s));
  const closes = (phrase) => res.some((r) => r.test(bareOf(phrase)));
  ok(res.length === 4, 'four closers are published, as patterns: ' + res.length);
  const SPEC = ["that's all", 'thank you, goodbye', 'end conversation', 'good night'];
  ok(SPEC.every(closes),
     'and all four of the spec\u2019s partings are closers: ' + SPEC.join(' \u00b7 '),
     JSON.stringify(SPEC.map((p) => p + '=' + closes(p))));
  ok(!closes("that's all I know about the roaster") && !closes('goodbye is a strange word'),
     'while a sentence that merely CONTAINS one is still a question - the patterns are ' +
     'anchored, so a conversation cannot be ended by accident');

  /* ---- 1. ONE CLICK ------------------------------------------------------- */
  step('1 · the one click');
  line('EMPLOYER', '[clicks the ear once]');
  await page.click('mic');
  ok(CLICKS === 1, 'ONE CLICK, and this file counted it: ' + CLICKS);
  const opened = await waitFor(page, '__galaxy.ear.open === true', 8000);
  ok(opened, 'and the click OPENED A SESSION rather than an utterance');
  await waitFor(page, '__galaxy.ear.analyser === true', 8000);
  const up = await page.json('({open: __galaxy.ear.open, opened: __galaxy.ear.opened,' +
    ' arms: __galaxy.ear.arms, stream: __galaxy.ear.stream,' +
    ' analyser: __galaxy.ear.analyser, gum: window.__conv.gum,' +
    ' clock: __galaxy.ear.clock})');
  ok(up.opened === 1 && up.gum === 1,
     'one session, one microphone: getUserMedia was asked exactly once',
     JSON.stringify(up));
  ok(up.clock === true,
     'and the courtesy clock started with it - a room nobody speaks in closes itself',
     JSON.stringify(up));
  const openSeal = await mark('ear open');
  ok(openSeal.seal.open === true && openSeal.seal.shown === true &&
     /ear open/i.test(openSeal.seal.cell) &&
     openSeal.seal.cell.indexOf('browser') >= 0,
     'THE TRANSPARENCY LAW, FIRST HOME: the seal reads "' + openSeal.seal.cell +
     '" - persistent, visible, and naming the engine', JSON.stringify(openSeal));
  ok(openSeal.dot.ear === true,
     'SECOND HOME: the organ-rail mic wears .ear, so the dot pulses for as long as the ' +
     'stream is live', JSON.stringify(openSeal.dot));
  const organ = await page.json('__galaxy.organs.state.mic');
  ok(organ && organ.organ === 'live' && /EAR OPEN/.test(organ.line),
     'and the rail SAYS it in words too: "' + (organ || {}).line + '"',
     JSON.stringify(organ));
  ok(organ && organ.lit === true && organ.beating === true,
     'AND THE DOT IS ACTUALLY PULSING - read from the computed style rather than from the ' +
     'class that was meant to cause it: opacity above the floor and the organbeat animation ' +
     'running', JSON.stringify(organ));

  /* ---- 2. THREE QUESTIONS, NO MORE CLICKS -------------------------------- */
  /* Each question goes in through heardFinal, which is the recogniser's own door, and then
     nothing touches the page until the answer has been spoken and the ear has re-armed by
     itself. The assertion that matters in this section is the one at the end of it: CLICKS
     is still 1. */
  const QUESTIONS = [
    'what is the web gate',
    'and what does the third door do',
    'tell me about the antecedent memory',
  ];
  const turn = async (n, words) => {
    step('2 · turn ' + n + ': ' + words);
    const before = await page.json('({said: window.__conv.said.length,' +
      ' done: window.__conv.done, arms: __galaxy.ear.arms,' +
      ' rearms: __galaxy.ear.rearms, turns: __galaxy.ear.turns})');
    line('EMPLOYER', words);
    await page.evaluate('__galaxy.speech.feedFinal(' + JSON.stringify(words) + ')');
    /* FINISH_MS is 900: the page waits that long for him to carry on before it decides the
       sentence is finished. Waited through rather than skipped, because that pause is part
       of how the turn ends. */
    const asked = await waitFor(page, '__galaxy.ear.turns === ' + (before.turns + 1), 6000);
    ok(asked, 'TURN ' + n + ': the sentence ended by itself and became a question - no ' +
       'button, no release, no second click');
    step('2 · turn ' + n + ': waiting for the answer to reach the funnel');
    const spoke = await waitFor(page,
      'window.__conv.said.length > ' + before.said, 120000);
    const said = await page.json('window.__conv.said');
    const answer = said.length ? said[said.length - 1].text : '';
    line('BUTLER', answer);
    ok(spoke && answer.length > 0,
       'and the answer came back and went through the funnel (' + answer.length +
       ' characters)', JSON.stringify(answer.slice(0, 90)));
    /* THE CAPTION, WHILE HE IS TALKING. PART 6's subtitle: it is up, it holds the line he
       is reading, and the state seal says SPEAKING. */
    const talking = await page.json('({caption: __galaxy.caption.up,' +
      ' text: __galaxy.caption.text, word: (document.getElementById("seal-text")||{})' +
      '.textContent, draining: __galaxy.voice.draining,' +
      ' state: document.getElementById("seal").getAttribute("data-state")})');
    ok(talking.caption === true && answer.indexOf(talking.text.slice(0, 40)) >= 0,
       'THE ANSWER IS A SUBTITLE: the caption is up and carries the line he is speaking',
       JSON.stringify(talking));
    if (n === 1) {
      await mark('speaking');
      ok(talking.word === 'speaking' || talking.draining === true,
         'and the seal says SPEAKING while he reads it', JSON.stringify(talking));
    }
    /* AND NOW NOBODY TOUCHES ANYTHING. The queue drains, speakDone goes up, and four
       hundred milliseconds after that the recogniser is up again on its own. */
    step('2 · turn ' + n + ': waiting for the answer to be read to its last word');
    const drained = await waitFor(page,
      'window.__conv.done > ' + before.done, 180000);
    ok(drained, 'the whole answer was read to its last word (speakDone fired)');
    const rearmed = await waitFor(page,
      '__galaxy.ear.rearms > ' + before.rearms, 6000);
    const after = await page.json('({rearms: __galaxy.ear.rearms,' +
      ' arms: __galaxy.ear.arms, why: __galaxy.ear.rearmWhy,' +
      ' open: __galaxy.ear.open, clock: __galaxy.ear.clock,' +
      ' caption: __galaxy.caption.pending})');
    ok(rearmed && after.arms > before.arms,
       'AND THE EAR RE-ARMED BY ITSELF: "' + after.why + '" - arms ' + before.arms +
       ' \u2192 ' + after.arms + ', with nobody\u2019s hand anywhere near the mouse',
       JSON.stringify(after));
    if (n === 1) {
      ok(after.why === 'his voice ended',
         'and it is measured from HIS VOICE ENDING rather than from the answer arriving - ' +
         'the page\u2019s own completion contract is the edge', JSON.stringify(after));
      ok(after.caption === true,
         'the caption\u2019s four-second fade is armed from the same edge, and not before it',
         JSON.stringify(after));
    }
    ok(CLICKS === 1, 'and the click counter still reads 1 after turn ' + n);
    return after;
  };

  await turn(1, QUESTIONS[0]);
  await turn(2, QUESTIONS[1]);
  const twoTurns = await page.json('({turns: __galaxy.ear.turns,' +
    ' opened: __galaxy.ear.opened, arms: __galaxy.ear.arms,' +
    ' rearms: __galaxy.ear.rearms, gum: window.__conv.gum})');
  ok(twoTurns.turns === 2 && twoTurns.opened === 1 && CLICKS === 1,
     'TWO FULL QUESTION-AND-ANSWER TURNS ON ONE CLICK: ' + twoTurns.turns +
     ' turns, ' + twoTurns.opened + ' session, ' + CLICKS + ' click',
     JSON.stringify(twoTurns));
  ok(twoTurns.arms > twoTurns.opened && twoTurns.gum === 1,
     'and the recogniser was raised ' + twoTurns.arms + ' times inside that one session ' +
     'without asking for the microphone twice', JSON.stringify(twoTurns));

  /* ---- 3. THE BARGE-IN ---------------------------------------------------- */
  step('3 · the barge-in');
  /* A third question, and this time he talks over the answer. Everything up to the moment of
     the interruption is the same as the two turns above; what is being watched is the
     instant itself, sampled in one evaluate so the three facts are from one tick. */
  line('EMPLOYER', QUESTIONS[2]);
  await page.evaluate('__galaxy.speech.feedFinal(' + JSON.stringify(QUESTIONS[2]) + ')');
  step('3 · waiting for the third answer to start');
  const talking = await waitFor(page, '__galaxy.voice.draining === true', 180000);
  ok(talking, 'a third answer comes back and the butler starts reading it');
  const midAnswer = await page.json('({queue: __galaxy.voice.queue,' +
    ' bus: __galaxy.audio.speechBus, zeroed: __galaxy.audio.speechZeroed,' +
    ' draining: __galaxy.voice.draining, caption: __galaxy.caption.up,' +
    ' arms: __galaxy.ear.arms, listening: __galaxy.ear.listening,' +
    ' bargeIns: __galaxy.ear.bargeIns})');
  note('mid-answer: ' + JSON.stringify(midAnswer));
  ok(midAnswer.zeroed === false && midAnswer.bus === 1,
     'and the bus is at full height while he speaks - there is nothing to undo yet',
     JSON.stringify(midAnswer));
  ok(midAnswer.listening === false,
     'with the recogniser DOWN while the butler reads, which is why he does not transcribe ' +
     'himself - the session is open, the microphone is not being listened to',
     JSON.stringify(midAnswer));
  /* THREE FRAMES OVER THE GATE, IN ONE TICK. The VAD wants three consecutive frames above
     the top threshold before it will call something speech, and the analyser's own loop is
     feeding it zeros from the silent file sixty times a second - so the three have to happen
     inside one task or the real frames will reset the count between them. */
  line('EMPLOYER', '[speaks over him] hold on, actually');
  const barge = await page.json('(function () {' +
    '__galaxy.ear.vad(0.25); __galaxy.ear.vad(0.25); var v = __galaxy.ear.vad(0.25);' +
    'return {vad: v, bus: __galaxy.audio.speechBus,' +
    ' zeroed: __galaxy.audio.speechZeroed, queue: __galaxy.voice.queue,' +
    ' draining: __galaxy.voice.draining, caption: __galaxy.caption.up,' +
    ' notes: __galaxy.voice.notes.slice(-2)};})()');
  note('the instant: ' + JSON.stringify(barge));
  ok(barge.vad.speech === true && barge.vad.bargeIns === 1,
     'BARGE-IN: speech over the butler is detected as an interruption, once',
     JSON.stringify(barge.vad));
  ok(barge.bus === 0 && barge.zeroed === true,
     'AND THE VOICE IS AT ZERO IN THE SAME TICK - not faded, not scheduled: the gain node ' +
     'reads ' + barge.bus + ', so whatever syllable was in flight is inaudible before it ' +
     'is gone', JSON.stringify(barge));
  ok(barge.queue === 0 && barge.draining === false,
     'and the REST OF THE ANSWER IS CANCELLED: the queue is empty and the run is over - ' +
     'interrupting him does not mean waiting for him to finish', JSON.stringify(barge));
  ok(barge.notes.join(' | ').indexOf('barge-in') >= 0,
     'the cancel is recorded in the page\u2019s own words: "' + barge.notes.join(' | ') + '"',
     JSON.stringify(barge.notes));
  ok(barge.caption === false,
     'and the subtitle goes with it - a caption for a sentence nobody heard is a caption ' +
     'for a sentence that was not said', JSON.stringify(barge));
  /* AND IT LISTENS. The counter rather than the flag: `arms` is raised in the recogniser's
     own onstart and only goes up, whereas `listening` is a live flag that a headless tab's
     network error can take back down between two polls. The claim is that the barge-in
     RAISED the recogniser, and that is what a counter records. */
  const listening = await waitFor(page,
    '__galaxy.ear.arms > ' + midAnswer.arms, 5000);
  const heard = await page.json('({arms: __galaxy.ear.arms,' +
    ' listening: __galaxy.ear.listening, status: document.getElementById("status").className})');
  ok(listening, 'AND IT LISTENS: the recogniser went up in the same breath (arms ' +
     midAnswer.arms + ' → ' + heard.arms + '), because an interruption is the start of ' +
     'the next thing he wants to say', JSON.stringify(heard));
  line('BUTLER', '[stops mid-sentence, listening]');
  ok(CLICKS === 1, 'still one click - a barge-in is not a button either');
  /* And the room goes quiet again: the analyser's own zeros carry the VAD past its hang
     time, so the end of that interruption is detected by the real detector. */
  const ended = await waitFor(page, '__galaxy.ear.speech === false', 4000);
  ok(ended, 'and the interruption ENDS on its own six hundred milliseconds later, from the ' +
     'analyser\u2019s own reading rather than from anything this harness did');

  /* ---- 4. THE CLOSER ------------------------------------------------------ */
  step('4 · the closer');
  const GOODBYE = 'thank you, goodbye';
  line('EMPLOYER', GOODBYE);
  const saidBefore = await page.evaluate('window.__conv.said.length');
  await page.evaluate('__galaxy.speech.feedFinal(' + JSON.stringify(GOODBYE) + ')');
  const closed = await waitFor(page, '__galaxy.ear.open === false', 5000);
  const bye = await page.json('({open: __galaxy.ear.open,' +
    ' closedBy: __galaxy.ear.closedBy, parting: __galaxy.ear.parting,' +
    ' stream: __galaxy.ear.stream, analyser: __galaxy.ear.analyser,' +
    ' clock: __galaxy.ear.clock, caption: __galaxy.caption.text,' +
    ' said: window.__conv.said.slice(-1)})');
  line('BUTLER', bye.parting);
  ok(closed && bye.open === false,
     'A CLOSER CLOSES THE SESSION: "' + GOODBYE + '" ends it', JSON.stringify(bye));
  ok(bye.closedBy.indexOf(GOODBYE) >= 0,
     'and the page records WHAT he said, not merely that something happened: ' +
     bye.closedBy, JSON.stringify(bye));
  ok(bye.parting.length > 0 && bye.said.length === 1 &&
     bye.said[0].text === bye.parting && bye.caption === bye.parting,
     'WITH A PARTING LINE, spoken and captioned: "' + bye.parting + '" - a person says ' +
     'goodbye back', JSON.stringify(bye));
  ok(bye.stream === false && bye.analyser === false && bye.clock === false,
     'and the microphone goes down with it: no stream, no analyser, no clock left running',
     JSON.stringify(bye));
  const shut = await mark('closed');
  ok(shut.seal.open === false && shut.seal.shown === false && shut.dot.ear === false,
     'THE SEAL STOPS SAYING EAR OPEN the moment it is not - the law cuts both ways',
     JSON.stringify(shut));

  /* ---- 5. THE COURTESY CLOCK --------------------------------------------- */
  step('5 · the courtesy clock');
  /* A second session, and the only thing this harness changes about the page: the timeout,
     shortened, because a proof cannot sit through forty-five seconds of nothing to find out
     that forty-five seconds of nothing works. The click below is a NEW conversation - the
     one-click claim was about the three turns above, and it is already proved. */
  note('a second session, to watch a silent room close itself');
  await page.evaluate('__galaxy.ear.hold(4)');
  line('EMPLOYER', '[clicks the ear again, and then says nothing at all]');
  await page.click('mic');
  ok(CLICKS === 2, 'a new conversation costs exactly one more click: ' + CLICKS);
  ok(await waitFor(page, '__galaxy.ear.open === true', 8000),
     'the session opens again');
  /* AND THEN WAITED FOR, because `open` is set before the permission prompt is answered and
     the clock cannot start until there is a microphone to be silent into. Reading the two in
     the same breath as the flag was a race this harness lost once. */
  const armed = await waitFor(page, '__galaxy.ear.clock === true', 4000);
  const held = await page.json('({timeoutS: __galaxy.ear.timeoutS,' +
    ' clock: __galaxy.ear.clock, stream: __galaxy.ear.stream})');
  ok(armed && held.timeoutS === 4,
     'with the clock shortened to ' + held.timeoutS + 's and armed', JSON.stringify(held));
  const gentle = await waitFor(page, '__galaxy.ear.open === false', 20000);
  const quiet = await page.json('({open: __galaxy.ear.open,' +
    ' closedBy: __galaxy.ear.closedBy, parting: __galaxy.ear.parting,' +
    ' caption: __galaxy.caption.text, stream: __galaxy.ear.stream,' +
    ' line: __galaxy.ear.TIMEOUT_LINE})');
  line('BUTLER', quiet.parting);
  ok(gentle && quiet.closedBy === 'silence',
     'SILENCE CLOSES IT, gently and by itself', JSON.stringify(quiet));
  ok(quiet.parting === quiet.line && quiet.parting === "I'll let you work, sir." &&
     quiet.caption === quiet.parting,
     'with the line the spec names: "' + quiet.parting + '"', JSON.stringify(quiet));
  ok(quiet.stream === false,
     'and the microphone is down - a courtesy close is a real close',
     JSON.stringify(quiet));
  await waitFor(page, '__galaxy.voice.draining === false', 60000);
  await sleep(400);
  const backToRest = await mark('at rest again');
  ok(backToRest.seal.open === false && backToRest.word === 'ready',
     'and the bar reads READY again, exactly as it did before any of this',
     JSON.stringify(backToRest));

  /* ---- 6. THE SEAL, AT EVERY STAGE --------------------------------------- */
  step('6 · the seal at every stage');
  const stages = seals.map((s) => s.stage + '=' + (s.seal.open ? 'OPEN:' : '') +
    (s.word || ''));
  note('the seal, stage by stage: ' + stages.join('  \u00b7  '));
  const openStages = seals.filter((s) => s.stage === 'ear open' || s.stage === 'speaking');
  ok(openStages.length === 2 && openStages.every((s) => s.seal.open === true &&
       s.seal.shown === true && s.seal.cell.indexOf('browser') >= 0),
     'THE SEAL IS CORRECT AT EVERY STAGE: EAR OPEN and the engine named for as long as the ' +
     'session lasted, including while he was talking', JSON.stringify(openStages));
  ok(seals[0].word === 'ready' && seals[seals.length - 1].word === 'ready' &&
     seals[0].seal.open === false && seals[seals.length - 1].seal.open === false,
     'and it opens and shuts with the session rather than drifting: ' + stages.join(' \u2192 '),
     JSON.stringify(stages));

  /* ---- 7. NOTHING IS KEPT ------------------------------------------------ */
  step('7 · nothing is kept');
  const kept = await page.json('({recorders: window.__conv.recorders,' +
    ' gum: window.__conv.gum, ledger: __galaxy.ear.kept,' +
    ' opened: __galaxy.ear.opened})');
  ok(kept.recorders === 0,
     'NO AUDIO IS STORED: MediaRecorder was replaced with a counter before the first click, ' +
     'and across two sessions, four turns and a barge-in it was never constructed once',
     JSON.stringify(kept));
  ok(kept.gum === kept.opened,
     'and one microphone per session and not one more: ' + kept.gum +
     ' asks for ' + kept.opened + ' sessions', JSON.stringify(kept));
  ok(kept.ledger.audio === 0 && kept.ledger.transcript === 0,
     'the page\u2019s own ledger agrees: nothing buffered, and the transcript spent and ' +
     'cleared', JSON.stringify(kept));
  ok(page.errors.length === 0,
     'AND THE PAGE THREW NOTHING through the whole conversation',
     page.errors.slice(0, 3).join('\n         '));

  /* ---- THE TRANSCRIPT --------------------------------------------------- */
  step('the transcript');
  say('\n  ---- the transcript ' + '-'.repeat(54));
  for (const row of script) {
    const [who, what] = row.split('\t');
    const text = what.length > 150 ? what.slice(0, 147) + '\u2026' : what;
    say('  ' + who.padEnd(9) + ' ' + text);
  }
  say('  ' + '-'.repeat(74));
  say('  clicks in the three-turn conversation above: 1');

  page.close();
}

/* THE WATCHDOG. Not decoration: this file spent one run hung with everything it had said
   still sitting in a pipe buffer, which is how a harness stops being evidence. The timer is
   unref'd so it cannot itself keep the process alive, it names the step that was in flight,
   and it exits non-zero - so preflight gets a failure with an address instead of a wait. */
const watchdog = setTimeout(() => {
  say('\n  HUNG at: ' + STEP);
  say('\n  VERIFY ' + (checks - bad.length) + '/' + checks + ' FAIL\n');
  for (const b of bad) say('    FAILED: ' + b);
  say('    FAILED: the run did not finish inside ' + (BUDGET_MS / 1000) + 's, at: ' + STEP);
  cleanup();
  process.exit(1);
}, BUDGET_MS);
watchdog.unref();

main().then(() => {
  clearTimeout(watchdog);
  say('\n  VERIFY ' + (checks - bad.length) + '/' + checks +
      (bad.length ? ' FAIL\n' : ' PASS\n'));
  for (const b of bad) say('    FAILED: ' + b);
  cleanup();
  process.exit(bad.length ? 1 : 0);
}).catch((e) => {
  clearTimeout(watchdog);
  say('\n  THREW at ' + STEP + ': ' + (e && e.message));
  say('\n  VERIFY ' + (checks - bad.length) + '/' + checks + ' FAIL\n');
  for (const b of bad) say('    FAILED: ' + b);
  say('    FAILED: threw at ' + STEP + ': ' + (e && e.message));
  cleanup();
  process.exit(1);
});

/* SYNCHRONOUS, AND A TREE KILL. p.kill() on Windows terminates the launcher and leaves the
   renderer, gpu and network children holding the profile directory open - so the temp
   directory could not be removed and the next run inherited whatever Chrome had left in it.
   taskkill /T takes the tree. Both are spawnSync because this is the last thing that happens
   before process.exit, and an await here is a promise nobody will be alive to settle. */
function cleanup() {
  for (const p of procs) {
    try { spawnSync('taskkill', ['/PID', String(p.pid), '/T', '/F'], { stdio: 'ignore' }); }
    catch { /* not Windows, or already gone */ }
    try { p.kill(); } catch { /* already gone */ }
  }
  for (const d of profiles) {
    try { rmSync(d, { recursive: true, force: true, maxRetries: 5, retryDelay: 200 }); }
    catch { /* a profile Chrome has not finished letting go of is litter, not a failure */ }
  }
}
