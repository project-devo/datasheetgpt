# Notes

## Goal 3: parsing 
- Checked by eye against the PDF: ESP32 p52, STM32F103 p44, MCP3008 p3 read correctly.
- LM358 (and likely the other TI sheets, LM317 and NE555): MIN/TYP/MAX values merge into one cell, e.g. "3 7". Readable with the column header, but numbers can be ambiguous.
- BME280: merged cells repeat text and leave many empty columns; values are present but messy.
- MCP3008: rows with several conditions put all values in one cell.


## Goal 4: chunking 
- 512 tokens (bge-small tokenizer), 64 overlap: 3,094 chunks, 935 from tables. All chunks <= 512 tokens incl. prefix.
- Text split on lines (parse.py has no paragraph marks). Tables over the budget split by rows with caption + header repeated (plan said one chunk per table, but bge-small ignores anything past 512 tokens).
- Graph pages that pdfplumber read as tables (giant header row) are split like text.
- Goal 13: 1024-token chunks will be cut to 512 by bge-small; compare 256 and 512, or switch model.

## Goal 12: baseline failures (s512-o64)
Baseline row in results/runs.csv: R@5 71%, MRR 0.517, answer 77%, citation 73%, latency 8.2 s avg / 3.9 s median.
9 of the 14 misses are "said Not found" when the answer exists, so most failures are retrieval, not the model.

1. ATmega328P basics (q16 SRAM, q18 max clock, q19 active current, q20 pin current) - RETRIEVAL + CHUNKING.
   Gold pages never reach the top 10. All 10 hits are pages 400-640, the "Typical Characteristics" graph pages
   that repeat "ATmega328P" in every caption but hold no values. Facts are in family form
   ("512/1K/1K/2Kbytes SRAM" for 48A/88A/168A/328P on p16), which embeds weakly for one part.
   Fix ideas: keyword search (Goal 14), down-weight graph-only chunks.

2. q49 BME280 current during pressure measurement (said 4.2 uA, expected 714 uA) - PARSING.
   The p8 table splits the label "Current during / pressure / measurement" over three rows, so 714 sits on a row
   with only "Current during | IDDP". The chunk was in the context (rank 5) but the model picked IDD,LP instead.

3. q38 LM317 minimum load current in uA (said Not found) - PARSING + GENERATION.
   Chunk was retrieved (rank 7). TI tables merge TYP and MAX into one cell ("3.5 10" mA), and the question asks
   in uA, so the model did not connect 3.5 mA to 3500 uA.

4. q07 ESP32 light-sleep current in uA (said Not found) - RETRIEVAL.
   The table on p30 says "0.8 mA"; the question says "microamps", so vector search ranks other power tables higher.
   The same chunk also has the wrong section label ("4.2.3 Audio PLL Clock"), so its prefix adds noise.
   Numeric questions have the lowest R@5 (50%).

5. Cross-part questions (q51, q54, q55; cross type only 20% correct) - RETRIEVAL.
   One search for two parts lets one part fill the context. q55 (ESP32 vs STM32F103 SRAM): 8 of the top 10 are
   STM32 chunks, the ESP32 SRAM page never appears, so the model says the ESP32 value is not given.
   Fix idea: detect the parts in the question and retrieve per part, then merge.

Main failure types: retrieval misses (1, 4, 5) cause most errors; table parsing (2, 3) causes the wrong or missing
values when the right chunk is found. Generation alone caused only partial answers (q35 dropped a term, q36 gave max not typical).


## Goal 13: chunk size

| config | R@5 | MRR | R@10 | correct | citation |
|---|---|---|---|---|---|
| s256-o64 | 69% | 0.451 | 76% | not judged | not judged |
| s512-o64 | 71% | 0.517 | 87% | 77% | 73% |
| s1024-o64 | 75% | 0.506 | 80% | 73% | 67% |

Overlap stayed at 64 so chunk size was the only change. 256 was not judged because it had the lowest recall.

Decision: keep s512-o64. 1024 finds a gold page in the top 5 more often, but its answers are worse
(73% vs 77% correct, 67% vs 73% cited) because one chunk holds several similar tables and the model
picks the wrong row (q24, q26). bge-small also embeds only the first 512 tokens of a 1024 chunk.
512 has the best MRR and R@10, and R@10 matters for Goals 14 and 15, which work on a top-20 list.
## Goal 14: hybrid search (2026-11-03)
- Keyword search with websearch_to_tsquery (AND of all words) found nothing for 36 of 55 questions; gold page in top 20 for only 13. Switched to OR of the same parsed words (to_tsquery('simple', ...)): 0 empty, gold in top 20 for 52 of 55.
- Hybrid = vector top 20 + keyword top 20 merged with reciprocal rank fusion (1 / (60 + rank)), using ranks only because cosine and ts_rank scores are on different scales.
- Retrieval vs vector-only: R@5 71% -> 82%, R@10 87% -> 89%, MRR 0.517 -> 0.515, R@1 36% -> 31%. Numeric R@5 50% -> 100%, table 67% -> 73%, lookup 84% -> 84%, cross 60% -> 60%.
- Answers: correct 77% -> 85%, citation 73% -> 82%; avg latency 8.2 s -> 9.6 s.
- More gold pages reach the top 5, but rank 1 got worse: ordering is the job of the reranker (Goal 15).
- Fixed: q07, q16, q20. New retrieval miss: q10 (STM32). Still failing: q18, q19 (ATmega), q42 (MCP3008 SPI clock), q51, q53 (cross).

## Goal 15: Reranking (2026-11-04)

Hybrid top 20 reranked by BAAI/bge-reranker-base (fastembed cross-encoder, CPU), keep top k.

| config | R@1 | R@5 | R@10 | MRR | correct | citation | avg latency |
|---|---|---|---|---|---|---|---|
| hybrid | 31% | 82% | 89% | 0.515 | 85% | 82% | 9.6 s |
| hybrid + rerank | 62% | 91% | 98% | 0.750 | 88% | 84% | 24.9 s |

- R@5 by type: lookup 96%, table 80%, numeric 90%, cross 100%.
- Still not in top 5: q13, q19, q21, q25, q42 (4 of 5 are table questions).
- Answer gain is small (+2 questions) because k=8 already held the gold page most of the time.
- 22/60 answers came from the Groq fallback (Gemini 503 overload), so the answer row mixes two models.
- Cost: retrieval 4-5 s -> 10-17 s on a laptop CPU. The model is 1.06 GB, too big for free Render (512 MB).
- Remaining wrong answers are table values (typ vs max) and "Not found" (q12, q35, q53), not ranking.

## Goal 16: final setup (2026-11-04)

- Shared DB connection: db.connect() now lends connections from a psycopg ConnectionPool (min 1, max 4, each checked before use because Neon sleeps after 5 min). Hybrid retrieval 4-5 s -> 1.2 s avg (median 1.0 s) on the laptop, same ranks.
- Small reranker tried: Xenova/ms-marco-MiniLM-L-6-v2 (0.08 GB): R@1 44%, R@5 82%, R@10 96%, MRR 0.598, 3.7 s retrieval. Same R@5 as hybrid and weaker on table (67%) and numeric (70%) questions.
- Live config: hybrid, no reranker. bge-reranker-base is the best config (R@5 91%, MRR 0.750, 88% correct) but needs 1.06 GB, and Render free has 512 MB and 0.1 CPU. MiniLM adds latency for no R@5 gain. Hybrid keeps retrieval near 1 s and fits in memory. The reranker is reported as the best offline result.
- Fresh hybrid judge (no cache): 80% correct, 76% citation. 41 Gemini answers were 83% correct (median 3.2 s); 19 Groq fallbacks (Gemini 503 on q01-q27) were 74% correct, 37 s avg. The Goal 14 run (all Gemini) was 85%.
- Results table: results/results.md. Chart: results/recall_at_5.png (scripts/plot_results.py).
- Goal 12 failures on the live setup: fixed q07, q16, q20, q38, q49, q55. Still failing: q18, q19 (ATmega gold pages not in the hybrid top 10), q51, q54 (cross-part). bge rerank fixes q18, q51 and q54 and makes q19 partial.
