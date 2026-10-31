"""Print the model names our keys can actually use."""
import os

from dotenv import load_dotenv
from google import genai
from groq import Groq

load_dotenv()

print("Gemini models that can generate text:")
gemini = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
for m in gemini.models.list():
    if "generateContent" in (m.supported_actions or []):
        print("  ", m.name)

print("\nGroq models:")
groq = Groq(api_key=os.getenv("GROQ_API_KEY"))
for m in groq.models.list().data:
    print("  ", m.id)