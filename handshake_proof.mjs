/* THE HANDSHAKE WINDOW, MADE FALSIFIABLE - §35 PART 1.
 *
 * THE BUG THIS SECTION FIXES, in one sentence: a confirmation is one or two syllables, a
 * speaker embedding needs seconds of speech, so the Doorman sealed "haan" GUEST and the house
 * refused its own employer the instant he answered the question it had just asked him.
 *
 * THE FIX IS CONTEXT AND NOT CONFIDENCE, and that is precisely why it has to be proved rather
 * than demonstrated. A threshold low enough to admit a one-word "yes" admits anybody saying
 * yes; this does something narrower - it lets ONE word, inside ONE window, opened by ONE
 * sentence the Doorman actually verified, inherit the seal that sentence earned. Every clause
 * in that sentence is a security property, and a feature of this shape is only as good as the
 * list of things it REFUSES to do. So the five edges the mandate names are the spine of this
 * file, each with the failure it catches:
 *
 *   NO WINDOW OPENS FROM A GUEST UTTERANCE. Failure mode: the privilege becomes self-serving -
 *     a stranger says a sentence, it opens his own window, and his next "yes" is the boss's.
 *     That is not a weaker version of the feature, it is the opposite of it.
 *   A CONFIRMATION WITH NO OPEN WINDOW IS REFUSED EXACTLY AS TODAY. Failure mode: a window
 *     that is "usually open" - the state machine defaulting to permissive when it has nothing
 *     recorded, which is the single commonest way a gate like this is lost.
 *   A NON-GRAMMAR UTTERANCE INSIDE AN OPEN WINDOW TAKES THE NORMAL DOORMAN PATH. Failure
 *     mode: the window widens by a SENTENCE rather than by nine words, so for two minutes
 *     after every proposal a guest can give this house any order at all.
 *   AFTER TIMEOUT, "YES" IS GUEST AGAIN. Failure mode: a window left open over a slot that is
 *     already empty - a standing permission nobody granted and nobody can see.
 *   AND THE TYPED PATH IS UNCHANGED. Failure mode: a fix that reached the keyboard, where
 *     there was never a problem, and therefore cannot be shown to have reached the ear.
 *
 * Two more that the mandate implies and that are cheaper to break than any of the above:
 *
 *   THE INHERITING SET IS THE ACTIONABLE SET. The words that may inherit a seal are read from
 *     hands.py's own grammar, not from a list beside it. Failure mode is quiet and nasty: a
 *     word that inherits BOSS but that is_confirmation() does not recognise arrives at the
 *     gate as a NEW SUBJECT and silently WITHDRAWS the proposal it was meant to approve. So
 *     this file asserts the two sets are the same set, member by member.
 *   AND THE WINDOW CLOSES ON THE FIRST WORD. Failure mode: one sentence buying two consents.
 *
 * §36 ADDED TWO SECTIONS AND OVERTURNED ONE CLAIM, and both belong in this header because the
 * list above is the file's spine and §36 moved part of it:
 *
 *   THE PROMOTION (section 5). Not one window had ever opened on the real machine - /health
 *     read `opened: 0, refusedNoWindow: 18`. The store holds two rows for one man, `Addi` with
 *     the hands and `Aditya` without, and the persona block's boss_call is `Aditya`: his live
 *     voice matched the row the house greets him by, sealed his NAME, and handshake_open()'s
 *     literal "BOSS" guard refused the one person it exists for. The fix promotes at the
 *     funnel - inside _speaker_remember(), BEFORE the seal is finalised and published - and
 *     the assertion that matters is the ORDER, because a fix applied at the gate instead would
 *     admit the order and still paint the chip ADITYA.
 *   THE LIVE WIRE (section 6). A real Piper "Yes." posted to the ear's own route and carried
 *     into /execute {door:"voice"} on the running server, with §35's two negatives re-run over
 *     the same wire with the same real audio.
 *   AND §35's "THE TYPED PATH OPENS NOTHING" IS OVERTURNED, deliberately. Two halves of a
 *     handshake need not arrive by the same door: the boss types the order and answers aloud,
 *     and that spoken yes was the one being sealed GUEST. The four other negatives stand.
 *
 * HOW IT PROVES IT, AND WHERE THE MICROPHONE IS. The window is a predicate and a
 * small state machine, so it is exercised STANDALONE through the absolute Python path - the
 * §32 shape, where STUDY_NOW_RE was proved against the regex itself rather than against a
 * sentence a model happened to produce - with the clock INJECTED. That is not a convenience:
 * an assertion about a 120-second timeout that waited 121 seconds would be an assertion this
 * file could only afford to make once, and the one about `now` being monotonic could not be
 * made at all. The integration is proved the same way, by calling the REAL doorman_refusal()
 * against a REAL pending proposal with a fabricated speaker slot, so the thing under test is
 * the shipped gate and not a re-description of it.
 *
 * Sections 1 to 5 keep that shape. SECTION 6 DOES NOT: it is HTTP, a wav file and the running
 * server, with no python, no fabricated slot and no injected clock - because §36 asks for the
 * proof at the integration layer and not at the predicate, and because the two bugs it fixes
 * were both WIRING and would both have passed every predicate in this file.
 *
 * THE ONE THING IT DOES NOT PROVE is the boss's own larynx through a microphone, and the reason
 * is measured rather than assumed - see the last section, which reads it off the running server
 * instead of claiming it.
 *
 * Nothing is written except one fixture wav under _runs/. config.json is never touched. The only hand ever proposed is `selftest`,
 * which reads a token on stdin and prints it back, and every proposal this file raises it also
 * cancels - the same hermetic hand chain_proof uses, for the same reason.
 *
 * Usage:  python server.py 2> server-trace.log   then   node handshake_proof.mjs
 */
import { spawnSync } from 'node:child_process';
import { readFileSync } from 'node:fs';

const GALAXY = 'http://127.0.0.1:4700';
/* The absolute path, as every harness on this machine uses: bare `python` here is the
   Microsoft Store stub, which exits without running anything. */
const PYTHON =
  'C:/Users/Fullstack Developer/AppData/Local/Programs/Python/Python313/python.exe';

let pass = 0, fail = 0; const failures = [];
const say = (m) => console.log(m);
const ok = (c, claim, detail) => {
  if (c) pass++; else { fail++; failures.push(claim); }
  say((c ? '  ok   ' : '  FAIL ') + claim);
  if (!c && detail) say('         ' + detail);
};
const note = (m) => say('  note ' + m);
const step = (m) => say('\n  ·· ' + m);

/* ---- the predicate runner ----
   One python per section rather than one per claim: the import of server.py costs about a
   second and a half, and a file that paid that forty times would be a file nobody runs. */
function python(lines) {
  const r = spawnSync(PYTHON, ['-c', lines.join('\n')],
                      { encoding: 'utf8', timeout: 90000,
                        cwd: process.cwd(), env: { ...process.env, PYTHONIOENCODING: 'utf-8' } });
  if (r.error) throw new Error('python: ' + r.error.message);
  if (r.status !== 0) {
    throw new Error('python exited ' + r.status + ': ' + (r.stderr || '').slice(-900));
  }
  const out = (r.stdout || '').trim();
  const brace = out.lastIndexOf('\n{');
  const json = brace >= 0 ? out.slice(brace + 1) : out;
  try { return JSON.parse(json); } catch (e) {
    throw new Error('python said something that was not JSON: ' + out.slice(-600));
  }
}

async function get(path) {
  const r = await fetch(GALAXY + path, { signal: AbortSignal.timeout(20000) });
  let body = null;
  try { body = await r.json(); } catch (e) { body = null; }
  return { status: r.status, body: body || {} };
}
async function post(path, body) {
  const r = await fetch(GALAXY + path, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body || {}), signal: AbortSignal.timeout(30000),
  });
  let out = null;
  try { out = await r.json(); } catch (e) { out = null; }
  return { status: r.status, body: out || {} };
}

say('\n  HANDSHAKE PROOF - §35 + §36 PART 1, the window that lets a boss say yes');
say('  ' + '-'.repeat(74));

/* =====================================================================================
   1 · THE GRAMMAR, read from the house's own lists and never from a copy of them
   ===================================================================================== */
step('1 · the grammar: nine words, two languages, one list');

/* §35's own vocabulary, verbatim from the mandate. A fixture that typed its own list would
   pass against a feature that implemented a different one. */
const NAMED = ['yes', 'no', 'yeah', 'nope', 'haan', 'nahi', 'cancel', 'stop', 'confirm',
               'thik hai'];
/* Case and padding, which §35 asks for in the words "trimmed, case-insensitive". */
const SHAPES = ['  yes  ', 'YES', 'Haan Ji', 'NAHI', '\tthik hai\n', 'Yes.', 'nahin ji'];
/* THE SIEVE. The first six are preflight's own pool - sentences that must never be heard as
   consent - and the last three are this section's additions: `na` is an English filler AND a
   Hindi tag question, and a two-letter alternative in an anchored whole-message pattern is
   the cheapest way to turn a grammar into a sieve. */
const LEAKS = ['what address is it going to', 'make it tomorrow instead',
               'why would you do that', 'what is react',
               'yes, and what is the population of tokyo', 'no idea what react is',
               'na', 'naa', 'nahi kya matlab hai', 'make a video about pricing'];

const G = python([
  'import json, sys, server, hands',
  'named = ' + JSON.stringify(NAMED),
  'shapes = ' + JSON.stringify(SHAPES),
  'leaks = ' + JSON.stringify(LEAKS),
  'out = {}',
  'out["named"] = {w: bool(server.handshake_grammar(w)) for w in named}',
  'out["shapes"] = {w: bool(server.handshake_grammar(w)) for w in shapes}',
  'out["leaks"] = {w: bool(server.handshake_grammar(w)) for w in leaks}',
  // THE TWO SETS, compared member by member rather than asserted to be equal in prose.
  'out["polarity"] = {w: (server.confirmation_in(w) or "") for w in named}',
  'out["actionable"] = {w: bool(hands.is_confirmation(w) or hands.is_refusal(w)) for w in named}',
  // And the Hindi half of BOTH polarities, which is the asymmetry that was the actual gap.
  'out["hi"] = {w: (server.confirmation_in(w) or "") for w in ["haan","haan ji","han",'
    + '"theek hai","thik hai","kar do","bilkul","nahi","nahin","nahi ji","nahin ji"]}',
  'print(json.dumps(out))',
]);

const missed = NAMED.filter((w) => !G.named[w]);
ok(missed.length === 0,
   'EVERY WORD §35 NAMES IS HEARD: yes/no/yeah/nope/haan/nahi/cancel/stop/confirm/thik hai',
   'not heard: ' + JSON.stringify(missed));
const badShape = SHAPES.filter((w) => !G.shapes[w]);
ok(badShape.length === 0,
   'and case and padding cost nothing - "  YES  ", "Haan Ji", "NAHI", "Yes." all heard',
   'not heard: ' + JSON.stringify(badShape));
const leaked = LEAKS.filter((w) => G.leaks[w]);
ok(leaked.length === 0,
   'AND THE SIEVE HOLDS: a question, a correction, a tag-question "na" and a video order are '
   + 'NOT confirmations - widening, not narrowing, is the danger here',
   'leaked: ' + JSON.stringify(leaked));
const noPolarity = NAMED.filter((w) => G.polarity[w] !== 'yes' && G.polarity[w] !== 'no');
ok(noPolarity.length === 0,
   'THE INHERITING SET IS THE ACTIONABLE SET: every word that may inherit a seal is a word '
   + 'confirmation_in() gives a polarity for - so none can arrive as a change of subject',
   'no polarity for: ' + JSON.stringify(noPolarity));
const notActionable = NAMED.filter((w) => !G.actionable[w]);
ok(notActionable.length === 0,
   'and the gate itself agrees, word for word: is_confirmation or is_refusal for all ten',
   'the gate does not act on: ' + JSON.stringify(notActionable));
const hiYes = Object.entries(G.hi).filter(([, v]) => v === 'yes').map(([k]) => k);
const hiNo = Object.entries(G.hi).filter(([, v]) => v === 'no').map(([k]) => k);
ok(hiYes.length >= 5 && hiNo.length >= 3,
   'AND IT IS BILINGUAL IN BOTH DIRECTIONS - ' + hiYes.length + ' Hindi yeses and '
   + hiNo.length + ' Hindi noes. The asymmetry WAS the bug: `haan` was in the house and its '
   + 'opposite was not, and an unheard no leaves the proposal standing',
   JSON.stringify(G.hi));

/* =====================================================================================
   2 · THE WINDOW, standalone, with the clock injected
   ===================================================================================== */
step('2 · the window: five edges, one spent word, and a clamped number');

const W = python([
  'import json, server',
  'S = "handshake-proof"',
  'out = {}',
  // ---- EDGE 1: no window opens from anything but a BOSS.
  'out["openGuest"] = bool(server.handshake_open(S, "GUEST", gate="selftest", pid="p1"))',
  'out["openUnver"] = bool(server.handshake_open(S, "UNVERIFIED", gate="selftest", pid="p1"))',
  'out["openEmpty"] = bool(server.handshake_open(S, "", gate="selftest", pid="p1"))',
  'out["openName"]  = bool(server.handshake_open(S, "Addi", gate="selftest", pid="p1"))',
  'out["liveAfterGuests"] = server.handshake_live(S) is not None',
  // ---- EDGE 2: a confirmation with no window at all.
  'row, why = server.handshake_honour(S, "yes")',
  'out["noWindow"] = [row is None, why]',
  // ---- a BOSS opens one.
  'out["openBoss"] = bool(server.handshake_open(S, "BOSS", topic="Test the hands themselves",'
  + ' gate="selftest", pid="p1", now=1000.0))',
  'w = server.handshake_live(S, pending_id="p1", now=1002.5)',
  'out["live"] = {"gate": w["gate"], "ageS": w["ageS"], "ttlS": w["ttlS"],'
  + ' "topic": w["topic"]}',
  // ---- EDGE 3: a non-grammar utterance inside an open window.
  'row, why = server.handshake_honour(S, "what is react", pending_id="p1", now=1002.5)',
  'out["nonGrammar"] = [row is None, why]',
  'out["survives"] = server.handshake_live(S, pending_id="p1", now=1002.5) is not None',
  // ---- the honour, and the latency it records.
  'row, why = server.handshake_honour(S, "haan", pending_id="p1", now=1003.0)',
  'out["honoured"] = row',
  // ---- closes on the FIRST confirmation.
  'row, why = server.handshake_honour(S, "yes", pending_id="p1", now=1003.5)',
  'out["second"] = [row is None, why]',
  // ---- EDGE 4: the timeout, from both sides of it.
  'server.handshake_open(S, "BOSS", gate="mail", pid="p2", now=2000.0)',
  'out["justInside"] = server.handshake_honour(S, "yes", pending_id="p2", now=2119.0)[0]'
  + ' is not None',
  'server.handshake_open(S, "BOSS", gate="mail", pid="p3", now=3000.0)',
  'out["justOutside"] = server.handshake_honour(S, "yes", pending_id="p3", now=3121.0)',
  // ---- the gate closing: a different proposal, and an empty slot.
  'server.handshake_open(S, "BOSS", gate="mail", pid="p4", now=4000.0)',
  'out["otherGate"] = server.handshake_honour(S, "yes", pending_id="p9", now=4001.0)[1]',
  'server.handshake_open(S, "BOSS", gate="mail", pid="p5", now=5000.0)',
  'out["gateGone"] = server.handshake_honour(S, "yes", pending_id="", now=5001.0)[1]',
  // ---- a NO is honoured too, and spends the window just as finally.
  'server.handshake_open(S, "BOSS", gate="mail", pid="p6", now=6000.0)',
  'r6, _ = server.handshake_honour(S, "nahi", pending_id="p6", now=6002.0)',
  'out["noHonoured"] = r6',
  // ---- the clamp.
  'out["clamp"] = [server.confirm_window_s({"confirm_window_s": 86400}),'
  + ' server.confirm_window_s({"confirm_window_s": 0}),'
  + ' server.confirm_window_s({"confirm_window_s": "oops"}),'
  + ' server.confirm_window_s({})]',
  'out["default"] = server.DEFAULT_CONFIG["confirm_window_s"]',
  'import hands',
  'out["ttl"] = hands.CONFIRM_TTL_S',
  // ---- and what the page is allowed to see.
  'st = server.handshake_state()',
  'out["state"] = st',
  'out["stateHasTopic"] = ("Test the hands themselves" in json.dumps(st["live"]))',
  'out["ringMax"] = server.HANDSHAKE_LOG_MAX',
  'out["seal"] = server.HANDSHAKE_SEAL',
  'print(json.dumps(out))',
]);

ok(!W.openGuest && !W.openUnver && !W.openEmpty && !W.openName && !W.liveAfterGuests,
   'EDGE 1 - NO WINDOW OPENS FROM A GUEST UTTERANCE, and not from UNVERIFIED, not from an '
   + 'enrolled name without hands, not from an empty seal. Four attempts, nothing open',
   JSON.stringify({ guest: W.openGuest, unverified: W.openUnver, blank: W.openEmpty,
                    named: W.openName, live: W.liveAfterGuests }));
ok(W.noWindow[0] === true && W.noWindow[1] === 'no open window',
   'EDGE 2 - A CONFIRMATION WITH NO OPEN WINDOW INHERITS NOTHING: the state machine fails '
   + 'CLOSED on an absence rather than defaulting permissive',
   JSON.stringify(W.noWindow));
ok(W.openBoss === true && W.live && W.live.gate === 'selftest' && W.live.ageS === 2.5
   && W.live.ttlS === 120,
   'A BOSS OPENS ONE, and it knows its gate, its age and what it is worth: '
   + JSON.stringify(W.live && { gate: W.live.gate, ageS: W.live.ageS, ttlS: W.live.ttlS }),
   JSON.stringify(W));
ok(W.nonGrammar[0] === true && W.nonGrammar[1] === 'not a confirmation' && W.survives === true,
   'EDGE 3 - A NON-GRAMMAR UTTERANCE INSIDE AN OPEN WINDOW TAKES THE NORMAL DOORMAN PATH, '
   + 'and does not consume the window either: the window widens the vocabulary by nine words '
   + 'and never by a sentence',
   JSON.stringify({ nonGrammar: W.nonGrammar, survives: W.survives }));
ok(!!W.honoured && W.honoured.latencyMs === 3000 && W.honoured.word === 'yes'
   && W.honoured.gate === 'selftest' && W.honoured.topic === 'Test the hands themselves'
   && W.honoured.seal === 'BOSS · HANDSHAKE',
   'AND A WORD INSIDE IT INHERITS THE SEAL, with the ledger row §35 asks for - topic, gate, '
   + 'latency: ' + JSON.stringify(W.honoured),
   JSON.stringify(W.honoured));
ok(W.second[0] === true && W.second[1] === 'no open window',
   'IT CLOSES ON THE FIRST CONFIRMATION. One sentence buys exactly one consent - the same '
   + 'one-turn-one-order rule _speaker_spend() applies to a verdict',
   JSON.stringify(W.second));
ok(W.justInside === true && W.justOutside[0] === null
   && W.justOutside[1] === 'no open window',
   'EDGE 4 - AFTER TIMEOUT, "yes" IS GUEST AGAIN: honoured at 119s of 120, refused at 121s. '
   + 'A window left open over a slot that is already empty is a standing permission',
   JSON.stringify({ at119: W.justInside, at121: W.justOutside }));
ok(W.otherGate === 'no open window' && W.gateGone === 'no open window',
   'AND IT CLOSES WHEN THE GATE DOES - a different proposal in the slot, or no proposal at '
   + 'all, and the window is already shut. Judged on READ, so it cannot be a callback one of '
   + 'the propose sites forgets to fire',
   JSON.stringify({ other: W.otherGate, gone: W.gateGone }));
ok(!!W.noHonoured && W.noHonoured.word === 'no',
   'A SPOKEN NO INHERITS TOO, and this is the half it would have been easy to leave out: a '
   + 'guest\'s no cancels the boss\'s business, so the boss\'s "nahi" must reach the gate '
   + 'as finally as his yes does',
   JSON.stringify(W.noHonoured));
ok(W.clamp[0] === 600 && W.clamp[1] === 5 && W.clamp[2] === 120 && W.clamp[3] === 120,
   'THE NUMBER IS CLAMPED, NOT TRUSTED: 86400 -> 600, 0 -> 5, "oops" -> 120. A day-long '
   + 'window is a typo and so is a zero, and both are refused here rather than halfway down '
   + 'the gate',
   JSON.stringify(W.clamp));
ok(W.default === 120 && W.ttl === W.default,
   'AND THE DEFAULT IS THE SAME NUMBER AS hands.CONFIRM_TTL_S (' + W.ttl + 's): the window '
   + 'may not outlive the proposal it was opened for',
   JSON.stringify({ confirmWindowS: W.default, confirmTtlS: W.ttl }));
ok(W.stateHasTopic === false && Array.isArray(W.state.live),
   'AND WHAT THE GLASS MAY SEE CARRIES NO SUBJECT: handshake_state()\'s live list holds the '
   + 'gate and the age and strips the topic, because the Scribe\'s law does not stop at the '
   + 'edge of a new feature',
   JSON.stringify(W.state.live));
ok(W.ringMax === 40 && W.state.rows.length <= W.ringMax && W.state.rows.length >= 3,
   'the ledger is a RING of ' + W.ringMax + ' and not an archive - ' + W.state.rows.length
   + ' rows after this section, bounded in a process that runs for weeks',
   JSON.stringify({ max: W.ringMax, rows: W.state.rows.length }));
ok(W.seal === 'BOSS · HANDSHAKE',
   'and the chip\'s words live in ONE constant - "' + W.seal + '" - so the page, the ledger '
   + 'and this file cannot disagree about them',
   JSON.stringify(W.seal));

/* =====================================================================================
   3 · THE REAL DOORMAN, against a real pending proposal
   ===================================================================================== */
step('3 · the shipped gate: doorman_refusal() over a real proposal, no microphone');

/* WHY A FABRICATED SLOT AND NOT A FABRICATED FUNCTION. _SPEAKER_SLOTS is this process's own
   record of what it heard; filling one in-process is the only way to ask the REAL
   doorman_refusal() what it does with a guest's "yes" without a microphone and without
   stubbing the thing under test. The verdict written in is a GUEST verdict - hands False -
   which is exactly what the Doorman reaches for a one-word utterance, and it is the state the
   whole section exists to rescue. has_hands_voice() is forced True for the same reason: on a
   machine with nothing enrolled the Doorman stands down entirely and there is no law to prove.
   Both are named here rather than hidden, and neither touches speaker-store. */
const D = python([
  'import json, time, server, hands, voiceprint',
  'S = "handshake-doorman"',
  'out = {}',
  'out["enrolledForReal"] = bool(voiceprint.has_hands_voice())',
  'voiceprint.has_hands_voice = lambda: True',
  // A real proposal, from the one hermetic hand in the registry.
  'status, payload = hands.propose("selftest", server.tool_facts("selftest",'
  + ' {"token": "HANDSHAKE-ONE"}), door="button")',
  'pend = hands.pending_public()',
  'out["pending"] = {"id": bool(pend and pend.get("id")), "tool": (pend or {}).get("tool"),'
  + ' "name": (pend or {}).get("name")}',
  // The page's body: a turn number this process issued, carrying a GUEST verdict.
  'def slot(hands_ok):',
  '    with server._SPEAKER_LOCK:',
  '        server._SPEAKER_SLOTS[S] = {"turn": 7, "at": time.time(),',
  '                                    "verdict": {"who": "GUEST", "hands": bool(hands_ok),',
  '                                                "score": 0.33, "unverified": False}}',
  '    return {"speaker": {"via": "voice", "turn": 7}, "session": S}',
  // ---- (a) a GUEST "yes" with no window: refused, exactly as today.
  'body = slot(False)',
  'refusal, seal = server.doorman_refusal(body, S, "yes")',
  'out["noWindow"] = {"refused": (refusal or {}).get("refused"), "seal": seal,',
  '                   "answer": (refusal or {}).get("answer", "")}',
  // ---- (b) and it opened NO window of its own, which is edge 1 at the real door.
  'out["guestOpened"] = server.handshake_live(S) is not None',
  // ---- (c) now a BOSS sentence leaves the gate standing: handshake_offer opens one.
  'with server._SPEAKER_LOCK:',
  '    server._SPEAKER_SLOTS[S] = {"turn": 8, "at": time.time(),',
  '                                "verdict": {"who": "Addi", "hands": True, "score": 0.91}}',
  'out["offered"] = bool(server.handshake_offer(S, {"speaker": {"via": "voice", "turn": 8}},'
  + ' None))',
  'w = server.handshake_live(S, pending_id=(pend or {}).get("id"))',
  'out["opened"] = {"gate": (w or {}).get("gate"), "topic": (w or {}).get("topic")}',
  // ---- (d) and NOW the guest-sealed "haan" is admitted by the window.
  'body = slot(False)',
  'refusal, seal = server.doorman_refusal(body, S, server.confirmation_in("haan"))',
  'out["honoured"] = {"refusal": refusal, "seal": seal}',
  // ---- (e) the window is spent: the next word is refused again.
  'body = slot(False)',
  'refusal2, seal2 = server.doorman_refusal(body, S, "yes")',
  'out["spent"] = {"refused": (refusal2 or {}).get("refused"), "seal": seal2}',
  // ---- (f) the stamp reaches a payload, once, and only the two named fields.
  'with server._HANDSHAKE_LOCK:',
  '    server._HANDSHAKE_LAST[S] = {"gate": "selftest", "word": "yes", "latencyMs": 1200,'
  + ' "windowS": 120, "topic": "Test the hands themselves"}',
  'p = server.handshake_stamp(S, {"ok": True, "answer": "Done, sir."})',
  'out["stamp"] = p',
  'out["stampTwice"] = server.handshake_stamp(S, {"ok": True}).get("handshake")',
  // ---- (g) the typed path: no speaker block at all.
  'server.handshake_open(S, "BOSS", gate="selftest", pid=(pend or {}).get("id"))',
  'refusal3, seal3 = server.doorman_refusal({"session": S}, S, "yes")',
  'out["typed"] = {"refusal": refusal3, "seal": seal3}',
  // ---- (h) §36: and the typed door now ARMS one, for the crossing §35 left open.
  'server.handshake_close(S)',
  'out["typedOpened"] = bool(server.handshake_offer(S, {"session": S}, None))',
  'w3 = server.handshake_live(S, pending_id=(pend or {}).get("id"))',
  'out["typedWindow"] = {"seal": (w3 or {}).get("seal"), "gate": (w3 or {}).get("gate"),',
  '                      "pid": bool((w3 or {}).get("pid"))}',
  // and it is still a window and not a key: a DIFFERENT proposal id shuts it unread.
  'out["typedGateShuts"] = server.handshake_live(S, pending_id="some-other-proposal") is None',
  // and put the house back exactly as it was found.
  'hands.clear_pending("handshake_proof")',
  'server.handshake_close(S)',
  'out["cleaned"] = hands.pending_public() is None',
  'print(json.dumps(out))',
]);

note('a hands-privileged voiceprint is '
     + (D.enrolledForReal ? 'enrolled on this machine' : 'NOT enrolled on this machine')
     + ', so has_hands_voice() is forced True below to give the law something to guard');
ok(D.pending.id === true && D.pending.tool === 'selftest',
   'a real proposal stands at the gate - the hermetic hand, "' + D.pending.name + '"',
   JSON.stringify(D.pending));
ok(D.noWindow.refused === 'not-the-boss' && D.noWindow.seal === 'GUEST'
   && /I take orders from one voice in this house/.test(D.noWindow.answer),
   'EDGE 2 AT THE REAL DOOR: a guest-sealed "yes" with no window is refused by the VERBATIM '
   + 'line, with the same reason code, and the fix changed none of it',
   JSON.stringify(D.noWindow));
ok(D.guestOpened === false,
   'EDGE 1 AT THE REAL DOOR: that refused guest opened no window of his own - the privilege '
   + 'cannot bootstrap itself out of the utterance it refused',
   JSON.stringify({ live: D.guestOpened }));
ok(D.offered === true && D.opened.gate === 'selftest'
   && D.opened.topic === 'Test the hands themselves',
   'AND A BOSS-SEALED SENTENCE THAT LEAVES THE GATE STANDING OPENS ONE, named by the '
   + 'registry\'s own label for the hand and not by the employer\'s sentence',
   JSON.stringify(D.opened));
ok(D.honoured.refusal === null && D.honoured.seal === 'BOSS · HANDSHAKE',
   'THE FIX, AT THE DOOR THAT REFUSED HIM: the same guest-sealed utterance - a spoken "haan" '
   + '- is now ADMITTED, and the seal the gate hands back reads BOSS · HANDSHAKE',
   JSON.stringify(D.honoured));
ok(D.spent.refused === 'not-the-boss' && D.spent.seal === 'GUEST',
   'and the window was SPENT doing it: the very next "yes" is a stranger again, which is the '
   + 'difference between a handshake and a key left under the mat',
   JSON.stringify(D.spent));
ok(D.stamp && D.stamp.speakerSeal === 'BOSS · HANDSHAKE' && D.stamp.handshake
   && D.stamp.handshake.gate === 'selftest' && D.stamp.handshake.latencyMs === 1200
   && !('topic' in (D.stamp.handshake || {})) && D.stampTwice == null,
   'THE SEAL REACHES THE PAGE IN TWO NAMED FIELDS AND NO PROSE - speakerSeal and handshake '
   + '(gate, word, latency, and no topic) - and it is taken ONCE, so a seal cannot be '
   + 'collected twice off one word',
   JSON.stringify({ stamp: D.stamp, twice: D.stampTwice }));
ok(D.typed.refusal === null && D.typed.seal === '',
   'EDGE 5 - THE TYPED GATE IS UNCHANGED: a body with no speaker block is refused nothing and '
   + 'sealed nothing, with a window standing open beside it. The keyboard is already the boss',
   JSON.stringify({ typed: D.typed }));
/* §36 OVERTURNS ONE §35 CLAIM BY NAME, and it is named here rather than quietly deleted.
   §35 asserted the typed door opens NO window, on the reasoning that a typed yes never reaches
   doorman_refusal(). True, and beside the point: THE TWO HALVES OF A HANDSHAKE NEED NOT ARRIVE
   BY THE SAME DOOR. The boss types "put that on my calendar" and answers out loud, which is
   the natural thing to do with a card on screen and the ear already open - and that spoken yes
   DOES reach doorman_refusal(), is one syllable, and was sealed GUEST. §35's own negative was
   the hole. The four §35 negatives above are untouched. */
ok(D.typedOpened === true && D.typedWindow.seal === 'BOSS'
   && D.typedWindow.gate === 'selftest' && D.typedWindow.pid === true,
   '§36: AND THE TYPED DOOR NOW ARMS ONE, sealed BOSS by the keyboard law and bound to the '
   + 'proposal id it was opened for - so the boss can type the order and answer it aloud',
   JSON.stringify({ opened: D.typedOpened, window: D.typedWindow }));
ok(D.typedGateShuts === true,
   'and the widening is still a window and not a key: that typed window is shut unread the '
   + 'moment the pending proposal is not the one it was opened for',
   JSON.stringify({ shutsOnOtherGate: D.typedGateShuts }));
ok(D.cleaned === true,
   'and the house is put back as it was found: nothing pending, no window open',
   JSON.stringify({ cleaned: D.cleaned }));

/* =====================================================================================
   4 · THE LIVE SERVER: the endpoint, and the typed door over the wire
   ===================================================================================== */
step('4 · over the wire: /health publishes it and the typed door is untouched');

let live = true;
try {
  const v = await get('/health');
  if (v.status !== 200) live = false;
  const hs = v.body.handshake;
  ok(!!hs && typeof hs === 'object',
     '/health PUBLISHES THE WINDOW, on the same trip as the Scribe and the speaker: a '
     + 'harness must be able to read this state without a microphone',
     JSON.stringify(v.body.handshake));
  ok(hs && hs.windowS === 120 && Array.isArray(hs.live) && hs.seen
     && typeof hs.seen.opened === 'number',
     'and it says what confirm_window_s ACTUALLY is (' + ((hs && hs.windowS) || '?')
     + 's) rather than what the file says - the clamp is on the server side of the wire',
     JSON.stringify(hs));
  /* WHAT THE WIRE MAY AND MAY NOT CARRY, scoped the way handshake_state() actually promises
     it - and the way section 2 already asserts it in-process. THE LIVE LIST CARRIES NO TOPIC:
     a window standing open is read by the glass on every poll, so it holds the gate and the
     age and nothing else. THE RING IS THE LEDGER and does carry the gate's registry LABEL,
     which is a tool name from a fixed list ("Send an email") and never the employer's
     sentence - handshake_offer() is where that is enforced and says so.
     WHY THIS IS NOT THE OLD `indexOf('topic') < 0`: that string searched the ring too, so it
     only ever passed on a COLD ring and reddened the second time this harness ran against one
     live process - while section 7 of this same file REQUIRES a published row. One of the two
     had to be wrong about the design, and it was this one. The claim that matters survives and
     is now checked per row rather than by substring: no row carries a sentence, and the only
     word published is one of the three strings confirmation_in() can return. */
  const hrows = (hs && hs.rows) || [];
  const freeText = hrows.filter((r) => ['sentence', 'question', 'text', 'said', 'utterance']
                                       .some((k) => k in r));
  const badWord = hrows.filter((r) => ['yes', 'no', ''].indexOf(String(r.word)) < 0);
  ok(hs && JSON.stringify(hs.live).indexOf('topic') < 0 && freeText.length === 0
     && badWord.length === 0,
     'AND THE ENDPOINT CARRIES NO UTTERANCE: the live list holds no topic at all, and across '
     + hrows.length + ' ledger row(s) there is no sentence field and every published word is '
     + 'one of yes/no/"" - the grammar, not a recording. Failure mode this guards: a '
     + 'transparency chip that publishes the subject of the boss\'s business to any tab',
     JSON.stringify({ live: hs && hs.live, rows: hrows.length,
                      freeText: freeText.length, words: badWord.length,
                      last: hrows.slice(-1) }));

  const before = (hs && hs.seen && hs.seen.opened) || 0;
  /* THE TYPED DOOR, END TO END. Nothing is pending, so the honest answer is the house's
     "nothing to confirm" - a 409 and `nothing-pending`, which is what this door has always
     said and is therefore the right thing to assert. The claim is the three ABSENCES, not a
     200: no 403, no Doorman reason code, no seal, no window. A test that demanded 200 here
     would be a test that had to be relaxed the first time it met the real door. */
  const t = await post('/chat', { question: 'yes', session: 'handshake-proof-typed' });
  ok(t.status !== 403 && (t.body || {}).refused !== 'not-the-boss'
     && (t.body || {}).refused !== 'unverified-voice',
     'A TYPED "yes" IS NOT REFUSED BY THE DOORMAN over the wire either - it gets the house\'s '
     + 'own "nothing is pending" (HTTP ' + t.status + ', '
     + JSON.stringify((t.body || {}).refused) + '), which is what this door said before §35',
     JSON.stringify({ status: t.status, body: (t.body || {}).answer }));
  ok(!(t.body || {}).handshake && !(t.body || {}).speakerSeal,
     'and it carries NO handshake and NO seal: the fix did not reach the keyboard, where '
     + 'there was never anything wrong',
     JSON.stringify({ handshake: (t.body || {}).handshake,
                      seal: (t.body || {}).speakerSeal }));
  const after = await get('/health');
  const opened = ((after.body.handshake || {}).seen || {}).opened || 0;
  ok(opened === before,
     'AND NO WINDOW OPENED ANYWHERE DOING IT: the counter stands at ' + opened
     + '. A typed turn that quietly armed a window would be a privilege granted by a '
     + 'keystroke to whoever speaks next',
     JSON.stringify({ before: before, after: opened }));
} catch (e) {
  live = false;
  note('the live server did not answer: ' + (e.message || e));
}
if (!live) {
  ok(false, 'the server answered /health - start it with: python server.py 2> server-trace.log',
     'the four assertions above need a running server');
}

/* =====================================================================================
   5 · THE PROMOTION - §36 PART 1, the root cause of the boss's two screenshots
   =====================================================================================
   WHY THE WINDOW ABOVE WAS NEVER ONCE OPENED ON THE REAL MACHINE, and it is not in any of the
   logic §35 proved. /health read `opened: 0, refusedNoWindow: 18`. handshake_open() demands the
   seal "BOSS" exactly; seal_for() reads BOSS only when the matched row carries `hands`; and
   this store holds TWO rows for one man - `Addi` with the hands, enrolled first, and `Aditya`
   without, enrolled later - while the persona block's boss_call is `Aditya`. His live voice
   matched the row the house greets him by, sealed his NAME, and the guard refused to open a
   window for the one person it exists for. The gate then refused his own "yes" as a guest with
   104 seconds of a window that had never existed.

   SO THE INHERITANCE IS APPLIED AT THE FUNNEL, WHICH IS BEFORE THE SEAL IS FINALISED AND
   PUBLISHED - _speaker_remember(), the one function every verdict passes through, and it
   mutates the verdict rather than copying it so that the chip, the slot, the gate decision and
   the ledger row all read ONE promotion. That ORDER is the assertion below that matters: a fix
   that promoted at the gate instead would admit the order and still paint the chip ADITYA,
   which is exactly the pair of screenshots. */
step('5 · §36: the house promotes the voice it calls the boss, before it publishes the seal');

const P = python([
  'import json, time, server, hands, voiceprint',
  'S = "handshake-promote"',
  'out = {}',
  'boss = server.persona(server.load_config()[0])["boss_call"]',
  'out["call"] = server.boss_call_slug()',
  'out["roster"] = [{"slug": voiceprint.slug(r["name"]), "hands": r["hands"]}'
  + ' for r in voiceprint.enrolled()]',
  // ---- (a) the house's own name for him, matched above threshold, carrying no hands.
  'v = {"who": boss, "address_form": boss, "hands": False, "score": 0.88, "known": 2,'
  + ' "unverified": False}',
  'turn = server._speaker_remember(S, v)',
  // THE ORDER, ASSERTED: seal_for() is read off THE SAME OBJECT the route publishes from, on
  // the line after _speaker_remember(), which is the route's own order at server.py:9868-9869.
  'out["published"] = {"hands": v.get("hands"), "marker": v.get("bossByName"),'
  + ' "seal": voiceprint.seal_for(v)}',
  'verdict, spoken, why = server._speaker_turn({"speaker": {"via": "voice", "turn": turn}}, S)',
  'out["slot"] = {"hands": bool((verdict or {}).get("hands")), "spoken": bool(spoken)}',
  // ---- (b) and a window therefore OPENS for him, which is the chain the screenshot needed.
  'hands.propose("selftest", server.tool_facts("selftest", {"token": "PROMOTE"}), door="button")',
  'pend = hands.pending_public()',
  'turn2 = server._speaker_remember(S, {"who": boss, "address_form": boss, "hands": False,'
  + ' "score": 0.9})',
  'out["opensNow"] = bool(server.handshake_offer(S,'
  + ' {"speaker": {"via": "voice", "turn": turn2}}, None))',
  'out["window"] = {"seal": (server.handshake_live(S, pending_id=(pend or {}).get("id"))'
  + ' or {}).get("seal")}',
  // ---- (c) and nobody else is promoted. Four refusals, one line each.
  'def probe(who, hands_ok=False):',
  '    v = {"who": who, "hands": hands_ok, "score": 0.88}',
  '    server.boss_by_name(v)',
  '    return {"hands": bool(v.get("hands")), "marker": v.get("bossByName")}',
  'out["other"] = probe("Somebody Else")',
  'out["prefix"] = probe(boss + " Sharma")',
  'out["guest"] = probe("GUEST")',
  'out["nameless"] = probe(None)',
  'before = server._BOSS_BY_NAME["promoted"]',
  'out["already"] = probe("Addi", True)',
  'out["notRecounted"] = server._BOSS_BY_NAME["promoted"] == before',
  'hands.clear_pending("handshake_proof")',
  'server.handshake_close(S)',
  'out["cleaned"] = hands.pending_public() is None',
  'print(json.dumps(out))',
]);

note('the store holds ' + JSON.stringify(P.roster) + ' and the house calls its boss "'
     + P.call + '" - which is the fault in one line: a row by that name with no hands of its own');
ok(P.published.hands === true && P.published.marker === true
   && P.published.seal === 'BOSS',
   'THE ROOT CAUSE, FIXED AT THE FUNNEL: a verdict naming the boss_call with no hands on its '
   + 'row is promoted inside _speaker_remember(), and seal_for() reads BOSS off THE SAME OBJECT '
   + 'the route publishes - so the chip, the slot and the gate cannot disagree about one voice',
   JSON.stringify(P.published));
ok(P.slot.hands === true && P.slot.spoken === true,
   'and the slot the GATE later reads carries the same promotion, because it is the same dict - '
   + 'the inheritance is applied before the seal is finalised, not after it',
   JSON.stringify(P.slot));
ok(P.opensNow === true && P.window.seal === 'BOSS',
   'SO A WINDOW NOW OPENS FOR HIM - the link that was missing under both screenshots: 104 '
   + 'seconds of countdown over a window handshake_open() had refused to create',
   JSON.stringify({ opened: P.opensNow, window: P.window }));
ok(P.other.hands === false && P.other.marker == null
   && P.guest.hands === false && P.guest.marker == null
   && P.nameless.hands === false && P.nameless.marker == null,
   'AND NOBODY ELSE IS PROMOTED: another enrolled name, a GUEST and a nameless verdict all '
   + 'come back exactly as they went in. The privilege is still a measured voiceprint match',
   JSON.stringify({ other: P.other, guest: P.guest, nameless: P.nameless }));
ok(P.prefix.hands === false && P.prefix.marker == null,
   'and the comparison is the whole slug and not a prefix - "' + P.call
   + '-sharma" is a different person, which is the failure mode of matching names by startswith',
   JSON.stringify(P.prefix));
ok(P.already.hands === true && P.already.marker == null && P.notRecounted === true,
   'a row that ALREADY has the hands is untouched and not counted as a promotion, so the '
   + 'number on /health is the number of verdicts this fix actually mended',
   JSON.stringify({ already: P.already, notRecounted: P.notRecounted }));
ok(P.cleaned === true, 'and the house is put back as it was found again',
   JSON.stringify({ cleaned: P.cleaned }));

/* =====================================================================================
   6 · THE LIVE HANDSHAKE, END TO END, THROUGH THE EAR'S OWN DOOR - §36 PART 1
   =====================================================================================
   §36 asks for the proof at the INTEGRATION LAYER AND NOT AT THE PREDICATE: a gate opened from
   a typed BOSS command, then the confirmation fed through the same entry point the ear's STT
   uses - and it asks for a Piper-synthesised "yes.wav" driven into the real ear if this machine
   can do it. IT CAN, so that is what happens below: say.synthesise() writes a real one-word
   utterance, it is posted as multipart audio to POST /speaker cmd=identify - the identical
   route the live ear posts to - and the turn number that comes back is carried into
   POST /execute {door:"voice"}, which is the door the page posts when it hears "yes" itself.
   Nothing in this section calls a matcher, a predicate or a python: it is HTTP, a wav file and
   the running server, and it fails if any link in that chain is the one §35 left broken. */
step('6 · over the wire with real audio: typed gate, spoken yes, sealed BOSS · HANDSHAKE');

const LIVE_SESSION = 'handshake-live-36';
const GUEST_SESSION = 'handshake-live-36-guest';
const REFUSAL_LINE = 'I take orders from one voice in this house, and it is not speaking just now.';

async function postAudio(fields, wav) {
  const form = new FormData();
  for (const [k, v] of Object.entries(fields)) form.append(k, String(v));
  form.append('audio0', new Blob([wav], { type: 'audio/wav' }), 'yes.wav');
  const r = await fetch(GALAXY + '/speaker', { method: 'POST', body: form,
                                               signal: AbortSignal.timeout(60000) });
  let out = null;
  try { out = await r.json(); } catch (e) { out = null; }
  return { status: r.status, body: out || {} };
}
const hs = async () => ((await get('/health')).body.handshake) || {};
const proposeTyped = (session) => post('/tools', {
  cmd: 'propose', tool: 'selftest', params: { token: 'HANDSHAKE-36' },
  door: 'button', session,
});
const withdraw = (session) => post('/tools', { cmd: 'withdraw', session });

let wire = true;
try {
  /* THE FIXTURE IS PIPER'S, written through say.synthesise() so the bytes are the voice this
     house actually speaks with - 22.05 kHz, which voiceprint.read_wav() reads natively. */
  const W = python([
    'import json, os, time, say',
    'os.makedirs("_runs/sweep36", exist_ok=True)',
    'started = time.time()',
    'wav, why, source = say.synthesise("Yes.")',
    'out = {"bytes": len(wav or b""), "why": why, "source": source,',
    '       "tookMs": int((time.time() - started) * 1000)}',
    'if wav:',
    '    open("_runs/sweep36/yes.wav", "wb").write(wav)',
    'out["path"] = "_runs/sweep36/yes.wav" if wav else ""',
    'print(json.dumps(out))',
  ]);
  ok(W.bytes > 44 && !!W.path,
     'PIPER SPOKE THE FIXTURE: a real "Yes." of ' + W.bytes + ' bytes in ' + W.tookMs
     + ' ms (' + (W.source || 'none') + '), so the ear below is driven by synthesised speech '
     + 'and not by a fabricated slot',
     JSON.stringify(W));
  const wav = W.bytes > 44 ? readFileSync('_runs/sweep36/yes.wav') : null;

  await withdraw(LIVE_SESSION);
  const h0 = await hs();
  const seen0 = h0.seen || {};
  ok(typeof (h0.bossByName || {}).call === 'string' && (h0.bossByName || {}).call.length > 0,
     '/health PUBLISHES THE PROMOTION as counts and a slug - call "'
     + ((h0.bossByName || {}).call || '?') + '", wouldPromote '
     + JSON.stringify((h0.bossByName || {}).wouldPromote) + ' - because a privilege granted '
     + 'invisibly is the one kind this house does not grant',
     JSON.stringify(h0.bossByName));

  /* ---- (a) THE TYPED GATE. No speaker block: the keyboard, which is the boss. */
  const pro = await proposeTyped(LIVE_SESSION);
  const id = ((pro.body || {}).pending || {}).id || '';
  const h1 = await hs();
  ok(pro.status === 200 && !!id,
     'a typed BOSS command raises a real gate over the wire - the hermetic selftest hand, so a '
     + 'fixture about the word "yes" can never post a letter',
     pro.status + ' ' + JSON.stringify((pro.body || {}).pending || {}).slice(0, 140));
  ok(((h1.seen || {}).opened || 0) === ((seen0.opened || 0) + 1)
     && (h1.live || []).some((w) => w.gate === 'selftest'),
     '§36: AND IT ARMED THE WINDOW - opened ' + (seen0.opened || 0) + ' -> '
     + ((h1.seen || {}).opened || 0) + ', one live window on gate selftest. On this machine '
     + 'that counter had never once moved off zero',
     JSON.stringify({ seen: h1.seen, live: h1.live }));

  /* ---- (b) THE EAR. The same route the live ear posts to, with real audio. */
  const ear = wav ? await postAudio({ cmd: 'identify', session: LIVE_SESSION }, wav)
                  : { status: 0, body: {} };
  const turn = (ear.body || {}).turn;
  ok(ear.status === 200 && typeof turn === 'number',
     'THE EAR TOOK THE WAV at POST /speaker cmd=identify and issued turn ' + turn
     + ' - the same entry point and the same multipart part name the page uses',
     ear.status + ' ' + JSON.stringify(ear.body).slice(0, 160));
  ok(ear.status === 200 && (ear.body || {}).seal !== 'BOSS'
     && (ear.body || {}).hands !== true,
     'AND IT SEALED THAT ONE WORD ' + JSON.stringify((ear.body || {}).seal)
     + ' - "' + ((ear.body || {}).why || '') + '". THIS IS THE BOSS\'S SCREENSHOT: the word the '
     + 'gate exists to collect carries too little speech to be anybody, which is why the fix '
     + 'had to be context and not a threshold',
     JSON.stringify({ seal: (ear.body || {}).seal, score: (ear.body || {}).score,
                      why: (ear.body || {}).why }));

  /* ---- (c) THE GATE. door "voice", the turn the ear issued, the proposal the keyboard made. */
  const run = await post('/execute', { id, door: 'voice', session: LIVE_SESSION,
                                       speaker: { via: 'voice', turn } });
  const h2 = await hs();
  ok(run.status === 200 && (run.body || {}).ok === true,
     'THE GATE ACCEPTED IT: HTTP ' + run.status + ', the hand ran. A guest-sealed spoken yes, '
     + 'admitted on a window a typed order opened - which is the whole of §36 PART 1 in one '
     + 'request',
     run.status + ' ' + JSON.stringify(run.body).slice(0, 200));
  ok((run.body || {}).speakerSeal === 'BOSS · HANDSHAKE'
     && (run.body || {}).handshake && (run.body || {}).handshake.gate === 'selftest'
     && (run.body || {}).handshake.word === 'yes',
     'AND THE SEAL IS ON THE REPLY THE CHIP IS PAINTED FROM: speakerSeal "'
     + ((run.body || {}).speakerSeal || '') + '" with its evidence (gate '
     + (((run.body || {}).handshake || {}).gate || '?') + ', '
     + (((run.body || {}).handshake || {}).latencyMs || 0) + ' ms of '
     + (((run.body || {}).handshake || {}).windowS || 0) + ' s). The page copies this string; '
     + 'it is forbidden from deriving it',
     JSON.stringify({ seal: (run.body || {}).speakerSeal,
                      handshake: (run.body || {}).handshake }));
  ok((run.body || {}).pending == null,
     'and the card CLOSES - the reply carries no pending proposal, so the countdown the boss '
     + 'photographed has nothing left to count',
     JSON.stringify({ pending: (run.body || {}).pending }));
  ok(((h2.seen || {}).honoured || 0) === ((seen0.honoured || 0) + 1)
     && (h2.live || []).length === 0
     && (h2.rows || []).some((r) => r.gate === 'selftest' && r.seal === 'BOSS · HANDSHAKE'),
     'THE LEDGER ROW IS WRITTEN AND THE WINDOW IS SPENT: honoured ' + (seen0.honoured || 0)
     + ' -> ' + ((h2.seen || {}).honoured || 0) + ', no window left standing, and a row '
     + 'carrying the gate, the latency and the seal',
     JSON.stringify({ seen: h2.seen, live: h2.live, rows: (h2.rows || []).slice(-1) }));

  /* ---- (d) §35's NEGATIVE, RE-RUN OVER THE WIRE WITH THE SAME REAL AUDIO. A proposal raised
     by a GUEST's voice arms nothing, and his "yes" meets the verbatim pre-§35 line. This is the
     assertion that says §36 widened the door by one crossing and not by a hole. */
  const g0 = await hs();
  const earG = wav ? await postAudio({ cmd: 'identify', session: GUEST_SESSION }, wav)
                   : { status: 0, body: {} };
  const proG = await post('/tools', {
    cmd: 'propose', tool: 'selftest', params: { token: 'HANDSHAKE-36-GUEST' },
    door: 'voice', session: GUEST_SESSION,
    speaker: { via: 'voice', turn: (earG.body || {}).turn },
  });
  const idG = ((proG.body || {}).pending || {}).id || '';
  const g1 = await hs();
  ok(!!idG && ((g1.seen || {}).opened || 0) === ((g0.seen || {}).opened || 0),
     'EDGE 1 OVER THE WIRE, WITH REAL AUDIO: a proposal raised by a GUEST-sealed voice stands '
     + 'at the gate and ARMS NOTHING - opened stays at ' + ((g1.seen || {}).opened || 0)
     + '. The privilege cannot bootstrap itself out of the voice it does not trust',
     JSON.stringify({ id: !!idG, before: (g0.seen || {}).opened,
                      after: (g1.seen || {}).opened }));
  const earG2 = wav ? await postAudio({ cmd: 'identify', session: GUEST_SESSION }, wav)
                    : { status: 0, body: {} };
  const runG = await post('/execute', { id: idG, door: 'voice', session: GUEST_SESSION,
                                        speaker: { via: 'voice', turn: (earG2.body || {}).turn } });
  const g2 = await hs();
  ok(runG.status === 403 && (runG.body || {}).refused === 'not-the-boss'
     && String((runG.body || {}).answer || '').indexOf(REFUSAL_LINE) >= 0,
     'EDGE 2 OVER THE WIRE: and that guest\'s spoken "yes" with no window is refused by the '
     + 'VERBATIM pre-§35 line with the same reason code - HTTP ' + runG.status + ', '
     + JSON.stringify((runG.body || {}).refused),
     runG.status + ' ' + JSON.stringify((runG.body || {}).answer || '').slice(0, 170));
  ok(((g2.seen || {}).refusedNoWindow || 0) > ((g1.seen || {}).refusedNoWindow || 0)
     && !(runG.body || {}).speakerSeal && !(runG.body || {}).handshake,
     'and it is COUNTED as a refusal with no window and carries no seal and no handshake row - '
     + 'refusedNoWindow ' + ((g1.seen || {}).refusedNoWindow || 0) + ' -> '
     + ((g2.seen || {}).refusedNoWindow || 0),
     JSON.stringify({ seen: g2.seen, seal: (runG.body || {}).speakerSeal }));
  ok((runG.body || {}).pending && (runG.body || {}).pending.id === idG,
     'AND THE CARD STANDS UNTOUCHED through the refusal, so the boss can still answer it from '
     + 'the keyboard - the escape hatch the law is strict because of',
     JSON.stringify({ pending: ((runG.body || {}).pending || {}).id === idG }));
  const gone = await withdraw(GUEST_SESSION);
  const left = await hs();
  ok((gone.body || {}).pending == null && (left.live || []).length === 0,
     'and the house is handed back as it was found: the guest proposal is withdrawn and no '
     + 'window is left standing anywhere',
     JSON.stringify({ pending: (gone.body || {}).pending, live: left.live }));
} catch (e) {
  wire = false;
  note('the live wiring section did not finish: ' + (e.message || e));
}
if (!wire) {
  ok(false, '§36 PART 1 integration ran end to end over HTTP',
     'the section above needs a running server and a working Piper');
}

/* =====================================================================================
   7 · THE ENVIRONMENT LIMIT, measured rather than claimed
   ===================================================================================== */
step('7 · the one thing this file does not prove, and why');

/* §36 raised the bar from §35's: the confirmation now goes through the ear's own route as a
   real Piper-synthesised wav, so what is left unproven is narrower than it was, and it is
   named at its new size rather than at the old one. */
note('PROVED IN §36 AND NOT IN §35: a real synthesised "Yes." through POST /speaker '
     + 'cmd=identify into POST /execute {door:"voice"} on the live server - the ear\'s own '
     + 'route, the page\'s own door, no fabricated slot anywhere in section 6.');
note('STILL NOT PROVED HERE: the boss\'s own larynx through a microphone, which is the one '
     + 'link no fixture can stand in for - whether THIS machine\'s "Aditya" row matches his '
     + 'live voice above cosine 0.50 is speaker_proof\'s measurement, not this file\'s, and '
     + 'the promotion in section 5 is what makes that match worth having. The loopback is '
     + 'still the reason a synthesised one-word utterance cannot be placed in the near band on '
     + 'purpose: speaker_proof\'s ladder steps from cosine 0.5443 straight to 0.3338 across '
     + 'this machine\'s own threshold.');

say('\n  ' + '-'.repeat(74));
if (failures.length) {
  say('  what failed:');
  for (const f of failures) say('    FAILED: ' + f);
}
say('  VERIFY ' + pass + '/' + (pass + fail) + ' ' + (fail ? 'FAIL' : 'PASS'));
process.exit(fail ? 1 : 0);
