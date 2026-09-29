"""assertions de tool execution para promptfoo.

todas leen la traza que arma evals/provider.py en metadata y reciben sus
parametros por el campo config de la assertion, por ejemplo:

    - type: python
      value: file://evals/asserts/herramientas.py:delego_en
      config:
        agente: agente_faqs
        no_delegar: [agente_agenda]

cada funcion devuelve un GradingResult (pass, score, reason) para que el
reporte explique por que paso o fallo.

en los casos contra open-meteo real las fechas se escriben relativas, como
[HOY+2]; se resuelven con metadata.hoy, el mismo "hoy" que uso el provider.
"""

import json
import re
from datetime import date, timedelta

_FECHA_RELATIVA = re.compile(r"^\[HOY([+-]\d+)?\]$")


def _metadata(context):
    meta = context.get("metadata")
    if not meta:
        meta = (context.get("providerResponse") or {}).get("metadata") or {}
    return meta


def _config(context):
    return context.get("config") or {}


def _resultado(ok, razon):
    return {"pass": bool(ok), "score": 1.0 if ok else 0.0, "reason": razon}


def _resolver(valor, context):
    # cambia [HOY+n] por la fecha real que uso el provider en ese turno
    if not isinstance(valor, str):
        return valor
    m = _FECHA_RELATIVA.match(valor.strip())
    if not m:
        return valor
    hoy = date.fromisoformat(_metadata(context)["hoy"])
    return (hoy + timedelta(days=int(m.group(1) or 0))).isoformat()


def _nombres(llamadas):
    return [c.get("herramienta") for c in llamadas]


def delego_en(output, context):
    """el manager delego en el especialista correcto (as_tool) y no en otros.

    config: agente (obligatorio), no_delegar (lista opcional)."""
    cfg = _config(context)
    llamadas = _nombres(_metadata(context).get("herramientas_manager", []))
    esperado = cfg["agente"]
    prohibidos = [a for a in cfg.get("no_delegar", []) if a in llamadas]

    if esperado not in llamadas:
        return _resultado(False, f"el manager no delego en {esperado}; delego en {llamadas or 'nadie'}")
    if prohibidos:
        return _resultado(False, f"el manager delego tambien en {prohibidos}, no correspondia")
    return _resultado(True, f"el manager delego en {esperado} (llamadas: {llamadas})")


def uso_herramienta(output, context):
    """la tool hoja correcta se ejecuto, con los argumentos esperados, y las
    tools prohibidas no se ejecutaron.

    config: herramienta (obligatorio), no_usar (lista opcional), argumentos
    (dict opcional, cada valor se compara exacto contra alguna llamada)."""
    cfg = _config(context)
    llamadas = _metadata(context).get("herramientas", [])
    nombres = _nombres(llamadas)
    esperada = cfg["herramienta"]
    prohibidas = [h for h in cfg.get("no_usar", []) if h in nombres]

    if prohibidas:
        return _resultado(False, f"se ejecuto {prohibidas} y no debia (tools: {nombres})")

    candidatas = [c for c in llamadas if c.get("herramienta") == esperada]
    if not candidatas:
        return _resultado(False, f"no se ejecuto {esperada} (tools: {nombres or 'ninguna'})")

    argumentos = {k: _resolver(v, context) for k, v in (cfg.get("argumentos") or {}).items()}
    if argumentos:
        for c in candidatas:
            reales = c.get("argumentos", {})
            if all(str(reales.get(k)) == str(v) for k, v in argumentos.items()):
                return _resultado(True, f"{esperada} se ejecuto con {reales}")
        vistos = [c.get("argumentos") for c in candidatas]
        return _resultado(False, f"{esperada} se ejecuto pero con {vistos}, se esperaba {argumentos}")

    return _resultado(True, f"{esperada} se ejecuto (llamadas: {len(candidatas)}, tools: {nombres})")


def sin_herramientas(output, context):
    """no se ejecuto ninguna tool hoja. sirve para casos donde el agente tiene
    que corregir al usuario antes de gastar una llamada."""
    nombres = _nombres(_metadata(context).get("herramientas", []))
    if nombres:
        return _resultado(False, f"se ejecutaron tools que no hacian falta: {nombres}")
    return _resultado(True, "no se ejecuto ninguna tool")


def recupero_ficha(output, context):
    """la busqueda en pgvector trajo la ficha que responde la pregunta.

    config: ficha (por ejemplo FAQ-021) o fichas (lista, basta con una)."""
    cfg = _config(context)
    esperadas = cfg.get("fichas") or [cfg["ficha"]]
    recuperadas = _metadata(context).get("fichas_recuperadas", [])
    encontradas = [f for f in esperadas if f in recuperadas]
    if encontradas:
        return _resultado(True, f"se recupero {encontradas} (recuperadas: {recuperadas})")
    return _resultado(False, f"no se recupero ninguna de {esperadas} (recuperadas: {recuperadas or 'ninguna'})")


def cita_guardada(output, context):
    """revisa el efecto real de agendar: la cita quedo guardada (o no) en el
    store, con la fecha correcta.

    config: esperada (true/false), fecha (opcional), veredicto (opcional)."""
    cfg = _config(context)
    citas = _metadata(context).get("citas_guardadas", [])
    esperada = bool(cfg.get("esperada", True))

    if not esperada:
        if citas:
            return _resultado(False, f"se guardo una cita y no debia: {json.dumps(citas, ensure_ascii=False)}")
        return _resultado(True, "no se guardo ninguna cita, correcto")

    if len(citas) != 1:
        return _resultado(False, f"se esperaba exactamente 1 cita guardada y hay {len(citas)}")
    cita = citas[0]
    for campo in ("fecha", "veredicto"):
        esperado = _resolver(cfg.get(campo), context)
        if campo in cfg and cita.get(campo) != esperado:
            return _resultado(False, f"la cita tiene {campo}={cita.get(campo)}, se esperaba {esperado}")
    return _resultado(True, f"cita guardada: fecha={cita.get('fecha')} veredicto={cita.get('veredicto')}")


def agenda_consistente(output, context):
    """para los casos con clima real, donde no se sabe de antemano si la cita
    se puede agendar: revisa que la herramienta, el store y la respuesta al
    usuario cuenten la misma historia.

    * si agendar_cita devolvio CITA_CONFIRMADA, tiene que haber exactamente una
      cita guardada con esa fecha y la respuesta tiene que confirmarla.
    * si devolvio NO_SE_PUDO_AGENDAR, no puede haber cita guardada y la
      respuesta no puede decir que quedo confirmada."""
    meta = _metadata(context)
    llamadas = [c for c in meta.get("herramientas", []) if c.get("herramienta") == "agendar_cita"]
    if not llamadas:
        return _resultado(False, "no se ejecuto agendar_cita")
    resultado = llamadas[-1].get("resultado", "")
    citas = meta.get("citas_guardadas", [])
    texto = output.lower()

    if resultado.startswith("CITA_CONFIRMADA"):
        fecha = llamadas[-1].get("argumentos", {}).get("fecha")
        if len(citas) != 1 or citas[0].get("fecha") != fecha:
            return _resultado(False, f"la tool confirmo la cita del {fecha} pero el store tiene {citas}")
        if not re.search(r"confirm|agend|reserv", texto):
            return _resultado(False, "la tool confirmo la cita pero la respuesta no lo dice")
        return _resultado(True, f"cita confirmada y guardada para {fecha}, la respuesta lo confirma")

    if citas:
        return _resultado(False, f"la tool no agendo pero el store tiene {citas}")
    if re.search(r"(?<!no\s)(qued[oó]|est[aá])\s+(confirmad|agendad|reservad)|cita_confirmada", texto):
        return _resultado(False, "la tool rechazo la cita pero la respuesta dice que quedo confirmada")
    return _resultado(True, "la tool rechazo la cita, no se guardo nada y la respuesta no la confirma")
