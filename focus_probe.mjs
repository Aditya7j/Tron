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
import { mkdtempSync, rmSync, existsSync, readFileSync } from 'node:fs';
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
                    'desk-move', 'desk-skin', 'merge', 'stack', 'lane', 'retire',
                    'hermetic'];

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

  close() { try { this.ws.close(); } catch { /* already gone */ } }
}

async function launch(exe, profile, url) {
  const proc = spawn(exe, [
    '--headless=new',
    '--remote-debugging-port=' + PORT,
    '--user-data-dir=' + profile,
    '--no-first-run', '--no-default-browser-check',
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
      ' · jarvis tab ' + (diag.frontIsHome ? 'yes' : 'no') + ' · cdp ' +
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
