#!/usr/bin/env python3
"""broadcast.py - the Broadcaster. The Director's films leave the machine, and nothing deletes.

§40. This is the narrowest hand in the house and the only one whose mistakes are PUBLIC, so it
is also the most heavily fenced. Four laws, and each one is a property of this file rather than
a promise made about it:

  UPLOAD-ONLY. There is no code path in this module that can issue an HTTP DELETE. Not "no
    delete is called today" - no delete is ISSUABLE: _http() checks its method against
    METHODS_ALLOWED and raises before a socket is opened. The scope Google forces on us
    (see SCOPES) permits videos.delete, so the prohibition cannot be bought with a scope and
    has to be written in code. broadcaster_proof scans this source for it AND calls _http
    with "DELETE" to watch it refuse.

  UNLISTED FIRST, ALWAYS. insert() takes no privacy argument. It writes PRIVACY_FIRST and
    nothing else, so "every upload lands unlisted" is not a convention a caller can forget -
    there is no parameter to get wrong. Public is a SECOND, separate call that a human has to
    approve out loud.

  THE PACKAGE IS BUILT FROM THE FILM, NOT FROM A MODEL. package() reads the Director's own
    script.md: its topic, its first narration line, the notes it cited. No model call, no
    invented claim, no keyword a human did not write. The one line this module cannot derive -
    the boss's affiliate disclosure - it REFUSES to invent and refuses to proceed without.

  NOTHING HERE PRINTS A CREDENTIAL. The token lives in secrets/youtube_token.json, which is
    inside the folder .gitignore already excludes wholesale, and status() reports a digest of
    the refresh token and never the token. The same law google_api.py works under.

WHY ITS OWN OAUTH AND NOT google_api.py's. Two reasons, both load-bearing. The first is the
scope list: google_api.py's three scopes are asserted by preflight and are deliberately as
narrow as Gmail and Calendar allow, and widening that grant to carry YouTube would make one
consent screen that asks for mail, diary and a channel together - so a boss who wanted to give
this machine a channel would have to re-approve his mailbox at the same time, and a revoked
channel would take the mail with it. Two grants, two token files, two consent screens that each
say one true thing. The second is the transport: a resumable upload is a binary PUT with a
Content-Range header and a 308 reply, and google_api.call() parses JSON and knows nothing about
either. Reusing it would have meant widening it for a case it was not built for.

WHAT IS SHARED is the client file - secrets/google_client.json, one Google Cloud project, one
downloaded OAuth client - because that genuinely IS the same thing, and a second client file
would be a second thing for the boss to download for no gain.
"""

import base64
import hashlib
import io
import json
import os
import pathlib
import re
import secrets as secretslib
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

import google_api                      # for client(), and for nothing else

ROOT = pathlib.Path(__file__).resolve().parent
SECRETS = ROOT / "secrets"
TOKEN_FILE = SECRETS / "youtube_token.json"

AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
API_BASE = "https://www.googleapis.com/youtube/v3"
UPLOAD_BASE = "https://www.googleapis.com/upload/youtube/v3"
DISCOVERY_URL = "https://www.googleapis.com/discovery/v1/apis/youtube/v3/rest"

# =============================================================================================
#  THE SCOPE DECISION, AND IT WAS MEASURED RATHER THAN REMEMBERED
# =============================================================================================
# §40 asks for youtube.upload + youtube.readonly and says to take the wider `youtube` only if
# the privacy update proves impossible under them. It proves impossible, and the evidence is
# Google's own machine-readable discovery document (revision 20261001), which lists the
# acceptable scopes per method. Recorded here as DISCOVERY_FACTS so that a harness can re-fetch
# the document and assert these are still true rather than trusting a comment:
#
#   videos.insert    youtube, youtube.force-ssl, youtube.upload, youtubepartner
#   thumbnails.set   youtube, youtube.force-ssl, youtube.upload, youtubepartner
#   videos.list      youtube, youtube.force-ssl, youtube.readonly, youtubepartner
#   videos.update    youtube, youtube.force-ssl,                  youtubepartner   <- no upload
#   videos.delete    youtube, youtube.force-ssl,                  youtubepartner
#
# So insert, the thumbnail and the verification all fit inside the narrow pair exactly as the
# mandate hoped - and the unlisted->public flip is videos.update, which does not. There is no
# way to be public later without it: privacyStatus can be SET at insert, and changed only by
# update. Hence `youtube`.
#
# AND THE LINE THAT MATTERS MORE THAN THE DECISION: videos.delete accepts exactly the same
# scopes as videos.update. There is no grant in this API that can change a video's privacy and
# cannot also destroy it. So the Delete Prohibition is not something the consent screen can
# promise the boss - it is a property of this file's source, which is why §40 asks for a source
# scan and why _http() refuses the method at runtime as well.
#
# WHY ALL THREE ARE STILL REQUESTED when `youtube` subsumes the other two for every method we
# call: the narrow pair is what the Broadcaster DEGRADES to. If the boss ever revokes the wide
# scope and leaves the narrow ones - or approves a narrower screen than we asked for - the
# granted-scope string in the token file will say so, scope_report() will read it, and uploading
# unlisted still works while publish refuses with a sentence that names the reason instead of
# surprising a human with a 403 halfway through a premiere.
SCOPE_UPLOAD = "https://www.googleapis.com/auth/youtube.upload"
SCOPE_READONLY = "https://www.googleapis.com/auth/youtube.readonly"
SCOPE_WIDE = "https://www.googleapis.com/auth/youtube"
SCOPES = [SCOPE_UPLOAD, SCOPE_READONLY, SCOPE_WIDE]

# The facts above, as data. Keyed by the method name this module uses them for.
DISCOVERY_FACTS = {
    "videos.insert": (SCOPE_WIDE, SCOPE_UPLOAD),
    "thumbnails.set": (SCOPE_WIDE, SCOPE_UPLOAD),
    "videos.list": (SCOPE_WIDE, SCOPE_READONLY),
    "videos.update": (SCOPE_WIDE,),
}

# ITS OWN LOOPBACK PORT. google_api.py owns 4731 and says why a fixed port rather than an
# ephemeral one; 4732 is the next free one and is never the server's 4700 nor any harness's
# 9222-9254. Two consent flows could in principle be in flight at once, and two flows on one
# port would mean the second one's redirect landing in the first one's catcher.
LOOPBACK_PORT = 4732
LOOPBACK_HOST = "127.0.0.1"
REDIRECT_URI = "http://%s:%d/" % (LOOPBACK_HOST, LOOPBACK_PORT)

HTTP_TIMEOUT = 30.0            # the JSON calls. Longer than google_api's 20s: videos.insert's
                               # metadata round-trip is slower than a calendar write.
UPLOAD_TIMEOUT = 300.0         # one chunk. 4 MiB on a slow line is minutes, not seconds.
CONSENT_TIMEOUT = 300.0
REFRESH_SKEW = 120.0

# =============================================================================================
#  THE UPLOAD'S OWN NUMBERS
# =============================================================================================
# A MULTIPLE OF 256 KiB, WHICH GOOGLE REQUIRES, and 4 MiB rather than the 8 or 64 a throughput
# benchmark would pick. The reason is proof rather than speed: the Director's films are 3-6 MB,
# so an 8 MiB chunk would make every real upload a SINGLE PUT and the resume path - the 308, the
# Range header, the offset arithmetic - would never once run in anger. At 4 MiB the useEffect
# film is two chunks, so the premiere itself exercises the branch that exists for a dropped
# connection. A file is not a test unless the test is the file.
CHUNK_BYTES = 4 * 1024 * 1024
RETRY_MAX = 5                  # per chunk. 5 doublings from 1s is 31s of patience.
RETRY_BASE_S = 1.0
RETRY_CAP_S = 16.0
# THE STATUSES THAT MEAN "TRY THE SAME CHUNK AGAIN". 308 is not here because 308 is success
# with more to do, not a failure. 404 is deliberately absent and the reason is in resume()'s
# docstring: a dead session must never be restarted automatically.
RETRY_STATUSES = (429, 500, 502, 503, 504)

PRIVACY_FIRST = "unlisted"     # see the module docstring's second law. insert() has no choice.
PRIVACY_PUBLIC = "public"
PRIVACIES = ("private", "unlisted", "public")
CATEGORY_EDUCATION = "27"      # YouTube's own id for Education. The Director makes explainers.

# =============================================================================================
#  THE PACKAGE'S LIMITS, every one of them YouTube's own
# =============================================================================================
TITLE_MAX = 100                # YouTube rejects 101. §40 names this number too.
DESC_MAX = 5000
TAGS_TOTAL_MAX = 500           # the sum of all tags, including the quoting YouTube adds
TAG_MAX = 30                   # one tag. Longer reads as a sentence and is ignored by search.
TAGS_MAX = 12                  # how many. Beyond a dozen is keyword stuffing, which the
                               # reused-content reviewers read as spam signal.
HOOK_MAX = 200                 # the first description line, which is what shows above the fold

_LOCK = threading.RLock()
_PENDING = {}
# COUNTS ONLY, the habit jobs.py and the Doorman keep: this module may know how many videos it
# has published and may never keep a second copy of what was in them.
_SEEN = {"uploads": 0, "chunks": 0, "resumes": 0, "retries": 0, "thumbs": 0,
         "updates": 0, "verifies": 0, "refusedDelete": 0}


# =============================================================================================
#  THE PROHIBITION, AT THE ONE PLACE A REQUEST IS MADE
# =============================================================================================
# EVERY HTTP METHOD THIS MODULE MAY USE, and the list is three words long. GET reads,
# POST inserts and opens an upload session, PUT sends the bytes. videos.update is a PUT.
# There is no fourth verb in the YouTube Data API that this house has any business speaking.
METHODS_ALLOWED = ("GET", "POST", "PUT")


class Prohibited(Exception):
    """Raised when something asks this module to do what it does not do.

    AN EXCEPTION AND NOT A RETURN VALUE, which is the whole point. Every other failure in
    this file comes back as (status, parsed, sentence) so that a caller can tell the boss
    what went wrong and carry on. This one is not a failure - it is a caller asking for
    something the house has forbidden, and a caller who did that has a bug, not bad luck.
    A sentence could be ignored by a `_, _, err = ...` that nobody checked; a raise cannot.
    """


def _refuse_method(method):
    """The one gate. Returns the method in upper case or raises Prohibited.

    THIS IS WHERE 'UPLOAD-ONLY' IS ENFORCED rather than where it is documented. The module
    holds a scope that permits videos.delete because Google offers no narrower one that can
    also change a privacy status - so the only thing standing between this house and a
    destroyed film is this function. It is three lines and it is the most important code in
    the file.
    """
    verb = str(method or "").strip().upper()
    if verb not in METHODS_ALLOWED:
        with _LOCK:
            _SEEN["refusedDelete"] += 1
        raise Prohibited(
            "the Broadcaster does not issue %s - it uploads, reads and updates, and the one "
            "thing it may never do is take a film down" % (verb or "an empty method"))
    return verb


# =============================================================================================
#  small helpers
# =============================================================================================
def digest(value):
    """A short sha256, for a log or a harness that must not see the thing itself."""
    if not value:
        return ""
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()[:12]


def _now():
    return time.time()


def _read_json(path):
    try:
        data = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


def token():
    return _read_json(TOKEN_FILE)


def save_token(data):
    """Owner-only, and never a partial write - google_api.save_token()'s reasoning exactly."""
    SECRETS.mkdir(parents=True, exist_ok=True)
    tmp = TOKEN_FILE.with_suffix(".tmp")
    body = json.dumps(data, indent=1)
    try:
        with io.open(tmp, "w", encoding="utf-8") as fh:
            fh.write(body)
        try:
            os.chmod(tmp, 0o600)
        except OSError:
            pass                                  # Windows: the ACL is the user's own already
        os.replace(tmp, TOKEN_FILE)
        return True
    except OSError:
        try:
            tmp.unlink()
        except OSError:
            pass
        return False


def forget():
    """Drop the local grant. NOT a revoke and NOT a delete of anything on YouTube.

    Worth being explicit about in a module with a delete prohibition: this removes a file on
    this machine. Every video ever uploaded stays exactly where it is, which is the whole
    design. Revoking the grant itself is a click in the boss's Google account.
    """
    try:
        TOKEN_FILE.unlink()
        return True
    except OSError:
        return False


def _sentence(exc):
    """An error a human can read, with nothing in it that was secret."""
    if isinstance(exc, urllib.error.HTTPError):
        return "YouTube answered HTTP %d" % exc.code
    if isinstance(exc, urllib.error.URLError):
        return "the connection failed: %s" % str(getattr(exc, "reason", ""))[:80]
    return str(exc)[:160]


def _api_error(parsed):
    """The reason YouTube gave, out of its error envelope, or ""."""
    err = (parsed or {}).get("error")
    if not isinstance(err, dict):
        return ""
    first = (err.get("errors") or [{}])[0]
    if isinstance(first, dict) and first.get("reason"):
        return "%s: %s" % (first["reason"], str(err.get("message") or "")[:120])
    return str(err.get("message") or "")[:140]


# =============================================================================================
#  THE TRANSPORT - one function, one method gate
# =============================================================================================
def _http(method, url, body=None, headers=None, raw=None, timeout=None):
    """(status, parsed, headers, error-sentence). The only place this module opens a socket.

    `body` is a dict to be sent as JSON; `raw` is bytes to be sent as they are. They are
    mutually exclusive and a caller passing both is a caller that has not decided.

    IT NEVER RAISES FOR AN HTTP STATUS, because a 308 is normal here and a 503 is a retry
    rather than a crash - so the status comes back as a number and the decision belongs to
    the caller. It raises for exactly one thing: a forbidden method.
    """
    verb = _refuse_method(method)                # <- the prohibition, before anything else
    data = raw
    out_headers = dict(headers or {})
    if body is not None:
        if raw is not None:
            raise Prohibited("a request carries either a JSON body or raw bytes, never both")
        data = json.dumps(body).encode("utf-8")
        out_headers["Content-Type"] = "application/json; charset=utf-8"
    req = urllib.request.Request(url, data=data, method=verb)
    for key, value in out_headers.items():
        req.add_header(key, value)
    try:
        with urllib.request.urlopen(req, timeout=float(timeout or HTTP_TIMEOUT)) as resp:
            payload = resp.read()
            got = dict(resp.headers.items())
            code = resp.status
    except urllib.error.HTTPError as exc:
        payload = b""
        try:
            payload = exc.read()
        except Exception:                                          # noqa: BLE001
            pass
        got = dict(getattr(exc, "headers", {}) or {})
        code = exc.code
    except Exception as exc:                                       # noqa: BLE001
        return 0, {}, {}, _sentence(exc)
    parsed = {}
    if payload:
        try:
            parsed = json.loads(payload.decode("utf-8", "replace"))
        except ValueError:
            parsed = {}
        if not isinstance(parsed, dict):
            parsed = {}
    err = _api_error(parsed) if code >= 400 else ""
    return code, parsed, got, err


# =============================================================================================
#  OAUTH - its own grant, its own token file, its own consent screen
# =============================================================================================
def _pkce():
    verifier = base64.urlsafe_b64encode(secretslib.token_bytes(48)).decode("ascii").rstrip("=")
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode("ascii")).digest()).decode("ascii").rstrip("=")
    return verifier, challenge


def consent_url():
    """(url, kit, error). The kit holds the verifier and state and is never shown."""
    cfg = google_api.client()
    if not cfg:
        return "", None, ("there is no Google client file - put the downloaded JSON at "
                          "secrets/google_client.json")
    verifier, challenge = _pkce()
    state = secretslib.token_urlsafe(24)
    query = {
        "client_id": cfg["client_id"],
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "state": state,
        "access_type": "offline",
        "prompt": "consent",
        # NOT include_granted_scopes. The two grants in this house stay separate on purpose -
        # see the module docstring - and that flag is precisely what would merge them.
    }
    return (AUTH_ENDPOINT + "?" + urllib.parse.urlencode(query),
            {"verifier": verifier, "state": state}, "")


class _Catcher(BaseHTTPRequestHandler):
    """One request, one answer, then it dies. It never serves a file."""

    def do_GET(self):                                             # noqa: N802
        params = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        got = {k: (v[0] if v else "") for k, v in params.items()}
        self.server.caught = got
        ok = bool(got.get("code")) and not got.get("error")
        page = ("<!doctype html><meta charset=utf-8><title>YouTube</title>"
                "<style>body{background:#06070c;color:#d8e0f0;font:15px/1.6 system-ui;"
                "display:grid;place-items:center;height:100vh;margin:0}b{color:%s}</style>"
                "<div><b>%s</b><p>%s</p></div>"
                % ("#7fd8a8" if ok else "#e08a8a",
                   "The channel is connected." if ok else "Not connected.",
                   "You may close this tab and go back to the console."
                   if ok else "Nothing was saved. The console will say why."))
        body = page.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        """Silence: the default prints the request line, and that line carries the code."""
        return


def _post_form(url, fields):
    """(status, parsed, error-sentence) for the token endpoint, which wants a FORM and not JSON.

    THROUGH _http() AND NOT BESIDE IT, and the second draft of this function is the reason worth
    writing down. The first opened its own socket - correctly, with its own _refuse_method("POST")
    above it, and it would have behaved identically for ever. preflight's delete-prohibition check
    failed it anyway, because the clause it asserts is not "every request is checked" but "there is
    exactly ONE door", and two doors is two policies however alike they are today. A module whose
    whole promise is that a verb is unreachable cannot have a second place where a verb is chosen.

    So the form encoding is all that is left here: `raw` bytes and the one header, which is
    precisely what _http()'s raw path exists for.

    THE CONTRACT IS UNCHANGED, including for a refusal. _api_error() reads YouTube's envelope,
    where `error` is an object; the token endpoint's `error` is a STRING ("invalid_grant"), so that
    function returns "" for every reply this one gets and the caller composes the sentence from the
    status exactly as it did before. The one case worth keeping by hand is the unparseable 4xx -
    Google answering with something that is not JSON at all - because "HTTP 400" with no noun in it
    is the sort of message that sends somebody looking in the wrong module.
    """
    status, parsed, _headers, err = _http(
        "POST", url, raw=urllib.parse.urlencode(fields).encode("ascii"),
        headers={"Content-Type": "application/x-www-form-urlencoded"})
    if not err and status >= 400 and not parsed:
        return status, {}, "HTTP %d from the token endpoint" % status
    return status, parsed, err


def _exchange(code, verifier):
    cfg = google_api.client()
    if not cfg:
        return None, "there is no Google client file any more"
    fields = {"client_id": cfg["client_id"], "code": code, "code_verifier": verifier,
              "grant_type": "authorization_code", "redirect_uri": REDIRECT_URI}
    if cfg.get("client_secret"):
        fields["client_secret"] = cfg["client_secret"]
    status, parsed, err = _post_form(TOKEN_ENDPOINT, fields)
    if err or status >= 400:
        return None, err or "the token exchange failed (HTTP %d)" % status
    access = str(parsed.get("access_token") or "")
    if not access:
        return None, "Google returned no access token"
    if not str(parsed.get("refresh_token") or ""):
        return None, ("Google returned no refresh token, so the connection would die within "
                      "the hour - not saving it")
    data = {
        "access_token": access,
        "refresh_token": str(parsed["refresh_token"]),
        "token_type": str(parsed.get("token_type") or "Bearer"),
        # THE GRANTED SCOPE STRING, KEPT VERBATIM, because scope_report() reads it to decide
        # whether publish is possible. What we ASKED for is in SCOPES; what we GOT is this.
        "scope": str(parsed.get("scope") or ""),
        "expires_at": _now() + float(parsed.get("expires_in") or 3600),
        "connected_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "channel": "", "channelTitle": "",
    }
    who = channel_of(access)
    data["channel"] = who.get("id") or ""
    data["channelTitle"] = who.get("title") or ""
    save_token(data)
    return data, ""


def connect(background=True):
    """Open the consent page and catch the redirect. A status-shaped dict.

    RESERVED FOR THE BOSS, and this function is the machine's half of it: it can open a
    browser and it cannot click Allow. §40 PART 0 names the consent as a prerequisite for
    exactly that reason.
    """
    url, kit, err = consent_url()
    if err:
        return {"state": "no-client", "why": err, "opened": False}
    try:
        server = HTTPServer((LOOPBACK_HOST, LOOPBACK_PORT), _Catcher)
    except OSError:
        return {"state": "busy", "opened": False,
                "why": ("port %d is in use, so the consent redirect could not be caught - "
                        "nothing was opened" % LOOPBACK_PORT)}
    server.caught = None
    server.timeout = CONSENT_TIMEOUT

    def wait():
        try:
            server.handle_request()
            got = server.caught or {}
        finally:
            try:
                server.server_close()
            except OSError:
                pass
        with _LOCK:
            _PENDING.clear()
        if not got or got.get("error"):
            with _LOCK:
                _PENDING.update({"state": "refused",
                                 "why": str(got.get("error") or "consent timed out")[:80]})
            return
        if got.get("state") != kit["state"]:
            with _LOCK:
                _PENDING.update({"state": "refused",
                                 "why": "the redirect did not match the request it answered"})
            return
        data, why = _exchange(got.get("code") or "", kit["verifier"])
        with _LOCK:
            _PENDING.update({"state": "connected" if data else "refused", "why": why})

    with _LOCK:
        _PENDING.clear()
        _PENDING.update({"state": "waiting", "why": ""})
    thread = threading.Thread(target=wait, name="youtube-consent", daemon=True)
    thread.start()
    opened = _open_browser(url)
    if not background:
        thread.join(CONSENT_TIMEOUT + 5)
    return {"state": pending().get("state") or "waiting", "opened": opened,
            "why": pending().get("why") or "", "url": url if not opened else ""}


def _open_browser(url):
    try:
        os.startfile(url)                                          # noqa: S606 - Windows
        return True
    except Exception:                                              # noqa: BLE001
        try:
            import webbrowser
            return bool(webbrowser.open(url))
        except Exception:                                          # noqa: BLE001
            return False


def pending():
    with _LOCK:
        return dict(_PENDING)


def access():
    """(bearer, state, why). state: connected / absent / reconnect / no-client."""
    cfg = google_api.client()
    if not cfg:
        return "", "no-client", "there is no Google client file at secrets/google_client.json"
    data = token()
    if not data or not data.get("refresh_token"):
        return "", "absent", "this machine is not connected to a YouTube channel yet"
    if data.get("access_token") and float(data.get("expires_at") or 0) - REFRESH_SKEW > _now():
        return data["access_token"], "connected", ""
    fields = {"client_id": cfg["client_id"], "refresh_token": data["refresh_token"],
              "grant_type": "refresh_token"}
    if cfg.get("client_secret"):
        fields["client_secret"] = cfg["client_secret"]
    status, parsed, err = _post_form(TOKEN_ENDPOINT, fields)
    if status >= 400 or err:
        if str((parsed or {}).get("error") or "") == "invalid_grant":
            return "", "reconnect", ("Google will not renew the channel connection - it has "
                                     "been revoked or has expired, and must be reconnected")
        return "", "connected", err or "the token could not be refreshed (HTTP %d)" % status
    fresh = str(parsed.get("access_token") or "")
    if not fresh:
        return "", "reconnect", "Google renewed nothing, so the connection must be remade"
    data["access_token"] = fresh
    data["expires_at"] = _now() + float(parsed.get("expires_in") or 3600)
    if parsed.get("refresh_token"):
        data["refresh_token"] = str(parsed["refresh_token"])
    if parsed.get("scope"):
        data["scope"] = str(parsed["scope"])
    save_token(data)
    return fresh, "connected", ""


def call(method, url, body=None, timeout=None):
    """One authenticated JSON request. (status, parsed, error-sentence).

    The 401-retry is google_api.call()'s, for its reason: a 401 on a token we have just
    refreshed is a revocation and not a race, so it is retried exactly once.
    """
    bearer, _state, why = access()
    if not bearer:
        return 0, {}, why or "not connected to a YouTube channel"
    head = {"Authorization": "Bearer " + bearer}
    status, parsed, _got, err = _http(method, url, body=body, headers=head, timeout=timeout)
    if status == 401:
        data = token() or {}
        data["expires_at"] = 0
        save_token(data)
        bearer, _state, why = access()
        if not bearer:
            return status, parsed, why or "Google rejected the channel connection"
        head = {"Authorization": "Bearer " + bearer}
        status, parsed, _got, err = _http(method, url, body=body, headers=head, timeout=timeout)
    return status, parsed, err


# =============================================================================================
#  WHAT THE GRANT PERMITS - read from the token, never assumed
# =============================================================================================
def granted():
    """The scopes actually in the token file, as a set. Empty when not connected."""
    return set(str((token() or {}).get("scope") or "").split())


def scope_report():
    """Which of this module's four calls the current grant permits, and why.

    THE EVIDENCE §40 ASKS FOR, as a dict rather than a sentence, so the harness and the
    report read the same thing. `wanted` is what the consent screen asked for; `have` is what
    came back; `can` is the intersection of the two with DISCOVERY_FACTS.
    """
    have = granted()
    can = {}
    for method, accepted in sorted(DISCOVERY_FACTS.items()):
        hit = sorted(have.intersection(accepted))
        can[method] = {"allowed": bool(hit), "via": hit, "accepts": list(accepted)}
    return {
        "wanted": list(SCOPES),
        "have": sorted(have),
        "can": can,
        # THE TWO SENTENCES THE REST OF THE HOUSE ACTS ON.
        "canUpload": can["videos.insert"]["allowed"],
        "canPublish": can["videos.update"]["allowed"],
        "whyNotPublish": ("" if can["videos.update"]["allowed"] else
                          ("the grant on this machine does not carry %s, so a film can be "
                           "uploaded unlisted and cannot be made public - the channel must be "
                           "reconnected to approve it" % SCOPE_WIDE)),
        # AND THE PROHIBITION, REPORTED AS A FACT ABOUT THE SCOPE RATHER THAN A CLAIM.
        "scopeWouldPermitDelete": SCOPE_WIDE in have,
        "deleteIssuable": False,
        "methodsAllowed": list(METHODS_ALLOWED),
    }


def discovery_check(timeout=25.0):
    """Re-fetch Google's discovery document and compare it with DISCOVERY_FACTS.

    NOT CALLED BY THE SERVER AND NOT ON ANY HOT PATH - it is one network call to a document
    half a megabyte wide, and it exists so that §40's scope decision can be re-proved rather
    than re-remembered. broadcaster_proof runs it; preflight does not, because preflight must
    pass on an aeroplane.
    """
    status, parsed, _got, err = _http("GET", DISCOVERY_URL, timeout=timeout)
    if status != 200 or not parsed:
        return {"ok": False, "why": err or "the discovery document could not be read (HTTP %d)"
                % status, "revision": "", "rows": {}}
    rows, agree = {}, True
    for method in sorted(set(list(DISCOVERY_FACTS) + ["videos.delete"])):
        res, name = method.split(".")
        live = sorted(((parsed.get("resources") or {}).get(res) or {})
                      .get("methods", {}).get(name, {}).get("scopes") or [])
        ours = sorted(DISCOVERY_FACTS.get(method, ()))
        # The force-ssl and partner scopes are real and are deliberately not in our table:
        # this house asks for neither, so the comparison is "is every scope we recorded still
        # accepted", not "is the list identical".
        kept = [s for s in ours if s in live]
        rows[method] = {"live": live, "recorded": ours, "stillAccepted": kept == ours}
        if method in DISCOVERY_FACTS and kept != ours:
            agree = False
    deletes = rows.get("videos.delete", {}).get("live") or []
    return {"ok": agree, "revision": str(parsed.get("revision") or ""), "rows": rows,
            # THE LINE THE REPORT QUOTES: update and delete accept the same scopes, so no
            # grant can separate them.
            "deleteNeedsSameAsUpdate":
                sorted(deletes) == sorted(rows.get("videos.update", {}).get("live") or []),
            "uploadCanDelete": SCOPE_UPLOAD in deletes,
            "why": ""}


def status():
    """What a panel shows. No token, no code, no secret - a digest and counts."""
    cfg = google_api.client()
    data = token()
    out = {
        "clientPresent": bool(cfg),
        "scopes": list(SCOPES),
        "port": LOOPBACK_PORT,
        "redirectUri": REDIRECT_URI,
        "tokenFile": "secrets/youtube_token.json",
        "state": "no-client" if not cfg else "absent",
        "why": "", "channel": "", "channelTitle": "", "connectedAt": "",
        "tokenDigest": "", "expiresInS": 0,
        "pending": pending().get("state") or "",
        "seen": dict(_SEEN),
        "scope": scope_report(),
        "privacyFirst": PRIVACY_FIRST,
        "chunkBytes": CHUNK_BYTES,
    }
    if not cfg:
        out["why"] = "there is no client file at secrets/google_client.json"
        return out
    if not data or not data.get("refresh_token"):
        out["why"] = "no channel is connected yet - the boss's consent is a prerequisite"
        return out
    out.update({
        "channel": str(data.get("channel") or ""),
        "channelTitle": str(data.get("channelTitle") or ""),
        "connectedAt": str(data.get("connected_at") or ""),
        "tokenDigest": digest(data.get("refresh_token")),
        "expiresInS": max(0, int(float(data.get("expires_at") or 0) - _now())),
    })
    _bearer, live, why = access()
    out["state"] = live
    out["why"] = why
    return out


# =============================================================================================
#  THE CHANNEL - prerequisite (b), checked and never created
# =============================================================================================
def channel_of(access_token):
    """{id, title} for the connected account's own channel, or {} - used at connect time."""
    url = API_BASE + "/channels?part=snippet&mine=true"
    status, parsed, _got, _err = _http("GET", url,
                                       headers={"Authorization": "Bearer " + access_token})
    if status != 200:
        return {}
    items = parsed.get("items") or []
    if not items:
        return {}
    first = items[0]
    return {"id": str(first.get("id") or ""),
            "title": str(((first.get("snippet") or {}).get("title")) or "")}


def channel():
    """The channel this machine may upload to, or a refusal that names the prerequisite.

    A GOOGLE ACCOUNT IS NOT A CHANNEL. An account that has never created one answers
    channels.list(mine=true) with an empty items array, and videos.insert against it fails
    with youtubeSignupRequired - a message nobody reads as "make a channel first". §40 names
    channel creation as the boss's, by hand, so this function's job is to say so in advance
    rather than let an upload discover it.
    """
    status, parsed, err = call("GET", API_BASE + "/channels?part=snippet,status&mine=true")
    if status == 0 or status >= 400:
        return {"ok": False, "id": "", "title": "",
                "why": err or "the channel could not be read (HTTP %d)" % status}
    items = parsed.get("items") or []
    if not items:
        return {"ok": False, "id": "", "title": "",
                "why": ("this Google account has no YouTube channel yet - one has to be "
                        "created by hand, by you, before anything can be uploaded")}
    first = items[0]
    return {"ok": True, "id": str(first.get("id") or ""),
            "title": str(((first.get("snippet") or {}).get("title")) or ""), "why": ""}


# =============================================================================================
#  THE PACKAGE - §40 PART 2, and every word of it comes off the film
# =============================================================================================
# A WORD, AND THE DOTS ARE THE WHOLE DIFFICULTY. "Next.js" and "node.js" are single words whose
# dot is interior and load-bearing, while "infrastructure." is one word and a full stop. So a dot
# is part of the word only when something follows it: the first draft of this pattern ended in
# `[A-Za-z0-9+#.]*` and the premiere's tag list shipped "infrastructure." with its full stop in it.
_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9+#]*(?:\.[A-Za-z0-9+#]+)*")
# Where a sentence ends, for surface_spellings() - see its note on sentence-initial capitals.
_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+")
# WORDS THAT ARE NEVER A TAG. Not a general stop-word list - these are specifically the words
# the Director's own narration is full of, so a tag list built from its prose would otherwise
# be "the, and, for, with" four times out of twelve.
_STOP = frozenset("""
a an and are as at be been but by can could do does for from had has have he her his how i if
in into is it its me my no not of on or our out she should so than that the their them then
there these they this those to too us was we were what when where which who why will with
would you your about more most such only just also very much many own same each both few
""".split())


def _words(text):
    return [w for w in _WORD_RE.findall(str(text or ""))]


def keywords(text, limit=TAGS_MAX):
    """The film's own keywords, best first, by a stated rule rather than a model.

    CASE IS KEPT FROM THE FIRST SIGHTING, which matters more than it looks: the prose says
    "useEffect" and "React", and a tag list that said "useeffect" would be a tag list for a
    different search. So the count is case-insensitive and the output is the spelling the film
    itself used.

    THE RANK IS (how often, how long, how early) AND EVERY TERM OF THAT IS DELIBERATE. Frequency
    first, because a word the narration keeps coming back to is what the film is about. Then
    LENGTH, which is director.keywords_in()'s insight and worth borrowing rather than
    re-deriving: in English prose length is a decent proxy for specificity, so "developers"
    outranks "event" among words said once each. Then position, so that a true tie is broken by
    the sentence that said it first - which is the hook, the line written to carry the topic.
    The first draft of this function broke ties ALPHABETICALLY and the premiere's tag list came
    back carrying "advise" and "against", two words that describe nothing, purely because they
    begin with an a.

    ADVERBS LAST, also director.keywords_in()'s, for its reason: "significantly" is the longest
    word in its sentence and says nothing about what the sentence is about.
    """
    seen, order, first = {}, {}, {}
    for index, word in enumerate(_words(text)):
        key = word.lower()
        if key in _STOP or len(key) < 3:
            continue
        seen[key] = seen.get(key, 0) + 1
        order.setdefault(key, word)
        first.setdefault(key, index)
    def rank(item):
        key, count = item
        adverb = key.endswith("ly") and len(key) > 5
        return (adverb, -count, -len(key), first[key])
    out = []
    for key, _count in sorted(seen.items(), key=rank):
        tag = order[key][:TAG_MAX]
        if tag and tag not in out:
            out.append(tag)
        if len(out) >= max(1, int(limit)):
            break
    return out


# A NOTE'S FILENAME, as the Scholar writes them: 2026-09-30-19-react-js.md. The date and the
# hour are the boss's reading history and are nobody's business; the slug after them is the
# subject he filed it under.
_NOTE_SLUG_RE = re.compile(r"^\d{4}-\d{2}-\d{2}-\d{1,2}-(.+?)(?:\.md)?$", re.I)
# Slug fragments that are not subjects. `js` and `py` are the file-type half of a slug like
# `react-js`, and a tag reading "js" on a React video is noise competing with the real one.
_SLUG_NOISE = frozenset(("js", "ts", "py", "md", "note", "notes", "doc", "docs"))


def note_keywords(cited, spellings=None):
    """The cited notes' own subjects, as tags. §40's "tags from the cited notes' keywords".

    AND IT READS THE FILENAME SLUG, NEVER THE NOTE'S BODY, which is the one genuinely sharp
    edge in this whole package. Tags are PUBLIC - they are published with the film and are
    machine-readable by anyone - and the notes are a private research collection. A tag list
    built by mining the text of four notes would put whatever the boss happened to be reading
    into a public field, including the parts of those notes that never made it into the film.
    The slug is different in kind: it is the subject line the boss himself chose when filing
    the note, it is one or two words, and on this premiere it is "react". That is a keyword;
    the note's contents are a diary.

    The DATE is dropped for the same reason the cited-notes line carries ids instead of
    filenames: "2026-09-30" tells a stranger when the boss was studying, which is not a
    keyword about React.
    """
    out = []
    for item in cited or []:
        name = str((item or {}).get("note") or "").strip()
        hit = _NOTE_SLUG_RE.match(name)
        slug = (hit.group(1) if hit else re.sub(r"\.md$", "", name, flags=re.I))
        for part in re.split(r"[-_\s]+", slug):
            key = part.strip().lower()
            if not key or key in _SLUG_NOISE or key in _STOP or len(key) < 3:
                continue
            tag = ((spellings or {}).get(key) or part)[:TAG_MAX]
            if tag not in out:
                out.append(tag)
    return out


def fit_tags(tags, total_max=TAGS_TOTAL_MAX):
    """As many of those tags as fit YouTube's 500-character total, in order.

    THE TOTAL IS COUNTED THE WAY YOUTUBE COUNTS IT - a tag containing a space is quoted on
    the wire, so it costs two characters more than its length. Getting this wrong means a
    perfectly good upload refused for `invalidTags` after the bytes have already gone.
    """
    out, used, seen = [], 0, set()
    for tag in tags or []:
        clean = re.sub(r"\s+", " ", str(tag or "")).strip()[:TAG_MAX]
        if not clean or clean.lower() in seen:
            # CASE-INSENSITIVELY, because the two sources overlap by design: the notes' subject
            # is "React" and the narration's commonest word is "react", and YouTube would have
            # taken both and spent two tags and eleven characters saying one thing. Whichever
            # arrives FIRST wins, which is why note_keywords() is passed the narration's
            # spellings - so the surviving copy is the capitalised one.
            continue
        seen.add(clean.lower())
        cost = len(clean) + (2 if " " in clean else 0) + (1 if out else 0)
        if used + cost > int(total_max):
            continue
        out.append(clean)
        used += cost
    return out, used


def read_script(folder):
    """The Director's script.md, parsed back into {topic, narration[], cited[]}.

    READ OFF DISK RATHER THAN PASSED IN, because the film outlives the render: a boss may ask
    for a video on Monday and publish it on Friday, by which time the job that made it is off
    the ledger's fifty-row ring. The folder is the durable thing, and script.md is the file
    §36 deliberately kept when it swept the scene parts away.
    """
    path = pathlib.Path(folder) / "script.md"
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return {"ok": False, "why": "there is no script.md beside that film", "topic": "",
                "narration": [], "cited": []}
    topic = ""
    head = re.search(r"^#\s+(.+)$", text, re.M)
    if head:
        topic = head.group(1).strip()
    narration, cited = [], []
    section = ""
    for line in text.splitlines():
        if line.startswith("## "):
            section = line[3:].strip().lower()
            continue
        if section == "narration":
            hit = re.match(r"^\s*\d+\.\s+(.*\S)", line)
            if hit:
                narration.append(hit.group(1).strip())
        elif section == "cited notes":
            hit = re.match(r"^\s*-\s+`([^`]+)`\s*-\s*(.+?)\s*$", line)
            if hit:
                cited.append({"id": hit.group(1), "note": hit.group(2)})
    return {"ok": bool(topic and narration), "why": "" if (topic and narration) else
            "that script.md has no topic or no narration in it",
            "topic": topic, "narration": narration, "cited": cited}


def cited_line(cited):
    """§40's cited-notes line: how many of the boss's own notes this film was built from.

    IT NAMES THE NOTES AND NOT THEIR CONTENTS. A description is public, and the note titles
    are dated filenames out of a private collection - "2026-09-30-19-react-js.md" tells a
    stranger what the boss was reading and when. So the line carries the COUNT and the
    machine-readable chunk ids, which are meaningless outside this house and are exactly what
    makes the claim auditable by the one person entitled to audit it.
    """
    n = len(cited or [])
    if not n:
        return ""
    return ("Written from %d note%s of my own research, and read by a synthetic voice. "
            "Source ids: %s." % (n, "" if n == 1 else "s",
                                 ", ".join(str(c.get("id") or "")[:16] for c in cited[:6])))


def disclosure(cfg=None):
    """(line, why) - the boss's approved affiliate-disclosure line, or a refusal.

    THIS MODULE WILL NOT INVENT IT, and that is prerequisite (c). A disclosure is a statement
    made to the public in the boss's name about his own commercial interests; a machine that
    composed one would be making a legal representation on behalf of a human who had never
    read it. So it comes out of config.json under `youtube_disclosure`, the boss writes it,
    and package() refuses to build a description without it rather than shipping one line
    short or one line invented.
    """
    try:
        if cfg is None:
            import server                        # the same late import director.py uses
            cfg = server.load_config()[0]
    except Exception:                                              # noqa: BLE001
        cfg = {}
    line = re.sub(r"\s+", " ", str((cfg or {}).get("youtube_disclosure") or "")).strip()
    if not line:
        return "", ("there is no approved disclosure line - put one in config.json under "
                    "\"youtube_disclosure\" and nothing will be described without it")
    return line[:600], ""


# THE WAY PEOPLE ASK FOR A FILM, which is not the way a title reads. A spoken topic arrives as
# an instruction to the Director - "explain useEffect in react", "make a video about X" - and the
# instruction's verb is addressed to this machine, not to the viewer. Stripped from the FRONT
# only, and only as a whole word, so "how to explain recursion" keeps its verb.
_IMPERATIVE_RE = re.compile(
    r"^(?:please\s+)?(?:can\s+you\s+)?"
    r"(?:explain|describe|cover|teach(?:\s+me)?|tell\s+me\s+about|talk\s+about|"
    r"make\s+(?:a\s+)?(?:video|film|short)\s+(?:about|on)|do\s+(?:a\s+)?(?:video|film)\s+on)"
    r"\s+(?:me\s+)?", re.I)
_SUFFIX = " - Explained"


def surface_spellings(lines):
    """{lowercased word: the spelling the Director's own prose used}.

    WHY THE NARRATION DECIDES THE CASE. A spoken topic is dictated, so it arrives flat -
    "explain useEffect in react" - and a title that says "react" is a title for a different
    search than the one that says "React". The fix is not a list of technology names that this
    file would have to keep up to date; it is that the SAME FILM already contains the correct
    spelling, because the narration is written prose and says "React" and "useEffect". So the
    casing is read off the film rather than guessed, and a word the narration never capitalises
    is left exactly as the boss said it.
    """
    out, weak = {}, {}
    for line in lines or []:
        for sentence in _SENT_SPLIT.split(str(line or "")):
            for index, word in enumerate(_WORD_RE.findall(sentence)):
                key = word.lower()
                if index == 0:
                    # A SENTENCE-INITIAL WORD IS NOT EVIDENCE ABOUT ITS OWN CASE, and this was
                    # a real bug rather than a precaution: every narration line begins with a
                    # capital, so the first draft learned that "the" is spelled "The" from the
                    # sentence "The hook runs after paint" - and then recased a title into
                    # "What is The virtual DOM". Such a word is remembered only as a FALLBACK,
                    # flattened, so it still appears in the map for any caller that wants the
                    # vocabulary, and teaches nothing about capitals.
                    weak.setdefault(key, key)
                    continue
                # Mid-sentence, the first capitalised sighting wins over a later flat one:
                # a proper noun is capitalised wherever it appears, so one capital is
                # evidence and one lower-case is only an absence of it.
                if key not in out or (word != key and out[key] == key):
                    out[key] = word
    merged = dict(weak)
    merged.update(out)
    return merged


def recase(text, spellings):
    """`text` with each word respelled the way the narration spells it, where it differs only
    in case. Never changes a letter, only its case, which is what makes this safe to run on a
    line a human wrote."""
    def swap(hit):
        word = hit.group(0)
        better = (spellings or {}).get(word.lower())
        return better if better and better.lower() == word.lower() else word
    return _WORD_RE.sub(swap, str(text or ""))


def title_for(topic, narration=None):
    """A title at or under 100 characters, carrying the topic keyword.

    THE TOPIC IS THE TITLE'S FIRST WORDS and not a slogan wrapped around it, because the topic
    is the phrase a search for this film will contain, and burying it behind a hook is how a
    title stops matching the thing it is for.

    AND THE SUFFIX MAKES NO CLAIM. It said "- Explained in 60 Seconds" for about an hour, which
    was a lie by four and a half seconds on the premiere and would be a lie by minutes on a
    longer film. A title is the most-read line this house publishes; it does not get to assert
    a number that nothing measured. "- Explained" asserts only what the film is.
    """
    said = re.sub(r"\s+", " ", str(topic or "")).strip()
    if not said:
        return ""
    said = _IMPERATIVE_RE.sub("", said).strip() or said
    said = recase(said, surface_spellings(narration or []))
    # Capitalise the first letter only if the word is not already deliberately lower-case -
    # "useEffect in React" must not become "UseEffect in React".
    first = said.split(" ", 1)[0] if said else ""
    if first and first == first.lower():
        said = said[0].upper() + said[1:]
    if len(said) + len(_SUFFIX) <= TITLE_MAX:
        return said + _SUFFIX
    return said[:TITLE_MAX]


def package(folder, cfg=None):
    """§40 PART 2, whole: {title, description, tags, thumbnail, why}.

    A PURE FUNCTION OF THE FOLDER AND THE CONFIG - no network, no model, no clock. That is
    what lets broadcaster_proof assert the SEO lengths and the disclosure as PREDICATES, with
    no channel connected and nothing uploaded.
    """
    folder = str(folder or "")
    read = read_script(folder)
    if not read["ok"]:
        return {"ok": False, "why": read["why"], "title": "", "description": "", "tags": [],
                "thumbnail": "", "cited": []}
    line, why = disclosure(cfg)
    if why:
        return {"ok": False, "why": why, "title": "", "description": "", "tags": [],
                "thumbnail": "", "cited": read["cited"]}
    spellings = surface_spellings(read["narration"])
    title = title_for(read["topic"], read["narration"])
    hook = re.sub(r"\s+", " ", (read["narration"] or [""])[0]).strip()[:HOOK_MAX]
    cite = cited_line(read["cited"])
    # THE THREE PARTS, IN THIS ORDER, and the order is the only taste here: the hook is what
    # YouTube shows above the fold, the cited-notes line is the channel's shield (see the
    # report's research note on reused content), and the disclosure is last because it is a
    # legal line rather than a reading line and burying it would be the thing a disclosure
    # exists to prevent.
    description = "\n\n".join([p for p in (hook, cite, line) if p])[:DESC_MAX]
    # THE CITED NOTES' SUBJECTS FIRST, then the film's own words. The order is the SEO decision:
    # YouTube weights the leading tags most heavily, and the notes' subjects are the terms the
    # boss himself filed this material under, so they are the terms his audience searches. The
    # film's keywords follow to widen the net. fit_tags() then truncates from the BACK, which
    # means the 500-character limit spends itself on the specific terms and drops the vague ones.
    body = " ".join([read["topic"]] + read["narration"])
    tags, used = fit_tags(note_keywords(read["cited"], spellings) + keywords(body))
    poster = pathlib.Path(folder) / "poster.jpg"
    return {
        "ok": True, "why": "",
        "title": title,
        "description": description,
        "tags": tags, "tagChars": used,
        "thumbnail": str(poster) if poster.exists() else "",
        "cited": read["cited"],
        "hook": hook, "citedLine": cite, "disclosure": line,
        "topic": read["topic"],
        "categoryId": CATEGORY_EDUCATION,
    }


# =============================================================================================
#  THE UPLOAD - resumable, and it lands unlisted because there is no other option
# =============================================================================================
def _open_session(path, snippet, on_note=None):
    """(session_uri, size, error). The metadata round-trip that precedes the bytes."""
    try:
        size = os.path.getsize(path)
    except OSError as exc:
        return "", 0, "that film is not on disk: %s" % _sentence(exc)
    if size <= 0:
        return "", 0, "that film is an empty file"
    bearer, _state, why = access()
    if not bearer:
        return "", size, why or "not connected to a YouTube channel"
    body = {
        "snippet": {
            "title": snippet["title"],
            "description": snippet["description"],
            "tags": list(snippet.get("tags") or []),
            "categoryId": str(snippet.get("categoryId") or CATEGORY_EDUCATION),
        },
        "status": {
            # UNLISTED, WRITTEN HERE, AND THERE IS NO ARGUMENT THAT CHANGES IT. See the
            # module docstring's second law.
            "privacyStatus": PRIVACY_FIRST,
            "selfDeclaredMadeForKids": False,
            "embeddable": True,
        },
    }
    url = (UPLOAD_BASE + "/videos?uploadType=resumable&part=" +
           urllib.parse.quote("snippet,status"))
    head = {"Authorization": "Bearer " + bearer,
            "X-Upload-Content-Length": str(size),
            "X-Upload-Content-Type": "video/mp4"}
    status, parsed, got, err = _http("POST", url, body=body, headers=head)
    if status != 200:
        return "", size, (err or "YouTube would not open an upload session (HTTP %d)" % status)
    session = str(got.get("Location") or got.get("location") or "")
    if not session:
        return "", size, "YouTube opened a session and did not say where"
    if on_note:
        on_note("session open, %.1f MB to send in %d chunk(s)"
                % (size / 1048576.0, (size + CHUNK_BYTES - 1) // CHUNK_BYTES))
    return session, size, ""


def _ask_offset(session, size):
    """How many bytes YouTube already has. (offset, done, resource, error).

    A zero-length PUT with `Content-Range: bytes */total` is the documented way to ask, and
    the answer is a 308 carrying `Range: bytes=0-N`. A 308 with NO Range means it has nothing,
    which is not an error - it is an offset of zero.
    """
    head = {"Content-Range": "bytes */%d" % size, "Content-Length": "0"}
    status, parsed, got, err = _http("PUT", session, raw=b"", headers=head,
                                     timeout=UPLOAD_TIMEOUT)
    if status in (200, 201):
        return size, True, parsed, ""
    if status != 308:
        return 0, False, {}, (err or "the upload session answered HTTP %d when asked where it "
                              "had got to" % status)
    rng = str(got.get("Range") or got.get("range") or "")
    hit = re.match(r"bytes=0-(\d+)", rng)
    return (int(hit.group(1)) + 1 if hit else 0), False, {}, ""


def insert(path, snippet, on_note=None, on_chunk=None):
    """Upload a film and leave it UNLISTED. {ok, videoId, url, bytes, chunks, why}.

    NO PRIVACY ARGUMENT. §40's "unlisted first" is enforced by the absence of a parameter
    rather than by a default a caller could override.

    THE RESUME IS REAL AND IT IS BOUNDED. A chunk that fails on a retryable status is sent
    again after a doubling backoff; after RETRY_MAX the whole upload stops and says where it
    got to, because a session URI stays valid for days and a human restarting it tomorrow is
    strictly better than this process hammering a broken line.

    AND A DEAD SESSION IS NEVER RESTARTED AUTOMATICALLY - the one failure mode in this file
    that would otherwise break the house's first law. A 404 on the session URI means the
    upload must begin again from the first byte, and beginning again is INDISTINGUISHABLE
    from uploading a second copy: if the first attempt had in fact completed and only the
    reply was lost, an automatic restart would put two identical films on a channel that may
    never delete either of them. So a 404 stops and says so, and recent_uploads() exists to
    let a human see what is actually up there before deciding.
    """
    session, size, err = _open_session(path, snippet, on_note=on_note)
    if err:
        return {"ok": False, "videoId": "", "url": "", "bytes": 0, "chunks": 0, "why": err}
    sent, chunks, resumes, retries = 0, 0, 0, 0
    resource = {}
    with io.open(path, "rb") as fh:
        while sent < size:
            fh.seek(sent)
            block = fh.read(CHUNK_BYTES)
            if not block:
                break
            last = sent + len(block) - 1
            head = {"Content-Length": str(len(block)),
                    "Content-Range": "bytes %d-%d/%d" % (sent, last, size),
                    "Content-Type": "video/mp4"}
            attempt, wait = 0, RETRY_BASE_S
            while True:
                status, parsed, got, why = _http("PUT", session, raw=block, headers=head,
                                                 timeout=UPLOAD_TIMEOUT)
                if status in (200, 201):
                    resource = parsed
                    sent = size
                    break
                if status == 308:
                    rng = str(got.get("Range") or got.get("range") or "")
                    hit = re.match(r"bytes=0-(\d+)", rng)
                    sent = (int(hit.group(1)) + 1) if hit else (last + 1)
                    break
                if status == 404:
                    return {"ok": False, "videoId": "", "url": "", "bytes": sent,
                            "chunks": chunks, "resumes": resumes, "retries": retries,
                            "why": ("the upload session has expired after %d of %d bytes. It "
                                    "is NOT restarted automatically: a restart cannot be told "
                                    "apart from a second copy, and this house does not delete "
                                    "what it uploads. Check the channel, then begin again by "
                                    "hand." % (sent, size))}
                if status in RETRY_STATUSES and attempt < RETRY_MAX:
                    attempt += 1
                    retries += 1
                    time.sleep(min(RETRY_CAP_S, wait))
                    wait *= 2
                    # ASK BEFORE RE-SENDING. A 503 may have been returned after the bytes
                    # were accepted, and re-sending a chunk YouTube already has is how an
                    # offset walks backwards.
                    where, done, res, ask_err = _ask_offset(session, size)
                    if ask_err:
                        continue
                    resumes += 1
                    if done:
                        resource, sent = res, size
                        break
                    if where != sent:
                        sent = where
                        break
                    continue
                if status == 0 and attempt < RETRY_MAX:
                    attempt += 1
                    retries += 1
                    time.sleep(min(RETRY_CAP_S, wait))
                    wait *= 2
                    continue
                return {"ok": False, "videoId": "", "url": "", "bytes": sent,
                        "chunks": chunks, "resumes": resumes, "retries": retries,
                        "why": why or "the upload stopped on HTTP %d after %d of %d bytes"
                        % (status, sent, size)}
            chunks += 1
            if on_chunk:
                on_chunk(min(sent, size), size, chunks)
    video_id = str((resource or {}).get("id") or "")
    with _LOCK:
        _SEEN["uploads"] += 1
        _SEEN["chunks"] += chunks
        _SEEN["resumes"] += resumes
        _SEEN["retries"] += retries
    if not video_id:
        # THE BYTES WENT AND THE ID DID NOT COME BACK. The film almost certainly exists, so
        # this is not reported as a clean failure: it is reported as an uncertainty with the
        # one instruction that resolves it.
        return {"ok": False, "videoId": "", "url": "", "bytes": sent, "chunks": chunks,
                "resumes": resumes, "retries": retries,
                "why": ("every byte was accepted and YouTube returned no video id, so a film "
                        "may be on the channel without this machine knowing its name - read "
                        "recent_uploads() before uploading it again")}
    return {"ok": True, "videoId": video_id, "url": watch_url(video_id),
            "bytes": sent, "chunks": chunks, "resumes": resumes, "retries": retries,
            "privacy": str(((resource.get("status") or {}).get("privacyStatus")) or ""),
            "why": ""}


def watch_url(video_id):
    return "https://www.youtube.com/watch?v=%s" % str(video_id or "")


def set_thumbnail(video_id, jpg_path):
    """The Director's poster, as the film's thumbnail. {ok, why}.

    THE POSTER AND NOT A FRAME YOUTUBE PICKED. §36 renders poster.jpg out of the finished
    file, so the thumbnail is a frame of the actual film rather than a drawn card - and the
    choice of which frame was made by the Director with the whole film in hand.
    """
    try:
        raw = pathlib.Path(jpg_path).read_bytes()
    except OSError as exc:
        return {"ok": False, "why": "that poster is not on disk: %s" % _sentence(exc)}
    if not raw:
        return {"ok": False, "why": "that poster is an empty file"}
    bearer, _state, why = access()
    if not bearer:
        return {"ok": False, "why": why or "not connected to a YouTube channel"}
    url = (UPLOAD_BASE + "/thumbnails/set?videoId=" +
           urllib.parse.quote(str(video_id or "")))
    head = {"Authorization": "Bearer " + bearer, "Content-Type": "image/jpeg",
            "Content-Length": str(len(raw))}
    status, parsed, _got, err = _http("POST", url, raw=raw, headers=head,
                                      timeout=UPLOAD_TIMEOUT)
    if status not in (200, 201):
        return {"ok": False, "why": err or "the thumbnail was refused (HTTP %d)" % status}
    with _LOCK:
        _SEEN["thumbs"] += 1
    return {"ok": True, "why": "", "bytes": len(raw)}


def set_privacy(video_id, privacy):
    """videos.update, and the only call in this module that changes a film already on YouTube.

    EVERY ONE OF THESE GETS A LEDGER ROW, which §40 requires in exchange for the wide scope.
    This function returns the transition it made so the caller can write it down; the caller
    that matters - the server's publish path - does.

    IT REFUSES ANYTHING BUT THE THREE WORDS. A typo in a privacy status is not a 400 from
    Google, it is a video left at whatever it was, reported as updated.
    """
    want = str(privacy or "").strip().lower()
    if want not in PRIVACIES:
        return {"ok": False, "why": "'%s' is not a privacy status - it is one of %s"
                % (want[:20], ", ".join(PRIVACIES)), "from": "", "to": ""}
    report = scope_report()
    if not report["canPublish"]:
        return {"ok": False, "why": report["whyNotPublish"], "from": "", "to": want}
    was = verify(video_id)
    before = was.get("privacy") or ""
    body = {"id": str(video_id or ""), "status": {"privacyStatus": want}}
    # PART=STATUS AND NOTHING ELSE. videos.update replaces every part it is given, so a call
    # that said part=snippet,status and sent a status alone would blank the title, the
    # description and the tags. This is the single sharpest edge in the API and the reason
    # this function does not take a snippet argument at all.
    status, parsed, err = call("PUT", API_BASE + "/videos?part=status", body=body)
    if status != 200:
        return {"ok": False, "why": err or "the privacy change was refused (HTTP %d)" % status,
                "from": before, "to": want}
    with _LOCK:
        _SEEN["updates"] += 1
    now = str(((parsed.get("status") or {}).get("privacyStatus")) or want)
    return {"ok": True, "why": "", "from": before, "to": now,
            "videoId": str(video_id or ""), "url": watch_url(video_id)}


def verify(video_id):
    """videos.list - what YouTube itself says about the film. {ok, privacy, title, ...}.

    THE PROOF THAT A THING HAPPENED IS READ BACK FROM THE SERVICE, never inferred from the
    call that made it happen. An upload that returned 200 and a privacy change that returned
    200 are both claims; this is the only evidence.
    """
    vid = str(video_id or "")
    if not vid:
        return {"ok": False, "why": "no video id", "privacy": "", "title": ""}
    url = (API_BASE + "/videos?part=snippet,status,processingDetails&id=" +
           urllib.parse.quote(vid))
    status, parsed, err = call("GET", url)
    if status != 200:
        return {"ok": False, "why": err or "the film could not be read back (HTTP %d)" % status,
                "privacy": "", "title": ""}
    items = parsed.get("items") or []
    if not items:
        return {"ok": False, "why": "YouTube does not have a film under that id",
                "privacy": "", "title": ""}
    item = items[0]
    snip = item.get("snippet") or {}
    stat = item.get("status") or {}
    with _LOCK:
        _SEEN["verifies"] += 1
    return {"ok": True, "why": "", "videoId": vid, "url": watch_url(vid),
            "privacy": str(stat.get("privacyStatus") or ""),
            "uploadStatus": str(stat.get("uploadStatus") or ""),
            "title": str(snip.get("title") or ""),
            "description": str(snip.get("description") or ""),
            "tags": list(snip.get("tags") or []),
            "thumbnails": sorted((snip.get("thumbnails") or {}).keys()),
            "publishedAt": str(snip.get("publishedAt") or ""),
            "processing": str(((item.get("processingDetails") or {})
                               .get("processingStatus")) or "")}


def recent_uploads(limit=5):
    """The channel's last few uploads, newest first. The lost-id recovery path.

    WHY THIS EXISTS AT ALL: insert() can lose a video id - a connection that drops after the
    final chunk is accepted but before the reply arrives leaves a film on the channel that
    this machine cannot name. In a house that may never delete, "upload it again and sort it
    out later" is not available. So this reads what is actually there, through the uploads
    playlist, under the readonly scope.
    """
    status, parsed, err = call(
        "GET", API_BASE + "/channels?part=contentDetails&mine=true")
    if status != 200:
        return {"ok": False, "why": err or "the channel could not be read (HTTP %d)" % status,
                "items": []}
    items = parsed.get("items") or []
    playlist = ""
    if items:
        playlist = str((((items[0].get("contentDetails") or {})
                         .get("relatedPlaylists") or {}).get("uploads")) or "")
    if not playlist:
        return {"ok": False, "why": "this channel has no uploads playlist", "items": []}
    url = (API_BASE + "/playlistItems?part=snippet,contentDetails&maxResults=%d&playlistId=%s"
           % (max(1, min(25, int(limit))), urllib.parse.quote(playlist)))
    status, parsed, err = call("GET", url)
    if status != 200:
        return {"ok": False, "why": err or "the uploads could not be read (HTTP %d)" % status,
                "items": []}
    out = []
    for row in parsed.get("items") or []:
        snip = row.get("snippet") or {}
        out.append({"videoId": str(((row.get("contentDetails") or {})
                                    .get("videoId")) or ""),
                    "title": str(snip.get("title") or ""),
                    "publishedAt": str(snip.get("publishedAt") or "")})
    return {"ok": True, "why": "", "playlist": playlist, "items": out}


# =============================================================================================
#  THE ENCODE CHECK - the one gate before any byte leaves
# =============================================================================================
def encode_check(path):
    """Is this actually a finished film? {ok, why, bytes, durationS, vcodec, acodec}.

    BEFORE THE UPLOAD AND NOT AFTER, because an upload cannot be taken back. §35's Director
    already probes its own output, but the Broadcaster is a separate hand and may be pointed
    at a folder by a human: a half-written mp4 from an interrupted render is a real file with
    a real size, and discovering that it has no audio stream AFTER it is on the channel is
    discovering it one step too late.
    """
    p = pathlib.Path(path)
    try:
        size = p.stat().st_size
    except OSError as exc:
        return {"ok": False, "why": "that film is not on disk: %s" % _sentence(exc),
                "bytes": 0, "durationS": 0.0, "vcodec": "", "acodec": ""}
    if size < 1024:
        return {"ok": False, "why": "that film is %d bytes - it is not a video" % size,
                "bytes": size, "durationS": 0.0, "vcodec": "", "acodec": ""}
    facts = {}
    try:
        import director
        facts = director.probe_streams(str(p)) or {}
    except Exception as exc:                                       # noqa: BLE001
        return {"ok": False, "why": "ffprobe could not read it: %s" % _sentence(exc),
                "bytes": size, "durationS": 0.0, "vcodec": "", "acodec": ""}
    # PROBE_STREAMS CAN FAIL WITHOUT COUNTING ANYTHING - no ffprobe on the PATH, or a file it
    # refused - and in that case it returns a `why` and no stream keys. Taking the absent keys
    # as zero would report "that film has no video stream", which blames the film for a missing
    # tool. The distinction matters because one of those is fixed by re-rendering and the other
    # is not.
    if "video" not in facts:
        return {"ok": False, "why": str(facts.get("why") or "ffprobe could not read it"),
                "bytes": size, "durationS": 0.0, "vcodec": "", "acodec": ""}
    video = int(facts.get("video") or 0)
    audio = int(facts.get("audio") or 0)
    secs = float(facts.get("durationS") or 0.0)
    if video < 1:
        return {"ok": False, "why": "that file has no video stream", "bytes": size,
                "durationS": secs, "vcodec": "", "acodec": ""}
    # DURATION BEFORE SOUND, and the order was chosen by running this on poster.jpg. ffprobe
    # reads a JPEG as one video stream of no duration, so the audio check fired first and said
    # "that film has no sound", which is true and is not the thing wrong with a photograph.
    # Length is the fault that distinguishes a still from a film; silence is the fault that
    # distinguishes a broken render from a good one.
    if secs <= 1.0:
        return {"ok": False, "why": "that is %.2fs long - it is a still, not a film" % secs,
                "bytes": size, "durationS": secs,
                "vcodec": str(facts.get("vcodec") or ""),
                "acodec": str(facts.get("acodec") or "")}
    if audio < 1:
        return {"ok": False, "why": "that film has no sound - it is not finished", "bytes": size,
                "durationS": secs, "vcodec": str(facts.get("vcodec") or ""), "acodec": ""}
    return {"ok": True, "why": "", "bytes": size, "durationS": secs,
            "vcodec": str(facts.get("vcodec") or ""),
            "acodec": str(facts.get("acodec") or "")}


def counts():
    with _LOCK:
        return dict(_SEEN)


# =============================================================================================
#  THE TWO JOURNEYS, AND WHY THEY ARE SHAPED DIFFERENTLY
# =============================================================================================
# §40 asks for bus events, a Chain Card and a spoken Yes, and the honest way to give it all three
# is to notice that the two halves of "publish a film" are not the same kind of act:
#
#   THE UPLOAD takes tens of seconds, sends four megabytes, and its product is UNLISTED - a URL
#     nobody has. It is shaped like the Director: a daemon thread, a live progress bus, and the
#     Doorman's BOSS-only gate. It does not go through the Hands, because the Hands' gate exists
#     to put a human between the house and an act strangers can see, and an unlisted video is
#     seen by nobody. Blocking an HTTP request for a minute to ask about it would break the
#     Async Law to buy a confirmation of something invisible.
#
#   THE FLIP TO PUBLIC takes one HTTP call and about four hundred milliseconds, and it is the
#     moment the film becomes visible to the world. So it is shaped like send_email: a registry
#     hand, which inherits the Chain Card, the one-pending-at-a-time slot and - because the
#     server's Doorman seals the confirming utterance - the handshake window. That is where §40's
#     "public only on the boss's spoken Yes" lives, and "a guest's yes leaves it unlisted" is
#     then a property of handshake_open()'s `seal == "BOSS"` rather than a new rule written here.
#
# THE ONE COST, NAMED RATHER THAN HIDDEN: a registry hand runs in a SUBPROCESS, and the progress
# bus is in-process state that /jobs reads out of the server's own memory. So publish()'s bus job
# reaches the LEDGER on disk - which is the durable record §40 asks for, carrying the id, the url
# and both privacy states - and does not appear as a live chip in the glass. For four hundred
# milliseconds of work that is the right trade: the chip would arrive and vanish inside a single
# poll interval, and the audit row is the thing that has to be true in a year.
STEPS = ("encode-check", "meta", "thumb", "verify")
PUBLISH_STEPS = ("publish",)


def upload(folder, cfg=None, report=True, on_card=None):
    """Upload the film in `folder` and leave it UNLISTED. The whole journey, with the bus.

    THE ONE ENTRY POINT, the way director.direct() is - the server's route, the hand crank and
    the proof all come through here, so there is one implementation of "what uploading means"
    rather than one per caller.
    """
    folder = str(folder or "")
    out = {"ok": False, "why": "", "folder": folder, "videoId": "", "url": "",
           "privacy": "", "bytes": 0, "chunks": 0, "resumes": 0, "retries": 0,
           "title": "", "tags": [], "thumb": False, "job": "", "elapsedS": 0.0}
    began = time.monotonic()

    # ---- THE PACKAGE FIRST, BEFORE THE BUS AND BEFORE ANY BYTE ------------------------------
    # A missing disclosure line and an unreadable script.md are both refusals, and refusing them
    # here means no job is ever opened for an upload that was never going to happen - the glass
    # does not show a chip that exists only to go red half a second later.
    kit = package(folder, cfg=cfg)
    if not kit["ok"]:
        out["why"] = kit["why"]
        return out
    out["title"], out["tags"] = kit["title"], list(kit["tags"])

    scope = scope_report()
    if not scope["canUpload"]:
        out["why"] = (status().get("why") or
                      "this machine is not connected to a YouTube channel yet")
        return out

    # `report` IS TRUE, FALSE, OR A REPORTER SOMEBODY ELSE ALREADY OPENED - director.direct()'s
    # signature, and for its reason. _Manager has to open the job on the CALLING thread, under
    # its own lock, so that request() can hand the job id back to the page in the same breath as
    # the sentence; a job opened inside the daemon thread does not exist yet when the HTTP reply
    # is written, and the page would have to guess which job on /jobs was its own.
    rep = None
    if report is True:
        try:
            import jobs
            rep = jobs.Reporter("broadcast", list(STEPS), verb="UPLOADING",
                                topic=kit["topic"])
        except Exception:                                          # noqa: BLE001
            rep = None
    elif report:
        rep = report
    if rep is not None:
        out["job"] = getattr(rep, "job", "")

    def step(name, detail=""):
        if rep:
            rep.step(name, detail=detail)

    def note(detail):
        if rep:
            rep.note(detail)

    def stop(why):
        out["why"] = why
        out["elapsedS"] = round(time.monotonic() - began, 1)
        if rep:
            rep.failed(why, videoId=out["videoId"], url=out["url"],
                       privacy=out["privacy"], path=str(pathlib.Path(folder) / "final.mp4"))
        return out

    # ---- 1. ENCODE CHECK --------------------------------------------------------------------
    film = str(pathlib.Path(folder) / "final.mp4")
    step("encode-check", "reading the finished file")
    probe = encode_check(film)
    if not probe["ok"]:
        return stop(probe["why"])
    note("%.1fs, %s/%s, %.1f MB" % (probe["durationS"], probe["vcodec"], probe["acodec"],
                                    probe["bytes"] / 1048576.0))

    # ---- 2. META + THE BYTES ----------------------------------------------------------------
    # ONE STEP FOR BOTH, because they are one HTTP conversation: the resumable session is opened
    # by POSTing the metadata and is then fed the file. Reporting them as two steps would show a
    # "meta" that completed in 300ms and a second step the plan never declared.
    step("meta", "%s - %d tag(s), %d chars of description"
         % (kit["title"][:60], len(kit["tags"]), len(kit["description"])))
    if on_card:
        on_card(dict(kit))
    sent = insert(film, kit, on_note=note,
                  on_chunk=lambda got, total, n: note(
                      "%d%% - chunk %d, %.1f of %.1f MB"
                      % (int(100.0 * got / max(1, total)), n, got / 1048576.0,
                         total / 1048576.0)))
    out.update({k: sent.get(k, out[k]) for k in
                ("videoId", "url", "bytes", "chunks", "resumes", "retries")})
    if not sent["ok"]:
        return stop(sent["why"])

    # ---- 3. THE THUMBNAIL -------------------------------------------------------------------
    # AFTER THE INSERT AND NOT BEFORE, which is why §40's list reads thumb-before-meta and this
    # code does not: thumbnails.set takes a videoId, so there is nothing to set a thumbnail ON
    # until the film exists. The order is the API's, not a preference.
    step("thumb", "the Director's own poster frame")
    if kit["thumbnail"]:
        thumb = set_thumbnail(out["videoId"], kit["thumbnail"])
        out["thumb"] = bool(thumb["ok"])
        if not thumb["ok"]:
            # NOT A FAILURE OF THE UPLOAD. The film is on the channel; a missing custom
            # thumbnail is a cosmetic loss, and failing the job here would report a successful
            # permanent upload as a failure - after which a human might upload it again.
            note("the poster was refused: %s" % thumb["why"][:80])
    else:
        note("no poster.jpg beside the film - YouTube will choose a frame")

    # ---- 4. READ IT BACK --------------------------------------------------------------------
    step("verify", "asking YouTube what it has")
    seen = verify(out["videoId"])
    out["privacy"] = seen.get("privacy") or ""
    if not seen["ok"]:
        # THE BYTES WENT. Reported as done-with-a-caveat rather than failed, for the same reason
        # the thumbnail is: the upload returned an id, so the film exists.
        note("it could not be read back yet: %s" % seen["why"][:80])
    out["ok"] = True
    out["processing"] = seen.get("processing") or ""
    out["elapsedS"] = round(time.monotonic() - began, 1)
    if rep:
        rep.done("unlisted at %s" % out["url"],
                 videoId=out["videoId"], url=out["url"],
                 privacy=out["privacy"] or PRIVACY_FIRST,
                 path=film, durationS=probe["durationS"],
                 poster=kit["thumbnail"], cited=[c["id"] for c in kit["cited"]])
    return out


def publish(video_id, folder="", report=True):
    """The flip to public. One call, one ledger row, both privacy states on it.

    SEPARATE FROM upload() AND WITH NO PATH BETWEEN THEM. Nothing in upload() can call this -
    the only way a film becomes public is a second, deliberate act by a caller that already
    holds a video id, which in this house means a human said yes to a Chain Card carrying the
    unlisted URL.
    """
    out = {"ok": False, "why": "", "videoId": str(video_id or ""), "url": "",
           "from": "", "to": "", "job": ""}
    if not out["videoId"]:
        out["why"] = "no video was named"
        return out
    rep = None
    if report:
        try:
            import jobs
            rep = jobs.Reporter("publish", list(PUBLISH_STEPS), verb="PUBLISHING",
                                topic=out["videoId"])
            out["job"] = rep.job
            rep.step("publish", "unlisted to public")
        except Exception:                                          # noqa: BLE001
            rep = None
    moved = set_privacy(out["videoId"], PRIVACY_PUBLIC)
    out["from"], out["to"] = moved.get("from") or "", moved.get("to") or ""
    out["url"] = moved.get("url") or watch_url(out["videoId"])
    if not moved["ok"]:
        out["why"] = moved["why"]
        if rep:
            rep.failed(out["why"], videoId=out["videoId"], url=out["url"],
                       privacy=out["from"], privacyFrom=out["from"], privacyTo="")
        return out
    # READ IT BACK, because a 200 from videos.update is a claim and videos.list is the evidence.
    seen = verify(out["videoId"])
    out["privacy"] = seen.get("privacy") or out["to"]
    out["title"] = seen.get("title") or ""
    out["ok"] = (out["privacy"] == PRIVACY_PUBLIC)
    if not out["ok"]:
        out["why"] = ("YouTube accepted the change and still reports the film as %s"
                      % (out["privacy"] or "nothing at all"))
    if rep:
        (rep.done if out["ok"] else rep.failed)(
            "%s is %s" % (out["videoId"], out["privacy"]),
            videoId=out["videoId"], url=out["url"], privacy=out["privacy"],
            privacyFrom=out["from"], privacyTo=out["to"])
    return out


def uploaded(video_id=""):
    """What THIS HOUSE put on the channel, out of its own ledger. A row, or {} / the whole list.

    THE PUBLISH HAND'S GUARD, and the reason it is needed is worth stating plainly. The flip to
    public is a registry tool, which means a language model can propose it and can therefore
    propose a video ID - and an id is sixteen characters of base64 that a model is perfectly
    capable of producing from nothing. Without this, a hallucinated id would be a request to make
    a STRANGER'S video public, and whether that would succeed depends only on whether the boss's
    channel happens to own it.

    So the hand will only publish a film this house uploaded, and "this house uploaded it" is not
    a claim it takes from the request: it is a row in jobs-ledger.json, written by upload() at the
    moment the bytes were accepted. A video id that is not in the ledger is refused by name.

    IT READS THE LEDGER FILE RATHER THAN THE LIVE BUS because the hand runs in a SUBPROCESS - it
    has no access to the server's memory - and because a film uploaded on Monday is published on
    Friday, long after any in-memory job has gone.
    """
    rows = []
    try:
        import jobs
        for row in jobs.ledger() or []:
            if str(row.get("name") or "") == "broadcast" and row.get("videoId"):
                rows.append(row)
    except Exception:                                              # noqa: BLE001
        return {} if video_id else []
    if not video_id:
        return rows
    want = str(video_id)
    # NEWEST FIRST, so a film re-read after a privacy change reports its latest known state.
    for row in reversed(rows):
        if str(row.get("videoId")) == want:
            return row
    return {}


def poster_of(video_id):
    """The poster file for a video id, from the ledger - or "" . NO PATH COMES FROM A CALLER.

    THE CHAIN CARD'S THUMBNAIL PLATE IS SERVED THROUGH THIS, and the indirection is the whole
    point. config.json's law in this house is that the server serves the viewer/ folder and
    nothing else, and a poster lives in output/, outside it. A route taking a PATH would be a
    route that serves arbitrary files from this disk the moment somebody writes `..` into it.
    A route taking a VIDEO ID can only ever return a file that upload() itself recorded, because
    the id is looked up in a ledger this machine wrote and the path comes out of the row - the
    browser never names a file at all.
    """
    row = uploaded(video_id) or {}
    return poster_path(row.get("poster"))


def poster_path(path):
    """A poster this house may serve, resolved - or "". THE ONE VALIDATOR, called by both.

    BELT AND BRACES FOR poster_of(), and the whole of the check for the server's second lookup.
    Even out of our own ledger the file must be a jpg under the Director's output root: a ledger
    is a file on disk, and a file on disk is a thing that can be edited. The server's fallback
    reads a path out of the pending proposal's parameters, which can have come from a language
    model's tool tag, so for that caller this function is the only thing standing between a
    GET and a file - which is why the two share it rather than each keeping a copy that could
    be tightened in one place and not the other.

    THREE TESTS, AND `..` IS BEATEN BY THE SECOND. resolve() flattens the traversal before the
    parent check sees it, so output/videos/x/../../../secrets/token.json resolves to a path
    whose parents do not include the output root and is refused - and would have been refused
    by the suffix test first anyway. The third is existence, because a route that 404s on a
    missing file reports the truth and a route that opens one reports an exception.
    """
    text = str(path or "")
    if not text:
        return ""
    try:
        resolved = pathlib.Path(text).resolve()
    except (OSError, ValueError):
        return ""
    try:
        import director
        root = pathlib.Path(director.OUT_ROOT).resolve()
    except Exception:                                              # noqa: BLE001
        root = (ROOT / "output").resolve()
    if resolved.suffix.lower() not in (".jpg", ".jpeg"):
        return ""
    if root not in resolved.parents:
        return ""
    return str(resolved) if resolved.exists() else ""


def card(folder, cfg=None, video_id="", url=""):
    """What the Chain Card shows before the boss says yes. Pure, so a harness can read it.

    §40: "the Chain Card shows title, description, tags, thumbnail plate and the unlisted URL".
    Composed server-side like every other seal word in this house, so the plate the harness
    asserts is the plate the boss actually read.
    """
    kit = package(folder, cfg=cfg)
    if not kit["ok"]:
        return {"ok": False, "why": kit["why"]}
    return {"ok": True, "why": "",
            "title": kit["title"], "titleChars": len(kit["title"]),
            "description": kit["description"], "descriptionChars": len(kit["description"]),
            "hook": kit["hook"], "citedLine": kit["citedLine"],
            "disclosure": kit["disclosure"],
            "tags": kit["tags"], "tagChars": kit["tagChars"],
            "thumbnail": kit["thumbnail"],
            "thumbnailBytes": (os.path.getsize(kit["thumbnail"])
                               if kit["thumbnail"] and os.path.exists(kit["thumbnail"]) else 0),
            "videoId": str(video_id or ""), "url": str(url or ""),
            "privacy": PRIVACY_FIRST,
            "asks": "public"}


class _Manager:
    """One upload at a time, on a daemon thread. director._Manager's shape and its reasons.

    ONE AT A TIME is not a performance choice: two concurrent uploads would interleave their
    progress on a bus the glass renders as a single chip, and an upload is the one operation in
    this house whose duplicate cannot be deleted.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._live = ""                 # the job id of the upload in flight, "" when idle
        self._title = ""
        self.last = {}                  # the last finished result, for a harness and a log

    def live(self):
        with self._lock:
            return self._live, self._title

    def request(self, folder, why="boss", cfg=None):
        """(started, sentence, job). Never blocks, never raises, never uploads on this thread.

        EVERY REFUSAL HAPPENS BEFORE THE THREAD EXISTS - no channel, no disclosure line, no
        script.md, an upload already in flight. The boss hears the reason in the same breath as
        the request, and no job is opened for work that was never going to start.
        """
        with self._lock:
            if self._live:
                return False, ("I am still putting up “%s”, sir - one at a time."
                               % self._title), self._live
        kit = package(folder, cfg=cfg)
        if not kit["ok"]:
            return False, kit["why"], ""
        if not scope_report()["canUpload"]:
            return False, (status().get("why") or "no channel is connected yet"), ""
        probe = encode_check(str(pathlib.Path(folder) / "final.mp4"))
        if not probe["ok"]:
            # THE ENCODE CHECK IS RUN TWICE AND THAT IS DELIBERATE: here, so that a half-written
            # file is refused out loud before a job is opened, and again inside upload() as the
            # first bus step, so that the hand crank and the proof get the same gate without
            # having to remember to call it. It is an ffprobe on a local file - cheap enough that
            # paying for it twice is better than a branch that can be forgotten.
            return False, probe["why"], ""
        try:
            import jobs
            report = jobs.Reporter("broadcast", list(STEPS), verb="UPLOADING",
                                   topic=kit["topic"])
        except Exception as exc:                                   # noqa: BLE001
            return False, "the progress bus would not open: %s" % _sentence(exc), ""
        with self._lock:
            self._live, self._title = report.job, kit["title"]

        def run():
            try:
                out = upload(folder, cfg=cfg, report=report)
            except Exception as exc:                               # noqa: BLE001
                out = {"ok": False, "folder": str(folder), "why": _sentence(exc)}
                try:
                    report.failed(out["why"])
                except Exception:                                  # noqa: BLE001
                    pass
            with self._lock:
                self._live, self._title = "", ""
                self.last = out
            import sys
            sys.stderr.write("broadcast: %r ok=%s id=%r why=%r\n"
                             % (str(folder), bool(out.get("ok")),
                                out.get("videoId") or "", out.get("why") or ""))

        threading.Thread(target=run, name="broadcast-upload", daemon=True).start()
        return (True, "Putting “%s” up now, sir - unlisted, about a minute. I shall "
                "bring you the link and ask before anyone else can see it." % kit["title"],
                report.job)


MANAGER = _Manager()
