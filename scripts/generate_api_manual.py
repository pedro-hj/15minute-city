"""Generate a versioned PDF manual from docs/API.md.

The Markdown is authoritative. Do not edit the PDF manually.
Usage: uv run --no-project --with reportlab==4.4.9 python scripts/generate_api_manual.py
"""

from __future__ import annotations

import argparse
import html
import re
import textwrap
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    HRFlowable,
    LongTable,
    Paragraph,
    Preformatted,
    SimpleDocTemplate,
    Spacer,
    TableStyle,
)

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs" / "API.md"
TARGET = ROOT / "docs" / "API-manual.pdf"

BLUE = colors.HexColor("#16416D")
INK = colors.HexColor("#172738")
MUTED = colors.HexColor("#516476")
GRAY = colors.HexColor("#E5EBF0")
PALE = colors.HexColor("#F1F5F8")


def register_fonts() -> None:
    directory = Path("/usr/share/fonts/truetype/dejavu")
    files = {
        "ManualSans": directory / "DejaVuSans.ttf",
        "ManualSans-Bold": directory / "DejaVuSans-Bold.ttf",
        "ManualMono": directory / "DejaVuSansMono.ttf",
    }
    if not all(path.exists() for path in files.values()):
        raise RuntimeError("DejaVu fonts are required (install fonts-dejavu-core)")
    for name, path in files.items():
        pdfmetrics.registerFont(TTFont(name, str(path)))
    pdfmetrics.registerFontFamily(
        "ManualSans", normal="ManualSans", bold="ManualSans-Bold"
    )


def styles() -> dict[str, ParagraphStyle]:
    base = {"alignment": TA_LEFT}
    return {
        "title": ParagraphStyle(
            "Title",
            **base,
            fontName="ManualSans-Bold",
            textColor=INK,
            fontSize=24,
            leading=29,
            spaceAfter=17,
        ),
        "h2": ParagraphStyle(
            "H2",
            **base,
            fontName="ManualSans-Bold",
            textColor=BLUE,
            fontSize=14,
            leading=19,
            spaceBefore=16,
            spaceAfter=8,
            keepWithNext=1,
        ),
        "h3": ParagraphStyle(
            "H3",
            **base,
            fontName="ManualSans-Bold",
            textColor=INK,
            fontSize=10.5,
            leading=15,
            spaceBefore=12,
            spaceAfter=7,
            keepWithNext=1,
        ),
        "body": ParagraphStyle(
            "Body",
            **base,
            fontName="ManualSans",
            textColor=INK,
            fontSize=9,
            leading=14.8,
            spaceAfter=8,
            allowWidows=0,
            allowOrphans=0,
        ),
        "bullet": ParagraphStyle(
            "Bullet",
            **base,
            fontName="ManualSans",
            textColor=INK,
            fontSize=9,
            leading=14.8,
            leftIndent=13,
            firstLineIndent=-11,
            spaceAfter=5,
        ),
        "cell": ParagraphStyle(
            "Cell",
            **base,
            fontName="ManualSans",
            textColor=INK,
            fontSize=7.35,
            leading=11,
            splitLongWords=1,
        ),
        "cellhead": ParagraphStyle(
            "CellHead",
            **base,
            fontName="ManualSans-Bold",
            textColor=BLUE,
            fontSize=7.4,
            leading=11,
        ),
        "code": ParagraphStyle(
            "Code",
            fontName="ManualMono",
            textColor=INK,
            fontSize=7.1,
            leading=11.2,
        ),
    }


def inline(value: str) -> str:
    value = html.escape(value.strip())
    value = re.sub(
        r"`([^`]+)`",
        r'<font face="ManualMono" size="8">\1</font>',
        value,
    )
    value = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", value)
    value = re.sub(r"\[([^]]+)\]\(([^)]+)\)", r"\1 (\2)", value)
    return value


def code_block(lines: list[str], ss: dict[str, ParagraphStyle]) -> LongTable:
    expanded: list[str] = []
    for line in lines:
        if len(line) <= 93:
            expanded.append(line)
        else:
            expanded.extend(
                textwrap.wrap(
                    line,
                    width=91,
                    break_long_words=True,
                    break_on_hyphens=False,
                )
            )
    block = Preformatted(
        "\n".join(expanded) or " ",
        ss["code"],
        maxLineLength=95,
        splitChars=" /-,",
    )
    table = LongTable([[block]], colWidths=[476])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), PALE),
                ("BOX", (0, 0), (-1, -1), 0.4, GRAY),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 9),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
            ]
        )
    )
    return table


def markdown_table(lines: list[str], ss: dict[str, ParagraphStyle]) -> list:
    parsed: list[list[str]] = []
    for line in lines:
        row = [cell.strip() for cell in line.strip("|").split("|")]
        if all(re.fullmatch(r":?-{3,}:?", cell) for cell in row):
            continue
        parsed.append(row)
    if len(parsed) < 2:
        return []

    count = len(parsed[0])
    if count == 2:
        widths = [285.6, 190.4]
    elif count == 3:
        widths = [133.28, 247.52, 95.2]
    else:
        widths = [476 / count] * count

    rows = [
        [
            Paragraph(inline(cell), ss["cellhead"] if index == 0 else ss["cell"])
            for cell in (row + [""] * count)[:count]
        ]
        for index, row in enumerate(parsed)
    ]
    table = LongTable(rows, colWidths=widths, repeatRows=1, hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), PALE),
                ("LINEBELOW", (0, 0), (-1, 0), 1, BLUE),
                ("LINEBELOW", (0, 1), (-1, -1), 0.35, GRAY),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                (
                    "ROWBACKGROUNDS",
                    (0, 1),
                    (-1, -1),
                    [colors.white, colors.HexColor("#FAFCFD")],
                ),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    return [table, Spacer(1, 10)]


def parse_markdown(text: str, ss: dict[str, ParagraphStyle]) -> list:
    story = []
    paragraph: list[str] = []
    code: list[str] | None = None
    table: list[str] = []

    def flush_paragraph() -> None:
        if paragraph:
            story.append(Paragraph(inline(" ".join(paragraph)), ss["body"]))
            paragraph.clear()

    def flush_table() -> None:
        if table:
            story.extend(markdown_table(table, ss))
            table.clear()

    for raw in text.splitlines():
        line = raw.strip()
        if code is not None:
            if line.startswith("```"):
                story.append(code_block(code, ss))
                story.append(Spacer(1, 8))
                code = None
            else:
                code.append(raw.rstrip())
            continue
        if line.startswith("```"):
            flush_paragraph()
            flush_table()
            code = []
            continue
        if line.startswith("|") and line.endswith("|"):
            flush_paragraph()
            table.append(line)
            continue
        flush_table()
        if not line:
            flush_paragraph()
        elif line.startswith("# "):
            flush_paragraph()
            story.append(Spacer(1, 15))
            story.append(
                HRFlowable(
                    width="12%",
                    thickness=3,
                    color=BLUE,
                    hAlign="LEFT",
                    spaceAfter=14,
                )
            )
            story.append(Paragraph(inline(line[2:]), ss["title"]))
        elif line.startswith("## "):
            flush_paragraph()
            story.append(Paragraph(inline(line[3:]), ss["h2"]))
        elif line.startswith("### "):
            flush_paragraph()
            story.append(Paragraph(inline(line[4:]), ss["h3"]))
        elif line.startswith("- "):
            flush_paragraph()
            story.append(Paragraph("•  " + inline(line[2:]), ss["bullet"]))
        else:
            paragraph.append(line.removesuffix("  "))

    flush_table()
    flush_paragraph()
    if code is not None:
        raise ValueError("Unclosed fenced code block in docs/API.md")
    return story


def page(pdf: canvas.Canvas, doc: SimpleDocTemplate) -> None:
    pdf.saveState()
    width, height = A4
    pdf.setStrokeColor(GRAY)
    pdf.setLineWidth(0.6)
    pdf.line(59, height - 44, width - 59, height - 44)
    pdf.setFont("ManualSans-Bold", 7.8)
    pdf.setFillColor(BLUE)
    pdf.drawString(59, height - 35, "15MINUTE-CITY  /  DOCUMENTAÇÃO DA API")
    pdf.line(59, 51, width - 59, 51)
    pdf.setFillColor(MUTED)
    pdf.setFont("ManualSans", 7.4)
    pdf.drawString(59, 38, "Manual de uso · API v1 · 08/10/2026")
    pdf.drawRightString(width - 59, 38, str(doc.page))
    pdf.restoreState()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=TARGET)
    args = parser.parse_args()
    register_fonts()
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    document = SimpleDocTemplate(
        str(output),
        pagesize=A4,
        leftMargin=59,
        rightMargin=59,
        topMargin=63,
        bottomMargin=65,
        title="Manual da API 15minute-city",
        author="Projeto 15minute-city",
        subject="Guia de consulta e integração REST",
        pageCompression=1,
        invariant=1,
    )
    document.build(
        parse_markdown(SOURCE.read_text(encoding="utf-8"), styles()),
        onFirstPage=page,
        onLaterPages=page,
    )
    print(f"PDF gerado: {output}")


if __name__ == "__main__":
    main()
