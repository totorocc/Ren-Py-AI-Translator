"""AI character analysis - build a 'character bible' for consistent dialogue.

The bible captures each character's gender, role, relationships and (critically)
the correct forms of address / pronouns in the target language, so that, e.g., a
wife addressing her husband in Vietnamese uses "anh"/"em" rather than the flat
"bạn"/"tôi". The result is editable by the user before translation.
"""

from __future__ import annotations

import json

from .translator import OpenAICompatClient, _extract_json, lang_display


def build_character_bible(client: OpenAICompatClient, target_lang: str,
                          description: str, genres: list,
                          characters: list) -> dict:
    """characters: list of {var, name, count, samples}. Returns a bible dict."""
    lang = lang_display(target_lang)
    genre_txt = ", ".join(genres) if genres else "unspecified"

    roster = []
    for c in characters:
        roster.append({
            "var": c.get("var"),
            "name": c.get("name"),
            "lines": c.get("count", 0),
            "samples": c.get("samples", [])[:6],
        })

    system = f"""You are a dramaturg and localisation lead preparing a {lang} \
translation of an 18+ Ren'Py visual novel. From the game description, genre and \
each character's sample lines, infer a concise character guide.

For EACH character determine: gender, approximate age band, personality / speech \
register, and their relationship to the other main characters. Then, most \
importantly, specify the correct {lang} forms of address and pronouns: how this \
character refers to themselves and how they address each significant other \
character, consistent with the relationship and the adult genre.

Return ONLY a JSON object of this shape:
{{
  "characters": [
    {{
      "var": "<variable or name>",
      "name": "<display name>",
      "gender": "male|female|other|unknown",
      "age": "<e.g. teens, 20s, 40s>",
      "role": "<their role / relationship summary>",
      "register": "<how they speak: polite, crude, shy, dominant...>",
      "address": "<in {lang}: how they call themselves and key others, e.g. 'self: em; husband Hùng: anh'>"
    }}
  ],
  "relationships": [
    {{"between": "<A> & <B>", "guidance": "<A->B and B->A {lang} pronouns / address>"}}
  ]
}}
No commentary, only JSON."""

    user = json.dumps({
        "description": description,
        "genre": genre_txt,
        "characters": roster,
    }, ensure_ascii=False)

    content = client.chat(
        [{"role": "system", "content": system},
         {"role": "user", "content": user}],
        response_json=True,
    )
    return _extract_json(content)


def render_bible(bible: dict, target_lang: str) -> str:
    """Render a bible dict into the plain-text block injected into prompts."""
    if not bible:
        return ""
    lines = []
    for c in bible.get("characters", []):
        name = c.get("name") or c.get("var") or "?"
        bits = []
        if c.get("gender"):
            bits.append(c["gender"])
        if c.get("age"):
            bits.append(c["age"])
        if c.get("role"):
            bits.append(c["role"])
        header = "- {} ({})".format(name, ", ".join(b for b in bits if b))
        lines.append(header)
        if c.get("register"):
            lines.append("    register: {}".format(c["register"]))
        if c.get("address"):
            lines.append("    address: {}".format(c["address"]))
    rels = bible.get("relationships", [])
    if rels:
        lines.append("Relationships:")
        for r in rels:
            lines.append("- {}: {}".format(
                r.get("between", "?"), r.get("guidance", "")))
    return "\n".join(lines)
