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
python evals/resumen.py   # tablas de resultados a partir de reports/reporte.json
```

La corrida completa (25 casos) tarda unos 25 minutos por la pausa de 45 s
entre turnos (ver "Ritmo de la corrida"). El reporte entregable esta en
[`reports/reporte.html`](reports/reporte.html) (se abre en el navegador) y
[`reports/reporte.json`](reports/reporte.json) (los datos crudos, con la
traza de tools de cada caso en `metadata`).

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

### Grader

Las assertions calificadas por modelo (`factuality`, `context-faithfulness`,
`llm-rubric`) usan `openai/gpt-oss-120b` en Groq, un modelo mas grande que el
del agente (`gpt-oss-20b`). Se sirve con `evals/grader.py` y no con el
provider `groq:` de promptfoo por tres problemas que aparecieron al correr:

* Con el plan gratis de Groq (8000 tokens por minuto por modelo), cada 429 de
  Groq trae dos tiempos de espera: el de tokens (menos de un segundo) y el de
  requests del dia (varios minutos). promptfoo usa el mas largo y se quedaba
  esperando unos 18 minutos por rechazo. El cliente de OpenAI respeta
  `retry-after`, que es el corto.
* Como el contenido esta en espanol, el grader contestaba "Veredicto: Si" y el
  parser de promptfoo solo entiende Yes/No. Se le pide contestar en ingles y
  con el formato exacto.
* En `context-faithfulness` el grader a veces repetia el encabezado
  `statements:` y promptfoo lo contaba como una afirmacion mas sin veredicto.
  Una respuesta con 2 afirmaciones apoyadas sacaba 0.67 en vez de 1.0. Se
  detecto auditando al grader (`GRADER_LOG=archivo.jsonl` guarda cada
  calificacion) y se quita ese encabezado.

### Ritmo de la corrida

Un turno del agente hace 4 requests a Groq (manager y especialista, dos cada
uno) y gasta de 5000 a 6000 tokens en un par de segundos. Con el limite de
8000 tokens por minuto, si los casos van seguidos Groq empieza a rechazar
requests y el cliente del agente espera y reintenta en silencio: esa espera se
media como latencia del agente. Se comprobo contando los 429 en el cliente
HTTP del agente (`llamadas_llm` y `reintentos_429` en `metadata`): sin pausa,
desde el septimo caso cada turno tenia de 3 a 5 rechazos y tardaba de 10 a
16 s en vez de 2. Por eso el provider tiene `delay: 45000` (45 s entre turnos)
y los casos corren de a uno.

### Evals de preguntas frecuentes (`evals/tests/faqs.yaml`)

Ground truth: `infra/Corpus_FAQs_Parachute_SA_2026.txt`. De las 120 fichas,
14 traen datos concretos y el resto son respuestas plantilla que solo dicen la
fecha del evento, la categoria y que se consulte a soporte. Ademas, dos fichas
del corpus traen una respuesta que no corresponde a su pregunta (FAQ-039 y
FAQ-103), y se usan como trampa.

| Caso | Que se busca |
|---|---|
| Peso maximo, edad minima, buceo, altura, velocidad, camaras | Fichas con datos: la respuesta repite los datos correctos |
| Pregunta parafraseada sobre peso | La busqueda semantica encuentra la ficha aunque la pregunta no se parezca |
| Fecha del evento | Solo las fichas plantilla tienen la fecha |
| Parqueo | Ficha plantilla: el agente no debe inventar que si hay parqueo |
| Capital de Francia | Fuera del dominio: no contesta de su conocimiento, manda a soporte |
| Seguro de viaje internacional | Tema sin ficha: dice que no tiene el dato y manda a soporte |
| Viento para suspender | Ficha ruidosa: no debe presentar 200 km/h como limite de viento |

Cada caso combina:

* **Factuality**: la respuesta contra la ficha del corpus, calificada por el
  grader.
* **Context faithfulness** (guia de RAG de promptfoo): lo que dice la respuesta
  tiene que salir de las fichas que trajo pgvector (`metadata.contexto`).
* **Deterministicos**: `regex` / `icontains` con los datos puntuales (100 kg,
  Q250, 24 horas, 29 de septiembre, el correo de soporte) y un `not-regex`
  que exige texto plano sin markdown. Se usa `\s` en los regex porque el
  modelo a veces separa palabras con un espacio angosto (U+202F).
* **Latencia**: el turno completo del agente en menos de 15 s.
* **Tool execution**: el manager delego en `agente_faqs` y no en
  `agente_agenda`; se ejecuto `buscar_en_faqs` y ninguna tool de agenda; la
  busqueda trajo la ficha esperada.

### Evals de agenda (`evals/tests/agenda.yaml`)

La mayoria de casos usan `clima_simulado`, asi el veredicto esperado se
conoce de antemano: el provider no llama a Open-Meteo, usa esos datos y
congela "hoy" en 2026-09-27. Los dos ultimos casos van contra Open-Meteo real
con fechas relativas (`[HOY+2]`, `[HOY+3]`), que el provider cambia por la
fecha real.

Criterio del agente (`app/shared/clima.py`), viento y rafagas en km/h:
viento ideal por debajo de 20, marginal de 20 a 28, prohibido arriba de 28;
rafagas prohibidas arriba de 35; cualquier lluvia prohibida; nubes ideales
por debajo de 30%, marginales de 30% a 75%, prohibidas arriba de 75%.

| Caso | Resultado esperado |
|---|---|
| Dia ideal | Cita confirmada y guardada con veredicto IDEAL |
| Viento 24 km/h | Cita confirmada con aviso, veredicto MARGINAL |
| Nubes 55% | Cita confirmada con aviso, veredicto MARGINAL |
| Lluvia 2.5 mm | No se agenda, explica la lluvia |
| Viento 32 km/h | No se agenda, explica el viento |
| Rafagas 42 km/h | No se agenda, explica las rafagas |
| Nubes 90% | No se agenda, explica la visibilidad |
| Fecha pasada | No se agenda, la fecha ya paso (con clima ideal a proposito) |
| A 28 dias | No se agenda, el pronostico solo llega a 16 dias |
| "5 de octubre de 2026" | El agente convierte a `2026-10-05` para la tool y agenda |
| Solo consultar el clima | Usa `consultar_clima`, nunca `agendar_cita` |
| En vivo: consultar clima | Datos reales de Open-Meteo, no agenda nada |
| En vivo: agendar | La tool, el store y la respuesta cuentan lo mismo |

Cada caso combina:

* **Factuality**: la respuesta contra lo que corresponde al clima del caso
  (confirmada, marginal o rechazada y por que). En el caso en vivo de
  consulta, como el clima real no se conoce, se usa `llm-rubric`.
* **Deterministicos**: la fecha, el motivo del rechazo (lluvia, viento,
  rafagas, nubes, 16 dias, fecha pasada), `marginal` cuando aplica, un
  `not-regex` que prohibe decir que la cita quedo confirmada cuando no se
  agendo, otro que prohibe mostrarle al usuario los codigos internos de las
  tools (`CITA_CONFIRMADA`, `NO_SE_PUDO_AGENDAR`, `FECHA_INVALIDA`), y texto
  plano sin markdown. La fecha se exige en las confirmaciones; en los
  rechazos se exige el motivo.
* **Latencia**: menos de 15 s; 20 s en los casos en vivo, que esperan a
  Open-Meteo.
* **Tool execution**: el manager delego en `agente_agenda` y no en
  `agente_faqs`; se ejecuto la tool correcta con la fecha correcta en formato
  AAAA-MM-DD (y el nombre cuando se dio); y se revisa el efecto real en el
  store de citas: la cita queda guardada solo si era seguro saltar, con la
  fecha y el veredicto correctos. En el caso en vivo de agendar,
  `agenda_consistente` revisa que si la tool confirmo haya exactamente una
  cita guardada y la respuesta lo diga, y que si rechazo no haya nada guardado
  ni la respuesta diga lo contrario.

## Resultados

Corrida completa del 29 de septiembre de 2026 (`reports/reporte.html`): 25
casos, 0 errores, 0 rechazos por rate limit.

| Funcionalidad | Casos que pasan | Latencia p50 | Latencia p95 | Reintentos 429 |
|---|---|---|---|---|
| FAQs | 10/12 (83%) | 1.8 s | 2.5 s | 0 |
| Agenda | 4/13 (31%) | 2.0 s | 2.8 s | 0 |

Por familia de eval (assertions que pasan):

| Familia de eval | FAQs | Agenda |
|---|---|---|
| Factuality | 9/11 (82%) | 8/12 (67%) |
| RAG (context faithfulness) | 8/9 (89%) | no aplica |
| Deterministicas (contains / regex) | 28/29 (97%) | 40/48 (83%) |
| Latencia | 12/12 (100%) | 13/13 (100%) |
| Tool execution | 31/31 (100%) | 30/37 (81%) |

Un caso pasa solo si pasan todas sus assertions, por eso el porcentaje por
caso es mas bajo que el de cada familia.

### Analisis: FAQs

Lo que funciona:

* Las 6 fichas con datos concretos se responden bien: factuality y
  faithfulness de 1.0 en todas. La pregunta parafraseada ("Peso 95 kilos...")
  tambien encuentra su ficha, asi que la busqueda semantica cumple.
* Tool execution perfecta: en los 12 casos el manager delego en
  `agente_faqs`, se ejecuto `buscar_en_faqs`, nunca se toco una tool de
  agenda, y la ficha esperada vino entre las recuperadas.
* Latencia muy por debajo del SLA de 15 s (p95 de 2.5 s).

Lo que falla:

* **Parqueo (alucinacion).** La ficha FAQ-003 es una plantilla que no dice si
  hay parqueo, pero el agente contesta "Hay parqueo disponible". Fallo en todas
  las corridas que se hicieron durante el desarrollo; factuality y
  faithfulness lo detectan. El modelo lee la pregunta repetida dentro de la
  plantilla ("Respuesta detallada para la consulta sobre '¿Hay parqueo...'")
  como si fuera la respuesta.
* **Ficha ruidosa FAQ-103.** El corpus trae en esa ficha la respuesta de la
  velocidad de caida libre. En esta corrida el agente la repitio tal cual como
  respuesta a "¿a que velocidad de viento se suspenden las operaciones?".
  En otras corridas si dijo que no tenia el dato, o sea que depende del
  muestreo del modelo.

Variacion entre corridas: la pregunta fuera del dominio ("capital de
Francia") paso aqui, pero en una corrida anterior el agente contesto "Paris"
de su propio conocimiento. Con un solo intento por caso estos resultados son
una muestra, no una tasa.

### Analisis: agenda

Lo que funciona:

* Cuando se ejecuta `agendar_cita`, el resultado es correcto siempre: el
  veredicto lo calcula codigo determinista (`evaluar_condiciones`), la cita se
  guarda solo si es segura y con el veredicto correcto, y la respuesta coincide
  (lluvia, fecha en lenguaje natural convertida a `2026-10-05`, 16 dias,
  caso en vivo contra Open-Meteo).
* Latencia bien dentro del SLA (p95 de 2.8 s, incluidos los casos en vivo).

Lo que falla, y es lo que mas le conviene a Parachute S.A. arreglar antes de
produccion:

* **Eleccion de herramienta.** Es el problema principal. En 3 casos donde el
  usuario pidio agendar, el agente uso `consultar_clima` en vez de
  `agendar_cita`, y en "nubes marginales" le dijo al usuario "La reserva esta
  lista" sin haber guardado nada. Al reves, en "solo consultar el clima"
  (el usuario pidio explicitamente no agendar) ejecuto `agendar_cita` y
  **guardo una cita que nadie pidio**. Las assertions sobre el store de citas
  son las que atrapan esto: leyendo solo el texto de la respuesta no se nota.
* **Preguntas innecesarias.** En 3 casos (viento, rafagas, fecha pasada) el
  agente no hizo nada y pidio el nombre o una aclaracion, aunque el nombre es
  opcional y el pedido era claro.
* **Formato.** Le muestra al usuario los codigos internos de la tool
  (`CITA_CONFIRMADA`) y usa listas con guiones aunque sus instrucciones piden
  texto plano.

La causa comun es que el especialista de agenda (`gpt-oss-20b`) sigue las
instrucciones de forma inconsistente: el mismo caso paso en una corrida y
fallo en otra con un comportamiento distinto.

### Recomendaciones para la siguiente iteracion

1. **Una sola tool para agendar.** Quitar `consultar_clima` del camino de
   agendar, o que el especialista de agenda solo tenga `agendar_cita` cuando
   el usuario pide reservar, y aclarar en las instrucciones que el nombre es
   opcional y que no se pregunta.
2. **Traducir los codigos de las tools** a texto para el usuario dentro de la
   propia tool, en vez de confiar en que el modelo los reescriba.
3. **Indexar pregunta y respuesta** en pgvector (hoy solo se indexa la
   pregunta) y limpiar las fichas del corpus que no corresponden a su pregunta
   (FAQ-039, FAQ-103).
4. **Instruccion explicita para fichas plantilla**: si la ficha no trae datos
   concretos, decir que no hay detalle y mandar a soporte, sin afirmar nada.
5. **Probar `gpt-oss-120b` como modelo del agente** con estos mismos evals y
   comparar: la suite ya esta lista para eso, basta con cambiar `GROQ_MODEL`.
6. **Correr los evals en cada cambio** y con `--repeat 3` para medir la
   variacion entre corridas, ahora que se sabe que existe.

### Limitaciones

* Un solo intento por caso: con un modelo que varia entre corridas, los
  porcentajes son una muestra. `--repeat` da tasas mas confiables a cambio de
  mas tiempo.
* El grader tambien varia. En una corrida de desarrollo califico con 0.67 una
  respuesta correcta sobre camaras porque convirtio el "No." inicial en una
  afirmacion aparte. Por eso cada caso combina assertions deterministicas con
  las del grader, y la bitacora del grader (`GRADER_LOG`) permite auditarlo.
* El `tokenUsage` que reporta el provider es el del manager; el SDK no suma
  el de las corridas anidadas de los especialistas (`as_tool`).
* La latencia se mide con 45 s de pausa entre turnos para no chocar con el
  limite del plan gratis de Groq. En produccion con un plan pagado ese limite
  no aplica, pero la concurrencia real tambien subiria la latencia.
