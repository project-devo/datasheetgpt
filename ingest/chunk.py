"""Split data/parsed/<part>.json blocks into chunks for embedding.

Writes data/chunks/<config>.jsonl, one chunk per line:
{"id", "config", "part", "page", "kind", "section", "tokens", "content"}
content starts with "Part: X | Page: N | Section: S" so retrieval knows the context.
Tokens are counted with the embedding model's own tokenizer (bge-small).
"""
import argparse
import json
from pathlib import Path

from tokenizers import Tokenizer

ROOT = Path(__file__).resolve().parent.parent
PARSED = ROOT / "data" / "parsed"
OUT = ROOT / "data" / "chunks"

tokenizer = Tokenizer.from_pretrained("BAAI/bge-small-en-v1.5")


def count(text):
    return len(tokenizer.encode(text, add_special_tokens=False).ids)


def prefix(block):
    head = f"Part: {block['part'].upper()} | Page: {block['page']}"
    if block["section"]:
        head += f" | Section: {block['section']}"
    return head




def split_long_line(line, budget):
    """Cut one line that is longer than the budget into word groups."""
    pieces, words = [], []
    for word in line.split():
        if words and count(" ".join(words + [word])) > budget:
            pieces.append(" ".join(words))
            words = []
        words.append(word)
    if words:
        pieces.append(" ".join(words))
    return pieces


def split_text(content, budget, overlap):
    """Pack lines into pieces of at most `budget` tokens; repeat ~`overlap` tokens of tail lines."""
    lines = []
    for line in content.split("\n"):
        lines += split_long_line(line, budget) if count(line) > budget else [line]

    pieces, current, size = [], [], 0
    for line in lines:
        n = count(line) + 1  # +1 for the newline
        if current and size + n > budget:
            pieces.append("\n".join(current))
            tail, tail_size = [], 0
            for old in reversed(current):  # carry the last lines over as overlap
                m = count(old) + 1
                if tail_size + m > overlap:
                    break
                tail.insert(0, old)
                tail_size += m
            current, size = tail, tail_size
        current.append(line)
        size += n
    if current:
        pieces.append("\n".join(current))
    return pieces


def split_table(content, budget):
    """Keep a table whole if it fits; else split by rows, repeating caption and header."""
    if count(content) <= budget:
        return [content]
    caption, _, table = content.partition("\n\n")
    rows = table.split("\n")
    head = caption + "\n\n" + "\n".join(rows[:2])  # caption, header row, --- row
    budget_rows = budget - count(head) - 1
    if count(head) > budget // 2:
        return split_text(content, budget, 0)  # header too big to repeat; split it like text
    long_rows = []
    for row in rows[2:]:
        long_rows += split_long_line(row, budget_rows) if count(row) > budget_rows else [row]
    pieces, current, size = [], [], 0
    for row in long_rows:
        n = count(row) + 1
        if current and size + n > budget_rows:
            pieces.append(head + "\n" + "\n".join(current))
            current, size = [], 0
        current.append(row)
        size += n
    if current:
        pieces.append(head + "\n" + "\n".join(current))
    return pieces


def chunk_part(part, size, overlap, config):
    blocks = json.loads((PARSED / f"{part}.json").read_text(encoding="utf-8"))
    chunks, position = [], {}
    for block in blocks:
        head = prefix(block)
        budget = size - count(head) - 3  # room for the prefix, its newline, [CLS] and [SEP]
        if block["kind"] == "table":
            pieces = split_table(block["content"], budget)
        else:
            pieces = split_text(block["content"], budget, overlap)
        for piece in pieces:
            if count(piece) < 5:
                continue  # a stray page number or label is not worth a chunk
            n = position.get(block["page"], 0) + 1
            position[block["page"]] = n
            content = head + "\n" + piece
            chunks.append({"id": f"{part}-p{block['page']:03d}-c{n:02d}", "config": config,
                           "part": part, "page": block["page"], "kind": block["kind"],
                           "section": block["section"], "tokens": count(content) + 2,
                           "content": content})
    return chunks


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--size", type=int, default=512, help="max tokens per chunk")
    parser.add_argument("--overlap", type=int, default=64, help="tokens repeated between text chunks")
    args = parser.parse_args()
    config = f"s{args.size}-o{args.overlap}"

    OUT.mkdir(exist_ok=True)
    parts = sorted(p.stem for p in PARSED.glob("*.json"))
    total = 0
    with open(OUT / f"{config}.jsonl", "w", encoding="utf-8") as f:
        for part in parts:
            chunks = chunk_part(part, args.size, args.overlap, config)
            for chunk in chunks:
                f.write(json.dumps(chunk, ensure_ascii=False) + "\n")
            tables = sum(c["kind"] == "table" for c in chunks)
            biggest = max(c["tokens"] for c in chunks)
            print(f"{part:<11} {len(chunks):>5} chunks  {tables:>4} table  max {biggest} tokens")
            total += len(chunks)
    print(f"total {total} chunks -> data/chunks/{config}.jsonl")

if __name__ == "__main__":
    main()