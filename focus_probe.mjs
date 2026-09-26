/* The instruments, in a real browser, with the server that is actually running.
 *
 *   read /focus/diag from the LONG-LIVED process  ->  read the ledger on disk  ->
 *   open ?focusprobe=1 at an asserted 1440x900 and read the verdict out of the page
 *   title  ->  open ?focusdebug=1 and check the overlay is really on the glass
 *
 * Why this file exists when test_focus_privacy.py already passes: everything below the
 * page can be proved in process, and none of it answers the question you actually have
 * at the moment a feature "isn't working" - which is whether the process holding your
 * session agrees with the code on disk. So the diag is read over HTTP from whatever is
 * listening on 4700, not from a fresh import, and the battery is run in Chrome rather
 * than reasoned about.
 *
 * THE VIEWPORT IS ASSERTED, at 1440 by 900, and the device metrics are overridden to
 * guarantee it before the battery is re-run. This is not decoration: a hidden or
 * throttled tab stretches a 250 ms timeout into a second or more, and every time-based
 * check on the page then passes or fails for reasons that have nothing to do with the
 * feature. The probe has two cases whose whole job is to catch that - `viewport` and
 * `timers` - and this runner makes sure they are answering about a real, visible,
 * correctly-sized tab.
 *
 * READ-ONLY against the server, on purpose. It starts no session and finishes none: a
 * real session long enough to write a ledger row would move the streak, and an
 * instrument that edits the thing it is measuring is not an instrument. The row's
 * eight-key whitelist is proved in test_focus_privacy.py against a throwaway ledger;
 * what is checked here is the shape of the real file on disk.
 *
 * The tabs are loaded with ?mute=1 - the law for every tab used for testing - so the
 * run is silent.
 *
 * Usage:  node focus_probe.mjs        (with server.py already running on 4700)
 */

import { spawn } from 'node:child_process';
import { mkdtempSync, rmSync, existsSync, readFileSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const GALAXY = 'http://127.0.0.1:4700';
const PROBE_URL = GALAXY + '/?focusprobe=1&mute=1';
const DEBUG_URL = GALAXY + '/?focusdebug=1&mute=1';
const PORT = 9225;                 // 9222 eyes, 9223 watch, 9224 brain, 9225 this
const CDP = 'http://127.0.0.1:' + PORT;
const NET_TIMEOUT_MS = 10000;
const WANT_W = 1440, WANT_H = 900;
const LEDGER = join(dirname(fileURLToPath(import.meta.url)), 'focus-ledger.json');

/* The eight keys a session row may have, and nothing else. Stated here as well as in
   focus.py so this run would notice the file growing a ninth field even if somebody
   had edited the whitelist to allow it. */
const ROW_KEYS = ['at', 'plannedMinutes', 'activeMinutes', 'onTargetMinutes',
                  'drifts', 'secondsAdrift', 'percent', 'completed'];

/* What the probe page must report on. A case going missing is a failure: a battery
   that quietly stopped running half of itself still says PASS. */
const WANT_CASES = ['viewport', 'visible', 'timers', 'frames', 'clock', 'phrases',
                    'card-on', 'card-drift', 'card-defer', 'card-blind', 'card-phone',
                    'gate', 'luma', 'seq', 'no-names', 'web-cue', 'web-safe',
                    'desk-move', 'desk-skin', 'merge', 'stack', 'lane', 'visage', 'eyeslaw',
                    'retire', 'hermetic'];

const CHROMES = [
  'C:/Program Files/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Google/Chrome/Application/chrome.exe',
  process.env.LOCALAPPDATA + '/Google/Chrome/Application/chrome.exe',
];

const t0 = Date.now();
const failures = [];
const notes = [];
let checks = 0;
let verdictLine = '';

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

  async evaluate(expression) {
    const r = await this.send('Runtime.evaluate', {
      expression, returnByValue: true, awaitPromise: true,
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

  /* A PLATE, and a CLOSE-UP when a rectangle is handed in - at 2x, because the two
     pictures this harness owes the lookbook are a 210px hologram with its eyes shut and
     the same one with them open, and a crop of a 1440px frame cannot show an eyelid. */
  async shot(file, clip) {
    const r = await this.send('Page.captureScreenshot', clip
      ? { format: 'png', clip: { x: clip.left, y: clip.top, width: clip.w, height: clip.h,
                                 scale: clip.scale || 2 } }
      : { format: 'png' });
    const data = r.result && r.result.data;
    if (!data) throw new Error('no screenshot came back');
    writeFileSync(file, Buffer.from(data, 'base64'));
    return file;
  }

  close() { try { this.ws.close(); } catch { /* already gone */ } }
}

async function launch(exe, profile, url) {
  const proc = spawn(exe, [
    '--headless=new',
    '--remote-debugging-port=' + PORT,
    '--user-data-dir=' + profile,
    '--no-first-run', '--no-default-browser-check',
    /* A CAMERA THAT EXISTS AND A PROMPT NOBODY HAS TO CLICK. Section 3c asserts the Eyes
       Law both ways round, and the closed half of it is worthless without the open half:
       "the face does not look when the camera is off" is only a law if opening the camera
       is what makes it look. The stream is Chrome's own test pattern - no frame of it is
       kept, and nothing in this run uploads one. */
    '--use-fake-device-for-media-stream',
    '--use-fake-ui-for-media-stream',
    '--autoplay-policy=no-user-gesture-required',
    /* The window this run insists on. Overridden again over CDP below, because a
       window size is a request and device metrics are a guarantee. */
    '--window-size=' + WANT_W + ',' + WANT_H,
    url,
  ], { detached: true, stdio: 'ignore' });
  for (let i = 0; i < 80; i++) {
    try { await cdp('/json/version'); break; } catch { await sleep(250); }
  }
  return proc;
}

async function attach(match) {
  let target = null;
  for (let i = 0; i < 40; i++) {
    const list = await cdp('/json/list');
    target = (Array.isArray(list) ? list : [])
      .filter((t) => t.type === 'page').find((t) => t.url.includes(match));
    if (target) break;
    await sleep(300);
  }
  if (!target) throw new Error('no page on port ' + PORT + ' matching ' + match);
  const page = new Page(target.webSocketDebuggerUrl);
  await page.open();
  await page.send('Runtime.enable');
  await page.send('Page.enable');
  return page;
}

/* WAIT FOR THE HANDLE, rather than sleeping for a number somebody guessed once.
   __galaxy is assigned on the last line of the page's own script, after the 3D
   library has loaded from a CDN, so how long that takes is not this run's business -
   but checking too early and reporting "the viewer exposes no probe handle" would be
   this run telling a lie about the page. */
async function waitForGalaxy(page, what, budgetMs = 30000) {
  for (let i = 0; i < budgetMs / 250; i++) {
    try {
      if (await page.evaluate('!!(window.__galaxy && window.__galaxy.' + what + ')')) {
        return true;
      }
    } catch { /* the context is still being replaced; ask again */ }
    await sleep(250);
  }
  return false;
}

/* ============================================================== the run ==== */

const profiles = [];
const browsers = [];

async function main() {
  console.log('\n  the instruments · diag, ledger, probe page, overlay\n');

  const exe = CHROMES.find((p) => existsSync(p));
  if (!exe) throw new Error('no chrome.exe found in the usual places');

  /* ---- 1. THE DIAG, from whatever is actually listening ----------------- */
  log('-- the diag: read from the RUNNING server, not from a fresh import');

  const health = await galaxy('/health');
  log('server: ' + health.notes + ' notes · answering with ' +
      (health.brain ? health.brain.label : '?'));

  const payload = await galaxy('/focus/diag');
  const d = payload && payload.diag;
  ok(!!d, 'GET /focus/diag answers', JSON.stringify(payload).slice(0, 200));
  const diag = d || {};
  note('pid ' + diag.pid + ' · up ' + Math.round((diag.uptimeS || 0) / 60) +
       'm · ticks ' + diag.ticks + ' · last tick ' + diag.tickAgeS + 's ago');
  /* THE FROZEN PROCESS, which is the reason this route exists at all. A long-lived
     server can be serving a config it read before you fixed it; pid and uptime are
     how you notice, and they are useless unless something prints them. */
  ok(typeof diag.pid === 'number' && diag.pid > 0 && diag.uptimeS >= 0,
     'it identifies the process that answered: pid ' + diag.pid +
     ', up for ' + Math.round((diag.uptimeS || 0) / 60) + ' minutes');
  ok(diag.tickAlive === false || diag.tickAgeS <= 5,
     'and the tick thread is either honestly dead or genuinely ticking',
     JSON.stringify({ tickAlive: diag.tickAlive, tickAgeS: diag.tickAgeS }));
  if (!diag.tickAlive) {
    note('no tick thread yet, which is correct with no session since the restart: ' +
         'the thread is started by the first session and lives for the process');
  }

  const strings = Object.entries(diag).filter(([, v]) => typeof v === 'string');
  const VOCAB = ['on', 'off', 'unknown', 'n/a', 'read', 'notbrowser', 'ambiguous',
                 'noendpoint', 'idle', 'arming', 'running', 'paused', 'ended'];
  const loose = strings.filter(([k, v]) => k !== 'backend' && !VOCAB.includes(v));
  ok(!loose.length,
     'every word in it comes from a fixed set, so there is nowhere for a name to be',
     JSON.stringify(loose));
  ok(/^[A-Za-z0-9_]{1,24}$/.test(diag.backend || ''),
     'and the backend is an identifier out of focus.py: ' + diag.backend);
  const nested = Object.entries(diag).filter(([, v]) => v && typeof v === 'object');
  ok(!nested.length, 'nothing nested: booleans, small numbers and words only',
     JSON.stringify(nested.map(([k]) => k)));
  /* The one check here that the in-process test cannot make: this diag was taken
     against the REAL desktop, so if an identity could get out, a real app name or a
     real host would be sitting in it right now. */
  const leak = JSON.stringify(diag).match(/[\w-]+\.(exe|com|net|org|io|app|local)\b/i);
  ok(!leak, 'and it was taken against the real desktop with nothing leaking out',
     leak ? leak[0] : '');
  log('front: ' + (diag.appReadable ? 'readable' : 'UNREADABLE') + ' · ' +
      (diag.frontIsBrowser ? 'browser' : 'native app') + ' · tab ' + diag.tabRead +
      ' · galaxy tab ' + (diag.frontIsHome ? 'yes' : 'no') + ' · cdp ' +
      (diag.cdpAlive ? 'alive' : 'none'));
  log('lock:  session ' + (diag.sessionOn ? 'on' : 'off') + ' · ' + diag.state +
      ' · locked ' + diag.locked + ' · lanes app=' + diag.appLane + ' tab=' +
      diag.tabLane + ' · settle ' + diag.settleTicks + '/' + diag.settleNeeded);

  /* THE LAW, step three: count the browser windows, and know which host this app's
     own tab is on. Counts only for the ports this run did not open - what is in the
     user's own browser is not this script's business. */
  const windows = [];
  for (const port of [9222, 9223, 9224, PORT]) {
    try {
      const list = await cdp('/json/list', 'http://127.0.0.1:' + port);
      const pages = (Array.isArray(list) ? list : []).filter((t) => t.type === 'page');
      const mine = pages.filter((t) => t.url.includes('127.0.0.1:4700')).length;
      windows.push(port + ': ' + pages.length + ' pages, ' + mine + ' on this app');
    } catch { windows.push(port + ': no endpoint'); }
  }
  note('browser endpoints · ' + windows.join(' · '));

  /* ---- 2. THE LEDGER on disk ------------------------------------------- */
  log('');
  log('-- the ledger: the shape of the real file, read and not written');

  let book = null;
  try { book = JSON.parse(readFileSync(LEDGER, 'utf8')); } catch { book = null; }
  if (!book) {
    note('no ledger on disk yet, so there is no row to check the shape of - it is ' +
         'written by the first session that runs longer than MIN_LEDGER_S');
  } else {
    const rows = Array.isArray(book.history) ? book.history : [];
    if (!('history' in book)) {
      /* A file written before the row existed. read_ledger() fills the key in and the
         next session that ends writes it, so this is a fact about the file's age
         rather than a fault - and saying so is the difference between an instrument
         and an alarm. */
      note('this ledger predates the per-session row: no history key on it yet, ' +
           'and the next session that runs past MIN_LEDGER_S adds one');
    }
    ok(!('history' in book) || Array.isArray(book.history),
       'the ledger carries a history array of end-of-session rows: ' + rows.length +
       ' of them', JSON.stringify(Object.keys(book)));
    const stray = [...new Set(rows.flatMap((r) => Object.keys(r || {})))]
      .filter((k) => !ROW_KEYS.includes(k));
    ok(!stray.length, 'and every row on disk has only the eight whitelisted keys',
       JSON.stringify(stray));
    const wrong = rows.filter((r) => ROW_KEYS.some((k) => !(k in r)));
    ok(!wrong.length, 'each of them complete, so a row is never half a record',
       JSON.stringify(wrong.slice(0, 1)));
    const dirty = JSON.stringify(book)
      .match(/[\w-]+\.(exe|com|net|org|io|app|local)\b/i);
    ok(!dirty, 'and the file holds no app, no site and no dictated sentence',
       dirty ? dirty[0] : '');
    if (rows.length) {
      const last = rows[rows.length - 1];
      log('last row: ' + last.at + ' · planned ' + last.plannedMinutes + 'm · active ' +
          last.activeMinutes + 'm · on target ' + last.onTargetMinutes + 'm · drifts ' +
          last.drifts + ' · adrift ' + last.secondsAdrift + 's · ' + last.percent +
          '% · ' + (last.completed ? 'completed' : 'ended early'));
    }
  }

  /* ---- 3. THE PROBE PAGE at an asserted 1440x900 ----------------------- */
  log('');
  log('-- the probe page: ?focusprobe=1 at an asserted ' + WANT_W + 'x' + WANT_H);

  const profile = mkdtempSync(join(tmpdir(), 'focus-probe-'));
  profiles.push(profile);
  browsers.push(await launch(exe, profile, PROBE_URL));
  const version = await cdp('/json/version');
  log('chrome: ' + version.Browser);

  const page = await attach('focusprobe=1');
  ok(await waitForGalaxy(page, 'probe'), 'the viewer exposes the probe handle');
  ok(await page.evaluate('__galaxy.probe.on') === true,
     'and the page knows it is in probe mode');
  ok(await page.evaluate('__galaxy.speech.muted') === true,
     'the tab was loaded with ?mute=1, so this run is silent and still checkable');

  /* THE ASSERTED VIEWPORT. A window size is what Chrome was asked for; device metrics
     are what the page gets. Both, then the battery is re-run so every case answers
     about the guaranteed size rather than about whatever the first frame happened to
     be. Visibility is forced the same way and for the same reason. */
  const first = await page.json('__galaxy.probe.viewport');
  await page.send('Emulation.setDeviceMetricsOverride', {
    width: WANT_W, height: WANT_H, deviceScaleFactor: 1, mobile: false,
  });
  await page.send('Page.bringToFront');
  await sleep(250);
  const sized = await page.json('__galaxy.probe.viewport');
  ok(sized.w === WANT_W && sized.h === WANT_H,
     'the viewport is ' + WANT_W + ' by ' + WANT_H + ', asserted rather than assumed',
     'launched at ' + first.w + 'x' + first.h + ', now ' + sized.w + 'x' + sized.h);
  ok(sized.visible === true,
     'and the tab is visible, so a throttled timer cannot make a time-based case lie',
     JSON.stringify(sized));

  /* Stringified inside the page's own promise chain: the battery is asynchronous, so
     JSON.stringify of the call would faithfully serialise a pending promise. */
  const verdict = JSON.parse(
    await page.evaluate('__galaxy.probe.run().then(v => JSON.stringify(v))'));
  ok(await page.evaluate('__galaxy.probe.done') === true,
     'the battery ran to the end and said so');
  const cases = await page.json('__galaxy.probe.cases');
  for (const c of cases) {
    console.log('  ' + at() + (c.ok ? '  ok   ' : '  FAIL ') + 'case ' + c.name +
                '  ' + c.detail);
    checks++;
    if (!c.ok) failures.push('probe case ' + c.name + ': ' + c.detail);
  }
  const missing = WANT_CASES.filter((n) => !cases.some((c) => c.name === n));
  ok(!missing.length, 'every case this run expects actually ran',
     JSON.stringify(missing));
  /* And each of them ONCE. A duplicate name means the page's own run on load and this
     re-run overlapped and pushed into the same list, which quietly merges cases
     measured before the viewport override with cases measured after it. */
  const seen = new Set();
  const twice = cases.filter((c) => {
    if (seen.has(c.name)) return true;
    seen.add(c.name);
    return false;
  });
  ok(cases.length === WANT_CASES.length && !twice.length,
     'exactly the ' + WANT_CASES.length + ' cases, each reported once, all from one run',
     cases.length + ' reported' +
     (twice.length ? ', duplicated: ' + JSON.stringify(twice.map((c) => c.name)) : ''));
  ok(verdict.total === cases.length && verdict.pass + verdict.failed.length ===
     verdict.total, 'the verdict adds up', JSON.stringify(verdict));

  /* THE TITLE IS THE CONTRACT. It carries the count, one word for the whole run and
     PASS or FAIL for each case by name, so a script needs nothing but this string. */
  const title = await page.evaluate('document.title');
  verdictLine = title;
  ok(/^PROBE \d+\/\d+ (PASS|FAIL) · /.test(title),
     'the page title carries the verdict a script can read', title);
  const named = WANT_CASES.filter((n) => title.includes(n + ':PASS') ||
                                         title.includes(n + ':FAIL'));
  ok(named.length === WANT_CASES.length,
     'with PASS or FAIL in it for every case by name',
     JSON.stringify(WANT_CASES.filter((n) => !named.includes(n))));
  ok(title.includes(verdict.failed.length ? 'FAIL' : 'PASS') &&
     title.startsWith('PROBE ' + verdict.pass + '/' + verdict.total),
     'and the title agrees with the cases underneath it', title);
  ok(await page.evaluate('__galaxy.probe.fetches') === 0,
     'the battery was hermetic: not one request left the page while it ran',
     'fetches: ' + await page.evaluate('__galaxy.probe.fetches'));

  /* ---- 3b. THE MIND, ONE STATE AT A TIME ------------------------------
     The `visage` case above already measures the instrument and it already proves the five
     signatures are distinct - but it reports that as ONE line, and a single boolean covering
     five states is a line that goes red without saying which state broke. So the five are
     walked again from out here and asserted BY NAME, which is what PART 7 asks for: an
     `idle` that had quietly become an `at rest`, or a `locked` that had stopped differing
     from `thinking`, is named in the failure rather than hidden inside `distinct=false`.
     Cheap, because it is five poses and five reads of computed style on a page that is
     already open, and it is the only place in this suite where a state's NAME appears. */
  log('');
  log('-- the Mind: five states, each one named');
  const MIND_STATES = ['idle', 'listening', 'thinking', 'speaking', 'locked'];
  const published = await page.json('__galaxy.face.states');
  ok(Array.isArray(published) && published.length === 5 &&
     MIND_STATES.every((s) => published.includes(s)),
     'the visage publishes exactly the five states the spec names',
     JSON.stringify(published));
  /* Motion stilled first: the signature of a state is its POSE, and a signature read
     halfway through a gimbal's rotation is a reading of the clock. */
  const wasPose = await page.evaluate('__galaxy.face.state');
  /* nomove stills the gimbals - a signature read halfway through a rotation is a reading of
     the clock - and the card is put into its `live` skin because that is the skin the five
     poses are written against. Both are put back at the end of the section. */
  const wasCard = await page.evaluate(
    '(function () { var c = document.getElementById("focuscard"), was = c.className;' +
    ' document.documentElement.classList.add("nomove"); c.className = "live";' +
    ' return was; })()');
  const seenSig = new Map();
  for (const s of MIND_STATES) {
    const r = await page.json('(function () {' +
      'var posed = __galaxy.face.pose(' + JSON.stringify(s) + ');' +
      'var box = document.getElementById("focusface");' +
      'var mini = document.getElementById("cmdmind");' +
      'var lens = box.querySelector(".mlens"), iris = box.querySelector(".miris");' +
      'var spoke = box.querySelector(".mspoke");' +
      'return {posed: posed, state: __galaxy.face.state,' +
      ' homes: __galaxy.face.homes, lit: __galaxy.face.lit,' +
      ' card: box.className, twin: mini ? mini.className : "",' +
      ' lens: getComputedStyle(lens).transform,' +
      ' iris: getComputedStyle(iris).transform,' +
      ' spoke: getComputedStyle(spoke).transform};})()');
    const sig = r.lens + '|' + r.iris + '|' + r.spoke;
    const clash = [...seenSig.entries()].find(([, v]) => v === sig);
    seenSig.set(s, sig);
    ok(r.posed === true && r.state === s && r.homes === 2 &&
       r.card.split(/\s+/).includes(s) && r.twin.split(/\s+/).includes(s) && !clash,
       'the Mind holds ' + s.toUpperCase() + ': both homes wear the pose and it looks ' +
       'like nothing else on the list',
       JSON.stringify({ state: r.state, homes: r.homes, card: r.card, twin: r.twin,
                        clashesWith: clash ? clash[0] : null }));
  }
  ok(new Set(seenSig.values()).size === 5,
     'and so all five are five, measured as aperture and waveform out of computed style ' +
     'rather than taken on trust from the class name',
     JSON.stringify([...seenSig.keys()]));
  await page.evaluate('__galaxy.face.pose(' + JSON.stringify(wasPose) + ')');
  await page.evaluate(
    '(function () { document.getElementById("focuscard").className = ' +
    JSON.stringify(wasCard) + ';' +
    ' document.documentElement.classList.remove("nomove"); })()');

  /* ---- 4. THE OVERLAY -------------------------------------------------- */
  log('');
  log('-- the overlay: ?focusdebug=1 on the glass, reading the running server');

  await page.send('Page.navigate', { url: DEBUG_URL });
  await sleep(500);                         // let the old context go before asking
  ok(await waitForGalaxy(page, 'debug'),
     'the overlay page boots and exposes the debug handle');
  ok(await page.evaluate('__galaxy.debug.on') === true,
     'the debug flag is read from the query string');
  ok(await page.evaluate('__galaxy.debug.shown') === true,
     'and the panel is actually in the document, not merely enabled');
  for (let i = 0; i < 20 && !(await page.evaluate('!!__galaxy.debug.diag')); i++) {
    await sleep(250);
  }
  const shown = await page.json('__galaxy.debug.diag');
  ok(!!shown, 'the overlay has a diag from the server',
     await page.evaluate('__galaxy.debug.trouble'));
  const age = await page.evaluate('__galaxy.debug.ageMs');
  ok(age !== null && age < 3500,
     'and it is fresh rather than a stale frame left on the screen', 'age ' + age + 'ms');
  const text = await page.evaluate('__galaxy.debug.text');
  const wants = ['process', 'tick', 'lanes', 'deferred', 'front', 'pixels', 'session'];
  const absent = wants.filter((w) => !text.includes(w));
  ok(!absent.length, 'it shows the flags, the deferred state, the lanes and the pixels',
     JSON.stringify(absent));
  const overlayLeak = text.match(/[\w-]+\.(exe|com|net|org|io|app|local)\b/i);
  ok(!overlayLeak, 'and nothing on the glass names an app or a site',
     overlayLeak ? overlayLeak[0] : '');
  log('');
  for (const line of text.split('\n').filter(Boolean)) log('  | ' + line);

  /* ---- 5. THE EYES LAW, BOTH WAYS ROUND -------------------------------
     THE METAPHOR NEVER LIES, and there is exactly one way to prove that: open a camera and
     watch the face open its eyes, then close the camera and watch them shut. The `eyeslaw`
     case in the battery asserts the STRUCTURE - one variable, one three-row table, the seal
     and the lid agreeing at one instant - and it can only ever assert it in the closed
     state, because the battery is hermetic and a hermetic battery has no camera. This
     section is the other half, and it is the half that could catch a real bug: a code path
     that opens the camera and paints the seal without waking the eyes, or - far worse - one
     that closes the camera and leaves them open, which is a face watching a room it cannot
     see.
     IT RUNS HERE, AFTER THE OVERLAY, AND FOR ONE REASON: the eyelids are pixels, and the
     hermetic page has none. The presence is built inside the same `else` that keeps the
     probe page off the network, so there the lid is a number nobody draws. The debug page
     section 4 just navigated to is a REAL page - worlds, deck, hologram - so this is where
     the law can be photographed as well as read.
     The camera is Chrome's fake device. No frame of it is read here and nothing in this
     section uploads one; what is being tested is the lid, not the landmarker. */
  log('');
  log('-- the Eyes Law: the camera decides, and one variable carries it');
  /* THE HOLOGRAM BOOTS LAST ON PURPOSE - after the worlds, the flow, the bloom's audition
     and its own - so on a freshly navigated page it is simply not there yet. Waited for by
     name rather than slept at, and the wait is allowed to fail: a machine that cannot build
     it still has a seal and a table to be truthful about, and the assertions below say
     which half they are reading. */
  let presUp = false;
  for (let i = 0; i < 160 && !presUp; i++) {
    presUp = (await page.evaluate('!!(window.__galaxy && __galaxy.presence' +
      ' && __galaxy.presence.built)')) === true;
    if (!presUp) await sleep(250);
  }
  log('   the hologram ' + (presUp ? 'is built and running' : 'never built: ' +
      (await page.evaluate('__galaxy.presence.trouble || __galaxy.presence.why || "?"'))));
  ok(presUp, 'THE HOLOGRAM IS ON THE GLASS on the real page, so the eyelids below are ' +
     'geometry and not just a number - every assertion after this one reads pixels that ' +
     'exist');
  const lidTable = await page.json('__galaxy.eyes.LID');
  ok(lidTable && Object.keys(lidTable).length === 3 && lidTable.shut === 0 &&
     lidTable.sampling === 0.5 && lidTable.watching === 1,
     'THE TABLE HAS THREE ROWS: shut 0, sampling a HALF, watching 1 - the half-lid is a ' +
     'state of its own because "open but not yet seeing" is a real thing the camera does',
     JSON.stringify(lidTable));
  /* FACE by hand, so the plates below are of eyelids rather than of a ring. This is the
     Command Panel's own call and it is allowed to clear a refusal; if the audition stood
     the face down in this headless renderer, the `degraded` line says so in the log. */
  const presWas = await page.json('({built: __galaxy.presence.built,' +
    ' mode: __galaxy.presence.mode, degraded: __galaxy.presence.degraded,' +
    ' points: __galaxy.presence.points, well: __galaxy.presence.well})');
  if (presWas.built) { await page.evaluate('__galaxy.presence.set("face")'); }
  await sleep(1000);
  const wellAt = await page.json('__galaxy.layout.rects.presence');
  log('   the presence: ' + JSON.stringify(presWas) +
      (wellAt ? '  ·  well at ' + JSON.stringify(wellAt) : '  ·  no well on the glass'));

  /* THE CLOSED HALF. The camera has never been opened in this run, so this is the standby
     the spec describes - and it is asserted by name, not by whatever happened to be true. */
  const eyes0 = await page.json('({s: __galaxy.eyes.sight, mode: __galaxy.presence.mode,' +
    ' lid: __galaxy.presence.lid, eye: __galaxy.presence.eye})');
  ok(eyes0.s.state === 'shut' && eyes0.s.live === false && eyes0.s.truth === false &&
     eyes0.s.lid === 0 && eyes0.s.seal.button === false && eyes0.s.seal.chip === false,
     'CAMERA OFF: the variable says "shut", eyesLive() agrees, and both EYES LIVE surfaces ' +
     'are dark', JSON.stringify(eyes0.s));
  ok(eyes0.lid === 0 && eyes0.eye < 0.05 && eyes0.lid === lidTable[eyes0.s.state],
     'AND THE FACE IS NOT LOOKING: the hologram was told lid ' + eyes0.lid +
     ' and its geometry has eased to ' + eyes0.eye + ' - closed-eye geometry, from the ' +
     'same variable and the same table', JSON.stringify(eyes0));
  if (wellAt) {
    await page.shot('focus-eyes-shut.png', wellAt);
    log('   wrote focus-eyes-shut.png (' + eyes0.mode + ' mode, camera off, eyes closed)');
  }

  /* THE OPEN HALF. start() is the organ's own door - the same one the #eye button calls. */
  const camUp = await page.evaluate('__galaxy.eyes.start()');
  await sleep(2600);                       // past the 420ms wake blink and the lid's ease
  const eyes1 = await page.json('({s: __galaxy.eyes.sight, reader: __galaxy.eyes.reader,' +
    ' lid: __galaxy.presence.lid, eye: __galaxy.presence.eye,' +
    ' dim: document.getElementById("eye-dim").textContent})');
  log('   camera up: ' + JSON.stringify(eyes1));
  ok(camUp === true && eyes1.s.live === true && eyes1.s.truth === true &&
     eyes1.s.state !== 'shut',
     'CAMERA ON: the fake device opened and the variable moved to "' + eyes1.s.state +
     '" - ' + (eyes1.s.state === 'watching'
       ? 'a baseline was measured, so the eyes are fully open'
       : 'the landmarkers are still waking, so the eyes are HALF open, which is the ' +
         'third state earning its keep'),
     JSON.stringify(eyes1.s));
  ok(eyes1.s.seal.button === true && eyes1.s.seal.chip === true,
     'and the EYES LIVE seal lit in the same breath - one variable, two surfaces, ' +
     'asserted together rather than one at a time', JSON.stringify(eyes1.s.seal));
  ok(eyes1.lid === lidTable[eyes1.s.state] && eyes1.lid >= 0.5,
     'THE EYES ARE OPEN: lid ' + eyes1.lid + ' for state "' + eyes1.s.state +
     '", straight off the same table the seal is read through', JSON.stringify(eyes1));
  ok(eyes1.eye >= eyes1.lid * 0.6,
     'and THE GEOMETRY FOLLOWED rather than merely being asked to: the eased eye stands ' +
     'at ' + eyes1.eye + ' against a target of ' + eyes1.lid,
     JSON.stringify({ eye: eyes1.eye, lid: eyes1.lid }));
  ok(eyes1.s.opens === eyes0.s.opens + 1 && eyes1.s.blinks === eyes0.s.blinks + 1 &&
     eyes1.s.changes > eyes0.s.changes,
     'AND IT BLINKED ON WAKING: ' + eyes1.s.opens + ' open, ' + eyes1.s.blinks +
     ' blink - a face that blinked idly would be pretending; this one blinks on a transition',
     JSON.stringify({ before: { opens: eyes0.s.opens, blinks: eyes0.s.blinks },
                      after: { opens: eyes1.s.opens, blinks: eyes1.s.blinks } }));
  if (wellAt) {
    await page.shot('focus-eyes-open.png', wellAt);
    log('   wrote focus-eyes-open.png (camera on, state "' + eyes1.s.state + '", lid ' +
        eyes1.lid + ')');
  }

  /* AND CLOSED THE INSTANT THE CAMERA RELEASES. Read with no sleep at all first: the
     variable and the seal must already have moved when stop() returns, because "the instant"
     is the word in the spec and a 200ms lag is a face still looking at a dark room. */
  await page.evaluate('__galaxy.eyes.stop()');
  const atOnce = await page.json('({s: __galaxy.eyes.sight, lid: __galaxy.presence.lid})');
  ok(atOnce.s.state === 'shut' && atOnce.s.live === false && atOnce.s.truth === false &&
     atOnce.s.lid === 0 && atOnce.s.seal.button === false && atOnce.s.seal.chip === false,
     'THE INSTANT THE CAMERA RELEASES, with no waiting at all: state "shut", eyesLive() ' +
     'agreeing, the table\'s lid back to 0 and both seal surfaces dark - one call moved ' +
     'all four', JSON.stringify(atOnce.s));
  /* AND THE HOLOGRAM ON THE VERY NEXT FRAME. The lid the shader is given is written by the
     frame loop, so at the instant above it is still whatever the last painted frame was
     told - which is not a lag in the law, it is the difference between a variable and a
     picture of it. ONE frame is the whole allowance, and it is measured rather than slept
     through: two rAFs and the target must already be 0, with only the ease left to travel. */
  /* evaluate() rather than json(), because json() wraps the expression in JSON.stringify -
     which would stringify the PROMISE and hand back an empty object. returnByValue awaits it
     and brings the resolved object across as it is. */
  const nextFrame = await page.evaluate(
    'new Promise(function (go) { requestAnimationFrame(function () {' +
    ' requestAnimationFrame(function () { go({lid: __galaxy.presence.lid,' +
    ' eye: __galaxy.presence.eye, state: __galaxy.eyes.sight.state}); }); }); })');
  ok(nextFrame.lid === 0 && nextFrame.state === 'shut',
     'and THE FACE WAS TOLD WITHIN ONE FRAME: the lid the shader is handed read ' +
     atOnce.lid + ' at the instant of the call and ' + nextFrame.lid + ' one frame later, ' +
     'with the eased geometry at ' + nextFrame.eye + ' and still travelling',
     JSON.stringify({ atCall: atOnce.lid, nextFrame: nextFrame }));
  await sleep(1400);
  const eyes2 = await page.json('({s: __galaxy.eyes.sight, lid: __galaxy.presence.lid,' +
    ' eye: __galaxy.presence.eye, mode: __galaxy.presence.mode})');
  ok(eyes2.eye < 0.12 && eyes2.lid === 0,
     'and the eyelids CLOSED rather than snapped: the geometry eased back to ' + eyes2.eye +
     ' over the blink', JSON.stringify(eyes2));
  ok(eyes2.s.closes === eyes0.s.closes + 1 && eyes2.s.blinks === eyes0.s.blinks + 2,
     'with a SLOW BLINK ON CLOSING too: ' + eyes2.s.closes + ' close, ' + eyes2.s.blinks +
     ' blinks for one open and one close and nothing in between',
     JSON.stringify(eyes2.s));
  ok(await page.evaluate('__galaxy.eyes.on') === false &&
     await page.evaluate('__galaxy.eyes.indicator') === false,
     'and NOTHING IS LEFT WATCHING: the track is released and the violet chip is out');
}

function teardown() {
  for (const proc of browsers) {
    try { process.kill(-proc.pid); } catch { /* already gone */ }
    try { proc.kill(); } catch { /* already gone */ }
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
  if (verdictLine) console.log('\n  ' + verdictLine);
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
