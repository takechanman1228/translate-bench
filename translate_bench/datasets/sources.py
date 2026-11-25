"""Download the upstream files from their publishers and verify their SHA-256."""

import hashlib
import shutil
import ssl
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

USER_AGENT = "translate-bench/1.0 (+https://github.com/takechanman1228/translate-bench)"


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _context():
    """TLS context: certifi's bundle when installed, else the system's, else a known system bundle file
    (some Python builds for macOS ship without a configured certificate store)."""
    try:
        import certifi
    except ImportError:
        certifi = None
    if certifi is not None:
        return ssl.create_default_context(cafile=certifi.where())
    context = ssl.create_default_context()
    if not context.cert_store_stats().get("x509_ca"):
        for bundle in ("/etc/ssl/cert.pem", "/etc/ssl/certs/ca-certificates.crt", "/etc/pki/tls/certs/ca-bundle.crt"):
            if Path(bundle).is_file():
                context.load_verify_locations(cafile=bundle)
                break
    return context


def fetch(key, spec, cache, log=print):
    """Return the path of a verified copy of one upstream file, downloading it when needed."""
    path = cache / key
    if path.is_symlink():
        raise ValueError(f"{path}: the download cache must not contain symbolic links")
    if path.is_file():
        if digest(path) == spec["sha256"]:
            log(f"Reused {key} (SHA-256 verified)")
            return path
        log(f"Discarding {key}: its SHA-256 differs from the published one")
        path.unlink()
    path.parent.mkdir(parents=True, exist_ok=True)
    start = time.monotonic()
    request = urllib.request.Request(spec["url"], headers={"User-Agent": USER_AGENT})
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as staged:
        try:
            with urllib.request.urlopen(request, timeout=90, context=_context()) as response:
                shutil.copyfileobj(response, staged, length=1 << 20)
        except (urllib.error.URLError, OSError) as exc:
            Path(staged.name).unlink(missing_ok=True)
            reason = getattr(exc, "reason", exc)
            hint = ""
            if isinstance(reason, ssl.SSLError):
                hint = " (certificate check failed; `python -m pip install certifi` usually fixes this)"
            raise ValueError(f"Could not download {key} from {spec['url']}: {reason}{hint}") from None
    actual = digest(staged.name)
    if actual != spec["sha256"]:
        Path(staged.name).unlink()
        raise ValueError(f"SHA-256 mismatch for {key}: expected {spec['sha256']}, got {actual}")
    Path(staged.name).replace(path)
    log(f"Downloaded {key} ({path.stat().st_size:,} bytes, SHA-256 verified, {time.monotonic() - start:.1f} s)")
    return path


def fetch_all(keys, sources, cache, log=None):
    log = log or (lambda message: print(message, file=sys.stderr, flush=True))
    return {key: fetch(key, sources[key], cache, log) for key in keys}
