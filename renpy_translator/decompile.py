"""Built-in .rpyc decompilation via unrpyc.

A released Ren'Py game whose source has been stripped only ships compiled
``.rpyc`` scripts, which cannot be read directly. This module makes the app
self-sufficient: it downloads the official unrpyc decompiler once into a local
cache and runs it to turn ``.rpyc`` back into ``.rpy`` source, so the user never
has to run a separate tool.

unrpyc: https://github.com/CensoredUsername/unrpyc (standalone, no Ren'Py needed)
"""

from __future__ import annotations

import io
import os
import subprocess
import sys
import urllib.request
import zipfile

CACHE_DIR = os.path.join(os.path.expanduser("~"), ".renpy_ai_translator", "unrpyc")
DEFAULT_URL = "https://github.com/CensoredUsername/unrpyc/archive/refs/heads/master.zip"


def _log(cb, msg):
    if cb:
        cb(msg)


def find_unrpyc(cache_dir=CACHE_DIR):
    """Return the path to a cached unrpyc.py, or None."""
    if not os.path.isdir(cache_dir):
        return None
    for root, _dirs, files in os.walk(cache_dir):
        if "unrpyc.py" in files:
            return os.path.join(root, "unrpyc.py")
    return None


def download_unrpyc(url=DEFAULT_URL, cache_dir=CACHE_DIR, log=None):
    """Download + extract unrpyc into the cache. Returns path to unrpyc.py."""
    os.makedirs(cache_dir, exist_ok=True)
    _log(log, "Downloading the unrpyc decompiler (one-time setup)...")
    req = urllib.request.Request(url, headers={"User-Agent": "renpy-ai-translator"})
    with urllib.request.urlopen(req, timeout=90) as resp:
        data = resp.read()
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise RuntimeError("Downloaded unrpyc archive is not a valid zip.")
    names = zf.namelist()
    if not any(n.endswith("unrpyc.py") for n in names):
        raise RuntimeError("Downloaded archive does not contain unrpyc.py.")
    # Guard against zip-slip.
    base = os.path.abspath(cache_dir)
    for n in names:
        dest = os.path.abspath(os.path.join(cache_dir, n))
        if not dest.startswith(base + os.sep) and dest != base:
            raise RuntimeError("Unsafe path in archive: " + n)
    zf.extractall(cache_dir)
    p = find_unrpyc(cache_dir)
    if not p:
        raise RuntimeError("unrpyc.py missing after extraction.")
    _log(log, "Decompiler ready.")
    return p


def ensure_unrpyc(url=DEFAULT_URL, cache_dir=CACHE_DIR, log=None):
    p = find_unrpyc(cache_dir)
    if p:
        return p
    return download_unrpyc(url, cache_dir, log)


def decompile_dir(game_dir, url=DEFAULT_URL, cache_dir=CACHE_DIR, log=None,
                  timeout=3600):
    """Decompile every .rpyc under ``game_dir`` (skips ones that already
    have a .rpy). Returns a summary dict.
    """
    unrpyc = ensure_unrpyc(url, cache_dir, log)
    _log(log, "Decompiling .rpyc scripts (this can take a while)...")
    # Without --clobber, unrpyc leaves existing .rpy untouched and only writes
    # source for compiled-only scripts. Run from unrpyc's own dir for imports.
    cmd = [sys.executable, unrpyc, game_dir]
    try:
        proc = subprocess.run(
            cmd, cwd=os.path.dirname(unrpyc),
            capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise RuntimeError("Decompiling timed out.")
    out = (proc.stdout or "") + (proc.stderr or "")
    for line in out.splitlines():
        line = line.strip()
        if line:
            _log(log, line[:200])
    if proc.returncode != 0 and "Decompilation of" not in out:
        # unrpyc returns non-zero on partial failures; surface a short reason.
        tail = "\n".join(out.splitlines()[-5:])[:400]
        _log(log, "unrpyc exited with code {}.".format(proc.returncode))
        if not out.strip():
            raise RuntimeError("unrpyc produced no output (code {}).".format(proc.returncode))
        _log(log, tail)
    return {"ok": True, "unrpyc": unrpyc, "returncode": proc.returncode}
