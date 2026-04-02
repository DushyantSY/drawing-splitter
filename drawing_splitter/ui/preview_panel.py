"""
ui/preview_panel.py - Page preview widget with title-block region overlay.

Shows a rendered page thumbnail and lets the user test extraction
on any specific page before running the full batch.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSpinBox,
    QPushButton, QTextEdit, QSizePolicy, QFrame, QScrollArea,
)
from PySide6.QtGui import QPixmap, QPainter, QPen, QColor, QImage
from PySide6.QtCore import Qt, Signal, QRect
from typing import Optional, Dict, Any, Callable


class PageCanvas(QLabel):
    """Label that draws the page image + a semi-transparent title block overlay."""

    def __init__(self):
        super().__init__()
        self.setAlignment(Qt.AlignCenter)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumSize(300, 400)
        self._region_pct: Optional[Dict[str, float]] = None
        self._base_pixmap: Optional[QPixmap] = None

    def set_page_image(self, png_bytes: bytes) -> None:
        img = QImage.fromData(png_bytes)
        self._base_pixmap = QPixmap.fromImage(img)
        self._update_display()

    def set_region(self, region_pct: Dict[str, float]) -> None:
        self._region_pct = region_pct
        self._update_display()

    def _update_display(self) -> None:
        if self._base_pixmap is None:
            return

        pixmap = self._base_pixmap.copy()
        w = pixmap.width()
        h = pixmap.height()

        if self._region_pct:
            x0 = int(w * self._region_pct["x_start_pct"] / 100)
            y0 = int(h * self._region_pct["y_start_pct"] / 100)
            x1 = int(w * self._region_pct["x_end_pct"] / 100)
            y1 = int(h * self._region_pct["y_end_pct"] / 100)

            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.Antialiasing)
            overlay_color = QColor(255, 200, 0, 60)
            painter.fillRect(QRect(x0, y0, x1 - x0, y1 - y0), overlay_color)
            pen = QPen(QColor(255, 160, 0), 2)
            painter.setPen(pen)
            painter.drawRect(QRect(x0, y0, x1 - x0, y1 - y0))
            painter.end()

        # Scale to fit the label while keeping aspect ratio
        scaled = pixmap.scaled(
            self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
        self.setPixmap(scaled)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_display()


class PreviewPanel(QWidget):
    """
    Full preview panel: page selector, canvas, and extraction result display.
    """

    # Emitted when user clicks "Test Extraction" with the page index (0-based)
    extract_requested = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._total_pages = 0
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(0, 0, 0, 0)

        # --- Top controls ---
        ctrl = QHBoxLayout()
        ctrl.addWidget(QLabel("Page:"))

        self._page_spin = QSpinBox()
        self._page_spin.setMinimum(1)
        self._page_spin.setMaximum(1)
        self._page_spin.setFixedWidth(70)
        ctrl.addWidget(self._page_spin)

        self._page_label = QLabel("/ —")
        ctrl.addWidget(self._page_label)
        ctrl.addStretch()

        self._preview_btn = QPushButton("Load Preview")
        self._preview_btn.setFixedWidth(120)
        self._preview_btn.clicked.connect(self._on_preview_clicked)
        ctrl.addWidget(self._preview_btn)

        self._extract_btn = QPushButton("Test Extraction")
        self._extract_btn.setFixedWidth(130)
        self._extract_btn.clicked.connect(self._on_extract_clicked)
        ctrl.addWidget(self._extract_btn)

        layout.addLayout(ctrl)

        # --- Canvas ---
        self._canvas = PageCanvas()
        scroll = QScrollArea()
        scroll.setWidget(self._canvas)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        layout.addWidget(scroll, stretch=3)

        # --- Extraction result ---
        self._result_box = QTextEdit()
        self._result_box.setReadOnly(True)
        self._result_box.setMaximumHeight(120)
        self._result_box.setPlaceholderText(
            "Extraction results will appear here after 'Test Extraction'."
        )
        layout.addWidget(self._result_box)

        self.setEnabled(False)

    # ------------------------------------------------------------------
    # Public API called by MainWindow
    # ------------------------------------------------------------------

    def set_pdf_loaded(self, total_pages: int) -> None:
        self._total_pages = total_pages
        self._page_spin.setMaximum(total_pages)
        self._page_spin.setValue(1)
        self._page_label.setText(f"/ {total_pages}")
        self.setEnabled(True)

    def set_page_image(self, png_bytes: bytes) -> None:
        self._canvas.set_page_image(png_bytes)

    def set_region(self, region_pct: Dict[str, float]) -> None:
        self._canvas.set_region(region_pct)

    def show_extraction_result(
        self,
        drawing_number: Optional[str],
        revision: Optional[str],
        raw_text: str,
        method: str,
    ) -> None:
        lines = [
            f"Method   : {method}",
            f"Drawing# : {drawing_number or '— not found —'}",
            f"Revision : {revision or '— not found —'}",
            "",
            "— Raw extracted text —",
            raw_text[:500] if raw_text else "(empty)",
        ]
        self._result_box.setPlainText("\n".join(lines))

    @property
    def current_page_index(self) -> int:
        """Returns 0-based page index."""
        return self._page_spin.value() - 1

    # ------------------------------------------------------------------
    # Signals / slots
    # ------------------------------------------------------------------

    def _on_preview_clicked(self) -> None:
        # MainWindow connects to this via a direct call
        if hasattr(self, "_preview_callback") and self._preview_callback:
            self._preview_callback(self.current_page_index)

    def _on_extract_clicked(self) -> None:
        self.extract_requested.emit(self.current_page_index)

    def set_preview_callback(self, cb: Callable) -> None:
        self._preview_callback = cb
