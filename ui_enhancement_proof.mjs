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
 *      goes back to wearing its core afterwards.
 *
 * BASE_REV is the commit this mandate started from. It is named rather than read as HEAD
 * because once this round is committed HEAD IS the new stylesheet, and "no new hue since HEAD"
 * would compare the file with itself.
 *
 * Port 9246, its own throwaway profile, closed by profile and by port and never by title.
 */
import { spawn, spawnSync } from 'node:child_process';
import { mkdtempSync, existsSync, readFileSync } from 'node:fs';
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
  spawn(exe, ['--remote-debugging-port=' + PORT, '--user-data-dir=' + profile, '--headless=new',
    '--no-first-run', '--no-default-browser-check', '--window-size=1440,900',
    '--enable-unsafe-swiftshader', '--use-angle=swiftshader',
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
  ok(wash.op > 0.9 && wash.z === '2' && wash.pe === 'none',
     'AND THE SKY STEPPED BACK BEHIND IT: the summoned dim is at ' + wash.op + ' on layer ' + wash.z +
     ', pointer-events ' + wash.pe, JSON.stringify(wash));
  await page.evaluate('__galaxy.orbit.close()');
  ok(await waitFor(page, "!__galaxy.orbit.isOpen && getComputedStyle(document.getElementById('orbit')).visibility === 'hidden'", 3000),
     'and closing it takes it off the glass entirely - hidden, not merely transparent');

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
  await waitFor(page, WASH + ' === 0', 8000);
  const after = await page.json(WASH);
  ok(before === 0 && during > 0.5 && after === 0,
     'AND THE GALAXY DIMS BEHIND AN OPEN COMMAND PANEL and comes back when it shuts: ' +
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
  await page.evaluate('__galaxy.presence.set("core")');
  ok(await waitFor(page, '__galaxy.presence.mode === "core"', 15000),
     'and the deck goes back to wearing its core, which is §32\'s default and stays it');

  step('5 · the sound, in two families');
  const au = await page.json('({family: __galaxy.audio.family, structure: __galaxy.audio.structure, played: __galaxy.audio.played})');
  ok(au.family && au.family.cool.indexOf('glass') >= 0 && au.family.warm.indexOf('wake') >= 0 &&
     Array.isArray(au.structure),
     'THE CHIMES ARE SORTED INTO THE SAME TWO FAMILIES: warm ' + JSON.stringify(au.family.warm) +
     ' for the presence acting, cool ' + JSON.stringify(au.family.cool) + ' for a surface arriving - ' +
     'and the cool cues keep their own ring, so they can never push the wake out of the one ' +
     'deck_proof reads', JSON.stringify(au));
}

say('\n  ' + '-'.repeat(74));
if (failures.length) { say('  FAILED:'); failures.forEach((f) => say('    - ' + f.slice(0, 160))); }
say('\n  VERIFY ' + pass + '/' + (pass + fail) + ' ' + (fail ? 'FAIL' : 'PASS') + '\n');
process.exit(fail ? 1 : 0);
