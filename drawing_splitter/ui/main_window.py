"""
ui/main_window.py - Main application window.

Layout:
  Left panel  : file/folder pickers + controls + log + progress
  Right panel : page preview
"""

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QSplitter,
    QLabel, QLineEdit, QPushButton, QTextEdit, QProgressBar,
    QTableWidget, QTableWidgetItem, QHeaderView, QFileDialog,
    QMessageBox, QGroupBox, QCheckBox, QSpinBox, QComboBox,
    QSizePolicy, QStatusBar,
)
from PySide6.QtCore import Qt, QThread
from PySide6.QtGui import QColor, QFont, QIcon
import os
import subprocess
from typing import Dict, Any, Optional

from ui.preview_panel import PreviewPanel
from ui.settings_dialog import SettingsDialog
from ui.worker import ProcessingWorker
from core.pdf_processor import PDFProcessor, PDFProcessorError
from core.extractor import Extractor
from core.ocr import OCREngine
from core.config import save_settings


_STATUS_COLORS = {
    "Success":              "#2ecc71",
    "OCR used":             "#3498db",
    "Manual review needed": "#e67e22",
    "Failed":               "#e74c3c",
}


class MainWindow(QMainWindow):

    def __init__(self, settings: Dict[str, Any]):
        super().__init__()
        self.settings = settings
        self._worker: Optional[ProcessingWorker] = None
        self._pdf_processor: Optional[PDFProcessor] = None
        self._total_pages = 0
        self._last_log_path = ""

        self.setWindowTitle("Drawing Splitter — Engineering PDF Tool")
        self.setMinimumSize(1100, 700)
        self.resize(1280, 780)

        self._apply_dark_theme()
        self._build_ui()
        self._connect_signals()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(10)

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self._build_left_panel())
        splitter.addWidget(self._build_right_panel())
        splitter.setSizes([640, 440])
        splitter.setHandleWidth(4)
        root.addWidget(splitter)

        # Status bar
        self.statusBar().showMessage("Ready. Open a PDF to begin.")

    def _build_left_panel(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setSpacing(10)
        layout.setContentsMargins(0, 0, 0, 0)

        layout.addWidget(self._build_file_group())
        layout.addWidget(self._build_options_group())
        layout.addWidget(self._build_action_group())
        layout.addWidget(self._build_results_group(), stretch=3)
        layout.addWidget(self._build_log_group(), stretch=2)

        return w

    def _build_file_group(self) -> QGroupBox:
        box = QGroupBox("Files")
        form = QVBoxLayout(box)
        form.setSpacing(6)

        # Input PDF
        in_row = QHBoxLayout()
        in_row.addWidget(QLabel("Input PDF:"))
        self._input_edit = QLineEdit()
        self._input_edit.setPlaceholderText("Select a multi-page engineering PDF…")
        self._input_edit.setReadOnly(True)
        in_row.addWidget(self._input_edit)
        self._browse_pdf_btn = QPushButton("Browse…")
        self._browse_pdf_btn.setFixedWidth(80)
        in_row.addWidget(self._browse_pdf_btn)
        form.addLayout(in_row)

        # Output folder
        out_row = QHBoxLayout()
        out_row.addWidget(QLabel("Output folder:"))
        self._output_edit = QLineEdit()
        self._output_edit.setPlaceholderText("Select destination folder…")
        self._output_edit.setReadOnly(True)
        out_row.addWidget(self._output_edit)
        self._browse_out_btn = QPushButton("Browse…")
        self._browse_out_btn.setFixedWidth(80)
        out_row.addWidget(self._browse_out_btn)
        form.addLayout(out_row)

        self._pdf_info_label = QLabel("No PDF loaded.")
        self._pdf_info_label.setStyleSheet("color: #888; font-size: 11px;")
        form.addWidget(self._pdf_info_label)

        return box

    def _build_options_group(self) -> QGroupBox:
        box = QGroupBox("Run Options")
        row = QHBoxLayout(box)
        row.setSpacing(16)

        self._test_mode_cb = QCheckBox("Test mode (first")
        row.addWidget(self._test_mode_cb)

        self._test_pages_spin = QSpinBox()
        self._test_pages_spin.setRange(1, 50)
        self._test_pages_spin.setValue(3)
        self._test_pages_spin.setFixedWidth(55)
        row.addWidget(self._test_pages_spin)
        row.addWidget(QLabel("pages)"))

        row.addStretch()

        self._settings_btn = QPushButton("⚙  Settings")
        row.addWidget(self._settings_btn)

        return box

    def _build_action_group(self) -> QGroupBox:
        # Single QGroupBox — the original double-box caused button GC and the signal crash
        box = QGroupBox("Actions")
        outer_layout = QVBoxLayout(box)
        outer_layout.setSpacing(6)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        self._start_btn = QPushButton("▶  Start Processing")
        self._start_btn.setFixedHeight(36)
        self._start_btn.setEnabled(False)
        self._start_btn.setObjectName("start_btn")
        btn_row.addWidget(self._start_btn, stretch=2)

        self._cancel_btn = QPushButton("⛔  Cancel")
        self._cancel_btn.setFixedHeight(36)
        self._cancel_btn.setEnabled(False)
        btn_row.addWidget(self._cancel_btn, stretch=1)

        self._open_out_btn = QPushButton("📂  Open Output")
        self._open_out_btn.setFixedHeight(36)
        self._open_out_btn.setEnabled(False)
        btn_row.addWidget(self._open_out_btn, stretch=1)

        self._export_log_btn = QPushButton("📄  Export Log")
        self._export_log_btn.setFixedHeight(36)
        self._export_log_btn.setEnabled(False)
        btn_row.addWidget(self._export_log_btn, stretch=1)

        outer_layout.addLayout(btn_row)

        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        self._progress_bar.setTextVisible(True)
        self._progress_bar.setFixedHeight(18)
        outer_layout.addWidget(self._progress_bar)

        return box

    def _build_results_group(self) -> QGroupBox:
        box = QGroupBox("Results")
        layout = QVBoxLayout(box)

        self._results_table = QTableWidget()
        self._results_table.setColumnCount(5)
        self._results_table.setHorizontalHeaderLabels(
            ["Page", "Drawing Number", "Revision", "Output Filename", "Status"]
        )
        self._results_table.horizontalHeader().setSectionResizeMode(
            3, QHeaderView.Stretch
        )
        self._results_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeToContents
        )
        self._results_table.setSelectionBehavior(QTableWidget.SelectRows)
        self._results_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._results_table.setAlternatingRowColors(True)
        self._results_table.verticalHeader().setVisible(False)
        layout.addWidget(self._results_table)

        return box

    def _build_log_group(self) -> QGroupBox:
        box = QGroupBox("Processing Log")
        layout = QVBoxLayout(box)

        self._log_text = QTextEdit()
        self._log_text.setReadOnly(True)
        self._log_text.setFont(QFont("Consolas", 9))
        self._log_text.setMaximumHeight(160)
        layout.addWidget(self._log_text)

        return box

    def _build_right_panel(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(0, 0, 0, 0)

        box = QGroupBox("Page Preview")
        box_layout = QVBoxLayout(box)
        self._preview = PreviewPanel()
        self._preview.set_preview_callback(self._load_preview_page)
        self._preview.extract_requested.connect(self._test_extraction)
        box_layout.addWidget(self._preview)
        layout.addWidget(box)

        return w

    # ------------------------------------------------------------------
    # Signal connections
    # ------------------------------------------------------------------

    def _connect_signals(self) -> None:
        self._browse_pdf_btn.clicked.connect(self._browse_pdf)
        self._browse_out_btn.clicked.connect(self._browse_output)
        self._settings_btn.clicked.connect(self._open_settings)
        self._start_btn.clicked.connect(self._start_processing)
        self._cancel_btn.clicked.connect(self._cancel_processing)
        self._open_out_btn.clicked.connect(self._open_output_folder)
        self._export_log_btn.clicked.connect(self._export_log)

    # ------------------------------------------------------------------
    # File picking
    # ------------------------------------------------------------------

    def _browse_pdf(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Input PDF", "", "PDF Files (*.pdf);;All Files (*)"
        )
        if not path:
            return
        self._input_edit.setText(path)
        self._load_pdf(path)

    def _browse_output(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Select Output Folder")
        if folder:
            self._output_edit.setText(folder)
            self._update_start_button()
            self._open_out_btn.setEnabled(True)

    def _load_pdf(self, path: str) -> None:
        # Close previous
        if self._pdf_processor:
            self._pdf_processor.close()
            self._pdf_processor = None

        try:
            proc = PDFProcessor(path)
            proc.open()
            self._pdf_processor = proc
            self._total_pages = proc.page_count

            self._pdf_info_label.setText(
                f"✓ Loaded: {os.path.basename(path)}  —  {self._total_pages} pages"
            )
            self._preview.set_pdf_loaded(self._total_pages)
            self._load_preview_page(0)
            self._update_start_button()
            self.statusBar().showMessage(
                f"Loaded: {os.path.basename(path)} ({self._total_pages} pages)"
            )
        except PDFProcessorError as e:
            QMessageBox.critical(self, "Cannot Open PDF", str(e))
            self._pdf_info_label.setText("⚠ Failed to load PDF.")
            self._start_btn.setEnabled(False)

    # ------------------------------------------------------------------
    # Preview
    # ------------------------------------------------------------------

    def _load_preview_page(self, page_index: int) -> None:
        if not self._pdf_processor:
            return
        try:
            png = self._pdf_processor.render_page_thumbnail(page_index, max_width=500)
            self._preview.set_page_image(png)
            self._preview.set_region(self.settings["title_block"])
        except Exception as e:
            self._log(f"Preview error: {e}")

    def _test_extraction(self, page_index: int) -> None:
        if not self._pdf_processor:
            return
        region = self.settings["title_block"]
        ocr_mode = self.settings.get("ocr_mode", "auto")

        # PDF text
        try:
            pdf_text = self._pdf_processor.extract_title_block_text(page_index, region)
        except Exception as e:
            pdf_text = ""
            self._log(f"Text extraction error: {e}")

        extractor = Extractor(self.settings["regex"])
        method = "pdf_text"
        text = pdf_text

        if ocr_mode != "never" and extractor.needs_ocr(pdf_text):
            method = "ocr"
            try:
                engine = OCREngine(
                    self.settings.get("tesseract_path", ""),
                    self.settings["ocr"]["language"],
                    self.settings["ocr"]["psm"],
                )
                raw_img = self._pdf_processor.render_title_block(
                    page_index, region, self.settings["ocr"]["dpi"]
                )
                enhanced = engine.preprocess_for_ocr(raw_img)
                text = engine.run_ocr(enhanced)
            except Exception as e:
                method = "pdf_text (OCR failed)"
                self._log(f"OCR error during test: {e}")

        result = extractor.extract(text or pdf_text, method)
        self._preview.show_extraction_result(
            result.drawing_number, result.revision, result.raw_text, result.method
        )

    # ------------------------------------------------------------------
    # Processing
    # ------------------------------------------------------------------

    def _start_processing(self) -> None:
        pdf_path = self._input_edit.text().strip()
        out_dir = self._output_edit.text().strip()

        if not pdf_path or not out_dir:
            QMessageBox.warning(self, "Missing Input", "Please select both input PDF and output folder.")
            return

        os.makedirs(out_dir, exist_ok=True)

        # Clear previous results
        self._results_table.setRowCount(0)
        self._log_text.clear()
        self._progress_bar.setValue(0)
        self._last_log_path = ""

        test_mode = self._test_mode_cb.isChecked()
        test_pages = self._test_pages_spin.value()

        self._worker = ProcessingWorker(
            pdf_path=pdf_path,
            output_dir=out_dir,
            settings=self.settings,
            test_mode=test_mode,
            test_pages=test_pages,
        )
        self._worker.progress.connect(self._on_progress)
        self._worker.log_message.connect(self._log)
        self._worker.page_done.connect(self._on_page_done)
        self._worker.finished.connect(self._on_finished)
        self._worker.error.connect(self._on_error)

        self._start_btn.setEnabled(False)
        self._cancel_btn.setEnabled(True)
        self._export_log_btn.setEnabled(False)
        self.statusBar().showMessage("Processing…")
        self._worker.start()

    def _cancel_processing(self) -> None:
        if self._worker and self._worker.isRunning():
            self._worker.request_cancel()
            self._cancel_btn.setEnabled(False)
            self.statusBar().showMessage("Cancelling…")

    def _on_progress(self, current: int, total: int) -> None:
        pct = int(current / total * 100) if total > 0 else 0
        self._progress_bar.setValue(pct)
        self._progress_bar.setFormat(f"{current} / {total}  ({pct}%)")

    def _on_page_done(self, result) -> None:
        row = self._results_table.rowCount()
        self._results_table.insertRow(row)

        items = [
            str(result.page_index + 1),
            result.drawing_number or "—",
            result.revision or "—",
            result.output_filename,
            result.status,
        ]
        color = _STATUS_COLORS.get(result.status, "#cccccc")
        for col, text in enumerate(items):
            item = QTableWidgetItem(text)
            if col == 4:
                item.setForeground(QColor(color))
            self._results_table.setItem(row, col, item)

        self._results_table.scrollToBottom()

    def _on_finished(self, summary: Dict) -> None:
        self._start_btn.setEnabled(True)
        self._cancel_btn.setEnabled(False)
        self._export_log_btn.setEnabled(True)
        self._last_log_path = summary.get("log_path", "")

        msg = (
            f"Done — {summary['total']} pages processed.\n"
            f"  ✅ Success: {summary['success']}\n"
            f"  🔵 OCR used: {summary['ocr_used']}\n"
            f"  ⚠ Review needed: {summary['review']}\n"
            f"  ❌ Failed: {summary['failed']}\n"
            f"  ⏩ Skipped: {summary['skipped']}"
        )
        self._log(msg)
        self.statusBar().showMessage(
            f"Finished — {summary['success']}/{summary['total']} successful"
        )

    def _on_error(self, message: str) -> None:
        QMessageBox.critical(self, "Processing Error", message)
        self._start_btn.setEnabled(True)
        self._cancel_btn.setEnabled(False)
        self.statusBar().showMessage("Error — see log.")

    # ------------------------------------------------------------------
    # Output / Export
    # ------------------------------------------------------------------

    def _open_output_folder(self) -> None:
        folder = self._output_edit.text().strip()
        if folder and os.path.isdir(folder):
            if os.name == "nt":
                os.startfile(folder)
            else:
                subprocess.Popen(["xdg-open", folder])

    def _export_log(self) -> None:
        if not hasattr(self, "_last_log_path") or not self._last_log_path:
            QMessageBox.information(self, "No Log", "Run a batch first to generate a log.")
            return
        dest, _ = QFileDialog.getSaveFileName(
            self, "Save Log As", self._last_log_path, "CSV Files (*.csv)"
        )
        if dest and dest != self._last_log_path:
            import shutil
            shutil.copy2(self._last_log_path, dest)
            self._log(f"Log exported to: {dest}")

    # ------------------------------------------------------------------
    # Settings
    # ------------------------------------------------------------------

    def _open_settings(self) -> None:
        dlg = SettingsDialog(self.settings, parent=self)
        if dlg.exec():
            self.settings = dlg.get_settings()
            save_settings(self.settings)
            # Refresh preview region overlay
            self._preview.set_region(self.settings["title_block"])
            self.statusBar().showMessage("Settings saved.")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _log(self, message: str) -> None:
        self._log_text.append(message)

    def _update_start_button(self) -> None:
        has_pdf = bool(self._input_edit.text().strip())
        has_out = bool(self._output_edit.text().strip())
        self._start_btn.setEnabled(has_pdf and has_out)

    def _apply_dark_theme(self) -> None:
        self.setStyleSheet("""
            QMainWindow, QWidget {
                background-color: #1e1e2e;
                color: #cdd6f4;
                font-family: 'Segoe UI', sans-serif;
                font-size: 12px;
            }
            QGroupBox {
                border: 1px solid #45475a;
                border-radius: 6px;
                margin-top: 8px;
                padding-top: 6px;
                font-weight: bold;
                color: #89b4fa;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 0 6px;
            }
            QPushButton {
                background-color: #313244;
                color: #cdd6f4;
                border: 1px solid #45475a;
                border-radius: 5px;
                padding: 5px 12px;
            }
            QPushButton:hover {
                background-color: #45475a;
                border-color: #89b4fa;
            }
            QPushButton:disabled {
                color: #585b70;
                border-color: #313244;
            }
            QPushButton#start_btn {
                background-color: #a6e3a1;
                color: #1e1e2e;
                font-weight: bold;
                border: none;
            }
            QPushButton#start_btn:hover {
                background-color: #94e2d5;
            }
            QPushButton#start_btn:disabled {
                background-color: #313244;
                color: #585b70;
            }
            QLineEdit, QTextEdit, QPlainTextEdit {
                background-color: #181825;
                border: 1px solid #45475a;
                border-radius: 4px;
                padding: 4px;
                color: #cdd6f4;
            }
            QTableWidget {
                background-color: #181825;
                gridline-color: #313244;
                border: 1px solid #45475a;
                color: #cdd6f4;
            }
            QHeaderView::section {
                background-color: #313244;
                color: #89b4fa;
                border: none;
                padding: 5px;
                font-weight: bold;
            }
            QTableWidget::item:selected {
                background-color: #45475a;
            }
            QTableWidget::item:alternate {
                background-color: #1e1e2e;
            }
            QProgressBar {
                border: 1px solid #45475a;
                border-radius: 4px;
                background-color: #181825;
                text-align: center;
                color: #cdd6f4;
            }
            QProgressBar::chunk {
                background-color: #89b4fa;
                border-radius: 3px;
            }
            QComboBox {
                background-color: #313244;
                border: 1px solid #45475a;
                border-radius: 4px;
                padding: 4px 8px;
                color: #cdd6f4;
            }
            QComboBox::drop-down {
                border: none;
            }
            QComboBox QAbstractItemView {
                background-color: #313244;
                selection-background-color: #45475a;
            }
            QSpinBox, QDoubleSpinBox {
                background-color: #313244;
                border: 1px solid #45475a;
                border-radius: 4px;
                padding: 4px;
                color: #cdd6f4;
            }
            QTabWidget::pane {
                border: 1px solid #45475a;
                border-radius: 4px;
            }
            QTabBar::tab {
                background-color: #313244;
                color: #cdd6f4;
                padding: 6px 14px;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                margin-right: 2px;
            }
            QTabBar::tab:selected {
                background-color: #45475a;
                color: #89b4fa;
            }
            QScrollBar:vertical {
                background: #181825;
                width: 8px;
                border-radius: 4px;
            }
            QScrollBar::handle:vertical {
                background: #45475a;
                border-radius: 4px;
                min-height: 20px;
            }
            QSplitter::handle {
                background-color: #45475a;
            }
            QCheckBox {
                spacing: 6px;
            }
            QCheckBox::indicator {
                width: 14px;
                height: 14px;
                border: 1px solid #45475a;
                border-radius: 3px;
                background: #313244;
            }
            QCheckBox::indicator:checked {
                background: #89b4fa;
            }
        """)

    def closeEvent(self, event):
        if self._worker and self._worker.isRunning():
            self._worker.request_cancel()
            self._worker.wait(3000)
        if self._pdf_processor:
            self._pdf_processor.close()
        save_settings(self.settings)
        event.accept()
