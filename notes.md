# Notes

## Goal 3: parsing (2026-11-01)
- Checked by eye against the PDF: ESP32 p52, STM32F103 p44, MCP3008 p3 read correctly.
- LM358 (and likely the other TI sheets, LM317 and NE555): MIN/TYP/MAX values merge into one cell, e.g. "3 7". Readable with the column header, but numbers can be ambiguous.
- BME280: merged cells repeat text and leave many empty columns; values are present but messy.
- MCP3008: rows with several conditions put all values in one cell.


## Goal 4: chunking (2026-11-01)
- 512 tokens (bge-small tokenizer), 64 overlap: 3,094 chunks, 935 from tables. All chunks <= 512 tokens incl. prefix.
- Text split on lines (parse.py has no paragraph marks). Tables over the budget split by rows with caption + header repeated (plan said one chunk per table, but bge-small ignores anything past 512 tokens).
- Graph pages that pdfplumber read as tables (giant header row) are split like text.
- Goal 13: 1024-token chunks will be cut to 512 by bge-small; compare 256 and 512, or switch model.