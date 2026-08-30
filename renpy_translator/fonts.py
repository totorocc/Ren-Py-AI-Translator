"""Pick a font that can actually display the translated language.

A translation looks broken if the game's font has no glyphs for the target
language. Vietnamese is the common case: decorative Latin fonts usually stop at
Western European accents, so every character that needs a Vietnamese-specific
mark (a, o, u with horn/hook/dot, plus d-stroke) silently renders as nothing.
"Nang cam len cao hon mot chut" is what a player sees.

Rather than guessing, this module reads a font's `cmap` table and checks that
the codepoints the language needs are really present.
"""

from __future__ import annotations

import os
import re
import shutil
import struct

FONT_DIR_NAME = "rpt_fonts"

# Characters that a font must have to render the language properly. These are
# the ones ordinary Latin fonts miss.
from . import languages as languages_mod


def required_chars(language):
    """Characters a font must contain to render this language."""
    return languages_mod.test_chars(language)

# Fonts that ship with the OS, per script. The cmap check below is what
# actually decides, so these only put likely winners first; a full sweep of the
# system font folder follows.
SCRIPT_FONTS = {
    "nt": {
        "latin": ["segoeui.ttf", "arial.ttf", "tahoma.ttf", "calibri.ttf"],
        "cyrillic": ["segoeui.ttf", "arial.ttf", "tahoma.ttf"],
        "greek": ["segoeui.ttf", "arial.ttf", "tahoma.ttf"],
        "cjk_ja": ["meiryo.ttc", "YuGothM.ttc", "msgothic.ttc"],
        "cjk_ko": ["malgun.ttf", "malgunsl.ttf", "batang.ttc"],
        "cjk_zh_hans": ["msyh.ttc", "msyh.ttf", "simsun.ttc", "simhei.ttf"],
        "cjk_zh_hant": ["msjh.ttc", "msjh.ttf", "mingliu.ttc"],
        "thai": ["leelawui.ttf", "leelawad.ttf", "tahoma.ttf"],
        "arabic": ["segoeui.ttf", "tahoma.ttf", "arial.ttf"],
        "hebrew": ["segoeui.ttf", "tahoma.ttf", "arial.ttf", "david.ttf"],
        "devanagari": ["Nirmala.ttf", "mangal.ttf"],
        "bengali": ["Nirmala.ttf", "vrinda.ttf"],
    },
    "posix": {
        "latin": ["DejaVuSans.ttf", "NotoSans-Regular.ttf",
                  "LiberationSans-Regular.ttf"],
        "cyrillic": ["DejaVuSans.ttf", "NotoSans-Regular.ttf"],
        "greek": ["DejaVuSans.ttf", "NotoSans-Regular.ttf"],
        "cjk_ja": ["NotoSansCJK-Regular.ttc", "NotoSansJP-Regular.otf"],
        "cjk_ko": ["NotoSansCJK-Regular.ttc", "NotoSansKR-Regular.otf"],
        "cjk_zh_hans": ["NotoSansCJK-Regular.ttc", "NotoSansSC-Regular.otf"],
        "cjk_zh_hant": ["NotoSansCJK-Regular.ttc", "NotoSansTC-Regular.otf"],
        "thai": ["NotoSansThai-Regular.ttf", "Garuda.ttf"],
        "arabic": ["NotoSansArabic-Regular.ttf", "DejaVuSans.ttf"],
        "hebrew": ["NotoSansHebrew-Regular.ttf", "DejaVuSans.ttf"],
        "devanagari": ["NotoSansDevanagari-Regular.ttf"],
        "bengali": ["NotoSansBengali-Regular.ttf"],
    },
}

WIN_FONT_DIR = r"C:\Windows\Fonts"
POSIX_FONT_DIRS = ["/usr/share/fonts", "/usr/local/share/fonts",
                   "/Library/Fonts", "/System/Library/Fonts",
                   os.path.expanduser("~/.fonts")]


# ---------------------------------------------------------------------------
# Minimal TrueType/OpenType cmap reader
# ---------------------------------------------------------------------------

class FontError(RuntimeError):
    pass


def _read_table_directory(data, offset=0):
    if len(data) < offset + 12:
        raise FontError("File is too small to be a font")
    tag = data[offset:offset + 4]
    if tag == b"ttcf":                       # font collection: use the first font
        if len(data) < 16:
            raise FontError("Damaged font collection")
        first = struct.unpack(">I", data[12:16])[0]
        return _read_table_directory(data, first)
    if tag not in (b"\x00\x01\x00\x00", b"true", b"OTTO", b"ttcf"):
        raise FontError("Not a TrueType/OpenType font")
    num_tables = struct.unpack(">H", data[offset + 4:offset + 6])[0]
    tables = {}
    pos = offset + 12
    for _ in range(num_tables):
        if pos + 16 > len(data):
            break
        rec_tag = data[pos:pos + 4]
        rec_off, rec_len = struct.unpack(">II", data[pos + 8:pos + 16])
        tables[rec_tag] = (rec_off, rec_len)
        pos += 16
    return tables


def _cmap_lookup_tables(data):
    """Return parsed subtables that can answer 'is this codepoint covered'."""
    tables = _read_table_directory(data)
    if b"cmap" not in tables:
        raise FontError("Font has no cmap table")
    base, _length = tables[b"cmap"]
    if base + 4 > len(data):
        raise FontError("Damaged cmap table")
    num = struct.unpack(">H", data[base + 2:base + 4])[0]
    subtables = []
    for i in range(num):
        rec = base + 4 + i * 8
        if rec + 8 > len(data):
            break
        platform, encoding, sub_off = struct.unpack(">HHI", data[rec:rec + 8])
        subtables.append((platform, encoding, base + sub_off))
    return subtables


def _covered_format4(data, off, cp):
    if cp > 0xFFFF:
        return False
    seg_x2 = struct.unpack(">H", data[off + 6:off + 8])[0]
    seg = seg_x2 // 2
    ends = off + 14
    starts = ends + seg_x2 + 2
    deltas = starts + seg_x2
    ranges = deltas + seg_x2
    for i in range(seg):
        end = struct.unpack(">H", data[ends + i * 2:ends + i * 2 + 2])[0]
        if cp > end:
            continue
        start = struct.unpack(">H", data[starts + i * 2:starts + i * 2 + 2])[0]
        if cp < start:
            return False
        delta = struct.unpack(">h", data[deltas + i * 2:deltas + i * 2 + 2])[0]
        range_off = struct.unpack(">H", data[ranges + i * 2:ranges + i * 2 + 2])[0]
        if range_off == 0:
            return ((cp + delta) & 0xFFFF) != 0
        idx = ranges + i * 2 + range_off + (cp - start) * 2
        if idx + 2 > len(data):
            return False
        glyph = struct.unpack(">H", data[idx:idx + 2])[0]
        return glyph != 0
    return False


def _covered_format12(data, off, cp):
    n_groups = struct.unpack(">I", data[off + 12:off + 16])[0]
    lo, hi = 0, n_groups - 1
    while lo <= hi:                                  # groups are sorted
        mid = (lo + hi) // 2
        rec = off + 16 + mid * 12
        if rec + 12 > len(data):
            return False
        start, end, glyph = struct.unpack(">III", data[rec:rec + 12])
        if cp < start:
            hi = mid - 1
        elif cp > end:
            lo = mid + 1
        else:
            return glyph != 0
    return False


def _covered(data, subtables, cp):
    for platform, encoding, off in subtables:
        if off + 2 > len(data):
            continue
        fmt = struct.unpack(">H", data[off:off + 2])[0]
        # Prefer Unicode-capable subtables.
        if fmt == 12 and (platform, encoding) in ((3, 10), (0, 4), (0, 6)):
            if _covered_format12(data, off, cp):
                return True
        elif fmt == 4 and (platform in (0, 3)):
            if _covered_format4(data, off, cp):
                return True
    return False


def missing_characters(font_path: str, language: str) -> list:
    """Return the required characters this font cannot display."""
    required = required_chars(language)
    if not required:
        return []
    with open(font_path, "rb") as f:
        data = f.read()
    subtables = _cmap_lookup_tables(data)
    return [ch for ch in required if not _covered(data, subtables, ord(ch))]


def supports_language(font_path: str, language: str) -> bool:
    try:
        return not missing_characters(font_path, language)
    except (FontError, OSError, struct.error, IndexError):
        return False


# ---------------------------------------------------------------------------
# Finding and installing a usable font
# ---------------------------------------------------------------------------

def _installed_fonts(roots) -> list:
    """Every font file on the machine, in a stable order."""
    out = []
    for root in roots:
        if not os.path.isdir(root):
            continue
        for dirpath, _dirs, files in os.walk(root):
            for fn in sorted(files):
                if fn.lower().endswith((".ttf", ".otf", ".ttc")):
                    out.append(os.path.join(dirpath, fn))
            if len(out) > 800:
                return out
    return out


def _candidates(language: str) -> list:
    """Preferred fonts for the language's script first, then everything else.

    Matching is by file name rather than full path, because distributions put
    fonts in different subfolders.
    """
    key = "nt" if os.name == "nt" else "posix"
    script = languages_mod.script(language)
    preferred = [n.lower() for n in SCRIPT_FONTS.get(key, {}).get(script, [])]
    roots = [WIN_FONT_DIR] if os.name == "nt" else POSIX_FONT_DIRS

    installed = _installed_fonts(roots)
    by_name = {}
    for path in installed:
        by_name.setdefault(os.path.basename(path).lower(), []).append(path)

    ranked = []
    for name in preferred:                       # keep the listed order
        ranked.extend(by_name.get(name, []))
    seen = set(ranked)

    # Body text wants a regular weight; push styled faces to the back.
    styled = re.compile(r"(bold|italic|oblique|light|thin|black|semi|extra)",
                        re.I)
    rest = [p for p in installed if p not in seen]
    rest.sort(key=lambda p: bool(styled.search(os.path.basename(p))))
    ranked.extend(rest)
    return ranked


def find_system_font(language: str) -> str | None:
    """First installed font that really covers the language, or None."""
    seen = set()
    for path in _candidates(language):
        if path in seen or not os.path.isfile(path):
            continue
        seen.add(path)
        if supports_language(path, language):
            return path
    return None


def install_font(game_root: str, font_path: str) -> str:
    """Copy a font into the game and return the path Ren'Py should use."""
    from .extractor import _game_dir
    target_dir = os.path.join(_game_dir(game_root), FONT_DIR_NAME)
    os.makedirs(target_dir, exist_ok=True)
    name = os.path.basename(font_path)
    target = os.path.join(target_dir, name)
    if os.path.abspath(font_path) != os.path.abspath(target):
        shutil.copyfile(font_path, target)
    return "{}/{}".format(FONT_DIR_NAME, name)


def describe(font_path: str, language: str) -> dict:
    """Report whether a font is usable, for the UI."""
    if not font_path or not os.path.isfile(font_path):
        return {"ok": False, "message": "Font file not found."}
    try:
        missing = missing_characters(font_path, language)
    except (FontError, OSError, struct.error, IndexError) as e:
        return {"ok": False, "message": "Could not read this font: %s" % e}
    if missing:
        return {"ok": False, "missing": "".join(missing[:12]),
                "message": "This font is missing {} required character(s): {}".format(
                    len(missing), "".join(missing[:12]))}
    return {"ok": True, "message": "Font covers {}.".format(language)}
