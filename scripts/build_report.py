"""Render the checked-in Chinese project report to a standalone, paginated PDF.

Run using Python with reportlab installed. No model/API calls are made.
"""
from __future__ import annotations

import argparse
import html
import re
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
                               KeepTogether, Image, PageBreak)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase.cidfonts import UnicodeCIDFont

ROOT = Path(__file__).resolve().parent.parent

def fonts():
    regular, bold = Path('C:/Windows/Fonts/simsun.ttc'), Path('C:/Windows/Fonts/simhei.ttf')
    if regular.exists() and bold.exists():
        pdfmetrics.registerFont(TTFont('ReportBody', str(regular), subfontIndex=0))
        pdfmetrics.registerFont(TTFont('ReportBold', str(bold)))
    else:
        pdfmetrics.registerFont(UnicodeCIDFont('STSong-Light'))
        pdfmetrics.registerFont(UnicodeCIDFont('HeiseiKakuGo-W5'))
        pdfmetrics.registerFontFamily('STSong-Light', normal='STSong-Light', bold='STSong-Light')
        return 'STSong-Light', 'STSong-Light'
    pdfmetrics.registerFontFamily('ReportBody', normal='ReportBody', bold='ReportBold', italic='ReportBody', boldItalic='ReportBold')
    return 'ReportBody', 'ReportBold'

def inline(s):
    s = html.escape(s)
    s = re.sub(r'`([^`]+)`', r'<font color="#145d5a">\1</font>', s)
    s = re.sub(r'\*\*([^*]+)\*\*', r'<b>\1</b>', s)
    s = re.sub(r'\[([^\]]+)\]\((https?://[^)]+)\)', r'<link href="\2" color="#145d5a">\1</link>', s)
    return s

def render(source, output):
    normal, bold = fonts()
    styles = getSampleStyleSheet()
    base = dict(fontName=normal, fontSize=10.2, leading=16, textColor=colors.HexColor('#23343c'),
                wordWrap='CJK', spaceAfter=7, allowWidows=0, allowOrphans=0)
    styles.add(ParagraphStyle(name='CNBody', **base))
    styles.add(ParagraphStyle(name='CNTitle', fontName=bold, fontSize=23, leading=31,
                              textColor=colors.HexColor('#143d3c'), spaceAfter=16, wordWrap='CJK'))
    styles.add(ParagraphStyle(name='CNH1', fontName=bold, fontSize=14, leading=21,
                              spaceBefore=16, spaceAfter=8, keepWithNext=True, textColor=colors.HexColor('#143d3c'), wordWrap='CJK'))
    styles.add(ParagraphStyle(name='CNH2', fontName=bold, fontSize=11.4, leading=18,
                              spaceBefore=10, spaceAfter=6, keepWithNext=True, textColor=colors.HexColor('#143d3c'), wordWrap='CJK'))
    styles.add(ParagraphStyle(name='CNCell', fontName=normal, fontSize=8.4, leading=12.7, wordWrap='CJK'))
    styles.add(ParagraphStyle(name='CNCode', fontName=normal, fontSize=8.4, leading=13.5,
                              backColor=colors.HexColor('#f0f4f3'), borderPadding=7, wordWrap='CJK', spaceAfter=2))
    styles.add(ParagraphStyle(name='CNBullet', **{**base, 'leftIndent':10, 'firstLineIndent':-8}))
    story = []
    lines = source.read_text(encoding='utf-8').splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
            continue
        if line.startswith('```'):
            i += 1
            code = []
            while i < len(lines) and not lines[i].startswith('```'):
                code.append(lines[i]); i += 1
            for code_line in code:
                story.append(Paragraph(html.escape(code_line).replace(' ', '&nbsp;'), styles['CNCode']))
            story.append(Spacer(1,7))
        elif line.startswith('|'):
            rows = []
            while i < len(lines) and lines[i].strip().startswith('|'):
                cells = [c.strip() for c in lines[i].strip().strip('|').split('|')]
                if not all(re.fullmatch(r'[:\- ]+', c or '-') for c in cells):
                    rows.append([Paragraph(inline(c),styles['CNCell']) for c in cells])
                i += 1
            n = len(rows[0])
            widths = {2:[140,355],3:[98,166,231],4:[86,143,133,133],5:[73,105,105,106,106]}.get(n,[495/n]*n)
            table = Table(rows,colWidths=widths,repeatRows=1,hAlign='LEFT')
            table.setStyle(TableStyle([
                ('BACKGROUND',(0,0),(-1,0),colors.HexColor('#e6efeb')),
                ('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#f7f9f8')]),
                ('VALIGN',(0,0),(-1,-1),'TOP'),
                ('LINEBELOW',(0,0),(-1,0),.6,colors.HexColor('#b8ccc3')),
                ('LINEBELOW',(0,-1),(-1,-1),.5,colors.HexColor('#b8ccc3')),
                ('LEFTPADDING',(0,0),(-1,-1),7),('RIGHTPADDING',(0,0),(-1,-1),7),
                ('TOPPADDING',(0,0),(-1,-1),7),('BOTTOMPADDING',(0,0),(-1,-1),7)]))
            story.extend([table,Spacer(1,9)])
            continue
        elif line.startswith('![image]('):
            path = source.parent / line[9:-1]
            if not path.exists():
                path = ROOT / line[9:-1]
            if path.exists():
                img = Image(str(path))
                ratio = 440 / img.imageWidth
                img.drawWidth = 440
                img.drawHeight = img.imageHeight*ratio
                story.extend([img,Spacer(1,9)])
        elif line.startswith('### '):
            story.append(Paragraph(inline(line[4:]),styles['CNH2']))
        elif line.startswith('## '):
            story.append(Paragraph(inline(line[3:]),styles['CNH1']))
        elif line.startswith('# '):
            story.append(Paragraph(inline(line[2:]),styles['CNTitle']))
        elif line.startswith('- '):
            story.append(Paragraph('• '+inline(line[2:]),styles['CNBullet']))
        else:
            para = line
            while i+1 < len(lines) and lines[i+1].strip() and not lines[i+1].startswith(('#','|','```','- ','![')):
                i += 1
                para += ' '+lines[i].strip()
            story.append(Paragraph(inline(para),styles['CNBody']))
        i += 1

    def decorate(canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor('#cbd8d2'))
        canvas.line(50,41,A4[0]-50,41)
        canvas.setFont(normal,8)
        canvas.setFillColor(colors.HexColor('#64766c'))
        canvas.drawString(50,28,'COMP7608B · Group 30 · Khoj Research Lab')
        canvas.drawRightString(A4[0]-50,28,str(doc.page))
        canvas.restoreState()

    output.parent.mkdir(parents=True,exist_ok=True)
    doc=SimpleDocTemplate(str(output),pagesize=A4,rightMargin=50,leftMargin=50,topMargin=42,bottomMargin=57,
                         title='Khoj Research Lab - 项目实现与本地部署报告',author='Group 30',pageCompression=1)
    doc.build(story,onFirstPage=decorate,onLaterPages=decorate)
    print(output)

if __name__ == '__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--source',type=Path,default=ROOT/'docs/PROJECT_REPORT.zh-CN.md')
    p.add_argument('--output',type=Path,default=ROOT/'docs/Khoj-Research-Lab-Report.pdf')
    a=p.parse_args()
    render(a.source,a.output)
