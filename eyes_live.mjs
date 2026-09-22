/* The eyes, driven end to end in a real browser with a real camera open.
 *
 *   press the EYE button  ->  hear "Eyes open, sir" AND the ear law, because the
 *   microphone is off  ->  sit neutrally until the organ has measured YOUR posture
 *   ->  pick up the phone  ->  be nudged inside a second  ->  stay bent and hear
 *   nothing for the thirty second cooldown  ->  slouch, and watch the boolean
 *   change with no word said  ->  leave the desk for three seconds and still be
 *   counted present  ->  ask "what do you think of my shirt?" and have exactly one
 *   frame leave  ->  start a session, pick the phone up again, and watch the drift
 *   land on the same books a tab drift lands on  ->  say "no Jarvis, I need to do
 *   something important" and prove the silence  ->  close the eyes
 *
 * Two things make this a real run rather than a demonstration:
 *
 *   THE CAMERA IS REAL. Chrome is launched with --use-fake-device-for-media-stream,
 *   so getUserMedia goes all the way through the browser's capture stack and the page
 *   holds a live MediaStream with a live track. What the fake device does NOT contain
 *   is a person, so the LANDMARKS are recorded ones, handed to the page through
 *   __galaxy.eyes.feed() - the one seam the camera itself feeds through. Everything
 *   downstream of that call is the code the camera drives: the baseline, the sustain,
 *   the report, the cooldown, the nudge.
 *
 *   AND THE LANDMARK CDN IS BLOCKED, on purpose, with Network.setBlockedURLs. A fake
 *   camera contains no face, so a working detector would answer "nobody there" seven
 *   times a second and reset the sustain window between every recorded posture. Taking
 *   the detectors away leaves the recorded landmarks as the only readings in the room -
 *   and it doubles as the honest-failure check, because a page that cannot load a
 *   landmarker has to SAY it cannot see rather than report a cheerful "upright".
 *
 * The tab is loaded with ?mute=1, which is the law for every tab used for testing, so
 * this run is silent. Nothing is stubbed to make it silent: speak() records every line
 * for six seconds in __galaxy.speech.said with a flag for whether it reached the
 * speakers, and that log is what every claim about a spoken line reads. Silence is
 * therefore checkable too, which is most of this file: three of the checks here are
 * about a sentence NOT being said.
 *
 * What is measured, and where the number comes from:
 *   - THE NUDGE LATENCY is wall time from the first head-down reading entering the page
 *     to the line appearing in the page's own record of what was spoken. It crosses the
 *     700 ms sustain in the page and a POST /eyes to the server, and the promise is that
 *     it lands inside a second.
 *   - the pools are read from focus.py itself through a short python, so "that line came
 *     from the phone pool" is a fact about the file rather than a regex I wrote twice.
 *
 * Usage:  node eyes_live.mjs        (with server.py already running on 4700)
 */

import { spawn, spawnSync } from 'node:child_process';
import { mkdtempSync, rmSync, existsSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const GALAXY = 'http://127.0.0.1:4700/';
const VIEWER = GALAXY + '?mute=1';            // the ear law's other half, in a URL
const CDP = 'http://127.0.0.1:9222';
const NUDGE_DEADLINE_MS = 1000;               // "inside a second", in one number
const SUSTAIN_MS = 700;                       // EYE_SUSTAIN_MS, for the log line
const COOLDOWN_S = 30;                        // EYE_COOLDOWN_S
const RELIEF_S = 180;                         // RELIEF_S
const ARM_WAIT_MS = 62000;                    // DEFER_APP_ONLY_S is 45; allow for ticks

/* The landmarkers and their models. Blocked, for the reason in the header. */
const BLOCKED = ['*tasks-vision*', '*mediapipe*', '*storage.googleapis.com/mediapipe*'];

const CHROMES = [
  'C:/Program Files/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Google/Chrome/Application/chrome.exe',
  process.env.LOCALAPPDATA + '/Google/Chrome/Application/chrome.exe',
];
/* This machine's real interpreter. A bare `python` here is the Store stub. */
const PYTHON = 'C:/Users/Fullstack Developer/AppData/Local/Programs/' +
               'Python/Python313/python.exe';

const t0 = Date.now();
const failures = [];
let checks = 0;

const at = () => ((Date.now() - t0) / 1000).toFixed(2).padStart(6) + 's';
const log = (m) => console.log('  ' + at() + '  ' + m);

function ok(cond, claim, detail) {
  checks++;
  console.log('  ' + at() + (cond ? '  ok   ' : '  FAIL ') + claim);
  if (!cond) {
    failures.push(claim);
    if (detail) console.log('            ' + detail);
  }
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const NET_TIMEOUT_MS = 10000;

async function cdp(path, method = 'GET') {
  const res = await fetch(CDP + path,
                          { method, signal: AbortSignal.timeout(NET_TIMEOUT_MS) });
  const text = await res.text();
  try { return JSON.parse(text); } catch { return text; }
}

async function galaxy(path, body) {
  const res = await fetch(GALAXY.replace(/\/$/, '') + path, body ? {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal: AbortSignal.timeout(NET_TIMEOUT_MS),
  } : { signal: AbortSignal.timeout(NET_TIMEOUT_MS) });
  return res.json();
}

/* ---- the line pools, read from focus.py rather than copied out of it ----
   A claim like "that sentence came from the phone pool" is only worth making against
   the pool the server actually draws from, and the templates carry {fields}, so the
   comparison is a regex built from the file at the moment of asking. */
function python(script, payload) {
  const r = spawnSync(PYTHON, ['-c', script],
                      { input: JSON.stringify(payload === undefined ? null : payload),
                        encoding: 'utf8', timeout: 20000 });
  if (r.error) throw new Error('python: ' + r.error.message);
  if (r.status !== 0) throw new Error('python exited ' + r.status + ': ' + (r.stderr || ''));
  return JSON.parse(r.stdout.trim() || 'null');
}

const PY_POOL = [
  'import sys, json, re, focus',
  'req = json.load(sys.stdin)',
  'pool = eval(req["pool"])',                      // e.g. focus.CALLOUTS_PHONE[1]
  'def rx(t):',
  '    body = re.sub(r"\\\\\\{[a-z_]+\\\\\\}", ".+", re.escape(t))',
  '    return re.compile("^" + body + "$")',
  'pats = [rx(t) for t in pool]',
  'hit = [l for l in req["lines"] if any(p.match(l) for p in pats)]',
  'print(json.dumps(hit))',
].join('\n');

/* Which of these spoken lines came out of that pool of templates. */
const fromPool = (lines, pool) => python(PY_POOL, { lines: lines, pool: pool });
/* Every pool the eyes may ever draw from, flattened - for the silence checks. */
const EVERY_EYE_LINE = '[t for pool in focus.EYE_POOLS for t in pool]';
const PHONE_TIER1 = 'focus.CALLOUTS_PHONE[1]';
/* Every phone line at every tier, plus the drill's. The in-session check uses this one
   rather than tier 1: the tier is a function of how many times you have drifted today,
   and what is being proved there is that a head going down draws on the PHONE pool and
   not on the slouch or absence ones. */
const PHONE_ANY = ('[t for pool in focus.CALLOUTS_PHONE.values() for t in pool]'
                   + ' + list(focus.CALLOUTS_PHONE_DRILL)');

const PY_LINES = [
  'import sys, json, focus',
  'json.load(sys.stdin)',
  'print(json.dumps({"eyes_on": focus.LINES["eyes_on"],',
  '                  "ears_off": focus.LINES["ears_off"],',
  '                  "eyes_off": focus.LINES["eyes_off"],',
  '                  "tuning": focus.EYES.tuning()}))',
].join('\n');

/* ---- the smallest CDP client that can evaluate an expression in a page ---- */
class Page {
  constructor(wsUrl) { this.wsUrl = wsUrl; this.id = 0; this.waiting = new Map(); }

  open() {
    return new Promise((resolve, reject) => {
      this.ws = new WebSocket(this.wsUrl);
      this.ws.onopen = () => resolve(this);
      this.ws.onerror = (e) => reject(new Error('CDP socket: ' + (e.message || 'failed')));
      this.ws.onmessage = (ev) => {
        const msg = JSON.parse(ev.data);
        const w = this.waiting.get(msg.id);
        if (w) { this.waiting.delete(msg.id); w(msg); }
      };
    });
  }

  send(method, params) {
    const id = ++this.id;
    return new Promise((resolve, reject) => {
      const bomb = setTimeout(() => {
        this.waiting.delete(id);
        reject(new Error(method + ' got no answer in ' + NET_TIMEOUT_MS + 'ms'));
      }, NET_TIMEOUT_MS);
      this.waiting.set(id, (msg) => { clearTimeout(bomb); resolve(msg); });
      this.ws.send(JSON.stringify({ id, method, params: params || {} }));
    });
  }

  async evaluate(expression) {
    const r = await this.send('Runtime.evaluate', {
      expression, returnByValue: true, awaitPromise: false,
    });
    if (r.error) throw new Error(r.error.message);
    if (r.result && r.result.exceptionDetails) {
      throw new Error('page threw: ' + r.result.exceptionDetails.text);
    }
    const res = r.result && r.result.result;
    return res ? res.value : undefined;
  }

  close() { try { this.ws.close(); } catch { /* already gone */ } }
}

/* ============================================================== the run ==== */

const profile = mkdtempSync(join(tmpdir(), 'eyes-live-'));
let chrome = null;

async function main() {
  console.log('\n  the eyes · the live loop\n');

  const said = python(PY_LINES);
  const health = await galaxy('/health');
  log('server: ' + health.notes + ' notes · brain ' + health.brain.label);

  // A run needs a known slate: the cooldown, the nudge count and the drift count are
  // all read as numbers here, and a session already in flight owns some of them.
  const before = (await galaxy('/focus')).focus;
  if (before && !['idle', 'ended'].includes(before.state)) {
    log('a session was already running (' + before.state + ') - ending it, because ' +
        'this run reads its counters');
    await galaxy('/focus', { cmd: 'abort' });
    await sleep(1200);
  }

  /* AND THE RELIEF VALVE MAY STILL BE OPEN from a previous run of this very file: phase
     10 asks for three minutes of silence and then proves it, and three minutes of
     silence is exactly what it gets - the hush belongs to the organ, so it outlives the
     session, the tab and this process. There is no way to cancel it that is not a hole
     in the feature, so a re-run inside that window waits it out rather than reaching in.
     Sitting through it is the honest cost of having asked for it. */
  let hush = (await galaxy('/focus')).focus;
  if (hush && hush.hushed) {
    log('the relief valve is still open from an earlier run - ' + hush.hushLeftS +
        's of silence left, and nothing may cancel it, so this run waits');
    for (let i = 0; i < 200 && hush.hushed; i++) {
      await sleep(2000);
      hush = (await galaxy('/focus')).focus;
    }
    log('the silence expired on its own - the eyes have their voice back');
  }

  const exe = CHROMES.find((p) => existsSync(p));
  if (!exe) throw new Error('no chrome.exe found in the usual places');

  // 1. A real, headed Chrome with a real - if fictional - camera. Headed is not
  //    optional: the session's reader asks the window manager what is in front, and a
  //    headless browser has no window to be in front of anything.
  chrome = spawn(exe, [
    '--remote-debugging-port=9222',
    '--user-data-dir=' + profile,
    '--no-first-run', '--no-default-browser-check',
    // The camera. The first flag makes one exist; the second answers the permission
    // prompt, because a prompt nobody can click is a run that hangs.
    '--use-fake-device-for-media-stream',
    '--use-fake-ui-for-media-stream',
    '--autoplay-policy=no-user-gesture-required',
    '--new-window', VIEWER,
  ], { detached: true, stdio: 'ignore' });

  for (let i = 0; i < 60; i++) {
    try { await cdp('/json/version'); break; } catch { await sleep(250); }
  }
  const version = await cdp('/json/version');
  log('chrome: ' + version.Browser);
  await sleep(3500);                    // the viewer's 3D boot

  const target = (await cdp('/json/list'))
    .filter((t) => t.type === 'page').find((t) => t.url.includes('127.0.0.1:4700'));
  if (!target) throw new Error('the viewer tab never appeared');
  const page = new Page(target.webSocketDebuggerUrl);
  await page.open();
  await page.send('Runtime.enable');
  await page.send('Network.enable');
  // See the header: with no face in the fake camera, a working detector would out-vote
  // every recorded posture with "nobody there" seven times a second.
  await page.send('Network.setBlockedURLs', { urls: BLOCKED });
  await cdp('/json/activate/' + target.id);
  await sleep(600);

  ok(await page.evaluate('!!window.__galaxy && !!window.__galaxy.eyes'),
     'the viewer exposes the eyes handle');
  ok(await page.evaluate('__galaxy.speech.muted') === true,
     'the tab was loaded with ?mute=1, so this run is silent and still checkable',
     'url=' + target.url);
  ok(await page.evaluate('__galaxy.eyes.supported') === true,
     'this browser will give the page a camera');
  ok(await page.evaluate('__galaxy.speech.listening') === false,
     'the microphone is OFF at the start, which is what the ear law is about');

  /* ---- the helpers ----------------------------------------------------- */

  /* Marked by TIME, never by index: the said log is a rolling six seconds, so an index
     into it means something different a moment later. */
  const mark = () => Date.now();
  const saidAfter = async (since) => JSON.parse(await page.evaluate(
    'JSON.stringify(__galaxy.speech.said.filter(function (s) { return s.at > ' +
    since + '; }))') || '[]');
  async function waitSaid(since, ms) {
    const until = Date.now() + ms;
    for (;;) {
      const lines = await saidAfter(since);
      if (lines.length) return lines[0];
      if (Date.now() >= until) return null;
      await sleep(60);
    }
  }
  const serverEyes = async () => (await galaxy('/focus')).focus;
  const eyeState = async (what) => JSON.parse(
    await page.evaluate('JSON.stringify(__galaxy.eyes.' + what + ')') || 'null');
  const press = async (id) => {
    const box = JSON.parse(await page.evaluate(
      '(function () { var r = document.getElementById(' + JSON.stringify(id) +
      ').getBoundingClientRect(); return JSON.stringify(' +
      '{x: Math.round(r.left + r.width/2), y: Math.round(r.top + r.height/2)}); })()'));
    for (const type of ['mousePressed', 'mouseReleased']) {
      await page.send('Input.dispatchMouseEvent',
        { type, x: box.x, y: box.y, button: 'left', clickCount: 1 });
    }
  };

  /* THE RECORDED POSTURES, and the only test-shaped thing in the run. Four numbers per
     posture in the normalised space MediaPipe reports, arranged into the six landmarks
     the geometry reads. They are ratios of each other, so they say "head tipped down"
     rather than "a head 41 cm from a 1080p lens". */
  await page.evaluate(`
    (function () {
      var P = {
        /* forehead, eye line, chin, nose, shoulder line - y grows downward */
        neutral: { fore: 0.20, eye: 0.32, chin: 0.55, nose: 0.30, shoulder: 0.62 },
        /* the phone: chin foreshortened and the nose fallen toward the shoulders */
        phone:   { fore: 0.24, eye: 0.40, chin: 0.58, nose: 0.50, shoulder: 0.62 },
        /* the slouch: sunk in the chair, head NOT bent - a different sentence */
        slouch:  { fore: 0.24, eye: 0.39, chin: 0.62, nose: 0.36, shoulder: 0.62 }
      };
      function feed(name) {
        if (name === 'away') return __galaxy.eyes.feed(null, null);
        var s = P[name];
        var f = new Array(264).fill(null);
        f[10]  = { x: 0.50, y: s.fore };     f[152] = { x: 0.50, y: s.chin };
        f[33]  = { x: 0.42, y: s.eye };      f[263] = { x: 0.58, y: s.eye };
        var p = new Array(13).fill(null);
        p[0]   = { x: 0.50, y: s.nose };
        p[11]  = { x: 0.34, y: s.shoulder }; p[12] = { x: 0.66, y: s.shoulder };
        return __galaxy.eyes.feed(f, p);
      }
      window.__body = feed;
      /* HELD, at the cadence a camera reads at, because a posture is a thing that
         lasts and the sustain window only means anything against a stream. */
      window.__hold = function (name) {
        clearInterval(window.__holdT);
        /* The page's own clock on the first reading of a new posture, so a latency can
           be quoted from the moment the posture entered the page rather than from the
           moment this harness asked it to. */
        window.__holdAt = Date.now();
        window.__holdT = setInterval(function () { feed(name); }, 120);
        return feed(name);
      };
      window.__release = function () { clearInterval(window.__holdT); };
      return 'ready';
    })()`);

  /* ---- 2. the eyes open, and the ear law is SAID ----------------------- */
  const onMark = mark();
  await press('eye');
  const onLine = await waitSaid(onMark, 6000);
  ok(await page.evaluate('__galaxy.eyes.on') === true,
     'the EYE button opened a real camera',
     'trouble=' + await page.evaluate('__galaxy.eyes.trouble'));
  ok(await page.evaluate('__galaxy.eyes.indicator') === true,
     'and the violet chip says so, so no camera is ever open unannounced');
  ok(!!onLine && onLine.text === said.eyes_on + ' ' + said.ears_off,
     'THE EAR LAW: the eyes came on with the mic off, and the assistant says so',
     'said: ' + JSON.stringify(onLine && onLine.text));
  ok(!!onLine && onLine.aloud === false,
     'and in a ?mute=1 tab that line was recorded rather than heard');
  let st = await serverEyes();
  ok(st.eyesOn === true && st.present === true,
     'the server knows the eyes are open and nobody has left yet',
     JSON.stringify({ eyesOn: st.eyesOn, present: st.present }));
  const tune = await eyeState('tuning');
  ok(JSON.stringify(tune) === JSON.stringify(said.tuning),
     'the page applies the server\'s own windows, handed back with the report',
     JSON.stringify(tune) + ' vs ' + JSON.stringify(said.tuning));

  // The landmarkers cannot load - see the header - and the page has to say so rather
  // than report a posture it did not read.
  let trouble = '';
  for (let i = 0; i < 40 && !trouble; i++) {
    trouble = await page.evaluate('__galaxy.eyes.trouble');
    if (!trouble) await sleep(250);
  }
  ok(/cannot read this camera/.test(trouble),
     'with the landmarkers unreachable the organ says it cannot see',
     'trouble=' + JSON.stringify(trouble));
  ok(await eyeState('base') === null,
     'and it has claimed no posture: no baseline, so nothing to compare anything to');

  /* ---- 3. YOUR neutral, measured through the camera's own seam --------- */
  await page.evaluate('void __hold("neutral")');
  let base = null;
  for (let i = 0; i < 60 && !base; i++) { await sleep(120); base = await eyeState('base'); }
  ok(!!base && typeof base.pitch === 'number' && typeof base.drop === 'number',
     'eight neutral readings later the organ has measured YOUR posture, not a constant',
     JSON.stringify(base));
  await sleep(600);
  st = await serverEyes();
  ok(st.present === true && st.headDown === false && st.slouched === false,
     'sitting normally publishes present, upright, unslouched',
     JSON.stringify({ present: st.present, headDown: st.headDown,
                      slouched: st.slouched }));
  const post = await eyeState('lastPost');
  const sent = Object.keys((post && post.sent) || {}).sort().join(',');
  ok(sent === 'cmd,ears,headDown,present,slouched',
     'THE WHOLE PAYLOAD: a command, three booleans and a word about the ears',
     'sent keys: ' + sent);
  /* nudges is a LIFETIME count, kept by the organ rather than by a session, so every
     claim about it below is a delta from here. A run that asserted zero would be
     asserting that the server had only just started, which is a fact about the server
     and not about the eyes. */
  const nudges0 = st.nudges;
  ok(st.hushed === false, 'and nothing has been said about any of it yet',
     JSON.stringify({ nudgesSoFarThisServer: nudges0, hushed: st.hushed }));

  /* ---- 4. THE PHONE: nudged inside a second --------------------------- */
  const phoneMark = mark();
  const started = Date.now();
  await page.evaluate('void __hold("phone")');
  const nudge = await waitSaid(phoneMark, 4000);
  const latency = nudge ? nudge.at - started : -1;
  log('NUDGE: ' + JSON.stringify(nudge && nudge.text) + '  (+' + latency + 'ms, of ' +
      'which ' + SUSTAIN_MS + 'ms is the sustain the posture had to hold)');
  ok(!!nudge, 'picking up the phone earns a word');
  ok(latency >= SUSTAIN_MS && latency <= NUDGE_DEADLINE_MS,
     'and it arrives inside a second of the posture starting - never before the sustain',
     'latency=' + latency + 'ms');
  ok(!!nudge && fromPool([nudge.text], PHONE_TIER1).length === 1,
     'the line came from the phone pool in focus.py, not from a general scolding',
     'said: ' + JSON.stringify(nudge && nudge.text));
  ok(!!nudge && !/[{}]/.test(nudge.text) && nudge.text.length < 90,
     'it is one dry sentence with no unfilled field in it');
  const nudgePost = await eyeState('lastPost');
  ok(!!nudgePost && nudgePost.spoke === true && nudgePost.via === false,
     'ONE NUDGER: with no session the line came back in the reply, for this tab to say',
     JSON.stringify(nudgePost));
  st = await serverEyes();
  ok(st.headDown === true && st.nudges === nudges0 + 1,
     'the posture is published as a boolean and exactly one nudge has been spent',
     JSON.stringify({ headDown: st.headDown, nudges: st.nudges, was: nudges0 }));
  /* WHEN the voice was spent, because the cooldown that follows is global: it is the
     organ's, not a session's, and the in-session drift in phase 9 is gated by the very
     same thirty seconds. The page said this line AFTER the server spent the cooldown,
     so counting from here is the conservative end. */
  const spentAt = nudge ? nudge.at : Date.now();

  /* ---- 5. THE COOLDOWN: still bent, and quiet ------------------------- */
  await page.evaluate('void __hold("neutral")');
  await sleep(1400);
  const coolMark = mark();
  await page.evaluate('void __hold("phone")');
  await sleep(2600);
  let heard = await saidAfter(coolMark);
  ok(fromPool(heard.map((s) => s.text), EVERY_EYE_LINE).length === 0,
     'a second bend inside the ' + COOLDOWN_S + 's cooldown earns silence, not a second nudge',
     'heard: ' + JSON.stringify(heard.map((s) => s.text)));
  st = await serverEyes();
  ok(st.headDown === true && st.nudges === nudges0 + 1,
     'and it is still watching: the boolean is true, the voice is simply spent',
     JSON.stringify({ headDown: st.headDown, nudges: st.nudges, was: nudges0 }));

  /* ---- 6. THE SLOUCH: its own boolean, its own pool ------------------- */
  const slouchMark = mark();
  await page.evaluate('void __hold("slouch")');
  await sleep(1500);
  st = await serverEyes();
  ok(st.slouched === true && st.headDown === false,
     'sinking in the chair is published as a slouch, and never at the same time as the phone',
     JSON.stringify({ slouched: st.slouched, headDown: st.headDown }));
  heard = await saidAfter(slouchMark);
  ok(fromPool(heard.map((s) => s.text), EVERY_EYE_LINE).length === 0,
     'one cooldown covers every posture, so the slouch waits its turn in silence');

  /* ---- 7. ABSENCE gets the longer grace ------------------------------- */
  await page.evaluate('void __hold("away")');
  await sleep(3400);
  st = await serverEyes();
  const stable = await eyeState('stable');
  ok(st.present === true && stable.present === true,
     'three seconds of empty chair is still present: glancing at a notification is not leaving',
     JSON.stringify({ server: st.present, page: stable.present,
                      graceMs: tune.absenceMs }));
  await page.evaluate('void __hold("neutral")');
  await sleep(900);

  /* ---- 8. LOOK AT ME: one frame, and only when asked ------------------ */
  ok(await page.evaluate('__galaxy.eyes.isLook("look at me")') === true &&
     await page.evaluate('__galaxy.eyes.isLook("what do you think of my shirt?")') === true,
     'the look phrases route to the eyes');
  ok(await page.evaluate('__galaxy.eyes.isLook("what do you think of this screen")') === false &&
     await page.evaluate('__galaxy.sight.isScreenish("what do you think of this screen")') === true,
     'and "this screen" still belongs to the screen organ, which is the whole trap here');
  ok(await page.evaluate('__galaxy.sight.isScreenish("look at me")') === false,
     'the two routes are disjoint in the live page, not just in the regexes');

  if (health.keyConfigured) {
    await page.evaluate('void __galaxy.ask("what do you think of my shirt?")');
    let look = null;
    for (let i = 0; i < 80 && !(look && look.brain); i++) {
      await sleep(500); look = await eyeState('lastLook');
    }
    log('LOOK: ' + JSON.stringify(look));
    ok(!!look && look.bytes > 0 && look.type === 'image/jpeg',
       'exactly one frame of the camera left this machine, as a JPEG',
       JSON.stringify(look));
    ok(!!look && look.ageMs < 3000,
       'and it was grabbed for this question, not remembered from an older one',
       'ageMs=' + (look && look.ageMs));
    ok(await page.evaluate('__galaxy.eyes.looks') === 1,
       'one question, one look');
    ok(await page.evaluate('__galaxy.eyes.proofShown') === true,
       'the frame that was sent is shown back, so the upload is never invisible');
    const answer = await page.evaluate(
      'document.getElementById("a-text") ? document.getElementById("a-text").textContent : ""');
    log('answered: ' + JSON.stringify(String(answer).slice(0, 160)));
    /* A brain NAME is the only proof that a brain answered: an error renders into the
       same card, so "there is text in it" would pass on "No such endpoint". */
    ok(!!(look && look.brain) && String(answer).trim().length > 0 &&
       !/Having a look/.test(answer),
       'and a brain answered the question that was asked, in one to three sentences',
       'brain=' + (look && look.brain) + ' asAsked=' + (look && look.asAsked) +
       ' answer=' + JSON.stringify(String(answer).slice(0, 120)));
    ok(String(answer).split(/(?<=[.!?])\s+/).filter((s) => s.trim()).length <= 3,
       'and it is one to three sentences, not an essay about a webcam frame');
    ok(await page.evaluate('__galaxy.eyes.on') === true,
       'the eyes are still open, and were never opened BY a phrase');
  } else {
    log('no key configured - the one-frame look is not exercised');
  }

  /* ---- 9. A SESSION: a phone drift is counted like a tab drift -------- */
  await page.evaluate('void __hold("neutral")');
  // The lock is about to be made out of whatever window is in front, so put the
  // browser there on purpose rather than hoping it stayed.
  await cdp('/json/activate/' + target.id);
  await sleep(500);
  await galaxy('/focus', { cmd: 'start', minutes: 10 });
  log('session started · waiting out the deferred lock (never leaves home base, so ' +
      'it settles on the application)');
  let fx = null;
  for (let i = 0; i < ARM_WAIT_MS / 1000; i++) {
    await sleep(1000);
    fx = await serverEyes();
    if (fx.state === 'running') break;
  }
  ok(fx && fx.state === 'running',
     'the session is watching something, so a drift can be counted against it',
     JSON.stringify(fx && { state: fx.state, locked: fx.locked,
                            tabWatched: fx.tabWatched }));
  ok(fx && fx.eyesOn === true,
     'and the eyes are still reporting into it',
     JSON.stringify(fx && { drifts: fx.drifts, eyesOn: fx.eyesOn }));
  ok(fx && fx.hushed === false,
     'and no relief valve is open, so a silence below would mean something',
     'hushed=' + (fx && fx.hushed) + ' nudges=' + (fx && fx.nudges));

  /* THE COOLDOWN IS THE ORGAN'S, NOT THE SESSION'S, and that is worth waiting out
     rather than hoping about. The nudge in phase 4 bought thirty seconds of quiet from
     the eyes themselves; a session starting inside that window is still covered by it,
     so a drift measured here would be silent for an entirely correct reason and this
     harness would call it a bug. An earlier run did exactly that - the deferred lock
     happened to settle twelve seconds sooner and three checks failed on a silence the
     design promises. So: wait for the voice to come back, and say how long. */
  const coolLeft = COOLDOWN_S * 1000 + 800 - (Date.now() - spentAt);
  if (coolLeft > 0) {
    log('waiting out the ' + COOLDOWN_S + 's cooldown the phone nudge bought (' +
        (coolLeft / 1000).toFixed(1) + 's left) - the eyes\' quiet covers a session too');
    await sleep(coolLeft);
  }
  ok(Date.now() - spentAt >= COOLDOWN_S * 1000,
     'the voice the phone nudge spent has had its full ' + COOLDOWN_S + ' seconds back',
     'since the nudge: ' + ((Date.now() - spentAt) / 1000).toFixed(1) + 's');

  /* AND THE SESSION HAS TO BE SETTLED BEFORE A POSTURE CAN BE A DRIFT, because
     _off_target() continues an excursion it is already in rather than starting a
     second one inside the first. If the window manager has this run's Chrome behind
     something else - a terminal, an editor, whatever launched this file - the session
     is already off target for an ordinary reason, and a head going down then is a
     posture inside an app drift, correctly counted once and correctly silent. That is
     the design, not a fault, so the harness puts the browser back in front and waits
     for the session to say it is watching again before it measures anything. */
  let settled = null;
  for (let i = 0; i < 30; i++) {
    settled = await serverEyes();
    if (!settled.drifting && !settled.inGrace) break;
    if (i % 5 === 0) await cdp('/json/activate/' + target.id);
    await sleep(1000);
  }
  ok(!!settled && !settled.drifting && !settled.inGrace,
     'the session is settled and watching, so the next drift will be the posture one',
     JSON.stringify(settled && { drifting: settled.drifting, inGrace: settled.inGrace,
                                 onTarget: settled.onTarget, atHome: settled.atHome,
                                 drifts: settled.drifts }));
  /* drifts is a DELTA from here for the same reason nudges was: a window that stole
     focus during the cooldown above may have earned the session an honest drift, and
     asserting zero would be asserting something about this machine's desktop. */
  const drifts0 = settled ? settled.drifts : 0;

  // The lock announces itself out loud when it lands; let that line be said before
  // marking, so the sentence measured below is the one about the posture.
  await sleep(1500);
  const driftMark = mark();
  const driftStart = Date.now();
  await page.evaluate('void __hold("phone")');
  const driftLine = await waitSaid(driftMark, 4000);
  const drifted = await eyeState('lastPost');
  const heldAt = await page.evaluate('window.__holdAt');
  /* Three numbers, because "1.4 seconds" on its own says nothing about which half of
     the pipeline spent it: the posture entered the page, the page posted it once the
     sustain was served, and the line was spoken. */
  log('DRIFT: ' + JSON.stringify(driftLine && driftLine.text) + '  (+' +
      (driftLine ? driftLine.at - driftStart : -1) + 'ms from the ask, +' +
      (driftLine ? driftLine.at - heldAt : -1) + 'ms from the first reading, posted at +' +
      (drifted ? drifted.at - heldAt : -1) + 'ms)');
  ok(!!driftLine && fromPool([driftLine.text], PHONE_ANY).length === 1,
     'inside a session the phone still speaks from its own pool',
     'said: ' + JSON.stringify(driftLine && driftLine.text));
  /* A wider deadline than the reply path, and honestly so: the line leaves the server
     in the say queue and comes back in the reply to the very post that queued it, so
     it costs the same round trip plus one reading of slack - the page notices the
     sustain has been served on a reading, not on a timer. */
  const driftLatency = driftLine ? driftLine.at - heldAt : -1;
  ok(driftLatency >= SUSTAIN_MS && driftLatency <= NUDGE_DEADLINE_MS + 500,
     'and it is still a word within about a second of the phone coming up',
     'latency=' + driftLatency + 'ms');
  ok(!!drifted && drifted.via === true && drifted.spoke === false,
     'and it travels in the say queue now, so every open tab says it exactly once',
     JSON.stringify(drifted));
  fx = await serverEyes();
  ok(fx.drifts === drifts0 + 1 && fx.postureDrift === true,
     'a phone drift is counted like a tab drift, on the same books',
     JSON.stringify({ drifts: fx.drifts, was: drifts0,
                      postureDrift: fx.postureDrift,
                      driftS: fx.driftS, tier: fx.tier }));

  /* ---- 10. THE RELIEF VALVE ------------------------------------------- */
  await page.evaluate('void __hold("neutral")');
  await sleep(1200);
  const reliefMark = mark();
  // Said out loud, through the door a dictated sentence comes in by.
  await page.evaluate('void __galaxy.ask("no Jarvis, I need to do something important")');
  const reliefLine = await waitSaid(reliefMark, 6000);
  log('RELIEF: ' + JSON.stringify(reliefLine && reliefLine.text));
  ok(!!reliefLine && /of silence, sir/i.test(reliefLine.text),
     'the relief line is understood and answered with the bargain it is',
     'said: ' + JSON.stringify(reliefLine && reliefLine.text));
  fx = await serverEyes();
  ok(fx.hushed === true && fx.hushLeftS >= RELIEF_S - 10 && fx.snoozed === true,
     'three minutes of silence, for the eyes and the session alike',
     JSON.stringify({ hushed: fx.hushed, hushLeftS: fx.hushLeftS,
                      snoozed: fx.snoozed, snoozeLeftS: Math.round(fx.snoozeLeftS) }));

  const silenceMark = mark();
  await page.evaluate('void __hold("phone")');
  await sleep(3400);
  heard = await saidAfter(silenceMark);
  ok(fromPool(heard.map((s) => s.text), EVERY_EYE_LINE).length === 0,
     'and the phone posture that just earned a nudge now earns nothing at all',
     'heard: ' + JSON.stringify(heard.map((s) => s.text)));
  fx = await serverEyes();
  ok(fx.headDown === true && fx.hushed === true,
     'the valve silenced the voice and nothing else - it is still watching',
     JSON.stringify({ headDown: fx.headDown, hushed: fx.hushed,
                      hushLeftS: fx.hushLeftS }));
  // The bargain, stated as a check: the clock and the count carry on. A valve that
  // stopped those would be a way of never finishing anything.
  ok(fx.elapsedS > 0 && fx.remainingS < 10 * 60,
     'the clock kept running through the silence, which is what it costs',
     JSON.stringify({ elapsedS: Math.round(fx.elapsedS),
                      remainingS: Math.round(fx.remainingS) }));

  /* ---- 11. the lid shuts --------------------------------------------- */
  await page.evaluate('void __release()');
  const offMark = mark();
  await press('eye');
  const offLine = await waitSaid(offMark, 4000);
  ok(!!offLine && offLine.text === said.eyes_off,
     'closing the eyes is confirmed out loud',
     'said: ' + JSON.stringify(offLine && offLine.text));
  ok(await page.evaluate('__galaxy.eyes.on') === false &&
     await page.evaluate('__galaxy.eyes.indicator') === false,
     'the camera is off and the chip agrees');
  ok(await page.evaluate('__galaxy.eyes.base') === null &&
     await page.evaluate('__galaxy.eyes.raw') === null,
     'and the measurements of your body went with it');
  await sleep(1200);
  fx = await serverEyes();
  ok(fx.eyesOn === false && fx.headDown === false && fx.slouched === false,
     'the server has forgotten the posture too',
     JSON.stringify({ eyesOn: fx.eyesOn, headDown: fx.headDown }));
  ok(await page.evaluate('__galaxy.speech.listening') === false,
     'and through all of that no organ ever turned the microphone on');

  page.close();
}

main().catch((e) => {
  failures.push('the run itself: ' + e.message);
  console.log('\n  ERROR ' + e.message + '\n' + (e.stack || ''));
}).finally(async () => {
  try { await galaxy('/focus', { cmd: 'abort' }); } catch { /* server may be gone */ }
  if (chrome) { try { chrome.kill(); } catch { /* ignore */ } }
  await sleep(700);
  try { rmSync(profile, { recursive: true, force: true }); } catch { /* windows */ }
  console.log('\n  ' + checks + ' checks, ' + failures.length + ' failed\n');
  failures.forEach((f) => console.log('    FAILED: ' + f));
  if (failures.length) console.log('');
  process.exit(failures.length ? 1 : 0);
});
