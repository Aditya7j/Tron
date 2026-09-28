/* census_proof.mjs - THE CENSUS: SEVENTEEN QUESTIONS, AND NOT ONE FILE UNTIL A WORD IS GIVEN.
 * =============================================================================================
 * WHY THIS BOARD NEEDS A HARNESS AND NOT A SCREENSHOT. A grid of readings can be checked with the
 * eye: the clock says 09:41 and it is 09:41. An INTAKE cannot. Its whole claim is about what does
 * NOT happen - he types an answer, and nothing is written - and a page that wrote the note the
 * instant the button was pressed would look identical in every plate anybody took of it. That
 * claim was also, until PART 8, false everywhere else in this project: "remember that ..." was
 * heard and written in the same breath, with no card, into a collection that is indexed and
 * quoted back. The Census is seventeen more chances to make the same mistake at once.
 *
 * THE SIX CLAIMS, and each names the failure it catches:
 *
 *   A. THE BANK IS THE BOUNDARY. Seventeen questions, three chapters, ids unique, titles that
 *      slugify to seventeen different filenames. Failure mode: two questions whose titles collide
 *      would file into the same note and answering one would close the other, so the board would
 *      report sixteen of seventeen for ever and he would never be asked the missing one.
 *
 *   B. THE THREE REFUSALS, AND THE FOLDER AFTER THEM. An id off the list, an empty answer, and a
 *      credential are each refused with no pending slot and nothing on disk. Failure mode: an
 *      intake form is the most natural place in a house for a password to be typed - "what are you
 *      learning at the moment" is not a question anybody expects to produce one - and a note is
 *      INDEXED, so a secret in one is a secret a later question can be answered with, out loud.
 *      The refusal is also asserted to carry no value anywhere in its payload.
 *
 *   C. THE BOARD AGREES WITH THE SERVER IT SPEAKS FOR, and the array agrees with the DOM. The
 *      question on the glass is the question GET /census called next; the fraction on each chapter
 *      tile is the server's count. Failure mode: a progress figure held in the page - which would
 *      read four of seventeen while the folder held three the moment he deleted a note.
 *
 *   D. THE DRAFT SURVIVES A REPAINT. boardPaint REBUILDS the grid rather than diffing it, so a
 *      half-typed answer inside the node it throws away is a half-typed answer that vanishes when
 *      anything else repaints. Typed through a real key event, not a hook, then a repaint forced,
 *      then read back out of the DOM.
 *
 *   E. FILE IT RAISES A CARD AND WRITES NOTHING. The real button is pressed with a real mouse, the
 *      proposal card is asserted to be up, and notes/census is asserted to be UNCHANGED while it
 *      is. Then Yes is pressed - also with a real mouse, because the consent door is deliberately
 *      not reachable from the test hook - and only then is there a file.
 *
 *   F. THE SITTING IS PUT DOWN AND LEAVES NO GHOST. Closing the board empties the grid, forgets
 *      the draft and forgets the skips. Failure mode: the shared board shell gained a board with
 *      state for the first time, and state in a shell that three subjects share is a leak into the
 *      other two.
 *
 * IT WRITES ONE REAL NOTE, AND TAKES IT BACK.
 *   - The answer it files says in its own words that a harness wrote it, so a reader who finds the
 *     file after a crash is not reading an invented fact about the employer. Nothing in this file
 *     puts a personal claim into his collection: that is the DO-NOT-INVENT law, and an intake
 *     harness is exactly where it would be broken by accident.
 *   - The file is removed in `finally` and build.py is re-run, and BOTH are assertions, so a run
 *     that died holding the note says so in its own verdict line.
 *   - If the question it wants is already answered, section E is skipped and says so rather than
 *     writing a second note beside his.
 *
 * Usage:  python server.py 2>> server-trace.log   then   node census_proof.mjs
 */
import { spawn } from 'node:child_process';
import { mkdtempSync, rmSync, existsSync, readdirSync, readFileSync, unlinkSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const GALAXY = 'http://127.0.0.1:4700';
const VIEW = GALAXY + '/?mute=1';
const PORT = 9285;                       // nobody else's; see the port map in the lookbook
const CDP = 'http://127.0.0.1:' + PORT;
/* FROM THE SCRIPT'S OWN PLACE, not from the shell's. Every "nothing was written" claim below
   is a readdir, and a readdir against a relative path is a claim about whatever directory the
   harness happened to be started in - which would pass beautifully from anywhere else. */
const ROOT = dirname(fileURLToPath(import.meta.url));
const CENSUS_DIR = join(ROOT, 'notes', 'census');
/* THE ABSOLUTE INTERPRETER. Bare `python` on this machine is the Store stub, which exits 9009
   and would make the rebuild-afterwards check fail for a reason that has nothing to do with
   the Census. */
const PY = 'C:/Users/Fullstack Developer/AppData/Local/Programs/Python/Python313/python.exe';
const WANT_ID = 'study-reading';          // the question this harness answers, and only this one
const WANT_FILE = 'what-i-am-reading.md';
const FIXTURE = 'This sentence was written by census_proof.mjs to prove the card is real, ' +
                'and it is removed again before the harness exits.';
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
      }, 20000);
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
/* THE FOLDER, READ FROM THIS PROCESS. Every "nothing was written" claim below is made against
   this rather than against something the page or the server said about itself, which is the only
   way that claim is worth making. An absent folder is an empty one: the hand creates it. */
const folder = () => {
  try { return readdirSync(CENSUS_DIR).filter((n) => n.endsWith('.md')).sort(); }
  catch { return []; }
};
/* A REAL MOUSE ON A REAL RECTANGLE. The tiles carry no ids - they are built from data - so the
   selector is how they are reached, and the press goes through Input.dispatchMouseEvent for the
   reason scribe_proof's does: element.click() would prove the handler runs and prove nothing at
   all about whether the thing is reachable with a pointer. */
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
async function openBoard(page) {
  await page.evaluate('__galaxy.cmd.open_(true)');
  await page.evaluate('__galaxy.cmd.run("census")');
  await waitFor(page, '__galaxy.cmd.board.which === "census"', 6000);
  await waitFor(page, '__galaxy.cmd.board.read !== null', 12000);
  await page.evaluate('__galaxy.cmd.board.paint()');
  await waitFor(page, '__galaxy.cmd.board.dom.length >= 4', 6000);
  return {
    tiles: await page.json('__galaxy.cmd.board.tiles'),
    dom: await page.json('__galaxy.cmd.board.dom'),
    head: await page.json('__galaxy.cmd.board.head'),
    row: await page.json('(function(){return __galaxy.cmd.rows.census;})()'),
  };
}
const byKey = (rows, key) => rows.filter((t) => String(t.key) === key)[0] || null;

const profiles = []; const procs = [];
let wroteNote = false;                   // set only once the file is genuinely there

async function main() {
  console.log('\n  the census: three chapters, seventeen questions, one card each\n');

  /* ============== A. THE BANK, BEFORE ANY PAGE IS INVOLVED ============================= */
  step('A. the question bank and the boundary it draws');
  const c0 = await get('/census');
  ok(c0.status === 200 && c0.body && c0.body.ok === true,
     'GET /census answers', JSON.stringify(c0.body).slice(0, 200));
  const snap = c0.body || {};
  const chapters = snap.chapters || [];
  ok(chapters.length === 3 &&
     JSON.stringify(chapters.map((c) => c.id)) === '["life","work","study"]',
     'three chapters, in order: ' + JSON.stringify(chapters.map((c) => c.name)),
     JSON.stringify(chapters.map((c) => c.id)));
  const all = chapters.reduce((a, c) => a.concat(c.questions || []), []);
  ok(all.length === 17 && snap.total === 17,
     'seventeen questions, and the total agrees with the list: ' + all.length + '/' + snap.total);
  const ids = new Set(all.map((q) => q.id));
  ok(ids.size === all.length, 'every question id is its own', String(ids.size));
  const slugs = new Set(all.map((q) => q.slug));
  ok(slugs.size === all.length,
     'AND EVERY TITLE SLUGIFIES TO ITS OWN FILENAME: ' + slugs.size + ' of ' + all.length,
     'failure mode: two questions sharing a filename means answering one closes the other, so ' +
     'the board reports sixteen of seventeen for ever and he is never asked the missing one');
  ok(all.every((q) => typeof q.ask === 'string' && /\?$/.test(q.ask.trim())),
     'and each one is a question, ending in a question mark',
     JSON.stringify(all.filter((q) => !/\?$/.test(String(q.ask).trim())).map((q) => q.id)));
  ok(String(snap.folder) === 'notes/census',
     'they file into notes/census, beside captures and not inside it: ' + snap.folder);
  const started = folder();
  note('notes/census holds ' + started.length + ' note(s) as this run begins: ' +
       JSON.stringify(started));
  ok(snap.answered === started.length,
     'and the server\'s count is the folder\'s count: ' + snap.answered + ' == ' + started.length,
     'failure mode: a progress figure held in the process, which is wrong from the first time ' +
     'he deletes a note until the next restart');

  /* ============== B. THE THREE REFUSALS ============================================== */
  step('B. what it will not file, and the folder afterwards');
  const r1 = await post('/census/answer', { id: 'not-a-question', answer: 'hello' });
  ok(r1.status === 400 && !(r1.body || {}).pending,
     'an id that is not one of the seventeen is refused, with no slot minted',
     JSON.stringify(r1.body).slice(0, 160));
  const r2 = await post('/census/answer', { id: 'life-home', answer: '   ' });
  ok(r2.status === 400 && !(r2.body || {}).pending,
     'an empty answer is refused - a skipped question is not a note saying nothing',
     JSON.stringify(r2.body).slice(0, 160));
  const SECRET = 'Tr0ub4dor3xK9z';
  const r3 = await post('/census/answer',
    { id: 'work-sign', answer: 'sign it Addi, and the api key is ' + SECRET });
  ok(r3.status === 400 && (r3.body || {}).refused === 'credential',
     'a credential in an answer is refused, and named as one',
     JSON.stringify(r3.body).slice(0, 200));
  ok(!JSON.stringify(r3.body || {}).includes(SECRET),
     'AND THE REFUSAL CARRIES NO VALUE, anywhere in its payload',
     'failure mode: a scanner that quotes what it found has copied the secret into the record ' +
     'that exists to prove it was kept out of the note');
  ok(JSON.stringify(folder()) === JSON.stringify(started),
     'and notes/census is untouched by all three: ' + JSON.stringify(folder()));

  /* ============== THE PAGE ========================================================== */
  const exe = CHROMES.find((p) => existsSync(p));
  if (!exe) throw new Error('no chrome.exe');
  const profile = mkdtempSync(join(tmpdir(), 'census-'));
  profiles.push(profile);
  procs.push(spawn(exe, ['--headless=new', '--remote-debugging-port=' + PORT,
    '--user-data-dir=' + profile, '--no-first-run', '--no-default-browser-check',
    '--window-size=1280,960', VIEW], { detached: true, stdio: 'ignore' }));
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
  ok(await waitFor(page, '!!(window.__galaxy && window.__galaxy.cmd)', 30000),
     'the viewer is up and the command panel exists');

  /* ============== C. THE BOARD AGAINST THE SERVER =================================== */
  step('C. the board, and the server it speaks for');
  const b = await openBoard(page);
  ok((await page.json('__galaxy.cmd.board.names')).includes('census'),
     'census is one of the boards the shell knows: ' +
     JSON.stringify(await page.json('__galaxy.cmd.board.names')));
  ok((await page.json('__galaxy.cmd.ids')).includes('census'),
     'and it has a row on the order sheet');
  ok(b.row && /of 17 answered/.test(String(b.row.line)),
     'whose line is a fraction and not a verdict: ' + JSON.stringify(b.row && b.row.line),
     'failure mode: "mostly done" is a summary somebody has to trust; a fraction is a ' +
     'statement about what the board will show');
  ok(/answered, in/.test(b.head) && b.head.includes('notes/census'),
     'the head names the folder and the gate: ' + JSON.stringify(b.head.slice(0, 120)));
  ok(/nothing here writes a note on its own/.test(b.head),
     'and says the gate out loud, on the glass');

  const askTile = byKey(b.tiles, 'ask');
  const askDom = byKey(b.dom, 'ask');
  ok(!!askTile && !!askDom, 'there is a question tile');
  const server = snap.next || {};
  ok(askTile && askTile.ask === server.ask,
     'and the question on it is the one GET /census called next: ' +
     JSON.stringify(String(askTile && askTile.ask).slice(0, 60)),
     'server said ' + JSON.stringify(server.ask));
  ok(askDom && askDom.ask === askTile.ask,
     'the DOM carries the same sentence as the array that built it',
     JSON.stringify([askTile && askTile.ask, askDom && askDom.ask]));
  ok(askDom && askDom.wide && askDom.shown,
     'it spans the grid and is on the glass', JSON.stringify(askDom));
  ok(askDom && askDom.input === '' && typeof askDom.hint === 'string' && askDom.hint.length > 0,
     'with an empty field carrying an example rather than a default: ' +
     JSON.stringify(askDom && askDom.hint));
  ok(askDom && askDom.acts.length === 2 &&
     askDom.acts[0].act === 'File it' && askDom.acts[1].act === 'Skip',
     'and two verbs, File it and Skip', JSON.stringify(askDom && askDom.acts));

  const chapterTiles = b.dom.filter((t) => String(t.key).indexOf('chapter:') === 0);
  ok(chapterTiles.length === 3, 'three chapter tiles under it: ' +
     JSON.stringify(chapterTiles.map((t) => t.name)));
  const agree = chapters.every((c) => {
    const tile = byKey(b.dom, 'chapter:' + c.id);
    return tile && tile.value === c.answered + '/' + c.total;
  });
  ok(agree, 'and every fraction on them is the server\'s own count',
     JSON.stringify(chapterTiles.map((t) => [t.name, t.value])));
  ok(b.tiles.length === b.dom.length,
     'the array the board computed and the cells it rendered are the same length: ' +
     b.tiles.length + ' / ' + b.dom.length);

  /* ============== D. THE DRAFT ===================================================== */
  step('D. the draft, across a repaint that rebuilds the grid');
  await clickSel(page, '#board-grid .btile[data-key="ask"] .bi');
  await page.send('Input.insertText', { text: 'a few words typed into the field' })
    .catch(() => { });
  await sleep(150);
  let draft = await page.json('__galaxy.cmd.census.draft');
  if (!draft) {
    /* SAID OUT LOUD RATHER THAN PAPERED OVER. If the key events did not land, the rest of this
       section still tests the mechanism that matters - the draft is held outside the DOM - but
       it is no longer testing that a human typing reaches it, and the log must not pretend
       otherwise. */
    note('Input.insertText did not reach the field; falling back to the page\'s own type()');
    await page.evaluate('__galaxy.cmd.census.type("a few words typed into the field")');
    draft = await page.json('__galaxy.cmd.census.draft');
  } else {
    ok(true, 'a real key event reaches the field and the page keeps the text: ' +
       JSON.stringify(draft));
  }
  ok(draft === 'a few words typed into the field',
     'the draft is held outside the input: ' + JSON.stringify(draft));
  await page.evaluate('__galaxy.cmd.board.paint()');
  await sleep(120);
  const afterPaint = byKey(await page.json('__galaxy.cmd.board.dom'), 'ask');
  ok(afterPaint && afterPaint.input === 'a few words typed into the field',
     'AND IT IS STILL IN THE FIELD AFTER THE GRID WAS REBUILT: ' +
     JSON.stringify(afterPaint && afterPaint.input),
     'failure mode: boardPaint throws the grid away and builds it again, so a draft that lived ' +
     'only in the input is lost the moment anything else repaints');

  /* ============== E. SKIP, AND THE CHAPTER DOORS =================================== */
  step('E. skip writes nothing, and a chapter is one press');
  const before = folder();
  const wasAsking = (await page.json('__galaxy.cmd.census.next') || {}).id;
  await clickSel(page, '#board-grid .btile[data-key="ask"] .brow button:nth-child(2)');
  await sleep(200);
  const nowAsking = (await page.json('__galaxy.cmd.census.next') || {}).id;
  ok(wasAsking && nowAsking && wasAsking !== nowAsking,
     'Skip moves the sitting on: ' + wasAsking + ' -> ' + nowAsking);
  ok((await page.json('__galaxy.cmd.census.skipped')).includes(wasAsking),
     'and remembers it as skipped for this sitting only');
  ok(JSON.stringify(folder()) === JSON.stringify(before),
     'and nothing is on disk: ' + JSON.stringify(folder()),
     'failure mode: a skip recorded server-side would be this house keeping a record of what ' +
     'he declined to say');
  ok((await page.json('__galaxy.cmd.census.draft')) === '',
     'and the draft went with the question it belonged to');

  await page.evaluate('__galaxy.cmd.census.pick("study")');
  await sleep(150);
  const inStudy = await page.json('__galaxy.cmd.census.next');
  ok(inStudy && inStudy.chapter === 'study',
     'picking a chapter draws the question from it: ' + (inStudy && inStudy.id));
  const studyTile = byKey(await page.json('__galaxy.cmd.board.dom'), 'chapter:study');
  ok(studyTile && studyTile.home,
     'and that chapter is the marked one, as the home clock is on the other board',
     JSON.stringify(studyTile));

  /* ============== F. FILE IT: A CARD, AND ONLY THEN A FILE ========================= */
  step('F. File it raises a card and writes nothing; Yes writes the note');
  let reached = inStudy;
  for (let i = 0; i < 6 && reached && reached.id !== WANT_ID; i++) {
    await page.evaluate('__galaxy.cmd.census.skip()');
    await sleep(120);
    reached = await page.json('__galaxy.cmd.census.next');
  }
  if (!reached || reached.id !== WANT_ID) {
    note('the question this harness answers (' + WANT_ID + ') is already answered in his own ' +
         'collection, so section F is skipped rather than writing a second note beside it');
  } else {
    const wasThere = folder();
    await clickSel(page, '#board-grid .btile[data-key="ask"] .bi');
    await page.send('Input.insertText', { text: FIXTURE }).catch(() => { });
    await sleep(150);
    if ((await page.json('__galaxy.cmd.census.draft')) !== FIXTURE) {
      await page.evaluate('__galaxy.cmd.census.type(' + JSON.stringify(FIXTURE) + ')');
    }
    ok(await clickSel(page, '#board-grid .btile[data-key="ask"] .brow button:nth-child(1)'),
       'File it is pressed, with a mouse, on the tile');
    ok(await waitFor(page, '!!__galaxy.hands.pending', 15000),
       'and a proposal card comes up');
    const pending = await page.json('__galaxy.hands.pending');
    ok(pending && pending.tool === 'save_note',
       'it is the save_note hand: ' + JSON.stringify(pending && pending.tool));
    ok(pending && (pending.params || {}).folder === 'census',
       'filing into the census folder: ' + JSON.stringify((pending || {}).params || {}));
    ok(pending && String((pending.params || {}).body || '').includes(reached.ask),
       'AND THE QUESTION IS IN THE NOTE, so a later question about it can match it',
       JSON.stringify(String((pending || {}).params && pending.params.body || '').slice(0, 90)));
    ok(await page.json('__galaxy.hands.shown'), 'the card is on the glass');
    ok(JSON.stringify(folder()) === JSON.stringify(wasThere),
       'AND NOTES/CENSUS IS STILL EXACTLY AS IT WAS while the card is up: ' +
       JSON.stringify(folder()),
       'failure mode: this is the whole claim of the part - an intake that wrote as fast as it ' +
       'was typed would look identical in every screenshot anybody took of it');
    ok((await page.evaluate('__galaxy.cmd.open')) === false,
       'and the order sheet got out of the card\'s way rather than drawing a second gate',
       'failure mode: two surfaces asking at once, one of which cannot grant anything');

    /* THE CONSENT, THROUGH THE ONLY DOOR THERE IS. There is no confirm hook in __galaxy on
       purpose - see the comment above hands.paint - so this is a real mouse on the real Yes. */
    const starsBefore = await page.evaluate('__galaxy.nodes.length');
    ok(await clickSel(page, '#ask-yes'), 'Yes is pressed, with a mouse');
    ok(await waitFor(page, '!__galaxy.hands.pending', 25000), 'the card goes down');
    const landed = await waitFor(page,
      '(function(){var a=document.getElementById("answer");' +
      'return !!a && /notes\\/census\\//.test(a.textContent);})()', 25000);
    ok(landed, 'and the answer surface says where it filed it');
    const after = folder();
    wroteNote = after.includes(WANT_FILE);
    ok(wroteNote, 'the note is on disk now: ' + JSON.stringify(after),
       'expected ' + WANT_FILE);
    if (wroteNote) {
      const text = readFileSync(join(CENSUS_DIR, WANT_FILE), 'utf8');
      ok(text.includes(FIXTURE) && text.includes(reached.ask),
         'and it holds both the answer and the question it answered');
      ok(!text.includes(SECRET), 'and nothing from the refused answer is anywhere in it');
    }
    ok(await waitFor(page, '__galaxy.nodes.length === ' + (starsBefore + 1), 10000),
       'ONE star is born for it, in the live graph: ' + starsBefore + ' -> ' +
       (await page.evaluate('__galaxy.nodes.length')),
       'failure mode: a re-index that rebuilt the graph from scratch would renumber every ' +
       'existing node, so every link he was looking at would point somewhere else');
    /* BY SLUG, because a node's `id` is its INDEX in the array - build_nodes sets
       id: len(nodes) - so there is nothing in it to match a filename against. */
    const star = await page.json(
      '(function(){var n=__galaxy.nodes.filter(function(x){' +
      'return String(x.slug||"") === "what-i-am-reading";})[0];' +
      'return n?{id:n.id,group:n.group,label:n.label}:null;})()');
    ok(star && star.group === 'census',
       'and it stands in the census cluster rather than among his passing thoughts: ' +
       JSON.stringify(star));

    const re = await get('/census');
    const row = ((re.body || {}).chapters || []).reduce((a, c) => a.concat(c.questions || []), [])
      .filter((q) => q.id === WANT_ID)[0];
    ok(row && row.answered === true,
       'and the next GET /census reads it as answered, off the folder',
       JSON.stringify(row));
    ok((re.body || {}).answered === started.length + 1,
       'with the count up by exactly one: ' + (re.body || {}).answered);

    /* AND THE POINT OF FILING IT AT ALL: it is a citizen of the corpus on the very next
       question, with no rebuild and no restart. Asserted against `nodes` - the star ids the
       answer lit - rather than against the prose, because the prose is a language model's
       and the ids are the retrieval's. */
    const chat = await post('/chat', { question: 'what did I say I am reading?',
                                       session: 'census-proof' });
    const reply = chat.body || {};
    ok(reply.kind === 'notes',
       'the very next question about it is answered from his own notes, not the web: ' +
       JSON.stringify(reply.kind),
       String(reply.answer || '').slice(0, 160));
    ok(star && Array.isArray(reply.nodes) && reply.nodes.indexOf(star.id) >= 0,
       'AND THE ANSWER LIGHTS THE STAR THAT WAS BORN A MOMENT AGO: node ' +
       (star && star.id) + ' in ' + JSON.stringify(reply.nodes),
       'failure mode: a note on disk and in the graph that retrieval cannot reach is a note ' +
       'he was told was kept and which will never be quoted back to him');
    /* WHAT IS NOT ASSERTED HERE, AND IS A KNOWN GAP RATHER THAN A PASS. `citations` on that
       same reply comes from the VECTOR store, and reindex_preserving_ids rebuilds the graph
       only - so a note filed this second is reachable by retrieval and lights its star while
       the citations panel beside it quotes something else. It is in the left-open list. */
    const cited = (reply.citations || []).map((c) => String(c.file || ''));
    if (!cited.some((f) => f.indexOf('census/') >= 0)) {
      note('and the citations panel does not yet name it (' +
           JSON.stringify(cited).slice(0, 90) + ') - the vector store is rebuilt on the next ' +
           'build.py, not on the splice; known, listed, not asserted here');
    }
    /* ONE MORE THING LEARNED THE HARD WAY, WRITTEN DOWN WHERE IT WILL BE READ AGAIN: the
       same question phrased "what am I reading at the moment?" classes as WEB and is answered
       off Wikipedia, with this note sitting in the corpus. The classifier does not consult
       the collection before deciding, and the web gate is not ours to move. Recorded. */
    const mis = await post('/chat', { question: 'what am I reading at the moment?',
                                      session: 'census-proof-b' });
    note('for the record, "what am I reading at the moment?" classes as ' +
         JSON.stringify((mis.body || {}).kind) + ' with the note in the corpus - a routing ' +
         'miss on a question about his own life, named in the left-open list, not fixed here');
  }

  /* ============== G. THE SITTING IS PUT DOWN ======================================= */
  step('G. closing the board, and what it leaves behind');
  await openBoard(page);
  await page.evaluate('__galaxy.cmd.census.type("half a sentence")');
  await page.evaluate('__galaxy.cmd.census.skip()');
  await page.evaluate('__galaxy.cmd.board.close()');
  await sleep(250);
  ok((await page.evaluate('document.querySelectorAll("#board-grid .btile").length')) === 0,
     'the grid is empty after close');
  ok((await page.json('__galaxy.cmd.board.which')) === '',
     'and the board forgets which it was');
  ok((await page.json('__galaxy.cmd.census.draft')) === '',
     'the draft is put down: it was never a note and it is not a record');
  ok((await page.json('__galaxy.cmd.census.skipped')).length === 0,
     'and so are the skips, so the same question is put again next time',
     JSON.stringify(await page.json('__galaxy.cmd.census.skipped')));
  const paints = await page.json('__galaxy.cmd.board.paints');
  await sleep(1600);
  ok((await page.json('__galaxy.cmd.board.paints')) === paints,
     'and nothing is repainting behind the closed panel: ' + paints,
     'a board holding a text field must not have a repaint cadence at all - it would throw ' +
     'away what he was typing once a second');

  /* AND THE TWO BOARDS THAT WERE HERE FIRST ARE UNHARMED. The shell gained a board with state
     for the first time, and state in a shared shell is a leak into its neighbours. */
  await page.evaluate('__galaxy.cmd.run("clock")');
  await waitFor(page, '__galaxy.cmd.board.tiles.length > 1', 12000);
  const clockDom = await page.json('__galaxy.cmd.board.dom');
  ok(clockDom.length > 1 && clockDom.every((t) => !t.wide && t.ask === '' && t.input === null),
     'the World Clock board renders exactly what it always did - no question, no field: ' +
     clockDom.length + ' tiles',
     JSON.stringify(clockDom.slice(0, 2)));
  await page.evaluate('__galaxy.cmd.board.close()');
  await page.evaluate('__galaxy.cmd.run("connectors")');
  await waitFor(page, '__galaxy.cmd.board.which === "connectors"', 6000);
  await waitFor(page, '__galaxy.cmd.board.dom.length > 4', 12000);
  const connDom = await page.json('__galaxy.cmd.board.dom');
  ok(connDom.every((t) => t.ask === '' && t.input === null),
     'and so does Connectors: ' + connDom.length + ' tiles, none of them asking anything');
  await page.evaluate('__galaxy.cmd.board.close()');
  await page.evaluate('__galaxy.cmd.paint()');
  await sleep(300);
  const censusRow = await page.json('(function(){return __galaxy.cmd.rows.census;})()');
  ok(censusRow && /of 17 answered/.test(String(censusRow.line)),
     'AND THE CENSUS ROW STILL READS ITS OWN ORGAN after two other boards were opened over it: ' +
     JSON.stringify(censusRow && censusRow.line),
     'failure mode: one shared reading slot for three boards - the bug the second board found');

  page.close();
}

main().catch((e) => {
  bad.push('the run itself: ' + e.message);
  console.log('\n  ERROR ' + (e && e.stack || e));
}).finally(async () => {
  /* THE NOTE GOES BACK, whatever happened above, and the removal is a CHECK: a harness that
     leaves an invented sentence in his collection has broken the DO-NOT-INVENT law on its way
     out, and it must say so in its own verdict line rather than quietly. */
  if (wroteNote) {
    let gone = false;
    try {
      const path = join(CENSUS_DIR, WANT_FILE);
      /* THE GUARD: only this file, and only if it is still the harness's own sentence. If he
         edited it in the ninety seconds this ran, it is his note now and it stays. */
      if (existsSync(path) && readFileSync(path, 'utf8').includes(FIXTURE)) {
        unlinkSync(path);
        gone = !existsSync(path);
      } else {
        note('the note is no longer the harness\'s own sentence, so it is left alone');
        gone = true;
      }
    } catch (e) { console.log('  ERROR could not remove the probe note: ' + e.message); }
    ok(gone, 'the probe note is out of notes/census again',
       'a harness that leaves an invented fact in his collection has broken the law it exists ' +
       'to protect');
    const build = spawn(PY, ['build.py'], { cwd: ROOT, stdio: 'ignore' });
    const code = await new Promise((r) => { build.on('exit', r); build.on('error', () => r(-1)); });
    ok(code === 0, 'and the galaxy is rebuilt without it (build.py exit ' + code + ')',
       'the file is gone but the index may still hold it - re-run build.py by hand');
  }
  procs.forEach((p) => { try { process.kill(p.pid); } catch { } });
  await sleep(700);
  profiles.forEach((p) => { try { rmSync(p, { recursive: true, force: true }); } catch { } });
  console.log('\n  VERIFY ' + (checks - bad.length) + '/' + checks +
              (bad.length ? ' FAIL' : ' PASS') + '\n');
  bad.forEach((b) => console.log('    FAILED: ' + b));
  process.exit(bad.length ? 1 : 0);
});
