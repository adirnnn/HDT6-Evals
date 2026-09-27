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

Pendiente.
