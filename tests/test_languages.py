"""Multi-language support: glyphs, line breaking and reading direction.

Adding a language is not just a dropdown entry. Each one needs a font that has
the glyphs, the right line-breaking algorithm (Thai and Chinese do not put
spaces between words), and the right reading direction.

Run:  python -m tests.test_languages
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from renpy_translator import activate, fonts, languages, translator  # noqa: E402

# Values Ren'Py accepts for the `language` style property, from
# renpy/text/text.py.
VALID_LINE_BREAK = {
    "unicode", "eastasian", "thaic90", "korean-with-spaces", "western",
    "japanese-loose", "japanese-normal", "japanese-strict", "anywhere",
}


def test_every_language_is_well_formed():
    assert len(languages.LANGUAGES) >= 20
    for key, info in languages.LANGUAGES.items():
        # The key doubles as the game/tl/<key>/ folder name, so it must be a
        # plain identifier.
        assert key.isidentifier(), key
        assert info["line_break"] in VALID_LINE_BREAK, (key, info["line_break"])
        assert info["test_chars"], key
        assert info["address_note"], key
        assert isinstance(info["rtl"], bool), key


def test_spaceless_scripts_do_not_use_western_line_breaking():
    """Thai and CJK would run out of the textbox with western breaking."""
    for key in ("thai", "japanese", "simplified_chinese", "traditional_chinese",
                "korean", "arabic", "persian", "hindi"):
        assert languages.line_break(key) != "western", key


def test_right_to_left_languages_are_flagged():
    rtl = {k for k in languages.LANGUAGES if languages.is_rtl(k)}
    assert rtl == {"arabic", "persian", "hebrew", "urdu"}, rtl
    # And only those get the config.rtl switch written into the game.
    assert "config.rtl = True" in activate.build_content("persian", "f.ttf")
    assert "config.rtl" not in activate.build_content("vietnamese", "f.ttf")


def test_line_breaking_reaches_the_generated_file():
    content = activate.build_content("thai", "rpt_fonts/x.ttf")
    assert 'language "unicode"' in content, content
    content = activate.build_content("japanese", "rpt_fonts/x.ttf")
    assert 'language "japanese-normal"' in content


def test_font_check_is_language_aware():
    """A Latin-only font must fail for scripts it cannot render."""
    import glob
    latin_only = glob.glob("/usr/**/reportlab/fonts/Vera.ttf", recursive=True)
    if not latin_only:
        return
    path = latin_only[0]
    # Vera has plain Latin but nothing for these.
    for key in ("thai", "japanese", "arabic", "hindi", "vietnamese"):
        assert not fonts.supports_language(path, key), key
    # It does cover basic English.
    assert fonts.supports_language(path, "english")


def test_prompt_carries_per_language_address_rules():
    """The pronoun guidance is the point of the tool; it must reach the model."""
    for key, needle in (("thai", "ครับ"), ("japanese", "keigo"),
                        ("german", "du or Sie"), ("russian", "ты or вы"),
                        ("vietnamese", "anh/chị/em")):
        prompt = translator.build_system_prompt(key, "a game", ["NTR"], "guide")
        assert needle in prompt, (key, needle)
        assert translator.lang_display(key) in prompt, key


def test_unknown_language_does_not_crash():
    assert languages.display_name("klingon") == "klingon"
    assert languages.line_break("klingon") == "western"
    assert languages.is_rtl("klingon") is False
    prompt = translator.build_system_prompt("klingon", "g", [], "b")
    assert "klingon" in prompt


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print("PASS", fn.__name__)
    print("\n%d/%d tests passed." % (len(fns), len(fns)))
