"""Translation orchestration: memory reuse, de-duplication, concurrency."""

from __future__ import annotations

import os
import threading
import time
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field

from . import activate as activate_mod
from . import fonts as fonts_mod
from . import memory as memory_mod
from .extractor import ExtractResult, StringUnit
from .tlgen import write_tl_files
from .translator import OpenAICompatClient, build_system_prompt, translate_items

# How often the translation memory is flushed to disk during a long run.
AUTOSAVE_SECONDS = 20


@dataclass
class JobState:
    status: str = "idle"          # idle|running|done|error|cancelled
    total: int = 0                # all units in the game
    completed: int = 0            # units resolved (reused + translated)
    failed: int = 0
    reused: int = 0               # units filled from translation memory
    unique_total: int = 0         # distinct lines actually sent to the model
    unique_done: int = 0
    started_at: float = 0.0
    message: str = ""
    log: list = field(default_factory=list)
    summary: dict = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    _cancel: threading.Event = field(default_factory=threading.Event, repr=False)

    def add_log(self, line: str):
        with self._lock:
            self.log.append("[{}] {}".format(time.strftime("%H:%M:%S"), line))
            self.log = self.log[-300:]

    def snapshot(self) -> dict:
        with self._lock:
            rate = 0.0
            eta = 0
            if self.started_at and self.unique_done:
                elapsed = max(0.001, time.time() - self.started_at)
                rate = self.unique_done / elapsed * 60.0        # lines per minute
                left = max(0, self.unique_total - self.unique_done)
                if rate > 0:
                    eta = int(left / (rate / 60.0))
            return {
                "status": self.status,
                "total": self.total,
                "completed": self.completed,
                "failed": self.failed,
                "reused": self.reused,
                "unique_total": self.unique_total,
                "unique_done": self.unique_done,
                "rate_per_min": round(rate, 1),
                "eta_seconds": eta,
                "message": self.message,
                "log": list(self.log[-120:]),
                "summary": dict(self.summary),
            }

    def cancel(self):
        self._cancel.set()

    @property
    def cancelled(self) -> bool:
        return self._cancel.is_set()


def _chunks(seq, size):
    for i in range(0, len(seq), size):
        yield i, seq[i:i + size]


def _speaker_for(unit) -> str:
    """Human-readable speaker, used as context in the prompt."""
    if isinstance(unit, StringUnit):
        return "UI / menu choice" if unit.kind == "menu" else "UI text"
    return unit.speaker or "Narrator"


def _memory_key_speaker(unit) -> str:
    """Stable speaker key used by the translation memory."""
    if isinstance(unit, StringUnit):
        return ""
    return memory_mod.speaker_key_from_prefix(unit.prefix)


def all_units(result: ExtractResult) -> list:
    return list(result.dialogues) + list(result.strings)


def apply_memory(result: ExtractResult, mem) -> tuple:
    """Fill in translations already known. Returns (reused, pending)."""
    reused, pending = 0, []
    for unit in all_units(result):
        hit = mem.get(_memory_key_speaker(unit), unit.source_text)
        if hit:
            unit.translation = hit
            reused += 1
        else:
            pending.append(unit)
    return reused, pending


def group_duplicates(units) -> "OrderedDict":
    """Group units that share a speaker and source text.

    Visual novels repeat a lot of text ("...", "Yes", stock reactions, repeated
    narration). Identical lines get an identical translation anyway, so each
    distinct line is sent to the model once and the answer is copied to every
    occurrence. On a real game this removes a large slice of the work.
    """
    groups = OrderedDict()
    for unit in units:
        key = (_memory_key_speaker(unit), unit.source_text)
        groups.setdefault(key, []).append(unit)
    return groups


def plan_translation(result: ExtractResult, project: str, language: str,
                     game_root: str = None) -> dict:
    """Preview how much of this game is already covered by memory."""
    mem = memory_mod.TranslationMemory(project, language).load()
    imported = 0
    if game_root:
        imported = memory_mod.import_from_tl(mem, game_root, language,
                                             overwrite=False)
    units = all_units(result)
    pending = [u for u in units
               if not mem.get(_memory_key_speaker(u), u.source_text)]
    known = len(units) - len(pending)
    unique_new = len(group_duplicates(pending))
    return {
        "total": len(units),
        "reused": known,
        "new": len(pending),
        "unique_new": unique_new,
        "memory_size": len(mem),
        "imported_from_tl": imported,
    }


def run_translation(state: JobState, game_root: str, language: str, cfg,
                    description: str, genres: list, bible_text: str,
                    result: ExtractResult, project: str = "") -> None:
    """Translate what is new, reuse what is known, then write tl files."""
    state.status = "running"
    state.failed = 0
    state.completed = 0
    state.reused = 0
    state.started_at = time.time()

    project = project or memory_mod.suggest_project_name(game_root)
    mem = memory_mod.TranslationMemory(project, language).load()
    state.add_log("Translation memory '{}' loaded: {} saved line(s).".format(
        project, len(mem)))

    # Recover any previous work still sitting in tl/ files. The tl folder is
    # regenerated from memory on every run, so anything that differs there is a
    # newer hand edit by the user: it must win over the stored value.
    imported = memory_mod.import_from_tl(mem, game_root, language, overwrite=True)
    if imported:
        state.add_log(
            "Recovered {} line(s) from the existing tl/{} folder.".format(
                imported, language))

    units = all_units(result)
    state.total = len(units)
    if not units:
        state.status = "done"
        state.message = "Nothing to translate."
        return

    reused, pending = apply_memory(result, mem)
    state.reused = reused
    state.completed = reused
    if reused:
        state.add_log("Reusing {} line(s) already translated. {} new line(s) "
                      "to do.".format(reused, len(pending)))

    if not pending:
        state.add_log("Nothing new in this version. Rebuilding tl files...")
        _finish(state, game_root, language, result, mem, project, cfg)
        return

    groups = group_duplicates(pending)
    keys = list(groups.keys())
    state.unique_total = len(keys)
    duplicates = len(pending) - len(keys)
    if duplicates:
        state.add_log(
            "{} of the {} new line(s) are repeats; only {} distinct line(s) "
            "will be sent.".format(duplicates, len(pending), len(keys)))

    system_prompt = build_system_prompt(language, description, genres, bible_text)
    client = OpenAICompatClient(
        cfg.api_base, cfg.api_key, cfg.model,
        temperature=cfg.temperature, timeout=cfg.request_timeout,
        max_retries=cfg.max_retries,
    )
    state.add_log(
        "Translating {} distinct line(s) into {} with '{}' "
        "({} per request, {} in parallel).".format(
            len(keys), language, cfg.model or "(unset)",
            cfg.batch_size, cfg.concurrency))

    batches = {}
    for start, chunk_keys in _chunks(keys, cfg.batch_size):
        items = []
        for j, key in enumerate(chunk_keys):
            first = groups[key][0]
            items.append({"id": j, "speaker": _speaker_for(first),
                          "text": key[1]})
        batches[start] = (chunk_keys, items)

    def work(start):
        chunk_keys, items = batches[start]
        if state.cancelled:
            return start, {}, None
        try:
            return start, translate_items(client, system_prompt, items,
                                          log=state.add_log), None
        except Exception as e:  # noqa: BLE001 - surface to UI
            return start, {}, str(e)

    last_save = [time.time()]

    def maybe_autosave():
        """Flush memory periodically so a long run never loses finished work."""
        if time.time() - last_save[0] < AUTOSAVE_SECONDS:
            return
        last_save[0] = time.time()
        try:
            mem.save()
        except OSError:
            pass

    with ThreadPoolExecutor(max_workers=max(1, cfg.concurrency)) as ex:
        futures = [ex.submit(work, start) for start in batches]
        for fut in as_completed(futures):
            start, mapping, err = fut.result()
            chunk_keys, _items = batches[start]
            resolved_units = 0
            if err:
                state.add_log("Batch at #{} failed: {}".format(start, err))
            else:
                for local, text in mapping.items():
                    if not (0 <= local < len(chunk_keys)):
                        continue
                    key = chunk_keys[local]
                    for unit in groups[key]:
                        unit.translation = text
                        resolved_units += 1
                    mem.put(key[0], key[1], text)

            done_keys = len([k for k in chunk_keys if groups[k][0].translation])
            missing = len(chunk_keys) - done_keys
            unresolved_units = sum(
                len(groups[k]) for k in chunk_keys if not groups[k][0].translation)
            if missing:
                state.add_log(
                    "{} line(s) in this batch could not be translated; they "
                    "stay in English and are retried next run.".format(missing))

            with state._lock:
                state.unique_done += len(chunk_keys)
                state.completed += resolved_units + unresolved_units
                state.failed += unresolved_units
                state.message = "{}/{} lines ({} reused)".format(
                    state.completed, state.total, state.reused)
            maybe_autosave()
            if state.cancelled:
                break

    if state.cancelled:
        state.status = "cancelled"
        state.add_log("Cancelled. Saving what is done so far...")

    _finish(state, game_root, language, result, mem, project, cfg)


def _resolve_font(state: JobState, game_root, language, cfg):
    """Pick and install a font that can actually render the language.

    The game's own font usually has no glyphs for Vietnamese, which makes the
    finished translation look broken even though the text is correct.
    """
    chosen = (getattr(cfg, "font_path", "") or "").strip()
    if chosen:
        if not os.path.isfile(chosen):
            state.add_log("Chosen font not found: " + chosen)
            chosen = ""
        elif not fonts_mod.supports_language(chosen, language):
            missing = "".join(fonts_mod.missing_characters(chosen, language)[:10])
            state.add_log(
                "Chosen font cannot display {} (missing {}); looking for "
                "another.".format(language, missing))
            chosen = ""
    if not chosen and getattr(cfg, "auto_font", True):
        chosen = fonts_mod.find_system_font(language) or ""
        if chosen:
            state.add_log("Using system font: " + os.path.basename(chosen))
    if not chosen:
        state.add_log(
            "No font covering {} was found. The translation will show blank "
            "characters until you pick a font in step 4.".format(language))
        return None
    try:
        rel = fonts_mod.install_font(game_root, chosen)
    except OSError as e:
        state.add_log("Could not copy the font into the game: " + str(e))
        return None
    state.add_log("Font installed into the game: " + rel)
    return rel


def _finish(state: JobState, game_root, language, result, mem, project, cfg=None):
    """Persist memory first, then write the tl files."""
    try:
        mem.save()
        state.add_log("Translation memory saved ({} line(s) total).".format(len(mem)))
    except OSError as e:
        state.add_log("Warning: could not save translation memory: " + str(e))

    state.add_log("Writing Ren'Py tl/{} files...".format(language))
    summary = write_tl_files(game_root, language, result)
    summary["project"] = project
    summary["memory_size"] = len(mem)
    summary["reused"] = state.reused
    state.summary = summary
    state.add_log("Wrote {} file(s) to {}".format(
        summary["files_written"], summary["tl_root"]))

    # Writing tl/ is not enough: Ren'Py only reads it once the language is
    # selected, and most released games have no language selector.
    if getattr(cfg, "activate_language", True):
        font_rel = _resolve_font(state, game_root, language, cfg)
        summary["font"] = font_rel
        try:
            info = activate_mod.write_language_switch(game_root, language, font_rel)
            summary["activated"] = True
            summary["switch_file"] = info["path"]
            state.add_log(
                "Language activated in the game ({}). Press ALT+L in game to "
                "toggle back to English.".format(
                    activate_mod.FILENAME))
        except OSError as e:
            summary["activated"] = False
            state.add_log("Could not write the language switch file: " + str(e))
    else:
        summary["activated"] = False
        state.add_log("Language switch file not written (disabled in settings). "
                      "Select the language from the game's preferences.")
    if state.status != "cancelled":
        state.status = "done"
    if state.started_at:
        mins = (time.time() - state.started_at) / 60.0
        state.add_log("Finished in {:.1f} minute(s).".format(mins))
    done = state.total - state.failed
    state.message = "Done. {} line(s) translated ({} reused), {} need review.".format(
        done, state.reused, state.failed)
