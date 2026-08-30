"""Translation memory: translate new game versions incrementally.

A game being translated is rarely finished in one pass, and a new game version
usually arrives before the translation is done. Re-translating every line each
time wastes time and API budget, and would throw away hand-edited lines.

This module stores every (speaker, source text) -> translation pair for a
*project* (a game, across all of its versions) so that on the next run only
genuinely new or changed English text is sent to the model.

Storage: ~/.renpy_ai_translator/memory/<project>__<language>.json

The key is the speaker plus the exact source text. Keying on the speaker
matters: the same English line said by a wife and by a stranger needs
different Vietnamese pronouns, so their translations must not be shared.
"""

from __future__ import annotations

import json
import os
import re
import time

from .extractor import (
    decode_string_literal,
    find_top_level_strings,
    strip_comment,
    _game_dir,
)

MEMORY_DIR = os.path.join(os.path.expanduser("~"), ".renpy_ai_translator", "memory")
_SEP = "\x00"

_TRANSLATE_BLOCK_RE = re.compile(r"^translate\s+(\w+)\s+(\w+)\s*:\s*$")
_TRANSLATE_STRINGS_RE = re.compile(r"^translate\s+(\w+)\s+strings\s*:\s*$")


# ---------------------------------------------------------------------------
# Keys
# ---------------------------------------------------------------------------

def speaker_key_from_prefix(prefix: str) -> str:
    """Normalise a say prefix into a stable speaker key.

    "" (narration) -> "", 'e happy' -> 'e', '"Sylvie"' -> '"Sylvie"'.
    """
    prefix = (prefix or "").strip()
    if not prefix:
        return ""
    if prefix[0] in ('"', "'"):
        return prefix
    return prefix.split()[0]


def make_key(speaker: str, source: str) -> str:
    return (speaker or "") + _SEP + source


def safe_name(s: str) -> str:
    s = re.sub(r"[^\w.-]+", "_", (s or "").strip())
    return s.strip("_") or "project"


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------

class TranslationMemory:
    """A project's saved translations for one target language."""

    def __init__(self, project: str, language: str, directory: str = None):
        self.project = project or "project"
        self.language = language
        # Resolved now (not at import time) so the location stays
        # overridable and testable.
        self.directory = directory or MEMORY_DIR
        self.entries: dict = {}
        self._loaded_count = 0

    @property
    def path(self) -> str:
        return os.path.join(
            self.directory,
            "{}__{}.json".format(safe_name(self.project), safe_name(self.language)),
        )

    def load(self):
        self.entries = {}
        if not os.path.exists(self.path):
            return self
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            return self
        for rec in data.get("entries", []):
            try:
                self.entries[make_key(rec.get("s", ""), rec["src"])] = rec["t"]
            except (KeyError, TypeError):
                continue
        self._loaded_count = len(self.entries)
        return self

    def save(self):
        os.makedirs(self.directory, exist_ok=True)
        records = []
        for key, translation in self.entries.items():
            speaker, _, source = key.partition(_SEP)
            records.append({"s": speaker, "src": source, "t": translation})
        payload = {
            "project": self.project,
            "language": self.language,
            "updated": time.strftime("%Y-%m-%d %H:%M:%S"),
            "count": len(records),
            "entries": records,
        }
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=1)
        os.replace(tmp, self.path)  # atomic: never leave a half-written memory
        return self

    # -- lookups ------------------------------------------------------
    def get(self, speaker: str, source: str):
        return self.entries.get(make_key(speaker, source))

    def put(self, speaker: str, source: str, translation: str):
        if source and translation:
            self.entries[make_key(speaker, source)] = translation

    def __len__(self):
        return len(self.entries)

    @property
    def added_since_load(self) -> int:
        return max(0, len(self.entries) - self._loaded_count)


# ---------------------------------------------------------------------------
# Importing existing tl/ files back into memory
# ---------------------------------------------------------------------------

def parse_say_line(code: str):
    """Return (speaker_key, text) for a say line, or None."""
    lits = find_top_level_strings(code)
    if not lits:
        return None
    first = lits[0]
    before = code[:first.start].strip()
    if before == "" and len(lits) >= 2:
        gap = code[first.end + 1:lits[1].start].strip()
        if gap == "":
            # One-off character:  "Sylvie" "Hello."
            return (code[first.start:first.end + 1],
                    decode_string_literal(lits[1].inner))
    return (speaker_key_from_prefix(before), decode_string_literal(first.inner))


def iter_tl_pairs(tl_root: str):
    """Yield (speaker_key, source, translation) from generated tl files.

    Reads both dialogue blocks (where the original is kept as a comment above
    the translated line) and `old`/`new` string blocks. This is what lets the
    tool recover previous work - including lines the user edited by hand.
    """
    if not os.path.isdir(tl_root):
        return
    for dirpath, _dirs, files in os.walk(tl_root):
        for fn in sorted(files):
            if not fn.endswith(".rpy"):
                continue
            try:
                with open(os.path.join(dirpath, fn), "r",
                          encoding="utf-8", errors="replace") as f:
                    lines = f.readlines()
            except OSError:
                continue
            in_strings = False
            pending_old = None
            block_original = None
            for raw in lines:
                line = raw.replace("﻿", "").rstrip("\n")
                stripped = line.strip()
                if not stripped:
                    continue

                if _TRANSLATE_STRINGS_RE.match(stripped):
                    in_strings = True
                    block_original = None
                    continue
                if _TRANSLATE_BLOCK_RE.match(stripped):
                    in_strings = False
                    block_original = None
                    continue

                if in_strings:
                    if stripped.startswith("old "):
                        lits = find_top_level_strings(stripped)
                        pending_old = decode_string_literal(lits[0].inner) if lits else None
                    elif stripped.startswith("new ") and pending_old is not None:
                        lits = find_top_level_strings(stripped)
                        if lits:
                            new = decode_string_literal(lits[0].inner)
                            if new:
                                yield ("", pending_old, new)
                        pending_old = None
                    continue

                # Dialogue block: "# <original>" then the translated line.
                if stripped.startswith("#"):
                    body = stripped.lstrip("#").strip()
                    parsed = parse_say_line(strip_comment(body)) if body else None
                    if parsed:
                        block_original = parsed
                    continue

                if block_original is not None:
                    parsed = parse_say_line(line)
                    if parsed:
                        src_speaker, src_text = block_original
                        _tl_speaker, tl_text = parsed
                        if src_text and tl_text:
                            yield (src_speaker, src_text, tl_text)
                    block_original = None


def import_from_tl(memory: TranslationMemory, game_root: str, language: str,
                   overwrite: bool = True) -> int:
    """Merge an existing game/tl/<language>/ folder into the memory.

    Returns the number of pairs imported. Untranslated lines (translation equal
    to the source) are skipped so they get retried later.
    """
    tl_root = os.path.join(_game_dir(game_root), "tl", language)
    n = 0
    for speaker, source, translation in iter_tl_pairs(tl_root):
        if translation == source:
            continue  # not actually translated yet
        if not overwrite and memory.get(speaker, source) is not None:
            continue
        memory.put(speaker, source, translation)
        n += 1
    return n


def list_projects(directory: str = None) -> list:
    directory = directory or MEMORY_DIR
    """List saved memories: [{project, language, count, updated, path}]."""
    out = []
    if not os.path.isdir(directory):
        return out
    for fn in sorted(os.listdir(directory)):
        if not fn.endswith(".json"):
            continue
        try:
            with open(os.path.join(directory, fn), "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            continue
        out.append({
            "project": data.get("project", fn),
            "language": data.get("language", ""),
            "count": data.get("count", len(data.get("entries", []))),
            "updated": data.get("updated", ""),
        })
    return out


def suggest_project_name(game_root: str) -> str:
    """Guess a version-independent project name from the folder name.

    'MyGame-0.7.2-pc' -> 'MyGame'. The user can always override it.
    """
    base = os.path.basename(os.path.normpath(game_root or "")) or "project"
    base = re.sub(r"[-_. ]+(pc|win|mac|linux|all|market|steam)$", "", base, flags=re.I)
    base = re.sub(r"[-_. ]*v?\d+(\.\d+)+[a-z]?.*$", "", base, flags=re.I)
    base = re.sub(r"[-_. ]+(ch|chapter|ep|episode|part)[-_. ]?\d+.*$", "", base, flags=re.I)
    return base.strip(" -_.") or os.path.basename(os.path.normpath(game_root or "")) or "project"
