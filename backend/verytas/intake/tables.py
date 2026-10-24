"""Tables: a fixed menu of cleaning operations, and one fact per row from a plan.

The model never writes code. It picks operations from this menu, each a typed record validated before
anything runs, and says which columns make a fact. Code applies the plan to every row, so each fact's
value is read from its own cell and can be traced back to it ("Pricing!C4"). Operations are pure
functions over strings: no evaluation, no file or network access, a bounded number per plan.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from verytas.intake.readers import Table, excel_date

MAX_FACT_ROWS = 300


class Trim(BaseModel):
    op: Literal["trim"] = "trim"


class DropEmptyRows(BaseModel):
    op: Literal["drop_empty_rows"] = "drop_empty_rows"


class DropRowsWithout(BaseModel):
    op: Literal["drop_rows_without"] = "drop_rows_without"
    column: str


class Rename(BaseModel):
    op: Literal["rename"] = "rename"
    column: str
    to: str = Field(max_length=80)


class Dedupe(BaseModel):
    op: Literal["dedupe"] = "dedupe"
    columns: list[str] = Field(default_factory=list, max_length=6)


class KeepRowsWhere(BaseModel):
    op: Literal["keep_rows_where"] = "keep_rows_where"
    column: str
    equals: str


class DropHeaderRows(BaseModel):
    """Repeated header rows, or notes typed under the header ("all prices incl. GST")."""
    op: Literal["drop_rows_matching"] = "drop_rows_matching"
    column: str
    pattern: str = Field(max_length=80, description="Plain text; rows whose cell contains it are dropped")


Op = Annotated[Trim | DropEmptyRows | DropRowsWithout | Rename | Dedupe | KeepRowsWhere | DropHeaderRows,
               Field(discriminator="op")]


class FactPlan(BaseModel):
    statement: str = Field(max_length=300, description="Template with {column} placeholders, e.g. "
                           "'The {Plan} plan costs Rs {Price} a month'")
    subject: str | None = Field(None, description="Column naming what the fact is about")
    value: str | None = Field(None, description="Column holding the number")
    unit: str | None = Field(None, description="A fixed unit ('INR', '%', 'learners') when the column has none")
    unit_column: str | None = None
    valid_from: str | None = Field(None, description="Column holding the date it applies from")
    valid_to: str | None = None


def _norm(s: str) -> str:
    return unicodedata.normalize("NFKC", s).strip()


def _col(t: Table, name: str | None) -> int | None:
    if not name:
        return None
    want = _norm(name).lower()
    for i, h in enumerate(t.header):
        if _norm(h).lower() == want:
            return i
    return None


def apply(t: Table, ops: list) -> tuple[Table, list[int], list[str]]:
    """The table after the operations, which source row each remaining row was, and what could not run."""
    header = list(t.header)
    rows = [list(r) for r in t.rows]
    origin = list(range(len(rows)))
    skipped: list[str] = []
    for op in ops[:12]:
        kind = op.op
        col = _col(Table(t.name, header, []), getattr(op, "column", None)) if hasattr(op, "column") else None
        if hasattr(op, "column") and col is None:
            skipped.append(f"{kind}: no column named {op.column!r}")
            continue
        keep: list[bool]
        if kind == "trim":
            rows = [[_norm(c) for c in r] for r in rows]
            continue
        if kind == "rename":
            header[col] = op.to
            continue
        if kind == "drop_empty_rows":
            keep = [any(c.strip() for c in r) for r in rows]
        elif kind == "drop_rows_without":
            keep = [bool(r[col].strip()) for r in rows]
        elif kind == "keep_rows_where":
            keep = [_norm(r[col]).lower() == _norm(op.equals).lower() for r in rows]
        elif kind == "drop_rows_matching":
            keep = [_norm(op.pattern).lower() not in _norm(r[col]).lower() for r in rows]
        elif kind == "dedupe":
            idx = [i for c in op.columns if (i := _col(Table(t.name, header, []), c)) is not None] \
                or list(range(len(header)))
            seen: set[tuple] = set()
            keep = []
            for r in rows:
                key = tuple(_norm(r[i]).lower() for i in idx)
                keep.append(key not in seen)
                seen.add(key)
        else:  # pragma: no cover - the union is closed
            continue
        rows = [r for r, k in zip(rows, keep, strict=True) if k]
        origin = [o for o, k in zip(origin, keep, strict=True) if k]
    # origin indexes the source rows, so the source's row numbers come along unfiltered.
    return Table(t.name, header, rows, t.header_row, t.lines), origin, skipped


_NUMBER = re.compile(r"[-+]?\d[\d,]*(?:\.\d+)?|[-+]?\.\d+")
_CURRENCY = {"₹": "INR", "rs": "INR", "inr": "INR", "$": "USD", "usd": "USD", "€": "EUR", "eur": "EUR",
             "£": "GBP", "gbp": "GBP"}


def number(cell: str) -> tuple[float, str | None] | None:
    """A cell's number and the unit written with it ("₹4,999" -> (4999, "INR"), "12%" -> (12, "%"))."""
    text = _norm(cell)
    m = _NUMBER.search(text)
    if not m:
        return None
    try:
        value = float(m.group(0).replace(",", ""))
    except ValueError:
        return None
    rest = (text[:m.start()] + " " + text[m.end():]).strip().lower()
    if "%" in rest:
        return value, "%"
    for mark, unit in _CURRENCY.items():
        if re.search(rf"(?<![a-z]){re.escape(mark)}(?![a-z])", rest):
            return value, unit
    words = re.findall(r"[a-z]+", rest)
    return value, (words[0] if words else None)


def header_unit(header: str) -> str | None:
    """The unit a column header states: "Price (Rs)", "Share (%)", "Learners [count]"."""
    m = re.search(r"[(\[]([^)\]]{1,20})[)\]]", header)
    if not m:
        return None
    inner = m.group(1).strip()
    return _CURRENCY.get(inner.lower().rstrip("."), "%" if inner == "%" else inner)


def as_date(cell: str) -> date | None:
    text = _norm(cell)
    if not text:
        return None
    if d := excel_date(text):
        return d
    for fmt in (r"(\d{4})-(\d{1,2})-(\d{1,2})", r"(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})"):
        m = re.fullmatch(fmt, text)
        if m:
            a, b, c = (int(x) for x in m.groups())
            try:
                return date(a, b, c) if fmt.startswith(r"(\d{4})") else date(c, b, a)  # day first, as in India
            except ValueError:
                return None
    return None


def profile(t: Table) -> str:
    """Per column: its type, how full it is, and units seen. What the model plans from."""
    out = []
    for i, h in enumerate(t.header[:30]):
        cells = [r[i] for r in t.rows if i < len(r)]
        filled = [c for c in cells if c.strip()]
        nums = [n for c in filled if (n := number(c)) and len(_NUMBER.sub("", c).strip()) <= 6]
        dates = [d for c in filled if (d := as_date(c))]
        kind = ("date" if filled and len(dates) >= 0.8 * len(filled)
                else "number" if filled and len(nums) >= 0.8 * len(filled) else "text")
        units = sorted({u for _, u in nums if u})[:3]
        out.append(f"{h} ({kind}, {len(filled)}/{len(cells)} filled" + (f", units {'/'.join(units)}" if units else "")
                   + ")")
    return "; ".join(out)


def default_plan(t: Table) -> FactPlan | None:
    """Offline: the first text column is the subject and the first number column the value."""
    subject = value = None
    for i, h in enumerate(t.header):
        cells = [r[i] for r in t.rows if r[i].strip()]
        if not cells:
            continue
        numeric = sum(1 for c in cells if number(c) is not None) >= 0.8 * len(cells)
        if numeric and value is None and not any(as_date(c) for c in cells[:5]):
            value = h
        elif not numeric and subject is None:
            subject = h
    if not (subject and value):
        return None
    return FactPlan(statement=f"{{{subject}}}: {{{value}}}", subject=subject, value=value)


def facts(t: Table, plan: FactPlan, origin: list[int], source: str) -> tuple[list[dict], list[str]]:
    """One fact payload per row (FactIn's fields) with the cell it came from, and rows that could not be read."""
    out, problems = [], []
    val, sub = _col(t, plan.value), _col(t, plan.subject)
    unit_col, vf, vt = _col(t, plan.unit_column), _col(t, plan.valid_from), _col(t, plan.valid_to)
    placeholders = re.findall(r"\{([^{}]+)\}", plan.statement)
    missing = [p for p in placeholders if _col(t, p) is None]
    if missing or (plan.value and val is None):
        return [], [f"the plan names columns the table doesn't have: {', '.join(missing or [plan.value or ''])}"]
    for row, src in zip(t.rows[:MAX_FACT_ROWS], origin, strict=False):
        statement = plan.statement
        for p in placeholders:
            statement = statement.replace("{" + p + "}", row[_col(t, p)])
        statement = " ".join(statement.split())
        if not statement or all(not row[_col(t, p)].strip() for p in placeholders):
            continue
        n = number(row[val]) if val is not None else None
        if val is not None and n is None:
            problems.append(f"{t.cell(src, val)}: {row[val]!r} is not a number")
            continue
        unit = ((row[unit_col].strip() if unit_col is not None else None) or plan.unit or (n[1] if n else None)
                or (header_unit(t.header[val]) if val is not None else None))
        out.append({
            "payload": {"statement": statement[:500], "value": n[0] if n else None, "unit": unit,
                        "subject": row[sub][:200] if sub is not None else None,
                        "valid_from": (as_date(row[vf]) if vf is not None else None),
                        "valid_to": (as_date(row[vt]) if vt is not None else None)},
            "provenance": {"source": source, "cell": t.cell(src, val if val is not None else 0),
                           "quote": " | ".join(c for c in row if c)[:300]}})
    return out, problems
