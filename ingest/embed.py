"""Embed one chunking config and load it into Neon.

Usage: python ingest/embed.py [--config s512-o64]
Deletes that config's rows first, so it is safe to re-run.
"""
import argparse
import json
import time
from pathlib import Path

from fastembed import TextEmbedding

from db import connect, create_schema

ROOT = Path(__file__).resolve().parent.parent
CHUNKS = ROOT / "data" / "chunks"
MODEL = "BAAI/bge-small-en-v1.5"
BATCH = 64


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="s512-o64", help="file in data/chunks, without .jsonl")
    args = parser.parse_args()

    with open(CHUNKS / f"{args.config}.jsonl", encoding="utf-8") as f:
        chunks = [json.loads(line) for line in f]
    print(f"{len(chunks)} chunks in {args.config}")
    for c in chunks:
        c["content"] = c["content"].replace("\x00", "")
        c["section"] = c["section"].replace("\x00", "")

    model = TextEmbedding(MODEL)
    start = time.time()
    vectors = list(model.embed([c["content"] for c in chunks], batch_size=BATCH))
    print(f"embedded in {time.time() - start:.0f} s, {len(vectors[0])} numbers each")

    create_schema()
    with connect() as conn:
        conn.execute("DELETE FROM chunks WHERE config = %s", (args.config,))
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO chunks (config, id, part, page, kind, section, content, embedding) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                [(args.config, c["id"], c["part"], c["page"], c["kind"], c["section"],
                  c["content"], v) for c, v in zip(chunks, vectors)],
            )
        count = conn.execute("SELECT count(*) FROM chunks WHERE config = %s",
                             (args.config,)).fetchone()[0]
    print(f"{count} rows in Neon for {args.config}")


if __name__ == "__main__":
    main()