# HADES por Voz

**HADES por Voz** es un prototipo funcional de asistente doméstico conversacional con memoria contextual.  
El sistema está desarrollado en Python y se ejecuta de forma local, integrando interacción por voz y texto, activación por palabra clave, activación manual por teclado, reconocimiento de voz, modelo de lenguaje local, síntesis de voz y memoria persistente por perfil de usuario.

El objetivo del proyecto es explorar cómo un agente doméstico puede ir más allá de responder comandos directos, aprendiendo patrones, hábitos y preferencias del usuario para ofrecer una interacción más natural, contextual y personalizada.

---

## Enlaces del proyecto

- **Repositorio:** https://github.com/Henrycn04/HADES-por-Voz
- **Video final de demostración:** https://youtu.be/tfBvssxGFTk?si=2AYXxT9mR6NuoTG1
- **Artículo académico final:** `docs/HADES_por_Voz_Entregable_3.pdf`
- **Documento del Entregable 2:** `docs/Entregable_2_HADES_por_Voz.pdf`
- **Protocolo experimental:** `docs/Guia_Procedimiento_HADES_por_Voz.html`

---

## Entregable 3 – Entrega Final, Artículo Académico y Presentación de HADES por Voz

Este repositorio corresponde a la versión final del proyecto para el curso **PF-3311 Agentes Virtuales Inteligentes**.

El Entregable 3 incluye:

- Prototipo funcional de HADES por Voz.
- Artículo académico final en formato PDF.
- Video final de demostración no listado en YouTube.
- Evidencia de interacción con el agente.
- Evaluación piloto exploratoria con usuarios.
- Resultados descriptivos del cuestionario UEQ, cuestionario propio y revisión de logs anonimizados.
- Discusión de limitaciones, conclusiones y trabajo futuro.

El estudio realizado debe interpretarse como un **piloto exploratorio con n = 2**, no como una evaluación estadísticamente generalizable. El objetivo fue obtener evidencia inicial sobre la utilidad de la memoria contextual, la naturalidad de la interacción, la percepción de control y los límites del prototipo.

---

## Estado final del prototipo

La versión actual de HADES por Voz implementa una Prueba de Concepto funcional con los siguientes componentes:

- Activación por palabra clave usando **openWakeWord**.
- Activación manual por teclado usando **ESPACIO** cuando la línea de chat está vacía.
- Entrada por texto mediante una línea de chat en terminal.
- Cancelación mediante **ESC** durante escucha, transcripción, respuesta del LLM o reproducción TTS.
- Reconocimiento de voz local usando **Whisper**.
- Procesamiento conversacional local usando **Ollama** con **Gemma 4 8B**.
- Síntesis de voz local usando **Kokoro ONNX**.
- Gestión de perfiles individuales.
- Memoria persistente en archivos JSON.
- Historial conversacional.
- Historial de acciones domésticas simuladas.
- Extracción de patrones, rutinas y preferencias.
- Detección de patrones por señales explícitas de recurrencia y por repetición.
- Simulación de comandos domésticos como alarmas, recordatorios, luces, música y ajustes de rutina.
- Comandos para olvidar o borrar información guardada incorrectamente.
- Edición y cancelación simulada de alarmas y recordatorios.
- Desambiguación cuando existen varias alarmas posibles.
- Recuperación de contexto previo para responder preguntas sobre rutinas aprendidas.

Actualmente el prototipo **no controla dispositivos reales del hogar**. Las acciones domésticas se simulan y se registran en memoria para demostrar la viabilidad de la arquitectura y la lógica de contextualización.

---

## Modos de interacción

HADES puede recibir entrada del usuario de tres formas.

### 1. Wake word

El usuario puede activar el sistema diciendo la palabra clave configurada:

```text
Hey Jarvis
```

Después de detectar la palabra clave, el sistema emite un cue corto y comienza a grabar el comando.

### 2. Activación por espacio

En modo HADES aparece una línea de entrada:

```text
Chat>
```

Si la línea está vacía y el usuario presiona **ESPACIO**, el sistema empieza a grabar como si se hubiera activado por wake word.

Este comportamiento solo se activa cuando el campo de chat está vacío. Si el usuario ya escribió texto, la barra espaciadora funciona normalmente como parte del mensaje.

### 3. Chat escrito

El usuario puede escribir directamente en la línea:

```text
Chat> recordame tomar agua a las 8
```

Al presionar **Enter**, el texto entra al mismo flujo del agente: procesamiento con LLM, memoria contextual, acciones simuladas, patrones y respuesta.

### Cancelación con ESC

La tecla **ESC** permite cancelar la interacción actual y regresar al estado de espera. Puede usarse durante:

- grabación de audio;
- transcripción STT;
- generación de respuesta con LLM;
- extracción de patrones;
- reproducción TTS.

En el caso del LLM, la cancelación es cooperativa: si la petición ya fue enviada a Ollama, el sistema puede ignorar el resultado y volver a estado idle, aunque la petición local haya quedado procesándose por unos segundos.

---

## Arquitectura general

```text
Usuario
  ↓
Entrada por voz o texto
  Wake word / ESPACIO / Chat escrito
  ↓
Captura de audio o texto
  Micrófono / Terminal
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
Historial, acciones y patrones
  conversation_history / action_history / patterns
  ↓
Síntesis de voz
  Kokoro ONNX
  ↓
Respuesta al usuario
  Voz y/o texto en terminal
```

---

## Memoria contextual

La memoria se organiza por perfil de usuario. Cada perfil puede almacenar:

- `conversation_history`: historial de conversación entre el usuario y HADES.
- `action_history`: acciones domésticas simuladas, como alarmas, luces o recordatorios.
- `patterns`: rutinas, preferencias o hábitos recurrentes detectados.
- `open_questions`: preguntas abiertas o información pendiente.
- `profile_summary`: resumen general del perfil.

La separación entre acciones y patrones es importante: una frase como “poné una alarma a las 7” se registra como acción puntual, mientras que una frase como “normalmente me despierto a las 7 entre semana” puede convertirse en un patrón recurrente.

---

## Reglas de memoria implementadas

La versión actual incluye reglas para reducir falsos positivos en memoria:

- No todo mensaje del usuario se guarda como patrón.
- Los eventos puntuales se registran como acciones, no como rutinas permanentes.
- Los patrones requieren señales de recurrencia o repetición.
- Las respuestas de HADES no deben usarse como evidencia para crear patrones del usuario.
- La memoria previa contextualiza, pero no debe reemplazar el comando actual.
- Las acciones relacionadas con salud, pastillas, medicamentos o vitaminas se normalizan en un dominio único para evitar duplicados.
- Los patrones repetidos pueden consolidarse en lugar de crear entradas innecesariamente duplicadas.

Señales que pueden indicar estabilidad o rutina:

```text
normalmente
usualmente
suelo
siempre
todos los días
días laborales
lunes a viernes
entre semana
cada mañana
todas las mañanas
rutina
prefiero
me gusta
no me gusta
```

También se contempla la detección por repetición. Por ejemplo, si el usuario menciona varias veces que se duerme a las 10, el sistema puede inferir que existe una posible rutina de sueño, aun si no siempre usa la palabra “normalmente”.

---

## Acciones simuladas

HADES registra acciones domésticas simuladas en `action_history`. Tipos de acciones contempladas:

- `alarm`
- `alarm_update`
- `alarm_cancel`
- `reminder`
- `reminder_update`
- `reminder_cancel`
- `light`
- `music`
- `do_not_disturb`
- `routine_adjustment`
- `other`

Ejemplos:

```text
Poné una alarma a las 7 de la mañana.
```

```text
Recordame tomar agua a las 8.
```

```text
Apagá las luces a las 10:30 de la noche.
```

```text
Cancelá la alarma de las 7.
```

```text
Editá la alarma de las 7 a las 8.
```

---

## Comandos de corrección de memoria

Durante pruebas o interacciones reales puede ocurrir que el agente guarde algo incorrecto. Para corregirlo, se agregaron comandos de olvido.

Ejemplos:

```text
Olvida eso.
```

```text
Borra eso.
```

```text
Borra lo último.
```

```text
Borra el último patrón.
```

```text
Olvida el último patrón.
```

```text
Borra la última acción.
```

```text
Olvida la última acción.
```

Estos comandos eliminan elementos recientes de `patterns` o `action_history`, sin borrar el historial conversacional completo.

---

## Edición y cancelación de alarmas

El sistema puede registrar edición y cancelación simulada de alarmas. Si el usuario da suficiente información, HADES intenta resolver la alarma directamente.

Ejemplos:

```text
Editá la alarma de las 7 a las 8.
```

```text
Cancelá la alarma de las 7.
```

Si el usuario no especifica cuál alarma desea modificar y existen varias alarmas registradas, HADES debe listar las opciones disponibles y preguntar cuál desea editar o cancelar.

Ejemplo:

```text
Editá la alarma.
```

Respuesta esperada:

```text
Tengo varias alarmas registradas:
1. Alarma para las 7:00 AM.
2. Alarma para las 10:00 PM.
¿Cuál querés editar?
```

El usuario puede responder por número o por referencia de hora:

```text
La primera.
```

```text
La de las 7.
```

```text
La segunda.
```

---

## Funcionalidades implementadas

- Ejecución local en Python.
- Menú principal en terminal.
- Creación y carga de perfiles.
- Modo HADES por voz.
- Activación con wake word.
- Activación manual con **ESPACIO**.
- Chat escrito desde terminal.
- Cancelación con **ESC**.
- Reconocimiento de voz con Whisper.
- Respuestas habladas con Kokoro ONNX.
- Procesamiento conversacional con Ollama y Gemma 4 8B.
- Memoria persistente por perfil.
- Registro de conversaciones.
- Registro de acciones simuladas.
- Extracción de patrones de rutina.
- Detección de patrones por repetición.
- Recuperación de contexto previo.
- Diferenciación entre eventos puntuales y rutinas recurrentes.
- Corrección de falsos positivos como `siete` interpretado como `sí`.
- Mejor manejo de referencias temporales como mañana, noche, tarde, AM y PM.
- Manejo más conservador de recordatorios relativos ambiguos.
- Comandos para olvidar la última acción o patrón.
- Edición y cancelación simulada de alarmas y recordatorios.
- Desambiguación cuando existen varias alarmas posibles.

---

## Limitaciones actuales

- Las acciones domésticas son simuladas y no controlan dispositivos reales.
- El reconocimiento de voz puede cometer errores en ambientes ruidosos o con frases ambiguas.
- La interpretación temporal todavía requiere mejoras.
- La revisión de memoria se realiza principalmente mediante JSON, no mediante una interfaz gráfica.
- La evaluación realizada fue piloto exploratoria con n = 2, por lo que sus resultados no son generalizables.
- El sistema requiere configuración local de dependencias, modelos y dispositivos de audio.

---

## Trabajo futuro

- Integración con dispositivos reales del hogar.
- Interfaz gráfica más amigable para revisar memoria y patrones.
- Mayor robustez ante errores de STT.
- Validación automática más extensa de patrones aprendidos.
- Exportación de sesiones de prueba.
- Modo debug visual para mostrar intención, dominio y acción detectada.
- Ampliación del estudio con más participantes y sesiones más largas.
- Integración futura con sensores o módulos contextuales del hogar.

---

## Requisitos generales

- Windows 10/11.
- Python 3.10 o superior. Recomendado: Python 3.11.
- Micrófono funcional.
- Dispositivo de salida de audio.
- Ollama instalado.
- Modelo Gemma 4 8B disponible en Ollama.
- Dependencias instaladas desde `requirements.txt`.
- FFmpeg instalado y disponible en `PATH`.
- eSpeak-NG instalado si Kokoro/phonemizer lo requiere en el entorno local.

---

## Instalación en Windows

Crear y activar entorno virtual:

```powershell
python -m venv .venv
.\.venv\Scripts\activate
```

Actualizar herramientas base:

```powershell
python -m pip install --upgrade pip setuptools wheel
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

> Nota: en algunos equipos Windows también funciona `py -m venv .venv`, pero si `py` no está disponible, usar `python -m venv .venv`.

---

## Dependencias externas del sistema

Whisper requiere FFmpeg instalado y disponible en `PATH`.

Verificar:

```powershell
ffmpeg -version
```

Instalar con Winget:

```powershell
winget install Gyan.FFmpeg
```

Kokoro/phonemizer puede requerir eSpeak-NG.

Verificar:

```powershell
espeak-ng --version
```

Instalar con Winget:

```powershell
winget install eSpeak-NG.eSpeak-NG
```

Después de instalar herramientas del sistema, cerrar y abrir nuevamente la terminal.

---

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

---

## Variables de entorno

El archivo `.env.example` contiene la estructura de configuración esperada. Variables típicas:

```env
HADES_LLM_PROVIDER=ollama
HADES_OLLAMA_MODEL=gemma4:8b
HADES_OLLAMA_HOST=http://localhost:11434

HADES_ENABLE_WAKE_WORD=true
HADES_WAKE_WORD=hey jarvis
HADES_WAKE_THRESHOLD=0.85
HADES_WAKE_COOLDOWN_SECONDS=1.5

HADES_MIC_DEVICE_ID=11
HADES_AUDIO_OUTPUT_DEVICE_ID=14

HADES_ENABLE_AUDIO_CUES=true
HADES_CUE_VOLUME=0.5

HADES_ENABLE_TTS=true
HADES_TTS_VOICE=em_alex
HADES_TTS_SPEED=1.15
```

Los identificadores de micrófono y salida de audio deben ajustarse según cada computadora.

---

## Ejecución

Ejecutar el programa principal:

```powershell
python main.py
```

Flujo básico:

1. Iniciar el sistema.
2. Crear o seleccionar un perfil.
3. Entrar al modo HADES.
4. Usar wake word, barra espaciadora o chat escrito.
5. Dar un comando o conversar con el agente.
6. Revisar la memoria JSON generada si se desea validar acciones y patrones.

---

## Ejemplos de interacción

### Comando puntual

```text
Hey Jarvis, poné una alarma a las siete.
```

Resultado esperado:

- HADES confirma la alarma.
- La acción se registra en `action_history`.
- No se crea un patrón permanente si no hay señal de recurrencia.

### Rutina recurrente

```text
Hey Jarvis, normalmente me duermo a las diez y media, entonces apagá las luces a esa hora.
```

Resultado esperado:

- HADES confirma el ajuste simulado.
- La acción se registra en `action_history`.
- La rutina puede registrarse como patrón en `patterns`.

### Consulta posterior

```text
Hey Jarvis, ¿qué sabes de mi rutina de sueño?
```

Resultado esperado:

- HADES recupera información del perfil activo.
- El agente responde usando la memoria contextual disponible.

### Olvidar memoria reciente

```text
Olvida eso.
```

Resultado esperado:

- HADES elimina la última acción o patrón relevante guardado.
- La conversación se mantiene en historial.

### Editar alarma ambigua

```text
Editá la alarma.
```

Resultado esperado:

- Si existen varias alarmas, HADES lista todas las opciones y pregunta cuál se desea editar.

---

## Revisión de dispositivos de audio

Para revisar entradas y salidas de audio disponibles en Windows:

```powershell
python -c "import sounddevice as sd; [print(i, d['name'], '| in:', d['max_input_channels'], '| out:', d['max_output_channels'], '| host:', sd.query_hostapis()[d['hostapi']]['name']) for i, d in enumerate(sd.query_devices())]"
```

---

## Estructura del repositorio

```text
HADES-por-Voz/
│
├── agent/
│   ├── hades_assistant.py
│   ├── llm_factory.py
│   ├── ollama_client.py
│   └── prompts.py
│
├── config/
│   └── settings.py
│
├── memory/
│   ├── __init__.py
│   └── memory_manager.py
│
├── pattern_extraction/
│   └── pattern_extractor.py
│
├── ui/
│   ├── __init__.py
│   └── terminal_input.py
│
├── voice/
│   ├── audio_cues.py
│   ├── kokoro_tts.py
│   ├── speech_to_text.py
│   └── wake_word.py
│
├── models/
│   └── kokoro/
│
├── records/
│   └── memorias y logs locales
│
├── docs/
│   ├── HADES_por_Voz_Entregable_3.pdf
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

---

## Consideraciones de privacidad

HADES por Voz está diseñado como un prototipo local porque trabaja con información personal del usuario, como rutinas, preferencias, acciones y horarios. Por eso:

- No se deben subir archivos `.env` al repositorio.
- No se deben subir API keys ni credenciales.
- No se deben subir memorias reales de usuarios.
- No se deben subir logs personales.
- La carpeta `records/` debe mantenerse fuera del repositorio si contiene datos reales.
- Los ejemplos incluidos en `docs/` deben ser ficticios o anonimizados.
- Los perfiles usados para pruebas con participantes deben ser perfiles de demostración o estar anonimizados.

---

## Investigación

Este prototipo forma parte del proyecto:

**HADES por Voz: Agente Virtual Conversacional con Memoria Contextual para el Hogar**

Curso: **PF-3311 Agentes Virtuales Inteligentes**  
Universidad de Costa Rica, Escuela de Ciencias de la Computación e Informática.

Las preguntas de investigación principales son:

1. ¿Cómo influye la memoria contextual en la percepción de naturalidad y utilidad de un agente virtual doméstico?
2. ¿Qué tipo de rutinas, preferencias o patrones personales puede aprender un agente virtual a partir de interacciones conversacionales simples en un periodo corto de tiempo?
3. ¿En qué medida retomar conversaciones previas y sugerir acciones personalizadas mejora la experiencia del usuario, y cuándo podría percibirse como invasivo?

---

## Entregable 2

El Entregable 2 incluyó:

- Documento de avance en PDF.
- Protocolo experimental en HTML.
- Evidencia visual del prototipo.
- Video de demostración inicial.
- Diseño metodológico del estudio piloto.
- Métricas, instrumentos y protocolos de interacción.

---

## Entregable 3

El Entregable 3 incluye:

- Artículo académico final en PDF.
- Video final de demostración.
- Prototipo funcional actualizado.
- Resultados de evaluación piloto.
- Discusión de limitaciones y trabajo futuro.
- Repositorio documentado para reproducción local.

---

## Estado de desarrollo

La versión actual corresponde a una PoC funcional final para el curso.  
El sistema está preparado para demostración y evaluación académica, manteniendo las acciones simuladas y la memoria contextual como los elementos centrales del proyecto.
