"""Build the PDF and Markdown description from reviewed structured content.

Run with Python containing reportlab and Pillow. Core agent dependencies do not
include the optional report-authoring tools.
"""
from pathlib import Path
import html
import json
import os
import re
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, PageBreak, Flowable
from PIL import Image as PILImage

ROOT = Path(__file__).resolve().parents[2]
DEST = ROOT / "deliverables/megafon"
DATA = json.loads((Path(__file__).parent / "report.json").read_text())
FONTS = Path(os.environ.get("SUBMISSION_FONT_DIR", "/System/Library/Fonts/Supplemental"))
for name, file in [("Body", "Arial.ttf"), ("Bold", "Arial Bold.ttf")]:
    pdfmetrics.registerFont(TTFont(name, str(FONTS / file)))
pdfmetrics.registerFontFamily("Body", normal="Body", bold="Bold", italic="Body", boldItalic="Bold")
INK, GREEN, GRAY = [colors.HexColor(c) for c in ["#172D32", "#007B64", "#52645F"]]
WIDTH = A4[0] - 88
S = {
    "title": ParagraphStyle("title", fontName="Bold", fontSize=23, leading=29, textColor=INK, spaceAfter=14),
    "h": ParagraphStyle("h", fontName="Bold", fontSize=19, leading=24, textColor=INK, spaceAfter=15),
    "lead": ParagraphStyle("lead", fontName="Bold", fontSize=11.2, leading=16, textColor=INK, spaceAfter=12),
    "body": ParagraphStyle("body", fontName="Body", fontSize=10.0, leading=14.3, textColor=INK, spaceAfter=9),
    "caption": ParagraphStyle("caption", fontName="Body", fontSize=8, leading=11, textColor=GRAY, spaceBefore=5, spaceAfter=9),
    "source": ParagraphStyle("source", fontName="Body", fontSize=7.6, leading=10.4, textColor=GRAY, spaceBefore=8),
    "cell": ParagraphStyle("cell", fontName="Body", fontSize=8.8, leading=12.1, textColor=INK),
    "th": ParagraphStyle("th", fontName="Bold", fontSize=8.8, leading=12.1, textColor=colors.white),
}


def p(text, style="body"):
    return Paragraph(html.escape(text).replace("\n", "<br/>"), S[style])


class Workflow(Flowable):
    def __init__(self):
        Flowable.__init__(self)
        self.width, self.height = WIDTH, 98

    def draw(self):
        canvas = self.canv
        labels = ["Запрос", "Исследование", "Варианты", "Проверка", "Выбор"]
        box = (WIDTH - 32) / 5
        for i, label in enumerate(labels):
            x = i * (box + 8)
            canvas.setFillColor(colors.HexColor("#EDF5F1"))
            canvas.setStrokeColor(colors.HexColor("#C9DED4"))
            canvas.roundRect(x, 48, box, 34, 5, fill=1, stroke=1)
            canvas.setFillColor(INK)
            canvas.setFont("Bold", 8.2)
            canvas.drawCentredString(x + box / 2, 61, label)
            if i < 4:
                canvas.setStrokeColor(GREEN)
                canvas.line(x + box + 1, 65, x + box + 7, 65)
        canvas.setFont("Body", 9)
        canvas.setFillColor(GRAY)
        canvas.drawString(0, 27, "LLM + инструкции + skills + локальный CLI")
        canvas.drawString(0, 10, "Файлы кейса сохраняют доказательства, состояние и следующий шаг")


def table(spec):
    widths = [WIDTH * .31, WIDTH * .69]
    rows = [[p(c, "th") for c in spec["headers"]]]
    rows += [[p(c, "cell") for c in row] for row in spec["rows"]]
    result = Table(rows, colWidths=widths, repeatRows=1, hAlign="LEFT")
    result.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), GREEN),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F4F7F5")]),
        ("GRID", (0, 0), (-1, -1), .4, colors.HexColor("#D9D9D9")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    ]))
    return result


def image(name, max_height=240):
    src = DEST / "submission" / name
    with PILImage.open(src) as im:
        w, h = im.size
    scale = min(WIDTH / w, max_height / h)
    return Image(str(src), width=w * scale, height=h * scale, hAlign="LEFT")


def footer(canvas, doc):
    canvas.saveState()
    canvas.setStrokeColor(colors.HexColor("#D2DED8"))
    canvas.line(44, 42, A4[0] - 44, 42)
    canvas.setFont("Body", 8)
    canvas.setFillColor(GRAY)
    canvas.drawString(44, 28, "Стратег Фабрики продуктов · Описание работы · 22 ноября 2026")
    canvas.drawRightString(A4[0] - 44, 28, str(doc.page))
    canvas.restoreState()


story = []
md = ["# " + DATA["title"], "", "Версия для конкурсной сдачи · 22 ноября 2026 года", ""]
for i, page in enumerate(DATA["pages"]):
    if i:
        story.append(PageBreak())
    else:
        story += [p("СТРАТЕГ ФАБРИКИ ПРОДУКТОВ", "caption"), p("Описание ИИ агента", "title")]
    story.append(p(f"{i + 1}. {page['title']}", "h"))
    md += ["## " + page["title"], ""]
    if page.get("lead"):
        story.append(p(page["lead"], "lead"))
        md += [page["lead"], ""]
    for text in page.get("paragraphs", []):
        story.append(p(text))
        md += [text, ""]
    if page.get("diagram"):
        story.append(Workflow())
    if page.get("table"):
        story.append(table(page["table"]))
        md += ["| " + " | ".join(page["table"]["headers"]) + " |", "| --- | --- |"]
        md += ["| " + " | ".join(row) + " |" for row in page["table"]["rows"]] + [""]
    if page.get("image"):
        story += [Spacer(1, 4), image(page["image"], 238), p(page["caption"], "caption")]
        md += [f"![{page['caption']}](submission/{page['image']})", ""]
    for name, caption in zip(page.get("images", []), page.get("captions", [])):
        story += [image(name, 176), p(caption, "caption")]
        md += [f"![{caption}](submission/{name})", ""]
    story.append(p(page["source"], "source"))
    md += [page["source"], ""]
doc = SimpleDocTemplate(str(DEST / "agent-description.pdf"), pagesize=A4, leftMargin=44,
                        rightMargin=44, topMargin=42, bottomMargin=55,
                        title=DATA["title"], author="Yablochniki", subject="Описание конкурсного ИИ агента и границ проверки")
doc.build(story, onFirstPage=footer, onLaterPages=footer)
(DEST / "agent-description.md").write_text("\n".join(md))
print("Built agent-description.pdf and agent-description.md")
