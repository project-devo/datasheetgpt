"""Goal 10: retrieval metrics on the frozen eval set.

For each answerable question, run retrieve() and find the rank of the first
chunk from a gold page. Prints recall@1/5/10 and MRR, overall and by type.

Usage: python eval/retrieval.py [--filter] [--config s512-o64]
"""
import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "ingest"))
from retrieve import DEFAULT_CONFIG, MODES, retrieve  # noqa: E402

K = 10
TYPES = ["lookup", "table", "numeric", "cross"]


def load_questions():
    with open(ROOT / "eval" / "questions.jsonl", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def first_gold_rank(results, gold_pages):
    for rank, r in enumerate(results, 1):
        if r["page"] in gold_pages.get(r["part"], []):
            return rank
    return None


def run(questions, use_filter, config, mode):
    rows = []
    for q in questions:
        if not q["gold_pages"]:  # unanswerable: no gold page to find
            continue
        # cross questions cover two parts, so they always search everything
        part = q["parts"][0] if use_filter and len(q["parts"]) == 1 else None
        t = time.perf_counter()
        results = retrieve(q["question"], k=K, part=part, config=config, mode=mode)
        ms = round((time.perf_counter() - t) * 1000)
        rank = first_gold_rank(results, q["gold_pages"])
        got = [f"{r['part']} p{r['page']}" for r in results]
        rows.append({"id": q["id"], "type": q["type"], "rank": rank, "got": got, "ms": ms})
        print(f"{q['id']} {q['type']:<8} rank {rank or '-':<3} {ms} ms")
    return rows


def scores(rows):
    n = len(rows)
    ranks = [r["rank"] for r in rows]

    def recall(k):
        return sum(1 for x in ranks if x and x <= k) / n

    mrr = sum(1 / x for x in ranks if x) / n
    return n, recall(1), recall(5), recall(10), mrr


def print_table(rows):
    print(f"\n{'type':<8} {'n':>3} {'R@1':>6} {'R@5':>6} {'R@10':>6} {'MRR':>6}")
    groups = [(t, [r for r in rows if r["type"] == t]) for t in TYPES]
    groups.append(("all", rows))
    for name, group in groups:
        if not group:
            continue
        n, r1, r5, r10, mrr = scores(group)
        print(f"{name:<8} {n:>3} {r1:>6.0%} {r5:>6.0%} {r10:>6.0%} {mrr:>6.3f}")



def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--filter", action="store_true", help="search only the question's part")
    parser.add_argument("--config", default=DEFAULT_CONFIG)
    parser.add_argument("--mode", choices=MODES, default="vector")
    args = parser.parse_args()

    rows = run(load_questions(), args.filter, args.config, args.mode)
    print_table(rows)
    print(f"\nAverage retrieval time {sum(r['ms'] for r in rows) / len(rows) / 1000:.1f} s")

    misses = [r for r in rows if not r["rank"] or r["rank"] > 5]
    print(f"\nNot in top 5 ({len(misses)}):")
    for r in misses:
        print(f"  {r['id']} {r['type']:<8} rank {r['rank'] or '-'} | {', '.join(r['got'][:5])}")

    label = args.config + ("" if args.mode == "vector" else f"-{args.mode}")
    out = ROOT / "results" / f"retrieval-{label}{'-filter' if args.filter else ''}.jsonl"
    out.parent.mkdir(exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    print(f"\nSaved {len(rows)} rows to {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()