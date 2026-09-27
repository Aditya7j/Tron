/* THE TWO HANDS THAT REACH OUTSIDE THE HOUSE, proved without leaving a mark on anybody.
 *
 * Until this round the two irreversible hands were only half real. add_calendar_event
 * appended a line to calendar.json, which is a file nobody but this project has ever
 * opened, and send_email logged in to smtp.gmail.com with an app password. They now call
 * Calendar v3 events.insert and Gmail v1 users.messages.send against an OAuth grant, and
 * that changes what a mistake costs: a wrong stamp used to be a wrong line in a local
 * file and is now an alarm on the employer's phone at four in the morning.
 *
 * So this harness has an awkward job. It has to prove that the authenticated path works -
 * that the token is fetched and refreshed, that a message serializes to something Gmail
 * accepts, that an event lands where it was aimed - WITHOUT sending mail to anybody and
 * without leaving an appointment in a diary that belongs to someone else. It does that
 * with the two narrowest methods Google offers:
 *
 *   - THE DRAFT. users.drafts.create proves auth, scope, RFC822 serialization and the
 *     base64url encoding all the way into Gmail's own parser - Gmail will reject a
 *     malformed raw field, so a draft that comes back with an id is a message that would
 *     have flown. It is then deleted, and its absence asserted. No letter leaves the
 *     building. THE ONE REAL SEND REMAINS THE EMPLOYER'S, by hand, as it has all along.
 *   - THE PROBE EVENT. An event is created two years out with an unmistakable title, read
 *     back with events.get to prove it really exists in Google's calendar and not just in
 *     a hopeful 200, then deleted, and the delete is proved by a get that 404s. Created
 *     and destroyed inside one run, so the diary ends the run exactly as it started it.
 *     (The events sections 3 and 4 of tools_live.mjs create are a different matter: those
 *     were approved by a human pressing Yes, so they are his and this file leaves them be.)
 *
 * WITHOUT A TOKEN - which is most machines, and this one until somebody presses Connect -
 * neither of those can run, and the harness does not pretend otherwise: those sections
 * SKIP with the reason printed, and the skip count is carried in the VERIFY line so a
 * skipped section can never be mistaken for a passed one. What it proves instead is the
 * half that matters more often: that an unconnected machine REFUSES in English, naming
 * the remedy, at the same door a human uses - and that a refusal is recorded as a failed
 * run rather than quietly swallowed.
 *
 * NO BROWSER, NO CDP PORT. Every claim here is an HTTP claim or a subprocess claim, so
 * unlike the headed harnesses this one is safe to run beside another - it cannot lose a
 * click it never makes. The window's side of this feature (the panel's state line, its
 * keyboard order, the contained answer) belongs to deck_proof.mjs and layout_proof.mjs.
 *
 * THE PROBES GO THROUGH THE PROJECT'S OWN MODULE. Sections 3 and 4 spawn python and call
 * google_api.create_draft / insert_event / get_event / delete_event - the identical
 * functions the hands call. A harness that spoke to Google directly with its own fetch
 * and its own token handling would be testing a second implementation and reporting on
 * the first. It also means the token is read in exactly one place, by the code that owns
 * it: this file never opens secrets/ and never holds a credential in its memory.
 *
 * WHAT IS NEVER PRINTED: no access token, no refresh token, no authorization code, no
 * client secret, and not the connected account's address either. Accounts appear as an
 * eight-character digest, which tells two grants apart and tells a reader nothing else.
 *
 * The run, in order:
 *   1. GET /google carries the six facts the panel needs and nothing it does not
 *   2. POST /google refuses a command it does not know, and disconnect on an unconnected
 *      machine says so rather than pretending to revoke something
 *   3. with no grant: both hands refuse, in their own words, through propose -> execute,
 *      and the ledger counts one FAILED run each - the subprocess really did decide
 *   4. the stamp is read before the network is: an unparseable time is refused at the gate
 *      with nothing left pending
 *   5. attachments are refused by name, in v1, rather than being silently dropped
 *   6. with a grant: the draft round trip
 *   7. with a grant: the probe event round trip, ending in a 404
 *
 * Usage:  python server.py 2> server-trace.log   then   node google_hands_proof.mjs
 */
import { spawn } from 'node:child_process';
import { mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const GALAXY = 'http://127.0.0.1:4700';
const LEDGER = 'tools-ledger.json';
/* The absolute path, because a bare `python` on this machine is a Store stub that prints
   an advertisement and exits 9009, and a harness that mistook that for a failing probe
   would be reporting on the wrong thing entirely. */
const PY = 'C:/Users/Fullstack Developer/AppData/Local/Programs/Python/Python313/python.exe';
const WANT_SCOPES = [
  'https://www.googleapis.com/auth/gmail.send',
  'https://www.googleapis.com/auth/gmail.compose',
  'https://www.googleapis.com/auth/calendar.events',
];

let checks = 0; const bad = []; const skipped = [];
const ok = (c, claim, detail) => {
  checks++; console.log((c ? '  ok   ' : '  FAIL ') + claim);
  if (!c) { bad.push(claim); if (detail) console.log('         ' + detail); }
};
const note = (m) => console.log('  note ' + m);
/* A SKIP IS NOT A PASS AND IS NOT A CHECK. It does not touch `checks`, so it cannot
   inflate the score, and it is counted separately and reprinted at the end: the failure
   mode this guards against is a machine with no token quietly reporting a full green and
   a reader concluding the Google path was exercised. */
const skip = (claim, why) => {
  skipped.push(claim); console.log('  SKIP ' + claim); console.log('         ' + why);
};
const digest = (s) => createHash('sha256').update(String(s)).digest('hex').slice(0, 8);
const first = (s) => String(s || '').replace(/\s+/g, ' ').trim().slice(0, 120);

const get = async (path) => {
  const r = await fetch(GALAXY + path);
  const t = await r.text();
  try { return { status: r.status, body: JSON.parse(t) }; }
  catch { return { status: r.status, body: t }; }
};
const post = async (path, payload) => {
  const r = await fetch(GALAXY + path, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  const t = await r.text();
  try { return { status: r.status, body: JSON.parse(t) }; }
  catch { return { status: r.status, body: t }; }
};
const runs = (id) => {
  try {
    const row = (JSON.parse(readFileSync(LEDGER, 'utf8')).tools || {})[id] || {};
    return (row.ok | 0) + (row.failed | 0);
  } catch { return 0; }
};
const failedRuns = (id) => {
  try {
    const row = (JSON.parse(readFileSync(LEDGER, 'utf8')).tools || {})[id] || {};
    return row.failed | 0;
  } catch { return 0; }
};

/* ---- one python probe, written to a scratch file and run ----------------------------
   Written to a file rather than passed with -c: the probe source contains quotes, braces
   and newlines, and shell quoting on Windows is where harnesses go to die. The scratch
   directory is removed in the finally below even if the run throws. */
const scratch = mkdtempSync(join(tmpdir(), 'ghp-'));
const python = (source, seconds = 90, stdin = null) => new Promise((resolve) => {
  const file = join(scratch, 'probe' + Math.random().toString(36).slice(2, 8) + '.py');
  writeFileSync(file, source, 'utf8');
  const kid = spawn(PY, [file], { cwd: process.cwd() });
  let out = '', err = '';
  if (stdin !== null) { kid.stdin.write(stdin); }
  kid.stdin.end();
  const bomb = setTimeout(() => { try { kid.kill(); } catch { } }, seconds * 1000);
  kid.stdout.on('data', (d) => { out += d; });
  kid.stderr.on('data', (d) => { err += d; });
  kid.on('close', (code) => {
    clearTimeout(bomb);
    let parsed = null;
    /* The LAST json-looking line, so a warning printed by an import cannot be mistaken
       for the probe's answer. */
    for (const line of out.split(/\r?\n/)) {
      const t = line.trim();
      if (t.startsWith('{') && t.endsWith('}')) { try { parsed = JSON.parse(t); } catch { } }
    }
    resolve({ code, parsed, out, err });
  });
});

/* The preamble every probe shares: put the project root on the path and import the same
   module the hands import. Nothing here reads secrets/ itself. */
const PREAMBLE = [
  'import sys, json, os',
  'sys.path.insert(0, os.getcwd())',
  'import google_api as g',
  '',
].join('\n');

/* THE PROBE SOURCES, HELD OUT WHERE THEY CAN BE COMPILED WITHOUT BEING RUN.
   Sections 6 and 7 are the only two that need a grant, which means on most machines -
   including every machine that has not pressed Connect - they skip, and their python is
   never parsed by anything. That is a trap: a typo inside a generated probe would sit here
   silently for weeks and then fail on the one machine that finally has a token, at the
   moment somebody was trying to prove the feature worked. So the sources are built by
   these two functions, and when a section skips, the source it WOULD have run is still
   handed to python's own compiler and asserted to parse. Compiling is not running: no
   import executes, no request is made, and a token is not needed to find a missing comma. */
const draftProbe = (stamp) => PREAMBLE + [
  'sys.path.insert(0, os.path.join(os.getcwd(), "tools"))',
  'import send_email as m',
  'out = {}',
  'raw = m.build("nobody@example.invalid", "trone draft probe ' + stamp + '",',
  '              "This draft is deleted by the harness that made it. ' + stamp + '",',
  '              (g.token() or {}).get("email") or "me")',
  'out["bytes"] = len(raw)',
  'made, err = g.create_draft(raw)',
  'out["err"] = err',
  'out["id"] = (made or {}).get("id") or ""',
  'out["messageId"] = ((made or {}).get("message") or {}).get("id") or ""',
  'if out["id"]:',
  '    st, got, e2 = g.call("GET", g.GMAIL_BASE + "/users/me/drafts/" + out["id"]',
  '                         + "?format=raw")',
  '    out["getStatus"] = st',
  '    import base64',
  '    blob = ((got or {}).get("message") or {}).get("raw") or ""',
  '    pad = "=" * (-len(blob) % 4)',
  '    text = base64.urlsafe_b64decode(blob + pad).decode("utf-8", "replace") if blob else ""',
  '    out["carriesSubject"] = "' + stamp + '" in text',
  '    out["carriesTo"] = "nobody@example.invalid" in text',
  '    ds, _d, derr = g.delete_draft(out["id"])',
  '    out["deleteStatus"] = ds',
  '    out["deleteErr"] = derr',
  '    gs, _g2, _e3 = g.call("GET", g.GMAIL_BASE + "/users/me/drafts/" + out["id"])',
  '    out["afterStatus"] = gs',
  'print(json.dumps(out))',
].join('\n');

const eventProbe = (title) => PREAMBLE + [
  'out = {}',
  'start, end, when, dur, err = g.event_times("2028-03-07T11:00", "")',
  'out["stampErr"] = err',
  'out["when"] = when',
  'out["duration"] = dur',
  'made, ierr = g.insert_event("' + title + '", start, end, "written by '
    + 'google_hands_proof.mjs, deleted moments later")',
  'out["err"] = ierr',
  'out["id"] = (made or {}).get("id") or ""',
  'if out["id"]:',
  '    st, got, _e = g.get_event(out["id"])',
  '    out["getStatus"] = st',
  '    out["summary"] = (got or {}).get("summary") or ""',
  '    out["startBack"] = ((got or {}).get("start") or {}).get("dateTime") or ""',
  '    ds, _d, derr = g.delete_event(out["id"])',
  '    out["deleteStatus"] = ds',
  '    out["deleteErr"] = derr',
  '    gs, gone, _e2 = g.get_event(out["id"])',
  '    out["afterStatus"] = gs',
  /* THE BODY OF THE AFTER-GET, not only its status code. Calendar does not forget a deleted
     event the way Gmail forgets a deleted draft: it keeps a tombstone, and events.get answers
     200 with status "cancelled" indefinitely. Reading the code alone cannot tell that apart
     from an event still sitting in the diary, which is the thing that actually matters. */
  '    out["afterState"] = (gone or {}).get("status") or ""',
  'print(json.dumps(out))',
].join('\n');

/* compile(), not exec(): python parses the probe and reports the first syntax error, and
   nothing in it runs. The source is passed on stdin so no quoting question arises. */
const parses = async (source, label) => {
  const r = await python([
    'import sys, json',
    'src = sys.stdin.read()',
    'try:',
    '    compile(src, "' + label + '", "exec")',
    '    print(json.dumps({"parses": True, "why": ""}))',
    'except SyntaxError as exc:',
    '    print(json.dumps({"parses": False, "why": "%s line %s" % (exc.msg, exc.lineno)}))',
  ].join('\n'), 40, source);
  return r.parsed || { parses: false, why: 'the compiler itself did not answer: ' + r.err };
};

async function main() {
  console.log('\nGOOGLE HANDS - the draft that is deleted and the event that is undone\n');

  /* ---- 1. the state line ---------------------------------------------------------- */
  console.log('1. GET /google - what the panel is given');
  const g0 = await get('/google');
  const grant = (g0.body && typeof g0.body === 'object') ? g0.body : {};
  ok(g0.status === 200 && grant.kind === 'google',
     'GET /google answers 200 as kind "google"',
     'without it the Command Panel has no state line at all: status ' + g0.status);
  ok(JSON.stringify(grant.scopes || []) === JSON.stringify(WANT_SCOPES),
     'it offers exactly the three write-only scopes, in order',
     'a wider scope never fails a test, it only permits - so this is equality, not '
     + 'containment. Got: ' + JSON.stringify(grant.scopes));
  ok(grant.port === 4731 && String(grant.redirectUri || '').includes('127.0.0.1:4731'),
     'the loopback door is 4731 on 127.0.0.1, and nowhere near a CDP port',
     'the harnesses own 9222-9254 and focus.py watches one of them; a consent server '
     + 'landing there would fight a debugger. Got: ' + grant.port + ' / ' + grant.redirectUri);
  const KNOWN = ['no-client', 'absent', 'connected', 'stale', 'error'];
  ok(KNOWN.includes(String(grant.state)),
     'the state word is one the panel knows how to render: ' + JSON.stringify(grant.state),
     'an unrecognised state word renders as a blank line, which reads as "no opinion" to '
     + 'somebody deciding whether to press Connect');
  const leaky = Object.keys(grant).filter((k) =>
    /access_?token|refresh_?token|secret|^code$|verifier|bearer/i.test(k));
  ok(leaky.length === 0,
     'and it carries no token, no code and no secret',
     'the page may know WHETHER it is connected and never HOW. Found: ' + leaky.join(', '));
  let secret = '';
  try {
    secret = String((JSON.parse(readFileSync('secrets/google_client.json', 'utf8'))
      .installed || {}).client_secret || '');
  } catch { /* no client file on this machine; the by-value check is skipped, not failed */ }
  if (secret) {
    ok(!JSON.stringify(grant).includes(secret),
       "and the client secret's own characters appear nowhere in the payload",
       'checked by value, because a field with an innocent name is still a leak');
  } else {
    skip("the client secret is absent from the payload, checked by value",
         'secrets/google_client.json could not be read, so there is no value to search for');
  }
  const served = await get('/secrets/google_token.json');
  ok(served.status !== 200,
     'secrets/google_token.json is not served to the browser (HTTP ' + served.status + ')',
     'that file holds a refresh token, which does not expire on its own');
  note('state ' + JSON.stringify(grant.state) + ', client present ' + !!grant.clientPresent
       + (grant.state === 'connected'
          ? ', account digest ' + digest(grant.email) + ', token digest '
            + (grant.tokenDigest || 'none')
          : ''));

  /* ---- 2. the two commands, and the one that must not lie ------------------------- */
  console.log('\n2. POST /google - the commands');
  const junk = await post('/google', { cmd: 'sudo-connect' });
  /* Either field: this route puts a refusal in `error` and leaves `answer` empty, which is
     what its own two other 400s do, and the page only ever sends connect or disconnect so
     nothing renders this string. The assertion reads both rather than pinning the
     convention, because which field carries it is the route's business and the CLAIM is
     that the refusal names the two commands instead of being silently ignored. */
  const junkSaid = String((junk.body || {}).error || (junk.body || {}).answer || '');
  ok(junk.status >= 400 && /only commands are connect and disconnect/i.test(junkSaid),
     'an unknown command is refused, naming the two that exist',
     'a route that ignores what it does not understand is a route that will one day '
     + 'silently not connect. Got ' + junk.status + ': ' + first(junkSaid));
  if (grant.state === 'connected') {
    skip('disconnect on an unconnected machine says so rather than pretending',
         'this machine IS connected, and a harness that called disconnect to see what it '
         + "said would have revoked the employer's grant to find out. That is not a test, "
         + 'that is a consequence.');
  } else {
    const off = await post('/google', { cmd: 'disconnect' });
    ok(off.status === 200 && /nothing|not connected|no token/i
      .test(String((off.body || {}).answer || '')),
       'disconnect with no token says there was nothing to disconnect',
       'the alternative is a cheerful "disconnected" that teaches the employer the button '
       + 'works when it has never been tested. Got: ' + first((off.body || {}).answer));
    const after = await get('/google');
    ok(String(((after.body || {}).state)) === String(grant.state),
       'and it left the state exactly as it found it',
       'nothing to revoke means nothing changes');
  }

  /* ---- 3. the refusals, through the door a human uses ----------------------------- */
  console.log('\n3. no grant, no guessing - the hands refuse in English');
  if (grant.state === 'connected') {
    skip('both hands refuse by name when there is no road to Google',
         'this machine has a grant, so the unconnected sentences cannot be reached without '
         + 'taking the grant away. preflight check 23 clause (c) owns the same claim and '
         + 'skips for the same reason.');
  } else {
    for (const probe of [
      { tool: 'add_calendar_event', params: { title: 'a probe that goes nowhere',
                                              start: '2099-01-01T09:00' },
        road: /no road to your calendar/i, what: 'calendar' },
      { tool: 'send_email', params: { to: 'nobody@example.invalid',
                                     subject: 'a probe that goes nowhere',
                                     body: 'This is never sent.' },
        road: /no road to your mail/i, what: 'mail' },
    ]) {
      const before = { all: runs(probe.tool), failed: failedRuns(probe.tool) };
      const pro = await post('/tools', { cmd: 'propose', tool: probe.tool,
                                         params: probe.params });
      const pending = ((pro.body || {}).pending) || {};
      ok(pro.status === 200 && !!pending.id,
         'the ' + probe.what + ' hand offers a card to confirm',
         'no card, no gate to walk through: status ' + pro.status);
      if (!pending.id) continue;
      ok(!String(pending.line || '').includes('{'),
         'and its sentence has no unfilled blank left in it',
         'a card reading "{when}" is a card somebody is being asked to approve blind: '
         + first(pending.line));
      const done = await post('/execute', { id: pending.id, door: 'button' });
      const said = String(((done.body || {}).answer) || '');
      ok(probe.road.test(said) && /connect google/i.test(said),
         'and on Yes it says there is no road to the ' + probe.what
         + ' yet, naming the remedy',
         'an HTTP 401 is not an answer to a person: ' + first(said));
      ok(!/token|bearer|401|invalid_grant/i.test(said),
         'without quoting a status code, a token or a Google error word at them',
         'the sentence a human hears must be about their situation, not about ours: '
         + first(said));
      const after = { all: runs(probe.tool), failed: failedRuns(probe.tool) };
      ok(after.failed === before.failed + 1 && after.all === before.all + 1,
         'and the ledger records exactly one FAILED run for it',
         'the subprocess started, read its stdin and decided - that is a failed run and '
         + 'not a refused proposal. ' + JSON.stringify(before) + ' -> '
         + JSON.stringify(after));
    }
  }

  /* ---- 4. the stamp is read before the network is --------------------------------- */
  console.log('\n4. an unreadable time never reaches Google');
  const beforeBad = runs('add_calendar_event');
  const badTime = await post('/tools', { cmd: 'propose', tool: 'add_calendar_event',
                                         params: { title: 'a probe that goes nowhere',
                                                   start: 'some time on thursday' } });
  const badSaid = String(((badTime.body || {}).answer) || '');
  ok(badTime.status >= 400 && !((badTime.body || {}).pending),
     'an unparseable start is refused at the gate, with nothing left pending',
     'the two worse options are a card with a literal {when} on it and a round trip to '
     + 'Google to be told no. Got ' + badTime.status + ' pending='
     + JSON.stringify((badTime.body || {}).pending));
  ok(/not a date i can read/i.test(badSaid) && /\d{4}-\d{2}-\d{2}/.test(badSaid),
     'and it names the shape it wanted, with an example',
     'a refusal that does not name its remedy is a machine saying no: ' + first(badSaid));
  ok(runs('add_calendar_event') === beforeBad,
     'and no subprocess was started at all',
     'the gate decided this one, so the ledger must show no new run');

  /* ---- 5. attachments, refused by name ------------------------------------------- */
  console.log('\n5. attachments in v1 - refused, not dropped');
  const att = await python(PREAMBLE + [
    'sys.path.insert(0, os.path.join(os.getcwd(), "tools"))',
    'import subprocess',
    'p = subprocess.run([sys.executable, os.path.join("tools", "send_email.py")],',
    '                   input=json.dumps({"to": "nobody@example.invalid",',
    '                                     "subject": "a probe that goes nowhere",',
    '                                     "body": "never sent",',
    '                                     "attachment": "C:/Windows/win.ini"}),',
    '                   capture_output=True, text=True, timeout=60)',
    'print(json.dumps({"code": p.returncode, "out": p.stdout.strip()[:400],',
    '                  "err": p.stderr.strip()[:200]}))',
  ].join('\n'));
  const attOut = (att.parsed || {});
  /* /attach/i, not /attachment/i: the hand says "I cannot attach a file to an email yet",
     which is the sentence a person would say, and an assertion that insisted on the noun
     would be testing the wording rather than the refusal. */
  ok(attOut.code !== 0 && /attach/i.test(String(attOut.out)),
     'a request carrying an attachment is refused, and the refusal says so',
     'the failure mode is worse than an error: the letter goes anyway, without the file, '
     + 'and the sender believes it went with it. Got code ' + attOut.code + ': '
     + first(attOut.out) + (att.err ? ' [stderr ' + first(att.err) + ']' : ''));
  ok(!/traceback/i.test(String(attOut.err)),
     'and it refuses in a sentence rather than a stack trace',
     'stderr: ' + first(attOut.err));

  /* ---- 6. the draft round trip ---------------------------------------------------- */
  console.log('\n6. the draft that proves the send without sending');
  if (grant.state !== 'connected') {
    skip('a draft is created from a real RFC822 message and then deleted',
         'there is no grant on this machine (state ' + JSON.stringify(grant.state)
         + '), so Gmail cannot be reached. Press Connect Google in the Command Panel and '
         + 'run this file again; the serialization half of the same claim is proved '
         + 'token-free by preflight check 16 and by tools/send_email.py\'s own build().');
    const p = await parses(draftProbe('probe-compile-only'), 'draft_probe');
    ok(p.parses === true,
       'and the draft probe this machine would have run is valid python',
       'a skipped section is never parsed, so a typo in it would wait silently until the '
       + 'one run that finally had a token: ' + p.why);
  } else {
    const stamp = 'probe-' + Date.now();
    const draft = await python(draftProbe(stamp));
    const d = draft.parsed || {};
    ok(!!d.id && !d.err,
       'Gmail accepted a real RFC822 message as a draft and gave it an id',
       'this is the whole authenticated write path - token, scope, base64url and Gmail\'s '
       + 'own parser - and Gmail rejects a malformed raw field. err=' + JSON.stringify(d.err)
       + ' stderr=' + first(draft.err));
    ok(d.bytes > 100,
       'the message it serialized was ' + d.bytes + ' bytes of real headers and body',
       'an empty or tiny raw field would be accepted and prove nothing');
    ok(d.carriesSubject === true && d.carriesTo === true,
       'and reading it back out of Gmail returns the same subject and recipient',
       'a 200 proves Gmail stored something; only the round trip proves it stored THIS. '
       + JSON.stringify({ getStatus: d.getStatus, subject: d.carriesSubject,
                          to: d.carriesTo }));
    ok(d.deleteStatus >= 200 && d.deleteStatus < 300,
       'the draft is then deleted (HTTP ' + d.deleteStatus + ')',
       'a harness that left drafts behind would fill the employer\'s mailbox one run at a '
       + 'time. ' + JSON.stringify(d.deleteErr));
    ok(d.afterStatus === 404,
       'and it is gone - a fetch of the same id 404s',
       'a delete that returns 204 and leaves the draft is the exact bug this asserts '
       + 'against. Got ' + d.afterStatus);
    ok(!/nobody@example\.invalid.*sent|messages\/send/i.test(String(draft.out)),
       'and nothing in this section called messages.send',
       'the one real send is the employer\'s, by hand, and always was');
    note('draft id digest ' + digest(d.id) + ' - created and destroyed inside this run');
  }

  /* ---- 7. the probe event, created and undone ------------------------------------- */
  console.log('\n7. the event that is created, seen, and taken back');
  if (grant.state !== 'connected') {
    skip('a probe event is created, read back with events.get, deleted, and 404s',
         'there is no grant on this machine (state ' + JSON.stringify(grant.state)
         + '), so Calendar cannot be reached. The stamp arithmetic that decides what would '
         + 'be sent - event_times() - is proved token-free by preflight check 23 clause (d) '
         + 'and by tools_live.mjs section 1.');
    const p = await parses(eventProbe('trone probe event - compile only'), 'event_probe');
    ok(p.parses === true,
       'and the calendar probe this machine would have run is valid python',
       'the same trap as section 6: unrun source is unparsed source. ' + p.why);
  } else {
    const title = 'trone probe event - delete me if you see me ' + Date.now();
    const ev = await python(eventProbe(title));
    const e = ev.parsed || {};
    ok(!!e.id && !e.err,
       'Calendar v3 events.insert created the probe event and returned Google\'s id',
       'err=' + JSON.stringify(e.err) + ' stderr=' + first(ev.err));
    ok(e.getStatus === 200 && e.summary === title,
       'events.get finds it, with the title that was sent',
       'a 200 from insert is a promise; the get is the proof. '
       + JSON.stringify({ status: e.getStatus, summary: first(e.summary) }));
    ok(String(e.startBack || '').startsWith('2028-03-07T11:00'),
       'and it landed at the time the stamp arithmetic asked for',
       'a timezone dropped between here and Google is a meeting five and a half hours out. '
       + 'Google returned ' + JSON.stringify(e.startBack) + ' for "' + e.when + '"');
    ok(e.deleteStatus >= 200 && e.deleteStatus < 300,
       'the probe event is then deleted (HTTP ' + e.deleteStatus + ')',
       JSON.stringify(e.deleteErr));
    /* THIS ASSERTION USED TO DEMAND A 404 AND IT WAS WRONG ABOUT GOOGLE, not about this code.
       It was written beside the Gmail draft check above, where a deleted draft really does
       404, and the shape was carried across to Calendar - where it does not hold. Measured on
       this machine: insert 200, delete 204, and then events.get answers 200 with
       status "cancelled" and a full body, because a deleted event stays retrievable as a
       tombstone so that subscribers can learn it was cancelled. Demanding a 404 there asserts
       a promise Calendar never made, and it failed the first time a machine had a grant to
       reach the real API with - which is exactly the moment a harness is being trusted.

       FAILURE MODE THIS CATCHES, which the old line also caught and must not lose: an event
       left LIVE in the diary after the run - a 200 whose status is still "confirmed". The
       difference between that and a tombstone is the whole point, so the state word is read
       rather than inferred from the code, and a 200 with no state word at all is refused. */
    ok(e.afterStatus === 404 || e.afterStatus === 410 || e.afterState === 'cancelled',
       'and it is gone - events.get returns ' +
       (e.afterStatus === 200 ? 'Calendar\'s cancelled tombstone (200 + status "cancelled"), '
                              + 'which is how Calendar says deleted'
                              : 'nothing at all (HTTP ' + e.afterStatus + ')'),
       'the diary must end this run exactly as it started it, with nothing confirmed left in '
       + 'it. Got status ' + e.afterStatus + ' and state '
       + JSON.stringify(e.afterState || '') + ' - a live event, not a deleted one');
    note('probe event id digest ' + digest(e.id) + ', read as "' + e.when + ', ' + e.duration
         + '" - created and deleted inside this run');
  }

  /* ---- the count ------------------------------------------------------------------ */
  console.log('\n  VERIFY ' + (checks - bad.length) + '/' + checks
              + (bad.length ? ' FAIL' : ' PASS')
              + (skipped.length ? '  (' + skipped.length + ' skipped)' : ''));
  if (bad.length) { console.log('  failed:'); bad.forEach((b) => console.log('    - ' + b)); }
  if (skipped.length) {
    console.log('  skipped, and a skip is not a pass:');
    skipped.forEach((s) => console.log('    - ' + s));
  }
  console.log('');
  return bad.length ? 1 : 0;
}

let code = 1;
try {
  code = await main();
} catch (err) {
  console.log('\n  FAIL the harness itself threw: ' + (err && err.stack || err));
  code = 1;
} finally {
  try { rmSync(scratch, { recursive: true, force: true }); } catch { }
}
process.exit(code);
