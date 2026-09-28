/* TWO THINGS ASKED FOR IN ONE BREATH, AND ONE WORD THAT ANSWERS FOR BOTH.
 *
 * The chain is the first thing in this machine where a single yes starts more than one
 * subprocess, so it is the first thing where "the gate held" is not enough: a plan can be
 * approved honestly and still go wrong halfway, and what happens in the second half is the
 * whole subject of this file. Four rounds, in the order the risk grows:
 *
 *   1. THE PLAN THE MODEL ACTUALLY SENDS. A two-intent directive, TYPED with the keyboard
 *      through the real box, answered by the real brain. The card that comes back is read
 *      off the screen - the numbers from the rendered ::before counter, not from the array
 *      index - and the proposal is heard as ONE sentence. Then No.
 *      -> nothing ran, and the ledger says so about BOTH hands.
 *      This is the only round that costs a model call, and it is the only one that can prove
 *      the model can still do this at all. It is also the round that must never be
 *      confirmed: it contains send_email, and no harness in this tree sends real mail.
 *
 *   2. THE CHAIN THAT RUNS. Two harmless hands, injected as the model's own TEXT - tag,
 *      terminator and all - and approved with a real click.
 *      -> both hands run, the ledger records ONE chain transaction, and the second hand's
 *         file contains what the FIRST hand said, because {{step1}} was filled in after
 *         step one succeeded rather than before it was asked for.
 *
 *   3. THE HALT LAW. Three steps, the middle one asked to fail for real - a subprocess that
 *      exits 1, not a mocked return value.
 *      -> step 1 ran, step 2 failed, and STEP 3'S LEDGER ROW DOES NOT MOVE AT ALL. That
 *         unmoved number is the whole law: the receipt could say anything, but a count that
 *         did not change is a script that was never started.
 *
 *   4. THE DOORMAN'S CHAIN. A guest's spoken yes at a two-step gate.
 *      -> refused in the mandate's words, zero hands run, and the card SURVIVES - then the
 *         employer's keyboard does what the room's voice could not.
 *
 * WHY THE INJECTION IS THE MODEL'S TEXT AND NOT A READY-MADE ARRAY. The first version of
 * this feature shipped a regex, and it read nothing: the tag closes with "]]" and a JSON
 * array closes with "]", so the model writes "}}]]" and the third bracket never comes. A
 * harness that posted a parsed array would prove propose_chain() and leave the scanner -
 * the exact place the bug was - untested for ever. So rounds 2, 3 and 4 post `said`, a
 * string shaped like a model's answer, and the server scans it with the production
 * chain_tag(). See /tools cmd:chain in server.py.
 *
 * WHAT THIS HARNESS WRITES: notes/Chain proof.md and notes/Chain proof halted.md, by asking
 * the save_minutes hand for them through the gate - which is the point, since the second
 * step of a chain has to actually happen - and it deletes them at the end. It never writes
 * config.json, never sends mail, and never touches the ledger except to read it.
 *
 * Usage:  python server.py 2>> server-trace.log   then   node chain_proof.mjs
 *         CHAIN_HEADED=1 to watch it happen; headless otherwise, which is how a sweep runs it.
 */
import { spawn } from 'node:child_process';
import { mkdtempSync, rmSync, existsSync, readFileSync, unlinkSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const GALAXY = 'http://127.0.0.1:4700';
const PORT = 9264;
const CDP = 'http://127.0.0.1:' + PORT;
const LEDGER = 'tools-ledger.json';
const HEADED = process.env.CHAIN_HEADED === '1';
const CHROMES = [
  'C:/Program Files/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Google/Chrome/Application/chrome.exe',
  process.env.LOCALAPPDATA + '/Google/Chrome/Application/chrome.exe',
];
/* The two files the plans below really produce. Named here so the cleanup at the end can
   remove exactly these and nothing else: a harness that deleted by pattern would be one
   typo away from deleting the employer's notes. */
const MADE = ['notes/Chain proof.md', 'notes/Chain proof halted.md'];

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let checks = 0; const bad = [];
const ok = (c, claim, detail) => {
  checks++; console.log((c ? '  ok   ' : '  FAIL ') + claim);
  if (!c) { bad.push(claim); if (detail) console.log('         ' + detail); }
};
const note = (m) => console.log('  note ' + m);
const procs = []; const profiles = [];

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
  close() { try { this.ws.close(); } catch { } }
}
const cdp = async (p) => { const r = await fetch(CDP + p); const t = await r.text();
  try { return JSON.parse(t); } catch { return t; } };

/* ---- the ledger, which is the witness that cannot be stage-managed ------------ */
const ledgerFile = () => { try { return JSON.parse(readFileSync(LEDGER, 'utf8')) || {}; }
                           catch { return {}; } };
const ledgerRow = (id) => {
  const row = (ledgerFile().tools || {})[id] || {};
  return { ok: row.ok | 0, failed: row.failed | 0, refused: row.refused | 0,
           lapsed: row.lapsed | 0 };
};
/* STARTED, which is ok + failed. `refused` counts plans the gate threw out before any
   subprocess existed and `lapsed` counts ones nobody answered, so a "nothing ran" claim
   that included either would pass on a run where nothing ran - and fail on one where a
   proposal was merely refused. Every halt assertion below is written against this. */
const runs = (id) => { const r = ledgerRow(id); return r.ok + r.failed; };
const chains = () => (ledgerFile().chains || []).slice();
const lastChain = () => { const c = chains(); return c.length ? c[c.length - 1] : null; };

/* A model's answer, as a string, for a plan of steps - and note the ONE closing bracket
   after the array. That is not a typo and it is the reason this file injects text instead of
   an array: a correctly written tag would end "...}]]]", and all six models in the research
   probe wrote "...}]]" instead, the array's own bracket doing double duty as the first of the
   tag's pair. The production scanner is measured against the shape that actually arrives. */
const asSaid = (steps) => 'Right away, sir. [[chain: ' + JSON.stringify(steps) + ']';

async function waitFor(page, expr, ms = 10000) {
  for (let i = 0; i < ms / 150; i++) {
    try { if (await page.evaluate(expr)) return true; } catch { }
    await sleep(150);
  }
  return false;
}

async function main() {
  console.log('\n  the chain: two things asked for, one word given, and where it stops\n');
  const exe = CHROMES.find((p) => existsSync(p));
  if (!exe) throw new Error('no chrome.exe');
  const health = await (await fetch(GALAXY + '/health')).json();
  note('server up, model ' + (health.model || '?') + ', chrome ' +
       (HEADED ? 'HEADED' : 'headless'));

  const profile = mkdtempSync(join(tmpdir(), 'chain-'));
  profiles.push(profile);
  const chrome = spawn(exe, [
    '--remote-debugging-port=' + PORT, '--user-data-dir=' + profile,
    '--no-first-run', '--no-default-browser-check',
    '--autoplay-policy=no-user-gesture-required',
    '--disable-features=CalculateNativeWinOcclusion',
    '--disable-backgrounding-occluded-windows',
    '--disable-renderer-backgrounding',
    ...(HEADED ? [] : ['--headless=new']),
    /* 1280x860 on purpose: the narrowest viewport the Layout Governor caps the answer at,
       which is the one where a four-step plan could push the Yes button off the bottom of
       the card. The measurements in round 3 are taken here for that reason. */
    '--window-size=1280,860', '--new-window', GALAXY,
  ], { detached: true, stdio: 'ignore' });
  procs.push(chrome);

  for (let i = 0; i < 80; i++) { try { await cdp('/json/version'); break; } catch { await sleep(250); } }
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
  ok(await waitFor(page, '!!(window.__galaxy && window.__galaxy.hands)', 30000),
     'the viewer is up and exposes the hands');
  await waitFor(page, '__galaxy.nodes.length > 0', 20000);

  /* THE FUNNEL, WRAPPED RATHER THAN STUBBED, exactly as tools_live does it: speakLine() is
     the one function in that page that speaks, and on the local voice there is no utterance
     to intercept, so a wrapper around speechSynthesis would record nothing and every spoken
     claim below would fail for want of an instrument. */
  await page.evaluate(`
    (function () {
      if (window.__spoken) return 'already';
      window.__spoken = [];
      addEventListener('speakLine', function (ev) {
        window.__spoken.push(String((ev.detail && ev.detail.text) || ''));
      });
      return 'wrapped';
    })()`);
  const spokenAll = async () => (await page.json('window.__spoken')) || [];
  const heldBack = async () => (await page.json(
    '__galaxy.speech.said.filter(function(s){return !s.aloud}).map(function(s){return s.text})')) || [];
  const mark = async () => (await spokenAll()).length;
  const waitSaid = async (re, ms = 30000, from = 0) => {
    const until = Date.now() + ms;
    while (Date.now() < until) {
      const lines = (await spokenAll()).slice(from).concat(await heldBack());
      const hit = lines.filter((l) => re.test(l)).pop();
      if (hit) return hit;
      await sleep(150);
    }
    return null;
  };

  const card = () => page.json('({shown: __galaxy.hands.shown, label: __galaxy.hands.label,' +
    ' rows: __galaxy.hands.rows, steps: __galaxy.hands.steps, clock: __galaxy.hands.clock,' +
    ' buttons: __galaxy.hands.buttons, pending: __galaxy.hands.pending})');
  const click = async (id) => {
    await page.evaluate('document.getElementById(' + JSON.stringify(id) +
                        ').scrollIntoView({block:"center"})');
    await sleep(120);
    const box = await page.json('(function(){var r=document.getElementById(' +
      JSON.stringify(id) + ').getBoundingClientRect();return {x:Math.round(r.left+r.width/2),' +
      'y:Math.round(r.top+r.height/2)};})()');
    for (const type of ['mousePressed', 'mouseReleased']) {
      await page.send('Input.dispatchMouseEvent',
        { type, x: box.x, y: box.y, button: 'left', clickCount: 1 });
    }
  };
  const type = async (text) => {
    for (const t of ['keyDown', 'char', 'keyUp']) {
      await page.send('Input.dispatchKeyEvent', { type: t, key: '/', code: 'Slash',
        text: '/', unmodifiedText: '/', windowsVirtualKeyCode: 191,
        nativeVirtualKeyCode: 191 });
    }
    await sleep(120);
    const up = await page.json('({up: __galaxy.typeLine.up, focused: __galaxy.typeLine.focused})');
    if (!up.up || !up.focused) throw new Error('the slash did not summon the type-line');
    await page.send('Input.insertText', { text });
    for (const t of ['keyDown', 'keyUp']) {
      await page.send('Input.dispatchKeyEvent', { type: t, key: 'Enter', code: 'Enter',
        windowsVirtualKeyCode: 13, nativeVirtualKeyCode: 13,
        text: t === 'keyDown' ? '\r' : undefined });
    }
  };
  const say = (words) => page.evaluate('void __galaxy.ask(' + JSON.stringify(words) + ')');

  /* THE INJECTION, AND IT GOES THROUGH THE PAGE. The plan is minted by the SERVER - the
     reply's pending is the server's own slot, with the server's own id - and then handed to
     production's showProposal() through the paint door. So the card under test is the card
     the employer sees, and the Yes on it carries an id the server will honour: this is a
     real gate with the model call taken out, not a drawing of one. */
  const inject = async (steps) => {
    const body = JSON.stringify({ cmd: 'chain', door: 'button', said: asSaid(steps) });
    /* evaluate() and not json(), because json() wraps the expression in JSON.stringify and
       this one is a promise: stringifying a Promise gives "{}" and every assertion after it
       would have been made about an empty object. The stringify happens INSIDE the page. */
    const raw = await page.evaluate(`
      (async function () {
        const r = await fetch('/tools', { method: 'POST',
          headers: { 'Content-Type': 'application/json' }, body: ${JSON.stringify(body)} });
        const d = await r.json();
        if (d && d.pending) __galaxy.hands.paint(d.pending);
        return JSON.stringify(d);
      })()`);
    return JSON.parse(raw || 'null');
  };

  await page.evaluate('document.getElementById("reset").click()', true);
  await sleep(800);
  /* ONE REAL CLICK, TO GIVE THIS TAB A VOICE - and it is here because of a measurement.
     Chrome's autoplay policy holds the FIRST line back until a trusted gesture arrives:
     until then speakLine() records the sentence and returns false without dispatching its
     event, so the funnel recorder above hears nothing. A .click() through Runtime.evaluate
     with userGesture does NOT release it; a dispatched mouse event does. Without this, round
     one's proposal - the only line spoken before any button is pressed - is provably said and
     unprovably heard, and the check would fail for want of an instrument. */
  await click('title');
  await sleep(200);
  note('the tab’s voice: ' + (await page.evaluate(
    'JSON.stringify({unlocked: __galaxy.speech.unlocked, muted: __galaxy.speech.muted, ' +
    'voice: __galaxy.speech.voice})')));

  /* The doorman's switch, read before any word is given out loud - see tools_live for the
     same fork. With nobody enrolled the law stands down and round 4 proves the opposite
     half: that a spoken yes at a chain gate runs the plan. Both branches require the same
     consequence; only the door changes.

     READ FROM THE SERVER AND NOT FROM THE PAGE, and that is a fix rather than a preference.
     This line used to ask __galaxy.speaker.hasHands, which the page learns from a /health
     POLL - measured at roughly three seconds after the tab exposes __galaxy, against a read
     taken about one second after it. So the switch was a race, and losing it did not skip a
     round: it sent the harness down the UNGUARDED branch on a guarded machine, where it
     asserted that a spoken yes runs the plan while the doorman - correctly - refused it. One
     race, three red assertions, and every one of them pointed at the server. The server is
     the doorman; GET /speaker is the doorman answering about himself, and it cannot be early. */
  const roster = await (await fetch(GALAXY + '/speaker')).json();
  const guarded = !!(roster && roster.hasHands);
  const DOORMAN = /i take orders from one voice in this house/i;
  note('the speaker store reads ' + (guarded ? 'GUARDED - a spoken yes at the chain gate is ' +
       'expected to be REFUSED and the keyboard to settle it'
     : 'EMPTY - the doorman stands down and a spoken yes runs the plan'));

  /* ================= 1. THE PLAN THE MODEL SENDS, TYPED ==================== */
  console.log('\n  1. a two-intent directive, typed, answered by the real brain\n');
  const beforeCal = runs('add_calendar_event'), beforeMail = runs('send_email');
  /* THE LEDGER IS A RING AND THIS ASSERTION USED TO FORGET IT. What follows wants to prove
     that a refused plan is recorded as ONE transaction and not as one row per tool, and the
     first draft proved it by counting: chains().length === chainsBefore + 1. That held for
     fifty rows and then became unprovable forever, because hands.py caps the file at
     CHAIN_LEDGER_MAX = 50 on the read AND on the write, so the fifty-first append pushes the
     oldest row out and the length never moves again. The harness passed 78/78 the day before
     this was found purely because the ring had not filled yet - a latent red with a date on
     it, and one that would have read as a regression in the server rather than as arithmetic
     in the harness. IDENTITY, NOT LENGTH: the row is new if its id was not in the ledger
     before, and "one and not two" is the claim that exactly one id appeared. That is what
     was meant all along, and it is true at any ring position. */
  const chainIdsBefore = new Set(chains().map((c) => String(c && c.id)));
  const markOne = await mark();
  /* THIS SENTENCE AND NOT A TIDIER ONE. "email the team" with no address was the first
     fixture and it failed six times out of six - correctly, because the model refused to
     invent a recipient and sent a single calendar tag instead. The address is the fixture's
     job, not the model's. */
  await type('add a vendor call to my calendar tomorrow at 4 and email the team at ' +
             'team@acme.com about it');
  const drawn = await waitFor(page, '__galaxy.hands.shown === true', 120000);
  ok(drawn, 'typing two instructions in one breath raises the gate',
     'nothing was proposed at all: the brain answered in prose, or the tag was unreadable');
  const one = await card();
  /* EVERY READ BELOW GOES THROUGH THESE TWO, and that is not defensiveness for its own sake:
     the one thing in this file that can legitimately surprise it is the model, and a harness
     that threw a TypeError on a prose answer would report "the run itself" instead of "the
     brain did not decompose it" - the wrong finding, from the right failure. */
  const served = (one && one.pending) || {};
  const plan = served.steps || [];
  note('   label: ' + JSON.stringify(one.label));
  note('   plan:  ' + JSON.stringify((one.steps || []).map(s => s.n + ' ' + s.what)));
  ok(served.chain === true && plan.length === 2,
     'THE BRAIN DECOMPOSED IT: the server minted a chain of exactly two steps',
     'failure mode: a single proposal for one of the two intents, which is the half-done ' +
     'plan nobody notices - got ' + JSON.stringify(served.tool) +
     ', chain=' + JSON.stringify(served.chain));
  const ids = plan.map(s => s.tool);
  ok(ids[0] === 'add_calendar_event' && ids[1] === 'send_email',
     'and in the order they must happen: the calendar before the email that refers to it',
     JSON.stringify(ids));
  ok((one.steps || []).length === 2,
     'the CHAIN CARD replaced the single gate card: two numbered items on screen',
     'failure mode: the rows rendered instead, which is one step\u2019s parameters passed ' +
     'off as the whole plan - got ' + JSON.stringify(one.steps));
  ok(Object.keys(one.rows || {}).length === 0,
     'and the single-proposal rows are EMPTY, so the card cannot show a plan of two beside ' +
     'the parameters of one', JSON.stringify(one.rows));
  const listTag = await page.evaluate("document.getElementById('ask-steps').tagName");
  ok(listTag === 'OL' && (one.steps || []).every(s => s.tag === 'LI'),
     'the plan is an ordered list of list items, so the order is the document’s own',
     JSON.stringify({ list: listTag, items: (one.steps || []).map(s => s.tag) }));
  ok((one.steps || []).length > 0 &&
     (one.steps || []).every(s => /counter\(\s*step\s*\)/.test(String(s.marker || ''))),
     'and the NUMBER beside each step is counter(step) - the list counting its own ' +
     'children - so no digit is written into the markup at all',
     'failure mode: numbers rendered as text, which can disagree with the order they are ' +
     'in - markers read ' + JSON.stringify((one.steps || []).map(s => s.marker)));
  ok(plan.length > 0 && (one.steps || []).length === plan.length &&
     (one.steps || []).every((s, i) => s.what === String((plan[i] || {}).line || '')),
     'and each line is the SERVER\u2019S sentence for that step, filled from the registry ' +
     'template - not the model\u2019s prose about it',
     JSON.stringify({ screen: (one.steps || []).map(s => s.what),
                      server: plan.map(s => s.line) }));
  ok((one.steps || []).every(s => !/\{[a-z]+\}/i.test(s.what)),
     'with no blank left standing in either of them', JSON.stringify(one.steps));
  const mailVals = ((one.steps || [])[1] || {}).vals || {};
  ok(String(mailVals.to || '').indexOf('team@acme.com') >= 0,
     'the exact values are under the sentence, in mono, so the recipient can be audited ' +
     'before the yes: ' + JSON.stringify(mailVals.to), JSON.stringify(mailVals));
  const spoke = await waitSaid(/shall i execute the chain/i, 30000, markOne);
  ok(!!spoke, 'the plan is PROPOSED OUT LOUD as one sentence: ' + JSON.stringify(spoke),
     'failure mode: two proposals spoken over each other, or none - a plan nobody heard');
  /* AND IT ENDS IN THE QUESTION, which is the assertion this round was written to make and
     the one that failed first. A two-step plan beginning with a calendar entry runs to about
     270 characters and the spoken cap is 260: the funnel kept the details and dropped "Shall
     I execute the chain?", so the plan was read out and the word was never asked for. See
     spokenForm() - the question is put back when the cap takes it. */
  ok(/shall i execute the chain\?\s*$/i.test(String(spoke || '')),
     'AND THE QUESTION IS THE LAST THING SAID, over a sentence longer than the 260-character ' +
     'spoken cap: ' + JSON.stringify(String(spoke || '').slice(-60)),
     'failure mode: a plan narrated and never put as a question - the listener with their ' +
     'back to the screen hears a statement and answers nothing');
  ok(/^i have a two-step plan/i.test(String(spoke || '').trim()),
     'one spoken proposal for the whole plan, not one per step', JSON.stringify(spoke));
  ok(/\bfirst\b/i.test(spoke || '') && /\bsecond\b/i.test(spoke || ''),
     'ordered out loud - First, then Second - because a listener has no numbers to look at',
     JSON.stringify(spoke));
  /* The cap is a SPOKEN cap and the card is not capped: what was heard is a fair reading of
     what is written, and what is written is the server's sentence entire. */
  const onCard = await page.evaluate('document.getElementById("a-text").textContent');
  ok(String(onCard || '').indexOf(String(served.line || '')) >= 0,
     'and the card carries the server’s sentence in full, cap or no cap, so reading it and ' +
     'hearing it agree', JSON.stringify(String(onCard || '').slice(0, 120)));
  /* ---- and No, because this plan contains a real email ---- */
  const markNo = await mark();
  await click('ask-no');
  const refusal = await waitSaid(/i have done nothing|nothing was done/i, 20000, markNo);
  ok(!!refusal, 'No is answered out loud: ' + JSON.stringify(refusal));
  ok(await waitFor(page, '__galaxy.hands.shown === false', 8000),
     'and the card goes, there being nothing left to answer');
  await sleep(500);
  ok(runs('add_calendar_event') === beforeCal && runs('send_email') === beforeMail,
     'THE GATE HELD FOR BOTH HANDS: neither script was started',
     JSON.stringify({ calendar: [beforeCal, runs('add_calendar_event')],
                      email: [beforeMail, runs('send_email')] }));
  const refusedRow = lastChain();
  const appeared = chains().map((c) => String(c && c.id))
    .filter((id) => !chainIdsBefore.has(id));
  ok(appeared.length === 1 && refusedRow && refusedRow.status === 'refused'
     && String(refusedRow.id) === appeared[0],
     'and the plan is recorded as ONE refused transaction, not two refused tools: ' +
     appeared.length + ' new row(s) in a ledger of ' + chains().length +
     ' (the ring holds 50, so this counts ids and not rows)',
     JSON.stringify({ appeared, row: refusedRow }));

  /* ================= 2. THE CHAIN THAT RUNS =============================== */
  console.log('\n  2. two harmless hands, injected as the model\u2019s own text, and a real click\n');
  MADE.forEach(f => { try { unlinkSync(f); } catch { } });
  const beforeTest = runs('selftest'), beforeSave = runs('save_minutes');
  const twoStep = [
    { hand: 'selftest', params: { token: 'CHAIN-ONE' } },
    { hand: 'save_minutes', params: { title: 'Chain proof', overwrite: true,
        minutes: 'The first step of this plan reported: {{step1}}' } },
  ];
  const reply = await inject(twoStep);
  ok(!!reply && reply.ok === true && reply.chain === true,
     'the server read a chain out of a model-shaped answer that closes with "}}]]" - the ' +
     'terminator a regex could never see', JSON.stringify(reply && reply.error));
  ok(await waitFor(page, '__galaxy.hands.shown === true', 8000),
     'the chain card is up, painted by production\u2019s own showProposal()');
  const two = await card();
  note('   plan: ' + JSON.stringify((two.steps || []).map(s => s.n + ' ' + s.what)));
  ok((two.steps || []).length === 2 &&
     two.steps.every((s, i) => s.what ===
       String((((reply || {}).pending || {}).steps || [])[i] &&
              ((reply.pending.steps[i] || {}).line) || '')),
     'two steps on screen, in the server’s order and the server’s words',
     JSON.stringify(two.steps));
  ok(/\{\{step1\}\}/.test(JSON.stringify((two.steps[1] || {}).vals || {})),
     'THE STATE PASSING IS VISIBLE BEFORE THE YES: the placeholder is on the card, in the ' +
     'field it will land in, exactly as it will be sent',
     'failure mode: a body that quotes step one without the employer having seen that it ' +
     'would - ' + JSON.stringify((two.steps[1] || {}).vals));
  ok(/step 1/i.test(String((two.steps[1] || {}).uses || '')),
     'and it is said in English beside the number, for somebody reading rather than ' +
     'auditing: ' + JSON.stringify((two.steps[1] || {}).uses));
  ok(String((two.steps[0] || {}).uses || '') === '',
     'while step one quotes nothing, having nothing behind it',
     JSON.stringify((two.steps[0] || {}).uses));
  const markRun = await mark();
  await click('ask-yes');
  const receipt = await waitSaid(/all \d+ steps are done|steps are done, sir/i, 60000, markRun);
  ok(!!receipt, 'one click runs the whole plan and says so once: ' + JSON.stringify(receipt),
     'failure mode: a receipt per step, or silence after the first hand');
  await sleep(700);
  ok(runs('selftest') === beforeTest + 1 && runs('save_minutes') === beforeSave + 1,
     'BOTH HANDS RAN, exactly once each',
     JSON.stringify({ selftest: [beforeTest, runs('selftest')],
                      save_minutes: [beforeSave, runs('save_minutes')] }));
  const okRow = lastChain();
  ok(!!okRow && okRow.status === 'ok' && okRow.ran === 2 && okRow.stopped === 0,
     'and the ledger records ONE transaction under one chain_id, with both steps run: ' +
     JSON.stringify(okRow && okRow.id), JSON.stringify(okRow));
  ok(!!okRow && /^c[0-9a-f]+-\d+$/.test(String(okRow.id || '')),
     'the chain_id is the plan\u2019s own, minted once and shaped like one',
     JSON.stringify(okRow && okRow.id));
  const wrote = existsSync(MADE[0]) ? readFileSync(MADE[0], 'utf8') : '';
  ok(wrote.indexOf('CHAIN-ONE') >= 0,
     'AND THE SECOND HAND RECEIVED WHAT THE FIRST ONE SAID: step one\u2019s own stdout is in ' +
     'the file step two wrote',
     'failure mode: the placeholder filled from the PROPOSAL rather than from the result, ' +
     'which is a body that reports a success nobody observed - wrote ' +
     JSON.stringify(wrote.slice(0, 160)));
  ok(wrote.indexOf('{{step1}}') < 0,
     'and the placeholder itself is gone, not left in the file as text',
     JSON.stringify(wrote.slice(0, 160)));

  /* ================= 3. THE HALT LAW ====================================== */
  console.log('\n  3. three steps, the middle one failing for real\n');
  const t0 = runs('selftest'), s0 = runs('save_minutes');
  const halting = [
    { hand: 'selftest', params: { token: 'HALT-ONE' } },
    { hand: 'selftest', params: { token: 'FAIL-TWO' } },
    { hand: 'save_minutes', params: { title: 'Chain proof halted', overwrite: true,
        minutes: 'This file must never exist. {{step2}}' } },
  ];
  const three = await inject(halting);
  ok(!!three && three.ok === true &&
     (((three.pending || {}).steps) || []).length === 3,
     'a three-step plan is proposed', JSON.stringify(three && three.error));
  await waitFor(page, '__galaxy.hands.shown === true', 8000);
  const card3 = await card();
  ok((card3.steps || []).length === 3 &&
     card3.steps.every(s => /counter\(\s*step\s*\)/.test(String(s.marker || ''))),
     'three steps on screen, each numbered by the list itself',
     JSON.stringify((card3.steps || []).map(s => [s.n, s.marker])));
  /* THE MEASUREMENTS, taken with the tallest card this file draws and the answer capped -
     because the failure this guards against is a plan so tall that the Yes button leaves
     the screen, and a gate you cannot reach is a gate that fails by never being answered. */
  const rects = await page.json('__galaxy.layout.rects');
  const R = (k) => rects[k] || null;
  note('   card ' + JSON.stringify(R('a-ask') && [R('a-ask').w, R('a-ask').h]) +
       ', steps ' + JSON.stringify(R('ask-steps') && [R('ask-steps').w, R('ask-steps').h]) +
       ', rows ' + JSON.stringify(R('ask-rows')) +
       ', yes bottom ' + (R('ask-yes') && R('ask-yes').bottom) +
       ', rail top ' + (R('bar') && R('bar').top));
  ok(!!R('ask-steps') && R('ask-steps').h > 0,
     'the steps list has a rectangle of its own, so the cap rule has something to cap',
     JSON.stringify(R('ask-steps')));
  ok(R('ask-rows') === null,
     'and the single-proposal rows have NO rectangle at all - an empty grid that still took ' +
     'room would push the plan down for nothing', JSON.stringify(R('ask-rows')));
  ok(!!R('ask-yes') && !!R('bar') && R('ask-yes').bottom <= R('bar').top,
     'THE YES BUTTON IS ABOVE THE ORGAN RAIL with a three-step plan on a 1280x860 window: ' +
     (R('ask-yes') && R('ask-yes').bottom) + ' <= ' + (R('bar') && R('bar').top),
     'failure mode: #ask-steps missing from the #answer.capped rule, which does not error - ' +
     'it silently grows the card until the gate is off screen');
  ok(!!R('ask-steps') && !!R('ask-yes') && R('ask-steps').bottom <= R('ask-yes').top,
     'and the plan is above the two answers, in reading order',
     JSON.stringify({ steps: R('ask-steps'), yes: R('ask-yes') }));

  const markHalt = await mark();
  await click('ask-yes');
  const halted = await waitSaid(/i have stopped the chain/i, 60000, markHalt);
  ok(!!halted, 'the receipt says the chain STOPPED: ' + JSON.stringify(halted),
     'failure mode: silence, or a receipt that reports the whole plan done');
  ok(/HALT-ONE/.test(String(halted || '')),
     'it names what DID happen first - step one\u2019s own evidence',
     JSON.stringify(halted));
  ok(/step 2 of 3/i.test(String(halted || '')),
     'then exactly where it stopped, by number', JSON.stringify(halted));
  ok(/on purpose|failed/i.test(String(halted || '')),
     'and why, in the script\u2019s own words', JSON.stringify(halted));
  ok(/step 3 was not attempted|not attempted/i.test(String(halted || '')),
     'and what was abandoned, so nobody is left assuming the rest went through',
     JSON.stringify(halted));
  await sleep(700);
  ok(runs('selftest') === t0 + 2,
     'steps one and two both really started: two runs of the hand that touches nothing',
     'runs ' + t0 + ' -> ' + runs('selftest'));
  ok(ledgerRow('selftest').failed >= 1,
     'and the failure is recorded as a failure, not a refusal - the subprocess did start',
     JSON.stringify(ledgerRow('selftest')));
  /* THE ASSERTION THE WHOLE LAW RESTS ON, and it is a number that does not move. */
  ok(runs('save_minutes') === s0,
     'STEP 3 WAS NEVER CALLED: save_minutes\u2019 ledger row did not move at all',
     'failure mode: the loop carried on past a failure, which is an email sent on the ' +
     'strength of a calendar entry that never existed - runs ' + s0 + ' -> ' +
     runs('save_minutes'));
  ok(!existsSync(MADE[1]),
     'and the file step 3 would have written does not exist',
     JSON.stringify(MADE[1]));
  const haltRow = lastChain();
  ok(!!haltRow && haltRow.status === 'halted' && haltRow.ran === 1 && haltRow.stopped === 2,
     'the ledger records one halted transaction, naming the index it stopped at: ' +
     JSON.stringify(haltRow), JSON.stringify(haltRow));
  ok(!!haltRow && !!okRow && haltRow.id !== okRow.id,
     'under a chain_id of its own, distinct from the plan that succeeded',
     JSON.stringify({ ok: okRow && okRow.id, halted: haltRow.id }));
  const ledgerText = existsSync(LEDGER) ? readFileSync(LEDGER, 'utf8') : '';
  ok(ledgerText.indexOf('FAIL-TWO') < 0 && ledgerText.indexOf('team@acme.com') < 0,
     'and it kept none of what the hands were given - no token, no address',
     ledgerText.slice(0, 200));

  /* ================= 4. THE DOORMAN'S CHAIN =============================== */
  console.log('\n  4. a spoken yes at a two-step gate\n');
  const t1 = runs('selftest');
  const guest = [
    { hand: 'selftest', params: { token: 'GUEST-ONE' } },
    { hand: 'selftest', params: { token: 'GUEST-TWO' } },
  ];
  await inject(guest);
  ok(await waitFor(page, '__galaxy.hands.shown === true', 8000),
     'a two-step plan is on the screen, waiting for one word');
  const markSaid = await mark();
  await say('yes, go ahead');
  if (guarded) {
    const refused = await waitSaid(DOORMAN, 30000, markSaid);
    ok(!!refused, 'A GUEST CANNOT APPROVE A SEQUENCE: the spoken yes is refused at the ' +
       'chain gate in the same words as at a single one - ' + JSON.stringify(refused),
       'failure mode: /chain/execute written as a second executor without the doorman, ' +
       'which is a stranger starting two subprocesses with one syllable');
    await sleep(500);
    ok(runs('selftest') === t1,
       'and ZERO hands executed - not the first one, which is the half of this that a ' +
       'per-step gate would have got wrong', 'runs ' + t1 + ' -> ' + runs('selftest'));
    ok(await waitFor(page, '__galaxy.hands.shown === true', 8000),
       'the card SURVIVED the stranger: a guest\u2019s word cannot take the employer\u2019s ' +
       'own question off his screen');
    const markKey = await mark();
    await click('ask-yes');
    const done = await waitSaid(/steps are done, sir/i, 60000, markKey);
    ok(!!done, 'THE KEYBOARD YES ALWAYS WORKS: the employer\u2019s own key runs the plan ' +
       'the room\u2019s voice could not - ' + JSON.stringify(done));
    await sleep(600);
    ok(runs('selftest') === t1 + 2,
       'and both steps ran, once each, on the one consent that counted',
       'runs ' + t1 + ' -> ' + runs('selftest'));
  } else {
    const done = await waitSaid(/steps are done, sir/i, 60000, markSaid);
    ok(!!done, 'with nobody enrolled the doorman stands down and the spoken yes runs the ' +
       'whole plan: ' + JSON.stringify(done));
    await sleep(600);
    ok(runs('selftest') === t1 + 2,
       'both steps ran, once each, from the spoken door alone',
       'runs ' + t1 + ' -> ' + runs('selftest'));
    note('the refusal half of this round is unprovable on a machine with an empty speaker ' +
         'store - enrol a voiceprint and it asserts three more things');
  }
  ok(await waitFor(page, '__galaxy.hands.shown === false', 8000),
     'and the gate is closed afterwards, either way');

  /* ================== ROUND 5: ONE INTENT IS NOT A CHAIN =========================
     Preflight asserts that a posted plan of one falls through to the single card. That is
     the schema half, and it proves the reader. THIS is the other half and it is the one the
     employer meets: a single-intent directive, spoken in English, through the real funnel,
     with the model deciding for itself what shape to answer in. The failure it guards is not
     a refusal - it is CEREMONY. A machine that wraps "put a vendor call in my calendar" in a
     numbered plan of one has turned a card with rows the employer can read into a list with
     one item and no rows, and has done it on the commonest instruction in the house.

     Each fixture is a whole directive with exactly one verb that reaches a hand. They are
     typed, not injected, and every one of them costs a model call - which is why there are
     six and not twenty, and why the set is chosen for PRECISION rather than volume: one per
     hand that can be asked for in a sentence, plus the two shapes that most look like two
     things and are not (a directive with a trailing clause, and one with the word "and"
     inside a single object). */
  console.log('\n  ---- round 5: one intent is not a chain ----\n');
  const SINGLES = [
    ['put a vendor call in my calendar for tomorrow at four', 'add_calendar_event',
     'the commonest directive in the house'],
    ['save the minutes of this meeting', 'save_minutes', 'one hand, no object to pass'],
    ['run a self test', 'selftest', 'the shortest directive there is'],
    ['put a meeting with the roasting team and the wholesale accounts in my calendar ' +
     'for Tuesday at ten', 'add_calendar_event',
     'the word "and" INSIDE one object: two people, one meeting, one hand'],
    ['add a dentist appointment to my calendar for Friday at nine, if you would',
     'add_calendar_event', 'a trailing clause is not a second instruction'],
    ['write a note of this conversation to a file called Tuesday', 'save_minutes',
     'one hand named two ways'],
  ];
  let singlesSeen = 0;
  for (const [words, hand, why] of SINGLES) {
    await page.evaluate('__galaxy.hands.close()');
    await sleep(150);
    await say(words);
    const drew = await waitFor(page, '__galaxy.hands.shown === true', 45000);
    const slot = await card();
    if (!drew) {
      /* NOT A FAILURE BY ITSELF, and said so out loud rather than scored. The gate can
         decline to raise for a sentence the model read as conversation, and this round is
         about the SHAPE of the card when there is one - never about forcing a card. What it
         must never be is a chain, and no card is not a chain. */
      note('no card for ' + JSON.stringify(words) + ' (' + why + ') - nothing to score');
      continue;
    }
    singlesSeen++;
    ok(!slot.pending || slot.pending.chain !== true,
       'ONE INTENT IS NOT A CHAIN: ' + JSON.stringify(words) + ' (' + why +
       ') drew a single card and not a plan',
       'chain=' + JSON.stringify(slot.pending && slot.pending.chain));
    ok((slot.steps || []).length === 0,
       '  and it is drawn with no numbered list at all: ' + (slot.steps || []).length +
       ' step row(s)');
    ok(Object.keys(slot.rows || {}).length > 0,
       '  and it keeps the single card’s ROWS, which is what a plan of one would have ' +
       'taken away: ' + Object.keys(slot.rows || {}).length + ' row(s)');
    await page.evaluate('__galaxy.hands.close()');
    await fetch(GALAXY + '/tools', { method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ cmd: 'cancel', door: 'curl' }) });
    await sleep(200);
  }
  ok(singlesSeen >= 3,
     'the precision set put at least three single-intent directives through the real funnel: ' +
     singlesSeen + ' of ' + SINGLES.length + ' raised a card',
     'a round that scored nothing would pass silently, so the count is asserted too');
  note('zero chain cards across ' + singlesSeen + ' single-intent directive(s)');

  /* ================== ROUND 6: A STEP THAT CANNOT FIT IS ANNOUNCED ================
     THE SPOKEN SUMMARY, and the defect is a disappearance. spokenForm() caps the voice at
     260 characters by keeping whole sentences and stopping, then puts the closing question
     back on the end - and a four-step plan is comfortably over the cap, so what came out was
     "I have a four-step plan, sir. First, <one step>. Shall I execute the chain?" with steps
     two, three and four GONE. Not shortened. Absent, from a sentence that had just announced
     there were four of them, in front of a listener whose back is to the screen.

     WHY THIS IS PROVEN BY EXECUTING THE PAGE AND NOT BY LISTENING TO IT. The spoken line is
     composed on the /chat path, so hearing a four-step plan out loud requires a MODEL to
     volunteer one - and a chain of four has never been proposed by a model in this house; it
     is on the open list. Waiting for one would make this a test of the model's mood. So the
     capping functions are lifted OUT OF THE SHIPPED PAGE - the same bytes the browser two
     inches away is running, sliced from viewer/index.html at this moment, not a copy kept
     here - and run on the real spoken line the SERVER composes for a real four-step plan.
     Two real halves, and no fixture in the middle pretending to be either. */
  console.log('\n  ---- round 6: the spoken summary drops no step ----\n');
  // Relative, like LEDGER and MADE above: this harness is run from the project root.
  const pageSrc = readFileSync('viewer/index.html', 'utf8');
  const from = pageSrc.indexOf('  const SPOKEN_MAX_CHARS = 260;');
  const to = pageSrc.indexOf('  /* Nothing else in the file is allowed to move the camera');
  ok(from > 0 && to > from,
     'the capping block is where this round expects it in viewer/index.html',
     'from ' + from + ' to ' + to);
  let spokenForm = null;
  if (from > 0 && to > from) {
    /* eslint-disable no-eval */
    spokenForm = eval('(function(){' + pageSrc.slice(from, to) +
                      '; return spokenForm; })()');
  }
  ok(typeof spokenForm === 'function',
     'and it evaluates: the page’s own spokenForm() is in hand, lifted not rewritten');

  const longTitle = 'Vendor quarterly review with the roasting team and the wholesale accounts';
  const four = await inject([
    /* AN ISO STAMP AND NOT "tomorrow at 4pm", because the schema is right to refuse the
       second one: readings() cannot derive a time it cannot read, and a step whose time is
       unreadable must never become approvable. The first draft of this round wrote prose
       here and was refused at step 1 - correctly, and by the very law round 1 asserts. */
    { hand: 'add_calendar_event',
      params: { title: longTitle, start: '2026-12-08T16:00', end: '2026-12-08T17:30' } },
    { hand: 'selftest', params: { token: 'FOUR-A' } },
    { hand: 'selftest', params: { token: 'FOUR-B' } },
    { hand: 'save_minutes', params: { title: 'CHAIN-FOUR', minutes: '{{step2}}' } },
  ]);
  const fourCard = await card();
  ok(!!four && four.ok === true && four.chain === true &&
     ((four.pending || {}).steps || []).length === 4,
     'a four-step plan is minted by the server, which is the most one word may carry',
     JSON.stringify(((four.pending || {}).steps || []).map(s => s.tool)));
  ok((fourCard.steps || []).length === 4,
     'THE CARD SHOWS ALL FOUR, whatever the voice does: the eye is never the thing that ' +
     'loses a step', (fourCard.steps || []).length + ' step row(s)');
  const serverLine = String((four.pending || {}).line || '');
  ok(serverLine.length > 260,
     'and the sentence the server composed really is over the spoken cap: ' +
     serverLine.length + ' characters, so this round is testing the case it claims to');
  if (typeof spokenForm === 'function') {
    const heard = spokenForm(serverLine);
    ok(/\?$/.test(heard),
       'the spoken form STILL ENDS WITH THE QUESTION: ' + JSON.stringify(heard.slice(-34)));
    ok(/shall i execute the chain\?$/i.test(heard),
       '  and it is the right question, not some other sentence that happened to end in one');
    ok(/and (one|two|three|four) more steps? on the card\./.test(heard),
       'A STEP THAT CANNOT FIT IS ANNOUNCED: ' + JSON.stringify(heard),
       'the cap used to drop steps two, three and four in silence');
    const ordinals = (s) => (String(s).match(/\b(?:First|Second|Third|Fourth|Then),/g) || [])
      .length;
    const lost = ordinals(serverLine) - ordinals(heard);
    const owned = Number((/and (one|two|three|four) more/.exec(heard) || [])[1] &&
      ({ one: 1, two: 2, three: 3, four: 4 })[(/and (one|two|three|four) more/
        .exec(heard) || [])[1]]);
    ok(lost > 0 && owned === lost,
       '  and the number it announces is the number it actually dropped: ' + lost +
       ' lost, ' + owned + ' owned up to');
    ok(spokenForm('Bonsoir.') === 'Bonsoir.' &&
       spokenForm(serverLine.slice(0, 120)) === serverLine.slice(0, 120),
       '  and nothing under the cap is touched, so this is not a rewrite of every answer');
  }
  await page.evaluate('__galaxy.hands.close()');
  await fetch(GALAXY + '/tools', { method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ cmd: 'cancel', door: 'curl' }) });
  ok(await waitFor(page, '__galaxy.hands.shown === false', 8000),
     'the four-step plan is put down again and NOTHING in this round was ever approved');

  page.close();
}

main().catch((e) => { bad.push('the run itself: ' + e.message); console.log('\n  ERROR ' + e.message); })
  .finally(async () => {
    /* WHAT THIS RUN MADE, REMOVED BY NAME. The second step of a chain has to really happen
       or round 2 proves nothing, so this harness really does write a notes file - and then
       takes it away, by exact path, because the notes directory is the employer's. */
    MADE.forEach(f => {
      if (existsSync(f)) { try { unlinkSync(f); note('removed ' + f); } catch { } }
    });
    procs.forEach(p => { try { process.kill(p.pid); } catch { } });
    await sleep(600);
    profiles.forEach(p => { try { rmSync(p, { recursive: true, force: true }); } catch { } });
    console.log('\n  VERIFY ' + (checks - bad.length) + '/' + checks +
                (bad.length ? ' FAIL' : ' PASS') + '\n');
    bad.forEach(b => console.log('    FAILED: ' + b));
    process.exit(bad.length ? 1 : 0);
  });
