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
 *   THE FIFO'S ARITHMETIC, on the string the constitution names: a hundred and twenty
 *     characters, and afterwards queued must equal played, dropped must be zero, and every
 *     chunk must have come off the AudioContext bus - because a page that quietly fell back
 *     to an <audio> tag would satisfy every count here and none of the requirement.
 *   A DECODE FAILURE, INJECTED. /say answers, the bytes arrive, and decodeAudioData is made
 *     to refuse exactly one of them - which is a different failure from a network that will
 *     not answer, and the one PART 2 actually names. Ten milliseconds of silence must take
 *     that chunk's place, the queue must advance through the SAME onended every other chunk
 *     uses, and the tail must still be read. Nor is one stumble a verdict: the local voice
 *     stays, because falling back on a single miss would cost the session its own voice.
 *   PIPER ABSENT. Then every /say is made to fail. The page must NAME its fallback to the
 *     browser's own voices and still read the line to the end.
 *   THE CASTING CONFIG, READ FROM FOUR PLACES. config.json's voice_model, /voices' chosen,
 *     /health.say's model and the telemetry rail's own VOICE cell must be the same voice,
 *     with length_scale 1.05 and noise_scale 0.4 on both server answers. ONE KEY of that
 *     file is read and nothing else about it is ever printed: it holds this machine's
 *     credentials, and the eight-character digest below is how "the casting door moved one
 *     key and nothing else" gets checked without anybody looking at the rest.
 *   THE DUCK. A chime fired while the butler is speaking must sound 80% down and must not
 *     lift the duck on its way out; the speech bus itself stays at full height.
 *   AND THE THREE CANDIDATES, AUDITIONED through the real bus, which is the casting test
 *     the lookbook has to report.
 *   AND THE CANCEL LAW, read out of the page's own source: only the stop control, a new
 *     question, the microphone opening, the reset, a barge-in and a closing word may empty
 *     the queue - six lines, every one of them a person saying stop. An SSE heartbeat, a
 *     panel render, a camera move, a focus tick and a proposal card must not be able to
 *     reach it at all.
 *
 * THE HARNESS WRAPS speakLine(), NOT speechSynthesis. That is the point of the funnel: a
 * proof that reached past it into the engine would be a proof about Chrome rather than
 * about this page's queue. The one place an utterance is inspected is labelled an
 * observer, and it only has anything to look at on the web path.
 *
 * Headed, GPU-backed, and NOT muted: the subject is what comes out of the speakers on the
 * machine in front of you. IT WILL TALK OUT LOUD FOR ABOUT THREE MINUTES. It asks the server
 * for audio and for nothing else - no mail, no diary, no model, and it never WRITES
 * config.json: the casting door is proved by its refusals and by a digest, because a test
 * that rewrote the file holding the employer's keys to see whether it could would be a worse
 * thing than the bug it was looking for.
 *
 * Usage:  python server.py 2> server-trace.log   then   node voice_proof.mjs
 */
import { spawn } from 'node:child_process';
import { mkdtempSync, rmSync, existsSync, readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
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
/* PART 2's own numbers, written here rather than read from the page, so that "the prosody
   is 1.05 and 0.4" is checked against the constitution and not against whatever the code
   currently happens to hold. */
const LENGTH_SCALE = 1.05;
const NOISE_SCALE = 0.4;
const SILENCE_MS = 10;        // what takes a chunk that would not decode
const DUCK = 0.2;             // 80% off the chimes while the butler is speaking
const CONFIG = 'config.json'; // read for ONE key - see readVoiceModel()
const CAST = ['en_US-ryan-high', 'en_GB-alan-medium', 'en_US-joe-medium'];
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

/* THE STRING PART 2 NAMES: a hundred and twenty characters, and the count is asserted below
   rather than trusted here, because a claim about a length nobody measures is decoration.
   One sentence, so the page's own splitter leaves it as ONE chunk - which is the point. The
   many-chunk case is what the long read above is for; this is the arithmetic case, and the
   simplest possible queue is the one where "queued equals played" has nowhere to hide. */
const LINE120 = 'A hundred and twenty characters, read to their final word: the archive is ' +
                'online, the hands are wired, and so am I, sir.';

/* Four sentences for the decode stumble, so that there is a queue either side of the hole.
   Distinct prose from SHORT below: the /say cache is keyed on the text, and a line that has
   already been synthesised comes back in milliseconds - which would make the gap either side
   of the injected failure a measurement of the cache rather than of the queue. */
/* Four sentences, and each one long enough that TWO of them will not fit inside the 180
   character ceiling - so the cut is four chunks and not two. That matters: the decode
   failure below is aimed by call number at the second chunk, and on a two-chunk line the
   second chunk IS the last one, which would leave no tail to prove survived. The length
   of these sentences is load-bearing, and section 6b checks the cut before it reads. */
const STUMBLE = [
  'One. The line before the stumble, and there is nothing at all wrong with this one, ' +
    'so it should be read to its final word in the local voice.',
  'Two. The line whose audio the engine is about to refuse to decode, for the proof, ' +
    'which is a thing that happens on a real machine now and then.',
  'Three. The line straight after the hole, which is the tail of the matter, and the ' +
    'one that used to be lost when a rejected promise went uncaught.',
  'Four. And the last word of all, sir, which is the thing actually being proved here: ' +
    'a queue that cannot drop a chunk, whatever the engine does.',
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

/* ONE KEY, AND A DIGEST OF THE REST.
   config.json holds this machine's credentials - the AWS pair, the mail password, the search
   keys - and the casting protocol is the only thing in this project that writes to it. So
   this reads voice_model, counts the keys, and folds everything ELSE into eight hex
   characters: enough to prove that a write moved one key and left the rest alone, and worth
   nothing whatever to anybody who reads the transcript. voice_engine is left out of the
   digest because the casting door sets it deliberately alongside the model; everything
   outside those two is what "nothing else moved" is about. Nothing is returned from here
   that is not a name, a count or a hash. */
function readVoiceModel() {
  let raw = null;
  try { raw = JSON.parse(readFileSync(CONFIG, 'utf8')); } catch (e) { return null; }
  if (!raw || typeof raw !== 'object') return null;
  const keys = Object.keys(raw).sort();
  const rest = {};
  keys.forEach((k) => { if (k !== 'voice_model' && k !== 'voice_engine') rest[k] = raw[k]; });
  return {
    model: String(raw.voice_model || ''), engine: String(raw.voice_engine || ''),
    keys: keys.length,
    digest: createHash('sha256').update(JSON.stringify(rest)).digest('hex').slice(0, 8),
  };
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
   poll and everything else go straight through.

   THE DECODE SWITCH. A different failure entirely, and the one PART 2 names: /say answers,
   the bytes arrive, and the AudioContext will not make a buffer of them. Breaking the
   network cannot produce it. It is patched onto BaseAudioContext.prototype because the
   page's context is a closure variable and this is the only door in - and it fails ONE call,
   by number, putting the real method back in the same tick, so everything after the stumble
   is the real engine rather than a crippled one. */
const INSTRUMENTS = `(function(){
  if (window.__vp) return 'already';
  window.__vp = { lines: [], given: [], samples: [], done: [], gapBad: 0, litAtEnd: null,
                  t0: 0, timer: null, failMark: '', failAll: false, sayCalls: 0,
                  sayFailed: 0, watchOrgan: false,
                  decodeCalls: 0, decodeAt: 0, decodeFiredAt: 0 };
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
  var proto = (window.BaseAudioContext || window.AudioContext).prototype;
  var realDecode = proto.decodeAudioData;
  proto.decodeAudioData = function () {
    window.__vp.decodeCalls++;
    if (window.__vp.decodeAt && window.__vp.decodeCalls === window.__vp.decodeAt) {
      window.__vp.decodeFiredAt = window.__vp.decodeCalls;
      window.__vp.decodeAt = 0;                 // one stumble, and then the engine back
      return Promise.reject(new Error('forced decode failure, for the proof'));
    }
    return realDecode.apply(this, arguments);
  };
  addEventListener('speakDone', function (e) { window.__vp.done.push(e.detail); });
  return 'wrapped';
})()`;

/* One read, start to finish, watched from inside the page the whole way. Returns
   everything Node needs to do its own arithmetic afterwards. */
async function readOut(page, text, timeout, opts = {}) {
  await page.evaluate(`(function(){
    window.__vp.lines = []; window.__vp.given = []; window.__vp.samples = [];
    window.__vp.done = []; window.__vp.gapBad = 0; window.__vp.litAtEnd = null;
    window.__vp.t0 = Date.now();
    window.__vp.watchOrgan = ${opts.watchOrgan ? 'true' : 'false'};
    /* THE COUNTERS AS THEY STAND, so that every number this run is judged on is a
       DIFFERENCE. speakFifo counts for the life of the tab, and a harness that read the
       totals would be reporting on every line spoken since boot - the greeting included. */
    window.__vp.fifo0 = __galaxy.voice.fifo;
    window.__vp.tone0 = __galaxy.audio.played.length;
    /* WHERE THE LOG STOOD, so that the notes this read produced can be told from the notes
       every read before it left in the same cumulative list - and so that a read emptied by
       one of the four licensed cancels says which one instead of failing ten checks about a
       queue that was doing exactly what it was told. */
    window.__vp.notes0 = __galaxy.voice.notes.length;
    /* A CHIME, FIRED INTO THE MIDDLE OF A SENTENCE, from inside the page and on a timer -
       because the thing being measured is what the bus does in the 150ms after a chime is
       asked for, and a round trip over a WebSocket is longer than the ramp it is trying to
       catch. Scheduled here rather than driven from Node for that reason alone. */
    window.__vp.chime = null;
    if (${Number(opts.chimeAt) || 0}) setTimeout(function () {
      var a = __galaxy.audio;
      var before = { gain: a.gain, ducked: a.ducked, count: a.played.length };
      var rang = a.play('wake');
      setTimeout(function () {
        var b = __galaxy.audio;
        window.__vp.chime = { before: before, rang: rang, gain: b.gain, ducked: b.ducked,
          count: b.played.length, bus: b.speechBus, trouble: b.trouble,
          draining: __galaxy.voice.draining,
          kinds: b.played.map(function (p) { return p && p.kind ? p.kind : p; }).slice(-3) };
      }, 150);
    }, ${Number(opts.chimeAt) || 0});
    /* Sampled from INSIDE the page every 120ms, so the continuity of the voice is not
       measured through a WebSocket. A sample where the indicator has gone dark with the
       queue still working is exactly the defect this whole arrangement exists to end. */
    window.__vp.timer = setInterval(function () {
      var v = __galaxy.voice;
      var c = v.chunks;
      var last = c.length ? c[c.length - 1] : null;
      var done = !!(last && last.end > 0) && v.queue === 0 && !v.draining;
      var lit = document.getElementById('status').className === 'speaking';
      var a = __galaxy.audio;
      /* The organ rail costs five getComputedStyle calls a sample, so it is read only for
         the one read that is about the organ. Over a ninety-second answer at 120ms it would
         be four thousand style resolutions bought for nothing. */
      var mic = window.__vp.watchOrgan ? (__galaxy.organs.state.mic || {}) : null;
      window.__vp.samples.push({ at: Date.now(), lit: lit, draining: v.draining,
        queue: v.queue, now: v.now, engine: v.engine, ka: v.keepAlive, done: done,
        built: a.built, ducked: a.ducked, gain: a.gain, bus: a.speechBus, down: v.down,
        st: a.state,
        micOrgan: mic ? mic.organ : '', micTone: mic ? mic.tone : '',
        micBeat: mic ? !!mic.beating : null, micLine: mic ? mic.line : '' });
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
    given: window.__vp.given, notes: __galaxy.voice.notes, notes0: window.__vp.notes0,
    engine: __galaxy.voice.engine, engineWhy: __galaxy.voice.engineWhy,
    down: __galaxy.voice.down,
    queue: __galaxy.voice.queue, draining: __galaxy.voice.draining,
    pageGap: __galaxy.voice.gapMax, stalls: __galaxy.voice.stalls,
    lit: document.getElementById('status').className === 'speaking',
    sayCalls: window.__vp.sayCalls, sayFailed: window.__vp.sayFailed,
    fifo0: window.__vp.fifo0, fifo: __galaxy.voice.fifo,
    doneLast: __galaxy.voice.doneLast, silenceMs: __galaxy.voice.SILENCE_MS,
    decodeFiredAt: window.__vp.decodeFiredAt, chime: window.__vp.chime,
    audio: {built: __galaxy.audio.built, gain: __galaxy.audio.gain,
            ducked: __galaxy.audio.ducked, duckTo: __galaxy.audio.duckTo,
            ceiling: __galaxy.audio.CEILING, duck: __galaxy.audio.DUCK,
            bus: __galaxy.audio.speechBus, played: __galaxy.audio.played} })`);
  /* What this read said for itself, and whether anything emptied the queue under it. */
  out.notesNew = (out.notes || []).slice(out.notes0 || 0);
  out.emptied = out.notesNew.filter((n) => /queue emptied by/.test(n));
  /* The deltas, done once and here, because every claim below is about THIS read. */
  out.spent = {};
  Object.keys(out.fifo || {}).forEach((k) => {
    if (typeof out.fifo[k] === 'number') out.spent[k] = out.fifo[k] - (out.fifo0[k] || 0);
  });
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
  /* SIX, raised from four when the Open Ear arrived, and the law did not change: every one
     of these is still a PERSON saying stop. A barge-in is him talking over the answer, which
     is the plainest "stop" there is; a closing word is him saying the conversation is over,
     and a goodbye queued behind four more sentences would not be one. What is still refused
     is everything that is not a person: a heartbeat, a render, a camera move, a focus tick,
     a proposal card. */
  ok(callers.length === 6,
     'exactly six lines in the page may empty the queue', JSON.stringify(callers));
  ok(/new question/.test(callers.join('|')) && /stop control/.test(callers.join('|')) &&
     /reset/.test(callers.join('|')) && /microphone/.test(callers.join('|')) &&
     /barge-in/.test(callers.join('|')) && /closing word/.test(callers.join('|')),
     'and they are the ones the law permits: a new question, the stop control, the reset ' +
     'button, the microphone opening, a barge-in and a closing word - every one of them a ' +
     'person saying so', JSON.stringify(callers));
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

  /* ---- 2b. THE CASTING CONFIG, READ FROM FOUR PLACES ---------------------- */
  /* PART 2 gives the casting protocol one lasting effect: "the choice writes config.json ->
     voice_model". Four things then have to be the same voice - the file, the /voices answer
     the panel paints from, the /say engine's own state, and the VOICE cell on the telemetry
     rail - and if any two of them disagree the deck is showing a voice that is not the one
     speaking. That is the whole check, and it is done by AGREEMENT rather than by asking any
     one of them whether it is right.

     THE FILE IS READ FOR ONE KEY. See readVoiceModel(). */
  const voices = await (await fetch(GALAXY + '/voices')).json();
  const disk = readVoiceModel();
  note('/voices: ' + JSON.stringify({ engine: voices.engine, piper: voices.piper,
    chosen: voices.chosen, fallback: voices.fallback,
    candidates: (voices.candidates || []).map((c) => c.model + (c.ready ? '' : ' (not ready)')) }));
  ok(!!disk, CONFIG + ' is on disk and is a JSON object - the casting decision has ' +
     'somewhere to live', String(disk));
  if (disk) {
    note('config.json: voice_model ' + JSON.stringify(disk.model) + ' · voice_engine ' +
         JSON.stringify(disk.engine) + ' · ' + disk.keys + ' keys · digest of the rest ' +
         disk.digest + ' (one key read; nothing else about that file is printed here)');
  }
  ok((voices.candidates || []).map((c) => c.model).join('|') === CAST.join('|'),
     'THE THREE CANDIDATES ARE THE THREE THE CONSTITUTION NAMES, in its order: ' +
     CAST.join(', '), JSON.stringify((voices.candidates || []).map((c) => c.model)));
  ok(collapse(voices.line || '') === 'The archive is online, and the hands are wired, sir.',
     'and they are all cast for the same line, word for word as it was written',
     JSON.stringify(voices.line));

  if (voices.piper) {
    ok(disk && disk.model === voices.chosen,
       'THE FILE AND THE SERVER NAME THE SAME VOICE: config.json’s voice_model is ' +
       JSON.stringify(voices.chosen) + ', which is what /voices reports as chosen',
       JSON.stringify({ disk: disk && disk.model, chosen: voices.chosen }));
    ok(health.say && health.say.model === voices.chosen,
       'and it is the voice /say is actually loaded with, rather than one it was asked for',
       JSON.stringify({ say: health.say && health.say.model, chosen: voices.chosen }));
    ok((voices.candidates || []).filter((c) => c.chosen).length === 1 &&
       (voices.candidates || []).find((c) => c.chosen).model === voices.chosen,
       'exactly one of the three is marked as the incumbent, and it is that one',
       JSON.stringify((voices.candidates || []).map((c) => [c.model, !!c.chosen])));
    /* THE RAIL. The fourth reading, and the only one the employer can see. */
    await waitFor(page, '__galaxy.rail.cells.voice.text.indexOf("\\u2026") < 0', 12000);
    const cells = await page.json('__galaxy.rail.cells');
    const shortName = String(voices.chosen).replace(/^[a-z]{2}_[A-Z]{2}-/, '');
    note('rail VOICE cell: ' + JSON.stringify(cells.voice));
    ok(cells.voice.text === 'piper · ' + shortName,
       'AND THE TELEMETRY RAIL SAYS SO OUT LOUD: [ VOICE: piper · ' + shortName +
       ' ] - the fourth reading, and the one the employer can actually see',
       JSON.stringify({ cell: cells.voice.text, wanted: 'piper · ' + shortName }));
    ok(cells.voice.tone === 'local',
       'in gold, because a voice synthesised from a file on this disk is local material',
       JSON.stringify(cells.voice));
  } else {
    /* PART 4's refusal: piper absent. The file may still name a voice; what matters is
       that the server says so plainly and the panel does not pretend. */
    note('piper is not installed on this machine - checking the refusal instead: ' +
         JSON.stringify(voices.fallback));
    ok(typeof voices.fallback === 'string' && voices.fallback.length > 0,
       'PIPER ABSENT IS SAID, NOT HIDDEN: /voices carries the reason the casting panel ' +
       'will print', JSON.stringify(voices.fallback));
  }

  /* THE PROSODY, from both answers. 1.05 and 0.4 are PART 2's numbers and they are the
     difference between a butler and a newsreader. */
  ok(Math.abs(Number(voices.lengthScale) - LENGTH_SCALE) < 1e-9 &&
     Math.abs(Number(voices.noiseScale) - NOISE_SCALE) < 1e-9,
     'THE PROSODY IS THE CONSTITUTION’S: length_scale ' + LENGTH_SCALE +
     ', noise_scale ' + NOISE_SCALE + ' - never rushed',
     JSON.stringify({ lengthScale: voices.lengthScale, noiseScale: voices.noiseScale }));
  ok(health.say && Math.abs(Number(health.say.lengthScale) - LENGTH_SCALE) < 1e-9 &&
     Math.abs(Number(health.say.noiseScale) - NOISE_SCALE) < 1e-9,
     'and /health.say agrees, so the two answers the deck reads cannot drift apart',
     JSON.stringify(health.say));

  /* THE DOOR THAT WRITES THE FILE, PROVED BY ITS REFUSAL. This harness will not write
     config.json - see the header - so what is checked is that the door cannot be talked
     into it: a voice that is not one of the three is refused before a byte moves, and the
     digest of everything else in that file is the same afterwards as it was before. */
  const bogus = 'en_US-nobody-medium';
  const refused = await (await fetch(GALAXY + '/voice', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ model: bogus }),
  })).json();
  const untouched = readVoiceModel();
  note('POST /voice ' + JSON.stringify(bogus) + ' -> ' + JSON.stringify(refused.error));
  ok(refused.ok === false && /not one of the three/.test(String(refused.error)),
     'A VOICE THAT WAS NEVER CAST IS REFUSED, and the refusal says why rather than ' +
     'answering 500', JSON.stringify(refused.error));
  ok(untouched && disk && untouched.digest === disk.digest &&
     untouched.model === disk.model && untouched.keys === disk.keys,
     'AND THE FILE WAS NOT TOUCHED: same voice_model, same ' + (disk ? disk.keys : '?') +
     ' keys, same digest of everything else (' + (untouched ? untouched.digest : '?') +
     ') - which is how a file holding credentials gets checked without being read',
     JSON.stringify({ before: disk && disk.digest,
                      after: untouched && untouched.digest }));

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
  /* THE POINT IS CHOSEN BY THE PAGE, not by this file. A fixed 600,400 is a guess about a
     viewport, and on a machine whose display scaling makes the window smaller than the
     flag asked for it can land on the ASK BAR - where the ear button lives, and where a
     click opens the microphone, which by the cancel law empties the queue. That run does
     not fail: it passes 99 checks and quietly proves nothing, because every read after it
     was cancelled by a microphone the harness opened itself. So the spot is asked for in
     CSS pixels, from the middle of the upper canvas, and what it would hit is checked
     before anything is dispatched at it. */
  const spot = await page.json('(function(){' +
    'var pick=function(f){var x=Math.round(innerWidth*0.5), y=Math.round(innerHeight*f);' +
    ' var e=document.elementFromPoint(x,y);' +
    ' return {x:x, y:y, hit: e ? (e.id || e.tagName.toLowerCase()) : null,' +
    '  bad: !!(e && e.closest && (e.closest("#bar") || e.closest("#cmd") ||' +
    '          e.closest("#toprail") || e.closest("button")))};};' +
    'var s=pick(0.3); if(s.bad) s=pick(0.2); if(s.bad) s=pick(0.12);' +
    's.view=[innerWidth,innerHeight]; return s;})()');
  note('the unlocking click: ' + spot.view.join('x') + ' viewport, at ' + spot.x + ',' +
       spot.y + ' - which is over ' + JSON.stringify(spot.hit));
  ok(spot.bad === false,
     'there is empty canvas to click: the gesture lands on ' + JSON.stringify(spot.hit) +
     ' and not on a control - an unlocking click that pressed the ear button would open ' +
     'the microphone, and the microphone empties the queue',
     JSON.stringify(spot));
  await realClick(page, spot.x, spot.y);
  ok(await waitFor(page, '__galaxy.speech.unlocked === true', 8000),
     'one real click unlocks the audio, as the autoplay policy requires');
  ok(await page.evaluate('__galaxy.audio.state') === 'running',
     'and the AudioContext it built in that gesture is RUNNING, not born suspended - a ' +
     'suspended context has a frozen clock, and every ramp booked against it (the duck ' +
     'among them) waits for a resume that may never come',
     await page.evaluate('__galaxy.audio.state + " / built " + __galaxy.audio.built'));
  ok(await page.evaluate('__galaxy.speech.muted === false'),
     'and this run is NOT muted - what follows is a measurement of the speakers');
  /* WAITED FOR, NOT SLEPT THROUGH. This was `sleep(1500)` with a comment saying "let the
     boot greeting finish speaking", and 1500 is a guess about how long a local voice takes
     to read one sentence on a machine nobody has measured. When piper is busy the greeting
     is still in the queue when the line below empties it - and a cancel that discards an
     unplayed chunk breaks `queued === played` FOR THE WHOLE SESSION, because the fifo's
     cumulative counters have no notion of a chunk that was thrown away on purpose. So the
     harness was manufacturing the one defect the section below exists to detect, on exactly
     the runs where the machine was slow enough to matter.
     The cancel stays, because a greeting that genuinely never finishes must not be allowed
     to bleed into the measurement - but by the time it runs the queue is dry and it has
     nothing to discard, which is why it no longer even writes a note. */
  const greeted = await waitFor(page,
    '__galaxy.voice.draining === false && __galaxy.voice.queue === 0', 30000);
  ok(greeted, 'the boot greeting was read to its end before anything was measured - waited ' +
     'for, because a cancel that discarded a chunk of it would put the session’s ' +
     'queued/played arithmetic permanently out by one',
     await page.evaluate('JSON.stringify(__galaxy.voice.fifo)'));
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

  /* FIRST, THAT NOBODY EMPTIED IT. The four licensed cancels are the four licensed cancels
     during a harness run as much as during a conversation, and a read that one of them
     ended is not a queue that dropped anything - it is a queue that obeyed. Named here so
     the ten checks below are read as consequences rather than as findings. */
  ok(r.emptied.length === 0,
     'NOTHING EMPTIED THE QUEUE UNDER THIS READ: no cancel, licensed or otherwise, ' +
     'happened while the answer was being spoken',
     'the queue was emptied mid-read: ' + JSON.stringify(r.emptied));
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

  /* ---- 5b. A HUNDRED AND TWENTY CHARACTERS, AND THE FIFO'S ARITHMETIC ----- */
  /* PART 2 asks for one specific thing to be countable: "an explicit queue that cannot drop
     a chunk", checked on "a 120-char string with zero drops". The long read above is the
     ARTISTIC case - ninety seconds, a dozen chunks, does it sag. This is the ACCOUNTING case,
     and it is deliberately the simplest queue there is, because a single chunk gives the
     numbers nowhere to hide: one queued, one played, none silent, none dropped.

     Every number is a DIFFERENCE against the counters as they stood before this line - see
     readOut - because speakFifo counts for the life of the tab and the greeting is in there.

     AND WHILE IT IS SPEAKING, two more things are watched that have no other moment: the
     chimes duck under it, and the mic organ on the rail reports SPEAKING. Both are only true
     for the nine seconds this takes, so they are sampled here rather than asserted after. */
  ok(LINE120.length === 120,
     'the line is a hundred and twenty characters, counted rather than assumed (' +
     LINE120.length + ')', JSON.stringify(LINE120.length));
  const cut120 = await page.json('__galaxy.voice.split(' + JSON.stringify(LINE120) + ')');
  note('reading the 120-character line, cut into ' + cut120.length + ' chunk(s), with a ' +
       'chime fired into the middle of it…');
  const q = await readOut(page, LINE120, SHORT_TIMEOUT_MS, { watchOrgan: true, chimeAt: 2500 });
  note('fifo for this read: ' + JSON.stringify(q.spent) + ' · bus ' + q.fifo.bus +
       ' · context ' + JSON.stringify(q.fifo.ctx) + ' @' + q.fifo.rate + 'Hz');
  note('doneLast: ' + JSON.stringify({ chunks: q.doneLast.chunks, spoken: q.doneLast.spoken,
    skipped: q.doneLast.skipped, silent: q.doneLast.silent, dropped: q.doneLast.dropped,
    queued: q.doneLast.queued, played: q.doneLast.played, stalls: q.doneLast.stalls,
    gapMax: q.doneLast.gapMax, engine: q.doneLast.engine }));
  ok(q.emptied.length === 0,
     'nothing emptied the queue under this line either, so the arithmetic below is about ' +
     'a read that was left alone', JSON.stringify(q.emptied));
  if (q.notes.length) q.notes.forEach((n) => console.log('         ' + n));

  ok(q.finished && q.doneLast.dropped === 0,
     'THE FIFO FINISHED THE 120-CHARACTER LINE WITH ZERO DROPS: every chunk that was ' +
     'queued reached an end, which is the one number this queue lives or dies by',
     JSON.stringify({ finished: q.finished, dropped: q.doneLast.dropped }));
  ok(q.spent.queued === cut120.length && q.spent.played === q.spent.queued,
     'QUEUED EQUALS PLAYED: ' + q.spent.queued + ' in, ' + q.spent.played + ' out, counted ' +
     'as a difference against where the counters stood before this line',
     JSON.stringify({ spent: q.spent, before: q.fifo0, after: q.fifo }));
  ok(q.doneLast.queued === q.doneLast.played,
     'and it is true of the whole session as well as of this line (' + q.doneLast.queued +
     ' queued, ' + q.doneLast.played + ' played since this tab opened)',
     JSON.stringify({ queued: q.doneLast.queued, played: q.doneLast.played }));
  ok(q.spent.silent === 0 && q.spent.decodeFails === 0 && q.spent.fetchFails === 0 &&
     q.spent.startFails === 0,
     'AND NOTHING STOOD IN FOR ANYTHING: no silence, no decode failure, no fetch failure ' +
     'and no refusal to start - the placeholder path is for the next section, not for a ' +
     'line that worked', JSON.stringify(q.spent));
  ok(collapse(q.doneLast.text) === collapse(LINE120),
     'the text that came back out of the queue is the text that went in, word for word',
     JSON.stringify({ in: LINE120.length, out: collapse(q.doneLast.text).length }));
  if (q.engine === 'piper') {
    ok(q.fifo.bus === true && q.fifo.ctx === 'running' && q.spent.decoded === cut120.length,
       'AND IT CAME OFF THE AUDIOCONTEXT BUS, decoded here: a page that had quietly fallen ' +
       'back to an <audio> tag would satisfy every count above and none of the requirement',
       JSON.stringify({ bus: q.fifo.bus, ctx: q.fifo.ctx, decoded: q.spent.decoded }));
    ok(q.marks.every((m) => m.source === 'piper' && m.secs > 0),
       'every chunk of it was real audio with a real duration, not an instant no-op',
       JSON.stringify(q.marks.map((m) => [m.source, m.secs])));
  }
  /* AND IT TOOK AS LONG AS SPEECH TAKES. The whole failure this file exists for looks like
     success in the counters: a queue that advances instantly has played everything it was
     given. So the wall clock is a check, against the page's own estimate for the line. */
  const est = await page.evaluate('__galaxy.voice.estimate(' + JSON.stringify(LINE120) + ')');
  ok(q.wall > est * 0.5,
     'and it really was SPOKEN: ' + (q.wall / 1000).toFixed(1) + 's of audio against the ' +
     'page’s own estimate of ' + (est / 1000).toFixed(1) + 's - a queue that advanced ' +
     'instantly would have "played" everything in milliseconds',
     JSON.stringify({ wall: q.wall, estimate: est }));

  /* THE DUCK, sampled through the whole line. */
  const live = q.samples.filter((s) => s.draining && s.built);
  const unducked = live.filter((s) => s.ducked !== true);
  const loud = live.filter((s) => s.gain !== null && s.gain > q.audio.duckTo + 0.0005);
  note('the duck: ' + live.length + ' samples while speaking · ' + unducked.length +
       ' with the duck off · ceiling ' + q.audio.ceiling + ' · ducked to ' + q.audio.duckTo +
       ' · at the end ' + q.audio.gain + ' (ducked ' + q.audio.ducked + ') · context ' +
       JSON.stringify([...new Set(live.map((s) => s.st))]));
  /* THE CLOCK THE DUCK IS BOOKED AGAINST. Every ramp in the tone engine is scheduled on
     actx.currentTime, and a suspended context's currentTime does not move - so a run that
     measured a duck through a suspended context would be measuring a frozen number and
     calling it a gain. Named separately from the duck itself for that reason. */
  ok(live.every((s) => s.st === 'running'),
     'the AudioContext was running for every sample of it, so the gains below are a ' +
     'measurement and not a stopped clock',
     JSON.stringify([...new Set(live.map((s) => s.st))]));
  ok(live.length > 5, 'the bus was watched for the length of the line (' + live.length +
     ' samples)', JSON.stringify(q.samples.length));
  ok(Math.abs(q.audio.duckTo - q.audio.ceiling * DUCK) < 1e-9 && q.audio.duck === DUCK,
     'THE DUCK IS 80%: the chime bus drops to ' + q.audio.duckTo + ' from a ceiling of ' +
     q.audio.ceiling + ', which is the ' + DUCK + ' the constitution asked for',
     JSON.stringify(q.audio));
  ok(unducked.length === 0 && loud.length <= 1,
     'AND IT WAS DOWN FOR THE WHOLE SENTENCE: not one sample caught the chimes at full ' +
     'height while the butler was speaking',
     JSON.stringify({ unducked: unducked.length, loud: loud.length,
                      worst: loud.slice(0, 2) }));
  /* AND IT LIFTS - asked the only way the audio thread will answer it honestly.
     Read after a pause first, and the pause is the point: the duck is a RAMP and not a
     step (TONE_DUCK_MS, 90ms, either way, because a gain that jumps is a click), so the
     gain sampled in the same millisecond the queue emptied is still at the bottom of a
     ramp that has only just been scheduled. 400ms is four ramps.

     WHY THAT RESTING READ IS NOTED AND NOT ASSERTED, and this cost a whole afternoon.
     `AudioParam.value` is not the timeline - it is the value the audio thread last
     COMPUTED for that param, and Chrome stops computing for a node it has disabled.
     A GainNode whose inputs all disconnect gets disabled (the mid-sentence wake chime
     above connects an envelope into the bus and drops it again at its own onended), and
     from that moment the param's `.value` is frozen wherever it stood - 0.03 here, since
     the chime died while the butler was still talking. The 90ms lift ramp is on the
     timeline and perfectly correct; nothing is evaluating it because nothing is playing.
     Reading that frozen number and calling the duck broken is measuring the observer.

     So the lift is measured the way an ear would meet it: fire a real chime, which
     reconnects an input and re-enables the bus, and watch the gain WHILE that chime is
     going through it. That is the actual claim - the next chime after the butler stops
     sounds at full height - and it is a measurement of the bus under load rather than of
     a parameter nobody is reading. Assert `ducked` too, so the page's intention and the
     node's behaviour still have to agree. */
  await sleep(400);
  const rested = await page.json('({gain: __galaxy.audio.gain, ducked: __galaxy.audio.ducked,' +
                                 ' ceiling: __galaxy.audio.CEILING, ms: __galaxy.audio.DUCK_MS})');
  note('and 400ms after the queue ran dry: ducked ' + rested.ducked + ', gain reads ' +
       rested.gain + ' - the ramp back up is ' + rested.ms + 'ms, either way (a bus with ' +
       'nothing playing through it is a bus Chrome has stopped evaluating, so that number ' +
       'is the last one it computed, not the timeline)');
  /* page.json() stringifies the expression, and a Promise stringifies to {} - so this one
     does its own awaiting and hands back the JSON. */
  const lift = JSON.parse(await page.evaluate(`(function(){
    var a = __galaxy.audio;
    var before = {gain: a.gain, ducked: a.ducked};
    var rang = a.play('yes');
    var t0 = performance.now(), samples = [];
    return new Promise(function(res){
      var iv = setInterval(function(){
        samples.push([Math.round(performance.now() - t0), __galaxy.audio.gain]);
        if (performance.now() - t0 > 180) {
          clearInterval(iv);
          res(JSON.stringify({before: before, rang: rang, samples: samples,
               ducked: __galaxy.audio.ducked, gain: __galaxy.audio.gain,
               ceiling: __galaxy.audio.CEILING}));
        }
      }, 20);
    });
  })()`));
  const liftMax = Math.max(...lift.samples.map((s) => s[1] || 0));
  note('so a chime was fired into the silence: ' + lift.samples.length + ' samples across ' +
       'its ' + lift.samples[lift.samples.length - 1][0] + 'ms, the bus rising to ' + liftMax +
       ' of ' + lift.ceiling + ' - ' + JSON.stringify(lift.samples.slice(0, 4)));
  ok(lift.rang === true && lift.ducked === false &&
     Math.abs(liftMax - lift.ceiling) < 0.0005,
     'AND THE CHIMES STAND BACK UP WHEN THE QUEUE RUNS DRY: the first chime after the last ' +
     'word plays at ' + liftMax + ' of ' + lift.ceiling + ', measured off the bus while it ' +
     'was carrying it - a duck that never lifted would be a mute with extra steps',
     JSON.stringify({ atEnd: { ducked: q.audio.ducked, gain: q.audio.gain }, rested,
                      lift: { rang: lift.rang, ducked: lift.ducked, max: liftMax,
                              samples: lift.samples } }));
  ok(live.every((s) => s.bus === 1),
     'while the SPEECH bus stayed at full height throughout: the butler is not what gets ' +
     'quieter', JSON.stringify([...new Set(live.map((s) => s.bus))]));

  /* THE CHIME THAT WAS FIRED INTO THE MIDDLE OF IT. */
  note('the chime, mid-sentence: ' + JSON.stringify(q.chime));
  ok(!!q.chime && q.chime.draining === true,
     'the chime was fired while a sentence was actually in flight, which is the only ' +
     'moment this claim exists in', JSON.stringify(q.chime));
  if (q.chime) {
    ok(q.chime.rang === true && q.chime.count === q.chime.before.count + 1,
       'A CHIME STILL SOUNDS UNDER A SENTENCE: it was scheduled and recorded (' +
       JSON.stringify(q.chime.kinds) + ') rather than dropped - the rule is that it does ' +
       'not talk OVER the butler, not that it is cancelled',
       JSON.stringify(q.chime));
    ok(q.chime.ducked === true && q.chime.gain <= q.audio.duckTo + 0.0005,
       'AND IT SOUNDED 80% DOWN: 150ms after it was asked for, the bus it plays through is ' +
       'still at ' + q.chime.gain + ' rather than ' + q.audio.ceiling + ' - a chime cannot ' +
       'lift its own duck on the way out', JSON.stringify(q.chime));
  }

  /* THE MIC ORGAN, WHICH IS THE ONE ORGAN THAT REPORTS SPEECH. PART 1 gives the rail four
     live states and "speaking" is the only one a voice harness can prove. */
  const micLive = live.filter((s) => s.micOrgan === 'live');
  const micSpeaking = live.filter((s) => s.micTone === 'speaking');
  note('the mic organ while he spoke: ' + micLive.length + ' of ' + live.length +
       ' samples live · ' + micSpeaking.length + ' toned "speaking" · beating on ' +
       live.filter((s) => s.micBeat).length + ' · line ' +
       JSON.stringify((live[Math.floor(live.length / 2)] || {}).micLine));
  ok(micLive.length === live.length && micSpeaking.length === live.length,
     'THE MIC ORGAN READS LIVE AND TONED "SPEAKING" FOR THE WHOLE SENTENCE - the organ rail ' +
     'is telling the truth about the one organ that is running',
     JSON.stringify({ live: micLive.length, speaking: micSpeaking.length,
                      samples: live.length,
                      seen: [...new Set(live.map((s) => s.micOrgan + '/' + s.micTone))] }));
  ok(live.every((s) => s.micBeat === true),
     'and its dot is BEATING, which is the pulse PART 1 spends only on an organ that is ' +
     'actually doing something', JSON.stringify([...new Set(live.map((s) => s.micBeat))]));
  ok(/SPEAKING · the ear is held while the butler talks/
       .test((live[Math.floor(live.length / 2)] || {}).micLine || ''),
     'with the tooltip state line to match, in words: "' +
     ((live[Math.floor(live.length / 2)] || {}).micLine || '') + '"');
  const micAfter = await page.json('__galaxy.organs.state.mic');
  ok(micAfter.organ === 'off' && micAfter.beating === false,
     'AND IT STOPS: the dot is still and the organ is off the moment he has finished, ' +
     'rather than pulsing at an empty queue', JSON.stringify(micAfter));

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
    /* The wording is the page's own: "chunk N had no audio (why); 10ms of silence in its
       place, the queue goes on". Matched on the shape that carries the chunk NUMBER,
       because a log line that says something went wrong without saying which chunk is a
       line you cannot act on. */
    ok(f.notes.some((n) => /chunk \d+ had no audio/.test(n)),
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

    /* ---- 6b. A DECODE FAILURE, AND THE TEN MILLISECONDS -------------------- */
    /* PART 2, in its own words: "a decode failure plays a 10 ms silent buffer and advances.
       The tail never dies." That is NOT the failure above. Above, /say never answered; here
       it answers, the bytes arrive, and the AudioContext refuses to make a buffer of them -
       which is the case where a queue built on "await the audio, then play it" stops dead
       with a rejected promise nobody catches and the rest of the answer is simply never
       read. So exactly one decode is made to fail, by number, and what has to happen is
       arithmetic: one more silence, one more decode failure, no drops, and a tail. */
    /* THE CUT FIRST, because the aim below depends on it. One decode call per chunk and a
       one-ahead buffer put call+2 on the SECOND chunk, so the line has to cut into at
       least three for there to be a tail behind the hole at all. Asserted rather than
       assumed: a shortened STUMBLE would otherwise quietly turn the next four checks into
       a proof about nothing. */
    const sCut = await page.json('__galaxy.voice.split(' + JSON.stringify(STUMBLE) + ')');
    ok(sCut.length >= 3,
       'the four lines cut into ' + sCut.length + ' chunks, so there is a tail behind the ' +
       'hole this section is about to make',
       JSON.stringify(sCut.map((c) => c.length)));
    const armed = await page.evaluate(
      'window.__vp.decodeAt = window.__vp.decodeCalls + 2; window.__vp.decodeAt');
    note('one decodeAudioData call (#' + armed + ') will refuse; reading ' + STUMBLE.length +
         ' characters in ' + sCut.length + ' chunks…');
    const d = await readOut(page, STUMBLE, SHORT_TIMEOUT_MS);
    const silent = d.marks.filter((m) => m.silent);
    const silentAt = d.marks.findIndex((m) => m.silent);
    const afterHole = silentAt >= 0 ? d.marks.slice(silentAt + 1) : [];
    note('with one decode refused: ' + JSON.stringify(d.spent) + ' · silence at chunk ' +
         silentAt + ' of ' + d.marks.length + ' · ' + afterHole.length + ' chunks after it');
    if (d.notes.length) d.notes.forEach((n) => console.log('         ' + n));

    ok(d.decodeFiredAt === armed && d.spent.decodeFails === 1,
       'THE INJECTION LANDED WHERE IT WAS AIMED: decode call #' + d.decodeFiredAt +
       ' refused, and the page counted exactly one decode failure',
       JSON.stringify({ armed, fired: d.decodeFiredAt, spent: d.spent }));
    ok(d.spent.fetchFails === 0,
       'and it was counted as a DECODE failure and not as a network one - the bytes did ' +
       'arrive, which is the whole difference between this section and the last',
       JSON.stringify(d.spent));
    ok(silent.length === 1 && d.spent.silent === 1 && d.silenceMs === SILENCE_MS,
       'TEN MILLISECONDS OF SILENCE TOOK ITS PLACE: exactly one chunk was played as the ' +
       'placeholder, and the placeholder is ' + d.silenceMs + 'ms long',
       JSON.stringify({ silent: silent.length, counted: d.spent.silent, ms: d.silenceMs }));
    ok(silent.length === 1 && silent[0].source === 'silence' &&
       Math.abs(silent[0].secs - SILENCE_MS / 1000) < 0.002,
       'and it really was ten milliseconds of audio - ' + (silent[0] || {}).secs + 's, ' +
       'measured off the buffer that was played rather than off the constant beside it',
       JSON.stringify(silent));
    ok(silent.length === 1 && silent[0].end > 0,
       'AND IT ADVANCED THROUGH THE SAME DOOR AS EVERY OTHER CHUNK: the placeholder’s ' +
       'onended fired, so nothing special had to be remembered about the failed chunk',
       JSON.stringify(silent));
    /* Both halves on the SAME line, and the decode half is what distinguishes it from the
       note section 6 left in this same cumulative log a moment ago. */
    ok(d.notes.some((n) => /chunk \d+ had no audio/.test(n) && /would not decode/.test(n) &&
                           new RegExp(SILENCE_MS + 'ms of silence in its place').test(n)),
       'and it said so in words, naming the chunk, the refusal to decode and the ten ' +
       'milliseconds', JSON.stringify(d.notes));
    ok(d.finished && d.doneLast.dropped === 0 && d.spent.queued === d.spent.played,
       'ZERO DROPS THROUGH A DECODE FAILURE: ' + d.spent.queued + ' queued, ' +
       d.spent.played + ' played, ' + d.doneLast.dropped + ' dropped - the queue cannot ' +
       'lose a chunk even when the audio engine refuses one',
       JSON.stringify({ spent: d.spent, doneLast: d.doneLast }));
    ok(afterHole.length > 0 && afterHole.every((m) => m.end > 0 && m.source === 'piper'),
       'AND THE TAIL NEVER DIED: all ' + afterHole.length + ' chunks after the hole were ' +
       'read as real audio, to the last word',
       JSON.stringify(afterHole.map((m) => [m.i, m.source, !!m.end])));
    const dLast = d.marks[d.marks.length - 1] || {};
    ok(!!dLast.end && !dLast.silent,
       'the last line of the four was spoken, out loud, after the stumble',
       JSON.stringify(dLast));
    ok(d.engine === 'piper' && d.down === '',
       'AND ONE STUMBLE IS NOT A VERDICT: the local voice kept the session. It takes TWO ' +
       'consecutive misses to fall back, because a browser voice bought with one bad ' +
       'decode would cost the whole answer its voice',
       JSON.stringify({ engine: d.engine, down: d.down }));
    ok(d.stalls === f.stalls,
       'and the stall watchdog never had to fire: the placeholder advanced the queue ' +
       'inside its own deadline rather than being rescued by a timer',
       JSON.stringify({ before: f.stalls, after: d.stalls }));
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
    /* READ WHILE IT WAS DOWN, not afterwards. `down` is cleared by the next health poll,
       and that poll lands inside the few seconds this read takes - so the value at the end
       of the read is the value AFTER the recovery, and a check on it was asserting that
       the page had not recovered yet. The samples were taken every 120ms throughout. */
    const downSeen = a.samples.filter((s) => s.down).map((s) => s.down);
    ok(downSeen.length > 0 || a.down !== '',
       'the page knew the local voice was down and could say so, rather than hiding the ' +
       'fallback inside "engine": "' + (downSeen[0] || a.down) + '" · said on ' +
       downSeen.length + ' of ' + a.samples.length + ' samples',
       JSON.stringify({ atEnd: a.down, seen: [...new Set(downSeen)] }));
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

  /* ---- 10. THE CASTING PROTOCOL, AUDITIONED ------------------------------- */
  /* PART 2's second half: three candidates, one line, the boss picks. deck_proof has already
     checked that the panel LISTS the three the server names, in the server's order, under the
     right skin. What it cannot check is the only thing that matters to an ear - that pressing
     Hear produces audio of the right voice through the real bus. That is what this does, and
     it is the casting test the lookbook reports.

     IT NEVER PRESSES KEEP. Keep is what writes config.json, and this file does not write that
     file; the digest at the end of the run is the proof that it did not. */
  await page.evaluate('__galaxy.cmd.open_(true)');
  await page.evaluate('__galaxy.cmd.cast.open()');
  await waitFor(page, '!!__galaxy.cmd.cast.state', 12000);
  const cast = await page.json('({view: __galaxy.cmd.view, offline: __galaxy.cmd.cast.offline,' +
    ' state: __galaxy.cmd.cast.state, kept: __galaxy.cmd.cast.kept,' +
    ' auditions: __galaxy.cmd.cast.auditions, error: __galaxy.cmd.cast.error,' +
    ' line: (document.getElementById("cast-line")||{}).textContent,' +
    ' warn: (document.getElementById("cast-warn")||{}).textContent})');
  note('the casting panel: view ' + cast.view + ' · offline ' + cast.offline + ' · line ' +
       JSON.stringify(collapse(cast.line || '')));
  ok(cast.view === 'cast' && !!cast.state,
     'the casting view is up and holding the server’s own answer');

  if (!voices.piper) {
    /* PART 4's refusal on a machine that really has no piper. The banner is #cast-warn and
       NOT #cast-line: the line is the sentence the candidates read, and the state of the
       machine is a different sentence in a different element. */
    ok(cast.offline === true,
       'PIPER OFFLINE: the panel says so on its own face rather than offering three ' +
       'voices that cannot speak', JSON.stringify(cast));
    ok(/piper offline/i.test(collapse(cast.warn || '')),
       'and it reads "Piper Offline — Web Fallback", which is the sentence PART 4 asks for',
       JSON.stringify(cast.warn));
  } else {
    ok(cast.offline === false,
       'no offline banner, because the local voice is here', JSON.stringify(cast.offline));
    const ready = (voices.candidates || []).filter((c) => c.ready);
    note('auditioning ' + ready.length + ' of ' + CAST.length + ' candidates - each one ' +
         'speaks "' + collapse(voices.line || '') + '"');
    const heard = [];
    for (const c of ready) {
      const key = c.model.replace(/[^a-z0-9]+/gi, '-');
      const started = Date.now();
      const began = await page.evaluate(
        '__galaxy.cmd.cast.hear(' + JSON.stringify(c.model) + ')');
      /* WHILE IT IS PLAYING. An audition is speech too, so the chimes are under it. */
      const during = await page.json('({ducked: __galaxy.audio.ducked,' +
        ' gain: __galaxy.audio.gain, playing: __galaxy.cmd.cast.playing,' +
        ' node: __galaxy.cmd.cast.node})');
      const done = await waitFor(page, '/^heard/.test((document.getElementById("cast-st-' +
        key + '")||{}).textContent||"")', 30000);
      const st = await page.evaluate(
        '(document.getElementById("cast-st-' + key + '")||{}).textContent');
      const secs = Number((/([\d.]+)s/.exec(String(st)) || [])[1] || 0);
      heard.push({ model: c.model, began, during, done, st: String(st), secs,
                   wall: Date.now() - started });
      note('  ' + c.model.padEnd(20) + ' -> ' + JSON.stringify(String(st)) + ' in ' +
           ((Date.now() - started) / 1000).toFixed(1) + 's' +
           (during.ducked ? ' · chimes ducked to ' + during.gain : ''));
      await sleep(400);
    }
    ok(heard.length === ready.length && heard.every((h) => h.began === true),
       'EVERY INSTALLED CANDIDATE ACCEPTED THE AUDITION: ' + heard.length + ' of ' +
       CAST.length + ' - ' + heard.map((h) => h.model).join(', '),
       JSON.stringify(heard.map((h) => [h.model, h.began])));
    ok(heard.every((h) => h.done && /^heard/.test(h.st) && h.secs > 1),
       'AND EVERY ONE OF THEM WAS HEARD TO THE END: the panel reports the length it played ' +
       'for each (' + heard.map((h) => h.secs + 's').join(', ') + '), which is its own ' +
       'onended and not a hope', JSON.stringify(heard.map((h) => h.st)));
    ok(heard.every((h) => h.during.ducked === true && h.during.node === true),
       'with the chimes ducked under the audition as well - the casting booth is speech, ' +
       'and the same rule applies to it',
       JSON.stringify(heard.map((h) => h.during)));
    ok(await page.evaluate('__galaxy.cmd.cast.error === ""'),
       'and the panel has no error to report at the end of it',
       await page.evaluate('__galaxy.cmd.cast.error'));
    /* AND THE BUTLER OWNS THE BUS. An audition begun in the middle of a sentence is
       refused, in words, rather than played over the top of him. */
    await page.evaluate('__galaxy.speech.speakLine("A sentence in progress, sir.")');
    await waitFor(page, '__galaxy.voice.draining === true', 5000);
    const clash = await page.evaluate(
      '__galaxy.cmd.cast.hear(' + JSON.stringify(ready[0].model) + ')');
    const clashSt = await page.evaluate('(document.getElementById("cast-st-' +
      ready[0].model.replace(/[^a-z0-9]+/gi, '-') + '")||{}).textContent');
    ok(clash === false && /hold/i.test(String(clashSt)),
       'AN AUDITION IS REFUSED MID-SENTENCE: "' + String(clashSt) + '" - the butler owns ' +
       'this bus, and the panel says so instead of talking over him',
       JSON.stringify({ began: clash, said: clashSt }));
    await page.evaluate('__galaxy.speech.cancel("the harness, clearing the clash")');
    await sleep(400);
  }
  ok(await page.evaluate('__galaxy.cmd.cast.kept === ""'),
     'NOTHING WAS KEPT: the choice is the employer’s, and this run only listened',
     await page.evaluate('__galaxy.cmd.cast.kept'));

  /* ---- 10b. AND THE SAME PANEL WITH NO PIPER AT ALL ---------------------- */
  /* PART 4's first refusal: "Piper absent -> casting panel reads Piper Offline — Web
     Fallback and defaults to Windows natural voices, no crash." Piper IS installed on this
     machine, so the branch above can only ever take the other road - and a refusal path that
     is never walked is a refusal path nobody has checked. So /voices is answered once, in
     the page, with the payload a machine without piper would get: same three models, none
     installed, none ready, and piper:false. A PAINT, exactly like deck_proof's forced empty
     archive - the stub is removed in the same breath and the panel is re-asked afterwards,
     so what is proved is the page's reading of that answer and nothing about this disk.

     Why the banner and not the line: #cast-line is the sentence the candidates read, which
     does not change when piper leaves. #cast-warn is where the state of the machine goes. */
  const gone = JSON.parse(await page.evaluate(`(async function(){
    var real = window.fetch;
    var body = {engine: 'piper', piper: false,
      fallback: 'piper is not installed, for the proof',
      line: 'The archive is online, and the hands are wired, sir.',
      chosen: '', lengthScale: 1.05, noiseScale: 0.4,
      candidates: [{model:'en_US-ryan-high', label:'Ryan', note:'American, warm, unhurried',
                    installed:false, ready:false, why:'piper is not installed', chosen:false},
                   {model:'en_GB-alan-medium', label:'Alan', note:'English, clipped',
                    installed:false, ready:false, why:'piper is not installed', chosen:false},
                   {model:'en_US-joe-medium', label:'Joe', note:'American, plainer, lower',
                    installed:false, ready:false, why:'piper is not installed', chosen:false}],
      ok: true, kind: 'voices'};
    window.fetch = function(u, o){
      if (String(u).indexOf('/voices') === 0) {
        return Promise.resolve(new Response(JSON.stringify(body),
          {status: 200, headers: {'Content-Type': 'application/json'}}));
      }
      return real.apply(window, arguments);
    };
    var threw = '';
    try { await __galaxy.cmd.cast.open(); } catch (e) { threw = String(e && e.message || e); }
    window.fetch = real;
    var rows = Array.prototype.map.call(
      document.querySelectorAll('#cast-list .cand'), function(el){
        var b = el.querySelector('.crow button');
        var k = el.querySelector('.crow button.keep');
        return {model: el.getAttribute('data-model'),
                hear: !!(b && b.disabled), keep: !!(k && k.disabled)};
      });
    return JSON.stringify({threw: threw, offline: __galaxy.cmd.cast.offline,
      warn: (document.getElementById('cast-warn')||{}).textContent,
      line: (document.getElementById('cast-line')||{}).textContent,
      rows: rows, error: __galaxy.cmd.cast.error, kept: __galaxy.cmd.cast.kept,
      voice: __galaxy.voice.name, why: __galaxy.voice.why,
      engine: __galaxy.voice.engine, spoke: __galaxy.speech.said.length});
  })()`));
  note('with piper answered away: offline ' + gone.offline + ' · banner ' +
       JSON.stringify(collapse(gone.warn || '')) + ' · rows ' + JSON.stringify(gone.rows));
  ok(gone.threw === '' && gone.offline === true,
     'PIPER ABSENT, AND THE PANEL SAYS SO INSTEAD OF FALLING OVER: the offline state is on ' +
     'the sheet itself, and opening it threw nothing',
     JSON.stringify({ threw: gone.threw, offline: gone.offline, error: gone.error }));
  ok(/piper offline/i.test(collapse(gone.warn || '')) &&
     /web fallback/i.test(collapse(gone.warn || '')),
     'AND IT READS "PIPER OFFLINE — WEB FALLBACK": "' + collapse(gone.warn || '') + '", ' +
     'which is the sentence PART 4 asks for, naming the voice that takes over rather than ' +
     'leaving the reader to guess', JSON.stringify(gone.warn));
  ok(gone.rows.length === CAST.length && gone.rows.every((r) => r.hear && r.keep),
     'and all three candidates are still LISTED and every one of them is unpressable: ' +
     'what is missing is legible, rather than three voices that would refuse if you tried ' +
     'them', JSON.stringify(gone.rows));
  /* AND THE WEB VOICE IS THE ONE IT FALLS TO. Not a claim about the banner's wording: the
     page's own chosen voice is a real speechSynthesis voice off this machine, which is what
     "defaults to Windows natural voices" means when there is no piper to ask. */
  ok(!!gone.voice && /\S/.test(gone.voice),
     'with a Windows voice already cast behind it (' + gone.voice + ' - ' + gone.why + '), ' +
     'so the fallback the banner names is a voice this machine has and not a promise',
     JSON.stringify({ voice: gone.voice, why: gone.why, engine: gone.engine }));
  await page.evaluate('__galaxy.cmd.cast.open()');
  await sleep(600);
  const putBack = await page.json('({offline: __galaxy.cmd.cast.offline,' +
    ' warn: (document.getElementById("cast-warn")||{}).textContent,' +
    ' rows: Array.prototype.map.call(document.querySelectorAll("#cast-list .cand"),' +
    '  function(el){var b=el.querySelector(".crow button");' +
    '   return {model: el.getAttribute("data-model"), hear: !!(b && b.disabled)};})})');
  ok(putBack.offline === false && putBack.rows.length === CAST.length &&
     putBack.rows.every((r) => r.hear === false),
     'then the real /voices puts it back: no banner, three voices, all three pressable - ' +
     'the absence was a paint and nothing else', JSON.stringify(putBack));

  await page.evaluate('__galaxy.cmd.view_("list"); __galaxy.cmd.open_(false)');

  /* AND THE FILE IS AS IT WAS. The last word of the run, and the one that matters most:
     three auditions, two sabotaged reads and four minutes of speech later, config.json holds
     the same voice, the same number of keys, and the same digest of everything else. */
  const ended = readVoiceModel();
  ok(ended && disk && ended.digest === disk.digest && ended.model === disk.model &&
     ended.keys === disk.keys,
     'AND config.json IS BYTE-FOR-BYTE THE SAME DECISION IT WAS AT THE START: voice_model ' +
     'unchanged, ' + (ended ? ended.keys : '?') + ' keys, digest ' +
     (ended ? ended.digest : '?') + ' - this harness listened to the casting protocol and ' +
     'wrote nothing to the file that holds the credentials',
     JSON.stringify({ before: disk && disk.digest, after: ended && ended.digest }));

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
