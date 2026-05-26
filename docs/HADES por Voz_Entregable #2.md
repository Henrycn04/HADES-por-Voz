# Entregable 2: Diseño Metodológico y Protocolo Experimental

**Proyecto:** HADES por Voz: Agente Virtual Conversacional con Memoria Contextual para el Hogar  
**Curso:** PF-3311 Agentes Virtuales Inteligentes  
**Estudiante:** Henry Campos Navarro — C21636  
**Universidad:** Universidad de Costa Rica, ECCI  
**Año:** 2026  

## Apartado A. Definición de condiciones

**Condición A:** HADES por Voz, agente doméstico conversacional con memoria contextual y detección de patrones. Durante una conversación de 10 a 20 minutos, el participante comparte hábitos, intereses y rutinas. El agente registra logs anonimizados y genera patrones revisables.

**Condición B:** experiencia previa reportada con asistentes tradicionales como Alexa, Google Home o Siri. Se usa como baseline porque estos sistemas suelen operar mediante comandos directos, consultas puntuales y automatizaciones explícitas.

**Justificación:** la comparación permite observar si HADES se percibe como más natural, útil, continuo o proactivo que la experiencia previa con asistentes tradicionales. Aunque es menos controlado que un A/B completo, es adecuado para una Prueba de Concepto inicial.

## Apartado B. Matriz de consistencia metodológica

| RQ | Variable o constructo | Instrumento / fuente | Tarea |
|---|---|---|---|
| RQ1. ¿Cómo influye la memoria contextual en la percepción de naturalidad y utilidad de un agente virtual doméstico? | Naturalidad, utilidad, continuidad y usabilidad. | UEQ + cuestionario propio. | Conversar con HADES y comparar la experiencia con asistentes tradicionales. |
| RQ2. ¿Qué tipo de rutinas, preferencias o patrones personales puede aprender un agente virtual a partir de interacciones conversacionales simples en un periodo corto de tiempo? | Precisión percibida y utilidad de patrones. | Logs + revisión de patrones con el participante. | Revisar patrones generados por HADES y clasificarlos. |
| RQ3. ¿En qué medida retomar conversaciones previas y sugerir acciones personalizadas mejora la experiencia del usuario, y cuándo podría percibirse como invasivo? | Proactividad, invasividad, privacidad y disposición de uso. | Cuestionario propio con ítems Likert y preguntas abiertas. | Evaluar interpretaciones y sugerencias del agente. |

Las variables dependientes son naturalidad, utilidad percibida, precisión percibida de patrones, continuidad conversacional, proactividad, invasividad y usabilidad general.

## Apartado C. Protocolo HTML

El protocolo adaptado se entrega como `Guia_Procedimiento_HADES_por_Voz.html`. Mantiene la estructura del formulario original e incluye consentimiento, baseline, carga de HADES, instrucciones neutras, revisión de patrones, cuestionarios post-interacción y anonimización.

## Apartado D. Justificación teórica en HCI

HADES por Voz no utiliza un avatar visual fuerte porque esta Prueba de Concepto no busca evaluar apariencia, gestos, animación facial ni representación corporal del agente. La decisión de diseño se centra en una presencia conversacional construida mediante voz o texto, continuidad del diálogo y uso de memoria contextual. Desde la perspectiva de Justine Cassell sobre agentes conversacionales encarnados, la presencia social de un agente no depende únicamente de tener un cuerpo visual, sino también de su capacidad para organizar la interacción, mantener turnos conversacionales y responder de forma situada. En HADES, ese soporte social se traslada a la manera en que el agente escucha, retoma información previa y convierte lo conversado en patrones revisables por el usuario.

El diseño también se relaciona con el soporte relacional planteado por Timothy Bickmore. Un agente relacional no se limita a resolver comandos aislados, sino que mantiene cierta continuidad con la persona, recuerda información relevante y adapta sus respuestas a interacciones anteriores. HADES intenta explorar esa idea en un contexto doméstico: en lugar de funcionar únicamente como Alexa, Google Home o Siri ante órdenes directas, busca detectar hábitos, intereses y rutinas a partir de una conversación inicial. Sin embargo, esta relación debe ser limitada y transparente, porque recordar o interpretar información personal puede resultar incómodo. Por eso, el protocolo incluye una revisión explícita de los patrones detectados, donde el participante puede indicar si las inferencias fueron correctas, útiles o invasivas.

Finalmente, el Efecto Proteus de Nick Yee y Jeremy Bailenson funciona como una advertencia metodológica. Si se incorporara un avatar humano con género, edad, expresiones o rasgos físicos definidos, la conducta del participante podría verse influida por la apariencia del agente y no necesariamente por la memoria contextual. Al reducir el componente visual, la evaluación se enfoca mejor en la variable central del proyecto: la capacidad del agente para generar continuidad, detectar patrones y ofrecer una experiencia personalizada. Esta decisión también se conecta con la tensión entre personalización y privacidad: HADES puede ser más útil si recuerda información, pero también puede ser percibido como invasivo si interpreta demasiado. Por eso, el uso de IDs anónimos, el resguardo seguro de logs y la validación de patrones con el participante son partes esenciales del diseño metodológico.

## Referencias

[1] J. Cassell, “Embodied Conversational Agents,” AI Magazine, 2001.  
[2] T. W. Bickmore and R. W. Picard, “Establishing and Maintaining Long-Term Human-Computer Relationships,” ACM TOCHI, 2005.  
[3] N. Yee and J. N. Bailenson, “The Proteus Effect,” Human Communication Research, 2007.  
[4] M. Schrepp, A. Hinderks, and J. Thomaschewski, “Applying the User Experience Questionnaire (UEQ) in Different Evaluation Scenarios,” 2014.
