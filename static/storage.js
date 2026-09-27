/**
 * IndexedDB Storage Engine para el Digitalizador de Encuestas de Salud (PROJ-003).
 * Proporciona persistencia offline robusta en el navegador con soporte de fallback.
 */

const DB_NAME = "HealthSurveyDB";
const DB_VERSION = 1;
const STORE_SURVEYS = "surveys";

class SurveyStorage {
    constructor() {
        this.db = null;
        this.memoryFallback = new Map();
        this.useFallback = false;
    }

    async init() {
        if (this.db) return this.db;
        if (this.useFallback) return null;

        if (!window.indexedDB) {
            console.warn("IndexedDB no está disponible en este navegador. Usando fallback en memoria/localStorage.");
            this.useFallback = true;
            this.loadFromLocalStorage();
            return null;
        }

        return new Promise((resolve) => {
            try {
                const request = indexedDB.open(DB_NAME, DB_VERSION);

                request.onupgradeneeded = (event) => {
                    const db = event.target.result;
                    if (!db.objectStoreNames.contains(STORE_SURVEYS)) {
                        const store = db.createObjectStore(STORE_SURVEYS, { keyPath: "id" });
                        store.createIndex("estado", "estado", { unique: false });
                        store.createIndex("created_at", "created_at", { unique: false });
                        store.createIndex("modalidad", "modalidad", { unique: false });
                    }
                };

                request.onsuccess = (event) => {
                    this.db = event.target.result;
                    resolve(this.db);
                };

                request.onerror = (event) => {
                    console.warn("Error abriendo IndexedDB, activando fallback:", event.target.error);
                    this.useFallback = true;
                    this.loadFromLocalStorage();
                    resolve(null);
                };

                request.onblocked = () => {
                    console.warn("IndexedDB bloqueado por otra pestaña");
                    this.useFallback = true;
                    this.loadFromLocalStorage();
                    resolve(null);
                };
            } catch (e) {
                console.warn("Excepción al inicializar IndexedDB:", e);
                this.useFallback = true;
                this.loadFromLocalStorage();
                resolve(null);
            }
        });
    }

    loadFromLocalStorage() {
        try {
            const raw = localStorage.getItem("health_surveys_fallback");
            if (raw) {
                const items = JSON.parse(raw);
                items.forEach(item => this.memoryFallback.set(item.id, item));
            }
        } catch (e) {
            console.warn("No se pudo leer de localStorage:", e);
        }
    }

    saveToLocalStorage() {
        try {
            const items = Array.from(this.memoryFallback.values());
            // Guardar solo metadatos si el tamaño de fotos es muy grande para localStorage
            const lightItems = items.map(s => ({
                ...s,
                fotos: s.fotos ? s.fotos.map((f, i) => f ? f.substring(0, 100) + "...(compressed)" : null) : []
            }));
            localStorage.setItem("health_surveys_fallback", JSON.stringify(lightItems));
        } catch (e) {
            console.warn("No se pudo guardar en localStorage:", e);
        }
    }

    async saveSurvey(survey) {
        await this.init();

        if (!survey.id) {
            const timestamp = Date.now();
            const rand = Math.floor(Math.random() * 900) + 100;
            survey.id = `SURV-${timestamp}-${rand}`;
        }
        if (!survey.created_at) {
            survey.created_at = new Date().toISOString();
        }
        if (!survey.estado) {
            survey.estado = "PENDIENTE";
        }

        if (this.useFallback || !this.db) {
            this.memoryFallback.set(survey.id, survey);
            this.saveToLocalStorage();
            return survey;
        }

        return new Promise((resolve, reject) => {
            try {
                const tx = this.db.transaction([STORE_SURVEYS], "readwrite");
                const store = tx.objectStore(STORE_SURVEYS);
                
                tx.onerror = (e) => {
                    console.warn("Error en transacción IndexedDB, guardando en fallback:", e.target.error);
                    this.memoryFallback.set(survey.id, survey);
                    this.saveToLocalStorage();
                    resolve(survey);
                };

                const req = store.put(survey);
                req.onsuccess = () => {
                    this.memoryFallback.set(survey.id, survey);
                    resolve(survey);
                };
                req.onerror = (e) => {
                    console.warn("Error en put IndexedDB, guardando en fallback:", e.target.error);
                    this.memoryFallback.set(survey.id, survey);
                    this.saveToLocalStorage();
                    resolve(survey);
                };
            } catch (err) {
                console.warn("Excepción al escribir en IndexedDB, usando fallback:", err);
                this.memoryFallback.set(survey.id, survey);
                this.saveToLocalStorage();
                resolve(survey);
            }
        });
    }

    async getSurvey(id) {
        await this.init();

        if (this.useFallback || !this.db) {
            return this.memoryFallback.get(id) || null;
        }

        return new Promise((resolve) => {
            try {
                const tx = this.db.transaction([STORE_SURVEYS], "readonly");
                const store = tx.objectStore(STORE_SURVEYS);
                const req = store.get(id);
                req.onsuccess = () => resolve(req.result || this.memoryFallback.get(id) || null);
                req.onerror = () => resolve(this.memoryFallback.get(id) || null);
            } catch (e) {
                resolve(this.memoryFallback.get(id) || null);
            }
        });
    }

    async getAllSurveys() {
        await this.init();

        if (this.useFallback || !this.db) {
            const items = Array.from(this.memoryFallback.values());
            items.sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
            return items;
        }

        return new Promise((resolve) => {
            try {
                const tx = this.db.transaction([STORE_SURVEYS], "readonly");
                const store = tx.objectStore(STORE_SURVEYS);
                const req = store.getAll();
                req.onsuccess = () => {
                    const items = req.result || [];
                    // Merge memory fallback items if any missing
                    this.memoryFallback.forEach((val, key) => {
                        if (!items.find(i => i.id === key)) {
                            items.push(val);
                        }
                    });
                    items.sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
                    resolve(items);
                };
                req.onerror = () => {
                    const items = Array.from(this.memoryFallback.values());
                    items.sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
                    resolve(items);
                };
            } catch (e) {
                const items = Array.from(this.memoryFallback.values());
                items.sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
                resolve(items);
            }
        });
    }

    async getPendingSurveys() {
        const all = await this.getAllSurveys();
        return all.filter(s => s.estado === "PENDIENTE" || s.estado === "ERROR");
    }

    async updateSurveyStatus(id, estado, resultadoExtraido = null, errorMensaje = null, modalidad = null) {
        await this.init();
        let survey = await this.getSurvey(id);
        if (!survey) {
            survey = { id: id, created_at: new Date().toISOString() };
        }

        survey.estado = estado;
        if (resultadoExtraido) {
            survey.resultado_extraccion = resultadoExtraido;
            if (!modalidad && resultadoExtraido["2. Forma en la que el trabajador desarrolla su ocupación u oficio"]) {
                survey.modalidad = resultadoExtraido["2. Forma en la que el trabajador desarrolla su ocupación u oficio"];
            }
        }
        if (modalidad) {
            survey.modalidad = modalidad;
        }
        if (survey.fotos) {
            survey.total_paginas = survey.fotos.length;
        }
        if (errorMensaje !== undefined) {
            survey.error_mensaje = errorMensaje;
        }
        survey.updated_at = new Date().toISOString();

        return this.saveSurvey(survey);
    }

    async deleteSurvey(id) {
        await this.init();
        this.memoryFallback.delete(id);
        this.saveToLocalStorage();

        if (this.useFallback || !this.db) {
            return true;
        }

        return new Promise((resolve) => {
            try {
                const tx = this.db.transaction([STORE_SURVEYS], "readwrite");
                const store = tx.objectStore(STORE_SURVEYS);
                const req = store.delete(id);
                req.onsuccess = () => resolve(true);
                req.onerror = () => resolve(true);
            } catch (e) {
                resolve(true);
            }
        });
    }

    async clearCompletedSurveys() {
        const all = await this.getAllSurveys();
        for (const s of all) {
            if (s.estado === "ENVIADO") {
                await this.deleteSurvey(s.id);
            }
        }
        return true;
    }

    async countSummary() {
        const all = await this.getAllSurveys();
        return {
            total: all.length,
            pendientes: all.filter(s => s.estado === "PENDIENTE" || s.estado === "ERROR").length,
            enviados: all.filter(s => s.estado === "ENVIADO").length,
            procesando: all.filter(s => s.estado === "PROCESANDO").length
        };
    }
}

window.surveyStorage = new SurveyStorage();
