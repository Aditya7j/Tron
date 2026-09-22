/* The layout governor, and the retirement, against a real browser at a real size.
 *
 * Every other check on these two lives in the hermetic battery, where the panel is opened
 * by a class and the eight seconds are read off a timer. That is enough to prove the
 * arithmetic and not enough to prove the FEATURE: the thing being fixed here was a
 * screenshot - a card sitting on a note's title, a spoken report burying the panel's
 * Connected chips - and a screenshot is about a real note, in a real panel, at a real
 * window size, with a real report in the toast.
 *
 * So this is the sequence in order, once, with nothing mocked:
 *
 *   open a note panel  ->  start a session BY VOICE (no gesture, so the card stays
 *   in the page)  ->  the card must sit LEFT of the panel edge and the note's title
 *   must be readable  ->  end the session and let it report  ->  the toast must stop
 *   at the panel edge with every Connected chip legible  ->  wait eight seconds  ->
 *   the card retires and the panel is still whole  ->  press FOCUS  ->  the desktop
 *   card takes over, the in-page card vanishes, and the floating window is sized for
 *   the card that is actually in it
 *
 * Rectangles are compared to EACH OTHER, never to a constant, so every check here
 * survives a change to LAYOUT. And the panel is checked against the viewport rather
 * than against a rectangle read four seconds earlier: Chrome's own furniture can gain
 * or lose an infobar mid-run - this run has watched innerHeight move by 58px - and a
 * check that compares absolute pixels across that is asserting about Chrome.
 *
 * It runs HEADED and at 1280x860: a Document PiP window is an OS window, and there is
 * no OS window in headless Chrome. A window will appear in the corner of your screen.
 *
 * One honest cost, stated because it is real: this finishes a one-minute session, which
 * writes ONE row to focus-ledger.json. A report is the thing being watched and abort does
 * not produce one. It stands down without touching anything if a session of yours is
 * already running.
 *
 * Usage:  node layout_proof.mjs        (server.py must be running on 4700)
 */
import { spawn } from 'node:child_process';
import { mkdtempSync, rmSync, existsSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const GALAXY = 'http://127.0.0.1:4700';
const VIEW = GALAXY + '/?mute=1';
const PORT = 9226;
const CDP = 'http://127.0.0.1:' + PORT;
const W = 1280, H = 860;
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
      const bomb = setTimeout(() => { this.w.delete(id); rej(new Error(method + ' timed out')); }, 15000);
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
const post = (p, b) => fetch(GALAXY + p, { method: 'POST',
  headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(b) }).then(r => r.json());

async function waitFor(page, expr, ms = 8000) {
  for (let i = 0; i < ms / 200; i++) {
    try { if (await page.evaluate(expr)) return true; } catch { }
    await sleep(200);
  }
  return false;
}

const profiles = []; const procs = [];
async function main() {
  const exe = CHROMES.find((p) => existsSync(p));
  if (!exe) throw new Error('no chrome.exe');
  const st0 = (await (await fetch(GALAXY + '/focus')).json()).focus;
  if (['arming', 'running', 'paused'].includes(st0.state)) {
    note('a session is already running; standing down'); return;
  }
  const profile = mkdtempSync(join(tmpdir(), 'gov-verify-'));
  profiles.push(profile);
  procs.push(spawn(exe, ['--remote-debugging-port=' + PORT, '--user-data-dir=' + profile,
    '--no-first-run', '--no-default-browser-check', '--window-size=' + W + ',' + H, VIEW],
    { detached: true, stdio: 'ignore' }));
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
  await page.send('Page.bringToFront');
  ok(await waitFor(page, '!!(window.__galaxy && window.__galaxy.layout)', 30000),
     'the viewer is up and exposes the layout governor');

  /* ---- 1. a real note panel ------------------------------------------- */
  await waitFor(page, '__galaxy.nodes.length > 0', 20000);
  await page.evaluate('__galaxy.focus(__galaxy.nodes[0].id,true)');
  await sleep(700);
  const title = await page.evaluate('document.getElementById("p-label").textContent');
  const open = await page.json('__galaxy.layout.last');
  ok(open.panelOpen === true, 'a note panel is open: "' + title + '"', JSON.stringify(open));

  /* ---- 2. a session by VOICE: no gesture, so the card stays in-page ---- */
  await page.evaluate('__galaxy.session.start(1)');
  ok(await waitFor(page, '__galaxy.session.live', 8000), 'the session started by voice');
  await sleep(600);
  const home = await page.json('({out:__galaxy.session.desk.out,inPage:__galaxy.session.desk.inPage})');
  ok(!home.out && home.inPage, 'and with no gesture the card stayed in the page',
     JSON.stringify(home));

  const r1 = await page.json('__galaxy.layout.rects');
  const titleBox = await page.json(
    '(function(){var t=document.getElementById("p-label");if(!t)return null;' +
    'var r=t.getBoundingClientRect();' +
    'return {left:Math.round(r.left),right:Math.round(r.right),top:Math.round(r.top),' +
    'bottom:Math.round(r.bottom),text:t.textContent.trim().slice(0,40)};})()');
  ok(!!r1.focuscard && r1.focuscard.right <= r1.panel.left,
     'THE RESERVED LANE: the card sits LEFT of the panel edge, not on it',
     'card.right=' + (r1.focuscard && r1.focuscard.right) + ' panel.left=' + r1.panel.left);
  if (titleBox) {
    const clear = titleBox.right <= (r1.focuscard ? r1.focuscard.left : 1e9) ||
                  titleBox.left >= (r1.focuscard ? r1.focuscard.right : -1) ||
                  titleBox.bottom <= (r1.focuscard ? r1.focuscard.top : 1e9) ||
                  titleBox.top >= (r1.focuscard ? r1.focuscard.bottom : -1);
    ok(clear, 'and the note title is fully readable: "' + titleBox.text + '"',
       JSON.stringify({ title: titleBox, card: r1.focuscard }));
  } else { note('no panel title element matched; skipping the title rectangle'); }

  /* ---- 3. the report, and the toast that must stop at the panel -------- */
  await page.evaluate('__galaxy.session.end()');
  ok(await waitFor(page, '!__galaxy.session.live', 8000), 'the session ended and reported');
  await sleep(900);
  const r2 = await page.json('__galaxy.layout.rects');
  const spoken = await page.evaluate('document.getElementById("a-text").textContent.slice(0,90)');
  note('report: ' + JSON.stringify(spoken));
  ok(!!r2.brain && r2.brain.right <= r2.panel.left,
     'THE TOAST WIDTH: the report stops at the panel edge',
     'toast.right=' + (r2.brain && r2.brain.right) + ' panel.left=' + r2.panel.left);
  /* The CONNECTED chips are the PANEL's - the neighbours list under its own heading -
     and "legible" means no part of the toast's rectangle is over any of them. */
  const chips = await page.json(
    '(function(){var out=[];var ns=document.querySelectorAll("#p-neighbours .chip,#p-neighbours button,#p-neighbours>*");' +
    'for(var i=0;i<ns.length;i++){var r=ns[i].getBoundingClientRect();if(!r.width)continue;' +
    'out.push({left:Math.round(r.left),right:Math.round(r.right),top:Math.round(r.top),' +
    'bottom:Math.round(r.bottom),text:ns[i].textContent.trim().slice(0,18)});}return out;})()');
  const clearOf = (b) => !r2.brain || b.right <= r2.brain.left || b.left >= r2.brain.right ||
                         b.bottom <= r2.brain.top || b.top >= r2.brain.bottom;
  ok(chips.length > 0 && chips.every(clearOf),
     'and every one of the ' + chips.length + ' CONNECTED chips is legible under it',
     JSON.stringify({ toast: r2.brain, covered: chips.filter(c => !clearOf(c)) }));

  /* ---- 4. eight seconds, and the corpse is carried out ----------------- */
  const armed = await page.json('({retiring:__galaxy.session.desk.retiring,' +
    'retireS:__galaxy.session.desk.retireS,clock:__galaxy.session.clock})');
  ok(armed.retiring === true && armed.retireS === 8,
     'THE RETIREMENT: the report is held, and the timer is armed for 8 s',
     JSON.stringify(armed));
  const t = Date.now();
  const went = await waitFor(page, '__galaxy.session.desk.retired', 14000);
  const took = ((Date.now() - t) / 1000).toFixed(1);
  ok(went && +took >= 7 && +took <= 11,
     'the card retired after ' + took + ' s, holding "' + armed.clock + '" until then');
  await sleep(700);
  const r3 = await page.json('__galaxy.layout.rects');
  ok(r3.focuscard === null, 'the card is gone from the screen',
     JSON.stringify(r3.focuscard));
  /* Against the VIEWPORT, not against the rectangle read four seconds ago: the browser's
     own chrome can gain or lose an infobar mid-run (this one did - innerHeight moved by
     58px), and a check that compares absolute pixels across that is asserting about
     Chrome's furniture rather than about the governor. */
  const view = await page.json('({vw:innerWidth,vh:innerHeight,' +
    'doc:document.documentElement.clientWidth})');
  const p = r3.panel;
  const whole = !!p && p.top === 0 && p.bottom >= view.vh - 2 &&
                p.right >= view.doc - 2 && p.w === r2.panel.w;
  const covered = ['focuscard', 'facecard', 'brain', 'legend'].filter(function (id) {
    const b = r3[id];
    return b && !(b.right <= p.left || b.left >= p.right ||
                  b.bottom <= p.top || b.top >= p.bottom);
  });
  ok(whole && covered.length === 0,
     'and the panel is still whole, on its own edge, with nothing over it',
     JSON.stringify({ panel: p, view: view, covered: covered }));

  /* ---- 5. and then a real press: the desktop card takes over ----------- */
  await page.evaluate(
    '(function(){var b=document.getElementById("focusbtn");' +
    'b.dispatchEvent(new PointerEvent("pointerdown",{bubbles:true,cancelable:true}));})()', true);
  await sleep(200);
  await page.evaluate('document.getElementById("focusbtn").click()', true);
  ok(await waitFor(page, '__galaxy.session.live', 8000),
     'the press started a second session');
  await sleep(1500);
  const out = await page.json('({out:__galaxy.session.desk.out,' +
    'inPage:__galaxy.session.desk.inPage,title:__galaxy.session.desk.title,' +
    'size:__galaxy.session.desk.size,organs:__galaxy.session.desk.organs,' +
    'h:__galaxy.session.desk.h,state:__galaxy.session.state.state,' +
    'clock:__galaxy.session.clock,card:__galaxy.session.card})');
  ok(out.out === true && out.inPage === false,
     'ONE CARD, TWO HOMES: the desktop card took over and the in-page card vanished',
     JSON.stringify(out));
  ok(out.title === 'Jarvis · focus', 'the floating window is its own window, by title',
     JSON.stringify(out.title));
  ok((out.organs || []).indexOf('focuscard') >= 0,
     'and the countdown is actually RENDERED in it, not an empty window',
     JSON.stringify(out));
  ok(Math.abs(out.size[0] - 320) <= 8 && Math.abs(out.size[1] - out.h) <= 46,
     'sized for the card that is in it: ' + JSON.stringify(out.size) + ' for h=' + out.h,
     JSON.stringify(out));
  note('the desktop card holds: [' + (out.organs || []).join(' ') + '] showing ' +
       JSON.stringify(out.clock));
  await post('/focus', { cmd: 'abort' });
  await sleep(900);
  const shut = await page.json('({out:__galaxy.session.desk.out})');
  ok(shut.out === false, 'and aborting closes it at once - no report, no eight seconds');
  page.close();
}

main().catch((e) => { bad.push('the run itself: ' + e.message); console.log('\n  ERROR ' + e.message); })
  .finally(async () => {
    try { await post('/focus', { cmd: 'abort' }); } catch { }
    procs.forEach(p => { try { process.kill(p.pid); } catch { } });
    await sleep(600);
    profiles.forEach(p => { try { rmSync(p, { recursive: true, force: true }); } catch { } });
    console.log('\n  VERIFY ' + (checks - bad.length) + '/' + checks +
                (bad.length ? ' FAIL' : ' PASS') + '\n');
    bad.forEach(b => console.log('    FAILED: ' + b));
    process.exit(bad.length ? 1 : 0);
  });
