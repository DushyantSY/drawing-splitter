"""
core/pdf_processor.py - PDF reading, title-block clipping, page splitting, and rendering.

Uses PyMuPDF (fitz) exclusively for all PDF operations.
"""

import fitz  # PyMuPDF
import os
from typing import Optional, Tuple, Dict, Any
import io


class PDFProcessorError(Exception):
    pass


class PDFProcessor:
    """
    Handles opening, validating, and extracting data from PDF files.
    Single instance is reused across the batch run.
    """

    def __init__(self, pdf_path: str):
        self.pdf_path = pdf_path
        self._doc: Optional[fitz.Document] = None

    def open(self) -> None:
        """Open and validate the PDF. Raises PDFProcessorError on failure."""
        if not os.path.isfile(self.pdf_path):
            raise PDFProcessorError(f"File not found: {self.pdf_path}")

        try:
            doc = fitz.open(self.pdf_path)
        except fitz.FileDataError as e:
            raise PDFProcessorError(f"Corrupted or unreadable PDF: {e}") from e

        if doc.needs_pass:
            doc.close()
            raise PDFProcessorError(
                "PDF is password-protected. Please decrypt it before processing."
            )

        if doc.page_count == 0:
            doc.close()
            raise PDFProcessorError("PDF has no pages.")

        self._doc = doc

    def close(self) -> None:
        if self._doc:
            self._doc.close()
            self._doc = None

    @property
    def page_count(self) -> int:
        self._require_open()
        return self._doc.page_count

    # ------------------------------------------------------------------
    # Title-block text extraction
    # ------------------------------------------------------------------

    def extract_title_block_text(
        self, page_index: int, region_pct: Dict[str, float]
    ) -> str:
        """
        Extract text from a percentage-defined rectangle on the page.

        region_pct keys: x_start_pct, y_start_pct, x_end_pct, y_end_pct
        All values are 0–100 percent of page dimensions.

        Returns raw text string (may be empty if the page is a scan).
        """
        self._require_open()
        page = self._doc[page_index]
        rect = self._pct_to_rect(page, region_pct)

        # Use "dict" extraction to get only the words inside rect
        text_blocks = page.get_text("text", clip=rect)
        return text_blocks.strip()

    def get_page_text_length(self, page_index: int) -> int:
        """Quick check: how many characters of selectable text does this page have?"""
        self._require_open()
        page = self._doc[page_index]
        return len(page.get_text("text").strip())

    # ------------------------------------------------------------------
    # Page rendering for OCR
    # ------------------------------------------------------------------

    def render_title_block(
        self,
        page_index: int,
        region_pct: Dict[str, float],
        dpi: int = 300,
    ) -> bytes:
        """
        Render the title-block region to a PNG image (bytes).
        Used when OCR is needed.
        """
        self._require_open()
        page = self._doc[page_index]
        rect = self._pct_to_rect(page, region_pct)

        zoom = dpi / 72.0
        mat = fitz.Matrix(zoom, zoom)
        clip = fitz.IRect(rect)
        pix = page.get_pixmap(matrix=mat, clip=clip, alpha=False)
        return pix.tobytes("png")

    def render_page_thumbnail(
        self, page_index: int, max_width: int = 600
    ) -> bytes:
        """
        Render the full page as a small PNG for UI preview.
        Returns PNG bytes.
        """
        self._require_open()
        page = self._doc[page_index]
        w = page.rect.width
        zoom = max_width / w if w > 0 else 1.0
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        return pix.tobytes("png")

    # ------------------------------------------------------------------
    # Page splitting / saving
    # ------------------------------------------------------------------

    def save_page_as_pdf(self, page_index: int, output_path: str) -> None:
        """
        Extract a single page and write it as a standalone PDF file.
        """
        self._require_open()

        new_doc = fitz.open()
        new_doc.insert_pdf(self._doc, from_page=page_index, to_page=page_index)

        # Ensure output directory exists
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

        new_doc.save(output_path, garbage=4, deflate=True)
        new_doc.close()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def is_page_empty(self, page_index: int) -> bool:
        """
        Heuristic: page is considered empty if it has no text and renders
        as a near-uniform image (very small pixmap variance).
        """
        self._require_open()
        page = self._doc[page_index]
        text = page.get_text("text").strip()
        if text:
            return False
        # Check image content - if the page has any image blocks it's not empty
        blocks = page.get_text("dict")["blocks"]
        return len(blocks) == 0

    def get_page_info(self, page_index: int) -> Dict[str, Any]:
        """Return basic metadata for a page."""
        self._require_open()
        page = self._doc[page_index]
        return {
            "index": page_index,
            "width": page.rect.width,
            "height": page.rect.height,
            "rotation": page.rotation,
            "text_length": len(page.get_text("text").strip()),
        }

    def _pct_to_rect(self, page: fitz.Page, region_pct: Dict[str, float]) -> fitz.Rect:
        """Convert percentage-based region to a fitz.Rect in page coordinates."""
        w = page.rect.width
        h = page.rect.height
        x0 = w * region_pct["x_start_pct"] / 100.0
        y0 = h * region_pct["y_start_pct"] / 100.0
        x1 = w * region_pct["x_end_pct"] / 100.0
        y1 = h * region_pct["y_end_pct"] / 100.0
        return fitz.Rect(x0, y0, x1, y1)

    def _require_open(self) -> None:
        if self._doc is None:
            raise PDFProcessorError("PDF is not open. Call open() first.")

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, *args):
        self.close()
