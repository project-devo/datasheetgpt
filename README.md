# DatasheetGPT

Ask questions about electronic component datasheets and get answers that cite the exact page they came from. Built as a retrieval-augmented generation (RAG) system and measured on a 60-question evaluation set I built myself.

**Live API:** https://datasheetgpt-api.onrender.com (open `/docs` and try `POST /ask`)
_Runs on Render's free tier, so the first request after idle can take about a minute to wake up._

Example: "What is the maximum supply voltage of the LM358?" returns "32 V [LM358 p.4]".

## Datasheets covered

ESP32, ATmega328P, STM32F103, LM358, NE555, LM317, MCP3008, BME280: 8 manufacturer PDFs, 1,099 pages. Sources and revisions are in `data/sources.csv`.

## How it works

1. **Parse** (`ingest/parse.py`): PyMuPDF extracts text page by page, pdfplumber turns tables into Markdown with their caption, and repeated headers and footers are removed.
2. **Chunk** (`ingest/chunk.py`): 512-token chunks with 64 overlap. Long tables are split between rows with the caption and header row repeated, so no value loses its column name. Every chunk is prefixed with its part, page and section.
3. **Embed** (`ingest/embed.py`): `bge-small-en-v1.5` on CPU via fastembed, stored in Postgres with pgvector (HNSW index). 3,094 chunks.
4. **Answer** (`api/answer.py`): the top 8 chunks go to Gemini Flash-Lite as numbered blocks. The model must answer only from them, cite like `[LM358 p.4]`, and say "Not found in the datasheets" otherwise. Groq is the fallback, and answers are cached in Postgres.

## Evaluation

- **Question set** (`eval/questions.jsonl`): 60 questions, each with an expected answer and gold page(s): 25 lookups, 15 table values, 10 numeric/unit, 5 comparing two parts, 5 unanswerable. AI-drafted from the PDFs, every gold page hand-verified, frozen before experiments (tag `eval-v1`).
- **Retrieval** (`eval/retrieval.py`): recall@5 and MRR against the gold pages.
- **Answers** (`eval/judge.py`): an LLM judge (Groq `gpt-oss-120b`, a different model from the one answering) grades each answer correct, partly correct or wrong; citations are checked in code against the gold pages. My own hand check of 15 judge verdicts agreed 15 of 15.

### Baseline results

| Config | Recall@5 | MRR | Answer accuracy | Citation accuracy | Median latency |
|---|---|---|---|---|---|
| 512-token chunks, vector search only | 71% | 0.517 | 77% | 73% | 3.9 s |

All 5 unanswerable questions correctly got "Not found". Most remaining errors are retrieval misses (the 653-page ATmega328P sheet crowds out the right page) and table parsing (merged MIN/TYP/MAX cells). The five worst failures are analysed in `notes.md`, and every run is logged in `results/runs.csv`.

**Next:** chunk-size, hybrid (keyword + vector) search and reranking experiments, each logged against this baseline.

## Stack

Python 3.11 · FastAPI · PostgreSQL + pgvector on Neon · fastembed (bge-small-en-v1.5) · Gemini API (free tier) with Groq fallback · PyMuPDF, pdfplumber · Render

## Run locally

1. Create a Python 3.11 virtual environment and run `pip install -r requirements-ingest.txt`
2. Copy `.env.example` to `.env` and add your Neon `DATABASE_URL`, `GEMINI_API_KEY` and `GROQ_API_KEY`
3. Download the PDFs listed in `data/sources.csv` into `data/` as `<part>.pdf`
4. `python ingest/parse.py`, then `python ingest/chunk.py`, then `python ingest/embed.py`
5. `python app.py` and open http://localhost:7860/docs
6. Reproduce the baseline: `python eval/retrieval.py`, then `python eval/judge.py`
