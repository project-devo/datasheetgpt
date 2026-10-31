"""Prove the Gemini and Groq API keys work: one tiny call to each."""
import os
import sys

from dotenv import load_dotenv
from google import genai
from groq import Groq

load_dotenv()  # finds .env in the repo root and loads it into os.environ

GEMINI_MODEL = "gemini-3.8-flash"
GROQ_MODEL = "openai/gpt-oss-20b"
PROMPT = "In one short sentence, what does an LM358 chip do?"


def check_gemini() -> bool:
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        print("Gemini: GEMINI_API_KEY is missing from .env")
        return False
    try:
        client = genai.Client(api_key=key)
        reply = client.models.generate_content(model=GEMINI_MODEL, contents=PROMPT)
        print(f"Gemini ({GEMINI_MODEL}): {(reply.text or '').strip()}")
        return True
    except Exception as e:
        print(f"Gemini failed: {e}")
        return False


def check_groq() -> bool:
    key = os.getenv("GROQ_API_KEY")
    if not key:
        print("Groq: GROQ_API_KEY is missing from .env")
        return False
    try:
        client = Groq(api_key=key)
        reply = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[{"role": "user", "content": PROMPT}],
        )
        print(f"Groq ({GROQ_MODEL}): {reply.choices[0].message.content.strip()}")
        return True
    except Exception as e:
        print(f"Groq failed: {e}")
        return False


if __name__ == "__main__":
    results = [check_gemini(), check_groq()]  # a list, so both always run
    if all(results):
        print("Both keys work.")
    else:
        sys.exit(1)