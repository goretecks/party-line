"""Settings persisted between runs (in %APPDATA%\\VOIP Translator on Windows)."""
from __future__ import annotations

import json
import os
import sys

APP_NAME = "VOIP Translator"

DEFAULTS = {
    "model": "small",
    "only_lang": "es",          # "" = any language
    "device": "",               # "" = system default output
    "threshold": 0.84,          # voice matching strictness
    "cpu_threads": 4,
    "font_size": 19,
    "geometry": "",
}


def app_dir() -> str:
    base = os.environ.get("APPDATA") if sys.platform == "win32" else os.path.expanduser("~/.config")
    d = os.path.join(base or os.path.expanduser("~"), APP_NAME)
    os.makedirs(d, exist_ok=True)
    return d


def _path() -> str:
    return os.path.join(app_dir(), "settings.json")


def load() -> dict:
    cfg = dict(DEFAULTS)
    try:
        with open(_path(), encoding="utf-8") as f:
            cfg.update({k: v for k, v in json.load(f).items() if k in DEFAULTS})
    except (OSError, ValueError):
        pass
    return cfg


def save(cfg: dict) -> None:
    try:
        with open(_path(), "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
    except OSError:
        pass
