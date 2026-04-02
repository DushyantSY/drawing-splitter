"""
core/namer.py - Filename construction, sanitization, and duplicate handling.
"""

import os
import re
from typing import Set, Optional


# Characters not allowed in Windows filenames
_INVALID_CHARS = re.compile(r'[\\/:*?"<>|]')

# Multiple consecutive underscores → single
_MULTI_UNDERSCORE = re.compile(r"_+")

# Max filename length (without extension) to avoid filesystem issues
_MAX_NAME_LEN = 200


class Namer:
    """
    Builds unique, sanitized output filenames for split drawing pages.
    Tracks all names already used in this session to handle duplicates.
    """

    def __init__(self, fallback_prefix: str = "PAGE", use_duplicate_suffix: bool = True):
        self.fallback_prefix = fallback_prefix
        self.use_duplicate_suffix = use_duplicate_suffix
        self._used: Set[str] = set()  # lowercase stems already emitted

    def reset(self) -> None:
        """Clear the used-names registry (call between batch runs)."""
        self._used.clear()

    def build_filename(
        self,
        drawing_number: Optional[str],
        revision: Optional[str],
        page_index: int,
        extension: str = ".pdf",
    ) -> str:
        """
        Construct a final output filename.

        Priority:
          1. drawingNumber_revision.pdf   (both found)
          2. drawingNumber_NOREV.pdf      (only drawing number)
          3. PAGE_0001_NONUM.pdf          (fallback)

        Handles duplicates by appending _2, _3, etc.
        """
        stem = self._build_stem(drawing_number, revision, page_index)
        stem = self._sanitize(stem)
        stem = stem[:_MAX_NAME_LEN]

        if not stem:
            stem = f"{self.fallback_prefix}_{page_index + 1:04d}"

        final_stem = self._deduplicate(stem)
        return final_stem + extension

    def _build_stem(
        self,
        drawing_number: Optional[str],
        revision: Optional[str],
        page_index: int,
    ) -> str:
        if drawing_number and revision:
            return f"{drawing_number}_{revision}"
        elif drawing_number:
            return f"{drawing_number}_NOREV"
        elif revision:
            return f"{self.fallback_prefix}_{page_index + 1:04d}_{revision}"
        else:
            return f"{self.fallback_prefix}_{page_index + 1:04d}_NONUM"

    def _sanitize(self, name: str) -> str:
        """Replace illegal filename characters and tidy up."""
        name = _INVALID_CHARS.sub("_", name)
        name = name.strip(". _")
        name = _MULTI_UNDERSCORE.sub("_", name)
        return name

    def _deduplicate(self, stem: str) -> str:
        """
        If *stem* was already used, append _2, _3, ... until unique.
        """
        if not self.use_duplicate_suffix:
            return stem

        key = stem.lower()
        if key not in self._used:
            self._used.add(key)
            return stem

        counter = 2
        while True:
            candidate = f"{stem}_{counter}"
            if candidate.lower() not in self._used:
                self._used.add(candidate.lower())
                return candidate
            counter += 1
