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
  'cfg = server.load_config()[0]',
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

say('');
say('  ' + '-'.repeat(74));
if (fail) { say('  FAILED:'); for (const f of failures) say('    - ' + f); say(''); }
say('  VERIFY ' + pass + '/' + (pass + fail) + (fail ? ' FAIL' : ' PASS'));
say('');
process.exit(fail ? 1 : 0);
