/* ear_dump.mjs - THE STATE DUMP. A DIAGNOSIS, NOT A PROOF.
   ==================================================================================
   THE COMPLAINT: partway through an Open Ear conversation the machine stops hearing whole
   sentences. A turn that should carry eight words carries one, or none, and the session
   limps on looking healthy from the outside - the seal is lit, the stream is live, the
   recogniser re-arms, and the transcript is a stub.

   AT LEAST FOUR MECHANISMS PRODUCE EXACTLY THAT AND NOTHING ELSE:
     (a) a STALE OUTPUT REFERENCE, or a speakDraining left true, holding the Echo law's
         acoustic gate half-shut so the first real final of the next turn is refused as a
         leak of the butler's own voice;
     (b) a DRIFTING NOISE FLOOR under a fixed VAD threshold, so EAR_HANG_MS elapses after
         the first word and earSpeechEnd() flushes the turn while he is still talking;
     (c) a RESTART RACE - stop() is asynchronous, listening goes false in the same tick, and
         a start() inside that window throws InvalidStateError - so a new recogniser gets
         only the tail of the sentence, or none of it;
     (d) RESULT HANDLING THAT STOPS AT THE FIRST FINAL, so words after it are dropped.

   THEY ARE INDISTINGUISHABLE FROM OUTSIDE AND THEIR REPAIRS ARE OPPOSITE. So this file
   asserts almost nothing. It opens ONE session, says six sentences of four to twelve words
   into it out of the real speakers with NO REFRESH between them, and prints what the page
   recorded per turn: the recogniser's lifecycle, finals and interims, the measured noise
   floor, the acoustic gate's output reference at the arm and at its loudest, the gate's
   edges, every word the Echo law refused with its score, and words spoken against words
   heard. The one line at the bottom says whether the collapse reproduced.

   READ THE REPORT, NAME THE MECHANISM, THEN FIX THAT. A fix chosen before this table exists
   is a guess, and three of the four candidates above have a plausible-looking repair that
   would make the other three worse.

   THE ROOM IS REAL AND SO IS THE VOICE. Recognition fixtures cannot be headless and cannot
   use a fake capture device - see the nine findings in tools/mouth.mjs - so this launches a
   headed Chrome on a throwaway profile, warms the render device, and has powershell play
   piper's wave out of the speakers. THE TAB IS NOT MUTED, deliberately: half the candidate
   mechanisms are about the butler's own voice in the microphone, and a silent tab would
   prove the ear works in a room the feature was never broken in.

   NO RETRIES. mouth.speakAndHear() exists and is right for a proof; it is wrong here. A
   sentence said three times until it lands is a harness hiding the exact turn this file was
   written to photograph.

       node ear_dump.mjs                     the six-sentence session, table to stdout
       EAR_DUMP_OUT=path node ear_dump.mjs   ...and a copy of the table to a file
   ================================================================================== */

import { spawn } from 'node:child_process';
import { existsSync, mkdtempSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { Mouth, TAP, SPOKEN_FLAGS, pythonPresent } from './tools/mouth.mjs';

const GALAXY = 'http://127.0.0.1:4700';
const CDP_PORT = 9253;
const CDP = 'http://127.0.0.1:' + CDP_PORT;
const OUT = process.env.EAR_DUMP_OUT || '';
const CHROMES = ['C:/Program Files/Google/Chrome/Application/chrome.exe',
  process.env.LOCALAPPDATA + '/Google/Chrome/Application/chrome.exe'];
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

/* ---- the transcript, kept so it can be written to a file as well as read ---- */
const out = [];
const say = (s) => { out.push(s); console.log(s); };
const step = (s) => say('\n  ·· ' + s);
const note = (s) => say('  note ' + s);

/* ================================ THE SIX SENTENCES ================================
   FOUR TO TWELVE WORDS, SPREAD ACROSS THAT RANGE rather than clustered in the middle: a
   floor that has drifted up bites the long sentences first (more chances for a dip below
   EAR_VAD_OFF to last EAR_HANG_MS), and a stale reference bites whichever sentence happens
   to follow the longest answer. A set of six seven-word sentences could not tell those two
   apart.
   AND NONE OF THEM IS A CONTROL. No closer ("that's all", "goodbye"), no interrupt ("stop",
   "cancel"), and nothing that trips a hand's trigger - "remind me" would put a calendar
   proposal on the table and a gate open across the turn, which is a different fixture. Each
   one is an ordinary question that makes the butler answer OUT LOUD, because the answer is
   what the next turn has to survive. */
const ALL_SENTENCES = [
  'tell me about coffee',
  'what do you know about the roaster',
  'and what did i write about the grinder exactly',
  'and who exactly am i',
  'tell me everything the notes say about brewing coffee at home',
  'what else is in there about the beans',
  /* SIX MORE, AND THEY ANSWER A DIFFERENT QUESTION THAN THE FIRST SIX. Six turns is enough to
     photograph a collapse if one happens early; the mandate asks whether a session degrades
     over TWELVE, which is a claim about ACCUMULATION - a noise floor that creeps up a little
     each turn, a reference that goes stale once and stays stale, a recogniser restarted eleven
     times. The same four-to-twelve-word spread is kept, for the reason the first six give, and
     so is the same rule: no closers, no interrupts, and nothing that trips a hand's trigger,
     because a proposal on the table holds a gate open across the turn and that is a different
     fixture. */
  'say that again more slowly',
  'what does the checklist say about opening up',
  'and how many hours do the beans rest',
  'remind yourself what i asked you first',
  'go through what the notes say about the wholesale accounts and the deliveries',
  'is there anything else worth knowing'
];
/* TWELVE IS THE MANDATE'S NUMBER AND SIX IS THE DIAGNOSIS'S. The default stays six, so running
   this file by hand is still the two-minute photograph it was written to be; the proof that
   asserts on twelve asks for twelve. */
/* EAR_DUMP_CLOUD=1 runs the same session against the cloud service instead of the on-device
   engine, for comparison only. See where it is used. */
const CLOUD = process.env.EAR_DUMP_CLOUD === '1';
const WANT_TURNS = Math.max(1, Math.min(ALL_SENTENCES.length,
  parseInt(process.env.EAR_DUMP_TURNS || '6', 10) || 6));
const SENTENCES = ALL_SENTENCES.slice(0, WANT_TURNS);
const words = (s) => String(s || '').trim().split(/\s+/).filter(Boolean).length;
/* HOW MANY OF HIS OWN WORDS CAME BACK, which is a different number from how many words the ear
   delivered - and the difference is not small. The delivered count is what this file has always
   printed, and for a diagnosis it is the right column: a turn reading 250% is a turn where the
   room handed over two and a half times what he said, which is the butler's own answer leaking
   into the microphone or the previous turn arriving late, and a human reading the table beside
   the transcript wants to see that.

   IT IS THE WRONG NUMBER TO ASSERT ON. "heard >= 90% of spoken" is a claim about RECALL - of the
   words he said, how many survived - and a raw count can clear 90% while carrying none of them.
   The first run of the twelve-turn proof read 250%, 144%, 225%, 200% and an aggregate of 113.2%,
   which is a measurement saying nothing at all about whether he was understood.

   A MULTISET AND NOT A SET, because "say that again more slowly" has no repeats but "what do you
   know about the roaster" could, and a set intersection would score a doubled word as heard once
   and a dropped one as heard anyway. Each spoken word is matched against one unused heard word
   and then struck off. Punctuation and case go, because the recogniser's commas are its own. */
const bag = (s) => String(s || '').toLowerCase().replace(/[^a-z0-9' ]+/g, ' ')
  .trim().split(/\s+/).filter(Boolean);
function recalled(spoken, heard) {
  const pool = bag(heard);
  let hit = 0;
  for (const w of bag(spoken)) {
    const at = pool.indexOf(w);
    if (at >= 0) { pool.splice(at, 1); hit++; }
  }
  return hit;
}

/* ---- CDP, the same twenty lines every harness here uses ---- */
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
      }, 60000);
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

/* A GENUINE GESTURE. document.body.click() does not unlock audio; Chrome wants an event it
   believes came from a human, which over CDP means Input.dispatchMouseEvent. */
async function realClick(page, x, y) {
  for (const type of ['mousePressed', 'mouseReleased']) {
    await page.send('Input.dispatchMouseEvent',
      { type, x, y, button: 'left', clickCount: 1, buttons: type === 'mousePressed' ? 1 : 0 });
    await sleep(50);
  }
}

const procs = [];
function cleanup() {
  for (const p of procs) { try { p.kill(); } catch (e) { /* already gone */ } }
}

/* ---- the table. Fixed columns, because a dump nobody can scan is a log file ---- */
function pad(s, n) {
  s = String(s);
  return s.length >= n ? s.slice(0, n) : s + ' '.repeat(n - s.length);
}
function rpad(s, n) {
  s = String(s);
  return s.length >= n ? s.slice(0, n) : ' '.repeat(n - s.length) + s;
}

async function main() {
  say('\n  EAR STATE DUMP - one session, six sentences, no refresh');
  say('  ' + '='.repeat(78));

  if (!pythonPresent()) {
    say('\n  the dump cannot be taken: python is not where tools/mouth.mjs expects it');
    return 2;
  }
  const exe = CHROMES.find((p) => existsSync(p));
  if (!exe) { say('\n  the dump cannot be taken: no Chrome on this machine'); return 2; }

  const profile = mkdtempSync(join(tmpdir(), 'eardump-'));
  const chrome = spawn(exe, ['--remote-debugging-port=' + CDP_PORT,
    '--user-data-dir=' + profile, '--no-first-run', '--no-default-browser-check',
    ...SPOKEN_FLAGS, '--window-size=1280,900', '--new-window', 'about:blank'],
    { detached: true, stdio: 'ignore' });
  procs.push(chrome);

  let target = null;
  for (let i = 0; i < 100 && !target; i++) {
    try {
      target = (await (await fetch(CDP + '/json/list')).json()).find((t) => t.type === 'page');
    } catch (e) { /* not up yet */ }
    if (!target) await sleep(300);
  }
  if (!target) { say('\n  Chrome never came up on the debugging port'); return 2; }

  const page = await new Page(target.webSocketDebuggerUrl).open();
  await page.send('Runtime.enable');
  await page.send('Page.enable');
  /* BEFORE NAVIGATING, or the page's own script takes the real constructor first and the
     recogniser's lifecycle cannot be read at all. */
  await page.send('Page.addScriptToEvaluateOnNewDocument', { source: TAP });
  /* THE OTHER ENGINE, ON REQUEST AND NEVER BY DEFAULT (EAR_DUMP_CLOUD=1).
     Both engines answer through one API and neither says which it is, so "the on-device model
     hears this room worse than the service" cannot be settled by argument - only by the same
     two sentences, the same speakers and the same minutes, twice. This stubs the ONE static the
     page reads before it decides, over CDP, before navigation: the page itself is unmodified,
     because a knob added to the page for a question would outlive the question. install() is
     left alone - the page only reaches for it when available() says downloadable. */
  if (CLOUD) {
    await page.send('Page.addScriptToEvaluateOnNewDocument', {
      source: "(function () {" +
        "['SpeechRecognition', 'webkitSpeechRecognition'].forEach(function (n) {" +
        "  var R = window[n];" +
        "  if (R && typeof R.available === 'function') {" +
        "    R.available = function () { return Promise.resolve('unavailable'); };" +
        "  }" +
        "});})()"
    });
  }
  /* NOT ?mute=1. See the header: the butler has to speak, because his own voice in the
     microphone is half of what is under suspicion. */
  await page.send('Page.navigate', { url: GALAXY + '/' });
  for (let i = 0; i < 200; i++) {
    if (await page.evaluate('!!(window.__galaxy && __galaxy.ear && __galaxy.ear.dump)')
      .catch(() => false)) break;
    await sleep(250);
  }
  const hasDump = await page.evaluate('!!(window.__galaxy && __galaxy.ear && __galaxy.ear.dump)')
    .catch(() => false);
  if (!hasDump) {
    say('\n  the page has no __galaxy.ear.dump - the instrumentation is not in this viewer');
    return 2;
  }
  await page.send('Page.bringToFront');

  /* ON-DEVICE OR THE TABLE IS UNREADABLE. The cloud recogniser throttles silently and
     returns empty transcripts with no error - which is a fifth mechanism with the same
     symptom, and one that is not this project's bug. A dump taken through it would name the
     wrong culprit with total confidence. */
  let local = null;
  for (let i = 0; i < 240; i++) {
    local = await page.json('__galaxy.ear.local');
    if (local && ['available', 'no-api', 'unavailable'].indexOf(local.state) >= 0) break;
    await sleep(1000);
  }
  // THE PACK, not the engine: nothing has armed yet, so `on` cannot be true here. See below.
  note('the on-device pack: ' + JSON.stringify(local));
  if (CLOUD && (!local || local.state === 'unavailable')) {
    note('THE CLOUD HALF, ON PURPOSE (EAR_DUMP_CLOUD=1). available() has been stubbed to ' +
         '"unavailable" before navigation, so the page chooses the service the way it would on ' +
         'a machine with no pack - and the refusal below is stood down for this run only, ' +
         'because a comparison between the two engines is the one reading it would prevent.');
  } else if (!local || local.state !== 'available') {
    say('\n  REFUSING TO TAKE THE DUMP. On-device recognition is ' +
        ((local && local.state) || 'unknown') + ', so every empty turn below could be the ' +
        'cloud service\'s silent throttle rather than this page. That is a finding about ' +
        'the machine, not about the ear, and a table taken through it would be evidence ' +
        'for whichever theory read it first.');
    return 2;
  }
  const vad = await page.json('({ON: __galaxy.ear.VAD_ON, OFF: __galaxy.ear.VAD_OFF,' +
    ' FRAMES: __galaxy.ear.VAD_FRAMES, HANG_MS: __galaxy.ear.HANG_MS,' +
    ' REARM_MS: __galaxy.ear.REARM_MS, ALPHA: __galaxy.ear.FLOOR_ALPHA})');
  const law = await page.json('({SIMILARITY: __galaxy.ear.echo.SIMILARITY,' +
    ' GATE_RATIO: __galaxy.ear.echo.GATE_RATIO, TAIL_MS: __galaxy.ear.echo.TAIL_MS,' +
    ' TAIL_MIN_CHARS: __galaxy.ear.echo.TAIL_MIN_CHARS,' +
    ' GATE_HOLD_MS: __galaxy.ear.echo.GATE_HOLD_MS})');
  note('the detector : ' + JSON.stringify(vad));
  note('the echo law : ' + JSON.stringify(law));

  const mouth = Mouth(page, (m) => say(m));
  /* WARM THE ROOM BEFORE THE EAR IS OPEN - finding 5 in mouth.mjs. A browser that has never
     rendered audio itself transcribes nothing at all, and the first soundstart the service
     honours is about two seconds after .start(). */
  await mouth.warm('warming the room');

  /* THE ONE CLICK, ON THE BUTTON, WITH A REAL MOUSE. __galaxy.ear.raise() would open the
     session without ever calling unlockAudio(), and an unmuted tab that cannot speak is the
     muted tab this dump refused above wearing a different hat. */
  const box = await page.json('(function () { var b = document.getElementById("mic")' +
    '.getBoundingClientRect(); return {x: Math.round(b.left + b.width / 2),' +
    ' y: Math.round(b.top + b.height / 2)}; })()');
  await realClick(page, box.x, box.y);
  for (let i = 0; i < 80; i++) {
    if (await page.json('!!__galaxy.ear.open')) break;
    await sleep(250);
  }
  const opened = await page.json('({open: __galaxy.ear.open, opened: __galaxy.ear.opened,' +
    ' arms: __galaxy.ear.arms, analyser: __galaxy.ear.analyser,' +
    ' unlocked: __galaxy.speech.unlocked, muted: __galaxy.speech.muted})');
  note('the one click: ' + JSON.stringify(opened));
  if (!opened.open) {
    say('\n  the ear never opened; there is nothing to dump');
    return 2;
  }
  if (!opened.unlocked) {
    note('AUDIO IS STILL LOCKED - the butler will not speak, so mechanisms (a) and (c) ' +
         'cannot show themselves in this run. The table below is still real; it is just ' +
         'blind to half the suspects.');
  }

  /* WHICH ENGINE HEARD HIM - AND THE READING IS TAKEN AFTERWARDS, FURTHER DOWN, NOT HERE.
     The page publishes this as __galaxy.ear.local so a spoken harness can say in its own
     transcript whether the words stayed in the room or went to a service, and the engine is
     chosen at the ARM: the property is set on the recogniser the first time the ear arms, which
     is after this point in the file. So `on` is false here for every run that will ever exist,
     and the first version of this read sat exactly here and called it a verdict - it printed
     "THESE WORDS ARE GOING TO A SERVICE" against a page that had simply not armed yet, and I
     wrote most of a diagnosis on top of it before `tries: 0` in the same line gave it away.
     The instrument was reading the shutter again, one layer up from the last time.

     WHAT THIS LINE IS FOR, then: the pack's availability BEFORE the session, which is a real
     thing worth recording (it is what the refusal above turns on) and is not a claim about
     which engine answered. The verdict is read after the last turn, where it exists. */
  const engineAtOpen = await page.json('__galaxy.ear.local');
  note('the pack, before a single arm: ' + JSON.stringify(engineAtOpen));

  /* ================================ THE SESSION ================================ */
  const rows = [];
  for (let i = 0; i < SENTENCES.length; i++) {
    const sentence = SENTENCES[i];
    step('turn ' + (i + 1) + ' of ' + SENTENCES.length + ': "' + sentence + '" (' +
         words(sentence) + ' words)');
    const before = await page.json('({turns: __galaxy.ear.turns, arms: __galaxy.ear.arms,' +
      ' sealed: __galaxy.ear.sealed, rows: __galaxy.ear.dump.length,' +
      ' floor: __galaxy.ear.floor})');
    const dumpBefore = await page.json('__galaxy.ear.dump');
    const nBefore = dumpBefore.length ? dumpBefore[dumpBefore.length - 1].n : 0;
    const finalsBefore = (await mouth.finals()).length;
    let spoke = null, trouble = '';
    try {
      /* say() waits for an arm that will still be alive when the words arrive - and that
         wait is also what lets the previous answer finish, which is why no explicit pause
         between sentences is needed or wanted. NO RETRY: see the header.
         AND THE WAIT IS NINETY SECONDS, not mouth's default sixteen. An answer is a model
         call plus several sentences read aloud, and the first run of this file timed out
         mid-answer, never played the sentence, and recorded it as a collapsed turn. See the
         note in mouth.settledArm. */
      spoke = await mouth.say(sentence, { waitMs: 90000 });
    } catch (e) {
      trouble = String((e && e.message) || e);
      note('the mouth could not speak into this turn: ' + trouble);
    }
    /* WAIT FOR THE TURN TO END, however it ends. A turn that collapses still ends - that is
       the whole symptom - so this waits for the page's own turn counter to move and gives up
       rather than retrying when it does not. */
    const deadline = Date.now() + 30000;
    let after = before;
    while (Date.now() < deadline) {
      after = await page.json('({turns: __galaxy.ear.turns, arms: __galaxy.ear.arms,' +
        ' sealed: __galaxy.ear.sealed, rows: __galaxy.ear.dump.length,' +
        ' floor: __galaxy.ear.floor})');
      if (after.turns > before.turns) break;
      await sleep(300);
    }
    rows.push({
      n: i + 1, sentence, spokenWords: words(sentence), nBefore, finalsBefore,
      armsUsed: after.arms - before.arms, turnsAdded: after.turns - before.turns,
      sealedAdded: after.sealed - before.sealed, trouble,
      ended: after.turns > before.turns
    });
    say('       spoken   : ' + words(sentence) + ' words · "' + sentence + '"');
    if (!rows[i].ended) {
      say('       THE TURN NEVER ENDED. Thirty seconds after the sentence was played the ' +
          'page\'s turn counter had not moved: nothing was flushed and nothing was asked.');
    }
  }
  /* AND THEN WAIT FOR THE LAST TURN'S FINAL, which the loop above cannot wait for.
     Every turn's wait ends when the page's turn counter moves. For turns 1..n-1 that is late
     enough by accident: the NEXT turn's say() spends seconds arming and speaking, and the
     final lands during it. For turn n there is no next turn, so the dump is read the instant
     the counter moves - and the header below says in its own words why that is too early:
     THE FINAL ARRIVES AFTER THE FLUSH THAT ENDS THE TURN. The first twelve-turn run with a
     real recall measure read turn 12 as 0 of 6 words with nothing delivered at all, while the
     browser tap showed its interims still arriving one line above the table. That was not the
     ear collapsing on a long session - it was this harness photographing the shutter.

     BOUNDED, AND LOUD IF IT EXPIRES. This waits for the last turn's own dump row to carry a
     transcript, for at most fifteen seconds, and says so if it never does - a turn that truly
     delivered nothing must still be able to read as nothing. It does NOT loosen anything: the
     words are still the words the page reports, judged against the sentence he said. */
  {
    const last = rows[rows.length - 1];
    const deadline = Date.now() + 15000;
    let got = '';
    while (Date.now() < deadline) {
      const now = await page.json('__galaxy.ear.dump');
      got = now.filter((d) => d.n > last.nBefore).map((d) => d.heard)
        .filter(Boolean).join(' ').trim();
      if (got) break;
      await sleep(300);
    }
    if (got) {
      say('');
      say('  the last turn’s transcript landed after its flush, as it always does - waited ' +
          'for it before reading the dump');
    } else {
      note('the last turn delivered no transcript even after fifteen seconds of waiting, so ' +
           'its nought is the ear’s and not the shutter’s');
    }
  }
  /* AND NOW THE ENGINE, WHICH IS A READING AND NOT A HOPE. Taken after the last turn, because
     the property is set at the arm and the arms are all behind us: whatever this says is what
     heard the twelve sentences above. The cloud recogniser throttles silently and raises no
     error - it fires audiostart, soundstart and speechstart into a loud room and hands back one
     word or none - so a low table under a cloud reading is not evidence about this page. */
  const engine = await page.json('__galaxy.ear.local');
  note('the engine that heard him: ' + JSON.stringify(engine));
  if (!engine || engine.on !== true) {
    note('THESE WORDS WENT TO A SERVICE AND DID NOT STAY IN THE ROOM (' +
         ((engine && engine.state) || 'unknown') + (engine && engine.why ? ', ' + engine.why
         : '') + '). It throttles without raising, so every recognition number in this run is ' +
         'UNTRUSTWORTHY until the same run is made with processLocally taken.');
  }
  mouth.unwatch();

  /* ================================ THE ROWS, READ WHOLE ================================
     ONE READ, AT THE END, AND THE FIRST RUN OF THIS FILE PROVES WHY. The rows were read
     mid-session, one turn at a time, immediately after the page's turn counter moved - and
     the recogniser's FINAL for a turn arrives AFTER the flush that ends it, because the
     flush is what calls stop() and stop() is what makes the recogniser hand over what it was
     holding. So every arm was photographed before its own final landed, every row said "0
     final", and "this page never consumes a final" was about to be written up as a finding
     off a measurement that could not have recorded one. The session's own numbers disagreed
     with the browser's tap - four finals there, none here - and that disagreement was the
     only thing that caught it. A dump is read once, when there is nothing left to arrive. */
  const dump = await page.json('__galaxy.ear.dump');
  for (const r of rows) {
    /* THE ARMS THIS SENTENCE LIVED IN, taken by the dump's own counter rather than by list
       length: the ring is capped, so length stops being a mark once it is full, and a
       harness measuring its own cap is the defect routing_proof already paid for once. */
    const mine = dump.filter((d) => d.n > r.nBefore &&
      (r.n === rows.length || d.n <= rows[r.n].nBefore));
    r.dumpRows = mine.length ? mine : [];
    r.finals = (await mouth.finals()).slice(r.finalsBefore,
      r.n === rows.length ? undefined : rows[r.n].finalsBefore);
    r.heard = r.dumpRows.map((d) => d.heard).filter(Boolean).join(' ').trim();
    r.heardWords = words(r.heard);
    /* BOTH NUMBERS ARE KEPT. heardWords is what the room delivered and recalledWords is how much
       of it was his - see recalled() above. The table prints both and the proof asserts on the
       second, because only one of them is a claim about being understood. */
    r.recalledWords = recalled(r.sentence, r.heard);
  }

  say('\n  ' + '='.repeat(78));
  say('  THE ARMS, TURN BY TURN, READ AFTER THE SESSION');
  for (const r of rows) {
    say('\n  turn ' + r.n + ': "' + r.sentence + '"');
    say('       spoken   : ' + r.spokenWords + ' words');
    say('       heard    : ' + r.heardWords + ' words · "' + r.heard + '"');
    say('       recognised by the browser: ' + JSON.stringify(r.finals));
    if (r.trouble) say('       the mouth could not speak: ' + r.trouble);
    for (const d of r.dumpRows) {
      say('       arm #' + d.n + ' (' + d.why + ')');
      say('         lifecycle  : ' + d.life.join(' -> '));
      say('         results    : ' + d.finals + ' final, ' + d.interims + ' interim, ' +
          d.finalChars + ' final chars · ' + d.sealedLate + ' late word(s) sealed off');
      say('         flags@arm  : draining=' + d.draining + ' queued=' + d.queued +
          ' busy=' + d.busy + ' sealed=' + d.sealed);
      say('         floor      : ' + d.floorAtArm + ' at the arm, ' + d.floorMax +
          ' at its highest (VAD_OFF is ' + vad.OFF + ', VAD_ON is ' + vad.ON + ')');
      say('         output ref : ' + d.refAtArm + ' at the arm (from ' + d.refFromAtArm +
          '), ' + d.refMax + ' at its loudest · ' + d.ttsLiveFrames +
          ' frame(s) with the engine speaking');
      say('         input peak : ' + d.inputMax);
      say('         gate edges : ' + d.gateOpened + ' open, ' + d.gateShut + ' shut');
      say('         VAD        : ' + d.speeches + ' speech start(s), ' + d.ends + ' end(s)');
      say('         echo law   : ' + d.dropped + ' refused' +
          (d.drops && d.drops.length
            ? '\n' + d.drops.map((x) => '                        layer ' + x.layer +
                ' sim ' + x.similarity + ' gate=' + x.gate + ' "' + x.text + '" · ' + x.why)
              .join('\n')
            : ''));
      say('         flushed by : ' + (d.flushWhy || '(still open)') + ' carrying ' +
          d.words + ' word(s)');
    }
    if (!r.ended) say('       and the turn never ended: nothing was flushed, nothing asked.');
  }

  /* ================================ THE TABLE ================================ */
  say('\n  ' + '='.repeat(78));
  say('  WORDS SPOKEN AGAINST WORDS HEARD, TURN BY TURN');
  say('  ' + '-'.repeat(78));
  say('  ' + pad('turn', 5) + rpad('said', 5) + rpad('heard', 7) + rpad('his', 5) +
      rpad('%', 6) + rpad('arms', 6) + rpad('fin', 5) + rpad('int', 5) + '  ' + 'sentence');
  let collapsed = 0;
  for (const r of rows) {
    /* THE PERCENTAGE IS RECALL and not delivery - see recalled(). It was the delivered count
       until a twelve-turn run printed 250% for a turn nobody could have understood. */
    const pct = r.spokenWords ? Math.round(100 * r.recalledWords / r.spokenWords) : 0;
    const fin = r.dumpRows.reduce((a, d) => a + d.finals, 0);
    const intm = r.dumpRows.reduce((a, d) => a + d.interims, 0);
    /* THE COLLAPSE, DEFINED BEFORE IT IS COUNTED so the definition cannot be chosen to suit
       the result: the mandate's own two tests, under 90% of the words or under three words
       from a sentence that carried four or more. */
    const bad = pct < 90 || (r.recalledWords < 3 && r.spokenWords >= 4);
    if (bad) collapsed++;
    say('  ' + pad((bad ? '*' : ' ') + r.n, 5) + rpad(r.spokenWords, 5) +
        rpad(r.heardWords, 7) + rpad(r.recalledWords, 5) + rpad(pct + '%', 6) +
        rpad(r.armsUsed, 6) +
        rpad(fin, 5) + rpad(intm, 5) + '  ' + r.sentence.slice(0, 40));
  }
  say('  ' + '-'.repeat(78));
  say('  * = under 90% of HIS words came back, or under three of them from a sentence of four');
  say('  said = what he spoke · heard = what the room delivered · his = how many were his');

  const floor = await page.json('({floor: __galaxy.ear.floor, frames: __galaxy.ear.floorFrames})');
  const gate = await page.json('__galaxy.ear.echo.gate');
  const state = await page.json('__galaxy.ear.echo.state');
  const shape = await page.json('({opened: __galaxy.ear.opened, turns: __galaxy.ear.turns,' +
    ' arms: __galaxy.ear.arms, rearms: __galaxy.ear.rearms, sealed: __galaxy.ear.sealed,' +
    ' sealExpired: __galaxy.ear.sealExpired, hardErrors: __galaxy.ear.hardErrors,' +
    ' bargeIns: __galaxy.ear.bargeIns})');
  const tap = await mouth.tap();
  say('\n  THE SESSION, WHOLE');
  say('  the shape        : ' + JSON.stringify(shape));
  say('  the floor at end : ' + JSON.stringify(floor));
  say('  the gate at end  : ' + JSON.stringify(gate));
  say('  the echo law     : ' + JSON.stringify(state));
  say('  the browser\'s own: ' + JSON.stringify({ built: tap.built, starts: tap.starts,
    stops: tap.stops, aborts: tap.aborts, live: tap.live,
    finals: tap.finals.length, interims: tap.interims.length,
    errors: tap.errors.map((e) => e.e) }));
  say('\n  THE RECOGNISER\'S OWN TIMELINE, whole session');
  for (const l of (await mouth.timeline(0))) say('    ' + l);

  say('\n  ' + '='.repeat(78));
  if (shape.opened !== 1) {
    say('  THE SESSION WAS NOT ONE SESSION (' + shape.opened + ' opens). Every claim about ' +
        'a conversation degrading over its own length is void; re-run.');
  } else if (collapsed) {
    say('  REPRODUCED: ' + collapsed + ' of ' + rows.length + ' turns collapsed inside one ' +
        'session with no refresh. The named mechanism is whichever column above changed ' +
        'between a good turn and a bad one - read it, then fix that and nothing else.');
  } else {
    say('  NOT REPRODUCED: all ' + rows.length + ' turns carried at least 90% of their ' +
        'words in one session. That is the finding, and it is reported as one rather than ' +
        'repaired: there is no evidence here for any of the four mechanisms, and a fix ' +
        'applied to this table would be a guess with a table stapled to it.');
  }
  say('  ' + '='.repeat(78) + '\n');
  /* TAGGED AND MACHINE-READABLE, for the caller that asserts rather than reads. session_proof's
     spoken half spawns this file and judges the table; it is handed the numbers rather than
     asked to parse the columns above, because a proof that re-derives its evidence out of
     another file's formatting is a proof that breaks when a column is widened. */
  say('EARDUMP ' + JSON.stringify({
    opened: shape.opened, turns: rows.length, collapsed,
    rows: rows.map((r) => ({
      n: r.n, said: r.spokenWords, delivered: r.heardWords, heard: r.recalledWords,
      pct: r.spokenWords ? Math.round(100 * r.recalledWords / r.spokenWords) : 0,
      arms: r.armsUsed, ended: !!r.ended, sentence: r.sentence
    })),
    engine: engine || { on: false, state: 'unread' },
    shape, floor, gate
  }));
  return collapsed ? 1 : 0;
}

const watchdog = setTimeout(() => {
  say('\n  the dump ran out of patience (9 minutes) - whatever is above is what there is\n');
  if (OUT) { try { writeFileSync(OUT, out.join('\n') + '\n'); } catch (e) { /**/ } }
  cleanup();
  process.exit(3);
}, 540000);

let code = 0;
try {
  code = await main();
} catch (e) {
  say('\n  the dump broke: ' + ((e && e.stack) || e) + '\n');
  code = 3;
}
clearTimeout(watchdog);
if (OUT) {
  try { writeFileSync(OUT, out.join('\n') + '\n'); say('  written to ' + OUT); }
  catch (e) { say('  could not write ' + OUT + ': ' + e.message); }
}
cleanup();
process.exit(code);
