/* clock_proof.mjs - THE WORLD CLOCK, AND WHETHER IT IS RIGHT.
 * =============================================================================================
 * WHAT MAKES A CLOCK HARD TO PROVE. Every other answer in this house can be checked against a
 * fixed string, a file on disk or a rule the server states out loud. A clock cannot: the right
 * answer changes every minute, so a fixture that says "it should say 15:40 in Tokyo" is wrong
 * sixty seconds after it is written, and the obvious repair - compute the expected answer with
 * the same code that produced it - proves nothing at all. A harness that asks worldclock.py what
 * time it is in Tokyo and then asks worldclock.py what time it ought to be in Tokyo has tested
 * that Python is deterministic.
 *
 * SO THE ORACLE IS NODE'S. `Intl.DateTimeFormat` with a timeZone reads V8's own bundled ICU
 * copy of the IANA database - a different database, shipped by a different project, parsed by
 * different code, in a different process. When the server says 15:40 in Tokyo and Node's ICU
 * says 15:40 in Tokyo, two independent implementations of the world's timezone rules agree, and
 * that is a real check. It also catches the one class of error that matters most here and is
 * invisible to any internal check: a DST transition the server's copy of the database has and
 * the world does not, or the reverse.
 *
 * THE FOUR CLAIMS THE MANDATE NAMES, and where each one is made:
 *   - three cities within a minute .............. section B, against Node's ICU
 *   - a date-line pair with opposite offsets .... section C, Apia (+13) and Pago Pago (-11)
 *   - a made-up city refused .................... section D
 *   - zero chips ................................ section E, through the real page
 *
 * WHY A MINUTE AND NOT A SECOND. The server reads its clock, composes, serialises and answers;
 * Node reads its clock afterwards. Those are two different instants and across the turn of a
 * minute they land on different minutes - legitimately. So the tolerance is stated in the claim
 * and the comparison is made on the whole INSTANT rather than on the printed digits: the two
 * readings are converted back to epoch milliseconds and required to be within 90 seconds. A
 * comparison of printed strings would have been flaky at 14:59:59.7 and I would have called it
 * a timezone bug.
 *
 * THE DATE LINE IS NOT AN EDGE CASE, IT IS THE FEATURE. Apia and Pago Pago are a hundred miles
 * apart and read the same minute on different DAYS. If the day offset were computed from the
 * hour difference - which is the shape the first implementation of anything like this takes -
 * both would come out the same, and the tile that says "tomorrow" would say it about the wrong
 * one. So the pair is asserted as a pair: same minute, opposite offset signs, different dates,
 * and day words that are not equal.
 *
 * NO BROWSER FOR SECTIONS A-D AND G. They are HTTP claims and can run beside anything. Sections
 * E and F need the page, so this harness is HEADED-free but does open one headless Chrome on its
 * own port; run it solo anyway, on the house rule, because a Chrome is a Chrome.
 *
 * Usage:  python server.py 2> server-trace.log   then   node clock_proof.mjs
 */
import { spawn } from 'node:child_process';
import { mkdtempSync, rmSync, existsSync, readFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const GALAXY = 'http://127.0.0.1:4700';
const VIEW = GALAXY + '/?mute=1';
const PORT = 9273;                       // nobody else's; see the port map in the lookbook
const CDP = 'http://127.0.0.1:' + PORT;
const LOG = (process.argv[2] || 'server-trace.log').replace(/^--log=/, '');
const CHROMES = [
  'C:/Program Files/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Google/Chrome/Application/chrome.exe',
  process.env.LOCALAPPDATA + '/Google/Chrome/Application/chrome.exe',
];
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let checks = 0; const bad = [];
const ok = (c, claim, detail) => {
  checks++; console.log((c ? '  ok   ' : '  FAIL ') + claim);
  if (!c) { bad.push(claim); if (detail) console.log('         ' + detail); }
};
const note = (m) => console.log('  note ' + m);
const step = (m) => console.log('\n  ---- ' + m + ' ----\n');

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
      }, 20000);
      this.w.set(id, (m) => { clearTimeout(bomb); res(m); });
      this.ws.send(JSON.stringify({ id, method, params: params || {} }));
    });
  }
  async evaluate(expression, userGesture = false) {
    const r = await this.send('Runtime.evaluate',
      { expression, returnByValue: true, awaitPromise: true, userGesture });
    if (r.result && r.result.exceptionDetails) {
      throw new Error('page threw: ' + r.result.exceptionDetails.text);
    }
    return r.result && r.result.result ? r.result.result.value : undefined;
  }
  async json(e) { return JSON.parse(await this.evaluate('JSON.stringify(' + e + ')') || 'null'); }
  close() { try { this.ws.close(); } catch { } }
}
const cdp = async (p) => {
  const r = await fetch(CDP + p); const t = await r.text();
  try { return JSON.parse(t); } catch { return t; }
};
const get = async (path) => {
  const r = await fetch(GALAXY + path); const t = await r.text();
  try { return { status: r.status, body: JSON.parse(t) }; }
  catch { return { status: r.status, body: t }; }
};
const post = async (path, payload) => {
  const r = await fetch(GALAXY + path, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  const t = await r.text();
  try { return { status: r.status, body: JSON.parse(t) }; }
  catch { return { status: r.status, body: t }; }
};
async function waitFor(page, expr, ms = 8000) {
  for (let i = 0; i < ms / 200; i++) {
    try { if (await page.evaluate(expr)) return true; } catch { }
    await sleep(200);
  }
  return false;
}

/* ---- THE INDEPENDENT ORACLE -------------------------------------------------------------
   V8's ICU, which is not the database the server read. The parts are pulled out one at a time
   rather than formatted and parsed back, because a format string is a locale away from being
   day/month instead of month/day and I would rather the bug be impossible than tested for. */
function icuParts(zone, when) {
  const f = new Intl.DateTimeFormat('en-US', {
    timeZone: zone, year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false,
  });
  const out = {};
  for (const p of f.formatToParts(when)) if (p.type !== 'literal') out[p.type] = p.value;
  // 24:00 is how ICU spells midnight under hour12:false in some locales, and reading it as
  // hour 24 makes the epoch arithmetic below a day out exactly once a day.
  const hour = out.hour === '24' ? '00' : out.hour;
  return {
    date: out.year + '-' + out.month + '-' + out.day,
    hhmm: hour + ':' + out.minute,
    /* The wall clock in that zone, expressed as if it were UTC. Subtracting this from the real
       instant gives the zone's offset, which is how the offset is checked without asking
       either database for one. */
    asUTC: Date.UTC(+out.year, +out.month - 1, +out.day, +hour, +out.minute, +out.second),
  };
}

/* The server's own reading, likewise reduced to an instant-as-if-UTC, so the two can be
   compared as numbers instead of as strings. `iso` carries an offset, so this is exact. */
function rowAsUTC(row) {
  const m = /^(\d{4})-(\d\d)-(\d\d)T(\d\d):(\d\d):(\d\d)/.exec(String(row.iso || ''));
  if (!m) return null;
  return Date.UTC(+m[1], +m[2] - 1, +m[3], +m[4], +m[5], +m[6]);
}

const lookups = () => (!LOG || !existsSync(LOG)) ? null
  : (readFileSync(LOG, 'utf8').match(/^ *web lookup /gm) || []).length;

const profiles = []; const procs = [];

async function main() {
  console.log('\n  the world clock: a table on this disk, checked against a different one\n');

  /* ================== SECTION A: THE ROUTE ========================================== */
  step('A. the route answers, and says which database answered');
  const before = lookups();
  const r0 = await get('/clock');
  ok(r0.status === 200, 'GET /clock answers 200', String(r0.status));
  const c0 = r0.body || {};
  ok(c0.ok === true, 'and it is ready: there is a zone database on this machine',
     JSON.stringify(c0.why || c0));
  if (c0.ok !== true) {
    note('every remaining claim depends on a zone database; stopping here would hide the ' +
         'rest, so they run and will fail honestly');
  }
  ok(typeof c0.source === 'string' && c0.source.length > 0,
     'and it NAMES the database it read: ' + JSON.stringify(c0.source),
     'failure mode: a clock that silently fell back to a hand-written offset table would ' +
     'read identically right for six months and be an hour out every March');
  ok((c0.places | 0) >= 100,
     'it knows a working number of places: ' + c0.places,
     'failure mode: a table of six cities that answers "I do not know" to Paris is a ' +
     'refusal the employer reads as a broken feature');
  ok(c0.lookups === 0, 'and the route declares zero lookups', JSON.stringify(c0.lookups));
  ok(Array.isArray(c0.tiles) && c0.tiles.length >= 4,
     'the board has tiles: ' + (c0.tiles || []).length, JSON.stringify(c0.tiles || []));
  const homeRows = (c0.tiles || []).filter((t) => t.home);
  ok(homeRows.length === 1,
     'EXACTLY ONE of them is home, because every other tile\'s day is measured against it',
     JSON.stringify(homeRows.map((t) => t.place)));
  ok(homeRows.length === 1 && homeRows[0].dayOffset === 0,
     'and his own clock is nought days from itself, which is the only reading it can have');

  /* ================== SECTION B: THREE CITIES WITHIN A MINUTE ======================= */
  step('B. three cities, against a database this harness did not read from');
  /* Asked with ?at= so both sides are talking about ONE instant. Without it the server reads
     its clock, answers, and Node reads its clock afterwards - and the gap between those two
     reads is exactly the thing a tolerance has to absorb. Pinning the instant removes the
     tolerance from the comparison of OFFSETS and leaves it only where it belongs. */
  const pin = new Date();
  const pinISO = pin.toISOString().replace('Z', '+00:00');
  const rP = await get('/clock?at=' + encodeURIComponent(pinISO));
  ok(rP.status === 200 && rP.body && rP.body.ok === true,
     'the route takes a fixed instant, so this section is reproducible', String(rP.status));
  const pinned = ((rP.body || {}).tiles || []);
  const THREE = ['London', 'New York', 'Tokyo'];
  for (const city of THREE) {
    const row = pinned.find((t) => t.place === city);
    if (!row) { ok(false, 'the board carries ' + city, JSON.stringify(pinned.map(t => t.place))); continue; }
    const mine = icuParts(row.zone, pin);
    const theirs = rowAsUTC(row);
    const driftMin = theirs == null ? 1e9 : Math.abs(theirs - mine.asUTC) / 60000;
    ok(driftMin <= 1,
       city + ' agrees with Node\'s ICU to within a minute: server ' + row.hhmm +
       ' vs ICU ' + mine.hhmm + ' (' + driftMin.toFixed(2) + ' min apart)',
       'failure mode: two timezone databases disagreeing means one of them has a DST rule ' +
       'the world does not, and the wrong one is on this disk');
    ok(row.hhmm === mine.hhmm || driftMin <= 1,
       '  and the printed digits are the same clock: ' + row.hhmm + ' / ' + mine.hhmm);
    /* THE OFFSET IS CHECKED SEPARATELY FROM THE TIME, because a right time with a wrong
       declared offset is what the PAGE ticks on - see clockNowFor(). A board that showed the
       correct minute on open and then drifted an hour would pass a time-only check. */
    const icuOff = Math.round((mine.asUTC - pin.getTime()) / 60000);
    ok(Math.abs(icuOff - (row.offsetMinutes | 0)) <= 1,
       '  and the offset it hands the page is right: ' + row.offsetMinutes +
       ' vs ICU ' + icuOff + ' minutes',
       'failure mode: the page ticks its tiles from this number, so an offset that is 60 out ' +
       'shows the right time for one second and the wrong hour for as long as it is open');
  }

  /* ================== SECTION C: THE DATE LINE ===================================== */
  step('C. the date line: one minute, two days, opposite offsets');
  const apia = await post('/chat', { question: 'what time is it in Apia' });
  const pago = await post('/chat', { question: 'what time is it in Pago Pago' });
  const aP = (apia.body || {}), pP = (pago.body || {});
  ok(aP.clockPlace === 'Apia', 'Apia resolves', JSON.stringify(aP.clockPlace));
  ok(pP.clockPlace === 'Pago Pago', 'Pago Pago resolves', JSON.stringify(pP.clockPlace));
  /* Read at one pinned instant through the module, so the pair is a pair rather than two
     readings taken a second apart across a midnight. */
  const at2 = new Date();
  const a2 = icuParts('Pacific/Apia', at2);
  const p2 = icuParts('Pacific/Pago_Pago', at2);
  const aOff = Math.round((a2.asUTC - at2.getTime()) / 60000);
  const pOff = Math.round((p2.asUTC - at2.getTime()) / 60000);
  ok(aOff > 0 && pOff < 0,
     'their offsets have OPPOSITE SIGNS: Apia ' + aOff + ', Pago Pago ' + pOff + ' minutes',
     'if this ever stops being true the pair has stopped being a date-line pair and this ' +
     'section is testing nothing');
  ok(a2.hhmm === p2.hhmm,
     'and they read the SAME MINUTE: ' + a2.hhmm + ' both',
     'a hundred miles apart at thirteen and minus eleven is a twenty-four hour gap, which ' +
     'is the same wall clock: ' + a2.hhmm + ' / ' + p2.hhmm);
  ok(a2.date !== p2.date,
     'ON DIFFERENT DAYS: ' + a2.date + ' and ' + p2.date,
     'failure mode: a day offset derived from the hour difference makes these two identical, ' +
     'and the tile that says "tomorrow" then says it about the wrong island');
  const aSaid = String(aP.answer || ''), pSaid = String(pP.answer || '');
  const dayWord = (s) => (/\b(yesterday|tomorrow|today)\b/i.exec(s) || [''])[0].toLowerCase();
  ok(dayWord(aSaid) && dayWord(pSaid),
     'BOTH SENTENCES CARRY A DAY WORD: ' + JSON.stringify([dayWord(aSaid), dayWord(pSaid)]),
     'failure mode: a clock reading with the day left off is the half of the answer that ' +
     'causes the missed call');
  ok(dayWord(aSaid) !== dayWord(pSaid),
     'AND THEY ARE DIFFERENT DAY WORDS, which is the whole claim of this section: ' +
     JSON.stringify(aSaid) + ' / ' + JSON.stringify(pSaid));
  ok(/against your clock/i.test(aSaid) && /against your clock/i.test(pSaid),
     'and each says what the day is measured against, so "tomorrow" is not left to mean ' +
     'tomorrow in Samoa');

  /* ================== SECTION D: A MADE-UP CITY ==================================== */
  step('D. a place that does not exist is refused, and not approximated');
  const FAKE = ['Narnia', 'Zanzibar-on-Sea', 'Upper Fenwickshire', 'Gondor'];
  for (const word of FAKE) {
    const res = await post('/chat', { question: 'what time is it in ' + word });
    const b = res.body || {};
    const said = String(b.answer || '');
    ok(b.clock === true && b.clockPlace === '',
       word + ' is handled BY THE CLOCK and resolves to nothing - a refusal, not a miss: ' +
       JSON.stringify({ clock: b.clock, place: b.clockPlace }),
       'failure mode: falling through to the web means a search engine is asked what time ' +
       'it is in Narnia, and it will answer something');
    ok(/\bi do not know where\b/i.test(said),
       '  and it says so plainly: ' + JSON.stringify(said));
    ok(!/\b(\d{1,2}:\d\d|o'clock|noon|midnight)\b/i.test(said),
       '  WITH NO TIME IN THE REFUSAL: ' + JSON.stringify(said),
       'failure mode: a nearest-match guess reads exactly like a right answer, and a clock ' +
       'that is confidently in the wrong hemisphere is worse than no clock');
    ok(!/\b(did you mean|perhaps|probably|closest|assuming)\b/i.test(said),
       '  and offers no nearest match, which would be a guess wearing a question mark');
    ok((b.nodes || []).length === 0 && b.lookups === 0,
       '  and it cost nothing: 0 nodes, 0 lookups',
       JSON.stringify({ nodes: (b.nodes || []).length, lookups: b.lookups }));
  }

  /* ================== SECTION E: ZERO CHIPS, THROUGH THE PAGE ======================= */
  step('E. zero chips: a clock answer cites nothing, because it read nothing');
  const exe = CHROMES.find((p) => existsSync(p));
  if (!exe) throw new Error('no chrome.exe');
  const profile = mkdtempSync(join(tmpdir(), 'clockproof-'));
  profiles.push(profile);
  procs.push(spawn(exe, ['--headless=new', '--remote-debugging-port=' + PORT,
    '--user-data-dir=' + profile, '--no-first-run', '--no-default-browser-check',
    '--window-size=1280,900', VIEW], { detached: true, stdio: 'ignore' }));
  for (let i = 0; i < 80; i++) {
    try { await cdp('/json/version'); break; } catch { await sleep(250); }
  }
  let target = null;
  for (let i = 0; i < 40; i++) {
    const l = await cdp('/json/list');
    target = (Array.isArray(l) ? l : []).filter((t) => t.type === 'page')
      .find((t) => t.url.includes('mute=1'));
    if (target) break;
    await sleep(300);
  }
  if (!target) throw new Error('no viewer page');
  const page = new Page(target.webSocketDebuggerUrl);
  await page.open();
  await page.send('Runtime.enable');
  ok(await waitFor(page, '!!(window.__galaxy && window.__galaxy.ask)', 30000),
     'the viewer is up and will take a question');
  await waitFor(page, '__galaxy.nodes.length > 0', 20000);

  const beforeAsk = lookups();
  /* `void`, on chain_proof's rule: ask() resolves when the turn is over, and awaiting it here
     would make a slow answer look like a harness timeout rather than a slow answer. */
  await page.evaluate('void __galaxy.ask("what time is it in Tokyo")');
  await waitFor(page, 'document.getElementById("a-text").textContent.indexOf("Tokyo") >= 0',
                30000);
  await sleep(600);
  const shown = await page.json('(function(){return {' +
    'answer: document.getElementById("a-text").textContent.trim(),' +
    'chips: document.getElementById("a-chips").children.length,' +
    'src: getComputedStyle(document.getElementById("a-src")).display,' +
    'panelOpen: document.getElementById("panel").classList.contains("open")};})()');
  ok(/\bTokyo\b/.test(shown.answer), 'the page shows the clock answer: ' +
     JSON.stringify(shown.answer));
  ok(shown.chips === 0,
     'ZERO CHIPS: a clock answer cites nothing, because it read nothing',
     JSON.stringify(shown));
  ok(shown.src === 'none',
     'and the sources row is not shown at all - not shown-and-empty, which would be a ' +
     '"Drawn from" heading over nothing', JSON.stringify(shown.src));
  ok(shown.panelOpen === false,
     'and no note was opened beside it: the camera holds and the galaxy does not move to ' +
     'illustrate a subtraction');
  const afterAsk = lookups();
  ok(beforeAsk === null || afterAsk === beforeAsk,
     'AND THE SERVER LOGGED NO WEB LOOKUP for the whole turn: ' + beforeAsk + ' -> ' + afterAsk,
     'failure mode: before the clock class existed this exact sentence spent a real search - ' +
     'a round trip and a rate limit to compute a subtraction');

  /* ================== SECTION F: THE BOARD ========================================= */
  step('F. the board: live tiles, day-offset labels, and no ghost when it closes');
  const names = await page.json('__galaxy.cmd.board.names');
  ok(Array.isArray(names) && names.indexOf('clock') >= 0,
     'the panel registers a World Clock board: ' + JSON.stringify(names));
  const rowSays = await page.json('(function(){__galaxy.cmd.open_(true);' +
    'return __galaxy.cmd.rows.clock;})()');
  ok(!!rowSays, 'and it has a row in the order sheet', JSON.stringify(rowSays));
  ok(rowSays && rowSays.label === 'World Clock',
     'labelled for what it is: ' + JSON.stringify(rowSays && rowSays.label));
  await page.evaluate('__galaxy.cmd.run("clock")');
  ok(await waitFor(page, '__galaxy.cmd.view === "board"', 6000),
     'pressing it opens a board rather than doing something');
  ok(await waitFor(page, '__galaxy.cmd.board.tiles.length > 1', 12000),
     'which fills with tiles', JSON.stringify(await page.json('__galaxy.cmd.board.why')));
  const tiles = await page.json('__galaxy.cmd.board.tiles');
  const dom = await page.json('__galaxy.cmd.board.dom');
  ok(tiles.length >= 5, 'there are ' + tiles.length + ' tiles',
     JSON.stringify(tiles.map((t) => t.name)));
  ok(dom.length === tiles.length,
     'AND THE DOM HAS THE SAME NUMBER: ' + dom.length + ' rendered against ' + tiles.length +
     ' computed', 'failure mode: a board whose array and glass disagree is a board that is ' +
     'right in a harness and wrong on screen');
  const pairs = tiles.map((t, i) => [t, dom[i]]);
  ok(pairs.every(([t, d]) => d && d.name === String(t.name) && d.value === String(t.value)),
     'and each tile\'s NAME AND READING reached the cell it was computed for',
     JSON.stringify(pairs.filter(([t, d]) => !d || d.name !== String(t.name) ||
                                            d.value !== String(t.value))));
  ok(dom.every((d) => /^\d\d:\d\d$/.test(d.value)),
     'every tile shows a clock: ' + JSON.stringify(dom.map((d) => d.value)));
  const homeTiles = dom.filter((d) => d.home);
  ok(homeTiles.length === 1,
     'exactly one tile is marked as his own clock: ' + JSON.stringify(homeTiles.map(d => d.name)));
  /* THE DAY-OFFSET LABEL. The mandate asks for it by name. It is empty on a tile that is on
     the same day, which is correct and is why the assertion is about the tiles that DIFFER:
     a label reading "today" on six tiles out of seven is noise, and its absence is the
     information. */
  const offTiles = tiles.filter((t) => t.dayOffset !== 0);
  if (offTiles.length) {
    ok(offTiles.every((t) => /yesterday|tomorrow|^[+-]\d+d$/.test(String(t.tag || ''))),
       'every tile on a DIFFERENT DAY carries the word: ' +
       JSON.stringify(offTiles.map((t) => t.name + '=' + t.tag)));
    ok(offTiles.every((t) => {
      const d = dom.find((x) => x.name === String(t.name));
      return d && d.tag === String(t.tag);
    }), '  and the word reached the glass, not just the array');
  } else {
    /* NOT A SKIP AND NOT A PASS BY LUCK. At some hours every board tile is on the same day as
       home, and then there is nothing to assert - so the run says so, and asserts the thing
       that IS checkable: that no tile claims a day word it has not earned. */
    note('every board tile is on the same day as home at this hour; the day-word assertion ' +
         'has nothing to bite on, so the inverse is asserted instead');
    ok(dom.every((d) => !/yesterday|tomorrow/.test(String(d.tag || ''))),
       'no tile claims a day it has not earned: ' + JSON.stringify(dom.map((d) => d.tag)));
  }
  /* IT TICKS. Two reads a little over a minute apart would be the honest test and would cost
     a minute; instead the SECOND is read twice across a repaint, which proves the timer is
     running and repainting from the clock rather than from the payload. */
  const paints1 = await page.json('__galaxy.cmd.board.paints');
  await sleep(2400);
  const paints2 = await page.json('__galaxy.cmd.board.paints');
  ok(paints2 > paints1,
     'the board repaints on its own while it is open: ' + paints1 + ' -> ' + paints2,
     'failure mode: a clock that is correct when it opens and frozen thereafter looks right ' +
     'for the first minute somebody watches it');
  const readsBefore = await page.json('(function(){return __galaxy.cmd.board.read ? 1 : 0;})()');
  ok(readsBefore === 1, 'and it has the server\'s reading behind it');

  /* THE CANARY THE MANDATE ASKS FOR, in the shape the clock board can wear it: closing the
     board must leave NO TILE ANYWHERE in the document. The connectors board's own canary -
     a fake registry row - belongs to its own harness; this is the same law tested on the
     shared machinery both boards use. */
  await page.evaluate('__galaxy.cmd.board.close()');
  await sleep(400);
  const ghosts = await page.json('document.querySelectorAll("#board-grid .btile").length');
  ok(ghosts === 0,
     'CLOSING IT LEAVES NO GHOST: ' + ghosts + ' tiles remain in the document',
     'failure mode: a board that hides instead of emptying keeps a stale reading alive, and ' +
     'the next open shows last hour\'s clock for a frame');
  ok(await waitFor(page, '__galaxy.cmd.board.which === ""', 3000),
     'and the board forgets which one it was');
  const stillTicking = await page.json('__galaxy.cmd.board.paints');
  await sleep(1600);
  ok((await page.json('__galaxy.cmd.board.paints')) === stillTicking,
     'and the timer really stopped rather than repainting a hidden grid: ' + stillTicking,
     'failure mode: an interval left running behind a closed panel is a leak that costs a ' +
     'frame a second forever and is invisible until the deck audition fails');
  await page.evaluate('__galaxy.cmd.open_(false)');

  /* ================== SECTION G: THE CLASS IS NOT A DRAGNET ========================= */
  step('G. the clock does not take questions that are not about a clock');
  /* THE FAILURE THIS GUARDS AGAINST IS THE OPPOSITE OF A MISS. A protected class that grew
     until it caught "what time is it in Tokyo" can grow one word further and catch "what did
     I write about the time in Tokyo", which has an answer in his notes. Every sentence here
     has a different door, and the claim is only that it is not this one. */
  const NOTMINE = [
    'what did I write about Tokyo',
    'what time did I write that note',
    'how much time is left',
    'set a timer for ten minutes',
    'what is the difference between Tokyo and London',
    'schedule a meeting in Tokyo',
    'what is the weather in Tokyo',
    'who are you',
    'are you there',
    'what can you do',
  ];
  for (const q of NOTMINE) {
    const res = await post('/chat', { question: q });
    const b = res.body || {};
    ok(b.clock !== true,
       JSON.stringify(q) + ' is NOT a clock question (route=' + JSON.stringify(b.route) + ')',
       'failure mode: a dragnet class answers the wrong question confidently and for free, ' +
       'which is harder to notice than a slow right answer');
  }
  /* AND THE PHRASINGS THAT MUST HIT. The first draft of the pattern was written under
     re.VERBOSE, where a space inside an alternation is stripped, so `(?:'s| is)?` compiled to
     `(?:'s|is)?` - and "what is the time in Sydney" silently fell out of the class while
     "what time is it in Sydney" worked. Every one of these is here because that bug passed a
     test suite that only used the phrasing I happened to type first. */
  const MINE = [
    ['what time is it in Sydney', 'Sydney'],
    ['what is the time in Sydney', 'Sydney'],
    ["what's the time in Sydney", 'Sydney'],
    ['whats the time in sydney', 'Sydney'],
    ['time in sydney', 'Sydney'],
    ['what is the time in sydney right now', 'Sydney'],
    ['sydney time', 'Sydney'],
    ['what day is it in auckland', 'Auckland'],
    ['how late is it in berlin', 'Berlin'],
    ['time in tokyo japan', 'Tokyo'],
  ];
  for (const [q, want] of MINE) {
    const res = await post('/chat', { question: q });
    const b = res.body || {};
    ok(b.clock === true && b.clockPlace === want,
       JSON.stringify(q) + ' -> ' + want,
       'got ' + JSON.stringify({ clock: b.clock, place: b.clockPlace, route: b.route }));
  }
  const bare = await post('/chat', { question: 'what time is it' });
  ok((bare.body || {}).clock === true && (bare.body || {}).clockPlace === '',
     'and with no place in it at all he gets his OWN clock',
     JSON.stringify(bare.body || {}));
  ok(!/against your clock/i.test(String((bare.body || {}).answer || '')),
     '  with no day clause, because a day offset against himself is nought by construction',
     JSON.stringify((bare.body || {}).answer));

  /* ================== SECTION H: WHAT THE VOICE IS HANDED ========================== */
  step('H. the sentence is speakable');
  const tokyo = await post('/chat', { question: 'what time is it in Tokyo' });
  const line = String((tokyo.body || {}).answer || '');
  ok(/\d{1,2}:\d\d|o'clock|noon|midnight/.test(line),
     'the time is written as a clock, not as two loose numbers: ' + JSON.stringify(line),
     'failure mode: "3 30 in the afternoon" is read by a neural voice as "three, thirty" - ' +
     'two numbers - and the first draft of this module produced exactly that');
  ok(!/\b(dash|hyphen|ellipsis|utc[+-]|gmt[+-])\b/i.test(line),
     'and it hands the voice no name of a mark and no offset notation: ' + JSON.stringify(line));
  ok(!/\bnone\b|\bnull\b|\bundefined\b|NaN/.test(line),
     'and no value leaked into it that was meant for a machine');
  /* THE PLACE IS GIVEN BACK CAPITALISED even though the funnel's peel lower-cases everything,
     because "I do not know where narnia is" reads as a machine that did not recognise the
     word as a place name - a second and untrue claim on top of the true one. */
  const low = await post('/chat', { question: 'what time is it in narnia' });
  ok(/where Narnia is/.test(String((low.body || {}).answer || '')),
     'a refusal gives the place back capitalised, however he typed it: ' +
     JSON.stringify((low.body || {}).answer));

  page.close();
}

main().catch((e) => {
  bad.push('the run itself: ' + e.message);
  console.log('\n  ERROR ' + (e && e.stack || e));
}).finally(async () => {
  procs.forEach((p) => { try { process.kill(p.pid); } catch { } });
  await sleep(700);
  profiles.forEach((p) => { try { rmSync(p, { recursive: true, force: true }); } catch { } });
  console.log('\n  VERIFY ' + (checks - bad.length) + '/' + checks +
              (bad.length ? ' FAIL' : ' PASS') + '\n');
  bad.forEach((b) => console.log('    FAILED: ' + b));
  process.exit(bad.length ? 1 : 0);
});
