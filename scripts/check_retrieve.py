"""Goal 6 check: is a gold page in the top k for 5 known questions?

Usage: python scripts/check_retrieve.py [--ids q01 q12 q24 q39 q45] [--k 5]
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "ingest"))
from retrieve import retrieve  # noqa: E402

DEFAULT_IDS = ["q01", "q12", "q24", "q39", "q45"]


def first_gold_rank(results, gold_pages):
    for rank, r in enumerate(results, 1):
        if r["page"] in gold_pages.get(r["part"], []):
            return rank
    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ids", nargs="+", default=DEFAULT_IDS)
    parser.add_argument("--k", type=int, default=5)
    args = parser.parse_args()

    questions = {}
    with open(ROOT / "eval" / "questions.jsonl", encoding="utf-8") as f:
        for line in f:
            q = json.loads(line)
            questions[q["id"]] = q

    for use_filter in (False, True):
        label = "with part filter" if use_filter else "no filter"
        print(f"\n== {label} ==")
        hits = 0
        for qid in args.ids:
            q = questions[qid]
            part = q["parts"][0] if use_filter else None
            results = retrieve(q["question"], k=args.k, part=part)
            rank = first_gold_rank(results, q["gold_pages"])
            hits += rank is not None
            got = ", ".join(f"{r['part']} p{r['page']}" for r in results)
            print(f"{qid} gold {q['gold_pages']} -> rank {rank or '-'} | {got}")
        print(f"gold page in top {args.k}: {hits}/{len(args.ids)}")


if __name__ == "__main__":
    main()