# Declutter Your Home, Calm Your Life (Book 1): paperback update

- `source/V10-...pdf` is the approved v10 (InDesign export, PDF/X-1a). It is the only source available.
- `qr/` holds the client's QR images, decoded and checked. The QR area is cleaned to pure black and white;
  the captions are kept as supplied.
- `edit_v10.py` applies the Oct 12 changes to pages 49, 219 and 221 only and writes `output/V11-...pdf`.

Checks: 227 pages, and every page except 49, 219 and 221 is pixel-identical to v10. Page labels,
PDF/X output intent and layout are kept. The QRs are DeviceGray, they scan to the right URLs, and they
print at 1.5 in (resources) and 1.0 in (review).

## EPUB (Kindle ebook)

- `build_epub.py` (with `pdf_lines.py`) rebuilds the ebook from the V11 PDF, the only source available:
  paragraphs, headings, lists, images, chapter files, a Table of Contents (EPUB nav),
  the two web addresses as links, and alt text on the QR images.
- Output: `output/Declutter_Your_Home_Calm_Your_Life_Alex_Lee.epub`

Checks: EPUBCheck 5.3 reports 0 errors and 0 warnings. The text matches the PDF word for word
(only the printed numbers of the numbered list differ, because the EPUB list numbers itself),
and the paragraph count matches (699).
