#!/usr/bin/env python3
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")


@dataclass(frozen=True)
class MarkdownRow:
    line_number: int
    raw: str
    cells: list[str]
    row: dict[str, str]


@dataclass(frozen=True)
class MarkdownTable:
    path: Path
    header_line: int
    header: list[str]
    rows: list[MarkdownRow]


def split_markdown_row(line: str) -> list[str]:
    text = line.strip()
    if text.startswith("|"):
        text = text[1:]
    if text.endswith("|"):
        text = text[:-1]

    cells: list[str] = []
    current: list[str] = []
    escaped = False
    for char in text:
        if escaped:
            current.append(char)
            escaped = False
            continue
        if char == "\\":
            escaped = True
            current.append(char)
            continue
        if char == "|":
            cells.append("".join(current).strip().replace("\\|", "|"))
            current = []
            continue
        current.append(char)
    cells.append("".join(current).strip().replace("\\|", "|"))
    return cells


def is_divider_row(line: str) -> bool:
    cells = split_markdown_row(line)
    if not cells:
        return False
    return all(re.fullmatch(r":?-{3,}:?", cell.strip()) for cell in cells)


def extract_table(path: Path, required_columns: set[str] | None = None) -> MarkdownTable:
    lines = path.read_text(encoding="utf-8").splitlines()
    required_columns = required_columns or set()
    for index, line in enumerate(lines):
        if not line.strip().startswith("|"):
            continue
        header = split_markdown_row(line)
        if required_columns and not required_columns.issubset(set(header)):
            continue
        if index + 1 >= len(lines) or not is_divider_row(lines[index + 1]):
            continue

        rows: list[MarkdownRow] = []
        for row_index in range(index + 2, len(lines)):
            row_line = lines[row_index]
            if not row_line.strip().startswith("|"):
                break
            cells = split_markdown_row(row_line)
            row = dict(zip(header, cells)) if len(cells) == len(header) else {}
            rows.append(MarkdownRow(row_index + 1, row_line, cells, row))
        return MarkdownTable(path=path, header_line=index + 1, header=header, rows=rows)
    raise ValueError(f"could not find markdown table in {path}")


def clean_text(value: str) -> str:
    return LINK_RE.sub(lambda match: match.group(1), value or "").strip()


def first_link_or_text(value: str) -> str:
    match = LINK_RE.search(value or "")
    if match:
        return match.group(2).strip()
    return (value or "").strip()


def parse_int(value: str) -> int | None:
    text = clean_text(value)
    if not text:
        return None
    try:
        return int(text)
    except ValueError:
        return None
