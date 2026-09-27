"""calendarizacion de citas: revisa el clima antes de confirmar y guarda en un json."""

import json
import os
import uuid
from datetime import datetime, timezone

from .clima import consultar_clima_raw

_RUTA_STORE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "citas.json")


def _leer_citas():
    if not os.path.exists(_RUTA_STORE):
        return []
    with open(_RUTA_STORE, encoding="utf-8") as f:
        return json.load(f)


def _guardar_cita(cita):
    os.makedirs(os.path.dirname(_RUTA_STORE), exist_ok=True)
    citas = _leer_citas()
    citas.append(cita)
    with open(_RUTA_STORE, "w", encoding="utf-8") as f:
        json.dump(citas, f, ensure_ascii=False, indent=2)


def _describir_clima(datos):
    return (
        f"temperatura {datos['temperatura']} C, viento {datos['viento']} km/h, "
        f"rafagas {datos['rafaga']} km/h, precipitacion {datos['precipitacion']} mm, "
        f"nubes {datos['nubes']}%"
    )


def agendar_cita_raw(fecha_str, nombre=None):
    """revisa el clima de la fecha pedida y, si las condiciones lo permiten,
    guarda la cita. devuelve texto listo para que el llm se lo explique al
    usuario."""
    datos = consultar_clima_raw(fecha_str)

    if "error" in datos:
        return f"NO_SE_PUDO_AGENDAR: {datos['error']}"

    evaluacion = datos["evaluacion"]
    resumen = _describir_clima(datos)

    if evaluacion["veredicto"] == "NO_SEGURO":
        razones = "; ".join(evaluacion["problemas"])
        return (
            f"NO_SE_PUDO_AGENDAR: el {datos['fecha']} el clima no es seguro para saltar "
            f"({razones}). Datos: {resumen}. No se guardo ninguna cita, sugiere elegir otra fecha."
        )

    cita = {
        "id": uuid.uuid4().hex[:8],
        "fecha": datos["fecha"],
        "nombre": nombre or None,
        "veredicto": evaluacion["veredicto"],
        "clima": resumen,
        "creada": datetime.now(timezone.utc).isoformat(),
    }
    _guardar_cita(cita)

    if evaluacion["veredicto"] == "MARGINAL":
        aviso = (
            "condiciones marginales, solo recomendable con instructor tandem experimentado"
        )
    else:
        aviso = "condiciones ideales para saltar"

    return (
        f"CITA_CONFIRMADA id={cita['id']} fecha={datos['fecha']} veredicto={evaluacion['veredicto']} "
        f"({aviso}). Datos del clima: {resumen}."
    )
