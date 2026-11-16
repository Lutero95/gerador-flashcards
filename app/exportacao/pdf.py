"""PDF com as fontes usadas na geração."""
from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer


def gerar_pdf_fontes(fontes):
    """Devolve os bytes do PDF. O texto das fontes é escapado: Paragraph interpreta marcação."""
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    story = []

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=18,
        textColor='#333',
        spaceAfter=30,
    )
    normal_style = styles['Normal']

    story.append(Paragraph("Fontes Utilizadas na Geração dos Flashcards", title_style))
    story.append(Spacer(1, 0.3 * inch))

    story.append(Paragraph(
        "As seguintes fontes foram utilizadas pela inteligência artificial para gerar o conteúdo dos flashcards:",
        normal_style
    ))
    story.append(Spacer(1, 0.2 * inch))

    if fontes:
        for i, fonte in enumerate(fontes, 1):
            story.append(Paragraph(f"{i}. {escape(str(fonte))}", normal_style))
            story.append(Spacer(1, 0.1 * inch))
    else:
        story.append(Paragraph("Informações geradas com base em conhecimento geral da IA.", normal_style))

    story.append(Spacer(1, 0.3 * inch))
    story.append(Paragraph(
        "<i>Este documento foi gerado automaticamente pelo Gerador de Flashcards.</i>",
        styles['Italic']
    ))

    doc.build(story)
    return buffer.getvalue()
