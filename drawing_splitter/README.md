# Drawing Splitter

A production-grade Windows desktop application for splitting multi-page engineering
drawing PDFs into individual files auto-named using the drawing number and revision
extracted from the title block.

---

## Features

- Splits any multi-page PDF into individual one-page PDFs
- Extracts drawing number and revision from the title block region
- Direct PDF text extraction first; OCR fallback when needed (Tesseract)
- Configurable title-block region (percentage-based, presets available)
- Editable regex patterns for drawing number and revision
- Page preview with title-block overlay before batch run
- Test mode (process first N pages only)
- CSV processing log (page, drawing#, revision, filename, status, remarks)
- Results table in UI with colour-coded status
- Duplicate filename handling (_2, _3 suffixes)
- Dark professional UI

---

## Project Structure

```
drawing_splitter/
├── app.py                    Entry point
├── requirements.txt
├── README.md
├── config/
│   └── settings.json         Persisted user settings
├── core/
│   ├── config.py             Settings loader/saver
│   ├── pdf_processor.py      PDF reading, splitting, rendering
│   ├── ocr.py                Tesseract OCR wrapper
│   ├── extractor.py          Regex extraction logic
│   ├── namer.py              Filename sanitization + dedup
│   └── logger.py             CSV log writer
└── ui/
    ├── main_window.py        Main application window
    ├── settings_dialog.py    Settings / regex / region dialog
    ├── preview_panel.py      Page preview widget
    └── worker.py             QThread batch processing worker
```

---

## Requirements

- **Python 3.10 or later** (3.11/3.12 recommended)
- **Windows 10 or Windows 11**
- **Tesseract OCR** (only required if your PDFs are scanned / non-selectable text)

---

## Setup

### 1. Clone or download

```
git clone https://github.com/yourorg/drawing-splitter.git
cd drawing-splitter
```

Or simply unzip the source folder.

### 2. Create a virtual environment (recommended)

```cmd
python -m venv .venv
.venv\Scripts\activate
```

### 3. Install Python dependencies

```cmd
pip install -r requirements.txt
```

### 4. Install Tesseract OCR (Windows)

Tesseract is only needed if your PDFs contain scanned (rasterized) pages with no
selectable text. If your PDFs have embedded text, skip this step.

**Steps:**

1. Download the latest Windows installer from:
   https://github.com/UB-Mannheim/tesseract/wiki

   Direct link (64-bit, English):
   `tesseract-ocr-w64-setup-5.x.x.exe`

2. Run the installer. Default install path:
   `C:\Program Files\Tesseract-OCR\`

3. During installation, ensure **English** language data is selected (it is by default).

4. (Optional) Add Tesseract to your PATH:
   - Open **System Properties → Advanced → Environment Variables**
   - Edit the **Path** variable under System variables
   - Add `C:\Program Files\Tesseract-OCR`

5. Verify the installation:
   ```cmd
   tesseract --version
   ```

6. In Drawing Splitter, open **Settings → OCR tab** and set the Tesseract path to:
   ```
   C:\Program Files\Tesseract-OCR\tesseract.exe
   ```

---

## Running the Application

```cmd
python app.py
```

---

## Usage

### Basic workflow

1. Click **Browse…** next to **Input PDF** and select your multi-page drawing PDF.
2. Click **Browse…** next to **Output folder** and choose where to save split files.
3. Click **▶ Start Processing**.
4. Results appear in the table. A CSV log is written to the output folder.

### Page Preview

- Use the **Page Preview** panel on the right to inspect any page before processing.
- The **yellow overlay** shows the current title-block region.
- Click **Load Preview** to render the selected page.
- Click **Test Extraction** to run the full extraction pipeline on that page and see
  what drawing number and revision would be extracted.

### Test Mode

Enable **Test mode** and set the page count (default 3) to run extraction on only
the first N pages. Useful for verifying settings on a large file.

### Settings

Click **⚙ Settings** to configure:

| Tab | Options |
|-----|---------|
| **General** | Duplicate handling, fallback prefix |
| **Title Block Region** | Preset (bottom-right, bottom-center, custom), X/Y percentages |
| **Regex Patterns** | Drawing number and revision regex patterns |
| **OCR** | OCR mode (auto/always/never), Tesseract path, DPI, language, PSM |

Settings are saved to `config/settings.json` automatically.

---

## Default Regex Patterns

| Field | Pattern |
|-------|---------|
| Drawing number | `([A-Z0-9]{2,}(?:-[A-Z0-9]+){4,})` |
| Revision (primary) | `\b(?:REV(?:ISION)?)[\s:._-]*([A-Z0-9]+)\b` |
| Revision (fallback) | `\b(R[0-9A-Z]+)\b` |

These match formats like:
- Drawing numbers: `TU-ER-JV-IB-GFC-CNT-CS-207`
- Revisions: `R1`, `R0`, `REV-1`, `REV A`, `REVISION 01`

To match a different drawing number format, update the pattern in Settings → Regex.

---

## Output Naming

| Extraction result | Output filename |
|-------------------|-----------------|
| Both found | `TU-ER-JV-IB-GFC-CNT-CS-207_R1.pdf` |
| Drawing number only | `TU-ER-JV-IB-GFC-CNT-CS-207_NOREV.pdf` |
| Neither found | `PAGE_0001_NONUM.pdf` |
| Duplicate | `TU-ER-JV-IB-GFC-CNT-CS-207_R1_2.pdf` |

---

## CSV Log

Each batch run writes a log file to the output folder:
`<source_pdf_name>_log_YYYYMMDD_HHMMSS.csv`

Columns:

| Column | Description |
|--------|-------------|
| `page_number` | 1-based page number |
| `extracted_text` | Output filename (text truncated if long) |
| `drawing_number` | Extracted drawing number or blank |
| `revision` | Extracted revision or blank |
| `output_filename` | Final output filename |
| `status` | Success / OCR used / Manual review needed / Failed |
| `remarks` | Any warnings or errors for that page |

---

## Packaging to EXE (PyInstaller)

### 1. Install PyInstaller

```cmd
pip install pyinstaller
```

### 2. Build standalone EXE

Run this from the `drawing_splitter` directory:

```cmd
pyinstaller ^
  --name "DrawingSplitter" ^
  --onefile ^
  --windowed ^
  --icon=assets\icon.ico ^
  --add-data "config;config" ^
  --hidden-import=fitz ^
  --hidden-import=PIL ^
  app.py
```

**Notes:**
- `--onefile` bundles everything into a single EXE (slower startup, easier to distribute).
- `--windowed` suppresses the console window.
- Remove `--icon` if you don't have an icon file.
- The resulting EXE will be in the `dist/` folder.

### 3. Distribute

Copy `dist\DrawingSplitter.exe` to the target machine.
Tesseract must still be installed separately on the target machine if OCR is needed.

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| "Tesseract not found" | Set the full path in Settings → OCR |
| Drawing number not extracted | Check the title block region — use Preview + Test Extraction to verify the region covers the right area |
| Revision not found | Add a revision pattern in Settings → Regex that matches your format |
| PDF is password-protected | Decrypt the PDF first (Adobe Acrobat, qpdf, etc.) |
| Very slow on large PDFs | Increase the Y start % to reduce the title block region size; avoid OCR if text is selectable |

---

## License

MIT License. See LICENSE file.
