# HDT6 Evals: agente de Parachute S.A. evaluado con promptfoo

CC3116. Parachute S.A. ya considera terminado el agente de HDT5 y lo quiere
poner en productivo, pero avisó que va a seguir iterando. Esta hoja cierra el
ciclo de desarrollo con el bloque que faltaba: **evals** con
[promptfoo](https://www.promptfoo.dev/) para las dos funcionalidades del
agente, **agendar citas** y **responder preguntas frecuentes**.

Se evalúa la arquitectura que en HDT5 se consideró la mejor: la
**centralizada**. Un `agente_manager` habla con el usuario y delega (con
`Agent.as_tool()`) en dos especialistas:

* `agente_faqs`: usa la tool `buscar_en_faqs` (búsqueda semántica en pgvector).
* `agente_agenda`: usa las tools `consultar_clima` y `agendar_cita`
  (Open-Meteo, revisa el clima antes de confirmar la cita).

## Estructura

```
app/                   el agente (arquitectura centralizada de HDT5)
  centralizado.py      manager + especialistas, loop de terminal
  shared/              logica de negocio: faqs, clima, agenda, tools, prompts
infra/                 base de conocimientos
  docker-compose.yml   postgres + pgvector
  cargar.py, db.py     parsea el corpus, calcula embeddings y llena la tabla
  Corpus_FAQs_Parachute_SA_2026.txt
evals/                 todo lo de promptfoo (provider, assertions, casos)
reports/               reportes generados por promptfoo
promptfooconfig.yaml   configuracion de los evals
```

## Requisitos

* Python 3.11 o superior.
* Node.js 20 o superior (para promptfoo).
* Docker Desktop (para pgvector).
* Una API Key gratuita de Groq: <https://console.groq.com/keys>

## Instalacion

```bash
python -m venv .venv
# Windows PowerShell:  .venv\Scripts\Activate.ps1
# Linux o macOS:       source .venv/bin/activate
pip install -r requirements.txt
npm install
```

```bash
copy .env.example .env
# editar .env y pegar GROQ_API_KEY
```

## Levantar la base de conocimientos

```bash
docker compose -f infra/docker-compose.yml up -d
python infra/cargar.py
```

`cargar.py` parsea las 120 fichas del corpus, calcula los embeddings y llena
la tabla `faqs`. Se puede correr varias veces sin duplicar nada.

## Probar el agente a mano

```bash
python app/centralizado.py
```

Escribe preguntas de FAQs o pide agendar una cita (por ejemplo "quiero agendar
una cita para el 2026-10-02"); para salir escribe `Bye` o presiona `Ctrl+C`.

## Evals

```bash
npm run eval      # corre todos los casos (sin cache, para medir latencia real)
npm run report    # corre y guarda reports/reporte.html y reports/reporte.json
npm run view      # abre el visor web de promptfoo
```

### Como funciona el provider

`evals/provider.py` es un provider de Python para promptfoo. Corre un turno
completo de `agente_manager` con la pregunta del caso y devuelve, ademas de la
respuesta, una traza en `metadata`:

* `herramientas_manager`: en que especialista delego el manager (`as_tool`).
* `herramientas`: las tools que de verdad se ejecutaron adentro de los
  especialistas (`buscar_en_faqs`, `consultar_clima`, `agendar_cita`), con
  argumentos y resultado. El SDK no expone lo que pasa adentro de un
  `as_tool`, asi que el provider envuelve las funciones `_raw` de
  `shared/tools.py`.
* `contexto` y `fichas_recuperadas`: lo que trajo la busqueda en pgvector.
* `citas_guardadas`: lo que quedo escrito en el store de citas en ese turno.
* `latencyMs`: el tiempo del turno del agente, sin contar la carga inicial del
  modelo de embeddings.

Para que los casos de agenda den lo mismo cualquier dia que se corran, si el
caso trae `clima_simulado` el provider no llama a Open-Meteo, usa esos datos y
congela "hoy" en 2026-09-27. Cada turno guarda sus citas en un archivo
temporal, nunca en `app/data/citas.json`. Nada de esto cambia el codigo del
agente: son dobles de prueba que se ponen y se quitan en cada caso.

Las assertions de tool execution estan en `evals/asserts/herramientas.py` y
leen esa traza.
