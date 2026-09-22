/* The brain swap, driven through both doors in a real browser.
 *
 *   open the chip's menu with a click  ->  click the GPT-6 Astra row and hear the
 *   line the SERVER wrote  ->  go home through the menu's last row  ->  then say
 *   "switch to Astra" into the real speech path and hear a DIFFERENT line  ->  and
 *   check that neither sentence ever contained a slug
 *
 * Why this file exists when test_brain.py already passes: everything below the page
 * can be proved in process, but "the button and the voice say the same kind of thing"
 * is a claim about what a hand and a mouth can get out of this app. So the menu is
 * opened by clicking the chip, the row is clicked rather than called, the spoken
 * sentence goes in through the same function the microphone feeds, and every line
 * this run quotes is read out of the page's own log of what it said.
 *
 * WHAT IS REAL HERE: Chrome, the page, the click, the speech path, the HTTP calls and
 * the server. Nothing is stubbed. The tab is loaded with ?mute=1 - the law for every
 * tab used for testing - so the run is silent; speak() still records every line in
 * __galaxy.speech.said with a flag for whether it reached the speakers, and that log
 * is what the claims below read.
 *
 * WHAT IS CHECKED ELSEWHERE: that each line came out of the curated pool in the right
 * order, and that the ladder below it falls back to a pretty name rather than a slug -
 * test_brain.py reads the pool itself, and preflight check 10 reads both doors over
 * HTTP. This run cares that the two doors reach that machinery at all.
 *
 * The brain is a runtime override, so this run puts it back on the way out and says
 * so. A restart would do the same, which is the point of never writing it to disk.
 *
 * Usage:  node brain_live.mjs        (with server.py already running on 4700)
 */

import { spawn } from 'node:child_process';
import { mkdtempSync, rmSync, existsSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const GALAXY = 'http://127.0.0.1:4700';
const VIEWER = GALAXY + '/?mute=1';
const CDP = 'http://127.0.0.1:9224';       // 9222 is the eyes, 9223 is the watch
const NET_TIMEOUT_MS = 10000;
const WANT = 'openai/gpt-6-astra';
const PRETTY = 'GPT-6 Astra';

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

  /* Fired with void and then polled, never awaited: a swap that is waiting on a
     provider must not be able to block this connection and make a slow run look hung. */
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

async function launch(exe, profile, port) {
  const proc = spawn(exe, [
    '--headless=new',
    '--remote-debugging-port=' + port,
    '--user-data-dir=' + profile,
    '--no-first-run', '--no-default-browser-check',
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
const spoken = [];              // every line this run heard the page say, in order

function freshProfile(tag) {
  const dir = mkdtempSync(join(tmpdir(), 'brain-live-' + tag + '-'));
  profiles.push(dir);
  return dir;
}

async function main() {
  console.log('\n  the brain · both doors, live\n');

  const exe = CHROMES.find((p) => existsSync(p));
  if (!exe) throw new Error('no chrome.exe found in the usual places');

  const health = await galaxy('/health');
  const home = health.brain;
  log('server: ' + health.notes + ' notes · answering with ' + home.label +
      ' from config.json');
  if (home.swapped) {
    note('the server was already on a runtime override when this run started; it ' +
         'will be left on the model config.json names, not on that one');
  }

  const brains = await galaxy('/brains');
  ok(Array.isArray(brains.models) && brains.models.length > 1,
     'the server publishes what it will answer to: ' + brains.models.length +
     ' models, and the menu is built from this');
  const astra = brains.models.find((m) => m.id === WANT);
  ok(astra && astra.pretty === PRETTY,
     'and it publishes a written name for each one, so nothing has to say a slug',
     JSON.stringify(astra));
  /* The four pinned phrases arrive as three keys, and that is the feature: "gpt-6
     astra" and "gpt 6 astra" are one key, because a hyphen is a transcription accident
     and must not be the difference between the right brain and a refusal. */
  const pinned = brains.pinned || [];
  ok(pinned.length >= 3 && pinned.indexOf('astra') >= 0 && pinned.indexOf('gpt 6') >= 0,
     'the spoken forms are pinned in config.json, so a catalogue change cannot ' +
     're-point them: ' + pinned.join(', '),
     JSON.stringify(pinned));

  browsers.push(await launch(exe, freshProfile('main'), 9224));
  const version = await cdp('/json/version');
  log('chrome: ' + version.Browser);
  const page = await attach(9224);
  await sleep(3500);                                  // the viewer's 3D boot

  ok(await page.evaluate('!!window.__galaxy && !!window.__galaxy.brain'),
     'the viewer exposes the brain handle');
  ok(await page.evaluate('__galaxy.speech.muted') === true,
     'the tab was loaded with ?mute=1, so this run is silent and still checkable');
  ok(await page.evaluate('__galaxy.brain.chip') === home.label,
     'the chip opens reading what the SERVER says is answering: ' + home.label);
  ok(await page.evaluate('__galaxy.brain.swappedStyle') === false,
     'and it is not wearing the swapped colour, because nothing has been swapped');

  /* ---- the helpers ----------------------------------------------------- */

  /* Everything the page said since a moment, newest last, whether or not the
     speakers were involved. The page's own log, not a guess from the network. */
  async function saidSince(stamp) {
    const lines = await page.json('__galaxy.speech.said');
    return (lines || []).filter((l) => l.at >= stamp).map((l) => l.text);
  }

  /* Wait for the page to say something new, or give up. A swap is one HTTP call and
     one sentence, so this is short; the model is never asked on a curated line. */
  async function waitForLine(stamp, whatFor, budgetMs = 25000) {
    for (let i = 0; i < budgetMs / 250; i++) {
      const lines = await saidSince(stamp);
      if (lines.length) {
        for (const l of lines) spoken.push(l);
        return lines[lines.length - 1];
      }
      await sleep(250);
    }
    throw new Error('the page said nothing at all after ' + whatFor);
  }

  async function brainNow() {
    return (await galaxy('/health')).brain || {};
  }

  /* ---- 1. THE BUTTON DOOR ---------------------------------------------- */
  log('');
  log('-- the button door: a click on the chip, then a click on a row');

  ok(await page.evaluate('__galaxy.brain.menuOpen') === false,
     'the menu starts shut');
  await page.evaluate('$_ = document.getElementById("brainchip").click()');
  await sleep(700);
  ok(await page.evaluate('__galaxy.brain.menuOpen') === true,
     'clicking the chip opens it: the chip is a button, not a label');

  const rows = await page.json('__galaxy.brain.rows');
  ok(rows.length >= brains.models.length,
     rows.length + ' rows, one for every model the server published plus the way home',
     JSON.stringify(rows));
  ok(rows.some((r) => r.indexOf(PRETTY) >= 0),
     'and one of them reads "' + PRETTY + '", as a person writes it');
  ok(!rows.some((r) => r.indexOf('/') >= 0),
     'no row shows a slug: the menu is in the same voice as everything else',
     JSON.stringify(rows.filter((r) => r.indexOf('/') >= 0)));
  ok(rows[rows.length - 1].toLowerCase().indexOf('back') >= 0,
     'the last row is the way home: "' + rows[rows.length - 1] + '"');

  let stamp = Date.now();
  const clicked = await page.evaluate('__galaxy.brain.click(' +
                                      JSON.stringify(PRETTY) + ')');
  ok(!!clicked, 'the ' + PRETTY + ' row was clicked, by label: "' + clicked + '"');
  const buttonLine = await waitForLine(stamp, 'the row was clicked');
  await sleep(400);

  const after = await brainNow();
  ok(after.model === WANT && after.swapped === true,
     'the server is now answering as ' + WANT + ' (swapped=' + after.swapped + ')',
     JSON.stringify(after.model));
  ok(await page.evaluate('__galaxy.brain.state.model') === WANT,
     'and the page knows it from the server\'s reply, not from what it clicked');
  ok(await page.evaluate('__galaxy.brain.swappedStyle') === true,
     'the chip took the swapped colour');
  ok(await page.evaluate('__galaxy.brain.menuOpen') === false,
     'and the menu shut itself, the way a menu does when you have chosen');

  log('  BUTTON SAID: ' + buttonLine);
  ok(buttonLine.indexOf(PRETTY) >= 0,
     'the line names the new brain the way a person writes it');
  ok(buttonLine.indexOf('/') < 0 && buttonLine.toLowerCase().indexOf('openai') < 0,
     'and reads no slug aloud');

  /* ---- 2. HOME, THROUGH THE SAME MENU ---------------------------------- */
  log('');
  log('-- home again, so that the next swap is a real change');

  await page.evaluate('document.getElementById("brainchip").click()');
  await sleep(600);
  stamp = Date.now();
  const homeRow = await page.evaluate('__galaxy.brain.click("back to")');
  ok(!!homeRow, 'the menu\'s last row goes home: "' + homeRow + '"');
  const homeLine = await waitForLine(stamp, 'the home row was clicked');
  log('  HOME SAID:   ' + homeLine);
  const back = await brainNow();
  ok(back.model === home.model && back.swapped === false,
     'the override is gone and config.json speaks again: ' + back.label);
  ok(homeLine.indexOf('/') < 0,
     'and it says where home is by name, not by slug');

  /* ---- 3. THE VOICE DOOR ----------------------------------------------- */
  log('');
  log('-- the voice door: the same words the microphone would deliver');

  const FINISH_MS = await page.evaluate('__galaxy.speech.FINISH_MS');
  ok(await page.evaluate('__galaxy.brain.isSwap("switch to Astra")') === true,
     'the page recognises "switch to Astra" as a swap rather than a question');
  stamp = Date.now();
  await page.evaluate('__galaxy.speech.feedFinal("switch to Astra")');
  await sleep(FINISH_MS + 400);                    // the pause that ends a sentence
  const voiceLine = await waitForLine(stamp, '"switch to Astra" was spoken');
  log('  VOICE SAID:  ' + voiceLine);

  const afterVoice = await brainNow();
  ok(afterVoice.model === WANT && afterVoice.swapped === true,
     'the spoken sentence landed on the same brain the button did');
  ok(voiceLine.indexOf(PRETTY) >= 0,
     'the line names the new brain the way a person writes it');
  ok(voiceLine.indexOf('/') < 0 && voiceLine.toLowerCase().indexOf('openai') < 0,
     'and reads no slug aloud');

  /* THE DEMONSTRATION. Two doors, two swaps onto the same brain, two different
     sentences - which is what a rotating pool is for and what random.choice() would
     have failed about one time in six. */
  ok(voiceLine !== buttonLine,
     'THE TWO DOORS SAID DIFFERENT LINES',
     'both said: ' + buttonLine);
  console.log('');
  console.log('      by button:  ' + buttonLine);
  console.log('      by voice:   ' + voiceLine);
  console.log('');

  /* ---- 4. nothing in this run ever read a slug out loud ---------------- */
  const dirty = spoken.filter((l) => /\//.test(l) || /openai|anthropic/i.test(l));
  ok(dirty.length === 0,
     'across all ' + spoken.length + ' lines this run heard, not one contains a slug '
     + 'or a vendor name',
     JSON.stringify(dirty));
  const creds = spoken.filter((l) => /sk-|api[_ ]?key|aws|bearer/i.test(l));
  ok(creds.length === 0, 'and nothing that looks like a credential', JSON.stringify(creds));

  /* ---- 5. put it back ------------------------------------------------- */
  log('');
  stamp = Date.now();
  await page.evaluate('__galaxy.speech.feedFinal("go back to your normal brain")');
  await sleep(FINISH_MS + 400);
  const restoredLine = await waitForLine(stamp, '"go back to your normal brain"');
  const end = await brainNow();
  ok(end.model === home.model && end.swapped === false,
     'left on ' + end.label + ', the model config.json names: "' + restoredLine + '"');
  ok(await page.evaluate('__galaxy.brain.chip') === home.label,
     'and the chip agrees, because it only ever moves on the server\'s word');

  page.close();
}

function teardown() {
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
  /* The override is runtime only, but leaving one behind would hand the next thing
     that runs a brain nobody asked for. Belt and braces, over HTTP, in case the run
     fell over before section 5. */
  try {
    const now = (await galaxy('/health')).brain || {};
    if (now.swapped) {
      await fetch(GALAXY + '/model', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ say: 'go back to your normal brain', door: 'curl' }),
        signal: AbortSignal.timeout(NET_TIMEOUT_MS),
      });
      console.log('\n  ' + at() + '  note  the run ended on an override; it has been ' +
                  'put back over HTTP');
    }
  } catch { /* the server is gone, and the override went with it */ }
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
