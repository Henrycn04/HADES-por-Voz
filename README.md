# HADES por Voz

## Descripción del proyecto
El objetivo del proyecto es explorar cómo un agente conversacional con memoria contextual puede aprender patrones personales a partir de interacciones simples y utilizarlos para interpretar situaciones futuras.

## Prototipo actual
Este prototipo implementa una primera versión de **HADES por Voz**:

- Conversación inicial por texto.
- Respuestas habladas con Gemini TTS.
- Extracción de patrones personales usando Gemini.
- Memoria contextual guardada en JSON.
- Interpretación de situaciones nuevas.
- STT provisional.

## Arquitectura

```text
Usuario escribe
  ↓
main.py
  ↓
ConversationAgent
  ↓
PatternExtractor con Gemini
  ↓
MemoryManager JSON
  ↓
ContextInterpreter con Gemini
  ↓
Respuesta de HADES + Gemini TTS (provisional)
```

## Instalación en Windows

```powershell
py -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

Luego abrí `.env` y pegue su API key:

```text
GEMINI_API_KEY=tu_api_key
```

## Ejecutar

```powershell
python main.py
```

## Flujo

1. Elegir `1. Conversación inicial para aprender patrones`.
2. Contestar las preguntas como usuario.
3. Elegir `3. Ver memoria JSON` para enseñar qué aprendió.
4. Elegir `2. Probar una situación actual`.
5. Probar algo como:

```text
Son las 9:40 PM, llegué tarde, tomé café y mañana tengo agenda libre.
```

La respuesta debería detectar que hay una posible desviación del patrón normal.

## Investigación

Este prototipo implementa los conceptos propuestos en la investigación:

- Memoria contextual del usuario
- Extracción de patrones desde conversación
- Interpretación de desviaciones de comportamiento