"""OpenAI-compatible endpoints over HTTP, and the journal and request runner that `run` and `judge` share.

Only the standard library: urllib for HTTP, threads for concurrent requests.

The API key is read from the environment variable the user names and sent as a bearer token. It is
never written to a file or printed, and it is masked in every error message. Redirects are not followed,
so the key goes only to the URL given. Records name the endpoint without credentials, port, path or
query: "local endpoint" for a loopback address, "private endpoint" for a private address or an
internal host name, and scheme and host for a public host; `record=True` keeps scheme, host and port.
Error bodies are never read: an HTTP error is kept as its status code and standard phrase, and a
connection error as a short classified reason.

Failures are sorted by what they say about the item:

- the reply is a property of the item (an empty or truncated output, a timeout, an HTTP 4xx such as
  a context overflow): the item gets a final status and is journaled;
- the endpoint is not usable (connection refused after retries, HTTP 401, 403 or 404, a rate limit
  that outlasts the retries): the run stops, the item is not journaled, and running the same command
  again resumes;
- transient errors (connection errors, HTTP 408, 429, 500, 502, 503, 504) are retried with
  exponential backoff, honouring Retry-After up to a minute; HTTP 408, 500, 502, 503 or 504 after the
  last retry is a final error of the item.
"""

import http
import http.client
import ipaddress
import json
import os
import queue
import socket
import ssl
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

RETRYABLE = {408, 429, 500, 502, 503, 504}
CONFIGURATION = {401: "the API key was rejected", 403: "access was refused", 404: "the URL or model was not found"}
PATHS = {"chat": "/chat/completions", "completions": "/completions"}
LOOPBACK = {"localhost", "127.0.0.1", "::1"}
# Host names that name a machine on a private network rather than a public service.
INTERNAL_SUFFIXES = (".local", ".localdomain", ".localhost", ".lan", ".home", ".home.arpa", ".internal", ".intranet",
                     ".corp", ".private", ".test", ".invalid", ".ts.net")


class Stop(RuntimeError):
    """The endpoint cannot be used now; nothing was journaled for the item in hand."""


class Failure(Exception):
    """A final, journaled failure of one item: status is "error" or "timeout"."""

    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def resolve(base_url, kind="chat"):
    """The request URL for an OpenAI base URL such as http://127.0.0.1:8080/v1.

    A URL that already ends in /chat/completions or /completions is used as given; a URL with no path
    gets /v1 first."""
    parts = urllib.parse.urlsplit(base_url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise ValueError(f"--base-url must be an http:// or https:// URL, got {public_url(base_url)!r}")
    path = parts.path.rstrip("/")
    if not path.endswith(tuple(PATHS.values())):
        path = (path or "/v1") + PATHS[kind]
    return urllib.parse.urlunsplit((parts.scheme, parts.netloc, path, parts.query, ""))


def public_url(url):
    """Scheme, host, port and path only: no user, password, query string or fragment."""
    parts = urllib.parse.urlsplit(url)
    host = parts.hostname or ""
    if ":" in host:
        host = f"[{host}]"
    try:
        port = parts.port
    except ValueError:
        port = None
    netloc = host + (f":{port}" if port else "")
    return urllib.parse.urlunsplit((parts.scheme, netloc, parts.path, "", ""))


def host_kind(host):
    """"local" (loopback), "private" (private address or internal host name) or "public"."""
    host = (host or "").strip("[]").lower().rstrip(".")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        if host == "localhost" or host.endswith(".localhost"):
            return "local"
        if "." not in host or host.endswith(INTERNAL_SUFFIXES):
            return "private"
        return "public"
    if address.is_loopback:
        return "local"
    return "public" if address.is_global else "private"


def recorded(url, record=False):
    """How a run's records name the endpoint (see the module docstring)."""
    parts = urllib.parse.urlsplit(url)
    host = parts.hostname or ""
    shown = f"[{host}]" if ":" in host else host
    if record:
        try:
            port = parts.port
        except ValueError:
            port = None
        return f"{parts.scheme}://{shown}" + (f":{port}" if port else "")
    kind = host_kind(host)
    return {"local": "local endpoint", "private": "private endpoint"}.get(kind, f"{parts.scheme}://{shown}")


def http_reason(code):
    try:
        return f"HTTP {code} {http.HTTPStatus(code).phrase}"
    except ValueError:
        return f"HTTP {code}"


def connection_reason(exc):
    """A short reason for a failed connection, without addresses, certificates or server text."""
    reason = getattr(exc, "reason", exc)
    if isinstance(reason, ConnectionRefusedError):
        return "connection refused"
    if isinstance(reason, socket.gaierror):
        return "host name not resolved"
    if isinstance(reason, ssl.SSLError):
        return "TLS error"
    if isinstance(reason, (TimeoutError, socket.timeout)):
        return "connection timed out"
    if isinstance(reason, (ConnectionResetError, http.client.RemoteDisconnected)):
        return "connection closed by the server"
    if isinstance(reason, http.client.HTTPException):
        return "malformed HTTP reply"
    return f"connection failed ({type(reason).__name__})"


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Every redirect becomes an HTTPError with its 3xx code, so the Authorization header never travels."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def read_key(variable):
    """The API key from the named environment variable, or None when no variable is named."""
    if not variable:
        return None
    key = os.environ.get(variable, "").strip()
    if not key:
        raise ValueError(f"--api-key-env {variable}: the environment variable is not set or empty")
    return key


class Endpoint:
    """One OpenAI-compatible endpoint: POST a JSON body, get the reply's JSON, with retries."""

    def __init__(self, base_url, kind="chat", api_key_env=None, timeout=120, retries=3, backoff=1.0, record=False):
        self.url = resolve(base_url, kind)
        self.public = public_url(self.url)  # shown on the terminal only
        self.identity = self.public  # what journal bindings hash; never written as text
        self.recorded = recorded(self.url, record)  # what records and messages that reach files say
        self._key = read_key(api_key_env)
        self.timeout, self.retries, self.backoff = timeout, retries, backoff
        handlers = [_NoRedirect()]
        if urllib.parse.urlsplit(self.url).hostname in LOOPBACK:
            handlers.append(urllib.request.ProxyHandler({}))  # a local server is never reached through a proxy
        self._opener = urllib.request.build_opener(*handlers)

    @property
    def authenticated(self):
        return self._key is not None

    def mask(self, text):
        text = str(text)
        return text.replace(self._key, "[api key]") if self._key else text

    def _send(self, body):
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self._key:
            headers["Authorization"] = f"Bearer {self._key}"
        request = urllib.request.Request(self.url, data=json.dumps(body).encode("utf-8"), headers=headers,
                                         method="POST")
        with self._opener.open(request, timeout=self.timeout) as response:
            raw = response.read()
        try:
            return json.loads(raw)
        except ValueError:
            raise Failure("error", "the reply is not JSON") from None

    def post(self, body):
        """(reply, attempts, seconds of the last attempt). Raises Failure (final, with .attempts and .seconds)
        or Stop (the endpoint is not usable)."""
        attempt = 0
        while True:
            attempt += 1
            started = time.monotonic()
            try:
                return self._attempt(body, attempt), attempt, time.monotonic() - started
            except Failure as exc:
                exc.attempts, exc.seconds = attempt, round(time.monotonic() - started, 3)
                raise
            except _Retry as exc:
                if attempt > self.retries:
                    raise Stop(f"{self.recorded} stopped answering ({exc}) after {attempt} attempts") from None
                time.sleep(min(exc.wait if exc.wait is not None else self.backoff * 2 ** (attempt - 1), 60))

    def _attempt(self, body, attempt):
        try:
            return self._send(body)
        except urllib.error.HTTPError as exc:
            # The body is not read: it can echo the request, internal addresses or other server detail.
            reason = http_reason(exc.code)
            wait = _retry_after(exc)
            exc.close()
            if 300 <= exc.code < 400:
                raise Stop(f"{self.recorded} answered {reason}, a redirect; redirects are not followed, so the API "
                           "key goes only to --base-url; give the final URL as --base-url") from None
            if exc.code in CONFIGURATION:
                raise Stop(f"{reason} from {self.recorded}: {CONFIGURATION[exc.code]}; check --base-url, --model "
                           "and --api-key-env") from None
            if exc.code not in RETRYABLE:
                raise Failure("error", reason) from None
            if attempt > self.retries:
                if exc.code == 429:
                    raise Stop(f"{self.recorded} keeps answering {reason} (rate limit or quota)") from None
                raise Failure("error", reason) from None
            raise _Retry(reason, wait) from None
        except (TimeoutError, socket.timeout):
            # The connection was made and the request sent; the reply did not come in time.
            raise Failure("timeout", f"no reply within {self.timeout:g} s") from None
        except urllib.error.URLError as exc:
            # Raised before the request was sent: refused, unreachable or a connect timeout.
            raise _Retry(connection_reason(exc), None) from None
        except (ConnectionError, http.client.HTTPException) as exc:
            raise _Retry(connection_reason(exc), None) from None


class _Retry(Exception):
    def __init__(self, message, wait):
        super().__init__(message)
        self.wait = wait


def _retry_after(exc):
    value = exc.headers.get("Retry-After") if exc.headers else None
    try:
        return max(0.0, float(value)) if value is not None else None
    except ValueError:
        return None


# Journal: one JSON line per finished unit of work, appended in one write ---------------------------------------

class Journal:
    """An append-only JSONL file. A last line without its newline is an interrupted write and is cut."""

    def __init__(self, path):
        self.path = Path(path)

    def read(self):
        if not self.path.exists():
            return []
        data = self.path.read_bytes()
        keep = data.rfind(b"\n") + 1
        if keep < len(data):
            with self.path.open("r+b") as stream:
                stream.truncate(keep)
            data = data[:keep]
        rows = []
        for number, line in enumerate(data.decode("utf-8-sig").splitlines(), 1):
            if line.strip():
                try:
                    rows.append(json.loads(line))
                except ValueError:
                    raise ValueError(f"{self.path}: line {number} is not valid JSON") from None
        return rows

    def append(self, record):
        line = (json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")
        with self.path.open("ab") as stream:
            stream.write(line)
            stream.flush()
            os.fsync(stream.fileno())


@contextmanager
def locked(directory, name):
    """An exclusive lock on DIRECTORY/NAME for the whole run, so two runs never write the same journal."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    stream = path.open("a+")
    try:
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        stream.close()  # the lock file belongs to the run that holds it
        raise RuntimeError(f"Another run is using {directory}; nothing was sent") from None
    try:
        yield
    finally:
        path.unlink(missing_ok=True)
        stream.close()


# Runner ----------------------------------------------------------------------------------------------------------

def run_all(tasks, work, commit, concurrency=1, log=print):
    """Call work(task) on `concurrency` threads and commit(task, result) in the calling thread as each finishes.

    Only the calling thread writes, so a journal is never written concurrently. A task is taken only when a
    thread is free, so a stop leaves nothing queued. On the first Ctrl-C no new task is taken and the tasks
    in flight are awaited and committed; a second Ctrl-C leaves them. A Stop raised by work halts the run the
    same way. Returns dict(stop=reason or None, interrupted=bool, abandoned=number of tasks left in flight).
    """
    todo = queue.SimpleQueue()
    for task in tasks:
        todo.put(task)
    finished = queue.SimpleQueue()
    halt = threading.Event()
    state = dict(stop=None, interrupted=False, abandoned=0, error=None)
    busy = [0]
    guard = threading.Lock()

    def worker():
        while not halt.is_set():
            with guard:
                try:
                    task = todo.get_nowait()
                except queue.Empty:
                    return
                busy[0] += 1
            try:
                finished.put((task, work(task), None))
            except BaseException as exc:  # handed to the calling thread
                halt.set()
                finished.put((task, None, exc))

    threads = [threading.Thread(target=worker, daemon=True) for _ in range(max(1, concurrency))]
    for thread in threads:
        thread.start()
    pressed = 0
    while True:
        try:
            try:
                task, result, exc = finished.get(timeout=0.2)
            except queue.Empty:
                if not any(t.is_alive() for t in threads) and finished.empty():
                    break
                continue
            with guard:
                busy[0] -= 1
            if exc is None:
                commit(task, result)
            elif isinstance(exc, Stop):
                state["stop"] = state["stop"] or str(exc)
            else:
                state["error"] = state["error"] or exc
        except KeyboardInterrupt:
            pressed += 1
            halt.set()
            state["interrupted"] = True
            if pressed > 1:
                state["abandoned"] = busy[0]
                log(f"Leaving {busy[0]} request(s) in flight; their items are not saved.")
                break
            log(f"Stopping: no new requests; waiting for {busy[0]} in flight (Ctrl-C again to leave them).")
    if state["error"] is not None:
        raise state["error"]
    return dict(stop=state["stop"], interrupted=state["interrupted"], abandoned=state["abandoned"])
