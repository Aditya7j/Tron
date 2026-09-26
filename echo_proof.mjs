/* echo_proof.mjs - THE ECHO LAW: he must not answer himself.
 *
 * THE DEFECT THIS IS ABOUT. The microphone can hear the speakers, so the recogniser
 * transcribes the butler's own answer and hands it to the funnel looking exactly like a
 * question. The page then asks itself the thing it just finished saying, and the next answer
 * is a transcript of the last one. It compounds, and the conversation leaves the room.
 *
 * WHAT IS BEING PROVED, and each claim names the failure mode it catches:
 *
 *   THE METRIC IS REAL ARITHMETIC AND NOT A RESEMBLANCE OF ONE. levenshtein('kitten',
 *     'sitting') is 3 in every textbook; a function that returned a plausible-looking number
 *     would pass a "similar strings score high" test and fail this one.
 *   THE METRIC IS THE RIGHT SHAPE FOR A TRANSCRIPT. A recogniser hands back eighteen
 *     characters of a four-hundred-character paragraph. Plain Levenshtein between those two
 *     is a distance of hundreds and a similarity near zero, so a PERFECT echo sails through
 *     a 0.70 threshold untouched. This harness measures both numbers on the same pair and
 *     asserts they disagree - which is the bug the free-ended distance fixes, stated as a
 *     number rather than as a paragraph of comment.
 *   AND IT STILL SAYS NO. The one way a filter like this fails silently is by becoming a
 *     wall: drop everything, score nothing, and the log fills with successes. So a genuinely
 *     different sentence of similar length is asserted to score UNDER the threshold, and the
 *     last step of this file asks an ordinary question in a quiet room and asserts it reaches
 *     the brain.
 *   LAYER 1 REFUSES HIS OWN WORDS - exact, fragmentary, and mangled the way a recogniser
 *     mangles a speaker leak - while the engine is really speaking, with the real microphone
 *     really open.
 *   THE INTERRUPTS ARE BEHIND THE LAW AND NOT IN FRONT OF IT. 'stop' is a barked word that
 *     skips the buffer and empties the queue. The line under test contains "I shall stop
 *     there", so a leak transcribed as 'stop' would cancel the answer mid-sentence: the
 *     self-answer defect wearing a control's clothes. Asserted by the queue surviving.
 *   INTERIMS COUNT TOO. An interim never reaches the brain by itself, and it does two other
 *     things: it lands in lastInterim, where flushThought staples it to the front of the next
 *     real question, and it re-arms the finish timer that decides when the room went quiet.
 *   LAYER 2 REFUSES WHAT LAYER 1 COULD NOT READ. A distinct sentence - one this harness has
 *     already proved scores under the threshold - is fed while the engine speaks into a quiet
 *     room, and is dropped anyway, because nothing in the room was 3.0x the output reference.
 *     The reference is asserted to be 'bus': real post-gain samples off speechBus, not a
 *     number this harness handed in.
 *   AND THE BARGE-IN STILL REGISTERS, which is the assertion that stops Layer 2 from being a
 *     mute button. Frames above 3.0x the measured output, sustained, open the gate; the
 *     distinct sentence then goes through and /chat is really requested.
 *   ZERO INPUTS TO THE BRAIN, counted at the wire. Every drop above is checked against a CDP
 *     Network counter on requests to /chat rather than against a page door, because a door
 *     that said "nothing was routed" is the same code under test saying it about itself.
 *
 * WHAT THIS HARNESS DOES NOT CLAIM. It does not feed the butler's audio into the recogniser,
 * because it cannot: window.SpeechRecognition opens its own capture inside the browser and
 * accepts no MediaStream, and Chrome's recognition service is throttled to silence under a
 * harness. So the transcript arrives through __galaxy.speech.feedFinal - the recogniser's own
 * door, the one conversation_proof has always used - and everything downstream of that door,
 * which is the whole of the law, runs for real. The two halves that are NOT simulated are the
 * ones that matter: the audio is real piper output through the real audio graph, so the output
 * reference is a measured signal, and the microphone is really open on the real device.
 *
 * Headed and NOT muted, because a ?mute=1 tab renders no audio, and with no audio there is no
 * speechBus, no analyser tapped off it, and no output reference - every Layer 2 assertion
 * would pass against a reference of zero, which is the one way this file could lie. It talks
 * out loud for about a minute. It writes nothing anywhere.
 *
 * Usage:  python server.py 2> server-trace.log   then   node echo_proof.mjs
 */
import { spawn } from 'node:child_process';
import { mkdtempSync, existsSync, statSync, openSync, readSync, closeSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const GALAXY = 'http://127.0.0.1:4700';
const PORT = 9248;
const CDP = 'http://127.0.0.1:' + PORT;
const TRACE = process.env.TRACE || 'server-trace.log';
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

/* The usual self-contained Page, with one addition: an EVENT tap. Every other harness here
   only ever answers its own requests, so its onmessage drops anything without an id - which
   is every CDP event there is. The /chat counter below is a Network event, and counting at
   the wire instead of at a page door is the difference between "the code says it routed
   nothing" and "nothing left the browser". */
class Page {
  constructor(u) { this.u = u; this.id = 0; this.w = new Map(); this.ev = new Map(); }
  open() { return new Promise((res, rej) => {
    this.ws = new WebSocket(this.u);
    this.ws.onopen = () => res(this);
    this.ws.onerror = (e) => rej(new Error('socket: ' + (e.message || 'failed')));
    this.ws.onmessage = (ev) => { const m = JSON.parse(ev.data);
      if (m.id === undefined) { const h = this.ev.get(m.method); if (h) h(m.params || {}); return; }
      const f = this.w.get(m.id); if (f) { this.w.delete(m.id); f(m); } }; }); }
  on(method, fn) { this.ev.set(method, fn); }
  send(method, params) { const id = ++this.id;
    return new Promise((res, rej) => {
      const bomb = setTimeout(() => { this.w.delete(id); rej(new Error(method + ' timed out')); }, 120000);
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
  /* NOT for an async expression: this wraps in JSON.stringify, which stringifies the Promise
     itself and leaves awaitPromise nothing to wait for. Use evaluate() for those. */
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

/* A GENUINE GESTURE. document.body.click() does not unlock audio, and without unlocked audio
   there is no AudioContext, no speechBus, and therefore no output reference at all - so every
   Layer 2 claim in this file rests on this function having worked. */
async function realClick(page, x, y) {
  for (const type of ['mousePressed', 'mouseReleased']) {
    await page.send('Input.dispatchMouseEvent',
      { type, x, y, button: 'left', clickCount: 1, buttons: type === 'mousePressed' ? 1 : 0 });
    await sleep(40);
  }
}

/* say.py writes one line per SYNTHESIS and never per cache hit, so this is how the outside
   world knows piper really ran rather than a wav being read off disk. */
function traceMark() { try { return statSync(TRACE).size; } catch (e) { return -1; } }
function traceSince(mark) {
  if (mark < 0) return null;
  try {
    const size = statSync(TRACE).size;
    if (size <= mark) return '';
    const fd = openSync(TRACE, 'r');
    const buf = Buffer.alloc(size - mark);
    readSync(fd, buf, 0, buf.length, mark);
    closeSync(fd);
    return buf.toString('utf8');
  } catch (e) { return null; }
}
const TRACE_LIVE = traceMark() >= 0;
const synths = (txt) => (txt ? [...txt.matchAll(/^say: \d+ chars -> \d+ bytes/gm)].length : 0);

/* ================================ THE SENTENCES ================================
   ONE line is spoken and everything is judged against it. It is long enough to have a middle
   - a transcript is a fragment, and a fragment of a two-word line proves nothing - and it
   contains "I shall stop there" on purpose, because 'stop' is a barked interrupt and the
   whole point of putting the echo law ahead of the interrupts is that a leak saying it must
   not empty the queue. */
const LINE = 'The roaster on the second shelf is warm, sir, and I have set the table by the ' +
             'window. I shall stop there unless you would like the rest of the inventory ' +
             'read out loud.';
/* Word for word, a piece of the middle: the substring case. */
const FRAGMENT = 'and I have set the table by the window';
/* WHAT A RECOGNISER ACTUALLY RETURNS. Three substitutions of the kind that come from hearing
   a speaker rather than a mouth - roaster/roster, warm/worm, shelf/shell - no punctuation and
   no capitals. This is the case exact matching cannot catch and the reason for the 0.70. */
const MANGLED = 'the roster on the second shell is worm sir and i have set the table by the window';
/* AND A SENTENCE THAT IS NOT HIS. Similar length, ordinary English, nothing in common. If the
   filter cannot tell this from the three above it is not a filter, it is a wall. */
const DISTINCT = 'What is the weather in Vancouver tomorrow afternoon and should I take a coat';

say('\n  ECHO PROOF - the butler must not answer himself');

const health = await (await fetch(GALAXY + '/health').catch(() => null))?.json()
  .catch(() => null) || null;
if (!health || !health.ok) {
  say('\n  the server on 4700 is not answering; start it first: python server.py');
  process.exit(1);
}
note('the server: model ' + health.model + ' · say ' + JSON.stringify(health.say));
ok(TRACE_LIVE, 'the server\u2019s trace is readable at ' + TRACE + ' - without it "piper ' +
   'really ran" is an assumption rather than a line', 'run: python server.py 2> ' + TRACE);

const exe = CHROMES.find((p) => existsSync(p));
if (!exe) { say('\n  no Chrome on this machine'); process.exit(1); }
const profile = mkdtempSync(join(tmpdir(), 'echo-'));
/* THE FAKE UI AND NOT A FAKE DEVICE, and the difference is load-bearing. --use-fake-ui
   answers the permission prompt, so the session can be opened without a hand on the mouse.
   A fake DEVICE would replace the microphone with Chrome's generated tone, which is a signal
   this harness invented - and the whole subject here is what a real microphone does with a
   real speaker in the same room. The device stays real; only the prompt is automated. */
const chrome = spawn(exe, ['--remote-debugging-port=' + PORT, '--user-data-dir=' + profile,
  '--no-first-run', '--no-default-browser-check', '--window-size=1200,820',
  '--use-fake-ui-for-media-stream', '--autoplay-policy=no-user-gesture-required',
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

/* ---- THE COUNTER AT THE WIRE ----
   Every request the page makes, tallied by path. `chat` is the one that matters: it is the
   only way a question reaches the brain, so "the brain received zero inputs" is this number
   not moving. Counted here rather than read from __galaxy so that the thing under test is
   not also the witness. */
const wire = { chat: 0, done: 0, all: 0, last: '' };
await page.send('Network.enable');
page.on('Network.requestWillBeSent', (p) => {
  const u = String((p.request && p.request.url) || '');
  wire.all++;
  if (/\/chat(\?|$)/.test(u)) { wire.chat++; wire.last = u; wire.ids = wire.ids || new Set(),
    wire.ids.add(p.requestId); }
});
page.on('Network.loadingFinished', (p) => {
  if (wire.ids && wire.ids.has(p.requestId)) { wire.ids.delete(p.requestId); wire.done++; }
});
const chatMark = () => wire.chat;
/* ASKING IS REFUSED WHILE THE PAGE IS BUSY - ask() returns on `busy` before it does anything
   at all - so a step that asks a second question before the first answer has landed reads a
   still wire and calls it a refusal. This waits for the brain to be free, at the wire, since
   there is no busy door and inventing one to satisfy a harness would be the wrong repair. */
async function brainFree(ms = 90000) {
  for (let i = 0; i < ms / 250; i++) {
    if (wire.done >= wire.chat) {
      if (await page.evaluate("document.getElementById('status').className !== 'thinking'")) {
        return true;
      }
    }
    await sleep(250);
  }
  return false;
}

ok(await waitFor(page, '!!(window.__galaxy && __galaxy.speech && __galaxy.ear && __galaxy.ear.echo)',
                 30000),
   'the viewer is up and the echo door is open at __galaxy.ear.echo');

await realClick(page, 600, 700);
await sleep(400);
ok(await waitFor(page, '__galaxy.speech.unlocked === true', 8000),
   'a real mouse gesture unlocked the audio - the AudioContext, the speech bus and the ' +
   'analyser tapped off it all depend on this, and so does every output reference below');
ok(await page.evaluate('__galaxy.speech.muted === false'),
   'the tab is NOT muted, so the words really reach the speakers: a muted tab would give a ' +
   'reference of zero and pass Layer 2 for the wrong reason');

const doorC = await page.json('__galaxy.ear.echo');
note('the law\u2019s own numbers: similarity > ' + doorC.SIMILARITY + ' is an echo · the ' +
     'gate wants ' + doorC.GATE_RATIO + 'x held ' + doorC.GATE_SUSTAIN_MS + 'ms · a finished ' +
     'line is still his voice for ' + doorC.TAIL_MS + 'ms');
ok(doorC.SIMILARITY === 0.7 && doorC.GATE_RATIO === 3,
   'the two thresholds are the mandate\u2019s: 0.70 on the similarity and 3.0x on the gate',
   JSON.stringify(doorC));
const bargeDoor = await page.json('__galaxy.ear.barge');
ok(bargeDoor.RATIO === 1.6,
   'and the BARGE-IN ratio is still 1.6, untouched - two gates, two different wagers: 1.6 ' +
   'decides whether to cut a sentence short, 3.0 decides whether words reach the brain, and ' +
   'voice_proof asserts the first one',
   JSON.stringify({ barge: bargeDoor.RATIO, echo: doorC.GATE_RATIO }));
ok(doorC.streamGated === false && doorC.transcriptGated === true,
   'the page PUBLISHES where the valve is rather than implying it: the stream is not gated ' +
   'and the transcript is, because ' + doorC.gatedWhy,
   JSON.stringify({ streamGated: doorC.streamGated, transcriptGated: doorC.transcriptGated }));

/* ============================== 1. THE METRIC, ALONE ============================== */
step('1. THE METRIC ON ITS OWN - no room, no engine, no page state');

const kitten = await page.evaluate('__galaxy.ear.echo.levenshtein("kitten","sitting")');
ok(kitten === 3, 'levenshtein("kitten","sitting") === 3, the textbook value - a function ' +
   'that merely returned small numbers for similar strings would pass a vaguer test than ' +
   'this one and be wrong arithmetic', 'got ' + kitten);
const same = await page.evaluate('__galaxy.ear.echo.levenshtein("' + FRAGMENT + '","' +
                                 FRAGMENT + '")');
ok(same === 0, 'and zero against itself, so the metric has no floor of its own', 'got ' + same);

const simSelf = await page.evaluate('__galaxy.ear.echo.similarity(' + JSON.stringify(LINE) +
                                    ',' + JSON.stringify(LINE) + ')');
ok(simSelf === 1, 'the whole line against itself scores 1.000', 'got ' + simSelf);

/* THE SHAPE PROBLEM, AS TWO NUMBERS ON ONE PAIR. */
const plain = await page.evaluate('__galaxy.ear.echo.levenshtein(' + JSON.stringify(FRAGMENT) +
                                  ',' + JSON.stringify(LINE) + ')');
const simFrag = await page.evaluate('__galaxy.ear.echo.similarity(' + JSON.stringify(FRAGMENT) +
                                    ',' + JSON.stringify(LINE) + ')');
note('the fragment against the whole line: plain distance ' + plain + ' (similarity about ' +
     (1 - plain / LINE.length).toFixed(2) + ' if taken that way) but the law scores ' + simFrag);
ok(plain > 90, 'a WORD-FOR-WORD piece of the line is ' + plain + ' plain edits away from it ' +
   '- which is the trap: read as a plain similarity that is about ' +
   (1 - plain / LINE.length).toFixed(2) + ', far under 0.70, and a perfect echo would have ' +
   'been routed to the brain', 'plain distance ' + plain);
ok(simFrag === 1, 'and the law scores the same pair 1.000, because the distance is taken ' +
   'against the best-matching SUBSTRING of what is being spoken - the free-prefix, ' +
   'free-suffix form - so a fragment is measured as a fragment', 'got ' + simFrag);

const simMangled = await page.evaluate('__galaxy.ear.echo.similarity(' + JSON.stringify(MANGLED) +
                                       ',' + JSON.stringify(LINE) + ')');
ok(simMangled > 0.7, 'a MANGLED fragment - roaster/roster, shelf/shell, warm/worm, the ' +
   'substitutions a microphone hearing a speaker produces - still scores ' +
   simMangled.toFixed(3) + ', over the threshold: this is the case exact matching cannot ' +
   'catch and the only reason the filter is fuzzy at all', 'got ' + simMangled);

const simDistinct = await page.evaluate('__galaxy.ear.echo.similarity(' + JSON.stringify(DISTINCT) +
                                        ',' + JSON.stringify(LINE) + ')');
ok(simDistinct < 0.7, 'and a DIFFERENT sentence of similar length scores only ' +
   simDistinct.toFixed(3) + ', under the threshold - without this assertion every drop below ' +
   'is consistent with a filter that drops everything, which is how a feature like this ' +
   'fails without anybody noticing', 'got ' + simDistinct);
note('so the threshold has ' + (simMangled - simDistinct).toFixed(3) +
     ' of daylight on either side of it between a leak and a question');

/* =========================== 2. THE MICROPHONE IS OPEN =========================== */
step('2. THE MICROPHONE IS REALLY OPEN - the mandate\u2019s "while the mic is open"');

const raised = await page.evaluate('__galaxy.ear.raise()');
ok(raised && raised.ok === true && raised.open === true,
   'the ear session opened for real through the organ\u2019s own door: getUserMedia was ' +
   'called, the prompt was answered, and the session is live', JSON.stringify(raised));
ok(raised && raised.stream === true && raised.analyser === true,
   'and the stream and the analyser are both up - so the loudness numbers Layer 2 reads are ' +
   'coming off a real device in a real room rather than out of this file',
   JSON.stringify(raised));
if (raised && raised.engine) note('the recogniser: ' + raised.engine + ' (the transcripts ' +
  'below arrive through feedFinal, which is the door it uses itself)');

/* ============================ 3. LAYER 1: HIS OWN WORDS ============================ */
step('3. LAYER 1 - the words he is saying, coming back at him');

const mark = traceMark();
/* THE ENGINE HAS TO BE PIPER BEFORE A WORD IS SPOKEN, and it is worth waiting for rather
   than working around. speakEngine starts at 'web' and only becomes 'piper' when a /health
   poll says the local voice is ready, so a harness that spoke on the first tick would be
   testing the browser's synthesiser - which never passes through this page's audio graph at
   all, leaving no speechBus, no analyser tapped off it, and an output reference of zero for
   every Layer 2 claim below. */
const gotPiper = await waitFor(page, '__galaxy.voice.engine === "piper"', 20000);
const engine = await page.evaluate('__galaxy.voice.engine');
ok(gotPiper && engine === 'piper',
   'the engine is piper - a real audio graph, so the output reference Layer 2 reads is ' +
   'post-gain samples off speechBus rather than a zero that would pass every gate assertion ' +
   'in this file for the wrong reason', 'engine is ' + engine);
/* SPOKEN FOR REAL. speakLine is the one funnel, so this is the same path an answer takes. */
await page.evaluate('__galaxy.speech.speakLine(' + JSON.stringify(LINE) + ')');
const speaking = await waitFor(page, '__galaxy.voice.draining || __galaxy.voice.queue > 0', 20000);
ok(speaking, 'the engine is speaking the line - every judgement in this step is against a ' +
   'queue that is really running, not against an empty one');
/* AND A CHUNK IS ACTUALLY IN FLIGHT, not merely queued behind a synthesis: piper takes about
   a second on a cold line, and during that second the queue is live while the bus is silent -
   which is a reference of zero wearing the clothes of a real measurement. */
ok(await waitFor(page, '__galaxy.voice.now >= 0', 25000),
   'and a chunk is in flight rather than queued behind a synthesis - so there is real audio ' +
   'on the bus for the reference to be measured from');

const spokenNow = await page.json('__galaxy.ear.echo.spoken');
ok(spokenNow.live === true && spokenNow.now.length > 40,
   'and the law can SEE what is being said: ' + spokenNow.now.length + ' characters of the ' +
   'chunk in flight plus the queue behind it, which is the mandate\u2019s "the active chunk ' +
   'and speakQueue"', JSON.stringify(spokenNow).slice(0, 300));

const before = await page.json('__galaxy.ear.echo.state');
const thoughtsBefore = (await page.json('__galaxy.ear.thoughts')).length;
const chatBefore = chatMark();

/* (a) THE EXACT SENTENCE. */
const jExact = await page.json('__galaxy.ear.echo.judge(' + JSON.stringify(LINE) + ')');
ok(jExact.kind === 'echo' && jExact.layer === 1,
   'his own sentence, word for word, is judged an ECHO by Layer 1: ' + jExact.why,
   JSON.stringify(jExact));
await page.evaluate('__galaxy.speech.feedFinal(' + JSON.stringify(LINE) + ')');
await sleep(120);
let after = await page.json('__galaxy.ear.echo.state');
ok(after.dropped === before.dropped + 1,
   'and feeding it through the recogniser\u2019s own door really dropped it - the count ' +
   'moved from ' + before.dropped + ' to ' + after.dropped + ', which is the drop being ' +
   'visible rather than silent', JSON.stringify(after));
ok(after.layer1 === before.layer1 + 1, 'by Layer 1 specifically, not by the gate',
   JSON.stringify(after));

/* (b) A WORD-FOR-WORD FRAGMENT: the substring case, named as itself. */
await page.evaluate('__galaxy.speech.feedFinal(' + JSON.stringify(FRAGMENT) + ')');
await sleep(120);
let log = await page.json('__galaxy.ear.echo.log');
let last = log[log.length - 1] || {};
ok(last.layer === 1 && /word for word/.test(last.why || ''),
   'a fragment of the middle is refused as a substring and the log SAYS substring rather ' +
   'than leaving it to be inferred from a 1.00: "' + (last.why || '') + '"',
   JSON.stringify(last));

/* (c) THE MANGLED ONE - the case the whole fuzziness exists for. */
await page.evaluate('__galaxy.speech.feedFinal(' + JSON.stringify(MANGLED) + ')');
await sleep(120);
log = await page.json('__galaxy.ear.echo.log');
last = log[log.length - 1] || {};
ok(last.layer === 1 && last.similarity > 0.7,
   'and the mangled transcript is refused on its score of ' + last.similarity +
   ', with the number written down beside the refusal: "' + (last.why || '') + '"',
   JSON.stringify(last));

/* (d) AN INTERIM. It never reaches the brain by itself, which is exactly why it is easy to
   forget - and forgetting it leaves his voice stapled to the front of the next question. */
const dropsBeforeInterim = (await page.json('__galaxy.ear.echo.state')).dropped;
await page.evaluate('__galaxy.speech.feedInterim(' + JSON.stringify(FRAGMENT) + ')');
await sleep(120);
after = await page.json('__galaxy.ear.echo.state');
ok(after.dropped === dropsBeforeInterim + 1,
   'an INTERIM of his own voice is dropped too - it would not have reached the brain by ' +
   'itself, it would have been appended to the next real question by flushThought and it ' +
   'would have kept re-arming the finish timer that decides the room has gone quiet',
   JSON.stringify(after));
const kept = await page.json('__galaxy.ear.kept');
ok(kept.transcript === 0,
   'and nothing of it was kept: the transcript buffer is ' + kept.transcript +
   ' characters long, so no part of his own sentence is waiting to be stapled to the next one',
   JSON.stringify(kept));

/* (e) THE BARKED WORD. */
const queueBefore = await page.json('__galaxy.voice.queue');
await page.evaluate('__galaxy.speech.feedFinal("stop")');
await sleep(200);
const stillSpeaking = await page.evaluate('__galaxy.voice.draining || __galaxy.voice.queue > 0');
log = await page.json('__galaxy.ear.echo.log');
last = log[log.length - 1] || {};
ok(last.text === 'stop' && last.layer === 1,
   '"stop" - leaked out of "I shall stop there" - is refused by the law BEFORE it reaches ' +
   'the interrupts: ' + (last.why || ''), JSON.stringify(last));
ok(stillSpeaking === true,
   'and the answer is STILL BEING READ, queue ' + queueBefore + ' then still draining - ' +
   'which is the assertion that the echo law sits in front of the interrupts and not ' +
   'behind them, because behind them a leaked "stop" empties the queue and the butler ' +
   'cuts himself off mid-sentence', String(stillSpeaking));

/* (f) AND THE WIRE. */
const thoughtsAfter = (await page.json('__galaxy.ear.thoughts')).length;
ok(chatMark() === chatBefore,
   'THE BRAIN RECEIVED ZERO INPUTS across all five drops - counted at the wire by CDP, ' +
   'still ' + chatMark() + ' request(s) to /chat, not by asking the page whether it had ' +
   'behaved', JSON.stringify({ before: chatBefore, now: chatMark(), all: wire.all }));
ok(thoughtsAfter === thoughtsBefore,
   'and not one thought was formed: ' + thoughtsAfter + ' in the log, the same number as ' +
   'before he started talking to himself',
   JSON.stringify({ before: thoughtsBefore, after: thoughtsAfter }));

/* ============================ 4. LAYER 2: THE GATE SHUT ============================ */
step('4. LAYER 2 - the words got past the filter; the room did not');

/* Quiet frames first, through the VAD's own door, so the gate has actually MEASURED the
   output rather than merely never having looked. 0.01 is under EAR_VAD_ON, so this is a
   quiet room and the barge-in gate is not being provoked. */
const quiet = await page.evaluate(
  '(async function(){ var g = null; ' +
  'for (var i = 0; i < 60; i++) { __galaxy.ear.vad(0.01); ' +
  '  g = __galaxy.ear.echo.gate; ' +
  '  if (i >= 12 && g.reference === "bus" && g.output > 0) break; ' +
  '  await new Promise(function(r){ setTimeout(r, 30); }); } ' +
  'return g; })()');
note('a quiet room against a live answer: input ' + quiet.input + ' against output ' +
     quiet.output + ' from the ' + quiet.reference + ' (' + quiet.ratio + 'x)');
ok(quiet.reference === 'bus' && quiet.output > 0,
   'the output reference is REAL: ' + quiet.output + ' RMS of post-gain samples read off ' +
   'speechBus through the analyser already tapped there for the mouth - not a number this ' +
   'harness handed in, which is what would make the whole of Layer 2 circular',
   JSON.stringify(quiet));
ok(quiet.open === false,
   'and the gate is SHUT, because nothing in the room came to ' + doorC.GATE_RATIO +
   'x that - the machine\u2019s own speakers leaking into the machine\u2019s own microphone ' +
   'measured ' + quiet.ratio + 'x, which is the field condition this law exists for',
   JSON.stringify(quiet));

const chatBefore2 = chatMark();
const jDistinct = await page.json('__galaxy.ear.echo.judge(' + JSON.stringify(DISTINCT) + ')');
ok(jDistinct.kind === 'echo' && jDistinct.layer === 2,
   'and now the sentence this harness PROVED scores only ' + simDistinct.toFixed(3) +
   ' - under the threshold, invisible to Layer 1 - is dropped anyway, by the gate: ' +
   jDistinct.why, JSON.stringify(jDistinct));
const l2Before = (await page.json('__galaxy.ear.echo.state')).layer2;
await page.evaluate('__galaxy.speech.feedFinal(' + JSON.stringify(DISTINCT) + ')');
await sleep(200);
after = await page.json('__galaxy.ear.echo.state');
ok(after.layer2 === l2Before + 1,
   'the drop is counted against Layer 2 specifically, ' + l2Before + ' then ' + after.layer2 +
   ' - so the two layers are separately provable and a regression in one cannot hide behind ' +
   'the other', JSON.stringify(after));
ok(chatMark() === chatBefore2,
   'and again nothing reached the brain: a transcript the recogniser mangled past all ' +
   'recognition still cannot get through, because to get through something in the room has ' +
   'to have been loud enough to be a person',
   JSON.stringify({ before: chatBefore2, now: chatMark() }));
ok((await page.json('__galaxy.ear.kept')).transcript === 0,
   'and the transcript buffer is still empty, so it was dropped rather than deferred');

/* ========================= 5. THE LOUD HUMAN BARGE-IN ========================= */
step('5. AND THE BARGE-IN REGISTERS - the assertion that stops Layer 2 being a mute button');

const stillLive = await page.evaluate('__galaxy.voice.draining || __galaxy.voice.queue > 0');
if (!stillLive) {
  note('the line finished; speaking it again so the barge-in has something to barge into');
  await page.evaluate('__galaxy.speech.speakLine(' + JSON.stringify(LINE) + ')');
  await waitFor(page, '__galaxy.voice.draining || __galaxy.voice.queue > 0', 20000);
  await sleep(900);
}
/* THE LEVEL IS COMPUTED FROM THE MEASURED OUTPUT, in the page, on the frame it is used. A
   fixed number would be either unreachable or free depending on how loud piper happened to
   be, and "3.6x whatever the speakers are actually doing" is the only version of this that
   is the same test twice. */
/* THE MAXIMA ARE CARRIED OUT OF THE LOOP AND THE LOOP STOPS ON SUCCESS, because the first
   version of this read the gate AFTERWARDS and found sustainedMs back at 0: a voice loud
   enough to clear 3.0x has already cleared the 1.6x barge-in gate, so the answer was
   cancelled, the queue went dry, and the sustain window was reset by the engine going quiet
   - the gate's own evidence erased by the gate working. */
const loud = await page.evaluate(
  '(async function(){ var maxSus = 0, maxRatio = 0, lvl = 0, ref = 0, gate = null; ' +
  'for (var i = 0; i < 30; i++) { ' +
  '  ref = __galaxy.ear.echo.gate.output || 0; ' +
  '  lvl = Math.min(0.99, Math.max(__galaxy.ear.VAD_ON * 1.5, ref * 3.6)); ' +
  '  __galaxy.ear.vad(lvl); ' +
  '  gate = __galaxy.ear.echo.gate; ' +
  '  if (gate.sustainedMs > maxSus) maxSus = gate.sustainedMs; ' +
  '  if (gate.ratio > maxRatio) maxRatio = gate.ratio; ' +
  '  if (gate.open && maxSus >= __galaxy.ear.echo.GATE_SUSTAIN_MS) break; ' +
  '  await new Promise(function(r){ setTimeout(r, 30); }); } ' +
  'return { level: lvl, ref: ref, maxSustainedMs: maxSus, maxRatio: maxRatio, ' +
  '         gate: gate, bargeIns: __galaxy.ear.bargeIns }; })()');
note('a voice leaning in: ' + loud.level.toFixed(3) + ' against ' + loud.ref.toFixed(3) +
     ' = ' + loud.maxRatio + 'x, held ' + loud.maxSustainedMs + 'ms');
ok(loud.maxRatio > 3,
   'the room was driven over ' + doorC.GATE_RATIO + 'x the MEASURED output - ' +
   loud.maxRatio + 'x - rather than over a fixed number that might have been free or ' +
   'unreachable depending on how loud the answer happened to be', JSON.stringify(loud));
ok(loud.maxSustainedMs >= doorC.GATE_SUSTAIN_MS,
   'and held there ' + loud.maxSustainedMs + 'ms, over the ' + doorC.GATE_SUSTAIN_MS +
   'ms asked - so one slammed door or one loud consonant is not a human being',
   JSON.stringify(loud));
ok(loud.gate.open === true,
   'THE GATE IS OPEN. Without this assertion every refusal above is consistent with a gate ' +
   'welded shut, which would be a page that had stopped listening rather than a page that ' +
   'had stopped answering itself', JSON.stringify(loud.gate));
ok(loud.gate.opens >= 1, 'and it opened exactly on an episode rather than flickering: ' +
   loud.gate.opens + ' opening(s)', JSON.stringify(loud.gate));
if (loud.bargeIns > 0) {
  note('the 1.6x barge-in gate took it as well and stopped the answer - which is the ' +
       'existing behaviour and untouched: a voice that clears 3.0x clears 1.6x on the way');
}

const chatBefore3 = chatMark();
const jOpen = await page.json('__galaxy.ear.echo.judge(' + JSON.stringify(DISTINCT) + ')');
ok(jOpen.kind === 'heard',
   'and the same sentence that was refused a moment ago is now HEARD: ' + jOpen.why,
   JSON.stringify(jOpen));
await page.evaluate('__galaxy.speech.feedFinal(' + JSON.stringify(DISTINCT) + ')');
/* FINISH_MS is 900 in the viewer: heardFinal BUFFERS and the thought is flushed by the
   recogniser's own pause afterwards, so a harness that checked the wire on the next tick
   would read zero and call it a refusal. Twice the pause, and then look. */
await sleep(1800);
ok(chatMark() === chatBefore3 + 1,
   'THE BARGE-IN REACHED THE BRAIN: exactly one new request to /chat, counted at the wire - ' +
   'one question in, one question through, and the law let it past on the loudness rather ' +
   'than on the words', JSON.stringify({ before: chatBefore3, now: chatMark() }));
/* The answer is on its way and this file has no business with it; the queue is emptied so
   the last step below starts from a quiet room instead of waiting out a paragraph. */
await page.evaluate('__galaxy.speech.cancel("the echo harness, having got its answer")');

/* ===================== 6. A QUIET ROOM IS NOT A GATED ROOM ===================== */
step('6. AND IN A QUIET ROOM THE LAW IS INERT - the regression this feature could become');

ok(await brainFree(), 'the brain has answered the barge-in and the page is free again - and ' +
   'this is waited for rather than assumed, because ask() returns immediately while the page ' +
   'is busy, so a question asked into a thinking page leaves the wire still and looks exactly ' +
   'like a refusal', JSON.stringify({ chat: wire.chat, finished: wire.done }));
await page.evaluate('__galaxy.speech.cancel("the echo harness, clearing the answer")');
await waitFor(page, '!__galaxy.voice.draining && __galaxy.voice.queue === 0', 30000);
/* Past ECHO_TAIL_MS since the engine went quiet, so the tail window has closed too. */
await sleep(doorC.TAIL_MS + 900);
const spokenQuiet = await page.json('__galaxy.ear.echo.spoken');
ok(spokenQuiet.live === false && spokenQuiet.tail === '',
   'the engine has been quiet for ' + spokenQuiet.sinceLiveMs + 'ms, past the ' +
   doorC.TAIL_MS + 'ms tail, so there is nothing left for a transcript to be an echo OF',
   JSON.stringify(spokenQuiet));
const jQuiet = await page.json('__galaxy.ear.echo.judge(' + JSON.stringify(LINE) + ')');
ok(jQuiet.kind === 'heard',
   'and even HIS OWN SENTENCE, verbatim, is heard now: ' + jQuiet.why + ' - the law is about ' +
   'a leak in progress, not a blacklist of things the butler has ever said, and a filter ' +
   'that kept refusing it would refuse the boss quoting him back',
   JSON.stringify(jQuiet));
const passedBefore = (await page.json('__galaxy.ear.echo.state')).passed;
const chatBefore4 = chatMark();
await page.evaluate('__galaxy.speech.feedFinal("What time is it, please")');
await sleep(1800);
after = await page.json('__galaxy.ear.echo.state');
ok(after.passed > passedBefore,
   'an ordinary question in a quiet room is PASSED, ' + passedBefore + ' then ' + after.passed +
   ' - the count of things the law let through, which is the number that would sit still if ' +
   'this feature had quietly become a wall', JSON.stringify(after));
ok(chatMark() === chatBefore4 + 1,
   'and it reached the brain: one more request to /chat',
   JSON.stringify({ before: chatBefore4, now: chatMark() }));
await page.evaluate('__galaxy.speech.cancel("the echo harness, closing")');

/* ============================== THE TALLY ============================== */
step('THE EVIDENCE');
const finalState = await page.json('__galaxy.ear.echo.state');
const finalLog = await page.json('__galaxy.ear.echo.log');
note('the law\u2019s ledger: ' + finalState.dropped + ' dropped (' + finalState.layer1 +
     ' by the words, ' + finalState.layer2 + ' by the room) and ' + finalState.passed +
     ' passed');
for (const e of finalLog) {
  say('       drop  L' + e.layer + '  sim ' + String(e.similarity).padEnd(5) + '  "' +
      String(e.text).slice(0, 46) + '"');
  say('             ' + e.why);
}
const trace = traceSince(mark);
const n = synths(trace);
/* A NOTE AND NOT A VERDICT, and the demotion is a correction rather than a concession.
   This was written as `ok(n > 0)` on the reasoning that a cache hit would mean "the audio
   the output reference was measured from was a file being reread". That reasoning is wrong
   twice over. It is wrong about the mechanism: say.py hands back the same WAV bytes either
   way, the page decodes them and plays them through the same speechBus, and the analyser
   reads post-gain samples off that bus - a cache hit is not a silent bus, and this very run
   measured 0.250 RMS on one. And it is wrong about itself: LINE is a fixed sentence, so the
   cache is cold exactly once per machine and the assertion could only ever pass on the first
   run and then fail for ever, which is an assertion that tests the age of a directory.
   What it was reaching for is asserted properly at the Layer 2 gate above - reference ===
   'bus' && output > 0, which is the measurement itself rather than a proxy for it. The count
   stays here as evidence, because knowing whether piper ran or the cache answered is worth
   a line when reading a transcript of this run six weeks later. */
note('piper synthesised ' + n + ' chunk(s) inside this run; the other ' +
     (n ? 'chunks came' : 'audio came') + ' from say-cache. Either way the bytes reach ' +
     'speechBus and the output reference measured off it was ' + quiet.output + ' RMS from ' +
     'the ' + quiet.reference + ' - which is the claim, and it is asserted above');
const earFinal = await page.json('__galaxy.ear.kept');
ok(earFinal.audio === 0 && earFinal.recorders === 0 && earFinal.transcript === 0,
   'nothing was kept: no audio, no recorder, and an empty transcript buffer at the end of a ' +
   'run that put nine transcripts through the funnel', JSON.stringify(earFinal));

await page.evaluate('__galaxy.ear.close("the echo harness")').catch(() => null);
page.close();
try { process.kill(-chrome.pid); } catch (e) { try { chrome.kill(); } catch (e2) { } }

say('\n  VERIFY ' + pass + '/' + (pass + fail) + (fail ? ' FAIL' : ' PASS'));
if (fail) { say('  failed:'); failures.forEach((f) => say('    - ' + f.slice(0, 110))); }
process.exit(fail ? 1 : 0);
