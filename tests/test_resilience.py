"""Resilience against models that do not return clean JSON.

9Router "combos" rotate each request across different models. Some ignore
response_format, wrap the answer in prose or <think> blocks, truncate it, or
refuse. A single bad reply must never cost a whole batch of dialogue.

Run:  python -m tests.test_resilience
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from renpy_translator import translator  # noqa: E402
from renpy_translator.translator import (  # noqa: E402
    TranslationError, looks_like_refusal, parse_translation_reply,
    translate_items,
)

PROMPT = ("You are a localiser.\n\n"
          "You will receive a JSON array of items, each with \"id\".")


def _items(n):
    return [{"id": i, "speaker": "e", "text": "Line %d." % i} for i in range(n)]


class FakeClient:
    """A model whose behaviour we can make as awkward as a real combo."""

    def __init__(self, mode, max_batch=99, refuse_ids=(), refuse_plain=False):
        self.mode = mode
        self.max_batch = max_batch
        self.refuse_ids = set(refuse_ids)
        self.refuse_plain = refuse_plain
        self.json_calls = 0
        self.plain_calls = 0

    def chat(self, messages, response_json=False):
        user = messages[-1]["content"]
        if response_json:
            self.json_calls += 1
            items = json.loads(user)
            if len(items) > self.max_batch:
                return "I have translated the lines for you, hope that helps."
            body = [{"id": i["id"], "text": "VI-" + i["text"]}
                    for i in items if i["id"] not in self.refuse_ids]
            for i in items:
                if i["id"] in self.refuse_ids:
                    body.append({"id": i["id"],
                                 "text": "I'm sorry, I cannot translate that."})
            payload = json.dumps({"translations": body}, ensure_ascii=False)
            if self.mode == "fenced":
                return "```json\n" + payload + "\n```"
            if self.mode == "chatty":
                return "Sure! Here you go:\n" + payload + "\nLet me know."
            if self.mode == "truncated":
                return payload[:-12]
            if self.mode == "never_json":
                return "Here are the translations, written out for you."
            return payload
        # plain-text mode
        self.plain_calls += 1
        line = user.split("Line: ", 1)[1].strip()
        if self.refuse_plain:
            return "I'm sorry, I cannot translate that."
        return "VI-" + line


def test_messy_but_valid_replies_are_parsed():
    for mode in ("plain", "fenced", "chatty", "truncated"):
        client = FakeClient(mode)
        got = translate_items(client, PROMPT, _items(4))
        assert len(got) == 4, (mode, got)
        assert got[0] == "VI-Line 0.", (mode, got)


def test_big_batch_rejected_is_recovered_by_splitting():
    # Model only copes with 2 lines at a time; ladder must halve until it fits.
    client = FakeClient("plain", max_batch=2)
    logs = []
    got = translate_items(client, PROMPT, _items(8), log=logs.append)
    assert len(got) == 8, got
    assert all(got[i] == "VI-Line %d." % i for i in range(8))
    assert client.plain_calls == 0, "splitting should have been enough"
    assert any("retrying smaller" in l for l in logs), logs


def test_model_that_never_returns_json_falls_back_to_plain_text():
    client = FakeClient("never_json")
    got = translate_items(client, PROMPT, _items(4))
    assert len(got) == 4, got
    assert client.plain_calls == 4, client.plain_calls
    assert got[3] == "VI-Line 3."


def test_refusal_in_a_batch_is_retried_and_recovered():
    """One model refusing must not lose the line: the ladder retries it."""
    client = FakeClient("plain", refuse_ids={1})
    got = translate_items(client, PROMPT, _items(3))
    assert len(got) == 3, got
    assert got[1] == "VI-Line 1.", "refused line should be recovered on retry"
    assert not any(looks_like_refusal(v) for v in got.values())


def test_line_refused_everywhere_is_left_untranslated():
    """If every attempt refuses, write nothing rather than the refusal text."""
    client = FakeClient("plain", refuse_ids={1}, refuse_plain=True)
    got = translate_items(client, PROMPT, _items(3))
    assert 1 not in got, got          # stays English, retried on the next run
    assert got[0] == "VI-Line 0." and got[2] == "VI-Line 2."
    assert not any(looks_like_refusal(v) for v in got.values())


def test_partial_json_keeps_what_parsed():
    reply = ('{"translations":[{"id":0,"text":"Chào anh"},'
             '{"id":1,"text":"Em nhớ')          # truncated mid-string
    got = parse_translation_reply(reply)
    assert got.get(0) == "Chào anh", got


def test_unusable_reply_still_raises():
    for junk in ("I will not do that.", "   "):
        try:
            parse_translation_reply(junk)
        except TranslationError:
            continue
        raise AssertionError("should have raised for %r" % junk)


def test_renpy_tags_and_interpolation_survive_parsing():
    reply = ('{"translations":[{"id":0,'
             '"text":"Em vui {b}lắm{/b}, [player_name]!\\nThật đấy."}]}')
    got = parse_translation_reply(reply)
    assert got[0] == "Em vui {b}lắm{/b}, [player_name]!\nThật đấy."


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print("PASS", fn.__name__)
    print("\n%d/%d tests passed." % (len(fns), len(fns)))
