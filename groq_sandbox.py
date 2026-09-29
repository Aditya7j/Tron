"""groq_sandbox.py - THE REFUSAL AND THE FALLBACK LAW, PROVED WITHOUT A ROUND TRIP.

WHY THIS FILE EXISTS AT ALL, since groq_proof.mjs already drives the live server. Three of
section 28's laws are about what happens when Groq will NOT answer:

    - empty key or 401: one attempt, a plain refusal naming the config field, provider
      unchanged, a ledger row, and no retry storm;
    - 429 or timeout: that single request goes to today's default for that capability -
      chat to bedrock, stt to the browser, vision to bedrock, tts to Piper - EXACTLY ONCE;
    - and through all of it the key is a digest and nothing else.

None of those can be observed against the real api.groq.com: the key in config.json works, the
account is not rate limited, and a harness cannot ask a third party to fail on cue. The usual
dodge is to assert the ladders by reading the source, which proves the code was typed and not
that it runs. So this file builds a SECOND server out of the same module on another port, with
two things replaced:

    urllib.request.urlopen   only for api.groq.com URLs. Everything else - the harness's own
                             requests to this sandbox, and every other host - goes to the real
                             one untouched, which is also what makes the Groq counter honest:
                             it is incremented in the stub, so it counts requests that actually
                             reached the wire and not calls that were refused before it.
    server.call_bedrock      to a marked sentence, so "the fallback answered" is a string
                             comparison rather than a judgement about prose, and so this file
                             spends nothing at AWS either.

EVERYTHING ELSE IS THE REAL THING: the real routes, the real load_config, the real
credentials_error, the real /say ladder with the real Piper on this machine, the real
multipart reader, the real turn ledger.

CONFIG.JSON IS NEVER WRITTEN. Each case runs against a COPY under _runs/ with one or two
fields changed, and server.CONFIG_PATH is pointed at the copy. The copies are removed on the
way out. The real file is opened once, read, and closed.

AND THE FAKE KEY IS FAKE. It is 'gsk_' and fifty-two zeroes - long enough to pass the empty
check, recognisable in a log, and worth nothing to anybody. Every response body this file
collects is searched for it at the end, which is how "the key never appears in a payload" is
tested rather than hoped for.

Usage:  python groq_sandbox.py            prints one JSON object on stdout
        python groq_sandbox.py --port N   if 4711 is taken
"""
import hashlib
import io
import json
import os
import struct
import sys
import threading
import time
import urllib.error
import urllib.request
from functools import partial
from http.server import ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
RUNS = os.path.join(HERE, "_runs")
sys.path.insert(0, HERE)
import server                                                  # noqa: E402

FAKE_KEY = "gsk_" + "0" * 52
PORT = 4711
BASE = None                                                    # set in main()
REAL_URLOPEN = urllib.request.urlopen
# What the stub should do with the next Groq request, and what it has seen. A list rather than
# a counter for the URLs, because "one attempt" is a claim about WHICH endpoints were called
# and not only how many times.
MODE = {"now": "ok"}
SEEN = []
BODIES = []                                                    # every payload the cases read


def wav_bytes(seconds=0.2, hz=8000):
    """A real WAV, built here: RIFF header, PCM16, one channel, a little silence.

    The /say route checks for b"RIFF" and a floor of 45 bytes before it believes an engine,
    which is exactly the check a canned reply has to satisfy to prove the route's own ladder
    rather than the stub's generosity.
    """
    n = int(seconds * hz)
    data = b"\x00\x00" * n
    return (b"RIFF" + struct.pack("<I", 36 + len(data)) + b"WAVEfmt " +
            struct.pack("<IHHIIHH", 16, 1, 1, hz, hz * 2, 2, 16) +
            b"data" + struct.pack("<I", len(data)) + data)


class Res(io.BytesIO):
    """A urlopen() return value, close enough for the three call sites in server.py."""

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def stub_urlopen(req, *args, **kwargs):
    """Groq's three endpoints, answered from this process. Everything else passes through."""
    url = req.full_url if hasattr(req, "full_url") else str(req)
    if server.GROQ_BASE not in url:
        return REAL_URLOPEN(req, *args, **kwargs)
    SEEN.append(url)
    mode = MODE["now"]
    if mode == "429":
        raise urllib.error.HTTPError(
            url, 429, "Too Many Requests", {},
            io.BytesIO(json.dumps({"error": {"message": "Rate limit reached for model."}})
                       .encode()))
    if mode == "401":
        raise urllib.error.HTTPError(
            url, 401, "Unauthorized", {},
            io.BytesIO(json.dumps({"error": {"message": "Invalid API Key"}}).encode()))
    if mode == "timeout":
        # THE SHAPE URLLIB ACTUALLY DELIVERS. socket.timeout arrives wrapped in URLError, and
        # the whole point of the transient whitelist is that it is read off this class rather
        # than off the sentence, so the sandbox must raise the real one.
        raise urllib.error.URLError(TimeoutError("timed out"))
    if url.endswith("/audio/speech"):
        return Res(wav_bytes())
    if url.endswith("/audio/transcriptions"):
        return Res(json.dumps({"text": "the sandbox heard this line"}).encode())
    return Res(json.dumps({
        "choices": [{"message": {"role": "assistant",
                                 "content": "SANDBOX-GROQ-ANSWER"}}],
        "usage": {"completion_tokens": 4}}).encode())


BEDROCK_MARK = "SANDBOX-BEDROCK-ANSWER"


def stub_bedrock(cfg, messages, image=None):
    return BEDROCK_MARK, None


# ---- driving the sandbox ---------------------------------------------------------------------

def hit(path, body=None, method=None, raw=False, multipart=None):
    """One request to the sandbox. Returns (status, parsed-or-bytes)."""
    data, headers = None, {"User-Agent": "groq-sandbox"}
    if multipart is not None:
        boundary = "----sandbox0000"
        name, blob = multipart
        parts = [("--%s\r\nContent-Disposition: form-data; name=\"%s\"; "
                  "filename=\"utterance.wav\"\r\nContent-Type: audio/wav\r\n\r\n"
                  % (boundary, name)).encode() + blob + b"\r\n",
                 ("--%s--\r\n" % boundary).encode()]
        data = b"".join(parts)
        headers["Content-Type"] = "multipart/form-data; boundary=%s" % boundary
    elif body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(BASE + path, data=data, headers=headers,
                                 method=method or ("POST" if data is not None else "GET"))
    try:
        with REAL_URLOPEN(req, timeout=120) as res:
            blob = res.read()
            code = res.status
    except urllib.error.HTTPError as exc:
        blob, code = exc.read(), exc.code
    BODIES.append(blob)
    if raw:
        return code, blob
    try:
        return code, json.loads(blob.decode("utf-8", "replace"))
    except Exception:                                          # noqa: BLE001
        return code, blob.decode("utf-8", "replace")[:400]


def config_copy(name, **fields):
    """A COPY of config.json with fields overridden, and the server pointed at it."""
    src = os.path.join(HERE, "config.json")
    dst = os.path.join(RUNS, "sandbox-%s.json" % name)
    with open(src, "r", encoding="utf-8") as fh:
        cfg = json.load(fh)
    cfg.update(fields)
    os.makedirs(RUNS, exist_ok=True)
    with open(dst, "w", encoding="utf-8") as fh:
        json.dump(cfg, fh, indent=2)
    server.CONFIG_PATH = dst
    return dst


def reset(**fields):
    """Counters and ledger cleared, overrides dropped, one fresh config copy in place."""
    for k in server._GROQ_SEEN:
        server._GROQ_SEEN[k] = 0
    del server._ENGINE_LOG[:]
    del SEEN[:]
    with server._brain_lock:
        for k in server._engines:
            server._engines[k] = None
        server._chat_engine = None
    return config_copy(fields.pop("_name", "case"), **fields)


def calls():
    return dict(server._GROQ_SEEN)


def ledger():
    return [dict(r) for r in server._ENGINE_LOG]


def main():
    global BASE, PORT
    if "--port" in sys.argv:
        PORT = int(sys.argv[sys.argv.index("--port") + 1])
    BASE = "http://127.0.0.1:%d" % PORT
    out = {"port": PORT,
           "fakeKeyDigest": hashlib.sha256(FAKE_KEY.encode()).hexdigest()[:12],
           "cases": {}}

    urllib.request.urlopen = stub_urlopen
    server.call_bedrock = stub_bedrock
    handler = partial(server.GalaxyHandler, directory=server.VIEWER_DIR)
    httpd = ThreadingHTTPServer(("127.0.0.1", PORT), handler)
    httpd.daemon_threads = True
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    time.sleep(0.4)

    fixture = wav_bytes(0.3)

    # ---- CASE 1: THE BLANK KEY. Every engine asked for Groq, the key taken out of the copy.
    # What must happen: four refusals naming the field, zero requests on the wire, and the
    # switch refused rather than accepted-and-broken.
    reset(_name="nokey", groq_api_key="", provider="groq", ear_stt="groq",
          vision_engine="groq", voice_engine="orpheus")
    case = {}
    code, health = hit("/health")
    case["healthCode"] = code
    case["served"] = (health.get("engines") or {}).get("served")
    case["keyPresent"] = ((health.get("engines") or {}).get("groqKey") or {}).get("present")
    cfg = server.load_config()[0]
    answer, error = server.call_model(cfg, [{"role": "user", "content": "are you there?"}])
    case["chat"] = {"answer": answer, "error": error or "",
                    "namesField": "groq_api_key" in (error or "")}
    code, payload = hit("/say", {"text": "Good evening, sir."})
    case["say"] = {"code": code, "error": (payload or {}).get("error", "")
                   if isinstance(payload, dict) else str(payload)}
    code, payload = hit("/ear/transcribe", multipart=("audio", fixture))
    case["ear"] = {"code": code, "error": (payload or {}).get("error", "")
                   if isinstance(payload, dict) else str(payload)}
    code, payload = hit("/engines", {"chat": "groq"})
    case["flip"] = {"code": code, "refused": (payload or {}).get("refused", ""),
                    "error": (payload or {}).get("error", "")}
    code, payload = hit("/model", {"say": "groq", "door": "curl"})
    case["switch"] = {"code": code, "refused": (payload or {}).get("refused", ""),
                      "error": (payload or {}).get("error", ""),
                      "provider": (payload or {}).get("provider", "")}
    # AND THE PROVIDER AFTER THE REFUSED SWITCH, read from /health rather than from the
    # refusal's own payload: "provider unchanged" is a claim about the next request, and the
    # next request reads load_config().
    code, health = hit("/health")
    case["afterRefusal"] = {"provider": health.get("provider"),
                            "served": (health.get("engines") or {}).get("served"),
                            "overrides": (health.get("engines") or {}).get("overrides")}
    case["calls"] = calls()
    case["wire"] = len(SEEN)
    case["ledger"] = ledger()
    out["cases"]["nokey"] = case

    # ---- CASE 2: A KEY THAT IS ACCEPTED. Every engine on Groq, every canned answer arriving.
    # What must happen: one request per capability, each answer arriving from Groq, and the
    # key absent from every payload.
    reset(_name="ok", groq_api_key=FAKE_KEY, provider="groq", ear_stt="groq",
          vision_engine="groq", voice_engine="orpheus")
    MODE["now"] = "ok"
    case = {}
    cfg = server.load_config()[0]
    answer, error = server.call_model(cfg, [{"role": "user", "content": "are you there?"}])
    case["chat"] = {"answer": answer, "error": error or ""}
    answer, error = server.call_model(cfg, [{"role": "user", "content": "what is this?"}],
                                      image=b"\xff\xd8\xff\xd9")
    case["vision"] = {"answer": answer, "error": error or ""}
    code, blob = hit("/say", {"text": "Good evening, sir."}, raw=True)
    case["say"] = {"code": code, "bytes": len(blob), "riff": blob[:4] == b"RIFF"}
    code, payload = hit("/ear/transcribe", multipart=("audio", fixture))
    case["ear"] = {"code": code, "served": (payload or {}).get("served", ""),
                   "text": (payload or {}).get("text", ""),
                   "fallback": (payload or {}).get("fallback")}
    case["calls"] = calls()
    case["wire"] = list(SEEN)
    case["ledger"] = ledger()
    out["cases"]["ok"] = case

    # ---- CASE 3: 429. THE FALLBACK LAW, one capability at a time.
    # What must happen: each request answered by today's default for that capability, exactly
    # one Groq attempt spent on it, and one ledger row naming the reason.
    reset(_name="429", groq_api_key=FAKE_KEY, provider="groq", ear_stt="groq",
          vision_engine="groq", voice_engine="orpheus")
    MODE["now"] = "429"
    case = {}
    cfg = server.load_config()[0]
    answer, error = server.call_model(cfg, [{"role": "user", "content": "are you there?"}])
    case["chat"] = {"answer": answer, "error": error or "",
                    "fromBedrock": answer == BEDROCK_MARK}
    answer, error = server.call_model(cfg, [{"role": "user", "content": "what is this?"}],
                                      image=b"\xff\xd8\xff\xd9")
    case["vision"] = {"answer": answer, "error": error or "",
                      "fromBedrock": answer == BEDROCK_MARK}
    code, blob = hit("/say", {"text": "Good evening, sir."}, raw=True)
    case["say"] = {"code": code, "bytes": len(blob) if isinstance(blob, bytes) else 0,
                   "riff": isinstance(blob, bytes) and blob[:4] == b"RIFF"}
    code, payload = hit("/ear/transcribe", multipart=("audio", fixture))
    case["ear"] = {"code": code, "served": (payload or {}).get("served", ""),
                   "fallback": (payload or {}).get("fallback"),
                   "reason": (payload or {}).get("reason", "")}
    case["calls"] = calls()
    case["wire"] = list(SEEN)
    case["ledger"] = ledger()
    out["cases"]["429"] = case

    # ---- CASE 4: A TIMEOUT. The same law by the other door - a road rather than a decision.
    reset(_name="timeout", groq_api_key=FAKE_KEY, provider="groq", vision_engine="groq")
    MODE["now"] = "timeout"
    cfg = server.load_config()[0]
    answer, error = server.call_model(cfg, [{"role": "user", "content": "are you there?"}])
    out["cases"]["timeout"] = {"chat": {"answer": answer, "error": error or "",
                                       "fromBedrock": answer == BEDROCK_MARK},
                               "calls": calls(), "wire": list(SEEN), "ledger": ledger()}

    # ---- CASE 5: 401. A WRONG KEY IS A REFUSAL AND NOT A FALLBACK.
    # What must happen: the boss hears the field's name, bedrock is never asked, and the
    # ledger says failed rather than fallback. This is the case that would be invisible if
    # every error fell back: a broken config.json that sounds perfectly fine.
    reset(_name="401", groq_api_key=FAKE_KEY, provider="groq", ear_stt="groq",
          vision_engine="groq", voice_engine="orpheus")
    MODE["now"] = "401"
    case = {}
    cfg = server.load_config()[0]
    answer, error = server.call_model(cfg, [{"role": "user", "content": "are you there?"}])
    case["chat"] = {"answer": answer, "error": error or "",
                    "fromBedrock": answer == BEDROCK_MARK,
                    "namesConfig": "config.json" in (error or "")}
    code, payload = hit("/say", {"text": "Good evening, sir."})
    case["say"] = {"code": code,
                   "error": (payload or {}).get("error", "") if isinstance(payload, dict)
                   else str(payload)[:200]}
    code, payload = hit("/ear/transcribe", multipart=("audio", fixture))
    case["ear"] = {"code": code, "served": (payload or {}).get("served", ""),
                   "fallback": (payload or {}).get("fallback"),
                   "error": (payload or {}).get("error", "")}
    case["calls"] = calls()
    case["wire"] = list(SEEN)
    case["ledger"] = ledger()
    out["cases"]["401"] = case

    # ---- CASE 6: THE FLAGS ARE INDEPENDENT. One engine flipped, the other three unmoved.
    reset(_name="flags", groq_api_key=FAKE_KEY)
    MODE["now"] = "ok"
    case = {"steps": []}
    code, payload = hit("/health")
    case["steps"].append({"step": "start", "code": code,
                          "engines": (payload.get("engines") or {})})
    for which, word in (("voice", "orpheus"), ("ear", "groq"), ("vision", "groq"),
                        ("chat", "groq")):
        code, payload = hit("/engines", {which: word})
        case["steps"].append({"step": which + "=" + word, "code": code,
                              "engines": payload.get("engines") or {}})
    code, payload = hit("/engines", {"voice": "gibberish"})
    case["refusedWord"] = {"code": code, "error": (payload or {}).get("error", ""),
                           "engines": payload.get("engines") or {}}
    code, payload = hit("/engines", {"reset": True})
    case["afterReset"] = {"code": code, "engines": payload.get("engines") or {}}
    out["cases"]["flags"] = case

    # ---- AND THE KEY, LOOKED FOR IN EVERYTHING THIS FILE COLLECTED.
    blob = b"".join(BODIES) + json.dumps(out).encode()
    out["keyInPayloads"] = FAKE_KEY.encode() in blob
    out["keyPrefixOnly"] = b"gsk_" in blob and FAKE_KEY.encode() not in blob

    httpd.shutdown()
    urllib.request.urlopen = REAL_URLOPEN
    for name in ("nokey", "ok", "429", "timeout", "401", "flags", "case"):
        path = os.path.join(RUNS, "sandbox-%s.json" % name)
        try:
            os.remove(path)
        except OSError:
            pass
    out["copiesRemoved"] = not any(
        os.path.exists(os.path.join(RUNS, "sandbox-%s.json" % n))
        for n in ("nokey", "ok", "429", "timeout", "401", "flags"))
    # TO A FILE AND NOT TO STDOUT, because ensure_index() prints "brain loaded 23 notes" on its
    # way through and a caller parsing stdout as JSON would trip over it. The one line printed
    # is the path, so a human running this by hand still knows where the answer went.
    os.makedirs(RUNS, exist_ok=True)
    dest = os.path.join(RUNS, "groq_sandbox.json")
    if "--out" in sys.argv:
        dest = sys.argv[sys.argv.index("--out") + 1]
    with open(dest, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1)
    print("groq_sandbox: %s" % dest)


if __name__ == "__main__":
    main()
