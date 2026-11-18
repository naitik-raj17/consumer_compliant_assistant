import logging
import re
from datetime import date
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

import config
from classifier import forum_heading, format_inr

log = logging.getLogger(__name__)

SECTIONS = [("facts", "FACTS OF THE CASE"), ("grounds", "GROUNDS"),
            ("relief", "RELIEF SOUGHT"), ("verification", "VERIFICATION")]
_HEAD_RE = re.compile(
    r"^\s*[*#\s]*(?:\d+\.\s*)?(FACTS(?: OF THE CASE)?|GROUNDS(?: OF (?:THE )?COMPLAINT)?|RELIEFS?(?: SOUGHT)?|PRAYER|VERIFICATION)"
    r"\s*\**\s*(?::\s*\**\s*(.*))?$", re.I)
_KEYMAP = {"F": "facts", "G": "grounds", "R": "relief", "P": "relief", "V": "verification"}


def parse_sections(draft: str) -> dict[str, str]:
    out = {k: [] for k, _ in SECTIONS}
    out["preamble"] = []
    current = "preamble"
    for line in (draft or "").splitlines():
        m = _HEAD_RE.match(line)
        if m:
            current = _KEYMAP[m.group(1)[0].upper()]
            if m.group(2):
                out[current].append(m.group(2))
        else:
            out[current].append(line)
    sections = {k: "\n".join(v).strip() for k, v in out.items()}
    if sections["preamble"] and not sections["facts"]:
        sections["facts"], sections["preamble"] = sections["preamble"], ""
    return sections


def _p(text: str) -> str:
    text = (text or "").replace("₹", "Rs. ")
    return escape(text)


def build_pdf(case: dict, user: dict, draft: str, out_path: Path | None = None) -> Path:
    config.ensure_dirs()
    out_path = Path(out_path) if out_path else config.PDF_DIR / f"complaint_{case['id']}.pdf"
    ss = getSampleStyleSheet()
    body = ParagraphStyle("body", parent=ss["Normal"], fontName="Times-Roman", fontSize=11.5,
                          leading=16, alignment=TA_JUSTIFY, spaceAfter=5)
    center = ParagraphStyle("center", parent=body, alignment=TA_CENTER)
    title = ParagraphStyle("title", parent=center, fontName="Times-Bold", fontSize=13.5, leading=18)
    head = ParagraphStyle("head", parent=body, fontName="Times-Bold", fontSize=12, spaceBefore=10, spaceAfter=6)
    right = ParagraphStyle("right", parent=body, alignment=TA_RIGHT)

    sections = parse_sections(draft)
    district = case.get("district") or ""
    place = ", ".join(p for p in (district, case["state"]) if p)
    opp = case.get("opposite_party") or "The Opposite Party"
    today = date.today().strftime("%d-%m-%Y")

    story = [
        Paragraph(_p("BEFORE THE " + forum_heading(case["forum"], case["state"], district).upper()), title),
        Spacer(1, 6),
        Paragraph(_p(f"Consumer Complaint No. ______ of {date.today().year}"), center),
        Spacer(1, 12),
        Paragraph("<b>IN THE MATTER OF:</b>", body),
        Paragraph(_p(f"{user['name']}"), body),
        Paragraph(_p(f"Email: {user['email']}  |  {place}"), body),
        Paragraph("<i>...Complainant</i>", right),
        Paragraph("<b>VERSUS</b>", center),
        Paragraph(_p(opp), body),
        Paragraph("<i>...Opposite Party</i>", right),
        Spacer(1, 10),
        Paragraph("<b>COMPLAINT UNDER SECTION 35 OF THE CONSUMER PROTECTION ACT, 2019</b>", center),
        Paragraph(_p(f"Value of goods/services paid as consideration: Rs. {format_inr(case['value'])}"), center),
        Spacer(1, 8),
        Paragraph("MOST RESPECTFULLY SHOWETH:", body),
    ]
    if sections["preamble"]:
        story += [Paragraph(_p(line), body) for line in sections["preamble"].splitlines() if line.strip()]

    defaults = {
        "facts": case.get("text", ""),
        "grounds": "The acts of the Opposite Party amount to deficiency in service and unfair trade practice "
                   "under Sections 2(11) and 2(47) of the Consumer Protection Act, 2019.",
        "relief": "Refund with interest, compensation for mental agony, and costs of litigation.",
        "verification": f"I, {user['name']}, the Complainant, verify that the contents of this complaint are true "
                        f"and correct to the best of my knowledge and belief. Verified at {place} on {today}.",
    }
    for key, label in SECTIONS:
        story.append(Paragraph(label, head))
        content = sections[key] or defaults[key]
        story += [Paragraph(_p(line), body) for line in content.splitlines() if line.strip()]

    story += [
        Spacer(1, 30),
        Paragraph(_p(f"Place: {place}"), body),
        Paragraph(_p(f"Date: {today}"), body),
        Paragraph("Signature of Complainant", right),
        Paragraph(_p(f"({user['name']})"), right),
    ]

    def _footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("Times-Roman", 9)
        canvas.drawCentredString(A4[0] / 2, 1.2 * cm, f"Page {doc.page}")
        canvas.restoreState()

    doc = SimpleDocTemplate(str(out_path), pagesize=A4, leftMargin=2.5 * cm, rightMargin=2.2 * cm,
                            topMargin=2 * cm, bottomMargin=2 * cm,
                            title=f"Consumer Complaint #{case['id']}", author=user["name"])
    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    log.info("PDF written: %s", out_path)
    return out_path
