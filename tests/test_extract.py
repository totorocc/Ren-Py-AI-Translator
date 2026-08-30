"""Offline tests for the extractor and tl generator (no network required).

Run from the project root:
    python -m tests.test_extract
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from renpy_translator import extractor, tlgen  # noqa: E402

SAMPLE = os.path.join(os.path.dirname(__file__), "sample_game")


def test_extraction_counts():
    res = extractor.extract(SAMPLE)
    assert res.files_scanned == 1
    # 9 say statements (narration, dialogue, attributes, one-off, menu caption).
    assert len(res.dialogues) == 9, len(res.dialogues)
    # 2 menu choices + 3 gettext UI strings.
    assert len(res.strings) == 5, len(res.strings)
    assert "e" in res.characters and res.characters["e"].name == "Eileen"
    assert res.characters["narrator"].is_narrator


def test_identifiers_are_label_prefixed_and_unique():
    res = extractor.extract(SAMPLE)
    ids = [d.identifier for d in res.dialogues]
    assert len(ids) == len(set(ids)), "identifiers must be unique"
    assert all(i.startswith("start_") for i in ids), ids


def test_escapes_and_tags_preserved():
    res = extractor.extract(SAMPLE)
    line = next(d for d in res.dialogues if "{b}Dinner{/b}" in d.source_text)
    assert "happy" in line.prefix          # image attribute kept
    assert line.who_var == "e"


def test_tl_generation_roundtrip(tmp=None):
    res = extractor.extract(SAMPLE)
    for d in res.dialogues:
        d.translation = "X " + d.source_text
    for s in res.strings:
        s.translation = "X " + s.source_text
    summary = tlgen.write_tl_files(SAMPLE, "vietnamese", res)
    out = os.path.join(summary["tl_root"], "script.rpy")
    assert os.path.exists(out)
    with open(out, "r", encoding="utf-8") as f:
        text = f.read()
    assert text.startswith("﻿")                   # BOM like Ren'Py
    assert "translate vietnamese start_" in text
    assert "translate vietnamese strings:" in text
    assert 'old "Yes"' in text and 'new "X Yes"' in text
    # cleanup
    import shutil
    shutil.rmtree(os.path.join(SAMPLE, "game", "tl"), ignore_errors=True)


def test_python_data_not_treated_as_dialogue():
    """Regression: dict/list bodies in define/default must NOT become dialogue."""
    import tempfile, shutil
    tmp = tempfile.mkdtemp()
    try:
        gdir = os.path.join(tmp, "game")
        os.makedirs(gdir)
        with open(os.path.join(gdir, "data.rpy"), "w", encoding="utf-8") as f:
            f.write(
                'define clothing = {\n'
                '    "School Outfit (Episode 1)" : "School",\n'
                '    "Bar Dress" : "Bar",\n'
                '}\n'
                'define keymap = {\n'
                '    "A" : 97,\n'
                '}\n'
                'define facts = {\n'
                '    "Fact 1" : [__("The penis is not a muscle.")],\n'
                '}\n'
                'define credits = [\n'
                '    "Brokenone222 \\ \\ ", "Katie Barnes",\n'
                ']\n'
                'define e = Character("Mai")\n'
                'label start:\n'
                '    "It was quiet."\n'
                '    e "Hello there."\n'
            )
        res = extractor.extract(tmp)
        # Only the two real say lines; none of the dict/list entries.
        assert len(res.dialogues) == 2, [d.source_text for d in res.dialogues]
        texts = {d.source_text for d in res.dialogues}
        assert texts == {"It was quiet.", "Hello there."}, texts
        # The __() fact is captured as a translatable string.
        assert any(s.source_text == "The penis is not a muscle." for s in res.strings)
        # Dict keys/values like "School" must never be captured as dialogue.
        assert not any("School" in d.source_text for d in res.dialogues)
        # Generated tl must not contain dict syntax leaking into a say line.
        for d in res.dialogues:
            d.translation = "X " + d.source_text
        for s in res.strings:
            s.translation = "X " + s.source_text
        tlgen.write_tl_files(tmp, "vietnamese", res)
        out = os.path.join(gdir, "tl", "vietnamese", "data.rpy")
        text = open(out, encoding="utf-8").read()
        assert '" : "' not in text and '" : [' not in text, "dict syntax leaked into tl"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_text_passed_to_python_helpers_is_extracted():
    """Phone messages and similar helpers are text too, but never assets."""
    import tempfile, shutil
    tmp = tempfile.mkdtemp()
    try:
        gdir = os.path.join(tmp, "game")
        os.makedirs(gdir)
        with open(os.path.join(gdir, "s.rpy"), "w", encoding="utf-8") as f:
            f.write(
                'define e = Character("Miles")\n'
                'label start:\n'
                '    e "Alright, one more."\n'
                '    $ phone_message(sender_1, "Hey babe, how is it going?")\n'
                '    $ phone_reply("Still just as boring.")\n'
                '    $ phone_image(sender_1, "images/bg 694.jpg")\n'
                '    $ mode = "netorare"\n'
                '    $ colour = "#ff0000"\n'
                '    python:\n'
                '        note = "The name is: {=red}Miles{/=}"\n'
                '        flag = "agecheck"\n'
            )
        res = extractor.extract(tmp)
        got = {u.source_text for u in res.strings if u.kind == "python"}

        # Prose reaches the translation.
        assert "Hey babe, how is it going?" in got, got
        assert "Still just as boring." in got, got
        assert "The name is: {=red}Miles{/=}" in got, got

        # Assets, flags and colours must never be translated.
        assert not any("images/" in g for g in got), got
        assert "netorare" not in got and "agecheck" not in got, got
        assert "#ff0000" not in got, got

        # Real dialogue is unaffected.
        assert len(res.dialogues) == 1

        # And the feature can be switched off.
        off = extractor.extract(tmp, extract_python=False)
        assert not any(u.kind == "python" for u in off.strings)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_prose_filter_rejects_technical_strings():
    lp = extractor.looks_like_prose
    for good in ["Hey babe, how is it going?", "I am good", "Sure.",
                 "The name is: {=red}Miles{/=}", "Go for it."]:
        assert lp(good), good
    for bad in ["images/bg 694.jpg", "netorare", "sender_1", "#ff0000",
                "gui/button.png", "AGECHECK", "a.b.c", "bg 694.jpg"]:
        assert not lp(bad), bad


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = 0
    for fn in fns:
        fn()
        print("PASS", fn.__name__)
        passed += 1
    print(f"\n{passed}/{len(fns)} tests passed.")