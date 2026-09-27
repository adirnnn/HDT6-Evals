"""consulta del clima en open-meteo y evaluacion de si es seguro saltar."""

from datetime import date, datetime
from zoneinfo import ZoneInfo

import requests

from .config import LATITUD, LONGITUD, MAX_DIAS_PREDICCION, ZONA_HORARIA

URL_FORECAST = "https://api.open-meteo.com/v1/forecast"

# los 5 parametros que pide la hoja de trabajo (wind_gusts_10m es el nombre real
# en open-meteo, la hoja lo escribe en singular)
VARIABLES = "temperature_2m,precipitation,cloud_cover,wind_speed_10m,wind_gusts_10m"

HORA_REPRESENTATIVA = 12  # mediodia: no se pide una hora especifica en la cita


def hoy_local():
    return datetime.now(ZoneInfo(ZONA_HORARIA)).date()


def validar_fecha(fecha_str):
    """revisa que la fecha tenga formato correcto y este dentro de los 16 dias
    que predice open-meteo. devuelve (fecha, None) si esta bien, o (None,
    mensaje_de_error) si hay que corregir al usuario."""
    try:
        fecha = date.fromisoformat(fecha_str.strip())
    except (ValueError, AttributeError):
        return None, f'no entendi la fecha "{fecha_str}", usa el formato AAAA-MM-DD'

    dias_adelante = (fecha - hoy_local()).days

    if dias_adelante < 0:
        return None, f"la fecha {fecha.isoformat()} ya paso, elige una fecha desde hoy en adelante"

    if dias_adelante > MAX_DIAS_PREDICCION:
        return None, (
            f"open-meteo solo predice el clima hasta {MAX_DIAS_PREDICCION} dias hacia "
            f"adelante, y {fecha.isoformat()} queda a {dias_adelante} dias. elige una "
            f"fecha entre hoy y los proximos {MAX_DIAS_PREDICCION} dias"
        )

    return fecha, None


def _pedir_clima(fecha, dias_adelante):
    parametros = {
        "latitude": LATITUD,
        "longitude": LONGITUD,
        "timezone": ZONA_HORARIA,
    }

    if dias_adelante == 0:
        # hoy: el clima "ahorita" ya sirve, se usa el bloque current
        parametros["current"] = VARIABLES
        r = requests.get(URL_FORECAST, params=parametros, timeout=15)
        r.raise_for_status()
        actual = r.json()["current"]
        return {
            "hora": actual["time"],
            "temperatura": actual["temperature_2m"],
            "precipitacion": actual["precipitation"],
            "nubes": actual["cloud_cover"],
            "viento": actual["wind_speed_10m"],
            "rafaga": actual["wind_gusts_10m"],
            "fuente": "current",
        }

    # fecha futura: el bloque daily de open-meteo no trae estas 5 variables
    # (usa agregados como temperature_2m_max), asi que se usa hourly y se toma
    # el mediodia del dia pedido como hora representativa. se pide start_date y
    # end_date iguales a la fecha en vez de forecast_days, porque forecast_days
    # solo llega hasta el dia 15 (hoy + 15) y necesitamos poder llegar hasta el
    # dia 16 que permite open-meteo
    parametros["hourly"] = VARIABLES
    parametros["start_date"] = fecha.isoformat()
    parametros["end_date"] = fecha.isoformat()
    r = requests.get(URL_FORECAST, params=parametros, timeout=15)
    r.raise_for_status()
    datos = r.json()["hourly"]

    hora_buscada = f"{fecha.isoformat()}T{HORA_REPRESENTATIVA:02d}:00"
    try:
        i = datos["time"].index(hora_buscada)
    except ValueError:
        raise RuntimeError(f"open-meteo no devolvio datos para {hora_buscada}")

    return {
        "hora": datos["time"][i],
        "temperatura": datos["temperature_2m"][i],
        "precipitacion": datos["precipitation"][i],
        "nubes": datos["cloud_cover"][i],
        "viento": datos["wind_speed_10m"][i],
        "rafaga": datos["wind_gusts_10m"][i],
        "fuente": "hourly",
    }


_CAMPOS_CLIMA = ("temperatura", "precipitacion", "nubes", "viento", "rafaga")


def consultar_clima_raw(fecha_str):
    """valida la fecha y trae el clima. devuelve un dict con los datos, o
    {"error": ...} si la fecha no sirve o si open-meteo todavia no tiene todos
    los datos para esa fecha (pasa en el borde de los 16 dias)."""
    fecha, error = validar_fecha(fecha_str)
    if error:
        return {"error": error}

    dias_adelante = (fecha - hoy_local()).days
    datos = _pedir_clima(fecha, dias_adelante)

    faltantes = [c for c in _CAMPOS_CLIMA if datos.get(c) is None]
    if faltantes:
        return {
            "error": (
                f"open-meteo todavia no tiene {', '.join(faltantes)} para el "
                f"{fecha.isoformat()} (dias tan lejanos a veces vienen incompletos), "
                "intenta con una fecha un poco mas cercana"
            )
        }

    datos["fecha"] = fecha.isoformat()
    datos["evaluacion"] = evaluar_condiciones(
        datos["viento"], datos["rafaga"], datos["precipitacion"], datos["nubes"]
    )
    return datos


def evaluar_condiciones(viento, rafaga, precipitacion, nubes):
    """aplica los criterios de la hoja de trabajo y devuelve el veredicto final
    mas el detalle de que fallo. viento y rafaga en km/h, precipitacion en mm,
    nubes en % de cobertura."""
    problemas = []

    if precipitacion > 0.0:
        problemas.append(f"precipitacion de {precipitacion} mm (prohibido saltar con lluvia)")

    if rafaga > 35:
        problemas.append(f"rafagas de {rafaga} km/h (el maximo permitido es 35 km/h)")

    if viento < 20:
        nivel_viento = "ideal"
    elif viento <= 28:
        nivel_viento = "marginal"
    else:
        nivel_viento = "prohibido"
        problemas.append(f"viento en superficie de {viento} km/h (excede 28 km/h)")

    if nubes < 30:
        nivel_nubes = "ideal"
    elif nubes <= 75:
        nivel_nubes = "marginal"
    else:
        nivel_nubes = "prohibido"
        problemas.append(f"cobertura de nubes de {nubes}% (excede 75%, visibilidad insuficiente)")

    if problemas:
        veredicto = "NO_SEGURO"
    elif nivel_viento == "marginal" or nivel_nubes == "marginal":
        veredicto = "MARGINAL"
    else:
        veredicto = "IDEAL"

    return {
        "veredicto": veredicto,
        "nivel_viento": nivel_viento,
        "nivel_nubes": nivel_nubes,
        "problemas": problemas,
    }
