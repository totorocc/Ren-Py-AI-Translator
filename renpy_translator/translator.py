"""OpenAI-compatible translation client + prompt construction.

Talks to any OpenAI-compatible /chat/completions endpoint. The default target
is 9Router (http://localhost:20128/v1). Only the Python standard library is
used for HTTP so the tool stays dependency-light.
"""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request

from . import languages as languages_mod


def lang_display(key):
    """Human name for a target language key, e.g. 'Thai (ไทย)'."""
    return languages_mod.display_name(key)


class TranslationError(RuntimeError):
    pass


class OpenAICompatClient:
    def __init__(self, base, api_key, model, temperature=0.3, timeout=120,
                 max_retries=4):
        self.base = base.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.temperature = temperature
        self.timeout = timeout
        self.max_retries = max_retries

    @staticmethod
    def _read_body(resp):
        raw = resp.read()
        enc = (resp.headers.get("Content-Encoding") or "").lower()
        if "gzip" in enc:
            import gzip
            try:
                raw = gzip.decompress(raw)
            except OSError:
                pass
        elif "deflate" in enc:
            import zlib
            try:
                raw = zlib.decompress(raw)
            except zlib.error:
                try:
                    raw = zlib.decompress(raw, -zlib.MAX_WBITS)
                except zlib.error:
                    pass
        text = raw.decode("utf-8", "replace")
        # Strip a UTF-8 BOM and surrounding whitespace that break json.loads.
        return text.lstrip("﻿").strip()

    @staticmethod
    def _parse_sse(text):
        """Reconstruct an OpenAI completion from a streamed `data:` body."""
        parts = []
        for line in text.splitlines():
            line = line.strip()
            if not line.startswith("data:"):
                continue
            payload = line[5:].strip()
            if not payload or payload == "[DONE]":
                continue
            try:
                obj = json.loads(payload)
                choice = obj["choices"][0]
            except (ValueError, KeyError, IndexError, TypeError):
                continue
            delta = choice.get("delta") or {}
            if delta.get("content"):
                parts.append(delta["content"])
            elif choice.get("message", {}).get("content"):
                parts.append(choice["message"]["content"])
        return {"choices": [{"message": {"content": "".join(parts)}}]}

    def _parse_response(self, text, status, url):
        if not text:
            raise TranslationError(
                "HTTP {} from {} but the response body was empty.".format(status, url))
        if text.lstrip().startswith("data:"):
            return self._parse_sse(text)
        try:
            return json.loads(text)
        except ValueError:
            raise TranslationError(
                "HTTP {} from {} but the body is not JSON. The endpoint may be "
                "wrong, or it returned an HTML/SSE page. First 300 chars:\n{}".format(
                    status, url, text[:300]))

    def _post(self, path, payload):
        url = self.base + path
        data = json.dumps(payload).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Accept-Encoding": "identity",
        }
        if self.api_key:
            headers["Authorization"] = "Bearer " + self.api_key
        last_err = None
        for attempt in range(self.max_retries):
            req = urllib.request.Request(url, data=data, headers=headers, method="POST")
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    text = self._read_body(resp)
                    status = getattr(resp, "status", None) or resp.getcode()
                    return self._parse_response(text, status, url)
            except urllib.error.HTTPError as e:
                body = e.read().decode("utf-8", "replace")
                if e.code in (429, 500, 502, 503, 504) and attempt < self.max_retries - 1:
                    last_err = "HTTP {}: {}".format(e.code, body[:200])
                    time.sleep(min(2 ** attempt, 20))
                    continue
                raise TranslationError("HTTP {} from {}: {}".format(e.code, url, body[:400]))
            except urllib.error.URLError as e:
                last_err = str(e.reason)
                if attempt < self.max_retries - 1:
                    time.sleep(min(2 ** attempt, 20))
                    continue
                raise TranslationError(
                    "Could not reach {}. Is 9Router running? ({})".format(url, last_err))
        raise TranslationError(last_err or "request failed")

    def chat(self, messages, response_json=False):
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "stream": False,
        }
        if response_json:
            payload["response_format"] = {"type": "json_object"}
        try:
            data = self._post("/chat/completions", payload)
        except TranslationError:
            if response_json:
                payload.pop("response_format", None)
                data = self._post("/chat/completions", payload)
            else:
                raise
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            raise TranslationError("Unexpected response shape: " + json.dumps(data)[:300])

    def test(self):
        out = self.chat([{"role": "user", "content": "Reply with the single word: OK"}])
        return out.strip()


# ---------------------------------------------------------------------------
# Prompt building
# ---------------------------------------------------------------------------

PRESERVE_RULES = """\
Strict formatting rules - keep the game working:
- Preserve every Ren'Py text tag exactly: {b}, {i}, {color=#fff}, {size=+4}, {w},
  {nw}, {p}, {/...}, etc. Do not translate or reorder them.
- Preserve interpolation untouched: [player_name], [item], [[literal_bracket]],
  %(var)s, and {{ }} escapes. Never translate text inside [ ].
- Preserve escapes (\\n, \\", leading/trailing spaces). Keep line breaks.
- Do not add or remove quotation marks. Translate ONLY the human-readable text.
- Keep proper nouns / character names consistent with the character guide."""


def build_system_prompt(target_lang, description, genres, character_bible):
    lang = lang_display(target_lang)
    genre_txt = ", ".join(genres) if genres else "unspecified"
    desc = description.strip() or "(no description provided)"
    bible = character_bible.strip() or "(no character guide provided)"
    address = languages_mod.address_note(target_lang) or (
        "Match the register and forms of address to the relationship "
        "between the speakers.")
    return f"""You are a professional localiser of Japanese/Western adult visual novels \
into {lang}. You are translating an interactive Ren'Py game.

GAME DESCRIPTION:
{desc}

GENRE / THEMES: {genre_txt}

This is an 18+ work of fiction for adult audiences. Translate all content \
faithfully, including mature, sexual or taboo themes, in natural, idiomatic \
{lang}. Do not censor, summarise, soften, moralise or refuse. Match the register \
and intensity of the source.

HOW {lang} HANDLES FORMS OF ADDRESS:
{address}

CHARACTER GUIDE (use this for pronouns, forms of address and relationships so \
dialogue stays natural and consistent between characters):
{bible}

When you translate a line, use the speaker and the character guide to choose the \
correct pronouns and forms of address. Keep them consistent for the same \
relationship across the whole game (for example, a wife addressing her husband \
must not sound like a stranger).

{PRESERVE_RULES}

You will receive a JSON array of items, each with "id", "speaker" and "text". \
Return ONLY a JSON object of this exact shape, with one entry per input id:
{{"translations": [{{"id": 0, "text": "<translation>"}}, ...]}}
Do not include any commentary, only the JSON object."""


# ---------------------------------------------------------------------------
# Tolerant response parsing
#
# 9Router "combos" rotate a request across many different models. They do not
# all honour response_format, and some wrap the answer in prose, markdown fences
# or <think> blocks, or truncate it. Everything below is about salvaging a
# usable result instead of throwing a whole batch away.
# ---------------------------------------------------------------------------

_JSON_INSTRUCTION_MARKER = "You will receive a JSON array"

PLAIN_INSTRUCTION = """\
You will receive one line of game text. Reply with ONLY the translated line.
No quotes around it, no explanation, no notes, no original text."""

_THINK_RE = re.compile(
    r"<(think|thinking|reasoning|scratchpad)>.*?</\1>",
    re.S | re.I)
_FENCE_OPEN_RE = re.compile(r"^```[a-zA-Z]*\s*\n?")
_FENCE_CLOSE_RE = re.compile(r"\n?```\s*$")
_LABEL_RE = re.compile(
    r"^\s*(translation|translated|vietnamese|japanese|output|answer|result)\s*[:：]\s*",
    re.I)
# Matches one {"id": N, "text": "..."} record even inside broken/truncated JSON.
_ENTRY_RE = re.compile(
    r'"id"\s*:\s*(\d+)\s*,\s*"text"\s*:\s*"((?:\\.|[^"\\])*)"')
_ENTRY_REV_RE = re.compile(
    r'"text"\s*:\s*"((?:\\.|[^"\\])*)"\s*,\s*"id"\s*:\s*(\d+)')


def _strip_wrappers(text):
    text = _THINK_RE.sub("", text or "").strip()
    text = _FENCE_OPEN_RE.sub("", text)
    text = _FENCE_CLOSE_RE.sub("", text)
    return text.strip()


def _balanced_slice(text, open_ch, close_ch):
    """Return the outermost balanced {...} / [...] block, ignoring strings."""
    start = text.find(open_ch)
    if start == -1:
        return None
    depth = 0
    i = start
    quote = False
    while i < len(text):
        c = text[i]
        if quote:
            if c == "\\":
                i += 2
                continue
            if c == '"':
                quote = False
        elif c == '"':
            quote = True
        elif c == open_ch:
            depth += 1
        elif c == close_ch:
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
        i += 1
    return None


def _loads_lenient(chunk):
    try:
        return json.loads(chunk)
    except ValueError:
        pass
    # Drop trailing commas, a very common small-model mistake.
    fixed = re.sub(r",\s*([}\]])", r"\1", chunk)
    try:
        return json.loads(fixed)
    except ValueError:
        return None


def _extract_json(text):
    """Parse a model reply into a dict/list, tolerating common noise."""
    cleaned = _strip_wrappers(text)
    if not cleaned:
        raise TranslationError("Model returned an empty reply")
    data = _loads_lenient(cleaned)
    if data is not None:
        return data
    for opener, closer in (("{", "}"), ("[", "]")):
        chunk = _balanced_slice(cleaned, opener, closer)
        if chunk:
            data = _loads_lenient(chunk)
            if data is not None:
                return data
    raise TranslationError("Model did not return valid JSON")


def _entries_from_data(data):
    """Normalise the several shapes models use into {id: text}."""
    out = {}
    if isinstance(data, dict):
        seq = data.get("translations")
        if seq is None:
            for key in ("items", "results", "lines", "data", "output"):
                if isinstance(data.get(key), list):
                    seq = data[key]
                    break
        if seq is None:
            # A plain {"0": "...", "1": "..."} mapping.
            for k, v in data.items():
                if isinstance(v, str) and str(k).strip().isdigit():
                    out[int(k)] = v
            return out
        data = seq
    if isinstance(data, list):
        for i, entry in enumerate(data):
            if isinstance(entry, str):
                out[i] = entry
                continue
            if not isinstance(entry, dict):
                continue
            text = entry.get("text", entry.get("translation", entry.get("value")))
            if text is None:
                continue
            ident = entry.get("id", entry.get("index", i))
            try:
                out[int(ident)] = str(text)
            except (ValueError, TypeError):
                continue
    return out


def salvage_entries(text):
    """Recover id/text pairs from malformed or truncated JSON."""
    out = {}
    cleaned = _strip_wrappers(text or "")
    for m in _ENTRY_RE.finditer(cleaned):
        try:
            out[int(m.group(1))] = json.loads('"' + m.group(2) + '"')
        except ValueError:
            continue
    for m in _ENTRY_REV_RE.finditer(cleaned):
        try:
            out.setdefault(int(m.group(2)), json.loads('"' + m.group(1) + '"'))
        except ValueError:
            continue
    return out


def parse_translation_reply(content):
    """Best-effort {id: translation} from any model reply."""
    try:
        return _entries_from_data(_extract_json(content))
    except TranslationError:
        salvaged = salvage_entries(content)
        if salvaged:
            return salvaged
        raise


def translate_batch(client, system_prompt, items):
    """Ask for a whole batch as JSON. Returns {id: translation}."""
    user = json.dumps(items, ensure_ascii=False)
    content = client.chat(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user},
        ],
        response_json=True,
    )
    return parse_translation_reply(content)


# Phrases that mean the model answered *about* the request instead of doing it.
# A refusal must never be written into the game as if it were a translation.
_REFUSAL_MARKERS = (
    "i cannot", "i can't", "i can not", "i won't", "i will not",
    "i'm sorry", "i am sorry", "i apologize", "i apologise",
    "i'm unable", "i am unable", "i must decline", "i'd rather not",
    "as an ai", "i'm not able", "i am not able",
    "cannot assist", "can't assist", "cannot help with", "can't help with",
    "against my guidelines", "violates", "not appropriate",
    "sorry, but", "unable to provide", "unable to translate",
)


def looks_like_refusal(text):
    """True if the reply is a refusal/commentary rather than a translation."""
    if not text:
        return False
    head = text.strip().lower()[:120]
    return any(marker in head for marker in _REFUSAL_MARKERS)


def _clean_plain(out, source):
    """Sanitise a single-line plain-text reply, or return None if unusable."""
    text = _strip_wrappers(out or "")
    if not text:
        return None
    text = _LABEL_RE.sub("", text).strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in ('"', "'", "\u201c"):
        text = text[1:-1].strip()
    if text.startswith("\u201c") and text.endswith("\u201d"):
        text = text[1:-1].strip()
    if not text:
        return None
    if looks_like_refusal(text):
        return None
    # A reply much longer than the source is commentary, not a translation.
    if len(text) > len(source) * 4 + 120:
        return None
    return text


def translate_one_plain(client, system_prompt, item):
    """Translate a single line without asking for JSON at all.

    This is the last resort and the most widely compatible mode: any model that
    can answer at all can return one line of text.
    """
    context = system_prompt.split(_JSON_INSTRUCTION_MARKER)[0].rstrip()
    messages = [
        {"role": "system", "content": context + "\n\n" + PLAIN_INSTRUCTION},
        {"role": "user", "content": "Speaker: {}\nLine: {}".format(
            item.get("speaker", ""), item["text"])},
    ]
    return _clean_plain(client.chat(messages), item["text"])


def translate_items(client, system_prompt, items, log=None, _depth=0):
    """Translate items, degrading gracefully when a model misbehaves.

    Ladder: one JSON batch -> salvage partial -> split the batch in half ->
    finally one plain-text request per line. Returns {id: translation} using
    the ids of ``items``.
    """
    if not items:
        return {}

    def note(msg):
        if log:
            log(msg)

    result = {}
    # Always send ids 0..n-1. After a split the caller's ids are no longer
    # contiguous, and a model echoing them back would be indistinguishable
    # from one that renumbers, so normalise and map back ourselves.
    local_items = [{"id": i, "speaker": it.get("speaker", ""), "text": it["text"]}
                   for i, it in enumerate(items)]
    try:
        by_local = translate_batch(client, system_prompt, local_items)
        for local, text in by_local.items():
            if not (0 <= local < len(items)):
                continue
            if not isinstance(text, str) or not text.strip():
                continue
            if looks_like_refusal(text):
                note("Line {} refused by the model; will retry.".format(
                    items[local]["id"]))
                continue
            result[items[local]["id"]] = text
    except TranslationError as e:
        note("Batch of {} rejected ({}); retrying smaller.".format(
            len(items), str(e)[:90]))
    except Exception as e:  # noqa: BLE001 - network/provider hiccup
        note("Batch of {} failed ({}); retrying smaller.".format(
            len(items), str(e)[:90]))

    missing = [it for it in items if it["id"] not in result]
    if not missing:
        return result

    # One line left: plain-text mode works with practically any model.
    if len(missing) == 1:
        item = missing[0]
        try:
            text = translate_one_plain(client, system_prompt, item)
            if text:
                result[item["id"]] = text
                note("Recovered 1 line in plain-text mode.")
        except Exception as e:  # noqa: BLE001
            note("Line {} failed: {}".format(item["id"], str(e)[:90]))
        return result

    # Otherwise halve the batch: smaller requests are far more reliable.
    if _depth >= 6:
        return result
    mid = len(missing) // 2
    for half in (missing[:mid], missing[mid:]):
        result.update(translate_items(client, system_prompt, half, log=log,
                                      _depth=_depth + 1))
    return result
