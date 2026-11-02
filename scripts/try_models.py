"""Try a few Gemini models once each: does it answer, and how fast?"""
import os
import time

from dotenv import load_dotenv
from google import genai
from google.genai import errors, types

load_dotenv()

MODELS = [
    "gemini-3.8-flash", "gemini-3.7-flash", "gemini-3.5-flash",
    "gemini-3.5-flash-lite", "gemini-3.1-flash-lite", "gemini-2.5-flash",
]
client = genai.Client(
    api_key=os.environ["GEMINI_API_KEY"],
    http_options=types.HttpOptions(timeout=60_000),
)

for m in MODELS:
    start = time.perf_counter()
    try:
        r = client.models.generate_content(model=m, contents="In one sentence, what does an LM358 do?")
        print(f"{m:<24} OK   {time.perf_counter() - start:5.1f}s  {(r.text or '').strip()[:60]}")
    except errors.APIError as e:
        print(f"{m:<24} {e.code}  {time.perf_counter() - start:5.1f}s")
    except Exception as e:
        print(f"{m:<24} FAIL {type(e).__name__}")