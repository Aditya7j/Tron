/* THE REWRITER, and THE LAW it is not allowed to break.
 *
 * The complaint was concrete: ask "what is react", follow up with "who created it?", and
 * the search went out with the pronoun still in it - so the web answered about the man who
 * created the World Wide Web. A follow-up has to inherit its predecessor's subject BEFORE
 * the search is fired, and it has to do so without ever putting a word in the employer's
 * mouth.
 *
 * Those two halves pull in opposite directions, which is why this runs in a real browser
 * against a real search rather than in the hermetic battery: the thing being proved is that
 * ONE sentence goes out to DuckDuckGo while a DIFFERENT sentence stays on the screen, and
 * both of those are observable facts about a running system.
 *
 * The sequence, once, nothing mocked:
 *
 *   ask "what is react"           -> a web answer; the memory now holds that question
 *   ask "who created it?"         -> the card and the sources panel quote "who created it?"
 *                                    the reply's searchedFor says "who created react"
 *                                    the sources are Walke / Facebook / react.dev, and
 *                                    Tim Berners-Lee is nowhere in them
 *                                 -> and the SERVER's own trace log says the same thing,
 *                                    read off disk, because the log is what a human would
 *                                    check at three in the morning
 *   ask "what is svelte"          -> a fresh subject, and then TWO NON-QUESTIONS over it:
 *   ask "ok got it"               -> a backchannel: one line, no search, no rewrite
 *   ask "translate good evening
 *        into french"             -> a TASK: kind compose, no search, no sources panel,
 *                                    no chips and nothing to attribute
 *   ask "who made it?"            -> and it STILL searches for Svelte, which is the proof
 *                                    that neither non-question touched the memory
 *   ask "draft an email to ..."   -> a task with a registry tool behind it, so the
 *                                    PROPOSAL path owns it: buttons and rendered
 *                                    parameters, still zero searches. Then "no".
 *   ask "who is <that address>"   -> the PII shield: held, said out loud, nothing sent
 *   press the real ↻ button       -> the conversation is forgotten, memory included
 *   ask "who created it?" again   -> searchedFor is the pronoun, verbatim, unrewritten
 *
 * The last step is the one that keeps the feature honest. A rewriter with nothing to
 * inherit from must search what it was given; inventing a subject out of an empty memory
 * would be worse than the bug this fixes.
 *
 * Headless, because nothing here is about a window. It reads the server's trace from
 * server-trace.log, or from a path given as argv[2]; with no readable log every check
 * still runs except the two that quote it.
 *
 * Usage:  python server.py 2> server-trace.log   then   node followup_proof.mjs
 */
import { spawn } from 'node:child_process';
import { mkdtempSync, rmSync, existsSync, readFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const GALAXY = 'http://127.0.0.1:4700';
const VIEW = GALAXY + '/?mute=1';
const PORT = 9227;
const CDP = 'http://127.0.0.1:' + PORT;
/* The server's stderr, which is where the lookup trace goes. Start the server with
   `python server.py 2> server-trace.log` and this finds it with no argument at all. */
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
      throw new Error('page threw: ' + r.result.exceptionDetails.text);
    }
    return r.result && r.result.result ? r.result.result.value : undefined;
  }
  async json(e) { return JSON.parse(await this.evaluate('JSON.stringify(' + e + ')') || 'null'); }
  close() { try { this.ws.close(); } catch { } }
}
const cdp = async (p) => { const r = await fetch(CDP + p); const t = await r.text();
  try { return JSON.parse(t); } catch { return t; } };

async function waitFor(page, expr, ms = 8000) {
  for (let i = 0; i < ms / 200; i++) {
    try { if (await page.evaluate(expr)) return true; } catch { }
    await sleep(200);
  }
  return false;
}

/* Every /chat reply the PAGE received, recorded by wrapping fetch rather than by asking
   the server again: the claim is about what the viewer was told and what it then chose to
   display, so a second identical request would be answering a different question. */
const TAP = `(function () {
  if (window.__tap) return 'already';
  window.__tap = [];
  var real = window.fetch.bind(window);
  window.fetch = function (url, init) {
    var body = init && init.body ? String(init.body) : '';
    return real(url, init).then(function (res) {
      var path = String(url);
      if (path.indexOf('/chat') >= 0 || path.indexOf('/reset') >= 0) {
        var copy = res.clone();
        copy.json().then(function (d) {
          window.__tap.push({ path: path, sent: body, got: d });
        }).catch(function () { });
      }
      return res;
    });
  };
  return 'wrapped';
})()`;

/* One turn, the way a hand does it: put it in ask() and wait for the page's own reply
   counter to move. The card is read AFTER that, so there is no race with rendering. */
async function turn(page, question, budget = 120000) {
  const before = await page.evaluate('window.__tap.filter(function(t){return t.path.indexOf("/chat")>=0}).length');
  await page.evaluate('__galaxy.ask(' + JSON.stringify(question) + ')');
  const got = await waitFor(page,
    'window.__tap.filter(function(t){return t.path.indexOf("/chat")>=0}).length > ' + before, budget);
  if (!got) throw new Error('no reply to ' + JSON.stringify(question) + ' within ' + budget + 'ms');
  await sleep(600);
  return page.json('(function(){var c=window.__tap.filter(function(t){' +
    'return t.path.indexOf("/chat")>=0});var last=c[c.length-1];' +
    'var p=document.getElementById("panel");return {' +
    'sent: JSON.parse(last.sent).question, got: last.got,' +
    'card: document.getElementById("a-q").textContent,' +
    'panel: document.getElementById("p-label").textContent,' +
    // The panel's own classes and the card's chips, for the turns whose whole claim is
    // that NOTHING was cited: a composed draft has no sources row and lights no note.
    'panelOpen: p.classList.contains("open"),' +
    'panelWeb: p.classList.contains("web"),' +
    'chips: document.getElementById("a-chips").children.length,' +
    'answer: document.getElementById("a-text").textContent.trim(),' +
    // The pair of buttons, and the parameter rows under them: the proposal a task with a
    // registry tool behind it has to produce, rendered, before anything runs.
    'proposal: document.getElementById("a-ask").classList.contains("show"),' +
    'rows: document.getElementById("ask-rows").textContent};})()');
}

/* How many live lookups the server has logged so far. "Zero searches" is a claim about
   what the server DID, so it is counted off disk rather than inferred from a reply. */
const lookups = () => (!LOG || !existsSync(LOG)) ? null
  : (readFileSync(LOG, 'utf8').match(/^ *web lookup /gm) || []).length;

const logSays = (re) => {
  if (!LOG || !existsSync(LOG)) return null;
  return re.test(readFileSync(LOG, 'utf8'));
};

const profiles = []; const procs = [];
async function main() {
  console.log('\n  the rewriter: one sentence out, another on the screen\n');
  const exe = CHROMES.find((p) => existsSync(p));
  if (!exe) throw new Error('no chrome.exe');
  if (!LOG) note('no server log path given; the two log checks will be skipped');
  else if (!existsSync(LOG)) note('log path does not exist: ' + LOG);

  const profile = mkdtempSync(join(tmpdir(), 'followup-'));
  profiles.push(profile);
  procs.push(spawn(exe, ['--headless=new', '--remote-debugging-port=' + PORT,
    '--user-data-dir=' + profile, '--no-first-run', '--no-default-browser-check',
    '--window-size=1280,900', VIEW], { detached: true, stdio: 'ignore' }));
  for (let i = 0; i < 80; i++) { try { await cdp('/json/version'); break; } catch { await sleep(250); } }
  let target = null;
  for (let i = 0; i < 40; i++) {
    const l = await cdp('/json/list');
    target = (Array.isArray(l) ? l : []).filter(t => t.type === 'page').find(t => t.url.includes('mute=1'));
    if (target) break; await sleep(300);
  }
  if (!target) throw new Error('no viewer page');
  const page = new Page(target.webSocketDebuggerUrl);
  await page.open();
  await page.send('Runtime.enable');
  ok(await waitFor(page, '!!(window.__galaxy && window.__galaxy.ask)', 30000),
     'the viewer is up and will take a question');
  await waitFor(page, '__galaxy.nodes.length > 0', 20000);
  await page.evaluate(TAP);

  /* A clean slate first, through the same button the last act uses - so the run does not
     inherit a subject from whatever was asked before it started. */
  await page.evaluate('document.getElementById("reset").click()', true);
  await sleep(800);

  /* ---- 1. the predecessor ------------------------------------------------ */
  const first = await turn(page, 'what is react');
  note('1: ' + JSON.stringify(first.got.searchedFor) + ' -> kind=' + first.got.kind);
  ok(first.got.kind === 'web' && first.got.searchedFor === 'what is react',
     'the first question went out as itself: ' + JSON.stringify(first.got.searchedFor),
     JSON.stringify({ kind: first.got.kind, searchedFor: first.got.searchedFor }));
  ok(!first.got.rewrote, 'and nothing was rewritten - there was nothing to inherit');

  /* ---- 2. the bare follow-up: two sentences, two places ------------------ */
  const second = await turn(page, 'who created it?');
  const sent = String(second.got.searchedFor || '');
  const srcs = (second.got.sources || []).map(s => (s.title || '') + ' ' + (s.url || ''));
  note('2: asked ' + JSON.stringify(second.sent) + ', searched ' + JSON.stringify(sent) +
       ' [' + (second.got.rewrote || 'verbatim') + ']');
  srcs.forEach(s => note('   source: ' + s.slice(0, 96)));

  ok(second.card === '\u201cwho created it?\u201d',
     'THE LAW, on the card: it quotes the employer word for word',
     JSON.stringify(second.card));
  ok(second.panel === 'who created it?',
     'THE LAW, in the sources panel: the same words again, not the rewrite',
     JSON.stringify(second.panel));
  ok(!/react/i.test(second.card) && !/react/i.test(second.panel),
     'nothing on the screen claims they said "React"');

  ok(/\breact\b/i.test(sent),
     'THE REWRITE: the query that left the machine names React',
     'searchedFor=' + JSON.stringify(sent));
  ok(!/\b(it|its|it\u2019s)\b/i.test(sent),
     'and the pronoun is gone from it, which is the whole complaint',
     'searchedFor=' + JSON.stringify(sent));
  ok(second.got.rewrote === 'quick' || second.got.rewrote === 'heuristic',
     'the reply says how it was rewritten: ' + JSON.stringify(second.got.rewrote));
  ok(sent !== second.sent,
     'so the sentence searched is NOT the sentence asked - by design',
     JSON.stringify({ asked: second.sent, searched: sent }));

  ok(srcs.length > 0 && srcs.some(s => /walke|facebook|react\.dev|react/i.test(s)),
     'the ' + srcs.length + ' sources are about React',
     JSON.stringify(srcs));
  ok(!srcs.some(s => /berners|world wide web|w3\.org/i.test(s)),
     'and Tim Berners-Lee is nowhere among them - the old wrong answer is gone',
     JSON.stringify(srcs.filter(s => /berners|world wide web|w3\.org/i.test(s))));

  /* ---- 3. and the log a human would actually read ------------------------ */
  const traced = logSays(/web lookup \([^)]*\) '[^']*react[^']*' \[(quick|heuristic) rewrite of 'who created it\?'\]/i);
  if (traced === null) note('skipped the log checks: no readable log');
  else {
    ok(traced === true,
       'the server trace log shows the rewritten query and what it was a rewrite OF');
    ok(logSays(/a bare follow-up: 'who created it\?' after 'what is react'/) === true,
       'and names the predecessor it inherited from');
  }

  /* ---- 4. THE TWO NON-QUESTIONS, and the subject that survives them -------
     An acknowledgment and a task are both messages that ask nothing, and the memory this
     whole file is about must stand through either of them. The sequence is one subject and
     two interruptions:

       "what is svelte"                       - a real question; the memory holds it
       "ok got it"                            - a BACKCHANNEL: one line, nothing spent
       "translate good evening into french"   - a TASK: composed, nothing searched
       "who made it?"                         - and it STILL inherits Svelte

     The last line is the point. If either interruption had written itself into the memory,
     the follow-up would have inherited "ok got it" or a request about French, and the
     politest and the most useful turns in the conversation would be the two that broke it. */
  const spentBefore = lookups();
  const subject = await turn(page, 'what is svelte');
  note('4: ' + JSON.stringify(subject.got.searchedFor) + ' -> kind=' + subject.got.kind);
  ok(subject.got.kind === 'web',
     'a fresh subject, asked and answered from the web',
     JSON.stringify({ kind: subject.got.kind, searchedFor: subject.got.searchedFor }));

  const ack = await turn(page, 'ok got it');
  note('4b: ' + JSON.stringify(ack.got.answer).slice(0, 96));
  ok(ack.got.kind === 'chat' && ack.got.backchannel === true,
     'THE BACKCHANNEL: kind=chat, and the reply says which door it came out of',
     JSON.stringify({ kind: ack.got.kind, backchannel: ack.got.backchannel }));
  ok(!('searchedFor' in ack.got) && !('sources' in ack.got) && !('rewrote' in ack.got),
     'nothing was searched and nothing was rewritten for it',
     Object.keys(ack.got).sort().join(','));
  ok(!/svelte/i.test(ack.got.answer || ''),
     'and it did not ANSWER again: no second lecture about Svelte',
     JSON.stringify(ack.got.answer));
  ok(ack.panel === 'what is svelte',
     'no new sources panel was opened for it - the label is still the old question',
     JSON.stringify(ack.panel));

  const task = await turn(page, 'translate good evening into french');
  note('4c: ' + JSON.stringify(task.got.answer).slice(0, 110));
  ok(task.got.kind === 'compose',
     'THE THIRD DOOR: a task is neither notes nor web - kind=compose',
     JSON.stringify({ kind: task.got.kind }));
  ok(!('searchedFor' in task.got) && !('searched' in task.got) && !('sources' in task.got),
     'ZERO SEARCHES: no searchedFor, no searched, no sources',
     Object.keys(task.got).sort().join(','));
  ok(Array.isArray(task.got.nodes) && task.got.nodes.length === 0 && task.chips === 0,
     'and no notes are lit behind prose the notes had no hand in',
     JSON.stringify({ nodes: task.got.nodes, chips: task.chips }));
  /* The panel is CLOSED, which is the claim: the one left open by the web answer two turns
     ago would otherwise sit under a sentence the assistant wrote itself and read as its
     provenance. Its `web` class survives the closing and is cleaned up by openPanel() the
     moment a note is shown - a class on a hidden element cites nothing. */
  ok(!task.panelOpen,
     'NO LIVE WEB PANEL - and the one left open by the last web answer was closed, so no '
     + 'sources row sits under a sentence it wrote itself',
     JSON.stringify({ open: task.panelOpen, web: task.panelWeb }));
  ok(!/according to/i.test(task.got.answer || '') && !/https?:\/\//.test(task.got.answer || ''),
     'no "ACCORDING TO" row and no link, because there is nothing to attribute',
     JSON.stringify(task.got.answer));
  ok(/bonsoir/i.test(task.got.answer || ''),
     'and it actually did the job: ' + JSON.stringify((task.got.answer || '').slice(0, 60)));

  /* "who created it?" rather than "who made it?", and the difference is worth a line: the
     notes contain the word "made" and do not contain "created", so "who made it?" scores
     above the relevance floor on its own and is answered - correctly - from the collection.
     The claim being tested here is about the MEMORY, so the follow-up has to be one the
     notes genuinely cannot answer, or the web gate never opens and the test proves
     nothing either way. */
  const inherited = await turn(page, 'who created it?');
  const heir = String(inherited.got.searchedFor || '');
  note('4d: searched ' + JSON.stringify(heir) + ' [' + (inherited.got.rewrote || 'verbatim') + ']');
  ok(/\bsvelte\b/i.test(heir),
     'THE MEMORY STOOD THROUGH BOTH: the follow-up still names Svelte',
     'searchedFor=' + JSON.stringify(heir));
  ok(!/\b(got it|french|translate|evening)\b/i.test(heir),
     'and inherited neither the acknowledgment nor the task', JSON.stringify(heir));
  ok(inherited.card === '“who created it?”',
     'THE LAW, unchanged: the card still quotes them', JSON.stringify(inherited.card));

  const spentAfter = lookups();
  if (spentBefore === null || spentAfter === null) note('skipped the lookup count: no log');
  else {
    ok(spentAfter === spentBefore + 2,
       'EXACTLY TWO lookups across those four turns - the two that were questions',
       'before=' + spentBefore + ' after=' + spentAfter);
    ok(logSays(/no lookup: 'ok got it' is an acknowledgment, nothing asked/) === true,
       'and the trace says why each was declined: the acknowledgment');
    ok(logSays(/no lookup: 'translate good evening into french' is a task; composed, not searched/) === true,
       'and the task');
  }

  /* ---- 5. THE TASK WITH HANDS BEHIND IT ----------------------------------
     "Draft an email" is a task too, and the third door is explicitly NOT where it goes: a
     registry tool matches it, so the proposal path owns it and the employer gets a pair of
     buttons and the parameters to read BEFORE anything is sent. Same door, chosen by
     whether a tool exists - not by the wording. */
  const ADDR = 'zqtask@example.invalid';
  const mail = await turn(page, 'draft an email to ' + ADDR + ' that I am fine');
  note('5: ' + JSON.stringify(mail.got.answer).slice(0, 110));
  ok(mail.got.kind === 'tool' && !!mail.got.pending,
     'THE PROPOSAL PATH OWNS IT: kind=tool, and something is pending',
     JSON.stringify({ kind: mail.got.kind, pending: !!mail.got.pending }));
  ok(!('searchedFor' in mail.got) && !('sources' in mail.got),
     'with zero searches on the way there', Object.keys(mail.got).sort().join(','));
  ok(mail.proposal && mail.rows.indexOf(ADDR) >= 0,
     'the parameters are RENDERED for reading before a word is given: '
     + JSON.stringify(mail.rows.slice(0, 120)));
  ok((mail.got.pending || {}).tool === 'send_email',
     'and it is the mailer that was proposed, named by id',
     JSON.stringify((mail.got.pending || {}).tool));

  /* Refused through the real NO button rather than by typing "no": while a proposal is
     pending the viewer answers a bare no against /tools, not /chat, so a typed refusal
     never reaches the endpoint this harness taps. The button is the honest gesture anyway -
     it is the one under the sentence. */
  const noBox = await page.json(
    '(function(){var r=document.getElementById("ask-no").getBoundingClientRect();' +
    'return {x:Math.round(r.left+r.width/2),y:Math.round(r.top+r.height/2)};})()');
  for (const type of ['mousePressed', 'mouseReleased']) {
    await page.send('Input.dispatchMouseEvent',
      { type, x: noBox.x, y: noBox.y, button: 'left', clickCount: 1 });
  }
  const gone = await waitFor(page,
    '!document.getElementById("a-ask").classList.contains("show")', 12000);
  ok(gone, 'and NO withdraws it, unrun - nothing was sent by this harness');
  ok(/let that go|as you wish|very good|not send|withdrawn|left it/i
     .test(await page.evaluate('document.getElementById("a-text").textContent')),
     'said once, in the butler\'s own words: '
     + JSON.stringify(await page.evaluate('document.getElementById("a-text").textContent')));

  /* ---- 6. THE PII SHIELD ------------------------------------------------- */
  const priv = await turn(page, 'who is ' + ADDR);
  note('6: ' + JSON.stringify(priv.got.answer).slice(0, 120));
  ok(priv.got.privateHeld === true && priv.got.kind === 'chat',
     'a question ABOUT an address is held: privateHeld, kind=chat',
     JSON.stringify({ kind: priv.got.kind, privateHeld: priv.got.privateHeld }));
  ok(/Private identifiers never leave this machine/.test(priv.got.answer || ''),
     'and it says so in one sentence rather than shrugging',
     JSON.stringify(priv.got.answer));
  /* No query and no sources, and the panel that is open is the PREVIOUS question's - the
     address is nowhere on the screen except in the card that quotes them, which is the one
     place it belongs. Testing "no panel at all" would be testing the last turn's tidiness
     rather than this turn's discretion. */
  ok(!('searchedFor' in priv.got) && !('sources' in priv.got)
     && priv.panel.indexOf(ADDR) < 0,
     'no query, no sources, and no sources panel quoting it - the address went nowhere',
     JSON.stringify({ keys: Object.keys(priv.got).sort().join(','), panel: priv.panel }));
  const spentEnd = lookups();
  if (spentEnd !== null && spentAfter !== null) {
    ok(spentEnd === spentAfter,
       'ZERO lookups across the email, the refusal and the held address (still '
       + spentEnd + ')', 'after=' + spentAfter + ' end=' + spentEnd);
    ok(logSays(/no lookup: a private identifier was in the message; the web was not asked/) === true,
       'and the trace says that one out loud too');
  }

  /* ---- 7. the ↻ button, pressed, and a follow-up with no history --------- */
  const box = await page.json(
    '(function(){var r=document.getElementById("reset").getBoundingClientRect();' +
    'return {x:Math.round(r.left+r.width/2),y:Math.round(r.top+r.height/2)};})()');
  for (const type of ['mousePressed', 'mouseReleased']) {
    await page.send('Input.dispatchMouseEvent',
      { type, x: box.x, y: box.y, button: 'left', clickCount: 1 });
  }
  const forgot = await waitFor(page,
    'window.__tap.some(function(t){return t.path.indexOf("/reset")>=0 && t.got && t.got.ok})', 8000);
  ok(forgot, 'the \u21bb button was pressed and the server confirmed the forgetting');

  const third = await turn(page, 'who created it?');
  const again = String(third.got.searchedFor || '');
  note('3: searched ' + JSON.stringify(again) + ' [' + (third.got.rewrote || 'verbatim') + ']');
  ok(again === 'who created it?' || again === 'who created it',
     'with the memory cleared the SAME follow-up is searched VERBATIM',
     'searchedFor=' + JSON.stringify(again));
  ok(!third.got.rewrote,
     'no rewrite is claimed, because there was nothing to inherit',
     JSON.stringify(third.got.rewrote));
  ok(!/\breact\b/i.test(again),
     'and no subject was invented out of an empty memory',
     'searchedFor=' + JSON.stringify(again));
  ok(third.card === '\u201cwho created it?\u201d',
     'the card still quotes them, rewrite or no rewrite', JSON.stringify(third.card));
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
