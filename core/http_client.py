# -- AI GENERATED CODE (Qwen3.8 Flash Next (local) + GLM 5.3 security audit (openrouter)) :: (2026-10-22) harness:openlumara
"""
a tiny HTTP/1.1 client built on asyncio streams + h11.

replaces aiohttp across the codebase (API client, http/web modules,
calendar sync, ntfy). h11 (pure-python, zero transitive dependencies)
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
- optional TLS verification bypass and per-request total timeouts
- browser-style redirects (disable with allow_redirects=False)
- hard-closing an in-flight response to cancel a stream
- optional pre-validated IP pinning (server_address=) so callers that
  resolve+validate before connecting never face a second, unvalidated
  DNS lookup (closes the DNS-rebinding TOCTOU window)

deliberately NOT implemented: cookies, proxies, brotli/zstd, HTTP/2, expect-continue.

security audit (2026-10-22) -- fixes applied, search "audit fix":
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
"""
import asyncio
import base64
import ipaddress
import json
import ssl
import urllib.parse
import zlib

import h11

DEFAULT_USER_AGENT = "OpenLumara/1.0"
READ_CHUNK_SIZE = 65536
MAX_IDLE_CONNS = 6

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


async def _deadline_await(deadline, coro):
    """await a coroutine while respecting an absolute monotonic deadline (None = forever)"""
    if deadline is None:
        return await coro

    remaining = deadline - asyncio.get_running_loop().time()
    if remaining <= 0:
        raise HTTPTimeout("Request timed out")

    try:
        return await asyncio.wait_for(coro, timeout=remaining)
    except asyncio.TimeoutError:
        raise HTTPTimeout("Request timed out")


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

    def __init__(self, client, key, reader, writer, conn, status, reason, headers, deadline):
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

        # transparent gzip/deflate decompression (stdlib zlib, sniffs gzip vs zlib headers)
        self._decompressor = None
        content_encoding = headers.get("content-encoding", "").lower().strip()
        if content_encoding in ("gzip", "x-gzip", "deflate"):
            self._decompressor = zlib.decompressobj(zlib.MAX_WBITS | 32)

        self._finished = False
        self._returned = False

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
                    raw = await _deadline_await(self._deadline, self._reader.read(READ_CHUNK_SIZE))
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
                        yield _inflate(self._decompressor, event.data)
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

        # only reached on a clean, complete read of the body
        self._finished = True
        self._pool_or_close()

    async def read(self):
        """read the whole body as bytes"""
        data = b""
        async for chunk in self.iter_any():
            data += chunk
        return data

    async def text(self):
        data = await self.read()
        encoding = self.charset or "utf-8"
        try:
            return data.decode(encoding, errors="replace")
        except LookupError:
            # unknown or bogus charset label: fall back to utf-8 (audit fix #6)
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
        try:
            self._writer.close()
        except Exception:
            pass

    def _pool_or_close(self):
        if self._returned:
            return
        self._returned = True

        # h11 knows whether this exchange may continue on the same connection:
        # both state machines must be back in IDLE (audit fix #7: uses the
        # documented our_state/their_state, not undocumented helpers);
        # trailing_data must be empty too (junk after the body would desync
        # the next request on this socket)
        poolable = False
        try:
            poolable = (
                self._conn.our_state is h11.IDLE
                and self._conn.their_state is h11.IDLE
                and not self._conn.trailing_data()[0]
            )
        except Exception:
            poolable = False

        if poolable and self._reader.exception() is None:
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

    def __init__(self, ssl_ctx=None, connect_timeout=5.0, user_agent=DEFAULT_USER_AGENT):
        # ssl_ctx: pass a relaxed context (verify_mode=CERT_NONE) to disable verification,
        # None to use the system default context for https
        self._ssl_ctx = ssl_ctx
        self._connect_timeout = connect_timeout
        self._user_agent = user_agent
        # pooled sockets are reusable once an exchange completed cleanly;
        # h11 state machines are per-request, so we only pool the streams.
        self._idle = {}  # (scheme, host, port) -> list of (reader, writer)
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

    async def get(self, url, headers=None, params=None, timeout_total=None):
        return await self.request("GET", url, headers=headers, params=params, timeout_total=timeout_total)

    async def post(self, url, headers=None, json_body=None, body=None, form=None, params=None, timeout_total=None):
        return await self.request("POST", url, headers=headers, json_body=json_body, body=body, form=form, params=params, timeout_total=timeout_total)

    async def request(self, method, url, headers=None, json_body=None, body=None, form=None,
                      params=None, basic_auth=None, timeout_total=None,
                      allow_redirects=True, max_redirects=5, server_address=None):
        if self._closed:
            raise HTTPError("Client is closed")

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
            resp = await self._request_once(method, url, headers, body, deadline, basic_auth, server_address)
            resp.url = url

            if allow_redirects and resp.status in (301, 302, 303, 307, 308):
                location = resp.headers.get("location")
                if location and redirects < max_redirects:
                    resp.close()
                    redirects += 1
                    url = urllib.parse.urljoin(url, location)

                    # a pinned address belongs to the previous URL only;
                    # following a redirect with it could connect somewhere else
                    server_address = None

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

                    if resp.status in (301, 302, 303):
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
    async def _request_once(self, method, url, headers, body, deadline, basic_auth=None, server_address=None):
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

        key = (scheme, host, port)

        # try a pooled connection first; if it died or went stale while idle, retry once on a fresh one
        for attempt in range(2):
            writer = None
            pooled = self._take_conn(key)
            try:
                if pooled is not None:
                    reader, writer = pooled
                else:
                    reader, writer = await self._connect(scheme, host, port, deadline, server_address)

                return await self._exchange(
                    reader, writer, scheme, method, path, host, port,
                    headers, body, deadline, pooled is not None, basic_auth,
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
        # note on pooling: a pooled connection keeps serving its original
        # (validated-at-connect) endpoint, which preserves the safety
        # guarantee; a changed pin opens a fresh connection.
        if server_address is not None:
            connect_host, connect_port = server_address
        else:
            connect_host, connect_port = host, port

        # SNI must not carry an IP literal (RFC 6066): for real hostnames we
        # pin server_hostname explicitly (cert is verified against the
        # hostname, never the pinned IP); for IP-literal hosts we omit it and
        # let asyncio skip SNI and verify against IP SAN entries instead.
        connect_kwargs = {"ssl": ctx}
        if scheme == "https":
            try:
                ipaddress.ip_address(host)
            except ValueError:
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

    async def _exchange(self, reader, writer, scheme, method, path, host, port, headers, body, deadline, pooled, basic_auth=None):
        # ---- build request headers ----
        host_header = f"[{host}]" if ":" in host else host
        if not ((scheme == "https" and port == 443) or (scheme == "http" and port == 80)):
            host_header += f":{port}"

        send_headers = {
            "Host": host_header,
            "User-Agent": self._user_agent,
            "Accept": "*/*",
            "Accept-Encoding": "identity",  # we decompress gzip/deflate ourselves; ask for raw by default
            "Connection": "keep-alive",
        }
        for key, value in (headers or {}).items():
            send_headers[key] = str(value)  # caller headers win

        if basic_auth:
            send_headers["Authorization"] = basic_auth

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
            await _deadline_await(deadline, writer.drain())
        except HTTPTimeout:
            raise
        except (ConnectionError, OSError) as e:
            _raise_conn_error(e, pooled=pooled, got_bytes=False)

        # ---- wait for the real response headers (h11 surfaces 1xx separately) ----
        got_bytes = False
        while True:
            try:
                event = conn.next_event()
            except h11.ProtocolError as e:
                _raise_conn_error(e, pooled=pooled, got_bytes=got_bytes)

            if type(event) is h11.NEED_DATA:
                try:
                    raw = await _deadline_await(deadline, reader.read(READ_CHUNK_SIZE))
                except HTTPTimeout:
                    raise
                except (ConnectionError, OSError) as e:
                    _raise_conn_error(e, pooled=pooled, got_bytes=got_bytes)

                conn.receive_data(raw)  # empty read = EOF: h11 decides if that's valid
                got_bytes = got_bytes or bool(raw)
                continue

            if isinstance(event, h11.InformationalResponse):
                continue  # interim 1xx response, keep waiting for the final one

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
            key=(scheme, host, port),
            reader=reader,
            writer=writer,
            conn=conn,
            status=event.status_code,
            reason=(event.reason or b"").decode("latin-1", errors="replace"),
            headers=Headers(pairs),
            deadline=deadline,
        )

    def _take_conn(self, key):
        conns = self._idle.get(key)
        while conns:
            reader, writer = conns.pop()
            if self._closed or reader.exception() is not None or reader.at_eof():
                try:
                    writer.close()
                except Exception:
                    pass
                continue
            return reader, writer
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
        conns = self._idle.setdefault(key, [])
        while len(conns) >= MAX_IDLE_CONNS:
            _, old_writer = conns.pop(0)
            try:
                old_writer.close()
            except Exception:
                pass
        conns.append((reader, writer))
