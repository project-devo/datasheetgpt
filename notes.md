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
