"""DatasheetGPT API: POST /ask returns an answer with datasheet page citations."""
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from answer import ask

PARTS = {"esp32", "atmega328p", "stm32f103", "lm358", "ne555", "lm317", "mcp3008", "bme280"}

app = FastAPI(
    title="DatasheetGPT",
    description="Ask questions about electronic component datasheets. Answers cite the datasheet page.",
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
    cached: bool
    latency_ms: int
    sources: list[dict]


@app.post("/ask", response_model=AskResponse)
def ask_endpoint(req: AskRequest):
    part = req.part.lower() if req.part else None
    if part and part not in PARTS:
        raise HTTPException(400, f"Unknown part '{req.part}'. Use one of: {', '.join(sorted(PARTS))}")
    return ask(req.question, part=part, k=req.k)