"""
medir_ancho.py - NeumaVision
Mide el ancho de la pista a partir de la mascara del modelo de segmentacion (RF-DETR Seg)
y lo clasifica como semaforo: Optimo / Moderado / Critico.

Uso:
  export PYTORCH_ENABLE_MPS_FALLBACK=1
  python medir_ancho.py foto1.jpg foto2.jpg ...            # usa GSD del EXIF si existe
  python medir_ancho.py --gsd 1.0 carpeta/*.jpg             # fuerza GSD en cm/px

Salida: ~/Desktop/resultados_ancho/<foto>_ancho.jpg  +  anchos.csv
"""
import argparse, csv, glob, os, random, sys
import cv2
import numpy as np
from PIL import Image
from skimage.morphology import skeletonize

# ---------------- Parametros del proyecto ----------------
ANCHO_CAMION_M = 7.3            # Komatsu 830E
F_OPTIMO = 3.5                  # >= 3.5 W  -> Optimo (doble sentido, recta)
F_CRITICO = 3.0                 # <  3.0 W  -> Critico
SENSOR_35MM_ANCHO = 36.0        # mm, para usar focal equivalente 35 mm

# Clases del modelo de segmentacion de pista (RF-DETR Seg entrenado en Roboflow)
CLASES_PISTA = {1: "Carpeta buen estado", 2: "Carpeta pedregosa"}
COLOR_CLASE_PISTA = {1: (43, 184, 168), 2: (158, 130, 255)}   # RGB

VERDE, AMARILLO, ROJO, GRIS = (60, 200, 60), (0, 200, 255), (40, 40, 230), (160, 160, 160)


def clasificar(ancho_m):
    if ancho_m is None:
        return "Sin medición", GRIS
    if ancho_m >= F_OPTIMO * ANCHO_CAMION_M:
        return "Óptimo", VERDE
    if ancho_m >= F_CRITICO * ANCHO_CAMION_M:
        return "Moderado", AMARILLO
    return "Crítico", ROJO


def gsd_desde_exif(ruta, ancho_px):
    """GSD en cm/px desde EXIF/XMP de DJI (altura relativa + focal equivalente 35 mm)."""
    try:
        raw = open(ruta, "rb").read()
        i = raw.find(b'drone-dji:RelativeAltitude="')
        if i < 0:
            return None
        alt = abs(float(raw[i + 28:raw.find(b'"', i + 28)]))
        f35 = Image.open(ruta).getexif().get_ifd(0x8769).get(0xA405)  # FocalLengthIn35mmFilm
        if not f35 or alt <= 0:
            return None
        return alt * SENSOR_35MM_ANCHO / (float(f35) * ancho_px) * 100
    except Exception:
        return None


def mascara_pista(modelo, img_rgb, umbral):
    return mascara_pista_conf(modelo, img_rgb, umbral)[0]


def nombre_clase_pista(clase):
    return CLASES_PISTA.get(int(clase), f"Clase {int(clase)}") if clase is not None else "Pista"


def mascara_pista_conf(modelo, img_rgb, umbral):
    """Igual que mascara_pista, pero devuelve tambien la confianza (0-1) y la clase de la
    mascara elegida (la de mayor confianza entre las dos etiquetas del modelo).

    Toma la mejor mascara de pista: la de mayor confianza (>= umbral) que cubra
    entre 10 % y 85 % de la imagen (descarta mascaras de toda la foto o astillas)."""
    det = modelo.predict(Image.fromarray(img_rgb), threshold=umbral)
    h, w = img_rgb.shape[:2]
    if det.mask is None or len(det) == 0:
        return np.zeros((h, w), np.uint8), None, None
    for k in np.argsort(-det.confidence):
        mk = det.mask[k].astype(np.uint8)
        if mk.shape != (h, w):
            mk = cv2.resize(mk, (w, h), interpolation=cv2.INTER_NEAREST)
        if 0.10 < mk.mean() < 0.85:
            return mk, float(det.confidence[k]), int(det.class_id[k])
    return np.zeros((h, w), np.uint8), None, None


def limpiar(m):
    h, w = m.shape
    k = max(5, int(min(h, w) * 0.01)) | 1
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k)))
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k)))
    n, lab, st, _ = cv2.connectedComponentsWithStats(m)
    out = np.zeros_like(m)
    for i in range(1, n):  # componentes grandes (>3 % de la imagen)
        if st[i, cv2.CC_STAT_AREA] > 0.03 * h * w:
            out[lab == i] = 1
    # rellenar huecos (rocas o manchas dentro de la pista)
    inv = (1 - out).astype(np.uint8)
    n, lab, st, _ = cv2.connectedComponentsWithStats(inv)
    for i in range(1, n):
        x, y, ww, hh, a = st[i]
        toca_borde = x == 0 or y == 0 or x + ww >= w or y + hh >= h
        if not toca_borde and a < 0.02 * h * w:
            out[lab == i] = 1
    # suavizar bordes para un eje central sin ramas espurias
    s = cv2.GaussianBlur(out.astype(np.float32), (0, 0), sigmaX=min(h, w) * 0.01)
    return (s > 0.5).astype(np.uint8)


def eje_principal(sk):
    """Del esqueleto deja solo el camino mas largo (elimina ramas laterales espurias).
    Devuelve los pixeles ordenados a lo largo del eje."""
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import dijkstra, connected_components
    ys, xs = np.nonzero(sk)
    n = len(ys)
    if n < 2:
        return ys, xs
    idx = -np.ones(sk.shape, np.int64)
    idx[ys, xs] = np.arange(n)
    f, t, wgt = [], [], []
    for dy, dx in [(0, 1), (1, -1), (1, 0), (1, 1)]:
        y2, x2 = ys + dy, xs + dx
        ok = (y2 >= 0) & (y2 < sk.shape[0]) & (x2 >= 0) & (x2 < sk.shape[1])
        j = np.full(n, -1); j[ok] = idx[y2[ok], x2[ok]]
        ok = j >= 0
        f.append(np.arange(n)[ok]); t.append(j[ok]); wgt.append(np.full(ok.sum(), np.hypot(dy, dx)))
    f, t, wgt = map(np.concatenate, (f, t, wgt))
    G = coo_matrix((wgt, (f, t)), shape=(n, n)).tocsr()
    # componente mas grande
    _, lab = connected_components(G, directed=False)
    comp = np.argmax(np.bincount(lab))
    a = np.nonzero(lab == comp)[0][0]
    d = dijkstra(G, directed=False, indices=a)
    d[~np.isfinite(d)] = -1
    A = int(np.argmax(d))
    d, pred = dijkstra(G, directed=False, indices=A, return_predecessors=True)
    d[~np.isfinite(d)] = -1
    B = int(np.argmax(d))
    camino = [B]
    while camino[-1] != A and pred[camino[-1]] >= 0:
        camino.append(pred[camino[-1]])
    camino = np.array(camino[::-1])
    return ys[camino], xs[camino]


def medir(m, escala_px=1):
    """Eje central ordenado, radio (px), validez y normal de cada punto.
    La mascara se extiende fuera de la foto (relleno replicado) para que el eje
    llegue hasta los bordes cuando la pista sale del encuadre."""
    h, w = m.shape
    pad = max(h, w) // 2
    mp = cv2.copyMakeBorder(m, pad, pad, pad, pad, cv2.BORDER_REPLICATE)
    dt = cv2.distanceTransform(mp, cv2.DIST_L2, 5)
    ys, xs = eje_principal(skeletonize(mp.astype(bool)))
    r = dt[ys, xs].astype(float)
    ys, xs = ys - pad, xs - pad
    N = len(ys)
    if N < 3:
        z = np.zeros(0)
        return z.astype(int), z.astype(int), z, z.astype(bool), np.zeros((0, 2))
    # direccion local del eje (diferencia entre puntos +-k a lo largo del camino)
    k = np.clip((1.2 * r).astype(int), max(1, 20 // escala_px), None)  # ventana amplia: direccion estable
    i = np.arange(N)
    a, b = np.clip(i - k, 0, N - 1), np.clip(i + k, 0, N - 1)
    d = np.stack([xs[b] - xs[a], ys[b] - ys[a]], 1).astype(float)
    d /= np.linalg.norm(d, axis=1, keepdims=True) + 1e-9
    nor = np.stack([-d[:, 1], d[:, 0]], 1)
    dentro = (ys >= 0) & (ys < h) & (xs >= 0) & (xs < w)
    valido = dentro.copy()
    for sgn in (1, -1):  # el ancho debe cerrarse dentro de la foto
        px = xs + sgn * nor[:, 0] * r * 1.05
        py = ys + sgn * nor[:, 1] * r * 1.05
        valido &= (px >= 0) & (px < w) & (py >= 0) & (py < h)
    if valido.any():  # descartar ensanches/puntas
        med = np.median(r[valido])
        valido &= (r > 0.6 * med) & (r < 1.6 * med)
    sel = dentro
    return ys[sel], xs[sel], r[sel], valido[sel], nor[sel]


# ---------------- Dibujo (panel y etiquetas) ----------------
_FUENTES = {
    False: ["/System/Library/Fonts/Supplemental/Arial.ttf", "/System/Library/Fonts/Helvetica.ttc",
            "/usr/share/fonts/opentype/inter/Inter-Regular.otf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"],
    True: ["/System/Library/Fonts/Supplemental/Arial Bold.ttf", "/System/Library/Fonts/Helvetica.ttc",
           "/usr/share/fonts/opentype/inter/Inter-Bold.otf",
           "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"],
}


def fuente(tam, negrita=False):
    from PIL import ImageFont
    for f in _FUENTES[negrita]:
        if os.path.exists(f):
            try:
                return ImageFont.truetype(f, int(tam))
            except Exception:
                pass
    return ImageFont.load_default()


def rgb(c):  # BGR (OpenCV) -> RGB (PIL)
    return (c[2], c[1], c[0])


def dibujar_panel(vis_bgr, estado, col, p10, med, gsd, fuente_gsd, pct, etiquetas, pista=None):
    from PIL import ImageDraw
    h, w = vis_bgr.shape[:2]
    u = w / 1536                                   # unidad de escala
    base = Image.fromarray(cv2.cvtColor(vis_bgr, cv2.COLOR_BGR2RGB)).convert("RGBA")
    capa = Image.new("RGBA", base.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(capa)

    # etiqueta de la segmentacion: "Pista · 64 %" arriba del camino (como la de las rocas)
    if pista is not None:
        conf_p, clase_p, (lx, ly) = pista
        txt_p = f"{nombre_clase_pista(clase_p)} · {conf_p:.0%}"
        f_p = fuente(17 * u, True)
        tw = d.textlength(txt_p, font=f_p)
        bx0 = min(max(int(lx - tw / 2 - 12 * u), 4), int(w - tw - 28 * u))
        by0 = min(max(int(ly), 4), int(h - 36 * u))
        d.rounded_rectangle([bx0, by0, bx0 + tw + 24 * u, by0 + 32 * u], radius=int(8 * u),
                            fill=COLOR_CLASE_PISTA.get(clase_p, (0, 120, 255)) + (235,))
        d.text((bx0 + 12 * u, by0 + 6 * u), txt_p, font=f_p, fill=(255, 255, 255, 255))

    # etiquetas de ancho: pastillas blancas con borde del color del tramo
    f_et = fuente(15 * u, True)
    for txt, (x, y), c in etiquetas:
        tw = d.textlength(txt, font=f_et)
        x0, y0 = int(x + 8 * u), int(y - 26 * u)
        x0 = min(max(x0, 4), int(w - tw - 22 * u))
        y0 = min(max(y0, 4), int(h - 28 * u))
        d.rounded_rectangle([x0, y0, x0 + tw + 16 * u, y0 + 24 * u], radius=int(12 * u),
                            fill=(255, 255, 255, 230), outline=rgb(c) + (255,), width=max(1, int(2 * u)))
        d.text((x0 + 8 * u, y0 + 3.5 * u), txt, font=f_et, fill=(40, 40, 40, 255))

    uc = u * 0.72                                  # escala de la tarjeta (mas compacta)
    # tarjeta resumen (blanca, semitransparente, esquinas redondeadas) abajo a la izquierda
    W, H = 360 * uc, 214 * uc
    x0, y0 = 24 * uc, h - H - 24 * uc
    d.rounded_rectangle([x0 + 4 * uc, y0 + 6 * uc, x0 + W + 4 * uc, y0 + H + 6 * uc], radius=int(18 * uc),
                        fill=(0, 0, 0, 60))                                   # sombra
    d.rounded_rectangle([x0, y0, x0 + W, y0 + H], radius=int(18 * uc), fill=(255, 255, 255, 235))
    px = x0 + 20 * uc
    d.text((px, y0 + 16 * uc), "ANCHO DE PISTA", font=fuente(13 * uc, True), fill=(120, 120, 120, 255))
    # pastilla de estado
    f_est = fuente(15 * uc, True)
    tw = d.textlength(estado.upper(), font=f_est)
    d.rounded_rectangle([x0 + W - tw - 46 * uc, y0 + 12 * uc, x0 + W - 16 * uc, y0 + 38 * uc],
                        radius=int(13 * uc), fill=rgb(col) + (255,))
    d.ellipse([x0 + W - tw - 38 * uc, y0 + 21 * uc, x0 + W - tw - 30 * uc, y0 + 29 * uc], fill=(255, 255, 255, 255))
    d.text((x0 + W - tw - 24 * uc, y0 + 16 * uc), estado.upper(), font=f_est, fill=(255, 255, 255, 255))
    # cifra principal
    num = f"{p10:.1f} m".replace(".", ",") if p10 else "—"
    d.text((px, y0 + 46 * uc), num, font=fuente(44 * uc, True), fill=(30, 30, 30, 255))
    d.text((px, y0 + 98 * uc), "ancho mínimo del tramo", font=fuente(14 * uc), fill=(110, 110, 110, 255))
    # barra de semaforo con umbrales
    by = y0 + 128 * uc
    lim_c, lim_o = F_CRITICO * ANCHO_CAMION_M, F_OPTIMO * ANCHO_CAMION_M
    bw = W - 40 * uc
    tramos = [(ROJO, 0.0, 0.40), (AMARILLO, 0.40, 0.65), (VERDE, 0.65, 1.0)]
    for c, a0, a1 in tramos:
        d.rectangle([px + a0 * bw, by, px + a1 * bw, by + 8 * uc], fill=rgb(c) + (255,))
    f_s = fuente(12 * uc)
    d.text((px + 0.40 * bw - 18 * uc, by + 12 * uc), f"{lim_c:.1f}".replace(".", ","), font=f_s, fill=(110, 110, 110, 255))
    d.text((px + 0.65 * bw - 18 * uc, by + 12 * uc), f"{lim_o:.1f}".replace(".", ","), font=f_s, fill=(110, 110, 110, 255))
    if p10:  # marcador de posicion
        def pos(v):
            if v < lim_c: return 0.40 * min(v / lim_c, 1)
            if v < lim_o: return 0.40 + 0.25 * (v - lim_c) / (lim_o - lim_c)
            return min(0.65 + 0.35 * (v - lim_o) / (lim_o * 0.4), 1.0)
        mx = px + pos(p10) * bw
        d.polygon([(mx - 7 * uc, by - 10 * uc), (mx + 7 * uc, by - 10 * uc), (mx, by - 1 * uc)], fill=(30, 30, 30, 255))
    # detalle
    f_d = fuente(13 * uc)
    med_t = f"{med:.1f} m".replace(".", ",") if med else "—"
    gsd_t = f"{gsd:.2f} cm/px ({fuente_gsd})".replace(".", ",") if gsd else "desconocido"
    d.text((px, y0 + 166 * uc), f"Mediano: {med_t}   ·   Eje medido: {pct:.0f} %", font=f_d, fill=(70, 70, 70, 255))
    d.text((px, y0 + 186 * uc), f"GSD: {gsd_t}   ·   Komatsu 830E", font=f_d, fill=(70, 70, 70, 255))

    out = Image.alpha_composite(base, capa).convert("RGB")
    return cv2.cvtColor(np.array(out), cv2.COLOR_RGB2BGR)


def procesar(modelo, ruta, gsd_forzado, umbral, salida, separacion_m=1.0):
    bgr = cv2.imread(ruta)
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    h, w = rgb.shape[:2]
    gsd = gsd_forzado or gsd_desde_exif(ruta, w)
    fuente = "forzado" if gsd_forzado else ("EXIF" if gsd else "sin GSD")

    m_raw, conf_p, clase_p = mascara_pista_conf(modelo, rgb, umbral)
    m = limpiar(m_raw)
    vis, res = analizar(bgr, m, gsd, fuente, separacion_m, conf_pista=conf_p, clase_pista=clase_p)
    base = os.path.splitext(os.path.basename(ruta))[0][:60]
    cv2.imwrite(os.path.join(salida, base + "_ancho.jpg"), vis, [cv2.IMWRITE_JPEG_QUALITY, 85])
    return dict(foto=os.path.basename(ruta), **res)


def analizar_archivo(ruta, bgr, mascara, gsd_configurado, conf_pista=None, clase_pista=None, *, media_resolucion=False):
    gsd_exif = gsd_desde_exif(str(ruta), bgr.shape[1])
    fuente = "EXIF" if gsd_exif else ("configurado" if gsd_configurado else "sin GSD")
    gsd = gsd_exif or gsd_configurado
    args = (bgr, mascara, gsd, fuente)
    datos_pista = {"conf_pista": conf_pista, "clase_pista": clase_pista}
    overlay, resumen = analizar(*args, **datos_pista, media_resolucion=media_resolucion)
    if media_resolucion and gsd:
        p10 = resumen["ancho_min_p10_m"]
        umbrales = (F_CRITICO * ANCHO_CAMION_M, F_OPTIMO * ANCHO_CAMION_M)
        if p10 == "" or any(abs(p10 - umbral) <= umbral * 0.05 for umbral in umbrales):
            return analizar(*args, **datos_pista)
    return overlay, resumen


def analizar(bgr, m, gsd, fuente, separacion_m=1.0, conf_pista=None, clase_pista=None, *, media_resolucion=False):
    """Mide el ancho sobre una mascara de pista ya limpia. Devuelve (imagen anotada, resumen)."""
    h, w = bgr.shape[:2]
    escala_px = 2 if media_resolucion and min(h, w) >= 2 else 1
    mascara_medicion = m
    if escala_px == 2:
        # Completa las dimensiones impares para que cada píxel reducido represente 2 × 2.
        mascara_par = cv2.copyMakeBorder(m, 0, h % 2, 0, w % 2, cv2.BORDER_REPLICATE)
        mascara_medicion = (cv2.resize(mascara_par.astype(np.float32), ((w + 1) // 2, (h + 1) // 2),
                                       interpolation=cv2.INTER_AREA) >= 0.5).astype(np.uint8)
    ys, xs, r, val, nor = medir(mascara_medicion, escala_px)
    # Proyecta los centros y radios al sistema original, que conserva su GSD.
    if escala_px == 2:
        ys, xs = ys * 2 + 0.5, xs * 2 + 0.5
        r *= 2
        val &= (ys < h) & (xs < w)

    vis = bgr.copy()
    capa = vis.copy()
    capa[m == 1] = (255, 140, 0)
    vis = cv2.addWeighted(capa, 0.25, vis, 0.75, 0)
    cnts, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cv2.drawContours(vis, cnts, -1, (255, 140, 0), 4)

    anchos_m = (2 * r * gsd / 100) if gsd else None
    colores = [GRIS if (not val[i] or anchos_m is None) else clasificar(anchos_m[i])[1] for i in range(len(ys))]

    # eje central (linea fina, coloreada por tramo)
    g_eje = max(4, w // 500)
    for i in range(1, len(ys)):
        if abs(int(xs[i]) - int(xs[i-1])) <= 2 * escala_px and abs(int(ys[i]) - int(ys[i-1])) <= 2 * escala_px:
            cv2.line(vis, (int(xs[i-1]), int(ys[i-1])), (int(xs[i]), int(ys[i])), colores[i], g_eje)

    etiquetas = []
    # lineas transversales cada `separacion_m` a lo largo del eje (de borde a borde)
    if len(ys) > 1:
        sep_px = (separacion_m * 100 / gsd) if gsd else 100
        paso = np.hypot(np.diff(xs), np.diff(ys))
        s_arc = np.concatenate([[0], np.cumsum(paso)])
        # radio suavizado a lo largo del eje para que las lineas no "salten"
        k = 15 // escala_px
        r_suave = np.array([np.median(r[max(0, i-k):i+k+1]) for i in range(len(r))])
        g_tr = max(4, w // 450)
        n_linea = 0
        etiquetas = []
        for objetivo in np.arange(sep_px / 2, s_arc[-1], sep_px):
            i = int(np.searchsorted(s_arc, objetivo))
            i = min(i, len(ys) - 1)
            if not val[i]:
                continue
            c = np.array([xs[i], ys[i]], float)
            p1 = (c + nor[i] * r_suave[i]).astype(int)
            p2 = (c - nor[i] * r_suave[i]).astype(int)
            cv2.line(vis, tuple(p1), tuple(p2), colores[i], g_tr, cv2.LINE_AA)
            if anchos_m is not None and n_linea % 4 == 0:   # etiqueta cada 4 lineas
                etiquetas.append((f"{2 * r_suave[i] * gsd / 100:.1f} m".replace(".", ","), tuple(p1), colores[i]))
            n_linea += 1

    # resumen: el ancho que manda es el minimo robusto (percentil 10)
    pct_val = 100 * val.mean() if len(val) else 0
    if anchos_m is not None and val.any() and pct_val >= 30:  # muy poco eje medible = no confiable
        p10, med = np.percentile(anchos_m[val], 10), np.median(anchos_m[val])
        estado, col = clasificar(p10)
    else:
        p10 = med = None
        estado, col = ("Sin medición", GRIS)

    pista = None
    if conf_pista is not None and m.any():
        filas = np.nonzero(m.any(axis=1))[0]
        y_top = int(filas[0])
        banda = m[y_top:y_top + max(1, h // 20)]
        x_c = float(np.nonzero(banda)[1].mean())
        pista = (conf_pista, clase_pista, (x_c, y_top + h * 0.06))
    vis = dibujar_panel(vis, estado, col, p10, med, gsd, fuente, pct_val, etiquetas, pista)

    return vis, dict(estado=estado,
                     ancho_min_p10_m=round(float(p10), 2) if p10 else "",
                     ancho_mediano_m=round(float(med), 2) if med else "",
                     gsd_cm_px=round(float(gsd), 3) if gsd else "", fuente_gsd=fuente,
                     eje_medible_pct=round(float(pct_val), 1),
                     confianza_pista=round(float(conf_pista), 3) if conf_pista is not None else "",
                     clase_pista=nombre_clase_pista(clase_pista) if conf_pista is not None else "")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("imagenes", nargs="*")
    ap.add_argument("--pesos", default=os.path.expanduser("~/Downloads/weights.pt"))
    ap.add_argument("--gsd", type=float, default=None, help="cm/px; si no se da, se lee del EXIF")
    ap.add_argument("--umbral", type=float, default=0.2)
    ap.add_argument("--separacion", type=float, default=1.0, help="metros entre lineas transversales")
    ap.add_argument("--n", type=int, default=5, help="fotos al azar si no se pasan rutas")
    ap.add_argument("--salida", default=os.path.expanduser("~/Desktop/resultados_ancho"))
    a = ap.parse_args()

    imgs = a.imagenes
    if not imgs:
        todas = glob.glob(os.path.expanduser("~/Desktop/Dataset NeumaVision/*/images/*.jpg"))
        imgs = random.sample(todas, min(a.n, len(todas)))
    os.makedirs(a.salida, exist_ok=True)

    from rfdetr import RFDETRSegMedium
    modelo = RFDETRSegMedium(pretrain_weights=a.pesos)

    filas = []
    for p in imgs:
        f = procesar(modelo, p, a.gsd, a.umbral, a.salida, a.separacion)
        print(f"{f['estado']:13s} p10={f['ancho_min_p10_m']} m  med={f['ancho_mediano_m']} m  "
              f"eje={f['eje_medible_pct']}%  {f['foto'][:50]}")
        filas.append(f)
    with open(os.path.join(a.salida, "anchos.csv"), "w", newline="") as fh:
        wr = csv.DictWriter(fh, fieldnames=list(filas[0].keys()))
        wr.writeheader(); wr.writerows(filas)
    print("Resultados en", a.salida)


if __name__ == "__main__":
    main()
