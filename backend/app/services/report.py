from collections import Counter
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.models import Detection, Mission, MissionImage


def build_report(mission: Mission, images: list[MissionImage], detections: list[Detection]) -> bytes:
    buffer = BytesIO()
    document = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=18 * mm, leftMargin=18 * mm)
    styles = getSampleStyleSheet()
    story = [
        Paragraph("Informe de inspección de caminos mineros", styles["Title"]),
        Paragraph(f"{mission.name} · {mission.segment}", styles["Heading2"]),
        Paragraph("Hallazgos que representan riesgo para los neumáticos de camiones CAEX.", styles["BodyText"]),
        Paragraph("Resultados simulados mientras DETECTOR_MODE=mock.", styles["Italic"]),
        Spacer(1, 8 * mm),
    ]
    counts = Counter(detection.label for detection in detections if detection.review_status != "rejected")
    summary_data = [["Imágenes", "Hallazgos", "Confirmados", "Pendientes"]]
    summary_data.append([
        len(images),
        len(detections),
        sum(item.review_status == "confirmed" for item in detections),
        sum(item.review_status == "pending" for item in detections),
    ])
    summary = Table(summary_data, colWidths=[38 * mm] * 4)
    summary.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#17222d")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("BACKGROUND", (0, 1), (-1, 1), colors.HexColor("#f1f4f5")),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#dce2e5")),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
    ]))
    story.extend([summary, Spacer(1, 8 * mm), Paragraph("Resumen por tipo", styles["Heading2"])])
    type_rows = [["Tipo", "Cantidad"]] + [[label, amount] for label, amount in sorted(counts.items())]
    type_table = Table(type_rows or [["Tipo", "Cantidad"]], colWidths=[110 * mm, 42 * mm])
    type_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f08c32")),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#dce2e5")),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.extend([type_table, Spacer(1, 8 * mm), Paragraph("Detalle", styles["Heading2"])])
    image_names = {image.id: image.filename for image in images}
    detail_rows = [["Imagen", "Hallazgo", "Confianza", "Ubicación", "Estado"]]
    detail_rows += [
        [
            image_names.get(item.image_id, "—")[:27],
            item.label,
            f"{item.confidence:.0%}",
            next(
                (f"{image.latitude:.5f}, {image.longitude:.5f}" for image in images if image.id == item.image_id and image.latitude is not None and image.longitude is not None),
                "Sin EXIF",
            ),
            item.review_status,
        ]
        for item in detections
    ]
    detail = Table(detail_rows, repeatRows=1, colWidths=[48 * mm, 35 * mm, 20 * mm, 38 * mm, 24 * mm])
    detail.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#17222d")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#dce2e5")),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(detail)
    document.build(story)
    return buffer.getvalue()
