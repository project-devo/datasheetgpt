"""Goal 16: results table (Markdown) and recall@5 bar chart from results/runs.csv."""
import csv
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # draw straight to a file, no window
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "results"
LIVE = "s512-o64-hybrid"
# runs.csv config -> label, in the order the experiments happened
LABELS = {
    "s512-o64": "512 chunks (baseline)",
    "s256-o64": "256 chunks",
    "s1024-o64": "1024 chunks",
    "s512-o64-hybrid": "hybrid (live)",
    "s512-o64-rerank-small": "hybrid + MiniLM",
    "s512-o64-rerank": "hybrid + bge rerank",
}


def pct(value):
    return f"{float(value):.0%}" if value else "-"


def main():
    with open(RESULTS / "runs.csv", encoding="utf-8", newline="") as f:
        by_config = {r["config"]: r for r in csv.DictReader(f)}
    rows = [by_config[c] for c in LABELS if c in by_config]

    lines = [
        "| config | recall@5 | MRR | answer accuracy | citation accuracy | median latency |",
        "|---|---|---|---|---|---|",
    ]
    for r in rows:
        latency = f"{r['median_latency_s']} s" if r["median_latency_s"] else "-"
        lines.append(f"| {LABELS[r['config']]} | {pct(r['recall_at_5'])} | {r['mrr']} | "
                     f"{pct(r['answer_acc'])} | {pct(r['citation_acc'])} | {latency} |")
    (RESULTS / "results.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))

    names = [LABELS[r["config"]] for r in rows]
    values = [float(r["recall_at_5"]) * 100 for r in rows]
    colors = ["#2b6cb0" if r["config"] == LIVE else "#a0aec0" for r in rows]
    fig, ax = plt.subplots(figsize=(8, 4.5))
    bars = ax.bar(names, values, color=colors)
    ax.bar_label(bars, fmt="%.0f%%")
    ax.set_ylabel("recall@5 (%)")
    ax.set_ylim(0, 100)
    ax.set_title("Recall@5 on 55 answerable questions, by config")
    ax.spines[["top", "right"]].set_visible(False)
    plt.xticks(rotation=20, ha="right")
    fig.tight_layout()
    fig.savefig(RESULTS / "recall_at_5.png", dpi=150)
    print("\nSaved results/results.md and results/recall_at_5.png")


if __name__ == "__main__":
    main()