"""DatasheetGPT API: POST /ask returns an answer with datasheet page citations."""
import json
import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from answer import ask, ask_stream

PARTS = {"esp32", "atmega328p", "stm32f103", "lm358", "ne555", "lm317", "mcp3008", "bme280"}

app = FastAPI(
    title="DatasheetGPT",
    description="Ask questions about electronic component datasheets. Answers cite the datasheet page.",
)

# Goal 18: the Next.js page on Vercel calls this API from the browser, so allow its origin.
# WEB_ORIGIN = the Vercel URL (comma-separate several); localhost:3000 is for `pnpm dev`.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", *filter(None, os.environ.get("WEB_ORIGIN", "").split(","))],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=500,
                          examples=["What is the maximum supply voltage of the LM358?"])
    part: str | None = None
    k: int = Field(default=8, ge=1, le=10)


class Citation(BaseModel):
    part: str
    page: int


class AskResponse(BaseModel):
    question: str
    answer: str
    citations: list[Citation]
    not_found: bool
    model: str
    config: str
    mode: str
    cached: bool
    latency_ms: int
    sources: list[dict]
    tools: list[dict] = []  # Goal 17: calculator runs {tool, args, result or error}


def check_part(part):
    part = part.lower() if part else None
    if part and part not in PARTS:
        raise HTTPException(400, f"Unknown part '{part}'. Use one of: {', '.join(sorted(PARTS))}")
    return part


@app.post("/ask", response_model=AskResponse)
def ask_endpoint(req: AskRequest):
    return ask(req.question, part=check_part(req.part), k=req.k)


@app.post("/ask/stream")
def ask_stream_endpoint(req: AskRequest):
    """Same answer as /ask, sent as server-sent events: status, tool, token... then done (with citations)."""
    part = check_part(req.part)

    def events():
        try:
            for event in ask_stream(req.question, part=part, k=req.k):
                yield f"data: {json.dumps(event)}\n\n"
        except Exception as e:  # the 200 header is already sent, so report the error as an event
            print(f"/ask/stream failed: {e!r}")
            yield f"data: {json.dumps({'type': 'error', 'message': 'The answer failed. Please try again.'})}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})




@app.get("/health")
def health():
    return {"status": "ok"}