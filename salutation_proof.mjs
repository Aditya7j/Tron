/* THE ADDRESS, and what a greeting is allowed to cost.
 *
 * "hello good morning Jarvis" used to be a substantial question. Every pleasantry peeled
 * away and the assistant's own NAME was left standing as a content word - so a salutation
 * scored nothing against the notes, fell through the thin-score trigger, lit the LIVE WEB
 * panel and spent a real search on DuckDuckGo asking who Jarvis is. Saying good morning
 * cost money.
 *
 * Two claims here, and they pull against each other, which is the only reason this file
 * is worth running:
 *
 *   NOTHING LEFT, NOTHING SPENT. "hello good morning Jarvis" and "good morning" must cost
 *     EXACTLY the same - the same kind, the same absent fields, the same still galaxy, and
 *     zero lookups in the server's own log. Not "nearly the same": the reply shapes are
 *     compared key for key.
 *
 *   THE VETO IS ON THE ADDRESS, NEVER ON THE WORD. "who is JARVIS in the movies?" keeps
 *     who, JARVIS and movies, reaches the web exactly as before, and comes back cited to
 *     the Marvel Cinematic Universe. A guard that silenced the word rather than the
 *     address would pass the first claim and fail this one, silently, forever.
 *
 * The log is read off disk rather than inferred, because "zero searches" is a claim about
 * what the server DID, and the absence of a line in a file you never opened proves nothing.
 * The server prints a positive line for a declined lookup - "no lookup: ... nothing asked"
 * - so both halves are readable.
 *
 * Headless; nothing mocked; one real search at the end.
 *
 * Usage:  python server.py 2> server-trace.log   then   node salutation_proof.mjs
 */
import { spawn } from 'node:child_process';
import { mkdtempSync, rmSync, existsSync, readFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const GALAXY = 'http://127.0.0.1:4700';
const VIEW = GALAXY + '/?mute=1';
const PORT = 9228;
const CDP = 'http://127.0.0.1:' + PORT;
/* The server's stderr, which is where the lookup trace goes. Start the server with
   `python server.py 2> server-trace.log` and this finds it with no argument at all. */
const LOG = (process.argv[2] || 'server-trace.log').replace(/^--log=/, '');
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
      const bomb = setTimeout(() => { this.w.delete(id); rej(new Error(method + ' timed out')); }, 20000);
      this.w.set(id, (m) => { clearTimeout(bomb); res(m); });
      this.ws.send(JSON.stringify({ id, method, params: params || {} })); }); }
  async evaluate(expression) {
    const r = await this.send('Runtime.evaluate',
      { expression, returnByValue: true, awaitPromise: true });
    if (r.result && r.result.exceptionDetails) {
      throw new Error('page threw: ' + r.result.exceptionDetails.text);
    }
    return r.result && r.result.result ? r.result.result.value : undefined;
  }
  async json(e) { return JSON.parse(await this.evaluate('JSON.stringify(' + e + ')') || 'null'); }
  close() { try { this.ws.close(); } catch { } }
}
const cdp = async (p) => { const r = await fetch(CDP + p); const t = await r.text();
  try { return JSON.parse(t); } catch { return t; } };

async function waitFor(page, expr, ms = 8000) {
  for (let i = 0; i < ms / 200; i++) {
    try { if (await page.evaluate(expr)) return true; } catch { }
    await sleep(200);
  }
  return false;
}

const TAP = `(function () {
  if (window.__tap) return 'already';
  window.__tap = [];
  var real = window.fetch.bind(window);
  window.fetch = function (url, init) {
    return real(url, init).then(function (res) {
      if (String(url).indexOf('/chat') >= 0) {
        var copy = res.clone();
        copy.json().then(function (d) { window.__tap.push(d); }).catch(function () { });
      }
      return res;
    });
  };
  return 'wrapped';
})()`;

/* What the SCREEN shows after a turn, which is where "no sources panel" lives: the panel's
   own classes, the card's chips, and whether anything in the galaxy is selected. */
const SCREEN = `(function () {
  var p = document.getElementById('panel');
  return {
    panelOpen: p.classList.contains('open'),
    panelWeb: p.classList.contains('web'),
    panelLabel: document.getElementById('p-label').textContent,
    chips: document.getElementById('a-chips').children.length,
    src: document.getElementById('a-src').textContent.trim(),
    answer: document.getElementById('a-text').textContent.trim(),
    card: document.getElementById('a-q').textContent,
    selected: __galaxy.selected === null || __galaxy.selected === undefined ? 0 : 1
  };
})()`;

async function turn(page, question, budget = 120000) {
  const before = await page.evaluate('window.__tap.length');
  await page.evaluate('__galaxy.ask(' + JSON.stringify(question) + ')');
  if (!await waitFor(page, 'window.__tap.length > ' + before, budget)) {
    throw new Error('no reply to ' + JSON.stringify(question));
  }
  await sleep(900);
  return { got: await page.json('window.__tap[window.__tap.length-1]'),
           screen: await page.json(SCREEN) };
}

const readLog = () => (LOG && existsSync(LOG)) ? readFileSync(LOG, 'utf8') : null;
const lookups = (text) => (text === null ? null
  : (text.match(/^ *web lookup /gm) || []).length);
const shape = (o) => Object.keys(o).sort().join(',');

const profiles = []; const procs = [];
async function main() {
  console.log('\n  the address: a greeting costs nothing, the word still travels\n');
  const exe = CHROMES.find((p) => existsSync(p));
  if (!exe) throw new Error('no chrome.exe');
  if (!LOG) note('no server log path given; the lookup-count checks will be skipped');
  else if (!existsSync(LOG)) note('log path does not exist: ' + LOG);

  const profile = mkdtempSync(join(tmpdir(), 'salutation-'));
  profiles.push(profile);
  procs.push(spawn(exe, ['--headless=new', '--remote-debugging-port=' + PORT,
    '--user-data-dir=' + profile, '--no-first-run', '--no-default-browser-check',
    '--window-size=1280,900', VIEW], { detached: true, stdio: 'ignore' }));
  for (let i = 0; i < 80; i++) { try { await cdp('/json/version'); break; } catch { await sleep(250); } }
  let target = null;
  for (let i = 0; i < 40; i++) {
    const l = await cdp('/json/list');
    target = (Array.isArray(l) ? l : []).filter(t => t.type === 'page').find(t => t.url.includes('mute=1'));
    if (target) break; await sleep(300);
  }
  if (!target) throw new Error('no viewer page');
  const page = new Page(target.webSocketDebuggerUrl);
  await page.open();
  await page.send('Runtime.enable');
  ok(await waitFor(page, '!!(window.__galaxy && window.__galaxy.ask)', 30000),
     'the viewer is up and will take a question');
  await waitFor(page, '__galaxy.nodes.length > 0', 20000);
  await page.evaluate(TAP);
  await page.evaluate('document.getElementById("reset").click()');
  await sleep(700);

  const before = lookups(readLog());

  /* ---- 1. the salutation with the name in it ----------------------------- */
  const long = await turn(page, 'hello good morning Jarvis');
  note('1: ' + JSON.stringify(long.got.answer).slice(0, 96));
  ok(long.got.kind === 'chat', 'kind is chat: the address was peeled, not searched',
     JSON.stringify({ kind: long.got.kind, searched: long.got.searched }));
  ok(!('sources' in long.got) && !('searched' in long.got) && !('searchedFor' in long.got),
     'the reply carries no sources, no searched, no searchedFor - nothing was spent',
     shape(long.got));
  ok(Array.isArray(long.got.nodes) && long.got.nodes.length === 0,
     'and no note indexes, so the galaxy cannot move');
  ok(!long.screen.panelOpen && !long.screen.panelWeb,
     'THE LAW: the LIVE WEB panel did not light',
     JSON.stringify({ open: long.screen.panelOpen, web: long.screen.panelWeb }));
  ok(long.screen.chips === 0 && long.screen.selected === 0,
     'no chips, nothing selected: the camera held',
     JSON.stringify({ chips: long.screen.chips, selected: long.screen.selected }));
  ok(/sir|morning|disposal|good/i.test(long.screen.answer) && long.screen.answer.length > 20,
     'and it is a butler greeting, spoken back: ' + JSON.stringify(long.screen.answer.slice(0, 60)));

  /* ---- 2. the same greeting without the address -------------------------- */
  const short = await turn(page, 'good morning');
  note('2: ' + JSON.stringify(short.got.answer).slice(0, 96));
  ok(short.got.kind === 'chat', 'kind is chat here too');
  ok(shape(short.got) === shape(long.got),
     'NOTHING LEFT, NOTHING SPENT: the two replies have the same fields, key for key',
     JSON.stringify({ withName: shape(long.got), without: shape(short.got) }));
  ok(!short.screen.panelOpen && !short.screen.panelWeb && short.screen.chips === 0,
     'the same still screen: no panel, no chips');

  const after = lookups(readLog());
  if (before === null || after === null) note('skipped the lookup count: no readable log');
  else {
    ok(after === before,
       'ZERO lookups in the server log across both greetings (still ' + after + ')',
       'before=' + before + ' after=' + after);
    const log = readLog();
    ok(/no lookup: 'hello good morning Jarvis' is greeting and address/.test(log) &&
       /no lookup: 'good morning' is greeting and address/.test(log),
       'and the log SAYS it declined, for each of them, rather than staying silent');
    ok(!/AND YET THE GATE OPENED/.test(log),
       'no salutation opened the gate - the leak detector never fired');
  }

  /* ---- 3. and the word itself, which is not an address ------------------- */
  const real = await turn(page, 'who is JARVIS in the movies?');
  const srcs = (real.got.sources || []).map(s => (s.title || '') + ' ' + (s.url || ''));
  note('3: ' + JSON.stringify(real.got.answer).slice(0, 110));
  srcs.forEach(s => note('   source: ' + s.slice(0, 96)));
  ok(real.got.kind === 'web' && real.got.searched === 'thin',
     'REAL QUESTIONS ABOUT THE NAME STILL TRAVEL: kind=web, searched=thin',
     JSON.stringify({ kind: real.got.kind, searched: real.got.searched }));
  ok(real.got.searchedFor === 'who is JARVIS in the movies?',
     'and it went out as asked, address peel and all: ' + JSON.stringify(real.got.searchedFor));
  ok(srcs.length > 0 && srcs.some(s => /marvel|mcu|stark|bettany|avengers|fandom|wikipedia/i.test(s)),
     'cited to the Marvel films, ' + srcs.length + ' sources', JSON.stringify(srcs));
  ok(real.screen.panelOpen && real.screen.panelWeb,
     'NOW the LIVE WEB panel lights - for a question, never for a greeting',
     JSON.stringify(real.screen));
  ok(real.screen.panelLabel === 'who is JARVIS in the movies?',
     'and the panel quotes the question as asked', JSON.stringify(real.screen.panelLabel));
  const end = lookups(readLog());
  if (end !== null && before !== null) {
    ok(end === before + 1, 'exactly one lookup in the log for the whole run: this one',
       'before=' + before + ' end=' + end);
  }
  page.close();
}

main().catch((e) => { bad.push('the run itself: ' + e.message); console.log('\n  ERROR ' + e.message); })
  .finally(async () => {
    procs.forEach(p => { try { process.kill(p.pid); } catch { } });
    await sleep(600);
    profiles.forEach(p => { try { rmSync(p, { recursive: true, force: true }); } catch { } });
    console.log('\n  VERIFY ' + (checks - bad.length) + '/' + checks +
                (bad.length ? ' FAIL' : ' PASS') + '\n');
    bad.forEach(b => console.log('    FAILED: ' + b));
    process.exit(bad.length ? 1 : 0);
  });
