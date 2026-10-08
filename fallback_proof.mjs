/* FALLBACK PROOF - §41's routing law after the hardening, and the Piper pipeline's two fixes.
 *
 * WHAT THIS FILE IS FOR, in one line: when Groq tires, the local engine must be the SAME
 * butler with the SAME hands, and it must still be that at turn twelve.
 *
 * Every clause below asserts against something observed - a prompt actually built, a model
 * actually run, a wav actually synthesised - and never against a constant this file also
 * wrote. The one exception is the two schedule constants, which are read off the module and
 * compared to the numbers the mandate named, because a number is the only thing a number
 * assertion can be.
 *
 * SECTIONS 5-8 ARE §42, which put Gemini between Groq and this machine. They are in THIS
 * file and not a new one because the claim they make is this file's own claim one tier
 * over: the middle engine must be the SAME butler with the SAME hands, assembled by the
 * same function, and a house with no Gemini key must behave exactly as it did before the
 * tier existed. Section 1 proves that for Ollama by reading the prompt; section 7 proves
 * it for Gemini the same way and then proves the stronger thing - that the two prompts are
 * the SAME OBJECT, not two objects that happen to match.
 *
 * WHAT IS STUBBED AND WHY. Sections 5, 6 and 8 replace call_ollama and/or call_gemini with
 * tripwires, because what they test is the ROUTE - which engine was reached for, in which
 * order, and which rows the ledger grew - and a route is a decision, not an answer. The
 * engines themselves are run for real elsewhere: Ollama in section 3, Gemini in section 7,
 * each answering a real prompt. A stub that stood in for an engine whose answer was being
 * judged would be this file writing its own evidence.
 */
import { spawnSync } from 'node:child_process';
import { existsSync, mkdirSync } from 'node:fs';

const PYTHON =
  'C:/Users/Fullstack Developer/AppData/Local/Programs/Python/Python313/python.exe';
const OUT = '_runs/sweep46';
if (!existsSync(OUT)) mkdirSync(OUT, { recursive: true });

let pass = 0, fail = 0;
const failures = [];
const say = (s) => console.log(s);
function ok(cond, claim, evidence) {
  if (cond) { pass++; say('  ok   ' + claim); } else {
    fail++; failures.push(claim); say('  FAIL ' + claim);
    if (evidence) say('         ' + String(evidence).slice(0, 420));
  }
}
const note = (s) => say('  note ' + s);
const step = (s) => say('\n  \u00b7\u00b7 ' + s);

function python(lines, ms) {
  const r = spawnSync(PYTHON, ['-c', lines.join('\n')],
    { encoding: 'utf8', timeout: ms || 900000, cwd: process.cwd(),
      env: { ...process.env, PYTHONIOENCODING: 'utf-8' } });
  if (r.error) throw new Error('python: ' + r.error.message);
  if (r.status !== 0) throw new Error('python exited ' + r.status + ': ' + (r.stderr || '').slice(-900));
  const out = (r.stdout || '').trim();
  const brace = out.lastIndexOf('\n{');
  try { return JSON.parse(brace >= 0 ? out.slice(brace + 1) : out); } catch (e) {
    throw new Error('python said something that was not JSON: ' + out.slice(-500));
  }
}

say('\n  FALLBACK PROOF - the local engine is the same butler, with the same hands');
say('  ' + '-'.repeat(74));

/* =====================================================================================
   1 · THE SYSTEM PROMPT SURVIVES - persona and hands manifest, on the fallback path
   ===================================================================================== */
step('1 · what the local engine is actually handed');

const P = python([
  'import json, sys, io',
  'sys.dont_write_bytecode = True',
  'sys.path.insert(0, ".")',
  'buf, real = io.StringIO(), sys.stderr',
  'sys.stderr = buf',
  'import server',
  'sys.stderr = real',
  'cfg = server.load_config()[0]',
  'man = server.capabilities_manifest(cfg) or ""',
  'msgs = server.assemble(system=server.SYSTEM_PROMPT, manifest=man, history=[],',
  '                       ask="send an email to bob about the invoice")[0]',
  'worn = server.wear_persona(cfg, msgs)',
  'out = server._ollama_fallback_messages(worn)',
  'sysblob = " ".join(m["content"] for m in out if m["role"] == "system")',
  'names = [t["name"] for t in server.hands.registry()]',
  'out_json = {',
  '  "systemChars": len(sysblob),',
  '  "handsNamed": [n for n in names if n in sysblob],',
  '  "handsTotal": len(names),',
  '  "personaKept": ("Galaxy" in sysblob),',
  '  "manifestKept": ("WHAT YOU CAN ACTUALLY DO" in sysblob),',
  '  "fallbackConstChars": len(server.OLLAMA_FALLBACK_SYSTEM),',
  '  "model": server.OLLAMA_CHAT_MODEL,',
  '  "numCtx": server.OLLAMA_FALLBACK_NUM_CTX,',
  '  "budget": server.OLLAMA_PROMPT_BUDGET_CHARS,',
  '  "timeout": server.OLLAMA_CHAT_TIMEOUT_S,',
  '}',
  'print(json.dumps(out_json))',
]);

note('system block: ' + P.systemChars + ' chars, naming ' + P.handsNamed.length + '/'
     + P.handsTotal + ' hands');
ok(P.systemChars > 8000,
   'THE REAL SYSTEM PROMPT REACHES THE LOCAL ENGINE: ' + P.systemChars + ' characters, against '
   + 'the ' + P.fallbackConstChars + '-character constant it used to be handed instead - a '
   + 'factor of ' + Math.round(P.systemChars / P.fallbackConstChars) + '',
   JSON.stringify({ now: P.systemChars, was: P.fallbackConstChars }));
ok(P.personaKept === true && P.manifestKept === true,
   'and BOTH blocks are in it - the persona and the hands manifest, which are the two things '
   + 'whose absence produced "please use your preferred ride-hailing app" and a house with no '
   + 'reachable hands',
   JSON.stringify({ persona: P.personaKept, manifest: P.manifestKept }));
ok(P.handsNamed.length === P.handsTotal && P.handsTotal >= 11,
   'EVERY HAND IS NAMED IN IT - all ' + P.handsTotal + ': ' + P.handsNamed.slice(0, 4).join(', ')
   + ', … - so there is no hand the local engine cannot be asked to propose',
   JSON.stringify(P.handsNamed));

ok(P.model === 'qwen3:latest' && P.numCtx === 8192 && P.budget === 24000,
   'the routing constants are named and swappable: model ' + P.model + ', num_ctx ' + P.numCtx
   + ', prompt budget ' + P.budget + ' chars, timeout ' + P.timeout + 's',
   JSON.stringify(P));

/* =====================================================================================
   2 · TWELVE TURNS - the system prompt is never the thing that goes
   ===================================================================================== */
step('2 · a growing conversation trims history and never the system block');

const T = python([
  'import json, sys, io',
  'sys.dont_write_bytecode = True',
  'sys.path.insert(0, ".")',
  'buf, real = io.StringIO(), sys.stderr',
  'sys.stderr = buf',
  'import server',
  'sys.stderr = real',
  'cfg = server.load_config()[0]',
  'man = server.capabilities_manifest(cfg) or ""',
  'rows = []',
  'hist = []',
  'for turn in range(1, 21):',
  '    hist.append({"role": "user", "content": "Turn %d: a question about pricing. " % turn * 30})',
  '    hist.append({"role": "assistant", "content": "Turn %d: an answer. " % turn * 30})',
  '    msgs = server.assemble(system=server.SYSTEM_PROMPT, manifest=man, history=list(hist),',
  '                           ask="turn %d question" % turn)[0]',
  '    out = server._ollama_fallback_messages(server.wear_persona(cfg, msgs))',
  '    sysc = sum(len(m["content"]) for m in out if m["role"] == "system")',
  '    tot = sum(len(m["content"]) for m in out)',
  '    blob = " ".join(m["content"] for m in out if m["role"] == "system")',
  '    rows.append({"turn": turn, "sys": sysc, "total": tot,',
  '                 "turns": len([m for m in out if m["role"] != "system"]),',
  '                 "manifest": "WHAT YOU CAN ACTUALLY DO" in blob,',
  '                 "persona": "Galaxy" in blob})',
  'print(json.dumps({"rows": rows, "budget": server.OLLAMA_PROMPT_BUDGET_CHARS}))',
]);

const r1 = T.rows[0], r12 = T.rows[11], r20 = T.rows[19];
note('turn 1  : system ' + r1.sys + ', total ' + r1.total + ', ' + r1.turns + ' turns kept');
note('turn 12 : system ' + r12.sys + ', total ' + r12.total + ', ' + r12.turns + ' turns kept');
note('turn 20 : system ' + r20.sys + ', total ' + r20.total + ', ' + r20.turns + ' turns kept');

ok(T.rows.every((r) => r.sys === r1.sys),
   'THE SYSTEM BLOCK IS THE SAME SIZE AT EVERY ONE OF THE 20 TURNS: ' + r1.sys + ' characters '
   + 'throughout - it is never trimmed, never truncated, never partly sent',
   JSON.stringify(T.rows.map((r) => r.sys).slice(0, 6)));
ok(T.rows.every((r) => r.manifest === true && r.persona === true),
   'and the manifest and the persona are intact at every turn, including turn 12 - which is '
   + 'where the degradation was reported',
   JSON.stringify(T.rows.filter((r) => !r.manifest || !r.persona)));
ok(T.rows.every((r) => r.total <= T.budget),
   'EVERY TURN FITS THE BUDGET: the largest is ' + Math.max(...T.rows.map((r) => r.total))
   + ' of ' + T.budget + ' characters, so nothing is left for the runtime to truncate '
   + 'silently from the front - which is what was eating the system prompt',
   JSON.stringify(T.rows.map((r) => r.total)));
ok(r20.turns < r12.turns || r20.turns <= r1.turns + 24,
   'and it is HISTORY that gives way: ' + r1.turns + ' turns kept at turn 1, ' + r12.turns
   + ' at turn 12, ' + r20.turns + ' at turn 20 - the oldest pairs go first and the newest '
   + 'question always stays',
   JSON.stringify({ t1: r1.turns, t12: r12.turns, t20: r20.turns }));

/* =====================================================================================
   3 · THE LOCAL ENGINE, RUN - a hand proposed on the fallback path
   ===================================================================================== */
step('3 · Groq forced to 429, and the local engine answers in character');

const L = python([
  'import json, sys, io',
  'sys.dont_write_bytecode = True',
  'sys.path.insert(0, ".")',
  'buf, real = io.StringIO(), sys.stderr',
  'sys.stderr = buf',
  'import server',
  'sys.stderr = real',
  // §42 PUT A TIER IN FRONT OF THE ONE THIS SECTION IS ABOUT, and the key is taken away
  // here for that reason alone. THIS WAS MEASURED, NOT ANTICIPATED: the first run of this
  // file after §42 failed exactly here, with the row reading served=gemini, because a
  // tired Groq now reaches Gemini first and the real config.json has a Gemini key in it.
  // The fixture was still correct about the chain and no longer testing what it was
  // written to test - "the LOCAL engine is the same butler". So Gemini is removed from
  // the house for this section, which is also the honest statement of its scope. Section
  // 5 is the one that asserts what an empty key does to the route.
  'cfg = dict(server.load_config()[0])',
  'cfg["gemini_api_key"] = ""',
  'man = server.capabilities_manifest(cfg) or ""',
  // GROQ, FORCED TIRED. The transient flag is what the law reads - never a string match.
  'def tired(cfg_, messages, image=None, model=None, status=None):',
  '    if status is not None:',
  '        status.update({"code": 429, "transient": True})',
  '    return None, "Groq is rate limiting (429)."',
  'server.call_groq = tired',
  'msgs = server.assemble(system=server.SYSTEM_PROMPT, manifest=man, history=[],',
  '                       ask="what can you actually do for me?")[0]',
  'worn = server.wear_persona(cfg, msgs)',
  'answer, err = server.call_groq_then_local(cfg, worn, None, "chat")',
  'rows = [dict(r) for r in server._ENGINE_LOG][-1:]',
  'print(json.dumps({"answer": answer, "err": err, "row": rows[0] if rows else {}}))',
], 900000);

note('answer: ' + JSON.stringify(String(L.answer || L.err || '').slice(0, 220)));
ok(!L.err && !!L.answer,
   'A TIRED GROQ IS ANSWERED BY THE LOCAL ENGINE, with the real prompt behind it',
   JSON.stringify({ err: L.err }));
ok((L.row || {}).served === 'ollama' && (L.row || {}).outcome === 'fallback',
   'and the ledger row reads served=ollama outcome=fallback, model ' + (L.row || {}).model,
   JSON.stringify(L.row));
/* THE HANDS ARE VISIBLE TO IT. Asked what it can do, an engine holding the manifest names
   things off the manifest; one holding the 343-character constant cannot. */
const named = ['email', 'calendar', 'newsletter', 'film', 'voice', 'note']
  .filter((w) => String(L.answer || '').toLowerCase().includes(w));
ok(named.length >= 2,
   'AND IT CAN SEE ITS OWN HANDS: the answer names ' + named.length + ' of them ('
   + named.join(', ') + ') - which is only possible if the manifest reached the model',
   JSON.stringify(String(L.answer || '').slice(0, 300)));
ok(!/ride-hailing|preferred app|I do not have the capability/i.test(String(L.answer || '')),
   'and it does not answer out of character - no "please use your preferred ride-hailing app", '
   + 'which is what a model says when nobody told it who it is',
   JSON.stringify(String(L.answer || '').slice(0, 200)));

/* =====================================================================================
   4 · THE VOICE - the hole in the sentence, and the symbols
   ===================================================================================== */
step('4 · piper: an unspeakable chunk is a sentence, and symbols are words');

const V = python([
  'import json, sys',
  'sys.dont_write_bytecode = True',
  'sys.path.insert(0, ".")',
  'import say',
  'out = {}',
  // THE DEFECT: a punctuation-only chunk used to crash piper and be SKIPPED, leaving a hole.
  'for label, text in (("dots", "..."), ("bangs", "!!!"), ("dashes", "-- ,")):',
  '    wav, why, src = say.synthesise(text)',
  '    out[label] = {"wav": bool(wav), "why": why}',
  'wav, why, src = say.synthesise("Right, sir.")',
  'out["real"] = {"bytes": len(wav or b""), "why": why}',
  'print(json.dumps(out))',
], 900000);

ok(V.dots.wav === false && /nothing speakable/.test(V.dots.why),
   'AN UNSPEAKABLE CHUNK IS REFUSED WITH A SENTENCE: "' + V.dots.why + '" - where it used to '
   + 'be `piper exited 1: wave.Error: # channels not specified`, an error about channels that '
   + 'says nothing about the cause and that the page skipped, leaving a hole mid-sentence',
   JSON.stringify(V.dots));
ok(V.bangs.wav === false && V.dashes.wav === false,
   'and so are "!!!" and "-- ," - every chunk that normalises down to punctuation',
   JSON.stringify({ bangs: V.bangs, dashes: V.dashes }));
ok(V.real.bytes > 1000,
   'while a real line still synthesises: ' + V.real.bytes + ' bytes of wav',
   JSON.stringify(V.real));

/* =====================================================================================
   5 · ZERO DRIFT - no Gemini key, and the chain is the one that was here before
   =====================================================================================
   THE MOST IMPORTANT CHECK IN §42, and the one a new tier is most likely to fail. The
   feature is gated on gemini_key() and nothing else, so an empty field must not merely
   "work" - it must leave the route it found. Both engines are tripwires here: the claim
   is about who was REACHED FOR, which is exactly what a counter can answer and an answer
   cannot. */
step('5 · gemini_api_key empty: Groq tires, and Ollama is still the next road');

const Z = python([
  'import json, sys, io',
  'sys.dont_write_bytecode = True',
  'sys.path.insert(0, ".")',
  'buf, real = io.StringIO(), sys.stderr',
  'sys.stderr = buf',
  'import server',
  'sys.stderr = real',
  'cfg = dict(server.load_config()[0])',
  // THE KEY TAKEN AWAY, which is the whole fixture. Everything else is left alone.
  'cfg["gemini_api_key"] = ""',
  'man = server.capabilities_manifest(cfg) or ""',
  'def tired(cfg_, messages, image=None, model=None, status=None):',
  '    if status is not None:',
  '        status.update({"code": 429, "transient": True})',
  '    return None, "Groq is rate limiting (429)."',
  // TRIPWIRES. Neither pretends to be an engine; each records that it was reached for.
  'seen = {"gemini": 0, "ollama": 0}',
  'def gem_trip(cfg_, messages, image=None, model=None, status=None):',
  '    seen["gemini"] += 1',
  '    return None, "the tripwire"',
  'def oll_trip(cfg_, messages, image=None, status=None):',
  '    seen["ollama"] += 1',
  '    if status is not None:',
  '        status.update({"reached": True, "slow": False, "model": "tripwire"})',
  '    return "A local answer.", None',
  'server.call_groq, server.call_gemini, server.call_ollama = tired, gem_trip, oll_trip',
  'del server._ENGINE_LOG[:]',
  'msgs = server.assemble(system=server.SYSTEM_PROMPT, manifest=man, history=[],',
  '                       ask="what can you actually do for me?")[0]',
  'worn = server.wear_persona(cfg, msgs)',
  'answer, err = server.call_groq_then_local(cfg, worn, None, "chat")',
  'rows = [dict(r) for r in server._ENGINE_LOG]',
  'print(json.dumps({"answer": answer, "err": err, "seen": seen, "rows": rows,',
  '                  "ready": server.gemini_ready(cfg)[0],',
  '                  "digest": server.gemini_digest(cfg)}))',
]);

note('engines reached: ' + JSON.stringify(Z.seen) + ', ledger rows: ' + Z.rows.length);
ok(Z.seen.gemini === 0,
   'GEMINI IS NEVER REACHED FOR WITH AN EMPTY KEY: the tripwire fired 0 times, so the '
   + 'absent key costs not one request, not one socket and not one millisecond',
   JSON.stringify(Z.seen));
ok(Z.seen.ollama === 1 && !Z.err && !!Z.answer,
   'and THIS MACHINE IS STILL THE NEXT ROAD: Ollama reached exactly once and the turn was '
   + 'answered - the route is Groq then Ollama, as it was before §42',
   JSON.stringify({ seen: Z.seen, err: Z.err }));
/* ONE ROW, AND THE FIRST DRAFT OF THIS CLAUSE ASSERTED TWO - which is worth leaving a note
   about, because the shape is not the obvious one. A TRANSIENTLY tired Groq writes NO row
   of its own: call_groq_then_local returns early with a row only when Groq succeeds or
   fails permanently, and on the transient path the reason is carried INTO the serving
   engine's row instead - which is why the assertion below reads the 429 off the ollama
   row. Two rows would have meant §42 had added one. */
ok(Z.rows.length === 1
   && Z.rows[0].provider === 'ollama' && Z.rows[0].served === 'ollama'
   && Z.rows[0].outcome === 'fallback' && /429/.test(String(Z.rows[0].reason || '')),
   'THE LEDGER IS THE SHAPE IT WAS: exactly ONE row, ollama/fallback, carrying Groq\'s 429 '
   + 'as its reason - no row was added, removed or re-worded by the tier that was skipped',
   JSON.stringify(Z.rows));
ok(Z.rows[0].spoken === 'Thinking locally, sir.',
   'down to the line the boss actually hears on a fallback - "' + Z.rows[0].spoken + '" - '
   + 'which is the fixed sentence for THIS MACHINE and must not be reached for a turn that '
   + 'never came near it',
   JSON.stringify(Z.rows[0]));
ok(!Z.rows.some((r) => r.provider === 'gemini' || r.served === 'gemini'),
   'and no row anywhere names gemini, so nothing downstream that reads the ledger can tell '
   + 'this tier was ever added',
   JSON.stringify(Z.rows.map((r) => r.provider)));
ok(Z.ready === false && Z.digest.present === false && Z.digest.sha256 === '',
   'while /health says so plainly: present=false and an empty digest - "not configured" and '
   + '"not helping" are different sentences',
   JSON.stringify(Z.digest));

/* =====================================================================================
   6 · THE KEY PUT BACK - Groq tires transiently, and Gemini is tried BEFORE Ollama
   ===================================================================================== */
step('6 · gemini_api_key present: the middle tier is reached, and it is reached first');

const M = python([
  'import json, sys, io',
  'sys.dont_write_bytecode = True',
  'sys.path.insert(0, ".")',
  'buf, real = io.StringIO(), sys.stderr',
  'sys.stderr = buf',
  'import server',
  'sys.stderr = real',
  'cfg = dict(server.load_config()[0])',
  'man = server.capabilities_manifest(cfg) or ""',
  'order = []',
  'def tired(cfg_, messages, image=None, model=None, status=None):',
  '    order.append("groq")',
  '    if status is not None:',
  '        status.update({"code": 429, "transient": True})',
  '    return None, "Groq is rate limiting (429)."',
  // GEMINI MADE TO 429 - the mandate's simulate-a-429 case - so section 6 proves the
  // order and the fall-through in one fixture rather than spending two live calls.
  'def gem_429(cfg_, messages, image=None, model=None, status=None):',
  '    order.append("gemini")',
  '    if status is not None:',
  '        status.update({"code": 429, "transient": True, "model": "gemini-3.5-flash-lite"})',
  '    return None, "Gemini is rate limiting - the free tier\'s daily cap (429)."',
  'def oll(cfg_, messages, image=None, status=None):',
  '    order.append("ollama")',
  '    if status is not None:',
  '        status.update({"reached": True, "slow": False, "model": "tripwire"})',
  '    return "A local answer.", None',
  'server.call_groq, server.call_gemini, server.call_ollama = tired, gem_429, oll',
  'del server._ENGINE_LOG[:]',
  'msgs = server.assemble(system=server.SYSTEM_PROMPT, manifest=man, history=[],',
  '                       ask="what can you actually do for me?")[0]',
  'worn = server.wear_persona(cfg, msgs)',
  'answer, err = server.call_groq_then_local(cfg, worn, None, "chat")',
  'rows = [dict(r) for r in server._ENGINE_LOG]',
  'print(json.dumps({"answer": answer, "err": err, "order": order, "rows": rows,',
  '                  "budget": server.FALLBACK_TRIGGER_BUDGET_MS,',
  '                  "keyPresent": server.gemini_digest(cfg)["present"]}))',
]);

note('roads taken, in order: ' + M.order.join(' -> '));
ok(M.keyPresent === true,
   'the real config.json carries a Gemini key (' + JSON.stringify(M.order) + ') - so this '
   + 'section is testing the configured house and not a fixture',
   JSON.stringify(M.keyPresent));
ok(JSON.stringify(M.order) === JSON.stringify(['groq', 'gemini', 'ollama']),
   'THE ORDER IS GROQ, THEN GEMINI, THEN THIS MACHINE: ' + M.order.join(' -> ')
   + ' - Gemini is tried after Groq tires and before Ollama, never the other way round',
   JSON.stringify(M.order));
ok(!M.err && M.answer === 'A local answer.',
   'A GEMINI 429 FALLS THROUGH TO OLLAMA CLEANLY: the turn is answered by the local engine '
   + 'and no error reaches the caller - the rate limit is invisible, exactly as a Groq 429 is',
   JSON.stringify({ err: M.err, answer: M.answer }));
const gemRow = M.rows.find((r) => r.provider === 'gemini') || {};
const ollRow = M.rows.find((r) => r.provider === 'ollama') || {};
ok(gemRow.served === 'gemini' && gemRow.outcome === 'failed'
   && /429/.test(String(gemRow.reason || '')),
   'AND THE 429 IS NOT LOST, it is written down: served=gemini outcome=failed, reason "'
   + String(gemRow.reason || '').slice(0, 60) + '" - inaudible at the tongue, legible in '
   + 'the ledger',
   JSON.stringify(gemRow));
ok(ollRow.outcome === 'fallback' && M.rows.filter((r) => r.outcome === 'fallback').length === 1,
   'exactly ONE row in the turn says "fallback" - the engine that actually served - so the '
   + 'third tier did not turn one hop into two',
   JSON.stringify(M.rows.map((r) => [r.provider, r.outcome])));
/* THE RE-BASED HANDOVER CLOCK. triggerMs means the handover and is judged against a 250ms
   budget; left alone it would have reported Gemini's whole attempt as Ollama's handover. */
ok(ollRow.withinBudget === true && ollRow.triggerMs < M.budget,
   'and Ollama\'s handover is still measured as a handover: triggerMs ' + ollRow.triggerMs
   + 'ms against the ' + M.budget + 'ms budget, measuring the gap in front of ITS request '
   + 'rather than the Gemini attempt that preceded it',
   JSON.stringify({ gemini: gemRow.triggerMs, ollama: ollRow.triggerMs }));

/* =====================================================================================
   7 · ONE PROMPT, NOT TWO - what Gemini is handed, against what Groq is handed
   =====================================================================================
   THE SINGLE MOST IMPORTANT CORRECTNESS CLAIM IN THE MANDATE, and the bug class is named
   in section 1: the original Ollama path built its system prompt from a 343-character
   constant instead of wear_persona()'s assembly, so no hand could ever be proposed on
   fallback. The test is not "Gemini's prompt looks right" - it is that Gemini's prompt is
   a RE-ADDRESSING OF THE SAME OBJECT, which is arithmetic: every character in, every
   character out, and the system text equal to the joined system blocks of `worn` rather
   than merely similar to them. */
step('7 · the system prompt Gemini receives is the one Groq receives');

const G = python([
  'import json, sys, io',
  'sys.dont_write_bytecode = True',
  'sys.path.insert(0, ".")',
  'buf, real = io.StringIO(), sys.stderr',
  'sys.stderr = buf',
  'import server',
  'sys.stderr = real',
  'cfg = server.load_config()[0]',
  'man = server.capabilities_manifest(cfg) or ""',
  'msgs = server.assemble(system=server.SYSTEM_PROMPT, manifest=man, history=[],',
  '                       ask="send an email to bob about the invoice")[0]',
  // ONE `worn` LIST, built once, by the one function both engines are fed from.
  'worn = server.wear_persona(cfg, msgs)',
  'body, syschars = server._gemini_payload(worn)',
  'sysblob = body["systemInstruction"]["parts"][0]["text"]',
  // The same list as Groq would put on the wire, for the character arithmetic.
  'expect_sys = "\\n\\n".join(str(m["content"]) for m in worn if m["role"] == "system")',
  'expect_turns = [str(m["content"]) for m in worn if m["role"] != "system"]',
  'got_turns = [p["text"] for c in body["contents"] for p in c["parts"]]',
  'names = [t["name"] for t in server.hands.registry()]',
  // AND THE PROOF THAT THERE IS NO SECOND PATH: the two functions that touch Gemini,
  // searched for the names a divergent assembly would have to use.
  // EXECUTABLE CODE ONLY, which is the whole reason this goes through ast rather than a
  // grep: call_gemini's docstring NAMES the bug class it exists to avoid - it says the
  // word OLLAMA_FALLBACK_SYSTEM and the word wear_persona in prose - so a search over
  // raw source would be a search over the comment that promises the thing, and would
  // fail on a correct function for explaining itself. ast.unparse drops the comments and
  // the docstring is dropped by hand, leaving the statements that actually run.
  'import ast, inspect, textwrap',
  'def code_only(fn):',
  '    tree = ast.parse(textwrap.dedent(inspect.getsource(fn)))',
  '    fn_node = tree.body[0]',
  '    first = fn_node.body[0] if fn_node.body else None',
  '    if (isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant)',
  '            and isinstance(first.value.value, str)):',
  '        fn_node.body = fn_node.body[1:]',
  '    return ast.unparse(tree)',
  'src = code_only(server.call_gemini) + code_only(server._gemini_payload)',
  'print(json.dumps({',
  '  "sysChars": len(sysblob),',
  '  "sysEqualsWorn": sysblob == expect_sys,',
  '  "turnsEqualWorn": got_turns == expect_turns,',
  '  "roles": [c["role"] for c in body["contents"]],',
  '  "handsNamed": [n for n in names if n in sysblob],',
  '  "handsTotal": len(names),',
  '  "personaKept": ("Galaxy" in sysblob),',
  '  "manifestKept": ("WHAT YOU CAN ACTUALLY DO" in sysblob),',
  '  "fallbackConstChars": len(server.OLLAMA_FALLBACK_SYSTEM),',
  '  "mentionsOwnPrompt": any(w in src for w in ("SYSTEM_PROMPT", "PERSONA_DEFAULT",',
  '                            "OLLAMA_FALLBACK_SYSTEM", "SMALLTALK_PROMPT",',
  '                            "capabilities_manifest", "assemble(")),',
  '  "callsWearPersona": "wear_persona" in src,',
  '  "model": server.gemini_chat_model(cfg),',
  '  "maxTokens": server.MAX_ANSWER_TOKENS,',
  '}))',
]);

note('system instruction: ' + G.sysChars + ' chars, naming ' + G.handsNamed.length + '/'
     + G.handsTotal + ' hands; model ' + G.model);
ok(G.sysEqualsWorn === true,
   'WHAT GEMINI IS HANDED IS THE WORN LIST, CHARACTER FOR CHARACTER: systemInstruction is '
   + 'exactly the system blocks of the same `worn` object Groq is given, joined in order - '
   + 'not a rebuild that happens to agree',
   JSON.stringify({ chars: G.sysChars, equal: G.sysEqualsWorn }));
ok(G.turnsEqualWorn === true && G.roles.every((r) => r === 'user' || r === 'model'),
   'and the conversation survives the re-addressing intact: every non-system message\'s '
   + 'text is unchanged and only the ROLE WORD differs (' + G.roles.join(', ') + '), which '
   + 'is the one thing Google genuinely spells differently',
   JSON.stringify({ roles: G.roles, equal: G.turnsEqualWorn }));
ok(G.sysChars > 8000 && G.sysChars > G.fallbackConstChars * 10,
   'IT IS THE REAL PROMPT AND NOT A STRIPPED ONE: ' + G.sysChars + ' characters, against the '
   + G.fallbackConstChars + '-character constant whose use on the Ollama path was the '
   + 'original bug - a factor of ' + Math.round(G.sysChars / G.fallbackConstChars),
   JSON.stringify({ gemini: G.sysChars, theBug: G.fallbackConstChars }));
ok(G.personaKept === true && G.manifestKept === true
   && G.handsNamed.length === G.handsTotal && G.handsTotal >= 11,
   'WITH THE PERSONA AND EVERY ONE OF THE ' + G.handsTotal + ' HANDS IN IT, so there is no '
   + 'hand Gemini cannot be asked to propose - which is the whole of what the stripped '
   + 'prompt took away',
   JSON.stringify(G.handsNamed));
ok(G.mentionsOwnPrompt === false && G.callsWearPersona === false,
   'AND THERE IS NO SECOND ASSEMBLY PATH TO DIVERGE: the source of call_gemini and '
   + '_gemini_payload names no system prompt, no persona constant, no manifest builder and '
   + 'no assemble() - it cannot build a prompt, only re-address one it was handed',
   JSON.stringify({ mentions: G.mentionsOwnPrompt, wears: G.callsWearPersona }));

/* =====================================================================================
   8 · GEMINI, RUN FOR REAL - a hand proposed through the middle tier
   =====================================================================================
   The live clause. Groq is forced to 429 and Gemini is NOT stubbed, so the answer below
   came off Google's wire through the real chain. The hands-offer prompt is the one the
   server builds at the hands gate - SMALLTALK_PROMPT with hands.prompt_parts() - because
   a tool tag is the thing being judged and a different prompt would not be that test. */
step('8 · Groq at 429, Gemini live: the tool tag still comes back');

let L8 = null, liveWhy = '';
try {
  L8 = python([
    'import json, sys, io',
    'sys.dont_write_bytecode = True',
    'sys.path.insert(0, ".")',
    'buf, real = io.StringIO(), sys.stderr',
    'sys.stderr = buf',
    'import server',
    'sys.stderr = real',
    'cfg = server.load_config()[0]',
    'def tired(cfg_, messages, image=None, model=None, status=None):',
    '    if status is not None:',
    '        status.update({"code": 429, "transient": True})',
    '    return None, "Groq is rate limiting (429)."',
    // AND OLLAMA MADE UNMISTAKABLE, so an answer from it could never be read as Gemini's.
    'def oll(cfg_, messages, image=None, status=None):',
    '    if status is not None:',
    '        status.update({"reached": True, "slow": False, "model": "tripwire"})',
    '    return "OLLAMA-SERVED-THIS", None',
    'server.call_groq, server.call_ollama = tired, oll',
    'del server._ENGINE_LOG[:]',
    // THE HANDS GATE'S OWN PROMPT, built the way server.py builds it.
    'manifest, protocol = server.hands.prompt_parts()',
    'msgs, _plan = server.assemble(system=server.SMALLTALK_PROMPT, manifest=manifest,',
    '                              protocol=protocol,',
    '                              ask="send an email to bob@example.com saying the '
    + 'invoice is attached", label="hands-offer")',
    'worn = server.wear_persona(cfg, msgs)',
    'answer, err = server.call_groq_then_local(cfg, worn, None, "chat")',
    'wanted, params, prose = server.hands.tool_tag(answer or "")',
    'rows = [dict(r) for r in server._ENGINE_LOG]',
    'print(json.dumps({"answer": answer, "err": err, "wanted": wanted,',
    '                  "params": (params or "")[:300], "rows": rows}))',
  ], 240000);
} catch (e) { liveWhy = String(e.message || e).slice(0, 300); }

if (!L8) {
  /* A LIVE CLAUSE THAT COULD NOT BE RUN IS NOT A PASS AND NOT A ROUTING FAILURE. The free
     tier has a daily cap; a capped day is reported in one line, exactly as routing_proof's
     third outcome reports a sentence the room mangled. */
  note('LIVE CLAUSE NOT RUN: ' + liveWhy);
  ok(false, 'section 8 needs one live Gemini call and could not make it - see the line above',
     liveWhy);
} else {
  const gRow = (L8.rows || []).find((r) => r.provider === 'gemini') || {};
  note('served by: ' + (gRow.provider || '?') + ' (' + (gRow.model || '?') + '), tag: '
       + String(L8.wanted));
  note('answer: ' + JSON.stringify(String(L8.answer || L8.err || '').slice(0, 200)));
  ok(!L8.err && !!L8.answer && L8.answer !== 'OLLAMA-SERVED-THIS',
     'A TIRED GROQ IS ANSWERED BY GEMINI, LIVE: the turn came back through the real chain '
     + 'and NOT from the local engine, which was left answering a sentinel it did not get '
     + 'to say',
     JSON.stringify({ err: L8.err, answer: String(L8.answer || '').slice(0, 120) }));
  ok(gRow.served === 'gemini' && gRow.outcome === 'fallback' && gRow.provider === 'gemini',
     'AND THE LEDGER SAYS SO: provider=gemini served=gemini outcome=fallback, model '
     + (gRow.model || '?') + ', ms ' + gRow.ms + ' - §42\'s one new column value, in the '
     + 'rows the existing B1 instrumentation already reads',
     JSON.stringify(gRow));
  ok(L8.wanted === 'send_email',
     'THE HANDS CONTRACT SURVIVES THE NEW TIER: Gemini emitted [[tool: send_email ...]] and '
     + 'hands.tool_tag() read it - the same tag, read by the same parser, as through Groq '
     + 'and through Ollama',
     JSON.stringify({ wanted: L8.wanted, params: L8.params }));
  ok(/bob@example\.com/i.test(String(L8.params || '')),
     'with the details carried into the tag: ' + JSON.stringify(String(L8.params || '')
       .slice(0, 160)) + ' - so the proposal downstream is composed from a real address and '
     + 'not from prose',
     JSON.stringify(L8.params));
  ok(typeof gRow.ms === 'number' && typeof gRow.groqMs === 'number',
     'and the latency columns are filled for the new tier too: ms ' + gRow.ms + ', groqMs '
     + gRow.groqMs + ' - so a Gemini-served turn reads on the same instrumentation as a '
     + 'Groq-served one, with no change anywhere else',
     JSON.stringify(gRow));
}

say('');
say('  ' + '-'.repeat(74));
if (fail) { say('  FAILED:'); for (const f of failures) say('    - ' + f); say(''); }
say('  VERIFY ' + pass + '/' + (pass + fail) + (fail ? ' FAIL' : ' PASS'));
say('');
process.exit(fail ? 1 : 0);
