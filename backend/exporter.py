"""
Exporter
--------
Converts the final report string into downloadable formats.

- Markdown : trivial encode to bytes
- PDF      : uses fpdf2 (pure Python, zero system dependencies — works on Render free tier)

fpdf2 docs: https://py-pdf.github.io/fpdf2/
"""
import re
from fpdf import FPDF

# ── Constants ──────────────────────────────────────────────────────────────────
MARGIN      = 18   # mm, page margin
LINE_HEIGHT = 7    # mm, default line height


# ── Markdown export ────────────────────────────────────────────────────────────

def to_markdown_bytes(report: str, query: str) -> bytes:
    header = f"# Research Report\n**Query:** {query}\n\n---\n\n"
    return (header + report).encode("utf-8")


# ── PDF export ─────────────────────────────────────────────────────────────────

class _ReportPDF(FPDF):
    def __init__(self, query: str):
        super().__init__()
        self._query = query
        self.set_margins(MARGIN, MARGIN, MARGIN)
        self.set_auto_page_break(auto=True, margin=MARGIN)

    def header(self):
        self.set_font("Helvetica", "B", 9)
        self.set_text_color(120, 120, 120)
        self.cell(0, 8, "Research Agent Report", align="R")
        self.ln(2)
        self.set_draw_color(220, 220, 220)
        self.line(MARGIN, self.get_y(), self.w - MARGIN, self.get_y())
        self.ln(4)

    def footer(self):
        self.set_y(-14)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(150, 150, 150)
        self.cell(0, 8, f"Page {self.page_no()}", align="C")


def _strip_markdown(text: str) -> str:
    """Remove the most common Markdown syntax, leaving plain readable text."""
    # Code fences → keep the content, drop the fences
    text = re.sub(r"```[^\n]*\n(.*?)```", r"\1", text, flags=re.DOTALL)
    # Inline code
    text = re.sub(r"`([^`]+)`", r"\1", text)
    # Bold / italic
    text = re.sub(r"\*{1,3}([^*]+)\*{1,3}", r"\1", text)
    text = re.sub(r"_{1,3}([^_]+)_{1,3}", r"\1", text)
    # Links: keep label
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    # Horizontal rules
    text = re.sub(r"^[-*_]{3,}\s*$", "", text, flags=re.MULTILINE)
    return text


def to_pdf_bytes(report: str, query: str) -> bytes:
    """
    Render the research report as a PDF using fpdf2.

    fpdf2 is pure Python — no GTK, Cairo, or Pango required.
    Installs with: pip install fpdf2
    """
    pdf = _ReportPDF(query)
    pdf.add_page()

    # ── Query badge ───────────────────────────────────────────────────────────
    pdf.set_fill_color(237, 233, 254)   # soft lavender
    pdf.set_text_color(79, 70, 229)     # indigo
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(0, 8, f"Research Topic: {query[:120]}", fill=True, ln=True)
    pdf.ln(4)

    # ── Report body ───────────────────────────────────────────────────────────
    pdf.set_text_color(26, 26, 46)      # near-black

    for raw_line in report.splitlines():
        line = raw_line.rstrip()

        # Headings
        if line.startswith("### "):
            pdf.set_font("Helvetica", "B", 12)
            pdf.ln(3)
            pdf.multi_cell(0, LINE_HEIGHT, _strip_markdown(line[4:]))
            pdf.set_draw_color(200, 200, 200)
            pdf.ln(1)

        elif line.startswith("## "):
            pdf.set_font("Helvetica", "B", 14)
            pdf.ln(5)
            pdf.multi_cell(0, LINE_HEIGHT + 1, _strip_markdown(line[3:]))
            pdf.set_draw_color(180, 180, 180)
            w = pdf.w - 2 * MARGIN
            pdf.line(MARGIN, pdf.get_y(), MARGIN + w, pdf.get_y())
            pdf.ln(3)

        elif line.startswith("# "):
            pdf.set_font("Helvetica", "B", 18)
            pdf.set_text_color(79, 70, 229)
            pdf.ln(4)
            pdf.multi_cell(0, LINE_HEIGHT + 3, _strip_markdown(line[2:]))
            pdf.set_text_color(26, 26, 46)
            pdf.ln(4)

        # Bullet points
        elif line.startswith("- ") or line.startswith("* "):
            pdf.set_font("Helvetica", "", 10)
            pdf.set_x(MARGIN + 4)
            pdf.multi_cell(
                0, LINE_HEIGHT,
                "\u2022  " + _strip_markdown(line[2:]),
            )

        # Numbered list
        elif re.match(r"^\d+\. ", line):
            pdf.set_font("Helvetica", "", 10)
            pdf.set_x(MARGIN + 4)
            pdf.multi_cell(0, LINE_HEIGHT, _strip_markdown(line))

        # Blank line
        elif line.strip() == "":
            pdf.ln(3)

        # Code block content (already stripped of fences by now)
        elif line.startswith("    ") or line.startswith("\t"):
            pdf.set_font("Courier", "", 9)
            pdf.set_fill_color(243, 244, 246)
            pdf.set_text_color(80, 80, 80)
            pdf.multi_cell(0, LINE_HEIGHT - 1, line.strip(), fill=True)
            pdf.set_text_color(26, 26, 46)

        # Regular paragraph text
        else:
            pdf.set_font("Helvetica", "", 10)
            pdf.multi_cell(0, LINE_HEIGHT, _strip_markdown(line))

    # ── Footer note ───────────────────────────────────────────────────────────
    pdf.ln(8)
    pdf.set_font("Helvetica", "I", 8)
    pdf.set_text_color(156, 163, 175)
    pdf.cell(0, 6, "Generated by Research Agent", align="C")

    return bytes(pdf.output())
