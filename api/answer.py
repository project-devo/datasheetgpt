"""Answer a question from the datasheets: retrieve chunks, ask the LLM, cite pages."""
import os
import csv
import hashlib
import json
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
from tools import convert_units, voltage_divider  # noqa: E402

load_dotenv()

GEMINI_MODEL = "gemini-3.1-flash-lite"  # 3.5-flash free tier: only ~20 requests/day
GROQ_MODEL = "openai/gpt-oss-20b"
RETRY_CODES = {429, 500, 503}  # rate limit, server error, overloaded
PROMPT_VERSION = "v5"
NOT_FOUND = "Not found in the datasheets."
DEFAULT_MODE = "hybrid"  # Goal 16: live setup (reranker too big for Render free)
MAX_TOOL_CALLS = 2  # Goal 17: a looping model can't burn the free quota
TOOLS = {"voltage_divider": voltage_divider, "convert_units": convert_units}

GROQ_TOOLS = [
    {"type": "function", "function": {
        "name": "voltage_divider",
        "description": "Output voltage of a resistor divider: vin through r1 (top) then r2 (bottom) to ground.",
        "parameters": {"type": "object", "properties": {
            "vin": {"type": "number", "description": "input voltage in volts"},
            "r1": {"type": "number", "description": "top resistor in ohms"},
            "r2": {"type": "number", "description": "bottom resistor in ohms"},
        }, "required": ["vin", "r1", "r2"]},
    }},
    {"type": "function", "function": {
        "name": "convert_units",
        "description": "Convert between metric prefixes of the same unit, like mA to A or kohm to ohm.",
        "parameters": {"type": "object", "properties": {
            "value": {"type": "number", "description": "the number to convert"},
            "from_unit": {"type": "string", "description": "unit of value, e.g. mA, kohm, MHz, uF"},
            "to_unit": {"type": "string", "description": "unit to convert to, e.g. A, ohm, Hz, nF"},
        }, "required": ["value", "from_unit", "to_unit"]},
    }},
]

SYSTEM_PROMPT = f"""You answer questions about electronic component datasheets.
Use ONLY the numbered context blocks you are given and the calculator tools. Do not use outside knowledge.
After every fact, cite its block's label exactly as written, for example [LM358 p.4].
Put one label in each pair of brackets; for two sources write [LM358 p.4] [LM358 p.6].
Give numbers with their units and conditions (typical or maximum, temperature, supply voltage).
Write plain text only: no LaTeX, no $ signs, no Markdown. Write symbols directly, like ±16 V or 10 µA.
For any calculation (voltage divider output, unit conversion), call the matching tool instead of doing the maths yourself. Take the inputs from the question or the context blocks.
A calculation whose inputs are all in the question is answerable even if the blocks say nothing about it: call the tool and give its result; cite blocks only for values taken from them.
Reply with exactly: {NOT_FOUND} only if neither the blocks nor a tool can answer the question.
Keep the answer short: one to four sentences."""

CITATION_RE = re.compile(r"\[([A-Za-z0-9]+),?\s*p\.\s*(\d+)\]")

# Goal 18: manufacturer PDF link per part, so a citation chip can open <url>#page=N
with open(ROOT / "data" / "sources.csv", encoding="utf-8") as f:
    PDF_URLS = {row["part"]: row["url"] for row in csv.DictReader(f)}

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


def run_tool(name, args):
    """Run one tool the model asked for. Errors go back to the model as text, not a crash."""
    func = TOOLS.get(name)
    if func is None:
        return {"error": f"unknown tool '{name}'"}
    try:
        return {"result": func(**args)}
    except (TypeError, ValueError) as e:
        return {"error": str(e)}


def gemini_client():
    global _gemini
    if _gemini is None:
        _gemini = genai.Client(
            api_key=os.environ["GEMINI_API_KEY"],
            http_options=types.HttpOptions(timeout=60_000),  # milliseconds
        )
    return _gemini


def groq_client():
    global _groq
    if _groq is None:
        _groq = Groq(api_key=os.environ["GROQ_API_KEY"], timeout=60, max_retries=5)  # seconds; retries wait out the 8K tokens/min limit
    return _groq


def gemini_config(allow_tools):
    return types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        thinking_config=types.ThinkingConfig(thinking_level="low"),
        tools=list(TOOLS.values()),  # the SDK reads type hints + docstrings
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        tool_config=types.ToolConfig(function_calling_config=types.FunctionCallingConfig(
            mode="AUTO" if allow_tools else "NONE")),
    )


def call_gemini(prompt):
    """Return (answer, tool_runs). Runs at most MAX_TOOL_CALLS tools, then forces a text answer."""
    contents = [types.Content(role="user", parts=[types.Part.from_text(text=prompt)])]
    tool_runs = []
    for _ in range(MAX_TOOL_CALLS + 1):
        allow = len(tool_runs) < MAX_TOOL_CALLS
        reply = gemini_client().models.generate_content(
            model=GEMINI_MODEL, contents=contents, config=gemini_config(allow))
        if not reply.function_calls or not allow:
            return (reply.text or "").strip(), tool_runs
        contents.append(reply.candidates[0].content)  # keep the model's turn (and its thought signature)
        results = []
        for call in reply.function_calls:
            args = dict(call.args or {})
            if len(tool_runs) < MAX_TOOL_CALLS:
                result = run_tool(call.name, args)
                tool_runs.append({"tool": call.name, "args": args, **result})
            else:
                result = {"error": "tool limit reached; answer with what you have"}
            results.append(types.Part.from_function_response(name=call.name, response=result))
        contents.append(types.Content(role="user", parts=results))
    return "", tool_runs


def call_groq(prompt):
    """Return (answer, tool_runs). Same tool loop as Gemini, in Groq's message format."""
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ]
    tool_runs = []
    for _ in range(MAX_TOOL_CALLS + 1):
        allow = len(tool_runs) < MAX_TOOL_CALLS
        reply = groq_client().chat.completions.create(
            model=GROQ_MODEL, messages=messages,
            tools=GROQ_TOOLS, tool_choice="auto" if allow else "none")
        msg = reply.choices[0].message
        if not msg.tool_calls or not allow:
            return (msg.content or "").strip(), tool_runs
        messages.append({"role": "assistant", "content": msg.content or "", "tool_calls": [
            {"id": tc.id, "type": "function",
             "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
            for tc in msg.tool_calls]})
        for tc in msg.tool_calls:
            args = json.loads(tc.function.arguments or "{}")
            if len(tool_runs) < MAX_TOOL_CALLS:
                result = run_tool(tc.function.name, args)
                tool_runs.append({"tool": tc.function.name, "args": args, **result})
            else:
                result = {"error": "tool limit reached; answer with what you have"}
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": json.dumps(result)})
    return "", tool_runs


def generate(prompt):
    """Return (answer, model). Gemini first; on a rate limit retry once, then Groq."""
    for attempt in range(2):
        try:
            text, tool_runs = call_gemini(prompt)
            return text, GEMINI_MODEL, tool_runs
        except errors.APIError as e:
            print(f"Gemini error {e.code} (attempt {attempt + 1})")
            if e.code not in RETRY_CODES:
                break  # not worth retrying, go straight to Groq
            if attempt == 0:
                time.sleep(3)
        except httpx.TimeoutException:
            print(f"Gemini timed out after 60s (attempt {attempt + 1})")
            break  # a hung call is unlikely to recover, go to Groq
    text, tool_runs = call_groq(prompt)
    return text, GROQ_MODEL, tool_runs


def stream_gemini(prompt, tool_runs):
    """Like call_gemini, but yields answer text as it arrives and each tool run (a dict) as it happens."""
    contents = [types.Content(role="user", parts=[types.Part.from_text(text=prompt)])]
    for _ in range(MAX_TOOL_CALLS + 1):
        allow = len(tool_runs) < MAX_TOOL_CALLS
        calls, model_parts = [], []
        for chunk in gemini_client().models.generate_content_stream(
                model=GEMINI_MODEL, contents=contents, config=gemini_config(allow)):
            if not chunk.candidates or not chunk.candidates[0].content:
                continue
            for part in chunk.candidates[0].content.parts or []:
                model_parts.append(part)
                if part.function_call:
                    calls.append(part.function_call)
                elif part.text and not part.thought:
                    yield part.text
        if not calls or not allow:
            return
        contents.append(types.Content(role="model", parts=model_parts))  # keeps the thought signature
        results = []
        for call in calls:
            args = dict(call.args or {})
            if len(tool_runs) < MAX_TOOL_CALLS:
                result = run_tool(call.name, args)
                run = {"tool": call.name, "args": args, **result}
                tool_runs.append(run)
                yield run
            else:
                result = {"error": "tool limit reached; answer with what you have"}
            results.append(types.Part.from_function_response(name=call.name, response=result))
        contents.append(types.Content(role="user", parts=results))


def stream_groq(prompt, tool_runs):
    """Like call_groq, but streamed. Tool calls arrive in pieces, so they are glued together first."""
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ]
    for _ in range(MAX_TOOL_CALLS + 1):
        allow = len(tool_runs) < MAX_TOOL_CALLS
        stream = groq_client().chat.completions.create(
            model=GROQ_MODEL, messages=messages, stream=True,
            tools=GROQ_TOOLS, tool_choice="auto" if allow else "none")
        text, calls = "", {}  # calls: index -> {id, name, arguments}
        for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            if delta.content:
                text += delta.content
                yield delta.content
            for tc in delta.tool_calls or []:
                c = calls.setdefault(tc.index, {"id": "", "name": "", "arguments": ""})
                if tc.id:
                    c["id"] = tc.id
                if tc.function and tc.function.name:
                    c["name"] = tc.function.name
                if tc.function and tc.function.arguments:
                    c["arguments"] += tc.function.arguments
        if not calls or not allow:
            return
        calls = [calls[i] for i in sorted(calls)]
        messages.append({"role": "assistant", "content": text, "tool_calls": [
            {"id": c["id"], "type": "function",
             "function": {"name": c["name"], "arguments": c["arguments"]}} for c in calls]})
        for c in calls:
            args = json.loads(c["arguments"] or "{}")
            if len(tool_runs) < MAX_TOOL_CALLS:
                result = run_tool(c["name"], args)
                run = {"tool": c["name"], "args": args, **result}
                tool_runs.append(run)
                yield run
            else:
                result = {"error": "tool limit reached; answer with what you have"}
            messages.append({"role": "tool", "tool_call_id": c["id"], "content": json.dumps(result)})


def generate_stream(prompt, info):
    """Streamed generate(): yields text pieces and tool runs. Puts the model and tool runs in info.
    Gemini first; it can only fall back to Groq if no answer text was sent yet."""
    for attempt in range(2):
        if attempt:
            yield {"retry": True}  # tells the page to forget tool runs shown from the failed try
        info["tools"], sent = [], False
        try:
            for piece in stream_gemini(prompt, info["tools"]):
                sent = sent or isinstance(piece, str)
                yield piece
            info["model"] = GEMINI_MODEL
            return
        except errors.APIError as e:
            print(f"Gemini error {e.code} (attempt {attempt + 1})")
            if sent:
                raise  # half an answer is already on screen; can't switch models now
            if e.code not in RETRY_CODES:
                break
            if attempt == 0:
                time.sleep(3)
        except httpx.TimeoutException:
            print(f"Gemini timed out after 60s (attempt {attempt + 1})")
            if sent:
                raise
            break
    info["tools"] = []
    info["model"] = GROQ_MODEL
    yield {"retry": True}
    yield from stream_groq(prompt, info["tools"])


def cache_key(question, part, k, config, mode="vector"):
    raw = f"{PROMPT_VERSION}|{config}|{k}|{part or ''}|{question.strip().lower()}"
    if mode != "vector":
        raw += f"|{mode}"
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


def ask(question, part=None, k=8, config=DEFAULT_CONFIG, use_cache=True, mode=DEFAULT_MODE):
    key = cache_key(question, part, k, config, mode)
    if use_cache:
        hit = cache_get(key)
        if hit:
            return {**hit, "mode": mode, "cached": True}

    start = time.perf_counter()
    chunks = retrieve(question, k=k, part=part, config=config, mode=mode)
    t_llm = time.perf_counter()
    print(f"retrieved {len(chunks)} chunks in {t_llm - start:.1f}s, asking the LLM...")
    text, model, tool_runs = generate(build_prompt(question, chunks))
    print(f"llm {time.perf_counter() - t_llm:.1f}s")
    response = make_response(question, text, model, tool_runs, config, chunks, start)
    if text:
        cache_put(key, question, config, response)
    return {**response, "mode": mode, "cached": False}


def make_response(question, text, model, tool_runs, config, chunks, start):
    not_found = "not found in the datasheets" in text.lower()
    return {
        "question": question,
        "answer": text,
        "citations": [] if not_found else extract_citations(text, chunks),
        "not_found": not_found,
        "model": model,
        "tools": tool_runs,
        "config": config,
        "sources": [
                        {"n": n, "id": c["id"], "part": c["part"], "page": c["page"], "kind": c["kind"], "score": c["score"]}
            for n, c in enumerate(chunks, 1)
        ],
        "latency_ms": round((time.perf_counter() - start) * 1000),
    }


def with_urls(citations):
    """Add the manufacturer PDF link at the cited page, e.g. .../lm358.pdf#page=4"""
    return [{**c, "url": f"{PDF_URLS[c['part']]}#page={c['page']}"} if c["part"] in PDF_URLS else c
            for c in citations]


def ask_stream(question, part=None, k=8, config=DEFAULT_CONFIG, use_cache=True, mode=DEFAULT_MODE):
    """Streamed ask() for POST /ask/stream. Yields events (dicts with a "type"):
    status -> tool (0-2) -> token (many) -> done (the full ask() response, citations with PDF links)."""
    key = cache_key(question, part, k, config, mode)
    if use_cache:
        hit = cache_get(key)
        if hit:
            yield {"type": "token", "text": hit["answer"]}
            yield {"type": "done", **hit, "citations": with_urls(hit["citations"]),
                   "mode": mode, "cached": True}
            return

    start = time.perf_counter()
    yield {"type": "status", "text": "Searching the datasheets"}
    chunks = retrieve(question, k=k, part=part, config=config, mode=mode)
    yield {"type": "status", "text": "Writing the answer"}
    info, pieces = {}, []
    for piece in generate_stream(build_prompt(question, chunks), info):
        if isinstance(piece, str):
            pieces.append(piece)
            yield {"type": "token", "text": piece}
        elif piece.get("retry"):
            pieces = []
            yield {"type": "retry"}
        else:
            yield {"type": "tool", **piece}
    text = "".join(pieces).strip()
    response = make_response(question, text, info["model"], info["tools"], config, chunks, start)
    if text:
        cache_put(key, question, config, response)
    yield {"type": "done", **response, "citations": with_urls(response["citations"]),
           "mode": mode, "cached": False}



if __name__ == "__main__":
    for q in ["What output voltage does a 10k/4.7k divider give from the ESP32's 3.3 V?",
              "Convert 250 mA to A",
              "What is the maximum supply voltage of the LM358?"]:  # no tool expected
        r = ask(q, use_cache=False)
        print(f"\n{q}\nmodel={r['model']} latency={r['latency_ms']} ms")
        print(r["answer"])
        print("tools:", r["tools"])
        print("citations:", r["citations"])

    print("\nStreaming:")
    for event in ask_stream("What is the typical input offset voltage of the LM358 at 25 °C?", use_cache=False):
        if event["type"] == "token":
            print(event["text"], end="", flush=True)
        elif event["type"] == "done":
            print(f"\n[{event['model']}, {event['latency_ms']} ms] {event['citations']}")
        else:
            print(f"\n<{event}>")