"""Hugging Face Space entry point: the FastAPI API plus a small Gradio page."""
import sys
from pathlib import Path

import gradio as gr
import uvicorn

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "api"))
sys.path.insert(0, str(ROOT / "ingest"))

from main import PARTS, app  # noqa: E402
from answer import ask  # noqa: E402
from retrieve import get_model  # noqa: E402

try:
    import spaces  # only installed on Hugging Face ZeroGPU Spaces

    @spaces.GPU
    def _zerogpu_placeholder():
        """ZeroGPU needs one @spaces.GPU function to start. This app runs on CPU and never calls it."""
        return None
except ImportError:
    pass  # running on your laptop, where the spaces package isn't installed

get_model()  # load bge-small at startup, so the first question isn't slow


def answer_question(question, part):
    question = (question or "").strip()
    if len(question) < 3:
        return "Type a question first.", ""
    result = ask(question, part=None if part == "any" else part)
    cites = ", ".join(f"{c['part'].upper()} p.{c['page']}" for c in result["citations"])
    info = f"Sources: {cites or 'none'} | model {result['model']} | {result['latency_ms']} ms"
    return result["answer"], info


with gr.Blocks() as demo:
    gr.Markdown("# DatasheetGPT\nAsk about 8 component datasheets. Every answer cites the page. API docs: [/docs](/docs)")
    question = gr.Textbox(label="Question", placeholder="What is the maximum supply voltage of the LM358?")
    part = gr.Dropdown(["any", *sorted(PARTS)], value="any", label="Part")
    button = gr.Button("Ask")
    answer = gr.Markdown()
    info = gr.Markdown()
    button.click(answer_question, [question, part], [answer, info])

# Gradio page at "/"; /ask, /health and /docs were added first, so they still win
app = gr.mount_gradio_app(app, demo, path="/")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=7860)