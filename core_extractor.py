"""
Motor de extracción multimodal y reglas de validación para Encuestas de Salud Ocupacional.
Implementa Google GenAI SDK con soporte para imágenes Base64 / PIL y reenvío directo a Webhook de Google Apps Script.
"""

import os
import io
import json
import base64
import re
import time
from datetime import datetime
from typing import List, Dict, Any, Optional
from PIL import Image, ImageOps
from google import genai
from google.genai import types
import requests
from dotenv import load_dotenv

# Cargar variables de entorno: primero workspace y luego sobreescribir con .env local del proyecto
workspace_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
workspace_env = os.path.join(workspace_root, ".env")
local_env = os.path.join(os.path.dirname(__file__), ".env")

if os.path.exists(workspace_env):
    load_dotenv(workspace_env)
if os.path.exists(local_env):
    load_dotenv(local_env, override=True)
load_dotenv(override=True)

WEBHOOK_URL = os.getenv(
    "HEALTH_SURVEY_WEBHOOK_URL",
    "https://script.google.com/macros/s/AKfycbybnO0mfJECnS3CQkHzVd4WRAvQFxfNc5JxkJkXEeFvQTBctUluD5CnpZk0gT18rG3K/exec"
)

# Configuración Motor Inferencia Local (Ollama + MiniCPM-V 2.6 en GPU RTX 4060)
DEFAULT_LLM_PROVIDER = os.getenv("DEFAULT_LLM_PROVIDER", "ollama")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434/v1").replace("localhost", "127.0.0.1")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "minicpm-v")
ENABLE_GEMINI_FALLBACK = os.getenv("ENABLE_GEMINI_FALLBACK", "true").lower() in ("true", "1", "yes")


# Configuración Gemini API (Fallback Cloud)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
DEFAULT_GEMINI_MODEL = os.getenv("DEFAULT_LLM_MODEL", "gemini-3.5-flash-lite")

# Inicialización del cliente de Gemini
client = None
if GEMINI_API_KEY:
    client = genai.Client(api_key=GEMINI_API_KEY)
else:
    try:
        client = genai.Client()
    except Exception as e:
        print(f"Advertencia: No se pudo inicializar client genai por defecto: {e}")


SYSTEM_INSTRUCTION = """
Eres un auditor y perito de máxima precisión en transcripción de formularios físicos de salud ocupacional y caracterización sociodemográfica.
Tu tarea es inspeccionar visualmente todas las hojas adjuntas de la encuesta física (4 fotos para Ambulante/Semiestacionario o 5 fotos para Estacionario) y consolidar la información para extraer ÚNICAMENTE las opciones que tengan una marca explícita ('X', '✓', círculo o relleno) y los números manuscritos exactos.

ESTRUCTURA DE LA CUADRÍCULA DE TRABAJADORES (CRÍTICO):
- El formulario físico está diseñado como una matriz con 10 columnas numeradas: N° 1, N° 2, N° 3, N° 4, N° 5, N° 6, N° 7, N° 8, N° 9, N° 10.
- DEBES LEER Y EXTRAER EXCLUSIVAMENTE LAS CASILLAS DE LA COLUMNA "N° 1" (TRABAJADOR 1, la primera columna de casillas adyacente al texto/número del ítem).
- Las columnas N° 2 a N° 10 están vacías; no te confundas con ellas. Solo transcribe lo marcado en la columna N° 1.

REGLAS DE ORO DE EXTRACCIÓN Y ALINEACIÓN VISUAL:
1. ALINEACIÓN ESTRICTA EN LA MISMA FILA HORIZONTAL (PREVENCIÓN DE DESPLAZAMIENTO VERTICAL / OFF-BY-ONE):
   - Cada casilla de verificación [ ] de la columna N° 1 pertenece ÚNICA Y EXCLUSIVAMENTE al texto de la MISMA FILA / RENGLÓN HORIZONTAL donde se encuentra la marca.
   - PROHIBICIÓN ABSOLUTA: NUNCA tomes la opción que está escrita en el renglón de abajo ni en el renglón de arriba.
   - REGLA DE ORO PARA "NINGUNO": NUNCA selecciones ni devuelvas "Ninguno" a menos que la casilla física de "Ninguno" en la columna N° 1 contenga explícitamente una "X", "✓" o marca visible dentro de ella. Si la casilla de "Ninguno" está en blanco o vacía, está TERMINANTEMENTE PROHIBIDO responder "Ninguno".

2. PREGUNTA 31 (PELIGROS POR CONDICIONES DE SEGURIDAD - HOJA 3):
   - Se ubica en la Hoja 3 bajo la sección "CONDICIONES DE TRABAJO".
   - Contiene 12 opciones (31.1 a 31.12).
   - REGLA MULTISELECCIÓN: Revisa meticulosamente la columna N° 1 en cada una de las 12 filas. Si hay varias casillas marcadas con 'X' (ej: 31.1 Herramientas manuales, 31.5 Condiciones locativas, 31.6 Orden y aseo, 31.10 Robos/atracos, 31.11 Accidentes de tránsito), DEBES INCLUIR TODAS LAS OPCIONES MARCADAS separadas por coma y espacio. NO omitas ninguna fila marcada.

3. PREGUNTAS DIVIDIDAS ENTRE DOS HOJAS:
   - Pregunta 28 (Síntomas): Empieza al final de la Hoja 2 (28.1 a 28.3) y continúa al inicio de la Hoja 3 (28.4 a 28.11). Transcribe todas las casillas marcadas con 'X' en la columna N° 1 de ambas hojas.
   - Pregunta 35 (Peligros Biológicos): Empieza al final de la Hoja 3 (35.1 y 35.2) y continúa al inicio de la Hoja 4 (35.3 a 35.10). Transcribe todas las casillas marcadas con 'X' en la columna N° 1 de ambas hojas (ej. 35.3 Mordeduras o picaduras).

4. DIFERENCIACIÓN PRECISA ENTRE AMBULANTE Y SEMIESTACIONARIO:
   - En la Pregunta "2. Forma en la que el trabajador desarrolla su ocupación u oficio" (Hoja 1), existen tres casillas diferenciadas: [ ] Ambulante   [ ] Semiestacionario   [ ] Estacionario.
   - Lee minuciosamente dónde está la 'X': Si la casilla junto a "Semiestacionario" tiene la marca, escribe "Semiestacionario". Si está en "Ambulante", escribe "Ambulante". Si está en "Estacionario", escribe "Estacionario".

5. NÚMEROS Y DÍGITOS MANUSCRITOS:
   - En campos numéricos manuscritos (Antigüedad 16, Horas al día 18, Días a la semana 19, Horas de sueño 25, Cédula 7): lee el valor manuscrito dentro del recuadro o sobre la línea.

ESTRUCTURA DE APARTADOS Y GUÍA DE INSPECCIÓN POR HOJA:

-- APARTADO 1: AMBULANTE / SEMIESTACIONARIO (4 HOJAS / FOTOS) --
- Hoja 1: (Preguntas 1 a 15) -> Fecha YYYY-MM-DD (1), Forma ("Ambulante" o "Semiestacionario" según casilla marcada) (2), Municipio (3), Ámbito territorial (4), Nombre (5), Apellido (5.1), Tipo de Doc (6), No. Doc (7), Fecha Nacimiento (8), Ocupación (9), Sexo (10), Nivel Educativo (11), Grupo Poblacional (12), Condiciones especiales (13), Organización social (14), Seguridad Social (15).
- Hoja 2: (Preguntas 16 a 28,3) -> Antigüedad (16), Jornada (17), Horas/día (18), Días/semana (19), Desplazamiento (20), Enfermedades diagnosticadas (21), Sustancias (22), Alcohol (23), Actividad física (24), Horas de sueño (25), Frutas/verduras (26), Manifestaciones en el último mes (27), Síntomas iniciales 28.1 a 28.3 (Dolor de cabeza, cuello, hombros/codos/muñecas/manos).
- Hoja 3: PELIGROS OCUPACIONALES (Preguntas 28,4 a 35,2) -> Síntomas restantes 28.4 a 28.10, Accidente laboral (29), Discapacidad (30), Peligros Seguridad (31.1 a 31.12), Peligros Físicos (32.1 a 32.8), Peligros Biomecánicos (33.1 a 33.5), Peligros Químicos (34.1 a 34.5), Peligros Biológicos 35.1 a 35.2.
- Hoja 4: SANEAMIENTO BÁSICO (Preguntas 35,3 a 36,10 y Agua y Saneamiento 1 - 4,7) -> Peligros Biológicos restantes 35.3 a 35.10 (ej. mordeduras 35.3), Peligros Psicosociales (36.1 a 36.10), y Saneamiento Básico: Agua (1.1 a 1.11), Excretas (2.1 a 2.9), Residuos generados (3.1 a 3.9), Combustibles (4.1 a 4.7).
- En este apartado de 4 hojas: "¿SEGUNDA HOJA PARTE II - CONDICIONES DEL LUGAR DE TRABAJO?" es "No" y los campos 1 a 21 de Parte II se dejan vacíos "".

-- APARTADO 2: ESTACIONARIO (5 HOJAS / FOTOS) --
- Incluye Hojas 1, 2, 3, 4 y además:
- Hoja 5 (solo Estacionario): PARTE II - CONDICIONES DEL TRABAJO (Preguntas 1 a 21.8) -> "¿SEGUNDA HOJA PARTE II - CONDICIONES DEL LUGAR DE TRABAJO?" es "Sí". Forma es "Estacionario". Transcribe: Lugar compartido con vivienda (1), Persona de contacto (2), Teléfono (3), Celular (4), Dirección (5), Actividad económica (6), Agua consumo (7.1 a 7.11), Tratamiento agua (8.1 a 8.4), Almacenamiento (9.1 a 9.9), Excretas (10.1 a 10.9), Residuos producto (11.1 a 11.9), Disposición residuos (12.1 a 12.7), Aguas residuales (13.1 a 13.5), Combustibles (14.1 a 14.7), Productos químicos (15.1 a 15.11), Almacenamiento químicos (16.1 a 16.6), Residuos peligrosos (17.1 a 17.10), Disposición peligrosos (18.1 a 18.7), Plagas/vectores (19.1 a 19.8), Animales ponzoñosos (20.1 a 20.5), Medidas control de vectores (21.1 a 21.8).
"""

OPCIONES_CATALOGO_64 = {
    "1. Fecha de caracterización": "Fecha en formato YYYY-MM-DD escrita en la cabecera superior",
    "NÚMERO DE FICHA": "Dejar vacío ''",
    "2. Forma en la que el trabajador desarrolla su ocupación u oficio": [
        "Ambulante", "Semiestacionario", "Estacionario"
    ],
    "3. Municipio donde se desarrolla la ocupación": "Texto del municipio / sector",
    "4. Ámbito Territorial": [
        "Rural", "Urbano", "Rural Disperso"
    ],
    "5. Nombre": "Nombre manuscrito",
    "5.1 Apellido": "Apellido manuscrito",
    "6. Tipo de Identificación": [
        "CC", "PASAPORTE", "PERMISO"
    ],
    "7. Número de Identificación": "Dígitos exactos manuscritos",
    "8. Fecha de Nacimiento": "Fecha de nacimiento en formato YYYY-MM-DD",
    "9. Ocupación u oficio": [
        "GANADERO", "COMERCIANTE", "PESCADOR", "AGRICULTOR", "Otro (texto manuscrito)"
    ],
    "10. Sexo biológico del rabajador": [
        "MUJER", "HOMBRE"
    ],
    "11. ¿Cuál es el nivel educativo del trabajador?": [
        "SIN ESTUDIOS", "BÁSICA PRIMARIA INCOMPLETA", "BÁSICA PRIMARIA COMPLETA",
        "BÁSICA SECUNDARIA INCOMPLETA", "BÁSICA SECUNDARIA COMPLETA",
        "MEDIA INCOMPLETA", "MEDIA COMPLETA", "PREGRADO INCOMPLETO",
        "PREGRADO COMPLETO", "POSGRADO INCOMPLETO", "POSGRADO COMPLETO",
        "FORMACIÓN PARA EL DESARROLLO Y EL TRABAJO"
    ],
    "12. ¿A que grupo de población el trabajador pertenece?": [
        "INDÍGENA", "NEGROS, ADRO, RAIZALES Y PALENQUEROS (NARP)",
        "POBLACIÓN GITANA (RROM)", "CAMPESINO", "NINGUNO"
    ],
    "13. ¿El trabajador presenta alguna de estas condiciones?": [
        "LGBTIQ+", "DESPLAZADO", "MIGRANTE", "DESMOVILIZADO",
        "VÍCTIMA DE VIOLENCIA O CONFLICTO ARMADO", "MUJER TRABAJADORA RURAL",
        "MUJER CABEZA DE FAMILIA", "ADULTO MAYOR", "POBLACIÓN PRIVADA DE LA LIBERTAD",
        "NO PERTENECE A NINGUNO"
    ],
    "14. ¿El trabajador pertenece a alguna organización social?": [
        "GRUPO ORGANIZADO DE TRABAJADORES INFORMALES", "REDES BARRIALES COMUNITARIOS",
        "GRUPO DE MUJER Y GÉNERO", "GRUPO RELIGIOSO", "GRUPOS DE MIGRANTES",
        "GRUPOS ÉTNICOS", "NO PERTENECE A NINGUNO"
    ],
    "15. ¿A cuál de los sistemas de la Seguridad Social Integral se encuentra afiliado el trabajador?": [
        "SALUD (RÉGIMEN CONTRIBUTIVO O RÉGIMEN SUBSIDIADO)", "RIESGOS LABORALES",
        "PENSIONES", "BEPS", "CAJAS DE COMPENSACIÓN FAMILIAR", "NINGUNO"
    ],
    "16. ¿Cuánto tiempo de antigüedad lleva el trabajador realizando la ocupación u oficio?": "Texto manuscrito o número de años/meses",
    "17. ¿En que jornada realiza la ocupación u oficio el trabajador?": [
        "DIURNA", "NOCTURNA", "MIXTA"
    ],
    "18. ¿Cuántas horas al día dedica el trabajador a la ocupación u oficio?": "Número manuscrito exacto de horas al día (cualquier valor de 1 a 24)",
    "19. ¿Cuántos días a la semana dedica el trabajador a la ocupación u oficio?": "Número manuscrito exacto de días a la semana (cualquier valor de 1 a 7)",
    "20. ¿Cuál es la forma de desplazamiento más frecuente que utiliza el trabajador hacia el lugar donde realiza su oficio u ocupación?": [
        "VEHÍCULO PARTICULAR", "TRANSPORTE PÚBLICO", "TRANSPORTE AEREO", "MOTOCICLETA",
        "BICICLETA", "PATINETA O MONOPATÍN", "MAQUINARIA AGRÍCOLA O CAMIÓN",
        "SEMOVIENTE", "CAMINANDO", "LANCHA, CANOA O SIMILARES", "TREN", "METROCABLE, TARABITA"
    ],
    "21. ¿Le han diagnosticado algunas de estas enfermedades o condiciones al trabajador?": [
        "ENFERMEDADES DEL CORAZÓN", "ENFERMEDADES DE LOS PULMONES", "DIABETES",
        "ENFERMEDADES CEREBROVASCULARES", "ENFERMEDADES OSTEOARTICULARES", "VÁRICES",
        "HIPERTENSIÓN ARTERIAL", "COLESTEROL O TRIGLICÉRIDOS ALTOS", "NINGUNA"
    ],
    "22. ¿El trabajador consume alguna de estas sustancias?": [
        "CIGARILLO", "SUSTANCIAS PSICOACTIVAS", "NINGUNA"
    ],
    "23. ¿Con que frecuencia el trabajador consume bebidas alcohólicas?": [
        "DIARIAMENTE", "SEMANALMENTE", "QUINCENALMENTE", "OCASIONALMENTE", "NO CONSUME"
    ],
    "24. ¿Cuanto tiempo a la semana realiza actividad física el trabajador?": [
        "NO REALIZA", "MENOS DE 150 MINUTOS A LA SEMANA",
        "APROXIMADAMENTE 150 MINUTOS A LA SEMANA", "MÁS DE 150 MINUTOS A LA SEMANA"
    ],
    "25. ¿Cuántas horas al día duerme el trabajador?": "Número manuscrito exacto de horas de sueño al día (cualquier valor de 1 a 24)",
    "26. ¿Con que frecuencia el trabajador consume frutas y verduras?": [
        "DIARIAMENTE", "SEMANALMENTE", "QUINCENALMENTE", "OCASIONALMENTE", "NO CONSUME"
    ],
    "27. En el último mes, ¿el trabajador ha presentado alguna de las siguientes manifestaciones o comportamientos?": [
        "DIFICULTADES PARA DORMIR", "DESINTÉRES POR LAS COSAS",
        "IRRABITABILIDAD, ACTITUDES O PENSAMIENTOS NEGATIVOS",
        "CONSUMO DE ALGÚN MEDICAMENTO PARA LOS NERVIOS O PARA DORMIR",
        "DIFICULTAD PARA MANEJAR LAS DIFICULTADES QUE SE PRESENTAN",
        "PÉRDIDA/AUMENTO DEL APETITO", "NINGUNO"
    ],
    "28. En el último mes, durante la realización del oficio u ocupación ¿el trabajador ha presenta alguno de estos síntomas?": [
        "DOLOR DE CABEZA", "DOLOR DE CUELLO",
        "DOLOR EN LOS HOMBROS, CODOS, MUÑECAS O MANOS",
        "DOLOR EN LA ESPALDA O CINTURA",
        "DOLOR EN LA CADERA, RODILLAS, TOBILLOS O PIES",
        "DIFICULTAD PARA RESPIRAR O TOS", "CANSANCIO VISUAL",
        "ARDOR EN LOS OJOS O LAGRIMEO", "RASQUIÑA EN LA PIEL",
        "ARDOR O ENROJECIMIENTO EN LA PIEL", "NINGUNO"
    ],
    "29. En el último mes, ¿el trabajador ha tenido algún accidente relacionado con su ocupación u oficio?": [
        "SI", "NO"
    ],
    "30. ¿El trabajador presenta algún tipo de discapacidad?": [
        "FÍSICA", "AUDITIVA", "VISUAL", "SORDOCEGUERA", "INTELECTUAL", "PSICOSOCIAL", "MÚLTIPLE", "NINGUNA"
    ],
    "31. Durante la realización del oficio ¿el trabajador se encuentra expuesto a los siguientes Peligros por Condiciones de Seguridad?": [
        "USO DE HERRAMIENTAS MANUALES, HERRAMIENTAS CORTOPUNZANTES, MAQUINARIA, EQUIPOS",
        "USO DIRECTO DE LA ELECTRICIDAD",
        "PRESENCIA DE CABLES DE ENERGÍA PELADOS, TOMAS SOBRECARGADAS O CONEXIONES DEFECTUOSAS",
        "PRESENCIA DE MATERIAL DE FÁCIL COMBUSTION, INCENDIO, EXPLOSIÓN, DERRAMES O FUGO DE SUSTANCIAS PELIGROSAS",
        "CONDICIONES LOCATIVAS DEFICIENTES EN EL LUGAR DE TRABAJO",
        "CONDICIONES DE ORDEN Y ASEO DEFICIENTES",
        "SITIOS DE ALMACENAMIENTO CON POSIBILIDAD DE CAÍDA DE OBJETOS",
        "TRABAJO EN LAS ALTURAS SUPERIORES A 1,50 M",
        "TRABAJOS EN ESPACIOS CONFINADOS (ESPACIOS CERRADOS)",
        "EXPOSICIÓN A ROBOS, ATRACOS, ASALTOS, ATENTADOS TERRORISTAS, ASONADAS, ETC",
        "EXPOSICIÓN A ACCIDENTES DE TRÁNSITO",
        "NINGUNO"
    ],
    "32. Durante la realización del oficio ¿el trabajador se encuentra expuesto a los siguientes Peligros Físicos?": [
        "PRESENCIA DE RUÍDO TAN ALTO QUE NO PERMITE SEGUIR UNA CONVERSACIÓN A UN METRO DE DISTANCIA, SIN ELEVAR LA VOZ",
        "ILUMINACIÓN INSUFICIENTE O EXCESIVA PARA EL DESARROLLO DE LA TAREA",
        "PRESENCIA DE TEMPERATURA NO CONFORTABLE POR MUCHO FRÍO O MUCHO CALOR",
        "EXPOSICIÓN DIRECTA AL SOL",
        "USO DE PRODUCTOS CON ALTAS TEMPERATURAS (LÍQUIDOS, ACEITES) O SUPERFICIES CALIENTES",
        "USO DE HERRAMIENTAS O MAQUINARÍA QUE GENERE VIBRACIÓN",
        "EXPOSICIÓN A RADIACIÓN ULTRAVIOLETA E INFRAROJAS",
        "NINGUNO"
    ],
    "33. Durante la realización del oficio ¿el trabajador se encuentra expuesto a los siguientes Peligros Biomecánicos?": [
        "EXIGENCIA DE POSTURAS O MOVIMIENTOS FORZADOS",
        "EXIGENCIA DE LEVANTAR, TRASLADAR O ARRASTRAR CARGAS, PERSONAS, ANIMALES U OTROS OBJETOS PESADOS",
        "ESPACIO LIMITADO PARA MOVERSE EN EL DESARROLLO DE LA TAREA",
        "EXIGENCIA DE MOVIMIENTOS REPETITIVOS EN CORTOS PERÍODOS DE TIEMPO",
        "NINGUNO"
    ],
    "34. Durante la realización del oficio ¿el trabajador se encuentra expuesto a los siguientes Peligros Químicos?": [
        "EXPOSICIÓN A HUMOS (HUMO DE SOLDADURA, DIESEL, ETC.) O POLVOS (POLVO DE ARENA O CEMENTO, ETC.) EN LA REALIZACIÓN DE LA TAREA",
        "EXPOSICIÓN A GASES O VAPORES EN LA REALIZACIÓN DE LA TAREA",
        "EXPOSICIÓN A FIBRAS NATURALES, INORGÁNICAS, SINTÉTICAS, ENTRE OTRAS",
        "EXPOSICIÓN DIRECTA DE LA PIEL CON SUSTANCIAS QUÍMICAS",
        "NINGUNO"
    ],
    "35. Durante la realización del oficio ¿el trabajador se encuentra expuesto a los siguientes Peligros Biológicos?": [
        "CONTACTO CON ANIMALES O PARTES DEL SACRIFICIO DE LOS MISMOS (PIEL, HUESOS, PLUMAS, CADÁVERES, ETC.)",
        "MANIPULACIÓN O CONTACTO CON MATERIALES O ANIMALES QUE PODRÍAN ESTAR INFECTADOS DE HONGOS, VIRUS O BACTERIAS (BASURAS)",
        "EXPOSICIÓN A MORDEDURAS O PICADURA DE ANIMALES",
        "EXPOSICIÓN A FLUIDOS O EXCREMENTOS DE ANIMALES O PERSONAS",
        "LA OCUPACIÓN SE REALIZA EN AMBIENTES NO CONTROLADOS (ZONAS BOSCOSAS, CAMPOS ABIERTOS, ETC.)",
        "TENENCIA DE FAUNA SILVESTRE",
        "TENENCIA INADECUADA DE ANIMALES DE COMPAÑÍA",
        "SANEAMIENTO BÁSICO INADECUADO",
        "LUGARES CON PRECIPITACIONES O AUMENTOS DE TEMPERATURA",
        "NINGUNO"
    ],
    "36. Durante la realización del oficio ¿el trabajador se encuentra expuesto a los siguientes Peligros Psicosociales?": [
        "NO ES POSIBLE CONVERSAR Y RESOLVER LOS PROBLEMAS FÁCILMENTE CON LOS COMPAÑEROS",
        "NO SE SIENTE SATISFECHO CON EL TRABAJO QUE REALIZA",
        "EL INGRESO QUE PERCIBE POR SU TRABAJO NO LE PERMITE SATISFACER SUS NECESIDADES BÁSICAS",
        "EL TRABAJO QUE REALIZA NO LE PERMITE TOMAR PAUSAS",
        "EL TRABAJO NO LE PERMITE TIEMPO LIBRE PARA HACER OTRAS ACTIVIDADES",
        "EL TRABAJO LE GENERA CONFLICTOS CON SU FAMILIA, ESPECIALMENTE POR EL TIEMPO QUE USTED DEDICA A ESTE",
        "EL TRABAJO LE GENERA CONFLICTOS CON SUS COMPAÑEROS, DUEÑOS DE LOS MEDIOS DE PRODUCCIÓN O HERRAMIENTAS",
        "EL TRABAJO LE GENERA CONFLICTOS POR EL USO DEL ESPACIO PÚBLICO",
        "EL TRABAJO LE PROVOCA TENSIÓN, ANSIEDAD O ANGUSTIA",
        "NINGUNO"
    ],
    "1. Si el trabajador utiliza agua para la realización del oficio u ocupación ¿de donde proviene ésta?": [
        "ACUEDUCTO COMUNAL O VEREDAL", "ACUEDUCTO PÚBLICO", "CARROCISTERNA",
        "AGUA EMBOTELLADA O EN BOLSA", "ABASTO", "PILA PÚBLICA",
        "POZO PROFUNDO O ALJIBE", "LAGUNA O JAGÜEY", "QUEBRADA O MANANTIAL",
        "AGUAS LLUVIAS", "NINGUNA"
    ],
    "2. Durante la realización del oficio u ocupación, ¿Dónde evacúa o dispone las excretas el trabajador?": [
        "CAMPO ABIERTO", "EN LETRINA TIPO ZANJA O TIPO TRINCHERA",
        "EN LETRINAS SANITARIAS DE FOSA SIMPLE", "INODORO CONECTADO A ALCANTARILLADO",
        "INODORO CONECTADO A POZO SÉPTICO O SUMIDERO", "INODORO CON DESCARGA AL AIRE LIBRE",
        "ESPACIO PÚBLICO", "FUENTES HÍDRICAS", "NINGUNO"
    ],
    "3. ¿Qué clase de residuos genera el oficio realizado por el trabajador?": [
        "RECIPIENTES O BOLSAS PLÁSTICAS", "VIDRIO", "PAPEL O CARTÓN",
        "ORGÁNICO BIODEGRADABLE (RESIDUOS DE COMIDA, CORTES Y PODAS DE MATERIALES VEGETALES, HOJARASCA)",
        "RESIDUOS METÁLICOS (CHATARRA, VIRUTA, TAPAS, ENVASES)", "RESIDUOS DE MADERA",
        "RESIDUOS PELIGROSOS", "AGUAS RESIDUALES", "NINGUNO"
    ],
    "4. Durante la realización del oficio u ocupación, ¿el trabajador utiliza algunos de estos combustibles?": [
        "GAS LICUADO DEL PETRÓLEO", "GAS NATURAL CONECTADO A RED PÚBLICA",
        "LEÑA, MADERA O CARBÓN DE LEÑA", "PETRÓLEO, GASOLINA, KEROSÉN, ALCOHOL",
        "CARBÓN MINERAL", "RESIDUO SÓLIDO O DESECHO", "NINGUNO"
    ],
    "¿SEGUNDA HOJA PARTE II - CONDICIONES DEL LUGAR DE TRABAJO?": [
        "SI", "NO"
    ],
    "1. Lugar de Trabajo compartido con vivienda": [
        "SI", "NO"
    ],
    "2. Persona de contacto del lugar de trabajo": "Texto manuscrito",
    "3. Teléfono": "Número telefónico",
    "4. Celular": "Número celular",
    "5. Dirección del Lugar de Trabajo": "Dirección manuscrita",
    "6. Actividad Económica": [
        "GANADERÍA", "COMERCIO", "PESCADERÍA", "AGRICULTURA", "Otro (texto)"
    ],
    "7. ¿De donde proviene el agua para el consumo humano en el lugar de trabajo?": [
        "ACUEDUCTO COMUNAL O VEREDAL", "ACUEDUCTO PÚBLICO", "CARROCISTERNA",
        "AGUA EMBOTELLADA O EN BOLSA", "ABASTO", "PILA PÚBLICA",
        "POZO PROFUNDO O ALJIBE", "LAGUNA O JAGÜEY", "QUEBRADA O MANANTIAL",
        "AGUAS LLUVIAS", "NINGUNA (PASE A LA PREGUNTA 10)"
    ],
    "8. ¿Qué tipo de tratamiento se realiza al agua antes del consumo humano?": [
        "SE HIERVE", "SE FILTRA", "SE DESINFECTA", "NO SE TRATA"
    ],
    "9. ¿Dónde se realiza el almacenamiento de agua para consumo humano en el lugar de trabajo?": [
        "RECIPIENTE O TANQUE CON TAPA", "RECIPIENTE O TANQUE SIN TAPA",
        "PIMPINAS", "OLLAS", "CANECAS", "TANQUE",
        "ENVASES QUE HAN CONTENIDO OTRO PRODUCTO", "BOLSAS", "NO SE ALMACENA"
    ],
    "10. ¿En el lugar de trabajo, dónde se evacuan y disponen las excretas?": [
        "CAMPO ABIERTO", "EN LETRINA TIPO ZANJA O TIPO TRINCHERA",
        "EN LETRINAS SANITARIAS DE FOSA SIMPLE", "INODORO CONECTADO A ALCANTARILLADO",
        "INODORO CONECTADO A POZO SÉPTICO", "INODORO CON DESCARGA AL AIRE LIBRE",
        "ESPACIO PÚBLICO", "FUENTES HÍDRICAS", "NINGUNO"
    ],
    "11. ¿Qué clase de residuos se generan producto de la actividad?": [
        "RECIPIENTES Y BOLSAS PLÁSTICAS", "VIDRIO", "PAPEL Y CARTÓN",
        "ORGÁNICO BIODEGRADABLE (RESIDUOS DE COMIDA, CORTES Y PODAS DE MATERIALES VEGETALES, HOJARASCA)",
        "RESIDUOS METÁLICOS (CHATARRA, VIRUTA, TAPAS, ENVASES)", "RESIDUOS DE MADERA",
        "RESIDUOS PELIGROSOS", "AGUAS RESIDUALES", "NINGUNO (PASE A LA PREGUNTA 14)"
    ],
    "12. ¿En el lugar donde realiza la ocupación u oficio cómo disponen los residuos sólidos?": [
        "QUEMA A CAMPO ABIERTO", "SE UTILIZAN COMO ABONO",
        "LO ARROJAN A CAMPO ABIERTO", "LO ARROJAN A FUENTES DE AGUA",
        "LO ENTIERRAN", "LO RECOGE UN OPERADOR", "NINGUNO"
    ],
    "13. ¿Dónde disponen las aguas residuales que se generan producto de la ocupación u oficio?": [
        "CAMPO ABIERTO", "CUERPOS DE AGUA", "ALCANTARILLADO",
        "SISTEMA DE TRATAMIENTO", "NO SE GENERAN"
    ],
    "14. En la ocupación u oficio que desarrolla, ¿se utilizan algunos de estos combustibles?": [
        "GAS LICUADO DEL PETRÓLEO", "GAS NATURAL CONECTADO A RED PÚBLICA",
        "LEÑA, MADERA O CARBÓN DE LEÑA", "PETRÓLEO, GASOLINA, KEROSÉN, ALCOHOL",
        "CARBÓN MINERAL", "RESIDUO SÓLIDO O DESECHO", "NINGUNO"
    ],
    "15. En la ocupación u oficio, ¿se usan algunas de las siguientes sustancias o productos químicos?": [
        "GASOLINA, ACEITE LUBRICANTE", "PLAGUICIDAS", "THINNER, VARSOL, REMOVEDORES",
        "ACEITE USADO", "ÁCIDOS", "PEGANTES", "PINTURAS", "CEMENTO", "MERCURIO",
        "COLORANTES O TINTAS", "NINGUNO (PASE A LA PREGUNTA 17)"
    ],
    "16. ¿Dónde se almacenan los productos químicos?": [
        "EN UN LUGAR COMPARTIDO CON LA VIVIENDA (HABITACIÓN, BAÑO, COCINA, ETC)",
        "EN ÁREAS EXTERNAS A LA VIVIENDA",
        "EN UN ÁREA INDEPENDIENTE EN EL MISMO LUGAR DE TRABAJO",
        "EN EL MISMO LUGAR DE TRABAJO SIN ÁREA ESPECIFICA",
        "A LA INTERPERIE", "NO LOS ALMACENA"
    ],
    "17. En la ocupación u oficio, ¿se generan algunos de los siguientes residuos peligros?": [
        "MEDICAMENTOS VENCIDOS", "BOMBILLAS Y LUMINARIAS", "LLANTAS USADAS",
        "ENVASES QUE ALMACENARON SUSTANCIAS QUÍMICAS",
        "RESIDUOS ELECTRÓNICOS O DE APARATOS ELÉCTRICOS Y ELECTRÓNICOS",
        "PLAGUICIDAS", "PILAS", "BATERÍAS PLOMO ÁCIDO", "ACEITES USADOS",
        "NO SE GENERAN (PASE A LA PREGUNTA 19)"
    ],
    "18. ¿En el lugar donde realiza la ocupación u oficio cómo se disponen los residuos peligrosos?": [
        "QUEMA A CAMPO ABIERTO", "SE UTILIZAN COMO ABONO",
        "LO ARROJAN A CAMPO ABIERTO", "LO ARROJAN A FUENTES DE AGUA",
        "LO ENTIERRAN", "LO RECOGE UN OPERADOR", "NINGUNO"
    ],
    "19. ¿Se han identificado las siguientes plagas o vectores en el lugar de trabajo?": [
        "ZANCUDOS", "GARRAPATAS", "PITO", "RATAS", "CUCARACHAS", "PULGAS", "CARACOLES", "NINGUNO"
    ],
    "20. ¿Se han identificado alguno de los siguientes animales ponzoñosos o venenosos?": [
        "ESCORPIONES", "ABEJAS/AVISPAS", "ARAÑAS", "SERPIENTES", "NINGUNO (FINALICE EL FORMULARIO)"
    ],
    "21. ¿Qué medidas se implementan en el lugar donde se desarrolla la ocupación u oficio para control de vectores o reducir el riesgo de incidentes con animales ponzoñosos y venenosos?": [
        "ELIMINACIÓN DE LOS LUGARES DE CRIANZA", "USO DE TOLDILLOS",
        "INSTALACIÓN DE MALLAS, REJAS, CAUCHOS O TRAMPAS QUE IMPIDAN EL INGRESO DE ANIMALES POR PUERTAS, VENTANAS Y DESAGUES",
        "USO DE HIERBICIDAS, INSECTICIDAS, RODENTICIDAS",
        "USO DE BIOPREPARADOS (PRODUCTOS EXTRAÍDOS DE LAS PLATANAS)",
        "USO DE ELEMENTOS DE PROTECCIÓN PERSONAL",
        "MANTENER UN BUEN ESTADO DE ORDEN Y LIMPIEZA EN EL LUGAR DE TRABAJO",
        "NINGUNO"
    ]
}

COLUMNAS_EXACTAS_64 = list(OPCIONES_CATALOGO_64.keys())

def normalizar_formato_fecha(val: str) -> str:
    """Normaliza cualquier fecha a formato estándar YYYY-MM-DD."""
    if not val:
        return ""
    val = val.strip()
    
    # 1. Si ya tiene formato YYYY-MM-DD
    if re.match(r'^\d{4}-\d{2}-\d{2}$', val):
        return val
        
    # 2. Si tiene formato YYYY/MM/DD o YYYY.MM.DD
    m = re.match(r'^(\d{4})[-/\.](\d{1,2})[-/\.](\d{1,2})$', val)
    if m:
        return f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
        
    # 3. Si tiene formato DD/MM/YYYY o DD-MM-YYYY o DD.MM.YYYY o DD MM YYYY
    m = re.match(r'^(\d{1,2})[\s\.\-_/]+(\d{1,2})[\s\.\-_/]+(\d{4})$', val)
    if m:
        return f"{int(m.group(3)):04d}-{int(m.group(2)):02d}-{int(m.group(1)):02d}"
        
    # 4. Si son 8 dígitos contiguos YYYYMMDD
    m = re.match(r'^(20\d{2}|19\d{2})(\d{2})(\d{2})$', val)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"

    # 5. Si son 8 dígitos contiguos DDMMYYYY
    m = re.match(r'^(\d{2})(\d{2})(20\d{2}|19\d{2})$', val)
    if m:
        return f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
        
    return val

def construir_prompt_schema() -> str:
    catalogo_formateado = []
    for col, opciones in OPCIONES_CATALOGO_64.items():
        if isinstance(opciones, list):
            opts_str = " | ".join(opciones)
            catalogo_formateado.append(f'  "{col}": [Opciones válidas: {opts_str}]')
        else:
            catalogo_formateado.append(f'  "{col}": "{opciones}"')
    
    catalogo_texto = "\n".join(catalogo_formateado)
    
    return f"""
A continuación tienes el CATÁLOGO EXACTO con las opciones válidas para cada una de las 64 columnas del formulario.

REGLAS DE PRECISIÓN ABSOLUTA:
1. ALINEACIÓN EN LA MISMA FILA: Cada casilla [X] pertenece al texto que está en SU MISMO RENGLÓN HORIZONTAL. Jamás selecciones la opción de abajo ni de arriba.
2. REGLA ESTRICTA PARA "NINGUNO": Solo responde "Ninguno" si la casilla de "Ninguno" contiene explícitamente una "X". Si la casilla de "Ninguno" está en blanco, NO escribas "Ninguno".
3. PREGUNTA 2: Revisa cuidadosamente si la 'X' está en "Ambulante" o en "Semiestacionario" o en "Estacionario" y transcribe el término exacto.
4. NÚMEROS: Lee el dígito manuscrito dibujado en la línea/casilla de respuesta (horas/días/identificación), no el número de la pregunta.
5. OPCIONES MÚLTIPLES: Si hay varias casillas marcadas, transcríbelas separadas por coma y espacio.

CATÁLOGO OFICIAL DE 64 COLUMNAS Y OPCIONES VÁLIDAS:
{catalogo_texto}

Devuelve ÚNICAMENTE un objeto JSON válido donde cada una de las 64 claves coincida exactamente con las anteriores y su valor sea el texto transcrito.
"""

def optimizar_imagen_para_vision(img: Image.Image, max_dim: int = 1600) -> Image.Image:
    """
    Optimiza una imagen PIL para inferencia multimodal de alta precisión:
    1. Corrige orientación basada en metadatos EXIF (ImageOps.exif_transpose).
    2. Asegura que la imagen quede en orientación vertical (portrait, height > width):
       Si el ancho es mayor al alto (imagen tomada apaisada/horizontal), la rota automáticamente para asegurar que quede vertical.
    3. Asegura formato RGB (elimina canales alfa / paletas que causan artefactos o errores al codificar JPEG).
    4. Si el ancho o alto supera max_dim (1600px), redimensiona manteniendo relación de aspecto
       usando remuestreo LANCZOS para máxima nitidez en trazos manuscritos y casillas marcadas.
    5. Previene desbordamiento de VRAM en GPU y mantiene alta resolución para distinguir casillas 'X' y dígitos.
    """
    try:
        img = ImageOps.exif_transpose(img)
    except Exception:
        pass

    if img.mode != "RGB":
        img = img.convert("RGB")

    # Rotación automática vertical: las encuestas de salud ocupacional son formularios impresos verticales (portrait)
    w, h = img.size
    if w > h:
        img = img.rotate(270, expand=True)
        w, h = img.size

    max_actual = max(w, h)
    if max_actual > max_dim:
        scale = max_dim / float(max_actual)
        nuevo_w = max(1, int(round(w * scale)))
        nuevo_h = max(1, int(round(h * scale)))
        resample_filter = getattr(Image, "Resampling", Image).LANCZOS
        img = img.resize((nuevo_w, nuevo_h), resample=resample_filter)
    
    return img

def codificar_pil_a_base64_jpeg(img: Image.Image, quality: int = 90) -> str:
    """Codifica una imagen PIL a string Base64 en formato JPEG optimizado."""
    if img.mode != "RGB":
        img = img.convert("RGB")
    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=quality, optimize=True)
    return base64.b64encode(buffer.getvalue()).decode("utf-8")

def decodificar_imagen_base64(base64_str: str) -> Image.Image:
    """Decodifica un string base64 (con o sin encabezado data:image/...) a objeto PIL Image."""
    if "," in base64_str:
        base64_str = base64_str.split(",", 1)[1]
    image_data = base64.b64decode(base64_str)
    return Image.open(io.BytesIO(image_data))

def verificar_estado_ollama(base_url: Optional[str] = None) -> Dict[str, Any]:
    """Verifica si el servidor Ollama está disponible y lista los modelos instalados."""
    url = (base_url or OLLAMA_BASE_URL).rstrip("/")
    root_url = url[:-3] if url.endswith("/v1") else url
    try:
        resp = requests.get(f"{root_url}/api/tags", timeout=1.5)
        if resp.status_code == 200:
            data = resp.json()
            modelos = [m.get("name") for m in data.get("models", [])]
            return {
                "disponible": True,
                "modelos": modelos,
                "url": url,
                "modelo_configurado": OLLAMA_MODEL
            }
    except Exception:
        pass
    return {
        "disponible": False,
        "modelos": [],
        "url": url,
        "modelo_configurado": OLLAMA_MODEL
    }

def obtener_valor_columna_raw(col: str, raw_data: Dict[str, Any]) -> str:
    """Busca el valor de una columna en raw_data de forma tolerante a diferencias de formato o listas."""
    # 1. Búsqueda exacta
    if col in raw_data and raw_data[col] is not None:
        val = raw_data[col]
        if isinstance(val, list):
            return ", ".join(str(v).strip() for v in val if v).strip()
        return str(val).strip()
    
    # 2. Búsqueda case-insensitive
    col_lower = col.strip().lower()
    for k, v in raw_data.items():
        if k.strip().lower() == col_lower and v is not None:
            if isinstance(v, list):
                return ", ".join(str(item).strip() for item in v if item).strip()
            return str(v).strip()

    # 3. Búsqueda por prefijo numérico (ej. "31.", "32.", "5.1", etc.)
    m = re.match(r'^(\d+(\.\d+)?)\.\s*(.*)', col)
    if m:
        num_prefix = m.group(1)
        for k, v in raw_data.items():
            k_clean = k.strip()
            if k_clean.startswith(f"{num_prefix}.") or k_clean.startswith(f"{num_prefix} ") or k_clean.startswith(f"{num_prefix}:") or k_clean == num_prefix:
                # Distinguir preguntas 1, 2, 3, 4 de distintas secciones
                if "agua" in col_lower and "agua" not in k.lower():
                    continue
                if "excretas" in col_lower and "excretas" not in k.lower():
                    continue
                if "residuos" in col_lower and "residuos" not in k.lower():
                    continue
                if "combustibles" in col_lower and "combustibles" not in k.lower():
                    continue
                if "vivienda" in col_lower and "vivienda" not in k.lower():
                    continue
                if "contacto" in col_lower and "contacto" not in k.lower():
                    continue
                
                if v is not None:
                    if isinstance(v, list):
                        return ", ".join(str(item).strip() for item in v if item).strip()
                    return str(v).strip()
                    
    return ""

def normalizar_payload_64(raw_data: Dict[str, Any], overrides: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """Asegura que el diccionario contenga exactamente las 64 columnas esperadas con cadenas de texto y formatos normalizados."""
    resultado = {}
    overrides = overrides or {}
    
    for col in COLUMNAS_EXACTAS_64:
        val = obtener_valor_columna_raw(col, raw_data)
        resultado[col] = val.strip()

    # Normalizar formato de fechas a YYYY-MM-DD
    if resultado.get("8. Fecha de Nacimiento"):
        resultado["8. Fecha de Nacimiento"] = normalizar_formato_fecha(resultado["8. Fecha de Nacimiento"])
    if resultado.get("1. Fecha de caracterización") and not (overrides.get("fecha")):
        resultado["1. Fecha de caracterización"] = normalizar_formato_fecha(resultado["1. Fecha de caracterización"])

    # Aplicar overrides si existen (ej. municipio fijado en selector de UI)
    if "fecha" in overrides and overrides["fecha"]:
        resultado["1. Fecha de caracterización"] = normalizar_formato_fecha(overrides["fecha"])
    if "municipio" in overrides and overrides["municipio"]:
        resultado["3. Municipio donde se desarrolla la ocupación"] = overrides["municipio"]
    
    # Determinar modalidad:
    ia_detected = resultado.get("2. Forma en la que el trabajador desarrolla su ocupación u oficio", "").strip()
    override_mod = (overrides.get("modalidad") or "").strip()
    
    # Si override es Estacionario (Apartado 2 - 5 fotos)
    if "estacionario" in override_mod.lower() and "semi" not in override_mod.lower():
        mod = "Estacionario"
    # Si override es específico para Semiestacionario
    elif "semi" in override_mod.lower() and "ambulante" not in override_mod.lower():
        mod = "Semiestacionario"
    # Si override es específico para Ambulante
    elif "ambulante" in override_mod.lower() and "semi" not in override_mod.lower():
        mod = "Ambulante"
    else:
        # En caso de 'Ambulante / Semiestacionario' o None, tomamos lo detectado visualmente por la IA:
        if "semi" in ia_detected.lower():
            mod = "Semiestacionario"
        elif "ambulante" in ia_detected.lower():
            mod = "Ambulante"
        elif "estacionario" in ia_detected.lower():
            mod = "Estacionario"
        else:
            mod = ia_detected.capitalize() if ia_detected else "Ambulante"
    
    resultado["2. Forma en la que el trabajador desarrolla su ocupación u oficio"] = mod

    # Saneamiento de Parte II basado en la modalidad detectada
    parte2_val = resultado.get("¿SEGUNDA HOJA PARTE II - CONDICIONES DEL LUGAR DE TRABAJO?", "").strip().upper()
    if mod in ["Ambulante", "Semiestacionario"]:
        resultado["¿SEGUNDA HOJA PARTE II - CONDICIONES DEL LUGAR DE TRABAJO?"] = "No"
        for i in range(1, 22):
            key = next((k for k in COLUMNAS_EXACTAS_64[43:] if k.startswith(f"{i}. ")), None)
            if key:
                resultado[key] = ""
    elif mod == "Estacionario" or parte2_val in ["SI", "SÍ", "1", "TRUE"]:
        resultado["¿SEGUNDA HOJA PARTE II - CONDICIONES DEL LUGAR DE TRABAJO?"] = "Sí"

    # Regla 6: NÚMERO DE FICHA vacío
    resultado["NÚMERO DE FICHA"] = ""

    return resultado

def extraer_con_ollama_vision(
    imagenes_pil: List[Image.Image],
    modelo: Optional[str] = None,
    base_url: Optional[str] = None
) -> Dict[str, Any]:
    """
    Procesa las 4 o 5 imágenes de la encuesta en un solo turno multimodal con Ollama
    usando el endpoint compatible con OpenAI (/v1/chat/completions).
    Aplica optimización de imagen (max 1600px) y devuelve estrictamente un objeto JSON con las 64 columnas.
    """
    endpoint_base = (base_url or OLLAMA_BASE_URL).rstrip("/")
    chat_url = f"{endpoint_base}/chat/completions"
    model_name = modelo or OLLAMA_MODEL

    # 1. Optimizar imágenes a max 1600px y codificar en Base64 JPEG
    imagenes_optimizadas = [optimizar_imagen_para_vision(img, max_dim=1600) for img in imagenes_pil]
    
    content_user: List[Dict[str, Any]] = [
        {
            "type": "text",
            "text": f"Inspecciona minuciosamente las siguientes {len(imagenes_optimizadas)} páginas adjuntas del formulario físico de salud ocupacional y extrae las 64 columnas exactas:\n\n{construir_prompt_schema()}"
        }
    ]

    for img in imagenes_optimizadas:
        b64_str = codificar_pil_a_base64_jpeg(img, quality=90)
        content_user.append({
            "type": "image_url",
            "image_url": {
                "url": f"data:image/jpeg;base64,{b64_str}"
            }
        })

    messages = [
        {
            "role": "system",
            "content": SYSTEM_INSTRUCTION
        },
        {
            "role": "user",
            "content": content_user
        }
    ]

    payload = {
        "model": model_name,
        "messages": messages,
        "temperature": 0.05,
        "response_format": {"type": "json_object"},
        "stream": False
    }

    headers = {
        "Content-Type": "application/json"
    }

    response = requests.post(chat_url, json=payload, headers=headers, timeout=120)
    
    if response.status_code != 200:
        raise RuntimeError(f"Ollama API error ({response.status_code}): {response.text}")

    resp_json = response.json()
    choices = resp_json.get("choices", [])
    if not choices:
        raise ValueError(f"Ollama devolvió respuesta vacía: {resp_json}")

    content_str = choices[0].get("message", {}).get("content", "").strip()
    if not content_str:
        raise ValueError("Ollama retornó contenido de mensaje vacío.")

    # Parsear bloque JSON
    match = re.search(r'\{[\s\S]*\}', content_str)
    if match:
        return json.loads(match.group(0))
    else:
        limpio = content_str
        if limpio.startswith("```json"):
            limpio = limpio[7:]
        if limpio.startswith("```"):
            limpio = limpio[3:]
        if limpio.endswith("```"):
            limpio = limpio[:-3]
        return json.loads(limpio.strip())

def extraer_con_gemini_vision(imagenes_pil: List[Image.Image], modelos: Optional[List[str]] = None) -> Dict[str, Any]:
    """Procesa una lista de imágenes PIL con Gemini Vision usando modelos de alta cuota y optimización a 1600px."""
    if not client:
        raise ValueError("Cliente Google GenAI no inicializado. Verifique GEMINI_API_KEY en .env")
        
    # Optimizar imágenes antes de la llamada
    imagenes_opt = [optimizar_imagen_para_vision(img, max_dim=1600) for img in imagenes_pil]

    modelos_candidatos = modelos or [
        DEFAULT_GEMINI_MODEL,
        "gemini-3.5-flash-lite",
        "gemini-3.1-flash-lite",
        "gemini-flash-lite-latest",
        "gemini-3.6-flash"
    ]
    prompt = f"{SYSTEM_INSTRUCTION}\n\n{construir_prompt_schema()}"
    
    ultimo_error = None
    for modelo in modelos_candidatos:
        for intento in range(2):
            try:
                config = types.GenerateContentConfig(
                    temperature=0.05
                )
                
                response = client.models.generate_content(
                    model=modelo,
                    contents=[*imagenes_opt, prompt],
                    config=config
                )
                
                if response.text:
                    texto_raw = response.text.strip()
                    match = re.search(r'\{[\s\S]*\}', texto_raw)
                    if match:
                        texto_json = match.group(0)
                        return json.loads(texto_json)
                    else:
                        texto_limpio = texto_raw
                        if texto_limpio.startswith("```json"):
                            texto_limpio = texto_limpio[7:]
                        if texto_limpio.startswith("```"):
                            texto_limpio = texto_limpio[3:]
                        if texto_limpio.endswith("```"):
                            texto_limpio = texto_limpio[:-3]
                        return json.loads(texto_limpio.strip())
            except Exception as e:
                print(f"Aviso: Modelo Gemini {modelo} (intento {intento+1}) falló ({e}).")
                ultimo_error = e
                time.sleep(1.5)
            
    raise RuntimeError(f"Fallo la extracción en todos los modelos Gemini probados: {ultimo_error}")

def extraer_datos_multimodal(
    imagenes_pil: List[Image.Image],
    provider: Optional[str] = None
) -> Dict[str, Any]:
    """
    Orquestador central de inferencia multimodal:
    - Si provider='ollama' (default): ejecuta Ollama local (MiniCPM-V 2.6 en GPU RTX 4060).
      Si Ollama no está activo o falla y ENABLE_GEMINI_FALLBACK=True, conmuta de forma transparente a Gemini Vision.
    - Si provider='gemini': ejecuta Gemini Vision. En caso de error 429/ResourceExhausted, conmuta a Ollama local.
    """
    proveedor_actual = (provider or DEFAULT_LLM_PROVIDER).lower().strip()
    
    if proveedor_actual == "ollama":
        try:
            print(f"[EXTRACTOR] Ejecutando inferencia local Ollama ({OLLAMA_MODEL}) en GPU...")
            return extraer_con_ollama_vision(imagenes_pil)
        except Exception as e_ollama:
            print(f"⚠️ [AVISO] Motor local Ollama no respondió o falló: {e_ollama}")
            if ENABLE_GEMINI_FALLBACK:
                print("🔄 [FALLBACK] Conmutando automáticamente a Gemini Vision Cloud...")
                return extraer_con_gemini_vision(imagenes_pil)
            else:
                raise e_ollama

    elif proveedor_actual == "gemini":
        try:
            print(f"[EXTRACTOR] Ejecutando inferencia con Gemini Vision ({DEFAULT_GEMINI_MODEL})...")
            return extraer_con_gemini_vision(imagenes_pil)
        except Exception as e_gemini:
            print(f"⚠️ [AVISO] Falló Gemini Vision: {e_gemini}")
            # Si ocurre error 429 Too Many Requests / ResourceExhausted, intentar Ollama local
            if "429" in str(e_gemini) or "ResourceExhausted" in str(e_gemini) or "quota" in str(e_gemini).lower():
                print("🔄 [FALLBACK 429] Detectada saturación de cuota en Gemini. Conmutando a Ollama local...")
                return extraer_con_ollama_vision(imagenes_pil)
            raise e_gemini
    else:
        # Fallback general
        return extraer_con_gemini_vision(imagenes_pil)

def enviar_webhook_google_sheets(datos_64: Dict[str, str], webhook_url: Optional[str] = None) -> Dict[str, Any]:
    """Envía el diccionario con las 64 columnas al Webhook de Google Apps Script mediante HTTP POST."""
    url = webhook_url or WEBHOOK_URL
    headers = {"Content-Type": "application/json"}
    
    try:
        response = requests.post(url, json=datos_64, headers=headers, timeout=35)
        return {
            "status_code": response.status_code,
            "success": response.status_code == 200,
            "response_text": response.text,
            "enviado": True
        }
    except Exception as e:
        return {
            "status_code": 500,
            "success": False,
            "response_text": str(e),
            "enviado": False
        }

def procesar_encuesta_completa(
    imagenes_base64_o_pil: List[Any],
    fecha_override: Optional[str] = None,
    municipio_override: Optional[str] = None,
    modalidad_override: Optional[str] = None,
    enviar_a_sheets: bool = True,
    provider: Optional[str] = None
) -> Dict[str, Any]:
    """
    Pipeline completo:
    1. Conversión y optimización de imágenes a PIL (max 1400px)
    2. Extracción multimodal con motor local Ollama (MiniCPM-V 2.6) o Gemini Vision (fallback)
    3. Normalización y validación estricta de 64 columnas
    4. Envío opcional directo al Webhook de Google Apps Script
    """
    imagenes_pil = []
    for item in imagenes_base64_o_pil:
        if isinstance(item, str):
            imagenes_pil.append(decodificar_imagen_base64(item))
        elif isinstance(item, Image.Image):
            imagenes_pil.append(item)
        else:
            raise TypeError(f"Tipo de imagen no soportado: {type(item)}")

    # 1. Extracción con motor multimodal (Ollama local / Gemini fallback)
    datos_crudos = extraer_datos_multimodal(imagenes_pil, provider=provider)
    
    # 2. Normalización de 64 columnas
    overrides = {
        "fecha": fecha_override,
        "municipio": municipio_override,
        "modalidad": modalidad_override
    }
    datos_normalizados = normalizar_payload_64(datos_crudos, overrides)
    
    # 3. Envío al Webhook si está habilitado
    webhook_resultado = None
    if enviar_a_sheets:
        webhook_resultado = enviar_webhook_google_sheets(datos_normalizados)
        
    return {
        "datos_extraidos": datos_normalizados,
        "webhook_resultado": webhook_resultado,
        "nombre_trabajador": f"{datos_normalizados.get('5. Nombre', '')} {datos_normalizados.get('5.1 Apellido', '')}".strip(),
        "total_columnas": len(datos_normalizados)
    }


