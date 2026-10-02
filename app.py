# =====================================================================
# Prototipo: estimación de riesgo de SOP (proyecto de grado, EAN)
# Recolección progresiva:
#   - Paso 1 (obligatorio): 5 preguntas no invasivas -> modelo_sop_corto.pkl
#   - Paso 2 (opcional):    conteo folicular (ovario derecho), si la
#                           usuaria tiene una ecografía reciente ->
#                           modelo_sop_foliculo.pkl
# Los tres modelos (corto, 14 preguntas y folículo) son regresión
# logística calibrada, entrenada con el dataset de Kottarathil
# (541 mujeres de Kerala, India). Esta versión usa corto + folículo,
# porque una sola pregunta de ecografía supera a las 9 preguntas no
# invasivas adicionales que probamos antes (ver notebook, Sección 8).
# Ejecutar con:  streamlit run app.py
# Archivos necesarios en la misma carpeta: modelo_sop_corto.pkl y
# modelo_sop_foliculo.pkl
# =====================================================================

# ============================ NÚCLEO (lógica) ========================
import numpy as np
import pandas as pd
import joblib

RUTA_CORTO = "modelo_sop_corto.pkl"
RUTA_FOLICULO = "modelo_sop_foliculo.pkl"

# Codificación tal como viene en el dataset de entrenamiento:
#   Cycle(R/I): 2 = regular, 4 = irregular
#   Variables Y/N: 1 = Sí, 0 = No
#   Follicle No. (R): conteo directo de folículos, mismo número que
#   reportaría una ecografía (sin conversión de unidades).
CICLO_REGULAR, CICLO_IRREGULAR = 2, 4

# Las 5 preguntas básicas, en el mismo orden que usa modelo_sop_corto.pkl
PREGUNTAS = {
    "Piel oscurecida": "piel",
    "Ciclo regular o irregular": "ciclo_irregular",
    "Aumento de peso": "aumento_peso",
    "Crecimiento de vello": "vello",
    "Acné": "acne",
}
PREGUNTA_OPCIONAL = "Conteo folicular (ovario derecho)"
CLAVE_OPCIONAL = "conteo_folicular"

GRUPOS = {
    "Oscurecimiento de la piel": ["Skin darkening (Y/N)"],
    "Ciclo menstrual": ["Cycle(R/I)"],
    "Aumento de peso": ["Weight gain(Y/N)"],
    "Crecimiento de vello": ["hair growth(Y/N)"],
    "Acné": ["Pimples(Y/N)"],
    "Conteo folicular": ["Follicle No. (R)"],
}
UMBRAL_APORTE = 0.10

CATEGORIAS = [
    (20, "Bajo", "#2e7d32"),
    (40, "Medio-bajo", "#7cb342"),
    (60, "Medio", "#f9a825"),
    (80, "Medio-alto", "#ef6c00"),
    (100, "Alto", "#c62828"),
]
PORCENTAJE_RECOMENDAR_CONSULTA = 41


def cargar_paquete(ruta):
    return joblib.load(ruta)


def valores_crudos(paquete):
    """Dataset de entrenamiento en unidades originales."""
    scaler = paquete["pipeline_base"].named_steps["scaler"]
    fondo = paquete["fondo_shap"]
    return pd.DataFrame(fondo.values * scaler.scale_ + scaler.mean_, columns=fondo.columns)


def rangos_entrenamiento(paquete):
    crudo = valores_crudos(paquete)
    return {c: (crudo[c].min(), crudo[c].max()) for c in crudo.columns}


def construir_fila(paquete, r):
    """Arma la fila del modelo con las respuestas disponibles en r."""
    f = {
        "Skin darkening (Y/N)": int(r["piel"]),
        "Cycle(R/I)": CICLO_IRREGULAR if r["ciclo_irregular"] else CICLO_REGULAR,
        "Weight gain(Y/N)": int(r["aumento_peso"]),
        "hair growth(Y/N)": int(r["vello"]),
        "Pimples(Y/N)": int(r["acne"]),
    }
    if "conteo_folicular" in r:
        f["Follicle No. (R)"] = r["conteo_folicular"]
    return pd.DataFrame([f])[paquete["columnas"]]


def estimar_riesgo(paquete, fila):
    """Probabilidad calibrada de SOP (0 a 1)."""
    return float(paquete["modelo_calibrado"].predict_proba(fila)[0, 1])


def aportes(paquete, fila):
    """
    Valores SHAP de la regresión logística. En un modelo lineal, el valor SHAP
    exacto de cada variable es coeficiente * (valor estandarizado - promedio
    del fondo), que es lo que calcula shap.LinearExplainer.
    """
    pipe = paquete["pipeline_base"]
    x = pipe.named_steps["scaler"].transform(fila)[0]
    promedio = paquete["fondo_shap"].mean(axis=0).values
    phi = pipe.named_steps["modelo"].coef_[0] * (x - promedio)
    return pd.Series(phi, index=paquete["columnas"])


def agrupar(phi, paquete):
    cols = set(paquete["columnas"])
    return pd.Series({g: phi[[c for c in cs if c in cols]].sum()
                      for g, cs in GRUPOS.items() if any(c in cols for c in cs)})


def fuera_de_rango(paquete, fila):
    avisos = []
    for col, (lo, hi) in rangos_entrenamiento(paquete).items():
        v = float(fila[col].iloc[0])
        if v < lo - 1e-9 or v > hi + 1e-9:
            avisos.append(col)
    return avisos


def categoria(pct):
    for limite, nombre, color in CATEGORIAS:
        if pct <= limite:
            return nombre, color
    return CATEGORIAS[-1][1], CATEGORIAS[-1][2]


def frase_respuesta(grupo, r):
    """Describe la respuesta de la usuaria en ese grupo, sin lenguaje causal."""
    si = lambda x, a, b: a if x else b
    frases = {
        "Oscurecimiento de la piel": lambda: si(r["piel"], "tener", "no tener") + " oscurecimiento de la piel",
        "Ciclo menstrual": lambda: "tener ciclos " + si(r["ciclo_irregular"], "irregulares", "regulares"),
        "Aumento de peso": lambda: si(r["aumento_peso"], "haber notado", "no haber notado") + " aumento de peso",
        "Crecimiento de vello": lambda: si(r["vello"], "tener", "no tener") + " crecimiento excesivo de vello",
        "Acné": lambda: si(r["acne"], "tener", "no tener") + " acné persistente",
        "Conteo folicular": lambda: "el conteo folicular que reportaste en tu ecografía",
    }
    return frases[grupo]()


def unir(items):
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " y " + items[-1]


def explicar(grupos_phi, r):
    suben = grupos_phi[grupos_phi >= UMBRAL_APORTE].sort_values(ascending=False).head(3)
    bajan = grupos_phi[grupos_phi <= -UMBRAL_APORTE].sort_values().head(3)
    partes = []
    if len(suben):
        partes.append("Lo que más aumentó tu estimación: "
                      + unir([frase_respuesta(k, r) for k in suben.index]) + ".")
    if len(bajan):
        partes.append("Lo que más la disminuyó: "
                      + unir([frase_respuesta(k, r) for k in bajan.index]) + ".")
    if not partes:
        partes.append("Ninguna de tus respuestas tuvo un peso destacado por sí sola.")
    return " ".join(partes)


def svg_dona(pct, color):
    import math
    radio = 54
    largo = 2 * math.pi * radio
    trazo = largo * pct / 100
    return f"""
    <div style="display:flex;justify-content:center">
    <svg width="220" height="220" viewBox="0 0 140 140">
      <circle cx="70" cy="70" r="{radio}" fill="none" stroke="#e6e6e6" stroke-width="14"/>
      <circle cx="70" cy="70" r="{radio}" fill="none" stroke="{color}" stroke-width="14"
              stroke-dasharray="{trazo:.1f} {largo:.1f}" stroke-linecap="round"
              transform="rotate(-90 70 70)"/>
      <text x="70" y="79" text-anchor="middle" font-size="28" font-weight="700"
            font-family="sans-serif" fill="#222">{pct}%</text>
    </svg></div>"""


# ============================ INTERFAZ (Streamlit) ===================
import streamlit as st
import streamlit.components.v1 as components


@st.cache_resource
def _paquetes():
    corto = cargar_paquete(RUTA_CORTO)
    try:
        foliculo = cargar_paquete(RUTA_FOLICULO)
    except FileNotFoundError:
        foliculo = None
    return corto, foliculo


def _si_no(etiqueta, clave):
    resp = st.radio(etiqueta, ["Sí", "No"], index=None, horizontal=True, key=clave)
    return None if resp is None else (resp == "Sí")


def pedir_basica(pregunta):
    clave = "q_" + PREGUNTAS[pregunta]
    textos = {
        "Piel oscurecida": "¿Tienes zonas de piel oscurecida (cuello, axilas o ingles)?",
        "Ciclo regular o irregular": None,  # caso especial, radio de dos opciones con texto propio
        "Aumento de peso": "¿Has notado aumento de peso que te cuesta controlar?",
        "Crecimiento de vello": "¿Tienes crecimiento excesivo de vello (rostro, pecho o espalda)?",
        "Acné": "¿Tienes acné persistente?",
    }
    if pregunta == "Ciclo regular o irregular":
        resp = st.radio("Tus ciclos menstruales son:", ["Regulares", "Irregulares"],
                        index=None, horizontal=True, key=clave)
        return None if resp is None else (resp == "Irregulares")
    return _si_no(textos[pregunta], clave)


def main():
    st.set_page_config(page_title="Estimación de riesgo de SOP", page_icon="🩺", layout="centered")
    corto, foliculo = _paquetes()

    st.title("Estimación de riesgo de SOP")
    st.caption("Prototipo académico · Proyecto de grado, Universidad EAN")
    st.info(
        "Esta herramienta estima un nivel de riesgo a partir de preguntas sencillas. "
        "**No es un diagnóstico médico** y no reemplaza la valoración de un profesional de la salud. "
        "Tus respuestas no se guardan."
    )

    respuestas = {}
    with st.form("formulario"):
        st.subheader("Paso 1: 5 preguntas básicas")
        for p in PREGUNTAS:
            respuestas[p] = pedir_basica(p)

        conteo_folicular = None
        usando_izquierdo = False
        if foliculo is not None:
            with st.expander("Paso 2 (opcional): ¿tienes una ecografía reciente?"):
                st.caption(
                    "Si tienes el conteo de folículos de una ecografía reciente, agrégalo aquí. "
                    "Es un solo dato, pero mejora bastante la precisión de la estimación."
                )
                sin_ovario_derecho = st.checkbox(
                    "No tengo ovario derecho", key="q_sin_ovario_derecho"
                )
                if not sin_ovario_derecho:
                    conteo_folicular = st.number_input(
                        PREGUNTA_OPCIONAL, min_value=0, max_value=40, value=None, step=1,
                        key="q_conteo_folicular",
                    )
                else:
                    st.caption(
                        "El modelo se entrenó con datos del ovario derecho. Si solo tienes el "
                        "izquierdo, puedes usar ese conteo en su lugar: la estimación sigue siendo "
                        "una aproximación, un poco menos precisa que si fuera el dato exacto con el "
                        "que se entrenó el modelo."
                    )
                    conteo_folicular = st.number_input(
                        "Conteo folicular (ovario izquierdo)", min_value=0, max_value=40,
                        value=None, step=1, key="q_conteo_folicular_izq",
                    )
                    usando_izquierdo = conteo_folicular is not None

        enviado = st.form_submit_button("Calcular mi estimación")

    if not enviado:
        return

    if any(respuestas[p] is None for p in PREGUNTAS):
        st.error("Por favor responde las preguntas básicas del Paso 1 para calcular la estimación.")
        return

    afinada = foliculo is not None and conteo_folicular is not None
    paquete = foliculo if afinada else corto
    r = {PREGUNTAS[p]: respuestas[p] for p in PREGUNTAS}
    if afinada:
        r[CLAVE_OPCIONAL] = conteo_folicular

    fila = construir_fila(paquete, r)
    prob = estimar_riesgo(paquete, fila)
    pct = int(round(prob * 100))
    nombre, color = categoria(pct)

    st.divider()
    st.subheader("Tu resultado")
    st.caption("Estimación afinada con el conteo folicular" if afinada
               else "Estimación básica con 5 preguntas")
    components.html(svg_dona(pct, color), height=240)
    st.markdown(f"<h3 style='text-align:center;color:{color}'>Riesgo estimado: {nombre}</h3>",
                unsafe_allow_html=True)

    fuera = fuera_de_rango(paquete, fila)
    if fuera:
        st.warning("Algunos de tus datos (" + ", ".join(fuera) + ") están fuera del rango de las "
                   "mujeres con las que se entrenó el modelo. La estimación puede ser menos confiable.")

    phi = aportes(paquete, fila)
    grupos_phi = agrupar(phi, paquete)
    st.write(explicar(grupos_phi, r))
    if afinada and usando_izquierdo:
        st.caption("Como incluiste el conteo folicular, tu estimación se apoya principalmente en ese dato. "
                   "Al ser el conteo del ovario izquierdo usado en lugar del derecho, esta parte del "
                   "resultado es una aproximación, no el dato exacto con el que se entrenó el modelo.")
    elif afinada:
        st.caption("Como incluiste el conteo folicular, tu estimación se apoya principalmente en ese dato, "
                   "que es más preciso que los síntomas reportados por sí solos.")
    else:
        st.caption("Esto describe cómo el modelo usó tus respuestas; no son causas médicas.")

    if pct >= PORCENTAJE_RECOMENDAR_CONSULTA:
        st.warning("Te recomendamos consultar con un profesional de la salud para una valoración adecuada.")
    else:
        st.success("Si tienes síntomas o dudas que te preocupen, consulta con un profesional de la salud.")

    with st.expander("¿Cómo se calculó? (detalle técnico)"):
        st.write("Aporte de cada grupo de respuestas a la estimación (valores SHAP, en escala logit). "
                 "Positivo: aumenta la estimación; negativo: la disminuye.")
        st.bar_chart(grupos_phi.round(3))

    st.caption("Prototipo entrenado con datos de 541 mujeres de Kerala, India. "
               "No ha sido validado en población colombiana.")


main()
