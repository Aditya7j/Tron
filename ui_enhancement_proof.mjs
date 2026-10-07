/* UI ENHANCEMENT PROOF - the duotone, the orbit map, the motion vocabulary, the face's mesh.
 *
 * WHAT THE MANDATE ASKED THIS FILE TO HOLD, and each is held two ways where it can be - once
 * off the SOURCE and once off the RUNNING PAGE - because the two fail differently: a token can
 * be declared and never reach a rule, and a rule can resolve to a colour nobody declared.
 *
 *   1. THE PALETTE. The duotone's custom properties exist at :root and resolve to the new
 *      palette in the browser; the -rgb triplets resolve to exactly their masters; the old names
 *      (--accent, --live, --local, --web, --doc) are members of the two families now and still
 *      compute to the same values; active states take gold and structure takes blue, read off
 *      the CSSOM and off one live element; and NO NEW HUE was written outside the token block -
 *      the distinct coloured literals outside :root are a subset of what the pre-mandate
 *      stylesheet already had.
 *   2. THE GALAXY VIEW. The orbit map draws the house's ACTUAL clusters: the names and counts on
 *      the glass equal the ones counted HERE, in Node, from viewer/graph-data.js - the corpus on
 *      disk, read by a different program - and the module's source carries none of those names
 *      as a literal, so the agreement cannot be a coincidence of hardcoding.
 *   3. THE MOTION. The named easings exist, the stylesheet carries no cubic-bezier outside the
 *      block that names them, every one of the four the mandate names is REFERENCED (by a rule
 *      or by the script's EASE reader), and what the browser computes for a panel and a caption
 *      is the named curve.
 *   4. THE FACE. Its mesh stratum is laid inside the one allocation, at the cap, and the deck
 *      goes back to wearing its rich mode afterwards (the DUST since UI mandate II).
 *   6. UI MANDATE II - THE LAYOUT AND THE PRESENCE SYSTEM. The sidebar renders and every row
 *      reaches a section the house really has (the mapping is written out beside the check);
 *      the header carries numbers the SERVER computed; the galaxy fills the main pane off the
 *      live groups; the right column names the persona the server serves and shows a real
 *      answer's real notes; the dust has its four states in the four tokens; ring, cube and
 *      core are gone; the face's topology is measured against PR #4's lattice; the presence is
 *      centred at a stated ratio of the pane; and the galaxy-to-presence turn fires off the
 *      real ear, opened by a real click on the real microphone button.
 *
 * BASE_REV is the commit this mandate started from. It is named rather than read as HEAD
 * because once this round is committed HEAD IS the new stylesheet, and "no new hue since HEAD"
 * would compare the file with itself.
 *
 * Port 9246, its own throwaway profile, closed by profile and by port and never by title.
 */
import { spawn, spawnSync } from 'node:child_process';
import { mkdtempSync, existsSync, readFileSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { basename, join } from 'node:path';

const GALAXY = 'http://127.0.0.1:4700';
const PORT = 9246;
const CDP = 'http://127.0.0.1:' + PORT;
const BASE_REV = 'e08ed4f';
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

let pass = 0, fail = 0;
const failures = [];
const say = (s) => console.log(s);
function ok(cond, claim, evidence) {
  if (cond) { pass++; say('  ok   ' + claim); } else {
    fail++; failures.push(claim); say('  FAIL ' + claim);
    if (evidence) say('         ' + String(evidence).slice(0, 600));
  }
}
const note = (s) => say('  note ' + s);
const step = (s) => say('\n  \u00b7\u00b7 ' + s);

/* ------------------------------------------------------------------ the source, in Node */
const NOW = readFileSync('viewer/index.html', 'utf8');
const git = spawnSync('git', ['show', BASE_REV + ':viewer/index.html'], { encoding: 'utf8', maxBuffer: 64 << 20 });
const BASE = git.status === 0 ? git.stdout : '';

function stylesheet(html) {
  const m = /<style>([\s\S]*?)<\/style>/.exec(html);
  return m ? m[1] : '';
}
function uncomment(css) { return css.replace(/\/\*[\s\S]*?\*\//g, ''); }
/* The first :root block, by brace counting - the token block is the one with every name in it. */
function splitRoot(css) {
  const at = css.indexOf(':root{');
  if (at < 0) return { root: '', rest: css };
  let depth = 0, i = css.indexOf('{', at);
  for (; i < css.length; i++) {
    if (css[i] === '{') depth++;
    else if (css[i] === '}') { depth--; if (depth === 0) break; }
  }
  return { root: css.slice(at, i + 1), rest: css.slice(0, at) + css.slice(i + 1) };
}
/* A COLOURED literal: a hex or rgb()/rgba() with numeric channels whose spread is over 8 - so
   white, black and the near-greys of the floor are neutrals and not hues. */
function hues(css) {
  const out = [];
  const re = /#([0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b|rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)/g;
  let m;
  while ((m = re.exec(css))) {
    let r, g, b;
    if (m[1]) {
      let h = m[1];
      if (h.length === 3) h = h.split('').map((c) => c + c).join('');
      r = parseInt(h.slice(0, 2), 16); g = parseInt(h.slice(2, 4), 16); b = parseInt(h.slice(4, 6), 16);
    } else { r = +m[2]; g = +m[3]; b = +m[4]; }
    if (Math.max(r, g, b) - Math.min(r, g, b) > 8) out.push(r + ',' + g + ',' + b);
  }
  return out;
}

say('\n  UI ENHANCEMENT PROOF');
say('  ' + '-'.repeat(74));

step('1 · the palette, off the source');
const cssNow = uncomment(stylesheet(NOW)), cssBase = uncomment(stylesheet(BASE));
const rootNow = splitRoot(cssNow);
const TOKENS = ['--gold-core', '--gold-core-rgb', '--gold-hot', '--gold-glow', '--gold-dim',
  '--gold-trace', '--gold-local', '--blue-structure', '--blue-structure-rgb', '--blue-glow',
  '--blue-dim', '--blue-trace', '--blue-deep', '--blue-live', '--duo-ribbon'];
const missing = TOKENS.filter((k) => !new RegExp(k.replace(/-/g, '\\-') + '\\s*:').test(rootNow.root));
ok(missing.length === 0,
   'THE DUOTONE IS DECLARED AT :root - ' + TOKENS.length + ' properties in two families, gold and ' +
   'blue, every one of them in the one token block', JSON.stringify(missing));
const aliases = [['--accent', 'var(--blue-structure)'], ['--live', 'var(--blue-live)'],
  ['--web', 'var(--blue-live)'], ['--local', 'var(--gold-local)'], ['--doc', 'var(--gold-local)']];
const badAlias = aliases.filter(([k, v]) => !new RegExp(k.replace(/-/g, '\\-') + '\\s*:\\s*' +
  v.replace(/[()-]/g, (c) => '\\' + c) + '\\s*;').test(rootNow.root));
ok(badAlias.length === 0 && /body\.accent-amber\{--accent:var\(--gold-core\)\}/.test(cssNow),
   'and the old names are MEMBERS of the families rather than literals of their own: --accent is ' +
   'the structure blue, --live and --web the live member, --local and --doc the local one, and the ' +
   'amber variant is the gold core', JSON.stringify(badAlias));
ok(!!BASE, 'the pre-mandate stylesheet is readable at ' + BASE_REV + ', so the next claim has ' +
   'something to be compared with', git.stderr);
const outsideNow = new Set(hues(rootNow.rest));
const outsideBase = new Set(hues(splitRoot(cssBase).rest));
const invented = [...outsideNow].filter((h) => !outsideBase.has(h));
const nowCount = hues(rootNow.rest).length, baseCount = hues(splitRoot(cssBase).rest).length;
ok(invented.length === 0,
   'NO NEW HUE OUTSIDE THE TOKEN BLOCK: the ' + outsideNow.size + ' distinct coloured literals left ' +
   'in the rules are all ones the stylesheet already had, and there are ' + nowCount + ' of them ' +
   'against ' + baseCount + ' before - every colour this round added came through a token',
   JSON.stringify(invented));
ok(nowCount < baseCount,
   'and the rules carry FEWER literal colours than they did (' + baseCount + ' -> ' + nowCount +
   '), because the accent sites were moved onto the families rather than restated',
   JSON.stringify({ before: baseCount, after: nowCount }));
/* THE JEWELS: on the duotone by hue, and under deck_proof's sweet ceiling. */
const pal = (/const PALETTE = \[([\s\S]*?)\]/.exec(NOW) || [, ''])[1].match(/#[0-9A-Fa-f]{6}/g) || [];
const hueOf = (hex) => {
  const n = parseInt(hex.slice(1), 16);
  const r = (n >> 16) & 255, g = (n >> 8) & 255, b = n & 255;
  const mx = Math.max(r, g, b), mn = Math.min(r, g, b);
  if (mx === mn) return -1;
  let h = mx === r ? ((g - b) / (mx - mn)) % 6 : mx === g ? (b - r) / (mx - mn) + 2 : (r - g) / (mx - mn) + 4;
  return (h * 60 + 360) % 360;
};
const offFamily = pal.filter((h) => { const d = hueOf(h); return !((d >= 15 && d <= 65) || (d >= 185 && d <= 245)); });
const sweets = pal.filter((h) => { const n = parseInt(h.slice(1), 16);
  const c = [(n >> 16) & 255, (n >> 8) & 255, n & 255];
  return Math.max(...c) > 224 && Math.max(...c) - Math.min(...c) > 120; });
ok(pal.length >= 7 && offFamily.length === 0 && sweets.length === 0,
   'THE CLUSTER JEWELS ARE ON THE DUOTONE: ' + pal.length + ' of them, every hue either warm ' +
   '(15-65 deg) or cool (185-245 deg), none a boiled sweet - ' + pal.join(' '),
   JSON.stringify({ offFamily, sweets }));

step('3 · the motion vocabulary, off the source');
const EASES = ['--ease-panel-open', '--ease-node-orbit-drift', '--ease-caption-reveal', '--ease-sphere-pulse'];
const undeclared = EASES.filter((k) => !new RegExp(k.replace(/-/g, '\\-') + '\\s*:').test(rootNow.root));
ok(undeclared.length === 0,
   'THE FOUR NAMED CURVES ARE DECLARED once, at :root: ' + EASES.join(', '), JSON.stringify(undeclared));
const script = NOW.slice(NOW.indexOf('</style>'));
const unused = EASES.filter((k) => !rootNow.rest.includes('var(' + k + ')') &&
  !new RegExp("EASE\\.(curve|ms)\\('" + k + "'\\)").test(script));
ok(unused.length === 0,
   'and EVERY ONE IS REFERENCED - by a rule as var(), or by the script through EASE.curve(), which ' +
   'reads the curve back out of the cascade instead of keeping a copy', JSON.stringify(unused));
const loose = (rootNow.rest.match(/cubic-bezier\([^)]*\)/g) || []);
ok(loose.length === 0,
   'NO CURVE IS PASTED: there is no cubic-bezier() in the stylesheet outside the block that names ' +
   'them (there were ' + (splitRoot(cssBase).rest.match(/cubic-bezier\(/g) || []).length +
   ' before this round)', JSON.stringify(loose));
const orbitSrcAt = NOW.indexOf('/* ======================= THE ORBIT MAP');
const orbitSrcTo = NOW.indexOf('/* ---- legend ----', orbitSrcAt);
const orbitOnly = orbitSrcAt >= 0 && orbitSrcTo > orbitSrcAt ? NOW.slice(orbitSrcAt, orbitSrcTo) : '';
const scriptCurves = (orbitOnly.match(/cubic-bezier\(\s*[\d.]+\s*,/g) || []).length;
ok(orbitOnly.length > 0 && scriptCurves === 0,
   'and the orbit map\'s script holds no curve of its own either: it moves on the names',
   String(scriptCurves));

step('2 · the galaxy view, off the corpus on disk');
const gd = readFileSync('viewer/graph-data.js', 'utf8');
const GRAPH = JSON.parse(gd.slice(gd.indexOf('{'), gd.lastIndexOf('};') + 1));
const groupsOnDisk = (GRAPH.meta && GRAPH.meta.groups && GRAPH.meta.groups.length)
  ? GRAPH.meta.groups.slice() : [...new Set(GRAPH.nodes.map((n) => n.group))].sort();
const countsOnDisk = {};
GRAPH.nodes.forEach((n) => { countsOnDisk[n.group] = (countsOnDisk[n.group] || 0) + 1; });
note('graph-data.js: ' + GRAPH.nodes.length + ' notes in ' + groupsOnDisk.length + ' clusters - ' +
     groupsOnDisk.map((g) => g + ' ' + (countsOnDisk[g] || 0)).join(', '));
const orbitSrc = (() => {
  const a = NOW.indexOf('/* ======================= THE ORBIT MAP');
  const b = NOW.indexOf('/* ---- legend ----', a);
  return a >= 0 && b > a ? NOW.slice(a, b) : '';
})();
const hard = groupsOnDisk.filter((g) => new RegExp("['\"`]" + g + "['\"`]").test(orbitSrc));
ok(orbitSrc.length > 2000 && hard.length === 0,
   'THE MAP CARRIES NO LIST OF ITS OWN: the orbit module\'s ' + orbitSrc.length + ' characters ' +
   'contain none of the corpus\'s ' + groupsOnDisk.length + ' folder names as a literal',
   JSON.stringify(hard));

/* ------------------------------------------------------------------ the running page */
const EXES = ['C:/Program Files/Google/Chrome/Application/chrome.exe',
              'C:/Program Files (x86)/Google/Chrome/Application/chrome.exe',
              process.env.LOCALAPPDATA + '/Google/Chrome/Application/chrome.exe'];
const exe = EXES.find((p) => existsSync(p));
function shutPort(port) {
  spawnSync('powershell.exe', ['-NoProfile', '-Command',
    'Get-CimInstance Win32_Process | Where-Object { $_.Name -eq \'chrome.exe\' -and ' +
    '$_.CommandLine -match \'remote-debugging-port=' + port + '\\b\' } | ' +
    'ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }'],
    { stdio: 'ignore' });
}
function shutChrome(profile) {
  spawnSync('powershell.exe', ['-NoProfile', '-Command',
    'Get-CimInstance Win32_Process | Where-Object { $_.Name -eq \'chrome.exe\' -and ' +
    '$_.CommandLine -match \'' + basename(profile) + '\' } | ' +
    'ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }'],
    { stdio: 'ignore' });
}
const profiles = [];
process.on('exit', () => { for (const p of profiles) shutChrome(p); shutPort(PORT); });

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
  async evaluate(expression) {
    const r = await this.send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true });
    if (r.result && r.result.exceptionDetails) {
      const d = r.result.exceptionDetails;
      throw new Error('page threw: ' + ((d.exception && (d.exception.description || d.exception.value)) || d.text));
    }
    return r.result && r.result.result ? r.result.result.value : undefined;
  }
  async json(e) { return JSON.parse(await this.evaluate('(async () => JSON.stringify(await (' + e + ')))()') || 'null'); }
}
const cdp = async (p) => { const r = await fetch(CDP + p); const t = await r.text();
  try { return JSON.parse(t); } catch { return t; } };
async function waitFor(page, expr, ms) {
  const t0 = Date.now();
  while (Date.now() - t0 < ms) { try { if (await page.evaluate(expr)) return true; } catch { } await sleep(200); }
  return false;
}

if (!exe) ok(false, 'the page is reachable in a real browser', 'no chrome.exe');
else {
  shutPort(PORT);
  await sleep(300);
  const profile = mkdtempSync(join(tmpdir(), 'uiproof-'));
  profiles.push(profile);
  /* UI MANDATE II: the fake microphone, so section 6 can open the REAL ear with a real click -
     two seconds of digital silence, the same file conversation_proof feeds its ear. */
  const silence = join(profile, 'silence.wav');
  {
    const rate = 48000, n = rate * 2, bytes = n * 2, b = Buffer.alloc(44 + bytes);
    b.write('RIFF', 0); b.writeUInt32LE(36 + bytes, 4); b.write('WAVE', 8);
    b.write('fmt ', 12); b.writeUInt32LE(16, 16); b.writeUInt16LE(1, 20);
    b.writeUInt16LE(1, 22); b.writeUInt32LE(rate, 24); b.writeUInt32LE(rate * 2, 28);
    b.writeUInt16LE(2, 32); b.writeUInt16LE(16, 34);
    b.write('data', 36); b.writeUInt32LE(bytes, 40);
    writeFileSync(silence, b);
  }
  spawn(exe, ['--remote-debugging-port=' + PORT, '--user-data-dir=' + profile, '--headless=new',
    '--no-first-run', '--no-default-browser-check', '--window-size=1440,900',
    '--enable-unsafe-swiftshader', '--use-angle=swiftshader',
    '--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream',
    '--use-file-for-fake-audio-capture=' + silence,
    GALAXY + '/?mute=1&vanish=0'], { detached: true, stdio: 'ignore' });
  for (let i = 0; i < 80; i++) { try { await cdp('/json/version'); break; } catch { await sleep(250); } }
  let target = null;
  for (let i = 0; i < 40; i++) {
    const l = await cdp('/json/list');
    target = (Array.isArray(l) ? l : []).filter((t) => t.type === 'page').find((t) => t.url.includes('127.0.0.1:4700'));
    if (target) break; await sleep(300);
  }
  if (!target) throw new Error('no viewer page');
  const page = new Page(target.webSocketDebuggerUrl);
  await page.open();
  await page.send('Runtime.enable');
  ok(await waitFor(page, '!!(window.__galaxy && __galaxy.orbit && __galaxy.nodes && __galaxy.nodes.length)', 60000),
     'the deck booted and carries the orbit map\'s door');

  step('1 · the palette, off the computed style');
  const res = await page.json(`(function(){
    var p = document.createElement('i'); p.style.position = 'fixed'; p.style.left = '-99px';
    document.body.appendChild(p);
    var c = function (v) { p.style.color = ''; p.style.color = v; return getComputedStyle(p).color; };
    var out = {
      goldCore: c('var(--gold-core)'), goldTriplet: c('rgb(var(--gold-core-rgb))'),
      blue: c('var(--blue-structure)'), blueTriplet: c('rgb(var(--blue-structure-rgb))'),
      accent: c('var(--accent)'), live: c('var(--live)'), local: c('var(--local)'),
      web: c('var(--web)'), doc: c('var(--doc)'), hot: c('var(--gold-hot)'),
      goldDim: c('var(--gold-dim)'), blueDim: c('var(--blue-dim)')
    };
    p.remove();
    var cap = document.getElementById('caption'), w = document.createElement('span');
    w.className = 'w now'; w.textContent = 'x'; cap.appendChild(w);
    out.nowWord = getComputedStyle(w).color; w.remove();
    var rules = [];
    Array.prototype.forEach.call(document.styleSheets, function (s) {
      try { Array.prototype.forEach.call(s.cssRules, function (r) { if (r.selectorText) rules.push([r.selectorText, r.style.cssText]); }); } catch (e) {}
    });
    /* EVERY rule with the selector, joined: this stylesheet often states one selector twice -
       layout in one rule, colour in a later one - and reading only the first is reading half. */
    var find = function (sel) { return rules.filter(function (x) { return x[0] === sel; })
      .map(function (x) { return x[1]; }).join(' '); };
    out.cmdHover = find('.cmdact:hover'); out.barFocus = find('#bar:focus-within');
    out.chipHover = find('.chip:hover'); out.chipIdle = find('.chip');
    out.cmdScroll = find('#cmd .cb');
    return out; })()`);
  note('computed: ' + JSON.stringify(res));
  ok(res.goldCore === 'rgb(255, 178, 60)' && res.goldTriplet === res.goldCore &&
     res.blue === 'rgb(124, 196, 255)' && res.blueTriplet === res.blue && res.hot === 'rgb(255, 242, 210)',
     'THE TWO MASTERS RESOLVE IN THE BROWSER and each triplet is exactly its master: gold ' +
     res.goldCore + ', blue ' + res.blue + ', the hot heart ' + res.hot, JSON.stringify(res));
  ok(res.accent === res.blue && res.live === 'rgb(34, 224, 255)' && res.web === res.live &&
     res.local === 'rgb(240, 184, 102)' && res.doc === res.local,
     'AND THE PROVENANCE COLOURS COMPUTE TO EXACTLY WHAT THEY ALWAYS DID - the instrumentation ' +
     'light is untouched: --live ' + res.live + ', --local ' + res.local + ', --accent ' + res.accent,
     JSON.stringify(res));
  ok(res.nowWord === res.goldCore,
     'THE WORD BEING SAID IS GOLD on the glass: a .w.now span in the caption computes to ' +
     res.nowWord + ' - the presence acting, in the presence\'s own amber', res.nowWord);
  const goldIn = (s) => /255, 178, 60|var\(--gold-core/.test(s);
  const blueIn = (s) => /124, 196, 255|var\(--blue-structure/.test(s);
  ok(goldIn(res.cmdHover) && goldIn(res.barFocus) && goldIn(res.chipHover),
     'ACTIVE STATES TAKE GOLD: a command row under the pointer, the ask bar with the caret in it, ' +
     'a chip under the pointer', JSON.stringify({ cmdHover: res.cmdHover, barFocus: res.barFocus, chipHover: res.chipHover }));
  ok(blueIn(res.chipIdle) && !goldIn(res.chipIdle) && blueIn(res.cmdScroll),
     'AND STRUCTURE TAKES BLUE: an idle chip and the command panel\'s scrollbar are on the ' +
     'structure family and not on the gold', JSON.stringify({ chip: res.chipIdle, scroll: res.cmdScroll }));

  step('2 · the galaxy view, on the glass');
  await page.evaluate('__galaxy.orbit.open()');
  ok(await waitFor(page, '__galaxy.orbit.isOpen && __galaxy.orbit.frames > 8', 15000),
     'the orbit map opened through the same door the stats line uses, and is moving');
  const ob = await page.json(`({ drawn: __galaxy.orbit.drawn, data: __galaxy.orbit.data, sum: __galaxy.orbit.sum,
    stats: document.getElementById('stats').textContent,
    vis: getComputedStyle(document.getElementById('orbit')).visibility })`);
  note('drawn: ' + JSON.stringify(ob.drawn.map((d) => d.label + ' / ' + d.sub)));
  const drawnNames = ob.drawn.map((d) => d.group).sort();
  ok(JSON.stringify(drawnNames) === JSON.stringify(groupsOnDisk.slice().sort()) &&
     ob.drawn.every((d) => d.label === d.group.toUpperCase()),
     'THE MAP DRAWS THE CORPUS\'S OWN CLUSTERS: ' + drawnNames.join(', ') + ' - exactly the ' +
     groupsOnDisk.length + ' folders graph-data.js lists, each labelled with its own name',
     JSON.stringify({ drawn: drawnNames, disk: groupsOnDisk }));
  const badCounts = ob.drawn.filter((d) => parseInt(d.sub, 10) !== (countsOnDisk[d.group] || 0));
  ok(badCounts.length === 0,
     'AND EACH ONE\'S COUNT IS THE ONE COUNTED FROM DISK: ' +
     ob.drawn.map((d) => d.group + ' ' + parseInt(d.sub, 10)).join(', '),
     JSON.stringify(badCounts));
  const nums = (s) => (String(s).match(/\d+/g) || []).join(',');
  ok(nums(ob.sum) === nums(ob.stats) && ob.data && ob.data.notes === GRAPH.nodes.length,
     'and its summary is the stats line\'s own arithmetic: "' + ob.sum + '" beside "' + ob.stats + '"',
     JSON.stringify({ sum: ob.sum, stats: ob.stats }));
  const t1 = await page.json('__galaxy.orbit.drawn.map(function(d){return d.transform;})');
  await sleep(1500);
  const t2 = await page.json('__galaxy.orbit.drawn.map(function(d){return d.transform;})');
  ok(t1.length > 0 && t1.some((v, i) => v !== t2[i]),
     'THE WORLDS ARE IN ORBIT: their transforms moved in 1.5s on the drift curve, by transform alone',
     JSON.stringify({ before: t1, after: t2 }));
  const wash = await page.json(`(function(){var e=document.getElementById('galaxywash'),c=getComputedStyle(e);
    return {op:+c.opacity,z:c.zIndex,pe:c.pointerEvents};})()`);
  /* UI MANDATE II CHANGED BOTH OF THESE, and the replacement says why. PR #4's map was a sheet
     summoned over the sky, so the dim went to ~0.9 while it was open and closing it hid it. The
     mandate makes the map THE MAIN PANE at rest: the dim is the PANE'S, a constant 0.58 over the
     3D sky inside the pane only, and the map leaves the glass when the STAGE turns to the
     presence, not when a close button is pressed (it has none now).
       old: wash.op > 0.9                         new: wash.op 0.58 (+-0.02), its box = the pane
       old: orbit.close() hides it                new: stage 'presence' hides it, 'galaxy' restores it */
  const pane0 = await page.json('__galaxy.layout.last.pane');
  const washBox = await page.json(`(function(){var r=document.getElementById('galaxywash').getBoundingClientRect();
    return {left:Math.round(r.left),right:Math.round(innerWidth-r.right),top:Math.round(r.top)};})()`);
  ok(Math.abs(wash.op - 0.58) <= 0.02 && wash.z === '2' && wash.pe === 'none' &&
     Math.abs(washBox.left - pane0.left) <= 1 && Math.abs(washBox.top - pane0.top) <= 1,
     'AND THE SKY STEPS BACK IN THE PANE: the dim is ' + wash.op + ' on layer ' + wash.z +
     ', pointer-events ' + wash.pe + ', and it lies over the pane only - from x=' + washBox.left +
     ' (the pane starts at ' + pane0.left + ') and y=' + washBox.top + ' (under the header)',
     JSON.stringify({ wash, washBox, pane: pane0 }));
  await page.evaluate('document.documentElement.classList.add("nomove"); __galaxy.stage.set("presence", "ui_enhancement_proof")');
  const offGlass = await waitFor(page, "getComputedStyle(document.getElementById('orbit')).visibility === 'hidden'", 3000);
  await page.evaluate('__galaxy.stage.set("galaxy", "ui_enhancement_proof"); document.documentElement.classList.remove("nomove")');
  const backOn = await waitFor(page, "getComputedStyle(document.getElementById('orbit')).visibility === 'visible' && __galaxy.orbit.isOpen", 3000);
  ok(offGlass && backOn,
     'and the map leaves the glass ENTIRELY when the stage turns to the presence - hidden, not ' +
     'merely transparent - and is back, still open, when the stage turns back to the galaxy',
     JSON.stringify({ offGlass, backOn }));

  step('4 · the ribbon and the dim behind the command panel');
  const ribbon = await page.json(`(function(){var a=getComputedStyle(document.getElementById('cmd'),'::after'),
    b=getComputedStyle(document.getElementById('focuscard'),'::after');
    return {cmd:a.backgroundImage, card:b.backgroundImage, cmdPE:a.pointerEvents};})()`);
  ok(/255, 178, 60/.test(ribbon.cmd) && /124, 196, 255/.test(ribbon.cmd) &&
     /255, 178, 60/.test(ribbon.card) && ribbon.cmdPE === 'none',
     'THE SUMMONED SURFACES CARRY THE DUOTONE RIBBON: the command panel and the focus card each ' +
     'have a gold-to-blue edge on ::after, which takes no pointer', JSON.stringify(ribbon).slice(0, 300));
  /* POLLED, NOT SLEPT. A transition's computed value moves with the document timeline, and the
     timeline moves with frames - in a software-rendered headless tab drawing a 3D sky a frame can
     take most of a second, so a fixed sleep reads a fade still in flight and calls it stuck. */
  const WASH = "+getComputedStyle(document.getElementById('galaxywash')).opacity";
  const before = await page.json(WASH);
  await page.evaluate('__galaxy.cmd.open_(true)');
  await waitFor(page, WASH + ' > 0.7', 8000);
  const during = await page.json(WASH);
  await page.evaluate('__galaxy.cmd.open_(false)');
  await waitFor(page, WASH + ' < 0.6', 8000);
  const after = await page.json(WASH);
  /* UI MANDATE II: the pane's dim rests at 0.58, so "back when it shuts" means back to 0.58.
     old: before === 0 && after === 0        new: before = after = the pane's 0.58, during > it by 0.2 */
  ok(Math.abs(before - 0.58) <= 0.02 && during >= before + 0.2 && Math.abs(after - before) <= 0.02,
     'AND THE GALAXY DIMS FURTHER BEHIND AN OPEN COMMAND PANEL and comes back when it shuts: ' +
     before + ' -> ' + during + ' -> ' + after, JSON.stringify({ before, during, after }));

  step('3 · the motion, as the browser computed it');
  const mo = await page.json(`({cmd:getComputedStyle(document.getElementById('cmd')).transitionTimingFunction,
    cap:getComputedStyle(document.getElementById('caption')).transitionTimingFunction,
    pulse: __galaxy.orbit.ease('--ease-sphere-pulse'), drift: __galaxy.orbit.ease('--ease-node-orbit-drift'),
    open: __galaxy.orbit.ease('--ease-panel-open')})`);
  ok(/cubic-bezier\(0\.16, 1, 0\.3, 1\)/.test(mo.cmd) && /linear/.test(mo.cap),
     'THE PANEL OPENS ON --ease-panel-open and the caption fades on --ease-caption-reveal, as the ' +
     'browser computed them: ' + mo.cmd + ' / ' + mo.cap, JSON.stringify(mo));
  ok(mo.drift.css === 'linear' && mo.drift.at[2] === 0.5 && /cubic-bezier/.test(mo.pulse.css) &&
     mo.open.at[2] > 0.5,
     'and the script reads the SAME curves back out of the cascade: drift ' + mo.drift.css +
     ', pulse ' + mo.pulse.css + ', panel-open at its midpoint ' + mo.open.at[2].toFixed(3),
     JSON.stringify(mo));

  step('4 · the face, inside the one allocation');
  /* READY FIRST: a mode asked for before the presence has booted is overwritten by the boot's own
     first mode (presMode records `want` and returns while there is no buffer), and under
     swiftshader the boot and its audition can still be running here. Waited for, not slept. */
  await waitFor(page, '__galaxy.presence.built && __galaxy.presence.probation !== "running"', 90000);
  const core0 = await page.json('({mode: __galaxy.presence.mode, objects: __galaxy.presence.objects, cap: __galaxy.presence.capacity})');
  await page.evaluate('__galaxy.presence.set("face")');
  const faced = await waitFor(page, '__galaxy.presence.mode === "face" && __galaxy.presence.mesh.points > 0', 20000);
  const fm = await page.json('({mode: __galaxy.presence.mode, mesh: __galaxy.presence.mesh, points: __galaxy.presence.points,' +
    ' cap: __galaxy.presence.capacity, objects: __galaxy.presence.objects, shader: __galaxy.presence.shader})');
  note('face: ' + JSON.stringify(fm));
  /* DENSITY ALONG AN EDGE IS THE CLAIM, not the edge count. The first lattice had 659 edges at
     four points each and the plate showed a dot-grid; what makes an edge read as a LINE is how
     many points share it, so eight a side is the floor and the edge count only has to be a
     real lattice's. */
  ok(faced && fm.mesh.points >= 3000 && fm.mesh.edges >= 200 && fm.mesh.perEdge >= 8 &&
     fm.points <= fm.cap && fm.objects <= core0.objects && fm.shader === true,
     'THE FACE CARRIES ITS MESH: ' + fm.mesh.points + ' points along ' + fm.mesh.edges + ' edges (' +
     fm.mesh.perEdge + ' a side) and ' + fm.mesh.verts + ' vertices, inside ' + fm.points + ' of a ' +
     fm.cap + '-point cap, and the presence is still ' + fm.objects + ' object(s) on one shader', JSON.stringify(fm));
  const faceMesh = fm.mesh;
  /* UI MANDATE II: the core is gone and the rich mode is the dust. old: back to "core". */
  await page.evaluate('__galaxy.presence.set("dust")');
  ok(await waitFor(page, '__galaxy.presence.mode === "dust"', 15000),
     'and the deck goes back to wearing its dust, which is the rich mode since UI mandate II');

  step('5 · the sound, in two families');
  const au = await page.json('({family: __galaxy.audio.family, structure: __galaxy.audio.structure, played: __galaxy.audio.played})');
  ok(au.family && au.family.cool.indexOf('glass') >= 0 && au.family.warm.indexOf('wake') >= 0 &&
     Array.isArray(au.structure),
     'THE CHIMES ARE SORTED INTO THE SAME TWO FAMILIES: warm ' + JSON.stringify(au.family.warm) +
     ' for the presence acting, cool ' + JSON.stringify(au.family.cool) + ' for a surface arriving - ' +
     'and the cool cues keep their own ring, so they can never push the wake out of the one ' +
     'deck_proof reads', JSON.stringify(au));

  /* ============================ 6. UI MANDATE II ============================
     THE SIDEBAR'S MAPPING, written out because the mandate asks for it and because the proof
     below presses each row and checks the section it reaches:
       Galaxy   -> stageSet('galaxy'): the orbit map of the corpus in the main pane
       Chat     -> the / organ: the written ask line (#typeline), focused
       Archive  -> cmdRun('archive'): the panel listing the documents in archive/ - the house's
                   memory, named for what it is (the reference's "Memory")
       Web      -> the pages the last web lookup read (openSources' own arguments); with none
                   fetched this session it SAYS so on the status line
       Focus    -> cmdRun('focus'): the focus button - a real session, aborted by this file
       System   -> cmdOpen(true): the command panel, where every setting lives (Ctrl+K)
     And the voice card under them presses the microphone button. */
  step('6 · UI mandate II - the layout, at 1600x900');
  await page.send('Emulation.setDeviceMetricsOverride', { width: 1600, height: 900, deviceScaleFactor: 1, mobile: false });
  await sleep(600);
  await page.evaluate('__galaxy.layout.run()');
  await sleep(400);
  const click = async (sel) => {
    const box = await page.json(`(function(){var e=document.querySelector(${JSON.stringify(sel)});if(!e)return null;
      var r=e.getBoundingClientRect();return {x:Math.round(r.left+r.width/2),y:Math.round(r.top+r.height/2)};})()`);
    if (!box) return null;
    for (const type of ['mousePressed', 'mouseReleased']) {
      await page.send('Input.dispatchMouseEvent', { type, x: box.x, y: box.y, button: 'left', clickCount: 1 });
    }
    return box;
  };
  const NAV = ['galaxy', 'chat', 'archive', 'web', 'focus', 'system'];
  const navNow = await page.json(`({nav: __galaxy.stage.nav(), last: __galaxy.layout.last,
    rail: parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--rail-h')),
    side: (function(){var r=document.getElementById('sidenav').getBoundingClientRect();
      return {left:r.left,top:Math.round(r.top),w:Math.round(r.width),h:Math.round(r.height)};})(),
    voice: !!document.getElementById('navvoice')})`);
  note('sidebar: ' + navNow.nav.map((n) => n.go + '="' + n.label + '"').join(' · ') + ' at ' + JSON.stringify(navNow.side));
  ok(JSON.stringify(navNow.nav.map((n) => n.go)) === JSON.stringify(NAV) &&
     navNow.nav.every((n) => n.label.length > 2) && navNow.voice &&
     navNow.side.left === 0 && navNow.side.w === navNow.last.sideW && navNow.side.w >= 150 &&
     Math.abs(navNow.side.top - navNow.rail) <= 1,
     'THE SIDEBAR RENDERS: ' + navNow.nav.map((n) => n.label).join(', ') + ' and the voice card, ' +
     navNow.side.w + 'px wide (icon and label) down the left edge under the ' + navNow.rail + 'px header',
     JSON.stringify(navNow.side));

  /* EACH ROW, PRESSED BY A REAL MOUSE EVENT, REACHES ITS SECTION. */
  const reached = {};
  await page.evaluate('document.documentElement.classList.add("nomove"); __galaxy.stage.set("presence", "ui_enhancement_proof 6")');
  await click('#sidenav .navi[data-go="galaxy"]');
  await sleep(300);
  reached.galaxy = await page.json(`({stage: __galaxy.stage.now, why: __galaxy.stage.why,
    on: !!document.querySelector('#sidenav .navi.on[data-go="galaxy"]'),
    orbit: getComputedStyle(document.getElementById('orbit')).visibility})`);
  await click('#sidenav .navi[data-go="chat"]');
  await sleep(300);
  reached.chat = await page.json(`({up: document.getElementById('typeline').classList.contains('up'),
    focus: document.activeElement && document.activeElement.id})`);
  await page.evaluate(`(function(){var e=document.getElementById('typeline');if(e)e.classList.remove('up');
    if(document.activeElement)document.activeElement.blur();})()`);
  const health = await (await fetch(GALAXY + '/health')).json();
  await click('#sidenav .navi[data-go="archive"]');
  await waitFor(page, "document.getElementById('panel').classList.contains('open')", 4000);
  reached.archive = await page.json(`({open: document.getElementById('panel').classList.contains('open'),
    docs: document.getElementById('panel').classList.contains('docs'),
    label: document.getElementById('p-label').textContent, meta: document.getElementById('p-meta').textContent})`);
  await page.evaluate(`(function(){var c=document.getElementById('close');if(c&&document.getElementById('panel').classList.contains('open'))c.click();})()`);
  await sleep(500);
  const webBefore = await page.json('__galaxy.stage.lastWeb');
  await click('#sidenav .navi[data-go="web"]');
  await sleep(300);
  reached.web = await page.json(`({status: document.getElementById('status').textContent, last: __galaxy.stage.lastWeb,
    panel: document.getElementById('panel').classList.contains('web')})`);
  await click('#sidenav .navi[data-go="focus"]');
  let focusState = null;
  for (let i = 0; i < 25 && !(focusState && (focusState.state === 'running' || focusState.state === 'arming')); i++) {
    await sleep(300);
    try { focusState = (await (await fetch(GALAXY + '/focus')).json()).focus; } catch { focusState = null; }
  }
  reached.focus = { state: focusState && focusState.state };
  await fetch(GALAXY + '/focus', { method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ cmd: 'abort' }) }).catch(() => null);
  await sleep(800);
  await click('#sidenav .navi[data-go="system"]');
  await sleep(500);
  reached.system = await page.json(`({open: document.getElementById('cmd').classList.contains('open')})`);
  await page.evaluate('__galaxy.cmd.open_(false); document.documentElement.classList.remove("nomove")');
  await sleep(500);
  note('reached: ' + JSON.stringify(reached));
  const filesLine = new RegExp('^' + ((health.vectors && health.vectors.files) || -1) + ' files? ');
  const navOk = {
    galaxy: reached.galaxy.stage === 'galaxy' && reached.galaxy.why === 'the sidebar' && reached.galaxy.on &&
            reached.galaxy.orbit === 'visible',
    chat: reached.chat.up === true && reached.chat.focus === 'qline',
    archive: reached.archive.open && reached.archive.docs && reached.archive.label === 'The archive' &&
             filesLine.test(reached.archive.meta),
    web: webBefore === null ? /no web page has been read this session/.test(reached.web.status)
                            : reached.web.panel === true,
    /* A session's first state is 'arming' (the grace before it counts), then 'running'. */
    focus: reached.focus.state === 'arming' || reached.focus.state === 'running',
    system: reached.system.open === true
  };
  ok(NAV.every((k) => navOk[k]),
     'EVERY ROW REACHES A SECTION THE HOUSE HAS, pressed with a real mouse event: Galaxy turned the ' +
     'pane to the map ("' + reached.galaxy.why + '"), Chat raised and focused the written ask, ' +
     'Archive opened "' + reached.archive.label + '" reading "' + reached.archive.meta.slice(0, 40) +
     '" - the server\'s own ' + (health.vectors && health.vectors.files) + ' files - Web ' +
     (webBefore === null ? 'SAID no page has been read yet' : 'reopened the last lookup') +
     ', Focus started a real session (' + reached.focus.state + ', then aborted here), System opened ' +
     'the command panel', JSON.stringify({ navOk, reached }));

  /* THE HEADER: THE NUMBERS ARE THE SERVER'S. #stats is counted by the page from its own arrays;
     /health is counted by server.py off the corpus. Two programs, one number. */
  const hdr = await page.json(`({stats: document.getElementById('stats').textContent,
    online: document.getElementById('toprail').classList.contains('online'),
    titleTop: Math.round(document.getElementById('title').getBoundingClientRect().top),
    statsBottom: Math.round(document.getElementById('stats').getBoundingClientRect().bottom),
    rail: parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--rail-h'))})`);
  const sn = (hdr.stats.match(/\d+/g) || []).map(Number);
  ok(sn[0] === health.notes && sn[1] === health.links && sn[2] === groupsOnDisk.length &&
     hdr.online === (health.ok === true) && hdr.titleTop >= 0 && hdr.statsBottom <= hdr.rail + 1,
     'THE HEADER CARRIES REAL COMPUTED VALUES: "' + hdr.stats + '" - ' + health.notes + ' notes and ' +
     health.links + ' connections as server.py counts them on /health, ' + groupsOnDisk.length +
     ' clusters as graph-data.js lists them - and ONLINE is lit because /health said ok, all inside ' +
     'the ' + hdr.rail + 'px header band', JSON.stringify({ hdr, notes: health.notes, links: health.links }));

  /* THE GALAXY FILLS THE MAIN PANE, off the live groups. */
  const gx = await page.json(`({o: (function(){var r=document.getElementById('orbit').getBoundingClientRect();
      return {l:Math.round(r.left),r:Math.round(r.right),t:Math.round(r.top),b:Math.round(r.bottom)};})(),
    pane: __galaxy.layout.last.pane, vh: innerHeight, drawn: __galaxy.orbit.drawn.map(function(d){return d.group;}),
    cards: document.querySelectorAll('#ob-svg .ob-card').length})`);
  const paneArea = (gx.pane.right - gx.pane.left) * (gx.vh - gx.pane.top);
  const orbitArea = (gx.o.r - gx.o.l) * (gx.o.b - gx.o.t);
  ok(Math.abs(gx.o.l - gx.pane.left) <= 1 && Math.abs(gx.o.r - gx.pane.right) <= 1 &&
     orbitArea / paneArea >= 0.75 &&
     JSON.stringify(gx.drawn.slice().sort()) === JSON.stringify(groupsOnDisk.slice().sort()),
     'THE GALAXY FILLS THE MAIN PANE: the map spans x ' + gx.o.l + '-' + gx.o.r + ' (the pane is ' +
     gx.pane.left + '-' + gx.pane.right + '), ' + Math.round(100 * orbitArea / paneArea) + '% of the ' +
     'pane\'s area above the ask, and it draws the ' + gx.drawn.length + ' groups graph-data.js lists ' +
     '(' + gx.drawn.join(', ') + ') - with no group name written in its source, see section 2',
     JSON.stringify(gx));

  /* THE RIGHT PANEL: THE PERSONA THE SERVER SERVES AND A REAL ANSWER'S REAL NOTES. */
  const persona = await (await fetch(GALAXY + '/persona')).json();
  const pick = GRAPH.nodes.filter((n) => n.label).slice(0, 2);
  await page.evaluate('(__galaxy.say("which notes say this?", "Two of your notes say so.", false, ' +
    JSON.stringify(pick.map((n) => n.id)) + '), 1)');
  await sleep(600);
  const rp = await page.json(`({name: document.getElementById('convo-name').textContent,
    sub: document.getElementById('convo-sub').textContent,
    chips: Array.prototype.map.call(document.querySelectorAll('#a-chips .chip span'), function(s){return s.textContent;}),
    lbl: document.querySelector('#a-src .lbl').textContent,
    brain: (function(){var r=document.getElementById('brain').getBoundingClientRect();return {l:Math.round(r.left),r:Math.round(r.right),t:Math.round(r.top),b:Math.round(r.bottom)};})(),
    answer: (function(){var r=document.getElementById('answer').getBoundingClientRect();return {l:Math.round(r.left),r:Math.round(r.right),t:Math.round(r.top),b:Math.round(r.bottom)};})(),
    paneR: __galaxy.layout.last.pane.right, mirrors: __galaxy.stage.mirrors})`);
  await sleep(1200);
  const mirrors2 = await page.json('__galaxy.stage.mirrors');
  ok(rp.name === persona.assistant && rp.sub.indexOf(persona.boss) >= 0 &&
     JSON.stringify(rp.chips) === JSON.stringify(pick.map((n) => n.label)) && rp.lbl === 'Drawn from' &&
     rp.brain.l >= rp.paneR && rp.answer.l >= rp.brain.l && rp.answer.r <= rp.brain.r &&
     mirrors2 > rp.mirrors,
     'THE RIGHT PANEL SHOWS REAL SOURCES: it is headed "' + rp.name + '" - the assistant /persona ' +
     'serves - and a real answer through the house\'s own renderer lists "' + rp.chips.join('", "') +
     '", the labels graph-data.js gives those two ids, inside the right-hand column (x ' + rp.brain.l +
     '-' + rp.brain.r + ', right of the pane\'s ' + rp.paneR + '); its avatar mirrors the presence ' +
     '(' + rp.mirrors + ' -> ' + mirrors2 + ' frames)', JSON.stringify({ rp, mirrors2 }));
  await page.evaluate('(__galaxy.vanish.now(true), 1)').catch(() => null);

  /* THE FOUR DUST STATES, IN THE FOUR TOKENS, and each one ON THE GLASS through the plate pin. */
  const ds = await page.json(`(function(){
    var cs = getComputedStyle(document.documentElement), v = function (n) { return cs.getPropertyValue(n).trim().toLowerCase(); };
    var d = __galaxy.presence.dust(), out = { states: d.states, palette: d.palette,
      tokens: { listening: v('--blue-structure'), thinking: v('--gold-core'), speaking: v('--gold-hot'), alert: v('--fail') },
      heart: {} };
    d.states.forEach(function (s) { __galaxy.presence.dustState(s); out.heart[s] = __galaxy.presence.dust().heart; });
    __galaxy.presence.dustState(null);
    return out; })()`);
  ok(JSON.stringify(ds.states) === JSON.stringify(['listening', 'thinking', 'speaking', 'alert']) &&
     ds.states.every((s) => ds.palette[s] === ds.tokens[s] && ds.heart[s] === ds.tokens[s]) &&
     new Set(Object.values(ds.palette)).size === 4,
     'THE FOUR DUST STATES EXIST IN THEIR TINTS: listening ' + ds.palette.listening + ' (--blue-structure), ' +
     'thinking ' + ds.palette.thinking + ' (--gold-core), speaking ' + ds.palette.speaking +
     ' (--gold-hot, the third tint: the gold family\'s white-hot), alert ' + ds.palette.alert +
     ' (--fail) - each read back off the shader\'s own heart uniform when pinned',
     JSON.stringify(ds));

  /* RING, CUBE AND CORE ARE GONE - from the mode list, from the panel's call, and from the source. */
  const gone = await page.json(`(function(){var was = __galaxy.presence.mode, after = {};
    ['ring','cube','core'].forEach(function (m) { __galaxy.presence.set(m); after[m] = __galaxy.presence.mode; });
    return { modes: __galaxy.presence.MODES, after: after, was: was }; })()`);
  const srcGone = ['presRingFill', 'presCubeFill', 'presCoreFill', 'PRES_CORE_ROLE'].filter((k) => NOW.includes(k));
  ok(JSON.stringify(gone.modes) === JSON.stringify(['dust', 'face']) &&
     Object.values(gone.after).every((m) => m === gone.was) && srcGone.length === 0,
     'RING, CUBE AND CORE ARE GONE: the modes are ' + JSON.stringify(gone.modes) + ', asking for any of ' +
     'the three by the panel\'s call leaves the presence on "' + gone.was + '", and none of their fills ' +
     'is left in viewer/index.html', JSON.stringify({ gone, srcGone }));

  /* THE FACE'S TOPOLOGY AGAINST PR #4'S LATTICE. The lattice is rebuilt here from PR #4's own
     constants (git show e5ead43) exactly as its source wired it - rows, columns and one
     alternating diagonal per cell - which makes every interior vertex degree 4 or 8 BY
     CONSTRUCTION, whatever the jitter. The anatomical mesh's degrees are read off the page. */
  const PR4 = spawnSync('git', ['show', 'e5ead43:viewer/index.html'], { encoding: 'utf8', maxBuffer: 64 << 20 });
  const pr4R = +((/FACE_MESH_ROWS:\s*(\d+)/.exec(PR4.stdout || '') || [])[1] || 0);
  const pr4C = +((/FACE_MESH_COLS:\s*(\d+)/.exec(PR4.stdout || '') || [])[1] || 0);
  const pr4Deg = {};
  {
    const deg = new Map(), k = (i, j) => i * pr4C + j, add = (a, b) => {
      deg.set(a, (deg.get(a) || 0) + 1); deg.set(b, (deg.get(b) || 0) + 1); };
    for (let i = 0; i < pr4R; i++) for (let j = 0; j < pr4C; j++) {
      if (j + 1 < pr4C) add(k(i, j), k(i, j + 1));
      if (i + 1 < pr4R) add(k(i, j), k(i + 1, j));
      if (i + 1 < pr4R && j + 1 < pr4C) {
        if ((i + j) % 2) add(k(i, j), k(i + 1, j + 1)); else add(k(i, j + 1), k(i + 1, j));
      }
    }
    for (const d of deg.values()) pr4Deg[d] = (pr4Deg[d] || 0) + 1;
  }
  const shareOf = (h, ds) => { const n = Object.values(h).reduce((a, b) => a + b, 0) || 1;
    return ds.reduce((s, d) => s + (h[d] || 0), 0) / n; };
  const share48 = (h) => shareOf(h, [4, 8]);
  const share567 = (h) => shareOf(h, [5, 6, 7]);
  const nowDeg = (faceMesh && faceMesh.degrees) || {};
  const kinds = (faceMesh && faceMesh.kinds) || {};
  const ANAT = ['brow', 'cheekbone', 'jaw', 'earL', 'earR', 'eyeL', 'eyeR', 'mouth', 'nose', 'chin'];
  const loops = (faceMesh && faceMesh.loops) || {};
  const closed = ['eyeL', 'eyeR', 'mouth'].every((l) => loops[l] && loops[l].n > 0 && loops[l].closed === loops[l].n);
  note('degrees: PR #4 lattice ' + JSON.stringify(pr4Deg) + ' (' + pr4R + 'x' + pr4C + ') · now ' + JSON.stringify(nowDeg));
  /* The lattice's figures are exact, not sampled: an 11x10 grid has 72 interior vertices, all of
     degree 4 or 8, and its border is 2/3/5 - so 65% of it is {4,8} and 15% is {5,6,7}. A
     triangulation of landmarks is the other way round: most vertices of degree 5-7. */
  ok(pr4R > 0 && share48(nowDeg) <= share48(pr4Deg) / 2 && share567(nowDeg) >= 0.6 &&
     share567(pr4Deg) <= 0.2 &&
     Object.keys(nowDeg).length >= 5 && ANAT.every((a) => (kinds[a] || 0) > 0) && closed,
     'THE FACE\'S TOPOLOGY IS ANATOMICAL, NOT PR #4\'S GRID: ' + Math.round(100 * share48(pr4Deg)) +
     '% of the lattice\'s ' + (pr4R * pr4C) + ' vertices have degree 4 or 8 against ' +
     Math.round(100 * share48(nowDeg)) + '% of the new mesh\'s ' + (faceMesh && faceMesh.verts) +
     ', and ' + Math.round(100 * share567(nowDeg)) + '% of the new mesh is degree 5-7 against ' +
     Math.round(100 * share567(pr4Deg)) + '% of the lattice; its landmarks are ' +
     ANAT.map((a) => a + ' ' + kinds[a]).join(', ') + ', and both eyes and the mouth are CLOSED loops in ' +
     'the edge set - inside the same ' + (faceMesh && faceMesh.points) + '-point mesh stratum',
     JSON.stringify({ pr4Deg, nowDeg, kinds, loops }));

  /* CENTRED, AT A STATED RATIO. */
  await page.evaluate('document.documentElement.classList.add("nomove"); __galaxy.stage.set("presence", "ui_enhancement_proof 6")');
  await sleep(500);
  const cp = await page.json(`({r: (function(){var b=document.getElementById('presence').getBoundingClientRect();
      return {l:b.left,t:b.top,w:b.width,h:b.height};})(), box: __galaxy.layout.last.wellBox,
    pane: __galaxy.layout.last.pane, L: {ratio: __galaxy.layout.LAYOUT.PRES_RATIO, edge: __galaxy.layout.LAYOUT.EDGE,
      cap: __galaxy.layout.LAYOUT.PRES_CAP}})`);
  await page.evaluate('__galaxy.stage.set("galaxy", "ui_enhancement_proof 6"); document.documentElement.classList.remove("nomove")');
  const bandC = { x: (cp.box.band.l + cp.box.band.r) / 2, y: (cp.box.band.t + cp.box.band.b) / 2 };
  const mid = { x: cp.r.l + cp.r.w / 2, y: cp.r.t + cp.r.h / 2 };
  const paneMin = Math.min(cp.pane.right - cp.pane.left - 2 * cp.L.edge, cp.box.pane.band);
  const ratio = cp.r.w / paneMin;
  ok(Math.abs(mid.x - bandC.x) <= 1.5 && Math.abs(mid.y - bandC.y) <= 1.5 &&
     (Math.abs(ratio - cp.L.ratio) <= 0.01 || cp.r.w >= cp.L.cap - 1),
     'THE PRESENCE IS CENTRED IN THE MAIN PANE AT A STATED RATIO: midpoint ' + Math.round(mid.x) + ',' +
     Math.round(mid.y) + ' on the pane band\'s ' + Math.round(bandC.x) + ',' + Math.round(bandC.y) + ', ' +
     Math.round(cp.r.w) + 'px = ' + ratio.toFixed(3) + ' x min(pane width, pane height) = ' + paneMin +
     'px - PRES_RATIO ' + cp.L.ratio + ', against PR #4\'s docked 420px well',
     JSON.stringify({ cp, ratio }));

  /* THE TURN FIRES OFF THE REAL EAR. A real mouse press on #mic runs earOpen(), which adds .ear
     to #mic and calls sealPaint(); sealPaint() hands the open ear to stageVoice(), which turns
     the stage. Nothing in this file calls the stage door for this check. */
  const st0 = await page.json('({now: __galaxy.stage.now, turns: __galaxy.stage.turns, flips: __galaxy.stage.flips})');
  await click('#mic');
  const earUp = await waitFor(page, '__galaxy.ear.open === true', 8000);
  const flipping = await page.json(`(function(){
    var a = document.getAnimations().filter(function (x) { return x.effect && x.effect.target &&
      (x.effect.target.id === 'presence' || x.effect.target.id === 'orbit'); });
    return a.map(function (x) { var k = x.effect.getKeyframes(); var t = x.effect.getTiming();
      return { id: x.effect.target.id, from: k[0].transform, to: k[k.length - 1].transform,
               easing: t.easing, duration: t.duration }; }); })()`);
  const st1 = await page.json(`({now: __galaxy.stage.now, why: __galaxy.stage.why, turns: __galaxy.stage.turns,
    turnMs: __galaxy.stage.turnMs, micEar: document.getElementById('mic').classList.contains('ear'),
    ease: getComputedStyle(document.documentElement).getPropertyValue('--ease-panel-open').trim(),
    dur: getComputedStyle(document.documentElement).getPropertyValue('--dur-stage-flip').trim()})`);
  note('the turn: ' + JSON.stringify(flipping));
  const norm = (s) => String(s).replace(/\s+/g, '');
  ok(earUp && st1.micEar && st1.now === 'presence' && st1.why === 'the ear opened' &&
     st1.turns === st0.turns + 1 && flipping.length === 2 &&
     flipping.every((f) => /rotateY/.test(f.from) && norm(f.easing) === norm(st1.ease)) &&
     Math.abs(flipping[0].duration * 2 - st1.turnMs) <= 1,
     'THE ORBIT-TO-PRESENCE TURN FIRES ON THE REAL VOICE TRIGGER: a real click on the microphone ' +
     'opened the ear (#mic.ear), sealPaint() handed it to the stage ("' + st1.why + '"), and two ' +
     'rotateY halves of ' + flipping.map((f) => f.duration + 'ms').join(' + ') + ' ran on ' +
     flipping.map((f) => '#' + f.id).join(' and ') + ' on --ease-panel-open (' + st1.ease + '), the ' +
     'turn PR #4 named for a surface arriving', JSON.stringify({ st0, st1, flipping }));
  await click('#mic');
  const earDown = await waitFor(page, '__galaxy.ear.open === false', 8000);
  /* TIMED FROM THE MOMENT THE VOICE IS OFF - ear shut and nothing speaking - so the claim is the
     hold the constant promises and not "eventually". A 20s wait once hid a hold that restarted on
     every seal paint and took 6.6s; this is the assertion that would have caught it. */
  const quiet = await waitFor(page, '!__galaxy.stage.ear && !__galaxy.stage.speaking', 20000);
  const tq = Date.now();
  const back = quiet && await waitFor(page, '__galaxy.stage.now === "galaxy"', 10000);
  const backMs = Date.now() - tq;
  const st2 = await page.json('({now: __galaxy.stage.now, why: __galaxy.stage.why, hold: __galaxy.stage.HOLD_MS,' +
    ' ear: __galaxy.ear.open, stageEar: __galaxy.stage.ear, speaking: __galaxy.stage.speaking,' +
    ' status: document.getElementById("status").className, mic: document.getElementById("mic").className})');
  ok(earDown && back && st2.why === 'the voice ended' && backMs <= st2.hold + 1000,
     'and when the ear closes the pane turns back to the galaxy ' + backMs + 'ms after the voice went ' +
     'quiet - the ' + st2.hold + 'ms hold, within a second ("' + st2.why + '")',
     JSON.stringify(Object.assign({ backMs: backMs }, st2)));
  await page.send('Emulation.clearDeviceMetricsOverride');
}

say('\n  ' + '-'.repeat(74));
if (failures.length) { say('  FAILED:'); failures.forEach((f) => say('    - ' + f.slice(0, 160))); }
say('\n  VERIFY ' + pass + '/' + (pass + fail) + ' ' + (fail ? 'FAIL' : 'PASS') + '\n');
process.exit(fail ? 1 : 0);
