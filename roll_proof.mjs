/* roll_proof.mjs - §32 PART 0's FOUR CLAIMS, machine-checked.
 *
 * The mandate's words: "Assert with plates at 1280/1366/1600: the bottom-bar pill contains
 * every icon including refresh and slash with ear/seal chips armed; no white strip below the
 * app at any height; long single-line errors keep the card max-width; palette rows, letters
 * and behaviour as pre-§31."
 *
 * The plates are in _runs/plates32.mjs and they are for the boss's eye. This file is the half
 * a machine can settle, and it exists because the three interesting failures here are all
 * invisible at the size an eye reads a screenshot: a ring clipped by two pixels, a strip three
 * pixels tall, a card eight pixels past its max-width. Nothing in here is a picture.
 *
 * FOUR SECTIONS, one per claim:
 *   1. THE PILL. Every control in the bottom bar - screen, eye, focus, scribe, mic, REFRESH,
 *      SLASH - inside the pill's own box, at all three widths, twice: once as the bar sits at
 *      rest and once with the ear/seal chips FORCED ON. The forcing is the point. Those three
 *      chips are the only thing in the bar whose width is not constant, they are exactly what
 *      appears when a conversation opens, and a pill that contains its icons only while the
 *      seal says READY is a pill that breaks the moment somebody talks to it.
 *   2. NO STRIP. At five heights per width: the document does not scroll vertically, the page
 *      root's own background is dark rather than pale, and the bottom row of the viewport
 *      belongs to the deck. The pixel half of this claim is in _runs/rowscan.py, which reads
 *      the strip plates; this half is the cause rather than the symptom.
 *   3. THE ERROR CARD. A LONG SINGLE-LINE error - the shape a refused fetch actually arrives
 *      in - must leave the card at the same width a short answer does, and must not make
 *      anything scroll sideways.
 *   4. THE PALETTE, as pre-§31: eleven rows, the same eleven letters in the same order, no
 *      ORPHANED section heads, no selection hooks, the sheet header back to `ctrl+k · esc`, and
 *      arrow keys that move nothing. "Orphaned" and not "none": PART 2 was told to heal this
 *      sheet's readability and the mandate names section labels inside that heal, so the labels
 *      PART 2 builds from CMD_ACTS' own `sec` field are expected here - what is forbidden is a
 *      heading with no row under it, which is what §31's grouping left behind. See the
 *      assertion itself, which carries the full argument and the old assertion's name.
 *
 * Headless, one temp profile, port 9299, killed by that profile's basename. It never touches
 * 9222 - that is the boss's own browser.
 */
import { spawn, spawnSync } from 'node:child_process';
import { mkdtempSync, rmSync, existsSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, basename } from 'node:path';

const PORT = 9299;                        // plates32 took 9298, eyeprobe 9297
const CDP = 'http://127.0.0.1:' + PORT;
const GALAXY = 'http://127.0.0.1:4700';
const WIDTHS = [[1280, 800], [1366, 768], [1600, 900]];
const HEIGHTS = [600, 665, 720, 860, 1080];
/* The seven controls the mandate counts, in document order, with REFRESH and SLASH named
   last because they are the two it calls out - they are the two at the end of the row and
   therefore the two an overflowing pill loses first. */
const ORGANS = ['screen', 'eye', 'focusbtn', 'scribebtn', 'mic', 'reset', 'slash'];
/* Pre-§31's palette, read out of _runs/sweep32/roll/HEAD-index.html:6118 rather than
   remembered. §31 did not add or remove a row - it grouped them - so this list is the same
   in both trees and the assertion is about ORDER and LETTERS surviving the ungrouping. */
const HEAD_ROWS = [['focus', 'F'], ['lock', 'L'], ['links', 'S'], ['presence', 'P'],
  ['archive', 'A'], ['google', 'G'], ['connectors', 'C'], ['cast', 'V'], ['clock', 'T'],
  ['census', 'Q'], ['voice', 'W']];
const HEAD_HINT = 'ctrl+k · esc';

const LONG_ERR = 'I could not reach the model, sir: the request to the router at ' +
  '127.0.0.1 was refused after 30 seconds with no reply at all, which usually means the ' +
  'server is not running or a second copy of it is holding the port, and until one of those ' +
  'two is true again there is nothing I can answer from the web - though your own notes are ' +
  'still here and still searchable, so ask me from them instead.';
const SHORT_OK = 'The tree came down on the Sunday, sir, and the decision with it.';

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let checks = 0;
const bad = [];
const ok = (c, claim, detail) => {
  checks++;
  console.log((c ? '  ok   ' : '  FAIL ') + claim);
  if (!c) { bad.push(claim); if (detail) console.log('         ' + detail); }
};
const note = (s) => console.log('       · ' + s);

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
  constructor(u) { this.u = u; this.id = 0; this.w = new Map(); }
  open() {
    return new Promise((res, rej) => {
      this.ws = new WebSocket(this.u);
      this.ws.onopen = () => res(this);
      this.ws.onerror = (e) => rej(new Error('socket: ' + (e.message || 'failed')));
      this.ws.onmessage = (ev) => {
        const m = JSON.parse(ev.data);
        const f = this.w.get(m.id);
        if (f) { this.w.delete(m.id); f(m); }
      };
    });
  }
  send(method, params) {
    const id = ++this.id;
    return new Promise((res, rej) => {
      const bomb = setTimeout(() => {
        this.w.delete(id); rej(new Error(method + ' timed out'));
      }, 30000);
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
  async json(e) {
    return JSON.parse(await this.evaluate('JSON.stringify(' + e + ')') || 'null');
  }
  async key(k, code, vk) {
    for (const type of ['keyDown', 'keyUp']) {
      await this.send('Input.dispatchKeyEvent',
        { type, key: k, code, windowsVirtualKeyCode: vk, nativeVirtualKeyCode: vk });
    }
  }
}
const cdp = async (p) => {
  const t = await (await fetch(CDP + p)).text();
  try { return JSON.parse(t); } catch { return t; }
};

/* THE BAR, MEASURED. The pill's PADDING box is the container - a control is contained when
   it sits inside the box the pill actually paints, and the pill paints its border. Rounded
   corners are handled by a corner inset rather than by hope: at the two ends of a 26px-radius
   pill the usable height is less than the pill's, so a control whose centre is within one
   radius of an end must ALSO clear the arc. That is what `arc` reports. */
const barJs = (armBody) => '(function(){' +
  armBody +
  'function box(el){var r=el.getBoundingClientRect();' +
  'return {l:r.left,t:r.top,r:r.right,b:r.bottom,w:r.width,h:r.height};}' +
  'var bar=document.getElementById("bar"); var bb=box(bar);' +
  'var cs=getComputedStyle(bar);' +
  /* THE EFFECTIVE RADIUS, and the clamp is not a nicety. This bar's radius is written 999px -
     the ordinary way to say "a pill, whatever height you end up being" - and CSS resolves that
     against the box: a corner radius can never exceed half the side it sits on. Run 1 of this
     harness took the 999 literally, which inverted every clamp below and reported all seven
     organs 200-370px outside a pill they were comfortably inside. Failure mode if it comes
     back: fourteen loud reds per width that are a harness bug wearing a layout bug's clothes. */
  'var rad=parseFloat(cs.borderTopLeftRadius)||0;' +
  'rad=Math.min(rad,bb.w/2,bb.h/2);' +
  'var cx=(bb.l+bb.r)/2, cy=(bb.t+bb.b)/2;' +
  'var seal=document.getElementById("seal");' +
  'var out={bar:bb,radius:rad,radiusAsWritten:cs.borderTopLeftRadius,overflow:cs.overflow,' +
  ' scrollW:bar.scrollWidth,clientW:bar.clientWidth,' +
  ' sealW:Math.round(seal.getBoundingClientRect().width),' +
  ' chips:["seal-ear","seal-who","seal-study"].map(function(id){' +
  '   var e=document.getElementById(id);' +
  '   return e&&getComputedStyle(e).display!=="none" ? (e.textContent||"").trim() : null;}),' +
  ' organs:{}};' +
  'IDS.forEach(function(id){var el=document.getElementById(id);' +
  ' if(!el){out.organs[id]=null;return;}' +
  ' var b=box(el); var vis=getComputedStyle(el).display!=="none";' +
  /* THE ARC TEST. Treat the pill as a stadium: inside the two end caps the boundary is a
     circle of radius `rad` centred one radius in from the end. A control corner outside that
     circle is a corner the pill clips, even though the rectangle test passed. */
  ' var kx=Math.min(Math.max(b.l,bb.l+rad),bb.r-rad);' +
  ' var far=0;' +
  ' [[b.l,b.t],[b.r,b.t],[b.l,b.b],[b.r,b.b]].forEach(function(p){' +
  '   var ax=Math.min(Math.max(p[0],bb.l+rad),bb.r-rad);' +
  '   var ay=Math.min(Math.max(p[1],bb.t+rad),bb.b-rad);' +
  '   var d=Math.sqrt((p[0]-ax)*(p[0]-ax)+(p[1]-ay)*(p[1]-ay));' +
  '   if(d>far) far=d;});' +
  ' out.organs[id]={box:b,vis:vis,' +
  '   inL:b.l>=bb.l-0.5, inR:b.r<=bb.r+0.5,' +
  '   inT:b.t>=bb.t-0.5, inB:b.b<=bb.b+0.5,' +
  '   arc:Math.round((far-rad)*100)/100, kx:Math.round(kx)};' +
  '});' +
  'return out;})()';

const armOne = (id, text) =>
  'var e=document.getElementById(' + JSON.stringify(id) + ');' +
  'if(e){e.classList.add("on");e.textContent=' + JSON.stringify(text) + ';}';

/* ARMING, and it is done by hand on purpose. These three chips are shown by a class the
   page adds when a conversation opens, a speaker is named and a study is filed; driving
   all three for real would mean a microphone, a doorman decision and a syllabus run inside
   a layout harness. The claim being tested is GEOMETRY - does the pill still hold its icons
   when the seal is at its widest - so the widest seal is manufactured and said to be
   manufactured. Failure mode of the alternative (measuring only the resting bar): green
   here and a clipped slash the first time somebody speaks.

   AND IT IS DONE IN THE SAME EXPRESSION AS THE MEASUREMENT. Run 2 of this harness armed the
   seal, slept, and then measured - and the 1366 block came back 52px tall with the chips
   gone, reading green while the 1280 and 1600 blocks read red at the same code. The page's
   own seal painter runs on a timer and rewrites exactly these three cells, so a sleep
   between the arming and the reading is a race the page wins about a third of the time. Arm
   and measure inside one synchronous task and no repaint can get between them; the reading
   returns the seal width and the three chips so a silently-disarmed measurement cannot pass
   for a passing one. */
const ARM = 'document.getElementById("seal").classList.add("open");' +
  armOne('seal-who', 'BOSS') +
  armOne('seal-study', 'FILED') +
  '(function(){var t=document.getElementById("seal-text");' +
  ' if(t) t.textContent="LISTENING";})();';
const DISARM = '(function(){' +
  'document.getElementById("seal").classList.remove("open");' +
  '["seal-who","seal-study"].forEach(function(id){' +
  ' var e=document.getElementById(id); if(e){e.classList.remove("on");e.textContent="";}});' +
  'var t=document.getElementById("seal-text"); if(t) t.textContent="ready";' +
  'return true;})()';

/* THE PAGE ROOT'S OWN LIGHT. A white strip below the app is, in every shape it can take,
   some ancestor's background showing through - so both roots are read, as rendered, and
   turned into one luminance figure. */
const ROOT_JS = '(function(){' +
  'function lum(c){var m=/rgba?\\(([^)]+)\\)/.exec(c);if(!m) return null;' +
  ' var p=m[1].split(",").map(parseFloat);' +
  ' if(p.length>3&&p[3]===0) return 0;' +
  ' return Math.round((0.2126*p[0]+0.7152*p[1]+0.0722*p[2])*10)/10;}' +
  'var h=getComputedStyle(document.documentElement), b=getComputedStyle(document.body);' +
  'return {docScrollH:document.documentElement.scrollHeight,' +
  ' docClientH:document.documentElement.clientHeight,' +
  ' docScrollW:document.documentElement.scrollWidth,' +
  ' docClientW:document.documentElement.clientWidth,' +
  ' innerH:window.innerHeight, innerW:window.innerWidth,' +
  ' htmlOverflow:h.overflow, bodyOverflow:b.overflow,' +
  ' htmlLum:lum(h.backgroundColor), bodyLum:lum(b.backgroundColor),' +
  ' htmlBg:h.backgroundColor, bodyBg:b.backgroundColor,' +
  /* WHAT IS AT THE VERY BOTTOM. One pixel above the last row, at three columns, because a
     strip that only exists under the pill is still a strip. */
  ' atBottom:[0.08,0.5,0.92].map(function(f){' +
  '   var el=document.elementFromPoint(Math.round(window.innerWidth*f),' +
  '     window.innerHeight-1);' +
  '   return el ? (el.id || el.tagName.toLowerCase() + "." +' +
  '     (el.className||"").toString().split(" ")[0]) : null;})};})()';

const CARD_JS = '(function(){' +
  'var a=document.getElementById("answer");' +
  'var r=a.getBoundingClientRect(); var cs=getComputedStyle(a);' +
  'return {err:a.classList.contains("err"),' +
  ' w:Math.round(r.width*100)/100, l:Math.round(r.left), rt:Math.round(r.right),' +
  ' h:Math.round(r.height), maxW:cs.maxWidth,' +
  ' scrollW:a.scrollWidth, clientW:a.clientWidth,' +
  ' docScrollW:document.documentElement.scrollWidth,' +
  ' docClientW:document.documentElement.clientWidth};})()';

const PAL_JS = '(function(){' +
  'var list=document.getElementById("cmd-list");' +
  'var rows=[].slice.call(list.querySelectorAll("button.cmdact")).map(function(b){' +
  ' return [b.id.replace(/^cmd-/,""),' +
  '   ((b.querySelector(".ck")||{}).textContent||"").trim()];});' +
  'var g=window.__galaxy&&__galaxy.cmd;' +
  /* SECTION HEADS, found by what they ARE rather than by the class §31 gave them: any child
     of the list that is not one of the rows. A rollback that renamed the class instead of
     removing the element would pass a class-name test. */
  'var strayEls=[].slice.call(list.children).filter(function(el){' +
  ' return !(el.tagName==="BUTTON"&&el.classList.contains("cmdact"));});' +
  'var stray=strayEls.map(function(el){return el.tagName.toLowerCase()+"."+' +
  '   ((el.className||"").toString().split(" ")[0]||"")+":"+' +
  '   (el.textContent||"").trim().slice(0,24);});' +
  /* AND WHAT EACH ONE IS, not merely that it is there. See the assertion this feeds: a heading
     that labels the row under it is a different object from a heading left over from a grouping
     that no longer exists, and the four facts below are how they are told apart - the class it
     was built with, that it is hidden from the reader who cannot see it, that it is not a Tab
     stop, and that a row follows it. An orphan fails the last one. */
  'var strayFacts=strayEls.map(function(el){' +
  ' var n=el.nextElementSibling;' +
  ' return {cls:el.classList.contains("cmdsec"),' +
  '  hidden:el.getAttribute("aria-hidden")==="true", tab:el.tabIndex,' +
  '  labels:!!(n&&n.tagName==="BUTTON"&&n.classList.contains("cmdact")),' +
  '  text:(el.textContent||"").trim()};});' +
  'var stops=[].slice.call(list.querySelectorAll("*")).filter(function(el){' +
  ' return el.tabIndex>=0;}).length;' +
  'return {rows:rows, stray:stray, strayFacts:strayFacts, stops:stops,' +
  ' hint:((document.getElementById("cmd-hint")||{}).textContent||"").trim(),' +
  ' hasGroups:!!(g&&g.groups), hasSelect:!!(g&&g.select), hasStep:!!(g&&g.step),' +
  ' selField:(g&&"sel" in g)?String(g.sel):"(absent)",' +
  ' armed:[].slice.call(list.querySelectorAll(".cmdact")).filter(function(b){' +
  '   return b.classList.contains("on")||b.classList.contains("sel")||' +
  '     b.getAttribute("aria-selected")==="true";}).map(function(b){return b.id;})};})()';

const profile = mkdtempSync(join(tmpdir(), 'rollproof-'));
let chrome = null;
function shut() {
  if (chrome) { try { chrome.kill(); } catch { /* ignore */ } }
  /* PROFILE-SCOPED, never by window title: the one Chrome on this machine that must
     survive every harness is the boss's own on 9222. */
  spawnSync('powershell.exe', ['-NoProfile', '-Command',
    'Get-CimInstance Win32_Process | Where-Object { $_.Name -eq \'chrome.exe\' -and ' +
    '$_.CommandLine -match \'' + basename(profile) + '\' } | ' +
    'ForEach-Object { taskkill /PID $_.ProcessId /F | Out-Null }'],
    { encoding: 'utf8', timeout: 30000 });
}

async function main() {
  /* A PORT THIS RUN DID NOT OPEN IS A BROWSER THIS RUN CANNOT TRUST. eyes_live spent three
     runs asserting about a previous run's Chrome because it skipped this. */
  let squatter = null;
  try {
    const r = await fetch(CDP + '/json/version', { signal: AbortSignal.timeout(2000) });
    squatter = (await r.json()).Browser || 'something';
  } catch { /* silence is the only acceptable state */ }
  if (squatter) {
    throw new Error('port ' + PORT + ' is already held by ' + squatter + ' - this run will ' +
      'not measure a browser it did not launch. Close it and re-run (a leftover from this ' +
      'harness is killable by its temp profile: rollproof-*).');
  }

  chrome = spawn(chromeExe(), [
    '--remote-debugging-port=' + PORT, '--user-data-dir=' + profile,
    '--no-first-run', '--no-default-browser-check', '--headless=new',
    '--disable-features=CalculateNativeWinOcclusion',
    '--disable-backgrounding-occluded-windows', '--disable-renderer-backgrounding',
    '--force-device-scale-factor=1',
    /* NO --hide-scrollbars, and that is deliberate. A scrollbar is one of the two ways a
       strip appears at the bottom of this app, and a flag that hides it would hide the
       evidence. The plates harness does hide them, because a plate of a scrollbar is a
       plate of Chrome. */
    '--window-size=1600,1080', '--new-window', GALAXY,
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
  await page.evaluate('window.IDS = ' + JSON.stringify(ORGANS) + ', 1');
  await sleep(7000);                      // the boot ceremony
  console.log('\n  chrome ' + ((await cdp('/json/version')).Browser || '?'));

  for (const [w, h] of WIDTHS) {
    await page.send('Emulation.setDeviceMetricsOverride',
      { width: w, height: h, deviceScaleFactor: 1, mobile: false });
    await sleep(1500);
    /* IDS is set on the page, and a device-metrics override does not reload - but a harness
       that assumed that once and was wrong reads as a null organ, so it is re-set. */
    await page.evaluate('window.IDS = ' + JSON.stringify(ORGANS) + ', 1');
    await page.evaluate('__galaxy.cmd.open_(false); __galaxy.say("", "", false, null)');
    await sleep(700);
    console.log('\n  ---- ' + w + 'x' + h + ' ----');

    /* ---- 1. THE PILL ---------------------------------------------------------------- */
    for (const armed of [false, true]) {
      const b = await page.json(barJs(armed ? ARM : ''));
      const tag = armed ? ' with the chips armed' : ' at rest';
      note('#bar ' + JSON.stringify(b.bar).replace(/"/g, '') + ' radius=' + b.radius +
           ' (written ' + b.radiusAsWritten + ') overflow=' + b.overflow +
           ' scroll=' + b.scrollW + '/' + b.clientW +
           ' seal=' + b.sealW + 'px chips=' + JSON.stringify(b.chips));
      /* THE ARMING IS ITSELF ASSERTED. Without this, a page change that stopped the chips
         showing would turn the fourteen checks below into fourteen greens about a bar
         nobody is stressing. */
      ok(armed ? b.chips.every((c) => c) : true,
        armed ? 'all three seal chips really are showing at ' + w + ': ' +
          JSON.stringify(b.chips) + ', seal ' + b.sealW + 'px'
          : 'the bar at rest has the seal it always has: ' + b.sealW + 'px, chips ' +
            JSON.stringify(b.chips),
        'failure mode: the page\'s seal painter wins the race and the chips are measured ' +
        'closed, so the widest bar this app can have is never tested. ' + JSON.stringify(b));
      for (const id of ORGANS) {
        const o = b.organs[id];
        const inside = !!o && o.vis && o.inL && o.inR && o.inT && o.inB && o.arc <= 0.5;
        ok(inside, '#' + id + ' is inside the pill' + tag,
          'failure mode: the bar is a flex row with no wrap, so the control that leaves the ' +
          'pill is the LAST one - refresh and slash - and it leaves by being clipped rather ' +
          'than by moving, which is why this is measured and not looked at. ' +
          JSON.stringify(o));
      }
      ok(b.scrollW <= b.clientW + 1,
        'and the pill itself does not scroll sideways' + tag + ': scrollWidth ' + b.scrollW +
        ' vs clientWidth ' + b.clientW,
        'failure mode: overflow:hidden turns an overflowing row into a row that LOOKS fine ' +
        'and has a control nobody can reach. ' + JSON.stringify(b));
      if (armed) { await page.evaluate(DISARM); await sleep(400); }
    }

    /* ---- 3. THE ERROR CARD ---------------------------------------------------------- */
    await page.evaluate('__galaxy.say("what did the tree meeting decide", ' +
      JSON.stringify(SHORT_OK) + ', false, null)');
    await sleep(2200);
    const shortCard = await page.json(CARD_JS);
    await page.evaluate('__galaxy.say("what did the tree meeting decide", ' +
      JSON.stringify(LONG_ERR) + ', true, null)');
    await sleep(2800);
    const errCard = await page.json(CARD_JS);
    note('short answer ' + JSON.stringify(shortCard));
    note('long error   ' + JSON.stringify(errCard));
    ok(errCard.err === true,
      'the long message really is rendered as an error (#answer has class err)',
      'failure mode: if it is not an error card then the next two checks are measuring the ' +
      'ordinary card and the claim is untested. ' + JSON.stringify(errCard));
    ok(Math.abs(errCard.w - shortCard.w) <= 1,
      'a long single-line error keeps the card at the width a short answer has: ' +
      errCard.w + 'px vs ' + shortCard.w + 'px (max-width ' + errCard.maxW + ')',
      'failure mode: one unbroken line sets the card\'s intrinsic width, the max-width is ' +
      'expressed in a unit that does not bind it, and the card grows to the sentence - which ' +
      'is the reported ugliness. ' + JSON.stringify({ short: shortCard, err: errCard }));
    ok(errCard.scrollW <= errCard.clientW + 1 &&
       errCard.docScrollW <= errCard.docClientW + 1,
      'and nothing scrolls sideways because of it: card ' + errCard.scrollW + '/' +
      errCard.clientW + ', document ' + errCard.docScrollW + '/' + errCard.docClientW,
      'failure mode: the card holds its width and the TEXT overflows it instead, which looks ' +
      'like a fix and reads like a bug. ' + JSON.stringify(errCard));
    await page.evaluate('__galaxy.say("", "", false, null)');
    await sleep(400);

    /* ---- 4. THE PALETTE, AS PRE-§31 -------------------------------------------------- */
    await page.evaluate('__galaxy.cmd.open_(true)');
    await sleep(800);
    const p = await page.json(PAL_JS);
    note('palette ' + JSON.stringify(p));
    ok(p.rows.length === HEAD_ROWS.length &&
       p.rows.every((r, i) => r[0] === HEAD_ROWS[i][0]),
      'the palette has pre-§31\'s ' + HEAD_ROWS.length + ' rows in pre-§31\'s order: ' +
      p.rows.map((r) => r[0]).join(' '),
      'failure mode: the rollback restores cmdBuild from HEAD but leaves a CMD_ACTS §31 ' +
      'reordered, and the sheet reads right while every muscle-memory row has moved. ' +
      JSON.stringify(p.rows));
    ok(p.rows.every((r, i) => r[1] === HEAD_ROWS[i][1]),
      'and pre-§31\'s letters on them: ' + p.rows.map((r) => r[1]).join(''),
      'failure mode: the letters are mnemonics, not shortcuts - nothing breaks when one is ' +
      'wrong, it is just a lie printed next to a row. ' + JSON.stringify(p.rows));
    /* REPLACES "no section heads left in the list: N non-row children" - one assertion for one,
       and the old name is here so the swap is findable from either side.
       WHY IT HAD TO BE REPLACED RATHER THAN SATISFIED. The old form forbade every non-row child
       of the list, and that was the right shape of question in PART 0's world: the only thing
       putting headings in this sheet was §31's regrouping, which PART 0 reverts, so "any heading
       at all" and "§31's headings" were the same set and the cheaper test was the honest one.
       PART 2 ends that. It names command-palette readability as a surface to HEAL and names
       "section labels" inside it, and the heal is built from a different mechanism: a `sec` field
       on the CMD_ACTS row that opens each group, emitted by cmdBuild immediately before that row.
       Eleven rows, three labels, and heal_proof already holds the readability half of the claim -
       the labels are aria-hidden, they are not Tab stops, the mono ramp is on them. So a literal
       reading of the old assertion would have had PART 0 delete what PART 2 was told to build,
       and the sweep would have gone green on a sheet the mandate asks for twice.
       WHAT IS ASSERTED INSTEAD IS THE PART OF IT PART 0 ACTUALLY OWNS: that no heading in this
       list is an ORPHAN. §31's failure mode was a label with nothing driving it - a heading for a
       group that had been removed from the data. PART 2's labels each sit immediately before the
       row they name, so `labels` is false for exactly the leftover the old test was hunting, and
       the count of Tab stops still equals the count of rows, so three headings did not make the
       list three stops longer to walk. Everything else about §31's palette is still forbidden by
       the four assertions around this one: the rows, their order, their letters, the header's key
       list, and the absence of groups/select/step/sel from __galaxy.cmd.
       FAILURE MODE IF THIS IS WEAKENED FURTHER: §31's grouping comes back one heading at a time,
       each one legibly labelling a row, and this assertion has nothing left to object to. That is
       what the row/letter/hook assertions beside it are for, and they are the ones to keep hard. */
    const orphans = (p.strayFacts || []).filter((s) => !s.cls || !s.hidden || s.tab >= 0 ||
                                                       !s.labels || !s.text);
    ok(orphans.length === 0 && p.stops === p.rows.length,
      p.stray.length === 0
        ? 'no headings in the list at all, and its ' + p.stops + ' Tab stops are its ' +
          p.rows.length + ' rows'
        : 'every heading left in the list labels the row under it - ' +
          (p.strayFacts || []).map((s) => JSON.stringify(s.text)).join(' ') +
          ' - and the ' + p.stops + ' Tab stops are still the ' + p.rows.length + ' rows, so ' +
          'PART 2\'s labels are here and §31\'s orphans are not',
      'failure mode: a section label survives with nothing under it - §31\'s headings removed ' +
      'from the data but still built - or a heading becomes focusable and makes the sheet ' +
      'longer to walk than it has rows. ' + JSON.stringify({ orphans: orphans,
        facts: p.strayFacts, stops: p.stops, rows: p.rows.length }));
    ok(p.hint === HEAD_HINT,
      'the sheet header is back to pre-§31\'s key list: ' + JSON.stringify(p.hint),
      'failure mode: the header still promises ↕ and ↵ after the selection code is gone, ' +
      'which is a shortcut advertised and not bound. got ' + JSON.stringify(p.hint));
    ok(!p.hasGroups && !p.hasSelect && !p.hasStep && p.selField === '(absent)',
      'and the §31 selection hooks are gone from __galaxy.cmd: groups/select/step/sel',
      'failure mode: the hooks survive the rollback and a harness written against them ' +
      'keeps passing, so the next sweep proves a palette that is no longer there. ' +
      JSON.stringify(p));
    /* BEHAVIOUR, and this is the one that needs a key rather than a reading: pre-§31's sheet
       binds ctrl+k and escape and nothing else, so ArrowDown must leave it exactly as it
       was. Dispatched twice, because a one-step selection could start at row 0 and look
       unchanged. */
    await page.key('ArrowDown', 'ArrowDown', 40);
    await page.key('ArrowDown', 'ArrowDown', 40);
    await sleep(500);
    const p2 = await page.json(PAL_JS);
    ok(p2.armed.length === 0 && p.armed.length === 0,
      'two ArrowDowns select nothing, as pre-§31: ' + JSON.stringify(p2.armed),
      'failure mode: the arrow handler outlives the selection painter, so the keys move an ' +
      'invisible cursor and Enter runs whatever it landed on. ' + JSON.stringify(p2));
    ok(p2.hint === p.hint && p2.rows.length === p.rows.length,
      'and the sheet is otherwise where it was after them',
      JSON.stringify({ before: p, after: p2 }));
    await page.evaluate('__galaxy.cmd.open_(false)');
    await sleep(400);

    /* ---- 2. NO STRIP, at five heights ----------------------------------------------- */
    for (const hh of HEIGHTS) {
      await page.send('Emulation.setDeviceMetricsOverride',
        { width: w, height: hh, deviceScaleFactor: 1, mobile: false });
      await sleep(1100);
      const r = await page.json(ROOT_JS);
      ok(r.docScrollH <= r.docClientH + 1 && r.innerH === hh,
        w + 'x' + hh + ': the app does not scroll vertically (' + r.docScrollH + ' vs ' +
        r.docClientH + ')',
        'failure mode: something is one rounding error taller than the viewport, the page ' +
        'gains a scroll, and the strip below the app is the page background under a document ' +
        'that is 3px too long. ' + JSON.stringify(r));
      ok(r.htmlLum !== null && r.bodyLum !== null &&
         r.htmlLum <= 40 && r.bodyLum <= 40 &&
         r.atBottom.every((x) => x !== null && x !== 'html' && x !== 'body'),
        w + 'x' + hh + ': and the bottom row of the glass is the deck, not the page under it' +
        ' (html lum ' + r.htmlLum + ', body lum ' + r.bodyLum + ', at bottom ' +
        JSON.stringify(r.atBottom) + ')',
        'failure mode: the deck stops short and the roots\' own background shows - which is ' +
        'exactly a white strip if a token made either of them pale. ' + JSON.stringify(r));
    }
    await page.send('Emulation.setDeviceMetricsOverride',
      { width: w, height: h, deviceScaleFactor: 1, mobile: false });
    await sleep(600);
  }

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
