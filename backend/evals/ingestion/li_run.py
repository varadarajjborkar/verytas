"""LlamaIndex's SimpleDirectoryReader (its default free, local file readers) on one file."""

import json
import sys
import time

from llama_index.core import SimpleDirectoryReader

path = sys.argv[1]
runs = []
for _ in range(int(sys.argv[2]) if len(sys.argv) > 2 else 5):
    t = time.perf_counter()
    docs = SimpleDirectoryReader(input_files=[path]).load_data()
    runs.append(time.perf_counter() - t)
units = []
for d in docs:
    m = d.metadata
    loc = m.get("page_label") or m.get("page_number") or m.get("slide_number") or m.get("sheet_name")
    units.append(
        {"text": d.text, "loc": int(loc) if str(loc).isdigit() else loc, "meta": {k: str(v)[:60] for k, v in m.items()}}
    )
print(
    json.dumps(
        {
            "units": units,
            "text": "\n\n".join(u["text"] for u in units),
            "tables": [],
            "cells": [],
            "notes": [],
            "readers": sorted({type(r).__name__ for r in []}),
            "ms": sorted(runs)[len(runs) // 2] * 1000,
        }
    )
)
