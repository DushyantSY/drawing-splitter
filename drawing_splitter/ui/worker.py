"""
ui/worker.py - QThread-based batch processing worker.

Emits signals for progress, per-page results, log messages, and completion.
Never touches the UI directly — all communication is via Qt signals.
"""

from PySide6.QtCore import QThread, Signal
from typing import Dict, Any, Optional, List
import traceback

from core.pdf_processor import PDFProcessor, PDFProcessorError
from core.ocr import OCREngine, OCRError
from core.extractor import Extractor, ExtractionResult
from core.namer import Namer
from core.logger import ProcessingLogger


class PageResult:
    """Lightweight result object passed through signals."""
    __slots__ = (
        "page_index", "drawing_number", "revision",
        "output_filename", "status", "remarks", "method",
    )

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


class ProcessingWorker(QThread):
    # (current_page, total_pages)
    progress = Signal(int, int)
    # Human-readable log line
    log_message = Signal(str)
    # PageResult object
    page_done = Signal(object)
    # Final summary dict
    finished = Signal(dict)
    # Error string (fatal)
    error = Signal(str)

    def __init__(
        self,
        pdf_path: str,
        output_dir: str,
        settings: Dict[str, Any],
        test_mode: bool = False,
        test_pages: int = 3,
        page_range: Optional[List[int]] = None,
    ):
        super().__init__()
        self.pdf_path = pdf_path
        self.output_dir = output_dir
        self.settings = settings
        self.test_mode = test_mode
        self.test_pages = test_pages
        self.page_range = page_range  # None = all pages
        self._cancel_requested = False

    def request_cancel(self) -> None:
        self._cancel_requested = True

    def run(self) -> None:
        summary = {
            "total": 0,
            "success": 0,
            "ocr_used": 0,
            "review": 0,
            "failed": 0,
            "skipped": 0,
            "log_path": "",
        }

        try:
            self._process(summary)
        except PDFProcessorError as e:
            self.error.emit(str(e))
        except Exception as e:
            self.error.emit(f"Unexpected error: {e}\n{traceback.format_exc()}")
        finally:
            self.finished.emit(summary)

    def _process(self, summary: Dict) -> None:
        cfg = self.settings
        region = cfg["title_block"]
        ocr_mode = cfg.get("ocr_mode", "auto")

        ocr_engine = OCREngine(
            tesseract_path=cfg.get("tesseract_path", ""),
            language=cfg["ocr"]["language"],
            psm=cfg["ocr"]["psm"],
        )
        extractor = Extractor(cfg["regex"])
        namer = Namer(
            fallback_prefix=cfg["output"]["fallback_prefix"],
            use_duplicate_suffix=cfg["output"]["duplicate_suffix"],
        )

        with PDFProcessor(self.pdf_path) as proc:
            total = proc.page_count

            # Determine which pages to process
            if self.page_range is not None:
                pages = [i for i in self.page_range if 0 <= i < total]
            elif self.test_mode:
                pages = list(range(min(self.test_pages, total)))
            else:
                pages = list(range(total))

            summary["total"] = len(pages)

            with ProcessingLogger(self.output_dir, self.pdf_path) as csv_log:
                summary["log_path"] = csv_log.log_path

                for idx, page_index in enumerate(pages):
                    if self._cancel_requested:
                        self.log_message.emit("⛔ Processing cancelled by user.")
                        summary["skipped"] += summary["total"] - idx
                        break

                    self.progress.emit(idx + 1, len(pages))
                    page_num = page_index + 1
                    self.log_message.emit(f"Processing page {page_num}/{total} …")

                    result = self._process_page(
                        proc, extractor, ocr_engine, namer,
                        page_index, region, ocr_mode, cfg,
                    )

                    # Save the PDF page
                    out_path = self._output_path(result.output_filename)
                    save_ok = True
                    try:
                        proc.save_page_as_pdf(page_index, out_path)
                    except Exception as e:
                        result.status = "Failed"
                        result.remarks += f" | Save error: {e}"
                        save_ok = False

                    # Update counters
                    s = result.status
                    if "Success" in s:
                        summary["success"] += 1
                    if "OCR" in s:
                        summary["ocr_used"] += 1
                    if "review" in s.lower():
                        summary["review"] += 1
                    if "Failed" in s:
                        summary["failed"] += 1

                    csv_log.write_row(
                        page_number=page_num,
                        extracted_text=result.output_filename,   # we store filename here; see remarks for text
                        drawing_number=result.drawing_number,
                        revision=result.revision,
                        output_filename=result.output_filename,
                        status=result.status,
                        remarks=result.remarks,
                    )

                    self.page_done.emit(result)
                    log_icon = "✅" if save_ok else "❌"
                    self.log_message.emit(
                        f"  {log_icon} {result.output_filename} [{result.status}]"
                    )

                csv_log.flush()

    def _process_page(
        self,
        proc: PDFProcessor,
        extractor: Extractor,
        ocr_engine: OCREngine,
        namer: Namer,
        page_index: int,
        region: Dict,
        ocr_mode: str,
        cfg: Dict,
    ) -> PageResult:
        page_num = page_index + 1
        remarks = ""
        method = "pdf_text"
        ext_result: Optional[ExtractionResult] = None

        # --- Empty page check ---
        try:
            if proc.is_page_empty(page_index):
                fn = namer.build_filename(None, None, page_index)
                return PageResult(
                    page_index=page_index,
                    drawing_number=None,
                    revision=None,
                    output_filename=fn,
                    status="Failed",
                    remarks="Empty page",
                    method="none",
                )
        except Exception:
            pass

        # --- Step 1: PDF text extraction ---
        pdf_text = ""
        try:
            pdf_text = proc.extract_title_block_text(page_index, region)
        except Exception as e:
            remarks += f"PDF text error: {e}. "

        # --- Step 2: Decide whether OCR is needed ---
        use_ocr = False
        if ocr_mode == "always":
            use_ocr = True
        elif ocr_mode == "auto":
            use_ocr = extractor.needs_ocr(pdf_text)
        # "never" → use_ocr stays False

        ocr_text = ""
        if use_ocr:
            method = "ocr"
            try:
                raw_image = proc.render_title_block(
                    page_index, region, dpi=cfg["ocr"]["dpi"]
                )
                enhanced = ocr_engine.preprocess_for_ocr(raw_image)
                ocr_text = ocr_engine.run_ocr(enhanced)
            except OCRError as e:
                remarks += f"OCR failed: {e}. "
                method = "pdf_text"  # fall back to whatever PDF text we got

        combined_text = (ocr_text or pdf_text).strip()
        if not combined_text:
            combined_text = pdf_text  # last resort

        # --- Step 3: Extract drawing number and revision ---
        ext_result = extractor.extract(combined_text, method)

        # --- Step 4: Build filename ---
        fn = namer.build_filename(
            ext_result.drawing_number,
            ext_result.revision,
            page_index,
        )

        if not ext_result.drawing_number:
            remarks += "Drawing number not found. "
        if not ext_result.revision:
            remarks += "Revision not found. "

        return PageResult(
            page_index=page_index,
            drawing_number=ext_result.drawing_number,
            revision=ext_result.revision,
            output_filename=fn,
            status=ext_result.status,
            remarks=remarks.strip(),
            method=method,
        )

    def _output_path(self, filename: str) -> str:
        import os
        return os.path.join(self.output_dir, filename)
