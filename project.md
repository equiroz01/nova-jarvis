NOVA Voice Agent

1. Descripción del Proyecto

NOVA Voice Agent es un asistente virtual por voz inspirado en la experiencia de Alexa/JARVIS, pero diseñado como una plataforma propia, extensible y orientada a servicios empresariales.

El objetivo es construir un asistente que pueda escuchar instrucciones en español, procesarlas mediante un LLM, ejecutar herramientas conectadas a sistemas propios y responder con una voz natural.

El proyecto no partirá desde cero. Se utilizará un proyecto open source como base inicial, principalmente llm-guy/jarvis, y se adaptará gradualmente a una arquitectura propia.

⸻

2. Objetivo

Crear un asistente de voz inteligente que pueda:

* Escuchar al usuario mediante micrófono.
* Convertir voz a texto.
* Procesar solicitudes usando un LLM.
* Responder con voz natural en español.
* Ejecutar herramientas propias.
* Consultar información de sistemas internos.
* Mantener memoria e historial.
* Funcionar como base para un producto empresarial.

⸻

3. Nombre del Proyecto

Nombre recomendado:

NOVA

Significado conceptual:

NOVA representa una inteligencia asistiva moderna, rápida y luminosa, alineada con la identidad espacial de Hypernova Labs.

Otros nombres posibles:

* AURA
* ORION
* COSMO
* ATLAS
* VEGA
* SIRIUS

⸻

4. Visión del Producto

NOVA debe evolucionar desde un asistente por voz local hasta una plataforma de agentes empresariales.

La visión final es permitir que una empresa tenga su propio asistente de voz conectado a sus sistemas internos, capaz de responder preguntas, ejecutar tareas, resumir información y apoyar procesos comerciales, operativos y de soporte.

Ejemplo:

Usuario:
"Nova, busca el cliente Farmacias Delta y dime si tiene tickets abiertos."
NOVA:
"Encontré al cliente Farmacias Delta. Tiene dos tickets abiertos. Uno está relacionado con facturación electrónica y el otro con configuración de impresora. El más reciente fue actualizado ayer."

⸻

5. Proyecto Base Recomendado

Repositorio principal sugerido:

https://github.com/llm-guy/jarvis

Razón:

Este proyecto ya incluye una base más cercana a un asistente moderno con voz, LLM, wake word y arquitectura extensible.

No se recomienda usar como base final proyectos simples de comandos fijos, ya que el objetivo de NOVA es convertirse en un agente inteligente con herramientas propias.

⸻

6. Arquitectura General

[Usuario]
   ↓
[Micrófono / Cliente Web / Cliente Desktop]
   ↓
[Wake Word o Push-to-Talk]
   ↓
[Speech-to-Text]
   ↓
[Orquestador del Agente]
   ↓
[LLM]
   ↓
[Tools / Skills]
   ↓
[Text-to-Speech]
   ↓
[Respuesta por Voz]

⸻

7. Componentes Principales

7.1 Cliente de Voz

Responsable de capturar audio y reproducir la respuesta.

Opciones iniciales:

* Cliente local en Python.
* Cliente web con micrófono.
* Cliente desktop.
* Raspberry Pi en fases futuras.

Para el MVP se recomienda iniciar con cliente local o web.

⸻

7.2 Wake Word

Permite activar el asistente mediante una palabra clave.

Opciones:

* “Nova”
* “Hey Nova”
* “Asistente”
* “Jarvis”

Para el MVP se recomienda iniciar con push-to-talk para reducir complejidad técnica. El wake word se puede agregar después.

⸻

7.3 Speech-to-Text

Convierte la voz del usuario a texto.

Opciones recomendadas:

* Whisper
* Faster Whisper
* Deepgram
* Azure Speech
* Google Speech-to-Text
* RealtimeSTT

Recomendación inicial:

Faster Whisper para pruebas locales.
Deepgram o Azure Speech para producción si se requiere baja latencia.

⸻

7.4 LLM

Modelo encargado de interpretar, razonar y decidir qué hacer.

Opciones:

* OpenAI
* Google Gemini
* Claude
* Ollama local
* Qwen local
* Llama local

Recomendación inicial:

Usar un LLM cloud para el MVP por calidad y velocidad.
Mantener Ollama como opción local para pruebas.

⸻

7.5 Orquestador

Es el núcleo del sistema.

Responsabilidades:

* Recibir el texto del usuario.
* Aplicar el prompt del sistema.
* Consultar memoria.
* Decidir si debe responder o usar una tool.
* Ejecutar herramientas.
* Validar permisos.
* Retornar una respuesta final.
* Enviar la respuesta al motor de voz.

Tecnología sugerida:

Python + FastAPI

Opcional:

LangGraph o arquitectura propia de tools.

⸻

7.6 Text-to-Speech

Convierte la respuesta textual en voz.

Opciones:

* ElevenLabs
* Azure Speech
* Google Cloud Text-to-Speech
* Piper
* Coqui TTS

Recomendación inicial:

ElevenLabs o Azure Speech para voz premium en español latino.
Piper para pruebas locales/offline.

Nota:

No se recomienda usar una imitación directa de la voz real de JARVIS/Marvel para fines comerciales. Es mejor crear una voz propia para NOVA.

⸻

7.7 Tools / Skills

Las tools permiten que NOVA haga tareas reales.

Ejemplos:

* Consultar clientes en CRM.
* Crear tickets de soporte.
* Consultar SQL Server.
* Buscar información en documentos.
* Consultar estado de cotizaciones.
* Crear borradores de correo.
* Consultar calendario.
* Consultar inventario.
* Revisar oportunidades comerciales.
* Generar propuestas.

Ejemplo:

Tool: search_customer
Entrada: nombre del cliente
Salida: datos básicos, estado comercial, tickets abiertos

⸻

7.8 Memoria y RAG

NOVA debe poder consultar documentos y recordar contexto.

Opciones:

* Qdrant
* PostgreSQL + pgvector
* Redis
* Meilisearch
* SQLite para MVP local

Usos:

* Historial de conversaciones.
* Memoria de usuario.
* Base de conocimiento.
* Documentación interna.
* Tickets históricos.
* Manuales de soporte.
* FAQs de productos.

⸻

8. Stack Técnico Inicial

MVP

Lenguaje: Python
Backend: FastAPI
STT: Faster Whisper
LLM: OpenAI / Gemini / Claude
TTS: ElevenLabs / Azure Speech
Memoria simple: SQLite o PostgreSQL
Vector DB: Qdrant
Cliente: Python local o Web
Deploy: Docker

Producción

Backend: FastAPI
Base de datos: PostgreSQL
Cache: Redis
Vector DB: Qdrant
STT: Deepgram / Azure Speech / Google Speech
LLM: OpenAI / Gemini / Claude / Ollama híbrido
TTS: ElevenLabs / Azure Speech
Observabilidad: OpenTelemetry / Application Insights
Seguridad: JWT, API Keys, RBAC
Deploy: Azure Container Apps / GCP Cloud Run / Kubernetes

⸻

9. Estructura Inicial del Proyecto

nova-voice-agent/
  README.md
  docker-compose.yml
  Dockerfile
  requirements.txt
  .env.example
  app/
    main.py
    config/
      settings.py
    agent/
      orchestrator.py
      prompts.py
      memory.py
      tools_registry.py
    stt/
      base.py
      faster_whisper_service.py
    tts/
      base.py
      elevenlabs_service.py
      azure_speech_service.py
    llm/
      base.py
      openai_service.py
      gemini_service.py
      ollama_service.py
    tools/
      base.py
      customer_tool.py
      support_tool.py
      sql_tool.py
      calendar_tool.py
      knowledge_tool.py
    audio/
      recorder.py
      player.py
    api/
      routes_health.py
      routes_agent.py
      routes_voice.py
    db/
      models.py
      repository.py
  docs/
    architecture.md
    roadmap.md
    integrations.md
    prompts.md
    security.md

⸻

10. Variables de Entorno

Archivo sugerido:

.env

Ejemplo:

APP_NAME=NOVA Voice Agent
APP_ENV=development
APP_PORT=8000
LLM_PROVIDER=openai
OPENAI_API_KEY=replace_me
GEMINI_API_KEY=replace_me
STT_PROVIDER=faster_whisper
TTS_PROVIDER=elevenlabs
ELEVENLABS_API_KEY=replace_me
ELEVENLABS_VOICE_ID=replace_me
DATABASE_URL=postgresql://user:password@localhost:5432/nova
QDRANT_URL=http://localhost:6333
QDRANT_API_KEY=replace_me
JWT_SECRET=replace_me
LOG_LEVEL=INFO

⸻

11. Prompt Base de NOVA

Eres NOVA, un asistente de voz privado creado para Hypernova Labs.
Tu objetivo es ayudar al usuario a consultar información, ejecutar tareas y resolver problemas usando herramientas internas.
Responde siempre en español claro, profesional y directo.
Cuando respondas por voz:
- Sé breve.
- Evita respuestas largas.
- Resume lo importante.
- Pregunta solo cuando sea necesario.
No ejecutes acciones críticas sin confirmación explícita del usuario.
Acciones críticas incluyen:
- Enviar correos.
- Crear cotizaciones formales.
- Modificar datos de clientes.
- Eliminar información.
- Enviar mensajes a terceros.
- Ejecutar consultas destructivas.
- Confirmar compromisos comerciales.
Si no tienes información suficiente, solicita una aclaración breve.
Si usas una herramienta, resume el resultado de forma clara.

⸻

12. Primeros Casos de Uso

Caso 1: Conversación básica

Usuario:
"Nova, explícame qué puedes hacer."
NOVA:
"Puedo ayudarte a buscar información, consultar sistemas internos, crear tickets, revisar clientes y preparar respuestas o cotizaciones."

⸻

Caso 2: Consulta de cliente

Usuario:
"Nova, busca el cliente Demo Corp."
NOVA:
"Encontré Demo Corp. Tiene una oportunidad abierta y dos tickets pendientes."

⸻

Caso 3: Soporte

Usuario:
"Nova, crea un ticket para el cliente Demo Corp por error de impresora."
NOVA:
"Puedo crearlo. Confírmame si deseas registrar el ticket con prioridad media."

⸻

Caso 4: Consulta documental

Usuario:
"Nova, ¿cómo se configura la factura electrónica en NAOS?"
NOVA:
"Según la documentación, primero debes configurar los datos fiscales, luego validar el ambiente de DGI y finalmente probar la emisión de CAFE."

⸻

Caso 5: Cotización

Usuario:
"Nova, prepara una cotización para 5 licencias de NAOS."
NOVA:
"Preparé un borrador de cotización para 5 licencias. ¿Quieres que lo envíe a PandaDoc o que solo lo deje como borrador?"

⸻

13. Roadmap Inicial

Fase 1: Validación Técnica

Duración estimada: 1 semana.

Objetivo:

Ejecutar un asistente de voz funcional usando un proyecto base.

Tareas:

* Clonar llm-guy/jarvis.
* Instalar dependencias.
* Ejecutar localmente.
* Revisar arquitectura.
* Probar STT.
* Probar LLM.
* Probar TTS.
* Cambiar idioma a español.
* Documentar hallazgos.

Entregable:

Demo local que escuche una pregunta y responda por voz en español.

⸻

Fase 2: Fork Propio NOVA

Duración estimada: 1 semana.

Objetivo:

Separar la base y crear estructura propia.

Tareas:

* Crear repositorio nova-voice-agent.
* Crear estructura modular.
* Crear FastAPI.
* Crear endpoint /health.
* Crear endpoint /agent/chat.
* Crear endpoint /voice/ask.
* Crear prompt base.
* Crear servicio LLM.
* Crear servicio TTS.
* Crear servicio STT.

Entregable:

Backend modular inicial de NOVA.

⸻

Fase 3: Primera Tool Real

Duración estimada: 1 semana.

Objetivo:

Permitir que NOVA ejecute una acción real.

Opciones de primera tool:

* Consultar cliente demo.
* Crear ticket demo.
* Consultar SQL Server.
* Buscar en documentación.
* Consultar una API interna.

Recomendación:

Iniciar con una tool simple llamada:

search_customer

Entregable:

NOVA puede responder por voz usando información obtenida desde una tool.

⸻

Fase 4: Memoria y Base de Conocimiento

Duración estimada: 1 a 2 semanas.

Objetivo:

Agregar RAG y memoria básica.

Tareas:

* Configurar Qdrant.
* Crear pipeline de indexación.
* Indexar documentos iniciales.
* Crear tool search_knowledge_base.
* Guardar historial de conversación.
* Agregar contexto por usuario.

Entregable:

NOVA puede responder preguntas usando documentación interna.

⸻

Fase 5: Demo Ejecutiva

Duración estimada: 1 semana.

Objetivo:

Preparar una demo comercial funcional.

Tareas:

* Crear interfaz simple.
* Agregar animación visual.
* Mejorar voz.
* Crear casos de demo.
* Medir latencia.
* Preparar guion de presentación.
* Documentar costos estimados.

Entregable:

Demo presentable para clientes, socios o equipo interno.

⸻

14. Comandos Iniciales

Clonar proyecto base

git clone https://github.com/llm-guy/jarvis.git
cd jarvis

Crear repositorio propio

mkdir nova-voice-agent
cd nova-voice-agent
git init

Crear entorno virtual

python3 -m venv .venv
source .venv/bin/activate

Instalar dependencias base

pip install fastapi uvicorn python-dotenv pydantic requests

Ejecutar API inicial

uvicorn app.main:app --reload --port 8000

⸻

15. API Inicial Esperada

Health Check

GET /health

Respuesta:

{
  "status": "ok",
  "service": "NOVA Voice Agent"
}

⸻

Chat por Texto

POST /agent/chat

Request:

{
  "message": "Nova, ¿qué puedes hacer?"
}

Response:

{
  "response": "Puedo ayudarte a consultar información, ejecutar tareas y responder preguntas usando herramientas internas."
}

⸻

Consulta por Voz

POST /voice/ask

Request:

Archivo de audio o stream de audio.

Response:

{
  "transcript": "Busca el cliente Demo Corp",
  "response": "Encontré Demo Corp. Tiene dos tickets abiertos.",
  "audio_url": "/audio/responses/response_001.mp3"
}

⸻

16. Seguridad Inicial

Desde el MVP se deben considerar controles mínimos.

Recomendaciones:

* Usar .env para secretos.
* No subir API keys al repositorio.
* Agregar .gitignore.
* Separar ambientes: local, dev, prod.
* Registrar logs de acciones.
* Confirmar acciones críticas.
* Limitar tools disponibles por usuario.
* Validar entradas antes de ejecutar acciones.
* No permitir SQL libre generado por el LLM.

⸻

17. .gitignore Recomendado

.venv/
__pycache__/
*.pyc
.env
.env.local
.env.production
audio/responses/
logs/
*.db
.DS_Store
.idea/
.vscode/

⸻

18. Criterios de Éxito del MVP

El MVP será exitoso si logra:

* Escuchar una pregunta en español.
* Transcribir correctamente la voz.
* Procesar la solicitud con un LLM.
* Responder con voz natural.
* Ejecutar al menos una tool.
* Guardar historial básico.
* Tener arquitectura modular.
* Ser fácil de extender.

⸻

19. Pendientes por Decidir

* Proveedor final de LLM.
* Proveedor final de TTS.
* Motor STT definitivo.
* Si el primer cliente será web, desktop o local CLI.
* Nombre comercial definitivo.
* Primera integración real.
* Infraestructura de despliegue.
* Modelo de costos.
* Modelo de permisos por usuario.
* Estrategia multi-tenant.

⸻

20. Recomendación de Inicio

La recomendación práctica es iniciar en este orden:

1. Clonar y probar llm-guy/jarvis.
2. Validar que funcione localmente.
3. Cambiar idioma y prompt a español.
4. Probar una voz premium en español.
5. Crear fork o proyecto propio NOVA.
6. Separar arquitectura en módulos.
7. Crear primera tool real.
8. Preparar demo ejecutiva.

El objetivo inicial no debe ser construir todo el producto, sino validar rápidamente una experiencia funcional:

Hablar → Entender → Razonar → Ejecutar → Responder con voz

Una vez logrado ese flujo, el proyecto puede evolucionar hacia una plataforma empresarial de agentes de voz.