"""provider de promptfoo para el agente centralizado de parachute s.a.

promptfoo le pasa a call_api() el prompt ya armado (la pregunta del usuario) y
este archivo corre un turno completo de agente_manager, igual que en la
terminal. ademas de la respuesta, devuelve en metadata todo lo que los evals
necesitan revisar:

* herramientas_manager: a que especialista delego el manager (as_tool) y con
  que input. sale de result.new_items del sdk.
* herramientas: las tools reales que se ejecutaron adentro de los
  especialistas (buscar_en_faqs, consultar_clima, agendar_cita), con sus
  argumentos y lo que devolvieron. el sdk no expone lo que pasa adentro de un
  as_tool, asi que se envuelven las funciones _raw de shared/tools.py.
* contexto y fichas_recuperadas: lo que devolvio la busqueda en pgvector, para
  los evals de rag (context-faithfulness) y para revisar la ficha correcta.
* citas_guardadas: lo que quedo escrito en el store de citas en este turno.

fixtures (test doubles, no se toca el codigo del agente):

* vars.clima_simulado: dict con temperatura, precipitacion, nubes, viento y
  rafaga. si viene, open-meteo no se llama y "hoy" se congela en
  vars.hoy_simulado (o HOY_SIMULADO), para que los casos de agenda den lo
  mismo cualquier dia que se corran.
* sin clima_simulado se usa open-meteo real. en ese caso el prompt puede traer
  fechas relativas como [HOY+3], que se cambian por la fecha real.
* cada turno escribe las citas en un archivo temporal propio, nunca en
  app/data/citas.json.
"""

import asyncio
import contextvars
import json
import os
import re
import sys
import tempfile
import time
from datetime import date, timedelta

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_RAIZ, "app"))

from agents import Runner, ToolCallItem  # noqa: E402

import shared.agenda as agenda  # noqa: E402
import shared.clima as clima  # noqa: E402
import shared.faqs as faqs  # noqa: E402
import shared.tools as tools  # noqa: E402
from centralizado import agente_manager  # noqa: E402

# fecha fija para los casos con clima simulado. queda antes del evento (29 de
# septiembre de 2026) para que las fechas de los casos caigan dentro de los 16
# dias que predice open-meteo
HOY_SIMULADO = "2026-09-27"

_FECHA_RELATIVA = re.compile(r"\[HOY([+-]\d+)?\]")
_ID_FICHA = re.compile(r"\[(FAQ-\d+)\]")

# registro de las tools hoja del turno actual. las tools sync del sdk corren en
# asyncio.to_thread, que copia el contexto, asi que la lista es la misma
_REGISTRO = contextvars.ContextVar("registro_herramientas", default=None)

# un solo event loop para todo el proceso: el cliente de groq (httpx async) se
# crea una vez al importar centralizado.py y no le gusta cambiar de loop entre
# llamadas
_LOOP = asyncio.new_event_loop()

# el modelo de embeddings tarda en cargar la primera vez. se carga aca para que
# esa espera no se cuente como latencia del primer caso
faqs._modelo()


def _trazar(nombre, funcion):
    def envuelta(*args, **kwargs):
        registro = _REGISTRO.get()
        entrada = {"herramienta": nombre, "argumentos": _argumentos(nombre, args, kwargs)}
        try:
            resultado = funcion(*args, **kwargs)
        except Exception as e:  # noqa: BLE001  se registra y se deja subir
            entrada["error"] = str(e)
            if registro is not None:
                registro.append(entrada)
            raise
        entrada["resultado"] = resultado if isinstance(resultado, str) else json.dumps(
            resultado, ensure_ascii=False, default=str
        )
        if registro is not None:
            registro.append(entrada)
        return resultado

    return envuelta


def _argumentos(nombre, args, kwargs):
    nombres = {
        "buscar_en_faqs": ("consulta", "k"),
        "consultar_clima": ("fecha",),
        "agendar_cita": ("fecha", "nombre"),
    }[nombre]
    datos = dict(zip(nombres, args))
    datos.update(kwargs)
    return datos


# shared/tools.py busca estas funciones por nombre en su propio modulo cada vez
# que se ejecuta una tool, asi que basta con reemplazarlas ahi
tools.buscar_en_faqs_raw = _trazar("buscar_en_faqs", faqs.buscar_en_faqs_raw)
tools.consultar_clima_raw = _trazar("consultar_clima", clima.consultar_clima_raw)
tools.agendar_cita_raw = _trazar("agendar_cita", agenda.agendar_cita_raw)


def _resolver_fechas(prompt, hoy):
    def cambiar(m):
        dias = int(m.group(1) or 0)
        return (hoy + timedelta(days=dias)).isoformat()

    return _FECHA_RELATIVA.sub(cambiar, prompt)


class _Fixtures:
    """aplica los test doubles de un caso y los deshace al terminar."""

    def __init__(self, variables):
        self.clima_simulado = variables.get("clima_simulado")
        if isinstance(self.clima_simulado, str):
            self.clima_simulado = json.loads(self.clima_simulado)
        hoy = variables.get("hoy_simulado") or HOY_SIMULADO
        self.hoy = date.fromisoformat(hoy) if self.clima_simulado else None
        self.store = None
        self._originales = {}

    def __enter__(self):
        self._originales = {
            "pedir": clima._pedir_clima,
            "hoy": clima.hoy_local,
            "store": agenda._RUTA_STORE,
        }
        fd, self.store = tempfile.mkstemp(prefix="citas_", suffix=".json")
        os.close(fd)
        os.remove(self.store)  # agenda.py crea el archivo si hace falta
        agenda._RUTA_STORE = self.store

        if self.clima_simulado:
            fijo = self.hoy
            simulado = dict(self.clima_simulado)

            def pedir_simulado(fecha, dias_adelante):
                return {
                    "hora": f"{fecha.isoformat()}T12:00",
                    "temperatura": simulado.get("temperatura", 28.0),
                    "precipitacion": simulado.get("precipitacion", 0.0),
                    "nubes": simulado.get("nubes", 10),
                    "viento": simulado.get("viento", 8.0),
                    "rafaga": simulado.get("rafaga", 15.0),
                    "fuente": "simulado",
                }

            clima._pedir_clima = pedir_simulado
            clima.hoy_local = lambda: fijo
        return self

    def hoy_efectivo(self):
        return self.hoy or clima.hoy_local()

    def citas(self):
        if not os.path.exists(self.store):
            return []
        with open(self.store, encoding="utf-8") as f:
            return json.load(f)

    def __exit__(self, *exc):
        clima._pedir_clima = self._originales["pedir"]
        clima.hoy_local = self._originales["hoy"]
        agenda._RUTA_STORE = self._originales["store"]
        if self.store and os.path.exists(self.store):
            os.remove(self.store)
        return False


def _herramientas_manager(result):
    llamadas = []
    for item in result.new_items:
        if not isinstance(item, ToolCallItem):
            continue
        crudo = item.raw_item
        nombre = getattr(crudo, "name", None)
        argumentos = getattr(crudo, "arguments", None)
        if isinstance(crudo, dict):
            nombre = crudo.get("name", nombre)
            argumentos = crudo.get("arguments", argumentos)
        try:
            argumentos = json.loads(argumentos) if isinstance(argumentos, str) else argumentos
        except json.JSONDecodeError:
            pass
        llamadas.append({"herramienta": nombre, "argumentos": argumentos})
    return llamadas


def _uso(result):
    uso = result.context_wrapper.usage
    return {
        "total": uso.total_tokens,
        "prompt": uso.input_tokens,
        "completion": uso.output_tokens,
    }


async def _correr(prompt):
    registro = []
    token = _REGISTRO.set(registro)
    try:
        inicio = time.perf_counter()
        result = await Runner.run(agente_manager, [{"role": "user", "content": prompt}])
        latencia = int((time.perf_counter() - inicio) * 1000)
    finally:
        _REGISTRO.reset(token)
    return result, registro, latencia


def call_api(prompt, options, context):
    variables = (context or {}).get("vars", {}) or {}

    with _Fixtures(variables) as fx:
        prompt = _resolver_fechas(prompt, fx.hoy_efectivo())
        try:
            result, registro, latencia = _LOOP.run_until_complete(_correr(prompt))
        except Exception as e:  # noqa: BLE001  promptfoo lo muestra como error del caso
            return {"error": f"{type(e).__name__}: {e}"}
        citas = fx.citas()
        hoy = fx.hoy_efectivo().isoformat()

    busquedas = [r for r in registro if r["herramienta"] == "buscar_en_faqs"]
    contexto = "\n\n".join(r.get("resultado", "") for r in busquedas)
    fichas = []
    for r in busquedas:
        for ficha in _ID_FICHA.findall(r.get("resultado", "")):
            if ficha not in fichas:
                fichas.append(ficha)

    return {
        "output": str(result.final_output),
        "latencyMs": latencia,
        "tokenUsage": _uso(result),
        "metadata": {
            "prompt_resuelto": prompt,
            "hoy": hoy,
            "clima_simulado": bool(fx.clima_simulado),
            "herramientas_manager": _herramientas_manager(result),
            "herramientas": registro,
            "contexto": contexto,
            "fichas_recuperadas": fichas,
            "citas_guardadas": citas,
        },
    }
