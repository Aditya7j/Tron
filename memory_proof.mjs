/* memory_proof.mjs - THE GALAXY IS HIS COLLECTION, AND NOTHING ELSE IS IN IT.
 * =============================================================================================
 * WHY THIS IS A HARNESS AND NOT A GLANCE AT THE SKY. §27 PART 8 says the worlds, the clusters and
 * the relations all DERIVE from his notes - "worlds == notes, clusters == folders, links ==
 * computed" - and every one of those is a claim you cannot check by looking. A galaxy with one
 * world too many looks like a galaxy. A galaxy built from a graph-data.js written last Tuesday
 * looks exactly like a galaxy built from the notes on disk now, and it is the same picture right
 * up to the moment he asks about the note he filed this morning and is told it does not exist.
 * The quarantine makes that worse rather than better: thirty invented café notes were turned out
 * of this collection in PART 8, and "they are gone" is a claim about ABSENCE - the one kind of
 * claim a screenshot can never make, because the picture looks the same whether they went or the
 * page simply stopped drawing them.
 *
 * THE FIVE CLAIMS, each naming the failure it catches:
 *
 *   A. THE SKY IS THE FOLDER, as SETS and not as counts. Every star's file is a file on disk and
 *      every markdown file under notes/ is a star; every star's cluster is the folder its file
 *      sits in. Failure mode: two off-by-one errors that cancel, which is what a count-only check
 *      passes and what a rename produces - one star with no file and one file with no star, and a
 *      note that can never be opened from the galaxy.
 *
 *   B. AND THE ARTEFACT IS NOT STALE. build.py is re-run and viewer/graph-data.js must come back
 *      IDENTICAL apart from its own timestamp. Failure mode: the whole of A passing against a
 *      graph-data.js that agreed with the disk an hour ago. A is a comparison between the page and
 *      the disk, and both of them read the same stale file - the page loads it and this harness's
 *      own readdir is the only independent witness in the room. Re-running the builder is what
 *      makes A a statement about the notes rather than about the artefact.
 *
 *   C. LINKS == COMPUTED, and computed by the BUILDER rather than by this file. The relations are
 *      corroborated against the raw notes - a wikilink link must have a [[target]] in one of its
 *      two notes, a mention link must have the other note's words in its prose, a shared link must
 *      have six citations to stand on - but they are never RECOMPUTED here. A harness that
 *      reimplements build_links has two implementations of one rule and proves only that they
 *      agree, which is precisely what they will stop doing. Failure mode this catches instead: a
 *      relation drawn between two notes that have nothing whatever to do with each other, which is
 *      the galaxy telling him something about his own thinking that is not true.
 *
 *   D. HIS REAL COLLECTION HAS NO RELATIONS, so the sky with relations in it is brought along.
 *      Section C runs against archive/quarantine - the turned-out corpus, thirty worlds and the
 *      wikilinks between them - built in for the length of the run with --no-vectors so the
 *      quarantine stays unindexed and his own notes are never re-embedded. Failure mode: a link
 *      harness that is green because there are no links, which is what this one would be today.
 *
 *   E. AND "remember that ..." IS A CARD. The one write in this project that used to happen
 *      without consent. Said through the spoken door, it must raise a proposal and leave the
 *      folder alone; said with nothing after it, it must refuse; and only a real mouse on the real
 *      Yes may put a file on the disk.
 *
 * IT WRITES ONE REAL NOTE AND TAKES IT BACK, and it moves his graph-data.js and puts it back.
 *   - The captured sentence says in its own words that a harness wrote it. Nothing here puts a
 *     personal claim into his collection: that is the DO-NOT-INVENT law, and a harness for the
 *     memory is exactly where it would be broken by accident.
 *   - The removal and the restore are both CHECKS, so a run that dies holding either says so in
 *     its own verdict line instead of quietly leaving an invented fact in the galaxy.
 *
 * Usage:  python server.py 2>> server-trace.log   then   node memory_proof.mjs   (solo)
 */
import { spawn, spawnSync } from 'node:child_process';
import { mkdtempSync, rmSync, existsSync, readdirSync, readFileSync, unlinkSync,
         statSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { tmpdir } from 'node:os';
import { join, dirname, relative } from 'node:path';
import { fileURLToPath } from 'node:url';

const GALAXY = 'http://127.0.0.1:4700';
const VIEW = GALAXY + '/?mute=1';
const PORT = 9287;                       // nobody else's; see the port map in the lookbook
const CDP = 'http://127.0.0.1:' + PORT;
/* FROM THE SCRIPT'S OWN PLACE, not the shell's: every claim below is a readdir, and a readdir
   against a relative path is a claim about whatever directory the harness was started in. */
const ROOT = dirname(fileURLToPath(import.meta.url));
const NOTES = join(ROOT, 'notes');
const CAPTURES = join(NOTES, 'captures');
const GRAPH = join(ROOT, 'viewer', 'graph-data.js');
const REF = 'archive/quarantine';        // the turned-out corpus, brought back as a fixture only
/* THE ABSOLUTE INTERPRETER. Bare `python` on this machine is the Store stub, which exits 9009 and
   would fail the rebuild for a reason that has nothing to do with the memory. */
const PY = 'C:/Users/Fullstack Developer/AppData/Local/Programs/Python/Python313/python.exe';
const CAPTURE_TITLE = 'the finish window should stay at 900ms';
const FIXTURE = 'This thought was captured by memory_proof.mjs to prove the card is real, and ' +
                'it is removed again before the harness exits.';
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
const post = async (path, body) => {
  const r = await fetch(GALAXY + path, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body || {}),
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
/* A REAL MOUSE ON A REAL RECTANGLE, for the consent door and for nothing else. element.click()
   would prove the handler runs and prove nothing about whether a pointer can reach it - and the
   hands hook deliberately has no confirm door, so this is the only way in. */
async function clickSel(page, sel) {
  const box = await page.json(`(function(){var e=document.querySelector(${JSON.stringify(sel)});
    if(!e) return null; var r=e.getBoundingClientRect();
    return {x:Math.round(r.left+r.width/2), y:Math.round(r.top+r.height/2),
            w:Math.round(r.width), h:Math.round(r.height)};})()`);
  if (!box || !box.w) return false;
  for (const type of ['mousePressed', 'mouseReleased']) {
    await page.send('Input.dispatchMouseEvent', { type, x: box.x, y: box.y, button: 'left',
      clickCount: 1, buttons: type === 'mousePressed' ? 1 : 0 });
    await sleep(45);
  }
  return true;
}

/* ---- THE DISK, READ FROM THIS PROCESS -------------------------------------------------------
   Nothing below asks the page or the server what is on the disk. That is the whole point: two
   readers of one stale artefact agree with each other perfectly. */
/* THE SAME NAMES THE BUILDER SKIPS, copied from build.py:65 rather than guessed at. If this
   walker followed quarantine/ and the builder did not, section A would redden every run and
   blame the page for obeying the law it was told to obey. */
const SKIP_DIRS = new Set(['.git', '.svn', '.hg', 'node_modules', 'viewer', '__pycache__',
  '.obsidian', '.trash', '.vscode', '.idea', 'venv', '.venv', 'env', 'quarantine']);
function walkMd(dir, base) {
  const out = [];
  let entries = [];
  try { entries = readdirSync(dir, { withFileTypes: true }); } catch { return out; }
  for (const e of entries.sort((a, b) => a.name.localeCompare(b.name))) {
    if (e.name.startsWith('.')) continue;
    const full = join(dir, e.name);
    if (e.isDirectory()) {
      if (SKIP_DIRS.has(e.name)) continue;
      out.push(...walkMd(full, base));
    } else if (/\.(md|markdown)$/i.test(e.name)) {
      out.push(relative(base, full).replace(/\\/g, '/'));
    }
  }
  return out;
}
/* The builder's own slug rule, for ASCII, and it is used to CORROBORATE and never to compute -
   see claim C. `slugify` in build.py normalises unicode first; these notes are ASCII, and if one
   day they are not, this reader is lenient in the direction of finding fewer targets. */
const slugly = (s) => String(s).toLowerCase().replace(/[^\w\s-]/g, ' ')
  .trim().replace(/[\s_-]+/g, '-').replace(/^-+|-+$/g, '');
const wikiTargets = (raw) => {
  const out = [];
  for (const hit of String(raw).match(/\[\[([^\]]+)\]\]/g) || []) {
    let t = hit.slice(2, -2).split('|')[0].split('#')[0].trim();
    t = t.split('/').pop();
    if (/\.md$/i.test(t)) t = t.slice(0, -3);
    const s = slugly(t);
    if (s) out.push(s);
  }
  return out;
};
/* graph-data.js is not byte-stable across rebuilds - write_outputs stamps its clock into the file
   - so the digest is taken with the clock masked. Masking it IS the check: a rebuild may change
   the time and must change nothing else.
   AND IT IS STAMPED TWICE, which cost this harness its first red. Masking only "generated" in the
   meta left the header comment - `// Generated by build.py on 2026-09-28T16:40:57Z` - in the
   digest, so two consecutive builds of the same six notes came back with different digests at the
   SAME LENGTH (3313 bytes both times), which reads exactly like a real drift: same shape,
   different content. MEASURED, by diffing two builds a second apart - the only two differing
   runs of characters in 3227 were the two stamps. So the rule is the clock and not one field:
   every ISO stamp in the file is normalised, and a stamp in a third place tomorrow is covered.
   FAILURE MODE THIS NAMES: a permanent red on the staleness check that blames his notes for the
   builder writing the time in more places than the harness knew about. */
const digestGraph = () => {
  const src = readFileSync(GRAPH, 'utf8');
  const masked = src.replace(/\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ/g, '<clock>');
  return { sha: createHash('sha256').update(masked).digest('hex').slice(0, 16),
           bytes: src.length, stamp: (src.match(/"generated":\s*"([^"]*)"/) || [])[1] || '?' };
};
const graphMeta = () => {
  const src = readFileSync(GRAPH, 'utf8');
  return { root: (src.match(/"notesRoot":\s*"([^"]*)"/) || [])[1] || '?',
           nodes: (src.match(/"id":\s*\d+/g) || []).length,
           links: (src.match(/"source":\s*\d+/g) || []).length };
};
function build(dir) {
  const args = dir ? [dir, '--no-vectors'] : ['--no-vectors'];
  const p = spawnSync(PY, ['build.py'].concat(args), { cwd: ROOT, encoding: 'utf8' });
  const line = String(p.stdout || '').split(/\r?\n/)
    .filter((l) => /worlds|nodes|links/i.test(l)).slice(-1)[0] || '';
  return { code: p.status, line: line.trim() };
}
const capture = () => {
  try { return readdirSync(CAPTURES).filter((n) => n.endsWith('.md')).sort(); }
  catch { return []; }
};

const profiles = []; const procs = [];
let swapped = false;                     // his graph-data.js is standing in for another corpus
let wrote = null;                        // the capture file, once it is genuinely on disk

async function main() {
  console.log('\n  the memory: his notes, his clusters, his relations, and nothing invented\n');

  /* ============== A. THE SKY IS THE FOLDER ============================================= */
  step('A. worlds == notes, clusters == folders');
  const onDisk = walkMd(NOTES, ROOT).map((f) => 'notes/' + f.replace(/^notes\//, ''));
  note(onDisk.length + ' markdown file(s) under notes/: ' + JSON.stringify(onDisk));
  ok(onDisk.length > 0,
     'there is a collection to prove anything about',
     'notes/ holds no markdown at all, so every claim below would be vacuously true');

  const exe = CHROMES.find((p) => existsSync(p));
  if (!exe) throw new Error('no chrome.exe');
  const profile = mkdtempSync(join(tmpdir(), 'devtools-profile-chrome-memory-'));
  profiles.push(profile);
  procs.push(spawn(exe, ['--headless=new', '--remote-debugging-port=' + PORT,
    '--user-data-dir=' + profile, '--no-first-run', '--no-default-browser-check',
    '--window-size=1378,900', '--use-gl=angle', '--use-angle=default',
    '--enable-unsafe-swiftshader', '--mute-audio', VIEW], { detached: true, stdio: 'ignore' }));
  for (let i = 0; i < 80; i++) {
    try { await cdp('/json/version'); break; } catch { await sleep(250); }
  }
  let target = null;
  for (let i = 0; i < 40; i++) {
    const l = await cdp('/json/list');
    target = (Array.isArray(l) ? l : []).filter((t) => t.type === 'page')
      .find((t) => t.url.includes('mute=1'));
    if (target) break;
    await sleep(300);
  }
  if (!target) throw new Error('no viewer page');
  const page = new Page(target.webSocketDebuggerUrl);
  await page.open();
  await page.send('Runtime.enable');
  await page.send('Input.enable').catch(() => { });
  ok(await waitFor(page, '!!(window.__galaxy && __galaxy.nodes && __galaxy.nodes.length)', 40000),
     'the viewer is up and the galaxy has stars in it');

  const stars = await page.json('__galaxy.nodes.map(function(n){return {id:n.id,' +
    ' slug:String(n.slug||""), group:String(n.group||""), file:String(n.file||""),' +
    ' degree:n.degree|0, words:n.words|0};})');
  const starFiles = stars.map((s) => s.file).sort();
  const wantFiles = onDisk.slice().sort();
  ok(JSON.stringify(starFiles) === JSON.stringify(wantFiles),
     'WORLDS == NOTES, as sets: ' + stars.length + ' stars and ' + onDisk.length +
     ' files, every one matched by path',
     'on disk and not a star: ' + JSON.stringify(wantFiles.filter((f) => !starFiles.includes(f))) +
     ' · a star with no file: ' + JSON.stringify(starFiles.filter((f) => !wantFiles.includes(f))) +
     ' - a count-only check passes two errors that cancel, and a rename makes exactly two');
  ok(stars.every((s, i) => s.id === i),
     'and a star\'s id is its index in the array, which is the contract build_nodes writes',
     'the ids are not 0..n-1, so anything that looks a node up by id is reading the wrong note: ' +
     JSON.stringify(stars.map((s) => s.id).slice(0, 12)));

  /* THE CLUSTERS, with "unfiled" standing in for the root of notes/ - a real cluster with no
     directory, and the case a naive folder comparison gets wrong. */
  const wrongGroup = stars.filter((s) => {
    const parts = s.file.split('/');                  // notes/<folder>/<file> or notes/<file>
    const want = parts.length > 2 ? parts[parts.length - 2] : 'unfiled';
    return s.group !== want;
  });
  ok(wrongGroup.length === 0,
     'CLUSTERS == FOLDERS: every star\'s cluster is the folder its file sits in' +
     (stars.some((s) => s.group === 'unfiled')
       ? ', with "unfiled" for the root of notes/' : ''),
     JSON.stringify(wrongGroup.slice(0, 4).map((s) => [s.file, s.group])));
  const clusters = Array.from(new Set(stars.map((s) => s.group))).sort();
  note('clusters in the sky: ' + JSON.stringify(clusters));
  ok(clusters.every((g) => typeof g === 'string' && g.length > 0),
     'and every cluster has a name, so no world is filed under nothing');
  ok(!starFiles.some((f) => /quarantine/i.test(f)),
     'AND NOTHING QUARANTINED IS A STAR: no star\'s path goes through a quarantine',
     JSON.stringify(starFiles.filter((f) => /quarantine/i.test(f))));

  const health = (await get('/health')).body || {};
  ok(health.notes === stars.length,
     'the server counts the same collection the page draws: /health says ' + health.notes +
     ' and the sky holds ' + stars.length,
     'failure mode: the page loaded one graph-data.js and the server re-indexed into another');
  let index = null;
  try { index = JSON.parse(readFileSync(join(ROOT, 'notes-index.json'), 'utf8')); } catch { }
  ok(index && Array.isArray(index.notes) && index.notes.length === stars.length,
     'and the index the brain retrieves from holds the same ' + stars.length + ' note(s)',
     'the galaxy and the retrieval index disagree, so a star can be lit that cannot be quoted: ' +
     JSON.stringify(index && index.notes ? index.notes.length : null));

  /* ============== B. THE ARTEFACT IS NOT STALE ========================================= */
  step('B. and the artefact is what his notes compute to, now');
  const before = digestGraph();
  note('viewer/graph-data.js is ' + before.bytes + ' bytes, stamped ' + before.stamp +
       ', digest ' + before.sha);
  const again = build(null);
  ok(again.code === 0, 'build.py re-runs against notes/ (' + again.line + ')',
     'exit ' + again.code);
  const after = digestGraph();
  ok(after.sha === before.sha,
     'THE REBUILD CHANGES THE CLOCK AND NOTHING ELSE: the digest is unchanged with both stamps ' +
     'masked (' + after.sha + '), so the galaxy on the glass is what his notes compute to TODAY',
     'the artefact was stale: rebuilding changed it from ' + before.sha + ' to ' + after.sha +
     ' (' + before.bytes + ' -> ' + after.bytes + ' bytes). Every check in section A compared ' +
     'the page against the disk and both were reading the same out-of-date file');
  ok(after.stamp !== before.stamp || again.code !== 0,
     'and the clock did move, so the rebuild really happened (' + before.stamp + ' -> ' +
     after.stamp + ')',
     'the stamp is identical, so build.py may not have written the file at all and the digest ' +
     'check above proved nothing');

  /* ============== E. THE REMEMBER HAND, WHILE HIS CORPUS IS STILL IN PLACE ============== */
  step('E. "remember that ..." is a card, not a write');
  const capturesBefore = capture();
  note('notes/captures holds ' + capturesBefore.length + ' note(s) as this begins');
  /* THE EMPTY TRIGGER AT THE SERVER'S OWN DOOR. The refusal that predates the gate, and the one
     place a direct POST is the honest test: what must be proved is that no SLOT is minted, and
     the slot lives in the server's table, not in this tab. */
  const empty = await post('/remember', { text: 'remember that', session: 'memory-proof' });
  const eb = empty.body || {};
  ok(empty.status === 400 && !eb.pending && !eb.id,
     'REFUSAL ON EMPTY: "remember that" with nothing after it is refused and mints no slot ' +
     '(HTTP ' + empty.status + ')',
     'a trigger with no thought behind it must not leave a slot a later yes can confirm - and a ' +
     'yes is one word, said in a room with no card on the glass: ' +
     JSON.stringify(eb).slice(0, 220));
  ok(JSON.stringify(capture()) === JSON.stringify(capturesBefore),
     'and nothing appeared in notes/captures: ' + JSON.stringify(capture()));
  const after400 = (await get('/tools')).body || {};
  ok(!after400.pending,
     'and the single slot is still empty afterwards, read from GET /tools',
     JSON.stringify(after400.pending));

  /* AND THE REAL ONE THROUGH THE PAGE'S OWN DOOR, not through fetch. A POST from this process
     raises a slot the server knows about and a card NOBODY CAN SEE, which would prove the
     server gates and leave the thing worth proving - that the gate reaches the glass - untested.
     __galaxy.ask() is the same function the microphone and the text rail call. */
  const said = 'remember that ' + FIXTURE;
  await page.evaluate('__galaxy.ask(' + JSON.stringify(said) + '), "asked"');
  const raised = await waitFor(page,
    '!!(__galaxy.hands.pending && __galaxy.hands.pending.tool === "save_note")', 30000);
  const card = await page.json('__galaxy.hands.pending');
  ok(raised,
     'A REMEMBERED THOUGHT RAISES A CARD IN THE PAGE: ' +
     JSON.stringify(card && { tool: card.tool, id: card.id ? 'minted' : null }),
     JSON.stringify(card).slice(0, 260));
  const slot = (await get('/tools')).body || {};
  ok(slot.pending && slot.pending.tool === 'save_note',
     'and the server holds exactly that one slot behind it: ' +
     JSON.stringify(slot.pending && slot.pending.tool),
     JSON.stringify(slot).slice(0, 240));
  ok(JSON.stringify(capture()) === JSON.stringify(capturesBefore),
     'AND THE FOLDER IS UNTOUCHED WHILE THE CARD IS UP: still ' + capturesBefore.length +
     ' note(s)',
     'this is the write that used to happen in the same breath as the sentence, with no card ' +
     'at all: ' + JSON.stringify(capture()));
  ok(await waitFor(page, '__galaxy.hands.shown === true', 6000),
     'and it is SHOWN on the glass, so there is something for him to press');
  const rows = await page.json('__galaxy.hands.rows');
  ok(rows && Object.keys(rows).length > 0 &&
     JSON.stringify(rows).toLowerCase().includes('captur'),
     'with the parameters rendered where he can read them before approving: ' +
     JSON.stringify(rows).slice(0, 200),
     'a card that does not show what it is about is a consent dialog for an unknown act');
  const buttons = await page.json('__galaxy.hands.buttons');
  ok(buttons && buttons.yes && buttons.no && buttons.disabled === false,
     'and both buttons are live: ' + JSON.stringify(buttons),
     'a card with a disabled Yes, or with one button, is a notification and not a gate');

  const lit = await page.json('__galaxy.nodes.length');
  ok(await clickSel(page, '#ask-yes'),
     'the real Yes is reachable with a real pointer',
     'the consent door is deliberately not on the test hook, so if a mouse cannot reach it, ' +
     'nothing can');
  const born = await waitFor(page, '__galaxy.nodes.length === ' + (lit + 1), 20000);
  const files = capture();
  const added = files.filter((f) => !capturesBefore.includes(f));
  if (added.length === 1) wrote = added[0];
  ok(added.length === 1,
     'AND ONLY THEN IS THERE A FILE: notes/captures gained exactly one, ' +
     JSON.stringify(added),
     'gained ' + added.length + ': ' + JSON.stringify(added));
  ok(born, 'and one star was born for it, without a reload (' + lit + ' -> ' +
     (await page.json('__galaxy.nodes.length')) + ')',
     'the note is on disk and the galaxy did not notice, so he cannot see what he just said');
  /* FOUND BY ITS FILE AND NOT BY ITS POSITION. capture_landed() re-indexes PRESERVING IDS by
     reordering the walk, so where the new star lands in the array is its business; that the star
     for this file exists and is filed under captures is the claim. */
  const newStar = wrote ? await page.json(
    '(function(){var f=' + JSON.stringify('notes/captures/' + wrote) + ';' +
    'var n=__galaxy.nodes.filter(function(x){return String(x.file||"")===f;})[0];' +
    'return n ? {id:n.id, group:String(n.group||""), file:String(n.file||"")} : null;})()') : null;
  ok(newStar && newStar.group === 'captures',
     'and it is the star for THAT file, in the captures cluster where a passing thought ' +
     'belongs: ' + JSON.stringify(newStar),
     'the note is on disk and no star carries its path, so the galaxy grew by one world that ' +
     'is not the note he just dictated');
  ok(wrote && readFileSync(join(CAPTURES, wrote), 'utf8').includes(FIXTURE),
     'and the file holds the sentence that was said, read back off the disk',
     'the note was written with something other than what he said in it');

  /* ============== C + D. A SKY WITH RELATIONS IN IT ===================================== */
  step('C. links == computed, corroborated against the notes themselves');
  const mine = graphMeta();
  note('his own collection computes to ' + mine.nodes + ' worlds and ' + mine.links +
       ' relations');
  if (mine.links === 0) {
    /* HIS COLLECTION HAS NO RELATIONS YET, so the assertions below would all be green on an
       empty set. The turned-out corpus is brought back as a FIXTURE - built with --no-vectors,
       so nothing under the quarantine becomes retrievable and his own notes are not re-embedded
       - and put away again in `finally` as a check. */
    const ref = build(REF);
    if (ref.code !== 0) throw new Error('the reference corpus will not build: exit ' + ref.code);
    swapped = true;
    note('brought in ' + REF + ' as a fixture, because a link harness with nothing to link is ' +
         'green for the wrong reason (' + ref.line + ')');
  }
  await page.send('Page.navigate', { url: VIEW });
  await sleep(1500);
  ok(await waitFor(page, '!!(window.__galaxy && __galaxy.allLinks && __galaxy.nodes.length > 2)',
                   40000),
     'the page comes back up on the reference sky');
  const sky = graphMeta();
  const nodes2 = await page.json('__galaxy.nodes.map(function(n){return {id:n.id,' +
    ' slug:String(n.slug||""), file:String(n.file||""), degree:n.degree|0};})');
  /* 3d-force-graph REPLACES source and target with the node objects once the graph is loaded,
     so a harness that reads link.source straight gets an object here and an integer in
     graph-data.js. Reading through the id is the difference between measuring the graph and
     measuring the library's bookkeeping. */
  const links = await page.json('__galaxy.allLinks.map(function(l){' +
    'var s = l.source, t = l.target;' +
    'return {s: (s && typeof s === "object") ? s.id : s,' +
    ' t: (t && typeof t === "object") ? t.id : t,' +
    ' kind: String(l.kind||""), weight: l.weight|0};})');
  ok(links.length === sky.links && links.length > 0,
     'THE PAGE HOLDS EVERY RELATION THE BUILDER WROTE: ' + links.length + ' in the sky, ' +
     sky.links + ' in graph-data.js',
     'the page is drawing a different link set from the one on disk');
  const kinds = {};
  links.forEach((l) => { kinds[l.kind] = (kinds[l.kind] || 0) + 1; });
  note('relations by kind: ' + JSON.stringify(kinds));
  ok(links.every((l) => ['wikilink', 'mention', 'shared'].includes(l.kind)),
     'and every one of them is one of the three declared signals',
     'a kind build_links never emits is a relation nothing can explain: ' +
     JSON.stringify(Object.keys(kinds)));
  ok(links.every((l) => l.s !== l.t),
     'no world is related to itself');
  ok(links.every((l) => Number.isInteger(l.s) && Number.isInteger(l.t) &&
                        l.s >= 0 && l.t >= 0 && l.s < nodes2.length && l.t < nodes2.length),
     'and both ends of every relation are stars that exist',
     JSON.stringify(links.filter((l) => !(l.s < nodes2.length && l.t < nodes2.length)).slice(0, 4)));
  const pairs = links.map((l) => Math.min(l.s, l.t) + ':' + Math.max(l.s, l.t));
  ok(new Set(pairs).size === pairs.length,
     'and each PAIR appears once, with the strongest signal that joined them - not once per ' +
     'signal',
     'duplicate pairs: ' + JSON.stringify(pairs.filter((p, i) => pairs.indexOf(p) !== i)
                                               .slice(0, 5)) +
     ' - two lines between the same two worlds reads as a stronger relation than the data says');
  ok(links.every((l) => l.weight >= 1),
     'and every relation carries a weight of at least one');

  /* THE CORROBORATION. The raw notes are read here and asked whether they can ACCOUNT for each
     relation the builder drew. Not recomputed - see claim C - so each test below is a NECESSARY
     condition, and a failure means a link exists that its own two notes cannot explain. */
  const raw = new Map();
  const readRaw = (file) => {
    if (!raw.has(file)) {
      try { raw.set(file, readFileSync(join(ROOT, file), 'utf8')); } catch { raw.set(file, ''); }
    }
    return raw.get(file);
  };
  const bySlug = new Map(nodes2.map((n) => [n.slug, n]));
  const unexplained = { wikilink: [], mention: [], shared: [] };
  for (const l of links) {
    const A = nodes2[l.s], B = nodes2[l.t];
    if (!A || !B) continue;
    const ra = readRaw(A.file), rb = readRaw(B.file);
    if (l.kind === 'wikilink') {
      const ta = wikiTargets(ra), tb = wikiTargets(rb);
      if (!ta.includes(B.slug) && !tb.includes(A.slug)) {
        unexplained.wikilink.push([A.slug, B.slug]);
      }
    } else if (l.kind === 'mention') {
      const words = (s) => s.split('-').filter(Boolean);
      const has = (text, slug) =>
        words(slug).every((w) => new RegExp('(?<![\\w])' + w + '(?![\\w])', 'i').test(text));
      if (!has(ra, B.slug) && !has(rb, A.slug)) unexplained.mention.push([A.slug, B.slug]);
    } else {
      const ca = new Set(wikiTargets(ra).filter((s) => bySlug.has(s)));
      const cb = new Set(wikiTargets(rb).filter((s) => bySlug.has(s)));
      const both = [...ca].filter((s) => cb.has(s));
      if (both.length < 6) unexplained.shared.push([A.slug, B.slug, both.length]);
    }
  }
  ok(unexplained.wikilink.length === 0,
     'EVERY WIKILINK RELATION HAS A [[target]] IN ONE OF ITS TWO NOTES: all ' +
     (kinds.wikilink || 0) + ' accounted for in the raw markdown',
     'unaccounted: ' + JSON.stringify(unexplained.wikilink.slice(0, 5)) +
     ' - a line drawn between two notes that never mention one another tells him something ' +
     'about his own thinking that is not true');
  ok(unexplained.mention.length === 0,
     'and every MENTION relation has the other note\'s words in its prose: all ' +
     (kinds.mention || 0) + ' accounted for',
     'unaccounted: ' + JSON.stringify(unexplained.mention.slice(0, 5)));
  ok(unexplained.shared.length === 0,
     'and every SHARED relation stands on at least six citations both notes make: all ' +
     (kinds.shared || 0) + ' accounted for',
     'unaccounted: ' + JSON.stringify(unexplained.shared.slice(0, 5)) +
     ' - the co-citation floor is SHARED_WIKILINK_MIN, and a shared link under it is two notes ' +
     'joined for reading the same one thing');

  /* AND THE DEGREE ON EACH WORLD IS THE NUMBER OF LINES ON IT. write_outputs counts this while
     it writes, so it is a second bookkeeping of the same fact - and the planet's radius is
     drawn from it, which is how a wrong degree becomes a visibly wrong sky. */
  const deg = new Map(nodes2.map((n) => [n.id, 0]));
  links.forEach((l) => { deg.set(l.s, deg.get(l.s) + 1); deg.set(l.t, deg.get(l.t) + 1); });
  const offDeg = nodes2.filter((n) => n.degree !== deg.get(n.id));
  ok(offDeg.length === 0,
     'and each world\'s recorded degree is the number of relations actually on it, across all ' +
     nodes2.length + ' worlds',
     JSON.stringify(offDeg.slice(0, 5).map((n) => [n.slug, n.degree, deg.get(n.id)])) +
     ' - degree sets the planet\'s radius, so a wrong one is a world drawn the wrong size');

  const strong = await page.json('__galaxy.strongLinks.length');
  ok(strong > 0 && strong <= links.length,
     'the strongest-links view is a SUBSET of the whole: ' + strong + ' of ' + links.length,
     'a simplified view holding more lines than the full one is not a simplification');

  page.close();
}

main().catch((e) => {
  bad.push('the run itself: ' + e.message);
  console.log('\n  ERROR ' + (e && e.stack || e));
}).finally(async () => {
  /* HIS COLLECTION GOES BACK FIRST, and both halves are CHECKS. A harness that leaves an
     invented sentence in his notes, or leaves his galaxy showing somebody else's corpus, has
     broken the law it exists to protect and must say so in its own verdict line. The capture is
     removed BEFORE the rebuild so that one build.py call restores the root and drops the note. */
  if (wrote) {
    let gone = false;
    try {
      const path = join(CAPTURES, wrote);
      /* Only this file, and only while it is still the harness's own sentence: if he edited it
         in the two minutes this ran, it is his note now and it stays. */
      if (existsSync(path) && readFileSync(path, 'utf8').includes(FIXTURE)) {
        unlinkSync(path);
        gone = !existsSync(path);
      } else {
        note('the capture is no longer the harness\'s own sentence, so it is left alone');
        gone = true;
      }
    } catch (e) { console.log('  ERROR could not remove the capture: ' + e.message); }
    ok(gone, 'the captured thought is out of notes/captures again',
       'a harness that leaves an invented fact in his collection has broken the DO-NOT-INVENT ' +
       'law on its way out');
  }
  if (swapped || wrote) {
    const back = spawnSync(PY, ['build.py'], { cwd: ROOT, encoding: 'utf8' });
    const now = graphMeta();
    ok(back.status === 0 && now.root === 'notes' && now.nodes > 0,
       'and his own collection is back in the galaxy, built from notes: ' + now.nodes +
       ' worlds, ' + now.links + ' relations',
       'build.py exit ' + back.status + ', notesRoot ' + now.root + ' - the galaxy is showing ' +
       'the wrong corpus, and only a build.py by hand will put it right');
  }
  procs.forEach((p) => { try { process.kill(p.pid); } catch { } });
  await sleep(700);
  profiles.forEach((p) => { try { rmSync(p, { recursive: true, force: true }); } catch { } });
  console.log('\n  VERIFY ' + (checks - bad.length) + '/' + checks +
              (bad.length ? ' FAIL' : ' PASS') + '\n');
  bad.forEach((b) => console.log('    FAILED: ' + b));
  process.exit(bad.length ? 1 : 0);
});
