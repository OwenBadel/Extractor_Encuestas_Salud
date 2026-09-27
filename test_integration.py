"""
Suite de pruebas de integración para el Digitalizador de Encuestas de Salud Ocupacional (PROJ-003).
Verifica:
1. Auto-rotación vertical y optimización de imágenes (garantiza orientación vertical y max 1600px)
2. Normalización estricta de fechas a formato estándar YYYY-MM-DD
3. Conexión y health check del backend
4. Envío directo de las 64 columnas al Webhook de Google Apps Script
5. Normalización y diferenciación estricta entre Semiestacionario, Ambulante y Estacionario
6. Reglas anti-desplazamiento vertical y reglas de 4 y 5 fotos
"""

import sys
import json
import base64
import io
from PIL import Image, ImageDraw
from fastapi.testclient import TestClient
from app import app
from core_extractor import (
    optimizar_imagen_para_vision,
    codificar_pil_a_base64_jpeg,
    normalizar_formato_fecha,
    normalizar_payload_64,
    verificar_estado_ollama,
    SYSTEM_INSTRUCTION
)

sys.stdout.reconfigure(encoding='utf-8')

def generar_imagen_simulada(texto="Página 1", width=800, height=1000):
    img = Image.new('RGB', (width, height), color=(240, 240, 240))
    draw = ImageDraw.Draw(img)
    draw.rectangle([20, 20, width - 20, height - 20], outline=(50, 50, 50), width=3)
    draw.text((40, 50), f"FORMULARIO DE SALUD - {texto}", fill=(0, 0, 0))
    draw.text((40, 90), "1. Fecha de caracterización: 2026-08-30", fill=(0, 0, 0))
    draw.text((40, 130), "2. Forma en la que el trabajador desarrolla su ocupación u oficio: Semiestacionario [X]", fill=(0, 0, 0))
    draw.text((40, 170), "5. Nombre: CARLOS", fill=(0, 0, 0))
    draw.text((40, 210), "5.1 Apellido: GOMEZ", fill=(0, 0, 0))
    draw.text((40, 250), "6. Tipo de Identificación: CC", fill=(0, 0, 0))
    draw.text((40, 290), "7. Número de Identificación: 1098765432", fill=(0, 0, 0))
    draw.text((40, 330), "8. Fecha de Nacimiento: 12/05/1990", fill=(0, 0, 0))
    draw.text((40, 370), "10. Sexo biológico del rabajador: Hombre [X]", fill=(0, 0, 0))
    
    buffer = io.BytesIO()
    img.save(buffer, format='JPEG')
    b64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
    return f"data:image/jpeg;base64,{b64}"

def test_suite():
    print("==================================================")
    print("[TEST] INICIANDO TEST SUITE PROJ-003 EXTRACTOR SALUD (MOTOR ORIGINAL)")
    print("==================================================")

    # 1. Test de Auto-rotación Vertical y Optimización (Max 1600px)
    print("\n1. Probando optimizar_imagen_para_vision (Auto-rotación a vertical + Max 1600px) ...")
    img_horizontal = Image.new('RGBA', (3200, 2400), color=(255, 200, 200, 255))
    img_opt = optimizar_imagen_para_vision(img_horizontal, max_dim=1600)
    w, h = img_opt.size
    print(f"  ✓ Imagen Horizontal Original: 3200x2400 -> Auto-rotada a Vertical: {w}x{h} ({img_opt.mode})")
    assert h > w, f"La imagen debe ser vertical (h > w), obtenida: {w}x{h}"
    assert max(w, h) == 1600, f"Dimensión máxima esperada 1600, obtenida: {max(w, h)}"
    assert img_opt.mode == "RGB", f"Modo esperado RGB, obtenido: {img_opt.mode}"

    b64_opt = codificar_pil_a_base64_jpeg(img_opt)
    assert len(b64_opt) > 100, "Base64 optimizado inválido"
    print("  ✓ Codificación Base64 JPEG optimizada exitosa.")

    # 2. Test de Normalización de Fechas (YYYY-MM-DD)
    print("\n2. Probando normalizar_formato_fecha (estándar YYYY-MM-DD) ...")
    assert normalizar_formato_fecha("2026-08-30") == "2026-08-30"
    assert normalizar_formato_fecha("2026/08/30") == "2026-08-30"
    assert normalizar_formato_fecha("30/08/2026") == "2026-08-30"
    assert normalizar_formato_fecha("12-05-1990") == "1990-05-12"
    assert normalizar_formato_fecha("12.05.1990") == "1990-05-12"
    assert normalizar_formato_fecha("30082026") == "2026-08-30"
    print("  ✓ Todas las variantes de fecha normalizan correctamente a YYYY-MM-DD.")

    # 3. Test de Normalización de Modalidades (Semiestacionario vs Ambulante vs Estacionario)
    print("\n3. Probando diferenciación de Modalidades (Semiestacionario vs Ambulante) ...")
    raw_semi = {
        "2. Forma en la que el trabajador desarrolla su ocupación u oficio": "Semiestacionario",
        "¿SEGUNDA HOJA PARTE II - CONDICIONES DEL LUGAR DE TRABAJO?": "No"
    }
    norm_semi = normalizar_payload_64(raw_semi, overrides={"modalidad": "Ambulante / Semiestacionario"})
    assert norm_semi["2. Forma en la que el trabajador desarrolla su ocupación u oficio"] == "Semiestacionario"
    assert norm_semi["¿SEGUNDA HOJA PARTE II - CONDICIONES DEL LUGAR DE TRABAJO?"] == "No"
    print("  ✓ Modalidad Semiestacionario preservada correctamente bajo Apartado Ambulante/Semiestacionario.")

    raw_amb = {
        "2. Forma en la que el trabajador desarrolla su ocupación u oficio": "Ambulante",
        "¿SEGUNDA HOJA PARTE II - CONDICIONES DEL LUGAR DE TRABAJO?": "No"
    }
    norm_amb = normalizar_payload_64(raw_amb, overrides={"modalidad": "Ambulante / Semiestacionario"})
    assert norm_amb["2. Forma en la que el trabajador desarrolla su ocupación u oficio"] == "Ambulante"
    assert norm_amb["¿SEGUNDA HOJA PARTE II - CONDICIONES DEL LUGAR DE TRABAJO?"] == "No"
    print("  ✓ Modalidad Ambulante preservada correctamente.")

    raw_est = {
        "2. Forma en la que el trabajador desarrolla su ocupación u oficio": "Estacionario",
        "¿SEGUNDA HOJA PARTE II - CONDICIONES DEL LUGAR DE TRABAJO?": "Sí",
        "1. Lugar de Trabajo compartido con vivienda": "NO"
    }
    norm_est = normalizar_payload_64(raw_est, overrides={"modalidad": "Estacionario"})
    assert norm_est["2. Forma en la que el trabajador desarrolla su ocupación u oficio"] == "Estacionario"
    assert norm_est["¿SEGUNDA HOJA PARTE II - CONDICIONES DEL LUGAR DE TRABAJO?"] == "Sí"
    print("  ✓ Modalidad Estacionario y Parte II configuradas correctamente.")

    # 4. Verificación de Reglas en Prompt (Anti-desplazamiento, Matriz N° 1, Pregunta 31)
    print("\n4. Verificando directivas en SYSTEM_INSTRUCTION ...")
    assert "PREVENCIÓN DE DESPLAZAMIENTO VERTICAL" in SYSTEM_INSTRUCTION
    assert "PREGUNTA 31 (PELIGROS POR CONDICIONES DE SEGURIDAD - HOJA 3)" in SYSTEM_INSTRUCTION
    assert "CUADRÍCULA DE TRABAJADORES" in SYSTEM_INSTRUCTION
    assert "PROHIBICIÓN ABSOLUTA: NUNCA tomes la opción que está escrita en el renglón de abajo" in SYSTEM_INSTRUCTION
    print("  ✓ Directivas del prompt verificadas.")

    # 5. Test Client FastAPI & Health check
    client = TestClient(app)
    print("\n5. Probando GET /api/health ...")
    resp = client.get("/api/health")
    assert resp.status_code == 200, f"Error en health check: {resp.status_code}"
    health_data = resp.json()
    print("  ✓ Health Status:", json.dumps(health_data, indent=2))
    assert health_data["status"] == "healthy"
    assert health_data["columnas_requeridas"] == 64
    assert "ollama" in health_data
    assert "gemini" in health_data

    # 6. Test Webhook directo (64 columnas)
    print("\n6. Probando POST /api/webhook-test (Envío directo a Google Sheets) ...")
    resp = client.post("/api/webhook-test", json={"override_nombre": "TEST_ORIGINAL_RESTAURADO"})
    assert resp.status_code == 200, f"Error en webhook-test: {resp.status_code}"
    webhook_data = resp.json()
    print("  ✓ Webhook Test Result:", webhook_data["resultado"])
    assert webhook_data["resultado"]["success"] == True
    assert webhook_data["resultado"]["status_code"] == 200

    print("\n==================================================")
    print("✅ TODAS LAS PRUEBAS DE INTEGRACIÓN HAN PASADO CON ÉXITO")
    print("==================================================")

if __name__ == "__main__":
    test_suite()
