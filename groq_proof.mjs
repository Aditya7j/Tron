/* groq_proof.mjs - THE BORROWED ENGINES, AND THE ROOM THEY RUN IN.
 * =============================================================================================
 * §28 puts a second supplier behind four of this house's senses - the tongue, the ear, the eyes
 * and the voice - and leaves every default exactly where it was. That combination is what makes
 * it dangerous: a flag that does nothing looks identical to a flag that works, right up until
 * the boss flips it in front of somebody. So every claim below is about a MEASUREMENT, and each
 * one names the failure it exists to catch.
 *
 *   A. THE FLAGS AT REST. The four engines read bedrock, browser, bedrock, piper - the same
 *      house as before a line of this was written - and the key is a length and a digest.
 *      Failure mode: an integration that quietly becomes the default the day it is merged,
 *      which is how a laptop with no network stops answering at all.
 *
 *   B. THE SWITCH, AND WHAT IT SPENDS. "/model groq" flips the tongue, the chip reads
 *      GROQ · <model>, and the switch spends ONE completion - then nothing, forever, until
 *      somebody asks something. Failure mode: a "ready?" ping on a timer, which is a bill
 *      that arrives monthly for a feature nobody used.
 *
 *   C. AND BACK, WITH ZERO RESIDUE. Failure mode: a restore that clears the label and leaves
 *      the routing, so the chip says OPUS while Groq answers - correct in every log.
 *
 *   D. THE REFUSAL AND THE FALLBACK LAW, from groq_sandbox.py. Those two laws are about what
 *      happens when Groq will not answer, and a working key cannot demonstrate either. The
 *      sandbox builds a second server out of the same module with urlopen stubbed for
 *      api.groq.com only, and measures all four capabilities under a blank key, a 429, a
 *      timeout and a 401. See its docstring for why that is not a source review.
 *
 *   E. THE EAR AND THE VOICE, AS A ROUND TRIP. Orpheus is asked to say one known sentence and
 *      whisper-large-v3-turbo is asked to read it back. Failure mode this catches that no
 *      status check can: audio that is 200 OK and unintelligible - a wrong sample rate, a
 *      truncated body, a header from one engine over the bytes of another.
 *
 *   F. THE QUIET TONGUE RUNS FIRST, for Piper and Orpheus alike, because both are fed from the
 *      page's one funnel. Failure mode: a second engine wired in below the normalizer, and the
 *      boss hearing "asterisk asterisk important asterisk asterisk".
 *
 *   G. THE FULL ROOM. Ctrl+A goes fullscreen, the Layout Governor re-measures, Escape comes
 *      back out - and while the caret is in a field the keystroke is left alone and means
 *      select-all. Failure mode: a deck that eats Ctrl+A in the ask bar, which is the one
 *      keystroke everybody uses to retype a question.
 *
 *   H. AND THE KEY IS NOWHERE. Not in /health, not in a payload, not in server-trace.log.
 *
 * IT SPENDS REAL GROQ CALLS - one ping, one completion, one vision read, one Orpheus line and
 * one transcription, all against the boss's own key. That is the point: every one of them is a
 * receipt in the lookbook. Nothing here writes config.json, and the four flags are put back
 * with POST /engines {"reset": true} on the way out, which is also what a restart does.
 *
 * Usage:  python server.py 2>> server-trace.log   then   node groq_proof.mjs   (solo)
 */
import { spawn, spawnSync } from 'node:child_process';
import { mkdtempSync, rmSync, existsSync, readFileSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const GALAXY = 'http://127.0.0.1:4700';
/* NOT MUTED, and it is the only harness in this project that opens the viewer that way: the
   page refuses to speak at all on a mute=1 tab - see MUTED in index.html - and two of the
   claims here are about what the voice funnel actually sends. Chrome is started with
   --mute-audio instead, so the desktop stays quiet while the page does the whole job. */
const VIEW = GALAXY + '/';
const PORT = 9288;                       // nobody else's; see the port map in the lookbook
const CDP = 'http://127.0.0.1:' + PORT;
const ROOT = dirname(fileURLToPath(import.meta.url));
const PY = 'C:/Users/Fullstack Developer/AppData/Local/Programs/Python/Python313/python.exe';
const TRACE = join(ROOT, 'server-trace.log');
const SANDBOX_OUT = join(ROOT, '_runs', 'groq_sandbox.json');
/* THE SENTENCE THE ROUND TRIP USES. Digits on purpose: "900" is what a transcriber writes for
   "nine hundred", so a transcript that comes back with the numeral is evidence the audio was
   really decoded rather than the text being echoed back from somewhere. */
const SAID = 'The finish window should stay at nine hundred milliseconds.';
const STARRED = 'This is **important**, sir - the *finish* window.';
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
const step = (m) => console.log('\n  ---- ' + m + ' ----\n');

class Page {
  constructor(u) { this.u = u; this.id = 0; this.w = new Map(); }
  open() {
    return new Promise((res, rej) => {
      this.ws = new WebSocket(this.u);
      this.ws.onopen = () => res(this);
      this.ws.onerror = (e) => rej(new Error('socket: ' + (e.message || 'failed')));
      this.ws.onmessage = (ev) => {
        const m = JSON.parse(ev.data);
        const f = this.w.get(m.id);
        if (f) { this.w.delete(m.id); f(m); }
      };
    });
  }
  send(method, params) {
    const id = ++this.id;
    return new Promise((res, rej) => {
      const bomb = setTimeout(() => {
        this.w.delete(id); rej(new Error(method + ' timed out'));
      }, 30000);
      this.w.set(id, (m) => { clearTimeout(bomb); res(m); });
      this.ws.send(JSON.stringify({ id, method, params: params || {} }));
    });
  }
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
const cdp = async (p) => {
  const r = await fetch(CDP + p); const t = await r.text();
  try { return JSON.parse(t); } catch { return t; }
};
const get = async (path) => {
  const r = await fetch(GALAXY + path); const t = await r.text();
  try { return { status: r.status, body: JSON.parse(t), text: t }; }
  catch { return { status: r.status, body: t, text: t }; }
};
const post = async (path, body) => {
  const r = await fetch(GALAXY + path, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body || {}),
  });
  const t = await r.text();
  try { return { status: r.status, body: JSON.parse(t), text: t }; }
  catch { return { status: r.status, body: t, text: t }; }
};
/* Bytes, for the one route that answers with audio. */
const postWav = async (path, body) => {
  const r = await fetch(GALAXY + path, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body || {}),
  });
  const buf = Buffer.from(await r.arrayBuffer());
  return { status: r.status, bytes: buf.length, riff: buf.slice(0, 4).toString() === 'RIFF',
           buf, source: r.headers.get('x-say-source') || '' };
};
/* One utterance up to /ear/transcribe, as multipart, because that is the shape the route
   reads - and building it by hand here rather than borrowing FormData keeps the boundary and
   the part name under this file's control. */
const postAudio = async (path, buf) => {
  const boundary = '----groqproof' + Date.now().toString(16);
  const head = Buffer.from('--' + boundary + '\r\nContent-Disposition: form-data; ' +
    'name="audio"; filename="utterance.wav"\r\nContent-Type: audio/wav\r\n\r\n');
  const tail = Buffer.from('\r\n--' + boundary + '--\r\n');
  const r = await fetch(GALAXY + path, {
    method: 'POST', body: Buffer.concat([head, buf, tail]),
    headers: { 'Content-Type': 'multipart/form-data; boundary=' + boundary },
  });
  const t = await r.text();
  try { return { status: r.status, body: JSON.parse(t), text: t }; }
  catch { return { status: r.status, body: t, text: t }; }
};
async function waitFor(page, expr, ms = 8000) {
  for (let i = 0; i < ms / 200; i++) {
    try { if (await page.evaluate(expr)) return true; } catch { }
    await sleep(200);
  }
  return false;
}
/* A REAL KEYSTROKE, through the browser's own input pipeline, because the Fullscreen API
   requires a user gesture and a dispatched-from-JS event does not carry one. This is the whole
   reason section G drives Chrome instead of calling requestFullscreen() from evaluate(). */
async function press(page, key, code, vk, modifiers = 0, text) {
  for (const type of ['keyDown', 'keyUp']) {
    await page.send('Input.dispatchKeyEvent', Object.assign({
      type, key, code, windowsVirtualKeyCode: vk, nativeVirtualKeyCode: vk, modifiers,
    }, type === 'keyDown' && text ? { text } : {}));
    await sleep(40);
  }
}
const ctrlA = (page) => press(page, 'a', 'KeyA', 65, 2);
const escape = (page) => press(page, 'Escape', 'Escape', 27, 0);

/* A GENUINE GESTURE, and the reason the first run of this file measured "0 chunk(s)" for a
   page that was working perfectly. speakLine() has three gates in front of it: MUTED, no
   speech engine at all, and audioUnlocked - and the third is Chrome's autoplay policy, which
   --autoplay-policy=no-user-gesture-required does NOT satisfy, because audioUnlocked is the
   PAGE's own flag, set by a click it believes came from a human. Without it the line is not
   refused, which would have been easier to read: it is HELD as pendingLine for the first
   gesture, so say() returns false, the chunk log stays empty, and every assertion below reads
   a page that is patiently waiting rather than one that is broken. document.body.click() will
   not do it either. Only Input.dispatchMouseEvent will. */
async function realClick(page, x, y) {
  for (const type of ['mousePressed', 'mouseReleased']) {
    await page.send('Input.dispatchMouseEvent',
      { type, x, y, button: 'left', clickCount: 1, buttons: type === 'mousePressed' ? 1 : 0 });
    await sleep(40);
  }
}

const engines = async () => (await get('/health')).body.engines || {};
const flip = (what, word) => post('/engines', { [what]: word });
const resetEngines = () => post('/engines', { reset: true });

const profiles = []; const procs = [];
let flipped = false;                     // something is being held away from config.json

async function main() {
  console.log('\n  the borrowed engines: four flags, one client, and the room they run in\n');

  /* ============== A. THE FLAGS AT REST ================================================= */
  step('A. the four engines, and the key as a digest');
  const h0 = await get('/health');
  if (h0.status !== 200) throw new Error('the server on 4700 is not answering; start it first');
  const e0 = h0.body.engines || {};
  ok(!!e0.served && !!e0.configured, 'the server publishes both what is SERVING and what ' +
     'config.json would bring back on a restart',
     JSON.stringify(e0).slice(0, 200) + ' - one label for two facts is how a rail ends up ' +
     'reading the file while the route reads the override');
  const DEFAULTS = { chat: 'bedrock', ear: 'browser', vision: 'bedrock', voice: 'piper' };
  for (const [which, word] of Object.entries(DEFAULTS)) {
    ok(e0.configured[which] === word,
       'config.json still serves the ' + which + ' from ' + word,
       'configured.' + which + ' is ' + e0.configured[which] + ' - §28 says today\'s ' +
       'behaviour is the default, and an integration that becomes the default on merge is ' +
       'how a laptop with no network stops answering');
  }
  ok(Object.values(e0.overrides || {}).every((v) => !v),
     'and nothing is being held away from the file: every override is empty',
     JSON.stringify(e0.overrides) + ' - a leftover override survives until a restart and ' +
     'reads as configuration to everybody looking at config.json');
  const key = e0.groqKey || {};
  ok(key.present === true && key.length > 20 && /^[0-9a-f]{12}$/.test(String(key.sha256)),
     'the key is present and described as a length and a twelve-character digest: ' +
     key.length + ' chars, sha256 ' + key.sha256,
     JSON.stringify(key) + ' - if this is not a digest it is a credential on the wire');
  ok(!/gsk_/.test(h0.text),
     'and the whole /health body has no "gsk_" anywhere in it',
     'the key or a fragment of it is in a response the browser can read');
  note('models: ' + JSON.stringify(e0.models));
  const calls0 = (e0.calls || {});
  note('calls so far this process: ' + JSON.stringify(calls0));

  /* ============== B. THE SWITCH ========================================================= */
  step('B. /model groq - the switch, the cell, and the one ping it spends');
  const bedrockLabel = (h0.body.brain || {}).label || '';
  /* READ AGAIN, IMMEDIATELY BEFORE THE SWITCH. The counter arithmetic below is the whole of
     "one cheap ping", so the window it is measured over has to be as narrow as the two
     requests that bracket it - section A's reading is several assertions old, and anything
     that happened in between would be charged to the switch. */
  const justBefore = await engines();
  const swap = await post('/model', { say: 'groq', door: 'curl' });
  ok(swap.status === 200 && swap.body.ok === true,
     'the spoken switch is accepted: "groq" through the same door every other swap uses',
     'HTTP ' + swap.status + ' ' + JSON.stringify(swap.body).slice(0, 220));
  ok(swap.body.intro === 'groq',
     'and it says which engine it moved to rather than only that it moved');
  ok(/^GROQ · /.test(String(swap.body.label || '')),
     'THE CELL CHANGES: the chip reads "' + swap.body.label + '"',
     'label is ' + JSON.stringify(swap.body.label) + ' - the boss must be able to see which ' +
     'engine is answering without asking it');
  ok(swap.body.ping === true && !swap.body.pingError,
     'the one cheap ping came back: Groq answered "ready" on the switch',
     'ping ' + swap.body.ping + ' pingError ' + JSON.stringify(swap.body.pingError) +
     ' - a switch that cannot say hello has moved the boss onto an engine that will refuse ' +
     'his next question instead');
  const e1 = await engines();
  ok(e1.served.chat === 'groq' && e1.configured.chat === 'bedrock',
     'the TONGUE is served by groq while the file still says bedrock - which is what makes ' +
     'the flip instant and the restart honest',
     JSON.stringify(e1.served) + ' / ' + JSON.stringify(e1.configured));
  ok(e1.served.ear === 'browser' && e1.served.vision === 'bedrock' &&
     e1.served.voice === 'piper',
     'and ONLY the tongue moved: the ear, the eyes and the voice are where they were',
     JSON.stringify(e1.served) + ' - §28 says flipping one engine changes one engine');
  const spentOnSwitch = (e1.calls.chat || 0) - (justBefore.calls.chat || 0);
  ok(spentOnSwitch === 1,
     'and the switch spent EXACTLY one completion, not two and not a probe loop',
     'chat calls went ' + (justBefore.calls.chat || 0) + ' -> ' + (e1.calls.chat || 0) +
     ' across the one request. The ledger at that moment: ' +
     JSON.stringify(e1.log || []).slice(0, 400) + ' - a second call here is either a retry ' +
     'inside the client or a probe somebody added to /health, and both are bills that ' +
     'arrive without a question being asked');
  /* NO POLLING, MEASURED BY WAITING. /health is polled by the page every few seconds and this
     harness has just called it twice; if anything on the server pinged Groq on a timer, the
     counter would move while nothing was asked. */
  await sleep(6000);
  const e1b = await engines();
  ok((e1b.calls.chat || 0) === (e1.calls.chat || 0),
     'six seconds and three health reads later the counter has not moved: no polling',
     'chat calls ' + e1.calls.chat + ' -> ' + e1b.calls.chat + ' - a ready-check on a timer ' +
     'is a bill that arrives monthly for a feature nobody used');

  const t0 = Date.now();
  const askGroq = await post('/chat', { question: 'In one short sentence, sir: what is the ' +
    'capital of France?', session: 'groq-proof' });
  const groqMs = Date.now() - t0;
  ok(askGroq.status === 200 && !!askGroq.body.answer && !askGroq.body.error,
     'and a real question gets a real answer from Groq in ' + groqMs + 'ms',
     'HTTP ' + askGroq.status + ' ' + JSON.stringify(askGroq.body).slice(0, 300));
  note('groq said: ' + JSON.stringify(String(askGroq.body.answer || '').slice(0, 160)));
  const e2 = await engines();
  const chatRow = (e2.log || []).filter((r) => r.capability === 'chat').slice(-1)[0] || {};
  ok(chatRow.served === 'groq' && chatRow.outcome === 'ok',
     'and the ledger has a row for it: chat served by groq, outcome ok',
     JSON.stringify(chatRow) + ' - a borrowed engine with no ledger row is an engine that ' +
     'can be answering for a month with nobody able to prove it');

  /* ============== C. AND BACK, WITH ZERO RESIDUE ======================================= */
  step('C. "go back to your normal brain" - and nothing left behind');
  const back = await post('/model', { say: 'back', door: 'curl' });
  ok(back.status === 200 && back.body.restored === true,
     'the restore is accepted through the same door');
  ok(!/GROQ/.test(String(back.body.label || '')) && back.body.label === bedrockLabel,
     'the cell reads "' + back.body.label + '" again, exactly as it did before the switch',
     'before ' + JSON.stringify(bedrockLabel) + ' after ' + JSON.stringify(back.body.label));
  const e3 = await engines();
  ok(e3.served.chat === 'bedrock' && !e3.overrides.chat,
     'and the ROUTING went back too, not only the label: no override is held',
     JSON.stringify({ served: e3.served, overrides: e3.overrides }) + ' - a restore that ' +
     'clears the label and leaves the routing reads as correct in every log');
  const askHome = await post('/chat', { question: 'One word, sir: ready?',
                                        session: 'groq-proof' });
  const homeRow = (((await engines()).log) || []).filter((r) => r.capability === 'chat')
    .slice(-1)[0] || {};
  ok(askHome.status === 200 && !!askHome.body.answer,
     'and the next question is answered by the house engine with no leftover error');
  ok(homeRow.served !== 'groq' || homeRow.at === chatRow.at,
     'with no new groq row in the ledger after the restore',
     JSON.stringify(homeRow) + ' - the tongue is still borrowed and the chip is lying');

  /* ============== D. THE REFUSAL AND THE FALLBACK LAW =================================== */
  step('D. the blank key, the 429, the timeout and the 401 - groq_sandbox.py');
  const sand = spawnSync(PY, ['groq_sandbox.py', '--port', '4711', '--out', SANDBOX_OUT],
                         { cwd: ROOT, encoding: 'utf8', timeout: 300000 });
  ok(sand.status === 0 && existsSync(SANDBOX_OUT),
     'the sandbox ran: a second server out of the same module, urlopen stubbed for ' +
     'api.groq.com only',
     'exit ' + sand.status + ' ' + String(sand.stderr || '').split(/\r?\n/).slice(-4).join(' | '));
  const S = JSON.parse(readFileSync(SANDBOX_OUT, 'utf8'));
  const C = S.cases || {};

  const nk = C.nokey || {};
  ok(nk.keyPresent === false, 'BLANK KEY: the copy really has no key in it');
  ok(nk.wire === 0,
     'and NOTHING reached the wire: zero requests to api.groq.com under a blank key',
     'the stub saw ' + nk.wire + ' - "one attempt" must not include an attempt spent ' +
     'discovering what config.json already knew');
  ok((nk.calls || {}).chat === 0 && (nk.calls || {}).tts === 0 && (nk.calls || {}).stt === 0,
     'the attempt counters stayed at zero for all three cloud capabilities',
     JSON.stringify(nk.calls));
  ok(nk.chat && nk.chat.namesField === true,
     'the tongue refuses in a plain sentence naming the config field',
     JSON.stringify(nk.chat));
  ok(/groq_api_key/.test((nk.say || {}).error || ''),
     'so does the voice, at 503 rather than with silence',
     JSON.stringify(nk.say));
  ok(/groq_api_key/.test((nk.ear || {}).error || ''),
     'and the ear');
  ok(nk.flip && nk.flip.code === 409 && nk.flip.refused === 'nokey',
     'and the FLAG ITSELF is refused rather than accepted-and-broken',
     JSON.stringify(nk.flip) + ' - a flag that reads "groq" over a house that cannot reach ' +
     'groq is a config file that lies');
  ok(nk.switch && nk.switch.code === 409 && nk.switch.refused === 'nokey',
     'the spoken switch is refused the same way, with the same word');
  ok(Object.values((nk.afterRefusal || {}).overrides || {}).every((v) => !v),
     'and the refused switch left no override behind',
     JSON.stringify(nk.afterRefusal));
  ok((nk.ledger || []).some((r) => r.outcome === 'failed'),
     'the ledger says failed - not fallback, and not nothing at all',
     JSON.stringify(nk.ledger || []).slice(0, 200));

  const okc = C.ok || {};
  ok(okc.chat && okc.chat.answer === 'SANDBOX-GROQ-ANSWER' &&
     okc.vision && okc.vision.answer === 'SANDBOX-GROQ-ANSWER',
     'A KEY THAT WORKS: chat and vision both answer through the one client, by model string',
     JSON.stringify(okc.chat) + ' ' + JSON.stringify(okc.vision));
  ok((okc.say || {}).code === 200 && okc.say.riff === true,
     'the voice answers with RIFF bytes the page can decode');
  ok((okc.ear || {}).served === 'groq' && (okc.ear || {}).fallback === false &&
     !!(okc.ear || {}).text,
     'and the ear answers with a transcript, naming groq as the server of it',
     JSON.stringify(okc.ear));
  ok(JSON.stringify(okc.calls) ===
     JSON.stringify({ chat: 1, vision: 1, stt: 1, tts: 1, refused: 0, fallback: 0 }),
     'ONE REQUEST PER CAPABILITY and not one more: ' + JSON.stringify(okc.calls),
     JSON.stringify(okc.calls) + ' - a retry hidden inside a client is a bill and a latency ' +
     'nobody can see');
  ok(Array.isArray(okc.wire) && okc.wire.length === 4 &&
     okc.wire.filter((u) => /chat\/completions$/.test(u)).length === 2 &&
     okc.wire.some((u) => /audio\/speech$/.test(u)) &&
     okc.wire.some((u) => /audio\/transcriptions$/.test(u)),
     'and the four requests went to the three documented endpoints, chat and vision sharing ' +
     'one of them',
     JSON.stringify(okc.wire));

  const r429 = C['429'] || {};
  ok((r429.chat || {}).fromBedrock === true,
     'THE FALLBACK LAW, 429: the tongue\'s single request goes to bedrock',
     JSON.stringify(r429.chat));
  ok((r429.vision || {}).fromBedrock === true,
     'the eyes to bedrock', JSON.stringify(r429.vision));
  ok((r429.say || {}).code === 200 && r429.say.riff === true && r429.say.bytes > 10000,
     'the voice to Piper - and the boss hears ONE answer, ' + (r429.say || {}).bytes +
     ' bytes of real local audio, never two and never none',
     JSON.stringify(r429.say));
  ok((r429.ear || {}).served === 'browser' && (r429.ear || {}).fallback === true,
     'and the ear declares the browser, which is the one capability whose default lives in ' +
     'the page rather than in this process',
     JSON.stringify(r429.ear));
  ok(JSON.stringify(r429.calls) ===
     JSON.stringify({ chat: 1, vision: 1, stt: 1, tts: 1, refused: 0, fallback: 4 }),
     'EXACTLY ONCE, four times over: one attempt per capability and four fallback rows',
     JSON.stringify(r429.calls) + ' - a fallback that retries first is a fallback that ' +
     'doubles the latency it exists to hide');
  const rows429 = r429.ledger || [];
  ok(['chat', 'vision', 'tts', 'stt'].every((cap) => rows429.some(
       (r) => r.capability === cap && r.outcome === 'fallback' && /429|rate/i.test(r.reason))),
     'and every row names the reason: the ledger is the only record that Groq was down',
     JSON.stringify(rows429).slice(0, 300));

  const rto = C.timeout || {};
  ok((rto.chat || {}).fromBedrock === true && (rto.calls || {}).chat === 1,
     'A TIMEOUT falls back by the same law and by the other door: a road, not a decision',
     JSON.stringify(rto));
  ok((rto.ledger || []).some((r) => /reach|timed out/i.test(r.reason || '')),
     'with the road named in the row', JSON.stringify(rto.ledger));

  const r401 = C['401'] || {};
  ok((r401.chat || {}).fromBedrock === false && (r401.chat || {}).namesConfig === true,
     'A 401 IS A REFUSAL AND NOT A FALLBACK: the boss is told which file to look in',
     JSON.stringify(r401.chat) + ' - falling a wrong key back would leave a broken ' +
     'config.json sounding perfectly fine for a month');
  ok((r401.say || {}).code === 503 && /groq_api_key/.test((r401.say || {}).error || ''),
     'the voice refuses and names the field', JSON.stringify(r401.say));
  ok((r401.ear || {}).code === 503 && (r401.ear || {}).fallback !== true,
     'the ear refuses rather than quietly handing the turn back to the browser',
     JSON.stringify(r401.ear));
  ok((r401.calls || {}).fallback === 0 &&
     (r401.ledger || []).every((r) => r.outcome !== 'fallback'),
     'and not one fallback row was written under a wrong key',
     JSON.stringify(r401.calls));

  const fl = C.flags || {};
  const steps = fl.steps || [];
  ok(steps.length === 5,
     'THE FLAGS ARE INDEPENDENT: four flips, measured one at a time');
  const moved = (i, which) => {
    const before = (steps[i - 1].engines || {}).served || {};
    const after = (steps[i].engines || {}).served || {};
    return Object.keys(after).filter((k) => after[k] !== before[k]);
  };
  for (let i = 1; i < steps.length; i++) {
    const which = steps[i].step.split('=')[0];
    const changed = moved(i, which);
    ok(changed.length === 1 && changed[0] === which,
       'flipping the ' + which + ' changed the ' + which + ' and nothing else',
       'these moved: ' + JSON.stringify(changed) + ' - one flag, one engine, or the boss ' +
       'cannot reason about what he just did');
  }
  ok((fl.refusedWord || {}).code === 400 &&
     /piper|orpheus|web/.test((fl.refusedWord || {}).error || ''),
     'a word no engine answers to is refused with the legal words in the sentence',
     JSON.stringify(fl.refusedWord) + ' - "grok" would otherwise resolve to "not groq" and ' +
     'the boss would be told the flip worked');
  const after = ((fl.afterReset || {}).engines || {});
  ok(JSON.stringify(after.served) === JSON.stringify(after.configured),
     'and after a reset the served engines and the file agree again, field for field: ' +
     JSON.stringify(after.served),
     JSON.stringify(after) + ' - "flipping back is instant and lossless" is exactly this');
  ok(S.keyInPayloads === false,
     'and the sandbox\'s fake key appears in none of the payloads it collected',
     'the key is in a response body - that is the digest-only law broken');
  ok(S.copiesRemoved === true,
     'the temporary config copies were removed on the way out',
     'a copy of his config.json with a fake key in it is still in _runs/');

  /* ============== E. THE ROUND TRIP ==================================================== */
  step('E. Orpheus speaks one line and whisper reads it back');
  const before = await engines();
  const vflip = await flip('voice', 'orpheus');
  flipped = true;
  ok(vflip.status === 200 && vflip.body.engines.served.voice === 'orpheus',
     'the VOICE flips to orpheus and the server says so',
     JSON.stringify(vflip.body).slice(0, 200));
  ok(vflip.body.engines.served.ear === before.served.ear &&
     vflip.body.engines.served.chat === before.served.chat,
     'and only the voice moved');
  ok(vflip.body.engines.models.voice === 'canopylabs/orpheus-v1-english',
     'the model named for the voice is the resolved Orpheus English slug: ' +
     vflip.body.engines.models.voice,
     'a slug that is not in the live catalogue is a 404 dressed as configuration');
  const tts0 = (before.calls || {}).tts || 0;
  const spoke = await postWav('/say', { text: SAID });
  ok(spoke.status === 200 && spoke.riff && spoke.bytes > 20000,
     'ORPHEUS SPEAKS: ' + spoke.bytes + ' bytes of RIFF audio for one sentence',
     'HTTP ' + spoke.status + ' bytes ' + spoke.bytes + ' riff ' + spoke.riff);
  const eT = await engines();
  ok(((eT.calls || {}).tts || 0) === tts0 + 1,
     'one call, one line: the tts counter went up by exactly one',
     tts0 + ' -> ' + (eT.calls || {}).tts);
  const ttsRow = (eT.log || []).filter((r) => r.capability === 'tts').slice(-1)[0] || {};
  ok(ttsRow.served === 'orpheus' && ttsRow.outcome === 'ok',
     'and the ledger names orpheus as the server of it', JSON.stringify(ttsRow));

  /* THE EAR, ON THE VOICE'S OWN OUTPUT. Nothing private is sent: the audio is a sentence this
     harness wrote, spoken by a machine, thirty seconds ago. */
  const earShut = await postAudio('/ear/transcribe', spoke.buf);
  ok(earShut.status === 409 && /ear_stt/.test((earShut.body || {}).error || ''),
     'WHILE THE EAR IS THE BROWSER\'S the cloud ear refuses and names the flag - it does not ' +
     'quietly transcribe anyway',
     'HTTP ' + earShut.status + ' ' + JSON.stringify(earShut.body).slice(0, 200) +
     ' - the ear contract is the browser\'s and this route is an opt-in, not a takeover');
  ok((earShut.body || {}).served === 'browser',
     'and it says who IS serving the ear instead of only who is not');
  await flip('ear', 'groq');
  const stt0 = ((await engines()).calls || {}).stt || 0;
  const heard = await postAudio('/ear/transcribe', spoke.buf);
  ok(heard.status === 200 && (heard.body || {}).served === 'groq',
     'flipped to groq, the same bytes come back as a transcript in ' +
     ((heard.body || {}).tookMs || '?') + 'ms',
     'HTTP ' + heard.status + ' ' + JSON.stringify(heard.body).slice(0, 220));
  const said = String((heard.body || {}).text || '');
  note('whisper heard: ' + JSON.stringify(said));
  ok(/finish window/i.test(said) && /900|nine hundred/i.test(said),
     'THE ROUND TRIP CLOSES: the words Orpheus was given came back through whisper',
     JSON.stringify(said) + ' vs ' + JSON.stringify(SAID) + ' - a 200 with unintelligible ' +
     'audio in it is exactly what a status check cannot see');
  const sttRow = (((await engines()).log) || []).filter((r) => r.capability === 'stt')
    .slice(-1)[0] || {};
  ok(sttRow.served === 'groq' && sttRow.outcome === 'ok',
     'with a ledger row of its own', JSON.stringify(sttRow));
  ok(((await engines()).calls.stt || 0) === stt0 + 1,
     'and one transcription spent, not two');

  /* ============== F. THE PAGE: THE TONGUE, THE SEAL AND THE FULL ROOM ================== */
  step('F. the page - the seal names the voice, and the Quiet Tongue runs first');
  const exe = CHROMES.find((p) => existsSync(p));
  if (!exe) throw new Error('no chrome.exe');
  const profile = mkdtempSync(join(tmpdir(), 'devtools-profile-chrome-groq-'));
  profiles.push(profile);
  procs.push(spawn(exe, ['--headless=new', '--remote-debugging-port=' + PORT,
    '--user-data-dir=' + profile, '--no-first-run', '--no-default-browser-check',
    '--window-size=1378,900', '--use-gl=angle', '--use-angle=default',
    '--enable-unsafe-swiftshader', '--mute-audio', '--autoplay-policy=no-user-gesture-required',
    VIEW], { detached: true, stdio: 'ignore' }));
  for (let i = 0; i < 80; i++) {
    try { await cdp('/json/version'); break; } catch { await sleep(250); }
  }
  let target = null;
  for (let i = 0; i < 40; i++) {
    const l = await cdp('/json/list');
    target = (Array.isArray(l) ? l : []).filter((t) => t.type === 'page')
      .find((t) => /127\.0\.0\.1:4700/.test(t.url));
    if (target) break;
    await sleep(300);
  }
  if (!target) throw new Error('no viewer page');
  const page = new Page(target.webSocketDebuggerUrl);
  await page.open();
  await page.send('Runtime.enable');
  await page.send('Input.enable').catch(() => { });
  ok(await waitFor(page, '!!(window.__galaxy && __galaxy.nodes)', 40000),
     'the viewer is up on an UNMUTED tab, so the voice funnel is live',
     'a mute=1 tab refuses to speak at all, which would make every claim below vacuous');
  /* THE GESTURE, TAKEN EARLY so the line the boot ceremony has been holding since /persona
     drains while the seal checks below run, rather than arriving in the middle of the one
     measurement this section exists to take. The point is asked for in CSS pixels from the
     page itself and checked before anything is dispatched at it: a click that landed on the
     ask bar's ear button would open the microphone, and by the cancel law the microphone
     empties the speech queue - a run that proves nothing while passing. */
  const spot = await page.json('(function(){' +
    'var pick=function(f){var x=Math.round(innerWidth*0.5), y=Math.round(innerHeight*f);' +
    ' var e=document.elementFromPoint(x,y);' +
    ' return {x:x, y:y, hit: e ? (e.id || e.tagName.toLowerCase()) : null,' +
    '  bad: !!(e && e.closest && (e.closest("#bar") || e.closest("#cmd") ||' +
    '          e.closest("#toprail") || e.closest("button")))};};' +
    'var s=pick(0.3); if(s.bad) s=pick(0.2); if(s.bad) s=pick(0.12);' +
    's.view=[innerWidth,innerHeight]; return s;})()');
  ok(spot.bad === false,
     'there is empty canvas at ' + spot.x + ',' + spot.y + ' (over ' +
     JSON.stringify(spot.hit) + ') for the unlocking gesture',
     JSON.stringify(spot) + ' - the gesture must not land on a control');
  await realClick(page, spot.x, spot.y);
  ok(await waitFor(page, '__galaxy.speech.unlocked === true', 8000),
     'ONE REAL CLICK UNLOCKS THE AUDIO, which the autoplay policy requires and no Chrome ' +
     'flag can grant: without it speakLine HOLDS the line instead of speaking it',
     'unlocked is ' + await page.evaluate('String(__galaxy.speech.unlocked)') +
     ' - every chunk count below would read zero on a page that is merely waiting');
  ok(await waitFor(page, '__galaxy.voice.served === "orpheus"', 25000),
     'the page notices the flip on its own health poll: speech.served is orpheus',
     'served is ' + await page.evaluate('String(__galaxy.voice.served)') +
     ' - the page must learn the engine from the server, not be told by a harness');
  ok(await page.evaluate('__galaxy.voice.engine === "piper"'),
     'and the FUNNEL is unchanged by it: the chunks still go out over /say, which is why ' +
     'nothing downstream of the response had to be touched',
     'engine is ' + await page.evaluate('String(__galaxy.voice.engine)'));
  const railVoice = await page.evaluate(
    'String((document.querySelector("#rail-voice .rv")||{}).textContent||"")');
  ok(/orpheus/i.test(railVoice),
     'THE SEAL NAMES THE SERVING VOICE: the rail reads "' + railVoice + '"',
     'the rail says ' + JSON.stringify(railVoice) + ' - a seal that says PIPER while a cloud ' +
     'voice is speaking is the deck lying about where his words went');
  /* AND THE EAR, WHICH HAS NO RAIL CELL - deliberately: the top rail is width-governed and a
     fifth cell would push the deck's own layout around for a flag that is almost always
     "browser". So the ear is named on the Voice Casting seal, which is where the voice is
     named, and read here through a real Ctrl+K rather than by calling the painter. */
  await press(page, 'k', 'KeyK', 75, 2);
  ok(await waitFor(page, '__galaxy.cmd.open === true', 4000),
     'the command sheet opens on a real Ctrl+K, so the seal below is the painted one');
  await sleep(400);
  const seal = await page.json('(__galaxy.cmd.rows.cast || {})');
  ok(/orpheus/i.test(String(seal.line || '')),
     'THE SEAL NAMES THE SERVING VOICE: "' + seal.line + '"',
     JSON.stringify(seal) + ' - the seal is the line he reads before he casts a voice');
  ok(/ear (browser|groq)/i.test(String(seal.line || '')),
     'and it names the SERVING EAR in the same line, which is the only place the ear is ' +
     'named at all',
     JSON.stringify(seal) + ' - §28 says the seal names the serving ear and voice; the ear ' +
     'has no rail cell because the rail is width-governed');
  ok(seal.tone === 'live',
     'and the seal is cyan rather than gold: gold in this deck means nothing left the ' +
     'machine, which is the one claim a cloud voice breaks',
     JSON.stringify(seal));
  await escape(page);
  await waitFor(page, '__galaxy.cmd.open === false', 4000);

  /* THE QUIET TONGUE, ASSERTED WHERE IT RUNS. It is the page's, and it runs on the text's way
     to an engine - so the claim is that the SPOKEN form of a starred line has no asterisks in
     it and the fetch that follows carries that form, with the engine flag making no
     difference to either. */
  const norm = await page.json('__galaxy.voice.normalize(' + JSON.stringify(STARRED) + ')');
  ok(typeof norm === 'string' && !/[*_`#]/.test(norm),
     'the Quiet Tongue takes the marks off: ' + JSON.stringify(norm),
     JSON.stringify(norm) + ' - "asterisk asterisk important" is what a reader hears otherwise');
  /* AND THE HELD LINE IS LET GO OF FIRST. The unlocking click released the boot salutation
     into the same funnel; waiting for the queue to run dry is what keeps the chunk rows and
     the tts arithmetic below about THIS sentence and not about that one. A fresh say() clears
     the log only when the funnel is not already draining, which is the whole reason to wait. */
  await waitFor(page, '__galaxy.voice.draining === false', 60000);
  const ttsB = ((await engines()).calls || {}).tts || 0;
  const took = await page.evaluate('__galaxy.voice.say(' + JSON.stringify(STARRED) + ')', true);
  ok(took === true,
     'the funnel ACCEPTS the line: say() returns true, so it was queued rather than held',
     'say() returned ' + JSON.stringify(took) + ' - false means one of speakLine\'s three ' +
     'gates (MUTED, no engine, not unlocked) turned it into a caption with no sound');
  const spokeIt = await waitFor(page, '__galaxy.voice.chunks.length > 0', 20000);
  const rows = await page.json('__galaxy.voice.chunks.map(function(c){' +
    'return {text: String(c.text||""), spoken: String(c.spoken||"")};})');
  ok(spokeIt && rows.length > 0,
     'the page really spoke it while Orpheus was serving: ' + rows.length + ' chunk(s)',
     'no chunk row appeared, so nothing below is a measurement');
  /* NOT VACUOUSLY. `rows.every` on an empty array is true, so the first version of this
     assertion passed on the run where nothing had been spoken at all - a green line reporting
     that no asterisk reached an engine no text had reached either. The row count and a
     non-null `spoken` are part of the claim. */
  const sung = rows.filter((r) => r.spoken !== null && r.spoken !== '');
  ok(sung.length > 0 && sung.every((r) => !/\*/.test(r.spoken)) &&
     rows.some((r) => /\*/.test(r.text)),
     'and NOT ONE ASTERISK reached the engine, across ' + sung.length + ' spoken chunk(s) ' +
     'whose raw text had them - normalization runs BEFORE the voice, Piper and Orpheus ' +
     'alike, because both are fed from this one funnel',
     JSON.stringify(rows) + ' - a second engine wired in below the normalizer is a boss ' +
     'hearing punctuation read out, and zero spoken rows here is no evidence either way');
  /* POLLED RATHER THAN SLEPT AT. A cloud voice's first chunk is a round trip to Groq, and a
     fixed 1500ms is a bet on somebody else's network - the kind of bet that fails once a
     fortnight and reads like a real regression when it does. */
  let ttsAfter = ttsB;
  for (let i = 0; i < 50 && ttsAfter <= ttsB; i++) {
    await sleep(500);
    ttsAfter = ((await engines()).calls || {}).tts || 0;
  }
  ok(ttsAfter > ttsB,
     'and those chunks really went to Orpheus: the tts counter moved (' + ttsB + ' -> ' +
     ttsAfter + ')',
     'the counter did not move, so the page spoke through something else and the seal is wrong');

  /* ============== G. THE FULL ROOM ===================================================== */
  step('G. Ctrl+A - the full room, the governor, and the guard');
  const box0 = await page.json('({fs: !!document.fullscreenElement, ' +
    'vw: innerWidth, vh: innerHeight, ' +
    'side: (__galaxy.layout.last && __galaxy.layout.last.wellBox || {}).side || 0, ' +
    'tier: (__galaxy.layout.last && __galaxy.layout.last.wellBox || {}).tier || "", ' +
    'runs: __galaxy.fullscreen.measured, changes: __galaxy.fullscreen.changes})');
  ok(box0.fs === false, 'the document does not start in fullscreen');
  note('at rest: ' + JSON.stringify(box0));
  await ctrlA(page);
  const wentFull = await waitFor(page, '!!document.fullscreenElement', 6000);
  const box1 = await page.json('({fs: !!document.fullscreenElement, ' +
    'vw: innerWidth, vh: innerHeight, ' +
    'side: (__galaxy.layout.last && __galaxy.layout.last.wellBox || {}).side || 0, ' +
    'lastVw: (__galaxy.layout.last||{}).vw, lastVh: (__galaxy.layout.last||{}).vh, ' +
    'runs: __galaxy.fullscreen.measured, changes: __galaxy.fullscreen.changes, ' +
    'taken: __galaxy.fullscreen.taken, guarded: __galaxy.fullscreen.guarded})');
  ok(wentFull && box1.fs === true,
     'CTRL+A TAKES THE ROOM: document.fullscreenElement is not null',
     JSON.stringify(box1) + ' - the Fullscreen API needs a user gesture, which is why this ' +
     'is a real keystroke through Chrome and not a call from evaluate()');
  ok(box1.changes > box0.changes,
     'the page learned it from the browser\'s own fullscreenchange, not from its own keypress',
     'changes ' + box0.changes + ' -> ' + box1.changes + ' - state synced from the keystroke ' +
     'would be state that is wrong the moment the browser refuses or Escape is pressed');
  ok(box1.runs > box0.runs,
     'and THE LAYOUT GOVERNOR RE-MEASURED: ' + box0.runs + ' -> ' + box1.runs + ' runs',
     'the governor did not run, so the presence tier, the containment budget and the rails ' +
     'are still sized for the old window');
  ok(box1.lastVw === box1.vw && box1.lastVh === box1.vh,
     'against the NEW dimensions: the governor\'s own record is ' + box1.lastVw + '×' +
     box1.lastVh + ' and the window is ' + box1.vw + '×' + box1.vh,
     JSON.stringify(box1) + ' - a re-measure against the old viewport is worse than none');
  note('the well: ' + box0.side + 'px (' + box0.tier + ') -> ' + box1.side + 'px');
  ok(box1.taken === 1 && box1.guarded === 0,
     'the keystroke was taken once and guarded none, which is the truth table\'s first row',
     JSON.stringify(box1));

  await escape(page);
  const cameBack = await waitFor(page, '!document.fullscreenElement', 6000);
  const box2 = await page.json('({fs: !!document.fullscreenElement, vw: innerWidth, ' +
    'lastVw: (__galaxy.layout.last||{}).vw, runs: __galaxy.fullscreen.measured, ' +
    'changes: __galaxy.fullscreen.changes})');
  ok(cameBack && box2.fs === false,
     'ESCAPE COMES BACK OUT by the browser\'s own law, with no key handler of ours involved',
     JSON.stringify(box2));
  ok(box2.runs > box1.runs && box2.lastVw === box2.vw,
     'and the governor re-measured again, for the window that is there now',
     'runs ' + box1.runs + ' -> ' + box2.runs + ', record ' + box2.lastVw + ' vs ' + box2.vw);

  /* THE GUARD. The ask bar is the summoned type-line, and this is the one keystroke everybody
     uses to retype a question - so it must reach the field untouched. */
  await page.evaluate('__galaxy.typeLine.raise("the harness")', true);
  await sleep(400);
  for (const ch of 'paris') await press(page, ch, 'Key' + ch.toUpperCase(),
                                        ch.toUpperCase().charCodeAt(0), 0, ch);
  const typed = await page.json('({value: String((document.getElementById("qline")||{}).value' +
    '||""), active: String((document.activeElement||{}).id||"")})');
  ok(typed.active === 'qline' && typed.value.length > 0,
     'the ask bar has the caret and the word "' + typed.value + '" in it',
     JSON.stringify(typed) + ' - without this the guard below would be untested');
  const g0 = await page.json('({guarded: __galaxy.fullscreen.guarded, ' +
    'taken: __galaxy.fullscreen.taken, fs: !!document.fullscreenElement})');
  await ctrlA(page);
  await sleep(400);
  const g1 = await page.json('({guarded: __galaxy.fullscreen.guarded, ' +
    'taken: __galaxy.fullscreen.taken, fs: !!document.fullscreenElement, ' +
    'selected: (function(){var e=document.getElementById("qline"); return e ? ' +
    'String(e.value).slice(e.selectionStart, e.selectionEnd) : "";})(), ' +
    'value: String((document.getElementById("qline")||{}).value||"")})');
  ok(g1.fs === false,
     'CTRL+A IN THE ASK BAR LEAVES THE ROOM ALONE: still not fullscreen',
     JSON.stringify(g1) + ' - a deck that eats Ctrl+A in a text field is a deck you cannot ' +
     'retype a question in');
  ok(g1.selected === g1.value && g1.value.length > 0,
     'and it did what it has always meant: the whole of "' + g1.value + '" is selected',
     JSON.stringify(g1) + ' - preventDefault on this keystroke is the bug; passing it through ' +
     'is the feature');
  ok(g1.guarded === g0.guarded + 1 && g1.taken === g0.taken,
     'the guard counted it and the toggle did not: guarded ' + g0.guarded + ' -> ' +
     g1.guarded + ', taken still ' + g1.taken,
     JSON.stringify([g0, g1]));
  await escape(page);

  /* ============== H. THE KEY IS NOWHERE =============================================== */
  step('H. the trace, the ledger and the page - all searched for the key');
  const keyLen = key.length;
  const trace = existsSync(TRACE) ? readFileSync(TRACE, 'utf8') : '';
  ok(trace.length > 0, 'server-trace.log is readable and ' + trace.length + ' bytes long',
     'with no trace there is nothing to clear the server of');
  ok(!/gsk_[A-Za-z0-9]{10}/.test(trace),
     'and NOT ONE Groq key appears in it, across ' + trace.split(/\r?\n/).length + ' lines',
     'a key on stderr is a key in server-trace.log, which is a file in this folder forever');
  const ledgerText = JSON.stringify((await engines()).log || []);
  ok(!/gsk_/.test(ledgerText),
     'the engine ledger carries reasons and outcomes and no credential',
     ledgerText.slice(0, 200));
  /* ASKED FROM INSIDE THE BROWSER, which is the only version of this question that matters:
     everything above was read by Node over the same socket, and the claim being made is about
     what the PAGE can see. */
  const pageText = await page.evaluate(
    'fetch("/health").then(function(r){return r.text();})');
  ok(String(pageText || '').length > 50 && !/gsk_/.test(String(pageText)),
     'and the page, asking /health with its own fetch, is given ' + String(pageText).length +
     ' bytes with no key in them',
     'the browser is holding the key, which is the one place §28 says it may never be');
  ok(keyLen > 20, 'the only two things said about it anywhere: ' + keyLen + ' characters and ' +
     'sha256 ' + key.sha256);

  page.close();
}

main().catch((e) => {
  bad.push('the run itself: ' + e.message);
  console.log('\n  ERROR ' + (e && e.stack || e));
}).finally(async () => {
  /* THE FOUR FLAGS GO BACK, AND IT IS A CHECK. A harness that leaves his voice on a cloud
     engine has reconfigured his house from a test - and because the overrides live in memory,
     the only thing that would ever put it right is a restart nobody knows is needed. */
  if (flipped) {
    const r = await resetEngines().catch(() => ({ status: 0, body: {} }));
    const e = (r.body || {}).engines || {};
    const back = JSON.stringify(e.served) === JSON.stringify(e.configured);
    ok(r.status === 200 && back,
       'every engine is back where config.json wants it: ' + JSON.stringify(e.served),
       JSON.stringify(e) + ' - the flags are held in memory, so this is the only thing that ' +
       'puts them back short of a restart');
    const DEF = { chat: 'bedrock', ear: 'browser', vision: 'bedrock', voice: 'piper' };
    ok(JSON.stringify(e.served) === JSON.stringify(DEF),
       'and those are the four defaults §28 requires after every run: ' + JSON.stringify(DEF),
       JSON.stringify(e.served));
  }
  procs.forEach((p) => { try { process.kill(p.pid); } catch { } });
  await sleep(700);
  profiles.forEach((p) => { try { rmSync(p, { recursive: true, force: true }); } catch { } });
  console.log('\n  VERIFY ' + (checks - bad.length) + '/' + checks +
              (bad.length ? ' FAIL' : ' PASS') + '\n');
  bad.forEach((b) => console.log('    FAILED: ' + b));
  process.exit(bad.length ? 1 : 0);
});
