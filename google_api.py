#!/usr/bin/env python3
"""google_api.py - the one road to Google, and the only place a token is ever read.

THE SHAPE OF THE THING. Two files in secrets/, three scopes, one loopback port, and a
single function that puts an authenticated request on the wire. Everything else in this
repository that wants Google goes through here, so there is exactly one place to audit
when the question is "what can this machine do to my account".

  secrets/google_client.json   the file downloaded from the Cloud console. Read, never
                               written. Its client_secret is NOT a secret in the usual
                               sense - RFC 8252 says an installed app cannot keep one, and
                               Google's own docs call it "optional" for this flow - which
                               is the argument for PKCE below, not an argument for
                               carelessness.
  secrets/google_token.json    written by connect() and refresh(). This is the file that
                               matters: a refresh token does not expire on its own, so
                               leaking it is worse than leaking the client file. secrets/
                               is gitignored and the server serves only viewer/, so it is
                               unreachable from the browser by construction rather than by
                               a rule somebody has to remember.

WHY PKCE WHEN THERE IS A CLIENT SECRET. The loopback redirect lands on 127.0.0.1, and any
other process on this machine could in principle race to listen on that port or read the
authorization code out of a URL. PKCE closes that: the code is worthless without the
verifier, which never leaves this process. Google recommends it for installed apps and
costs nothing to do properly, so it is done properly - S256, never "plain".

WHAT IS NOT HERE, DELIBERATELY. No token, no refresh token, no authorization code and no
account address is ever returned to a caller that prints things, logged, or put on the
wire to the browser. status() returns booleans, a state word, the account address (which
the panel is specifically asked to show) and sha256 digests. digest() exists so that a
harness can prove two things are the same token without either of them learning what the
token is.

Standard library only: urllib, json, base64, hashlib, secrets, http.server, threading.
"""
import base64
import hashlib
import json
import os
import pathlib
import secrets as secretslib
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

ROOT = pathlib.Path(__file__).resolve().parent
SECRETS = ROOT / "secrets"
CLIENT_FILE = SECRETS / "google_client.json"
TOKEN_FILE = SECRETS / "google_token.json"

AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
REVOKE_ENDPOINT = "https://oauth2.googleapis.com/revoke"
CALENDAR_BASE = "https://www.googleapis.com/calendar/v3"
GMAIL_BASE = "https://gmail.googleapis.com/gmail/v1"

# THREE SCOPES AND NOT ONE CHARACTER WIDER. gmail.send can send and can do nothing else -
# it cannot read a single message in the mailbox. gmail.compose is here only because the
# PROOF must exercise auth and serialization without a letter leaving the building, and
# drafts.create is the narrowest method that does that; it also happens to be what lets
# users.getProfile tell the panel which account is connected. calendar.events can write
# events and cannot read the rest of the calendar's settings. Notably absent:
# gmail.readonly, gmail.modify, https://mail.google.com/ (which is total control of the
# mailbox), and plain "calendar". A wider scope is one consent screen away and would never
# be noticed; that is exactly why the list is written down here and asserted in preflight.
SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/calendar.events",
]

# ITS OWN PORT, AND NOT THE SERVER'S. 4700 is the house; 9222-9254 are the harnesses'
# debugging ports and one of them is watched by focus.py, so nothing here may go near
# them. 4731 is otherwise unused on this machine and is fixed rather than ephemeral for
# one reason: a fixed loopback port can be allowed through a firewall once, and an
# ephemeral one asks the question again every time. If it is busy, connect() says so and
# refuses rather than silently listening somewhere the redirect will not arrive.
LOOPBACK_PORT = 4731
LOOPBACK_HOST = "127.0.0.1"
REDIRECT_URI = "http://%s:%d/" % (LOOPBACK_HOST, LOOPBACK_PORT)

HTTP_TIMEOUT = 20.0
CONSENT_TIMEOUT = 300.0
REFRESH_SKEW = 120.0          # refresh this many seconds BEFORE expiry, not after

_LOCK = threading.RLock()
_PENDING = {}                 # the one consent attempt in flight, if any


# ------------------------------------------------------------------ small helpers

def digest(value):
    """A short sha256 of anything, for logs and harnesses that must not see the thing.

    Twelve hex characters is 48 bits: enough that "the token did not change across a
    refresh" is a meaningful assertion, and far too little to be worth attacking.
    """
    if not value:
        return ""
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()[:12]


def _now():
    return time.time()


def _read_json(path):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


def client():
    """The downloaded client file, under either of the two keys Google ships it with."""
    data = _read_json(CLIENT_FILE)
    if not data:
        return None
    body = data.get("installed") or data.get("web") or data
    if not isinstance(body, dict) or not body.get("client_id"):
        return None
    return body


def token():
    return _read_json(TOKEN_FILE)


def save_token(data):
    """Write the token file with an owner-only mode, and never through a partial write.

    The temp-file-and-replace is not ceremony: a refresh that is interrupted halfway
    through writing would otherwise leave a truncated token file, and the failure mode of
    that is "reconnect needed" on a machine whose connection was in fact fine.
    """
    with _LOCK:
        SECRETS.mkdir(parents=True, exist_ok=True)
        tmp = TOKEN_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=1) + "\n", encoding="utf-8")
        try:
            os.chmod(tmp, 0o600)
        except OSError:
            pass                      # Windows ACLs; the folder is the real boundary
        os.replace(tmp, TOKEN_FILE)


def forget():
    """Delete the token file. Returns True if there was one to delete."""
    with _LOCK:
        try:
            TOKEN_FILE.unlink()
            return True
        except FileNotFoundError:
            return False
        except OSError:
            return False


# ------------------------------------------------------------------ the wire

def _post_form(url, fields):
    """A form POST that returns (status, parsed-json, error-sentence).

    Google's two error shapes are both handled here so no caller has to guess: the token
    endpoint answers {"error": "invalid_grant", "error_description": "..."} and the APIs
    answer {"error": {"code": 400, "message": "..."}}. Either way the caller gets one
    English sentence it can speak aloud.
    """
    body = urllib.parse.urlencode(fields).encode("ascii")
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    return _send(req)


def _send(req):
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as res:
            raw = res.read().decode("utf-8", "replace")
            if not raw.strip():
                return res.status, {}, ""
            try:
                return res.status, json.loads(raw), ""
            except ValueError:
                return res.status, {}, "Google answered something that was not JSON"
    except urllib.error.HTTPError as exc:
        raw = ""
        try:
            raw = exc.read().decode("utf-8", "replace")
        except Exception:
            pass
        parsed = {}
        try:
            parsed = json.loads(raw) if raw.strip() else {}
        except ValueError:
            parsed = {}
        return exc.code, parsed, _error_sentence(exc.code, parsed)
    except urllib.error.URLError as exc:
        return 0, {}, "Google could not be reached (%s)" % str(exc.reason)[:80]
    except (TimeoutError, OSError) as exc:
        return 0, {}, "Google did not answer in time (%s)" % type(exc).__name__


def _error_sentence(code, parsed):
    """Name the failure plainly, and never quote a token back out of it."""
    err = parsed.get("error")
    if isinstance(err, dict):
        message = str(err.get("message") or "")[:200]
        return "Google refused it (HTTP %d: %s)" % (code, message or "no reason given")
    if isinstance(err, str):
        described = str(parsed.get("error_description") or "")[:200]
        return "Google refused it (HTTP %d: %s%s)" % (
            code, err, " - " + described if described else "")
    return "Google refused it (HTTP %d)" % code


# ------------------------------------------------------------------ consent

def _pkce():
    """A verifier and its S256 challenge, base64url with the padding stripped."""
    verifier = base64.urlsafe_b64encode(secretslib.token_bytes(48)).decode("ascii").rstrip("=")
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode("ascii")).digest()).decode("ascii").rstrip("=")
    return verifier, challenge


def consent_url():
    """Build the consent URL and the PKCE/state secrets that must outlive it.

    Returns (url, kit, error). The kit is kept by the caller and never shown: it holds the
    verifier that turns the authorization code into a token, and the state that proves the
    redirect we receive is the one we sent.
    """
    cfg = client()
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
        # offline + consent together are what guarantee a refresh_token EVERY time rather
        # than only on the very first authorization. Without them a reconnect can return
        # an access token and no refresh token, and the connection then dies quietly an
        # hour later - which looks exactly like a bug in this file and is not one.
        "access_type": "offline",
        "prompt": "consent",
    }
    url = AUTH_ENDPOINT + "?" + urllib.parse.urlencode(query)
    return url, {"verifier": verifier, "state": state}, ""


class _Catcher(BaseHTTPRequestHandler):
    """One request, one answer, then the server dies. It never serves a file."""

    def do_GET(self):                                     # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        got = {k: (v[0] if v else "") for k, v in params.items()}
        self.server.caught = got
        ok = bool(got.get("code")) and not got.get("error")
        page = ("<!doctype html><meta charset=utf-8><title>Google</title>"
                "<style>body{background:#06070c;color:#d8e0f0;font:15px/1.6 system-ui;"
                "display:grid;place-items:center;height:100vh;margin:0}"
                "b{color:%s}</style><div><b>%s</b><p>%s</p></div>"
                % ("#7fd8a8" if ok else "#e08a8a",
                   "Connected." if ok else "Not connected.",
                   "You may close this tab and go back to the console."
                   if ok else "Nothing was saved. The console will say why."))
        body = page.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        """Silence. The default handler prints the full request line - which is the line
        carrying the authorization code - straight to stderr, and stderr is a log file."""
        return


def _exchange(code, verifier):
    cfg = client()
    if not cfg:
        return None, "there is no Google client file any more"
    fields = {
        "client_id": cfg["client_id"],
        "code": code,
        "code_verifier": verifier,
        "grant_type": "authorization_code",
        "redirect_uri": REDIRECT_URI,
    }
    if cfg.get("client_secret"):
        fields["client_secret"] = cfg["client_secret"]
    status, parsed, err = _post_form(TOKEN_ENDPOINT, fields)
    if err or status >= 400:
        return None, err or "the token exchange failed (HTTP %d)" % status
    access = str(parsed.get("access_token") or "")
    if not access:
        return None, "Google returned no access token"
    data = {
        "access_token": access,
        "refresh_token": str(parsed.get("refresh_token") or ""),
        "token_type": str(parsed.get("token_type") or "Bearer"),
        "scope": str(parsed.get("scope") or " ".join(SCOPES)),
        "expires_at": _now() + float(parsed.get("expires_in") or 3600),
        "connected_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "email": "",
    }
    if not data["refresh_token"]:
        # Honest rather than convenient: without this the connection works for an hour
        # and then asks to be reconnected, and the reason would be invisible.
        return None, ("Google returned no refresh token, so the connection would die "
                      "within the hour - not saving it")
    data["email"] = _who(data["access_token"])
    save_token(data)
    return data, ""


def _who(access_token):
    """The connected account's address, via the narrowest method the scopes allow.

    users.getProfile accepts gmail.compose, which is already held. If Google declines it
    the connection is still perfectly good, so this returns "" and the panel says
    CONNECTED without an address rather than calling the whole thing broken.
    """
    req = urllib.request.Request(GMAIL_BASE + "/users/me/profile", method="GET")
    req.add_header("Authorization", "Bearer " + access_token)
    status, parsed, err = _send(req)
    if err or status >= 400:
        return ""
    return str(parsed.get("emailAddress") or "")


def connect(background=True):
    """Open the consent page and catch the redirect. Returns a status-shaped dict.

    The HTTP route that calls this must not block: consent takes as long as a human takes.
    So with background=True this returns immediately after the browser has been opened,
    and the panel watches status() until the state word changes.
    """
    url, kit, err = consent_url()
    if err:
        return {"state": "no-client", "why": err, "opened": False}
    try:
        server = HTTPServer((LOOPBACK_HOST, LOOPBACK_PORT), _Catcher)
    except OSError as exc:
        return {"state": "error", "opened": False,
                "why": ("the loopback port %d is not free (%s), so Google's redirect "
                        "would not arrive" % (LOOPBACK_PORT, type(exc).__name__))}
    server.caught = None
    server.timeout = CONSENT_TIMEOUT

    def wait():
        with _LOCK:
            _PENDING.update({"started": _now(), "state": "waiting", "why": ""})
        try:
            server.handle_request()            # exactly one; the timeout applies to it
            got = server.caught or {}
        finally:
            try:
                server.server_close()
            except OSError:
                pass
        with _LOCK:
            if not got:
                _PENDING.update({"state": "timeout",
                                 "why": "nobody came back from Google within %ds"
                                        % int(CONSENT_TIMEOUT)})
                return
            if got.get("error"):
                _PENDING.update({"state": "refused",
                                 "why": "Google said: %s" % str(got.get("error"))[:80]})
                return
            if got.get("state") != kit["state"]:
                # The one check that makes the loopback safe to use at all.
                _PENDING.update({"state": "refused",
                                 "why": "the redirect did not carry the state we sent, "
                                        "so it was not ours and was thrown away"})
                return
        data, exchange_err = _exchange(got.get("code") or "", kit["verifier"])
        with _LOCK:
            if exchange_err:
                _PENDING.update({"state": "refused", "why": exchange_err})
            else:
                _PENDING.update({"state": "connected", "why": "",
                                 "email": data.get("email") or ""})

    thread = threading.Thread(target=wait, name="google-consent", daemon=True)
    thread.start()
    opened = _open_browser(url)
    out = {"state": "waiting", "opened": opened, "port": LOOPBACK_PORT,
           "why": "" if opened else ("the consent page could not be opened - paste the "
                                     "URL the console printed instead")}
    if not background:
        thread.join(CONSENT_TIMEOUT + 5)
        out = status()
    return out


def _open_browser(url):
    """Open the default browser with no console window and no shell string.

    os.startfile is used rather than a command line because a URL on a command line is a
    URL that can be quoted wrongly - and because preflight asserts that nothing this
    server starts shows a console window.
    """
    try:
        os.startfile(url)                                          # noqa: S606 (Windows)
        return True
    except Exception:
        try:
            import webbrowser
            return bool(webbrowser.open(url))
        except Exception:
            return False


def pending():
    with _LOCK:
        return dict(_PENDING)


def disconnect():
    """Delete the token, and tell Google to forget it too if it will listen.

    The revoke is best-effort on purpose: the file is the thing this machine controls, so
    it goes first and unconditionally. A revoke that fails because the network is down
    must not leave a live refresh token on the disk.
    """
    data = token() or {}
    had = forget()
    revoked = False
    refresh = data.get("refresh_token") or data.get("access_token")
    if refresh:
        status_code, _parsed, _err = _post_form(REVOKE_ENDPOINT, {"token": refresh})
        revoked = 200 <= status_code < 300
    with _LOCK:
        _PENDING.clear()
    return {"had": had, "revoked": revoked}


# ------------------------------------------------------------------ using it

def access():
    """A usable access token, refreshing first if it is close to expiry.

    Returns (token, state, why). state is one of connected / absent / reconnect / no-client
    so that every caller can turn it into the right sentence without parsing English.
    """
    cfg = client()
    if not cfg:
        return "", "no-client", ("there is no Google client file at "
                                 "secrets/google_client.json")
    data = token()
    if not data or not data.get("refresh_token"):
        return "", "absent", "this machine is not connected to Google yet"
    if data.get("access_token") and float(data.get("expires_at") or 0) - REFRESH_SKEW > _now():
        return data["access_token"], "connected", ""
    fields = {
        "client_id": cfg["client_id"],
        "refresh_token": data["refresh_token"],
        "grant_type": "refresh_token",
    }
    if cfg.get("client_secret"):
        fields["client_secret"] = cfg["client_secret"]
    status_code, parsed, err = _post_form(TOKEN_ENDPOINT, fields)
    if status_code >= 400 or err:
        # invalid_grant is the one that means the human must act: the refresh token has
        # been revoked, or the password changed, or the grant expired. Anything else may
        # be the network, and saying RECONNECT for a flat network would be a lie.
        reason = str((parsed or {}).get("error") or "")
        if reason == "invalid_grant":
            return "", "reconnect", ("Google will not renew the connection - it has been "
                                     "revoked or has expired, and must be reconnected")
        return "", "connected", err or "the token could not be refreshed (HTTP %d)" % status_code
    fresh = str(parsed.get("access_token") or "")
    if not fresh:
        return "", "reconnect", "Google renewed nothing, so the connection must be remade"
    data["access_token"] = fresh
    data["expires_at"] = _now() + float(parsed.get("expires_in") or 3600)
    if parsed.get("refresh_token"):
        data["refresh_token"] = str(parsed["refresh_token"])
    if parsed.get("scope"):
        data["scope"] = str(parsed["scope"])
    if not data.get("email"):
        data["email"] = _who(fresh)
    save_token(data)
    return fresh, "connected", ""


def call(method, url, body=None):
    """One authenticated request. Returns (http_status, parsed, error-sentence).

    Every caller in this repository goes through this function, which means the
    Authorization header is written in exactly one place and a token cannot end up in a
    query string by somebody's convenience.
    """
    bearer, state, why = access()
    if not bearer:
        return 0, {}, why or "not connected to Google"
    data = None
    req_headers = {"Authorization": "Bearer " + bearer}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        req_headers["Content-Type"] = "application/json; charset=utf-8"
    req = urllib.request.Request(url, data=data, method=method)
    for key, value in req_headers.items():
        req.add_header(key, value)
    status_code, parsed, err = _send(req)
    if status_code == 401:
        # One retry, and one only: a 401 on a token we just refreshed is not a race, it is
        # a revocation, and retrying it forever would hammer Google to no purpose.
        data_file = token() or {}
        data_file["expires_at"] = 0
        save_token(data_file)
        bearer, state, why = access()
        if not bearer:
            return status_code, parsed, why or "Google rejected the connection"
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Authorization", "Bearer " + bearer)
        if body is not None:
            req.add_header("Content-Type", "application/json; charset=utf-8")
        status_code, parsed, err = _send(req)
    return status_code, parsed, err


def status():
    """What the panel shows, and nothing a log would be sorry for carrying.

    No token, no refresh token and no authorization code appears in this dict. The account
    address does, because the panel is specifically asked to show which account is
    connected - and a digest of the refresh token does, so that a harness can prove a
    refresh kept the same grant without ever seeing it.
    """
    cfg = client()
    out = {
        "clientPresent": bool(cfg),
        "clientId": (str(cfg.get("client_id"))[:12] + "…") if cfg else "",
        "scopes": list(SCOPES),
        "port": LOOPBACK_PORT,
        "redirectUri": REDIRECT_URI,
        "state": "no-client",
        "email": "",
        "why": "",
        "connectedAt": "",
        "tokenDigest": "",
        "expiresInS": 0,
        "pending": pending().get("state") or "",
    }
    if not cfg:
        out["why"] = "there is no client file at secrets/google_client.json"
        return out
    data = token()
    if not data or not data.get("refresh_token"):
        out["state"] = "absent"
        out["why"] = "not connected yet"
        return out
    out.update({
        "email": str(data.get("email") or ""),
        "connectedAt": str(data.get("connected_at") or ""),
        "tokenDigest": digest(data.get("refresh_token")),
        "expiresInS": max(0, int(float(data.get("expires_at") or 0) - _now())),
        "grantedScopes": str(data.get("scope") or ""),
    })
    # The state word is what the panel renders, so it is resolved against Google rather
    # than guessed from the file: a token file can look perfect and be revoked.
    _bearer, live, why = access()
    out["state"] = "connected" if live == "connected" else live
    out["why"] = why
    if live == "connected" and not out["email"]:
        out["email"] = str((token() or {}).get("email") or "")
    return out


# ------------------------------------------------------------------ time, once

# HALF AN HOUR, AND IT IS SHOWN RATHER THAN ASSUMED. "remind me to call the client at
# four" names a start and no end, and a calendar event must have both. The brain is told
# never to invent a time, so the DEFAULT lives here instead of in the model: thirty
# minutes, computed in one place, and rendered onto the confirmation card as part of the
# duration before anybody presses Yes. An invented end that nobody saw would be the same
# mistake as an invented address.
DEFAULT_MINUTES = 30
_MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August",
           "September", "October", "November", "December")
_DAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")


def _parse_stamp(text):
    """A date or a datetime, or None. ISO-8601 only, and deliberately nothing else.

    No natural language. "next Tuesday" is not parsed here and must not be: a calendar
    write is irreversible enough that guessing which Tuesday somebody meant is worse than
    asking. The brain is given the current local time and told to do the arithmetic, and
    what arrives here is either a stamp or a refusal.
    """
    import datetime as dt
    raw = str(text or "").strip()
    if not raw:
        return None, False
    if len(raw) == 10 and raw.count("-") == 2:
        try:
            return dt.datetime.strptime(raw, "%Y-%m-%d"), True
        except ValueError:
            return None, False
    cleaned = raw.replace("Z", "+00:00").replace(" ", "T", 1) if " " in raw and "T" not in raw else raw.replace("Z", "+00:00")
    try:
        parsed = dt.datetime.fromisoformat(cleaned)
    except ValueError:
        return None, False
    if parsed.tzinfo is None:
        # A naive stamp means local time on THIS machine, and is given this machine's
        # offset explicitly. Sending an offset rather than an IANA zone name keeps the
        # standard library sufficient and removes a whole class of "which Europe/London".
        parsed = parsed.astimezone()
    return parsed, False


def _pretty_when(moment, all_day):
    day = _DAYS[moment.weekday()]
    date = "%s %d %s" % (day, moment.day, _MONTHS[moment.month - 1])
    if all_day:
        # Just the date. "all day" is the DURATION's word, and both halves are always
        # spoken together - saying it here too produced "Thursday 1 October, all day, all
        # day", which is what happens when two functions each think they own a fact.
        return date
    hour = moment.hour % 12 or 12
    ampm = "am" if moment.hour < 12 else "pm"
    clock = "%d:%02d %s" % (hour, moment.minute, ampm)
    return "%s at %s" % (date, clock)


def _pretty_span(seconds, all_day):
    if all_day:
        days = max(1, int(round(seconds / 86400.0)))
        return "all day" if days == 1 else "%d days" % days
    minutes = int(round(seconds / 60.0))
    if minutes < 60:
        return "%d minutes" % minutes
    hours, rest = divmod(minutes, 60)
    label = "%d hour%s" % (hours, "" if hours == 1 else "s")
    return label if not rest else "%s %d minutes" % (label, rest)


def event_times(start, end=""):
    """(start_obj, end_obj, when, duration, error) - Calendar v3's shapes, and the words.

    One function so the sentence on the confirmation card and the JSON on the wire can
    never disagree about what is being written. The card gets `when` and `duration`; the
    API gets the two objects; a bad stamp gets a sentence naming the shape expected.
    """
    import datetime as dt
    begin, all_day = _parse_stamp(start)
    if begin is None:
        return None, None, "", "", ("that start time is not a date I can read - it wants "
                                    "2026-09-28T16:00 or 2026-09-28")
    finish, end_all_day = _parse_stamp(end) if str(end or "").strip() else (None, all_day)
    defaulted = finish is None
    if defaulted:
        finish = (begin + dt.timedelta(days=1)) if all_day else (
            begin + dt.timedelta(minutes=DEFAULT_MINUTES))
    elif end_all_day != all_day:
        return None, None, "", "", ("the start and the end are not the same kind of time - "
                                    "one is a whole day and the other is an hour")
    if finish <= begin:
        return None, None, "", "", "that event would end before it started"
    if all_day:
        start_obj = {"date": begin.strftime("%Y-%m-%d")}
        end_obj = {"date": finish.strftime("%Y-%m-%d")}
    else:
        start_obj = {"dateTime": begin.isoformat()}
        end_obj = {"dateTime": finish.isoformat()}
    span = _pretty_span((finish - begin).total_seconds(), all_day)
    if defaulted and not all_day:
        span += " (the default, since no end was given)"
    return start_obj, end_obj, _pretty_when(begin, all_day), span, ""


# ------------------------------------------------------------------ the two hands

def insert_event(title, start, end, description="", calendar_id="primary"):
    """Calendar v3 events.insert on the primary calendar. Returns (event, error)."""
    body = {"summary": title, "start": start, "end": end}
    if description:
        body["description"] = description
    url = "%s/calendars/%s/events" % (CALENDAR_BASE, urllib.parse.quote(calendar_id))
    status_code, parsed, err = call("POST", url, body)
    if err or status_code >= 400:
        return None, err or "the calendar refused it (HTTP %d)" % status_code
    return parsed, ""


def get_event(event_id, calendar_id="primary"):
    url = "%s/calendars/%s/events/%s" % (CALENDAR_BASE, urllib.parse.quote(calendar_id),
                                        urllib.parse.quote(event_id))
    return call("GET", url)


def delete_event(event_id, calendar_id="primary"):
    url = "%s/calendars/%s/events/%s" % (CALENDAR_BASE, urllib.parse.quote(calendar_id),
                                        urllib.parse.quote(event_id))
    return call("DELETE", url)


def b64url(raw_bytes):
    """base64url with the padding stripped, which is what Gmail's raw field wants."""
    return base64.urlsafe_b64encode(raw_bytes).decode("ascii").rstrip("=")


def send_message(raw_bytes):
    url = GMAIL_BASE + "/users/me/messages/send"
    status_code, parsed, err = call("POST", url, {"raw": b64url(raw_bytes)})
    if err or status_code >= 400:
        return None, err or "Gmail refused it (HTTP %d)" % status_code
    return parsed, ""


def create_draft(raw_bytes):
    url = GMAIL_BASE + "/users/me/drafts"
    status_code, parsed, err = call("POST", url, {"message": {"raw": b64url(raw_bytes)}})
    if err or status_code >= 400:
        return None, err or "Gmail refused the draft (HTTP %d)" % status_code
    return parsed, ""


def delete_draft(draft_id):
    url = GMAIL_BASE + "/users/me/drafts/" + urllib.parse.quote(draft_id)
    return call("DELETE", url)
