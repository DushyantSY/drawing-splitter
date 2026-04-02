"""
core/logger.py - CSV processing log writer.

Writes one row per page, incrementally flushed so partial results survive
a crash or user cancel.
"""

import csv
import os
from datetime import datetime
from typing import Optional


_COLUMNS = [
    "page_number",
    "extracted_text",
    "drawing_number",
    "revision",
    "output_filename",
    "status",
    "remarks",
]


class ProcessingLogger:
    """
    Thread-safe (single-writer assumed) CSV log.
    Open with a context manager or call open()/close() manually.
    """

    def __init__(self, output_dir: str, source_pdf: str):
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        pdf_stem = os.path.splitext(os.path.basename(source_pdf))[0]
        filename = f"{pdf_stem}_log_{ts}.csv"
        self.log_path = os.path.join(output_dir, filename)
        self._file = None
        self._writer = None
        self._row_count = 0

    def open(self) -> None:
        os.makedirs(os.path.dirname(os.path.abspath(self.log_path)), exist_ok=True)
        self._file = open(self.log_path, "w", newline="", encoding="utf-8-sig")
        self._writer = csv.DictWriter(self._file, fieldnames=_COLUMNS)
        self._writer.writeheader()
        self._file.flush()

    def close(self) -> None:
        if self._file:
            self._file.flush()
            self._file.close()
            self._file = None
            self._writer = None

    def write_row(
        self,
        page_number: int,
        extracted_text: str,
        drawing_number: Optional[str],
        revision: Optional[str],
        output_filename: str,
        status: str,
        remarks: str = "",
    ) -> None:
        if self._writer is None:
            raise RuntimeError("Logger is not open. Call open() first.")

        # Truncate extracted_text to avoid huge cells
        short_text = (extracted_text or "").replace("\n", " ").strip()
        if len(short_text) > 300:
            short_text = short_text[:297] + "..."

        self._writer.writerow(
            {
                "page_number": page_number,
                "extracted_text": short_text,
                "drawing_number": drawing_number or "",
                "revision": revision or "",
                "output_filename": output_filename,
                "status": status,
                "remarks": remarks,
            }
        )
        self._row_count += 1
        # Flush every 10 rows to balance performance vs durability
        if self._row_count % 10 == 0:
            self._file.flush()

    def flush(self) -> None:
        if self._file:
            self._file.flush()

    @property
    def row_count(self) -> int:
        return self._row_count

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, *args):
        self.close()
