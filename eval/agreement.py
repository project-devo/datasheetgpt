"""Goal 11: agreement between the LLM judge and my own hand checks.

Fill the "mine" column of results/judge-handcheck.csv with correct, partial
or wrong (your own verdict), then run: python eval/agreement.py
"""
import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FILE = ROOT / "results" / "judge-handcheck.csv"


def main():
    with open(FILE, encoding="utf-8-sig", newline="") as f:
        rows = [r for r in csv.DictReader(f) if r["mine"].strip()]
    if not rows:
        print("Fill the 'mine' column first.")
        return
    agree = [r for r in rows if r["mine"].strip().lower() == r["judge"]]
    print(f"Agreement: {len(agree)}/{len(rows)} = {len(agree) / len(rows):.0%}")
    for r in rows:
        if r not in agree:
            print(f"  {r['id']}: judge {r['judge']}, me {r['mine'].strip().lower()}")


if __name__ == "__main__":
    main()
