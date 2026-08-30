"""Turn the generated translation on inside the game, with a usable font.

Writing game/tl/<language>/ is only half the job:

* Ren'Py uses those files only when that language is selected, and most
  released games have no language selector, so the game keeps showing English.
  Ren'Py documents the fix (Translation -> Unsanctioned Translations): set
  ``config.language``, which overrides any memorised choice.

* The game's own font usually has no glyphs for the target language. For
  Vietnamese that means every character needing a horn/hook/dot mark silently
  disappears, so text renders as "Nang c m len cao h n m t chut". Ren'Py's
  documented answer is a ``translate <language> python`` block that swaps the
  fonts when the language is active.

Both are handled by one small, clearly-marked file written into the game.
Deleting that file puts the game back exactly as it was.
"""

from __future__ import annotations

import os

from . import languages as languages_mod
from .extractor import _game_dir

FILENAME = "zzz_rpt_language.rpy"

_HEADER = '''\
# Written by Ren'Py AI Translator.
#
# 1. Ren'Py only uses game/tl/{language}/ when that language is selected, and
#    this game has no language selector, so the language is set here.
# 2. The game's own font has no {language} glyphs, so the font is swapped
#    while that language is active.
#
# To undo everything, delete this file.
# Press ALT+L while playing to toggle the language.

init 1000 python:
    if getattr(persistent, "_rpt_disabled", False):
        config.language = None
    else:
        config.language = "{language}"

init 1001 python:
    def _rpt_toggle_language():
        persistent._rpt_disabled = not getattr(persistent, "_rpt_disabled", False)
        renpy.change_language(None if persistent._rpt_disabled else "{language}")
        renpy.restart_interaction()

screen _rpt_language_key():
    key "alt_K_l" action Function(_rpt_toggle_language)

init 1002 python:
    # Guarded: a missing config must never stop the game from starting.
    try:
        if "_rpt_language_key" not in config.overlay_screens:
            config.overlay_screens.append("_rpt_language_key")
    except Exception:
        pass
{rtl_block}'''

# Ren'Py re-runs these when the language is activated, then rebuilds styles.
_FONT_BLOCK = '''

# ---- Font and text layout for {language} -------------------------------------
# The original font lacks {language} glyphs. Each assignment is guarded so an
# older game without the GUI framework still starts normally.
# `language "{line_break}"` picks Ren'Py's line-breaking algorithm: scripts that
# do not put spaces between words need the Unicode or CJK rules, or text runs
# straight out of the dialogue box.

translate {language} python:
    _rpt_font = "{font}"
    for _rpt_name in ("text_font", "name_text_font", "interface_text_font",
                      "button_text_font", "choice_button_text_font",
                      "label_text_font", "notify_font", "input_font",
                      "system_font"):
        try:
            if hasattr(store.gui, _rpt_name):
                setattr(store.gui, _rpt_name, _rpt_font)
        except Exception:
            pass

translate {language} style default:
    font "{font}"
    language "{line_break}"

translate {language} style say_dialogue:
    font "{font}"

translate {language} style say_label:
    font "{font}"

translate {language} style button_text:
    font "{font}"

translate {language} style input:
    font "{font}"
'''


def switch_path(game_root: str) -> str:
    return os.path.join(_game_dir(game_root), FILENAME)


_RTL_BLOCK = """
init 1003 python:
    # {language} is written right to left; Ren'Py only reorders lines when
    # config.rtl is on.
    try:
        config.rtl = True
    except Exception:
        pass
"""


def build_content(language: str, font: str | None = None) -> str:
    rtl_block = (_RTL_BLOCK.format(language=language)
                 if languages_mod.is_rtl(language) else "")
    content = _HEADER.format(language=language, rtl_block=rtl_block)
    if font:
        content += _FONT_BLOCK.format(
            language=language, font=font,
            line_break=languages_mod.line_break(language))
    return content


def write_language_switch(game_root: str, language: str,
                          font: str | None = None) -> dict:
    """Create (or refresh) the activation file. Returns a summary dict."""
    path = switch_path(game_root)
    content = build_content(language, font)
    existing = None
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                existing = f.read()
        except OSError:
            existing = None
    if existing == content:
        return {"path": path, "written": False, "font": font,
                "reason": "already up to date"}
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    # A stale .rpyc next to it would shadow the new source.
    stale = path + "c"
    if os.path.exists(stale):
        try:
            os.remove(stale)
        except OSError:
            pass
    return {"path": path, "written": True, "font": font}


def remove_language_switch(game_root: str) -> bool:
    """Delete the activation file (back to the original language)."""
    removed = False
    for path in (switch_path(game_root), switch_path(game_root) + "c"):
        if os.path.exists(path):
            try:
                os.remove(path)
                removed = True
            except OSError:
                pass
    return removed


def is_active(game_root: str) -> bool:
    return os.path.exists(switch_path(game_root))
