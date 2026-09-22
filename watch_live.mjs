/* The screen watch, driven end to end in a real browser against your real monitor.
 *
 *   say "watch my screen"  ->  a real getDisplayMedia share of the ENTIRE SCREEN,
 *   confirmed off the track rather than off the request  ->  watch the five-second
 *   loop run for a while and prove that nothing has left the machine  ->  prove the
 *   two diff thresholds: a corner clock does not reset the stillness clock, a window
 *   opening does  ->  then LEAVE THE DESK ALONE for a minute and hear the one nudge
 *   ->  drive a second nudge inside the cooldown and hear nothing at all  ->  ask
 *   "what do you think of this?" and get an answer from THAT SAME SHARE, with no
 *   second picker  ->  say "stop watching" and watch the share go out with it
 *
 * What makes this a real run rather than a demonstration:
 *
 *   THE SHARE IS REAL. Chrome is launched with
 *   --auto-select-desktop-capture-source="Entire screen", so getDisplayMedia goes all
 *   the way through the browser's capture stack and the page holds a live track of
 *   your actual monitor. The frame that the nudge sends is a frame of your desk.
 *
 *   AND CHROME IS HEADLESS, which is not a convenience here - it is the experiment.
 *   The thing being measured is a STILLNESS CLOCK against the real screen, and a
 *   headed run would paint an animated 3D galaxy onto the very monitor it is
 *   watching: the clock would reset five times a second and the threshold would
 *   never arrive. Headless keeps the watcher off the watched screen.
 *
 *   THE DIFF IS FED, the way eyes_live.mjs feeds recorded landmarks: synthetic
 *   thumbnails go in through __galaxy.watch.feed(), the one door the real thumbnails
 *   come through, so the clock, the threshold and the nudge below it are the code the
 *   five-second timer drives.
 *
 * WHAT THIS RUN NEEDS FROM YOU: about a minute of not touching the desk, once, when
 * it says so. That is the feature. If something on your screen moves during it the
 * clock resets - correctly - and this file says so and waits again rather than
 * pretending. A run that moved the mouse for you would be proving nothing.
 *
 * The tab is loaded with ?mute=1, the law for every tab used for testing, so this run
 * is silent. Nothing is stubbed to make it silent: speak() records every line for six
 * seconds in __galaxy.speech.said with a flag for whether it reached the speakers, and
 * that log is what every claim about a spoken line - and every claim about a SILENCE -
 * reads here.
 *
 * Usage:  node watch_live.mjs        (with server.py already running on 4700)
 */

import { spawn } from 'node:child_process';
import { mkdtempSync, rmSync, existsSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const GALAXY = 'http://127.0.0.1:4700';
const VIEWER = GALAXY + '/?mute=1';
const CDP = 'http://127.0.0.1:9223';          // not 9222: eyes_live.mjs lives there
const NET_TIMEOUT_MS = 10000;

const CHROMES = [
  'C:/Program Files/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Google/Chrome/Application/chrome.exe',
  process.env.LOCALAPPDATA + '/Google/Chrome/Application/chrome.exe',
];

const t0 = Date.now();
const failures = [];
const notes = [];
let checks = 0;

const at = () => ((Date.now() - t0) / 1000).toFixed(2).padStart(6) + 's';
const log = (m) => console.log('  ' + at() + '  ' + m);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function ok(cond, claim, detail) {
  checks++;
  console.log('  ' + at() + (cond ? '  ok   ' : '  FAIL ') + claim);
  if (!cond) {
    failures.push(claim);
    if (detail) console.log('            ' + detail);
  }
}

/* Not every truth about a machine is a pass or a fail. A Chrome that will not hand
   over a tab capture without a picker is a fact about Chrome, and saying so is more
   use than a green tick that means nothing. */
function note(text) {
  notes.push(text);
  console.log('  ' + at() + '  note  ' + text);
}

async function cdp(path, base = CDP, method = 'GET') {
  const res = await fetch(base + path,
                          { method, signal: AbortSignal.timeout(NET_TIMEOUT_MS) });
  const text = await res.text();
  try { return JSON.parse(text); } catch { return text; }
}

async function galaxy(path) {
  const res = await fetch(GALAXY + path, { signal: AbortSignal.timeout(NET_TIMEOUT_MS) });
  return res.json();
}

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

  /* NEVER with awaitPromise on anything that may not settle - a share that is waiting
     on a picker would block this whole connection and the run would look hung rather
     than blocked. Everything here is fired with void and then polled. */
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

  async json(expression) {
    return JSON.parse(await this.evaluate('JSON.stringify(' + expression + ')') || 'null');
  }

  close() { try { this.ws.close(); } catch { /* already gone */ } }
}

async function launch(exe, profile, port, extraFlags) {
  const proc = spawn(exe, [
    '--headless=new',
    '--remote-debugging-port=' + port,
    '--user-data-dir=' + profile,
    '--no-first-run', '--no-default-browser-check',
    // The share. The first flag answers the picker; the second answers the permission
    // prompt, because a prompt nobody can click is a run that hangs.
    ...extraFlags,
    '--use-fake-ui-for-media-stream',
    '--autoplay-policy=no-user-gesture-required',
    '--window-size=1280,800',
    VIEWER,
  ], { detached: true, stdio: 'ignore' });
  const base = 'http://127.0.0.1:' + port;
  for (let i = 0; i < 80; i++) {
    try { await cdp('/json/version', base); break; } catch { await sleep(250); }
  }
  return proc;
}

async function attach(port) {
  const base = 'http://127.0.0.1:' + port;
  let target = null;
  for (let i = 0; i < 40; i++) {
    const list = await cdp('/json/list', base);
    target = (Array.isArray(list) ? list : [])
      .filter((t) => t.type === 'page').find((t) => t.url.includes('127.0.0.1:4700'));
    if (target) break;
    await sleep(300);
  }
  if (!target) throw new Error('the viewer tab never appeared on port ' + port);
  const page = new Page(target.webSocketDebuggerUrl);
  await page.open();
  await page.send('Runtime.enable');
  return page;
}

/* ============================================================== the run ==== */

const profiles = [];
const browsers = [];

function freshProfile(tag) {
  const dir = mkdtempSync(join(tmpdir(), 'watch-live-' + tag + '-'));
  profiles.push(dir);
  return dir;
}

async function main() {
  console.log('\n  the watch · the live loop\n');

  const exe = CHROMES.find((p) => existsSync(p));
  if (!exe) throw new Error('no chrome.exe found in the usual places');

  const health = await galaxy('/health');
  log('server: ' + health.notes + ' notes · brain ' + health.brain.label);

  /* The purse, before anything. This run measures one nudge and one refusal, and both
     of those are numbers that a previous run may have spent: the cooldown is the
     machine's, not the tab's, which is the whole point of it. */
  const purse0 = await galaxy('/stuck');
  const TUNE = purse0.tuning;
  log('the windows, from the server: still ' + TUNE.stillS + 's · cooldown ' +
      TUNE.cooldownS + 's · tick ' + TUNE.tickMs + 'ms · ' +
      TUNE.thumbW + 'x' + TUNE.thumbH + ' at ' + TUNE.cellDelta + ' luma / ' +
      (TUNE.changedFraction * 100).toFixed(1) + '% of cells');
  if (purse0.watch.hushed) {
    log('the eyes\' relief valve is open - ' + purse0.watch.hushLeftS + 's of silence ' +
        'left, and it covers this organ too, so this run waits it out');
    for (let i = 0; i < 200; i++) {
      await sleep(2000);
      if (!(await galaxy('/stuck')).watch.hushed) break;
    }
    log('the silence expired on its own');
  }
  if (!purse0.watch.mayNudge) {
    log('a nudge was spent ' + (TUNE.cooldownS - purse0.watch.cooldownLeftS) +
        's ago and the cooldown has ' + purse0.watch.cooldownLeftS + 's to run. ' +
        'Nothing may shorten it, so this run waits: that is the feature.');
    for (let i = 0; i < 200; i++) {
      await sleep(3000);
      if ((await galaxy('/stuck')).watch.mayNudge) break;
    }
    log('the purse is open again');
  }
  const nudges0 = purse0.watch.nudges;
  const refused0 = purse0.watch.refused;

  browsers.push(await launch(exe, freshProfile('main'), 9223,
                             ['--auto-select-desktop-capture-source=Entire screen']));
  const version = await cdp('/json/version');
  log('chrome: ' + version.Browser + ' (headless, so the watcher is not on the ' +
      'watched screen)');
  const page = await attach(9223);
  await sleep(3500);                    // the viewer's 3D boot

  ok(await page.evaluate('!!window.__galaxy && !!window.__galaxy.watch'),
     'the viewer exposes the watch handle');
  ok(await page.evaluate('__galaxy.speech.muted') === true,
     'the tab was loaded with ?mute=1, so this run is silent and still checkable');
  ok(await page.evaluate('__galaxy.sight.supported') === true,
     'this browser will give the page a screen');
  ok(await page.evaluate('__galaxy.watch.on') === false,
     'and nothing is being watched yet');
  const pageTune = await page.json('__galaxy.watch.tuning');
  ok(JSON.stringify(pageTune) === JSON.stringify(TUNE),
     'the page starts with the server\'s windows, not a copy of its own',
     JSON.stringify(pageTune) + ' vs ' + JSON.stringify(TUNE));

  /* ---- the helpers ----------------------------------------------------- */

  const mark = () => Date.now();
  /* Every entry is {at, text, aloud}. In a muted tab `aloud` is false by design - the
     line is recorded, not spoken - so "it said this" is a claim about the log, and
     "it said nothing" is a claim about the log being empty. Both are checkable, which
     is the whole reason the log exists. */
  const saidIn = async (p, since) => (await p.json(
    '__galaxy.speech.said.filter(function (s) { return s.at > ' + since + '; })')) || [];
  const saidAfter = (since) => saidIn(page, since);
  async function waitSaidIn(p, since, ms, match) {
    const stop = Date.now() + ms;
    for (;;) {
      const lines = (await saidIn(p, since)).filter((s) => !match || match.test(s.text));
      if (lines.length) return lines[0];
      if (Date.now() >= stop) return null;
      await sleep(120);
    }
  }
  const waitSaid = (since, ms, match) => waitSaidIn(page, since, ms, match);
  const W = async (what) => page.json('__galaxy.watch.' + what);
  async function until(expr, ms, every = 200) {
    const stop = Date.now() + ms;
    for (;;) {
      if (await page.evaluate(expr)) return true;
      if (Date.now() >= stop) return false;
      await sleep(every);
    }
  }

  /* A synthetic thumbnail: 576 grey numbers, the shape the real one has. `changed` of
     them are pushed far past the cell threshold and the rest are left alone, so the
     fraction is chosen rather than hoped for.
     THE WHOLE SEQUENCE GOES IN ONE EVALUATION, because the real five-second tick is
     also feeding this organ from the real monitor: split across four round trips, a
     tick landing between two of them would diff a synthetic screen against a real one
     and every verdict after it would be about the wrong pair of pictures. */
  const FEED_SEQ = (steps) =>
    '(function () {' +
    ' var N = ' + (TUNE.thumbW * TUNE.thumbH) + ', out = [];' +
    ' function mk(base, changed) {' +
    '   var a = new Uint8ClampedArray(N);' +
    '   for (var i = 0; i < N; i++) a[i] = base;' +
    '   for (var j = 0; j < changed; j++) a[j] = base + 80;' +
    '   return a; }' +
    ' var plan = ' + JSON.stringify(steps) + ';' +
    ' for (var k = 0; k < plan.length; k++) {' +
    '   var v = __galaxy.watch.feed(mk(plan[k][0], plan[k][1]));' +
    '   out.push({cells: v && v.cells, fraction: v && v.fraction,' +
    '             changed: v && v.changed, total: v && v.total,' +
    '             stillS: __galaxy.watch.stillS}); }' +
    ' return out; })()';

  // ============================================================ 1. "watch my screen"

  console.log('\n  -- 1. the share, and what it actually is\n');

  const said1 = mark();
  await page.evaluate('void __galaxy.ask("watch my screen")');
  ok(await until('__galaxy.watch.on', 20000),
     'saying "watch my screen" starts a watch');
  const surface = await W('surface');
  ok(surface === 'monitor',
     'and the track says the surface is a monitor - the entire screen, off the track ' +
     'rather than off the request', 'displaySurface=' + JSON.stringify(surface));
  ok(await page.evaluate('__galaxy.watch.indicator') === true,
     'the amber chip agrees with the organ');
  ok(await page.evaluate('__galaxy.sight.sharing') === true,
     'there is exactly one live share, and the watch is using it');
  ok(await W('ownsShare') === true,
     'and the watch knows the share is its own to close');

  const onLine = await waitSaid(said1, 6000, /watching your screen/i);
  ok(!!onLine, 'it says so out loud', JSON.stringify(await saidAfter(said1)));
  ok(!!onLine && /nothing leaves this machine/i.test(onLine.text),
     'and the sentence is about what this costs, not about what it can see',
     onLine && onLine.text);

  // THE FACE. Exactly one of its two homes, and the page is honest about which.
  const pinned = await W('facePinned');
  const card = await W('faceCard');
  ok(pinned !== card,
     'the face has exactly one home: the desktop or the page, never both and never ' +
     'neither', 'pinned=' + pinned + ' card=' + card);
  if (pinned) {
    log('the face is pinned off the page, above every other window');
  } else {
    note('this Chrome would not open a Document Picture-in-Picture window (headless ' +
         'has no desktop to pin to), so the face is on the page - and the spoken ' +
         'line said so rather than claiming a pin it did not get');
    ok(!!onLine && /will not let my face off the/i.test(onLine.text),
       'and it said exactly that, unprompted', onLine && onLine.text);
  }

  // ====================================================== 2. the loop costs nothing

  console.log('\n  -- 2. three ticks of the free loop\n');

  const ticks0 = await W('ticks');
  await sleep(Math.round(TUNE.tickMs * 2.4));
  const ticks1 = await W('ticks');
  ok(ticks1 > ticks0,
     'the five-second loop is running against the real screen',
     'ticks ' + ticks0 + ' -> ' + ticks1);
  const diff = await W('lastDiff');
  ok(!!diff && diff.total === TUNE.thumbW * TUNE.thumbH,
     'and each tick compares exactly ' + (TUNE.thumbW * TUNE.thumbH) + ' grey numbers',
     JSON.stringify(diff));
  ok(await W('lastNudge') === null,
     'nothing has been sent anywhere: the loop has cost nothing but arithmetic');
  const purse1 = await galaxy('/stuck');
  ok(purse1.watch.nudges === nudges0 && purse1.watch.refused === refused0,
     'and the server has not been asked for anything at all',
     JSON.stringify(purse1.watch));
  ok(/no frame sent/.test(await page.evaluate("document.getElementById('watch-sent').textContent")),
     'the chip says "no frame sent", which is still true');

  // ===================================================== 3. the two thresholds

  console.log('\n  -- 3. what counts as the screen changing\n');

  /* Five feeds in one breath. The first two settle the organ on a flat grey screen
     (the first one differs from the real monitor and so resets the clock, which is
     exactly right); then a corner clock, then a bigger corner clock, then a window
     opening. The counts CLIMB - 1, 9, 49 - because each verdict is about the step
     before it, so what is being fed is 1 more cell, then 8 more, then 40 more. */
  const seq = await page.json(FEED_SEQ([[60, 0], [60, 0], [60, 1], [60, 9], [60, 49]]));
  const [, settled, clock1, clock8, change] = seq;
  ok(settled && settled.changed === false && settled.total === TUNE.thumbW * TUNE.thumbH,
     'two identical screens in a row are not a change', JSON.stringify(settled));

  // A corner clock. One cell of 576 is 0.17% - far under the 1.5% the screen must
  // move by - and this is the check that the fraction is a FEATURE and not a fudge:
  // without it, any desktop with a clock on it would reset this timer for ever and
  // the nudge below would never once fire.
  ok(clock1 && clock1.cells === 1 && clock1.changed === false,
     'one cell of 576 moving is a clock ticking in the corner, and the screen has ' +
     'not changed', JSON.stringify(clock1));
  ok(clock8 && clock8.cells === 8 && clock8.changed === false,
     'eight of them - 1.4% - is still under the line', JSON.stringify(clock8));
  ok(clock8 && clock8.stillS >= settled.stillS,
     'so the stillness clock has not been reset by any of it',
     settled.stillS + 's -> ' + (clock8 && clock8.stillS) + 's');

  // A window opening. 40 cells is 6.9%, and that is a man doing something.
  ok(change && change.cells === 40 && change.changed === true,
     'forty cells - 6.9% - is a window opening, and the screen HAS changed',
     JSON.stringify(change));
  ok(change && change.stillS === 0,
     'and the stillness clock is back to zero', JSON.stringify(change));

  // ============================================== 4. the threshold, and the nudge

  console.log('\n  -- 4. now leave the desk alone for ' + TUNE.stillS + ' seconds\n');
  log('THE REAL SCREEN IS BEING WATCHED. If anything on it moves, the clock resets - ' +
      'correctly - and this waits again.');

  let nudge = null, resets = 0, attempts = 0;
  const said4 = mark();
  /* Six attempts, because a desk is not a laboratory: a spinner in a terminal, a
     notification, a clock with a second hand - any of them resets the clock, and
     every one of those resets is the feature working. What would be dishonest is
     giving up after one and calling the feature broken. */
  while (!nudge && attempts < 6) {
    attempts++;
    const startedAt = await W('stillS');
    const deadline = Date.now() + (TUNE.stillS + 25) * 1000;
    let last = startedAt;
    while (Date.now() < deadline) {
      await sleep(1500);
      const now = await W('stillS');
      if (now < last) { resets++; log('the screen moved - the clock reset at ' + last + 's'); }
      last = now;
      nudge = await W('lastNudge');
      if (nudge) break;
    }
    if (!nudge) {
      log('attempt ' + attempts + ' did not reach ' + TUNE.stillS + 's of stillness (' +
          resets + ' resets so far)');
    }
  }

  ok(!!nudge,
     'a screen held still for ' + TUNE.stillS + ' seconds earns one nudge',
     resets + ' resets in ' + attempts + ' attempt(s) - something on the real screen ' +
     'kept moving, which is the feature working, not a bug. Run it again on a quiet ' +
     'desk.');

  if (nudge) {
    log('the nudge landed at ' + nudge.stillS + 's of stillness, ' +
        Math.round(nudge.bytes / 1024) + ' KB of a ' + nudge.w + '×' + nudge.h +
        ' frame, ' + nudge.ageMs + 'ms old');
    ok(nudge.spent === true && nudge.status === 200,
       'and it cost exactly one model call', JSON.stringify({
         status: nudge.status, spent: nudge.spent, why: nudge.why }));
    ok(nudge.stillS >= TUNE.stillS,
       'it was not sent one second early', nudge.stillS + 's');
    ok(nudge.ageMs < 10000,
       'the frame was grabbed at the moment of asking, not earlier', nudge.ageMs + 'ms');
    ok(nudge.text.length > 0 && nudge.quiet === false,
       'the brain said something', JSON.stringify(nudge.text.slice(0, 120)));
    /* THE NUDGE IS SPOKEN, and in a muted tab that means it reached the one function
       that speaks and was recorded there. `aloud` is false because ?mute=1 is the law
       for a test tab - and a line in this log is exactly what the silence checks
       below are the absence of. */
    const spoken = await waitSaid(said4, 4000, /.{15,}/);
    ok(!!spoken && spoken.text === nudge.text,
       'the page said it, unasked, and said precisely what the brain sent',
       JSON.stringify(spoken && spoken.text.slice(0, 90)));
    ok(!!spoken && spoken.aloud === false,
       'aloud=false, because this tab is muted - nothing here is stubbed to be silent');
    ok(await page.evaluate('__galaxy.watch.nudges') === 1,
       'one frame has left this machine, and the chip says so',
       await page.evaluate("document.getElementById('watch-sent').textContent"));
    ok(await page.evaluate('__galaxy.sight.proofShown') === true,
       'the exact frame it sent is shown beside the nudge, so the claim is checkable ' +
       'by eye');
    const purse2 = await galaxy('/stuck');
    ok(purse2.watch.nudges === nudges0 + 1,
       'and the server counted one nudge, not two', JSON.stringify(purse2.watch));
    ok(purse2.watch.mayNudge === false && purse2.watch.cooldownLeftS > 120,
       'the purse is shut for ' + purse2.watch.cooldownLeftS + ' seconds',
       JSON.stringify(purse2.watch));

    // =========================================== 5. and then it shuts up
    console.log('\n  -- 5. the three-minute cooldown\n');

    await sleep(1200);                  // let the nudge's own line age out of the way
    const said5 = mark();
    // The same call the tick makes at the threshold, made by hand rather than by
    // waiting another minute for the clock. Everything past this point is the
    // server's answer.
    await page.evaluate('void __galaxy.watch.nudge()');
    await until('__galaxy.watch.lastNudge && __galaxy.watch.lastNudge.at > ' +
                nudge.at, 15000);
    const refusal = await W('lastNudge');
    ok(!!refusal && refusal.status === 429 && refusal.why === 'cooldown',
       'a second nudge inside the cooldown is refused', JSON.stringify(refusal && {
         status: refusal.status, why: refusal.why }));
    ok(!!refusal && refusal.quiet === true && refusal.spoke === false,
       'and refused SILENTLY - an announced silence is not a silence');
    await sleep(2500);
    const duringCooldown = await saidAfter(said5);
    ok(duringCooldown.length === 0,
       'nothing at all was said in the ' + Math.round((Date.now() - said5) / 1000) +
       ' seconds since', JSON.stringify(duringCooldown.map((s) => s.text)));
    const purse3 = await galaxy('/stuck');
    ok(purse3.watch.nudges === nudges0 + 1,
       'and it bought no second model call', JSON.stringify(purse3.watch));
  }

  // =============================== 6. an answer from that same share

  console.log('\n  -- 6. "what do you think of this?" - from the share already open\n');

  const sharingBefore = await page.evaluate('__galaxy.sight.sharing');
  const sentBefore = await page.json('__galaxy.sight.lastSent');
  ok(sharingBefore === true && sentBefore === null,
     'going in: one live share, and not one frame of it sent by a question yet',
     JSON.stringify(sentBefore));
  const said6 = mark();
  await page.evaluate('void __galaxy.ask("what do you think of this?")');
  ok(await until('__galaxy.sight.lastSent', 60000),
     'the question is answered from the screen while the watch is running');
  const sent = await page.json('__galaxy.sight.lastSent');
  ok(!!sent, 'and it sent one frame of it', JSON.stringify(sent));
  ok(await page.evaluate('__galaxy.sight.sharing') === true,
     'from THE SAME SHARE: no second picker, no second stream, one capture on this ' +
     'machine throughout');
  ok(await W('on') === true,
     'and the watch is still watching, having answered a question in the middle of it');
  const answered = await waitSaid(said6, 40000, /.{25,}/);
  ok(!!answered, 'the answer was spoken', answered && answered.text.slice(0, 90));
  const held = await W('held');
  log('ticks deferred while that question was in flight: ' + held +
      ' (the clock kept running; only the voice waited)');

  // ======================================================= 7. stop watching

  console.log('\n  -- 7. "stop watching"\n');

  const said7 = mark();
  await page.evaluate('void __galaxy.ask("stop watching")');
  ok(await until('!__galaxy.watch.on', 10000), 'the watch stops when told to');
  const offLine = await waitSaid(said7, 6000, /no longer watching/i);
  ok(!!offLine, 'and says so', JSON.stringify(await saidAfter(said7)));
  ok(await page.evaluate('__galaxy.watch.indicator') === false,
     'the chip goes out with it');
  ok(await W('facePinned') === false && await W('faceCard') === false,
     'so does the face - there is no watching face over a watch that has stopped');
  ok(await page.evaluate('__galaxy.sight.sharing') === false,
     'and the share the watch opened goes out too, rather than leaving a capture ' +
     'running that nothing is using');

  const ticksAfter = await W('ticks');
  await sleep(Math.round(TUNE.tickMs * 1.6));
  ok(await W('ticks') === ticksAfter,
     'the five-second loop has genuinely stopped, not merely gone quiet',
     ticksAfter + ' -> ' + (await W('ticks')));

  page.close();

  // ================================================= 8. the tab-share trap

  console.log('\n  -- 8. the trap: a tab cannot police tabs\n');

  /* A second browser, launched with the flag that hands getDisplayMedia a TAB instead
     of a screen. If it works, the watch must refuse it out loud; if this Chrome will
     not do it without a picker, that is a fact about Chrome and is reported as one
     rather than dressed up as a pass. */
  browsers.push(await launch(exe, freshProfile('tab'), 9224, [
    // The viewer's own <title>, exactly: this flag matches the whole thing.
    '--auto-select-tab-capture-source-by-title=Knowledge Galaxy',
  ]));
  let tabPage = null;
  try {
    tabPage = await attach(9224);
    /* A SECOND tab, and it is not a nicety: the watch asks for the share with
       selfBrowserSurface:'exclude', so the asking tab is kept out of the picker
       list - correctly, since watching the watcher is never the right answer. With
       one tab in the browser that leaves the flag nothing to auto-select and Chrome
       hands over the screen instead. A second tab with the same title is the one
       Chrome can pick, and it is the one this phase needs it to pick. */
    try {
      await cdp('/json/new?' + encodeURIComponent(VIEWER),
                'http://127.0.0.1:9224', 'PUT');
      await sleep(2500);
    } catch {
      note('this Chrome would not open a second tab over CDP, so the picker had only ' +
           'the asking tab to offer - which the watch excludes on purpose');
    }
    await sleep(3500);
    const saidT = mark();
    await tabPage.evaluate('void __galaxy.ask("watch my screen")');
    const settled = await (async () => {
      const stop = Date.now() + 20000;
      for (;;) {
        const s = await tabPage.json(
          '{on: __galaxy.watch.on, surface: __galaxy.watch.surface,' +
          ' trouble: __galaxy.watch.trouble, sharing: __galaxy.sight.sharing}');
        if (s.on || s.trouble) return s;
        if (Date.now() >= stop) return s;
        await sleep(300);
      }
    })();
    if (settled.trouble === 'tab') {
      ok(settled.on === false,
         'handed a single tab, the watch refuses to start', JSON.stringify(settled));
      const steer = await waitSaidIn(tabPage, saidT, 6000, /Entire Screen/i);
      ok(!!steer, 'and says so, steering to Entire Screen',
         JSON.stringify(await saidIn(tabPage, saidT)));
      ok(!!steer && /wander/i.test(steer.text) && /scrolling/i.test(steer.text),
         'naming both halves of the trap: it keeps painting itself, and its own ' +
         'scrolling would read as work', steer && steer.text);
      ok(settled.sharing === false,
         'and the capture it may not use is closed again');
    } else if (settled.on && settled.surface === 'monitor') {
      note('this Chrome will not auto-select a tab capture at all - it answers ' +
           '--auto-select-tab-capture-source-by-title with screen:0:0 regardless, ' +
           'with a uniquely titled second tab and with no monitor hint in the ' +
           'request - so the trap could not be sprung live on this machine. The ' +
           'refusal itself is covered by test_watch.py, which reads both surface ' +
           'checks, the sentence they speak and the share they close. This phase is ' +
           'left in so that a Chrome which honours the flag springs it.');
    } else {
      note('the tab-capture flag left this browser with ' + JSON.stringify(settled) +
           ', which is neither a tab nor a screen - nothing to conclude, so nothing ' +
           'is claimed.');
    }
  } catch (e) {
    note('the tab-capture browser could not be driven (' + e.message + '), so the ' +
         'trap was not sprung live; test_watch.py covers the refusal.');
  } finally {
    if (tabPage) tabPage.close();
  }
}

function teardown() {
  /* Chrome is a tree of processes and kill() reaches the root of it. taskkill /T is
     the Windows follow-up, because a renderer left holding a screen capture is a
     green light on somebody's taskbar for no reason at all. */
  for (const b of browsers) {
    try { b.kill(); } catch { /* already gone */ }
    try {
      spawn('taskkill', ['/PID', String(b.pid), '/T', '/F'], { stdio: 'ignore' });
    } catch { /* not windows, or already gone */ }
  }
  for (const p of profiles) {
    try { rmSync(p, { recursive: true, force: true }); } catch { /* windows locks it */ }
  }
}

main().catch((e) => {
  failures.push('the run itself: ' + e.message);
  console.log('\n  ' + at() + '  FAIL the run itself: ' + e.message + '\n');
  if (e.stack) console.log(e.stack.split('\n').slice(1, 4).join('\n'));
}).finally(async () => {
  await sleep(300);
  teardown();
  console.log('\n  ' + checks + ' checks, ' + failures.length + ' failed');
  if (notes.length) {
    console.log('');
    for (const n of notes) console.log('    note: ' + n);
  }
  if (failures.length) {
    console.log('');
    for (const f of failures) console.log('    FAILED: ' + f);
  }
  console.log('');
  process.exit(Math.min(failures.length, 120));
});
