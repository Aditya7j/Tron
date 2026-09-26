/* THE LOCK THAT LOCKS - the whole of PART F, against a real browser, end to end.
 *
 * Six sections, in the order the feature is actually lived:
 *
 *   1  THE PREMISE          no debugging port anywhere, a server running THIS code
 *   2  THE PORTLESS PRESS   LOCK THIS TAB with no port -> it says so, and offers the
 *                           hand that fixes it; NO is admitted on the card
 *   3  THE CONSENT          YES runs tools/relaunch_chrome.py for real, the port comes
 *                           up, and the lock completes ITSELF with teeth
 *   4  THE TEETH            leaving the locked tab is noticed inside 1.5 s and called
 *                           out once; coming back is said once; a second drift inside
 *                           thirty seconds offers the summon; YES brings him back
 *   5  THE UNLOCK           the session ends and NOTHING is left watching
 *   6  THE EPISODE          every line the session said, in order, for the lookbook
 *
 * WHY IT CANNOT BE DONE IN PROCESS. Every claim in PART F is a claim about a browser:
 * that bit 1 of the front expression drops when you open a tab beside the locked one,
 * that /json/activate raises a window as well as a tab, that a politely closed Chrome
 * writes a session the relaunch can restore. A fake reader can be made to say any of
 * that. So there are no fakes here: a real Chrome, the real launcher, the real hand,
 * the real gate, and the server that is actually running on 4700.
 *
 * IT MUST RUN SOLO, and it checks: section 1 refuses to start if anything is already
 * answering on 9222, 9223 or 9224, because the whole of section 2 is about there being
 * no port and a leftover harness browser would make it pass while proving nothing.
 *
 * WHAT IT TOUCHES, and how it puts it back:
 *   - It uses the LAUNCHER'S profile (%LOCALAPPDATA%\Jarvis\devtools-profile-chrome),
 *     because tools/relaunch_chrome.py closes exactly that profile and restores exactly
 *     its tabs - that is the chain under test. So the profile's four session files are
 *     copied aside before anything is launched and copied back at the end, and the
 *     browser is closed politely on the way out. The boss's ordinary Chrome, on the
 *     DEFAULT profile, is never touched: the launcher's step 2 is scoped by command
 *     line and so is every close in this file.
 *   - It runs a REAL session on the server and ends it with `abort`, which records no
 *     ledger row and moves no streak: an instrument that edits what it measures is not
 *     an instrument. That is also why nothing here calls `finish`.
 *   - Two work tabs are opened and both are closed again.
 *
 * Usage:  node lock_proof.mjs        (with server.py running on 4700, nothing else)
 */

import { spawn, spawnSync } from 'node:child_process';
import { existsSync, mkdirSync, copyFileSync, readdirSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const GALAXY = 'http://127.0.0.1:4700';
const PORTS = [9222, 9223, 9224];       // the three focus.py looks at, in its order
const PORT = 9222;                      // the one launch-chrome.ps1 opens
const CDP = 'http://127.0.0.1:' + PORT;
const WORK_A = 'https://example.com/';
const WORK_B = 'https://example.com/?galaxy=b';
const HOST = 'example.com';
/* The same expression focus.py evaluates, stated here so this file would notice the two
   going out of step: bit 1 is "the active tab of my window", bit 2 is "my window has the
   keyboard". The lock rests on bit 1 and nothing else. */
const FRONT = "((document.visibilityState==='visible')?1:0)+(document.hasFocus()?2:0)";
const PROFILE = join(process.env.LOCALAPPDATA || '', 'Jarvis', 'devtools-profile-chrome');
/* WHAT THIS CHROME ACTUALLY CALLS ITS SESSION.
   The four names below are pre-M100 Chrome, and on Chrome/153 not one of them exists: the
   session lives in Default/Sessions/ as Session_<timestamp> and Tabs_<timestamp>. The list
   was a comfort that copied nothing - "copied 0 session file(s) aside" followed, in teardown,
   by "put 0 session file(s) back", which reads like a safety net and is not one. If a run of
   this harness ever has to force a browser that would not close, the boss's real tabs go with
   it and both lines still print. Match on the pattern, and keep the legacy names for an older
   Chrome that might still write them. */
const SESSION_DIRS = [join('Default', 'Sessions'), 'Default', ''];
const LEGACY_SESSION_FILES = ['Last Session', 'Last Tabs', 'Current Session', 'Current Tabs'];
function isSessionFile(f) {
  return /^(Session|Tabs)_\d+$/.test(f) || LEGACY_SESSION_FILES.includes(f);
}
const BACKUP = join(tmpdir(), 'lockproof-session-' + Date.now());
const NET_MS = 10000;
const HAND_MS = 170000;             // the relaunch hand's own timeout is 120 s
const DRIFT_BUDGET_MS = 1500;       // the mandate's figure, asserted and not assumed
const HOLD_MS = 45000;              // long enough to cover a press over three dead ports
const PRESS_MS = 40000;             // the press itself is the slowest call in the file

/* THE SENTENCES, copied out of the mandate rather than imported from focus.py. An
   assertion that reads its expected value out of the thing under test proves only that
   the file is self-consistent; these are the words the boss was promised. */
const SAY = {
  noport: 'I cannot lock a tab, sir - Chrome has no debugging port open.',
  declined: 'Tab-level locking is off, then, sir: no debugging port, and you would ' +
            'rather I did not restart the browser. I shall watch the application only.',
  askRelaunch: 'I need Chrome relaunched with the debugging port to lock a tab, sir. ' +
               'Shall I?',
  askSummon: 'Shall I bring you back?',
  summoned: 'Here you are, sir - back where you said you would be.',
  settled: 'Locked on, sir.',
  armed: "Go to it, sir. I'll lock on where you land.",
  back: 'Back. Thank you, sir.',
};
/* Tier one of the locked-tab pool, rendered. Four lines, chosen at random, so the
   assertion is membership - and the first of them is the mandate's own sentence. */
const LOCKED_TIER1 = (n) => [
  'You have left the locked tab, sir - drift ' + n + '.',
  'That is not the locked tab, sir.',
  'The tab you asked me to hold you to is still open, sir. This is not it.',
  'Off the locked tab, sir.',
];

const CHROMES = [
  'C:/Program Files/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Google/Chrome/Application/chrome.exe',
  process.env.LOCALAPPDATA + '/Google/Chrome/Application/chrome.exe',
];

const t0 = Date.now();
const failures = [];
const notes = [];
const episode = [];          // every say line, in order, for the lookbook
let pending = [];            // the ones a step has not looked at yet
let seqSeen = 0;
let checks = 0;
let backedUp = false;
let presses = 0;             // LOCK THIS TAB, counted, per session

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
function note(text) { notes.push(text); console.log('  ' + at() + '  note  ' + text); }

/* ---------------------------------------------------------------- the two servers */

async function galaxy(path, body, ms) {
  const res = await fetch(GALAXY + path, body
    ? { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body), signal: AbortSignal.timeout(ms || NET_MS) }
    : { signal: AbortSignal.timeout(ms || NET_MS) });
  return res.json();
}
async function hand(path, body, ms) {
  const res = await fetch(GALAXY + path, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body), signal: AbortSignal.timeout(ms || NET_MS) });
  return res.json();
}
async function cdp(path, method = 'GET', port = PORT) {
  const res = await fetch('http://127.0.0.1:' + port + path,
                          { method, signal: AbortSignal.timeout(NET_MS) });
  const text = await res.text();
  try { return JSON.parse(text); } catch { return text; }
}
async function portAlive(port) {
  try { await cdp('/json/version', 'GET', port); return true; } catch { return false; }
}
async function pages() {
  const list = await cdp('/json/list');
  return (Array.isArray(list) ? list : []).filter((t) => t.type === 'page');
}

/* One CDP method, one reply, one socket - closed before it is returned from, because
   section 5 asserts that no socket is left attached to the locked tab and a socket this
   file forgot to close would answer that question for it. */
function sock(url) {
  let id = 0; const waiting = new Map();
  const ws = new WebSocket(url);
  const ready = new Promise((go, no) => { ws.onopen = () => go(); ws.onerror = no; });
  ws.onmessage = (ev) => {
    const m = JSON.parse(ev.data);
    const w = waiting.get(m.id); if (w) { waiting.delete(m.id); w(m); }
  };
  return {
    ready,
    send: (method, params) => new Promise((go, no) => {
      const n = ++id;
      const bomb = setTimeout(() => no(new Error(method + ' never answered')), NET_MS);
      waiting.set(n, (m) => { clearTimeout(bomb); go(m); });
      ws.send(JSON.stringify({ id: n, method, params: params || {} }));
    }),
    close: () => { try { ws.close(); } catch { /* already gone */ } },
  };
}
async function bits(target) {
  const s = sock(target.webSocketDebuggerUrl);
  await s.ready;
  try {
    const r = await s.send('Runtime.evaluate', { expression: FRONT, returnByValue: true });
    return r.result && r.result.result ? r.result.result.value : null;
  } finally { s.close(); }
}

/* windowsHide, and it is not cosmetic: without it every one of these calls flashes a
   console window, and a console window appearing takes the foreground away from the
   browser this harness has just spent a second raising. */
const ps = (cmd) => spawnSync('powershell', ['-NoProfile', '-Command', cmd],
                              { encoding: 'utf8', windowsHide: true }).stdout.trim();
/* Chrome processes ON THE LAUNCHER'S PROFILE and nothing else, matched the way
   launch-chrome.ps1 matches them: by command line. The boss's ordinary browsing is on
   another profile and no line in this file can see it. */
const MINE = "Get-CimInstance Win32_Process -Filter \"Name='chrome.exe'\" | " +
             "Where-Object { $_.CommandLine -and $_.CommandLine -like '*devtools-profile-chrome*' }";

function chromeOnProfile() { return Number(ps('@(' + MINE + ').Count') || '0'); }

/* WM_CLOSE, which is what the X button posts and the only exit that writes the session
   files the relaunch restores. Never Stop-Process here: a force kill is a crash, and a
   crash is exactly what the launcher's own comment says loses the tabs. */
function closeProfileChromePolitely(reason) {
  if (!chromeOnProfile()) return true;
  log('closing the profile browser politely (' + reason + ')');
  ps(MINE + ' | ForEach-Object { $p = Get-Process -Id $_.ProcessId ' +
     '-ErrorAction SilentlyContinue; if ($p -and $p.MainWindowHandle -ne 0) ' +
     '{ [void]$p.CloseMainWindow() } }');
  for (let i = 0; i < 40; i++) {
    if (!chromeOnProfile()) return true;
    spawnSync('powershell', ['-NoProfile', '-Command', 'Start-Sleep -Milliseconds 250'],
              { encoding: 'utf8' });
  }
  return false;
}

/* THE FOREGROUND, TAKEN AND THEN VERIFIED - and the verification is the point.
 *
 * The session reads the front window with GetForegroundWindow. Everything in sections 2
 * and 3 is a claim about what happens when a BROWSER is the thing in front, so a raise
 * that quietly failed would not make this harness fail: it would make it pass a different
 * feature, the one where nothing of ours is in front and there is correctly nothing to
 * offer. That is precisely what happened before this function checked its work.
 *
 * WScript.Shell's AppActivate is not enough. Windows only lets a process set the
 * foreground if it owns it already or has just been launched, which is why a raise works
 * immediately after a launch and silently does nothing eight seconds later. The documented
 * way round it is to attach our input queue to the thread that DOES own the foreground and
 * ask from inside its rights, so that is what Raise does - and then FrontPid is read back
 * and compared, because a bool from SetForegroundWindow is not the same fact.
 */
const FG_CS =
  'using System; using System.Runtime.InteropServices; public static class Fg { ' +
  '[DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow(); ' +
  '[DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint p); ' +
  '[DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h); ' +
  '[DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int c); ' +
  '[DllImport("user32.dll")] public static extern bool AttachThreadInput(uint a, uint b, bool t); ' +
  '[DllImport("kernel32.dll")] public static extern uint GetCurrentThreadId(); ' +
  'public static uint FrontPid() { uint p; GetWindowThreadProcessId(GetForegroundWindow(), out p); return p; } ' +
  'public static bool Raise(IntPtr h) { uint p; uint theirs = GetWindowThreadProcessId(GetForegroundWindow(), out p); ' +
  'uint mine = GetCurrentThreadId(); AttachThreadInput(mine, theirs, true); ShowWindow(h, 9); ' +
  'bool got = SetForegroundWindow(h); AttachThreadInput(mine, theirs, false); return got; } }';

/* HELD in front, not merely put there, for as long as a press takes.
 *
 * Measured on this machine: a portless press costs the server six to ten seconds - three
 * dead debugging ports, probed - and it reads the foreground TWICE inside that, once to
 * decide what is in front and once to decide whether offering to relaunch the browser
 * would help. The editor this harness was written in reclaims the foreground somewhere in
 * between, and then the second read honestly reports no browser, the offer is honestly
 * withheld, and the run passes a feature nobody asked about. A boss pressing the pill has
 * his browser in front for the whole of the press, so that is what this reproduces.
 */
function holdChromeForward(ms) {
  const child = spawn('powershell', ['-NoProfile', '-Command',
    "Add-Type -TypeDefinition '" + FG_CS + "'; " +
    '$t = @(' + MINE + ' | ForEach-Object { Get-Process -Id $_.ProcessId ' +
    '-ErrorAction SilentlyContinue } | Where-Object { $_.MainWindowHandle -ne 0 }); ' +
    'if (-not $t.Count) { exit }; ' +
    '$end = (Get-Date).AddMilliseconds(' + ms + '); ' +
    'while ((Get-Date) -lt $end) { [void][Fg]::Raise($t[0].MainWindowHandle); ' +
    'Start-Sleep -Milliseconds 300 }'],
    { detached: true, stdio: 'ignore', windowsHide: true });
  child.unref();
  return child;
}
function letGo(child) { try { child.kill(); } catch { /* already finished */ } }

/* WHO HAS THE FOREGROUND NOW. Used only in failure details, where "the session saw no
   browser in front" is worth nothing and "the session saw Code in front" is the whole
   answer. */
function frontProcess() {
  return ps("Add-Type -TypeDefinition '" + FG_CS + "'; $p = [Fg]::FrontPid(); " +
            '$n = (Get-Process -Id $p -ErrorAction SilentlyContinue).ProcessName; ' +
            '"$n ($p)"');
}

function bringChromeForward() {
  return ps(
    /* single-quoted for PowerShell: the C# above has double quotes in it and no single
       ones, so it goes through verbatim with no escaping to get wrong */
    "Add-Type -TypeDefinition '" + FG_CS + "'; " +
    '$t = @(' + MINE + ' | ForEach-Object { Get-Process -Id $_.ProcessId ' +
    '-ErrorAction SilentlyContinue } | Where-Object { $_.MainWindowHandle -ne 0 }); ' +
    'if (-not $t.Count) { "no window"; exit }; ' +
    '$want = $t[0].Id; ' +
    'for ($i = 0; $i -lt 10; $i++) { [void][Fg]::Raise($t[0].MainWindowHandle); ' +
    'Start-Sleep -Milliseconds 220; ' +
    'if ([Fg]::FrontPid() -eq $want) { "front is chrome $want"; exit } }; ' +
    '"FAILED to raise chrome $want; front is $([Fg]::FrontPid())"');
}

/* ------------------------------------------------------------- the session's voice */

function harvest(state) {
  const fresh = (state.say || []).filter((l) => l && l.seq > seqSeen);
  if (fresh.length) seqSeen = fresh[fresh.length - 1].seq;
  for (const l of fresh) { episode.push(l); pending.push(l); }
  return fresh;
}
function drain() { const out = pending; pending = []; return out; }
const texts = (lines) => lines.map((l) => l.text);

/* Poll /focus until the predicate holds, harvesting every line on the way past so the
   transcript is complete and no callout is lost to the twelve-line queue. */
async function until(pred, budgetMs, everyMs = 110) {
  const start = Date.now();
  for (;;) {
    const state = (await galaxy('/focus')).focus;
    harvest(state);
    if (pred(state)) return { hit: true, ms: Date.now() - start, state };
    if (Date.now() - start > budgetMs) return { hit: false, ms: Date.now() - start, state };
    await sleep(everyMs);
  }
}
async function state() {
  const s = (await galaxy('/focus')).focus;
  harvest(s);
  return s;
}
/* LOCK THIS TAB, exactly as viewer/index.html sends it from the pill - source 'card' is
   the flag that says "the press itself brought this window to the front, so ask the
   browser which tab is in front, not the window manager". Counted, because "the lock
   completes itself" is a claim about how many times this was called. */
async function pressPill() {
  presses++;
  /* PRESS_MS, not the ordinary budget, and this is measured rather than padded: a press
     with no debugging port anywhere probes three dead ports before it answers, and that
     took 9.75 s on this machine - under a 10 s client budget by a quarter of a second.
     Timing out here would abort the run with "the operation was aborted" while the server
     was still working correctly: a harness failure reported as a feature failure. */
  const reply = await galaxy('/focus', { cmd: 'retarget', source: 'card' }, PRESS_MS);
  harvest(reply.focus);
  return reply;
}
async function diag() { return (await galaxy('/focus/diag')).diag || {}; }

/* -------------------------------------------------------------------- the sections */

async function premise() {
  console.log('\n  1. THE PREMISE\n');
  const health = await galaxy('/health');
  ok(health && health.ok === true, 'the server on 4700 answers /health');
  for (const p of PORTS) {
    const alive = await portAlive(p);
    ok(!alive, 'nothing is answering on the debugging port ' + p,
       'Section 2 is about a browser with NO port. Close the browser on that port - or ' +
       'whatever harness left it - and run this one solo.');
    if (alive) throw new Error('port ' + p + ' is open; this harness must run solo');
  }
  /* THE SERVER IS RUNNING THIS CODE, not the copy on disk. The whole of PART F lives in
     a long-lived process, and a harness that proves the file and not the process is the
     one that lets you spend an afternoon on a feature that was never restarted. */
  const s = await state();
  ok(Object.prototype.hasOwnProperty.call(s, 'lockedTab') &&
     Object.prototype.hasOwnProperty.call(s, 'tabLockWhy'),
     'the running process publishes lockedTab and tabLockWhy',
     'restart server.py: this is the pre-PART-F process');
  const d = await diag();
  /* WHICH PROCESS ANSWERED. Windows will let a second server bind 4700 and lose, leaving
     the old one answering, and then a whole run proves yesterday's code. The pid and the
     uptime go in the transcript so that can never be a guess. */
  note('the server answering 4700 is pid ' + d.pid + ', up ' + d.uptimeS + 's');
  ok(d && typeof d.watchers === 'number' && typeof d.watchPolls === 'number' &&
     typeof d.watchState === 'string',
     'and the instrument reports watchers, watchPolls and watchState',
     JSON.stringify({ watchers: d && d.watchers, polls: d && d.watchPolls,
                      state: d && d.watchState }));
  ok(d.watchers === 0 && d.watchState === 'n/a',
     'with nothing watching before we start: watchers ' + d.watchers +
     ', watchState ' + d.watchState);
  /* A session left running by an earlier run would answer every assertion below about
     a lock nobody in this file took. */
  if (s.state !== 'idle' && s.state !== 'ended') {
    note('a session was already running (' + s.state + '); aborting it first');
    await galaxy('/focus', { cmd: 'abort' });
    await state();
  }
  const none = await galaxy('/focus', { cmd: 'summon' });
  ok(none.summoned === false && /no locked tab/i.test(none.answer || ''),
     'and a summon with no lock refuses in a sentence rather than doing something: "' +
     (none.answer || '') + '"');
}

function backupProfileSession() {
  console.log('\n  1a. THE PROFILE, BORROWED AND PUT BACK\n');
  if (!PROFILE || !existsSync(PROFILE)) {
    note('the launcher profile does not exist yet - nothing to back up');
    return;
  }
  /* Closed first, so what is copied is the session Chrome has actually written rather
     than a half-flushed one, and so our own portless launch below creates a window
     instead of being handed to a browser that already owns the profile. */
  closeProfileChromePolitely('so the session on disk is the real one');
  mkdirSync(BACKUP, { recursive: true });
  let n = 0;
  for (const dir of SESSION_DIRS) {
    const from = join(PROFILE, dir);
    if (!existsSync(from)) continue;
    for (const f of readdirSync(from)) {
      if (!isSessionFile(f)) continue;
      mkdirSync(join(BACKUP, dir), { recursive: true });
      try { copyFileSync(join(from, f), join(BACKUP, dir, f)); n++; } catch { /* locked */ }
    }
  }
  backedUp = true;
  log('copied ' + n + ' session file(s) aside; they go back in teardown');
}

let chromeExe = null;
function launchPortless() {
  chromeExe = CHROMES.find((p) => existsSync(p));
  if (!chromeExe) throw new Error('no chrome.exe found');
  /* DELIBERATELY WITHOUT --remote-debugging-port. This is the browser the boss actually
     has on the morning the feature has to say something useful: the one he opened from
     the taskbar. On the launcher's profile, because the hand under test closes that
     profile and restores its tabs - which is the chain being proved, not a detail. */
  spawn(chromeExe, ['--user-data-dir=' + PROFILE, '--no-first-run',
                    '--no-default-browser-check', '--window-size=1100,780',
                    '--new-window', WORK_A], { detached: true, stdio: 'ignore' });
}

async function portlessPress() {
  console.log('\n  2. THE PORTLESS PRESS\n');
  launchPortless();
  for (let i = 0; i < 40; i++) {
    if (chromeOnProfile()) break;
    await sleep(250);
  }
  await sleep(3500);                       // let the page paint and the title settle
  ok(chromeOnProfile() > 0, 'a browser with no debugging port is up on the profile');
  const raised = bringChromeForward();
  ok(/^front is chrome/.test(raised), 'and it is the window in front: ' + raised,
     'FAILURE MODE: nothing of ours in front. Every check below would then be about a ' +
     'session correctly declining to lock a tab in a desktop it cannot see - a pass ' +
     'for the wrong feature.');
  await sleep(600);
  for (const p of PORTS) {
    ok(!(await portAlive(p)), 'and port ' + p + ' is still dead, as the case requires');
  }
  const cap = (await galaxy('/health')).focus || {};
  ok(cap.browser === true && cap.cdp === false,
     'the session sees a BROWSER in front and no CDP: browser=' + cap.browser +
     ', cdp=' + cap.cdp,
     'if browser is false the desktop is not ours - this harness needs the foreground');

  const got = await keepAskingForThePort('2');
  ok(!!got, 'the press happened with the browser in front for the whole of it' +
     (got ? ': ' + got.raised : ''),
     'FAILURE MODE: not the feature but the desktop. Each attempt above names what held ' +
     'the foreground instead; a session that cannot see a browser is right to offer ' +
     'nothing, and a harness that accepted that would be passing the wrong feature.');
  if (!got) return;
  const said = got.said;
  const press = got.press;
  ok(said.includes(SAY.noport),
     'it SAYS the port is missing: "' + SAY.noport + '"',
     JSON.stringify(said));
  ok(said.includes(SAY.askRelaunch),
     'and asks for the one thing that would fix it: "' + SAY.askRelaunch + '"',
     JSON.stringify(said));
  ok(press.answer === SAY.askRelaunch,
     'with the question as the reply\'s spoken line, so one tab says it once',
     JSON.stringify(press.answer));
  ok(press.focus.tabLockWhy === 'noport',
     'and the CARD is told why in one word: tabLockWhy=' + press.focus.tabLockWhy,
     'FAILURE MODE: a pill that flashed LOCKED and a card that then said nothing at ' +
     'all - tab-lock silently off, which is what this Part exists to remove');

  /* THE GATE IS THE ORDINARY GATE. Not a special dialog: the same one pending slot the
     boss already answers yes to, with the same TTL and the same two words. */
  const slot = await galaxy('/tools', { cmd: 'lapse' });
  ok(slot.pending && slot.pending.tool === 'relaunch_chrome',
     'the question is in the ordinary pending slot, as tool ' +
     (slot.pending && slot.pending.tool), JSON.stringify(slot.pending || null));
  ok(slot.pending && (slot.pending.fields || []).length === 0,
     'and it carries NO parameters - there is nothing in it to point somewhere else',
     JSON.stringify(slot.pending && slot.pending.fields));
  if (!slot.pending) return;

  /* NO. The half that is easy to leave unbuilt, and the half the mandate names: "No
     consent -> the card says plainly that tab-lock is off and why." */
  const no = await galaxy('/tools', { cmd: 'cancel', id: slot.pending.id, door: 'button' });
  ok(no.ok !== false, 'the No is accepted at the button door');
  const after = await until((s) => s.tabLockWhy === 'declined', 4000);
  ok(after.hit, 'and the card stops asking: tabLockWhy=' + after.state.tabLockWhy,
     'FAILURE MODE: a feature that looks armed and is not. A no that changed nothing ' +
     'visible would leave the card claiming a lock the session cannot take.');
  ok(texts(drain()).includes(SAY.declined),
     'said out loud too, once: "' + SAY.declined.slice(0, 48) + '..."');
  await galaxy('/focus', { cmd: 'abort' });
  await state();
  drain();
}

/* ONE FRESH SESSION, ONE VERIFIED RAISE, ONE PRESS - and a fresh session every time,
   because the offer is deliberately once per session: pressing twice inside one session
   is refused by design and a harness that did it would be measuring that refusal. */
async function askForThePort() {
  await clearTheGate('the press');
  await galaxy('/focus', { cmd: 'start', minutes: 9 });
  await state();
  /* HELD, not merely raised, and for the whole press. A portless press takes the server
     the best part of ten seconds - three dead debugging ports, each probed - and the
     foreground is read twice inside it: once to decide what is in front, and again to
     decide whether an offer would help. Anything that takes the foreground in between
     makes the second read disagree with the first, which is the ordinary, correct "there
     is no browser here to lock": the feature behaving well and the harness proving
     nothing about the case it was written for. */
  const held = holdChromeForward(HOLD_MS);
  const raised = bringChromeForward();
  drain();
  presses = 0;
  const press = await pressPill();
  const front = frontProcess();            // read before letting go, so it means something
  letGo(held);
  return { raised, press, front, said: texts(drain()) };
}

/* AN EMPTY GATE, which is a precondition and not a courtesy.
 *
 * _ask_for_the_port() asks the hands gate to hold its question, and a gate that is ALREADY
 * holding a proposal cannot: the session then does the honest thing and says the plain
 * sentence instead of a question nobody could answer - "Tab-level locking is off, then,
 * sir" with no "Shall I?" before it. An abandoned run leaves exactly that behind, and the
 * next run reads it as a broken feature. So the gate is emptied first, out loud, and what
 * was in it is named.
 */
async function clearTheGate(why) {
  const slot = await galaxy('/tools', { cmd: 'lapse' });
  if (!slot.pending) return null;
  await galaxy('/tools', { cmd: 'cancel', id: slot.pending.id, door: 'button' });
  log('cleared a proposal left in the gate before ' + why + ': ' + slot.pending.tool);
  drain();
  return slot.pending.tool;
}

/* THREE FRESH SESSIONS AT MOST, and fresh is the load-bearing word: the offer is
   deliberately once per session, so a retry inside one session would measure that
   refusal instead. Each failed attempt names what was in front, because the difference
   between "the feature is broken" and "the editor took the foreground" is the whole
   difference between a bug and a Tuesday. */
async function keepAskingForThePort(where) {
  for (let attempt = 1; attempt <= 3; attempt++) {
    let tried;
    try {
      tried = await askForThePort();
    } catch (e) {
      /* A press that never came back is an attempt that failed, not a run that ends: the
         next attempt gets a fresh session and the reason is in the transcript. */
      log('attempt ' + attempt + ' threw: ' + e.message + '; front is ' + frontProcess());
      await galaxy('/focus', { cmd: 'abort' }).catch(() => {});
      await state();
      drain();
      continue;
    }
    if (tried.press.answer === SAY.askRelaunch) {
      if (attempt > 1) note('section ' + where + ' needed ' + attempt + ' attempts; the ' +
                            'foreground was taken from Chrome during the earlier ones');
      return tried;
    }
    /* The two ways this fails look nothing alike in the transcript, and saying which one
       happened is the difference between a five-minute fix and an afternoon: either the
       session never saw a browser (the foreground went), or it saw one, said the port was
       missing, and could not ask (the gate was holding something). */
    log('attempt ' + attempt + ': raise said "' + tried.raised + '", the press answered ' +
        JSON.stringify(tried.press.answer) + ', front at the end of the press was ' +
        tried.front + ' - ' + (tried.said.includes(SAY.noport)
          ? 'it DID say the port was missing and then could not ask, which is a gate that '
            + 'was already holding a proposal'
          : 'it never reached the port at all, which is a foreground it could not see a '
            + 'browser in'));
    await galaxy('/focus', { cmd: 'abort' });
    await state();
    drain();
  }
  return null;
}

async function consent() {
  console.log('\n  3. THE CONSENT, AND THE LOCK THAT COMPLETES ITSELF\n');
  const got = await keepAskingForThePort('3');
  ok(!!got, 'the press asks for the port again in a new session' +
     (got ? ': "' + got.raised + '"' : ''),
     'FAILURE MODE: the offer is once per session, so this is also the check that a ' +
     'second session gets its own chance to ask - and, if it is the foreground that ' +
     'failed rather than the feature, the attempts above name what was in front instead.');
  const slot = await galaxy('/tools', { cmd: 'lapse' });
  ok(slot.pending && slot.pending.tool === 'relaunch_chrome',
     'and the slot holds relaunch_chrome again',
     JSON.stringify(slot.pending || null));
  drain();
  if (!slot.pending) {
    throw new Error('nothing to consent to; the chain stops here');
  }

  log('YES - running tools/relaunch_chrome.py for real; this closes the profile ' +
      'browser politely and brings it back with the port');
  const ran = await hand('/execute', { id: slot.pending.id, door: 'button' }, HAND_MS);
  ok(ran.ok === true && ran.ran === 'relaunch_chrome',
     'the hand ran: ' + JSON.stringify(ran.ran), JSON.stringify(ran).slice(0, 300));
  ok(/\b9222\b/.test(ran.answer || ''),
     'and its own sentence names the port it opened: "' +
     String(ran.answer || '').slice(0, 96) + '"');
  ok(await portAlive(PORT), 'the debugging port ' + PORT + ' answers now');
  const cap = (await galaxy('/health')).focus || {};
  ok(cap.cdp === true,
     'and the session agrees it can read tabs now: cdp=' + cap.cdp,
     'FAILURE MODE: capability() holds its answer for three seconds, so a yes that ' +
     'opened the port could be met with a cached "there is no port" - see ' +
     '_forget_capability()');

  /* WHAT THE RELAUNCH PUTS IN FRONT OF HIM, which is the thing the design of this
     section turned on. launch-chrome.ps1 ends with --new-window on the viewer, so the
     browser comes back showing the CARD - home base, the one surface a session may not
     lock, because it is where the button lives. So the honest outcome here is not a lock:
     it is the re-arm, out loud, and then the lock landing on the first real tab he goes
     to. "The lock completes itself" means NO SECOND PRESS, not telepathy about a tab
     that no longer exists - the tab ids the old browser had died with it. */
  await state();                 // harvest what the hand's own retarget said
  const afterHand = texts(drain());
  log('after the relaunch it said: ' + JSON.stringify(afterHand));
  ok(afterHand.includes(SAY.armed) || afterHand.includes(SAY.settled),
     'it picks the session back up out loud rather than going quiet',
     JSON.stringify(afterHand));
  ok(!afterHand.includes(SAY.noport) && !afterHand.includes(SAY.declined),
     'and never says the port is missing after opening it',
     'FAILURE MODE: capability() caches its answer for three seconds, so a yes that ' +
     'opened the port could be answered with a stale "there is no port" and the boss ' +
     'would be asked to relaunch the browser he just relaunched - see ' +
     '_forget_capability()');

  /* AND NOW HE GOES TO HIS WORK, which is all that is left of the gesture. One press
     was spent, before the relaunch; presses is asserted below so that is a fact in the
     transcript rather than a claim in a comment. */
  const restored = (await findWork()).work;
  ok(restored.length === 1, 'the relaunch restored his work tab: ' +
     restored.map((t) => t.url).join(' '),
     'FAILURE MODE: a hand that "relaunches Chrome" by killing it. --restore-last-session ' +
     'only works on a browser that was closed, not shot.');
  const A = restored[0];
  await cdp('/json/activate/' + A.id);
  const lock = await until((s) => !!s.lockedTab, 14000);
  const s = lock.state;
  ok(lock.hit, 'THE LOCK COMPLETED ITSELF on the tab he went to, with no second press: ' +
     'lockedTab="' + s.lockedTab + '"',
     JSON.stringify({ lockedTab: s.lockedTab, why: s.tabLockWhy, state: s.state }));
  ok(presses === 1, 'one press of the pill in this whole session: presses=' + presses,
     'FAILURE MODE: a harness that presses again and calls the result self-completing');
  ok(s.tabLockWhy === '', 'with nothing left to explain: tabLockWhy="' + s.tabLockWhy + '"');
  ok(s.lockedTab.length > 0 && s.lockedTab.length <= 24,
     'and the title on the card is at most 24 characters: ' + s.lockedTab.length);
  /* IT IS THE SAME TAB. The card shows a title and the watcher holds a target id, and
     this is the only place the two can be compared: a lock that named one tab and watched
     another would read perfectly on the card and call out at the wrong moment. */
  ok(A.title.startsWith(s.lockedTab.replace(/…$/, '').trim()) ||
     s.lockedTab.startsWith(A.title.slice(0, 18)),
     'and the title on the card is THIS tab\'s: card "' + s.lockedTab + '" vs tab "' +
     A.title.slice(0, 40) + '"');
  ok(texts(drain()).includes(SAY.settled), 'said plainly: "' + SAY.settled + '"');
  const d = await diag();
  ok(d.watchers === 1 && d.watchState === 'on',
     'the instrument shows one live watcher: watchers=' + d.watchers +
     ', watchState=' + d.watchState);
  /* It polls every 300 ms and it has only just been made, so this waits rather than
     reading the counter in the same breath as the lock. The claim is not "it has already
     polled", which is a race: it is "it polls", which is the feature. */
  let polls = d.watchPolls;
  for (let i = 0; i < 12 && polls < 1; i++) { await sleep(250); polls = (await diag()).watchPolls; }
  ok(polls > 0, 'and it is actually polling: watchPolls=' + polls,
     'FAILURE MODE: a watcher object that exists and never asks the browser anything ' +
     'would report LOCKED and notice nothing');
  return A;
}

/* The two tabs, by identity. A is the locked one. */
async function findWork() {
  const list = await pages();
  const work = list.filter((t) => t.url.includes(HOST));
  return { all: list, work };
}

async function teeth(A) {
  console.log('\n  4. THE TEETH\n');
  /* ONE WINDOW, TWO TABS, and that is the case the teeth exist for. A second tab of the
     SAME HOST is invisible to the window reader - it reads a host and the host is
     right - so the ONLY organ that can notice is the watcher. Measured in _spike25:
     activating A raises A's window, and PUT /json/new then opens into THAT window, so
     A drops to bits 0 and the drift is real rather than arranged. */
  await cdp('/json/activate/' + A.id);
  await sleep(900);
  ok(await bits(A) === 3, 'the locked tab is active and focused before we leave it');
  const before = await state();
  ok(before.drifts === 0 && before.drifting === false,
     'and the session is clean: drifts=' + before.drifts);
  drain();

  const t = Date.now();
  const made = await cdp('/json/new?' + encodeURIComponent(WORK_B), 'PUT');
  const B = made && made.id ? made : null;
  ok(!!B, 'a second tab of the same host opens beside it');
  const drift = await until((s) => s.drifting === true, DRIFT_BUDGET_MS + 1200);
  const took = Date.now() - t;
  ok(drift.hit && took <= DRIFT_BUDGET_MS,
     'LEAVING THE LOCKED TAB IS NOTICED in ' + took + ' ms (budget ' +
     DRIFT_BUDGET_MS + ' ms)',
     'FAILURE MODE: the whole feature. Same host, same window, same application - ' +
     'nothing but the watcher can see this, so a watcher that is not polling passes ' +
     'every other check in this file and this one only.');
  ok(drift.state.drifts === 1, 'and it counts as exactly one drift: ' + drift.state.drifts);
  const bitsA = await bits(A);
  ok(bitsA === 0, 'the locked tab really is behind: bits=' + bitsA +
     ' (bit 1 clear is the whole signal)');

  const calls = texts(drain());
  const tier1 = LOCKED_TIER1(1);
  const spoken = calls.filter((x) => tier1.includes(x));
  ok(spoken.length === 1,
     'ONE callout for the episode, from the locked-tab pool: "' + (spoken[0] || '') + '"',
     JSON.stringify(calls));
  ok(!calls.some((x) => x.includes(HOST)),
     'and it names no site: the locked pool is nameless, whatever the naming switch says',
     JSON.stringify(calls));

  /* COMING BACK, said once. A watchdog that only ever tells you off is a watchdog you
     turn off. */
  await cdp('/json/activate/' + A.id);
  const back = await until((s) => s.drifting === false, 3000);
  ok(back.hit, 'returning to it resumes on target in ' + back.ms + ' ms');
  const backLines = texts(drain());
  ok(backLines.filter((x) => x === SAY.back).length === 1,
     'and says so ONCE: "' + SAY.back + '"', JSON.stringify(backLines));
  ok(back.state.drifts === 1,
     'the drift is not refunded by coming back: drifts=' + back.state.drifts);

  /* THE SECOND DRIFT, inside thirty seconds. The narrating stops and something is
     offered instead - through the same gate as every other hand. */
  await cdp('/json/activate/' + B.id);
  const again = await until((s) => s.drifting === true, DRIFT_BUDGET_MS + 1200);
  ok(again.hit, 'a second drift is noticed in ' + again.ms + ' ms');
  await sleep(400);          // the callout and the offer land on the same beat
  await state();
  const lines = texts(drain());
  ok(lines.some((x) => LOCKED_TIER1(2).includes(x)),
     'called out again from the locked pool: "' +
     (lines.find((x) => LOCKED_TIER1(2).includes(x)) || '') + '"', JSON.stringify(lines));
  ok(lines.includes(SAY.askSummon),
     'and THEN it offers to fix it: "' + SAY.askSummon + '"',
     'FAILURE MODE: a third, fourth and fifth sentence about the same drift. Two ' +
     'callouts inside thirty seconds is a pull, not absent-mindedness.');
  const slot = await galaxy('/tools', { cmd: 'lapse' });
  ok(slot.pending && slot.pending.tool === 'summon_tab',
     'in the ordinary slot, as tool ' + (slot.pending && slot.pending.tool));
  ok(slot.pending && (slot.pending.fields || []).length === 0,
     'and again with no parameters: the locked tab lives in the session, not on the wire');

  if (!slot.pending) {
    ok(false, 'there is no proposal to say yes to, so the summon cannot be proved');
    return { A, B };
  }
  log('YES - running tools/summon_tab.py');
  const ran = await hand('/execute', { id: slot.pending.id, door: 'button' }, 30000);
  ok(ran.ok === true && ran.ran === 'summon_tab', 'the summon hand ran',
     JSON.stringify(ran).slice(0, 240));
  ok(String(ran.answer || '').trim() === SAY.summoned,
     'and its stdout is the session\'s own sentence: "' + String(ran.answer).trim() + '"');
  const bitsBack = await bits(A);
  ok((bitsBack & 1) === 1 && (bitsBack & 2) === 2,
     'THE LOCKED TAB AND ITS WINDOW ARE IN FRONT AGAIN: bits=' + bitsBack,
     'FAILURE MODE: a summon that reports success off the HTTP status. activate() ' +
     'reads the answer back off the tab for exactly this reason.');
  const home = await until((s) => s.drifting === false, 3000);
  ok(home.hit, 'the session agrees he is back');
  ok(home.state.drifts === 2,
     'and the record keeps BOTH drifts: drifts=' + home.state.drifts +
     ' - a rescue that also cleaned the books would make the sparkline a record of ' +
     'how often he accepted help');
  const d = await diag();
  ok(d.watchers === 1 && d.watchState === 'on',
     'the watcher is still the same one watcher: ' + d.watchers + ' / ' + d.watchState);
  return { A, B };
}

async function unlock(A, B) {
  console.log('\n  5. THE UNLOCK\n');
  const d0 = await diag();
  await galaxy('/focus', { cmd: 'abort' });
  const s = await state();
  ok(s.state === 'ended', 'the session ends');
  ok(s.lockedTab === '', 'and the card stops naming a tab at once: lockedTab=""',
     'FAILURE MODE: a title that outlives the watcher. It is read straight off the ' +
     'live watcher for this reason, never from a copy kept beside it.');
  const d1 = await diag();
  ok(d1.watchers === 0, 'NOTHING IS LEFT WATCHING: watchers=' + d1.watchers);
  ok(d1.watchState === 'gone' || d1.watchState === 'n/a',
     'watchState=' + d1.watchState);
  await sleep(1500);
  const d2 = await diag();
  ok(d2.watchPolls === d1.watchPolls,
     'and the polling has stopped dead: watchPolls ' + d0.watchPolls + ' -> ' +
     d1.watchPolls + ' -> ' + d2.watchPolls + ' over a second and a half',
     'FAILURE MODE: a thread still asking a browser about a tab after the session it ' +
     'belonged to is over.');

  /* NO CDP SESSION LEFT ATTACHED, asked of the browser itself rather than inferred.
     Every socket this file opened was closed in bits(), so anything attached here is
     the session's. */
  const version = await cdp('/json/version');
  const b = sock(version.webSocketDebuggerUrl);
  await b.ready;
  let targets = [];
  try {
    const r = await b.send('Target.getTargets', {});
    targets = ((r.result && r.result.targetInfos) || []).filter((t) => t.type === 'page');
  } finally { b.close(); }
  const stuck = targets.filter((t) => t.attached &&
                                      (t.targetId === A.id || t.targetId === B.id));
  ok(stuck.length === 0,
     'and no debugger is still attached to the two work tabs',
     JSON.stringify(targets.map((t) => ({ id: t.targetId.slice(0, 8), a: t.attached,
                                          url: t.url.slice(0, 40) }))));
  const none = await galaxy('/focus', { cmd: 'summon' });
  ok(none.summoned === false,
     'a summon after the end refuses rather than moving a window: "' + none.answer + '"');
}

/* ------------------------------------------------------------------------ teardown */

async function tidy() {
  console.log('\n  6. TEARDOWN\n');
  try {
    const { work } = await findWork();
    for (const t of work) { await cdp('/json/close/' + t.id); }
    if (work.length) log('closed ' + work.length + ' work tab(s)');
  } catch { /* the browser may already be gone */ }
  await sleep(600);
  const gone = closeProfileChromePolitely('the run is over');
  log(gone ? 'the profile browser is closed' : 'the profile browser would not close');
  await sleep(900);
  if (backedUp && existsSync(BACKUP)) {
    let n = 0, dropped = 0;
    for (const dir of SESSION_DIRS) {
      const from = join(BACKUP, dir);
      if (!existsSync(from)) continue;
      const kept = new Set(readdirSync(from).filter(isSessionFile));
      /* Chrome picks the NEWEST Session_<timestamp>, so copying his aside and leaving ours
         beside it restores nothing: the run's own session wins on every count. Whatever this
         run wrote goes, and only then does his come back. Safe because the browser on this
         profile is closed by the line above, and because PROFILE is the launcher's own
         devtools profile - never his everyday one. */
      const live = join(PROFILE, dir);
      if (existsSync(live)) {
        for (const f of readdirSync(live)) {
          if (!isSessionFile(f) || kept.has(f)) continue;
          try { rmSync(join(live, f), { force: true }); dropped++; } catch { /* locked */ }
        }
      }
      for (const f of kept) {
        try { copyFileSync(join(from, f), join(PROFILE, dir, f)); n++; } catch { /* locked */ }
      }
    }
    if (dropped) log('cleared ' + dropped + ' session file(s) this run wrote');
    log('put ' + n + ' session file(s) back; the boss\'s tabs return on his next launch');
    try { rmSync(BACKUP, { recursive: true, force: true }); } catch { /* fine */ }
  }
}

/* ---------------------------------------------------------------------------- main */

async function main() {
  await premise();
  backupProfileSession();
  await portlessPress();
  const locked = await consent();
  const { A, B } = await teeth(locked);
  await unlock(A, B);
}

main().catch((e) => {
  failures.push('the run itself: ' + e.message);
  console.log('\n  ' + at() + '  FAIL the run itself: ' + e.message);
  if (e.stack) console.log(e.stack.split('\n').slice(1, 4).join('\n'));
}).finally(async () => {
  try { await galaxy('/focus', { cmd: 'abort' }); } catch { /* server may be down */ }
  try { await tidy(); } catch (e) { console.log('  teardown: ' + e.message); }
  console.log('\n  THE EPISODE, as the session said it:\n');
  for (const l of episode) {
    console.log('    ' + String(l.seq).padStart(3) + '  ' + (l.kind + '     ').slice(0, 8) +
                l.text);
  }
  console.log('\n  ' + checks + ' checks, ' + failures.length + ' failed');
  if (notes.length) { console.log(''); for (const n of notes) console.log('    note: ' + n); }
  if (failures.length) {
    console.log('');
    for (const f of failures) console.log('    FAILED: ' + f);
  }
  console.log('');
  process.exit(Math.min(failures.length, 120));
});
