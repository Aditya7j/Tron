/* THE COMMAND DECK, measured rather than admired.
 *
 * Everything this file checks is a claim the new look makes about itself, and every one of
 * them is the kind of claim that is easy to make and easy to get wrong:
 *
 *   THE FRAME RATE. Five seconds of idle galaxy, sampled from the page's own
 *     requestAnimationFrame deltas - not from a profiler's summary, and not from the
 *     page's own opinion of itself alone: Node computes the mean and the worst frames from
 *     the raw deltas, and then compares its answer to __galaxy.deck.fps. Two independent
 *     measurements agreeing is evidence; one number in a debug panel is not. The GPU is
 *     named in the output, because "52fps" means nothing if the renderer turns out to be
 *     software.
 *   THE AUTO-DISABLE, provoked for real. CPU throttling is turned up until the page cannot
 *     hold 45fps, and then the bloom is expected to REMOVE ITSELF within its three-second
 *     grace period and say why. A guard that has never fired is a guard nobody has tested.
 *   THE OVERLAYS DO NOT BLOCK ANYTHING. Not "pointer-events is none in the stylesheet" -
 *     document.elementFromPoint at the middle of each button, which is the same question
 *     the headless hand asks, and then a real Input event on No that has to land.
 *   THE TYPEWRITER DOES NOT HIDE THE ANSWER. While the reveal is mid-flight, the card's
 *     textContent must already be the whole sentence. This is the one thing that would
 *     quietly break every other harness in this repo.
 *   THE CAP ON THE VOICE OF THE MACHINE. Read off the gain node, not off the constant.
 *   AND THREE PICTURES: the galaxy, the glass, and the dimmed gate.
 *
 * GPU-BACKED, AND NOW HEADLESS, which is a change of means and not of subject. The rule has
 * always been that a frame rate measured under software rasterisation is a number about
 * SwiftShader and not about this machine, and that rule is why this used to open a real
 * window. The window turned out to be the problem: requestAnimationFrame belongs to the
 * compositor, and Windows stops driving the compositor for a window it thinks nobody can
 * see. Anything that took the foreground mid-run - an editor, a console, the shell this was
 * launched from - froze the page a few seconds after boot, and fifteen checks then failed
 * while pointing at the frame rate. Worse, a real window sits under a real mouse: one run
 * recorded nine camera flights in thirty "idle" seconds, every one of them a genuine click
 * on the canvas. --headless=new keeps the hardware renderer - on this machine both modes
 * report the same ANGLE/D3D11 Intel Arc device, which the run prints so you can check - and
 * gives back a compositor that draws whether or not anyone is watching. Set DECK_HEADED=1
 * to open the window and watch it with your own eyes; the numbers are then at the mercy of
 * your window manager, which is the trade being made. Not muted, for the same reason
 * tools_live.mjs is not. It clicks No and nothing else, so it writes nothing to your diary.
 *
 * Usage:  python server.py 2> server-trace.log   then   node deck_proof.mjs
 *         DECK_HEADED=1 node deck_proof.mjs      to watch it happen in a window
 */
import { spawn, spawnSync } from 'node:child_process';
import { mkdtempSync, rmSync, existsSync, writeFileSync, readFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
/* THE REDACTOR'S OWN DEPENDENCY, WHICH WAS MISSING - and the shape of the bug is worth a line
   because it hid for a whole section. noaddr() below is called by EVERY ok(), but it only
   reaches createHash when a claim actually contains an email address, so the file ran green
   through a hundred and ninety-four assertions and then died with `createHash is not defined`
   the moment the Google row printed a connected account. The sign-off read 194/201 against a
   baseline of 254 and the missing sixty looked like a deck that had stopped working.
   IT FAILED CLOSED, WHICH IS THE ONE MERCY: the throw happens inside noaddr, before console.log,
   so no address was ever printed unredacted. The standing rule - no account email in a log
   except as a sha256 digest - held by accident rather than by design.
   FAILURE MODE IF THIS IMPORT IS REMOVED AGAIN: the harness stops at the first assertion whose
   text contains an address, which on this machine is a different assertion every time the
   Google connection changes, so the file appears to fail in an unrelated place at random. */
import { createHash } from 'node:crypto';

/* The project root as this file's own place, not as the shell's: the corpus swap below is a
   build.py run and a file read, and both would be about the wrong directory otherwise. */
const ROOT = dirname(fileURLToPath(import.meta.url));

const GALAXY = 'http://127.0.0.1:4700';
const PORT = 9236;
const CDP = 'http://127.0.0.1:' + PORT;
const CHROMES = [
  'C:/Program Files/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Google/Chrome/Application/chrome.exe',
  process.env.LOCALAPPDATA + '/Google/Chrome/Application/chrome.exe',
];
/* Headless unless asked otherwise - see the header. The flag is read once here so every
   decision below that depends on it reads the same answer. */
const HEADED = process.env.DECK_HEADED === '1';
const IDLE_MS = 5000;          // the recording the spec asks for
/* Thirty seconds, and the spec's own number. It is long on purpose: the failure it is for -
   a slow constant orbit - is invisible over one second and unmistakable over thirty, and any
   easing that has not finished settling by then was never going to. */
const CALM_MS = 30000;
/* 55, raised from 50 when the flat spheres became planets - text-mapped worlds with an
   atmosphere each, spinning, under a bloom. The point of raising a floor at the same time
   as adding the thing that has to clear it is that the harness cannot then be said to have
   made room for the feature. */
const FPS_FLOOR = 55;
/* The planetarium's resting emissive for a SELECTED world - the state the sweep has to
   return it to, stated here rather than read back from the page, so "it put the glow back"
   is checked against a number and not against the defendant's own account of itself. A
   selected world sits at EMISSIVE_HOT because that is the planetary way of being selected:
   lit from within rather than painted white. */
const PLANET_EMISSIVE_HOT = 0.34;
/* UI MANDATE II: THE CORE IS GONE, AND SO IS ITS SUM. The dust is one written constant - every
   point of the allocation, DUST_PTS = 13800 - and presN is `density >= 1 ? n : max(8, round(n *
   density))` with no per-group floors, because the dust has no groups. Duplicated here for the
   reason the core's sum was: if the fill's count moves, this goes red and says which way. */
const DUST_PTS = 13800;
const dustCount = (d) => (d >= 1 ? DUST_PTS : Math.max(8, Math.round(DUST_PTS * d)));
const DUST_FULL = dustCount(1);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

/* Two seconds of digital zero, 16-bit PCM mono, which is the only shape Chrome's fake
   audio capture will read. Chrome loops it, so the room is silent for as long as the run
   lasts. Written into the throwaway profile, so it leaves with it. */
function silence(dir) {
  const path = join(dir, 'silence.wav');
  const rate = 48000, n = rate * 2, bytes = n * 2;
  const b = Buffer.alloc(44 + bytes);
  b.write('RIFF', 0); b.writeUInt32LE(36 + bytes, 4); b.write('WAVE', 8);
  b.write('fmt ', 12); b.writeUInt32LE(16, 16); b.writeUInt16LE(1, 20);
  b.writeUInt16LE(1, 22); b.writeUInt32LE(rate, 24); b.writeUInt32LE(rate * 2, 28);
  b.writeUInt16LE(2, 32); b.writeUInt16LE(16, 34);
  b.write('data', 36); b.writeUInt32LE(bytes, 40);
  writeFileSync(path, b);
  return path;
}

/* ============ NOTHING THIS HARNESS PRINTS MAY CARRY THE ACCOUNT ADDRESS ============
 * The standing rule is absolute: no credential, token, authorization code, client secret or
 * account email in a log, a plate or the lookbook except as a sha256 digest. This harness
 * breached it without ever meaning to. `note('orders: ...')` dumps every palette row's label
 * AND its state line, and the Google row's state line is literally
 * "GOOGLE: CONNECTED · <the employer's address>" - so four saved deck_proof logs carried it.
 *
 * THE CURE IS AT THE PRINTER AND NOT AT THE ONE CALL SITE, because the call site was not the
 * mistake - reading the sheet's own sentences is exactly what this harness is for. Any future
 * assertion that quotes page text would breach the rule again, and a rule that has to be
 * remembered at every new console.log is a rule that will be forgotten at one of them.
 *
 * A DIGEST AND NOT A DELETION. The reason the address was in the log at all is that it is
 * evidence: it says the grant is open and whose it is, and "CONNECTED" with the address simply
 * removed could be any account or none. Eight hex characters keep the one property a reader of
 * two logs needs - whether it is the SAME account - and carry nothing back.
 *
 * FAILURE MODE if the pattern were tighter: an address with a plus-tag or a subdomain would
 * slip through and read as prose. It is deliberately the broadest thing that is still an
 * address, and it is applied to `detail` as well, because a FAIL prints page text verbatim and
 * a breach that only happens on a red line is the one nobody looks for. */
const ADDR = /[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/g;
const noaddr = (m) => String(m).replace(ADDR, (a) =>
  '<account · sha256 ' + createHash('sha256').update(a).digest('hex').slice(0, 8) + '>');

let checks = 0; const bad = [];
const ok = (c, claim, detail) => {
  checks++; console.log((c ? '  ok   ' : '  FAIL ') + noaddr(claim));
  if (!c) { bad.push(noaddr(claim)); if (detail) console.log('         ' + noaddr(detail)); }
};
const note = (m) => console.log('  note ' + noaddr(m));
const procs = []; const profiles = [];

/* ============ THE REFERENCE CORPUS, AND WHY THIS HARNESS NOW BUILDS ITS OWN ============
 * THIS IS A RENDERER PROOF, AND IT WAS QUIETLY A CORPUS PROOF. Half of what is below is a
 * claim about how RELATIONS are drawn: one travelling dot per link, no Line object anywhere,
 * ring thickness as a ladder of four widths earned by a world's own link count, simplify-on-
 * load showing the strong subset and hiding the rest. Every one of those needs a graph with
 * links in it, and until PART 8 there was one by luck: the collection shipped with a dummy
 * cafe whose thirty notes cross-referenced each other, and this file scored 238/238 against
 * it without ever saying that was a dependency.
 *
 * PART 8 moved that corpus to archive/quarantine/ and left three true notes behind, which do
 * not mention one another. Nought links. Five checks went red and a sixth threw on
 * __galaxy.active[0], taking a hundred and seventy-six further checks with it - and not one
 * of those reds was about the renderer. The harness was reporting the shape of his
 * collection.
 *
 * SO IT BRINGS ITS OWN SKY. graph-data.js is rebuilt from archive/quarantine/ for the length
 * of the run and rebuilt from notes/ again afterwards, and BOTH builds pass --no-vectors, so
 * the embeddings are never touched: the quarantine stays unindexed, which is the whole point
 * of it being quarantined, and his own notes are never re-embedded to pay for a frame-rate
 * measurement. Nothing is written into notes/ at all - the thirty notes already exist, they
 * are not his, and they are the exact corpus the numbers below were calibrated against.
 *
 * AND THE RESTORATION IS A CHECK. A harness that leaves the galaxy showing a fictional cafe
 * has broken the thing it was measuring, and it must say so in its own verdict line. */
const REF = 'archive/quarantine';
const PY = 'C:/Users/Fullstack Developer/AppData/Local/Programs/Python/Python313/python.exe';
let swapped = null;               // the reading taken before the swap, or null if never swapped

function buildFrom(dir) {
  const args = dir ? [dir, '--no-vectors'] : ['--no-vectors'];
  const p = spawnSync(PY, ['build.py'].concat(args), { cwd: ROOT, encoding: 'utf8' });
  const line = String(p.stdout || '').split(/\r?\n/)
    .filter((l) => /worlds|nodes|links/i.test(l)).slice(-1)[0] || '';
  return { code: p.status, line: line.trim() };
}
/* WHAT THE PAGE WILL LOAD, read out of the file the page loads rather than out of /health -
   the server holds its own in-memory index and this swap deliberately does not disturb it.
   `root` is the notesRoot build.py stamped into the file, and it is the field the restoration
   is asserted on: a count cannot be the claim here, because the boss can file a note through
   the Census or the remember hand while this harness is running - he did, twice, during the
   run that taught this - and "his collection is back" must not go red because his collection
   grew. The root is the thing that was swapped, so the root is the thing to check. */
function graphCounts() {
  try {
    const src = readFileSync(join(ROOT, 'viewer', 'graph-data.js'), 'utf8');
    const n = (src.match(/"id":\s*\d+/g) || []).length;
    const l = (src.match(/"source":\s*\d+/g) || []).length;
    const m = src.match(/"notesRoot":\s*"([^"]*)"/);
    return { nodes: n, links: l, root: m ? m[1] : '?' };
  } catch { return { nodes: -1, links: -1, root: '?' }; }
}

class Page {
  constructor(u) { this.u = u; this.id = 0; this.w = new Map(); this.casts = 0; this.casting = false; this.errors = []; }
  open() { return new Promise((res, rej) => {
    this.ws = new WebSocket(this.u);
    this.ws.onopen = () => res(this);
    this.ws.onerror = (e) => rej(new Error('socket: ' + (e.message || 'failed')));
    this.ws.onmessage = (ev) => { const m = JSON.parse(ev.data);
      /* WHAT THE PAGE THREW. An exception inside the animation loop kills the loop:
         the re-schedule at the end of the tick never runs, every counter stops at the same
         number, and from then on every frame-rate check in this file fails while pointing
         at the frame rate instead of at the throw. Collected here so the page's own error
         is in the transcript, named, at the moment it happened. */
      if (m.method === 'Runtime.exceptionThrown') {
        const d = m.params && m.params.exceptionDetails;
        const t = d && (d.exception && (d.exception.description || d.exception.value) || d.text);
        this.errors.push(String(t).split('\n').slice(0, 3).join(' | '));
        return;
      }
      /* A screencast frame is not a reply to anything, and Chrome stops sending them after
         a handful go unacknowledged - which would quietly undo the keep-alive below
         halfway through a measurement. So they are counted and acked here. */
      if (m.method === 'Page.screencastFrame') {
        this.casts++;
        this.send('Page.screencastFrameAck', { sessionId: m.params.sessionId }).catch(() => {});
        return;
      }
      const f = this.w.get(m.id); if (f) { this.w.delete(m.id); f(m); } }; }); }
  /* THE FRAMES KEEP COMING. Every frame-rate claim in this file is a claim about
     requestAnimationFrame, and Windows stops calling it the moment its compositor decides
     this window is behind another one. That is not a small effect: a run made while an
     editor was maximised over the window recorded 0 frames in 5 seconds, and thirteen
     checks failed - the frame rate, the travelling dots, the hidden-tab test, the whole
     calm sky - for a reason with nothing whatever to do with the page. A live screencast
     is the one lever that makes the compositor keep producing frames for a window nobody
     is looking at. Nothing is done with the pictures; they are 80x60 at quality 5, which
     costs less than the measurement it protects. */
  async cast(on) {
    if (on && !this.casting) {
      await this.send('Page.enable');
      await this.send('Page.startScreencast',
        { format: 'jpeg', quality: 5, maxWidth: 80, maxHeight: 60, everyNthFrame: 1 });
      this.casting = true;
    } else if (!on && this.casting) {
      await this.send('Page.stopScreencast');
      this.casting = false;
    }
    return this.casting;
  }
  send(method, params) { const id = ++this.id;
    return new Promise((res, rej) => {
      const bomb = setTimeout(() => { this.w.delete(id); rej(new Error(method + ' timed out')); }, 30000);
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
  /* A FULL FRAME BY DEFAULT, and a CLOSE-UP when a rectangle is handed in. The clip is
     captured at 2x so a 210px hologram is legible as a plate - the lookbook has to be able
     to show that the brow and the lips are readable in the density, which a 210px crop of a
     1400px screenshot cannot say either way. */
  async shot(file, clip) {
    const r = await this.send('Page.captureScreenshot', clip
      ? { format: 'png', captureBeyondViewport: false,
          clip: { x: clip.left, y: clip.top, width: clip.w, height: clip.h,
                  scale: clip.scale || 2 } }
      : { format: 'png' });
    const data = r.result && r.result.data;
    if (!data) throw new Error('no screenshot came back');
    writeFileSync(file, Buffer.from(data, 'base64'));
    return file;
  }
  close() { try { this.ws.close(); } catch { } }
}
const cdp = async (p) => { const r = await fetch(CDP + p); const t = await r.text();
  try { return JSON.parse(t); } catch { return t; } };

/* THE SERVER, FOR THE ONE SECTION THAT NEEDS A REAL SESSION. Work mode is subscribed to
   focus.py's SSE push and to nothing else, so the only honest way to make the room change
   is to start a session on the server the way the card does. It is ended with `abort`,
   which records no ledger row and moves no streak - the same precedent lock_proof.mjs
   sets for exactly this reason: an instrument that edits what it measures is not one. */
const galaxy = async (path, body) => {
  const r = await fetch(GALAXY + path, body === undefined ? { }
    : { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body) });
  const t = await r.text();
  try { return JSON.parse(t); } catch { return t; }
};

/* A DEADLINE, not a number of tries. This counted iterations - ms/150 of them - on the
   assumption that a poll costs nothing, which is true right up until the section that
   throttles the CPU twenty times over. There, every evaluate takes seconds, and a "30s"
   wait for a guard that was never going to fire ran for more than ten minutes before
   anyone looked. Wall-clock is what the caller meant. */
async function waitFor(page, expr, ms = 10000) {
  const until = Date.now() + ms;
  while (Date.now() < until) {
    try { if (await page.evaluate(expr)) return true; } catch { }
    await sleep(150);
  }
  return false;
}

/* The computed style of a real element or of one of its pseudo-elements, which is where
   every glow and every ring on this page lives. */
const css = (page, id, prop, pseudo) => page.evaluate(
  'getComputedStyle(document.getElementById(' + JSON.stringify(id) + ')' +
  (pseudo ? ',' + JSON.stringify(pseudo) : '') + ').' + prop);

/* WHAT IS ACTUALLY UNDER THE MIDDLE OF A BUTTON. The same question the harnesses ask by
   dispatching a mouse event at that point - asked here as a value, so a failure names the
   element that is in the way instead of just timing out. */
const topOf = (page, id) => page.evaluate(`(function(){
  var el = document.getElementById(${JSON.stringify(id)});
  if (!el) return 'missing';
  var r = el.getBoundingClientRect();
  var hit = document.elementFromPoint(Math.round(r.left + r.width / 2),
                                      Math.round(r.top + r.height / 2));
  if (!hit) return 'nothing';
  if (hit === el || el.contains(hit)) return 'itself';
  return (hit.id ? '#' + hit.id : hit.tagName.toLowerCase() +
          (hit.className ? '.' + String(hit.className).split(' ')[0] : ''));
})()`);

async function main() {
  console.log('\n  the command deck: five seconds of idle sky, and three pictures\n');
  const exe = CHROMES.find((p) => existsSync(p));
  if (!exe) throw new Error('no chrome.exe');
  const health = await (await fetch(GALAXY + '/health')).json();
  note('server up, model ' + (health.model || '?'));

  /* THE SKY THIS RUN MEASURES. See the note above the swap helpers: the relation half of
     this file needs a graph with relations in it, and his own three notes do not mention
     each other. Swapped only when there is nothing to draw, so a collection that has grown
     links of its own is measured as it stands and the quarantine is left alone. */
  const mine = graphCounts();
  if (mine.links > 0) {
    note('the collection has ' + mine.links + ' relations of its own, so it is measured as ' +
         'it stands and no corpus is swapped in');
  } else {
    const built = buildFrom(REF);
    const ref = graphCounts();
    swapped = mine;
    ok(built.code === 0 && ref.links > 0,
       'his collection draws ' + mine.links + ' relations, so the reference corpus is built ' +
       'in for the length of the run: ' + ref.nodes + ' worlds, ' + ref.links + ' relations',
       JSON.stringify({ exit: built.code, line: built.line, ref: ref }));
    if (!(built.code === 0 && ref.links > 0)) {
      throw new Error('the reference corpus would not build; nothing below would mean anything');
    }
  }

  const profile = mkdtempSync(join(tmpdir(), 'deck-'));
  profiles.push(profile);
  /* Headed and GPU-backed on purpose - see the header. A fixed window size so the
     screenshots are comparable between runs and the bloom's half-resolution can be
     checked against a number rather than against itself. */
  const chrome = spawn(exe, [
    '--remote-debugging-port=' + PORT, '--user-data-dir=' + profile,
    '--no-first-run', '--no-default-browser-check',
    '--autoplay-policy=no-user-gesture-required',
    /* These three ask Chrome not to reason about occlusion and not to throttle a renderer
       it thinks is in the background. They are the documented answer to the frozen-window
       problem and they are kept for the DECK_HEADED=1 case, where they help - but they were
       not enough on their own: with all three set, a headed run still went from 60fps to 0
       about four seconds after boot. Hence the line below them. */
    '--disable-features=CalculateNativeWinOcclusion',
    '--disable-backgrounding-occluded-windows',
    '--disable-renderer-backgrounding',
    ...(HEADED ? [] : ['--headless=new']),
    /* THE MICROPHONE, GRANTED AND SILENT. The idle recording below is taken with the Open
       Ear held open - a session with a live getUserMedia stream, an AnalyserNode and a
       per-frame RMS on top of everything else the deck is doing - because "55fps with the
       Open Ear idle" is the requirement and a frame rate measured without it would be
       measuring a page nobody uses. The capture reads a file of zeros rather than Chrome's
       440Hz test tone: a sine wave is a voice as far as any VAD is concerned, and the
       session would spend the whole recording thinking somebody was talking. */
    '--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream',
    '--use-file-for-fake-audio-capture=' + silence(profile),
    '--window-size=1400,940', '--new-window', GALAXY,
  ], { detached: true, stdio: 'ignore' });
  procs.push(chrome);

  for (let i = 0; i < 80; i++) { try { await cdp('/json/version'); break; } catch { await sleep(250); } }
  note('chrome: ' + ((await cdp('/json/version')).Browser || '?'));
  let target = null;
  for (let i = 0; i < 40; i++) {
    const l = await cdp('/json/list');
    target = (Array.isArray(l) ? l : []).filter(t => t.type === 'page')
      .find(t => t.url.includes('127.0.0.1:4700'));
    if (target) break; await sleep(300);
  }
  if (!target) throw new Error('no viewer page');
  const page = new Page(target.webSocketDebuggerUrl);
  await page.open();
  await page.send('Runtime.enable');
  await page.send('Page.enable');
  /* THE WINDOW HAS TO BE THE ONE IN FRONT - when there is a window at all. Chrome's
     occlusion detection is not the same thing as document.visibilityState: a covered window
     still reports "visible" while its rAF clock is stopped and its CSS transitions stand
     still, so it does not produce a slow number, it produces a stuck one, and the harness
     then blames the page. Under DECK_HEADED=1 this is the best that can be asked for, and
     it is not much: bringToFront puts the window in front at this instant and cannot keep
     it there. In the default headless run there is no window to cover and the call is a
     harmless no-op. */
  try { await page.send('Page.bringToFront'); } catch (e) { note('bringToFront: ' + e.message); }
  ok(await waitFor(page, '!!(window.__galaxy && window.__galaxy.deck)', 30000),
     'the viewer is up and exposes the deck');
  await waitFor(page, '__galaxy.nodes.length > 0', 20000);
  /* A LIVE SUBSCRIPTION TO THE FRAMES, which in a headed run is what persuades the
     compositor to keep drawing a window nobody is looking at. Headless needs no persuading,
     so this is insurance for DECK_HEADED=1 rather than the load-bearing part - and it is
     insurance that did not hold on its own, which is why the default changed.
     Started AFTER the page has loaded, and that ordering matters: a screencast begun while
     the first navigation is in flight is torn down when that navigation commits, and the
     subscription then reports itself as on while no frames arrive. Every re-arming below is
     there for the same reason. Wrapped, because a mode that refuses to screencast should
     not end the run. */
  try { await page.cast(true); } catch (e) { note('screencast: ' + e.message); }
  await sleep(300);
  note((HEADED ? 'headed' : 'headless') + ' · frames subscribed: ' +
       (page.casting ? 'yes' : 'no') + ', ' + page.casts + ' pictures in the first moment');

  /* ---- 0. WHAT WE ARE MEASURING ON ---------------------------------------- */
  const gpu = await page.evaluate(`(function(){
    try {
      var c = document.createElement('canvas');
      var gl = c.getContext('webgl2') || c.getContext('webgl');
      if (!gl) return 'no webgl';
      var e = gl.getExtension('WEBGL_debug_renderer_info');
      return e ? String(gl.getParameter(e.UNMASKED_RENDERER_WEBGL)) : 'unnamed';
    } catch (err) { return 'error: ' + err.message; }
  })()`);
  note('renderer: ' + gpu);
  /* AND IT HAD BETTER BE THE REAL ONE. This was a warning in a note, which was enough while
     the run always opened a window; now that the default is headless it is the promise the
     header makes, so it is checked. A 60fps under SwiftShader would be a number about this
     CPU and would tell you nothing about the deck. */
  ok(!/swiftshader|software|llvmpipe|disabled/i.test(gpu),
     'MEASURED ON THE REAL GPU, not a software rasteriser - every frame number below is ' +
     'about this machine\u2019s hardware', gpu);

  /* ---- 1. THE DECK CAME UP ------------------------------------------------ */
  await waitFor(page, '__galaxy.deck.stars === "webgl"', 12000);
  /* The canvas field is faded out before it is stopped - 800ms of CSS and then the loop -
     so this waits for the handover to finish rather than catching it mid-dissolve. A
     harness that samples a transition halfway through and calls it a failure is measuring
     its own timing, not the page's. */
  await waitFor(page, '__galaxy.deck.canvasLive === false', 4000);
  /* AND THE AUDITION HAS TO BE OVER. The page spends its first few seconds measuring
     itself with the bloom off and then on, and drops the glow if it costs too much here.
     Recording frames in the middle of that would be recording the audition. */
  ok(await waitFor(page, '__galaxy.deck.probation !== "running"', 14000),
     'the bloom’s audition finished before anything was timed');
  const deck = await page.json('({on: __galaxy.deck.on, stars: __galaxy.deck.stars,' +
    ' bloom: __galaxy.deck.bloom, why: __galaxy.deck.why, trouble: __galaxy.deck.trouble,' +
    ' three: __galaxy.deck.three, lines: __galaxy.deck.lines,' +
    ' drawn: __galaxy.deck.starsDrawn, res: __galaxy.deck.bloomRes,' +
    ' canvas: __galaxy.deck.canvasLive, probation: __galaxy.deck.probation,' +
    ' baseline: __galaxy.deck.baseline, trial: __galaxy.deck.trial})');
  note('deck: ' + JSON.stringify(deck));
  ok(deck.on === true, 'the deck booted: three.js loaded and the graph\u2019s scene was found',
     JSON.stringify(deck.trouble));
  ok(deck.stars === 'webgl' && deck.drawn > 0,
     'the starfield is a real particle system, PROVED by the renderer\u2019s own count of ' +
     'points drawn (' + deck.drawn + ')',
     JSON.stringify({ stars: deck.stars, trouble: deck.trouble }));
  ok(deck.canvas === false,
     'and the 2D canvas field has stopped - two skies is one sky too many, and the ' +
     'expensive one is the one nobody can see');
  /* THE SILENT WIRES, from the deck's side of the house. This check used to read
     `deck.lines > 0` and insist the links' own materials were there for the breathing pulse
     to have something to breathe on. There is no pulse now and there are no materials: the
     line geometry is gone, and a connection exists only as its travelling dot. The
     assertion is inverted rather than deleted because the deck counts link materials by
     walking the live scene, which makes it a witness INDEPENDENT of the one in section 1d -
     that one asks the library what it was told, this one asks the scene what is in it. */
  ok(deck.lines === 0, 'and the deck, walking the scene itself, finds NO link materials at ' +
     'all (' + deck.lines + ' for ' + (await page.evaluate('__galaxy.active.length')) +
     ' relations) - there is no hairline left to breathe, which is the point',
     JSON.stringify({ lines: deck.lines }));
  if (deck.bloom) {
    const vp = await page.json('({w: innerWidth, h: innerHeight})');
    ok(!!deck.res && Math.abs(deck.res[0] - vp.w * 0.5) <= 2 &&
       Math.abs(deck.res[1] - vp.h * 0.5) <= 2,
       'the bloom runs at HALF resolution, read off the pass: ' + JSON.stringify(deck.res) +
       ' for a ' + vp.w + '\u00d7' + vp.h + ' viewport',
       JSON.stringify({ res: deck.res, viewport: vp }));
  } else {
    note('no bloom this run (' + (deck.why || deck.trouble || 'no reason given') +
         ') - the page is expected to be perfectly good without it, which is the point ' +
         'of the guard');
  }
  /* THE AUDITION IS ALLOWED TO GO EITHER WAY. What is being proved is that it HAPPENED
     and that its verdict matches what the page then did - a page that kept a bloom it
     measured as too expensive, or dropped one it measured as cheap, would be lying to
     itself about its own frame rate. */
  note('audition: ' + deck.probation + ' · ' + deck.baseline + 'fps without the glow, ' +
       deck.trial + 'fps with it');
  ok(deck.probation === 'kept' || deck.probation === 'dropped',
     'the bloom was AUDITIONED on this machine rather than assumed: ' + deck.probation,
     JSON.stringify({ probation: deck.probation, baseline: deck.baseline, trial: deck.trial }));
  ok(deck.probation === 'kept' ? deck.bloom === true : deck.bloom === false,
     'and the verdict is what the page actually did with it',
     JSON.stringify({ probation: deck.probation, bloom: deck.bloom, why: deck.why }));
  if (deck.probation === 'dropped') {
    ok(deck.baseline > 0 && deck.trial > 0 && /audition|fps/.test(deck.why),
       'the reason it went is READABLE and arithmetical, not a shrug: ' + deck.why,
       JSON.stringify({ baseline: deck.baseline, trial: deck.trial, why: deck.why }));
  }

  /* ---- 1b. THE INSTRUMENT NODES ------------------------------------------
     THE VISUAL CONSTITUTION, clause one: "delete the text-textured spheres and Saturn
     rings. Nodes become sleek dark metallic or frosted-glass spheres carrying one thin
     glowing equator ring: ring colour = cluster, ring thickness = connection density. No
     literal text on worlds; text lives in glass."

     Every one of those is a measurement here, and two of them are measurements that the
     old version of this block asserted the OPPOSITE of - it required a 512x256 text canvas
     per world and a ring only on the hubs. Those checks are gone rather than relaxed,
     because a harness that still passed on the old design would be proof of nothing.

       - ZERO characters, from a counter that nothing increments. THIS CLAUSE CHANGED WITH
         TRUE WORLDS and it is worth saying exactly how. There ARE colour maps now - one
         procedural skin per world, bands or craters or cracks - so "no texture" is no
         longer the assertion and could not be: the assertion is that not one CHARACTER is
         drawn on any of them. The text canvases were the problem, not the canvas;
       - ONE shared frost map for the whole galaxy, where there used to be one per world;
       - the crust carries both maps - a skin and the shared roughness - and its material
         is per KIND, so metalness is now a rocky world's 0.05 rather than a housing's 0.9;
       - EVERY world wears a ring and every ring lies in its own equator: tilted a quarter
         turn about X and exactly zero about Z, which is what makes it not Saturn;
       - THICKNESS IS DENSITY, recounted in Node from the link data and checked monotonic
         against the geometry's own inner and outer radius;
       - COLOUR IS CLUSTER, checked as a partition: same folder, same colour, and as many
         colours as there are folders on screen;
       - and each of those colours is a JEWEL by measurement - hue kept, saturation and
         lightness pinned - rather than by being one of seven strings this file also holds.
       - NOTHING IS BUILT AFTER BOOT. builds is read now and read again after the
         five-second recording, and if it moved, a world was rasterised inside a frame. */
  ok(await waitFor(page, '__galaxy.planets.on === true', 12000),
     'the planetarium booted: the node spheres are THREE.Groups now',
     JSON.stringify(await page.evaluate('__galaxy.planets.why')));
  const pl = await page.json('({on: __galaxy.planets.on, why: __galaxy.planets.why,' +
    ' count: __galaxy.planets.count, builds: __galaxy.planets.builds,' +
    ' textures: __galaxy.planets.textures, chars: __galaxy.planets.textChars,' +
    ' frost: __galaxy.planets.frost, tiers: __galaxy.planets.tiers,' +
    ' ringed: __galaxy.planets.ringed, spins: __galaxy.planets.spins,' +
    ' paints: __galaxy.planets.paints, nodes: __galaxy.nodes.length,' +
    ' seeds: Object.keys(__galaxy.planets.seeds).length,' +
    ' distinct: new Set(Object.keys(__galaxy.planets.seeds)' +
    '   .map(function (k) { return __galaxy.planets.seeds[k]; })).size,' +
    ' kinds: __galaxy.planets.kinds})');
  note('planets: ' + JSON.stringify(pl));
  ok(pl.count === pl.nodes && pl.builds === pl.nodes,
     'one world per note, built exactly once each (' + pl.builds + ' builds for ' +
     pl.nodes + ' notes)', JSON.stringify(pl));
  ok(pl.chars === 0 && pl.textures === pl.nodes,
     'NO LITERAL TEXT ON ANY WORLD: zero characters drawn, on ' + pl.textures + ' skins ' +
     'for ' + pl.nodes + ' notes - one procedural surface each, not one glyph between them',
     JSON.stringify({ textures: pl.textures, chars: pl.chars }));
  ok(pl.seeds === pl.nodes && pl.distinct === pl.nodes,
     'and NO TWO WORLDS SHARE A SEED: ' + pl.distinct + ' distinct seeds across ' +
     pl.seeds + ' worlds, counted from the page rather than promised by the generator',
     JSON.stringify({ seeds: pl.seeds, distinct: pl.distinct }));
  ok(pl.frost === 1,
     'and ONE frosted roughness map serves the whole galaxy, where there used to be a ' +
     'canvas per world (' + pl.frost + ')', JSON.stringify({ frost: pl.frost }));
  const shape = await page.json('__galaxy.planets.shapeOf(__galaxy.nodes[0].id)');
  note('one world: ' + JSON.stringify(shape));
  ok(!!shape && shape.map === true && shape.frosted === true,
     'the crust carries BOTH maps - its own procedural skin and the shared roughness - ' +
     'which is the surface TRUE WORLDS asked for',
     JSON.stringify(shape && { map: shape.map, frosted: shape.frosted }));
  ok(!!shape && ['gas', 'rocky', 'ice'].indexOf(shape.kind) >= 0,
     'and its material comes from its KIND (' + (shape ? shape.kind : '?') +
     '): metalness ' + (shape ? shape.metalness : '?') + ', roughness ' +
     (shape ? shape.roughness : '?') + ' - rock does not shine and gas is not a mirror',
     JSON.stringify(shape));
  ok(!!shape && shape.roughness > 0.3 && shape.metalness < 0.25,
     'never glossy and never chrome: roughness above 0.3, metalness below 0.25, so the key ' +
     'light leaves a lift rather than a small white sun',
     JSON.stringify(shape && { roughness: shape.roughness, metalness: shape.metalness }));
  ok(!!shape && shape.parts === 4 && shape.spinKids === 1 && shape.ring === true &&
     shape.shell === true,
     'and the world is assembled as specified: one spinning core inside a tilted orbit ' +
     'group, plus an atmosphere, a fresnel shell and ONE ring that do not spin with it',
     JSON.stringify(shape && { parts: shape.parts, spinKids: shape.spinKids,
                               ring: shape.ring, shell: shape.shell }));
  ok(!!shape && shape.radius > 1,
     'it is sized from the same nodeVal the old spheres used (radius ' +
     (shape ? shape.radius : '?') + ')');

  /* ---- 1c. THE KEY LIGHT, AND THE ANNOTATION THAT IS NOT A TOOLTIP -------
     TRUE WORLDS asks for two things that no earlier clause covered, and both are the kind
     of claim that is easy to write in a comment and hard to keep: ONE off-frame
     directional key light (not a second sun added alongside the library's own, which is
     how a scene ends up flat and lit from everywhere), and a hover annotation that is a
     mono HUD line with a one-pixel leader RATHER THAN A TOOLTIP BUBBLE. The bubble is the
     thing being replaced, so its absence is measured on the element itself - no
     background, no border, no corner radius, and the library's own .scene-tooltip never
     rendered - and the leader's height is read in pixels, because "one-pixel" is either
     one pixel or it is a style. */
  const lights = await page.json('__galaxy.planets.lights');
  note('lights: ' + JSON.stringify(lights));
  ok(!!lights && lights.key && lights.key.type === 'DirectionalLight' &&
     lights.added <= 1 && lights.retuned >= 1,
     'ONE key light, and it is the library\'s own directional retuned rather than a rival ' +
     'sun added next to it (found ' + (lights ? lights.found : '?') + ', retuned ' +
     (lights ? lights.retuned : '?') + ', added ' + (lights ? lights.added : '?') + ')',
     JSON.stringify(lights));
  ok(!!lights && !!lights.ambient && lights.ambient.intensity < 1.2,
     'and the ambient is a FILL, not the library\'s lit-from-everywhere pi (' +
     (lights && lights.ambient ? lights.ambient.intensity : '?') + ') - without that ' +
     'collapse there is no terminator to see',
     JSON.stringify(lights && lights.ambient));

  await page.evaluate('__galaxy.hover(__galaxy.nodes[0].id)');
  await sleep(500);
  const ann = await page.json('__galaxy.annotation');
  note('annotation: ' + JSON.stringify(ann));
  ok(!!ann && ann.on === true && /·/.test(ann.text || ''),
     'hovering a world names it: "' + (ann ? (ann.text || '').slice(0, 72) : '?') + '"',
     JSON.stringify(ann && { on: ann.on, text: ann.text }));
  ok(!!ann && ann.lead && ann.lead.drawn >= 1 && ann.lead.h === 1,
     'with a leader line exactly ONE pixel high (' + (ann && ann.lead ? ann.lead.h : '?') +
     ') running out to it', JSON.stringify(ann && ann.lead));
  ok(!!ann && ann.skin && ann.skin.bg === 'rgba(0, 0, 0, 0)' &&
     ann.skin.border === '0px' && ann.skin.radius === '0px' &&
     ann.skin.events === 'none' && /Mono/.test(ann.skin.mono || ''),
     'and it is NEVER A TOOLTIP BUBBLE: no background, no border, no radius, mono, and ' +
     'deaf to the pointer', JSON.stringify(ann && ann.skin));
  ok(!!ann && ann.tip && ann.tip.shown === false && !ann.tip.html,
     'the library\'s own .scene-tooltip is empty and never shown - the bubble was replaced, ' +
     'not covered up', JSON.stringify(ann && ann.tip));
  await page.evaluate('__galaxy.hover(null)');

  /* THE LADDER AND THE PARTITION, both recounted here rather than believed. The degrees
     are counted in Node from __galaxy.active - the same undirected, de-duplicated count the
     page uses - and the cluster of each world is read from the node data, so neither claim
     is settled by asking the page what it thinks it did. */
  const rings = await page.json(`(function(){
    var deg = new Map();
    __galaxy.nodes.forEach(function(n){ deg.set(n.id, 0); });
    var seen = new Set();
    __galaxy.active.forEach(function(l){
      var a = typeof l.source === 'object' ? l.source.id : l.source;
      var b = typeof l.target === 'object' ? l.target.id : l.target;
      var k = a < b ? a + '>' + b : b + '>' + a;
      if (seen.has(k) || a === b) return;
      seen.add(k);
      deg.set(a, deg.get(a) + 1); deg.set(b, deg.get(b) + 1);
    });
    var out = [], of = __galaxy.planets.ringOf;
    __galaxy.nodes.forEach(function(n){
      var r = of[n.id];
      if (!r) return;
      out.push({ id: n.id, group: n.group, mine: deg.get(n.id), page: r.deg,
                 tier: r.tier, width: r.width, inner: r.inner,
                 tiltX: r.tiltX, tiltZ: r.tiltZ, colour: r.colour, visible: r.visible });
    });
    return out;
  })()`);
  const tiers = await page.json('({tiers: __galaxy.sky.ringTiers, at: __galaxy.sky.ringAt,' +
    ' alpha: __galaxy.sky.ringAlpha, inner: __galaxy.sky.ringIn})');
  note('ring tiers ' + JSON.stringify(tiers.tiers) + ' at ' + JSON.stringify(tiers.at) +
       ', inner ' + tiers.inner + ', alpha ' + tiers.alpha);
  ok(rings.length === pl.nodes && pl.ringed === pl.nodes,
     'EVERY WORLD WEARS ONE: ' + pl.ringed + ' rings for ' + pl.nodes + ' worlds - the ' +
     'ring is the readout every instrument carries, not a badge a few of them earn',
     JSON.stringify({ ringed: pl.ringed, nodes: pl.nodes, measured: rings.length }));
  /* NOT SATURN, and this is the check the constitution's "Saturn rings" clause comes down
     to: a quarter turn about X puts the ring in the body's own equatorial plane, and any
     rotation about Z at all is the jaunty planetary tilt that was deleted. */
  const tilted = rings.filter((r) => Math.abs(r.tiltX - Math.PI / 2) > 1e-4 || r.tiltZ !== 0);
  ok(tilted.length === 0,
     'AND IT IS AN EQUATOR RING, NOT A SATURN RING: every one of ' + rings.length +
     ' is a quarter turn about X and exactly zero about Z',
     JSON.stringify(tilted.slice(0, 3)));
  ok(rings.every((r) => Math.abs(r.inner - tiers.inner) < 1e-6) &&
     tiers.inner > 1 && tiers.inner < 1.1,
     'each sits just clear of its own crust (inner radius ' + tiers.inner +
     ' against a body of 1), so thickness grows outwards rather than eating the world',
     JSON.stringify(rings.slice(0, 2).map((r) => r.inner)));
  ok(tiers.tiers.length === 4 && tiers.at.length === 3 &&
     tiers.tiers.every((w, i) => i === 0 || w > tiers.tiers[i - 1]) &&
     tiers.tiers[3] <= 0.13,
     'THE LADDER IS FOUR STRICTLY INCREASING THICKNESSES, the thickest still a hairline at ' +
     tiers.tiers[3] + ' of a radius: ' + tiers.tiers.join(' < '),
     JSON.stringify(tiers));
  /* THICKNESS IS DENSITY, proved as a function rather than as a correlation: a world with
     more links may never wear a thinner ring than a world with fewer, and the width it
     wears has to be the tier its OWN count earns under the page's boundaries. */
  const ladder = (deg) => {
    let t = 0;
    tiers.at.forEach((a, i) => { if (deg >= a) t = i + 1; });
    return tiers.tiers[Math.min(t, tiers.tiers.length - 1)];
  };
  const misdeg = rings.filter((r) => r.mine !== r.page);
  const miswidth = rings.filter((r) => Math.abs(r.width - ladder(r.mine)) > 1e-4);
  const inversions = rings.filter((a) => rings.some((b) => b.mine > a.mine && b.width < a.width));
  ok(misdeg.length === 0 && miswidth.length === 0 && inversions.length === 0,
     'RING THICKNESS IS CONNECTION DENSITY: all ' + rings.length + ' widths are the tier ' +
     'their own recounted link total earns, and not one world with more links wears a ' +
     'thinner ring than one with fewer',
     JSON.stringify({ degMismatch: misdeg.slice(0, 3), widthMismatch: miswidth.slice(0, 3),
                      inversions: inversions.slice(0, 3) }));
  const widthTally = {};
  rings.forEach((r) => { widthTally[r.width] = (widthTally[r.width] || 0) + 1; });
  ok(Object.keys(widthTally).length >= 2,
     'and the ladder is actually in use - ' + JSON.stringify(widthTally) +
     ' - so the thickness carries information rather than being one value thirty times');
  /* COLOUR IS CLUSTER, as a partition: one colour per folder, one folder per colour. Either
     half failing is the same bug seen from a different side - a ring that told you about
     something other than which folder its note is in. */
  const byGroup = new Map(), byColour = new Map();
  rings.forEach((r) => {
    if (!byGroup.has(r.group)) byGroup.set(r.group, new Set());
    byGroup.get(r.group).add(r.colour);
    if (!byColour.has(r.colour)) byColour.set(r.colour, new Set());
    byColour.get(r.colour).add(r.group);
  });
  const split = [...byGroup].filter(([, cs]) => cs.size > 1);
  const shared = [...byColour].filter(([, gs]) => gs.size > 1);
  ok(split.length === 0 && shared.length === 0 && byColour.size === byGroup.size &&
     byColour.size > 1,
     'RING COLOUR IS CLUSTER: ' + byColour.size + ' colours across ' + byGroup.size +
     ' folders, each folder one colour and no colour in two folders',
     JSON.stringify({ splitFolders: split.map(([g]) => g), sharedColours: shared.map(([c]) => c) }));
  /* A JEWEL BY MEASUREMENT. "Desaturated jewel tone" is two numbers: the hue survives and
     the other two channels are pinned, so every ring is the same richness whatever the
     palette did. Converted here from the hex the material actually holds. */
  const hsl = (hex) => {
    const n = parseInt(hex.slice(1), 16);
    const r = ((n >> 16) & 255) / 255, g = ((n >> 8) & 255) / 255, b = (n & 255) / 255;
    const max = Math.max(r, g, b), min = Math.min(r, g, b), l = (max + min) / 2;
    const s = max === min ? 0 : (max - min) / (l > 0.5 ? 2 - max - min : max + min);
    return { s: s, l: l };
  };
  const stones = [...byColour.keys()].map((c) => Object.assign({ hex: c }, hsl(c)));
  const dull = stones.filter((c) => Math.abs(c.s - 0.55) > 0.02 || Math.abs(c.l - 0.47) > 0.02);
  ok(dull.length === 0,
     'AND EVERY ONE IS A DESATURATED JEWEL: ' + stones.map((c) => c.hex).join(' ') +
     ' - saturation and lightness pinned at 0.55/0.47, measured off the material',
     JSON.stringify(dull));
  ok(tiers.alpha > 0.4 && tiers.alpha < 1,
     'worn at ' + Math.round(tiers.alpha * 100) + '% - the one lit thing on a dark body, ' +
     'and still not opaque', JSON.stringify(tiers.alpha));
  ok(pl.spins > 0, 'and they are turning (' + pl.spins + ' spin frames so far)');

  /* THE SPIN STOPS WITH THE TAB. visibilityState is a read-only accessor, so it is
     redefined outright - the same trick the speech tests use - and then put back. */
  /* The counter is read INSIDE the same evaluate that installs the override, and that is
     not tidiness. Read in a call of its own, a frame gets between the reading and the lie:
     the tab turns once more while the round trip is in the air, the count comes back one
     higher than the "before" it is compared against, and the check fails by exactly one
     frame - 270 against 271 - having found nothing wrong with the page at all. Nothing can
     turn between two statements in the same expression. */
  const spinBefore = await page.evaluate(`(function(){
    var was = __galaxy.planets.spins;
    Object.defineProperty(document, 'visibilityState',
      { configurable: true, get: function(){ return 'hidden'; } });
    return was;
  })()`);
  await sleep(700);
  const hiddenRun = await page.json('({spins: __galaxy.planets.spins,' +
    ' skipped: __galaxy.planets.skipped})');
  await page.evaluate(`(function(){ delete document.visibilityState; return document.visibilityState; })()`);
  await sleep(300);
  const spinAfter = await page.evaluate('__galaxy.planets.spins');
  ok(hiddenRun.spins === spinBefore && hiddenRun.skipped > 10,
     'A HIDDEN TAB TURNS NOTHING: ' + hiddenRun.skipped + ' frames skipped and not one ' +
     'degree of rotation while the tab reported itself hidden',
     JSON.stringify({ before: spinBefore, during: hiddenRun.spins, skipped: hiddenRun.skipped }));
  ok(spinAfter > hiddenRun.spins,
     'and they start again when it comes back (' + spinAfter + ' > ' + hiddenRun.spins + ')');
  const buildsBeforeIdle = pl.builds;

  /* ---- 1c. THE BREATHING SKY -----------------------------------------------
     Every number is read off the force itself rather than off the source, because a
     literal in the page and a literal in the harness agreeing proves only that someone
     typed the same thing twice. The claim that matters is the last one: NOTHING TOUCHES.
     It is measured from live coordinates and real radii, after the layout has settled. */
  const sky = await page.json('({charge: __galaxy.sky.charge, distance: __galaxy.sky.distance,' +
    ' collide: __galaxy.sky.collide, pad: __galaxy.sky.pad, fog: __galaxy.sky.fog,' +
    ' starDim: __galaxy.sky.starDim, palette: __galaxy.sky.palette})');
  note('sky: ' + JSON.stringify(sky));
  ok(sky.charge <= -250,
     'the worlds push each other apart at ' + sky.charge + ', not -165',
     JSON.stringify(sky.charge));
  ok(!!sky.distance && sky.distance.mention >= 150 && sky.distance.wikilink > 100 &&
     sky.distance.shared > sky.distance.mention,
     'and the links are long now - ' + JSON.stringify(sky.distance) +
     ' - still three lengths, still shortest for a wikilink',
     JSON.stringify(sky.distance));
  ok(sky.collide === true && sky.pad >= 18,
     'and a collision force is installed with a ' + sky.pad + '-unit gap on top of each ' +
     'world’s own radius', JSON.stringify({ collide: sky.collide, pad: sky.pad }));
  /* Settled first: a collision force resolves overlap over a few hundred ticks, and a
     galaxy measured mid-explosion would be measured while it was still wrong. */
  await sleep(2500);
  const near = await page.json('__galaxy.sky.nearest');
  note('closest two worlds: ' + JSON.stringify(near));
  ok(!!near && near.gap > 0,
     'AND NOTHING TOUCHES: the closest two worlds in the galaxy are ' + (near ? near.gap : '?') +
     ' units apart at the surface - measured from live coordinates and real radii, not ' +
     'from the force’s promise', JSON.stringify(near));
  ok(!!sky.fog && sky.fog.density > 0,
     'the scene carries fog (density ' + (sky.fog ? sky.fog.density : 0) + ' in ' +
     (sky.fog ? sky.fog.colour : '?') + '), so distance reads as distance',
     JSON.stringify(sky.fog));
  /* ---- §31 PART 2: AND THE FOG IS CALIBRATED TO THE SKY, NOT TO A LITERAL ----
     WHY THREE MORE LINES ON A NUMBER THAT WAS ALREADY CHECKED. `density > 0` passed
     throughout the round in which the fog was erasing 99.9997% of every world on the deck:
     FogExp2 removes 1 - exp(-(density x distance)^2), the camera's distance follows the note
     count, and a squared exponential does not age gracefully. A positive density proves the
     depth cue exists; it says nothing about whether it is a depth cue or a blindfold.
     SO THE PRODUCT IS WHAT IS ASSERTED. k = density x the far side of the cloud is the whole
     behaviour in one number, and it has to stay in a band no matter how large the archive
     grows - which is exactly the claim that the density is being recomputed from the sky.
     Failure mode this catches, and it is the one that happened: someone leaves a literal
     density in place, the Scholar writes another hundred notes, the fit retreats, and the deck
     centre goes back to being an empty starfield with every harness still green. */
  ok(!!sky.fog && sky.fog.k >= 0.45 && sky.fog.k <= 0.85,
     'AND THE DEPTH CUE IS A DEPTH CUE: fog density x the far side of the cloud is ' +
     (sky.fog ? sky.fog.k : '?') + ', inside 0.45-0.85, so the worlds at the back of this ' +
     'galaxy are about a third of the way to the void and not erased into it - a claim about ' +
     'the PRODUCT, which is what FogExp2 actually acts on, and therefore true at any corpus ' +
     'size rather than at the one this was written against',
     JSON.stringify(sky.fog));
  ok(!!sky.fog && sky.fog.tunes > 0 && sky.fog.span && sky.fog.span[1] > sky.fog.span[0],
     'and it was RECOMPUTED ' + (sky.fog ? sky.fog.tunes : 0) + ' times against a cloud ' +
     'measured from ' + (sky.fog ? sky.fog.span.join(' to ') : '?') + ' units out, so the ' +
     'camera moving is enough to keep it honest', JSON.stringify(sky.fog));
  /* THE SAME CLAIM AS THE EYE MAKES, in the harness's own arithmetic: how much of a world at
     the middle of the cloud survives the fog. Half is the floor. At the density this replaced
     the answer was three parts in a million, which is the number that made the deck a
     starfield - so this is the assertion that would have failed then and passes now. */
  const fogKeep = sky.fog
    ? Math.exp(-Math.pow(sky.fog.density * (sky.fog.span[0] + sky.fog.span[1]) / 2, 2))
    : 0;
  ok(fogKeep >= 0.5,
     'and a world in the middle of the cloud keeps ' + Math.round(fogKeep * 100) +
     '% of its own light through that fog, where anything under half is a world the legend ' +
     'counts and the glass does not show',
     JSON.stringify({ keep: +fogKeep.toFixed(4), fog: sky.fog }));
  ok(sky.starDim <= 0.8,
     'the starfield is dimmed to ' + Math.round(sky.starDim * 100) + '% - a backdrop, ' +
     'not a subject', JSON.stringify(sky.starDim));
  /* DECANDIED, and checked by MEASUREMENT rather than by matching seven strings: what makes
     a pastel a sweet is that it is both very bright and very saturated. Every cluster
     colour has to sit under that ceiling. */
  const candy = sky.palette.filter((hex) => {
    const n = parseInt(hex.slice(1), 16);
    const r = (n >> 16) & 255, g = (n >> 8) & 255, b = n & 255;
    const max = Math.max(r, g, b), min = Math.min(r, g, b);
    return max > 224 && max - min > 120;
  });
  /* THE COUNT IS NOT SEVEN, IT IS ENOUGH. This read `palette.length === 7` until the
     corpus grew an eighth cluster - "unfiled", which is what build.py calls a note saved
     at the root of notes/ rather than inside a folder, so it arrives the first time the
     scribe writes a meeting without being told where to file it. Seven strings and eight
     clusters made COLOUR IS CLUSTER above fail by arithmetic: colorOf wraps on
     PALETTE.length, so the eighth folder shared steel blue with the first. The two checks
     could not both hold, and the one to give was this one, because a hardcoded 7 was never
     what it claimed to measure - its own comment says "by MEASUREMENT rather than by
     matching seven strings". So it now asserts the precondition the partition check
     silently depends on: at least one nameable colour per cluster on screen, and not one
     of them a sweet. Strictly stronger than the number it replaced. */
  ok(sky.palette.length >= byGroup.size && sky.palette.length >= 7 && candy.length === 0,
     'the palette carries ' + sky.palette.length + ' jewels for ' + byGroup.size +
     ' clusters - a nameable colour each, and not one of them a boiled sweet: ' +
     sky.palette.join(' '),
     JSON.stringify({ candy: candy, clusters: byGroup.size }));

  /* ---- 1c-2. THE DEEP FIELD ------------------------------------------------
     THE DEEP FIELD asks for four things, and three of them are the kind of claim that
     looks identical whether it was built or merely declared. So none of them is read off a
     constant.
     THE NEBULA is asked of the computed background: how many radial stops, and the loudest
     alpha among them. Six per cent is the ceiling in the specification and it is read out
     of the cascade, because a stylesheet is where this one can go wrong.
     THE THREE LAYERS are proved by MOVING THE MOUSE. Three shells with three weights in a
     table is a table; three shells that travel three different distances when a real
     pointer crosses the window is parallax. The near band must move strictly further than
     the middle, and the middle strictly further than the far - which is the only ordering
     that reads as depth, and the one that inverts if the weights are ever transposed.
     THE SUN is asked to be the SAME DIRECTION as the key light, component by component.
     That is the whole claim of the feature: the light on the worlds and the light in the
     sky are one fact. Then it is asked to have moved - `moves` counts the frames on which
     its transform was actually rewritten, so a glow painted at one spot for ever fails
     here even though it would photograph correctly.
     AND WHAT IT MUST NOT BE: the flare covers the whole window and lies over the graph, so
     a single pointer-events slip would make the galaxy unclickable. Measured, not assumed. */
  const field = await page.json('(function(){' +
    'var nb=document.getElementById("nebula"),gr=document.getElementById("grain"),' +
    'sg=document.getElementById("sunglow");' +
    'var cs=getComputedStyle(nb);var m=cs.backgroundImage.match(/rgba?\\([^)]*\\)/g)||[];' +
    'var a=m.map(function(s){var p=s.replace(/rgba?\\(|\\)/g,"").split(",");' +
    'return p.length>3?parseFloat(p[3]):1;});' +
    'var stops=(cs.backgroundImage.match(/radial-gradient/g)||[]).length;' +
    'var sgc=getComputedStyle(sg);' +
    'return {stops:stops,alpha:Math.max.apply(null,a.concat([0])),blur:cs.filter,' +
    'grain:+getComputedStyle(gr).opacity,grainTile:/url\\(/.test(getComputedStyle(gr).backgroundImage),' +
    'sunEvents:sgc.pointerEvents,sunZ:sgc.zIndex,' +
    'sunKids:sg.querySelectorAll("i").length};})()');
  note('deep field: ' + JSON.stringify(field));
  ok(field.stops >= 2 && field.stops <= 3 && field.alpha <= 0.06,
     'THE NEBULA is ' + field.stops + ' radial gradients and the loudest of them is ' +
     Math.round(field.alpha * 1000) / 10 + '% - at or under the six per cent ceiling, so ' +
     'nothing in the frame gives up contrast for it', JSON.stringify(field));
  ok(field.grain > 0 && field.grain <= 0.04 && field.grainTile === true,
     'and the film grain is still over it at ' + Math.round(field.grain * 1000) / 10 +
     '%, a tile rather than a request', JSON.stringify(field));
  ok(field.sunEvents === 'none' && field.sunKids === 2,
     'the sun’s flare is deaf to the pointer (z-index ' + field.sunZ + ', ' +
     field.sunKids + ' parts) - it covers the graph, so a click must go straight through it',
     JSON.stringify(field));

  /* The pointer, hard left and then hard right, with time for the 180ms ease to finish
     either side. A synthetic pointermove through the browser rather than a call into the
     page: the parallax listens to the event, and what is being proved is that the event
     reaches the sky. */
  const window_ = await page.json('({w: innerWidth, h: innerHeight})');
  const leanTo = async (x) => {
    await page.send('Input.dispatchMouseEvent',
                    { type: 'mouseMoved', x, y: Math.round(window_.h / 2), buttons: 0 });
    await sleep(1100);          // 180ms tau, and then some: the ease must be finished
    return page.json('({p: __galaxy.deck.pointer, L: __galaxy.deck.layers,' +
                     ' sun: __galaxy.deck.sun})');
  };
  const swept = { left: await leanTo(40), right: await leanTo(window_.w - 40) };
  const swing = (swept.left.L || []).map((L, i) => {
    const r = swept.right.L[i];
    return +Math.hypot(r.at[0] - L.at[0], r.at[1] - L.at[1],
                       r.at[2] - L.at[2]).toFixed(2);
  });
  note('star layers: ' + JSON.stringify((swept.right.L || []).map(
    (L) => ({ stars: L.stars, r: L.r, par: L.par }))));
  note('pointer ' + JSON.stringify(swept.left.p) + ' -> ' +
       JSON.stringify(swept.right.p) + ', swing ' + JSON.stringify(swing));
  ok((swept.right.L || []).length === 3,
     'THREE STAR LAYERS in the deep field, not one shell with a range of radii inside it',
     JSON.stringify((swept.right.L || []).length));
  ok(swing.length === 3 && swing[2] > swing[1] && swing[1] > swing[0] && swing[0] > 0,
     'AND THEY PARALLAX: a real pointer crossing the window swings them ' +
     swing.join(' / ') + ' units - near further than middle, middle further than far, ' +
     'which is the ordering the eye reads as distance', JSON.stringify(swing));
  ok(Math.abs(swept.left.p[0]) > 0.5 && swept.right.p[0] > 0.5 &&
     swept.left.p[0] < 0,
     'driven by the parallax’s OWN eased pointer (' + swept.left.p[0] + ' -> ' +
     swept.right.p[0] + '), so the sky and the camera lean on one number',
     JSON.stringify([swept.left.p, swept.right.p]));
  const sun = swept.right.sun;
  ok(!!sun && !!lights && JSON.stringify(sun.dir) === JSON.stringify(lights.dir),
     'THE DISTANT SUN IS THE KEY LIGHT: ' + JSON.stringify(sun && sun.dir) +
     ' is the same direction the worlds are lit from, component for component - one claim ' +
     'and not two', JSON.stringify({ sun: sun && sun.dir, key: lights && lights.dir }));
  ok(!!sun && sun.lit === true && sun.moves > 1,
     'and it is projected every frame rather than painted on: the flare has been rewritten ' +
     (sun ? sun.moves : 0) + ' times and sits at ' + JSON.stringify(sun && sun.at) +
     (sun && sun.grazing
       ? ' - GRAZING, because the key is off frame at this angle, so the disc is suppressed ' +
         'and only the veil is drawn'
       : ' - with the disc in frame'),
     JSON.stringify(sun));

  /* ---- 1d. THE SILENT WIRES ------------------------------------------------
     A connection exists only as its travelling dot: one per link, tinted from the source,
     and NO LINE at any opacity in any view. The "one system" claim is the one that protects
     the frame rate, so it is asked of the SCENE - how many Points objects are in it besides
     the starfield - rather than of the code; and the "no lines" claim is asked of the
     library, because a transparent line is still a line the renderer builds and sorts. */
  const flow = await page.json('({on: __galaxy.flow.on, why: __galaxy.flow.why,' +
    ' links: __galaxy.flow.links, dots: __galaxy.flow.dots, perLink: __galaxy.flow.perLink,' +
    ' objects: __galaxy.flow.objects, size: __galaxy.flow.size, tint: __galaxy.flow.tint,' +
    ' alpha: __galaxy.flow.alpha, hotAlpha: __galaxy.flow.hotAlpha,' +
    ' hotSpeed: __galaxy.flow.hotSpeed, dim: __galaxy.flow.dim,' +
    ' lineObjects: __galaxy.flow.lineObjects, vis: __galaxy.flow.linkVisibility,' +
    ' frames: __galaxy.flow.frames, active: __galaxy.active.length,' +
    ' all: __galaxy.allLinks.length, strong: __galaxy.strongLinks.length})');
  note('flow: ' + JSON.stringify(flow));
  ok(flow.on === true, 'the travelling dots are running', JSON.stringify(flow.why));
  ok(flow.lineObjects === 0 && flow.vis === false,
     'THE SILENT WIRES: not one Line object in the whole scene, and the library is told ' +
     'so rather than handed a transparent colour',
     JSON.stringify({ lineObjects: flow.lineObjects, linkVisibility: flow.vis }));
  ok(flow.links === flow.active && flow.dots === flow.active * 1 && flow.perLink === 1,
     'ONE DOT PER RELATION: ' + flow.dots + ' dots for ' + flow.active + ' links',
     JSON.stringify(flow));
  ok(flow.objects === 1,
     'AND THEY ARE ONE OBJECT: the scene holds exactly one Points system for all ' +
     flow.dots + ' of them, which is why the frame rate below survives them',
     JSON.stringify({ objects: flow.objects }));
  ok(Math.abs(flow.size - 1.2) < 0.01 && Math.abs(flow.tint - 0.6) < 0.01,
     'size ' + flow.size + ', tinted to ' + Math.round(flow.tint * 100) +
     '% of the source colour, as specified');
  ok(Math.abs(flow.alpha - 0.35) < 1e-9 && Math.abs(flow.hotAlpha - 0.8) < 1e-9 &&
     Math.abs(flow.hotSpeed - 1.3) < 1e-9,
     'at rest ' + flow.alpha + ', touched ' + flow.hotAlpha + ', and only ' +
     Math.round((flow.hotSpeed - 1) * 100) + '% faster when touched',
     JSON.stringify(flow));
  /* SIMPLIFY ON LOAD, which is a claim about what you see before you click anything: the
     strongest links only, with the other hundred-odd a toggle away for the curious. */
  ok(flow.active === flow.strong && flow.strong < flow.all,
     'THE VIEW ON LOAD IS SIMPLIFY: ' + flow.strong + ' of the ' + flow.all +
     ' relations, the rest behind the header toggle',
     JSON.stringify({ active: flow.active, strong: flow.strong, all: flow.all }));
  /* TRAVELLING, not merely present: one dot's position is read twice, a moment apart, out
     of the live buffer - and its distance along the link has to have moved. */
  const dotA = await page.json('__galaxy.flow.sampleAt(0)');
  await sleep(400);
  const dotB = await page.json('__galaxy.flow.sampleAt(0)');
  const moved = dotA && dotB ? Math.hypot(dotB[0] - dotA[0], dotB[1] - dotA[1], dotB[2] - dotA[2]) : 0;
  note('one dot, 400ms apart: ' + JSON.stringify(dotA) + ' -> ' + JSON.stringify(dotB));
  ok(moved > 0.5 && dotA[3] !== dotB[3],
     'AND THEY TRAVEL: one dot moved ' + moved.toFixed(2) + ' units along its link in ' +
     '400ms, read out of the position buffer itself',
     JSON.stringify({ from: dotA, to: dotB }));
  const framesLater = await page.evaluate('__galaxy.flow.frames');
  ok(framesLater > flow.frames,
     'and the whole system is being written every frame (' + flow.frames + ' -> ' +
     framesLater + ')');
  /* THE TINT IS THE SOURCE'S COLOUR, at six tenths OF THE RESTING ALPHA - checked against
     the source node's own cluster colour, recomputed in Node from the palette rather than
     asked of the page. The alpha is in the colour and not in the material because a
     PointsMaterial has one opacity for the whole cloud and this spec asks for two; under
     additive blending a dot's contribution is colour x opacity, so folding 0.35 into the
     buffer and leaving the material at 1 is the same arithmetic with per-dot control. That
     is why what is expected here is 0.6 x 0.35 and not 0.6. */
  const tintCheck = await page.json(`(function(){
    var l = __galaxy.active[0];
    var sid = typeof l.source === 'object' ? l.source.id : l.source;
    var src = __galaxy.nodes.filter(function(n){ return n.id === sid; })[0];
    return { hex: __galaxy.colorOf[src.group], dot: __galaxy.flow.colourAt(0),
             alpha: __galaxy.flow.alphaAt(0) };
  })()`);
  const wantRgb = (() => {
    const n = parseInt(String(tintCheck.hex).slice(1), 16);
    return [((n >> 16) & 255) / 255, ((n >> 8) & 255) / 255, (n & 255) / 255]
      .map((v) => v * 0.6 * 0.35);
  })();
  const tintErr = Math.max(...wantRgb.map((v, i) => Math.abs(v - tintCheck.dot[i])));
  ok(tintErr < 0.01,
     'and the first dot is 60% of its source cluster’s colour at 0.35 opacity (' +
     tintCheck.hex + ' → ' + JSON.stringify(tintCheck.dot) + ')',
     JSON.stringify({ want: wantRgb, got: tintCheck.dot }));
  ok(Math.abs(tintCheck.alpha - 0.6 * 0.35) < 0.002,
     'which the buffer itself reads back as tint x alpha = ' + tintCheck.alpha,
     JSON.stringify({ want: 0.6 * 0.35, got: tintCheck.alpha }));

  /* THE MIND SHOWS THE CONNECTIONS YOU ARE TOUCHING. Hover one planet and its own synapses
     go to 0.8 while every other one drops to a texture. Driven through the library's own
     onNodeHover callback, because a pointer cannot be put on a sphere in a WebGL canvas
     without reimplementing the projection - and a test that did that would be proving the
     projection maths rather than this rule. Read back out of the colour buffer, per dot,
     which is the only place the answer actually lives. */
  const hoverCheck = await page.json(`(function(){
    var idOf = function (e) { return typeof e === 'object' ? e.id : e; };
    var links = __galaxy.active;
    /* The busiest node, so that "its own" and "every other" are both non-empty - hovering a
       leaf with one synapse would make the second half of the claim a sample of one. */
    var count = {}, best = null;
    links.forEach(function (l) {
      [idOf(l.source), idOf(l.target)].forEach(function (id) {
        count[id] = (count[id] || 0) + 1;
        if (best === null || count[id] > count[best]) best = id;
      });
    });
    var mine = [], theirs = [];
    links.forEach(function (l, i) {
      (idOf(l.source) === +best || idOf(l.target) === +best ? mine : theirs).push(i);
    });
    var read = function (list) { return list.map(function (i) { return __galaxy.flow.alphaAt(i); }); };
    var rest = { mine: read(mine), theirs: read(theirs) };
    var hov = __galaxy.hover(+best);
    var hot = { mine: read(mine), theirs: read(theirs) };
    __galaxy.hover(null);
    var off = { mine: read(mine), theirs: read(theirs) };
    var node = __galaxy.nodes.filter(function (n) { return n.id === +best; })[0];
    return { id: +best, label: node && node.label, hov: hov,
             n: { mine: mine.length, theirs: theirs.length },
             rest: rest, hot: hot, off: off };
  })()`);
  const spread = (a) => (a.length ? [Math.min(...a), Math.max(...a)] : [null, null]);
  note('hovered "' + hoverCheck.label + '": ' + hoverCheck.n.mine + ' of its own synapses, ' +
       hoverCheck.n.theirs + ' others  ·  own ' + JSON.stringify(spread(hoverCheck.hot.mine)) +
       '  ·  others ' + JSON.stringify(spread(hoverCheck.hot.theirs)));
  ok(hoverCheck.n.mine > 1 && hoverCheck.n.theirs > 1 && hoverCheck.hov.hot === hoverCheck.n.mine,
     'hovering "' + hoverCheck.label + '" lit exactly its own ' + hoverCheck.n.mine +
     ' synapses and left ' + hoverCheck.n.theirs + ' others to compare against',
     JSON.stringify(hoverCheck.hov));
  ok(hoverCheck.hot.mine.every((a) => Math.abs(a - 0.6 * 0.8) < 0.002),
     'ONLY ITS OWN BRIGHTEN: every one of its ' + hoverCheck.n.mine +
     ' dots is at 0.8, read out of the buffer',
     JSON.stringify(spread(hoverCheck.hot.mine)));
  ok(hoverCheck.hot.theirs.every((a) => a < 0.6 * 0.35 * 0.9),
     'AND THE REST HIDE: every other dot is dimmer than its own resting alpha - present ' +
     'as texture, gone as information',
     JSON.stringify(spread(hoverCheck.hot.theirs)));
  ok(hoverCheck.rest.mine.concat(hoverCheck.rest.theirs)
       .every((a) => Math.abs(a - 0.6 * 0.35) < 0.002) &&
     hoverCheck.off.mine.concat(hoverCheck.off.theirs)
       .every((a) => Math.abs(a - 0.6 * 0.35) < 0.002),
     'and the pointer leaving puts all ' + (hoverCheck.n.mine + hoverCheck.n.theirs) +
     ' of them back to one resting alpha, as they were before it arrived',
     JSON.stringify({ before: spread(hoverCheck.rest.mine.concat(hoverCheck.rest.theirs)),
                      after: spread(hoverCheck.off.mine.concat(hoverCheck.off.theirs)) }));

  /* ---- 1e. WHAT IS NO LONGER IN THE ROOM ----------------------------------
     TWO DELETIONS, ASSERTED AS ABSENCES. The smiley's bar-eyes and bar-mouth are gone and
     the visage is a gyroscopic lens; the standing chat box is gone and the type-line is
     summoned. Both are checked by counting the things that would still be there if the
     work had been half done - a feature that was added on top of what it replaced looks
     identical in a screenshot and fails here. */
  /* The smiley's own class names, counted across the WHOLE document rather than inside the
     visage - a bar-mouth left behind in the Command Panel's small Mind is the same defect.
     face.bars is not this number: it is the waveform ring's spoke count, which is a Mind
     part and is asserted as a presence below. */
  const gone = await page.json('({ghosts: document.querySelectorAll(' +
    '".feye,.feyes,.fmouth,.fbarm,.fring,.fscan").length,' +
    ' lens: document.querySelectorAll(".mlens").length,' +
    ' iris: document.querySelectorAll(".miris").length,' +
    ' gimbals: document.querySelectorAll("#focusface .mgimbal").length,' +
    ' spokes: __galaxy.face.bars, homes: __galaxy.face.homes,' +
    ' states: __galaxy.face.states,' +
    ' input: __galaxy.typeLine.persistentInput})');
  ok(gone.ghosts === 0,
     'THE SMILEY IS GONE: not one bar-eye, bar-mouth or scan line left anywhere in the ' +
     'document', JSON.stringify(gone));
  ok(gone.lens >= 1 && gone.iris >= 1 && gone.gimbals === 3 && gone.spokes > 0,
     'and what stands in its place is the Mind: an optical lens with an iris, ' +
     gone.gimbals + ' gimbal rings and a ' + gone.spokes + '-spoke waveform ring',
     JSON.stringify(gone));
  ok(gone.input.q === false && gone.input.send === false &&
     gone.input.textareas === 0 && gone.input.barInputs === 0,
     'THE PERSISTENT TEXTAREA IS GONE: no #q, no #send, no textarea anywhere, and no ' +
     'standing field in the bottom bar', JSON.stringify(gone.input));

  /* ---- 2. FIVE SECONDS OF IDLE SKY, WITH THE EAR OPEN -------------------- */
  await sleep(1800);                       // let the boot overlay finish and the layout settle
  /* THE OPEN EAR IS PART OF THE IDLE PAGE NOW, so it is part of what the floor is measured
     against: a live microphone stream, an AnalyserNode and an RMS every frame, on top of
     the worlds, the textures, the nebula and the bloom. Opened before the recording is
     armed and closed after it is read, so the number below is the page as he will sit in
     front of it rather than a quieter version of it. */
  const earUp = JSON.parse(await page.evaluate(
    '__galaxy.ear.raise().then(function (r) { return JSON.stringify(r); })') || 'null') || {};
  ok(earUp.open === true && earUp.stream === true && earUp.analyser === true,
     'THE OPEN EAR IS UP for the measurement: one click, a live stream and an analyser on it',
     JSON.stringify(earUp));
  note('the ear reports its engine as "' + earUp.engine + '" - and it says so on the seal');
  await page.evaluate(`(function(){
    window.__fps = { deltas: [], run: true };
    var last = performance.now();
    (function step(now){
      if (!window.__fps.run) return;
      var d = now - last; last = now;
      if (d > 0) window.__fps.deltas.push(d);
      requestAnimationFrame(step);
    })(last);
    return 'armed';
  })()`);
  note('recording ' + (IDLE_MS / 1000) + 's of the idle sky, hands off\u2026');
  const castsBefore = page.casts;
  await sleep(IDLE_MS);
  note('the compositor sent ' + (page.casts - castsBefore) + ' pictures during the recording' +
       (HEADED ? ' - if this is zero the window is not being drawn and nothing below is ' +
                 'about the page' : ''));
  ok(page.errors.length === 0,
     'AND THE PAGE THREW NOTHING while it was being watched - an exception inside the tick ' +
     'stops the tick, and every number below would then be measuring a dead loop',
     page.errors.slice(0, 4).join('\n         '));
  await page.evaluate('window.__fps.run = false');
  const deltas = (await page.json('window.__fps.deltas')) || [];
  const total = deltas.reduce((a, b) => a + b, 0);
  const mean = deltas.length ? (deltas.length / (total / 1000)) : 0;
  const sorted = deltas.slice().sort((a, b) => a - b);
  const p95 = sorted[Math.floor(sorted.length * 0.95)] || 0;
  const worst = sorted[sorted.length - 1] || 0;
  const slow = deltas.filter((d) => d > 20).length;
  const pageFps = await page.evaluate('__galaxy.deck.fps');
  note('frames ' + deltas.length + ' in ' + Math.round(total) + 'ms  \u00b7  mean ' +
       mean.toFixed(1) + 'fps  \u00b7  p95 ' + p95.toFixed(1) + 'ms  \u00b7  worst ' +
       worst.toFixed(1) + 'ms  \u00b7  over 20ms: ' + slow + '/' + deltas.length);
  ok(deltas.length > 100, 'the page was actually animating during the recording (' +
     deltas.length + ' frames)');
  ok(mean >= FPS_FLOOR, 'IDLE GALAXY HOLDS ' + mean.toFixed(1) + 'fps over ' +
     (IDLE_MS / 1000) + 's, above the ' + FPS_FLOOR + 'fps floor',
     'mean ' + mean.toFixed(1) + 'fps on ' + gpu);
  ok(p95 <= 20.5, 'and it holds it CONSISTENTLY: 95% of frames under 20ms (' +
     p95.toFixed(1) + 'ms)', 'p95 ' + p95.toFixed(1) + 'ms, worst ' + worst.toFixed(1) + 'ms');
  ok(Math.abs(pageFps - mean) < 12,
     'the page\u2019s own monitor agrees with this measurement (' + pageFps + ' vs ' +
     mean.toFixed(1) + 'fps), so the guard below is watching the real frame rate',
     JSON.stringify({ page: pageFps, harness: +mean.toFixed(1) }));

  /* THE PERFORMANCE LAW, MEASURED. Five seconds and three hundred frames later, not one
     more world and not one more canvas than at boot. This is the check that would catch a
     texture being rebuilt per frame - the one mistake in this feature that a screenshot
     would look perfect through while the frame rate quietly died. */
  const afterIdle = await page.json('({builds: __galaxy.planets.builds,' +
    ' textures: __galaxy.planets.textures, paints: __galaxy.planets.paints,' +
    ' spins: __galaxy.planets.spins})');
  ok(afterIdle.builds === buildsBeforeIdle && afterIdle.textures === pl.textures,
     'TEXTURES ARE BUILT ONCE: ' + afterIdle.builds + ' builds and ' + afterIdle.textures +
     ' canvases before the recording and the same after ' + deltas.length + ' frames',
     JSON.stringify({ before: buildsBeforeIdle, after: afterIdle.builds }));
  /* The PLANETS' axial spin, which is not the camera and never was: a world turning on its
     own axis is motion inside the frame, and THE LAW OF ALIVENESS keeps it. What SCOPE A
     retired is the camera, and that is section 2b. */
  ok(afterIdle.spins >= deltas.length * 0.8,
     'and the worlds really are turning on their own axes, per frame (' + afterIdle.spins +
     ' spin frames against ' + deltas.length + ' recorded)',
     JSON.stringify(afterIdle));

  /* AND THE EAR WAS OPEN THE WHOLE TIME. Read after the recording rather than before, so
     the claim is "the frame rate above was measured with a live microphone on the page" and
     not "a microphone was opened at some point near it". The seal is read from the same
     instant, because the transparency law does not get a holiday during a benchmark. */
  const earIdle = await page.json('({open: __galaxy.ear.open, opened: __galaxy.ear.opened,' +
    ' frames: __galaxy.ear.frames, analyser: __galaxy.ear.analyser,' +
    ' stream: __galaxy.ear.stream, engine: __galaxy.ear.engine,' +
    ' seal: __galaxy.ear.seal, dot: __galaxy.ear.dot})');
  ok(earIdle.open === true && earIdle.analyser === true,
     'and THE EAR WAS STILL OPEN at the end of the recording - the ' + mean.toFixed(1) +
     'fps above is the page with a live microphone on it', JSON.stringify(earIdle));
  ok(earIdle.frames >= deltas.length * 0.5,
     'the analyser really was reading the room every frame (' + earIdle.frames +
     ' RMS frames against ' + deltas.length + ' recorded)', JSON.stringify(earIdle));
  ok(earIdle.seal && earIdle.seal.open === true && earIdle.seal.shown === true &&
     /ear open/i.test(earIdle.seal.cell) && earIdle.seal.cell.indexOf(earIdle.engine) >= 0,
     'THE SEAL SAYS SO, all the way through: "' + (earIdle.seal || {}).cell +
     '" - open, visible, and naming the engine', JSON.stringify(earIdle.seal));
  ok(earIdle.dot && earIdle.dot.ear === true,
     'and the organ-rail mic wears .ear for every second the stream is live',
     JSON.stringify(earIdle.dot));
  await page.evaluate('__galaxy.ear.close("the deck proof", "")');
  await sleep(500);
  ok((await page.evaluate('__galaxy.ear.open')) === false &&
     (await page.evaluate('__galaxy.ear.stream')) === false,
     'and it closes again, stream and all - nothing is left listening behind the proof');

  /* ---- 2b. THE CALM SKY: THIRTY SECONDS, AND YOUR HEAD DOES NOT MOVE -----
     The rule is that nothing moves the camera unless a hand does. That is not provable by
     sampling a position twice - a slow orbit sampled at the wrong two moments reads as
     still - so what is watched is the camera's QUATERNION, which is the whole answer to
     "did the viewer's head move", together with the page's own count of the frames on which
     the parallax decided NOT to touch the camera. holds climbing while moves stands still
     is a stronger statement than any pair of samples: it says the code reached the decision
     point six hundred times and declined every time.
     The give is proved first, because "the camera never moves" is trivially true of a dead
     feature. The pointer is moved to a corner through the parallax's own input - the camera
     leans, by no more than the 2.5 degrees the spec allows - and THEN the pointer is held
     still for thirty seconds. */
  /* THE SECTION STARTS FROM A KNOWN SKY. Everything in it - the give, the clamp, the
     stillness - is read off a camera with nothing selected, because an open panel suspends
     the parallax by design and the first check would then fail for the right reason at the
     wrong time. The panel is closed through its own close button, called rather than
     clicked, so this works with input already switched off. */
  await page.evaluate(`(function(){
    var c = document.getElementById('close');
    if (c && document.getElementById('panel').classList.contains('open')) c.click();
    return document.getElementById('panel').classList.contains('open');
  })()`);
  await sleep(500);
  const calm0 = await page.json('({spin: __galaxy.camera.spin, quat: __galaxy.camera.quat,' +
    ' par: __galaxy.camera.parallax, target: __galaxy.camera.target,' +
    ' flights: __galaxy.camera.flights})');
  note('calm sky: ' + JSON.stringify(calm0));
  ok(calm0.spin === false,
     'THE GALAXY RESTS BY DEFAULT: no auto-rotation, and config.json did not ask for any',
     JSON.stringify({ spin: calm0.spin, why: calm0.par.why }));
  ok(calm0.par.on === true && Math.abs(calm0.par.maxDeg - 2.5) < 0.01,
     'the pointer parallax is armed and clamped to ' + calm0.par.maxDeg + ' degrees',
     JSON.stringify(calm0.par));
  /* THE GIVE. Pointer to the far corner, then long enough for a 180ms ease to arrive. */
  ok(await page.evaluate('__galaxy.camera.look(1, 1)') === true,
     'the pointer is taken to the corner of the window');
  await sleep(1500);
  const leaned = await page.json('({quat: __galaxy.camera.quat, par: __galaxy.camera.parallax,' +
    ' target: __galaxy.camera.target})');
  const qMoved = (a, b) => Math.max(...a.map((v, i) => Math.abs(v - b[i])));
  note('leaned: yaw ' + leaned.par.yawDeg + '° pitch ' + leaned.par.pitchDeg + '° · ' +
       leaned.par.moves + ' moves, ' + leaned.par.holds + ' holds');
  ok(leaned.par.moves > 5 && qMoved(calm0.quat, leaned.quat) > 0.0005,
     'AND THERE IS GIVE: the camera leaned toward it over ' + leaned.par.moves +
     ' frames (quaternion moved by ' + qMoved(calm0.quat, leaned.quat).toFixed(5) + ')',
     JSON.stringify({ from: calm0.quat, to: leaned.quat, par: leaned.par }));
  ok(Math.abs(leaned.par.yawDeg) <= 2.51 && Math.abs(leaned.par.pitchDeg) <= 2.51,
     'and it leaned by no more than the clamp allows: ' + leaned.par.yawDeg + '° yaw, ' +
     leaned.par.pitchDeg + '° pitch',
     JSON.stringify(leaned.par));
  /* AND NOW THE THIRTY SECONDS, in a real window on a real desktop, which is the one
     uncomfortable fact about this check. If a hand moves the mouse over the canvas while
     this is running, 3d-force-graph's onNodeClick flies the camera to a note and the hold
     below fails - a true report of the camera and a false report of the sky. That happened:
     nine flights in thirty idle seconds, every one of them stamped `onNodeClick`.
     The obvious fix was to have the browser ignore input events for the duration, and it is
     the wrong fix: Input.setIgnoreInputEvents stops the compositor for the target as well,
     so the frames stop, the parallax stops counting, and the hold then passes because the
     page is dead rather than because the sky is calm. A check that cannot fail is worse
     than one that fails honestly. So input is left alone and the page's own flight log is
     read instead: if the camera did move, the assertion names the caller that moved it, and
     a click from the desktop says so in as many words. */
  note('holding the pointer still for ' + (CALM_MS / 1000) + 's - hands off the mouse; the ' +
       'quaternion must not move by one digit…');
  const heldFrom = await page.json('({quat: __galaxy.camera.quat, pos: __galaxy.camera.pos,' +
    ' par: __galaxy.camera.parallax, target: __galaxy.camera.target,' +
    ' flights: __galaxy.camera.flights})');
  /* THE SAME THIRTY SECONDS PAY FOR A SECOND LAW. The camera is one half of "the sky does
     not wander"; the galaxy ROOT is the other, and a drifting root is invisible in the
     camera numbers because it moves the whole world under a perfectly still head. Read
     here and again below off the same hold rather than in a section of its own - a second
     thirty-second idle window would double the harness's running time to assert the same
     thing about the same quiet page. */
  const stillFrom = await page.json('__galaxy.deck.still');
  await sleep(CALM_MS);
  const heldTo = await page.json('({quat: __galaxy.camera.quat, pos: __galaxy.camera.pos,' +
    ' par: __galaxy.camera.parallax, target: __galaxy.camera.target,' +
    ' flights: __galaxy.camera.flights})');
  const stillTo = await page.json('__galaxy.deck.still');
  note('after ' + (CALM_MS / 1000) + 's: quat ' + JSON.stringify(heldTo.quat) + ' · ' +
       (heldTo.par.moves - heldFrom.par.moves) + ' moves, ' +
       (heldTo.par.holds - heldFrom.par.holds) + ' holds');
  ok(JSON.stringify(heldFrom.quat) === JSON.stringify(heldTo.quat),
     'THIRTY SECONDS OF STILLNESS: the camera quaternion is unchanged to four decimals',
     JSON.stringify({ before: heldFrom.quat, after: heldTo.quat }));
  ok(JSON.stringify(heldFrom.pos) === JSON.stringify(heldTo.pos),
     'and so is its position: ' + JSON.stringify(heldTo.pos),
     JSON.stringify({ before: heldFrom.pos, after: heldTo.pos }));
  ok(heldTo.par.moves === heldFrom.par.moves &&
     heldTo.par.holds - heldFrom.par.holds > 300,
     'and it was a DECISION, not an absence: the parallax reached the camera ' +
     (heldTo.par.holds - heldFrom.par.holds) + ' times in those ' + (CALM_MS / 1000) +
     's and declined every one of them',
     JSON.stringify({ moves: [heldFrom.par.moves, heldTo.par.moves],
                      holds: [heldFrom.par.holds, heldTo.par.holds] }));
  /* The page keeps the stack of every flight, so if one happened unbidden this reads out
     the code that asked for it rather than leaving "the camera moved" to be guessed at. */
  const flog = (await page.json('__galaxy.camera.flightLog')) || [];
  const clicked = flog.some((f) => /onNodeClick|onClick/.test(String(f.by)));
  ok(heldTo.flights === heldFrom.flights && heldTo.flights === calm0.flights,
     'and nothing flew anywhere: ' + heldTo.flights + ' flights, the same as before' +
     (heldTo.flights === heldFrom.flights ? '' : clicked
       ? ' - BUT THE LOG SAYS onNodeClick: a hand touched the canvas during the hold, so ' +
         'this run cannot speak for the calm sky. Run it again without using the mouse.'
       : ' - and NOT from a click: the page flew itself, which is the violation'),
     JSON.stringify({ calm0: calm0.flights, from: heldFrom.flights, to: heldTo.flights,
                      log: flog }));
  /* ---- 2b-2. THE STILL FRAME: THE GALAXY ROOT DOES NOT GO ANYWHERE -------
     A LAW ABOUT THE OTHER HALF OF THE PICTURE. The camera being still is not the same
     statement as the sky being still: translate the root group by a hand's width and every
     camera number above is unchanged while the whole galaxy slides off the reserved side of
     the screen. So the root's position and orientation are pinned for the life of the page,
     and the page measures its own deviation before correcting it - dPos and dQuat are
     running MAXIMA, not samples, which is why one read after thirty idle seconds is a
     stronger claim than two reads thirty seconds apart.
     AND THE SKY MUST NOT BE FROZEN TO PASS. A dead scene satisfies "the root did not move"
     perfectly, so the same two reads are used the other way round: the worlds' own axial
     rotations and micro-orbit positions must have MOVED across the hold. Still, not dead. */
  note('still frame: ' + stillTo.kind + ' "' + stillTo.name + '" pinned at ' +
       JSON.stringify(stillTo.at) + ' · dPos ' + stillTo.dPos + ' · dQuat ' + stillTo.dQuat +
       ' · ' + stillTo.holds + ' holds, ' + stillTo.corrections + ' corrections');
  ok(stillTo.found === true && stillTo.pinned === true && !stillTo.trouble,
     'THE GALAXY ROOT IS IDENTIFIED AND PINNED: the ' + stillTo.kind + ' named "' +
     stillTo.name + '" - if this cannot be found there is nothing holding the sky in place',
     JSON.stringify(stillTo).slice(0, 400));
  ok(stillTo.dPos === 0,
     'AND OVER ' + (CALM_MS / 1000) + 's OF IDLE IT NEVER TRANSLATED: the largest position ' +
     'deviation the page has ever measured on the root is ' + stillTo.dPos,
     JSON.stringify({ dPos: stillTo.dPos, at: stillTo.at,
                      before: stillFrom.dPos, after: stillTo.dPos }));
  ok(stillTo.dQuat === 0,
     'and it never turned either: largest quaternion deviation ' + stillTo.dQuat + ' - the ' +
     'root holds ' + JSON.stringify(stillTo.quat) + ' for the life of the page',
     JSON.stringify({ dQuat: stillTo.dQuat, quat: stillTo.quat,
                      before: stillFrom.dQuat, after: stillTo.dQuat }));
  ok(stillTo.corrections === 0,
     'and the pin never had to FIGHT anyone for it: ' + stillTo.corrections +
     ' corrections, so nothing in the page is writing to the root behind its back',
     JSON.stringify({ corrections: stillTo.corrections, dPos: stillTo.dPos }));
  ok(stillTo.holds - stillFrom.holds > 300,
     'and the watch was AWAKE for the hold: the pin checked the root ' +
     (stillTo.holds - stillFrom.holds) + ' times in those ' + (CALM_MS / 1000) +
     's - a sleeping watch would report a deviation of zero too',
     JSON.stringify({ holds: [stillFrom.holds, stillTo.holds] }));
  /* The two halves of "still, not frozen", counted world by world across the same hold.
     The bar is four fifths rather than all of them because a world whose drift period
     happens to fold back on itself over exactly these thirty seconds would read as
     stationary for an honest reason. */
  const spinN = Math.min(stillFrom.spins.length, stillTo.spins.length);
  const turning = stillFrom.spins.filter((v, i) => i < spinN && v !== stillTo.spins[i]).length;
  const driftN = Math.min(stillFrom.drifts.length, stillTo.drifts.length);
  const wandering = stillFrom.drifts.filter((v, i) => i < driftN &&
    JSON.stringify(v) !== JSON.stringify(stillTo.drifts[i])).length;
  const SELF_MIN = Math.max(3, Math.ceil(spinN * 0.8));
  note('of ' + spinN + ' built worlds, ' + turning + ' turned on their own axes and ' +
       wandering + ' moved along their micro-orbits while the root stood still');
  ok(spinN >= 3 && turning >= SELF_MIN,
     'THE SKY IS STILL, NOT FROZEN: ' + turning + ' of ' + spinN +
     ' worlds turned on their own axes during the hold (at least ' + SELF_MIN + ' required)',
     JSON.stringify({ worlds: spinN, turning: turning,
                      from: stillFrom.spins.slice(0, 5), to: stillTo.spins.slice(0, 5) }));
  ok(driftN >= 3 && wandering >= Math.max(3, Math.ceil(driftN * 0.8)),
     'and ' + wandering + ' of ' + driftN + ' rode their micro-orbits: motion INSIDE the ' +
     'frame is what the still frame is for',
     JSON.stringify({ worlds: driftN, wandering: wandering,
                      from: stillFrom.drifts.slice(0, 3), to: stillTo.drifts.slice(0, 3) }));

  /* The pointer goes back to the middle and the lean unwinds, so the pictures below are of
     the galaxy and not of the galaxy at 2.5 degrees. */
  await page.evaluate('__galaxy.camera.look(0, 0)');
  await sleep(1500);

  /* ---- 2b-3. THE ORRERY: THE WORLDS THEMSELVES TRAVEL --------------------
     A SECTION THAT EXISTS BECAUSE THE SECTION ABOVE IS NOT ENOUGH. "The root did not move
     and the worlds' micro-orbits did" was already proved, and it was proved of a wobble a
     few per cent of a world's radius wide, riding on the planet's own Object3D INSIDE its
     group - a shimmer that no link and no label ever had to follow because nothing outside
     that group could see it. The orrery is the other thing: the world's own COORDINATES
     travel, which means the relation dots and the hover annotation have to travel with them.

     THE FOUR FAILURE MODES THIS SECTION IS BUILT AROUND, each of which passed something
     during development:
       (a) the coordinates travel and the spheres do not. Measured for real: 21.99 world
           units of coordinate against 3.48 of mesh, because 3d-force-graph puts its whole
           per-frame position update behind `engineRunning` and stops the moment the layout
           settles. Every screen-space reading agreed the deck was fine, because every one of
           them went through graph2ScreenCoords, which projects the number and not the world.
       (b) too slow to see. A floor satisfied by anything above it is the strip's mistake from
           section 23 all over again, so the floor here is the DECLARED px/minute and not
           "greater than zero".
       (c) too fast to sit with. A ceiling, in the same units, from the same measurement.
       (d) a drift that adds up - worlds walking out of frame over an afternoon. Caught by the
           offset being bounded: |offset| must never exceed the world's own amplitude.
     And one more that is not about motion at all: worlds must not drift INTO each other. The
     amplitude was chosen against a measured 49-unit closest approach, and this re-measures the
     closest approach over the whole window rather than trusting the arithmetic. */
  const orrD = await page.json('__galaxy.orrery.DECLARED');
  const orrOn = await page.json('({on: __galaxy.orrery.on, why: __galaxy.orrery.why,' +
    ' worlds: __galaxy.orrery.worlds, frames: __galaxy.orrery.frames})');
  note('orrery: ' + orrOn.why + ' · ' + orrOn.worlds + ' worlds · ' + orrOn.frames +
       ' frames · amp ' + orrD.AMP + ' x radius, floor ' + orrD.AMP_MIN + 'u · periods ' +
       orrD.T_MIN + '-' + orrD.T_MAX +
       's · declared ' + orrD.PX_MIN + '-' + orrD.PX_MAX + ' px/minute');
  ok(orrOn.on === true && orrOn.why === 'travelling' && orrOn.frames > 100,
     'THE ORRERY IS RUNNING: ' + orrOn.frames + ' frames of travel so far, and it says "' +
     orrOn.why + '" rather than naming a throw',
     JSON.stringify(orrOn));
  ok(orrD.AMP > 0 && orrD.AMP_MIN > 0 && orrD.T_MIN >= 60 && orrD.T_MAX > orrD.T_MIN &&
     orrD.PX_MIN > 0 && orrD.PX_MAX > orrD.PX_MIN,
     'and its numbers are DECLARED in one place: amplitude ' + orrD.AMP +
     ' x the world\'s own radius with a floor of ' + orrD.AMP_MIN + ' world units, period ' +
     orrD.T_MIN + '-' + orrD.T_MAX + 's, screen speed ' + orrD.PX_MIN + '-' + orrD.PX_MAX +
     ' px/minute at the default camera',
     JSON.stringify(orrD));

  /* TWENTY SECONDS, sampled every second, and a picture at each end sixty seconds apart.
     A second is the right grain for this: it is long enough that a world at 10 px/minute
     has moved a measurable fraction of a pixel and short enough that twenty of them
     describe the path rather than the chord. */
  const ORR_MS = 20000, ORR_STEP = 1000;
  /* FIRST, THE SKY HAS TO BE COLD. Every number below is a SCREEN-SPACE path length, and a
     world's screen position moves for two quite different reasons: the orrery's own ellipse,
     which is what is being measured, and the force layout still settling, which is not. The
     two are indistinguishable in sx/sy, and the second one is much the larger while it lasts.
     MEASURED: on a thirty-world corpus this reported the fastest world at 74.5 px/minute
     against a declared ceiling of 30 - two and a half times over - with every world-space
     offset inside its own amplitude, which is the signature of exactly this confusion: the
     orbits were within bounds and the ground underneath them was still moving.
     THE BASE POSITION IS THE ONE TO WATCH, not x: x is base + orbit, so a cold layout under a
     travelling orrery still changes x every frame. base = x - ox, which the sample already
     carries both halves of. */
  const baseStill = async () => {
    let prev = null;
    for (let i = 0; i < 60; i++) {
      const s = await page.json('__galaxy.orrery.sample()');
      const base = s.map((w) => [w.x - (w.ox || 0), w.y - (w.oy || 0), w.z - (w.oz || 0)]);
      if (prev) {
        let worst = 0;
        for (let k = 0; k < base.length; k++) {
          worst = Math.max(worst, Math.hypot(base[k][0] - prev[k][0], base[k][1] - prev[k][1],
                                             base[k][2] - prev[k][2]));
        }
        if (worst < 0.02) return { secs: i, worst: worst };
      }
      prev = base;
      await sleep(1000);
    }
    return { secs: 60, worst: -1 };
  };
  const cold = await baseStill();
  ok(cold.worst >= 0 && cold.worst < 0.02,
     'THE SKY IS COLD BEFORE IT IS TIMED: the force layout settled after ' + cold.secs +
     's, and every world\'s base position now moves less than ' + cold.worst.toFixed(4) +
     ' units a second - so what is measured below is the orrery and not the simulation',
     'the layout was still moving after 60s (worst ' + cold.worst.toFixed(3) + ' units/s), so ' +
     'a screen-space speed measured now would be the simulation\'s and not the orrery\'s');
  note('watching ' + orrOn.worlds + ' worlds travel for ' + (ORR_MS / 1000) + 's');
  const orrShotA = await page.shot('_runs/after/orrery-wide-A.png');
  const orrShotAt = Date.now();
  const orrSamples = [];
  for (let i = 0; i * ORR_STEP <= ORR_MS; i++) {
    orrSamples.push({ at: await page.evaluate('performance.now()'),
                      s: await page.json('__galaxy.orrery.sample()') });
    if (i * ORR_STEP < ORR_MS) await sleep(ORR_STEP);
  }
  const oFirst = orrSamples[0].s, oLast = orrSamples[orrSamples.length - 1].s;
  const orrSecs = (orrSamples[orrSamples.length - 1].at - orrSamples[0].at) / 1000;

  /* (a) THE SPHERES ARE WHERE THE NUMBERS SAY THEY ARE, every sample, every world. Not
     "the mesh moved" - that was true while the defect was live, because the planetarium's
     own micro-drift moves it - but "the mesh is AT the coordinate". A mesh that has stopped
     being copied drifts away from its coordinate and never comes back. */
  let meshOff = 0, meshWorld = '';
  for (const smp of orrSamples) for (const w of smp.s) {
    if (w.mx == null) continue;
    const d = Math.hypot(w.mx - w.x, w.my - w.y, w.mz - w.z);
    if (d > meshOff) { meshOff = d; meshWorld = w.id; }
  }
  ok(meshOff <= 0.001,
     'AND THE SPHERES GO WITH THE NUMBERS: across ' + orrSamples.length + ' samples of ' +
     oFirst.length + ' worlds the largest gap between a world\'s coordinate and its rendered ' +
     'mesh was ' + meshOff.toFixed(5) + ' units',
     'world ' + meshWorld + ' sat ' + meshOff.toFixed(3) + ' units from its own coordinate. ' +
     'This is the library\'s engineRunning gate: it stops copying coordinates into Object3D ' +
     'positions when the layout settles, and the orrery must do it instead');

  /* (b) and (c) THE ENVELOPE, as screen-space PATH LENGTH per minute - the distance each
     world actually travelled across the glass, summed over the window. Net displacement is
     not used and must not be: a world halfway round its ellipse returns towards its start,
     so a net-displacement floor is failed hardest by the world that travelled furthest. */
  /* THE STRIDE HAS TO BE LONGER THAN THE NOISE, AND A SECOND IS NOT. This is a path length in
     SCREEN PIXELS, and the declared ceiling is 30 px/minute - which is half a pixel a second.
     Summed over twenty one-second intervals, absolute magnitudes of half-pixel displacements
     are mostly the projection's own jitter: the camera's micro-drift, the parallax's eased
     lean, and the rounding in graph2ScreenCoords. Every one of those contributes a POSITIVE
     term to a sum of magnitudes, so the estimator can only ever read high.
     MEASURED, TWICE, AND THE SECOND ATTEMPT IS WHY THIS COMMENT EXISTS. At a one-second stride
     the thirty worlds read 19.7 to 74.6 px/minute against a declared 6 to 30 - the whole
     distribution lifted, which looks like a term they all share. So the per-interval median
     was computed as that shared term and subtracted, and the fastest world went UP, from 30.5
     to 64.9: subtracting a vector from a displacement of similar size and different direction
     increases its magnitude. That disconfirmed the shared-term theory and named the real one -
     at this stride there is no signal to decompose, only noise.
     FIVE SECONDS INSTEAD. A world of 60-100s period crosses about a quarter of its ellipse in
     the twenty-second window, so four five-second chords follow that arc to well under a
     percent, while each one carries five times the travel for the same jitter. Net
     displacement is still refused, for the reason the original comment gives: a world halfway
     round its ellipse is on its way home, and a floor measured on the chord is failed hardest
     by the world that travelled furthest. The one-second figure is kept beside it as
     `glassPxMin` so the two can be read against each other rather than one replacing the
     other quietly. */
  /* AND THE ENVELOPE IS A CLAIM ABOUT A CAMERA, WHICH THIS SKY IS NOT SITTING AT.
     PX_MIN/PX_MAX are declared in SCREEN PIXELS, and the declaration says where from: "at the
     default camera ... at 1400x940 (1378 x 842 css) ... at a camera that settles at z 2304 -
     so 0.3919 px per world unit", over 31 worlds. A pixel is not a property of the orrery. It
     is the product of the orbit, the field of view and HOW FAR AWAY THE CAMERA PARKED, and the
     camera parks wherever the deck's one zoomToFit puts it - which depends on how wide the
     layout spread, which depends on the corpus. A harness that brings its own sky, as this one
     now does, is by construction not at the camera the numbers were taken from.
     THIS WAS THE THIRD HYPOTHESIS AND THE RIGHT ONE, and the first two are worth keeping
     because each was disconfirmed by a measurement rather than dropped. (1) The force layout
     was still cooling: refuted by the cold-sky gate above - it settles in a second and the
     worst base motion after that is 0.0000 units/s. (2) A motion the whole frame shared was
     being counted as each world's own: refuted by subtracting the per-interval median, which
     moved the fastest world the WRONG WAY, from 30.5 to 64.9. (3) The scale: the readings ran
     2.4x the ceiling, and 2.4x is not a subtle bug - it is what a camera two and a half times
     closer does to every pixel figure on the glass, which is the exact mistake this
     declaration's own comment records making twice in the other direction.
     SO THE READINGS ARE CONVERTED to the camera the ceiling was declared at before they are
     compared to it. For a fixed vertical field of view the scale goes as height/distance, so
     the factor is (live distance / 2304) x (842 / live css height) - no field of view needed,
     which matters because the page does not expose one. Both figures are printed. If the two
     cameras ever coincide the factor is 1 and nothing happens.
     FAILURE MODE THIS NAMES, and it is the one that was live here: a green ceiling on a wide
     sky and a red one on a narrow sky, from the same orrery, with the harness reporting a
     defect in the page every time the employer's collection changed shape. */
  const DECL_Z = 2304, DECL_H = 842, DECL_PX = 0.3919;
  const cam = await page.json('({pos: __galaxy.camera.pos, t: __galaxy.camera.target,' +
                              ' h: window.innerHeight, w: window.innerWidth})');
  const camDist = Math.hypot(cam.pos[0] - cam.t.x, cam.pos[1] - cam.t.y, cam.pos[2] - cam.t.z);
  const toDecl = (camDist / DECL_Z) * (DECL_H / cam.h);
  note('the camera sits ' + camDist.toFixed(0) + ' units out over ' + cam.h + ' css px (' +
       (DECL_PX / toDecl).toFixed(4) + ' px per world unit) where the envelope was declared at ' +
       DECL_Z + ' over ' + DECL_H + ' (' + DECL_PX + ') - so every reading below is multiplied ' +
       'by ' + toDecl.toFixed(3) + ' to be compared with a ceiling declared at that camera');
  const STRIDE = 5;
  const orrRows = [];
  for (let k = 0; k < oFirst.length; k++) {
    let pathPx = 0, jitterPx = 0, offMax = 0;
    for (let i = 0; i < orrSamples.length; i++) {
      const w = orrSamples[i].s[k];
      offMax = Math.max(offMax, Math.hypot(w.ox || 0, w.oy || 0, w.oz || 0));
      if (i === 0) continue;
      const p = orrSamples[i - 1].s[k];
      jitterPx += Math.hypot(w.sx - p.sx, w.sy - p.sy);
      if (i % STRIDE === 0) {
        const q = orrSamples[i - STRIDE].s[k];
        pathPx += Math.hypot(w.sx - q.sx, w.sy - q.sy);
      }
    }
    const strided = Math.floor((orrSamples.length - 1) / STRIDE) * STRIDE;
    const perSample = orrSecs / (orrSamples.length - 1);
    orrRows.push({ id: oFirst[k].id, period: oFirst[k].period, amp: oFirst[k].amp,
                   r: oFirst[k].r, offMax: offMax,
                   pxMin: pathPx * 60 * toDecl / (strided * perSample),
                   glassPxMin: jitterPx * 60 * toDecl / orrSecs,
                   here: pathPx * 60 / (strided * perSample) });
  }
  /* THE FLOOR BINDS WHERE THE DECLARATION SAYS IT BINDS. AMP_MIN exists because an unlinked
     note is the smallest world on the deck and was the one world under the px floor; the claim
     in the page is that 8.00 units is under what a single relation already buys, so it can
     only ever catch degree-0 worlds. That is an arithmetic claim about live radii and it is
     checked here rather than asserted in a comment: every world the floor lifted must be a
     world whose radius is the smallest radius on the deck. */
  const floored = orrRows.filter((r) => r.amp > orrD.AMP * r.r + 1e-9);
  const minR = Math.min(...orrRows.map((r) => r.r));
  ok(floored.every((r) => Math.abs(r.r - minR) < 1e-6),
     'THE AMPLITUDE FLOOR CATCHES ONLY THE QUIETEST WORLDS: ' + floored.length + ' of ' +
     orrRows.length + ' had their excursion lifted to the declared ' + orrD.AMP_MIN +
     ' units, and every one of them is a world of the smallest radius on the deck (' +
     minR.toFixed(2) + ' units, which is an unlinked note) - so no world with a relation, and ' +
     'therefore no world with a close neighbour, travels further than its own radius licenses',
     'the floor reached a world that has neighbours, which spends the collision margin the ' +
     'amplitude was argued against: ' +
     JSON.stringify(floored.filter((r) => Math.abs(r.r - minR) >= 1e-6)
                           .slice(0, 5).map((r) => [r.id, +r.r.toFixed(2), +r.amp.toFixed(2)])));
  orrRows.sort((a, b) => a.pxMin - b.pxMin);
  const slowest = orrRows[0], fastest = orrRows[orrRows.length - 1];
  note('slowest world "' + slowest.id + '" (period ' + slowest.period.toFixed(0) + 's) ' +
       slowest.pxMin.toFixed(1) + ' px/minute · fastest "' + fastest.id + '" (period ' +
       fastest.period.toFixed(0) + 's) ' + fastest.pxMin.toFixed(1) + ' px/minute · ' +
       'at the declared camera, measured on a ' + STRIDE + 's stride · on this run\'s own ' +
       'glass they travel ' + slowest.here.toFixed(1) + ' and ' + fastest.here.toFixed(1) +
       ' · summed at a 1s stride, where jitter is a bigger share of the reading, ' +
       slowest.glassPxMin.toFixed(1) + ' and ' + fastest.glassPxMin.toFixed(1));
  const tooSlow = orrRows.filter((r) => r.pxMin < orrD.PX_MIN);
  ok(orrRows.length >= 10 && tooSlow.length === 0,
     'EVERY WORLD TRAVELS FAR ENOUGH TO SEE: all ' + orrRows.length + ' cleared the declared ' +
     'floor of ' + orrD.PX_MIN + ' px/minute, the slowest at ' + slowest.pxMin.toFixed(1),
     tooSlow.length + ' world(s) under the floor - a world that does not move is furniture ' +
     'again, and "greater than zero" would have passed it: ' +
     JSON.stringify(tooSlow.slice(0, 5).map((r) => [r.id, +r.pxMin.toFixed(2)])));
  const tooFast = orrRows.filter((r) => r.pxMin > orrD.PX_MAX);
  ok(tooFast.length === 0,
     'AND NONE OF THEM IS BUSY: all ' + orrRows.length + ' stayed under the declared ceiling ' +
     'of ' + orrD.PX_MAX + ' px/minute, the fastest at ' + fastest.pxMin.toFixed(1) +
     ' - which is ' + (fastest.pxMin / 60).toFixed(2) + ' px in a second, and a second is ' +
     'the interval the brief says nothing may be visible over',
     tooFast.length + ' world(s) over the ceiling: ' +
     JSON.stringify(tooFast.slice(0, 5).map((r) => [r.id, +r.pxMin.toFixed(2)])));
  /* (d) BOUNDED, NOT INTEGRATED - and bounded by the RIGHT number, which the first version of
     this assertion got wrong and was right to fail on. It compared the offset's magnitude to
     the amplitude A, as though the excursion were a sphere of radius A. It is not: the three
     axes carry A x 1, A x 0.62 and A x 0.84, so the furthest a world can be from its base is
     A x sqrt(1 + 0.62^2 + 0.84^2) = 1.4456 A. The measured worst was 1.369 A - inside the real
     envelope and outside the one I had written down. The honest statement of "bounded" is
     per-axis, which is both correct and strictly stronger than any bound on the magnitude:
     each component must stay inside its own axis weight. */
  const AXIS = orrD.AXIS;
  const perAxis = [];
  for (let k = 0; k < oFirst.length; k++) {
    let wx = 0, wy = 0, wz = 0;
    for (const smp of orrSamples) {
      const w = smp.s[k];
      wx = Math.max(wx, Math.abs(w.ox || 0)); wy = Math.max(wy, Math.abs(w.oy || 0));
      wz = Math.max(wz, Math.abs(w.oz || 0));
    }
    const a = oFirst[k].amp;
    perAxis.push({ id: oFirst[k].id,
                   rx: wx / (a * AXIS[0]), ry: wy / (a * AXIS[1]), rz: wz / (a * AXIS[2]) });
  }
  const bust = perAxis.filter((r) => r.rx > 1.001 || r.ry > 1.001 || r.rz > 1.001);
  const worstAxis = Math.max(...perAxis.map((r) => Math.max(r.rx, r.ry, r.rz)));
  ok(bust.length === 0,
     'and the travel is BOUNDED rather than accumulated: across ' + orrSamples.length +
     ' samples no world\'s offset ever left its per-axis envelope of A x ' +
     JSON.stringify(AXIS) + ' (worst ' + worstAxis.toFixed(4) + ' of the axis allowance)',
     'an offset past its envelope means the drift is being integrated, which walks the ' +
     'worlds out of frame over an afternoon and passes every short measurement: ' +
     JSON.stringify(bust.slice(0, 5)));
  /* AND THEY DO NOT DRIFT INTO EACH OTHER. Surface to surface, over every sample. */
  let tight = Infinity, tightPair = '';
  for (const smp of orrSamples) {
    for (let i = 0; i < smp.s.length; i++) for (let j = i + 1; j < smp.s.length; j++) {
      const a = smp.s[i], b = smp.s[j];
      const gap = Math.hypot(b.x - a.x, b.y - a.y, b.z - a.z) - a.r - b.r;
      if (gap < tight) { tight = gap; tightPair = a.id + '/' + b.id; }
    }
  }
  /* THE FLOOR IS THE ARITHMETIC AND NOT A ROUND NUMBER, and it is RECOMPUTED from live bases
     rather than copied out of the page's comment - which is the whole point, because the pair
     that comment named stopped being the closest pair when the layout last moved and nothing
     would have said so. A world can be at most A x sqrt(1 + 0.62^2 + 0.84^2) = 1.4456 A from
     its base, so a pair's gap can shrink by at most 1.4456 (A1 + A2) - once, not twice, because
     each world's excursion is measured from its own base and the gap is measured between the
     bases. Over all 465 pairs, the smallest (base gap - that closure) is what the amplitude
     guarantees, and it must be positive: that is the assertion an amplitude raised past what
     this layout can carry would fail, and "greater than zero units of measured clearance"
     would not. The measured approach is then checked against the bound as well, which is what
     catches the model being wrong rather than the amplitude - an offset that could exceed
     1.4456 A would show up here as a real gap smaller than a guaranteed one. */
  let guard = Infinity, guardPair = '';
  {
    const bases = orrSamples[0].s.map((w) => ({ id: w.id, r: w.r, amp: w.amp,
      x: w.x - (w.ox || 0), y: w.y - (w.oy || 0), z: w.z - (w.oz || 0) }));
    for (let i = 0; i < bases.length; i++) for (let j = i + 1; j < bases.length; j++) {
      const a = bases[i], b = bases[j];
      const left = Math.hypot(a.x - b.x, a.y - b.y, a.z - b.z) - a.r - b.r
                 - 1.4456 * (a.amp + b.amp);
      if (left < guard) { guard = left; guardPair = a.id + '/' + b.id; }
    }
  }
  ok(guard > 0 && tight >= guard,
     'and NO TWO WORLDS TOUCH while they travel, by arithmetic and not by luck: over all ' +
     'pairs the tightest guarantee is ' + guard.toFixed(1) + ' world units of clearance (' +
     guardPair + ', base gap minus 1.4456 x both amplitudes), and the closest any pair actually ' +
     'came over the window was ' + tight.toFixed(1) + ' (' + tightPair + ') - outside the bound, ' +
     'as it must be',
     'either the guaranteed clearance has gone negative, which means the amplitude is wrong for ' +
     'this layout, or a real approach came inside the bound, which means the bound is wrong: ' +
     JSON.stringify({ guard: guard, guardPair: guardPair, tight: tight, tightPair: tightPair }));

  /* LINKS FOLLOW THEIR WORLDS. This deck draws no library lines - linkVisibility(false), the
     relation is carried by the travelling dots - so "links follow" is a claim about the dots,
     and it is checked the way it is stated: a dot's live position, read out of the position
     buffer, must lie ON the segment between its two endpoints' live coordinates. The failure
     mode is a frame of lag: if flowFrame read last frame's endpoints while the worlds moved
     this frame, every dot would sit slightly off its own line, in the direction its endpoints
     were travelling. Perpendicular distance is the measurement that sees that and the
     parameter t is the one that does not. */
  const glue = await page.json(`(function(){
    var out = [];
    /* The dot buffer is laid out PER_LINK dots per link in the order of the active link
       list, which is the same array flowFrame walks - so dot i belongs to link
       floor(i / PER_LINK) and no lookup is needed or trusted. */
    var links = __galaxy.active;
    var per = __galaxy.flow.perLink || 1;
    for (var i = 0; i < 12 && i < __galaxy.flow.dots; i++) {
      var p = __galaxy.flow.sampleAt(i);
      if (!p) continue;
      var l = links[Math.floor(i / per)];
      if (!l) continue;
      var a = l.source, b = l.target;
      if (!a || !b || !isFinite(a.x) || !isFinite(b.x)) continue;
      var vx = b.x - a.x, vy = b.y - a.y, vz = b.z - a.z;
      var len = Math.hypot(vx, vy, vz) || 1;
      var wx = p[0] - a.x, wy = p[1] - a.y, wz = p[2] - a.z;
      var t = (wx * vx + wy * vy + wz * vz) / (len * len);
      var px = a.x + vx * t, py = a.y + vy * t, pz = a.z + vz * t;
      out.push({ i: i, t: +t.toFixed(4), off: +Math.hypot(p[0]-px, p[1]-py, p[2]-pz).toFixed(4),
                 len: +len.toFixed(2) });
    }
    return out;
  })()`);
  const offWorst = glue.length ? Math.max(...glue.map((g) => g.off)) : Infinity;
  const tBad = glue.filter((g) => g.t < -0.02 || g.t > 1.02);
  note('twelve dots against their live endpoints: worst perpendicular offset ' +
       offWorst.toFixed(3) + ' units, t in [' +
       (glue.length ? Math.min(...glue.map(g => g.t)).toFixed(3) : '?') + ', ' +
       (glue.length ? Math.max(...glue.map(g => g.t)).toFixed(3) : '?') + ']');
  ok(glue.length >= 6 && offWorst < 0.6 && tBad.length === 0,
     'THE RELATIONS FOLLOW THEIR WORLDS: all ' + glue.length + ' sampled dots sit ON the ' +
     'segment between their two endpoints\' LIVE coordinates - worst perpendicular offset ' +
     offWorst.toFixed(3) + ' units against links ' +
     (glue.length ? Math.min(...glue.map(g => g.len)).toFixed(0) : '?') + '+ units long',
     'a dot off its own line is a frame of lag between the orrery moving the worlds and ' +
     'flowFrame placing the dots, which is why the orrery runs before flowTick and not after: ' +
     JSON.stringify(glue.slice(0, 6)));

  /* THE HOVER ANNOTATION STAYS GLUED while its world drifts under the pointer. Not "the
     annotation is still on screen" - that is true of an annotation nailed to one pixel while
     its world leaves. The annotation's anchor must move BY THE SAME VECTOR the world's
     projection moved, every sample. hudPlace derives the anchor from the projection plus a
     leader of min(apparent radius, 90) + GAP, so the two deltas agree to within the change
     in apparent radius and a rounding - a couple of pixels, not zero.
     A world near the right edge is skipped: at HUD.EDGE the annotation mirrors to the other
     side, which moves the anchor by twice the leader on one frame for an honest reason. */
  /* THE WORLD IS CHOSEN BY INDEX AND HOVERED BY ITS OWN ID, which is not fussiness. The
     sampler stringifies ids so its output is comparable, and the first version of this
     section hovered that string - __galaxy.hover("3") - against a deck whose ids are NUMBERS.
     byId.get("3") finds nothing, so nothing was hovered, and the section then measured an
     annotation that was off: twelve samples of a frozen anchor, a slip of 0.57px, and an
     assertion that read as "the annotation barely moved" when the truth was "there was no
     annotation". Hence the index, and hence `on` and `node` being asserted on every sample
     rather than assumed from the call having been made. */
  const hoverPick = await page.json(`(function(){
    var s = __galaxy.orrery.sample();
    var best = null;
    for (var i = 0; i < s.length; i++) {
      if (s[i].sx == null || s[i].sx < 380 || s[i].sx > window.innerWidth - 420) continue;
      if (s[i].sy < 120 || s[i].sy > window.innerHeight - 260) continue;
      if (!best || s[i].amp > best.amp) { best = s[i]; best.idx = i; }
    }
    return best;
  })()`);
  ok(!!hoverPick, 'a world in open glass to hover, clear of the right edge where the ' +
     'annotation mirrors: "' + (hoverPick ? hoverPick.id : 'none') + '"');
  if (hoverPick) {
    const IDX = hoverPick.idx;
    const hovered = await page.json('(function(){ var n = __galaxy.Graph.graphData().nodes[' +
      IDX + ']; __galaxy.hover(n.id);' +
      ' return { id: String(n.id), type: typeof n.id, on: __galaxy.annotation.on }; })()');
    await sleep(400);
    ok(hovered.on === true,
       'and hovering it TOOK: the annotation is on the glass for world "' + hovered.id +
       '", whose id is a ' + hovered.type,
       'the hover did not take, so everything below would be measuring an annotation that is ' +
       'not there: ' + JSON.stringify(hovered));
    /* THIRTY SECONDS, AND THE LENGTH IS DERIVED RATHER THAN PICKED. The bar below is "the
       world must have gone somewhere", and the only defensible size for it is the declared
       floor scaled to this window. At twelve seconds - what this watched at first - the
       declared 6 px/minute guarantees 1.2 px, so a bar of 2 px was quietly asserting 10
       px/minute: a number nothing declared, which duly failed the run the orrery's real
       pixel scale came to light in. Thirty seconds makes the declared floor worth 3 px and
       the bar an honest fraction of it. It costs no wall-clock either: the plates below are
       a fixed sixty seconds apart and this time comes out of the sleep that was owed. */
    const glueRows = [];
    const GLUE_N = 31;
    for (let i = 0; i < GLUE_N; i++) {
      glueRows.push(await page.json(`(function(){
        var w = __galaxy.orrery.sample()[${IDX}];
        return { sx: w ? w.sx : null, sy: w ? w.sy : null, now: performance.now(),
                 at: __galaxy.annotation.at, side: __galaxy.annotation.side,
                 on: __galaxy.annotation.on, node: String(__galaxy.annotation.node) };
      })()`));
      if (i < GLUE_N - 1) await sleep(1000);
    }
    const g0 = glueRows[0], gN = glueRows[glueRows.length - 1];
    const sideHeld = glueRows.every((r) => r.side === g0.side);
    const stillOn = glueRows.every((r) => r.on === true && r.node === hovered.id);
    let slip = 0;
    for (let i = 1; i < glueRows.length; i++) {
      const a = glueRows[i - 1], b = glueRows[i];
      slip = Math.max(slip, Math.hypot((b.at[0] - a.at[0]) - (b.sx - a.sx),
                                       (b.at[1] - a.at[1]) - (b.sy - a.sy)));
    }
    const worldRan = Math.hypot(gN.sx - g0.sx, gN.sy - g0.sy);
    const annRan = Math.hypot(gN.at[0] - g0.at[0], gN.at[1] - g0.at[1]);
    const glueSecs = (gN.now - g0.now) / 1000;
    note('hovered "' + hoverPick.id + '" for ' + glueSecs.toFixed(0) + 's: its projection ran ' +
         worldRan.toFixed(1) + 'px, the annotation ran ' + annRan.toFixed(1) +
         'px, worst per-second slip ' + slip.toFixed(2) + 'px, side "' + g0.side + '" held ' +
         sideHeld);
    ok(stillOn && sideHeld && slip <= 3.5,
       'THE ANNOTATION STAYS GLUED TO A DRIFTING WORLD: over ' + glueSecs.toFixed(0) +
       's its anchor tracked the world\'s projection to within ' + slip.toFixed(2) +
       'px per second - it followed, it was not merely still on the glass',
       'a slip this large means the annotation is anchored to something other than the live ' +
       'coordinate, which is invisible in a screenshot and obvious to a reader: ' +
       JSON.stringify(glueRows.slice(0, 4)));
    /* THE BAR IS THE DECLARATION, SCALED TO THE WINDOW, with a third taken off - and the third
       is the one part of this that is a judgement rather than a derivation, so here is what it
       pays for. PX_MIN is a floor on PATH length averaged over twenty seconds; this measures
       NET displacement over thirty. A world whose motion happens to be pointing along the view
       axis for this particular half-minute projects shorter than its own average, and the two
       are only equal for a world travelling in a straight line across the glass. Two thirds is
       what covers that without the bar ceasing to mean anything. */
    const glueFloor = orrD.PX_MIN * (glueSecs / 60) * (2 / 3);
    ok(annRan > glueFloor && worldRan > glueFloor,
       'and it had something to follow: the world\'s projection moved ' + worldRan.toFixed(1) +
       'px in those ' + glueSecs.toFixed(0) + 's and the annotation moved ' + annRan.toFixed(1) +
       'px with it - against ' + glueFloor.toFixed(1) + 'px, which is the declared floor of ' +
       orrD.PX_MIN + ' px/minute scaled to this window and discounted a third for foreshortening',
       'both near zero means this passed by nothing having moved, which proves no glue at ' +
       'all: ' + JSON.stringify({ worldRan: worldRan, annRan: annRan, floor: glueFloor }));
    await page.evaluate('__galaxy.hover(null)');
    await sleep(300);
  }

  /* AND THE SECOND WIDE SHOT, SIXTY SECONDS AFTER THE FIRST - waited out rather than
     assumed. The twenty-second sampler and the twelve-second hover come to about thirty-five
     seconds between the plates, and "sixty seconds apart" is the brief's number and not
     approximately its number, so the remainder is slept off here. The only thing that may
     differ between the two plates is where the worlds are: same camera, same star field,
     same legend, same toast, nothing hovered in either. */
  const PLATE_GAP_MS = 60000;
  const owed = PLATE_GAP_MS - (Date.now() - orrShotAt);
  if (owed > 0) { note('holding ' + (owed / 1000).toFixed(0) + 's more to make the plates a ' +
                       'full minute apart'); await sleep(owed); }
  const orrShotB = await page.shot('_runs/after/orrery-wide-B.png');
  const plateGap = (Date.now() - orrShotAt) / 1000;
  ok(plateGap >= 59.5,
     'TWO WIDE SHOTS A FULL MINUTE APART: ' + plateGap.toFixed(1) + 's between ' +
     orrShotA.split('/').pop() + ' and ' + orrShotB.split('/').pop() +
     ' - the worlds are elsewhere and nothing else is',
     'plates ' + plateGap.toFixed(1) + 's apart cannot show a minute of travel');
  const netPx = [];
  for (let k = 0; k < oFirst.length; k++) {
    netPx.push(Math.hypot(oLast[k].sx - oFirst[k].sx, oLast[k].sy - oFirst[k].sy));
  }
  note('over the ' + orrSecs.toFixed(0) + 's window, net screen displacement ran ' +
       Math.min(...netPx).toFixed(1) + ' to ' + Math.max(...netPx).toFixed(1) + ' px');

  /* ---- 2c. THE PRESENCE: A CORE MADE OF LIGHT, AND WHAT IT COSTS ---------
     §32 PART 1 CHANGED WHAT THIS SECTION IS OF, AND THAT IS THE ONLY REASON IT IS EDITED.
     The mandate replaces the point-cloud mask with the boss's amber particle-core, so the
     mode this section measures is CORE and not FACE, and the ten criteria below the frame
     rate are replaced with criteria about a sphere - each one named beside the face criterion
     it stands in for, in the report and in the comment above it. Everything else in this
     section is untouched: the same counters, the same floor, the same recorder, the same
     units, so the §31 numbers and these are comparable.
     THE FACE IS NOT DELETED. It is still a mode, it still builds, and section 2c-2 below
     still photographs it - what changed is which mode the deck wears and which mode the
     floor is measured against.
     THE HOLOGRAM IS PART OF THE IDLE PAGE NOW, so it is measured the way the textures and
     the nebula are: not "does it appear" but "does the deck still hold its floor with it on
     the glass". Ten thousand points in one draw call is cheap; ten thousand points rebuilt
     per frame is not, and the difference is invisible in a screenshot. So the counts that
     make it cheap - one object, one material, and a geometry that is written on a mode
     switch and never again - are asserted from the scene graph, and then the frame rate is
     re-measured with CORE live.
     Read at this point in the run rather than at boot on purpose: the audition is long over
     by now, so `probation` is a verdict rather than a work in progress. */
  const pr0 = await page.json('({on: __galaxy.presence.on, built: __galaxy.presence.built,' +
    ' mode: __galaxy.presence.mode, want: __galaxy.presence.want,' +
    ' why: __galaxy.presence.why, trouble: __galaxy.presence.trouble,' +
    ' three: __galaxy.presence.three, objects: __galaxy.presence.objects,' +
    ' materials: __galaxy.presence.materials, shader: __galaxy.presence.shader,' +
    ' points: __galaxy.presence.points, capacity: __galaxy.presence.capacity,' +
    ' probation: __galaxy.presence.probation, baseline: __galaxy.presence.baseline,' +
    ' trial: __galaxy.presence.trial, degraded: __galaxy.presence.degraded,' +
    ' said: __galaxy.presence.said, notes: __galaxy.presence.notes,' +
    ' frames: __galaxy.presence.frames, fps: __galaxy.presence.fps,' +
    ' switches: __galaxy.presence.switches, well: __galaxy.presence.well,' +
    ' level: __galaxy.presence.level, from: __galaxy.presence.from,' +
    ' analyser: __galaxy.presence.analyser, lid: __galaxy.presence.lid,' +
    ' eye: __galaxy.presence.eye, truth: __galaxy.eyes.sight.truth})');
  note('presence: ' + JSON.stringify(pr0));
  ok(pr0.built === true && pr0.on === true && !pr0.trouble,
     'THE PRESENCE IS BUILT AND RUNNING on three r' + pr0.three + ': a hologram docked in ' +
     'the reserved well, mode "' + pr0.mode + '"', JSON.stringify(pr0).slice(0, 400));
  ok(pr0.well.fits === true && pr0.well.lit === true && pr0.well.nofit === false,
     'the Layout Governor gave it a well ' + pr0.well.side + 'px on a side at dpr ' +
     pr0.well.dpr + ', and the canvas is lit rather than stood down',
     JSON.stringify(pr0.well));
  note('the audition: baseline ' + pr0.baseline + 'fps drawn cheap, trial ' + pr0.trial +
       'fps with the dust whole, verdict "' + pr0.probation + '"' +
       (pr0.degraded ? ' - DEGRADED: ' + pr0.degraded : ''));
  /* THE AUDITION EITHER KEPT THE DUST OR SAID WHY IT DID NOT, and both are correct behaviour -
     so the assertion is on the pair, not on the outcome. UI MANDATE II: the rich mode is the
     DUST now and the fallback is the dust drawn CHEAP (PRES.CHEAP_DENSITY of its points), not a
     ring - the ring is gone. Replaces "AND THE AUDITION KEPT THE CORE". */
  ok(pr0.mode === 'dust' || (pr0.degraded && pr0.said === true && pr0.notes.length > 0),
     pr0.mode === 'dust' && !pr0.degraded
       ? 'AND THE AUDITION KEPT THE DUST: ' + pr0.trial + 'fps with ' + pr0.points +
         ' points on the glass, against ' + pr0.baseline + 'fps drawn cheap'
       : 'the dust could not hold the floor on this GPU and it SAID SO ONCE: "' +
         pr0.notes[0] + '" - drawn cheap, which is the law working',
     JSON.stringify({ mode: pr0.mode, probation: pr0.probation, baseline: pr0.baseline,
                      trial: pr0.trial, degraded: pr0.degraded, notes: pr0.notes }));
  /* THE PRESENCE IS PUT ON THE GLASS FOR EVERYTHING BELOW. UI mandate II PART 4: at rest the main
     pane shows the galaxy and the presence comes in when the voice does. "The deck holds its
     floor with the presence on the glass" is a claim about the presence BEING on the glass, so
     the stage is turned to it through stageSet() - the door the ear uses - and handed back at
     the end of the section. */
  await page.evaluate('__galaxy.stage.set("presence", "deck_proof")');
  await sleep(1200);
  if (pr0.mode !== 'dust' || pr0.degraded) {
    note('putting the DUST back by hand for the measurement, exactly as the P row does…');
    await page.evaluate('__galaxy.presence.set("dust")');
    await sleep(1200);
  }
  const core0 = await page.json('({mode: __galaxy.presence.mode,' +
    ' points: __galaxy.presence.points, capacity: __galaxy.presence.capacity,' +
    ' objects: __galaxy.presence.objects, materials: __galaxy.presence.materials,' +
    ' shader: __galaxy.presence.shader, switches: __galaxy.presence.switches,' +
    ' frames: __galaxy.presence.frames, stage: __galaxy.stage.now})');
  /* Replaces "CORE MODE IS LIVE for the measurement below". */
  ok(core0.mode === 'dust' && core0.stage === 'presence',
     'DUST MODE IS LIVE AND ON THE STAGE for the measurement below', JSON.stringify(core0));
  /* Replaces "a core assembled from EXACTLY 13,740 POINTS". The dust is the whole allocation, by
     one written constant, so the exact figure is DUST_FULL and the spare is zero by design. */
  ok(core0.points === DUST_FULL && core0.points <= core0.capacity,
     'and it is a dust cloud of EXACTLY ' + core0.points.toLocaleString() + ' POINTS - the ' +
     'whole ' + core0.capacity + '-point buffer allocated once, filled by one constant (' +
     DUST_PTS + ')', JSON.stringify({ points: core0.points, want: DUST_FULL, cap: core0.capacity }));
  ok(core0.points >= 8000 && core0.points <= 13800,
     'and inside the 8-13.8k band the spec names for a presence that has to read as a volume ' +
     '- the same band the face was held to, unmoved',
     JSON.stringify(core0));
  ok(core0.objects === 1 && core0.materials === 1 && core0.shader === true,
     'ONE Points OBJECT, ONE SHADER MATERIAL, counted off the scene graph: ' +
     core0.objects + ' object, ' + core0.materials + ' material, and it is a ShaderMaterial ' +
     '- light rather than a textured mesh', JSON.stringify(core0));
  await page.evaluate(`(function(){
    window.__fps2 = { deltas: [], run: true };
    var last = performance.now();
    (function step(now){
      if (!window.__fps2.run) return;
      var d = now - last; last = now;
      if (d > 0) window.__fps2.deltas.push(d);
      requestAnimationFrame(step);
    })(last);
    return 'armed';
  })()`);
  note('recording ' + (IDLE_MS / 1000) + 's of the sky WITH THE DUST on the glass…');
  await sleep(IDLE_MS);
  await page.evaluate('window.__fps2.run = false');
  const fd = (await page.json('window.__fps2.deltas')) || [];
  const ftotal = fd.reduce((a, b) => a + b, 0);
  const fmean = fd.length ? (fd.length / (ftotal / 1000)) : 0;
  const fsorted = fd.slice().sort((a, b) => a - b);
  const fp95 = fsorted[Math.floor(fsorted.length * 0.95)] || 0;
  const core1 = await page.json('({mode: __galaxy.presence.mode,' +
    ' frames: __galaxy.presence.frames, fps: __galaxy.presence.fps,' +
    ' worst: __galaxy.presence.worst, switches: __galaxy.presence.switches,' +
    ' points: __galaxy.presence.points, objects: __galaxy.presence.objects,' +
    ' degraded: __galaxy.presence.degraded, level: __galaxy.presence.level,' +
    ' from: __galaxy.presence.from})');
  note('with DUST live: ' + fd.length + ' frames, mean ' + fmean.toFixed(1) + 'fps, p95 ' +
       fp95.toFixed(1) + 'ms  ·  the presence rendered ' +
       (core1.frames - core0.frames) + ' of them and calls it ' + core1.fps + 'fps' +
       '  ·  idle sky without it read ' + mean.toFixed(1) + 'fps');
  ok(fmean >= FPS_FLOOR,
     'THE DECK HOLDS ' + fmean.toFixed(1) + 'fps WITH THE DUST LIVE, above the ' + FPS_FLOOR +
     'fps floor - ' + core1.points + ' points, a live analyser tap and thirty textured ' +
     'worlds, on ' + gpu,
     'mean ' + fmean.toFixed(1) + 'fps with dust vs ' + mean.toFixed(1) + 'fps without');
  ok(fd.length > 100 && Math.abs((core1.frames - core0.frames) - fd.length) < fd.length * 0.35,
     'and IT RIDES THE ORBIT LOOP rather than a second one: the presence drew ' +
     (core1.frames - core0.frames) + ' frames while the page drew ' + fd.length +
     ' - one tick, not two', JSON.stringify({ page: fd.length,
       presence: core1.frames - core0.frames }));
  ok(core1.switches === core0.switches && core1.objects === 1,
     'NO PER-FRAME GEOMETRY REBUILDS: the attributes were written ' + core1.switches +
     ' times for ' + core1.switches + ' mode switches and not once during ' + fd.length +
     ' frames', JSON.stringify({ switches: [core0.switches, core1.switches] }));
  /* Replaces "it was still the CORE at the end of the recording". */
  ok(core1.mode === 'dust' && !core1.degraded,
     'and it was still the DUST at the end of the recording - the sustained guard found ' +
     'nothing to complain about', JSON.stringify(core1));
  ok(core1.from === 'rest' && core1.level < 0.08,
     'AND THE MOUTH IS AT REST while nothing is speaking: level ' + core1.level +
     ' from "' + core1.from + '" - it is driven by a signal, not by a clock',
     JSON.stringify({ level: core1.level, from: core1.from }));
  ok(pr0.truth === false && pr0.lid === 0 && pr0.eye < 0.05,
     'AND THE EYES ARE CLOSED: the camera is off, so the seal reads ' + pr0.truth +
     ', the lid is ' + pr0.lid + ' and the geometry has eased to ' + pr0.eye +
     ' - the metaphor does not lie on an idle page',
     JSON.stringify({ truth: pr0.truth, lid: pr0.lid, eye: pr0.eye }));

  /* THE PLATES: the whole deck with the dust on the stage, then each of the TWO modes at 2x.
     UI MANDATE II PART 3 removes the ring, the cube and the core; the loop is the two modes that
     exist. The switch accounting counts actual changes, as before. */
  const wellRect = await page.json('__galaxy.layout.rects.presence');
  await page.shot('deck-presence.png');
  note('wrote deck-presence.png (the whole deck, with the dust on the stage)');
  const MODE_PLATES = [['dust', 'deck-presence-dust.png'], ['face', 'deck-presence-face.png']];
  let modeFails = 0, writeFails = 0, changes = 0;
  const modeSeen = [];
  let wasMode = core1.mode, sw = core1.switches;
  for (const [m, file] of MODE_PLATES) {
    await page.evaluate('__galaxy.presence.set("' + m + '")');
    await sleep(1400);
    const s = await page.json('({mode: __galaxy.presence.mode,' +
      ' points: __galaxy.presence.points, objects: __galaxy.presence.objects,' +
      ' materials: __galaxy.presence.materials, switches: __galaxy.presence.switches,' +
      ' fps: __galaxy.presence.fps})');
    modeSeen.push(m + ' ' + s.points + 'pts');
    if (s.mode !== m || s.objects !== 1 || s.materials !== 1 || s.points < 1000) modeFails++;
    const want = sw + (m === wasMode ? 0 : 1);
    if (want !== sw) changes++;
    if (s.switches !== want) {
      writeFails++;
      note('   switch accounting: asked for ' + m + ' from ' + wasMode + ', wanted ' + want +
           ' writes, got ' + s.switches);
    }
    sw = s.switches; wasMode = s.mode;
    if (wellRect) await page.shot(file, wellRect);
  }
  note('the two modes: ' + modeSeen.join('  ·  ') +
       (wellRect ? ' - plates at 2x from the well at ' + JSON.stringify(wellRect) : ''));
  /* Replaces "ALL FOUR MODES SWITCH FROM THE COMMAND PANEL'S OWN CALL". */
  ok(modeFails === 0,
     'BOTH MODES SWITCH FROM THE COMMAND PANEL’S OWN CALL and each is the same single Points ' +
     'object refilled: ' + modeSeen.join(', '),
     JSON.stringify({ fails: modeFails, seen: modeSeen }));
  ok(writeFails === 0 && sw === core1.switches + changes,
     'and each one cost EXACTLY ONE attribute write - ' + sw + ' for the life of the page, ' +
     changes + ' of them here for ' + changes + ' actual changes of mode - while asking for ' +
     'the mode already on the glass cost nothing at all',
     JSON.stringify({ from: core1.switches, to: sw, changes: changes, offBy: writeFails }));
  /* Replaces "AND THE OTHER MODES ARE UNTOUCHED BY THE CORE" (ring 5092, cube 8748). The boss's
     instruction removes ring, cube and core outright and supersedes the DO-NOT-ALTER that guarded
     them, so the claim that matters now is the opposite one: THEY ARE GONE. The mode list is
     exactly the two, and asking for any of the three by the panel's own call changes nothing. */
  const presGone = await page.json(`(function(){
    var before = __galaxy.presence.mode, out = {};
    ['ring', 'cube', 'core'].forEach(function (m) { __galaxy.presence.set(m); out[m] = __galaxy.presence.mode; });
    return { modes: __galaxy.presence.modes || null, before: before, after: out };
  })()`);
  const modesNow = presGone.modes || (await page.json('__galaxy.presence.MODES || null'));
  ok(['ring', 'cube', 'core'].every((m) => presGone.after[m] !== m) &&
     JSON.stringify(modesNow) === JSON.stringify(['dust', 'face']),
     'AND RING, CUBE AND CORE ARE GONE: the mode list is exactly ' + JSON.stringify(modesNow) +
     ', and asking for ring, cube or core by the panel\'s own call leaves the presence on ' +
     JSON.stringify(presGone.after),
     JSON.stringify(presGone));
  /* Replaces "and THE FACE STILL BUILDS ... beside the core". Same claim, new neighbour. */
  ok(modeSeen.indexOf('dust ' + DUST_FULL + 'pts') >= 0 &&
     modeSeen.some((s) => /^face \d+pts$/.test(s) && +s.slice(5, -3) >= 8000),
     'and THE FACE STILL BUILDS: it is in the list at ' +
     (modeSeen.find((s) => s.startsWith('face ')) || '?') + ' beside the dust at ' +
     DUST_FULL + ' - selectable the same way it always was',
     JSON.stringify(modeSeen));
  await page.evaluate('__galaxy.presence.set("dust")');
  await sleep(1200);
  /* Replaces "the deck is left wearing its CORE for the pictures below". */
  ok((await page.evaluate('__galaxy.presence.mode')) === 'dust',
     'and the deck is left wearing its DUST for the pictures below');

  /* ---- 2c-2. THE DUST IS A VOLUME, AND IT IS IN THE STATE THE HOUSE IS IN ----
   * §32 REPLACED THE FACE'S CRITERIA WITH THE CORE'S; UI MANDATE II REPLACES THE CORE'S WITH THE
   * DUST'S, one for one, each beside the one it stands in for, and the count does not go down:
   *    old: THE CORE DOOR ANSWERS                  new: THE DUST DOOR ANSWERS
   *    old: CRIT 1 - A SHELL, NOT A BALL            new: CRIT 1 - A VOLUME, NOT A SHELL
   *    old: CRIT 2 - WOVEN FROM GREAT CIRCLES       new: CRIT 2 - NOISE-SHAPED, NOT A FOG
   *    old: CRIT 3 - TWO BANDS, PLACED, FLAT        new: CRIT 3 - DENSE AT THE HEART
   *    old: CRIT 4 - A HEART WITH AIR ROUND IT      new: CRIT 4 - NO FEATURES AT ALL
   *    old: THE RETICLE IS FOUR BRACKETS            new: FOUR STATES, FOUR TOKENS
   *    old: ONE PER QUADRANT                        new: EVERY OCTANT CARRIES DUST
   *    old: ALL FOUR AT THE SAME HALF-SIDE          new: EACH STATE IS ITS OWN COLOUR
   *    old: EACH BRACKET IS AN L                    new: THE LIVE FUNNEL DRIVES THE STATE
   *    old: THE RETICLE FRAMES EVERYTHING           new: THE CLOUD STAYS INSIDE ITS WINDOW
   *    old: THE §33 ORBITS CROSS                    new: A STATE CHANGE EASES, IT DOES NOT CUT
   *    old: THE CORE FILLS 59% OF THE FRAME         new: THE DUST FILLS A STATED SHARE OF THE FRAME
   *    old: inside the mandate's ceiling            new: inside the mandate's ceiling  (kept)
   * Every threshold below was set AFTER measuring the shipped cloud (_runs/sweep50/dustgeo.mjs:
   * density 12,235 at the heart against 2,257 at the edge, clumping 3.41x the Poisson figure,
   * octants within 0.80 of each other, frame fill 0.669) and sits well clear of it, so a fill
   * that drifts toward fog or a ball goes red rather than a measurement that wobbles. */
  const dg = await page.json('__galaxy.presence.dust()');
  const g = dg && dg.geo;
  ok(!!g && dg.points > 0,
     'THE DUST DOOR ANSWERS with the geometry it actually drew, walked off the buffer',
     JSON.stringify(dg && { points: dg.points, geo: g }));
  if (g) {
    note('the shells (0-0.2 .. 0.8-1.0): ' + g.bins.join(' / ') + ' points, density ' +
         g.density.join(' / ') + ' per unit volume · octants ' + g.octants.join('/') +
         ' · clumping ' + g.cv + ' against Poisson ' + g.poissonCv + ' (x' + g.structure + ')');
    ok(g.bins.every((c) => c >= dg.points * 0.01),
       'CRITERION 1 - IT IS A VOLUME AND NOT A SHELL: every one of five radial shells holds dust (' +
       g.bins.join(' / ') + ' of ' + dg.points + ') - a shell would leave the inner ones empty',
       JSON.stringify(g.bins));
    ok(g.structure >= 2.0,
       'CRITERION 2 - IT IS NOISE-SHAPED, NOT A FOG: counts in ' + g.voxels + ' voxels of the ' +
       '0.33-0.57 shell vary ' + g.structure + 'x as much as a uniform scatter of the same mean ' +
       'would (CV ' + g.cv + ' against ' + g.poissonCv + ') - filaments and voids, not an even haze',
       JSON.stringify({ cv: g.cv, poisson: g.poissonCv, structure: g.structure, floor: 2.0 }));
    ok(g.density[0] >= 3 * g.density[4],
       'CRITERION 3 - IT IS DENSE AT THE HEART: ' + g.density[0] + ' points per unit volume in the ' +
       'inner fifth against ' + g.density[4] + ' in the outer - ' +
       (g.density[0] / g.density[4]).toFixed(1) + 'x, floor 3x',
       JSON.stringify(g.density));
    ok(g.roles.length === 1 && g.mesh === 0,
       'CRITERION 4 - IT HAS NO FEATURES AT ALL: one role across every point (' +
       JSON.stringify(g.roles) + ' - no eye, lid, lip, jaw or neck) and ' + g.mesh +
       ' points carrying the face\'s mesh flag',
       JSON.stringify({ roles: g.roles, mesh: g.mesh }));
    const pal = dg.palette || {};
    ok(JSON.stringify(dg.states) === JSON.stringify(['listening', 'thinking', 'speaking', 'alert']) &&
       Object.keys(pal).length === 4,
       'FOUR STATES, FOUR TOKENS: ' + dg.states.join(', ') + ' - read off the stylesheet at boot',
       JSON.stringify(pal));
    const octMin = Math.min(...g.octants), octMax = Math.max(...g.octants);
    ok(octMin >= 0.6 * octMax,
       'EVERY OCTANT CARRIES DUST: ' + g.octants.join('/') + ' - the least is ' +
       (octMin / octMax).toFixed(2) + ' of the most, floor 0.6, so the cloud is not lopsided',
       JSON.stringify(g.octants));
    /* The tokens as the stylesheet writes them - plain #rrggbb, read straight off :root. */
    const tok = await page.json('(function(){var cs = getComputedStyle(document.documentElement),' +
      ' v = function (n) { return cs.getPropertyValue(n).trim().toLowerCase(); };' +
      ' return { listening: v("--blue-structure"), thinking: v("--gold-core"),' +
      ' speaking: v("--gold-hot"), alert: v("--fail") }; })()');
    ok(['listening', 'thinking', 'speaking', 'alert'].every((s) => pal[s] === tok[s]) &&
       new Set(Object.values(pal)).size === 4,
       'EACH STATE IS ITS OWN COLOUR, AND IT IS THE TOKEN\'S: ' +
       Object.keys(pal).map((s) => s + ' ' + pal[s]).join(', ') +
       ' - four different colours, each equal to the stylesheet token it was read from',
       JSON.stringify({ palette: pal, tokens: tok }));
    /* THE LIVE FUNNEL DRIVES IT: setStatus() - the one function every status in the house goes
       through - and the house's own error card, not a pin. */
    const funnel = await page.json(`(function(){
      var out = {};
      __galaxy.status.set('thinking'); out.thinking = __galaxy.presence.dust().live;
      __galaxy.status.set('speaking'); out.speaking = __galaxy.presence.dust().live;
      __galaxy.status.set('listening'); out.listening = __galaxy.presence.dust().live;
      __galaxy.say('what failed?', 'The local engine timed out.', true, null);
      out.alert = __galaxy.presence.dust().live;
      __galaxy.vanish.now(true);
      __galaxy.status.idle();
      out.after = __galaxy.presence.dust().live;
      return out; })()`);
    ok(funnel.thinking === 'thinking' && funnel.speaking === 'speaking' &&
       funnel.listening === 'listening' && funnel.alert === 'alert' && funnel.after === 'listening',
       'THE LIVE FUNNEL DRIVES THE STATE: setStatus("thinking") -> ' + funnel.thinking +
       ', ("speaking") -> ' + funnel.speaking + ', ("listening") -> ' + funnel.listening +
       ', an error card from the house\'s own answer path -> ' + funnel.alert +
       ', and idle again -> ' + funnel.after, JSON.stringify(funnel));
    const reachOk = g.rMax <= 1.0001;
    ok(reachOk && g.frameFill < 0.80,
       'THE CLOUD STAYS INSIDE ITS WINDOW: the farthest point is at ' + g.rMax + ' of the written ' +
       'radius, worn at ' + g.scale + ' - ' + g.frameFill + ' of the frame\'s half-height, inside the ' +
       'edge window the canvas is masked to',
       JSON.stringify({ rMax: g.rMax, frameFill: g.frameFill }));
    /* A STATE CHANGE EASES: the heart's colour is caught strictly between two palettes on the way
       from listening to thinking, driven through setStatus() - the live path. (The plate pin,
       presence.dustState, writes the colour outright on purpose: a plate is of a state, not of a
       transition.) So the claim is about the light, sampled frame by frame, not a class name. */
    /* evaluate, not json: json() wraps the expression in JSON.stringify, which would stringify
       the PROMISE; evaluate awaits it and the function hands back its own JSON. */
    const eased = JSON.parse(await page.evaluate(`(async function(){
      __galaxy.presence.dustState(null);
      __galaxy.status.set('listening');
      await new Promise(function (r) { setTimeout(r, 1500); });
      var seen = [];
      __galaxy.status.set('thinking');
      for (var i = 0; i < 14; i++) {
        await new Promise(function (r) { requestAnimationFrame(function () { r(); }); });
        seen.push(__galaxy.presence.dust().heart);
      }
      await new Promise(function (r) { setTimeout(r, 1800); });
      var end = __galaxy.presence.dust().heart;
      __galaxy.status.idle();
      return JSON.stringify({ seen: seen, end: end, from: __galaxy.presence.dust().palette.listening,
               to: __galaxy.presence.dust().palette.thinking }); })()`));
    /* ARRIVED is within 2/255 a channel: the lerp is exponential (TAU 320ms) and rounds to a hex,
       so after 1.8s it sits a rounding step from the token - #ffb23d for #ffb23c - and an exact
       match would be a test of float rounding, not of the ease. */
    const near = (a, b) => [1, 3, 5].every((i) => Math.abs(parseInt(a.substr(i, 2), 16) -
      parseInt(b.substr(i, 2), 16)) <= 2);
    const between = eased.seen.filter((h) => !near(h, eased.from) && !near(h, eased.to));
    ok(near(eased.end, eased.to) && between.length >= 2,
       'A STATE CHANGE EASES, IT DOES NOT CUT: listening ' + eased.from + ' to thinking ' + eased.to +
       ' passed through ' + between.length + ' intermediate colours in 14 frames (' +
       between.slice(0, 4).join(', ') + ' …) and arrived at ' + eased.end,
       JSON.stringify(eased));
    ok(g.frameFill > 0.60 && g.frameFill < 0.75,
       'AND THE DUST FILLS ' + Math.round(g.frameFill * 100) + '% OF THE FRAME\'S HALF-HEIGHT - ' +
       'the stated band 60-75%, so the cloud reads as the presence and not as a speck or a wall',
       JSON.stringify({ frameFill: g.frameFill }));
    ok(dg.points <= 14000,
       'all of it inside the mandate\'s ceiling: ' + dg.points + ' points, cap 14000',
       JSON.stringify({ points: dg.points }));
  }

  /* ---- 2c-2b. THE DOORS DO NOT ANSWER FOR EACH OTHER ----
     Replaces "THE TWO SHAPE DOORS KNOW WHICH MODE THEY SPEAK FOR" (core() vs shape()). With the
     dust on the glass, dust() answers with geometry and shape() - the face's reader - returns
     null; and core() no longer exists at all, because there is no core to read. */
  const presDoors = await page.json('({shape: __galaxy.presence.shape() === null,' +
    ' dust: !!(__galaxy.presence.dust() && __galaxy.presence.dust().geo),' +
    ' core: typeof __galaxy.presence.core})');
  ok(presDoors.shape === true && presDoors.dust === true && presDoors.core === 'undefined',
     'THE DOORS KNOW WHICH MODE THEY SPEAK FOR: with the dust on the glass dust() answers with ' +
     'geometry, shape() returns null rather than reading the dust through the face\'s ' +
     'vocabulary, and core() is gone with the core', JSON.stringify(presDoors));

  /* ---- 2c-2c. IT PULSES ON SPOKEN SYLLABLES ---- (kept: the pulse is the dust's now) */
  const wasPose = await page.json('__galaxy.face.state');
  await page.evaluate('__galaxy.face.pose("speaking")');
  const spoke = await page.json(
    '(function(){var g=__galaxy.presence;' +
    'return {before: g.pulses, level: g.level, from: g.from};})()');
  await sleep(3200);
  const spoke2 = await page.json(
    '(function(){var g=__galaxy.presence;' +
    'return {after: g.pulses, pulse: g.pulse, level: g.level, from: g.from};})()');
  await page.evaluate('__galaxy.face.pose(' + JSON.stringify(wasPose || 'idle') + ')');
  await sleep(700);
  const quiet = await page.json(
    '(function(){var g=__galaxy.presence;' +
    'return {pulses: g.pulses, pulse: g.pulse, from: g.from};})()');
  const fired = spoke2.after - spoke.before;
  note('three seconds of speaking: ' + fired + ' syllable onsets, level ' + spoke2.level +
       ' from "' + spoke2.from + '"  ·  then back to "' + quiet.from + '"');
  ok(fired >= 2 && spoke2.from === 'cadence',
     'IT PULSES ON SPOKEN SYLLABLES: ' + fired + ' onsets in three seconds of real cadence ' +
     '(floor 2, and the beat clamp allows 2.6 to 7.1), driven through face.pose("speaking") ' +
     'and read off the level source "' + spoke2.from + '" - not off a uniform this harness set',
     JSON.stringify({ fired: fired, from: spoke2.from, level: spoke2.level }));
  ok(quiet.from === 'rest' && quiet.pulse === 0,
     'and it STOPS when the speaking stops: the level source is back to "' + quiet.from +
     '" and the pulse envelope is a clean ' + quiet.pulse +
     ' - alive on a signal, never fidgeting on a clock',
     JSON.stringify(quiet));

  /* ---- THE FOUR PLATES, at the four yaws (kept; plates renamed deck-dust-yaw*) ---- */
  const YAWS = [-30, 0, 30, 90];
  let yawFails = 0;
  const yawSeen = [];
  for (const deg of YAWS) {
    const held = await page.json('__galaxy.presence.yaw(' + deg + ')');
    await sleep(420);
    const u = await page.json('__galaxy.presence.uniforms');
    const want = (deg * Math.PI) / 180;
    if (held !== deg || !u || u.yawHold !== 1 || Math.abs(u.yaw - want) > 0.0005) {
      yawFails++;
      note('   yaw ' + deg + ' did not take: ' + JSON.stringify({ held, u }));
    }
    yawSeen.push(deg + '° (' + (u ? u.yaw.toFixed(4) : '?') + ' rad)');
    if (wellRect) {
      await page.shot('deck-dust-yaw' + (deg < 0 ? 'm' : '') + Math.abs(deg) + '.png', wellRect);
    }
  }
  ok(yawFails === 0,
     'AND THE PRESENCE HOLDS STILL TO BE PHOTOGRAPHED at every angle asked for: ' +
     yawSeen.join('  ·  ') + ' - the uniform read back off the material each time, so the ' +
     'plates are of the attitudes they are named for',
     JSON.stringify({ fails: yawFails, seen: yawSeen }));
  const freed = await page.json('__galaxy.presence.yaw(null)');
  const uFree = await page.json('__galaxy.presence.uniforms');
  ok(freed === null && uFree && uFree.yawHold === 0,
     'and the pin comes out afterwards - the presence is left with its own motion, not frozen ' +
     'at 90 degrees for whatever runs next',
     JSON.stringify({ freed, yawHold: uFree && uFree.yawHold }));

  /* ---- 2c-2d. THREE PINNED PHASES OF THE FLOW, AND THE SPEECH PULSE, AS PLATES ----
     Replaces "THE THREE RING PHASES ARE PINNED AND REPRODUCIBLE". presence.phase(f) pins the one
     clock the dust's flow and turn are driven from; f is in laps of the dust's slow turn now. */
  const PHASES = [[0, 'deck-dust-phase-0.png'], [1 / 3, 'deck-dust-phase-33.png'],
                  [2 / 3, 'deck-dust-phase-66.png']];
  const phaseSeen = [];
  let phaseFails = 0;
  for (const [f, file] of PHASES) {
    const held = await page.json('__galaxy.presence.phase(' + f + ')');
    await sleep(380);
    const u = await page.json('__galaxy.presence.uniforms');
    if (held === null || !u || u.yawHold !== 1 || u.pulse !== 0) {
      phaseFails++;
      note('   phase ' + f.toFixed(4) + ' did not take: ' + JSON.stringify({ held, u }));
    }
    phaseSeen.push(Math.round(f * 100) + '/100 lap (uPhase ' + (u ? u.phase : '?') + ')');
    if (wellRect) await page.shot(file, wellRect);
  }
  ok(phaseFails === 0 && new Set(phaseSeen).size === 3,
     'THREE PINNED PHASES OF THE FLOW ARE REPRODUCIBLE: ' + phaseSeen.join('  ·  ') +
     ' - one clock uniform held, the buffer never rewritten, so the three plates are three ' +
     'moments of ONE cloud and the lookbook can put them side by side',
     JSON.stringify({ fails: phaseFails, seen: phaseSeen }));
  await page.json('__galaxy.presence.phase(0, 1)');
  await sleep(380);
  const uPulse = await page.json('__galaxy.presence.uniforms');
  ok(uPulse && uPulse.pulse === 1 && uPulse.phase === 0,
     'AND THE SPEECH PULSE CAN BE PHOTOGRAPHED AT A STATED AMOUNT: uPulse pinned at ' +
     (uPulse && uPulse.pulse) + ' on the same phase-0 frame as the plate above, so the pair ' +
     'differs in the heart and in nothing else',
     JSON.stringify(uPulse));
  if (wellRect) await page.shot('deck-dust-pulse.png', wellRect);
  const phFreed = await page.json('__galaxy.presence.phase(null)');
  const uPhFree = await page.json('__galaxy.presence.uniforms');
  ok(phFreed === null && uPhFree && uPhFree.yawHold === 0 && uPhFree.pulse === 0 &&
     uPhFree.phase === 0,
     'and THAT pin comes out too: hold ' + (uPhFree && uPhFree.yawHold) + ', pulse ' +
     (uPhFree && uPhFree.pulse) + ', phase ' + (uPhFree && uPhFree.phase) +
     ' - the presence is handed back its own clock', JSON.stringify(uPhFree));

  /* ---- 2c-3. THE COMPACT TIER (kept; the dust thins by density exactly as the core did) ----
     Changed: the fallback when even the compact tier cannot hold the floor is the CHEAP DRAW of
     the same mode (the ring is gone), and the count is dustCount(density) - one constant, no
     per-group floors. The ladder and its crowded-then-cleared fallback are unchanged. */
  const TIER_H = 860;
  const TIER_LADDER = [1600, 1536, 1440, 1366, 1280, 1180, 1100, 1024, 960, 900, 820, 760];
  const TIER_READ = '({tier: __galaxy.presence.well.tier,' +
    ' builtTier: __galaxy.presence.well.builtTier, side: __galaxy.presence.well.side,' +
    ' fits: __galaxy.presence.well.fits, why: __galaxy.presence.well.why,' +
    ' density: __galaxy.presence.well.density, min: __galaxy.presence.well.min,' +
    ' minCompact: __galaxy.presence.well.minCompact, mode: __galaxy.presence.mode,' +
    ' points: __galaxy.presence.points, capacity: __galaxy.presence.capacity,' +
    ' degraded: __galaxy.presence.degraded, cheap: __galaxy.presence.dust().cheap,' +
    ' compactAudit: __galaxy.presence.compactAudit, trial: __galaxy.presence.trial,' +
    ' baseline: __galaxy.presence.baseline, probation: __galaxy.presence.probation})';
  const atWidth = async (w) => {
    await page.send('Emulation.setDeviceMetricsOverride',
      { width: w, height: TIER_H, deviceScaleFactor: 0, mobile: false });
    await sleep(300);
    await page.evaluate('__galaxy.layout.run()');
    await sleep(280);
    return page.json(TIER_READ);
  };
  const settled = async (label) => {
    let r = await page.json(TIER_READ);
    if (r.mode !== 'dust' || r.cheap) {
      note(label + ': the dust was ' + (r.cheap ? 'drawn cheap' : 'off the glass') + ' (' +
           (r.degraded || r.probation || '?') + '), so it is put back by hand to count it');
      await page.evaluate('__galaxy.presence.set("dust")');
      await sleep(1200);
    }
    for (let i = 0; i < 25; i++) {
      r = await page.json(TIER_READ);
      const want = dustCount(r.density);
      if (r.mode === 'dust' && r.points === want) return r;
      await sleep(200);
    }
    note(label + ': the count never settled - ' + r.points + ' points against ' +
         dustCount(r.density) + ' expected at density ' + r.density);
    return r;
  };
  const crowdId = await page.evaluate('__galaxy.nodes[0].id');
  await page.evaluate('__galaxy.focus(' + JSON.stringify(crowdId) + ', true)', true);
  const crowdStart = await galaxy('/focus', { cmd: 'start', minutes: 9 });
  note('the lane crowded: the note panel open and a real session card up (state=' +
       ((crowdStart && crowdStart.focus && crowdStart.focus.state) || '?') + ')');
  await sleep(1400);
  await atWidth(1920);
  const wide = await settled('the full tier');
  ok(wide.tier === 'full' && wide.builtTier === 'full' && wide.density === 1 &&
     wide.points === DUST_FULL && wide.points <= wide.capacity,
     'at 1920x' + TIER_H + ' the well is ' + wide.side + 'px, clear of the ' + wide.min +
     'px full floor, and the presence is at full density: ' +
     wide.points.toLocaleString() + ' points of a ' + wide.capacity + '-point allocation',
     JSON.stringify(wide));
  const rungs = [];
  let compact = null;
  for (const w of TIER_LADDER) {
    const r = await atWidth(w);
    rungs.push(w + '→' + r.side + 'px ' + (r.tier || '-') + (r.why ? ' (' + r.why + ')' : ''));
    if (r.tier === 'compact') { compact = Object.assign({ w: w }, r); break; }
  }
  note('the tier ladder at ' + TIER_H + ' tall: ' + rungs.join('   '));
  let crowdedForTier = true;
  if (!compact) {
    note('no rung produced the compact tier with the lane crowded, so the lane is cleared and the ' +
         'ladder walked again, which is a weaker condition and is reported as one');
    await page.evaluate(`(function(){
      var c = document.getElementById('close');
      if (c && document.getElementById('panel').classList.contains('open')) c.click();
      return document.getElementById('panel').classList.contains('open');
    })()`);
    await galaxy('/focus', { cmd: 'abort' });
    await sleep(1200);
    crowdedForTier = false;
    const bare = [];
    for (const w of TIER_LADDER) {
      const r = await atWidth(w);
      bare.push(w + '→' + r.side + 'px ' + (r.tier || '-') + (r.why ? ' (' + r.why + ')' : ''));
      if (r.tier === 'compact') { compact = Object.assign({ w: w }, r); break; }
    }
    note('the same ladder with the lane clear: ' + bare.join('   '));
    rungs.push('| lane cleared |', ...bare);
  }
  ok(!!compact,
     compact
       ? 'THE COMPACT TIER ENGAGES AT ' + compact.w + 'x' + TIER_H + ': ' + compact.side +
         'px of room, under the ' + compact.min + 'px full floor and over the ' +
         compact.minCompact + 'px compact one - "' + compact.why + '"' +
         (crowdedForTier ? ' (lane crowded, which is the truer room)'
                         : ' (LANE CLEARED to reach it)')
       : 'no width on the ladder produced the compact tier with the lane crowded OR clear, so ' +
         'its point count and its audition cannot be measured in this window',
     JSON.stringify(rungs));
  if (compact) {
    const audited = await waitFor(page,
      '__galaxy.presence.compactAudit === "kept" || ' +
      '__galaxy.presence.compactAudit === "dropped"', 30000);
    await sleep(600);
    const ca = await page.json(TIER_READ);
    ok(audited && (ca.compactAudit === 'kept' || ca.compactAudit === 'dropped'),
       'and it AUDITIONS ITSELF on the mechanism that already exists: "' +
       ca.compactAudit + '" - ' + ca.trial + 'fps compact against ' + ca.baseline +
       'fps drawn cheap, floor ' + FPS_FLOOR + ', keep-ratio 90%',
       JSON.stringify({ audited: audited, ca: ca }));
    /* Changed: "dropped" now means the same dust drawn cheap, not the ring. */
    ok(ca.compactAudit === 'kept' ? (ca.mode === 'dust' && !ca.cheap)
                                  : (ca.mode === 'dust' && ca.cheap === true),
       ca.compactAudit === 'kept'
         ? 'the verdict and the room agree: kept, and the mode is still ' + ca.mode + ', drawn whole'
         : 'the verdict and the room agree: dropped, and it fell back to the CHEAP DRAW of the same ' +
           'dust - not to nothing, and not to a mode that no longer exists',
       JSON.stringify({ verdict: ca.compactAudit, mode: ca.mode, cheap: ca.cheap, degraded: ca.degraded }));
    if (ca.mode !== 'dust' || ca.cheap) {
      note('the compact tier could not hold ' + FPS_FLOOR + 'fps on this GPU: putting the dust ' +
           'back whole by hand to read the point count it would have drawn');
      await page.evaluate('__galaxy.presence.set("dust")');
      await sleep(1200);
    }
    const cf = await page.json(TIER_READ);
    const ratio = wide.points > 0 ? cf.points / wide.points : 0;
    ok(cf.builtTier === 'compact' && cf.points === dustCount(cf.density) &&
       cf.points < wide.points && ratio > 0.3 && ratio < 0.6,
       'AND IT IS THE SAME DUST WITH FEWER POINTS: ' + cf.points.toLocaleString() +
       ' points at ' + Math.round(cf.density * 100) + '% density against ' +
       wide.points.toLocaleString() + ' full - ' + Math.round(ratio * 1000) / 10 +
       '% of the vertices for ' + Math.round((compact.side / wide.side) * 100) +
       '% of the width',
       JSON.stringify({ compact: cf, fullPoints: wide.points, ratio: ratio }));
    const three = await page.json('({objects: __galaxy.presence.objects,' +
      ' materials: __galaxy.presence.materials, shader: __galaxy.presence.shader})');
    ok(three.objects === 1 && three.materials === 1 && three.shader === true,
       'still one object, one material and a real shader at the compact tier - the density ' +
       'changed and nothing else did', JSON.stringify(three));
    const compactRect = await page.json('__galaxy.layout.rects.presence');
    if (compactRect) await page.shot('deck-dust-compact.png', compactRect);
  }
  await page.send('Emulation.clearDeviceMetricsOverride');
  await sleep(300);
  await page.evaluate(`(function(){
    var c = document.getElementById('close');
    if (c && document.getElementById('panel').classList.contains('open')) c.click();
    return document.getElementById('panel').classList.contains('open');
  })()`);
  await galaxy('/focus', { cmd: 'abort' });
  await sleep(1400);
  await page.evaluate('__galaxy.layout.run()');
  await sleep(400);
  const backWide = await settled('back at full width');
  ok(backWide.tier === 'full' && backWide.builtTier === 'full' && backWide.density === 1 &&
     backWide.points === wide.points,
     'and the tier is not a one-way door: the window comes back and so does the full ' +
     'density - ' + backWide.points.toLocaleString() + ' points again',
     JSON.stringify(backWide));
  if (backWide.mode !== 'dust') {
    await page.evaluate('__galaxy.presence.set("dust")');
    await sleep(1000);
  }
  /* AND THE PANE GOES BACK TO THE GALAXY, which is what it shows at rest. */
  await page.evaluate('__galaxy.stage.set("galaxy", "deck_proof")');
  await sleep(1000);

  /* ---- 2c-4. WORK MODE IS THE ROOM, NOT THE CARD --------------------------
     WHAT IS BEING CHECKED, AND WHY EACH HALF OF IT IS SEPARATE. A tint on the countdown
     card is a label; the room going quiet is the feature. So three things are read, and
     from three different organs: the DEEP FIELD's two nebula layers, the DECK's star
     parallax swing, and the PLANETARIUM's emissive desaturation. One number moving would
     be a tint by another name.
     THE SESSION IS REAL. There is no setter for work mode on purpose - it is subscribed to
     focus.py's own SSE push - so this starts a session on the server and aborts it. `arming`
     counts as started: focus.py promotes to `running` only once its reader has LOCKED ON,
     which on a machine whose front window is a headless Chrome never happens, and the room
     is meant to change when the session begins rather than when the lock lands.
     AND THE CROSSFADE IS PROVED BY AN INTERMEDIATE FRAME. A cut and a 900ms ease look
     identical in a before-and-after pair, which is the whole reason the mandate asked for
     the frame in between: at least one sample has to be caught strictly between the two
     ends, in both directions. */
  const workRead = '({t: Math.round(performance.now()), w: __galaxy.work})';
  const nebCss = await page.evaluate(
    '(function(){var e=document.getElementById("nebula-work");if(!e)return null;' +
    'var c=getComputedStyle(e);return JSON.stringify({z:c.zIndex,pe:c.pointerEvents,' +
    'op:c.opacity,pos:c.position,stops:(c.backgroundImage.match(/rgba?\\(/g)||[]).length});})()');
  const neb = nebCss ? JSON.parse(nebCss) : null;
  ok(!!neb && neb.z === '1' && neb.pe === 'none' && neb.pos === 'fixed' &&
     +neb.op === 0 && neb.stops >= 2,
     'THE WORKING SKY IS A SECOND LAYER, not a repaint of the first: #nebula-work sits on ' +
     'layer ' + (neb && neb.z) + ' beside the nebula, ' + (neb && neb.stops) +
     ' gradients, pointer-events ' + (neb && neb.pe) + ', and at rest it is invisible',
     JSON.stringify(neb));
  const w0 = await page.json('__galaxy.work');
  ok(w0.on === false && w0.k === 0 && w0.neb === 1 && w0.nebWork === 0 && w0.sway === 1 &&
     w0.desat === 0,
     'and with no session the room is exactly the room it always was: k=0, nebula at ' +
     w0.neb + ', the second layer at ' + w0.nebWork + ', full parallax, no desaturation',
     JSON.stringify(w0));
  ok(w0.tune && w0.tune.MS === 900 && w0.tune.NEB_IDLE === 1 && w0.tune.NEB_WORK === 0.3 &&
     w0.tune.SWAY === 0.45 && w0.tune.DESAT === 0.45,
     'the five numbers are declared where they can be argued with: ' +
     JSON.stringify(w0.tune) + ' - 900ms is three times --spring-ms, the nebula dims to ' +
     '30% rather than to nothing so the cloud keeps its shape, and the sway and the ' +
     'emissive both give up 55%',
     JSON.stringify(w0.tune));
  const swingIdle = w0.swing;
  await galaxy('/focus', { cmd: 'abort' });
  await sleep(500);
  const started = await galaxy('/focus', { cmd: 'start', minutes: 9 });
  const sState = (started && started.focus && started.focus.state) || '?';
  note('/focus start answered state=' + sState);
  const up = [];
  for (let i = 0; i < 16; i++) { up.push(await page.json(workRead)); await sleep(110); }
  await sleep(700);
  const w1 = await page.json('__galaxy.work');
  note('the ramp up: ' + up.map((r) => r.w.k).join(' → ') + ' → ' + w1.k);
  const mid = up.filter((r) => r.w.k > 0 && r.w.k < 1);
  ok(mid.length >= 2,
     'THE ROOM CROSSFADES RATHER THAN CUTTING: ' + mid.length + ' of ' + up.length +
     ' samples caught it strictly between the two ends (' +
     mid.slice(0, 4).map((r) => r.w.k).join(', ') + ' …)',
     JSON.stringify(up.map((r) => r.w.k)));
  const first1 = up.find((r) => r.w.k === 1);
  const span = first1 ? first1.t - up[0].t : 0;
  ok(!first1 || (span >= 500 && span <= 1700),
     first1
       ? 'and it takes ' + span + 'ms of wall clock to arrive, against the 900ms declared ' +
         '- one --spring curve, not a step'
       : 'the ramp was still moving at the end of the sampling window, which is the same ' +
         'claim from the other side',
     JSON.stringify({ span: span, ms: w0.tune.MS }));
  ok(w1.on === true && w1.k === 1 && w1.neb === 0.3 && w1.nebWork === 1 &&
     w1.desat === 0.45 && Math.abs(w1.sway - 0.45) < 1e-6,
     'AND ALL THREE ORGANS ANSWERED: the nebula fell to ' + w1.neb + ' with the cooler ' +
     'band up at ' + w1.nebWork + ', the star parallax from ' + swingIdle + ' to ' +
     w1.swing + ' units, and the world emissive desaturated by ' +
     Math.round(w1.desat * 100) + '%',
     JSON.stringify(w1));
  ok(w1.turns === w0.turns + 1 && w1.why.includes(sState),
     'once, and it says what turned it: "' + w1.why + '" (turn ' + w1.turns + ')',
     JSON.stringify({ before: w0.turns, after: w1.turns, why: w1.why }));
  await page.shot('deck-work-mode.png');
  note('wrote deck-work-mode.png (the room with a session running)');
  /* AND IT REVERSES, on the same curve. A one-way tint is a bug that only shows up after
     the session the user was not measuring. */
  await galaxy('/focus', { cmd: 'abort' });
  const down = [];
  for (let i = 0; i < 16; i++) { down.push(await page.json(workRead)); await sleep(110); }
  await sleep(800);
  const w2 = await page.json('__galaxy.work');
  note('the ramp down: ' + down.map((r) => r.w.k).join(' → ') + ' → ' + w2.k);
  const midDown = down.filter((r) => r.w.k > 0 && r.w.k < 1);
  ok(midDown.length >= 2 && w2.k === 0 && w2.neb === 1 && w2.nebWork === 0 &&
     w2.desat === 0 && w2.sway === 1,
     'THE ROOM WARMS BACK UP THE SAME WAY IT COOLED: ' + midDown.length +
     ' intermediate samples on the way home, and it settles exactly back on the room it ' +
     'started from - k=' + w2.k + ', nebula ' + w2.neb + ', swing ' + w2.swing,
     JSON.stringify({ down: down.map((r) => r.w.k), settled: w2 }));
  ok(w2.turns === w0.turns + 2,
     'two turns for one session, and not one per SSE push: turns=' + w2.turns,
     JSON.stringify(w2.turns));

  /* ---- 3. THE PICTURE OF THE GALAXY -------------------------------------- */
  await page.shot('deck-galaxy.png');
  note('wrote deck-galaxy.png (the glowing galaxy, nothing open over it)');
  /* AND ONE FROM CLOSE UP, because "the file lives inside the world" is a claim about
     something you have to fly up to a planet to see. The camera is put a short way off the
     biggest hub and the shutter waits for the flight to land. */
  const scansBefore = await page.evaluate('__galaxy.planets.scans');
  const flown = await page.evaluate(`(function(){
    var best = __galaxy.nodes[0], bestR = -1;
    __galaxy.nodes.forEach(function(n){
      var d = __galaxy.planets.shapeOf(n.id);
      if (d && d.radius > bestR) { bestR = d.radius; best = n; }
    });
    __galaxy.focus(best.id, true);
    /* Sampled in the SAME turn as the selection. The sweep is 600ms long and a round trip
       to Node is not free, so asking afterwards could easily be asking too late - and a
       check that sometimes misses the thing it is checking is worse than no check. */
    return JSON.stringify({ label: best.label, id: best.id,
      scanning: __galaxy.planets.scanning, scanned: __galaxy.planets.scanned,
      scans: __galaxy.planets.scans,
      emissive: __galaxy.planets.shapeOf(best.id).emissive });
  })()`, true);
  const sweep = JSON.parse(flown);
  note('sweep: ' + flown);
  ok(sweep.scanning === true && sweep.scans === scansBefore + 1 && sweep.scanned === sweep.id,
     'SELECTING A WORLD STARTS THE SCANLINE, on the world that was selected - the machine ' +
     'acknowledging it has opened one', flown);
  /* And it is over well inside a second, so it cannot be mistaken for a permanent state. */
  await sleep(900);
  const afterSweep = await page.json('Object.assign({scanning: __galaxy.planets.scanning},' +
    ' __galaxy.planets.shapeOf(' + JSON.stringify(sweep.id) + '))');
  ok(afterSweep.scanning === false &&
     Math.abs(afterSweep.emissive - PLANET_EMISSIVE_HOT) < 0.001,
     'and it finishes on its own in under a second, leaving the selected world lit from ' +
     'within (' + afterSweep.emissive + ') rather than painted white',
     JSON.stringify(afterSweep));
  /* THE HOUSING STAYS DARK. A selected world used to come back as '#ffffff' from nodeColor,
     which under an emissive and a bloom is not a highlight, it is an erasure. Now that
     nothing is written on a world the reason has changed and the requirement has not: the
     body is the instrument's housing and the RING is its readout, so a world that lit up
     white would be a machine with its light in the wrong place.
     WHERE THAT NUMBER LIVES MOVED WITH TRUE WORLDS, and this check moved with it rather
     than being relaxed. material.color used to BE the crust, so reading it was reading the
     darkness; now it is a multiplier over a procedural skin, and a near-white multiplier
     over a dark skin is still a dark world. So the law is checked where it is now true:
     the skin's own mean luminance, measured off its pixels at boot, times that multiplier.
     A world painted white still fails, because either number going to one fails. */
  const crust = await page.json('(function(){' +
    ' var s = __galaxy.planets.skinOf(' + JSON.stringify(sweep.id) + ');' +
    ' var b = __galaxy.planets.shapeOf(' + JSON.stringify(sweep.id) + ').body;' +
    ' var ch = String(b).slice(1).match(/../g).map(function(h){ return parseInt(h,16)/255; });' +
    ' var bl = ch[0]*0.2126 + ch[1]*0.7152 + ch[2]*0.0722;' +
    ' return {mean: s ? s.mean : -1, body: b, bodyLum: +bl.toFixed(4),' +
    '         crust: s ? +(s.mean * bl).toFixed(4) : -1};' +
    '})()');
  note('crust: ' + JSON.stringify(crust));
  ok(afterSweep.body !== '#ffffff' && crust.mean > 0 && crust.crust < 0.34,
     'and the selected world keeps a DARK CRUST: skin mean ' + crust.mean + ' times body ' +
     crust.body + ' is ' + crust.crust + ' of white - lit from within, never painted white',
     JSON.stringify(crust));
  await sleep(1200);
  await page.evaluate(`(function(){
    var n = __galaxy.nodes.filter(function(x){ return x.id === __galaxy.selected; })[0];
    if (!n || n.x === undefined) return 'no position';
    var len = Math.hypot(n.x, n.y, n.z) || 1, k = 1 + 34 / len;
    __galaxy.Graph.cameraPosition({ x: n.x * k, y: n.y * k, z: n.z * k }, n, 900);
    return 'closing in';
  })()`);
  await sleep(1400);
  await page.shot('deck-planet.png');
  note('wrote deck-planet.png (one world, close enough to read its surface)');
  await page.evaluate('__galaxy.Graph.cameraPosition({x:0,y:0,z:640},{x:0,y:0,z:0},900)');
  /* Put the selection back the way it was found, through the page's OWN background-click
     handler rather than by reaching into the DOM - so that section 4 below is still
     opening a panel that was shut, which is what it claims to be checking. */
  await page.evaluate('(__galaxy.Graph.onBackgroundClick() || function(){})()');
  await sleep(1100);

  /* ---- 4. THE HYPER-GLASS PANEL ------------------------------------------ */
  const firstId = await page.evaluate('__galaxy.nodes[0].id');
  await page.evaluate('__galaxy.focus(' + JSON.stringify(firstId) + ', true)', true);
  ok(await waitFor(page, 'document.getElementById("panel").classList.contains("open")', 6000),
     'a note opens the side panel');
  await sleep(2100);                          // the flight lands before the picture
  const glass = await page.json('(function(){var s=getComputedStyle(' +
    'document.getElementById("panel"));return {blur: s.backdropFilter || s.webkitBackdropFilter,' +
    ' trans: s.transitionProperty, ms: s.transitionDuration, ease: s.transitionTimingFunction};})()');
  note('panel: ' + JSON.stringify(glass));
  ok(/blur\(12px\)/.test(glass.blur) && /saturate\(1\.5\)|saturate\(150%\)/.test(glass.blur),
     'the panel is hyper-glass: blur(12px) saturate(150%), from the browser\u2019s own ' +
     'computed style', JSON.stringify(glass.blur));
  ok(glass.trans === 'transform' && glass.ms === '0.3s',
     'and it enters on a transform alone, capped at 300ms - no width, no top, no shadow',
     JSON.stringify({ property: glass.trans, duration: glass.ms }));
  /* THE MOTION LANGUAGE, and it is asserted as ARITHMETIC rather than as a string. A
     pattern match on the one curve this file happens to know would pass the day someone
     introduced a second, springier one somewhere else; what the constitution actually
     forbids is an entrance that travels past the value it is animating to, which is
     exactly a control point with y > 1. So both y values are parsed and bounded, and the
     named curve is checked on top of that. */
  const ease = (function (s) {
    const m = /cubic-bezier\(([^)]+)\)/.exec(String(s || ''));
    if (!m) return null;
    const p = m[1].split(',').map(Number);
    return p.length === 4 && p.every((n) => isFinite(n)) ? p : null;
  })(glass.ease);
  ok(!!ease && ease[1] <= 1 && ease[3] <= 1 && ease[1] >= 0 && ease[3] >= 0,
     'and it SETTLES rather than bouncing: both control-point y values inside [0,1], so ' +
     'nothing overshoots the value it is animating to',
     JSON.stringify({ ease: glass.ease, y1: ease && ease[1], y2: ease && ease[3] }));
  ok(/cubic-bezier\(0\.16,\s*1,\s*0\.3,\s*1\)/.test(glass.ease),
     'on the exact curve the constitution names: cubic-bezier(0.16, 1, 0.3, 1)', glass.ease);
  const rim = await css(page, 'panel', 'pointerEvents', '::before');
  ok(rim === 'none', 'the 1px lit rim is a pseudo-element that cannot be clicked', rim);
  const grain = await page.json('(function(){var s=getComputedStyle(' +
    'document.getElementById("grain"));return {o: s.opacity, pe: s.pointerEvents,' +
    ' bg: s.backgroundImage.slice(0, 24)};})()');
  ok(grain.o === '0.02' && grain.pe === 'none' && /^url\("data:image\/svg/.test(grain.bg),
     'the void\u2019s noise is a 2% inline SVG - no request, no click surface',
     JSON.stringify(grain));
  await page.shot('deck-panel.png');
  note('wrote deck-panel.png (the hyper-glass panel over the galaxy)');

  /* ---- 4b. THE TWO RAILS, AND THE ORDER SHEET -----------------------------
     Three surfaces, and one question asked of each: does it report the MACHINE, or does
     it report itself? A readout that can be right while the thing behind it is wrong is
     decoration, and the way to tell the difference from the outside is to read the surface
     and the machine separately and insist that they agree.

       THE TELEMETRY RAIL is checked against /health, fetched here in Node, and against the
         model chip's own text - so "ARCHIVE: 36 FILES" has to be the number of files the
         server says are indexed, and "MODEL: …" has to be the brain the chip already
         names. Then the empty archive is FORCED through the rail's paint door, because the
         one state the constitution has an opinion about is the one this machine is not in:
         nothing indexed has to come up in muted red, measured off the computed colour, and
         the renderer has to still be alive afterwards.
       THE ORGAN RAIL is checked while nothing is running, which is the half that is easy
         to get wrong. Five dots, five state lines, and not one of them lit - a rail that
         glowed at rest would be a rail you stop reading. The beat itself is proved where
         speech is the subject: voice_proof watches the mic organ while the butler talks.
       THE COMMAND PANEL is opened by a REAL Ctrl+K through the browser's own key queue,
         not by calling the function that the key calls, and closed by a real Escape. Every
         row's label and state line is read back, the links order is flipped twice and the
         GRAPH is measured each time, and the casting view has to name the three candidates
         the SERVER named.
       AND THE SUSPENSION, which is the edge case the constitution states: a sheet open
         while the pointer keeps moving. The camera must decline every frame - not stop
         being asked. */
  /* The note panel is closed first, and by its own button. It suspends the parallax by
     design, so leaving it open would make the last claim in this section pass for the
     wrong reason - the strongest possible way to fake "the command panel suspends it". */
  await page.evaluate(`(function(){
    var c = document.getElementById('close');
    if (c && document.getElementById('panel').classList.contains('open')) c.click();
    return document.getElementById('panel').classList.contains('open');
  })()`);
  await sleep(450);

  const trail = await page.json(`(function(){
    var el = document.getElementById('toprail');
    var s = getComputedStyle(el), r = el.getBoundingClientRect();
    var av = getComputedStyle(el.querySelector('#rail-archive .rv'));
    var kv = getComputedStyle(el.querySelector('#rail-archive .rk'));
    return {cells: __galaxy.rail.cells, ms: __galaxy.rail.RAIL_MS, web: __galaxy.rail.web,
            chip: __galaxy.brain.chip,
            order: Array.prototype.map.call(el.children, function (c) { return c.id; }),
            css: {mono: s.fontFamily, size: s.fontSize, up: s.textTransform,
                  pe: s.pointerEvents, z: s.zIndex,
                  blur: s.backdropFilter || s.webkitBackdropFilter,
                  h: Math.round(r.height), top: Math.round(r.top),
                  left: Math.round(r.left), right: Math.round(innerWidth - r.right),
                  railH: parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--rail-h')),
                  titleW: (__galaxy.layout.last || {}).titleW},
            valueColour: av.color, keyMono: kv.fontFamily};
  })()`);
  const cells = trail.cells || {};
  note('top rail: ' + ['model', 'voice', 'archive', 'web'].map((k) =>
    '[' + k + ': ' + ((cells[k] || {}).text || '?') +
    ((cells[k] || {}).tone ? ' ' + cells[k].tone : '') + ']').join(' '));
  ok(JSON.stringify(trail.order) ===
     JSON.stringify(['rail-model', 'rail-voice', 'rail-archive', 'rail-web']),
     'THE TELEMETRY RAIL READS LEFT TO RIGHT AS THE CONSTITUTION ORDERS IT: ' +
     'model, voice, archive, web', JSON.stringify(trail.order));
  const filled = ['model', 'voice', 'archive', 'web'].every((k) => cells[k] &&
    cells[k].shown && cells[k].text && cells[k].text !== '…');
  ok(filled, 'and all four cells are painted with a value rather than the markup’s ellipsis',
     JSON.stringify(cells));
  ok(/mono/i.test(trail.css.mono) && trail.css.up === 'uppercase' &&
     trail.css.size === '10px' && /mono/i.test(trail.keyMono),
     'it is mono type throughout, uppercase, at 10px - an instrument label, not a sentence',
     JSON.stringify({ family: trail.css.mono, size: trail.css.size, transform: trail.css.up }));
  /* UI MANDATE II PART 1 MOVED THIS BAND: the status strip is restyled INTO the header row,
     which is --rail-h (58px) tall and starts where the title block (brand, h1, the computed
     note/connection counts) ends - the governor writes rail.style.left = titleW. Old: h === 30,
     left === 0. New: h === --rail-h read off :root, left === layout.last.titleW. The claim the
     assertion exists for - a band across the very top that never takes a press - is unchanged. */
  ok(trail.css.pe === 'none' && trail.css.top === 0 && trail.css.railH > 0 &&
     trail.css.h === trail.css.railH && trail.css.titleW > 0 &&
     Math.abs(trail.css.left - trail.css.titleW) <= 1,
     'a ' + trail.css.h + 'px header band across the very top, beside the ' + trail.css.titleW +
     'px title block, that CANNOT BE CLICKED: pointer-events none, so it never takes a press ' +
     'meant for the sky', JSON.stringify(trail.css));
  ok(/blur\(12px\)/.test(trail.css.blur) && trail.css.z === '6',
     'dark glass on the same blur as every other surface, at z-index 6 - under the panel ' +
     'and under the card', JSON.stringify({ blur: trail.css.blur, z: trail.css.z }));
  /* AGREEMENT, not plausibility. Each of the four is compared with the thing it claims to
     be reporting, read from somewhere else: two from the server over HTTP, one from the
     chip's own text node, one from the page's live web state. */
  const live0 = await (await fetch(GALAXY + '/health')).json();
  const vec0 = live0.vectors || {};
  const files0 = Number(vec0.files) || 0;
  ok((cells.archive || {}).text === files0 + (files0 === 1 ? ' file' : ' files') &&
     cells.archive.tone === (files0 ? 'local' : 'bad'),
     'ARCHIVE says what the SERVER says is indexed - ' + files0 + ' files - and says it in ' +
     'gold, because a file on this disk is local material',
     JSON.stringify({ cell: cells.archive, health: { files: vec0.files, ready: vec0.ready } }));
  const model0 = String((live0.say || {}).model || '').replace(/^[a-z]{2}_[A-Z]{2}-/, '');
  ok(/^(piper|web) · .+/.test((cells.voice || {}).text) &&
     (live0.say && live0.say.engine === 'piper'
       ? cells.voice.text === 'piper · ' + model0 && cells.voice.tone === 'local'
       : /^web · /.test(cells.voice.text)),
     'VOICE names the engine AND the voice, and on the local engine it is the model file ' +
     'the server is actually loading: ' + (cells.voice || {}).text,
     JSON.stringify({ cell: cells.voice, say: live0.say }));
  ok((cells.model || {}).text === trail.chip,
     'MODEL is the same brain the chip names - one reading, two places, no way to disagree',
     JSON.stringify({ rail: (cells.model || {}).text, chip: trail.chip }));
  const doors = ((live0.web || {}).backends) || [];
  ok(doors.length
       ? (cells.web.text === trail.web && /^(ready|throttled)$/.test(cells.web.text))
       : (cells.web.text === 'offline' && cells.web.tone === 'bad'),
     'WEB reports the door this config actually has: ' + (cells.web || {}).text +
     ' (' + (doors.length ? doors.join(', ') : 'no backends') + ')',
     JSON.stringify({ cell: cells.web, backends: doors }));
  ok(trail.ms === 10000,
     'and it re-reads /health every ' + (trail.ms / 1000) + 's, so an archive rebuilt in ' +
     'another window is a stale readout for seconds and not for the session', String(trail.ms));

  /* THE EMPTY ARCHIVE (Part 4 of the constitution). Forced through railFrom - the same
     door the ten-second poll goes through - and NOT by emptying the employer's index to
     see a colour. The claim is the colour and the survival: muted red, measured, and a
     renderer still drawing frames afterwards. */
  const errBefore = page.errors.length;
  const railSpin0 = await page.evaluate('__galaxy.planets.spins');
  const drained = await page.json(`(function(){
    __galaxy.rail.paint({vectors: {on: true, present: true, ready: true, files: 0, chunks: 0},
                         say: ${JSON.stringify(live0.say || {})},
                         web: {backends: ${JSON.stringify(doors)}}});
    var c = __galaxy.rail.cells;
    return {cell: c.archive, colour: getComputedStyle(
      document.querySelector('#rail-archive .rv')).color, nodes: __galaxy.nodes.length};
  })()`);
  note('forced empty: ' + JSON.stringify(drained.cell) + ' ' + drained.colour);
  ok(drained.cell.text === '0 files' && drained.cell.tone === 'bad',
     'AN EMPTY ARCHIVE SAYS SO: [ ARCHIVE: 0 FILES ], flagged as a fault rather than ' +
     'printed in the same grey as everything else', JSON.stringify(drained.cell));
  ok(/^rgba\(255,\s*107,\s*107,\s*0\.72\)$/.test(drained.colour),
     'in MUTED red - .72 alpha, measured off the browser, which reads as a fault without ' +
     'becoming an alarm', drained.colour);
  await sleep(700);
  const railSpin1 = await page.evaluate('__galaxy.planets.spins');
  ok(page.errors.length === errBefore && railSpin1 > railSpin0 &&
     drained.nodes > 0,
     'and the renderer did not so much as flinch: ' + (railSpin1 - railSpin0) +
     ' more frames of spin, no exception thrown',
     JSON.stringify({ errors: page.errors.slice(errBefore), spins: [railSpin0, railSpin1] }));
  /* Put the real numbers back, from a fresh reading, so nothing after this section is
     looking at a rail this section invented. */
  const live1 = await (await fetch(GALAXY + '/health')).json();
  await page.evaluate('__galaxy.rail.paint(' + JSON.stringify(live1) + ')');
  const restored = await page.json('__galaxy.rail.cells.archive');
  ok(restored.text === files0 + (files0 === 1 ? ' file' : ' files') && restored.tone === 'local',
     'then one real reading puts it back to ' + restored.text + ' - the forced state was a ' +
     'paint and nothing else', JSON.stringify(restored));

  /* ---- the organ rail, at rest ---- */
  const org = await page.json(`(function(){
    var st = __galaxy.organs.state, out = {};
    __galaxy.organs.ids.forEach(function (id) {
      var el = document.getElementById(id);
      out[id] = {title: el ? String(el.title || '') : null,
                 organ: st[id] ? st[id].organ : null};
    });
    return {ids: __galaxy.organs.ids, live: __galaxy.organs.live,
            paints: __galaxy.organs.paints, state: st, tips: out,
            reduce: matchMedia('(prefers-reduced-motion: reduce)').matches,
            beat: (function () {
              var found = [];
              for (var sh of document.styleSheets) {
                var rs; try { rs = sh.cssRules; } catch (e) { continue; }
                for (var r of rs) {
                  if (r.selectorText === '[data-organ="live"] .od') found.push(r.cssText);
                  if (r.media && String(r.media.mediaText).indexOf('reduced-motion') >= 0) {
                    for (var q of r.cssRules || []) {
                      if (q.selectorText === '[data-organ="live"] .od') found.push('@reduce ' + q.cssText);
                    }
                  }
                }
              }
              return found;
            })()};
  })()`);
  note('organ rail: ' + JSON.stringify(Object.keys(org.state || {}).map((k) =>
    k + '=' + ((org.state[k] || {}).organ || '?'))) + ' · live ' + org.live);
  /* SIX, AND THE SIXTH IS THE SCRIBE. This list is spelled out rather than counted on
     purpose - it is the tripwire that fires when a button is added to the markup and
     forgotten in ORGANS, which paints no dot and reports no state and therefore looks
     exactly like nothing being wrong. #scribebtn joined it in the same commit that added
     the button, which is the only way this assertion is worth keeping. */
  ok(JSON.stringify(org.ids) ===
     JSON.stringify(['screen', 'eye', 'focusbtn', 'scribebtn', 'mic', 'reset']),
     'THE ORGAN RAIL IS THE SIX BUTTONS ON THE BAR: #screen #eye #focusbtn #scribebtn ' +
     '#mic #reset, under the ids every other harness in this repo already clicks',
     JSON.stringify(org.ids));
  const dots = org.ids.every((id) => org.state[id] && org.state[id].dot);
  ok(dots, 'each one carries a state dot', JSON.stringify(org.state));
  const lines = org.ids.filter((id) => !(org.state[id] || {}).line);
  ok(lines.length === 0,
     'and a state line in its tooltip, on every one of the six',
     'no line on: ' + JSON.stringify(lines));
  const twoLine = org.ids.filter((id) =>
    String((org.tips[id] || {}).title || '').split('\n').length !== 2);
  ok(twoLine.length === 0,
     'the tooltip is the markup’s own sentence PLUS the state - two lines, so the ' +
     'designer’s description of what the button is for is never overwritten',
     'not two lines: ' + JSON.stringify(twoLine.map((id) => [id, org.tips[id].title])));
  /* THE HALF THAT IS EASY TO GET WRONG, and the one the constitution is actually about:
     the dot is a state, not an ornament. Nothing is running here - no share, no camera, no
     session, no microphone - so no organ may read live and NOTHING may pulse. The greeting
     is on screen, which makes #reset legitimately HELD, and that is the distinction being
     checked rather than waved at: a held organ shows a still dot, and only a live one
     beats. lit is read off the computed opacity and beating off the computed animation, so
     both are what the eye gets rather than what the attribute intended. */
  const wrongLit = org.ids.filter((id) => {
    const s = org.state[id] || {};
    return s.lit !== (s.organ === 'held' || s.organ === 'live');
  });
  const beating = org.ids.filter((id) => (org.state[id] || {}).beating);
  ok(org.live === 0 && beating.length === 0 && wrongLit.length === 0,
     'AT REST NOTHING PULSES: no organ is live, so no dot beats - and the one thing that ' +
     'IS true, a conversation there to forget, shows as a STILL dot on #reset',
     JSON.stringify({ live: org.live, beating, wrongLit, state: org.state }));
  /* The shorthand serialises as "animation: auto ease 0s 1 normal none running none", so
     what is matched is the animation NAME at the end of it rather than the word none, which
     appears in the fill-mode of the running rule as well. */
  ok(org.beat.some((t) => /running organbeat/.test(t)) &&
     org.beat.some((t) => /^@reduce/.test(t) && /running none/.test(t)),
     'the pulse is spent only on data-organ="live", and a reader who asked for less motion ' +
     'gets the dot without it', JSON.stringify(org.beat));

  /* ---- the command panel, by the real key ---- */
  const ctrlK = async () => {
    for (const type of ['keyDown', 'keyUp']) {
      await page.send('Input.dispatchKeyEvent', {
        type, key: 'k', code: 'KeyK', windowsVirtualKeyCode: 75,
        nativeVirtualKeyCode: 75, modifiers: 2 });
    }
  };
  const escape = async () => {
    for (const type of ['keyDown', 'keyUp']) {
      await page.send('Input.dispatchKeyEvent', {
        type, key: 'Escape', code: 'Escape', windowsVirtualKeyCode: 27,
        nativeVirtualKeyCode: 27 });
    }
  };
  await ctrlK();
  ok(await waitFor(page, '__galaxy.cmd.open === true', 3000),
     'A REAL CTRL+K SUMMONS THE COMMAND PANEL: dispatched through the browser’s key ' +
     'queue, not by calling the handler');
  await sleep(450);                       // the 300ms entrance lands before it is measured
  const sheet = await page.json(`(function(){
    var el = document.getElementById('cmd'), s = getComputedStyle(el);
    var r = el.getBoundingClientRect();
    var bar = document.getElementById('bar').getBoundingClientRect();
    var lab = document.querySelector('#cmd .cmdact .cl');
    var st = document.querySelector('#cmd .cmdact .cs');
    return {rows: __galaxy.cmd.rows, ids: __galaxy.cmd.ids, view: __galaxy.cmd.view,
            opens: __galaxy.cmd.opens,
            count: document.querySelectorAll('#cmd-list .cmdact').length,
            css: {trans: s.transitionProperty, ms: s.transitionDuration,
                  ease: s.transitionTimingFunction, z: s.zIndex,
                  blur: s.backdropFilter || s.webkitBackdropFilter, tx: s.transform,
                  o: s.opacity, pe: s.pointerEvents},
            mono: {label: lab ? getComputedStyle(lab).fontFamily : '',
                   state: st ? getComputedStyle(st).fontFamily : ''},
            box: {x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width),
                  h: Math.round(r.height), bottom: Math.round(r.bottom)},
            barTop: Math.round(bar.top),
            railBottom: Math.round(
              document.getElementById('toprail').getBoundingClientRect().bottom),
            hidden: el.getAttribute('aria-hidden')};
  })()`);
  const rows = sheet.rows || {};
  note('orders: ' + Object.keys(rows).map((k) => k + ' "' + (rows[k] || {}).label + '" · ' +
    (rows[k] || {}).line).join(' | '));
  /* EIGHT ORDERS NOW, AND IN THIS ORDER. The presence was the sixth act added to this
     sheet - the only way to change the hologram's mode by hand - and it sits after `links`
     because the sheet reads outward from the session: what you are doing, where, what you
     can see, what is looking back, what it knows, WHAT IT CAN REACH, how it sounds.
     `google` is the seventh and it went between `archive` and `cast` for that reading: the
     archive is what this machine holds, the grant is what it can touch outside the house,
     and the voice is how it tells you about either. The list is asserted whole rather than
     by length so that an order appearing, disappearing or MOVING is a failure with a name
     in it - which is exactly what caught this assertion when the seventh arrived, and again
     when the eighth did.

     `voice` IS THE EIGHTH AND IT IS LAST FOR A REASON THAT IS NOT ALPHABETICAL. Learning a
     voiceprint is the only order on this sheet that is boss-only, and the guard is
     STRUCTURAL rather than a check: no sentence anywhere in the funnel reaches that action,
     so the only way to start an enrolment is to press this row - which is a keystroke, and
     the keyboard is the boss's door. It sits after `cast` because the reading ends where the
     sheet's trust does: everything above is something the house does, and this is the house
     being told whose voice it works for. */
  /* AND NOW THERE ARE TEN, because two of them open a BOARD rather than doing a thing, and
     each one sits directly under the order it is the wide reading of. `connectors` goes
     between `google` and `cast`: the Google row is one grant with one verb, and the board
     behind this row is every reach the house has - the grant, the hands, the voice, the eyes
     and the Scribe - so it belongs where "what it can reach" already was, one line wider.
     `clock` goes between `cast` and `voice` for the same rule and for one more: it is the
     only row on the sheet that reports a fact about the world rather than about this machine,
     and it stops short of `voice` because the boss-only order stays last, as it has since it
     arrived. A board row is still an ORDER - it has a label, a state line and a keystroke -
     so it is asserted in this list rather than beside it, and the list is still whole rather
     than counted, so a row appearing, vanishing or MOVING is a failure with a name in it. */
  /* AND NOW ELEVEN, because the Census is the third board. It goes between `clock` and
     `voice`, which is the same rule applied a third time and one new one: every row above it
     TELLS him something - what he is doing, what it can see, what it can reach, what time it
     is somewhere else - and this is the only row on the sheet that ASKS HIM FOR SOMETHING.
     That is why it cannot go first: a sheet whose opening line wanted an answer out of him
     would be an order sheet that took orders. And `voice` still ends the sheet, because the
     boss-only order has been last since it arrived and a list that reshuffles when a feature
     lands is a list nobody can read the argument off. */
  ok(JSON.stringify(sheet.ids) ===
     JSON.stringify(['focus', 'lock', 'links', 'presence', 'archive', 'google', 'connectors',
                     'cast', 'clock', 'census', 'voice']) && sheet.count === 11,
     'ELEVEN DIEGETIC ORDERS, and they are the eleven the constitution lists: start focus, ' +
     'lock ' +
     'the tab, simplify the links, change the presence, open the archive, connect Google, ' +
     'read the connectors, cast the voice, read the world clock, sit the Census, learn a voice',
     JSON.stringify({ ids: sheet.ids, rendered: sheet.count }));
  const dumb = sheet.ids.filter((id) => !rows[id] || !rows[id].label || !rows[id].line ||
                                        !rows[id].shown);
  ok(dumb.length === 0,
     'every order carries a label AND a line that reports the state of the organ behind it',
     'silent rows: ' + JSON.stringify(dumb.map((id) => [id, rows[id]])));
  ok(/mono/i.test(sheet.mono.state) && !/mono/i.test(sheet.mono.label),
     'mono for the state lines and the reading type for the labels - the instrument speaks ' +
     'in mono and the order speaks in English', JSON.stringify(sheet.mono));
  ok(/blur\(12px\)/.test(sheet.css.blur) && sheet.css.z === '10' && sheet.css.o === '1' &&
     sheet.css.pe === 'auto' && sheet.hidden === 'false',
     'dark glass, at z-index 10 - under the countdown card at 12, and pressable while open',
     JSON.stringify({ blur: sheet.css.blur, z: sheet.css.z, hidden: sheet.hidden }));
  ok(sheet.box.x === 0 && sheet.box.y === sheet.railBottom && sheet.box.bottom < sheet.barTop,
     'it hangs from the telemetry rail down the left wall and STOPS SHORT OF THE ASK BAR: ' +
     'bottom ' + sheet.box.bottom + 'px, bar at ' + sheet.barTop + 'px',
     JSON.stringify({ box: sheet.box, barTop: sheet.barTop }));
  /* THE MOTION LANGUAGE AGAIN, on the one surface that arrives from off-screen, where an
     overshoot would be visible as a bounce against the edge of the window. Asserted the
     same way as the panel's: the arithmetic first, the named curve second. */
  const ceases = String(sheet.css.ease).match(/cubic-bezier\([^)]*\)/g) || [];
  const springs = ceases.map((s) => {
    const m = /cubic-bezier\(([^)]+)\)/.exec(s);
    const p = m ? m[1].split(',').map(Number) : null;
    return p && p.length === 4 && p.every((n) => isFinite(n)) ? p : null;
  });
  ok(sheet.css.trans === 'opacity, transform' && /^0\.3s(, 0\.3s)?$/.test(sheet.css.ms),
     'and it enters on opacity and transform alone, both capped at 300ms - nothing that ' +
     'costs a layout', JSON.stringify({ property: sheet.css.trans, duration: sheet.css.ms }));
  ok(springs.length === 2 && springs.every((p) => p && p[1] <= 1 && p[3] <= 1 &&
                                                 p[1] >= 0 && p[3] >= 0),
     'on a curve that SETTLES: every control-point y inside [0,1], so the sheet cannot ' +
     'slide past the wall and come back', JSON.stringify(springs));
  ok(ceases.length === 2 &&
     ceases.every((s) => /cubic-bezier\(0\.16,\s*1,\s*0\.3,\s*1\)/.test(s)),
     'and it is the one curve the constitution names, on both properties: ' +
     'cubic-bezier(0.16, 1, 0.3, 1)', JSON.stringify(ceases));

  /* THE ORDERS PRESS THE REAL CONTROLS. The links order is the one that can be proved
     without a session, a camera or a microphone: it flips the graph itself, so the claim
     is checked against the number of links THE GRAPH IS DRAWING and not against the row's
     own account of what it did. Twice, because a switch that only goes one way is a
     button that broke halfway. */
  const linksNow = async () => await page.json(`({label: __galaxy.cmd.rows.links.label,
    line: __galaxy.cmd.rows.links.line, drawn: __galaxy.Graph.graphData().links.length,
    all: __galaxy.allLinks.length, strong: __galaxy.strongLinks.length,
    open: __galaxy.cmd.open})`);
  const l0 = await linksNow();
  await page.evaluate('__galaxy.cmd.run("links")', true);
  await sleep(500);
  const l1 = await linksNow();
  await page.evaluate('__galaxy.cmd.run("links")', true);
  await sleep(500);
  const l2 = await linksNow();
  note('links: ' + [l0, l1, l2].map((l) => l.label + ' (' + l.drawn + ' drawn)').join(' -> '));
  ok(l0.drawn === l0.strong && l1.drawn === l1.all && l2.drawn === l2.strong,
     'SIMPLIFY LINKS PRESSES THE REAL CONTROL: the graph went ' + l0.drawn + ' -> ' +
     l1.drawn + ' -> ' + l2.drawn + ' links, which is the strong subset, all of them, ' +
     'and back',
     JSON.stringify({ drawn: [l0.drawn, l1.drawn, l2.drawn], all: l0.all, strong: l0.strong }));
  /* THE LABEL NAMES THE PRESS, NOT THE STATE. On a graph already thinned to the strong
     subset the order reads "Show Every Link", because a row saying "Simplify Links" over an
     already-simplified galaxy is a button that does the opposite of its word. */
  ok(l0.label === 'Show Every Link' && l1.label === 'Simplify Links' &&
     l2.label === 'Show Every Link',
     'and the order RENAMES ITSELF to what pressing it would do next, rather than naming ' +
     'the state it is already in', JSON.stringify([l0.label, l1.label, l2.label]));
  ok(l1.open === true && l2.open === true,
     'and the sheet stays open across it, because thinning a graph is something you look at',
     JSON.stringify({ after1: l1.open, after2: l2.open }));

  /* THE CASTING VIEW. Three candidates, and the line they speak has to be the SERVER's
     constant - if this file typed the sentence itself, the audition and config.json could
     drift apart and every check here would still pass. Nothing is auditioned: the FIFO and
     the sound belong to voice_proof, and this is the deck. */
  const voices = await (await fetch(GALAXY + '/voices')).json();
  await page.evaluate('__galaxy.cmd.cast.open()', true);
  await sleep(900);
  const casting = await page.json(`(function(){
    return {view: __galaxy.cmd.view, offline: __galaxy.cmd.cast.offline,
            state: __galaxy.cmd.cast.state,
            line: (document.getElementById('cast-line').textContent || '').trim(),
            warn: (document.getElementById('cast-warn').textContent || '').trim(),
            names: Array.prototype.map.call(
              document.querySelectorAll('#cast-list .cand'), function (c) {
                return (c.getAttribute('data-model') || '');
              }),
            chosen: document.querySelectorAll('#cast-list .cand.chosen').length,
            buttons: document.querySelectorAll('#cast-list .cand button').length};
  })()`);
  note('casting: ' + JSON.stringify({ view: casting.view, names: casting.names,
                                      chosen: casting.chosen, offline: casting.offline }));
  const wanted = (voices.candidates || []).map((c) => c.model);
  ok(casting.view === 'cast' && casting.names.length === wanted.length &&
     wanted.every((m, i) => casting.names[i] === m),
     'VOICE CASTING lists the candidates the SERVER names, in the server’s order: ' +
     wanted.join(', '), JSON.stringify({ shown: casting.names, server: wanted }));
  ok(!!voices.line && casting.line.indexOf(String(voices.line)) >= 0,
     'and the sentence they audition is the server’s own constant, printed rather than ' +
     'retyped here: ' + JSON.stringify(casting.line),
     JSON.stringify({ shown: casting.line, server: voices.line }));
  ok(voices.piper === true
       ? (casting.offline === false && casting.warn === '' && casting.chosen === 1)
       : (casting.offline === true && /piper offline/i.test(casting.warn)),
     voices.piper
       ? 'piper is installed, so there is no offline banner and the voice in config.json is ' +
         'marked as the one already kept'
       : 'PIPER IS ABSENT, and the panel says so - "Piper Offline — Web Fallback" - ' +
         'instead of offering three dead candidates',
     JSON.stringify({ piper: voices.piper, offline: casting.offline, warn: casting.warn }));
  await page.evaluate('__galaxy.cmd.view_("list")', true);
  await sleep(300);
  ok(await page.evaluate('__galaxy.cmd.view') === 'list',
     'and Back returns to the rest of the orders');

  /* ESCAPE, by the real key. It closes the sheet and NOTHING ELSE: the page has always
     bound Escape to clearing a selection, and a sheet that also wiped the note you were
     reading would be a shortcut you learn not to use. */
  await escape();
  ok(await waitFor(page, '__galaxy.cmd.open === false', 3000),
     'a real Escape dismisses it');

  /* ---- Part 4: a sheet open while the camera is being asked to move ----
     LIVENESS FIRST, and it is not a formality. Every claim here is about counters that only
     move while the page's one animation loop is running, so "the camera did not move" and
     "nothing is running" produce identical numbers - and the second of those would let a
     frozen tab pass this section for the worst possible reason. So the loop is proved to be
     turning, on its own counters and on the planets' spin, before its stillness is read as
     a decision. */
  const beat = async () => await page.json('({moves: __galaxy.camera.parallax.moves,' +
    ' holds: __galaxy.camera.parallax.holds, suspended: __galaxy.camera.parallax.suspended,' +
    ' spins: __galaxy.planets.spins, fps: __galaxy.deck.fps})');
  await page.evaluate('__galaxy.camera.look(0.25, 0.25)');
  await sleep(900);
  const beatA = await beat();
  await sleep(900);
  const beatB = await beat();
  ok(beatB.holds + beatB.moves > beatA.holds + beatA.moves && beatB.spins > beatA.spins,
     'the loop is turning and the parallax is being asked on every frame of it: +' +
     (beatB.holds - beatA.holds) + ' holds, +' + (beatB.moves - beatA.moves) + ' moves, +' +
     (beatB.spins - beatA.spins) + ' frames of spin in 900ms',
     JSON.stringify({ a: beatA, b: beatB }));
  await page.evaluate('__galaxy.camera.look(1, 1)');
  await sleep(1200);
  const par0 = await beat();
  ok(par0.moves > beatB.moves && par0.suspended === false,
     'and with nothing open the pointer reaches it: ' + (par0.moves - beatB.moves) +
     ' moves after the pointer went to the corner', JSON.stringify(par0));
  await ctrlK();
  const summoned = await waitFor(page, '__galaxy.cmd.open === true', 3000);
  /* THE BASELINE FOR "NOTHING WAS ASKED" IS TAKEN AFTER THE SHEET IS OPEN, and the reason is
     a boundary this assertion used to lose a run to. `holds` counts frames on which the
     parallax was asked and declined, and Ctrl-K is not instantaneous: between par0 being
     read and cmd.open going true the loop draws a frame or two in which the sheet is not yet
     open, the pointer is still at the far corner, and the camera legitimately declines it.
     Those holds belong to the UNSUSPENDED page and counting them against the suspension was
     measuring the keystroke's latency, not the behaviour.
     `moves` is still read against par0, because that one has no boundary to lose: a camera
     that eased even one frame's worth toward the corner after the sheet was summoned is the
     drift this whole section exists to forbid, whichever side of the open it happened on. */
  const parS = await beat();
  /* The pointer keeps arriving while the sheet is open - the OPPOSITE corner, so there is a
     real difference for the camera to refuse rather than a still mouse to coast on. */
  await page.evaluate('__galaxy.camera.look(-1, -1)');
  await sleep(1400);
  const par1 = await beat();
  note('parallax under the sheet: suspended ' + par1.suspended + ' · moves ' +
       par0.moves + ' -> ' + par1.moves + ' · holds +' + (par1.holds - parS.holds) +
       ' (+' + (parS.holds - par0.holds) + ' across the keystroke itself) · spins +' +
       (par1.spins - par0.spins));
  ok(summoned && par1.suspended === true,
     'THE PARALLAX SUSPENDS WHILE THE SHEET IS OPEN - the flag is written on every frame, ' +
     'so a panel summoned by a key is honoured on the next frame and not on the next mouse ' +
     'move', JSON.stringify({ open: summoned, par: par1 }));
  ok(par1.moves === par0.moves && par1.holds === parS.holds,
     'and the camera is FROZEN rather than eased: the pointer was taken to the opposite ' +
     'corner and for 1.4s of open sheet neither counter moved - not one ease and not one ' +
     'poll, because WANTED is dragged up to NOW instead of being followed',
     JSON.stringify({ moves: [par0.moves, par1.moves],
                      holds: [par0.holds, parS.holds, par1.holds] }));
  ok(par1.spins - par0.spins > 30,
     'and it is a DECISION and not a dead page: the sky itself turned ' +
     (par1.spins - par0.spins) + ' more frames while the camera declined to move',
     JSON.stringify({ spins: [par0.spins, par1.spins], fps: par1.fps }));
  await page.shot('deck-command.png');
  note('wrote deck-command.png (the order sheet under the telemetry rail)');
  await escape();
  ok(await waitFor(page, '__galaxy.cmd.open === false', 3000),
     'Escape dismisses it again, with the camera mid-lean');
  await sleep(900);
  const par2 = await beat();
  ok(par2.suspended === false && (par2.holds > par1.holds || par2.moves > par1.moves),
     'and the give comes back the moment the sheet is gone - suspended is a state, not a ' +
     'one-way door', JSON.stringify({ par1, par2 }));
  await page.evaluate('__galaxy.camera.look(0, 0)');
  await sleep(1200);

  /* ---- 5. THE HANDS GATE, DIMMED, AND STILL CLICKABLE -------------------- */
  /* Summoned with the slash, because there is no standing field to focus any more. */
  for (const t of ['keyDown', 'char', 'keyUp']) {
    await page.send('Input.dispatchKeyEvent', { type: t, key: '/', code: 'Slash',
      text: '/', unmodifiedText: '/', windowsVirtualKeyCode: 191,
      nativeVirtualKeyCode: 191 });
  }
  await sleep(150);
  ok(await page.evaluate('__galaxy.typeLine.up && __galaxy.typeLine.focused'),
     'pressing / summons the type-line and gives it the keyboard');
  await page.send('Input.insertText', { text: 'remind me to call the client at four' });
  for (const type of ['keyDown', 'keyUp']) {
    await page.send('Input.dispatchKeyEvent', {
      type, key: 'Enter', code: 'Enter', windowsVirtualKeyCode: 13,
      nativeVirtualKeyCode: 13, text: type === 'keyDown' ? '\r' : undefined });
  }
  const proposed = await waitFor(page, '__galaxy.hands.shown === true', 90000);
  ok(proposed, 'an instruction raises the Yes/No pair');
  if (proposed) {
    /* THE TYPEWRITER, caught in the act. The proposal line is long enough to be typed,
       and this is the sample that matters: mid-reveal, the card already holds every
       word. Sampled at once, in one evaluate, so the two numbers are from one instant. */
    const mid = await page.json('({lit: __galaxy.type.lit, total: __galaxy.type.total,' +
      ' typing: __galaxy.type.typing, chars: __galaxy.type.text.length,' +
      ' line: (__galaxy.hands.pending || {}).line})');
    note('typewriter: ' + JSON.stringify({ lit: mid.lit, total: mid.total, chars: mid.chars }));
    if (mid.total > 0 && mid.typing) {
      ok(mid.chars === mid.total && mid.lit < mid.total,
         'THE ANSWER IS COMPLETE BEFORE IT IS REVEALED: ' + mid.lit + ' of ' + mid.total +
         ' characters lit, and all ' + mid.chars + ' already readable in the DOM',
         JSON.stringify(mid));
    } else {
      note('the reveal had already finished by the time we looked (' + mid.total +
           ' chars) - the completeness check below covers the same claim');
    }
    ok(typeof mid.line === 'string' && mid.line.length > 0 &&
       (await page.evaluate('__galaxy.type.text')).indexOf(mid.line) >= 0,
       'and what the card holds is the server\u2019s own proposal sentence, whole');

    /* The vignette fades in over 220ms. Waited for rather than slept past, so the claim
       below is "it reached full dim" and not "it was dim when we happened to look" - and
       if it never arrives, the trace says whether the class was missing or the transition
       simply never advanced, which are two completely different bugs. */
    const dimmed = await waitFor(page,
      'getComputedStyle(document.getElementById("handswash")).opacity === "1"', 3000);
    const wash = await page.json('(function(){var s=getComputedStyle(' +
      'document.getElementById("handswash"));return {pe: s.pointerEvents, o: s.opacity,' +
      ' prop: s.transitionProperty, ms: s.transitionDuration, live:' +
      ' document.getElementById("handswash").classList.contains("live")};})()');
    note('vignette: ' + JSON.stringify(wash));
    if (!dimmed) {
      const stuck = await page.json(`(function(){
        var el = document.getElementById('handswash');
        var out = [];
        for (var sh of document.styleSheets) {
          var rs; try { rs = sh.cssRules; } catch (e) { continue; }
          for (var r of rs) if (r.selectorText === '#handswash.live') out.push(r.cssText);
        }
        return {rule: out, anims: (el.getAnimations ? el.getAnimations().length : -1),
                reduce: matchMedia('(prefers-reduced-motion: reduce)').matches,
                nomove: document.documentElement.className,
                hidden: document.hidden, vis: document.visibilityState};
      })()`);
      note('NOT DIM after 3s - the shape of it: ' + JSON.stringify(stuck));
    }
    ok(wash.live === true && wash.o === '1', 'the room dims while a hand is being offered');
    ok(wash.pe === 'none',
       'THE DIMMING CANNOT BLOCK A CLICK: pointer-events none on a full-screen overlay',
       JSON.stringify(wash));
    ok(wash.prop === 'opacity',
       'and it dims by opacity alone - no shadow, no size, nothing that costs a layout',
       JSON.stringify({ property: wash.prop, duration: wash.ms }));
    const ring = await page.json('(function(){var s=getComputedStyle(' +
      'document.getElementById("answer"), "::after");return {pe: s.pointerEvents,' +
      ' anim: s.animationName, ms: s.animationDuration};})()');
    ok(ring.pe === 'none' && ring.anim === 'urgent',
       'the urgent gold/cyan ring pulses AROUND the buttons without covering them',
       JSON.stringify(ring));
    const gate = await page.json('(function(){var s=getComputedStyle(' +
      'document.getElementById("a-ask"));return {anim: s.animationName, ms: s.animationDuration};})()');
    ok(gate.anim === 'gate' && parseFloat(gate.ms) <= 0.1,
       'the card arrives in ' + gate.ms + ' - under the 100ms a headless hand can wait ' +
       'for a rectangle to stop moving', JSON.stringify(gate));

    /* THE DECISIVE CHECK, and the reason every overlay on this page is unclickable. */
    const overYes = await topOf(page, 'ask-yes');
    const overNo = await topOf(page, 'ask-no');
    ok(overYes === 'itself', 'the middle of Yes is Yes - nothing is on top of it', overYes);
    ok(overNo === 'itself', 'the middle of No is No', overNo);
    const yesGlow = await page.json('(function(){var s=getComputedStyle(' +
      'document.getElementById("ask-yes")), n=getComputedStyle(' +
      'document.getElementById("ask-no"));return {yes: s.backgroundImage.slice(0,18),' +
      ' yesShadow: s.boxShadow !== "none", noBg: n.backgroundColor,' +
      ' yesFont: getComputedStyle(document.getElementById("ask-rows")).fontFamily};})()');
    ok(/gradient/.test(yesGlow.yes) && yesGlow.yesShadow === true &&
       /rgba\(0, 0, 0, 0\)|transparent/.test(yesGlow.noBg),
       'Yes is solid and glowing, No is ghosted - the two answers do not look alike',
       JSON.stringify(yesGlow));
    ok(/JetBrains Mono/i.test(yesGlow.yesFont),
       'and the parameters are set in JetBrains Mono, so a subject line reads as data',
       yesGlow.yesFont);

    await page.shot('deck-gate.png');
    note('wrote deck-gate.png (the dimmed deck and the gold gate)');

    /* ---- 6. REDUCED MOTION IS HONOURED ---------------------------------- */
    await page.send('Emulation.setEmulatedMedia',
      { features: [{ name: 'prefers-reduced-motion', value: 'reduce' }] });
    await sleep(200);
    const still = await page.json('(function(){return {' +
      ' ring: getComputedStyle(document.getElementById("answer"), "::after").animationName,' +
      ' gate: getComputedStyle(document.getElementById("a-ask")).animationName,' +
      ' wash: getComputedStyle(document.getElementById("handswash")).transitionDuration,' +
      ' ch: getComputedStyle(document.getElementById("a-text")).opacity};})()');
    ok(still.ring === 'none' && still.gate === 'none' && parseFloat(still.wash) === 0,
       'asked for less motion, the gate stops moving entirely - and still says everything ' +
       'it said before', JSON.stringify(still));
    await page.send('Emulation.setEmulatedMedia', { features: [] });
    await sleep(200);

    /* ---- 7. A REAL HAND ON NO ------------------------------------------- */
    const box = await page.json('(function(){var r=document.getElementById("ask-no")' +
      '.getBoundingClientRect();return {x:Math.round(r.left+r.width/2),' +
      'y:Math.round(r.top+r.height/2)};})()');
    for (const type of ['mousePressed', 'mouseReleased']) {
      await page.send('Input.dispatchMouseEvent',
        { type, x: box.x, y: box.y, button: 'left', clickCount: 1 });
    }
    ok(await waitFor(page, '__galaxy.hands.pending === null', 15000),
       'a real mouse event at the middle of No is REFUSED THROUGH THE SERVER, animations ' +
       'and dimming and all');
    ok(await page.evaluate(
       'document.getElementById("handswash").classList.contains("live") === false'),
       'and the room comes back up when the question goes away');
  }

  /* ---- 8. THE TONES, AND THE CAP --------------------------------------- */
  const audio = await page.json('({built: __galaxy.audio.built, gain: __galaxy.audio.gain,' +
    ' state: __galaxy.audio.state, ceiling: __galaxy.audio.CEILING,' +
    ' ducked: __galaxy.audio.ducked, duck: __galaxy.audio.DUCK,' +
    ' duckTo: __galaxy.audio.duckTo, speechBus: __galaxy.audio.speechBus,' +
    ' played: __galaxy.audio.played.map(function(t){return t.kind}),' +
    ' trouble: __galaxy.audio.trouble})');
  note('audio: ' + JSON.stringify(audio));
  ok(audio.built === true, 'the tone engine was built on a real gesture, with no mp3 ' +
     'anywhere', JSON.stringify(audio.trouble));
  /* THE CAP, AND THE DUCK UNDER IT. This check used to read the gain node against a flat
     0.15 - which was true until the chimes learned to stand back while the butler speaks.
     The claim now is the one that was always meant: the ceiling is 15% and the node is
     EITHER at it or at the ducked fraction of it, and never anywhere else and never above.
     Read as a pair, because a node at 0.03 with `ducked` false would be a leak and a node
     at 0.15 with `ducked` true would be a duck that did nothing. */
  const duckTo = +(audio.ceiling * audio.duck).toFixed(6);
  const atCeiling = audio.gain === audio.ceiling && audio.ducked === false;
  const atDuck = Math.abs(audio.gain - duckTo) < 1e-6 && audio.ducked === true;
  ok(audio.ceiling === 0.15 && (atCeiling || atDuck) && audio.duckTo === duckTo,
     'THE VOLUME IS CAPPED AT 15%, read back off the gain node rather than off the ' +
     'constant beside it - and the only other level it may hold is ' +
     Math.round(audio.duck * 100) + '% of that while the butler is speaking',
     JSON.stringify({ node: audio.gain, declared: audio.ceiling, ducked: audio.ducked,
                      duckTo: duckTo }));
  ok(audio.played.indexOf('wake') >= 0,
     'the wake chime sounded when the hand was offered: ' + JSON.stringify(audio.played));
  ok(audio.played.indexOf('no') >= 0, 'and the refusal had its own sound');

  /* ---- 9. THE BLOOM, FORCED - AND THEN TAKEN AWAY ---------------------- */
  /* The audition may well have refused the glow on this machine, and that is the page
     behaving correctly rather than a hole in the proof. So the glow is asked for by hand
     with ?bloom=1, which skips the audition and NOT the 45fps brake: one navigation gives
     both the picture of the bloom actually running and the only honest way to show the
     emergency guard firing. */
  note('reloading with ?bloom=1: the audition skipped, the brake still armed\u2026');
  await page.send('Page.navigate', { url: GALAXY + '/?bloom=1' });
  await sleep(1200);
  ok(await waitFor(page, '!!(window.__galaxy && __galaxy.deck)', 30000),
     'the page comes back up with the bloom forced');
  await waitFor(page, '__galaxy.nodes.length > 0', 20000);
  /* The navigation above ended the screencast, and the section below provokes the frame-rate
     guard on purpose - so it needs frames more than any other part of this file. */
  page.casting = false;
  try { await page.cast(true); } catch (e) { note('screencast: ' + e.message); }
  const forced = await waitFor(page, '__galaxy.deck.bloom === true', 20000);
  const fdeck = await page.json('({bloom: __galaxy.deck.bloom, res: __galaxy.deck.bloomRes,' +
    ' probation: __galaxy.deck.probation, why: __galaxy.deck.why,' +
    ' trouble: __galaxy.deck.trouble})');
  note('forced deck: ' + JSON.stringify(fdeck));
  ok(forced && fdeck.probation === 'forced',
     'THE BLOOM RUNS when it is asked for outright, at half resolution ' +
     JSON.stringify(fdeck.res), JSON.stringify(fdeck));
  if (forced) {
    await waitFor(page, '__galaxy.deck.frames > 120', 8000);
    await sleep(1500);
    note('bloom running at ' + (await page.evaluate('__galaxy.deck.fps')) + 'fps');
    await page.shot('deck-galaxy-bloom.png');
    note('wrote deck-galaxy-bloom.png (the galaxy with the glow on)');

    /* A BUSY THREAD, NOT A THROTTLE, AND THE THROTTLE IS WHY THIS COMMENT IS LONG.
       The brake's rule is three seconds with NO frame at or above the floor, reset by any
       single frame over it - deliberately, because one bad second is a flight or a rebuild
       and not a verdict about the glow. Emulation.setCPUThrottlingRate cannot produce that
       shape. It multiplies main-thread WORK, so it makes frames spiky rather than slow, and
       a spiky frame rate crosses the floor constantly.
       MEASURED, with a sampler on the judge's own reading, one row per frame (_runs/
       bloom_sag.log): at 20x the mean was 51.3fps, 86% of frames were at or over the floor,
       and the LONGEST CONTINUOUS SAG was 1450ms against a 3000ms grace. At 30x it was worse
       - 91% over the floor and a longest sag of 318ms - because leaning harder makes the
       stalls deeper, not longer. So the brake was right every time it did not fire, and the
       old ramp's own end-of-sleep reading (run 4: "held 25.9fps at 30x") was a snapshot of
       an instant, not a description of seven seconds. It read like a broken brake and was a
       lying measurement. That is the failure mode this provocation is built to avoid.
       WHAT DOES IT: a rAF hook of the harness's own that spins for a fixed number of
       milliseconds and then asks for the next frame. That pins the frame rate flat - burn
       30ms and the page holds 31.5fps with ONE crossing of the floor in nine seconds - which
       is exactly the machine the guard exists for, and the judge measures the page's frame
       rate without caring why it sagged. The burn stays well under the judge's 2000ms
       "the browser suspended us" ceiling: a frame that long is not counted at all, so a
       heavier hand than this would silence the very judge it is trying to convict.
       THE RAMP SURVIVES, and 18ms is in it on purpose: it lands at ~50fps, above the floor,
       so the first rung asserts by omission that the brake does NOT fire on a page that is
       merely busy. AND THE WAIT IS A SLEEP, NOT A POLL - waitFor would ask the page a
       question every few hundred milliseconds, and answering one while the thread is
       saturated is itself a long frame. The harness would interrupt the sag it is waiting
       for. So: lean, go quiet for longer than the grace, then ask once. */
    let dropped = false;
    const burnOn = (ms) => page.evaluate('(function(){window.__burn=' + ms + ';' +
      'if (window.__burning) return "already"; window.__burning = true;' +
      '(function spin(){ if (!window.__burning) return;' +
      ' var until = performance.now() + window.__burn;' +
      ' while (performance.now() < until) {}' +
      ' requestAnimationFrame(spin); })(); return "burning";})()');
    for (const burn of [18, 30, 45]) {
      note('holding the main thread busy ' + burn + 'ms a frame to sag the frame rate below ' +
           '45 and keep it there\u2026');
      await burnOn(burn);
      await sleep(7000);
      const sag = await page.json('({bloom: __galaxy.deck.bloom, fps: __galaxy.deck.fps})');
      if (sag.bloom === false) {
        dropped = true;
        note('the brake fired at ' + burn + 'ms a frame (' + sag.fps + 'fps)');
        break;
      }
      note('held ' + sag.fps + 'fps at ' + burn + 'ms a frame - above the floor, so leaning ' +
           'harder');
    }
    await page.evaluate('window.__burning = false; "stopped"');
    await sleep(1200);
    const why = await page.evaluate('__galaxy.deck.why');
    ok(dropped, 'THE BLOOM DISABLES ITSELF when the frame rate cannot hold the floor: ' +
       JSON.stringify(why));
    ok(/fps/.test(String(why)),
       'and it records the frame rate it saw, so the reason is readable afterwards', why);
    await sleep(1500);
    const after = await page.evaluate('__galaxy.deck.fps');
    note('with the bloom gone and the throttle off: ' + after + 'fps');
    ok(await page.evaluate('__galaxy.deck.stars === "webgl"'),
       'and the galaxy itself survived losing the glow - the stars are still drawn');
  } else {
    note('the bloom could not be forced (' + (fdeck.why || fdeck.trouble || '?') +
         '), so the guard is exercised through its own entry point instead');
    const why = await page.evaluate('__galaxy.deck.drop("proof")');
    ok(typeof why === 'string', 'the drop path is callable and answers with a reason', why);
  }
  ok(await page.evaluate('__galaxy.deck.DECK.FPS_FLOOR === 45 && ' +
     '__galaxy.deck.DECK.FPS_GRACE_MS === 3000'),
     'the floor is 45fps held for 3 seconds, as specified');

  page.close();
}

main().catch((e) => { bad.push('the run itself: ' + e.message); console.log('\n  ERROR ' + e.message); })
  .finally(async () => {
    /* HIS OWN SKY BACK, AND SAID OUT LOUD. First, before the browsers are even closed: a
       run that dies here leaves the galaxy showing a fictional cafe, and the one thing worse
       than that is leaving it there quietly. */
    if (swapped) {
      const back = buildFrom('');
      const now = graphCounts();
      ok(back.code === 0 && now.root === 'notes' && now.nodes > 0,
         'and his own collection is back in the galaxy, built from ' + now.root + ': ' +
         now.nodes + ' worlds, ' + now.links + ' relations' +
         (now.nodes === swapped.nodes ? '' :
          ' (it was ' + swapped.nodes + ' when this run began - he filed one while it ran)'),
         JSON.stringify({ exit: back.code, was: swapped, now: now,
                          fix: 'run: python build.py' }));
    }
    procs.forEach(p => { try { process.kill(p.pid); } catch { } });
    await sleep(600);
    profiles.forEach(p => { try { rmSync(p, { recursive: true, force: true }); } catch { } });
    console.log('\n  VERIFY ' + (checks - bad.length) + '/' + checks +
                (bad.length ? ' FAIL' : ' PASS') + '\n');
    bad.forEach(b => console.log('    FAILED: ' + b));
    process.exit(bad.length ? 1 : 0);
  });
