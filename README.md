# HADES por Voz

**HADES por Voz** es un prototipo de asistente doméstico conversacional con memoria contextual.  
El sistema está desarrollado en Python y se ejecuta de forma local, integrando activación por palabra clave, reconocimiento de voz, modelo de lenguaje local, síntesis de voz y memoria persistente por perfil de usuario.

El objetivo del proyecto es explorar cómo un agente doméstico puede ir más allá de responder comandos directos, aprendiendo patrones, hábitos y preferencias del usuario para ofrecer una interacción más natural, contextual y personalizada.

## Enlaces del proyecto

- **Repositorio:** https://github.com/Henrycn04/HADES-por-Voz
- **Video de demostración:** https://youtu.be/-ljTmLNjrvM
- **Documento del Entregable 2:** `docs/Entregable_2_HADES_por_Voz.pdf`
- **Protocolo experimental:** `docs/Guia_Procedimiento_HADES_por_Voz.html`

## Estado actual del prototipo

La versión actual de HADES por Voz implementa una Prueba de Concepto funcional con los siguientes componentes:

- Activación por palabra clave usando **openWakeWord**.
- Reconocimiento de voz local usando **Whisper**.
- Procesamiento conversacional local usando **Ollama** con **Gemma 4 8B**.
- Síntesis de voz local usando **Kokoro ONNX**.
- Gestión de perfiles individuales.
- Memoria persistente en archivos JSON.
- Historial conversacional.
- Historial de acciones domésticas simuladas.
- Extracción de patrones, rutinas y preferencias.
- Simulación de comandos domésticos como alarmas, recordatorios, luces, música y ajustes de rutina.

Actualmente el prototipo no controla dispositivos reales del hogar. Las acciones domésticas se simulan y se registran en memoria para demostrar la viabilidad de la arquitectura y la lógica de contextualización.

## Arquitectura general

```text
Usuario
  ↓
Wake word / Activación por palabra clave
  openWakeWord
  ↓
Captura de audio
  Micrófono del sistema
  ↓
Reconocimiento de voz
  Whisper local
  ↓
Texto del usuario
  ↓
Agente conversacional
  Python + HADES Assistant
  ↓
Modelo de lenguaje local
  Ollama + Gemma 4 8B
  ↓
Memoria contextual
  Perfil activo + JSON persistente
  ↓
Historial y patrones
  conversation_history / action_history / patterns
  ↓
Síntesis de voz
  Kokoro ONNX
  ↓
Respuesta hablada al usuario
```

## Memoria contextual

La memoria se organiza por perfil de usuario. Cada perfil puede almacenar:

- `conversation_history`: historial de conversación entre el usuario y HADES.
- `action_history`: acciones domésticas simuladas, como alarmas, luces o recordatorios.
- `patterns`: rutinas, preferencias o hábitos recurrentes detectados.
- `open_questions`: preguntas abiertas o información pendiente.
- `profile_summary`: resumen general del perfil.

La separación entre acciones y patrones es importante: una frase como “poné una alarma a las 7” se registra como acción puntual, mientras que una frase como “normalmente me despierto a las 7 entre semana” puede convertirse en un patrón recurrente.

## Funcionalidades implementadas

- Ejecución local en Python.
- Menú principal en terminal.
- Creación y carga de perfiles.
- Modo HADES por voz.
- Activación con wake word.
- Reconocimiento de voz con Whisper.
- Respuestas habladas con Kokoro ONNX.
- Procesamiento conversacional con Ollama y Gemma 4 8B.
- Memoria persistente por perfil.
- Registro de conversaciones.
- Registro de acciones simuladas.
- Extracción de patrones de rutina.
- Recuperación de contexto previo.
- Diferenciación inicial entre eventos puntuales y rutinas recurrentes.

## Funcionalidades pendientes

- Integración con dispositivos reales del hogar.
- Interfaz gráfica más amigable.
- Mayor robustez ante errores de STT.
- Mejor interpretación temporal de comandos ambiguos.
- Validación automática de patrones aprendidos.
- Evaluación piloto con compañeros del curso.
- Integración futura con sensores o módulos contextuales del hogar.

## Requisitos generales

- Windows 10/11.
- Python 3.10 o superior.
- Micrófono funcional.
- Dispositivo de salida de audio.
- Ollama instalado.
- Modelo Gemma 4 8B disponible en Ollama.
- Dependencias instaladas desde `requirements.txt`.

## Instalación en Windows

Crear y activar entorno virtual:

```powershell
py -m venv .venv
.\.venv\Scripts\activate
```

Instalar dependencias:

```powershell
pip install -r requirements.txt
```

Copiar archivo de variables de entorno:

```powershell
copy .env.example .env
```

Editar `.env` según la configuración local del sistema.

## Configuración de Ollama

Verificar que Ollama esté instalado y funcionando:

```powershell
ollama --version
```

Descargar o preparar el modelo configurado para el proyecto:

```powershell
ollama pull gemma4:8b
```

> Nota: el nombre exacto del modelo puede variar según la configuración local usada en Ollama. Revisar el archivo de configuración o `.env.example`.

## Ejecución

Ejecutar el programa principal:

```powershell
python main.py
```

Flujo básico:

1. Iniciar el sistema.
2. Crear o seleccionar un perfil.
3. Entrar al modo HADES.
4. Activar el asistente con la palabra clave.
5. Dar un comando o conversar con el agente.
6. Revisar la memoria JSON generada.

## Ejemplos de interacción

Comando puntual:

```text
Hey Jarvis, poné una alarma a las siete.
```

Resultado esperado:

- HADES confirma la alarma.
- La acción se registra en `action_history`.
- No se crea un patrón permanente si no hay señal de recurrencia.

Rutina recurrente:

```text
Hey Jarvis, normalmente me duermo a las diez y media, entonces apagá las luces a esa hora.
```

Resultado esperado:

- HADES confirma el ajuste simulado.
- La acción se registra en `action_history`.
- La rutina puede registrarse como patrón en `patterns`.

Consulta posterior:

```text
Hey Jarvis, ¿qué sabes de mi rutina de sueño?
```

Resultado esperado:

- HADES recupera información del perfil activo.
- El agente responde usando la memoria contextual disponible.

## Revisión de dispositivos de audio

Para revisar entradas y salidas de audio disponibles en Windows:

```powershell
python -c "import sounddevice as sd; [print(i, d['name'], '| in:', d['max_input_channels'], '| out:', d['max_output_channels'], '| host:', sd.query_hostapis()[d['hostapi']]['name']) for i, d in enumerate(sd.query_devices())]"
```

## Estructura del repositorio

```text
HADES-por-Voz/
│
├── agent/
│   ├── hades_assistant.py
│   ├── llm_factory.py
│   └── ollama_client.py
│
├── memory/
│   └── memory_manager.py
│
├── pattern_extraction/
│   └── pattern_extractor.py
│
├── voice/
│   ├── audio_cues.py
│   ├── kokoro_tts.py
│   ├── wake_word.py
│   └── whisper_stt.py
│
├── models/
│   └── kokoro/
│
├── records/
│   └── memorias y logs locales
│
├── docs/
│   ├── Entregable_2_HADES_por_Voz.pdf
│   ├── Guia_Procedimiento_HADES_por_Voz.html
│   └── img/
│
├── .env.example
├── .gitignore
├── README.md
├── requirements.txt
└── main.py
```

## Consideraciones de privacidad

HADES por Voz está diseñado como un prototipo local porque trabaja con información personal del usuario, como rutinas, preferencias, acciones y horarios. Por eso:

- No se deben subir archivos `.env` al repositorio.
- No se deben subir memorias reales de usuarios.
- No se deben subir logs personales.
- La carpeta `records/` debe mantenerse fuera del repositorio si contiene datos reales.
- Los ejemplos incluidos en `docs/` deben ser ficticios o anonimizados.

## Investigación

Este prototipo forma parte del proyecto:

**HADES por Voz: Agente Virtual Conversacional con Memoria Contextual para el Hogar**

Las preguntas de investigación principales son:

1. ¿Cómo influye la memoria contextual en la percepción de naturalidad y utilidad de un agente virtual doméstico?
2. ¿Qué tipo de rutinas, preferencias o patrones personales puede aprender un agente virtual a partir de interacciones conversacionales simples en un periodo corto de tiempo?
3. ¿En qué medida retomar conversaciones previas y sugerir acciones personalizadas mejora la experiencia del usuario, y cuándo podría percibirse como invasivo?

## Entregable 2

El Entregable 2 incluye:

- Documento de avance en PDF.
- Protocolo experimental en HTML.
- Evidencia visual del prototipo.
- Video de demostración.
- Diseño metodológico del estudio piloto.
- Métricas, instrumentos y protocolos de interacción.
