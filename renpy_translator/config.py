"""Persistent configuration (API endpoint, model, batching)."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass

CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".renpy_ai_translator")
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")


@dataclass
class AppConfig:
    # 9Router exposes an OpenAI-compatible API on localhost by default.
    api_base: str = "http://localhost:20128/v1"
    api_key: str = ""
    model: str = ""
    temperature: float = 0.3
    batch_size: int = 25          # distinct lines per request
    concurrency: int = 8          # parallel requests
    max_retries: int = 4
    request_timeout: int = 120
    activate_language: bool = True   # write the in-game language switch
    extract_python_strings: bool = True  # text passed to python helpers
    auto_font: bool = True           # find a font that covers the language
    font_path: str = ""              # explicit font file, if the user picked one
    unrpyc_url: str = (
        "https://github.com/CensoredUsername/unrpyc"
        "/archive/refs/heads/master.zip")

    def to_public(self) -> dict:
        """Config for the UI (api key length only, not the secret)."""
        d = asdict(self)
        d["api_key_set"] = bool(self.api_key)
        d.pop("api_key", None)
        return d


def load_config() -> AppConfig:
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            cfg = AppConfig()
            for k, v in data.items():
                if hasattr(cfg, k):
                    setattr(cfg, k, v)
            return cfg
        except (OSError, ValueError):
            pass
    return AppConfig()


def save_config(cfg: AppConfig) -> None:
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(asdict(cfg), f, indent=2)
