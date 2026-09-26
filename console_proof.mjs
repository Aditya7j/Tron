/* CONSOLE PROOF - the black window that flashed after every answer, and the desk that
 * has to stay empty now.
 *
 * THE COMPLAINT, in the boss's words: a black console blinks on the desktop after he is
 * spoken to. The cause was measured before a line was changed - say.py handed piper to
 * subprocess.run() with the default creation flags, Windows gave the child a console of
 * its own, and a console has a window:
 *
 *     HIT +2,300ms  pid 45448  class PseudoConsoleWindow
 *           chain: piper.exe(45448) <- python.exe(42376)
 *
 * The repair is tools/_proc.py and every call site migrated to it. This file is the part
 * that cannot be read out of the source: whether the desktop actually stays empty while
 * the server is made to work. It drives four real things through a real page and watches
 * user32 at 8 ms through console_watch.py the whole time.
 *
 * WHAT IS BEING PROVED, and every one of these names the failure it catches:
 *
 *   FOUR SILENT DESKTOPS - a short answer, a long one, a voice recast and a proposal.
 *     Failure mode: the flash itself, in the four shapes that can produce it. A short
 *     answer is one piper spawn; a long one is a spawn per chunk, which is where a race
 *     between the window and the hide would show; a recast is a spawn with a model the
 *     cache has never seen, through the audition door rather than the answer door; and a
 *     proposal is the OTHER spawner entirely - hands.py starting a python script - which
 *     shares nothing with the voice except the policy under test.
 *   AND EACH WATCH REALLY LOOKED. `polls` is asserted above a floor per case. Failure
 *     mode: a watcher that returned early, or read end-of-input as a stop, and handed back
 *     `silent: true` without having examined the desktop once. That exact bug was in the
 *     first version of console_watch.py and it passed everything.
 *   AND EACH WATCH HAD SOMETHING TO SEE. A spawn is asserted inside every window: a fresh
 *     `say:` line in the trace for the three voice cases (say.py writes that line on a
 *     cache MISS and never on a hit, so it is proof piper really ran), and the hand's own
 *     ledger for the proposal. Failure mode - and this is the one that would make the
 *     whole file worthless - a case that spawned nothing at all, because the line was
 *     already in say-cache/, reporting an empty desktop as a pass. Every voice case is
 *     therefore made cold on purpose: the answers carry a nonce sentence through the
 *     page's own funnel, and the audition's cache entry is deleted before the watch opens.
 *   AND THE POLICY IS NOT A HABIT. say.py and hands.py are read: the two live spawn sites
 *     call _proc.run, and neither file calls subprocess.run in code. Failure mode is the
 *     one that arrives in six months - a third spawner added by somebody who never read
 *     tools/_proc.py, flashing again, with nobody connecting the flash to the new feature.
 *     The repo-wide audit is preflight's check 21, which can use `ast` and therefore does.
 *
 * TWO DISCRETION DECISIONS, recorded here because the mandate names them differently:
 *
 *   THE FILTER IS BY WINDOW CLASS, NOT BY IMAGE NAME. The mandate asks for "any conhost.exe
 *     or cmd.exe window". Taken literally that misses the defect twice over: the visible
 *     window in the measurement above was owned by piper.exe, not by conhost.exe, and its
 *     class was PseudoConsoleWindow rather than the famous ConsoleWindowClass - the server
 *     is started from a shell holding a ConPTY, so its console children get a pseudo-
 *     console. Worse, conhost.exe is what CREATE_NO_WINDOW legitimately produces: the flag
 *     means "a console with no window", so Windows still allocates one and hosts it in a
 *     conhost that never shows itself. An image-name test would pass the bug and fail the
 *     fix. So: all three console window classes, VISIBLE only, filtered by parent chain to
 *     the server pid - and hidden conhosts reported for the record and judged by nothing.
 *   THE PROPOSAL IS RAISED THROUGH /tools, NOT BY TYPING. Every other case here is typed
 *     or clicked. This one posts propose+execute for `selftest` - the hermetic hand - the
 *     way preflight's check 16(d) does, because a harness that typed an instruction and
 *     then clicked Yes on whatever came back is a harness that can click Yes on send_email.
 *     The spawn's parentage, which is the entire subject, is identical either way.
 *
 * Headed and NOT muted, because the spawn under test only happens when a chunk is really
 * fetched and really played: a ?mute=1 tab would report four silent desktops and nothing
 * would have been started. It talks out loud for a minute. It writes nothing anywhere
 * except one deleted say-cache entry, which is a cache and regenerates itself.
 *
 * Usage:  python server.py 2> server-trace.log   then   node console_proof.mjs
 */
import { spawn, spawnSync } from 'node:child_process';
import { mkdtempSync, existsSync, readFileSync, statSync, openSync, readSync, closeSync,
         rmSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const GALAXY = 'http://127.0.0.1:4700';
/* The absolute path, as every harness on this machine uses: bare `python` here is the
   Microsoft Store stub, which exits without running anything. */
const PYTHON =
  'C:/Users/Fullstack Developer/AppData/Local/Programs/Python/Python313/python.exe';
const PORT = 9247;
const CDP = 'http://127.0.0.1:' + PORT;
const TRACE = process.env.TRACE || 'server-trace.log';
const CHROMES = [
  'C:/Program Files/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Google/Chrome/Application/chrome.exe',
  process.env.LOCALAPPDATA + '/Google/Chrome/Application/chrome.exe',
];
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let pass = 0, fail = 0; const failures = [];
const say = (m) => console.log(m);
const ok = (c, claim, detail) => {
  if (c) pass++; else { fail++; failures.push(claim); }
  say((c ? '  ok   ' : '  FAIL ') + claim);
  if (!c && detail) say('         ' + detail);
};
const note = (m) => say('  note ' + m);
const step = (m) => say('\n  ·· ' + m);

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
      const bomb = setTimeout(() => { this.w.delete(id); rej(new Error(method + ' timed out')); }, 120000);
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
  close() { try { this.ws.close(); } catch (e) { /* going anyway */ } }
}
const cdp = async (p) => { const r = await fetch(CDP + p); const t = await r.text();
  try { return JSON.parse(t); } catch (e) { return t; } };

async function waitFor(page, expr, ms = 10000) {
  for (let i = 0; i < ms / 200; i++) {
    try { if (await page.evaluate(expr)) return true; } catch (e) { /* not yet */ }
    await sleep(200);
  }
  return false;
}

/* A GENUINE GESTURE, copied from voice_proof and nudge_proof for the same reason it exists
   there: document.body.click() does not unlock audio, and without unlocked audio no chunk
   is ever fetched, so every desktop below would be empty because nothing happened. */
async function realClick(page, x, y) {
  for (const type of ['mousePressed', 'mouseReleased']) {
    await page.send('Input.dispatchMouseEvent',
      { type, x, y, button: 'left', clickCount: 1, buttons: type === 'mousePressed' ? 1 : 0 });
    await sleep(40);
  }
}

/* ---- the trace, read as bytes since a mark. say.py writes one line per SYNTHESIS, never
   per cache hit, which is the only cheap way to know from outside whether piper actually
   ran inside a watch window. ---- */
function traceMark() {
  try { return statSync(TRACE).size; } catch (e) { return -1; }
}
function traceSince(mark) {
  if (mark < 0) return null;
  try {
    const size = statSync(TRACE).size;
    if (size <= mark) return '';
    const fd = openSync(TRACE, 'r');
    const buf = Buffer.alloc(size - mark);
    readSync(fd, buf, 0, buf.length, mark);
    closeSync(fd);
    return buf.toString('utf8');
  } catch (e) { return null; }
}
const TRACE_LIVE = traceMark() >= 0;
const synths = (txt) => (txt ? [...txt.matchAll(/^say: \d+ chars -> \d+ bytes/gm)].length : 0);

/* ---- say-cache/, addressed the way say.py addresses it. Used once, to DELETE the
   audition's entry so the recast case is a cold spawn rather than a file read. The knobs
   are part of the key on purpose over there, so they are part of it here too. ---- */
function cacheFile(text, model) {
  const raw = [model, '1.0500', '0.4000', text].join('\u0000');
  return join('say-cache', createHash('sha256').update(raw, 'utf8')
    .digest('hex').slice(0, 32) + '.wav');
}

/* ================================ THE DESK WATCHER ================================
   One console_watch.py per case, held open on a pipe. The pipe matters: that watcher
   treats end-of-input as "keep watching" and only a written `stop` as a stop, because a
   version that quit on EOF returned `polls: 0, silent: true` - a green light for a desktop
   nobody had looked at. So this class keeps stdin open for the life of the case. */
class Desk {
  constructor(pid) { this.pid = pid; }
  async open(seconds) {
    this.out = ''; this.err = '';
    this.proc = spawn(PYTHON, ['console_watch.py', '--pid', String(this.pid),
                               '--seconds', String(seconds)],
                      { stdio: ['pipe', 'pipe', 'pipe'] });
    this.proc.stdout.on('data', (b) => { this.out += b.toString(); });
    this.proc.stderr.on('data', (b) => { this.err += b.toString(); });
    for (let i = 0; i < 150; i++) {
      if (this.out.indexOf('WATCHING') >= 0) return true;
      if (this.proc.exitCode !== null) return false;
      await sleep(100);
    }
    return false;
  }
  async verdict() {
    try { this.proc.stdin.write('stop\n'); } catch (e) { /* it may have timed out */ }
    for (let i = 0; i < 300; i++) {
      const line = this.out.split('\n').map((s) => s.trim())
        .find((s) => s.startsWith('{'));
      if (line) { try { this.proc.kill(); } catch (e) { /* gone */ } return JSON.parse(line); }
      await sleep(100);
    }
    try { this.proc.kill(); } catch (e) { /* gone */ }
    return { polls: 0, windows: [{ pid: 0, class: 'the watcher never answered' }],
             bystanders: [], hiddenConsoles: [], silent: false, err: this.err.slice(-400) };
  }
}

/* The one sentence every case's verdict is judged by, written once so the four cases
   cannot drift apart in what they mean by "silent". */
function judge(name, w, spawned, how, floor) {
  const chains = (w.windows || []).map((h) => h.class + ' at +' + h.atMs + 'ms  ' +
                                        (h.chain || []).join(' <- '));
  note(name + ': ' + w.polls + ' polls · ' + (w.windows || []).length + ' window(s) ours · ' +
       (w.bystanders || []).length + ' bystander(s) · ' +
       (w.hiddenConsoles || []).length + ' hidden console host(s)');
  if ((w.bystanders || []).length) {
    note('       bystanders, none of them ours: ' +
         w.bystanders.map((b) => b.class + '/' + (b.chain || [])[0]).join(', '));
  }
  ok(spawned, name + ' REALLY STARTED SOMETHING: ' + how + ' - without this the empty ' +
     'desktop below is the desktop of a machine that was asked to do nothing',
     JSON.stringify({ spawned, how }));
  ok(w.polls > floor, '       and THE DESK WAS WATCHED THROUGHOUT: ' + w.polls +
     ' polls of user32 while it happened, over a floor of ' + floor + ' - a watcher that ' +
     'returned early would report an empty desktop it had never examined',
     JSON.stringify({ polls: w.polls, err: w.err || '' }));
  ok(w.silent === true, '       and NOT ONE CONSOLE WINDOW APPEARED anywhere in the ' +
     'server\u2019s process tree - which is the black flash itself, and the only thing ' +
     'here that can fail on the boss\u2019s behalf' +
     ((w.hiddenConsoles || []).length
       ? ' (' + w.hiddenConsoles.length + ' hidden console host(s) were allocated, which ' +
         'is CREATE_NO_WINDOW working rather than failing)'
       : ''),
     chains.length ? chains.join(' | ') : JSON.stringify(w));
  return w.silent === true && spawned && w.polls > floor;
}

say('\n  CONSOLE PROOF - the black window after every answer, and the desk that stays empty');

const health = await (await fetch(GALAXY + '/health').catch(() => null))?.json()
  .catch(() => null) || null;
if (!health || !health.ok) {
  say('\n  the server on 4700 is not answering; start it first: python server.py');
  process.exit(1);
}
note('the server: model ' + health.model + ' · say ' + JSON.stringify(health.say));
ok(TRACE_LIVE, 'the server\u2019s trace is readable at ' + TRACE + ', which is where the ' +
   '"piper really ran" evidence lives - without it every case here could pass on a cache hit',
   'run the server as: python server.py 2> ' + TRACE);

/* THE PID UNDER TEST comes from the server's own mouth. Not from a process list: two
   python.exe processes have shared port 4700 on this machine before, and watching the wrong
   one is a clean desktop for the wrong reason. */
const diag = await (await fetch(GALAXY + '/focus/diag')).json();
const SERVER_PID = diag && diag.diag ? diag.diag.pid : 0;
ok(SERVER_PID > 0, 'the server named its own pid, ' + SERVER_PID + ' - so the parent-PID ' +
   'filter is anchored to the process actually answering on 4700 rather than to whichever ' +
   'python.exe a process list happens to list first', JSON.stringify(diag && diag.diag));
if (!SERVER_PID) { say('\n  no server pid to watch'); process.exit(1); }
note('uptime ' + (diag.diag.uptimeS) + 's, so this is a server that has been running, not ' +
     'one this harness just started');

const exe = CHROMES.find((p) => existsSync(p));
if (!exe) { say('\n  no Chrome on this machine'); process.exit(1); }
const profile = mkdtempSync(join(tmpdir(), 'console-'));
const chrome = spawn(exe, ['--remote-debugging-port=' + PORT, '--user-data-dir=' + profile,
  '--no-first-run', '--no-default-browser-check', '--window-size=1200,820',
  '--new-window', GALAXY], { detached: true, stdio: 'ignore' });

let target = null;
for (let i = 0; i < 100 && !target; i++) {
  try {
    const l = await cdp('/json/list');
    target = (Array.isArray(l) ? l : []).filter((t) => t.type === 'page')
      .find((t) => String(t.url).includes('127.0.0.1:4700'));
  } catch (e) { /* not up yet */ }
  if (!target) await sleep(300);
}
if (!target) { say('\n  Chrome never came up on the debugging port'); process.exit(1); }
const page = await new Page(target.webSocketDebuggerUrl).open();
await page.send('Runtime.enable');
await page.send('Page.enable');
try { await page.send('Page.bringToFront'); } catch (e) { note('bringToFront: ' + e.message); }
ok(await waitFor(page, '!!(window.__galaxy && __galaxy.speech && __galaxy.voice)', 30000),
   'the viewer is up and the speech doors are open');

/* ---- audio, unlocked by a real gesture on empty canvas ---------------------------- */
const spot = await page.json('(function(){' +
  'var pick=function(f){var x=Math.round(innerWidth*0.5), y=Math.round(innerHeight*f);' +
  ' var e=document.elementFromPoint(x,y);' +
  ' return {x:x, y:y, hit: e ? (e.id || e.tagName.toLowerCase()) : null,' +
  '  bad: !!(e && e.closest && (e.closest("#bar") || e.closest("#cmd") ||' +
  '          e.closest("#toprail") || e.closest("button")))};};' +
  'var s=pick(0.3); if(s.bad) s=pick(0.2); if(s.bad) s=pick(0.12);' +
  'return s;})()');
await realClick(page, spot.x, spot.y);
await sleep(400);
ok(await waitFor(page, '__galaxy.speech.unlocked === true', 8000),
   'the first click unlocked the audio, so chunks will really be fetched and played - ' +
   'without this all four desktops below are empty because nothing was ever started',
   JSON.stringify(spot));
const drain = () => waitFor(page, '!__galaxy.voice.draining && __galaxy.voice.queue === 0', 90000);
await drain();

/* Typed, with the keyboard, through the vanishing input - the way the boss asks. Copied
   from tools_live: "/" summons the line, the text is inserted, Enter sends. A door that
   handed a string to ask() would prove the server spawns quietly when nobody is typing. */
const type = async (text) => {
  for (const t of ['keyDown', 'char', 'keyUp']) {
    await page.send('Input.dispatchKeyEvent', { type: t, key: '/', code: 'Slash',
      text: '/', unmodifiedText: '/', windowsVirtualKeyCode: 191,
      nativeVirtualKeyCode: 191 });
  }
  await sleep(150);
  const up = await page.json('({up: __galaxy.typeLine.up, focused: __galaxy.typeLine.focused})');
  if (!up.up || !up.focused) throw new Error('the slash did not summon the type-line');
  await page.send('Input.insertText', { text });
  for (const t of ['keyDown', 'keyUp']) {
    await page.send('Input.dispatchKeyEvent', {
      type: t, key: 'Enter', code: 'Enter', windowsVirtualKeyCode: 13,
      nativeVirtualKeyCode: 13, text: t === 'keyDown' ? '\r' : undefined });
  }
};

/* THE COLD LINE. A sentence carrying this run's nonce, spoken through the page's own funnel
   at the end of an answer case. It is not the subject of the case - the answer is - it is
   the guarantee that the case cannot pass on a say-cache hit, which is the one way an empty
   desktop means nothing. Unique text, so piper must run. */
const NONCE = String(Date.now()).slice(-6);
let coldLines = 0;
const coldLine = async (which) => {
  coldLines++;
  const line = 'Console probe ' + which + ', reference ' + NONCE + ', sir.';
  await page.evaluate('__galaxy.speech.speakLine(' + JSON.stringify(line) + ')');
  await sleep(300);
  await drain();
  return line;
};

const verdicts = {};

/* ---- 1. A SHORT ANSWER ----------------------------------------------------------- */
step('a short answer, typed and spoken');
let desk = new Desk(SERVER_PID);
ok(await desk.open(240), 'the desk watcher is up and polling for case 1');
let mark = traceMark();
await type('in one short sentence, what is the web gate');
const spoke1 = await waitFor(page, '__galaxy.voice.draining === true', 120000);
await drain();
const cold1 = await coldLine('one');
let w = await desk.verdict();
let misses = synths(traceSince(mark));
note('the trace recorded ' + misses + ' synthesis(es) inside that watch');
verdicts.short = judge('A SHORT ANSWER', w, misses >= 1,
  'piper ran ' + misses + ' time(s) under the server while the desk was watched, by ' +
  'say.py\u2019s own trace line, which is written on a cache miss and never on a hit', 200);
ok(spoke1, '       and the answer was really read aloud rather than merely rendered - the ' +
   'speech queue drained, which is what puts a piper spawn on the server in the first place');

/* ---- 2. A LONG ANSWER, which is a spawn per chunk -------------------------------- */
step('a long answer - one spawn per chunk, which is where a race would show');
desk = new Desk(SERVER_PID);
ok(await desk.open(300), 'the desk watcher is up and polling for case 2');
mark = traceMark();
await type('explain the web gate, the antecedent memory and the vocative peel at length, ' +
           'in five or six full sentences');
const spoke2 = await waitFor(page, '__galaxy.voice.draining === true', 180000);
await drain();
const cold2 = await coldLine('two');
w = await desk.verdict();
misses = synths(traceSince(mark));
note('the trace recorded ' + misses + ' synthesis(es) inside that watch');
verdicts.long = judge('A LONG ANSWER', w, misses >= 2,
  'piper ran ' + misses + ' times under the server - more than one spawn inside a single ' +
  'watch, which is the case a hide-after-the-fact repair loses', 400);
ok(spoke2 && misses >= 2,
   '       and it really was the MULTI-CHUNK path: ' + misses + ' separate spawns for one ' +
   'answer, so the desktop stayed empty across a sequence of them rather than across one',
   JSON.stringify({ spoke2, misses }));

/* ---- 3. A VOICE RECAST, through the audition door -------------------------------- */
step('a voice recast - a spawn with a model this machine has not just used');
await page.evaluate('__galaxy.cmd.cast.open()');
await sleep(600);
const cast = await page.json('__galaxy.cmd.cast.state');
ok(!!(cast && cast.line && (cast.candidates || []).length >= 2),
   'the casting panel knows the installed voices and the audition line - ' +
   (cast ? JSON.stringify(cast.chosen) + ' is the one in config.json' : 'no panel state'),
   JSON.stringify(cast));
/* A voice OTHER than the configured one, chosen from what the panel actually offers, so
   this case is a recast rather than the same voice under another name. */
const other = (cast.candidates || []).find((c) => c.ready && c.model !== cast.chosen);
ok(!!other, 'there is a second installed voice to recast into: ' +
   (other ? other.label + ' (' + other.model + ')' : 'none'));
/* COLD BY DELETION. The audition line is fixed, so it may well be in say-cache/ from an
   earlier run - and a cache hit would make this case a file read with no child process in
   it at all. The entry is addressed exactly as say.py addresses it and removed. */
const cf = cacheFile(cast.line, other.model);
const had = existsSync(cf);
try { rmSync(cf); } catch (e) { /* it was not there, which is the same starting state */ }
note('say-cache entry for the recast line ' + (had ? 'existed and was deleted' : 'was ' +
     'not there') + ', so the audition below must run piper');
desk = new Desk(SERVER_PID);
ok(await desk.open(180), 'the desk watcher is up and polling for case 3');
mark = traceMark();
const heard = await page.json('__galaxy.cmd.cast.hear(' + JSON.stringify(other.model) + ')');
await sleep(1200);
await waitFor(page, '__galaxy.cmd.cast.playing === ""', 60000);
w = await desk.verdict();
misses = synths(traceSince(mark));
note('the audition said ' + JSON.stringify(heard) + ' · ' + misses + ' synthesis(es)');
verdicts.recast = judge('A VOICE RECAST', w, misses >= 1,
  'piper ran ' + misses + ' time(s) for ' + other.model + ', a model the cache had no ' +
  'entry for, so this was a cold spawn through the audition door rather than the answer door',
  150);
/* Re-read from the SERVER, which reads it off the disk, rather than from the panel's copy:
   the claim is about config.json, and the panel's own state object would agree with itself
   whatever happened to the file. */
const after3 = await (await fetch(GALAXY + '/voices')).json();
ok(heard !== false && after3.chosen === cast.chosen,
   '       and the recast was an AUDITION, not a decision: config.json still names ' +
   after3.chosen + ' after auditioning ' + other.model + ' - a harness that changed the ' +
   'configured voice would be writing config.json, which no harness in this house is ' +
   'allowed to do',
   JSON.stringify({ heard, was: cast.chosen, now: after3.chosen }));

/* ---- 4. A PROPOSAL, which is the other spawner entirely -------------------------- */
step('a proposal - hands.py starting a python script, which shares nothing with the voice');
await drain();
desk = new Desk(SERVER_PID);
ok(await desk.open(180), 'the desk watcher is up and polling for case 4');
mark = traceMark();
/* propose + execute, from the page's own origin, on the hermetic hand. See the header for
   why this one is not typed. */
/* evaluate, not json: page.json wraps the expression in JSON.stringify, and stringifying a
   promise gives `{}` - awaitPromise has nothing left to await. returnByValue carries the
   plain object back on its own. */
const proposed = await page.evaluate(
  '(async function(){var r=await fetch("/tools",{method:"POST",' +
  'headers:{"Content-Type":"application/json"},body:JSON.stringify(' +
  '{cmd:"propose",tool:"selftest",params:{token:"' + NONCE + '"},door:"curl"})});' +
  'return {status:r.status, body: await r.json()};})()');
ok(proposed.status === 200 && proposed.body && proposed.body.pending &&
   proposed.body.pending.tool === 'selftest',
   'a proposal is pending for the hermetic hand, and for that hand only - ' +
   JSON.stringify(proposed.body && proposed.body.pending
     ? proposed.body.pending.tool : proposed.status),
   JSON.stringify(proposed).slice(0, 400));
const ran = await page.evaluate(
  '(async function(){var r=await fetch("/execute",{method:"POST",' +
  'headers:{"Content-Type":"application/json"},body:JSON.stringify({door:"curl"})});' +
  'return {status:r.status, body: await r.json()};})()');
/* A dwell before the verdict. A hand is a python.exe that lives for under a second, and
   the window - if the policy ever lapsed - appears as the child starts, not as it exits;
   closing the watch on the same tick /execute answers would be reading the desk after the
   thing worth seeing had already gone. */
await sleep(1500);
await drain();
w = await desk.verdict();
const handRan = !!(ran.status === 200 && ran.body && ran.body.ok && ran.body.ran === 'selftest');
note('the hand answered ' + JSON.stringify(ran.body && ran.body.ran) + ' status ' + ran.status);
verdicts.proposal = judge('A PROPOSAL', w, handRan,
  'the accepted hand really ran: /execute answered ok with ran=' +
  JSON.stringify(ran.body && ran.body.ran) + ', and hands.py runs a hand by starting a ' +
  'python script - a second spawner, on the same policy', 100);

/* ---- 5. AND THE POLICY IS NOT A HABIT ------------------------------------------- */
step('the two live spawn sites, read out of the source');
/* CODE LINES ONLY, and the first version of this was wrong in the way that matters: it
   dropped `#` comments and kept docstrings, so hands.py's own module docstring - which
   explains the call it makes, in prose, by name - was read as a bare subprocess call and
   failed the file that had just been repaired. Triple-quoted blocks go too. This is a
   crude parser and it is allowed to be: the repo-wide audit is preflight's check 21, which
   walks the real `ast` and therefore cannot be fooled by prose at all. */
const codeLines = (f) => {
  const out = []; let inDoc = false;
  for (const raw of readFileSync(f, 'utf8').split('\n')) {
    let rest = raw, keep = '';
    for (;;) {
      const i = rest.search(/"""|'''/);
      if (i < 0) { if (!inDoc) keep += rest; break; }
      if (!inDoc) keep += rest.slice(0, i);
      inDoc = !inDoc;
      rest = rest.slice(i + 3);
    }
    const hash = keep.indexOf('#');
    if (hash >= 0) keep = keep.slice(0, hash);
    if (keep.trim()) out.push(keep);
  }
  return out;
};
for (const f of ['say.py', 'hands.py']) {
  const lines = codeLines(f);
  const bare = lines.filter((l) => /\bsubprocess\.(run|Popen|call|check_output|check_call)\s*\(/.test(l));
  const quiet = lines.filter((l) => /\b_proc\.(run|popen)\s*\(/.test(l));
  ok(quiet.length >= 1 && bare.length === 0,
     f + ' SPAWNS THROUGH THE ONE POLICY: ' + quiet.length + ' call(s) to _proc, and not ' +
     'one line of code that reaches subprocess directly - which is how a spawner added ' +
     'next month inherits the fix instead of flashing again',
     JSON.stringify({ bare: bare.map((l) => l.trim().slice(0, 70)), quiet: quiet.length }));
}
const procSrc = readFileSync(join('tools', '_proc.py'), 'utf8');
ok(/creationflags["']\]\s*=\s*CREATE_NO_WINDOW/.test(procSrc) &&
   /if kwargs\.get\("creationflags"\)/.test(procSrc) &&
   /0x08000000/.test(procSrc),
   'and the policy itself is what it claims: CREATE_NO_WINDOW injected on win32, and a ' +
   'caller that passed its own creationflags left alone - DETACHED_PROCESS and ' +
   'CREATE_NEW_CONSOLE are deliberate choices, and or-ing a flag into them is how a ' +
   'launcher stops launching');

/* ---- the matrix ---------------------------------------------------------------- */
step('the four desktops');
const four = ['short', 'long', 'recast', 'proposal'];
for (const k of four) note('  ' + k.padEnd(9) + (verdicts[k] ? 'silent' : 'NOT SILENT'));
ok(four.every((k) => verdicts[k] === true),
   'ALL FOUR ARE SILENT: a short answer, a long one, a voice recast and a proposal, each ' +
   'with a real child process started under the server and a desk watched at 8ms ' +
   'throughout - the flash the boss reported has nowhere left to come from',
   JSON.stringify(verdicts));
note('the cold lines spoken to keep the answer cases honest: ' + coldLines + ', nonce ' +
     NONCE + ' - "' + cold1 + '" and "' + cold2 + '"');

say('\n  VERIFY ' + pass + '/' + (pass + fail) + (fail ? ' FAIL' : ' PASS'));
if (fail) { say(''); for (const f of failures) say('    FAILED: ' + f); }
page.close();
spawnSync('taskkill', ['/PID', String(chrome.pid), '/T', '/F']);
process.exit(fail ? 1 : 0);
