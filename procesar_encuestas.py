"""
Módulo ejecutable local y CLI: Extractor de Encuestas de Salud Ocupacional (PROJ-003)
Procesa encuestas desde carpetas locales o llamadas directas integrando el catálogo oficial de 64 columnas.
"""

import os
import sys
import json
import glob
from typing import List, Optional
from PIL import Image
from dotenv import load_dotenv

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Cargar variables de entorno
load_dotenv()

from core_extractor import (
    OPCIONES_CATALOGO_64,
    COLUMNAS_EXACTAS_64,
    SYSTEM_INSTRUCTION,
    construir_prompt_schema,
    normalizar_formato_fecha,
    normalizar_payload_64,
    extraer_con_ollama_vision,
    extraer_con_gemini_vision,
    extraer_datos_multimodal,
    optimizar_imagen_para_vision,
    verificar_estado_ollama,
    enviar_webhook_google_sheets,
    procesar_encuesta_completa,
    DEFAULT_LLM_PROVIDER,
    OLLAMA_MODEL,
    OLLAMA_BASE_URL,
    DEFAULT_GEMINI_MODEL,
    ENABLE_GEMINI_FALLBACK,
    WEBHOOK_URL
)

CARPETA_IMAGENES = "fotos_encuestas"

def procesar_lote_encuesta(rutas_imagenes: List[str], modalidad: Optional[str] = None, municipio: Optional[str] = None, provider: Optional[str] = None):
    """Procesa una lista de rutas de imágenes locales usando el motor central multimodal con auto-detección."""
    imagenes_pil = [Image.open(r) for r in rutas_imagenes]
    return procesar_encuesta_completa(
        imagenes_base64_o_pil=imagenes_pil,
        modalidad_override=modalidad,
        municipio_override=municipio,
        enviar_a_sheets=True,
        provider=provider
    )

def enviar_a_google_sheets(datos_extraidos, fecha_fija_municipio=None):
    """Función de compatibilidad para envío directo."""
    if fecha_fija_municipio:
        datos_extraidos["1. Fecha de caracterización"] = fecha_fija_municipio
    return enviar_webhook_google_sheets(datos_extraidos)

if __name__ == "__main__":
    ollama_info = verificar_estado_ollama()
    print("==========================================================")
    print("=== MOTOR DE EXTRACCIÓN PROJ-003 INICIALIZADO ===")
    print("==========================================================")
    print(f"• Proveedor por defecto: {DEFAULT_LLM_PROVIDER.upper()}")
    print(f"• Ollama Local: {'ONLINE' if ollama_info['disponible'] else 'OFFLINE'} ({ollama_info.get('modelo_configurado')})")
    print(f"• Gemini Cloud Fallback: {'ACTIVO' if ENABLE_GEMINI_FALLBACK else 'INACTIVO'} ({DEFAULT_GEMINI_MODEL})")
    print(f"• Webhook Google Sheets: {WEBHOOK_URL[:45]}...")
    print(f"• Total Columnas Formulario: {len(COLUMNAS_EXACTAS_64)}")
    print("==========================================================\n")