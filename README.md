# Ren'Py AI Translator

**Translate Ren'Py visual novels into 29 languages with AI, without your characters suddenly speaking to their spouse like a customer service representative.**

<p align="center">
  <img src="https://img.shields.io/badge/python-3.9%2B-blue" alt="Python 3.9+">
  <img src="https://img.shields.io/badge/languages-29-orange" alt="29 languages">
  <img src="https://img.shields.io/badge/tests-32%20passing-brightgreen" alt="Tests">
  <img src="https://img.shields.io/badge/dependencies-exactly%201-success" alt="Dependencies">
  <img src="https://img.shields.io/badge/vibes-immaculate-ff69b4" alt="Vibes">
</p>

---

## The problem, illustrated

You feed a visual novel into a generic translator. A wife says something tender to her husband of nine years. It comes out as:

> **Wife:** Hello. I am fine. And you, sir?

Congratulations, you have invented the world's most awkward marriage.

Here is the thing machine translation keeps getting wrong: **most languages encode the relationship between the speakers**, not just the meaning of the sentence.

| Language | The thing MTL always gets wrong |
|---|---|
| Vietnamese | `anh/em` between spouses, not the neutral `bạn/tôi` |
| Japanese | keigo vs plain form, and whether it is `-san`, `-chan` or nothing at all |
| Korean | 존댓말 vs 반말, plus 오빠/언니/선배 |
| Thai | ครับ / ค่ะ particles, and which of six pronouns fits |
| German | `du` or `Sie`, and never flip-flopping between them |
| Russian | `ты` or `вы`, plus gendered past-tense verbs |
| Spanish | `tú`, `usted` or `vos` depending on who and where |
| Persian | تو or شما, and the whole art of تعارف |

A generic translator sees a sentence. It does not see a relationship.

**This tool builds a character guide first**, works out who is speaking to whom, then translates every line with that in front of it. Revolutionary concept. Took the industry until 2026.

---

## Supported languages

29 targets, each with its own address rules, font requirements and line-breaking behaviour baked in:

**East & Southeast Asia** Japanese · Korean · Chinese (Simplified) · Chinese (Traditional) · Thai · Vietnamese · Indonesian · Filipino

**South Asia** Hindi · Bengali

**Right to left** Arabic · Persian (Farsi) · Hebrew · Urdu

**Europe & Americas** English · Spanish · Portuguese (BR) · French · German · Italian · Dutch · Polish · Czech · Hungarian · Romanian · Greek · Russian · Ukrainian · Turkish

Missing yours? It is one entry in `languages.py`. Genuinely, that is the whole change.

---

## What it actually does

<table>
<tr><td width="30">🧠</td><td><b>Character bible</b><br>Detects every <code>Character()</code>, profiles gender, role and relationships with AI, then proposes the correct forms of address <i>for your target language specifically</i>. You edit it. This is the single biggest quality lever, so please actually edit it.</td></tr>
<tr><td>🌏</td><td><b>Language-aware, not just language-labelled</b><br>Thai gets Unicode line breaking because Thai does not use spaces between words. Japanese gets CJK breaking rules. Arabic and Persian get <code>config.rtl</code> so the text actually reads right to left. Getting this wrong makes text run out of the dialogue box, which is a fun way to discover you shipped something broken.</td></tr>
<tr><td>📦</td><td><b>Extracts everything itself</b><br>Loose <code>.rpy</code>? Read directly. Packed in <code>.rpa</code>? Unpacked automatically. Only compiled <code>.rpyc</code> left? One button downloads unrpyc and decompiles it <b>inside the app</b>. No second tool, no terminal, no "just run this Python script bro".</td></tr>
<tr><td>📱</td><td><b>Finds the text other tools miss</b><br>Games love hiding dialogue in <code>$ phone_message(sender, "hey babe")</code>. Ren'Py itself refuses to generate translations for those. We grab them anyway. Asset paths and flags are left alone, so your <code>images/bg_694.jpg</code> does not get lovingly translated into Thai.</td></tr>
<tr><td>🧵</td><td><b>Translation memory</b><br>Game updated to v0.36 before you finished v0.35? Only the <b>new and changed</b> lines get sent. Everything else is reused instantly and for free. Your hand edits survive too, and they win over the stored version.</td></tr>
<tr><td>⚡</td><td><b>Actually fast</b><br>Duplicate lines are sent once (VNs repeat a <i>lot</i>). Requests run in parallel. Live throughput and ETA so you can watch the number go up.</td></tr>
<tr><td>🛟</td><td><b>Survives bad models</b><br>Using a router where every request hits a different model with different opinions about JSON? The parser salvages fenced JSON, prose-wrapped JSON, <code>&lt;think&gt;</code> blocks, bare arrays, trailing commas and even replies cut off mid-sentence. If that fails it splits the batch. If that fails it asks one line at a time in plain text. Something will stick.</td></tr>
<tr><td>🚫</td><td><b>Refusal detection</b><br>If a model gets shy and replies "I'm sorry, I cannot help with that", that sentence does <b>not</b> get written into your game as dialogue. It gets retried. Because that is a terrible thing for a character to say mid-scene.</td></tr>
<tr><td>🔤</td><td><b>Fonts that can actually spell</b><br>The app reads the font's <code>cmap</code> table and checks the characters your language really needs, then installs one that passes. See the horror story below.</td></tr>
<tr><td>🔌</td><td><b>Turns the translation on</b><br>Writing <code>tl/</code> files is only half the job. Most released games have no language selector, so Ren'Py happily ignores your translation forever. The app flips the switch for you.</td></tr>
</table>

---

## Requirements

- **Python 3.9+**
- **[9Router](https://9router.com)** running locally, or literally any OpenAI-compatible endpoint (OpenAI, DeepSeek, OpenRouter, Ollama, LM Studio, your cousin's GPU)
- **One** dependency: `pywebview`. That is the whole list. We are not shipping you 400 npm packages.

> **Windows:** needs the Edge WebView2 Runtime, which you already have unless your PC is haunted. If the window is blank, install the Evergreen WebView2 Runtime.

---

## Quick start

**Windows:** double-click `run.bat`. It makes a venv and installs things. Go make tea.

**macOS / Linux:**

```bash
chmod +x run.sh
./run.sh
```

**Manual, for people who like typing:**

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate    macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

---

## Using it: 5 steps, roughly 5 minutes of your attention

### 1. Project

Point at the game's **root folder** (the one containing `game/`). Hit **Scan**.

The app unpacks `.rpa` archives, counts everything, and tells you if there are compiled-only `.rpyc` files. If there are, click **Decompile inside the app** and go make more tea.

You also get a **project name** here. Keep it the same across game versions and the translation memory does its thing.

### 2. Language & context

Pick your target language. Describe the game in two or three sentences. Tag the genres.

Yes, the genre tags include NTR, Cheating, Blackmail, Corruption and friends. No, we are not going to make it weird. Tone and forms of address genuinely depend on this, and a model that thinks it is translating a cooking show will produce very confused dialogue.

### 3. Characters

Set gender where the model cannot tell, then **Generate with AI**.

You now have a character guide, written for your specific target language. **Edit it.** This is where you decide that Hana uses 반말 with her childhood friend and 존댓말 with her boss, or that Sara says تو to her sister and شما to her father-in-law. Thirty seconds here beats two hours of fixing pronouns afterwards.

### 4. API & tuning

Base URL (`http://localhost:20128/v1` for 9Router), your key, your model. Hit **Test connection**.

Then pick a speed preset:

| Preset | Lines / request | Parallel | For |
|---|---|---|---|
| Gentle | 10 | 2 | free tiers and strict rate limits |
| Balanced | 25 | 8 | most people |
| **Fast** | 40 | 16 | your own paid key, living dangerously |

Also on this screen: the **font picker** and the **turn the language on** switch. Both are on by default. Both save you from a very specific kind of sadness.

### 5. Translate

Press the button. Watch `lines/min` and the ETA. Files land in `game/tl/<language>/`.

Then **close the game completely and start it again**. Not a save reload. A full restart. Ren'Py decides the language at launch and is very stubborn about it.

Press **ALT+L** in game to toggle back to the original language if you want to compare.

---

## The Hall of Fame of Things That Went Wrong

Every entry here is a real bug that a real user hit, and every one is now fixed. Consider this section a museum.

### "My game shows English even though it said Done"

Ren'Py only reads `game/tl/<language>/` **when that language is selected**, and most released games have no language selector, so nobody can ever select it. Your translation sits there, perfect and completely ignored.

The app writes one small file, `game/zzz_rpt_language.rpy`, that sets `config.language`. This is the mechanism Ren'Py officially documents for fan translations. Delete that file to undo everything.

### "Half the letters are missing"

The translation is fine. The **font** is not. The game's pretty handwriting font has `â` and `ê` but has never heard of `ằ ơ ộ ứ ậ đ`, so those characters render as absolutely nothing. Same story for Thai, Arabic, Hindi and every CJK script, except there the entire sentence vanishes instead of just the interesting parts.

The app reads the font's actual character table, checks whether it covers your language, and installs one that does. You can also pick your own font and **Check** will tell you exactly which characters it is missing before you waste a translation run on it.

### "Thai text runs straight out of the dialogue box"

Thai does not put spaces between words. Neither does Chinese. Ren'Py's default line breaking looks for spaces, finds none, and cheerfully renders one very long line into the void.

Each language carries its own line-breaking rule (`unicode`, `japanese-normal`, `korean-with-spaces`, `western`) and it gets written into the game with the font settings. Right-to-left languages additionally get `config.rtl` turned on, because Ren'Py will not reverse anything unless you ask.

### "Batch at #140 failed: Model did not return valid JSON"

Some models return JSON. Some return JSON wrapped in markdown. Some return JSON with a friendly paragraph on top. Some return JSON that stops halfway through because they ran out of tokens mid-word. Some just describe the JSON they would have written, if only they had felt like it.

The parser handles all of that, then falls back to splitting the batch, then falls back to one plain-text request per line. A weird reply costs you one line, not twenty.

### "The game crashed with a wall of `expected statement` errors"

An early version mistook Python dictionaries for dialogue and generated syntactically invalid translation files. Now bracket depth is tracked and dict/list bodies are never mistaken for someone talking. There is a regression test named after this incident.

### "Phone messages were never translated"

They are function calls, not say statements, so Ren'Py's own extractor ignores them too. We scan `$` lines and `python:` blocks for text that reads like prose. On the game this was built against, that recovered 242 lines.

---

## How it works, for the curious

The tool reproduces Ren'Py's own translation identifier algorithm (`md5(say.get_code() + "\r\n")[:8]`, prefixed by the enclosing label) and the `old`/`new` string format. The generated files are picked up by the engine exactly like ones produced by the official SDK.

```renpy
# script.rpy:10
translate thai start_bf7424c5:

    # e "Hello, [player_name]. You're home late again."
    e "สวัสดี [player_name] วันนี้กลับดึกอีกแล้วนะ"

translate thai strings:

    old "Yes"
    new "ใช่"
```

Ren'Py tags (`{b}`, `{w}`), interpolation (`[player_name]`) and escapes are preserved. Nothing in the original game is overwritten.

### Adding a language

One dictionary entry in `renpy_translator/languages.py`:

```python
"swedish": {
    "english": "Swedish", "native": "Svenska", "script": "latin",
    "line_break": "western", "rtl": False,
    "test_chars": "åäöÅÄÖ",
    "address_note": "Swedish dropped the formal ni in ordinary speech; "
                    "carry the relationship through tone instead.",
},
```

That is it. Font selection, the prompt, the dropdown and the generated Ren'Py settings all read from there. PRs welcome, especially from people who actually speak the language.

### Project layout

```
main.py                     desktop entry point (pywebview window)
run.bat / run.sh            one-click launchers
web/index.html              the entire UI, one file, no build step
renpy_translator/
    languages.py            29 languages: glyphs, line breaking, address rules
    rpy_lex.py              Ren'Py string encode/decode + translation identifiers
    extractor.py            scan .rpy -> dialogue + strings + characters
    rpa.py                  unpack .rpa archives (RPA-2.0/3.0)
    decompile.py            in-app .rpyc decompilation via unrpyc
    tlgen.py                write game/tl/<language>/ files
    translator.py           OpenAI-compatible client + resilient parsing
    characters.py           AI character guide (forms of address)
    memory.py               translation memory (incremental re-runs)
    activate.py             in-game language switch, font, RTL, line breaking
    fonts.py                font coverage check (reads the cmap table)
    pipeline.py             de-duplication, batching, concurrency, progress
    config.py               saved settings
    api.py                  JS <-> Python bridge
tests/                      32 tests, all green, genuinely useful
```

### Tests

```bash
python -m tests.test_extract      # extraction + tl generation
python -m tests.test_memory       # incremental re-runs + de-duplication
python -m tests.test_resilience   # badly behaved models
python -m tests.test_languages    # glyphs, line breaking, reading direction
```

Every test in there exists because something broke once. They are not decorative.

---

## Honest limitations

Because a README that only brags is a sales page, not documentation.

- **Exact-match memory.** Change one comma in the source and that line is treated as new. Safe, but not clever.
- **Address rules are guidance, not grammar.** The model still has to apply them. For languages with heavy honorific systems, read the output and fix what it got wrong. Your fixes are then permanent.
- **Unusual custom statements** are skipped rather than risk generating a wrong translation identifier. Skipped text stays in the original language; it does not break the game.
- **Screen text without `_()`** is not auto-extracted. Ren'Py treats those as developer-side strings and so do we.
- **RTL is Ren'Py's implementation, not ours.** We turn it on correctly; how well it renders is up to the engine and your font.
- **Fonts have licences.** Copying a system font for personal use is fine. Bundling one into a public translation mod is a different conversation, and it is one you should have with the licence, not with me.

---

## Please translate responsibly

This tool exists for fan translation. Some obvious things:

- Get permission from the game's creator where you can. It is polite and occasionally it works.
- Do not sell someone else's game with your translation glued on.
- Many of these games are 18+. Keep them away from people who should not have them.
- Only the lines being translated are sent to the endpoint you configure. Nothing else leaves your machine. Your game folder is nobody's business, and frankly we do not want to know.

---

## ☕ Buy me a coffee

I built this because pronoun-blind machine translation made a fictional married couple sound like they had just been introduced at a conference. That kind of injustice keeps a person up at night.

If this tool saved you hours of manual editing, or rescued a translation you had already given up on, consider fuelling the next batch of languages:

<p align="center">
  <a href="https://www.buymeacoffee.com/totoroc" target="_blank">
    <img src="https://cdn.buymeacoffee.com/buttons/v2/default-yellow.png" alt="Buy Me A Coffee" height="60" width="217">
  </a>
</p>

<p align="center">
  <b><a href="https://buymeacoffee.com/totoroc">buymeacoffee.com/totoroc</a></b>
</p>

Coffee converts directly into commits. This is science. Do not look it up.

Not into coffee? A ⭐ on the repo is free and works almost as well.

---

## Contributing

**Adding your language** is the most useful thing you can do, and it is one dictionary entry (see above). If you speak it natively, your `address_note` will be better than anything I can write.

**Found a bug?** Open an issue. Include the log from the app, it is genuinely detailed and will save us both a week.

---

## License

MIT. Do what you like. If it breaks your game, you get to keep both pieces, and also a translation memory file so at least you do not have to pay for it twice.
