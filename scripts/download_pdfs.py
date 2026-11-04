"""Download the 8 datasheet PDFs listed in data/sources.csv into data/.

Usage: python scripts/download_pdfs.py
Skips files that are already there. Some manufacturer sites refuse
scripts; if one fails, open its URL in a browser and save it as
data/<part>.pdf.
"""
import csv
from pathlib import Path

import httpx

DATA = Path(__file__).resolve().parent.parent / "data"
# a normal browser User-Agent; some sites block the default Python one
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                         "(KHTML, like Gecko) Chrome/140.0 Safari/537.36"}


def main():
    with open(DATA / "sources.csv", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    failed = []
    for row in rows:
        path = DATA / row["file"]
        if path.exists():
            print(f"{row['part']:<11} already there")
            continue
        try:
            r = httpx.get(row["url"], headers=HEADERS, follow_redirects=True, timeout=120)
            r.raise_for_status()
            if not r.content.startswith(b"%PDF"):
                raise ValueError("response is not a PDF")
            path.write_bytes(r.content)
            print(f"{row['part']:<11} {len(r.content) / 1e6:.1f} MB")
        except Exception as e:  # keep going so one bad site doesn't stop the rest
            print(f"{row['part']:<11} FAILED: {e}")
            failed.append(row)

    for row in failed:
        print(f"Download by hand: {row['url']}  ->  data/{row['file']}")


if __name__ == "__main__":
    main()
