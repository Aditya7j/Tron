/* The live loop the focus feature has to survive, driven end to end.
 *
 *   click FOCUS in the Jarvis tab  ->  hear "go to what you're working on"
 *   ->  answer "what are we focusing on?" out loud  ->  switch to the work tab
 *   ->  hear "Locked on, sir."  ->  switch away  ->  hear the callout within
 *   three seconds  ->  switch back  ->  MOVE THE LOCK from all three surfaces it
 *   can be moved from  ->  end the session  ->  hear the report
 *
 * That order is the whole point of the deferred lock. The FOCUS button lives in the
 * Jarvis tab, so the surface in front of you at the click is the one surface you are
 * certain to leave; a session that locked it would read your actual work as a drift
 * three seconds in. So this test asserts that NOTHING is locked at the click, and
 * that the lock arrives later, out loud, on the surface you settled on.
 *
 * The lock having been inferred, it also has to be movable on purpose, and the second
 * half of this run is that: the spoken override from a work tab, the same words from
 * the Jarvis tab (where the only honest answer is to re-arm), and a real mouse press
 * on the pill on the card - which opens a SECOND browser window first, because a tab
 * can only be visible while home base is the thing in front if it belongs to another
 * window, and that is the whole geometry of the trap the pill has to dodge.
 *
 * Nothing here is a mock. It launches a real headed Chrome on the DevTools port
 * (which is also the only way focus.py can read an active tab's host at all),
 * opens a work site and a distraction on genuinely different hosts, and switches
 * between them with Target.activateTarget - so the server's reader is doing the
 * same Win32 foreground query and the same CDP join it does in normal use.
 *
 * The callout NAMES the site you drifted to, so the privacy assertion in the middle of
 * this run is the true one rather than the simple one: the name may be in the sentence
 * and in no other field, and the sentence itself has to be GONE from the state the
 * browser holds a tick later. Said out loud, written down nowhere - and iana.org is in
 * no map, so the same three checks also prove the unmapped case end to end: the bare
 * domain, with no subdomain, no path and no URL in a spoken line.
 *
 * What is measured, and where each number comes from:
 *   - the CALLOUT LATENCY is wall time from the activate call returning to a new
 *     line appearing in the page's own recording of what was spoken. Not the
 *     server's queue - the browser's speaker. That is the promise being tested.
 *   - speechSynthesis.speak is WRAPPED, not stubbed, so the line is recorded and
 *     still comes out of the speakers. You should hear this run.
 *   - the viewer is a BACKGROUND tab throughout the drift, which is the case the
 *     stream exists for: a hidden tab's timers are throttled to about once a
 *     minute, and three seconds is not reachable by polling from one.
 *
 * Usage:  node focus_live.mjs
 */

import { spawn } from 'node:child_process';
import { mkdtempSync, rmSync, existsSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const GALAXY = 'http://127.0.0.1:4700/';
const WORK = 'https://example.com/';          // the thing you said you would do
const AWAY = 'https://www.iana.org/';         // the thing you did instead
// A second window, on the distraction's host, for the card trap. It has to be a
// different URL from AWAY so the test can tell the two targets apart - and the same
// HOST, because the host is the only thing a lock is ever made of.
const BEHIND = 'https://www.iana.org/help/example-domains';
const BEHIND_FRAG = 'help/example-domains';
const CDP = 'http://127.0.0.1:9222';
const CALLOUT_DEADLINE_MS = 3000;             // the promise, in one number
const LOCK_FLASH_MS = 1000;                   // FOCUS_LOCK_FLASH_MS in the viewer
const LABEL_TTL_MS = 6000;                    // focus.LABEL_LINE_TTL_S, in ms: how
                                              // long a line that NAMES a site may sit
                                              // in the queue before it is scrubbed

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

function ok(cond, claim, detail) {
  checks++;
  console.log('  ' + at() + (cond ? '  ok   ' : '  FAIL ') + claim);
  if (!cond) {
    failures.push(claim);
    if (detail) console.log('            ' + detail);
  }
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

/* Everything that leaves this process gets a deadline. A browser that stops answering
   is a result - "Chrome went away" - and a test run that hangs silently instead of
   saying so is the one failure mode that wastes a whole afternoon. */
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
      // A closed tab never answers, and a promise that waits for it forever turns a
      // failed check into a run that simply stops.
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
    const res = r.result && r.result.result;
    if (r.result && r.result.exceptionDetails) {
      throw new Error('page threw: ' + r.result.exceptionDetails.text);
    }
    return res ? res.value : undefined;
  }

  close() { try { this.ws.close(); } catch { /* already gone */ } }
}

/* ============================================================== the run ==== */

const profile = mkdtempSync(join(tmpdir(), 'focus-live-'));
let chrome = null;

async function main() {
  console.log('\n  focus sessions · the live loop\n');

  // 0. Is the galaxy up, and does it admit what it can see?
  const health = await galaxy('/health');
  log('server: ' + health.notes + ' notes · reader ' + health.focus.backend);
  ok(health.focus.app === true, 'the server can read the frontmost application');

  const exe = CHROMES.find((p) => existsSync(p));
  if (!exe) throw new Error('no chrome.exe found in the usual places');

  // 1. A real, headed Chrome. Headed is not optional: the reader asks the window
  //    manager which window is in front, and a headless browser has no window to
  //    be in front. --remote-debugging-port is what makes the tab readable at all.
  chrome = spawn(exe, [
    '--remote-debugging-port=9222',
    '--user-data-dir=' + profile,
    '--no-first-run', '--no-default-browser-check',
    '--new-window', GALAXY,
  ], { detached: true, stdio: 'ignore' });

  for (let i = 0; i < 60; i++) {
    try { await cdp('/json/version'); break; } catch { await sleep(250); }
  }
  const version = await cdp('/json/version');
  log('chrome: ' + version.Browser);

  // The server should now see a readable tab where a moment ago it did not. The
  // wait is for capability()'s short cache, which was populated a second ago when
  // there was no browser in existence to find.
  await sleep(4200);
  const cap = await galaxy('/health');
  ok(cap.focus.cdp === true,
     'with Chrome on the DevTools port the active tab becomes readable',
     'health.focus = ' + JSON.stringify(cap.focus));

  // 2. Two more tabs on genuinely different hosts, with different titles - the
  //    reader joins the OS window to the browser's tabs by title, so two pages
  //    called the same thing would be a test rigged to pass.
  await cdp('/json/new?' + encodeURIComponent(WORK), 'PUT');
  await cdp('/json/new?' + encodeURIComponent(AWAY), 'PUT');
  await sleep(2500);

  const targets = (await cdp('/json/list')).filter((t) => t.type === 'page');
  const find = (frag) => targets.find((t) => t.url.includes(frag));
  const tabGalaxy = find('127.0.0.1:4700');
  const tabWork = find('example.com');
  const tabAway = find('iana.org');
  ok(!!(tabGalaxy && tabWork && tabAway), 'three tabs: home base, work, distraction',
     targets.map((t) => t.url).join(' | '));

  // 3. Attach to the viewer and record what it actually says out loud.
  const page = new Page(tabGalaxy.webSocketDebuggerUrl);
  await page.open();
  await page.send('Runtime.enable');
  await page.evaluate(`
    (function () {
      if (window.__spoken) return 'already';
      window.__spoken = [];
      var real = speechSynthesis.speak.bind(speechSynthesis);
      // Wrapped, not replaced: the line is recorded AND still comes out of the
      // speakers, which is the difference between testing the plumbing and
      // testing the thing the user asked for.
      speechSynthesis.speak = function (u) {
        window.__spoken.push({ at: Date.now(), text: String(u.text || '') });
        return real(u);
      };
      return 'wrapped';
    })()`);

  const spokenCount = () => page.evaluate('window.__spoken.length');
  const spokenLast = () => page.evaluate('window.__spoken.length ? window.__spoken[window.__spoken.length-1].text : ""');
  /* Everything spoken since a mark, which is how a claim about what was NOT said is
     made safely: a session with a live drift is saying things on its own schedule, so
     "the last line was X" and "no line was Y" are different questions. */
  const spokenSince = async (mark) => JSON.parse(await page.evaluate(
    'JSON.stringify(window.__spoken.slice(' + mark +
    ').map(function (s) { return s.text; }))'));
  /* Polled, never slept-and-sampled - see the callout below for why. */
  async function waitLine(mark, ms) {
    const until = Date.now() + ms;
    while (Date.now() < until) {
      if (await spokenCount() > mark) return await spokenLast();
      await sleep(120);
    }
    return null;
  }
  /* Said out loud, through the very same door a dictated sentence comes in by: ask()
     is what the microphone calls, so this exercises the real routing decision rather
     than posting the command the router was supposed to have chosen. */
  const say = (words) => page.evaluate('void __galaxy.ask(' + JSON.stringify(words) + ')');
  /* Two sources, deliberately kept apart. The SERVER is asked about accounting,
     because it owns the tick and the counters. The PAGE is asked about what the
     user can see and hear. Asking the page for a counter would be testing how
     recently it was pushed to, which is a different and much less useful thing. */
  const serverState = async () => (await galaxy('/focus')).focus;
  const clientState = async () => JSON.parse(await page.evaluate(
    'JSON.stringify(__galaxy.session.state)') || 'null');

  ok(await page.evaluate('!!window.__galaxy && !!window.__galaxy.session'),
     'the viewer exposes the session handle');
  ok(await page.evaluate('__galaxy.session.streaming') === true,
     'the viewer is subscribed to the event stream, not polling',
     'polling=' + await page.evaluate('__galaxy.session.polling'));

  // 4. A real click on the FOCUS button. This also unlocks audio, which no
  //    synthetic .click() would do - Chrome wants a genuine input event.
  await cdp('/json/activate/' + tabGalaxy.id);
  await sleep(600);
  const box = await page.evaluate(`
    (function () { var r = document.getElementById('focusbtn').getBoundingClientRect();
      return JSON.stringify({x: Math.round(r.left + r.width/2),
                             y: Math.round(r.top + r.height/2)}); })()`);
  const { x, y } = JSON.parse(box);
  for (const type of ['mousePressed', 'mouseReleased']) {
    await page.send('Input.dispatchMouseEvent',
      { type, x, y, button: 'left', clickCount: 1 });
  }
  await sleep(1500);
  let st = await serverState();
  ok(st && st.state === 'arming',
     'the FOCUS button starts a session on the server',
     'state=' + (st && st.state));
  ok(await page.evaluate('__galaxy.speech.unlocked') === true,
     'the click unlocked the voice, so the callouts can be heard');

  // 4a. THE DEFERRED LOCK. The click happened in the Jarvis tab, which is the one
  //     surface it must refuse to lock. Nothing is being watched yet, and the state
  //     says so in a boolean rather than leaving the card to guess.
  ok(st.deferred === true && st.locked === false && st.tabWatched === false,
     'clicking FOCUS in the Jarvis tab locks NOTHING - the lock is deferred',
     JSON.stringify({ deferred: st.deferred, locked: st.locked,
                      tabWatched: st.tabWatched }));
  const startLine = await spokenLast();
  log('said: ' + JSON.stringify(startLine));
  ok(/go to what you'?re working on/i.test(startLine),
     'and it SAYS the lock is deferred, so a deferred lock is never a silent one',
     'said: ' + JSON.stringify(startLine));
  ok(/what are we focusing on/i.test(startLine),
     'the same line asks what the session is for');
  ok(await page.evaluate('__galaxy.session.deferred') === true &&
     (await page.evaluate('__galaxy.session.card')).indexOf('deferred') !== -1,
     'the countdown card shows the deferred state rather than a confident clock',
     'card="' + await page.evaluate('__galaxy.session.card') + '"');

  // 4b. THE ANSWER WINDOW. The assistant asked a question out loud, so the
  //     microphone opens for one answer with no wake word. answer() is precisely the
  //     call flushThought() makes while that window is armed, so driving it here
  //     exercises the dictation path rather than a test-only shortcut.
  await sleep(1200);                      // FOCUS_ANSWER_WAIT_MS, plus the question
  ok(await page.evaluate('__galaxy.session.answerArmed') === true,
     'the microphone opens itself for one answer, no wake word needed',
     'awaitingIntent=' + st.awaitingIntent);
  const beforeNoted = await spokenCount();
  await page.evaluate('__galaxy.session.answer("the invoice importer")');
  await sleep(1200);
  st = await serverState();
  ok(st.intent === 'the invoice importer',
     'the answer is attached to the running session as its intent',
     'intent=' + JSON.stringify(st.intent));
  ok(st.awaitingIntent === false && await page.evaluate('__galaxy.session.answerArmed') === false,
     'and the window closes on that one answer, so the next sentence is a question again');
  const noted = await spokenLast();
  ok(await spokenCount() > beforeNoted && /noted/i.test(noted) &&
     !/invoice/i.test(noted),
     'the acknowledgement is "Noted, sir." - your sentence is never read back at you',
     'said: ' + JSON.stringify(noted));
  // Shown, not recited. And written with textContent, so a dictated angle bracket is
  // a dictated angle bracket rather than markup on the card.
  ok(await page.evaluate(
       "document.getElementById('focus-intent').textContent") === 'the invoice importer',
     'the card shows the intent, which is where a long answer lives instead of aloud',
     JSON.stringify(await page.evaluate(
       "document.getElementById('focus-intent').textContent")));

  // 5. Go to the work site and STAY there. This is the surface that becomes the
  //    target: not the one in front of you when you clicked, the first one that is
  //    not home base and that you are still on a tick later.
  const beforeLock = await spokenCount();
  const wentToWork = Date.now();
  await cdp('/json/activate/' + tabWork.id);
  log('-> activated the work site; waiting to settle');

  let lockLine = null;
  while (Date.now() - wentToWork < 12000) {
    if (await spokenCount() > beforeLock) { lockLine = await spokenLast(); break; }
    await sleep(150);
  }
  ok(lockLine !== null && /locked on/i.test(lockLine),
     'settling on the work site is announced out loud, so a wrong lock is audible',
     'after ' + (Date.now() - wentToWork) + 'ms, said: ' + JSON.stringify(lockLine));
  log('said after ' + (Date.now() - wentToWork) + 'ms: ' + JSON.stringify(lockLine));
  st = await serverState();
  ok(st.state === 'running' && st.locked && st.deferred === false,
     'it locked on once you settled somewhere that is not home base',
     JSON.stringify({ state: st.state, locked: st.locked, deferred: st.deferred }));
  ok(st.tabWatched === true,
     'it locked the SITE as well as the application (host-level, not per-page)',
     'tabWatched=' + st.tabWatched);
  // The absence of a caveat is the signal: "Locked on, sir." on its own means the
  // site was locked too, and the app-only fallback appends a sentence saying so.
  ok(!/watch the application/i.test(lockLine || ''),
     'and it did not have to fall back to watching the application only');

  // Settle some honest time on target, and prove a changing PATH on the locked
  // host is not a drift - the single-page-app case host-level hashing exists for.
  // What is asserted is that on-target time GREW across the navigations, not that it
  // reached some total. The total is not this test's business: settling takes as long
  // as it takes, and on a desktop with other windows on it a second or two can land
  // in the home bucket because the Jarvis window really did come to the front for a
  // moment. The buckets are logged for exactly that reason - a surprising total is
  // usually the machine being busy, and it is easier to see that than to guess it.
  await page.send('Runtime.evaluate', { expression: '1' });        // keep-alive
  const workPage = new Page(tabWork.webSocketDebuggerUrl);
  await workPage.open();
  const beforePaths = await serverState();
  for (const path of ['#one', '#two/deep', '#three?q=1']) {
    await workPage.evaluate('location.hash = ' + JSON.stringify(path));
    await sleep(1600);
  }
  st = await serverState();
  const buckets = (s) => JSON.stringify({ onTargetS: s.onTargetS, driftS: s.driftS,
                                          homeS: s.homeS, unknownS: s.unknownS });
  log('buckets before: ' + buckets(beforePaths) + '  after: ' + buckets(st));
  ok(st.drifts === 0 && st.onTargetS > beforePaths.onTargetS,
     'a changing path on the locked site is not a drift, and still counts as time on '
     + 'target',
     JSON.stringify({ drifts: st.drifts,
                      onTargetS: [beforePaths.onTargetS, st.onTargetS] }));

  // 6. THE MOMENT. Switch to the distraction and time the spoken callout.
  const before = await spokenCount();
  const switched = Date.now();
  await cdp('/json/activate/' + tabAway.id);
  log('-> SWITCHED to the distraction; listening for the callout');

  let heard = null, latency = null;
  while (Date.now() - switched < CALLOUT_DEADLINE_MS + 2500) {
    if (await spokenCount() > before) {
      latency = Date.now() - switched;
      heard = await spokenLast();
      break;
    }
    await sleep(100);
  }
  ok(latency !== null && latency <= CALLOUT_DEADLINE_MS,
     'the callout was SPOKEN within ' + CALLOUT_DEADLINE_MS + 'ms of the tab switch',
     latency === null ? 'nothing was spoken at all'
                      : 'took ' + latency + 'ms');
  log('heard after ' + latency + 'ms: ' + JSON.stringify(heard));
  // And it is coloured by what you told it you were doing. Once: the pools take over
  // afterwards, because a line that repeats your own sentence five times is a parrot.
  ok(/invoice importer/i.test(heard || ''),
     'the FIRST callout uses your own words for the work',
     'heard: ' + JSON.stringify(heard));

  st = await serverState();
  ok(st.drifting === true && st.drifts === 1, 'the server counted exactly one drift',
     JSON.stringify({ drifting: st.drifting, drifts: st.drifts }));
  const card = await page.evaluate('__galaxy.session.card');
  ok(card.indexOf('drift') !== -1,
     'the countdown card is tinted for drift while you are away',
     'card="' + card + '"');

  // NAMING THE DRIFT, live. The callout is supposed to say where you went - that is
  // the feature - so this is no longer "no identity anywhere". It is three claims,
  // which is the promise broken into the parts that can each be wrong on their own.
  //
  // One: it said the name out loud. AWAY is iana.org, which is in no map, so this is
  // also the unmapped-host case end to end: the bare domain and nothing else.
  ok(/iana\.org/i.test(heard || ''),
     'the callout NAMED the site you drifted to, by its bare domain',
     'heard: ' + JSON.stringify(heard));
  ok(!/www\.|\/help|example-domains|https?:/i.test(heard || ''),
     'and only the domain: no subdomain, no path, no URL in a spoken line',
     'heard: ' + JSON.stringify(heard));

  // Two: the name is in the sentence and in nothing else. Every other key of the
  // state the browser holds, with the spoken queue taken out of it.
  const held = await clientState();
  const keysOnly = JSON.stringify(Object.assign({}, held, { say: undefined }));
  ok(!/iana|chrome\.exe|Example Domain/i.test(keysOnly),
     'no field the browser received names the app or either site - only the sentence',
     keysOnly.slice(0, 200));
  const namedLines = (held.say || []).filter((l) => /iana\.org/i.test(l.text));
  ok(namedLines.length === 1,
     'exactly one line in the queue names it, and it is the callout',
     JSON.stringify((held.say || []).map((l) => l.text)));

  // Three: and it does not survive. The server takes the line out of the queue a tick
  // after it was delivered, so the name stops existing everywhere at once - which is
  // the difference between saying something and recording it. Polled, because the
  // scrub happens on the server's tick and not on ours.
  const scrubStarted = Date.now();
  const scrubBudget = LABEL_TTL_MS + 6000;
  let scrubbedAfter = null;
  while (Date.now() - scrubStarted < scrubBudget) {
    await sleep(400);
    if (!/iana/i.test(JSON.stringify(await clientState()))) {
      scrubbedAfter = Date.now() - scrubStarted;
      break;
    }
  }
  ok(scrubbedAfter !== null,
     'the named line is GONE from the state the browser holds, within one TTL',
     scrubbedAfter === null ? 'still there after ' + scrubBudget + 'ms'
                            : 'gone after ' + scrubbedAfter + 'ms');
  log('the name was spoken, then scrubbed after ' + scrubbedAfter + 'ms');

  // 7. Back to the work site. Two claims, and they are separated deliberately: the
  //    drift must still be live at the instant of return (otherwise "welcome back"
  //    is being spoken about a drift that quietly resolved itself while nobody was
  //    looking, which would be a bug wearing a passing test), and the return must
  //    then be acknowledged. The acknowledgement is POLLED, like the callout - a
  //    fixed sleep and one sample is a coin toss on whichever side of it the line
  //    happens to land, and it will not always be the same side.
  await sleep(2500);
  st = await serverState();
  ok(st.drifting === true,
     'the drift is still live at the moment of return, not self-resolved',
     JSON.stringify({ drifting: st.drifting, drifts: st.drifts }));
  const beforeBack = await spokenCount();
  const returned = Date.now();
  await cdp('/json/activate/' + tabWork.id);
  log('-> back to the work site');

  let backLine = null;
  while (Date.now() - returned < CALLOUT_DEADLINE_MS + 2500) {
    if (await spokenCount() > beforeBack) { backLine = await spokenLast(); break; }
    await sleep(100);
  }
  ok(backLine !== null, 'coming back is acknowledged out loud',
     'nothing new was spoken in ' + (Date.now() - returned) + 'ms');
  log('said after ' + (Date.now() - returned) + 'ms: ' + JSON.stringify(backLine));
  st = await serverState();
  ok(st.drifting === false, 'the drift is over and the card is calm again',
     JSON.stringify({ drifting: st.drifting,
                      card: await page.evaluate('__galaxy.session.card') }));

  /* ================================================== moving the lock, on purpose ==
   * Everything above is inference: the session chose its target by watching where you
   * settled. Inference is occasionally wrong, so there is an explicit override - and
   * it is driven here from all three surfaces it can be used from, because each one
   * has a different right answer and only one of them is the obvious one.
   *
   *   a work tab      lock THAT, in one read, and forgive the drift you were in
   *   the Jarvis tab  lock NOTHING: re-arm, and say where it will be looking
   *   the card        the press is what brought this tab to the front, so the window
   *                   manager's answer is "the card". Ask the browser instead.
   */

  // --- surface one: a work tab, said out loud ---------------------------------
  // From the distraction, with a counted drift live. That is deliberate: the sentence
  // has to move the lock AND clear the drift, and "forgiven silently" is only a claim
  // worth testing when there was something there to forgive.
  const beforeAway = await spokenCount();
  await cdp('/json/activate/' + tabAway.id);
  const nagLine = await waitLine(beforeAway, CALLOUT_DEADLINE_MS + 2500);
  const preMove = await serverState();
  ok(nagLine !== null && preMove.drifting === true && preMove.drifts === 2,
     'set up: back on the distraction, called out for it, and a drift on the books',
     JSON.stringify({ drifting: preMove.drifting, drifts: preMove.drifts }));

  const sightBefore = await page.evaluate('JSON.stringify(__galaxy.sight.lastSent || null)');
  const beforeMove = await spokenCount();
  // The natural sentence, lead-in and all, because that is how it gets said.
  await say("okay, I'm gonna need you to keep me in this tab.");
  const moveLine = await waitLine(beforeMove, 8000);
  log('said after the sentence: ' + JSON.stringify(moveLine));
  ok(/locked on/i.test(moveLine || ''),
     'saying it from the tab you want locks THAT tab, and says so out loud',
     'said: ' + JSON.stringify(moveLine));
  st = await serverState();
  ok(st.state === 'running' && st.locked === true && st.tabWatched === true &&
     st.deferred === false,
     'in ONE read - no second tick, because you have just told me',
     JSON.stringify({ state: st.state, locked: st.locked, tabWatched: st.tabWatched }));
  const moveLines = await spokenSince(beforeMove);
  ok(!moveLines.some((l) => /^back\b|back at last/i.test(l)),
     'and the drift is forgiven SILENTLY - no "Back. Thank you, sir." for a correction '
     + 'you made yourself',
     JSON.stringify(moveLines));
  ok(st.drifting === false && st.drifts === preMove.drifts - 1 &&
     st.driftS <= preMove.driftS + 0.01,
     'forgiven in the ledger too: the drift is taken back off the count, seconds and all',
     JSON.stringify({ drifts: [preMove.drifts, st.drifts],
                      driftS: [preMove.driftS, st.driftS] }));
  // The collision the ORDER in ask() exists to settle: the screen share's matcher
  // claims "this tab" just as loudly, and if it had won you would have been handed a
  // photograph of the tab instead of having it watched.
  ok(await page.evaluate('__galaxy.sight.isScreenish("lock on this tab")') === true &&
     await page.evaluate('__galaxy.session.isFocusPhrase("lock on this tab")') === true &&
     await page.evaluate('JSON.stringify(__galaxy.sight.lastSent || null)') === sightBefore,
     'the share claims that sentence too and lost: nothing was photographed',
     'lastSent ' + sightBefore + ' -> ' +
     await page.evaluate('JSON.stringify(__galaxy.sight.lastSent || null)'));
  // And the lock really is somewhere else now: a few honest seconds where it used to
  // be a drift, and no callout for any of them.
  const afterMove = await serverState();
  await sleep(3200);
  st = await serverState();
  ok(st.drifts === afterMove.drifts && st.onTargetS > afterMove.onTargetS,
     'the tab that was a distraction ten seconds ago is now simply the work',
     JSON.stringify({ drifts: [afterMove.drifts, st.drifts],
                      onTargetS: [afterMove.onTargetS, st.onTargetS] }));

  // --- surface two: the Jarvis tab, which is the one it must refuse ------------
  await cdp('/json/activate/' + tabGalaxy.id);
  await sleep(1600);                      // a tick, so the server has seen home base
  const beforeArm = await spokenCount();
  await say('lock on this tab');
  const armLine = await waitLine(beforeArm, 8000);
  log('said from home base: ' + JSON.stringify(armLine));
  ok(/lock on where you land/i.test(armLine || ''),
     'said from THIS page it locks nothing and says where it will be looking instead',
     'said: ' + JSON.stringify(armLine));
  st = await serverState();
  ok(st.state === 'arming' && st.deferred === true && st.locked === false &&
     st.tabWatched === false,
     'the deferred lock is re-armed rather than pointed at the page the button is on',
     JSON.stringify({ state: st.state, deferred: st.deferred, locked: st.locked }));
  ok((await page.evaluate('__galaxy.session.card')).indexOf('deferred') !== -1,
     'and the card admits it, instead of showing a confident clock over nothing',
     'card="' + await page.evaluate('__galaxy.session.card') + '"');
  const beforeReland = await spokenCount();
  await cdp('/json/activate/' + tabWork.id);
  const relandLine = await waitLine(beforeReland, 14000);
  ok(/locked on/i.test(relandLine || ''),
     'and the promise is kept: it locks on the next surface you settle on',
     'said: ' + JSON.stringify(relandLine));
  st = await serverState();
  ok(st.locked === true && st.deferred === false && st.tabWatched === true,
     'which leaves the lock on the work site, ready for the button');

  // --- surface three: the pill on the card, and the trap it has to dodge -------
  // A second window on the distraction's host. Without it the trap cannot even be
  // set: the tabs in this window are hidden while home base is in front, and a hidden
  // tab is nobody's idea of the tab you meant.
  spawn(exe, ['--user-data-dir=' + profile, '--new-window', BEHIND],
        { detached: true, stdio: 'ignore' }).unref();
  await sleep(3500);
  const behind = (await cdp('/json/list'))
    .filter((t) => t.type === 'page').find((t) => t.url.includes(BEHIND_FRAG));
  ok(!!behind, 'a second browser window is open behind the card, on another site',
     (await cdp('/json/list')).map((t) => t.url).join(' | '));
  await cdp('/json/activate/' + tabGalaxy.id);       // the card, in front, as at a press
  await sleep(1700);
  const atHome = await serverState();
  ok(atHome.drifting === false,
     'sitting on the Jarvis tab to reach the card is not a drift - home base never '
     + 'counts against you',
     JSON.stringify({ drifting: atHome.drifting, homeS: atHome.homeS }));

  const beforePress = await spokenCount();
  const lockBox = JSON.parse(await page.evaluate(`
    (function () { var r = document.getElementById('focus-lock').getBoundingClientRect();
      return JSON.stringify({x: Math.round(r.left + r.width/2),
                             y: Math.round(r.top + r.height/2),
                             w: Math.round(r.width)}); })()`));
  ok(lockBox.w > 0, 'the LOCK THIS TAB pill is on the card, next to pause and end',
     JSON.stringify(lockBox));
  for (const type of ['mousePressed', 'mouseReleased']) {
    await page.send('Input.dispatchMouseEvent',
      { type, x: lockBox.x, y: lockBox.y, button: 'left', clickCount: 1 });
  }
  const pillNow = JSON.parse(await page.evaluate(`JSON.stringify({
    text: document.getElementById('focus-lock').textContent,
    done: document.getElementById('focus-lock').classList.contains('done')})`));
  ok(/^locked$/i.test(pillNow.text.trim()) && pillNow.done === true,
     'it flashes LOCKED from the press itself, not from the reply - the press is a fact',
     JSON.stringify(pillNow));
  const pressLine = await waitLine(beforePress, 8000);
  log('said after the press: ' + JSON.stringify(pressLine));
  ok(/locked on/i.test(pressLine || ''),
     'and it locks the tab BEHIND the card, where reading the foreground would have '
     + 'answered "the card"',
     'said: ' + JSON.stringify(pressLine));
  st = await serverState();
  ok(st.locked === true && st.tabWatched === true && st.deferred === false,
     'a site, then: not this page, not an application, and not a re-arm',
     JSON.stringify({ locked: st.locked, tabWatched: st.tabWatched,
                      deferred: st.deferred }));
  await sleep(LOCK_FLASH_MS + 600);
  const pillLater = JSON.parse(await page.evaluate(`JSON.stringify({
    text: document.getElementById('focus-lock').textContent,
    done: document.getElementById('focus-lock').classList.contains('done')})`));
  ok(/lock this tab/i.test(pillLater.text) && pillLater.done === false,
     'and goes back to being an offer a second later, so the card is never stuck '
     + 'mid-press',
     JSON.stringify(pillLater));

  /* WHICH site did it lock? The page is never told, so it is proved the only way that
     leaves the privacy intact: by behaviour. The window behind the card stops being a
     drift, and the site that was the target until the press starts being one. */
  const beforeProof = await serverState();
  await cdp('/json/activate/' + behind.id);
  await sleep(3400);
  st = await serverState();
  ok(st.drifting === false && st.drifts === beforeProof.drifts &&
     st.onTargetS > beforeProof.onTargetS,
     'the window behind the card is the target now: working in it is not a drift',
     JSON.stringify({ drifting: st.drifting, drifts: [beforeProof.drifts, st.drifts],
                      onTargetS: [beforeProof.onTargetS, st.onTargetS] }));
  const beforeOld = await spokenCount();
  await cdp('/json/activate/' + tabWork.id);
  const oldLine = await waitLine(beforeOld, CALLOUT_DEADLINE_MS + 2500);
  st = await serverState();
  ok(oldLine !== null && st.drifting === true,
     'and the site it was watching before the press is now a distraction - the lock '
     + 'moved, proved without the browser being told one host',
     'said: ' + JSON.stringify(oldLine) + ' drifting=' + st.drifting);
  await cdp('/json/close/' + behind.id);             // tidy the extra window away
  await sleep(600);
  // And once more, in the third phrasing, to leave the session on target and quiet for
  // the report card - which is also the ordinary use of the thing: the lock is wrong,
  // you are already looking at the right surface, you say so and carry on.
  const beforeSettle = await spokenCount();
  await say('this is the tab');
  const settleLine = await waitLine(beforeSettle, 8000);
  st = await serverState();
  ok(/locked on/i.test(settleLine || '') && st.drifting === false && st.locked === true,
     '"this is the tab" works as well as "lock on this tab", and ends the drift with it',
     'said: ' + JSON.stringify(settleLine) + ' drifting=' + st.drifting);

  // Long enough for the ledger to take it seriously rather than call it a mis-tap.
  while ((await serverState()).elapsedS < 34) await sleep(1000);

  // 8. End it, and hear the report card.
  await cdp('/json/activate/' + tabGalaxy.id);
  await sleep(800);
  const beforeReport = await spokenCount();
  const endBox = await page.evaluate(`
    (function () { var r = document.getElementById('focus-end').getBoundingClientRect();
      return JSON.stringify({x: Math.round(r.left + r.width/2),
                             y: Math.round(r.top + r.height/2)}); })()`);
  const end = JSON.parse(endBox);
  for (const type of ['mousePressed', 'mouseReleased']) {
    await page.send('Input.dispatchMouseEvent',
      { type, x: end.x, y: end.y, button: 'left', clickCount: 1 });
  }
  await sleep(2000);
  ok(await spokenCount() > beforeReport, 'ending the session speaks a report card');
  const report = await spokenLast();
  log('REPORT: ' + JSON.stringify(report));
  st = await serverState();
  ok(st.state === 'ended' && !!st.report, 'the session is over and has a report',
     JSON.stringify({ state: st.state, endedReason: st.endedReason }));
  ok(/on target/i.test(report) && /percent clean/i.test(report),
     'the report gives minutes on target out of planned, and a clean percentage');
  ok(/drift/i.test(report), 'the report names the drift count');
  ok(/invoice importer/i.test(report),
     'and the report card is about what you said you sat down to do',
     'report: ' + JSON.stringify(report));
  ok(st.sessions >= 1, 'the aggregates-only ledger recorded the session',
     JSON.stringify({ sessions: st.sessions, streak: st.streak, best: st.bestStreak }));
  log('ledger: ' + JSON.stringify({ sessions: st.sessions, streak: st.streak,
                                    best: st.bestStreak, clean: st.cleanPct + '%' }));

  // 9. A reload must REJOIN, not restart - and must not replay the callouts.
  await galaxy('/focus', { cmd: 'start', minutes: 5 });
  await sleep(1500);
  await page.send('Page.enable');
  await page.send('Page.reload', { ignoreCache: true });
  await sleep(3500);
  const fresh = new Page((await cdp('/json/list'))
    .find((t) => t.url.includes('127.0.0.1:4700')).webSocketDebuggerUrl);
  await fresh.open();
  await fresh.send('Runtime.enable');
  const rejoined = JSON.parse(
    await fresh.evaluate('JSON.stringify(__galaxy.session.state)') || 'null');
  ok(rejoined && (rejoined.state === 'arming' || rejoined.state === 'running') &&
     rejoined.elapsedS >= 1,
     'a reloaded tab rejoins the session in progress instead of starting a new one',
     JSON.stringify(rejoined && { state: rejoined.state, elapsedS: rejoined.elapsedS }));
  ok(await fresh.evaluate('__galaxy.session.spokenSeq') >= (rejoined ? rejoined.seq : 0),
     'the reloaded tab adopted the say-sequence, so no callout is spoken twice',
     'spokenSeq=' + await fresh.evaluate('__galaxy.session.spokenSeq') +
     ' seq=' + (rejoined && rejoined.seq));
  fresh.close();
  await galaxy('/focus', { cmd: 'abort' });     // leave nothing running behind us
  page.close();
  workPage.close();
}

main().catch((e) => {
  failures.push('the run itself: ' + e.message);
  console.log('\n  ERROR ' + e.message + '\n' + (e.stack || ''));
}).finally(async () => {
  try { await galaxy('/focus', { cmd: 'abort' }); } catch { /* server may be gone */ }
  try { await cdp('/json/close/x'); } catch { /* ignore */ }
  if (chrome) { try { chrome.kill(); } catch { /* ignore */ } }
  await sleep(700);
  try { rmSync(profile, { recursive: true, force: true }); } catch { /* windows */ }
  console.log('\n  ' + checks + ' checks, ' + failures.length + ' failed\n');
  failures.forEach((f) => console.log('    FAILED: ' + f));
  if (failures.length) console.log('');
  process.exit(failures.length ? 1 : 0);
});
