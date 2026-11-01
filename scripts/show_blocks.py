"""Print the parsed blocks of one page, to compare against the PDF.

Usage: python scripts/show_blocks.py lm358 10
"""
import json
import sys
from pathlib import Path

part, page = sys.argv[1], int(sys.argv[2])
path = Path(__file__).resolve().parent.parent / "data" / "parsed" / f"{part}.json"
for block in json.loads(path.read_text(encoding="utf-8")):
    if block["page"] == page:
        print(f"--- {block['kind']} | section: {block['section']}")
        print(block["content"], "\n")