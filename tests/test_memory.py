"""Incremental translation tests: new game version must not restart from zero.

Run from the project root:
    python -m tests.test_memory
"""

import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import renpy_translator.memory as memory_mod  # noqa: E402
from renpy_translator import config, extractor, pipeline  # noqa: E402

VI = {
    "It was quiet.": "Trời yên tĩnh.",
    "Hello there.": "Chào anh.",
    "I missed you.": "Em nhớ anh.",
    "Good night.": "Chúc ngủ ngon.",
    "Who are you?": "Anh là ai?",
    "A new scene begins.": "Một cảnh mới bắt đầu.",
    "Hello there, darling.": "Chào anh yêu.",
}


class _Harness:
    """Isolates the memory folder and counts lines sent to the model."""

    def __init__(self):
        self.dirs = []
        self.sent = 0
        self.last_result = None
        self._real_dir = memory_mod.MEMORY_DIR
        self._real_batch = pipeline.translate_items
        memory_mod.MEMORY_DIR = self.tmp()
        pipeline.translate_items = self._fake_batch

    def _fake_batch(self, client, prompt, items, log=None, _depth=0):
        self.sent += len(items)
        return {i["id"]: VI.get(i["text"], "??" + i["text"]) for i in items}

    def tmp(self, prefix="rpt_"):
        d = tempfile.mkdtemp(prefix=prefix)
        self.dirs.append(d)
        return d

    def game(self, prefix, lines):
        root = self.tmp(prefix)
        gdir = os.path.join(root, "game")
        os.makedirs(gdir, exist_ok=True)
        with open(os.path.join(gdir, "s.rpy"), "w", encoding="utf-8") as f:
            f.write('define e = Character("Mai")\nlabel start:\n')
            for line in lines:
                f.write("    " + line + "\n")
        return root

    def translate(self, root, project="MyGame"):
        state = pipeline.JobState()
        # Keep the extraction that the run actually mutated, so tests can
        # inspect the units afterwards.
        self.last_result = extractor.extract(root)
        pipeline.run_translation(
            state, root, "vietnamese", config.AppConfig(model="dummy"),
            "a test game", ["NTR"], "guide",
            self.last_result, project=project)
        return state.snapshot()

    @staticmethod
    def tl_path(root):
        return os.path.join(root, "game", "tl", "vietnamese", "s.rpy")

    def close(self):
        memory_mod.MEMORY_DIR = self._real_dir
        pipeline.translate_items = self._real_batch
        for d in self.dirs:
            shutil.rmtree(d, ignore_errors=True)


V1 = ['"It was quiet."', 'e "Hello there."', 'e "I missed you."', 'e "Good night."']
V2 = ['"It was quiet."', 'e "Hello there, darling."', 'e "I missed you."',
      'e "Good night."', 'e "Who are you?"', '"A new scene begins."']


def test_new_version_only_translates_new_lines():
    h = _Harness()
    try:
        v1 = h.game("MyGame-0.5_", V1)
        h.translate(v1)
        assert h.sent == 4, h.sent

        # A new version, in a NEW folder: 3 unchanged, 1 changed, 2 added.
        h.sent = 0
        v2 = h.game("MyGame-0.6_", V2)
        result = extractor.extract(v2)
        plan = pipeline.plan_translation(result, "MyGame", "vietnamese",
                                         game_root=v2)
        assert plan["total"] == 6 and plan["reused"] == 3 and plan["new"] == 3, plan

        snap = h.translate(v2)
        assert h.sent == 3, "only new/changed text may be sent, got %s" % h.sent
        assert snap["reused"] == 3, snap
        text = open(h.tl_path(v2), encoding="utf-8").read()
        for expected in ("Trời yên tĩnh.", "Chào anh yêu.", "Anh là ai?"):
            assert expected in text, expected

        # Running again costs nothing at all.
        h.sent = 0
        h.translate(v2)
        assert h.sent == 0, "a re-run must not re-send anything"
    finally:
        h.close()


def test_hand_edited_translation_survives_and_is_reused():
    h = _Harness()
    try:
        v1 = h.game("MyGame-0.5_", V1)
        h.translate(v1)

        # Edit one line by hand, the way a user polishing pronouns would.
        path = h.tl_path(v1)
        with open(path, encoding="utf-8") as f:
            edited = f.read().replace('e "Chúc ngủ ngon."',
                                      'e "Ngủ ngon nhé anh yêu."')
        with open(path, "w", encoding="utf-8") as f:
            f.write(edited)

        # Re-running the same game keeps the edit (tl wins over stored memory).
        h.sent = 0
        h.translate(v1)
        assert h.sent == 0
        assert "Ngủ ngon nhé anh yêu." in open(path, encoding="utf-8").read()

        # And the edit carries into the next version via the memory.
        v2 = h.game("MyGame-0.6_", V2)
        h.translate(v2)
        assert "Ngủ ngon nhé anh yêu." in open(h.tl_path(v2), encoding="utf-8").read()
    finally:
        h.close()


def test_memory_is_per_project_and_per_speaker():
    h = _Harness()
    try:
        v1 = h.game("MyGame-0.5_", V1)
        h.translate(v1, project="MyGame")
        # A different game must not reuse the first game's memory.
        h.sent = 0
        other = h.game("OtherGame-1.0_", V1)
        h.translate(other, project="OtherGame")
        assert h.sent == 4, "a different project must start clean"

        # Same English line, different speaker -> not shared (pronouns differ).
        mem = memory_mod.TranslationMemory("MyGame", "vietnamese").load()
        assert mem.get("e", "Hello there.") is not None
        assert mem.get("b", "Hello there.") is None
    finally:
        h.close()


def test_import_from_older_version_folder():
    h = _Harness()
    try:
        v1 = h.game("MyGame-0.5_", V1)
        h.translate(v1, project="MyGame")
        # Seed a fresh project name from the older folder (the Import button).
        mem = memory_mod.TranslationMemory("Renamed", "vietnamese")
        added = memory_mod.import_from_tl(mem, v1, "vietnamese")
        mem.save()
        assert added == 4, added
        assert memory_mod.TranslationMemory("Renamed", "vietnamese").load().get(
            "e", "Good night.") == "Chúc ngủ ngon."
    finally:
        h.close()


def test_repeated_lines_are_sent_once():
    """VN scripts repeat a lot of text; each distinct line costs one slot."""
    h = _Harness()
    try:
        lines = ['"It was quiet."'] * 5 + ['e "Hello there."'] * 3 + ['e "Good night."']
        root = h.game("Repeats-1.0_", lines)
        assert len(pipeline.all_units(extractor.extract(root))) == 9

        snap = h.translate(root, project="Repeats")
        result = h.last_result
        # 9 lines in the game, but only 3 distinct ones are billed.
        assert h.sent == 3, "duplicates must not be re-sent, got %s" % h.sent
        assert snap["total"] == 9 and snap["failed"] == 0, snap
        assert snap["unique_total"] == 3, snap

        # Every occurrence still receives the translation.
        for unit in pipeline.all_units(result):
            assert unit.translation, unit.source_text
        text = open(h.tl_path(root), encoding="utf-8").read()
        assert text.count("Trời yên tĩnh.") == 5, text.count("Trời yên tĩnh.")
    finally:
        h.close()


def test_translation_is_switched_on_inside_the_game():
    """Writing tl/ is not enough: Ren'Py must be told to use the language."""
    from renpy_translator import activate
    h = _Harness()
    try:
        root = h.game("Activate-1.0_", V1)
        h.translate(root, project="Activate")

        path = activate.switch_path(root)
        assert os.path.exists(path), "language switch file must be written"
        text = open(path, encoding="utf-8").read()
        # config.language is the documented way to force an unsanctioned
        # translation on when the game has no language selector.
        assert 'config.language = "vietnamese"' in text, text
        assert "init 1000 python:" in text, "must run after the game's own init"
        # It lives in game/, never inside tl/.
        assert os.path.basename(os.path.dirname(path)) == "game"

        # Re-running is idempotent and the file can be removed cleanly.
        h.translate(root, project="Activate")
        assert activate.is_active(root)
        assert activate.remove_language_switch(root)
        assert not activate.is_active(root)
    finally:
        h.close()


def test_activation_can_be_turned_off():
    from renpy_translator import activate
    h = _Harness()
    try:
        root = h.game("NoActivate-1.0_", V1)
        state = pipeline.JobState()
        cfg = config.AppConfig(model="dummy")
        cfg.activate_language = False
        pipeline.run_translation(
            state, root, "vietnamese", cfg, "g", [], "guide",
            extractor.extract(root), project="NoActivate")
        assert not activate.is_active(root), "must respect the setting"
    finally:
        h.close()


def test_font_is_installed_and_wired_into_the_switch():
    """A translation with no suitable font renders as blank accents."""
    from renpy_translator import activate, fonts
    h = _Harness()
    try:
        root = h.game("Fonted-1.0_", V1)
        state = pipeline.JobState()
        cfg = config.AppConfig(model="dummy")
        pipeline.run_translation(
            state, root, "vietnamese", cfg, "g", [], "guide",
            extractor.extract(root), project="Fonted")

        summary = state.snapshot()["summary"]
        font_rel = summary.get("font")
        if font_rel is None:
            # No system font on this machine covers Vietnamese; the run must
            # still succeed and must say so rather than silently shipping
            # unreadable text.
            assert any("No font covering" in l for l in state.snapshot()["log"])
            return

        # The font file really landed inside the game.
        installed = os.path.join(root, "game", *font_rel.split("/"))
        assert os.path.isfile(installed), installed
        assert fonts.supports_language(installed, "vietnamese")

        # And the switch file tells Ren'Py to use it for this language only.
        text = open(activate.switch_path(root), encoding="utf-8").read()
        assert 'translate vietnamese python:' in text
        assert 'translate vietnamese style default:' in text
        assert font_rel in text
    finally:
        h.close()


def test_font_checker_rejects_a_font_without_vietnamese():
    """The checker must catch the exact failure the user hit."""
    from renpy_translator import fonts
    import glob
    # Vera/DejaVu are handy stand-ins: one lacks Vietnamese, one has it.
    lacking = glob.glob("/usr/**/reportlab/fonts/Vera.ttf", recursive=True)
    covering = glob.glob("/usr/share/fonts/**/DejaVuSans.ttf", recursive=True)
    if not lacking or not covering:
        return  # font set not available on this machine
    assert not fonts.supports_language(lacking[0], "vietnamese")
    missing = fonts.missing_characters(lacking[0], "vietnamese")
    assert "ằ" in missing and "ơ" in missing, missing
    assert fonts.supports_language(covering[0], "vietnamese")


def test_project_name_ignores_version_suffix():
    s = memory_mod.suggest_project_name
    assert s("/games/MyGame-0.7.2-pc") == "MyGame"
    assert s("/games/Corrupted_Hearts-v1.4-win") == "Corrupted_Hearts"
    assert s("/games/PlainName") == "PlainName"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print("PASS", fn.__name__)
    print("\n%d/%d tests passed." % (len(fns), len(fns)))
