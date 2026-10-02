/* THE BROADCASTER, MADE FALSIFIABLE - §40 PART 3.
 *
 * WHAT THIS FILE IS FOR. Every other harness in this house proves that something HAPPENS. This
 * one mostly proves that something CANNOT, which is a different kind of measurement and the
 * reason it is ten sections rather than four. A film this house puts on YouTube is the first
 * artefact it makes that a stranger can see and that nothing here may take back: there is no
 * undo, the audience is not the boss, and a mistake is a mistake in public under his name. So
 * the assertions are about PROPERTIES OF THE CLIENT rather than about a successful upload -
 * a successful upload proves the happy path and says nothing at all about the three failures
 * that would matter (a film published without a word being said, a film deleted, a film
 * published that this house never uploaded).
 *
 * THE ONE FACT THAT SHAPES EVERYTHING ELSE, and it is measured in §2 against Google's own
 * discovery document rather than remembered: videos.update and videos.delete accept the
 * IDENTICAL scope set. There is no grant that may change a film's privacy and may not delete
 * it. The narrow-scope defence is therefore unavailable, the Delete Prohibition has to be a
 * property of broadcast.py's SOURCE, and a property of source is exactly the sort of thing that
 * is true until somebody edits a file. Hence §1, which is the heart of this harness.
 *
 * §40's FOUR PREDICATE PROOFS, each with the section that measures it:
 *   - SEO lengths                      §3   (title <= 100 carrying the topic keyword, tags
 *                                            <= 500/30 chars, description <= 5000)
 *   - disclosure presence              §4   (and the refusal when the boss has approved none)
 *   - the delete-prohibition scan       §1   (source, AST, seven spellings, and the live refusal
 *                                            through the one door traffic really takes)
 *   - guest stays unlisted              §6   (both halves: a guest's "publish it" refused before
 *                                            a card exists, and a guest's "yes" with no window)
 *
 * WHAT IT REFUSES TO DO. It never writes config.json - the disclosure line §4 needs is passed
 * into package() in memory and never reaches disk. It never uploads: there is no connected
 * channel on this machine, which is a prerequisite reserved for the boss, and §10 reports that
 * as a blocked premiere rather than stubbing it green. It never deletes anything anywhere, which
 * is not a promise but a consequence - broadcast.py has no path that could. It reads no
 * credential: the one token fact it prints is a sha256 digest, and §10 asserts the absence of
 * everything else.
 *
 * Usage:  node broadcaster_proof.mjs        (server.py must be running on 4700)
 */
import { spawn, spawnSync } from 'node:child_process';
import { mkdtempSync, existsSync, mkdirSync, writeFileSync, statSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { basename, join } from 'node:path';

/* The absolute path, as every harness on this machine uses: bare `python` here is the
   Microsoft Store stub, which exits without running anything. */
const PYTHON =
  'C:/Users/Fullstack Developer/AppData/Local/Programs/Python/Python313/python.exe';
const GALAXY = 'http://127.0.0.1:4700';
const PORT = 9242;                       // nobody else's; see the port map in the lookbook
const CDP = 'http://127.0.0.1:' + PORT;
const W = 1280, H = 900;
const OUT = '_runs/sweep40';
const CHROMES = [
  'C:/Program Files/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Google/Chrome/Application/chrome.exe',
  process.env.LOCALAPPDATA + '/Google/Chrome/Application/chrome.exe',
];

/* THE PREMIERE'S FILM, named here once. §40 PART 3 says "one live premiere upload of the
   useEffect film", and this is the folder the Director left it in - 4,250,031 bytes of h264+aac
   at 50.65s, with a poster and the script.md the package is composed from. */
const FILM = 'output/videos/explain-useeffect-in-react';
/* THE TOPIC KEYWORD the title must carry, from that film's own script.md. */
const TOPIC = 'explain useEffect in react';
/* A DISCLOSURE LINE FOR THE PROOF, AND IT IS NOT THE BOSS'S. §40 reserves the approved
   affiliate-disclosure line to him and this harness may not invent one into config.json, so
   this string is passed to package() as an in-memory cfg and dies with the process. Every plate
   and every claim below that rests on it is labelled, and §4 proves the refusal that stands
   when it is absent - which is the state this machine is actually in. */
const TEST_DISCLOSURE =
  'Some links in this description are affiliate links (PROOF FIXTURE - not the approved line).';

let pass = 0, fail = 0; const failures = [];
const say = (m) => console.log(m);
const ok = (c, claim, detail) => {
  if (c) pass++; else { fail++; failures.push(claim); }
  say((c ? '  ok   ' : '  FAIL ') + claim);
  if (!c && detail) say('         ' + detail);
};
const note = (m) => say('  note ' + m);
const step = (m) => say('\n  ·· ' + m);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

/* ---- the predicate runner ----
   One python per section rather than one per claim: importing server.py costs about a second
   and a half, and a file that paid that twenty times is a file nobody runs. Every block ends
   by printing one line of JSON, and the LAST brace-opening line is the one read - so a module
   that writes to stdout on import cannot corrupt the reading. */
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
  try { return JSON.parse(brace >= 0 ? out.slice(brace + 1) : out); } catch (e) {
    throw new Error('python said something that was not JSON: ' + out.slice(-600));
  }
}

/* The hand crank, run as a shell would run it, because its exit status is part of its contract
   and a runner that threw on a non-zero status could not test a refusal. */
function crank(args, ms) {
  const r = spawnSync(PYTHON, ['tools/broadcast_film.py', ...args, '--json'],
                      { encoding: 'utf8', timeout: ms || 90000,
                        cwd: process.cwd(), env: { ...process.env, PYTHONIOENCODING: 'utf-8' } });
  const out = (r.stdout || '').trim();
  let body = {};
  const brace = out.lastIndexOf('\n{');
  try { body = JSON.parse(brace >= 0 ? out.slice(brace + 1) : out); } catch (e) { body = {}; }
  return { status: r.status, body, stdout: out, stderr: (r.stderr || '').slice(-500) };
}

async function http(path, init) {
  const r = await fetch(GALAXY + path, init);
  const ctype = r.headers.get('content-type') || '';
  const buf = Buffer.from(await r.arrayBuffer());
  let body = null;
  if (ctype.includes('json')) { try { body = JSON.parse(buf.toString('utf8')); } catch { } }
  return { status: r.status, ctype, bytes: buf.length, magic: buf.slice(0, 3).toString('hex'),
           body };
}
const post = (path, payload) => http(path, {
  method: 'POST', headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(payload || {}) });

say('\n  BROADCASTER PROOF - §40 PART 3');
say('  ' + '-'.repeat(74));

try { mkdirSync(OUT, { recursive: true }); } catch { }

/* =====================================================================================
   1 · THE DELETE PROHIBITION
   The one law in this house that cannot be undone by anything, asserted four ways: by
   constant, by AST, by execution, and through the real door. Four, because each of the first
   three can be true while the thing is still deletable.
   ===================================================================================== */
step('1 · the delete prohibition: by constant, by AST, by execution, and through the door');

const P = python([
  'import ast, inspect, io, json, re, sys',
  'sys.dont_write_bytecode = True',
  'import broadcast',
  'out = {}',
  'src = io.open("broadcast.py", encoding="utf-8").read()',
  // DOCSTRINGS AND COMMENTS STRIPPED FIRST. The module's own prose is where it swears the verb
  // off, so a plain search over the file finds the promise and reports it as the crime.
  'def strip(text):',
  '    text = re.sub(r\'"""[\\s\\S]*?"""\', \'""\', text)',
  '    return re.sub(r"#.*$", "", text, flags=re.M)',
  'code = strip(src)',
  'out["methods"] = list(broadcast.METHODS_ALLOWED)',
  // THE ONE PLACE "videos.delete" IS ALLOWED TO APPEAR, and it must appear there. discovery()
  // READS GOOGLE'S SCOPE TABLE for the delete method - that read is §40's own required evidence,
  // the measurement that proves update and delete share a scope set and that the prohibition
  // therefore has to live here in the source. A scan blunt enough to forbid the word would
  // forbid the proof of why the word is forbidden. So the source is scanned in two halves:
  // inside discovery(), where the name is a row in a document, and everywhere else, where it
  // would be a request.
  // STRIPPED THE SAME WAY BEFORE IT IS CUT OUT, or the cut silently misses: `code` has had its
  // docstrings and comments removed and raw getsource() has not, so the two texts never match
  // and the scope-table read stays in the half it is being excluded from.
  'doc = strip(inspect.getsource(broadcast.discovery_check))',
  'elsewhere = code.replace(doc, "")',
  'assert doc in code, "the discovery read was not found in the stripped source"',
  'out["deleteWords"] = len(re.findall(r"\\bDELETE\\b", code))',
  'out["deleteEndpoints"] = len(re.findall(r"videos\\.delete|/videos\\?id=", elsewhere))',
  'out["deleteInDiscovery"] = len(re.findall(r"videos\\.delete", doc))',
  'out["discoveryIssues"] = sorted({n.func.attr for n in ast.walk(ast.parse(doc.strip()))'
  + ' if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}'
  + ' & {"_http", "urlopen", "insert", "set_privacy"})',
  'out["codeChars"] = len(code)',
  // -- the AST: one door, and the guard is its first statement.
  'tree = ast.parse(src)',
  'funcs = {n.name: n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}',
  'http_fn = funcs.get("_http")',
  'body = [n for n in http_fn.body if not (isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant))]',
  'out["firstStatementGuards"] = "_refuse_method" in ast.dump(body[0])',
  'out["socketOpeners"] = sorted({fn.name for fn in funcs.values() for n in ast.walk(fn)'
  + ' if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)'
  + ' and n.func.attr == "urlopen"})',
  // -- the guard, executed, in seven spellings and three that must still pass.
  'refused, slipped = [], []',
  'for verb in ("DELETE", "delete", " Delete ", "PATCH", "HEAD", "OPTIONS", ""):',
  '    try:',
  '        broadcast._refuse_method(verb)',
  '    except broadcast.Prohibited:',
  '        refused.append(verb or "(empty)")',
  '    except Exception as exc:',
  '        slipped.append("%r raised %s" % (verb, type(exc).__name__))',
  '    else:',
  '        slipped.append("%r allowed" % verb)',
  'passed = []',
  'for verb in ("GET", "post", " Put "):',
  '    try:',
  '        passed.append(broadcast._refuse_method(verb))',
  '    except Exception as exc:',
  '        slipped.append("%r refused: %s" % (verb, exc))',
  'out["refused"], out["slipped"], out["passed"] = refused, slipped, passed',
  // -- IS IT AN EXCEPTION OR A RETURN VALUE? The distinction is the whole of the design: a
  // falsy return is ignorable at a call site and a raise is not.
  'out["prohibitedIsException"] = issubclass(broadcast.Prohibited, Exception)',
  // -- and through the real door, against a real URL, with no socket opened.
  'try:',
  '    broadcast._http("DELETE", broadcast.API_BASE + "/videos?id=aaaaaaaaaaa")',
  '    out["doorRefuses"] = False',
  'except broadcast.Prohibited:',
  '    out["doorRefuses"] = True',
  'except Exception as exc:',
  '    out["doorRefuses"] = "raised " + type(exc).__name__',
  'out["refusedCount"] = broadcast._SEEN["refusedDelete"]',
  // -- forget() is the only function in the module with a destructive name, and what it
  // destroys is this machine's own token file. Asserted off its source, not its docstring.
  'out["forgetSource"] = inspect.getsource(broadcast.forget)',
  'out["scope"] = broadcast.scope_report()',
  'print(json.dumps(out))',
]);

ok(JSON.stringify(P.methods) === JSON.stringify(['GET', 'POST', 'PUT']),
   'THE TRANSPORT KNOWS THREE VERBS: ' + P.methods.join(', ') + ' - an upload needs POST and '
   + 'PUT, a verification needs GET, and there is no fourth',
   JSON.stringify(P.methods));
ok(P.deleteWords === 0 && P.deleteEndpoints === 0,
   'and the verb DELETE appears NOWHERE in ' + P.codeChars + ' characters of its code, nor does '
   + 'any videos.delete endpoint outside the scope-table read - measured with the docstrings '
   + 'stripped, so the module\'s own promise is not read back as the crime',
   JSON.stringify({ words: P.deleteWords, endpoints: P.deleteEndpoints }));
ok(P.deleteInDiscovery > 0 && P.discoveryIssues.length === 0,
   'AND THE ONE PLACE THE NAME DOES APPEAR IS THE EVIDENCE, NOT A CALL: discovery_check() names '
   + 'videos.delete ' + P.deleteInDiscovery + ' times to READ ITS SCOPE ROW out of Google\'s own '
   + 'document - which is what proves update and delete are inseparable - and issues no request '
   + 'of its own while doing it',
   JSON.stringify({ inDiscovery: P.deleteInDiscovery, issues: P.discoveryIssues }));
ok(P.firstStatementGuards === true,
   'THE GUARD IS _http()\'s FIRST STATEMENT, by AST - not a check somewhere in the middle after '
   + 'a URL has been built',
   JSON.stringify(P.firstStatementGuards));
ok(JSON.stringify(P.socketOpeners) === JSON.stringify(['_http']),
   'and _http IS THE ONLY FUNCTION IN THE MODULE THAT OPENS A SOCKET, so there is one door and '
   + 'therefore one policy. A second door would pass every assertion above and still delete',
   JSON.stringify(P.socketOpeners));
ok(P.refused.length === 7 && P.slipped.length === 0,
   'THE GUARD FIRES on all seven spellings - ' + P.refused.join(', ') + ' - and still passes '
   + 'GET, post and " Put " (' + P.passed.join(', ') + ')',
   JSON.stringify({ refused: P.refused, slipped: P.slipped }));
ok(P.prohibitedIsException === true,
   'and it RAISES rather than returning something falsy, which is the part that cannot be '
   + 'ignored at a call site: `if not allowed` can be forgotten, an exception cannot',
   JSON.stringify(P.prohibitedIsException));
ok(P.doorRefuses === true,
   '_http("DELETE", <the real videos endpoint>) RAISES BEFORE A SOCKET IS OPENED. This is the '
   + 'clause that catches a guard that is present, correct and never called',
   JSON.stringify(P.doorRefuses));
ok(P.refusedCount >= 8,
   'and every refusal is counted where the house can read it: _SEEN.refusedDelete is '
   + P.refusedCount + ' after this section, so an attempt is an event and not a silence',
   JSON.stringify(P.refusedCount));
ok(!/videos|API_BASE|_http/.test(P.forgetSource) && /TOKEN_FILE|unlink|remove/.test(P.forgetSource),
   'AND forget() - the one destructively-named function in the module - touches the local token '
   + 'file and nothing on the network: every film ever uploaded stays exactly where it is',
   P.forgetSource.replace(/\s+/g, ' ').slice(0, 220));
ok(P.scope.deleteIssuable === false
   && JSON.stringify(P.scope.methodsAllowed) === JSON.stringify(['GET', 'POST', 'PUT']),
   'and the client REPORTS the prohibition as a fact about itself (deleteIssuable false) rather '
   + 'than as a claim about the grant',
   JSON.stringify({ deleteIssuable: P.scope.deleteIssuable, scopeWouldPermitDelete:
                    P.scope.scopeWouldPermitDelete }));

/* =====================================================================================
   2 · THE SCOPE DECISION, against Google's own document
   §40: "name the evidence either way". The evidence is a live fetch, because a scope table
   copied into a comment is a scope table that was true once.
   ===================================================================================== */
step('2 · the scope decision, re-proved against the live discovery document');

const D = crank(['--discovery'], 60000);
if (D.status === 0 && D.body && D.body.ok) {
  writeFileSync(join(OUT, 'discovery.json'), JSON.stringify(D.body, null, 1) + '\n');
  const rows = D.body.rows || {};
  const SET = (k) => (rows[k] ? rows[k].live.map((s) => s.split('/auth/')[1]).sort() : []);
  note('discovery revision ' + D.body.revision + ' · kept at ' + join(OUT, 'discovery.json'));
  for (const k of Object.keys(rows).sort()) note('  ' + k.padEnd(16) + SET(k).join(' · '));
  ok(SET('videos.insert').includes('youtube.upload')
     && SET('thumbnails.set').includes('youtube.upload')
     && SET('videos.list').includes('youtube.readonly'),
     'THE NARROW PAIR IS REAL: youtube.upload carries the insert AND the thumbnail, and '
     + 'youtube.readonly carries the verification - so §40\'s preference is satisfiable for '
     + 'everything except the flip',
     JSON.stringify({ insert: SET('videos.insert'), list: SET('videos.list') }));
  ok(!SET('videos.update').includes('youtube.upload'),
     'AND IT CANNOT FLIP PRIVACY: videos.update does not accept youtube.upload, so the privacy '
     + 'update is impossible under the narrow pair - which is the branch §40 named',
     JSON.stringify(SET('videos.update')));
  ok(JSON.stringify(SET('videos.update')) === JSON.stringify(SET('videos.delete'))
     && D.body.deleteNeedsSameAsUpdate === true,
     'THE DECISIVE ROW, AND IT IS WHY THE PROHIBITION LIVES IN THE SOURCE: videos.update and '
     + 'videos.delete accept the IDENTICAL set (' + SET('videos.delete').join(', ') + '). No '
     + 'grant exists that may make a film public and may not take it down',
     JSON.stringify({ update: SET('videos.update'), delete: SET('videos.delete') }));
  ok(D.body.uploadCanDelete === false,
     'and the narrow upload scope cannot delete, so nothing is lost by taking the wide one for '
     + 'the flip that could have been kept by not taking it',
     JSON.stringify(D.body.uploadCanDelete));
} else {
  note('the discovery document could not be read ('
       + ((D.body && D.body.why) || D.stderr || 'no reason given')
       + ') - §2 is the one section here that needs the network, and the evidence kept from the '
       + 'last successful run stands at ' + join(OUT, 'discovery.json'));
  ok(existsSync(join(OUT, 'discovery.json')),
     'the scope decision rests on a discovery document kept on disk, even on a flat network',
     'no discovery.json and no network: the scope decision is unproved this run');
}

/* =====================================================================================
   3 · THE PACKAGE - SEO by Galaxy, within YouTube's own arithmetic
   ===================================================================================== */
step('3 · the package: title, description, tags and thumbnail, against the real limits');

const K = python([
  'import json, os, sys',
  'sys.dont_write_bytecode = True',
  'import broadcast',
  'CFG = {"youtube_disclosure": ' + JSON.stringify(TEST_DISCLOSURE) + '}',
  'kit = broadcast.package(' + JSON.stringify(FILM) + ', cfg=CFG)',
  'out = dict(kit)',
  'out["limits"] = {"title": broadcast.TITLE_MAX, "desc": broadcast.DESC_MAX,'
  + ' "tagsTotal": broadcast.TAGS_TOTAL_MAX, "tag": broadcast.TAG_MAX,'
  + ' "tags": broadcast.TAGS_MAX, "hook": broadcast.HOOK_MAX}',
  'out["parts"] = kit["description"].split("\\n\\n") if kit["ok"] else []',
  'out["longestTag"] = max([len(t) for t in kit.get("tags") or [""]])',
  'out["thumbBytes"] = os.path.getsize(kit["thumbnail"]) if kit.get("thumbnail") else 0',
  // THE FILM ITSELF AND NOT ITS FOLDER: encode_check() probes one file with ffprobe, and handed
  // a directory it reports "Permission denied" - which is a true sentence about the wrong
  // question. upload() passes the mp4; so does this.
  'out["encode"] = broadcast.encode_check(os.path.join(' + JSON.stringify(FILM) + ', "final.mp4"))',
  // THE TAGS ARE CASE-INSENSITIVELY UNIQUE. Measured because the note slugs and the narration
  // spell the same word two ways, and a card shipping React and react wastes the 500 characters
  // on a duplicate.
  'out["dupes"] = len(kit.get("tags") or []) - len({t.lower() for t in kit.get("tags") or []})',
  'print(json.dumps(out))',
]);

ok(K.ok === true, 'the premiere\'s film packages: ' + FILM, K.why);
note('title       : ' + JSON.stringify(K.title) + '  (' + (K.title || '').length + '/'
     + K.limits.title + ')');
note('tags        : ' + (K.tags || []).join(', ') + '  (' + K.tagChars + '/'
     + K.limits.tagsTotal + ' chars, ' + (K.tags || []).length + ' of ' + K.limits.tags + ')');
note('thumbnail   : ' + K.thumbnail + '  (' + K.thumbBytes + ' bytes)');
note('description : ' + (K.description || '').length + '/' + K.limits.desc + ' chars in '
     + (K.parts || []).length + ' parts');

ok((K.title || '').length > 0 && (K.title || '').length <= K.limits.title,
   'THE TITLE FITS: ' + (K.title || '').length + ' of ' + K.limits.title + ' characters',
   JSON.stringify(K.title));
ok(/useeffect/i.test(K.title || '') && /react/i.test(K.title || ''),
   'and it CARRIES THE TOPIC KEYWORD - "useEffect" and "React", off the film\'s own script.md '
   + 'rather than off a template',
   JSON.stringify({ title: K.title, topic: K.topic }));
ok(!/\b(\d+)\s*(second|minute)/i.test(K.title || ''),
   'and it asserts NO NUMBER NOTHING MEASURED. The first draft read "Explained in 60 Seconds" '
   + 'over a 50.65-second film: a title is the most-read line this house publishes',
   JSON.stringify(K.title));
ok(K.tagChars <= K.limits.tagsTotal && (K.tags || []).length <= K.limits.tags
   && K.longestTag <= K.limits.tag,
   'THE TAGS FIT YouTube\'s OWN ARITHMETIC: ' + K.tagChars + '/' + K.limits.tagsTotal
   + ' characters, ' + (K.tags || []).length + ' tags, longest ' + K.longestTag + '/'
   + K.limits.tag,
   JSON.stringify({ chars: K.tagChars, n: (K.tags || []).length, longest: K.longestTag }));
ok(K.dupes === 0,
   'and no tag is a case-variant of another - the note slugs say "React" and the narration says '
   + '"react", and shipping both would spend the 500 characters on a duplicate',
   JSON.stringify(K.tags));
ok(!(K.tags || []).some((t) => /[.,]$/.test(t)),
   'and no tag carries its punctuation: a word-boundary that ended in [.] shipped '
   + '"infrastructure." as a search term',
   JSON.stringify(K.tags));
ok((K.description || '').length <= K.limits.desc && (K.parts || []).length === 3,
   'THE DESCRIPTION IS EXACTLY THREE PARTS - hook, cited notes, disclosure - and fits in '
   + (K.description || '').length + '/' + K.limits.desc + ' characters',
   JSON.stringify(K.parts));
ok((K.thumbnail || '').endsWith('poster.jpg') && K.thumbBytes > 2000,
   'THE THUMBNAIL IS THE DIRECTOR\'S OWN POSTER JPG, ' + K.thumbBytes + ' bytes - not a frame '
   + 'this harness chose and not a default',
   JSON.stringify({ thumb: K.thumbnail, bytes: K.thumbBytes }));
/* NOT `ok === true` ALONE. encode_check() returns ok with the streams it found, and the failure
   this clause exists to catch is a film that encoded "successfully" with no audio track - which
   plays as 50 seconds of silence to an audience and cannot be taken down afterwards. So the
   codecs are named. */
ok(K.encode && K.encode.ok === true && K.encode.vcodec === 'h264' && K.encode.acodec === 'aac'
   && K.encode.durationS > 1,
   'and the film is PROBED BEFORE A BYTE GOES UP: ' + K.encode.vcodec + ' + ' + K.encode.acodec
   + ', ' + K.encode.durationS + 's, ' + K.encode.bytes + ' bytes - a silent or streamless film '
   + 'is a mistake that cannot be deleted afterwards, so the audio track is named rather than '
   + 'assumed from a true `ok`',
   JSON.stringify(K.encode));

/* =====================================================================================
   4 · THE DISCLOSURE - honesty by law, and the refusal that stands without it
   ===================================================================================== */
step('4 · the disclosure: cited by id, approved by the boss, and refused when it is absent');

const DISC = python([
  'import json, sys',
  'sys.dont_write_bytecode = True',
  'import broadcast',
  'out = {}',
  // (a) THE STATE THIS MACHINE IS ACTUALLY IN: no approved line in config.json.
  'out["live"] = broadcast.package(' + JSON.stringify(FILM) + ')',
  'out["liveCard"] = broadcast.card(' + JSON.stringify(FILM) + ')',
  // (b) and with one approved, in memory only - this harness never writes config.json.
  'CFG = {"youtube_disclosure": ' + JSON.stringify(TEST_DISCLOSURE) + '}',
  'kit = broadcast.package(' + JSON.stringify(FILM) + ', cfg=CFG)',
  'out["with"] = {"ok": kit["ok"], "disclosure": kit["disclosure"],'
  + ' "cited": kit["citedLine"], "ids": kit["cited"], "hook": kit["hook"]}',
  // (c) AND A BLANK ONE IS NOT A LINE. A config key present and empty must refuse exactly as an
  // absent one does, or the refusal is a test of a key rather than of a disclosure.
  'out["blank"] = broadcast.package(' + JSON.stringify(FILM) + ', cfg={"youtube_disclosure": "   "})',
  'out["disclosureSource"] = broadcast.disclosure.__doc__ or ""',
  'print(json.dumps(out))',
]);

ok(DISC.live.ok === false && /disclosure/i.test(DISC.live.why || ''),
   'WITHOUT AN APPROVED LINE THE PACKAGE REFUSES TO EXIST: "' + (DISC.live.why || '')
   + '" - it does not invent a disclosure, because a disclosure is a legal representation in '
   + 'the boss\'s name',
   JSON.stringify(DISC.live));
ok(DISC.blank.ok === false,
   'and a key that is present and BLANK refuses identically - the test is for a line, not for a '
   + 'key being set',
   JSON.stringify(DISC.blank.why));
ok(DISC.liveCard.ok === false && /disclosure/i.test(DISC.liveCard.why || ''),
   'so no Chain Card can be raised for a film whose description would be missing it either',
   JSON.stringify(DISC.liveCard));
ok(DISC.with.ok === true && DISC.with.disclosure === TEST_DISCLOSURE,
   'WITH ONE APPROVED, the description carries it VERBATIM - not paraphrased, not shortened: '
   + JSON.stringify(DISC.with.disclosure),
   JSON.stringify(DISC.with));
ok(/\d+ cited note/i.test(DISC.with.cited || '') || (DISC.with.ids || []).length > 0,
   'AND THE CITED-NOTES LINE NAMES THE SOURCES - ' + (DISC.with.ids || []).length
   + ' of them - which is the channel\'s shield against the reused-content policy: "'
   + (DISC.with.cited || '').slice(0, 110) + '"',
   JSON.stringify(DISC.with.cited));
ok(!(DISC.with.cited || '').includes('\\') && !/\.md\b/.test(DISC.with.cited || ''),
   'and it cites IDS AND NOT FILENAMES, so a public description cannot leak the shape of the '
   + 'boss\'s own folders',
   JSON.stringify(DISC.with.cited));

/* =====================================================================================
   5 · UNLISTED FIRST, by construction rather than by discipline
   ===================================================================================== */
step('5 · unlisted first: no argument, no default, no caller that could ask otherwise');

const U = python([
  'import inspect, json, sys',
  'sys.dont_write_bytecode = True',
  'import broadcast',
  'out = {}',
  'out["insertParams"] = list(inspect.signature(broadcast.insert).parameters)',
  'out["uploadParams"] = list(inspect.signature(broadcast.upload).parameters)',
  'out["first"] = broadcast.PRIVACY_FIRST',
  'out["privacies"] = list(broadcast.PRIVACIES)',
  'src = inspect.getsource(broadcast._open_session)',
  'out["writesFirst"] = "PRIVACY_FIRST" in src',
  'out["writesPublic"] = "PRIVACY_PUBLIC" in src or \'"public"\' in src',
  // THE FLIP REFUSES A WORD THAT IS NOT ONE OF THE THREE, before any network. A typo in a
  // privacy status is not a 400 from Google - it is a film left as it was, reported as changed.
  'out["badWord"] = broadcast.set_privacy("aaaaaaaaaaa", "publik")',
  // AND IT REFUSES WITHOUT THE SCOPE, by name, rather than letting a 403 surprise a premiere.
  'out["noScope"] = broadcast.set_privacy("aaaaaaaaaaa", "public")',
  'out["canPublish"] = broadcast.scope_report()["canPublish"]',
  'out["steps"] = list(broadcast.STEPS) + list(broadcast.PUBLISH_STEPS)',
  'print(json.dumps(out))',
]);

ok(!U.insertParams.some((p) => /privac/i.test(p)),
   'insert(' + U.insertParams.join(', ') + ') HAS NO PRIVACY ARGUMENT AT ALL. "Unlisted first" '
   + 'is therefore not a default a caller can override - there is nothing to pass',
   JSON.stringify(U.insertParams));
ok(U.first === 'unlisted' && U.writesFirst === true && U.writesPublic === false,
   'and the session body writes PRIVACY_FIRST (' + U.first + ') and never mentions public, so '
   + 'the first state a film can have is the one nobody can find',
   JSON.stringify({ first: U.first, writesFirst: U.writesFirst, public: U.writesPublic }));
ok(U.badWord.ok === false && /not a privacy status/i.test(U.badWord.why || ''),
   'THE FLIP REFUSES A MISSPELLED STATUS before the network: "' + U.badWord.why + '". A typo '
   + 'would otherwise be a film left as it was and reported as changed',
   JSON.stringify(U.badWord));
ok(U.noScope.ok === false,
   'and without the wide scope it refuses BY NAME rather than letting a 403 land halfway through '
   + 'a premiere: "' + (U.noScope.why || '').slice(0, 120) + '"',
   JSON.stringify({ noScope: U.noScope, canPublish: U.canPublish }));
ok(JSON.stringify(U.steps) === JSON.stringify(['encode-check', 'meta', 'thumb', 'verify',
                                               'publish']),
   'and the bus has §40\'s own step names, in order: ' + U.steps.join(' · '),
   JSON.stringify(U.steps));

/* =====================================================================================
   6 · THE DOORMAN - and §40's "guest voice => stays unlisted", both halves
   ===================================================================================== */
step('6 · the two intents, the nine refusals, and a guest who cannot publish');

/* THE INTENT TABLE. The left column is what is said; the right is which route must take it, or
   "-" for the funnel declining and leaving it to the ordinary brain. The nine dashes are the
   whole point of the section: an unanchored pattern would hear "do not publish it", "unpublish
   it" and "delete the video" as orders. */
const HEARD = [
  ['put it on youtube', 'UPLOAD'],
  ['upload it', 'UPLOAD'],
  ['post the video to youtube', 'UPLOAD'],
  ['put that up on the channel', 'UPLOAD'],
  ['publish it', 'PUBLISH'],
  ['make it public', 'PUBLISH'],
  ['go public', 'PUBLISH'],
  ['release it now', 'PUBLISH'],
  ['what did you upload', '-'],
  ['is it on youtube yet', '-'],
  ['do not publish it', '-'],
  ['unpublish it', '-'],
  ['delete the video', '-'],
  ['take it down', '-'],
  ['publish a book', '-'],
  ['how do i upload a video', '-'],
  ['make a video about react', '-'],
];

const G = python([
  'import json, sys',
  'sys.dont_write_bytecode = True',
  'import server',
  'out = {"heard": []}',
  'CASES = ' + JSON.stringify(HEARD.map((r) => r[0])),
  'for text in CASES:',
  '    if server.broadcast_asked(text):',
  '        out["heard"].append("UPLOAD")',
  '    elif server.publish_asked(text):',
  '        out["heard"].append("PUBLISH")',
  '    else:',
  '        out["heard"].append("-")',
  // -- THE DOORMAN'S VERDICT, for four seals. A spoken sentence sealed anything but BOSS is
  // refused; a TYPED one is the keyboard of this machine, which this house has always treated
  // as the boss.
  'out["gate"] = {}',
  'for label, spoken, seal in (("boss", True, "BOSS"), ("guest", True, "GUEST"),',
  '                            ("unverified", True, "UNVERIFIED"), ("typed", False, "")):',
  '    allowed, why = server.broadcast_allowed(spoken, seal)',
  '    out["gate"][label] = {"allowed": bool(allowed), "why": why}',
  // -- AND THE WHOLE ROUTE, through the real funnel, for a guest asking for public. What is
  // being read is the payload a harness reads instead of parsing a sentence back.
  'klass, said = server.protected_answer("publish it", spoken=True, seal="GUEST")',
  'out["guestPublish"] = {"class": klass, "broadcast": said.get("broadcast"),',
  '                       "publish": said.get("broadcastPublish"),',
  '                       "pending": said.get("broadcastPending"),',
  '                       "refused": said.get("refused"),',
  '                       "answer": (said.get("answer") or "")[:140],',
  '                       "lookups": said.get("lookups"), "nodes": len(said.get("nodes") or [])}',
  'klass2, said2 = server.protected_answer("put it on youtube", spoken=True, seal="GUEST")',
  'out["guestUpload"] = {"class": klass2, "started": said2.get("broadcastStarted"),',
  '                      "refused": said2.get("refused"),',
  '                      "answer": (said2.get("answer") or "")[:140]}',
  // -- THE SECOND HALF OF "GUEST STAYS UNLISTED": a guest's yes, with no window open.
  'import hands',
  'hands.clear_pending("broadcaster_proof")',
  'S = "broadcaster-proof-guest"',
  'out["noWindow"] = list(server.handshake_honour(S, "yes", pending_id="", now=1.0))[:2]',
  'out["guestOpens"] = server.handshake_open(S, "GUEST", gate="broadcast", pid="p1", now=2.0)',
  'out["bossOpens"] = server.handshake_open(S, "BOSS", gate="broadcast", pid="p2", now=3.0)',
  'out["unpaid"] = list(server.UNPAID_CLASSES)',
  'out["pendingAfter"] = hands.pending_public()',
  'print(json.dumps(out))',
]);

const wrong = HEARD.filter((row, i) => G.heard[i] !== row[1]);
for (let i = 0; i < HEARD.length; i++) {
  note('  ' + (G.heard[i] === HEARD[i][1] ? ' ' : '!') + ' ' + HEARD[i][0].padEnd(30)
       + G.heard[i] + (G.heard[i] === HEARD[i][1] ? '' : '   expected ' + HEARD[i][1]));
}
ok(wrong.length === 0,
   'THE TWO INTENTS ARE HEARD AND THE NINE LOOKALIKES ARE NOT: 8 routed, 9 declined, including '
   + '"do not publish it", "unpublish it", "delete the video" and "take it down"',
   JSON.stringify(wrong));
ok(G.gate.boss.allowed === true && G.gate.guest.allowed === false
   && G.gate.unverified.allowed === false && G.gate.typed.allowed === true,
   'THE DOOR IS THE BOSS\'S SEAL OR THIS MACHINE\'S KEYBOARD: boss yes, guest no, unverified '
   + 'no, typed yes',
   JSON.stringify(G.gate));
ok(G.guestPublish.broadcast === true && G.guestPublish.publish === true
   && G.guestPublish.pending === '' && G.guestPublish.refused === 'not-the-boss',
   'A GUEST ASKING FOR PUBLIC IS REFUSED BEFORE A CARD EXISTS - broadcastPending is empty, so '
   + 'there is no proposal standing for any later "yes" to confirm. This is the strong half of '
   + '§40\'s "guest voice => stays unlisted"',
   JSON.stringify(G.guestPublish));
ok(G.pendingAfter === null,
   'and the slot is still empty afterwards, measured rather than inferred from the payload',
   JSON.stringify(G.pendingAfter));
ok(G.guestUpload.started === false && G.guestUpload.refused === 'not-the-boss',
   'and a guest cannot even put a film up UNLISTED: "'
   + (G.guestUpload.answer || '').slice(0, 90) + '"',
   JSON.stringify(G.guestUpload));
/* `None` AND NOT `False` is the first element: handshake_honour() returns the WORD IT HONOURED
   or nothing at all, and "no open window" is nothing at all rather than a refusal. A harness
   that asserted False here would have been asserting that a refusal happened, which would read
   as a decision being taken about a film when in truth no question was outstanding. */
ok(G.noWindow[0] === null && G.noWindow[1] === 'no open window' && G.guestOpens === false
   && G.bossOpens === true,
   'THE WEAK HALF HOLDS TOO: a "yes" with no window inherits nothing, and a GUEST utterance '
   + 'cannot open one - only a BOSS seal can. So a guest\'s word at a card the boss raised '
   + 'leaves the film unlisted',
   JSON.stringify({ noWindow: G.noWindow, guest: G.guestOpens, boss: G.bossOpens }));
ok(G.guestPublish.lookups === 0 && G.guestPublish.nodes === 0,
   'and the whole route costs NOTHING to answer: 0 lookups, 0 nodes - which is why "broadcast" '
   + 'is in UNPAID_CLASSES (' + G.unpaid.join(', ') + ')',
   JSON.stringify({ lookups: G.guestPublish.lookups, nodes: G.guestPublish.nodes }));
ok(G.unpaid.includes('broadcast')
   && G.unpaid.slice(0, 4).join() === 'confirmation,meta,identity,directive',
   'and it is APPENDED after the mandate\'s four rather than mixed in among them',
   JSON.stringify(G.unpaid));

/* =====================================================================================
   7 · THE LEDGER AND THE PUBLISH GUARD
   ===================================================================================== */
step('7 · the ledger keys, and the hand that will only publish what this house uploaded');

const L = python([
  'import json, subprocess, sys',
  'sys.dont_write_bytecode = True',
  'import jobs, broadcast',
  'out = {"rowKeys": list(jobs.ROW_KEYS), "resultKeys": list(jobs.RESULT_KEYS)}',
  'out["uploaded"] = len(broadcast.uploaded())',
  'out["unknown"] = broadcast.uploaded("Zq1_inventX")',
  'from tools import _proc',
  'done = _proc.run([sys.executable, "tools/publish_video.py"],',
  '                 input=json.dumps({"video": "Zq1_inventX", "title": "x"}).encode("utf-8"),',
  '                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)',
  'out["handStatus"] = done.returncode',
  'out["handSaid"] = done.stdout.decode("ascii", "replace").strip()',
  'short = _proc.run([sys.executable, "tools/publish_video.py"],',
  '                  input=json.dumps({"video": "short"}).encode("utf-8"),',
  '                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)',
  'out["shapeSaid"] = short.stdout.decode("ascii", "replace").strip()',
  'print(json.dumps(out))',
]);

for (const k of ['videoId', 'url', 'privacy']) {
  ok(L.rowKeys.includes(k) && L.resultKeys.includes(k),
     'the ledger row and the job result both carry `' + k + '`, so the page and the ledger '
     + 'cannot disagree about what went up',
     JSON.stringify({ row: L.rowKeys, result: L.resultKeys }));
}
ok(L.rowKeys.includes('privacyFrom') && L.rowKeys.includes('privacyTo'),
   'and the row carries privacyFrom/privacyTo - the wide `youtube` scope was taken in exchange '
   + 'for writing every privacy change down, so it is written down',
   JSON.stringify(L.rowKeys));
ok(JSON.stringify(L.unknown) === '{}' ,
   'an id this house never uploaded is not in the ledger, which is what the guard reads',
   JSON.stringify(L.unknown));
ok(L.handStatus === 1 && /no record/i.test(L.handSaid),
   'THE PUBLISH HAND REFUSES A FILM IT DID NOT UPLOAD: "' + L.handSaid + '". A video id is '
   + 'eleven characters a language model can produce from nothing, and an invented one is a '
   + 'request to make a STRANGER\'S video public',
   JSON.stringify({ status: L.handStatus, said: L.handSaid }));
ok(/not a video id/i.test(L.shapeSaid) && !/short/.test(L.shapeSaid),
   'and a malformed id is refused without being echoed back - model text does not reach a log '
   + 'or a spoken line: "' + L.shapeSaid + '"',
   JSON.stringify(L.shapeSaid));

/* =====================================================================================
   8 · THE POSTER ROUTE - the one place this server sends bytes from outside viewer/
   ===================================================================================== */
step('8 · the poster route: an id, never a path');

const health = await http('/health');
ok(health.status === 200, 'the server is answering on 4700', JSON.stringify(health.status));

for (const [probe, want, why] of [
  ['/poster', 400, 'no id at all'],
  ['/poster?video=', 400, 'an empty id'],
  ['/poster?video=../../secrets/youtube_token.json', 400, 'a traversal'],
  ['/poster?video=output/videos/x/poster.jpg', 400, 'a path, which is what the law forbids'],
  ['/poster?video=aaaaaaaaaa', 400, 'ten characters - the wrong shape'],
  ['/poster?video=aaaaaaaaaaa', 404, 'eleven well-formed characters of no film of ours'],
]) {
  const r = await http(probe);
  ok(r.status === want, 'GET ' + probe + ' -> ' + r.status + '  (' + why + ')',
     JSON.stringify({ got: r.status, want }));
}

/* =====================================================================================
   9 · THE CHAIN CARD, ON GLASS
   §40: "the Chain Card shows title, description, tags, thumbnail plate and the unlisted URL".
   Raised through POST /tools, which is the same propose() the spoken route calls, and
   photographed - because a card nobody looked at is a schema and not a card.
   ===================================================================================== */
step('9 · the Chain Card: six rows, a thumbnail plate, and the unlisted URL');

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
      const bomb = setTimeout(() => { this.w.delete(id); rej(new Error(method + ' timed out')); },
                              20000);
      this.w.set(id, (m) => { clearTimeout(bomb); res(m); });
      this.ws.send(JSON.stringify({ id, method, params: params || {} })); }); }
  async evaluate(expression) {
    const r = await this.send('Runtime.evaluate',
      { expression, returnByValue: true, awaitPromise: true });
    if (r.result && r.result.exceptionDetails) {
      const d = r.result.exceptionDetails;
      throw new Error('page threw: ' + ((d.exception && (d.exception.description ||
        d.exception.value)) || d.text) + '  <- ' + expression.slice(0, 160));
    }
    return r.result && r.result.result ? r.result.result.value : undefined;
  }
  /* THE AWAIT IS INSIDE THE STRINGIFY AND NOT AROUND IT. `JSON.stringify(somePromise)` is the
     string "{}" - a Promise has no own enumerable properties - so a bare stringify of an async
     IIFE returns an empty object with a 200-shaped silence, and every assertion written against
     it fails for a reason that has nothing to do with the thing being measured. awaitPromise on
     the evaluate call cannot help: by then the promise is already inside a finished string. */
  async json(e) {
    const raw = await this.evaluate('(async () => JSON.stringify(await (' + e + ')))()');
    return JSON.parse(raw || 'null');
  }
  async shot(file, clip) {
    const r = await this.send('Page.captureScreenshot', clip
      ? { format: 'png', clip: { x: clip.x, y: clip.y, width: clip.w, height: clip.h, scale: 1 } }
      : { format: 'png' });
    const data = r.result && r.result.data;
    if (!data) throw new Error('no screenshot came back');
    if (file) writeFileSync(file, Buffer.from(data, 'base64'));
    return data;
  }
  close() { try { this.ws.close(); } catch { } }
}
const cdp = async (p) => {
  const r = await fetch(CDP + p);
  const t = await r.text();
  try { return JSON.parse(t); } catch { return t; }
};
async function waitFor(page, expr, ms = 8000) {
  const t0 = Date.now();
  for (let i = 0; i < Math.ceil(ms / 150); i++) {
    try { if (await page.evaluate(expr)) return (Date.now() - t0) || 1; } catch { }
    await sleep(150);
  }
  return null;
}
/* THE WINDOW MUST STAY AWAKE. This desktop minimises a harness Chrome a couple of seconds in,
   and a minimised window paints nothing - a plate of it is a plate of the last frame before it
   went away. BOUNDS ONLY: Page.bringToFront steals the employer's foreground and does nothing
   for a minimised window anyway. */
function keepFront(page, every = 1500) {
  let puts = 0;
  const t = setInterval(async () => {
    try {
      const { result } = await page.send('Browser.getWindowForTarget');
      if (result && result.bounds && result.bounds.windowState === 'minimized') {
        await page.send('Browser.setWindowBounds',
          { windowId: result.windowId, bounds: { windowState: 'normal' } });
        puts++;
      }
    } catch (e) { /* the run is ending, or this build has no Browser domain */ }
  }, every);
  if (t.unref) t.unref();
  return { stop: () => clearInterval(t), count: () => puts };
}
const profiles = []; const procs = [];
/* THE CLEANUP THAT RUNS EVEN WHEN THIS FILE THROWS. The tidy-up at the bottom of the script is
   unreachable from a top-level exception, and three unreachable tidy-ups are what left a Chrome
   holding port 9242 and poisoned every run after. An exit hook is synchronous, so spawnSync is
   exactly the right tool in it, and it is registered before the first launch rather than after. */
process.on('exit', () => {
  for (const p of profiles) shutChrome(p);
  shutPort(PORT);
});
/* PROFILE-SCOPED, never by window title: the one Chrome on this machine that must survive every
   harness is the employer's own on 9222. */
function shutChrome(profile) {
  spawnSync('powershell.exe', ['-NoProfile', '-Command',
    'Get-CimInstance Win32_Process | Where-Object { $_.Name -eq \'chrome.exe\' -and ' +
    '$_.CommandLine -match \'' + basename(profile) + '\' } | ' +
    'ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }'],
    { stdio: 'ignore' });
}
/* AND THE SAME BROOM, BY PORT, BEFORE THE LAUNCH - because the profile of a browser this run
   did not start is a profile this run does not know the name of.
   THE BUG THIS EXISTS FOR, which cost four assertions and an hour of blaming a stylesheet.
   Three earlier runs of this file threw - a wrong attribute name, a wrong function name - and a
   throw at top level skips the cleanup at the bottom, so their Chromes stayed up holding 9242.
   Every run after that launched a new Chrome which FAILED TO BIND THE PORT AND EXITED QUIETLY,
   and /json/list then answered from the SURVIVOR: a browser carrying the index.html of an hour
   ago. A CSS fix that was correct, served and verified by curl read as no fix at all, four
   viewport assertions went red as a block, and the page said capped:true the whole time so the
   evidence all looked like a layout problem. A stale debugger port does not fail - it answers
   wrongly, which is worse.
   PORT-SCOPED AND NOT TITLE-SCOPED, and 9242 is nobody else's: the employer's own browser is on
   9222 and the number is matched exactly. */
function shutPort(port) {
  spawnSync('powershell.exe', ['-NoProfile', '-Command',
    'Get-CimInstance Win32_Process | Where-Object { $_.Name -eq \'chrome.exe\' -and ' +
    '$_.CommandLine -match \'remote-debugging-port=' + port + '\\b\' } | ' +
    'ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }'],
    { stdio: 'ignore' });
}

/* THE CARD'S SIX PARAMETERS, composed by the SERVER's own package() through the hand crank, so
   the card photographed below carries the real title, the real tags and the real poster path
   rather than six strings this file typed. The one thing that is this harness's and not the
   house's is the disclosure inside the description - see TEST_DISCLOSURE. */
const CARD = python([
  'import json, sys',
  'sys.dont_write_bytecode = True',
  'import broadcast',
  'CFG = {"youtube_disclosure": ' + JSON.stringify(TEST_DISCLOSURE) + '}',
  'kit = broadcast.package(' + JSON.stringify(FILM) + ', cfg=CFG)',
  // A FICTIONAL BUT WELL-FORMED ID, because no film has been uploaded: the premiere is blocked
  // on the boss's consent. It is eleven characters of URL-safe base64, which is the shape the
  // route, the hand and the page all test for, and it is NOT written to the ledger - §10 says
  // so out loud. The plate it resolves through is therefore the PENDING SLOT's, which is the
  // second of /poster's two lookups and the one that needs proving.
  'VID = "PRooF40card"',
  'print(json.dumps({"video": VID, "title": kit["title"],',
  '                  "url": broadcast.watch_url(VID),',
  '                  "tags": ", ".join(kit["tags"]),',
  '                  "thumbnail": kit["thumbnail"],',
  '                  "description": kit["description"]}))',
]);

const exe = CHROMES.find((p) => existsSync(p));
let page = null, keeper = null, profile = null;
if (!exe) {
  note('no chrome.exe on this machine - §9 cannot photograph a card');
  ok(false, 'the Chain Card is photographed with its thumbnail plate', 'no chrome.exe');
} else {
  shutPort(PORT);                 // see shutPort: a survivor on this port answers with old HTML
  await sleep(400);
  profile = mkdtempSync(join(tmpdir(), 'broadcaster-'));
  profiles.push(profile);
  procs.push(spawn(exe, ['--remote-debugging-port=' + PORT, '--user-data-dir=' + profile,
    '--no-first-run', '--no-default-browser-check', '--window-size=' + W + ',' + H,
    '--disable-features=CalculateNativeWinOcclusion',
    '--disable-backgrounding-occluded-windows', '--disable-renderer-backgrounding',
    '--new-window', GALAXY], { detached: true, stdio: 'ignore' }));
  for (let i = 0; i < 80; i++) { try { await cdp('/json/version'); break; } catch { await sleep(250); } }
  let target = null;
  for (let i = 0; i < 40; i++) {
    const l = await cdp('/json/list');
    target = (Array.isArray(l) ? l : []).filter((t) => t.type === 'page')
      .find((t) => t.url.includes('127.0.0.1:4700'));
    if (target) break; await sleep(300);
  }
  if (!target) throw new Error('no viewer page');
  page = new Page(target.webSocketDebuggerUrl);
  await page.open();
  await page.send('Runtime.enable');
  await page.send('Page.enable');
  try { await page.send('Page.bringToFront'); } catch (e) { note('bringToFront: ' + e.message); }
  keeper = keepFront(page);
  ok(!!await waitFor(page, '!!(window.__galaxy && document.getElementById("ask-plate"))', 30000),
     'the viewer is up and carries §40\'s plate element',
     'the page never exposed #ask-plate');

  /* AND IT IS THIS AFTERNOON'S PAGE. The tab is asked to prove its own freshness against the
     file on disk before one pixel of it is measured, because the alternative is what happened:
     a Chrome left over from a crashed run answering /json/list with the markup of an hour ago,
     and four viewport assertions going red at a stylesheet that was already correct. A harness
     that cannot tell a stale page from a broken one reports the wrong bug with total
     confidence. The string is §40's own two-stage plate rule, which no earlier page has. */
  const fresh = await page.json('({served: document.documentElement.outerHTML'
    + '.indexOf("flex:0 0 auto;width:96px") >= 0, url: location.href,'
    + ' bytes: document.documentElement.outerHTML.length})');
  ok(fresh.served === true,
     'and the markup it is serving is the one on disk right now - ' + fresh.bytes
     + ' characters from ' + fresh.url + ' carrying §40\'s own plate rule',
     'THIS IS A STALE BROWSER, not a layout fault: port ' + PORT + ' was answered by a Chrome '
     + 'that loaded the page before the last edit. Nothing measured below it means anything. '
     + JSON.stringify(fresh));

  /* THE PROPOSAL, THROUGH THE SAME DOOR THE SPOKEN ROUTE USES. propose() validates the
     parameters, fills the one slot and composes the line from the registry - so the card below
     is the card a real "put it on youtube" would raise, minus the upload. */
  const proposed = await page.json(
    '(async () => { const r = await fetch("/tools", {method:"POST",'
    + ' headers:{"Content-Type":"application/json"},'
    + ' body: JSON.stringify({cmd:"propose", tool:"publish_video", door:"voice",'
    + ' params:' + JSON.stringify(CARD) + '})});'
    + ' const d = await r.json(); window.__p40 = d.pending;'
    + ' return {status: r.status, answer: d.answer, id: d.pending && d.pending.id,'
    + ' tool: d.pending && d.pending.tool, fields: (d.pending && d.pending.fields || [])'
    + '   .map(f => f.name), params: d.pending && d.pending.params}; })()');
  ok(proposed.status === 200 && proposed.tool === 'publish_video' && !!proposed.id,
     'the proposal is raised through the same propose() the spoken route calls, and the server '
     + 'minted a real slot for it',
     JSON.stringify(proposed));
  ok(JSON.stringify(proposed.fields) === JSON.stringify(['video', 'title', 'url', 'tags',
                                                         'thumbnail', 'description']),
     'and the SLOT ITSELF declares §40\'s six fields - the card is not a second description of '
     + 'the parameters, it IS them',
     JSON.stringify(proposed.fields));
  note('the line the boss would hear: "' + (proposed.answer || '').slice(0, 150) + '"');
  ok(/unlisted/i.test(proposed.answer || '') && /public\?/.test(proposed.answer || ''),
     'AND THE LINE SAYS THE FILM IS UNLISTED AND ASKS FOR PUBLIC - the two facts the word "yes" '
     + 'is being spent on, in the sentence itself',
     JSON.stringify(proposed.answer));

  /* AND NOW IT IS DRAWN, through production's own showProposal() - the same function the
     server's reply calls at viewer/index.html:11826, reached by the paint door layout_proof
     uses. The tab is not polled into showing a card because nothing in this house polls for
     one: a proposal is painted by the reply that raised it, and this harness raised its own
     over /tools rather than by speaking to a language model.
     WHAT IS REAL AND WHAT IS NOT, said plainly: the ROWS, the amber card, the countdown and
     the plate below are production's, and the SLOT is the server's own, minted above and
     readable at /poster. What is not real is a boss pressing Yes - the paint door carries no
     consent and /execute refuses an id this tab did not get from the server. */
  /* THE SENTENCE FIRST, THEN THE CARD, WHICH IS PRODUCTION'S OWN ORDER - respond() calls
     renderAnswer() and only then showProposal(). It is not decoration: the card is laid out
     INSIDE the answer panel, so painted into a tab that has never answered anything it is a
     real card with a real plate in a zero-by-zero box, and the screenshot of it is 255 bytes of
     nothing. The first run of this section photographed exactly that and every assertion about
     the rows still passed, because textContent reads a hidden element perfectly well. */
  await page.evaluate('window.__galaxy.say("make it public",'
    + JSON.stringify(proposed.answer || '') + ', false, null)');
  const painted = await page.json('window.__galaxy.hands.paint(window.__p40)');
  const shown = await waitFor(page,
    'document.getElementById("a-ask").classList.contains("show")', 12000);
  ok(painted === true && !!shown,
     'the card is on the glass in ' + shown + 'ms, drawn by the same showProposal() the '
     + 'server\'s own reply calls',
     JSON.stringify({ painted, shown }));

  const plate = await waitFor(page,
    'document.getElementById("ask-plate").classList.contains("show")', 8000);
  const card = await page.json('(() => {'
    + ' const ask = document.getElementById("a-ask");'
    + ' const img = document.getElementById("ask-plate");'
    + ' const rows = [...document.querySelectorAll("#ask-rows b")].map(b => b.textContent);'
    + ' const vals = [...document.querySelectorAll("#ask-rows span")].map(s => s.textContent);'
    + ' const box = ask.getBoundingClientRect();'
    + ' const ib = img.getBoundingClientRect();'
    + ' return {rows, vals, shown: ask.classList.contains("show"),'
    + '  plate: {shown: img.classList.contains("show"), src: img.getAttribute("src") || "",'
    + '    w: img.naturalWidth, h: img.naturalHeight, boxW: Math.round(ib.width),'
    + '    boxH: Math.round(ib.height)},'
    + '  box: {x: Math.round(box.x), y: Math.round(box.y), w: Math.round(box.width),'
    + '    h: Math.round(box.height)},'
    // THE ROWS' OWN RECTANGLE AND COMPUTED DISPLAY, for the same reason the plate's box is
    // read: six names came back out of textContent on the first run of this section and not
    // one of them was on screen.
    + '  rowsBox: (() => { const r = document.getElementById("ask-rows");'
    + '    const b = r.getBoundingClientRect(); const a = document.getElementById("answer");'
    + '    return {w: Math.round(b.width), h: Math.round(b.height), scrollH: r.scrollHeight,'
    + '      display: getComputedStyle(r).display, kids: r.children.length,'
    + '      capped: a.classList.contains("capped"), answerH: Math.round('
    + '        a.getBoundingClientRect().height), innerH: window.innerHeight,'
    + '      lblH: Math.round(document.getElementById("ask-lbl").getBoundingClientRect().height),'
    + '      yesBottom: Math.round('
    + '        document.getElementById("ask-yes").getBoundingClientRect().bottom)}; })(),'
    + '  buttons: [...document.querySelectorAll("#a-ask button")].map(b => b.textContent)}; })()');

  ok(JSON.stringify(card.rows) === JSON.stringify(['video', 'title', 'url', 'tags', 'thumbnail',
                                                   'description']),
     'THE CARD SHOWS ALL SIX ROWS, in the registry\'s order: ' + card.rows.join(' · '),
     JSON.stringify(card.rows));
ok(card.rowsBox.h > 0 && card.rowsBox.w > 0 && card.rowsBox.display !== 'none',
   'and they are LAID OUT, not merely present: ' + card.rowsBox.w + '×' + card.rowsBox.h
   + ' as display:' + card.rowsBox.display + '. textContent answers just as well from a '
   + 'display:none element, so the six names above are not on their own evidence that the boss '
   + 'can read them',
   JSON.stringify(card.rowsBox));
  const joined = (card.vals || []).join(' \u0001 ');
  ok(joined.includes(CARD.title), 'the TITLE on the glass is the package\'s title, character '
     + 'for character', JSON.stringify(card.vals && card.vals[1]));
  ok(joined.includes(CARD.url) && /youtube\.com\/watch\?v=/.test(CARD.url),
     'THE UNLISTED URL IS ON THE CARD - ' + CARD.url + ' - so the boss can open the thing he is '
     + 'about to make public before he says yes',
     JSON.stringify(CARD.url));
  ok(joined.includes(CARD.tags.split(',')[0].trim()) && joined.includes(TEST_DISCLOSURE),
     'and so are the TAGS and the DESCRIPTION - including the disclosure line verbatim, which '
     + 'is the one thing on this card that must not be summarised',
     JSON.stringify({ tags: CARD.tags.slice(0, 60), hasDisclosure: joined.includes(TEST_DISCLOSURE) }));
  ok(!!plate && card.plate.shown === true && card.plate.w > 0 && card.plate.h > 0
     && card.plate.boxW > 0 && card.plate.boxH > 0,
     'THE THUMBNAIL PLATE IS A REAL DECODED IMAGE, LAID OUT: ' + card.plate.w + '×'
     + card.plate.h + ' natural pixels in a ' + card.plate.boxW + '×' + card.plate.boxH
     + ' box, shown in ' + plate + 'ms. The BOX is asserted as well as the decode, because a '
     + 'decoded image in a zero-height box is invisible and photographs as nothing',
     JSON.stringify(card.plate));
  ok(/^\/poster\?video=/.test(card.plate.src) && !card.plate.src.includes('output'),
     'and its src is AN ID AND NOT A PATH (' + card.plate.src + '), even though the path is '
     + 'sitting on the row below it - which is the whole of /poster\'s reason for existing',
     JSON.stringify(card.plate.src));
  ok(JSON.stringify(card.buttons) === JSON.stringify(['Yes', 'No']),
     'and it is the SAME CARD as every other hand\'s: one Yes, one No, one countdown, one slot',
     JSON.stringify(card.buttons));

  /* ALL FIVE THINGS AT ONCE, AT FIVE HEIGHTS, AND THE ORDER IN WHICH THEY GIVE WAY. §40 asks
     for a card that shows the title, the description, the tags, the thumbnail AND the unlisted
     URL - and that is a claim about them being on screen TOGETHER, which is a different claim
     from each of them existing. The first run of this section proved every one of the six rows
     green at a 723px viewport while the rows were laid out at 723x0: the plate took its 110
     pixels unconditionally and the rows, the only yielding thing in a capped card, absorbed all
     of it. Six parameters in the DOM, readable by textContent, invisible to the boss.
     THE LAW THIS NOW ASSERTS, in the order of priority it encodes:
       1. the rows are never zero - the parameters are what consent is given to;
       2. the Yes button is always on screen - the deck's own law;
       3. the plate is shown when there is room for both and HIDDEN when there is not, never
          squeezed to a sliver - a one-pixel band of a poster is noise, not a thumbnail.
     Five heights, because the exchange only happens at the bottom of the range: 710 is the
     last viewport that carries both, and 700 is the first that drops the picture. A
     one-viewport proof of a budget is no proof of a budget. */
  for (const h of [900, 760, 723, 710, 700, 640]) {
    await page.send('Emulation.setDeviceMetricsOverride',
      { width: 1280, height: h, deviceScaleFactor: 1, mobile: false });
    await sleep(400);
    const m = await page.json('(() => { const r = document.getElementById("ask-rows");'
      + ' const p = document.getElementById("ask-plate");'
      + ' const y = document.getElementById("ask-yes");'
      + ' const rb = r.getBoundingClientRect(), pb = p.getBoundingClientRect();'
      + ' return {rows: Math.round(rb.height), plate: Math.round(pb.height),'
      + '  yes: Math.round(y.getBoundingClientRect().bottom), view: window.innerHeight,'
      + '  scrollH: r.scrollHeight, cssWidth: getComputedStyle(p).width,'
      + '  capped: document.getElementById("answer").classList.contains("capped"),'
      + '  ruleServed: document.documentElement.outerHTML.indexOf("width:96px") >= 0}; })()');
    const roomy = m.view > 700;
    const plateOk = roomy ? m.plate >= 24 : m.plate === 0;
    ok(m.rows > 0 && m.yes <= m.view && plateOk,
       'AT A ' + m.view + 'px VIEWPORT the parameters and the buttons are on screen and the '
       + 'plate ' + (roomy ? 'is with them at ' + m.plate + 'px - a picture, not a sliver'
                           : 'has stood down rather than crowd them out')
       + ': rows ' + m.rows + 'px of ' + m.scrollH + ' (scrolling), plate ' + m.plate
       + 'px, Yes ending at ' + m.yes + ' inside ' + m.view,
       JSON.stringify({ ...m, expectedPlate: roomy ? '>=24' : '0' }));
  }
  await page.send('Emulation.clearDeviceMetricsOverride');
  await sleep(300);
  /* and the reading the plate below is taken at is re-measured, because the box moved. */
  const box = await page.json('(() => { const b = document.getElementById("a-ask")'
    + '.getBoundingClientRect(); return {x: Math.round(b.x), y: Math.round(b.y),'
    + ' w: Math.round(b.width), h: Math.round(b.height)}; })()');
  card.box = box;

  /* THE PLATES. Two: the card in its room, and the card's own rectangle at 1:1. */
  await page.shot(join(OUT, 'broadcast-card-room.png'));
  await page.shot(join(OUT, 'broadcast-card.png'),
                  { x: card.box.x - 8, y: card.box.y - 8, w: card.box.w + 16,
                    h: card.box.h + 16 });
  note('plates: ' + join(OUT, 'broadcast-card.png') + ' (the card, 1:1) and '
       + join(OUT, 'broadcast-card-room.png') + ' (the room)');
  ok(existsSync(join(OUT, 'broadcast-card.png'))
     && statSync(join(OUT, 'broadcast-card.png')).size > 4000,
     'and the plate is on disk for the boss, '
     + statSync(join(OUT, 'broadcast-card.png')).size + ' bytes',
     'no plate was written');

  /* AND THE CARD IS WITHDRAWN. A proposal left standing would lapse into a spoken line in the
     employer's room an hour from now, which is a harness leaving litter in a live house. */
  const gone = await page.json(
    '(async () => { const r = await fetch("/tools", {method:"POST",'
    + ' headers:{"Content-Type":"application/json"}, body: JSON.stringify({cmd:"withdraw"})});'
    + ' const d = await r.json(); return {status: r.status, withdrew: d.withdrew}; })()');
  ok(gone.status === 200,
     'and the harness takes its card away rather than leaving one to lapse in a live house',
     JSON.stringify(gone));
  const after = await http('/poster?video=' + CARD.video);
  ok(after.status === 404,
     'after which the plate\'s own route 404s again - the slot was the only thing that made that '
     + 'id resolvable, and nothing of this harness is left reachable',
     JSON.stringify(after.status));
}

/* =====================================================================================
   10 · THE PREMIERE, AND WHAT IT IS WAITING FOR
   §40 PART 3 asks for a live premiere upload. It is blocked on three prerequisites the mandate
   itself reserves to the boss, so this section MEASURES the block rather than reporting a
   stub as green: a harness that invented a consent, a channel or a disclosure line would be
   asserting against a machine nobody has.
   ===================================================================================== */
step('10 · the premiere: named prerequisites, and nothing invented in their place');

const S = crank(['--status']);
const st = S.body || {};
note('token file   : ' + (st.tokenFile || '?') + '  (state ' + (st.state || '?') + ')');
note('channel      : ' + (st.channelTitle || '(none)') + ' · digest '
     + (st.tokenDigest ? st.tokenDigest.slice(0, 12) + '…' : '(none)'));
note('why          : ' + (st.why || '(nothing outstanding)'));

ok(st.state !== 'connected' ? S.status === 1 : S.status === 0,
   'the hand crank\'s exit status tells a shell the truth about the connection (' + st.state
   + ' -> exit ' + S.status + ')',
   JSON.stringify({ state: st.state, status: S.status }));

const PREREQS = [
  ['(a) OAuth consent in the boss\'s browser', st.state === 'connected'],
  ['(b) a channel on the boss\'s Google account', !!st.channel],
  ['(c) the boss\'s approved affiliate-disclosure line', DISC.live.ok === true],
];
for (const [what, met] of PREREQS) note('  ' + (met ? 'met    ' : 'WAITING') + '  ' + what);
const blocked = PREREQS.filter(([, met]) => !met);

if (!blocked.length) {
  note('every prerequisite is met - the premiere can be run with: '
       + 'python tools/broadcast_film.py --upload ' + FILM);
  ok(false, 'THE LIVE PREMIERE RAN - unlisted, then public on the boss\'s word',
     'the prerequisites are met, so this harness should no longer be reporting the premiere as '
     + 'blocked: run --upload, approve the card on camera, and assert the public page here');
} else {
  ok(true, 'THE PREMIERE IS BLOCKED ON ' + blocked.length + ' PREREQUISITE(S) RESERVED TO THE '
     + 'BOSS, each named: ' + blocked.map(([w]) => w.slice(0, 3)).join(' ')
     + ' - and nothing here invents one in their place');
}

/* AND NOT ONE CREDENTIAL REACHED THIS OUTPUT. The status payload is scanned for the four things
   that may never be printed: an access token, a refresh token, a client secret and an account
   email. The digest is the one exception and is asserted to BE a digest. */
const leak = JSON.stringify(st);
ok(!/access_token|refresh_token|client_secret/.test(leak) && !/@gmail|@googlemail/.test(leak),
   'and the status line carries no token, no secret and no account email - only a digest',
   leak.slice(0, 300));
ok(!st.tokenDigest || /^[0-9a-f]{16,64}$/.test(st.tokenDigest),
   'and the one credential-shaped string in it is a sha256 digest or empty',
   JSON.stringify(st.tokenDigest));

/* =====================================================================================
   the verdict
   ===================================================================================== */
if (page) { try { page.close(); } catch { } }
if (keeper) {
  const puts = keeper.count();
  keeper.stop();
  note('the window had to be un-minimised ' + puts + ' time(s) in this run');
}
for (const p of profiles) shutChrome(p);
for (const pr of procs) { try { pr.kill(); } catch { } }

say('');
say('  ' + '-'.repeat(74));
if (fail) { say('  FAILED:'); for (const f of failures) say('    - ' + f); say(''); }
say('  VERIFY ' + pass + '/' + (pass + fail) + (fail ? ' FAIL' : ' PASS'));
say('');
process.exit(fail ? 1 : 0);
