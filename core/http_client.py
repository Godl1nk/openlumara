# -- AI GENERATED CODE (Qwen3.8 Flash Next (local) + GLM 5.3 security audit (openrouter) + Claude Opus 5.5 security audit) :: (2026-10-22) harness:openlumara
# ROSE22: i wanted this code to be very secure, since we've
# essentially hand-rolled our own HTTP library here in order to
# get rid of transitive dependencies..
# 
# since this is mostly AI generated, i passed it through multiple AI security audits
# using the combined power of local and cloud
# one of the rare exceptions where i used cloud AI
# as i don't want to risk security vulnerabilities
# for this part of the framework
"""
a tiny HTTP/1.1 client built on asyncio streams + h11.

h11 (pure-python, zero transitive dependencies)
handles the protocol correctness: status line + header parsing, body
framing, chunked transfer-encoding, keep-alive negotiation and EOF handling.

on top of h11 this adds:
- keep-alive connection pooling, with recovery from stale pooled connections
  (retried only for idempotent methods, and only before any response bytes)
- auth credentials are dropped on cross-origin redirects (never leaked) --
  this covers the basic_auth parameter AND caller-supplied Authorization /
  Cookie / Proxy-Authorization headers
- streaming response bodies (SSE) as an async iterator
- transparent gzip/deflate decompression via stdlib zlib
- json / form-urlencoded / raw bodies, query params, basic auth
- optional TLS verification bypass, per-request total timeouts and
  response body size caps. a 60s total timeout applies when the caller does
  not pass one; an explicit timeout_total=None keeps waiting forever
- browser-style redirects (disable with allow_redirects=False)
- hard-closing an in-flight response to cancel a stream
- optional pre-validated IP pinning (server_address=) so callers that
  resolve+validate before connecting never face a second, unvalidated
  DNS lookup (closes the DNS-rebinding TOCTOU window); the pin is part of
  the connection-pool identity (audit fix r2-H1), so a pooled socket can
  never bypass it

deliberately NOT implemented: cookies, proxies, brotli/zstd, HTTP/2, expect-continue.

security audit (2026-10-22 Qwen3.8 Flash Next Local) -- fixes applied, search "audit fix":
#1 credential headers stripped on cross-origin redirects; body descriptor
   headers dropped when 301/302/303 rewrite the request into a GET
#2 _return_conn no longer pools a socket after the client was closed
#3 query params merged into the URL query string (never appended after '#')
#4 local h11 request-validation errors are never classified as stale
   connections, so they are never retried
#5 invalid ports raise HTTPError instead of leaking a bare ValueError
#6 text() honors the response charset, falling back to utf-8
#7 keep-alive pooling decided via documented h11 state (both sides IDLE);
   requests now always send EndOfMessage so that state is reachable
   (without it, bodyless requests could never be pooled)
+   Response is now an async context manager
+   _request_once closes its socket when cancelled

security audit round 2 (2026-10-22 GLM-5.3 openrouter) -- fixes applied, search "r2-":
H1   the connection pool includes the pinned connect endpoint in its key
     (_pool_key): a request with server_address= can never be served an
     idle socket that was established without (or with a different) pin,
     so the DNS-rebinding validation can no longer be bypassed by a stale
     pooled connection; unpinned requests keep the classic key and never
     pick up pinned sockets either
M1   decompressed response bodies are capped (MAX_BODY_SIZE, with a
     per-client and per-request override) -> HTTPBodyTooLarge;
     defuses gzip/deflate bombs
M2   callers that omit timeout_total now get DEFAULT_TOTAL_TIMEOUT (60s)
     instead of waiting forever; an explicit timeout_total=None keeps the
     infinite behaviour, and core/api.py sets total_timeout=None on its
     client so long generations and model loads are never cut off
L1   https://<IP-literal> no longer raises a bare ValueError out of asyncio
     ("check_hostname requires server_hostname"): with verification on it
     needs Python >= 3.13 (the IP is passed as server_hostname, checked
     against IP SAN entries, no SNI sent), otherwise a clear HTTPError;
     with verification off no hostname/SNI is sent at all
L2   text() also catches ValueError -- a hostile charset label can select a
     non-text codec (base64/hex/zip) whose binascii.Error is not LookupError
L3   abandoning iter_any() mid-stream (break -> GeneratorExit) severs the
     socket instead of leaking it until GC

security audit round 3 (2026-10-22 Claude Opus 5.5) -- fixes applied, search "r3-":
H1   a pinned request (server_address=) no longer follows a redirect to
     another origin with plain, unvalidated DNS (the pin used to be dropped
     and the hop followed anyway); same-origin hops keep the pin, other
     hops are returned to the caller as the unfollowed 3xx
H2   decompression: raw wire bytes are capped too (bytes after a gzip
     member grew zlib's unused_data without limit), inflate output is
     bounded per call, multi-member gzip is decoded completely
M1   keep-alive pooling never worked: h11 reports DONE/DONE (not IDLE/IDLE)
     after an exchange, and trailing_data was called although it is a
     property (TypeError swallowed). both fixed; pooling is now live
M2   _exchange's header loop variable shadowed the pool-key parameter, so
     sockets were filed under a header NAME instead of the r2-H1 key
M3   caller headers merge case-insensitively (no duplicate UA/Accept-
     Encoding/Authorization, lowercase "host" works); caller Content-Length
     / Transfer-Encoding are ignored (body framing is ours)
L1   https -> http redirects are not auto-followed
L2   HEAD stays HEAD on 303; 301/302 only rewrite POST to GET
L3   read() caches the body (read() then text()/json() used to see b"")
L4   close() after the socket was pooled no longer severs the pooled socket
L5   request targets are percent-encoded where h11 would reject them; IDN
     hosts go into the Host header as IDNA
L6   a stale pooled connection is retried on a FRESH socket
L7   idle sockets are capped across all pool keys (MAX_IDLE_TOTAL)

security audit round 4 (2026-10-22 Qwen3.8 Flash Next local) -- fixes applied, search "r4-":
M1   the response-header phase is capped (MAX_HEADER_SIZE): h11 enforces
     no resource limits of its own, so a server streaming never-completing
     header bytes (or huge 1xx blocks) grew RAM without bound during the
     header wait; only a total timeout stopped it, and core/api.py's client
     has none. additionally HTTPClient(idle_timeout=) now bounds a SINGLE
     transport operation even when the total timeout is None, so a stalled
     or slowloris server can no longer pin a connection forever;
     core/api.py opts into a 900s idle timeout (long generations keep
     working, dead sockets die). also fixes L6: an abandoned coroutine is
     closed instead of emitting a RuntimeWarning.
"""
import asyncio
import base64
import ipaddress
import json
import ssl
import sys
import urllib.parse
import zlib

import h11

DEFAULT_USER_AGENT = "OpenLumara/1.0"
READ_CHUNK_SIZE = 65536
MAX_IDLE_CONNS = 6
MAX_IDLE_TOTAL = 32  # audit r3-L7: idle sockets across all pool keys

# audit fix r2-M2: omitting timeout_total used to mean "wait forever"; that
# made every default caller vulnerable to stalled/slowloris servers. new
# callers get this total timeout; an explicit timeout_total=None still means
# infinite (core/api.py relies on that for long generations and model loads).
DEFAULT_TOTAL_TIMEOUT = 60.0

# audit fix r2-M1: cap on the DECOMPRESSED response body. a few hundred KB
# of gzip input can expand into gigabytes and OOM the process; count the
# bytes that actually land in RAM. None disables the cap.
MAX_BODY_SIZE = 32 * 1024 * 1024

# audit fix r4-M1: h11 enforces no resource limits of its own, so the bytes
# fed to it during the response-header phase are counted here. a server
# streaming never-completing header data (or huge 1xx blocks) used to grow
# RAM without bound, stopped only by a total timeout -- which the api client
# deliberately does not have. 128 KiB is generous for legitimate headers.
MAX_HEADER_SIZE = 128 * 1024

# sentinel distinguishing "caller did not pass a timeout" (use the client
# default) from an explicit None (= infinite). None cannot be the sentinel
# because None is a meaningful timeout value here.
_UNSET = object()

# retrying a stale pooled connection is only safe when replaying the request
# cannot duplicate a side effect
IDEMPOTENT_METHODS = ("GET", "HEAD", "OPTIONS", "PUT", "DELETE")

# headers carrying credentials or origin-pinned routing state: these must
# never survive a cross-origin redirect (audit fix #1)
_SENSITIVE_HEADERS = frozenset((
    "authorization",
    "cookie",
    "proxy-authorization",
    "host",
))
# body descriptor headers that must not survive a 301/302/303 method change
# to GET -- the body is dropped, so describing it would desync the request
_BODY_DESCRIPTOR_HEADERS = frozenset(("content-type", "content-length"))


def _pool_key(scheme, host, port, server_address=None):
    """identity of a pooled connection.

    audit fix r2-H1: when the caller pinned a connect address
    (server_address=), the pinned endpoint becomes part of the key. a
    resolved+validated request can therefore never be served an idle socket
    that was established WITHOUT that pin (or with a different one), which
    used to silently defeat the DNS-rebinding defense. requests without a
    pin keep the classic (scheme, host, port) key and never pick up pinned
    sockets either; same host + same pin still reuses keep-alive as before."""
    if server_address is not None:
        connect_host, connect_port = server_address
        return (scheme, host, port, connect_host, connect_port)
    return (scheme, host, port)


def _origin_of(parsed):
    """(scheme, host, port) tuple used to compare redirect origins.

    returns None when the port cannot be parsed; None compares unequal to
    any real origin, so a redirect to an unparseable target always counts
    as cross-origin and credentials get dropped (fail-safe)."""
    scheme = (parsed.scheme or "").lower()
    try:
        port = parsed.port
    except ValueError:
        return None
    if port is None:
        port = 443 if scheme == "https" else 80
    return (scheme, (parsed.hostname or "").lower(), port)


class HTTPError(Exception):
    """base class for every error this client raises (maps to aiohttp.ClientError)"""
    pass

class HTTPConnectionError(HTTPError):
    """connection refused/dropped, or the server spoke nonsense"""
    pass

class HTTPSSLError(HTTPConnectionError):
    """TLS handshake or certificate verification failed"""
    pass

class HTTPTimeout(HTTPError):
    """connect timeout or per-request total timeout exceeded"""
    pass

class HTTPBodyTooLarge(HTTPError):
    """audit fix r2-M1: response body exceeded max_body_size (counted after decompression)"""
    pass

class _StaleConnection(HTTPConnectionError):
    """a pooled connection was closed or corrupted by the server between requests"""
    pass


def _raise_conn_error(exc, pooled=False, got_bytes=False):
    """maps low-level socket/h11 failures onto our exception classes"""
    if pooled and not got_bytes:
        raise _StaleConnection(str(exc)) from exc
    raise HTTPConnectionError(str(exc)) from exc


def _inflate(decompressor, data):
    if decompressor is None:
        return data
    return decompressor.decompress(data)


async def _deadline_await(deadline, coro, idle=None):
    """await a coroutine under an absolute monotonic deadline (None = forever)
    and an optional per-operation idle timeout.

    audit fix r4-M1: with timeout_total=None a stalled server could hold a
    single read forever; idle bounds ONE transport operation, so long-lived
    but ACTIVE streams keep working while dead air times out."""
    timeout = None
    reason = "Request timed out"
    if deadline is not None:
        timeout = deadline - asyncio.get_running_loop().time()
        if timeout <= 0:
            # audit r4-L6: close the abandoned coroutine so asyncio does not
            # emit a "coroutine was never awaited" RuntimeWarning
            coro.close()
            raise HTTPTimeout(reason)
    if idle is not None and (timeout is None or idle < timeout):
        timeout = idle
        reason = f"Connection produced no data for {idle:.0f}s"
    if timeout is None:
        return await coro

    try:
        return await asyncio.wait_for(coro, timeout=timeout)
    except asyncio.TimeoutError:
        raise HTTPTimeout(reason)


class Headers(dict):
    """tiny case-insensitive response header dict; first occurrence of a key wins.
    lookups ignore casing, but the original casing is preserved for display."""

    def __init__(self, pairs=None):
        dict.__init__(self)
        for key, value in pairs or []:
            if not any(k.lower() == key.lower() for k in self):
                dict.__setitem__(self, key, value)

    def __getitem__(self, key):
        try:
            return dict.__getitem__(self, key)
        except KeyError:
            lowered = key.lower()
            for k, v in dict.items(self):
                if k.lower() == lowered:
                    return v
            raise

    def get(self, key, default=None):
        try:
            return self[key]
        except KeyError:
            return default

    def __contains__(self, key):
        if dict.__contains__(self, key):
            return True
        lowered = key.lower()
        return any(k.lower() == lowered for k in dict.keys(self))


def basic_auth(username, password):
    """builds the value of an HTTP Basic auth header"""
    raw = f"{username}:{password}".encode("utf-8")
    return "Basic " + base64.b64encode(raw).decode("ascii")


class Response:
    """
    an aiohttp-ClientResponse-shaped response with a still-open connection.
    consume the body via iter_any()/read()/text(), then it is returned to the
    pool automatically; close() severs the connection for good (also used to
    cancel an in-flight stream). async-with is supported: the body is drained
    and pooled on clean exit, the connection severed on error.
    """

    def __init__(self, client, key, reader, writer, conn, status, reason, headers, deadline, max_body_size=None, idle_timeout=None):
        self.status = status
        self.reason = reason
        self.headers = headers
        self.url = ""  # set by the client to the final request URL
        self.cookies = {}  # no cookie jar: this client is stateless by design

        self._client = client
        self._key = key
        self._reader = reader
        self._writer = writer
        self._conn = conn  # the h11.Connection owning this exchange
        self._deadline = deadline
        # audit fix r4-M1: per-operation idle timeout for body reads, even
        # when the total deadline is None
        self._idle_timeout = idle_timeout
        # audit fix r2-M1: decompressed body byte budget (None = unlimited)
        self._max_body_size = max_body_size
        self._body_bytes = 0

        # transparent gzip/deflate decompression (stdlib zlib, sniffs gzip vs zlib headers)
        self._decompressor = None
        content_encoding = headers.get("content-encoding", "").lower().strip()
        if content_encoding in ("gzip", "x-gzip", "deflate"):
            self._decompressor = zlib.decompressobj(zlib.MAX_WBITS | 32)

        self._finished = False
        self._returned = False
        # audit r3-L4: set once the socket went back to the pool; a late
        # close() (e.g. an abandoned iter_any generator finalized after
        # release()) must not sever a socket that now belongs to the pool
        self._pooled = False
        # audit r3-L3: read() caches the body so read()/text()/json() can be
        # combined (the second call used to return an empty body)
        self._body = None
        # audit r3-H2: raw (on-the-wire) byte count, and decoder state for
        # multi-member gzip / trailing junk after the compressed stream
        self._wire_bytes = 0
        self._members_done = 0
        self._inflate_stopped = False

    def _decode(self, data):
        """audit r3-H2: count + inflate one body chunk, enforcing max_body_size.

        - the raw wire bytes are capped too: after the end of a gzip stream
          zlib parks every further input byte in unused_data, so trailing
          junk used to grow RAM without ever counting toward the cap
        - inflate output is bounded per call (max_length), so one 64 KiB
          chunk can no longer expand into ~64 MiB before the cap is checked
        - multi-member gzip (concatenated members) is decoded completely
          instead of silently truncated after the first member; junk after a
          complete member is ignored (urllib3 behaviour)"""
        cap = self._max_body_size
        self._wire_bytes += len(data)
        if cap is not None and self._wire_bytes > cap:
            raise HTTPBodyTooLarge(f"Response body exceeds the {cap}-byte limit")
        if self._decompressor is None:
            out = data
        else:
            out = b""
            while data and not self._inflate_stopped:
                budget = None if cap is None else cap - self._body_bytes - len(out)
                try:
                    piece = self._decompressor.decompress(data, 0 if budget is None else budget + 1)
                except zlib.error:
                    if self._members_done == 0:
                        raise
                    self._inflate_stopped = True
                    break
                out += piece
                if budget is not None and len(piece) > budget:
                    raise HTTPBodyTooLarge(f"Response body exceeds the {cap}-byte limit")
                if self._decompressor.eof:
                    self._members_done += 1
                    data = self._decompressor.unused_data
                    self._decompressor = zlib.decompressobj(zlib.MAX_WBITS | 32)
                else:
                    data = b""
        self._body_bytes += len(out)
        if cap is not None and self._body_bytes > cap:
            raise HTTPBodyTooLarge(f"Response body exceeds the {cap}-byte limit")
        return out

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        # audit hardening: an async-with caller can never leak an
        # unconsumed connection
        if exc_type is None:
            await self.release()
        else:
            self.close()

    async def iter_any(self):
        """yield the (decompressed) response body as it arrives"""
        if self._finished or self._returned:
            return

        try:
            while True:
                event = self._conn.next_event()

                if type(event) is h11.NEED_DATA:
                    raw = await _deadline_await(self._deadline, self._reader.read(READ_CHUNK_SIZE), idle=self._idle_timeout)
                    # an empty read signals EOF of the transport to h11;
                    # the next next_event() either completes the body (EOF-framed)
                    # or raises RemoteProtocolError (truncated)
                    self._conn.receive_data(raw)
                    continue

                if type(event) is h11.EndOfMessage:
                    break

                if type(event) is h11.PAUSED:
                    # e.g. after a completed protocol switch; no more body events
                    break

                if type(event) is h11.Data:
                    if event.data:
                        # audit fix r2-M1 + r3-H2: count DECOMPRESSED bytes
                        # (what lands in RAM) and raw wire bytes; see _decode
                        chunk = self._decode(bytes(event.data))
                        if chunk:
                            yield chunk
                    continue

                raise HTTPConnectionError(f"Unexpected HTTP event in response body: {event!r}")

        except asyncio.CancelledError:
            self.close()
            raise
        except HTTPError:
            self.close()
            raise
        except (h11.ProtocolError, asyncio.IncompleteReadError, OSError, zlib.error) as e:
            self.close()
            raise HTTPConnectionError(f"Connection error while reading body: {e}")
        except BaseException:
            # audit fix r2-L3: GeneratorExit (a caller that broke out of the
            # async-for) and any other BaseException must sever the socket
            # too -- an abandoned stream used to leak the connection until GC
            self.close()
            raise

        # only reached on a clean, complete read of the body
        self._finished = True
        self._pool_or_close()

    async def read(self):
        """read the whole body as bytes"""
        # audit r3-L3: cached, so text()/json() after read() see the body;
        # (accumulated in a bytearray)
        if self._body is not None:
            return self._body
        data = bytearray()
        async for chunk in self.iter_any():
            data += chunk
        self._body = bytes(data)
        return self._body

    async def text(self):
        data = await self.read()
        encoding = self.charset or "utf-8"
        try:
            return data.decode(encoding, errors="replace")
        except (LookupError, ValueError):
            # audit fix #6 + r2-L2: an unknown or bogus charset label falls
            # back to utf-8. ValueError too, because a hostile charset label
            # can select a valid NON-text codec (base64, hex, zip, quopri),
            # whose decode raises binascii.Error -- a ValueError subclass,
            # not a LookupError
            return data.decode("utf-8", errors="replace")

    async def json(self):
        return json.loads(await self.text())

    @property
    def closed(self):
        """True once the body has been fully consumed or the connection severed"""
        return self._finished or self._returned

    @property
    def charset(self):
        """the charset parameter of the Content-Type header, if any"""
        content_type = self.headers.get("content-type", "")
        for part in content_type.split(";")[1:]:
            key, _, value = part.strip().partition("=")
            if key.strip().lower() == "charset":
                return value.strip().strip('"') or None
        return None

    async def release(self):
        """drain whatever body is left, then pool the connection if possible"""
        if self._finished or self._returned:
            self._pool_or_close()
            return

        try:
            async for _ in self.iter_any():
                pass
        except HTTPError:
            self.close()

    def close(self):
        """sever the connection for good (never returned to the pool)"""
        self._finished = True
        self._returned = True
        if self._pooled:
            # audit r3-L4: the socket was already handed back to the pool
            return
        try:
            self._writer.close()
        except Exception:
            pass

    def _pool_or_close(self):
        if self._returned:
            return
        self._returned = True

        # h11 knows whether this exchange may continue on the same connection.
        # audit r3-M1: after a complete keep-alive exchange h11 reports
        # DONE/DONE (IDLE is only reached via start_next_cycle(), which we
        # never call because every request gets a fresh h11.Connection), so
        # the old IDLE/IDLE test was never true and NOTHING was ever pooled.
        # DONE/DONE also implies keep-alive: "Connection: close" or HTTP/1.0
        # puts the states in MUST_CLOSE instead.
        # trailing_data must be empty too (junk after the body would desync
        # the next request on this socket). audit r3-M1: trailing_data is a
        # PROPERTY in h11; calling it raised TypeError, which the bare except
        # below swallowed -- a second, independent reason nothing was pooled
        poolable = False
        try:
            poolable = (
                self._conn.our_state is h11.DONE
                and self._conn.their_state is h11.DONE
                and not self._conn.trailing_data[0]
            )
        except Exception:
            poolable = False

        if poolable and self._reader.exception() is None:
            self._pooled = True
            self._client._return_conn(self._key, self._reader, self._writer)
        else:
            try:
                self._writer.close()
            except Exception:
                pass


class HTTPClient:
    """
    a tiny keep-alive-pooling HTTP/1.1 client. asyncio-only, not thread-safe.
    one instance == one aiohttp-style ClientSession.
    """

    def __init__(self, ssl_ctx=None, connect_timeout=5.0, user_agent=DEFAULT_USER_AGENT,
                 total_timeout=DEFAULT_TOTAL_TIMEOUT, max_body_size=MAX_BODY_SIZE,
                 idle_timeout=None):
        # ssl_ctx: pass a relaxed context (verify_mode=CERT_NONE) to disable verification,
        # None to use the system default context for https
        # total_timeout: total timeout used for requests that omit timeout_total
        #   (None = this client never times out; core/api.py uses exactly that,
        #   so long generations and model loads are never cut off)
        # max_body_size: decompressed body cap for requests that do not pass
        #   their own (None = unlimited)
        # idle_timeout: audit fix r4-M1: max time a SINGLE transport operation
        #   (one read or drain) may wait, even when the total timeout is None.
        #   bounds stalled/slowloris servers for infinite-timeout clients;
        #   None disables it. core/api.py sets a generous value so long
        #   generations keep working while dead sockets die.
        self._ssl_ctx = ssl_ctx
        self._connect_timeout = connect_timeout
        self._user_agent = user_agent
        self._total_timeout = total_timeout
        self._max_body_size = max_body_size
        self._idle_timeout = idle_timeout
        # pooled sockets are reusable once an exchange completed cleanly;
        # h11 state machines are per-request, so we only pool the streams.
        # (scheme, host, port), or (scheme, host, port, connect_host,
        # connect_port) when the caller pinned an address -- see _pool_key
        self._idle = {}
        self._closed = False

    async def close(self):
        self._closed = True
        for conns in self._idle.values():
            for reader, writer in conns:
                try:
                    writer.close()
                except Exception:
                    pass
        self._idle.clear()

    @property
    def closed(self):
        return self._closed

    async def get(self, url, headers=None, params=None, timeout_total=_UNSET, max_body_size=None):
        return await self.request("GET", url, headers=headers, params=params, timeout_total=timeout_total, max_body_size=max_body_size)

    async def post(self, url, headers=None, json_body=None, body=None, form=None, params=None, timeout_total=_UNSET, max_body_size=None):
        return await self.request("POST", url, headers=headers, json_body=json_body, body=body, form=form, params=params, timeout_total=timeout_total, max_body_size=max_body_size)

    async def request(self, method, url, headers=None, json_body=None, body=None, form=None,
                      params=None, basic_auth=None, timeout_total=_UNSET,
                      allow_redirects=True, max_redirects=5, server_address=None,
                      max_body_size=None):
        if self._closed:
            raise HTTPError("Client is closed")

        # audit fix r2-M2: omitting timeout_total no longer means forever --
        # the client's total_timeout (60s by default) applies. an EXPLICIT
        # None keeps the old infinite behaviour (core/api.py relies on it).
        if timeout_total is _UNSET:
            timeout_total = self._total_timeout
        if max_body_size is None:
            max_body_size = self._max_body_size
        deadline = None if timeout_total is None else asyncio.get_running_loop().time() + timeout_total

        if params:
            # audit fix #3: merge params into the query string properly --
            # never append after a '#' fragment (params can carry API keys)
            parts = urllib.parse.urlsplit(url)
            extra = urllib.parse.urlencode(params)
            query = f"{parts.query}&{extra}" if parts.query else extra
            url = urllib.parse.urlunsplit(
                (parts.scheme, parts.netloc, parts.path, query, parts.fragment)
            )

        # normalize caller headers to a plain mutable dict once, up front:
        # keeps the redirect-time credential stripping simple and guarantees
        # .items() works later
        headers = dict(headers) if headers is not None else None

        # body precedence: explicit raw body > json > form; each implies a default content-type
        default_content_type = None
        if json_body is not None and body is None:
            body = json.dumps(json_body).encode("utf-8")
            default_content_type = "application/json"
        elif form is not None and body is None:
            body = urllib.parse.urlencode(form).encode("utf-8")
            default_content_type = "application/x-www-form-urlencoded"

        if default_content_type is not None:
            headers = dict(headers or {})
            if not any(k.lower() == "content-type" for k in headers):
                headers["Content-Type"] = default_content_type

        origin = _origin_of(urllib.parse.urlsplit(url))

        redirects = 0
        while True:
            resp = await self._request_once(method, url, headers, body, deadline, basic_auth, server_address, max_body_size)
            resp.url = url

            if allow_redirects and resp.status in (301, 302, 303, 307, 308):
                location = resp.headers.get("location")
                if location and redirects < max_redirects:
                    next_url = urllib.parse.urljoin(url, location)
                    next_parsed = urllib.parse.urlsplit(next_url)
                    cur_parsed = urllib.parse.urlsplit(url)

                    # audit r3-H1: a pinned address (server_address=) belongs
                    # to the validated host only. the old code dropped the pin
                    # and kept following, i.e. the hop was resolved by plain,
                    # UNVALIDATED DNS -- an SSRF / DNS-rebinding bypass for any
                    # caller that pins but leaves allow_redirects=True (the
                    # default). same-origin hops keep the pin; anything else is
                    # handed back to the caller (as an unfollowed 3xx) so it
                    # can re-validate the new target, like http_module does.
                    if (server_address is not None
                            and _origin_of(next_parsed) != _origin_of(cur_parsed)):
                        return resp

                    # audit r3-L1: never auto-follow an https -> http
                    # downgrade (a 307/308 would replay the body, and any
                    # same-host state, over plaintext); hand the 3xx back
                    if ((cur_parsed.scheme or "").lower() == "https"
                            and (next_parsed.scheme or "").lower() == "http"):
                        return resp

                    resp.close()
                    redirects += 1
                    url = next_url

                    if _origin_of(urllib.parse.urlsplit(url)) != origin:
                        # audit fix #1: cross-origin hop -> drop credentials
                        # from EVERY source: the basic_auth parameter, and
                        # any caller-supplied Authorization / Cookie /
                        # Proxy-Authorization / Host headers. an unparseable
                        # redirect target counts as cross-origin too (the
                        # _origin_of None fail-safe), and the follow-up
                        # request will then fail on the invalid port.
                        basic_auth = None
                        headers = {
                            k: v for k, v in (headers or {}).items()
                            if k.lower() not in _SENSITIVE_HEADERS
                        }

                    # audit r3-L2: fetch-spec method rewriting -- 303 turns
                    # anything but HEAD into GET; 301/302 only rewrite POST.
                    # the old code also turned HEAD (and PUT/DELETE on
                    # 301/302) into a GET, downloading bodies HEAD avoids
                    upper = method.upper()
                    if ((resp.status == 303 and upper != "HEAD")
                            or (resp.status in (301, 302) and upper == "POST")):
                        # browser-style: these become a bodyless GET; stale
                        # body descriptor headers must not survive either
                        method = "GET"
                        body = None
                        headers = {
                            k: v for k, v in (headers or {}).items()
                            if k.lower() not in _BODY_DESCRIPTOR_HEADERS
                        }
                    continue

            return resp

    # ---------------------------
    # internals
    # ---------------------------
    async def _request_once(self, method, url, headers, body, deadline, basic_auth=None, server_address=None, max_body_size=None):
        parsed = urllib.parse.urlsplit(url)
        scheme = (parsed.scheme or "https").lower()
        if scheme not in ("http", "https"):
            raise HTTPError(f"Unsupported URL scheme: {scheme}")

        host = parsed.hostname
        if not host:
            raise HTTPError(f"URL has no host: {url}")

        # audit fix #5: a non-numeric port raises ValueError from
        # urlsplit().port -- keep the "everything is HTTPError" contract
        try:
            port = parsed.port
        except ValueError:
            raise HTTPError(f"Invalid port in URL: {url}") from None
        if port is None:
            port = 443 if scheme == "https" else 80

        path = parsed.path or "/"
        if parsed.query:
            path += "?" + parsed.query
        # audit r3-L5: percent-encode anything h11 would reject in a request
        # target (spaces, non-ASCII, control bytes); printable ASCII is left
        # untouched so existing escapes and reserved characters survive
        path = "".join(
            c if "\x21" <= c <= "\x7e" else urllib.parse.quote(c, safe="")
            for c in path
        )

        # audit fix r2-H1: the pool identity includes the pinned endpoint
        # when there is one -- see _pool_key
        key = _pool_key(scheme, host, port, server_address)

        # try a pooled connection first; if it died or went stale while idle, retry once on a fresh one
        for attempt in range(2):
            writer = None
            # audit r3-L6: the retry must use a FRESH connection, as the
            # comment above promises; popping another idle socket (likely
            # just as stale, e.g. after a server restart) failed the request
            pooled = self._take_conn(key) if attempt == 0 else None
            try:
                if pooled is not None:
                    reader, writer = pooled
                else:
                    reader, writer = await self._connect(scheme, host, port, deadline, server_address)

                return await self._exchange(
                    reader, writer, scheme, method, path, host, port,
                    headers, body, deadline, pooled is not None, basic_auth,
                    max_body_size, key,
                )

            except HTTPError as e:
                if writer is not None:
                    try:
                        writer.close()
                    except Exception:
                        pass
                if (attempt == 0 and pooled is not None
                        and isinstance(e, _StaleConnection)
                        and method.upper() in IDEMPOTENT_METHODS):
                    continue
                raise
            except BaseException:
                # audit hardening: includes asyncio.CancelledError --
                # never leak the socket when a request is cancelled mid-flight
                if writer is not None:
                    try:
                        writer.close()
                    except Exception:
                        pass
                raise

    async def _connect(self, scheme, host, port, deadline, server_address=None):
        ctx = None
        if scheme == "https":
            ctx = self._ssl_ctx if self._ssl_ctx is not None else ssl.create_default_context()

        timeout = self._connect_timeout
        if deadline is not None:
            timeout = min(timeout, max(0.1, deadline - asyncio.get_running_loop().time()))

        # DNS-rebinding hardening: server_address lets a caller that already
        # resolved+validated the hostname pin the exact IP to connect to.
        # for https the TLS handshake still uses the original hostname for
        # SNI and certificate verification (the cert is checked against the
        # hostname, never against the pinned IP).
        # note on pooling (audit fix r2-H1): the pool key now includes the
        # pinned endpoint, so a pin can only ever be served by a connection
        # that was established with that exact pin. a different pin -- or no
        # pin at all -- gets its own separate pool (i.e. a fresh, freshly
        # validated connection) instead of hijacking this socket.
        if server_address is not None:
            connect_host, connect_port = server_address
        else:
            connect_host, connect_port = host, port

        # SNI must not carry an IP literal (RFC 6066): for real hostnames we
        # pin server_hostname explicitly (cert is verified against the
        # hostname, never the pinned IP).
        # audit fix r2-L1: the old code simply omitted server_hostname for
        # IP-literal hosts, which made asyncio raise a bare
        # ValueError("check_hostname requires server_hostname") on Python
        # < 3.13, bypassing the "everything is HTTPError" contract. now:
        #   - verification on + Python >= 3.13: pass the IP as
        #     server_hostname; ssl checks it against IP SAN entries and
        #     sends no SNI for IP addresses
        #   - verification on + older Python: raise a clear HTTPError
        #   - verification off (caller's explicit choice): send no hostname
        #     at all -- nothing is verified anyway and no SNI goes out
        connect_kwargs = {"ssl": ctx}
        if scheme == "https":
            try:
                ipaddress.ip_address(host)
                ip_literal = True
            except ValueError:
                ip_literal = False
            if not ip_literal:
                connect_kwargs["server_hostname"] = host
            elif ctx.check_hostname:
                if sys.version_info < (3, 13):
                    raise HTTPError(
                        f"Cannot verify the TLS certificate of IP-literal host {host}: "
                        "IP SAN verification requires Python 3.13+; connect to the "
                        "hostname instead, or use an ssl_ctx with check_hostname=False"
                    )
                connect_kwargs["server_hostname"] = host

        try:
            return await asyncio.wait_for(
                asyncio.open_connection(connect_host, connect_port, **connect_kwargs),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            raise HTTPTimeout(f"Timed out connecting to {host}:{port}")
        except ssl.SSLError as e:
            raise HTTPSSLError(f"TLS error connecting to {host}:{port}: {e}")
        except (ConnectionError, OSError) as e:
            raise HTTPConnectionError(f"Could not connect to {host}:{port}: {e}")
        except ValueError as e:
            # audit fix r2-L1: keep the "everything is HTTPError" contract
            # even if the event loop rejects the connect arguments outright
            # (e.g. check_hostname without a server_hostname on old Pythons)
            raise HTTPError(f"Cannot connect to {host}:{port}: {e}") from e

    async def _exchange(self, reader, writer, scheme, method, path, host, port, headers, body, deadline, pooled, basic_auth=None, max_body_size=None, key=None):
        # ---- build request headers ----
        if ":" in host:
            host_header = f"[{host}]"
        elif host.isascii():
            host_header = host
        else:
            # audit r3-L5: an IDN host goes on the wire as its IDNA (punycode)
            # form -- it used to be latin-1 encoded raw (or rejected)
            try:
                host_header = host.encode("idna").decode("ascii")
            except UnicodeError:
                raise HTTPError(f"Invalid host: {host!r}") from None
        if not ((scheme == "https" and port == 443) or (scheme == "http" and port == 80)):
            host_header += f":{port}"

        send_headers = {
            "Host": host_header,
            "User-Agent": self._user_agent,
            "Accept": "*/*",
            "Accept-Encoding": "identity",  # we decompress gzip/deflate ourselves; ask for raw by default
            "Connection": "keep-alive",
        }

        def _set_header(name, value):
            # audit r3-M3: header names are case-insensitive. the old plain
            # dict merge kept BOTH "User-Agent" and "user-agent" (two
            # Accept-Encoding / Authorization values on the wire), and a
            # lowercase "host" made h11 reject every request
            lowered = name.lower()
            for existing in [k for k in send_headers if k.lower() == lowered]:
                del send_headers[existing]
            send_headers[name] = value

        # audit r3-M2: this loop variable used to be called "key", shadowing
        # the pool-key PARAMETER -- every request with caller headers handed
        # its socket back under the last header NAME (e.g. "Accept-Encoding")
        # instead of the (scheme, host, port[, pin]) key, so r2-H1 was never
        # actually in effect once pooling works
        for name, value in (headers or {}).items():
            name = str(name)
            # audit r3-M3: body framing is ours alone -- a caller
            # Content-Length / Transfer-Encoding produced CL+TE (smuggling-
            # shaped) requests or a declared body that never comes
            if name.lower() in ("content-length", "transfer-encoding"):
                continue
            _set_header(name, str(value))  # caller headers win

        if basic_auth:
            _set_header("Authorization", basic_auth)

        if body is not None:
            send_headers["Content-Length"] = str(len(body))

        # ---- serialize the request with h11 ----
        conn = h11.Connection(our_role=h11.CLIENT)
        try:
            header_pairs = [
                (name.encode("latin-1"), str(value).encode("latin-1"))
                for name, value in send_headers.items()
            ]
            payload = conn.send(h11.Request(method=method, target=path, headers=header_pairs))
            if body is not None:
                payload += conn.send(h11.Data(data=body))
            # audit fix #7 companion: always finish the request framing, even
            # bodyless ones. h11 needs EndOfMessage to move our_state to
            # DONE (and then both sides to IDLE), which is exactly what the
            # keep-alive pooling check in Response._pool_or_close looks at.
            # for bodyless requests this emits no extra bytes on the wire.
            payload += conn.send(h11.EndOfMessage())
        except (h11.LocalProtocolError, ValueError, UnicodeEncodeError) as e:
            # audit fix #4: these are deterministic local validation
            # failures (bad method/target/header bytes) -- the pooled
            # connection is innocent, so this is never a stale connection
            # and must never be retried on a fresh socket
            raise HTTPError(f"Invalid request: {e}") from e

        try:
            writer.write(payload)
            await _deadline_await(deadline, writer.drain(), idle=self._idle_timeout)
        except HTTPTimeout:
            raise
        except (ConnectionError, OSError) as e:
            _raise_conn_error(e, pooled=pooled, got_bytes=False)

        # ---- wait for the real response headers (h11 surfaces 1xx separately) ----
        got_bytes = False
        interim_1xx = 0
        header_bytes = 0  # audit fix r4-M1
        while True:
            try:
                event = conn.next_event()
            except h11.ProtocolError as e:
                _raise_conn_error(e, pooled=pooled, got_bytes=got_bytes)

            if type(event) is h11.NEED_DATA:
                # audit fix r4-M1: h11 buffers without limits by design, so a
                # server streaming never-completing header bytes (or huge 1xx
                # blocks) grew RAM here with only the total timeout as a brake
                # -- and core/api.py's client deliberately has none. abort
                # before feeding the parser anything past the budget; the
                # check only fires while h11 still NEED_DATA, so a response
                # whose headers complete just past the boundary still
                # surfaces normally. a plain HTTPConnectionError, not a
                # _StaleConnection: a hostile server does not get retried
                if header_bytes > MAX_HEADER_SIZE:
                    raise HTTPConnectionError(
                        f"Response headers exceed the {MAX_HEADER_SIZE}-byte limit"
                    )
                try:
                    raw = await _deadline_await(deadline, reader.read(READ_CHUNK_SIZE), idle=self._idle_timeout)
                except HTTPTimeout:
                    raise
                except (ConnectionError, OSError) as e:
                    _raise_conn_error(e, pooled=pooled, got_bytes=got_bytes)

                conn.receive_data(raw)  # empty read = EOF: h11 decides if that's valid
                header_bytes += len(raw)
                got_bytes = got_bytes or bool(raw)
                continue

            if isinstance(event, h11.InformationalResponse):
                # interim 1xx response, keep waiting for the final one.
                # audit fix r2-M2: cap the count -- a server trickling 1xx
                # forever would stall an infinite-timeout caller (core/api.py)
                interim_1xx += 1
                if interim_1xx > 10:
                    _raise_conn_error(
                        HTTPConnectionError("Server sent too many 1xx interim responses"),
                        pooled=pooled, got_bytes=got_bytes,
                    )
                continue

            if isinstance(event, h11.Response):
                break

            _raise_conn_error(
                HTTPConnectionError(f"Unexpected event before response headers: {event!r}"),
                pooled=pooled, got_bytes=got_bytes,
            )

        pairs = [
            (name.decode("latin-1", errors="replace"), value.decode("latin-1", errors="replace"))
            for name, value in event.headers
        ]

        return Response(
            client=self,
            # audit fix r2-H1: the pool key is decided once in _request_once
            # (it may include the pinned endpoint) and threaded through here,
            # so the Response returns the socket to exactly the pool it came from
            key=key if key is not None else (scheme, host, port),
            reader=reader,
            writer=writer,
            conn=conn,
            status=event.status_code,
            reason=(event.reason or b"").decode("latin-1", errors="replace"),
            headers=Headers(pairs),
            deadline=deadline,
            idle_timeout=self._idle_timeout,
            max_body_size=max_body_size,
        )

    def _take_conn(self, key):
        conns = self._idle.get(key)
        while conns:
            reader, writer = conns.pop()
            if (self._closed or reader.exception() is not None or reader.at_eof()
                    or writer.is_closing()):
                try:
                    writer.close()
                except Exception:
                    pass
                continue
            if not conns:
                self._idle.pop(key, None)
            return reader, writer
        # audit r3-L7: drop empty per-key lists (one per host/pin otherwise)
        self._idle.pop(key, None)
        return None

    def _return_conn(self, key, reader, writer):
        if self._closed:
            # audit fix #2: the original had the return inside the except
            # block, so a successful writer.close() fell through and pooled
            # a dead socket after the client was closed
            try:
                writer.close()
            except Exception:
                pass
            return
        # audit r3-L7: also cap idle sockets across ALL keys -- every
        # distinct host (and every distinct pin) had its own 6-socket budget,
        # so an agent fetching many hostile hosts could hoard file descriptors
        while sum(len(c) for c in self._idle.values()) >= MAX_IDLE_TOTAL:
            oldest_key = next(iter(self._idle))
            _, old_writer = self._idle[oldest_key].pop(0)
            if not self._idle[oldest_key]:
                del self._idle[oldest_key]
            try:
                old_writer.close()
            except Exception:
                pass
        conns = self._idle.setdefault(key, [])
        while len(conns) >= MAX_IDLE_CONNS:
            _, old_writer = conns.pop(0)
            try:
                old_writer.close()
            except Exception:
                pass
        conns.append((reader, writer))
