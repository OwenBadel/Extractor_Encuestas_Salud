"""
Servidor Backend FastAPI para el Digitalizador de Encuestas de Salud Ocupacional (PROJ-003).
Conecta la UI PWA en frontend con el motor Gemini Vision / Ollama y el Webhook de Google Apps Script.
"""

import os
import sys
from typing import List, Optional, Dict, Any
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field
from dotenv import load_dotenv

# Importar motor central de extracción
from core_extractor import (
    procesar_encuesta_completa,
    enviar_webhook_google_sheets,
    verificar_estado_ollama,
    COLUMNAS_EXACTAS_64,
    WEBHOOK_URL,
    GEMINI_API_KEY,
    DEFAULT_LLM_PROVIDER,
    OLLAMA_MODEL,
    OLLAMA_BASE_URL,
    DEFAULT_GEMINI_MODEL,
    ENABLE_GEMINI_FALLBACK
)

# Inicializar FastAPI
app = FastAPI(
    title="Extractor de Encuestas de Salud Ocupacional - PROJ-003",
    version="1.1.0",
    description="Backend de digitalización multimodal con Ollama (MiniCPM-V 2.6 en GPU RTX 4060), fallback a Gemini Vision y Webhook Google Sheets."
)

# Configuración de CORS para permitir solicitudes desde cualquier origen local o móvil
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Modelos Pydantic para tipado estricto
class SurveyProcessRequest(BaseModel):
    id: Optional[str] = "TEMP-001"
    modalidad: Optional[str] = Field(None, description="Ambulante / Semiestacionario (4 fotos) o Estacionario (5 fotos)")
    municipio: Optional[str] = ""
    fecha: Optional[str] = ""
    fotos: List[str] = Field(..., description="Lista de imágenes en formato Base64 (4 fotos para Ambulante/Semiestacionario o 5 fotos para Estacionario)")
    enviar_a_sheets: Optional[bool] = True
    provider: Optional[str] = Field(None, description="ollama o gemini (opcional, por defecto usa DEFAULT_LLM_PROVIDER)")

class BatchSyncRequest(BaseModel):
    encuestas: List[SurveyProcessRequest]

class DirectWebhookTestRequest(BaseModel):
    datos: Optional[Dict[str, str]] = None
    override_nombre: Optional[str] = "TEST_SISTEMA"

# Rutas de API
@app.get("/api/health")
def health_check():
    """Verifica el estado del backend, motor local Ollama, clave Gemini y webhook."""
    ollama_info = verificar_estado_ollama()
    return {
        "status": "healthy",
        "proveedor_activo": DEFAULT_LLM_PROVIDER,
        "ollama": {
            "disponible": ollama_info["disponible"],
            "modelo_configurado": OLLAMA_MODEL,
            "modelos_instalados": ollama_info["modelos"],
            "url": OLLAMA_BASE_URL
        },
        "gemini": {
            "api_key_configurada": bool(GEMINI_API_KEY and len(GEMINI_API_KEY) > 5),
            "modelo_fallback": DEFAULT_GEMINI_MODEL,
            "fallback_activo": ENABLE_GEMINI_FALLBACK
        },
        "modelo_activo": OLLAMA_MODEL if DEFAULT_LLM_PROVIDER == "ollama" else DEFAULT_GEMINI_MODEL,
        "webhook_url": WEBHOOK_URL,
        "columnas_requeridas": len(COLUMNAS_EXACTAS_64),
        "version": "1.3.0"
    }

@app.post("/api/process-survey")
async def process_survey(payload: SurveyProcessRequest):
    """
    Procesa una encuesta física en uno de los dos apartados:
    - Apartado 1: Ambulante / Semiestacionario (4 fotos, Hojas 1 a 4). La IA determina en Hoja 1 si es Ambulante o Semiestacionario.
    - Apartado 2: Estacionario (5 fotos, Hojas 1 a 5, incluye Parte II).
    - Optimiza y orienta verticalmente las imágenes a max 1600px.
    - Aplica reglas de normalización de 64 columnas (fechas YYYY-MM-DD).
    - Envía a Google Sheets vía Webhook.
    """
    modalidad = payload.modalidad.strip() if payload.modalidad else None
    fotos_count = len(payload.fotos)
    
    if fotos_count == 0:
        raise HTTPException(status_code=400, detail="Debe adjuntar al menos una foto de la encuesta.")

    try:
        resultado = procesar_encuesta_completa(
            imagenes_base64_o_pil=payload.fotos,
            fecha_override=payload.fecha,
            municipio_override=payload.municipio,
            modalidad_override=modalidad,
            enviar_a_sheets=payload.enviar_a_sheets,
            provider=payload.provider
        )
        
        modalidad_detectada = resultado["datos_extraidos"].get(
            "2. Forma en la que el trabajador desarrolla su ocupación u oficio",
            modalidad or "Detectada por IA"
        )
        
        return {
            "id": payload.id,
            "success": True,
            "modalidad": modalidad_detectada,
            "total_fotos": fotos_count,
            "nombre_trabajador": resultado["nombre_trabajador"],
            "datos_extraidos": resultado["datos_extraidos"],
            "webhook_resultado": resultado["webhook_resultado"]
        }
    except Exception as e:
        print(f"Error procesando encuesta {payload.id}: {e}")
        return JSONResponse(
            status_code=500,
            content={
                "id": payload.id,
                "success": False,
                "error": str(e)
            }
        )


@app.post("/api/sync-batch")
async def sync_batch(payload: BatchSyncRequest):
    """
    Procesa un lote de encuestas secuencialmente y retorna el resumen de sincronización.
    """
    resultados = []
    total = len(payload.encuestas)
    exitosos = 0
    fallidos = 0
    
    for item in payload.encuestas:
        try:
            modalidad = item.modalidad.strip().capitalize() if item.modalidad else None
            resultado = procesar_encuesta_completa(
                imagenes_base64_o_pil=item.fotos,
                fecha_override=item.fecha,
                municipio_override=item.municipio,
                modalidad_override=modalidad,
                enviar_a_sheets=item.enviar_a_sheets,
                provider=item.provider
            )
            
            modalidad_detectada = resultado["datos_extraidos"].get(
                "2. Forma en la que el trabajador desarrolla su ocupación u oficio",
                modalidad or "Detectada por IA"
            )
            
            exitosos += 1
            resultados.append({
                "id": item.id,
                "success": True,
                "modalidad": modalidad_detectada,
                "nombre_trabajador": resultado["nombre_trabajador"],
                "datos_extraidos": resultado["datos_extraidos"],
                "webhook_resultado": resultado["webhook_resultado"]
            })
        except Exception as e:
            fallidos += 1
            resultados.append({
                "id": item.id,
                "success": False,
                "error": str(e)
            })
            
    return {
        "total_procesadas": total,
        "exitosos": exitosos,
        "fallidos": fallidos,
        "detalles": resultados
    }

@app.post("/api/webhook-test")
def test_webhook_direct(payload: DirectWebhookTestRequest):
    """Prueba rápida de envío directo de las 64 columnas al Webhook de Google Sheets."""
    datos = payload.datos or {c: "" for c in COLUMNAS_EXACTAS_64}
    datos["5. Nombre"] = payload.override_nombre
    datos["5.1 Apellido"] = "DIAGNÓSTICO_TEST"
    datos["1. Fecha de caracterización"] = "2026-08-30"
    datos["3. Municipio donde se desarrolla la ocupación"] = "Centro de Pruebas"
    
    res = enviar_webhook_google_sheets(datos)
    return {
        "webhook_url": WEBHOOK_URL,
        "resultado": res
    }

# Montar carpeta estática si existe
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

@app.get("/storage.js")
def serve_storage_js():
    """Entrega el script storage.js con tipo MIME correcto."""
    storage_file = os.path.join(os.path.dirname(__file__), "static", "storage.js")
    if os.path.exists(storage_file):
        return FileResponse(storage_file, media_type="application/javascript")
    raise HTTPException(status_code=404, detail="storage.js no encontrado")

@app.get("/")
def serve_index():
    """Entrega la SPA principal."""
    index_file = os.path.join(os.path.dirname(__file__), "static", "index.html")
    if os.path.exists(index_file):
        return FileResponse(index_file)
    return {"message": "Digitalizador de Encuestas API Activa. Carpeta static/ no encontrada."}

if __name__ == "__main__":
    import uvicorn
    print("Iniciando servidor FastAPI en http://localhost:8000 ...")
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
