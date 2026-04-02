"""
core/extractor.py - Regex-based extraction of drawing number and revision
from title-block text.

Supports multiple revision formats:
  R0, R1, R2
  REV-0, REV-1
  REV A, REV B
  REVISION 01
  P1, P2 (preliminary)
"""

import re
from typing import Optional, Tuple, Dict, Any
from dataclasses import dataclass


@dataclass
class ExtractionResult:
    drawing_number: Optional[str]
    revision: Optional[str]
    raw_text: str
    method: str          # "pdf_text" | "ocr" | "none"
    confidence: str      # "high" | "low" | "none"

    @property
    def is_complete(self) -> bool:
        return bool(self.drawing_number and self.revision)

    @property
    def status(self) -> str:
        if self.is_complete:
            if self.method == "ocr":
                return "OCR used"
            return "Success"
        elif self.drawing_number or self.revision:
            return "Manual review needed"
        return "Failed"


class Extractor:
    """
    Applies configured regex patterns to extracted text and returns
    structured ExtractionResult objects.
    """

    # Minimum chars of text before we consider PDF text extraction sufficient
    MIN_TEXT_LENGTH = 15

    def __init__(self, regex_config: Dict[str, str]):
        self._drawing_pattern = self._compile(
            regex_config.get("drawing_number", r"([A-Z0-9]{2,}(?:-[A-Z0-9]+){4,})")
        )
        self._rev_primary = self._compile(
            regex_config.get(
                "revision_primary",
                r"\b(?:REV(?:ISION)?)[\s:._-]*([A-Z0-9]+)\b",
            )
        )
        self._rev_fallback = self._compile(
            regex_config.get("revision_fallback", r"\b(R[0-9A-Z]+)\b")
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def extract(self, text: str, method: str) -> ExtractionResult:
        """
        Run all patterns against *text* and return an ExtractionResult.
        *method* should be "pdf_text" or "ocr".
        """
        upper = text.upper()

        drawing_number = self._find_drawing_number(upper)
        revision = self._find_revision(upper)

        if drawing_number and revision:
            confidence = "high"
        elif drawing_number or revision:
            confidence = "low"
        else:
            confidence = "none"

        return ExtractionResult(
            drawing_number=drawing_number,
            revision=revision,
            raw_text=text,
            method=method if text.strip() else "none",
            confidence=confidence,
        )

    def needs_ocr(self, pdf_text: str) -> bool:
        """
        Decide whether the PDF text is sufficient or OCR is required.
        We need OCR if:
          - text is too short
          - drawing number not found in PDF text
        """
        if len(pdf_text.strip()) < self.MIN_TEXT_LENGTH:
            return True
        upper = pdf_text.upper()
        return self._find_drawing_number(upper) is None

    def update_patterns(self, regex_config: Dict[str, str]) -> None:
        """Hot-reload regex patterns from updated settings."""
        self._drawing_pattern = self._compile(
            regex_config.get("drawing_number", r"([A-Z0-9]{2,}(?:-[A-Z0-9]+){4,})")
        )
        self._rev_primary = self._compile(
            regex_config.get(
                "revision_primary",
                r"\b(?:REV(?:ISION)?)[\s:._-]*([A-Z0-9]+)\b",
            )
        )
        self._rev_fallback = self._compile(
            regex_config.get("revision_fallback", r"\b(R[0-9A-Z]+)\b")
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _find_drawing_number(self, text: str) -> Optional[str]:
        if self._drawing_pattern is None:
            return None
        m = self._drawing_pattern.search(text)
        if m:
            return m.group(1).strip()
        return None

    def _find_revision(self, text: str) -> Optional[str]:
        # Try primary pattern first
        if self._rev_primary:
            m = self._rev_primary.search(text)
            if m:
                rev = m.group(1).strip()
                return self._normalize_revision(rev)

        # Fallback pattern
        if self._rev_fallback:
            m = self._rev_fallback.search(text)
            if m:
                rev = m.group(1).strip()
                return self._normalize_revision(rev)

        return None

    @staticmethod
    def _normalize_revision(rev: str) -> str:
        """
        Normalize revision string to a clean, filename-safe form.
        Examples:
          "01"  → "R01"  (if purely numeric, prefix R)
          "A"   → "A"
          "R1"  → "R1"
          "REV1" → "REV1"   (already has prefix)
        """
        rev = rev.strip().upper()
        # Remove spaces e.g. "REV 1" → "REV1"
        rev = re.sub(r"\s+", "", rev)
        # If purely numeric, prefix with R
        if re.match(r"^\d+$", rev):
            rev = "R" + rev
        return rev

    @staticmethod
    def _compile(pattern: str) -> Optional[re.Pattern]:
        """Compile a regex pattern, returning None if invalid."""
        if not pattern:
            return None
        try:
            return re.compile(pattern, re.IGNORECASE)
        except re.error:
            return None
