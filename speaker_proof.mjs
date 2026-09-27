/* speaker_proof.mjs - THE DOORMAN: WHO IS SPEAKING, AND WHOSE YES COUNTS.
   ======================================================================================
   PART 1 asked for a voiceprint: enrolment through the open ear, recognition on every turn,
   and one law - "with >=1 hands-privileged voiceprint enrolled, a spoken Yes/No at the Hands
   gate accepts only a hands-privileged voiceprint". PART 4 asked for this file: "enrol from
   pre-recorded wav fixtures (boss matches, a second voice refuses, noise floor refuses);
   spoken gate round - boss yes executes, guest yes refused with the named line, keyboard Yes
   still executes; seal labels correct per turn; raw-audio-deleted asserted; store hygiene
   asserted."

   WHY THE FIXTURES ARE RECORDINGS AND NOT A ROOM. Every other spoken harness in this house
   drives a real microphone, because what it measures is whether a sentence survives a room.
   This one measures a comparison between two larynxes, and for that a room is noise in the
   statistical sense: the same wav enrolled and then identified gives a number that means
   something, and "a voice that sounds a bit like the boss" cannot be produced on demand.
   Three recorded voices, one of them enrolled, are the only way to assert a REFUSAL - and the
   refusal is the whole of the law. Section E puts the recordings through Chrome's fake audio
   device and the page's own microphone graph afterwards, which is where the number that
   matters to a real turn is measured: echo cancellation, noise suppression and automatic gain
   are all on in that path and all three move a voiceprint.

   WHAT THIS HARNESS DOES TO THE HOUSE, said plainly at the top because it writes to the
   voiceprint store. It enrols TWO THROWAWAY ROWS - one hands-privileged, one not - and it
   forgets both, at the start of the run in case a crashed run left them and again in a finally
   block. It never touches, reads out, prints or replaces a row it did not create. If the house
   already has a boss enrolled, that row is background: it can only make the guest fixtures
   MORE likely to match something, which is the direction that would fail this file rather than
   flatter it.

   AND NO VECTOR IS EVER PRINTED. The store is read here to assert its shape - 192 floats per
   row, no long opaque strings, no audio of any kind in the folder - and what is printed is a
   length and a key name. An embedding is biometric data about a named person and nobody can
   rotate a larynx; a harness that pasted one into a terminal report would have put it in the
   lookbook.

   HOW TO RUN IT
     node speaker_proof.mjs                 the whole file (sections A-F)
     WIRE_ONLY=1 node speaker_proof.mjs     sections A-D and F - no browser, seconds
     SPEAKER_HEADED=1 node speaker_proof.mjs  section E with the window shown

   Section E launches its own Chrome on port 9263, so this file runs ALONE: a background
   sweep that also holds port 9222 will take its clicks. Preflight check 25 is the cheap
   standing version of section A and runs on every preflight.                            */
import { spawn } from 'node:child_process';
import { existsSync, mkdtempSync, rmSync, readFileSync, writeFileSync, readdirSync,
         statSync, readFileSync as slurp } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, extname } from 'node:path';

const GALAXY = 'http://127.0.0.1:4700';
const CDP_PORT = 9263;
const CDP = 'http://127.0.0.1:' + CDP_PORT;
const WIRE_ONLY = !!process.env.WIRE_ONLY;
const HEADED = process.env.SPEAKER_HEADED === '1';
const CAL = join('_spoken', 'cal');
const STORE = 'speaker-store';
const SESSION = 'speaker-proof';
const CHROMES = ['C:/Program Files/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Google/Chrome/Application/chrome.exe',
  process.env.LOCALAPPDATA + '/Google/Chrome/Application/chrome.exe'];
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

/* THE TWO ROWS THIS FILE OWNS. Named so that a stray one in a store is obviously a harness's
   litter and not a person, and so that `forget` at the top of the run is unambiguous. */
const HANDS_ROW = 'Proof Hands';
const PLAIN_ROW = 'Proof Plain';

/* ---- the scoreboard ---- */
let pass = 0, fail = 0;
const failures = [];
const say = (s) => console.log(s);
const step = (s) => say('\n  \u00b7\u00b7 ' + s);
const note = (s) => say('  note ' + s);
/* ---- THE SCRUB, THE SAME STANDING LAW AS routing_proof.mjs -------------------------------
   No account address may appear in a log, a plate or the lookbook except as a digest, and the
   payloads this file prints come off routes that carry the Command Panel's rows. It goes
   further here, because the thing this file handles is worse than an address: any run of four
   or more decimal places is replaced too, so a row's embedding cannot reach a terminal report
   even by accident - through a `why` string, an error, or a payload dump added next year.

   WHAT IT DOES NOT DO: it does not touch an assertion. Every judgement in this file reads the
   parsed payload; the scrub is downstream of all of them, on the way to the screen only. A
   scrubbed print therefore cannot make a red row look green - it can only make a green row
   less quotable, which is the right way round. Scores ARE printed, deliberately and to four
   places, via score() below, which formats a number the assertion already read. */
function scrub(s) {
  return String(s === undefined || s === null ? '' : s)
    .replace(/[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/g, '<address withheld>')
    .replace(/-?\d\.\d{5,}/g, '<vector withheld>');
}
const score = (n) => Number(n || 0).toFixed(4);
function ok(cond, claim, debug) {
  if (cond) { pass++; say('  ok   ' + scrub(claim)); return true; }
  fail++; failures.push(scrub(claim));
  say('  FAIL ' + scrub(claim));
  if (debug !== undefined) say('         ' + scrub(String(debug)).slice(0, 700));
  return false;
}

/* ---- the wire ---- */
async function post(path, body) {
  const res = await fetch(GALAXY + path, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  });
  const text = await res.text();
  let json = null;
  try { json = JSON.parse(text); } catch (e) { json = { unparsed: text.slice(0, 300) }; }
  return { status: res.status, body: json };
}
/* THE AUDIO DOOR. Parts are numbered audio0, audio1, ... because _read_multipart returns a
   dict keyed by part name and three parts all called "audio" would silently become one -
   an enrolment on a third of the speech it was given, which would then refuse itself for
   being too short and blame the speaker. */
async function postAudio(fields, clips) {
  const form = new FormData();
  for (const [k, v] of Object.entries(fields)) form.append(k, String(v));
  clips.forEach((buf, i) => form.append('audio' + i,
    new Blob([buf], { type: 'audio/wav' }), 'clip' + i + '.wav'));
  const res = await fetch(GALAXY + '/speaker', { method: 'POST', body: form });
  const text = await res.text();
  let json = null;
  try { json = JSON.parse(text); } catch (e) { json = { unparsed: text.slice(0, 300) }; }
  return { status: res.status, body: json };
}
const speakerState = () => post('/speaker', { cmd: 'state', session: SESSION });
const forget = (name) => post('/speaker', { cmd: 'forget', name, session: SESSION });
/* THE OFFER ON THE TABLE IS ALWAYS selftest. The standing rule is that preflight and every
   harness use tools/selftest.py and never send real mail - a fixture about the word "yes"
   must not be able to post a letter. */
const propose = () => post('/tools', {
  cmd: 'propose', tool: 'selftest', params: { token: 'SPEAKER' },
  door: 'harness', session: SESSION
});
const withdraw = () => post('/tools', { cmd: 'withdraw', session: SESSION });

/* ================================ THE WAVS ================================
   16-bit PCM in, 16-bit PCM out, written here rather than shelled out to python: a harness
   that needed a python to build its own fixture would be a harness that could not run on a
   machine where the thing it is testing is installed and the thing building its inputs is
   not.                                                                                   */
function readWav(path) {
  const b = readFileSync(path);
  let at = 12, rate = 0, bits = 16, chans = 1, data = null;
  while (at + 8 <= b.length) {
    const id = b.toString('ascii', at, at + 4), size = b.readUInt32LE(at + 4);
    if (id === 'fmt ') {
      chans = b.readUInt16LE(at + 10); rate = b.readUInt32LE(at + 12);
      bits = b.readUInt16LE(at + 22);
    }
    if (id === 'data') { data = b.subarray(at + 8, at + 8 + size); break; }
    at += 8 + size + (size & 1);
  }
  if (!data || bits !== 16) throw new Error(path + ' is not 16-bit pcm');
  const n = Math.floor(data.length / 2 / chans);
  const out = new Int16Array(n);
  for (let i = 0; i < n; i++) out[i] = data.readInt16LE(i * 2 * chans);
  return { samples: out, rate, seconds: n / rate };
}
function writeWav(samples, rate) {
  const bytes = samples.length * 2, w = Buffer.alloc(44 + bytes);
  w.write('RIFF', 0); w.writeUInt32LE(36 + bytes, 4); w.write('WAVE', 8);
  w.write('fmt ', 12); w.writeUInt32LE(16, 16); w.writeUInt16LE(1, 20);
  w.writeUInt16LE(1, 22); w.writeUInt32LE(rate, 24); w.writeUInt32LE(rate * 2, 28);
  w.writeUInt16LE(2, 32); w.writeUInt16LE(16, 34);
  w.write('data', 36); w.writeUInt32LE(bytes, 40);
  for (let i = 0; i < samples.length; i++) w.writeInt16LE(samples[i], 44 + i * 2);
  return w;
}
function clip(name) {
  const { samples, rate } = readWav(join(CAL, name));
  return writeWav(samples, rate);
}
/* A TRIMMED CLIP IS HOW THE SECONDS REFUSAL IS REACHED. The fixtures are 4.2 to 6.6 seconds
   each, so three of them clear the 8-second floor comfortably and only the SENTENCE count can
   be made to fail. Three one-and-a-half-second pieces are three sentences and four and a half
   seconds, which is the other refusal - the one that has to name the seconds still missing. */
function trimmed(name, seconds) {
  const { samples, rate } = readWav(join(CAL, name));
  return writeWav(samples.subarray(0, Math.min(samples.length, Math.round(rate * seconds))),
                  rate);
}
/* THE NOISE FLOOR, and it is generated rather than recorded on purpose: a recording of a quiet
   room is a recording of a room, and what the mandate asks about is a chunk of audio with no
   larynx in it at all. Deterministic (a fixed-seed LCG) so a red row here is reproducible. */
function noisePcm(seconds, rate, amplitude) {
  const n = Math.round(seconds * rate), out = new Int16Array(n);
  let seed = 20260927;
  for (let i = 0; i < n; i++) {
    seed = (seed * 1103515245 + 12345) & 0x7fffffff;
    out[i] = Math.round(((seed / 0x7fffffff) * 2 - 1) * amplitude * 32767);
  }
  return out;
}
const noiseWav = (seconds, rate, amplitude) =>
  writeWav(noisePcm(seconds, rate, amplitude), rate);

/* ================================ AUDIT: WHAT IS ON DISK ================================
   THE LAW IS "embeddings only, forever", and the only way to assert a deletion is to count
   what exists before and after. say-cache/ is excluded by name for the reason preflight
   excludes it: that is the voice this machine PRODUCES, and this file makes it speak.     */
const AUDIO_EXT = new Set(['.wav', '.mp3', '.ogg', '.flac', '.m4a', '.webm', '.opus', '.aac',
                           '.pcm', '.raw', '.aiff', '.aif', '.wma']);
const SKIP_DIRS = new Set(['say-cache', 'node_modules', '.git', '__pycache__']);
function audioUnder(dir, depth, out) {
  out = out || [];
  if (depth > 4) return out;
  let entries = [];
  try { entries = readdirSync(dir, { withFileTypes: true }); } catch (e) { return out; }
  for (const e of entries) {
    if (e.isDirectory()) {
      if (!SKIP_DIRS.has(e.name)) audioUnder(join(dir, e.name), depth + 1, out);
    } else if (AUDIO_EXT.has(extname(e.name).toLowerCase())) {
      let size = -1;
      try { size = statSync(join(dir, e.name)).size; } catch (e2) { size = -1; }
      out.push(join(dir, e.name) + '|' + size);
    }
  }
  return out;
}

/* ================================ SECTION A: THE STORE ================================ */
async function sectionA() {
  step('A. THE STORE\'S HOUSE RULES - gitignored, denied, embeddings only');

  const ignore = existsSync('.gitignore') ? slurp('.gitignore', 'utf8') : '';
  const rules = ignore.split(/\r?\n/).map((l) => l.trim())
    .filter((l) => l && !l.startsWith('#'));
  ok(rules.includes('speaker-store/') || rules.includes('speaker-store'),
     'speaker-store/ is in .gitignore - without this line 192 floats per named person are ' +
     'one `git add -A` from a remote, and a larynx cannot be rotated',
     rules.slice(0, 12).join(' '));

  let deny = [];
  try {
    deny = ((JSON.parse(slurp('.claude/settings.json', 'utf8')).permissions || {}).deny) || [];
  } catch (e) { deny = []; }
  ok(deny.some((r) => String(r).includes('speaker-store')),
     'Read(./speaker-store/**) is denied in .claude/settings.json, the same posture as ' +
     'secrets/ - so the assistant that wrote this file cannot read a voiceprint back out',
     JSON.stringify(deny));

  /* THE FOLDER ITSELF. Read for shape and never for content: what is printed below is a
     count, a length and a key name. */
  const files = existsSync(STORE) ? readdirSync(STORE) : [];
  const audio = files.filter((f) => AUDIO_EXT.has(extname(f).toLowerCase()));
  ok(audio.length === 0,
     'no audio of any kind inside the store - a wav in here would mean some path retained a ' +
     'sample, and this folder is the only place such a path could plausibly have put it',
     audio.join(', '));
  const strays = files.filter((f) => extname(f).toLowerCase() !== '.json');
  ok(strays.length === 0, 'every file in the store is a .json row and nothing else',
     strays.join(', '));

  let shaped = 0, blobs = [];
  for (const f of files.filter((f) => f.endsWith('.json'))) {
    let row = null;
    try { row = JSON.parse(slurp(join(STORE, f), 'utf8')); } catch (e) { row = null; }
    if (!row) { blobs.push(f + ' is not readable json'); continue; }
    if (!Array.isArray(row.embedding) || row.embedding.length !== 192) {
      blobs.push(f + ' carries ' + (Array.isArray(row.embedding)
        ? row.embedding.length + ' numbers' : typeof row.embedding) + ' where 192 belong');
      continue;
    }
    /* A BASE64 WAV IN A FIELD CALLED "sample" WOULD PASS A CHECK THAT ONLY COUNTED THE
       EMBEDDING, so every other field is measured too. Nothing in a row needs a blob. */
    for (const [k, v] of Object.entries(row)) {
      if (k === 'embedding') continue;
      if (typeof v === 'string' && v.length > 256) blobs.push(f + ': ' + k + ' is ' + v.length +
        ' characters - an embedding is 192 numbers and nothing here needs a blob');
      if (Array.isArray(v) && v.length > 192) blobs.push(f + ': ' + k + ' is a ' + v.length +
        '-long list');
    }
    shaped++;
  }
  ok(blobs.length === 0,
     'every one of the ' + shaped + ' row(s) on disk is exactly 192 floats with no long ' +
     'opaque string beside it - audio wearing a json coat would be caught here',
     blobs.slice(0, 4).join(' | '));

  /* AND THE STORE IS NOT REACHABLE OVER HTTP, asked here as well as in preflight check 9,
     because the ear's own page is the one client that legitimately talks to /speaker and is
     therefore the one place an embedding could plausibly be handed to a browser. */
  const probes = ['/speaker-store/', '/speaker-store/addi.json',
                  '/../speaker-store/addi.json', '/viewer/../speaker-store/addi.json'];
  const index = existsSync(join('viewer', 'index.html'))
    ? slurp(join('viewer', 'index.html')) : Buffer.alloc(0);
  const got = [];
  for (const p of probes) {
    try {
      const res = await fetch(GALAXY + p);
      const body = Buffer.from(await res.arrayBuffer());
      const benign = res.status === 200 && index.length && body.equals(index);
      got.push(p + ' -> ' + res.status + (benign ? ' (the viewer page)' : ''));
      if (res.status === 200 && !benign) {
        ok(false, 'speaker-store/ is unreachable from the browser', p + ' served ' +
           body.length + ' bytes');
        return;
      }
    } catch (e) { got.push(p + ' -> ' + (e.code || 'refused')); }
  }
  ok(true, 'all ' + probes.length + ' paths at speaker-store/ refuse or resolve back into ' +
     'viewer/: ' + got.join('; '));

  /* THE ROSTER OVER THE WIRE. Four facts draw the Command Panel's row - who, how they are
     addressed, whether they may use the hands, and when they enrolled. The 192 floats are
     not one of them, and sending them would let a page do the comparing. */
  const st = await speakerState();
  ok(st.status === 200 && st.body.installed && st.body.ready,
     'the doorman is installed and ready: ECAPA-TDNN at ' + (st.body.dim || '?') +
     ' dimensions, threshold ' + st.body.threshold,
     JSON.stringify(st.body).slice(0, 200));
  const blob = JSON.stringify(st.body);
  ok(!/embedding/.test(blob) && !/-?\d\.\d{5,}/.test(blob),
     'and cmd=state answers in counts, names and booleans - no field called "embedding" and ' +
     'no long decimal anywhere in the payload',
     blob.slice(0, 200));
  ok(st.body.keepsAudio === false,
     'the state says keepsAudio false out loud, so a proof has a field to go red on the day ' +
     'one appears');
  return st.body;
}

/* ================================ SECTION B: ENROLMENT ================================ */
async function sectionB() {
  step('B. ENROLMENT FROM FIXTURES - and the three refusals');

  /* A crashed earlier run is forgotten first: the duplicate check would otherwise refuse this
     run's own enrolment and every assertion below it would be about the wrong thing. */
  for (const name of [HANDS_ROW, PLAIN_ROW, 'Proof Other', 'Proof Short']) await forget(name);

  const before = (await speakerState()).body.count;
  const joe = [clip('joe-0.wav'), clip('joe-1.wav'), clip('joe-2.wav')];
  const ryan = [clip('ryan-0.wav'), clip('ryan-1.wav'), clip('ryan-2.wav')];

  /* -- the hands-privileged row. Enrolled FIRST for a reason: on an empty store the first
     enrolment is the boss and carries hands: true whatever the body says, which is the
     mandate's own rule, so a run on a fresh machine must not spend that on the plain row. */
  let r = await postAudio({ cmd: 'enrol', name: HANDS_ROW, addressForm: HANDS_ROW,
                            hands: 'true', session: SESSION }, joe);
  const hands = r.body.enrolled || {};
  ok(r.status === 200 && hands.hands === true,
     'a hands-privileged voiceprint enrolled from three recorded sentences: ' +
     hands.sentences + ' sentences, ' + hands.seconds + 's of speech, ' + r.body.tookMs + 'ms',
     JSON.stringify(r.body).slice(0, 220));
  ok(r.body.keptAudio === false && r.body.audioSeconds > 0,
     'and the route says it kept none of the ' + r.body.audioSeconds + ' seconds it was ' +
     'given - the samples arrive as an argument, are read once by embed(), and the only ' +
     'thing that leaves is 192 floats');

  /* -- the enrolled voice with no hands. This row is why the seal has three readings and not
     two: an enrolled person the gate will NOT take a yes from reads as their own name. */
  r = await postAudio({ cmd: 'enrol', name: PLAIN_ROW, addressForm: PLAIN_ROW,
                        hands: 'false', session: SESSION }, ryan);
  const plain = r.body.enrolled || {};
  ok(r.status === 200 && plain.hands === false,
     'a second voice enrolled WITHOUT the hands, so the seal has a third reading to give: ' +
     'a name, for somebody this house knows and takes no orders from',
     JSON.stringify(r.body).slice(0, 200));

  const mid = (await speakerState()).body;
  ok(mid.count === before + 2,
     'the store went from ' + before + ' row(s) to ' + mid.count + ' - two enrolments, two ' +
     'rows, and no row invented on the way');

  /* -- REFUSAL ONE: a duplicate, by name. The cost of not refusing is two rows for one
     larynx and a store where forgetting somebody only half works. */
  r = await postAudio({ cmd: 'enrol', name: 'Proof Other', addressForm: 'Proof Other',
                        hands: 'false', session: SESSION },
                      [clip('joe-1.wav'), clip('joe-2.wav'), clip('joe-3.wav')]);
  const dup = String(r.body.error || '');
  ok(r.status !== 200 && dup.includes(HANDS_ROW),
     'the same larynx under a second name is refused AS A DUPLICATE and the refusal names ' +
     'the row it already has: "' + dup.slice(0, 120) + '"',
     r.status + ' ' + JSON.stringify(r.body).slice(0, 200));
  ok((await speakerState()).body.count === mid.count,
     'and the refused duplicate wrote nothing: still ' + mid.count + ' rows');

  /* -- REFUSAL TWO: too little speech, naming the seconds. "That was not enough" tells a
     person to guess; "another 3.5 seconds" tells them what to do. */
  r = await postAudio({ cmd: 'enrol', name: 'Proof Short', addressForm: 'Proof Short',
                        hands: 'false', session: SESSION },
                      [trimmed('alan-0.wav', 1.5), trimmed('alan-1.wav', 1.5),
                       trimmed('alan-2.wav', 1.5)]);
  const short = String(r.body.error || '');
  ok(r.status !== 200 && /second/i.test(short) && /\d/.test(short),
     'three sentences totalling four and a half seconds are refused with the SECONDS still ' +
     'missing named: "' + short.slice(0, 130) + '"',
     r.status + ' ' + JSON.stringify(r.body).slice(0, 200));

  /* -- REFUSAL THREE: too few sentences, which is a different refusal for the reason the
     average exists - one long reading gives one point around the speaker's centre. */
  r = await postAudio({ cmd: 'enrol', name: 'Proof Short', addressForm: 'Proof Short',
                        hands: 'false', session: SESSION }, [clip('alan-0.wav')]);
  const few = String(r.body.error || '');
  ok(r.status !== 200 && /sentence/i.test(few),
     'and one long clip is refused for the SENTENCES rather than the seconds: "' +
     few.slice(0, 130) + '"',
     r.status + ' ' + JSON.stringify(r.body).slice(0, 200));

  /* -- AND THE KEYBOARD IS THE DOOR. The real guard is structural - no sentence anywhere in
     the funnel reaches cmd=enrol - and this is the explicit half of it, so that the day
     somebody wires a spoken shortcut to enrolment it fails loudly instead of working. */
  r = await postAudio({ cmd: 'enrol', name: 'Proof Spoken', addressForm: 'x', via: 'voice',
                        session: SESSION }, joe);
  ok(r.status === 403 && /Command Panel/i.test(String(r.body.error || '')),
     'an enrolment that admits it came in through the ear is refused by name: "' +
     String(r.body.error || '').slice(0, 110) + '"',
     r.status + ' ' + JSON.stringify(r.body).slice(0, 160));

  /* -- RE-LEARNING KEEPS THE PRIVILEGE IT ALREADY HAD, and a refused re-learning leaves the
     old row where it was. This is the quietest way the whole law could be stood down: forget,
     then enrol, then discover the new sentences were four seconds short - and the house's
     only hands-privileged row is gone. */
  r = await postAudio({ cmd: 'enrol', name: HANDS_ROW, addressForm: HANDS_ROW,
                        replace: 'true', session: SESSION },
                      [trimmed('joe-0.wav', 1.0)]);
  const after = (await speakerState()).body;
  ok(r.status !== 200 && after.count === mid.count && after.hasHands === true,
     'a re-learning that comes up short is refused AND leaves the old row intact: still ' +
     after.count + ' rows and hasHands still true, so the law cannot be disarmed by a ' +
     'failed replace',
     r.status + ' ' + JSON.stringify(r.body.error || '').slice(0, 140));
  r = await postAudio({ cmd: 'enrol', name: HANDS_ROW, addressForm: HANDS_ROW,
                        replace: 'true', session: SESSION }, joe);
  ok(r.status === 200 && (r.body.enrolled || {}).hands === true,
     'and a re-learning that succeeds comes back WITH the hands it had, though the body ' +
     'never asked for them - a boss re-enrolling after a cold must not return as a ' +
     'hands-less row');
  ok((await speakerState()).body.count === mid.count,
     'the replace overwrote one file rather than adding a row: still ' + mid.count);
  return { hands, plain };
}

/* ================================ SECTION C: THE MATCH TABLE ================================ */
const table = [];
async function identify(label, buf) {
  const r = await postAudio({ cmd: 'identify', session: SESSION }, [buf]);
  const b = r.body || {};
  table.push({ label, seal: b.seal || '-', who: b.who || '-', hands: !!b.hands,
               score: Number(b.score || 0), ms: b.tookMs, turn: b.turn, why: b.why || '' });
  return { status: r.status, ...b };
}
async function sectionC() {
  step('C. THE MATCH TABLE - one embedding per turn, in RAM, and the seal it earns');

  const boss = await identify('the hands voice (joe-3)', clip('joe-3.wav'));
  ok(boss.status === 200 && boss.seal === 'BOSS' && boss.hands === true,
     'a fourth sentence from the enrolled hands voice reads BOSS at cosine ' +
     score(boss.score) + ' - and BOSS is a PRIVILEGE and not a row number: the seal reads it ' +
     'for exactly the voices the Hands gate will take a yes from',
     JSON.stringify(boss).slice(0, 220));
  ok(boss.score >= 0.5,
     'and it clears the 0.50 threshold with ' + score(boss.score) + ', against a measured ' +
     'same-voice floor of 0.8182 over eighteen pairs');

  const named = await identify('the plain voice (ryan-3)', clip('ryan-3.wav'));
  ok(named.status === 200 && named.seal === PLAIN_ROW && named.hands === false,
     'the enrolled voice with no hands reads as ITS OWN NAME at cosine ' + score(named.score) +
     ', not BOSS and not GUEST - the third reading the seal owes an enrolled person the gate ' +
     'will not obey',
     JSON.stringify(named).slice(0, 220));

  /* NO CROSSOVER, and this is the assertion the refusal actually rests on. Two larynxes were
     enrolled a minute ago under two names with two different privileges; each of their fourth
     sentences has to come back matched to ITS OWN row. A matcher that returned the wrong row
     at a high score would pass every "is it above the threshold" assertion in this file and
     hand a guest the hands. */
  ok(boss.who === HANDS_ROW && named.who === PLAIN_ROW,
     'and there is NO CROSSOVER: joe-3 matched ' + boss.who + ' and ryan-3 matched ' +
     named.who + ' - two larynxes, two rows, neither borrowing the other\'s, which is the ' +
     'discrimination the whole law rests on');

  /* A THIRD LARYNX, and the assertion is written for BOTH houses it can run in. On a machine
     with somebody already enrolled, alan is very likely that somebody - the boss's own store
     is not this harness's to empty - so the claim cannot be "this reads GUEST". What is true
     either way, and is the thing worth asserting, is that a third voice does not land on
     either row this run created. */
  const second = await identify('a third voice (alan-3)', clip('alan-3.wav'));
  const mine = second.who === HANDS_ROW || second.who === PLAIN_ROW;
  if (second.seal === 'GUEST') {
    ok(second.status === 200 && second.score < 0.5,
       'a third larynx this house has never been taught reads GUEST at cosine ' +
       score(second.score) + ' - measured different-voice ceiling 0.2954 over forty-eight ' +
       'pairs, and the 0.5228 gap below the same-voice floor is what the 0.50 threshold sits in',
       JSON.stringify(second).slice(0, 220));
  } else {
    ok(second.status === 200 && !mine,
       'a third larynx matched ' + second.who + ' at cosine ' + score(second.score) +
       ' - a row this house enrolled before this run and NOT either of the two this run ' +
       'created, so three voices produced three rows and not one of them borrowed another\'s',
       JSON.stringify(second).slice(0, 220));
    note('this machine already knows that third voice, so its GUEST reading cannot be ' +
         'asserted here - the noise floor below is the input nobody can have enrolled, and ' +
         'preflight check 25 names the roster this ran against');
  }

  const noise = await identify('the noise floor', noiseWav(5, 16000, 0.05));
  ok(noise.status === 200 && noise.seal === 'GUEST' && noise.hands === false,
     'five seconds of noise with no larynx in it reads GUEST at cosine ' + score(noise.score) +
     ' - the failure this catches is a matcher that returns its nearest row whatever the ' +
     'distance, which would make silence the boss',
     JSON.stringify(noise).slice(0, 220));

  ok(table.every((t) => t.turn > 0) &&
     new Set(table.map((t) => t.turn)).size === table.length,
     'each of the ' + table.length + ' turns got its own number from this server, none of ' +
     'them zero: turn 0 is the number the page sends when it has no verdict, and a number ' +
     'this process never issued is what makes the page unable to lie');
  const kept = await postAudio({ cmd: 'identify', session: SESSION }, [clip('joe-3.wav')]);
  ok(kept.body.keptAudio === false,
     'and every identify says keptAudio false: the chunk is embedded in RAM and dropped, ' +
     'which is the only claim a route can make that a harness can name');
  return { boss, named, second, noise };
}

/* ================================ SECTION D: THE SPOKEN GATE ================================ */
async function turnFor(buf) {
  const r = await postAudio({ cmd: 'identify', session: SESSION }, [buf]);
  return r.body.turn;
}
async function offerAndSay(turn, door) {
  const p = await propose();
  const id = ((p.body || {}).pending || {}).id;
  if (!id) return { status: 0, body: { error: 'no proposal was made' } };
  const body = { id, door: door || 'voice', session: SESSION };
  if (turn !== null) body.speaker = { via: 'voice', turn };
  const r = await post('/execute', body);
  if (r.status !== 200) await withdraw();
  return r;
}
const LINE = 'I take orders from one voice in this house, and it is not speaking just now.';
async function sectionD() {
  step('D. THE LAW AT THE HANDS GATE - whose yes becomes an action');

  /* -- the boss's yes executes. Nothing else in this file matters if this one is red: a law
     that refuses everybody is not a doorman, it is a locked door. */
  let r = await offerAndSay(await turnFor(clip('joe-3.wav')));
  ok(r.status === 200 && r.body.ok === true && /self test/i.test(String(r.body.answer || '')),
     'a spoken yes carrying a hands-privileged turn EXECUTES: "' +
     String(r.body.answer || '').slice(0, 90) + '"',
     r.status + ' ' + JSON.stringify(r.body).slice(0, 200));

  /* -- ONE TURN, ONE ORDER. A verdict is worth 45 seconds to /chat, which only uses it to
     decide what to call somebody; at THIS gate it authorises an action, and a number that
     authorises twice is a number worth stealing. The case this closes is the barked interrupt,
     which reaches the page before the detector has ended the utterance and therefore travels
     with the PREVIOUS turn's number. */
  const spent = await turnFor(clip('joe-3.wav'));
  r = await offerAndSay(spent);
  ok(r.status === 200, 'the same turn, used once, executed once', r.status);
  r = await offerAndSay(spent);
  ok(r.status === 403 && r.body.refused === 'not-the-boss',
     'and the SAME turn number a second time is refused: an honoured word spends its slot, ' +
     'so one measured utterance cannot consent twice',
     r.status + ' ' + JSON.stringify(r.body).slice(0, 160));

  /* -- the enrolled voice with no hands. Courteous, and it names no name: not the boss's,
     not theirs, because a refusal is not the place to tell a stranger who gives orders here. */
  r = await offerAndSay(await turnFor(clip('ryan-3.wav')));
  ok(r.status === 403 && String(r.body.answer || '').trim() === LINE,
     'a spoken yes from an ENROLLED voice without the hands is refused with the mandate\'s ' +
     'line, verbatim: "' + String(r.body.answer || '').slice(0, 90) + '"',
     r.status + ' ' + JSON.stringify(r.body).slice(0, 220));
  ok(!new RegExp(HANDS_ROW, 'i').test(String(r.body.answer || '')) &&
     !new RegExp(PLAIN_ROW, 'i').test(String(r.body.answer || '')),
     'and the refusal names NO NAME - neither the privileged row nor the refused one');

  /* -- a guest proper. */
  r = await offerAndSay(await turnFor(noiseWav(5, 16000, 0.05)));
  ok(r.status === 403 && r.body.refused === 'not-the-boss',
     'a yes carrying a GUEST turn is refused the same way, and the seal on the refusal reads ' +
     '"' + (r.body.seal || '-') + '"',
     r.status + ' ' + JSON.stringify(r.body).slice(0, 180));

  /* -- AND IT FAILS CLOSED. A number this server never issued is the shape a hung, timed-out
     or forged identification takes, and the page sends turn 0 rather than omitting the block
     for exactly this reason: an omitted block reads as a keystroke. */
  for (const forged of [0, 99999]) {
    r = await offerAndSay(forged);
    ok(r.status === 403 && r.body.refused === 'not-the-boss',
       'turn ' + forged + ' - a number this process never issued - is refused exactly as a ' +
       'guest is, so a spoken yes whose speaker could not be established fails CLOSED',
       r.status + ' ' + JSON.stringify(r.body).slice(0, 160));
  }

  /* -- THE GUEST'S NO IS REFUSED TOO, and at the other door. A stranger who can say no can
     quietly stop everything this house is asked to do: the word cancels a proposal the boss
     made and is waiting on. Neither word is an opinion at this gate. */
  const p = await propose();
  const id = ((p.body || {}).pending || {}).id;
  r = await post('/tools', { cmd: 'cancel', id, door: 'voice', session: SESSION,
                             speaker: { via: 'voice', turn: await turnFor(clip('ryan-3.wav')) } });
  ok(r.status === 403 && r.body.refused === 'not-the-boss',
     'a spoken NO from a voice without the hands is refused at /tools cmd=cancel as well - ' +
     'the law is one function called at three doors, because a law written at one of them ' +
     'is a law with two ways round it',
     r.status + ' ' + JSON.stringify(r.body).slice(0, 180));
  /* -- THE KEYBOARD IS ALWAYS OPEN, and this assertion carries a second one for free: it
     executes THE SAME proposal id the guest just tried to cancel, so a 200 here is also the
     proof that the refused no left the offer standing. The cost of the doorman refusing the
     boss on a bad morning is one keystroke; the cost of admitting a stranger is a sent
     email. The two are not the same size, so the law is strict and the other door stays
     unlocked. */
  r = await post('/execute', { id, door: 'button', session: SESSION });
  ok(r.status === 200 && r.body.ok === true,
     'and the keyboard executes THAT SAME proposal with no speaker block at all - which is ' +
     'both halves of it: the refused no left the offer standing, and a typed Yes never ' +
     'reaches the doorman, because that is the boss\'s other door',
     r.status + ' ' + JSON.stringify(r.body).slice(0, 160));
  await withdraw();
}

/* ================================ SECTION E: THE SEAL IN THE GLASS ================================
   Everything above is the wire. This is the only section that measures what a real turn does:
   the recording goes in through Chrome's fake audio device, down the page's own microphone
   graph - echo cancellation, noise suppression and automatic gain all on - into the doorman's
   tap, and out as the words in the seal cell the employer can actually see.               */
class Page {
  constructor(u) { this.u = u; this.id = 0; this.w = new Map(); this.errors = []; }
  open() {
    return new Promise((res, rej) => {
      this.ws = new WebSocket(this.u);
      this.ws.onopen = () => res(this);
      this.ws.onerror = (e) => rej(new Error('socket: ' + (e.message || 'failed')));
      this.ws.onmessage = (ev) => {
        const m = JSON.parse(ev.data);
        if (m.method === 'Runtime.exceptionThrown') {
          const d = m.params.exceptionDetails;
          this.errors.push(d.text + ' ' + ((d.exception && d.exception.description) || ''));
        }
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
  async evaluate(expression) {
    const r = await this.send('Runtime.evaluate',
      { expression, returnByValue: true, awaitPromise: true });
    if (r.result && r.result.exceptionDetails) {
      throw new Error('page threw: ' + JSON.stringify(r.result.exceptionDetails).slice(0, 400));
    }
    return r.result && r.result.result ? r.result.result.value : undefined;
  }
  async json(e) { return JSON.parse(await this.evaluate('JSON.stringify(' + e + ')') || 'null'); }
  close() { try { this.ws.close(); } catch (e) { } }
}
const cdpGet = async (p) => {
  const r = await fetch(CDP + p); const t = await r.text();
  try { return JSON.parse(t); } catch (e) { return t; }
};
/* CHROME LOOPS THE FILE IT IS GIVEN, and a loop with no pause in it never ends an utterance:
   the VAD closes a turn on silence, so a gap is stapled on the end. 48 kHz because that is
   what the flag wants; linear resampling because what is being measured is a larynx and a
   better kernel would change the fourth decimal place of a number whose gap is 0.52.      */
function loopFile(dir, source, gapS) {
  const { samples, rate } = source.pcm
    ? { samples: source.pcm, rate: source.rate }
    : readWav(join(CAL, source.file));
  const out = 48000, m = Math.floor(samples.length * out / rate);
  const gap = Math.round(out * gapS), grown = new Int16Array(m + gap);
  for (let i = 0; i < m; i++) {
    const t = i * rate / out, j = Math.floor(t), f = t - j;
    const a = samples[j] || 0, c = samples[Math.min(samples.length - 1, j + 1)] || 0;
    grown[i] = Math.max(-32768, Math.min(32767, Math.round(a + (c - a) * f)));
  }
  const path = join(dir, 'loop.wav');
  writeFileSync(path, writeWav(grown, out));
  return path;
}
async function pageRound(which, source, want) {
  const profile = mkdtempSync(join(tmpdir(), 'spkp-'));
  const loop = loopFile(profile, source, 1.6);
  const exe = CHROMES.find((p) => existsSync(p));
  if (!exe) { ok(false, 'a Chrome-family browser is on this machine'); return null; }
  const chrome = spawn(exe, [
    '--remote-debugging-port=' + CDP_PORT, '--user-data-dir=' + profile,
    '--no-first-run', '--no-default-browser-check',
    '--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream',
    '--use-file-for-fake-audio-capture=' + loop,
    '--disable-features=CalculateNativeWinOcclusion',
    '--disable-backgrounding-occluded-windows', '--disable-renderer-backgrounding',
    ...(HEADED ? [] : ['--headless=new']),
    '--window-size=1400,900', '--new-window', GALAXY + '/?mute=1',
  ], { detached: true, stdio: 'ignore' });
  try {
    for (let i = 0; i < 80; i++) {
      try { await cdpGet('/json/version'); break; } catch (e) { await sleep(250); }
    }
    let target = null;
    for (let i = 0; i < 40; i++) {
      const l = await cdpGet('/json/list');
      target = (Array.isArray(l) ? l : []).find((t) => t.type === 'page' && /4700/.test(t.url));
      if (target) break;
      await sleep(250);
    }
    if (!target) { ok(false, 'the viewer opened on port ' + CDP_PORT); return null; }
    const page = await new Page(target.webSocketDebuggerUrl).open();
    await page.send('Runtime.enable');
    for (let i = 0; i < 80; i++) {
      if (await page.evaluate('!!(window.__galaxy && __galaxy.speaker)')) break;
      await sleep(250);
    }
    /* THE COUNT ARRIVES ON THE FIRST /health POLL and not at boot, so a probe that reads
       before it lands prints installed:false and learns nothing about the doorman. */
    for (let i = 0; i < 60; i++) {
      if (await page.evaluate('__galaxy.speaker.count > 0')) break;
      await sleep(500);
    }
    /* A GENUINE GESTURE. Chrome keeps an AudioContext suspended until it believes a human
       touched the page, and a suspended context delivers no worklet chunks at all - which is
       a silent tap that looks exactly like a silent microphone, and cost this harness two
       runs before the flag was found. */
    for (const type of ['mousePressed', 'mouseReleased']) {
      await page.send('Input.dispatchMouseEvent', { type, x: 700, y: 860, button: 'left',
        clickCount: 1, buttons: type === 'mousePressed' ? 1 : 0 });
      await sleep(40);
    }
    const raised = JSON.parse(await page.evaluate(
      '__galaxy.ear.raise().then(function (r) { return JSON.stringify(r); })') || 'null') || {};
    ok(raised.open === true && raised.stream === true,
       '[' + which + '] the ear opens on a real gesture and holds a stream');
    await sleep(1500);
    ok(await page.evaluate('__galaxy.speaker.tapped') === true,
       '[' + which + '] and the doorman\'s tap comes up on that same stream in ' +
       (await page.evaluate('__galaxy.speaker.mode')) + ' mode - one registered worklet ' +
       'shared with the Scribe, pulled through a gain of zero so nothing is audible',
       await page.evaluate('__galaxy.speaker.trouble'));

    let last = null;
    for (let i = 0; i < 26; i++) {
      await sleep(1000);
      last = await page.json('({ring:__galaxy.speaker.ringMs,chunks:__galaxy.speaker.chunks,' +
        'RING:__galaxy.speaker.RING_MS,turns:__galaxy.speaker.turns,' +
        'seal:__galaxy.speaker.seal,score:__galaxy.speaker.score,' +
        'echo:__galaxy.speaker.echoDropped,failed:__galaxy.speaker.failed,' +
        'keeps:__galaxy.speaker.keepsAudio,cell:(__galaxy.speaker.cell||{}),' +
        'ends:__galaxy.ear.ends})');
      if (last && last.turns >= 2) break;
    }
    ok(!!last && last.turns >= 1,
       '[' + which + '] ' + (last ? last.turns : 0) + ' utterance(s) reached the doorman ' +
       'through the page\'s own microphone graph in ' + (last ? last.chunks : 0) +
       ' half-second chunks', JSON.stringify(last));
    ok(!!last && last.ring > 0 && last.ring <= last.RING,
       '[' + which + '] the ring holds ' + (last ? last.ring : 0) + 'ms and rolls at ' +
       (last ? last.RING : 0) + 'ms - a bounded buffer, so an ear left open all afternoon ' +
       'costs fourteen seconds of RAM and not an afternoon of it');
    ok(!!last && last.seal === want,
       '[' + which + '] the seal reads ' + (last ? last.seal : '-') + ' at cosine ' +
       score(last && last.score) + ' THROUGH THE PAGE - echo cancellation, noise suppression ' +
       'and automatic gain are all on in that path, and the wanted reading is ' + want,
       JSON.stringify(last));
    ok(!!last && last.cell && last.cell.text === 'speaker: ' + want && last.cell.on === true,
       '[' + which + '] and the GLASS says so: the seal cell reads "' +
       ((last && last.cell && last.cell.text) || '') + '" while the ear is open, which is ' +
       'the only version of this the employer can see',
       JSON.stringify(last && last.cell));
    ok(!!last && last.failed === 0 && last.keeps === false,
       '[' + which + '] no identification failed, and the page holds no audio: the ring is ' +
       'PCM in RAM, sliced per utterance, and keepsAudio is false by construction');

    /* AND CLOSING THE EAR EMPTIES IT. The seal is live only - the mandate's word - so when
       the ear shuts the buffer, the verdict and the cell all go at once, and nothing about
       who was in the room survives the session. */
    await page.evaluate('__galaxy.ear.close("speaker-proof")');
    await sleep(700);
    const shut = await page.json('({ring:__galaxy.speaker.ringMs,' +
      'samples:__galaxy.speaker.ringSamples,seal:__galaxy.speaker.seal,' +
      'tapped:__galaxy.speaker.tapped,cell:(__galaxy.speaker.cell||{})})');
    ok(shut.ring === 0 && shut.samples === 0 && shut.tapped === false && shut.seal === '' &&
       shut.cell.text === '' && shut.cell.on === false,
       '[' + which + '] and closing the ear drops the tap, empties the ring to ' +
       shut.samples + ' samples and clears the cell - live only, never written to ledger, ' +
       'lookbook or log beyond counts',
       JSON.stringify(shut));
    if (page.errors.length) {
      note('page errors: ' + scrub(page.errors.slice(0, 3).join(' | ')).slice(0, 300));
    }
    ok(page.errors.length === 0, '[' + which + '] and the page threw nothing while it ran');
    page.close();
    return last;
  } finally {
    try { process.kill(-chrome.pid); } catch (e) { }
    try { chrome.kill(); } catch (e) { }
    await sleep(600);
    try { rmSync(profile, { recursive: true, force: true }); } catch (e) { }
  }
}
async function sectionE() {
  step('E. THE SEAL IN THE GLASS - the same recordings, through a real microphone graph');
  const b = await pageRound('joe-3.wav', { file: 'joe-3.wav' }, 'BOSS');
  /* THE GUEST ROUND IS NOISE AND NOT A THIRD RECORDING, for a reason worth writing down: the
     house this harness runs in may already have somebody enrolled, and alan-3 through the page
     would then read BOSS on one machine and GUEST on another. A generated noise floor is the
     one input nobody can have enrolled, so the assertion means the same thing everywhere. */
  const g = await pageRound('the noise floor',
    { pcm: noisePcm(4.5, 16000, 0.09), rate: 16000 }, 'GUEST');
  return { b, g };
}

/* ================================ SECTION F: THE AUDIO IS GONE ================================ */
async function sectionF(before) {
  step('F. RAW AUDIO DELETED - counted rather than promised');
  const after = audioUnder('.', 0, []);
  const added = after.filter((a) => !before.includes(a));
  /* say-cache/ is excluded by name above - that is the voice this machine PRODUCES, and
     nothing in this file makes it speak, but the exclusion is the same one preflight uses
     and is left in place so the two agree. */
  ok(added.length === 0,
     'this run put every one of its clips through enrolment and identification and left not ' +
     'one audio file behind: ' + before.length +
     ' audio files under the project root before, the same ' + after.length + ' after',
     added.slice(0, 6).join(' | '));
  const files = existsSync(STORE) ? readdirSync(STORE) : [];
  ok(files.every((f) => f.endsWith('.json')),
     'and the store still holds nothing but json rows after two enrolments and a replace',
     files.join(', '));
  const st = (await speakerState()).body;
  ok(st.seen && st.seen.audioSeconds > 0 && st.keepsAudio === false,
     'the server\'s own tally says it has passed ' + (st.seen || {}).audioSeconds +
     ' seconds of audio through RAM cumulatively and kept none of it - a count, which is all ' +
     'the Scribe\'s privacy law allows a log to know');
  return st;
}

/* ================================ THE RUN ================================ */
const audioBefore = audioUnder('.', 0, []);
let health = null;
try {
  const up = await fetch(GALAXY + '/health').then((r) => r.json()).catch(() => null);
  if (!up) { say('\n  the server is not answering on ' + GALAXY + ' - start it first.'); process.exit(2); }
  say('  server: ' + (up.model || '?') + ' \u00b7 speaker ' +
      JSON.stringify((up.speaker || {}).count) + ' row(s) enrolled before this run');

  health = await sectionA();
  await sectionB();
  await sectionC();
  await sectionD();
  if (!WIRE_ONLY) await sectionE();
  else note('section E skipped: WIRE_ONLY=1 is a regression pass, not a pass');
  await sectionF(audioBefore);
} catch (err) {
  fail++;
  failures.push('the harness threw: ' + scrub(err && err.message));
  say('\n  THREW ' + scrub(err && err.stack ? err.stack.split('\n')[0] : err));
} finally {
  /* THE LITTER GOES BACK, always. A harness that left a hands-privileged voiceprint in a real
     store would have changed who this house takes orders from in order to prove who it takes
     orders from. */
  for (const name of [HANDS_ROW, PLAIN_ROW, 'Proof Other', 'Proof Short', 'Proof Spoken']) {
    await forget(name);
  }
  await withdraw();
  const end = (await speakerState()).body;
  const back = end.count === ((health && health.count) || 0);
  say('\n  ' + (back ? 'ok   ' : 'FAIL ') + 'the store is back as it was: ' + end.count +
      ' row(s), hasHands ' + end.hasHands);
  if (back) pass++; else { fail++; failures.push('the store was left with litter in it'); }
}

/* ---- THE MATCH TABLE, printed whatever happened, because it is the lookbook's evidence ---- */
if (table.length) {
  say('\n  ---- THE MATCH SCORES ------------------------------------------------');
  say('  ' + 'utterance'.padEnd(26) + ' | cosine | seal            | hands | ms');
  say('  ' + '-'.repeat(26) + '-+--------+-----------------+-------+-----');
  for (const t of table) {
    say('  ' + t.label.slice(0, 26).padEnd(26) + ' | ' + score(t.score).padEnd(6) + ' | ' +
        String(t.seal).slice(0, 15).padEnd(15) + ' | ' +
        (t.hands ? 'yes' : 'no').padEnd(5) + ' | ' + t.ms);
  }
  say('  the threshold is 0.50; measured same-voice floor 0.8182 (n=18), different-voice ' +
      'ceiling 0.2954 (n=48)');
}

say('\n  VERIFY ' + pass + '/' + (pass + fail) + (fail ? ' FAIL' : ' PASS'));
if (fail) {
  say('');
  for (const f of failures) say('    FAILED: ' + f);
}
process.exit(fail ? 1 : 0);
