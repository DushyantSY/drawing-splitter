"""
ui/settings_dialog.py - Settings, region, and regex configuration dialog.
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, QWidget,
    QLabel, QLineEdit, QDoubleSpinBox, QComboBox, QPushButton,
    QFileDialog, QFormLayout, QGroupBox, QMessageBox, QSpinBox,
    QDialogButtonBox,
)
from PySide6.QtCore import Qt
import re
import copy
from typing import Dict, Any


class SettingsDialog(QDialog):
    """Modal settings dialog with tabs: General, Title Block, Regex, OCR."""

    def __init__(self, settings: Dict[str, Any], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumWidth(540)
        self.setModal(True)

        # Work on a deep copy; only apply on OK
        self._settings = copy.deepcopy(settings)
        self._build_ui()
        self._load_values()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        tabs = QTabWidget()
        tabs.addTab(self._build_general_tab(), "General")
        tabs.addTab(self._build_region_tab(), "Title Block Region")
        tabs.addTab(self._build_regex_tab(), "Regex Patterns")
        tabs.addTab(self._build_ocr_tab(), "OCR")
        layout.addWidget(tabs)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self._on_ok)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _build_general_tab(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        form.setSpacing(10)

        # Output duplicate handling
        self._dup_combo = QComboBox()
        self._dup_combo.addItem("Append _2, _3 (recommended)", True)
        self._dup_combo.addItem("Overwrite", False)
        form.addRow("Duplicate filenames:", self._dup_combo)

        # Fallback prefix
        self._fallback_edit = QLineEdit()
        self._fallback_edit.setPlaceholderText("PAGE")
        form.addRow("Fallback name prefix:", self._fallback_edit)

        return w

    def _build_region_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setSpacing(12)

        # Preset selector
        preset_box = QGroupBox("Preset")
        preset_layout = QHBoxLayout(preset_box)
        self._preset_combo = QComboBox()
        self._preset_combo.addItems(["bottom-right", "bottom-center", "custom"])
        self._preset_combo.currentTextChanged.connect(self._apply_preset)
        preset_layout.addWidget(self._preset_combo)
        layout.addWidget(preset_box)

        # Custom region inputs
        region_box = QGroupBox("Custom Region (% of page dimensions)")
        form = QFormLayout(region_box)
        form.setSpacing(8)

        def pct_spin():
            s = QDoubleSpinBox()
            s.setRange(0.0, 100.0)
            s.setSingleStep(1.0)
            s.setDecimals(1)
            s.setSuffix(" %")
            return s

        self._x_start = pct_spin()
        self._y_start = pct_spin()
        self._x_end = pct_spin()
        self._y_end = pct_spin()

        form.addRow("X start (left edge):", self._x_start)
        form.addRow("Y start (top edge):", self._y_start)
        form.addRow("X end (right edge):", self._x_end)
        form.addRow("Y end (bottom edge):", self._y_end)
        layout.addWidget(region_box)

        hint = QLabel(
            "Tip: For a bottom-right title block, typical values are\n"
            "X: 60%→100%,  Y: 78%→100%"
        )
        hint.setStyleSheet("color: #888; font-size: 11px;")
        layout.addWidget(hint)
        layout.addStretch()

        return w

    def _build_regex_tab(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        form.setSpacing(12)

        self._re_drawing = QLineEdit()
        self._re_drawing.setFont(self._monofont())
        form.addRow("Drawing number:", self._re_drawing)

        self._re_rev_primary = QLineEdit()
        self._re_rev_primary.setFont(self._monofont())
        form.addRow("Revision (primary):", self._re_rev_primary)

        self._re_rev_fallback = QLineEdit()
        self._re_rev_fallback.setFont(self._monofont())
        form.addRow("Revision (fallback):", self._re_rev_fallback)

        test_btn = QPushButton("Validate Patterns")
        test_btn.clicked.connect(self._validate_regex)
        form.addRow("", test_btn)

        hint = QLabel(
            "Patterns use Python regex syntax.\n"
            "Each pattern must contain exactly one capture group ( ... )."
        )
        hint.setStyleSheet("color: #888; font-size: 11px;")
        form.addRow("", hint)

        return w

    def _build_ocr_tab(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        form.setSpacing(12)

        # OCR mode
        self._ocr_mode = QComboBox()
        self._ocr_mode.addItem("Auto (OCR only when needed)", "auto")
        self._ocr_mode.addItem("Always use OCR", "always")
        self._ocr_mode.addItem("Never use OCR", "never")
        form.addRow("OCR mode:", self._ocr_mode)

        # Tesseract path
        path_row = QHBoxLayout()
        self._tess_path = QLineEdit()
        self._tess_path.setPlaceholderText(
            r"C:\Program Files\Tesseract-OCR\tesseract.exe"
        )
        path_row.addWidget(self._tess_path)
        browse_btn = QPushButton("Browse…")
        browse_btn.setFixedWidth(80)
        browse_btn.clicked.connect(self._browse_tesseract)
        path_row.addWidget(browse_btn)
        form.addRow("Tesseract path:", path_row)

        # OCR DPI
        self._ocr_dpi = QSpinBox()
        self._ocr_dpi.setRange(72, 600)
        self._ocr_dpi.setSingleStep(50)
        self._ocr_dpi.setSuffix(" DPI")
        form.addRow("Render DPI:", self._ocr_dpi)

        # OCR language
        self._ocr_lang = QLineEdit()
        self._ocr_lang.setPlaceholderText("eng")
        form.addRow("Tesseract language:", self._ocr_lang)

        # PSM
        self._ocr_psm = QSpinBox()
        self._ocr_psm.setRange(0, 13)
        form.addRow("Page segmentation mode (PSM):", self._ocr_psm)

        hint = QLabel("PSM 6 = single block of text (recommended for title blocks).")
        hint.setStyleSheet("color: #888; font-size: 11px;")
        form.addRow("", hint)

        return w

    # ------------------------------------------------------------------
    # Load / save values
    # ------------------------------------------------------------------

    def _load_values(self) -> None:
        s = self._settings
        out = s["output"]
        tb = s["title_block"]
        rx = s["regex"]
        ocr = s["ocr"]

        # General
        idx = 0 if out.get("duplicate_suffix", True) else 1
        self._dup_combo.setCurrentIndex(idx)
        self._fallback_edit.setText(out.get("fallback_prefix", "PAGE"))

        # Region
        preset = tb.get("preset", "bottom-right")
        idx = self._preset_combo.findText(preset)
        self._preset_combo.setCurrentIndex(max(idx, 0))
        self._x_start.setValue(tb.get("x_start_pct", 60.0))
        self._y_start.setValue(tb.get("y_start_pct", 78.0))
        self._x_end.setValue(tb.get("x_end_pct", 100.0))
        self._y_end.setValue(tb.get("y_end_pct", 100.0))

        # Regex
        self._re_drawing.setText(rx.get("drawing_number", ""))
        self._re_rev_primary.setText(rx.get("revision_primary", ""))
        self._re_rev_fallback.setText(rx.get("revision_fallback", ""))

        # OCR
        mode = s.get("ocr_mode", "auto")
        for i in range(self._ocr_mode.count()):
            if self._ocr_mode.itemData(i) == mode:
                self._ocr_mode.setCurrentIndex(i)
                break
        self._tess_path.setText(s.get("tesseract_path", ""))
        self._ocr_dpi.setValue(ocr.get("dpi", 300))
        self._ocr_lang.setText(ocr.get("language", "eng"))
        self._ocr_psm.setValue(ocr.get("psm", 6))

    def _collect_values(self) -> None:
        s = self._settings
        s["output"]["duplicate_suffix"] = self._dup_combo.currentData()
        s["output"]["fallback_prefix"] = self._fallback_edit.text().strip() or "PAGE"

        s["title_block"]["preset"] = self._preset_combo.currentText()
        s["title_block"]["x_start_pct"] = self._x_start.value()
        s["title_block"]["y_start_pct"] = self._y_start.value()
        s["title_block"]["x_end_pct"] = self._x_end.value()
        s["title_block"]["y_end_pct"] = self._y_end.value()

        s["regex"]["drawing_number"] = self._re_drawing.text().strip()
        s["regex"]["revision_primary"] = self._re_rev_primary.text().strip()
        s["regex"]["revision_fallback"] = self._re_rev_fallback.text().strip()

        s["ocr_mode"] = self._ocr_mode.currentData()
        s["tesseract_path"] = self._tess_path.text().strip()
        s["ocr"]["dpi"] = self._ocr_dpi.value()
        s["ocr"]["language"] = self._ocr_lang.text().strip() or "eng"
        s["ocr"]["psm"] = self._ocr_psm.value()

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _apply_preset(self, preset: str) -> None:
        presets = {
            "bottom-right":  (60.0, 78.0, 100.0, 100.0),
            "bottom-center": (25.0, 78.0, 75.0, 100.0),
        }
        if preset in presets:
            x0, y0, x1, y1 = presets[preset]
            self._x_start.setValue(x0)
            self._y_start.setValue(y0)
            self._x_end.setValue(x1)
            self._y_end.setValue(y1)

    def _browse_tesseract(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Tesseract Executable",
            r"C:\Program Files\Tesseract-OCR",
            "Executables (*.exe);;All Files (*)",
        )
        if path:
            self._tess_path.setText(path)

    def _validate_regex(self) -> None:
        patterns = {
            "Drawing number": self._re_drawing.text(),
            "Revision (primary)": self._re_rev_primary.text(),
            "Revision (fallback)": self._re_rev_fallback.text(),
        }
        errors = []
        for name, pat in patterns.items():
            if not pat:
                continue
            try:
                compiled = re.compile(pat, re.IGNORECASE)
                if compiled.groups == 0:
                    errors.append(f"{name}: pattern has no capture group.")
            except re.error as e:
                errors.append(f"{name}: {e}")
        if errors:
            QMessageBox.warning(self, "Invalid Patterns", "\n".join(errors))
        else:
            QMessageBox.information(self, "Validation Passed", "All patterns are valid ✓")

    def _on_ok(self) -> None:
        self._collect_values()
        self.accept()

    def get_settings(self) -> Dict[str, Any]:
        return self._settings

    @staticmethod
    def _monofont():
        from PySide6.QtGui import QFont
        f = QFont("Consolas")
        f.setPointSize(10)
        return f
