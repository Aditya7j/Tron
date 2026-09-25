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
const PLANET_EMISSIVE_HOT = 0.34;
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
                  left: Math.round(r.left), right: Math.round(innerWidth - r.right)},
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
  ok(trail.css.pe === 'none' && trail.css.top === 0 && trail.css.left === 0 &&
     trail.css.h === 30,
     'a 30px band across the very top that CANNOT BE CLICKED: pointer-events none, so it ' +
     'never takes a press meant for the sky', JSON.stringify(trail.css));
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
  ok(JSON.stringify(org.ids) ===
     JSON.stringify(['screen', 'eye', 'focusbtn', 'mic', 'reset']),
     'THE ORGAN RAIL IS THE FIVE BUTTONS THAT WERE ALREADY THERE: #screen #eye #focusbtn ' +
     '#mic #reset, under the ids every other harness in this repo already clicks',
     JSON.stringify(org.ids));
  const dots = org.ids.every((id) => org.state[id] && org.state[id].dot);
  ok(dots, 'each one carries a state dot', JSON.stringify(org.state));
  const lines = org.ids.filter((id) => !(org.state[id] || {}).line);
  ok(lines.length === 0,
     'and a state line in its tooltip, on every one of the five',
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
  ok(JSON.stringify(sheet.ids) ===
     JSON.stringify(['focus', 'lock', 'links', 'archive', 'cast']) && sheet.count === 5,
     'FIVE DIEGETIC ORDERS, and they are the five the constitution lists: start focus, ' +
     'lock the tab, simplify the links, open the archive, cast the voice',
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
  /* The pointer keeps arriving while the sheet is open - the OPPOSITE corner, so there is a
     real difference for the camera to refuse rather than a still mouse to coast on. */
  await page.evaluate('__galaxy.camera.look(-1, -1)');
  await sleep(1400);
  const par1 = await beat();
  note('parallax under the sheet: suspended ' + par1.suspended + ' · moves ' +
       par0.moves + ' -> ' + par1.moves + ' · holds +' + (par1.holds - par0.holds) +
       ' · spins +' + (par1.spins - par0.spins));
  ok(summoned && par1.suspended === true,
     'THE PARALLAX SUSPENDS WHILE THE SHEET IS OPEN - the flag is written on every frame, ' +
     'so a panel summoned by a key is honoured on the next frame and not on the next mouse ' +
     'move', JSON.stringify({ open: summoned, par: par1 }));
  ok(par1.moves === par0.moves && par1.holds === par0.holds,
     'and the camera is FROZEN rather than eased: the pointer was taken to the opposite ' +
     'corner and neither counter moved, because WANTED is dragged up to NOW instead of ' +
     'being followed', JSON.stringify({ moves: [par0.moves, par1.moves],
                                        holds: [par0.holds, par1.holds] }));
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

    /* A RAMP, NOT A NUMBER. This used to set the throttle to 20x and wait, and 20x is not
       a fact about anything - it is a guess about how slow a machine has to pretend to be
       before a headless compositor misses a frame. Measured here it lands at 46-52fps, a
       hair ABOVE the 45 floor, so the test passed or failed on which side of the floor the
       noise fell. What is actually being proved is that a SUSTAINED SAG drops the bloom, so
       the harness leans harder until the sag exists and then holds the brake to it.
       AND THE WAIT IS A SLEEP, NOT A POLL. waitFor asks the page a question every few
       hundred milliseconds, and at these throttle rates answering one is itself a long
       frame - long enough to trip the brake's own "the browser suspended us" guard, which
       resets the sag timer. The harness was interrupting the very sag it was waiting for.
       So: lean, go quiet for longer than the three-second grace, then ask once. */
    let dropped = false;
    for (const rate of [20, 30, 45]) {
      note('throttling the CPU ' + rate + '\u00d7 to drive the frame rate under 45fps\u2026');
      await page.send('Emulation.setCPUThrottlingRate', { rate });
      await sleep(7000);
      const sag = await page.json('({bloom: __galaxy.deck.bloom, fps: __galaxy.deck.fps})');
      if (sag.bloom === false) { dropped = true; note('the brake fired at ' + rate + '\u00d7'); break; }
      note('held ' + sag.fps + 'fps at ' + rate + '\u00d7 - above the floor, so leaning harder');
    }
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
