"""grader de las assertions model graded (factuality, context-faithfulness,
llm-rubric), servido como provider de python para promptfoo.

por que no se usa directo el provider groq: de promptfoo: groq gratis tiene un
limite de 8000 tokens por minuto para gpt-oss-120b. cuando se pasa, groq
responde 429 con dos tiempos de espera, el de tokens (menos de un segundo) y
el de requests del dia (varios minutos). promptfoo toma el mas largo y se
quedaba esperando 15 a 20 minutos por cada 429. el cliente de openai en cambio
respeta el header retry-after, que es el corto.

de paso se baja el esfuerzo de razonamiento del modelo: calificar no necesita
mucho, y asi cada calificacion gasta menos tokens del limite por minuto.

tambien se le pide al grader que conteste en ingles y con el formato exacto
del prompt: como las respuestas del agente estan en espanol, el modelo tendia
a escribir "Veredicto: Si", y el parser de promptfoo solo entiende Yes/No.

con GRADER_LOG=ruta.jsonl se guarda cada calificacion para auditarla.
"""

import json
import os

from dotenv import load_dotenv
from openai import OpenAI

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(_RAIZ, ".env"))

_CLIENTE = None


def _cliente():
    global _CLIENTE
    if _CLIENTE is None:
        _CLIENTE = OpenAI(
            api_key=os.environ["GROQ_API_KEY"],
            base_url=os.environ.get("GROQ_BASE_URL", "https://api.groq.com/openai/v1"),
            max_retries=10,
            timeout=120,
        )
    return _CLIENTE


_SISTEMA = (
    "You are an evaluation grader. The texts you grade may be in Spanish, but you "
    "must always write your answer in English and follow the exact output format "
    "requested in the prompt (for example the literal words Yes/No, Verdict:, "
    "Final verdict for each statement in order:, or the requested JSON). Do not "
    "add any text after the requested final line."
)


def _mensajes(prompt):
    # los graders de promptfoo mandan el prompt como lista de mensajes en json
    try:
        datos = json.loads(prompt)
    except (json.JSONDecodeError, TypeError):
        datos = None
    if isinstance(datos, list) and datos and all(isinstance(m, dict) and "role" in m for m in datos):
        mensajes = datos
    else:
        mensajes = [{"role": "user", "content": prompt}]
    return [{"role": "system", "content": _SISTEMA}] + mensajes


def _sin_encabezado(texto):
    # context-faithfulness le pide al grader que extraiga las afirmaciones de la
    # respuesta; el prompt termina en "statements:" y espera solo la lista. el
    # modelo a veces repite ese encabezado, y promptfoo lo contaba como una
    # afirmacion mas sin veredicto: con 2 afirmaciones apoyadas daba 2/3 = 0.67
    # en vez de 1.0 (se vio en la bitacora del grader). se quita el encabezado
    limpio = texto.lstrip()
    if limpio.lower().startswith("statements:"):
        return limpio[len("statements:"):].lstrip()
    return texto


def _bitacora(prompt, texto):
    # si GRADER_LOG apunta a un archivo, se guarda cada calificacion (prompt y
    # respuesta) en jsonl para poder auditar al grader cuando algo no cuadra
    ruta = os.environ.get("GRADER_LOG")
    if not ruta:
        return
    with open(ruta, "a", encoding="utf-8") as f:
        f.write(json.dumps({"prompt": prompt, "respuesta": texto}, ensure_ascii=False) + "\n")


def call_api(prompt, options, context):
    config = (options or {}).get("config", {}) or {}
    try:
        respuesta = _cliente().chat.completions.create(
            model=config.get("model", "openai/gpt-oss-120b"),
            messages=_mensajes(prompt),
            temperature=config.get("temperature", 0),
            reasoning_effort=config.get("reasoning_effort", "low"),
        )
    except Exception as e:  # noqa: BLE001  promptfoo lo muestra como error del grader
        return {"error": f"{type(e).__name__}: {e}"}

    uso = respuesta.usage
    texto = _sin_encabezado(respuesta.choices[0].message.content or "")
    _bitacora(prompt, texto)
    return {
        "output": texto,
        "tokenUsage": {
            "total": uso.total_tokens,
            "prompt": uso.prompt_tokens,
            "completion": uso.completion_tokens,
        },
    }
