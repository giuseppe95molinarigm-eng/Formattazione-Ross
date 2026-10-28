# Declutter Beyond — 6 x 9 KDP print interior (Book 2)

Alex Lee · Purposeful Living Press. The series design follows
"Declutter Your Home, Calm Your Life" (V9, 6x9); the reference PDF is in `source/`.

- `output/Declutter_Beyond_Interior_6x9.pdf` is the print interior (159 pages).
- `source/` holds both reference PDFs from Book 1: the opening excerpt and the final part.
- `build_book.py` goes manuscript .docx → `output/book.html` → PDF, using WeasyPrint.
  It includes a pagination pass for illustrations.
- `book.css` holds the series design, with specs measured from the reference PDF.
- `qc_check.py [checklist.docx]` runs the automated QC and writes `qc/qc_report.txt`.
- `qc_render.py` renders contact sheets for visual review.
- `fonts/` contains only open-licence (OFL) fonts. Avenir (in the reference) is replaced
  by Nunito Sans, and Adobe Caslon Pro Italic by Libre Caslon Text Italic.
  EB Garamond and League Gothic are the same fonts the reference uses.

Rebuild: `pip install weasyprint python-docx pymupdf pillow && python3 build_book.py`

## The Declutter Beyond Toolkit (printable companion)

- `toolkit/output/Declutter_Beyond_Toolkit_Letter.pdf` is the downloadable workbook,
  US Letter (8.5 x 11 in), 16 pages, set for home printing.
- `toolkit/build_toolkit.py` and `toolkit/toolkit.css` build it from
  `toolkit/source/Declutter_Beyond_Checklist_v13_7.docx`, using the same design system as the book.
- The manuscript's underscore lines are drawn as ruled writing lines, one rule per line (158).

Rebuild: `python3 toolkit/build_toolkit.py`

## Revision 1 (client review, Nelson)

- Ink: text 100% black, running heads 80%, labels 60%, rules 40% (Book 1's values).
- Hyphenation: off by default. A composition pass (`tune_text`) tightens tracking, and only
  as a last resort hyphenates long words, in paragraphs with a very loose line. Result: 0.5% of
  lines hyphenated, the same as Book 1. A paragraph's last word is never hyphenated.
- The space above headings, quotes, lists and figures is carried by the preceding element,
  so anything that starts a page sits at the top of the text block.
- Illustrations use the crop set in Word (`images/cropped/`); previously the crop was ignored.
- Wording: "this document" → "this book" (3×, copyright page), listed in `CLIENT_EDITS`.

## Revision 3 (Oct 21, check of the Oct 7 review points)

- Points 1–3 (TOC levels, "to" on p. 42, title/copyright/TOC sequence) were already fixed in the Oct 7 build;
  re-verified on the PDF.
- TOC: leader dots and page numbers now use one style on every entry (EB Garamond 11 pt), so the dot-to-number
  gap is uniform. IDML: tab + number in character style "TOC Number".
- p. 13: the drop cap "I" ("I want…") now keeps a word space after it.
- Pagination unchanged (159 pages); only pages iii, iv and 13 differ from the Oct 7 PDF.

## Revision 4 (client, Oct 28)

- Copyright page: Book 1's wording plus `ISBN: 979-8-9821289-1-1 (paperback)` (`COPYRIGHT` in build_book.py).
- p. 139: review address `beyond-review.purposefullivingpress.com` plus review QR (1 in).
- p. 153: address `resources-declutter.purposefullivingpress.com` plus resources QR (1.5 in), replacing the old QR.
- New: `build_epub.py` builds the Kindle EPUB (`output/Declutter_Beyond_Alex_Lee.epub`) from `output/book.html`,
  with links and QR alt text. EPUBCheck reports 0 errors and 0 warnings.
- Pending: Avenir (Book/Medium/Black) and Adobe Caslon Pro Italic font files, to match Book 1 exactly in the PDF.
  The PDF still uses Nunito Sans and Libre Caslon as stand-ins; the IDML already specifies Avenir and Adobe Caslon Pro.
