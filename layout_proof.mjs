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
 *   must be readable  ->  dictate an intent that cannot be broken, and every line box
 *   of text in the card must lie inside the card's own padded box  ->  put a real
 *   paragraph in the answer toast and shorten the viewport until the two surfaces want
 *   the same pixels: they must not overlap, and the toast must give up WIDTH rather
 *   than position  ->  end the session and let it report  ->  the toast must stop
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
const SHORT = 380;            // the squeezed height that makes the two surfaces collide
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
/* Two rectangles do not overlap, in the form the browser's own coordinates take: touching
   edges are not an overlap, which is why every comparison here is <= and not <. A missing
   rectangle is a surface that is not on screen, and nothing on screen can be covered by
   something that is not. */
const disjoint = (a, b) => !a || !b ||
  a.right <= b.left || a.left >= b.right || a.bottom <= b.top || a.top >= b.bottom;
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

/* THE TIDY CARD, measured rather than eyeballed.
 *
 * The bug this exists for was text leaving its box: a long status line running out
 * past the rounded corner, a dictated intent - which can be a URL, and a URL has no
 * spaces to break at - pushing the card's own edge off the screen. So the claim is
 * not "it looks contained". The claim is arithmetic: for every TEXT NODE in the card,
 * every one of its line rectangles lies inside the card's PADDED box - the card's
 * border box inset by its own computed border and padding, read from the browser, so
 * a change to --cardpad moves the assertion with it rather than falsifying it.
 *
 * Line rectangles and not element rectangles, because an element that wraps has one
 * rectangle per line and it is the LONGEST line that escapes; a bounding box averaged
 * over two lines can sit inside the card while the first line hangs out of it.
 *
 * The tolerance is a real half-pixel matter and not a fudge to make a failure pass:
 * a Range rectangle is a line box, and a line box carries the trailing side-bearing of
 * its last glyph plus - on the uppercase header row - 0.22em of letter-spacing after
 * the final letter, which is ink-free space the layout engine still measures. One
 * pixel of that is not text outside the card. Ten would be.
 */
const TIDY_TOL = 1.5;
const TIDY = `(function () {
  var card = document.getElementById('focuscard');
  if (!card || getComputedStyle(card).display === 'none') return null;
  var cs = getComputedStyle(card), cr = card.getBoundingClientRect();
  var num = function (v) { return parseFloat(v) || 0; };
  var box = {
    left:   cr.left   + num(cs.borderLeftWidth)   + num(cs.paddingLeft),
    right:  cr.right  - num(cs.borderRightWidth)  - num(cs.paddingRight),
    top:    cr.top    + num(cs.borderTopWidth)    + num(cs.paddingTop),
    bottom: cr.bottom - num(cs.borderBottomWidth) - num(cs.paddingBottom)
  };
  var r2 = function (v) { return Math.round(v * 100) / 100; };
  var lines = [], worst = -1e9, placed = [];
  var walk = document.createTreeWalker(card, NodeFilter.SHOW_TEXT, null);
  for (var n; (n = walk.nextNode());) {
    if (!n.nodeValue || !n.nodeValue.trim()) continue;
    var host = n.parentElement;
    if (!host) continue;
    var hs = getComputedStyle(host);
    if (hs.display === 'none' || hs.visibility === 'hidden' || +hs.opacity === 0) continue;
    if (!host.getClientRects().length) continue;
    var label = (host.id || host.tagName.toLowerCase()) + ' "' + n.nodeValue.trim().slice(0, 24) + '"';
    if (hs.position === 'absolute' || hs.position === 'fixed') placed.push(label);
    var rg = document.createRange(); rg.selectNodeContents(n);
    var rs = rg.getClientRects();
    for (var i = 0; i < rs.length; i++) {
      var r = rs[i];
      if (r.width < 0.5 && r.height < 0.5) continue;
      var over = Math.max(box.left - r.left, r.right - box.right,
                          box.top - r.top, r.bottom - box.bottom);
      if (over > worst) worst = over;
      lines.push({ who: label, over: r2(over),
                   rect: [r2(r.left), r2(r.top), r2(r.right), r2(r.bottom)] });
    }
  }
  return {
    box: { left: r2(box.left), right: r2(box.right),
           top: r2(box.top), bottom: r2(box.bottom) },
    cardW: Math.round(cr.width), cardH: Math.round(cr.height),
    pad: [cs.paddingTop, cs.paddingRight, cs.paddingBottom, cs.paddingLeft].join(' '),
    count: lines.length, placed: placed, worst: r2(worst),
    outside: lines.filter(function (l) { return l.over > ${TIDY_TOL}; })
  };
})()`;

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

  /* ---- 2b. THE TIDY CARD: the text lives inside the box ---------------- */
  /* Answered with the hardest thing a dictated intent can be: no spaces to break at,
     longer than the card is wide. A containment check against "on target" would pass
     on a card with no wrapping at all and prove nothing about the rule being tested. */
  const HARD = 'rewriting https://internal.example.com/queues/invoice-importer/retries?since=yesterday';
  await page.evaluate('__galaxy.session.answer(' + JSON.stringify(HARD) + ')');
  await sleep(900);
  const shown = await page.evaluate('document.getElementById("focus-intent").textContent');
  ok(shown.indexOf('internal.example.com') !== -1,
     'the card is carrying an unbreakable ' + HARD.length + '-character intent',
     JSON.stringify(shown));
  const tidy = await page.json(TIDY);
  ok(!!tidy && tidy.count >= 5,
     'and there are ' + (tidy && tidy.count) + ' line boxes of text in it to measure',
     JSON.stringify(tidy));
  if (tidy) {
    note('padded box ' + JSON.stringify(tidy.box) + ' · card ' + tidy.cardW + 'x' +
         tidy.cardH + ' · padding ' + tidy.pad);
    ok(tidy.outside.length === 0,
       'THE TIDY CARD: every one of the ' + tidy.count + ' line boxes lies inside the ' +
       'padded box - worst overhang ' + tidy.worst + 'px',
       JSON.stringify({ box: tidy.box, outside: tidy.outside }));
    ok(tidy.placed.length === 0,
       'and none of that text is absolutely positioned: the digits keep their own row',
       JSON.stringify(tidy.placed));
    ok(tidy.cardW <= r1.focuscard.w + 1,
       'and the long word did not widen the card itself: ' + tidy.cardW + 'px');
  }

  /* ---- 2c. THE MEASURED CLEARANCE: the toast and the card, at once ----- */
  /* A real paragraph through the real renderer: the toast's height is the other half of
     this law, and a height is content. This happens BEFORE the session ends on purpose -
     once it has reported, an eight-second retirement is running and every second spent
     here would be a second stolen from the check that measures it. */
  const TOASTY = 'Three things, sir: the invoice importer retry queue, the ledger ' +
    'migration you paused on Tuesday, and a note to yourself about the billing webhook ' +
    'that has been sitting unread since the fourteenth of the month.';
  await page.evaluate('__galaxy.say("what did I leave unfinished?",' +
    JSON.stringify(TOASTY) + ',false,null)');
  await sleep(600);
  /* Both readings are taken under a device-metrics override, and the WIDTH is the same
     1280 in both of them. That is not tidiness: --window-size=1280,860 gives a viewport of
     1266 (Chrome's own furniture takes the difference), and the toast is centred on the
     canvas, so a run that measured the roomy case at 1266 and the crowded case at 1280
     would see the toast's left edge move by 7px for a reason that has nothing to do with
     the rule being tested - and "it gave up width, not position" would fail on arithmetic
     about window borders. Fixed width, one variable: height. */
  const metrics = (h) => page.send('Emulation.setDeviceMetricsOverride',
                                   { width: W, height: h, deviceScaleFactor: 0, mobile: false });
  /* THE ORGAN RAIL is the ask bar, and the ask bar is not one of the governed surfaces -
     the governor never places it, so it has no entry in layout.rects and has to be read
     off the element. Same shape as a rects entry so that disjoint() can take either. */
  const railBox = () => page.json('(function(){var g=function(id){' +
    'var e=document.getElementById(id);' +
    'if(!e||!e.getClientRects().length||getComputedStyle(e).display==="none")return null;' +
    'var r=e.getBoundingClientRect();' +
    'return {top:Math.round(r.top),left:Math.round(r.left),right:Math.round(r.right),' +
    ' bottom:Math.round(r.bottom),w:Math.round(r.width),h:Math.round(r.height)};};' +
    /* The command panel is never display:none - it is a slid sheet, kept off the left edge
       by a transform with opacity 0 and pointer-events off, because a panel that is built
       and hidden animates and a panel that is created on Ctrl+K does not. So it is read as
       what it is rather than expected to be absent. */
    'var c=document.getElementById("cmd"), cs=c?getComputedStyle(c):null;' +
    'return {bar:g("bar"), cmd:g("cmd"), sheet: c ? {open:c.classList.contains("open"),' +
    ' opacity:+cs.opacity, pe:cs.pointerEvents} : null};})()');
  await metrics(H);
  await sleep(700);
  await page.evaluate('__galaxy.layout.run()');
  await sleep(500);
  const wide = await page.json('__galaxy.layout.last');
  const wideR = await page.json('__galaxy.layout.rects');
  const wv = await page.json('({vw:innerWidth,vh:innerHeight})');
  const wideBar = await railBox();
  ok(wv.vw === W && wv.vh === H,
     'measuring at exactly ' + W + 'x' + H + ', which is the viewport the law names',
     JSON.stringify(wv));
  ok(!!(wide.toastBox && wide.cardBox),
     'the governor measured BOTH boxes rather than assuming they are far apart',
     JSON.stringify({ toast: wide.toastBox, card: wide.cardBox }));
  ok(wide.overlap === false && disjoint(wideR.brain, wideR.focuscard),
     'THE LAW at ' + W + 'x' + H + ': the toast and the card do not overlap',
     JSON.stringify({ governor: wide.toastBox, toast: wideR.brain, card: wideR.focuscard }));

  /* And now the case the law is actually FOR. At 1280x860 these two sit at opposite ends
     of the screen, so a green check up there proves only that the window is tall. The
     viewport is shortened - still 1280 WIDE, which is the width the law is stated for -
     until the card's rows and the toast's rows genuinely want the same pixels, and the
     governor has to give something up. */
  await metrics(SHORT);
  await sleep(700);
  await page.evaluate('__galaxy.layout.run()');
  await sleep(500);
  const tight = await page.json('__galaxy.layout.last');
  const tightR = await page.json('__galaxy.layout.rects');
  const tv = await page.json('({vw:innerWidth,vh:innerHeight})');
  const tightBar = await railBox();
  note('squeezed to ' + tv.vw + 'x' + tv.vh + ' · card ' + JSON.stringify(tight.cardBox) +
       ' · toast ' + JSON.stringify(tight.toastBox));
  ok(tv.vw >= 1280 && tv.vh < H,
     'squeezed to ' + tv.vw + 'x' + tv.vh + ': still at or above the 1280px the law names',
     JSON.stringify(tv));
  ok(tight.clearedToast === true,
     'crowded, the governor had to move to clear the card - the rule FIRED, so what ' +
     'follows is not true by luck',
     JSON.stringify({ toast: tight.toastBox, card: tight.cardBox }));
  ok(tight.overlap === false && disjoint(tightR.brain, tightR.focuscard),
     'and crowded they STILL do not overlap: toast ' + JSON.stringify(tightR.brain) +
     ' clear of card ' + JSON.stringify(tightR.focuscard),
     JSON.stringify({ governor: { toast: tight.toastBox, card: tight.cardBox } }));
  ok(!!tightR.brain && !!wideR.brain && Math.abs(tightR.brain.left - wideR.brain.left) <= 1 &&
     tightR.brain.w < wideR.brain.w,
     'and it gave up WIDTH, not position: ' + (wideR.brain && wideR.brain.w) + 'px -> ' +
     (tightR.brain && tightR.brain.w) + 'px, still starting at the same x',
     JSON.stringify({ wide: wideR.brain, tight: tightR.brain }));
  /* The card is the same card at both heights, and its text is still inside it: a rule
     that held at 860px and quietly stopped holding at 380px would be no rule. */
  const tidy2 = await page.json(TIDY);
  ok(!!tidy2 && tidy2.outside.length === 0 && tidy2.count === tidy.count,
     'and the card is still tidy in the squeezed window: ' + (tidy2 && tidy2.count) +
     ' line boxes in, worst overhang ' + (tidy2 && tidy2.worst) + 'px',
     JSON.stringify(tidy2 && { box: tidy2.box, outside: tidy2.outside }));
  /* ---- 2d. THE RAILS NEVER OVERLAP THE CARD ---------------------------- */
  /* PART 1 added two rails to a page whose card positions were decided before either of
     them existed: a telemetry header across the top, and the organ rail along the ask bar
     at the bottom. The card is FIXED. So the question is not whether the rails look right
     on a tall window - it is whether the band each rail took was a band the card was ever
     using, and the squeezed viewport is where that stops being a matter of opinion: at
     380px the card's rows and the toast's rows already want the same pixels, and anything
     that took height off the top or the bottom took it from this.
     Rectangles compared to each other, never to a constant, so raising --rail-h moves
     these checks instead of falsifying them. */
  const railCase = (label, r, bar) => {
    note(label + ': top rail ' + JSON.stringify(r.toprail) + ' · ask bar ' +
         JSON.stringify(bar.bar) + ' · card ' + JSON.stringify(r.focuscard));
    ok(!!r.toprail && !!bar.bar && !!r.focuscard,
       label + ' - both rails and the card are on screen, which is what makes the rest of ' +
       'this worth asserting', JSON.stringify({ rail: r.toprail, bar: bar.bar,
                                                card: r.focuscard }));
    ok(disjoint(r.toprail, r.focuscard),
       label + ' - THE TELEMETRY RAIL DOES NOT OVERLAP THE CARD (rail ends ' +
       (r.toprail && r.toprail.bottom) + 'px, card begins ' +
       (r.focuscard && r.focuscard.top) + 'px)',
       JSON.stringify({ rail: r.toprail, card: r.focuscard }));
    /* WHICH AXIS DID THE SEPARATING, said out loud. On a tall window the bar is below the
       card and the gap is vertical; squeezed to 380px the card's rows and the bar's row want
       the same band and it is the COLUMN that keeps them apart - the bar narrows to the
       toast's width on the left while the card holds the right. A message that only ever
       quoted tops and bottoms would read as nonsense in the second case, and the second
       case is the one worth proving. */
    const axis = !bar.bar || !r.focuscard ? 'nothing to compare'
      : bar.bar.bottom <= r.focuscard.top ? 'the bar sits ' +
          (r.focuscard.top - bar.bar.bottom) + 'px above the card'
      : bar.bar.top >= r.focuscard.bottom ? 'the bar sits ' +
          (bar.bar.top - r.focuscard.bottom) + 'px below the card'
      : bar.bar.right <= r.focuscard.left ? 'the bar ends at ' + bar.bar.right +
          'px and the card begins at ' + r.focuscard.left + 'px, in the next column over'
      : bar.bar.left >= r.focuscard.right ? 'the bar begins at ' + bar.bar.left +
          'px, past the card\'s right edge at ' + r.focuscard.right + 'px'
      : 'they share pixels';
    ok(disjoint(bar.bar, r.focuscard),
       label + ' - AND NEITHER DOES THE ORGAN RAIL: ' + axis,
       JSON.stringify({ bar: bar.bar, card: r.focuscard }));
    /* The other two surfaces that live in those bands, reported rather than asserted: the
       constitution's claim is about the CARD, and the toast and the note panel are placed
       by a governor whose rules are tested above on their own terms. Printed so that a rail
       creeping into either one is visible here instead of being nobody's check. */
    note(label + ': rail vs toast ' + (disjoint(r.toprail, r.brain) ? 'clear' : 'OVERLAP') +
         ' · bar vs toast ' + (disjoint(bar.bar, r.brain) ? 'clear' : 'OVERLAP') +
         ' · rail vs panel ' + (disjoint(r.toprail, r.panel) ? 'clear' : 'OVERLAP') +
         ' · rail vs title ' + (disjoint(r.toprail, r.title) ? 'clear' : 'OVERLAP') +
         ' — and "bar vs toast" reads OVERLAP because the organ rail is INSIDE the toast ' +
         'column (#bar is a child of #brain, under the status row), so that pair is a ' +
         'containment rather than a collision: ' + JSON.stringify(r.brain));
    ok(!!bar.sheet && bar.sheet.open === false && bar.sheet.opacity === 0 &&
       bar.sheet.pe === 'none' && !!bar.cmd && bar.cmd.right <= 1,
       label + ' - and the unsummoned command panel is covering nothing: opacity 0, ' +
       'pointer-events none, and its box held off the left edge at ' +
       (bar.cmd && bar.cmd.right) + 'px',
       JSON.stringify({ sheet: bar.sheet, box: bar.cmd }));
  };
  railCase('roomy at ' + W + 'x' + H, wideR, wideBar);
  railCase('squeezed at ' + W + 'x' + SHORT, tightR, tightBar);
  /* And the rails are not what gave way. The governor narrows the TOAST when the window
     is short; if the squeeze had instead been paid for by the top rail losing its height
     or the ask bar sliding off the bottom, every disjointness check above would pass on a
     page with no rails left to overlap anything. */
  ok(!!wideR.toprail && !!tightR.toprail && tightR.toprail.h === wideR.toprail.h &&
     tightR.toprail.top === wideR.toprail.top,
     'AND THE RAILS DID NOT PAY FOR THE SQUEEZE: the header is the same ' +
     (wideR.toprail && wideR.toprail.h) + 'px band at both heights, in the same place - ' +
     'the toast gave up width, the rail gave up nothing',
     JSON.stringify({ wide: wideR.toprail, tight: tightR.toprail }));
  ok(!!tightBar.bar && tightBar.bar.bottom <= tv.vh + 1 && tightBar.bar.top >= 0,
     'and the organ rail is still wholly inside the ' + tv.vh + 'px viewport (' +
     (tightBar.bar && tightBar.bar.top) + '-' + (tightBar.bar && tightBar.bar.bottom) +
     'px) rather than pushed off the bottom of it',
     JSON.stringify({ bar: tightBar.bar, vh: tv.vh }));

  await page.send('Emulation.clearDeviceMetricsOverride');
  await sleep(600);
  await page.evaluate('__galaxy.layout.run()');
  await sleep(400);
  const back = await page.json('({vw:innerWidth,vh:innerHeight})');
  ok(back.vh > SHORT, 'the window is its own size again: ' + back.vw + 'x' + back.vh,
     JSON.stringify(back));

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
