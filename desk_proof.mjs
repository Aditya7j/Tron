/* The countdown card's second home, in a real browser, on the real desktop.
 *
 *   launch a HEADED Chrome  ->  press the FOCUS button inside a user activation  ->
 *   watch the card leave the page for a Document Picture-in-Picture window  ->
 *   press LOCK THIS TAB from inside that window and read what it posted  ->
 *   abort, and watch the card come home  ->  start a session with NO gesture and
 *   prove it waits in the page until the next click
 *
 * Why this file exists when focus_probe.mjs already covers the page. Two reasons, and
 * the first is the whole point of the feature: a Document PiP window cannot be opened
 * without a transient user activation, so the one thing that matters here - that the
 * card genuinely leaves the tab and floats above everything else - cannot be proved by
 * a battery that runs itself on load. It needs a press in a real window, which is what
 * this does; see Page.press for exactly where the activation comes from and why it is
 * not a synthesised mouse event. And second, HEADED: headless Chrome has no desktop to
 * float above, and asserting against a window manager that is not there would be a
 * decoration. Run it and you will see a window appear in the bottom-right of your
 * screen. That is the deliverable, and it is meant to be watched once.
 *
 * WHAT THIS CANNOT PROVE, said plainly rather than fudged: that the window is on top of
 * every other application. Always-on-top is the browser's guarantee for this window
 * type; nothing readable from the page reports it. What is asserted instead is that the
 * window exists as its own OS window of the asked-for size in the asked-for corner, that
 * it is not the viewer tab, and that the card - the same element, with its handlers -
 * is inside it while the page no longer holds one.
 *
 * IT LEAVES YOUR RECORD ALONE. Both sessions it starts end with `abort`, the one ending
 * that never writes a row, and the ledger is checksummed either side to prove it. It
 * stands down rather than interfere if a session is already running.
 *
 * Usage:  node desk_proof.mjs        (with server.py already running on 4700)
 */

import { spawn } from 'node:child_process';
import { mkdtempSync, rmSync, existsSync, readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { tmpdir } from 'node:os';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const GALAXY = 'http://127.0.0.1:4700';
const VIEW_URL = GALAXY + '/?mute=1';
/* 9222, and not the 9225 focus_probe.mjs uses, on purpose: focus.py only reads
   127.0.0.1:9222-9224, and the lock-pill chain below needs the SERVER to be able to see
   this browser's tabs. A proof on a port the server cannot reach would be asserting
   against a browser nobody can join. */
const PORT = 9222;
const CDP = 'http://127.0.0.1:' + PORT;
const WORK_URL = 'https://example.com/';
const NET_TIMEOUT_MS = 10000;
const WANT_W = 1280, WANT_H = 860;
const DESK_W = 320, DESK_H = 280;      // what viewer/index.html asks requestWindow for
const LEDGER = join(dirname(fileURLToPath(import.meta.url)), 'focus-ledger.json');

/* THE TIDY CARD, out in the floating window - which is the harder of its two homes and
 * therefore the one worth measuring. Out there the card is 320px wide instead of 460,
 * it is display:flex and position:static instead of fixed, and its padding comes from
 * DESK_CSS rather than from the page's stylesheet. Three different numbers and one rule:
 * every line rectangle of every text node lies inside the card's own padded box, read
 * from the PiP window's own getComputedStyle so that a change to DESK_CSS moves the
 * assertion with it instead of falsifying it.
 *
 * Line rectangles, not element rectangles: an element that wraps has one rectangle per
 * line, and a bounding box averaged over two lines can sit inside the card while the
 * first line hangs out of it. The tolerance is the trailing side-bearing of a last glyph
 * plus the header row's 0.22em of letter-spacing after its final letter - ink-free space
 * the engine still measures. A pixel of that is not text outside the card; ten would be.
 */
const TIDY_TOL = 1.5;
const TIDY_PIP = `(function () {
  var w = documentPictureInPicture.window;
  if (!w) return null;
  var d = w.document, card = d.getElementById('focuscard');
  if (!card) return null;
  var cs = w.getComputedStyle(card), cr = card.getBoundingClientRect();
  var num = function (v) { return parseFloat(v) || 0; };
  var r2 = function (v) { return Math.round(v * 100) / 100; };
  var box = {
    left:   cr.left   + num(cs.borderLeftWidth)   + num(cs.paddingLeft),
    right:  cr.right  - num(cs.borderRightWidth)  - num(cs.paddingRight),
    top:    cr.top    + num(cs.borderTopWidth)    + num(cs.paddingTop),
    bottom: cr.bottom - num(cs.borderBottomWidth) - num(cs.paddingBottom)
  };
  var lines = [], worst = -1e9, placed = [];
  var walk = d.createTreeWalker(card, w.NodeFilter.SHOW_TEXT, null);
  for (var n; (n = walk.nextNode());) {
    if (!n.nodeValue || !n.nodeValue.trim()) continue;
    var host = n.parentElement;
    if (!host) continue;
    var hs = w.getComputedStyle(host);
    if (hs.display === 'none' || hs.visibility === 'hidden' || +hs.opacity === 0) continue;
    if (!host.getClientRects().length) continue;
    var label = (host.id || host.tagName.toLowerCase()) +
                ' "' + n.nodeValue.trim().slice(0, 24) + '"';
    if (hs.position === 'absolute' || hs.position === 'fixed') placed.push(label);
    var rg = d.createRange(); rg.selectNodeContents(n);
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
    card: [Math.round(cr.width), Math.round(cr.height)],
    win: [w.innerWidth, w.innerHeight],
    /* What the rows ADD UP TO against what they were given. The overflow is hidden out
       here (html,body{overflow:hidden}), so a card whose rows want more than the window
       has does not scroll and does not complain - it silently cuts the bottom off the
       button row, which is exactly the failure this measurement exists to name.
       Measured from the last child's own bottom edge and NOT from scrollHeight: Chrome
       leaves the bottom padding out of scrollHeight once the content overflows, so
       scrollHeight under-reports the shortfall by exactly the padding that is missing -
       it read 170 into 167 for a button row hanging 16px out of the card.
       Note the shape of the answer: the LOCK THIS TAB row carries margin-top:auto, so
       whenever the rows fit they are pushed out to fill the glass exactly and need EQUALS
       have. This number is therefore binary and not a margin to watch: equal is fitting,
       greater is a control with its bottom cut off. */
    need: (function () {
      var low = cr.top, kids = card.children;
      for (var j = 0; j < kids.length; j++) {
        var kr = kids[j].getBoundingClientRect();
        if (kr.height && kr.bottom > low) low = kr.bottom;
      }
      return r2(low - cr.top + num(cs.paddingBottom) + num(cs.borderBottomWidth));
    })(),
    have: r2(cr.height),
    pad: [cs.paddingTop, cs.paddingRight, cs.paddingBottom, cs.paddingLeft].join(' '),
    count: lines.length, placed: placed, worst: r2(worst),
    outside: lines.filter(function (l) { return l.over > ${TIDY_TOL}; })
  };
})()`;

const CHROMES = [
  'C:/Program Files/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Google/Chrome/Application/chrome.exe',
  process.env.LOCALAPPDATA + '/Google/Chrome/Application/chrome.exe',
];

const t0 = Date.now();
const failures = [];
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

function note(text) { console.log('  ' + at() + '  note  ' + text); }

async function cdp(path) {
  const res = await fetch(CDP + path, { signal: AbortSignal.timeout(NET_TIMEOUT_MS) });
  const text = await res.text();
  try { return JSON.parse(text); } catch { return text; }
}

async function galaxy(path, body) {
  const init = body
    ? { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body) }
    : {};
  init.signal = AbortSignal.timeout(NET_TIMEOUT_MS);
  const res = await fetch(GALAXY + path, init);
  return res.json();
}

function ledgerSum() {
  try { return createHash('sha256').update(readFileSync(LEDGER)).digest('hex').slice(0, 16); }
  catch { return 'no-ledger'; }
}

/* ---- the smallest CDP client that can evaluate and click ---- */
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

  async evaluate(expression, userGesture = false) {
    const r = await this.send('Runtime.evaluate', {
      expression, returnByValue: true, awaitPromise: true, userGesture,
    });
    if (r.error) throw new Error(r.error.message);
    if (r.result && r.result.exceptionDetails) {
      throw new Error('page threw: ' + r.result.exceptionDetails.text + ' ' +
                      JSON.stringify(r.result.exceptionDetails.exception || {}));
    }
    const res = r.result && r.result.result;
    return res ? res.value : undefined;
  }

  async json(expression) {
    return JSON.parse(await this.evaluate('JSON.stringify(' + expression + ')') || 'null');
  }

  /* THE PRESS - and the one thing in this run that is not quite what it looks like, so
     here it is in full rather than buried.
     Chrome will not give a Document PiP window to synthetic input. Input.dispatchMouseEvent
     produces a click the page handles in every other respect - the FOCUS button starts a
     session from it perfectly well - and requestWindow answers that same click with
     "NotAllowedError: Document PiP requires user activation". Measured, not assumed; it is
     why this does not use it. Runtime.evaluate with userGesture IS an activation the API
     accepts, so that is where the activation comes from, and the click itself is the
     page's own: the same element, the same onclick, the same deskOpen('press'), the same
     everything after it. What is supplied here is the fact of a finger. What is proved is
     all of what the finger would have started.
     `how` says which events a real finger would have sent, and it is not cosmetic:
       'mouse'       - pointerdown then click, which is what a press of a button is, and
                       the two activations the viewer needs to open the window on one and
                       size it on the other. This is the default for that reason.
       'click'       - a click alone: the keyboard's version of a press, and every
                       synthetic one.
       'pointerdown' - the press going down and nothing else, for the armed next-click,
                       whose listener is on pointerdown and never sees a bare .click(). */
  async press(selector, how = 'mouse') {
    const one = (what) => this.evaluate(
      '(function(){var el=document.querySelector(' + JSON.stringify(selector) + ');' +
      'if(!el) return "missing";' +
      (what === 'down'
        ? 'el.dispatchEvent(new PointerEvent("pointerdown",{bubbles:true,cancelable:true}));'
        : 'el.click();') +
      'return "pressed";})()', true);
    if (how !== 'click') {
      const did = await one('down');
      if (did !== 'pressed') throw new Error('nothing matches ' + selector);
      if (how === 'pointerdown') return did;
      /* A HUMAN-LENGTH PRESS. The gap is not padding: a finger holds a button down for
         something like a tenth of a second, and the viewer uses that gap - the window is
         asked for on the way down and sized on the way back up. Sending both halves in
         the same breath collapses the two activations into one and only tests a press
         nobody performs. */
      await new Promise((r) => setTimeout(r, 160));
    }
    const did = await one('click');
    if (did !== 'pressed') throw new Error('nothing matches ' + selector);
    return did;
  }

  close() { try { this.ws.close(); } catch { /* already gone */ } }
}

async function launch(exe, profile) {
  /* No --headless. A Document PiP window is an OS window, and there is no OS window in
     headless Chrome - the request either fails or succeeds into nothing, and a proof
     that passes in a browser with no desktop proves nothing about a desktop. */
  const proc = spawn(exe, [
    '--remote-debugging-port=' + PORT,
    '--user-data-dir=' + profile,
    '--no-first-run', '--no-default-browser-check',
    '--disable-features=Translate',
    '--window-size=' + WANT_W + ',' + WANT_H,
    VIEW_URL,
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

async function waitFor(page, expression, budgetMs = 6000) {
  for (let i = 0; i < budgetMs / 200; i++) {
    try { if (await page.evaluate(expression)) return true; } catch { /* ask again */ }
    await sleep(200);
  }
  return false;
}

/* ============================================================== the run ==== */

const profiles = [];
const browsers = [];

async function main() {
  console.log('\n  the second home · the countdown card on the desktop\n');

  const exe = CHROMES.find((p) => existsSync(p));
  if (!exe) throw new Error('no chrome.exe found in the usual places');

  const before = await galaxy('/focus');
  if (before && before.focus &&
      ['arming', 'running', 'paused'].includes(before.focus.state)) {
    note('a session is ALREADY running; standing down rather than ending yours');
    console.log('\n  ' + checks + ' checks, 0 failed · stood down\n');
    return;
  }
  const sumBefore = ledgerSum();
  note('ledger checksum before: ' + sumBefore);

  const profile = mkdtempSync(join(tmpdir(), 'desk-proof-'));
  profiles.push(profile);
  log('-- launching a HEADED Chrome on ' + PORT + ' (a window will appear)');
  browsers.push(await launch(exe, profile));
  const page = await attach('mute=1');
  ok(await waitFor(page, '!!(window.__galaxy && window.__galaxy.session)', 30000),
     'the viewer is up and exposes the session handle');
  await page.send('Page.bringToFront');

  /* ---- 1. CAN THIS BROWSER DO IT AT ALL ------------------------------- */
  const can = await page.evaluate('__galaxy.session.desk.can');
  ok(typeof can === 'boolean', 'the page reports whether it can pop the card out');
  if (!can) {
    /* THE HONEST FALLBACK. Not a failure of this run - a browser without Document PiP
       is a supported case - but it is asserted rather than assumed: the card must stay
       in the page and the refusal must be said once. */
    note('this browser has no Document Picture-in-Picture; proving the fallback instead');
    await page.press('#focusbtn');
    await sleep(1200);
    const fell = await page.json('({out:__galaxy.session.desk.out,' +
      'inPage:__galaxy.session.desk.inPage,said:__galaxy.session.desk.said,' +
      'answer:document.getElementById("a-text").textContent})');
    ok(!fell.out && fell.inPage, 'the card stays in the page');
    ok(fell.said && /corner of the tab/i.test(fell.answer),
       'and it says so once, in as many words', JSON.stringify(fell));
    await galaxy('/focus', { cmd: 'abort' });
    return;
  }

  /* ---- 2. A WORK WINDOW, so the lock has somewhere to land ------------- */
  let workOpen = false;
  try {
    const made = await page.send('Target.createTarget', { url: WORK_URL, newWindow: true });
    workOpen = !!(made.result && made.result.targetId);
    await sleep(2500);
    const list = await cdp('/json/list');
    const work = (Array.isArray(list) ? list : []).find((t) => t.url.includes('example.com'));
    workOpen = !!work && !/chrome-error/.test(work.url);
    note(workOpen ? 'a second window holds ' + WORK_URL + ' as the work surface'
                  : 'no work window (the network refused); the lock chain will say so');
  } catch (e) {
    note('could not open a work window: ' + e.message);
  }
  await page.send('Page.bringToFront');

  /* ---- 3. THE PRESS. One click, and the card leaves the page ----------- */
  log('-- the press: the FOCUS button, inside a user activation');
  const start = await page.json('({out:__galaxy.session.desk.out,' +
    'inPage:__galaxy.session.desk.inPage,live:__galaxy.session.live})');
  ok(!start.out && start.inPage && !start.live,
     'before the press: no session, and the card is in the tab where it has always been',
     JSON.stringify(start));

  await page.press('#focusbtn');
  const popped = await waitFor(page, '__galaxy.session.desk.out', 8000);
  ok(popped, 'the click popped the card out onto the desktop');
  if (!popped) {
    /* Everything from here reads documentPictureInPicture.window, and there isn't one.
       Carrying on would turn one honest failure into six imaginary ones and then throw
       on a null, which says nothing about the feature and hides the one line that does:
       what the browser gave as its reason. So: report it, put the session back, stop. */
    const why = await page.json('({trouble:__galaxy.session.desk.trouble,' +
      'can:__galaxy.session.desk.can,said:__galaxy.session.desk.said,' +
      'wanted:__galaxy.session.desk.wanted,live:__galaxy.session.live})');
    note('the browser refused the window: ' + (why.trouble || '(no reason given)'));
    note('stopping here rather than asserting against a window that is not there');
    note(JSON.stringify(why));
    await galaxy('/focus', { cmd: 'abort' });
    page.close();
    return;
  }

  /* The window opens on the way down and the session starts on the way up, so for a
     moment there is a card out there with nothing to count yet - the grace window in
     fxPaint is exactly that moment. Wait for the first painted clock rather than reading
     into the gap and calling it a failure. */
  await waitFor(page,
    '/^\\d+:\\d\\d$/.test((documentPictureInPicture.window||{document:document}).document' +
    '.getElementById("focus-clock").textContent)', 8000);
  const out = await page.json(
    '(function(){var w=documentPictureInPicture.window;' +
    'var d=w&&w.document, c=d&&d.getElementById("focuscard");' +
    'var cs=c&&w.getComputedStyle(c);' +
    'return {title:d&&d.title, hasCard:!!c, cls:c&&c.className,' +
    ' clock:c&&d.getElementById("focus-clock").textContent,' +
    ' pill:!!(d&&d.getElementById("focus-lock")),' +
    ' display:cs&&cs.display, position:cs&&cs.position,' +
    ' inner:[w&&w.innerWidth,w&&w.innerHeight],' +
    ' at:[w&&w.screenX,w&&w.screenY],' +
    ' screen:[screen.availWidth,screen.availHeight],' +
    ' inPage:__galaxy.session.desk.inPage,' +
    ' opener:d&&(d===document)};})()');
  ok(out.hasCard && !out.inPage,
     'ONE CARD, TWO HOMES, NEVER BOTH: it is in the window and gone from the page',
     JSON.stringify(out));
  ok(out.opener === false && out.title === 'Jarvis · focus',
     'the window is its own document with its own title, not the viewer tab',
     JSON.stringify({ title: out.title, opener: out.opener }));
  ok(/^\d+:\d\d$/.test(out.clock || '') && /\blive\b/.test(out.cls || ''),
     'and the SERVER\'s session is painting it out there: the clock reads ' + out.clock,
     JSON.stringify({ clock: out.clock, cls: out.cls }));
  ok(out.display === 'flex' && out.position === 'static',
     'the card fills the window rather than hiding under the 720px rule',
     JSON.stringify({ display: out.display, position: out.position }));
  /* THE SIZE, and the one place this run is deliberately not strict on the first look.
     width/height are a hint the browser may ignore, and this Chrome does: it grants 80%
     of the screen however small a window is asked for. The viewer answers that with
     deskFit(), which resizeTo()s the window down - and resizeTo needs an activation of
     its own, because requestWindow ate the one the click gave. So what is asserted is
     the outcome a user gets: the window settles to the asked-for size by the time the
     next click has happened, and it is reported which of the two ways it got there. */
  const granted = await page.json('__galaxy.session.desk.size');
  const fits = (s) => Math.abs(s[0] - DESK_W) <= 8 && Math.abs(s[1] - DESK_H) <= 8;
  const fixes = await page.evaluate('__galaxy.session.desk.fitted');
  if (fits(granted)) {
    note(fixes
      ? 'the window is ' + granted.join('x') + ', and got there by correction: this ' +
        'browser granted its own size and the press\'s own up-stroke resized it (' +
        fixes + ' correction' + (fixes === 1 ? '' : 's') + ', within the one press)'
      : 'the browser granted the size that was asked for outright: ' + granted.join('x'));
  } else {
    note('the browser ignored the asked-for ' + DESK_W + 'x' + DESK_H + ' and granted ' +
         granted.join('x') + '; the next click corrects it');
    await page.press('#title h1', 'pointerdown');
    await sleep(700);
  }
  const size = await page.json('__galaxy.session.desk.size');
  ok(fits(size), 'the window is the size the card was written for: ' + size.join('x') +
     ' (asked ' + DESK_W + 'x' + DESK_H + ')', JSON.stringify({ granted, size }));
  /* THE TIDY CARD, now that the window is the size the card was written for - measuring
     it before the correction would be measuring a card that has 80% of the screen to
     spread out in, which is not the box the text has to live inside.
     And measured in the card's TALLEST dress, because the shortest one proves nothing:
     an intent is dictated first, and one with no spaces in it, so the card is carrying
     its clamped intent row and the status lines are carrying a word that cannot be
     broken at a space. A containment check against "on target" and an empty intent would
     be green on a card two rows shorter than the one you actually get. */
  const HARD = 'rewriting https://internal.example.com/queues/invoice-importer/retries';
  await page.evaluate('__galaxy.session.answer(' + JSON.stringify(HARD) + ')');
  await sleep(1200);
  const intent = await page.evaluate(
    '(function(){var w=documentPictureInPicture.window;' +
    'var e=w&&w.document.getElementById("focus-intent");' +
    'return e?e.textContent:"";})()');
  ok(intent.indexOf('internal.example.com') !== -1,
     'the desktop card is carrying an unbreakable ' + HARD.length + '-character intent',
     JSON.stringify(intent));
  const tidy = await page.json(TIDY_PIP);
  ok(!!tidy && tidy.count >= 5,
     'there are ' + (tidy && tidy.count) + ' line boxes of text out there to measure',
     JSON.stringify(tidy));
  if (tidy) {
    note('padded box ' + JSON.stringify(tidy.box) + ' · card ' + tidy.card.join('x') +
         ' in a ' + tidy.win.join('x') + ' window · padding ' + tidy.pad +
         ' · rows want ' + tidy.need + 'px of the ' + tidy.have + 'px they have');
    ok(tidy.need <= tidy.have,
       'the card\'s rows FIT the window they were given: ' + tidy.need + 'px into ' +
       tidy.have + 'px',
       JSON.stringify({ need: tidy.need, have: tidy.have, win: tidy.win }));
    ok(tidy.outside.length === 0,
       'THE TIDY CARD: all ' + tidy.count + ' of them lie inside the card\'s padded box ' +
       'out in the floating window - worst overhang ' + tidy.worst + 'px',
       JSON.stringify({ box: tidy.box, outside: tidy.outside }));
    ok(tidy.placed.length === 0,
       'and none of that text is absolutely positioned: the digits keep their own row',
       JSON.stringify(tidy.placed));
    ok(tidy.card[0] <= tidy.win[0],
       'and the card did not grow wider than the window it is in: ' +
       tidy.card[0] + 'px in ' + tidy.win[0] + 'px');
  }
  /* The corner, as the window manager actually granted it. Chrome may refuse a
     placement outright - moveTo on a PiP window is silently ignored here, and its own
     default placement happens to be this same corner - so the claim is checked as "the
     bottom-right quarter of the screen": where your eyes rest, not a number. */
  const at = await page.json(
    '(function(){var w=documentPictureInPicture.window;' +
    'return [w.screenX,w.screenY,screen.availWidth,screen.availHeight];})()');
  ok(at[0] > at[2] / 2 && at[1] > at[3] / 2,
     'and it sits in the bottom-right corner, out of the reading line',
     'at ' + at.slice(0, 2).join(',') + ' on ' + at.slice(2).join('x'));
  const live = await galaxy('/focus');
  ok(live && live.focus && ['arming', 'running'].includes(live.focus.state),
     'the server agrees a session is running (' +
     (live.focus && live.focus.state) + ')');

  /* ---- 4. THE TINT, in the real window -------------------------------- */
  /* The drift tone applied by hand for one frame, and the computed background read back
     out of the DESKTOP window. That the server's drifting state is what adds this class
     is proved hermetically by the probe's desk-move case; what needs a real window is
     that the class still means red out here, where the page's stylesheet had to be
     copied for it to mean anything at all. */
  const tint = await page.json(
    '(function(){var w=documentPictureInPicture.window;' +
    'var c=w.document.getElementById("focuscard");' +
    'var calm=w.getComputedStyle(c).backgroundImage;' +
    'c.classList.add("drift");' +
    'var hot=w.getComputedStyle(c).backgroundImage;' +
    'var bar=w.getComputedStyle(c).borderTopColor;' +
    'c.classList.remove("drift");' +
    'return {calm:calm.slice(0,60), hot:hot.slice(0,60), bar:bar};})()');
  ok(tint.hot !== tint.calm && /46, 10, 16|255, 77, 94/.test(tint.hot + tint.bar),
     'drifting tints the whole desktop window red, over whatever is behind it',
     JSON.stringify(tint));

  /* ---- 5. THE CARD TRAP, from the desktop window ---------------------- */
  /* Pressing the pill makes the PiP WINDOW frontmost, not your browser - so what the
     press must post is the card flag, and the server must then ask the browser which of
     its tabs is visible instead of reading the foreground. The flag is asserted from the
     wire; where the lock landed is reported, because that depends on what is really in
     front of this machine while the run happens. */
  log('-- the pill: LOCK THIS TAB, pressed inside the desktop window');
  /* THE FRONT WINDOW IS THE CARD. Not a detail of the harness - it is the trap itself.
     Pressing the pill puts the PiP window in front, so a server reading "the frontmost
     window" sees a window titled `Jarvis · focus` on about:blank, which matches no tab
     at all. So the card is brought to the front on purpose here, and what is then
     demanded is that the lock lands on the WORK tab anyway, by way of the browser's own
     account of which of its tabs is showing. A run with the work window in front would
     pass through the ordinary title join and prove nothing about the card. */
  let front = 'unknown';
  /* SITTING IN THE WORK TAB, first. Not stage dressing: Chrome tracks window occlusion
     on Windows and reports a completely covered window's pages as `hidden`, and a hidden
     page is not a candidate for the lock - correctly, since you cannot be working in a
     window you cannot see. The first run of this stage left the work window buried under
     the viewer's and the server refused the lock for exactly that reason. So the work
     window is raised first and the card raised over it, which is the real shape of the
     thing: your work in front, the countdown floating above it. */
  const raise = async (pick) => {
    const list = await cdp('/json/list');
    const t = (Array.isArray(list) ? list : []).find(pick);
    if (!t || !t.webSocketDebuggerUrl) return false;
    const p = new Page(t.webSocketDebuggerUrl);
    await p.open();
    await p.send('Page.enable');
    await p.send('Page.bringToFront');
    p.close();
    return true;
  };
  if (workOpen) { await raise((t) => t.url.includes('example.com')); await sleep(600); }
  if (await raise((t) => t.title === 'Jarvis · focus')) front = 'the card, over the work window';
  else if (workOpen) front = 'the work window (the card is not a debuggable target here)';
  note('brought to the front: ' + front);
  /* capability() is cached for three seconds, and the answer that matters is the one
     taken AFTER the window was raised. Waiting it out costs three seconds and buys the
     difference between "the lock did not land" and knowing why. */
  await sleep(3300);
  const cap = ((await galaxy('/health')) || {}).focus || {};
  note('the machine sees: foreground app=' + cap.app + ' browser=' + cap.browser +
       ' cdp=' + cap.cdp);
  /* The same question the server is about to ask, asked here first and printed: every
     http(s) page, is it visible and does it have focus. When the lock does not land this
     is the line that says whether the browser answered or the reader did. */
  const seenBy = [];
  for (const t of (Array.isArray(await cdp('/json/list')) ? await cdp('/json/list') : [])) {
    if (t.type !== 'page' || !/^https?:/.test(t.url || '')) continue;
    const p = new Page(t.webSocketDebuggerUrl);
    try {
      await p.open();
      await p.send('Runtime.enable');
      seenBy.push(new URL(t.url).host + ' ' +
                  await p.evaluate('document.visibilityState + (document.hasFocus()?"+focus":"")'));
    } catch (e) { seenBy.push((t.url || '?') + ' unreadable'); }
    p.close();
  }
  note('the browser\'s own account of its tabs: ' + (seenBy.join(' | ') || 'none'));

  /* The pill's text is read in the same breath as the click, not after the wait: it says
     LOCKED from the press and puts itself back a second later, so a read that comes
     after the round trip catches it after it has already reverted. The spoken answer is
     read too, because the server's own words are the only thing that says WHY a press it
     could not read did not lock anything. */
  const sent = await page.evaluate(
    '(async function(){var seen=null,said=null;var real=window.fetch;' +
    'window.fetch=function(u,o){if(String(u).indexOf("/focus")===0&&o&&o.body){' +
    'seen=JSON.parse(o.body);' +
    'return real.apply(window,arguments).then(function(r){' +
    'return r.clone().json().then(function(j){said=j.answer||"";return r;},' +
    'function(){return r;});});}' +
    'return real.apply(window,arguments);};' +
    'var p=documentPictureInPicture.window.document.getElementById("focus-lock");' +
    'p.click();' +
    'var flash=p.textContent;' +
    'await new Promise(function(r){setTimeout(r,2500);});' +
    'window.fetch=real;' +
    'return {sent:seen, pill:flash, said:said, back:p.textContent};})()');
  note('the server said: ' + JSON.stringify(sent.said));
  ok(sent.sent && sent.sent.cmd === 'retarget' && sent.sent.source === 'card',
     'the pill out there posts the same re-target with the card flag',
     JSON.stringify(sent));
  ok(/locked/i.test(sent.pill || ''),
     'and says LOCKED from the press itself, not from the reply', JSON.stringify(sent));
  const after = await galaxy('/focus');
  const f = (after && after.focus) || {};
  note('the server answered: locked=' + f.locked + ' tabWatched=' + f.tabWatched +
       ' deferred=' + f.deferred + (workOpen ? ' (with a work window open)' : ''));
  if (workOpen && cap.browser) {
    ok(f.locked && f.tabWatched,
       'and the work tab is locked, from a press whose front window was ' + front,
       JSON.stringify({ locked: f.locked, tabWatched: f.tabWatched, deferred: f.deferred }));
  } else if (!cap.browser) {
    /* Not a failure of the card, and not dressed up as a pass either: no browser was
       frontmost when the pill was pressed, so there was no front window to read. On a
       machine where another application holds the foreground - a terminal running this
       script, most of the time - the server correctly re-arms the deferred lock. */
    note('no browser was frontmost at the press, so the lock had nothing to land on; ' +
         'the server re-armed the deferred lock instead (deferred=' + f.deferred + ')');
    ok(f.deferred === true,
       'and a press it could not read re-arms the deferred lock rather than guessing',
       JSON.stringify({ locked: f.locked, deferred: f.deferred }));
  } else {
    note('no work window, so nothing for the lock to land on');
  }

  /* ---- 6. THE END ----------------------------------------------------- */
  log('-- the end: aborting, and the card comes home');
  await page.evaluate('__galaxy.session.send({cmd:"abort"})');
  const home = await waitFor(page, '!__galaxy.session.desk.out', 6000);
  ok(home, 'finishing the session closed the desktop card');
  const back = await page.json('({inPage:__galaxy.session.desk.inPage,' +
    'slot:(function(){var c=document.getElementById("focuscard");' +
    'return !!c && c.nextElementSibling && c.nextElementSibling.id;})(),' +
    'pip:!!documentPictureInPicture.window})');
  ok(back.inPage && back.pip === false,
     'the card is back in the tab and the window is gone', JSON.stringify(back));
  ok(back.slot === 'sharewash',
     'and back in its own slot in the page, not appended wherever was convenient',
     JSON.stringify(back));

  /* ---- 7. THE VOICE PATH: no gesture, so it waits ---------------------- */
  log('-- a session with NO gesture: the card waits in the page and upgrades on a click');
  await page.evaluate('__galaxy.session.start(1)');     // no userGesture: like speaking
  ok(await waitFor(page, '__galaxy.session.live', 6000), 'the session started');
  await sleep(400);
  const waiting = await page.json('({out:__galaxy.session.desk.out,' +
    'inPage:__galaxy.session.desk.inPage,wanted:__galaxy.session.desk.wanted})');
  ok(!waiting.out && waiting.inPage,
     'a session nobody clicked leaves the card in the page, as it always was',
     JSON.stringify(waiting));
  ok(waiting.wanted, 'and the next click anywhere is armed to upgrade it',
     JSON.stringify(waiting));
  /* A click on nothing in particular - the page's own title - and a whole press of it,
     down and up: the armed upgrade opens the window on the way down and the size
     correction rides the way back up, exactly as the FOCUS button does. */
  await page.press('#title h1');
  const upgrade = await waitFor(page, '__galaxy.session.desk.out', 8000);
  ok(upgrade, 'one click somewhere harmless, and the card is on the desktop');
  if (upgrade) {
    const upgraded = await page.json('({inPage:__galaxy.session.desk.inPage,' +
      'size:__galaxy.session.desk.size,' +
      'clock:documentPictureInPicture.window.document' +
      '.getElementById("focus-clock").textContent})');
    ok(!upgraded.inPage && /^\d+:\d\d$/.test(upgraded.clock || ''),
       'counting out there too: ' + upgraded.clock, JSON.stringify(upgraded));
    ok(fits(upgraded.size),
       'and the same one press sized it: ' + upgraded.size.join('x'),
       JSON.stringify(upgraded));
  } else {
    note('no second window, so nothing to read in it: ' +
         await page.evaluate('__galaxy.session.desk.trouble'));
  }

  await page.evaluate('__galaxy.session.send({cmd:"abort"})');
  await waitFor(page, '!__galaxy.session.desk.out', 6000);

  /* ---- 8. AND IT TOUCHED NOTHING -------------------------------------- */
  const sumAfter = ledgerSum();
  ok(sumAfter === sumBefore,
     'two sessions started and aborted, and your ledger is byte-for-byte unchanged',
     sumBefore + ' -> ' + sumAfter);
  page.close();
}

main().then(() => {
  console.log('\n  ' + checks + ' checks, ' + failures.length + ' failed\n');
  if (failures.length) process.exitCode = 1;
}).catch((e) => {
  console.log('\n  FAIL  ' + e.message + '\n');
  process.exitCode = 1;
}).finally(async () => {
  for (const b of browsers) { try { b.kill(); } catch { /* gone */ } }
  await sleep(600);
  for (const p of profiles) { try { rmSync(p, { recursive: true, force: true }); } catch { /* later */ } }
});
