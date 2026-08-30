"""pywebview JS API bridge between the HTML UI and the Python backend."""

from __future__ import annotations

import os
import threading
import traceback

from . import config as config_mod
from . import extractor as extractor_mod
from . import fonts as fonts_mod
from . import languages as languages_mod
from . import rpa as rpa_mod
from .characters import build_character_bible, render_bible
from . import memory as memory_mod
from .pipeline import JobState, plan_translation, run_translation
from .translator import OpenAICompatClient, TranslationError


def _count_compiled_only(game_dir: str) -> int:
    """Count .rpyc scripts that have no matching .rpy source (need decompiling)."""
    count = 0
    for dirpath, _dirnames, filenames in os.walk(game_dir):
        parts = os.path.relpath(dirpath, game_dir).replace("\\", "/").split("/")
        if parts and parts[0] == "tl":
            continue
        names = set(filenames)
        for fn in filenames:
            if fn.endswith(".rpyc") and (fn[:-1] not in names):  # .rpyc -> .rpy
                count += 1
    return count


class Api:
    def __init__(self):
        self.window = None
        self.cfg = config_mod.load_config()
        self._extract = None
        self._game_root = None
        self._job = None
        self._thread = None
        self._dl_job = None
        self._project = ""

    # -- config ---------------------------------------------------------
    def get_config(self):
        return {"ok": True, "config": self.cfg.to_public()}

    def save_settings(self, payload):
        try:
            for key in ("api_base", "model"):
                if key in payload and isinstance(payload[key], str):
                    setattr(self.cfg, key, payload[key].strip())
            if payload.get("api_key"):
                self.cfg.api_key = payload["api_key"].strip()
            if "extract_python_strings" in payload:
                self.cfg.extract_python_strings = bool(
                    payload["extract_python_strings"])
            if "activate_language" in payload:
                self.cfg.activate_language = bool(payload["activate_language"])
            if "auto_font" in payload:
                self.cfg.auto_font = bool(payload["auto_font"])
            if "font_path" in payload and isinstance(payload["font_path"], str):
                self.cfg.font_path = payload["font_path"].strip()
            for key, cast in (("temperature", float), ("batch_size", int),
                              ("concurrency", int), ("max_retries", int),
                              ("request_timeout", int)):
                if key in payload and payload[key] not in (None, ""):
                    setattr(self.cfg, key, cast(payload[key]))
            config_mod.save_config(self.cfg)
            return {"ok": True, "config": self.cfg.to_public()}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "message": str(e)}

    def test_connection(self):
        if not self.cfg.model:
            return {"ok": False, "message": "Set a model name first."}
        client = OpenAICompatClient(
            self.cfg.api_base, self.cfg.api_key, self.cfg.model,
            temperature=0, timeout=30, max_retries=1)
        try:
            reply = client.test()
            return {"ok": True, "message": "Connected. Model replied: " + reply[:60]}
        except TranslationError as e:
            return {"ok": False, "message": str(e)}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "message": str(e)}

    # -- project --------------------------------------------------------
    def _active_window(self):
        """Resolve the live window lazily (avoids an api<->window cycle)."""
        try:
            import webview
        except ImportError:
            return self.window
        wins = getattr(webview, "windows", None)
        if wins:
            return wins[0]
        return self.window

    def pick_game_folder(self):
        try:
            import webview
            win = self._active_window()
            if win is None:
                return {"ok": False, "message": "Window is not ready yet."}
            paths = win.create_file_dialog(webview.FOLDER_DIALOG)
            if not paths:
                return {"ok": False, "cancelled": True}
            return {"ok": True, "path": paths[0]}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "message": str(e)}

    def scan_game(self, path, unpack=True):
        path = (path or "").strip()
        if not path or not os.path.isdir(path):
            return {"ok": False, "message": "Folder not found."}
        game_dir = os.path.join(path, "game")
        if not os.path.isdir(game_dir) and os.path.basename(path) != "game":
            return {"ok": False,
                    "message": "No 'game' subfolder found. Point to the game's root folder."}

        inner = extractor_mod._game_dir(path)
        notes = []

        # Step 1: unpack any .rpa archives so packed .rpy scripts become visible.
        unpack_summary = {"archives": 0, "files_extracted": 0}
        if unpack:
            try:
                unpack_summary = rpa_mod.unpack_archives(inner, only_scripts=True)
            except Exception as e:  # noqa: BLE001 - non-fatal
                notes.append("Archive unpack skipped: " + str(e))
            if unpack_summary.get("archives"):
                notes.append("Unpacked {} archive(s), {} script file(s).".format(
                    unpack_summary["archives"], unpack_summary["files_extracted"]))

        # Step 2: extract translatable units from .rpy sources.
        try:
            result = extractor_mod.extract(
                path,
                extract_python=getattr(self.cfg, "extract_python_strings", True))
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "message": "Scan failed: " + str(e),
                    "trace": traceback.format_exc()}
        self._extract = result
        self._game_root = path

        # Step 3: detect compiled-only .rpyc (no .rpy source) -> needs decompiling.
        rpyc_only = _count_compiled_only(inner)
        if rpyc_only:
            notes.append(
                "{} compiled-only .rpyc script(s) have no .rpy source. Decompile "
                "them with unrpyc (github.com/CensoredUsername/unrpyc), then "
                "re-scan to include them.".format(rpyc_only))

        chars = []
        for var, ch in sorted(result.characters.items(),
                              key=lambda kv: -kv[1].count):
            chars.append({
                "var": var,
                "name": ch.name,
                "is_narrator": ch.is_narrator,
                "count": ch.count,
                "samples": ch.samples[:5],
            })
        project = (self._project or "").strip() or \
            memory_mod.suggest_project_name(path)
        self._project = project

        python_strings = sum(1 for u in result.strings if u.kind == "python")
        if python_strings:
            notes.append(
                "{} line(s) of text are passed to Python helpers (phone "
                "messages, custom UI). They are included as string "
                "translations.".format(python_strings))

        return {
            "ok": True,
            "files": result.files_scanned,
            "dialogues": len(result.dialogues),
            "strings": len(result.strings),
            "python_strings": python_strings,
            "characters": chars,
            "archives": unpack_summary.get("archives", 0),
            "extracted_files": unpack_summary.get("files_extracted", 0),
            "rpyc_only": rpyc_only,
            "project": project,
            "note": " ".join(notes),
        }

    # -- translation memory (incremental / resume) -----------------------
    def translation_plan(self, payload):
        """How much of this game is already translated (reuse preview)."""
        if self._extract is None or not self._game_root:
            return {"ok": False, "message": "Scan a game first."}
        language = payload.get("language", "vietnamese")
        project = (payload.get("project") or self._project or "").strip()
        if not project:
            project = memory_mod.suggest_project_name(self._game_root)
        self._project = project
        try:
            plan = plan_translation(self._extract, project, language,
                                    game_root=self._game_root)
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "message": str(e)}
        plan["ok"] = True
        plan["project"] = project
        return plan

    def list_memories(self):
        try:
            return {"ok": True, "projects": memory_mod.list_projects()}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "message": str(e)}

    def import_previous_version(self, payload):
        """Merge translations from an older copy of the game into memory."""
        language = payload.get("language", "vietnamese")
        project = (payload.get("project") or self._project or "").strip()
        old_path = (payload.get("path") or "").strip()
        if not project:
            return {"ok": False, "message": "Set a project name first."}
        if not old_path:
            win = self._active_window()
            if win is None:
                return {"ok": False, "message": "Window is not ready yet."}
            try:
                import webview
                picked = win.create_file_dialog(webview.FOLDER_DIALOG)
            except Exception as e:  # noqa: BLE001
                return {"ok": False, "message": str(e)}
            if not picked:
                return {"ok": False, "cancelled": True}
            old_path = picked[0]
        if not os.path.isdir(old_path):
            return {"ok": False, "message": "Folder not found."}
        try:
            mem = memory_mod.TranslationMemory(project, language).load()
            before = len(mem)
            added = memory_mod.import_from_tl(mem, old_path, language,
                                              overwrite=False)
            mem.save()
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "message": str(e)}
        if added == 0:
            return {"ok": True, "imported": 0, "memory_size": len(mem),
                    "message": "No translated lines found in "
                               "{}/game/tl/{}.".format(
                                   os.path.basename(old_path), language)}
        return {"ok": True, "imported": added, "memory_size": len(mem),
                "before": before,
                "message": "Imported {} line(s). Memory now holds {}.".format(
                    added, len(mem))}

    # -- languages ---------------------------------------------------------
    def list_languages(self):
        """Every target language the tool knows how to handle."""
        return {"ok": True,
                "languages": languages_mod.as_list(),
                "default": languages_mod.DEFAULT}

    # -- fonts ------------------------------------------------------------
    def check_font(self, payload):
        """Report whether a font can display the target language."""
        language = payload.get("language", "vietnamese")
        path = (payload.get("path") or self.cfg.font_path or "").strip()
        if not path:
            found = fonts_mod.find_system_font(language)
            if not found:
                return {"ok": False, "auto": True,
                        "message": "No installed font covering {} was found. "
                                   "Pick a font file.".format(language)}
            info = fonts_mod.describe(found, language)
            info["path"] = found
            info["auto"] = True
            return info
        info = fonts_mod.describe(path, language)
        info["path"] = path
        info["auto"] = False
        return info

    def pick_font_file(self, payload=None):
        try:
            import webview
            win = self._active_window()
            if win is None:
                return {"ok": False, "message": "Window is not ready yet."}
            picked = win.create_file_dialog(
                webview.OPEN_DIALOG,
                file_types=("Font files (*.ttf;*.otf;*.ttc)", "All files (*.*)"))
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "message": str(e)}
        if not picked:
            return {"ok": False, "cancelled": True}
        path = picked[0]
        language = (payload or {}).get("language", "vietnamese")
        info = fonts_mod.describe(path, language)
        info["path"] = path
        return info

    # -- decompile (.rpyc) ----------------------------------------------
    def start_decompile(self):
        if not self._game_root:
            return {"ok": False, "message": "Scan a game first."}
        if self._dl_job is not None and self._dl_job.status == "running":
            return {"ok": False, "message": "Decompilation already running."}
        from . import decompile as decompile_mod
        job = JobState()
        job.status = "running"
        self._dl_job = job
        inner = extractor_mod._game_dir(self._game_root)
        url = getattr(self.cfg, "unrpyc_url", decompile_mod.DEFAULT_URL)

        def runner():
            try:
                job.add_log("Looking for compiled scripts to decompile.")
                decompile_mod.decompile_dir(inner, url=url, log=job.add_log)
                job.message = "Decompilation finished. Re-scanning..."
                job.status = "done"
            except Exception as e:  # noqa: BLE001
                job.status = "error"
                job.message = str(e)
                job.add_log("Error: " + str(e))

        t = threading.Thread(target=runner, daemon=True)
        t.start()
        return {"ok": True}

    def decompile_progress(self):
        if self._dl_job is None:
            return {"ok": True, "status": "idle"}
        snap = self._dl_job.snapshot()
        snap["ok"] = True
        return snap

    # -- characters -----------------------------------------------------
    def analyze_characters(self, payload):
        if self._extract is None:
            return {"ok": False, "message": "Scan a game first."}
        if not self.cfg.model:
            return {"ok": False, "message": "Configure the API model first."}
        language = payload.get("language", "vietnamese")
        description = payload.get("description", "")
        genres = payload.get("genres", [])
        characters = payload.get("characters") or []
        if not characters:
            characters = [
                {"var": v, "name": c.name, "count": c.count, "samples": c.samples}
                for v, c in self._extract.characters.items()
            ]
        client = OpenAICompatClient(
            self.cfg.api_base, self.cfg.api_key, self.cfg.model,
            temperature=0.2, timeout=self.cfg.request_timeout,
            max_retries=self.cfg.max_retries)
        try:
            bible = build_character_bible(client, language, description, genres, characters)
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "message": str(e)}
        return {"ok": True, "bible": bible,
                "rendered": render_bible(bible, language)}

    # -- translation ----------------------------------------------------
    def start_translation(self, payload):
        if self._extract is None or not self._game_root:
            return {"ok": False, "message": "Scan a game first."}
        if not self.cfg.model:
            return {"ok": False, "message": "Configure the API model first."}
        if self._thread and self._thread.is_alive():
            return {"ok": False, "message": "A translation is already running."}
        language = payload.get("language", "vietnamese")
        description = payload.get("description", "")
        genres = payload.get("genres", [])
        bible_text = payload.get("bible_text", "")
        project = (payload.get("project") or self._project or "").strip()
        if not project:
            project = memory_mod.suggest_project_name(self._game_root)
        self._project = project

        self._job = JobState()
        self._job.add_log("Starting translation job.")

        def runner():
            try:
                run_translation(
                    self._job, self._game_root, language, self.cfg,
                    description, genres, bible_text, self._extract,
                    project=project)
            except Exception as e:  # noqa: BLE001
                self._job.status = "error"
                self._job.message = str(e)
                self._job.add_log("Fatal error: " + str(e))

        self._thread = threading.Thread(target=runner, daemon=True)
        self._thread.start()
        return {"ok": True}

    def get_progress(self):
        if self._job is None:
            return {"ok": True, "status": "idle"}
        snap = self._job.snapshot()
        snap["ok"] = True
        return snap

    def cancel_translation(self):
        if self._job:
            self._job.cancel()
            return {"ok": True}
        return {"ok": False, "message": "No job running."}

    def open_output(self):
        if not self._game_root:
            return {"ok": False}
        target = os.path.join(self._game_root, "game", "tl")
        try:
            if os.name == "nt":
                os.startfile(target)  # type: ignore[attr-defined]
            return {"ok": True, "path": target}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "message": str(e)}
