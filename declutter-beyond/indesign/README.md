# InDesign sources

- `idml.py` is a minimal IDML writer, based on an InDesign-exported template (`template/`).
- `build_book_idml.py` builds `Declutter_Beyond_InDesign/Declutter_Beyond_Interior_6x9.idml`
  and its `Links/` folder from `output/book.html` and the approved PDF's page plan.
- `validate_idml.py <file.idml>` checks the package structure and every internal reference.

To use the package: open the .idml in InDesign (File > Open) and save it as .indd.
Keep the `Links` folder next to the file.

## Deliverables

- `Declutter_Beyond_InDesign.zip` is the main book (`.idml`, `Links/`, `Document fonts/`, `READ_ME_FIRST.txt`).
- `Declutter_Beyond_Toolkit_InDesign.zip` is the Toolkit, with the same layout.

Rebuild: `python3 indesign/build_book_idml.py` and `python3 indesign/build_toolkit_idml.py`
(they read `output/book.html` and `toolkit/output/toolkit.html` plus the approved PDFs).

## Checks performed

- `validate_idml.py`: zip layout, well-formed XML, and every reference resolves
  (stories, threaded frames, styles, swatches, masters, variables, sections).
- Opened in Scribus 1.6 (independent IDML importer): both documents import with all pages
  and the book's fonts, and all text is present (`compare_render.py`).
  Scribus does not support paragraph rules or running-head text variables, so those two
  features could not be checked there.
- Not tested in Adobe InDesign itself (not available here).
