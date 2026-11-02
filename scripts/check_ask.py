"""Goal 7 check: 5 eval questions + 1 off-topic question through ask().

Usage: python scripts/check_ask.py [--ids q01 q12 q24 q39 q45]
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "api"))
from answer import ask  # noqa: E402

DEFAULT_IDS = ["q01", "q12", "q24", "q39", "q45"]
OFF_TOPIC = "What is the boiling point of water at sea level?"


def cites_gold(citations, gold_pages):
    return any(c["page"] in gold_pages.get(c["part"], []) for c in citations)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ids", nargs="+", default=DEFAULT_IDS)
    parser.add_argument("--k", type=int, default=8)
    args = parser.parse_args()

    with open(ROOT / "eval" / "questions.jsonl", encoding="utf-8") as f:
        questions = {q["id"]: q for q in map(json.loads, f)}

    gold_hits = 0
    for qid in args.ids:
        q = questions[qid]
        r = ask(q["question"], k=args.k)
        hit = cites_gold(r["citations"], q["gold_pages"])
        gold_hits += hit
        cited = ", ".join(f"{c['part']} p{c['page']}" for c in r["citations"]) or "none"
        print(f"\n{qid} [{r['model']}{', cached' if r['cached'] else ''}] {q['question']}")
        print(f"  expected: {q['answer']}  (gold {q['gold_pages']})")
        print(f"  answer:   {r['answer']}")
        print(f"  cited:    {cited}  -> gold page cited: {'yes' if hit else 'NO'}")
        print("  sources: ", [s.get("id") for s in r["sources"]])

    r = ask(OFF_TOPIC)
    print(f"\noff-topic [{r['model']}] {OFF_TOPIC}")
    print(f"  answer: {r['answer']}  -> not_found: {r['not_found']}")

    print(f"\ngold page cited: {gold_hits}/{len(args.ids)}, off-topic said Not found: {r['not_found']}")


if __name__ == "__main__":
    main()