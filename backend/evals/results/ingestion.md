# Document ingestion: our readers against LlamaIndex

Measured 29 Oct 2026. Same files, same machine (Apple M-series laptop), one process per file and pipeline.

"Cell addresses" counts what each pipeline returns. LlamaIndex's documents carry the file name and page label in their metadata, and no sheet cell.

- **Ours:** `verytas/intake/readers.py`.
- **LlamaIndex:** `SimpleDirectoryReader` from `llama-index-core` 0.14.25 and `llama-index-readers-file` 0.7.0. These are its default local file readers: pypdf for PDF, docx2txt for Word, pandas for Excel and CSV, and its own PowerPoint reader.

LlamaParse, LlamaIndex's paid cloud parser, is not compared. It would send a company's confidential guidelines to a third party, which the product rules out.

## The corpus

`gen.py` builds a brand kit with known content, so every score is checked against ground truth:

| File | Contents |
|---|---|
| PDF | 6 pages of rules, a table on page 4, a running footer |
| Word file | Headings, bullets, a table, a page header |
| Excel file | Two sheets, with a blank row, so the cell addresses are known |
| PowerPoint deck | 6 slides with speaker notes, and a table on slide 3 |
| CSV | 40 rows |
| Scanned PDF | The text exists only as a picture |

It also builds three hostile files:

- a Word file with an external entity that points at a local secret file;
- a Word file with an entity expansion bomb;
- a spreadsheet that unpacks from 298 KB to 300 MB.

## Results

| | Ours | LlamaIndex |
|---|---|---|
| PDF: sentences read, on the right page | 24/24, 24/24 | 24/24, 24/24 |
| PDF: table rows kept together | 7/7 | 0/7 |
| Word: sentences read | 20/20 | 20/20 |
| Word: table rows kept together | 6/6 | 0/6 |
| Excel: rows kept together | 30/30 | 30/30 |
| Excel: values with their cell address ("Pricing!B4") | 111/111 | 0/111 |
| PowerPoint: text and speaker notes, on the right slide | 24/24 | 24/24 |
| PowerPoint: table rows kept together | 3/3 | 3/3 |
| CSV: rows | 41/41 | 40/41 |
| Scanned PDF | No text, and says the page is a scan | One empty document, no warning |
| External entity (XXE) | Secret not read; rest of the file read | Secret not read; logs "Skipping" and returns no document |
| Entity expansion bomb | Refused, with a note | Logs "Skipping" and returns no document |
| 300 MB spreadsheet bomb | Capped: 0.1 s, 39 MB of memory | Read in full: 36 s, 2.9 GB of memory, 2.4 billion characters |
| Time per file (median of 5) | 0.4 to 24 ms | 0.8 to 185 ms |
| Memory per process | 38 to 77 MB | 159 to 172 MB |

## The first run, and the gaps it found in ours

The first run had LlamaIndex ahead on PowerPoint:

- Ours read 18 of 24 sentences, because it skipped speaker notes.
- Ours kept 0 of 3 slide table rows together.

Neither pipeline kept Word table rows together (0 of 6 each).

Both gaps in ours are now fixed:

- **PowerPoint:** our reader takes the notes body of each slide's notes page, and reads slide tables as rows.
- **Word:** our reader keeps Word tables as rows, and leaves the text the review reads unchanged.

The table above is after those fixes.

## Verdict

We keep our readers.

- **Where LlamaIndex is ahead:** nowhere, after the PowerPoint fix. It was ahead there on the first run, and that is fixed now.
- **Cell addresses:** LlamaIndex does not give them. A rule drafted from a spreadsheet must cite "Pricing!B4", so a reviewer can check where it came from.
- **Table rows:** in PDF and Word, LlamaIndex loses them, so a "Say / Instead of" table reaches the model as a column of loose words.
- **Failures:** LlamaIndex returns an empty document for a scan with no warning. A file it can't parse is written to its log and left out of the results. Ours puts what it could not read into the reading itself, where the admin sees it.
- **Hostile files:** the spreadsheet bomb alone would take 2.9 GB of memory on the shared demo server.

## Reproduce

LlamaIndex goes in a separate virtual environment, never the backend's:

```sh
WORK=/tmp/ingest-bench
mkdir -p "$WORK"
python3 -m venv "$WORK/.venv"
"$WORK/.venv/bin/pip" install llama-index-core llama-index-readers-file reportlab openpyxl python-docx python-pptx docx2txt pandas pypdf
"$WORK/.venv/bin/python" evals/ingestion/gen.py "$WORK/corpus"
"$WORK/.venv/bin/python" evals/ingestion/bench.py "$WORK"   # prints the table rows; raw numbers in $WORK/results.json
```

Run it from `backend/`. Our side runs on `backend/.venv`.
