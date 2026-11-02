"""Answer a question from the datasheets: retrieve chunks, ask the LLM, cite pages."""
import os 
import hashlib
import re
import sys
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv
from google import genai
from google.genai import errors, types
from groq import Groq

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "ingest"))
from db import connect  # noqa: E402
from psycopg.types.json import Jsonb  # noqa: E402
from retrieve import DEFAULT_CONFIG, retrieve  # noqa: E402

load_dotenv()

GEMINI_MODEL = "gemini-3.5-flash"
GROQ_MODEL = "openai/gpt-oss-20b"
RETRY_CODES = {429, 500, 503}  # rate limit, server error, overloaded
PROMPT_VERSION = "v2"
NOT_FOUND = "Not found in the datasheets."

SYSTEM_PROMPT = f"""You answer questions about electronic component datasheets.
Use ONLY the numbered context blocks you are given. Do not use outside knowledge.
After every fact, cite its block's label exactly as written, for example [LM358 p.4].
Put one label in each pair of brackets; for two sources write [LM358 p.4] [LM358 p.6].
Give numbers with their units and conditions (typical or maximum, temperature, supply voltage).
If the blocks do not contain the answer, reply with exactly: {NOT_FOUND}
Write plain text only: no LaTeX, no $ signs, no Markdown. Write symbols directly, like ±16 V or 10 µA.
Keep the answer short: one to four sentences."""

CITATION_RE = re.compile(r"\[([A-Za-z0-9]+),?\s*p\.\s*(\d+)\]")

_gemini = None
_groq = None


def label(chunk):
    return f"[{chunk['part'].upper()} p.{chunk['page']}]"


def build_prompt(question, chunks):
    blocks = [
        f"Block {n} {label(c)} ({c['kind']})\n{c['content']}"
        for n, c in enumerate(chunks, 1)
    ]
    context = "\n\n".join(blocks)
    return f"Context blocks:\n\n{context}\n\nQuestion: {question}"


def extract_citations(answer, chunks):
    """Cited (part, page) pairs in order, keeping only pages that were in the context."""
    allowed = {(c["part"], c["page"]) for c in chunks}
    found = []
    for part, page in CITATION_RE.findall(answer):
        pair = (part.lower(), int(page))
        if pair in allowed and pair not in found:
            found.append(pair)
    return [{"part": p, "page": pg} for p, pg in found]


def call_gemini(prompt):
    global _gemini
    if _gemini is None:
        _gemini = genai.Client(
            api_key=os.environ["GEMINI_API_KEY"],
            http_options=types.HttpOptions(timeout=60_000),  # milliseconds
        )
    reply = _gemini.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            thinking_config=types.ThinkingConfig(thinking_level="low"),
        ),
    )
    return (reply.text or "").strip()


def call_groq(prompt):
    global _groq
    if _groq is None:
        _groq = Groq(api_key=os.environ["GROQ_API_KEY"], timeout=60)  # seconds
    reply = _groq.chat.completions.create(
        model=GROQ_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
    )
    return (reply.choices[0].message.content or "").strip()


def generate(prompt):
    """Return (answer, model). Gemini first; on a rate limit retry once, then Groq."""
    for attempt in range(2):
        try:
            return call_gemini(prompt), GEMINI_MODEL
        except errors.APIError as e:
            print(f"Gemini error {e.code} (attempt {attempt + 1})")
            if e.code not in RETRY_CODES:
                break  # not worth retrying, go straight to Groq
            if attempt == 0:
                time.sleep(3)
        except httpx.TimeoutException:
            print(f"Gemini timed out after 60s (attempt {attempt + 1})")
            break  # a hung call is unlikely to recover, go to Groq
    return call_groq(prompt), GROQ_MODEL


def cache_key(question, part, k, config):
    raw = f"{PROMPT_VERSION}|{config}|{k}|{part or ''}|{question.strip().lower()}"
    return hashlib.sha256(raw.encode()).hexdigest()


def cache_get(key):
    with connect() as conn:
        row = conn.execute(
            "SELECT response FROM answer_cache WHERE key = %s", [key]
        ).fetchone()
    return row[0] if row else None


def cache_put(key, question, config, response):
    with connect() as conn:
        conn.execute(
            "INSERT INTO answer_cache (key, question, config, response) "
            "VALUES (%s, %s, %s, %s) "
            "ON CONFLICT (key) DO UPDATE SET response = EXCLUDED.response, created_at = now()",
            [key, question, config, Jsonb(response)],
        )


def ask(question, part=None, k=8, config=DEFAULT_CONFIG, use_cache=True):
    key = cache_key(question, part, k, config)
    if use_cache:
        hit = cache_get(key)
        if hit:
            return {**hit, "cached": True}

    start = time.perf_counter()
    chunks = retrieve(question, k=k, part=part, config=config)
    t_llm = time.perf_counter()
    print(f"retrieved {len(chunks)} chunks in {t_llm - start:.1f}s, asking the LLM...")
    text, model = generate(build_prompt(question, chunks))
    print(f"llm {time.perf_counter() - t_llm:.1f}s")
    not_found = "not found in the datasheets" in text.lower()
    response = {
        "question": question,
        "answer": text,
        "citations": [] if not_found else extract_citations(text, chunks),
        "not_found": not_found,
        "model": model,
        "config": config,
        "sources": [
                        {"n": n, "id": c["id"], "part": c["part"], "page": c["page"], "kind": c["kind"], "score": c["score"]}
            for n, c in enumerate(chunks, 1)
        ],
        "latency_ms": round((time.perf_counter() - start) * 1000),
    }
    if text:
        cache_put(key, question, config, response)
    return {**response, "cached": False}



if __name__ == "__main__":
    q = "What is the maximum supply voltage of the LM358?"
    for _ in range(2):
        r = ask(q)
        print(f"cached={r['cached']} model={r['model']} latency={r['latency_ms']} ms")
        print(r["answer"])
        print("citations:", r["citations"])