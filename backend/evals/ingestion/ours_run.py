"""Our readers on one file: units with locations, tables with cell addresses, notes, and timing."""

import json
import sys
import time
from pathlib import Path

from verytas.intake import readers as R

TYPES = {".pdf": "application/pdf", ".docx": R.DOCX, ".xlsx": R.XLSX, ".pptx": R.PPTX, ".csv": "text/csv"}
path = Path(sys.argv[1])
raw = path.read_bytes()
mt = TYPES[path.suffix]
runs = []
for _ in range(int(sys.argv[2]) if len(sys.argv) > 2 else 5):
    t = time.perf_counter()
    out = R.read(raw, mt, path.stem)
    runs.append(time.perf_counter() - t)
loc = {"application/pdf": "page", R.PPTX: "slide"}.get(mt)
units = [{"text": p, "loc": i + 1 if loc else None} for i, p in enumerate(out.pages)] or [
    {"text": out.text, "loc": None}
]
tables, cells = [], []
for t in out.tables:
    tables.append({"name": t.name, "rows": [t.header] + t.rows})
    for c, v in enumerate(t.header):
        cells.append({"sheet": t.name, "addr": f"{R._letters(c)}{t.header_row}", "value": v})
    for r, row in enumerate(t.rows):
        for c, v in enumerate(row):
            cells.append({"sheet": t.name, "addr": t.cell(r, c).split("!", 1)[1], "value": v})
print(
    json.dumps(
        {
            "units": units,
            "text": out.text,
            "tables": tables,
            "cells": cells,
            "notes": out.notes,
            "ms": sorted(runs)[len(runs) // 2] * 1000,
        }
    )
)
