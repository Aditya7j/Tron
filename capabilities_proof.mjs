/* THE MANIFEST IS A MIRROR, NOT A BROCHURE - PART D's second half, proved by changing him.
 *
 * "What can you do" is the question an assistant is worst at. The easy way to answer it is a
 * paragraph of prose written by hand, and the paragraph is wrong the day after it is
 * written: a hand is added and he cannot name it, a hand is removed and he offers it. The
 * claim of this Part is that the answer is GENERATED - assembled at start-up out of the live
 * registry and the live organs - so that the list he recites and the list he can actually
 * run are the same list by construction.
 *
 * A fixture cannot prove that by reading the manifest, because a hard-coded paragraph and a
 * generated one look identical from outside. It can only prove it by CHANGING THE REGISTRY
 * AND SEEING HIM CHANGE. So this file fits a hand that has never existed - a canary - and
 * asks him what he can do:
 *
 *   BEFORE. He names every hand in the registry by its human name, and does not name the
 *     canary, which is the control: if he named it before it was fitted the rest would mean
 *     nothing.
 *   FITTED. The canary goes into tools/registry.json, the server is restarted by this
 *     fixture, and he names it - in the spoken answer he gives the boss AND in the model's
 *     own preamble, reached through a free-form question that is not the capabilities class.
 *     Failure mode: a manifest built once by hand, or built from the registry but never
 *     reaching the brain, so he recites the canary when asked directly and denies it when
 *     asked sideways.
 *   AND THE COUNT IS HIS OWN. The start-up line in the trace says how many hands he knows
 *     and names them. Failure mode: a manifest that grew a sentence without growing a hand.
 *   REMOVED. The registry goes back, the server is restarted again, and he stops naming it -
 *     and denies it if pressed. Failure mode is the dangerous direction: a capability that
 *     outlives the hand, so he offers to do something there is no longer any code for.
 *
 * WHY THIS ONE RESTARTS THE SERVER. _MANIFEST is built once at start-up and cached on
 * purpose: every token in it is paid on every brain call, and rebuilding it per request
 * would count the notes and stat the registry on the hot path. The mandate says restart, and
 * the reason it says restart is that the cache is correct. So this fixture owns the restart -
 * reading the pid from /focus/diag, killing it the way this machine requires, waiting for
 * the port to actually go dead, and starting a fresh one with its stderr still landing in
 * server-trace.log so the harnesses that read the trace keep working afterwards.
 *
 * THE REGISTRY IS RESTORED IN A finally, AND FROM MEMORY. tools/registry.json is real
 * configuration for real hands, one of which sends mail. It is read into memory before
 * anything is written, written back byte-for-byte at the end whatever happens - assertion
 * failure, exception, or a throw from Chrome - and a .bak is left on disk as well, so that a
 * process killed between the write and the restore can still be undone by hand. The canary
 * itself is inert: it names a script that does not exist, so even if consent were somehow
 * given there is nothing for it to run.
 *
 * Usage:  python server.py 2> server-trace.log   then   node capabilities_proof.mjs
 */
import { spawn, spawnSync } from 'node:child_process';
import { readFileSync, writeFileSync, copyFileSync, existsSync, statSync,
         openSync, unlinkSync } from 'node:fs';

const GALAXY = 'http://127.0.0.1:4700';
const PYTHON =
  'C:/Users/Fullstack Developer/AppData/Local/Programs/Python/Python313/python.exe';
const REGISTRY = 'tools/registry.json';
const BACKUP = 'tools/registry.json.capabilities-proof.bak';
const TRACE = 'server-trace.log';
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let pass = 0, fail = 0; const failures = [];
const say = (m) => console.log(m);
const ok = (c, claim, detail) => {
  if (c) pass++; else { fail++; failures.push(claim); }
  say((c ? '  ok   ' : '  FAIL ') + claim);
  if (!c && detail) say('         ' + detail);
};
const note = (m) => say('  note ' + m);
const step = (m) => say('\n  ·· ' + m);

/* THE CANARY. A hand with a human name no prose of mine would ever have written, so that
   finding it in his mouth can only mean he read the registry. Inert by construction: the
   script does not exist on disk, which _clean_tool permits and which means the worst case of
   a bug in this fixture is a proposal that cannot run. */
const CANARY_ID = 'water_the_ferns';
const CANARY_NAME = 'Water the ferns on the landing';
const CANARY = {
  id: CANARY_ID,
  name: CANARY_NAME,
  script: 'water_the_ferns.py',
  capabilities: [
    "water the ferns on the employer's landing",
    'see to the plants when they have gone a week without',
  ],
  triggers: ['\\bferns?\\b', '\\bwater\\s+the\\s+plants\\b'],
  params: [{ name: 'which', type: 'string', required: false }],
  timeout_s: 5,
  proposal: 'The ferns on the landing, sir - a full can each. Shall I?',
};

async function ask(question, session) {
  const r = await fetch(GALAXY + '/chat', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question, session: session || 'capabilities-proof' }),
  });
  let body = null;
  try { body = await r.json(); } catch (e) { body = null; }
  return { status: r.status, body: body || {} };
}
async function diag() {
  try {
    const r = await fetch(GALAXY + '/focus/diag');
    const j = await r.json();
    return j.diag || null;
  } catch (e) { return null; }
}
async function alive() { return (await diag()) !== null; }

/* THE RESTART, done the way this machine actually requires.
   Measured on this box and written down because it cost an afternoon once: a second
   server.py can bind 4700 while the first is still holding it, exit 1, and leave the OLD
   process answering every request - so a fixture that starts a server and then asserts on
   "the new behaviour" can be reading the old one all day. The only reliable sequence is:
   read the pid he reports himself, kill that pid with its children, wait until /focus/diag
   stops answering ALTOGETHER, and only then start one - and confirm the pid changed. */
async function restart(why) {
  const before = await diag();
  const oldPid = before ? before.pid : null;
  note('restarting: ' + why + (oldPid ? ' (pid ' + oldPid + ' has been up ' +
       before.uptimeS + 's)' : ' (nothing answering)'));
  if (oldPid) spawnSync('taskkill', ['/PID', String(oldPid), '/T', '/F'], { encoding: 'utf8' });
  let dead = false;
  for (let i = 0; i < 60 && !dead; i++) { dead = !(await alive()); if (!dead) await sleep(250); }
  if (!dead) { ok(false, 'the old server would not die - pid ' + oldPid); return null; }
  /* stderr APPENDED to the same log the running server writes, so the trace stays one
     continuous record and the harnesses that read it keep working after this file exits. */
  const fd = openSync(TRACE, 'a');
  const child = spawn(PYTHON, ['server.py'], {
    detached: true, stdio: ['ignore', 'ignore', fd], windowsHide: true,
  });
  child.unref();
  let now = null;
  for (let i = 0; i < 80 && !now; i++) { now = await diag(); if (!now) await sleep(250); }
  if (!now) { ok(false, 'the fresh server never came up'); return null; }
  ok(now.pid !== oldPid && now.uptimeS < 60,
     'AND IT IS GENUINELY A NEW SERVER: pid ' + oldPid + ' -> ' + now.pid + ', up ' +
     now.uptimeS + 's. Asserted rather than assumed, because on this machine a failed ' +
     'start leaves the old process answering and every claim after it would be a lie',
     JSON.stringify({ oldPid, now: now.pid, uptimeS: now.uptimeS }));
  return now;
}
/* The start-up line he writes about himself, taken from a mark so an older restart's line
   cannot be mistaken for this one's. */
function manifestLine(fromByte) {
  const buf = readFileSync(TRACE, 'utf8').slice(fromByte);
  const hits = buf.split(/\r?\n/).filter((l) => / knows \d+ hand/.test(l));
  return hits.length ? hits[hits.length - 1] : '';
}
const traceSize = () => (existsSync(TRACE) ? statSync(TRACE).size : 0);

/* WHAT HE SAYS WHEN ASKED OUTRIGHT, and what the model was told behind it. Two readings of
   the same fact, because they come from two renderings of one build and a bug in either one
   is invisible from the other. */
async function askedOutright() {
  const r = await ask('galaxy what can you do', 'capabilities-direct-' + Date.now());
  return { answer: String(r.body.answer || ''), body: r.body };
}
/* THE SAME QUESTION, ASKED IN EVERY STATE. This replaced a probe that passed for the wrong
   reason and is worth recording, because the wrong reason is the one the mandate names: I
   first asked "the plants on the landing are looking dreadful, is that something you could
   help with" and accepted any mention of plants as evidence. He answered it from the WEB - a
   page of plant-care symptom checkers - and the word "plants" in that answer made the
   assertion green while proving nothing whatever about the manifest.
   The fix is not a tighter word list. It is a question whose ANSWER MUST CHANGE when the
   registry changes: one sentence, asked before the canary is fitted, after it is fitted, and
   after it is removed. Before and after removal he must say he has not got the hand; while it
   is fitted he must not. The wording is his own in all three, the question is identical in
   all three, and no echo of my phrasing and no web page can produce that pattern - only
   having read the registry can. It is also deliberately a request TO him in the second
   person rather than a question about the world, so the web gate stays shut and the answer
   comes from the preamble. */
const SIDEWAYS = 'could you water the ferns on the landing for me';

/* AND MEASURED ON WHAT HAPPENS, NOT ON HOW HE PUTS IT. This is the third phrasing list to
   fail in this round and the last one I shall write. It fell over on a perfect refusal:
   "that would require hands of a rather more botanical sort than I've been given, sir - the
   ferns must fend for themselves", which declines flatly and contains NO NEGATION WORD AT
   ALL. The refusal is comparative. No list of negations can see it, and any list I write is
   a list of the ways I would have said it.
   The structural fact is better evidence anyway, because it is the thing the boss actually
   experiences: DOES A PROPOSAL COME UP. A hand he has is offered for a yes - that is the
   gate's whole contract - and a hand he has not got cannot be, because there is nothing in
   the registry to surface. So the claim is that a proposal for the canary appears if and only
   if the canary is fitted. It is binary, it is phrasing-proof, and it is what "he can do it"
   means here.
   The prose is still printed at every state, because the boss reads prose and a reviewer
   should see it - but it is evidence for his eye, not a pattern for mine. What IS asserted
   about the prose is one thing only, and in the negative: while he has no such hand he must
   not promise to do it anyway. An undertaking with no gate behind it is the failure that
   would matter, and it needs no vocabulary to detect - only first-person future beside the
   verb in the question. */
async function askedSideways(label) {
  const r = await ask(SIDEWAYS, 'capabilities-free-' + Date.now());
  const answer = String(r.body.answer || '');
  const pending = r.body.pending || null;
  const offered = !!pending && pending.tool === CANARY_ID;
  const promised =
    /\bI(?:'ll|'m| will| shall| have| am)\s+(?:now\s+|just\s+)?(?:water|watered|watering|see(?:n)? to|seeing to|fetch|attend)/i
      .test(answer);
  note(label + ': route ' + JSON.stringify(r.body.route) +
       (pending ? ' · PROPOSED ' + pending.tool : ' · no proposal') +
       ' · "' + answer.slice(0, 200) + '"');
  return { answer, pending, offered, promised, body: r.body };
}
const withdraw = () => fetch(GALAXY + '/tools', {
  method: 'POST', headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ cmd: 'withdraw' }),
}).catch(() => null);

say('\n  CAPABILITIES PROOF - a hand fitted today is a capability he can name today');

if (!(await alive())) {
  say('\n  the server on 4700 is not answering; start it first: python server.py');
  process.exit(1);
}
const original = readFileSync(REGISTRY);            /* bytes, before anything is touched */
copyFileSync(REGISTRY, BACKUP);
note('the registry is ' + original.length + ' bytes; a byte copy is at ' + BACKUP);

try {
  /* ---- 1. BEFORE: the control -------------------------------------------------- */
  step('before the canary is fitted');
  const reg0 = JSON.parse(original.toString('utf8'));
  const ids0 = reg0.tools.map((t) => t.id);
  const names0 = reg0.tools.map((t) => t.name.trim().replace(/\.$/, ''));
  note('the registry holds ' + ids0.length + ' hands: ' + ids0.join(', '));
  ok(ids0.indexOf(CANARY_ID) < 0,
     'THE CANARY IS NOT A REAL HAND: "' + CANARY_ID + '" is in no registry on this ' +
     'machine, so every later sighting of it is caused by this fixture and nothing else',
     JSON.stringify(ids0));

  const before = await askedOutright();
  note('asked outright: "' + before.answer.slice(0, 260) + '"');
  const missing0 = names0.filter((n) => before.answer.indexOf(n) < 0);
  ok(missing0.length === 0,
     'HE ALREADY NAMES EVERY HAND HE HAS: all ' + names0.length + ' human names from the ' +
     'registry appear in the answer he gives the boss - not a summary of them, the names ' +
     'themselves. A manifest that dropped a hand would leave the boss unable to ask for it',
     JSON.stringify({ missing0, answer: before.answer }));
  ok(before.answer.toLowerCase().indexOf('fern') < 0,
     'AND HE DOES NOT NAME THE CANARY YET, which is the control this whole file rests on',
     JSON.stringify(before.answer));
  await withdraw();
  const side0 = await askedSideways('asked sideways, before');
  ok(!side0.offered && !side0.promised,
     'AND ASKED FOR IT OUTRIGHT NOTHING IS OFFERED: "' + SIDEWAYS + '" - a request to him ' +
     'rather than a question about the world, so the web gate stays shut and the answer ' +
     'comes from the preamble - and with no such hand in the registry no proposal comes up ' +
     'and he promises nothing in prose either. The first of three readings of one unchanged ' +
     'sentence',
     JSON.stringify({ offered: side0.offered, promised: side0.promised,
                      answer: side0.answer }));
  await withdraw();

  /* ---- 2. FITTED --------------------------------------------------------------- */
  step('the canary is fitted and the server restarted');
  const reg1 = JSON.parse(original.toString('utf8'));
  reg1.tools.push(CANARY);
  writeFileSync(REGISTRY, JSON.stringify(reg1, null, 1) + '\n');
  const mark1 = traceSize();
  const up1 = await restart('a hand was added to the registry');
  if (!up1) throw new Error('no server after the first restart');
  const line1 = manifestLine(mark1);
  note('he wrote at start-up: ' + line1.trim());
  /* COUNTED, NOT TYPED. `ids0.length` is what the registry held before the canary went in,
     so the number expected here is that plus one - and it stays right the next time a hand
     is added to the registry, which is exactly the property the assertion is about. A
     literal here would have to be edited by whoever adds the eighth hand, and an assertion
     that has to be edited to keep passing has stopped being evidence. */
  const fittedCount = ids0.length + 1;
  ok(new RegExp('knows ' + fittedCount + ' hands').test(line1) &&
     line1.indexOf(CANARY_ID) >= 0,
     'HE COUNTED THE NEW HAND HIMSELF: the start-up line says ' + fittedCount +
     ' and names ' + CANARY_ID +
     ' - the manifest counted the registry rather than repeating a number I typed',
     JSON.stringify(line1));

  const fitted = await askedOutright();
  note('asked outright: "' + fitted.answer.slice(0, 300) + '"');
  ok(fitted.answer.indexOf(CANARY_NAME) >= 0,
     'AND HE OFFERS IT TO THE BOSS BY ITS HUMAN NAME: "' + CANARY_NAME + '" is in the ' +
     'spoken answer, a sentence no prose of mine contains. Nothing was retrained, nothing ' +
     'was re-written - a line of JSON was added and he can name it',
     JSON.stringify(fitted.answer));
  const stillAll = names0.filter((n) => fitted.answer.indexOf(n) < 0);
  ok(stillAll.length === 0,
     '       and the hands he already had are all still there: adding one did not drop one, ' +
     'which is what a manifest assembled by concatenation would do at the first line wrap',
     JSON.stringify(stillAll));

  /* THE OTHER RENDERING. "what can you do" is a protected class answered from the spoken
     manifest, so on its own it proves only that ONE string was built from the registry. The
     model's preamble is a different rendering of the same build, and this reaches it the
     only way a fixture can: a question that is not protected, whose honest answer requires
     having read the list. */
  await withdraw();
  const side1 = await askedSideways('asked sideways, fitted');
  /* THE SAME SENTENCE, THE SECOND READING - and the gate is the evidence. The hand exists
     now, so the sentence that got nothing a moment ago must surface a proposal naming it,
     put to him for a yes like every other hand. Still gated: he offers, he does not act. */
  ok(side1.offered && side1.pending.tool === CANARY_ID,
     'AND THE SAME SENTENCE NOW RAISES THE HAND: "' + SIDEWAYS + '" asked again, unchanged, ' +
     'and this time a proposal comes up naming ' + CANARY_ID + ' - "' +
     String((side1.pending || {}).line || '').slice(0, 80) + '". One question, two registry ' +
     'states, two opposite outcomes, and the difference is a line of JSON. No echo of my ' +
     'phrasing and no web page can produce that; only having read the registry can',
     JSON.stringify({ offered: side1.offered, pending: side1.pending,
                      answer: side1.answer }));
  ok(!!side1.pending && side1.pending.tool === CANARY_ID && !/\b(?:done|watered|I have watered)\b/i.test(side1.answer),
     '       and it is OFFERED, not done: a hand fitted one minute ago still goes through ' +
     'the consent gate like every other, which is the one property of the Hands pipeline ' +
     'that must not be reachable around',
     JSON.stringify({ pending: side1.pending, answer: side1.answer }));
  await withdraw();
  /* And the hand is genuinely reachable, not just describable: the registry the gate reads
     is the registry the manifest read. One door, not two. */
  const pub = await (await fetch(GALAXY + '/tools')).json();
  ok((pub.tools || []).some((t) => t.id === CANARY_ID),
     '       and the gate can see the same hand the manifest described, so what he offers ' +
     'and what he could be asked to run are one list',
     JSON.stringify((pub.tools || []).map((t) => t.id)));

  /* ---- 3. REMOVED: the dangerous direction ------------------------------------- */
  step('the canary is removed and the server restarted again');
  writeFileSync(REGISTRY, original);
  const mark2 = traceSize();
  const up2 = await restart('the hand was taken back out of the registry');
  if (!up2) throw new Error('no server after the second restart');
  const line2 = manifestLine(mark2);
  note('he wrote at start-up: ' + line2.trim());
  ok(new RegExp('knows ' + ids0.length + ' hands').test(line2) &&
     line2.indexOf(CANARY_ID) < 0,
     'HE STOPPED COUNTING IT: back to ' + ids0.length + ', and the canary is not among them',
     JSON.stringify(line2));
  const gone = await askedOutright();
  note('asked outright: "' + gone.answer.slice(0, 200) + '"');
  ok(gone.answer.indexOf(CANARY_NAME) < 0 && gone.answer.toLowerCase().indexOf('fern') < 0,
     'AND HE NO LONGER OFFERS IT: the capability died with the hand. This is the direction ' +
     'that matters - a manifest which kept the sentence after the code went would have him ' +
     'promising the boss something there is nothing left to run',
     JSON.stringify(gone.answer));
  await withdraw();
  const side2 = await askedSideways('asked sideways, removed');
  ok(!side2.offered && !side2.promised,
     'AND THE SAME SENTENCE STOPS RAISING IT: the third reading of "' + SIDEWAYS + '" - no ' +
     'proposal, no promise. The full arc of one unchanged question is nothing, offered, ' +
     'nothing, tracking the registry underneath it in BOTH directions. This end of the arc ' +
     'is the one that matters: a capability which outlived its hand would have him offering ' +
     'the boss something there is no longer any code to run',
     JSON.stringify({ offered: side2.offered, promised: side2.promised,
                      answer: side2.answer }));
  await withdraw();
} finally {
  /* THE REGISTRY GOES BACK WHATEVER HAPPENED. From the bytes read before the first write,
     compared after writing, and the .bak only removed once the comparison passes - so the
     one outcome this file will not produce is a machine left with a hand it should not have
     and no copy of what it used to have. */
  writeFileSync(REGISTRY, original);
  const back = readFileSync(REGISTRY);
  const identical = Buffer.compare(back, original) === 0;
  ok(identical && JSON.parse(back.toString('utf8')).tools.every((t) => t.id !== CANARY_ID),
     'AND THE REGISTRY IS BYTE-FOR-BYTE WHAT IT WAS: ' + back.length + ' bytes restored ' +
     'from memory in a finally, canary gone. A fixture that edits real configuration owes ' +
     'this assertion more than it owes any of the others',
     JSON.stringify({ identical, was: original.length, now: back.length }));
  if (identical) { try { unlinkSync(BACKUP); } catch (e) { /* leave it, it is harmless */ } }
  else note('THE BACKUP HAS BEEN LEFT AT ' + BACKUP + ' - restore it by hand');
  const last = await diag();
  if (!last) {
    note('no server is answering; start one: python server.py 2> server-trace.log');
  } else {
    note('the server now answering 4700 is pid ' + last.pid + ', up ' + last.uptimeS +
         's, stderr appended to ' + TRACE);
  }
}

say('\n  VERIFY ' + pass + '/' + (pass + fail) + (fail ? ' FAIL' : ' PASS'));
if (fail) { say(''); for (const f of failures) say('    FAILED: ' + f); }
process.exit(fail ? 1 : 0);
