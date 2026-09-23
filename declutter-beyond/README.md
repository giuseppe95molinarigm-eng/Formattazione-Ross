# Declutter Beyond — 6 x 9 KDP print interior (Book 2)

Alex Lee · Purposeful Living Press. The series design follows
"Declutter Your Home, Calm Your Life" (V9, 6x9); the reference PDF is in `source/`.

- `output/Declutter_Beyond_Interior_6x9.pdf` is the print interior (159 pages).
- `build_book.py` goes manuscript .docx → `output/book.html` → PDF, using WeasyPrint.
  It includes a pagination pass for illustrations.
- `book.css` holds the series design, with specs measured from the reference PDF.
- `qc_check.py [checklist.docx]` runs the automated QC and writes `qc/qc_report.txt`.
- `qc_render.py` renders contact sheets for visual review.
- `fonts/` contains only open-licence (OFL) fonts. Avenir (in the reference) is replaced
  by Nunito Sans, and Adobe Caslon Pro Italic by Libre Caslon Text Italic.
  EB Garamond and League Gothic are the same fonts the reference uses.

Rebuild: `pip install weasyprint python-docx pymupdf pillow && python3 build_book.py`
