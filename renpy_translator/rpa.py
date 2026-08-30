"""Unpack Ren'Py .rpa archives (RPA-2.0 / RPA-3.0) in pure Python.

Released games usually pack the contents of ``game/`` into one or more ``.rpa``
archives, so the loose ``.rpy`` scripts are not visible on disk. This module
extracts the script files out of those archives so the scanner can read them,
the same first step the Ren'Py SDK or tools like rpatool perform.

The archive index is a zlib-compressed pickle. We unpickle it with a restricted
unpickler that refuses to import/execute anything, so a malicious index cannot
run code.
"""

from __future__ import annotations

import io
import os
import pickle
import zlib

SCRIPT_EXTS = (".rpy", ".rpyc", ".rpym", ".rpymc")


class _SafeUnpickler(pickle.Unpickler):
    """Allow only the plain data types that an RPA index is made of."""

    def find_class(self, module, name):
        raise pickle.UnpicklingError(
            "Refusing to load {}.{} from archive index".format(module, name))


def _loads_safe(data: bytes):
    return _SafeUnpickler(io.BytesIO(data)).load()


def is_rpa(path: str) -> bool:
    try:
        with open(path, "rb") as f:
            return f.read(7) in (b"RPA-3.0", b"RPA-2.0")
    except OSError:
        return False


def extract_rpa(archive_path: str, out_dir: str,
                only_exts: tuple | None = None) -> list:
    """Extract files from one .rpa archive into ``out_dir``.

    Returns the list of archive-relative paths written. If ``only_exts`` is
    given, only files with those extensions are written.
    """
    written = []
    with open(archive_path, "rb") as f:
        header = f.readline()
        parts = header.split()
        if not parts:
            raise ValueError("Empty archive header")
        magic = parts[0]
        if magic == b"RPA-3.0":
            offset = int(parts[1], 16)
            key = int(parts[2], 16)
        elif magic == b"RPA-2.0":
            offset = int(parts[1], 16)
            key = 0
        else:
            raise ValueError("Not an RPA-2.0/3.0 archive: " + archive_path)

        f.seek(offset)
        index = _loads_safe(zlib.decompress(f.read()))

        for path, entries in index.items():
            if not entries:
                continue
            entry = entries[0]
            if len(entry) == 2:
                start, length = entry
                prefix = b""
            else:
                start, length, prefix = entry[0], entry[1], entry[2]
                if isinstance(prefix, str):
                    prefix = prefix.encode("latin-1", "replace")
            start ^= key
            length ^= key

            norm = str(path).replace("\\", "/")
            if only_exts and not norm.lower().endswith(only_exts):
                continue

            f.seek(start)
            body = f.read(max(0, length - len(prefix)))
            data = prefix + body

            out_path = os.path.join(out_dir, *norm.split("/"))
            os.makedirs(os.path.dirname(out_path) or out_dir, exist_ok=True)
            with open(out_path, "wb") as o:
                o.write(data)
            written.append(norm)
    return written


def find_archives(game_dir: str) -> list:
    archives = []
    for dirpath, _dirnames, filenames in os.walk(game_dir):
        for fn in filenames:
            if fn.lower().endswith(".rpa"):
                p = os.path.join(dirpath, fn)
                if is_rpa(p):
                    archives.append(p)
    return archives


def unpack_archives(game_dir: str, only_scripts: bool = True) -> dict:
    """Unpack every .rpa in ``game_dir``. Returns a summary dict.

    By default only script files (.rpy/.rpyc) are extracted, which is all the
    translator needs and avoids unpacking gigabytes of images/audio.
    """
    only = SCRIPT_EXTS if only_scripts else None
    archives = find_archives(game_dir)
    results = []
    total = 0
    for arc in archives:
        try:
            files = extract_rpa(arc, game_dir, only_exts=only)
            results.append({"archive": os.path.basename(arc), "files": len(files)})
            total += len(files)
        except Exception as e:  # noqa: BLE001 - report, keep going
            results.append({"archive": os.path.basename(arc), "error": str(e)})
    return {"archives": len(archives), "files_extracted": total, "details": results}
