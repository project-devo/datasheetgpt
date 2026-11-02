"""Nearest-neighbour check: print the chunks closest to a question.

Usage: python scripts/search.py "maximum supply voltage LM358" [--k 5] [--config s512-o64]
"""
import argparse
import sys
from pathlib import Path

from fastembed import TextEmbedding

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ingest"))
from db import connect  # noqa: E402

MODEL = "BAAI/bge-small-en-v1.5"
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("question")
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--config", default="s512-o64")
    args = parser.parse_args()

    model = TextEmbedding(MODEL)
    vector = next(model.embed([QUERY_PREFIX + args.question]))

    with connect() as conn:
        rows = conn.execute(
            "SELECT id, part, page, kind, embedding <=> %s AS distance, content "
            "FROM chunks WHERE config = %s ORDER BY distance LIMIT %s",
            (vector, args.config, args.k),
        ).fetchall()

    for rank, (chunk_id, part, page, kind, distance, content) in enumerate(rows, 1):
        lines = content.splitlines()
        preview = lines[1][:90] if len(lines) > 1 else ""
        print(f"{rank}. {chunk_id:<22} {part:<11} p{page:<4} {kind:<5} score {1 - distance:.3f}")
        print(f"   {preview}")


if __name__ == "__main__":
    main()