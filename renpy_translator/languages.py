"""The languages this tool can translate into, and what each one needs.

Adding a language is not just adding a name to a dropdown. Each one differs in
three ways that decide whether the result is readable:

* **Glyphs.** A font that renders English fine may have nothing for Thai,
  Arabic or Vietnamese tone marks. ``test_chars`` are the characters a font
  must actually contain, verified against the font's cmap table.
* **Line breaking.** Thai and Chinese do not put spaces between words, so
  Ren'Py needs the Unicode/CJK breaking algorithm or text runs off the box.
  ``line_break`` maps to Ren'Py's ``language`` style property.
* **Forms of address.** This is the whole point of the tool. Most languages
  encode the relationship between speakers, and a translation that ignores it
  sounds wrong even when every word is correct. ``address_note`` goes into the
  prompt.

Ren'Py language names double as folder names under game/tl/, so each key is a
plain identifier.
"""

from __future__ import annotations

# Line-break values accepted by Ren'Py's `language` style property, from
# renpy/text/text.py: unicode, eastasian, thaic90, korean-with-spaces, western,
# japanese-loose, japanese-normal, japanese-strict, anywhere.

LANGUAGES = {
    # ---- East and South-East Asia ------------------------------------
    "vietnamese": {
        "english": "Vietnamese", "native": "Tiếng Việt", "script": "latin",
        "line_break": "western", "rtl": False,
        "test_chars": "ăâđêôơưĂÂĐÊÔƠƯằắẳẵặầấẩẫậềếểễệồốổỗộờớởỡợừứửữựỳýỷỹỵ",
        "address_note":
            "Vietnamese pronouns encode age, gender and relationship. Choose "
            "from anh/chị/em/con/cháu/ông/bà/chú/cô and match them to each "
            "pair of speakers. Never fall back on the neutral bạn/tôi between "
            "people who are close.",
    },
    "japanese": {
        "english": "Japanese", "native": "日本語", "script": "cjk_ja",
        "line_break": "japanese-normal", "rtl": False,
        "test_chars": "あいうえおアイウエオ日本語私",
        "address_note":
            "Use the right politeness level (keigo, teineigo, plain form) and "
            "honorifics (-san, -chan, -kun, -sama, or none) for each pair. "
            "Pick pronouns (watashi, boku, ore, atashi) to fit the speaker.",
    },
    "korean": {
        "english": "Korean", "native": "한국어", "script": "cjk_ko",
        "line_break": "korean-with-spaces", "rtl": False,
        "test_chars": "한국어안녕하세요글",
        "address_note":
            "Choose the speech level for each pair: 존댓말 (-요/-습니다) or 반말. "
            "Use titles such as 오빠/언니/형/누나/선배/씨 where the relationship "
            "calls for them.",
    },
    "simplified_chinese": {
        "english": "Chinese (Simplified)", "native": "简体中文",
        "script": "cjk_zh_hans", "line_break": "eastasian", "rtl": False,
        "test_chars": "你好世界这们说讲实国爱",
        "address_note":
            "Choose 你 or 您 by relationship, and use kinship terms "
            "(哥/姐/叔/阿姨) the way a native speaker would.",
    },
    "traditional_chinese": {
        "english": "Chinese (Traditional)", "native": "繁體中文",
        "script": "cjk_zh_hant", "line_break": "eastasian", "rtl": False,
        "test_chars": "你好世界這們說講實國愛",
        "address_note":
            "Use Taiwan-style Traditional Chinese wording. Choose 你 or 您 by "
            "relationship and use kinship terms naturally.",
    },
    "thai": {
        "english": "Thai", "native": "ไทย", "script": "thai",
        "line_break": "unicode", "rtl": False,
        "test_chars": "กขคงจฉชญฐณสวัสดีครับค่ะเแโใไ",
        "address_note":
            "Match the politeness particles (ครับ / ค่ะ / จ้ะ) to the speaker's "
            "gender and the register. Choose pronouns (ผม/ฉัน/เรา/กู/มึง) by "
            "closeness and status.",
    },
    "indonesian": {
        "english": "Indonesian", "native": "Bahasa Indonesia", "script": "latin",
        "line_break": "western", "rtl": False, "test_chars": "aeiou",
        "address_note":
            "Choose kamu / anda / lu by closeness, and use kinship terms "
            "(mas, mbak, kak, om, tante) where a native speaker would.",
    },
    "filipino": {
        "english": "Filipino", "native": "Filipino", "script": "latin",
        "line_break": "western", "rtl": False, "test_chars": "ñÑaeiou",
        "address_note":
            "Use po/opo and kuya/ate/tito/tita where respect or closeness "
            "calls for it.",
    },
    # ---- South Asia ---------------------------------------------------
    "hindi": {
        "english": "Hindi", "native": "हिन्दी", "script": "devanagari",
        "line_break": "unicode", "rtl": False,
        "test_chars": "नमस्तेअआइईकखगघ",
        "address_note":
            "Choose तू / तुम / आप by intimacy and respect, and keep it "
            "consistent for each pair of speakers.",
    },
    "bengali": {
        "english": "Bengali", "native": "বাংলা", "script": "bengali",
        "line_break": "unicode", "rtl": False,
        "test_chars": "নমস্কারঅআইঈকখগঘ",
        "address_note":
            "Choose তুই / তুমি / আপনি by intimacy and respect, consistently "
            "per relationship.",
    },
    # ---- Right to left -------------------------------------------------
    "arabic": {
        "english": "Arabic", "native": "العربية", "script": "arabic",
        "line_break": "unicode", "rtl": True,
        "test_chars": "مرحباابتثجحخدذ",
        "address_note":
            "Match formality to the relationship, and use the correct "
            "gendered forms of address and verb agreement for each speaker.",
    },
    "persian": {
        "english": "Persian (Farsi)", "native": "فارسی", "script": "arabic",
        "line_break": "unicode", "rtl": True,
        "test_chars": "سلامپژگچابتث",
        "address_note":
            "Choose تو or شما by closeness and respect. Persian politeness "
            "(تعارف) matters: match the register to the relationship.",
    },
    "hebrew": {
        "english": "Hebrew", "native": "עברית", "script": "hebrew",
        "line_break": "unicode", "rtl": True,
        "test_chars": "שלוםאבגדהוז",
        "address_note":
            "Hebrew marks gender on verbs and adjectives. Use the correct "
            "gendered forms for who is speaking and who is addressed.",
    },
    "urdu": {
        "english": "Urdu", "native": "اردو", "script": "arabic",
        "line_break": "unicode", "rtl": True,
        "test_chars": "سلامٹڈڑژگچھ",
        "address_note":
            "Choose تو / تم / آپ by intimacy and respect, consistently per "
            "relationship.",
    },
    # ---- Europe and the Americas ---------------------------------------
    "spanish": {
        "english": "Spanish", "native": "Español", "script": "latin",
        "line_break": "western", "rtl": False, "test_chars": "áéíóúüñ¿¡",
        "address_note":
            "Choose tú / usted / vos by closeness and respect, and keep it "
            "consistent for each pair.",
    },
    "portuguese": {
        "english": "Portuguese (Brazil)", "native": "Português", "script": "latin",
        "line_break": "western", "rtl": False, "test_chars": "áâãçéêíóôõú",
        "address_note":
            "Choose você / tu / o senhor by closeness and respect, in "
            "Brazilian usage.",
    },
    "french": {
        "english": "French", "native": "Français", "script": "latin",
        "line_break": "western", "rtl": False, "test_chars": "àâçéèêëîïôùûü",
        "address_note":
            "Choose tu or vous per pair of speakers and never switch without "
            "a reason in the story.",
    },
    "german": {
        "english": "German", "native": "Deutsch", "script": "latin",
        "line_break": "western", "rtl": False, "test_chars": "äöüßÄÖÜ",
        "address_note":
            "Choose du or Sie per pair of speakers and stay consistent.",
    },
    "italian": {
        "english": "Italian", "native": "Italiano", "script": "latin",
        "line_break": "western", "rtl": False, "test_chars": "àèéìòù",
        "address_note": "Choose tu or Lei by closeness and respect.",
    },
    "russian": {
        "english": "Russian", "native": "Русский", "script": "cyrillic",
        "line_break": "western", "rtl": False, "test_chars": "АБВГДЖЗИЙЛЩЭЮЯёй",
        "address_note":
            "Choose ты or вы per pair. Russian marks gender in past-tense "
            "verbs, so use the speaker's gender correctly.",
    },
    "ukrainian": {
        "english": "Ukrainian", "native": "Українська", "script": "cyrillic",
        "line_break": "western", "rtl": False, "test_chars": "ҐґЄєІіЇїАБВЖЩ",
        "address_note":
            "Choose ти or ви per pair, and match gendered verb forms to the "
            "speaker.",
    },
    "polish": {
        "english": "Polish", "native": "Polski", "script": "latin",
        "line_break": "western", "rtl": False, "test_chars": "ąćęłńóśźżĄŁŻ",
        "address_note":
            "Choose ty or the formal pan/pani, and match gendered verb forms "
            "to the speaker.",
    },
    "turkish": {
        "english": "Turkish", "native": "Türkçe", "script": "latin",
        "line_break": "western", "rtl": False, "test_chars": "çğıöşüÇĞİÖŞÜ",
        "address_note":
            "Choose sen or siz by closeness and respect, and use abi/abla/bey/"
            "hanım where a native speaker would.",
    },
    "czech": {
        "english": "Czech", "native": "Čeština", "script": "latin",
        "line_break": "western", "rtl": False, "test_chars": "áčďéěíňóřšťúůýž",
        "address_note": "Choose ty or vy per pair, and match gendered forms.",
    },
    "romanian": {
        "english": "Romanian", "native": "Română", "script": "latin",
        "line_break": "western", "rtl": False, "test_chars": "ăâîșțĂÂÎȘȚ",
        "address_note": "Choose tu or dumneavoastră by closeness and respect.",
    },
    "hungarian": {
        "english": "Hungarian", "native": "Magyar", "script": "latin",
        "line_break": "western", "rtl": False, "test_chars": "áéíóöőúüű",
        "address_note": "Choose te or ön/maga by closeness and respect.",
    },
    "dutch": {
        "english": "Dutch", "native": "Nederlands", "script": "latin",
        "line_break": "western", "rtl": False, "test_chars": "ëïéèáà",
        "address_note": "Choose je or u by closeness and respect.",
    },
    "greek": {
        "english": "Greek", "native": "Ελληνικά", "script": "greek",
        "line_break": "western", "rtl": False, "test_chars": "ΑΒΓΔΩαβγδωήίό",
        "address_note": "Choose εσύ or εσείς by closeness and respect.",
    },
    "english": {
        "english": "English", "native": "English", "script": "latin",
        "line_break": "western", "rtl": False, "test_chars": "abcABC",
        "address_note":
            "English has no formal/informal split, so carry the relationship "
            "through tone, nicknames and register instead.",
    },
}

DEFAULT = "vietnamese"


def get(key):
    return LANGUAGES.get(key)


def display_name(key) -> str:
    info = LANGUAGES.get(key)
    if not info:
        return key
    if info["native"] and info["native"] != info["english"]:
        return "{} ({})".format(info["english"], info["native"])
    return info["english"]


def test_chars(key) -> str:
    info = LANGUAGES.get(key)
    return info["test_chars"] if info else ""


def script(key) -> str:
    info = LANGUAGES.get(key)
    return info["script"] if info else "latin"


def line_break(key) -> str:
    info = LANGUAGES.get(key)
    return info["line_break"] if info else "western"


def is_rtl(key) -> bool:
    info = LANGUAGES.get(key)
    return bool(info and info["rtl"])


def address_note(key) -> str:
    info = LANGUAGES.get(key)
    return info["address_note"] if info else ""


def as_list() -> list:
    """For the UI dropdown, grouped-ish and alphabetical by English name."""
    return sorted(
        ({"key": k, "label": display_name(k), "rtl": v["rtl"],
          "script": v["script"]} for k, v in LANGUAGES.items()),
        key=lambda d: d["label"])
