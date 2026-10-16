# =====================================================================
# Prototipo: estimación de riesgo de SOP (proyecto de grado, EAN)
# Recolección progresiva:
#   - Paso 1 (obligatorio): 5 preguntas no invasivas -> modelo_sop_corto.pkl
#   - Paso 2 (opcional):    conteo folicular (ovario derecho), si la
#                           usuaria tiene una ecografía reciente ->
#                           modelo_sop_foliculo.pkl
# Organización del código:
#   modelo.py      lógica del modelo (carga, fila, probabilidad, categorías)
#   explicacion.py por qué cada respuesta sube o baja la estimación
#   app.py         interfaz (este archivo)
# Ejecutar con:  streamlit run app.py
# =====================================================================
from modelo import (
    CLAVE_OPCIONAL,
    PORCENTAJE_RECOMENDAR_CONSULTA,
    PREGUNTA_OPCIONAL,
    PREGUNTAS,
    RUTA_CORTO,
    RUTA_FOLICULO,
    cargar_paquete,
    categoria,
    construir_fila,
    estimar_riesgo,
    fuera_de_rango,
)
from explicacion import analisis_general, construir_explicacion, svg_cascada


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

    sin_ovarios = st.checkbox("No tengo ovarios (por cirugía u otra causa)", key="q_sin_ovarios")
    if sin_ovarios:
        st.info(
            "Esta herramienta estima el riesgo de SOP, una condición que depende de los ovarios y "
            "de la ovulación, así que no aplica en tu caso. Si tienes dudas sobre tu salud hormonal "
            "o metabólica, puedes consultar con ginecología o endocrinología."
        )
        return

    respuestas = {}
    st.subheader("Paso 1: 5 preguntas básicas")
    for p in PREGUNTAS:
        respuestas[p] = pedir_basica(p)

    # Los pasos van fuera de un st.form a propósito: dentro de un formulario los
    # widgets no se actualizan entre sí hasta enviar, y la casilla "No tengo
    # ovario derecho" necesita cambiar en vivo qué campo se muestra. El botón
    # de calcular va al final, después del Paso 2.
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

    enviado = st.button("Calcular mi estimación", type="primary")

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

    explicacion = construir_explicacion(paquete, fila)

    st.subheader("Por qué salió este resultado")
    st.caption("La cuenta parte de 0 %. Primero se suma el riesgo mínimo que da el modelo aun "
               "sin ninguna señal y luego cada respuesta suma puntos hasta llegar a tu estimación.")
    svg, alto = svg_cascada(explicacion)
    components.html(svg, height=alto + 10)

    for item in explicacion["items"]:
        st.markdown("**" + ("▲ " if item["puntos"] >= 0 else "▼ ") + item["frase"] + "**")
        st.caption(item["razon"])
    if explicacion["menores"]:
        st.markdown("Otras respuestas casi no cambiaron el resultado.")

    st.subheader("En resumen")
    st.write(analisis_general(pct, explicacion))
    if afinada and usando_izquierdo:
        st.caption("Como incluiste el conteo folicular, tu estimación se apoya principalmente en ese dato. "
                   "Al ser el conteo del ovario izquierdo usado en lugar del derecho, esta parte del "
                   "resultado es una aproximación, no el dato exacto con el que se entrenó el modelo.")
    elif afinada:
        st.caption("Como incluiste el conteo folicular, tu estimación se apoya principalmente en ese dato, "
                   "que es más preciso que los síntomas reportados por sí solos.")
    else:
        st.caption("Esto describe asociaciones que encontró el modelo; no son causas médicas.")

    if pct >= PORCENTAJE_RECOMENDAR_CONSULTA:
        st.warning("Te recomendamos consultar con un profesional de la salud para una valoración adecuada.")
    else:
        st.success("Si tienes síntomas o dudas que te preocupen, consulta con un profesional de la salud.")

    st.caption("Prototipo entrenado con datos de 541 mujeres de Kerala, India. "
               "No ha sido validado en población colombiana.")


main()
