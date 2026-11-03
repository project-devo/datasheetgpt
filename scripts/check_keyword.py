"""Goal 14 check: how often keyword search finds anything, and a gold page, in its top 20."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "ingest"))
sys.path.insert(0, str(ROOT / "eval"))
from retrieve import keyword_search  # noqa: E402
from retrieval import first_gold_rank, load_questions  # noqa: E402

questions = [q for q in load_questions() if q["gold_pages"]]
for match in ("all", "any"):
    empty, found = [], 0
    for q in questions:
        results = keyword_search(q["question"], k=20, match=match)
        if not results:
            empty.append(q["id"])
        if first_gold_rank(results, q["gold_pages"]):
            found += 1
    print(f"match={match}: no results {len(empty)}/{len(questions)}, gold in top 20 {found}/{len(questions)}")
    print(f"  empty: {' '.join(empty) or '-'}")