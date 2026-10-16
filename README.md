# Calculador SOP

Prototipo académico (proyecto de grado, Universidad EAN) que estima un **nivel de riesgo** de
Síndrome de Ovario Poliquístico (SOP) a partir de preguntas sencillas.
**No es un diagnóstico** y no reemplaza la valoración de un profesional de la salud.

## Cómo funciona

- **Paso 1 (obligatorio):** 5 preguntas de Sí/No (piel oscurecida, ciclo irregular, aumento de peso,
  crecimiento de vello y acné). Usa `modelo_sop_corto.pkl`.
- **Paso 2 (opcional):** conteo folicular de una ecografía reciente. Usa `modelo_sop_foliculo.pkl`.
- Ambos modelos son regresión logística con calibración Platt, entrenada con el dataset público de
  Kottarathil (541 mujeres de Kerala, India). **No está validado en población colombiana.**
- La app **no guarda ningún dato** de las usuarias (Ley 1581 de 2012).
- Si la usuaria marca "No tengo ovarios", la app no calcula y explica que la herramienta no aplica en su caso.

## Explicación del resultado

La pantalla de resultado muestra cómo cambió la estimación respuesta por respuesta:

- La cuenta parte de 0 %: primero se suma el riesgo mínimo que da el modelo aun sin ninguna señal (riesgo base) y luego cada respuesta suma puntos hasta la estimación de la usuaria.
- Los aportes de cada respuesta se calculan con valores de Shapley exactos sobre la **probabilidad
  calibrada**, de modo que se cumple siempre: `riesgo base + suma de aportes = estimación`.
- Las frases por pregunta, la razón asociada y el resumen final se generan con plantillas y reglas
  (sin modelos de lenguaje). Son **asociaciones del modelo, no causas**.

## Estructura

| Archivo | Contenido |
|---|---|
| `app.py` | Interfaz en Streamlit |
| `modelo.py` | Carga de modelos, armado de la fila, probabilidad y categorías de riesgo |
| `explicacion.py` | Aportes por variable, diccionario de frases, resumen y gráfica en cascada |
| `tests/test_explicacion.py` | Pruebas (aditividad con tolerancia de 0,5 puntos, orden, casos extremos, vocabulario) |

## Ejecutar

```
pip install -r requirements.txt
python -m streamlit run app.py
```

## Pruebas

```
python -m unittest discover -s tests -v
```

## Pendiente (trabajo futuro)

Pantalla inicial con aviso de privacidad y casilla de aceptación, formulario por pasos con barra
de progreso, ayudas (?) en cada pregunta, sección "Sobre el modelo", PDF descargable, opción
"No sé", intervalo de incertidumbre por bootstrap, IMC automático y simulador "¿Y si…?".
Varias de estas funciones requieren variables o datos de entrenamiento que el modelo actual no usa.
