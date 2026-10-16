# =====================================================================
# modelo.py: lógica del modelo (sin Streamlit, para poder probarla)
#
# Los dos modelos son regresión logística calibrada (Platt), entrenada
# con el dataset de Kottarathil (541 mujeres de Kerala, India):
#   - modelo_sop_corto.pkl:    5 preguntas básicas
#   - modelo_sop_foliculo.pkl: las 5 preguntas + conteo folicular
# =====================================================================
import joblib
import pandas as pd

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
