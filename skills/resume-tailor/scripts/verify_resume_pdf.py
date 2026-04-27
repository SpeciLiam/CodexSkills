#!/usr/bin/env python3

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import subprocess
import sys


@dataclass
class PageCheck:
    page_count: int
    height: float | None
    used_height: float | None
    bottom_margin: float | None


def load_with_pypdf(pdf_path: Path) -> PageCheck | None:
    try:
        from pypdf import PdfReader
    except Exception:
        return None

    reader = PdfReader(str(pdf_path))
    page_count = len(reader.pages)
    if page_count != 1:
        return PageCheck(page_count, None, None, None)

    page = reader.pages[0]
    height = float(page.mediabox.height)
    y_values: list[float] = []

    def visitor_text(text: str, cm, tm, font_dict, font_size) -> None:  # noqa: ANN001
        if not text.strip():
            return
        try:
            y_values.append(float(tm[5]))
        except (IndexError, TypeError, ValueError):
            return

    try:
        page.extract_text(visitor_text=visitor_text)
    except Exception:
        y_values = []

    if not y_values:
        return PageCheck(page_count, height, None, None)

    top = max(y_values)
    bottom = min(y_values)
    return PageCheck(
        page_count=page_count,
        height=height,
        used_height=max(0.0, top - bottom),
        bottom_margin=max(0.0, bottom),
    )


def page_count_with_mdls(pdf_path: Path) -> int | None:
    try:
        result = subprocess.run(
            ["mdls", "-raw", "-name", "kMDItemNumberOfPages", str(pdf_path)],
            check=True,
            capture_output=True,
            text=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None

    value = result.stdout.strip()
    if value.isdigit():
        return int(value)
    return None


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify that a rendered resume PDF is exactly one page and materially fills it."
    )
    parser.add_argument("--pdf", required=True, help="Path to the rendered resume PDF")
    parser.add_argument(
        "--min-used-height-ratio",
        type=float,
        default=0.68,
        help="Minimum vertical text span as a fraction of page height.",
    )
    parser.add_argument(
        "--max-bottom-margin-ratio",
        type=float,
        default=0.22,
        help="Maximum allowed bottom whitespace as a fraction of page height.",
    )
    args = parser.parse_args()

    pdf_path = Path(args.pdf).expanduser().resolve()
    if not pdf_path.exists():
        raise SystemExit(f"PDF not found: {pdf_path}")

    check = load_with_pypdf(pdf_path)
    if check is None:
        page_count = page_count_with_mdls(pdf_path)
        if page_count is None:
            raise SystemExit(
                "Could not inspect PDF. Install pypdf or run on macOS with mdls available."
            )
        check = PageCheck(page_count, None, None, None)

    if check.page_count != 1:
        print(f"FAIL page_count={check.page_count}; resume must render to exactly one page.")
        return 1

    if check.height and check.used_height is not None and check.bottom_margin is not None:
        used_ratio = check.used_height / check.height
        bottom_ratio = check.bottom_margin / check.height
        status = (
            "PASS"
            if used_ratio >= args.min_used_height_ratio
            and bottom_ratio <= args.max_bottom_margin_ratio
            else "FAIL"
        )
        print(
            status,
            f"page_count=1 used_height={used_ratio:.1%} bottom_margin={bottom_ratio:.1%}",
        )
        if used_ratio < args.min_used_height_ratio:
            return 1
        if bottom_ratio > args.max_bottom_margin_ratio:
            return 1
        return 0

    print("PASS page_count=1; text-position fill check unavailable, inspect the rendered PDF visually.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
