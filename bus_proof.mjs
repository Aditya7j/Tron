/* bus_proof.mjs - THE PROGRESS BUS, AND WHETHER THE GLASS CAN BE BELIEVED. §35 PART 3.
 * =============================================================================================
 * THE BOSS'S LAW, in his words: "while Galaxy works, the glass shows what he is doing, step by
 * step, so the boss knows not to disturb. A backend-only job is not accepted."
 *
 * SO WHAT IS BEING PROVED HERE IS NOT "THE BUS HAS A STATE". It is that a man looking at the
 * glass is told the truth about a machine he cannot see. Every way that goes wrong leaves the
 * page looking perfectly healthy, which is why each assertion below names the failure it
 * catches:
 *   a step list that is ordered because it was appended in order, while the bus's own sequence
 *     numbers disagree - a progress bar that looks right and is reading the wrong job;
 *   an index kept by hand at four call sites, so the fourth step reports "3 of 5";
 *   a chip that outlives the render, so DO NOT DISTURB is still up an hour later;
 *   a result line put back on the card by the next poll after the man cleared it;
 *   a completion sentence spoken once per poll instead of once per job;
 *   a field a producer kept for its own bookkeeping reaching the browser because it was passed
 *     to finish();
 *   and the quietest of them: a render in flight with a seal reading READY, which is the exact
 *     failure PART 3 exists to forbid, because a machine that looks idle gets a second order
 *     typed into it.
 *
 * THE FOUR SECTIONS, and why the expensive one is last:
 *   A. THE SCRIPTED JOB - five events, in process, against jobs.py alone. §35's own fixture:
 *      "a scripted fake job emits five events". It also drives the two states a real run will
 *      not show on a good day - failed, and stale - and it writes to a ledger of its OWN in
 *      _runs/bus/ so the house's jobs-ledger.json is not touched by a fixture.
 *   B. THE ENDPOINT - GET /jobs over HTTP, and one REAL job end to end in about five seconds,
 *      by asking for a video about something the notes know nothing about. A real producer,
 *      real events, a real ledger row, and no 67-second render to get them.
 *   C. THE GLASS, from a scripted payload - the strip text asserted headless "from the endpoint
 *      JSON", which is §35's own phrasing. Every one of the five step marks, the seal's word,
 *      the result line, and the three edges the card's ownership rule exists for.
 *   D. THE GLASS, FOR REAL - one render, ordered from the page the way the boss orders it, with
 *      the mid-job plate at 1366 and the endpoint's five ordered events read back for the same
 *      job. Last because it costs nineteen seconds with a warm piper cache and sixty-seven cold.
 *
 * WHAT IT REFUSES TO DO. It writes no config.json, sends no mail, reads no credential, and
 * holds no POST to /jobs because there is none to hold: the bus is a GET, and the one id this
 * page ever follows is the one the server put in the reply to the boss's own question. A guest
 * watching a render he was refused can read it and stop nothing - which is why the page is
 * allowed to show it at all.
 *
 * RUN IT SOLO, SEQUENTIALLY, QUIET. One headless Chrome on port 9311, one temp profile, killed
 * by that profile's basename. It drives two real renders; a second harness sharing this machine
 * would be measuring this one's ffmpeg.
 *
 * Usage:  python server.py 2>> _runs/server-trace.log   then   node bus_proof.mjs
 */
import { spawn, spawnSync } from 'node:child_process';
import { mkdtempSync, mkdirSync, existsSync, readFileSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = dirname(fileURLToPath(import.meta.url));
const GALAXY = 'http://127.0.0.1:4700';
const VIEW = GALAXY + '/?mute=1';
const PORT = 9311;                 // nobody else's: cine_proof has 9307, _cineprobe 9306
const CDP = 'http://127.0.0.1:' + PORT;
const SESSION = 'busproof';
/* The absolute interpreter: bare `python` on this machine is the Store stub, which exits
   without running anything and would redden section A for no reason of the bus's. */
const PY = 'C:/Users/Fullstack Developer/AppData/Local/Programs/Python/Python313/python.exe';
const OUT = join(ROOT, '_runs', 'sweep35');
const PLATE = join(OUT, 'plate-busjob.png');
/* THE TOPIC THE NOTES KNOW NOTHING ABOUT, measured rather than assumed: recall() answers
   opens=False at best 0.4748 for this one against this 55-note corpus, which is director_proof's
   own fixture and the reason section B costs seconds instead of a minute. */
const SILENT = 'tungsten carbide lathe bearings';
const TOPIC = 'micro-saas pricing';
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

/* ---- the predicate runner ----
   One python per section, not one per claim: importing jobs.py is cheap but the process is not,
   and a harness that paid for thirty of them is a harness nobody runs twice. */
function python(lines, ms) {
  const r = spawnSync(PY, ['-c', lines.join('\n')],
                      { encoding: 'utf8', timeout: ms || 120000, cwd: ROOT,
                        env: { ...process.env, PYTHONIOENCODING: 'utf-8' } });
  if (r.error) throw new Error('python: ' + r.error.message);
  if (r.status !== 0) {
    throw new Error('python exited ' + r.status + ': ' + (r.stderr || '').slice(-900));
  }
  const out = (r.stdout || '').trim();
  const brace = out.lastIndexOf('\n{');
  try { return JSON.parse(brace >= 0 ? out.slice(brace + 1) : out); } catch (e) {
    throw new Error('python said something that was not JSON: ' + out.slice(-600));
  }
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
/* THE ROW FOR ONE JOB, polled until it stops running. Returns the last row seen plus every
   chip the endpoint showed on the way, because "the chip was never empty while it ran" is an
   assertion about the WHOLE run and cannot be read off the end of it. */
async function follow(id, ms) {
  const chips = []; const seen = [];
  const until = Date.now() + (ms || 60000);
  let row = null;
  while (Date.now() < until) {
    const r = await get('/jobs?job=' + id);
    const rows = ((r.body || {}).jobs) || [];
    row = rows[0] || row;
    if (row) { chips.push(String(row.chip || '')); seen.push(row.outcome); }
    if (row && row.outcome !== 'running') break;
    await sleep(500);
  }
  return { row, chips, seen };
}
const monotonic = (a) => a.every((v, i) => i === 0 || v >= a[i - 1]);
const strictUp = (a) => a.every((v, i) => i === 0 || v > a[i - 1]);
/* THE PLAN'S OWN INDEX, CHECKED AGAINST EVERY EVENT rather than against five of them.
   §35 asks for "ordered events {job, step, i, n, detail, elapsed_s}", and the lie this catches
   is the one Reporter exists to make impossible: an index kept by hand, so the fourth step
   reports "3 of 5". Checking the rule `i == plan.indexOf(step) + 1` on EVERY event is strictly
   stronger than checking i against array position, because a real producer calls note() several
   times inside one step - the Director sends six events for `voice` - and each repeat is one
   more chance to tell on itself. The terminal event is excluded by name: its `step` IS the
   outcome, which is in no plan. */
function indexedRight(events, plan) {
  const wrong = [];
  for (const e of events) {
    const at = plan.indexOf(e.step);
    if (at < 0) { wrong.push('unplanned step ' + JSON.stringify(e.step)); continue; }
    if (e.i !== at + 1) wrong.push(e.step + ' said ' + e.i + ', the plan says ' + (at + 1));
    if (e.n !== plan.length) wrong.push(e.step + ' said n=' + e.n);
  }
  return wrong;
}
const firstEach = (events) =>
  events.map((e) => e.step).filter((s, i, all) => all.indexOf(s) === i);
const readJson = (p) => { try { return JSON.parse(readFileSync(p, 'utf8')); } catch { return null; } };

const profiles = []; const procs = [];

/* THE SCRIPTED PAYLOADS. Shaped like jobs.public() because that is what the page is handed on
   every real poll - the same funnel, jobApply(), not a test double - and written out here so
   that the five step MARKS and the chip the strip shows can be asserted against §35's own
   literal example: "DIRECTING · 3/5 SCENES · 42s" and "script ✓ · voice ✓ · scenes … ·
   captions · stitch". A page that composed either of those strings itself would be a page that
   could claim progress the renderer has not made, so both arrive from the server. */
const FAKE_ID = 'cafe123456';
function fakeRow(over) {
  return Object.assign({
    job: FAKE_ID, name: 'director', verb: 'DIRECTING', topic: TOPIC, n: 5,
    outcome: 'running', elapsedS: 42.0, startedAt: '21:16:05',
    steps: [{ n: 1, step: 'script', state: 'done' }, { n: 2, step: 'voice', state: 'done' },
            { n: 3, step: 'scenes', state: 'running' },
            { n: 4, step: 'captions', state: 'waiting' },
            { n: 5, step: 'stitch', state: 'waiting' }],
    events: [{ job: FAKE_ID, step: 'scenes', i: 3, n: 5, detail: '', elapsed_s: 42.0,
               seq: 3, at: '21:16:47' }],
    chip: 'DIRECTING \u00b7 3/5 SCENES \u00b7 42s', result: {}, stale: false,
  }, over || {});
}
function fakePayload(row) {
  return { jobs: [row], live: row.outcome === 'running' ? row : null,
           chip: row.outcome === 'running' ? row.chip : '',
           busy: row.outcome === 'running',
           seen: { opened: 1, done: 0, failed: 0, stale: 0, events: 3 },
           maxJobs: 8, staleS: 300, ok: true, kind: 'jobs', nodes: [] };
}
const apply = (page, payload) =>
  page.json('__galaxy.job.apply(' + JSON.stringify(payload) + ')');

async function main() {
  mkdirSync(OUT, { recursive: true });
  console.log('\n  BUS PROOF - §35 PART 3, the backend made visible on the glass');
  console.log('  ' + '-'.repeat(76));

  /* ===================================================================================
     A · THE SCRIPTED JOB - five events, and the two states a good day never shows
     =================================================================================== */
  step('A. a scripted five-event job, against jobs.py alone');

  const a = python([
    'import json, time, pathlib, jobs',
    '# A LEDGER OF OUR OWN. A fixture that appended to jobs-ledger.json would put five fake',
    '# rows into the record the lookbook quotes, and "one row per job" would stop being',
    '# checkable against the real thing.',
    'pathlib.Path("_runs/bus").mkdir(parents=True, exist_ok=True)',
    'jobs.LEDGER_PATH = pathlib.Path("_runs/bus/_ledger.json")',
    'jobs.LEDGER_PATH.unlink(missing_ok=True)',
    'jobs.forget_all("fixture")',
    'PLAN = ["one", "two", "three", "four", "five"]',
    'r = jobs.Reporter("fake", PLAN, verb="faking", topic="five events")',
    'shots = []',
    'for i, name in enumerate(PLAN):',
    '    r.step(name, "detail %d" % (i + 1))',
    '    time.sleep(0.02)',
    '    shots.append(jobs.public(r.job)["jobs"][0])',
    '# ALL FIVE RESULT KEYS, because §36 gave the Director two more - sceneTypes and poster -',
    '# and a fixture that still reported three would make "the result is exactly RESULT_KEYS"',
    '# a claim about this file rather than about the whitelist. `scratch` is the one key that',
    '# must still be dropped: that is the whitelist being tested.',
    'row = r.done("All five, sir.", cited=["a", "b"], durationS=12.5,',
    '             path="output/videos/x/final.mp4",',
    '             sceneTypes=["hook", "chart", "cta"],',
    '             poster="output/videos/x/poster.jpg",',
    '             scratch="/tmp/not-for-the-browser")',
    'after = jobs.public(r.job)["jobs"][0]',
    'again = jobs.finish(r.job, "done", "a second call")',
    'led = [x for x in jobs.ledger() if x.get("job") == r.job]',
    '# THE MARKS OF EVERY STATE, including the two a happy render never reaches. A separate',
    '# job so the five above stay clean, and failed at step 2 of 3 on purpose: _steps_public',
    '# has to call step 3 waiting and not stopped.',
    'f = jobs.Reporter("fake", ["alpha", "beta", "gamma"], verb="failing", topic="the bad one")',
    'f.step("alpha"); f.step("beta")',
    'f.failed("it broke, sir")',
    'badsteps = jobs.public(f.job)["jobs"][0]["steps"]',
    '# AND THE STALE JOB, judged by a READER with the clock moved on rather than by sleeping',
    '# five minutes. public(now=) is the only hook needed: _judge_stale takes the same now.',
    's = jobs.Reporter("fake", ["only"], verb="hanging", topic="the hung one")',
    's.step("only")',
    'late = jobs.public(s.job, now=jobs._now() + jobs.JOB_STALE_S + 1.0)["jobs"][0]',
    'staleRow = [x for x in jobs.ledger() if x.get("job") == s.job]',
    'out = {',
    '  "events": shots[-1]["events"], "mid": shots[2], "after": after,',
    '  "row": row, "again": again, "ledger": led, "badsteps": badsteps,',
    '  "late": {"outcome": late["outcome"], "chip": late["chip"], "stale": late["stale"]},',
    '  "staleRow": staleRow, "seen": jobs.public()["seen"],',
    '  "EVENT_KEYS": list(jobs.EVENT_KEYS), "PUBLIC_KEYS": list(jobs.PUBLIC_KEYS),',
    '  "RESULT_KEYS": list(jobs.RESULT_KEYS), "ROW_KEYS": list(jobs.ROW_KEYS),',
    '  "LEDGER_MAX": jobs.LEDGER_MAX,',
    '  "publicTop": sorted(jobs.public().keys()),',
    '}',
    'print(json.dumps(out, ensure_ascii=False))',
  ], 60000);

  const ev = a.events || [];
  const PLAN = ['one', 'two', 'three', 'four', 'five'];
  ok(ev.length === 6,
     'the scripted job emitted the five step events AND THE OPENING ONE: ' + ev.length,
     'reconciling §35\'s "five events" with what open_job() actually does, which is emit one ' +
     'event of its own carrying the first planned step. It is there for a reason worth keeping: ' +
     'without it the chip is blank for however long the first step takes to begin, which on a ' +
     'cold retrieval is seconds of a machine that looks idle. got ' + ev.length);
  ok(ev[0].step === PLAN[0] && ev[0].i === 1 && ev[0].seq === 1,
     'and that opening event is already 1 of 5, so the chip is never blank and never zero: ' +
     JSON.stringify(ev[0].step) + ' ' + ev[0].i + '/' + ev[0].n);
  ok(strictUp(ev.map((e) => e.seq)),
     'ORDERED BY THE BUS\'S OWN SEQUENCE and not by where they landed in an array: seq ' +
     ev.map((e) => e.seq).join(','),
     'failure mode: a reader that trusted array position would call a reordered list ordered');
  const wrongA = indexedRight(ev, PLAN);
  ok(wrongA.length === 0,
     'EVERY EVENT\'S INDEX IS THE PLAN\'S, on all ' + ev.length + ' of them: ' +
     ev.map((e) => e.i + '/' + e.n).join(' '),
     'failure mode: an index maintained by hand at four call sites - the fourth step reporting ' +
     '"3 of 5" is the commonest way a progress bar lies. ' + wrongA.join('; '));
  ok(monotonic(ev.map((e) => e.elapsed_s)),
     'with a non-decreasing elapsed_s: ' + ev.map((e) => e.elapsed_s).join(', '),
     'failure mode: time.time() instead of a monotonic clock - a clock correction mid-render ' +
     'would walk the chip backwards');
  ok(firstEach(ev).join(',') === PLAN.join(','),
     'and the steps appear in the order of the plan it was opened with: ' + firstEach(ev).join(','),
     JSON.stringify(ev.map((e) => e.step)));
  const stray = ev.flatMap((e) => Object.keys(e)).filter((k) => !a.EVENT_KEYS.includes(k));
  ok(stray.length === 0,
     'NO EVENT CARRIES A KEY OUTSIDE jobs.EVENT_KEYS: ' + a.EVENT_KEYS.join(','),
     'failure mode: a producer passing its own bookkeeping to emit() and reaching the ' +
     'browser by accident. stray: ' + stray.join(','));

  const mid = a.mid || {};
  ok(/^FAKING \u00b7 3\/5 THREE \u00b7 \d+s$/.test(String(mid.chip || '')),
     'the chip at step three reads VERB · 3/5 STEP · Ns - ' + JSON.stringify(mid.chip),
     'composed in jobs.chip_text() so the string a harness asserts is the string he reads');
  ok((mid.steps || []).map((s) => s.state).join(',') === 'done,done,running,waiting,waiting',
     'and the live list has two done, one running, two waiting',
     JSON.stringify((mid.steps || []).map((s) => s.state)));
  ok(JSON.stringify(mid.result || {}) === '{}',
     'while nothing has been made yet, there is NO result on the wire - not a hopeful one',
     JSON.stringify(mid.result));

  const after = a.after || {};
  ok(after.outcome === 'done' && (after.steps || []).every((s) => s.state === 'done'),
     'on completion every step reads done and the outcome is done');
  ok(after.chip === '',
     'AND THE CHIP GOES EMPTY, so DO NOT DISTURB cannot outlive the render',
     'failure mode: a chip that stuck would have the man tiptoeing round an idle machine for ' +
     'the rest of the day. got ' + JSON.stringify(after.chip));
  ok(JSON.stringify(Object.keys(after.result || {}).sort()) ===
     JSON.stringify(a.RESULT_KEYS.slice().sort()),
     'the result on the wire is exactly jobs.RESULT_KEYS: ' + a.RESULT_KEYS.join(','),
     JSON.stringify(after.result));
  ok(after.result.durationS === 12.5 && after.result.cited.length === 2 &&
     after.result.path === 'output/videos/x/final.mp4' &&
     (after.result.sceneTypes || []).join('·') === 'hook·chart·cta' &&
     /poster\.jpg$/.test(String(after.result.poster || '')),
     'carrying the duration, the cited notes, the path - and §36\'s two: the scene types the ' +
     'beats were DRAWN as and the poster beside the mp4',
     JSON.stringify(after.result));
  ok(!JSON.stringify(after).includes('not-for-the-browser'),
     'AND THE FIELD THE LEDGER REFUSED IS NOWHERE ON THE WIRE: `scratch` was passed to ' +
     'finish() and dropped by ROW_KEYS',
     'failure mode: a whitelist on one side only - the page is the side with the attacker on ' +
     'it. ' + JSON.stringify(after.result));
  const pubStray = Object.keys(after).filter((k) => !a.PUBLIC_KEYS.includes(k));
  ok(pubStray.length === 0, 'no public key outside jobs.PUBLIC_KEYS', pubStray.join(','));

  ok((a.ledger || []).length === 1,
     'ONE LEDGER ROW PER JOB, and finish() called twice wrote one: ' + (a.ledger || []).length,
     'failure mode: a producer whose finally-block closes a job that already succeeded - two ' +
     'rows for one video, and the ledger stops being countable');
  ok(JSON.stringify(a.again) === JSON.stringify(a.row),
     'the second finish() returned the row the first one wrote rather than a new one');
  const led = (a.ledger || [])[0] || {};
  ok(led.topic === 'five events' && led.detail === 'All five, sir.' && led.steps === 5 &&
     led.cited.length === 2 && led.durationS === 12.5 && led.path,
     'and the row carries topic, detail, steps, cited, duration and path',
     JSON.stringify(led));
  ok(!JSON.stringify(led).includes('not-for-the-browser'),
     'and not the field ROW_KEYS refused either');

  ok((a.badsteps || []).map((s) => s.state).join(',') === 'done,failed,waiting',
     'A FAILED JOB marks the step it died on and leaves the rest waiting: ' +
     JSON.stringify((a.badsteps || []).map((s) => s.state)),
     'failure mode: a failure that marked every remaining step failed would read as five ' +
     'things broken when one did');
  ok(a.late.outcome === 'failed' && a.late.chip === '' && a.late.stale === false,
     'A JOB THAT STOPPED REPORTING is judged failed by whoever reads next, and its chip clears',
     'failure mode: a producer killed mid-render leaving DO NOT DISTURB on the glass until the ' +
     'server restarts. ' + JSON.stringify(a.late));
  ok((a.staleRow || []).length === 1 && (a.staleRow[0] || {}).why === 'stale',
     'and it writes its one ledger row, saying why: ' +
     JSON.stringify((a.staleRow[0] || {}).detail || ''));
  note('seen counters after the fixtures: ' + JSON.stringify(a.seen));

  /* ===================================================================================
     B · THE ENDPOINT - and one real job end to end, in seconds
     =================================================================================== */
  step('B. GET /jobs, and a real producer through it');

  const e0 = await get('/jobs');
  ok(e0.status === 200 && e0.body && e0.body.ok === true && e0.body.kind === 'jobs',
     'GET /jobs answers 200, ok, kind=jobs', String(e0.status));
  const wantTop = a.publicTop.concat(['ok', 'kind', 'nodes']).sort();
  const gotTop = Object.keys(e0.body || {}).sort();
  ok(JSON.stringify(gotTop) === JSON.stringify(wantTop),
     'THE ROUTE IS A PASSTHROUGH: it adds ok, kind and nodes to jobs.public() and nothing else',
     'failure mode: a second channel composed at the route, which would make section A\'s ' +
     'whitelist a statement about a function nobody calls. got ' + gotTop.join(',') +
     ' want ' + wantTop.join(','));
  ok(e0.body.staleS === 300 && e0.body.maxJobs === 8,
     'and it publishes its own bounds: maxJobs ' + e0.body.maxJobs + ', staleS ' +
     e0.body.staleS + 's');

  const ledgerBefore = ((readJson(join(ROOT, 'jobs-ledger.json')) || {}).jobs || []).length;
  const askedAt = Date.now();
  const r1 = await post('/chat', { question: 'make a video about ' + SILENT, session: SESSION });
  const b1 = r1.body || {};
  ok(b1.direct === true && b1.directStarted === true && /^[0-9a-f]{10}$/.test(b1.directJob || ''),
     'a TYPED order starts a real render and the reply carries the bus id: ' +
     JSON.stringify(b1.directJob),
     'the keyboard is the boss\'s other door - see director_allowed(). ' + JSON.stringify(b1));
  const silent = await follow(b1.directJob, 60000);
  const sr = silent.row || {};
  ok(sr.outcome === 'failed',
     'and the run ENDS, by itself, without this harness touching it: ' + sr.outcome,
     JSON.stringify(silent.seen));
  ok(sr.name === 'director' && sr.verb === 'DIRECTING' && sr.topic === SILENT && sr.n === 5,
     'the row names the producer, the verb and the topic: ' +
     [sr.name, sr.verb, sr.topic, sr.n].join(' / '), JSON.stringify(sr));
  const sev = sr.events || [];
  ok(sev.length >= 2 && strictUp(sev.map((x) => x.seq)) &&
     monotonic(sev.map((x) => x.elapsed_s)),
     'its events come back in seq order with a non-decreasing elapsed: ' +
     sev.map((x) => x.seq + ':' + x.step + '@' + x.elapsed_s).join(' '));
  ok(sev[0].step === 'script' && sev[0].i === 1 && sev[0].n === 5,
     'the first step is `script`, 1 of 5 - the plan the Director declared');
  ok(sev[sev.length - 1].step === sr.outcome,
     'and the last event IS the outcome, so a reader can find the ending without guessing');
  ok(/the notes hold nothing/i.test(String(sev[sev.length - 1].detail || '')),
     'THE GRACEFUL EMPTY TRAVELS AS THE PRODUCER\'S OWN SENTENCE: ' +
     JSON.stringify(sev[sev.length - 1].detail),
     'failure mode: a bus that reduced it to FAILED would throw away the only sentence in the ' +
     'exchange that tells him what to do next');
  ok(JSON.stringify(sr.result || {}) === '{}',
     'a run that made nothing publishes no result at all', JSON.stringify(sr.result));
  /* SECONDS, NOT MINUTES - and the floor is 0, not 0.1. elapsedS is rounded to one decimal,
     and a warm retrieval refuses this topic in under 50 ms, so a `> 0` floor asserted that the
     machine was SLOW: the same row read 0.8s on a cold embedding cache and 0.0s on a warm one.
     What the claim is actually about is the ceiling - that no ffmpeg ran - so the wall clock of
     the whole exchange is asserted alongside it, which cannot round away. */
  ok(sr.elapsedS >= 0 && sr.elapsedS < 40 && (Date.now() - askedAt) < 40000,
     'it took ' + sr.elapsedS + 's - seconds, because retrieval refused before any ffmpeg ran '
     + '(' + ((Date.now() - askedAt) / 1000).toFixed(1) + 's on the wire)');
  const one = await get('/jobs?job=' + b1.directJob);
  ok(((one.body || {}).jobs || []).length === 1,
     'and ?job= returns exactly that one row', String(((one.body || {}).jobs || []).length));
  /* ONE ROW PER JOB, ON A RING THAT IS ALREADY FULL. jobs.LEDGER_MAX is 50 and this machine's
     ledger reached it, so `before + 1` stopped being the arithmetic of a correct append and
     became a statement that the ring had spare room: the row IS written, an old one is evicted,
     and the count holds at 50. Both halves are asserted - the count is min(before+1, MAX) and
     the LAST row is this job's - so a ledger that silently stopped appending still reds. */
  const ledgerRows = ((readJson(join(ROOT, 'jobs-ledger.json')) || {}).jobs || []);
  const ledgerAfter = ledgerRows.length;
  const lastRow = ledgerRows[ledgerRows.length - 1] || {};
  ok(ledgerAfter === Math.min(ledgerBefore + 1, a.LEDGER_MAX) &&
     lastRow.job === b1.directJob && lastRow.outcome === 'failed',
     'the house ledger took exactly one row - ' + ledgerBefore + ' -> ' + ledgerAfter +
     ' on a ring of ' + a.LEDGER_MAX + ' - and the newest row is this job: ' +
     JSON.stringify(lastRow.job) + ' / ' + JSON.stringify(lastRow.outcome));
  note('the refused render answered in ' + ((Date.now() - askedAt) / 1000).toFixed(1) + 's');

  /* ===================================================================================
     C · THE GLASS, from the endpoint's own JSON
     =================================================================================== */
  step('C. the strip, the seal and the card, asserted headless at 1366');

  const exe = CHROMES.find((p) => existsSync(p));
  if (!exe) throw new Error('no chrome.exe');
  const profile = mkdtempSync(join(tmpdir(), 'busproof-'));
  profiles.push(profile);
  procs.push(spawn(exe, ['--headless=new', '--remote-debugging-port=' + PORT,
    '--user-data-dir=' + profile, '--no-first-run', '--no-default-browser-check',
    '--window-size=1366,768', VIEW], { detached: true, stdio: 'ignore' }));
  for (let i = 0; i < 80; i++) {
    try { await cdp('/json/version'); break; } catch { await sleep(250); }
  }
  let target = null;
  for (let i = 0; i < 40; i++) {
    const l = await cdp('/json/list');
    target = (Array.isArray(l) ? l : []).filter((t) => t.type === 'page')
      .find((t) => String(t.url).includes('mute=1'));
    if (target) break;
    await sleep(300);
  }
  if (!target) throw new Error('no viewer page');
  const page = new Page(target.webSocketDebuggerUrl);
  await page.open();
  await page.send('Runtime.enable');
  ok(await waitFor(page, '!!(window.__galaxy && window.__galaxy.ask)', 30000),
     'the viewer is up and will take a question');
  ok(await waitFor(page, '!!(__galaxy.job && __galaxy.job.state)', 15000),
     'THE PAGE POLLS /jobs OF ITS OWN ACCORD and has the payload',
     'failure mode: jobUp() never called from boot, so the chip is dead and a render is ' +
     'invisible - which is the whole of what PART 3 forbids');
  const c0 = await page.json('__galaxy.job');
  ok(c0.POLL_MS === 2500 && c0.IDLE_MS === 6000,
     'its two cadences are the documented ones: ' + c0.POLL_MS + 'ms live, ' +
     c0.IDLE_MS + 'ms idle');
  ok(c0.polling === true && c0.reads >= 1 && c0.errors === 0,
     'reads=' + c0.reads + ' errors=' + c0.errors + ' and the interval is live');
  ok(c0.cadence === 6000,
     'and it is arming at the IDLE cadence while nothing is running: ' + c0.cadence + 'ms',
     'failure mode: two always-on 2.5s background polls, half of them reporting nothing');
  ok(c0.chip === '' && c0.chipOn === false && c0.inCard === false,
     'nothing is running, so the strip cell is empty AND hidden, and the card is bare',
     JSON.stringify({ chip: c0.chip, chipOn: c0.chipOn, inCard: c0.inCard }));
  /* `muted`, not `ready`: this tab is ?mute=1 and the seal says so, which is sealPaint()'s
     bottom rung and the right answer here. What matters is that the bus is not touching the
     word while nothing runs - so the assertion is against the page's OWN idle word, read from
     a tab with no job, rather than against a constant this harness would be free to choose. */
  ok(c0.seal === 'muted' && c0.seal !== c0.SEAL_WORD,
     'the seal reads this tab\'s ordinary word and emphatically not the job word: ' +
     JSON.stringify(c0.seal) + ' (a ?mute=1 tab)', JSON.stringify(c0.seal));
  const JOBWORD = String(c0.SEAL_WORD || '');
  ok(JOBWORD === 'do not disturb',
     'THE JOB WORD IS §35\'S PHRASE MINUS THE PREFIX THE CHIP SUPPLIES: ' +
     JSON.stringify(JOBWORD) + ' - measured, not preferred',
     '§35 asks for "JOB · DO NOT DISTURB". #seal is 380px at 1366 and frozen, the chip is 236px ' +
     'of §35\'s own string, and #seal-text - the one cell that gives - is left with 119px, or ' +
     '59px once a spoken order has sealed BOSS beside it. The full phrase needs 159px and was ' +
     'reaching the glass as "JOB · DO NOT DI…". Named in the lookbook.');
  ok(await page.evaluate('typeof __galaxy.job.post === "undefined"'),
     'THE BUS IS A READER: the page exposes no way to start, stop or alter a job',
     'failure mode: a browser that could cancel the boss\'s render - /jobs is a GET and this ' +
     'block holds no POST');

  /* THE PAGE'S OWN POLL IS STOPPED FOR THE REST OF THIS SECTION, and this is a statement about
     the harness rather than about the glass. The payloads below are scripted - §35's fixture -
     and a real 2.5-second poll landing between an apply() and the read of it would overwrite
     the scripted job with the truth, which is that nothing is running: a TRUE assertion would
     go red at random. jobCadence() only re-arms an interval that exists, so job.cadence goes on
     being decided and can still be asserted. Section D puts it back up and uses nothing else. */
  await page.evaluate('void __galaxy.job.down()');
  ok(await page.evaluate('__galaxy.job.polling === false'),
     'the harness stops the page\'s own poll before handing it scripted payloads',
     'so that a real poll cannot overwrite a fixture mid-assertion');

  /* THE FOLLOW, in the order the chat handler does it: an answer is rendered, THEN the render is
     pinned to it. Both halves are here because the pin is a watermark on the card's generation -
     jobSeen() after respond() is the whole reason the step list appears at all - and a fixture
     that skipped the answer would be relying on whatever the boot sequence last typed. */
  await page.evaluate('void __galaxy.say("make a video about ' + TOPIC + '", ' +
    JSON.stringify('Building your video on ' + TOPIC + ' - about three minutes, sir.') +
    ', false, null, null, null)');
  await page.evaluate('void __galaxy.job.seen({ directJob: ' + JSON.stringify(FAKE_ID) + ' })');
  await sleep(600);
  const midRow = fakeRow();
  await apply(page, fakePayload(midRow));
  const c1 = await page.json('__galaxy.job');
  ok(c1.chip === 'DIRECTING \u00b7 3/5 SCENES \u00b7 42s',
     'THE STRIP CARRIES §35\'S OWN CHIP, copied from the endpoint: ' + JSON.stringify(c1.chip),
     'failure mode: a page that composed this string could claim progress the renderer has ' +
     'not made. got ' + JSON.stringify(c1.chip));
  ok(c1.chipOn === true, 'and the cell is shown rather than shown-and-blank');
  ok(c1.seal === JOBWORD,
     'THE SEAL READS DO NOT DISTURB while it runs: ' + JSON.stringify(c1.seal),
     'failure mode: a seal reading READY over five live ffmpeg encodes - the exact thing PART 3 ' +
     'exists to forbid, because a machine that looks idle gets a second order typed into it');
  /* AND IT IS WHOLE ON THE GLASS, which is a different claim from the one above: #seal-text
     ellipsises, so a word that fits the hook and a word that fits the cell are two facts. The
     first plate of this feature proved it by coming back reading "JOB · DO NOT DI…". */
  const fit = await page.json(`(function(){ const t = document.getElementById('seal-text');
    return {clientW: t.clientWidth, scrollW: t.scrollWidth, text: t.textContent,
            chipW: Math.round(document.getElementById('seal-study').getBoundingClientRect().width),
            sealW: Math.round(document.getElementById('seal').getBoundingClientRect().width)}; })()`);
  ok(fit.scrollW <= fit.clientW + 1,
     'and it is NOT TRUNCATED beside a full-length chip: ' + fit.scrollW + 'px in ' +
     fit.clientW + 'px (the chip takes ' + fit.chipW + 'px of a ' + fit.sealW + 'px strip)',
     'the measurement that chose the word. ' + JSON.stringify(fit));
  ok(c1.line === 'script \u2713 \u00b7 voice \u2713 \u00b7 scenes \u2026 \u00b7 captions \u00b7 stitch',
     'AND THE CARD RENDERS §35\'S OWN STEP LIST: ' + JSON.stringify(c1.line),
     'the whole plan, including what has not happened - a list of only the finished steps ' +
     'answers "what has it done" and never "how much longer"');
  ok(c1.inCard === true && await page.evaluate(
       'document.getElementById("job-line").parentNode.id === "a-text"'),
     'written INTO the existing paragraph - no new panel, no new strip, zero layout change',
     '§35 PART 3\'s DO-NOT-ALTER: "the bus writes text into existing strips only"');
  ok(c1.cadence === 2500,
     'and the poll has moved to the live cadence: ' + c1.cadence + 'ms');

  /* EVERY MARK, including the two a good day never shows. A sixth state would render as the
     bare word, which is the right failure: a step list missing one tick is readable. */
  await apply(page, fakePayload(fakeRow({
    steps: [{ n: 1, step: 'one', state: 'done' }, { n: 2, step: 'two', state: 'running' },
            { n: 3, step: 'three', state: 'failed' }, { n: 4, step: 'four', state: 'stopped' },
            { n: 5, step: 'five', state: 'waiting' }],
  })));
  const marks = await page.evaluate('__galaxy.job.line');
  ok(marks === 'one \u2713 \u00b7 two \u2026 \u00b7 three \u2717 \u00b7 four \u2014 \u00b7 five',
     'all five of jobs._steps_public()\'s states have a mark, and `waiting` has none: ' +
     JSON.stringify(marks),
     'failure mode: a glyph for "not started" puts five symbols on a line whose whole job is ' +
     'to be read at a glance from across a desk');

  /* THE RESULT CARD. §35: "replacing itself with the result card on completion (mp4 path,
     duration, cited notes)". */
  const DONE_SAID = 'Your video on micro-saas pricing is ready, sir - 65 seconds, from 5 of ' +
                    'your own notes.';
  const doneRow = fakeRow({
    outcome: 'done', elapsedS: 18.8,
    steps: [1, 2, 3, 4, 5].map((n) => ({ n, step: ['script', 'voice', 'scenes', 'captions',
                                                   'stitch'][n - 1], state: 'done' })),
    events: [{ job: FAKE_ID, step: 'done', i: 5, n: 5, detail: DONE_SAID, elapsed_s: 18.8,
               seq: 6, at: '21:16:24' }],
    chip: '',
    result: { cited: ['a', 'b', 'c', 'd', 'e'], durationS: 65.0,
              path: 'output/videos/micro-saas-pricing/final.mp4' },
  });
  await apply(page, fakePayload(doneRow));
  const c2 = await page.json('__galaxy.job');
  ok(c2.line === 'ready \u00b7 65s \u00b7 output/videos/micro-saas-pricing/final.mp4 \u00b7 5 notes',
     'THE STEP LIST IS REPLACED BY THE RESULT: ' + JSON.stringify(c2.line),
     'every field off row.result, which jobs.finish() built out of the ledger row it had just ' +
     'written - so the card and the ledger cannot disagree about what was made');
  ok(c2.chip === '' && c2.chipOn === false && c2.seal !== JOBWORD,
     'the chip and DO NOT DISTURB both clear the moment it is done',
     JSON.stringify({ chip: c2.chip, seal: c2.seal }));
  const said1 = await page.json('__galaxy.speech.said');
  const heard = (said1 || []).filter((s) => String(s.text || '') === DONE_SAID);
  ok(heard.length === 1,
     'AND THE ENDING IS SPOKEN ONCE, in the producer\'s own words: ' + heard.length + ' time(s)',
     'failure mode: the row goes on reading `done` for as long as the bus remembers it, so a ' +
     'missing guard reads the sentence out every 2.5 seconds until the tab is closed. ' +
     JSON.stringify((said1 || []).map((s) => s.text)));
  await apply(page, fakePayload(doneRow));
  await apply(page, fakePayload(doneRow));
  const said2 = await page.json('__galaxy.speech.said');
  ok((said2 || []).filter((s) => String(s.text || '') === DONE_SAID).length === 1,
     'two more polls of the same finished job say nothing further');

  /* THE CARD'S OWNERSHIP RULE, which is the only part of this design with a decision in it. */
  await page.evaluate('void __galaxy.say("something else", ' +
    JSON.stringify('A different answer, long enough to be a real one and not a status line, ' +
                   'so the typewriter treats it exactly as it treats an answer from the brain.') +
    ', false, null, null, null)');
  await apply(page, fakePayload(doneRow));
  const c3 = await page.json('__galaxy.job');
  ok(c3.inCard === false && c3.line === '',
     'THE NEXT ANSWER TAKES THE LINE WITH IT, and a later poll does not put it back',
     'typeOut() rebuilds #a-text\'s children, so the line is deleted by the paragraph it lived ' +
     'in - and the moment the card is about to say something else is exactly when a stale step ' +
     'list should go. ' + JSON.stringify({ inCard: c3.inCard, line: c3.line }));
  await page.evaluate('void __galaxy.job.forget("the harness")');
  await apply(page, fakePayload(midRow));
  const c4 = await page.json('__galaxy.job');
  ok(c4.chip === 'DIRECTING \u00b7 3/5 SCENES \u00b7 42s' && c4.inCard === false,
     'A JOB THIS TAB DID NOT COMMISSION shows its chip and writes nothing into the card',
     'the named limit: the card holds an answer to a question somebody typed HERE, and there ' +
     'is no honest answer for another tab\'s render to sit under. ' +
     JSON.stringify({ chip: c4.chip, inCard: c4.inCard }));
  await apply(page, fakePayload(fakeRow({ outcome: 'done', chip: '', result: {} })));
  await page.evaluate('void __galaxy.job.forget("the harness")');

  /* ===================================================================================
     D · THE GLASS, FOR REAL - one render, ordered the way the boss orders it
     =================================================================================== */
  step('D. a real render, from the page, with the mid-job plate');

  /* Nothing scripted from here on: the poll goes back up and the page is left to find out for
     itself what the server is doing, which is the only version of this that proves anything. */
  await page.evaluate('void __galaxy.job.up()');
  const realStart = Date.now();
  await page.evaluate('void __galaxy.ask(' + JSON.stringify('make a video about ' + TOPIC) + ')');
  /* BOTH HALVES, because they arrive down different wires and the chip can win. jobWord() reads
     data.live, which any poll brings; the card needs the id the /chat reply carried. Waiting on
     the chip alone and then reading `follow` would be a harness race, not a page bug. */
  const up = await waitFor(page,
    '__galaxy.job.chip !== "" && __galaxy.job.follow !== "" && __galaxy.job.line !== ""', 40000);
  ok(up, 'the chip, the followed id and the step list are all up within forty seconds of the ' +
         'order being given',
     'failure mode: jobSeen() wired before respond() instead of after it - the chip would be ' +
     'right and the card would stay bare with nothing in any log');
  const d1 = await page.json('__galaxy.job');
  ok(/^DIRECTING \u00b7 [1-5]\/5 [A-Z]+ \u00b7 \d+s$/.test(String(d1.chip || '')),
     'and it is the REAL render\'s chip: ' + JSON.stringify(d1.chip), JSON.stringify(d1.chip));
  ok(d1.seal === JOBWORD,
     'the seal reads DO NOT DISTURB over a real ffmpeg: ' + JSON.stringify(d1.seal));
  ok(/^[0-9a-f]{10}$/.test(String(d1.follow || '')) && d1.row && d1.row.job === d1.follow,
     'the page is following the id the SERVER minted, and the endpoint knows it: ' +
     JSON.stringify(d1.follow),
     'failure mode: MANAGER.live() read back after the call - "pending" before the thread ' +
     'started and "" after a fast render, so the page polled an id matching no job');
  ok(/\u2713|\u2026/.test(String(d1.line || '')),
     'and the card is already showing marked steps: ' + JSON.stringify(d1.line));

  /* THE PLATE IS TAKEN AT REST AND IN THE MIDDLE, not at the first chip. The first attempt took
     it the instant the chip appeared and caught the card mid-transition: the box had not finished
     growing, the answer text and the step list were still outside its rounded border, and the
     plate showed a render with no steps on a page whose DOM had them all along. A plate is
     evidence for the boss's eye, so it waits for a step past the first and for the card to
     settle - and the geometry below is asserted BEFORE the shutter, so a plate that lies about
     the glass cannot pass quietly again. */
  await waitFor(page, '/\u00b7 [2-5]\\//.test(__galaxy.job.chip)', 60000);
  await sleep(500);
  const box = await page.json(`(function(){
    const line = document.getElementById('job-line');
    const card = document.getElementById('answer');
    if (!line || !card) return {inside: false, why: 'no element'};
    const l = line.getBoundingClientRect(), c = card.getBoundingClientRect();
    const cs = getComputedStyle(line);
    return {inside: l.top >= c.top - 1 && l.bottom <= c.bottom + 1 &&
                    l.left >= c.left - 1 && l.right <= c.right + 1,
            visible: cs.visibility === 'visible' && Number(cs.opacity) > 0.5 && l.height > 8,
            parent: line.parentNode.id,
            line: Math.round(l.top) + '..' + Math.round(l.bottom),
            card: Math.round(c.top) + '..' + Math.round(c.bottom),
            text: line.textContent};
  })()`);
  ok(box.inside && box.visible && box.parent === 'a-text',
     'AT PLATE TIME THE STEP LIST IS INSIDE THE CARD\'S OWN BOX AND VISIBLE: line ' +
     box.line + ' within card ' + box.card,
     'failure mode: the card was still growing when the shutter went - the DOM is right, the ' +
     'glass is not, and only a plate shows it. ' + JSON.stringify(box));
  await page.shot(PLATE);
  const d1b = await page.json('__galaxy.job');
  note('mid-job plate at 1366x768: ' + PLATE.replace(ROOT + '\\', ''));
  note('the plate was taken reading: ' + JSON.stringify(d1b.chip) + ' / ' +
       JSON.stringify(d1b.line) + ' / seal ' + JSON.stringify(d1b.seal));

  const ended = await waitFor(page, '__galaxy.job.row && __galaxy.job.row.outcome !== "running"',
                              200000);
  const wall = (Date.now() - realStart) / 1000;
  ok(ended, 'the render finished on its own', 'waited ' + wall.toFixed(1) + 's');
  ok(wall <= 180,
     '§35\'s wall budget held: ' + wall.toFixed(1) + 's from the order to the result, ceiling 180s',
     'a warm piper cache renders this in about nineteen seconds and a cold one in sixty-seven');
  const d2 = await page.json('__galaxy.job');
  ok(d2.row.outcome === 'done',
     'it ended done: ' + d2.row.outcome + ' - ' +
     JSON.stringify((d2.row.events || []).slice(-1)[0] || {}));
  ok(/^ready \u00b7 \d+s \u00b7 output\/videos\/[a-z0-9-]+\/final\.mp4 \u00b7 \d+ notes$/
       .test(String(d2.line || '')),
     'THE RESULT LINE IS THE REAL ONE: ' + JSON.stringify(d2.line), JSON.stringify(d2.line));
  ok(d2.chip === '' && d2.seal !== JOBWORD && d2.cadence === 6000,
     'the chip clears, the seal lets go, and the poll falls back to the idle cadence',
     JSON.stringify({ chip: d2.chip, seal: d2.seal, cadence: d2.cadence }));
  const DPLAN = ['script', 'voice', 'scenes', 'captions', 'stitch'];
  const dev = d2.row.events || [];
  const steps = dev.filter((x) => DPLAN.includes(x.step));
  ok(firstEach(steps).join(',') === DPLAN.join(','),
     'THE REAL RUN FLOWED THROUGH THE SAME BUS: all five steps, in the declared order, out of ' +
     dev.length + ' events',
     'more than five because the Director calls note() inside its long steps - "scene 3 of 5" ' +
     'is the one thing that makes a 7-second encode bearable to watch. ' +
     JSON.stringify(dev.map((x) => x.step)));
  const wrongD = indexedRight(steps, DPLAN);
  ok(wrongD.length === 0,
     'and every one of those ' + steps.length + ' events carries the plan\'s own index: ' +
     firstEach(steps).map((s, i) => (i + 1) + '/5 ' + s).join(' '),
     'checked per event, not per step, because note() repeats are where a hand-kept index ' +
     'would show. ' + wrongD.join('; '));
  ok(strictUp(dev.map((x) => x.seq)) && monotonic(dev.map((x) => x.elapsed_s)),
     'ordered by seq with a monotonic elapsed across the whole render: ' +
     dev[0].elapsed_s + 's to ' + dev[dev.length - 1].elapsed_s + 's over ' +
     dev.length + ' events',
     JSON.stringify(dev.map((x) => x.seq + '@' + x.elapsed_s)));
  ok(dev[dev.length - 1].step === 'done' && dev[dev.length - 1].i === 5,
     'and the last event is the outcome at 5 of 5: ' + dev[dev.length - 1].step);
  const realSaid = await page.json('__galaxy.speech.said');
  const endLine = String((dev[dev.length - 1] || {}).detail || '');
  ok(endLine && (realSaid || []).filter((s) => String(s.text || '') === endLine).length === 1,
     'and the ending was announced once, in the server\'s own sentence: ' +
     JSON.stringify(endLine.slice(0, 90)),
     JSON.stringify((realSaid || []).map((s) => String(s.text).slice(0, 40))));
  const rows = ((readJson(join(ROOT, 'jobs-ledger.json')) || {}).jobs || [])
    .filter((r) => r.job === d1.follow);
  ok(rows.length === 1 && rows[0].cited && rows[0].cited.length >= 1 && rows[0].durationS > 0 &&
     rows[0].path,
     'ONE LEDGER ROW for the render, carrying topic, cited notes, duration and path',
     JSON.stringify(rows));
  ok(existsSync(join(ROOT, String(rows[0].path || 'nope').replace(/\//g, '\\'))),
     'and the path in it is a file that is actually on this disk: ' + (rows[0] || {}).path);
  ok(String(rows[0].topic || '').includes('saas'),
     'the ledger row names the topic that was asked for: ' + JSON.stringify(rows[0].topic));

  /* AND NOTHING KEY-SHAPED ANYWHERE ON THE WIRE, which is this house's habit on every payload
     a browser can read. The bus carries a producer's free text, and free text is where a
     credential would get in. */
  const whole = JSON.stringify((await get('/jobs')).body || {});
  ok(!/gsk_[A-Za-z0-9]|AKIA[0-9A-Z]{10,}|sk-[A-Za-z0-9]{20,}/.test(whole),
     'NO CREDENTIAL IS IN /jobs: nothing key-shaped in the whole payload');

  page.close();
}

main().then(() => {
  console.log('\n  ' + '-'.repeat(76));
  if (bad.length) {
    console.log('  failures:');
    bad.forEach((b) => console.log('    - ' + b));
  }
  console.log('  VERIFY ' + (checks - bad.length) + '/' + checks +
              (bad.length ? ' FAIL' : ' PASS'));
}).catch((e) => {
  console.log('\n  HARNESS ERROR: ' + (e && e.message));
  console.log('  VERIFY ' + (checks - bad.length) + '/' + (checks + 1) + ' FAIL');
}).finally(async () => {
  /* PROFILE-SCOPED, NEVER BY WINDOW TITLE. 9222 is the employer's own browser and this
     machine's rule is absolute: the filter is this harness's temp-profile basename. */
  const base = profiles[0] ? profiles[0].split(/[\\/]/).pop() : '';
  procs.forEach((p) => { try { p.kill(); } catch { } });
  if (base) {
    spawnSync('powershell', ['-NoProfile', '-Command',
      "Get-CimInstance Win32_Process -Filter \"Name='chrome.exe'\" | " +
      "Where-Object { $_.CommandLine -match '" + base + "' } | " +
      'ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }'],
      { encoding: 'utf8', timeout: 30000 });
  }
});
