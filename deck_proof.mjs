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
import { spawn } from 'node:child_process';
import { mkdtempSync, rmSync, existsSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

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
const PLANET_EMISSIVE_HOT = 0.4;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

let checks = 0; const bad = [];
const ok = (c, claim, detail) => {
  checks++; console.log((c ? '  ok   ' : '  FAIL ') + claim);
  if (!c) { bad.push(claim); if (detail) console.log('         ' + detail); }
};
const note = (m) => console.log('  note ' + m);
const procs = []; const profiles = [];

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
  async shot(file) {
    const r = await this.send('Page.captureScreenshot', { format: 'png' });
    const data = r.result && r.result.data;
    if (!data) throw new Error('no screenshot came back');
    writeFileSync(file, Buffer.from(data, 'base64'));
    return file;
  }
  close() { try { this.ws.close(); } catch { } }
}
const cdp = async (p) => { const r = await fetch(CDP + p); const t = await r.text();
  try { return JSON.parse(t); } catch { return t; } };

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

  /* ---- 1b. THE PLANETARIUM: WORLDS, NOT DOTS -----------------------------
     Three claims, and the third is the only one a screenshot could not settle.
       - every note is a four-part world with its own 512x256 canvas of its own text;
       - the hubs wear rings, recounted here from the link data rather than believed;
       - NOTHING IS BUILT AFTER BOOT. builds is read now and read again after the
         five-second recording, and if it moved, a texture was rasterised inside a frame. */
  ok(await waitFor(page, '__galaxy.planets.on === true', 12000),
     'the planetarium booted: the node spheres are THREE.Groups now',
     JSON.stringify(await page.evaluate('__galaxy.planets.why')));
  const pl = await page.json('({on: __galaxy.planets.on, why: __galaxy.planets.why,' +
    ' count: __galaxy.planets.count, builds: __galaxy.planets.builds,' +
    ' textures: __galaxy.planets.textures, chars: __galaxy.planets.textChars,' +
    ' ringed: __galaxy.planets.ringed, spins: __galaxy.planets.spins,' +
    ' paints: __galaxy.planets.paints, nodes: __galaxy.nodes.length})');
  note('planets: ' + JSON.stringify(pl));
  ok(pl.count === pl.nodes && pl.builds === pl.nodes,
     'one world per note, built exactly once each (' + pl.builds + ' builds for ' +
     pl.nodes + ' notes)', JSON.stringify(pl));
  ok(pl.textures === pl.nodes && pl.chars > pl.nodes * 100,
     'and every surface carries REAL TEXT from its own file - ' + pl.chars +
     ' characters drawn across ' + pl.textures + ' canvases',
     JSON.stringify({ textures: pl.textures, chars: pl.chars }));
  const shape = await page.json('__galaxy.planets.shapeOf(__galaxy.nodes[0].id)');
  note('one world: ' + JSON.stringify(shape));
  ok(!!shape && !!shape.tex && shape.tex[0] === 512 && shape.tex[1] === 256,
     'the surface texture is 512×256, read off the canvas rather than off the constant',
     JSON.stringify(shape && shape.tex));
  ok(!!shape && shape.parts === 3 && shape.spinKids === 2 && shape.glow === true,
     'and the world is assembled as specified: a spinning core and text shell, plus an ' +
     'atmosphere and a ring that do NOT spin with it',
     JSON.stringify(shape));
  ok(!!shape && shape.radius > 1,
     'it is sized from the same nodeVal the old spheres used (radius ' +
     (shape ? shape.radius : '?') + ')');
  /* THE RING IS A CLAIM ABOUT CONNECTEDNESS, so it is checked against the connectedness -
     recounted here, in Node, from __galaxy.active. A harness that asked the page how many
     hubs it thought there were would be asking the defendant. */
  const hubs = await page.evaluate(`(function(){
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
    var n = 0;
    var need = __galaxy.sky.ringDeg;
    deg.forEach(function(d){ if (d >= need) n++; });
    return n;
  })()`);
  /* THE THRESHOLD IS READ, NOT WRITTEN DOWN TWICE. It moved from six to eight the day the
     ring became a mark of a real hub rather than of having friends, and a harness holding
     its own copy of the number would have failed for the wrong reason - or worse, passed. */
  const ringDeg = await page.evaluate('__galaxy.sky.ringDeg');
  ok(ringDeg >= 8,
     'a ring means a REAL hub: the threshold is ' + ringDeg + ' connections, not six',
     JSON.stringify({ ringDeg: ringDeg }));
  ok(pl.ringed === hubs && hubs > 0 && hubs < pl.nodes / 2,
     'and the ringed worlds are exactly those hubs: ' + pl.ringed + ' with a ring, ' + hubs +
     ' with ' + ringDeg + ' or more links, counted independently - a minority of ' +
     pl.nodes + ' worlds, which is what makes the ring mean anything',
     JSON.stringify({ ringed: pl.ringed, hubs: hubs, deg: '>=' + ringDeg }));
  const ringShape = await page.json('({alpha: __galaxy.sky.ringAlpha, width: __galaxy.sky.ringWidth})');
  ok(ringShape.alpha <= 0.13 && ringShape.width <= 0.34,
     'and it is worn lightly: opacity ' + ringShape.alpha + ' and width ' + ringShape.width +
     ', both half what they were', JSON.stringify(ringShape));
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
  ok(sky.palette.length === 7 && candy.length === 0,
     'the palette is seven jewels and not one of them is a boiled sweet: ' +
     sky.palette.join(' '), JSON.stringify(candy));

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

  /* ---- 2. FIVE SECONDS OF IDLE SKY --------------------------------------- */
  await sleep(1800);                       // let the boot overlay finish and the layout settle
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
  await sleep(CALM_MS);
  const heldTo = await page.json('({quat: __galaxy.camera.quat, pos: __galaxy.camera.pos,' +
    ' par: __galaxy.camera.parallax, target: __galaxy.camera.target,' +
    ' flights: __galaxy.camera.flights})');
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
  /* The pointer goes back to the middle and the lean unwinds, so the pictures below are of
     the galaxy and not of the galaxy at 2.5 degrees. */
  await page.evaluate('__galaxy.camera.look(0, 0)');
  await sleep(1500);

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
  /* THE SURFACE IS STILL THERE TO BE READ. A selected world used to come back as
     '#ffffff' from nodeColor, which under an emissive and a bloom erased its own text. The
     body has to stay a dark cluster colour, not a lamp. */
  ok(afterSweep.body !== '#ffffff' && /^#[0-9a-f]{6}$/.test(afterSweep.body || '') &&
     Math.max(...(afterSweep.body || '#ffffff').slice(1).match(/../g)
       .map((h) => parseInt(h, 16))) < 190,
     'and the selected world keeps a DARK body (' + afterSweep.body + ') so its own text ' +
     'is still legible on it', JSON.stringify(afterSweep));
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
  ok(glass.trans === 'transform' && glass.ms === '0.25s',
     'and it enters on a transform alone, capped at 250ms - no width, no top, no shadow',
     JSON.stringify({ property: glass.trans, duration: glass.ms }));
  ok(/cubic-bezier\(0\.34,\s*1\.56,\s*0\.64,\s*1\)/.test(glass.ease),
     'on the spring the spec asked for', glass.ease);
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

  /* ---- 5. THE HANDS GATE, DIMMED, AND STILL CLICKABLE -------------------- */
  await page.evaluate('document.getElementById("q").focus()', true);
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
    ' played: __galaxy.audio.played.map(function(t){return t.kind}),' +
    ' trouble: __galaxy.audio.trouble})');
  note('audio: ' + JSON.stringify(audio));
  ok(audio.built === true, 'the tone engine was built on a real gesture, with no mp3 ' +
     'anywhere', JSON.stringify(audio.trouble));
  ok(audio.gain === 0.15 && audio.ceiling === 0.15,
     'THE VOLUME IS CAPPED AT 15%, read back off the gain node rather than off the ' +
     'constant beside it', JSON.stringify({ node: audio.gain, declared: audio.ceiling }));
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

    note('throttling the CPU 20\u00d7 to drive the frame rate under 45fps\u2026');
    await page.send('Emulation.setCPUThrottlingRate', { rate: 20 });
    const dropped = await waitFor(page, '__galaxy.deck.bloom === false', 30000);
    await page.send('Emulation.setCPUThrottlingRate', { rate: 1 });
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
    procs.forEach(p => { try { process.kill(p.pid); } catch { } });
    await sleep(600);
    profiles.forEach(p => { try { rmSync(p, { recursive: true, force: true }); } catch { } });
    console.log('\n  VERIFY ' + (checks - bad.length) + '/' + checks +
                (bad.length ? ' FAIL' : ' PASS') + '\n');
    bad.forEach(b => console.log('    FAILED: ' + b));
    process.exit(bad.length ? 1 : 0);
  });
