# =====================================================================
# Prototipo: estimación de riesgo de SOP (proyecto de grado, EAN)
# Recolección progresiva:
#   - Paso 1 (obligatorio): 5 preguntas -> modelo corto (modelo_sop_corto.pkl)
#   - Paso 2 (opcional):    las otras 9 preguntas -> modelo largo (modelo_sop.pkl),
#                           solo si se responden todas.
# Ambos son regresión logística calibrada, entrenada con el dataset de
# Kottarathil (541 mujeres de Kerala, India).
# Ejecutar con:  streamlit run app.py
# Archivos necesarios en la misma carpeta: modelo_sop_corto.pkl y modelo_sop.pkl
# =====================================================================

# ============================ NÚCLEO (lógica) ========================
import numpy as np
import pandas as pd
import joblib

RUTA_CORTO = "modelo_sop_corto.pkl"
RUTA_LARGO = "modelo_sop.pkl"

# Codificación tal como viene en el dataset de entrenamiento:
#   Cycle(R/I): 2 = regular, 4 = irregular
#   Variables Y/N: 1 = Sí, 0 = No
#   Waist(inch) y Hip(inch) están en PULGADAS; peso en kg; estatura en cm
#   Cycle length(days) toma valores de 2 a 12 (mediana 5): son los días de
#   sangrado de la menstruación, no la duración total del ciclo.
CICLO_REGULAR, CICLO_IRREGULAR = 2, 4
CM_POR_PULGADA = 2.54

RANGOS_DURACION = {
    "1 a 3 días": (0, 3),
    "4 a 5 días": (4, 5),
    "6 a 7 días": (6, 7),
    "8 días o más": (8, 99),
}

# Las 14 preguntas: nombre -> clave interna, en el orden en que se muestran.
PREGUNTAS = {
    "Edad": "edad",
    "Peso": "peso",
    "Estatura": "estatura",
    "Cintura": "cintura",
    "Cadera": "cadera",
    "Ciclo regular o irregular": "ciclo_irregular",
    "Días de sangrado": "duracion",
    "Aumento de peso": "aumento_peso",
    "Crecimiento de vello": "vello",
    "Piel oscurecida": "piel",
    "Caída de cabello": "cabello",
    "Acné": "acne",
    "Comida rápida": "comida_rapida",
    "Ejercicio": "ejercicio",
}

# Variables muy correlacionadas (peso e IMC, r = 0.90) se suman en un solo
# grupo, porque sus aportes individuales no se pueden leer por separado.
GRUPOS = {
    "Ciclo menstrual": ["Cycle(R/I)"],
    "Duración de la menstruación": ["Cycle length(days)"],
    "Aumento de peso": ["Weight gain(Y/N)"],
    "Crecimiento de vello": ["hair growth(Y/N)"],
    "Oscurecimiento de la piel": ["Skin darkening (Y/N)"],
    "Caída de cabello": ["Hair loss(Y/N)"],
    "Acné": ["Pimples(Y/N)"],
    "Medidas corporales": ["Weight (Kg)", "Height(Cm)", "BMI", "Waist(inch)",
                           "Hip(inch)", "Waist:Hip Ratio"],
    "Edad": ["Age (yrs)"],
    "Hábitos": ["Fast food (Y/N)", "Reg.Exercise(Y/N)"],
}
UMBRAL_APORTE = 0.10
# Entran al cálculo pero no se mencionan en el texto: su efecto en el modelo
# largo va en contra de lo esperable (caída de cabello) o refleja asociaciones
# indirectas de los datos (hábitos).
NO_MENCIONAR = ["Hábitos", "Caída de cabello"]

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


def valor_por_rango(paquete_largo):
    """Valor que se le asigna a cada rango de días de sangrado (mediana observada)."""
    dias = valores_crudos(paquete_largo)["Cycle length(days)"].round()
    mapa = {}
    for nombre, (lo, hi) in RANGOS_DURACION.items():
        en_rango = dias[(dias >= lo) & (dias <= hi)]
        mapa[nombre] = float(en_rango.median()) if len(en_rango) else float((lo + min(hi, lo + 4)) / 2)
    return mapa


def construir_fila(paquete, r, duraciones=None):
    """Arma la fila del modelo con las respuestas disponibles en r."""
    f = {}
    if "edad" in r:
        f["Age (yrs)"] = r["edad"]
    if "peso" in r:
        f["Weight (Kg)"] = r["peso"]
    if "estatura" in r:
        f["Height(Cm)"] = r["estatura"]
    if "peso" in r and "estatura" in r:
        f["BMI"] = r["peso"] / (r["estatura"] / 100) ** 2
    if "cintura" in r:
        f["Waist(inch)"] = r["cintura"] / CM_POR_PULGADA
    if "cadera" in r:
        f["Hip(inch)"] = r["cadera"] / CM_POR_PULGADA
    if "cintura" in r and "cadera" in r:
        f["Waist:Hip Ratio"] = r["cintura"] / r["cadera"]
    if "ciclo_irregular" in r:
        f["Cycle(R/I)"] = CICLO_IRREGULAR if r["ciclo_irregular"] else CICLO_REGULAR
    if "duracion" in r:
        f["Cycle length(days)"] = duraciones[r["duracion"]]
    for clave, col in [("aumento_peso", "Weight gain(Y/N)"), ("vello", "hair growth(Y/N)"),
                       ("piel", "Skin darkening (Y/N)"), ("cabello", "Hair loss(Y/N)"),
                       ("acne", "Pimples(Y/N)"), ("comida_rapida", "Fast food (Y/N)"),
                       ("ejercicio", "Reg.Exercise(Y/N)")]:
        if clave in r:
            f[col] = int(r[clave])
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
        if col in ("Age (yrs)", "Weight (Kg)", "Height(Cm)", "BMI", "Waist(inch)", "Hip(inch)"):
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
        "Ciclo menstrual": lambda: "tener ciclos " + si(r["ciclo_irregular"], "irregulares", "regulares"),
        "Duración de la menstruación": lambda: "una menstruación de " + r["duracion"],
        "Aumento de peso": lambda: si(r["aumento_peso"], "haber notado", "no haber notado") + " aumento de peso",
        "Crecimiento de vello": lambda: si(r["vello"], "tener", "no tener") + " crecimiento excesivo de vello",
        "Oscurecimiento de la piel": lambda: si(r["piel"], "tener", "no tener") + " oscurecimiento de la piel",
        "Acné": lambda: si(r["acne"], "tener", "no tener") + " acné persistente",
        "Medidas corporales": lambda: "tus medidas corporales (peso, estatura, cintura y cadera)",
        "Edad": lambda: "tu edad",
    }
    return frases[grupo]()


def unir(items):
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " y " + items[-1]


def explicar(grupos_phi, r):
    g = grupos_phi.drop(NO_MENCIONAR, errors="ignore")
    suben = g[g >= UMBRAL_APORTE].sort_values(ascending=False).head(3)
    bajan = g[g <= -UMBRAL_APORTE].sort_values().head(3)
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
        largo = cargar_paquete(RUTA_LARGO)
    except FileNotFoundError:
        largo = None
    return corto, largo


def _si_no(etiqueta, clave):
    resp = st.radio(etiqueta, ["Sí", "No"], index=None, horizontal=True, key=clave)
    return None if resp is None else (resp == "Sí")


def pedir(pregunta):
    """Dibuja el campo de una pregunta. Devuelve la respuesta, o None si está sin responder."""
    clave = "q_" + PREGUNTAS[pregunta]
    if pregunta == "Edad":
        return st.number_input("Edad (años)", min_value=15, max_value=60, value=None, step=1, key=clave)
    if pregunta == "Peso":
        return st.number_input("Peso (kg)", min_value=30, max_value=200, value=None, step=1, key=clave)
    if pregunta == "Estatura":
        return st.number_input("Estatura (cm)", min_value=120, max_value=210, value=None, step=1, key=clave)
    if pregunta == "Cintura":
        return st.number_input("Cintura (cm)", min_value=50, max_value=160, value=None, step=1, key=clave)
    if pregunta == "Cadera":
        return st.number_input("Cadera (cm)", min_value=60, max_value=170, value=None, step=1, key=clave)
    if pregunta == "Ciclo regular o irregular":
        resp = st.radio("Tus ciclos menstruales son:", ["Regulares", "Irregulares"],
                        index=None, horizontal=True, key=clave)
        return None if resp is None else (resp == "Irregulares")
    if pregunta == "Días de sangrado":
        return st.radio("¿Cuántos días dura normalmente tu menstruación (días de sangrado)?",
                        list(RANGOS_DURACION.keys()), index=None, horizontal=True, key=clave)
    textos = {
        "Aumento de peso": "¿Has notado aumento de peso que te cuesta controlar?",
        "Crecimiento de vello": "¿Tienes crecimiento excesivo de vello (rostro, pecho o espalda)?",
        "Piel oscurecida": "¿Tienes zonas de piel oscurecida (cuello, axilas o ingles)?",
        "Caída de cabello": "¿Has notado caída de cabello inusual?",
        "Acné": "¿Tienes acné persistente?",
        "Comida rápida": "¿Consumes comida rápida con frecuencia?",
        "Ejercicio": "¿Haces ejercicio de forma regular?",
    }
    return _si_no(textos[pregunta], clave)


def main():
    st.set_page_config(page_title="Estimación de riesgo de SOP", page_icon="🩺", layout="centered")
    corto, largo = _paquetes()

    basicas = [p for p in PREGUNTAS if p in corto["preguntas"]]
    opcionales = [p for p in PREGUNTAS if p not in corto["preguntas"]]

    st.title("Estimación de riesgo de SOP")
    st.caption("Prototipo académico · Proyecto de grado, Universidad EAN")
    st.info(
        "Esta herramienta estima un nivel de riesgo a partir de preguntas sencillas. "
        "**No es un diagnóstico médico** y no reemplaza la valoración de un profesional de la salud. "
        "Tus respuestas no se guardan."
    )

    respuestas = {}
    with st.form("formulario"):
        st.subheader(f"Paso 1: {len(basicas)} preguntas básicas")
        for p in basicas:
            respuestas[p] = pedir(p)

        if largo is not None:
            with st.expander(f"Paso 2 (opcional): afina tu estimación con {len(opcionales)} preguntas más"):
                st.caption(f"Si respondes las {len(opcionales)} preguntas, la estimación usa más información. "
                           "Si dejas alguna sin responder, se usa solo el Paso 1.")
                for p in opcionales:
                    respuestas[p] = pedir(p)

        enviado = st.form_submit_button("Calcular mi estimación")

    if not enviado:
        return

    if any(respuestas[p] is None for p in basicas):
        st.error("Por favor responde las preguntas básicas del Paso 1 para calcular la estimación.")
        return

    contestadas_opc = [p for p in opcionales if respuestas.get(p) is not None]
    afinada = largo is not None and len(contestadas_opc) == len(opcionales)
    if largo is not None and contestadas_opc and not afinada:
        st.info(f"Respondiste {len(contestadas_opc)} de {len(opcionales)} preguntas del Paso 2. "
                "Para afinar la estimación se necesitan todas, así que este resultado usa solo el Paso 1.")

    if afinada:
        paquete, usadas = largo, list(PREGUNTAS)
    else:
        paquete, usadas = corto, basicas
    r = {PREGUNTAS[p]: respuestas[p] for p in usadas}

    duraciones = valor_por_rango(largo) if afinada else None
    fila = construir_fila(paquete, r, duraciones)
    prob = estimar_riesgo(paquete, fila)
    pct = int(round(prob * 100))
    nombre, color = categoria(pct)

    st.divider()
    st.subheader("Tu resultado")
    st.caption("Estimación afinada con las 14 preguntas" if afinada
               else f"Estimación básica con {len(basicas)} preguntas")
    components.html(svg_dona(pct, color), height=240)
    st.markdown(f"<h3 style='text-align:center;color:{color}'>Riesgo estimado: {nombre}</h3>",
                unsafe_allow_html=True)

    fuera = fuera_de_rango(paquete, fila)
    if fuera:
        st.warning("Algunos de tus datos (" + ", ".join(fuera) + ") están fuera del rango de las "
                   "mujeres con las que se entrenó el modelo (20 a 48 años). "
                   "La estimación puede ser menos confiable.")

    phi = aportes(paquete, fila)
    grupos_phi = agrupar(phi, paquete)
    st.write(explicar(grupos_phi, r))
    if afinada:
        st.caption("Esto describe cómo el modelo usó tus respuestas; no son causas médicas. "
                   "Tus respuestas sobre hábitos (comida rápida y ejercicio) y caída de cabello también entran "
                   "en el cálculo, pero en los datos de entrenamiento se relacionan con el resultado de forma "
                   "indirecta, por eso no se destacan.")
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
