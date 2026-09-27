# 📋 Extractor de Encuestas de Salud — Digitalizador Multimodal de Salud Ocupacional

[![FastAPI](https://img.shields.io/badge/FastAPI-0.115%2B-009688)](https://fastapi.tiangolo.com/)
[![Python 3.12](https://img.shields.io/badge/Python-3.12-blue)](https://www.python.org/)
[![Google GenAI SDK](https://img.shields.io/badge/Google_GenAI-Gemini_Vision-4285f4)](https://ai.google.dev/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

---

**Autor y Titular:** Ingeniero Owen Badel Hooker  
**GitHub:** [OwenBadel](https://github.com/OwenBadel)  
**Repositorio Oficial:** [Extractor_Encuestas_Salud](https://github.com/OwenBadel/Extractor_Encuestas_Salud)  

---

Solución de digitalización industrial y extracción multimodal para formularios físicos de caracterización de salud laboral y condiciones de trabajo. Combina una **PWA móvil Offline-First** con diseño industrial (*Kinetic Field System*), un motor de visión multimodal con **Google Gemini Vision** / **Ollama Vision** y sincronización en tiempo real de **64 columnas exactas** hacia Google Sheets mediante **Google Apps Script**.

---

## 🏛️ Características Principales

* 📱 **PWA Móvil Offline-First:** Interfaz táctil con visor de cámara WebRTC, crosshairs guía, selector de galería, y persistencia local en **IndexedDB** (`HealthSurveyDB`).
* 🔄 **Modalidades de Encuesta:**
  - **Ambulante / Semiestacionario:** 4 fotografías (la Parte II de condiciones de trabajo se desactiva y limpia automáticamente).
  - **Estacionario:** 5 fotografías (se procesa e incluye la quinta hoja completa).
* 👁️ **Procesamiento de Visión Multimodal:**
  - Auto-rotación inteligente de imágenes horizontales a verticales.
  - Escalado y compresión adaptativa a 1600px para máxima fidelidad OCR y bajo consumo de ancho de banda.
  - Soporte híbrido: **Google Gemini Vision** (`gemini-3.5-flash-lite` / `gemini-2.5-flash`) con opción de fallback local mediante **Ollama** (`minicpm-v`).
* 📊 **Catálogo Estricto de 64 Columnas:**
  - Normalización unificada de fechas (`YYYY-MM-DD`).
  - Validación cruzada de nombres dudosos contra sexo biológico.
  - Prevención de desplazamiento vertical en matrices tabulares densas.
* 🌐 **Envío Resiliente a Google Sheets:** Conexión directa mediante Webhook de Google Apps Script con cola de sincronización por lotes.

---

## 📂 Estructura del Proyecto

```text
PROJ_003_Extractor_Encuestas_Salud/
├── app.py                                <-- Servidor Backend FastAPI (Endpoints REST y SPA)
├── core_extractor.py                     <-- Motor multimodal, normalización y catálogo de 64 columnas
├── procesar_encuestas.py                 <-- CLI ejecutable para procesamiento local
├── test_integration.py                   <-- Suite de pruebas automatizadas E2E
├── static/                               <-- SPA / PWA Móvil (Kinetic Field System)
│   ├── index.html                        <-- Interfaz de captura táctil, cámara y bandeja
│   └── storage.js                        <-- Capa de persistencia IndexedDB
├── .env                                  <-- Configuración de API Keys y endpoints
└── README.md                             <-- Documentación técnica de ejecución
```

---

## 🚀 Guía de Instalación y Ejecución

### 1. Configuración de Variables de Entorno (`.env`)
Verifica que las siguientes claves estén configuradas en el archivo `.env`:
```env
GEMINI_API_KEY=tu_clave_de_gemini
DEFAULT_LLM_PROVIDER=gemini
WEBHOOK_URL=https://script.google.com/macros/s/.../exec
```

### 2. Iniciar el Servidor FastAPI y PWA
Desde la raíz del proyecto:
```bash
python app.py
```
O con Uvicorn:
```bash
uvicorn app:app --host 127.0.0.1 --port 8000 --reload
```
Abre tu navegador en `http://127.0.0.1:8000` para acceder a la aplicación móvil.

### 3. Ejecutar Pruebas Automatizadas de Integración
Ejecuta la suite completa de pruebas:
```bash
python test_integration.py
```
La suite valida:
1. Auto-rotación y compresión de imágenes a 1600px.
2. Normalización de fechas a formato `YYYY-MM-DD`.
3. Lógica de modalidades (Semiestacionario vs Ambulante vs Estacionario).
4. Directivas de prompt anti-desplazamiento vertical.
5. Diagnóstico de salud (`/api/health`).
6. Envío real de prueba al Webhook de Google Sheets (`/api/webhook-test`).

---

## 🏛️ Arquitectura Técnica y Capacidades
* **PWA Móvil Offline-First:** Persistencia en IndexedDB, captura y compresión de fotos in situ, reintentos exponenciales.
* **Extracción Multimodal con Gemini Vision:** Catálogo estricto de 64 columnas con validación cruzada y anti-desplazamiento.
* **Integración Google Sheets:** Despacho automatizado mediante Webhook de Google Apps Script.
