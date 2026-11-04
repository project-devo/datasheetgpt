"""Goal 11: grade DatasheetGPT's answers with an LLM judge.

For each question: get the pipeline's answer with ask(), check its citations
against the gold pages in code, and ask a different model (Groq gpt-oss-120b)
whether the answer matches the expected one.

Usage: python eval/judge.py [--ids q01 q02] [--limit 20]
"""
import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from groq import Groq

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT / "api"))
from answer import ask  # noqa: E402
from retrieve import DEFAULT_CONFIG, MODES  # noqa: E402

JUDGE_MODEL = "openai/gpt-oss-120b"
JUDGE_VERSION = "j1"  # bump when the rubric or judge model changes
VERDICTS = ("correct", "partial", "wrong")

RUBRIC = """You grade answers from a datasheet question-answering system.
You get a question, the expected answer written by a human from the datasheet, and the system's answer.
Compare only the facts. Ignore wording, citations in brackets and extra detail that does not contradict the expected answer.
Grades:
- correct: contains the expected value or fact; numbers match (the same value in another unit counts, e.g. 0.5 mA = 500 µA).
- partial: some of the expected answer is right but part is missing or wrong (for example one of two values, or a typical value given when the maximum was asked).
- wrong: the key value or fact is missing or different, or the system said it could not find the answer.
Reply with JSON only: {"verdict": "correct" | "partial" | "wrong", "reason": "<one short sentence>"}"""

_groq = None


def judge_answer(question, expected, answer):
    """Ask the judge model for a verdict. Returns {"verdict", "reason"}."""
    global _groq
    if _groq is None:
        _groq = Groq(api_key=os.environ["GROQ_API_KEY"], timeout=60, max_retries=5)
    user = f"Question: {question}\nExpected answer: {expected}\nSystem answer: {answer}"
    reply = _groq.chat.completions.create(
        model=JUDGE_MODEL,
        messages=[
            {"role": "system", "content": RUBRIC},
            {"role": "user", "content": user},
        ],
        response_format={"type": "json_object"},
        reasoning_effort="low",
        temperature=0,
    )
    data = json.loads(reply.choices[0].message.content)
    if data.get("verdict") not in VERDICTS:
        raise ValueError(f"bad verdict from judge: {data}")
    return {"verdict": data["verdict"], "reason": data.get("reason", "")}



CACHE_FILE = ROOT / "results" / "judge-cache.json"


def load_cache():
    if CACHE_FILE.exists():
        return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    return {}


def save_cache(cache):
    CACHE_FILE.parent.mkdir(exist_ok=True)
    CACHE_FILE.write_text(json.dumps(cache, indent=1, ensure_ascii=False), encoding="utf-8")


def cache_key(question, expected, answer):
    raw = f"{JUDGE_VERSION}|{question}|{expected}|{answer}"
    return hashlib.sha256(raw.encode()).hexdigest()


def cites_gold(citations, gold_pages):
    return any(c["page"] in gold_pages.get(c["part"], []) for c in citations)


def grade(q, r, cache):
    """Verdict for one question: code decides the Not found cases, the judge the rest."""
    if not q["gold_pages"]:  # unanswerable question
        if r["not_found"]:
            return {"verdict": "correct", "reason": "said Not found", "by": "code"}
        return {"verdict": "wrong", "reason": "answered an unanswerable question", "by": "code"}
    if r["not_found"]:
        return {"verdict": "wrong", "reason": "said Not found but the answer exists", "by": "code"}
    key = cache_key(q["question"], q["answer"], r["answer"])
    if key not in cache:
        cache[key] = judge_answer(q["question"], q["answer"], r["answer"])
        save_cache(cache)
        time.sleep(2)  # stay under Groq's free per-minute limits
    return {**cache[key], "by": "judge"}


def load_questions():
    with open(ROOT / "eval" / "questions.jsonl", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def run(questions, config, mode="vector", use_cache=True):
    cache = load_cache()
    rows = []
    for q in questions:
        r = ask(q["question"], config=config, mode=mode, use_cache=use_cache)
        g = grade(q, r, cache)
        cite_ok = cites_gold(r["citations"], q["gold_pages"]) if q["gold_pages"] else None
        rows.append({
            "id": q["id"], "type": q["type"], "verdict": g["verdict"], "by": g["by"],
            "reason": g["reason"], "cite_ok": cite_ok, "question": q["question"],
            "expected": q["answer"], "answer": r["answer"], "citations": r["citations"],
            "model": r["model"], "cached": r["cached"], "latency_ms": r["latency_ms"],
        })
        cite = "-" if cite_ok is None else ("gold" if cite_ok else "NOT gold")
        print(f"{q['id']} {q['type']:<12} {g['verdict']:<8} cite {cite:<8} {r['model']}")
    return rows


TYPES = ["lookup", "table", "numeric", "cross", "unanswerable"]


def share(group, verdict):
    return sum(r["verdict"] == verdict for r in group) / len(group)


def print_summary(rows):
    print(f"\n{'type':<12} {'n':>3} {'correct':>8} {'partial':>8} {'wrong':>6} {'cite':>6}")
    groups = [(t, [r for r in rows if r["type"] == t]) for t in TYPES]
    groups.append(("all", rows))
    for name, group in groups:
        if not group:
            continue
        cited = [r["cite_ok"] for r in group if r["cite_ok"] is not None]
        cite = f"{sum(cited) / len(cited):.0%}" if cited else "-"
        print(f"{name:<12} {len(group):>3} {share(group, 'correct'):>8.0%} "
              f"{share(group, 'partial'):>8.0%} {share(group, 'wrong'):>6.0%} {cite:>6}")

    latency = sum(r["latency_ms"] for r in rows) / len(rows)
    groq = sum("gemini" not in r["model"] for r in rows)
    print(f"\nAverage answer latency {latency / 1000:.1f} s; answered by the Groq fallback: {groq}")

    bad = [r for r in rows if r["verdict"] != "correct"]
    print(f"\nNot correct ({len(bad)}):")
    for r in bad:
        print(f"  {r['id']} {r['type']:<12} {r['verdict']:<8} {r['reason']}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ids", nargs="+", help="only these question ids")
    parser.add_argument("--limit", type=int, help="only the first N questions")
    parser.add_argument("--config", default=DEFAULT_CONFIG)
    parser.add_argument("--mode", choices=MODES, default="vector")
    parser.add_argument("--no-cache", action="store_true", help="ask the LLM again instead of reusing cached answers")
    args = parser.parse_args()

    questions = load_questions()
    if args.ids:
        questions = [q for q in questions if q["id"] in args.ids]
    if args.limit:
        questions = questions[: args.limit]

    rows = run(questions, config=args.config, mode=args.mode, use_cache=not args.no_cache)
    print_summary(rows)

    label = args.config + ("" if args.mode == "vector" else f"-{args.mode}")
    out = ROOT / "results" / f"judge-{label}.jsonl"
    with open(out, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"\nSaved {len(rows)} rows to {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()