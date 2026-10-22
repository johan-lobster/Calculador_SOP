# =====================================================================
# Prototipo: estimación de riesgo de SOP (proyecto de grado, EAN)
# Interfaz: bienvenida -> seis preguntas (una por pantalla) -> resultado
# -> "¿Y ahora qué?" -> vista "Aprende más".
#   - Preguntas 1 a 5 (obligatorias): modelo_sop_corto.pkl
#   - Pregunta 6 (opcional, conteo folicular): modelo_sop_foliculo.pkl
# Organización del código:
#   modelo.py      lógica del modelo (NO se toca)
#   explicacion.py por qué cada respuesta sube o baja la estimación (NO se toca)
#   app.py         interfaz (este archivo)
# Ejecutar con:  streamlit run app.py     (requiere streamlit >= 1.40)
# =====================================================================
import math
from datetime import date

from modelo import (
    CLAVE_OPCIONAL,
    PORCENTAJE_RECOMENDAR_CONSULTA,
    PREGUNTAS,
    RUTA_CORTO,
    RUTA_FOLICULO,
    cargar_paquete,
    categoria,
    construir_fila,
    estimar_riesgo,
    fuera_de_rango,
)
from explicacion import analisis_general, construir_explicacion

# ----------------------------------------------------------- colores
SALVIA = "#4A7C7D"
SALVIA_CLARO = "#8DB3A9"
MALVA = "#9C7A97"
MALVA_OSCURO = "#7E5F7A"
PIZARRA = "#2D3748"
MELOCOTON = "#F4A261"
ARENA = "#E9D8A6"
TERRACOTA = "#C8694A"
BORDE = "#D5E3E1"

# Escala de las 5 categorías (sin rojo). Siempre color + ícono + texto.
NOMBRES_NIVEL = ["Bajo", "Medio-bajo", "Medio", "Medio-alto", "Alto"]
COLORES_ESCALA = [SALVIA, SALVIA_CLARO, ARENA, MELOCOTON, TERRACOTA]
CATEGORIAS_UI = {
    "Bajo": dict(
        nivel=1, borde="#4A7C7D", fondo="#E3EEEC", icono="hoja",
        frase="Tus respuestas muestran pocas señales asociadas al SOP.",
        micro=("Es una noticia tranquila, pero un resultado bajo no descarta nada por sí solo. "
               "Si algo de tu ciclo o de tu piel te preocupa, vale la pena comentarlo en consulta."),
    ),
    "Medio-bajo": dict(
        nivel=2, borde="#8DB3A9", fondo="#EAF2EF", icono="hoja",
        frase="Tus respuestas muestran algunas señales asociadas al SOP, sin un patrón marcado.",
        micro=("Una o dos señales son comunes y pueden deberse a muchas cosas. "
               "Si persisten o te incomodan, puedes consultarlo con calma."),
    ),
    "Medio": dict(
        nivel=3, borde="#E9D8A6", fondo="#F7EFD3", icono="punto",
        frase="Tus respuestas muestran varias señales asociadas al SOP.",
        micro=("Hay un conjunto de señales que vale la pena revisar con un profesional. "
               "No significa que tengas SOP: solo una valoración médica puede confirmarlo."),
    ),
    "Medio-alto": dict(
        nivel=4, borde="#F4A261", fondo="#FFF1E3", icono="triangulo",
        frase="Tus respuestas coinciden con bastantes señales asociadas al SOP.",
        micro=("Te sugerimos pedir una cita con ginecología o endocrinología para revisarlo. "
               "Es un paso tranquilo y de rutina, no una urgencia."),
    ),
    "Alto": dict(
        nivel=5, borde="#C8694A", fondo="#FBEDE7", icono="atencion",
        frase="Tus respuestas coinciden con muchas de las señales asociadas al SOP.",
        micro=("Lo más útil ahora es hablarlo con un profesional de la salud, que podrá valorar tu "
               "caso con exámenes. Esto no es un diagnóstico, y el SOP es una condición frecuente "
               "que se puede manejar con acompañamiento médico."),
    ),
}

# ----------------------------------------------------------- preguntas
# Mismo orden que PREGUNTAS de modelo.py (el orden define la fila del modelo).
_CLAVES = list(PREGUNTAS.values())  # piel, ciclo_irregular, aumento_peso, vello, acne
ORDINALES = ["Primera", "Segunda", "Tercera", "Cuarta", "Quinta", "Sexta"]

PREGUNTAS_UI = [
    dict(
        clave=_CLAVES[0], titulo="¿Tienes zonas de piel oscurecida (cuello, axilas o ingles)?",
        si="Sí", no="No", verdadero="Sí",
        ayuda=("Son manchas o zonas más oscuras que el resto de la piel, a veces con textura "
               "aterciopelada, en el cuello, las axilas o las ingles. Un bronceado o las marcas de "
               "roce de la ropa no cuentan."),
        resumen="Piel oscurecida",
    ),
    dict(
        clave=_CLAVES[1], titulo="Tus ciclos menstruales son:",
        si="Irregulares", no="Regulares", verdadero="Irregulares",
        ayuda=("Se consideran irregulares si pasan menos de 21 o más de 35 días entre un periodo y "
               "otro, si cambian mucho de un mes a otro, o si pasas varios meses sin periodo. "
               "Si no estás segura, elige la opción que más se parezca a lo que has vivido en "
               "el último año."),
        resumen="Ciclos",
    ),
    dict(
        clave=_CLAVES[2], titulo="¿Has notado aumento de peso que te cuesta controlar?",
        si="Sí", no="No", verdadero="Sí",
        ayuda=("Cuando subes de peso sin un cambio claro en tu alimentación o actividad, o te cuesta "
               "bajarlo aunque lo intentes."),
        resumen="Aumento de peso",
    ),
    dict(
        clave=_CLAVES[3], titulo="¿Tienes crecimiento excesivo de vello (rostro, pecho o espalda)?",
        si="Sí", no="No", verdadero="Sí",
        ayuda=("Vello grueso y oscuro en zonas donde suele ser escaso: encima del labio, mentón, pecho, "
               "abdomen o espalda. El vello fino y claro no cuenta."),
        resumen="Crecimiento de vello",
    ),
    dict(
        clave=_CLAVES[4], titulo="¿Tienes acné persistente?",
        si="Sí", no="No", verdadero="Sí",
        ayuda=("Brotes que aparecen con frecuencia y duran meses, o que siguen saliendo pasada la "
               "adolescencia, en la cara, el pecho o la espalda."),
        resumen="Acné",
    ),
]
N_OBLIGATORIAS = len(PREGUNTAS_UI)  # 5


# ----------------------------------------------------------- utilidades puras
def h(s):
    """Colapsa HTML a una línea: evita que Markdown lo tome como bloque de código."""
    return " ".join(linea.strip() for linea in s.strip().splitlines() if linea.strip())


def lista_ordinales(indices):
    """[1, 3] -> 'la segunda y la cuarta pregunta'; [1] -> 'la segunda pregunta'."""
    nombres = [ORDINALES[i].lower() for i in indices]
    if len(nombres) == 1:
        return f"la {nombres[0]} pregunta"
    return "la " + ", la ".join(nombres[:-1]) + " y la " + nombres[-1] + " pregunta"


def _puntos_txt(valor):
    n = max(1, int(round(abs(valor))))
    return "1 punto" if n == 1 else f"{n} puntos"


# Íconos de línea (24x24, trazo redondeado). Se dibujan con ico().
ICONOS = {
    "brote": '<path d="M12 21v-8"/><path d="M12 13c0-3.6-2.6-5.6-6.5-5.6 0 3.6 2.6 5.6 6.5 5.6z"/>'
             '<path d="M12 11c0-3.2 2.3-5.2 5.8-5.2 0 3.2-2.3 5.2-5.8 5.2z"/>',
    "hoja": '<path d="M5 19c0-8 5-13 14-14 0 9-5 14-13 14"/><path d="M5 19l8-8"/>',
    "punto": '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="2.5"/>',
    "triangulo": '<path d="M12 4L3 19.5h18L12 4z"/><path d="M12 10v4.5M12 17h.01"/>',
    "atencion": '<circle cx="12" cy="12" r="9"/><path d="M12 7.5v5M12 16h.01"/>',
    "info": '<circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 8h.01"/>',
    "escudo": '<path d="M12 3l8 3v6c0 4.5-3.2 8-8 9-4.8-1-8-4.5-8-9V6l8-3z"/>',
    "escudo_check": '<path d="M12 3l8 3v6c0 4.5-3.2 8-8 9-4.8-1-8-4.5-8-9V6l8-3z"/><path d="M8.5 12l2.5 2.5 4.5-5"/>',
    "portapapeles": '<rect x="6" y="4.5" width="12" height="16.5" rx="2"/><path d="M9.5 4.5h5v3h-5z"/><path d="M9 12h6M9 16h4"/>',
    "reloj": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    "check_circulo": '<circle cx="12" cy="12" r="9"/><path d="M8 12.5l3 3 5-6"/>',
    "barras": '<path d="M5 20V11M12 20V4M19 20v-6"/>',
    "candado": '<rect x="5" y="11" width="14" height="9" rx="2"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/>',
    "check": '<path d="M5 12.5l4.5 4.5L19 7"/>',
    "flecha_ne": '<path d="M7 17L17 7M8 7h9v9"/>',
    "estetoscopio": '<path d="M5 3H4a2 2 0 0 0-2 2v4a6 6 0 0 0 12 0V5a2 2 0 0 0-2-2h-1"/>'
                    '<path d="M8 15a6 6 0 0 0 12 0v-3"/><circle cx="20" cy="10" r="2"/>',
    "telefono": '<path d="M5 4h4l2 5-2.5 1.5a11 11 0 0 0 5 5L15 13l5 2v4a2 2 0 0 1-2 2A16 16 0 0 1 3 6a2 2 0 0 1 2-2z"/>',
    "libro": '<path d="M12 6c-2-1.5-5-2-8-2v13c3 0 6 .5 8 2 2-1.5 5-2 8-2V4c-3 0-6 .5-8 2z"/><path d="M12 6v13"/>',
    "ciclo": '<path d="M20 12a8 8 0 1 1-2.5-5.8"/><path d="M20 4v4.5h-4.5"/>',
    "brillo": '<circle cx="12" cy="12" r="3"/><path d="M12 3v3M12 18v3M3 12h3M18 12h3"/>',
    "ondas": '<path d="M4 9c2-2.5 4 2.5 8 0s6 2.5 8 0M4 15c2-2.5 4 2.5 8 0s6 2.5 8 0"/>',
    "gota": '<path d="M12 3c3.5 4.5 6 7.5 6 10.5a6 6 0 0 1-12 0C6 10.5 8.5 7.5 12 3z"/>',
    "balanza": '<rect x="4" y="4" width="16" height="16" rx="4"/><path d="M8.5 10a4.5 4.5 0 0 1 7 0M12 12.5l2-2.2"/>',
}


def ico(nombre, tam=22, color="currentColor", grosor=1.75):
    return (f'<svg class="ico" width="{tam}" height="{tam}" viewBox="0 0 24 24" fill="none" '
            f'stroke="{color}" stroke-width="{grosor}" stroke-linecap="round" stroke-linejoin="round" '
            f'aria-hidden="true">{ICONOS[nombre]}</svg>')


def svg_dona(pct):
    """Dona con degradado salvia -> malva, halo suave y el porcentaje real al centro."""
    radio = 76
    largo = 2 * math.pi * radio
    trazo = largo * pct / 100
    return h(f"""
    <svg class="dona" viewBox="0 0 200 200" role="img" aria-label="Estimación del modelo: {pct} por ciento"
         xmlns="http://www.w3.org/2000/svg">
      <defs>
        <linearGradient id="gdona" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stop-color="{SALVIA}"/><stop offset="100%" stop-color="{MALVA}"/>
        </linearGradient>
        <filter id="halo" x="-30%" y="-30%" width="160%" height="160%"><feGaussianBlur stdDeviation="9"/></filter>
      </defs>
      <circle cx="100" cy="100" r="{radio}" fill="rgba(156,122,151,.18)" filter="url(#halo)"/>
      <circle cx="100" cy="100" r="{radio}" fill="none" stroke="{BORDE}" stroke-width="16"/>
      <circle cx="100" cy="100" r="{radio}" fill="none" stroke="url(#gdona)" stroke-width="16"
              stroke-linecap="round" stroke-dasharray="{trazo:.1f} {largo:.1f}" transform="rotate(-90 100 100)"/>
      <text x="100" y="114" text-anchor="middle" font-size="44" font-weight="800"
            font-family="Inter, Arial, sans-serif" fill="{PIZARRA}">{pct}%</text>
    </svg>""")


def _signo(p):
    return ("▲ +" if p >= 0 else "▼ −") + str(max(1, int(round(abs(p))))) + " pts"


def svg_cascada(explicacion):
    """
    Cascada en la escala de riesgo (misma lógica que explicacion.svg_cascada, solo cambian los
    colores): sube en melocotón, baja en salvia claro, fondo transparente, texto en pizarra.
    El signo y la flecha van escritos, así que no depende solo del color.
    """
    ancho, margen, alto_fila = 360, 8, 44
    zona = ancho - 2 * margen
    esc = lambda pct: margen + zona * max(0.0, min(100.0, pct)) / 100

    base, final = explicacion["base_pct"], explicacion["final_pct"]
    filas = [("Punto de partida", "0 %", 0, 0, BORDE)]
    acumulado = 0.0
    if explicacion["base_visible"]:
        filas.append(("Riesgo base (sin ninguna señal)", _signo(base), 0, base, BORDE))
        acumulado = base
    for it in explicacion["items"]:
        nuevo = acumulado + it["puntos"]
        color = MELOCOTON if it["puntos"] >= 0 else SALVIA_CLARO
        filas.append((it["etiqueta"], _signo(it["puntos"]), acumulado, nuevo, color))
        acumulado = nuevo
    if explicacion["menores"]:
        resto = sum(m["puntos"] for m in explicacion["menores"])
        if not explicacion["base_visible"]:
            resto += base
        nuevo = acumulado + resto
        filas.append(("Otras respuestas", "casi sin efecto", acumulado, nuevo, BORDE))
        acumulado = nuevo
    filas.append(("Tu estimación", f"{round(final)} %", 0, final, MALVA_OSCURO))

    alto = alto_fila * len(filas) + 10
    resumen = "; ".join(f"{e}: {v}" for e, v, *_ in filas)
    partes = [
        f'<svg viewBox="0 0 {ancho} {alto}" role="img" width="100%" '
        f'style="display:block;margin:0 auto;max-width:{ancho}px;background:transparent" '
        f'aria-label="Cómo cambió tu estimación. {resumen}" '
        f'xmlns="http://www.w3.org/2000/svg" font-family="Inter, Arial, sans-serif">'
    ]
    for k, (etiqueta, valor, desde, hasta, color) in enumerate(filas):
        y = 6 + k * alto_fila
        izq, der = sorted((esc(desde), esc(hasta)))
        partes.append(f'<text x="{margen}" y="{y + 14}" font-size="14" fill="{PIZARRA}">{etiqueta}</text>')
        partes.append(f'<text x="{ancho - margen}" y="{y + 14}" font-size="14" font-weight="700" '
                      f'text-anchor="end" fill="{PIZARRA}">{valor}</text>')
        partes.append(f'<rect x="{margen}" y="{y + 22}" width="{zona}" height="12" rx="4" fill="#E3EEEC"/>')
        partes.append(f'<rect x="{izq:.1f}" y="{y + 22}" width="{max(der - izq, 2):.1f}" height="12" '
                      f'rx="4" fill="{color}" stroke="{PIZARRA}" stroke-width="0.8"/>')
    partes.append("</svg>")
    return "".join(partes)


def texto_resumen(res, resp):
    """Resumen en texto plano para llevar a la consulta (se genera al momento, no se guarda)."""
    lineas = [
        "RESUMEN DE MI ESTIMACIÓN DE SOP (prototipo académico, Universidad EAN)",
        f"Fecha: {date.today().strftime('%d/%m/%Y')}",
        "",
        "Mis respuestas:",
    ]
    for q in PREGUNTAS_UI:
        v = resp.get(q["clave"])
        txt = "sin respuesta" if v is None else (q["si"] if v else q["no"])
        lineas.append(f"- {q['resumen']}: {txt}")
    if res["afinada"]:
        lado = "izquierdo (usado como aproximación)" if res["usando_izquierdo"] else "derecho"
        lineas.append(f"- Conteo folicular (ovario {lado}): {res['conteo']}")
    else:
        lineas.append("- Conteo folicular: no lo tenía")
    lineas += [
        "",
        f"Resultado: {res['pct']} % · nivel {res['nombre']} "
        f"({'seis' if res['afinada'] else 'cinco'} preguntas)",
        "",
        "Importante: es una estimación de un modelo entrenado con 541 mujeres de Kerala, India, "
        "no validado en población colombiana. No es un diagnóstico y no reemplaza la valoración "
        "de un profesional de la salud.",
    ]
    return "\n".join(lineas)


def ilustracion_botanica():
    """Composición abstracta (sin rostros): óvalo, cuenco, manchas malva, ramas, círculos y ondas."""
    def hoja(x, y, rot, color, esc=1.0):
        return (f'<path d="M0 0C9 -12 9 -30 0 -44C-9 -30 -9 -12 0 0Z" fill="{color}" '
                f'transform="translate({x} {y}) rotate({rot}) scale({esc})"/>')
    ondas = "".join(
        f'<path d="M{198} {170 + i * 11}c6 -6 12 6 18 0s12 6 18 0s12 6 18 0s12 6 18 0" fill="none" '
        f'stroke="{SALVIA}" stroke-width="1.5" stroke-linecap="round"/>' for i in range(5))
    return h(f"""
    <svg class="ilus" viewBox="0 0 300 300" role="img"
         aria-label="Ilustración decorativa de hojas y formas orgánicas" xmlns="http://www.w3.org/2000/svg">
      <ellipse cx="150" cy="150" rx="100" ry="122" fill="#E3EEEC"/>
      <path d="M62 168h176a88 88 0 0 1-176 0z" fill="{SALVIA}"/>
      <path d="M62 168h88a88 88 0 0 1-88 0z" fill="{SALVIA_CLARO}"/>
      <path d="M205 62c26-12 52 6 46 34-5 24-34 32-52 16-14-13-14-40 6-50z" fill="{MALVA}" fill-opacity=".85"/>
      <path d="M52 212c8-26 40-34 58-16 16 16 8 46-16 54-24 7-48-14-42-38z" fill="{MALVA}" fill-opacity=".85"/>
      <path d="M150 168V78" stroke="{SALVIA}" stroke-width="1.5" fill="none"/>
      {hoja(150, 120, -28, SALVIA, 0.8)}{hoja(150, 100, 24, SALVIA_CLARO, 0.8)}{hoja(150, 82, -8, SALVIA, 0.7)}
      <path d="M232 268c-6-28-2-50 14-72" stroke="{SALVIA}" stroke-width="1.5" fill="none"/>
      {hoja(240, 232, 36, SALVIA, 0.65)}{hoja(236, 250, -36, SALVIA_CLARO, 0.65)}{hoja(246, 214, 12, SALVIA, 0.55)}
      <path d="M88 252c10-18 30-28 52-30" stroke="{SALVIA}" stroke-width="1.5" fill="none"/>
      {hoja(112, 236, 58, SALVIA_CLARO, 0.6)}
      <circle cx="188" cy="80" r="7" fill="{MALVA}"/><circle cx="60" cy="150" r="6" fill="{SALVIA}"/>
      <circle cx="262" cy="150" r="5" fill="{MALVA}"/>
      {ondas}
    </svg>""")


# ====================================================== INTERFAZ (Streamlit)
import streamlit as st

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
:root {
  --bg: #FAFAFA; --bg-2: #EEF4F3;
  --salvia: #4A7C7D; --salvia-oscuro: #2F5758; --salvia-claro: #8DB3A9; --salvia-tinte: #E3EEEC;
  --malva: #9C7A97; --malva-oscuro: #7E5F7A; --malva-hover: #6B4F67;
  --pizarra: #2D3748; --pizarra-2: #4A5568;
  --melocoton: #F4A261; --melocoton-tinte: #FFF1E3; --arena: #E9D8A6;
  --terracota: #C8694A; --terracota-tinte: #FBEDE7; --borde: #D5E3E1;
  --sombra: 0 1px 2px rgba(45,55,72,.06), 0 14px 34px rgba(74,124,125,.14);
  --pila: 0 1px 2px rgba(45,55,72,.06), 0 14px 34px rgba(74,124,125,.14),
          0 8px 0 -6px rgba(255,255,255,.9), 0 16px 0 -12px rgba(255,255,255,.7);
}
html, body { overflow-x: hidden; }
html, body, .stApp, button, input, textarea, [data-testid="stMarkdownContainer"] {
  font-family: 'Inter', system-ui, -apple-system, 'Segoe UI', Arial, sans-serif !important;
}
.stApp { background: linear-gradient(180deg, #FAFAFA 0%, #EEF4F3 100%) fixed; color: var(--pizarra);
         font-size: 17px; overflow-x: hidden; }
[data-testid="stAppViewContainer"], [data-testid="stMain"], .main, [data-testid="stBottom"] {
  background: transparent !important; position: relative; z-index: 1;
}
.stApp::before {
  content: ""; position: fixed; inset: 0; z-index: 0; pointer-events: none;
  background:
    radial-gradient(circle at 8% 20%, rgba(74,124,125,.30) 0, rgba(74,124,125,0) 18%),
    radial-gradient(circle at 8% 80%, rgba(74,124,125,.22) 0, rgba(74,124,125,0) 18%),
    radial-gradient(circle at 92% 25%, rgba(156,122,151,.28) 0, rgba(156,122,151,0) 18%),
    radial-gradient(circle at 92% 85%, rgba(156,122,151,.22) 0, rgba(156,122,151,0) 18%);
}
[data-testid="stHeader"], [data-testid="stToolbar"], [data-testid="stDecoration"], #MainMenu, footer {
  display: none !important;
}
.block-container, [data-testid="stMainBlockContainer"] {
  max-width: 720px !important; padding: 0 16px 56px !important;
}
[data-testid="stMarkdownContainer"] p, [data-testid="stMarkdownContainer"] li { font-size: 17px; line-height: 1.6; }
[data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] p { font-size: 14.5px; color: var(--pizarra-2); }
h1, h2, h3 { color: var(--pizarra); font-weight: 800; letter-spacing: -.02em; }
h2 { font-size: 25px !important; font-weight: 700 !important; letter-spacing: -.01em; }
a { color: var(--salvia-oscuro); }
.ico { flex: none; }

/* ---------- Encabezado global ---------- */
.sop-header {
  width: 100vw; margin-left: calc(50% - 50vw); min-height: 96px; display: flex; align-items: center;
  background: linear-gradient(90deg, #4A7C7D 0%, #7E5F7A 100%); color: #fff;
  border-radius: 0 0 28px 28px; box-shadow: 0 10px 30px rgba(74,124,125,.25); margin-bottom: 8px;
}
.sop-header-in { width: 100%; max-width: 720px; margin: 0 auto; padding: 0 16px; display: flex;
                 align-items: center; gap: 12px; }
.sop-t1 { font-size: 22px; font-weight: 700; line-height: 1.2; color: #fff; }
.sop-t2 { font-size: 14px; color: rgba(255,255,255,.92); margin-top: 2px; }

/* ---------- Barra de pestañas propia (st.session_state) ---------- */
.st-key-tabs { border-bottom: 1px solid var(--borde); margin-bottom: 20px; }
.st-key-tabs [data-testid="stHorizontalBlock"] { flex-direction: row !important; flex-wrap: nowrap !important;
  gap: 8px !important; }
.st-key-tabs [data-testid="stColumn"], .st-key-tabs [data-testid="column"] {
  min-width: 0 !important; width: auto !important; flex: 0 0 auto !important; }
.st-key-tabs button, .st-key-tabs button[kind="primary"], .st-key-tabs button[kind="secondary"],
.st-key-tabs button[data-testid="stBaseButton-primary"], .st-key-tabs button[data-testid="stBaseButton-secondary"] {
  background: transparent !important; box-shadow: none !important; border: 0 !important;
  border-bottom: 3px solid transparent !important; border-radius: 0 !important; min-height: 48px !important;
  padding: 0 14px !important; color: var(--pizarra-2) !important; font-weight: 500 !important; width: auto !important;
}
.st-key-tabs button[kind="primary"], .st-key-tabs button[data-testid="stBaseButton-primary"] {
  color: var(--pizarra) !important; font-weight: 700 !important; border-bottom: 3px solid var(--malva-oscuro) !important;
}

/* ---------- Tarjetas ---------- */
.card, .st-key-card_par, .st-key-card_impar, .st-key-tarjeta_bienv, .st-key-tarjeta_resultado,
.st-key-card_resumen, [class*="st-key-ahora_"], .st-key-card_ayuda {
  background: #FFFFFF; border: 1px solid var(--borde); border-radius: 20px; padding: 28px; box-shadow: var(--sombra);
}
.st-key-card_par, .st-key-card_impar, .st-key-tarjeta_bienv, .st-key-tarjeta_resultado { box-shadow: var(--pila); }
.st-key-card_par { animation: entraA 200ms ease-out both; }
.st-key-card_impar { animation: entraB 200ms ease-out both; }
@keyframes entraA { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: none; } }
@keyframes entraB { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: none; } }
@media (prefers-reduced-motion: reduce) { .st-key-card_par, .st-key-card_impar { animation: none; } }
@media (max-width: 640px) {
  .card, .st-key-card_par, .st-key-card_impar, .st-key-tarjeta_bienv, .st-key-tarjeta_resultado,
  .st-key-card_resumen, [class*="st-key-ahora_"], .st-key-card_ayuda { padding: 18px; }
  .stApp::before { opacity: .5; }
}

/* ---------- Avisos propios (reemplazan st.info / warning / error) ---------- */
.aviso { display: flex; gap: 12px; align-items: flex-start; padding: 14px 16px; border-radius: 14px;
         border-left: 4px solid; color: var(--pizarra); line-height: 1.55; margin: 12px 0; font-size: 16px; }
.aviso .ico { margin-top: 2px; }
.aviso-info { background: var(--salvia-tinte); border-color: var(--salvia); }
.aviso-precaucion { background: var(--melocoton-tinte); border-color: var(--melocoton); }
.aviso-error { background: var(--terracota-tinte); border-color: var(--terracota); }
.aviso-centrado { max-width: 560px; margin: 20px auto 0; }

/* ---------- Pastillas ---------- */
.pill-ord { display: inline-block; background: var(--salvia); color: #fff; font-weight: 600; font-size: 14px;
            padding: 5px 14px; border-radius: 999px; }
.pill-opc { display: inline-block; background: var(--melocoton-tinte); border: 1px solid var(--melocoton);
            color: var(--pizarra); font-weight: 600; font-size: 14px; padding: 4px 12px; border-radius: 999px;
            margin-left: 8px; }
.pill-centro { text-align: center; margin: 24px 0 12px; }
.pill-fuerte { display: inline-block; background: var(--salvia); color: #fff; font-weight: 600; font-size: 14px;
               padding: 6px 16px; border-radius: 999px; }
.sop-h1 { font-size: clamp(28px, 4vw, 40px); font-weight: 800; letter-spacing: -.02em; line-height: 1.15;
          margin: 8px 0 16px; color: var(--pizarra); }
.sop-h1.centro { text-align: center; }
.sop-h2 { font-size: clamp(26px, 3.4vw, 32px); font-weight: 800; letter-spacing: -.02em; line-height: 1.2;
          margin: 14px 0 10px; color: var(--pizarra); }

/* ---------- Bienvenida ---------- */
.lista-ico { list-style: none; padding: 0; margin: 10px 0 18px; display: flex; flex-direction: column; gap: 12px; }
.lista-ico li { display: flex; gap: 12px; align-items: flex-start; font-size: 16px; line-height: 1.5; color: var(--pizarra); }
.lista-ico .ico { color: var(--salvia); margin-top: 1px; }
.ilus { width: 100%; max-width: 300px; height: auto; display: block; margin: 0 auto; }
.st-key-pill_sinov { background: var(--salvia-tinte); border: 1px solid var(--borde); border-radius: 999px;
                     padding: 6px 16px; width: fit-content; margin-bottom: 12px; }
@media (max-width: 640px) {
  .st-key-tarjeta_bienv [data-testid="stHorizontalBlock"] { flex-direction: column-reverse !important; }
  .st-key-tarjeta_bienv .ilus { max-height: 140px; }
}

/* ---------- Progreso ---------- */
.prog { margin: 4px 0 18px; text-align: center; }
.prog-t { font-size: 15px; color: var(--pizarra-2); margin: 0 0 10px; }
.prog-d { display: flex; align-items: center; justify-content: center; }
.dot { width: 26px; height: 26px; border-radius: 50%; border: 2px solid var(--borde); background: #fff;
       display: inline-flex; align-items: center; justify-content: center; flex: none; }
.dot.ok { background: var(--salvia); border-color: var(--salvia); }
.dot.act { width: 30px; height: 30px; border: 3px solid var(--malva-oscuro); background: #fff; }
.lin { width: 48px; height: 3px; background: var(--borde); flex: none; }
.lin.ok { background: var(--salvia); }
@media (max-width: 420px) { .lin { width: 30px; } }

/* ---------- Botones ---------- */
.stButton > button, .stDownloadButton > button {
  min-height: 52px; border-radius: 14px; font-size: 17px; font-weight: 600; width: 100%;
  border: 1.5px solid var(--salvia); background: #fff; color: var(--pizarra); box-shadow: none;
}
.stButton > button p, .stDownloadButton > button p { font-size: inherit; font-weight: inherit; color: inherit; margin: 0; }
button[kind="primary"], button[data-testid="stBaseButton-primary"] {
  background: var(--malva-oscuro) !important; color: #fff !important; border: 0 !important; font-weight: 700 !important;
  box-shadow: 0 8px 20px rgba(126,95,122,.30) !important;
}
button[kind="primary"]:hover, button[data-testid="stBaseButton-primary"]:hover {
  background: var(--malva-hover) !important; color: #fff !important; transform: translateY(-1px);
}
button:focus-visible { outline: 3px solid #7E5F7A !important; outline-offset: 2px !important; }
.st-key-comenzar button { width: auto; min-width: 200px; }
@media (max-width: 640px) { .st-key-comenzar button { width: 100%; } }
.st-key-sutil button, .st-key-sutil button[kind="secondary"] {
  border: 0 !important; background: transparent !important; box-shadow: none !important; min-height: 36px !important;
  font-size: 15px !important; font-weight: 500 !important; text-decoration: underline; color: var(--pizarra-2) !important;
}

/* Sí / No: anchos, siempre lado a lado, seleccionado en degradado salvia */
.st-key-yesno button, .st-key-yesno button[kind="secondary"] {
  min-height: 64px; border-radius: 16px; font-size: 18px; font-weight: 700;
  background: var(--salvia-tinte); border: 1.5px solid var(--salvia); color: var(--pizarra);
}
.st-key-yesno button:hover { background: #D8E8E5; }
.st-key-yesno button[kind="primary"], .st-key-yesno button[data-testid="stBaseButton-primary"] {
  background: linear-gradient(135deg, #4A7C7D, #3F6B6C) !important; color: #fff !important;
  box-shadow: 0 8px 20px rgba(74,124,125,.35) !important; transform: none;
}
.st-key-yesno [data-testid="stHorizontalBlock"], .st-key-nav [data-testid="stHorizontalBlock"] {
  flex-direction: row !important; flex-wrap: nowrap !important; gap: 12px !important;
}
.st-key-yesno [data-testid="stColumn"], .st-key-nav [data-testid="stColumn"],
.st-key-yesno [data-testid="column"], .st-key-nav [data-testid="column"] {
  min-width: 0 !important; width: auto !important; flex: 1 1 0 !important;
}

/* ---------- Expanders como tarjetas ---------- */
[data-testid="stExpander"] details { border: 1px solid var(--borde) !important; border-radius: 16px !important;
  background: #fff !important; box-shadow: 0 1px 2px rgba(45,55,72,.06), 0 6px 18px rgba(74,124,125,.08); }
[data-testid="stExpander"] summary { background: #fff !important; border-radius: 16px; font-weight: 600; color: var(--pizarra); }
[data-testid="stExpander"] summary svg { color: var(--salvia) !important; }
[data-testid="stExpander"] details > div { background: #fff; color: var(--pizarra-2); border-radius: 0 0 16px 16px; }
.st-key-ayuda summary p::before {
  content: "?"; display: inline-flex; align-items: center; justify-content: center; width: 22px; height: 22px;
  border-radius: 50%; background: var(--salvia); color: #fff; font-size: 14px; font-weight: 700; margin-right: 8px;
}
.st-key-ayuda [data-testid="stExpander"] details { box-shadow: none; border: 0 !important; }
.st-key-ayuda [data-testid="stExpander"] details > div p { font-size: 16px; }
[data-testid="stNumberInput"] div[data-baseweb="input"] { border: 1.5px solid var(--salvia); border-radius: 12px;
  min-height: 52px; background: #fff; }
[data-testid="stNumberInput"] input { font-size: 17px; color: var(--pizarra); }
[data-testid="stCheckbox"] label span { font-size: 16px; color: var(--pizarra); }

/* ---------- Resultado ---------- */
.dona { width: 100%; max-width: 200px; height: auto; display: block; margin: 0 auto; }
.nivel { display: inline-flex; align-items: center; gap: 10px; padding: 8px 14px; border-radius: 999px;
         border: 2px solid; color: var(--pizarra); font-weight: 700; font-size: 16px; }
.pts { display: inline-flex; gap: 5px; }
.pt { width: 10px; height: 10px; border-radius: 50%; border: 1.5px solid var(--malva-oscuro); display: inline-block; }
.pt.on { background: var(--malva-oscuro); }
.escala { margin: 18px 0 6px; }
.escala-seg { display: flex; gap: 4px; align-items: center; height: 24px; }
.escala-seg span { flex: 1; height: 14px; border-radius: 8px; display: block; }
.escala-seg span.act { height: 18px; transform: scale(1.15); border: 2px solid #fff;
                       box-shadow: 0 2px 8px rgba(45,55,72,.3); }
.escala-lab { display: grid; grid-template-columns: repeat(5, 1fr); gap: 4px; margin-top: 6px; }
.escala-lab span { font-size: 14.5px; color: var(--pizarra-2); text-align: center; white-space: nowrap; }
.escala-lab span:first-child { text-align: left; } .escala-lab span:last-child { text-align: right; }
.escala-lab span.act { color: var(--pizarra); font-weight: 700; overflow: visible; }
.micro { font-size: 15px; color: var(--pizarra-2); line-height: 1.55; margin: 8px 0 0; }
.factor { background: #fff; border: 1px solid var(--borde); border-radius: 16px; padding: 16px; height: 100%;
          box-shadow: 0 1px 2px rgba(45,55,72,.06), 0 6px 18px rgba(74,124,125,.08); }
.factor-t { font-weight: 600; color: var(--pizarra); font-size: 17px; margin: 0; }
.factor-p { font-weight: 700; color: var(--malva-oscuro); font-size: 16px; margin: 2px 0 8px; }
.factor-p.baja { color: var(--salvia-oscuro); }
.factor-b { height: 8px; border-radius: 8px; background: var(--salvia-tinte); overflow: hidden; margin-bottom: 10px; }
.factor-b span { display: block; height: 100%; border-radius: 8px; background: linear-gradient(90deg, #4A7C7D, #9C7A97); }
.factor-b span.baja { background: var(--salvia-claro); }
.factor-d { font-size: 14.5px; color: var(--pizarra-2); line-height: 1.5; margin: 0; }

/* ---------- ¿Y ahora qué? ---------- */
.ahora { display: flex; gap: 16px; align-items: center; }
.ahora-ico { width: 56px; height: 56px; border-radius: 50%; background: var(--salvia); color: #fff; display: flex;
             align-items: center; justify-content: center; flex: none; }
.ahora-et { font-size: 15px; color: var(--pizarra-2); margin: 0; }
.ahora-ti { font-size: 23px; font-weight: 700; color: var(--pizarra); line-height: 1.25; margin: 2px 0 0; }
@media (max-width: 640px) { .ahora-ti { font-size: 20px; } }

/* ---------- Aprende más ---------- */
.seccion { margin-top: 40px; }
.que-es { display: flex; gap: 14px; align-items: flex-start; }
.que-es-q { width: 36px; height: 36px; border-radius: 50%; background: var(--salvia); color: #fff; font-weight: 700;
            display: flex; align-items: center; justify-content: center; flex: none; font-size: 18px; }
.pill-tinte { display: inline-block; background: var(--salvia-tinte); color: var(--salvia-oscuro); font-weight: 600;
              font-size: 14.5px; padding: 6px 14px; border-radius: 999px; margin-top: 10px; }
.senales { display: grid; grid-template-columns: repeat(6, 1fr); gap: 12px; margin-top: 12px; }
.senal { grid-column: span 2; min-height: 64px; background: #fff; border: 1px solid var(--borde); border-radius: 16px;
         padding: 12px; display: flex; align-items: center; gap: 12px; font-size: 16px; font-weight: 500;
         box-shadow: 0 1px 2px rgba(45,55,72,.06), 0 6px 18px rgba(74,124,125,.08); }
.senal:nth-child(4) { grid-column: 2 / span 2; } .senal:nth-child(5) { grid-column: 4 / span 2; }
.senal-i { width: 40px; height: 40px; border-radius: 50%; background: var(--salvia-tinte); color: var(--salvia);
           display: flex; align-items: center; justify-content: center; flex: none; }
@media (max-width: 640px) {
  .senales { grid-template-columns: repeat(2, 1fr); }
  .senal, .senal:nth-child(4) { grid-column: auto; } .senal:nth-child(5) { grid-column: 1 / -1; }
}
.pasos { display: flex; gap: 16px; margin-top: 12px; }
.paso { flex: 1; position: relative; text-align: center; padding: 0 4px; }
.paso-n { width: 36px; height: 36px; border-radius: 50%; background: var(--salvia); color: #fff; font-weight: 700;
          display: flex; align-items: center; justify-content: center; margin: 0 auto 8px; position: relative; z-index: 1; }
.paso:not(:last-child)::after { content: ""; position: absolute; top: 18px; left: calc(50% + 26px);
                                right: calc(-50% + 26px); border-top: 2px dotted var(--salvia-claro); }
.paso b { display: block; font-size: 16px; margin-bottom: 2px; }
.paso span { font-size: 15px; color: var(--pizarra-2); line-height: 1.5; display: block; }
@media (max-width: 640px) {
  .pasos { flex-direction: column; gap: 18px; }
  .paso { text-align: left; padding-left: 52px; }
  .paso-n { position: absolute; left: 0; top: 0; margin: 0; }
  .paso:not(:last-child)::after { top: 40px; bottom: -22px; left: 17px; right: auto; border-top: 0;
                                  border-left: 2px dotted var(--salvia-claro); }
}
.fuentes { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-top: 12px; }
@media (max-width: 480px) { .fuentes { grid-template-columns: 1fr; } }
a.fuente { display: flex; gap: 12px; align-items: center; background: #fff; border: 1px solid var(--borde);
           border-radius: 16px; padding: 14px; text-decoration: none; color: var(--pizarra);
           box-shadow: 0 1px 2px rgba(45,55,72,.06), 0 6px 18px rgba(74,124,125,.08); transition: box-shadow .15s, border-color .15s; }
a.fuente:hover, a.fuente:focus-visible { border-color: var(--salvia); box-shadow: 0 2px 4px rgba(45,55,72,.08), 0 12px 28px rgba(74,124,125,.2); }
.fuente-i { width: 36px; height: 36px; border-radius: 50%; background: var(--salvia-tinte); color: var(--salvia);
            display: flex; align-items: center; justify-content: center; flex: none; }
.fuente-t { font-weight: 600; font-size: 15.5px; line-height: 1.3; display: block; }
.fuente-e { font-size: 14px; color: var(--pizarra-2); display: block; margin-top: 2px; }
.fuente-f { color: var(--salvia); margin-left: auto; flex: none; }
.sop-h2-ico { display: flex; align-items: center; gap: 10px; }
.sop-h2-ico .ico { color: var(--salvia); }
</style>
"""


def aviso(tipo, html, icono=None):
    icono = icono or {"info": "escudo", "precaucion": "info", "error": "info"}[tipo]
    color = {"info": SALVIA, "precaucion": PIZARRA, "error": PIZARRA}[tipo]
    st.markdown(h(f'<div class="aviso aviso-{tipo}" role="note">{ico(icono, 22, color)}<div>{html}</div></div>'),
                unsafe_allow_html=True)


AVISO_ETICO = ("Esta herramienta <strong>no es un diagnóstico médico</strong> y no reemplaza la "
               "valoración de un profesional de la salud. Tus respuestas no se guardan.")


@st.cache_resource
def _paquetes():
    corto = cargar_paquete(RUTA_CORTO)
    try:
        foliculo = cargar_paquete(RUTA_FOLICULO)
    except FileNotFoundError:
        foliculo = None
    return corto, foliculo


# ----------------------------------------------------------- estado
def iniciar_estado():
    ss = st.session_state
    ss.setdefault("vista", "estimacion")   # estimacion | aprende
    ss.setdefault("etapa", "bienvenida")   # bienvenida | preguntas | resultado
    ss.setdefault("paso", 0)               # 0..5
    ss.setdefault("resp", {})              # clave -> True/False
    ss.setdefault("sin_der", False)
    ss.setdefault("conteo", None)
    ss.setdefault("falta_msg", None)
    ss.setdefault("resultado", None)


def reiniciar():
    for k in ["etapa", "paso", "resp", "sin_der", "conteo", "falta_msg", "resultado", "sin_ovarios"]:
        st.session_state.pop(k, None)
    iniciar_estado()
    st.session_state.vista = "estimacion"


def ir(etapa=None, paso=None):
    if etapa is not None:
        st.session_state.etapa = etapa
    if paso is not None:
        st.session_state.paso = paso
    st.session_state.falta_msg = None


def ir_vista(vista):
    st.session_state.vista = vista


def responder(clave, valor):
    st.session_state.resp[clave] = valor


def _sync_conteo(clave):
    st.session_state.conteo = st.session_state.get(clave)


def _sync_sin_der():
    st.session_state.sin_der = st.session_state.get("w_sin_der", False)
    st.session_state.conteo = None  # el dato de un ovario no sirve como el del otro


# ----------------------------------------------------------- encabezado y pestañas
def encabezado():
    st.markdown(h(f"""
    <header class="sop-header"><div class="sop-header-in">{ico("brote", 32, "#fff")}
    <div><div class="sop-t1">Estimación de riesgo de SOP</div>
    <div class="sop-t2">Prototipo académico · Proyecto de grado, Universidad EAN</div></div></div></header>"""),
        unsafe_allow_html=True)
    with st.container(key="tabs"):
        c1, c2, _ = st.columns([1, 1, 2])
        with c1:
            st.button("Mi estimación", key="tab_est", on_click=ir_vista, args=("estimacion",),
                      type="primary" if st.session_state.vista == "estimacion" else "secondary")
        with c2:
            st.button("Aprende más", key="tab_apr", on_click=ir_vista, args=("aprende",),
                      type="primary" if st.session_state.vista == "aprende" else "secondary")


# ----------------------------------------------------------- 1. bienvenida
def pantalla_bienvenida():
    with st.container(key="tarjeta_bienv"):
        izq, der = st.columns([3, 2])
        with der:
            st.markdown(f"<div>{ilustracion_botanica()}</div>", unsafe_allow_html=True)
        with izq:
            st.markdown('<h1 class="sop-h1">Hola, qué bueno que estés aquí</h1>', unsafe_allow_html=True)
            st.markdown(
                "**¿Qué es el SOP?** El síndrome de ovario poliquístico es una condición hormonal "
                "frecuente: afecta a cerca de 1 de cada 10 mujeres y muchas veces se reconoce tarde.\n\n"
                "**¿Qué hace esta herramienta?** Con cinco preguntas sencillas (y una sexta opcional) "
                "estima qué tanto se parecen tus respuestas al patrón del SOP.\n\n"
                "**¿Cuánto tarda?** **6 preguntas, menos de 2 minutos.**"
            )
            st.markdown("**Antes de empezar**")
            st.markdown(h(f"""
            <ul class="lista-ico">
            <li>{ico("portapapeles")}<span>Son <strong>cinco preguntas obligatorias</strong> y <strong>una sexta opcional</strong> sobre una ecografía reciente.</span></li>
            <li>{ico("check_circulo")}<span>No hay respuestas buenas ni malas: elige la que más se parezca a tu caso.</span></li>
            <li>{ico("barras")}<span>Al final verás un porcentaje, un nivel y <strong>por qué</strong> salió ese resultado.</span></li>
            <li>{ico("escudo")}<span>El resultado es una estimación: <strong>no es un diagnóstico</strong> y no reemplaza a un profesional de la salud.</span></li>
            <li>{ico("candado")}<span>Tus respuestas <strong>no se guardan</strong>.</span></li>
            </ul>"""), unsafe_allow_html=True)
            with st.container(key="pill_sinov"):
                sin_ovarios = st.checkbox("No tengo ovarios (por cirugía u otra causa)", key="sin_ovarios")
            if sin_ovarios:
                aviso(
                    "precaucion",
                    "Esta herramienta estima el riesgo de SOP, una condición que depende de los ovarios y de la "
                    "ovulación, así que <strong>no aplica en tu caso</strong>. Si tienes dudas sobre tu salud "
                    "hormonal o metabólica, puedes consultar con ginecología o endocrinología.",
                )
            else:
                with st.container(key="comenzar"):
                    st.button("Comenzar →", type="primary", key="btn_comenzar", on_click=ir,
                              args=("preguntas", 0))


# ----------------------------------------------------------- 2. preguntas
def progreso_html(paso):
    resp = st.session_state.resp
    n_resp = sum(1 for q in PREGUNTAS_UI if resp.get(q["clave"]) is not None)
    partes = []
    for i, q in enumerate(PREGUNTAS_UI):
        contestada = resp.get(q["clave"]) is not None
        actual = i == paso
        estado = "pregunta actual" if actual else ("respondida" if contestada else "pendiente")
        cls = "act" if actual else ("ok" if contestada else "")
        marca = ico("check", 14, "#fff", 2.6) if (contestada and not actual) else ""
        partes.append(f'<span class="dot {cls}" role="img" aria-label="Pregunta {i + 1}, {estado}">{marca}</span>')
        if i < N_OBLIGATORIAS - 1:
            partes.append(f'<span class="lin {"ok" if contestada else ""}"></span>')
    return h(f'<div class="prog"><p class="prog-t">{n_resp} de {N_OBLIGATORIAS} preguntas obligatorias '
             f'respondidas</p><div class="prog-d">{"".join(partes)}</div></div>')


def _clave_tarjeta(paso):
    return "card_par" if paso % 2 == 0 else "card_impar"


def pantalla_pregunta_obligatoria(paso):
    ss = st.session_state
    q = PREGUNTAS_UI[paso]
    actual = ss.resp.get(q["clave"])

    st.markdown(progreso_html(paso), unsafe_allow_html=True)
    if ss.falta_msg:
        aviso("error", ss.falta_msg)

    with st.container(key=_clave_tarjeta(paso)):
        st.markdown(f'<span class="pill-ord">{ORDINALES[paso]} pregunta</span>', unsafe_allow_html=True)
        st.markdown(f'<h2 class="sop-h2">{q["titulo"]}</h2>', unsafe_allow_html=True)
        with st.container(key="yesno"):
            c1, c2 = st.columns(2)
            for col, etiqueta, valor in ((c1, q["si"], True), (c2, q["no"], False)):
                with col:
                    elegido = actual is not None and actual == valor
                    st.button(
                        ("✓ " if elegido else "") + etiqueta,
                        key=f"r_{q['clave']}_{int(valor)}",
                        type="primary" if elegido else "secondary",
                        on_click=responder, args=(q["clave"], valor),
                    )
        with st.container(key="ayuda"):
            with st.expander("¿Qué cuenta como…?"):
                st.write(q["ayuda"])
        with st.container(key="nav"):
            a, b = st.columns(2)
            with a:
                if paso > 0:
                    st.button("← Anterior", key="btn_ant", on_click=ir, kwargs=dict(paso=paso - 1))
            with b:
                st.button("Siguiente →", key="btn_sig", type="primary", on_click=ir, kwargs=dict(paso=paso + 1))
    aviso_etico_centrado()


def aviso_etico_centrado():
    st.markdown(h(f'<div class="aviso aviso-info aviso-centrado" role="note">{ico("escudo", 22, SALVIA)}'
                  f'<div>{AVISO_ETICO}</div></div>'), unsafe_allow_html=True)


def pantalla_pregunta_opcional(hay_foliculo):
    ss = st.session_state
    st.markdown(progreso_html(-1), unsafe_allow_html=True)
    if ss.falta_msg:
        aviso("error", ss.falta_msg)

    with st.container(key=_clave_tarjeta(N_OBLIGATORIAS)):
        st.markdown(f'<span class="pill-ord">{ORDINALES[N_OBLIGATORIAS]} pregunta</span>'
                    '<span class="pill-opc">Opcional</span>', unsafe_allow_html=True)
        st.markdown('<h2 class="sop-h2">¿Tienes el conteo folicular de una ecografía reciente?</h2>',
                    unsafe_allow_html=True)
        st.caption(
            "Si tienes este dato de una ecografía reciente, agregarlo ayuda a que la estimación sea más "
            "precisa. Si no lo tienes, puedes dejarla en blanco."
        )
        st.checkbox("No tengo ovario derecho", value=ss.sin_der, key="w_sin_der", on_change=_sync_sin_der)
        if ss.sin_der:
            aviso(
                "precaucion",
                "El modelo se entrenó con datos del ovario derecho. Si solo tienes el izquierdo, puedes "
                "usar ese conteo en su lugar: la estimación sigue siendo una aproximación, un poco menos "
                "precisa que con el dato exacto con el que se entrenó el modelo.",
            )
            etiqueta = "Conteo folicular (ovario izquierdo)"
        else:
            etiqueta = "Conteo folicular (ovario derecho)"
        clave_conteo = "w_conteo_izq" if ss.sin_der else "w_conteo_der"  # una clave por ovario
        st.number_input(
            etiqueta, min_value=0, max_value=40, value=ss.conteo, step=1,
            key=clave_conteo, on_change=_sync_conteo, args=(clave_conteo,),
        )
        with st.container(key="ayuda"):
            with st.expander("¿Qué cuenta como…?"):
                st.write(
                    "Es el número de folículos (pequeñas bolsitas donde maduran los óvulos) que aparece en el "
                    "informe de una ecografía pélvica o transvaginal para ese ovario. Si tu informe no lo "
                    "menciona, deja la casilla en blanco."
                )

        st.markdown("**Tus respuestas**")
        for i, q in enumerate(PREGUNTAS_UI):
            v = ss.resp.get(q["clave"])
            texto = "falta responder" if v is None else (q["si"] if v else q["no"])
            marca = "○" if v is None else "✓"
            st.markdown(f"{marca} {ORDINALES[i]}: {q['resumen']} · {texto}")

        with st.container(key="nav"):
            a, b = st.columns(2)
            with a:
                st.button("← Anterior", key="btn_ant6", on_click=ir, kwargs=dict(paso=N_OBLIGATORIAS - 1))
            with b:
                calcular = st.button("Calcular mi estimación", key="btn_calc", type="primary")
    aviso_etico_centrado()
    if calcular:
        calcular_resultado()


def calcular_resultado():
    ss = st.session_state
    corto, foliculo = _paquetes()
    faltan = [i for i, q in enumerate(PREGUNTAS_UI) if ss.resp.get(q["clave"]) is None]
    if faltan:
        ss.paso = faltan[0]
        ss.falta_msg = (f"<strong>Te falta responder {lista_ordinales(faltan)}.</strong> "
                        "Te llevamos a la primera que falta; la sexta es opcional y no hace falta para calcular.")
        st.rerun()
        return

    conteo = ss.conteo
    afinada = foliculo is not None and conteo is not None
    paquete = foliculo if afinada else corto
    r = {q["clave"]: bool(ss.resp[q["clave"]]) for q in PREGUNTAS_UI}
    if afinada:
        r[CLAVE_OPCIONAL] = conteo

    fila = construir_fila(paquete, r)
    pct = int(round(estimar_riesgo(paquete, fila) * 100))
    nombre, _color_antiguo = categoria(pct)
    ss.resultado = dict(
        pct=pct, nombre=nombre, afinada=afinada, conteo=conteo, usando_izquierdo=afinada and ss.sin_der,
        fuera=fuera_de_rango(paquete, fila),
        explicacion=construir_explicacion(paquete, fila),
    )
    ss.etapa = "resultado"
    ss.falta_msg = None
    st.rerun()


# ----------------------------------------------------------- 3. resultado
def pastilla_nivel(nombre, cat):
    puntos = "".join(f'<span class="pt{" on" if i < cat["nivel"] else ""}"></span>' for i in range(5))
    return h(f'<span class="nivel" style="background:{cat["fondo"]};border-color:{cat["borde"]}">'
             f'{ico(cat["icono"], 20, PIZARRA)}<span>Nivel {nombre}</span>'
             f'<span class="pts" role="img" aria-label="Nivel {cat["nivel"]} de 5">{puntos}</span></span>')


def escala_riesgo(nombre):
    idx = NOMBRES_NIVEL.index(nombre)
    segs = "".join(f'<span class="{"act" if i == idx else ""}" style="background:{c}"></span>'
                   for i, c in enumerate(COLORES_ESCALA))
    etiquetas = []
    for i in range(5):
        if i == idx:
            etiquetas.append(f'<span class="act">▲<br>{nombre}</span>')
        elif i == 0:
            etiquetas.append("<span>Bajo</span>")
        elif i == 4:
            etiquetas.append("<span>Alto</span>")
        else:
            etiquetas.append("<span></span>")
    return h(f'<div class="escala" role="img" aria-label="Escala de riesgo: nivel {nombre}">'
             f'<div class="escala-seg">{segs}</div><div class="escala-lab">{"".join(etiquetas)}</div></div>')


def tarjeta_factor(item, max_pts):
    pts = item["puntos"]
    ancho = max(6, min(100, abs(pts) / max_pts * 100)) if max_pts else 6
    if pts >= 0:
        linea = f'<p class="factor-p">▲ +{_puntos_txt(pts)}</p>'
        barra = f'<span style="width:{ancho:.0f}%"></span>'
    else:
        linea = f'<p class="factor-p baja">▼ bajó tu estimación en {_puntos_txt(pts)}</p>'
        barra = f'<span class="baja" style="width:{ancho:.0f}%"></span>'
    return h(f'<div class="factor"><p class="factor-t">{item["etiqueta"]}</p>{linea}'
             f'<div class="factor-b">{barra}</div><p class="factor-d">{item["razon"]}</p></div>')


def informe_en_pdf(res, resp):
    """Bytes del informe en PDF (se arma una sola vez por resultado). None si no se puede generar."""
    if "pdf" in res:
        return res["pdf"]
    try:
        from informe_pdf import generar_pdf
        expl = res["explicacion"]
        respuestas = []
        for q in PREGUNTAS_UI:
            v = resp.get(q["clave"])
            respuestas.append((q["resumen"], "Sin respuesta" if v is None else (q["si"] if v else q["no"]),
                               bool(v)))
        if res["afinada"]:
            n = int(res["conteo"])
            unidad = "1 folículo" if n == 1 else f"{n} folículos"
            if res["usando_izquierdo"]:
                texto = f"{unidad} (ovario izquierdo, usado como aproximación: menor precisión)"
            else:
                texto = f"{unidad} (ovario derecho)"
            respuestas.append(("Conteo folicular", texto, True))
        else:
            respuestas.append(("Conteo folicular", "No lo tenía", False))
        factores = [dict(etiqueta=i["etiqueta"], puntos=i["puntos"], razon=i["razon"]) for i in expl["items"]]
        res["pdf"] = generar_pdf(
            res["pct"], res["nombre"], res["afinada"], res["conteo"], res["usando_izquierdo"],
            factores, bool(expl["menores"]), respuestas,
        )
    except Exception:
        res["pdf"] = None
    return res["pdf"]


def pantalla_resultado():
    ss = st.session_state
    res = ss.resultado
    if res is None:
        ir("bienvenida", 0)
        st.rerun()
        return
    pct, nombre, expl = res["pct"], res["nombre"], res["explicacion"]
    cat = CATEGORIAS_UI[nombre]

    # A. cabecera
    linea = ("Estimación con seis preguntas (incluye conteo folicular)" if res["afinada"]
             else "Estimación con cinco preguntas")
    st.markdown(f'<div class="pill-centro"><span class="pill-fuerte">{linea}</span></div>'
                f'<h1 class="sop-h1 centro">{cat["frase"]}</h1>', unsafe_allow_html=True)

    # B. tarjeta principal
    with st.container(key="tarjeta_resultado"):
        c1, c2 = st.columns([1, 2])
        with c1:
            st.markdown(f"<div>{svg_dona(pct)}</div>", unsafe_allow_html=True)
        with c2:
            st.markdown(f"<div>{pastilla_nivel(nombre, cat)}</div>" + escala_riesgo(nombre),
                        unsafe_allow_html=True)
            st.markdown(
                '<p class="micro">Este porcentaje es una estimación del modelo con datos de otro país; no es '
                'la probabilidad real de que tengas SOP.</p>'
                f'<p class="micro"><strong>{cat["micro"]}</strong></p>', unsafe_allow_html=True)

    if res["fuera"]:
        aviso("precaucion",
              "Algunos de tus datos (" + ", ".join(res["fuera"]) + ") están fuera del rango de las mujeres "
              "con las que se entrenó el modelo. La estimación puede ser menos confiable.")

    # C. qué influyó
    st.markdown('<h2 class="sop-h2" style="margin-top:32px">Qué influyó en tu resultado</h2>',
                unsafe_allow_html=True)
    items = expl["items"]
    max_pts = max((abs(i["puntos"]) for i in items), default=0)
    for ini in range(0, len(items), 3):
        grupo = items[ini:ini + 3]
        cols = st.columns(3)
        for col, it in zip(cols, grupo):
            with col:
                st.markdown(tarjeta_factor(it, max_pts), unsafe_allow_html=True)
    if expl["menores"]:
        st.markdown("Otras respuestas casi no cambiaron el resultado.")
    with st.expander("Ver por qué salió este resultado"):
        st.caption("La cuenta parte de 0 %. Primero se suma el riesgo mínimo que da el modelo aun sin "
                   "ninguna señal y luego cada respuesta suma o resta puntos hasta llegar a tu estimación.")
        st.markdown(f"<div>{svg_cascada(expl)}</div>", unsafe_allow_html=True)

    with st.container(key="card_resumen"):
        st.markdown("**En resumen**")
        st.write(analisis_general(pct, expl))
        if res["afinada"] and res["usando_izquierdo"]:
            st.caption("Como incluiste el conteo folicular, tu estimación se apoya principalmente en ese dato. "
                       "Al ser el conteo del ovario izquierdo usado en lugar del derecho, esta parte del "
                       "resultado es una aproximación, no el dato exacto con el que se entrenó el modelo.")
        elif res["afinada"]:
            st.caption("Como incluiste el conteo folicular, tu estimación se apoya principalmente en ese dato, "
                       "que es más preciso que los síntomas reportados por sí solos.")
        else:
            st.caption("Esto describe asociaciones que encontró el modelo; no son causas médicas.")

    if pct >= PORCENTAJE_RECOMENDAR_CONSULTA:
        aviso("precaucion", "Te recomendamos consultar con un profesional de la salud para una valoración adecuada.")
    else:
        aviso("info", "Si tienes síntomas o dudas que te preocupen, consulta con un profesional de la salud.",
              "info")
    st.caption("Prototipo entrenado con datos de 541 mujeres de Kerala, India. "
               "No ha sido validado en población colombiana.")

    # D. ¿Y ahora qué?
    st.markdown('<h1 class="sop-h1 centro" style="margin-top:40px">¿Y ahora qué?</h1>', unsafe_allow_html=True)
    if pct >= PORCENTAJE_RECOMENDAR_CONSULTA:
        aviso("precaucion", "Te recomendamos consultar con un profesional de la salud. "
                            "Este resultado no es un diagnóstico.", "escudo")
    else:
        aviso("precaucion", "Si tienes síntomas o dudas, consulta con un profesional de la salud. "
                            "Este resultado no es un diagnóstico.", "escudo")

    tarjetas = [
        ("estetoscopio", "A quién consultar", "Ginecología o endocrinología",
         "Ginecología y endocrinología son las especialidades que más atienden estas inquietudes. "
         "Puedes empezar por la que te quede más accesible."),
        ("telefono", "Cómo pedir la cita por tu EPS", "Medicina general → remisión",
         "Pide una cita de medicina general (por la app, la línea telefónica o la sede de tu EPS), cuéntale "
         "tus síntomas y pregunta por la remisión a ginecología o endocrinología. Si eres menor de edad, "
         "puedes ir acompañada de un adulto de confianza."),
        ("portapapeles", "Qué llevar", "Fechas de ciclos, peso, fotos de síntomas",
         "- Las fechas de tus últimos ciclos (idealmente de los últimos meses).\n"
         "- Tu peso aproximado y si ha cambiado.\n"
         "- Notas o fotos de los síntomas que te preocupan (piel, vello, acné).\n"
         "- Ecografías o exámenes anteriores y los medicamentos que tomas.\n\n"
         "**Qué exámenes suelen pedir.** Según cada caso, el equipo médico puede pedir exámenes de sangre y "
         "una ecografía pélvica. Es el profesional quien decide cuáles."),
    ]
    for n, (icono, etiqueta, titular, detalle) in enumerate(tarjetas):
        with st.container(key=f"ahora_{n}"):
            st.markdown(h(f'<div class="ahora"><div class="ahora-ico">{ico(icono, 28, "#fff")}</div>'
                          f'<div><p class="ahora-et">{etiqueta}</p><p class="ahora-ti">{titular}</p></div></div>'),
                        unsafe_allow_html=True)
            with st.expander("Ver detalle"):
                st.markdown(detalle)
        st.markdown('<div style="height:8px"></div>', unsafe_allow_html=True)

    pdf = informe_en_pdf(res, ss.resp)
    a, b = st.columns(2)
    with a:
        if pdf is not None:
            st.download_button(
                "Descargar informe en PDF", data=pdf,
                file_name=f"informe_estimacion_sop_{date.today().isoformat()}.pdf",
                mime="application/pdf", key="btn_pdf", type="primary",
            )
        else:  # sin reportlab o sin poder generarlo: el .txt queda como principal
            st.download_button(
                "Descargar resumen en texto (.txt)", data=texto_resumen(res, ss.resp),
                file_name="resumen_estimacion_sop.txt", mime="text/plain", key="btn_descarga_txt0",
                type="primary",
            )
    with b:
        st.button("Volver a empezar", key="btn_reiniciar", on_click=reiniciar)
    if pdf is not None:
        st.download_button(
            "Descargar versión en texto (.txt)", data=texto_resumen(res, ss.resp),
            file_name="resumen_estimacion_sop.txt", mime="text/plain", key="btn_descarga_txt",
        )
    st.caption("El informe se genera en este momento; no se guarda en ningún servidor.")
    with st.container(key="sutil"):
        x, y = st.columns(2)
        with x:
            st.button("Cambiar mis respuestas", key="btn_cambiar", on_click=ir, args=("preguntas", 0))
        with y:
            st.button("Quiero aprender más sobre el SOP →", key="btn_aprende", on_click=ir_vista, args=("aprende",))


# ----------------------------------------------------------- Aprende más
# URLs: ninguna se pudo abrir desde el entorno de desarrollo. [verificar] todas antes de publicar.
FUENTES = [
    ("Organización Mundial de la Salud (OMS): Síndrome del ovario poliquístico (hoja informativa)",
     "https://www.who.int/news-room/fact-sheets/detail/polycystic-ovary-syndrome",
     "Hoja informativa"),                                                                       # [verificar]
    ("Teede HJ et al. (2023). Recomendaciones de la guía internacional basada en la evidencia para el "
     "SOP. Human Reproduction",
     "https://doi.org/10.1093/humrep/dead156", "Guía basada en evidencia"),                      # [verificar]
    ("MedlinePlus (en español): Síndrome de ovario poliquístico",
     "https://medlineplus.gov/spanish/polycysticovarysyndrome.html",
     "Información para pacientes"),                                                             # [verificar]
    ("Ministerio de Salud y Protección Social de Colombia", "https://www.minsalud.gov.co",
     "Colombia"),                                                                               # [verificar]
    ("Federación Colombiana de Obstetricia y Ginecología (FECOLSOG)", "https://fecolsog.org",
     "Ginecología · Colombia"),                                                                 # [verificar]
    ("Asociación Colombiana de Endocrinología, Diabetes y Metabolismo", "https://www.endocrino.org.co",
     "Endocrinología · Colombia"),                                                              # [verificar]
]

SENALES = [
    ("ciclo", "Ciclos menstruales irregulares o que tardan en llegar"),
    ("brillo", "Acné que persiste"),
    ("ondas", "Más vello grueso en rostro, pecho o espalda"),
    ("gota", "Zonas de piel oscurecida (cuello, axilas, ingles)"),
    ("balanza", "Dificultad para controlar el peso"),
]


def pestana_aprende_mas():
    # 1. ¿Qué es el SOP?
    with st.container(key="card_ayuda"):
        st.markdown(h("""
        <div class="que-es"><div class="que-es-q" aria-hidden="true">?</div><div>
        <h2 class="sop-h2" style="margin-top:0">¿Qué es el SOP?</h2>
        <p style="margin:0">El síndrome de ovario poliquístico (SOP) es una condición en la que las hormonas del
        cuerpo funcionan de una forma distinta. Por eso los ciclos pueden volverse irregulares y pueden aparecer
        señales como acné, más vello del habitual o cambios en la piel. Es frecuente: afecta a cerca de 1 de cada
        10 mujeres (entre 10 % y 13 % según la guía internacional de 2023), y como cada mujer lo vive distinto,
        a veces tarda en reconocerse.</p>
        <span class="pill-tinte">Afecta a cerca de 1 de cada 10 mujeres</span></div></div>"""),
            unsafe_allow_html=True)

    # 2. Señales
    celdas = "".join(f'<div class="senal"><span class="senal-i">{ico(i, 22)}</span><span>{t}</span></div>'
                     for i, t in SENALES)
    st.markdown(f'<div class="seccion"><h2 class="sop-h2" style="margin:0">Señales que suelen mencionarse</h2>'
                f'<div class="senales">{celdas}</div></div>', unsafe_allow_html=True)

    # 3. Aviso
    aviso("precaucion", "Tener una de estas señales no significa tener SOP: todas pueden tener muchas otras causas.")

    # 4. Mitos
    st.markdown('<h2 class="sop-h2" style="margin-top:40px">Mitos comunes</h2>', unsafe_allow_html=True)
    with st.container(key="mitos"):
        with st.expander("“SOP significa tener quistes en los ovarios”"):
            st.write("El nombre confunde. Lo que se ve en la ecografía suelen ser folículos pequeños, "
                     "y no todas las mujeres con SOP los presentan.")
        with st.expander("“Solo les da a mujeres con sobrepeso”"):
            st.write("No. El SOP puede presentarse con cualquier peso.")
        with st.expander("“Con SOP no se puede tener hijos”"):
            st.write("Muchas mujeres con SOP logran un embarazo, a veces con acompañamiento médico. "
                     "Si te preocupa, conversa con ginecología.")

    # 5. Dónde acudir
    st.markdown(h("""
    <div class="seccion"><h2 class="sop-h2" style="margin:0">Dónde acudir en Colombia</h2>
    <div class="pasos">
    <div class="paso"><div class="paso-n">1</div><b>Primer paso</b><span>Medicina general en tu EPS, que puede remitirte a una especialidad.</span></div>
    <div class="paso"><div class="paso-n">2</div><b>Especialidades</b><span>Ginecología y endocrinología.</span></div>
    <div class="paso"><div class="paso-n">3</div><b>Instituciones de referencia</b><span>Ministerio de Salud y Protección Social, Federación Colombiana de Obstetricia y Ginecología y Asociación Colombiana de Endocrinología, Diabetes y Metabolismo (enlaces abajo).</span></div>
    </div></div>"""), unsafe_allow_html=True)

    # 6. Fuentes
    tarjetas = "".join(
        f'<a class="fuente" href="{url}" target="_blank" rel="noopener noreferrer">'
        f'<span class="fuente-i">{ico("libro", 20)}</span>'
        f'<span><span class="fuente-t">{nombre}</span><span class="fuente-e">{etiqueta}</span></span>'
        f'<span class="fuente-f">{ico("flecha_ne", 20)}</span></a>'
        for nombre, url, etiqueta in FUENTES)
    st.markdown(h(f'<div class="seccion"><h2 class="sop-h2 sop-h2-ico" style="margin:0">'
                  f'{ico("escudo_check", 26)}Fuentes confiables</h2><div class="fuentes">{tarjetas}</div></div>'),
                unsafe_allow_html=True)

    # 7. Aviso ético
    st.markdown('<div style="height:28px"></div>', unsafe_allow_html=True)
    aviso("info", AVISO_ETICO)

    # 8. Volver
    _, centro, _ = st.columns([1, 2, 1])
    with centro:
        st.button("← Volver a mi estimación", key="btn_volver", on_click=ir_vista, args=("estimacion",))


# ----------------------------------------------------------- principal
def main():
    st.set_page_config(page_title="Estimación de riesgo de SOP", page_icon="🩺", layout="centered")
    st.markdown(CSS, unsafe_allow_html=True)
    iniciar_estado()
    _corto, foliculo = _paquetes()
    encabezado()

    if st.session_state.vista == "aprende":
        pestana_aprende_mas()
        return
    etapa = st.session_state.etapa
    if etapa == "bienvenida":
        pantalla_bienvenida()
    elif etapa == "preguntas":
        paso = min(max(st.session_state.paso, 0), N_OBLIGATORIAS)
        if paso < N_OBLIGATORIAS:
            pantalla_pregunta_obligatoria(paso)
        else:
            pantalla_pregunta_opcional(foliculo is not None)
    else:
        pantalla_resultado()


if __name__ == "__main__":
    main()
