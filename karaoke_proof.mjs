/* §39 - THE WORD-BY-WORD REVEAL, THE VANISH, AND THE SIDEBAR'S GLASS BODY, against a real
 * browser, a real AudioContext and the server's own per-word timings.
 *
 * WHY THIS CANNOT BE A HERMETIC TEST, stated first because it is the whole shape of the file.
 * Every claim §39 makes is a claim about an instant: WHEN word nineteen appeared relative to
 * when the speakers said it, WHETHER the sky came back after the card left, and WHETHER you
 * can see stars through the sidebar. A fake clock proves the arithmetic of karaTick() and
 * nothing about the feature. So this runs HEADED, UN-MUTED, at 1280x860, with real audio off
 * the real /say and real screenshots of the real galaxy. IT WILL TALK OUT LOUD for about two
 * minutes. A window will appear; something on this desk minimises it about two seconds in, so
 * keepFront() un-minimises by BOUNDS ONLY and never steals the foreground.
 *
 * WHAT IS PROVED, in order, and every number below is read off the page or out of a PNG:
 *
 *   THE SURFACE. §38's law hands the sentence to whichever of the card and the caption is
 *     carrying it, so the reveal follows it. Both paths are driven here - a capped answer,
 *     where the card keeps its paragraph because the voice says less than the card holds, and
 *     a short one, where the card yields and the caption carries it - and in both the spans
 *     must be ON THE GLASS and not merely lit inside a display:none element.
 *   THE DRIFT, five timestamps, +/-1 word. At each one the page is asked for the audio clock
 *     (actx.currentTime - the chunk's start) and for how many words are visible, in ONE
 *     evaluate so both describe the same instant. The expected count is recomputed HERE from
 *     the server's own X-Word-Timings, which is the point: two independent walks of the same
 *     numbers agreeing is evidence, one number is a claim.
 *   ZERO REFLOW, as the card's own height: before the first word and at the last, equal, with
 *     the page's own per-frame counter at zero beside it.
 *   THE VANISH, against the SKY ITSELF. The honest form of "pixel-identical to the pre-answer
 *     plate" is in THE CHURN below: a live galaxy is never pixel-identical to itself.
 *   THE EXEMPTIONS: a gate card outlives its grace and goes when the gate is resolved; a
 *     hover hold and its re-arm are read out of the page's own words.
 *   THE SIDEBAR'S THREE CLOSES, each one separately and each named by the page.
 *   THE GLASS BODY: the panel's background and blur MEASURED against the card's, the alpha
 *     against the --glass token it was read from, the hairline, no inset glow, the geometry
 *     reported unchanged, the ink's contrast computed in Node from the colours the page is
 *     actually painting, and stars measured THROUGH the panel in two camera positions.
 *   AND THE MUTED TAB, in a second tab of its own: full text instantly, no spans at all, and
 *     a vanish on an estimated read-time instead of an ending.
 *
 * THE CHURN, because this is the one assertion whose form had to be argued for. The mandate
 * asks for the sky "pixel-identical to the pre-answer plate". It cannot be: the starfield
 * twinkles, the presence breathes, and two frames of an idle galaxy taken 450ms apart already
 * differ. So the sky's own frame-to-frame churn is MEASURED first, from back-to-back frames of
 * the card's exact rectangle with no card in it, and that measurement is the tolerance. The
 * mid-answer frame must differ from the pre-answer frame by far more than the churn - that is
 * the proof the card was really there - and the post-vanish frame by no more than it. Beside
 * that sits the DOM's own verdict, which IS exact: no classes, no rectangle, no text.
 *
 * It never writes config.json, never sends mail, and asks the server for nothing but audio.
 *
 * Usage:  node karaoke_proof.mjs        (server.py must be running on 4700)
 */
import { spawn, spawnSync } from 'node:child_process';
import { mkdtempSync, rmSync, existsSync, mkdirSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { basename, join } from 'node:path';

const GALAXY = 'http://127.0.0.1:4700';
const PORT = 9229;                       // nobody else's; see the port map in the lookbook
const CDP = 'http://127.0.0.1:' + PORT;
const W = 1280, H = 860;
const OUT = '_runs/sweep39';
const CHROMES = [
  'C:/Program Files/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Google/Chrome/Application/chrome.exe',
  process.env.LOCALAPPDATA + '/Google/Chrome/Application/chrome.exe',
];
/* A COLUMN OF A LIVE STARFIELD HAS A SPREAD IN THE TENS; a column of bare body background has
   one value from top to bottom. Two is PNG quantisation and the body's own vertical gradient
   and nothing else - layout_proof's number, kept deliberately, because it was measured against
   the smallest real starfield column on this page (29). */
const FLAT_TOL = 2;
const DRIFT_TOL = 1;                     // words, as the mandate names it
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let checks = 0; const bad = [];
const ok = (c, claim, detail) => {
  checks++; console.log((c ? '  ok   ' : '  FAIL ') + claim);
  if (!c) { bad.push(claim); if (detail) console.log('         ' + detail); }
};
const note = (m) => console.log('  note ' + m);
const r2 = (n) => Math.round(n * 100) / 100;

/* ---- THE TWO ANSWERS, chosen for what they make the page do ----
   A CAPPED ANSWER, which is the card path. The voice says the first sentences and the card
   holds the rest, so spokenForm() returns a strict PREFIX of the paragraph - which fails
   answerYield()'s comparison in the only direction that matters, the card keeps its paragraph,
   and the reveal runs where a person is reading. It is also the one case where the un-spoken
   tail has to arrive with the last spoken word. */
const LONG_ANSWER =
  'The pricing page is ready, sir, and the middle tier is the one they will take. ' +
  'Three columns, the usual ladder, with the annual discount stated in money rather than in ' +
  'a percentage, because nobody converts twenty per cent into rupees at a glance. ' +
  'The enterprise column asks for a conversation instead of a number, which is what the ' +
  'last two deals wanted anyway. ' +
  'I have left the comparison table collapsed on a telephone and open on a desk, and the ' +
  'footnote about the trial now says fourteen days in both places rather than fourteen in ' +
  'one and thirty in the other. ' +
  'Everything else on that page is the copy you approved on Tuesday, unchanged.';
/* A SHORT ONE, which is the caption path and the commonest answer in the house: the voice says
   exactly what the card holds, §38 hands the sentence to the caption, and the card's paragraph
   stands down. If the reveal did not follow it there, this is where it would be invisible. */
const SHORT_ANSWER = 'The invoice importer has caught up, sir - eleven retries, all of them ' +
  'clean, and the queue is empty again.';
const GATE_ANSWER = 'That one needs your word first, sir: it writes to the diary.';
const MUTED_ANSWER = 'The quiet tab still shows you the whole sentence at once, sir.';
const NUDGE_LINE = 'You have been at that for fifty minutes, sir.';

const PROPOSAL = {
  name: 'add_calendar_event',
  expiresInS: 600,
  fields: [{ name: 'title' }, { name: 'start' }, { name: 'end' }],
  params: {
    title: 'Quarterly review with the Galaxy team',
    start: '2026-10-05T16:00:00+05:30',
    end: '2026-10-05T17:00:00+05:30',
  },
};

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
      const bomb = setTimeout(() => { this.w.delete(id); rej(new Error(method + ' timed out')); }, 20000);
      this.w.set(id, (m) => { clearTimeout(bomb); res(m); });
      this.ws.send(JSON.stringify({ id, method, params: params || {} })); }); }
  async evaluate(expression, userGesture = false) {
    const r = await this.send('Runtime.evaluate',
      { expression, returnByValue: true, awaitPromise: true, userGesture });
    if (r.result && r.result.exceptionDetails) {
      const d = r.result.exceptionDetails;
      throw new Error('page threw: ' + ((d.exception && (d.exception.description ||
        d.exception.value)) || d.text) + '  <- ' + expression.slice(0, 160));
    }
    return r.result && r.result.result ? r.result.result.value : undefined;
  }
  async json(e) { return JSON.parse(await this.evaluate('JSON.stringify(' + e + ')') || 'null'); }
  /* ONE CAPTURE, TWO USES: written to disk for the boss and handed back as base64 for the
     assertion. A plate nothing reads back is a souvenir; an assertion with no plate beside it
     is a number nobody can check. scale 1 throughout, so one image pixel is one CSS pixel and
     two frames of the same rectangle are comparable whatever this monitor's ratio is. */
  async shot(file, clip) {
    const r = await this.send('Page.captureScreenshot', clip
      ? { format: 'png', clip: { x: clip.x, y: clip.y, width: clip.w, height: clip.h,
                                 scale: clip.scale || 1 } }
      : { format: 'png' });
    const data = r.result && r.result.data;
    if (!data) throw new Error('no screenshot came back');
    if (file) writeFileSync(file, Buffer.from(data, 'base64'));
    return data;
  }
  close() { try { this.ws.close(); } catch { } }
}
const cdp = async (p, method) => {
  const r = await fetch(CDP + p, method ? { method } : undefined);
  const t = await r.text();
  try { return JSON.parse(t); } catch { return t; }
};

/* HOW LONG IT TOOK, OR null - AND NEVER 0, which is a repair of this function rather than a
   style. It returned the elapsed milliseconds on success and 0 on timeout, and every call site
   in this file tests the result with `!!` - so a condition that was already true on the FIRST
   poll returned 0 and read as a timeout. It cost a red on a green behaviour: the sidebar's (c)
   close happened in the same millisecond as the utterance, the page named the reason correctly,
   and the assertion reported "closed it in 0ms" as a failure. Success is therefore floored at
   1ms - honest to this clock's resolution, since the poll interval is 150ms - and a timeout is
   null, which is falsy, prints as "null" in a message and can never be confused with a fast
   success again. */
async function waitFor(page, expr, ms = 8000) {
  const t0 = Date.now();
  for (let i = 0; i < Math.ceil(ms / 150); i++) {
    try { if (await page.evaluate(expr)) return (Date.now() - t0) || 1; } catch { }
    await sleep(150);
  }
  return null;
}

/* THE WINDOW MUST STAY AWAKE. A minimised window throttles requestAnimationFrame, and this
   harness's entire subject is a rAF walk against an audio clock: a throttled reveal reads as a
   broken one. BOUNDS ONLY - Page.bringToFront steals the foreground from the employer and does
   nothing for a minimised window anyway. */
function keepFront(page, every = 1500) {
  let puts = 0;
  const t = setInterval(async () => {
    try {
      const { result } = await page.send('Browser.getWindowForTarget');
      if (result && result.bounds && result.bounds.windowState === 'minimized') {
        await page.send('Browser.setWindowBounds',
          { windowId: result.windowId, bounds: { windowState: 'normal' } });
        puts++;
      }
    } catch (e) { /* the run is ending, or this build has no Browser domain */ }
  }, every);
  if (t.unref) t.unref();
  return { stop: () => clearInterval(t), count: () => puts };
}

/* A GENUINE GESTURE. document.body.click() does not unlock audio - Chrome wants an event it
   believes came from a human, which over CDP means Input.dispatchMouseEvent. */
async function realClick(page, x, y) {
  for (const type of ['mousePressed', 'mouseReleased']) {
    await page.send('Input.dispatchMouseEvent',
      { type, x, y, button: 'left', clickCount: 1, buttons: type === 'mousePressed' ? 1 : 0 });
    await sleep(40);
  }
}

/* PARK THE POINTER IN THE TOP-LEFT CORNER, and do it AGAIN AFTER EVERY SCREENSHOT.
   THIS IS NOT BELT AND BRACES, it is the fix for four reds. §39 holds a hovered card
   deliberately - vanishHeld() asks `card.matches(':hover')` - so wherever Chrome thinks the
   mouse is decides whether the vanish section is testing the vanish or the hover exemption.
   And Chrome's answer is not fixed by a synthetic move: Page.captureScreenshot with a clip
   resizes the compositor surface, and on a resize the renderer re-derives hover FROM THE REAL
   OS CURSOR - which on a headed harness is wherever the employer left the mouse, very often
   over the middle of the window where the card is. Measured: the pointer was parked at (6,6)
   before the first plate and the page still reported "the pointer is on the card" four minutes
   later, having taken four screenshots in between.
   So park() is called after each shot and immediately before anything reads a hold, and it
   moves through two positions so that there is a real delta for the renderer to act on. */
async function park(page) {
  for (const [x, y] of [[4, 4], [6, 6]]) {
    await page.send('Input.dispatchMouseEvent', { type: 'mouseMoved', x, y, buttons: 0 });
    await sleep(60);
  }
  return page.evaluate(
    '(function(){var h=document.querySelectorAll(":hover"),a=document.getElementById("answer");' +
    'var on=!!(a&&a.matches(":hover"));' +
    'return on?("still on the card, hover chain: "+[].map.call(h,function(e){' +
    ' return e.id||e.tagName;}).join(">")):"";})()');
}

/* AND THEN WAIT FOR THE SKY TO STOP, WHICH IS THE OTHER HALF OF park().
   THE POINTER STEERS THE CAMERA. §34's parallax eases the view toward a yaw and pitch derived
   from the cursor, on an exponential with its own tau - so a pointer that jumps from the middle
   of the window to (6,6) does not move the camera once, it moves it for the next several
   seconds. Measured, and it cost two reds: a plate taken immediately after a park read 12.63
   mean against a plate taken two seconds later, while two settled frames the same distance
   apart read 2.00. The sky had not misbehaved and the vanish had not left anything behind - the
   harness had nudged the camera and then photographed the easing.
   The page counts this for us: parallax.moves is frames on which the parallax actually touched
   the camera and parallax.holds frames on which it decided not to. So "still" is not a sampled
   position, it is moves having stopped climbing. */
async function settleSky(page, ms = 4000) {
  const t0 = Date.now();
  let last = -1, same = 0;
  while (Date.now() - t0 < ms) {
    const p = await page.json('__galaxy.camera.parallax');
    if (p.moves === last) { if (++same >= 2) return { ms: Date.now() - t0, moves: p.moves }; }
    else { same = 0; last = p.moves; }
    await sleep(140);
  }
  return { ms: Date.now() - t0, moves: last, timedOut: true };
}

/* ---- THE PIXEL BENCH, installed in the page ----
   THE HOUSE TECHNIQUE, unchanged from cine_proof and layout_proof: the browser decodes its own
   PNG. A decoder written here would be a second implementation of PNG in this repository and
   the one thing it could add is a bug of its own. Frames are kept under keys so that a later
   assertion can compare two captures taken a minute apart without either of them crossing the
   socket twice. */
const BENCH = `(function () {
  if (window.__kp) return 'already installed';
  var L = function (d, i) { return 0.2126 * d[i] + 0.7152 * d[i + 1] + 0.0722 * d[i + 2]; };
  window.__kp = {
    shots: {},
    marks: { speakDone: [], vanish: [], lines: [] },
    put: function (k, b64) {
      return new Promise(function (res) {
        var im = new Image();
        im.onload = function () {
          var c = document.createElement('canvas');
          c.width = im.naturalWidth; c.height = im.naturalHeight;
          var x = c.getContext('2d');
          x.drawImage(im, 0, 0);
          __kp.shots[k] = { w: c.width, h: c.height,
                            d: x.getImageData(0, 0, c.width, c.height).data };
          res({ w: c.width, h: c.height });
        };
        im.onerror = function () { res(null); };
        im.src = 'data:image/png;base64,' + b64;
      });
    },
    /* MEAN ABSOLUTE LUMINANCE DIFFERENCE, plus the worst single pixel and the share of pixels
       over a visible threshold. The mean is the number the churn argument rests on; the other
       two are there so that a difference concentrated in six pixels cannot hide inside a mean
       over two hundred thousand of them. */
    diff: function (a, b) {
      var A = __kp.shots[a], B = __kp.shots[b];
      if (!A || !B || A.w !== B.w || A.h !== B.h) return null;
      var sum = 0, worst = 0, over = 0, n = A.w * A.h;
      for (var i = 0; i < A.d.length; i += 4) {
        var d = Math.abs(L(A.d, i) - L(B.d, i));
        sum += d; if (d > worst) worst = d; if (d > 8) over++;
      }
      return { mean: +(sum / n).toFixed(4), worst: +worst.toFixed(2),
               pct: +(100 * over / n).toFixed(3), w: A.w, h: A.h };
    },
    /* LUMINANCE SPREAD DOWN EVERY COLUMN of a frame: max minus min. A column with structure in
       it - a star, the core's haze, a rim - has a spread; a dead flat band has none. This is
       how "stars and haze show THROUGH the panel" becomes a number. */
    spread: function (k) {
      var A = __kp.shots[k];
      if (!A) return null;
      var cols = [], flat = 0;
      for (var x = 0; x < A.w; x++) {
        var lo = 1e9, hi = -1e9;
        for (var y = 0; y < A.h; y++) {
          var v = L(A.d, (y * A.w + x) * 4);
          if (v < lo) lo = v; if (v > hi) hi = v;
        }
        var s = hi - lo;
        cols.push(s);
        if (s <= ${FLAT_TOL}) flat++;
      }
      var sorted = cols.slice().sort(function (p, q) { return p - q; });
      return { cols: cols.length, flat: flat,
               min: +sorted[0].toFixed(2),
               median: +sorted[Math.floor(sorted.length / 2)].toFixed(2),
               max: +sorted[sorted.length - 1].toFixed(2) };
    },
    /* THE FRAME AS A COARSE GRID of mean luminances, which is how "the sky shows through a
       12px blur" becomes measurable. A blur DESTROYS the stars as points and KEEPS the field
       they make: per-pixel comparison of a blurred frame against an unblurred one finds almost
       nothing, and a 6x8 grid of means finds the haze, the rim and the empty quarters exactly
       where they are. The harness then correlates this grid through the glass against the same
       grid of the bare sky, which is a claim an opaque slab cannot satisfy at any threshold:
       a slab's grid is flat, and a flat series correlates with nothing. */
    cells: function (k, nx, ny) {
      var A = __kp.shots[k];
      if (!A) return null;
      var out = [];
      for (var cy = 0; cy < ny; cy++) {
        for (var cx = 0; cx < nx; cx++) {
          var x0 = Math.floor(A.w * cx / nx), x1 = Math.floor(A.w * (cx + 1) / nx);
          var y0 = Math.floor(A.h * cy / ny), y1 = Math.floor(A.h * (cy + 1) / ny);
          var sum = 0, n = 0;
          for (var y = y0; y < y1; y++) {
            for (var x = x0; x < x1; x++) { sum += L(A.d, (y * A.w + x) * 4); n++; }
          }
          out.push(n ? +(sum / n).toFixed(3) : 0);
        }
      }
      return out;
    },
    /* THE MEAN COLOUR of a frame, which is what the contrast arithmetic composites the glass
       over: the real backdrop behind the real panel, rather than an assumed black. */
    mean: function (k) {
      var A = __kp.shots[k];
      if (!A) return null;
      var r = 0, g = 0, b = 0, n = A.w * A.h;
      for (var i = 0; i < A.d.length; i += 4) { r += A.d[i]; g += A.d[i + 1]; b += A.d[i + 2]; }
      return { r: +(r / n).toFixed(2), g: +(g / n).toFixed(2), b: +(b / n).toFixed(2),
               lum: +((0.2126 * r + 0.7152 * g + 0.0722 * b) / n).toFixed(2) };
    }
  };
  /* THE TWO ENDINGS, timestamped by the page as they happen. The grace is the distance between
     them and a harness that polled for it would be measuring its own poll interval. */
  addEventListener('speakDone', function () { __kp.marks.speakDone.push(Date.now()); });
  addEventListener('answerVanish', function (e) {
    __kp.marks.vanish.push({ at: Date.now(), instant: !!(e.detail && e.detail.instant),
                             why: (e.detail && e.detail.why) || '' });
  });
  addEventListener('speakLine', function (e) {
    __kp.marks.lines.push({ at: Date.now(), chunks: e.detail && e.detail.chunks });
  });
  return 'installed';
})()`;

/* ONE READING OF THE REVEAL, taken as a single evaluate so that the clock and the glass
   describe the same instant. Two evaluates across a 16ms frame describe two instants, and at
   2.6 words a second that is the whole of the tolerance being tested. */
const SAMPLE = `(function () {
  var k = __galaxy.kara;
  return { wall: Date.now(), where: k.where, on: k.on, words: k.words, spoken: k.spoken,
           said: k.said, seen: k.seen, chunk: k.chunk, h: k.h, h0: k.h0, moves: k.moves,
           flats: k.flats, mismatches: k.mismatches, why: k.why,
           engine: __galaxy.voice.engine, queue: __galaxy.voice.queue,
           draining: __galaxy.voice.draining, cap: __galaxy.caption.carries };
})()`;

/* THE WORD THE AUDIO CLOCK HAS EARNED, recomputed in Node from the server's own numbers. The
   page walks `starts` forwards in karaTick(); this walks the same array independently, and the
   tail rule is applied here too because it is part of the law and not a detail of the walk:
   once the clock is past the last word the VOICE will say, everything the card holds is shown. */
function expectedWords(s) {
  const c = s.chunk;
  if (!c || c.at == null || !c.starts || !c.starts.length) return null;
  let n = c.w0;
  for (let j = 0; j < c.starts.length; j++) if (c.at >= c.starts[j]) n = c.w0 + j + 1;
  if (n >= s.spoken) n = s.words;
  return n;
}

/* WCAG 2.1 contrast, the arithmetic written out rather than imported, over a backdrop that was
   MEASURED. A translucent panel has no colour of its own: what the eye gets is the glass
   composited over whatever sky is behind it, so the sky is sampled from a plate of the panel's
   own rectangle taken with the panel closed. */
const chan = (v) => { const c = v / 255; return c <= 0.04045 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4); };
const lumOf = (rgb) => 0.2126 * chan(rgb[0]) + 0.7152 * chan(rgb[1]) + 0.0722 * chan(rgb[2]);
function parseColour(s) {
  const m = String(s || '').match(/rgba?\(([^)]+)\)/);
  if (!m) return null;
  const p = m[1].split(/[,/\s]+/).filter(Boolean).map(Number);
  return { rgb: [p[0] || 0, p[1] || 0, p[2] || 0], a: p.length > 3 ? p[3] : 1 };
}
function over(fore, back) {              // source-over, premultiplied by hand
  return [0, 1, 2].map((i) => fore.a * fore.rgb[i] + (1 - fore.a) * back[i]);
}
function ratio(ink, bg) {
  const a = lumOf(ink), b = lumOf(bg);
  const hi = Math.max(a, b), lo = Math.min(a, b);
  return Math.round(((hi + 0.05) / (lo + 0.05)) * 100) / 100;
}
/* Pearson's r between two grids of the same shape. Null when either side is flat, which is
   not a failure to compute but the answer itself: a flat grid is an opaque panel. */
function correlate(a, b) {
  if (!a || !b || a.length !== b.length || a.length < 4) return null;
  const n = a.length;
  const ma = a.reduce((s, v) => s + v, 0) / n, mb = b.reduce((s, v) => s + v, 0) / n;
  let num = 0, da = 0, db = 0;
  for (let i = 0; i < n; i++) {
    const x = a[i] - ma, y = b[i] - mb;
    num += x * y; da += x * x; db += y * y;
  }
  if (da <= 0 || db <= 0) return null;
  return Math.round((num / Math.sqrt(da * db)) * 1000) / 1000;
}
/* The luminance the panel would read if it were the opaque slab §39 replaced: its own colour
   at alpha 1, in the same 0-255 weighting __kp uses, so the two numbers are comparable. */
const slabLum = (rgb) => r2(0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]);

const profiles = []; const procs = [];
/* PROFILE-SCOPED, never by window title: the one Chrome on this machine that must survive every
   harness is the employer's own on 9222. */
function shutChrome(profile) {
  spawnSync('powershell.exe', ['-NoProfile', '-Command',
    'Get-CimInstance Win32_Process | Where-Object { $_.Name -eq \'chrome.exe\' -and ' +
    '$_.CommandLine -match \'' + basename(profile) + '\' } | ' +
    'ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }'],
    { stdio: 'ignore' });
}

async function main() {
  const exe = CHROMES.find((p) => existsSync(p));
  if (!exe) throw new Error('no chrome.exe');
  try { mkdirSync(OUT, { recursive: true }); } catch { }
  const health = await (await fetch(GALAXY + '/health')).json();
  note('server: say ' + JSON.stringify(health.say && health.say.ready) +
       ' · model ' + ((health.say && health.say.model) || '?'));

  const profile = mkdtempSync(join(tmpdir(), 'karaoke-'));
  profiles.push(profile);
  procs.push(spawn(exe, ['--remote-debugging-port=' + PORT, '--user-data-dir=' + profile,
    '--no-first-run', '--no-default-browser-check', '--window-size=' + W + ',' + H,
    '--disable-features=CalculateNativeWinOcclusion',
    '--disable-backgrounding-occluded-windows', '--disable-renderer-backgrounding',
    '--new-window', GALAXY], { detached: true, stdio: 'ignore' }));
  for (let i = 0; i < 80; i++) { try { await cdp('/json/version'); break; } catch { await sleep(250); } }
  let target = null;
  for (let i = 0; i < 40; i++) {
    const l = await cdp('/json/list');
    target = (Array.isArray(l) ? l : []).filter((t) => t.type === 'page')
      .find((t) => t.url.includes('127.0.0.1:4700'));
    if (target) break; await sleep(300);
  }
  if (!target) throw new Error('no viewer page');
  const page = new Page(target.webSocketDebuggerUrl);
  await page.open();
  await page.send('Runtime.enable');
  await page.send('Page.enable');
  try { await page.send('Page.bringToFront'); } catch (e) { note('bringToFront: ' + e.message); }
  const keeper = keepFront(page);

  ok(!!await waitFor(page, '!!(window.__galaxy && __galaxy.kara && __galaxy.vanish && ' +
     '__galaxy.sidebar)', 30000), 'the viewer is up and exposes §39: kara, vanish and sidebar');
  note(await page.evaluate(BENCH));

  /* ---- 0. THE ROOM THIS IS BEING MEASURED IN ---------------------------- */
  const room = await page.json('({vw: innerWidth, vh: innerHeight, dpr: devicePixelRatio,' +
    ' vis: document.visibilityState, focus: document.hasFocus(),' +
    ' reduced: matchMedia("(prefers-reduced-motion: reduce)").matches,' +
    ' nomove: document.documentElement.classList.contains("nomove"),' +
    ' muted: __galaxy.speech.muted, vanishOff: __galaxy.vanish.off,' +
    ' fadeMs: __galaxy.vanish.fadeMs, grace: __galaxy.vanish.GRACE_MS,' +
    /* THE DISSOLVE IS READ OFF THE CASCADE, not off the resting card: vanishFadeMs() reports
       whatever transition the card currently carries, and --vanish-ms only becomes that
       transition once .vanishing is on it. Both numbers are taken and the larger is used as
       the window, so the grace assertion cannot be made to pass by a small resting value. */
    ' vanishMs: parseFloat(getComputedStyle(document.documentElement)' +
    '   .getPropertyValue("--vanish-ms")) || 0,' +
    ' idle: __galaxy.sidebar.IDLE_MS})');
  note('room: ' + room.vw + 'x' + room.vh + ' · dpr ' + room.dpr + ' · ' + room.vis +
       ' · reduced-motion ' + room.reduced);
  ok(room.muted === false && room.vanishOff === false,
     'this tab is NOT muted and the vanish is NOT pinned - the subject is the real feature',
     JSON.stringify(room));
  ok(room.reduced === false && room.nomove === false,
     'and nothing has asked the page to hold still, so the dissolve and the accent are live',
     JSON.stringify({ reduced: room.reduced, nomove: room.nomove }));

  await realClick(page, Math.round(room.vw * 0.5), Math.round(room.vh * 0.28));
  ok(!!await waitFor(page, '__galaxy.speech.unlocked === true', 8000),
     'one real click unlocks the audio, as the autoplay policy requires');
  /* AND THE POINTER IS PARKED IN THE CORNER. A mouse left where it clicked is a mouse RESTING
     ON THE CARD once a card is rendered under it, and §39 holds a hovered card deliberately -
     so an unparked pointer silently converts every vanish assertion below into a test of the
     hover exemption. Measured, not guessed: the first run of this file recorded a hold reading
     "the pointer is on the card" before the gate section had even begun. */
  const parked = await park(page);
  ok(parked === '',
     'the pointer is parked in the corner, so nothing below is accidentally testing the hover ' +
     'hold instead of the vanish - and park() is called again after every plate, because a ' +
     'clipped screenshot hands hover back to the real cursor',
     parked);
  await waitFor(page, '__galaxy.voice.engineWhy && __galaxy.voice.engineWhy !== "not asked yet"',
                15000);
  const eng = await page.json('({engine: __galaxy.voice.engine, why: __galaxy.voice.engineWhy,' +
    ' down: __galaxy.voice.down})');
  note('ENGINE: ' + eng.engine + ' · ' + eng.why);
  ok(eng.engine === 'piper' && eng.down === '',
     'the local voice is carrying the chunks, which is the only path with an audio clock',
     JSON.stringify(eng));
  if (eng.engine !== 'piper') {
    note('WITHOUT PIPER THERE IS NO CLOCK TO MEASURE. The reveal is deliberately not armed on ' +
         'the browser\'s own voice, so the sections below would be asserting about a feature ' +
         'that correctly stood itself down. Stopping here rather than printing green.');
    keeper.stop(); page.close(); return;
  }
  /* The queue must be empty before the first answer: a boot line still draining would arm the
     reveal against a sentence this harness did not choose. */
  await waitFor(page, '__galaxy.voice.draining === false', 20000);
  await page.evaluate('__galaxy.speech.cancel("the harness is clearing the room")');
  await sleep(400);

  /* ================================================================== */
  /* 1. THE SKY, BEFORE ANY CARD - and the churn that is the tolerance   */
  /* ================================================================== */
  /* THE CLIP IS THE CARD'S OWN RECTANGLE, found by putting a card up and reading it, because a
     rectangle written down here would be an assertion about this build's layout. The card is
     then wiped instantly - the same wipe a new utterance does - and the sky's own churn is
     measured in that exact rectangle with nothing in it. */
  await page.evaluate('__galaxy.page.render("sizing the frame", ' +
    JSON.stringify(LONG_ANSWER) + ')');
  await sleep(600);
  const clipRaw = await page.json(
    '(function(){var r=document.getElementById("answer").getBoundingClientRect();' +
    'return {x:Math.round(r.left),y:Math.round(r.top),w:Math.round(r.width),' +
    'h:Math.round(r.height)};})()');
  /* Inset by two pixels so the rounded corner's antialiasing and the 1px rim are outside the
     comparison: those pixels belong to the card, and the question being asked is about the sky. */
  const CLIP = { x: clipRaw.x + 2, y: clipRaw.y + 2, w: clipRaw.w - 4, h: clipRaw.h - 4 };
  note('the card\'s rectangle: ' + clipRaw.w + 'x' + clipRaw.h + ' at ' +
       clipRaw.x + ',' + clipRaw.y);
  const wiped = await page.evaluate('__galaxy.vanish.now(true)');
  ok(wiped === true, 'the sizing card is wiped instantly, the way a new utterance wipes one');
  /* EVERY WAIT BELOW IS FOR AN INCREMENT OF THIS COUNTER AND NEVER FOR IT TO BE NON-ZERO. The
     wipe just above already moved it, and the boot ceremony's own silent card moved it before
     that: a `done > 0` wait would have been satisfied in one millisecond by a card that left
     a minute ago, and the plate taken afterwards would have been a plate of the card still
     sitting there. That is exactly what the first run of this file did. */
  let doneAt = await page.json('__galaxy.vanish.done');
  let marksAt = (await page.json('__kp.marks')).vanish.length;
  note('the vanish counter already stands at ' + doneAt + ' (the boot ceremony\'s silent card ' +
       'and the sizing wipe), so every wait below is for an increment of it');
  await sleep(700);
  const gone0 = await page.json('__galaxy.vanish.card');
  ok(gone0.className === '' && gone0.rects === 0 && gone0.text === 0,
     'and it left NOTHING: no classes, no rectangle, no paragraph',
     JSON.stringify(gone0));

  const still = await settleSky(page);
  note('the camera is still before the baseline: the parallax stopped touching it after ' +
       still.ms + 'ms' + (still.timedOut ? ' - OR DID NOT, which is reported here because ' +
       'every plate below is a comparison of two frames' : ''));
  for (const k of ['pre1', 'pre2', 'pre3']) {
    const b64 = await page.shot(k === 'pre1' ? join(OUT, 'kara-sky-pre.png') : null, CLIP);
    await page.evaluate('__kp.put("' + k + '", "' + b64 + '")');
    await sleep(420);
  }
  const churnA = await page.json('__kp.diff("pre1","pre2")');
  const churnB = await page.json('__kp.diff("pre2","pre3")');
  const churnC = await page.json('__kp.diff("pre1","pre3")');
  const CHURN = Math.max(churnA.mean, churnB.mean, churnC.mean);
  const CHURN_PCT = Math.max(churnA.pct, churnB.pct, churnC.pct);
  note('THE SKY\'S OWN CHURN in that rectangle, three frames 420ms apart: mean ' +
       churnA.mean + ' / ' + churnB.mean + ' / ' + churnC.mean +
       ' · worst pixel ' + Math.max(churnA.worst, churnB.worst, churnC.worst) +
       ' · pixels over 8: ' + CHURN_PCT + '%');
  ok(CHURN > 0, 'the galaxy is ALIVE in that rectangle - the churn is non-zero, which is why ' +
     '"pixel-identical" is measured against the churn and not against zero',
     JSON.stringify({ churnA, churnB, churnC }));

  /* ================================================================== */
  /* 2. THE WORD LAYER ON THE CARD, AND THE DRIFT                        */
  /* ================================================================== */
  const armed = await page.json(
    '(function(){var t=' + JSON.stringify(LONG_ANSWER) + ';' +
    ' __galaxy.page.render("what happened to the pricing page", t);' +
    ' var s=__galaxy.camera.spokenForm(t);' +
    ' __galaxy.speech.speakLine(s);' +
    ' return {spoken:s, spokenWords:s.split(/\\s+/).filter(Boolean).length,' +
    '  held:t.split(/\\s+/).filter(Boolean).length, where:__galaxy.kara.where,' +
    '  why:__galaxy.kara.why, words:__galaxy.kara.words, seen:__galaxy.kara.seen,' +
    '  h0:__galaxy.kara.h0, yielded:__galaxy.caption.yielded};})()');
  note('the answer: ' + armed.held + ' words held, ' + armed.spokenWords + ' spoken (the ' +
       '260-character cap), card.yield=' + armed.yielded);
  ok(armed.where === 'card',
     'THE CAPPED ANSWER RUNS ON THE CARD: the voice says less than the card holds, so §38\'s ' +
     'yield does not fire and the paragraph is where a person is reading it',
     JSON.stringify({ where: armed.where, why: armed.why, yielded: armed.yielded }));
  ok(armed.words === armed.held && armed.seen.spans === armed.held,
     'every word of the paragraph is in the DOM before any of them is visible: ' +
     armed.seen.spans + ' spans for ' + armed.held + ' words',
     JSON.stringify(armed.seen));
  ok(armed.seen.said === 0 && armed.seen.hidden === armed.held &&
     armed.seen.onGlass === armed.held,
     'and at the instant it was armed NONE was revealed and ALL had a rectangle - which is the ' +
     'zero-reflow guarantee itself: visibility, never display',
     JSON.stringify(armed.seen));
  /* h0 ARRIVES ON THE FIRST FRAME OF THE REVEAL - karaUp() is called from src.start(), so that
     frame is the audio's own frame and it lights the first word immediately after recording the
     height. `said <= 1` is therefore the strongest reading available from out here, and the
     guarantee that it was recorded with NOTHING lit is the page's own `!kara.said` guard, which
     is why h0 === hArm is asserted beside it: two layout heights taken whole seconds apart,
     one before the audio and one on it, agreeing to the pixel. */
  const settled = await waitFor(page, '__galaxy.kara.h0 > 0', 20000);
  const heights = await page.json('({hArm: __galaxy.kara.hArm, h0: __galaxy.kara.h0,' +
    ' h: __galaxy.kara.h, paint: __galaxy.kara.hPaint, said: __galaxy.kara.seen.said})');
  ok(!!settled && heights.h0 > 0 && heights.said <= 1 && heights.h0 === heights.hArm,
     'the surface\'s LAYOUT height was recorded on the first frame of the reveal and before ' +
     'that frame lit anything: ' + heights.h0 + 'px, the same number arming read (' +
     heights.hArm + 'px), with ' + heights.said + ' word(s) lit by the time it was asked for',
     JSON.stringify(heights));
  note('and the PAINTED box at this instant reads ' + heights.paint + 'px - @keyframes rise ' +
       'brings the card in at scale(.985), so the client rect moves 196 → 198 → 199 while the ' +
       'layout box never does. That is why the reflow law is written on offsetHeight: a word ' +
       'going from hidden to visible cannot change a layout height, and measuring the painted ' +
       'one scored the card\'s own entrance as 82 reflows');

  /* ---- the five timestamps ---- */
  const waited = await waitFor(page, '__galaxy.kara.chunk && __galaxy.kara.chunk.at !== null &&' +
    ' __galaxy.kara.chunk.at > 0.05', 20000);
  ok(!!waited, 'audio is on the bus and the chunk clock is running (' + waited + 'ms to the ' +
     'first sample)');
  const samples = [];
  for (let i = 0; i < 5; i++) {
    await sleep(i === 0 ? 900 : 1100);
    const s = await page.json(SAMPLE);
    s.want = expectedWords(s);
    samples.push(s);
  }
  console.log('        clock      chunk  starts  expected  visible  drift   accent');
  let drifts = 0, usable = 0;
  for (const s of samples) {
    if (s.want == null) { console.log('        (no chunk on the clock at this instant)'); continue; }
    usable++;
    const d = s.seen.said - s.want;
    if (Math.abs(d) > DRIFT_TOL) drifts++;
    console.log('       ' + String(r2(s.chunk.at)).padStart(7) + 's' +
      String(s.chunk.i).padStart(7) + String(s.chunk.starts.length).padStart(8) +
      String(s.want).padStart(10) + String(s.seen.said).padStart(9) +
      String(d > 0 ? '+' + d : d).padStart(7) + String(s.seen.accent).padStart(9));
  }
  ok(usable === 5, 'five readings were taken with the audio clock live in all five',
     JSON.stringify(samples.map((s) => s.chunk && s.chunk.at)));
  ok(usable === 5 && drifts === 0,
     'THE DRIFT IS INSIDE ONE WORD AT EVERY ONE OF THE FIVE, against the server\'s own ' +
     'X-Word-Timings walked independently here',
     JSON.stringify(samples.map((s) => ({ at: s.chunk && s.chunk.at, want: s.want,
                                          said: s.seen.said }))));
  ok(samples.every((s) => s.seen.accent <= 1),
     'and at most ONE word wore the accent at a time - it is a state on the word being said, ' +
     'not a trail',
     JSON.stringify(samples.map((s) => s.seen.accent)));
  ok(samples.every((s) => s.seen.said > 0) && samples[4].seen.said > samples[0].seen.said,
     'the reveal moved forwards across the five: ' +
     samples.map((s) => s.seen.said).join(' → ') + ' of ' + armed.words);
  ok(samples.every((s) => s.where === 'card' && s.seen.onGlass === s.seen.spans),
     'every span stayed ON THE GLASS throughout - the reveal is lighting words a person can ' +
     'actually see, which is the trap §38\'s yield law sets for this feature',
     JSON.stringify(samples.map((s) => [s.where, s.seen.onGlass, s.seen.spans])));
  ok(samples.every((s) => s.moves === 0 && s.h === s.h0),
     'ZERO REFLOW, measured at all five: the card\'s height never moved from ' + heights.h0 +
     'px and the page\'s own counter stands at 0',
     JSON.stringify(samples.map((s) => [s.h0, s.h, s.moves])));
  ok(samples.every((s) => s.mismatches === 0),
     'and the server and the page counted the SAME words in every chunk - no spread-evenly ' +
     'fallback was needed (flats: ' + samples[4].flats + ')',
     JSON.stringify(samples.map((s) => [s.mismatches, s.flats])));

  /* ---- the mid-answer plate, and the tail ---- */
  const midB64 = await page.shot(join(OUT, 'kara-mid-reveal.png'), CLIP);
  await park(page);                        // the clip resize just handed hover to the real cursor
  await page.evaluate('__kp.put("mid", "' + midB64 + '")');
  const mid = await page.json('__kp.diff("pre1","mid")');
  const midSeen = await page.json(SAMPLE);
  note('the mid-reveal plate was taken at word ' + midSeen.seen.said + ' of ' + midSeen.words);
  ok(mid.mean > CHURN * 2 && mid.pct > CHURN_PCT * 1.4,
     'THE CARD IS REALLY THERE: the mid-answer frame differs from the pre-answer sky by ' +
     mid.mean + ' against a churn of ' + r2(CHURN) + ' - ' +
     r2(mid.mean / Math.max(CHURN, 0.0001)) + 'x - over ' + mid.pct + '% of the rectangle ' +
     'against the churn\'s ' + CHURN_PCT + '%',
     JSON.stringify({ mid, churn: CHURN, churnPct: CHURN_PCT }));

  /* ---- the ending: full text, then the grace ---- */
  const done = await waitFor(page, '__galaxy.voice.draining === false && ' +
    '__galaxy.voice.done > 0', 150000);
  ok(!!done, 'the queue ran dry: the whole capped answer was read');
  await sleep(250);
  const whole = await page.json(SAMPLE);
  ok(whole.seen.said === whole.seen.spans && whole.seen.accent === 0,
     'AND THE WHOLE PARAGRAPH IS ON THE GLASS when the voice stops, tail included: ' +
     whole.seen.said + ' of ' + whole.seen.spans + ' words, no accent left behind',
     JSON.stringify(whole.seen));
  ok(whole.moves === 0 && whole.h === whole.h0,
     'and the card is still exactly the height it was before the first word: ' + whole.h + 'px',
     JSON.stringify({ h0: whole.h0, h: whole.h, moves: whole.moves }));

  /* ================================================================== */
  /* 3. THE VANISH, AND THE SKY COMING BACK                              */
  /* ================================================================== */
  const drifted = await page.evaluate('__galaxy.vanish.holdNow');
  const reparked = await park(page);
  if (drifted === 'the pointer is on the card') {
    note('THE POINTER HAD DRIFTED BACK ONTO THE CARD between the plate and here - the clipped ' +
         'capture handed hover to the real cursor - and park() has moved it off again' +
         (reparked ? ', UNSUCCESSFULLY: ' + reparked : ''));
  }
  const before = await page.json('__galaxy.vanish.record');
  const armedV = await page.json('({inMs: __galaxy.vanish.inMs, why: __galaxy.vanish.why,' +
    ' armed: __galaxy.vanish.armed, pending: __galaxy.vanish.pending,' +
    ' hold: __galaxy.vanish.holdNow, fade: __galaxy.vanish.fadeMs})');
  ok(armedV.pending === true && armedV.inMs > 0 && armedV.inMs <= room.grace,
     'THE GRACE IS ARMED by the voice ending, with ' + armedV.inMs + 'ms left of ' + room.grace +
     ' - because "' + armedV.why + '"',
     JSON.stringify(armedV));
  ok(armedV.hold === '', 'and nothing is holding the card: no gate, no pointer, no focus',
     'holdNow said: "' + armedV.hold + '"');
  const FADE = Math.max(armedV.fade, room.vanishMs);
  const left = await waitFor(page, '__galaxy.vanish.done > ' + doneAt,
                             room.grace + FADE + 6000);
  ok(!!left, 'the card left on its own, ' + left + 'ms after the grace was read');
  const marks = await page.json('__kp.marks');
  if (marks.speakDone.length && marks.vanish.length > marksAt) {
    const gap = marks.vanish[marksAt].at - marks.speakDone[marks.speakDone.length - 1];
    note('MEASURED GRACE, end of voice to card removed: ' + gap + 'ms (' + room.grace +
         ' named + ' + FADE + 'ms dissolve = ' + (room.grace + FADE) + ')');
    ok(gap >= room.grace && gap <= room.grace + FADE + 900,
       'and the grace the page kept is the grace it names: ' + gap + 'ms, inside [' + room.grace +
       ', ' + (room.grace + FADE + 900) + ']',
       JSON.stringify({ gap, grace: room.grace, fade: FADE, resting: armedV.fade }));
    ok(marks.vanish[marksAt].instant === false &&
       marks.vanish[marksAt].why === 'the voice ended',
       'it DISSOLVED rather than snapped, and for the right reason - "' +
       marks.vanish[marksAt].why + '". The fade is the courtesy; the removal is the point',
       JSON.stringify(marks.vanish.slice(marksAt)));
  } else { note('no new event marks came back; the two assertions above are skipped'); }
  doneAt = await page.json('__galaxy.vanish.done');
  marksAt = (await page.json('__kp.marks')).vanish.length;
  const after = await page.json('__galaxy.vanish.card');
  ok(after.className === '' && after.rects === 0 && after.text === 0 && after.q === 0 &&
     after.chips === 0 && after.ask === false,
     'THE CARD IS GONE AND NOT MERELY TRANSPARENT: no classes, no rectangle, no question, no ' +
     'paragraph, no chips, no gate',
     JSON.stringify(after));
  const record = await page.json('__galaxy.vanish.record');
  ok(record.chunks === before.chunks && record.spoke === before.spoke &&
     record.ids === before.ids && record.ledger === before.ledger,
     'AND IT IS DISPLAY-ONLY: the chunk log, the queue\'s line ids, the spoken count and the ' +
     'ledger rows are all exactly as they were (' + JSON.stringify(before) + ') - four ' +
     'counters that only ever go up, which is what an assertion of this shape needs',
     JSON.stringify({ before, after: record }));
  /* The caption has its own four seconds and its own half-second fade; the sky is not back
     until both surfaces are. */
  await waitFor(page, '__galaxy.caption.up === false', 9000);
  await sleep(900);
  const postB64 = await page.shot(join(OUT, 'kara-sky-post.png'), CLIP);
  await page.evaluate('__kp.put("post", "' + postB64 + '")');
  const post = await page.json('__kp.diff("pre1","post")');
  const postSp = await page.json('__kp.spread("post")');
  const preSp = await page.json('__kp.spread("pre1")');
  const midSp = await page.json('__kp.spread("mid")');
  /* THE LONG BASELINE IS REPORTED AND NOT ASSERTED ON, and this is the one place in the file
     where the mandate's own words have to be read as a claim about the DECK rather than about a
     bitmap. "The sky returns to exactly its pre-answer state" cannot be measured as a diff
     against a plate taken ninety seconds earlier, because this galaxy turns: 17% of the pixels
     in this rectangle already differ between two frames 420ms apart, and over the minute and a
     half a long answer takes to be spoken the rectangle holds a different part of the sky
     altogether. Measured here: 36.3 mean against the card's own 26.3 - a diff that would red
     the vanish for the crime of the galaxy having rotated, and pass a vanish that left a
     DARKER card behind. So two honest measurements replace it, and both are below. */
  note('POST-VANISH against the pre-answer plate, NINETY SECONDS OF ROTATION LATER: mean ' +
       post.mean + ' · worst pixel ' + post.worst + ' · pixels over 8: ' + post.pct +
       '%   (two sky frames 420ms apart: mean ' + r2(CHURN) + ', ' + CHURN_PCT + '%)');
  /* MEASUREMENT ONE: the column spread, which rotation barely moves and a card multiplies.
     WHICH WAY ROUND IT GOES WAS MEASURED, and the first version of this assertion had it
     backwards. In the SIDEBAR's text-free band a 12px backdrop-blur DESTROYS the spread - 47
     bare, 3 through the glass - and that is the number PART 4 is argued on. The answer card is
     the opposite case and for an obvious reason once seen: it is full of #f2f6ff words at
     luminance 245 on glass at 15, so any column crossing a line of text spreads by 200-odd.
     Open sky reads about 46 in this rectangle and the card about 177. Both are invariant to
     WHICH stars are where, which is the property that survives ninety seconds of rotation. */
  ok(postSp.median > preSp.median * 0.5 && postSp.median < preSp.median * 2 &&
     midSp.median > postSp.median * 2,
     'THE RECTANGLE IS OPEN SKY AGAIN AND NOT A CARD: its median column spread reads ' +
     postSp.median + ' after the vanish against ' + preSp.median + ' before the answer - the ' +
     'same figure - where with the card over it the lit words took it to ' + midSp.median +
     '. A rotating galaxy changes which stars are in the band and not what a band of stars ' +
     'measures, which is why this survives a baseline a pixel diff cannot',
     JSON.stringify({ post: postSp.median, pre: preSp.median, card: midSp.median }));
  /* MEASUREMENT TWO: THE SAME CARD, UP AND AWAY AGAIN, ON A SHORT BASELINE. Three frames
     inside two seconds, which is the baseline the churn was measured on - so "to within the
     sky's own churn" means what it says. The removal is the real one: vanishNow(false) is the
     function the four-second grace itself calls, with the same dissolve and the same removal;
     only the waiting is skipped, because what is being measured here is the rectangle and not
     the clock - the clock is §2 above and the hold is §6. */
  /* A THROWAWAY FRAME BEFORE THE SETTLE, AND NO park() ANYWHERE IN THIS BLOCK - which is the
     second repair of the same fault and the one that found its cause. Settling the camera and
     THEN taking the first plate still read 3.46° of yaw across the triple, with not one mouse
     event dispatched in between: the clipped capture resizes the surface, the renderer
     re-derives the pointer from the real OS cursor, and the parallax target jumps from the
     corner park() put it in to wherever the employer's cursor actually is - so the very act of
     photographing the sky is what starts the ease. Taking one frame FIRST pays that jump before
     anything is measured; every capture after it re-derives the same cursor, so the target stops
     moving and the four frames are shot from one aim. The hover hold this park used to defend
     against is irrelevant here, because the removal below is vanishNow() and not a grace. */
  await page.shot(null, CLIP);
  const stillA = await settleSky(page);
  const camA = await page.json('__galaxy.camera.parallax');
  const tA = Date.now();
  const skyA = await page.shot(null, CLIP);
  await page.evaluate('__kp.put("skyA", "' + skyA + '")');
  await page.evaluate('__galaxy.page.render("what happened to the pricing page", ' +
    JSON.stringify(LONG_ANSWER) + ')');
  await sleep(700);                                  // the entrance spring, and then a frame
  await page.evaluate('__kp.put("cardB", "' + (await page.shot(null, CLIP)) + '")');
  /* AND NOT ONE MOUSE EVENT INSIDE THE FOUR FRAMES, which is why this calls vanishNow()
     directly instead of arming a short grace: an armed grace has to be protected from the
     hover hold, protecting it means parking the pointer, and parking the pointer swings the
     camera for the next two seconds - 103 frames of parallax, measured by the assertion
     below, straight through the middle of a pixel comparison. vanishNow(false) is the same
     function the grace calls, with the same dissolve and the same removal; the four seconds
     and the hold are measured where they belong, above and in §6. */
  const armShort = await page.evaluate('__galaxy.vanish.now(false)');
  const wentB = await waitFor(page, '__galaxy.vanish.done > ' + doneAt, 3000 + FADE);
  await sleep(FADE + 350);
  await page.evaluate('__kp.put("skyC", "' + (await page.shot(null, CLIP)) + '")');
  const camC = await page.json('__galaxy.camera.parallax');
  const skyBack = await page.json('__kp.diff("skyA","skyC")');
  const covered = await page.json('__kp.diff("skyA","cardB")');
  /* AND THE CONTROL IS TAKEN ON THE SAME INTERVAL, which is the whole reason this is worth
     doing twice: the churn above was measured over 420ms and these two frames are 1.8s apart,
     so the tolerance has to be the sky's drift over 1.8s and not over 420ms. skyD is skyC
     plus exactly the interval that separated skyA from skyC, with nothing happening in
     between - so diff(skyC,skyD) is what "the sky moved on its own" costs on this baseline. */
  const SPAN = Date.now() - tA;                      // the real skyA → skyC interval, measured
  await sleep(SPAN);
  await page.evaluate('__kp.put("skyD", "' + (await page.shot(null, CLIP)) + '")');
  const drift = await page.json('__kp.diff("skyC","skyD")');
  const camD = await page.json('__galaxy.camera.parallax');
  const TOL = Math.max(drift.mean * 1.5 + 0.5, CHURN + 0.5);
  /* AND THE CAMERA POINTED THE SAME WAY AT BOTH ENDS - as an ANGLE and not as a frame count,
     which is the repair of an assertion I wrote wrong on the previous run. Requiring
     `parallax.moves` to be unchanged demands something no headed harness on a live desktop can
     promise: the loop eases every frame it is above PARALLAX_EPS, the real OS cursor is a
     position this process does not own, and a clipped captureScreenshot resizes the surface and
     has the renderer re-derive the pointer from that cursor - so the counter climbed 103 while
     both pixel assertions it was guarding passed. What a pixel comparison actually needs is not
     a still loop but a camera aimed identically in the two frames being compared, and parYaw /
     parPitch are exactly that number. The spin is deliberately NOT in them: the galaxy's own
     rotation is what the skyC→skyD control is for. */
  const dYaw = Math.abs(camC.yawDeg - camA.yawDeg);
  const dPitch = Math.abs(camC.pitchDeg - camA.pitchDeg);
  ok(dYaw <= 0.25 && dPitch <= 0.25,
     'and THE CAMERA WAS AIMED THE SAME WAY IN THE TWO FRAMES BEING COMPARED: the parallax ' +
     'offset moved ' + r2(dYaw) + '° of yaw and ' + r2(dPitch) + '° of pitch between skyA and ' +
     'skyC (ceiling 0.25° each), which is what makes a pixel diff of them mean anything at all ' +
     '- the pointer steers this view, and a plate taken while the easing was still running ' +
     'reads like a card that never left. The loop itself ticked ' +
     (camD.moves - camA.moves) + ' frames across all four, reported and not required',
     JSON.stringify({ a: { yaw: camA.yawDeg, pitch: camA.pitchDeg, moves: camA.moves },
                      c: { yaw: camC.yawDeg, pitch: camC.pitchDeg, moves: camC.moves },
                      d: { moves: camD.moves }, settleTook: stillA.ms }));
  note('SHORT BASELINE, sky → card → sky inside ' + r2(SPAN / 1000) + 's: the card changes ' +
       covered.mean + ' of that rectangle (' + covered.pct + '% of its pixels); the sky after ' +
       'it reads ' + skyBack.mean + ' against the sky before it (' + skyBack.pct + '%); and the sky ' +
       'drifts ' + drift.mean + ' (' + drift.pct + '%) on its own over the same ' +
       r2(SPAN / 1000) + 's with no card in it at all');
  ok(armShort === true && !!wentB && skyBack.mean <= TOL,
     'THE SKY RETURNS TO EXACTLY ITS PRE-ANSWER STATE, to within what the sky does on its own: ' +
     skyBack.mean + ' across the card going up and coming away, against ' + drift.mean +
     ' for the same rectangle over the same ' + r2(SPAN / 1000) + 's of an untouched galaxy ' +
     '(tolerance ' + r2(TOL) + ')',
     JSON.stringify({ skyBack, drift, tol: r2(TOL), armed: armShort, left: wentB }));
  ok(covered.mean > skyBack.mean * 2 && covered.pct > skyBack.pct * 1.4,
     'and the rectangle KNOWS the difference: the card moved it ' +
     r2(covered.mean / Math.max(skyBack.mean, 0.0001)) + 'x as far as the sky moved itself over ' +
     'the same ' + r2(SPAN / 1000) + 's - so a vanish that had left anything behind would have ' +
     'shown here',
     JSON.stringify({ card: covered, sky: skyBack }));
  doneAt = await page.json('__galaxy.vanish.done');
  marksAt = (await page.json('__kp.marks')).vanish.length;

  /* ================================================================== */
  /* 4. THE CAPTION SURFACE - the commonest answer in the house           */
  /* ================================================================== */
  /* ---- A2, PATH ONE: NO AUDIO CLOCK AT ALL ----
     §38's law is about WHICH SURFACE holds the sentence, and it has to hold whether or not a
     sample is ever decoded. This is the path where none is: the line is handed to the funnel
     and the queue is then emptied before anything can start, which is what a cancel, a chunk
     that will not start and a synthesis that fails all come down to. The caption must be up
     with the WHOLE sentence on it, at once, exactly as it was before A2 - there is no clock
     to dole it out word by word and pretending otherwise would hide the answer. */
  const fbBefore = await page.json('__galaxy.caption.fallbacks');
  const shortFall = await page.json(
    '(function(){var t=' + JSON.stringify(SHORT_ANSWER) + ';' +
    ' __galaxy.page.render("is the importer caught up", t);' +
    ' __galaxy.speech.speakLine(__galaxy.camera.spokenForm(t));' +
    ' __galaxy.speech.cancel("the fallback path under test");' +
    ' var n=function(s){return String(s||"").replace(/\\s+/g," ").trim();};' +
    ' return {held:__galaxy.caption.held, fallbacks:__galaxy.caption.fallbacks,' +
    '  holdWhy:__galaxy.caption.holdWhy, yielded:__galaxy.caption.yielded,' +
    '  carries:__galaxy.caption.carries, whole:n(__galaxy.caption.text)===n(t)};})()');
  ok(shortFall.yielded === true && shortFall.carries.card === '',
     '§38 STILL HOLDS ON THE FALLBACK PATH: the voice says exactly what the card holds, so ' +
     'the card yields and the caption carries the sentence - and it holds with no audio ' +
     'clock in the room, which is the case A2 had to leave standing',
     JSON.stringify({ yielded: shortFall.yielded, carries: shortFall.carries }));
  ok(shortFall.fallbacks === fbBefore + 1 && shortFall.held === false && shortFall.whole,
     'AND THE WHOLE LINE IS UP AT ONCE: the hold fell back (' + shortFall.holdWhy + '), ' +
     'nothing is still being held, and the caption reads the complete sentence. A deferred ' +
     'caption that could be left waiting for audio that never comes would be an answer the ' +
     'employer never sees, which is a worse bug than the one A2 set out to fix',
     JSON.stringify(shortFall));

  /* ---- A2, PATH TWO: THE AUDIO CLOCK STARTS ----
     The normal path, and the one that changed. The caption and the reveal now BOTH begin at
     src.start() rather than at speakLine(), so this is waited for rather than read in the
     same tick - reading it synchronously is reading the moment before the feature runs. The
     claim is unchanged from §39: the reveal takes the caption as its surface and every word of
     the sentence is a span with a rectangle. */
  await page.evaluate('__galaxy.speech.cancel("resetting for the normal path")');
  await sleep(250);
  await page.evaluate(
    '(function(){var t=' + JSON.stringify(SHORT_ANSWER) + ';' +
    ' __galaxy.page.render("is the importer caught up", t);' +
    ' __galaxy.speech.speakLine(__galaxy.camera.spokenForm(t));})()');
  const armedOk = await waitFor(page, '__galaxy.kara.where === "caption"', 30000);
  const shortArm = await page.json(
    '(function(){return {where:__galaxy.kara.where, why:__galaxy.kara.why,' +
    '  words:__galaxy.kara.words, seen:__galaxy.kara.seen,' +
    '  yielded:__galaxy.caption.yielded, carries:__galaxy.caption.carries,' +
    '  flushes:__galaxy.caption.flushes, h0:__galaxy.kara.h0};})()');
  ok(!!armedOk && shortArm.where === 'caption' && shortArm.seen.spans === shortArm.words &&
     shortArm.seen.onGlass === shortArm.seen.spans,
     'AND THE REVEAL FOLLOWED THE SENTENCE ONTO THE CAPTION: ' + shortArm.seen.spans +
     ' spans, all of them with a rectangle. Wired to #a-text alone this feature would have ' +
     'been invisible in the commonest case in the house',
     JSON.stringify(shortArm));
  /* WAITED FOR, NOT SLEPT THROUGH. The first chunk of a new sentence takes seconds to arrive -
     piper synthesises it, the server times it and the page decodes it, which measured 5.3s on
     this machine - so a fixed sleep lands before the first word and reads a prefix of zero. */
  await waitFor(page, '__galaxy.kara.seen.said > 0', 25000);
  await sleep(500);
  const capMid = await page.json(SAMPLE);
  ok(capMid.seen.said > 0 && capMid.seen.said < capMid.seen.spans,
     'mid-sentence the caption is a PREFIX on the glass: ' + capMid.seen.said + ' of ' +
     capMid.seen.spans + ' words',
     JSON.stringify(capMid.seen));
  ok(capMid.moves === 0 && capMid.h === capMid.h0,
     'and the caption\'s own box has not moved either: ' + capMid.h + 'px, ' + capMid.moves +
     ' moves - the words were all in it before any of them was visible',
     JSON.stringify({ h0: capMid.h0, h: capMid.h, moves: capMid.moves }));
  const capFull = await page.evaluate('document.getElementById("caption").textContent');
  ok(capFull.replace(/\s+/g, ' ').trim() === SHORT_ANSWER.replace(/\s+/g, ' ').trim(),
     'while textContent reads the WHOLE sentence throughout - a screen reader, a harness and ' +
     'the caption probe all see the complete line, as eight standing assertions require');
  await waitFor(page, '__galaxy.voice.draining === false', 60000);
  await sleep(300);
  const capEnd = await page.json(SAMPLE);
  ok(capEnd.seen.said === capEnd.seen.spans,
     'and the whole caption is lit when the voice stops: ' + capEnd.seen.said + '/' +
     capEnd.seen.spans);
  ok(!!await waitFor(page, '__galaxy.vanish.done > ' + doneAt, room.grace + FADE + 7000),
     'and the caption\'s card went too, on the same grace - the reveal\'s surface does not ' +
     'change what happens when the voice stops');
  doneAt = await page.json('__galaxy.vanish.done');

  /* ================================================================== */
  /* 5. THE GATE NEVER VANISHES                                          */
  /* ================================================================== */
  await page.evaluate('__galaxy.page.render("put the review in the diary", ' +
    JSON.stringify(GATE_ANSWER) + '); __galaxy.speech.speakLine(' +
    JSON.stringify(GATE_ANSWER) + ')');
  await waitFor(page, '__galaxy.voice.draining === false', 60000);
  await page.evaluate('__galaxy.hands.paint(' + JSON.stringify(PROPOSAL) + ')');
  await sleep(300);
  const gateUp = await page.json('({shown: __galaxy.hands.shown, hold: __galaxy.vanish.holdNow,' +
    ' inMs: __galaxy.vanish.inMs, pending: __galaxy.vanish.pending,' +
    ' card: __galaxy.vanish.card, done: __galaxy.vanish.done})');
  ok(gateUp.shown === true && gateUp.card.ask === true,
     'a gate is open on the card: Yes and No are up');
  ok(gateUp.hold === 'a gate is open',
     'and the page names the hold in the employer\'s own words: "' + gateUp.hold + '"');
  const doneBeforeGate = gateUp.done;
  await sleep(room.grace + 2500);
  const gateHeld = await page.json('({card: __galaxy.vanish.card, held: __galaxy.vanish.held,' +
    ' holds: __galaxy.vanish.holds, fired: __galaxy.vanish.fired,' +
    ' done: __galaxy.vanish.done, hold: __galaxy.vanish.holdNow})');
  ok(gateHeld.card.show === true && gateHeld.done === doneBeforeGate,
     'THE GRACE CAME AND WENT AND THE GATE CARD STAYED - ' + (room.grace + 2500) + 'ms after ' +
     'the voice ended, with the question still on the glass',
     JSON.stringify(gateHeld));
  ok(gateHeld.held >= 1 && gateHeld.holds.indexOf('a gate is open') >= 0,
     'refused ' + gateHeld.held + ' time(s), each one recorded with its reason: ' +
     JSON.stringify(gateHeld.holds));
  ok(gateHeld.card.vanishing === false,
     'and it was never even half-faded: a card the employer is being asked to answer must not ' +
     'be at 40% opacity while he reads it');
  await page.evaluate('__galaxy.hands.close()');
  const gateGone = await waitFor(page, '__galaxy.vanish.done > ' + doneBeforeGate,
                                 room.grace + 4000);
  const resolved = await page.json('({why: __galaxy.vanish.why, card: __galaxy.vanish.card})');
  ok(!!gateGone, 'AND WHEN THE GATE IS RESOLVED THE GRACE IS GIVEN: the card left ' + gateGone +
     'ms later, because "' + resolved.why + '"', JSON.stringify(resolved));
  ok(resolved.why === 'the gate resolved',
     'named by the one function every ending comes through - a Yes, a No, a spoken yes or the ' +
     'proposal\'s own timeout all arrive at clearAskUI()');

  /* ================================================================== */
  /* 6. THE HOVER HOLD, which the mandate asked to have named            */
  /* ================================================================== */
  await page.evaluate('__galaxy.page.render("the hover hold", ' +
    JSON.stringify(SHORT_ANSWER) + ')');
  await sleep(500);
  const cardBox = await page.json(
    '(function(){var r=document.getElementById("answer").getBoundingClientRect();' +
    'return {x:Math.round(r.left+r.width/2),y:Math.round(r.top+r.height/2)};})()');
  await page.send('Input.dispatchMouseEvent', { type: 'mouseMoved', x: cardBox.x, y: cardBox.y });
  await sleep(150);
  const hover = await page.json('({hold: __galaxy.vanish.holdNow,' +
    ' HOVER_MS: __galaxy.vanish.HOVER_MS})');
  ok(hover.hold === 'the pointer is on the card',
     'with the pointer on the card the page names THAT hold: "' + hover.hold + '" - and the ' +
     'rule is that a pointer hold RE-ARMS at ' + hover.HOVER_MS + 'ms when the pointer ' +
     'leaves, where a gate hold does not',
     JSON.stringify(hover));
  const held0 = await page.json('__galaxy.vanish.held');
  await page.evaluate('__galaxy.vanish.arm(500, "the harness is testing the hover hold")');
  await sleep(1100);
  const heldHover = await page.json('({held: __galaxy.vanish.held, holds: __galaxy.vanish.holds,' +
    ' card: __galaxy.vanish.card, inMs: __galaxy.vanish.inMs})');
  ok(heldHover.card.show === true && heldHover.held > held0 &&
     heldHover.holds[heldHover.holds.length - 1] === 'the pointer is on the card',
     'a grace that expired under the pointer did not take the paragraph away mid-read, and ' +
     're-armed instead: ' + heldHover.inMs + 'ms on the new clock',
     JSON.stringify(heldHover));
  await page.send('Input.dispatchMouseEvent', { type: 'mouseMoved', x: 8, y: 8 });
  const released = await waitFor(page, '__galaxy.vanish.card.show === false',
                                hover.HOVER_MS + 4000);
  ok(!!released, 'AND THE POINTER LEAVING RELEASED IT: the card went ' + released +
     'ms after the pointer left, on the re-armed ' + hover.HOVER_MS + 'ms clock');

  /* ================================================================== */
  /* 6b. THE RENDER HOLD, which bus_proof named and this measures         */
  /* ================================================================== */
  /* WRITTEN AFTER A STANDING HARNESS WENT RED, which is the only reason this section exists.
     bus_proof read 80/81 on §39's first sweep - "the step list is inside the card's own box"
     with both boxes at 0..0 - because #job-line is a child of #a-text: the Director writes a
     live render's progress INTO the answer card that ordered it, the sentence ordering it ends
     in two seconds, and a ninety-second job was therefore losing its only progress indicator
     four seconds in. The exemption is in vanishHeld(); this measures it.
     AND IT IS DRIVEN THROUGH jobApply(), the funnel every real poll comes through - the same
     door bus_proof uses to hand the page a scripted job rather than wait three minutes for an
     encode. Nothing here is a test double: jobSeen() is what respond() calls when the server
     says a render started, and jobApply() is what the 2.5s poll calls with /jobs' payload. */
  const JOBID = 'a1b2c3d4e5';
  const jobRow = function (outcome, marks) {
    return JSON.stringify({ live: outcome === 'running' ? JOBID : null, busy: outcome === 'running',
      jobs: [{ job: JOBID, topic: 'the render hold', outcome: outcome, steps: [
        { step: 'notes', state: marks[0] }, { step: 'script', state: marks[1] },
        { step: 'voice', state: marks[2] }, { step: 'scenes', state: marks[3] },
        { step: 'encode', state: marks[4] }] }] });
  };
  await page.evaluate('__galaxy.page.render("make me a video about the pricing page", ' +
    JSON.stringify(SHORT_ANSWER) + ')');
  await sleep(400);
  const reads0 = await page.json('__galaxy.job.reads');
  await page.evaluate('__galaxy.job.seen({directJob:"' + JOBID + '"})');
  /* AND THE SCRIPTED ROW GOES IN AFTER THE REAL FETCH HAS LANDED, which cost three reds on the
     first run of this section. jobSeen() ends with jobFetch() - "not at the next tick: the
     steps belong beside the sentence" - so a GET /jobs is already in flight when this line
     runs, and on the first attempt it resolved a few milliseconds AFTER the apply() below and
     overwrote job.state with the server's real payload, which has no row with this id in it.
     The step list read "" for a card that had been handed a running render, which looks exactly
     like the exemption not working. Waiting for the fetch to land first makes the scripted row
     the LAST writer, which is the same position a real poll would be in.
     IT WAITS ON job.reads AND NOT ON job.state, because the page has been polling /jobs on its
     idle cadence since boot - state is long since non-null, and a wait on it would return in
     the same millisecond and prove nothing. reads is the counter jobFetch() bumps, so
     reads > reads0 is the fetch jobSeen() itself started, finished. */
  await waitFor(page, '__galaxy.job.reads > ' + reads0, 8000);
  await sleep(250);
  await page.evaluate('__galaxy.job.apply(' +
    jobRow('running', ['done', 'done', 'running', 'waiting', 'waiting']) + ')');
  await sleep(200);
  const jobUp = await page.json('({line: __galaxy.job.line, inCard: __galaxy.job.inCard,' +
    ' hold: __galaxy.vanish.holdNow, JOB_MS: __galaxy.vanish.JOB_MS,' +
    ' POLL_MS: __galaxy.job.POLL_MS, show: __galaxy.vanish.card.show})');
  ok(jobUp.inCard === true && jobUp.show === true && jobUp.line.length > 0,
     'a render is in flight and its step list is in the card, where §35 puts it: "' +
     jobUp.line + '"', JSON.stringify(jobUp));
  ok(jobUp.hold === 'a render is running',
     'AND THE PAGE NAMES THE RENDER HOLD: "' + jobUp.hold + '" - the exemption bus_proof\'s ' +
     'plate assertion asked for, in the same vocabulary as the gate and the pointer',
     JSON.stringify(jobUp));
  ok(jobUp.JOB_MS === jobUp.POLL_MS,
     'and it re-checks on the BUS\'S OWN CADENCE rather than a number of its own: ' +
     jobUp.JOB_MS + 'ms, which is JOB_POLL_MS - so the re-check lands at most one poll after ' +
     'the row stops reading running');
  const heldJob0 = await page.json('__galaxy.vanish.held');
  const doneJob0 = await page.json('__galaxy.vanish.done');
  await page.evaluate('__galaxy.vanish.arm(300, "the harness is timing the render hold")');
  await sleep(1400);
  const jobHeld = await page.json('({held: __galaxy.vanish.held, holds: __galaxy.vanish.holds,' +
    ' card: __galaxy.vanish.card, inMs: __galaxy.vanish.inMs, line: __galaxy.job.line})');
  ok(jobHeld.card.show === true && jobHeld.card.vanishing === false &&
     jobHeld.held > heldJob0 && jobHeld.line.length > 0 &&
     jobHeld.holds[jobHeld.holds.length - 1] === 'a render is running',
     'THE GRACE CAME AND WENT AND THE RENDER STAYED ON THE GLASS: the step list still reads "' +
     jobHeld.line + '" with ' + jobHeld.inMs + 'ms on the re-armed clock, and the card was ' +
     'never even half-faded while the machine was working',
     JSON.stringify(jobHeld));
  /* AND THEN IT FINISHES, through the same funnel. No `events` on the row, so jobAnnounce()
     has nothing to say and speaks nothing - which keeps this assertion about the hold's
     RELEASE and not about a new utterance's wipe. The real path speaks here, and the sentence
     it speaks arms a grace of its own: that is the comment in THE EXEMPTIONS, not this test. */
  await page.evaluate('__galaxy.job.apply(' +
    jobRow('done', ['done', 'done', 'done', 'done', 'done']) + ')');
  const jobLeft = await waitFor(page, '__galaxy.vanish.done > ' + doneJob0,
                                jobUp.JOB_MS + FADE + 3000);
  const afterJob = await page.json('({why: __galaxy.vanish.why, card: __galaxy.vanish.card,' +
    ' hold: __galaxy.vanish.holdNow, line: __galaxy.job.line})');
  ok(!!jobLeft && afterJob.card.show === false && afterJob.card.rects === 0,
     'AND THE HOLD RELEASED ITSELF WHEN THE RENDER DID: the card left ' + jobLeft +
     'ms after the row stopped reading running, on the re-armed ' + jobUp.JOB_MS +
     'ms clock - a render ends by itself, which is why this hold re-arms where a gate\'s ' +
     'does not', JSON.stringify(afterJob));
  await page.evaluate('__galaxy.job.forget("the harness is done with the scripted render")');

  /* ================================================================== */
  /* 7. THE SIDEBAR'S THREE CLOSES                                       */
  /* ================================================================== */
  await waitFor(page, '__galaxy.nodes.length > 0', 20000);
  const pick = await page.json(
    '(function(){var ns=__galaxy.nodes||[],deg={},' +
    'ls=(__galaxy.strongLinks&&__galaxy.strongLinks.length?__galaxy.strongLinks' +
    ':(__galaxy.allLinks||[])),' +
    'id=function(x){return x&&typeof x==="object"?x.id:x;};' +
    'for(var i=0;i<ls.length;i++){var a=id(ls[i].source),b=id(ls[i].target);' +
    'deg[a]=(deg[a]||0)+1;deg[b]=(deg[b]||0)+1;}' +
    'var best=ns[0],n=best?(deg[best.id]||0):0;' +
    'for(var j=0;j<ns.length;j++){var d=deg[ns[j].id]||0;if(d>n){n=d;best=ns[j];}}' +
    'return {id:best.id,degree:n,of:ns.length};})()');
  note('the note used for the sidebar: degree ' + pick.degree + ' of ' + pick.of + ' notes');

  /* ---- (a) the card that cited it vanished ---- */
  await page.evaluate('__galaxy.page.render("what do the notes say", ' +
    JSON.stringify(SHORT_ANSWER) + ')');
  await sleep(300);
  await page.evaluate('__galaxy.focus(' + JSON.stringify(pick.id) + ',true)');
  await sleep(900);
  const openA = await page.json('({open: __galaxy.sidebar.open, cited: __galaxy.sidebar.cited,' +
    ' opens: __galaxy.sidebar.opens, inMs: __galaxy.sidebar.inMs,' +
    ' closes: __galaxy.sidebar.closes})');
  ok(openA.open === true && openA.cited === true,
     'THE PANEL IS OPEN AND KNOWS IT WAS CITED - it was opened while the answer card was up, ' +
     'which is measured rather than guessed',
     JSON.stringify(openA));
  await page.evaluate('__galaxy.vanish.arm(600, "the harness is retiring the citing card")');
  const closedA = await waitFor(page, '__galaxy.sidebar.open === false', 6000);
  const byA = await page.json('({by: __galaxy.sidebar.by, why: __galaxy.sidebar.why,' +
    ' closes: __galaxy.sidebar.closes, open: __galaxy.sidebar.open})');
  ok(!!closedA && byA.closes === openA.closes + 1,
     'CLOSE (a): the card that cited it vanished and the panel went with it, ' + closedA +
     'ms later - "' + byA.why + '"', JSON.stringify(byA));
  ok(byA.why === 'the card that cited it vanished',
     'and it says so in its own words rather than leaving a harness to infer it');

  /* ---- (c) a new spoken utterance began ---- */
  await page.evaluate('__galaxy.focus(' + JSON.stringify(pick.id) + ',true)');
  await sleep(800);
  const openC = await page.json('({open: __galaxy.sidebar.open, cited: __galaxy.sidebar.cited,' +
    ' closes: __galaxy.sidebar.closes})');
  ok(openC.open === true && openC.cited === false,
     'the panel is open again with NO card on the glass, so this time it is not cited by one',
     JSON.stringify(openC));
  await page.evaluate('__galaxy.speech.speakLine(' + JSON.stringify(NUDGE_LINE) + ')');
  const closedC = await waitFor(page, '__galaxy.sidebar.open === false', 4000);
  const byC = await page.json('({why: __galaxy.sidebar.why, closes: __galaxy.sidebar.closes})');
  ok(!!closedC && byC.why === 'a new utterance began',
     'CLOSE (c): a new spoken utterance closed it in ' + closedC + 'ms - "' + byC.why +
     '". Worth naming: this includes the UNASKED sentences, so a posture nudge spoken into a ' +
     'quiet room closes an open note', JSON.stringify(byC));
  await waitFor(page, '__galaxy.voice.draining === false', 40000);
  await sleep(400);

  /* ---- (b) twenty seconds with nobody in it, and the touch that re-arms ---- */
  await page.evaluate('__galaxy.focus(' + JSON.stringify(pick.id) + ',true)');
  await sleep(700);
  const openB = await page.json('({open: __galaxy.sidebar.open, inMs: __galaxy.sidebar.inMs,' +
    ' armed: __galaxy.sidebar.armed, touches: __galaxy.sidebar.touches,' +
    ' closes: __galaxy.sidebar.closes, IDLE_MS: __galaxy.sidebar.IDLE_MS})');
  ok(openB.open === true && openB.inMs > openB.IDLE_MS - 1500,
     'the idle clock is armed on open with ' + openB.inMs + 'ms of ' + openB.IDLE_MS +
     ' left', JSON.stringify(openB));
  await sleep(7000);
  const mid7 = await page.json('__galaxy.sidebar.inMs');
  const panelMid = await page.json(
    '(function(){var r=document.getElementById("panel").getBoundingClientRect();' +
    'return {x:Math.round(r.left+r.width/2),y:Math.round(r.top+r.height*0.4)};})()');
  await page.send('Input.dispatchMouseEvent',
    { type: 'mouseMoved', x: panelMid.x, y: panelMid.y });
  await sleep(250);
  const touched = await page.json('({inMs: __galaxy.sidebar.inMs,' +
    ' touches: __galaxy.sidebar.touches, hover: __galaxy.sidebar.hover,' +
    ' armed: __galaxy.sidebar.armed})');
  ok(touched.touches > openB.touches && touched.inMs > mid7 + 4000,
     'A HAND IN THE PANEL RE-ARMS IT: ' + mid7 + 'ms left before the pointer moved inside, ' +
     touched.inMs + 'ms after - ' + touched.touches + ' touches counted',
     JSON.stringify({ mid7, touched }));
  /* AND THE POINTER IS TAKEN BACK OUT, because a resting pointer is a HOLD and not a touch:
     the mandate's "no hover or scroll" means the idle close must not fire while a reader's
     hand is still on the panel, and that path is asserted by the hold counter below. */
  await page.send('Input.dispatchMouseEvent', { type: 'mouseMoved', x: 8, y: 8 });
  await sleep(200);
  const closedB = await waitFor(page, '__galaxy.sidebar.open === false', openB.IDLE_MS + 9000);
  const byB = await page.json('({why: __galaxy.sidebar.why, closes: __galaxy.sidebar.closes,' +
    ' holds: __galaxy.sidebar.holds, armed: __galaxy.sidebar.armed, by: __galaxy.sidebar.by})');
  ok(!!closedB && /nothing touched it for/.test(byB.why),
     'CLOSE (b): ' + Math.round(openB.IDLE_MS / 1000) + 's with nobody in it and it closed ' +
     'itself - "' + byB.why + '" (' + closedB + 'ms after the pointer left)',
     JSON.stringify(byB));
  note('the three closes, in the panel\'s own words: ' + JSON.stringify(byB.by));

  /* ================================================================== */
  /* 8. THE GLASS BODY                                                   */
  /* ================================================================== */
  /* THE SKY BEHIND THE PANEL IS SAMPLED FIRST, with the panel closed, because the contrast
     arithmetic below composites the glass over a REAL backdrop and the real backdrop is
     whatever galaxy happens to be behind the right-hand rail. */
  await page.evaluate('__galaxy.page.render("the glass body", ' +
    JSON.stringify(SHORT_ANSWER) + ')');
  await sleep(500);
  await page.evaluate('__galaxy.focus(' + JSON.stringify(pick.id) + ',true)');
  await sleep(1000);
  const geo = await page.json(
    '(function(){var p=document.getElementById("panel"),c=document.getElementById("answer");' +
    'var pr=p.getBoundingClientRect(),cr=c.getBoundingClientRect(),cs=getComputedStyle(p);' +
    'return {panel:{x:Math.round(pr.left),y:Math.round(pr.top),w:Math.round(pr.width),' +
    ' h:Math.round(pr.height),right:Math.round(pr.right)},' +
    ' card:{right:Math.round(cr.right)}, vw:innerWidth, vh:innerHeight,' +
    ' transition:cs.transitionProperty, dur:cs.transitionDuration,' +
    ' radius:cs.borderTopLeftRadius, pad:cs.padding, z:cs.zIndex,' +
    ' spring:getComputedStyle(document.documentElement).getPropertyValue("--spring-ms").trim()};})()');
  note('the panel: ' + geo.panel.w + 'x' + geo.panel.h + ' at x=' + geo.panel.x +
       ', right edge ' + geo.panel.right + ' of ' + geo.vw + ' · transition ' +
       geo.transition + ' ' + geo.dur + ' · radius ' + geo.radius);
  const glass = await page.json('__galaxy.sidebar.glass');
  /* THE INKS ARE READ NOW, WITH BOTH SURFACES UP. The card is wiped further down to clear the
     rail for the plates, and getComputedStyle on a paragraph inside a hidden card is a reading
     of a colour nobody is looking at. Both comparisons below want the colours as the employer
     had them. */
  const ink = await page.json('__galaxy.sidebar.ink');
  const extra = await page.json(
    '(function(){var q=document.getElementById("a-q");' +
    'var ch=document.querySelector("#panel .chips span, #panel .chips button, #panel .chip");' +
    'var g=function(e){return e?getComputedStyle(e).color:null;};' +
    'return {cardMuted:g(q), panelChip:g(ch)};})()');
  ok(!!(ink && ink.panelBody && ink.cardAnswer),
     'both inks are readable off the live elements: the panel\'s body and the card\'s answer',
     JSON.stringify(ink));
  ok(glass.panel.background === glass.card.background,
     'THE SAME TRANSLUCENT BACKGROUND AS THE ANSWER CARD, measured on both live elements: ' +
     glass.panel.background,
     JSON.stringify({ panel: glass.panel.background, card: glass.card.background }));
  const tok = parseColour(glass.token.glass), pan = parseColour(glass.panel.background);
  ok(!!tok && !!pan && tok.a === pan.a &&
     tok.rgb.every((v, i) => v === pan.rgb[i]),
     'AND THE ALPHA WAS READ FROM THE CARD\'S OWN TOKEN RATHER THAN INVENTED: --glass is ' +
     glass.token.glass + ' and the panel is painting alpha ' + (pan && pan.a),
     JSON.stringify({ token: glass.token.glass, panel: glass.panel.background }));
  ok(glass.panel.backdrop === glass.card.backdrop && /blur/.test(glass.panel.backdrop),
     'the same backdrop-blur as the card, on both live elements: ' + glass.panel.backdrop,
     JSON.stringify({ panel: glass.panel.backdrop, card: glass.card.backdrop,
                      token: glass.token.blur }));
  /* A HAIRLINE IS COMPARED WITH THE HOUSE'S OTHER HAIRLINE, not with the string "1px". Chrome
     snaps border widths to whole DEVICE pixels, so a declared 1px reads back as 0.666667px at
     this monitor's ratio of 1.5 - which is a correct hairline reported in CSS pixels and not a
     thin border. What can be asserted is that it is ONE DEVICE PIXEL of var(--line), that it
     is no thicker than a CSS pixel, and that it is the same width the card's own rim is drawn
     at. See the first run of this file, where '1px solid' failed on a 1px declaration. */
  const bPanel = parseFloat(glass.panel.borderLeft) || 0;
  const bCard = parseFloat(glass.card.border || glass.card.borderLeft) || 0;
  const devPx = r2(bPanel * room.dpr);
  ok(bPanel > 0 && bPanel <= 1 && devPx === 1,
     'A 1px HAIRLINE down its leading edge, and exactly one device pixel of it: ' +
     glass.panel.borderLeft + ' at dpr ' + room.dpr + ' = ' + devPx + ' device px',
     JSON.stringify({ panel: glass.panel.borderLeft, dpr: room.dpr, devPx }));
  ok(Math.abs(bPanel - bCard) < 0.01 &&
     parseColour(glass.panel.borderLeft).a === parseColour(glass.token.line).a,
     'and it is the house hairline rather than one of its own: the same width the card is ' +
     'rimmed at (' + bCard + 'px) in the --line token\'s own alpha, ' + glass.token.line,
     JSON.stringify({ panel: glass.panel.borderLeft, card: glass.card.borderLeft,
                      token: glass.token.line }));
  ok(glass.panel.shadow === 'none' || glass.panel.shadow.indexOf('inset') < 0,
     'and NO INNER GLOW: box-shadow is "' + glass.panel.shadow + '" - nothing inset, so the ' +
     'panel is a pane of the same glass rather than a lit slab');
  ok(geo.panel.right === geo.vw && geo.panel.y === 0 && geo.panel.h === geo.vh,
     'GEOMETRY UNCHANGED: still the full-height rail on the right edge, ' + geo.panel.w +
     'px wide, radius ' + geo.radius + ', padding ' + geo.pad,
     JSON.stringify(geo.panel));
  ok(geo.transition === 'transform' &&
     Math.abs(parseFloat(geo.dur) - parseFloat(geo.spring)) < 0.001,
     'and the open/close animation is untouched: transform only, ' + geo.dur + ' (--spring-ms ' +
     geo.spring + ') - the material changed, nothing animates that did not before',
     JSON.stringify({ transition: geo.transition, dur: geo.dur, spring: geo.spring }));

  /* ---- the ink, over a backdrop that was measured ---- */
  /* THE BAND IS THE PANEL'S OWN EMPTY FOOT, found rather than chosen. A clip over the panel's
     content would have text in it, and TEXT HAS COLUMN SPREAD: an opaque slab with a paragraph
     on it would pass a "there is structure inside the panel" test on the strength of its own
     letters. So the measurement is taken below the last child, where there is nothing but
     glass and whatever is behind it, and if that band is too short to measure the two
     assertions below say so instead of passing. */
  const band = await page.json(
    '(function(){var p=document.getElementById("panel"),b=document.querySelector("#panel .body");' +
    'var pr=p.getBoundingClientRect();' +
    'var kids=b?b.children:[],low=b?b.getBoundingClientRect().top:pr.top;' +
    'for(var i=0;i<kids.length;i++){var r=kids[i].getBoundingClientRect();' +
    ' if(r.height>0&&r.bottom>low)low=r.bottom;}' +
    'var top=Math.ceil(low+12),bot=Math.floor(pr.bottom-14);' +
    'return {x:Math.round(pr.left+12),y:top,w:Math.round(pr.width-24),h:bot-top,' +
    ' lastChildBottom:Math.round(low)};})()');
  const CLIP_SKY = band.h >= 50
    ? { x: band.x, y: band.y, w: band.w, h: Math.min(band.h, 320) }
    : { x: geo.panel.x + 12, y: Math.round(geo.vh * 0.62), w: geo.panel.w - 24, h: 220 };
  if (band.h >= 50) {
    note('the text-free band inside the panel: ' + CLIP_SKY.w + 'x' + CLIP_SKY.h + ' at y=' +
         CLIP_SKY.y + ', starting ' + (CLIP_SKY.y - band.lastChildBottom) +
         'px below the last thing written in it');
  } else {
    note('the panel\'s content reaches its foot (band ' + band.h + 'px), so the lower rail is ' +
         'used instead and some of the spread below may be the panel\'s own text');
  }
  /* THE SKY IN THAT EXACT BAND, with the panel closed: this is the backdrop the contrast
     arithmetic composites the glass over, and it is a measurement rather than an assumed black. */
  await page.evaluate('__galaxy.vanish.now(true)');
  /* THE PANEL IS HIDDEN, NOT CLOSED, for the reason spelled out at the plates below: closing it
     clears the selection, which takes the dimming off the whole galaxy, and the backdrop this
     arithmetic needs is the sky that is ACTUALLY behind the open panel. */
  await page.evaluate('document.getElementById("panel").style.visibility = "hidden", "hidden"');
  await settleSky(page);
  await sleep(500);
  const skyB64 = await page.shot(join(OUT, 'kara-rail-sky.png'), CLIP_SKY);
  await page.evaluate('document.getElementById("panel").style.visibility = "", "shown"');
  await park(page);
  await page.evaluate('__kp.put("skyRail", "' + skyB64 + '")');
  const skyMean = await page.json('__kp.mean("skyRail")');
  const skySpread = await page.json('__kp.spread("skyRail")');
  note('the bare sky in that band: mean luminance ' + skyMean.lum + ' · column spread median ' +
       skySpread.median + ' (' + skySpread.flat + ' of ' + skySpread.cols + ' columns flat)');
  const back = [skyMean.r, skyMean.g, skyMean.b];
  const onGlass = over(parseColour(glass.panel.background), back);
  const rPanel = ratio(parseColour(ink.panelBody.color).rgb, onGlass);
  const rCard = ratio(parseColour(ink.cardAnswer.color).rgb, onGlass);
  const rMeta = ink.panelMeta ? ratio(parseColour(ink.panelMeta.color).rgb, onGlass) : null;
  const rCardMuted = extra.cardMuted ? ratio(parseColour(extra.cardMuted).rgb, onGlass) : null;
  note('the glass over that sky composites to rgb(' +
       onGlass.map((v) => Math.round(v)).join(',') + ')');
  note('CONTRAST, computed here from the colours the page is painting:');
  note('  panel body   ' + ink.panelBody.color + ' at ' + ink.panelBody.size + '  ' +
       rPanel + ':1');
  note('  card answer  ' + ink.cardAnswer.color + ' at ' + ink.cardAnswer.size + '  ' +
       rCard + ':1');
  if (rMeta != null) note('  panel meta   ' + ink.panelMeta.color + '  ' + rMeta + ':1' +
    (rCardMuted != null ? '   (the card\'s own muted ink: ' + rCardMuted + ':1)' : ''));
  ok(rPanel >= rCard,
     'TEXT ON GLASS AT OR ABOVE THE CARD\'S MEASURED VALUE: the panel\'s body reads ' + rPanel +
     ':1 against the card\'s ' + rCard + ':1 over the same measured backdrop',
     JSON.stringify({ panel: rPanel, card: rCard, ink, back }));
  if (rMeta != null && rCardMuted != null) {
    ok(rMeta >= rCardMuted - 0.01,
       'and the secondary ink keeps its own comparison too: the panel\'s meta rows read ' +
       rMeta + ':1 against the card\'s muted ink at ' + rCardMuted + ':1 - both are ' +
       'var(--muted), which is why they agree',
       JSON.stringify({ meta: rMeta, cardMuted: rCardMuted }));
  }
  ok(rPanel >= 4.5,
     'and it clears the AA floor for body text on its own: ' + rPanel + ':1 against 4.5:1');

  /* ---- the two plates: stars and haze THROUGH the panel ----
     TWO CAMERAS, ONE PANEL, AND THE SAME NOTE IN IT. The second plate flies the camera with
     focusNode(n, false) - a flight without a selection - so the panel is not reopened and not
     repainted: its geometry, its text and its ink are IDENTICAL in the two frames. Anything
     that differs between them therefore came through the glass. That is the assertion an
     opaque slab cannot pass, and a spread measurement alone could be passed by a slab with a
     paragraph on it. */
  const far = await page.json(
    '(function(){var ns=__galaxy.nodes||[],b=null;' +
    'for(var i=0;i<ns.length;i++) if(ns[i].id===' + JSON.stringify(pick.id) + ') b=ns[i];' +
    'var best=null,d=-1;' +
    'for(var j=0;j<ns.length;j++){var n=ns[j];' +
    ' if(!n||n.x===undefined||!b||b.x===undefined) continue;' +
    ' var k=Math.hypot(n.x-b.x,n.y-b.y,n.z-b.z); if(k>d){d=k;best=n;}}' +
    'return best?{id:best.id,dist:Math.round(d)}:null;})()');
  /* AND THE SKY IS SAMPLED AT EACH POSITION, by closing the panel without moving the camera.
     That pairing is the measurement: at one camera position, the same rectangle with and
     without the glass over it. A per-pixel comparison of those two would find almost nothing -
     a 12px blur destroys a star as a point - so the comparison is made on a coarse grid, where
     a blur keeps everything: the haze, the rim, the empty quarters. */
  const SLAB = slabLum(parseColour(glass.panel.background).rgb);
  const ALPHA = parseColour(glass.panel.background).a;   // read off the live panel, not named
  const GRID = [6, 8];
  const plates = [];
  for (const spot of [{ where: 'dense-field', id: pick.id },
                      { where: 'far-side', id: far && far.id }]) {
    if (spot.id == null) { note('no second node to fly to; one plate only'); continue; }
    await page.evaluate('__galaxy.focus(' + JSON.stringify(spot.id) + ',true)');
    await waitFor(page, '__galaxy.sidebar.open === true', 5000);
    await sleep(2600);                     // the 1700ms flight, and then the sky settling
    /* THE BAND IS RE-MEASURED HERE, because this panel holds a different note and a text-free
       band is only text-free for the words that are actually in it. */
    const b = await page.json(
      '(function(){var p=document.getElementById("panel"),' +
      'bd=document.querySelector("#panel .body");var pr=p.getBoundingClientRect();' +
      'var kids=bd?bd.children:[],low=bd?bd.getBoundingClientRect().top:pr.top;' +
      'for(var i=0;i<kids.length;i++){var r=kids[i].getBoundingClientRect();' +
      ' if(r.height>0&&r.bottom>low)low=r.bottom;}' +
      'var top=Math.ceil(low+12),bot=Math.floor(pr.bottom-14);' +
      'return {x:Math.round(pr.left+12),y:top,w:Math.round(pr.width-24),h:bot-top};})()');
    const clip = { x: b.x, y: b.y, w: b.w, h: Math.min(Math.max(b.h, 0), 320) };
    const thin = clip.h < 50;
    /* The pair below is a comparison of two frames of the same sky, so the camera has to be
       done easing before the first of them - see settleSky(). */
    const stillHere = await settleSky(page);
    const file = join(OUT, 'kara-sidebar-' + spot.where + '.png');
    await page.shot(file, { x: Math.max(0, geo.panel.x - 200), y: 0,
                            w: Math.min(geo.vw, geo.panel.w + 200), h: geo.vh, scale: 2 });
    await page.evaluate('__kp.put("g-' + spot.where + '", "' +
      (await page.shot(null, clip)) + '")');
    /* AND NOW THE SAME RECTANGLE WITHOUT THE GLASS - BY HIDING THE PANEL, NOT BY CLOSING IT.
       This is the fix for three reds and it was a real measurement error, not a threshold.
       sidebar.close() goes through clearSelection(), which drops the selection, and a deck with
       nothing selected DOES NOT DIM THE REST OF THE GALAXY: hiNodes.clear() + refresh() takes
       the highlight off and every other node back to full brightness. So the "bare sky" frame
       was a BRIGHTER SKY than the one the glass was actually standing in front of, and the
       panel then read darker than a 60%-alpha composite over it could possibly be - 15.62
       measured against 20.20 predicted, which reads exactly like an opaque slab and was in
       fact an un-dimmed backdrop. visibility:hidden takes the panel's paint and its
       backdrop-filter away and touches NOTHING else: same camera, same selection, same
       highlight, same dimming, and no transition, because the panel animates transform only. */
    await page.evaluate(
      'document.getElementById("panel").style.visibility = "hidden", "hidden"');
    await sleep(160);
    await page.evaluate('__kp.put("s-' + spot.where + '", "' +
      (await page.shot(null, clip)) + '")');
    await page.evaluate('document.getElementById("panel").style.visibility = "", "shown"');
    await park(page);
    const g = { sp: await page.json('__kp.spread("g-' + spot.where + '")'),
                mn: await page.json('__kp.mean("g-' + spot.where + '")'),
                cells: await page.json('__kp.cells("g-' + spot.where + '",' + GRID + ')') };
    const s = { sp: await page.json('__kp.spread("s-' + spot.where + '")'),
                mn: await page.json('__kp.mean("s-' + spot.where + '")'),
                cells: await page.json('__kp.cells("s-' + spot.where + '",' + GRID + ')') };
    const r = correlate(s.cells, g.cells);
    plates.push({ where: spot.where, file, clip, thin, g, s, r });
    note('plate ' + spot.where + ': the camera settled in ' + stillHere.ms + 'ms before the pair');
    note('plate ' + spot.where + ': bare sky luminance ' + s.mn.lum + ' → through the glass ' +
         g.mn.lum + ' (an opaque slab would read ' + SLAB + ') · ' + GRID[0] + 'x' + GRID[1] +
         ' grid correlation r=' + r + ' · column spread ' + s.sp.median + ' → ' + g.sp.median);
  }
  for (const p of plates) {
    /* WHAT A 60% ALPHA PREDICTS, as a number this harness can check rather than trust.
       __kp.mean() is the luminance of the MEAN CHANNELS, which makes it linear in the pixels -
       so a blur, which preserves a mean, passes straight through it, and the saturate(150%)
       leg preserves it exactly because feColorMatrix's saturate matrix is built on these same
       three coefficients. The composite is therefore arithmetic: 0.6 of the panel's own colour
       plus 0.4 of the sky measured behind it. An opaque slab lands on SLAB; a pane of glass
       lands here; and the tolerance is deliberately narrower than the distance between them. */
    const pred = r2(ALPHA * SLAB + (1 - ALPHA) * p.s.mn.lum);
    const tol = Math.max(2, 0.18 * pred);
    const dark = p.s.mn.lum <= SLAB + 2;
    note('plate ' + p.where + ': ' + ALPHA + ' x ' + SLAB + ' + ' + r2(1 - ALPHA) + ' x ' +
         p.s.mn.lum + ' = ' + pred + ' predicted · ' + p.g.mn.lum + ' measured · ' +
         r2(Math.abs(p.g.mn.lum - pred)) + ' apart, tolerance ' + r2(tol) +
         ' (an opaque slab would be ' + r2(Math.abs(SLAB - pred)) + ' away)');
    ok(!p.thin && Math.abs(p.g.mn.lum - pred) <= tol,
       'THE GLASS IS THE COMPOSITE ITS OWN ALPHA PREDICTS (' + p.where + '): a text-free band ' +
       'inside the panel reads ' + p.g.mn.lum + ' where ' + ALPHA + ' of the panel colour over ' +
       (1 - ALPHA) + ' of the sky measured behind it comes to ' + pred +
       ' - and an opaque slab of the same colour would read ' + SLAB,
       JSON.stringify({ sky: p.s.mn.lum, glass: p.g.mn.lum, pred, slab: SLAB, tol: r2(tol),
                        thin: p.thin }));
    if (dark) {
      note('and the sky in this band is itself darker than the panel\'s own colour (' +
           p.s.mn.lum + ' against ' + SLAB + '), so the glass is correctly BRIGHTER than what ' +
           'is behind it here - the deck\'s empty quarter, where 60% of a dark grey is the ' +
           'brightest thing in the rectangle');
    } else {
      ok(p.g.mn.lum > SLAB + 0.3 && p.g.mn.lum < p.s.mn.lum,
         'AND IT DIMS THAT SKY RATHER THAN REPLACING IT (' + p.where + '): ' + p.g.mn.lum +
         ' sits above the ' + SLAB + ' the same colour would read at alpha 1 and below the ' +
         p.s.mn.lum + ' of the sky it is standing in front of',
         JSON.stringify({ sky: p.s.mn.lum, glass: p.g.mn.lum, slab: SLAB }));
    }
    ok(p.r != null && p.r > 0.5,
       'AND WHAT SHOWS THROUGH IS THAT SKY AND NOT A TEXTURE OF ITS OWN (' + p.where + '): the ' +
       GRID[0] + 'x' + GRID[1] + ' luminance grid through the glass correlates with the grid of ' +
       'the bare sky behind it at r=' + p.r + ' - the panel is bright exactly where the galaxy ' +
       'behind it is bright. An opaque slab\'s grid is flat and correlates with nothing',
       JSON.stringify({ r: p.r, sky: p.s.cells, glass: p.g.cells }));
    ok(p.g.sp.median > FLAT_TOL && p.g.sp.flat < p.g.sp.cols * 0.25,
       'and there is structure in it to see (' + p.where + '): the median column inside the ' +
       'panel has a luminance spread of ' + p.g.sp.median + ' against a flat-band tolerance of ' +
       FLAT_TOL + ', with ' + p.g.sp.flat + ' of ' + p.g.sp.cols + ' columns flat',
       JSON.stringify(p.g.sp));
  }
  if (plates.length === 2) {
    /* THE CONTROL FOR THE CORRELATION, reported rather than asserted because its own premise -
       that two camera positions put GENUINELY different skies behind the rail - is a fact about
       the deck's layout and not something this file gets to require. If the panel had a
       luminance texture of its own (a gradient, an inner glow, a slab's falloff) it would
       correlate about as well with ANY sky as with the one behind it; these two numbers are
       what that would look like. */
    const cross = [correlate(plates[1].s.cells, plates[0].g.cells),
                   correlate(plates[0].s.cells, plates[1].g.cells)];
    note('CONTROL: each panel against the OTHER position\'s sky - r=' + cross[0] + ' and r=' +
         cross[1] + ', against r=' + plates[0].r + ' and r=' + plates[1].r + ' for the sky each ' +
         'was actually standing in front of');
    const dim = plates[0].s.mn.lum >= plates[1].s.mn.lum ? plates : plates.slice().reverse();
    ok(dim[0].g.mn.lum > dim[1].g.mn.lum,
       'TWO CAMERA POSITIONS AND THE PANEL FOLLOWS THE SKY: the brighter backdrop (' +
       dim[0].where + ', ' + dim[0].s.mn.lum + ') gives the brighter glass (' + dim[0].g.mn.lum +
       ') and the dimmer one (' + dim[1].where + ', ' + dim[1].s.mn.lum + ') the dimmer glass (' +
       dim[1].g.mn.lum + ')',
       JSON.stringify(plates.map((p) => [p.where, p.s.mn.lum, p.g.mn.lum])));
    note('the plate to read for the core\'s haze through the glass is ' + dim[0].where +
         '; ' + dim[1].where + ' is the deck\'s empty quarter, where there is genuinely less ' +
         'to see through it - which is itself the point');
  }
  await page.evaluate('__galaxy.sidebar.close("the harness is done with the panel")');

  /* ================================================================== */
  /* 9. THE MUTED TAB                                                    */
  /* ================================================================== */
  /* A SECOND TAB OF ITS OWN, because MUTED is read off the query string at load: a muted path
     cannot be tested by muting a tab that has already decided it can speak. It is LAST on
     purpose - a second tab takes the foreground, and everything above needed this one awake. */
  const MURL = GALAXY + '/?mute=1';
  let mpage = null;
  try {
    const made = await cdp('/json/new?url=' + encodeURIComponent(MURL), 'PUT');
    const url = made && made.webSocketDebuggerUrl;
    if (url) { mpage = new Page(url); await mpage.open(); }
    note('the second tab opened at ' + ((made && made.url) || '?'));
  } catch (e) { note('could not open a second tab: ' + e.message); }
  if (!mpage) {
    note('THE MUTED SECTION IS NOT RUN: this Chrome would not open a second tab over /json/new. ' +
         'Reported rather than passed.');
  } else {
    await mpage.send('Runtime.enable');
    await mpage.send('Page.enable');
    /* NAVIGATED EXPLICITLY, because /json/new's url parameter is not honoured by every build -
       the first run of this file got a tab that was never pointed at anything and a
       ReferenceError for __galaxy, which is the correct reading of a blank page and tells you
       nothing about the muted path. Navigating twice to the same URL costs a reload and
       removes the ambiguity. */
    try { await mpage.send('Page.navigate', { url: MURL }); } catch (e) { note('navigate: ' + e.message); }
    const mup = await waitFor(mpage, '!!(window.__galaxy && __galaxy.vanish)', 45000);
    const mwhere = await mpage.evaluate('location.href').catch(() => '?');
    ok(!!mup,
       'a second tab is up at ?mute=1 (' + mwhere + ') - the muted path cannot be tested in a ' +
       'tab that has already decided it can speak');
    if (!mup) {
      note('THE MUTED SECTION STOPS HERE: the second tab never finished booting, so everything ' +
           'below it would be a reading of a blank page. Reported rather than passed.');
      mpage.close(); mpage = null;
    }
  }
  if (mpage) {
    const mroom = await mpage.json('({muted: __galaxy.speech.muted,' +
      ' off: __galaxy.vanish.off, perWord: __galaxy.vanish.READ_SECS_PER_WORD,' +
      ' min: __galaxy.vanish.READ_MIN_MS, grace: __galaxy.vanish.GRACE_MS})');
    ok(mroom.muted === true && mroom.off === false,
       'it knows it is muted and the vanish is still live in it', JSON.stringify(mroom));
    /* The same increment discipline as the main tab: this tab has already put a boot card up
       and taken it away, so `done > 0` would be satisfied by a card that left a minute ago. */
    const mdoneAt = await mpage.json('__galaxy.vanish.done');
    const mres = await mpage.json(
      '(function(){var t=' + JSON.stringify(MUTED_ANSWER) + ';' +
      ' __galaxy.page.render("the quiet tab", t);' +
      ' __galaxy.speech.speakLine(t);' +
      ' return {where:__galaxy.kara.where, why:__galaxy.kara.why,' +
      '  seen:__galaxy.kara.seen, arms:__galaxy.kara.arms,' +
      '  text:document.getElementById("a-text").textContent,' +
      '  inMs:__galaxy.vanish.inMs, vwhy:__galaxy.vanish.why,' +
      '  words:t.split(/\\s+/).filter(Boolean).length};})()');
    const wantMs = Math.max(mroom.min, Math.round(mres.words * mroom.perWord * 1000)) +
                   mroom.grace;
    ok(mres.arms === 0 && mres.seen.spans === 0 && mres.where === '',
       'FULL TEXT INSTANTLY: no reveal was armed at all in a tab with no voice, so there are ' +
       'no spans and nothing is hidden - which is what the paragraph did before §39 existed',
       JSON.stringify(mres.seen) + ' · ' + mres.why);
    ok(mres.text.replace(/\s+/g, ' ').trim() === MUTED_ANSWER.replace(/\s+/g, ' ').trim(),
       'and the whole sentence is on the glass, character for character');
    ok(mres.inMs > 0 && Math.abs(mres.inMs - wantMs) < 900,
       'THE MUTED VANISH IS ARMED ON AN ESTIMATED READ instead of an ending: ' + mres.inMs +
       'ms against ' + mres.words + ' words x ' + mroom.perWord + 's + ' + mroom.grace +
       'ms grace = ' + wantMs + 'ms - because "' + mres.vwhy + '"',
       JSON.stringify({ got: mres.inMs, want: wantMs, words: mres.words }));
    const mbefore = await mpage.json('__galaxy.vanish.record');
    const mleft = await waitFor(mpage, '__galaxy.vanish.done > ' + mdoneAt, wantMs + 6000);
    const mafter = await mpage.json('({card: __galaxy.vanish.card,' +
      ' record: __galaxy.vanish.record})');
    ok(!!mleft && mafter.card.className === '' && mafter.card.rects === 0,
       'and the quiet card left on its own after the read-time, leaving the sky',
       JSON.stringify(mafter.card));
    ok(mafter.record.chunks === mbefore.chunks && mafter.record.ids === mbefore.ids &&
       mafter.record.spoke === mbefore.spoke && mafter.record.ledger === mbefore.ledger,
       'display-only there too: the muted tab\'s chunk log, line ids, spoken count and ledger ' +
       'rows are untouched',
       JSON.stringify({ before: mbefore, after: mafter.record }));
    /* AND NAMED RATHER THAN ASSERTED, because it is not a record: the page's six-second echo
       window is what the first run of this file mistook for a transcript, and it reads 2
       before a muted grace and 0 after one for the ordinary reason that 8.5 seconds is longer
       than six. Nothing was taken away; the window had simply expired. */
    note('the echo window either side, for the avoidance of exactly one doubt: ' +
         (await mpage.evaluate('__galaxy.vanish.echo')) + ' now, and SAID_TTL_MS is 6000 - a ' +
         'rolling six seconds of what was just said, not a transcript');
    mpage.close();
  }

  note('the plates for the boss: ' + OUT + '/kara-mid-reveal.png · kara-sky-post.png · ' +
       'kara-sidebar-boot.png · kara-sidebar-cluster.png (and kara-sky-pre.png, the baseline)');
  note('the window had to be un-minimised ' + keeper.count() + ' time(s) in this run');
  keeper.stop();
  page.close();
}

main().catch((e) => { bad.push('the run itself: ' + e.message); console.log('\n  ERROR ' + e.message); })
  .finally(async () => {
    procs.forEach((p) => { try { process.kill(p.pid); } catch { } });
    profiles.forEach((p) => shutChrome(p));
    await sleep(700);
    profiles.forEach((p) => { try { rmSync(p, { recursive: true, force: true }); } catch { } });
    console.log('\n  VERIFY ' + (checks - bad.length) + '/' + checks +
                (bad.length ? ' FAIL' : ' PASS') + '\n');
    bad.forEach((b) => console.log('    FAILED: ' + b));
    process.exit(bad.length ? 1 : 0);
  });
