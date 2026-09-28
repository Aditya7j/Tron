/* mic_probe.mjs - WHICH MICROPHONE IS THE DEFAULT? A DIAGNOSIS, NOT A PROOF.
   ==================================================================================
   THE COMPLAINT it exists to settle: every spoken fixture returns nothing while the page's
   own analyser reads a healthy level, and BOTH recognition engines - on-device and cloud -
   are equally deaf. That combination cannot be the engine, the volume, the VAD or the echo
   law, because those four are downstream of a stream that demonstrably carries sound.

   What it CAN be is two different microphones. Chrome's speech recogniser does not use the
   page's getUserMedia stream; it opens the system default capture device itself. So a room
   where the fixture plays out of the laptop speakers into the laptop microphone array, but
   the DEFAULT capture device is a bluetooth headset lying on a desk somewhere, produces
   exactly the observed report: the page hears the room, the recogniser hears an earcup.
   The tell that started this was a transcript reading "Connected" - a headset's own pairing
   announcement, which is not a mishearing of any sentence anybody said.

   So: open a real headed Chrome, take the default microphone the ordinary way, and print
   the LABEL of the track that arrived along with every device the browser can see. The
   label is the answer. Nothing here asserts and nothing here is a gate; it changes no
   state, writes no file and closes what it opened. */

import { spawn, spawnSync } from 'node:child_process';
import { mkdtempSync, rmSync, existsSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const PY = 'C:/Users/Fullstack Developer/AppData/Local/Programs/Python/Python313/python.exe';
const UTTER = 'tools/utter.py';        // the same voice, gain and limiter every harness plays
const PORT = 9271;                     // nobody else's port; see the port map in the lookbook
const CDP = 'http://127.0.0.1:' + PORT;
const CHROMES = ['C:/Program Files/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Google/Chrome/Application/chrome.exe',
  process.env.LOCALAPPDATA + '/Google/Chrome/Application/chrome.exe'];
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function cdp(path) {
  const res = await fetch(CDP + path);
  return res.json();
}

/* The smallest CDP client that can evaluate one expression. */
class Page {
  constructor(url) { this.url = url; this.id = 0; this.waiting = new Map(); }
  open() {
    return new Promise((resolve, reject) => {
      this.ws = new WebSocket(this.url);
      this.ws.onopen = () => resolve();
      this.ws.onerror = (e) => reject(new Error('ws: ' + (e && e.message)));
      this.ws.onmessage = (ev) => {
        const m = JSON.parse(ev.data);
        if (m.id && this.waiting.has(m.id)) {
          const { resolve: r, reject: j } = this.waiting.get(m.id);
          this.waiting.delete(m.id);
          if (m.error) j(new Error(m.error.message)); else r(m.result);
        }
      };
    });
  }
  send(method, params) {
    const id = ++this.id;
    return new Promise((resolve, reject) => {
      this.waiting.set(id, { resolve, reject });
      this.ws.send(JSON.stringify({ id, method, params: params || {} }));
    });
  }
  async evaluate(expr) {
    const r = await this.send('Runtime.evaluate',
      { expression: expr, awaitPromise: true, returnByValue: true });
    if (r.exceptionDetails) throw new Error('page threw: ' + r.exceptionDetails.text);
    return r.result.value;
  }
}

const profile = mkdtempSync(join(tmpdir(), 'micprobe-'));
let chrome = null;
try {
  const exe = CHROMES.find((p) => existsSync(p));
  if (!exe) throw new Error('no chrome.exe found in the usual places');
  chrome = spawn(exe, [
    '--remote-debugging-port=' + PORT,
    '--user-data-dir=' + profile,
    '--no-first-run', '--no-default-browser-check',
    // A real device, not a fake one: a fake capture device would answer the question wrong
    // on purpose. The fake UI only clicks the permission prompt nobody is here to click.
    '--use-fake-ui-for-media-stream',
    '--autoplay-policy=no-user-gesture-required',
    /* A BACKGROUNDED TAB THROTTLES setInterval TO 1Hz, and the first draft of phase 2 read
       EIGHT frames across a four-second wave and called the eight samples a peak. Both
       numbers were then near the noise floor and would have been believed. */
    '--disable-background-timer-throttling',
    '--disable-backgrounding-occluded-windows',
    '--disable-renderer-backgrounding',
    '--new-window', 'http://127.0.0.1:4700/?mute=1',
  ], { detached: true, stdio: 'ignore' });

  for (let i = 0; i < 60; i++) {
    try { await cdp('/json/version'); break; } catch { await sleep(250); }
  }
  await sleep(2500);
  const target = (await cdp('/json/list'))
    .filter((t) => t.type === 'page').find((t) => t.url.includes('127.0.0.1:4700'));
  if (!target) throw new Error('the viewer tab never appeared');
  const page = new Page(target.webSocketDebuggerUrl);
  await page.open();
  await page.send('Runtime.enable');
  await page.send('Page.enable');
  await page.send('Page.bringToFront');
  /* /json/activate answers "Target activated" in plain text, not JSON, so it cannot go
     through cdp() - which is how the first draft of this line crashed the probe. */
  await fetch(CDP + '/json/activate/' + target.id).catch(() => {});

  /* THE DEFAULT, TAKEN THE ORDINARY WAY. No deviceId constraint: the whole point is to be
     handed whatever Windows calls the default, which is what the recogniser also gets. */
  const out = await page.evaluate(`(async function () {
    const r = { taken: null, settings: null, devices: [], error: '' };
    try {
      const s = await navigator.mediaDevices.getUserMedia({ audio: true });
      const t = s.getAudioTracks()[0];
      r.taken = t && t.label;
      r.settings = t && t.getSettings ? t.getSettings() : null;
      const all = await navigator.mediaDevices.enumerateDevices();
      r.devices = all.filter(function (d) { return d.kind === 'audioinput'; })
        .map(function (d) { return { id: d.deviceId.slice(0, 12), label: d.label }; });
      s.getTracks().forEach(function (x) { x.stop(); });
    } catch (e) { r.error = String(e && e.message || e); }
    return JSON.stringify(r);
  })()`);
  const r = JSON.parse(out);

  console.log('\n  WHICH MICROPHONE THE BROWSER IS HANDED BY DEFAULT');
  console.log('  ' + '-'.repeat(76));
  if (r.error) console.log('  getUserMedia refused: ' + r.error);
  console.log('  the track it took : ' + JSON.stringify(r.taken));
  console.log('  its settings      : ' + JSON.stringify(r.settings));
  console.log('  every audioinput it can see:');
  for (const d of r.devices) console.log('    ' + d.id + '  ' + d.label);
  console.log('  ' + '-'.repeat(76));
  /* The verdict is a reading, not a pass. A harness that failed here would be asserting a
     fact about a desk rather than about the code. */
  const label = String(r.taken || '').toLowerCase();
  if (/headset|hands-free|bluetooth|btg/.test(label)) {
    console.log('  READING: the default capture device is a HEADSET. Every spoken fixture in');
    console.log('  this suite plays out of the laptop speakers, so the recogniser is listening');
    console.log('  to an earcup and the room is not in the signal. Spoken results taken now');
    console.log('  measure the desk and not the machine.');
  } else if (/array|microphone/.test(label)) {
    console.log('  READING: the default capture device is the built-in array - the room IS in');
    console.log('  the signal, so a deaf spoken run is about something else.');
  } else {
    console.log('  READING: unrecognised device; read the label above and decide by hand.');
  }

  /* ---- PHASE 2: BOTH EARS AT ONCE ------------------------------------------
     The label above says which device the page is handed. It does NOT say what each device
     can hear, and that is the actual question: the fixture plays out of the laptop speakers,
     so a microphone in the room should read a level and a microphone in an earcup on a desk
     should read nearly nothing. Opening every real capture device at the same instant and
     playing ONE wave through the room measures both against the same sound, which is the
     only comparison that cannot be confounded by the room changing between two takes. */
  const real = r.devices.filter((d) => d.id !== 'default' && !/^communicatio/.test(d.id));
  if (real.length >= 2) {
    const full = JSON.parse(await page.evaluate(
      '(async function () { const all = await navigator.mediaDevices.enumerateDevices();' +
      'return JSON.stringify(all.filter(function (d) { return d.kind === "audioinput"; })' +
      '.map(function (d) { return { id: d.deviceId, label: d.label }; })); })()'));
    const ids = full.filter((d) => d.id !== 'default' && d.id !== 'communications');
    const armed = await page.evaluate(`(async function () {
      window.__probe = { taps: [] };
      const want = ${JSON.stringify(ids)};
      const ctx = new (window.AudioContext || window.webkitAudioContext)();
      const out = [];
      for (const d of want) {
        try {
          const s = await navigator.mediaDevices.getUserMedia(
            { audio: { deviceId: { exact: d.id } } });
          const an = ctx.createAnalyser();
          an.fftSize = 2048;
          ctx.createMediaStreamSource(s).connect(an);
          const buf = new Float32Array(an.fftSize);
          const tap = { label: d.label, peak: 0, frames: 0, stream: s, an: an, buf: buf };
          window.__probe.taps.push(tap);
          out.push(d.label);
        } catch (e) { out.push(d.label + ' -- REFUSED: ' + (e && e.name)); }
      }
      window.__probe.timer = setInterval(function () {
        for (const t of window.__probe.taps) {
          t.an.getFloatTimeDomainData(t.buf);
          let m = 0;
          for (let i = 0; i < t.buf.length; i++) {
            const v = Math.abs(t.buf[i]);
            if (v > m) m = v;
          }
          if (m > t.peak) t.peak = m;
          t.frames++;
        }
      }, 25);
      return JSON.stringify(out);
    })()`);
    console.log('\n  BOTH EARS AT ONCE - one wave through the room, every device listening');
    console.log('  ' + '-'.repeat(76));
    console.log('  armed: ' + armed);
    await sleep(800);                       // let each analyser settle before the sound
    /* utter.py normalises to 0.22 RMS through a limiter, which is the same wave every
       spoken harness in this suite plays. Anything else would measure a different room. */
    const said = 'tell me about coffee, and what did I write about the grinder';
    const u = spawnSync(PY, [UTTER, '-', said], { encoding: 'utf8' });
    const line = String(u.stdout || '').split(/\r?\n/).find((l) => l.startsWith('UTTER '));
    if (!line) {
      console.log('  utter.py said nothing usable: ' + (u.stderr || u.stdout || '').slice(0, 200));
    } else {
      const wav = JSON.parse(line.slice(6));
      console.log('  playing ' + wav.seconds + 's of piper out of the speakers...');
      spawnSync('powershell', ['-NoProfile', '-Command',
        "(New-Object Media.SoundPlayer '" + String(wav.path).replace(/\\/g, '/') +
        "').PlaySync()"], { encoding: 'utf8' });
    }
    const peaks = JSON.parse(await page.evaluate(`(function () {
      clearInterval(window.__probe.timer);
      const rows = window.__probe.taps.map(function (t) {
        t.stream.getTracks().forEach(function (x) { x.stop(); });
        return { label: t.label, peak: Math.round(t.peak * 100000) / 100000, frames: t.frames };
      });
      return JSON.stringify(rows);
    })()`));
    for (const p of peaks) {
      console.log('    peak ' + String(p.peak).padEnd(9) + ' over ' +
        String(p.frames).padStart(4) + ' frames   ' + p.label);
    }
    console.log('  ' + '-'.repeat(76));
    const room = peaks.find((p) => /array/i.test(p.label));
    const cup = peaks.find((p) => /headset|btg|hands-free/i.test(p.label));
    if (room && cup) {
      console.log('  READING: the room reads ' + room.peak + ' and the headset reads ' +
        cup.peak + '. The recogniser takes the COMMUNICATIONS device, which is the headset,');
      console.log('  so whichever of those two numbers is small is the one it is transcribing.');
    }
  }
  console.log('');
} finally {
  try { if (chrome) { await cdp('/json/close/x').catch(() => {}); } } catch {}
  try { process.kill(-chrome.pid); } catch {}
  try { if (chrome) chrome.kill(); } catch {}
  await sleep(700);
  try { rmSync(profile, { recursive: true, force: true }); } catch {}
}
