"""envoltorios @function_tool sobre la logica de negocio pura de shared/*.

estas son las tools que usan los especialistas de la arquitectura centralizada.
la funcion de negocio (el "_raw") vive aparte para poder probarla sola y para
que los evals puedan trazar cada llamada.
"""

from agents import function_tool

from .agenda import agendar_cita_raw
from .clima import consultar_clima_raw
from .faqs import buscar_en_faqs_raw


@function_tool
def buscar_en_faqs(consulta: str, k: int = 4) -> str:
    """Busca en la base de conocimientos de FAQs de Parachute S.A. por similitud
    semantica y devuelve las fichas mas parecidas a la consulta.

    Args:
        consulta: la pregunta o el tema a buscar, en lenguaje natural.
        k: cuantas fichas traer, por defecto 4.
    """
    return buscar_en_faqs_raw(consulta, k)


@function_tool
def consultar_clima(fecha: str) -> str:
    """Consulta el pronostico del clima en la zona de salto para una fecha, sin
    agendar nada. Sirve para que el usuario decida si quiere reservar.

    Args:
        fecha: fecha en formato AAAA-MM-DD. Open-Meteo solo predice hasta 16
            dias hacia adelante desde hoy.
    """
    datos = consultar_clima_raw(fecha)
    if "error" in datos:
        return f"FECHA_INVALIDA: {datos['error']}"

    ev = datos["evaluacion"]
    problemas = "; ".join(ev["problemas"]) if ev["problemas"] else "ninguno"
    return (
        f"fecha={datos['fecha']} veredicto={ev['veredicto']} "
        f"temperatura={datos['temperatura']}C viento={datos['viento']}km/h "
        f"rafagas={datos['rafaga']}km/h precipitacion={datos['precipitacion']}mm "
        f"nubes={datos['nubes']}% problemas={problemas}"
    )


@function_tool
def agendar_cita(fecha: str, nombre: str | None = None) -> str:
    """Revisa el clima de la fecha pedida y, si las condiciones son seguras
    para saltar, agenda la cita. Si no son seguras, no agenda nada y explica
    por que.

    Args:
        fecha: fecha deseada para la cita, en formato AAAA-MM-DD.
        nombre: nombre de quien reserva, opcional.
    """
    return agendar_cita_raw(fecha, nombre)

