/* mouth.mjs - THE HARNESS'S VOICE.
   ==================================================================================
   The mandate: "every behavioural fixture runs twice - typed, for determinism, and spoken
   through the real microphone via the Open Ear, with real recognition, colloquial and
   messy." This is the second half. It says a sentence OUT LOUD, out of the machine's
   speakers, and the page's own webkitSpeechRecognition hears it off the microphone array
   and hands the words to heardFinal() - the same door a human voice uses, unassisted.

   EVERY LINE OF THE RECIPE BELOW WAS MEASURED across twenty spikes, and most of it is
   counter-intuitive enough that it would never have been guessed. The findings, in the
   order they bite:

   1. --use-file-for-fake-audio-capture DOES NOT REACH THE RECOGNISER. It reaches
      getUserMedia perfectly (track "Fake Default Audio Input", 48 kHz, analyser shows the
      utterance), and Chrome's speech input opens the system default device instead, so with
      the fake file armed the recogniser fires audiostart and speechstart and returns zero
      results and zero errors. --headless=new returns nothing either. Hence: a real room.
   2. THE SENTENCE IS PLAYED BY ANOTHER PROCESS, not by Chrome. Chrome's echo canceller
      treats audio Chrome rendered as its own and cancels it: with the page's ear open, an
      internally-played fixture read 0.0256 on the page's own analyser against a 0.0269
      silence floor - identical to silence. Played by powershell it read 0.1723. An external
      speaker source is not in the AEC's render reference and cannot be cancelled, which is
      also the honest simulation: a person in the chair is not in it either.
   3. PROCESSED CAPTURE IS FINE. echoCancellation + noiseSuppression + autoGainControl all
      true - what PART C requires - transcribes as reliably as raw capture. That was worth
      checking, because a noise suppressor is exactly the thing that would eat a far-field
      synthetic voice, and it does not.
   4. THE WAVE HAS TO BE COMPRESSED. Piper's output peaks at full scale and still measures
      0.027 RMS in the room, because speech is mostly quiet. utter.py RMS-normalises to 0.22
      through a tanh limiter, which is what moved the page's analyser from 0.027 to 0.17.
   5. THE RENDER DEVICE MUST BE WARM AND THE RECOGNISER MUST BE SETTLED, in that order.
      Arming and speaking at once yields nothing at all - the words land before the service
      is listening. The measured distance from .start() to audiostart is ~150ms and from
      .start() to the first soundstart it will honour is ~2s. Both are in warm() and in the
      settled-arm wait in say().
   6. IT IS FLAKY, AND THAT IS NOT NEGOTIABLE AWAY. One run in eight of the known-good
      recipe returns an empty transcript with no error - a cloud service, on a laptop
      microphone, in a room. So say() RETRIES. A spoken fixture that did not retry would be
      a harness that fails for reasons that have nothing to do with this code, and the whole
      suite would be distrusted because of it.
   7. THE CLOUD SERVICE THROTTLES SILENTLY, AND EVERY "TURN TWO IS DEAF" SYMPTOM WAS THIS.
      The cloud recogniser stops returning results after some number of sessions and RAISES
      NO ERROR: audiostart, soundstart and speechstart all fire into a room the analyser
      reads at 0.4, and nothing comes back. Proof: spike 19, UNCHANGED between runs, scored
      6 of 6, then 1 of 6, then 1 of 6 inside forty minutes.
      THIS IS ALSO A WARNING ABOUT READING SPIKES. Under that throttle I measured "a spent
      recogniser is deaf" (fresh instances heard, reused ones did not), believed it, and
      edited the page's startListening() to retire and rebuild per arm. It was an artefact of
      the quota draining across the run: re-run on-device, reuse scored fresh=true
      reuse=true reuse-far=true fresh-again=true. The edit was reverted; reuse stays. A
      platform finding taken during a throttle is not a finding. The page now asks for
      on-device recognition, which has no quota behind it and keeps the words in the room -
      so a spoken fixture WAITS for __galaxy.ear.local.state === 'available' and records
      which engine it used, or a null transcript in the lookbook is unreadable evidence.
   8. ?mute=1 SUPPRESSES THE speakLine EVENT. index.html raises the caption, records the
      line, and RETURNS before dispatching the event when the tab is muted - so a harness
      that watches the event to mean "he answered" reports a silent false negative on a
      muted tab, which is every live harness we have. The observable that survives mute is
      __galaxy.speech.said. It has a six-second TTL, so it is polled and accumulated HERE,
      in Node, where nothing expires.
   9. THE TRANSCRIPT CANNOT BE READ OUT OF THE PAGE AFTERWARDS. phraseBuffer is cleared in
      the same task that spends it, so polling __galaxy.ear.buffer at 60ms caught nothing
      even on utterances that routed correctly. The words are taken from TAP below - a
      wrapper around webkitSpeechRecognition installed before the page's own script runs -
      which is also the only honest place to take them from: the page still keeps nothing,
      and ear.kept.transcript stays the zero that proves it.

   WHAT IT REFUSES TO DO. It does not call feedFinal. The typed pass already proves the
   funnel behind that door; a spoken pass that used the same door would prove nothing new
   and would be a lie in the lookbook. If the room fails, speakAndHear() reports that it
   failed.  */

import { spawnSync } from 'node:child_process';
import { existsSync } from 'node:fs';

const PY = 'C:/Users/Fullstack Developer/AppData/Local/Programs/Python/Python313/python.exe';
const UTTER = 'tools/utter.py';

/* Measured: .start() to audiostart is ~150ms, but the first soundstart the service will
   honour is ~2s in. 1800ms plus the arm-stability check in say() is what made turns two and
   three land; 1600 without the check played into arms that were about to die. */
const SETTLE_MS = 1800;
const HEARD_TIMEOUT_MS = 12000;
const TRIES = 3;                  // finding 6
const SAID_POLL_MS = 250;         // well inside the page's six-second said TTL (finding 8)

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

/* ================================ THE TAP ================================
   Install with Page.addScriptToEvaluateOnNewDocument BEFORE navigating, or the page's own
   script captures the real constructor first and this sees nothing. It is a pure observer:
   it adds listeners and counts calls, and hands every event straight through.  */
export const TAP = `(function () {
  window.__tap = { built: 0, starts: 0, stops: 0, aborts: 0, live: 0,
                   ev: [], finals: [], interims: [], errors: [], lang: null };
  var Real = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!Real) { window.__tap.absent = true; return; }
  var seq = 0;
  function Tapped() {
    var r = new Real(), t = window.__tap, mine = ++seq;
    t.built++;
    ['start','audiostart','soundstart','speechstart','speechend','soundend','audioend',
     'end','nomatch'].forEach(function (n) {
      r.addEventListener(n, function () {
        t.ev.push({ at: Date.now(), n: n, r: mine });
        if (n === 'start') t.live++;
        if (n === 'end') t.live--;
      });
    });
    r.addEventListener('error', function (e) {
      t.ev.push({ at: Date.now(), n: 'error:' + e.error, r: mine });
      t.errors.push({ at: Date.now(), e: e.error, r: mine });
    });
    r.addEventListener('result', function (e) {
      for (var i = e.resultIndex; i < e.results.length; i++) {
        var row = { at: Date.now(), t: e.results[i][0].transcript, r: mine };
        if (e.results[i].isFinal) t.finals.push(row); else t.interims.push(row);
        t.ev.push({ at: row.at, r: mine,
          n: (e.results[i].isFinal ? 'FINAL "' : 'interim "') + row.t + '"' });
      }
    });
    var s = r.start.bind(r), p = r.stop.bind(r), a = r.abort.bind(r);
    r.start = function () { t.starts++; t.lang = r.lang;
      t.ev.push({ at: Date.now(), n: '.start()', r: mine }); return s(); };
    r.stop = function () { t.stops++;
      t.ev.push({ at: Date.now(), n: '.stop()', r: mine }); return p(); };
    r.abort = function () { t.aborts++;
      t.ev.push({ at: Date.now(), n: '.abort()', r: mine }); return a(); };
    return r;
  }
  /* THE STATICS HAVE TO COME ACROSS. available() and install() - the on-device API - live
     on the constructor, and a tap that replaced the global with a bare function silently
     took them away: the page then reported "this build has no SpeechRecognition.available()"
     and fell back to the throttled cloud service, WHICH IS A BUG THE HARNESS CAUSED IN THE
     THING IT WAS MEASURING. Forwarded rather than copied, so the browser still receives the
     real constructor as its receiver. */
  ['available', 'install'].forEach(function (n) {
    if (typeof Real[n] === 'function') {
      Tapped[n] = function () { return Real[n].apply(Real, arguments); };
    }
  });
  window.webkitSpeechRecognition = Tapped;
  window.SpeechRecognition = Tapped;
})()`;

/* ---- piper, once per distinct sentence, cached on disk ---- */
export function synthesise(text, opts) {
  const args = [UTTER];
  if (opts && opts.device) args.push('--device');
  if (opts && opts.gain) args.push('--gain', String(opts.gain));
  args.push('-', text);
  const r = spawnSync(PY, args, { encoding: 'utf8' });
  const line = String(r.stdout || '').split(/\r?\n/).find((l) => l.startsWith('UTTER '));
  if (!line) {
    throw new Error('utter.py said nothing usable for ' + JSON.stringify(text) +
      ': ' + (r.stderr || r.stdout || r.error || '').toString().slice(0, 400));
  }
  return JSON.parse(line.slice(6));
}

/* ---- the speakers, out of Chrome's reach (finding 2) ---- */
function playSync(path) {
  const r = spawnSync('powershell', ['-NoProfile', '-Command',
    "(New-Object Media.SoundPlayer '" + String(path).replace(/\\/g, '/') + "').PlaySync()"],
    { encoding: 'utf8' });
  if (r.status !== 0) {
    throw new Error('the speakers refused ' + path + ': ' + (r.stderr || r.status));
  }
  return true;
}

export function Mouth(page, log) {
  const note = log || (() => { });
  const said = [];                 // what the mouth spoke
  const lines = [];                // what the page said back, accumulated (finding 8)
  const seen = new Set();
  let poller = null;
  let warmed = false;

  async function tap() {
    const t = await page.json('window.__tap || null');
    if (!t) {
      throw new Error('the recogniser tap is not installed: send ' +
        'Page.addScriptToEvaluateOnNewDocument with mouth.TAP BEFORE navigating, or the ' +
        'page captures the real constructor first and no transcript can be read at all');
    }
    return t;
  }

  /* THE PAGE'S OWN WORDS, KEPT OUTSIDE IT. __galaxy.speech.said drops lines after six
     seconds; this poll is four times faster than that. The failure mode it catches: an
     answer that arrived and aged out between two reads, reported as "he never answered". */
  function watch() {
    if (poller) return false;
    poller = setInterval(async () => {
      try {
        for (const l of (await page.json('__galaxy.speech.said')) || []) {
          const key = l.at + '|' + l.text;
          if (!seen.has(key)) { seen.add(key); lines.push(l); }
        }
      } catch (e) { /* navigating, or gone */ }
    }, SAID_POLL_MS);
    return true;
  }
  function unwatch() { if (poller) { clearInterval(poller); poller = null; } }

  /* WARM THE ROOM BEFORE THE EAR IS OPEN (finding 5). */
  async function warm(text) {
    if (warmed) return false;
    watch();
    /* CHROME HAS TO HAVE RENDERED SOMETHING ITSELF. Every spike that produced a transcript
       had Chrome render audio before the recogniser was armed; every one that armed into a
       browser which had never opened its render device produced nothing - no results, no
       errors. Half a second of 1 kHz at a sixth of full scale is enough. It is played
       through userGesture, not through --autoplay-policy, so the page under test keeps its
       own audio-unlock semantics: a harness must not hand the page a privilege the boss's
       own click has to earn. */
    const before = await page.evaluate(`(function () {
      var c = new (window.AudioContext || window.webkitAudioContext)();
      var o = c.createOscillator(), g = c.createGain();
      o.frequency.value = 1000; g.gain.value = 0.15;
      o.connect(g); g.connect(c.destination);
      o.start(); o.stop(c.currentTime + 0.5);
      window.__mouthWarmCtx = c;
      return c.state;
    })()`, true);
    await sleep(900);
    const state = await page.json('window.__mouthWarmCtx.state');
    if (state !== 'running') {
      throw new Error('the warm tone never played (AudioContext ' + before + ' -> ' + state +
        '); without it the recogniser hears nothing and says nothing');
    }
    const w = synthesise(text || 'warming the room');
    playSync(w.path);
    warmed = true;
    note('   the room warmed - a 1kHz tone from Chrome and "' + w.text +
         '" from the speakers - before the ear was opened');
    return true;
  }

  /* WAIT FOR AN ARM THAT WILL STILL BE ALIVE WHEN THE WORDS ARRIVE.
     THE FAILURE MODE THIS CATCHES, and it cost two days: __galaxy.ear.listening is true from
     the recogniser's onstart, but a session that is one tick from its own no-speech timeout
     is also "listening". Speaking into it returns no transcript AND no error - a silent
     false negative indistinguishable from a routing bug. So: wait for listening, note WHICH
     arm it is, settle, then check the arm did not change underneath. If it did, that session
     died during the settle and this one gets the full settle of its own. */
  async function settledArm(settleMs) {
    for (let round = 0; round < 8; round++) {
      let live = null;
      for (let i = 0; i < 80 && !live; i++) {
        const s = await page.json('({listening: !!__galaxy.ear.listening,' +
          ' analyser: !!__galaxy.ear.analyser, arms: __galaxy.ear.arms, open: !!__galaxy.ear.open})');
        if (!s.open) throw new Error('the ear closed; there is nothing to speak into');
        if (s.listening && s.analyser) live = s; else await sleep(200);
      }
      if (!live) throw new Error('the ear is not listening; there is nothing to speak into');
      await sleep(settleMs);
      const now = await page.json('({listening: !!__galaxy.ear.listening, arms: __galaxy.ear.arms})');
      if (now.listening && now.arms === live.arms) return live.arms;
    }
    throw new Error('the recogniser re-armed eight times without ever settling; ' +
      'something is tearing it down (see __tap.ev)');
  }

  /* One utterance. Speaks it and reports what it did - it does NOT decide whether the page
     heard it; that is the caller's assertion. */
  async function say(text, opts) {
    const o = opts || {};
    watch();
    const wav = synthesise(text, o);
    let arm = null;
    if (o.waitForEar !== false) {
      arm = await settledArm(o.settleMs == null ? SETTLE_MS : o.settleMs);
    }
    playSync(wav.path);
    said.push({ text: text, seconds: wav.seconds, path: wav.path, arm: arm });
    note('   spoken aloud: "' + text + '" (' + wav.seconds + 's, ' +
      (wav.cached ? 'cached' : 'fresh') + (arm == null ? '' : ', into arm ' + arm) + ')');
    return { text: text, seconds: wav.seconds, path: wav.path, arm: arm };
  }

  /* Says it, then waits for the page to have HEARD it - and says it again if the service
     came back empty (finding 6). `hear` is the caller's own reader, so "heard" means
     whatever the fixture is about, never merely "a transcript arrived". */
  async function speakAndHear(text, hear, opts) {
    const o = opts || {};
    const tries = o.tries || TRIES;
    for (let attempt = 1; attempt <= tries; attempt++) {
      const mark = (await tap()).finals.length;
      await say(text, o);
      const deadline = Date.now() + (o.timeoutMs || HEARD_TIMEOUT_MS);
      while (Date.now() < deadline) {
        const got = await hear();
        if (got) {
          return { ok: true, attempts: attempt, heard: got,
                   transcript: (await finals()).slice(mark) };
        }
        await sleep(250);
      }
      const partial = (await finals()).slice(mark);
      note('   attempt ' + attempt + ' of ' + tries + ': the room gave back ' +
        (partial.length ? JSON.stringify(partial) : 'nothing at all'));
    }
    return { ok: false, attempts: tries, heard: null, transcript: [] };
  }

  /* What the recogniser actually made of it, for the lookbook's spoken column. */
  async function finals() { return (await tap()).finals.map((f) => f.t); }
  async function lastPhrase() { const f = await finals(); return f.length ? f[f.length - 1] : null; }

  /* The page's own lines, and the ones since a mark. */
  function saidLines() { return lines.slice(); }
  function saidSince(mark) { return lines.slice(mark); }
  function saidMark() { return lines.length; }

  /* The recogniser's timeline, human-readable, for a transcript in the lookbook or for
     working out why a spoken fixture failed. */
  async function timeline(sinceMs) {
    const t = await tap();
    const cut = sinceMs ? Date.now() - sinceMs : 0;
    return t.ev.filter((e) => e.at >= cut)
      .map((e) => 'r' + e.r + ' ' + e.n);
  }

  return { TAP, watch, unwatch, warm, say, speakAndHear, finals, lastPhrase, timeline,
           saidLines, saidSince, saidMark, tap,
           get said() { return said.slice(); } };
}

/* The flags a spoken fixture's Chrome needs. A harness that forgets one of these does not
   fail loudly - it falls back to a silent room and reports "no transcript" as though the
   page were at fault. HEADED IS NOT OPTIONAL: --headless=new returns no transcripts. */
export const SPOKEN_FLAGS = ['--use-fake-ui-for-media-stream'];

export function pythonPresent() { return existsSync(PY); }
