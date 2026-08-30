"""Extract translatable units (dialogue + strings) and characters from a Ren'Py game.

The extractor scans ``<game_root>/game/**/*.rpy`` (skipping any existing ``tl/``
folder) and produces:

* DialogueUnit  - one per say statement, with a Ren'Py translation identifier.
* StringUnit    - menu choices and ``_(...)`` UI strings (old/new style).
* Character     - detected ``Character(...)`` definitions + sampled dialogue.

It is a pragmatic line-based parser tuned for the forms that make up the vast
majority of real visual-novel scripts. Unusual statement forms are skipped
rather than risk emitting a wrong translation identifier.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

from .rpy_lex import (
    IdentifierAllocator,
    decode_string_literal,
    digest_for_code,
    say_get_code,
)

# Statement keywords that begin a NON-dialogue statement. If a line's first
# token is one of these (and it is not also a known Character variable), the
# line is never treated as a say statement.
RESERVED = {
    "if", "elif", "else", "while", "for", "pass", "return", "jump", "call",
    "menu", "label", "scene", "show", "hide", "with", "play", "stop", "queue",
    "voice", "pause", "window", "nvl", "define", "default", "python", "init",
    "image", "transform", "screen", "style", "add", "use", "has", "on",
    "import", "from", "class", "def", "at", "as", "behind", "onlayer",
    "zorder", "expression", "text", "textbutton", "imagebutton", "hbox",
    "vbox", "vpgrid", "frame", "fixed", "grid", "side", "key", "timer",
    "mousearea", "drag", "draggable", "bar", "vbar", "viewport", "transclude",
    "showif", "layeredimage", "camera", "function", "contains", "block",
    "parallel", "choice", "time", "repeat", "event", "extend",
}

# Block headers (ending in ``:``) inside which leading strings are NOT dialogue
# (screen language, raw python, styling, etc.). Say extraction is suppressed.
SUPPRESS_OPENERS = re.compile(
    r"^(screen|python|init\s+python|init|style|transform|layeredimage|image|"
    r"camera|translate)\b.*:\s*$"
)

# Files this tool generates itself. Re-scanning them would turn our own output
# (font names, style blocks) into fake dialogue and bill it on every run.
GENERATED_FILES = {"zzz_rpt_language.rpy"}

_PREFIX_RE = re.compile(r"[A-Za-z_][\w@-]*(\s+[@-]?[\w@-]+)*$")
# A say suffix starting with one of these is dict/list/code syntax, not dialogue.
_BAD_SUFFIX = set(":,=]})")
_CHARACTER_DEF_RE = re.compile(
    r"^\s*(?:define|default)\s+([A-Za-z_]\w*)\s*\+?=\s*"
    r"(?:Character|DynamicCharacter)\s*\((.*)$"
)
_GETTEXT_RE = re.compile(r"""_\(\s*(?P<q>['"])(?P<body>(?:\\.|(?!(?P=q)).)*)(?P=q)\s*\)""")
# Text handed to Python helpers, e.g. `$ phone_message(sender, "Hi there")`.
# Ren'Py never generates translate blocks for these, but it *does* run every
# displayed string through the string translator (renpy.substitutions.substitute
# calls translate_string), so they can be translated as old/new string pairs.
# The filters below keep prose and reject asset paths, flags and identifiers.
_PY_OPENER_RE = re.compile(r"^(init\s+-?\d*\s*python|python)\b.*:\s*$")
_TAG_RE = re.compile(r"\{[^{}]*\}")
_INTERP_RE = re.compile(r"\[[^\[\]]*\]")
_ASSET_RE = re.compile(
    r"\.(png|jpg|jpeg|webp|gif|bmp|ogg|mp3|wav|opus|webm|mp4|avi|mkv|rpy|rpyc"
    r"|ttf|otf|json|txt|xml|csv)$", re.I)
_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
# A dotted reference such as store.foo.bar - must have real segments, so a
# sentence like "Sure." is not mistaken for one.
_DOTTED_RE = re.compile(r"^[A-Za-z_]\w*(\.[A-Za-z_]\w*)+$")
_CONST_RE = re.compile(r"^[A-Z0-9_ ]+$")
_TERMINAL_RE = re.compile(r"[.!?\u2026]$")


def looks_like_prose(text: str) -> bool:
    """True if a string literal reads like text shown to the player."""
    t = (text or "").strip()
    if len(t) < 2 or not re.search(r"[A-Za-z]", t):
        return False
    if _IDENT_RE.match(t) or _DOTTED_RE.match(t) or _CONST_RE.match(t):
        return False
    if t.startswith("#"):                       # colour literals
        return False
    # Ren'Py tags and interpolations are not evidence either way, and a closing
    # tag like {/b} would otherwise look like a path.
    bare = _INTERP_RE.sub("", _TAG_RE.sub("", t)).strip()
    if not bare:
        return False
    if "/" in bare or "\\" in bare:
        return False
    if _ASSET_RE.search(bare):
        return False
    if re.search(r"\s", bare):                  # two or more words
        return True
    return bool(_TERMINAL_RE.search(bare)) and len(bare) >= 3


_LABEL_RE = re.compile(r"^label\s+([A-Za-z_]\w*)\s*(?:\(.*\))?\s*:")
_MENU_RE = re.compile(r"^menu\b.*:\s*$")


@dataclass
class DialogueUnit:
    file_rel: str
    line_no: int
    label: str | None
    prefix: str          # normalised who + attributes ("" for narration)
    suffix: str          # normalised trailing modifiers
    source_text: str     # decoded dialogue value
    original_code: str   # reconstructed get_code() (original)
    identifier: str
    who_var: str | None  # the character variable, if any
    speaker: str = ""    # resolved display name (filled later)
    translation: str = ""


@dataclass
class StringUnit:
    file_rel: str
    line_no: int
    source_text: str     # decoded value (the translation key)
    kind: str            # "menu" | "gettext"
    translation: str = ""


@dataclass
class Character:
    var: str
    name: str
    is_narrator: bool = False
    count: int = 0
    samples: list[str] = field(default_factory=list)


@dataclass
class ExtractResult:
    dialogues: list[DialogueUnit] = field(default_factory=list)
    strings: list[StringUnit] = field(default_factory=list)
    characters: dict[str, Character] = field(default_factory=dict)
    files_scanned: int = 0

    @property
    def total_units(self) -> int:
        return len(self.dialogues) + len(self.strings)


# ---------------------------------------------------------------------------
# Lexical helpers
# ---------------------------------------------------------------------------

@dataclass
class _Lit:
    start: int
    end: int      # index of the closing quote
    inner: str


def strip_comment(line: str) -> str:
    """Remove a trailing ``#`` comment, respecting string literals."""
    out = []
    i = 0
    n = len(line)
    quote = None
    while i < n:
        c = line[i]
        if quote:
            out.append(c)
            if c == "\\" and i + 1 < n:
                out.append(line[i + 1])
                i += 2
                continue
            if c == quote:
                quote = None
        else:
            if c == "#":
                break
            if c in ('"', "'"):
                quote = c
            out.append(c)
        i += 1
    return "".join(out).rstrip()


def find_top_level_strings(code: str) -> list[_Lit]:
    """Return string literals that are not nested inside another string."""
    lits: list[_Lit] = []
    i = 0
    n = len(code)
    while i < n:
        c = code[i]
        if c in ('"', "'"):
            quote = c
            j = i + 1
            buf = []
            while j < n:
                cj = code[j]
                if cj == "\\" and j + 1 < n:
                    buf.append(code[j:j + 2])
                    j += 2
                    continue
                if cj == quote:
                    break
                buf.append(cj)
                j += 1
            lits.append(_Lit(start=i, end=j, inner="".join(buf)))
            i = j + 1
        else:
            i += 1
    return lits


def _norm_ws(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def _bracket_delta(code: str) -> int:
    """Net change in ()/[]{} nesting on a line, ignoring brackets in strings."""
    depth = 0
    i = 0
    n = len(code)
    quote = None
    while i < n:
        c = code[i]
        if quote:
            if c == "\\" and i + 1 < n:
                i += 2
                continue
            if c == quote:
                quote = None
            i += 1
            continue
        if c in ('"', "'"):
            quote = c
        elif c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
        i += 1
    return depth


def _looks_like_prefix(before: str) -> bool:
    if not before:
        return True
    return bool(_PREFIX_RE.match(before))


# ---------------------------------------------------------------------------
# Character defaults
# ---------------------------------------------------------------------------

def _parse_character_name(args: str) -> str | None:
    """Pull a display name out of the first Character() argument."""
    args = args.strip()
    if args.startswith("None"):
        return None
    m = re.match(r"""_\(\s*(['"])((?:\\.|(?!\1).)*)\1""", args)
    if m:
        return decode_string_literal(m.group(2))
    m = re.match(r"""(['"])((?:\\.|(?!\1).)*)\1""", args)
    if m:
        return decode_string_literal(m.group(2))
    return None


# ---------------------------------------------------------------------------
# Main extraction
# ---------------------------------------------------------------------------

def iter_rpy_files(game_root: str):
    """Yield (abs_path, rel_path_under_game) for translatable .rpy files."""
    game_dir = _game_dir(game_root)
    for dirpath, dirnames, filenames in os.walk(game_dir):
        rel_dir = os.path.relpath(dirpath, game_dir)
        parts = rel_dir.replace("\\", "/").split("/")
        if parts and parts[0] == "tl":
            continue
        for fn in sorted(filenames):
            if not fn.endswith(".rpy") or fn in GENERATED_FILES:
                continue
            abs_path = os.path.join(dirpath, fn)
            rel = os.path.relpath(abs_path, game_dir).replace("\\", "/")
            yield abs_path, rel


def _game_dir(game_root: str) -> str:
    """Resolve the inner ``game`` directory of a Ren'Py project."""
    cand = os.path.join(game_root, "game")
    if os.path.isdir(cand):
        return cand
    # The user may have pointed directly at the game/ folder.
    return game_root


def find_characters(game_root: str) -> dict[str, Character]:
    chars: dict[str, Character] = {}
    for abs_path, _rel in iter_rpy_files(game_root):
        try:
            with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
                for raw in f:
                    m = _CHARACTER_DEF_RE.match(raw)
                    if not m:
                        continue
                    var = m.group(1)
                    name = _parse_character_name(m.group(2))
                    chars[var] = Character(
                        var=var,
                        name=name or var,
                        is_narrator=(name is None),
                    )
        except OSError:
            continue
    return chars


def extract(game_root: str, max_samples: int = 8,
            extract_python: bool = True) -> ExtractResult:
    result = ExtractResult()
    result.characters = find_characters(game_root)
    known_chars = set(result.characters.keys())
    alloc = IdentifierAllocator()
    seen_strings: set[str] = set()

    for abs_path, rel in iter_rpy_files(game_root):
        result.files_scanned += 1
        current_label: str | None = None
        menu_stack: list[int] = []
        suppress_stack: list[int] = []
        python_stack: list[int] = []
        expr_depth = 0
        try:
            with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
        except OSError:
            continue

        for idx, raw in enumerate(lines):
            line_no = idx + 1
            code = strip_comment(raw.replace("\t", "    ").rstrip("\n"))
            if not code.strip():
                continue
            indent = len(code) - len(code.lstrip(" "))
            stripped = code.strip()

            # Close blocks we have dedented out of.
            while menu_stack and indent <= menu_stack[-1]:
                menu_stack.pop()
            while suppress_stack and indent <= suppress_stack[-1]:
                suppress_stack.pop()
            while python_stack and indent <= python_stack[-1]:
                python_stack.pop()

            # Track multi-line Python expressions (dict/list values in define/
            # default, etc.) so their entries are never read as dialogue.
            depth_before = expr_depth
            expr_depth = max(0, expr_depth + _bracket_delta(code))

            suppressed = bool(suppress_stack) or depth_before > 0

            # gettext strings can appear anywhere (even in suppressed blocks).
            for gm in _GETTEXT_RE.finditer(code):
                val = decode_string_literal(gm.group("body"))
                if val and val not in seen_strings:
                    seen_strings.add(val)
                    result.strings.append(
                        StringUnit(rel, line_no, val, "gettext")
                    )

            # Text passed to Python helpers (phone messages, custom UI, ...).
            if extract_python and (stripped.startswith("$ ") or python_stack):
                for lit in find_top_level_strings(code):
                    val = decode_string_literal(lit.inner)
                    if val and val not in seen_strings and looks_like_prose(val):
                        seen_strings.add(val)
                        result.strings.append(
                            StringUnit(rel, line_no, val, "python"))

            # Character definitions (single line).
            cm = _CHARACTER_DEF_RE.match(code)
            if cm:
                var = cm.group(1)
                if var not in result.characters:
                    nm = _parse_character_name(cm.group(2))
                    result.characters[var] = Character(
                        var=var, name=nm or var, is_narrator=(nm is None)
                    )
                    known_chars.add(var)
                continue

            # Block openers that suppress say extraction.
            if SUPPRESS_OPENERS.match(stripped):
                if _PY_OPENER_RE.match(stripped):
                    python_stack.append(indent)
                suppress_stack.append(indent)
                continue

            lm = _LABEL_RE.match(stripped)
            if lm:
                name = lm.group(1)
                if not name.startswith("_"):
                    current_label = name
                continue

            is_menu_header = bool(_MENU_RE.match(stripped))
            in_menu = bool(menu_stack) and indent > menu_stack[-1]

            classified = _classify(code, in_menu, suppressed, known_chars)
            if classified is not None:
                kind = classified[0]
                if kind == "choice":
                    val = decode_string_literal(classified[1])
                    if val and val not in seen_strings:
                        seen_strings.add(val)
                        result.strings.append(
                            StringUnit(rel, line_no, val, "menu")
                        )
                elif kind == "say":
                    _add_dialogue(
                        result, alloc, known_chars, rel, line_no,
                        current_label, classified,
                        max_samples,
                    )

            if is_menu_header:
                menu_stack.append(indent)

    # Resolve speaker display names.
    for d in result.dialogues:
        if d.who_var is None:
            d.speaker = "Narrator"
        elif d.who_var.startswith('"') or d.who_var.startswith("'"):
            d.speaker = decode_string_literal(d.who_var[1:-1])
        else:
            ch = result.characters.get(d.who_var)
            d.speaker = ch.name if ch else d.who_var
    return result


def _add_dialogue(result, alloc, known_chars, rel, line_no, label,
                  classified, max_samples):
    _, prefix, inner, suffix = classified
    value = decode_string_literal(inner)
    if not value:
        return
    code = say_get_code(prefix, value, suffix)
    digest = digest_for_code(code)
    identifier = alloc.allocate(label, digest)

    who_var: str | None
    if prefix == "":
        who_var = None
    elif prefix.startswith('"') or prefix.startswith("'"):
        who_var = prefix
    else:
        who_var = prefix.split()[0]

    result.dialogues.append(DialogueUnit(
        file_rel=rel, line_no=line_no, label=label, prefix=prefix,
        suffix=suffix, source_text=value, original_code=code,
        identifier=identifier, who_var=who_var,
    ))

    # Sample dialogue for the character bible.
    if who_var and not (who_var.startswith('"') or who_var.startswith("'")):
        ch = result.characters.get(who_var)
        if ch is None:
            ch = Character(var=who_var, name=who_var)
            result.characters[who_var] = ch
            known_chars.add(who_var)
        ch.count += 1
        if len(ch.samples) < max_samples and len(value) > 4:
            ch.samples.append(value)


def _classify(code: str, in_menu: bool, suppressed: bool, known_chars: set):
    """Classify a code line. Returns a tuple or None.

    ("say", prefix, inner, suffix) or ("choice", inner).
    """
    lits = find_top_level_strings(code)
    if not lits:
        return None
    first = lits[0]
    before = code[:first.start].strip()
    ends_colon = code.rstrip().endswith(":")

    # Menu choice: a leading string that opens a block.
    if in_menu and before == "" and ends_colon:
        return ("choice", first.inner)

    if suppressed:
        return None

    if ends_colon:
        # if cond:, while ...:, etc. - the string is a code literal.
        return None

    # One-off string character:  "Sylvie" "Hello."
    if before == "" and len(lits) >= 2:
        between = code[first.end + 1:lits[1].start].strip()
        if between == "":
            prefix = code[first.start:first.end + 1]
            suffix = _norm_ws(code[lits[1].end + 1:])
            if suffix[:1] in _BAD_SUFFIX:
                return None
            return ("say", prefix, lits[1].inner, suffix)

    # Narration.
    if before == "":
        suffix = _norm_ws(code[first.end + 1:])
        if suffix[:1] in _BAD_SUFFIX:
            return None
        return ("say", "", first.inner, suffix)

    # who + attributes.
    if not _looks_like_prefix(before):
        return None
    tokens = before.split()
    first_tok = tokens[0]
    if first_tok in RESERVED and first_tok not in known_chars and first_tok != "extend":
        return None
    if (first_tok in known_chars) or (first_tok == "extend") or (first_tok not in RESERVED):
        prefix = " ".join(tokens)
        suffix = _norm_ws(code[first.end + 1:])
        if suffix[:1] in _BAD_SUFFIX:
            return None
        return ("say", prefix, first.inner, suffix)
    return None
