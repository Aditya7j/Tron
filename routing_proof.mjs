/* routing_proof.mjs - THE FUNNEL, IN THE BOSS'S OWN SENTENCES, TYPED AND THEN SPOKEN.
   ==================================================================================
   PART A said it plainly: four protected classes above every retrieval, in funnel order,
   costing zero lookups, with the trace naming the class. PART H said how it is proved: the
   boss's real sentences, verbatim, "each asserting kind, lookup count and spoken class,
   typed and by voice".

   WHY BOTH COLUMNS EXIST, and it is not ceremony. The typed column is deterministic - the
   same twelve strings over HTTP, so a routing regression is caught at the wire with no room
   for a room. The spoken column is the only one that proves the thing the boss actually
   does: he talks, and what reaches the funnel is whatever the recogniser made of his voice.
   A sentence that routes perfectly when typed and arrives as something else when spoken has
   not passed, and only this column can tell.

   WHAT EACH ASSERTION IS FOR. Three numbers per sentence, and each catches a different lie:
     kind    - the door it came out of. A protected class that answers correctly FROM THE
               NOTES is the failure this Part exists to remove: right words, wrong road, one
               corpus change away from being wrong words too.
     lookups - what it cost. This is the only assertion that can tell "answered from state"
               from "searched and then happened to say the right thing", and it is measured
               at the wire, on the response the page acted on, not inferred.
     route   - the class named out loud, in the payload AND in the trace. PART A asks for
               the trace by name, so when server-trace.log is capturable this harness reads
               it and quotes the line; the lookbook's evidence is that line.

   HOW TO RUN IT
     node routing_proof.mjs              typed, then spoken (the full fixture)
     TYPED_ONLY=1 node routing_proof.mjs typed only - for a quick regression, NOT a pass
     SPOKEN_ONLY=1 node routing_proof.mjs the voice column alone

   The spoken column needs a real room: speakers, a microphone, and a headed Chrome. See
   tools/mouth.mjs, whose header records the eight findings that recipe is made of.

   AND IT HAS THREE OUTCOMES, NOT TWO, for reasons measured over three consecutive runs - see
   THE THIRD OUTCOME beside the scoreboard. A sentence the room mangled five times running is
   reported UNPROVEN rather than failed, because no routing decision was made to judge; the
   unproven are counted, named in the verdict line, and capped at two of thirteen, so a page
   that hears nothing still fails and fails in one line instead of thirteen.                */
import { spawn, spawnSync } from 'node:child_process';
import { existsSync, mkdtempSync, statSync, openSync, readSync, closeSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { Mouth, TAP, SPOKEN_FLAGS, pythonPresent } from './tools/mouth.mjs';

const GALAXY = 'http://127.0.0.1:4700';
const CDP_PORT = 9241;
const CDP = 'http://127.0.0.1:' + CDP_PORT;
const TRACE = process.env.TRACE || 'server-trace.log';
const TYPED_ONLY = !!process.env.TYPED_ONLY;
const SPOKEN_ONLY = !!process.env.SPOKEN_ONLY;
const CHROMES = ['C:/Program Files/Google/Chrome/Application/chrome.exe',
  process.env.LOCALAPPDATA + '/Google/Chrome/Application/chrome.exe'];
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

/* ---- the scoreboard ---- */
let pass = 0, fail = 0;
const failures = [];
/* ---- AND A THIRD OUTCOME, WHICH THE SPOKEN COLUMN ALONE NEEDS -----------------------------
   An assertion should fail when the thing under test is wrong. The thing under test in this
   file is the FUNNEL, and a sentence the room mangled five times running has told us nothing
   about it either way: the boss's words never arrived, so there was no routing decision to be
   right or wrong about. Counting that as a routing failure blames the wrong component - which
   is a rule this file already keeps one paragraph down, where a phrase the room invents between
   two fixtures is explicitly not the funnel's to answer for.
   MEASURED, BECAUSE THE BUDGET BELOW HAD TO COME FROM SOMEWHERE. Three consecutive runs of the
   full spoken column failed a DIFFERENT sentence each time and never the same one twice: first
   "switch your voice to joe" and "is my calendar connected", then "no no cancel that", then
   "what is the web gate". Each had five honest attempts and each was thrown away for the right
   reason - "Is my phone", "Sorry pap", "Hey can you take a video for me", and three attempts
   that came back empty altogether. A verdict that flips on which sentence the room fumbled is
   not a reading of the funnel.
   WHAT THIS DOES NOT LET THROUGH, and this is the whole design of it. Unproven is not a pass:
   it is counted, printed on its own line, named in the verdict, and BUDGETED. A page whose ear
   is broken, whose recogniser never starts, or whose microphone is muted puts every sentence in
   this bucket and fails on the budget - which is a better failure than today's, because it
   fails once with a count instead of thirteen times with thirteen explanations. A routing
   regression is untouched: the words arrive, the funnel answers, and the assertion runs. */
let unproven = 0;
const unprovens = [];
function cannotSay(claim, debug) {
  unproven++; unprovens.push(scrub(claim));
  say('  n/a  UNPROVEN ' + scrub(claim));
  if (debug !== undefined) say('         ' + scrub(String(debug)).slice(0, 700));
}
const say = (s) => console.log(s);
const step = (s) => say('\n  ·· ' + s);
const note = (s) => say('  note ' + s);
/* ---- THE SCRUB, AND IT IS A STANDING LAW RATHER THAN A TIDINESS -------------------------
   No account address may appear in a log, a plate or the lookbook except as a digest. The
   connection answers below quote the Command Panel's row verbatim, and when the grant is live
   that row reads "GOOGLE: CONNECTED · someone@gmail.com" - so the one honest sentence in this
   fixture is also the one that would put the boss's address into a file that gets pasted into
   a section of a book. Every printed answer goes through here.

   WHAT IT DOES NOT DO: it does not touch the assertion. okAnswer matches on "GOOGLE: " and
   the state word comes off the payload, so a scrubbed print cannot make a red row look green
   - the scrub is downstream of every judgement in this file. */
function scrub(s) {
  return String(s === undefined || s === null ? '' : s)
    .replace(/[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/g, '<address withheld>');
}
function ok(cond, claim, debug) {
  if (cond) { pass++; say('  ok   ' + scrub(claim)); return true; }
  fail++; failures.push(scrub(claim));
  say('  FAIL ' + scrub(claim));
  if (debug !== undefined) say('         ' + scrub(String(debug)).slice(0, 700));
  return false;
}

/* ---- the wire, typed ---- */
async function post(path, body) {
  const res = await fetch(GALAXY + path, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  });
  const text = await res.text();
  let json = null;
  try { json = JSON.parse(text); } catch (e) { json = { unparsed: text.slice(0, 300) }; }
  return { status: res.status, body: json };
}
const ask = (question, opts) => post('/chat', Object.assign(
  { question, session: 'routing-proof' }, opts || {}));

/* THE OFFER THIS HARNESS PUTS ON THE TABLE IS ALWAYS selftest. The standing rule is that
   preflight and every harness use tools/selftest.py and never send real mail - a fixture
   about the word "yes" must not be able to post a letter. */
const proposeSelftest = () => post('/tools', {
  cmd: 'propose', tool: 'selftest',
  params: { token: 'routing-proof' }, door: 'harness'
});
const clearSlot = () => post('/tools', { cmd: 'withdraw' });

/* ---- the trace, read rather than trusted ----
   THE FAILURE MODE THIS CATCHES IS A SILENT ROUTING CHANGE. A change that sent "who am i"
   back to the notes would still answer, and still answer correctly for a while; the line
   that would stop reading "route: identity" is the only cheap early warning there is. Read
   as bytes since a mark so nothing older than this sentence can be mistaken for it. */
function traceMark() {
  try { return statSync(TRACE).size; } catch (e) { return -1; }
}
function traceSince(mark) {
  if (mark < 0) return null;
  try {
    const size = statSync(TRACE).size;
    if (size <= mark) return '';
    const fd = openSync(TRACE, 'r');
    const buf = Buffer.alloc(size - mark);
    readSync(fd, buf, 0, buf.length, mark);
    closeSync(fd);
    return buf.toString('utf8');
  } catch (e) { return null; }
}
const TRACE_LIVE = traceMark() >= 0;

/* ================================ THE MATRIX ================================
   Every sentence here is one the boss actually said, kept verbatim - including the ones
   that are not quite sentences. `want` is the whole claim: which door, what it cost, and
   the class it must name. `setup` is the state the sentence arrives into, because half of
   PART A is about what a word means in context: "yes yes do it galaxy" is an execution with
   an offer standing and a refusal without one, and BOTH are requirements.               */
const MATRIX = [
  {
    say: 'can you listen to me', setup: 'none', ear: true,
    want: { status: 200, kind: 'chat', route: 'meta', lookups: 0 },
    answerHas: 'the ear is open',
    why: 'CLASS 2, META-CONVERSATIONAL. He is asking whether he is heard. Searching the ' +
         'notes for it is the defect; answering from the live ear is the feature.'
  },
  {
    say: 'can you listen to me', setup: 'none', ear: false, label: 'with the ear SHUT',
    want: { status: 200, kind: 'chat', route: 'meta', lookups: 0 },
    answerHas: 'the ear is shut',
    why: 'AND IT IS READ OFF THE LIVE STATE, not a hopeful fixed string: the same ' +
         'question with the ear shut must not claim the room is his. This is the ' +
         'frozen-level-reads-like-a-shut-mouth precedent, applied to a sentence.'
  },
  {
    say: 'hey galaxy are you there', setup: 'none', ear: true,
    want: { status: 200, kind: 'chat', route: 'meta', lookups: 0 },
    why: 'THE VOCATIVE AND THE PLEASANTRY COME OFF FIRST. This one peels to nothing at ' +
         'all - "there" is a greeting\u2019s second half - which is why the classes are ' +
         'tried against every rung of the peel and not only the last.'
  },
  {
    say: 'yes yes do it galaxy', setup: 'pending', label: 'with an offer standing',
    want: { status: 200, kind: 'tool', ok: true },
    want_pending: null, noRetrieval: true,
    why: 'CLASS 1, AFFIRMATIVE. Doubled, with his name on the end, and it is still a yes ' +
         'and nothing else. The failure mode: a yes that gets searched for instead of ' +
         'obeyed, and an offer left standing after he accepted it.'
  },
  {
    say: 'yes yes do it galaxy', setup: 'none', label: 'with NOTHING pending',
    want: { status: 409, kind: 'tool', route: 'confirmation', lookups: 0 },
    answerHas: 'Nothing is pending',
    why: 'AND A RELEASED CONFIRMATION IS NEVER SEARCHED. The words are consent with ' +
         'nothing to consent to: refused by name, at zero cost. Searching them would put ' +
         '"yes yes do it galaxy" to the notes and read something back.'
  },
  {
    say: 'ok do it', setup: 'pending',
    want: { status: 200, kind: 'tool', ok: true },
    want_pending: null, noRetrieval: true,
    why: 'The shortest yes he uses. Two words, no name, no punctuation.'
  },
  {
    say: 'no no cancel that', setup: 'pending',
    want: { status: 200, kind: 'tool' },
    want_pending: null, noRetrieval: true,
    why: 'CLASS 1, NEGATIVE. The failure mode is the expensive one: a no that is read as ' +
         'a new request, which withdraws the offer AND then searches the notes for the ' +
         'word "cancel".'
  },
  {
    say: 'switch your voice to joe', setup: 'none',
    want: { status: 200, kind: 'tool' }, want_pending: 'set_voice',
    answerHas: 'change the voice',
    why: 'CLASS 4, A DIRECTIVE - AND IT IS A REGISTRY HAND, WHICH THE MANDATE SAID TO LEAVE ' +
         'ALONE: "Third Door verbs and registry hands as built". So the right outcome is not ' +
         'a swap performed but a hand OFFERED: set_voice proposed, its parameters validated, ' +
         'waiting for a word. The DOOR is the claim. The price is printed and not asserted, ' +
         'because a registry hand is entitled to spend the trigger\u2019s own embedding ' +
         'working out which hand was meant, and pinning that number here would be this ' +
         'fixture legislating inside the Hands pipeline.'
  },
  {
    say: 'who are you', setup: 'none',
    want: { status: 200, kind: 'chat', route: 'identity', lookups: 0 },
    answerHas: 'Galaxy',
    why: 'CLASS 3, IDENTITY. From the persona block. A machine that has to look up who it ' +
         'is does not know.'
  },
  {
    say: 'who am i', setup: 'none',
    want: { status: 200, kind: 'chat', route: 'identity', lookups: 0 },
    answerHas: 'Aditya',
    why: 'AND HE IS NAMED IN FULL. The same class, the other direction: an assistant who ' +
         'cannot say whose he is.'
  },
  {
    say: "what's my name", setup: 'none',
    want: { status: 200, kind: 'chat', route: 'identity', lookups: 0 },
    answerHas: 'Addi',
    why: 'The warm form too - the answer names the formal address and the one he is ' +
         'called, because both are his.'
  },
  {
    say: 'galaxy what can you do', setup: 'none',
    want: { status: 200, kind: 'chat', route: 'identity', lookups: 0 },
    why: 'CLASS 3, CAPABILITIES, off the manifest built from the live registry at start - ' +
         'so a hand added tomorrow is named tomorrow. Asserted against the registry below ' +
         'rather than against a remembered sentence.'
  },
  /* ---- CLASS 3, CONTINUED: THE CONNECTION ------------------------------------------
     THE QUEUED NIT, AND IT WAS A REAL ONE. "How do I connect google" scores nothing against
     a collection of coffee notes, so it fell to the bottom of the funnel, where "the notes
     are thin" is the web gate's own cue - and the boss's question about the laptop in front
     of him bought a search engine's opinion on connecting Google Calendar to Outlook. Three
     rows, because the three shapes fail differently: the noun said outright, the noun
     pointed at, and the question that presumes the wrong answer.

     WHAT `answerHas` ASSERTS HERE is the part that keeps two voices in one house agreed. The
     Command Panel has a row whose LINE is the state, and the spoken answer quotes that line
     verbatim rather than paraphrasing it - so this fixture matches on "GOOGLE: ", which no
     paraphrase would ever contain, and on the words "Command Panel". If server.py's ladder
     and the panel's rowRead() ever drift apart, one of them stops containing the other's
     string and this row is where it shows.                                               */
  {
    say: 'how do i connect google', setup: 'none',
    want: { status: 200, kind: 'chat', route: 'identity', lookups: 0 },
    answerHas: 'GOOGLE: ', alsoHas: ['Command Panel'], wantsGoogleState: true,
    why: 'CLASS 3, THE CONNECTION, AND IT NAMES THE SWITCH. Read from the live /google ' +
         'state at zero cost. The failure mode this replaces is not a wrong answer but a ' +
         'wrong ROAD: the sentence used to reach the web gate, and a search engine cannot ' +
         'see this machine’s token file.'
  },
  {
    say: 'is my calendar connected', setup: 'none',
    want: { status: 200, kind: 'chat', route: 'identity', lookups: 0 },
    answerHas: 'GOOGLE: ', alsoHas: ['Command Panel'], wantsGoogleState: true,
    why: 'THE SAME CLASS IN THE WORDS HE USES FOR IT. "Calendar" and "mail" are the organs ' +
         'he thinks in; "Google" is the grant underneath. Both must arrive at the same ' +
         'reading, or the answer depends on which word he happened to reach for.'
  },
  {
    say: 'why is it not connected', setup: 'none', label: 'the noun pointed at, nothing pending',
    want: { status: 200, kind: 'chat', route: 'identity', lookups: 0 },
    answerHas: 'GOOGLE: ', alsoHas: ['Command Panel'], wantsGoogleState: true,
    why: 'THE DEICTIC RUNG, AND IT IS DELIBERATELY NARROWER THAN THE OTHER TWO: "it" is ' +
         'also how a standing offer is referred to, and this funnel is consulted before ' +
         'about_the_proposal(). So it answers here, with nothing pending - and the row ' +
         'below proves it stands down when there IS something on the card.'
  },
  {
    say: 'why is it not connected', setup: 'pending', label: 'with an offer standing',
    want: { status: 200 }, notConnection: true, noRetrieval: true,
    why: 'AND THE SAME SENTENCE IS NOT THE CONNECTION WHEN SOMETHING IS ON THE CARD. He is ' +
         'looking at a proposal and asking about IT. The failure mode if this rung did not ' +
         'stand down: a question about the invitation in front of him answered with a ' +
         'lecture about OAuth, and the offer neither executed nor released.'
  },
  {
    say: 'tell me about the meeting minutes', setup: 'none',
    want: { status: 200, kind: 'notes', minLookups: 1 },
    notProtected: true,
    why: 'AND THE FUNNEL DOES NOT SWALLOW A REAL QUESTION. This one is HIS: it is about ' +
         'his notes, it must reach them, and it must cost what a retrieval costs. A ' +
         'protected class that grew until it caught this would be a machine that stopped ' +
         'reading his own files. IT USED TO ASK ABOUT AN INVOICE IMPORTER, and PART 8 is ' +
         'why it does not. The importer was a note in the demonstration corpus; once that ' +
         'corpus was quarantined the sentence went to the WEB - and this row went on ' +
         'passing, because all it demanded was a status and a lookup, and a web search is ' +
         'a lookup. A fixture whose stated reason has quietly stopped describing what ' +
         'happens is worse than a red: it is a row of evidence for a claim nobody is ' +
         'testing any more. So it now names something his own files actually hold, and ' +
         'kind=notes is asserted outright so the door it went through is pinned, not ' +
         'inferred from a count that two different doors can both produce.'
  },
  {
    say: 'what is react', setup: 'none',
    want: { status: 200, minLookups: 1 },
    notProtected: true,
    why: 'THE ONE THE MANDATE EXPECTED TO GO TO THE WEB, and on this corpus it does not: ' +
         'the meaning-only notes door opens at 0.614 against a 0.60 threshold on the ' +
         'Astra prompt-pack PDF. The threshold and the retrieval mechanics are ' +
         'DO-NOT-ALTER, so what is asserted here is what the gate actually guarantees - ' +
         'not protected, and it costs a lookup. The web door is proved by the sentence ' +
         'below, which the notes measurably do not hold.'
  },
  {
    say: 'what is the web gate', setup: 'none',
    want: { status: 200, kind: 'web', minLookups: 1 },
    notProtected: true,
    why: 'THE WEB DOOR, on a question the notes hold 0.00 of - measured, in the trace, ' +
         'not chosen because it sounded worldly. A Web Gate assertion that quietly ' +
         'passed through the notes would prove nothing about the web at all.'
  },

  /* ==================== §29: THE ROOM, ASKED FOR ====================
     Five phrasings of one instruction, and they are the five the mandate names rather than
     five this file invented, because the point of them is COVERAGE OF A RECOGNISER: the
     on-device ear writes "full screen", the cloud writes "fullscreen", a keyboard writes
     "full-screen", and a phrasing that only works in one of the three spellings is a feature
     that works for whoever happened to be testing it.

     WHY `lookups: 0` IS THE LOAD-BEARING NUMBER HERE. Before §29 all five of these sentences
     reached the NOTES door and cost a retrieval each - measured on the stale server this run
     replaced, which answered "switch to full screen" with "That particular lever was never
     fitted to me, sir", kind=notes, lookups=1. So the regression this row catches is not
     hypothetical and is not "the wrong words": it is an instruction being researched instead
     of obeyed. The funnel either recognises the instruction above every retrieval or the deck
     pays a model call to explain why it cannot do the thing it can do.

     AND `noChips` IS THE CLAIM THE MANDATE MAKES IN ITS OWN WORDS - "with zero chips". An
     obeyed instruction has nothing to cite. A citation on this answer would mean the sentence
     went somewhere and came back, which is the failure above wearing the right words. */
  {
    say: 'switch to full screen', setup: 'none',
    want: { status: 200, kind: 'chat', route: 'fullscreen', lookups: 0 },
    wantsFullscreen: 'on', noChips: true, answerHas: 'Filling the screen',
    why: '§29, THE ROOM ASKED FOR IN WORDS. A fifth route above every retrieval, and the ' +
         'four protected CLASSES are untouched: PROTECTED_CLASSES is still exactly four, and ' +
         'this rides as payload fields the way `clock` already does. The failure mode: an ' +
         'instruction answered as a question, which is what this sentence did yesterday.'
  },
  {
    say: 'go full screen', setup: 'none',
    want: { status: 200, kind: 'chat', route: 'fullscreen', lookups: 0 },
    wantsFullscreen: 'on', noChips: true,
    why: 'THE SHORTEST FORM, and the one an impatient person actually says. It is here ' +
         'because a regex anchored a word too tightly would take the long form and drop this.'
  },
  {
    say: 'make it full screen', setup: 'none',
    want: { status: 200, kind: 'chat', route: 'fullscreen', lookups: 0 },
    wantsFullscreen: 'on', noChips: true,
    why: 'WITH A PRONOUN IN IT. "it" is the deck, and no antecedent memory is consulted to ' +
         'know that - which is the point: the instruction is recognised by its shape, so a ' +
         'cleared antecedent cannot make the room stop obeying.'
  },
  {
    say: 'fill the screen', setup: 'none',
    want: { status: 200, kind: 'chat', route: 'fullscreen', lookups: 0 },
    wantsFullscreen: 'on', noChips: true,
    why: 'AND THE ONE WITH NEITHER SPELLING OF THE WORD IN IT. This row is the reason the ' +
         'matcher is a set of forms and not a substring search for "fullscreen".'
  },
  {
    say: 'exit full screen', setup: 'none',
    want: { status: 200, kind: 'chat', route: 'fullscreen', lookups: 0 },
    wantsFullscreen: 'off', answerHas: 'Back to the window', noChips: true,
    why: 'THE WAY BACK, AND IT IS A DIFFERENT INSTRUCTION AND NOT A TOGGLE. The mandate says ' +
         'each variant calls the same toggle Ctrl+A calls, and what protects that sentence is ' +
         'that there is exactly ONE path into the Fullscreen API - but the WANT has to travel ' +
         'as "off", because a blind flip on "exit full screen" spoken at a windowed deck would ' +
         'ENTER fullscreen. That is the defect this row exists to make impossible: OFF is ' +
         'asserted as OFF at the wire, not inferred from a flip.'
  },
  {
    say: 'what is full screen mode?', setup: 'none',
    want: { status: 200, minLookups: 1 },
    notProtected: true, noFullscreen: true, wantsChips: true,
    why: 'THE CONTROL, AND IT IS THE WHOLE SAFETY OF PART 2. A question ABOUT full screen is ' +
         'an ordinary question and must be answered like one: through a door that costs a ' +
         'lookup, carrying its honest citations, with no fullscreen field in the payload and ' +
         'nothing done to the room. The failure mode is a funnel that grew until the deck ' +
         'could no longer be asked about itself without changing shape - and the thing that ' +
         'keeps it out is that both instruction patterns are ^...$ anchored on the ' +
         'addressless form, so a sentence with a question in front of the words never matches. ' +
         'On this corpus it lands on the NOTES door with 2 citations; the assertion is written ' +
         'as "a lookup and at least one chip" rather than "kind=notes", because which door an ' +
         'ordinary question opens is a property of the corpus and not of §29.'
  }
];

/* ================================ THE TYPED COLUMN ================================ */
async function typedPass() {
  say('\n  ---- TYPED: the twelve sentences at the wire ----------------------------');
  const rows = [];
  for (const row of MATRIX) {
    const label = '"' + row.say + '"' + (row.label ? ' · ' + row.label : '');
    step('typed ' + label);
    say('       ' + row.why);
    /* THE STATE THE SENTENCE ARRIVES INTO, set explicitly every time. A proposal left
       standing by an earlier row would make the row after it a different test than the one
       it says it is - which is exactly how an abandoned run poisons the hands gate. */
    await clearSlot();
    let offered = null;
    if (row.setup === 'pending') {
      const p = await proposeSelftest();
      offered = p.body && p.body.pending;
      if (!offered) { ok(false, 'the offer this row needs could not be put up', JSON.stringify(p)); continue; }
    }
    const mark = traceMark();
    const body = { question: row.say, session: 'routing-proof' };
    if (row.ear !== undefined) body.ear = { open: !!row.ear };
    const r = await post('/chat', body);
    const trace = traceSince(mark);
    const got = r.body || {};
    const w = row.want;
    const okStatus = r.status === w.status;
    const okKind = w.kind === undefined || got.kind === w.kind;
    const okRoute = w.route === undefined || got.route === w.route;
    const okLookups = w.lookups === undefined || got.lookups === w.lookups;
    const okMin = w.minLookups === undefined || Number(got.lookups) >= w.minLookups;
    const okOk = w.ok === undefined || got.ok === w.ok;
    const okAnswer = !row.answerHas ||
      String(got.answer || '').toLowerCase().indexOf(row.answerHas.toLowerCase()) >= 0;
    const okPending = !('want_pending' in row) ||
      (row.want_pending === null ? !got.pending
        : (typeof row.want_pending === 'string'
            ? !!got.pending && got.pending.tool === row.want_pending
            : !!got.pending));
    /* NOT PROTECTED is a claim in its own right and it is asserted as one: the payload of
       a protected class carries `protected` with the class in it, so a real question that
       started coming back protected would be caught here rather than in a month. */
    const okNotProt = !row.notProtected || !got.protected;
    /* THE CONNECTION'S OWN THREE CLAIMS.
       `alsoHas`  - every string that must be in the sentence, not just the first one.
                    answerHas is one substring, and one substring cannot express "it quotes
                    the panel's reading AND names the row".
       `wantsGoogleState` - the payload carries the state word, so a harness knows WHICH of
                    the six readings it got without parsing English back out of the prose.
                    A sentence is not evidence of a ladder; the word is.
       `notConnection` - the negative claim, and the only one that can catch the deictic rung
                    growing. Asserted as the absence of the state word rather than as the
                    absence of a route, because a proposal remark is ALSO answered at zero
                    cost from state, so route and lookups cannot tell the two apart. */
    const okAlso = !row.alsoHas || row.alsoHas.every(
      (s) => String(got.answer || '').indexOf(s) >= 0);
    const okGState = !row.wantsGoogleState || (typeof got.googleState === 'string' &&
      ['connected', 'absent', 'no-client', 'waiting', 'refused', 'reconnect', 'unknown']
        .indexOf(got.googleState) >= 0);
    const okNotConn = !row.notConnection ||
      (!got.googleState && String(got.answer || '').indexOf('GOOGLE: ') < 0);
    /* §29'S THREE CLAIMS, and each is written as a claim about the PAYLOAD because the payload
       is what the page acts on. The page's own side of this - fullAsked() - reads exactly
       these two fields and nothing else, so a row that asserted only the sentence would pass
       on an answer that says "Filling the screen" and leaves the deck the size it was.
         `wantsFullscreen`  the direction, asserted as 'on'/'off' and never as "truthy". A
                            want of "on" arriving as "off" is a working feature pointed the
                            wrong way, and it reads as a pass to anything that only checks
                            that the field is there.
         `noChips`          zero of all three chip carriers. Counted across nodes, sources and
                            citations rather than one of them, because three different doors
                            fill three different fields and checking one proves nothing about
                            the other two.
         `noFullscreen`     the control's negative: the field is ABSENT, not false. `false` is
                            what a refusal carries, and the control is not a refusal - it is a
                            question that never reached the route at all. */
    const chipCount = (a) => (Array.isArray(a) ? a.length : 0);
    const chips = chipCount(got.nodes) + chipCount(got.sources) + chipCount(got.citations);
    const okFull = !row.wantsFullscreen ||
      (got.fullscreen === true && got.fullscreenWant === row.wantsFullscreen);
    const okNoChips = !row.noChips || chips === 0;
    const okNoFull = !row.noFullscreen ||
      (got.fullscreen === undefined || got.fullscreen === null) &&
      (got.fullscreenWant === undefined || got.fullscreenWant === null);
    const okChips = !row.wantsChips || chips >= 1;
    ok(okStatus && okKind && okRoute && okLookups && okMin && okOk && okAnswer &&
       okPending && okNotProt && okAlso && okGState && okNotConn &&
       okFull && okNoChips && okNoFull && okChips,
       'TYPED ' + label + ' -> ' + r.status + ' kind=' + got.kind +
       ' route=' + (got.route || '-') + ' lookups=' + got.lookups +
       (got.fullscreenWant ? ' want=' + got.fullscreenWant : '') +
       ((row.noChips || row.wantsChips) ? ' chips=' + chips : '') +
       (got.googleState ? ' google=' + got.googleState : '') +
       (got.protected ? ' protected=' + got.protected : '') +
       (('want_pending' in row) ? ' pending=' + (got.pending ? got.pending.tool : 'none') : ''),
       JSON.stringify({ status: r.status, kind: got.kind, route: got.route,
                        lookups: got.lookups, protected: got.protected,
                        fullscreen: got.fullscreen, want: got.fullscreenWant, chips: chips,
                        ok: got.ok, pending: got.pending && got.pending.tool,
                        answer: String(got.answer || got.error || '').slice(0, 160) }));
    say('       he was told: "' + scrub(got.answer || got.error).slice(0, 150) + '"');
    if (trace) {
      const lines = trace.split(/\r?\n/).filter((l) => /route:|tool:|web lookup|notes/.test(l));
      if (lines.length) say('       the trace: ' + lines.map((l) => l.trim()).join(' ¦ ').slice(0, 300));
    }
    /* ZERO LOOKUPS IS A CLAIM ABOUT WORK NOT DONE, so it is proved by absence in the trace
       rather than by a counter. The confirmation payloads carry no `lookups` field at all
       (hands._reply builds them), so for those rows the only available evidence is that the
       server wrote no retrieval line while answering this sentence. The failure mode: a
       protected class that quietly embeds the utterance or opens the notes door, paying for
       an answer it already had. */
    if ((row.noRetrieval || w.lookups === 0) && TRACE_LIVE && trace !== null) {
      const spent = trace.split(/\r?\n/)
        .filter((l) => /recall: the notes door opened|web lookup|embedding/.test(l));
      ok(spent.length === 0,
         '       and NOTHING WAS LOOKED UP for it: no notes door, no web lookup in the ' +
         'trace this sentence wrote', JSON.stringify(spent));
    }
    /* PART A ASKS FOR THE TRACE BY NAME. Only the protected classes and the confirmation
       write a route line, so only they are held to it. */
    if (w.route && TRACE_LIVE) {
      ok(trace !== null && new RegExp('route: ' + w.route).test(trace),
         '       and THE TRACE NAMES THE CLASS: a line reading "route: ' + w.route + '"',
         JSON.stringify(String(trace).slice(-400)));
    }
    rows.push({ say: row.say, label: row.label || '', typed: got, status: r.status,
                trace: trace });
    await sleep(120);
  }
  await clearSlot();
  return rows;
}

/* ================= §29: THE DOORMAN ON THE FULLSCREEN INSTRUCTION =================
   "A guest's spoken command meets 'Only the boss fills the room, Addi.' with the state
   untouched." That is a claim about a SPOKEN turn from somebody who is not the boss, and the
   hard part of proving it is ordinarily a second person and a microphone.

   IT DOES NOT NEED EITHER, and the mechanism is one speaker_proof already measured: five
   seconds of generated noise posted to /speaker comes back sealed GUEST, because the matcher
   returns GUEST rather than its nearest row when nothing clears the 0.50 threshold. So this
   file can hold a real GUEST verdict, reached by this server from real audio, and quote its
   turn number at /chat exactly as the page would. Deterministic - a fixed-seed LCG - so a red
   row here is reproducible on a machine with no audio hardware at all.

   WHAT IT DELIBERATELY DOES NOT DO: it does not enrol, forget or replace anything. The boss's
   speaker store is not a harness's to edit, and a fixture that emptied it to make its own
   arithmetic neat would be the most expensive green in the file.

   AND WHAT IT CANNOT PROVE HERE, said plainly rather than left as a gap: the mandate admits
   BOSS *or a name*, and a NAMED colleague is ALLOWED through this gate. Proving that needs a
   second enrolled larynx, which needs an enrolment - so it is measured in-process and reported
   in the lookbook's gate table instead of asserted here. What this section proves is the
   refusal, which is the half that can do harm if it is wrong.

   THE SEAL IS ASSERTED BEFORE THE REFUSAL IS. A refusal on a turn that was never sealed GUEST
   is not evidence of a doorman - it is evidence of a server that refuses everything, which is
   also what a broken fullscreen_allowed() looks like. */
function writeWav(samples, rate) {
  const bytes = samples.length * 2, w = Buffer.alloc(44 + bytes);
  w.write('RIFF', 0); w.writeUInt32LE(36 + bytes, 4); w.write('WAVE', 8);
  w.write('fmt ', 12); w.writeUInt32LE(16, 16); w.writeUInt16LE(1, 20);
  w.writeUInt16LE(1, 22); w.writeUInt32LE(rate, 24); w.writeUInt32LE(rate * 2, 28);
  w.writeUInt16LE(2, 32); w.writeUInt16LE(16, 34);
  w.write('data', 36); w.writeUInt32LE(bytes, 40);
  for (let i = 0; i < samples.length; i++) w.writeInt16LE(samples[i], 44 + i * 2);
  return w;
}
function noisePcm(seconds, rate, amplitude) {
  const n = Math.round(seconds * rate), out = new Int16Array(n);
  let seed = 20260927;
  for (let i = 0; i < n; i++) {
    seed = (seed * 1103515245 + 12345) & 0x7fffffff;
    out[i] = Math.round(((seed / 0x7fffffff) * 2 - 1) * amplitude * 32767);
  }
  return out;
}
const noiseWav = (seconds, rate, amplitude) => writeWav(noisePcm(seconds, rate, amplitude), rate);
/* Parts numbered audio0, audio1, ... because _read_multipart keys its dict by part name and
   two parts both called "audio" would silently become one. */
async function postAudio(fields, clips) {
  const form = new FormData();
  for (const [k, v] of Object.entries(fields)) form.append(k, String(v));
  clips.forEach((buf, i) => form.append('audio' + i,
    new Blob([buf], { type: 'audio/wav' }), 'clip' + i + '.wav'));
  const res = await fetch(GALAXY + '/speaker', { method: 'POST', body: form });
  const text = await res.text();
  let json = null;
  try { json = JSON.parse(text); } catch (e) { json = { unparsed: text.slice(0, 300) }; }
  return { status: res.status, body: json };
}

const GUEST_SESSION = 'routing-proof-guest';
async function fullscreenDoorman() {
  say('\n  ---- §29 THE DOORMAN: a guest asks for the room ------------------------');
  const sp = await (await fetch(GALAXY + '/health')).json().catch(() => null);
  if (!sp || !sp.speaker || !sp.speaker.ready) {
    note('the speaker brain is not ready on this machine, so no seal can be earned and the ' +
         'refusal cannot be reached honestly. Reported, not skipped silently.');
    return ok(false, '§29 the guest refusal could not be exercised: /health says the speaker ' +
              'brain is not ready', JSON.stringify(sp && sp.speaker));
  }
  if (!sp.speaker.hasHands) {
    note('nobody with hands is enrolled on this machine, so fullscreen_allowed() opens for ' +
         'everyone BY DESIGN - a house that has never been taught a voice cannot prefer one.');
    return ok(true, '§29 the doorman stands down when no hands voice is enrolled, which is ' +
              'the Fallback Law applied to a gate: no roster, no refusals',
              JSON.stringify(sp.speaker));
  }

  step('a voice this house has never heard asks for the room');
  const id = await postAudio({ cmd: 'identify', session: GUEST_SESSION },
                             [noiseWav(5, 16000, 0.05)]);
  const seal = (id.body && id.body.seal) || '-';
  const turn = id.body && id.body.turn;
  ok(id.status === 200 && seal === 'GUEST' && !!turn,
     'five seconds of audio with no larynx in it is sealed ' + seal + ' and issued turn ' +
     turn + ' - a real verdict this server reached from real audio, not a word this harness ' +
     'chose for itself',
     JSON.stringify(id.body).slice(0, 260));
  if (seal !== 'GUEST' || !turn) {
    return note('without a GUEST seal there is nothing to refuse, so the rows below are not run');
  }

  const mark = traceMark();
  const r = await post('/chat', { question: 'go full screen', session: GUEST_SESSION,
                                  speaker: { via: 'voice', turn } });
  const trace = traceSince(mark);
  const g = r.body || {};
  say('       he was told: "' + scrub(g.answer || g.error) + '"');

  ok(r.status === 200 && g.refused === 'not-the-boss',
     'THE GUEST IS REFUSED AT THE DOORMAN: refused=' + (g.refused || 'nothing') +
     ' - and it is the doorman and not an error, because the deck has to keep working for ' +
     'the person in front of it',
     JSON.stringify(g).slice(0, 300));
  /* THE STATE, UNTOUCHED, AND IT IS THE PAYLOAD THAT SAYS SO. The page's fullAsked() is
     driven by exactly two fields; with no want in the payload there is no branch that can
     reach fullToggle(). `fullscreen:false` rather than absent is the refusal's own signature -
     the control row above asserts the ABSENT form, so the two cannot be confused. */
  ok(g.fullscreen === false && (g.fullscreenWant === undefined || g.fullscreenWant === null),
     'AND THE ROOM IS UNTOUCHED: the payload carries fullscreen=false and no ' +
     'fullscreenWant at all, so there is no field the page could act on even if it wanted to',
     JSON.stringify({ fullscreen: g.fullscreen, want: g.fullscreenWant }));
  /* THE MANDATE'S SENTENCE, AND IT ARRIVES DE-ADDRESSED WITHOUT A SPECIAL CASE. It is stored
     verbatim as the mandate wrote it - "Only the boss fills the room, Addi." - and the vocative
     peel, which is a DO-NOT-ALTER, takes the boss's address form off it for anybody who is not
     him. The failure mode this catches is the one worth catching: a stranger in the room being
     called by the boss's name while being told the room is not theirs. */
  const said = String(g.answer || '');
  ok(/only the boss fills the room/i.test(said),
     'and he is told the mandate’s own sentence: "' + scrub(said) + '"', said);
  ok(said.indexOf('Addi') < 0,
     'AND IT IS DE-ADDRESSED FOR A STRANGER: the boss’s address form is peeled off by the ' +
     'existing vocative peel, so a guest is refused without being called by his name', said);
  /* A REFUSAL MUST BE FREE. A doorman that paid for a model call to say no would be a doorman
     a stranger could run a bill up on, and the zero here is the same zero the five obeyed
     variants carry: the funnel answered above every retrieval either way. */
  ok(Number(g.lookups || 0) === 0 &&
     (!Array.isArray(g.citations) || g.citations.length === 0),
     'and THE REFUSAL COST NOTHING: lookups=' + (g.lookups || 0) + ' and no chips - a no is ' +
     'not a research question',
     JSON.stringify({ lookups: g.lookups, citations: (g.citations || []).length }));
  if (TRACE_LIVE && trace !== null) {
    const line = trace.split(/\r?\n/).find((l) => /route: fullscreen/.test(l));
    ok(!!line && /refused/.test(line),
       'and THE TRACE SAYS SO OUT LOUD, which is where the lookbook’s evidence comes ' +
       'from: "' + String(line || '').trim().slice(0, 170) + '"',
       JSON.stringify(String(trace).slice(-400)));
  }

  /* AND THE REFUSAL DOES NOT LATCH. A gate that refused once and then stayed shut would pass
     every assertion above and break the deck for its owner - so the boss's own keyboard is
     tried immediately afterwards, in the same session the guest just spoke into. */
  step('and the boss, typing, in the very session the guest just spoke into');
  const after = await post('/chat', { question: 'go full screen', session: GUEST_SESSION });
  const a = after.body || {};
  ok(after.status === 200 && a.fullscreen === true && a.fullscreenWant === 'on' && !a.refused,
     'THE REFUSAL DID NOT LATCH: the same instruction typed is obeyed at once (want=' +
     (a.fullscreenWant || '-') + ') - the guard is on the TURN, not on the session',
     JSON.stringify(a).slice(0, 260));
  return null;
}

/* ---- THE MANIFEST IS CURRENT, asserted against the live registry rather than against a
   sentence somebody remembered. The failure mode is the one PART D names: an assistant who
   names a hand he has not got, or does not name one he has. */
async function capabilitiesAgree() {
  step('the capabilities answer against the live registry');
  const r = await ask('galaxy what can you do');
  const answer = String((r.body || {}).answer || '').toLowerCase();
  const health = await (await fetch(GALAXY + '/health')).json();
  const organs = [
    { word: 'email', why: 'the email hand' },
    { word: 'calendar', why: 'the calendar hand' },
    { word: 'voice', why: 'the voice hand' }
  ];
  const missing = organs.filter((o) => answer.indexOf(o.word) < 0).map((o) => o.why);
  ok(missing.length === 0,
     'HE NAMES THE HANDS HE HAS: the capabilities answer mentions every hand in the ' +
     'registry that has a human name' + (missing.length ? ' - MISSING ' + missing.join(', ') : ''),
     JSON.stringify({ answer: answer.slice(0, 300), missing: missing }));
  ok(Number((r.body || {}).lookups) === 0,
     'and it costs nothing to say it: a machine that has to search to find out what it ' +
     'can do does not know what it can do',
     JSON.stringify(r.body && r.body.lookups));
  note('the manifest he speaks: "' + scrub((r.body || {}).answer).slice(0, 300) + '"');
  note('the notes behind it: ' + JSON.stringify(health.notes) + ' · vectors ' +
       JSON.stringify(health.vectors));
  return r.body;
}

/* ================================ CITATION HONESTY ================================
   A CHIP IS A CLAIM ABOUT THE SENTENCE ABOVE IT. "Drawn from" over three planets says: this
   answer came out of these notes. That is a claim only the ANSWER can support, and this
   server used to make it out of the RETRIEVAL - which runs before the answer exists. So a
   brain that could not be reached came back as an error with three planets lit under "Drawn
   from", and a refusal that correctly said the notes do not cover it came back cited on the
   notes it was refusing about, with the camera flying to one of them.

   WHY THIS IS MEASURED IN THE DOM AND NOT AT THE WIRE. `nodes: []` at the wire is the input
   to renderAnswer(); the chip row is the output, and between them sit byId.get(), safeUrl(),
   docCite() and a display toggle. The claim the mandate makes is about what the employer can
   SEE, so the count is taken off #a-chips.children and the label off #a-src - which is also
   the only way to notice the row going invisible for the wrong reason.

   AND THE CONTROL IS THE POINT OF THE SECTION. "Chip count 0" is satisfied completely by a
   chip renderer that has stopped working, and that is section 23's lesson twice over: an
   assertion can be green and still be blind. So the last fixture is a real question about the
   real notes, which MUST light at least one chip under "Drawn from" - and it runs through the
   same page, the same ask(), the same renderer as the five that must light none.          */
const CHIP_PORT = 9245;
const CHIP_FIXTURES = [
  { say: 'who are you', want: 0,
    why: 'AN IDENTITY LINE CITES NOTHING. It comes out of the persona block, which is not in ' +
         'the collection and has no planet.' },
  { say: 'galaxy what can you do', want: 0,
    why: 'NOR DOES A CAPABILITY LINE. It is read off the registry manifest; a chip under it ' +
         'would point at a note that has never heard of the email hand.' },
  { say: 'is my calendar connected', want: 0,
    why: 'NOR THE CONNECTION. Read from the live /google state - see the four rows above - ' +
         'and there is no note in the galaxy about this machine’s own token file.' },
  { say: 'ok got it', want: 0,
    why: 'AN ACKNOWLEDGEMENT IS A REPLY TO THE BUTLER, NOT A QUESTION PUT TO HIM. The ' +
         'backchannel door spends nothing and must show nothing: chips under "right you are, ' +
         'sir" would be provenance for a courtesy.' },
  { say: 'good morning galaxy', want: 0,
    why: 'AND A GREETING LEAST OF ALL. The vocative peel and the salutation veto already ' +
         'stop the lookup; this asserts the CARD agrees with them.' },
  { say: 'what am I building you for', want: 'some', label: 'THE CONTROL',
    why: 'AND NOW THE OTHER DIRECTION, which is the only thing that makes the five above ' +
         'mean anything. A real question about his real notes, answered from them, MUST ' +
         'light a chip row labelled "Drawn from". Without this row a broken chip renderer ' +
         'would pass this whole section 5/5. THE QUESTION CHANGED IN PART 8 and the control ' +
         'got stronger for it: it used to ask about coffee churn, which was a note in the ' +
         'demonstration corpus, and that corpus is now quarantined. This asks something only ' +
         'HIS two captures answer, so the row it lights is provenance for his own words.' }
];

async function chipHonesty() {
  say('\n  ---- CITATION HONESTY: what the card claims about where a sentence came from ----');
  const exe = CHROMES.find((p) => existsSync(p));
  if (!exe) { ok(false, 'the chip column cannot run: no Chrome on this machine'); return []; }
  const profile = mkdtempSync(join(tmpdir(), 'routing-chips-'));
  /* HEADLESS AND MUTED, and it may be: nothing in this section needs a room. The spoken
     column below is the headed one, and the two never overlap - this Chrome is killed before
     that one is spawned, which is the background-shell law kept rather than tested. */
  const chrome = spawn(exe, ['--remote-debugging-port=' + CHIP_PORT,
    '--user-data-dir=' + profile, '--no-first-run', '--no-default-browser-check',
    '--headless=new', '--mute-audio', '--disable-features=CalculateNativeWinOcclusion',
    '--disable-backgrounding-occluded-windows', '--disable-renderer-backgrounding',
    '--window-size=1400,940', '--new-window', 'about:blank'],
    { detached: true, stdio: 'ignore' });
  const rows = [];
  try {
    let target = null;
    for (let i = 0; i < 100 && !target; i++) {
      try {
        target = (await (await fetch('http://127.0.0.1:' + CHIP_PORT + '/json/list')).json())
          .find((t) => t.type === 'page');
      } catch (e) { /* not up yet */ }
      if (!target) await sleep(300);
    }
    if (!target) { ok(false, 'the chip column: Chrome never came up on port ' + CHIP_PORT); return rows; }
    const page = await new Page(target.webSocketDebuggerUrl).open();
    await page.send('Runtime.enable');
    await page.send('Page.enable');
    await page.send('Page.navigate', { url: GALAXY + '/?mute=1' });
    for (let i = 0; i < 200; i++) {
      if (await page.evaluate('!!(window.__galaxy && __galaxy.ask && __galaxy.nodes)')
            .catch(() => false)) break;
      await sleep(250);
    }
    /* READ THROUGH THE PAGE'S OWN ask(), not through renderAnswer. __galaxy.say would let
       this fixture hand the renderer whatever it liked, which would prove that the renderer
       obeys a harness and nothing about what the server sends. */
    const READ = `(function () {
      var box = document.getElementById('a-chips');
      var src = document.getElementById('a-src');
      var lbl = src && src.querySelector('.lbl');
      var txt = document.getElementById('a-text');
      var kids = box ? Array.prototype.slice.call(box.children) : [];
      return {
        chips: kids.length,
        tags: kids.map(function (k) { return k.tagName; }).join(','),
        rowShown: !!(src && src.style.display !== 'none' && src.offsetParent !== null),
        label: lbl ? lbl.textContent.trim() : '',
        answer: txt ? txt.textContent.slice(0, 160) : '',
        busyClass: document.getElementById('answer').className
      };
    })()`;
    for (const f of CHIP_FIXTURES) {
      const label = '"' + f.say + '"' + (f.label ? ' · ' + f.label : '');
      step('chips for ' + label);
      say('       ' + f.why);
      await page.evaluate('__galaxy.ask(' + JSON.stringify(f.say) + ')');
      /* WAIT FOR THE ANSWER AND NOT FOR A CLOCK. The interim line reads "Thinking across N
         notes…", so a fixed sleep would measure the placeholder on a slow turn - and the
         placeholder carries no chips, which would make every row pass for the wrong reason. */
      let read = null;
      for (let i = 0; i < 240; i++) {
        read = await page.json(READ);
        if (read && read.answer && !/^Thinking across|^Looking at|^Having a look|^Writing that/
              .test(read.answer)) break;
        await sleep(500);
      }
      const got = (read && read.chips) || 0;
      const good = f.want === 'some' ? got >= 1 : got === f.want;
      ok(good,
         'CHIPS ' + label + ' -> ' + got + ' chip' + (got === 1 ? '' : 's') +
         ', row ' + (read && read.rowShown ? 'shown' : 'hidden') +
         (read && read.label ? ' labelled "' + read.label + '"' : '') +
         (f.want === 'some' ? ' (at least one required)' : ' (none allowed)'),
         JSON.stringify(read));
      if (f.want === 'some') {
        ok(!!(read && read.rowShown && read.label === 'Drawn from'),
           '       and THE LABEL IS THE CLAIM: a notes answer says "Drawn from", which is a ' +
           'statement about his own collection',
           JSON.stringify(read && { rowShown: read.rowShown, label: read.label }));
      } else {
        ok(!!(read && !read.rowShown),
           '       and THE WHOLE ROW IS GONE, not merely empty: an empty "Drawn from" heading ' +
           'still claims a provenance, it just fails to name it',
           JSON.stringify(read && { rowShown: read.rowShown, label: read.label }));
      }
      say('       he was told: "' + scrub(read && read.answer).slice(0, 140) + '"');
      rows.push({ say: f.say, label: f.label || '', chips: got,
                  rowShown: !!(read && read.rowShown), lbl: (read && read.label) || '' });
      await sleep(200);
    }
  } finally {
    spawnSync('taskkill', ['/PID', String(chrome.pid), '/T', '/F']);
  }
  return rows;
}

/* ================================ THE SPOKEN COLUMN ================================
   The same sentences, out of the speakers, into the microphone array, through the page's
   own recogniser and the page's own funnel. Nothing is fed to heardFinal(): the words that
   reach the funnel are the words the room produced.                                     */
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
      }, 40000);
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
  async json(e) {
    return JSON.parse(await this.evaluate('JSON.stringify(' + e + ')') || 'null');
  }
}

/* THE WIRE TAP, AND IT READS THE REPLIES TOO. __wire in the spikes recorded requests, which
   answers "how many lookups did one sentence cost" and not "which door did it come out
   of". This one clones the response the PAGE acted on and keeps kind, route and lookups -
   the same three numbers the typed column asserts, off the same wire, in a real room. */
const WIRE_TAP = `(function () {
  window.__wire = [];
  var real = window.fetch;
  window.fetch = function (input, init) {
    var url = typeof input === 'string' ? input : (input && input.url) || '';
    var body = (init && typeof init.body === 'string') ? init.body : '';
    var watched = url.indexOf('/chat') >= 0 || url.indexOf('/tools') >= 0 ||
                  url.indexOf('/execute') >= 0;
    var out = real.apply(this, arguments);
    if (watched) {
      var row = { at: Date.now(), url: String(url).split('?')[0], q: body.slice(0, 160),
                  status: 0, kind: null, route: null, lookups: null, answer: '' };
      window.__wire.push(row);
      out.then(function (res) {
        row.status = res.status;
        res.clone().text().then(function (t) {
          try {
            var j = JSON.parse(t);
            row.kind = j.kind || null; row.route = j.route || null;
            row.lookups = (j.lookups === undefined ? null : j.lookups);
            row.protected = j.protected || null;
            row.answer = String(j.answer || j.error || '').slice(0, 200);
          } catch (e) { row.answer = '(unparsed)'; }
        });
      }, function () { row.status = -1; });
    }
    return out;
  };
})()`;

/* ---- WHAT "HEARD" MEANS, AND WHY IT IS READ OFF THE WIRE ----
   The first spoken run measured it off the recogniser's finals and printed `recognised: []`
   beside a /chat carrying "Who are you" - the words plainly arrived, the instrument could
   not see them. Two reasons, both structural rather than incidental:
     - THE PAGE CAN ASK ON AN INTERIM. flushThought appends lastInterim, so a sentence whose
       final has not landed when FINISH_MS expires is asked anyway - correctly - and the tap's
       finals list is still empty at that moment.
     - THE TRANSCRIPT VANISHES. The vanishing input is DO-NOT-ALTER and it is right: one
       phrase, kept at zero, cleared as soon as it is spent. A harness that needs it to linger
       is asking the page to be less careful than it is.
   So the question the page POSTED is the evidence, and it is better evidence: it proves the
   words reached the funnel, which is what this fixture is about. It also sorts two failures
   that the first run confused - the room mishearing a sentence, and the funnel misrouting one.
   A row is only judged once a posted question carries the words that were said; until then
   the sentence is said again. The first run's "hey galaxy are you there -> route:
   confirmation" was exactly that confusion: a stray "No" the room invented on its own got
   picked up as the answer to a sentence that had not been transcribed yet. */
function norm(s) {
  return String(s || '').toLowerCase().replace(/[^a-z0-9' ]+/g, ' ')
    .replace(/\bokay\b/g, 'ok').replace(/\s+/g, ' ').trim();
}

/* THE SAME WORDS WITH THE SPACES TAKEN OUT, and it is used for exactly one thing: deciding
   whether what reached the wire is the sentence he said.
   THE FAILURE MODE THIS CATCHES is a false red. The room transcribed "what is the web gate"
   as "What is the webgate" three times running - one token where he said two - so the
   containment test missed, the fixture refused to judge routing on words he had not said
   (which is right), said the sentence again twice, and failed a row whose own wire log shows
   200 kind=web lookups=2: the routing under test was correct in all three attempts. A space
   inside a compound noun is a transcription accident of the same family as the hyphen in
   "gpt-6 astra", which config.json's pinned phrases have folded since the brain was built.
   It does NOT weaken the guard: a recogniser that hears a DIFFERENT sentence still has
   different letters, and that is the thing this test exists to refuse.
   AND IT IS COMPARED BY EQUALITY, NOT BY CONTAINMENT, which is a correction of this paragraph
   rather than an addition to it. Containment was the first test and it had a hole the argument
   above does not cover: a recogniser that adds a word has all the same letters AND SOME MORE.
   Measured - "no no cancel that" came back as "No no cancel that Why", the trailing "Why" being
   the room's and nobody else's, and containment waved it through as his sentence. The funnel
   then did what it should with a longer sentence and sent it to the web for two lookups, and the
   fixture failed the confirmation class for answering a question the boss never asked. Equality
   keeps every accident this comment was written for - a swallowed space and "okay" for "ok" both
   fold to the same letters - and refuses the one it was not. */
function tight(s) {
  return norm(s).replace(/ /g, '');
}

/* The chat rows a page posted since a mark, newest last, with the question unpacked. */
async function chatRows(page, from) {
  const all = await page.json('__wire');
  return all.slice(from)
    .filter((e) => e.url.indexOf('/chat') >= 0)
    .map((e) => {
      let q = '';
      try { q = JSON.parse(e.q).question || ''; } catch (x) { q = e.q; }
      return Object.assign({}, e, { question: q });
    });
}

/* EVERY SENTENCE THE ROOM CAN ANSWER GETS SAID OUT LOUD - thirteen of the fifteen. Two are
   left out for reasons that are about the fixture and not about convenience:
     - "can you listen to me" WITH THE EAR SHUT cannot be spoken at all. Saying it into a
       shut ear is not a hard test of the live-state read, it is an impossible one: nothing
       would hear it. That row is the typed column's to prove, and it does.
     - "what is react" is dropped because on this corpus it answers from the notes at 0.614,
       exactly as the row beside it does, so speaking it buys a second copy of a claim the
       typed column already makes and costs half a minute of a talking laptop.
   Everything else is said: the peel, all four protected classes, a yes and a no in a real
   voice, a directive, a refusal with nothing pending, and the two real questions that must
   still reach the notes and the web. */
/* AND THREE OF THE FOUR CONNECTION ROWS ARE LEFT TYPED, which is a discretion decision and
   not an omission. "Is my calendar connected" is spoken, because it is the sentence he would
   actually say and the only one of the four whose transcription is at any risk - the room has
   to get both "calendar" and "connected" right through a speaker and a microphone. The other
   three are variations on the REGEX, not on the room: "how do i connect google" differs from
   it only in which alternative of CONNECTION_RE matches, and the two deictic rows are about
   what is on the card, which the typed column controls exactly and the room does not. Speaking
   them would buy four copies of one claim at half a minute of talking laptop each. */
const SPOKEN = MATRIX.filter((r) => !(r.say === 'can you listen to me' && r.ear === false))
  .filter((r) => r.say !== 'what is react')
  .filter((r) => r.say !== 'how do i connect google')
  .filter((r) => r.say !== 'why is it not connected')
  /* §29 IS HELD OUT OF THE SPOKEN COLUMN, and the reason is mechanical rather than shy. This
     column drives ONE headed Chrome whose window size every later measurement in it depends
     on, and these five sentences are an instruction to change that window: speaking "switch
     to full screen" into it would put the instrument itself in fullscreen halfway through its
     own run. The second reason is the budget - two unproven out of thirteen is a number three
     measured runs produced, and quietly stretching the denominator to nineteen would loosen a
     threshold without measuring it again.
     WHAT COVERS THE GAP, so this is a held-out row and not an untested path: the funnel is
     reached from a REAL SPOKEN TURN in fullscreenDoorman() - sealed from audio by this server,
     carrying via:'voice' - so the spoken road into the fullscreen route is exercised, and the
     three spellings the recogniser can produce are covered by the typed variants above. */
  .filter((r) => !r.wantsFullscreen && !r.noFullscreen);

async function spokenPass() {
  say('\n  ---- SPOKEN: the same sentences, out of the speakers -------------------');
  if (!pythonPresent()) {
    ok(false, 'the spoken column cannot run: python is not where mouth.mjs expects it');
    return [];
  }
  const exe = CHROMES.find((p) => existsSync(p));
  if (!exe) { ok(false, 'the spoken column cannot run: no Chrome on this machine'); return []; }
  const profile = mkdtempSync(join(tmpdir(), 'routing-'));
  const chrome = spawn(exe, ['--remote-debugging-port=' + CDP_PORT,
    '--user-data-dir=' + profile, '--no-first-run', '--no-default-browser-check',
    ...SPOKEN_FLAGS, '--window-size=1200,820', '--new-window', 'about:blank'],
    { detached: true, stdio: 'ignore' });
  let target = null;
  for (let i = 0; i < 100 && !target; i++) {
    try { target = (await (await fetch(CDP + '/json/list')).json()).find((t) => t.type === 'page'); }
    catch (e) { /* not up yet */ }
    if (!target) await sleep(300);
  }
  if (!target) { ok(false, 'Chrome never came up on the debugging port'); return []; }
  const page = await new Page(target.webSocketDebuggerUrl).open();
  await page.send('Runtime.enable');
  await page.send('Page.enable');
  /* BEFORE NAVIGATING, both of them, or the page's own script gets the real constructor
     and the real fetch first and neither tap sees anything. */
  await page.send('Page.addScriptToEvaluateOnNewDocument', { source: TAP });
  await page.send('Page.addScriptToEvaluateOnNewDocument', { source: WIRE_TAP });
  await page.send('Page.navigate', { url: GALAXY + '/?mute=1' });
  for (let i = 0; i < 160; i++) {
    if (await page.evaluate('!!(window.__galaxy && __galaxy.ear)').catch(() => false)) break;
    await sleep(250);
  }
  /* ON-DEVICE OR SAY SO. The cloud service throttles silently - see finding 7 in
     mouth.mjs - and a null transcript under that throttle looks exactly like a routing
     bug. Which engine heard the boss goes in the lookbook beside the transcript. */
  let local = null;
  for (let i = 0; i < 200; i++) {
    local = await page.json('__galaxy.ear.local');
    if (local && ['available', 'no-api', 'unavailable'].indexOf(local.state) >= 0) break;
    await sleep(1000);
  }
  note('the recognition engine: ' + JSON.stringify(local));
  ok(!!local && local.state === 'available',
     'THE WORDS STAY IN THE ROOM: on-device recognition is the engine for this column, so ' +
     'no transcript below can quietly be a throttled cloud transcript',
     JSON.stringify(local));

  const mouth = Mouth(page, (m) => say(m));
  await mouth.warm('warming the room');
  const click = await page.evaluate('__galaxy.ear.raise()');
  note('the one click: ' + JSON.stringify(click));

  const rows = [];
  for (const row of SPOKEN) {
    const label = '"' + row.say + '"' + (row.label ? ' · ' + row.label : '');
    step('spoken ' + label);
    const mark = mouth.saidMark();
    const want = norm(row.say);
    const wantTight = tight(row.say);
    /* THE ATTEMPT LOOP IS THE FIXTURE'S OWN, not mouth.say()'s, for one reason that only
       shows up in a real room: a misheard sentence CHANGES THE SERVER'S STATE. The first run
       had "yes yes do it galaxy" come back as "A half of that on top of" - a genuine new
       request, which released the proposal exactly as PART B says it must. Saying it again
       into an empty gate would then test nothing. So each attempt re-establishes the state
       the row is about, and the retry is honest instead of lucky.
       AND FIVE, NOT THREE, WHICH IS ARITHMETIC AND NOT PATIENCE. The budget was three and it
       was measured too small: on one full run of this column the on-device recogniser carried
       the boss's actual words on the first attempt for nine of thirteen sentences, needed a
       third for two more, and never managed two of them at all - "is my calendar connected"
       came back as "Is my phone", then "My calendar connected", then "Sorry pap". Call the
       per-attempt hit rate 0.6, which is about what that run shows. Three attempts then miss a
       given sentence 6.4% of the time and a thirteen-sentence column goes red better than half
       the time it is run, which makes the column's verdict a coin toss rather than a reading.
       Five attempts take that to 1% a sentence and about one run in eight - the honest ceiling
       for a real room, and still short of a guarantee, which is why this comment exists.
       WHAT THIS DOES NOT DO is widen what counts as heard. Every attempt is still judged
       against the boss's own words and a mishearing is still thrown away rather than routed;
       the budget buys more chances at the microphone and no latitude at all in the assertion. */
    const SPOKEN_TRIES = 5;
    let got = null, chats = [], fresh = [], attempts = 0, t0 = 0, before = null, transcript = [];
    for (let attempt = 1; attempt <= SPOKEN_TRIES && !got; attempt++) {
      attempts = attempt;
      await clearSlot();
      if (row.setup === 'pending') {
        const p = await proposeSelftest();
        if (!p.body || !p.body.pending) {
          ok(false, 'spoken ' + label + ': the offer could not be put up', JSON.stringify(p));
          break;
        }
      }
      const wire0 = (await page.json('__wire')).length;
      before = await page.json('({turns: __galaxy.ear.turns, arms: __galaxy.ear.arms,' +
        ' sealed: __galaxy.ear.sealed})');
      t0 = await page.json('Date.now()');
      /* HEARD MEANS THE WORDS HE SAID REACHED THE FUNNEL AND IT ANSWERED THEM. Both halves:
         a posted question that carries the sentence, and a status back. */
      const r = await mouth.speakAndHear(row.say, async () => {
        const w = await chatRows(page, wire0);
        const hit = w.filter((e) => e.status > 0 && tight(e.question) === wantTight);
        return hit.length ? hit : null;
      }, { timeoutMs: 26000, tries: 1 });
      transcript = r.transcript;
      chats = await chatRows(page, wire0);
      const hit = chats.filter((e) => e.status > 0 && tight(e.question) === wantTight);
      fresh = (await page.json('__galaxy.ear.thoughts')).filter((t) => t.at >= t0);
      if (hit.length) { got = hit[hit.length - 1]; break; }
      say('       attempt ' + attempt + ': the room made it "' +
        chats.map((e) => e.question).join(' ¦ ') + '" - the words he said are not in there, ' +
        'so the sentence is said again rather than judged on somebody else’s words');
      await sleep(1500);
    }
    const after = await page.json('({turns: __galaxy.ear.turns, arms: __galaxy.ear.arms,' +
      ' sealed: __galaxy.ear.sealed})');
    got = got || {};
    say('       posted     : "' + (got.question || '(nothing carrying his words)') + '"' +
        (attempts > 1 ? ' · on attempt ' + attempts : ''));
    say('       recognised : ' + JSON.stringify(transcript));
    say('       he answered: "' + String(got.answer || '').slice(0, 150) + '"');
    say('       the wire   : ' + JSON.stringify(chats.map((e) => e.status +
      ' kind=' + e.kind + ' route=' + e.route + ' lookups=' + e.lookups + ' q="' +
      e.question + '"')));
    const w = row.want;
    const heard = !!got.question;
    const okKind = w.kind === undefined || got.kind === w.kind;
    const okRoute = w.route === undefined || got.route === w.route;
    const okLookups = w.lookups === undefined || got.lookups === w.lookups;
    const okMin = w.minLookups === undefined || Number(got.lookups) >= w.minLookups;
    /* ONE UTTERANCE, ONE ASK - counted among the asks that carry HIS words. A stray phrase
       the room invents in the gap between two fixtures is the room's, not the funnel's, and
       failing the funnel for it would be a test blaming the wrong component; it is printed
       above either way. What must not happen is the same sentence asked twice. */
    const mine = chats.filter((e) => tight(e.question) === wantTight);
    const okOnce = mine.length === 1;
    if (!heard) {
      /* NOT HEARD IN FIVE TRIES - see THE THIRD OUTCOME at the top. No routing decision was
         made, so there is nothing here to pass or fail; it is counted and budgeted instead.
         The flush assertion below is skipped with it, because it would be measuring the same
         non-event from the other end and did indeed fail alongside this in two of the three
         runs that led to this change - one room fumble, two reds, both about nothing. */
      cannotSay('SPOKEN ' + label + ' -> the room never carried his words to the funnel in ' +
        attempts + ' tries, so the funnel made no decision to judge. What it heard instead: ' +
        JSON.stringify(transcript.length ? transcript : chats.map((e) => e.question)),
        JSON.stringify({ transcript, attempts, wire: chats.map((e) => e.question) }));
    } else {
    ok(okKind && okRoute && okLookups && okMin && okOnce,
       'SPOKEN ' + label + ' -> the funnel was asked "' + (got.question || '') + '" · ' +
       mine.length + ' ask' + (mine.length === 1 ? '' : 's') + ' · kind=' + got.kind +
       ' route=' + (got.route || '-') + ' lookups=' + got.lookups,
       JSON.stringify({ posted: got.question, transcript, attempts, wire: chats }));
    /* AND ONE UTTERANCE MADE ONE THOUGHT, off the ledger, by TIMESTAMP rather than by list
       length - the list is capped at twelve and the first run read "+0 thought" off a full
       one, which is a harness measuring its own cap. Two claims: every turn taken is
       accounted for by a named flush, and no two flushes carried the same sentence. The
       second is the double-flush signature precisely: Chrome hands back the final it was
       holding after flushThought has already sent the thought, and before the seal was
       added r.onend asked the same words a second time. */
    const dTurns = after.turns - before.turns;
    const texts = fresh.map((t) => t.text);
    const twice = texts.filter((t, i) => texts.indexOf(t) !== i);
    ok(dTurns === fresh.length && fresh.length >= 1 && twice.length === 0,
       '       and ONE UTTERANCE MADE ONE THOUGHT (+' + dTurns + ' turn, ' + fresh.length +
       ' flush' + (fresh.length === 1 ? '' : 'es') + ' - "' +
       fresh.map((t) => t.why).join('" then "') + '" · ' + (after.sealed - before.sealed) +
       ' late word' + (after.sealed - before.sealed === 1 ? '' : 's') + ' sealed off)',
       JSON.stringify({ fresh, twice, dTurns }));
    }
    rows.push({ say: row.say, label: row.label || '', posted: got.question || '',
                transcript, attempts, wire: got, flushes: fresh,
                spoke: mouth.saidSince(mark) });
    await sleep(1200);
  }
  mouth.unwatch();
  const shape = await page.json('({opened: __galaxy.ear.opened, arms: __galaxy.ear.arms,' +
    ' turns: __galaxy.ear.turns, gum: __galaxy.organs.state.mic})');
  ok(shape.opened === 1,
     'AND ALL OF IT ON ONE CLICK: ' + shape.turns + ' spoken turns, ' + shape.arms +
     ' arms of the recogniser, ' + shape.opened + ' session', JSON.stringify(shape));
  /* THE BUDGET, WHICH IS WHAT KEEPS "UNPROVEN" FROM BEING A PLACE TO HIDE. Three measured runs
     of this column each lost one sentence of thirteen, so two is the room's bad day and three is
     something else: a muted microphone, a recogniser that never starts, a page whose ear opens
     and hears nothing. That is exactly the failure this column exists to catch, and it fails
     here - once, with a count, instead of thirteen times over with thirteen explanations.
     The floor underneath it is the other half of the same claim: the column has to have PROVED
     something. A run that heard two sentences and shrugged at eleven must not read as green
     because eleven of them were politely filed as unproven. */
  const heardRows = rows.filter((r) => r.posted).length;
  ok(unproven <= 2 && heardRows >= rows.length - 2,
     'AND THE ROOM ACTUALLY DELIVERED: ' + heardRows + ' of ' + rows.length +
     ' spoken sentences reached the funnel in his own words, ' + unproven +
     ' went unproven - inside the budget of 2, which three runs of this column put at one lost ' +
     'sentence each',
     unproven + ' of ' + rows.length + ' sentences never reached the funnel. Past two this is ' +
     'not a room having a bad minute: check that the microphone is not muted, that on-device ' +
     'recognition is installed, and that this harness is the only thing holding the microphone');
  await clearSlot();
  spawnSync('taskkill', ['/PID', String(chrome.pid), '/T', '/F']);
  return rows;
}

/* ================================ THE RUN ================================ */
say('\n  ROUTING PROOF - the funnel in the boss\u2019s own sentences');
const health = await (await fetch(GALAXY + '/health').catch(() => null))?.json()
  .catch(() => null) || null;
if (!health || !health.ok) {
  say('\n  the server on 4700 is not answering; start it first: python server.py');
  process.exit(1);
}
note('the server: brain ' + health.brain + ' · model ' + health.model + ' · notes ' +
     JSON.stringify(health.notes));
note(TRACE_LIVE ? 'the trace is capturable at ' + TRACE + ', so the route lines are asserted'
                : 'NO TRACE AT ' + TRACE + ': the route lines cannot be read, so only the ' +
                  'payloads are asserted. Run the server as: python server.py 2> ' + TRACE);
ok(TRACE_LIVE, 'the server\u2019s trace is readable, which is where PART A asks for the ' +
   'class to be named');

const typed = TYPED_ONLY || !SPOKEN_ONLY ? await typedPass() : [];
if (!SPOKEN_ONLY) await capabilitiesAgree();
/* §29's doorman runs with the TYPED column and not with the spoken one, even though what it
   proves is about a voice: the guest's turn is sealed from a generated WAV posted over HTTP,
   so it needs no room, no microphone and no second person - and a claim that can be made at
   the wire should be made there, where it cannot be lost to a recogniser having a bad minute. */
if (!SPOKEN_ONLY) await fullscreenDoorman();
/* THE CHIP COLUMN GOES BEFORE THE SPOKEN ONE and both are sequential, because only one
   headed Chrome can hold its own clicks at a time and the chip pass kills its own headless
   one before returning. TYPED_ONLY keeps it: it is a wire-and-DOM claim, not a room claim. */
const chips = SPOKEN_ONLY ? [] : await chipHonesty();
const spoken = TYPED_ONLY ? [] : await spokenPass();

/* ---- the table the lookbook wants, printed here so it is copied rather than retyped ---- */
say('\n  ---- THE FIXTURE TABLE ------------------------------------------------');
say('  ' + 'sentence'.padEnd(36) + ' | ' + 'typed'.padEnd(30) + ' | spoken');
say('  ' + '-'.repeat(36) + '-+-' + '-'.repeat(30) + '-+-' + '-'.repeat(30));
/* Walked over the MATRIX rather than over the typed results, so the table is the whole
   fixture whichever column was run - a table that disappears under SPOKEN_ONLY is a table
   that cannot be pasted into the lookbook after a voice run. */
for (const m of MATRIX) {
  const row = typed.find((t) => t.say === m.say && (t.label || '') === (m.label || '')) ||
              { say: m.say, label: m.label, typed: null, status: '-' };
  const key = row.say + (row.label ? ' (' + row.label + ')' : '');
  const t = row.typed || {};
  const sp = spoken.find((s) => s.say === row.say && (s.label || '') === (row.label || ''));
  /* The spoken cell says what the funnel was ASKED, because that is what the spoken column
     measures - the words that got through the room - and then where they came out. */
  const spoke = sp
    ? ('asked "' + (sp.posted || '(never heard)') + '" -> ' +
       (sp.wire.kind || '?') + '/' + (sp.wire.route || '-') + '/' + sp.wire.lookups +
       (sp.attempts > 1 ? ' (said ' + sp.attempts + 'x)' : ''))
    : (TYPED_ONLY ? 'not run' : 'not spoken');
  const typedCell = row.typed
    ? (row.status + ' ' + (t.kind || '?') + '/' + (t.route || '-') + '/' + t.lookups)
    : 'not run';
  say('  ' + key.slice(0, 36).padEnd(36) + ' | ' + typedCell.slice(0, 30).padEnd(30) +
      ' | ' + spoke.slice(0, 60));
}

/* ---- and the chip table, in the same shape and for the same reason ---- */
if (chips.length) {
  say('\n  ---- THE CITATION-HONESTY FIXTURES -----------------------------------');
  say('  ' + 'sentence'.padEnd(42) + ' | chips | row      | label');
  say('  ' + '-'.repeat(42) + '-+-------+----------+-----------');
  for (const c of chips) {
    say('  ' + (c.say + (c.label ? ' (' + c.label + ')' : '')).slice(0, 42).padEnd(42) +
        ' | ' + String(c.chips).padEnd(5) + ' | ' +
        (c.rowShown ? 'shown' : 'hidden').padEnd(8) + ' | ' + (c.lbl || '-'));
  }
}

/* THE VERDICT NAMES THE UNPROVEN OUT LOUD, in the one line a reader copies into a report. An
   unproven sentence that only showed up two hundred lines further up would be a pass with a
   secret, which is the opposite of what the third outcome is for. */
say('\n  VERIFY ' + pass + '/' + (pass + fail) + (fail ? ' FAIL' : ' PASS') +
    (unproven ? ' · ' + unproven + ' UNPROVEN (the room, not the funnel: ' +
     unprovens.map((u) => (u.match(/"([^"]+)"/) || [, u])[1]).join(', ') + ')' : ''));
if (unproven && !fail) {
  say('\n  the unproven sentences are listed above with what the room made of them instead.');
  say('  They are inside the budget this file declares, and the assertion that says so is in');
  say('  the run; a re-run usually carries them and usually loses a different one.');
}
if (fail) {
  say('');
  for (const f of failures) say('    FAILED: ' + f);
}
process.exit(fail ? 1 : 0);
