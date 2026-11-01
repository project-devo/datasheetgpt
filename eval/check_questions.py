"""Check eval/questions.jsonl for mistakes and show progress toward 60.

Run it after every few questions: python eval/check_questions.py
"""
import csv
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
QUESTIONS = ROOT / "eval" / "questions.jsonl"

TARGET_TOTAL = 60
TARGET_TYPES = {"lookup": 25, "table": 15, "numeric": 10, "cross": 5, "unanswerable": 5}
FIELDS = ["id", "parts", "type", "question", "answer", "gold_pages"]

# part id -> page count, from the sources.csv written in Goal 2
with open(ROOT / "data" / "sources.csv", encoding="utf-8") as f:
    PAGES = {row["part"]: int(row["pages"]) for row in csv.DictReader(f)}


def problems(q):
    """Return a list of what is wrong with one question (empty = fine)."""
    found = []
    missing = [k for k in FIELDS if k not in q]
    if missing:
        return [f"missing fields {missing}"]

    if q["type"] not in TARGET_TYPES:
        found.append(f"type '{q['type']}' must be one of {list(TARGET_TYPES)}")
    if not str(q["question"]).strip() or not str(q["answer"]).strip():
        found.append("question and answer can't be empty")

    parts = q["parts"]
    if not isinstance(parts, list) or not parts:
        return found + ['parts must be a list, like ["esp32"]']
    unknown = [p for p in parts if p not in PAGES]
    if unknown:
        return found + [f"unknown part {unknown}; use {list(PAGES)}"]
    if q["type"] == "cross" and len(parts) != 2:
        found.append("a cross question needs exactly 2 parts")
    if q["type"] != "cross" and len(parts) != 1:
        found.append("only cross questions can have 2 parts")

    gold = q["gold_pages"]
    if not isinstance(gold, dict):
        return found + ['gold_pages must look like {"esp32": [5]}']
    if q["type"] == "unanswerable":
        if gold:
            found.append("unanswerable questions need gold_pages {}")
        if q["answer"] != "Not found":
            found.append('unanswerable questions need answer "Not found"')
        return found

    if set(gold) != set(parts):
        found.append(f"gold_pages needs pages for exactly these parts: {parts}")
    for part, pages in gold.items():
        if not isinstance(pages, list) or not pages:
            found.append(f"gold_pages[{part}] must be a non-empty list of page numbers")
            continue
        for p in pages:
            if not isinstance(p, int) or not 1 <= p <= PAGES.get(part, 0):
                found.append(f"page {p} is not a real page of {part} (1 to {PAGES.get(part)})")
    return found


errors = []
ids, questions = set(), set()
types, per_part = Counter(), Counter()
total = 0

with open(QUESTIONS, encoding="utf-8") as f:
    for n, line in enumerate(f, start=1):
        if not line.strip():
            continue  # blank lines are allowed
        try:
            q = json.loads(line)
        except json.JSONDecodeError as e:
            errors.append(f"line {n}: not valid JSON ({e.msg}, column {e.colno})")
            continue
        total += 1
        label = f"line {n} ({q.get('id', 'no id')})"

        for problem in problems(q):
            errors.append(f"{label}: {problem}")
        if q.get("id") in ids:
            errors.append(f"{label}: id used twice")
        ids.add(q.get("id"))
        text = str(q.get("question", "")).strip().lower()
        if text in questions:
            errors.append(f"{label}: same question written twice")
        questions.add(text)

        types[q.get("type")] += 1
        for part in q.get("parts", []) if isinstance(q.get("parts"), list) else []:
            per_part[part] += 1

print(f"Questions: {total} / {TARGET_TOTAL}\n")
print("By type (have / target):")
for t, target in TARGET_TYPES.items():
    print(f"  {t:<13} {types[t]:>2} / {target}")
print("\nBy part (cross questions count for both parts):")
for part in PAGES:
    print(f"  {part:<11} {per_part[part]:>2}")

if errors:
    print(f"\n{len(errors)} problem(s):")
    for e in errors:
        print("  " + e)
elif total == TARGET_TOTAL:
    print("\nAll 60 questions pass. Ready to freeze.")
else:
    print("\nNo problems so far.")