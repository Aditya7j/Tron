/* connectors_proof.mjs - THE CONNECTORS BOARD, AND THE ONE TILE THAT IS NOT THERE.
 * =============================================================================================
 * WHAT THIS BOARD IS FOR, AND WHY IT NEEDS A HARNESS OF ITS OWN. "Is my calendar connected" was
 * answerable three ways before this part - the grant row, a spoken sentence, the telemetry rail -
 * and none of the three said anything about the mail, the voice, the eyes or the Scribe. A grid
 * that answers the whole question is only worth having if every cell in it is READ rather than
 * remembered, and "read rather than remembered" is not visible in a screenshot. Hence this file.
 *
 * THE FOUR CLAIMS, and each names the failure it catches:
 *
 *   A. EVERY TILE AGREES WITH THE SERVER IT CLAIMS TO SPEAK FOR. The grant word on the Calendar
 *      tile is compared against GET /google, and the hand small-print against GET /tools. Failure
 *      mode: a board that cached CONNECTED at boot and kept saying it after the token died - which
 *      is the exact failure the grant row's own comment says the row was designed to avoid, and a
 *      new surface is a new chance to reintroduce it.
 *
 *   B. NOTION IS ON THE BOARD, AND SAYS IT IS NOT CONFIGURED. Failure mode: a connectors board
 *      that lists only what works is a brochure. The employer cannot ask for a thing he has no
 *      way of knowing is missing. This is asserted as a PRESENT tile with an honest word in it,
 *      and - the other half - with nothing anywhere in the house pretending to implement it.
 *
 *   C. NO TILE CAN RUN A HAND. Failure mode: the Halt Law says a registry script runs after a
 *      proposal and a human word. A grid cell wired to the executor would be a second door with
 *      no gate on it, and it would be the most natural thing in the world to add. Every hand tile
 *      is asserted to carry NO BUTTON AT ALL - not a disabled one, none - and the one button the
 *      board does have is asserted to be the grant's.
 *
 *   D. THE CANARY. A fake connector is planted in tools/registry.json, the board is reopened, and
 *      the tile must appear; the entry is removed, the board reopened, and NO GHOST may remain.
 *      Failure mode: a grid that is diffed against its previous contents rather than rebuilt, in
 *      which the one case that goes wrong is removal - so the removal is the test.
 *
 * THE CANARY WRITES A REAL FILE, AND THAT IS HANDLED CAREFULLY.
 *   - The original bytes are read first and written back in a `finally`, and the restoration is
 *     itself an assertion, so a harness that died half way says so in its own verdict line.
 *   - The planted entry names a script that DOES NOT EXIST, and that is asserted before planting.
 *     hands.py validates the filename's shape but not the file's existence, so the entry surfaces
 *     on the board - which is what is being tested - while remaining incapable of executing
 *     anything at all if something did reach for it.
 *   - Nothing is asked of the assistant while the canary is in the file, so it never reaches a
 *     prompt manifest.
 *
 * Usage:  python server.py 2> server-trace.log   then   node connectors_proof.mjs
 */
import { spawn } from 'node:child_process';
import { mkdtempSync, rmSync, existsSync, readFileSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { createHash } from 'node:crypto';
import { join } from 'node:path';

const GALAXY = 'http://127.0.0.1:4700';
const VIEW = GALAXY + '/?mute=1';
const PORT = 9274;                       // nobody else's; see the port map in the lookbook
const CDP = 'http://127.0.0.1:' + PORT;
const REGISTRY = 'tools/registry.json';
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
/* THE ACCOUNT NAME NEVER REACHES THIS LOG. The Gmail and Calendar tiles legitimately show the
   employer which mailbox the grant belongs to - that is his own glass, and the Google row has
   shown it since long before this board existed. A harness log is a different object: it is
   pasted into terminal reports and quoted in the lookbook, and the standing rule is that an
   account email appears in those only as a digest. So every tile string this file prints goes
   through here first, and the digest is stable, so two runs can still be compared. */
const safe = (s) => String(s === undefined || s === null ? s : s).replace(
  /[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/g,
  (m) => 'sha256:' + createHash('sha256').update(m).digest('hex').slice(0, 12));
const show = (v) => safe(JSON.stringify(v));
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
async function waitFor(page, expr, ms = 8000) {
  for (let i = 0; i < ms / 200; i++) {
    try { if (await page.evaluate(expr)) return true; } catch { }
    await sleep(200);
  }
  return false;
}

/* Open the board, wait for its read to land, and hand back both halves at once - the array the
   page computed and the cells it actually rendered. Every section below reads them as a pair,
   because a board that put the right word in the wrong cell is a board that passes on one. */
async function openBoard(page, name, wantAtLeast) {
  await page.evaluate('__galaxy.cmd.open_(true)');
  await page.evaluate('__galaxy.cmd.run(' + JSON.stringify(name) + ')');
  await waitFor(page, '__galaxy.cmd.board.which === ' + JSON.stringify(name), 6000);
  await waitFor(page, '__galaxy.cmd.board.read !== null', 12000);
  /* One more paint after the read lands, so the grid is built from the answer and not from the
     empty state the board deliberately paints first. */
  await page.evaluate('__galaxy.cmd.board.paint()');
  if (wantAtLeast) {
    await waitFor(page, '__galaxy.cmd.board.dom.length >= ' + wantAtLeast, 6000);
  }
  return {
    tiles: await page.json('__galaxy.cmd.board.tiles'),
    dom: await page.json('__galaxy.cmd.board.dom'),
    head: await page.json('__galaxy.cmd.board.head'),
    row: await page.json('(function(){return __galaxy.cmd.rows.connectors;})()'),
  };
}
const byName = (rows, name) => rows.filter((t) => String(t.name) === name)[0] || null;

const profiles = []; const procs = [];
let original = null;                     // the registry's own bytes, restored in `finally`

async function main() {
  console.log('\n  the connectors board: six readings, the hands from a file, and one absence\n');

  /* ================== THE SERVER'S SIDE, BEFORE THE PAGE IS ASKED ==================== */
  step('A. what the server says, so the board can be checked against it rather than itself');
  const g0 = await get('/google');
  ok(g0.status === 200, 'GET /google answers', String(g0.status));
  const grant = g0.body || {};
  ok(typeof grant.state === 'string',
     'and it carries a state word: ' + JSON.stringify(grant.state), JSON.stringify(grant));
  /* THE PRIVACY CLAUSE, asserted here rather than assumed: this harness prints the grant it
     compares against, so if a token ever appeared in that payload it would appear in this log. */
  const grantText = JSON.stringify(grant);
  ok(!/"(access|refresh)_?[Tt]oken"|"client_secret"/.test(grantText),
     'and NO TOKEN OR SECRET is in the payload this board reads',
     'failure mode: the board is a new reader of /google, and a route that started carrying a ' +
     'token would put it on a grid, in a screenshot, in a lookbook');
  const t0 = await get('/tools');
  ok(t0.status === 200, 'GET /tools answers', String(t0.status));
  const hands0 = ((t0.body || {}).tools || []);
  ok(hands0.length > 0, 'and the registry has ' + hands0.length + ' validated hand(s): ' +
     JSON.stringify(hands0.map((t) => t.id)));
  ok(hands0.every((t) => !('script' in t) && !('triggers' in t)),
     'with no script path and no trigger in what the page is allowed to see',
     JSON.stringify(Object.keys(hands0[0] || {})));

  /* ================== THE PAGE ====================================================== */
  const exe = CHROMES.find((p) => existsSync(p));
  if (!exe) throw new Error('no chrome.exe');
  const profile = mkdtempSync(join(tmpdir(), 'connectors-'));
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
  ok(await waitFor(page, '!!(window.__galaxy && window.__galaxy.cmd)', 30000),
     'the viewer is up and the command panel exists');
  /* /health HAS TO HAVE LANDED ONCE, or the Voice and Scribe tiles are honestly reading "asking"
     and this harness would be asserting against a page mid-boot.

     THE FIRST VERSION OF THIS GATE WAS A LIE, and it cost three reds that looked like page bugs.
     It waited on the MODEL cell carrying text - but the markup ships every rail cell with an
     ellipsis placeholder (`<b class="rv">…</b>`, index.html:2185-2188), so that condition is true
     in the first frame, before a single fetch has returned. Worse, the model value also arrives
     on a SECOND route: loadBrains() reads /brains and calls paintBrain(), and /brains answers
     long before /health, which probes piper, whisper, the index and the web door on its way.

     So the gate is the ARCHIVE cell, and it is matched against the four shapes railFrom() can
     write into it - never against "not the placeholder", because an empty string would pass that.
     The archive is on /health and nowhere else in the page, and it is not one of the facts the
     sections below assert, so waiting on it is not waiting for the answer. */
  const HEALTH_LANDED = '(function(){var c=__galaxy.rail.cells.archive;' +
    'return !!c && /^(off|building|\\d+ files?)$/.test(String(c.text));})()';
  ok(await waitFor(page, HEALTH_LANDED, 30000),
     'and /health has landed once, so the organ tiles are reading state rather than "asking"',
     'failure mode: every tile below would be asserted against a page mid-boot, and the Voice ' +
     'and Scribe tiles would read the browser engine and an absent transcriber - correctly, ' +
     'for a page that had not been told otherwise yet');
  /* And the ellipsis trap itself, asserted rather than only commented, so that a later hand
     re-writing this gate against the model cell is told why that cell cannot carry the gate. */
  const railText = await page.json('__galaxy.rail.cells');
  ok(railText.model && railText.model.text !== '…',
     'and the rail\'s placeholder ellipsis has been replaced by a real value: ' +
     JSON.stringify(railText.model && railText.model.text),
     'failure mode: "…" is truthy, so any gate written as !!cell.text passes before boot');
  await sleep(800);

  step('B. the six named tiles, each checked against the thing it claims to read');
  const names = await page.json('__galaxy.cmd.board.names');
  ok(names.indexOf('connectors') >= 0, 'there is a Connectors board: ' + JSON.stringify(names));
  let b = await openBoard(page, 'connectors', 6);
  ok(b.row && b.row.label === 'Connectors',
     'and a row in the order sheet labelled for it: ' + JSON.stringify(b.row && b.row.label));
  ok(b.dom.length === b.tiles.length,
     'the grid renders every tile it computed: ' + b.dom.length + ' of ' + b.tiles.length);
  const SIX = ['Calendar', 'Gmail', 'Notion', 'Voice', 'Eyes', 'Scribe'];
  for (const name of SIX) {
    ok(!!byName(b.dom, name), 'the board shows ' + name,
       JSON.stringify(b.dom.map((t) => t.name)));
  }
  /* (A) THE GRANT WORD, AGAINST /google. Both tiles read one token, so they are asserted to
     agree with each other as well as with the server: two tiles reading the same grant
     independently is how one of them ends up CONNECTED while the other says CLOSED. */
  const WORD_FOR = {
    connected: 'CONNECTED', reconnect: 'RECONNECT', unknown: 'UNKNOWN',
    'no-client': 'NO CLIENT',
  };
  const wantWord = WORD_FOR[String(grant.state)] || 'CLOSED';
  const cal = byName(b.dom, 'Calendar'), gm = byName(b.dom, 'Gmail');
  ok(cal && cal.value === wantWord,
     'Calendar reads ' + JSON.stringify(cal && cal.value) + ', which is what /google says (' +
     JSON.stringify(grant.state) + ')',
     'failure mode: a board that cached a state word at boot keeps saying it after the token dies');
  ok(gm && cal && gm.value === cal.value,
     'and Gmail reads the same word, because it is the same grant: ' +
     JSON.stringify(gm && gm.value));
  ok(!/ya29\.|[A-Za-z0-9_-]{40,}/.test(String((cal && cal.sub) || '') +
                                       String((gm && gm.sub) || '')),
     'and neither tile\'s small print carries anything that looks like a token: ' +
     show([cal && cal.sub, gm && gm.sub]));
  /* (A, second half) THE HAND SMALL-PRINT, AGAINST /tools. A grant with no hand behind it is
     true about Google and useless about the thing he wants to do, so the tile says which. */
  const hasCalHand = hands0.some((t) => t.id === 'add_calendar_event');
  const hasMailHand = hands0.some((t) => t.id === 'send_email');
  if (String(grant.state) === 'connected') {
    ok(hasCalHand === !/no hand in the registry/.test(String(cal.sub)),
       'Calendar\'s small print agrees with the registry about its hand: ' +
       show(cal.sub));
    ok(hasMailHand === !/no hand in the registry/.test(String(gm.sub)),
       'and so does Gmail\'s: ' + show(gm.sub));
  } else {
    /* NOT A SKIP. With no grant the tiles are meant to show the REASON and not the hand, so
       that is the claim, and it is the one a disconnected machine can actually make. */
    note('the grant is ' + JSON.stringify(grant.state) + ', so the two service tiles are ' +
         'showing why rather than what they could do');
    ok(!!String(cal.sub || '').trim() && !!String(gm.sub || '').trim(),
       'both service tiles still give a reason rather than an empty line: ' +
       show([cal.sub, gm.sub]));
  }
  /* Voice, Eyes and Scribe, each against the live page state they are drawn from. */
  /* READ THROUGH THE SAME HOOKS THE REST OF THE DECK IS PROVEN THROUGH - eyes.on is eyesLive()
     itself, which is the single variable the Eyes Law names - so this is a comparison against
     the page's own source of truth and not against a second reading of the camera. */
  const live = await page.json('(function(){return {' +
    'engine: __galaxy.voice.engine,' +
    'canSee: !!__galaxy.eyes.supported,' +
    'eyesLive: !!__galaxy.eyes.on,' +
    'scribeInstalled: !!__galaxy.scribe.installed,' +
    'scribeReady: !!__galaxy.scribe.ready};})()');
  note('live page state: ' + JSON.stringify(live));
  const vo = byName(b.dom, 'Voice'), ey = byName(b.dom, 'Eyes'), sc = byName(b.dom, 'Scribe');
  ok(vo && /^(PIPER|BROWSER)$/.test(vo.value),
     'Voice reads one of the two engines that exist: ' + JSON.stringify(vo && vo.value));
  ok(vo && vo.value === (live.engine === 'piper' ? 'PIPER' : 'BROWSER'),
     '  and it is the engine the chunks are ACTUALLY going through (' + live.engine + '), not ' +
     'the one config.json asked for',
     'failure mode: a half-downloaded model reads as piper in the config and as the browser on ' +
     'the wire, and the tile that believed the config would be wrong out loud');
  ok(ey && /^(LIVE|CLOSED|UNSUPPORTED)$/.test(ey.value),
     'Eyes reads one of the three camera states: ' + JSON.stringify(ey && ey.value));
  ok(ey && (live.canSee ? ey.value !== 'UNSUPPORTED' : ey.value === 'UNSUPPORTED'),
     '  and it agrees with the browser about whether there is a camera api at all');
  ok(ey && !live.canSee ? true : (ey.value === (live.eyesLive ? 'LIVE' : 'CLOSED')),
     '  and with eyesLive() itself, which is the one variable the Eyes Law names: tile ' +
     JSON.stringify(ey && ey.value) + ' against __galaxy.eyes.on ' + live.eyesLive,
     'failure mode: two surfaces claiming to know about one camera is one claim too many, and ' +
     'this board is the newest of them');
  ok(sc && /^(ASKING|NOT INSTALLED|LISTENING|STARTING|READY|LOADING)$/.test(sc.value),
     'Scribe reads one of the six states it can be in: ' + JSON.stringify(sc && sc.value));
  ok(sc && (live.scribeInstalled ? sc.value !== 'NOT INSTALLED' : sc.value === 'NOT INSTALLED'),
     '  and it agrees with /health about whether the transcriber is on this machine');
  ok(!sc || sc.value !== 'NOT READY',
     '  and never reads NOT READY, which was a branch on a field the page does not carry',
     'failure mode: scribe.loading is sent by /health and never copied onto the page object, ' +
     'so a tile that branched on it read the wrong word for the whole of the model\'s load');

  step('C. Notion is on the board and says it is not configured - and is not stubbed anywhere');
  const no = byName(b.dom, 'Notion');
  ok(no && /NOT CONFIGURED/.test(String(no.value)),
     'Notion reads ' + JSON.stringify(no && no.value),
     'failure mode: a connectors board that lists only what works is a brochure, and he cannot ' +
     'ask for a thing he has no way of knowing is missing');
  ok(no && /no hand in the registry/.test(String(no.sub)),
     'and says why, in terms of the registry: ' + show(no && no.sub));
  ok(no && no.act === 'Connect' && no.actOff === true,
     'with a Connect button that is PRESENT AND DISABLED: ' +
     JSON.stringify({ act: no && no.act, off: no && no.actOff }),
     'a cell that vanished when it could not be used would take its explanation with it');
  ok(!hands0.some((t) => /notion/i.test(t.id + ' ' + t.name)),
     'and the registry holds no notion hand, so the tile is a reading of an absence rather ' +
     'than a stub waiting for a key');

  step('D. no tile on this board can run a hand');
  const handTiles = b.tiles.filter((t) => String(t.key).indexOf('hand:') === 0);
  ok(handTiles.length > 0,
     'the registry\'s own hands surface as tiles: ' +
     JSON.stringify(handTiles.map((t) => t.name)));
  const handDom = b.dom.filter((d) => String(d.key).indexOf('hand:') === 0);
  ok(handDom.length === handTiles.length,
     'and every one of them reached the grid: ' + handDom.length + ' of ' + handTiles.length);
  ok(handDom.every((d) => d.act === ''),
     'AND NOT ONE OF THEM CARRIES A BUTTON - not a disabled one, none: ' +
     JSON.stringify(handDom.map((d) => d.name + '=' + JSON.stringify(d.act))),
     'failure mode: the Halt Law says a registry script runs after a proposal and a human ' +
     'word. A grid cell wired to the executor is a second door with no gate on it');
  const buttons = b.dom.filter((d) => d.act);
  ok(buttons.every((d) => ['Calendar', 'Gmail', 'Notion', 'Voice'].indexOf(d.name) >= 0),
     'the only cells that carry a verb at all are the grant\'s two, Notion\'s refusal and the ' +
     'recast: ' + JSON.stringify(buttons.map((d) => d.name + '=' + d.act)));
  /* AND A GRANT THAT IS OPEN CARRIES NO VERB. The first plate of this board read "CONNECTED"
     beside a disabled button saying Connect, which a reader takes as a broken button rather
     than as a state of the grant. Disconnect is not the fix: the Google row already owns that
     word, and a second revoke door on this grid is exactly what Eyes and Scribe are kept
     verbless to prevent. So the assertion is directional - connected means readout, anything
     else means a button with a reason under it. */
  if (String(grant.state) === 'connected') {
    ok(!byName(b.dom, 'Calendar').act && !byName(b.dom, 'Gmail').act,
       'and with the grant open the two service tiles are readouts, not dead buttons: ' +
       JSON.stringify([byName(b.dom, 'Calendar').act, byName(b.dom, 'Gmail').act]),
       'failure mode: a disabled Connect beside CONNECTED reads as a bug in the button, and a ' +
       'live Disconnect here would be a second door onto the one grant');
  } else {
    ok(!!byName(b.dom, 'Calendar').act && !!byName(b.dom, 'Gmail').act,
       'and with no grant the two service tiles carry the one verb that could help: ' +
       JSON.stringify([byName(b.dom, 'Calendar').act, byName(b.dom, 'Gmail').act]));
  }
  ok(!byName(b.dom, 'Eyes').act && !byName(b.dom, 'Scribe').act,
     'Eyes and Scribe carry no verb, because each already has exactly one control elsewhere',
     'the Eyes Law is that one variable and one control claim to know about the camera; a ' +
     'second button here could be pressed while #eye disagreed');
  ok(/never by pressing a tile/i.test(String(b.head)),
     'and the board says so where a human reads it: ' + JSON.stringify(String(b.head)));
  /* THE ROW CANNOT DRIFT FROM THE GRID. The row counts by calling the tile builder, so this
     asserts the arrangement rather than a number I typed in two places. */
  const namedCount = b.tiles.filter((t) => String(t.key).indexOf('hand:') !== 0
                                        && t.key !== 'registry').length;
  const rowLine = String((b.row && b.row.line) || '');
  ok(rowLine.indexOf(namedCount + ' connectors') === 0,
     'the row\'s count is the grid\'s count: ' + JSON.stringify(rowLine) + ' against ' +
     namedCount + ' named tiles',
     'failure mode: a row claiming six while the grid shows seven is the door lying about ' +
     'the room behind it');
  ok(rowLine.indexOf(hands0.length + ' hand') > 0,
     'and its hand count is the registry\'s: ' + JSON.stringify(rowLine));

  /* ================== THE CANARY ==================================================== */
  step('E. the canary: a fake connector appears, and leaves nothing behind');
  ok(existsSync(REGISTRY), 'the registry is where it is meant to be: ' + REGISTRY);
  original = readFileSync(REGISTRY, 'utf8');
  const parsed = JSON.parse(original);
  const CANARY_ID = 'canary_connector';
  const CANARY_NAME = 'A canary connector';
  const CANARY_SCRIPT = 'canary_connector_does_not_exist.py';
  ok(!existsSync(join('tools', CANARY_SCRIPT)),
     'AND THE SCRIPT THE CANARY NAMES DOES NOT EXIST, so the planted entry can surface on a ' +
     'board and still be incapable of executing anything: ' + CANARY_SCRIPT,
     'failure mode: a canary that could actually run is not a canary, it is a hole');
  ok(!parsed.tools.some((t) => t && t.id === CANARY_ID),
     'and no hand by that id is in the file already, so the tile it raises is the one planted here');

  const beforeCount = b.dom.length;
  parsed.tools.push({
    id: CANARY_ID, name: CANARY_NAME, script: CANARY_SCRIPT,
    capabilities: ['pretend to be a connector, for connectors_proof.mjs, and nothing else'],
    params: [], timeout_s: 1,
    proposal: 'Shall I do the canary thing, sir?',
    step: 'do the canary thing',
  });
  writeFileSync(REGISTRY, JSON.stringify(parsed, null, 2) + '\n', 'utf8');
  /* THE SERVER RE-READS ON MTIME, no restart: hands.registry() caches on the file's stamp
     precisely so a hand can be added by editing JSON. Asserted rather than assumed, because
     if /tools does not carry the canary then the board failing to show it proves nothing. */
  let served = null;
  for (let i = 0; i < 20; i++) {
    served = ((await get('/tools')).body || {}).tools || [];
    if (served.some((t) => t.id === CANARY_ID)) break;
    await sleep(250);
  }
  ok(served.some((t) => t.id === CANARY_ID),
     'GET /tools carries the planted hand without a restart, on the registry\'s own mtime rule',
     JSON.stringify(served.map((t) => t.id)));

  b = await openBoard(page, 'connectors', beforeCount + 1);
  const raised = byName(b.dom, CANARY_NAME);
  ok(!!raised,
     'AND A TILE APPEARS FOR IT: ' + JSON.stringify(raised && raised.name),
     JSON.stringify(b.dom.map((d) => d.name)));
  ok(raised && raised.key === 'hand:' + CANARY_ID,
     'keyed off the registry id rather than its label: ' + JSON.stringify(raised && raised.key));
  ok(raised && raised.act === '',
     'and it carries no verb either, like every other hand: ' +
     JSON.stringify(raised && raised.act));
  ok(b.dom.length === beforeCount + 1,
     'the grid grew by exactly one: ' + beforeCount + ' -> ' + b.dom.length);

  /* PUT BACK HERE so the rest of the run is against the real registry, and put back AGAIN in the
     `finally` where the restoration is asserted. Writing the same bytes twice costs nothing; the
     alternative - clearing `original` here - would mean the successful path was the one path with
     no assertion that the file was restored, which is exactly backwards. */
  writeFileSync(REGISTRY, original, 'utf8');
  for (let i = 0; i < 20; i++) {
    served = ((await get('/tools')).body || {}).tools || [];
    if (!served.some((t) => t.id === CANARY_ID)) break;
    await sleep(250);
  }
  ok(!served.some((t) => t.id === CANARY_ID),
     'the entry is taken back out and /tools stops carrying it',
     JSON.stringify(served.map((t) => t.id)));
  b = await openBoard(page, 'connectors', beforeCount);
  ok(!byName(b.dom, CANARY_NAME),
     'AND THE TILE IS GONE FROM THE GRID - no ghost: ' + JSON.stringify(b.dom.map((d) => d.name)),
     'failure mode: a grid diffed against its own previous contents goes wrong on REMOVAL and ' +
     'only on removal, which is why removal is the test');
  ok(b.dom.length === beforeCount,
     'and the count is back where it started: ' + b.dom.length + ' of ' + beforeCount);
  const anywhere = await page.json(
    'document.body.innerHTML.indexOf(' + JSON.stringify(CANARY_NAME) + ')');
  ok(anywhere === -1,
     'and the canary\'s name is nowhere in the document at all, not merely off the grid',
     'a tile hidden rather than removed keeps a stale reading alive for the next open');

  step('F. closing it leaves nothing running and nothing on the glass');
  await page.evaluate('__galaxy.cmd.board.close()');
  await sleep(400);
  ok((await page.json('document.querySelectorAll("#board-grid .btile").length')) === 0,
     'the grid is empty after close');
  ok((await page.json('__galaxy.cmd.board.which')) === '', 'and the board forgets which it was');
  const p1 = await page.json('__galaxy.cmd.board.paints');
  await sleep(1600);
  ok((await page.json('__galaxy.cmd.board.paints')) === p1,
     'and nothing is repainting behind the closed panel: ' + p1,
     'connectors has no repaint cadence at all - its facts change when something happens, ' +
     'not once a second - so a tick here would be a leak with no purpose');
  /* THE BUG THIS BOARD ALMOST INTRODUCED, asserted so it cannot come back: the two boards
     shared one `read` slot, so opening Connectors and going back left the World Clock ROW
     painting from the connectors payload - "0 tiles, 0 places known" about an organ that was
     working perfectly. Each board now writes its own slot by name. */
  await page.evaluate('__galaxy.cmd.run("clock")');
  await waitFor(page, '__galaxy.cmd.board.tiles.length > 1', 12000);
  await page.evaluate('__galaxy.cmd.board.close()');
  await page.evaluate('__galaxy.cmd.run("connectors")');
  await waitFor(page, '__galaxy.cmd.board.which === "connectors"', 6000);
  await page.evaluate('__galaxy.cmd.board.close()');
  await page.evaluate('__galaxy.cmd.paint()');
  await sleep(300);
  const clockRow = await page.json('(function(){return __galaxy.cmd.rows.clock;})()');
  ok(clockRow && /places known/.test(String(clockRow.line)) &&
     !/^0 tiles/.test(String(clockRow.line)),
     'AND THE WORLD CLOCK ROW STILL READS ITS OWN ORGAN after Connectors was opened over it: ' +
     JSON.stringify(clockRow && clockRow.line),
     'failure mode: one shared reading slot for two boards - fine with one board, wrong with ' +
     'two, which is the worst kind of fine');

  page.close();
}

main().catch((e) => {
  bad.push('the run itself: ' + e.message);
  console.log('\n  ERROR ' + (e && e.stack || e));
}).finally(async () => {
  /* THE REGISTRY GOES BACK, whatever happened above, and the restoration is a CHECK so that a
     harness which died holding the file open says so in its own verdict line rather than
     leaving a fake hand in the house for somebody else to find. */
  if (original !== null) {
    let restored = false;
    try { writeFileSync(REGISTRY, original, 'utf8'); restored = true; } catch (e) {
      console.log('  ERROR could not restore ' + REGISTRY + ': ' + e.message);
    }
    ok(restored && readFileSync(REGISTRY, 'utf8') === original,
       'and tools/registry.json is byte-for-byte what it was before this harness ran',
       'a fake hand left in the registry is this harness leaving a hole behind it');
  } else {
    /* THE HARNESS DIED BEFORE IT READ THE FILE, which means it never wrote it either. Said out
       loud rather than left silent, because "no restoration check" and "restoration passed" must
       not look the same in a verdict. */
    note('the registry was never read, so it was never written, so there is nothing to restore');
  }
  procs.forEach((p) => { try { process.kill(p.pid); } catch { } });
  await sleep(700);
  profiles.forEach((p) => { try { rmSync(p, { recursive: true, force: true }); } catch { } });
  console.log('\n  VERIFY ' + (checks - bad.length) + '/' + checks +
              (bad.length ? ' FAIL' : ' PASS') + '\n');
  bad.forEach((b) => console.log('    FAILED: ' + b));
  process.exit(bad.length ? 1 : 0);
});
