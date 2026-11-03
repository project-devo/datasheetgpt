"""Write one row per config to results/runs.csv from the Goal 10 and 11 result files."""
import argparse
import csv
import json
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "results"
RUNS = RESULTS / "runs.csv"
FIELDS = ["config", "recall_at_5", "mrr", "answer_acc", "citation_acc",
          "avg_latency_s", "median_latency_s", "notes"]


def load(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f]


def make_row(config, notes):
    ret = load(RESULTS / f"retrieval-{config}.jsonl")
    jud = load(RESULTS / f"judge-{config}.jsonl")

    ranks = [r["rank"] for r in ret]
    recall5 = sum(1 for k in ranks if k and k <= 5) / len(ranks)
    mrr = sum(1 / k for k in ranks if k) / len(ranks)

    correct = sum(1 for j in jud if j["verdict"] == "correct") / len(jud)
    cites = [j["cite_ok"] for j in jud if j["cite_ok"] is not None]
    cite_acc = sum(cites) / len(cites)

    secs = [j["latency_ms"] / 1000 for j in jud]

    return {
        "config": config,
        "recall_at_5": f"{recall5:.3f}",
        "mrr": f"{mrr:.3f}",
        "answer_acc": f"{correct:.3f}",
        "citation_acc": f"{cite_acc:.3f}",
        "avg_latency_s": f"{statistics.mean(secs):.1f}",
        "median_latency_s": f"{statistics.median(secs):.1f}",
        "notes": notes,
    }


def save(row):
    rows = []
    if RUNS.exists():
        with open(RUNS, encoding="utf-8", newline="") as f:
            rows = [r for r in csv.DictReader(f) if r["config"] != row["config"]]
    rows.append(row)
    with open(RUNS, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--config", default="s512-o64")
    p.add_argument("--notes", default="")
    args = p.parse_args()
    row = make_row(args.config, args.notes)
    save(row)
    for key, value in row.items():
        print(f"{key:<17} {value}")
    print(f"\nSaved to {RUNS.relative_to(ROOT)}")


if __name__ == "__main__":
    main()