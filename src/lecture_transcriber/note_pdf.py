"""Local A4 PDF, embedded Korean font, no HTML or network renderer."""
from io import BytesIO
from pathlib import Path
from threading import RLock
from xml.sax.saxutils import escape
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle
from .note_content import KINDS,evidence
LOCK=RLock()

def make_pdf(note):
    with LOCK:
        if 'NoteKorean' not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont('NoteKorean',str(Path(__file__).parent/'fonts/NanumGothic-Regular.ttf')))
        styles={name:ParagraphStyle(name,fontName='NoteKorean',fontSize=size,leading=size*1.6,wordWrap='CJK',spaceAfter=8,textColor=colors.HexColor(color),keepWithNext=heading) for name,size,color,heading in [('body',10,'#162b25',False),('title',19,'#176c4a',True),('heading',13,'#176c4a',True),('meta',8,'#50665a',False)]}
        styles['heading'].spaceBefore=16
        def p(text,style='body'):return Paragraph(escape(str(text)).replace('\n','<br/>'),styles[style])
        story=[p(note['title'],'title'),p(KINDS[note['kind']]+' 강의노트','heading')]
        source=note['sources'];content=note['content']
        def labels(unit):
            # Keep provenance/warnings, but omit lecture timestamps in PDF.
            label=evidence(unit,source) if unit['basis']=='supplement' else ('확인 필요' if unit['uncertain'] else '')
            if label:story.append(p(label,'meta'))
        def block(b):
            labels(b)
            if b['type']=='paragraph':story.append(p(b['text']))
            elif b['type']=='list':story.extend(p('• '+v) for v in b['items'])
            elif b['type']=='qa':story.extend([p('질문: '+b['question']),p('답: '+b['answer'])])
            else:
                table=Table([[p(x) for x in r] for r in [b['columns']]+b['rows']],colWidths=[475/len(b['columns'])]*len(b['columns']),repeatRows=1,hAlign='LEFT',splitByRow=1,splitInRow=1)
                table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#e7f3eb')),('VALIGN',(0,0),(-1,-1),'TOP'),('GRID',(0,0),(-1,-1),.4,colors.HexColor('#bfd4c7')),('LEFTPADDING',(0,0),(-1,-1),7),('RIGHTPADDING',(0,0),(-1,-1),7)]))
                story.extend([table,Spacer(1,10)])
        for section in ([] if note['kind']=='practice' else content['sections']):
            story.append(p(section['heading'],'heading'))
            for b in section['blocks']:block(b)
        if content['questions']:
            story.append(p('문제','heading'))
            if content['fewer_questions_reason']:story.append(p(content['fewer_questions_reason'],'meta'))
            for q in content['questions']:
                story.append(p(q['id']+'. '+q['prompt']));labels(q);story.extend(p(v) for v in q['options'])
            story.append(p('정답과 해설','heading'))
            for a in content['answers']:
                story.extend([p(a['question_id']+'. '+a['answer']),p(a['explanation'])]);labels(a)
        output=BytesIO()
        def page(canvas,doc):
            canvas.saveState();canvas.setFont('NoteKorean',9);canvas.drawCentredString(A4[0]/2,25,str(doc.page));canvas.restoreState()
        SimpleDocTemplate(output,pagesize=A4,leftMargin=60,rightMargin=60,topMargin=45,bottomMargin=45,title=note['title'],author='Speech to Note').build(story,onFirstPage=page,onLaterPages=page)
        return output.getvalue()
