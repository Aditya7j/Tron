/* cine_proof.mjs - §33's CINEMA AND ITS PRICE, machine-checked.
 *
 * THE MANDATE'S PART 2 IS A LIST OF CONDITIONS, AND THIS IS THAT LIST AS ASSERTIONS:
 *   "Frame-time budget measured per effect and tabulated: bloom pass, smoke, rings, stream -
 *    each with its millisecond cost at 1280 and fullscreen. 60fps containment asserted with
 *    everything on at 1280/1600/fullscreen; a declared point+sprite cap for the whole presence
 *    system, asserted. Config flags bloom_on, smoke_on (default on) with an auto-revert clause
 *    ... Text-contrast and card-legibility assertions at all three widths with bloom at full
 *    strength; core/addon pin-parity assertion green. Speech-glow continuity assertion: on a
 *    fixed utterance, speaking-frame core luminance and bloom intensity measurably exceed
 *    idle-frame values (thresholds named in the proof) and settle back within one second of
 *    silence; a bloom-on build that loses the pulse fails this assertion."
 *
 * EVERY ASSERTION NAMES ITS FAILURE MODE, which is the mandate's standing requirement for this
 * round and is why the claims in here are long sentences rather than labels.
 *
 * NINE SECTIONS:
 *   1. THE PIN AND THE HOST, by SOURCE. The mandate asks for a source check and not a runtime
 *      one, because a runtime check cannot tell a pinned addon from a lucky cache. Both halves
 *      are here: the importmap's two specifiers read out of viewer/index.html, the four bare
 *      addon specifiers, the absence of any second three version, the absence of GSAP and of a
 *      build step - and THEN the live REVISION, which is the parity half.
 *   2. THE RINGS. Two orbits that cross rather than nest, inside the reticle, with §32's
 *      geometry byte-for-byte where it was and the point cap asserted as a number.
 *   3. THE HAZE IS GONE (UI mandate III PART 1, which removed it as the pale disc behind the
 *      presence): no door, no sprites, no second scene pass, no fog, one object, and nothing on
 *      the canvas moving on a clock of its own - measured off the presence's own pixels.
 *   4. THE LIGHT. The composer, the three passes IN ORDER BY NAME, the half-resolution decision
 *      still in force, and the alpha corners still transparent with bloom at full.
 *   5. THE TEXT. Bloom at full strength against UI text and card edges at all three widths,
 *      asserted as PIXEL IDENTITY rather than as a contrast ratio - see the section header.
 *   6. THE SPEAKING GLOW. Idle against speaking against one second later, in bloom strength AND
 *      in measured core luminance, with the thresholds named; and the heartbeat surviving with
 *      the bloom switched off, which is the mandate's "bloom may die before the heartbeat does".
 *   7. THE STREAM. One in flight, the queue's ceiling, the drop counter, and the overlay's
 *      three structural properties.
 *   8. THE PRICE. The frame-time table, per effect, priced by INTERLEAVED on/off PAIRS at
 *      1280 / 1600 / fullscreen - and 60fps containment asserted from whole-frame time rather
 *      than from a vsync-clamped fps.
 *   9. THE GUARDS. The two config flags end to end, a clean run's empty revert list, the ladder
 *      in the right order, and the spring's integrated numbers.
 *
 * WHY VSYNC IS OFF IN THIS HARNESS. The first draft asserted 60fps containment by reading
 * __galaxy.presence.fps with each effect switched off in turn. It read 60.0 on every row at
 * every width with everything on AND with everything off, because the rAF loop is clamped to
 * the display's refresh: any chain that fits inside 16.7ms reads exactly 60, so the instrument
 * cannot tell a 2ms chain from a 14ms one and the "budget" would have been four copies of the
 * same number. With --disable-gpu-vsync the loop runs flat out, the frame time is the real one
 * including the GPU, and 60fps containment becomes the STRONGER claim "the frame costs less
 * than 16.67ms" rather than "the clamp held". Both are stated where they are asserted.
 *
 * Headless, one temp profile, port 9307, killed by that profile's basename. It never touches
 * 9222 - that is the boss's own browser.
 */
import { spawn, spawnSync } from 'node:child_process';
import { mkdtempSync, rmSync, existsSync, readFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, basename } from 'node:path';

const PORT = 9307;                        // _cineprobe took 9306, roll_proof 9299
const CDP = 'http://127.0.0.1:' + PORT;
const GALAXY = 'http://127.0.0.1:4700';
const SRC = 'viewer/index.html';

/* THE HOUSE PIN, READ FROM THE VIEWER AND NOT TYPED HERE. The mandate: "at round start read
   the house's existing three.js pin and CDN host from viewer/index.html; the post-processing
   addons load from the identical pin and host". A harness that hardcoded 0.183.0 would go green
   on the day somebody bumped the viewer and left the addons behind - which is the exact failure
   the parity assertion exists to catch. So the pin is PARSED, printed, and then everything else
   is compared against what was parsed. */
const SOURCE = readFileSync(SRC, 'utf8');
const IMPORTMAP = (/<script type="importmap">([\s\S]*?)<\/script>/.exec(SOURCE) || [])[1] || '';
const THREE_SPEC = (/"three"\s*:\s*"([^"]+)"/.exec(IMPORTMAP) || [])[1] || '';
const ADDON_SPEC = (/"three\/addons\/"\s*:\s*"([^"]+)"/.exec(IMPORTMAP) || [])[1] || '';
const PIN = (/three@([0-9][0-9.]*)\//.exec(THREE_SPEC) || [])[1] || '';
const HOST = (/^https:\/\/([^/]+)\//.exec(THREE_SPEC) || [])[1] || '';
const ADDONS = ['EffectComposer', 'RenderPass', 'UnrealBloomPass', 'OutputPass'];

const WIDTHS = [[1280, 800], [1600, 900], [1920, 1080]];   // the third is this run's fullscreen
/* UI MANDATE II: THE SEVEN-RADIUS LADDER IS GONE WITH THE CORE. The dust's silhouette is one
   radius and a density that falls from the heart outward; section 2 reads the five radial shells
   off the drawn buffer and asserts the fall, which is the ladder's job (a structure that cannot
   collapse into one thick band) said for a volume. */
const DUST_SHELLS = ['0-0.2', '0.2-0.4', '0.4-0.6', '0.6-0.8', '0.8-1.0'];
/* THE THRESHOLDS, NAMED HERE RATHER THAN INLINE, because the mandate says "thresholds named in
   the proof" and a number buried in an expression is not named. */
const T = {
  FRAME_MS: 16.67,        // 60fps containment, as a frame time
  GLOW_MIN: 1.10,         // bloom strength while speaking must clear this - CINE's own floor
  SETTLE_MS: 1000,        // the mandate's "within one second of silence"
  SETTLE_EPS: 0.08,       // how close to idle counts as settled, in strength units
  LUM_RISE: 1.02,         // speaking core luminance / idle, measured in pixels
  /* UI MANDATE III: the haze is gone, so the two numbers that bounded it are gone with it. These
     replace them, and both were set after measuring (see section 3 and PART 2's replacement).
     STILL is how many lit pixels of the presence's own 160px snapshot may change between two
     snapshots 1.4s apart with the presence's clock pinned - zero, because with the haze gone
     nothing on that canvas runs on a clock of its own. NULL_BOUND is how far toggling the
     removed haze's flag may move the chain's paired dispatch: a flag with nothing to switch. */
  STILL: 0, NULL_BOUND: 0.02,
  BARE_MAX: 1,               // the presence canvas with its points off, peak 0-255: nothing behind it
  GLASS_MAX: 1,              // light the canvas adds on screen at 0.85-0.95 of the well, 0-255
  CORNER_LUM: 0.02,       // how much DARKER than the ground a corner may be - i.e. not at all
  FALLOFF: 4,             // centre contribution / worst corner: a glow falls off, a fill does not
  TEXT_DELTA: 2,          // max per-channel change in a text crop when the bloom comes on
  STREAM_BOUND: 1.5,      // the stream's frame cost is asserted as a bound, not priced
  SPRING_MIN: 0.005, SPRING_MAX: 0.04,  // the overshoot must be visible and must not be a bounce
  /* §34. EVERY ONE OF THESE FOUR IS A MEASURED NUMBER AND NOT A PREFERENCE, and the measurement
     is named beside it so a later round can see what it would be loosening.
     EDGE_LUM is what the canvas may still ADD at its own border, paired against the canvas being
     absent. Before the window: 0.04845-0.06846 (12.4-17.5/255) on all four sides, 4/4 sign. After:
     0.00029-0.00047 (~0.1/255). 0.004 is 1/255 - above the after-reading by 8x so the breath and
     the deck's drift cannot redden it, and 12x BELOW the defect so a regression cannot hide in it.
     EDGE_CTRL is the positive control's floor: switching the window off must put the rectangle
     back by at least this much. Measured: +0.0448 to +0.0491, 4/4 sign, se <= 0.001. A window that
     is never applied reads 0 here, which is the §33 trap this threshold exists to catch.
     SCALE_GAP is how far the core fraction may differ between windowed and fullscreen on ONE
     screen width. Measured 6.6-10.5% once the ask is viewport-derived; the deck's band clamps the
     rest and PART 3's own limit is reported rather than asserted away.
     BRACKET_PX is the floor the .pb marks keep when the well is small (the CSS max(10px, ...)). */
  EDGE_LUM: 0.004, EDGE_CTRL: 0.02, SCALE_GAP: 0.15, BRACKET_PX: 10
};

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let checks = 0;
const bad = [];
const ok = (c, claim, detail) => {
  checks++;
  console.log((c ? '  ok   ' : '  FAIL ') + claim);
  if (!c) { bad.push(claim); if (detail) console.log('         ' + detail); }
};
const note = (s) => console.log('       · ' + s);
const head = (s) => console.log('\n  ---- ' + s + ' ----');

function chromeExe() {
  const tries = [
    'C:/Program Files/Google/Chrome/Application/chrome.exe',
    'C:/Program Files (x86)/Google/Chrome/Application/chrome.exe',
    join(process.env.LOCALAPPDATA || '', 'Google/Chrome/Application/chrome.exe'),
  ];
  for (const t of tries) if (existsSync(t)) return t;
  throw new Error('no chrome.exe found');
}

class Page {
  constructor(u) { this.u = u; this.id = 0; this.w = new Map(); this.logs = []; }
  open() {
    return new Promise((res, rej) => {
      this.ws = new WebSocket(this.u);
      this.ws.onopen = () => res(this);
      this.ws.onerror = (e) => rej(new Error('socket: ' + (e.message || 'failed')));
      this.ws.onmessage = (ev) => {
        const m = JSON.parse(ev.data);
        const f = this.w.get(m.id);
        if (f) { this.w.delete(m.id); f(m); return; }
        if (m.method === 'Runtime.exceptionThrown') {
          this.logs.push('throw: ' + ((m.params.exceptionDetails || {}).text || ''));
        }
      };
    });
  }
  send(method, params) {
    const id = ++this.id;
    return new Promise((res, rej) => {
      const bomb = setTimeout(() => { this.w.delete(id); rej(new Error(method + ' timed out')); },
                              40000);
      this.w.set(id, (m) => { clearTimeout(bomb); res(m); });
      this.ws.send(JSON.stringify({ id, method, params: params || {} }));
    });
  }
  async evaluate(e) {
    const r = await this.send('Runtime.evaluate',
      { expression: e, returnByValue: true, awaitPromise: true, userGesture: true });
    if (r.result && r.result.exceptionDetails) {
      throw new Error('page threw: ' + JSON.stringify(
        (r.result.exceptionDetails.exception &&
         r.result.exceptionDetails.exception.description) ||
        r.result.exceptionDetails.text));
    }
    return r.result && r.result.result ? r.result.result.value : undefined;
  }
  async json(e) { return JSON.parse(await this.evaluate('JSON.stringify(' + e + ')') || 'null'); }
  /* PIXELS, AND THE DECODER IS CHROME'S OWN.
     Node has no PNG decoder in its standard library and this house adds no dependency, so the
     screenshot goes back into the page it came from, is decoded by the browser as an Image, and
     is measured in a 2D canvas. Everything crosses the wire as a base64 string and a handful of
     numbers.
     WHY NOT drawImage(presence-cvs) DIRECTLY, which would be three lines shorter: the presence
     renderer runs without preserveDrawingBuffer, so its back buffer is gone by the time any
     script can read it, and a reading taken that way is either a blank or the compositor's last
     copy depending on timing. Page.captureScreenshot measures WHAT IS ON THE GLASS, which is
     also the only thing the mandate's words are about. Failure mode of the shortcut: an
     all-zero luminance that reads as "the core went dark" on a build where nothing is wrong. */
  async pixels(clip) {
    const r = await this.send('Page.captureScreenshot',
      { format: 'png', captureBeyondViewport: false,
        clip: { x: Math.round(clip.x), y: Math.round(clip.y),
                width: Math.max(1, Math.round(clip.w)),
                height: Math.max(1, Math.round(clip.h)), scale: 1 } });
    const data = r.result && r.result.data;
    if (!data) throw new Error('no screenshot came back');
    const out = await this.evaluate(
      '(async function(){' +
      'var im = new Image();' +
      'await new Promise(function(res,rej){im.onload=res;im.onerror=rej;' +
      'im.src="data:image/png;base64,' + data + '";});' +
      'var c=document.createElement("canvas");c.width=im.width;c.height=im.height;' +
      'var g=c.getContext("2d",{willReadFrequently:true});g.drawImage(im,0,0);' +
      'var d=g.getImageData(0,0,c.width,c.height).data, n=c.width*c.height;' +
      'var s=0,mx=0,hot=0,sum=[0,0,0];' +
      'for(var i=0;i<d.length;i+=4){' +
      ' var l=(0.2126*d[i]+0.7152*d[i+1]+0.0722*d[i+2])/255;' +
      ' s+=l; if(l>mx)mx=l; if(l>0.75)hot++;' +
      ' sum[0]+=d[i];sum[1]+=d[i+1];sum[2]+=d[i+2];}' +
      'return JSON.stringify({w:c.width,h:c.height,n:n,' +
      ' mean:+(s/n).toFixed(5), max:+mx.toFixed(5), hot:+(hot/n).toFixed(5),' +
      ' rgb:[+(sum[0]/n).toFixed(3),+(sum[1]/n).toFixed(3),+(sum[2]/n).toFixed(3)],' +
      ' sig:d.length});})()');
    return JSON.parse(out);
  }
  /* MANY REGIONS OUT OF ONE SHOT, WHICH IS WHAT MAKES A DIFFERENCE MEASUREMENT HONEST HERE.
     Five separate pixels() calls are five separate screenshots taken seconds apart, because each
     one is a CDP round trip plus an in-page PNG decode. That is fine when the subject is static
     and fatal when it is not: the deck's force graph is a live simulation BEHIND the presence
     canvas, so a bright star drifting through one crop between two shots shows up in the
     subtraction as if the canvas had put it there. It is how the corner assertion went red at
     exactly one corner, 0.25 against 0.055 at the other three, with the haze switched off and
     nothing wrong.
     So: one screenshot of the whole canvas rect, decoded once, and every region measured out of
     THAT image. All five readings are then the same instant by construction, and the only gap
     left is the one between the two states - which the caller shortens and medians over. */
  async regions(clip, boxes) {
    const r = await this.send('Page.captureScreenshot',
      { format: 'png', captureBeyondViewport: false,
        clip: { x: Math.round(clip.x), y: Math.round(clip.y),
                width: Math.max(1, Math.round(clip.w)),
                height: Math.max(1, Math.round(clip.h)), scale: 1 } });
    const data = r.result && r.result.data;
    if (!data) throw new Error('no screenshot came back');
    const out = await this.evaluate(
      '(async function(){' +
      'var im = new Image();' +
      'await new Promise(function(res,rej){im.onload=res;im.onerror=rej;' +
      'im.src="data:image/png;base64,' + data + '";});' +
      'var c=document.createElement("canvas");c.width=im.width;c.height=im.height;' +
      'var g=c.getContext("2d",{willReadFrequently:true});g.drawImage(im,0,0);' +
      'var B=' + JSON.stringify(boxes) + ', out=[];' +
      'for (var b=0;b<B.length;b++){' +
      ' var x=Math.max(0,Math.min(c.width-1,Math.round(B[b][0])));' +
      ' var y=Math.max(0,Math.min(c.height-1,Math.round(B[b][1])));' +
      ' var w=Math.max(1,Math.min(c.width-x,Math.round(B[b][2])));' +
      ' var h=Math.max(1,Math.min(c.height-y,Math.round(B[b][3])));' +
      ' var d=g.getImageData(x,y,w,h).data, s=0;' +
      ' for(var i=0;i<d.length;i+=4) s+=(0.2126*d[i]+0.7152*d[i+1]+0.0722*d[i+2])/255;' +
      ' out.push(+(s/(w*h)).toFixed(5));}' +
      'return JSON.stringify(out);})()');
    return JSON.parse(out);
  }
  /* THE SAME SHOT, KEPT AS BYTES, for the text assertion - where the question is not "how
     bright" but "did a single pixel move". */
  async raw(clip) {
    const r = await this.send('Page.captureScreenshot',
      { format: 'png', captureBeyondViewport: false,
        clip: { x: Math.round(clip.x), y: Math.round(clip.y),
                width: Math.max(1, Math.round(clip.w)),
                height: Math.max(1, Math.round(clip.h)), scale: 1 } });
    return (r.result && r.result.data) || '';
  }
}
const cdp = async (p) => {
  const t = await (await fetch(CDP + p)).text();
  try { return JSON.parse(t); } catch { return t; }
};

const profile = mkdtempSync(join(tmpdir(), 'cineproof-'));
let chrome = null;
function shut() {
  if (chrome) { try { chrome.kill(); } catch { /* ignore */ } }
  /* PROFILE-SCOPED, never by window title: the one Chrome on this machine that must survive
     every harness is the boss's own on 9222. */
  spawnSync('powershell.exe', ['-NoProfile', '-Command',
    'Get-CimInstance Win32_Process | Where-Object { $_.Name -eq \'chrome.exe\' -and ' +
    '$_.CommandLine -match \'' + basename(profile) + '\' } | ' +
    'ForEach-Object { taskkill /PID $_.ProcessId /F | Out-Null }'],
    { encoding: 'utf8', timeout: 30000 });
}

/* A CONFIGURATION'S FRAME TIME, as a median of three samples rather than one reading. The
   presence shares its loop with the deck's graph, so a single 900ms window has about a
   millisecond of variance in it - enough to make the bloom look free on one run and twice its
   price on the next. Three samples and the middle one. */
async function frameMs(page, n) {
  const got = [];
  for (let i = 0; i < (n || 3); i++) {
    await sleep(1100);
    const f = await page.evaluate('__galaxy.presence.fps');
    if (f > 0) got.push(1000 / f);
  }
  got.sort((a, b) => a - b);
  return got.length ? +got[Math.floor(got.length / 2)].toFixed(3) : 0;
}

async function main() {
  /* A PORT THIS RUN DID NOT OPEN IS A BROWSER THIS RUN CANNOT TRUST. */
  let squatter = null;
  try {
    const r = await fetch(CDP + '/json/version', { signal: AbortSignal.timeout(2000) });
    squatter = (await r.json()).Browser || 'something';
  } catch { /* silence is the only acceptable state */ }
  if (squatter) {
    throw new Error('port ' + PORT + ' is already held by ' + squatter + ' - this run will not ' +
      'measure a browser it did not launch (a leftover from this harness is killable by its ' +
      'temp profile: cineproof-*).');
  }

  /* ================================ 1. THE PIN AND THE HOST ============================ */
  head('1. the pin, the host and the vendor, by source');
  note('read from ' + SRC + ': three@' + (PIN || '?') + ' on ' + (HOST || '?'));
  ok(!!PIN && !!HOST && THREE_SPEC ===
       'https://' + HOST + '/npm/three@' + PIN + '/build/three.module.js',
     'THE IMPORTMAP\'S CORE SPECIFIER IS THE HOUSE PIN ON THE HOUSE HOST: "three" resolves to ' +
     THREE_SPEC + ', which is where the pin and the host in every other assertion in this ' +
     'section were read FROM - failure mode if this line were a literal instead: the harness ' +
     'goes green on the day the viewer is bumped and the addons are left on the old version',
     THREE_SPEC);
  ok(ADDON_SPEC === 'https://' + HOST + '/npm/three@' + PIN + '/examples/jsm/',
     'AND THE ADDON PREFIX IS THE IDENTICAL PIN AND THE IDENTICAL HOST: "three/addons/" -> ' +
     ADDON_SPEC + ' - failure mode if the two drifted: the post chain runs classes compiled ' +
     'against a different three than the renderer they are handed, which is the exact shape of ' +
     'the intersectsFrustum break this file already carries a note about',
     ADDON_SPEC);
  const specs = ADDONS.map((a) =>
    new RegExp("import\\('three/addons/postprocessing/" + a + "\\.js'\\)").test(SOURCE));
  ok(specs.every(Boolean),
     'ALL FOUR ADDONS ARE IMPORTED BY BARE SPECIFIER: ' + ADDONS.join(', ') + ' each come from ' +
     "'three/addons/postprocessing/<name>.js' and therefore from the importmap - failure mode " +
     'of a full URL here: a second place a version can be typed, which is how a pin drifts ' +
     'without anybody editing the importmap',
     JSON.stringify(ADDONS.map((a, i) => a + ':' + specs[i])));
  const versions = [...new Set((SOURCE.match(/three@[0-9][0-9.]*/g) || []))];
  ok(versions.length === 1 && versions[0] === 'three@' + PIN,
     'AND THERE IS EXACTLY ONE three VERSION STRING IN THE WHOLE VIEWER: ' + versions.join(', ') +
     ' - failure mode of two: both load, both are pinned, nothing throws, and the page holds ' +
     'two incompatible class hierarchies that only disagree under a resize or a frustum test',
     JSON.stringify(versions));
  /* THE GSAP TEST IS A LOAD TEST AND NOT A WORD TEST, which is a correction this harness earned
     the first time it ran: /gsap/i over the whole file matches the four comment lines that QUOTE
     the mandate's own GSAP clause, so the word test went red on a file containing no GSAP at
     all. The thing that must be absent is a script tag, a module import or a CDN URL - the ways
     a library actually arrives. Failure mode of the word test: it punishes the file for
     documenting the rule it is obeying, and the obvious fix is to delete the explanation. */
  const gsapLoad = /(<script[^>]*gsap|from\s+["']gsap|import\(\s*["'][^"']*gsap|\/\/[^"'\s]*cdn[^"'\s]*gsap)/i
                     .test(SOURCE);
  ok(!gsapLoad,
     'NO GSAP IS LOADED, SO THE HOUSE OWNS EVERY LINE OF THE MOTION: no script tag, no import, ' +
     'no CDN URL - the mandate permits it by pinned CDN only if the hand-rolled spring fails the ' +
     'boss\'s plate checkpoint, and the spring has not been to a checkpoint yet - failure mode ' +
     'of a pre-emptive vendor: 70KB and an animation system nobody in this house can debug, ' +
     'added to avoid twenty lines of arithmetic',
     'gsap loaded: ' + gsapLoad);
  const built = /node_modules|from\s+["']gsap|<script src="\.\/(dist|bundle)/.test(SOURCE);
  ok(!built,
     'AND NO BUILD STEP AND NO NEW VENDOR: no node_modules, no bundle entry point, nothing but ' +
     'the pinned CDN - failure mode: a viewer that cannot be opened from the filesystem by the ' +
     'next person to look at it',
     'built: ' + built);

  chrome = spawn(chromeExe(), [
    '--remote-debugging-port=' + PORT, '--user-data-dir=' + profile,
    '--no-first-run', '--no-default-browser-check', '--headless=new', '--mute-audio',
    '--disable-features=CalculateNativeWinOcclusion',
    '--disable-backgrounding-occluded-windows', '--disable-renderer-backgrounding',
    '--force-device-scale-factor=1',
    /* SEE THE HEADER: without these two every frame-time reading in section 8 is the number
       60 and the budget is four copies of it. */
    '--disable-gpu-vsync', '--disable-frame-rate-limit',
    /* AND THE CARD IS PINNED, through §39's own named door - not one assertion in this file
       changed. §39 gave the answer card a four-second grace and then removes it, and on a
       ?mute=1 tab like this one the grace is an ESTIMATED READ TIME, so it arms on every card
       this harness renders whether a voice ever spoke or not. Section 7 flies its six particles
       from #a-chips (see presence.stream(n), which falls back to #answer and then gives up), so
       a card that had left took the origin with it: six sends came back 'no-origin', the queue
       read 0 where 5 were expected, and the next assertion threw on the flying dot's transform
       being null - a page working exactly as §39's mandate asks, reading as a broken particle
       stream. ?vanish=0 is the door that mandate names for "a harness that needs a standing
       card for twenty seconds", and it is the whole of the repair. */
    '--window-size=1600,1000', '--new-window', GALAXY + '/?mute=1&vanish=0',
  ], { detached: true, stdio: 'ignore' });
  chrome.unref();

  for (let i = 0; i < 80; i++) {
    try { await cdp('/json/version'); break; } catch { await sleep(250); }
  }
  let target = null;
  for (let i = 0; i < 40; i++) {
    const l = await cdp('/json/list');
    target = (Array.isArray(l) ? l : []).filter((t) => t.type === 'page')
      .find((t) => t.url.includes('127.0.0.1:4700'));
    if (target) break;
    await sleep(300);
  }
  if (!target) throw new Error('the viewer tab never appeared');
  const page = new Page(target.webSocketDebuggerUrl);
  await page.open();
  await page.send('Runtime.enable');
  await page.send('Page.enable');

  for (let i = 0; i < 240; i++) {
    if (await page.evaluate('!!(window.__galaxy && __galaxy.presence && __galaxy.presence.on)')) break;
    await sleep(250);
  }
  /* THE DUST IS ASKED FOR AFTER THE BOOT, not before: presMode() on a presence that has not
     booted is a request the boot then overwrites with its own first mode. UI MANDATE II: the core
     is gone and the rich mode is the dust; and since the main pane shows the galaxy at rest, the
     stage is turned to the presence through stageSet() - the door the ear uses - because every
     pixel this file reads is a pixel of the presence ON the glass. */
  await page.evaluate('__galaxy.stage.set("presence", "cine_proof")');
  const mode = await page.evaluate("String(__galaxy.presence.set('dust'))");
  await sleep(2500);
  const rev = await page.json('__galaxy.presence.cine.rev');
  ok(mode === 'dust' && String(rev) === String(PIN).split('.')[1],
     'AND THE PARITY IS LIVE AS WELL AS WRITTEN: the three the presence actually resolved ' +
     'reports REVISION ' + rev + ', which is ' + PIN + '\'s minor - failure mode of asserting ' +
     'only the source: a stale service worker or a CDN redirect serves a different build and ' +
     'every other assertion in this file is made against code the importmap did not choose',
     JSON.stringify({ mode: mode, rev: rev, pin: PIN }));

  /* ====================================== 2. THE DUST ================================== */
  /* UI MANDATE II PART 3 REMOVED THE CORE, and its orbits, bands, shell, heart and reticle with
     it. Each of this section's seven assertions is replaced by the dust's counterpart, named
     beside the one it stands in for:
       old: TWO ORBITAL BANDS, POINT-BUILT       new: THE DUST IS POINT-BUILT IN THE ONE BUFFER
       old: DIFFERING INCLINATIONS AND SPEEDS    new: IT TURNS, DRIFTS AND BREATHES, ALL SLOW
       old: EACH AT ITS DECLARED RADIUS, FLAT     new: IT REACHES ITS DECLARED RADIUS AND NO FURTHER
       old: EVERYTHING ROUND INSIDE THE RETICLE  new: EVERY OCTANT CARRIES DUST
       old: THE SEVEN-RADIUS LADDER ASCENDS      new: THE DENSITY FALLS SHELL BY SHELL FROM THE HEART
                                                 (UI mandate IV: THE HEART IS THE DENSEST SHELL)
       old: THE POINT CAP HOLDS, WHOLE CORE ON   new: THE POINT CAP HOLDS, WHOLE DUST ON
       old: §32 IS WHERE §32 LEFT IT             new: THE DUST IS WHERE MANDATE II LEFT IT */
  head('2. the dust');
  const dust = await page.json('__galaxy.presence.dust()');
  const cine0 = await page.json('__galaxy.presence.cine');
  const geo = (dust && dust.geo) || null;
  const life = await page.json('__galaxy.presence.life || null');
  note('shells ' + DUST_SHELLS.join(' / ') + ': ' + (geo ? geo.bins.join(' / ') : '-') +
       ' points, density ' + (geo ? geo.density.join(' / ') : '-') + ' · life ' + JSON.stringify(life));
  ok(!!geo && geo.roles.length === 1 && geo.mesh === 0 && dust.points === cine0.points,
     'THE DUST IS POINT-BUILT IN THE ONE BUFFER: ' + (dust && dust.points) + ' points of one ' +
     'role in the presence\'s single Points object, no second object - failure mode of a cloud ' +
     'built as many Points: deck_proof\'s "one object, one material" goes red and the cap stops ' +
     'meaning anything',
     JSON.stringify(geo && { roles: geo.roles, mesh: geo.mesh, points: dust && dust.points }));
  /* UI MANDATE III PART 1B: the 0.05 drift became a per-point WANDER - heart points a little,
     edge points a lot, one in ten a stray - so the claim names the wander's own numbers.
     Old: life.drift in (0, 0.2). New: wander edge > heart > 0, a stray multiplier > 1, all slow. */
  const wd = (life && life.wander) || {};
  ok(!!life && life.spin > 0 && life.spin < 0.3 && wd.edge > wd.heart && wd.heart > 0 &&
     wd.edge < 0.5 && wd.stray > 1 && wd.hz && wd.hz[1] < 0.5 && life.breath > 0 && life.breath < 0.05,
     'IT TURNS, WANDERS AND BREATHES, AND ALL OF IT SLOWLY: spin ' + (life && life.spin) +
     ' rad/s, each point on its own path - ' + wd.heart + ' at the heart to ' + wd.edge + ' at the edge, ' +
     wd.stray + 'x for one in ' + Math.round(1 / (wd.strayShare || 0.1)) + ', at ' + JSON.stringify(wd.hz) +
     ' Hz - and a breath of ' + (life && life.breath) + ' at ' +
     (life && life.breathHz) + 'Hz - failure mode of a still cloud: a photograph of smoke, and of a ' +
     'fast one: a cloud that fidgets when the house is doing nothing',
     JSON.stringify(life));
  ok(!!geo && geo.rMax <= 1.0001 && geo.rMax >= 0.95,
     'IT REACHES ITS DECLARED RADIUS AND NO FURTHER: the farthest point is at ' +
     (geo && geo.rMax) + ' of the written radius ' + (geo && geo.radius) + ' - failure mode of a ' +
     'rejection sampler gone wrong: a ball that stops short (a smaller presence than the governor ' +
     'sized for) or points flung outside the window that masks the canvas',
     JSON.stringify(geo && { rMax: geo.rMax, radius: geo.radius }));
  const octLo = geo ? Math.min(...geo.octants) : 0, octHi = geo ? Math.max(...geo.octants) : 1;
  ok(!!geo && octLo >= 0.6 * octHi,
     'EVERY OCTANT CARRIES DUST: ' + (geo && geo.octants.join('/')) + ', the least ' +
     (octLo / octHi).toFixed(2) + ' of the most - failure mode of a seeded noise field that ' +
     'happens to empty one side: a lopsided cloud that reads as a crescent from half the yaws',
     JSON.stringify(geo && geo.octants));
  /* UI MANDATE IV: the dust is a membrane round a dim core glow, so its density is NOT monotone - it
     dips inside the membrane and peaks on it, and a smooth radial fall-off is what the mandate removed.
     The failure mode this assertion guards - an even fog with no heart - is claimed directly instead.
     Old: density falls at every shell. New: the heart is the densest shell, the outermost is thinner
     than the one inside it (the edge dissolves), and the densest is at least 5x the thinnest
     (measured 52x) - not a flat fill. */
  const dmax = geo ? Math.max(...geo.density) : 0, dmin = geo ? Math.min(...geo.density) : 1;
  const falls = !!geo && geo.density[0] === dmax && geo.density[4] < geo.density[3] && dmax >= 5 * dmin;
  ok(falls,
     'THE HEART IS THE DENSEST SHELL AND THE FILL IS NOT FLAT: ' +
     (geo ? DUST_SHELLS.map((s, i) => s + ' ' + geo.density[i]).join(' / ') : '-') +
     ' points per unit volume - the heart the most, the outermost shell thinner than the membrane ' +
     'inside it, the densest ' + (dmax / dmin).toFixed(0) + 'x the thinnest - failure mode of a flat ' +
     'fill: an even fog with no heart, which is the thing the mandate\'s "dense" rules out',
     JSON.stringify(geo && geo.density));
  ok(cine0.points === 13800 && cine0.points <= cine0.pointCap,
     'AND THE DECLARED POINT CAP HOLDS WITH THE WHOLE DUST ON: ' + cine0.points + ' of ' +
     cine0.pointCap + ' - the dust is the whole allocation by one constant, so the headroom is ' +
     'zero by design and a fill that asked for more would be truncated, not grown',
     JSON.stringify({ points: cine0.points, cap: cine0.pointCap }));
  /* UI MANDATE III PART 1B: the seed ball is worn smaller (0.86 -> 0.62) so that the bound on the
     furthest wandering stray - reachFill - lands inside the canvas's window. Old: scale 0.86,
     frameFill 0.6687. New: scale 0.62, frameFill 0.4822 (the seed), reachFill under 0.92. */
  /* UI MANDATE IV: a membrane to RMAX 1.45, worn at 0.545. Old (III): seed radius 1 at 0.62, fill
     0.4822. New: radius 1.45, scale 0.545, the furthest point 0.58-0.68 of the frame, the bound under 0.92. */
  ok(!!geo && geo.radius === 1.45 && geo.scale === 0.545 && geo.frameFill > 0.58 && geo.frameFill < 0.68 &&
     geo.reachFill > geo.frameFill && geo.reachFill < 0.92,
     'AND THE DUST IS WHERE MANDATE IV LEFT IT: a membrane to a radius of ' + (geo && geo.radius) + ' worn at ' +
     (geo && geo.scale) + ', its furthest point at ' + (geo && geo.frameFill) + ' of the frame half-height, every ' +
     'point BOUNDED at ' + (geo && geo.reachFill) + ' - inside the window - failure mode ' +
     'of a changed fill: the lookbook\'s four state plates stop being a valid comparison',
     JSON.stringify(geo));

  /* ================================ 3. THE HAZE IS GONE ================================ */
  /* UI MANDATE III PART 1 REMOVED THE SMOKE: twelve additive sprites that were the pale disc
     behind the presence, cut into a clean circle by the canvas's window. Each of this section's
     five assertions is replaced by the absence it now has to prove:
       old: A SMALL NUMBER OF LARGE SPRITES (12)     new: NO SPRITES, NO DOOR
       old: SHARING ONE MATERIAL                    new: NO SECOND SCENE PASS IN THE CHAIN
       old: AND NO FOG ANYWHERE                     new: AND NO FOG ANYWHERE (kept)
       old: IN ITS OWN SCENE, ONE GROUP             new: THE PRESENCE SCENE IS ONE OBJECT
       old: THE DRIFT IS CLAMPED                    new: THE WANDER IS BOUNDED, AND THE WINDOW
                                                         IS SIZED FROM THE BOUND */
  head('3. the haze is gone');
  const hz0 = await page.json('({door: typeof __galaxy.presence.smoke, sprites: __galaxy.presence.cine.sprites,' +
    ' haze: __galaxy.presence.cine.haze, fog: __galaxy.presence.cine.fog, objects: __galaxy.presence.objects,' +
    ' chain: __galaxy.presence.cine.chain, inner: __galaxy.presence.edge().inner,' +
    ' reach: __galaxy.presence.dust().geo.reachFill, pad: __galaxy.presence.cine.CINE.EDGE_PAD,' +
    ' max: __galaxy.presence.cine.CINE.EDGE_MAX})');
  note('the haze: ' + JSON.stringify(hz0));
  ok(hz0.door === 'undefined' && hz0.sprites === 0 && hz0.haze === false,
     'THERE ARE NO SPRITES AND NO DOOR TO THEM: presence.smoke is ' + hz0.door + ', the cinema counts ' +
     hz0.sprites + ' sprites and reports haze ' + hz0.haze + ' - failure mode of a haze turned down ' +
     'rather than removed: a layer at zero opacity that a config flag or a later round turns back on',
     JSON.stringify(hz0));
  ok((hz0.chain || []).filter((n) => n === 'RenderPass').length === 1,
     'AND NO SECOND SCENE PASS: the chain renders one scene, the presence\'s own (' +
     (hz0.chain || []).join(' -> ') + ') - failure mode: an empty haze pass still clearing and ' +
     'compositing a full-size target every frame for nothing',
     JSON.stringify(hz0.chain));
  ok(hz0.fog === false,
     'AND NO FOG ANYWHERE, WHICH IS §31\'S LAW: the presence scene carries none - failure mode of ' +
     'scene fog: it tints by depth, and the far half of the cloud would wear it as a veil',
     JSON.stringify({ fog: hz0.fog }));
  ok(hz0.objects === 1,
     'THE PRESENCE SCENE IS ONE OBJECT, the Points cloud, and nothing behind it - counted off the ' +
     'scene graph: ' + hz0.objects + ' - failure mode: a backing disc or glow mesh added to the ' +
     'scene, which is the background circle by another route',
     JSON.stringify({ objects: hz0.objects }));
  ok(hz0.reach > 0 && hz0.inner >= Math.min(hz0.max, hz0.reach + hz0.pad) - 0.0001 && hz0.reach < hz0.max,
     'THE WANDER IS BOUNDED, AND THE WINDOW IS SIZED FROM THE BOUND: the furthest a wandering point ' +
     'can be drawn is ' + hz0.reach + ' of the half-extent, and the window opens at ' + hz0.inner +
     ' - outside it, under the ' + hz0.max + ' cap - so no point is ever cut by the edge; failure ' +
     'mode of a wander with no bound: strays flung into the window\'s ramp and dimmed for being free',
     JSON.stringify(hz0));

  /* ====================================== 4. THE LIGHT ================================= */
  head('4. the light');
  note('chain: ' + (cine0.chain || []).join(' -> '));
  /* UI MANDATE III: the haze's pass is gone, so the chain is three. Old: 4. New: 3. */
  ok(cine0.composer === true && cine0.passes === 3,
     'THE POST CHAIN IS UP WITH THREE PASSES: failure mode of two: the OutputPass is the one ' +
     'missing, the tone mapping and colour space conversion never happen, and the whole deck ' +
     'reads as a washed-out bug nobody attributes to a missing pass',
     JSON.stringify({ composer: cine0.composer, passes: cine0.passes }));
  ok(JSON.stringify(cine0.chain) ===
       JSON.stringify(['RenderPass', 'UnrealBloomPass', 'OutputPass']),
     'IN THE ORDER presence -> bloom -> output, BY CLASS NAME AND NOT BY COUNT: ' +
     (cine0.chain || []).join(' -> ') + ' - failure mode of the bloom ahead of the render: it ' +
     'blooms last frame\'s buffer and the glow trails the cloud by a frame',
     JSON.stringify(cine0.chain));
  ok(cine0.bloomRes && cine0.side &&
     Math.abs(cine0.bloomRes[0] - cine0.side * cine0.scale) <= 1,
     'AND THE BLOOM IS STILL AT HALF RESOLUTION AFTER EVERY RESIZE THIS RUN HAS DONE: ' +
     JSON.stringify(cine0.bloomRes) + ' against a ' + cine0.side + 'px canvas at scale ' +
     cine0.scale + ' - failure mode without the setSize wrapper: the composer calls setSize ' +
     'with the real viewport on every resize and silently undoes the one decision that makes ' +
     'this affordable, so the cost appears days later as "the deck got slow"',
     JSON.stringify({ res: cine0.bloomRes, side: cine0.side, scale: cine0.scale }));
  /* THE FOUR CORNERS, with the bloom at FULL - AND MEASURED BY DIFFERENCE, which is a
     correction this harness earned on its first run.
     The first draft cropped each corner and asserted the luminance was under 0.10. It read 0.14
     to 0.16 and went red on a canvas that is perfectly transparent, because
     Page.captureScreenshot captures the COMPOSITED page: the deck's own starfield is behind the
     presence well, so a corner crop contains the ground showing THROUGH the canvas. 0.14 there
     is not a grey canvas, it is what transparency looks like over a lit deck - and an absolute
     threshold cannot tell the two apart in either direction. Failure mode of the absolute test,
     stated for the record: it is red when the deck is bright and green when the deck is dark,
     so it reports the wallpaper and never the thing it was written to catch.
     SO THE CANVAS IS HIDDEN AND THE SAME CROP TAKEN AGAIN - and the SECOND draft of this
     assertion was wrong too, in a way worth writing down because it is the more instructive
     error. It measured the canvas's own contribution by difference and required it to be under
     0.02. The contribution came back at +0.06 at all four corners, and the sign is the whole
     story: the canvas ADDS light there. An opaque clear cannot add light, it REPLACES it - the
     corner would go to the clear colour and stop depending on the deck behind it at all, so the
     difference would be NEGATIVE and large. A positive 0.06 is the additive haze, whose sprites
     reach 1.44 in natural units against a 1.06 reticle, plus the bloom's tail. Failure mode of
     the difference-magnitude test: it is red on a correct additive overlay and would have been
     "fixed" by dimming the haze, which is a real feature deleted to satisfy a wrong test.
     WHAT ACTUALLY DISCRIMINATES A CLEAR FROM A GLOW IS FALLOFF, so that is what is asserted:
       (a) nothing is destroyed - shown >= hidden at every corner, because an overlay that
           composites cannot be darker than the ground it composites over; and
       (b) the contribution FALLS OFF - the centre's contribution is many times the corner's. A
           flat opaque clear is uniform by definition, so it fails (b) with a ratio near 1,
           whatever its colour; a glow fails nothing.
     AND THE HAZE IS SWITCHED OFF FOR THIS ONE READING, which is the third correction and the
     last. With the smoke on, the falloff came back at 3.53x - under the 4x above - because a
     sprite had drifted toward the bottom-left corner and contributed 0.254 there on its own. The
     4x had been reasoned from the core's gaussian alone, and the haze is not the core's gaussian:
     its sprites reach 1.44 in natural units against a 1.06 reticle and they MOVE, so the corner's
     contribution depends on where twelve drifting sprites happen to be when the shutter opens.
     Failure mode of leaving it on: an assertion about ALPHA that passes or fails on where the
     haze drifted, i.e. a flaky test whose red says nothing about the thing it is named after.
     Switching the haze off costs this assertion nothing, because the smoke's own RenderPass -
     the pass that CLEARS, and therefore the one most likely to clear to opaque - still runs and
     still clears when the group inside it is invisible. The haze's reach is the bracket test's
     business, two assertions down, and it is measured photometrically there.
     The 4x in (b) is then on principle: with only the core and the bloom's tail in the frame, a
     corner 18px wide outside a core filling 59% of it is an order of magnitude down, and 4x sits
     well inside that and well outside the 1.0 a flat fill would give whatever its colour. */
  const box = await page.json(
    '(function(){var r=document.getElementById("presence-cvs").getBoundingClientRect();' +
    'return {x:r.left,y:r.top,w:r.width,h:r.height};})()');
  await page.evaluate('__galaxy.presence.cine.set({bloom:true})');
  await page.evaluate('__galaxy.face.pose("speaking")');
  await sleep(700);
  /* THE CORE'S CLOCK IS PINNED HERE TOO, for the reason the bracket assertion below spells out
     at length: the breath moves the canvas's own brightness by about ±0.04, and a difference
     measurement whose two halves sit at unrelated points of a 4-second cycle reports the breath. */
  await page.evaluate('__galaxy.presence.phase(0)');
  const CORNER = 18;
  /* FIVE REGIONS OF ONE SHOT, in coordinates relative to the canvas rect: four corners and the
     centre. One screenshot per state means the five readings are simultaneous. */
  const REG = [[0, 0], [box.w - CORNER, 0], [0, box.h - CORNER],
               [box.w - CORNER, box.h - CORNER],
               [(box.w - CORNER) / 2, (box.h - CORNER) / 2]]
    .map(([x, y]) => [x, y, CORNER, CORNER]);
  /* THREE PAIRS, MEDIANED PER REGION. The gap between the two states is the one window a
     drifting star can still slip through, so the pair is taken three times and the middle
     reading kept: a star crossing one crop corrupts one pair, not the median of three. */
  const pairs = [];
  for (let p = 0; p < 3; p++) {
    const on = await page.regions(box, REG);
    /* visibility and not display: display:none would take the canvas out of flow, the governor
       would resize the deck around the hole, and the crop would land on different pixels for a
       reason that has nothing to do with alpha. */
    await page.evaluate('document.getElementById("presence-cvs").style.visibility="hidden"');
    await sleep(140);
    const off = await page.regions(box, REG);
    await page.evaluate('document.getElementById("presence-cvs").style.visibility=""');
    await sleep(140);
    pairs.push({ on: on, off: off, d: on.map((v, i) => +(v - off[i]).toFixed(5)) });
  }
  await page.evaluate('__galaxy.presence.phase(null)');
  await page.evaluate('__galaxy.face.pose("idle")');
  await sleep(400);
  const med = (a) => { const s = a.slice().sort((x, y) => x - y); return s[Math.floor(s.length / 2)]; };
  const all5 = REG.map((_, i) => med(pairs.map((p) => p.d[i])));
  const contrib = all5.slice(0, 4);
  const midContrib = all5[4];
  const shown = pairs[1].on.slice(0, 4);
  const hidden = pairs[1].off.slice(0, 4);
  const worstCorner = Math.max(...contrib.map(Math.abs));
  const falloff = worstCorner > 0.0001 ? +(midContrib / worstCorner).toFixed(2) : 999;
  pairs.forEach((p, i) => note('pair ' + (i + 1) + ' corner contributions: ' +
                               p.d.slice(0, 4).join(', ') + ' · centre ' + p.d[4]));
  note('median contribution: corners ' + contrib.join(', ') + ' · centre ' +
       midContrib + ' · falloff ' + falloff + 'x');
  ok(contrib.every((d) => d >= -T.CORNER_LUM) && falloff >= T.FALLOFF,
     'THE PRESENCE CANVAS STILL COMPOSITES OVER THE DECK RATHER THAN REPLACING IT, WITH THE ' +
     'BLOOM AT FULL AND NO HAZE (UI mandate III removed it) SO ALPHA IS THE ONLY VARIABLE: no corner is darker ' +
     'than the ground beneath it (median contributions over three tightly-paired shots ' +
     contrib.join('/') + ', none below -' + T.CORNER_LUM + '), and what the canvas does add ' +
     'FALLS OFF - the centre contributes ' + midContrib + ' against a worst corner of ' +
     worstCorner.toFixed(5) + ', a ratio of ' + falloff + 'x over the named ' + T.FALLOFF + 'x - ' +
     'which is a glow and not a fill, because a pass that cleared to opaque would contribute ' +
     'the SAME amount everywhere and give a ratio near 1 whatever colour it cleared to; failure ' +
     'mode of the defect this catches: a black square the size of the well sitting over the ' +
     'deck\'s own ground, which reads as a layout bug rather than as a render-target clear and ' +
     'would be looked for in the governor for a week',
     JSON.stringify({ shown: shown, hidden: hidden, contrib: contrib, mid: midContrib,
                      falloff: falloff }));
  /* AND THE BRACKETS, photometrically - WITH THE CORE'S CLOCK PINNED, which is the difference
     between this assertion and a green that means nothing.
     The first version took one shot with the haze on and one with it off and required the
     difference to be under 0.08 in magnitude. It read +0.043 on one run and -0.039 on the next,
     on the same build. A NEGATIVE gain is the tell: twelve additive sprites cannot make a crop
     darker, so whatever that number was measuring, it was not the haze. It was the core's BREATH
     - the brackets are part of the core's own point cloud, the breath moves their brightness by
     about ±0.04, and the two shots were taken ~600ms apart at unrelated points in a 4-second
     cycle. Failure mode of that version, which is the one worth remembering: it passed, under a
     tolerance that happened to be wider than the breath, and it would have gone on passing with
     the haze parked directly over the brackets. A tolerance large enough to absorb a confounder
     is a tolerance large enough to absorb the defect.
     SO THE CLOCK IS PINNED. presence.phase(0) holds uPhase - which the breath, the precession,
     the shell's turn and the travelling arc all read - and zeroes both event envelopes, so the
     core is pixel-identical between the two shots and the haze is the only thing that changed.
     AND THE HAZE IS SAMPLED OVER TIME RATHER THAN ONCE, because the sprites drift and the
     mandate's word is "never". Five samples across five seconds, worst one asserted: the claim
     becomes "at no sampled moment did the haze add more than 0.08 at the brackets", which is
     what "never occluding the Eyes brackets" actually means. The pin does not stop the drift -
     presSmokeFrame has its own clock - and that is exactly why it is safe to sample over it. */
  /* REPLACES "AND THE HAZE NEVER OCCLUDES THE EYES' BRACKETS". The haze had its own clock - the
     sprites drifted while the presence's clock was pinned - which is why that assertion sampled
     five seconds of drift. With the haze gone, NOTHING on the presence canvas runs on a clock of
     its own: pin the presence's clock and the canvas must hold still, pixel for pixel. Read off
     the presence's own canvas (presence.snap), so the deck's moving sky behind it is not in the
     reading. Old: haze gain at the brackets <= 0.08. New: lit pixels changed across five
     snapshots over 5.6s with the clock pinned <= STILL (zero). */
  await page.evaluate('__galaxy.presence.set("dust")');
  await page.evaluate('__galaxy.presence.phase(0.3)');
  await sleep(700);
  const stills = [];
  for (let i = 0; i < 5; i++) {
    stills.push(JSON.parse(await page.evaluate('__galaxy.presence.snap(160).then(function(s){return JSON.stringify(s)})')));
    await sleep(1400);
  }
  await page.evaluate('__galaxy.presence.phase(null)');
  const bitsDiff = (a, b) => { let n = 0; for (let i = 0; i < a.length; i++) { let x = parseInt(a[i], 16) ^ parseInt(b[i], 16); while (x) { n += x & 1; x >>= 1; } } return n; };
  const changed = stills.slice(1).map((s) => bitsDiff(stills[0].mask, s.mask));
  const litPx = (stills[0].mask.match(/[1-9a-f]/g) || []).length;
  note('pinned presence, lit pixels changed vs the first snapshot: ' + changed.join(', ') +
       ' (of a mask with ~' + litPx + ' lit nibbles)');
  ok(stills.every((s) => !s.error && s.mask) && changed.every((c) => c <= T.STILL) && litPx > 50,
     'AND NOTHING ON THE PRESENCE CANVAS RUNS ON A CLOCK OF ITS OWN: with the presence\'s clock ' +
     'pinned, five snapshots of its own canvas over 5.6 seconds differ by ' + changed.join('/') +
     ' lit pixels - the haze it replaces drifted on its own clock under the same pin, which is what ' +
     'this section used to have to sample; failure mode: a second layer animating behind the ' +
     'presence, which is a background by another name',
     JSON.stringify({ changed: changed, lit: litPx }));

  /* ======================================= 5. THE TEXT ================================= */
  head('5. the text and the card edges, with bloom at full');
  /* ASSERTED AS PIXEL IDENTITY, NOT AS A CONTRAST RATIO, and the reason is structural: the
     bloom runs inside the PRESENCE's own renderer and composer, whose output is one canvas in
     one corner of the deck. UI text is DOM. So the correct claim is not "the text still has
     enough contrast" - it is "the bloom cannot touch the text at all", and the strongest
     available evidence for that is two screenshots of the same text crop, one with the bloom at
     full strength and one with it off, that are byte-identical.
     TWO SURFACES PER WIDTH, AND BOTH ARE CHOSEN FOR BEING STILL - which is what makes identity a
     fair test rather than a race against an animation:
       TEXT is #title h1, "Knowledge Galaxy" - a real heading at a real weight, rendered once and
       never rewritten. Not #p-label, which is the panel's heading and is EMPTY until a star is
       opened; not #stats, which is live and would make two shots differ for a reason that has
       nothing to do with the bloom; not #caption, which is gone four seconds after he speaks.
       A CARD EDGE is the leftmost 10px column of #bar, the ask bar: its border, its backdrop
       blur and nothing else. The column is deliberately narrow enough to exclude #seal's dot,
       which breathes - a crop containing a breathing dot cannot be asserted as identical and the
       temptation would be to loosen the threshold until it passed. */
  const CROPS = [
    ['#title h1 (text)',
     '(function(){var e=document.querySelector("#title h1");if(!e)return null;' +
     'var r=e.getBoundingClientRect();if(r.width<8)return null;' +
     'return {x:Math.max(0,r.left-4),y:Math.max(0,r.top-4),w:Math.min(420,r.width+8),' +
     'h:Math.min(70,r.height+8)};})()'],
    ['#bar left edge (card)',
     '(function(){var e=document.getElementById("bar");if(!e)return null;' +
     'var r=e.getBoundingClientRect();if(r.width<8)return null;' +
     'return {x:Math.max(0,r.left-2),y:r.top,w:10,h:Math.min(70,r.height)};})()'],
  ];
  for (const [w, h] of WIDTHS) {
    await page.send('Emulation.setDeviceMetricsOverride',
      { width: w, height: h, deviceScaleFactor: 1, mobile: false });
    await sleep(700);
    await page.evaluate('__galaxy.layout.run()');
    await sleep(700);
    for (const [label, expr] of CROPS) {
      const tbox = await page.json(expr);
      if (!tbox || tbox.w < 8) { note(w + ': ' + label + ' is not on screen'); continue; }
      /* THE BLOOM AT FULL MEANS SPEAKING, not merely enabled: idle strength is 0.55 and the
         mandate's words are "with bloom at full strength", which only happens on a syllable. */
      await page.evaluate('__galaxy.presence.cine.set({bloom:true})');
      await page.evaluate('__galaxy.face.pose("speaking")');
      await sleep(900);
      const lit = await page.raw(tbox);
      const litPx = await page.pixels(tbox);
      await page.evaluate('__galaxy.face.pose("idle")');
      await page.evaluate('__galaxy.presence.cine.set({bloom:false})');
      await sleep(900);
      const dark = await page.raw(tbox);
      const darkPx = await page.pixels(tbox);
      await page.evaluate('__galaxy.presence.cine.set({bloom:true})');
      const same = lit === dark && lit.length > 0;
      const dRgb = Math.max(...litPx.rgb.map((v, i) => Math.abs(v - darkPx.rgb[i])));
      note(w + 'x' + h + ' ' + label + ': ' + (same ? 'byte-identical' :
           'differs, worst channel ' + dRgb.toFixed(3)) + ', crop mean ' + litPx.mean);
      ok(same || dRgb <= T.TEXT_DELTA,
         'UI TEXT AND CARD EDGES DO NOT BLOOM AT ' + w + 'x' + h + ' - ' + label + ': the same ' +
         'crop with the bloom at FULL (a speaking frame, not merely enabled) and with it off is ' +
         (same ? 'byte-identical' : 'within ' + dRgb.toFixed(2) + ' of a channel, under the ' +
          'named tolerance of ' + T.TEXT_DELTA) + ' - failure mode of a global bloom: the ' +
         'strength that makes a hologram glow also smears every 10.5px label on the deck, and ' +
         'the first thing anyone blames is the font',
         JSON.stringify({ same: same, dRgb: dRgb, lit: litPx.rgb, dark: darkPx.rgb, box: tbox }));
    }
  }
  await page.send('Emulation.setDeviceMetricsOverride',
    { width: 1600, height: 900, deviceScaleFactor: 1, mobile: false });
  await sleep(600);
  await page.evaluate('__galaxy.layout.run()');
  await sleep(600);

  /* =================================== 6. THE SPEAKING GLOW =========================== */
  head('6. the speaking glow');
  /* DRIVEN THROUGH THE DOOR THE DECK ITSELF USES, face.pose("speaking") - the cadence path,
     which headless is the only one available and is also the WEAKER one: its rises are about a
     quarter of a real syllable onset's. A glow that shows up on cadence shows up on piper. */
  const boxNow = await page.json(
    '(function(){var r=document.getElementById("presence-cvs").getBoundingClientRect();' +
    'return {x:r.left,y:r.top,w:r.width,h:r.height};})()');
  const coreClip = { x: boxNow.x + boxNow.w * 0.22, y: boxNow.y + boxNow.h * 0.22,
                     w: boxNow.w * 0.56, h: boxNow.h * 0.56 };
  /* EACH STATE IS AVERAGED OVER A WHOLE PERIOD OF ITS OWN OSCILLATION, which is the correction
     this assertion earned on its second run: one idle shot against one speaking shot gave a ratio
     of 1.0056 where the run before had given 1.1646 on the same build. Neither reading was wrong
     and the glow was never broken - both states MOVE, on two unrelated clocks:
       the breath  - CORE_BREATH * sin(2*pi*CORE_BREATH_HZ*t) on the core's scale, a slow cycle
                     which the shader STANDS DOWN while a sentence is in flight (see the comment
                     at `float breath` in presCore: "the object breathes at rest and holds still
                     to talk"), so the idle state has a swing the speaking state does not;
       the cadence - face.beat seconds per chunk, a raised cosine between 0.34 and 0.78 of gain.
     A single pair therefore samples two sine waves at two arbitrary phases and divides. Worse
     than noisy: it can read a correct build as a LOSS, because an idle shot caught at the top of
     the breath is being compared against a speaking frame that has no breath left in it at all.
     Unlike every other photometric assertion in this file the clock cannot be pinned here -
     presence.phase(0) zeroes uPulse and uFlare, which are the very envelopes the speech drives,
     so pinning would freeze the subject. So each state is sampled for AT LEAST ONE FULL PERIOD of
     the oscillation that is live in it and the means are compared: over a whole cycle the breath
     sine integrates to zero and the idle mean is the true base, while the speaking mean carries
     the cadence envelope's own average, which is positive at every phase because the cadence
     floor is 0.34 and not 0. Both periods are READ FROM THE DOORS (presence.life.breathHz, face.beat)
     and not typed in, for the same reason the shell radius is.
     Failure mode of comparing maxima instead: it needs the breath peak and a syllable onset to
     land in the same shutter, which is luck, and it would have been "fixed" by widening the
     threshold until luck was no longer required - a test tuned to pass. That is not a prediction:
     the printed series below it have already shown an idle run whose own maximum, 0.45819, was
     ABOVE the brightest of thirteen speaking frames, 0.4471, on a build where the means differed
     by 18% in the right direction. The idle maximum has the periodic band flare in it as well as
     the breath, and neither is the subject. Failure mode of the
     single pair: a flaky red on correct code, which is worse than a flaky green, because the next
     person to see it spends an hour inside the glow looking for a defect that is not there. */
  await page.evaluate('__galaxy.presence.cine.set({bloom:true})');
  await sleep(1200);
  const clocks = await page.json(
    '({breathHz: __galaxy.presence.life.breathHz, beat: __galaxy.face.beat})');
  const BREATH_MS = Math.round(1000 / (clocks.breathHz || 0.11));
  const BEAT_MS = Math.round(1000 * (clocks.beat || 1.6));
  /* N SAMPLES EVENLY SPACED ACROSS THE SPAN, AND THE COUNT IS DELIBERATELY SMALL. The first
     version of this sampler took a reading every 160ms for as long as the span lasted, which came
     to 35 shots across one breath and 13 across two beats - and the third run of it died with
     `Page.captureScreenshot timed out` after forty seconds inside this very loop. Forty-eight
     back-to-back captures, each one a CDP round trip plus an in-page PNG decode on the same main
     thread the render loop is on, with the vsync clamp off so that loop is already running flat
     out: the instrument was loading the thing it was measuring until the compositor stopped
     answering. Evenly spaced samples over exactly one period cancel a sine at twelve as well as
     they do at thirty-five - it is the PHASE COVERAGE that cancels it, not the count - so the
     honest fix is fewer shots, not a bigger timeout.
     Failure mode of raising the 40s bomb instead: the harness would have gone green by waiting
     out a stall it was itself causing, and the next section to add a screenshot loop would
     inherit a timeout tuned to hide it. */
  const lumSeries = async (spanMs, n) => {
    const v = [];
    const step = Math.max(80, Math.round(spanMs / n));
    const t0 = Date.now();
    for (let i = 0; i < n; i++) {
      const due = t0 + i * step;
      const wait = due - Date.now();
      if (wait > 0) await sleep(wait);
      v.push((await page.regions(coreClip, [[0, 0, coreClip.w, coreClip.h]]))[0]);
    }
    return { v, span: Date.now() - t0, n: v.length, step,
             mean: +(v.reduce((a, b) => a + b, 0) / v.length).toFixed(5),
             min: Math.min(...v), max: Math.max(...v) };
  };
  /* ONE BREATH CYCLE FOR THE IDLE READING, TWO CADENCE CYCLES FOR THE SPEAKING ONE - the shortest
     spans over which each confounder averages out, and no longer, because every sample is a
     screenshot and this section is already the slowest in the file. */
  const idleSeries = await lumSeries(BREATH_MS, 12);
  const idleCine = await page.json('__galaxy.presence.cine');
  await page.evaluate('__galaxy.face.pose("speaking")');
  await sleep(600);
  const speakSeries = await lumSeries(BEAT_MS * 2, 10);
  const speakCine = await page.json(
    '({strength: __galaxy.presence.cine.strength, peak: __galaxy.presence.cine.glowPeak,' +
    ' env: __galaxy.presence.cine.env, level: __galaxy.presence.level,' +
    ' from: __galaxy.presence.from, pulses: __galaxy.presence.pulses})');
  const idleLum = { mean: idleSeries.mean };
  const speakLum = { mean: speakSeries.mean };
  await page.evaluate('__galaxy.face.pose("idle")');
  await sleep(T.SETTLE_MS + 120);
  const settled = await page.json(
    '({strength: __galaxy.presence.cine.strength, env: __galaxy.presence.cine.env,' +
    ' from: __galaxy.presence.from})');
  note('strength idle ' + idleCine.strength + ' -> speaking peak ' + speakCine.peak +
       ' -> ' + settled.strength + ' one second after silence');
  note('core crop luminance idle ' + idleLum.mean + ' -> speaking ' + speakLum.mean +
       ' (ratio ' + (speakLum.mean ? (speakLum.mean / idleLum.mean).toFixed(4) : '-') + ')');
  note('idle    ' + idleSeries.n + ' samples over ' + idleSeries.span + 'ms (one breath of ' +
       BREATH_MS + 'ms), ' + idleSeries.min + ' .. ' + idleSeries.max);
  note('speaking ' + speakSeries.n + ' samples over ' + speakSeries.span + 'ms (two beats of ' +
       BEAT_MS + 'ms), ' + speakSeries.min + ' .. ' + speakSeries.max);
  ok(idleCine.strength === idleCine.idle,
     'AT REST THE BLOOM SITS AT ITS DECLARED IDLE STRENGTH: ' + idleCine.strength + ' = ' +
     idleCine.idle + ' - failure mode of an idle that drifts: every later comparison in this ' +
     'section is against a moving baseline and the speaking rise cannot be attributed',
     JSON.stringify({ strength: idleCine.strength, idle: idleCine.idle }));
  ok(speakCine.peak >= T.GLOW_MIN && speakCine.peak > idleCine.strength,
     'WHEN GALAXY SPEAKS THE HALO BLOOMS IN SYLLABLE STEP: strength peaked at ' +
     speakCine.peak + ', over the named floor of ' + T.GLOW_MIN + ' and over the idle ' +
     idleCine.strength + ', driven by the real level source "' + speakCine.from + '" rather ' +
     'than by a uniform this harness wrote - failure mode of a harness-set uniform: it proves ' +
     'the harness can assign a number',
     JSON.stringify(speakCine));
  ok(speakLum.mean > idleLum.mean * T.LUM_RISE,
     'AND IT IS VISIBLE IN PIXELS AND NOT ONLY IN THE READOUT: the core crop averages ' +
     speakLum.mean + ' over ' + speakSeries.n + ' speaking frames against ' + idleLum.mean +
     ' over ' + idleSeries.n + ' idle frames, a ratio of ' +
     (speakLum.mean / idleLum.mean).toFixed(4) + ' over the named threshold of ' + T.LUM_RISE +
     ' - failure mode of asserting the readout alone: cine.strength can rise while ' +
     'presBloomPass.enabled is false and nothing on the glass changes at all, which is exactly ' +
     'what an auto-revert leaves behind',
     JSON.stringify({ idle: idleSeries, speak: speakSeries }));
  ok(Math.abs(settled.strength - idleCine.idle) <= T.SETTLE_EPS && settled.from === 'rest',
     'AND IT SETTLES BACK TO BREATH WITHIN ONE SECOND OF SILENCE: ' + settled.strength +
     ' against an idle of ' + idleCine.idle + ' (tolerance ' + T.SETTLE_EPS + ') with the level ' +
     'source back to "' + settled.from + '" - failure mode of a slow decay: the deck stays lit ' +
     'after he stops talking, so the one thing the glow is supposed to mean stops being ' +
     'information',
     JSON.stringify(settled));
  /* THE HEARTBEAT OUTLIVES THE BLOOM, which is the mandate's words: "The speaking pulse is
     load-bearing: bloom may die before the heartbeat does." */
  await page.evaluate('__galaxy.presence.cine.set({bloom:false})');
  await page.evaluate('__galaxy.face.pose("speaking")');
  await sleep(2600);
  const noBloomPulse = await page.json(
    '({pulses: __galaxy.presence.pulses, pulse: __galaxy.presence.pulse,' +
    ' level: __galaxy.presence.level, from: __galaxy.presence.from,' +
    ' bloom: __galaxy.presence.cine.bloom})');
  await page.evaluate('__galaxy.face.pose("idle")');
  await page.evaluate('__galaxy.presence.cine.set({bloom:true})');
  ok(noBloomPulse.bloom === false && noBloomPulse.pulses > speakCine.pulses &&
     noBloomPulse.from === 'cadence',
     'AND THE HEARTBEAT OUTLIVES THE BLOOM: with the bloom switched off the core still pulsed ' +
     (noBloomPulse.pulses - speakCine.pulses) + ' more times on the same utterance path - ' +
     'failure mode of wiring the modulation THROUGH the bloom: the auto-revert that saves a ' +
     'slow machine also silences the one signal that says he is speaking, and the mandate ' +
     'names that the wrong way round on purpose',
     JSON.stringify(noBloomPulse));
  /* THE QUIET TONGUE CLAUSE, which is satisfied BY CONSTRUCTION rather than by a second path -
     and that is the assertion. tongueNormalize rewrites the WORDS; the audio still leaves
     through speechBus into presAnal, which is the only analyser the presence has. */
  const tongue = await page.json(
    '({normalize: typeof (__galaxy.voice && __galaxy.voice.normalize), ' +
    ' analyser: __galaxy.presence.analyser, from: __galaxy.presence.from})');
  ok(tongue.normalize === 'function',
     'AND THE QUIET TONGUE DRIVES IT EXACTLY AS TTS DOES, BY CONSTRUCTION: ' +
     '__galaxy.voice.normalize is a ' + tongue.normalize + ' on the TEXT, and there is one ' +
     'audio funnel - speechBus into presAnal - so the read-aloud path cannot fail to drive the ' +
     'glow without the spoken path failing too; failure mode of a second playback path: a ' +
     'read-aloud that is silent on the glass, and a harness that passes because it only ever ' +
     'tested the other one',
     JSON.stringify(tongue));

  /* ====================================== 7. THE STREAM =============================== */
  head('7. the stream');
  const s0 = await page.json('__galaxy.presence.stream()');
  const burst = await page.json('__galaxy.presence.stream(6)');
  await sleep(320);
  const mid = await page.json('__galaxy.presence.stream()');
  ok(burst.filter((x) => x === 'queued').length === 6 && mid.inflight === true &&
     mid.queued === 5,
     'ONE PARTICLE IN FLIGHT AND THE REST QUEUED: six sends left one flying and ' + mid.queued +
     ' waiting - failure mode of a dot per citation: six overlapping flights on a six-chip ' +
     'answer, which reads as a burst of noise rather than as six deliveries, and a leaked ' +
     'element every time a re-render interrupts one',
     JSON.stringify(mid));
  ok(mid.at && /translate3d/.test(mid.at.transform) && !/left|top/.test(mid.at.transform),
     'MOVING ON transform AND opacity ONLY, WHICH IS THE HOUSE\'S CINEMATIC LAW: ' +
     mid.at.transform + ' - failure mode of animating left/top: layout on every frame of every ' +
     'delivery, on the one element that crosses the whole deck',
     JSON.stringify(mid.at));
  await sleep(6 * (s0.ms + s0.gap) + 500);
  const afterBurst = await page.json('__galaxy.presence.stream()');
  ok(afterBurst.flown - s0.flown === 6 && afterBurst.queued === 0 &&
     afterBurst.inflight === false && afterBurst.raf === false,
     'EVERY QUEUED FLIGHT COMPLETES AND THEN THE LOOP STOPS ITSELF: ' +
     (afterBurst.flown - s0.flown) + ' delivered, queue empty, no rAF pending - failure mode of ' +
     'a loop that keeps running: the stream\'s cost in the frame-time table becomes a permanent ' +
     'tax rather than the price of a delivery, and the table attributes it to the core',
     JSON.stringify(afterBurst));
  const flood = await page.json(
    '(function(){var r=__galaxy.presence.stream(40);var c={};' +
    'r.forEach(function(x){c[x]=(c[x]||0)+1});return c;})()');
  const afterFlood = await page.json('__galaxy.presence.stream()');
  ok(flood.queued === 8 && flood.dropped === 32,
     'AND THE QUEUE HAS A CEILING WITH A COUNTER RATHER THAN AN APPETITE: forty sends became ' +
     flood.queued + ' queued and ' + flood.dropped + ' dropped at a declared maximum of ' +
     s0.max + ' - failure mode of an unbounded queue: a Scholar that keeps twenty notes in one ' +
     'tick leaves the deck streaming for half a minute after it has finished working',
     JSON.stringify({ flood: flood, dropped: afterFlood.dropped }));
  const overlay = await page.json(
    '(function(){var h=document.getElementById("cine-stream");if(!h)return null;' +
    'var c=getComputedStyle(h);return {pe:c.pointerEvents, pos:c.position, z:c.zIndex,' +
    ' boot:getComputedStyle(document.getElementById("boot")||document.body).zIndex,' +
    ' kids:h.children.length, aria:h.getAttribute("aria-hidden")};})()');
  ok(overlay && overlay.pe === 'none' && overlay.pos === 'fixed' &&
     Number(overlay.z) < Number(overlay.boot) && overlay.kids === 1,
     'THE OVERLAY IS A FIXED, UNCLICKABLE, SINGLE-CHILD HOST UNDER THE BOOT CURTAIN: ' +
     'pointer-events ' + overlay.pe + ', z-index ' + overlay.z + ' against #boot\'s ' +
     overlay.boot + ' - failure mode of a higher z: a particle flies across the boot curtain ' +
     'during the ceremony; failure mode of pointer-events auto: a 14px dead zone wandering ' +
     'across every control on the deck',
     JSON.stringify(overlay));
  const hooks = /cineStreamCites\(\);/.test(SOURCE) &&
                /cineStreamKeep\(study\.state && study\.state\.kept\)/.test(SOURCE);
  ok(hooks,
     'AND BOTH HOOKS ARE WIRED WHERE THE MANDATE PUTS THEM: cineStreamCites() after ' +
     'renderAnswer\'s own layout() call, and cineStreamKeep() on the Scholar\'s kept counter in ' +
     'studyApply and studyPost - failure mode of the citation hook placed before layout(): the ' +
     'chips\' boxes are read in the PREVIOUS answer\'s geometry, so every particle leaves from ' +
     'where the old citation row used to be',
     'cites hook / keep hook: ' + hooks);

  /* ======================================= 8. THE PRICE =============================== */
  head('8. the price, per effect, by interleaved pairs');
  /* TWO INSTRUMENTS, AND EACH IS USED ONLY FOR WHAT IT CAN RESOLVE. This is the third attempt at
     this section and the first one that is honest, so the two discarded ones are written down.
       ATTEMPT ONE read presence.fps with each effect off in turn. It returned 60.000 on every
       row of every width with everything on AND with everything off, because the rAF loop is
       clamped to the display: any chain under 16.7ms reads exactly 60. A saturated instrument.
       ATTEMPT TWO ran the same ladder with --disable-gpu-vsync, which does uncap the loop and
       does give a true whole-frame time including the GPU. But the differences came back as
       -0.126, +0.032, -0.277 ms for the bloom against a noise floor, measured in-run, of 0.145
       ms: a NEGATIVE cost for a pass that certainly costs something. The instrument is not
       wrong, it is too coarse - the whole frame also contains the deck's force graph, the
       starfield and the compositor, and the effect being priced is 2% of it. Failure mode if
       that table had been published: three rows of noise with minus signs, presented as a
       budget, and the one real claim in the section - containment - discredited along with them.
     SO: cine.cost(n) FOR ATTRIBUTION, FRAME TIME FOR CONTAINMENT.
       cine.cost(n) runs n renders of the real chain back to back in one task and divides. It
       sees only the presence - no graph, no compositor, no scheduler - so a 0.3ms pass is 7% of
       its signal instead of 2% of a much noisier one. That is what makes the per-effect column
       resolvable. What it does NOT see is the GPU work the driver has not made it wait for, so
       it must never be used for containment.
       The uncapped whole-frame time is the opposite: it sees everything including the GPU, and
       it is the only reading from which "this fits in 16.67ms" is a true statement.
     BOTH ARE PRINTED ON EVERY ROW, labelled, and each assertion names which one it rests on.
     ATTEMPT THREE - the one this file shipped first - used cine.cost correctly and still gated it
     wrongly, which is worth as much space as the other two. It took the four medians SEPARATED IN
     TIME (all, then a flag change and a settle, then -bloom, and so on) and compared the
     difference against a floor measured as |A - B| for one more pair of identical medians. On
     three runs of the same build that floor came back 0.028, 0.145 and 0.148 ms while the bloom
     came back 0.098, 0.100 and 0.157 - so one reading was four times its floor, the next was
     under it, and the assertion flipped red on the third run with nothing changed but the weather
     on this machine. Two design errors, neither in the viewer:
       a) SEPARATION. Four readings taken over several seconds with flag changes between them put
          anything that drifts on that scale - another process, the deck's graph, the GPU's clock -
          inside the subtraction instead of outside it.
       b) A FLOOR FROM ONE PAIR. |A - B| for a single pair is one sample of a noise distribution
          used as though it were that distribution's width; its own spread is about as large as
          its mean, which is the three-to-one swing above. _runs/_cinepair.mjs measured it: ten
          such pairs gave 0.002 to 0.032 ms, and a separate null run produced a single -0.148
          outlier - so the floor is usually tiny and occasionally enormous, and which one a run
          gets is luck.
     SO THE PRICE IS NOW PAIRED AND INTERLEAVED: on, off, on, off, k times, with the difference of
     each adjacent pair kept. Drift is common to both halves of a pair and cancels; the standard
     error of the k differences is a real estimate of the floor, from the same data. The probe
     settles what that buys - ten paired differences for the bloom came back 0.079 to 0.099 ms
     (mean 0.0888, se 0.0022) and a second set 0.074 to 0.119 (mean 0.0991, se 0.0045), while the
     NULL - on against on, where the true answer is zero - straddled zero at mean -0.0116 with an
     se of 0.0174. Twenty differences out of twenty positive for the bloom; the null's sign is a
     coin. That is a resolved measurement and the gate below is built from it: the mean must clear
     twice its own standard error AND the differences must agree in sign, which is a sign test and
     needs no assumption about the shape of the noise at all.
     Failure mode of keeping the separated version with a wider floor: the one honest row in the
     section becomes unfalsifiable, because a floor wide enough to absorb a 0.148 ms outlier is
     wide enough to absorb the entire bloom pass. */
  const CN = 240;                     // the cost door's ceiling - the longest sample it allows
  const costOf = async (n) => {       // median of three, for the same reason frameMs takes three
    const got = [];
    for (let i = 0; i < 3; i++) {
      const c = await page.json('__galaxy.presence.cine.cost(' + CN + ')');
      if (c && c.perFrame) got.push(c.perFrame);
      await sleep(120);
    }
    got.sort((a, b) => a - b);
    return got.length ? got[Math.floor(got.length / 2)] : 0;
  };
  /* ONE EFFECT'S PRICE, PAIRED. `k` pairs of (flag on, flag off) back to back, differences kept.
     `pos` is how many of them came out positive - the sign test - and `se` is the standard error
     of their mean, which is the floor this reading is gated against. */
  const PAIRS = 8;
  const priceOf = async (flag, k) => {
    const d = [];
    for (let i = 0; i < k; i++) {
      await page.evaluate('__galaxy.presence.cine.set({' + flag + ':true})');
      await sleep(140);
      const on = await costOf();
      await page.evaluate('__galaxy.presence.cine.set({' + flag + ':false})');
      await sleep(140);
      const off = await costOf();
      d.push(+(on - off).toFixed(3));
    }
    await page.evaluate('__galaxy.presence.cine.set({' + flag + ':true})');
    const mean = d.reduce((a, b) => a + b, 0) / d.length;
    const sd = Math.sqrt(d.reduce((a, b) => a + (b - mean) * (b - mean), 0) /
                         Math.max(1, d.length - 1));
    return { d, k: d.length, mean: +mean.toFixed(4), sd: +sd.toFixed(4),
             se: +(sd / Math.sqrt(d.length)).toFixed(4), pos: d.filter((x) => x > 0).length,
             lo: Math.min(...d), hi: Math.max(...d) };
  };
  console.log('       width        -- dispatch ms, cine.cost(' + CN + ') --    ' +
              'paired mean +- se, ' + PAIRS + ' pairs, +ve   whole frame');
  console.log('                    all   -bloom  -smoke   core      bloom              ' +
              'smoke                 all');
  const table = [];
  for (const [w, h] of WIDTHS) {
    await page.send('Emulation.setDeviceMetricsOverride',
      { width: w, height: h, deviceScaleFactor: 1, mobile: false });
    await sleep(700);
    await page.evaluate('__galaxy.layout.run()');
    await sleep(800);
    await page.evaluate('__galaxy.presence.cine.set({bloom:true,smoke:true})');
    const all = await costOf();
    const allFrame = await frameMs(page);
    await page.evaluate('__galaxy.presence.cine.set({bloom:false})');
    const noB = await costOf();
    await page.evaluate('__galaxy.presence.cine.set({smoke:false})');
    const none = await costOf();
    await page.evaluate('__galaxy.presence.cine.set({bloom:true})');
    const noS = await costOf();
    await page.evaluate('__galaxy.presence.cine.set({smoke:true})');
    /* THE FOUR MEDIANS ARE KEPT AS CONTEXT AND NO LONGER CARRY A CLAIM. They are the chain's
       absolute dispatch cost in each configuration, which is worth printing - a reader can see
       that the whole presence costs a sixth of a millisecond to dispatch - but the per-effect
       SUBTRACTION of two of them is the separated design this section stopped trusting. The
       priced columns beside them are paired. */
    const pb = await priceOf('bloom', PAIRS);
    const ps = await priceOf('smoke', PAIRS);
    const row = { w: w, h: h, all: all, noB: noB, noS: noS, none: none, frame: allFrame,
                  bloom: pb.mean, smoke: ps.mean, pb: pb, ps: ps };
    table.push(row);
    console.log('       ' + (w + 'x' + h).padEnd(12) +
                String(all).padStart(7) + String(noB).padStart(8) + String(noS).padStart(8) +
                String(none).padStart(7) +
                ('    ' + pb.mean.toFixed(3) + ' +- ' + pb.se.toFixed(3) +
                 ' ' + pb.pos + '/' + pb.k).padEnd(26) +
                (ps.mean.toFixed(3) + ' +- ' + ps.se.toFixed(3) +
                 ' ' + ps.pos + '/' + ps.k).padEnd(22) +
                String(allFrame).padStart(8) + ' ms');
  }
  table.forEach((r) => note('paired differences at ' + r.w + ': bloom ' + r.pb.d.join(' ') +
                            ' · smoke ' + r.ps.d.join(' ')));
  /* THE STREAM IS THE ONE EFFECT cine.cost CANNOT SEE AT ALL, and that is a fact about the
     effect rather than a gap in the instrument: the particle is a DOM element on its own
     compositor layer moving on transform and opacity. It never enters presComposer.render, so
     the cost door is blind to it BY CONSTRUCTION and the only instrument left is the whole
     frame - where it is NOT resolvable at all. Three runs of the difference, same build, same
     machine, nothing else changed: -0.037 ms, +0.465 ms, -1.944 ms, against noise floors of
     0.069 to 0.145 ms. It changes sign. There is no threshold that makes a quantity like that
     into a measurement, and the mistake would be to keep widening a bound until the sign stops
     mattering - that is a test tuned to pass rather than a test of anything.
     SO THE ASSERTION IS THE ONE STATEMENT THAT IS BOTH TRUE AND LOAD-BEARING: containment holds
     WHILE THE STREAM IS FLYING. A stream that cost five milliseconds would show up in that
     immediately; a stream that costs a tenth of one is indistinguishable from zero, and the
     report says so in those words instead of printing a number with a sign in it. */
  const floorA = await frameMs(page, 3);
  const floorB = await frameMs(page, 3);
  const floor = +Math.abs(floorA - floorB).toFixed(3);
  const quiet = await frameMs(page, 3);
  await page.evaluate('__galaxy.presence.stream(8)');
  const streaming = await frameMs(page, 3);
  const streamCost = +(streaming - quiet).toFixed(3);
  await sleep(8 * (s0.ms + s0.gap) + 400);
  const flewAll = await page.json('__galaxy.presence.stream()');
  note('the whole frame\'s noise floor: ' + floor + ' ms');
  note('the stream: ' + streaming + ' ms/frame with deliveries in the air against ' + quiet +
       ' idle (difference ' + streamCost + ' ms, NOT RESOLVABLE - three runs of this same ' +
       'subtraction gave -0.037, +0.465 and -1.944 ms)');
  ok(streaming < T.FRAME_MS && flewAll.queued === 0 && flewAll.inflight === false,
     'AND CONTAINMENT HOLDS WHILE THE STREAM IS FLYING: ' + streaming + ' ms/frame with ' +
     'deliveries in the air against a budget of ' + T.FRAME_MS + ', and all eight had landed ' +
     'with the queue empty by the end of the window - which is deliberately NOT a claim about ' +
     'the stream\'s cost, because that subtraction is not resolvable on this instrument: three ' +
     'runs of it on the same build gave -0.037, +0.465 and -1.944 ms against noise floors of ' +
     '0.069 to ' + Math.max(floor, 0.145) + ' ms, so it changes sign; failure mode of widening a ' +
     'bound until a sign-changing quantity fits inside it: a test tuned to pass, reported as a ' +
     'budget line, for an effect whose real price is one compositor-layer transform',
     JSON.stringify({ streaming: streaming, quiet: quiet, cost: streamCost, floor: floor,
                      landed: flewAll }));
  table.forEach((r) => {
    ok(r.frame < T.FRAME_MS,
       '60FPS CONTAINMENT WITH EVERYTHING ON AT ' + r.w + 'x' + r.h + ': ' + r.frame +
       ' ms/frame against a budget of ' + T.FRAME_MS + ' - and this rests on the WHOLE-FRAME ' +
       'instrument and not on the cost door, deliberately: the frame time is taken with the ' +
       'vsync clamp off, so it includes the GPU, the deck\'s graph and the compositor, which is ' +
       'everything containment is actually about; failure mode of asserting this from ' +
       'cine.cost: the driver returns from render() long before the GPU is finished, so a ' +
       'GPU-bound chain reports a comfortable dispatch time and drops frames anyway',
       JSON.stringify(r));
  });
  /* THE TWO EFFECTS GET TWO ASSERTIONS, BECAUSE THEIR COSTS HAVE DIFFERENT SHAPES - which is
     the last thing this section learned and the reason it is not one line.
     The bloom is five render-target passes with their own uniform setup and program binds: a
     real main-thread cost, and the cost door resolves it cleanly at 0.09-0.16ms, an order of
     magnitude above its own floor.
     The smoke is twelve large blended quads sharing one material. Its DISPATCH is a third of
     the bloom's - 0.01 to 0.06ms - and the paired design does resolve it: every one of ten probe
     pairs came back positive at a mean of 0.0298 with an se of 0.0051. But a resolved dispatch
     is still not this effect's PRICE, and that distinction is the whole point of the second
     assertion: the smoke's cost is GPU FILL, twelve big overlapping translucent rectangles, and
     the cost door cannot see fill at all because the driver returns from render() long before the
     GPU has drawn them. So the number is reported as what it is - dispatch only - and the fill is
     covered where fill is actually visible, in the whole-frame containment rows above.
     Failure mode of publishing 0.03ms as "the smoke's cost": the next person to read the budget
     concludes the haze is nearly free and turns it on for a fill-bound machine, where it is the
     most expensive thing in the chain.
     SO: both are PAIRED, the bloom is PRICED, and the smoke is BOUNDED-AND-LABELLED. */
  ok(table.every((r) => r.pb.mean > r.pb.se * 2 && r.pb.pos >= r.pb.k - 1 &&
                        r.pb.mean < T.FRAME_MS / 8),
     'THE BLOOM PASS IS PRICED AND THE PRICE IS RESOLVED: ' +
     table.map((r) => r.pb.mean.toFixed(3) + ' +- ' + r.pb.se.toFixed(3)).join(' / ') +
     ' ms of dispatch at ' + WIDTHS.map((x) => x[0]).join('/') + ', each the mean of ' + PAIRS +
     ' INTERLEAVED on/off pairs so that drift cancels inside each pair rather than accumulating ' +
     'across the table; every mean clears twice its own standard error, ' +
     table.map((r) => r.pb.pos + '/' + r.pb.k).join(' and ') + ' of the individual differences ' +
     'came out positive - a sign test that assumes nothing about the shape of the noise - and ' +
     'every reading is under an eighth of the frame budget; failure mode of the separated ' +
     'subtraction this replaced: the same bloom read 0.098, 0.100 and 0.157 ms against a ' +
     'single-pair floor that read 0.028, 0.145 and 0.148, so the assertion\'s verdict was decided ' +
     'by which of those two numbers a run happened to draw',
     JSON.stringify(table.map((r) => ({ w: r.w, bloom: r.pb }))));
  /* REPLACES "AND THE SMOKE IS BOUNDED AND LABELLED". The haze is gone, so its row becomes a null
     control: the same paired on/off toggles of its flag must move the chain's dispatch by nothing
     beyond noise, because the flag has nothing left to switch. */
  ok(table.every((r) => Math.abs(r.ps.mean) <= Math.max(2 * r.ps.se, T.NULL_BOUND)),
     'AND THE REMOVED HAZE COSTS NOTHING BECAUSE IT IS NOT THERE: toggling its flag in ' + PAIRS +
     ' interleaved pairs moved the chain\'s dispatch by ' +
     table.map((r) => r.ps.mean.toFixed(3) + ' +- ' + r.ps.se.toFixed(3)).join(' / ') +
     ' ms at ' + WIDTHS.map((x) => x[0]).join('/') + ' - inside twice its own standard error or ' +
     T.NULL_BOUND + ' ms everywhere, the reading of a switch wired to nothing; failure mode: a ' +
     'haze still built and still drawn behind a flag that says it is off',
     JSON.stringify(table.map((r) => ({ w: r.w, smoke: r.ps }))));

  /* ====================================== 9. THE GUARDS ============================== */
  head('9. the guards, the flags and the spring');
  const health = await (await fetch(GALAXY + '/health')).json();
  const want = await page.json('__galaxy.presence.cine.want');
  ok(health.cine && typeof health.cine.bloom === 'boolean' &&
     typeof health.cine.smoke === 'boolean',
     'THE TWO CONFIG FLAGS ARE PUBLISHED AS BOOLEANS BY /health: ' +
     JSON.stringify(health.cine) + ' - failure mode of publishing the config itself: a server ' +
     'that answers a browser with its own settings file is one typo away from answering with a ' +
     'key, which is why only booleans ever cross this line',
     JSON.stringify(health.cine));
  /* UI MANDATE III: server.py is frozen and still publishes smoke_on; the page has no haze for it
     to switch. Old: want.smoke === health.cine.smoke. New: want.bloom follows the server, and the
     page's own record of the haze stays off whatever the server publishes. */
  ok(want.bloom === health.cine.bloom && !want.smoke,
     'AND THE PAGE WANTS WHAT THE SERVER SAYS FOR THE ONE EFFECT IT STILL HAS: want ' +
     JSON.stringify(want) + ' against health ' + JSON.stringify(health.cine) + ' - the bloom ' +
     'follows the flag, and smoke_on, still published by a server this round may not touch, has ' +
     'nothing left to switch; failure mode of a page that ignores the bloom flag: the mandate\'s ' +
     '"any containment failure flips the offending flag off" has nothing to flip',
     JSON.stringify({ want: want, health: health.cine }));
  const flagSrc = /"bloom_on": True/.test(readFileSync('server.py', 'utf8')) &&
                  /"smoke_on": True/.test(readFileSync('server.py', 'utf8'));
  ok(flagSrc,
     'DEFAULTING ON IN server.py\'s DEFAULT_CONFIG: failure mode of defaulting off "to be ' +
     'safe": the cinema ships dark on every machine that has no config.json, which is every ' +
     'fresh checkout, and what actually protects a slow machine is the page\'s own auto-revert ' +
     'rather than a cautious default nobody ever turns back on',
     'bloom_on/smoke_on True: ' + flagSrc);
  const cineEnd = await page.json('__galaxy.presence.cine');
  ok(cineEnd.reverts.length === 0 && cineEnd.throws === 0,
     'AND NOTHING AUTO-REVERTED ON A CLEAN RUN: no reverts, no pass throws, after ' +
     cineEnd.frames + ' composed frames and every flag toggled ' +
     (WIDTHS.length * 4) + ' times by hand - failure mode of a revert here: the price table ' +
     'above was measured on a chain that had already given up, and every row of it is the cost ' +
     'of something that is not running',
     JSON.stringify({ reverts: cineEnd.reverts, throws: cineEnd.throws, frames: cineEnd.frames }));
  const retried = await page.json('__galaxy.presence.cine.retry()');
  ok(retried && retried.bloom === want.bloom && !retried.smoke,
     'AND THERE IS A WAY BACK FROM A REVERT THAT IS A DECISION RATHER THAN A POLL: retry() ' +
     'restores ' + JSON.stringify(retried) + ' - failure mode of letting the /health poll ' +
     'restore it: the containment guard fires, the next poll undoes it, and the ladder becomes ' +
     'a loop that drops frames forever',
     JSON.stringify(retried));
  const spring = await page.json('__galaxy.presence.spring');
  note('spring: zeta ' + spring.zeta + ', overshoot ' + (spring.overshoot * 100).toFixed(2) +
       '% , ' + spring.stops.length + ' stops, last ' + spring.stops[spring.stops.length - 1]);
  ok(spring.overshoot >= T.SPRING_MIN && spring.overshoot <= T.SPRING_MAX,
     'THE SPRING OVERSHOOTS ONCE, INSIDE ITS OWN WINDOW: ' +
     (spring.overshoot * 100).toFixed(2) + '% at a damping ratio of ' + spring.zeta +
     ' - failure mode of the first constants this round tried, which had a perfectly ' +
     'respectable zeta of 0.920 and overshot by 0.06%: its half-period was 616ms, so inside a ' +
     '320ms window it never overshot at all and was cut off 4.9% short, which is a 0.68px jump ' +
     'at the end of every card entrance',
     JSON.stringify(spring));
  ok(spring.stops[spring.stops.length - 1] === 0 && spring.injected === true &&
     spring.sheet === true,
     'AND THE LAST KEYFRAME IS LITERALLY AT REST, WHICH IS THE CEILING THE ANIMATION LAW WANTS: ' +
     spring.stops.length + ' baked stops ending at ' + spring.stops[spring.stops.length - 1] +
     ', in a stylesheet this page injected - failure mode without the ceiling: a K or D edited ' +
     'to an underdamped pair leaves an answer card oscillating forever, and every layout ' +
     'assertion in the house measures a moving box',
     JSON.stringify({ last: spring.stops[spring.stops.length - 1], injected: spring.injected }));
  const anim = await page.json(
    '(function(){var s=document.getElementById("cine-spring");if(!s)return null;' +
    'var t=s.textContent;return {rise:/#answer\\.show\\{animation:cine-rise (\\d+)ms/.exec(t)?' +
    '+RegExp.$1:0, pop:/cine-pop (\\d+)ms/.test(t), reduce:/prefers-reduced-motion:reduce\\)' +
    '\\{#answer\\.show/.test(t)};})()');
  ok(anim && anim.rise === spring.ms && anim.pop === true && anim.reduce === true,
     'THE CARD AND THE SEALS RUN IT AND REDUCED MOTION TURNS IT OFF: cine-rise at ' +
     (anim && anim.rise) + 'ms on #answer.show, cine-pop on the three seal badges, and a ' +
     'prefers-reduced-motion block that sets animation:none - failure mode of a spring with no ' +
     'reduced-motion clause: it is the house\'s own accessibility law broken by the one ' +
     'animation added to the surface a harness measures most',
     JSON.stringify(anim));

  /* ============ 10. §34: THE EDGE WINDOW, AND THE PRESENCE SCALED FROM THE VIEWPORT ==========
     WHAT THE BOSS CIRCLED: a visible rectangle with a brown tint around the blue sphere, and a
     core too small outside fullscreen. Three claims are proved here and one is reported with its
     limit named rather than asserted into a pass.
     THE RECTANGLE'S MECHANISM, MEASURED BEFORE ANYTHING WAS WRITTEN (_runs/_rectprobe.log). With
     the bloom switched off all four border strips fall from ~0.048 to ~0.000, so the dominant
     painter is UnrealBloomPass spreading light to the render target's border and stopping dead
     there; 6 of 12 haze quads also reach 1.35-1.58 against a frameHalf of 1.2859 and are cut by
     that same border; and the sprite texture is INNOCENT - alpha is exactly 0 at its quad edge and
     corners at mip 0, and the sprite is magnified (180 device px over 128 texels), so no mip is
     averaging a square into the picture. A texture cannot fix a bloom halo, so the window is
     applied at the border the two defects share.
     WHY THE CORNERS ARE EXCLUDED FROM THE BORDER CLAIM AND NOT QUIETLY AVERAGED IN. All four
     corners keep 0.0222-0.0247 with the window on. That is the Eyes reticle: _runs/_rectprobe2
     hid the four .pb marks and hid the whole well, and the two readings were IDENTICAL to five
     decimals, with a top-strip control at 0.00000. The brackets are a feature. An assertion that
     demanded the corners match the sky would go red on the Eyes forever and the fix for it would
     be to delete the reticle. So the strips start 20px in from each corner and stop 20px short of
     the next, which puts no bracket inside any strip at any well size.
     AND WHY THERE IS A POSITIVE CONTROL AT ALL. §33 wrote sixty lines of screen-space fade, never
     asked the page whether the fade was in force, and measured it doing 0.0005 +- 0.0008. A
     one-sided after-reading cannot tell "the window works" from "the window never applied and
     something else moved". edge(0) must put the rectangle BACK. */
  head('§34 — the window at the border, and the presence sized from the viewport');
  await page.send('Emulation.setDeviceMetricsOverride',
    { width: 1366, height: 696, deviceScaleFactor: 1, mobile: false });
  await page.evaluate("String(__galaxy.presence.set('dust'))");
  await sleep(1800);
  const door = await page.json('__galaxy.presence.edge()');
  /* UI MANDATE II: the reticle went with the core. What the picture owns now is the dust's own
     reach at its widest moment - frame fill x (1 + breath + full level swell + full pulse swell),
     every term read off PRES rather than typed. Old: the reticle's corner, 0.8398. */
  /* UI MANDATE III: the dust wanders now, so what the picture owns is the BOUND on that wander,
     published by the page as reachFill (presDustReach: seed x wander x radial x swells, every term
     at its peak). Old: frameFill x (1 + breath + level + pulse). */
  const reachK = await page.json('({fill: __galaxy.presence.dust().geo.reachFill})');
  const retReach = reachK.fill;
  note('edge() reports inner ' + (door && door.inner) + ', pad ' + (door && door.pad) +
       ', max ' + (door && door.max) + ', applied ' + (door && door.applied));
  ok(!!door && door.applied === true && door.radial === true && door.closestSide === true &&
     door.inner > retReach && door.inner <= door.max,
     'THE EDGE WINDOW IS IN FORCE AND IT STARTS OUTSIDE EVERYTHING THE PICTURE OWNS: a ' +
     'closest-side radial gradient read back off getComputedStyle - not off the stylesheet this ' +
     'harness could have been written against - with an inner radius of ' + (door && door.inner) +
     ' of the half-extent, which is outside the dust at its widest - ' + retReach.toFixed(4) +
     ' - the bound on its furthest wandering stray at full breath, level and pulse; so the window ' +
     'cannot dim the cloud by arithmetic and not by hope. Failure mode this ' +
     'catches: the exact §33 one - a correction written, shipped, and never applied by the ' +
     'browser at all, measured as "doing nothing" and retired as a wrong hypothesis',
     JSON.stringify(door));

  /* THE PAIRED BORDER READING, CLOCK PINNED. The border is bloom skirt and the breath moves the
     bloom, so the pin is as load-bearing here as in the bracket assertion above. The pair is
     canvas-visible against canvas-hidden, which isolates what the CANVAS adds from what the deck
     already had there - the distinction §33 got backwards when it attributed 0.05 at the corners
     to "the deck showing through the canvas alpha" and retired the box hypothesis on the strength
     of it. The 40px-outside boxes are a built-in null: they are off the canvas, so the canvas can
     contribute nothing there, and any reading above the noise means the instrument is wrong. */
  const wb = await page.json(
    '(function(){var b=document.querySelector("#presence").getBoundingClientRect();' +
    'return {x:b.x,y:b.y,w:b.width,h:b.height,vw:innerWidth,vh:innerHeight};})()');
  const EP = 48, EIN = 4, ESK = 20;
  const eClip = { x: Math.max(0, wb.x - EP), y: Math.max(0, wb.y - EP),
                  w: Math.min(wb.vw - Math.max(0, wb.x - EP), wb.w + 2 * EP),
                  h: Math.min(wb.vh - Math.max(0, wb.y - EP), wb.h + 2 * EP) };
  const eox = wb.x - eClip.x, eoy = wb.y - eClip.y;
  const EREG = [
    [eox + ESK, eoy, wb.w - 2 * ESK, EIN],                   // border top
    [eox + ESK, eoy + wb.h - EIN, wb.w - 2 * ESK, EIN],      // border bottom
    [eox, eoy + ESK, EIN, wb.h - 2 * ESK],                   // border left
    [eox + wb.w - EIN, eoy + ESK, EIN, wb.h - 2 * ESK],      // border right
    [eox + ESK, eoy - 40, wb.w - 2 * ESK, EIN],              // null: 40px above
    [eox + ESK, eoy + wb.h + 40, wb.w - 2 * ESK, EIN],       // null: 40px below
    [eox - 40, eoy + ESK, EIN, wb.h - 2 * ESK],              // null: 40px left
    [eox + wb.w + 40, eoy + ESK, EIN, wb.h - 2 * ESK],       // null: 40px right
  ];
  const ENM = ['top', 'bottom', 'left', 'right', 'null+40 above', 'null+40 below',
               'null+40 left', 'null+40 right'];
  async function borderContrib() {
    const acc = EREG.map(() => []);
    for (let p = 0; p < 3; p++) {
      const on = await page.regions(eClip, EREG);
      await page.evaluate('document.getElementById("presence-cvs").style.visibility="hidden"');
      await sleep(160);
      const off = await page.regions(eClip, EREG);
      await page.evaluate('document.getElementById("presence-cvs").style.visibility=""');
      await sleep(160);
      on.forEach((v, i) => acc[i].push(+(v - off[i]).toFixed(5)));
    }
    return acc.map((a) => med(a));
  }
  await page.evaluate('__galaxy.presence.phase(0)');
  await sleep(300);
  const cOn = await borderContrib();
  note('canvas contribution, window ON: ' +
       ENM.map((n, i) => n + ' ' + cOn[i].toFixed(5)).join(' · '));
  const worstEdge = Math.max(...cOn.slice(0, 4).map(Math.abs));
  const worstNull = Math.max(...cOn.slice(4).map(Math.abs));
  ok(worstEdge <= T.EDGE_LUM && worstNull <= T.EDGE_LUM,
     'PART 1 - THERE IS NO EDGE LEFT AT THE WELL\'S BORDER: with the core\'s clock pinned, the ' +
     'canvas adds at most ' + worstEdge.toFixed(5) + ' (' + (worstEdge * 255).toFixed(2) +
     '/255) along its own border, under the named ' + T.EDGE_LUM + ' - against ' +
     '0.04845-0.06846 (12.4-17.5/255) measured on the same four strips before the window, a ' +
     'reduction of more than ten times, and now below the 1.39/255 the border read with the ' +
     'bloom and the haze BOTH switched off. The four 40px-outside boxes are the instrument\'s ' +
     'own null and read ' + worstNull.toFixed(5) + ', because the canvas is not there to ' +
     'contribute. Failure mode: axis-aligned quad edges and a bloom halo stopping dead at the ' +
     'render target, which the boss circled as a rectangle with a brown tint and which no ' +
     'amount of looking at the sprite texture explains',
     JSON.stringify({ contrib: cOn, worstEdge: worstEdge, worstNull: worstNull }));

  const off0 = await page.json('__galaxy.presence.edge(0)');
  await sleep(400);
  const cOff = await borderContrib();
  const back0 = await page.json('__galaxy.presence.edge(1)');
  await sleep(400);
  await page.evaluate('__galaxy.presence.phase(null)');
  const rise = cOff.slice(0, 4).map((v, i) => +(v - cOn[i]).toFixed(5));
  const worstRise = Math.min(...rise);
  note('window OFF: ' + ENM.slice(0, 4).map((n, i) => n + ' ' + cOff[i].toFixed(5)).join(' · ') +
       ' — rise ' + rise.join(', '));
  /* REPLACES "AND THE WINDOW IS WHAT IS HOLDING IT DOWN". That control switched the window off and
     required the rectangle to come BACK (>= EDGE_CTRL) - its subject was the bloom's skirt, a lit
     sheet that reached the canvas border and that the window existed to hide. UI mandate III removed
     that sheet (the bloom's blend no longer adds alpha; see presCine), and on this build the border
     gains +0.0000 with the window off: there is nothing left for the window to hold down. So the
     claim is now the stronger one - the border is clean WITHOUT the window as well as with it - and
     the half that guards against §33's trap is kept: the door must still report the window off,
     then on, read back off getComputedStyle. Old: rise >= EDGE_CTRL. New: |rise| <= EDGE_LUM. */
  ok(off0 && off0.applied === false && back0 && back0.applied === true &&
     rise.every((r) => Math.abs(r) <= T.EDGE_LUM),
     'AND THE BORDER IS CLEAN EVEN WITH THE WINDOW SWITCHED OFF: off at run time, the border moves by ' +
     rise.map((r) => r.toFixed(4)).join(', ') + ' (each within the named ' + T.EDGE_LUM + ') - the ' +
     'bloom no longer lays a sheet out to the edge for the window to hide - and the door agrees with ' +
     'itself either way - applied false with it off, true with it back. Failure mode without ' +
     'this control, and it is not hypothetical: §33\'s fade was measured doing 0.0005 +- 0.0008 ' +
     'and the hypothesis was retired, when what the number actually showed was a correction ' +
     'that the browser had never put in force',
     JSON.stringify({ off: off0, back: back0, on: cOn.slice(0, 4), offv: cOff.slice(0, 4) }));

  /* ============================ PART 2, REPLACED: NO DISC IN THE WELL ===========================
     §34 PART 2 proved the haze's hue (the shell's blue, not amber) off its material and its pixels.
     UI mandate III removed the haze, so the claim that replaces it is the one the boss's new note
     asks for: there is no disc behind the presence at all. Measured by taking the presence away: a
     BARE snapshot (presence.snap(n, true)) draws one frame of its own canvas with its points off,
     so anything still lit is not the presence. On the committed page the haze left a disc peaking
     at 77-102 out of 255 in the dust and 36 round the face. Both modes, bloom on. Old: tint === shell
     blue and B > R. New: the bare canvas peaks at <= BARE_MAX with no pixel over 1, in dust and face. */
  await page.send('Emulation.setDeviceMetricsOverride',
    { width: 1366, height: 768, deviceScaleFactor: 1, mobile: false });
  await sleep(1600);
  await page.evaluate('__galaxy.presence.cine.set({bloom:true})');
  const discs = {};
  for (const m of ['dust', 'face']) {
    await page.evaluate('__galaxy.presence.set("' + m + '")');
    await sleep(1800);
    const s = JSON.parse(await page.evaluate('__galaxy.presence.snap(160, true).then(function(s){return JSON.stringify(s)})'));
    const w = JSON.parse(await page.evaluate('__galaxy.presence.snap(160).then(function(s){return JSON.stringify(s)})'));
    discs[m] = { bareMean: s.mean, bareMax: s.max, bareOver1: s.over1, wholeMax: w.max };
  }
  /* WHAT THE CANVAS ADDS TO THE SCREEN, RING BY RING: the well screenshotted with the presence
     canvas shown and again hidden, decoded by the page itself, and differenced per ring of the
     half-extent - three pairs, medianed - with the presence's clock pinned so the pair differs only
     in the canvas. This is the instrument that sees a disc of added light: an in-page readback of a
     premultiplied canvas cannot (light on zero alpha reads back as black). */
  const GLASS_RINGS = 20;
  const glassRings = async (box) => {
    const shot = async () => {
      const r = await page.send('Page.captureScreenshot', { format: 'png', clip: { x: box.left, y: box.top, width: box.w, height: box.h, scale: 1 } });
      return JSON.parse(await page.evaluate('(async function(){var im=new Image();await new Promise(function(res){im.onload=res;' +
        'im.src="data:image/png;base64,' + r.result.data + '";});var c=document.createElement("canvas");c.width=im.width;c.height=im.height;' +
        'var g=c.getContext("2d",{willReadFrequently:true});g.drawImage(im,0,0);var d=g.getImageData(0,0,c.width,c.height).data,h=c.width/2,' +
        's=new Array(' + GLASS_RINGS + ').fill(0),n=new Array(' + GLASS_RINGS + ').fill(0);for(var y=0;y<c.height;y++)for(var x=0;x<c.width;x++){' +
        'var q=Math.hypot(x+0.5-h,y+0.5-h)/h;if(q>=1)continue;var k=Math.floor(q*' + GLASS_RINGS + '),i=(y*c.width+x)*4;' +
        's[k]+=0.2126*d[i]+0.7152*d[i+1]+0.0722*d[i+2];n[k]++;}return JSON.stringify(s.map(function(v,k){return v/Math.max(1,n[k]);}));})()'));
    };
    await page.evaluate('__galaxy.presence.phase(0.2)');
    await sleep(500);
    const diffs = [];
    for (let p = 0; p < 3; p++) {
      const on = await shot();
      await page.evaluate('document.getElementById("presence-cvs").style.visibility="hidden"');
      await sleep(200);
      const off = await shot();
      await page.evaluate('document.getElementById("presence-cvs").style.visibility=""');
      await sleep(200);
      diffs.push(on.map((v, i) => v - off[i]));
    }
    await page.evaluate('__galaxy.presence.phase(null)');
    return diffs[0].map((_, i) => { const a = diffs.map((d) => d[i]).sort((x, y) => x - y); return +a[1].toFixed(2); });
  };
  /* the ring 0.85-0.95 of the half-extent: outside the cloud and the head, inside the window */
  const outerAdded = (rings) => +((rings[17] + rings[18]) / 2).toFixed(2);
  const glassBox = await page.json('__galaxy.layout.rects.presence');
  for (const m of ['dust', 'face']) {
    await page.evaluate('__galaxy.presence.set("' + m + '")');
    await sleep(1800);
    discs[m].glass = outerAdded(await glassRings(glassBox));
  }
  await page.evaluate('__galaxy.presence.set("dust")');
  note('the presence canvas with its points off, 0-255: ' + JSON.stringify(discs));
  ok(['dust', 'face'].every((m) => discs[m].bareMax <= T.BARE_MAX && discs[m].bareOver1 === 0 && discs[m].wholeMax > 50),
     'PART 2, REPLACED - THERE IS NO DISC BEHIND THE PRESENCE, IN EITHER MODE: with its points ' +
     'switched off for one frame, the presence\'s own canvas peaks at ' + discs.dust.bareMax + ' (dust) and ' +
     discs.face.bareMax + ' (face) out of 255, no pixel over 1, where the same frames with the points ' +
     'on peak at ' + discs.dust.wholeMax + ' and ' + discs.face.wholeMax + ' - nothing behind the presence; ' +
     'failure mode this catches: the pale circle the boss circled, by any route - a sprite, a ' +
     'backing mesh, a CSS gradient on the canvas',
     JSON.stringify(discs));
  ok(['dust', 'face'].every((m) => discs[m].glass <= T.GLASS_MAX),
     'AND NO DISC OF LIGHT ON THE GLASS EITHER: shot on the screen with the canvas shown and hidden, the ' +
     'presence adds ' + discs.dust.glass + ' (dust) and ' + discs.face.glass + ' (face) out of 255 between 0.85 ' +
     'and 0.95 of the well\'s radius, ceiling ' + T.GLASS_MAX + ' - the bloom\'s old additive-alpha blend laid ' +
     '11-17 there round speaking dust once the haze was gone, which this round\'s blend removed',
     JSON.stringify({ dust: discs.dust.glass, face: discs.face.glass }));

  /* ============================== PART 3: THE PRESENCE SCALE ==============================
     THE ARITHMETIC THIS CHECKS, AND THE LIMIT IT REPORTS. The well used to ask for a fixed 420px
     rect, so on a bigger screen the sphere got relatively SMALLER - the boss's "too small outside
     fullscreen" from the other end. It now asks min(PRES_CAP, min(vw,vh) * PRES_CORE_FRAC /
     PRES_FILL), i.e. it is derived from the viewport. What it then gets is min(ask, room, band),
     and the deck's band is vh-387 at every height measured (696->309 ... 1080->693), which is
     SUBTRACTIVE - so on short viewports the band binds and 0.42 is not reachable without moving
     chrome that is DO-NOT-ALTER. The mandate's own word is "clamped", so the clamp is reported
     with the fraction it yields rather than asserted away, and what IS asserted is the thing that
     was actually broken: the core must grow when the room grows. On the old build it did not -
     at 1600 the fullscreen fraction was LOWER than the windowed one (0.2770 against 0.3011)
     because the well sat pinned at 420 while the viewport grew around it. */
  /* FIRST, THE GLASS IS PUT IN A DEFINED STATE, and this is not tidiness - it is the only way
     the six numbers below are a measurement of the SIZING LAW rather than of what the Scholar
     happened to read this morning. §40 MEASURED THE FAULT: the deck's toast is a column, and on
     a day the house has studied, #digestpanel is in it at 241.8px - so #brain stands 451.3px
     tall with nothing spoken, the band above it collapses below PRES_MIN, and five of the six
     states fall to the SECOND choice ("beside the toast"), where the well's side is bound by a
     HORIZONTAL term and is therefore identical at both heights of one width. `grew` then cannot
     hold at any width - not because the presence stopped scaling, but because nothing vertical
     is binding it - and at 1600 the two heights land either side of the 192px flip (191 against
     192), so the windowed well reads 382px beside the toast and the taller fullscreen one reads
     263px above it. Measured both ways in _runs/sweep40/well_probe.mjs: digest on the glass,
     grew false/false/false with the 1600 gap at 0.579; digest dismissed, #brain 199.5px, all six
     above the toast, grew true/true/true and every gap inside SCALE_GAP. 199.5+26+12+149 is the
     387 this part's own comment records from §39, which is the state §39 measured and did not
     name. THE PAGE'S OWN HAND DOES IT - __galaxy.study.close() is what the digest's own dismiss
     button calls, and it ends in layout() - so nothing here reaches past the API a person has. */
  const digestWas = await page.json('(function(){var p=document.getElementById("digestpanel");' +
    'var h=document.getElementById("brain").getBoundingClientRect().height;' +
    'return {shown:!!(p&&p.classList.contains("show")),brain:+h.toFixed(1)};})()');
  await page.evaluate('(window.__galaxy && __galaxy.study && __galaxy.study.close) ? ' +
                      '(__galaxy.study.close(), 1) : 0');
  await sleep(700);
  const digestNow = await page.json('(function(){var p=document.getElementById("digestpanel");' +
    'var h=document.getElementById("brain").getBoundingClientRect().height;' +
    'return {shown:!!(p&&p.classList.contains("show")),brain:+h.toFixed(1)};})()');
  note('PART 3 setup — the Scholar digest was ' + (digestWas.shown ? 'ON the glass' : 'already off')
       + ' (toast ' + digestWas.brain + 'px) and is now '
       + (digestNow.shown ? 'STILL ON' : 'dismissed') + ' (toast ' + digestNow.brain + 'px): the '
       + 'presence is sized against the deck below it, so the toast is the room this part varies '
       + 'the viewport against and it is stated rather than inherited');

  const SCR = [[1280, 800], [1366, 768], [1600, 900]];
  const srows = [];
  for (const [sw, sh] of SCR) {
    for (const mode of ['windowed', 'fullscreen']) {
      const svh = mode === 'windowed' ? sh - 72 : sh;
      await page.send('Emulation.setDeviceMetricsOverride',
        { width: sw, height: svh, deviceScaleFactor: 1, mobile: false });
      /* AND AT EVERY READ, not once before the loop: the digest ARRIVES ON A POLL, so a run
         that closed it at second 0 can have it back at second 4 and measure three states
         against one toast and three against another. Closing it per state is what makes the
         six comparable. */
      await page.evaluate('(window.__galaxy && __galaxy.study && __galaxy.study.close) ? ' +
                          '(__galaxy.study.close(), 1) : 0');
      await sleep(1500);
      const r = await page.json(
        '(function(){var L=__galaxy.layout.LAYOUT;var W=__galaxy.presence.well;' +
        'var c=__galaxy.presence.dust();var G=__galaxy.layout.last;' +
        'var b=document.querySelector("#presence").getBoundingClientRect();' +
        'var pb=document.querySelectorAll("#presence .pb").length;' +
        'return {side:+b.width.toFixed(1),fill:c.geo.frameFill,ratio:L.PRES_RATIO,edge:L.EDGE,' +
        'pane:G.pane,band:G.wellBox&&G.wellBox.pane?G.wellBox.pane.band:null,' +
        'govAsk:G.wellBox?G.wellBox.ask:null,cap:L.PRES_CAP,why:String(W.why),' +
        'pb:pb,kids:document.getElementById("presence").children.length,' +
        'inner:__galaxy.presence.edge().inner,vw:innerWidth,vh:innerHeight};})()');
      const mn = Math.min(r.vw, r.vh);
      /* UI MANDATE II PART 2: the ask is PRES_RATIO x min(the pane's width less its edges, the
         pane's free band), capped - recomputed here from the LAYOUT constants and the governor's
         published pane, so the second assertion below is two computations of one number. Old:
         min(PRES_CAP, min(vw,vh) x PRES_CORE_FRAC / PRES_FILL). */
      const ask = Math.round(Math.min(r.cap, r.ratio *
        Math.min(r.pane.right - r.pane.left - 2 * r.edge, r.band)));
      srows.push({ sw, mode, vh: r.vh, mn, side: r.side, ask, govAsk: r.govAsk,
                   core: +((r.side * r.fill) / mn).toFixed(4),
                   bandBound: /the band/.test(r.why), askBound: /the ask/.test(r.why),
                   pb: r.pb, kids: r.kids, inner: r.inner, fill: r.fill, why: r.why });
    }
  }
  /* windowed is MODELLED as the fullscreen height minus 72px of browser chrome: two emulated
     viewport heights on one width, which is what "identical feel windowed and fullscreen" is a
     claim about. It is named as a model and is not a real document.fullscreenElement - that one
     belongs to layout_proof, which drives it with Ctrl+A. */
  srows.forEach((r) => note(r.sw + 'x' + r.vh + ' (' + r.mode + '): well ' + r.side +
    'px, asked ' + r.ask + 'px, dust/min(vw,vh) ' + r.core.toFixed(4) +
    ', bracket ' + r.pb + 'px — ' + r.why.slice(-46)));
  const gaps = SCR.map(([sw]) => {
    const a = srows.find((r) => r.sw === sw && r.mode === 'windowed');
    const b = srows.find((r) => r.sw === sw && r.mode === 'fullscreen');
    return { sw, w: a.core, f: b.core, grew: b.core >= a.core,
             gap: +(Math.abs(b.core - a.core) / b.core).toFixed(4) };
  });
  const asksVary = new Set(srows.map((r) => r.ask)).size === srows.length;
  ok(asksVary && gaps.every((g) => g.grew) && gaps.every((g) => g.gap <= T.SCALE_GAP),
     'PART 3 - THE PRESENCE IS SIZED FROM THE VIEWPORT AND NO LONGER FROM A FIXED RECT: all six ' +
     'states ask for a different number of pixels (' + srows.map((r) => r.ask).join('/') +
     '), the dust GROWS when the room grows at every width (' +
     gaps.map((g) => g.sw + ': ' + g.w.toFixed(4) + '->' + g.f.toFixed(4)).join(', ') +
     '), and windowed sits within ' + (100 * Math.max(...gaps.map((g) => g.gap))).toFixed(1) +
     '% of fullscreen on the same screen, inside the named ' + (100 * T.SCALE_GAP) + '%. ' +
     'Failure mode of the fixed rect this replaces, which is the boss\'s own complaint read from ' +
     'the other end: a 420px well on a 1920x1080 screen is a SMALLER fraction of the room than ' +
     'the same 420px on 1366x768, so the sphere shrank as the display got better',
     JSON.stringify({ asks: srows.map((r) => r.ask), gaps: gaps }));

  /* UI MANDATE II: PRES_FILL and PRES_CORE_FRAC are gone - the governor no longer sizes the well
     from a copy of the renderer's fill, it sizes it from the PANE. So the duplicated number this
     checks is the ask itself: the harness's recomputation against the governor's published one.
     Old: LAYOUT.PRES_FILL === core().frame.fill. New: recomputed ask === wellBox.ask (+-1px for
     the band's rounding). The other two halves are unchanged. */
  const fillAgrees = srows.every((r) => r.govAsk !== null && Math.abs(r.govAsk - r.ask) <= 1);
  const oneInner = new Set(srows.map((r) => r.inner)).size === 1;
  /* UI MANDATE IV PART 2 REMOVED THE FOUR CORNER MARKS (#presence .pb), so this third half follows:
     old - the brackets scale with the well, floor BRACKET_PX; new - there are none at any well size,
     and the well holds only its canvas and its tag. */
  const pbScales = srows.every((r) => r.pb === 0 && r.kids === 2);
  ok(fillAgrees && oneInner && pbScales,
     'AND THE THREE NUMBERS THIS ROUND DUPLICATED STILL AGREE WITH THEIR ORIGINALS: the ' +
     'governor\'s published ask (' + srows.map((r) => r.govAsk).join('/') + ') against this ' +
     'file\'s own PRES_RATIO x the pane (' + srows.map((r) => r.ask).join('/') + ') in all six ' +
     'states - a governor sizing the well from anything but the pane would part from it and ' +
     'nothing would throw; the window\'s inner radius is ONE scale-invariant number (' + srows[0].inner +
     ') at every well size, which is what makes it a property of the frame rather than of a ' +
     'pixel count; and at every one of the six well sizes there are no corner marks round the ' +
     'core (' + srows.map((r) => r.pb).join('/') + ' .pb, the well holding only its canvas and tag) - ' +
     'UI mandate IV removed the four brackets that framed it',
     JSON.stringify({ ask: srows.map((r) => [r.govAsk, r.ask]),
                      inner: srows.map((r) => r.inner), pb: srows.map((r) => r.pb) }));
  /* THE LIMIT, PRINTED RATHER THAN BURIED: what the band costs the mandate's 0.42. */
  note('PART 3 limit — the band binds in ' +
       srows.filter((r) => r.bandBound).length + ' of 6 states, so the dust fraction lands at ' +
       Math.min(...srows.map((r) => r.core)).toFixed(4) + '..' +
       Math.max(...srows.map((r) => r.core)).toFixed(4) + ' of min(vw,vh) (the well itself is ' +
       srows.map((r) => r.side).join('/') + 'px, PRES_RATIO of the pane)');
  await page.evaluate('__galaxy.stage.set("galaxy", "cine_proof")');

  note('page exceptions during the run: ' + (page.logs.length ? page.logs.join(' | ') : 'none'));
  try { page.ws.close(); } catch { /* ignore */ }
}

main().catch((e) => {
  bad.push('the run itself: ' + e.message);
  console.log('\n  ERROR ' + (e && e.stack));
}).finally(async () => {
  shut();
  await sleep(600);
  try { rmSync(profile, { recursive: true, force: true }); } catch { /* windows */ }
  console.log('\n  VERIFY ' + (checks - bad.length) + '/' + checks +
              (bad.length ? ' FAIL' : ' PASS') + '\n');
  bad.forEach((b) => console.log('    FAILED: ' + b));
  process.exit(bad.length ? 1 : 0);
});
