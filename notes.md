# Notes

## Goal 3: parsing (2026-11-01)
- Checked by eye against the PDF: ESP32 p52, STM32F103 p44, MCP3008 p3 read correctly.
- LM358 (and likely the other TI sheets, LM317 and NE555): MIN/TYP/MAX values merge into one cell, e.g. "3 7". Readable with the column header, but numbers can be ambiguous.
- BME280: merged cells repeat text and leave many empty columns; values are present but messy.
- MCP3008: rows with several conditions put all values in one cell.