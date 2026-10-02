# InDesign sources (work in progress)

- `idml.py` is a minimal IDML writer, based on an InDesign-exported template (`template/`).
- `build_book_idml.py` builds `Declutter_Beyond_InDesign/Declutter_Beyond_Interior_6x9.idml`
  and its `Links/` folder from `output/book.html` and the approved PDF's page plan.
- `validate_idml.py <file.idml>` checks the package structure and every internal reference.

To use the package: open the .idml in InDesign (File > Open) and save it as .indd.
Keep the `Links` folder next to the file.
