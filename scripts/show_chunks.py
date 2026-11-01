"""Print the chunks of one page, to check chunking by eye.

Usage: python scripts/show_chunks.py lm358 4
"""
import json
import sys
from pathlib import Path

part, page = sys.argv[1], int(sys.argv[2])
config = sys.argv[3] if len(sys.argv) > 3 else "s512-o64"
path = Path(__file__).resolve().parent.parent / "data" / "chunks" / f"{config}.jsonl"
with open(path, encoding="utf-8") as f:
    for line in f:
        chunk = json.loads(line)
        if chunk["part"] == part and chunk["page"] == page:
            print(f"=== {chunk['id']} | {chunk['kind']} | {chunk['tokens']} tokens")
            print(chunk["content"], "\n")