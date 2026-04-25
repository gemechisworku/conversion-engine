from __future__ import annotations

import argparse
import textwrap
from pathlib import Path

PAGE_WIDTH = 612
PAGE_HEIGHT = 792
MARGIN_X = 54
MARGIN_Y = 54
FONT_NAME = "Courier"
FONT_SIZE = 10
LEADING = 12
MAX_CHARS = 92
MAX_LINES_PER_PAGE = 54


def _escape_pdf_text(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _normalize_line(line: str) -> str:
    stripped = line.rstrip()
    if stripped.startswith("## "):
        return stripped[3:].upper()
    if stripped.startswith("# "):
        return stripped[2:].upper()
    return stripped


def _prepare_pages(text: str) -> list[list[str]]:
    raw_pages = [chunk.strip("\n") for chunk in text.split("<!-- PAGEBREAK -->")]
    pages: list[list[str]] = []
    for raw_page in raw_pages:
        lines: list[str] = []
        for raw_line in raw_page.splitlines():
            line = _normalize_line(raw_line)
            if not line.strip():
                lines.append("")
                continue
            wrapped = textwrap.wrap(
                line,
                width=MAX_CHARS,
                replace_whitespace=False,
                drop_whitespace=False,
                break_long_words=False,
                break_on_hyphens=False,
            )
            lines.extend(wrapped or [""])
        while lines and not lines[-1]:
            lines.pop()
        if len(lines) > MAX_LINES_PER_PAGE:
            raise ValueError(
                f"Page has {len(lines)} lines, which exceeds the {MAX_LINES_PER_PAGE}-line limit. "
                "Shorten the source or reduce spacing."
            )
        pages.append(lines)
    return pages


def _build_page_stream(lines: list[str], page_number: int, page_count: int) -> bytes:
    commands = [
        "BT",
        f"/F1 {FONT_SIZE} Tf",
        f"{LEADING} TL",
        f"1 0 0 1 {MARGIN_X} {PAGE_HEIGHT - MARGIN_Y} Tm",
    ]
    for idx, line in enumerate(lines):
        if idx > 0:
            commands.append("T*")
        commands.append(f"({_escape_pdf_text(line)}) Tj")
    commands.extend(
        [
            "ET",
            "BT",
            f"/F1 9 Tf",
            f"1 0 0 1 {PAGE_WIDTH - MARGIN_X - 90} 28 Tm",
            f"({_escape_pdf_text(f'Page {page_number} of {page_count}')}) Tj",
            "ET",
        ]
    )
    return "\n".join(commands).encode("latin-1", errors="replace")


def _render_pdf(pages: list[list[str]], output_path: Path) -> None:
    objects: list[bytes | None] = []

    def add_object(obj: bytes | None) -> int:
        objects.append(obj)
        return len(objects)

    font_id = add_object(b"<< /Type /Font /Subtype /Type1 /BaseFont /Courier >>")
    page_ids: list[int] = []
    content_ids: list[int] = []

    for page_number, lines in enumerate(pages, start=1):
        stream = _build_page_stream(lines, page_number=page_number, page_count=len(pages))
        content_obj = (
            f"<< /Length {len(stream)} >>\nstream\n".encode("latin-1")
            + stream
            + b"\nendstream"
        )
        content_ids.append(add_object(content_obj))
        page_ids.append(add_object(None))

    pages_id = add_object(None)
    catalog_id = add_object(f"<< /Type /Catalog /Pages {pages_id} 0 R >>".encode("latin-1"))

    for page_id, content_id in zip(page_ids, content_ids, strict=True):
        objects[page_id - 1] = (
            f"<< /Type /Page /Parent {pages_id} 0 R /MediaBox [0 0 {PAGE_WIDTH} {PAGE_HEIGHT}] "
            f"/Resources << /Font << /F1 {font_id} 0 R >> >> /Contents {content_id} 0 R >>"
        ).encode("latin-1")

    kids = " ".join(f"{page_id} 0 R" for page_id in page_ids)
    objects[pages_id - 1] = f"<< /Type /Pages /Count {len(page_ids)} /Kids [{kids}] >>".encode("latin-1")

    pdf = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for index, obj in enumerate(objects, start=1):
        if obj is None:
            raise RuntimeError(f"Uninitialized PDF object {index}")
        offsets.append(len(pdf))
        pdf.extend(f"{index} 0 obj\n".encode("latin-1"))
        pdf.extend(obj)
        pdf.extend(b"\nendobj\n")

    xref_offset = len(pdf)
    pdf.extend(f"xref\n0 {len(objects) + 1}\n".encode("latin-1"))
    pdf.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        pdf.extend(f"{offset:010d} 00000 n \n".encode("latin-1"))

    trailer = (
        f"trailer\n<< /Size {len(objects) + 1} /Root {catalog_id} 0 R >>\n"
        f"startxref\n{xref_offset}\n%%EOF\n"
    )
    pdf.extend(trailer.encode("latin-1"))
    output_path.write_bytes(pdf)


def main() -> None:
    parser = argparse.ArgumentParser(description="Render memo_source.md into memo.pdf")
    parser.add_argument(
        "--input",
        default="memo_source.md",
        help="Path to the source markdown-like memo file.",
    )
    parser.add_argument(
        "--output",
        default="memo.pdf",
        help="Path to the output PDF file.",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)
    pages = _prepare_pages(input_path.read_text(encoding="utf-8"))
    if len(pages) != 2:
        raise ValueError(f"Expected exactly 2 pages, found {len(pages)} pages.")
    _render_pdf(pages, output_path)


if __name__ == "__main__":
    main()
