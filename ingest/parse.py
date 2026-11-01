"""Parse every datasheet in data/ into data/parsed/<part>.json.

Each output file is a list of blocks in reading order:
{"part", "page", "kind" ("text" or "table"), "section", "content"}
Text comes from PyMuPDF, tables from pdfplumber (as Markdown),
and section names from the PDF's bookmarks.
"""
import json
import re
import sys
from collections import Counter
from pathlib import Path

import pdfplumber
import pymupdf

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUT = DATA / "parsed"


def read_lines(page, skip_boxes):
    """Text lines of one page as (top, text, in_margin), leaving out table areas."""
    margin = page.rect.height * 0.10  # headers and footers sit in the top and bottom 10%
    lines = []
    for x0, y0, x1, y1, text, _, kind in page.get_text("blocks"):
        if kind != 0:
            continue  # kind 1 is a picture
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        if any(a <= cx <= c and b <= cy <= d for a, b, c, d in skip_boxes):
            continue  # inside a table; the table block already has this text
        in_margin = y0 < margin or y1 > page.rect.height - margin
        for line in text.splitlines():
            if line.strip():
                lines.append((y0, line.strip(), in_margin))
    return lines



def clean_cell(cell):
    return (cell or "").replace("\n", " ").replace("|", "/").strip()


def to_markdown(rows):
    """Turn pdfplumber rows into a Markdown table, dropping empty columns."""
    rows = [[clean_cell(c) for c in row] for row in rows]
    keep = [i for i in range(len(rows[0])) if any(row[i] for row in rows)]
    rows = [[row[i] for i in keep] for row in rows]
    rows = [row for row in rows if any(row)]
    if len(rows) < 2 or len(keep) < 2:
        return None  # one row or one column is not a real table
    lines = ["| " + " | ".join(rows[0]) + " |", "|" + " --- |" * len(keep)]
    lines += ["| " + " | ".join(row) + " |" for row in rows[1:]]
    return "\n".join(lines)


def page_sections(doc):
    """Page number -> bookmark titles that start on that page, in order."""
    starts = {}
    for level, title, page in doc.get_toc():
        if re.match(r"(Table|Figure)\s", title):
            continue  # ST bookmarks every table and figure; those aren't sections
        starts.setdefault(page, []).append(title.strip())
    return starts


def repeated_lines(all_pages):
    """Margin lines (digits ignored) on at least a third of the pages: headers and footers."""
    counts = Counter()
    for lines in all_pages:
        counts.update({re.sub(r"\d+", "#", text) for _, text, edge in lines if edge})
    limit = max(3, len(all_pages) // 3)
    return {key for key, n in counts.items() if n >= limit}


def page_blocks(part, number, tables, lines, titles, section):
    """Merge one page's text lines and tables into blocks, top to bottom."""
    items = [(top, "text", text) for top, text in lines]
    items += [(box[1], "table", markdown) for box, markdown in tables]
    items.sort(key=lambda item: item[0])

    blocks, text, last_line = [], [], ""
    for top, kind, value in items:
        new_section = (kind == "text" and titles
                       and value.lower().startswith(titles[0].lower()[:25]))
        if text and (kind == "table" or new_section):
            blocks.append({"part": part, "page": number, "kind": "text",
                           "section": section, "content": "\n".join(text)})
            text = []
        if new_section:
            section = titles.pop(0)
        if kind == "text":
            text.append(value)
            last_line = value
        else:
            caption = last_line or section  # the line just above the table
            blocks.append({"part": part, "page": number, "kind": "table",
                           "section": section, "content": caption + "\n\n" + value})
    if text:
        blocks.append({"part": part, "page": number, "kind": "text",
                       "section": section, "content": "\n".join(text)})
    if titles:
        section = titles[-1]  # titles we couldn't spot still start on this page
    return blocks, section


def parse(part):
    pdf_path = DATA / f"{part}.pdf"
    doc = pymupdf.open(pdf_path)

    # pass 1: find tables, and read the text outside them
    pages = []
    with pdfplumber.open(pdf_path) as pdf:
        for number, plumb_page in enumerate(pdf.pages, start=1):
            tables = []
            for table in plumb_page.find_tables():
                markdown = to_markdown(table.extract(x_tolerance=1.5))
                if markdown:
                    tables.append((table.bbox, markdown))
            lines = read_lines(doc[number - 1], [box for box, _ in tables])
            pages.append((tables, lines))
            plumb_page.flush_cache()  # keeps memory low on the 653-page ATmega
            if number % 100 == 0:
                print(f"  {part}: page {number}/{len(pdf.pages)}", flush=True)

    # pass 2: drop headers and footers, then build blocks page by page
    junk = repeated_lines([lines for _, lines in pages])
    starts = page_sections(doc)
    blocks, section = [], ""
    for number, (tables, lines) in enumerate(pages, start=1):
        lines = [(top, text) for top, text, edge in lines
                 if not (edge and re.sub(r"\d+", "#", text) in junk)]
        titles = list(starts.get(number, []))
        new_blocks, section = page_blocks(part, number, tables, lines, titles, section)
        blocks += new_blocks
    return blocks


def main():
    OUT.mkdir(exist_ok=True)
    parts = sys.argv[1:] or sorted(p.stem for p in DATA.glob("*.pdf"))
    for part in parts:
        blocks = parse(part)
        with open(OUT / f"{part}.json", "w", encoding="utf-8") as f:
            json.dump(blocks, f, ensure_ascii=False, indent=1)
        tables = sum(b["kind"] == "table" for b in blocks)
        print(f"{part:<11} {len(blocks):>5} blocks  {tables:>4} tables")

if __name__ == "__main__":
    main()