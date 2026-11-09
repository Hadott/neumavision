from collections import Counter
from io import BytesIO
from pathlib import Path

from PIL import Image as PILImage, ImageDraw, ImageFont
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.lib.enums import TA_CENTER
from reportlab.platypus import (
    CondPageBreak,
    Image,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.models import Deteccion, Imagen, Mision


LOGO_PATH = Path(__file__).resolve().parents[2] / "assets" / "logo.png"
ICONS_DIR = Path(__file__).resolve().parents[2] / "assets" / "icons"

BLACK = colors.HexColor("#0b0c0e")
YELLOW = colors.HexColor("#facc15")
GOLD = colors.HexColor("#a16207")
LINE = colors.HexColor("#dce2e5")
LIGHT = colors.HexColor("#f7f8f8")
MUTED = colors.HexColor("#6c7881")
ON_BRAND = colors.HexColor("#171412")
DANGER = colors.HexColor("#c0392b")
WARN = colors.HexColor("#a16207")
OPTIMO = colors.HexColor("#167d72")

CRITICALITY_COLORS = {"critico": DANGER, "moderado": WARN, "optimo": OPTIMO}
CRITICALITY_LABELS = {"critico": "CRÍTICO", "moderado": "MODERADO", "optimo": "ÓPTIMO"}

GOOD_CONDITION_LABEL = "Carpeta Buen Estado"

LABEL_COLORS = {
    "Rocas": "#f2b23e",
    GOOD_CONDITION_LABEL: "#2bb8a8",
    "Material Pedregoso": "#9e82ff",
}
FALLBACK_COLOR = "#4ca8ff"

RECOMMENDATIONS = {
    "Rocas": "Retirar la roca de la pista o berma antes de que un CAEX transite por el sector, evitando dañar el pretil de seguridad durante el retiro.",
    "Material Pedregoso": "Retirar el material pedregoso acumulado en la pista y evaluar si el pretil lateral requiere refuerzo adicional para evitar nuevos derrames.",
    GOOD_CONDITION_LABEL: "Sin acción requerida: el tramo fotografiado se encuentra en buen estado. Mantener en el monitoreo periódico habitual.",
}
DEFAULT_RECOMMENDATION = "Evaluar el hallazgo en terreno y aplicar la medida correctiva que corresponda antes del próximo tránsito de camiones."

# Maquinaria de apoyo sugerida por tipo de hallazgo (icon key -> nombre a mostrar)
MACHINERY = {
    "Rocas": [
        ("cargador_frontal", "Cargador frontal"),
        ("camion_tolva", "Camión tolva"),
    ],
    "Material Pedregoso": [
        ("bulldozer", "Bulldozer"),
        ("cargador_frontal", "Cargador frontal"),
        ("camion_tolva", "Camión tolva"),
    ],
}
DEFAULT_MACHINERY = [("motoniveladora", "Motoniveladora"), ("cargador_frontal", "Cargador frontal")]

# Causa probable y consecuencia de no corregir el hallazgo, por tipo
CAUSES = {
    "Rocas": {
        "causa": "Material suelto o de sobretamaño que cae de la tolva de un CAEX, se desprende de un pretil "
        "lateral, o queda en la pista tras una tronadura o el paso de equipos de carguío.",
        "consecuencia": "Corte o perforación de la banda de rodado al pasar por encima, especialmente en la pared "
        "lateral del neumático. Puede derivar en pérdida de presión inmediata, exposición de cables de la carcasa "
        "y, en el peor caso, en la pérdida total del neumático OTR.",
    },
    "Material Pedregoso": {
        "causa": "Inestabilidad del talud o pretil lateral del camino, erosión por riego mal controlado, o "
        "vibración por tránsito de equipos pesados que suelta material pedregoso hacia la plataforma de tránsito.",
        "consecuencia": "El material pedregoso acumulado en la pista puede dañar los neumáticos igual que una "
        "roca suelta, y su presencia indica un riesgo mayor de inestabilidad del talud que podría derivar en un "
        "derrame de mayor magnitud sobre la vía o los equipos que transitan.",
    },
}
DEFAULT_CAUSE = {
    "causa": "Deterioro progresivo del camino por tránsito y condiciones climáticas sin mantención oportuna.",
    "consecuencia": "Riesgo de daño a los neumáticos OTR y a los componentes del camión si el hallazgo no se "
    "corrige antes del próximo tránsito.",
}

FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/Library/Fonts/Arial Bold.ttf",
]


def _load_font(size: int) -> ImageFont.FreeTypeFont:
    for candidate in FONT_CANDIDATES:
        path = Path(candidate)
        if path.exists():
            try:
                return ImageFont.truetype(str(path), size)
            except OSError:
                continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def _hex_to_rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))


def _annotate_image(image: Imagen, image_detections: list[Deteccion], max_width: int = 1300) -> BytesIO | None:
    """Draws bounding boxes for non-rejected detections on a resized copy of the photo."""
    path = Path(image.ruta_almacenada)
    if not path.exists():
        return None
    try:
        with PILImage.open(path) as source:
            photo = source.convert("RGB")
    except Exception:
        return None

    scale = min(1.0, max_width / photo.width) if photo.width else 1.0
    if scale < 1.0:
        photo = photo.resize((round(photo.width * scale), round(photo.height * scale)))
    draw = ImageDraw.Draw(photo)
    label_font = _load_font(max(14, round(photo.width * 0.014)))
    stroke = max(2, round(photo.width * 0.0035))

    for detection in image_detections:
        if detection.estado_revision == "rejected":
            continue
        rgb = _hex_to_rgb(LABEL_COLORS.get(detection.clase, FALLBACK_COLOR))
        left = detection.bbox_x * photo.width
        top = detection.bbox_y * photo.height
        right = left + detection.bbox_ancho * photo.width
        bottom = top + detection.bbox_alto * photo.height
        draw.rectangle([left, top, right, bottom], outline=rgb, width=stroke)
        tag = f"{detection.clase} · {detection.confianza:.0%}"
        text_bbox = draw.textbbox((0, 0), tag, font=label_font)
        tag_w = text_bbox[2] - text_bbox[0] + 12
        tag_h = text_bbox[3] - text_bbox[1] + 8
        tag_top = max(0, top - tag_h)
        draw.rectangle([left, tag_top, left + tag_w, tag_top + tag_h], fill=rgb)
        draw.text((left + 6, tag_top + 3), tag, fill=(15, 12, 8), font=label_font)

    buffer = BytesIO()
    photo.save(buffer, format="JPEG", quality=85)
    buffer.seek(0)
    return buffer


def _styles():
    base = getSampleStyleSheet()
    return {
        "h1": ParagraphStyle("h1c", parent=base["Heading1"], fontSize=15, textColor=BLACK, spaceBefore=4, spaceAfter=8),
        "h2": ParagraphStyle("h2c", parent=base["Heading2"], fontSize=11, textColor=BLACK, spaceBefore=2, spaceAfter=4),
        "body": ParagraphStyle("bodyc", parent=base["BodyText"], fontSize=9.5, leading=14, textColor=colors.HexColor("#2a2a2a")),
        "muted": ParagraphStyle("mutedc", parent=base["BodyText"], fontSize=8.5, leading=12, textColor=MUTED),
        "cover_title": ParagraphStyle("coverTitle", parent=base["Title"], fontSize=26, textColor=BLACK, spaceAfter=6),
        "cover_sub": ParagraphStyle("coverSub", parent=base["Italic"], fontSize=12, textColor=colors.HexColor("#3a3a3a")),
        "kpi_label": ParagraphStyle("kpiLabel", parent=base["Normal"], fontSize=8, textColor=colors.white, alignment=TA_CENTER),
        "kpi_value": ParagraphStyle("kpiValue", parent=base["Normal"], fontSize=17, textColor=colors.white, alignment=TA_CENTER, spaceBefore=2),
        "card_title": ParagraphStyle("cardTitle", parent=base["Heading3"], fontSize=10.5, textColor=BLACK, spaceAfter=0),
        "thumb_caption": ParagraphStyle("thumbCaption", parent=base["Normal"], fontSize=7.5, textColor=colors.HexColor("#3a3a3a"), alignment=TA_CENTER),
    }


def _status_badge(status: str):
    return {
        "confirmed": ("CONFIRMADO — requiere acción", DANGER),
        "pending": ("PENDIENTE DE REVISIÓN", WARN),
    }.get(status, (status.upper(), MUTED))


def _diagnosis_block(label: str, styles: dict) -> Table:
    """Full-width 'causa / consecuencia / maquinaria sugerida' block for one finding type."""
    cause = CAUSES.get(label, DEFAULT_CAUSE)
    machinery = MACHINERY.get(label, DEFAULT_MACHINERY)

    label_style = ParagraphStyle(
        "diagLabel", parent=styles["muted"], fontName="Helvetica-Bold", textColor=BLACK, fontSize=8, spaceAfter=1,
    )

    icon_cells, caption_cells = [], []
    for icon_key, name in machinery:
        icon_path = ICONS_DIR / f"{icon_key}.png"
        if icon_path.exists():
            icon_cells.append(Image(str(icon_path), width=22 * mm, height=14.7 * mm))
        else:
            icon_cells.append(Paragraph("", styles["muted"]))
        caption_cells.append(Paragraph(name, styles["thumb_caption"]))
    icon_col_width = min(31 * mm, (77 * mm) / max(len(icon_cells), 1))
    machinery_table = Table([icon_cells, caption_cells], colWidths=[icon_col_width] * len(icon_cells))
    machinery_table.setStyle(TableStyle([
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("LEFTPADDING", (0, 0), (-1, -1), 1),
        ("RIGHTPADDING", (0, 0), (-1, -1), 1),
    ]))

    body_rows = [
        [Paragraph("CAUSA PROBABLE", label_style), Paragraph("CONSECUENCIA SI NO SE CORRIGE", label_style)],
        [Paragraph(cause["causa"], styles["muted"]), Paragraph(cause["consecuencia"], styles["muted"])],
        [Paragraph("MAQUINARIA SUGERIDA", label_style), ""],
        [machinery_table, ""],
    ]
    block = Table(
        [
            [Paragraph(
                f'<font color="{LABEL_COLORS.get(label, FALLBACK_COLOR)}">●</font> <b>{label}</b> — diagnóstico y maquinaria sugerida',
                styles["card_title"],
            ), ""],
            *body_rows,
        ],
        colWidths=[77 * mm, 77 * mm],
    )
    block.setStyle(TableStyle([
        ("SPAN", (0, 0), (1, 0)),
        ("SPAN", (0, 3), (1, 3)),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 4),
        ("TOPPADDING", (0, 3), (-1, 3), 4),
    ]))

    wrapper = Table([[block]], colWidths=[160 * mm])
    wrapper.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.7, GOLD),
        ("LINEABOVE", (0, 0), (-1, 0), 2.2, GOLD),
        ("BACKGROUND", (0, 0), (-1, -1), LIGHT),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    ]))
    return wrapper


def _footer(canvas, document):
    canvas.saveState()
    canvas.setStrokeColor(LINE)
    canvas.line(18 * mm, 16 * mm, A4[0] - 18 * mm, 16 * mm)
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(MUTED)
    canvas.drawString(18 * mm, 11 * mm, "NeumaVision · Informe generado automáticamente por el sistema de visión por computador")
    canvas.drawRightString(A4[0] - 18 * mm, 11 * mm, f"Página {document.page}")
    canvas.restoreState()


def _draw_tire_watermark(canvas, cx: float, cy: float, r_outer: float, alpha: float = 0.055):
    """Original decorative pictogram (concentric rings + tread ticks) evoking an OTR tire —
    NeumaDiesel's own business — used as a faint cover background, not copied artwork."""
    import math

    watermark = colors.Color(BLACK.red, BLACK.green, BLACK.blue, alpha=alpha)
    canvas.saveState()
    canvas.setStrokeColor(watermark)
    for i in range(5):
        rr = r_outer * (1 - i * 0.15)
        canvas.setLineWidth(2.4)
        canvas.circle(cx, cy, rr, stroke=1, fill=0)
    inner_r = r_outer * 0.86
    outer_r = r_outer * 1.05
    n = 44
    canvas.setLineWidth(3.6)
    for i in range(n):
        angle = 2 * math.pi * i / n
        x1 = cx + inner_r * math.cos(angle)
        y1 = cy + inner_r * math.sin(angle)
        x2 = cx + outer_r * math.cos(angle)
        y2 = cy + outer_r * math.sin(angle)
        canvas.line(x1, y1, x2, y2)
    canvas.restoreState()


def build_report(mission: Mision, images: list[Imagen], detections: list[Deteccion]) -> bytes:
    styles = _styles()
    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=19 * mm,
        bottomMargin=20 * mm,
        title=f"Informe NeumaVision — {mission.nombre}",
    )

    def _cover_decoration(canvas, doc):
        canvas.saveState()
        _draw_tire_watermark(canvas, A4[0] - 15 * mm, A4[1] * 0.60, 100 * mm)
        band_h = 24 * mm
        canvas.setFillColor(BLACK)
        canvas.rect(0, 0, A4[0], band_h, fill=1, stroke=0)
        canvas.setFillColor(YELLOW)
        canvas.rect(0, band_h, A4[0], 1.3 * mm, fill=1, stroke=0)

        date_str = mission.fecha_creacion.strftime("%d-%m-%Y")
        canvas.setFont("Helvetica-Bold", 9)
        canvas.setFillColor(colors.white)
        canvas.drawString(18 * mm, 15.5 * mm, "NEUMADIESEL")
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#c7c9cc"))
        canvas.drawString(18 * mm, 11 * mm, f"Tramo: {mission.tramo}")
        canvas.drawString(18 * mm, 7 * mm, f"Fecha de misión: {date_str}")

        canvas.setFont("Helvetica-Bold", 9)
        canvas.setFillColor(YELLOW)
        canvas.drawRightString(A4[0] - 18 * mm, 15.5 * mm, "GENERADO AUTOMÁTICAMENTE")
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#c7c9cc"))
        canvas.drawRightString(A4[0] - 18 * mm, 11 * mm, "Sistema de visión por computador NeumaVision")
        canvas.drawRightString(A4[0] - 18 * mm, 7 * mm, f"Generado el {date_str}")
        canvas.restoreState()

    def _content_decoration(canvas, doc):
        canvas.saveState()
        bar_h = 14 * mm
        canvas.setFillColor(BLACK)
        canvas.rect(0, A4[1] - bar_h, A4[0], bar_h, fill=1, stroke=0)
        canvas.setFillColor(YELLOW)
        canvas.rect(0, A4[1] - bar_h - 0.9 * mm, A4[0], 0.9 * mm, fill=1, stroke=0)
        canvas.setFont("Helvetica-Bold", 8)
        canvas.setFillColor(YELLOW)
        canvas.drawString(18 * mm, A4[1] - 9.3 * mm, "NEUMAVISION")
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(colors.white)
        label = mission.nombre if len(mission.nombre) <= 58 else mission.nombre[:55] + "..."
        canvas.drawRightString(A4[0] - 18 * mm, A4[1] - 9.3 * mm, f"Informe de Inspección de Caminos · {label}")
        canvas.restoreState()
        _footer(canvas, doc)

    by_image: dict[str, list[Deteccion]] = {}
    for detection in detections:
        by_image.setdefault(detection.id_imagen, []).append(detection)

    active = [d for d in detections if d.estado_revision != "rejected"]
    discarded = [d for d in detections if d.estado_revision == "rejected"]
    confirmed = [d for d in active if d.estado_revision == "confirmed"]
    pending = [d for d in active if d.estado_revision == "pending"]
    counts = Counter(d.clase for d in active)
    average_confidence = sum(d.confianza for d in active) / len(active) if active else 0.0
    located = sum(1 for image in images if image.latitud is not None and image.longitud is not None)

    story = []

    # ---- Cover: branding and title only (running header/footer drawn on the canvas) ----
    top_row_cells = []
    if LOGO_PATH.exists():
        logo = Image(str(LOGO_PATH), width=26 * mm, height=26 * mm)
        logo.hAlign = "LEFT"
        top_row_cells.append(logo)
    else:
        top_row_cells.append(Paragraph("", styles["muted"]))
    tag_style = ParagraphStyle("coverTag", parent=styles["muted"], alignment=2, fontSize=8.5, leading=12)
    top_row_cells.append(Paragraph(
        f"<b>INFORME TÉCNICO</b><br/>Sistema NeumaVision · {mission.fecha_creacion.year}",
        tag_style,
    ))
    top_row = Table([top_row_cells], colWidths=[80 * mm, 76 * mm])
    top_row.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(top_row)
    story.append(Spacer(1, 20 * mm))
    story.append(Paragraph("NEUMADIESEL", ParagraphStyle("brand", fontName="Helvetica-Bold", fontSize=11, textColor=GOLD, spaceAfter=3)))
    story.append(Paragraph("Informe de Inspección de Caminos", styles["cover_title"]))
    story.append(Spacer(1, 3 * mm))
    story.append(Paragraph(mission.nombre, ParagraphStyle(
        "coverMission", fontName="Helvetica-Bold", fontSize=13.5, textColor=BLACK, spaceAfter=3, leading=17,
    )))
    story.append(Paragraph(mission.tramo, styles["cover_sub"]))
    story.append(PageBreak())

    # ---- Executive summary ----
    story.append(Paragraph("Resumen ejecutivo", styles["h1"]))
    story.append(Paragraph(
        "Este informe reemplaza el levantamiento manual de anomalías del camino: identifica rocas y acumulaciones "
        "de material pedregoso que puedan dañar los neumáticos OTR de los camiones CAEX, y verifica el estado de "
        "la carpeta de rodado, a partir de imágenes RGB georreferenciadas.",
        styles["body"],
    ))
    story.append(Spacer(1, 5 * mm))

    legend_data = [
        [
            Paragraph("<b>● CONFIRMADO</b>", ParagraphStyle("legendC", fontSize=9, textColor=DANGER)),
            Paragraph("Hallazgo validado por un revisor — requiere corrección en terreno.", styles["muted"]),
        ],
        [
            Paragraph("<b>● PENDIENTE</b>", ParagraphStyle("legendP", fontSize=9, textColor=WARN)),
            Paragraph("Detectado por el modelo, aún sin validar por un revisor.", styles["muted"]),
        ],
    ]
    legend = Table(legend_data, colWidths=[42 * mm, 132 * mm])
    legend.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.6, LINE),
        ("INNERGRID", (0, 0), (-1, -1), 0.4, LINE),
        ("BACKGROUND", (0, 0), (-1, -1), LIGHT),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(legend)
    story.append(Spacer(1, 7 * mm))

    kpis = [
        ("Imágenes", str(len(images))),
        ("Hallazgos activos", str(len(active))),
        ("Confirmados", str(len(confirmed))),
        ("Pendientes", str(len(pending))),
        ("Confianza media", f"{average_confidence:.0%}"),
        ("Con ubicación GPS", f"{located}/{len(images)}"),
    ]
    kpi_cells = []
    for k, v in kpis:
        kpi_cells.append(Paragraph(f"{v}<br/><font size=7>{k.upper()}</font>", ParagraphStyle(
            "kpiCell", fontSize=16, leading=18, textColor=colors.white, alignment=TA_CENTER,
        )))
    kpi_grid = Table([kpi_cells], colWidths=[28 * mm] * len(kpi_cells))
    kpi_grid.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), BLACK),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("LINEAFTER", (0, 0), (-2, 0), 0.6, colors.HexColor("#2a2a2c")),
    ]))
    story.append(kpi_grid)
    story.append(Spacer(1, 7 * mm))

    story.append(Paragraph("Hallazgos por tipo", styles["h2"]))
    type_rows = [["Tipo", "Cantidad", "Recomendación general"]]
    for label, amount in sorted(counts.items(), key=lambda item: -item[1]):
        type_rows.append([
            Paragraph(f'<font color="{LABEL_COLORS.get(label, FALLBACK_COLOR)}">●</font> {label}', styles["body"]),
            str(amount),
            Paragraph(RECOMMENDATIONS.get(label, DEFAULT_RECOMMENDATION), styles["body"]),
        ])
    if len(type_rows) == 1:
        type_rows.append([Paragraph("—", styles["body"]), "0", Paragraph("Sin hallazgos activos en esta misión.", styles["body"])])
    type_table = Table(type_rows, colWidths=[32 * mm, 20 * mm, 122 * mm], repeatRows=1)
    type_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), YELLOW),
        ("TEXTCOLOR", (0, 0), (-1, 0), ON_BRAND),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.4, LINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT]),
    ]))
    story.append(type_table)
    story.append(Spacer(1, 8 * mm))

    criticality_counts = Counter(
        image.criticidad_manual for image in images if image.criticidad_manual in CRITICALITY_COLORS
    )
    if criticality_counts:
        story.append(Paragraph("Clasificación manual de imágenes (semáforo de criticidad)", styles["h2"]))
        story.append(Paragraph(
            "Criticidad asignada por el revisor a cada imagen durante la etapa de revisión, independiente de la "
            "confianza del modelo.",
            styles["muted"],
        ))
        story.append(Spacer(1, 2 * mm))
        crit_cells, crit_captions = [], []
        for level in ("critico", "moderado", "optimo"):
            amount = criticality_counts.get(level, 0)
            color_hex = f"#{CRITICALITY_COLORS[level].hexval()[2:]}"
            crit_cells.append(Paragraph(
                f'<font color="{color_hex}" size="16">●</font> <font size="13"><b>{amount}</b></font>',
                styles["body"],
            ))
            crit_captions.append(Paragraph(CRITICALITY_LABELS[level], styles["muted"]))
        unclassified = len(images) - sum(criticality_counts.values())
        if unclassified > 0:
            crit_cells.append(Paragraph(f'<font size="13"><b>{unclassified}</b></font>', styles["body"]))
            crit_captions.append(Paragraph("SIN CLASIFICAR", styles["muted"]))
        criticality_table = Table([crit_cells, crit_captions], colWidths=[38 * mm] * len(crit_cells))
        criticality_table.setStyle(TableStyle([
            ("BOX", (0, 0), (-1, -1), 0.6, LINE),
            ("INNERGRID", (0, 0), (-1, -1), 0.4, LINE),
            ("BACKGROUND", (0, 0), (-1, -1), LIGHT),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]))
        story.append(criticality_table)
        story.append(Spacer(1, 8 * mm))

    story.append(CondPageBreak(35 * mm))
    story.append(Spacer(1, 6 * mm))

    # ---- Per-image finding cards ----
    story.append(Paragraph("Fichas de hallazgos por imagen", styles["h1"]))
    story.append(Paragraph(
        "Cada ficha muestra la imagen con los hallazgos activos marcados, su ubicación cuando está disponible, la "
        "recomendación asociada a cada tipo de anomalía y, más abajo, la causa probable, la consecuencia de no "
        "corregirla y la maquinaria de apoyo sugerida.",
        styles["muted"],
    ))
    story.append(Spacer(1, 4 * mm))

    card_number = 0
    for image in images:
        image_detections = [d for d in by_image.get(image.id_imagen, []) if d.estado_revision != "rejected"]
        if not image_detections and image.criticidad_manual not in CRITICALITY_COLORS:
            continue
        card_number += 1

        annotated = _annotate_image(image, image_detections)
        photo_cell = Image(annotated, width=82 * mm, height=82 * mm * image.alto / image.ancho) if annotated else Paragraph("Imagen no disponible", styles["muted"])
        location_text = (
            f"{image.latitud:.5f}, {image.longitud:.5f}"
            if image.latitud is not None and image.longitud is not None
            else "Sin coordenadas EXIF"
        )
        photo_block = [
            photo_cell,
            Spacer(1, 2 * mm),
            Paragraph(f"<b>Ubicación:</b> {location_text}", styles["muted"]),
        ]
        if image.criticidad_manual in CRITICALITY_COLORS:
            crit_color = CRITICALITY_COLORS[image.criticidad_manual]
            photo_block.append(Spacer(1, 1.5 * mm))
            photo_block.append(Paragraph(
                f'<font color="#{crit_color.hexval()[2:]}">●</font> <b>Criticidad asignada: '
                f"{CRITICALITY_LABELS[image.criticidad_manual]}</b>",
                styles["muted"],
            ))

        finding_rows = []
        if not image_detections:
            finding_rows.append(
                Table(
                    [[Paragraph("Sin hallazgos activos en esta imagen.", styles["muted"])]],
                    colWidths=[70 * mm],
                )
            )
        for detection in image_detections:
            status_text, status_color = _status_badge(detection.estado_revision)
            finding_rows.append(
                Table(
                    [[
                        Paragraph(
                            f'<font color="{LABEL_COLORS.get(detection.clase, FALLBACK_COLOR)}">●</font> '
                            f"<b>{detection.clase}</b> — {detection.confianza:.0%}",
                            styles["card_title"],
                        ),
                    ], [
                        Paragraph(f'<font color="#{status_color.hexval()[2:]}"><b>{status_text}</b></font>', styles["muted"]),
                    ], [
                        Paragraph(RECOMMENDATIONS.get(detection.clase, DEFAULT_RECOMMENDATION), styles["body"]),
                    ]],
                    colWidths=[70 * mm],
                    style=TableStyle([
                        ("TOPPADDING", (0, 0), (-1, -1), 1),
                        ("BOTTOMPADDING", (0, 0), (-1, 0), 2),
                        ("BOTTOMPADDING", (0, 1), (-1, 1), 3),
                        ("BOTTOMPADDING", (0, 2), (-1, 2), 8),
                    ]),
                )
            )

        card_table = Table(
            [[photo_block, finding_rows]],
            colWidths=[86 * mm, 74 * mm],
        )
        card_table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("BOX", (0, 0), (-1, -1), 0.7, LINE),
            ("BACKGROUND", (0, 0), (0, 0), LIGHT),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ]))

        header = Table(
            [[Paragraph(f"Ficha {card_number} · {image.nombre_archivo}", ParagraphStyle("cardHeader", fontName="Helvetica-Bold", fontSize=9.5, textColor=colors.white))]],
            colWidths=[160 * mm],
        )
        header.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), BLACK),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ]))

        card_flow = [header, card_table]
        seen_labels = []
        for detection in image_detections:
            if detection.clase not in seen_labels:
                seen_labels.append(detection.clase)
        for label in seen_labels:
            if label == GOOD_CONDITION_LABEL:
                continue
            card_flow.append(Spacer(1, 2.5 * mm))
            card_flow.append(_diagnosis_block(label, styles))
        card_flow.append(Spacer(1, 6 * mm))

        story.append(KeepTogether(card_flow))

    if card_number == 0:
        story.append(Paragraph("No hay hallazgos activos (confirmados o pendientes) en esta misión.", styles["body"]))

    # ---- Discarded findings (audit trail) ----
    if discarded:
        story.append(CondPageBreak(70 * mm))
        story.append(Spacer(1, 6 * mm))
        story.append(Paragraph("Hallazgos descartados", styles["h1"]))
        story.append(Paragraph(
            "Detecciones del modelo marcadas como falso positivo durante la revisión. Se listan como registro de auditoría.",
            styles["muted"],
        ))
        story.append(Spacer(1, 3 * mm))
        image_names = {image.id_imagen: image.nombre_archivo for image in images}
        rows = [["Imagen", "Hallazgo", "Confianza"]]
        for d in discarded:
            rows.append([
                Paragraph(image_names.get(d.id_imagen, "—"), styles["body"]),
                Paragraph(d.clase, styles["body"]),
                f"{d.confianza:.0%}",
            ])
        discard_table = Table(rows, colWidths=[80 * mm, 54 * mm, 30 * mm], repeatRows=1)
        discard_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), BLACK),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("GRID", (0, 0), (-1, -1), 0.35, LINE),
            ("FONTSIZE", (0, 0), (-1, -1), 8.5),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT]),
        ]))
        story.append(discard_table)

    document.build(story, onFirstPage=_cover_decoration, onLaterPages=_content_decoration)
    return buffer.getvalue()
