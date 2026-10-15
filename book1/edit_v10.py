#!/usr/bin/env python3
"""Declutter Your Home, Calm Your Life: paperback update from v10 (client
request of Oct 12, ebook ASIN B0HMKBDMJG).

The InDesign source of v10 is not available, so the approved v10 PDF is
edited in place on the three pages concerned only; every other page is
untouched. Existing text that has to move down is copied from the original
page as-is (not retyped). New text is set in EB Garamond, the book's body
font, in DeviceGray black (the file is PDF/X-1a: no RGB, no transparency).

  p. 49   "SCAN THE QR CODE" placeholder -> qr-resources-declutter-captioned.png
  p. 219  review URL -> home-review.purposefullivingpress.com + review QR below
  p. 221  new line "You can download the Companion Resources here: <url>",
          old QR -> qr-resources-declutter-captioned.png
"""
from pathlib import Path

import pymupdf

HERE = Path(__file__).resolve().parent
SRC = HERE / "source" / "V10-Declutter_Your_Home_Alex_Lee_6x9.pdf"
OUT = HERE / "output" / "V12-Declutter_Your_Home_Alex_Lee_6x9.pdf"
FONTS = HERE.parent / "declutter-beyond" / "fonts"
QR_RES = HERE / "qr" / "qr-resources-declutter-captioned.png"
QR_REV = HERE / "qr" / "QR_home-review_labeled.png"

ISBN_LINE = "ISBN: 979-8-9821289-0-4 (paperback)"
REVIEW_URL = "home-review.purposefullivingpress.com"
RESOURCES_URL = "resources-declutter.purposefullivingpress.com"
RESOURCES_LINE = "You can download the Companion Resources here:"

# share of the image width taken by the QR symbol (measured on the files)
QR_SHARE = {QR_RES: 1503 / 1799, QR_REV: 1315 / 1640}
IMG_AR = {QR_RES: 2000 / 1799, QR_REV: 1972 / 1640}
CENTER_X = 228.0                     # centre of the recto text block (72-384)
BLACK = (0,)                         # DeviceGray


def qr_rect(img, qr_inches, top):
    w = qr_inches * 72 / QR_SHARE[img]
    h = w * IMG_AR[img]
    return pymupdf.Rect(CENTER_X - w / 2, top, CENTER_X + w / 2, top + h)


def centered(page, text, baseline, font_key, size):
    font = pymupdf.Font(fontfile=str(FONTS / FONT_FILES[font_key]))
    w = font.text_length(text, fontsize=size)
    page.insert_text((CENTER_X - w / 2, baseline), text, fontname=font_key,
                     fontfile=str(FONTS / FONT_FILES[font_key]), fontsize=size, color=BLACK)


FONT_FILES = {"EBGR": "EBGaramond-Regular.ttf", "EBGB": "EBGaramond-Bold.ttf"}


def block(src_doc, pno, clip):
    """One-page document holding only the content inside `clip` of a page."""
    tmp = pymupdf.open()
    tmp.insert_pdf(src_doc, from_page=pno, to_page=pno)
    pg = tmp[0]
    r = pg.rect
    for outside in (pymupdf.Rect(0, 0, r.x1, clip.y0), pymupdf.Rect(0, clip.y1, r.x1, r.y1),
                    pymupdf.Rect(0, clip.y0, clip.x0, clip.y1), pymupdf.Rect(clip.x1, clip.y0, r.x1, clip.y1)):
        pg.add_redact_annot(outside)
    pg.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_REMOVE,
                        graphics=pymupdf.PDF_REDACT_LINE_ART_REMOVE_IF_TOUCHED)
    return tmp


def move(page, src_doc, pno, clip, dy):
    """Draw the original content of `clip` shifted down by dy points."""
    tmp = block(src_doc, pno, clip)
    page.show_pdf_page(clip + (0, dy, 0, dy), tmp, 0, clip=clip)


def clear(page, rect):
    page.add_redact_annot(rect)
    page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_REMOVE,
                          graphics=pymupdf.PDF_REDACT_LINE_ART_NONE)


def gray_image(page, rect, img):
    """Place a QR image as a DeviceGray bitmap (no ICC profile, no alpha), as
    PDF/X-1a requires."""
    pix = pymupdf.Pixmap(str(img))
    if pix.colorspace.n != 1 or pix.alpha:
        pix = pymupdf.Pixmap(pymupdf.csGRAY, pix)
    page.insert_image(rect, pixmap=pix, keep_proportion=True)


def label_index(doc, label):
    hits = doc.get_page_numbers(label)
    assert len(hits) == 1, label
    return hits[0]


def main():
    orig = pymupdf.open(SRC)
    doc = pymupdf.open(SRC)

    # ---- p. 49: placeholder text + temporary QR -> resources QR (1.5 in)
    i = label_index(doc, "49")
    p = doc[i]
    assert "SCAN THE QR CODE" in p.get_text()
    clear(p, pymupdf.Rect(72, 395, 384, 562))
    gray_image(p, qr_rect(QR_RES, 1.5, 397), QR_RES)

    # ---- p. 219: new URL + review QR (1 in); lower block moved down, gaps tightened
    i = label_index(doc, "219")
    p = doc[i]
    assert "YOUR_ASIN" in p.get_text()
    clear(p, pymupdf.Rect(60, 318, 384, 520))
    centered(p, REVIEW_URL, 328.5, "EBGB", 12)
    r = qr_rect(QR_REV, 1.0, 337)
    gray_image(p, r, QR_REV)
    # original blocks (clip rect, original baseline of its first line) -> new baseline
    blocks = [(pymupdf.Rect(60, 350, 384, 368), 362.5),      # Your words matter...
              (pymupdf.Rect(60, 375, 384, 425), 387.5),      # Every review helps... (3 lines)
              (pymupdf.Rect(60, 432, 384, 450), 444.5),      # Thank you for trusting...
              (pymupdf.Rect(60, 470, 384, 514), 483.0)]      # Now go enjoy... / You've earned it.
    new_first = r.y1 + 18
    targets = [new_first, new_first + 22, new_first + 22 + 54, new_first + 22 + 54 + 26]
    for (clip, base), target in zip(blocks, targets):
        move(p, orig, i, clip, target - base)

    # ---- p. ii: paperback ISBN after "First Edition" (client, Oct 15);
    # the DISCLAIMER block moves down by one paragraph step (23 pt)
    i = label_index(doc, "ii")
    p = doc[i]
    assert "First Edition" in p.get_text() and "ISBN" not in p.get_text()
    clear(p, pymupdf.Rect(40, 236, 380, 335))
    move(p, orig, i, pymupdf.Rect(40, 236, 380, 335), 23)
    p.insert_text((50.4, 233.8), ISBN_LINE, fontname="EBGR",
                  fontfile=str(FONTS / FONT_FILES["EBGR"]), fontsize=10.5, color=BLACK)

    # ---- p. 221: add the download line, "SCAN THE QR CODE BELOW" moved down, new QR (1.5 in)
    i = label_index(doc, "221")
    p = doc[i]
    assert "SCAN THE QR CODE BELOW" in p.get_text()
    clear(p, pymupdf.Rect(72, 352, 384, 548))
    centered(p, RESOURCES_LINE, 352.0, "EBGR", 12)
    centered(p, RESOURCES_URL, 368.0, "EBGB", 12)
    move(p, orig, i, pymupdf.Rect(120, 355, 340, 372), 396.0 - 367.3)
    gray_image(p, qr_rect(QR_RES, 1.5, 406), QR_RES)

    for lab in ("49", "219", "221", "ii"):     # PDF/X-1a: plain DeviceGray, no ICC-based colour
        pg = doc[label_index(doc, lab)]
        for im in pg.get_images(full=True):
            if doc.xref_get_key(im[0], "ColorSpace")[0] == "xref":
                doc.xref_set_key(im[0], "ColorSpace", "/DeviceGray")
    for pg in doc:                       # drop the empty /Annots left by the redactions
        if doc.xref_get_key(pg.xref, "Annots") == ("array", "[]"):
            doc.xref_set_key(pg.xref, "Annots", "null")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    doc.save(OUT, garbage=3, deflate=True)
    print("saved", OUT)


if __name__ == "__main__":
    main()
