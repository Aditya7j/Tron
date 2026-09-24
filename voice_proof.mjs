/* THE UNBROKEN VOICE, measured end to end - because the complaint was "it fades out and
 * never reaches the last word", and neither a screenshot nor a unit test can see that.
 *
 * WHAT IS BEING PROVED, and it is one thing: A LONG ANSWER IS READ TO ITS FINAL WORD.
 * Everything below exists to make that falsifiable rather than reassuring:
 *
 *   THE FULL-READ CONTRACT. One answer of about a minute and a half goes through the
 *     funnel. The last chunk's end must have fired, the queue must be empty, speakDone
 *     must have gone up exactly once, and the concatenation of every chunk the page
 *     wrapped must equal the text that went in - word for word, not approximately.
 *   THE GAP. Every chunk's start and end is timestamped by the page; the worst silence
 *     between one ending and the next beginning is recomputed HERE, in Node, from the raw
 *     marks and then compared against the page's own arithmetic. Two independent sums
 *     agreeing is evidence; one number is a claim.
 *   THE INDICATOR. The SPEAKING light is sampled from inside the page for the whole
 *     answer. It must still be lit at the end of the last chunk and out after it, because
 *     an indicator that goes dark mid-answer is how this defect looked from the outside.
 *   ONE FORCED FAILURE. A single /say request is made to fail on purpose. That chunk must
 *     be skipped with a line in the log AND THE QUEUE MUST STILL FINISH - one stumble is
 *     one missing sentence, not the end of the answer.
 *   PIPER ABSENT. Then every /say is made to fail. The page must NAME its fallback to the
 *     browser's own voices and still read the line to the end.
 *   AND THE CANCEL LAW, read out of the page's own source: only the stop control, a new
 *     question, the microphone opening and the reset may empty the queue. An SSE
 *     heartbeat, a panel render, a camera move, a focus tick and a proposal card must not
 *     be able to reach it at all.
 *
 * THE HARNESS WRAPS speakLine(), NOT speechSynthesis. That is the point of the funnel: a
 * proof that reached past it into the engine would be a proof about Chrome rather than
 * about this page's queue. The one place an utterance is inspected is labelled an
 * observer, and it only has anything to look at on the web path.
 *
 * Headed, GPU-backed, and NOT muted: the subject is what comes out of the speakers on the
 * machine in front of you. IT WILL TALK OUT LOUD FOR ABOUT TWO MINUTES. It asks the server
 * for audio and for nothing else - no mail, no diary, no model.
 *
 * Usage:  python server.py 2> server-trace.log   then   node voice_proof.mjs
 */
import { spawn } from 'node:child_process';
import { mkdtempSync, rmSync, existsSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const GALAXY = 'http://127.0.0.1:4700';
const PORT = 9238;
const CDP = 'http://127.0.0.1:' + PORT;
const CHROMES = [
  'C:/Program Files/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Google/Chrome/Application/chrome.exe',
  process.env.LOCALAPPDATA + '/Google/Chrome/Application/chrome.exe',
];
const GAP_MAX_MS = 2000;      // the spec's ceiling on silence between two chunks
const SPEAK_MAX = 180;        // and its ceiling on the length of one chunk
const SPEECH_TIMEOUT_MS = 260000;
const SHORT_TIMEOUT_MS = 90000;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const collapse = (s) => String(s).replace(/\s+/g, ' ').trim();

/* About a minute and a half at rate 1.0, and deliberately ORDINARY prose: long sentences,
   short sentences, a semicolon, a dash, a number, a quoted phrase. A paragraph made of
   nothing but neat full stops would prove only that the easy case works. */
const LONG = [
  'Right, sir. Here is the whole of what the notes say about the wholesale side of the ' +
  'business, read out in order, so you can hear it while you are doing something else.',
  'Seven accounts bring in twelve thousand six hundred pounds a month, which is about ' +
  'twenty one per cent of revenue, and it is the most stable line in the monthly summary.',
  'The oldest of them is a bookshop café called Ledger and Loom; they take eighteen ' +
  'kilograms a week of the house blend, they found us at the farmers market booth, and ' +
  'they have never once been late paying.',
  'Third Rail Diner takes twelve kilograms a week, blend only, and is price sensitive - ' +
  'which in practice means they ask about the price every quarter and then renew anyway.',
  'Hartwell Hotel takes nine kilograms plus a decaf line. That is the account that ' +
  'demanded consistency, and it is the reason every batch now gets logged in the roasting ' +
  'schedule, which has turned out to be worth far more than the account itself.',
  'Two office contracts take six kilograms a week between them: low touch, high margin, ' +
  'and almost no correspondence.',
  'Two small cafés take four kilograms each, and both of them came in from the local press ' +
  'coverage rather than from anything we did deliberately.',
  'How it works, mechanically: roasted on Tuesday, delivered Wednesday morning, invoiced ' +
  'net fifteen, and the whole round is done by eleven.',
  'The thing worth your attention is the concentration. One account is a quarter of the ' +
  'wholesale line, and it is the one with no contract, only eleven years of goodwill.',
  'That is the end of the notes on wholesale. Nothing here needed the web, and nothing ' +
  'here needed a model - it is all read from your own files.',
].join(' ');

/* Six sentences, for the two failure proofs. Short on purpose: the long read above has
   already settled the long case, and the question here is only whether a hole in the
   middle of a queue stops the queue. The marker word is how one specific chunk is picked
   out for sabotage - by its TEXT, because with a one-ahead buffer the order requests
   arrive in is not quite the order the chunks are read in. */
const MARKER = 'trebuchet';
const SHORT = [
  'One. The first line of the short answer, and nothing is wrong with it yet.',
  'Two. The second line follows the first and is also perfectly ordinary.',
  'Three. This line is the ' + MARKER + ', and it is the one that will be sabotaged.',
  'Four. The line after the hole, which is the one that used to never arrive.',
  'Five. And another after that, to prove the queue kept its place.',
  'Six. The last line, sir, which is the whole point of the exercise.',
].join(' ');

let checks = 0; const bad = [];
const ok = (c, claim, detail) => {
  checks++; console.log((c ? '  ok   ' : '  FAIL ') + claim);
  if (!c) { bad.push(claim); if (detail) console.log('         ' + detail); }
};
const note = (m) => console.log('  note ' + m);
const procs = []; const profiles = [];

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
  async evaluate(expression, userGesture = false) {
    const r = await this.send('Runtime.evaluate',
      { expression, returnByValue: true, awaitPromise: true, userGesture });
    if (r.result && r.result.exceptionDetails) {
      /* The description carries the message and the stack; text alone is just "Uncaught",
         which tells you a harness run died and nothing about where. */
      const d = r.result.exceptionDetails;
      throw new Error('page threw: ' + ((d.exception && (d.exception.description ||
        d.exception.value)) || d.text) + '  <- ' + expression.slice(0, 120));
    }
    return r.result && r.result.result ? r.result.result.value : undefined;
  }
  async json(e) { return JSON.parse(await this.evaluate('JSON.stringify(' + e + ')') || 'null'); }
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

/* A GENUINE GESTURE. document.body.click() does not unlock audio - Chrome wants an event
   it believes came from a human, which over CDP means Input.dispatchMouseEvent. */
async function realClick(page, x, y) {
  for (const type of ['mousePressed', 'mouseReleased']) {
    await page.send('Input.dispatchMouseEvent',
      { type, x, y, button: 'left', clickCount: 1, buttons: type === 'mousePressed' ? 1 : 0 });
    await sleep(40);
  }
}

/* THE ALLOWLIST, WALKED AGAIN, HERE. Same rule as the page's: normalise, then exact,
   then prefix, then substring. Written out a second time on purpose - if this and the
   page ever disagree about which voice the machine's inventory deserves, that disagreement
   is the finding, and one shared implementation would hide it. */
const norm = (s) => String(s == null ? '' : s).toLowerCase().replace(/\s+/g, ' ').trim();
/* The platform's packaging removed: Edge says "Microsoft Guy Online (Natural) - English
   (United States)" and Chrome says "Microsoft David - English (United States)" for voices
   of the same family, so an allowlist that matches only the literal string finds nothing in
   one of the two browsers. */
const bare = (s) => norm(String(s == null ? '' : s)
  .replace(/\(natural\)/gi, ' ').replace(/\bonline\b|\bdesktop\b/gi, ' '));
function bestFor(order, names) {
  const pool = names.map(norm);
  const find = (w) => {
    if (!w) return -1;
    let hit = pool.findIndex((n) => n === w);
    if (hit < 0) hit = pool.findIndex((n) => n.indexOf(w) === 0);
    if (hit < 0) hit = pool.findIndex((n) => n.indexOf(w) >= 0);
    return hit;
  };
  for (let i = 0; i < order.length; i++) {
    const hit = find(norm(order[i]));
    if (hit >= 0) return { rank: i + 1, name: names[hit], how: 'literal' };
  }
  for (let i = 0; i < order.length; i++) {
    const hit = find(bare(order[i]));
    if (hit >= 0) return { rank: i + 1, name: names[hit], how: 'without the platform suffix' };
  }
  return { rank: 0, name: '', how: '' };
}

/* THE INSTRUMENTS, installed once and reused by all three reads. Two of them:

   THE FUNNEL WRAP. speakLine() itself, so every line this harness sends is recorded as
   the page received it. This is the wrap the spec asks for, and it is on the funnel
   rather than on speechSynthesis for the reason the funnel exists.

   THE /say SWITCH. A fetch wrapper that can fail one named chunk or all of them, so
   "what happens when a chunk stumbles" and "what happens when piper is absent" are
   things this file can cause rather than wait for. It matches ONLY /say - the health
   poll and everything else go straight through. */
const INSTRUMENTS = `(function(){
  if (window.__vp) return 'already';
  window.__vp = { lines: [], given: [], samples: [], done: [], gapBad: 0, litAtEnd: null,
                  t0: 0, timer: null, failMark: '', failAll: false, sayCalls: 0,
                  sayFailed: 0 };
  var funnel = __galaxy.speech.speakLine;
  __galaxy.speech.speakLine = function (t) {
    window.__vp.lines.push(String(t));
    return funnel(t);
  };
  /* An OBSERVER, not a funnel: what the browser's engine was handed, which is a
     different question from what the page was asked to say, and one that only has an
     answer on the web path. */
  var rawSpeak = speechSynthesis.speak.bind(speechSynthesis);
  speechSynthesis.speak = function (u) {
    window.__vp.given.push({ chars: (u.text || '').length, rate: u.rate, pitch: u.pitch,
      volume: u.volume, voice: u.voice ? u.voice.name : '', lang: u.lang });
    return rawSpeak(u);
  };
  var rawFetch = window.fetch;
  window.fetch = function (u, o) {
    var url = String((u && u.url) || u || '');
    if (url.indexOf('/say') >= 0) {
      window.__vp.sayCalls++;
      var body = '';
      try { body = String((o && o.body) || ''); } catch (e) { body = ''; }
      var doomed = window.__vp.failAll ||
        (window.__vp.failMark && body.indexOf(window.__vp.failMark) >= 0);
      if (doomed) {
        window.__vp.sayFailed++;
        return Promise.resolve(new Response(
          JSON.stringify({ ok: false, error: 'forced failure, for the proof' }),
          { status: 503, headers: { 'Content-Type': 'application/json' } }));
      }
    }
    return rawFetch.apply(window, arguments);
  };
  addEventListener('speakDone', function (e) { window.__vp.done.push(e.detail); });
  return 'wrapped';
})()`;

/* One read, start to finish, watched from inside the page the whole way. Returns
   everything Node needs to do its own arithmetic afterwards. */
async function readOut(page, text, timeout) {
  await page.evaluate(`(function(){
    window.__vp.lines = []; window.__vp.given = []; window.__vp.samples = [];
    window.__vp.done = []; window.__vp.gapBad = 0; window.__vp.litAtEnd = null;
    window.__vp.t0 = Date.now();
    /* Sampled from INSIDE the page every 120ms, so the continuity of the voice is not
       measured through a WebSocket. A sample where the indicator has gone dark with the
       queue still working is exactly the defect this whole arrangement exists to end. */
    window.__vp.timer = setInterval(function () {
      var v = __galaxy.voice;
      var c = v.chunks;
      var last = c.length ? c[c.length - 1] : null;
      var done = !!(last && last.end > 0) && v.queue === 0 && !v.draining;
      var lit = document.getElementById('status').className === 'speaking';
      window.__vp.samples.push({ at: Date.now(), lit: lit, draining: v.draining,
        queue: v.queue, now: v.now, engine: v.engine, ka: v.keepAlive, done: done });
      if (!done && Date.now() - window.__vp.t0 > 3000 && !lit) window.__vp.gapBad++;
      if (!done) window.__vp.litAtEnd = lit;
    }, 120);
    return __galaxy.speech.speakLine(${JSON.stringify(text)});
  })()`);
  const started = Date.now();
  const finished = await waitFor(page, 'window.__vp.done.length > 0', timeout);
  const wall = Date.now() - started;
  await page.evaluate('clearInterval(window.__vp.timer)');
  const out = await page.json(`({ finished: ${finished}, wall: ${wall},
    marks: __galaxy.voice.chunks, done: window.__vp.done,
    samples: window.__vp.samples, gapBad: window.__vp.gapBad,
    litAtEnd: window.__vp.litAtEnd, lines: window.__vp.lines,
    given: window.__vp.given, notes: __galaxy.voice.notes,
    engine: __galaxy.voice.engine, engineWhy: __galaxy.voice.engineWhy,
    down: __galaxy.voice.down,
    queue: __galaxy.voice.queue, draining: __galaxy.voice.draining,
    pageGap: __galaxy.voice.gapMax, stalls: __galaxy.voice.stalls,
    lit: document.getElementById('status').className === 'speaking',
    sayCalls: window.__vp.sayCalls, sayFailed: window.__vp.sayFailed })`);
  return out;
}

/* The gap, recomputed in Node from the raw marks, plus which chunk it fell before. */
function gapOf(marks) {
  let worst = 0, at = -1;
  for (let i = 1; i < marks.length; i++) {
    const g = marks[i].start - marks[i - 1].end;
    if (marks[i - 1].end && marks[i].start && g > worst) { worst = g; at = i; }
  }
  return { worst, at };
}

async function main() {
  console.log('\n  the unbroken voice: one long answer, read to its final word, out loud\n');
  const exe = CHROMES.find((p) => existsSync(p));
  if (!exe) throw new Error('no chrome.exe');
  const health = await (await fetch(GALAXY + '/health')).json();
  note('server up · /say reports ' + JSON.stringify(health.say));

  /* ---- 0. THE CANCEL LAW, READ OUT OF THE SOURCE -------------------------- */
  /* Before anything is spoken, because it is a claim about what CANNOT happen and no
     amount of listening can establish that. */
  const src = await (await fetch(GALAXY + '/index.html')).text();
  const callers = [...src.matchAll(/speakCancel\('([^']+)'\)/g)].map((m) => m[1]);
  note('speakCancel callers: ' + JSON.stringify(callers));
  ok(callers.length === 4,
     'exactly four lines in the page may empty the queue', JSON.stringify(callers));
  ok(/new question/.test(callers.join('|')) && /stop control/.test(callers.join('|')) &&
     /reset/.test(callers.join('|')) && /microphone/.test(callers.join('|')),
     'and they are the ones the law permits: a new question, the stop control, the reset ' +
     'button and the microphone opening - every one of them a person saying so',
     JSON.stringify(callers));
  ok(/THE CANCEL LAW/.test(src) && /not an SSE heartbeat/i.test(src),
     'the law is written at the cancel site, naming the things that may NOT touch the ' +
     'queue - heartbeats, panel renders, camera moves, focus ticks, proposal cards');
  /* The engine's own cancel, still allowed inside the speech section - a dead utterance
     has to be cleared off the engine before the next one can start - and nowhere else. */
  const tail = src.split('THE FUNNEL, AND THE QUEUE')[1] || '';
  const raw = [...src.matchAll(/speechSynthesis\.cancel\(\)/g)].length;
  const rawInSection = [...tail.matchAll(/speechSynthesis\.cancel\(\)/g)].length;
  ok(raw > 0 && raw === rawInSection,
     'and every remaining speechSynthesis.cancel() lives inside the speech section: ' +
     rawInSection + ' of ' + raw + ' - nothing outside it can reach the engine',
     JSON.stringify({ total: raw, inSection: rawInSection }));

  const profile = mkdtempSync(join(tmpdir(), 'voice-'));
  profiles.push(profile);
  /* NOT muted, and headed: ?mute=1 would make every check below a check about bookkeeping.
     The autoplay flag is NOT set - the whole point is that the real gesture works. */
  const chrome = spawn(exe, [
    '--remote-debugging-port=' + PORT, '--user-data-dir=' + profile,
    '--no-first-run', '--no-default-browser-check',
    '--window-size=1200,820', '--new-window', GALAXY,
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
  try { await page.send('Page.bringToFront'); } catch (e) { note('bringToFront: ' + e.message); }
  ok(await waitFor(page, '!!(window.__galaxy && window.__galaxy.voice)', 30000),
     'the viewer is up and exposes the voice');

  /* ---- 1. WHICH VOICE, AND WHY -------------------------------------------- */
  /* Still asked first even when piper is the engine, because the web voice is the
     FALLBACK, and a fallback nobody has checked is not a fallback. */
  ok(await waitFor(page, 'speechSynthesis.getVoices().length > 0', 20000),
     'the machine has voices to choose from');
  await page.evaluate('__galaxy.speech.refreshVoice()');
  const v = await page.json('({name: __galaxy.voice.name, lang: __galaxy.voice.lang,' +
    ' why: __galaxy.voice.why, pinned: __galaxy.voice.pinned,' +
    ' allowlisted: __galaxy.voice.allowlisted, order: __galaxy.voice.ORDER,' +
    ' list: __galaxy.voice.list, max: __galaxy.voice.MAX,' +
    ' keepAlive: __galaxy.voice.KEEPALIVE_MS, stall: __galaxy.voice.STALL_MS,' +
    ' deadPad: __galaxy.voice.DEAD_PAD_MS})');
  note('this machine has ' + v.list.length + ' voices:');
  v.list.forEach((n) => console.log('         ' + n));
  note('CHOSEN: ' + v.name + ' (' + v.lang + ')  ·  because: ' + v.why);
  ok(!!v.name, 'a voice was chosen and it has a name', JSON.stringify(v.why));
  ok(v.max === SPEAK_MAX, 'the chunk ceiling is ' + SPEAK_MAX + ' characters, as specified',
     JSON.stringify(v.max));
  ok(v.keepAlive === 5000 && v.stall === 3000 && v.deadPad === 5000,
     'and the three timers are the ones the spec named: keep-alive 5s, a 3s stall ' +
     'watchdog, and a dead-utterance deadline of the estimate plus 5s',
     JSON.stringify({ keepAlive: v.keepAlive, stall: v.stall, deadPad: v.deadPad }));

  const names = v.list.map((s) => s.replace(/ \[[^\]]*\]$/, ''));
  const best = bestFor(v.order, names);
  if (best.rank) {
    ok(norm(v.name) === norm(best.name),
       'AND IT IS THE BEST ONE THIS MACHINE HAS: allowlist #' + best.rank + ', "' +
       best.name + '" (matched ' + best.how + ') - recounted here from the inventory ' +
       'rather than taken on trust',
       JSON.stringify({ chose: v.name, shouldHave: best.name, rank: best.rank }));
    /* The page must also have understood WHY, not just landed in the right place: a fallback
       that happens to agree with allowlist #5 is luck, and luck stops working on the next
       machine. */
    ok(new RegExp('allowlist #' + best.rank + '\\b').test(v.why),
       'and it says it got there by the list, not by the generic male fallback: "' +
       v.why + '"', JSON.stringify(v.why));
    ok(v.allowlisted === true, 'and the page agrees that its choice is on the allowlist');
  } else {
    note('none of the six allowlisted voices exist on this machine - checking the ' +
         'fallback rule instead of the list');
    ok(/male|voice_name/.test(v.why) || /no male voice/.test(v.why),
       'the fallback names the rule that fired rather than shrugging: "' + v.why + '"',
       JSON.stringify(v.why));
    ok(/^en/i.test(v.lang),
       'and what it fell through to is at least an English voice (' + v.lang + ')');
  }

  /* ---- 2. WHICH ENGINE, NAMED --------------------------------------------- */
  /* AFTER THE PAGE HAS ASKED. The engine is decided by the boot health poll, and until that
     answer lands the page honestly reports "web, not asked yet" - which is the state this
     used to catch. It read the default a second after load, said the page was on the wrong
     engine, and then every check that followed asserted against a browser voice while the
     page was about to spend the run on piper: one race, twenty-one failures, and none of
     them about the voice. The page is waited for instead. Its own words are the signal -
     "not asked yet" is exactly the sentence that means the question is still in the air. */
  const asked = await waitFor(page,
    '__galaxy.voice.engineWhy && __galaxy.voice.engineWhy !== "not asked yet"', 15000);
  ok(asked, 'the page asked the server which engine it may use, and got an answer',
     await page.evaluate('__galaxy.voice.engineWhy'));
  const eng = await page.json('({engine: __galaxy.voice.engine,' +
    ' why: __galaxy.voice.engineWhy})');
  note('ENGINE: ' + eng.engine + '  ·  because: ' + eng.why);
  ok(eng.engine === (health.say && health.say.ready ? 'piper' : 'web'),
     'the page is on the engine the server said it could have (' + eng.engine + ')',
     JSON.stringify({ page: eng, server: health.say }));
  ok(eng.why.length > 8 && /piper|browser/.test(eng.why),
     'and it can say WHICH engine and why in a sentence: "' + eng.why + '"');

  /* ---- 3. THE CUT, BEFORE A WORD IS SPOKEN -------------------------------- */
  const chunks = await page.json('__galaxy.voice.split(' + JSON.stringify(LONG) + ')');
  const longest = chunks.reduce((a, c) => Math.max(a, c.length), 0);
  note('the answer is ' + LONG.length + ' characters, cut into ' + chunks.length +
       ' chunks, longest ' + longest);
  ok(chunks.length > 8, 'a long answer is cut into many chunks, not sent as one');
  /* The one licensed exception is a single unbroken token longer than the ceiling - a URL
     or a hash - which is left whole because half a URL read aloud is a noise. */
  const over = chunks.filter((c) => c.length > SPEAK_MAX && /\s/.test(c));
  ok(over.length === 0, 'and no chunk containing a word boundary exceeds ' + SPEAK_MAX +
     ' characters (longest ' + longest + ')', JSON.stringify(over.slice(0, 2)));
  const enders = chunks.filter((c) => /[.!?…][")'\]]?$/.test(c.trim())).length;
  ok(enders >= Math.ceil(chunks.length * 0.6),
     'they end on sentence boundaries rather than at the character limit (' + enders +
     ' of ' + chunks.length + ')', JSON.stringify(chunks.map((c) => c.slice(-24))));
  ok(collapse(chunks.join(' ')) === collapse(LONG),
     'AND THE CONCATENATION OF THE CHUNKS IS THE ANSWER, character for character - not ' +
     'one word of it is lost in the cutting',
     JSON.stringify({ in: collapse(LONG).length, out: collapse(chunks.join(' ')).length }));

  /* ---- 4. THE GESTURE THAT UNLOCKS IT ------------------------------------- */
  await realClick(page, 600, 400);
  ok(await waitFor(page, '__galaxy.speech.unlocked === true', 8000),
     'one real click unlocks the audio, as the autoplay policy requires');
  ok(await page.evaluate('__galaxy.speech.muted === false'),
     'and this run is NOT muted - what follows is a measurement of the speakers');
  await sleep(1500);                            // let the boot greeting finish speaking
  await page.evaluate('__galaxy.speech.cancel("the harness clearing the greeting")');
  await sleep(500);
  ok(await page.evaluate(INSTRUMENTS) === 'wrapped',
     'the harness is wrapped around speakLine() - THE FUNNEL - rather than around ' +
     'speechSynthesis, so what follows is a proof about this page\u2019s queue');

  /* ---- 5. THE FULL READ -------------------------------------------------- */
  note('reading ' + LONG.length + ' characters out loud on the ' + eng.engine +
       ' path - about a minute and a half, and you should hear it…');
  const r = await readOut(page, LONG, SPEECH_TIMEOUT_MS);
  const gap = gapOf(r.marks);
  const spoken = r.marks.filter((m) => m.start && m.end).length;
  const skipped = r.marks.filter((m) => m.skipped).length;
  const errored = r.marks.filter((m) => m.error).length;
  note('chunks: ' + r.marks.length + ' queued · ' + spoken + ' spoken · ' + skipped +
       ' skipped · ' + errored + ' errored · worst gap ' + gap.worst + 'ms' +
       (gap.at >= 0 ? ' (before chunk ' + gap.at + ')' : '') + ' · ' + r.stalls + ' stalls');
  if (r.notes.length) r.notes.forEach((n) => console.log('         ' + n));

  ok(r.finished, 'IT READ THE WHOLE ANSWER: speakDone went up after ' +
     (r.wall / 1000).toFixed(1) + 's', 'timed out after ' + (r.wall / 1000).toFixed(0) + 's');
  ok(r.done.length === 1, 'speakDone fired exactly ONCE - one answer, one completion',
     JSON.stringify(r.done.length));
  const last = r.marks[r.marks.length - 1] || {};
  ok(!!last.end, 'THE LAST CHUNK\u2019S END FIRED - the final word was reached, not ' +
     'assumed', JSON.stringify(last));
  ok(r.queue === 0 && r.draining === false,
     'AND THE QUEUE IS EMPTY: nothing left unstarted and the funnel has stopped draining',
     JSON.stringify({ queue: r.queue, draining: r.draining }));
  ok(collapse((r.done[0] && r.done[0].text) || '') === collapse(LONG),
     'AND THE CONCATENATION OF THE CHUNKS THE PAGE WRAPPED EQUALS THE TEXT THAT WENT IN - ' +
     'the read was complete, not merely long',
     JSON.stringify({ inChars: collapse(LONG).length,
                      outChars: collapse((r.done[0] && r.done[0].text) || '').length }));
  ok(spoken === r.marks.length && skipped === 0,
     'every chunk started and ended, and none had to be skipped',
     JSON.stringify(r.marks.filter((m) => !m.end || m.skipped).slice(0, 4)));
  ok(gap.worst < GAP_MAX_MS,
     'NO SILENCE OVER ' + (GAP_MAX_MS / 1000) + 's BETWEEN CHUNKS: worst was ' + gap.worst +
     'ms, measured in Node from the page\u2019s own timestamps',
     JSON.stringify({ worst: gap.worst, at: gap.at,
                      marks: r.marks.slice(Math.max(0, gap.at - 1), gap.at + 1) }));
  ok(Math.abs(r.pageGap - gap.worst) <= 1,
     'and the page\u2019s own arithmetic agrees (' + r.pageGap + 'ms vs ' + gap.worst +
     'ms), so the number in the instrument can be trusted next time');
  ok(r.wall > 60000,
     'and it really was a long answer, not a fast failure: ' + (r.wall / 1000).toFixed(1) +
     's of speech', (r.wall / 1000).toFixed(1) + 's');

  /* THE INDICATOR. */
  const litSamples = r.samples.filter((s) => s.lit).length;
  note('indicator: ' + r.samples.length + ' samples, ' + litSamples + ' with SPEAKING lit, ' +
       r.gapBad + ' dark mid-answer');
  ok(r.gapBad === 0,
     'SPEAKING STAYED LIT UNTIL THE LAST CHUNK ENDED: not one of ' + r.samples.length +
     ' samples caught the indicator dark with the queue still working',
     JSON.stringify({ dark: r.gapBad, total: r.samples.length }));
  ok(r.litAtEnd === true,
     'it was still lit on the last sample before the queue emptied',
     JSON.stringify(r.litAtEnd));
  ok(r.lit === false,
     'and it went out when the queue emptied, rather than staying lit forever');
  ok(await page.evaluate('__galaxy.voice.keepAlive === false'),
     'the keep-alive cleared itself at the end, rather than ticking forever');
  ok(r.lines.length === 1,
     'and the whole answer went through ONE call to the funnel (' + r.lines.length + ')',
     JSON.stringify(r.lines.length));

  /* WHAT THE FAR END WAS HANDED. Only the web path has utterances to inspect; on the
     piper path the equivalent evidence is that every chunk came back as audio, which the
     skipped count above has already settled. */
  if (r.engine === 'web') {
    const rates = [...new Set(r.given.map((g) => g.rate))];
    const pitches = [...new Set(r.given.map((g) => g.pitch))];
    const vols = [...new Set(r.given.map((g) => g.volume))];
    const voices = [...new Set(r.given.map((g) => g.voice))];
    note('as the engine received them: rate ' + JSON.stringify(rates) + ' · pitch ' +
         JSON.stringify(pitches) + ' · volume ' + JSON.stringify(vols) + ' · voice ' +
         JSON.stringify(voices));
    ok(vols.length === 1 && vols[0] === 1,
       'VOLUME 1.0 ON EVERY UTTERANCE, read off the utterances rather than off the source',
       JSON.stringify(vols));
    ok(rates.length === 1 && rates[0] === 1, 'rate 1.0, unhurried', JSON.stringify(rates));
    ok(pitches.length === 1 && Math.abs(pitches[0] - 0.9) < 0.001,
       'pitch 0.9 - the weight the spec asked for', JSON.stringify(pitches));
    ok(voices.length === 1 && norm(voices[0]) === norm(v.name),
       'all of it in the one chosen voice: ' + JSON.stringify(voices[0]),
       JSON.stringify({ given: voices, chosen: v.name }));
  } else {
    const piped = r.marks.filter((m) => m.source === 'piper').length;
    ok(piped === r.marks.length,
       'every one of the ' + piped + ' chunks was audio from /say rather than a browser ' +
       'utterance - this was the local voice all the way down',
       JSON.stringify(r.marks.filter((m) => m.source !== 'piper').slice(0, 3)));
    ok(r.sayCalls >= r.marks.length,
       'and the page asked /say for at least as many chunks as it read (' + r.sayCalls +
       ' requests for ' + r.marks.length + ' chunks), which is the one-ahead buffer',
       JSON.stringify({ calls: r.sayCalls, chunks: r.marks.length }));
  }

  /* ---- 6. ONE FORCED FAILURE, AND THE QUEUE STILL FINISHES ---------------- */
  if (r.engine === 'piper') {
    note('sabotaging the chunk containing "' + MARKER + '" and reading again…');
    await page.evaluate('window.__vp.failMark = ' + JSON.stringify(MARKER) + '; 1');
    const f = await readOut(page, SHORT, SHORT_TIMEOUT_MS);
    await page.evaluate('window.__vp.failMark = ""; 1');
    const hole = f.marks.filter((m) => m.skipped);
    note('with one chunk sabotaged: ' + f.marks.length + ' chunks · ' + hole.length +
         ' skipped · finished ' + f.finished);
    if (f.notes.length) f.notes.forEach((n) => console.log('         ' + n));
    ok(f.sayFailed >= 1, 'the sabotage landed: ' + f.sayFailed + ' /say request(s) refused',
       JSON.stringify(f.sayFailed));
    ok(hole.length === 1,
       'exactly one chunk was skipped - the sabotaged one, and no collateral',
       JSON.stringify(hole));
    ok(f.notes.some((n) => /skipped/.test(n)),
       'AND IT SAID SO: one line in the log naming the chunk it could not speak',
       JSON.stringify(f.notes));
    ok(f.finished && f.queue === 0 && !f.draining,
       'AND THE QUEUE STILL FINISHED: speakDone went up, the queue emptied, the tail did ' +
       'not die because one chunk stumbled',
       JSON.stringify({ finished: f.finished, queue: f.queue, draining: f.draining }));
    const fLast = f.marks[f.marks.length - 1] || {};
    ok(!!fLast.end && !fLast.skipped,
       'and the LAST chunk was spoken - the sentence after the hole is the one that used ' +
       'to never arrive', JSON.stringify(fLast));
    ok(f.marks.filter((m) => m.end && !m.skipped).length === f.marks.length - 1,
       'every chunk except the sabotaged one was read (' +
       f.marks.filter((m) => m.end && !m.skipped).length + ' of ' + f.marks.length + ')');
    await sleep(600);

    /* ---- 7. PIPER ABSENT, FALLBACK NAMED, STILL FINISHES ----------------- */
    note('now failing EVERY /say - the local voice is absent and the page must name its ' +
         'fallback and still finish…');
    await page.evaluate('window.__vp.failAll = true; 1');
    const a = await readOut(page, SHORT, SHORT_TIMEOUT_MS);
    await page.evaluate('window.__vp.failAll = false; 1');
    note('with piper absent: ' + a.marks.length + ' chunks · ' +
         a.marks.filter((m) => m.source === 'web').length + ' read by the browser · ' +
         'finished ' + a.finished);
    if (a.notes.length) a.notes.forEach((n) => console.log('         ' + n));
    ok(a.notes.some((n) => /falling back to/.test(n)),
       'THE FALLBACK IS NAMED, not silent: the log says which voice took over',
       JSON.stringify(a.notes));
    ok(a.marks.filter((m) => m.source === 'web').length >= a.marks.length - 2,
       'and all but the first stumble were read by the browser\u2019s own voice (' +
       a.marks.filter((m) => m.source === 'web').length + ' of ' + a.marks.length + ')',
       JSON.stringify(a.marks.map((m) => m.source)));
    ok(a.finished && a.queue === 0 && !a.draining,
       'AND IT STILL READ THE LINE TO THE END: speakDone went up with piper unreachable',
       JSON.stringify({ finished: a.finished, queue: a.queue, draining: a.draining }));
    const aLast = a.marks[a.marks.length - 1] || {};
    ok(!!aLast.end, 'including the last chunk of it', JSON.stringify(aLast));
    /* And the engine goes back where it belongs on the next health poll, so one bad
       minute does not cost the session its local voice. */
    ok(a.down !== '',
       'the page knew the local voice was down and could say so, rather than hiding the ' +
       'fallback inside "engine"', JSON.stringify(a.down));
    ok(await waitFor(page, '__galaxy.voice.down === "" && __galaxy.voice.engine === "piper"',
                     25000),
       'and the next health poll puts the local voice back - a stumble is not a verdict',
       await page.evaluate('__galaxy.voice.down + " / " + __galaxy.voice.engine'));
  } else {
    note('this machine is on the web path, so there is no /say to sabotage - the two ' +
         'failure proofs need the local engine and are skipped rather than faked');
  }

  /* ---- 8. APPEND, NOT SUBSTITUTE, AND THEN A REAL CANCEL ------------------ */
  /* The queue's whole reason for existing: a second line arriving mid-answer waits its
     turn instead of killing the first. Then the one door that may empty it. */
  await page.evaluate('__galaxy.speech.speakLine(' + JSON.stringify(LONG) + ')');
  await sleep(2500);
  const mid = await page.json('({chunks: __galaxy.voice.chunks.length,' +
    ' queue: __galaxy.voice.queue, draining: __galaxy.voice.draining})');
  await page.evaluate('__galaxy.speech.speakLine("And one more thing, sir.")');
  const after = await page.json('({chunks: __galaxy.voice.chunks.length,' +
    ' queue: __galaxy.voice.queue, draining: __galaxy.voice.draining})');
  note('mid-answer: ' + JSON.stringify(mid) + ' then a second line: ' + JSON.stringify(after));
  ok(after.chunks === mid.chunks + 1 && after.draining === true,
     'A SECOND LINE MID-ANSWER IS APPENDED, NOT SUBSTITUTED: ' + mid.chunks +
     ' chunks became ' + after.chunks + ', and the first answer keeps its ending',
     JSON.stringify({ mid, after }));
  await page.evaluate('__galaxy.speech.cancel("the harness, standing in for the stop control")');
  await sleep(600);
  const stopped = await page.json('({queue: __galaxy.voice.queue,' +
    ' draining: __galaxy.voice.draining,' +
    ' lit: document.getElementById("status").className === "speaking"})');
  ok(stopped.queue === 0 && stopped.draining === false,
     'AND CANCEL STILL MEANS CANCEL: the queue is empty and nothing is draining',
     JSON.stringify(stopped));
  await sleep(700);
  ok(!(await page.evaluate('__galaxy.voice.speaking')),
     'with nothing left speaking behind it', JSON.stringify(stopped));

  /* ---- 9. THE PIN IS WIRED, EVEN WHEN IT IS EMPTY ------------------------ */
  ok(typeof health.voice === 'string',
     '/health publishes voice_name from config.json, so a pin can reach the browser at all',
     JSON.stringify(health.voice));
  ok(await page.evaluate('__galaxy.voice.pinned === ' + JSON.stringify(health.voice)),
     'and the page is holding exactly what the server sent (' +
     (health.voice ? JSON.stringify(health.voice) : 'empty - the allowlist decides') + ')');
  const other = names.find((n) => norm(n) !== norm(v.name));
  if (other) {
    const pinnedTo = await page.json('(function(){ __galaxy.voice.pin(' +
      JSON.stringify(other) + '); return {name: __galaxy.voice.name,' +
      ' why: __galaxy.voice.why, pinned: __galaxy.voice.pinned}; })()');
    note('pinned to ' + JSON.stringify(other) + ' -> ' + JSON.stringify(pinnedTo));
    ok(norm(pinnedTo.name) === norm(other) && /config\.json/.test(pinnedTo.why),
       'A PIN OUTRANKS THE ALLOWLIST: asked for ' + JSON.stringify(other) + ' it took it, ' +
       'and said why', JSON.stringify(pinnedTo));
    const back = await page.json('(function(){ __galaxy.voice.pin("");' +
      ' return {name: __galaxy.voice.name, why: __galaxy.voice.why}; })()');
    ok(norm(back.name) === norm(v.name),
       'and removing the pin returns it to the same choice it made at boot (' + back.name +
       ')', JSON.stringify({ boot: v.name, afterUnpin: back.name, why: back.why }));
  } else {
    note('only one voice on this machine, so there is no second name to pin - the pin ' +
         'path is proved by the /health wiring above and nothing more can be asked here');
  }
  ok(v.why.length > 0 && !/^\s*$/.test(v.why),
     'and the reason a voice was chosen is always available to read: "' + v.why + '"');

  page.close();
}

main().then(() => {
  console.log('\n  VERIFY ' + (checks - bad.length) + '/' + checks +
              (bad.length ? ' PASS - ' + bad.length + ' FAILED' : ' PASS') + '\n');
  if (bad.length) bad.forEach((b) => console.log('  failed: ' + b));
  for (const p of procs) { try { process.kill(-p.pid); } catch { try { p.kill(); } catch { } } }
  for (const d of profiles) { try { rmSync(d, { recursive: true, force: true }); } catch { } }
  process.exit(bad.length ? 1 : 0);
}).catch((e) => {
  console.log('\n  BROKE: ' + e.message + '\n');
  for (const p of procs) { try { process.kill(-p.pid); } catch { try { p.kill(); } catch { } } }
  for (const d of profiles) { try { rmSync(d, { recursive: true, force: true }); } catch { } }
  process.exit(1);
});
