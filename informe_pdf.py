# =====================================================================
# informe_pdf.py: informe en PDF (1 a 2 páginas, tamaño carta) para llevar a la consulta.
# Solo consume resultados que ya calculó app.py (no toca modelo.py ni ningún cálculo)
# y no depende de Streamlit. Todo es vectorial (reportlab), se arma en memoria
# (io.BytesIO) y no se escribe nada en disco ni en el servidor.
#
# Fuentes: Inter (Regular, SemiBold, Bold) desde ./fonts (licencia OFL). Si faltan,
# usa Helvetica sin que la app falle; por eso íconos, flechas y checks se dibujan
# como formas vectoriales y no como caracteres.
# =====================================================================
import io
import math
import os
from datetime import date

from reportlab.graphics.shapes import Circle, Drawing, Group, Line, Path, Polygon, PolyLine, Rect, String
from reportlab.lib.colors import Color, HexColor, white
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.pdfmetrics import registerFontFamily, stringWidth
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas as pdfcanvas
from reportlab.platypus import (BaseDocTemplate, Flowable, Frame, KeepTogether, NextPageTemplate,
                                PageTemplate, Paragraph, Spacer, Table, TableStyle)

# ----------------------------------------------------------- contenido editable
# Tres especialidades/servicios del recorrido (edítalas aquí). Solo informativas: sin tratamientos
# ni medicamentos.
ESPECIALIDADES = [
    ("Medicina general", "Primer contacto en tu EPS; puede remitirte a una especialidad."),
    ("Ginecología", "Revisa ciclos, ovarios y salud reproductiva."),
    ("Endocrinología", "Revisa las hormonas y cómo el cuerpo usa la insulina."),
]

QUE_LLEVAR = [
    "Las fechas de tus últimos ciclos.",
    "Tu peso aproximado y si ha cambiado.",
    "Notas o fotos de los síntomas que te preocupan.",
    "Ecografías o exámenes anteriores.",
    "Los medicamentos que tomas.",
]

PREGUNTAS_CONSULTA = [
    "¿Qué exámenes me recomiendan para entender mejor lo que me pasa?",
    "¿Cada cuánto debería hacerme controles?",
    "¿Qué señales conviene que anote entre una consulta y otra?",
    "¿Hace falta que consulte también con otra especialidad?",
]

AVISO_ETICO = ("Esta herramienta no es un diagnóstico médico y no reemplaza la valoración de un "
               "profesional de la salud. Tus respuestas no se guardan.")
NOTA_POBLACION = ("Modelo entrenado con datos de 541 mujeres de Kerala, India. No ha sido validado en "
                  "población colombiana.")
MICROTEXTO = ("Este porcentaje es una estimación del modelo con datos de otro país; no es la "
              "probabilidad real de que tengas SOP.")

# ----------------------------------------------------------- paleta
PIZARRA = HexColor("#2D3748")
PIZARRA_2 = HexColor("#4A5568")
SALVIA = HexColor("#4A7C7D")
SALVIA_CLARO = HexColor("#8DB3A9")
SALVIA_TINTE = HexColor("#E3EEEC")
MALVA = HexColor("#9C7A97")
MALVA_OSCURO = HexColor("#7E5F7A")
BORDE = HexColor("#D5E3E1")
FONDO = HexColor("#FAFAFA")
FONDO_2 = HexColor("#EEF4F3")
MELOCOTON = HexColor("#F4A261")

# nivel -> (fondo, borde, ícono, índice 0-4)
CATEGORIAS_PDF = {
    "Bajo": ("#E3EEEC", "#4A7C7D", "hoja"),
    "Medio-bajo": ("#EAF2EF", "#8DB3A9", "hoja"),
    "Medio": ("#F7EFD3", "#E9D8A6", "punto"),
    "Medio-alto": ("#FFF1E3", "#F4A261", "triangulo"),
    "Alto": ("#FBEDE7", "#C8694A", "atencion"),
}
NOMBRES_NIVEL = ["Bajo", "Medio-bajo", "Medio", "Medio-alto", "Alto"]
COLORES_ESCALA = ["#4A7C7D", "#8DB3A9", "#E9D8A6", "#F4A261", "#C8694A"]

# ----------------------------------------------------------- fuentes
DIR_FUENTES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")


def _registrar_fuentes():
    """(regular, semibold, bold). Inter si existen los TTF; si no, Helvetica."""
    try:
        for nombre, archivo in (("Inter", "Inter-Regular.ttf"), ("Inter-SemiBold", "Inter-SemiBold.ttf"),
                                ("Inter-Bold", "Inter-Bold.ttf")):
            pdfmetrics.registerFont(TTFont(nombre, os.path.join(DIR_FUENTES, archivo)))
        registerFontFamily("Inter", normal="Inter", bold="Inter-Bold", italic="Inter", boldItalic="Inter-Bold")
        return "Inter", "Inter-SemiBold", "Inter-Bold"
    except Exception:
        return "Helvetica", "Helvetica-Bold", "Helvetica-Bold"


# ----------------------------------------------------------- íconos vectoriales (caja de 24 unidades)
def _trazo(shape, color, grosor=1.7):
    shape.strokeColor = color
    shape.strokeWidth = grosor
    shape.strokeLineCap = 1
    if hasattr(shape, "strokeLineJoin"):
        shape.strokeLineJoin = 1
    if not isinstance(shape, (Line, PolyLine)):
        shape.fillColor = None
    return shape


def _curva(inicio, *tramos):
    p = Path()
    p.moveTo(*inicio)
    for t in tramos:
        if len(t) == 2:
            p.lineTo(*t)
        else:
            p.curveTo(*t)
    return p


def icono(nombre, x, y, tam, color, grosor=1.7):
    """Grupo con el ícono dibujado en (x, y) (esquina inferior izquierda) con lado `tam` en pt."""
    g = []
    if nombre == "hoja":
        p = _curva((5, 5), (5, 13, 10, 18, 19, 19), (19, 10, 14, 5, 6, 5))
        g += [_trazo(p, color, grosor), _trazo(Line(5, 5, 13, 13), color, grosor)]
    elif nombre == "brote":
        g += [_trazo(Line(12, 3, 12, 11), color, grosor)]
        g += [_trazo(_curva((12, 11), (12, 14.6, 9.4, 16.6, 5.5, 16.6), (5.5, 13, 8.1, 11, 12, 11)), color, grosor)]
        g += [_trazo(_curva((12, 13), (12, 16.2, 14.3, 18.2, 17.8, 18.2), (17.8, 15, 15.5, 13, 12, 13)), color, grosor)]
    elif nombre == "punto":
        g += [_trazo(Circle(12, 12, 9), color, grosor), _trazo(Circle(12, 12, 2.5), color, grosor)]
    elif nombre == "triangulo":
        t = PolyLine([12, 20, 3, 4.5, 21, 4.5, 12, 20])
        g += [_trazo(t, color, grosor), _trazo(Line(12, 14, 12, 9.5), color, grosor)]
        c = Circle(12, 7, 1.1); c.fillColor = color; c.strokeColor = None
        g.append(c)
    elif nombre == "atencion":
        g += [_trazo(Circle(12, 12, 9), color, grosor), _trazo(Line(12, 16.5, 12, 11.5), color, grosor)]
        c = Circle(12, 8, 1.1); c.fillColor = color; c.strokeColor = None
        g.append(c)
    elif nombre == "escudo":
        p = _curva((12, 21), (20, 18), (20, 12), (20, 7.5, 16.8, 4, 12, 3), (7.2, 4, 4, 7.5, 4, 12), (4, 18), (12, 21))
        g.append(_trazo(p, color, grosor))
    elif nombre == "check":
        g.append(_trazo(PolyLine([5, 11.5, 9.5, 7, 19, 17]), color, grosor))
    elif nombre == "guion":
        g.append(_trazo(Line(6, 12, 18, 12), color, grosor))
    s = tam / 24.0
    return Group(*g, transform=(s, 0, 0, s, x, y))


def _mezcla(c1, c2, t):
    return Color(c1.red + (c2.red - c1.red) * t, c1.green + (c2.green - c1.green) * t,
                 c1.blue + (c2.blue - c1.blue) * t)


# ----------------------------------------------------------- gráficos (Drawing)
def dibujo_dona(pct, fuentes, lado=48 * mm):
    """Dona vectorial: pista, arco salvia->malva (franjas cortas de color interpolado) y % al centro."""
    _, f_sb, f_b = fuentes
    d = Drawing(lado, lado)
    c = lado / 2
    grosor = lado * 0.105
    r = lado / 2 - grosor / 2 - 2
    pista = Circle(c, c, r)
    pista.fillColor = None; pista.strokeColor = BORDE; pista.strokeWidth = grosor
    d.add(pista)
    total = 360.0 * max(0, min(100, pct)) / 100
    if total > 0:
        pasos = max(1, int(math.ceil(total / 3)))
        for i in range(pasos):
            a0 = 90 - total * i / pasos
            a1 = 90 - total * (i + 1) / pasos
            x0, y0 = c + r * math.cos(math.radians(a0)), c + r * math.sin(math.radians(a0))
            x1, y1 = c + r * math.cos(math.radians(a1)), c + r * math.sin(math.radians(a1))
            seg = Line(x0, y0, x1, y1)
            seg.strokeColor = _mezcla(SALVIA, MALVA, (i + 0.5) / pasos)
            seg.strokeWidth = grosor
            seg.strokeLineCap = 1
            d.add(seg)
    t = String(c, c - 10, f"{pct}%", fontName=f_b, fontSize=30, textAnchor="middle")
    t.fillColor = PIZARRA
    d.add(t)
    return d


def dibujo_pastilla(nombre, nivel, fuentes, ancho=70 * mm):
    f_reg, f_sb, _ = fuentes
    fondo, borde, ico = CATEGORIAS_PDF[nombre]
    alto = 24
    d = Drawing(ancho, alto)
    caja = Rect(1, 1, ancho - 2, alto - 2, rx=alto / 2, ry=alto / 2)
    caja.fillColor = HexColor(fondo); caja.strokeColor = HexColor(borde); caja.strokeWidth = 1.6
    d.add(caja)
    d.add(icono(ico, 9, 4, 16, PIZARRA, 1.8))
    t = String(30, 8, f"Nivel {nombre}", fontName=f_sb, fontSize=11.5)
    t.fillColor = PIZARRA
    d.add(t)
    ancho_t = stringWidth(f"Nivel {nombre}", f_sb, 11.5)
    x0 = 30 + ancho_t + 12
    for i in range(5):
        p = Circle(x0 + i * 10, alto / 2, 3.2)
        p.strokeColor = MALVA_OSCURO; p.strokeWidth = 1.2
        p.fillColor = MALVA_OSCURO if i < CATEGORIAS_NIVEL(nombre) else white
        d.add(p)
    return d


def CATEGORIAS_NIVEL(nombre):
    return NOMBRES_NIVEL.index(nombre) + 1


def dibujo_escala(nombre, fuentes, ancho=100 * mm):
    f_reg, f_sb, _ = fuentes
    idx = NOMBRES_NIVEL.index(nombre)
    alto = 46
    d = Drawing(ancho, alto)
    gap = 4
    w = (ancho - 4 * gap) / 5
    yc = alto - 15
    for i, col in enumerate(COLORES_ESCALA):
        if i == idx:
            continue
        r = Rect(i * (w + gap), yc - 5, w, 10, rx=5, ry=5)
        r.fillColor = HexColor(col); r.strokeColor = None
        d.add(r)
    # segmento actual: más grande y con borde blanco (más un trazo fino en pizarra para el blanco y negro)
    x = idx * (w + gap)
    halo = Rect(x - 2.5, yc - 10.5, w + 5, 21, rx=10.5, ry=10.5)
    halo.fillColor = white; halo.strokeColor = PIZARRA; halo.strokeWidth = 0.6
    d.add(halo)
    act = Rect(x - 1, yc - 8, w + 2, 16, rx=8, ry=8)
    act.fillColor = HexColor(COLORES_ESCALA[idx]); act.strokeColor = None
    d.add(act)
    # marcador y nombre bajo el segmento actual
    cx = x + w / 2
    tri = Polygon([cx - 4, yc - 14, cx + 4, yc - 14, cx, yc - 20])
    tri.fillColor = PIZARRA; tri.strokeColor = None
    d.add(tri)
    t = String(cx, yc - 31, nombre, fontName=f_sb, fontSize=9.5, textAnchor="middle")
    t.fillColor = PIZARRA
    d.add(t)
    if idx != 0:
        a = String(0, yc - 31, "Bajo", fontName=f_reg, fontSize=9.5)
        a.fillColor = PIZARRA_2
        d.add(a)
    if idx != 4:
        b = String(ancho, yc - 31, "Alto", fontName=f_reg, fontSize=9.5, textAnchor="end")
        b.fillColor = PIZARRA_2
        d.add(b)
    return d


def _puntos_txt(valor):
    n = max(1, int(round(abs(valor))))
    return "1 punto" if n == 1 else f"{n} puntos"


def dibujo_factores(items, fuentes, ancho):
    """Barras horizontales: una por factor, con su valor escrito (no depende del color)."""
    f_reg, f_sb, _ = fuentes
    fila, alto_barra = 22, 10
    max_abs = max(abs(i["puntos"]) for i in items)
    tope = max(10, int(math.ceil(max_abs / 5.0)) * 5)
    paso = 5 if tope <= 20 else (10 if tope <= 60 else 20)
    x0, x1 = 128, ancho - 92
    alto = fila * len(items) + 30
    d = Drawing(ancho, alto)
    zona_sup = alto - 6
    zona_inf = 22
    for v in range(0, tope + 1, paso):
        x = x0 + (x1 - x0) * v / tope
        g = Line(x, zona_inf - 4, x, zona_sup)
        g.strokeColor = BORDE; g.strokeWidth = 0.6
        d.add(g)
        t = String(x, 6, str(v), fontName=f_reg, fontSize=9, textAnchor="middle")
        t.fillColor = PIZARRA_2
        d.add(t)
    t = String(x1 + 8, 6, "puntos", fontName=f_reg, fontSize=9)
    t.fillColor = PIZARRA_2
    d.add(t)
    eje = Line(x0, zona_inf - 4, x0, zona_sup)
    eje.strokeColor = PIZARRA; eje.strokeWidth = 1
    d.add(eje)
    for k, it in enumerate(items):
        y = zona_sup - fila * (k + 1) + (fila - alto_barra) / 2
        sube = it["puntos"] >= 0
        etiqueta = String(0, y + 1.5, it["etiqueta"], fontName=f_sb, fontSize=10)
        etiqueta.fillColor = PIZARRA
        d.add(etiqueta)
        largo = max(3, (x1 - x0) * min(abs(it["puntos"]), tope) / tope)
        if sube:
            n = 14
            for j in range(n):
                r = Rect(x0 + largo * j / n, y, largo / n + 0.4, alto_barra)
                r.fillColor = _mezcla(SALVIA, MALVA, j / max(1, n - 1)); r.strokeColor = None
                d.add(r)
        else:
            r = Rect(x0, y, largo, alto_barra)
            r.fillColor = SALVIA_CLARO; r.strokeColor = PIZARRA; r.strokeWidth = 0.6
            d.add(r)
        # flecha vectorial + valor escrito
        xv = x1 + 8
        cy = y + alto_barra / 2
        if sube:
            tri = Polygon([xv, cy - 3, xv + 7, cy - 3, xv + 3.5, cy + 3.5])
            txt = f"+{_puntos_txt(it['puntos'])}"
        else:
            tri = Polygon([xv, cy + 3, xv + 7, cy + 3, xv + 3.5, cy - 3.5])
            txt = f"bajó {_puntos_txt(it['puntos'])}"
        tri.fillColor = PIZARRA; tri.strokeColor = None
        d.add(tri)
        v = String(xv + 11, y + 1.5, txt, fontName=f_sb, fontSize=10)
        v.fillColor = PIZARRA
        d.add(v)
    return d


def dibujo_icono_celda(nombre, color, lado=14, grosor=2.2):
    d = Drawing(lado, lado)
    d.add(icono(nombre, 0, 0, lado, color, grosor))
    return d


def dibujo_numero(n, fuentes, lado=26):
    d = Drawing(lado, lado)
    c = Circle(lado / 2, lado / 2, lado / 2 - 0.5)
    c.fillColor = SALVIA; c.strokeColor = None
    d.add(c)
    t = String(lado / 2, lado / 2 - 4.5, str(n), fontName=fuentes[2], fontSize=13, textAnchor="middle")
    t.fillColor = white
    d.add(t)
    return d


# ----------------------------------------------------------- flowables propios
class Tarjeta(Flowable):
    """Tarjeta blanca con borde, esquinas redondeadas y sombra suave (rectángulo desplazado)."""

    def __init__(self, contenido, ancho=None, pad=10, alto_min=0, radio=12, sin_fondo_interno=False):
        super().__init__()
        self.contenido = contenido if isinstance(contenido, (list, tuple)) else [contenido]
        self.ancho, self.pad, self.alto_min, self.radio = ancho, pad, alto_min, radio
        self._medidas = []

    def wrap(self, w, h):
        self.width = self.ancho or w
        interior = self.width - 2 * self.pad
        self._medidas = []
        total = 2 * self.pad
        for f in self.contenido:
            fw, fh = f.wrap(interior, h)
            self._medidas.append((fw, fh))
            total += fh
        self.height = max(total, self.alto_min)
        return self.width, self.height

    def draw(self):
        c = self.canv
        w, h, r = self.width, self.height, self.radio
        c.setFillColor(SALVIA_TINTE)
        c.roundRect(1.6, -1.8, w - 1.6, h, r, stroke=0, fill=1)
        c.setFillColor(white)
        c.setStrokeColor(BORDE)
        c.setLineWidth(0.8)
        c.roundRect(0, 0, w - 1.6, h - 0.0, r, stroke=1, fill=1)
        y = h - self.pad
        for f, (fw, fh) in zip(self.contenido, self._medidas):
            y -= fh
            f.drawOn(c, self.pad, y)


class Recortada(Flowable):
    """Envuelve un flowable (p. ej. una tabla) recortándolo con esquinas redondeadas y borde."""

    def __init__(self, interior, radio=10):
        super().__init__()
        self.interior, self.radio = interior, radio

    def wrap(self, w, h):
        self.width, self.height = self.interior.wrap(w, h)
        self.width = w
        return self.width, self.height

    def draw(self):
        c = self.canv
        c.saveState()
        p = c.beginPath()
        p.roundRect(0, 0, self.width, self.height, self.radio)
        c.clipPath(p, stroke=0, fill=0)
        self.interior.drawOn(c, 0, 0)
        c.restoreState()
        c.setStrokeColor(BORDE)
        c.setLineWidth(0.8)
        c.roundRect(0, 0, self.width, self.height, self.radio, stroke=1, fill=0)


class Aviso(Flowable):
    """Aviso con fondo salvia tinte, borde izquierdo de 4 pt e ícono de escudo."""

    def __init__(self, parrafo):
        super().__init__()
        self.parrafo = parrafo

    def wrap(self, w, h):
        self.width = w
        pw, ph = self.parrafo.wrap(w - 52, h)
        self.height = ph + 20
        return self.width, self.height

    def draw(self):
        c = self.canv
        c.saveState()
        p = c.beginPath()
        p.roundRect(0, 0, self.width, self.height, 8)
        c.clipPath(p, stroke=0, fill=0)
        c.setFillColor(SALVIA_TINTE)
        c.rect(0, 0, self.width, self.height, stroke=0, fill=1)
        c.setFillColor(SALVIA)
        c.rect(0, 0, 4, self.height, stroke=0, fill=1)
        c.restoreState()
        d = Drawing(22, 22)
        d.add(icono("escudo", 0, 0, 22, SALVIA, 1.8))
        d.drawOn(c, 16, self.height / 2 - 11)
        self.parrafo.drawOn(c, 46, 10)


# ----------------------------------------------------------- lienzo con "Página X de Y"
class _Lienzo(pdfcanvas.Canvas):
    fuente_pie = "Helvetica"

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self._estados = []

    def showPage(self):
        self._estados.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total = len(self._estados)
        for estado in self._estados:
            self.__dict__.update(estado)
            self._pie(total)
            super().showPage()
        super().save()

    def _pie(self, total):
        ancho, _ = letter
        x0, x1 = 18 * mm, ancho - 18 * mm
        self.setStrokeColor(BORDE)
        self.setLineWidth(0.7)
        self.line(x0, 15 * mm, x1, 15 * mm)
        self.setFillColor(PIZARRA_2)
        self.setFont(self.fuente_pie, 9)
        self.drawString(x0, 10.5 * mm, "Prototipo académico · Proyecto de grado, Universidad EAN")
        self.drawRightString(x1, 10.5 * mm, f"Página {self._pageNumber} de {total}")


def _fondo(canvas, doc):
    ancho, alto = letter
    canvas.saveState()
    canvas.setFillColor(FONDO)
    canvas.rect(0, 0, ancho, alto, stroke=0, fill=1)
    canvas.restoreState()


def _encabezado_factory(fuentes, fecha_txt):
    f_reg, f_sb, f_b = fuentes

    def _encabezado(canvas, doc):
        _fondo(canvas, doc)
        ancho, alto = letter
        h = 28 * mm
        canvas.saveState()
        p = canvas.beginPath()
        r = 14
        p.moveTo(0, alto)
        p.lineTo(ancho, alto)
        p.lineTo(ancho, alto - h + r)
        p.curveTo(ancho, alto - h + r * 0.45, ancho - r * 0.45, alto - h, ancho - r, alto - h)
        p.lineTo(r, alto - h)
        p.curveTo(r * 0.45, alto - h, 0, alto - h + r * 0.45, 0, alto - h + r)
        p.close()
        canvas.clipPath(p, stroke=0, fill=0)
        try:
            canvas.linearGradient(0, 0, ancho, 0, (SALVIA, MALVA_OSCURO), (0, 1), extend=False)
        except Exception:  # respaldo: franjas verticales
            n = 40
            for i in range(n):
                canvas.setFillColor(_mezcla(SALVIA, MALVA_OSCURO, i / (n - 1)))
                canvas.rect(ancho * i / n, alto - h, ancho / n + 1, h, stroke=0, fill=1)
        canvas.restoreState()
        x = 18 * mm
        canvas.setFillColor(white)
        canvas.setFont(f_b, 20)
        canvas.drawString(x, alto - 13.5 * mm, "Estimación de riesgo de SOP")
        canvas.setFont(f_reg, 11)
        canvas.drawString(x, alto - 20.5 * mm, "Informe para llevar a mi consulta")
        d = Drawing(26, 26)
        d.add(icono("brote", 0, 0, 26, white, 1.7))
        d.drawOn(canvas, ancho - 18 * mm - 26, alto - 13 * mm)
        canvas.setFont(f_reg, 10.5)
        canvas.drawRightString(ancho - 18 * mm, alto - 20.5 * mm, fecha_txt)

    return _encabezado


# ----------------------------------------------------------- generar_pdf
def generar_pdf(pct, nombre, afinada, conteo, usando_izquierdo, factores, hay_menores, respuestas,
                fecha=None):
    """
    Devuelve los bytes del PDF.
      pct, nombre        : porcentaje y categoría ('Bajo' ... 'Alto')
      afinada, conteo    : si se usó el conteo folicular y su valor
      usando_izquierdo   : el conteo es del ovario izquierdo (menor precisión)
      factores           : lista de dicts con 'etiqueta', 'puntos' (con signo) y 'razon'
      hay_menores        : hubo respuestas con efecto casi nulo
      respuestas         : lista de (etiqueta, texto_de_la_respuesta, afirmativa: bool)
    """
    fuentes = _registrar_fuentes()
    f_reg, f_sb, f_b = fuentes
    _Lienzo.fuente_pie = f_reg
    fecha = fecha or date.today()
    fecha_txt = fecha.strftime("%d/%m/%Y")

    ancho_pag, alto_pag = letter
    margen = 18 * mm
    ancho_util = ancho_pag - 2 * margen

    base = ParagraphStyle("base", fontName=f_reg, fontSize=10.5, leading=14.7, textColor=PIZARRA)
    peq = ParagraphStyle("peq", parent=base, fontSize=9.5, leading=13, textColor=PIZARRA_2)
    nota = ParagraphStyle("nota", parent=base, fontSize=9, leading=12.5, textColor=PIZARRA_2)
    h2 = ParagraphStyle("h2", parent=base, fontName=f_b, fontSize=13.5, leading=17, spaceBefore=12, spaceAfter=6)
    h3 = ParagraphStyle("h3", parent=base, fontName=f_sb, fontSize=11, leading=14)
    tarj_t = ParagraphStyle("tarj_t", parent=base, fontName=f_sb, fontSize=11, leading=14)
    tarj_d = ParagraphStyle("tarj_d", parent=base, fontSize=9.5, leading=13, textColor=PIZARRA_2)
    punto = ParagraphStyle("punto", parent=base, fontSize=10, leading=14, leftIndent=11, bulletIndent=0,
                           spaceAfter=2)

    historia = [NextPageTemplate("siguientes")]

    # --- 2. Resultado
    tipo = ("Estimación con seis preguntas (incluye conteo folicular)" if afinada
            else "Estimación con cinco preguntas")
    ancho_izq = 52 * mm
    ancho_der = ancho_util - 2 * 10 - ancho_izq - 6 * mm
    derecha = Table(
        [[dibujo_pastilla(nombre, CATEGORIAS_NIVEL(nombre), fuentes, ancho=min(ancho_der, 78 * mm))],
         [dibujo_escala(nombre, fuentes, ancho=ancho_der)],
         [Paragraph(f"<b>{tipo}</b>", ParagraphStyle("t", parent=base, fontName=f_sb, fontSize=10.5))],
         [Paragraph(MICROTEXTO, peq)]],
        colWidths=[ancho_der],
        style=TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                          ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                          ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
    resultado = Table(
        [[dibujo_dona(pct, fuentes, ancho_izq), derecha]],
        colWidths=[ancho_izq + 6 * mm, ancho_der],
        style=TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                          ("RIGHTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 0),
                          ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
    historia.append(Tarjeta([resultado], pad=10))

    # --- 3. Qué influyó
    historia.append(Paragraph("Qué influyó en tu resultado", h2))
    bloque = []
    if factores:
        grafico = dibujo_factores(factores, fuentes, ancho_util - 20)
        frases = [Paragraph(f"<b>{f['etiqueta']}.</b> {f['razon']}", peq) for f in factores]
        bloque.append(Tarjeta([grafico], pad=10))
        bloque.append(Spacer(1, 6))
        for p in frases:
            bloque.append(p)
            bloque.append(Spacer(1, 3))
    if hay_menores:
        bloque.append(Paragraph("Otras respuestas casi no cambiaron el resultado.", peq))
    if not factores and not hay_menores:
        bloque.append(Paragraph("Ninguna respuesta cambió la estimación de forma destacada.", peq))
    historia.append(KeepTogether(bloque[:2]) if len(bloque) >= 2 else bloque[0])
    historia.extend(bloque[2:])

    # --- 4. Mis respuestas
    filas, estilos = [], []
    for i, (etiqueta, texto, afirm) in enumerate(respuestas):
        filas.append([Paragraph(etiqueta, h3),
                      dibujo_icono_celda("check" if afirm else "guion", SALVIA if afirm else PIZARRA_2),
                      Paragraph(texto, base)])
    tabla = Table(filas, colWidths=[58 * mm, 9 * mm, ancho_util - 67 * mm])
    tabla.setStyle(TableStyle([
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [white, FONDO_2]),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 10), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    ]))
    leyenda = Table([[dibujo_icono_celda("check", SALVIA, 10, 2.4), Paragraph("la señal está presente", nota),
                      dibujo_icono_celda("guion", PIZARRA_2, 10, 2.4), Paragraph("la señal no está presente", nota)]],
                    colWidths=[5 * mm, 40 * mm, 5 * mm, 60 * mm], hAlign="LEFT",
                    style=TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                                      ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 2),
                                      ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
    historia.append(KeepTogether([Paragraph("Mis respuestas", h2), Recortada(tabla), Spacer(1, 3), leyenda]))

    # --- 5. Especialidades
    ancho_t = (ancho_util - 2 * 4 * mm) / 3
    tarjetas = []
    for n, (nom, desc) in enumerate(ESPECIALIDADES, start=1):
        tarjetas.append(Tarjeta([dibujo_numero(n, fuentes), Spacer(1, 4), Paragraph(nom, tarj_t),
                                 Paragraph(desc, tarj_d)], pad=9, alto_min=36 * mm))
    fila_t = Table([[tarjetas[0], "", tarjetas[1], "", tarjetas[2]]],
                   colWidths=[ancho_t, 4 * mm, ancho_t, 4 * mm, ancho_t],
                   style=TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                     ("RIGHTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 0),
                                     ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
    historia.append(KeepTogether([Paragraph("Especialidades que pueden ayudarte", h2), fila_t]))

    # --- 6. Para la consulta
    ancho_c = (ancho_util - 6 * mm) / 2
    izq = [Paragraph("Qué llevar", h3), Spacer(1, 4)] + [Paragraph(t, punto, bulletText="•") for t in QUE_LLEVAR]
    der = [Paragraph("Preguntas que puedo hacer", h3), Spacer(1, 4)] + [Paragraph(t, punto, bulletText="•")
                                                                        for t in PREGUNTAS_CONSULTA]
    t_izq, t_der = Tarjeta(izq, pad=10), Tarjeta(der, pad=10)
    alto_c = max(t_izq.wrap(ancho_c, 1e4)[1], t_der.wrap(ancho_c, 1e4)[1])
    t_izq.alto_min = t_der.alto_min = alto_c
    consulta = Table([[t_izq, "", t_der]], colWidths=[ancho_c, 6 * mm, ancho_c],
                     style=TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                       ("RIGHTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 0),
                                       ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
    historia.append(KeepTogether([Paragraph("Para la consulta", h2), consulta]))

    # --- 7. Aviso final
    historia.append(Spacer(1, 12))
    historia.append(KeepTogether([Aviso(Paragraph(AVISO_ETICO, base)), Spacer(1, 4),
                                  Paragraph(NOTA_POBLACION, nota)]))

    # --- armado
    buf = io.BytesIO()
    doc = BaseDocTemplate(
        buf, pagesize=letter, leftMargin=margen, rightMargin=margen, topMargin=margen, bottomMargin=margen,
        title="Informe de estimación de SOP", author="Prototipo académico · Universidad EAN",
        subject="Estimación de riesgo de SOP (no es un diagnóstico)", creator="Calculador SOP · Universidad EAN",
        lang="es")
    marco_1 = Frame(margen, 20 * mm, ancho_util, alto_pag - 28 * mm - 7 * mm - 20 * mm, id="m1",
                    leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    marco_n = Frame(margen, 20 * mm, ancho_util, alto_pag - 20 * mm - margen, id="mn",
                    leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    doc.addPageTemplates([
        PageTemplate(id="primera", frames=[marco_1], onPage=_encabezado_factory(fuentes, fecha_txt)),
        PageTemplate(id="siguientes", frames=[marco_n], onPage=_fondo),
    ])
    doc.build(historia, canvasmaker=_Lienzo)
    return buf.getvalue()
