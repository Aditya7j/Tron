/* THE REWRITER, and THE LAW it is not allowed to break.
 *
 * The complaint was concrete: ask "what is react", follow up with "who created it?", and
 * the search went out with the pronoun still in it - so the web answered about the man who
 * created the World Wide Web. A follow-up has to inherit its predecessor's subject BEFORE
 * the search is fired, and it has to do so without ever putting a word in the employer's
 * mouth.
 *
 * Those two halves pull in opposite directions, which is why this runs in a real browser
 * against a real search rather than in the hermetic battery: the thing being proved is that
 * ONE sentence goes out to DuckDuckGo while a DIFFERENT sentence stays on the screen, and
 * both of those are observable facts about a running system.
 *
 * The sequence, once, nothing mocked:
 *
 *   ask "what is react"           -> a web answer; the memory now holds that question
 *   ask "who created it?"         -> the card and the sources panel quote "who created it?"
 *                                    the reply's searchedFor says "who created react"
 *                                    the sources are Walke / Facebook / react.dev, and
 *                                    Tim Berners-Lee is nowhere in them
 *                                 -> and the SERVER's own trace log says the same thing,
 *                                    read off disk, because the log is what a human would
 *                                    check at three in the morning
 *   press the real ↻ button       -> the conversation is forgotten, memory included
 *   ask "who created it?" again   -> searchedFor is the pronoun, verbatim, unrewritten
 *
 * The last step is the one that keeps the feature honest. A rewriter with nothing to
 * inherit from must search what it was given; inventing a subject out of an empty memory
 * would be worse than the bug this fixes.
 *
 * Headless, because nothing here is about a window. It reads the server's trace from
 * server-trace.log, or from a path given as argv[2]; with no readable log every check
 * still runs except the two that quote it.
 *
 * Usage:  python server.py 2> server-trace.log   then   node followup_proof.mjs
 */
import { spawn } from 'node:child_process';
import { mkdtempSync, rmSync, existsSync, readFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const GALAXY = 'http://127.0.0.1:4700';
const VIEW = GALAXY + '/?mute=1';
const PORT = 9227;
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
const cdp = async (p) => { const r = await fetch(CDP + p); const t = await r.text();
  try { return JSON.parse(t); } catch { return t; } };

async function waitFor(page, expr, ms = 8000) {
  for (let i = 0; i < ms / 200; i++) {
    try { if (await page.evaluate(expr)) return true; } catch { }
    await sleep(200);
  }
  return false;
}

/* Every /chat reply the PAGE received, recorded by wrapping fetch rather than by asking
   the server again: the claim is about what the viewer was told and what it then chose to
   display, so a second identical request would be answering a different question. */
const TAP = `(function () {
  if (window.__tap) return 'already';
  window.__tap = [];
  var real = window.fetch.bind(window);
  window.fetch = function (url, init) {
    var body = init && init.body ? String(init.body) : '';
    return real(url, init).then(function (res) {
      var path = String(url);
      if (path.indexOf('/chat') >= 0 || path.indexOf('/reset') >= 0) {
        var copy = res.clone();
        copy.json().then(function (d) {
          window.__tap.push({ path: path, sent: body, got: d });
        }).catch(function () { });
      }
      return res;
    });
  };
  return 'wrapped';
})()`;

/* One turn, the way a hand does it: put it in ask() and wait for the page's own reply
   counter to move. The card is read AFTER that, so there is no race with rendering. */
async function turn(page, question, budget = 120000) {
  const before = await page.evaluate('window.__tap.filter(function(t){return t.path.indexOf("/chat")>=0}).length');
  await page.evaluate('__galaxy.ask(' + JSON.stringify(question) + ')');
  const got = await waitFor(page,
    'window.__tap.filter(function(t){return t.path.indexOf("/chat")>=0}).length > ' + before, budget);
  if (!got) throw new Error('no reply to ' + JSON.stringify(question) + ' within ' + budget + 'ms');
  await sleep(600);
  return page.json('(function(){var c=window.__tap.filter(function(t){' +
    'return t.path.indexOf("/chat")>=0});var last=c[c.length-1];return {' +
    'sent: JSON.parse(last.sent).question, got: last.got,' +
    'card: document.getElementById("a-q").textContent,' +
    'panel: document.getElementById("p-label").textContent};})()');
}

const logSays = (re) => {
  if (!LOG || !existsSync(LOG)) return null;
  return re.test(readFileSync(LOG, 'utf8'));
};

const profiles = []; const procs = [];
async function main() {
  console.log('\n  the rewriter: one sentence out, another on the screen\n');
  const exe = CHROMES.find((p) => existsSync(p));
  if (!exe) throw new Error('no chrome.exe');
  if (!LOG) note('no server log path given; the two log checks will be skipped');
  else if (!existsSync(LOG)) note('log path does not exist: ' + LOG);

  const profile = mkdtempSync(join(tmpdir(), 'followup-'));
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

  /* A clean slate first, through the same button the last act uses - so the run does not
     inherit a subject from whatever was asked before it started. */
  await page.evaluate('document.getElementById("reset").click()', true);
  await sleep(800);

  /* ---- 1. the predecessor ------------------------------------------------ */
  const first = await turn(page, 'what is react');
  note('1: ' + JSON.stringify(first.got.searchedFor) + ' -> kind=' + first.got.kind);
  ok(first.got.kind === 'web' && first.got.searchedFor === 'what is react',
     'the first question went out as itself: ' + JSON.stringify(first.got.searchedFor),
     JSON.stringify({ kind: first.got.kind, searchedFor: first.got.searchedFor }));
  ok(!first.got.rewrote, 'and nothing was rewritten - there was nothing to inherit');

  /* ---- 2. the bare follow-up: two sentences, two places ------------------ */
  const second = await turn(page, 'who created it?');
  const sent = String(second.got.searchedFor || '');
  const srcs = (second.got.sources || []).map(s => (s.title || '') + ' ' + (s.url || ''));
  note('2: asked ' + JSON.stringify(second.sent) + ', searched ' + JSON.stringify(sent) +
       ' [' + (second.got.rewrote || 'verbatim') + ']');
  srcs.forEach(s => note('   source: ' + s.slice(0, 96)));

  ok(second.card === '\u201cwho created it?\u201d',
     'THE LAW, on the card: it quotes the employer word for word',
     JSON.stringify(second.card));
  ok(second.panel === 'who created it?',
     'THE LAW, in the sources panel: the same words again, not the rewrite',
     JSON.stringify(second.panel));
  ok(!/react/i.test(second.card) && !/react/i.test(second.panel),
     'nothing on the screen claims they said "React"');

  ok(/\breact\b/i.test(sent),
     'THE REWRITE: the query that left the machine names React',
     'searchedFor=' + JSON.stringify(sent));
  ok(!/\b(it|its|it\u2019s)\b/i.test(sent),
     'and the pronoun is gone from it, which is the whole complaint',
     'searchedFor=' + JSON.stringify(sent));
  ok(second.got.rewrote === 'quick' || second.got.rewrote === 'heuristic',
     'the reply says how it was rewritten: ' + JSON.stringify(second.got.rewrote));
  ok(sent !== second.sent,
     'so the sentence searched is NOT the sentence asked - by design',
     JSON.stringify({ asked: second.sent, searched: sent }));

  ok(srcs.length > 0 && srcs.some(s => /walke|facebook|react\.dev|react/i.test(s)),
     'the ' + srcs.length + ' sources are about React',
     JSON.stringify(srcs));
  ok(!srcs.some(s => /berners|world wide web|w3\.org/i.test(s)),
     'and Tim Berners-Lee is nowhere among them - the old wrong answer is gone',
     JSON.stringify(srcs.filter(s => /berners|world wide web|w3\.org/i.test(s))));

  /* ---- 3. and the log a human would actually read ------------------------ */
  const traced = logSays(/web lookup \([^)]*\) '[^']*react[^']*' \[(quick|heuristic) rewrite of 'who created it\?'\]/i);
  if (traced === null) note('skipped the log checks: no readable log');
  else {
    ok(traced === true,
       'the server trace log shows the rewritten query and what it was a rewrite OF');
    ok(logSays(/a bare follow-up: 'who created it\?' after 'what is react'/) === true,
       'and names the predecessor it inherited from');
  }

  /* ---- 4. the ↻ button, pressed, and a follow-up with no history --------- */
  const box = await page.json(
    '(function(){var r=document.getElementById("reset").getBoundingClientRect();' +
    'return {x:Math.round(r.left+r.width/2),y:Math.round(r.top+r.height/2)};})()');
  for (const type of ['mousePressed', 'mouseReleased']) {
    await page.send('Input.dispatchMouseEvent',
      { type, x: box.x, y: box.y, button: 'left', clickCount: 1 });
  }
  const forgot = await waitFor(page,
    'window.__tap.some(function(t){return t.path.indexOf("/reset")>=0 && t.got && t.got.ok})', 8000);
  ok(forgot, 'the \u21bb button was pressed and the server confirmed the forgetting');

  const third = await turn(page, 'who created it?');
  const again = String(third.got.searchedFor || '');
  note('3: searched ' + JSON.stringify(again) + ' [' + (third.got.rewrote || 'verbatim') + ']');
  ok(again === 'who created it?' || again === 'who created it',
     'with the memory cleared the SAME follow-up is searched VERBATIM',
     'searchedFor=' + JSON.stringify(again));
  ok(!third.got.rewrote,
     'no rewrite is claimed, because there was nothing to inherit',
     JSON.stringify(third.got.rewrote));
  ok(!/\breact\b/i.test(again),
     'and no subject was invented out of an empty memory',
     'searchedFor=' + JSON.stringify(again));
  ok(third.card === '\u201cwho created it?\u201d',
     'the card still quotes them, rewrite or no rewrite', JSON.stringify(third.card));
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
