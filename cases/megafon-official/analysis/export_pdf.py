"""Render the final Markdown with bundled ReportLab; no network or installs."""
from pathlib import Path
import re,html
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_LEFT
from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,LongTable,TableStyle,PageBreak,KeepTogether,CondPageBreak
from reportlab.lib.pagesizes import A4
ROOT=Path(__file__).resolve().parents[3]
SRC=ROOT/'deliverables/megafon/strategy.md'
OUT=SRC.with_suffix('.pdf')
fontdir=Path('/System/Library/Fonts/Supplemental')
for name,file in [('Doc','Arial.ttf'),('DocB','Arial Bold.ttf'),('DocI','Arial Italic.ttf')]:pdfmetrics.registerFont(TTFont(name,str(fontdir/file)))
pdfmetrics.registerFontFamily('Doc',normal='Doc',bold='DocB',italic='DocI',boldItalic='DocB')
ink=colors.HexColor('#142D35');accent=colors.HexColor('#007E68');muted=colors.HexColor('#5A6A6E')
styles={
 'body':ParagraphStyle('body',fontName='Doc',fontSize=9.4,leading=13.5,textColor=ink,spaceAfter=7,allowWidows=0,allowOrphans=0),
 'title':ParagraphStyle('title',fontName='DocB',fontSize=23,leading=28,textColor=ink,spaceAfter=16),
 'h2':ParagraphStyle('h2',fontName='DocB',fontSize=17,leading=21,textColor=accent,spaceAfter=13,keepWithNext=True),
 'h3':ParagraphStyle('h3',fontName='DocB',fontSize=12,leading=16,textColor=ink,spaceBefore=12,spaceAfter=8,keepWithNext=True),
 'cell':ParagraphStyle('cell',fontName='Doc',fontSize=8.0,leading=10.8,textColor=ink,spaceAfter=0),
 'th':ParagraphStyle('th',fontName='DocB',fontSize=8.0,leading=10.8,textColor=colors.white,spaceAfter=0),
 'caption':ParagraphStyle('caption',fontName='DocI',fontSize=8.3,leading=11,textColor=muted,spaceAfter=8)}
def inline(s):
 s=html.escape(s).replace('`','')
 s=re.sub(r'\*\*(.*?)\*\*',r'<b>\1</b>',s)
 s=re.sub(r'\[\[C-(\d+)\]\]',r'<font color="#6E7C80" size="7">[C-\1]</font>',s)
 return s
lines=SRC.read_text().splitlines();story=[];i=0;section=0
W=A4[0]-84
while i<len(lines):
 line=lines[i].strip()
 if not line:i+=1;continue
 if line.startswith('|'):
  raw=[]
  while i<len(lines) and lines[i].strip().startswith('|'):
   row=[c.strip() for c in lines[i].strip().strip('|').split('|')]
   if not all(re.fullmatch(r':?-+:?',c) for c in row):raw.append(row)
   i+=1
  n=len(raw[0])
  # Give descriptive columns enough room while retaining legible numeric columns.
  if n==7:weights=[2.7,1,1.05,1.22,1,1.25,1.35]
  elif n==6:weights=[2.8,1,1,1.8,1.8,1]
  elif n==5:weights=[2.1,2.0,1,2.8,2.0] if 'Период' not in raw[0][0] else [1,1.8,2.4,1.6,2.4]
  elif n==4:weights=[1.8,2.5,2.5,2.5]
  elif n==3:weights=[2.6,3.6,3.7]
  else:weights=[1]*n
  widths=[W*w/sum(weights) for w in weights]
  data=[[Paragraph(inline(c),styles['th' if ri==0 else 'cell']) for c in row] for ri,row in enumerate(raw)]
  table=LongTable(data,colWidths=widths,repeatRows=1,hAlign='LEFT',splitByRow=1,splitInRow=1)
  table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),accent),('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.HexColor('#F1F6F5'),colors.white]),('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),6),('RIGHTPADDING',(0,0),(-1,-1),6),('TOPPADDING',(0,0),(-1,-1),7),('BOTTOMPADDING',(0,0),(-1,-1),7),('LINEBELOW',(0,0),(-1,0),.6,accent),('LINEBELOW',(0,1),(-1,-1),.25,colors.HexColor('#D1DEDA'))]))
  height=table.wrap(W,100000)[1]
  block=[table,Spacer(1,10)]
  if story and isinstance(story[-1],Paragraph) and story[-1].style.name=='h3' and height<620:
   block.insert(0,story.pop())
  story.extend([KeepTogether(block)] if height<650 else block)
  continue
 if line.startswith('# '):story.append(Paragraph(inline(line[2:]),styles['title']))
 elif line.startswith('## '):
  story.append(PageBreak() if section==0 else CondPageBreak(240));section+=1;story.append(Spacer(1,10));story.append(Paragraph(inline(line[3:]),styles['h2']))
 elif line.startswith('### '):
  if line.startswith('### 5.3.'):story.append(CondPageBreak(370))
  story.append(Paragraph(inline(line[4:]),styles['h3']))
 else:
  paragraph=[line]
  while i+1<len(lines) and lines[i+1].strip() and not lines[i+1].lstrip().startswith(('#','|')):
   # Preserve numbered steps as separate paragraphs.
   if re.match(r'\d+\. ',lines[i+1]):break
   i+=1;paragraph.append(lines[i].strip())
  text=' '.join(paragraph)
  style=styles['caption'] if text.startswith('Конкурсная стратегия') else styles['body']
  story.append(Paragraph(inline(text),style))
 i+=1

def page(canvas,doc):
 canvas.saveState();canvas.setStrokeColor(accent);canvas.setLineWidth(.6);canvas.line(42,A4[1]-31,A4[0]-42,A4[1]-31)
 canvas.setFont('Doc',7.5);canvas.setFillColor(muted)
 canvas.drawString(42,A4[1]-23,'СВЯЗЬ ДЛЯ БЛИЗКИХ  /  УЧЕБНАЯ СТРАТЕГИЯ')
 canvas.drawString(42,24,'22.11.2026  •  Сценарии на допущениях  •  Решение не подтверждено')
 canvas.drawRightString(A4[0]-42,24,str(doc.page));canvas.restoreState()
doc=SimpleDocTemplate(str(OUT),pagesize=A4,rightMargin=42,leftMargin=42,topMargin=46,bottomMargin=44,title='Связь для близких — конкурсная стратегия',author='Стратег Фабрики продуктов',pageCompression=1)
doc.build(story,onFirstPage=page,onLaterPages=page)
print(OUT)
