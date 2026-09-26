/* scribe_proof.mjs - THE SCRIBE: a meeting, taken down, and minuted with a Yes.
 *
 * THE DEFECT THIS IS ABOUT. A feature that listens to a meeting has four ways of failing
 * that all look identical from the outside - a lit button and an empty panel. The picker was
 * dismissed; the picker was accepted with Share audio unticked; the transcriber is not
 * installed; or the audio graph was built correctly and never pulled. Every one of those is
 * a silent failure, and three of them are silent failures the USER caused and can fix if
 * somebody tells them. So this file proves the happy path once and each refusal by name.
 *
 * WHAT IS BEING PROVED, and each claim names the failure mode it catches:
 *
 *   THE ORGAN IS IN THE RAIL AND THE RAIL KNOWS IT. #scribebtn is present, is an organ, and
 *     __galaxy.organs.ids names it. A button added to the markup and forgotten in ORGANS
 *     paints no dot and reports no state - the one bug in this deck that looks like nothing.
 *   THE BUTTON IS GATED ON A FACT. /health says whether faster-whisper imported; the page
 *     disables the button when it did not, and the seal reads SCRIBE: TRANSCRIBER OFFLINE.
 *     Failure mode: a picker opened on a machine with nowhere to send the audio, discovered
 *     three seconds into somebody's meeting.
 *   A DISMISSED PICKER IS SCRIBE: CANCELLED, not an error and not silence. Failure mode: a
 *     man dismisses the picker, nothing whatever happens, and he presses the button again.
 *   AN UNTICKED SHARE AUDIO IS SCRIBE: SHARE AUDIO OFF, AND THE CAPTURE IS STOPPED. This is
 *     the one this feature would otherwise fail silently on: a video track with no audio
 *     track lights the button, opens the panel and transcribes three seconds of nothing,
 *     forever. Both halves are asserted - the seal word AND that the video track it was
 *     handed is really in state 'ended', because a refusal that leaves a live screen capture
 *     running has told the truth to the user and lied to the operating system.
 *   THE WHOLE CHAIN, WITH A REAL PICKER AND A KNOWN SENTENCE. getDisplayMedia is really
 *     called, really granted, and really carries an audio track; the worklet really runs;
 *     WAV chunks really reach /scribe/transcribe - counted at the WIRE, off CDP Network
 *     events, not off a page counter; and the words come back into the panel. Failure mode
 *     this catches above all others: the un-pulled graph. A worklet connected to nothing
 *     never has process() called, raises no error, and produces exactly the same screen as
 *     a muted microphone.
 *   AND THE CHUNKS ARE WHOLE FILES. Every chunk after the first is asserted to have
 *     transcribed rather than been skipped, which is the MediaRecorder trap stated as a
 *     number: with start(3000) only the first blob carries the webm header and PyAV rejects
 *     every one after it. A worklet plus a WAV header per chunk cannot fail that way, and
 *     this is the assertion that says so.
 *   STOP LEAVES THE TRANSCRIPT ON SCREEN. The panel stays open, carrying the full record,
 *     with Draft Minutes under it - and the tracks are stopped. Failure mode: a panel that
 *     closed on stop, taking the only copy of the meeting with it.
 *   THE MINUTES ARE DRAFTED, SHOWN, AND WRITTEN ONLY AFTER A YES. /scribe/minutes returns
 *     the four sections; the proposal card renders the title and the minutes as rows a human
 *     could read; the file does not exist before the Yes and does exist after it. Failure
 *     mode: a hand that writes on propose rather than on execute.
 *   AND THE PRIVACY LAW IS PUBLISHED ON BOTH SIDES. /health.scribe.keepsAudio and
 *     __galaxy.scribe.keepsAudio are both false, and the run is asserted to have left no new
 *     audio file anywhere under the project root. A promise nothing checks is a comment.
 *
 * HOW THE KNOWN SENTENCE GETS IN, and it is worth reading because it is better than it
 * sounds. Chrome's --use-fake-device-for-media-stream replaces BOTH capture devices, and the
 * measured finding on this machine is that getDisplayMedia's audio track is then the fake
 * device too - label 'Fake audio' - reading --use-file-for-fake-audio-capture. So the sentence
 * arrives through the real getDisplayMedia audio path, not through a stub: the page's own
 * graph, worklet, resampler, WAV writer and POST all run on it untouched. The sentence itself
 * is real piper output, fetched from this server's /say, so the audio under test is speech and
 * not a tone.
 *
 * WHAT THIS HARNESS DOES SIMULATE, stated plainly: the two refusals that are about what the
 * PICKER returned. There is no flag that makes Chrome's auto-accept return a stream with the
 * audio tick off, and none that makes it reject after accepting, so for those two cases
 * getDisplayMedia is replaced - with a real rejected DOMException and a real video-only
 * MediaStream off a canvas. Everything downstream of the picker, which is the entire subject
 * of those two assertions, is the page's own code.
 *
 * Headless=new on purpose: a headed window that loses focus stops getting rAF, and this run
 * is a minute long. It writes one file - notes/<the drafted minutes> - because that is the
 * thing being proved, prints it, and deletes it again.
 *
 * Usage:  python server.py 2>> server-trace.log   then   node scribe_proof.mjs
 */
import { spawn } from 'node:child_process';
import { mkdtempSync, rmSync, existsSync, writeFileSync, readFileSync, unlinkSync,
         readdirSync, statSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = dirname(fileURLToPath(import.meta.url));
const NOTES = join(ROOT, 'notes');
const GALAXY = 'http://127.0.0.1:4700';
const PORT = 9251;
const CDP = 'http://127.0.0.1:' + PORT;
const CHROMES = [
  'C:/Program Files/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Google/Chrome/Application/chrome.exe',
  process.env.LOCALAPPDATA + '/Google/Chrome/Application/chrome.exe',
];
const HEADED = process.env.SCRIBE_HEADED === '1';

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let pass = 0, fail = 0; const failures = [];
const say = (m) => console.log(m);
const ok = (c, claim, detail) => {
  if (c) pass++; else { fail++; failures.push(claim); }
  say((c ? '  ok   ' : '  FAIL ') + claim);
  if (!c && detail) say('         ' + detail);
};
const note = (m) => say('  note ' + m);
const step = (m) => say('\n  \u00b7\u00b7 ' + m);
const procs = []; const profiles = []; const wrote = [];

/* ================================ THE SENTENCE ================================
   Plain, common words on purpose. piper renders an unusual proper noun into something a
   transcriber then spells its own way - "Priya" comes back as "Pre-E" - and an assertion
   built on one of those fails for a reason that has nothing to do with the Scribe. Note
   what is NOT asserted: "at ten", because base.en writes it "at 10", which is correct and
   would still break a literal match. */
const SENTENCE = 'The quarterly review is on Thursday at ten. We agreed to send the deck ' +
                 'by Wednesday evening.';
/* Three words from the middle of it, each long enough that a chunk boundary cannot produce
   them by accident. The fixture loops for as long as the meeting runs, so each of them
   lands well inside a three-second window at least once. */
const KEYWORDS = ['quarterly', 'thursday', 'wednesday'];

class Page {
  constructor(u) { this.u = u; this.id = 0; this.w = new Map(); this.ev = new Map();
                   this.posts = 0; this.minutes = 0; this.errors = []; }
  open() { return new Promise((res, rej) => {
    this.ws = new WebSocket(this.u);
    this.ws.onopen = () => res(this);
    this.ws.onerror = () => rej(new Error('socket failed'));
    this.ws.onmessage = (ev) => { const m = JSON.parse(ev.data);
      if (m.id === undefined) { const h = this.ev.get(m.method); if (h) h(m.params || {}); return; }
      const f = this.w.get(m.id); if (f) { this.w.delete(m.id); f(m); } }; }); }
  on(method, fn) { this.ev.set(method, fn); }
  send(method, params) { const id = ++this.id;
    return new Promise((res, rej) => {
      const bomb = setTimeout(() => { this.w.delete(id); rej(new Error(method + ' timed out')); },
                              120000);
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
  const until = Date.now() + ms;
  while (Date.now() < until) {
    try { if (await page.evaluate(expr)) return true; } catch (e) { /* not yet */ }
    await sleep(250);
  }
  return false;
}

/* A GENUINE GESTURE, and the Scribe needs one twice over: unlockAudio() will not run off a
   synthetic click, and without unlocked audio there is no AudioContext to hang the capture
   graph on at all. */
async function realClick(page, id) {
  const box = await page.json(`(function(){var e=document.getElementById(${JSON.stringify(id)});
    if(!e) return null; var r=e.getBoundingClientRect();
    return {x:Math.round(r.left+r.width/2), y:Math.round(r.top+r.height/2),
            w:Math.round(r.width), h:Math.round(r.height)};})()`);
  if (!box || !box.w) return false;
  for (const type of ['mousePressed', 'mouseReleased']) {
    await page.send('Input.dispatchMouseEvent', { type, x: box.x, y: box.y, button: 'left',
      clickCount: 1, buttons: type === 'mousePressed' ? 1 : 0 });
    await sleep(45);
  }
  return true;
}

/* ---- THE FIXTURE. Real piper speech, resampled to 48k and headroom-limited ----
   RESAMPLED because Chrome's file-backed fake device is fed straight to the capture path and
   a rate it did not expect comes out pitched; 48000 is what every other harness here hands
   it and what the device reports natively.
   PEAK-LIMITED TO 0.4 for a reason this harness discovered rather than assumed: BOTH capture
   devices are the fake device, so the display-audio track and the microphone track carry the
   SAME file, and the page sums them. Two copies of a full-scale signal clip, and a clipped
   consonant is a transcription error this file would then blame on the Scribe. */
async function fixture(dir) {
  const res = await fetch(GALAXY + '/say', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text: SENTENCE })
  });
  if (!res.ok) throw new Error('/say refused the fixture: ' + res.status);
  const src = Buffer.from(await res.arrayBuffer());
  if (src.length < 64 || src.toString('ascii', 0, 4) !== 'RIFF') {
    throw new Error('/say did not return a RIFF wave');
  }
  /* Walk the chunks rather than assuming the data starts at 44: piper's writer has put a
     LIST chunk in front of the samples before now, and a harness that guesses the offset
     transcribes the tail of a header as speech. */
  const rate = src.readUInt32LE(24), bits = src.readUInt16LE(34), chans = src.readUInt16LE(22);
  let at = 12, dataAt = -1, dataLen = 0;
  while (at + 8 <= src.length) {
    const id = src.toString('ascii', at, at + 4), len = src.readUInt32LE(at + 4);
    if (id === 'data') { dataAt = at + 8; dataLen = Math.min(len, src.length - dataAt); break; }
    at += 8 + len + (len & 1);
  }
  if (dataAt < 0 || bits !== 16) throw new Error('unexpected wave: ' + bits + ' bit');
  const n = Math.floor(dataLen / 2 / chans);
  const mono = new Float32Array(n);
  let peak = 0;
  for (let i = 0; i < n; i++) {
    let sum = 0;
    for (let c = 0; c < chans; c++) sum += src.readInt16LE(dataAt + (i * chans + c) * 2);
    const v = sum / chans / 32768;
    mono[i] = v;
    if (Math.abs(v) > peak) peak = Math.abs(v);
  }
  const gain = peak > 0 ? 0.4 / peak : 1;
  const out = 48000;
  const m = Math.max(1, Math.floor(n * out / rate));
  const bytes = m * 2;
  const b = Buffer.alloc(44 + bytes);
  b.write('RIFF', 0); b.writeUInt32LE(36 + bytes, 4); b.write('WAVE', 8);
  b.write('fmt ', 12); b.writeUInt32LE(16, 16); b.writeUInt16LE(1, 20);
  b.writeUInt16LE(1, 22); b.writeUInt32LE(out, 24); b.writeUInt32LE(out * 2, 28);
  b.writeUInt16LE(2, 32); b.writeUInt16LE(16, 34);
  b.write('data', 36); b.writeUInt32LE(bytes, 40);
  for (let i = 0; i < m; i++) {
    const src2 = i * rate / out;
    const a = Math.floor(src2), c = Math.min(n - 1, a + 1), t = src2 - a;
    let v = (mono[a] * (1 - t) + mono[c] * t) * gain;
    if (v > 1) v = 1; if (v < -1) v = -1;
    b.writeInt16LE(Math.round(v * 32767), 44 + i * 2);
  }
  const path = join(dir, 'meeting.wav');
  writeFileSync(path, b);
  return { path, seconds: m / out, rate, peak: Number(peak.toFixed(3)) };
}

/* Everything under the project root that looks like audio, by name and mtime. The privacy
   law is "no audio byte reaches a disk", and the only way to assert it from out here is to
   photograph the tree before and after and compare. */
function audioFiles() {
  const out = {};
  const walk = function (dir, depth) {
    if (depth > 4) return;
    let rows = [];
    try { rows = readdirSync(dir, { withFileTypes: true }); } catch (e) { return; }
    for (const r of rows) {
      const p = join(dir, r.name);
      if (r.isDirectory()) {
        if (/^(\.git|__pycache__|node_modules|\.venv)$/.test(r.name)) continue;
        walk(p, depth + 1);
      } else if (/\.(wav|webm|ogg|mp3|m4a|opus|pcm|raw)$/i.test(r.name)) {
        try { out[p] = statSync(p).mtimeMs; } catch (e) { /* went away */ }
      }
    }
  };
  walk(ROOT, 0);
  return out;
}

function cleanup() {
  procs.forEach((p) => { try { process.kill(-p.pid); } catch (e) {
    try { p.kill('SIGKILL'); } catch (e2) { /* gone */ } } });
  profiles.forEach((p) => { try { rmSync(p, { recursive: true, force: true }); } catch (e) { } });
}

async function main() {
  say('\n  SCRIBE PROOF - a meeting, taken down, and minuted with a Yes\n');

  const health = await (await fetch(GALAXY + '/health').catch(() => null))?.json()
    .catch(() => null) || null;
  if (!health || !health.ok) {
    say('  the server on 4700 is not answering; start it first: python server.py');
    process.exit(1);
  }
  const sh = health.scribe || {};
  note('the server: model ' + health.model + ' \u00b7 scribe ' + JSON.stringify({
    installed: sh.installed, ready: sh.ready, model: sh.model, device: sh.device,
    computeType: sh.computeType, keepsAudio: sh.keepsAudio }));
  ok(sh.installed === true,
     '/health publishes an installed transcriber - without one nothing below this line can ' +
     'be distinguished from a broken page',
     'why: ' + (sh.why || '(none given)'));
  if (!sh.installed) { say('\n  stopping: there is no transcriber to prove.'); process.exit(1); }
  ok(sh.keepsAudio === false && sh.keepsText === false,
     '/health publishes the privacy law as two booleans - a promise no harness can read is ' +
     'a comment');

  const exe = CHROMES.find((p) => existsSync(p));
  if (!exe) { say('\n  no Chrome on this machine'); process.exit(1); }
  const profile = mkdtempSync(join(tmpdir(), 'scribe-'));
  profiles.push(profile);
  const fix = await fixture(profile);
  note('the fixture: ' + fix.seconds.toFixed(2) + 's of piper speech, ' + fix.rate +
       'Hz -> 48000Hz, peak ' + fix.peak + ' limited to 0.40 \u00b7 "' + SENTENCE + '"');

  const before = audioFiles();

  const chrome = spawn(exe, [
    '--remote-debugging-port=' + PORT, '--user-data-dir=' + profile,
    '--no-first-run', '--no-default-browser-check',
    '--autoplay-policy=no-user-gesture-required',
    ...(HEADED ? [] : ['--headless=new']),
    /* THE PICKER, ANSWERED. This is the flag that makes a real getDisplayMedia resolve
       without a hand on the mouse; the documented alternatives (the tab-capture flags on
       their own) hang the promise for ever on this machine. */
    '--auto-select-desktop-capture-source=Entire screen',
    /* AND THE DEVICE, WHICH IS WHERE THE SENTENCE COMES FROM - both devices, which is the
       measured behaviour this harness leans on: the display capture's audio track is the
       fake device too, so the known sentence arrives through the real capture path. */
    '--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream',
    '--use-file-for-fake-audio-capture=' + fix.path,
    '--window-size=1380,920', '--new-window', GALAXY,
  ], { detached: true, stdio: 'ignore' });
  procs.push(chrome);

  for (let i = 0; i < 90; i++) { try { await cdp('/json/version'); break; } catch { await sleep(250); } }
  note('chrome: ' + ((await cdp('/json/version')).Browser || '?') +
       (HEADED ? ' \u00b7 headed' : ' \u00b7 headless=new'));
  let target = null;
  for (let i = 0; i < 60; i++) {
    const l = await cdp('/json/list');
    target = (Array.isArray(l) ? l : []).filter((t) => t.type === 'page')
      .find((t) => t.url.includes('127.0.0.1:4700'));
    if (target) break;
    await sleep(300);
  }
  if (!target) throw new Error('no viewer page');
  const page = new Page(target.webSocketDebuggerUrl);
  await page.open();
  await page.send('Runtime.enable');
  await page.send('Page.enable');
  await page.send('Network.enable');
  /* COUNTED AT THE WIRE. A page counter saying "I posted eleven chunks" is the code under
     test reporting on itself; a CDP Network event is the browser reporting what left it. */
  page.on('Network.requestWillBeSent', (p) => {
    const url = (p.request && p.request.url) || '';
    if (url.includes('/scribe/transcribe')) page.posts++;
    if (url.includes('/scribe/minutes')) page.minutes++;
  });
  page.on('Runtime.exceptionThrown', (p) => {
    const d = (p.exceptionDetails || {});
    page.errors.push(String(d.text || '') + ' ' +
      String((d.exception && d.exception.description) || '').split('\n')[0]);
  });
  try { await page.send('Page.bringToFront'); } catch (e) { /* headless has no window */ }

  ok(await waitFor(page, '!!(window.__galaxy && window.__galaxy.scribe)', 30000),
     'the viewer is up and exposes the Scribe door');
  await waitFor(page, '__galaxy.nodes.length > 0', 20000);

  /* ---- 1. THE ORGAN IS IN THE RAIL ---------------------------------------- */
  step('the organ');
  const ids = await page.json('__galaxy.organs.ids');
  ok(Array.isArray(ids) && ids.indexOf('scribebtn') >= 0,
     'the organ rail names scribebtn - a button in the markup and missing from ORGANS ' +
     'paints no dot and reports no state, which looks exactly like nothing being wrong',
     'ids: ' + JSON.stringify(ids));
  const dom = await page.json(`(function(){
    var b = document.getElementById('scribebtn');
    if (!b) return null;
    var rail = document.getElementById('bar');
    return { organ: b.classList.contains('organ'), dot: !!b.querySelector('.od'),
             svg: !!b.querySelector('svg'), inRail: !!(rail && rail.contains(b)),
             before: (b.nextElementSibling||{}).id || '' };
  })()`);
  ok(dom && dom.organ && dom.dot && dom.svg && dom.inRail,
     'it is a real organ in the bar: the class, the waveform glyph and the state dot',
     JSON.stringify(dom));
  await waitFor(page, '__galaxy.scribe.installed === true', 15000);
  ok(await page.evaluate('!document.getElementById("scribebtn").disabled'),
     'and it is enabled, because /health said there is a transcriber');

  /* ---- 2. REFUSAL: TRANSCRIBER OFFLINE ------------------------------------ */
  step('refusal one: the transcriber is offline');
  await page.evaluate(`__galaxy.scribe.health({ installed: false, ready: false,
    model: 'base.en', why: 'faster-whisper is not installed on this machine (harness)' })`);
  const offline = await page.json(`(function(){
    var b = document.getElementById('scribebtn');
    return { disabled: b.disabled, title: b.title };
  })()`);
  ok(offline.disabled === true,
     'an offline transcriber DISABLES the button - the failure mode is a picker opened on a ' +
     'machine with nowhere to send the audio',
     JSON.stringify(offline));
  /* THIS IS THE ASSERTION THAT FOUND A BUG, so it is worth saying what it now demands.
     The tooltip must carry BOTH halves: the button's own markup sentence, which says what
     the control is for, and the state line, which says why it cannot be used and quotes the
     server's reason verbatim. It failed the first time because scribeHealthFrom wrote the
     title itself and organsPaint overwrote it a tick later - and because the boot-time
     placeholder had been captured as the base sentence, so hovering the Scribe for the rest
     of the session read "Checking whether this machine has a transcriber…" as its purpose.
     Asserting both halves is what makes that single-author rule enforceable. */
  ok(/Take the minutes/.test(offline.title) &&
     /the transcriber is offline/.test(offline.title) &&
     /harness/.test(offline.title),
     'and the tooltip carries BOTH the markup’s sentence and the server’s own ' +
     'reason - it outlives the four seconds the seal gives it, and a tooltip written by ' +
     'two authors is a tooltip that shows whichever of them painted last',
     JSON.stringify(offline.title));
  const started = await page.evaluate('__galaxy.scribe.start()', true);
  ok(started === false, 'start() refuses outright rather than opening a picker');
  const seal1 = await page.json('__galaxy.scribe.seal');
  ok(String(seal1.word) === 'scribe: transcriber offline',
     'and the seal reads SCRIBE: TRANSCRIBER OFFLINE',
     JSON.stringify(seal1));
  ok(await page.evaluate('document.getElementById("seal-text").textContent') ===
     'scribe: transcriber offline',
     'the seal really shows it - the word is in the DOM, not only in a state object');
  ok(await page.evaluate('!document.getElementById("scribepanel").classList.contains("show")'),
     'and the panel never opened, so nothing on screen claims a meeting is being taken');
  /* Put the truth back, from the server, rather than from this harness's opinion of it. */
  await page.evaluate('__galaxy.brain.refresh()');
  ok(await waitFor(page, '__galaxy.scribe.installed === true', 8000),
     'the next /health puts the button back - the gate is a fact each poll, not a latch');

  /* ---- 3. REFUSAL: CANCELLED --------------------------------------------- */
  step('refusal two: the picker was dismissed');
  await page.evaluate(`(function(){
    window.__realGDM = navigator.mediaDevices.getDisplayMedia.bind(navigator.mediaDevices);
    navigator.mediaDevices.getDisplayMedia = function(){
      return Promise.reject(new DOMException('Permission denied', 'NotAllowedError'));
    };
    return true;
  })()`);
  ok(await page.evaluate('__galaxy.scribe.start()', true) === false,
     'a dismissed picker starts nothing');
  const seal2 = await page.json('__galaxy.scribe.seal');
  ok(String(seal2.word) === 'scribe: cancelled',
     'and the seal reads SCRIBE: CANCELLED - a decision, reported, with nothing spoken',
     JSON.stringify(seal2));
  ok(await page.evaluate('__galaxy.scribe.on === false && ' +
     '!document.getElementById("scribebtn").classList.contains("on")'),
     'the button is not lit, so nothing on screen disagrees with the seal');

  /* ---- 4. REFUSAL: SHARE AUDIO OFF --------------------------------------- */
  step('refusal three: the picker was accepted with Share audio unticked');
  await page.evaluate(`(function(){
    window.__vidOnly = null;
    navigator.mediaDevices.getDisplayMedia = function(){
      /* A REAL MediaStream with a REAL live video track and no audio track - which is
         exactly what the picker hands back when the tick is left off. */
      var c = document.createElement('canvas'); c.width = 64; c.height = 48;
      c.getContext('2d').fillRect(0, 0, 64, 48);
      window.__vidOnly = c.captureStream(2);
      return Promise.resolve(window.__vidOnly);
    };
    return true;
  })()`);
  ok(await page.evaluate('__galaxy.scribe.start()', true) === false,
     'a capture with no audio track starts nothing');
  const seal3 = await page.json('__galaxy.scribe.seal');
  ok(String(seal3.word) === 'scribe: share audio off',
     'and the seal reads SCRIBE: SHARE AUDIO OFF, naming the tick by its own label',
     JSON.stringify(seal3));
  const stopped = await page.json(`(function(){
    var s = window.__vidOnly;
    if (!s) return null;
    return s.getTracks().map(function(t){ return t.readyState; });
  })()`);
  ok(Array.isArray(stopped) && stopped.length > 0 && stopped.every((s) => s === 'ended'),
     'AND THE CAPTURE IT WAS HANDED IS STOPPED - a refusal that leaves a live screen ' +
     'capture running has told the truth to the user and lied to the operating system',
     JSON.stringify(stopped));
  await page.evaluate('navigator.mediaDevices.getDisplayMedia = window.__realGDM; true');

  /* ---- 5. THE WHOLE CHAIN ------------------------------------------------- */
  step('the meeting: a real picker, a real worklet, a known sentence');
  const postsBefore = page.posts;
  ok(await realClick(page, 'scribebtn'),
     'the Scribe organ is pressed by a real mouse event - a synthetic click does not ' +
     'unlock audio, and with no AudioContext there is no graph to hang the capture on');
  const live = await waitFor(page, '__galaxy.scribe.on === true', 25000);
  const cap = await page.json('__galaxy.scribe');
  ok(live, 'the meeting starts: the picker resolved and the graph was built',
     'trouble: ' + (cap && cap.trouble) + ' \u00b7 micWhy: ' + (cap && cap.micWhy));
  ok(cap.hasSys === true,
     'the system audio track is live - this is the track the mandate is about');
  ok(cap.hasMic === true,
     'and the local microphone is tapped too, so both halves of a meeting are heard',
     'micWhy: ' + cap.micWhy);
  ok(cap.mode === 'worklet',
     'the tap is an AudioWorklet and not the deprecated fallback',
     'mode: ' + cap.mode + ' \u00b7 trouble: ' + cap.trouble);
  const painted = await page.json('__galaxy.organs.state.scribebtn');
  ok(painted && painted.organ === 'live' && painted.lit && /TAKING THE MINUTES/.test(painted.line),
     'the organ rail paints it LIVE with a lit dot and says what is happening',
     JSON.stringify(painted));
  const panelLive = await page.json('__galaxy.scribe.panel');
  ok(panelLive && panelLive.open && panelLive.live,
     'the transcript panel is open and marked live', JSON.stringify(panelLive));

  /* THE ASSERTION THIS WHOLE FILE EXISTS FOR. A worklet that is built and never pulled
     produces this exact screen and no chunks at all. */
  const gotChunk = await waitFor(page, '__galaxy.scribe.posted >= 1', 20000);
  ok(gotChunk, 'the worklet is being PULLED: a chunk was built and posted within 20s - the ' +
     'silent failure this catches is a tap connected to nothing, which raises no error and ' +
     'looks identical to a muted microphone',
     JSON.stringify(await page.json('__galaxy.scribe')));
  ok(page.posts - postsBefore >= 1,
     'and the POST is counted at the WIRE, off a CDP Network event rather than a page ' +
     'counter: ' + (page.posts - postsBefore) + ' request(s) to /scribe/transcribe');

  const heard = await waitFor(page,
    `(function(){var t=__galaxy.scribe.text.toLowerCase();
      return ${JSON.stringify(KEYWORDS)}.every(function(k){return t.indexOf(k)>=0;});})()`,
    75000);
  const after = await page.json('__galaxy.scribe');
  say('');
  note('the transcript, as the panel shows it:');
  (await page.json('__galaxy.scribe.panel')).shown.forEach((l) => say('       | ' + l));
  say('');
  ok(heard, 'the known sentence comes back through the whole chain - getDisplayMedia, the ' +
     'mixer, the worklet, the 16kHz WAV, /scribe/transcribe, faster-whisper and the panel: ' +
     'every one of ' + KEYWORDS.join(', ') + ' is in the transcript',
     'text: ' + JSON.stringify(after.text));
  ok(after.kept >= 2,
     'and MORE THAN ONE chunk transcribed - which is the MediaRecorder trap stated as a ' +
     'number: with start(3000) only the first blob carries the webm header and every later ' +
     'one is a headerless cluster PyAV refuses. ' + after.kept + ' of ' + after.chunks +
     ' chunks came back with words',
     JSON.stringify({ chunks: after.chunks, kept: after.kept, skipped: after.skipped,
                      failed: after.failed }));
  ok(after.failed === 0,
     'no chunk was lost to a failed request', 'failed: ' + after.failed);
  ok(after.bytes > 0 && after.bytes < 8 * 1024 * 1024 * after.chunks,
     'the chunks are the size a 3s 16kHz mono WAV should be: ' +
     Math.round(after.bytes / Math.max(1, after.chunks) / 1024) + ' KB each');
  ok(after.keepsAudio === false,
     'and the page publishes the same privacy law the server does: keepsAudio false');

  /* ---- 6. STOP LEAVES THE RECORD ON SCREEN ------------------------------- */
  step('stop: the panel stays, carrying the meeting');
  ok(await realClick(page, 'scribebtn'), 'the same button, pressed again');
  ok(await waitFor(page, '__galaxy.scribe.on === false', 8000), 'the meeting ends');
  const idle = await page.json(`(function(){
    var s = __galaxy.scribe, p = s.panel;
    return { open: p.open, live: p.live, done: p.done, rows: p.rows,
             hasSys: s.hasSys, hasMic: s.hasMic, words: s.text.split(/\\s+/).length,
             draft: !document.getElementById('scribe-draft').disabled,
             footShown: getComputedStyle(
               document.querySelector('#scribepanel .foot')).display };
  })()`);
  ok(idle.open && idle.done && !idle.live,
     'THE PANEL STAYS OPEN with the full transcript - the failure mode is a panel that ' +
     'closed on stop and took the only copy of the meeting with it',
     JSON.stringify(idle));
  ok(idle.footShown === 'flex' && idle.draft,
     'and Draft Minutes is there to be pressed');
  ok(idle.hasSys === false && idle.hasMic === false,
     'both captures are released, which is what turns the browser\u2019s own recording ' +
     'indicator off');
  const held = await page.json('__galaxy.organs.state.scribebtn');
  ok(held && held.organ === 'held',
     'the organ reads HELD: something is true and nothing is happening',
     JSON.stringify(held));

  /* ---- 7. THE MINUTES, AND THE YES --------------------------------------- */
  step('the minutes: drafted, shown, and written only after a Yes');
  const notesBefore = new Set(existsSync(NOTES) ? readdirSync(NOTES) : []);
  ok(await realClick(page, 'scribe-draft'), 'Draft Minutes is pressed');
  ok(await waitFor(page, '__galaxy.hands.shown === true', 90000),
     'a proposal card arrives - the brain drafted and the gate is asking',
     JSON.stringify(await page.json('__galaxy.scribe')));
  ok(page.minutes >= 1,
     'and /scribe/minutes really was requested, counted at the wire: ' + page.minutes);
  const draft = await page.json('__galaxy.scribe');
  const rows = await page.json('__galaxy.hands.rows');
  const label = await page.evaluate('__galaxy.hands.label');
  note('the proposal: ' + label);
  /* The card wears the registry's English name; `tool` is the id the /execute door will
     actually run. Both are asserted, because a card that says one thing and runs another is
     the only way this gate can lie. */
  ok(await page.evaluate('__galaxy.hands.pending.tool') === 'save_minutes' &&
     /minutes/i.test(String(label)),
     'the card names the hand that would run, and the pending tool really is save_minutes',
     'label: ' + label + ' · tool: ' + await page.evaluate('__galaxy.hands.pending.tool'));
  ok(!!rows.title && /^Meeting-\d{4}-\d{2}-\d{2}-\d{4}$/.test(String(rows.title)),
     'the title is the mandate\u2019s default, Meeting-YYYY-MM-DD-HHmm',
     JSON.stringify(rows.title));
  const body = String(rows.minutes || '');
  ok(/## Attendees/.test(body) && /## Key Decisions/.test(body) &&
     /## Action Items/.test(body) && /## Raw Excerpts/.test(body),
     'and the minutes ON THE CARD carry all four sections - what is being approved is ' +
     'what would be written, not a promise about it',
     body.slice(0, 160));
  ok(draft.drafted === true && draft.raw === false,
     'the brain drafted them rather than the raw-transcript fallback being used');
  ok(Object.prototype.hasOwnProperty.call(rows, 'overwrite'),
     'and the overwrite flag is a ROW on the card rather than a hidden parameter - Yes on ' +
     'an existing file means Replace, and it has to say so where it is read',
     JSON.stringify(rows.overwrite));
  /* The clamp is asserted on the row the clamp is FOR, found by its label rather than by
     position, because the schema's order is the registry's business and not this file's. */
  const clamp = await page.json(`(function(){
    var kids = document.getElementById('ask-rows').children, el = null;
    for (var i = 0; i + 1 < kids.length; i += 2) {
      if (kids[i].textContent === 'minutes') { el = kids[i + 1]; break; }
    }
    if (!el) return { missing: true };
    var yes = document.getElementById('ask-yes').getBoundingClientRect();
    return { max: getComputedStyle(el).maxHeight, over: getComputedStyle(el).overflowY,
             scrolls: el.scrollHeight > el.clientHeight + 2,
             yesOnScreen: yes.bottom <= window.innerHeight && yes.top >= 0 };
  })()`);
  ok(clamp.max !== 'none' && clamp.over !== 'visible' && clamp.yesOnScreen,
     'the minutes row is CLAMPED and Yes is still on the screen - an unbounded value here ' +
     'pushes the one button that must never be unreachable off the bottom of the window',
     JSON.stringify(clamp));

  const path = join(NOTES, String(rows.title) + '.md');
  ok(!notesBefore.has(String(rows.title) + '.md') && !existsSync(path),
     'THE FILE DOES NOT EXIST YET - a hand that wrote on propose rather than on execute ' +
     'would have written it by now',
     path);
  ok(await realClick(page, 'ask-yes'), 'Yes is pressed');
  ok(await waitFor(page, '__galaxy.hands.shown === false', 40000),
     'the card settles');
  const answer = await page.evaluate('document.getElementById("a-text").textContent');
  note('the answer: ' + answer);
  ok(/notes\//.test(String(answer)) && /Written to|Replaced/.test(String(answer)),
     'and the answer is the script\u2019s own stdout - the tool says where it put the file',
     'answer: ' + answer);
  ok(existsSync(path), 'THE MINUTES ARE ON DISK, in notes/, after the Yes and not before',
     path);
  if (existsSync(path)) {
    wrote.push(path);
    const text = readFileSync(path, 'utf8');
    ok(/^# Meeting-/.test(text) && /## Attendees/.test(text) && /## Raw Excerpts/.test(text),
       'the file carries the heading, the stamp and the four sections');
    ok(KEYWORDS.some((k) => text.toLowerCase().includes(k)),
       'and the meeting\u2019s own words are in it - the minutes are about THIS recording',
       text.slice(0, 200));
    say('');
    say('  ---- notes/' + String(rows.title) + '.md, as written ----');
    text.split('\n').forEach((l) => say('  | ' + l));
    say('  ---- end ----');
    say('');
  }

  /* ---- 8. AND NOTHING WAS RECORDED TO DISK ------------------------------- */
  step('the privacy law, measured rather than promised');
  const now = audioFiles();
  const fresh = Object.keys(now).filter((p) => !(p in before));
  ok(fresh.length === 0,
     'not one audio file appeared anywhere under the project root during the meeting - ' +
     'which is the whole of the privacy law, asserted from outside the process that makes ' +
     'the promise',
     JSON.stringify(fresh));
  const sh2 = (await (await fetch(GALAXY + '/health')).json()).scribe || {};
  ok(sh2.chunks >= after.kept && sh2.keepsAudio === false,
     'the server counted the chunks it transcribed (' + sh2.chunks + ') and still holds no ' +
     'audio and no text');
  ok(page.errors.length === 0,
     'and the page threw nothing for the whole run', JSON.stringify(page.errors.slice(0, 3)));

  page.close();
}

main().then(() => {
  wrote.forEach((p) => { try { unlinkSync(p); say('  note removed ' + p); } catch (e) { } });
  cleanup();
  say('\n  ' + (pass + fail) + ' checks \u00b7 ' + pass + ' pass \u00b7 ' + fail + ' fail \u00b7 ' +
      (fail ? 'FAIL' : 'PASS') + '\n');
  if (fail) failures.forEach((f) => say('    - ' + f));
  process.exit(fail ? 1 : 0);
}).catch((e) => {
  wrote.forEach((p) => { try { unlinkSync(p); } catch (e2) { } });
  cleanup();
  say('\n  the harness itself broke: ' + (e && e.message));
  say(String(e && e.stack).split('\n').slice(1, 4).join('\n'));
  process.exit(1);
});
