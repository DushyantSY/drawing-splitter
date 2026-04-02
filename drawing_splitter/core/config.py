"""
core/config.py - Settings persistence layer.
Loads settings.json from the config/ directory next to app.py,
merges with defaults, and provides save functionality.
"""

import json
import os
import copy
from typing import Any, Dict

_CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "config",
    "settings.json",
)

_DEFAULTS: Dict[str, Any] = {
    "tesseract_path": r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    "ocr_mode": "auto",          # "auto" | "always" | "never"
    "title_block": {
        "preset": "bottom-right",
        "x_start_pct": 60.0,
        "y_start_pct": 78.0,
        "x_end_pct": 100.0,
        "y_end_pct": 100.0,
    },
    "regex": {
        "drawing_number": r"([A-Z0-9]{2,}(?:-[A-Z0-9]+){4,})",
        "revision_primary": r"\b(?:REV(?:ISION)?)[\s:._-]*([A-Z0-9]+)\b",
        "revision_fallback": r"\b(R[0-9A-Z]+)\b",
    },
    "output": {
        "duplicate_suffix": True,
        "fallback_prefix": "PAGE",
    },
    "ocr": {
        "dpi": 300,
        "language": "eng",
        "psm": 6,
    },
    "ui": {
        "theme": "dark",
        "preview_zoom": 1.0,
    },
}


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge override into base (base is mutated copy)."""
    result = copy.deepcopy(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_settings() -> Dict[str, Any]:
    """Load settings from disk, filling missing keys with defaults."""
    if os.path.isfile(_CONFIG_PATH):
        try:
            with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
                on_disk = json.load(f)
            return _deep_merge(_DEFAULTS, on_disk)
        except (json.JSONDecodeError, OSError):
            pass
    return copy.deepcopy(_DEFAULTS)


def save_settings(settings: Dict[str, Any]) -> None:
    """Persist settings to disk."""
    os.makedirs(os.path.dirname(_CONFIG_PATH), exist_ok=True)
    with open(_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2)
