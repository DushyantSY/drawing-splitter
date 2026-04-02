"""
core/ocr.py - Tesseract OCR wrapper.

Accepts image bytes (PNG/JPEG) and returns extracted text.
Falls back gracefully when Tesseract is unavailable or misconfigured.
"""

import os
import subprocess
import tempfile
import shutil
from typing import Optional


class OCRError(Exception):
    pass


class OCREngine:
    """
    Thin wrapper around Tesseract CLI.
    We call the Tesseract binary directly for maximum portability on Windows
    without requiring pytesseract as an intermediary.
    """

    def __init__(self, tesseract_path: str, language: str = "eng", psm: int = 6):
        self.tesseract_path = tesseract_path
        self.language = language
        self.psm = psm
        self._available: Optional[bool] = None

    def is_available(self) -> bool:
        """Check once whether the Tesseract binary is reachable."""
        if self._available is not None:
            return self._available

        path = self.tesseract_path
        if not path:
            self._available = False
            return False

        # Also check PATH
        if not os.path.isfile(path):
            resolved = shutil.which("tesseract")
            if resolved:
                self.tesseract_path = resolved
                self._available = True
                return True
            self._available = False
            return False

        try:
            result = subprocess.run(
                [path, "--version"],
                capture_output=True,
                timeout=10,
            )
            self._available = result.returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            self._available = False

        return self._available

    def run_ocr(self, image_bytes: bytes) -> str:
        """
        Run Tesseract on image_bytes (PNG/JPEG).
        Returns extracted text or raises OCRError.
        """
        if not self.is_available():
            raise OCRError(
                f"Tesseract not found at '{self.tesseract_path}'. "
                "Please install Tesseract and update the path in Settings."
            )

        # Write image to a temp file, run Tesseract, read output
        tmp_dir = tempfile.mkdtemp()
        try:
            img_path = os.path.join(tmp_dir, "region.png")
            out_base = os.path.join(tmp_dir, "output")

            with open(img_path, "wb") as f:
                f.write(image_bytes)

            cmd = [
                self.tesseract_path,
                img_path,
                out_base,
                "-l", self.language,
                "--psm", str(self.psm),
                "txt",
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                timeout=60,
            )

            if result.returncode != 0:
                stderr = result.stderr.decode("utf-8", errors="replace").strip()
                raise OCRError(f"Tesseract exited with code {result.returncode}: {stderr}")

            out_txt = out_base + ".txt"
            if not os.path.isfile(out_txt):
                raise OCRError("Tesseract did not produce output file.")

            with open(out_txt, "r", encoding="utf-8", errors="replace") as f:
                text = f.read()

            return text.strip()

        except subprocess.TimeoutExpired:
            raise OCRError("Tesseract timed out (>60 s). Page may be too complex.")
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def preprocess_for_ocr(self, image_bytes: bytes) -> bytes:
        """
        Optional: enhance image contrast/binarize before OCR.
        Requires Pillow. If Pillow is unavailable, returns original bytes.
        """
        try:
            from PIL import Image, ImageEnhance, ImageFilter
            import io

            img = Image.open(io.BytesIO(image_bytes)).convert("L")  # Grayscale

            # Increase contrast
            enhancer = ImageEnhance.Contrast(img)
            img = enhancer.enhance(2.0)

            # Mild sharpening
            img = img.filter(ImageFilter.SHARPEN)

            buf = io.BytesIO()
            img.save(buf, format="PNG")
            return buf.getvalue()

        except ImportError:
            return image_bytes
        except Exception:
            return image_bytes
