"""
Drawing Splitter - Entry point
Engineering drawing PDF splitter with auto-naming from title block extraction.
"""

import sys
import os

# Ensure the app directory is on the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon

from ui.main_window import MainWindow
from core.config import load_settings


def main():
    # High-DPI support
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setApplicationName("Drawing Splitter")
    app.setApplicationVersion("1.0.0")
    app.setOrganizationName("EngineeringTools")

    # Load persisted settings before building UI
    settings = load_settings()

    window = MainWindow(settings)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
