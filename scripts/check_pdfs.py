"""Check every datasheet in data/ and write data/sources.csv.

For each PDF it counts the pages and the pages with almost no selectable
text (a sign of a scanned image). Revisions are typed into PARTS by hand.
"""
import csv
import re
from pathlib import Path

import pymupdf  # this is PyMuPDF

DATA = Path(__file__).resolve().parent.parent / "data"
MIN_CHARS = 50  # a real text page has hundreds of characters; a scan has ~0

# part id (= file name), manufacturer, URL, revision (fill in by hand)
PARTS = [
    ("esp32", "Espressif", "https://www.espressif.com/sites/default/files/documentation/esp32_datasheet_en.pdf", "Version 5.3"),
    ("atmega328p", "Microchip", "https://ww1.microchip.com/downloads/aemDocuments/documents/MCU08/ProductDocuments/DataSheets/ATmega48A-PA-88A-PA-168A-PA-328-P-DS-DS40002061B.pdf", "DS40002061B"),
    ("stm32f103", "STMicroelectronics", "https://www.st.com/resource/en/datasheet/stm32f103c8.pdf", "DS5319 Rev 20"),
    ("lm358", "Texas Instruments", "https://www.ti.com/lit/ds/symlink/lm358.pdf", "SLOS068AB (revised Oct 2024)"),
    ("ne555", "Texas Instruments", "https://www.ti.com/lit/ds/symlink/ne555.pdf", "SLFS022K (revised Mar 2026"),
    ("lm317", "Texas Instruments", "https://www.ti.com/lit/ds/symlink/lm317.pdf", "SLVS044Z (revised Apr 2025)"),
    ("mcp3008", "Microchip", "https://ww1.microchip.com/downloads/aemDocuments/documents/MCU08/ProductDocuments/DataSheets/MCP3004-MCP3008-Data-Sheet-DS20001295.pdf", "DS20001295E"),
    ("bme280", "Bosch Sensortec", "https://www.bosch-sensortec.com/media/boschsensortec/downloads/datasheets/bst-bme280-ds002.pdf", "1.24"),
]

# lines on page 1 that look like a revision, to help you fill in PARTS
REV_HINT = re.compile(r"\b(rev(ision)?|version)\b|DS\d{5,}", re.IGNORECASE)

rows = []
for part, maker, url, revision in PARTS:
    path = DATA / f"{part}.pdf"
    if not path.exists():
        print(f"{part}: MISSING data/{path.name}")
        continue

    with pymupdf.open(path) as doc:
        pages = doc.page_count
        low_text = [i + 1 for i, page in enumerate(doc)
                    if len(page.get_text().strip()) < MIN_CHARS]
        first_page = doc[0].get_text().splitlines()

    # a few blank or picture-only pages are normal; many means a scan
    status = "OK" if len(low_text) <= max(3, pages * 0.05) else "CHECK: maybe scanned"
    print(f"{part:<11} {pages:>4} pages   low-text pages: {len(low_text):<3} {status}")
    if low_text:
        print(f"            low-text page numbers: {low_text[:10]}")
    if not revision:
        hints = [line.strip() for line in first_page if REV_HINT.search(line)][:2]
        print(f"            revision not filled in; page 1 says: {hints}")

    rows.append({"part": part, "manufacturer": maker, "url": url,
                 "revision": revision, "pages": pages, "file": path.name})

with open(DATA / "sources.csv", "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=["part", "manufacturer", "url", "revision", "pages", "file"])
    writer.writeheader()
    writer.writerows(rows)

print(f"\nWrote {len(rows)} rows to data/sources.csv")