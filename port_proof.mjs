/* The flag, and the two sessions it is the difference between.
 *
 * Tab-level locking needs Chrome's DevTools port. launch-chrome.ps1 exists so that
 * opening the port is one double-click instead of something you remember, and the
 * start line exists so that FORGETTING is something you hear rather than something
 * you find out about half an hour later. Two halves, and this run does both against
 * the same machine, back to back:
 *
 *   WITH the port  (launched by the script itself)
 *     -> /health says focus.cdp = true
 *     -> the start line makes no excuses
 *     -> settling on a work site locks the SITE: tabWatched = true
 *     -> drifting to another host is called out BY NAME, within three seconds
 *
 *   WITHOUT the port  (an ordinary Chrome, exactly as double-clicking it gives you)
 *     -> /health says focus.cdp = false
 *     -> the start line gains one clause, out loud, before the question:
 *        "Tab-level locking is unavailable, sir - Chrome was not launched with the
 *         DevTools port, so I shall watch the application only."
 *     -> and the session still runs
 *
 * THE LAW being tested is the second half, and it is the whole reason this file is
 * not just focus_live.mjs again: a session that silently watched the application
 * while you believed it was watching the site would pass every other test in this
 * repository. Silence about a missing lock is a wrong lock wearing a costume.
 *
 * Nothing is mocked. It runs the real PowerShell script, kills and relaunches a real
 * Chrome twice, and reads what the PAGE actually spoke (speechSynthesis is wrapped,
 * not replaced - you should hear this run) for the half where a page is readable, and
 * the server's own say-queue for the half where, by definition, it is not.
 *
 * It finishes by leaving your ORDINARY Chrome running, because that is the state the
 * second half needs and it is also your real profile with your real tabs. Double-click
 * the desktop shortcut to get the port back.
 *
 * Usage:  node port_proof.mjs          (server.py must be running on 4700)
 */

import { spawn, execFileSync } from 'node:child_process';
import { existsSync } from 'node:fs';

const GALAXY = 'http://127.0.0.1:4700';
const CDP = 'http://127.0.0.1:9222';
const SCRIPT = 'launch-chrome.ps1';
const WORK = 'https://example.com/';           // what you said you would do
const AWAY = 'https://www.iana.org/';          // what you did instead
const CALLOUT_DEADLINE_MS = 3000;
const CLAUSE = /tab-level locking is unavailable/i;
const NET_TIMEOUT_MS = 12000;

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

async function galaxy(path, body) {
  const res = await fetch(GALAXY + path, body ? {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal: AbortSignal.timeout(NET_TIMEOUT_MS),
  } : { signal: AbortSignal.timeout(NET_TIMEOUT_MS) });
  return res.json();
}

async function cdp(path, method = 'GET') {
  const res = await fetch(CDP + path,
                         { method, signal: AbortSignal.timeout(NET_TIMEOUT_MS) });
  const text = await res.text();
  try { return JSON.parse(text); } catch { return text; }
}

/* The same minimal CDP client the other live harnesses use: one socket, one
   expression at a time, and a deadline on everything - a browser that stops
   answering is a result, not a reason to hang. */
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
    const r = await this.send('Runtime.evaluate',
                              { expression, returnByValue: true, awaitPromise: true });
    if (r.error) throw new Error(r.error.message);
    if (r.result && r.result.exceptionDetails) {
      throw new Error('page threw: ' + r.result.exceptionDetails.text);
    }
    return r.result && r.result.result ? r.result.result.value : undefined;
  }
  close() { try { this.ws.close(); } catch { /* already gone */ } }
}

/* The server's own queue, which is what the browser will speak. Used for the half of
   this run where there is no readable page to ask - that being the whole point of it. */
const serverState = async () => (await galaxy('/focus')).focus;
const serverSaid = async () => {
  const st = await serverState();
  const say = st.say || [];
  return say.length ? say[say.length - 1].text : '';
};
const abort = async () => { try { await galaxy('/focus', { cmd: 'abort' }); } catch { } };

/* focus.py caches capability() for CAPABILITY_TTL_S, so every claim about cdp waits
   the cache out rather than reading a boolean that was decided before the browser
   existed. Polled, not slept: the shape of the answer is the thing being asserted. */
async function waitCdp(want, budgetMs) {
  const until = Date.now() + budgetMs;
  let focus = null;
  for (;;) {
    focus = (await galaxy('/health')).focus;
    if (!!focus.cdp === want || Date.now() > until) return focus;
    await sleep(700);
  }
}

let plainChrome = null;

async function main() {
  console.log('\n  the DevTools port: the launcher, and the honest downgrade\n');

  if (!existsSync(SCRIPT)) throw new Error('run me from the project root: ' + SCRIPT + ' is not here');
  const exe = CHROMES.find((p) => existsSync(p));
  if (!exe) throw new Error('no chrome.exe found in the usual places');

  const up = await galaxy('/health');
  ok(up.ok === true && up.focus.app === true,
     'the server is up and can read the frontmost application',
     JSON.stringify(up.focus));
  await abort();                      // nothing of ours, and nothing of anyone else's

  // =========================================================== WITH THE PORT ====
  // Half one, and the script does the work: it kills the strays, relaunches with the
  // flag and a profile of its own (the default profile is refused the port by Chrome
  // itself since 136), opens the viewer, and then proves it rather than assuming.
  log('running ' + SCRIPT + ' - this closes any Chrome you have open');
  let out = '';
  try {
    out = execFileSync('powershell', ['-NoProfile', '-ExecutionPolicy', 'Bypass',
                                      '-File', './' + SCRIPT],
                       { encoding: 'utf8', timeout: 120000 });
  } catch (e) {
    out = (e.stdout || '') + (e.stderr || '');
    ok(false, SCRIPT + ' exited cleanly', out.trim().split('\n').slice(-4).join(' | '));
  }
  out.trim().split(/\r?\n/).forEach((l) => l.trim() && log('  | ' + l.trim()));
  ok(/DevTools port 9222 is open/.test(out),
     'the script opened the DevTools port and said so');
  ok(/focus\.cdp = true/.test(out),
     'the script checked the SERVER too, rather than trusting its own launch');

  const cap = await waitCdp(true, 12000);
  ok(cap.cdp === true, '/health reports focus.cdp = true: a site can be locked',
     JSON.stringify(cap));

  // Two more tabs, on genuinely different hosts with different titles - the reader
  // joins the OS window to a tab by title, so two pages called the same thing would
  // be a test rigged to pass.
  await cdp('/json/new?' + encodeURIComponent(WORK), 'PUT');
  await cdp('/json/new?' + encodeURIComponent(AWAY), 'PUT');
  await sleep(2500);
  const tabs = (await cdp('/json/list')).filter((t) => t.type === 'page');
  const find = (frag) => tabs.find((t) => t.url.includes(frag));
  const tabGalaxy = find('127.0.0.1:4700');
  const tabWork = find('example.com');
  const tabAway = find('iana.org');
  ok(!!(tabGalaxy && tabWork && tabAway), 'three tabs: home base, work, distraction',
     tabs.map((t) => t.url).join(' | '));
  if (!tabGalaxy) throw new Error('the script did not open the viewer');

  const page = new Page(tabGalaxy.webSocketDebuggerUrl);
  await page.open();
  await page.send('Runtime.enable');
  /* THE FUNNEL, NOT THE ENGINE. Wrapped, not stubbed: the line is recorded AND still
     comes out of the speakers. speakLine() is the one function in that page that speaks,
     and it is what is watched here - because on the local voice (piper) there is no
     utterance to intercept at all, so a wrapper around speechSynthesis.speak would have
     recorded nothing but the warm-up blank and every claim below would have failed for
     want of an instrument rather than for want of a voice. */
  const hasFunnel = '!!(window.__galaxy && __galaxy.speech && __galaxy.speech.speakLine)';
  const funnelBy = Date.now() + 30000;
  let funnel = false;
  while (!(funnel = await page.evaluate(hasFunnel)) && Date.now() < funnelBy) {
    await sleep(250);
  }
  ok(funnel === true, 'the viewer is up and exposes its speech funnel, speakLine()');
  await page.evaluate(`
    (function () {
      if (window.__spoken) return 'already';
      window.__spoken = [];
      addEventListener('speakLine', function (ev) {
        window.__spoken.push(String((ev.detail && ev.detail.text) || ''));
      });
      return 'wrapped';
    })()`);
  const spokenCount = () => page.evaluate('window.__spoken.length');
  const spokenLast = () => page.evaluate(
    'window.__spoken.length ? window.__spoken[window.__spoken.length-1] : ""');
  /* The line that is the START line, found by what it says rather than by being the
     most recent thing spoken. On a fresh profile the microphone is off, so the viewer
     adds its own "my ears are off" line immediately afterwards - reading the last
     line would be reading that one, and a check that passes because it looked at the
     wrong sentence is worse than no check. */
  const spokenAll = async () => JSON.parse(
    await page.evaluate('JSON.stringify(window.__spoken)'));
  const spokenMatching = async (re) =>
    (await spokenAll()).filter((s) => re.test(s)).pop() || '';
  async function waitLine(mark, ms) {
    const until = Date.now() + ms;
    while (Date.now() < until) {
      if (await spokenCount() > mark) return await spokenLast();
      await sleep(120);
    }
    return null;
  }

  // A REAL mouse press on FOCUS. Synthetic clicks do not unlock audio, and a run that
  // asserts about what was "heard" while the speaker is still locked is asserting
  // about a queue.
  await cdp('/json/activate/' + tabGalaxy.id);
  await sleep(700);
  const box = JSON.parse(await page.evaluate(`
    (function () { var r = document.getElementById('focusbtn').getBoundingClientRect();
      return JSON.stringify({x: Math.round(r.left + r.width/2),
                             y: Math.round(r.top + r.height/2)}); })()`));
  for (const type of ['mousePressed', 'mouseReleased']) {
    await page.send('Input.dispatchMouseEvent',
                    { type, x: box.x, y: box.y, button: 'left', clickCount: 1 });
  }
  await sleep(1600);
  let st = await serverState();
  ok(st.state === 'arming', 'the FOCUS button started a session', 'state=' + st.state);
  const started = await spokenMatching(/lock on there/i);
  log('said: ' + JSON.stringify(started));
  ok(/^\d+ minutes, sir/.test(started),
     'the start line was spoken out loud in the page, not only queued',
     'spoken: ' + JSON.stringify(await spokenAll()));
  ok(!CLAUSE.test(started),
     'with the port open the start line makes no excuses about the lock',
     'said: ' + JSON.stringify(started));
  ok(/what are we focusing on/i.test(started),
     'and it still ends with the question, so the answer window opens as usual');

  // The answer, through the same door a dictated sentence comes in by. The first
  // callout uses your own words, which is how the named line below is recognisable
  // as the FIRST one rather than a pool line that happened to match.
  await sleep(1200);
  await page.evaluate('__galaxy.session.answer("the invoice importer")');
  await sleep(1200);

  // Settle on the work site. Not the tab you clicked in - the first one that is not
  // home base and that you are still on a tick later.
  let mark = await spokenCount();
  const wentToWork = Date.now();
  await cdp('/json/activate/' + tabWork.id);
  log('-> activated the work site; waiting for the lock');
  const lockLine = await waitLine(mark, 14000);
  log('said after ' + (Date.now() - wentToWork) + 'ms: ' + JSON.stringify(lockLine));
  st = await serverState();
  ok(st.locked === true && st.tabWatched === true,
     'it locked the SITE as well as the application - that is what the port buys',
     JSON.stringify({ locked: st.locked, tabWatched: st.tabWatched,
                      appWatched: st.appWatched }));
  ok(!/watch the application/i.test(lockLine || ''),
     'and it did not have to fall back to watching the application only',
     'said: ' + JSON.stringify(lockLine));

  // THE MOMENT. A different host, and the callout has to name it within three
  // seconds - a name being precisely the thing an app-level lock could never say.
  mark = await spokenCount();
  const switched = Date.now();
  await cdp('/json/activate/' + tabAway.id);
  log('-> SWITCHED to the distraction; listening');
  let heard = null, latency = null;
  while (Date.now() - switched < CALLOUT_DEADLINE_MS + 2500) {
    if (await spokenCount() > mark) {
      latency = Date.now() - switched;
      heard = await spokenLast();
      break;
    }
    await sleep(100);
  }
  log('heard after ' + latency + 'ms: ' + JSON.stringify(heard));
  ok(latency !== null && latency <= CALLOUT_DEADLINE_MS,
     'the callout was spoken within ' + CALLOUT_DEADLINE_MS + 'ms of the switch',
     latency === null ? 'nothing was spoken at all' : 'took ' + latency + 'ms');
  ok(/iana\.org/i.test(heard || ''),
     'and it NAMED the site you drifted to - the tab-level name, out loud',
     'heard: ' + JSON.stringify(heard));
  ok(!/www\.|\/help|https?:/i.test(heard || ''),
     'the bare domain and nothing else: no subdomain, no path, no URL');
  st = await serverState();
  ok(st.drifts === 1, 'one drift, counted once', 'drifts=' + st.drifts);
  await abort();
  page.close();

  // ======================================================== WITHOUT THE PORT ====
  // Half two: Chrome exactly as double-clicking Chrome gives you it. Default profile,
  // no flag, no port - and therefore no readable tab, which is why every claim from
  // here is read from the server's own say-queue rather than from a page.
  log('closing it, and starting an ORDINARY Chrome - no flag, your own profile');
  try { execFileSync('taskkill', ['/IM', 'chrome.exe', '/F'], { stdio: 'ignore' }); } catch { }
  await sleep(2000);
  plainChrome = spawn(exe, [GALAXY + '/'], { detached: true, stdio: 'ignore' });
  await sleep(4000);

  let portAnswered = true;
  try { await cdp('/json/version'); } catch { portAnswered = false; }
  ok(portAnswered === false,
     'an ordinary Chrome has no DevTools port at all',
     portAnswered ? 'something is still listening on 9222' : '');

  const bare = await waitCdp(false, 14000);
  ok(bare.cdp === false,
     '/health reports focus.cdp = false, so tab-level locking is unavailable',
     JSON.stringify(bare));

  const say = await galaxy('/focus', { cmd: 'start', minutes: 5 });
  const line = say.answer || await serverSaid();
  log('said: ' + JSON.stringify(line));
  ok(CLAUSE.test(line),
     'THE LAW: the start line says the tab-level lock is unavailable, out loud',
     'said: ' + JSON.stringify(line));
  ok(/watch the application only/i.test(line),
     'and says what it will do instead - watch the application',
     'said: ' + JSON.stringify(line));
  ok(/devtools port/i.test(line),
     'and names the cause, which is the thing the script fixes');
  const qAt = line.toLowerCase().indexOf('what are we focusing on');
  ok(qAt !== -1 && line.toLowerCase().indexOf('tab-level locking') < qAt,
     'the clause comes BEFORE the question, so nothing is said into an open microphone',
     'said: ' + JSON.stringify(line));

  // Said once. The session goes on running, and the caveat does not come back every
  // tick - a warning you hear twenty times an hour is a warning you stop hearing.
  st = await serverState();
  ok(st.state === 'arming' && st.plannedS === 300,
     'and the session still runs: a missing lock is a downgrade, not a refusal',
     JSON.stringify({ state: st.state, plannedS: st.plannedS }));
  // Every line that carries the clause, by seq, watched across seven seconds of ticks.
  // A set, because "said once" is a claim about distinct lines and not about how many
  // times a poll happened to see the same one.
  const clauseSeqs = new Set();
  const watchUntil = Date.now() + 7000;
  while (Date.now() < watchUntil) {
    const now = await serverState();
    (now.say || []).forEach((l) => { if (CLAUSE.test(l.text)) clauseSeqs.add(l.seq); });
    await sleep(500);
  }
  ok(clauseSeqs.size === 1,
     'and it is spoken ONCE: seven seconds of ticks add no second caveat',
     'seqs carrying the clause: ' + JSON.stringify([...clauseSeqs]));
  await abort();

  log('leaving your ordinary Chrome open - double-click the shortcut for the port');
}

main().catch((e) => {
  failures.push('the run itself: ' + e.message);
  console.log('\n  ERROR ' + e.message + '\n' + (e.stack || ''));
}).finally(async () => {
  await abort();
  console.log('\n  ' + checks + ' checks, ' + failures.length + ' failed\n');
  failures.forEach((f) => console.log('    FAILED: ' + f));
  if (failures.length) console.log('');
  process.exit(failures.length ? 1 : 0);
});
