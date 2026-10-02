/* THE DIRECTOR, MADE FALSIFIABLE - §35 PART 2 and §36 PART 2.
 *
 * WHAT THIS FILE IS FOR, and it is not "does the mp4 exist". Every defect this pipeline had in
 * the building of it returned exit code 0, a playable file and in-budget numbers: a three-second
 * audio desync, a caption burned on top of the beat card it duplicated, a narrated note header,
 * a narrated URL, a bar chart of a figure the narration never spoke, an answer truncated
 * mid-word by the dispatcher's token ceiling - and then §36's own: a card that reprinted its
 * caption word for word, a frozen frame that held for nine seconds, a hook card that stopped
 * mid-clause, a flow box reading "Technical Authenticati". Not one of them was visible in the
 * JSON. So the assertions here are about MEASURED PROPERTIES OF THE ARTEFACT - stream counts off
 * ffprobe, cue counts off the SRT, note ids off script.md, durations off the WAV headers the
 * voice wrote, token overlap off the strings the filtergraph actually drew, and gray frame
 * differences off the finished mp4 - and each one names the failure it catches, because a budget
 * nobody can fail is not a budget.
 *
 * §35's FOUR CLAIMS, still proved here in its own words:
 *   "voiceover 40-70s; total wall <= 180s" (§36 raised the wall to 240 and this file asserts the
 *    raised number, which is the one §36 line that LOOSENS a budget - the stitch is now one
 *    re-encoding xfade chain instead of a -c copy concat);
 *   "ffprobe confirms one video + one audio stream; ledger row per video with topic, cited
 *    notes, duration, path"; "topic with no matching notes -> 'the notes hold nothing on X' and
 *    no mp4"; "one guest-refusal assertion"; "the real video run flows through the same bus".
 *
 * §36's SIX LAWS, each with the section that measures it:
 *   - no card body duplicates its captions - shared tokens < 40%            §5 and §8
 *   - five scene types, auto-classified, >= 3 distinct per >= 4-beat script §5 and §8
 *   - no static frame longer than 2s - gray MAD between t and t+1s         §7 and §8
 *   - 0.4s of real silence after each beat, one clock for three readers    §6
 *   - the two bookends, and no caption cue overlapping the hook            §6, §7, §8
 *   - a thumbnail JPG poster beside final.mp4                              §8
 *
 * THE SHAPE, and what each section costs. Two real renders (§8) because §36 names two exact
 * requests; seven one-scene encodes (§7) at about a second each, because a motion law asserted
 * only on the two finished files would not say WHICH scene type froze; everything else is a pure
 * function exercised standalone, which is the §32 shape - prove the predicate against the
 * predicate, and prove the integration against the artefact.
 *
 * WHAT IT REFUSES TO DO. It never writes config.json, never sends mail, never reads a
 * credential, and never asks a model anything except through the two renders - which may fall
 * back to the notes' own prose, and §8 asserts the result either way rather than requiring the
 * network. The one stubbed function is named where it is stubbed, and it is stubbed in §2 only,
 * so that proving the DOOR does not cost a video.
 *
 * Usage:  node director_proof.mjs          (no server required - this one is all local)
 */
import { spawnSync } from 'node:child_process';
import { existsSync, statSync } from 'node:fs';

/* The absolute path, as every harness on this machine uses: bare `python` here is the
   Microsoft Store stub, which exits without running anything. */
const PYTHON =
  'C:/Users/Fullstack Developer/AppData/Local/Programs/Python/Python313/python.exe';

const TOPIC = 'micro-saas pricing';
/* §36's SECOND MANDATED REQUEST, verbatim as the boss asked it: "explain useEffect in react".
   The two together are the proof that the scene grammar is read off the BEAT and not off a
   setting - one must come out with a chart in it and the other with a code card, from the same
   code path and the same corpus. */
const TOPIC2 = 'explain useEffect in react';
/* THE SILENT TOPIC, and it is measured rather than assumed: recall() answers opens=False at
   best 0.4748 for this one against this 55-note corpus. A topic the notes half-know would make
   §4 a coin toss. */
const SILENT = 'tungsten carbide lathe bearings';

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
   One python per section rather than one per claim: importing server.py costs about a second
   and a half, and a file that paid that forty times is a file nobody runs. */
function python(lines, ms) {
  const r = spawnSync(PYTHON, ['-c', lines.join('\n')],
                      { encoding: 'utf8', timeout: ms || 120000,
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

/* ---- the CLI runner ----
   SEPARATE FROM python() FOR ONE REASON: tools/make_video.py exits 1 when no video was made,
   which is correct - a shell script needs to know - and is exactly the case §4 asserts. A
   runner that threw on a non-zero status could not test the graceful empty at all. */
function cli(args, ms) {
  const r = spawnSync(PYTHON, ['tools/make_video.py', ...args],
                      { encoding: 'utf8', timeout: ms || 240000,
                        cwd: process.cwd(), env: { ...process.env, PYTHONIOENCODING: 'utf-8' } });
  if (r.error) throw new Error('cli: ' + r.error.message);
  const out = (r.stdout || '').trim();
  const brace = out.lastIndexOf('\n{');
  let body = {};
  try { body = JSON.parse(brace >= 0 ? out.slice(brace + 1) : out); } catch (e) { body = {}; }
  return { status: r.status, body, stdout: out, stderr: (r.stderr || '').slice(-600) };
}

say('\n  DIRECTOR PROOF - §35 PART 2 + §36 PART 2, the director\'s cut');
say('  ' + '-'.repeat(74));

/* =====================================================================================
   1 · THE COMMAND SURFACE - what it hears, and the much longer list of what it does not
   ===================================================================================== */
step('1 · the command surface: nine forms heard, thirteen sentences refused');

/* §35's own two command shapes, verbatim: "make a video about X", "video banao X par". The
   expectation column is the topic the peel leaves behind - "micro saas pricing" and not
   "micro-saas pricing", because _addressless_forms flattens punctuation before the pattern
   sees it. That is asserted rather than tolerated: both forms open retrieval (0.8349 and
   0.8315) and both slug to the same folder, so the peel costs nothing. */
const FORMS = [
  ['make a video about micro-saas pricing', 'micro saas pricing'],
  ['make me a video on cold email', 'cold email'],
  ['video banao pricing par', 'pricing'],
  ['pricing par video banao', 'pricing'],
  ['ek video banao micro-saas par', 'micro saas'],
  ['create a video about churn now', 'churn'],
  ['film a video on retention please', 'retention'],
  ['video bana do pricing par', 'pricing'],
  ['make a video', '*'],
];
/* THE SIEVE. The first nine are _DIRECT_NOT - sentences ABOUT videos, which an unanchored
   pattern would hear as orders to make one - and the last four are this section's own: two bare
   deictics, whose referent lives in the antecedent memory that this branch sits above, plus one
   sentence from each neighbouring branch, because the three share a funnel and the cheapest
   regression is a branch that starts eating its neighbour's sentences. */
const NOT = [
  'what video did you make', 'can you make videos', 'how do i make a video',
  'show me the video', 'play the video', 'why did you make that video',
  'is the video ready', 'delete the video', 'what is a video',
  'make a video about it', 'make a video about that',
  'study micro-saas now', 'what time is it in tokyo',
];

const C = python([
  'import json, server, voiceprint',
  'FORMS = ' + JSON.stringify(FORMS),
  'NOT = ' + JSON.stringify(NOT),
  // FORCED TRUE so the gate has something to guard: study_allowed() stands down entirely on a
  // machine with nothing enrolled, and a pass that came from an empty roster is not a pass.
  'voiceprint.has_hands_voice = lambda: True',
  'GATE = [[False, ""], [True, "BOSS"], [True, "GUEST"], [True, ""], [True, "MAYA"]]',
  'out = {',
  '  "heard": [[q, server.director_asked(q)] for q, _w in FORMS],',
  '  "deaf": [[q, server.director_asked(q)] for q in NOT],',
  // THE SAME GATE, ASSERTED BEHAVIOURALLY. director_allowed() calls study_allowed() rather than
  // copying it, and the way to prove that is the only way that survives an edit to either: run
  // both over the same matrix and require the answers to be identical, seal by seal.
  '  "gate": [[s, k, list(server.director_allowed(s, k)),',
  '            list(server.study_allowed(s, k))] for s, k in GATE],',
  '  "refusal": server.STUDY_REFUSAL,',
  '  "unpaid": list(server.UNPAID_CLASSES),',
  '  "protected": list(server.PROTECTED_CLASSES),',
  '  "module": server.director is not None,',
  '}',
  'print(json.dumps(out))',
]);

ok(C.module, 'server.py imports the director module');
for (const [q, want] of FORMS) {
  const got = (C.heard.find((r) => r[0] === q) || [])[1];
  ok(got === want, 'heard: "' + q + '" -> ' + JSON.stringify(want),
     'director_asked() answered ' + JSON.stringify(got));
}
const leaks = C.deaf.filter((r) => r[1]);
ok(leaks.length === 0,
   'all 13 controls refuse the branch - nine _DIRECT_NOT, two deictics, two neighbours',
   leaks.map((r) => r[0] + ' -> ' + JSON.stringify(r[1])).join(' | '));
const gateSame = C.gate.every((r) => JSON.stringify(r[2]) === JSON.stringify(r[3]));
ok(gateSame,
   'director_allowed() IS the Scholar\'s gate - identical over five (spoken, seal) pairs',
   JSON.stringify(C.gate));
const guestRow = C.gate.find((r) => r[0] === true && r[1] === 'GUEST');
ok(guestRow && guestRow[2][0] === false && guestRow[2][1] === C.refusal,
   'a GUEST seal is refused with STUDY_REFUSAL verbatim, not a second sentence',
   JSON.stringify(guestRow));
const bossRow = C.gate.find((r) => r[1] === 'BOSS');
ok(bossRow && bossRow[2][0] === true, 'a BOSS seal is admitted');
const typedRow = C.gate.find((r) => r[0] === false);
ok(typedRow && typedRow[2][0] === true,
   'the typed path is admitted unchanged - the keyboard is already the boss');
ok(C.unpaid.includes('direct') && C.protected.length === 4 && !C.protected.includes('direct'),
   'direct is an UNPAID class and is NOT a fifth PROTECTED class',
   'unpaid=' + C.unpaid.join(',') + ' protected=' + C.protected.join(','));

/* =====================================================================================
   2 · THE DOORMAN - a guest asks for a video, and nothing renders
   ===================================================================================== */
step('2 · the guest refusal, through the SHIPPED funnel');

/* WHY THE STUB IS HERE AND NOWHERE ELSE. This section is about the DOOR, and the door's whole
   job is to decide whether the render starts. So director.direct is replaced by a recorder that
   appends the topic it was called with and returns - which makes "nothing was rendered" a
   POSITIVE assertion about an empty list rather than the absence of a file, and makes the BOSS
   half of the matrix cost nothing. §8 runs the real pipeline, unstubbed, twice. */
const D = python([
  'import json, server, director, jobs, voiceprint',
  'voiceprint.has_hands_voice = lambda: True',
  'calls = []',
  // THE SIGNATURE IS direct()'s, report and all: the manager hands in the job it opened, and a
  // stub that would not accept it raises TypeError on the daemon thread where nobody is looking.
  'def _stub(topic, keep_parts=False, report=None):',
  '    calls.append(topic)',
  '    if report:',
  '        report.done("stubbed", cited=[], durationS=0.0, path="", sceneTypes=[], poster="")',
  '    return {"ok": True, "topic": topic, "answer": "stubbed", "cited": [], "voiceS": 0.0,',
  '            "path": "", "probe": {}}',
  'director.direct = _stub',
  'def ask(q, spoken, seal):',
  '    name, said = server.protected_answer(q, None, False, False, spoken, seal)',
  '    return {"route": name, "answer": (said or {}).get("answer"),',
  '            "direct": (said or {}).get("direct"),',
  '            "started": (said or {}).get("directStarted"),',
  '            "refused": (said or {}).get("refused"),',
  '            "job": (said or {}).get("directJob"),',
  '            "lookups": (said or {}).get("lookups")}',
  'out = {}',
  'out["guest"] = ask("make a video about micro-saas pricing", True, "GUEST")',
  'out["guestCalls"] = list(calls)',
  'out["blank"] = ask("make a video", True, "BOSS")',
  'out["blankCalls"] = list(calls)',
  'out["boss"] = ask("make a video about micro-saas pricing", True, "BOSS")',
  // The daemon thread has to be given a moment to reach the stub, or "it was called" would be
  // an assertion about thread scheduling rather than about the branch.
  'import time',
  'time.sleep(1.5)',
  'out["bossCalls"] = list(calls)',
  'out["live"] = list(director.MANAGER.live())',
  // THE ID THE PAGE WAS GIVEN, LOOKED UP ON THE BUS. The placeholder this used to return
  // ("pending") is non-empty and would pass any assertion that only counted characters.
  'out["known"] = len((jobs.public(out["boss"]["job"]).get("jobs") or []))',
  'out["allJobs"] = len((jobs.public().get("jobs") or []))',
  'out["refusalText"] = server.STUDY_REFUSAL',
  'print(json.dumps(out))',
]);

ok(D.guest.route === 'direct', 'a guest\'s request still ROUTES to direct - it is answered, '
   + 'not ignored', JSON.stringify(D.guest.route));
ok(D.guest.refused === 'not-the-boss',
   'the guest is refused with the reason code not-the-boss', JSON.stringify(D.guest.refused));
ok(D.guest.started === false, 'directStarted is false for the guest');
ok(D.guest.answer === D.refusalText,
   'the guest hears STUDY_REFUSAL verbatim', JSON.stringify(D.guest.answer));
ok(D.guestCalls.length === 0,
   'NOTHING RENDERED for the guest - direct() was never called even once',
   JSON.stringify(D.guestCalls));
ok(D.guest.lookups === 0, 'the refusal spends no lookups');
ok(D.blank.route === 'direct' && D.blank.started === false
   && /what should the video be about/i.test(D.blank.answer || ''),
   '"make a video" with no topic asks one question back and renders nothing',
   JSON.stringify(D.blank.answer));
ok(D.blankCalls.length === 0, 'the topicless request rendered nothing either');
ok(D.boss.started === true && D.boss.direct === true,
   'the BOSS\'s request starts, and says so on the payload', JSON.stringify(D.boss));
ok(/^Building your video on micro saas pricing - about three minutes, sir\.$/
   .test(D.boss.answer || ''),
   'the boss hears §35\'s announcement, word for word, at job start',
   JSON.stringify(D.boss.answer));
ok(typeof D.boss.job === 'string' && /^[0-9a-f]{10}$/.test(D.boss.job || ''),
   'the payload carries a job id, so the glass has something to poll',
   JSON.stringify(D.boss.job));
ok(D.known === 1 && D.allJobs === 1,
   'and THE BUS KNOWS THAT EXACT ID - it is the job that was opened, not a placeholder',
   JSON.stringify({ known: D.known, all: D.allJobs }));
ok(D.bossCalls.length === 1 && D.bossCalls[0] === 'micro saas pricing',
   'the render was handed to the thread exactly once, with the peeled topic',
   JSON.stringify(D.bossCalls));
ok(D.live[0] === '' && D.live[1] === '',
   'the manager is idle again once the (stubbed) render returns - the lock is released',
   JSON.stringify(D.live));

/* =====================================================================================
   3 · THE PROSE REPAIRS, §38's HOOK HEADLINE AND TOPIC READERS, AND THE DECLARED BUDGETS
   ===================================================================================== */
step('3 · the prose repairs, the hook headline, the topic readers and the constants, standalone');

/* THE HOOK FIXTURES, one per tier, and the middle one is not invented: it is the sentence the
   first §36 hook card cut at the word "to". */
const HOOKS = [
  'Price on the value delivered, not on the seats.',
  'Price your product at $50-$100 per month rather than $19 to significantly reduce the '
  + 'number of customers needed to reach your revenue goal.',
  'Target B2B micro-niches defined by high subscription price tolerance rather than consumer '
  + 'markets, as businesses demonstrate higher willingness to pay and lower churn friction '
  + 'for simple focused solutions.',
];

const P = python([
  'import json, director',
  'HEADER = "Micro-Saas - auto-studied Target B2B customers who already pay for tools. '
  + 'A second sentence that is perfectly fine."',
  // THE FIRST SENTENCE IS DELIBERATELY LONG ENOUGH TO SURVIVE: _sentences drops any part of 25
  // characters or fewer as a chunk-boundary crumb, so a four-word fixture would have proved the
  // crumb rule and said nothing at all about the URL rule.
  'URLS = "Pricing is the one lever that moves revenue without more traffic. '
  + 'Sources https://www.microsaasideas.net/pricing and more."',
  'LONG = "This one sentence runs on and on past any reasonable length for a spoken beat and '
  + 'keeps going well past thirty two words which is the ceiling this file enforces so that '
  + 'nothing is ever chopped in the middle of a clause again, truly."',
  'TYPO = "A dash \\u2013 and a ligature \\ufb01t \\ufb02ow."',
  // §38: a 37-word sentence that an author joined with a semicolon, and a 40-word one whose
  // FIRST half is still over the ceiling on its own. The first is salvaged as two sentences,
  // the second keeps only the half that fits - and neither is ever cut mid-clause.
  'SEMI = "The effect runs after the browser has painted the component onto the screen, which '
  + 'is later than most people expect; returning a function from it is how you tell React to '
  + 'tear that same work down before the next run begins."',
  'SEMI_LONG = "The effect that you pass to the hook will run again after the browser has '
  + 'painted every single one of the component subtrees that React has queued for this '
  + 'particular commit and for no other; it then returns the cleanup function you wrote."',
  'HOOKS = ' + JSON.stringify(HOOKS),
  'TOPIC = ' + JSON.stringify(TOPIC),
  // §38 PART 1's TWO LEXICAL READERS, on the REAL SCORES this machine returned for "explain
  // useEffect in react" - 0.778 / 0.743 / 0.674 / 0.568 - and the last of those four is the note
  // the share-picker sentence came out of. Synthetic text, measured scores: the point of the
  // fixture is the SHAPE of the ranking, which is what RECALL_GAP is cut against.
  'RTOPIC = "explain useEffect in react"',
  'HITS = [',
  '  {"id": "n1", "score": 0.778, "text": "The useEffect hook lets a react component '
  + 'synchronise with an external system after it renders."},',
  '  {"id": "n2", "score": 0.743, "text": "Returning a cleanup function from useEffect is how '
  + 'react tears that same effect down before the next run."},',
  '  {"id": "n3", "score": 0.674, "text": "React runs the effect after the browser has painted '
  + 'the component, which is later than people expect."},',
  '  {"id": "n4", "score": 0.568, "text": "If I pick a tab in the share picker the room keeps '
  + 'that tab on the wall until I stop it."},',
  ']',
  'TKEPT, TCUT = director.note_tier(RTOPIC, [dict(h) for h in HITS])',
  'VOCAB = director.topic_vocabulary(RTOPIC, TKEPT)',
  // THE CORPUS IS BUILT HERE EXACTLY AS topic_guard() BUILDS IT - the agreed vocabulary plus
  // every word of the notes that survived the tier - because _grounded() is only meaningful
  // against the same set the shipped caller hands it.
  'CORPUS = set(VOCAB) | set(director._words(" ".join(h["text"] for h in TKEPT)))',
  'ONTOPIC = "React runs the effect after the browser has painted your component."',
  'OFFTOPIC = "If I pick a tab in the share picker the room keeps that tab until I stop it."',
  'INVENT = "The useEffect hook cut our render cost by forty percent in production."',
  'rows = [{"text": "one", "seconds": 20.0, "start": 0.0},',
  '        {"text": "two", "seconds": 20.0, "start": 20.0},',
  '        {"text": "three", "seconds": 20.0, "start": 40.0},',
  '        {"text": "four", "seconds": 20.0, "start": 60.0}]',
  'kept, cut = director.fit_budget([dict(r) for r in rows])',
  'short = [{"text": "a", "seconds": 12.0, "start": 0.0},',
  '         {"text": "b", "seconds": 12.0, "start": 12.0},',
  '         {"text": "c", "seconds": 12.0, "start": 24.0}]',
  'kept3, cut3 = director.fit_budget([dict(r) for r in short])',
  'cues = director.caption_cues([{"text": " ".join(["word"] * 30), "seconds": 13.0,',
  '                               "start": 0.0}], 3.0)',
  'out = {',
  '  "header": director._sentences(HEADER),',
  '  "urls": director._sentences(URLS),',
  '  "long": director._sentences(LONG),',
  '  "typo": director._sentences(TYPO),',
  // fit_budget returns the DROPPED ROWS and not a count, so that a caller can say which lines
  // went. Counted here rather than re-shaped, so the assertion is about the real return value.
  '  "fit": {"kept": len(kept), "cut": len(cut),',
  '          "secs": round(sum(r["seconds"] for r in kept), 1)},',
  '  "fit3": {"kept": len(kept3), "cut": len(cut3)},',
  '  "cues": [{"start": round(c["start"], 2), "end": round(c["end"], 2),',
  '            "chars": max(len(l) for l in c["lines"]),',
  '            "rows": len(c["lines"])} for c in cues],',
  // §38: THE HOOK CARD IS A HEADLINE NOW. hook_rows() is retired with the lead silence it
  // existed for - what is carried is the headline, its word count, its wrapped rows and its
  // duplication share against the sentence the voice says over it.
  '  "heads": [{"head": director.hook_head(TOPIC, h), "sent": h,',
  '             "words": len(director.hook_head(TOPIC, h).split()),',
  '             "rows": len(director._wrap(director.hook_head(TOPIC, h), 26)),',
  '             "dup": director.duplication(director.hook_head(TOPIC, h), h),',
  '             "lastY": 230 + 72 * (len(director._wrap(director.hook_head(TOPIC, h), 26)) - 1)}',
  '            for h in HOOKS],',
  '  "headBare": director.hook_head("", HOOKS[0]),',
  '  "hooksIn": HOOKS,',
  // §38 PART 1's SENTENCE SALVAGE. SEMI is the shape the two best react notes carry: one
  // sentence of 37 words joined by a semicolon, which the >32-word rule used to drop whole.
  '  "semi": director._sentences(SEMI),',
  '  "semiLong": director._sentences(SEMI_LONG),',
  '  "tier": {"kept": [h["id"] for h in TKEPT], "cut": [h["id"] for h in TCUT]},',
  '  "tierOne": [h["id"] for h in director.note_tier(RTOPIC, [dict(HITS[0])])[0]],',
  '  "tierNone": [len(x) for x in director.note_tier(RTOPIC, [])],',
  '  "vocab": sorted(VOCAB),',
  '  "relOn": list(director.beat_relevance(ONTOPIC, VOCAB)),',
  '  "relOff": list(director.beat_relevance(OFFTOPIC, VOCAB)),',
  '  "grounded": [director._grounded(ONTOPIC, CORPUS), director._grounded(INVENT, CORPUS)],',
  '  "guardRe": [list(director._GUARD_RE.match(s).groups()) if director._GUARD_RE.match(s)',
  '              else None',
  '              for s in ["1. KEEP", "2) DROP", "3 - REWRITE: React runs the effect.",',
  '                        "4. rewrite: lower case still reads", "KEEP"]],',
  '  "slug": [director.slug_of(t) for t in ["micro-saas pricing", "micro saas pricing",',
  '                                         "", "A/B TESTS & prices!!"]],',
  '  "const": {"voiceMin": director.VOICE_MIN_S, "voiceMax": director.VOICE_MAX_S,',
  '            "wallMax": director.WALL_MAX_S, "pause": director.PAUSE_S,',
  '            "xfade": director.XFADE_S, "hook": director.HOOK_S, "cta": director.CTA_S,',
  '            "dupMax": director.DUP_MAX, "madMin": director.MOTION_MAD_MIN,',
  '            "seed": director.GRADIENT_SEED,',
  '            "motionSpeed": director.MOTION_SPEED, "chartSpan": director.CHART_SPAN,',
  '            "headlineWords": director.HEADLINE_WORDS, "sameKind": director.SAME_KIND_MAX,',
  '            "bulletMin": director.BULLET_MIN_WORDS, "bulletMax": director.BULLET_MAX_WORDS,',
  '            "bulletKeep": director.BULLET_KEEP_WORDS, "recallGap": director.RECALL_GAP,',
  '            "topicMin": director.TOPIC_MIN_WORDS, "topicNotes": director.TOPIC_NOTES_MIN,',
  '            "varietyMin": director.VARIETY_MIN, "varietyBeats": director.VARIETY_BEATS,',
  '            "kinds": list(director.SCENE_KINDS), "beatsMax": director.BEATS_MAX},',
  '  "text": director.TEXT,',
  '  "steps": list(director.STEPS),',
  '  "probe": director.probe(),',
  '}',
  'print(json.dumps(out))',
]);

ok(P.header.length >= 1 && !/auto-studied/.test(P.header.join(' ')),
   'the Scholar\'s "<Title> - auto-studied " header is never narrated',
   JSON.stringify(P.header));
ok(!/http|www\.|^sources/i.test(P.urls.join(' ')) && P.urls.length >= 1,
   'a note\'s trailing Sources URL block is never narrated',
   JSON.stringify(P.urls));
ok(P.long.length === 0,
   'a sentence over 32 words is DROPPED WHOLE, never chopped - the dangling-fragment fix',
   JSON.stringify(P.long));
ok(!/[\u2013\u2014\ufb01\ufb02]/.test(P.typo.join(' ')),
   'typography and PDF ligatures are flattened to ASCII before the synthesiser sees them',
   JSON.stringify(P.typo));
ok(P.fit.kept === 3 && P.fit.cut === 1 && P.fit.secs <= P.const.voiceMax,
   'fit_budget drops trailing lines by MEASURED duration until the voice is inside 70s',
   JSON.stringify(P.fit));
ok(P.fit3.kept === 3 && P.fit3.cut === 0,
   'fit_budget never cuts below three beats, even when the ceiling would ask it to',
   JSON.stringify(P.fit3));
const wide = P.cues.filter((c) => c.chars > 42 || c.rows > 2);
ok(P.cues.length >= 2 && wide.length === 0,
   'a 30-word beat becomes several cues, none wider than 42 columns or taller than 2 rows',
   JSON.stringify(P.cues));
const span = P.cues.length
  ? Math.abs((P.cues[P.cues.length - 1].end - P.cues[0].start) - 13.0) : 99;
ok(P.cues[0].start === 3.0 && span < 0.05,
   'with a lead passed in, the cues start at it and end when the voice does - no accumulated '
   + 'drift', JSON.stringify([P.cues[0].start, P.cues[P.cues.length - 1].end]));

/* ---- §38 PART 3: THE HOOK CARD IS A HEADLINE. §36's three hook_rows tiers are retired with
   the lead silence they existed for - they put the whole opening sentence on the glass in
   54-pixel type and then the voice spoke that same sentence over the NEXT scene. What is
   asserted now is the opposite property: the card is short, it is NOT the sentence, and it keeps
   the one duplication law every other card keeps. ---- */
ok(P.heads.every((h) => h.words >= 1 && h.words <= P.const.headlineWords),
   'the hook card carries a HEADLINE of at most 8 words - §38 PART 3, and the number is '
   + 'HEADLINE_WORDS rather than a literal', JSON.stringify(P.heads.map((h) => h.words)));
ok(P.heads.every((h) => h.rows <= 2 && h.lastY < 400),
   'it wraps into at most two 54px rows, high on the card, clear of the burned-in captions that '
   + 'now live where the old sign-off line was', JSON.stringify(P.heads.map((h) => h.lastY)));
ok(P.heads.every((h) => h.head !== h.sent && h.head.length < h.sent.length / 2),
   'THE HOOK SENTENCE IS NO LONGER ON THE HOOK CARD - it is spoken from t=0 and it lives in the '
   + 'captions, which is the whole of §38 PART 3; the three longest first sentences in the '
   + 'fixture set all come back as a headline under half their own length',
   JSON.stringify(P.heads.map((h) => h.head)));
ok(P.heads.every((h) => h.dup < P.const.dupMax),
   'and the card that §36 EXEMPTED from the duplication law now keeps it - the exemption was '
   + 'the lead silence, and the lead is gone', JSON.stringify(P.heads.map((h) => h.dup)));
ok(P.headBare.split(' ').length <= P.const.headlineWords && P.headBare.length > 0,
   'a topic too thin to print still yields a headline - the sentence\'s own keywords, then the '
   + 'house\'s four words, never an empty card', JSON.stringify(P.headBare));

/* ---- §38 PART 1: THE SENTENCE SALVAGE. The upstream half of the off-topic beat: the two
   best-scoring react notes carry their claims in 37- and 51-word sentences, the >32-word rule
   dropped both WHOLE, and the composer went hunting a third beat down the ranking - where it
   found the share picker. A semicolon is the author's own declaration that the halves stand
   alone, so they are split there and nowhere else. ---- */
ok(P.semi.length === 2 && P.semi.every((s) => s.split(' ').length <= 32),
   'a 37-word sentence joined by a semicolon is SPLIT INTO TWO narratable sentences instead of '
   + 'being dropped whole - §38 PART 1\'s upstream repair', JSON.stringify(P.semi));
ok(P.semi.every((s) => /^["']?[A-Z0-9$]/.test(s) && /[.!?]$/.test(s)),
   'and each half is a sentence IN WRITING too: the second is capitalised and both end in a '
   + 'full stop, because these become captions as well as speech', JSON.stringify(P.semi));
ok(P.semiLong.length === 1 && P.semiLong[0].split(' ').length <= 32,
   'a half that is still over the ceiling is still dropped - the split is not a licence to '
   + 'narrate anything, and nothing is ever CUT', JSON.stringify(P.semiLong));
/* ---- §38 PART 1: THE TWO READERS, on the real ranking. The share-picker sentence came out of a
   chunk that scored 0.568 while the react notes scored 0.778 / 0.743 / 0.674 - retrieval already
   knew, and nothing downstream asked it. Both readers are asserted here without a model, so the
   topic guard's floor holds with the network down; the MODEL half of the guard is measured on the
   live renders in section 8. ---- */
ok(JSON.stringify(P.tier.kept) === JSON.stringify(['n1', 'n2', 'n3'])
   && JSON.stringify(P.tier.cut) === JSON.stringify(['n4']),
   'note_tier KEEPS THE BAND AND DROPS THE PASSENGER: three notes inside 0.15 of the best hit, '
   + 'and the 0.568 chunk that the off-topic beat was written from is not handed to the writer '
   + 'at all', JSON.stringify(P.tier));
ok(JSON.stringify(P.tierOne) === JSON.stringify(['n1']),
   'and THE FIRST HIT IS ALWAYS KEPT - a topic with one note is a thin topic, not an empty one',
   JSON.stringify(P.tierOne));
ok(JSON.stringify(P.tierNone) === JSON.stringify([0, 0]),
   'while no notes at all tier to nothing, without an exception on the way',
   JSON.stringify(P.tierNone));
ok(P.vocab.includes('useeffect') && P.vocab.includes('react') && P.vocab.includes('explain')
   && !P.vocab.includes('browser'),
   'topic_vocabulary is what the notes AGREE on plus the boss\'s own words: "useeffect" and '
   + '"react" are in two notes each and "explain" is in the topic he typed, while "browser" '
   + 'appears in one note only and is not part of what this topic is made of',
   JSON.stringify(P.vocab));
ok(P.relOff[0] === 0 && P.relOff[1] === 0.0,
   'THE NAMED RELEVANCE CHECK, ON THE SENTENCE THAT SHIPPED: "if I pick a tab in the share '
   + 'picker..." corroborates ZERO words of the useEffect lexicon - it is not a near miss, it is '
   + 'a sentence about a different subject', JSON.stringify(P.relOff));
ok(P.relOn[0] >= P.const.topicMin && P.relOn[1] > 0,
   'where an on-topic sentence corroborates ' + P.relOn[0] + ' words at a share of ' + P.relOn[1]
   + ' - and the COUNT is the test while the share is only reported, because a share floor is '
   + 'gamed by brevity: a four-word beat with one topic word scores 0.25',
   JSON.stringify(P.relOn));
ok(P.grounded[0] === true && P.grounded[1] === false,
   'A REWRITE MAY ONLY RE-ARRANGE: a sentence built from the notes\' own words is grounded, and '
   + '"cut our render cost by forty percent" is NOT - which is the one place asking a model to '
   + 'rewrite narration could have leaked an invented statistic into the boss\'s own documents',
   JSON.stringify(P.grounded));
const gre = P.guardRe;
ok(gre[0][1].toUpperCase() === 'KEEP' && gre[1][1].toUpperCase() === 'DROP'
   && gre[2][1].toUpperCase() === 'REWRITE' && gre[2][2] === 'React runs the effect.'
   && gre[3][1].toUpperCase() === 'REWRITE' && gre[4] === null,
   'and the verdict line is parsed in the four shapes a thinker actually writes - "1. KEEP", '
   + '"2) DROP", "3 - REWRITE: <sentence>", lower case - while a line with no number is NOT read, '
   + 'so an unnumbered aside cannot silently re-judge beat one', JSON.stringify(gre));
ok(P.slug[0] === 'micro-saas-pricing' && P.slug[1] === 'micro-saas-pricing'
   && P.slug[2] === 'untitled' && !/[^a-z0-9-]/.test(P.slug[3]),
   'slug_of() is a filename and never anything else, and both peelings land in one folder',
   JSON.stringify(P.slug));
ok(JSON.stringify(P.steps)
   === JSON.stringify(['script', 'voice', 'scenes', 'captions', 'stitch']),
   'the five steps are §35\'s five, in §35\'s order');

/* ---- THE DECLARED NUMBERS, asserted so that a loosened budget cannot pass as a tightened one.
   §36 raises the wall from 180 to 240 and that is the ONE loosening in it, so the number is
   named here rather than inferred from whatever the file happens to hold. ---- */
ok(P.const.voiceMin === 40.0 && P.const.voiceMax === 70.0,
   'the voiceover budget is still §35\'s 40-70s', JSON.stringify(P.const));
ok(P.const.wallMax === 240.0,
   '§36\'s raised wall budget is 240s, declared as a constant and not as a magic number');
ok(P.const.pause === 0.4 && P.const.xfade === 0.5,
   '§36\'s 0.4s beat pause and 0.5s cross-dissolve are constants');
ok(P.const.dupMax === 0.40,
   '§36\'s duplication ceiling is 40% of the caption\'s own content words');
ok(P.const.madMin === 3.0 && P.const.motionSpeed === 0.10,
   'THE MOTION THRESHOLD IS NAMED: gray MAD >= 3.0 between t and t+1s, and the drift that clears '
   + 'it is 0.10 over a PINNED ramp - unpinned, gradients chose its orientation from a random '
   + 'seed per scene and the same filtergraph gave one beat 7.6 and the next 1.8');
ok(P.const.seed === 7,
   'and the ramp\'s seed and endpoints are pinned, so the motion law is asserted against a '
   + 'reproducible number rather than against a coin toss', JSON.stringify(P.const.seed));
ok(P.const.hook === 4.5 && P.const.cta === 5.0,
   '§38: the hook card\'s SHARE OF THE FIRST BEAT and the sign-off\'s tail are both declared - '
   + 'HOOK_S is no longer a lead silence, it is how long the title card holds over the opening '
   + 'sentence');
ok(P.const.bulletMin === 3 && P.const.bulletMax === 7 && P.const.bulletKeep === 3,
   '§38 PART 2\'s list law is three declared numbers: a bullet is 3 to 7 words, and the sentence '
   + 'must still hold 3 content words the card does not print',
   JSON.stringify([P.const.bulletMin, P.const.bulletMax, P.const.bulletKeep]));
ok(P.const.recallGap === 0.15 && P.const.topicMin === 1 && P.const.topicNotes === 2,
   '§38 PART 1\'s two readers are declared too: a note more than 0.15 below the best hit is not '
   + 'about the topic, and a beat needs one word corroborated by two of the notes that are',
   JSON.stringify([P.const.recallGap, P.const.topicMin, P.const.topicNotes]));
ok(P.const.kinds.length === 7 && P.const.kinds.includes('chart') && P.const.kinds.includes('code')
   && P.const.kinds.includes('flow') && P.const.kinds.includes('bullets')
   && P.const.kinds.includes('chips'),
   '§36\'s five scene types plus the two bookends are ONE declared table - a sixth cannot be '
   + 'added without appearing in SCENE_KINDS', JSON.stringify(P.const.kinds));
ok(P.probe.ffmpeg && P.probe.ffprobe && P.probe.voice && P.probe.fonts.bold,
   'the local toolchain is present: ffmpeg, ffprobe, the piper voice, the fonts - zero vendors',
   JSON.stringify({ ff: P.probe.ffmpeg, fp: P.probe.ffprobe, v: P.probe.voice,
                    why: P.probe.voiceWhy }));
ok(/y_align=font/.test(P.text || ''),
   'EVERY drawtext REFERS ITS y TO THE FONT\'S LINE METRICS, not to its own string\'s bounding '
   + 'box - without it two tokens of one code line given the same y do not share a baseline, and '
   + '`no wrapper` rode five pixels above `React 19:` on a shipped plate', JSON.stringify(P.text));
ok(P.probe.fonts.mono === true,
   'and the MONOSPACE font §36\'s code card needs - Consolas, already on this machine',
   JSON.stringify(P.probe.fonts));
note('ffmpeg is ' + (P.probe.ffmpegVersion || '?'));
note('the voice is ' + P.probe.voiceModel);

/* =====================================================================================
   4 · THE GRACEFUL EMPTY - through the mandated CLI, because it is cheap enough to
   ===================================================================================== */
step('4 · a topic the notes are silent on: a sentence, and no mp4');

/* §35 fixes the manual path as "tools/make_video.py --topic X --json, mirroring study_tick.py",
   so the CLI is driven here rather than described: argparse, the path insert, the one-JSON-line
   tail and the exit code are all under test, and this is the one path cheap enough (about two
   and a half seconds) to spend a whole process on. */
const E = cli(['--topic', SILENT, '--json'], 90000);
ok(E.body && typeof E.body === 'object' && E.body.topic === SILENT,
   'the CLI prints one JSON object on the last line, as a harness needs',
   E.stdout.slice(-200));
ok(E.body.ok === false, 'ok is false - there is no video');
ok(/^The notes hold nothing on tungsten carbide lathe bearings, sir/.test(E.body.answer || ''),
   '§35\'s own sentence: "the notes hold nothing on X"', JSON.stringify(E.body.answer));
ok(E.body.why === 'the notes hold nothing on this',
   'the reason is recall()\'s own opens=False and not a score this file re-derives',
   JSON.stringify(E.body.why));
ok(!E.body.path, 'no path is reported', JSON.stringify(E.body.path));
ok(!existsSync('output/videos/' + 'tungsten-carbide-lathe-bearings/final.mp4'),
   'NO MP4 EXISTS ON DISK for the silent topic - asserted off the filesystem, not off the JSON');
ok(E.status === 1, 'the CLI exits 1, so a shell script can tell', 'status=' + E.status);
ok((E.body.wallS || 99) < 20,
   'and it costs seconds rather than minutes - the empty is checked FIRST, before any encode',
   'wall=' + E.body.wallS + 's');

/* =====================================================================================
   5 · §36's SCENE GRAMMAR - the five types, the duplication law, and the number readers
   ===================================================================================== */
step('5 · the grammar: what a beat is classified as, and what the card may print');

/* THE BEAT FIXTURES. Every one of them is the shape of a real sentence from this corpus or from
   the two renders below, and each is here because it discriminates: a code beat with a known
   shape, a code beat whose shape would reprint the sentence, a tech beat with no identifier in
   it at all, a number beat, a process beat short enough that its own topic word is expensive, a
   list beat, and a sentence with nothing in it to draw. */
const BEATS = {
  code: 'The useEffect hook lets a component synchronise with an external system after it '
        + 'renders.',
  codeEcho: 'In React you reach for useEffect to subscribe to a source and to clean that '
            + 'subscription up.',
  codeUnknown: 'useThrottle is a hook you write yourself.',
  tech: 'The hook and the api are boilerplate for every component.',
  chart: 'Price your product at fifty to a hundred dollars a month, rather than nineteen '
         + 'dollars.',
  flow: 'Validate the idea first, then launch the product and refine the pricing.',
  list: 'Every micro-saas needs authentication, payments, email delivery, and a billing portal.',
  // §38 PART 2 ADDS THE SECOND LIST FIXTURE, and the pair is the whole point: `list` above is a
  // comma list of ONE- AND TWO-WORD items, which is what shipped bullets reading "Say" and
  // "Entire", so under §38 it is no longer a stack at all - it degrades to chips. `listLong` has
  // items of four words each behind a stem, so it IS a stack, and it is what the "every bullet is
  // at least three words" assertion is measured on.
  listLong: 'A good onboarding flow sends a welcome email, confirms the billing address, and '
            + 'invites the first teammate.',
  bare: 'It is the pricing that really matters here.',
};
/* THE SPOKEN-NUMBER CASES. The required chart vanished on a re-render because the model wrote
   the narration in words, so the reader that fixed it is proved on its own four edges: a range
   that says its unit once, the same words with a preposition between them that is NOT a range,
   a year and a port number, and a multiple. */
const SPOKEN = [
  ['fifty to a hundred dollars a month, rather than nineteen', ['$50', '$100', '$19']],
  ['a hundred at a hundred dollars', ['$100']],
  ['in 2026 the server listened on port 4700', []],
  ['one point five times the revenue', ['1.5x']],
  ['two hundred customers and three hundred leads', []],
];

const G = python([
  'import json, director',
  'BEATS = ' + JSON.stringify(BEATS),
  'SPOKEN = ' + JSON.stringify(SPOKEN.map((s) => s[0])),
  'TOPIC = ' + JSON.stringify(TOPIC),
  'CASES = {',
  '  "twice": "Prices rose 50% and then 50% again, and churn fell 200%.",',
  '  "years": "In 2026 the server listened on port 4700 and read 1 note.",',
  '  "huge": "A 1200% jump and a 5000x return.",',
  '  "mixed": "Conversion at 4% against a 3x multiple on 12 percent of users.",',
  '  "none": "Target the customers who already pay for tools.",',
  '}',
  // THE MAGNITUDE CASE, and it is the real sentence that produced the bad plate: three prices
  // and one annual revenue goal, where a shared scale draws one full-width bar and three stubs.
  'MAG = "Charge $19 or $50 to $100 a month and aim at $5,000 MRR."',
  'FAMILY = "Conversion at 4% and 9% on a $50 plan at $100."',
  // §38: THE SCRIPT THAT CANNOT REACH THREE TYPES, as a fixture, because the useEffect render
  // reached it for real on the first §38 sweep. Two sentences name an API and three are plain
  // prose - no figures, no arrow word, no identifier, no list - so after code is spent twice
  // there is nothing left for the director to choose. Before PART 2 the third type came from a
  // bullets stack whose rows were single words, which is exactly what this mandate deleted.
  // The two API sentences are written for this fixture rather than taken from BEATS, because
  // BEATS["code"] says "...after it renders" and the word `after` makes it a flow candidate too -
  // which the first draft of this fixture proved by failing on its own afford check.
  // AND THE SCRIPT THE GREEDY PASS WALKED PAST. Both opening sentences carry figures, the second
  // also says "from ... towards ... after" and is the only beat in the script that could be a
  // diagram; the three that follow are plain prose. One pass takes chart twice and ends on two
  // types with a flow still on the table - which is what the pricing render did on this sweep.
  'WALK = ["Starter sits at $19 and then the team plan jumps to $50 a month.",',
  '        "Revenue went from $4,000 towards $9,000 after the second price rise.",',
  '        BEATS["bare"], BEATS["tech"],',
  '        "Most teams only notice the difference when real users arrive."]',
  'PROSE = ["useThrottle is a hook you write yourself.",',
  '         "The useMemo hook caches one computed value for you.",',
  '         BEATS["bare"], BEATS["tech"],',
  '         "Most teams only notice the difference when real users arrive."]',
  'out = {',
  '  "numbers": {k: [f["label"] for f in director._numbers_in(v)] for k, v in CASES.items()},',
  '  "spoken": [[t, [f["label"] for f in director._spoken_numbers(t)]] for t in SPOKEN],',
  '  "mag": [f["label"] for f in director.chart_figures(MAG)],',
  '  "family": [f["label"] for f in director.chart_figures(FAMILY)],',
  '  "floorOne": [f["label"] for f in director.chart_figures("A single $50 plan.")],',
  // THE LAW ITSELF. §35's card WAS its caption, so it is the top of the scale and must measure
  // 1.0; a three-keyword label on the same sentence is the bottom; and a chart's own bar labels
  // against a narration that says those numbers in words must cost NOTHING.
  '  "dupWhole": director.duplication(BEATS["chart"], BEATS["chart"]),',
  '  "dupLabel": director.duplication("Product \\u00b7 Nineteen", BEATS["chart"]),',
  '  "dupFigures": director.duplication("$50 $100 $19", BEATS["chart"]),',
  '  "dupEmpty": director.duplication("", BEATS["chart"]),',
  '  "budget": [[k, director.shared_budget(v)] for k, v in BEATS.items()],',
  '  "classify": {k: director.classify_beat(v, TOPIC) for k, v in BEATS.items()},',
  // card_plan IS ASKED FOR EVERY TYPE ON EVERY BEAT, which is the only way to prove that a type
  // it cannot keep the law with is REFUSED rather than drawn badly.
  // §38: THE FOURTH COLUMN IS card_share, NOT duplication OF THE PRINTED TEXT. A stack of whole
  // list items reprints its own sentence by construction - that is what a list IS - and measuring
  // the printed string put every list beat at 1.000 and made THE LIST unreachable. The law the
  // pipeline keeps is the one asserted here, or the assertion is testing a different build.
  '  "plans": {k: {kind: list(director.card_plan(kind, v, TOPIC)[:3])',
  '                + [director.card_share(*director.card_plan(kind, v, TOPIC)[:3], v)]',
  '                for kind in ("chart", "code", "flow", "bullets", "chips")}',
  '            for k, v in BEATS.items()},',
  '  "all": director.classify_all([BEATS["chart"],',
  '                                BEATS["chart"].replace("nineteen", "twenty"),',
  '                                BEATS["chart"].replace("nineteen", "thirty"),',
  '                                BEATS["flow"], BEATS["listLong"]], TOPIC),',
  '  "fiveCharts": director.classify_all([BEATS["chart"]] * 5, TOPIC),',
  '  "prose": director.classify_all(PROSE, TOPIC),',
  '  "proseAfford": sorted({k for b in PROSE for k in director.classify_beat(b, TOPIC)}),',
  '  "walk": director.classify_all(WALK, TOPIC),',
  '  "walkAfford": sorted({k for b in WALK for k in director.classify_beat(b, TOPIC)}),',
  '  "walkOptions": [list(director.classify_beat(b, TOPIC)) for b in WALK],',
  '  "keys": director.keywords_in("useEffect runs significantly after every single render", 3),',
  '  "head": director.headline_of(BEATS["chart"], keys=3),',
  '  "headWords": len(director.headline_of(BEATS["chart"], keys=3).split()),',
  '  "topicHead": director.topic_head(TOPIC),',
  '  "flowBoxes": director.flow_of(BEATS["flow"]),',
  '  "listBullets": director.bullets_of(BEATS["list"]),',
  '  "listLong": director.bullets_of(BEATS["listLong"]),',
  '  "listWhole": director.bullets_of("Confirm the billing address, invite the first teammate, '
  + 'and send a welcome email."),',
  '  "codeShape": list(director.code_of(BEATS["code"])),',
  '  "codeNone": list(director.code_of(BEATS["tech"])),',
  '  "need": dict(director.NEED_ITEMS),',
  '}',
  'print(json.dumps(out))',
]);

/* ---- the number readers ---- */
ok(G.numbers.twice.length === 2,
   '_numbers_in dedupes: "50% ... 50% again ... 200%" is two bars, not three',
   JSON.stringify(G.numbers.twice));
ok(G.numbers.years.length === 0,
   'a year and a port number are not quantities - 2026 and 4700 draw nothing',
   JSON.stringify(G.numbers.years));
ok(G.numbers.mixed.length === 3,
   '%, x and the word percent are all read', JSON.stringify(G.numbers.mixed));
ok(G.numbers.none.length === 0, 'prose with no figures asks for no chart');
for (const [text, want] of SPOKEN) {
  const got = (G.spoken.find((r) => r[0] === text) || [])[1];
  ok(JSON.stringify(got) === JSON.stringify(want),
     'spoken numbers: "' + text.slice(0, 44) + '" -> ' + JSON.stringify(want),
     'read ' + JSON.stringify(got));
}
ok(JSON.stringify(G.mag) === JSON.stringify(['$19', '$50', '$100']),
   'chart_figures CLUSTERS BY MAGNITUDE: $19/$50/$100 keep their scale and the $5,000 goal is '
   + 'left off, because one full-width bar beside three stubs shows the viewer nothing',
   JSON.stringify(G.mag));
ok(JSON.stringify(G.family) === JSON.stringify(['$50', '$100']),
   'and ONE unit family only, money first - a 4% bar beside a $100 bar is two rectangles',
   JSON.stringify(G.family));
ok(G.floorOne.length === 0,
   'one figure is not a chart - the floor is two bars, because one bar is a labelled rectangle',
   JSON.stringify(G.floorOne));

/* ---- §36's FIRST LAW, measured on the scale it is defined over ---- */
ok(G.dupWhole === 1.0,
   '§35\'S CARD MEASURES 1.00 against its own caption - the defect the law exists to forbid is '
   + 'at the top of this scale and not somewhere in the middle of it', 'got ' + G.dupWhole);
ok(G.dupLabel < 0.40,
   'a two-keyword label on the same sentence measures ' + G.dupLabel + ', inside the ceiling');
ok(G.dupFigures === 0.0,
   'AND A CHART\'S BAR LABELS COST NOTHING: "$50 $100 $19" against a voice saying those numbers '
   + 'in words measures 0.0, because figures are not prose - otherwise §36\'s first-named scene '
   + 'type would have been its hardest to pass', 'got ' + G.dupFigures);
ok(G.dupEmpty === 0.0, 'an empty card duplicates nothing, by definition rather than by accident');
const budgets = Object.fromEntries(G.budget);
ok(Object.values(budgets).every((b) => b >= 1),
   'shared_budget never returns zero - a sentence always gets some label',
   JSON.stringify(G.budget));
ok(budgets.bare < budgets.list,
   'THE LABEL SHRINKS WITH THE SENTENCE: a six-word beat may reprint fewer of its own words '
   + 'than a fourteen-word one', JSON.stringify(G.budget));

/* ---- the classifier ---- */
ok(G.classify.code[0] === 'code',
   'a beat naming a hook this house knows the shape of is a CODE beat, first choice',
   JSON.stringify(G.classify.code));
ok(G.classify.chart[0] === 'chart',
   'a beat carrying two comparable figures is a NUMBER beat', JSON.stringify(G.classify.chart));
ok(G.classify.flow.includes('flow'),
   'a sentence that says "then" is a PROCESS beat', JSON.stringify(G.classify.flow));
ok(G.classify.listLong[0] === 'bullets',
   'a sentence whose comma list carries WHOLE PHRASES is a LIST beat', G.classify.listLong);
ok(JSON.stringify(G.classify.list) === JSON.stringify(['chips']),
   '§38: BUT A COMMA LIST OF SINGLE WORDS IS NOT A STACK ANY MORE - "authentication, payments, '
   + 'email delivery" shipped as bullets reading "Say" and "Entire", so a beat whose items are '
   + 'too short to be items renders as headline + chips instead', JSON.stringify(G.classify.list));
ok(JSON.stringify(G.classify.tech) === JSON.stringify(['chips']),
   'A TECH BEAT WITH NO IDENTIFIER IN IT IS NOT A CODE BEAT - "the hook and the api are '
   + 'boilerplate" falls through to chips rather than letting the house draw a signature it did '
   + 'not find', JSON.stringify(G.classify.tech));
ok(G.classify.codeUnknown.includes('code'),
   'but an identifier with no known shape IS a code beat - the card shows the name and draws no '
   + 'invented signature', JSON.stringify(G.classify.codeUnknown));
ok(JSON.stringify(G.codeShape[1].length ? 'shape' : 'none') === '"shape"'
   && G.codeShape[0] === 'useEffect',
   'code_of() answers with the API name and the shape the library documents',
   JSON.stringify(G.codeShape));
ok(G.codeNone[0] === '' && G.codeNone[1].length === 0,
   'and with nothing at all when the sentence names nothing', JSON.stringify(G.codeNone));
ok(JSON.stringify(G.classify.bare) === JSON.stringify(['chips']),
   'a sentence with no figures, no list, no movement and no identifier is a chips card',
   JSON.stringify(G.classify.bare));

/* ---- the plans: a type that cannot keep the law is REFUSED, not drawn badly ---- */
const plan = (beat, kind) => G.plans[beat][kind];
ok(plan('chart', 'chart')[0] === 'chart' && plan('chart', 'chart')[2].length === 3,
   'card_plan draws the chart it was asked for when the figures are there',
   JSON.stringify(plan('chart', 'chart')));
ok(plan('code', 'chart')[0] === 'chips',
   'AND REFUSES ONE WHEN THEY ARE NOT: asking for a chart of a sentence with no figures returns '
   + 'a chips card, where it used to return ("chart", headline, []) - a scene with a title and '
   + 'no visual at all', JSON.stringify(plan('code', 'chart')));
ok(plan('tech', 'code')[0] === 'chips',
   'and refuses a code card with no identifier to print', JSON.stringify(plan('tech', 'code')));
const codePlan = plan('code', 'code');
ok(codePlan[0] === 'code' && codePlan[2].length === 5 && codePlan[3] < 0.40,
   'A SIGNATURE IS KEPT WHOLE OR REPLACED, never trimmed: all four lines plus the API name '
   + 'survive at ' + codePlan[3] + ', because `const [state, dispatch] =` with nothing after it '
   + 'reads as a rendering fault', JSON.stringify(codePlan));
ok(plan('codeEcho', 'code')[0] === 'chips',
   'and a shape whose own identifiers would reprint the narration is REFUSED - the sentence that '
   + 'says "subscribe to a source" cannot also have subscribe(source) on the glass',
   JSON.stringify(plan('codeEcho', 'code')));
const flowPlan = plan('flow', 'flow');
ok(flowPlan[0] === 'flow' && flowPlan[2].length >= 2 && flowPlan[3] < 0.40,
   'THE SHORT PROCESS SENTENCE KEEPS ITS DIAGRAM at ' + flowPlan[3] + ': the topic headline '
   + 'spent one of its seven content words on the word "pricing" the sentence itself says, which '
   + 'measured 0.43 and lost the arrows - so a headline the boxes have already paid for is used '
   + 'instead', JSON.stringify(flowPlan));
const listPlan = plan('listLong', 'bullets');
ok(listPlan[0] === 'bullets' && listPlan[2].length >= 2 && listPlan[3] < 0.40,
   'a list beat keeps its stack at ' + listPlan[3] + ', with the topic as the headline - and §38 '
   + 'measures that share over the HEADLINE ALONE, because the items ARE the visual, exactly as a '
   + 'chart\'s bar labels are', JSON.stringify(listPlan));
ok(plan('list', 'bullets')[0] === 'chips',
   'and the single-word list is REFUSED a stack rather than given one word per row',
   JSON.stringify(plan('list', 'bullets')));
const allPlans = Object.values(G.plans).flatMap((byKind) => Object.values(byKind));
ok(allPlans.every((p) => p[3] < 0.40),
   'AND EVERY ONE OF THE ' + allPlans.length + ' (beat x type) PLANS CLEARS THE LAW - the '
   + 'degradation is exhaustive over this fixture set, not best-effort',
   JSON.stringify(allPlans.filter((p) => p[3] >= 0.40)));
ok(allPlans.every((p) => p[1].split(' ').length <= 8),
   'and no headline is longer than §36\'s eight words',
   JSON.stringify(allPlans.map((p) => p[1]).filter((h) => h.split(' ').length > 8)));
ok(G.headWords <= 8 && G.head.includes('·'),
   'headline_of() reads as a title - keywords joined by a middot, never a truncated clause',
   JSON.stringify(G.head));
ok(G.topicHead === 'Micro-saas Pricing',
   'topic_head() is the boss\'s own words, title-cased', JSON.stringify(G.topicHead));

/* THE WORDS ON A BOX ARE WHOLE WORDS FROM THE SENTENCE. "Technical Authenticati" shipped once,
   because a 22-character slice cuts mid-word; this is the assertion that would have caught it. */
const srcWords = (s) => s.toLowerCase().match(/[a-z0-9$%-]+/g) || [];
const whole = (labels, sentence) => {
  const bag = srcWords(sentence);
  return labels.every((l) => srcWords(l).every((w) => bag.includes(w)));
};
ok(G.flowBoxes.length >= 2 && whole(G.flowBoxes, BEATS.flow),
   'every flow box is made of WHOLE WORDS the sentence itself says - no character slicing',
   JSON.stringify(G.flowBoxes));
ok(G.listLong.length >= 2 && whole(G.listLong, BEATS.listLong),
   'and so is every bullet', JSON.stringify(G.listLong));
/* §38 PART 2, ON THE FIXTURE. The shipped stack read "Say" and "Entire" - the FIRST WORD of each
   comma part - so the floor is three words per bullet, and it is asserted on the parser rather
   than on the drawing, because the drawing cannot repair a one-word item. */
ok(G.listLong.every((b) => b.split(/\s+/).length >= 3),
   'EVERY BULLET IS AT LEAST THREE WORDS: whole list items, never first words',
   JSON.stringify(G.listLong.map((b) => [b, b.split(/\s+/).length])));
ok(G.listLong.every((b) => b.split(/\s+/).length <= 7),
   'and at most seven, so a bullet is a row on a card and not a paragraph in a smaller font',
   JSON.stringify(G.listLong));
ok(G.listBullets.length === 0,
   'the single-word list parses to NO BULLETS AT ALL, which is what sends it to chips - the '
   + 'refusal is in the parser, so every caller inherits it', JSON.stringify(G.listBullets));
ok(G.listWhole.length === 0,
   'AND A SENTENCE THAT IS NOTHING BUT ITS LIST GETS NO STACK EITHER: "confirm the billing '
   + 'address, invite the first teammate, and send a welcome email" would put the entire spoken '
   + 'sentence on the glass, so the parser requires at least three content words of the sentence '
   + 'to be left UNPRINTED - the card may carry the list, never the narration',
   JSON.stringify(G.listWhole));
ok(G.keys.includes('useEffect'),
   'keywords_in() carries the ORIGINAL SPELLING back - useEffect, never "Useeffect" on the glass',
   JSON.stringify(G.keys));
ok(!G.keys.includes('significantly'),
   'and demotes -ly adverbs, because length is a bad salience proxy at the top of the scale - '
   + 'the first chart plate was headlined "Significantly · High-ticket · Objectives"',
   JSON.stringify(G.keys));

/* ---- the director's variety rule ---- */
const counts = {};
for (const k of G.all) counts[k] = (counts[k] || 0) + 1;
ok(new Set(G.all).size >= P.const.varietyMin,
   '§36\'s VARIETY LAW on a five-beat script: ' + new Set(G.all).size + ' distinct scene types - '
   + JSON.stringify(G.all));
ok(Object.values(counts).every((n) => n <= P.const.sameKind),
   'no scene type is used more than SAME_KIND_MAX times - five number beats are not five bar '
   + 'charts, which is the slideshow again with bars on it', JSON.stringify(counts));
ok(G.fiveCharts.filter((k) => k === 'chart').length === 2,
   'five IDENTICAL number beats yield exactly two charts and then step aside',
   JSON.stringify(G.fiveCharts));
/* §38: AND THE OTHER END OF THAT RULE - a five-beat script that CANNOT reach three types. This
   is the shape the useEffect render took on the first §38 sweep, and the reason the on-video law
   below is measured against what the beats afford: stepping aside needs somewhere to step. */
ok(new Set(G.prose).size === 2 && G.prose.filter((k) => k === 'chips').length === 3,
   'A FIVE-BEAT SCRIPT OF TWO API SENTENCES AND THREE PLAIN ONES REACHES TWO TYPES, not '
   + P.const.varietyMin + ' - ' + JSON.stringify(G.prose) + ': code is spent after two and the '
   + 'remaining three sentences have no figures, no arrow word, no identifier and no list between '
   + 'them. §38\'s repair pass does not invent variety', JSON.stringify(G.prose));
ok(G.proseAfford.length === 2 && G.proseAfford.every((k) => G.prose.includes(k)),
   'AND NOTHING WAS LEFT ON THE TABLE: the union of every type those five sentences qualify for '
   + 'is ' + JSON.stringify(G.proseAfford) + ', and both were drawn - so the repetition is the '
   + 'narration\'s shape and not the director declining a card it could have cut',
   JSON.stringify({ afford: G.proseAfford, drawn: G.prose }));
/* §38's SECOND PASS, ON THE SCRIPT THAT CAUGHT IT. The greedy pass spends chart on both opening
   beats and the one diagram sentence in the script is never drawn - two types where three were
   available, which is what the pricing render shipped on the first §38 sweep. */
ok(JSON.stringify(G.walkOptions[1]).includes('flow') && !JSON.stringify(G.walkOptions[0]).includes('flow'),
   'THE SETUP IS THE REAL ONE: only the second of the five beats can be a diagram at all',
   JSON.stringify(G.walkOptions));
ok(new Set(G.walk).size >= P.const.varietyMin && G.walk[1] === 'flow',
   'AND THE SECOND PASS REACHES IT: ' + JSON.stringify(G.walk) + ' - the beat holding a chart its '
   + 'neighbour also drew gives that chart up for the flow nobody else in the script could draw, '
   + 'first-fit in beat order so the cut is reproducible from the sentences alone',
   JSON.stringify({ options: G.walkOptions, drawn: G.walk }));
ok(G.walkAfford.every((k) => G.walk.includes(k)),
   'and once again nothing available is left undrawn', JSON.stringify(
     { afford: G.walkAfford, drawn: G.walk }));
ok(JSON.stringify(G.need) === JSON.stringify({ chart: 2, code: 1, flow: 2, bullets: 2, chips: 0 }),
   'NEED_ITEMS is declared: what each type must have found before it may be drawn at all',
   JSON.stringify(G.need));

/* =====================================================================================
   6 · THE ONE CLOCK - the 0.4s pause as real silence, and the xfade arithmetic
   ===================================================================================== */
step('6 · one clock, three readers: the audio, the cues and the dissolves');

/* THE WAVS HERE ARE SYNTHESISED, NOT SPOKEN, and that is the point: a tone of known length lets
   "the pause is 0.4 seconds of ACTUAL SILENCE" be read out of the joined file byte by byte,
   which is not something piper's output could tell us. No model, no voice, no network. */
const K = python([
  'import json, math, os, struct, wave, director',
  'scratch = os.path.join("_runs", "sweep36")',
  'os.makedirs(scratch, exist_ok=True)',
  'rows = []',
  'for i in range(3):',
  '    path = os.path.join(scratch, "tone%02d.wav" % i)',
  '    with wave.open(path, "wb") as fh:',
  '        fh.setnchannels(1)',
  '        fh.setsampwidth(2)',
  '        fh.setframerate(22050)',
  '        fh.writeframes(b"".join(struct.pack("<h", int(9000 * math.sin(n * 0.08)))',
  '                                for n in range(22050)))',
  '    rows.append({"n": i + 1, "text": "line %d of the fixture" % (i + 1), "wav": path,',
  '                 "seconds": director.wav_seconds(path)})',
  // §38 PART 3: lead=0.0 EVERYWHERE. The voiceover begins at frame zero and the hook card now
  // takes a SHARE of the first beat's slot instead of a silent lead of its own - so the whole of
  // this section's arithmetic is re-derived from a lead of nothing.
  'stamped, total = director.timeline([dict(r) for r in rows], lead=0.0,',
  '                                   gap=director.PAUSE_S)',
  'dest = os.path.join(scratch, "joined.wav")',
  'full, why = director.join_wavs([dict(r) for r in rows], dest, lead=0.0,',
  '                               tail=director.CTA_S, gap=director.PAUSE_S)',
  'with wave.open(dest, "rb") as fh:',
  '    rate, width = fh.getframerate(), fh.getsampwidth()',
  '    raw = fh.readframes(fh.getnframes())',
  'def window(a, b):',
  '    return raw[int(a * rate) * width:int(b * rate) * width]',
  'open_loud = window(0.0, 0.2)',
  'gap_q = window(1.02, 1.38)',
  'line_loud = window(0.3, 0.9)',
  'tail_q = window(total + 0.1, total + director.CTA_S - 0.1)',
  'cues = director.caption_cues(stamped)',
  // AND THE SCENE SLOTS ARE SPLIT THE WAY make() SPLITS THEM: the hook takes half of beat one or
  // HOOK_S, whichever is less, and beat one keeps the remainder. One beat, two cards, one slot.
  'hook_s = round(min(director.HOOK_S, stamped[0]["slot"] / 2.0), 3)',
  'slots = ([hook_s, round(stamped[0]["slot"] - hook_s, 3)]',
  '         + [r["slot"] for r in stamped[1:]] + [director.CTA_S])',
  'out = {',
  '  "stamped": [{"n": r["n"], "start": r["start"], "slot": r["slot"],',
  '               "seconds": round(r["seconds"], 3)} for r in stamped],',
  '  "total": total, "full": full, "why": why,',
  '  "openLoud": max(open_loud) > 0, "gapSilent": set(gap_q) == {0},',
  '  "tailSilent": set(tail_q) == {0}, "lineLoud": max(line_loud) > 0,',
  '  "cues": [{"start": round(c["start"], 3), "end": round(c["end"], 3)} for c in cues],',
  '  "hookS": hook_s,',
  '  "slots": slots, "offsets": director.xfade_offsets(slots),',
  '  "oneSlot": director.xfade_offsets([7.0]),',
  '  "hook": director.HOOK_S, "cta": director.CTA_S, "gap": director.PAUSE_S,',
  '  "xfade": director.XFADE_S,',
  '}',
  'print(json.dumps(out))',
]);

const beats3 = K.stamped;
ok(beats3[0].start === 0.0,
   '§38: THE FIRST BEAT STARTS AT FRAME ZERO. It used to start at ' + K.hook + 's, and those were '
   + 'the four and a half seconds the boss watched in silence while the hook card sat there and '
   + 'the sentence it was made of was spoken later, over scene two', JSON.stringify(beats3[0]));
ok(beats3.every((r, i) => i === 0
      || Math.abs(r.start - (beats3[i - 1].start + beats3[i - 1].seconds + K.gap)) < 0.002),
   'and every later beat starts one measured line plus one 0.4s pause after the one before it',
   JSON.stringify(beats3.map((r) => r.start)));
ok(beats3.every((r) => Math.abs(r.slot - (r.seconds + K.gap)) < 0.002),
   'each row\'s SLOT is its own speech plus the pause - the number the scene is cut to',
   JSON.stringify(beats3.map((r) => r.slot)));
const wantTotal = beats3.reduce((s, r) => s + r.seconds + K.gap, 0);
ok(Math.abs(K.total - wantTotal) < 0.002,
   'timeline() returns the finished audio clock, lead and pauses included',
   'total=' + K.total + ' want=' + wantTotal);
ok(!K.why && Math.abs(K.full - (K.total + K.cta)) < 0.01,
   'THE JOINED WAV IS EXACTLY THAT CLOCK PLUS THE SIGN-OFF TAIL, measured off the file\'s own '
   + 'header: ' + K.full + 's against ' + (K.total + K.cta).toFixed(3) + 's', K.why);
ok(K.openLoud === true,
   'AND THE FIRST FRAMES OF THE JOINED WAV CARRY SOUND, read out of the file\'s own samples: the '
   + 'window from 0.00s to 0.20s is not all zeros, where under §36 the first 4.5 seconds were');
ok(K.gapSilent === true && K.lineLoud === true,
   '§36\'s 0.4s PAUSE IS REAL SILENCE TOO - the window after line one is all zeros while the '
   + 'line itself is not, which is what a pause synthesised into the TEXT could never guarantee');
ok(K.tailSilent === true,
   'and the tail under the sign-off card is silent for its whole length');
ok(K.cues.length >= 3 && K.cues[0].start <= 1.0,
   '§38 INVERTS THE HOOK EXEMPTION: the FIRST CAPTION starts at ' + K.cues[0].start + 's, inside '
   + 'one second, because the hook sentence is now spoken under the hook card instead of being '
   + 'printed on it - the card carries a headline only, and the words live in the captions like '
   + 'every other beat\'s', JSON.stringify(K.cues.slice(0, 2)));
ok(K.hookS > 0 && K.hookS <= K.hook
   && Math.abs((K.slots[0] + K.slots[1]) - beats3[0].slot) < 0.002,
   'and THE HOOK CARD SHARES BEAT ONE RATHER THAN CONSUMING IT: ' + K.hookS + 's of hook plus '
   + K.slots[1] + 's of scene equals the beat\'s own ' + beats3[0].slot + 's slot. Consuming it '
   + 'was measured: classify_all over beats[1:] for the useEffect script returned no code card at '
   + 'all, because the sentence that names the hook IS beat one',
   JSON.stringify([K.hookS, K.slots.slice(0, 2), beats3[0].slot]));
const lastBeat = beats3[beats3.length - 1];
ok(Math.abs(K.cues[K.cues.length - 1].end - (lastBeat.start + lastBeat.seconds)) < 0.01,
   'and the last cue ends exactly when the last line stops speaking - not when the file ends',
   JSON.stringify([K.cues[K.cues.length - 1].end, lastBeat.start + lastBeat.seconds]));
/* THE ARITHMETIC THAT CAN SILENTLY DESYNC EVERYTHING, checked against a hand sum. */
let acc = 0; const wantOffsets = K.slots.slice(0, -1).map((s) => { acc += s; return Math.round(acc * 1000) / 1000; });
ok(JSON.stringify(K.offsets) === JSON.stringify(wantOffsets),
   'xfade_offsets() is the running sum of the slots, one per JOIN and not one per scene: '
   + K.offsets.length + ' offsets for ' + K.slots.length + ' scenes', JSON.stringify(K.offsets));
ok(K.oneSlot.length === 0, 'a single scene has no transitions at all', JSON.stringify(K.oneSlot));
const picture = K.slots.reduce((s, x) => s + x, 0) + K.xfade;
ok(Math.abs((K.offsets[K.offsets.length - 1] + K.slots[K.slots.length - 1] + K.xfade) - picture)
   < 0.002,
   'and the chain it describes is sum(slots) + one dissolve long, so -shortest trims exactly the '
   + 'half second of overhang off the sign-off card', 'picture=' + picture.toFixed(3));
ok(Math.abs(picture - (K.full + K.xfade)) < 0.02,
   'THE PICTURE AND THE AUDIO AGREE TO THE FRAME: scenes ' + picture.toFixed(3) + 's, audio '
   + K.full.toFixed(3) + 's plus the trimmed dissolve - one clock, three readers');

/* =====================================================================================
   7 · THE SEVEN SCENE BUILDERS - each one encoded, probed, and MEASURED FOR MOTION
   ===================================================================================== */
step('7 · every scene type, one encode each: does it render, and does it move');

/* WHY EACH TYPE IS BUILT ALONE HERE. The motion law could be asserted on the two finished videos
   only, and then a frozen CODE card inside a moving film would pass - the sampled second would
   just land on another scene. One encode per type, at about a second each, says WHICH type
   froze. The static control at the end is what makes the threshold a measurement rather than a
   number: the same card without the drifting background must FAIL it. */
const SCENES = python([
  'import json, os, director',
  'folder = os.path.join(director.OUT_ROOT, "_sceneproof")',
  'os.makedirs(folder, exist_ok=True)',
  'SECS = 3.6',
  'FIGS = director.chart_figures("Charge $19 or $50 to $100 a month.")',
  'API, LINES = director.code_of("The useEffect hook synchronises with an external system.")',
  // §38: THE HOOK IS BUILT FROM THE SHIPPED READER rather than from a hand-written string, so
  // the band measurement below is of the card the pipeline actually draws.
  'HEAD = director.hook_head("micro-saas pricing",',
  '                          "Price on the value delivered, not on the seats.")',
  'builds = [',
  '  ("hook", lambda p: director.hook_card("micro-saas pricing", HEAD, SECS, p)),',
  '  ("chart", lambda p: director.chart_scene("Pricing \\u00b7 Tiers", FIGS, SECS, p)),',
  '  ("code", lambda p: director.code_scene("useEffect \\u00b7 Cleanup", API, LINES, SECS, p)),',
  '  ("flow", lambda p: director.flow_scene("Micro-saas Pricing",',
  '      ["Validate", "Launch", "Refine"], SECS, p)),',
  '  ("bullets", lambda p: director.bullets_scene("Micro-saas Pricing",',
  '      ["Authentication", "Payments", "Email Delivery"], SECS, p)),',
  '  ("chips", lambda p: director.chips_scene("Pricing \\u00b7 B2B",',
  '      ["pricing", "b2b", "tolerance"], SECS, p)),',
  '  ("cta", lambda p: director.cta_card("Micro-saas Pricing",',
  '      ["573caf07abc#0000", "f037d632def#0000"], SECS, p)),',
  ']',
  'out = {"scenes": [], "figs": [f["label"] for f in FIGS], "api": API, "lines": len(LINES)}',
  'for kind, build in builds:',
  '    path = os.path.join(folder, "%s.mp4" % kind)',
  '    err = build(path)',
  '    out["scenes"].append({"kind": kind, "err": err or "",',
  '                          "probe": director.probe_streams(path),',
  '                          "mad": director.motion_mad(path, 0.8),',
  '                          "bytes": os.path.getsize(path) if os.path.exists(path) else 0})',
  // THE NEGATIVE CONTROL. The same headline on a STILL background, through the same encoder:
  // this is §35's picture, and it must fail §36's threshold or the threshold means nothing.
  'still = os.path.join(folder, "still.mp4")',
  'graph = ("color=c=0x0a0f18:s=1280x720:r=30,"',
  '         + ",".join(director._headline("Pricing \\u00b7 B2B", "a frozen card")))',
  'out["stillErr"] = director._encode(graph, 3.6, still) or ""',
  'out["stillMad"] = director.motion_mad(still, 0.8)',
  // AND §35's OWN DRIFT SPEED, which is the other end of the control: not frozen, and still not
  // enough to clear the law §36 wrote after watching it.
  'slow = os.path.join(folder, "slow.mp4")',
  'graph35 = ("gradients=s=1280x720:c0=0x0a0f18:c1=0x12203a:x0=0:y0=0:x1=1280:y1=720:"',
  '           "seed=7:speed=0.01:r=30,"',
  '           + ",".join(director._headline("Pricing \\u00b7 B2B", "the \\u00a735 drift")))',
  'out["slowErr"] = director._encode(graph35, 3.6, slow) or ""',
  'out["slowMad"] = director.motion_mad(slow, 0.8)',
  // DID THE BARS ACTUALLY GROW. The bar band is cropped out of two frames - one before the
  // animation has run and one after - and reduced to a mean gray value: more bar is more ink.
  // Pillow is not installed, so the pixels come out of ffmpeg as a raw gray plane.
  'chart = os.path.join(folder, "chart.mp4")',
  'ff = director._which("ffmpeg")',
  'ink = {}',
  'for tag, at in (("early", "0.12"), ("late", "3.20")):',
  '    rawp = os.path.join(folder, tag + ".gray")',
  '    director._run([ff, "-hide_banner", "-loglevel", "error", "-y", "-ss", at, "-i",',
  '                   os.path.join(folder, "chart.mp4"), "-frames:v", "1",',
  '                   "-vf", "crop=820:240:150:286,scale=82:24,format=gray",',
  '                   "-f", "rawvideo", rawp])',
  '    try:',
  '        with open(rawp, "rb") as fh:',
  '            data = fh.read()',
  '        ink[tag] = round(sum(data) / float(len(data) or 1), 2)',
  '    except OSError:',
  '        ink[tag] = -1.0',
  'out["ink"] = ink',
  // §38 PART 3, MEASURED IN PIXELS: IS THE HOOK CARD'S BODY REALLY GONE. Two bands of the hook
  // encode are cropped to a raw gray plane - the headline band at y=220 and the band at y=400
  // where §36 printed the rest of the sentence and the "from your own notes" footer. The reading
  // is the band's MAXIMUM, not its mean: the drifting gradient makes a mean depend on where the
  // band sits, while white 54px type puts a 255 in any band it touches and the background's own
  // brightest colour is 0x12203a, a gray of about 32. So "no text here" is a hard number.
  'bands = {}',
  'for tag, crop in (("head", "1200:150:40:220"), ("body", "1200:260:40:400")):',
  '    rawp = os.path.join(folder, "hook-%s.gray" % tag)',
  '    director._run([ff, "-hide_banner", "-loglevel", "error", "-y", "-ss", "1.0", "-i",',
  '                   os.path.join(folder, "hook.mp4"), "-frames:v", "1",',
  '                   "-vf", "crop=%s,format=gray" % crop, "-f", "rawvideo", rawp])',
  '    try:',
  '        with open(rawp, "rb") as fh:',
  '            data = fh.read()',
  '        bands[tag] = max(data) if data else -1',
  '    except OSError:',
  '        bands[tag] = -1',
  'out["bands"] = bands',
  'out["head"] = HEAD',
  // AND THE KICKER, WHICH THE FIRST §38 PLATE CAUGHT SAYING THE HEADLINE TWICE. Two hook cards
  // are built - one whose headline IS the topic, one whose headline is a word out of the
  // sentence - and the 24px kicker band at y=70 is read the same way: present or absent, by its
  // brightest pixel, rather than by reading the filtergraph back as a string.
  'kick = {}',
  'for tag, head in (("same", "Explain useEffect In React"), ("diff", "Recommendations")):',
  '    path = os.path.join(folder, "kick-%s.mp4" % tag)',
  '    kick[tag + "Err"] = director.hook_card("explain useEffect in react", head, 2.0, path) or ""',
  '    rawp = os.path.join(folder, "kick-%s.gray" % tag)',
  '    director._run([ff, "-hide_banner", "-loglevel", "error", "-y", "-ss", "1.0", "-i", path,',
  '                   "-frames:v", "1", "-vf", "crop=1100:60:90:70,format=gray",',
  '                   "-f", "rawvideo", rawp])',
  '    try:',
  '        with open(rawp, "rb") as fh:',
  '            data = fh.read()',
  '        kick[tag] = max(data) if data else -1',
  '    except OSError:',
  '        kick[tag] = -1',
  'out["kick"] = kick',
  // AND THE CHIP BOX IS MEASURED AGAINST ITS OWN LABEL, IN PIXELS OF THE REAL FONT. The width
  // chips_scene() computes is compared with the ink the label actually lays down at the fontsize
  // it is actually drawn at: each word is rendered white on black at 32px bold, the rightmost
  // lit column is found, and the box must hold that plus the 24px of padding on each side the
  // label's own x assumes. Under the stale `20 * chars * 0.62` this reads 147 against a needed
  // 182 for "Handling", which is the 27 pixels it spilled out through its own outline.
  'CHIPW = ["Handling", "Simpler", "Authentication", "B2b", "Pricing", "Micro-saas"]',
  'fits = []',
  'for word in CHIPW:',
  '    rawp = os.path.join(folder, "chipw.gray")',
  '    graph = ("color=c=black:s=1280x160,drawtext=%s:fontfile=\'%s\':text=\'%s\':"',
  '             "fontsize=32:fontcolor=white:x=20:y=40,format=gray"',
  '             % (director.TEXT, director.FONT_BOLD, director._esc(word)))',
  '    director._run([ff, "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i", graph,',
  '                   "-frames:v", "1", "-f", "rawvideo", rawp])',
  '    with open(rawp, "rb") as fh:',
  '        data = fh.read()',
  '    lit = [x for x in range(1280)',
  '           if max(data[row * 1280 + x] for row in range(160)) > 90]',
  '    need = (max(lit) - 20 if lit else 0) + 48',
  '    fits.append({"word": word, "need": need,',
  '                 "box": int(32 * len(word) * 0.62) + 48,',
  '                 "old": int(20 * len(word) * 0.62) + 48})',
  'out["fits"] = fits',
  'print(json.dumps(out))',
], 300000);

ok(SCENES.figs.length === 3 && SCENES.api === 'useEffect' && SCENES.lines === 4,
   'the fixtures the builders are given come from the grammar itself, not from literals',
   JSON.stringify({ figs: SCENES.figs, api: SCENES.api, lines: SCENES.lines }));
for (const s of SCENES.scenes) {
  ok(!s.err && s.probe.video === 1 && s.probe.audio === 0
     && Math.abs((s.probe.durationS || 0) - 3.6) < 0.2,
     'the ' + s.kind + ' scene encodes: one video stream, no audio, 3.6s, no filtergraph error',
     JSON.stringify({ err: s.err, probe: s.probe }));
}
for (const s of SCENES.scenes) {
  ok(s.mad >= P.const.madMin,
     'MOTION LAW on the ' + s.kind + ' scene: gray MAD ' + s.mad + ' >= ' + P.const.madMin
     + ' between t and t+1s', 'a frozen card reads 0.0 - this one read ' + s.mad);
}
ok(!SCENES.stillErr && SCENES.stillMad >= 0 && SCENES.stillMad < P.const.madMin,
   'THE NEGATIVE CONTROL FAILS IT: the same headline on a still background reads '
   + SCENES.stillMad + ', under the threshold - so the law discriminates rather than passing '
   + 'everything ffmpeg can encode', JSON.stringify(SCENES.stillErr));
ok(!SCENES.slowErr && SCENES.slowMad < P.const.madMin,
   'AND SO DOES §35\'s OWN DRIFT: speed=0.01 reads ' + SCENES.slowMad + ', which is why §36 '
   + 'moved it to ' + P.const.motionSpeed + ' - the boss\'s "captioned slideshow" was moving, '
   + 'just not enough to see', JSON.stringify(SCENES.slowMad));
/* ---- §38 PART 3, IN PIXELS: the hook card's body is absent, not merely shortened ---- */
ok(SCENES.bands.head > 200,
   'THE HOOK CARD\'S HEADLINE BAND HOLDS TYPE: the brightest pixel between y=220 and y=370 reads '
   + SCENES.bands.head + ' of 255, so "' + SCENES.head + '" is on the glass',
   JSON.stringify(SCENES.bands));
ok(SCENES.bands.body >= 0 && SCENES.bands.body < 120,
   '§38 PART 3: AND THE BODY BAND IS EMPTY - the brightest pixel between y=400 and y=660 reads '
   + SCENES.bands.body + ', against a 255 where §36 printed the rest of the opening sentence and '
   + 'the "from your own notes" footer. That band is where the burned-in captions now go, and the '
   + 'sentence that used to be printed there is spoken from t=0 instead',
   JSON.stringify(SCENES.bands));
ok(!SCENES.kick.sameErr && !SCENES.kick.diffErr
   && SCENES.kick.same < 120 && SCENES.kick.diff > 150,
   'AND THE KICKER IS NOT THE HEADLINE TWICE: with "Explain useEffect In React" as the headline '
   + 'the kicker band reads ' + SCENES.kick.same + ' - empty - where a headline of different '
   + 'words leaves it at ' + SCENES.kick.diff + '. The first §38 plate printed '
   + '"EXPLAIN USEEFFECT IN REACT" in 24px directly above the same words in 54px, because '
   + 'hook_head() tries the topic first and usually wins it', JSON.stringify(SCENES.kick));
const tight = SCENES.fits.filter((f) => f.box < f.need);
const wouldHave = SCENES.fits.filter((f) => f.old < f.need);
ok(tight.length === 0 && wouldHave.length > 0,
   'EVERY CHIP FITS INSIDE ITS OWN BOX, measured in pixels of the real font at the real fontsize: '
   + SCENES.fits.map((f) => f.word + ' ' + f.need + '/' + f.box).join('  ')
   + ' - and the stale width this replaces fails ' + wouldHave.length + ' of the same '
   + SCENES.fits.length + ', which is "Handling" spilling 27 pixels out through its own outline '
   + 'on the first §38 plate', JSON.stringify({ tight, wouldHave }));
ok(SCENES.ink.late > SCENES.ink.early * 1.15 && SCENES.ink.early >= 0,
   'THE BARS GREW: the bar band is ' + SCENES.ink.late + ' mean gray at 3.2s against '
   + SCENES.ink.early + ' at 0.12s - measured in the band itself, so the background drift '
   + 'cannot account for it', JSON.stringify(SCENES.ink));

/* =====================================================================================
   8 · THE TWO MANDATED RENDERS - the boss's own two requests, end to end
   ===================================================================================== */
step('8 · the two renders §36 names: "' + TOPIC + '" and "' + TOPIC2 + '"');

note('two real renders: about 17s each with a warm piper cache, about 70s cold. Plates, '
     + 'ffprobe, the motion law and the ledger rows all come off these two files.');

const R = python([
  'import json, os, re, director, jobs, ingest',
  'TOPICS = ' + JSON.stringify([TOPIC, TOPIC2]),
  'PLATES = os.path.join("_runs", "sweep36")',
  'os.makedirs(PLATES, exist_ok=True)',
  'ff = director._which("ffmpeg")',
  'out = {}',
  'for topic in TOPICS:',
  // keep_parts SO THAT THE SCENE FILES SURVIVE for the lookbook, and because §8 asserts the
  // sweep-up rule separately on the files that are NOT kept.
  '    res = director.direct(topic, keep_parts=True)',
  '    slug = director.slug_of(topic)',
  '    folder = os.path.join(director.OUT_ROOT, slug)',
  '    mp4 = os.path.join(folder, "final.mp4")',
  '    secs = (res.get("probe") or {}).get("durationS") or 0.0',
  '    times = [2.0, round(secs * 0.22, 2), round(secs * 0.45, 2), round(secs * 0.7, 2),',
  '             round(max(0.5, secs - 4.0), 2)]',
  '    plates = []',
  '    for at in times:',
  '        png = os.path.join(PLATES, "plate-%s-%02ds.png" % (slug, int(at)))',
  '        if os.path.exists(mp4):',
  '            director._run([ff, "-hide_banner", "-loglevel", "error", "-y", "-ss", "%.2f" % at,',
  '                           "-i", mp4, "-frames:v", "1", png])',
  '        plates.append({"at": at, "png": png.replace("\\\\", "/"),',
  '                       "bytes": os.path.getsize(png) if os.path.exists(png) else 0})',
  '    def rd(name):',
  '        try:',
  '            with open(os.path.join(folder, name), encoding="utf-8") as fh:',
  '                return fh.read()',
  '        except OSError:',
  '            return ""',
  '    poster_path = os.path.join(folder, "poster.jpg")',
  '    magic = b""',
  '    try:',
  '        with open(poster_path, "rb") as fh:',
  '            magic = fh.read(3)',
  '    except OSError:',
  '        pass',
  '    srt = rd("captions.srt")',
  // §38 PARTS 1 AND 2, MEASURED OFF THE SHIPPED SCRIPT. The spoken beats are read back out of
  // script.md - the file a person opens to check the machine - and then re-measured against the
  // tiered vocabulary and re-parsed by the list reader, so the on-video assertions are about the
  // narration that was actually synthesised rather than about an intermediate the dict reports.
  '    spoken = re.findall(r"(?m)^\\s*\\d+\\.\\s+(.*\\S)\\s*$",',
  '                        rd("script.md").split("## Cited notes")[0])',
  '    live = (ingest.recall(topic, top_k=5) or {}).get("hits") or []',
  '    tiered = director.note_tier(topic, live)[0]',
  '    lexicon = director.topic_vocabulary(topic, tiered)',
  '    out[topic] = {',
  '      "res": res,',
  '      "job": (jobs.public(res.get("job") or "").get("jobs") or [{}])[0],',
  '      "rows": [r for r in jobs.ledger() if r.get("job") == res.get("job")],',
  '      "hitIds": [h.get("id") for h in',
  '                 ((ingest.recall(topic, top_k=5) or {}).get("hits") or [])],',
  '      "spoken": spoken,',
  '      "vocab": sorted(lexicon),',
  '      "relevance": [list(director.beat_relevance(b, lexicon)) for b in spoken],',
  '      "bulletSets": [director.bullets_of(b) for b in spoken],',
  // AND WHAT EACH SPOKEN BEAT COULD HAVE BEEN DRAWN AS, re-derived from the shipped sentence.
  // The variety law is judged against this below rather than against a flat three, because a
  // sentence with no figures in it cannot be a chart however the director feels about repetition.
  '      "afford": [list(director.classify_beat(b, topic)) for b in spoken],',
  '      "script": rd("script.md"), "srtCues": srt.count(" --> "),',
  '      "srtHead": srt[:60], "assHead": rd("captions.ass")[:420],',
  '      "assFades": rd("captions.ass").count("\\\\fad(120,120)"),',
  '      "mp4Bytes": os.path.getsize(mp4) if os.path.exists(mp4) else 0,',
  '      "posterBytes": os.path.getsize(poster_path) if os.path.exists(poster_path) else 0,',
  '      "posterMagic": magic.hex(),',
  '      "plates": plates, "mads": director.motion_mads(mp4, times) if os.path.exists(mp4) else [],',
  '      "parts": sorted(f for f in os.listdir(folder) if f.startswith("s0")',
  '                      or f.startswith("s1")) if os.path.isdir(folder) else [],',
  '      "leftovers": sorted(os.listdir(folder)) if os.path.isdir(folder) else [],',
  '    }',
  'print(json.dumps(out))',
], 900000);

const renders = [[TOPIC, 'chart'], [TOPIC2, 'code']];
let busRun = null;
for (const [topic, must] of renders) {
  const A = R[topic], V = A.res, probe = V.probe || {};
  if (!busRun) busRun = { topic, A, V };
  say('\n     ---- ' + topic + ' ----');
  ok(V.ok === true, '[' + topic + '] the render succeeded', JSON.stringify(V.why || ''));
  ok(V.wallS <= P.const.wallMax,
     '[' + topic + '] BUDGET: wall ' + V.wallS + 's, inside §36\'s ' + P.const.wallMax + 's');
  ok(probe.video === 1 && probe.audio === 1 && probe.vcodec === 'h264' && probe.acodec === 'aac',
     '[' + topic + '] FFPROBE: exactly one H.264 video stream and one AAC audio stream',
     JSON.stringify(probe));
  ok(A.mp4Bytes > 200000,
     '[' + topic + '] the file is a real encode (' + Math.round(A.mp4Bytes / 1024) + ' KB), not '
     + 'the 261-byte stub a dropped filtergraph leaves', 'bytes=' + A.mp4Bytes);
  /* THE CLOCK, READ BACK OFF THE FINISHED FILE. sceneTypes is the hook, the beats, an optional
     recap chart and the sign-off, so the recap's existence is arithmetic rather than a claim -
     and that makes the whole audio length predictable to the frame. */
  const recap = (V.sceneTypes || []).length - V.beats - 2;
  /* §38: THE LEAD TERM IS GONE from this sum, and its absence is the assertion. Under §36 the
     joined audio opened with HOOK_S of silence; now the speech starts at sample zero, so the
     audio is speech + pauses + an optional recap + the sign-off tail and nothing else. */
  const wantAudio = V.voiceS + V.beats * P.const.pause + recap * 4.5 + P.const.cta;
  ok(recap === 0 || recap === 1,
     '[' + topic + '] the scene list is hook + ' + V.beats + ' beats + ' + recap
     + ' recap + sign-off', JSON.stringify(V.sceneTypes));
  ok(Math.abs((V.audioS || 0) - wantAudio) < 0.05,
     '[' + topic + '] SYNC: the joined audio is ' + V.audioS + 's, which is NO LEAD + '
     + V.voiceS + ' speech + ' + V.beats + 'x0.4 pause' + (recap ? ' + 4.5 recap' : '')
     + ' + 5.0 tail = ' + wantAudio.toFixed(3) + 's', 'want ' + wantAudio);
  ok(Math.abs((probe.durationS || 0) - (V.audioS || 0)) < 0.35,
     '[' + topic + '] and the CONTAINER lasts exactly that long - the xfade offsets agree with '
     + 'the audio clock', 'duration=' + probe.durationS + ' audio=' + V.audioS);
  ok((V.sceneTypes || [])[0] === 'hook'
     && (V.sceneTypes || [])[(V.sceneTypes || []).length - 1] === 'cta',
     '[' + topic + '] §36\'s BOOKENDS are the first and last scenes',
     JSON.stringify(V.sceneTypes));
  /* ---- the first law, on the real artefact ---- */
  const dups = V.dup || [];
  ok(dups.length === V.beats + 1 && dups.every((d) => d.share < P.const.dupMax),
     '[' + topic + '] §36\'s FIRST LAW on all ' + dups.length + ' cards - the ' + V.beats
     + ' beat scenes AND THE HOOK, which §38 brings under the law for the first time because it '
     + 'no longer prints its sentence: every card\'s shared-token share with its own caption is '
     + 'under ' + P.const.dupMax + ' (max ' + V.dupMax + ')', JSON.stringify(dups));
  const hookDup = dups.find((d) => d.kind === 'hook') || {};
  ok(hookDup.share !== undefined && hookDup.share < P.const.dupMax,
     '[' + topic + '] and the HOOK\'S OWN SHARE is reported in the dict at ' + hookDup.share
     + ', where §36 exempted it entirely', JSON.stringify(hookDup));
  ok(V.dupMax < P.const.dupMax,
     '[' + topic + '] and the pipeline reports that maximum itself, in the dict and the ledger - '
     + 'so a regression shows up in a real render, not only under a harness', 'dupMax=' + V.dupMax);
  /* ---- the scene grammar, on the real artefact ---- */
  const kinds = V.sceneKinds || [];
  ok((V.sceneTypes || []).includes(must),
     '[' + topic + '] §36 REQUIRES A ' + must.toUpperCase() + ' SCENE IN THIS VIDEO, and there '
     + 'is one', JSON.stringify(V.sceneTypes));
  ok(must !== 'chart' || V.chart === true, '[' + topic + '] and the dict says chart=true');
  ok(must !== 'code' || V.code === true, '[' + topic + '] and the dict says code=true');
  if (V.beats >= P.const.varietyBeats) {
    // §38 MOVED THIS LAW ONTO ITS HONEST FOOTING, and the move cost a red before it earned one.
    // §36 asked for three distinct types in any film of four beats or more, flat. On this round's
    // useEffect render that failed - five beats drawn as code · code · chips · chips · chips - and
    // the cause is PART 2 of this very mandate: the third type in §36's cut of this film was a
    // BULLETS stack whose rows read "Say" and "Entire", single words the list parser no longer
    // produces. Nothing else about those three sentences changed; they never had figures to chart,
    // an arrow word to flow, or an identifier to type. So the flat three was only ever reachable
    // through the defect, and asserting it now would be asking the director to draw a chart out of
    // a sentence with no numbers in it. The law is therefore measured against WHAT THE BEATS
    // AFFORD - classify_beat() re-run on the shipped sentences - with the forced-repetition clause
    // below carrying the weight the number used to: a film short of three types must have left no
    // available type undrawn. That clause has teeth - it immediately reddened the PRICING film,
    // which had a flow sentence and drew chart twice instead, and classify_all() grew its second
    // pass to answer it. A fifth shape for prose-only beats is named for the Phase 3 punchlist.
    const afford = A.afford || [];
    const offered = [...new Set([].concat(...afford))].sort();
    const want = Math.min(P.const.varietyMin, offered.length);
    ok(afford.length === V.beats && kinds.length >= want,
       '[' + topic + '] VARIETY LAW against what the narration affords: ' + V.beats + ' beats, '
       + 'offering ' + JSON.stringify(offered) + ' between them, drawn as ' + kinds.length
       + ' distinct scene types ' + JSON.stringify(kinds) + ' - at least ' + want,
       JSON.stringify(afford));
    if (kinds.length < P.const.varietyMin) {
      ok(offered.length > 0 && offered.every((k) => kinds.includes(k)),
         '[' + topic + '] AND THE REPETITION IS FORCED RATHER THAN CHOSEN: every type any beat '
         + 'offered was actually drawn, so this film is short of three because the narration is '
         + 'short of three shapes - if a chart had been available anywhere and the film had '
         + 'repeated chips instead, this would be red',
         JSON.stringify({ offered, kinds, afford }));
    }
  } else {
    note('[' + topic + '] the variety law does not bind: ' + V.beats + ' beats, under the four '
         + '§36 names, drawn as ' + JSON.stringify(kinds) + '. Named rather than papered over - '
         + 'this corpus holds three narratable sentences on this topic.');
    ok(kinds.length >= 1 && kinds.every((k) => P.const.kinds.includes(k)),
       '[' + topic + '] and every type it did use is one of the declared seven',
       JSON.stringify(kinds));
  }
  /* ---- the motion law, on the real artefact ---- */
  const mads = A.mads || [];
  const frozen = mads.filter((m) => m.mad >= 0 && m.mad < P.const.madMin);
  const unread = mads.filter((m) => m.mad < 0);
  ok(mads.length === 5 && frozen.length === 0 && unread.length === 0,
     '[' + topic + '] MOTION LAW at five sampled seconds: '
     + mads.map((m) => m.at + 's=' + m.mad).join('  ') + ' - all >= ' + P.const.madMin,
     JSON.stringify({ frozen, unread }));
  /* ---- the plates, the poster, the captions ---- */
  ok(A.plates.length === 5 && A.plates.every((p) => p.bytes > 20000),
     '[' + topic + '] five plates grabbed off the finished file',
     JSON.stringify(A.plates.map((p) => p.at + 's ' + p.bytes + 'B')));
  for (const p of A.plates) {
    if (!existsSync(p.png)) ok(false, '[' + topic + '] plate ' + p.png + ' exists on disk');
  }
  ok(A.plates.every((p) => existsSync(p.png)),
     '[' + topic + '] and node can open all five from the repo root',
     JSON.stringify(A.plates.map((p) => p.png)));
  ok(A.posterBytes > 2048 && A.posterMagic.startsWith('ffd8ff'),
     '[' + topic + '] §36\'s THUMBNAIL exists beside final.mp4 and is a real JPEG by its own '
     + 'magic bytes (' + Math.round(A.posterBytes / 1024) + ' KB)',
     JSON.stringify({ bytes: A.posterBytes, magic: A.posterMagic }));
  ok(V.poster === 'output/videos/' + V.slug + '/poster.jpg' && existsSync(V.poster),
     '[' + topic + '] and the dict reports its repo-relative path for the Broadcaster',
     JSON.stringify(V.poster));
  ok(V.cues >= 5 && A.srtCues === V.cues,
     '[' + topic + '] the SRT holds exactly the ' + V.cues + ' cues the pipeline reported',
     'srt=' + A.srtCues);
  ok(/PlayResX:\s*1280/.test(A.assHead) && /PlayResY:\s*720/.test(A.assHead),
     '[' + topic + '] the BURNED file is an ASS with an explicit 1280x720 PlayRes',
     A.assHead.slice(0, 110).replace(/\n/g, ' | '));
  ok(A.assFades === V.cues,
     '[' + topic + '] and §36\'s CAPTION FADE is on every one of them - {\\fad(120,120)} x '
     + A.assFades, 'cues=' + V.cues + ' fades=' + A.assFades);
  /* §38 PART 3, READ OFF THE SHIPPED SRT RATHER THAN OFF THE DICT. §36 asserted the opposite of
     this - "no caption before the hook ends" - and that assertion was the defect, certified: the
     first spoken words landed 4.5 s in, over scene two, while the boss watched a silent title
     card. The inversion is the fix, and it is measured on the subtitle file the file ships with. */
  const m = /(\d\d):(\d\d):(\d\d),(\d\d\d)/.exec(A.srtHead || '');
  const firstCue = m ? (+m[1]) * 3600 + (+m[2]) * 60 + (+m[3]) + (+m[4]) / 1000 : -1;
  ok(firstCue >= 0 && firstCue <= 1.0,
     '[' + topic + '] VOICE AT FRAME ZERO: the first cue in the shipped SRT starts at ' + firstCue
     + 's, inside one second - §36 required it to start at or after ' + P.const.hook + 's and that '
     + 'is what the silent opening was', A.srtHead);
  /* ---- the script and its citations ---- */
  ok((V.cited || []).length >= 1, '[' + topic + '] the script cites at least one note',
     JSON.stringify(V.cited));
  const strays = (V.cited || []).filter((id) => !(A.hitIds || []).includes(id));
  ok(strays.length === 0,
     '[' + topic + '] every cited id is one retrieval actually returned - nothing invented',
     JSON.stringify(strays));
  const uncited = (V.cited || []).filter((id) => !(A.script || '').includes(id));
  ok((A.script || '').includes('## Cited notes') && uncited.length === 0,
     '[' + topic + '] script.md carries every cited note id under its own heading',
     JSON.stringify(uncited));
  ok(!/auto-studied|https?:\/\//.test((A.script || '').split('## Cited notes')[0] || ''),
     '[' + topic + '] and the NARRATION in it holds no note header and no URL');
  ok(V.beats >= 3 && V.beats <= P.const.beatsMax,
     '[' + topic + '] the narration is ' + V.beats + ' beats (3-' + P.const.beatsMax + ')');
  ok(typeof V.budgetOk === 'boolean'
     && V.budgetOk === (V.voiceS >= P.const.voiceMin && V.voiceS <= P.const.voiceMax),
     '[' + topic + '] budgetOk REPORTS the 40-70s floor honestly rather than enforcing it: '
     + V.voiceS + 's, budgetOk=' + V.budgetOk,
     'the asymmetry is §35\'s: a long script can be shortened, a short one can only be padded '
     + 'with prose the notes do not hold');
  if (!V.budgetOk) {
    note('[' + topic + '] NAMED, NOT CHASED: the voiceover is ' + V.voiceS + 's, under the 40s '
         + 'floor, because this corpus holds only ' + V.beats + ' narratable sentences on the '
         + 'topic. Padding it would mean inventing prose, which is the one thing the Director '
         + 'refuses.');
  }
  /* ---- §38 PART 1, ON THE SHIPPED VIDEO: the topic guard, and the relevance check by name ---- */
  ok(V.notesKept >= 1 && V.notesKept + V.notesDropped === (A.hitIds || []).length,
     '[' + topic + '] NOTE TIERING on the live retrieval: ' + V.notesKept + ' of '
     + (V.notesKept + V.notesDropped) + ' retrieved notes are inside 0.15 of the best hit and '
     + 'were handed to the writer; ' + V.notesDropped + ' were not',
     JSON.stringify({ kept: V.notesKept, dropped: V.notesDropped, hits: (A.hitIds || []).length }));
  const guard = V.guard || [];
  ok(guard.length >= V.beats && guard.every((g) => typeof g.words === 'number'
       && ['kept', 'rewritten', 'dropped'].includes(g.verdict)),
     '[' + topic + '] THE GUARD RAN AND LOGGED ONE VERDICT PER DRAFTED BEAT - ' + guard.length
     + ' judged, ' + guard.filter((g) => g.verdict === 'kept').length + ' kept, '
     + guard.filter((g) => g.verdict === 'rewritten').length + ' rewritten, '
     + guard.filter((g) => g.verdict === 'dropped').length + ' dropped',
     JSON.stringify(guard.map((g) => [g.n, g.verdict, g.by, g.words])));
  const spokenGuard = guard.filter((g) => g.verdict !== 'dropped');
  ok(spokenGuard.length === V.beats + (V.trimmed || 0),
     '[' + topic + '] and EXACTLY THE SURVIVORS WERE SPOKEN: ' + spokenGuard.length
     + ' kept-or-rewritten rows against ' + V.beats + ' beats in the film plus '
     + (V.trimmed || 0) + ' the 70s ceiling trimmed afterwards - a beat the guard dropped is '
     + 'never narrated, which is the whole of §38 PART 1',
     JSON.stringify([spokenGuard.length, V.beats, V.trimmed]));
  ok(V.guardMin >= P.const.topicMin,
     '[' + topic + '] EVERY SPOKEN BEAT PASSES THE NAMED RELEVANCE CHECK: the weakest corroborates '
     + V.guardMin + ' words of the tiered vocabulary, floor ' + P.const.topicMin,
     JSON.stringify(spokenGuard.map((g) => [g.n, g.words, g.share])));
  /* AND RE-MEASURED INDEPENDENTLY, off script.md rather than off the dict the pipeline wrote. */
  const rel = A.relevance || [];
  ok(rel.length === V.beats && rel.every((r) => r[0] >= P.const.topicMin),
     '[' + topic + '] re-read off the shipped script.md and re-measured against the tiered '
     + 'lexicon, all ' + rel.length + ' narrated sentences clear it too: '
     + JSON.stringify(rel.map((r) => r[0])),
     JSON.stringify((A.spoken || []).map((s, i) => [rel[i], s.slice(0, 50)])));
  ok(!/share picker|entire screen|mute|loudspeaker/i.test((A.spoken || []).join(' ')),
     '[' + topic + '] AND THE HOUSE-BEHAVIOUR SENTENCE IS NOT IN IT. "If I pick a tab in the '
     + 'share picker..." was beat four of the shipped useEffect video, lifted from a mixed note '
     + 'about this room\'s own screen sharing - the exact sentence, asserted by its own words',
     JSON.stringify((A.spoken || []).filter((s) => /share|screen|mute/i.test(s))));
  /* ---- §38 PART 2, ON THE SHIPPED VIDEO: no bullet is a first word ---- */
  const stacks = (A.bulletSets || []).filter((b) => b.length);
  const shortBullets = stacks.flat().filter((b) => b.split(/\s+/).length < P.const.bulletMin);
  ok(shortBullets.length === 0,
     '[' + topic + '] EVERY BULLET THIS FILM COULD DRAW IS AT LEAST ' + P.const.bulletMin
     + ' WORDS: ' + (stacks.length ? JSON.stringify(stacks.flat()) : 'no beat in it has list '
       + 'structure at all, so none was drawn as a stack - which is PART 2\'s other half')
     + '', JSON.stringify(shortBullets));
  ok(!(V.sceneKinds || []).includes('bullets') || stacks.length > 0,
     '[' + topic + '] and a BULLETS scene exists only where a narrated sentence really parses '
     + 'into whole items - a beat with no list structure is chips, never a stack of one-word rows',
     JSON.stringify({ kinds: V.sceneKinds, stacks: stacks.length }));
  note('[' + topic + '] ' + (V.sceneTypes || []).join(' · ') + '  |  wall ' + V.wallS
       + 's  ·  voice ' + V.voiceS + 's  ·  audio ' + V.audioS + 's  ·  file '
       + probe.durationS + 's  ·  dupMax ' + V.dupMax + '  ·  ' + V.cues + ' cues  ·  '
       + Math.round(A.mp4Bytes / 1024) + ' KB  ·  prose by ' + V.source);
}

/* THE TWO RENDERS ARE DIFFERENT FILMS, and that is the assertion the pair exists for: one code
   path, one corpus, two scene vocabularies chosen off the beats. */
const t1 = (R[TOPIC].res.sceneTypes || []).join(','), t2 = (R[TOPIC2].res.sceneTypes || []).join(',');
ok(t1 !== t2,
   'THE TWO VIDEOS ARE NOT THE SAME FILM WITH DIFFERENT WORDS: ' + t1 + '  vs  ' + t2);
ok(R[TOPIC].res.chart === true && R[TOPIC2].res.code === true,
   'the pricing video has the chart §36 demands and the react video has the code card - from one '
   + 'code path and one corpus, decided by the beats');

/* =====================================================================================
   9 · THE BUS AND THE LEDGER - §35 PART 3's claim, and §36's extra two fields
   ===================================================================================== */
step('9 · the first render, read back off the progress bus and out of the ledger');

const { V, A } = busRun;
const Q = A.job || {}, ev = Q.events || [];
ok(typeof V.job === 'string' && V.job.length > 0 && Q.job === V.job,
   'the run opened exactly one job and the result carries its id', JSON.stringify(V.job));
/* THE VERB IS UPPERCASE ON PURPOSE - open_job() cases it once so that the chip, the ledger and
   this harness cannot disagree about it - so the assertion is on the shipped case. */
ok(Q.name === 'director' && Q.verb === 'DIRECTING' && Q.topic === busRun.topic,
   'the job names its producer, its verb and its topic',
   JSON.stringify({ name: Q.name, verb: Q.verb, topic: Q.topic }));
ok(ev.length >= 5, 'it emitted ' + ev.length + ' events, at least one per step');
const seqs = ev.map((e) => e.seq);
ok(seqs.every((s, i) => i === 0 || s > seqs[i - 1]) && seqs[0] === 1,
   'the events are ORDERED BY THEIR OWN seq, 1 upward - asserted off the field and not off the '
   + 'array position, which would pass for a list that arrived shuffled', JSON.stringify(seqs));
const elapsed = ev.map((e) => e.elapsed_s);
ok(elapsed.every((s, i) => typeof s === 'number' && (i === 0 || s >= elapsed[i - 1])),
   'elapsed_s never goes backwards - it is monotonic, not the wall clock',
   JSON.stringify(elapsed));
const seen = ev.map((e) => e.step);
let cursor = -1, inOrder = true;
for (const w of ['script', 'voice', 'scenes', 'captions', 'stitch']) {
  const at = seen.indexOf(w, cursor + 1);
  if (at < 0) { inOrder = false; break; }
  cursor = at;
}
ok(inOrder, 'all five steps appear in the stream, in order', JSON.stringify(seen));
ok(ev.every((e) => typeof e.i === 'number' && typeof e.n === 'number' && e.n >= e.i && e.i >= 0),
   'every event carries a sane i of n, which is what the chip prints',
   JSON.stringify(ev.map((e) => e.i + '/' + e.n)));
ok(Q.n === 5 && Q.outcome === 'done',
   'the job closed as done over five steps', JSON.stringify({ n: Q.n, outcome: Q.outcome }));
ok(ev.every((e) => Object.keys(e).every((k) => ['job', 'step', 'i', 'n', 'detail', 'elapsed_s',
                                                'seq', 'at'].includes(k))),
   'no event carries a key outside §35\'s six plus the bus\'s own two');
/* §36's SCENE LIST ON THE WIRE: the scenes step's detail is what the glass prints mid-render,
   so the chip says "hook · chart · flow · ..." rather than a bare count. */
const scenesEv = ev.find((e) => e.step === 'scenes');
ok(scenesEv && (V.sceneTypes || []).every((k) => (scenesEv.detail || '').includes(k)),
   'the scenes event names every type it is about to draw, so the glass shows the shape of the '
   + 'film while it is being made', JSON.stringify(scenesEv && scenesEv.detail));

for (const [topic] of renders) {
  const rows = R[topic].rows, res = R[topic].res;
  ok(rows.length === 1,
     '[' + topic + '] EXACTLY ONE LEDGER ROW for this job', JSON.stringify(rows.length));
  const row = rows[0] || {};
  ok(row.topic === topic && row.outcome === 'done' && typeof row.elapsedS === 'number',
     '[' + topic + '] the row names the topic, the outcome and the wall cost',
     JSON.stringify({ t: row.topic, o: row.outcome, e: row.elapsedS }));
  ok(Array.isArray(row.cited) && row.cited.length === (res.cited || []).length,
     '[' + topic + '] it names the cited notes, all of them', JSON.stringify(row.cited));
  ok(typeof row.durationS === 'number'
     && Math.abs(row.durationS - ((res.probe || {}).durationS || 0)) < 0.5,
     '[' + topic + '] and the duration is the FILE\'s own measured one',
     'row=' + row.durationS + ' probe=' + (res.probe || {}).durationS);
  ok(row.path === res.path && existsSync(row.path || 'nowhere'),
     '[' + topic + '] the row names a path node can open', JSON.stringify(row.path));
  /* §36's TWO NEW LEDGER FIELDS, which are the whole point of a ledger a week later: a boss
     reading the log can see which beat was drawn as what, and that a thumbnail exists, without
     opening the mp4. */
  ok(JSON.stringify(row.sceneTypes) === JSON.stringify(res.sceneTypes),
     '[' + topic + '] THE ROW CARRIES §36\'s SCENE-TYPE LIST, exactly as rendered: '
     + JSON.stringify(row.sceneTypes), JSON.stringify(res.sceneTypes));
  ok(row.poster === res.poster && existsSync(row.poster || 'nowhere'),
     '[' + topic + '] and the poster path', JSON.stringify(row.poster));
  const result = (R[topic].job || {}).result || {};
  ok(JSON.stringify(result.sceneTypes) === JSON.stringify(res.sceneTypes)
     && result.poster === res.poster,
     '[' + topic + '] and the PAGE is told the same two things through /jobs - one whitelist, no '
     + 'second channel', JSON.stringify(result));
  note('[' + topic + '] ledger row: ' + JSON.stringify({
    topic: row.topic, cited: (row.cited || []).length, durationS: row.durationS,
    sceneTypes: row.sceneTypes, poster: row.poster, elapsedS: row.elapsedS }));
}

note('NOT PROVED HERE: the live spoken "make a video about X" into the running server. §1 and '
     + '§2 prove the pattern and the gate against the shipped functions; the ear itself is '
     + 'handshake_proof\'s subject.');
note('THE ONE MEASURABLE RESIDUE OF THE DUPLICATION LAW: a beat of only two content words, one '
     + 'of which is the word "notes", would leave card_plan() no clean headline at all and '
     + 'measures 0.5. It is unreachable from the pipeline - _sentences() drops anything of 25 '
     + 'characters or fewer, and make() always has a topic to fall back on - and it is named '
     + 'rather than hidden behind a rounded number.');

say('\n  ' + '-'.repeat(74));
if (failures.length) {
  say('  what failed:');
  for (const f of failures) say('    FAILED: ' + f);
}
say('  VERIFY ' + pass + '/' + (pass + fail) + ' ' + (fail ? 'FAIL' : 'PASS'));
process.exit(fail ? 1 : 0);
