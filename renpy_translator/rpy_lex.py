"""Low level Ren'Py string / say helpers.

This module reproduces the small pieces of Ren'Py's own source that are needed
to compute *translation identifiers* for dialogue and to encode/decode string
literals exactly the way Ren'Py does. Getting these byte-for-byte correct is
what makes the generated ``tl/`` files actually apply in game.

References (Ren'Py source, MIT licensed):
    renpy/translation/__init__.py  -> encode_say_string, quote_unicode
    renpy/translation/generation.py -> write_translates, create_translate
"""

from __future__ import annotations

import hashlib
import re


# ---------------------------------------------------------------------------
# String literal encode / decode
# ---------------------------------------------------------------------------

def encode_say_string(s: str) -> str:
    """Encode a string the way Ren'Py encodes say-statement text.

    Mirrors ``renpy.translation.encode_say_string``. Returns the value wrapped
    in double quotes.
    """
    s = s.replace("\\", "\\\\")
    s = s.replace("\n", "\\n")
    s = s.replace('"', '\\"')
    # Escape a space that immediately follows another space, so runs of spaces
    # survive. Using a function avoids backslash-in-replacement pitfalls.
    s = re.sub(r"(?<= ) ", lambda _m: "\\ ", s)
    return '"' + s + '"'


def quote_unicode(s: str) -> str:
    """Mirror ``renpy.translation.quote_unicode`` (used for old/new strings)."""
    s = s.replace("\\", "\\\\")
    s = s.replace('"', '\\"')
    s = s.replace("\a", "\\a")
    s = s.replace("\b", "\\b")
    s = s.replace("\f", "\\f")
    s = s.replace("\n", "\\n")
    s = s.replace("\r", "\\r")
    s = s.replace("\t", "\\t")
    s = s.replace("\v", "\\v")
    return s


_DECODE_MAP = {
    "n": "\n",
    "t": "\t",
    "r": "\r",
    "a": "\a",
    "b": "\b",
    "f": "\f",
    "v": "\v",
    '"': '"',
    "'": "'",
    "\\": "\\",
    " ": " ",
}


def decode_string_literal(inner: str) -> str:
    """Decode the *inner* text of a Ren'Py string literal to its value.

    ``inner`` is the text between the surrounding quotes, exactly as written in
    the .rpy file. We undo backslash escapes. Ren'Py interpolation/text-tag
    escapes ("[[", "{{") are NOT string escapes and are intentionally kept.
    """
    out = []
    i = 0
    n = len(inner)
    while i < n:
        c = inner[i]
        if c == "\\" and i + 1 < n:
            nxt = inner[i + 1]
            out.append(_DECODE_MAP.get(nxt, nxt))
            i += 2
        else:
            out.append(c)
            i += 1
    return "".join(out)


# ---------------------------------------------------------------------------
# say "get_code" reconstruction + translation identifier
# ---------------------------------------------------------------------------

def say_get_code(prefix: str, value: str, suffix: str = "") -> str:
    """Reconstruct ``Say.get_code()`` for a standard say statement.

    ``prefix`` holds the normalised who/attributes ("e", "e happy", "" for
    narration, or a quoted one-off name). ``value`` is the decoded dialogue
    text. ``suffix`` holds normalised trailing modifiers (e.g. "with dissolve",
    "nointeract"). The result is hashed to build the translation identifier.
    """
    parts = []
    if prefix:
        parts.append(prefix)
    parts.append(encode_say_string(value))
    if suffix:
        parts.append(suffix)
    return " ".join(parts)


def digest_for_code(code: str) -> str:
    """The 8-hex digest Ren'Py derives from a say statement's code."""
    md5 = hashlib.md5()
    md5.update((code + "\r\n").encode("utf-8"))
    return md5.hexdigest()[:8]


def base_identifier(label: str | None, digest: str) -> str:
    """Build the base identifier before collision suffixing.

    Mirrors ``Restructurer.unique_identifier`` minus the dedupe loop.
    """
    if label is None:
        return digest
    return label.replace(".", "_") + "_" + digest


class IdentifierAllocator:
    """Assigns unique identifiers in document order, matching Ren'Py's suffixing.

    Ren'Py appends ``_1``, ``_2`` ... when a base identifier collides with one
    already used in the game. We track every identifier we have handed out and
    apply the same rule.
    """

    def __init__(self) -> None:
        self._used: set[str] = set()

    def allocate(self, label: str | None, digest: str) -> str:
        base = base_identifier(label, digest)
        identifier = base
        i = 0
        while identifier in self._used:
            i += 1
            identifier = "{0}_{1}".format(base, i)
        self._used.add(identifier)
        return identifier
