# =====================================================================
# explicacion.py: por qué cada respuesta sube o baja la estimación
# (sin Streamlit, para poder probarla)
#
# Método: valores de Shapley exactos, calculados sobre la probabilidad
# calibrada que ve la usuaria (no sobre la escala interna del modelo).
# Con 5 o 6 variables hay solo 32 o 64 combinaciones, así que el cálculo
# es exacto y rápido. La referencia es el perfil "sin ninguna señal"
# (todas las respuestas en el valor más bajo del dataset: sin síntomas,
# ciclo regular y, si aplica, el menor conteo folicular). Se cumple siempre:
#     riesgo base + suma de aportes = estimación final
# y la cuenta arranca en 0 %: primero el riesgo mínimo que da el modelo aun
# sin señales (riesgo base) y luego cada respuesta suma puntos.
#
# Todo el texto es de plantillas y reglas: no se usa ningún LLM.
# =====================================================================
import itertools
import math

import numpy as np
import pandas as pd

from modelo import (
    PORCENTAJE_RECOMENDAR_CONSULTA,
    categoria,
    valores_crudos,
)

# Efecto menor a este valor (en puntos de porcentaje) se agrupa en una línea.
UMBRAL_PUNTOS = 1.0

COLOR_SUBE = "#d55e00"   # naranja (paleta apta para daltonismo)
COLOR_BAJA = "#0072b2"   # azul
COLOR_NEUTRO = "#555555"
COLOR_TEXTO = "#222222"

# Por variable (clave = nombre de columna del dataset):
#   etiqueta   : nombre legible
#   sube/baja  : frase según el efecto; {pts} y {folic} se rellenan solos
#   razon      : por qué esa respuesta se asocia con el SOP (asociación, no causa)
#   resumen_*  : forma corta para el análisis general
#   modificable: si depende de hábitos o puede abordarse con ayuda profesional
DICCIONARIO = {
    "Skin darkening (Y/N)": {
        "etiqueta": "Piel oscurecida",
        "sube": "Tener zonas de piel oscurecida subió tu estimación en {pts}.",
        "baja": "No tener zonas de piel oscurecida bajó tu estimación en {pts}.",
        "razon": ("Las zonas oscuras en cuello, axilas o ingles se asocian con que el cuerpo "
                  "responde menos a la insulina, algo frecuente en el SOP."),
        "resumen_sube": "tener piel oscurecida",
        "resumen_baja": "no tener piel oscurecida",
        "modificable": False,
    },
    "Cycle(R/I)": {
        "etiqueta": "Ciclo menstrual",
        "sube": "Que tus ciclos sean irregulares subió tu estimación en {pts}.",
        "baja": "Que tus ciclos sean regulares bajó tu estimación en {pts}.",
        "razon": ("Los ciclos irregulares son una de las señales más comunes del SOP porque "
                  "suelen indicar que la ovulación no ocurre con regularidad."),
        "resumen_sube": "tener ciclos irregulares",
        "resumen_baja": "tener ciclos regulares",
        "modificable": False,
    },
    "Weight gain(Y/N)": {
        "etiqueta": "Aumento de peso",
        "sube": "Haber notado aumento de peso subió tu estimación en {pts}.",
        "baja": "No haber notado aumento de peso bajó tu estimación en {pts}.",
        "razon": ("El aumento de peso es frecuente en el SOP por los cambios hormonales y la "
                  "respuesta reducida a la insulina, aunque también tiene muchas otras causas."),
        "resumen_sube": "el aumento de peso",
        "resumen_baja": "no haber notado aumento de peso",
        "modificable": True,
    },
    "hair growth(Y/N)": {
        "etiqueta": "Crecimiento de vello",
        "sube": "Tener crecimiento excesivo de vello subió tu estimación en {pts}.",
        "baja": "No tener crecimiento excesivo de vello bajó tu estimación en {pts}.",
        "razon": ("El exceso de vello puede reflejar niveles altos de hormonas masculinas "
                  "(andrógenos), una de las características del SOP."),
        "resumen_sube": "el crecimiento excesivo de vello",
        "resumen_baja": "no tener exceso de vello",
        "modificable": False,
    },
    "Pimples(Y/N)": {
        "etiqueta": "Acné",
        "sube": "Tener acné persistente subió tu estimación en {pts}.",
        "baja": "No tener acné persistente bajó tu estimación en {pts}.",
        "razon": ("El acné persistente también puede relacionarse con andrógenos altos, "
                  "aunque es común por muchas otras razones."),
        "resumen_sube": "el acné persistente",
        "resumen_baja": "no tener acné persistente",
        "modificable": False,
    },
    "Follicle No. (R)": {
        "etiqueta": "Conteo folicular",
        "sube": "Tu conteo de {folic} subió tu estimación en {pts}.",
        "baja": "Tu conteo de {folic} bajó tu estimación en {pts}.",
        "razon": ("Tener muchos folículos pequeños en los ovarios es una de las características "
                  "que se buscan en la ecografía del SOP."),
        "resumen_sube": "el conteo folicular de tu ecografía",
        "resumen_baja": "el conteo folicular de tu ecografía",
        "modificable": False,
    },
}


# ---------------------------------------------------------------- cálculo
def perfil_sin_senales(paquete):
    """Valor más bajo de cada variable en el dataset de entrenamiento."""
    cols = list(paquete["columnas"])
    return valores_crudos(paquete)[cols].min().to_numpy(dtype=float)


def aportes_probabilidad(paquete, fila):
    """
    Devuelve (base, aportes, final), todo en probabilidad (0 a 1).

    Shapley exacto con una referencia fija: para cada subconjunto S de
    variables, v(S) es la probabilidad calibrada cuando las variables de S
    toman los valores de la usuaria y las demás el valor "sin señal".
        base  = v(vacío)  (riesgo del perfil sin ninguna señal)
        final = v(todo)   (estimación de la usuaria)
        base + suma(aportes) = final   (exacto, salvo error de punto flotante)
    """
    cols = list(paquete["columnas"])
    n = len(cols)
    ref = perfil_sin_senales(paquete)
    x = fila.iloc[0][cols].to_numpy(dtype=float)

    mascaras = list(itertools.product([0, 1], repeat=n))
    filas = np.array([[x[j] if m[j] else ref[j] for j in range(n)] for m in mascaras])
    probs = paquete["modelo_calibrado"].predict_proba(pd.DataFrame(filas, columns=cols))[:, 1]
    v = dict(zip(mascaras, probs))

    fact = math.factorial
    phi = np.zeros(n)
    for j in range(n):
        for m in mascaras:
            if m[j] == 0:
                s_ = sum(m)
                peso = fact(s_) * fact(n - s_ - 1) / fact(n)
                con_j = list(m)
                con_j[j] = 1
                phi[j] += peso * (v[tuple(con_j)] - v[m])

    base = float(v[tuple([0] * n)])
    final = float(v[tuple([1] * n)])
    return base, pd.Series(phi, index=cols), final


# ------------------------------------------------------------------ texto
def _puntos(valor):
    n = max(1, int(round(abs(valor))))
    return "1 punto" if n == 1 else f"{n} puntos"


def _folic(valor):
    n = int(round(valor))
    return "1 folículo" if n == 1 else f"{n} folículos"


def _unir(items):
    items = list(items)
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " y " + items[-1]


def construir_explicacion(paquete, fila):
    """
    Devuelve un diccionario con:
      base_pct, final_pct : riesgo base (sin señales) y estimación (en %, sin redondear)
      base_visible : True si el riesgo base es de 1 punto o más (se dibuja como fila)
      items   : variables con efecto >= 1 punto, de mayor a menor efecto
      menores : variables con efecto < 1 punto (se agrupan en una línea)
    Cada item trae: columna, etiqueta, puntos (con signo), frase, razon, modificable.
    """
    base, phi, final = aportes_probabilidad(paquete, fila)
    items, menores = [], []
    for col, valor in phi.items():
        pts = float(valor) * 100
        d = DICCIONARIO[col]
        item = {
            "columna": col,
            "etiqueta": d["etiqueta"],
            "puntos": pts,
            "razon": d["razon"],
            "modificable": d["modificable"],
        }
        plantilla = d["sube"] if pts >= 0 else d["baja"]
        folic = _folic(fila.iloc[0][col]) if col == "Follicle No. (R)" else ""
        item["frase"] = plantilla.format(pts=_puntos(pts), folic=folic)
        item["resumen"] = d["resumen_sube"] if pts >= 0 else d["resumen_baja"]
        (items if abs(pts) >= UMBRAL_PUNTOS else menores).append(item)
    items.sort(key=lambda i: abs(i["puntos"]), reverse=True)
    return {
        "base_pct": base * 100,
        "final_pct": final * 100,
        "base_visible": base * 100 >= UMBRAL_PUNTOS,
        "items": items,
        "menores": menores,
    }


def analisis_general(pct, explicacion):
    """3 a 5 frases hechas con reglas. Tono tranquilo, nunca alarmista."""
    items = explicacion["items"]
    nombre, _ = categoria(pct)
    frases = [f"Tu estimación quedó en el rango {nombre.lower()} ({pct} %)."]

    suben = [i for i in items if i["puntos"] > 0][:2]
    bajan = [i for i in items if i["puntos"] < 0][:1]
    if suben:
        frases.append("Lo que más subió tu estimación fue "
                      + _unir([i["resumen"] for i in suben]) + ".")
    if bajan:
        frases.append("Lo que más la bajó fue " + bajan[0]["resumen"] + ".")
    if not suben and not bajan:
        frases.append("Ninguna de tus respuestas cambió la estimación de forma destacada.")

    if suben:
        if any(i["modificable"] for i in suben):
            frases.append("De estos factores, el aumento de peso es el que puede abordarse "
                          "con acompañamiento profesional; los demás son rasgos que no "
                          "cambian solo con hábitos.")
        else:
            frases.append("Ninguno de estos factores depende de tus hábitos.")

    cierre = ("Esto muestra asociaciones del modelo, no causas, y no es un diagnóstico; ")
    if pct >= PORCENTAJE_RECOMENDAR_CONSULTA:
        cierre += "te recomendamos consultar con ginecología o endocrinología."
    else:
        cierre += ("si tienes síntomas o dudas, consulta con ginecología o endocrinología.")
    frases.append(cierre)
    return " ".join(frases)


# ----------------------------------------------------------------- gráfica
def _signo(p):
    return ("▲ +" if p >= 0 else "▼ −") + str(max(1, int(round(abs(p))))) + " pts"


def svg_cascada(explicacion):
    """
    Cascada horizontal: parte de 0 %, suma el riesgo base y cada respuesta, y llega a la estimación.
    Naranja ▲ = sube, azul ▼ = baja. El signo y la flecha van escritos, así que
    no depende solo del color. Pensado primero para celular (ancho adaptable).
    """
    ancho, margen, alto_fila = 360, 12, 42
    zona = ancho - 2 * margen
    esc = lambda pct: margen + zona * max(0.0, min(100.0, pct)) / 100

    base, final = explicacion["base_pct"], explicacion["final_pct"]
    filas = [("Punto de partida", "0 %", 0, 0, COLOR_NEUTRO)]
    acumulado = 0.0
    if explicacion["base_visible"]:
        filas.append(("Riesgo base (sin ninguna señal)", _signo(base), 0, base, COLOR_NEUTRO))
        acumulado = base
    for it in explicacion["items"]:
        nuevo = acumulado + it["puntos"]
        color = COLOR_SUBE if it["puntos"] >= 0 else COLOR_BAJA
        filas.append((it["etiqueta"], _signo(it["puntos"]), acumulado, nuevo, color))
        acumulado = nuevo
    if explicacion["menores"]:
        resto = sum(m["puntos"] for m in explicacion["menores"])
        if not explicacion["base_visible"]:
            resto += base
        nuevo = acumulado + resto
        filas.append(("Otras respuestas", "casi sin efecto", acumulado, nuevo, COLOR_NEUTRO))
        acumulado = nuevo
    filas.append(("Tu estimación", f"{round(final)} %", 0, final, COLOR_TEXTO))

    alto = alto_fila * len(filas) + 14
    resumen = "; ".join(f"{e}: {v}" for e, v, *_ in filas)
    partes = [
        f'<svg width="100%" viewBox="0 0 {ancho} {alto}" role="img" '
        f'style="display:block;margin:0 auto;max-width:{ancho}px" '
        f'aria-label="Cómo cambió tu estimación. {resumen}" '
        f'xmlns="http://www.w3.org/2000/svg" font-family="sans-serif">',
        f'<rect width="{ancho}" height="{alto}" rx="10" fill="#ffffff"/>',
    ]
    for k, (etiqueta, valor, desde, hasta, color) in enumerate(filas):
        y = 8 + k * alto_fila
        izq, der = sorted((esc(desde), esc(hasta)))
        partes.append(f'<text x="{margen}" y="{y + 13}" font-size="13" fill="{COLOR_TEXTO}">{etiqueta}</text>')
        partes.append(f'<text x="{ancho - margen}" y="{y + 13}" font-size="13" font-weight="700" '
                      f'text-anchor="end" fill="{COLOR_TEXTO}">{valor}</text>')
        partes.append(f'<rect x="{margen}" y="{y + 20}" width="{zona}" height="12" rx="3" fill="#eeeeee"/>')
        partes.append(f'<rect x="{izq:.1f}" y="{y + 20}" width="{max(der - izq, 2):.1f}" height="12" '
                      f'rx="3" fill="{color}"/>')
    partes.append("</svg>")
    return "".join(partes), alto
