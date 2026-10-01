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
    /* AND FINDING 9 FIRST, BECAUSE A MUTED SPEAKER IS NOT A ROOM. See ensureRoom below: this
       desk's render endpoint is found muted again and again, and every spoken fixture in the
       project reads that as a page that cannot hear. */
    ensureRoom(note);
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
  async function settledArm(settleMs, waitMs) {
    /* HOW LONG "WAIT FOR THE EAR" IS ALLOWED TO BE, and it is a parameter because the right
       answer depends on what came before.
       THE FAILURE MODE THIS CATCHES, measured in the first ear_dump run: the ear is shut for
       the whole of an answer - the question is posted, a model answers it, and piper reads
       several sentences at length-scale 1.05 - and a long answer takes well over sixteen
       seconds end to end. A fixed sixteen-second wait expired while the butler was still
       talking, this threw "the ear is not listening", the sentence was NEVER PLAYED, and the
       turn was then recorded as eleven words spoken and none heard. That is a harness
       running out of patience wearing the exact costume of the defect the fixture was
       written to find, and it would have been written up as one: the tell is in the dump,
       where that arm shows an input peak of 0.043 against a floor of 0.006 and zero VAD
       speech starts - a silent room, not a deaf ear. So a fixture that speaks after an
       answer must say how long an answer may take. */
    const budget = waitMs > 0 ? waitMs : 16000;
    const polls = Math.max(1, Math.round(budget / 200));
    for (let round = 0; round < 8; round++) {
      let live = null;
      for (let i = 0; i < polls && !live; i++) {
        const s = await page.json('({listening: !!__galaxy.ear.listening,' +
          ' analyser: !!__galaxy.ear.analyser, arms: __galaxy.ear.arms, open: !!__galaxy.ear.open})');
        if (!s.open) throw new Error('the ear closed; there is nothing to speak into');
        if (s.listening && s.analyser) live = s; else await sleep(200);
      }
      if (!live) {
        throw new Error('the ear is not listening after ' + Math.round(budget / 1000) +
          's; there is nothing to speak into (if an answer was being read, the budget is ' +
          'too short - pass waitMs)');
      }
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
      arm = await settledArm(o.settleMs == null ? SETTLE_MS : o.settleMs, o.waitMs);
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
/* ---------------------------------------------------------------------------------------
   FINDING 9, AND IT INVALIDATED A DAY OF CONCLUSIONS: THE RENDER ENDPOINT IS FOUND MUTED.
   Not wound down - MUTED, repeatedly, by something outside this project. It was found at 2%
   and muted; raised to 90% and unmuted; and read again hours later at 92% AND MUTED. Nothing
   in this repository calls SetMute except the four diagnostics in _runs/, and Windows'
   communications ducking is off (UserDuckingPreference 3, "do nothing"). So it comes back on
   its own, and a spoken harness that checks the room once at the top of a twenty-minute sweep
   is checking a fact that expires.

   WHY THIS WAS NOT CAUGHT FOR SO LONG, and it is worth writing down because the instrument
   lied with a straight face: _runs/_playprobe.ps1 plays a wav and reports the render PEAK
   METER, and that meter reports the session's stream level WITHOUT REGARD TO MUTE. Measured,
   both ways, one minute apart: muted, RENDER PEAK 0.7303; unmuted, RENDER PEAK 0.6403. The
   probe printed "the room carried it" on a device that was outputting silence. On the strength
   of that one number the acoustic loop was written off as a property of this desk.

   WHAT IT ACTUALLY COSTS. With the endpoint unmuted and no other process holding the
   microphone, _runs/_aecprobe.mjs reads the page's own analyser at 1.0000 while the sentence
   plays against a 0.0168 quiet-room floor - a ratio of 59.5, which is clipping. The same probe
   with the endpoint muted and two leaked harness Chromes on the microphone read 0.0391 against
   a 0.0378 floor, which is silence. Same desk, same speakers, same wav.

   SO THIS RAISES IT, AND PUTS IT BACK. The level belongs to the employer and not to a test,
   so the previous value and mute state are captured and restored on process exit - including
   an exit by exception, which is the case that matters, because that is how the room got left
   at 90% unmuted in a room the employer was sitting in.
   FAILURE MODE IF THIS IS REMOVED: every spoken fixture reports an empty transcript, the empty
   transcript is read as a defect in the ear, the funnel or the recogniser, and the conclusion
   drawn is that the machine cannot do it. The machine can. The speaker was off.
   --------------------------------------------------------------------------------------- */
const ROOM_FLOOR_PCT = 55;      // below this a far-field synthetic voice does not survive the room
const ROOM_WORKING_PCT = 90;    // what _aecprobe measured a 59.5 ratio at
let ROOM_WAS = null;            // { pct, muted } - the employer's own setting, to be handed back

/* One PowerShell child, one inline type, used for both the read and the write - a second
   Add-Type in a second process costs a second of start-up per call. */
const ROOM_PS = `
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
[Guid("5CDF2C82-841E-4546-9722-0CF74078229A"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
interface IAEV {
  int f1(); int f2(); int GetChannelCount(out uint c);
  int SetMasterVolumeLevel(float v, Guid g);
  int SetMasterVolumeLevelScalar(float v, Guid g);
  int GetMasterVolumeLevel(out float v);
  int GetMasterVolumeLevelScalar(out float v);
  int f7(); int f8(); int f9(); int f10();
  int SetMute([MarshalAs(UnmanagedType.Bool)] bool m, Guid g);
  int GetMute([MarshalAs(UnmanagedType.Bool)] out bool m);
}
[Guid("D666063F-1587-4E43-81F1-B948E807363F"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
interface IMMD { int Activate(ref Guid i, int c, IntPtr p, [MarshalAs(UnmanagedType.IUnknown)] out object o); }
[Guid("A95664D2-9614-4F35-A746-DE8DB63617E6"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
interface IMMDE { int f(); int GetDefaultAudioEndpoint(int flow, int role, out IMMD d); }
[ComImport, Guid("BCDE0395-E52F-467C-8E3D-C4579291692E")] class En { }
public class Room {
  static IAEV Ep() {
    IMMDE en = (IMMDE)(new En()); IMMD d; en.GetDefaultAudioEndpoint(0, 0, out d);
    Guid i = typeof(IAEV).GUID; object o; d.Activate(ref i, 23, IntPtr.Zero, out o);
    return (IAEV)o;
  }
  public static string Read() {
    var e = Ep(); float v; bool m;
    e.GetMasterVolumeLevelScalar(out v); e.GetMute(out m);
    return ((int)Math.Round(v * 100)) + " " + (m ? "1" : "0");
  }
  public static string Write(int pct, bool mute) {
    var e = Ep(); e.SetMasterVolumeLevelScalar(pct / 100.0f, Guid.Empty);
    e.SetMute(mute, Guid.Empty); return Read();
  }
}
'@
`;

function roomRead() {
  const r = spawnSync('powershell', ['-NoProfile', '-Command', ROOM_PS + '[Room]::Read()'],
    { encoding: 'utf8' });
  const m = String(r.stdout || '').trim().match(/(\d+)\s+([01])/);
  return m ? { pct: Number(m[1]), muted: m[2] === '1' } : null;
}

function roomWrite(pct, muted) {
  spawnSync('powershell', ['-NoProfile', '-Command',
    ROOM_PS + '[Room]::Write(' + pct + ', $' + (muted ? 'true' : 'false') + ')'],
    { encoding: 'utf8' });
}

/* Called once per Mouth, from warm(). Idempotent: the employer's setting is captured the FIRST
   time only, so a second harness in the same process cannot record the level a first one
   raised and then "restore" it to that. */
export function ensureRoom(note) {
  const now = roomRead();
  if (!now) {
    if (note) note('   the render endpoint could not be read, so the room is being taken on ' +
                   'trust - if every transcript below is empty, that is the first thing to check');
    return null;
  }
  if (!now.muted && now.pct >= ROOM_FLOOR_PCT) {
    if (note) note('   the room is open: render ' + now.pct + '%, unmuted');
    return now;
  }
  if (ROOM_WAS === null) {
    ROOM_WAS = now;
    /* ON EXIT, AND ON EVERY EXIT. An uncaught throw is the case this is really for: that is how
       a sweep left this machine at 90% unmuted overnight. spawnSync because an exit handler gets
       no event loop - a promise here would never resolve. */
    process.on('exit', () => {
      if (ROOM_WAS) {
        roomWrite(ROOM_WAS.pct, ROOM_WAS.muted);
        console.log('  note the room was handed back: render ' + ROOM_WAS.pct + '%, ' +
                    (ROOM_WAS.muted ? 'muted' : 'unmuted') + ' - as it was found');
      }
    });
  }
  roomWrite(ROOM_WORKING_PCT, false);
  const after = roomRead();
  if (note) {
    note('   THE ROOM WAS SHUT AND HAS BEEN OPENED FOR THIS RUN: render was ' + now.pct + '%' +
         (now.muted ? ' and MUTED' : '') + ', now ' + ((after && after.pct) || '?') +
         '% unmuted. It is put back exactly as found when this process exits, including on a ' +
         'throw. A muted speaker reads in this log as a page that cannot hear.');
  }
  return after;
}

/* AND THE THREE OCCLUSION FLAGS, WHICH THE PARAGRAPH ABOVE PREDICTED AND THIS LIST DID NOT
   HAVE. It said a harness that forgets one of these "falls back to a silent room and reports
   'no transcript' as though the page were at fault", and that is precisely what routing_proof
   has been reporting: five attempts, "the room gave back nothing at all" every time, and then
   a Runtime.evaluate that outran its 40s bomb and killed the file before it could sign off.
   THE MECHANISM, MEASURED TWICE ELSEWHERE. This desktop minimizes a harness's Chrome window a
   second or two after it opens, and Chrome marks a covered or minimized window occluded: the
   page becomes a BACKGROUND page, its timers are clamped to about one a second and its audio
   graph is starved. echo_proof went from 28/49 to 49/49 on these three flags alone, and
   _runs/_aecprobe.mjs sampled an analyser across one 3.4-second sentence and got THREE samples
   without the cure and 173 with it. A recogniser in that state is not mishearing the room, it
   is barely being run.
   FAILURE MODE IF THESE ARE REMOVED: every spoken fixture in this project reports an empty
   transcript, the empty transcript is read as a defect in the ear or the funnel, and the days
   go into a recogniser that was never given a chance to tick. */
export const SPOKEN_FLAGS = ['--use-fake-ui-for-media-stream',
  '--disable-features=CalculateNativeWinOcclusion',
  '--disable-backgrounding-occluded-windows', '--disable-renderer-backgrounding'];

/* PUT THE WINDOW BACK WHERE IT CAN BE SEEN, because the flags above are necessary and not
   sufficient: they stop Chrome treating a covered window as hidden, but a MINIMIZED window is
   still a minimized window and this desk minimizes it anyway. setWindowBounds AND NEVER
   bringToFront - bringToFront steals the keyboard off whatever the employer is typing into,
   and the employer is sitting at this machine while the sweep runs. Every failure is swallowed
   on purpose: a harness that cannot restore its window should go on and measure what it can,
   and say so, rather than die at the first CDP call. */
export async function unminimise(page, targetId, note) {
  try {
    const { windowId } = await page.send('Browser.getWindowForTarget',
      targetId ? { targetId } : {});
    await page.send('Browser.setWindowBounds', { windowId, bounds: { windowState: 'normal' } });
    await page.send('Browser.setWindowBounds',
      { windowId, bounds: { left: 30, top: 30, width: 1200, height: 820 } });
    return true;
  } catch (e) {
    if (note) note('   the window could not be restored: ' + (e && e.message));
    return false;
  }
}

export function pythonPresent() { return existsSync(PY); }
