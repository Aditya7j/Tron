/* boot_proof.mjs - THE BOOT CEREMONY, IN ITS THREE FORMS.
 *
 * On the first healthy /health of a session, once and never twice, the butler says "I am ready,
 * Addi. Fully functional - every feature live." over a generative jingle built out of
 * oscillators on the chime bus, ducked 80% beneath his own voice. Three things can be true of
 * the tab it happens in, and the ceremony is a different shape in each:
 *
 *   A MUTED TAB holds no ceremony at all, and says why. A tab that cannot make a sound has
 *     nothing to announce, and a silent tab that had "already done it" would rob the session
 *     of its opening the moment the employer unmuted.
 *   A REDUCED-MOTION TAB keeps the sentence and drops the flourish. prefers-reduced-motion is
 *     a request about the machine's manners, not a request to be told less: the line arrives on
 *     the caption and in the speakers, and the jingle - the decorative half - does not play.
 *   A PLAIN TAB gets the whole thing: nine scheduled oscillator notes across 2.5-3.5s, the
 *     'boot' kind in the tone ring, the line spoken, and the chime bus 80% down underneath it.
 *
 * AND THE ONE LAW ACROSS ALL THREE: once per session. /health is polled every ten seconds for
 * as long as the tab is open, so a ceremony guarded by a timestamp or a debounce would hold for
 * the first minute and then start announcing itself over the answers. This asks for several
 * more healthy readings by the same door the brain chip uses, and asserts that nothing fires
 * twice: same timestamp, same note count, one firing.
 *
 * WHY HEADLESS AND WHY A CLICK: the jingle and the voice both need the autoplay door, and this
 * page keeps its own audioUnlocked rather than trusting Chrome's flag - so each tab is given a
 * real Input.dispatchMouseEvent, which is the gesture the law is actually about. Muted output,
 * because what is asserted is the graph, the ring and the gain, and none of those need a
 * speaker. voice_proof owns the out-loud half of this and asserts the ceremony's once-per-
 * session guard against a real read; nothing here overlaps it.
 *
 * Usage:  python server.py 2> server-trace.log   then   node boot_proof.mjs
 * Port 9280 - nobody else's. It writes nothing, reads no credential and asks the model nothing.
 */
import { spawn, spawnSync } from 'node:child_process';
import { mkdtempSync, rmSync, existsSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, basename } from 'node:path';

const GALAXY = 'http://127.0.0.1:4700';
const PORT = 9280;
const CDP = 'http://127.0.0.1:' + PORT;
const LINE = /Fully functional/;
const CHROMES = [
  'C:/Program Files/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Google/Chrome/Application/chrome.exe',
  process.env.LOCALAPPDATA + '/Google/Chrome/Application/chrome.exe',
];
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

let pass = 0, fail = 0;
const reds = [];
function ok(cond, line, dump) {
  if (cond) { pass++; console.log('  ok   ' + line); return true; }
  fail++; reds.push(line);
  console.log('  FAIL ' + line);
  if (dump) console.log('         ' + dump);
  return false;
}
const note = (s) => console.log('  note ' + s);

class Page {
  constructor(u) { this.u = u; this.id = 0; this.w = new Map(); }
  open() {
    return new Promise((res, rej) => {
      this.ws = new WebSocket(this.u);
      this.ws.onopen = () => res(this);
      this.ws.onerror = (e) => rej(new Error('socket: ' + (e.message || 'failed')));
      this.ws.onmessage = (ev) => {
        const m = JSON.parse(ev.data);
        if (!m.id) {
          if (m.method === 'Runtime.exceptionThrown') {
            const d = m.params.exceptionDetails;
            note('the page threw while booting: ' + (d.text || '') + ' ' +
                 (d.exception ? (d.exception.description || d.exception.value) : ''));
          }
          return;
        }
        const f = this.w.get(m.id);
        if (f) { this.w.delete(m.id); f(m); }
      };
    });
  }
  send(method, params) {
    const id = ++this.id;
    return new Promise((res, rej) => {
      const bomb = setTimeout(() => { this.w.delete(id); rej(new Error(method + ' timed out')); },
                              25000);
      this.w.set(id, (m) => { clearTimeout(bomb); res(m); });
      this.ws.send(JSON.stringify({ id, method, params: params || {} }));
    });
  }
  async evaluate(expression) {
    const r = await this.send('Runtime.evaluate',
      { expression, returnByValue: true, awaitPromise: true });
    if (r.result && r.result.exceptionDetails) {
      const d = r.result.exceptionDetails;
      throw new Error('page threw: ' + ((d.exception && (d.exception.description ||
        d.exception.value)) || d.text) + '  <- ' + expression.slice(0, 90));
    }
    return r.result && r.result.result ? r.result.result.value : undefined;
  }
  async json(e) { return JSON.parse(await this.evaluate('JSON.stringify(' + e + ')') || 'null'); }
  async click() {
    for (const type of ['mousePressed', 'mouseReleased']) {
      await this.send('Input.dispatchMouseEvent',
        { type, x: 640, y: 860, button: 'left', clickCount: 1 });
    }
  }
  close() { try { this.ws.close(); } catch { } }
}

const cdp = async (p) => {
  const r = await fetch(CDP + p);
  const t = await r.text();
  try { return JSON.parse(t); } catch { return t; }
};

const profiles = [];
let procs = [];
/* THE WHOLE BROWSER, not the socket, and gone before the next one is launched: the three tabs
   share one debug port, and a second Chrome cannot bind 9280 while the first still holds it -
   /json/list then quietly hands back the PREVIOUS tab, which reads as a ceremony that fired
   identically under two different conditions. Windows gives no process groups worth killing, so
   the spawned handle is only half the job: it is the renderer and GPU children that keep the
   port. Scoped by the temp profile's own name on the CommandLine, never by window title, so
   nothing of the employer's is ever in range - his own Chrome does not carry this string. */
async function killBrowsers() {
  for (const p of procs.splice(0)) { try { p.kill(); } catch { } }
  for (const d of profiles) {
    spawnSync('powershell.exe', ['-NoProfile', '-Command',
      'Get-CimInstance Win32_Process -Filter "Name=\'chrome.exe\'" | ' +
      'Where-Object { $_.CommandLine -match \'' + basename(d) + '\' } | ' +
      'ForEach-Object { taskkill /PID $_.ProcessId /F | Out-Null }'],
      { encoding: 'utf8', timeout: 30000 });
  }
  /* AND WAITED FOR, by the only witness that matters: the port answering is the old browser
     still alive. A fixed sleep here is how two tabs end up being the same tab. */
  for (let i = 0; i < 40; i++) {
    try { await cdp('/json/version'); } catch { return; }
    await sleep(250);
  }
  note('the debug port is STILL answering after ten seconds - the next tab may be the last one');
}

/* ONE TAB, BOOTED UNDER WHATEVER CONDITIONS THE CALLER NAMES.
   The emulated media has to be set BEFORE the viewer loads, because bootReduced() is read at
   the moment the ceremony fires - a second or two after the page is up - so the tab is opened
   on about:blank, told what kind of machine it is, and only then sent to the viewer. */
async function boot(exe, { url, reduced, label }) {
  const profile = mkdtempSync(join(tmpdir(), 'bootproof-'));
  profiles.push(profile);
  procs.push(spawn(exe, ['--headless=new', '--remote-debugging-port=' + PORT,
    '--user-data-dir=' + profile, '--no-first-run', '--no-default-browser-check',
    '--autoplay-policy=no-user-gesture-required', '--mute-audio',
    '--window-size=1280,900', 'about:blank'], { detached: true, stdio: 'ignore' }));
  for (let i = 0; i < 80; i++) { try { await cdp('/json/version'); break; } catch { await sleep(250); } }
  let target = null;
  for (let i = 0; i < 40; i++) {
    const l = await cdp('/json/list');
    target = (Array.isArray(l) ? l : []).find((t) => t.type === 'page');
    if (target) break;
    await sleep(300);
  }
  if (!target) throw new Error('no tab to boot in');
  const page = new Page(target.webSocketDebuggerUrl);
  await page.open();
  await page.send('Runtime.enable');
  await page.send('Page.enable');
  if (reduced) {
    await page.send('Emulation.setEmulatedMedia',
      { features: [{ name: 'prefers-reduced-motion', value: 'reduce' }] });
  }
  await page.send('Page.navigate', { url });
  console.log('\n  === ' + label + ' ===');
  let up = false;
  for (let i = 0; i < 80; i++) {
    try { if (await page.evaluate('!!(window.__galaxy && window.__galaxy.boot)')) { up = true; break; } }
    catch (e) { /* navigating */ }
    await sleep(500);
  }
  ok(up, 'the viewer is up in this tab and exposes __galaxy.boot');
  if (reduced) {
    ok(await page.evaluate('matchMedia("(prefers-reduced-motion: reduce)").matches') === true,
       'and it is a machine that has asked for less motion, which is the condition under test');
  }
  /* WAITED FOR, not slept at: the ceremony rides the first healthy /health, and how long that
     takes is the server's business. The ceiling is what makes the wait an assertion. */
  for (let i = 0; i < 60; i++) {
    if (await page.evaluate('__galaxy.boot.fired === 1')) break;
    await sleep(500);
  }
  return page;
}

async function main() {
  const exe = CHROMES.find((p) => existsSync(p));
  if (!exe) throw new Error('no chrome');
  const health = await (await fetch(GALAXY + '/health')).json();
  note('server: ' + (health.ok ? 'healthy' : 'NOT healthy') + ' · brain ' +
       ((health.brain && health.brain.label) || '?'));

  /* ---- A. A MUTED TAB HOLDS NO CEREMONY, AND SAYS WHY ------------------- */
  let page = await boot(exe, { url: GALAXY + '/?mute=1', label: 'a MUTED tab' });
  const m = await page.json('({boot: __galaxy.boot, caption: __galaxy.caption.text,' +
    ' kinds: __galaxy.audio.played.map(function (t) { return t.kind; }),' +
    ' said: __galaxy.speech.said.length})');
  note('   boot: ' + JSON.stringify(m.boot));
  ok(m.boot.fired === 1 && m.boot.said === false && m.boot.spoke === false,
     'A MUTED TAB HOLDS NO CEREMONY: it fired once and then declined, rather than leaving the ' +
     'ceremony armed to go off the moment the employer unmutes mid-answer',
     JSON.stringify(m.boot));
  ok(/muted/.test(m.boot.why),
     'AND IT SAYS WHY, in words: "' + m.boot.why + '"', JSON.stringify(m.boot));
  ok(m.boot.jingle.played === false && m.kinds.indexOf('boot') < 0,
     'with no jingle scheduled and no "boot" note in the tone ring: ' + JSON.stringify(m.kinds),
     JSON.stringify(m.boot.jingle));
  ok(!LINE.test(m.caption || ''),
     'and nothing of the readiness line on the caption either: "' + (m.caption || '') + '"');
  page.close();
  await killBrowsers();

  /* ---- B. REDUCED MOTION KEEPS THE SENTENCE AND DROPS THE FLOURISH ------ */
  page = await boot(exe, { url: GALAXY + '/', reduced: true,
                           label: 'an unmuted tab on a machine that asked for less motion' });
  await page.click();
  /* READ EARLY, because the caption is armed to fade: the sentence is raised by speakLine at
     the instant the gesture releases the held line, and a read taken a lazy five seconds later
     would be asserting the fade rather than the caption. */
  await sleep(400);
  const quiet = await page.json('({text: __galaxy.caption.text, up: __galaxy.caption.up})');
  ok(LINE.test(quiet.text || '') && quiet.up === true,
     'THE LINE ARRIVES AS A CAPTION on the quiet machine, raised and readable: "' +
     (quiet.text || '') + '"', JSON.stringify(quiet));
  await sleep(2100);
  const q = await page.json('({boot: __galaxy.boot, caption: __galaxy.caption.text,' +
    ' kinds: __galaxy.audio.played.map(function (t) { return t.kind; }),' +
    ' said: __galaxy.speech.said.map(function (s) { return s.text; })})');
  note('   boot: ' + JSON.stringify(q.boot));
  ok(q.boot.fired === 1 && q.boot.reduced === true,
     'THE CEREMONY STILL HAPPENS ON A QUIET MACHINE: it fired once and knows what kind of ' +
     'machine it is', JSON.stringify(q.boot));
  ok(q.boot.jingle.played === false && q.kinds.indexOf('boot') < 0,
     'AND THE FLOURISH IS WHAT IT DROPS: no jingle, no "boot" note on the chime bus - ' +
     JSON.stringify(q.kinds), JSON.stringify(q.boot.jingle));
  ok(/reduced-motion/.test(q.boot.jingle.why),
     'and it names the reason rather than looking broken: "' + q.boot.jingle.why + '"');
  ok(q.boot.said === true && (LINE.test(q.caption || '') || q.said.some((s) => LINE.test(s))),
     'BUT THE SENTENCE IS NOT DROPPED WITH IT: the readiness line reached the caption and the ' +
     'ledger - a request for less motion is not a request to be told less',
     JSON.stringify({ caption: q.caption, said: q.said }));
  page.close();
  await killBrowsers();

  /* ---- C. A PLAIN TAB GETS THE WHOLE CEREMONY -------------------------- */
  page = await boot(exe, { url: GALAXY + '/', label: 'a plain unmuted tab' });
  const before = await page.json('__galaxy.boot');
  ok(before.fired === 1 && before.spoke === false &&
     /first gesture/.test(before.why),
     'BEFORE ANY GESTURE the ceremony has fired and is HELD rather than lost: "' + before.why +
     '" - a browser that will not make a sound yet is not a butler with nothing to say',
     JSON.stringify(before));
  await page.click();
  await sleep(3800);
  const c = await page.json('({boot: __galaxy.boot,' +
    ' kinds: __galaxy.audio.played.map(function (t) { return t.kind; }),' +
    ' caption: __galaxy.caption.text,' +
    ' said: __galaxy.speech.said.map(function (s) { return s.text; })})');
  note('   boot: ' + JSON.stringify(c.boot));
  note('   the tone ring: ' + JSON.stringify(c.kinds));
  ok(c.boot.jingle.played === true && c.boot.jingle.notes >= 7,
     'THE JINGLE IS PLAYED, AND IT IS BUILT RATHER THAN FETCHED: ' + c.boot.jingle.notes +
     ' oscillator notes scheduled on the chime bus, no file and no network',
     JSON.stringify(c.boot.jingle));
  ok(c.boot.jingle.ms >= 2500 && c.boot.jingle.ms <= 3500,
     'AND IT LASTS ' + (c.boot.jingle.ms / 1000).toFixed(2) + 's, inside the 2.5-3.5s the ' +
     'mandate asks for - long enough to be a ceremony, short enough not to be a wait',
     JSON.stringify(c.boot.jingle));
  ok(c.kinds.indexOf('boot') >= 0,
     'and every one of those notes went through the SAME bus the chimes use, named "boot" in ' +
     'the ring: ' + JSON.stringify(c.kinds));
  ok(c.boot.said === true && (LINE.test(c.caption || '') || c.said.some((s) => LINE.test(s))),
     'WITH THE LINE UNDERNEATH IT, declarative and unhedged: the held sentence survived the ' +
     'wait for the gesture and was spoken, not discarded',
     JSON.stringify({ caption: c.caption, said: c.said }));

  /* AND ON ONE SURFACE, WHICH IS WHERE THE BOOT PLATES FOUND A DEFECT. The autoplay law joins
     the salutation and the readiness line into one breath, so the caption carries both while the
     card holds the greeting alone - and a yield rule written as character-for-character equality
     called those different sentences and left the greeting on the glass twice, forty pixels
     apart. Asserted here rather than in the one-surface section of voice_proof because this is
     the only moment in a session when two held lines are spoken as one. */
  const surf = await page.json('({carries: __galaxy.caption.carries,' +
    ' yielded: __galaxy.caption.yielded, up: __galaxy.caption.up})');
  ok(surf.up === true && surf.yielded === true && surf.carries.card === '' &&
     LINE.test(surf.carries.caption || ''),
     'AND ON EXACTLY ONE SURFACE while it is read: the caption carries the joined breath and ' +
     'the card has stood its paragraph down, so the greeting inside it is read once and not ' +
     'twice', JSON.stringify(surf));

  /* ---- AND ONCE PER SESSION, ASKED FOR RATHER THAN WAITED FOR ---------- */
  for (let i = 0; i < 4; i++) {
    await page.evaluate('__galaxy.brain.refresh().then(function () { return 1; })');
    await sleep(350);
  }
  const end = await page.json('__galaxy.boot');
  note('   after four more healthy readings: ' + JSON.stringify(end));
  ok(end.fired === 1 && end.at === c.boot.at && end.jingle.notes === c.boot.jingle.notes &&
     end.healthy > c.boot.healthy,
     'ONCE PER SESSION, AND NOT ONCE PER POLL: ' + end.healthy + ' healthy /health readings ' +
     'have now landed, four of them demanded just now, and the ceremony is still one firing ' +
     'at one timestamp with the same ' + end.jingle.notes + ' notes',
     JSON.stringify({ before: c.boot, after: end }));
  const kindsEnd = await page.json('__galaxy.audio.played.map(function (t) { return t.kind; })');
  ok(kindsEnd.filter((k) => k === 'boot').length === c.kinds.filter((k) => k === 'boot').length,
     'and not one further "boot" note reached the bus while those readings landed: ' +
     JSON.stringify(kindsEnd));
  page.close();
}

main()
  .catch((e) => { fail++; reds.push('the run threw: ' + e.message);
                  console.log('\n  THREW ' + e.stack); })
  .finally(async () => {
    await killBrowsers();
    for (const d of profiles) { try { rmSync(d, { recursive: true, force: true }); } catch { } }
    console.log('\n  VERIFY ' + pass + '/' + (pass + fail) +
                (fail ? ' PASS - ' + fail + ' FAILED' : ' PASS'));
    for (const r of reds) console.log('\n  failed: ' + r);
    process.exit(fail ? 1 : 0);
  });
