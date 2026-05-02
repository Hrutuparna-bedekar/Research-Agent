"""
Exporter
--------
Converts the final report string into downloadable formats.

- Markdown : trivial encode to bytes
- PDF      : uses fpdf2 (pure Python, zero system dependencies — works on Render free tier)

fpdf2's built-in fonts (Helvetica, Courier, Times) only support Latin-1.
All text is sanitised through _to_latin1_safe() before writing so no
UnicodeEncodeError can occur regardless of LLM output content.
"""
import re
from fpdf import FPDF

# ── Constants ──────────────────────────────────────────────────────────────────
MARGIN      = 18   # mm, page margin
LINE_HEIGHT = 7    # mm, default line height


# ── Unicode → Latin-1 sanitiser ───────────────────────────────────────────────

_UNICODE_MAP = {
    "\u2022": "-",    # bullet •
    "\u00b7": "-",    # middle dot ·
    "\u25cf": "*",    # black circle ●
    "\u2013": "-",    # en dash –
    "\u2014": "--",   # em dash —
    "\u2018": "'",    # left single quote '
    "\u2019": "'",    # right single quote '
    "\u201c": '"',    # left double quote "
    "\u201d": '"',    # right double quote "
    "\u2026": "...",  # ellipsis …
    "\u2212": "-",    # minus sign −
    "\u2192": "->",   # right arrow →
    "\u2190": "<-",   # left arrow ←
    "\u21d2": "=>",   # double right arrow ⇒
    "\u2260": "!=",   # not equal ≠
    "\u2248": "~=",   # approximately ≈
    "\u221e": "inf",  # infinity ∞
    "\u03b1": "alpha",
    "\u03b2": "beta",
    "\u03b3": "gamma",
    "\u03b4": "delta",
    "\u2714": "OK",   # heavy check mark ✔
    "\u2718": "X",    # heavy ballot X ✘
    "\u2764": "<3",   # heart ❤
    "\u00e9": "e",    # é
    "\u00e8": "e",    # è
    "\u00ea": "e",    # ê
    "\u00e0": "a",    # à
    "\u00e2": "a",    # â
    "\u00fc": "u",    # ü
    "\u00f6": "o",    # ö
    "\u00e4": "a",    # ä
    "\u2500": "-",    # box-drawing ─
    "\u2502": "|",    # box-drawing │
    "\u250c": "+",    # box-drawing ┌
    "\u2510": "+",
    "\u2514": "+",
    "\u2518": "+",
    "\u251c": "+",
    "\u2524": "+",
    "\u252c": "+",
    "\u2534": "+",
    "\u253c": "+",
}

def _to_latin1_safe(text: str) -> str:
    """Replace characters outside Latin-1 (>255) with readable ASCII stand-ins."""
    parts = []
    for ch in text:
        if ch in _UNICODE_MAP:
            parts.append(_UNICODE_MAP[ch])
        elif ord(ch) > 255:
            parts.append("?")   # unknown — keep a visible placeholder
        else:
            parts.append(ch)
    return "".join(parts)


# ── Markdown helpers ───────────────────────────────────────────────────────────

def _strip_markdown(text: str) -> str:
    """Remove common Markdown syntax, leaving plain readable text."""
    text = re.sub(r"```[^\n]*\n(.*?)```", r"\1", text, flags=re.DOTALL)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"\*{1,3}([^*]+)\*{1,3}", r"\1", text)
    text = re.sub(r"_{1,3}([^_]+)_{1,3}", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"^[-*_]{3,}\s*$", "", text, flags=re.MULTILINE)
    return text


def _cell(text: str) -> str:
    """Strip markdown AND sanitise to Latin-1 in one step."""
    return _to_latin1_safe(_strip_markdown(text))


# ── Markdown export ────────────────────────────────────────────────────────────

def to_markdown_bytes(report: str, query: str) -> bytes:
    header = f"# Research Report\n**Query:** {query}\n\n---\n\n"
    return (header + report).encode("utf-8")


# ── PDF export ─────────────────────────────────────────────────────────────────

class _ReportPDF(FPDF):
    def __init__(self, query: str):
        super().__init__()
        self._query = _to_latin1_safe(query)
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


def to_pdf_bytes(report: str, query: str) -> bytes:
    """
    Render the research report as a PDF using fpdf2.

    fpdf2 is pure Python — no GTK, Cairo, or Pango required.
    All text is sanitised to Latin-1 before writing so Unicode from
    LLM output never causes an encoding error.
    """
    pdf = _ReportPDF(query)
    pdf.add_page()

    # ── Query badge ───────────────────────────────────────────────────────────
    pdf.set_fill_color(237, 233, 254)
    pdf.set_text_color(79, 70, 229)
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(0, 8, f"Research Topic: {pdf._query[:120]}", fill=True, ln=True)
    pdf.ln(4)

    # ── Report body ───────────────────────────────────────────────────────────
    pdf.set_text_color(26, 26, 46)

    for raw_line in report.splitlines():
        line = raw_line.rstrip()

        # H3
        if line.startswith("### "):
            pdf.set_font("Helvetica", "B", 12)
            pdf.ln(3)
            pdf.multi_cell(0, LINE_HEIGHT, _cell(line[4:]))
            pdf.ln(1)

        # H2
        elif line.startswith("## "):
            pdf.set_font("Helvetica", "B", 14)
            pdf.ln(5)
            pdf.multi_cell(0, LINE_HEIGHT + 1, _cell(line[3:]))
            pdf.set_draw_color(180, 180, 180)
            pdf.line(MARGIN, pdf.get_y(), pdf.w - MARGIN, pdf.get_y())
            pdf.ln(3)

        # H1
        elif line.startswith("# "):
            pdf.set_font("Helvetica", "B", 18)
            pdf.set_text_color(79, 70, 229)
            pdf.ln(4)
            pdf.multi_cell(0, LINE_HEIGHT + 3, _cell(line[2:]))
            pdf.set_text_color(26, 26, 46)
            pdf.ln(4)

        # Bullet list  (use ASCII dash — no Unicode bullet needed)
        elif line.startswith("- ") or line.startswith("* "):
            pdf.set_font("Helvetica", "", 10)
            pdf.set_x(MARGIN + 4)
            pdf.multi_cell(0, LINE_HEIGHT, "-  " + _cell(line[2:]))

        # Numbered list
        elif re.match(r"^\d+\. ", line):
            pdf.set_font("Helvetica", "", 10)
            pdf.set_x(MARGIN + 4)
            pdf.multi_cell(0, LINE_HEIGHT, _cell(line))

        # Blank line
        elif line.strip() == "":
            pdf.ln(3)

        # Indented code block
        elif line.startswith("    ") or line.startswith("\t"):
            pdf.set_font("Courier", "", 9)
            pdf.set_fill_color(243, 244, 246)
            pdf.set_text_color(80, 80, 80)
            pdf.multi_cell(0, LINE_HEIGHT - 1, _to_latin1_safe(line.strip()), fill=True)
            pdf.set_text_color(26, 26, 46)

        # Regular paragraph
        else:
            pdf.set_font("Helvetica", "", 10)
            pdf.multi_cell(0, LINE_HEIGHT, _cell(line))

    # ── Footer note ───────────────────────────────────────────────────────────
    pdf.ln(8)
    pdf.set_font("Helvetica", "I", 8)
    pdf.set_text_color(156, 163, 175)
    pdf.cell(0, 6, "Generated by Research Agent", align="C")

    return bytes(pdf.output())
