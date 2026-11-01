"""Find which PDF pages of one datasheet mention some words.

Usage: python scripts/find_pages.py esp32 "deep-sleep"
Page numbers are PDF pages as the viewer shows them (cover = 1).
"""
import sys
from pathlib import Path

import pymupdf  # PyMuPDF

DATA = Path(__file__).resolve().parent.parent / "data"
MAX_SHOWN = 30  # the ATmega file is huge; don't flood the terminal

if len(sys.argv) < 3:
    sys.exit('usage: python scripts/find_pages.py <part> "<words>"')

part = sys.argv[1]
words = " ".join(sys.argv[2:]).lower()

hits = 0
with pymupdf.open(DATA / f"{part}.pdf") as doc:
    for i, page in enumerate(doc):
        text = page.get_text()
        pos = text.lower().find(words)
        if pos == -1:
            continue
        hits += 1
        if hits <= MAX_SHOWN:
            # a short piece of text around the match, on one line
            snippet = " ".join(text[max(0, pos - 60): pos + 80].split())
            print(f"p.{i + 1}: ...{snippet}...")

print(f"\n{hits} page(s) mention '{words}'")